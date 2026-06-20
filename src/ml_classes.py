import json
import math
import random
import numpy as np
from collections import deque, defaultdict

try:
    import scipy.stats as _stats
    _SCIPY = True
except ImportError:
    _SCIPY = False

# ─── OpponentHandTracker ───────────────────────────────────────────────────────

class OpponentHandTracker:
    # Bayesian belief over which 4 cards the enemy holds in their hand right now.

    def __init__(self, all_cards: list):
        # Uniform prior: equal probability each card is in the 8-card deck.
        n = len(all_cards)
        self._all_cards = list(all_cards)
        self._belief: dict[str, float] = {c: 1.0 / n for c in all_cards}
        self._played: list[str] = []

    def observe_play(self, card_name: str):
        # Remove played card from belief and renormalise remaining distribution.
        if card_name in self._belief:
            self._belief.pop(card_name)
            self._played.append(card_name)
            total = sum(self._belief.values())
            if total > 0:
                self._belief = {k: v / total for k, v in self._belief.items()}

    def likely_next(self) -> list:
        # Return the top-4 cards by current posterior probability.
        ranked = sorted(self._belief, key=lambda c: self._belief[c], reverse=True)
        return ranked[:4]

    def reset(self):
        # Clear state for a new battle.
        n = len(self._all_cards)
        self._belief = {c: 1.0 / n for c in self._all_cards}
        self._played = []


# ─── ThompsonBandit ───────────────────────────────────────────────────────────

class ThompsonBandit:
    # Beta-distribution Thompson sampling bandit per (card, phase) arm.

    def __init__(self):
        self._alpha: dict[str, float] = defaultdict(lambda: 1.0)
        self._beta: dict[str, float] = defaultdict(lambda: 1.0)

    @staticmethod
    def arm_key(card: str, phase: str) -> str:
        return f"{card}::{phase}"

    def sample(self, card: str, phase: str) -> float:
        # Draw one sample from Beta(alpha, beta) for this arm.
        key = self.arm_key(card, phase)
        a, b = self._alpha[key], self._beta[key]
        if _SCIPY:
            return float(_stats.beta.rvs(a, b))
        # Fallback: approximate via rejection sampling with uniform draws.
        for _ in range(1000):
            x = random.random()
            # Proportional to x^(a-1)*(1-x)^(b-1); normalise by max at mode.
            if a > 1 and b > 1:
                mode = (a - 1) / (a + b - 2)
            else:
                mode = 0.5
            peak = (mode ** (a - 1)) * ((1 - mode) ** (b - 1)) if 0 < mode < 1 else 1.0
            fx = (x ** (a - 1)) * ((1 - x) ** (b - 1)) / (peak + 1e-12)
            if random.random() < fx:
                return x
        return a / (a + b)  # mean as last-resort fallback

    def update(self, card: str, phase: str, reward: float):
        # reward in [0,1]: successes go to alpha, failures to beta.
        key = self.arm_key(card, phase)
        self._alpha[key] += reward
        self._beta[key] += 1.0 - reward

    def save(self, path: str):
        data = {"alpha": dict(self._alpha), "beta": dict(self._beta)}
        with open(path, "w") as f:
            json.dump(data, f)

    def load(self, path: str):
        with open(path) as f:
            data = json.load(f)
        self._alpha = defaultdict(lambda: 1.0, data.get("alpha", {}))
        self._beta = defaultdict(lambda: 1.0, data.get("beta", {}))


# ─── ElixirLeakPredictor ──────────────────────────────────────────────────────

class ElixirLeakPredictor:
    # XGBoost-based predictor for elixir leaking; heuristic fallback when unavailable.

    def __init__(self):
        try:
            import xgboost as xgb
            self._xgb = xgb
            self._model = None
        except ImportError:
            self._xgb = None
            self._model = None

    def features(self, hand_costs, elixir, timer_s, phase) -> np.ndarray:
        # 8-dim feature vector: 4 card costs, current elixir, time, min cost, phase flag.
        costs = list(hand_costs)[:4]
        while len(costs) < 4:
            costs.append(0)
        phase_enc = {"early": 0, "mid": 1, "late": 2, "overtime": 3}.get(phase, 1)
        return np.array(costs + [elixir, timer_s, min(costs), phase_enc], dtype=np.float32)

    def will_leak(self, hand_costs, elixir, timer_s, phase) -> bool:
        # Predict whether elixir will leak in the next 10 seconds.
        if self._model is not None:
            feat = self.features(hand_costs, elixir, timer_s, phase).reshape(1, -1)
            pred = self._model.predict(feat)
            return bool(pred[0] > 0.5)
        # Heuristic: leak if elixir nearly full and cheapest card is expensive.
        return elixir >= 9 and min(hand_costs) > 4

    def train(self, replay_data: list):
        # Train from a list of dicts with keys: hand_costs, elixir, timer_s, phase, leaked.
        if self._xgb is None:
            return
        X = np.array([
            self.features(d["hand_costs"], d["elixir"], d["timer_s"], d["phase"])
            for d in replay_data
        ])
        y = np.array([int(d["leaked"]) for d in replay_data])
        self._model = self._xgb.XGBClassifier(n_estimators=100, use_label_encoder=False,
                                               eval_metric="logloss")
        self._model.fit(X, y)


# ─── UKFTroopTracker ──────────────────────────────────────────────────────────

class UKFTroopTracker:
    # Unscented Kalman Filter per troop track; linear fallback when filterpy missing.

    def __init__(self):
        try:
            from filterpy.kalman import UnscentedKalmanFilter as _UKF
            from filterpy.kalman import MerweScaledSigmaPoints
            self._UKF = _UKF
            self._SigmaPoints = MerweScaledSigmaPoints
            self._filterpy = True
        except ImportError:
            self._filterpy = False
        # Tracks: id -> ukf or (x, y, vx, vy, t) for fallback.
        self._tracks: dict = {}

    def _fx(self, x, dt):
        # State transition: [x, y, vx, vy] with constant velocity.
        return np.array([x[0] + x[2] * dt, x[1] + x[3] * dt, x[2], x[3]])

    def _hx(self, x):
        # Observation model: we see [x, y].
        return x[:2]

    def _make_ukf(self):
        pts = self._SigmaPoints(n=4, alpha=0.1, beta=2., kappa=-1)
        ukf = self._UKF(dim_x=4, dim_z=2, fx=self._fx, hx=self._hx,
                        dt=0.1, points=pts)
        ukf.x = np.zeros(4)
        ukf.P *= 0.1
        ukf.R = np.eye(2) * 0.01
        ukf.Q = np.eye(4) * 0.001
        return ukf

    def update(self, track_id, x_norm: float, y_norm: float):
        # Predict then update the UKF (or linear tracker) for this troop.
        if self._filterpy:
            if track_id not in self._tracks:
                ukf = self._make_ukf()
                ukf.x[:2] = [x_norm, y_norm]
                self._tracks[track_id] = ukf
            else:
                ukf = self._tracks[track_id]
                ukf.predict()
                ukf.update(np.array([x_norm, y_norm]))
        else:
            import time as _time
            now = _time.monotonic()
            if track_id in self._tracks:
                prev = self._tracks[track_id]
                dt = now - prev[4]
                vx = (x_norm - prev[0]) / max(dt, 1e-3)
                vy = (y_norm - prev[1]) / max(dt, 1e-3)
                self._tracks[track_id] = (x_norm, y_norm, vx, vy, now)
            else:
                self._tracks[track_id] = (x_norm, y_norm, 0.0, 0.0, now)

    def predict_ahead(self, track_id, dt: float) -> tuple:
        # Return predicted (x, y) position dt seconds in the future.
        if track_id not in self._tracks:
            return (0.5, 0.5)
        if self._filterpy:
            ukf = self._tracks[track_id]
            pred = self._fx(ukf.x, dt)
            return (float(pred[0]), float(pred[1]))
        else:
            x, y, vx, vy, _ = self._tracks[track_id]
            return (x + vx * dt, y + vy * dt)


# ─── DecisionTransformerScorer ────────────────────────────────────────────────

class DecisionTransformerScorer:
    # Transformer-based card scorer; scaffold requires fine-tuning before use.

    def __init__(self, n_cards=110, d_model=128, n_heads=4, n_layers=2):
        try:
            import torch
            from torch import nn
            self._torch = torch
            self._nn = nn
            self._d_model = d_model
            self._n_cards = n_cards
            # Simple encoder: card embed + positional + transformer layers.
            self._embed = nn.Embedding(n_cards + 4, d_model)  # +4 for special tokens
            enc_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=n_heads,
                                                   batch_first=True)
            self._transformer = nn.TransformerEncoder(enc_layer, num_layers=n_layers)
            self._head = nn.Linear(d_model, 1)
            self._ready = True
        except ImportError:
            self._ready = False

    def tokenize(self, hand, board_state, elixir, phase):
        # Encode hand + board context into a (1, seq_len, d_model) tensor.
        if not self._ready:
            return None
        torch = self._torch
        # Map card names to ids 0..n_cards-1; unknown → n_cards.
        ids = [hash(c) % self._n_cards for c in hand[:4]]
        ids += [hash(str(elixir)) % self._n_cards,
                hash(str(phase)) % self._n_cards]
        t = torch.tensor([ids], dtype=torch.long)          # (1, seq_len)
        emb = self._embed(t)                               # (1, seq_len, d_model)
        return emb

    def score(self, hand, board_state, elixir, phase) -> dict:
        # Return a {card: score} mapping for each card in hand.
        if not self._ready:
            return {}
        emb = self.tokenize(hand, board_state, elixir, phase)
        enc = self._transformer(emb)                       # (1, seq_len, d_model)
        scores = self._head(enc).squeeze(-1).squeeze(0)    # (seq_len,)
        scores = scores.detach()
        return {c: float(scores[i]) for i, c in enumerate(hand[:4])}


# ─── AttentiveGNNScorer ───────────────────────────────────────────────────────

class AttentiveGNNScorer:
    # Graph Attention Network scoring per-unit danger; scaffold requires training.

    def __init__(self, in_dim=5, hidden=64, heads=4):
        try:
            import torch
            from torch import nn
            self._torch = torch
            self._nn = nn
            self._in_dim = in_dim
            self._hidden = hidden
            self._heads = heads
            # Single GAT-like attention layer (manual, avoids torch_geometric dep).
            self._W = nn.Linear(in_dim, hidden * heads)
            self._attn = nn.Linear(2 * hidden * heads, 1)
            self._out = nn.Linear(hidden * heads, 1)
            self._ready = True
        except ImportError:
            self._ready = False

    def build_graph(self, troops: list) -> tuple:
        # Build node feature matrix and fully-connected edge index from troop list.
        if not troops:
            return np.zeros((0, 5)), np.zeros((2, 0), dtype=int)
        feats = []
        for t in troops:
            feats.append([
                t.get("x_norm", 0.5),
                t.get("y_norm", 0.5),
                t.get("hp_norm", 1.0),
                float(t.get("is_enemy", 0)),
                t.get("speed_norm", 0.5),
            ])
        node_feats = np.array(feats, dtype=np.float32)
        n = len(troops)
        rows, cols = [], []
        for i in range(n):
            for j in range(n):
                if i != j:
                    rows.append(i)
                    cols.append(j)
        edge_index = np.array([rows, cols], dtype=int)
        return node_feats, edge_index

    def score(self, troops: list) -> np.ndarray:
        # Return per-unit danger scores as a numpy array.
        if not troops:
            return np.array([])
        if not self._ready:
            return np.ones(len(troops)) / len(troops)
        node_feats, edge_index = self.build_graph(troops)
        torch = self._torch
        x = torch.tensor(node_feats)                   # (N, in_dim)
        h = self._W(x)                                 # (N, hidden*heads)
        if edge_index.shape[1] == 0:
            out = self._out(h).squeeze(-1)
        else:
            src = torch.tensor(edge_index[0])
            dst = torch.tensor(edge_index[1])
            e_feat = torch.cat([h[src], h[dst]], dim=-1)
            attn_w = torch.softmax(self._attn(e_feat).squeeze(-1), dim=0)
            agg = torch.zeros_like(h)
            for i, (s, d) in enumerate(zip(edge_index[0], edge_index[1])):
                agg[d] += attn_w[i] * h[s]
            out = self._out(agg).squeeze(-1)
        return out.detach().numpy()


# ─── DreamerV3RSSM ────────────────────────────────────────────────────────────

class DreamerV3RSSM:
    # Recurrent State Space Model for imagination-based lookahead; scaffold only.

    def __init__(self, latent_dim=128, action_dim=576):
        try:
            import torch
            from torch import nn
            self._torch = torch
            self._nn = nn
            self._latent_dim = latent_dim
            self._action_dim = action_dim
            self._encoder = nn.Sequential(
                nn.Linear(latent_dim, latent_dim),
                nn.ELU(),
                nn.Linear(latent_dim, latent_dim),
            )
            self._dynamics = nn.GRUCell(action_dim + latent_dim, latent_dim)
            self._reward_head = nn.Sequential(
                nn.Linear(latent_dim, 64),
                nn.ELU(),
                nn.Linear(64, 1),
            )
            self._ready = True
        except ImportError:
            self._ready = False

    def encode(self, obs: np.ndarray):
        # Map a flat observation array to a latent state tensor.
        if not self._ready:
            return 0.0
        torch = self._torch
        x = torch.tensor(obs, dtype=torch.float32)
        if x.shape[-1] != self._latent_dim:
            # Pad or truncate to match expected dim.
            x = x[:self._latent_dim] if x.numel() >= self._latent_dim else \
                torch.cat([x, torch.zeros(self._latent_dim - x.numel())])
        return self._encoder(x.unsqueeze(0))             # (1, latent_dim)

    def imagine(self, latent, action_seq, steps=3) -> list:
        # Unroll latent dynamics for `steps` steps given an action sequence.
        if not self._ready:
            return [0.0] * steps
        torch = self._torch
        h = latent if hasattr(latent, "shape") else torch.zeros(1, self._latent_dim)
        results = []
        for i in range(steps):
            if i < len(action_seq):
                a = torch.tensor(action_seq[i], dtype=torch.float32)
                if a.numel() != self._action_dim:
                    a = torch.zeros(self._action_dim)
                a = a.unsqueeze(0)
            else:
                a = torch.zeros(1, self._action_dim)
            inp = torch.cat([h, a], dim=-1)
            h = self._dynamics(inp, h)
            results.append(h)
        return results

    def decode_reward(self, latent) -> float:
        # Predict scalar reward from a latent state.
        if not self._ready:
            return 0.0
        if not hasattr(latent, "shape"):
            return 0.0
        return float(self._reward_head(latent).squeeze())


# ─── EWCContinualLearner ──────────────────────────────────────────────────────

class EWCContinualLearner:
    # Elastic Weight Consolidation to prevent catastrophic forgetting.

    def __init__(self, model, lambda_ewc=400.0):
        try:
            import torch
            self._torch = torch
            self._ready = True
        except ImportError:
            self._ready = False
        self._model = model
        self._lambda = lambda_ewc
        self._fisher: dict = {}   # param name → Fisher diagonal
        self._theta_star: dict = {}  # param name → stored weights θ*

    def compute_fisher(self, dataloader):
        # Estimate diagonal Fisher information via squared gradients.
        if not self._ready or self._model is None:
            return
        torch = self._torch
        self._fisher = {n: torch.zeros_like(p)
                        for n, p in self._model.named_parameters()
                        if p.requires_grad}
        self._model.eval()
        for batch in dataloader:
            self._model.zero_grad()
            x, y = batch
            loss = self._model(x)
            if hasattr(loss, "mean"):
                loss = loss.mean()
            loss.backward()
            for n, p in self._model.named_parameters():
                if p.grad is not None:
                    self._fisher[n] += p.grad.detach() ** 2
        n = max(len(dataloader), 1)
        for n_key in self._fisher:
            self._fisher[n_key] /= n

    def ewc_loss(self, model):
        # Compute the EWC penalty term: λ/2 * Σ F_i * (θ_i - θ*_i)^2.
        if not self._ready or not self._fisher:
            return 0.0
        torch = self._torch
        loss = torch.tensor(0.0)
        for name, param in model.named_parameters():
            if name in self._fisher and name in self._theta_star:
                loss += (self._fisher[name] *
                         (param - self._theta_star[name]) ** 2).sum()
        return self._lambda / 2.0 * loss

    def consolidate(self, model):
        # Store current weights θ* for future EWC penalty computation.
        if not self._ready:
            return
        self._theta_star = {
            n: p.detach().clone()
            for n, p in model.named_parameters()
            if p.requires_grad
        }


# ─── BrainLikeReplayBuffer ────────────────────────────────────────────────────

class BrainLikeReplayBuffer:
    # Experience replay buffer with KL-divergence priority over expert vs bot policy.

    def __init__(self, capacity=10000):
        self._buffer: deque = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, bot_logits, expert_logits):
        # Store a transition along with both policy logit arrays.
        self._buffer.append({
            "state": state,
            "action": action,
            "reward": reward,
            "next_state": next_state,
            "bot_logits": list(bot_logits),
            "expert_logits": list(expert_logits),
        })

    def priority(self, idx: int) -> float:
        # KL(bot_π || expert_π) for transition at index idx.
        item = list(self._buffer)[idx]
        bot = np.array(item["bot_logits"], dtype=np.float64)
        exp = np.array(item["expert_logits"], dtype=np.float64)
        # Softmax both distributions.
        bot = np.exp(bot - bot.max()); bot /= bot.sum()
        exp = np.exp(exp - exp.max()); exp /= exp.sum()
        # KL = Σ p * log(p/q), clip for numerical safety.
        kl = float(np.sum(bot * np.log(np.clip(bot / np.clip(exp, 1e-9, None), 1e-9, None))))
        return max(kl, 1e-6)

    def sample(self, batch_size: int) -> list:
        # Sample transitions proportional to KL priority.
        n = len(self._buffer)
        if n == 0:
            return []
        priorities = np.array([self.priority(i) for i in range(n)], dtype=np.float64)
        probs = priorities / priorities.sum()
        idxs = np.random.choice(n, size=min(batch_size, n), replace=False, p=probs)
        buf = list(self._buffer)
        return [buf[i] for i in idxs]


# ─── KernelBandit ─────────────────────────────────────────────────────────────

class KernelBandit:
    # RBF Kernel UCB bandit for evaluating elixir trade quality.

    def __init__(self, context_dim=8, beta=2.0):
        try:
            from sklearn.gaussian_process.kernels import RBF
            self._kernel = RBF(length_scale=1.0)
            self._sklearn = True
        except ImportError:
            self._sklearn = False
            self._kernel = None
        self._beta = beta
        self._context_dim = context_dim
        self._contexts: list = []   # observed context vectors
        self._actions: list = []    # observed action indices
        self._rewards: list = []    # observed rewards
        self._K_inv = None          # inverse kernel matrix cache

    def encode_context(self, hand, board) -> np.ndarray:
        # Encode hand costs and board summary into an 8-dim feature vector.
        costs = [c if isinstance(c, (int, float)) else 0 for c in list(hand)[:4]]
        while len(costs) < 4:
            costs.append(0)
        board_feats = list(board)[:4] if hasattr(board, "__iter__") else [0, 0, 0, 0]
        while len(board_feats) < 4:
            board_feats.append(0)
        return np.array(costs + board_feats, dtype=np.float64)

    def _rbf(self, x1, x2, length=1.0):
        # Manual RBF kernel: k(x1,x2) = exp(-||x1-x2||²/(2l²)).
        diff = x1 - x2
        return float(np.exp(-np.dot(diff, diff) / (2 * length ** 2)))

    def select_action(self, contexts: list) -> int:
        # UCB selection: argmax μ(x) + β * σ(x) over candidate action contexts.
        if not contexts:
            return 0
        if not self._contexts:
            return random.randrange(len(contexts))
        if not self._sklearn:
            return random.randrange(len(contexts))
        best_idx, best_ucb = 0, -1e9
        for i, ctx in enumerate(contexts):
            c = np.array(ctx, dtype=np.float64)
            # Kernel vector between candidate and observed points.
            k_vec = np.array([self._rbf(c, np.array(x)) for x in self._contexts])
            k_self = self._rbf(c, c)
            r_vec = np.array(self._rewards)
            if self._K_inv is not None:
                mu = float(k_vec @ self._K_inv @ r_vec)
                var = k_self - float(k_vec @ self._K_inv @ k_vec)
            else:
                mu = 0.0
                var = k_self
            ucb = mu + self._beta * math.sqrt(max(var, 0))
            if ucb > best_ucb:
                best_ucb = ucb
                best_idx = i
        return best_idx

    def update(self, context, action, reward: float):
        # Add new observation and recompute inverse kernel matrix.
        ctx = np.array(context, dtype=np.float64)
        self._contexts.append(ctx)
        self._actions.append(action)
        self._rewards.append(reward)
        n = len(self._contexts)
        K = np.array([[self._rbf(self._contexts[i], self._contexts[j])
                       for j in range(n)] for i in range(n)])
        K += np.eye(n) * 1e-4  # regularisation
        try:
            self._K_inv = np.linalg.inv(K)
        except np.linalg.LinAlgError:
            self._K_inv = None


# ─── LoRAScorer ───────────────────────────────────────────────────────────────

class LoRAScorer:
    # TinyLlama-based auxiliary card scorer via token log-probability continuation.

    def __init__(self, model_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0"):
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch
            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForCausalLM.from_pretrained(
                model_name, torch_dtype=torch.float16
            )
            self._model.eval()
            self._ready = True
        except (ImportError, Exception):
            self._ready = False

    def score(self, hand: list, board_summary: str) -> dict:
        # Score each card via log-probability of card name as the next token.
        if not self._ready:
            return {}
        torch = self._torch
        cards_str = ", ".join(hand)
        prompt = f"Hand: {cards_str}. Board: {board_summary}. Best play:"
        enc = self._tokenizer(prompt, return_tensors="pt")
        scores = {}
        with torch.no_grad():
            base_out = self._model(**enc)
            logits = base_out.logits[0, -1, :]   # next-token logits
            log_probs = torch.log_softmax(logits, dim=-1)
            for card in hand:
                # Score by the log-prob of the first subword of the card name.
                card_ids = self._tokenizer.encode(card, add_special_tokens=False)
                if card_ids:
                    scores[card] = float(log_probs[card_ids[0]])
                else:
                    scores[card] = 0.0
        return scores


# ─── GroundedSAM2Detector ─────────────────────────────────────────────────────

class GroundedSAM2Detector:
    # Zero-shot troop detection via GroundingDINO + SAM2; graceful fallback.

    def __init__(self):
        self.ready = False
        try:
            from groundingdino.util.inference import load_model, predict
            import supervision as sv
            self._load_model = load_model
            self._predict = predict
            self._sv = sv
            # Load with default weights paths; user must supply actual paths.
            self._gdino_model = None
            self._sam2_model = None
            self.ready = False   # remains False until weights loaded explicitly
        except (ImportError, Exception):
            self.ready = False

    def detect(self, frame, prompts=None) -> list:
        # Return detections in YOLOTroopDetector format: list of dicts.
        if prompts is None:
            prompts = ["troop", "unit", "tower"]
        if not self.ready or self._gdino_model is None:
            return []
        try:
            import torch
            from groundingdino.util.inference import predict
            import cv2
            # GroundingDINO expects PIL images; convert from BGR numpy.
            from PIL import Image as _PIL
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = _PIL.fromarray(rgb)
            results = []
            for prompt in prompts:
                boxes, logits, phrases = predict(
                    model=self._gdino_model,
                    image=pil_img,
                    caption=prompt,
                    box_threshold=0.3,
                    text_threshold=0.25,
                )
                h, w = frame.shape[:2]
                for box, conf, phrase in zip(boxes, logits, phrases):
                    cx, cy, bw, bh = box.tolist()
                    results.append({
                        "label": phrase,
                        "confidence": float(conf),
                        "x_norm": cx,
                        "y_norm": cy,
                        "w_norm": bw,
                        "h_norm": bh,
                    })
            return results
        except Exception:
            return []


# ─── BenchmarkRunner ──────────────────────────────────────────────────────────

class BenchmarkRunner:
    # Validates bot performance vs. fixed archetype win-rate baselines.

    archetypes = {
        "Hog Cycle": {
            "deck": ["Hog Rider", "Ice Spirit", "Skeletons", "Log",
                     "Musketeer", "Cannon", "Knight", "Ice Golem"],
            "baseline_winrate": 0.50,
        },
        "Beatdown": {
            "deck": ["Golem", "Baby Dragon", "Mega Minion", "Lumberjack",
                     "Night Witch", "Elixir Collector", "Zap", "Lightning"],
            "baseline_winrate": 0.48,
        },
        "Control": {
            "deck": ["X-Bow", "Tesla", "Ice Spirit", "Fireball",
                     "Archers", "Log", "Knight", "Ice Golem"],
            "baseline_winrate": 0.47,
        },
    }

    def __init__(self, bot_stats_path=None):
        self._path = bot_stats_path
        # Try to hydrate from POST_MATCH_ANALYZER if available globally.
        self._extra_history: list = []
        try:
            global POST_MATCH_ANALYZER
            if POST_MATCH_ANALYZER is not None and hasattr(POST_MATCH_ANALYZER, "history"):
                self._extra_history = POST_MATCH_ANALYZER.history
        except (NameError, AttributeError):
            pass

    def _opponent_archetype(self, match: dict) -> str:
        # Classify a match's opponent deck into one of the known archetypes.
        opp_cards = set(match.get("opponent_deck", []))
        best, best_overlap = "Unknown", -1
        for name, info in self.archetypes.items():
            overlap = len(opp_cards & set(info["deck"]))
            if overlap > best_overlap:
                best_overlap = overlap
                best = name
        return best

    def run_check(self, history: list) -> dict:
        # Compute win% per archetype from a list of match result dicts.
        # Each match dict: {"result": "win"|"loss", "opponent_deck": [...]}
        counts: dict = {arch: {"wins": 0, "total": 0} for arch in self.archetypes}
        all_matches = history + self._extra_history
        for match in all_matches:
            arch = self._opponent_archetype(match)
            if arch in counts:
                counts[arch]["total"] += 1
                if match.get("result") == "win":
                    counts[arch]["wins"] += 1
        results = {}
        for arch, data in counts.items():
            if data["total"] > 0:
                results[arch] = data["wins"] / data["total"]
            else:
                results[arch] = None  # not enough data
        return results

    def alert_if_degraded(self, history: list, threshold=0.05) -> list:
        # Return list of archetypes where win% has dropped below baseline - threshold.
        winrates = self.run_check(history)
        degraded = []
        for arch, wr in winrates.items():
            if wr is None:
                continue
            baseline = self.archetypes[arch]["baseline_winrate"]
            if wr < baseline - threshold:
                degraded.append(arch)
        return degraded
