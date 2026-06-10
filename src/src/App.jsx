import React, { useState, useRef } from "react";

const WORKER_URL = "https://small-king-a65c.jared1999.workers.dev";

async function crFetch(tag) {
 const res = await fetch(`${WORKER_URL}/v1/players/%23${tag}`);
 if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
 return res.json();
}

async function callAI(system, userPrompt, history) {
 const msgs = history
   ? history.map(m => ({ role: m.role, content: m.content }))
   : [{ role: "user", content: userPrompt }];
 const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
   method: "POST",
   headers: { "Content-Type": "application/json", "Authorization": "Bearer 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" },
   body: JSON.stringify({ model: "llama-3.3-70b-versatile", max_tokens: 3000, messages: [{ role: "system", content: system }, ...msgs] }),
 });
 if (!res.ok) throw new Error(`Groq ${res.status}`);
 const data = await res.json();
 return data.choices?.[0]?.message?.content || "Error.";
}

const META_DECKS = [
 { name:"Hog EQ Cycle", archetype:"Cycle", tier:"S", metaScore:100, cards:["Hog Rider","Earthquake","Firecracker","Skeletons","Ice Spirit","Cannon","The Log","Knight"] },
 { name:"Hog FC Cycle", archetype:"Cycle", tier:"S", metaScore:98, cards:["Hog Rider","Firecracker","Skeletons","Ice Spirit","Cannon","The Log","Musketeer","Knight"] },
 { name:"Pekka Bridge Spam", archetype:"Bridge Spam", tier:"S", metaScore:96, cards:["P.E.K.K.A","Bandit","Royal Ghost","Battle Ram","Poison","Zap","Magic Archer","Electro Wizard"] },
 { name:"LavaLoon", archetype:"Beatdown", tier:"S", metaScore:94, cards:["Lava Hound","Balloon","Tombstone","Mega Minion","Lumberjack","Zap","Lightning","Minions"] },
 { name:"Log Bait", archetype:"Bait", tier:"S", metaScore:93, cards:["Goblin Barrel","Princess","Goblin Gang","Rocket","Inferno Tower","Knight","The Log","Barbarian Barrel"] },
 { name:"Miner Poison Cycle", archetype:"Cycle", tier:"A+", metaScore:90, cards:["Miner","Poison","Wall Breakers","Bats","Goblin Gang","Zap","Musketeer","Ice Golem"] },
 { name:"Giant Witch", archetype:"Beatdown", tier:"A+", metaScore:88, cards:["Giant","Witch","Musketeer","Poison","Zap","Archers","Skeleton Army","Tombstone"] },
 { name:"Golem Beatdown", archetype:"Beatdown", tier:"A+", metaScore:87, cards:["Golem","Night Witch","Baby Dragon","Lightning","Tornado","Zap","Tombstone","Mega Minion"] },
 { name:"Graveyard Poison", archetype:"Control", tier:"A+", metaScore:86, cards:["Graveyard","Poison","Ice Golem","Tombstone","Minions","Archers","Barbarian Barrel","Knight"] },
 { name:"X-Bow Cycle", archetype:"Siege", tier:"A+", metaScore:85, cards:["X-Bow","Tesla","Ice Spirit","Skeletons","The Log","Archers","Ice Golem","Earthquake"] },
 { name:"Mortar Bait", archetype:"Siege", tier:"A", metaScore:82, cards:["Mortar","Goblin Gang","Archers","Skeletons","Fireball","Zap","Ice Spirit","Bats"] },
 { name:"Royal Giant Control", archetype:"Control", tier:"A", metaScore:80, cards:["Royal Giant","Electro Dragon","Cannon Cart","Earthquake","Zap","Musketeer","Skeletons","Ice Spirit"] },
 { name:"Ram Rider Bridge Spam", archetype:"Bridge Spam", tier:"A", metaScore:79, cards:["Ram Rider","Bandit","Goblin Gang","Poison","Zap","Magic Archer","Skeletons","Electro Wizard"] },
 { name:"Hog AQ Cycle", archetype:"Cycle", tier:"A", metaScore:78, cards:["Hog Rider","Archers","Ice Golem","Skeletons","Cannon","Fireball","The Log","Ice Spirit"] },
 { name:"Balloon Cycle", archetype:"Cycle", tier:"A", metaScore:74, cards:["Balloon","Freeze","Minions","Skeleton Army","Arrows","Ice Spirit","Goblin Gang","Mega Minion"] },
 { name:"Miner Wall Breakers", archetype:"Cycle", tier:"A", metaScore:73, cards:["Miner","Wall Breakers","Goblin Gang","Fireball","Archers","Bats","Zap","Cannon"] },
 { name:"Pekka Ram Rider", archetype:"Bridge Spam", tier:"A", metaScore:72, cards:["P.E.K.K.A","Ram Rider","Bandit","Poison","Zap","Magic Archer","Skeletons","Electro Wizard"] },
 { name:"Golem Night Witch", archetype:"Beatdown", tier:"A", metaScore:71, cards:["Golem","Night Witch","Mega Minion","Baby Dragon","Earthquake","Zap","Tombstone","Lightning"] },
 { name:"Hog Cycle Classic", archetype:"Cycle", tier:"B+", metaScore:66, cards:["Hog Rider","Musketeer","Cannon","Ice Golem","Fireball","The Log","Skeletons","Ice Spirit"] },
 { name:"Electro Giant Control", archetype:"Control", tier:"B+", metaScore:63, cards:["Electro Giant","Tornado","Electro Spirit","Musketeer","Zap","The Log","Archers","Ice Golem"] },
 { name:"Mini Pekka Bait", archetype:"Bait", tier:"B", metaScore:60, cards:["Mini P.E.K.K.A","Goblin Barrel","Princess","Goblin Gang","Rocket","Zap","The Log","Ice Spirit"] },
];

const SYNERGIES = {
 "Hog Rider":    { "Earthquake":10,"Ice Spirit":6,"Skeletons":6,"Cannon":5,"Firecracker":8,"The Log":5 },
 "Miner":        { "Poison":10,"Wall Breakers":10,"Bats":4,"Goblin Gang":5 },
 "Lava Hound":   { "Balloon":15,"Tombstone":6,"Mega Minion":5,"Lumberjack":8,"Lightning":6 },
 "P.E.K.K.A":   { "Bandit":8,"Battle Ram":7,"Magic Archer":6,"Electro Wizard":5 },
 "Giant":        { "Witch":8,"Musketeer":7,"Poison":6,"Skeleton Army":5 },
 "Golem":        { "Night Witch":10,"Baby Dragon":8,"Lightning":7,"Mega Minion":6 },
 "Graveyard":    { "Poison":12,"Ice Golem":8,"Tombstone":6 },
 "Goblin Barrel":{ "Princess":8,"Goblin Gang":8,"Rocket":7,"The Log":6 },
 "X-Bow":        { "Tesla":8,"Ice Spirit":6,"Skeletons":5,"The Log":5 },
 "Balloon":      { "Lava Hound":15,"Freeze":10,"Minions":5 },
 "Ram Rider":    { "Bandit":8,"Goblin Gang":5,"Zap":4 },
};

const EVO_BONUS = { "Firecracker":25,"Skeletons":25,"Knight":20,"Bomber":18,"Archers":18,"Zap":15,"Barbarian Barrel":12,"Ice Spirit":12 };

function scoreCard(card) {
 const diff = (card.maxLevel||14)-(card.level||1);
 let s = diff<=1?10:diff<=3?6:1;
 if (card.evolutionLevel>0) s += EVO_BONUS[card.name]||20;
 return s;
}

function scoreDeckLocal(cards) {
 const level = cards.reduce((sum,c) => {
   const d = (c.maxLevel||14)-(c.level||1);
   return sum+(d<=1?10:d<=3?6:1);
 }, 0);
 const evo = cards.reduce((sum,c) => c.evolutionLevel>0?sum+(EVO_BONUS[c.name]||20):sum, 0);
 let synergy = 0;
 cards.forEach(c => {
   const l = SYNERGIES[c.name];
   if (!l) return;
   cards.forEach(o => { if (l[o.name]) synergy += l[o.name]; });
 });
 synergy = Math.min(synergy, 60);
 const names = cards.map(c=>c.name);
 let coverage = 0;
 if (names.some(n=>["Musketeer","Archers","Firecracker","Mega Minion","Baby Dragon","Minions","Bats","Electro Dragon"].includes(n))) coverage+=15; else coverage-=50;
 if (names.some(n=>["The Log","Zap","Barbarian Barrel","Ice Spirit"].includes(n))) coverage+=15; else coverage-=20;
 if (names.some(n=>["Fireball","Poison","Rocket","Lightning","Earthquake"].includes(n))) coverage+=15;
 if (cards.some(c=>c.type?.toLowerCase()==="building")) coverage+=10;
 return Math.max(0, Math.min(100, Math.round(level*0.35+evo*0.10+synergy*0.25+coverage*0.15)));
}

function getTier(score) {
 if (score>=95) return "S+"; if (score>=88) return "S"; if (score>=80) return "A+";
 if (score>=70) return "A"; if (score>=60) return "B+"; return "B";
}

function getTierColor(tier) {
 return {"S+":"#ffd700","S":"#ff9800","A+":"#4caf50","A":"#2196f3","B+":"#9c27b0","B":"#607d8b"}[tier]||"#888";
}

function buildLocalCandidates(playerCards) {
 const owned = new Set(playerCards.map(c=>c.name.toLowerCase()));
 const cardMap = {};
 playerCards.forEach(c=>{cardMap[c.name.toLowerCase()]=c;});
 const candidates = [];
 META_DECKS.forEach(meta => {
   const missing = meta.cards.filter(n=>!owned.has(n.toLowerCase()));
   if (missing.length===0) {
     const dc = meta.cards.map(n=>cardMap[n.toLowerCase()]);
     const pr = scoreDeckLocal(dc);
     const fs = Math.round(pr*0.6+meta.metaScore*0.4);
     candidates.push({...meta, deckCards:dc, powerRating:fs, winRate:null, battles:null, matchType:"local"});
   } else if (missing.length===1) {
     const deckNames = new Set(meta.cards.map(n=>n.toLowerCase()));
     const sub = playerCards.filter(c=>!deckNames.has(c.name.toLowerCase())).sort((a,b)=>scoreCard(b)-scoreCard(a))[0];
     if (sub) {
       const newCards = meta.cards.map(n=>owned.has(n.toLowerCase())?n:sub.name);
       const dc = newCards.map(n=>cardMap[n.toLowerCase()]);
       const pr = scoreDeckLocal(dc);
       candidates.push({...meta, name:meta.name+" (Adapted)", cards:newCards, deckCards:dc, powerRating:Math.round(pr*0.6+(meta.metaScore*0.7)*0.4), winRate:null, battles:null, matchType:"partial", substituted:{original:missing[0],replacement:sub.name}});
     }
   }
 });
 if (candidates.length<3) {
   const top8 = [...playerCards].sort((a,b)=>scoreCard(b)-scoreCard(a)).slice(0,8);
   const pr = scoreDeckLocal(top8);
   candidates.push({name:"Best Available",archetype:"Mixed",tier:getTier(pr),metaScore:50,cards:top8.map(c=>c.name),deckCards:top8,powerRating:pr,winRate:null,battles:null,matchType:"generated"});
 }
 const seen = new Set();
 return candidates
   .filter(c=>{const k=c.cards.join(",");if(seen.has(k))return false;seen.add(k);return true;})
   .sort((a,b)=>b.powerRating-a.powerRating)
   .slice(0,20);
}

async function fetchDecks(playerData, cards) {
 try {
   const res = await fetch(`${WORKER_URL}/recommend`, {
     method: "POST",
     headers: { "Content-Type": "application/json" },
     body: JSON.stringify({ player: playerData, cards })
   });
   if (res.ok) {
     const data = await res.json();
     if (data.decks?.length > 0 && data.meta?.hasData) {
       return {
         decks: data.decks.map((d,i) => ({
           ...d,
           name: d.name || `Meta Deck #${i+1}`,
           archetype: d.archetype || "Unknown",
           tier: getTier(d.powerRating),
           source: "live",
         })),
         source: "live",
         meta: data.meta
       };
     }
   }
 } catch (e) {
   console.log("Live DB not ready, using local engine");
 }
 const candidates = buildLocalCandidates(cards);
 return { decks: candidates.slice(0,3), source: "local", meta: null };
}

async function explainTopDecks(topDecks, playerData) {
 const deckSummaries = topDecks.map((d,i) => {
   const wrStr = d.winRate ? `, Win Rate: ${d.winRate}%` : "";
   const bStr = d.battles ? `, Battles: ${d.battles}` : "";
   return `Deck ${i+1}: ${d.name||"Meta Deck"} (${d.archetype||"Unknown"}, ${d.tier} tier, Power: ${d.powerRating}/100${wrStr}${bStr})
Cards: ${d.cards.join(", ")}
Card levels: ${d.deckCards.map(c=>`${c.name} L${c.level||"?"}/${c.maxLevel||14}`).join(", ")}
Evolutions: ${d.deckCards.filter(c=>c.evolutionLevel>0).map(c=>c.name).join(", ")||"None"}`;
 }).join("\n\n");

 const prompt = `Player: ${playerData.name} | Trophies: ${playerData.trophies} | Arena: ${playerData.arena?.name} | King Level: ${playerData.expLevel}

Top 3 decks:
${deckSummaries}

For EACH deck return a JSON explanation. Return ONLY this JSON array, no markdown:
[{"deckIndex":0,"winCondition":"1-2 sentences","synergies":["synergy 1","synergy 2"],"attack":"2 sentences","defense":"2 sentences","counters":["c1","c2","c3"],"upgradePriority":[{"card":"Name","reason":"why","impact":"high"}]}]`;

 const response = await callAI("You are an expert Clash Royale coach 2026. Return only valid JSON array, no markdown.", prompt);
 const clean = response.replace(/```json|```/g,"").trim();
 const match = clean.match(/\[[\s\S]*\]/);
 if (!match) throw new Error("Could not parse AI explanation");
 return JSON.parse(match[0]);
}

const RARITY_COLORS = { common:"#90a4ae",rare:"#42a5f5",epic:"#ab47bc",legendary:"#ffd700",champion:"#ff6f00" };
const TYPE_ICONS = { troop:"âï¸",spell:"â¨",building:"ð°",champion:"ð" };

function ElixirBadge({ value }) {
 const colors = {1:"#e91e63",2:"#9c27b0",3:"#3f51b5",4:"#2196f3",5:"#00bcd4",6:"#4caf50",7:"#ff9800",8:"#f44336",9:"#b71c1c",10:"#7f0000"};
 return <div style={{background:colors[value]||"#555",color:"#fff",borderRadius:"50%",width:20,height:20,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,fontWeight:800,flexShrink:0}}>{value}</div>;
}

function CardTile({ card, selected, onClick }) {
 const col = RARITY_COLORS[card.rarity?.toLowerCase()]||"#888";
 return (
   <div onClick={onClick} title={`${card.name} â L${card.level||"?"}`} style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:3,padding:"6px 4px",background:selected?`${col}25`:"rgba(255,255,255,0.03)",border:`1.5px solid ${selected?col:"rgba(255,255,255,0.07)"}`,borderRadius:8,cursor:"pointer",transition:"all 0.15s",boxShadow:selected?`0 0 12px ${col}55`:"none",position:"relative",minHeight:70}}>
     {card.iconUrls?.medium?<img src={card.iconUrls.medium} alt={card.name} style={{width:38,height:38,objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:20}}>{TYPE_ICONS[card.type?.toLowerCase()]||"ð"}</div>}
     <div style={{fontSize:8,color:selected?col:"#777",fontWeight:selected?700:400,textAlign:"center",lineHeight:1.2,wordBreak:"break-word",width:"100%"}}>{card.name}</div>
     <div style={{position:"absolute",top:3,left:3}}><ElixirBadge value={card.elixirCost||"?"}/></div>
     {card.level&&<div style={{position:"absolute",top:3,right:3,fontSize:8,background:"rgba(0,0,0,0.75)",borderRadius:3,padding:"1px 3px",color:"#ffd700",fontWeight:700}}>L{card.level}</div>}
     {card.evolutionLevel>0&&<div style={{position:"absolute",bottom:18,right:2,fontSize:7,color:"#00e5ff",fontWeight:800}}>EVO</div>}
   </div>
 );
}

function DeckCard({ card, onRemove }) {
 if (!card) return <div style={{aspectRatio:"3/4",border:"1.5px dashed rgba(255,255,255,0.07)",borderRadius:8,display:"flex",alignItems:"center",justifyContent:"center",color:"rgba(255,255,255,0.1)",fontSize:18}}>+</div>;
 const col = RARITY_COLORS[card.rarity?.toLowerCase()]||"#888";
 return (
   <div onClick={onRemove} style={{aspectRatio:"3/4",background:`linear-gradient(145deg,${col}20,${col}08)`,border:`1.5px solid ${col}55`,borderRadius:8,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",cursor:"pointer",padding:3,gap:2,position:"relative"}}>
     {card.iconUrls?.medium?<img src={card.iconUrls.medium} alt={card.name} style={{width:"68%",objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:16}}>{TYPE_ICONS[card.type?.toLowerCase()]||"ð"}</div>}
     <div style={{fontSize:7,color:col,fontWeight:700,textAlign:"center",lineHeight:1.1,wordBreak:"break-word",width:"100%"}}>{card.name}</div>
     <ElixirBadge value={card.elixirCost||"?"}/>
     <div style={{position:"absolute",top:2,right:2,color:"rgba(255,255,255,0.18)",fontSize:9}}>â</div>
   </div>
 );
}

function StatBar({ label, value, max, color }) {
 return (
   <div style={{display:"flex",alignItems:"center",gap:8,fontSize:11}}>
     <div style={{width:82,color:"#555",flexShrink:0}}>{label}</div>
     <div style={{flex:1,height:4,background:"rgba(255,255,255,0.05)",borderRadius:2,overflow:"hidden"}}>
       <div style={{width:`${Math.min(100,(value/max)*100)}%`,height:"100%",background:color,borderRadius:2,transition:"width 0.5s"}}/>
     </div>
     <div style={{width:28,color:"#ccc",textAlign:"right",fontWeight:700,fontSize:12}}>{value}</div>
   </div>
 );
}

function Bubble({ msg }) {
 const isAI = msg.role==="assistant";
 return (
   <div style={{display:"flex",flexDirection:isAI?"row":"row-reverse",gap:8,alignItems:"flex-start",marginBottom:10}}>
     {isAI&&<div style={{width:28,height:28,borderRadius:"50%",background:"linear-gradient(135deg,#ff6f00,#e65100)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:13,flexShrink:0}}>ð¤</div>}
     <div style={{maxWidth:"83%",background:isAI?"rgba(255,111,0,0.08)":"rgba(255,255,255,0.05)",border:`1px solid ${isAI?"rgba(255,111,0,0.22)":"rgba(255,255,255,0.07)"}`,borderRadius:isAI?"4px 12px 12px 12px":"12px 4px 12px 12px",padding:"9px 13px",fontSize:13,color:"#ddd",lineHeight:1.65,whiteSpace:"pre-wrap"}}>
       {msg.content}
     </div>
   </div>
 );
}

function DeckOption({ deckData, explanation, allCards, onSelect, index }) {
 const col = ["#ffd700","#c0c0c0","#cd7f32"][index]||"#888";
 const tierCol = getTierColor(deckData.tier);
 const ratingColor = deckData.powerRating>=80?"#4caf50":deckData.powerRating>=60?"#ffd700":"#ff9800";
 const isLive = deckData.source==="live";
 return (
   <div style={{background:"rgba(255,255,255,0.02)",border:`1px solid ${col}33`,borderRadius:10,padding:14,marginBottom:14}}>
     <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8,gap:8}}>
       <div style={{minWidth:0}}>
         <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:3,flexWrap:"wrap"}}>
           <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:20,color:col,lineHeight:1}}>#{index+1}</div>
           <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:15,color:"#ddd",letterSpacing:0.5,lineHeight:1}}>{deckData.name||"Meta Deck"}</div>
           {deckData.matchType==="partial"&&<div style={{fontSize:8,background:"rgba(255,152,0,0.15)",border:"1px solid rgba(255,152,0,0.3)",borderRadius:3,padding:"1px 5px",color:"#ffb74d"}}>ADAPTED</div>}
           {isLive&&<div style={{fontSize:8,background:"rgba(76,175,80,0.15)",border:"1px solid rgba(76,175,80,0.3)",borderRadius:3,padding:"1px 5px",color:"#81c784"}}>ð´ LIVE</div>}
         </div>
         <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
           <div style={{fontSize:10,background:`${tierCol}22`,border:`1px solid ${tierCol}55`,borderRadius:4,padding:"1px 7px",color:tierCol,fontWeight:800}}>{deckData.tier}</div>
           <div style={{fontSize:10,color:"#666"}}>{deckData.archetype||"Unknown"}</div>
           <div style={{fontSize:11,color:ratingColor,fontWeight:700}}>â­ {deckData.powerRating}/100</div>
           {deckData.winRate!=null&&<div style={{fontSize:11,color:"#4caf50",fontWeight:700}}>ð {deckData.winRate}% WR</div>}
           {deckData.battles!=null&&<div style={{fontSize:10,color:"#555"}}>{deckData.battles.toLocaleString()} battles</div>}
         </div>
       </div>
       <button onClick={()=>onSelect(deckData)} style={{padding:"7px 14px",background:`linear-gradient(135deg,${col},${col}88)`,border:"none",borderRadius:7,color:"#000",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:12,letterSpacing:1,flexShrink:0,fontWeight:800}}>USE THIS</button>
     </div>

     <div style={{marginBottom:10}}>
       <div style={{height:5,background:"rgba(255,255,255,0.05)",borderRadius:3,overflow:"hidden"}}>
         <div style={{width:`${deckData.powerRating}%`,height:"100%",background:`linear-gradient(90deg,${ratingColor},${ratingColor}88)`,borderRadius:3,boxShadow:`0 0 8px ${ratingColor}`}}/>
       </div>
     </div>

     {deckData.substituted&&(
       <div style={{fontSize:10,color:"#ffb74d",background:"rgba(255,152,0,0.08)",border:"1px solid rgba(255,152,0,0.2)",borderRadius:5,padding:"4px 8px",marginBottom:8}}>
         â ï¸ Missing <b>{deckData.substituted.original}</b> â replaced with <b>{deckData.substituted.replacement}</b>
       </div>
     )}

     <div style={{display:"grid",gridTemplateColumns:"repeat(8,1fr)",gap:4,marginBottom:10}}>
       {deckData.cards.map((cardName,i)=>{
         const card = allCards.find(c=>c.name.toLowerCase()===cardName.toLowerCase());
         const rcol = card?(RARITY_COLORS[card.rarity?.toLowerCase()]||"#888"):"#444";
         const lfm = card?(card.maxLevel||14)-(card.level||1):99;
         return (
           <div key={i} style={{aspectRatio:"3/4",background:card?`linear-gradient(145deg,${rcol}20,${rcol}08)`:"rgba(255,50,50,0.1)",border:`1px solid ${card?rcol+"55":"rgba(255,50,50,0.3)"}`,borderRadius:6,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:2,gap:1,position:"relative"}}>
             {card?.iconUrls?.medium?<img src={card.iconUrls.medium} alt={card.name} style={{width:"80%",objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:14}}>{card?TYPE_ICONS[card.type?.toLowerCase()]||"ð":"â"}</div>}
             <div style={{fontSize:6,color:card?rcol:"#ff5252",fontWeight:700,textAlign:"center",lineHeight:1.1,wordBreak:"break-word",width:"100%"}}>{cardName}</div>
             {card&&<div style={{fontSize:6,color:lfm<=1?"#4caf50":lfm<=3?"#ffd700":"#ff5252",fontWeight:700}}>L{card.level}</div>}
             {card?.evolutionLevel>0&&<div style={{position:"absolute",top:1,right:1,fontSize:6,color:"#00e5ff",fontWeight:800}}>EVO</div>}
           </div>
         );
       })}
     </div>

     {explanation?(
       <>
         <div style={{fontSize:11,color:"#888",marginBottom:8,padding:"6px 8px",background:"rgba(255,255,255,0.02)",borderRadius:6}}>
           ð¯ <span style={{color:"#ccc"}}>{explanation.winCondition}</span>
         </div>
         {explanation.synergies?.length>0&&(
           <div style={{marginBottom:8}}>
             <div style={{fontSize:9,color:col,fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:4}}>â¡ KEY SYNERGIES</div>
             {explanation.synergies.map((s,i)=>(
               <div key={i} style={{fontSize:11,color:"#666",padding:"2px 0",display:"flex",gap:6}}>
                 <span style={{color:col,flexShrink:0}}>â</span>{s}
               </div>
             ))}
           </div>
         )}
         <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:8}}>
           <div style={{background:"rgba(255,111,0,0.05)",border:"1px solid rgba(255,111,0,0.15)",borderRadius:6,padding:"7px 9px"}}>
             <div style={{fontSize:9,color:"#ff9a40",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:3}}>âï¸ ATTACK</div>
             <div style={{fontSize:10,color:"#666",lineHeight:1.5}}>{explanation.attack}</div>
           </div>
           <div style={{background:"rgba(33,150,243,0.05)",border:"1px solid rgba(33,150,243,0.15)",borderRadius:6,padding:"7px 9px"}}>
             <div style={{fontSize:9,color:"#64b5f6",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:3}}>ð¡ï¸ DEFENSE</div>
             <div style={{fontSize:10,color:"#666",lineHeight:1.5}}>{explanation.defense}</div>
           </div>
         </div>
         {explanation.counters?.length>0&&(
           <div style={{display:"flex",gap:6,flexWrap:"wrap",alignItems:"center",marginBottom:8}}>
             <span style={{fontSize:9,color:"#555",textTransform:"uppercase",letterSpacing:1}}>â ï¸ Watch out:</span>
             {explanation.counters.map((c,i)=>(
               <span key={i} style={{fontSize:10,background:"rgba(255,50,50,0.08)",border:"1px solid rgba(255,50,50,0.2)",borderRadius:4,padding:"1px 6px",color:"#ff5252"}}>{c}</span>
             ))}
           </div>
         )}
         {explanation.upgradePriority?.length>0&&(
           <div style={{borderTop:"1px solid rgba(255,255,255,0.04)",paddingTop:8}}>
             <div style={{fontSize:9,color:"#ffd700",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:6}}>â¬ï¸ UPGRADE PRIORITY</div>
             {explanation.upgradePriority.map((u,i)=>(
               <div key={i} style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
                 <div style={{fontSize:9,color:"#ffd700",width:14,textAlign:"center",fontWeight:800}}>{i+1}</div>
                 <div style={{flex:1}}>
                   <span style={{fontSize:11,color:"#ffd700",fontWeight:700}}>{u.card}</span>
                   <span style={{fontSize:10,color:"#555",marginLeft:6}}>{u.reason}</span>
                 </div>
                 <div style={{fontSize:8,padding:"1px 5px",background:u.impact==="high"?"rgba(76,175,80,0.15)":"rgba(255,152,0,0.15)",border:`1px solid ${u.impact==="high"?"rgba(76,175,80,0.3)":"rgba(255,152,0,0.3)"}`,borderRadius:3,color:u.impact==="high"?"#81c784":"#ffb74d",fontWeight:700,textTransform:"uppercase",flexShrink:0}}>{u.impact}</div>
               </div>
             ))}
           </div>
         )}
       </>
     ):(
       <div style={{fontSize:11,color:"#444",fontStyle:"italic"}}>Loading AI analysis...</div>
     )}
   </div>
 );
}

export default function App() {
 const [tagInput, setTagInput] = useState("");
 const [player, setPlayer] = useState(null);
 const [allCards, setAllCards] = useState([]);
 const [deck, setDeck] = useState([]);
 const [deckOptions, setDeckOptions] = useState([]);
 const [explanations, setExplanations] = useState([]);
 const [dataSource, setDataSource] = useState(null);
 const [dbMeta, setDbMeta] = useState(null);
 const [search, setSearch] = useState("");
 const [filterType, setFilterType] = useState("all");
 const [tab, setTab] = useState("build");
 const [messages, setMessages] = useState([{role:"assistant",content:"ð Enter your #PLAYERTAG and hit LINK â I'll check live battle data to find your best decks with real win rates!"}]);
 const [input, setInput] = useState("");
 const [chatLoading, setChatLoading] = useState(false);
 const [fetching, setFetching] = useState(false);
 const [fetchStatus, setFetchStatus] = useState("");
 const [error, setError] = useState("");
 const chatEnd = useRef(null);
 const scrollBottom = () => setTimeout(()=>chatEnd.current?.scrollIntoView({behavior:"smooth"}),50);

 const fetchPlayer = async () => {
   const tag = tagInput.trim().replace(/^#/,"").toUpperCase();
   if (!tag) return;
   setFetching(true); setError(""); setFetchStatus("Fetching your profile...");
   try {
     const data = await crFetch(tag);
     if (!data.name) throw new Error("Player not found.");
     setPlayer(data);
     const cards = (data.cards||[]).sort((a,b)=>(a.elixirCost||0)-(b.elixirCost||0));
     setAllCards(cards);
     setDeck([]); setDeckOptions([]); setExplanations([]);
     setFetchStatus("Checking live battle database...");
     const { decks, source, meta } = await fetchDecks(data, cards);
     setDeckOptions(decks);
     setDataSource(source);
     setDbMeta(meta);
     setTab("decks");
     setFetchStatus("AI is analyzing your top decks...");
     const explanationData = await explainTopDecks(decks, data);
     setExplanations(explanationData);
     setFetchStatus("");
     const top = decks[0];
     const sourceLabel = source==="live"
       ? `ð Live data from ${meta?.battles?.toLocaleString()||"?"} battles`
       : "ð Meta engine (live DB building up...)";
     setMessages([{role:"assistant",content:`â Linked **${data.name}**!\n\nð ${data.trophies?.toLocaleString()} trophies Â· ${data.arena?.name} Â· King Level ${data.expLevel}\n\n${sourceLabel}\n\nYour #1 deck: **${top?.name||"Meta Deck"}** (${top?.tier} tier, ${top?.powerRating}/100${top?.winRate!=null?`, ${top.winRate}% WR`:""})\n\nCheck â¡ DECKS for full breakdown!`}]);
     scrollBottom();
   } catch(e) {
     setError(`Failed: ${e.message}`);
     setFetchStatus("");
   }
   setFetching(false);
 };

 const selectDeck = (deckData) => {
   const matched = deckData.deckCards||deckData.cards.map(name=>allCards.find(c=>c.name.toLowerCase()===name.toLowerCase())).filter(Boolean);
   setDeck(matched);
   setTab("build");
   const expl = explanations.find((_,i)=>deckOptions[i]?.cards?.join()===deckData.cards?.join());
   setMessages(prev=>[...prev,
     {role:"user",content:`Selected ${deckData.name||"deck"}`},
     {role:"assistant",content:`ð¥ Locked in! ${deckData.tier} tier Â· ${deckData.powerRating}/100${deckData.winRate!=null?` Â· ${deckData.winRate}% WR`:""}\n\n${expl?.winCondition||"Use your win condition aggressively!"}\n\nâ¡ ${expl?.synergies?.[0]||"Good luck!"}\n\nAsk me anything!`}
   ]);
 };

 const toggleCard = (card) => {
   const key = card.id||card.name;
   if (deck.find(c=>(c.id||c.name)===key)) { setDeck(deck.filter(c=>(c.id||c.name)!==key)); return; }
   if (deck.length<8) setDeck([...deck,card]);
 };

 const sendMessage = async (custom) => {
   const text = custom||input.trim();
   if (!text||chatLoading) return;
   setInput("");
   const deckDesc = deck.length?`Current deck: ${deck.map(c=>`${c.name}(${c.elixirCost}e, L${c.level||"?"}${c.evolutionLevel>0?" EVO":""})`).join(", ")}`:"No deck selected.";
   const playerDesc = player?`Player: ${player.name}, Trophies: ${player.trophies}, Arena: ${player.arena?.name}, King Level: ${player.expLevel}`:"No account linked.";
   const userMsg = {role:"user",content:text};
   const newHistory = [...messages,userMsg];
   setMessages(newHistory); scrollBottom();
   setChatLoading(true);
   try {
     const reply = await callAI(`You are an expert Clash Royale AI coach in 2026. ${playerDesc}. ${deckDesc}. Concise, direct, casual gamer tone. Bullet points. Under 200 words unless deep analysis.`,null,newHistory);
     setMessages([...newHistory,{role:"assistant",content:reply}]);
   } catch(e) { setMessages([...newHistory,{role:"assistant",content:`â ï¸ Error: ${e.message}`}]); }
   setChatLoading(false); scrollBottom();
 };

 const filtered = allCards.filter(c=>{
   const ms = c.name.toLowerCase().includes(search.toLowerCase());
   const mt = filterType==="all"||c.type?.toLowerCase()===filterType;
   return ms&&mt;
 });
 const avgElixir = deck.length?(deck.reduce((s,c)=>s+(c.elixirCost||0),0)/deck.length).toFixed(1):0;
 const cycleElixir = [...deck].sort((a,b)=>(a.elixirCost||0)-(b.elixirCost||0)).slice(0,4).reduce((s,c)=>s+(c.elixirCost||0),0);
 const deckPower = deck.length>0?scoreDeckLocal(deck):0;
 const quickPrompts = ["How do I play this?","What counters this?","Upgrade priority?","Rate my deck 1-10","Best hero for this?"];

 return (
   <div style={{minHeight:"100vh",background:"#08080f",color:"#e0e0e0",fontFamily:"'Rajdhani','Oswald',sans-serif",display:"flex",flexDirection:"column"}}>
     <style>{`
       @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Bebas+Neue&display=swap');
       *{box-sizing:border-box;margin:0;padding:0}
       ::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:#1a1a1a;border-radius:2px}
       textarea{resize:none}input::placeholder,textarea::placeholder{color:#2a2a2a}
     `}</style>

     <div style={{background:"linear-gradient(90deg,#140800,#0a0a1a,#140800)",borderBottom:"1px solid rgba(255,111,0,0.15)",padding:"10px 16px",display:"flex",alignItems:"center",gap:12,flexWrap:"wrap",boxShadow:"0 2px 20px rgba(255,111,0,0.08)"}}>
       <div style={{display:"flex",alignItems:"center",gap:10,flexShrink:0}}>
         <span style={{fontSize:22}}>ð</span>
         <div>
           <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:22,letterSpacing:2,color:"#ff6f00",lineHeight:1}}>ROYALE DECK AI</div>
           <div style={{fontSize:9,color:"#333",letterSpacing:1,textTransform:"uppercase"}}>Live Data Â· Synergy Engine Â· AI Coach</div>
         </div>
       </div>
       <div style={{flex:1,maxWidth:420,display:"flex",gap:6}}>
         {player?(
           <div style={{display:"flex",alignItems:"center",gap:8,background:"rgba(255,111,0,0.07)",border:"1px solid rgba(255,111,0,0.2)",borderRadius:8,padding:"6px 10px",flex:1}}>
             <span style={{fontSize:14}}>ð</span>
             <div style={{flex:1,minWidth:0}}>
               <div style={{fontSize:12,fontWeight:700,color:"#ff9a40",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{player.name}</div>
               <div style={{fontSize:9,color:"#444"}}>{player.trophies?.toLocaleString()} trophies Â· {player.arena?.name} Â· {allCards.length} cards</div>
             </div>
             <button onClick={()=>{setPlayer(null);setAllCards([]);setDeck([]);setDeckOptions([]);setExplanations([]);setTagInput("");}} style={{background:"rgba(255,50,50,0.1)",border:"1px solid rgba(255,50,50,0.2)",borderRadius:4,color:"#ff5252",fontSize:9,cursor:"pointer",padding:"2px 7px",fontFamily:"'Rajdhani',sans-serif",fontWeight:700,flexShrink:0}}>UNLINK</button>
           </div>
         ):(
           <>
             <input value={tagInput} onChange={e=>setTagInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&fetchPlayer()} placeholder="#PLAYERTAG"
               style={{flex:1,background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.1)",borderRadius:7,padding:"7px 10px",color:"#ddd",fontFamily:"'Rajdhani',sans-serif",fontSize:13,outline:"none",letterSpacing:1}}/>
             <button onClick={fetchPlayer} disabled={fetching} style={{padding:"7px 16px",background:"linear-gradient(135deg,#ff6f00,#e65100)",border:"none",borderRadius:7,color:"#fff",cursor:fetching?"default":"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:14,letterSpacing:1,opacity:fetching?0.6:1,flexShrink:0}}>
               {fetching?"...":"LINK"}
             </button>
           </>
         )}
       </div>
       <div style={{display:"flex",gap:5,marginLeft:"auto"}}>
         {["build","decks","chat"].map(t=>(
           <button key={t} onClick={()=>setTab(t)} style={{padding:"5px 13px",background:tab===t?"rgba(255,111,0,0.15)":"transparent",border:`1px solid ${tab===t?"#ff6f00":"rgba(255,255,255,0.07)"}`,borderRadius:6,color:tab===t?"#ff6f00":"#444",cursor:"pointer",fontFamily:"'Rajdhani',sans-serif",fontWeight:700,fontSize:12,letterSpacing:1,textTransform:"uppercase"}}>
             {t==="build"?"ð":t==="decks"?"â¡":"ð¤"} {t}
           </button>
         ))}
       </div>
     </div>

     {fetchStatus&&<div style={{background:"rgba(255,111,0,0.06)",borderBottom:"1px solid rgba(255,111,0,0.12)",color:"#cc7a30",padding:"5px 16px",fontSize:11}}>â³ {fetchStatus}</div>}
     {error&&<div style={{background:"rgba(255,50,50,0.07)",borderBottom:"1px solid rgba(255,50,50,0.15)",color:"#ff5252",padding:"5px 16px",fontSize:11}}>â ï¸ {error}</div>}
     {dataSource&&!fetchStatus&&(
       <div style={{background:dataSource==="live"?"rgba(76,175,80,0.06)":"rgba(255,111,0,0.04)",borderBottom:`1px solid ${dataSource==="live"?"rgba(76,175,80,0.15)":"rgba(255,111,0,0.1)"}`,color:dataSource==="live"?"#66bb6a":"#555",padding:"4px 16px",fontSize:10,display:"flex",gap:16,flexWrap:"wrap"}}>
         <span>{dataSource==="live"?`ð´ LIVE â ${dbMeta?.battles?.toLocaleString()||"?"} battles Â· ${dbMeta?.totalDecks?.toLocaleString()||"?"} unique decks`:"ð META ENGINE â Live DB building, will switch to real data automatically"}</span>
         {dbMeta?.lastCrawl&&<span>Last crawl: {new Date(dbMeta.lastCrawl).toLocaleTimeString()}</span>}
       </div>
     )}

     <div style={{flex:1,display:"flex",overflow:"hidden",height:"calc(100vh - 65px)"}}>
       <div style={{width:260,flexShrink:0,borderRight:"1px solid rgba(255,255,255,0.05)",display:"flex",flexDirection:"column",background:"rgba(255,255,255,0.01)",overflow:"hidden"}}>
         <div style={{padding:"12px 12px 8px"}}>
           <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:7}}>
             <div style={{fontFamily:"'Bebas Neue',sans-serif",letterSpacing:1,color:"#ff6f00",fontSize:13}}>DECK {deck.length}/8</div>
             {deck.length>0&&<button onClick={()=>setDeck([])} style={{background:"rgba(255,50,50,0.09)",border:"1px solid rgba(255,50,50,0.18)",borderRadius:4,color:"#ff5252",fontSize:9,cursor:"pointer",padding:"2px 7px",fontFamily:"'Rajdhani',sans-serif",fontWeight:700}}>CLEAR</button>}
           </div>
           <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:5}}>
             {Array(8).fill(null).map((_,i)=><DeckCard key={i} card={deck[i]} onRemove={()=>deck[i]&&toggleCard(deck[i])}/>)}
           </div>
         </div>
         {deck.length>0&&(
           <div style={{padding:"0 12px 8px",display:"flex",flexDirection:"column",gap:4}}>
             <StatBar label="Avg Elixir" value={avgElixir} max={6} color="#9c27b0"/>
             <StatBar label="Cycle" value={cycleElixir} max={25} color="#2196f3"/>
             <StatBar label="Spells" value={deck.filter(c=>c.type?.toLowerCase()==="spell").length} max={4} color="#4caf50"/>
             <StatBar label="Power" value={deckPower} max={100} color="#ffd700"/>
             {deck.length===8&&(
               <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:2}}>
                 <div style={{fontSize:10,color:getTierColor(getTier(deckPower)),fontWeight:800}}>{getTier(deckPower)} Tier</div>
                 <button onClick={()=>{setTab("chat");sendMessage("Full deck analysis: tier, synergies, win condition, counters, upgrade priority.");}} style={{padding:"5px 10px",background:"linear-gradient(135deg,#ff6f00,#e65100)",border:"none",borderRadius:6,color:"#fff",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:11,letterSpacing:1}}>ð¤ ANALYZE</button>
               </div>
             )}
           </div>
         )}
         <div style={{height:1,background:"rgba(255,255,255,0.04)",margin:"0 12px"}}/>
         <div style={{padding:"4px 12px 6px",display:"flex",flexDirection:"column",gap:5}}>
           <input value={search} onChange={e=>setSearch(e.target.value)} placeholder={player?"Search cards...":"Link account first"} disabled={!player}
             style={{background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.07)",borderRadius:6,padding:"6px 9px",color:"#ddd",fontFamily:"'Rajdhani',sans-serif",fontSize:12,width:"100%",outline:"none"}}/>
           <div style={{display:"flex",gap:3,flexWrap:"wrap"}}>
             {["all","troop","spell","building","champion"].map(t=>(
               <button key={t} onClick={()=>setFilterType(t)} style={{padding:"2px 6px",background:filterType===t?"rgba(255,111,0,0.14)":"transparent",border:`1px solid ${filterType===t?"#ff6f00":"rgba(255,255,255,0.06)"}`,borderRadius:4,color:filterType===t?"#ff6f00":"#333",cursor:"pointer",fontSize:9,fontFamily:"'Rajdhani',sans-serif",fontWeight:700,textTransform:"uppercase"}}>{t}</button>
             ))}
           </div>
         </div>
         <div style={{flex:1,overflowY:"auto",padding:"0 12px 12px"}}>
           {!player?(
             <div style={{textAlign:"center",color:"#1e1e1e",fontSize:12,paddingTop:28}}>
               <div style={{fontSize:26,marginBottom:6}}>ð</div>Link your account<br/>to see your cards
             </div>
           ):(
             <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:4}}>
               {filtered.map(card=>(
                 <CardTile key={card.id||card.name} card={card} selected={!!deck.find(c=>(c.id||c.name)===(card.id||card.name))} onClick={()=>toggleCard(card)}/>
               ))}
             </div>
           )}
         </div>
       </div>

       <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
         {tab==="decks"&&(
           <div style={{flex:1,overflowY:"auto",padding:20}}>
             <div style={{maxWidth:700,margin:"0 auto"}}>
               <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:24,letterSpacing:2,color:"#ff6f00",marginBottom:2}}>YOUR TOP META DECKS</div>
               <div style={{color:"#333",fontSize:11,marginBottom:16}}>
                 {dataSource==="live"?"Ranked by real win rate from live battle data":"Ranked by meta score + synergy + card levels"} Â· Hit USE THIS to auto-fill
               </div>
               {!player?(
                 <div style={{textAlign:"center",color:"#222",paddingTop:40,fontSize:13}}>
                   <div style={{fontSize:32,marginBottom:8}}>ð</div>Link your account
                 </div>
               ):deckOptions.length===0?(
                 <div style={{textAlign:"center",color:"#333",paddingTop:40,fontSize:13}}>
                   <div style={{fontSize:32,marginBottom:8}}>â³</div>{fetchStatus||"Loading..."}
                 </div>
               ):(
                 deckOptions.map((d,i)=>(
                   <DeckOption key={i} deckData={{...d,source:dataSource}} explanation={explanations[i]} allCards={allCards} onSelect={selectDeck} index={i}/>
                 ))
               )}
             </div>
           </div>
         )}

         {tab==="build"&&(
           <div style={{flex:1,overflowY:"auto",padding:24}}>
             <div style={{maxWidth:540,margin:"0 auto"}}>
               <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:28,letterSpacing:2,color:"#ff6f00",marginBottom:4}}>YOUR AI DECK COACH</div>
               <div style={{color:"#2a2a2a",fontSize:13,marginBottom:20}}>Link â Pick deck â Get AI coached</div>
               {!player?(
                 <div style={{background:"rgba(255,111,0,0.05)",border:"1px solid rgba(255,111,0,0.14)",borderRadius:10,padding:18}}>
                   <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:14,color:"#ff9a40",letterSpacing:1,marginBottom:10}}>HOW IT WORKS</div>
                   {["Enter your #PLAYERTAG above and hit LINK","Checks live battle database for real win rates","Falls back to meta engine if DB is still building","Go to â¡ DECKS â pick your best deck","Hit USE THIS â slots auto-fill instantly","Chat with AI for coaching, counters and tips"].map((s,i)=>(
                     <div key={i} style={{display:"flex",gap:10,padding:"5px 0",borderBottom:"1px solid rgba(255,255,255,0.03)",fontSize:12,color:"#3a3a3a"}}>
                       <span style={{color:"#ff6f00",fontWeight:700,width:16,flexShrink:0}}>{i+1}.</span>{s}
                     </div>
                   ))}
                 </div>
               ):(
                 <div style={{background:"rgba(46,125,50,0.06)",border:"1px solid rgba(46,125,50,0.16)",borderRadius:10,padding:14}}>
                   <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:13,color:"#66bb6a",letterSpacing:1,marginBottom:10}}>â {player.name?.toUpperCase()} â LINKED</div>
                   <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8}}>
                     {[["ð","Trophies",player.trophies?.toLocaleString()],["ðºï¸","Arena",player.arena?.name],["ð","Cards",allCards.length],["â­","King Lvl",player.expLevel],["ð","Best",player.bestTrophies?.toLocaleString()],["âï¸","Wins",player.wins?.toLocaleString()]].map(([icon,label,val])=>(
                       <div key={label} style={{background:"rgba(255,255,255,0.02)",borderRadius:7,padding:"7px 9px"}}>
                         <div style={{fontSize:13,marginBottom:1}}>{icon}</div>
                         <div style={{fontSize:8,color:"#333",textTransform:"uppercase",letterSpacing:0.5}}>{label}</div>
                         <div style={{fontSize:13,color:"#bbb",fontWeight:700}}>{val||"â"}</div>
                       </div>
                     ))}
                   </div>
                   {deckOptions.length>0&&<button onClick={()=>setTab("decks")} style={{marginTop:10,width:"100%",padding:"8px",background:"linear-gradient(135deg,#1b5e20,#2e7d32)",border:"1px solid rgba(46,125,50,0.35)",borderRadius:7,color:"#a5d6a7",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:12,letterSpacing:1.5}}>â¡ VIEW YOUR TOP META DECKS</button>}
                 </div>
               )}
             </div>
           </div>
         )}

         {tab==="chat"&&(
           <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
             <div style={{flex:1,overflowY:"auto",padding:"14px 18px"}}>
               {messages.map((m,i)=><Bubble key={i} msg={m}/>)}
               {chatLoading&&(
                 <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:10}}>
                   <div style={{width:28,height:28,borderRadius:"50%",background:"linear-gradient(135deg,#ff6f00,#e65100)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:13}}>ð¤</div>
                   <div style={{color:"#cc7a30",fontSize:12,fontStyle:"italic"}}>Coaching you up...</div>
                 </div>
               )}
               <div ref={chatEnd}/>
             </div>
             <div style={{padding:"6px 18px",display:"flex",gap:5,flexWrap:"wrap",borderTop:"1px solid rgba(255,255,255,0.04)"}}>
               {quickPrompts.map(p=>(
                 <button key={p} onClick={()=>sendMessage(p)} disabled={chatLoading} style={{padding:"3px 10px",background:"rgba(255,111,0,0.06)",border:"1px solid rgba(255,111,0,0.15)",borderRadius:20,color:"#cc7a30",cursor:"pointer",fontSize:11,fontFamily:"'Rajdhani',sans-serif",fontWeight:600,opacity:chatLoading?0.4:1}}>{p}</button>
               ))}
             </div>
             <div style={{padding:"8px 18px 14px",display:"flex",gap:7}}>
               <textarea value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMessage();}}} placeholder="Ask about deck, counters, upgrades..." rows={2}
                 style={{flex:1,background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.07)",borderRadius:9,padding:"9px 13px",color:"#ddd",fontFamily:"'Rajdhani',sans-serif",fontSize:13,outline:"none",lineHeight:1.5}}/>
               <button onClick={()=>sendMessage()} disabled={chatLoading||!input.trim()} style={{padding:"0 16px",background:"linear-gradient(135deg,#ff6f00,#e65100)",border:"none",borderRadius:9,color:"#fff",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:15,letterSpacing:1.5,opacity:chatLoading||!input.trim()?0.45:1}}>SEND</button>
             </div>
           </div>
         )}
       </div>
     </div>
   </div>
 );
}
