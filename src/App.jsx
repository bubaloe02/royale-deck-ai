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
 const level = cards.reduce((sum,c) => { const d=(c.maxLevel||14)-(c.level||1); return sum+(d<=1?10:d<=3?6:1); }, 0);
 const evo = cards.reduce((sum,c) => c.evolutionLevel>0?sum+(EVO_BONUS[c.name]||20):sum, 0);
 let synergy = 0;
 cards.forEach(c => { const l=SYNERGIES[c.name]; if(!l) return; cards.forEach(o=>{if(l[o.name]) synergy+=l[o.name];}); });
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
     candidates.push({...meta, deckCards:dc, powerRating:Math.round(pr*0.6+meta.metaScore*0.4), winRate:null, battles:null, matchType:"local"});
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
 return candidates.filter(c=>{const k=c.cards.join(",");if(seen.has(k))return false;seen.add(k);return true;}).sort((a,b)=>b.powerRating-a.powerRating).slice(0,20);
}

async function fetchDecks(playerData, cards) {
 try {
   const res = await fetch(`${WORKER_URL}/recommend`, {
     method:"POST", headers:{"Content-Type":"application/json"},
     body:JSON.stringify({player:playerData, cards})
   });
   if (res.ok) {
     const data = await res.json();
     if (data.decks?.length>0 && data.meta?.hasData) {
       return { decks:data.decks.map((d,i)=>({...d,name:d.name||`Meta Deck #${i+1}`,archetype:d.archetype||"Unknown",tier:getTier(d.powerRating),source:"live"})), source:"live", meta:data.meta };
     }
   }
 } catch(e) { console.log("Live DB not ready"); }
 const candidates = buildLocalCandidates(cards);
 return { decks:candidates.slice(0,3), source:"local", meta:null };
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
 const prompt = `Player: ${playerData.name} | Trophies: ${playerData.trophies} | Arena: ${playerData.arena?.name} | King Level: ${playerData.expLevel}\n\nTop 3 decks:\n${deckSummaries}\n\nFor EACH deck return a JSON explanation. Return ONLY this JSON array, no markdown:\n[{"deckIndex":0,"winCondition":"1-2 sentences","synergies":["synergy 1","synergy 2"],"attack":"2 sentences","defense":"2 sentences","counters":["c1","c2","c3"],"upgradePriority":[{"card":"Name","reason":"why","impact":"high"}]}]`;
 const response = await callAI("You are an expert Clash Royale coach 2026. Return only valid JSON array, no markdown.", prompt);
 const clean = response.replace(/```json|```/g,"").trim();
 const match = clean.match(/\[[\s\S]*\]/);
 if (!match) throw new Error("Could not parse AI explanation");
 return JSON.parse(match[0]);
}

const RARITY_COLORS = { common:"#90a4ae",rare:"#42a5f5",epic:"#ab47bc",legendary:"#ffd700",champion:"#ff6f00" };
const TYPE_ICONS = { troop:"⚔️",spell:"✨",building:"🏰",champion:"👑" };

function ElixirBadge({ value }) {
 const colors = {1:"#e91e63",2:"#9c27b0",3:"#3f51b5",4:"#2196f3",5:"#00bcd4",6:"#4caf50",7:"#ff9800",8:"#f44336",9:"#b71c1c",10:"#7f0000"};
 return <div style={{background:colors[value]||"#555",color:"#fff",borderRadius:"50%",width:18,height:18,display:"flex",alignItems:"center",justifyContent:"center",fontSize:10,fontWeight:800,flexShrink:0}}>{value}</div>;
}

function CardTile({ card, selected, onClick }) {
 const col = RARITY_COLORS[card.rarity?.toLowerCase()]||"#888";
 return (
   <div onClick={onClick} style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:2,padding:"8px 4px",background:selected?`${col}25`:"rgba(255,255,255,0.04)",border:`2px solid ${selected?col:"rgba(255,255,255,0.08)"}`,borderRadius:10,cursor:"pointer",transition:"all 0.15s",boxShadow:selected?`0 0 14px ${col}55`:"none",position:"relative",minHeight:80}}>
     {card.iconUrls?.medium?<img src={card.iconUrls.medium} alt={card.name} style={{width:44,height:44,objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:22}}>{TYPE_ICONS[card.type?.toLowerCase()]||"🃏"}</div>}
     <div style={{fontSize:9,color:selected?col:"#666",fontWeight:selected?700:400,textAlign:"center",lineHeight:1.2,wordBreak:"break-word",width:"100%"}}>{card.name}</div>
     <div style={{position:"absolute",top:4,left:4}}><ElixirBadge value={card.elixirCost||"?"}/></div>
     {card.level&&<div style={{position:"absolute",top:4,right:4,fontSize:8,background:"rgba(0,0,0,0.8)",borderRadius:3,padding:"1px 3px",color:"#ffd700",fontWeight:700}}>L{card.level}</div>}
     {card.evolutionLevel>0&&<div style={{position:"absolute",bottom:20,right:3,fontSize:7,color:"#00e5ff",fontWeight:800}}>EVO</div>}
   </div>
 );
}

function DeckCardSlot({ card, onRemove }) {
 if (!card) return <div style={{aspectRatio:"3/4",border:"2px dashed rgba(255,255,255,0.08)",borderRadius:8,display:"flex",alignItems:"center",justifyContent:"center",color:"rgba(255,255,255,0.12)",fontSize:20}}>+</div>;
 const col = RARITY_COLORS[card.rarity?.toLowerCase()]||"#888";
 return (
   <div onClick={onRemove} style={{aspectRatio:"3/4",background:`linear-gradient(145deg,${col}25,${col}08)`,border:`2px solid ${col}66`,borderRadius:8,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",cursor:"pointer",padding:3,gap:2,position:"relative"}}>
     {card.iconUrls?.medium?<img src={card.iconUrls.medium} alt={card.name} style={{width:"70%",objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:18}}>{TYPE_ICONS[card.type?.toLowerCase()]||"🃏"}</div>}
     <div style={{fontSize:7,color:col,fontWeight:700,textAlign:"center",lineHeight:1.1,wordBreak:"break-word",width:"100%"}}>{card.name}</div>
     <ElixirBadge value={card.elixirCost||"?"}/>
     <div style={{position:"absolute",top:2,right:2,color:"rgba(255,255,255,0.2)",fontSize:9}}>✕</div>
   </div>
 );
}

function Bubble({ msg }) {
 const isAI = msg.role==="assistant";
 return (
   <div style={{display:"flex",flexDirection:isAI?"row":"row-reverse",gap:8,alignItems:"flex-start",marginBottom:12}}>
     {isAI&&<div style={{width:30,height:30,borderRadius:"50%",background:"linear-gradient(135deg,#ff6f00,#e65100)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,flexShrink:0}}>🤖</div>}
     <div style={{maxWidth:"82%",background:isAI?"rgba(255,111,0,0.09)":"rgba(255,255,255,0.06)",border:`1px solid ${isAI?"rgba(255,111,0,0.25)":"rgba(255,255,255,0.08)"}`,borderRadius:isAI?"4px 14px 14px 14px":"14px 4px 14px 14px",padding:"10px 14px",fontSize:14,color:"#ddd",lineHeight:1.65,whiteSpace:"pre-wrap"}}>
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
 const upgrades = explanation?.upgradePriority||[];
 return (
   <div style={{background:"rgba(255,255,255,0.025)",border:`1px solid ${col}33`,borderRadius:14,padding:16,marginBottom:16}}>
     <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:10,gap:8}}>
       <div style={{minWidth:0}}>
         <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4,flexWrap:"wrap"}}>
           <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:22,color:col,lineHeight:1}}>#{index+1}</div>
           <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:16,color:"#ddd",letterSpacing:0.5,lineHeight:1}}>{deckData.name||"Meta Deck"}</div>
           {deckData.matchType==="partial"&&<div style={{fontSize:9,background:"rgba(255,152,0,0.15)",border:"1px solid rgba(255,152,0,0.3)",borderRadius:4,padding:"2px 6px",color:"#ffb74d"}}>ADAPTED</div>}
           {isLive&&<div style={{fontSize:9,background:"rgba(76,175,80,0.15)",border:"1px solid rgba(76,175,80,0.3)",borderRadius:4,padding:"2px 6px",color:"#81c784"}}>🔴 LIVE</div>}
         </div>
         <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
           <div style={{fontSize:11,background:`${tierCol}22`,border:`1px solid ${tierCol}55`,borderRadius:4,padding:"2px 8px",color:tierCol,fontWeight:800}}>{deckData.tier}</div>
           <div style={{fontSize:11,color:"#555"}}>{deckData.archetype||"Unknown"}</div>
           <div style={{fontSize:12,color:ratingColor,fontWeight:700}}>⭐ {deckData.powerRating}/100</div>
           {deckData.winRate!=null&&<div style={{fontSize:12,color:"#4caf50",fontWeight:700}}>📊 {deckData.winRate}% WR</div>}
           {deckData.battles!=null&&<div style={{fontSize:11,color:"#444"}}>{deckData.battles.toLocaleString()} battles</div>}
         </div>
       </div>
       <button onClick={()=>onSelect(deckData)} style={{padding:"9px 16px",background:`linear-gradient(135deg,${col},${col}88)`,border:"none",borderRadius:9,color:"#000",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:13,letterSpacing:1,flexShrink:0,fontWeight:800}}>USE</button>
     </div>

     <div style={{marginBottom:12}}>
       <div style={{height:5,background:"rgba(255,255,255,0.06)",borderRadius:3,overflow:"hidden"}}>
         <div style={{width:`${deckData.powerRating}%`,height:"100%",background:`linear-gradient(90deg,${ratingColor},${ratingColor}88)`,borderRadius:3,boxShadow:`0 0 8px ${ratingColor}`}}/>
       </div>
     </div>

     {deckData.substituted&&(
       <div style={{fontSize:11,color:"#ffb74d",background:"rgba(255,152,0,0.08)",border:"1px solid rgba(255,152,0,0.2)",borderRadius:6,padding:"5px 10px",marginBottom:10}}>
         ⚠️ Missing <b>{deckData.substituted.original}</b> → replaced with <b>{deckData.substituted.replacement}</b>
       </div>
     )}

     <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:6,marginBottom:12}}>
       {deckData.cards.map((cardName,i)=>{
         const card = allCards.find(c=>c.name.toLowerCase()===cardName.toLowerCase());
         const rcol = card?(RARITY_COLORS[card.rarity?.toLowerCase()]||"#888"):"#444";
         const lfm = card?(card.maxLevel||14)-(card.level||1):99;
         return (
           <div key={i} style={{aspectRatio:"3/4",background:card?`linear-gradient(145deg,${rcol}20,${rcol}08)`:"rgba(255,50,50,0.1)",border:`1.5px solid ${card?rcol+"55":"rgba(255,50,50,0.3)"}`,borderRadius:8,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:3,gap:1,position:"relative"}}>
             {card?.iconUrls?.medium?<img src={card.iconUrls.medium} alt={card.name} style={{width:"78%",objectFit:"contain"}} onError={e=>{e.target.style.display="none"}}/>:<div style={{fontSize:16}}>{card?TYPE_ICONS[card.type?.toLowerCase()]||"🃏":"❌"}</div>}
             <div style={{fontSize:7,color:card?rcol:"#ff5252",fontWeight:700,textAlign:"center",lineHeight:1.1,wordBreak:"break-word",width:"100%"}}>{cardName}</div>
             {card&&<div style={{fontSize:7,color:lfm<=1?"#4caf50":lfm<=3?"#ffd700":"#ff5252",fontWeight:700}}>L{card.level}</div>}
             {card?.evolutionLevel>0&&<div style={{position:"absolute",top:2,right:2,fontSize:7,color:"#00e5ff",fontWeight:800}}>⚡</div>}
           </div>
         );
       })}
     </div>

     {explanation?(
       <>
         <div style={{fontSize:12,color:"#777",marginBottom:10,padding:"8px 10px",background:"rgba(255,255,255,0.025)",borderRadius:8}}>
           🎯 <span style={{color:"#bbb"}}>{explanation.winCondition}</span>
         </div>
         {explanation.synergies?.length>0&&(
           <div style={{marginBottom:10}}>
             <div style={{fontSize:10,color:col,fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:5}}>⚡ SYNERGIES</div>
             {explanation.synergies.map((s,i)=>(
               <div key={i} style={{fontSize:12,color:"#555",padding:"3px 0",display:"flex",gap:6}}>
                 <span style={{color:col,flexShrink:0}}>→</span>{s}
               </div>
             ))}
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
             {explanation.counters.map((c,i)=>(
               <span key={i} style={{fontSize:11,background:"rgba(255,50,50,0.08)",border:"1px solid rgba(255,50,50,0.2)",borderRadius:5,padding:"2px 8px",color:"#ff5252"}}>{c}</span>
             ))}
           </div>
         )}
         {upgrades.length>0&&(
           <div style={{borderTop:"1px solid rgba(255,255,255,0.05)",paddingTop:10}}>
             <div style={{fontSize:10,color:"#ffd700",fontWeight:700,textTransform:"uppercase",letterSpacing:1,marginBottom:6}}>⬆️ UPGRADE PRIORITY</div>
             {upgrades.map((u,i)=>(
               <div key={i} style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}>
                 <div style={{fontSize:10,color:"#ffd700",width:16,textAlign:"center",fontWeight:800}}>{i+1}</div>
                 <div style={{flex:1}}>
                   <span style={{fontSize:12,color:"#ffd700",fontWeight:700}}>{u.card}</span>
                   <span style={{fontSize:11,color:"#444",marginLeft:6}}>{u.reason}</span>
                 </div>
                 <div style={{fontSize:9,padding:"2px 6px",background:u.impact==="high"?"rgba(76,175,80,0.15)":"rgba(255,152,0,0.15)",border:`1px solid ${u.impact==="high"?"rgba(76,175,80,0.3)":"rgba(255,152,0,0.3)"}`,borderRadius:4,color:u.impact==="high"?"#81c784":"#ffb74d",fontWeight:700,textTransform:"uppercase",flexShrink:0}}>{u.impact}</div>
               </div>
             ))}
           </div>
         )}
       </>
     ):(
       <div style={{fontSize:12,color:"#333",fontStyle:"italic"}}>Loading AI analysis...</div>
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
 const [tab, setTab] = useState("home");
 const [messages, setMessages] = useState([{role:"assistant",content:"👑 Enter your #PLAYERTAG to get started — I'll find your best meta decks with real win rates!"}]);
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
   setFetching(true); setError(""); setFetchStatus("Fetching profile...");
   try {
     const data = await crFetch(tag);
     if (!data.name) throw new Error("Player not found.");
     setPlayer(data);
     const cards = (data.cards||[]).sort((a,b)=>(a.elixirCost||0)-(b.elixirCost||0));
     setAllCards(cards);
     setDeck([]); setDeckOptions([]); setExplanations([]);
     setFetchStatus("Checking live battle data...");
     const { decks, source, meta } = await fetchDecks(data, cards);
     setDeckOptions(decks);
     setDataSource(source);
     setDbMeta(meta);
     setTab("decks");
     setFetchStatus("AI analyzing your decks...");
     const explanationData = await explainTopDecks(decks, data);
     setExplanations(explanationData);
     setFetchStatus("");
     const top = decks[0];
     setMessages([{role:"assistant",content:`✅ Linked **${data.name}**!\n\n🏆 ${data.trophies?.toLocaleString()} trophies · ${data.arena?.name} · King Level ${data.expLevel}\n\nYour #1 deck: **${top?.name||"Meta Deck"}** (${top?.tier} tier, ${top?.powerRating}/100${top?.winRate!=null?`, ${top.winRate}% WR`:""})\n\nTap ⚡ Decks to see the full breakdown!`}]);
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
     {role:"assistant",content:`🔥 **${deckData.name}** locked in! ${deckData.tier} · ${deckData.powerRating}/100${deckData.winRate!=null?` · ${deckData.winRate}% WR`:""}\n\n${expl?.winCondition||"Use your win condition aggressively!"}\n\nAsk me anything!`}
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
   } catch(e) { setMessages([...newHistory,{role:"assistant",content:`⚠️ Error: ${e.message}`}]); }
   setChatLoading(false); scrollBottom();
 };

 const filtered = allCards.filter(c=>{
   const ms = c.name.toLowerCase().includes(search.toLowerCase());
   const mt = filterType==="all"||c.type?.toLowerCase()===filterType;
   return ms&&mt;
 });

 const avgElixir = deck.length?(deck.reduce((s,c)=>s+(c.elixirCost||0),0)/deck.length).toFixed(1):0;
 const deckPower = deck.length>0?scoreDeckLocal(deck):0;
 const quickPrompts = ["How do I play this?","What counters this?","Upgrade priority?","Rate my deck","Best hero?"];

 return (
   <div style={{minHeight:"100vh",minHeight:"100dvh",background:"#08080f",color:"#e0e0e0",fontFamily:"'Rajdhani','Oswald',sans-serif",display:"flex",flexDirection:"column",maxWidth:480,margin:"0 auto",position:"relative"}}>
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
           <div style={{fontSize:8,color:"#333",letterSpacing:1,textTransform:"uppercase"}}>Live Data · AI Coach</div>
         </div>
       </div>
       {player?(
         <div style={{display:"flex",alignItems:"center",gap:8,background:"rgba(255,111,0,0.08)",border:"1px solid rgba(255,111,0,0.2)",borderRadius:8,padding:"6px 10px"}}>
           <div style={{minWidth:0}}>
             <div style={{fontSize:12,fontWeight:700,color:"#ff9a40",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis",maxWidth:100}}>{player.name}</div>
             <div style={{fontSize:9,color:"#444"}}>{player.trophies?.toLocaleString()} 🏆</div>
           </div>
           <button onClick={()=>{setPlayer(null);setAllCards([]);setDeck([]);setDeckOptions([]);setExplanations([]);setTagInput("");setTab("home");}} style={{background:"rgba(255,50,50,0.1)",border:"1px solid rgba(255,50,50,0.2)",borderRadius:4,color:"#ff5252",fontSize:9,cursor:"pointer",padding:"2px 6px",fontFamily:"'Rajdhani',sans-serif",fontWeight:700}}>✕</button>
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

     {/* STATUS BARS */}
     {fetchStatus&&<div style={{background:"rgba(255,111,0,0.06)",borderBottom:"1px solid rgba(255,111,0,0.12)",color:"#cc7a30",padding:"5px 16px",fontSize:11,flexShrink:0}}>⏳ {fetchStatus}</div>}
     {error&&<div style={{background:"rgba(255,50,50,0.07)",borderBottom:"1px solid rgba(255,50,50,0.15)",color:"#ff5252",padding:"5px 16px",fontSize:11,flexShrink:0}}>⚠️ {error}</div>}
     {dataSource&&!fetchStatus&&(
       <div style={{background:dataSource==="live"?"rgba(76,175,80,0.06)":"rgba(255,111,0,0.04)",borderBottom:`1px solid ${dataSource==="live"?"rgba(76,175,80,0.15)":"rgba(255,111,0,0.1)"}`,color:dataSource==="live"?"#66bb6a":"#555",padding:"4px 16px",fontSize:10,flexShrink:0}}>
         {dataSource==="live"?`🔴 LIVE · ${dbMeta?.battles?.toLocaleString()||"?"} battles · ${dbMeta?.totalDecks?.toLocaleString()||"?"} decks`:"📋 Meta engine · Live DB building..."}
       </div>
     )}

     {/* MAIN CONTENT */}
     <div style={{flex:1,overflow:"hidden",display:"flex",flexDirection:"column"}}>

       {tab==="home"&&(
         <div style={{flex:1,overflowY:"auto",padding:20}}>
           <div style={{textAlign:"center",paddingTop:20,paddingBottom:30}}>
             <div style={{fontSize:48,marginBottom:8}}>👑</div>
             <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:32,letterSpacing:3,color:"#ff6f00",marginBottom:4}}>ROYALE DECK AI</div>
             <div style={{color:"#333",fontSize:13,marginBottom:30}}>AI-powered deck builder · Live win rates</div>
             <div style={{background:"rgba(255,111,0,0.05)",border:"1px solid rgba(255,111,0,0.15)",borderRadius:14,padding:20,textAlign:"left"}}>
               <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:16,color:"#ff9a40",letterSpacing:1,marginBottom:12}}>HOW IT WORKS</div>
               {["Enter your #PLAYERTAG and tap LINK","Live win rates from real battle data","3 optimized decks scored by synergy + levels","AI explains attack, defense and counters","Chat with AI coach for matchup tips"].map((s,i)=>(
                 <div key={i} style={{display:"flex",gap:12,padding:"8px 0",borderBottom:"1px solid rgba(255,255,255,0.04)",fontSize:13,color:"#3a3a3a",alignItems:"center"}}>
                   <div style={{width:24,height:24,borderRadius:"50%",background:"rgba(255,111,0,0.15)",border:"1px solid rgba(255,111,0,0.3)",display:"flex",alignItems:"center",justifyContent:"center",color:"#ff6f00",fontWeight:800,fontSize:11,flexShrink:0}}>{i+1}</div>
                   {s}
                 </div>
               ))}
             </div>
           </div>
         </div>
       )}

       {tab==="decks"&&(
         <div style={{flex:1,overflowY:"auto",padding:16}}>
           <div style={{fontFamily:"'Bebas Neue',sans-serif",fontSize:22,letterSpacing:2,color:"#ff6f00",marginBottom:2}}>YOUR META DECKS</div>
           <div style={{color:"#333",fontSize:11,marginBottom:14}}>{dataSource==="live"?"Ranked by real win rate":"Ranked by meta score + synergy"} · Tap USE to auto-fill</div>
           {!player?(
             <div style={{textAlign:"center",color:"#222",paddingTop:40,fontSize:13}}>
               <div style={{fontSize:32,marginBottom:8}}>🔗</div>Link your account first
             </div>
           ):deckOptions.length===0?(
             <div style={{textAlign:"center",color:"#333",paddingTop:40,fontSize:13}}>
               <div style={{fontSize:32,marginBottom:8}}>⏳</div>{fetchStatus||"Generating..."}
             </div>
           ):(
             deckOptions.map((d,i)=>(
               <DeckOption key={i} deckData={{...d,source:dataSource}} explanation={explanations[i]} allCards={allCards} onSelect={selectDeck} index={i}/>
             ))
           )}
         </div>
       )}

       {tab==="build"&&(
         <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
           <div style={{padding:"12px 16px 8px",background:"rgba(255,255,255,0.01)",borderBottom:"1px solid rgba(255,255,255,0.05)"}}>
             <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
               <div style={{fontFamily:"'Bebas Neue',sans-serif",letterSpacing:1,color:"#ff6f00",fontSize:14}}>DECK {deck.length}/8</div>
               <div style={{display:"flex",gap:8,alignItems:"center"}}>
                 {deck.length>0&&(
                   <>
                     <div style={{fontSize:11,color:getTierColor(getTier(deckPower)),fontWeight:800}}>{getTier(deckPower)} · {deckPower}/100</div>
                     <div style={{fontSize:11,color:"#555"}}>⚡ {avgElixir}</div>
                     <button onClick={()=>setDeck([])} style={{background:"rgba(255,50,50,0.09)",border:"1px solid rgba(255,50,50,0.18)",borderRadius:4,color:"#ff5252",fontSize:9,cursor:"pointer",padding:"2px 7px",fontFamily:"'Rajdhani',sans-serif",fontWeight:700}}>CLEAR</button>
                   </>
                 )}
               </div>
             </div>
             <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:6}}>
               {Array(8).fill(null).map((_,i)=><DeckCardSlot key={i} card={deck[i]} onRemove={()=>deck[i]&&toggleCard(deck[i])}/>)}
             </div>
             {deck.length===8&&(
               <button onClick={()=>{setTab("chat");sendMessage("Full deck analysis: tier, synergies, win condition, counters, upgrade priority.");}} style={{marginTop:8,width:"100%",padding:"10px",background:"linear-gradient(135deg,#ff6f00,#e65100)",border:"none",borderRadius:9,color:"#fff",cursor:"pointer",fontFamily:"'Bebas Neue',sans-serif",fontSize:13,letterSpacing:1.5}}>🤖 AI ANALYZE THIS DECK</button>
             )}
           </div>
           <div style={{padding:"8px 16px 6px",borderBottom:"1px solid rgba(255,255,255,0.05)"}}>
             <input value={search} onChange={e=>setSearch(e.target.value)} placeholder={player?"Search cards...":"Link account to see cards"} disabled={!player}
               style={{width:"100%",background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.07)",borderRadius:8,padding:"8px 12px",color:"#ddd",fontFamily:"'Rajdhani',sans-serif",fontSize:13,outline:"none",marginBottom:6}}/>
             <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
               {["all","troop","spell","building","champion"].map(t=>(
                 <button key={t} onClick={()=>setFilterType(t)} style={{padding:"3px 8px",background:filterType===t?"rgba(255,111,0,0.14)":"transparent",border:`1px solid ${filterType===t?"#ff6f00":"rgba(255,255,255,0.06)"}`,borderRadius:5,color:filterType===t?"#ff6f00":"#333",cursor:"pointer",fontSize:10,fontFamily:"'Rajdhani',sans-serif",fontWeight:700,textTransform:"uppercase"}}>{t}</button>
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
             <textarea value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMessage();}}} placeholder="Ask about deck, counters, upgrades..." rows={2}
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
