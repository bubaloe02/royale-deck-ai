import React, { useState, useRef, useEffect } from "react";

const WORKER_URL = "https://small-king-a65c.jared1999.workers.dev";

// ─── ALL GROQ CALLS GO THROUGH WORKER — NO API KEY IN FRONTEND ───────────────
async function callAI(system, userPrompt, history, max_tokens) {
  const msgs = history
    ? history.map(m => ({ role: m.role, content: m.content }))
    : [{ role: "user", content: userPrompt }];
  const res = await fetch(`${WORKER_URL}/ai/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: msgs, system, max_tokens: max_tokens || 3000 })
  });
  if (!res.ok) throw new Error(`Chat ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data.content;
}

async function crFetch(tag) {
  const res = await fetch(`${WORKER_URL}/v1/players/%23${tag}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

async function crFetchBattles(tag) {
  try {
    const res = await fetch(`${WORKER_URL}/v1/players/%23${tag}/battlelog`);
    if (!res.ok) return [];
    return await res.json();
  } catch(e) { return []; }
}

function analyzeBattleHistory(battles) {
  const archetypeStats = {};
  if (!Array.isArray(battles)) return archetypeStats;
  battles.forEach(battle => {
    if (battle.type !== "PvP") return;
    const team = battle.team?.[0];
    if (!team?.cards) return;
    const cardNames = team.cards.map(c => c.name);
    const archetype = guessArchetype(cardNames);
    const won = (team.crowns || 0) > (battle.opponent?.[0]?.crowns || 0);
    if (!archetypeStats[archetype]) archetypeStats[archetype] = { wins: 0, losses: 0 };
    if (won) archetypeStats[archetype].wins++; else archetypeStats[archetype].losses++;
  });
  return archetypeStats;
}

function guessArchetype(cardNames) {
  const names = cardNames.map(n => n.toLowerCase());
  if (names.includes("hog rider")) return "Hog Cycle";
  if (names.includes("lava hound")) return "LavaLoon";
  if (names.includes("golem")) return "Golem Beatdown";
  if (names.includes("goblin barrel")) return "Log Bait";
  if (names.includes("x-bow")) return "X-Bow Siege";
  if (names.includes("mortar")) return "Mortar Siege";
  if (names.includes("miner")) return "Miner Cycle";
  if (names.includes("graveyard")) return "Graveyard Control";
  if (names.includes("p.e.k.k.a")) return "Pekka Bridge Spam";
  if (names.includes("giant")) return "Giant Beatdown";
  if (names.includes("balloon")) return "Balloon Cycle";
  return "Mixed";
}

const META_DECKS = [
  { name:"Hog EQ Cycle", archetype:"Hog Cycle", tier:"S", metaScore:100, cards:["Hog Rider","Earthquake","Firecracker","Skeletons","Ice Spirit","Cannon","The Log","Knight"] },
  { name:"Hog FC Cycle", archetype:"Hog Cycle", tier:"S", metaScore:98, cards:["Hog Rider","Firecracker","Skeletons","Ice Spirit","Cannon","The Log","Musketeer","Knight"] },
  { name:"Pekka Bridge Spam", archetype:"Pekka Bridge Spam", tier:"S", metaScore:96, cards:["P.E.K.K.A","Bandit","Royal Ghost","Battle Ram","Poison","Zap","Magic Archer","Electro Wizard"] },
  { name:"LavaLoon", archetype:"LavaLoon", tier:"S", metaScore:94, cards:["Lava Hound","Balloon","Tombstone","Mega Minion","Lumberjack","Zap","Lightning","Minions"] },
  { name:"Log Bait", archetype:"Log Bait", tier:"S", metaScore:93, cards:["Goblin Barrel","Princess","Goblin Gang","Rocket","Inferno Tower","Knight","The Log","Barbarian Barrel"] },
  { name:"Miner Poison", archetype:"Miner Cycle", tier:"A+", metaScore:90, cards:["Miner","Poison","Wall Breakers","Bats","Goblin Gang","Zap","Musketeer","Ice Golem"] },
  { name:"Golem Beatdown", archetype:"Golem Beatdown", tier:"A+", metaScore:87, cards:["Golem","Night Witch","Baby Dragon","Lightning","Tornado","Zap","Tombstone","Mega Minion"] },
  { name:"Graveyard Poison", archetype:"Graveyard Control", tier:"A+", metaScore:86, cards:["Graveyard","Poison","Ice Golem","Tombstone","Minions","Archers","Barbarian Barrel","Knight"] },
  { name:"X-Bow Cycle", archetype:"X-Bow Siege", tier:"A+", metaScore:85, cards:["X-Bow","Tesla","Ice Spirit","Skeletons","The Log","Archers","Ice Golem","Earthquake"] },
  { name:"Hog AQ Cycle", archetype:"Hog Cycle", tier:"A", metaScore:78, cards:["Hog Rider","Archers","Ice Golem","Skeletons","Cannon","Fireball","The Log","Ice Spirit"] },
  { name:"Hog Cycle Classic", archetype:"Hog Cycle", tier:"B+", metaScore:66, cards:["Hog Rider","Musketeer","Cannon","Ice Golem","Fireball","The Log","Skeletons","Ice Spirit"] },
];

const HERO_SYNERGIES = {
  "Golden Knight":  { archetypes:["Hog Cycle","Pekka Bridge Spam"], note:"Dash pairs with Hog/Ram for double pressure" },
  "Archer Queen":   { archetypes:["LavaLoon","Balloon Cycle"],      note:"Invisible ability protects air pushes" },
  "Skeleton King":  { archetypes:["Graveyard Control","Log Bait"],   note:"Army ability floods with skeletons" },
  "Mighty Miner":   { archetypes:["Miner Cycle","Hog Cycle"],        note:"Secondary win condition for cycle" },
  "Little Prince":  { archetypes:["Pekka Bridge Spam"],              note:"Guard ability sustains bridge spam" },
  "Monk":           { archetypes:["Golem Beatdown","Giant Beatdown"], note:"Deflect ability anchors beatdown defense" },
  "Boss Bandit":    { archetypes:["X-Bow Siege","Graveyard Control"],note:"Lasso ability controls siege lane" },
  "Goblinstein":    { archetypes:["Golem Beatdown","Giant Beatdown"], note:"Lightning ability powers up beatdown" },
};

const CHAMPION_NAMES = ["Golden Knight","Archer Queen","Skeleton King","Mighty Miner","Little Prince","Monk","Boss Bandit","Goblinstein"];
const isChampionCard = (card) => card?.rarity?.toLowerCase()==="champion" || CHAMPION_NAMES.includes(card?.name);

const EVO_TIERS = {
  "Firecracker":   { tier:"S+", bonus:30, note:"Splits on death — game changing" },
  "Mini P.E.K.K.A":{ tier:"S+", bonus:28, note:"Double strike — strongest troop EVO" },
  "Knight":        { tier:"S",  bonus:24, note:"Shield + rage aura — best defensive EVO" },
  "Princess":      { tier:"S",  bonus:22, note:"Area damage — strongest ranged EVO" },
  "Musketeer":     { tier:"A+", bonus:20, note:"Bouncing shots — multi-target" },
  "Ice Spirit":    { tier:"A+", bonus:18, note:"Freezes multiple targets" },
  "Bats":          { tier:"A+", bonus:18, note:"Split on death — swarm" },
  "Mega Minion":   { tier:"A+", bonus:18, note:"Enrages — burst damage" },
  "Giant":         { tier:"A",  bonus:16, note:"Extra HP — tankier push" },
  "Ice Golem":     { tier:"A",  bonus:15, note:"Bigger freeze radius" },
  "Valkyrie":      { tier:"A",  bonus:14, note:"Spin ability — area clear" },
  "Royal Hogs":    { tier:"A",  bonus:14, note:"Shield charge" },
  "Goblin Cage":   { tier:"A",  bonus:13, note:"Goblin Brawler on death" },
  "Barbarians":    { tier:"B+", bonus:12, note:"Rage on spawn" },
  "Minion Horde":  { tier:"B+", bonus:12, note:"Extra minions" },
  "Furnace":       { tier:"B+", bonus:11, note:"Fire Spirit spam" },
  "Royal Giant":   { tier:"B+", bonus:11, note:"Shield charge" },
  "Witch":         { tier:"B+", bonus:11, note:"Skeleton flood" },
  "P.E.K.K.A":    { tier:"B+", bonus:10, note:"Lightning on swing" },
  "Dart Goblin":   { tier:"B",  bonus:9,  note:"Faster attack speed" },
  "Hunter":        { tier:"B",  bonus:9,  note:"Shotgun spread" },
  "Electro Dragon":{ tier:"B",  bonus:9,  note:"Chain lightning" },
  "Baby Dragon":   { tier:"B",  bonus:8,  note:"Larger area" },
};

const SYNERGIES = {
  "Hog Rider":     { "Earthquake":10,"Ice Spirit":6,"Skeletons":6,"Cannon":5,"Firecracker":8,"The Log":5,"Golden Knight":9,"Mighty Miner":7 },
  "Lava Hound":    { "Balloon":15,"Tombstone":6,"Mega Minion":5,"Lumberjack":8,"Lightning":6,"Archer Queen":10 },
  "P.E.K.K.A":    { "Bandit":8,"Battle Ram":7,"Magic Archer":6,"Electro Wizard":5,"Little Prince":8 },
  "Golem":         { "Night Witch":10,"Baby Dragon":8,"Lightning":7,"Mega Minion":6,"Monk":8,"Goblinstein":9 },
  "Graveyard":     { "Poison":12,"Ice Golem":8,"Tombstone":6,"Skeleton King":10 },
  "Goblin Barrel": { "Princess":8,"Goblin Gang":8,"Rocket":7,"The Log":6 },
  "X-Bow":         { "Tesla":8,"Ice Spirit":6,"Skeletons":5,"The Log":5,"Boss Bandit":7 },
  "Balloon":       { "Lava Hound":15,"Freeze":10,"Minions":5,"Archer Queen":9 },
  "Miner":         { "Poison":10,"Wall Breakers":10,"Bats":4,"Goblin Gang":5,"Little Prince":7,"Mighty Miner":8 },
};

function scoreCard(card) {
  const diff = (card.maxLevel||14)-(card.level||1);
  let s = diff<=1?10:diff<=3?6:1;
  if (card.evolutionLevel>0) { const e=EVO_TIERS[card.name]; s+=e?e.bonus:15; }
  if (isChampionCard(card)) s+=8;
  if (card.iconUrls?.heroMedium) s+=15;
  return s;
}

function scoreDeckLocal(cards) {
  const level = cards.reduce((sum,c)=>{ const d=(c.maxLevel||14)-(c.level||1); return sum+(d<=1?10:d<=3?6:1); },0);
  const evo = cards.reduce((sum,c)=>{ if(c.evolutionLevel>0){const e=EVO_TIERS[c.name];return sum+(e?e.bonus:15);}return sum; },0);
  const hero = cards.reduce((sum,c)=>{const b=isChampionCard(c)?8:0;return sum+b+(c.iconUrls?.heroMedium?15:0);},0);
  let synergy=0;
  cards.forEach(c=>{ const l=SYNERGIES[c.name]; if(!l) return; cards.forEach(o=>{if(l[o.name])synergy+=l[o.name];}); });
  synergy=Math.min(synergy,60);
  const names=cards.map(c=>c.name);
  let coverage=0;
  if(names.some(n=>["Musketeer","Archers","Firecracker","Mega Minion","Baby Dragon","Minions","Bats","Electro Dragon"].includes(n))) coverage+=15; else coverage-=50;
  if(names.some(n=>["The Log","Zap","Barbarian Barrel","Ice Spirit"].includes(n))) coverage+=15; else coverage-=20;
  if(names.some(n=>["Fireball","Poison","Rocket","Lightning","Earthquake"].includes(n))) coverage+=15;
  if(cards.some(c=>c.type?.toLowerCase()==="building")) coverage+=10;
  return Math.max(0,Math.min(100,Math.round(level*0.30+evo*0.15+hero*0.05+synergy*0.25+coverage*0.15)));
}

function getTier(score) {
  if(score>=95) return "S+"; if(score>=88) return "S"; if(score>=80) return "A+";
  if(score>=70) return "A"; if(score>=60) return "B+"; return "B";
}
function getTierColor(tier) {
  return {"S+":"#ffd700","S":"#ff9800","A+":"#4caf50","A":"#2196f3","B+":"#9c27b0","B":"#607d8b"}[tier]||"#888";
}

function buildLocalCandidates(playerCards, battleStats) {
  const owned=new Set(playerCards.map(c=>c.name.toLowerCase()));
  const cardMap={};
  playerCards.forEach(c=>{cardMap[c.name.toLowerCase()]=c;});
  const candidates=[];
  META_DECKS.forEach(meta=>{
    const missing=meta.cards.filter(n=>!owned.has(n.toLowerCase()));
    if(missing.length===0){
      const dc=meta.cards.map(n=>cardMap[n.toLowerCase()]);
      const pr=scoreDeckLocal(dc);
      const personalWR=battleStats[meta.archetype];
      let boost=0;
      if(personalWR&&(personalWR.wins+personalWR.losses)>=3){
        const wr=personalWR.wins/(personalWR.wins+personalWR.losses);
        boost=Math.round((wr-0.5)*20);
      }
      candidates.push({...meta,deckCards:dc,powerRating:Math.min(100,Math.round(pr*0.6+meta.metaScore*0.4)+boost),
        winRate:null,battles:null,matchType:"local",
        personalWR:personalWR?Math.round(personalWR.wins/(personalWR.wins+personalWR.losses)*100):null,
        personalBattles:personalWR?personalWR.wins+personalWR.losses:null});
    } else if(missing.length===1){
      const deckNames=new Set(meta.cards.map(n=>n.toLowerCase()));
      const sub=playerCards.filter(c=>!deckNames.has(c.name.toLowerCase())).sort((a,b)=>scoreCard(b)-scoreCard(a))[0];
      if(sub){
        const newCards=meta.cards.map(n=>owned.has(n.toLowerCase())?n:sub.name);
        const dc=newCards.map(n=>cardMap[n.toLowerCase()]);
        const pr=scoreDeckLocal(dc);
        candidates.push({...meta,name:meta.name+" (Adapted)",cards:newCards,deckCards:dc,
          powerRating:Math.round(pr*0.6+(meta.metaScore*0.7)*0.4),
          winRate:null,battles:null,matchType:"partial",
          substituted:{original:missing[0],replacement:sub.name}});
      }
    }
  });
  if(candidates.length<3){
    const top8=[...playerCards].sort((a,b)=>scoreCard(b)-scoreCard(a)).slice(0,8);
    const pr=scoreDeckLocal(top8);
    candidates.push({name:"Best Available",archetype:"Mixed",tier:getTier(pr),metaScore:50,
      cards:top8.map(c=>c.name),deckCards:top8,powerRating:pr,winRate:null,battles:null,matchType:"generated"});
  }
  const seen=new Set();
  return candidates.filter(c=>{const k=c.cards.join(",");if(seen.has(k))return false;seen.add(k);return true;})
    .sort((a,b)=>b.powerRating-a.powerRating).slice(0,20);
}

async function fetchDecks(playerData, cards, battleStats) {
  const currentDeckCards=playerData.currentDeck||[];
  let currentDeckOption=null;
  if(currentDeckCards.length===8){
    const cardMap={};
    cards.forEach(c=>{cardMap[c.name.toLowerCase()]=c;});
    const activeEvoNames=new Set(currentDeckCards.filter(c=>(c.evolutionLevel||0)>0||c.iconUrls?.evolutionMedium).map(c=>c.name.toLowerCase()));
    const dc=currentDeckCards.map(c=>{
      const base=cardMap[c.name.toLowerCase()]||c;
      return {...base,evolutionLevel:activeEvoNames.has(c.name.toLowerCase())?(c.evolutionLevel||1):0};
    });
    const pr=scoreDeckLocal(dc);
    const archetype=guessArchetype(currentDeckCards.map(c=>c.name));
    const personalWR=battleStats[archetype];
    const evosInDeck=dc.filter(c=>c.evolutionLevel>0);
    const heroInDeck=dc.find(c=>isChampionCard(c));
    currentDeckOption={
      name:"Your Current Deck",archetype,tier:getTier(pr),metaScore:95,
      cards:currentDeckCards.map(c=>c.name),deckCards:dc,
      powerRating:Math.min(100,pr+5),winRate:null,battles:null,
      matchType:"current",isCurrentDeck:true,
      evosUsed:evosInDeck.map(c=>c.name),
      hero:heroInDeck?.name||null,
      personalWR:personalWR?Math.round(personalWR.wins/(personalWR.wins+personalWR.losses)*100):null,
      personalBattles:personalWR?personalWR.wins+personalWR.losses:null,
    };
  }
  try {
    const res=await fetch(`${WORKER_URL}/recommend`,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({player:playerData,cards})
    });
    if(res.ok){
      const data=await res.json();
      if(data.decks?.length>0&&data.meta?.hasData){
        let liveDecks=data.decks.map((d,i)=>({...d,
          name:d.name||`Meta Deck #${i+1}`,
          archetype:d.archetype||"Unknown",
          tier:getTier(d.powerRating),
          source:"live",
          bracket:data.meta?.bracket,
          usingGlobal:data.meta?.usingGlobal,
        }));
        if(currentDeckOption) liveDecks=[currentDeckOption,...liveDecks.slice(0,2)];
        return {decks:liveDecks,source:"live",meta:data.meta};
      }
    }
  } catch(e){}
  const candidates=buildLocalCandidates(cards,battleStats);
  let decks=candidates.slice(0,3);
  if(currentDeckOption){
    const already=decks.some(d=>d.cards.join()===currentDeckOption.cards.join());
    if(!already) decks=[currentDeckOption,...decks.slice(0,2)];
  }
  return {decks,source:"local",meta:null};
}

async function fetchAIDecks(playerData, cards) {
  const res=await fetch(`${WORKER_URL}/ai/recommend`,{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({player:playerData,cards})
  });
  if(!res.ok) throw new Error(`AI recommend failed: ${res.status}`);
  return res.json();
}

async function fetchMetaNews() {
  try {
    const res=await fetch(`${WORKER_URL}/meta/news`);
    if(!res.ok) return null;
    return res.json();
  } catch(e){ return null; }
}

async function explainTopDecks(topDecks, playerData) {
  const deckSummaries=topDecks.map((d,i)=>{
    const wrStr=d.winRate?`, WR:${d.winRate}%`:"";
    const wilsonStr=d.wilsonScore?`, Wilson:${d.wilsonScore}%`:"";
    const personalStr=d.personalWR!=null?`, YourWR:${d.personalWR}%`:"";
    const evoStr=d.evosUsed?.length?`, EVOs:${d.evosUsed.join(",")}` :"";
    const heroStr=d.hero?`, Hero:${d.hero}`:"";
    const bracketStr=d.bracket?`, Bracket:${d.bracket}`:"";
    return `Deck ${i+1}: ${d.name} (${d.archetype}, ${d.tier}, Power:${d.powerRating}/100${wrStr}${wilsonStr}${personalStr}${evoStr}${heroStr}${bracketStr})
Cards: ${d.cards.join(", ")}
Levels: ${d.deckCards?.map(c=>`${c.name} L${c.level||"?"}/${c.maxLevel||14}${c.evolutionLevel>0?` EVO${c.evolutionLevel}`:""}${isChampionCard(c)?" HERO":""}`).join(", ")}`;
  }).join("\n\n");

  const prompt=`Player: ${playerData.name} | Trophies: ${playerData.trophies} | Arena: ${playerData.arena?.name} | King Level: ${playerData.expLevel}

Top 3 decks (v2 engine — Wilson score confidence + trophy-range filtered):
${deckSummaries}

Return ONLY this JSON array, no markdown:
[{"deckIndex":0,"winCondition":"1-2 sentences","synergies":["s1","s2"],"attack":"2 sentences","defense":"2 sentences","counters":["c1","c2","c3"],"heroTip":"hero tip or null","evoTips":["evo tip"],"upgradePriority":[{"card":"Name","reason":"why","impact":"high"}]}]`;

  const response=await callAI("You are an expert Clash Royale coach 2026. Return only valid JSON array.",prompt,null,2000);
  const clean=response.replace(/```json|```/g,"").trim();
  const match=clean.match(/\[[\s\S]*\]/);
  if(!match) throw new Error("Could not parse AI explanation");
  return JSON.parse(match[0]);
}

const RARITY_COLORS={common:"#90a4ae",rare:"#42a5f5",epic:"#ab47bc",legendary:"#ffd700",champion:"#ff6f00"};
const TYPE_ICONS={troop:"⚔️",spell:"✨",building:"🏰",champion:"👑"};

function ElixirBadge({value}){
  const colors={1:"#e91e63",2:"#9c27b0",3:"#3f51b5",4:"#2196f3",5:"#00bcd4",6:"#4caf50",7:"#ff9800",8:"#f44336"};
  return <div style={{background:colors[value]||"#555",color:"#fff",borderRadius:"50%",width:18,height:18,display:"flex",alignItems:"center",justifyContent:"center",fontSize:10,fontWeight:800,flexShrink:0}}>{value}</div>;
}

function CardTile({card,selected,onClick}){
  const col=RARITY_COLORS[card.rarity?.toLowerCase()]||"#888";
  const isChampion=isChampionCard(card);
  const isHero=!!card.iconUrls?.heroMedium;
  const evoInfo=card.evolutionLevel>0?EVO_TIERS[card.name]:null;
  const borderCol=selected?col:isHero?"#FFD700":isChampion?"rgba(255,111,0,0.3)":"rgba(255,255,255,0.08)";
  const shadow=selected?`0 0 14px ${col}55`:isHero?"0 0 8px rgba(255,215,0,0.3)":isChampion?"0 0 8px rgba(255,111,0,0.2)":"none";
  const imgSrc=isHero?card.iconUrls.heroMedium:(card.evolutionLevel>0&&card.iconUrls?.evolutionMedium?card.iconUrls.evolutionMedium:card.iconUrls?.medium);
  return(
    <div onClick={onClick} style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:2,padding:"8px 4px",background:selected?`${col}25`:"rgba(255,255,255,0.04)",border:`2px solid ${borderCol}`,borderRadius:10,cursor:"pointer",transition:"all 0.15s",boxShadow:shadow,position:"relative",minHeight:80}}>
      {imgSrc?<img src={imgSrc} alt={card.name} style={{width:44,height:44,objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:22}}>{isHero?"⚔️":isChampion?"👑":TYPE_ICONS[card.type?.toLowerCase()]||"🃏"}</div>}
      <div style={{fontSize:9,color:selected?col:isHero?"#FFD700":isChampion?"#ff9a40":"#666",fontWeight:selected||isHero||isChampion?700:400,textAlign:"center",lineHeight:1.2,wordBreak:"break-word",width:"100%"}}>{card.name}</div>
      <div style={{position:"absolute",top:4,left:4}}><ElixirBadge value={card.elixirCost||"?"}/></div>
      {card.level&&<div style={{position:"absolute",top:4,right:4,fontSize:8,background:"rgba(0,0,0,0.8)",borderRadius:3,padding:"1px 3px",color:"#ffd700",fontWeight:700}}>L{card.level}</div>}
      {card.evolutionLevel>0&&<div style={{position:"absolute",bottom:20,right:3,fontSize:7,color:"#00e5ff",fontWeight:800,background:"rgba(0,229,255,0.1)",borderRadius:2,padding:"0 2px"}}>EVO{card.evolutionLevel}</div>}
      {isHero?<div style={{position:"absolute",bottom:20,left:3,fontSize:7,color:"#FFD700",fontWeight:800,background:"rgba(255,215,0,0.15)",borderRadius:2,padding:"0 2px"}}>⚔️HERO</div>:isChampion&&<div style={{position:"absolute",bottom:20,left:3,fontSize:7,color:"#ff9a40",fontWeight:800}}>👑</div>}
      {evoInfo&&<div style={{position:"absolute",bottom:0,left:0,right:0,fontSize:6,color:evoInfo.tier==="S+"?"#ffd700":evoInfo.tier==="S"?"#ff9800":"#4caf50",fontWeight:800,textAlign:"center",background:"rgba(0,0,0,0.6)",borderRadius:"0 0 8px 8px",padding:"1px 0"}}>{evoInfo.tier}</div>}
    </div>
  );
}

function DeckCardSlot({card,onRemove}){
  if(!card) return <div style={{aspectRatio:"3/4",border:"2px dashed rgba(255,255,255,0.08)",borderRadius:8,display:"flex",alignItems:"center",justifyContent:"center",color:"rgba(255,255,255,0.12)",fontSize:20}}>+</div>;
  const col=RARITY_COLORS[card.rarity?.toLowerCase()]||"#888";
  const isChampion=isChampionCard(card);
  const isHero=!!card.iconUrls?.heroMedium;
  const isEvo=card.evolutionLevel>0;
  const borderCol=isHero?"#FFD700":isChampion?"#ff6f00":isEvo?"rgba(0,229,255,0.6)":col+"66";
  const glowShadow=isHero?"0 0 8px rgba(255,215,0,0.3)":isChampion?"0 0 8px rgba(255,111,0,0.3)":isEvo?"0 0 8px rgba(0,229,255,0.3)":"none";
  const imgSrc=isHero?card.iconUrls.heroMedium:(isEvo&&card.iconUrls?.evolutionMedium?card.iconUrls.evolutionMedium:card.iconUrls?.medium);
  return(
    <div onClick={onRemove} style={{aspectRatio:"3/4",background:`linear-gradient(145deg,${col}25,${col}08)`,border:`2px solid ${borderCol}`,borderRadius:8,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",cursor:"pointer",padding:3,gap:2,position:"relative",boxShadow:glowShadow}}>
      {imgSrc?<img src={imgSrc} alt={card.name} style={{width:"70%",objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:18}}>{isHero?"⚔️":isChampion?"👑":TYPE_ICONS[card.type?.toLowerCase()]||"🃏"}</div>}
      <div style={{fontSize:7,color:isHero?"#FFD700":isChampion?"#ff9a40":col,fontWeight:700,textAlign:"center",lineHeight:1.1,wordBreak:"break-word",width:"100%"}}>{card.name}</div>
      <ElixirBadge value={card.elixirCost||"?"}/>
      {isEvo&&<div style={{position:"absolute",top:2,left:2,fontSize:7,color:"#00e5ff",fontWeight:800,background:"rgba(0,0,0,0.7)",borderRadius:2,padding:"0 2px"}}>EVO{card.evolutionLevel}</div>}
      {isHero?<div style={{position:"absolute",top:2,right:2,fontSize:7,color:"#FFD700",fontWeight:800,background:"rgba(255,215,0,0.15)",borderRadius:2,padding:"0 2px"}}>⚔️</div>:isChampion&&<div style={{position:"absolute",top:2,right:2,fontSize:8}}>👑</div>}
      <div style={{position:"absolute",bottom:2,right:2,color:"rgba(255,255,255,0.2)",fontSize:9}}>✕</div>
    </div>
  );
}

function Bubble({msg}){
  const isAI=msg.role==="assistant";
  return(
    <div style={{display:"flex",flexDirection:isAI?"row":"row-reverse",gap:8,alignItems:"flex-start",marginBottom:12}}>
      {isAI&&<div style={{width:30,height:30,borderRadius:"50%",background:"linear-gradient(135deg,#ff6f00,#e65100)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,flexShrink:0}}>🤖</div>}
      <div style={{maxWidth:"82%",background:isAI?"rgba(255,111,0,0.09)":"rgba(255,255,255,0.06)",border:`1px solid ${isAI?"rgba(255,111,0,0.25)":"rgba(255,255,255,0.08)"}`,borderRadius:isAI?"4px 14px 14px 14px":"14px 4px 14px 14px",padding:"10px 14px",fontSize:14,color:"#ddd",lineHeight:1.65,whiteSpace:"pre-wrap"}}>
        {msg.content}
      </div>
    </div>
  );
}

function MetaNewsCard({news}){
  if(!news) return null;
  const alertColors={buff:"#4caf50",nerf:"#f44336",rising:"#2196f3",falling:"#ff9800"};
  return(
    <div style={{background:"rgba(255,255,255,0.025)",border:"1px solid rgba(255,111,0,0.15)",borderRadius:12,padding:14,marginBottom:16}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
        <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:16,letterSpacing:1,color:"#ff9a40"}}>📰 META REPORT</div>
        <div style={{fontSize:10,color:"#333"}}>{news.lastUpdated} · v2 engine</div>
      </div>
      <div style={{fontSize:12,color:"#555",marginBottom:12,lineHeight:1.6}}>{news.metaSummary}</div>
      {news.alerts?.length>0&&(
        <div style={{marginBottom:12}}>
          {news.alerts.map((alert,i)=>(
            <div key={i} style={{display:"flex",gap:8,alignItems:"flex-start",padding:"6px 8px",background:`${alertColors[alert.type]||"#888"}11`,border:`1px solid ${alertColors[alert.type]||"#888"}33`,borderRadius:8,marginBottom:6}}>
              <span style={{fontSize:14,flexShrink:0}}>{alert.emoji}</span>
              <div style={{flex:1}}>
                <span style={{fontSize:12,color:alertColors[alert.type]||"#888",fontWeight:700}}>{alert.card}</span>
                <span style={{fontSize:11,color:"#555",marginLeft:6}}>{alert.message}</span>
              </div>
              <div style={{fontSize:9,color:alertColors[alert.type]||"#888",background:`${alertColors[alert.type]||"#888"}22`,borderRadius:3,padding:"1px 5px",flexShrink:0,fontWeight:700,textTransform:"uppercase"}}>{alert.impact}</div>
            </div>
          ))}
        </div>
      )}
      {news.topArchetypes?.length>0&&(
        <div style={{marginBottom:10}}>
          <div style={{fontSize:10,color:"#ff9a40",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:6}}>🏆 TOP ARCHETYPES</div>
          {news.topArchetypes.map((a,i)=>(
            <div key={i} style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
              <div style={{fontSize:11,background:`${getTierColor(a.tier)}22`,border:`1px solid ${getTierColor(a.tier)}55`,borderRadius:3,padding:"1px 6px",color:getTierColor(a.tier),fontWeight:800,minWidth:28,textAlign:"center"}}>{a.tier}</div>
              <div style={{fontSize:12,color:"#ddd",fontWeight:600}}>{a.name}</div>
              <div style={{fontSize:10,color:a.trend==="rising"?"#4caf50":a.trend==="falling"?"#f44336":"#555"}}>{a.trend==="rising"?"📈":a.trend==="falling"?"📉":"→"}</div>
              <div style={{fontSize:10,color:"#444",flex:1}}>{a.reason}</div>
            </div>
          ))}
        </div>
      )}
      {news.tip&&<div style={{fontSize:11,color:"#ffd700",background:"rgba(255,215,0,0.06)",border:"1px solid rgba(255,215,0,0.15)",borderRadius:6,padding:"6px 10px"}}>💡 {news.tip}</div>}
    </div>
  );
}

function DeckOption({deckData,explanation,allCards,onSelect,index,isAIGenerated}){
  const isCurrentDeck=deckData.matchType==="current";
  const col=isCurrentDeck?"#00e5ff":isAIGenerated?"#9c27b0":["#ffd700","#c0c0c0","#cd7f32"][index]||"#888";
  const tierCol=getTierColor(deckData.tier);
  const ratingColor=deckData.powerRating>=80?"#4caf50":deckData.powerRating>=60?"#ffd700":"#ff9800";
  const isLive=deckData.source==="live";
  const upgrades=explanation?.upgradePriority||[];
  const evosInDeck=deckData.deckCards?.filter(c=>c?.evolutionLevel>0)||[];
  const heroInDeck=deckData.deckCards?.find(c=>isChampionCard(c))||(deckData.hero?{name:deckData.hero}:null);

  return(
    <div style={{background:isAIGenerated?"rgba(156,39,176,0.04)":isCurrentDeck?"rgba(0,229,255,0.04)":"rgba(255,255,255,0.025)",border:`1px solid ${col}${isCurrentDeck||isAIGenerated?"55":"33"}`,borderRadius:14,padding:16,marginBottom:16}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:10,gap:8}}>
        <div style={{minWidth:0}}>
          <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:4,flexWrap:"wrap"}}>
            {isCurrentDeck?<div style={{fontSize:10,background:"rgba(0,229,255,0.15)",border:"1px solid rgba(0,229,255,0.4)",borderRadius:4,padding:"2px 8px",color:"#00e5ff",fontWeight:800}}>🎮 YOUR DECK</div>
            :isAIGenerated?<div style={{fontSize:10,background:"rgba(156,39,176,0.15)",border:"1px solid rgba(156,39,176,0.4)",borderRadius:4,padding:"2px 8px",color:"#ce93d8",fontWeight:800}}>🤖 AI GENERATED</div>
            :<div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:22,color:col,lineHeight:1}}>#{index+1}</div>}
            <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:15,color:"#ddd",letterSpacing:0.5,lineHeight:1}}>{deckData.name||"Meta Deck"}</div>
            {deckData.matchType==="partial"&&<div style={{fontSize:9,background:"rgba(255,152,0,0.15)",border:"1px solid rgba(255,152,0,0.3)",borderRadius:4,padding:"2px 6px",color:"#ffb74d"}}>ADAPTED</div>}
            {isLive&&<div style={{fontSize:9,background:"rgba(76,175,80,0.15)",border:"1px solid rgba(76,175,80,0.3)",borderRadius:4,padding:"2px 6px",color:"#81c784"}}>🔴 LIVE</div>}
            {deckData.bracket&&<div style={{fontSize:9,background:"rgba(33,150,243,0.12)",border:"1px solid rgba(33,150,243,0.3)",borderRadius:4,padding:"2px 6px",color:"#64b5f6"}}>{deckData.bracket}</div>}
          </div>
          <div style={{display:"flex",alignItems:"center",gap:6,flexWrap:"wrap"}}>
            <div style={{fontSize:11,background:`${tierCol}22`,border:`1px solid ${tierCol}55`,borderRadius:4,padding:"2px 8px",color:tierCol,fontWeight:800}}>{deckData.tier}</div>
            <div style={{fontSize:11,color:"#555"}}>{deckData.archetype||"Unknown"}</div>
            <div style={{fontSize:12,color:ratingColor,fontWeight:700}}>⭐ {deckData.powerRating}/100</div>
            {deckData.winRate!=null&&<div style={{fontSize:11,color:"#4caf50",fontWeight:700}}>📊 {deckData.winRate}%</div>}
            {deckData.wilsonScore!=null&&<div style={{fontSize:11,color:"#2196f3",fontWeight:700}}>Wilson {deckData.wilsonScore}%</div>}
            {deckData.confidence!=null&&<div style={{fontSize:10,color:"#444"}}>conf {deckData.confidence}%</div>}
            {deckData.personalWR!=null&&<div style={{fontSize:11,color:"#00e5ff",fontWeight:700}}>🎮 {deckData.personalWR}%</div>}
          </div>
          {(evosInDeck.length>0||heroInDeck)&&(
            <div style={{display:"flex",gap:4,flexWrap:"wrap",marginTop:5}}>
              {heroInDeck&&<div style={{fontSize:9,background:"rgba(255,111,0,0.12)",border:"1px solid rgba(255,111,0,0.3)",borderRadius:4,padding:"2px 6px",color:"#ff9a40",fontWeight:700}}>👑 {heroInDeck.name}</div>}
              {evosInDeck.map((c,i)=>{
                const evoInfo=EVO_TIERS[c.name];
                return <div key={i} style={{fontSize:9,background:"rgba(0,229,255,0.08)",border:"1px solid rgba(0,229,255,0.25)",borderRadius:4,padding:"2px 6px",color:"#00e5ff",fontWeight:700}}>⚡ {c.name} {evoInfo?`(${evoInfo.tier})`:""}</div>;
              })}
            </div>
          )}
        </div>
        <button onClick={()=>onSelect(deckData)} style={{padding:"9px 16px",background:isAIGenerated?"linear-gradient(135deg,#9c27b0,#6a1b9a)":isCurrentDeck?"linear-gradient(135deg,#00e5ff,#0097a7)":`linear-gradient(135deg,${col},${col}88)`,border:"none",borderRadius:9,color:"#fff",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:13,letterSpacing:1,flexShrink:0,fontWeight:800}}>USE</button>
      </div>

      <div style={{marginBottom:12}}>
        <div style={{height:5,background:"rgba(255,255,255,0.06)",borderRadius:3,overflow:"hidden"}}>
          <div style={{width:`${deckData.powerRating}%`,height:"100%",background:`linear-gradient(90deg,${ratingColor},${ratingColor}88)`,borderRadius:3}}/>
        </div>
      </div>

      {deckData.substituted&&<div style={{fontSize:11,color:"#ffb74d",background:"rgba(255,152,0,0.08)",border:"1px solid rgba(255,152,0,0.2)",borderRadius:6,padding:"5px 10px",marginBottom:10}}>⚠️ Missing <b>{deckData.substituted.original}</b> → replaced with <b>{deckData.substituted.replacement}</b></div>}

      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:6,marginBottom:12}}>
        {deckData.cards.map((cardName,i)=>{
          const card=allCards.find(c=>c.name.toLowerCase()===cardName.toLowerCase());
          const rcol=card?(RARITY_COLORS[card.rarity?.toLowerCase()]||"#888"):"#444";
          const lfm=card?(card.maxLevel||14)-(card.level||1):99;
          const isChamp=isChampionCard(card);
          const isHeroCard=!!card?.iconUrls?.heroMedium;
          const evoInfo=card?.evolutionLevel>0?EVO_TIERS[card.name]:null;
          const cardImgSrc=isHeroCard?card.iconUrls.heroMedium:(card?.evolutionLevel>0&&card?.iconUrls?.evolutionMedium?card.iconUrls.evolutionMedium:card?.iconUrls?.medium);
          return(
            <div key={i} style={{aspectRatio:"3/4",background:card?`linear-gradient(145deg,${rcol}20,${rcol}08)`:"rgba(255,50,50,0.1)",border:`1.5px solid ${card?isHeroCard?"#FFD700":isChamp?"#ff6f00":rcol+"55":"rgba(255,50,50,0.3)"}`,borderRadius:8,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:3,gap:1,position:"relative",boxShadow:isHeroCard?"0 0 6px rgba(255,215,0,0.2)":isChamp?"0 0 6px rgba(255,111,0,0.2)":"none"}}>
              {cardImgSrc?<img src={cardImgSrc} alt={card.name} style={{width:"78%",objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:14}}>{card?(isHeroCard?"⚔️":isChamp?"👑":TYPE_ICONS[card.type?.toLowerCase()]||"🃏"):"❌"}</div>}
              <div style={{fontSize:6,color:card?(isHeroCard?"#FFD700":isChamp?"#ff9a40":rcol):"#ff5252",fontWeight:700,textAlign:"center",lineHeight:1.1,wordBreak:"break-word",width:"100%"}}>{cardName}</div>
              {card&&<div style={{fontSize:6,color:lfm<=1?"#4caf50":lfm<=3?"#ffd700":"#ff5252",fontWeight:700}}>L{card.level}</div>}
              {card?.evolutionLevel>0&&<div style={{position:"absolute",top:1,right:1,fontSize:6,color:"#00e5ff",fontWeight:800,background:"rgba(0,0,0,0.7)",borderRadius:2,padding:"0 1px"}}>E{card.evolutionLevel}</div>}
              {isHeroCard?<div style={{position:"absolute",top:1,left:1,fontSize:6,color:"#FFD700",fontWeight:800}}>⚔️</div>:isChamp&&<div style={{position:"absolute",top:1,left:1,fontSize:7}}>👑</div>}
              {evoInfo&&<div style={{position:"absolute",bottom:0,left:0,right:0,fontSize:5,color:evoInfo.tier==="S+"?"#ffd700":"#4caf50",fontWeight:800,textAlign:"center",background:"rgba(0,0,0,0.7)",borderRadius:"0 0 6px 6px"}}>{evoInfo.tier}</div>}
            </div>
          );
        })}
      </div>

      {explanation&&(
        <>
          {deckData.whyThisDeck&&<div style={{fontSize:12,color:"#9c27b0",marginBottom:8,padding:"6px 8px",background:"rgba(156,39,176,0.06)",border:"1px solid rgba(156,39,176,0.15)",borderRadius:6}}>🤖 {deckData.whyThisDeck}</div>}
          <div style={{fontSize:12,color:"#777",marginBottom:10,padding:"8px 10px",background:"rgba(255,255,255,0.025)",borderRadius:8}}>🎯 <span style={{color:"#bbb"}}>{explanation.winCondition||deckData.winCondition}</span></div>
          {explanation.synergies?.length>0&&(
            <div style={{marginBottom:10}}>
              <div style={{fontSize:10,color:col,fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:5}}>⚡ SYNERGIES</div>
              {explanation.synergies.map((s,i)=><div key={i} style={{fontSize:12,color:"#555",padding:"3px 0",display:"flex",gap:6}}><span style={{color:col,flexShrink:0}}>→</span>{s}</div>)}
            </div>
          )}
          {explanation.heroTip&&<div style={{fontSize:11,color:"#ff9a40",background:"rgba(255,111,0,0.06)",border:"1px solid rgba(255,111,0,0.15)",borderRadius:6,padding:"5px 8px",marginBottom:8}}>👑 Hero tip: {explanation.heroTip}</div>}
          {explanation.evoTips?.length>0&&(
            <div style={{marginBottom:10}}>
              <div style={{fontSize:10,color:"#00e5ff",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:5}}>⚡ EVO TIPS</div>
              {explanation.evoTips.map((t,i)=><div key={i} style={{fontSize:11,color:"#555",padding:"2px 0",display:"flex",gap:6}}><span style={{color:"#00e5ff",flexShrink:0}}>→</span>{t}</div>)}
            </div>
          )}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:10}}>
            <div style={{background:"rgba(255,111,0,0.06)",border:"1px solid rgba(255,111,0,0.15)",borderRadius:8,padding:"8px 10px"}}>
              <div style={{fontSize:10,color:"#ff9a40",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:4}}>⚔️ ATTACK</div>
              <div style={{fontSize:11,color:"#555",lineHeight:1.5}}>{explanation.attack}</div>
            </div>
            <div style={{background:"rgba(33,150,243,0.06)",border:"1px solid rgba(33,150,243,0.15)",borderRadius:8,padding:"8px 10px"}}>
              <div style={{fontSize:10,color:"#64b5f6",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:4}}>🛡️ DEFENSE</div>
              <div style={{fontSize:11,color:"#555",lineHeight:1.5}}>{explanation.defense}</div>
            </div>
          </div>
          {explanation.counters?.length>0&&(
            <div style={{display:"flex",gap:6,flexWrap:"wrap",alignItems:"center",marginBottom:10}}>
              <span style={{fontSize:10,color:"#444",textTransform:"uppercase",letterSpacing:1}}>⚠️ Watch:</span>
              {explanation.counters.map((c,i)=><span key={i} style={{fontSize:11,background:"rgba(255,50,50,0.08)",border:"1px solid rgba(255,50,50,0.2)",borderRadius:5,padding:"2px 8px",color:"#ff5252"}}>{c}</span>)}
            </div>
          )}
          {upgrades.length>0&&(
            <div style={{borderTop:"1px solid rgba(255,255,255,0.05)",paddingTop:10}}>
              <div style={{fontSize:10,color:"#ffd700",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:6}}>⬆️ UPGRADE PRIORITY</div>
              {upgrades.map((u,i)=>(
                <div key={i} style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}>
                  <div style={{fontSize:10,color:"#ffd700",width:16,textAlign:"center",fontWeight:800}}>{i+1}</div>
                  <div style={{flex:1}}><span style={{fontSize:12,color:"#ffd700",fontWeight:700}}>{u.card}</span><span style={{fontSize:11,color:"#444",marginLeft:6}}>{u.reason}</span></div>
                  <div style={{fontSize:9,padding:"2px 6px",background:u.impact==="high"?"rgba(76,175,80,0.15)":"rgba(255,152,0,0.15)",border:`1px solid ${u.impact==="high"?"rgba(76,175,80,0.3)":"rgba(255,152,0,0.3)"}`,borderRadius:4,color:u.impact==="high"?"#81c784":"#ffb74d",fontWeight:700,textTransform:"uppercase",flexShrink:0}}>{u.impact}</div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function App(){
  const [tagInput,setTagInput]=useState("");
  const [player,setPlayer]=useState(null);
  const [allCards,setAllCards]=useState([]);
  const [deck,setDeck]=useState([]);
  const [deckOptions,setDeckOptions]=useState([]);
  const [explanations,setExplanations]=useState([]);
  const [dataSource,setDataSource]=useState(null);
  const [dbMeta,setDbMeta]=useState(null);
  const [battleStats,setBattleStats]=useState({});
  const [metaNews,setMetaNews]=useState(null);
  const [aiDecks,setAiDecks]=useState([]);
  const [aiLoading,setAiLoading]=useState(false);
  const [aiExplanations,setAiExplanations]=useState([]);
  const [search,setSearch]=useState("");
  const [filterType,setFilterType]=useState("all");
  const [tab,setTab]=useState("home");
  const [messages,setMessages]=useState([{role:"assistant",content:"👑 Enter your #PLAYERTAG to get started — v2 AI engine with Wilson score, trophy-range filtering, hero & EVO support!"}]);
  const [input,setInput]=useState("");
  const [chatLoading,setChatLoading]=useState(false);
  const [fetching,setFetching]=useState(false);
  const [fetchStatus,setFetchStatus]=useState("");
  const [error,setError]=useState("");
  const [decksView,setDecksView]=useState("live");
  const [supportCard,setSupportCard]=useState(null);
  const chatEnd=useRef(null);
  const scrollBottom=()=>setTimeout(()=>chatEnd.current?.scrollIntoView({behavior:"smooth"}),50);

  useEffect(()=>{
    fetchMetaNews().then(news=>{if(news&&!news.error)setMetaNews(news);}).catch(()=>{});
  },[]);

  const fetchPlayer=async()=>{
    const tag=tagInput.trim().replace(/^#/,"").toUpperCase();
    if(!tag) return;
    setFetching(true);setError("");setFetchStatus("Fetching profile...");
    try{
      const data=await crFetch(tag);
      if(!data.name) throw new Error("Player not found.");
      setPlayer(data);
      const cards=(data.cards||[]).sort((a,b)=>(a.elixirCost||0)-(b.elixirCost||0));
      setAllCards(cards);
      console.log("[DEBUG] first 5 cards:", cards.slice(0,5).map(c=>({name:c.name,rarity:c.rarity,type:c.type,evolutionLevel:c.evolutionLevel})));
      console.log("Card types:", [...new Set(cards.map(c => c.rarity))]);
      console.log("[DEBUG] currentDeck:", JSON.stringify(data.currentDeck));
      setSupportCard(data.currentDeckSupportCards?.[0]||null);
      setDeck([]);setDeckOptions([]);setExplanations([]);setAiDecks([]);setAiExplanations([]);

      setFetchStatus("Analyzing battle history...");
      const battles=await crFetchBattles(tag);
      const stats=analyzeBattleHistory(battles);
      setBattleStats(stats);

      setFetchStatus("Loading v2 live deck data...");
      const {decks,source,meta}=await fetchDecks(data,cards,stats);
      setDeckOptions(decks);setDataSource(source);setDbMeta(meta);
      setTab("decks");

      setFetchStatus("AI analyzing decks...");
      const explanationData=await explainTopDecks(decks,data);
      setExplanations(explanationData);
      setFetchStatus("");

      const top=decks[0];
      const evosOwned=cards.filter(c=>c.evolutionLevel>0);
      const heroesOwned=cards.filter(c=>isChampionCard(c));
      const statsLine=Object.keys(stats).length>0
        ?`\n\n📊 Your WRs: ${Object.entries(stats).map(([a,s])=>`${a} ${Math.round(s.wins/(s.wins+s.losses)*100)}%`).join(", ")}`:"";
      const bracketLine=meta?.bracket?`\n🎯 Bracket: ${meta.bracket}${meta.usingGlobal?" (global fallback)":""}` :"";
      setMessages([{role:"assistant",content:`✅ **${data.name}** linked!\n\n🏆 ${data.trophies?.toLocaleString()} trophies · ${data.arena?.name} · King Lv${data.expLevel}\n⚡ ${evosOwned.length} EVOs · 👑 ${heroesOwned.length} heroes${bracketLine}${statsLine}\n\n#1 deck: **${top?.name}** (${top?.tier} · ${top?.powerRating}/100)\n\nTap ⚡ Decks or 🤖 AI Generate!`}]);
      scrollBottom();
    } catch(e){
      setError(`Failed: ${e.message}`);setFetchStatus("");
    }
    setFetching(false);
  };

  const generateAIDecks=async()=>{
    if(!player||!allCards.length) return;
    setAiLoading(true);setDecksView("ai");setError("");
    try{
      const result=await fetchAIDecks(player,allCards);
      if(result.decks?.length>0){
        const cardMap={};
        allCards.forEach(c=>{cardMap[c.name.toLowerCase()]=c;});
        const mappedDecks=result.decks.map(d=>({
          ...d,
          deckCards:d.cards.map(n=>cardMap[n.toLowerCase()]).filter(Boolean),
          source:"ai",isAIGenerated:true,matchType:"ai",
          bracket:result.bracket,
        }));
        setAiDecks(mappedDecks);
        const expl=await explainTopDecks(mappedDecks,player);
        setAiExplanations(expl);
      }
    } catch(e){setError(`AI generation failed: ${e.message}`);}
    setAiLoading(false);
  };

  const selectDeck=(deckData)=>{
    const matched=deckData.deckCards||deckData.cards.map(name=>allCards.find(c=>c.name.toLowerCase()===name.toLowerCase())).filter(Boolean);
    setDeck(matched);setTab("build");
    const evos=matched.filter(c=>c?.evolutionLevel>0);
    const hero=matched.find(c=>isChampionCard(c));
    setMessages(prev=>[...prev,
      {role:"user",content:`Selected ${deckData.name||"deck"}`},
      {role:"assistant",content:`🔥 **${deckData.name}** locked in!\n${deckData.tier} · ${deckData.powerRating}/100${deckData.personalWR!=null?` · 🎮 ${deckData.personalWR}% your WR`:""}${deckData.wilsonScore?` · Wilson ${deckData.wilsonScore}%`:""}${deckData.bracket?`\n🎯 ${deckData.bracket} bracket data`:""}\n${hero?`👑 Hero: ${hero.name} — ${HERO_SYNERGIES[hero.name]?.note||"powerful ability"}`:""}\n${evos.length>0?`⚡ EVOs: ${evos.map(c=>`${c.name} (${EVO_TIERS[c.name]?.tier||"A"})`).join(", ")}`:""}\n\n${deckData.winCondition||"Use your win condition aggressively!"}\n\nAsk me anything!`}
    ]);
  };

  const toggleCard=(card)=>{
    const key=card.id||card.name;
    if(deck.find(c=>(c.id||c.name)===key)){setDeck(deck.filter(c=>(c.id||c.name)!==key));return;}
    if(isChampionCard(card)&&deck.some(c=>isChampionCard(c))) return;
    if(deck.length<8) setDeck([...deck,card]);
  };

  const sendMessage=async(custom)=>{
    const text=custom||input.trim();
    if(!text||chatLoading) return;
    setInput("");
    const deckDesc=deck.length?`Current deck: ${deck.map(c=>`${c.name}(${c.elixirCost}e,L${c.level||"?"}${c.evolutionLevel>0?` EVO${c.evolutionLevel}`:""}${isChampionCard(c)?" 👑":""}`).join(", ")}`:"No deck selected.";
    const playerDesc=player?`Player: ${player.name}, Trophies: ${player.trophies}, King Level: ${player.expLevel}`:"No account linked.";
    const statsDesc=Object.keys(battleStats).length>0?`Personal WRs: ${Object.entries(battleStats).map(([a,s])=>`${a} ${Math.round(s.wins/(s.wins+s.losses)*100)}%`).join(", ")}`:""
    const userMsg={role:"user",content:text};
    const newHistory=[...messages,userMsg];
    setMessages(newHistory);scrollBottom();
    setChatLoading(true);
    try{
      const reply=await callAI(
        `You are an expert Clash Royale AI coach 2026. ${playerDesc}. ${deckDesc}. ${statsDesc}. Hero cards (Champions) have special abilities, only 1 per deck. EVO cards are significantly stronger. Concise, direct, casual gamer tone. Under 200 words.`,
        null,newHistory
      );
      setMessages([...newHistory,{role:"assistant",content:reply}]);
    } catch(e){setMessages([...newHistory,{role:"assistant",content:`⚠️ Error: ${e.message}`}]);}
    setChatLoading(false);scrollBottom();
  };

  const filtered=allCards.filter(c=>{
    const ms=c.name.toLowerCase().includes(search.toLowerCase());
    const mt=filterType==="all"||
      (filterType==="hero"&&!!c.iconUrls?.heroMedium)||
      (filterType==="evo"&&c.evolutionLevel>0)||
      (filterType!=="hero"&&filterType!=="evo"&&c.type?.toLowerCase()===filterType);
    return ms&&mt;
  });

  const avgElixir=deck.length?(deck.reduce((s,c)=>s+(c.elixirCost||0),0)/deck.length).toFixed(1):0;
  const deckPower=deck.length>0?scoreDeckLocal(deck):0;
  const deckEvos=deck.filter(c=>c?.evolutionLevel>0);
  const deckHero=deck.find(c=>isChampionCard(c));
  const quickPrompts=["How do I play this?","What counters this?","Best hero for this?","Rate my EVO choices","Upgrade priority?"];
  const activeDecks=decksView==="ai"?aiDecks:deckOptions;
  const activeExplanations=decksView==="ai"?aiExplanations:explanations;

  return(
    <div style={{minHeight:"100dvh",background:"#08080f",color:"#e0e0e0",fontFamily:"'Rajdhani','Oswald',sans-serif",display:"flex",flexDirection:"column",maxWidth:480,margin:"0 auto",position:"relative"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Bebas+Neue&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;}
        ::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:#1a1a1a;border-radius:2px}
        textarea{resize:none}input::placeholder,textarea::placeholder{color:#2a2a2a}
        body{overscroll-behavior:none;}
      `}</style>

      {/* HEADER */}
      <div style={{background:"linear-gradient(90deg,#140800,#0a0a1a,#140800)",borderBottom:"1px solid rgba(255,111,0,0.15)",padding:"12px 16px",display:"flex",alignItems:"center",justifyContent:"space-between",boxShadow:"0 2px 20px rgba(255,111,0,0.08)",flexShrink:0}}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <span style={{fontSize:24}}>👑</span>
          <div>
            <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:20,letterSpacing:2,color:"#ff6f00",lineHeight:1}}>ROYALE DECK AI</div>
            <div style={{fontSize:8,color:"#333",letterSpacing:1,textTransform:"uppercase"}}>v2 · Live Data · AI Coach · Meta News</div>
          </div>
        </div>
        {player?(
          <div style={{display:"flex",alignItems:"center",gap:8,background:"rgba(255,111,0,0.08)",border:"1px solid rgba(255,111,0,0.2)",borderRadius:8,padding:"6px 10px"}}>
            <div style={{minWidth:0}}>
              <div style={{fontSize:12,fontWeight:700,color:"#ff9a40",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis",maxWidth:90}}>{player.name}</div>
              <div style={{fontSize:9,color:"#444"}}>{player.trophies?.toLocaleString()} 🏆</div>
            </div>
            <button onClick={()=>{setPlayer(null);setAllCards([]);setDeck([]);setDeckOptions([]);setExplanations([]);setBattleStats({});setAiDecks([]);setAiExplanations([]);setTagInput("");setTab("home");setSupportCard(null);}} style={{background:"rgba(255,50,50,0.1)",border:"1px solid rgba(255,50,50,0.2)",borderRadius:4,color:"#ff5252",fontSize:9,cursor:"pointer",padding:"2px 6px",fontFamily:"'Rajdhani',sans-serif",fontWeight:700}}>✕</button>
          </div>
        ):(
          <div style={{display:"flex",gap:6}}>
            <input value={tagInput} onChange={e=>setTagInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&fetchPlayer()} placeholder="#PLAYERTAG"
              style={{width:110,background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.1)",borderRadius:7,padding:"7px 8px",color:"#ddd",fontFamily:"'Rajdhani',sans-serif",fontSize:12,outline:"none",letterSpacing:1}}/>
            <button onClick={fetchPlayer} disabled={fetching} style={{padding:"7px 12px",background:"linear-gradient(135deg,#ff6f00,#e65100)",border:"none",borderRadius:7,color:"#fff",cursor:fetching?"default":"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:13,letterSpacing:1,opacity:fetching?0.6:1}}>
              {fetching?"...":"LINK"}
            </button>
          </div>
        )}
      </div>

      {fetchStatus&&<div style={{background:"rgba(255,111,0,0.06)",borderBottom:"1px solid rgba(255,111,0,0.12)",color:"#cc7a30",padding:"5px 16px",fontSize:11,flexShrink:0}}>⏳ {fetchStatus}</div>}
      {error&&<div style={{background:"rgba(255,50,50,0.07)",borderBottom:"1px solid rgba(255,50,50,0.15)",color:"#ff5252",padding:"5px 16px",fontSize:11,flexShrink:0}}>⚠️ {error}</div>}
      {dataSource&&!fetchStatus&&(
        <div style={{background:dataSource==="live"?"rgba(76,175,80,0.06)":"rgba(255,111,0,0.04)",borderBottom:`1px solid ${dataSource==="live"?"rgba(76,175,80,0.15)":"rgba(255,111,0,0.1)"}`,color:dataSource==="live"?"#66bb6a":"#555",padding:"4px 16px",fontSize:10,flexShrink:0}}>
          {dataSource==="live"
            ?`🔴 LIVE v2 · ${dbMeta?.battles?.toLocaleString()||"?"} battles · ${dbMeta?.totalDecks?.toLocaleString()||"?"} decks · ${dbMeta?.bracket||"?"} bracket${dbMeta?.usingGlobal?" (global)":""}`
            :"📋 Meta engine · Live DB building..."}
        </div>
      )}

      <div style={{flex:1,overflow:"hidden",display:"flex",flexDirection:"column"}}>

        {/* HOME */}
        {tab==="home"&&(
          <div style={{flex:1,overflowY:"auto",padding:20}}>
            {metaNews&&<MetaNewsCard news={metaNews}/>}
            <div style={{textAlign:"center",paddingTop:10,paddingBottom:30}}>
              <div style={{fontSize:48,marginBottom:8}}>👑</div>
              <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:32,letterSpacing:3,color:"#ff6f00",marginBottom:4}}>ROYALE DECK AI</div>
              <div style={{color:"#333",fontSize:12,marginBottom:4}}>v2 Engine · Wilson Score · Trophy Brackets · PageRank</div>
              <div style={{color:"#222",fontSize:11,marginBottom:24}}>No API key in frontend · All calls secured through worker</div>
              <div style={{background:"rgba(255,111,0,0.05)",border:"1px solid rgba(255,111,0,0.15)",borderRadius:14,padding:20,textAlign:"left"}}>
                <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:16,color:"#ff9a40",letterSpacing:1,marginBottom:12}}>V2 FEATURES</div>
                {[
                  "🔴 Trophy-range filtered win rates (Legend/Champion/Master/Challenger)",
                  "📊 Wilson score confidence intervals — no more 100% WR from 2 battles",
                  "⏱️ Temporal decay — recent battles weighted 2x over historical",
                  "🕸️ Card interaction graph — PageRank anchor cards boost scoring",
                  "📈 Meta velocity — detects rising/falling cards in last 48h",
                  "🤖 AI deck generation using live pair stats as synergy ground truth",
                  "👑 Hero card synergy analysis per champion ability",
                  "⚡ EVO tier scoring S+ to B with per-card bonuses",
                  "🔒 Groq API key secured in worker — never exposed to browser",
                  "📰 Live meta news with buff/nerf alerts from real win rate data",
                ].map((s,i)=>(
                  <div key={i} style={{display:"flex",gap:12,padding:"7px 0",borderBottom:"1px solid rgba(255,255,255,0.04)",fontSize:12,color:"#3a3a3a",alignItems:"flex-start"}}>{s}</div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* DECKS */}
        {tab==="decks"&&(
          <div style={{flex:1,overflowY:"auto",padding:16}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
              <div>
                <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:22,letterSpacing:2,color:"#ff6f00",lineHeight:1}}>YOUR META DECKS</div>
                <div style={{color:"#333",fontSize:11}}>{dataSource==="live"?"v2 Wilson score + trophy bracket":"Meta engine fallback"}</div>
              </div>
              {player&&(
                <button onClick={generateAIDecks} disabled={aiLoading} style={{padding:"8px 12px",background:aiLoading?"rgba(156,39,176,0.3)":"linear-gradient(135deg,#9c27b0,#6a1b9a)",border:"none",borderRadius:9,color:"#fff",cursor:aiLoading?"default":"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:11,letterSpacing:1,opacity:aiLoading?0.7:1}}>
                  {aiLoading?"⏳ AI...":"🤖 AI GENERATE"}
                </button>
              )}
            </div>

            {aiDecks.length>0&&(
              <div style={{display:"flex",gap:6,marginBottom:12}}>
                <button onClick={()=>setDecksView("live")} style={{flex:1,padding:"7px",background:decksView==="live"?"rgba(255,111,0,0.14)":"transparent",border:`1px solid ${decksView==="live"?"#ff6f00":"rgba(255,255,255,0.06)"}`,borderRadius:7,color:decksView==="live"?"#ff6f00":"#333",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:12,letterSpacing:1}}>⚡ LIVE DATA</button>
                <button onClick={()=>setDecksView("ai")} style={{flex:1,padding:"7px",background:decksView==="ai"?"rgba(156,39,176,0.14)":"transparent",border:`1px solid ${decksView==="ai"?"#9c27b0":"rgba(255,255,255,0.06)"}`,borderRadius:7,color:decksView==="ai"?"#ce93d8":"#333",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:12,letterSpacing:1}}>🤖 AI GENERATED</button>
              </div>
            )}

            {!player?(
              <div style={{textAlign:"center",color:"#222",paddingTop:40,fontSize:13}}>
                <div style={{fontSize:32,marginBottom:8}}>🔗</div>Link your account first
              </div>
            ):activeDecks.length===0?(
              <div style={{textAlign:"center",color:"#333",paddingTop:40,fontSize:13}}>
                <div style={{fontSize:32,marginBottom:8}}>{aiLoading?"⏳":"⚡"}</div>
                {aiLoading?"AI generating your perfect decks...":fetchStatus||"Generating..."}
              </div>
            ):(
              activeDecks.map((d,i)=>(
                <DeckOption key={i} deckData={{...d,source:dataSource}} explanation={activeExplanations[i]} allCards={allCards} onSelect={selectDeck} index={i} isAIGenerated={decksView==="ai"}/>
              ))
            )}
          </div>
        )}

        {/* BUILD */}
        {tab==="build"&&(
          <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
            <div style={{padding:"12px 16px 8px",background:"rgba(255,255,255,0.01)",borderBottom:"1px solid rgba(255,255,255,0.05)"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
                <div style={{fontFamily:"'Bebas Neue',sans-serif",letterSpacing:1,color:"#ff6f00",fontSize:14}}>DECK {deck.length}/8</div>
                <div style={{display:"flex",gap:8,alignItems:"center"}}>
                  {deck.length>0&&(
                    <>
                      <div style={{fontSize:11,color:getTierColor(getTier(deckPower)),fontWeight:800}}>{getTier(deckPower)} · {deckPower}/100</div>
                      <div style={{fontSize:11,color:"#555"}}>⚡{avgElixir}</div>
                      {deckEvos.length>0&&<div style={{fontSize:10,color:"#00e5ff",fontWeight:700}}>EVO×{deckEvos.length}</div>}
                      {deckHero&&<div style={{fontSize:10,color:"#ff9a40",fontWeight:700}}>👑</div>}
                      <button onClick={()=>setDeck([])} style={{background:"rgba(255,50,50,0.09)",border:"1px solid rgba(255,50,50,0.18)",borderRadius:4,color:"#ff5252",fontSize:9,cursor:"pointer",padding:"2px 7px",fontFamily:"'Rajdhani',sans-serif",fontWeight:700}}>CLEAR</button>
                    </>
                  )}
                </div>
              </div>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:6}}>
                {Array(8).fill(null).map((_,i)=><DeckCardSlot key={i} card={deck[i]} onRemove={()=>deck[i]&&toggleCard(deck[i])}/>)}
              </div>
              {deckHero&&(
                <div style={{marginTop:6,padding:"5px 8px",background:"rgba(255,111,0,0.06)",border:"1px solid rgba(255,111,0,0.15)",borderRadius:6,fontSize:11,color:"#ff9a40"}}>
                  👑 {deckHero.name} — {HERO_SYNERGIES[deckHero.name]?.note||"hero card active"}
                </div>
              )}
              {supportCard&&(
                <div style={{marginTop:8,padding:"6px 0 2px"}}>
                  <div style={{fontSize:9,color:"#555",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:5}}>🗼 TOWER SUPPORT</div>
                  <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:6}}>
                    <div style={{aspectRatio:"3/4",background:"linear-gradient(145deg,rgba(192,192,192,0.12),rgba(192,192,192,0.04))",border:"2px solid #9e9e9e",borderRadius:8,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:3,gap:2,position:"relative",boxShadow:"0 0 8px rgba(192,192,192,0.12)"}}>
                      {supportCard.iconUrls?.medium?<img src={supportCard.iconUrls.medium} alt={supportCard.name} style={{width:"70%",objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:18}}>🗼</div>}
                      <div style={{fontSize:7,color:"#9e9e9e",fontWeight:700,textAlign:"center",lineHeight:1.1,wordBreak:"break-word",width:"100%"}}>{supportCard.name}</div>
                      <ElixirBadge value={supportCard.elixirCost||"?"}/>
                      {supportCard.level&&<div style={{position:"absolute",top:2,right:2,fontSize:7,background:"rgba(0,0,0,0.7)",borderRadius:2,padding:"0 2px",color:"#bdbdbd",fontWeight:700}}>L{supportCard.level}</div>}
                      <div style={{position:"absolute",top:2,left:2,fontSize:7,color:"#9e9e9e",fontWeight:800,background:"rgba(158,158,158,0.15)",borderRadius:2,padding:"0 2px"}}>SUP</div>
                    </div>
                  </div>
                </div>
              )}
              {deck.length===8&&(
                <button onClick={()=>{setTab("chat");sendMessage("Full deck analysis: tier, synergies, win condition, hero usage, EVO priorities, counters, upgrade priority.");}} style={{marginTop:8,width:"100%",padding:"10px",background:"linear-gradient(135deg,#ff6f00,#e65100)",border:"none",borderRadius:9,color:"#fff",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:13,letterSpacing:1.5}}>🤖 AI ANALYZE THIS DECK</button>
              )}
            </div>
            <div style={{padding:"8px 16px 6px",borderBottom:"1px solid rgba(255,255,255,0.05)"}}>
              <input value={search} onChange={e=>setSearch(e.target.value)} placeholder={player?"Search cards...":"Link account first"} disabled={!player}
                style={{width:"100%",background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.07)",borderRadius:8,padding:"8px 12px",color:"#ddd",fontFamily:"'Rajdhani',sans-serif",fontSize:13,outline:"none",marginBottom:6}}/>
              <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
                {["all","hero","evo","troop","spell","building"].map(t=>(
                  <button key={t} onClick={()=>setFilterType(t)} style={{padding:"3px 8px",background:filterType===t?"rgba(255,111,0,0.14)":"transparent",border:`1px solid ${filterType===t?"#ff6f00":"rgba(255,255,255,0.06)"}`,borderRadius:5,color:filterType===t?"#ff6f00":"#333",cursor:"pointer",fontSize:10,fontFamily:"'Rajdhani',sans-serif",fontWeight:700,textTransform:"uppercase"}}>{t==="hero"?"⚔️ HERO":t==="evo"?"⚡ EVO":t.toUpperCase()}</button>
                ))}
              </div>
            </div>
            <div style={{flex:1,overflowY:"auto",padding:"8px 16px 16px"}}>
              {!player?(
                <div style={{textAlign:"center",color:"#1e1e1e",fontSize:13,paddingTop:40}}>
                  <div style={{fontSize:32,marginBottom:8}}>🔗</div>Link your account to see your cards
                </div>
              ):(
                <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:6}}>
                  {filtered.map(card=>(
                    <CardTile key={card.id||card.name} card={card} selected={!!deck.find(c=>(c.id||c.name)===(card.id||card.name))} onClick={()=>toggleCard(card)}/>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* CHAT */}
        {tab==="chat"&&(
          <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
            <div style={{flex:1,overflowY:"auto",padding:"16px"}}>
              {messages.map((m,i)=><Bubble key={i} msg={m}/>)}
              {chatLoading&&(
                <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:10}}>
                  <div style={{width:30,height:30,borderRadius:"50%",background:"linear-gradient(135deg,#ff6f00,#e65100)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:14}}>🤖</div>
                  <div style={{color:"#cc7a30",fontSize:13,fontStyle:"italic"}}>Coaching you up...</div>
                </div>
              )}
              <div ref={chatEnd}/>
            </div>
            <div style={{padding:"6px 16px",display:"flex",gap:6,flexWrap:"wrap",borderTop:"1px solid rgba(255,255,255,0.05)"}}>
              {quickPrompts.map(p=>(
                <button key={p} onClick={()=>sendMessage(p)} disabled={chatLoading} style={{padding:"5px 12px",background:"rgba(255,111,0,0.07)",border:"1px solid rgba(255,111,0,0.18)",borderRadius:20,color:"#cc7a30",cursor:"pointer",fontSize:12,fontFamily:"'Rajdhani',sans-serif",fontWeight:600,opacity:chatLoading?0.4:1}}>{p}</button>
              ))}
            </div>
            <div style={{padding:"8px 16px 16px",display:"flex",gap:8}}>
              <textarea value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMessage();}}} placeholder="Ask about deck, hero, EVOs, counters..." rows={2}
                style={{flex:1,background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.08)",borderRadius:10,padding:"10px 14px",color:"#ddd",fontFamily:"'Rajdhani',sans-serif",fontSize:14,outline:"none",lineHeight:1.5}}/>
              <button onClick={()=>sendMessage()} disabled={chatLoading||!input.trim()} style={{padding:"0 16px",background:"linear-gradient(135deg,#ff6f00,#e65100)",border:"none",borderRadius:10,color:"#fff",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:15,letterSpacing:1.5,opacity:chatLoading||!input.trim()?0.45:1}}>↑</button>
            </div>
          </div>
        )}
      </div>

      {/* BOTTOM NAV */}
      <div style={{display:"flex",borderTop:"1px solid rgba(255,255,255,0.07)",background:"#080810",flexShrink:0,paddingBottom:"env(safe-area-inset-bottom)"}}>
        {[
          {id:"home",icon:"🏠",label:"Home"},
          {id:"decks",icon:"⚡",label:"Decks"},
          {id:"build",icon:"🃏",label:"Build"},
          {id:"chat",icon:"🤖",label:"Coach"},
        ].map(t=>(
          <button key={t.id} onClick={()=>setTab(t.id)} style={{flex:1,padding:"10px 0",background:"transparent",border:"none",cursor:"pointer",display:"flex",flexDirection:"column",alignItems:"center",gap:2}}>
            <div style={{fontSize:20}}>{t.icon}</div>
            <div style={{fontSize:10,color:tab===t.id?"#ff6f00":"#333",fontFamily:"'Rajdhani',sans-serif",fontWeight:tab===t.id?700:400,letterSpacing:0.5}}>{t.label}</div>
            {tab===t.id&&<div style={{width:20,height:2,background:"#ff6f00",borderRadius:1}}/>}
          </button>
        ))}
      </div>
    </div>
  );
}
