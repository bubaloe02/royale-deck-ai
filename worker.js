// ─── ROYALE DECK AI v2.0.1 WORKER ────────────────────────────────────────────
// v2 improvements:
// 1. Trophy-range filtering
// 2. Wilson score confidence interval
// 3. Temporal decay (recent battles weighted 2x)
// 4. Card interaction graph + PageRank anchors
// 5. Meta velocity detection

const CR_API = "https://proxy.royaleapi.dev/v1";
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Content-Type": "application/json",
};

const MIN_TROPHIES = 4000;
const CRAWL_INTERVAL_MS = 10 * 60 * 1000;
const RECENT_BATTLE_WINDOW_MS = 48 * 60 * 60 * 1000; // 48 hours
const HISTORICAL_WINDOW_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

const LOCATION_IDS = [
  57000000,57000049,57000077,57000094,57000160,57000214,57000261,
  57000033,57000044,57000060,57000075,57000076,57000086,57000093,
  57000095,57000097,57000098,57000103,57000105,57000110,57000113,
  57000116,57000119,57000127,57000128,57000130,57000131,57000133,
  57000136,57000137,57000138,57000139,57000140,57000141,57000142,
  57000143,57000145,57000146,57000149,57000150,57000152,57000153,
  57000154,57000155,57000157,57000158,57000159,57000161,57000163,
];

// Trophy brackets
const TROPHY_BRACKETS = [
  { name: "Legend",     min: 10000, max: 99999 },
  { name: "Champion",   min: 8000,  max: 9999  },
  { name: "Master",     min: 6000,  max: 7999  },
  { name: "Challenger", min: 4000,  max: 5999  },
];

function getTrophyBracket(trophies) {
  return TROPHY_BRACKETS.find(b => trophies >= b.min && trophies <= b.max) || TROPHY_BRACKETS[3];
}

const META_DECKS = [
  { name:"Hog EQ Cycle", archetype:"Hog Cycle", tier:"S", cards:["Hog Rider","Earthquake","Firecracker","Skeletons","Ice Spirit","Cannon","The Log","Knight"] },
  { name:"Hog FC Cycle", archetype:"Hog Cycle", tier:"S", cards:["Hog Rider","Firecracker","Skeletons","Ice Spirit","Cannon","The Log","Musketeer","Knight"] },
  { name:"Pekka Bridge Spam", archetype:"Pekka Bridge Spam", tier:"S", cards:["P.E.K.K.A","Bandit","Royal Ghost","Battle Ram","Poison","Zap","Magic Archer","Electro Wizard"] },
  { name:"LavaLoon", archetype:"LavaLoon", tier:"S", cards:["Lava Hound","Balloon","Tombstone","Mega Minion","Lumberjack","Zap","Lightning","Minions"] },
  { name:"Log Bait", archetype:"Log Bait", tier:"S", cards:["Goblin Barrel","Princess","Goblin Gang","Rocket","Inferno Tower","Knight","The Log","Barbarian Barrel"] },
  { name:"Miner Poison Cycle", archetype:"Miner Cycle", tier:"A+", cards:["Miner","Poison","Wall Breakers","Bats","Goblin Gang","Zap","Musketeer","Ice Golem"] },
  { name:"Giant Witch", archetype:"Giant Beatdown", tier:"A+", cards:["Giant","Witch","Musketeer","Poison","Zap","Archers","Skeleton Army","Tombstone"] },
  { name:"Golem Beatdown", archetype:"Golem Beatdown", tier:"A+", cards:["Golem","Night Witch","Baby Dragon","Lightning","Tornado","Zap","Tombstone","Mega Minion"] },
  { name:"Graveyard Poison", archetype:"Graveyard Control", tier:"A+", cards:["Graveyard","Poison","Ice Golem","Tombstone","Minions","Archers","Barbarian Barrel","Knight"] },
  { name:"X-Bow Cycle", archetype:"X-Bow Siege", tier:"A+", cards:["X-Bow","Tesla","Ice Spirit","Skeletons","The Log","Archers","Ice Golem","Earthquake"] },
  { name:"Mortar Bait", archetype:"Mortar Siege", tier:"A", cards:["Mortar","Goblin Gang","Archers","Skeletons","Fireball","Zap","Ice Spirit","Bats"] },
  { name:"Royal Giant Control", archetype:"Mixed", tier:"A", cards:["Royal Giant","Electro Dragon","Cannon Cart","Earthquake","Zap","Musketeer","Skeletons","Ice Spirit"] },
  { name:"Ram Rider Bridge Spam", archetype:"Pekka Bridge Spam", tier:"A", cards:["Ram Rider","Bandit","Goblin Gang","Poison","Zap","Magic Archer","Skeletons","Electro Wizard"] },
  { name:"Hog AQ Cycle", archetype:"Hog Cycle", tier:"A", cards:["Hog Rider","Archers","Ice Golem","Skeletons","Cannon","Fireball","The Log","Ice Spirit"] },
  { name:"Balloon Cycle", archetype:"Balloon Cycle", tier:"A", cards:["Balloon","Freeze","Minions","Skeleton Army","Arrows","Ice Spirit","Goblin Gang","Mega Minion"] },
  { name:"Miner Wall Breakers", archetype:"Miner Cycle", tier:"A", cards:["Miner","Wall Breakers","Goblin Gang","Fireball","Archers","Bats","Zap","Cannon"] },
  { name:"Pekka Ram Rider", archetype:"Pekka Bridge Spam", tier:"A", cards:["P.E.K.K.A","Ram Rider","Bandit","Poison","Zap","Magic Archer","Skeletons","Electro Wizard"] },
  { name:"Golem Night Witch", archetype:"Golem Beatdown", tier:"A", cards:["Golem","Night Witch","Mega Minion","Baby Dragon","Earthquake","Zap","Tombstone","Lightning"] },
  { name:"Hog Cycle Classic", archetype:"Hog Cycle", tier:"B+", cards:["Hog Rider","Musketeer","Cannon","Ice Golem","Fireball","The Log","Skeletons","Ice Spirit"] },
  { name:"Electro Giant Control", archetype:"Mixed", tier:"B+", cards:["Electro Giant","Tornado","Electro Spirit","Musketeer","Zap","The Log","Archers","Ice Golem"] },
  { name:"Mini Pekka Bait", archetype:"Log Bait", tier:"B", cards:["Mini P.E.K.K.A","Goblin Barrel","Princess","Goblin Gang","Rocket","Zap","The Log","Ice Spirit"] },
];

function matchMetaDeck(cards) {
  const sortedCards = [...cards].sort();
  for (const meta of META_DECKS) {
    const sortedMeta = [...meta.cards].sort();
    const matches = sortedCards.filter(c => sortedMeta.some(m => m.toLowerCase() === c.toLowerCase())).length;
    if (matches >= 7) return { name:meta.name, archetype:meta.archetype, tier:meta.tier };
  }
  const names = cards.map(c => c.toLowerCase());
  if (names.includes("hog rider")) return { name:"Hog Cycle", archetype:"Hog Cycle", tier:"A" };
  if (names.includes("lava hound")) return { name:"LavaLoon", archetype:"LavaLoon", tier:"A" };
  if (names.includes("golem")) return { name:"Golem Beatdown", archetype:"Golem Beatdown", tier:"A" };
  if (names.includes("goblin barrel")) return { name:"Bait", archetype:"Log Bait", tier:"A" };
  if (names.includes("x-bow")) return { name:"X-Bow Siege", archetype:"X-Bow Siege", tier:"A" };
  if (names.includes("mortar")) return { name:"Mortar Siege", archetype:"Mortar Siege", tier:"B+" };
  if (names.includes("miner")) return { name:"Miner Cycle", archetype:"Miner Cycle", tier:"A" };
  if (names.includes("graveyard")) return { name:"Graveyard Control", archetype:"Graveyard Control", tier:"A" };
  if (names.includes("p.e.k.k.a")) return { name:"Pekka Bridge Spam", archetype:"Pekka Bridge Spam", tier:"A" };
  return { name:"Meta Deck", archetype:"Mixed", tier:"B" };
}

// ─── V2: WILSON SCORE CONFIDENCE INTERVAL ────────────────────────────────────
// Replaces raw win rate — demotes low-sample decks automatically
// z=1.96 for 95% confidence
function wilsonScore(wins, losses) {
  const n = wins + losses;
  if (n === 0) return 0;
  const p = wins / n;
  const z = 1.96;
  const z2 = z * z;
  const numerator = p + z2 / (2 * n) - z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n);
  const denominator = 1 + z2 / n;
  return numerator / denominator;
}

// ─── V2: TEMPORAL DECAY ───────────────────────────────────────────────────────
// Recent battles (< 48h) weighted 2x, older weighted 1x
function temporalScore(recentWins, recentLosses, oldWins, oldLosses) {
  const weightedWins = recentWins * 2 + oldWins;
  const weightedLosses = recentLosses * 2 + oldLosses;
  return wilsonScore(weightedWins, weightedLosses);
}

// ─── V2: CARD INTERACTION GRAPH (simplified PageRank) ────────────────────────
// Builds adjacency weights from pair win rates
// Returns top "anchor" cards — most connected in winning decks
function buildCardGraph(pairStats) {
  const graph = {}; // card -> { neighbor: weight }
  for (const pair of pairStats) {
    const wr = pair.wins / (pair.wins + pair.losses);
    if (wr < 0.5) continue; // only positive synergies
    const [a, b] = pair.pair_key.split("|");
    if (!graph[a]) graph[a] = {};
    if (!graph[b]) graph[b] = {};
    const weight = wr * Math.log(pair.wins + pair.losses + 1); // wr * confidence
    graph[a][b] = (graph[a][b] || 0) + weight;
    graph[b][a] = (graph[b][a] || 0) + weight;
  }

  // Simplified PageRank — 10 iterations
  const cards = Object.keys(graph);
  const scores = {};
  cards.forEach(c => { scores[c] = 1.0; });

  for (let iter = 0; iter < 10; iter++) {
    const newScores = {};
    cards.forEach(c => {
      let sum = 0;
      const neighbors = graph[c] || {};
      Object.entries(neighbors).forEach(([n, w]) => {
        const totalOut = Object.values(graph[n] || {}).reduce((a,b)=>a+b,0);
        if (totalOut > 0) sum += scores[n] * w / totalOut;
      });
      newScores[c] = 0.15 + 0.85 * sum;
    });
    cards.forEach(c => { scores[c] = newScores[c] || scores[c]; });
  }

  return scores; // card -> pagerank score
}

// ─── V2: META VELOCITY ────────────────────────────────────────────────────────
// Detects cards rising/falling in win rate
function calcMetaVelocity(recentWR, historicalWR) {
  if (historicalWR === 0) return 0;
  return recentWR - historicalWR; // positive = rising, negative = falling
}

// ─── ROUTER ───────────────────────────────────────────────────────────────────

export default {
  async fetch(req, env, ctx) {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS_HEADERS });
    const url = new URL(req.url);

    if (url.pathname === "/recommend" && req.method === "POST") {
      ctx.waitUntil(maybeCrawl(env));
      return handleRecommend(req, env);
    }
    if (url.pathname === "/meta/status") return handleStatus(req, env);
    if (url.pathname === "/meta/crawl") {
      ctx.waitUntil(runCrawl(env));
      return json({ ok:true, message:"Crawl started" });
    }
    if (url.pathname === "/meta/seed") {
      ctx.waitUntil(seedAll(env));
      return json({ ok:true, message:"Seeding..." });
    }
    if (url.pathname === "/meta/aggregate") {
      ctx.waitUntil(runAggregator(env));
      return json({ ok:true, message:"Aggregator started" });
    }
    if (url.pathname === "/meta/velocity") return handleMetaVelocity(req, env);
    if (url.pathname === "/meta/graph") return handleCardGraph(req, env);
    if (url.pathname === "/meta/news") return handleMetaNews(req, env);
    if (url.pathname === "/ai/recommend" && req.method === "POST") return handleAIRecommend(req, env);
    if (url.pathname === "/ai/chat" && req.method === "POST") return handleAIChat(req, env);
    if (url.pathname === "/stats/decks") return handleDeckStats(req, env);
    return proxyToCR(req, env);
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runCrawl(env));
  }
};

async function maybeCrawl(env) {
  try {
    const state = await env.DB.prepare("SELECT last_crawl FROM crawl_state WHERE id=1").first();
    if (Date.now() - (state?.last_crawl || 0) > CRAWL_INTERVAL_MS) await runCrawl(env);
  } catch(e) { console.error("maybeCrawl:", e.message); }
}

async function proxyToCR(req, env) {
  try {
    const url = new URL(req.url);
    const path = url.pathname.replace(/^\/v1/, "");
    const res = await fetch(`${CR_API}${path}${url.search}`, {
      headers: { "Authorization": `Bearer ${env.CR_API_KEY}` }
    });
    return new Response(await res.text(), { status: res.status, headers: CORS_HEADERS });
  } catch(e) { return json({ error: e.message }, 500); }
}

// ─── SEED ─────────────────────────────────────────────────────────────────────

async function seedAll(env) {
  let totalQueued = 0;
  const locationOffset = Math.floor((Date.now() / 60000)) % LOCATION_IDS.length;
  const locBatch = LOCATION_IDS.slice(locationOffset, locationOffset + 5);

  for (const locId of locBatch) {
    try {
      const res = await fetch(`${CR_API}/locations/${locId}/rankings/players?limit=200`, {
        headers: { "Authorization": `Bearer ${env.CR_API_KEY}` }
      });
      if (!res.ok) continue;
      const data = await res.json();
      for (const p of (data.items || []).filter(p => (p.trophies||0) >= MIN_TROPHIES)) {
        await enqueuePlayer(env, p.tag, p.trophies||0, p.name||"");
        totalQueued++;
      }
    } catch(e) { console.error("Seed location:", locId, e.message); }
    await sleep(200);
  }

  for (const minScore of [55000, 45000, 35000]) {
    try {
      const res = await fetch(`${CR_API}/clans?minMembers=40&minScore=${minScore}&limit=10`, {
        headers: { "Authorization": `Bearer ${env.CR_API_KEY}` }
      });
      if (!res.ok) continue;
      const data = await res.json();
      for (const clan of (data.items||[]).slice(0,5)) {
        const members = await getClanMembers(env, clan.tag);
        for (const m of members) { await enqueuePlayer(env, m.tag, m.trophies||0, m.name||""); totalQueued++; }
      }
    } catch(e) {}
  }

  console.log(`Seeded ${totalQueued} players`);
  return totalQueued;
}

async function getClanMembers(env, clanTag) {
  try {
    const tag = clanTag.replace("#", "%23");
    const res = await fetch(`${CR_API}/clans/${tag}/members`, {
      headers: { "Authorization": `Bearer ${env.CR_API_KEY}` }
    });
    if (!res.ok) return [];
    const data = await res.json();
    return (data.items||[]).filter(m => (m.trophies||0) >= MIN_TROPHIES);
  } catch(e) { return []; }
}

async function enqueuePlayer(env, tag, trophies=0, name="") {
  try {
    await env.DB.prepare(`
      INSERT INTO players (tag, name, trophies, last_scanned, scan_count, queued)
      VALUES (?, ?, ?, 0, 0, 1)
      ON CONFLICT(tag) DO UPDATE SET
        trophies = MAX(trophies, excluded.trophies),
        name = CASE WHEN excluded.name != '' THEN excluded.name ELSE name END,
        queued = CASE WHEN queued = 0 AND scan_count < 5 THEN 1 ELSE queued END
    `).bind(tag, name, trophies).run();
  } catch(e) {}
}

// ─── CRAWL ────────────────────────────────────────────────────────────────────

async function runCrawl(env) {
  if (!env.CR_API_KEY) return;
  console.log("v2 crawl starting...");
  await env.DB.prepare("UPDATE crawl_state SET last_crawl=? WHERE id=1").bind(Date.now()).run();
  let totalBattles = 0;

  try {
    const { results: players } = await env.DB.prepare(`
      SELECT tag, trophies, scan_count, last_scanned FROM players
      WHERE queued=1 ORDER BY trophies DESC, last_scanned ASC LIMIT 50
    `).all();

    if (players.length < 10) { await seedAll(env); }

    for (let i = 0; i < Math.min(players.length, 50); i += 5) {
      const batch = players.slice(i, i + 5);
      const batchNewTags = new Set();

      await Promise.all(batch.map(async p => {
        try {
          const tag = p.tag.replace("#", "%23");
          const res = await fetch(`${CR_API}/players/${tag}/battlelog`, {
            headers: { "Authorization": `Bearer ${env.CR_API_KEY}` }
          });
          await env.DB.prepare("UPDATE players SET queued=0, last_scanned=?, scan_count=scan_count+1 WHERE tag=?")
            .bind(Date.now(), p.tag).run();
          if (!res.ok) return;
          const battles = await res.json();
          if (!Array.isArray(battles)) return;
          for (const battle of battles.slice(0, 25)) {
            const result = await processBattle(battle, env);
            if (result) {
              totalBattles++;
              if (result.opponentTag) batchNewTags.add(result.opponentTag);
              if (result.teamTag) batchNewTags.add(result.teamTag);
            }
          }
        } catch(e) { console.error("Player error:", p.tag, e.message); }
      }));

      // Enqueue unseen opponents
      for (const oppTag of batchNewTags) {
        const existing = await env.DB.prepare("SELECT tag, scan_count, queued FROM players WHERE tag=?").bind(oppTag).first();
        if (!existing) { await enqueuePlayer(env, oppTag, 0, ""); }
        else if (existing.scan_count < 3 && !existing.queued) {
          await env.DB.prepare("UPDATE players SET queued=1 WHERE tag=?").bind(oppTag).run();
        }
      }

      if (totalBattles > 0) {
        await env.DB.prepare("UPDATE crawl_state SET battles_processed=battles_processed+?, players_crawled=players_crawled+5 WHERE id=1")
          .bind(totalBattles).run();
        totalBattles = 0;
      }
      await sleep(500);
    }

    await runAggregator(env);
    console.log("v2 crawl complete");
  } catch(e) { console.error("Crawl error:", e.message); }
}

async function processBattle(battle, env) {
  try {
    const team = battle.team?.[0];
    const opponent = battle.opponent?.[0];
    if (!team || !opponent) return null;
    const teamCards = team.cards?.map(c => c.name).filter(Boolean);
    const oppCards = opponent.cards?.map(c => c.name).filter(Boolean);
    if (teamCards?.length !== 8 || oppCards?.length !== 8) return {
      opponentTag: opponent.tag||null, teamTag: null
    };
    const trophies = team.startingTrophies||0;
    if (trophies > 0 && trophies < MIN_TROPHIES) return {
      opponentTag: opponent.tag||null, teamTag: team.tag||null
    };
    const teamWon = (team.crowns||0) > (opponent.crowns||0);
    const battleId = `${team.tag||""}_${opponent.tag||""}_${battle.battleTime||Date.now()}`;
    const gameMode = battle.gameMode?.name || battle.type || "unknown";
    const battleTime = battle.battleTime || new Date().toISOString();

    await env.DB.prepare(`
      INSERT OR IGNORE INTO battles (battle_id, battle_time, player1_tag, player2_tag, winner_tag, game_mode, trophies)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).bind(battleId, battleTime, team.tag||"", opponent.tag||"", teamWon?(team.tag||""):(opponent.tag||""), gameMode, trophies).run();

    const sorted1 = [...teamCards].sort();
    const sorted2 = [...oppCards].sort();
    await storeDeck(env, battleId, team.tag||"", sorted1);
    await storeDeck(env, battleId, opponent.tag||"", sorted2);

    return { opponentTag: opponent.tag||null, teamTag: team.tag||null };
  } catch(e) { return null; }
}

async function storeDeck(env, battleId, playerTag, sorted) {
  try {
    await env.DB.prepare(`
      INSERT OR IGNORE INTO battle_decks
        (battle_id, player_tag, card1, card2, card3, card4, card5, card6, card7, card8)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(battleId, playerTag, ...sorted.slice(0,8)).run();
  } catch(e) {}
}

// ─── V2 AGGREGATOR ───────────────────────────────────────────────────────────
// Aggregates with temporal weighting:
// - recent_wins/losses (< 48h) stored separately
// - historical_wins/losses (< 7 days)
// Wilson score computed at query time from weighted totals

async function runAggregator(env) {
  console.log("v2 aggregator running...");
  try {
    const now = Date.now();
    const recentCutoff = new Date(now - RECENT_BATTLE_WINDOW_MS).toISOString().slice(0,19).replace('T','T');
    const historyCutoff = new Date(now - HISTORICAL_WINDOW_MS).toISOString().slice(0,19).replace('T','T');

    // Get all battles with decks and outcomes within 7 days
    const { results: rawBattles } = await env.DB.prepare(`
      SELECT
        b.battle_id,
        b.battle_time,
        b.winner_tag,
        b.trophies,
        d.player_tag,
        d.card1, d.card2, d.card3, d.card4,
        d.card5, d.card6, d.card7, d.card8
      FROM battles b
      JOIN battle_decks d ON b.battle_id = d.battle_id
      WHERE b.trophies >= ? AND b.battle_time >= ?
      ORDER BY b.battle_time DESC
      LIMIT 5000
    `).bind(MIN_TROPHIES, historyCutoff).all();

    if (!rawBattles.length) { console.log("No battles to aggregate"); return; }

    console.log(`v2 aggregating ${rawBattles.length} rows...`);

    // Group by battle
    const battleMap = {};
    for (const row of rawBattles) {
      if (!battleMap[row.battle_id]) {
        battleMap[row.battle_id] = {
          winner: row.winner_tag,
          trophies: row.trophies,
          battleTime: row.battle_time,
          isRecent: row.battle_time >= recentCutoff,
          decks: []
        };
      }
      const cards = [row.card1,row.card2,row.card3,row.card4,row.card5,row.card6,row.card7,row.card8].filter(Boolean);
      battleMap[row.battle_id].decks.push({ playerTag: row.player_tag, cards });
    }

    // Aggregate with temporal weighting
    const deckStats = {};    // hash -> { cards, wins, losses, recentWins, recentLosses, trophies[] }
    const pairStats = {};    // pair_key -> { wins, losses, recentWins, recentLosses }
    const cardStats = {};    // card_name -> { wins, losses, recentWins, recentLosses, usage }

    for (const [battleId, battle] of Object.entries(battleMap)) {
      if (battle.decks.length !== 2) continue;
      const isRecent = battle.isRecent;

      for (const deck of battle.decks) {
        const won = deck.playerTag === battle.winner;
        const sorted = [...deck.cards].sort();
        const hash = sorted.join("|");

        // Deck stats
        if (!deckStats[hash]) deckStats[hash] = { cards:sorted, wins:0, losses:0, recentWins:0, recentLosses:0, trophies:[] };
        if (won) { deckStats[hash].wins++; if(isRecent) deckStats[hash].recentWins++; }
        else { deckStats[hash].losses++; if(isRecent) deckStats[hash].recentLosses++; }
        deckStats[hash].trophies.push(battle.trophies);

        // Pair stats
        for (let i = 0; i < sorted.length; i++) {
          for (let j = i+1; j < sorted.length; j++) {
            const key = `${sorted[i]}|${sorted[j]}`;
            if (!pairStats[key]) pairStats[key] = { wins:0, losses:0, recentWins:0, recentLosses:0 };
            if (won) { pairStats[key].wins++; if(isRecent) pairStats[key].recentWins++; }
            else { pairStats[key].losses++; if(isRecent) pairStats[key].recentLosses++; }
          }
        }

        // Card stats
        for (const card of sorted) {
          if (!cardStats[card]) cardStats[card] = { wins:0, losses:0, recentWins:0, recentLosses:0, usage:0 };
          if (won) { cardStats[card].wins++; if(isRecent) cardStats[card].recentWins++; }
          else { cardStats[card].losses++; if(isRecent) cardStats[card].recentLosses++; }
          cardStats[card].usage++;
        }
      }
    }

    // Write deck_stats with temporal data
    // We'll store recent_wins/losses in existing wins/losses fields
    // and use a JSON blob for full temporal data
    for (const [hash, stat] of Object.entries(deckStats)) {
      const avgTrophies = Math.round(stat.trophies.reduce((a,b)=>a+b,0) / stat.trophies.length);
      const wilson = wilsonScore(stat.wins, stat.losses);
      const temporal = temporalScore(stat.recentWins, stat.recentLosses, stat.wins-stat.recentWins, stat.losses-stat.recentLosses);

      await env.DB.prepare(`
        INSERT INTO deck_stats (deck_hash, cards_json, wins, losses, avg_trophies, last_updated)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(deck_hash) DO UPDATE SET
          wins = excluded.wins,
          losses = excluded.losses,
          avg_trophies = excluded.avg_trophies,
          last_updated = excluded.last_updated
      `).bind(hash, JSON.stringify({ cards:stat.cards, wilson, temporal, recentWins:stat.recentWins, recentLosses:stat.recentLosses }), stat.wins, stat.losses, avgTrophies, Date.now()).run();
    }

    // Write pair_stats
    for (const [key, stat] of Object.entries(pairStats)) {
      await env.DB.prepare(`
        INSERT INTO pair_stats (pair_key, wins, losses)
        VALUES (?, ?, ?)
        ON CONFLICT(pair_key) DO UPDATE SET wins=excluded.wins, losses=excluded.losses
      `).bind(key, stat.wins, stat.losses).run();
    }

    // Write card_stats with velocity data encoded in usage_count JSON
    for (const [card, stat] of Object.entries(cardStats)) {
      const recentWR = stat.recentWins + stat.recentLosses > 0
        ? stat.recentWins / (stat.recentWins + stat.recentLosses) : 0;
      const historicalWR = stat.wins + stat.losses > 0
        ? stat.wins / (stat.wins + stat.losses) : 0;
      const velocity = calcMetaVelocity(recentWR, historicalWR);

      await env.DB.prepare(`
        INSERT INTO card_stats (card_name, wins, losses, usage_count)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(card_name) DO UPDATE SET wins=excluded.wins, losses=excluded.losses, usage_count=excluded.usage_count
      `).bind(card, stat.wins, stat.losses, stat.usage).run();
    }

    console.log(`v2 aggregator: ${Object.keys(deckStats).length} decks, ${Object.keys(pairStats).length} pairs, ${Object.keys(cardStats).length} cards`);
  } catch(e) { console.error("Aggregator error:", e.message); }
}

// ─── V2 RECOMMEND ─────────────────────────────────────────────────────────────
// Trophy-range filtered + Wilson score + temporal decay + card graph boost

async function handleRecommend(req, env) {
  try {
    const { player, cards } = await req.json();
    if (!cards?.length) return json({ error: "cards required" }, 400);

    const ownedNames = new Set(cards.map(c => c.name.toLowerCase()));
    const cardMap = {};
    cards.forEach(c => { cardMap[c.name.toLowerCase()] = c; });

    // V2: Trophy-range filtering
    const playerTrophies = player?.trophies || 0;
    const bracket = getTrophyBracket(playerTrophies);
    const trophyMin = bracket.min;
    const trophyMax = bracket.max;
    console.log(`Player ${playerTrophies} trophies -> bracket: ${bracket.name} (${trophyMin}-${trophyMax})`);

    // Get decks filtered by trophy bracket
    const { results: deckStats } = await env.DB.prepare(`
      SELECT * FROM deck_stats
      WHERE wins+losses >= 2
        AND avg_trophies >= ?
        AND avg_trophies <= ?
      ORDER BY avg_trophies DESC
      LIMIT 1000
    `).bind(trophyMin, trophyMax).all();

    // Fallback: if not enough bracket data, use global
    const useGlobal = deckStats.length < 10;
    const finalDeckStats = useGlobal
      ? (await env.DB.prepare("SELECT * FROM deck_stats WHERE wins+losses>=2 ORDER BY last_updated DESC LIMIT 1000").all()).results
      : deckStats;

    // Get pair stats for synergy scoring
    const { results: pairStats } = await env.DB.prepare(
      "SELECT pair_key, wins, losses FROM pair_stats WHERE wins+losses>=2 LIMIT 3000"
    ).all();
    const pairWinRates = {};
    pairStats.forEach(p => { pairWinRates[p.pair_key] = p.wins/(p.wins+p.losses); });

    // V2: Build card interaction graph
    const cardGraph = buildCardGraph(pairStats);

    // Score all playable decks
    const playable = [];
    for (const stat of finalDeckStats) {
      let parsed;
      try {
        parsed = JSON.parse(stat.cards_json);
      } catch { continue; }

      // Handle both v1 (array) and v2 (object with cards + wilson) formats
      const deckCards = Array.isArray(parsed) ? parsed : parsed.cards;
      const precomputedWilson = Array.isArray(parsed) ? null : parsed.wilson;
      const precomputedTemporal = Array.isArray(parsed) ? null : parsed.temporal;
      const recentWins = Array.isArray(parsed) ? 0 : (parsed.recentWins||0);
      const recentLosses = Array.isArray(parsed) ? 0 : (parsed.recentLosses||0);

      if (!deckCards || !deckCards.every(n => ownedNames.has(n.toLowerCase()))) continue;

      const playerCards = deckCards.map(n => cardMap[n.toLowerCase()]);
      const oldWins = stat.wins - recentWins;
      const oldLosses = stat.losses - recentLosses;

      // V2 scoring components
      const wilsonWR = precomputedWilson || wilsonScore(stat.wins, stat.losses);
      const temporalWR = precomputedTemporal || temporalScore(recentWins, recentLosses, oldWins, oldLosses);

      // Level score
      const levelScore = calcLevelScore(playerCards);

      // Pair synergy
      const synergyScore = calcPairSynergy(deckCards, pairWinRates);

      // EVO score
      const evoScore = playerCards.reduce((sum, c) => {
        if (!c || !c.evolutionLevel) return sum;
        const bonuses = {"Firecracker":30,"Mini P.E.K.K.A":28,"Knight":24,"Princess":22,"Musketeer":20,"Ice Spirit":18,"Bats":18,"Mega Minion":18,"Giant":16,"Ice Golem":15,"Valkyrie":14,"Royal Hogs":14};
        return sum + (bonuses[c.name]||10);
      }, 0);

      // V2: Card graph boost (PageRank anchor bonus)
      const graphBoost = deckCards.reduce((sum, name) => sum + (cardGraph[name] || 0), 0) / deckCards.length;
      const normalizedGraphBoost = Math.min(10, graphBoost * 5);

      // V2: Hero score
      const heroCard = playerCards.find(c => c?.rarity?.toLowerCase()==="champion");
      const heroScore = heroCard ? 8 : 0;

      // V2: Final composite score
      // wilson*0.35 + temporal*0.15 + level*0.20 + synergy*0.15 + evo*0.10 + graph*0.05
      const finalScore = Math.min(100, Math.round(
        wilsonWR  * 100 * 0.35 +
        temporalWR * 100 * 0.15 +
        levelScore * 0.20 +
        synergyScore * 0.15 +
        Math.min(100, evoScore * 2) * 0.10 +
        normalizedGraphBoost * 0.05 +
        heroScore * 0.05
      ));

      const meta = matchMetaDeck(deckCards);
      playable.push({
        cards: deckCards,
        deckCards: playerCards,
        wins: stat.wins,
        losses: stat.losses,
        recentWins,
        recentLosses,
        winRate: Math.round((stat.wins/(stat.wins+stat.losses))*100),
        wilsonScore: Math.round(wilsonWR*100),
        temporalScore: Math.round(temporalWR*100),
        avgTrophies: stat.avg_trophies,
        powerRating: finalScore,
        battles: stat.wins+stat.losses,
        confidence: Math.min(100, Math.round(Math.log10(stat.wins+stat.losses+1)*33)),
        bracket: bracket.name,
        usingGlobal: useGlobal,
        name: meta.name,
        archetype: meta.archetype,
        tier: meta.tier,
      });
    }

    const top3 = playable.sort((a,b) => b.powerRating-a.powerRating).slice(0,3);
    const state = await env.DB.prepare("SELECT * FROM crawl_state WHERE id=1").first();
    const battleCount = await env.DB.prepare("SELECT COUNT(*) as count FROM battles").first();
    const queueCount = await env.DB.prepare("SELECT COUNT(*) as count FROM players WHERE queued=1").first();

    return json({
      decks: top3,
      meta: {
        totalDecks: finalDeckStats.length,
        battles: battleCount?.count||0,
        lastCrawl: state?.last_crawl||0,
        hasData: finalDeckStats.length>0,
        queueSize: queueCount?.count||0,
        bracket: bracket.name,
        usingGlobal: useGlobal,
        engine: "v2",
      }
    });
  } catch(e) { return json({ error: e.message }, 500); }
}

// ─── V2: META VELOCITY ENDPOINT ───────────────────────────────────────────────

async function handleMetaVelocity(req, env) {
  try {
    const now = Date.now();
    const recentCutoff = new Date(now - RECENT_BATTLE_WINDOW_MS).toISOString().slice(0,19);
    const historyCutoff = new Date(now - HISTORICAL_WINDOW_MS).toISOString().slice(0,19);

    // Get recent card performance
    const { results: recentBattles } = await env.DB.prepare(`
      SELECT d.card1, d.card2, d.card3, d.card4, d.card5, d.card6, d.card7, d.card8,
             b.winner_tag, d.player_tag
      FROM battles b JOIN battle_decks d ON b.battle_id = d.battle_id
      WHERE b.battle_time >= ? AND b.trophies >= ?
      LIMIT 2000
    `).bind(recentCutoff, MIN_TROPHIES).all();

    const { results: historicalBattles } = await env.DB.prepare(`
      SELECT d.card1, d.card2, d.card3, d.card4, d.card5, d.card6, d.card7, d.card8,
             b.winner_tag, d.player_tag
      FROM battles b JOIN battle_decks d ON b.battle_id = d.battle_id
      WHERE b.battle_time >= ? AND b.battle_time < ? AND b.trophies >= ?
      LIMIT 5000
    `).bind(historyCutoff, recentCutoff, MIN_TROPHIES).all();

    const calcCardWRs = (rows) => {
      const stats = {};
      for (const row of rows) {
        const cards = [row.card1,row.card2,row.card3,row.card4,row.card5,row.card6,row.card7,row.card8].filter(Boolean);
        const won = row.player_tag === row.winner_tag;
        for (const card of cards) {
          if (!stats[card]) stats[card] = { wins:0, losses:0 };
          if (won) stats[card].wins++; else stats[card].losses++;
        }
      }
      const wrs = {};
      for (const [card, s] of Object.entries(stats)) {
        if (s.wins + s.losses >= 5) wrs[card] = s.wins / (s.wins + s.losses);
      }
      return wrs;
    };

    const recentWRs = calcCardWRs(recentBattles);
    const historicalWRs = calcCardWRs(historicalBattles);

    const velocity = [];
    for (const card of Object.keys(recentWRs)) {
      if (!historicalWRs[card]) continue;
      const v = calcMetaVelocity(recentWRs[card], historicalWRs[card]);
      velocity.push({
        card,
        recentWR: Math.round(recentWRs[card]*100),
        historicalWR: Math.round(historicalWRs[card]*100),
        velocity: Math.round(v*100),
        trend: v > 0.05 ? "rising" : v < -0.05 ? "falling" : "stable",
      });
    }

    velocity.sort((a,b) => Math.abs(b.velocity) - Math.abs(a.velocity));
    return json({ velocity: velocity.slice(0, 20), engine: "v2" });
  } catch(e) { return json({ error: e.message }, 500); }
}

// ─── V2: CARD GRAPH ENDPOINT ──────────────────────────────────────────────────

async function handleCardGraph(req, env) {
  try {
    const { results: pairStats } = await env.DB.prepare(
      "SELECT pair_key, wins, losses FROM pair_stats WHERE wins+losses >= 5 LIMIT 2000"
    ).all();
    const graph = buildCardGraph(pairStats);
    const sorted = Object.entries(graph)
      .sort((a,b) => b[1]-a[1])
      .slice(0, 30)
      .map(([card, score]) => ({ card, score: Math.round(score*100)/100 }));
    return json({ anchors: sorted, engine: "v2" });
  } catch(e) { return json({ error: e.message }, 500); }
}

// ─── AI CHAT ──────────────────────────────────────────────────────────────────
// Proxy for all frontend AI calls — keeps GROQ_API_KEY server-side

async function handleAIChat(req, env) {
  try {
    const { messages, system, max_tokens } = await req.json();
    if (!messages?.length) return json({ error: "messages required" }, 400);

    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${env.GROQ_API_KEY}` },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",
        max_tokens: max_tokens || 3000,
        messages: system ? [{ role: "system", content: system }, ...messages] : messages,
      }),
    });
    if (!res.ok) throw new Error(`Groq ${res.status}: ${await res.text()}`);
    const data = await res.json();
    const content = data.choices?.[0]?.message?.content;
    if (!content) throw new Error("Empty response from Groq");
    return json({ content });
  } catch(e) { return json({ error: e.message }, 500); }
}

// ─── AI RECOMMEND ─────────────────────────────────────────────────────────────

async function handleAIRecommend(req, env) {
  try {
    const { player, cards } = await req.json();
    if (!cards?.length) return json({ error: "cards required" }, 400);

    const playerTrophies = player?.trophies || 0;
    const bracket = getTrophyBracket(playerTrophies);

    const { results: pairStats } = await env.DB.prepare(
      "SELECT pair_key, wins, losses FROM pair_stats WHERE wins+losses>=3 ORDER BY CAST(wins AS FLOAT)/(wins+losses) DESC LIMIT 300"
    ).all();
    const { results: cardStats } = await env.DB.prepare(
      "SELECT card_name, wins, losses, usage_count FROM card_stats WHERE wins+losses>=5 ORDER BY CAST(wins AS FLOAT)/(wins+losses) DESC LIMIT 50"
    ).all();
    const { results: topDecks } = await env.DB.prepare(
      "SELECT cards_json, wins, losses, avg_trophies FROM deck_stats WHERE wins+losses>=3 AND avg_trophies>=? ORDER BY CAST(wins AS FLOAT)/(wins+losses) DESC LIMIT 15"
    ).bind(bracket.min).all();

    const battleCount = await env.DB.prepare("SELECT COUNT(*) as count FROM battles").first();
    const cardGraph = buildCardGraph(pairStats);

    const topAnchors = Object.entries(cardGraph)
      .sort((a,b)=>b[1]-a[1])
      .slice(0,10)
      .map(([c,s])=>`${c}(${Math.round(s*10)/10})`);

    const topPairs = pairStats.slice(0,80).map(p => {
      const wr = Math.round(p.wins/(p.wins+p.losses)*100);
      const wilson = Math.round(wilsonScore(p.wins,p.losses)*100);
      return `${p.pair_key}: ${wr}% raw, ${wilson}% wilson (${p.wins+p.losses} battles)`;
    }).join("\n");

    const topDeckContext = topDecks.slice(0,10).map(d => {
      try {
        const parsed = JSON.parse(d.cards_json);
        const dc = Array.isArray(parsed) ? parsed : parsed.cards;
        const wr = Math.round(d.wins/(d.wins+d.losses)*100);
        const wilson = Math.round(wilsonScore(d.wins,d.losses)*100);
        return `[${dc.join(", ")}] ${wr}% WR (${wilson}% wilson, ${d.wins+d.losses} battles, avg ${d.avg_trophies} trophies)`;
      } catch { return null; }
    }).filter(Boolean).join("\n");

    const ownedCards = cards.map(c => ({
      name:c.name, level:c.level, maxLevel:c.maxLevel,
      maxed:(c.maxLevel-c.level)<=1, evo:c.evolutionLevel>0?c.evolutionLevel:null,
      rarity:c.rarity, elixir:c.elixirCost, type:c.type,
      isChampion:c.rarity?.toLowerCase()==="champion",
    }));
    const champions = ownedCards.filter(c=>c.isChampion);
    const evos = ownedCards.filter(c=>c.evo);

    const prompt = `You are an expert Clash Royale deck builder AI using v2 statistical engine with Wilson score confidence intervals and temporal decay weighting.

PLAYER:
- Name: ${player?.name}, Trophies: ${playerTrophies}, Trophy Bracket: ${bracket.name} (${bracket.min}-${bracket.max})
- King Level: ${player?.expLevel}, Arena: ${player?.arena?.name}

OWNED CARDS (${ownedCards.length} total):
${ownedCards.map(c=>`${c.name} L${c.level}/${c.maxLevel}${c.evo?` EVO${c.evo}`:""}${c.maxed?" MAXED":""}${c.isChampion?" HERO":""} (${c.elixir}e)`).join("\n")}

HERO CARDS: ${champions.map(c=>`${c.name} L${c.level}`).join(", ")||"None"}
EVO CARDS: ${evos.map(c=>`${c.name} EVO${c.evo}`).join(", ")||"None"}

LIVE BATTLE DATA (${battleCount?.count||0} real battles, ${bracket.name} bracket):
Top card pair win rates (Wilson score confidence):
${topPairs}

Top anchor cards by interaction graph PageRank:
${topAnchors.join(", ")}

Top performing decks in ${bracket.name} bracket:
${topDeckContext}

KEY RULES:
1. Only use cards the player owns
2. Exactly 8 cards per deck
3. Max 1 hero card per deck
4. Prioritize owned EVO cards when they fit
5. Prefer maxed/near-maxed cards
6. Use pair win rates as synergy ground truth
7. High PageRank anchor cards = core of strong decks

Return ONLY this JSON array, no markdown:
[{
  "name":"Deck name","archetype":"Archetype","tier":"S/A+/A/B+",
  "cards":["Card1"..."Card8"],"hero":"HeroName or null",
  "evosUsed":["EVO cards"],"winCondition":"2 sentences",
  "whyThisDeck":"Why optimal for this player specifically",
  "attack":"2 sentences","defense":"2 sentences",
  "counters":["c1","c2","c3"],"synergyHighlights":["s1","s2"],
  "upgradePriority":[{"card":"Name","reason":"why","impact":"high/medium"}],
  "powerRating":85
}]`;

    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method:"POST",
      headers:{"Content-Type":"application/json","Authorization":`Bearer ${env.GROQ_API_KEY}`},
      body:JSON.stringify({
        model:"llama-3.3-70b-versatile", max_tokens:4000, temperature:0.3,
        messages:[
          {role:"system",content:"You are an expert Clash Royale AI coach. Return only valid JSON arrays."},
          {role:"user",content:prompt}
        ]
      })
    });

    if (!res.ok) throw new Error(`Groq ${res.status}`);
    const data = await res.json();
    const text = data.choices?.[0]?.message?.content||"";
    const clean = text.replace(/```json|```/g,"").trim();
    const match = clean.match(/\[[\s\S]*\]/);
    if (!match) throw new Error("Could not parse AI response");
    const aiDecks = JSON.parse(match[0]);
    const ownedSet = new Set(cards.map(c=>c.name.toLowerCase()));
    const validated = aiDecks
      .map(d=>({...d, cards:d.cards.filter(c=>ownedSet.has(c.toLowerCase())), hero:d.hero&&ownedSet.has(d.hero.toLowerCase())?d.hero:null}))
      .filter(d=>d.cards.length>=7);

    return json({ decks:validated, source:"ai", bracket:bracket.name, totalBattles:battleCount?.count||0, engine:"v2" });
  } catch(e) { return json({ error:e.message }, 500); }
}

// ─── META NEWS ────────────────────────────────────────────────────────────────

async function handleMetaNews(req, env) {
  try {
    const { results: cardStats } = await env.DB.prepare(
      "SELECT card_name, wins, losses, usage_count FROM card_stats WHERE wins+losses>=5 ORDER BY CAST(wins AS FLOAT)/(wins+losses) DESC"
    ).all();

    const topCards = cardStats.slice(0,10).map(c=>`${c.card_name}: ${Math.round(c.wins/(c.wins+c.losses)*100)}% WR`).join(", ");
    const bottomCards = cardStats.slice(-10).map(c=>`${c.card_name}: ${Math.round(c.wins/(c.wins+c.losses)*100)}% WR`).join(", ");

    const velocityRes = await handleMetaVelocity(req, env);
    const velocityData = await velocityRes.json();
    const risingCards = (velocityData.velocity||[]).filter(v=>v.trend==="rising").slice(0,3).map(v=>`${v.card} +${v.velocity}%`).join(", ");
    const fallingCards = (velocityData.velocity||[]).filter(v=>v.trend==="falling").slice(0,3).map(v=>`${v.card} ${v.velocity}%`).join(", ");

    const prompt = `You are a Clash Royale meta analyst in 2026. Analyze this live data:

STRONGEST CARDS: ${topCards}
WEAKEST CARDS: ${bottomCards}
RISING (last 48h): ${risingCards||"None detected yet"}
FALLING (last 48h): ${fallingCards||"None detected yet"}

Return ONLY this JSON, no markdown:
{
  "lastUpdated":"June 2026",
  "metaSummary":"2-3 sentence current meta overview",
  "alerts":[{"type":"buff/nerf/rising/falling","card":"Name","impact":"high/medium/low","message":"1 sentence","emoji":"🔴/🟢/📈/📉"}],
  "topArchetypes":[{"name":"Archetype","tier":"S/A+/A","trend":"rising/stable/falling","reason":"1 sentence"}],
  "tip":"One actionable meta tip"
}`;

    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method:"POST",
      headers:{"Content-Type":"application/json","Authorization":`Bearer ${env.GROQ_API_KEY}`},
      body:JSON.stringify({model:"llama-3.3-70b-versatile",max_tokens:800,temperature:0.2,
        messages:[{role:"system",content:"Clash Royale meta analyst. Return only valid JSON."},
                  {role:"user",content:prompt}]})
    });
    if (!res.ok) throw new Error(`Groq ${res.status}`);
    const data = await res.json();
    const text = data.choices?.[0]?.message?.content||"";
    const clean = text.replace(/```json|```/g,"").trim();
    const match = clean.match(/\{[\s\S]*\}/);
    if (!match) throw new Error("Could not parse meta news");
    return json({...JSON.parse(match[0]), engine:"v2"});
  } catch(e) { return json({ error:e.message }, 500); }
}

// ─── STATUS ───────────────────────────────────────────────────────────────────

async function handleStatus(req, env) {
  try {
    const state = await env.DB.prepare("SELECT * FROM crawl_state WHERE id=1").first();
    const d = await env.DB.prepare("SELECT COUNT(*) as count FROM deck_stats").first();
    const c = await env.DB.prepare("SELECT COUNT(*) as count FROM card_stats").first();
    const p = await env.DB.prepare("SELECT COUNT(*) as count FROM players").first();
    const b = await env.DB.prepare("SELECT COUNT(*) as count FROM battles").first();
    const q = await env.DB.prepare("SELECT COUNT(*) as count FROM players WHERE queued=1").first();
    return json({
      lastCrawl: state?.last_crawl ? new Date(state.last_crawl).toISOString() : "Never",
      battles: b?.count||0,
      uniqueDecks: d?.count||0,
      uniqueCards: c?.count||0,
      totalPlayers: p?.count||0,
      queueSize: q?.count||0,
      engine: "v2",
    });
  } catch(e) { return json({ error:e.message }, 500); }
}

// ─── DECK STATS ───────────────────────────────────────────────────────────────

async function handleDeckStats(req, env) {
  try {
    const url = new URL(req.url);
    const cards = url.searchParams.get("cards")?.split(",") || [];
    if (cards.length !== 8) return json({ error:"Need 8 cards" }, 400);
    const hash = [...cards].sort().join("|");
    const stat = await env.DB.prepare("SELECT * FROM deck_stats WHERE deck_hash=?").bind(hash).first();
    if (!stat) return json({ found:false });
    let parsed;
    try { parsed = JSON.parse(stat.cards_json); } catch { parsed = {}; }
    const wilson = Array.isArray(parsed) ? wilsonScore(stat.wins,stat.losses) : (parsed.wilson||0);
    return json({
      found:true,
      winRate: Math.round((stat.wins/(stat.wins+stat.losses))*100),
      wilsonScore: Math.round(wilson*100),
      wins:stat.wins, losses:stat.losses,
      battles:stat.wins+stat.losses,
      avgTrophies:stat.avg_trophies,
      confidence: Math.min(100, Math.round(Math.log10(stat.wins+stat.losses+1)*33)),
      engine:"v2",
    });
  } catch(e) { return json({ error:e.message }, 500); }
}

// ─── HELPERS ──────────────────────────────────────────────────────────────────

function calcLevelScore(cards) {
  if (!cards?.length) return 0;
  return cards.reduce((sum,card) => {
    if (!card) return sum;
    const diff = (card.maxLevel||14)-(card.level||1);
    return sum + (diff<=1?10:diff<=3?6:1);
  },0);
}

function calcPairSynergy(cards, pairWinRates) {
  let score=0, pairs=0;
  for (let i=0;i<cards.length;i++) {
    for (let j=i+1;j<cards.length;j++) {
      const key=[cards[i],cards[j]].sort().join("|");
      if (pairWinRates[key]) { score+=pairWinRates[key]*100; pairs++; }
    }
  }
  return pairs>0?score/pairs:50;
}

function sleep(ms) { return new Promise(r=>setTimeout(r,ms)); }

function json(data, status=200) {
  return new Response(JSON.stringify(data), { status, headers:CORS_HEADERS });
}
