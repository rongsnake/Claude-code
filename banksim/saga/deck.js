/* ------------------------------------------------------------------ the era decks
   "As it might have been": only structural events and the epoch anchors keep
   their dates. Everything else is drawn from the era's deck: archetypes with
   a yearly hazard, odds that answer to what the house is doing, a rumour
   posted a turn ahead (sometimes false), the council's advice, and the real
   episode each one echoes as a footnote.

   The draw for the NEXT turn happens at the end of this one, so a rumour has
   a turn to be acted on: cut the court's loan, fill the till, close the far
   branch. What the card does when it lands depends on the house as it then
   stands. All draws use the game's seeded stream, so a seed replays.        */

const DECK=D.deck||[], COUNCIL=D.council||{};
const SEATS=['growth','prudence','court','conscience'];
const SEAT_NAME={growth:'Growth',prudence:'Prudence',court:'The court',conscience:'Conscience'};
const LTARGET={rialto:2.5,medici:3.0,princes:3.2,northern:3.5,country:5.0,lombard:8.0,basel:14.0};
const MAX_CARDS_PER_TURN=3;
/* Calibration dials (STYLISED), tuned by headless play so that a prudent house
   usually survives, an ambitious one can be designated and a reckless one dies,
   as with the dated history. hazard: multiplies a card's yearly hazard by its
   kind; odds: multiplies every odds weight (how much the house's conduct
   matters); size: multiplies the damage of defaults, shocks and panics. */
const DECK_TUNE={hazard:{choice:0.55,offer:0.7,sovereign_default:1.6,panic:1.4,shock:1.0,forced_loan:1.0},odds:1.6,size:{sovereign_default:1.15,panic:1.25,shock:1.0},decline:4,choiceGap:2};

function ensureDeckState(){
  if(!S.mode) S.mode='history';                 // games saved before the decks existed play on as they were
  S.deckFired=S.deckFired||{}; S.deckLast=S.deckLast||{};
  S.rumours=S.rumours||[]; S.pending=S.pending||[]; S.choices=S.choices||[]; S.dispatch=S.dispatch||[];
}
function cardById(id){ return DECK.find(c=>c.id===id); }
function courtName(sov){ const v=D.sovereigns[sov]; if(!v) return 'the court'; return sov==='emerging'?'a foreign government':v.name; }
function fillText(s,t){ if(!s) return ''; const court=t&&t.sov?courtName(t.sov):'the court'; const cname=t&&t.city?city(t.city).name:city(S.seat).name;
  return s.replace(/\{court\}/g,court).replace(/\{city\}/g,cname).replace(/^the /,m=>m) ; }
function capFirst(s){ return s?s.charAt(0).toUpperCase()+s.slice(1):s; }

/* ---- what the house is doing: the signals a card's odds answer to (each about 0 to 1) */
function sovExposure(s){ let a=0; for(const cls of SOV_SCALAR) a+=((S.assets[cls]||{})[s])||0; return a/Math.max(equity(),1); }
function cityRatio(cid){ const att=cityAttribution(); if(!att[cid]) return 0; let pc=0; for(const k of PRIVATE) pc+=amount(k); const base=baseProsperity(cid); if(base<=0.02) return 0; return pc*att[cid]/(0.3*pool(S.year)*base); }
function signal(name,t){
  switch(name){
    case 'sov_exposure': return t&&t.sov?clamp(sovExposure(t.sov),0,2):0;
    case 'city_heat': return t&&t.city?clamp(cityRatio(t.city)/1.6,0,2):0;
    case 'leverage': { const L=liabilities()/Math.max(equity(),1); return clamp(L/(LTARGET[era().id]||5)-1,0,2); }
    case 'thin_till': { const r=S.assets.cash/Math.max(liabilities(),1); return clamp((0.2-r)/0.2,0,1); }
    case 'far_branches': return hasTech('telegraph')?0:branchIds().filter(c=>distFromSeat(c)>400).length/3;
    case 'trading_book': return clamp((S.assets.trading_book||0)/Math.max(totalAssets(),1)/0.2,0,2);
    case 'low_standing': return clamp((50-S.standing.merchants)/50,0,1);
    case 'fame': { const top=Math.max(1,...D.rivals.filter(rivalActive).map(rivalDeposits)); return clamp(S.funding.deposits/top,0,1.5); }
    case 'many_branches': return branchIds().length/6;
  } return 0; }

/* ---- who a card falls on */
function pickWeighted(items){ const tot=items.reduce((a,b)=>a+b[1],0); if(tot<=0) return null; let r=rng()*tot; for(const [k,w] of items){ r-=w; if(r<=0) return k; } return items[items.length-1][0]; }
function knownOpen(cid){ const cs=S.cityState[cid]; return cs&&cs.open!==false&&!cs.sacked&&S.year>=(city(cid).opens||1300)&&isKnown(cid); }
function resolveTarget(c){
  switch(c.target){
    case 'lent_sovereign': { const items=Object.keys(D.sovereigns).filter(courtActive).map(s=>[s,sovExposure(s)]).filter(x=>x[1]>0.002);
      if(items.length) return {sov:pickWeighted(items)};
      const weak=Object.keys(D.sovereigns).filter(s=>courtActive(s)&&(D.sovereigns[s].reliability??0.7)<0.7&&knownOpen(sovSeat(s)));
      return weak.length?{sov:weak[Math.floor(rng()*weak.length)],newsOnly:true}:null; }
    case 'reachable_sovereign': { const r=[...sovereignsReachable()].filter(s=>D.sovereigns[s]&&courtActive(s)); return r.length?{sov:r[Math.floor(rng()*r.length)]}:null; }
    case 'seat_sovereign': return {sov:seatSovereign(),city:S.seat};
    case 'branch_city': { const att=cityAttribution(); const items=Object.entries(att).filter(([c])=>S.branches[c]); return {city:pickWeighted(items)||S.seat}; }
    case 'seat': return {city:S.seat};
    case 'cities': { const ok=(c.cities||[]).filter(knownOpen); if(!ok.length) return null; const mine=ok.filter(x=>S.branches[x]); const pool2=mine.length&&rng()<0.6?mine:ok; return {city:pool2[Math.floor(rng()*pool2.length)]}; }
    default: return {};
  } }
function cardEligible(c){ const E=era(); if(c.era!==E.id) return false; const w=c.window; if(w&&(S.year<w[0]||S.year>=w[1])) return false;
  if(c.once&&S.deckFired[c.id]) return false; if(c.cooldown&&S.deckLast[c.id]!=null&&S.year-S.deckLast[c.id]<c.cooldown) return false; return true; }
function cardKind(c){ return c.choice&&c.choice.length?'choice':((c.effects||[])[0]||{}).type||'flavour'; }
function cardProb(c,t,years){ let m=1; for(const o of (c.odds||[])) m*=1+(o.weight||0)*DECK_TUNE.odds*signal(o.signal,t); const h=Math.min(0.5,(c.hazard||0)*(DECK_TUNE.hazard[cardKind(c)]??1)*m); return 1-Math.pow(1-h,years); }

/* ---- the draw for the coming turn, made at the end of this one */
function deckPredraw(){
  ensureDeckState(); S.rumours=[]; S.pending=[]; if(S.mode!=='deck'||!S.alive||S.year>=2027) return;
  const years=era().turn_years; const chosen=[]; let choiceTaken=false;
  for(const c of DECK){ if(!cardEligible(c)) continue; const t=resolveTarget(c); if(!t) continue; const p=cardProb(c,t,years); const hit=rng()<p;
    if(hit){ if(c.choice&&c.choice.length){ if(choiceTaken||(S.lastChoiceTurn!=null&&S.turn-S.lastChoiceTurn<DECK_TUNE.choiceGap)) continue; choiceTaken=true; } chosen.push({id:c.id,t,r:rng()}); }
    else if(c.rumour&&rng()<p*(c.rumour.false_rate||0.3)*0.8) S.rumours.push({id:c.id,t,real:false}); }
  chosen.sort((a,b)=>a.r-b.r); for(const x of chosen.slice(0,MAX_CARDS_PER_TURN)){ S.pending.push({id:x.id,t:x.t}); const c=cardById(x.id); if(c.choice&&c.choice.length) S.lastChoiceTurn=S.turn; if(c.rumour&&rng()<0.6) S.rumours.push({id:x.id,t:x.t,real:true}); }
  // the street does not say which rumours are true
  S.rumours.sort((a,b)=>(a.id<b.id?-1:1)); if(S.rumours.length>3) S.rumours.length=3;
}

/* ---- the turn: pending cards land */
function deckTurn(years,ctx){
  ensureDeckState(); S.dispatch=[]; if(S.mode!=='deck') return; const fired=S.pending; S.pending=[]; S.rumours=[];
  for(const p of fired){ const c=cardById(p.id); if(!c) continue; let t=p.t; if(t&&t.sov&&!courtActive(t.sov)) t=resolveTarget(c); if(!t) continue;
    S.deckFired[c.id]=(S.deckFired[c.id]||0)+1; S.deckLast[c.id]=S.year;
    const yr=S.year+Math.floor(rng()*years);
    if(c.choice&&c.choice.length){ S.choices.push({id:c.id,t,year:yr}); log(yr,capFirst(fillText(c.title,t)),fillText(c.text,t),'hist','ARCHETYPE'); S.log[0].precedent=c.precedent; S.dispatch.push({id:c.id,t,year:yr,choice:true}); fx({k:'news',year:yr,title:capFirst(fillText(c.title,t)),tone:'hist',city:t.city,sov:t.sov}); continue; }
    applyCard(c,t,yr,ctx); S.dispatch.push({id:c.id,t,year:yr}); }
}
function cardEvent(c,f,t,yr){ const e={year:yr,id:'deck:'+c.id,title:capFirst(fillText(c.title,t)),text:fillText(c.text,t),provenance:'ARCHETYPE',effect:{}};
  const cities=t.city?[t.city]:(t.sov?[sovSeat(t.sov)]:null);
  switch(f.type){
    case 'sovereign_default': e.effect={type:'sovereign_default',sovereign:t.sov,haircut:Math.min(0.95,f.haircut*DECK_TUNE.size.sovereign_default)}; break;
    case 'offer': e.effect={type:'offer',sovereign:t.sov||seatSovereign(),size:f.size,yield:f.yield,turns:f.turns||2}; break;
    case 'forced_loan': e.effect={type:'forced_loan',sovereign:t.sov||seatSovereign(),share:f.share,yield:f.yield}; break;
    case 'shock': e.effect={type:'shock',kind:f.kind,size:f.size*DECK_TUNE.size.shock,cities:cities||undefined}; if(f.panic) e.effect.panic=f.panic*DECK_TUNE.size.panic; break;
    case 'panic': e.effect={type:'panic',size:f.size*DECK_TUNE.size.panic,cities:cities||undefined}; break;
    default: e.effect=Object.assign({},f,{city:t.city||S.seat,sovereign:t.sov});
  } e.art=c.art; return e; }
function applyCard(c,t,yr,ctx){ const effs=(c.effects&&c.effects.length?c.effects:[{type:'flavour'}]);
  effs.forEach((f,i)=>{ if(t.newsOnly&&f.type==='sovereign_default'){ /* the court defaults on others; the house is not exposed */ }
    const e=cardEvent(c,f,t,yr); const n0=S.offers.length; applyEvent(e,Object.assign({},ctx,{quiet:i>0})); if(S.offers.length>n0) S.offers[S.offers.length-1].deck=true; if(i===0&&S.log[0]&&S.log[0].title===e.title) S.log[0].precedent=c.precedent; });
  const k=artFx(c.art); if(k) fx({k,city:t.city||(t.sov?sovSeat(t.sov):S.seat)}); }
function resolveChoice(i,opt){ const ch=S.choices[i]; if(!ch) return false; const c=cardById(ch.id); const o=(c.choice||[])[opt]; if(!o){ S.choices.splice(i,1); return true; }
  for(const f of (o.effects||[])){ const e=cardEvent(c,f,ch.t,S.year); applyEvent(e,{shocks:[],defaults:[],addPanic:()=>{},quiet:true,immediate:true}); }
  log(S.year,'You chose: '+o.label,o.result||'','hist','ARCHETYPE'); S.choices.splice(i,1); save(); render(); return true; }
function autoOption(c){ const opts=c.choice||[]; if(!opts.length) return 0; const crown=S.standing.crown[seatSovereign()]??40;
  const hurt=o=>(o.effects||[]).reduce((a,f)=>a+(f.type==='standing'&&f.who==='crown'?Math.min(0,f.delta):0)+(f.type==='windfall'?0:0),0);
  const ok=opts.map((o,i)=>i).filter(i=>crown+hurt(opts[i])>=25); const pool=ok.length?ok:opts.map((o,i)=>i); return pool[Math.floor(rng()*pool.length)]; }
function settleChoices(){ while(S.choices&&S.choices.length){ const c=cardById(S.choices[0].id); resolveChoice(0,AUTOPLAY&&c?autoOption(c):0); } }
function artFx(a){ return {plague:'plague',war:'war',riot:'war',fire:'smoke',ship:'wreck',flood:'storm',harbour:'wreck',quake:'quake',gold:'coinsUp',coin:'coinsUp',grain:'storm'}[a]||null; }

/* ------------------------------------------------------------------ the council */
function councilFor(){ return COUNCIL[era().id]||null; }
function remarkKeys(seat){ const cash=S.assets.cash/Math.max(liabilities(),1), lev=signal('leverage'); let prince=0; for(const s in D.sovereigns) prince=Math.max(prince,sovExposure(s));
  const bubble=branchIds().some(c=>cityRatio(c)>1.2), far=signal('far_branches')>0, loss=S.lastProfit<0, good=S.lastProfit>0&&S.turn>0;
  const tech=D.techs.some(t=>!S.techs[t.id]&&techAvailable(t)), offer=S.offers.length>0, centre=S.centre!==S.seat;
  const k=[];
  if(seat==='growth'){ if(offer) k.push('court_offer'); if(cash>0.35) k.push('flush_till'); if(tech) k.push('new_tech'); if(centre) k.push('centre_moving'); if(loss) k.push('loss_turn'); if(good) k.push('good_turn'); }
  if(seat==='prudence'){ if(cash<0.12) k.push('thin_till'); if(lev>0.3) k.push('high_leverage'); if(prince>0.6) k.push('big_prince_exposure'); if(bubble) k.push('bubble_city'); if(far) k.push('far_branches'); if(loss) k.push('loss_turn'); }
  if(seat==='court'){ if(offer) k.push('court_offer'); if(centre) k.push('centre_moving'); if(prince>0.3) k.push('big_prince_exposure'); if(good) k.push('good_turn'); }
  if(seat==='conscience'){ if(prince>0.5) k.push('big_prince_exposure'); if(bubble) k.push('bubble_city'); if(good) k.push('good_turn'); if(loss) k.push('loss_turn'); if(tech) k.push('new_tech'); }
  k.push('quiet'); return k; }
function remarkFor(p,seat,i){ const R=p.remarks||{}; for(const k of remarkKeys(seat)){ const arr=R[k]; if(arr&&arr.length) return arr[(S.turn+i)%arr.length]; } return ''; }
function renderCouncil(){ const box=$('council'); if(!box) return; const C=councilFor(); if(!C){ box.innerHTML='<p class="muted small">The partners meet in silence.</p>'; return; }
  const st=styleFor(); const rum=(S.rumours||[]).map(r=>({r,c:cardById(r.id)})).filter(x=>x.c);
  box.innerHTML=SEATS.map((seat,i)=>{ const p=C[seat]; if(!p) return ''; let say=remarkFor(p,seat,i), on='';
      if(rum.length){ const x=rum[(S.turn+i)%rum.length]; const a=(x.c.advice||{})[seat]; if(a&&(i+S.turn)%2===0){ say=a; on=' <span class="on">on the rumour</span>'; } }
      return `<div class="adv" data-seat="${seat}"><div class="por">${portraitSVG(p.portrait||{},st,seat)}</div><div class="who"><b>${esc(p.name)}</b><span>${esc(p.title)} · ${SEAT_NAME[seat]}</span><q>${esc(say)}</q>${on}</div></div>`; }).join('')
   + (rum.length?`<div class="rumours"><div class="rh">The street says</div>${rum.map(x=>`<div class="rm"><span class="rm-c">${esc(x.r.t&&x.r.t.city?city(x.r.t.city).name:x.r.t&&x.r.t.sov?(D.sovereigns[x.r.t.sov].name.replace(/^the /,'')):'')}</span> ${esc(fillText(x.c.rumour.text,x.r.t))}</div>`).join('')}<div class="small faint">Some rumours are false. Each that is true lands next turn.</div></div>`:'');
  const pc=$('council-bios'); if(pc) pc.innerHTML=SEATS.map(s=>C[s]?`<div><b>${esc(C[s].name)}</b>, ${esc(C[s].title)}: ${esc(C[s].bio||'')}</div>`:'').join(''); }

/* ------------------------------------------------------------------ period style */
function styleFor(y){ y=y??S.year; return y<1600?'woodcut':y<1850?'engraving':y<1970?'newsprint':'terminal'; }

/* ---- portraits: a head and shoulders drawn from the council's description */
const SKIN={light:'#f1d3b8',olive:'#d8b07f',brown:'#a8744a',dark:'#6b4428'};
const HAIRC={black:'#1d1a17',brown:'#5a3a22',grey:'#9a968f',white:'#e8e4dc',auburn:'#8a3a1c',blond:'#d6b25e'};
function portraitSVG(p,st,seat){ const sk=SKIN[p.skin]||SKIN.light, hc=HAIRC[p.hair_colour]||HAIRC.brown, gc=p.colour||'#4a3a2a'; const old=p.age==='old', f=p.sex==='f';
  const ol=st==='terminal'?'none':'#1d1a17', sw=st==='woodcut'?2.2:st==='engraving'?1.1:st==='newsprint'?1.3:0;
  let s=`<svg viewBox="0 0 64 64" class="portrait st-${st}" role="img" aria-label="${esc(seat)}"><rect width="64" height="64" class="pbg"/>`;
  // shoulders and garment
  const g={robe:'M6 64 Q8 44 32 42 Q56 44 58 64Z',doublet:'M8 64 Q10 46 32 44 Q54 46 56 64Z',gown:'M4 64 Q6 44 32 42 Q58 44 60 64Z',habit:'M4 64 Q6 40 32 38 Q58 40 60 64Z',coat:'M7 64 Q9 45 32 43 Q55 45 57 64Z',frock_coat:'M7 64 Q9 45 32 43 Q55 45 57 64Z',suit:'M8 64 Q10 46 32 44 Q54 46 56 64Z',open_collar:'M8 64 Q10 46 32 44 Q54 46 56 64Z'}[p.garment]||'M8 64 Q10 46 32 44 Q54 46 56 64Z';
  s+=`<path d="${g}" fill="${gc}" stroke="${ol}" stroke-width="${sw}"/>`;
  if(['suit','frock_coat','coat'].includes(p.garment)) s+=`<path d="M26 44 L32 58 L38 44" fill="#f4efe6" stroke="${ol}" stroke-width="${sw*0.6}"/>`+(p.garment==='suit'?`<path d="M31 47 L33 47 L34 58 L32 61 L30 58Z" fill="#7a1f2a"/>`:'');
  if(p.garment==='doublet') s+=`<path d="M24 44 Q32 49 40 44" fill="none" stroke="#f4efe6" stroke-width="2.4"/>`;
  if(p.garment==='habit') s+=`<path d="M20 40 Q32 52 44 40" fill="none" stroke="${ol}" stroke-width="${sw}"/>`;
  // neck and head
  s+=`<rect x="27" y="36" width="10" height="9" fill="${sk}" stroke="${ol}" stroke-width="${sw*0.5}"/>`;
  s+=`<ellipse cx="32" cy="27" rx="${f?10:11}" ry="13" fill="${sk}" stroke="${ol}" stroke-width="${sw}"/>`;
  // hair
  const H={short:`<path d="M21 24 Q21 12 32 12 Q43 12 43 24 Q40 17 32 17 Q24 17 21 24Z" fill="${hc}"/>`,
    long:`<path d="M20 26 Q19 11 32 11 Q45 11 44 26 L46 42 Q42 36 41 24 Q38 17 32 17 Q26 17 23 24 Q22 36 18 42Z" fill="${hc}"/>`,
    curled:`<g fill="${hc}"><circle cx="22" cy="20" r="4"/><circle cx="27" cy="14" r="4"/><circle cx="33" cy="12" r="4"/><circle cx="39" cy="14" r="4"/><circle cx="43" cy="20" r="4"/></g>`,
    tied:`<path d="M21 24 Q21 11 32 11 Q43 11 43 24 Q40 16 32 16 Q24 16 21 24Z" fill="${hc}"/><circle cx="44" cy="22" r="2.5" fill="${hc}"/>`,
    wig:`<path d="M18 34 Q14 10 32 9 Q50 10 46 34 Q44 26 42 22 Q38 16 32 16 Q26 16 22 22 Q20 26 18 34Z" fill="${p.hair_colour==='black'?'#e8e4dc':hc}"/><g fill="#e8e4dc"><circle cx="19" cy="30" r="3"/><circle cx="45" cy="30" r="3"/></g>`,
    bob:`<path d="M20 30 Q18 11 32 11 Q46 11 44 30 L41 30 Q42 18 32 17 Q22 18 23 30Z" fill="${hc}"/>`,
    bun:`<path d="M21 24 Q21 12 32 12 Q43 12 43 24 Q40 16 32 16 Q24 16 21 24Z" fill="${hc}"/><circle cx="32" cy="9" r="4.5" fill="${hc}"/>`}[p.hair]||'';
  s+=H;
  // face
  s+=`<g stroke="${st==='terminal'?'#3a2a1a':ol}" stroke-width="1.1" fill="none"><path d="M26.5 25.5 h3 M34.5 25.5 h3"/><path d="M32 27 L31 32 L33 32"/><path d="M28.5 35 Q32 ${old?35.6:36.6} 35.5 35"/>${old?'<path d="M24 22 Q26 21 28 22 M36 22 Q38 21 40 22" opacity=".6"/>':''}</g>`;
  const fh={beard:`<path d="M21.5 30 Q22 44 32 45 Q42 44 42.5 30 Q40 37 32 38 Q24 37 21.5 30Z" fill="${hc}"/>`,moustache:`<path d="M27 33 Q32 31 37 33 Q32 34.5 27 33Z" fill="${hc}"/>`,stubble:`<path d="M23 31 Q24 40 32 41 Q40 40 41 31" fill="${hc}" opacity=".25"/>`,whiskers:`<path d="M21 24 Q20 34 26 36 L26 30Z M43 24 Q44 34 38 36 L38 30Z" fill="${hc}"/>`}[p.facial_hair];
  if(fh&&!f) s+=fh;
  // headwear
  const hw={cappuccio:`<path d="M18 26 Q16 6 34 6 Q50 8 46 24 Q40 15 32 15 Q22 16 18 26Z" fill="#7a1f2a" stroke="${ol}" stroke-width="${sw}"/><path d="M44 12 Q56 18 54 34" fill="none" stroke="#7a1f2a" stroke-width="5"/>`,
    beret:`<path d="M18 18 Q22 6 36 7 Q50 9 46 18Z" fill="#1d1a17" stroke="${ol}" stroke-width="${sw*0.6}"/>`,
    coif:`<path d="M20 30 Q18 10 32 10 Q46 10 44 30 Q42 18 32 17 Q22 18 20 30Z" fill="#f4efe6" stroke="${ol}" stroke-width="${sw*0.7}"/>`,
    biretta:`<path d="M21 16 L22 7 L42 7 L43 16Z" fill="#1d1a17"/><circle cx="32" cy="5" r="2" fill="#1d1a17"/>`,
    tricorn:`<path d="M14 16 Q32 2 50 16 Q42 12 32 13 Q22 12 14 16Z" fill="#1d1a17"/>`,
    top_hat:`<rect x="22" y="1" width="20" height="13" fill="#1d1a17"/><rect x="17" y="13" width="30" height="3" rx="1.5" fill="#1d1a17"/>`,
    bowler:`<path d="M21 15 Q21 4 32 4 Q43 4 43 15Z" fill="#1d1a17"/><rect x="17" y="14" width="30" height="2.6" rx="1.3" fill="#1d1a17"/>`,
    skullcap:`<path d="M23 15 Q32 7 41 15Z" fill="#1d1a17"/>`,
    veil:`<path d="M18 40 Q14 10 32 9 Q50 10 46 40 Q42 22 32 18 Q22 22 18 40Z" fill="#2a2a3a"/>`}[p.headwear];
  if(hw) s+=hw;
  // what they carry
  const ac={spectacles:`<g fill="none" stroke="#1d1a17" stroke-width="1"><circle cx="28" cy="26" r="3.2"/><circle cx="36" cy="26" r="3.2"/><path d="M31.2 26 h1.6"/></g>`,
    chain:`<path d="M20 48 Q32 58 44 48" fill="none" stroke="#d6b25e" stroke-width="2"/>`,
    rosary:`<path d="M24 46 Q32 56 40 46" fill="none" stroke="#5a3a22" stroke-width="1.4" stroke-dasharray="1.5 1.5"/><path d="M32 54 v5 M30 56.5 h4" stroke="#5a3a22" stroke-width="1.2"/>`,
    quill:`<path d="M48 64 L56 40 Q58 46 50 64Z" fill="#f4efe6" stroke="${ol}" stroke-width=".8"/>`,
    ledger:`<rect x="40" y="50" width="16" height="12" fill="#7a1f2a" stroke="${ol}" stroke-width="1"/><path d="M42 52 h12" stroke="#d6b25e" stroke-width="1"/>`,
    pocket_watch:`<path d="M38 50 Q44 52 46 56" fill="none" stroke="#d6b25e" stroke-width="1"/><circle cx="46" cy="57" r="2.4" fill="#d6b25e"/>`,
    lanyard:`<path d="M27 45 L30 60 M37 45 L34 60" stroke="#2a78d6" stroke-width="1.2"/><rect x="29" y="58" width="6" height="5" fill="#f4efe6" stroke="#2a78d6" stroke-width=".6"/>`,
    tablet:`<rect x="40" y="48" width="14" height="14" rx="1.5" fill="#1d1a17"/><rect x="41.5" y="49.5" width="11" height="11" fill="#3a6aa0"/>`,
    pipe:`<path d="M36 34 Q42 36 42 40 L45 40 L45 36" fill="none" stroke="#5a3a22" stroke-width="1.6"/>`,
    seal_ring:`<circle cx="50" cy="58" r="2.2" fill="#d6b25e" stroke="${ol}" stroke-width=".6"/>`}[p.accessory];
  if(ac) s+=ac;
  return s+'</svg>'; }

/* ---- card art: a motif per kind of event, drawn in the age's manner */
const ART={
  crown:'<path d="M14 44 L12 22 L22 32 L32 16 L42 32 L52 22 L50 44Z"/><rect x="14" y="44" width="36" height="6"/><circle cx="32" cy="14" r="3"/>',
  ship:'<path d="M8 40 Q12 50 20 50 L46 50 Q54 48 58 38 L46 42 L18 42Z"/><path d="M30 42 V8 M30 10 L46 30 L30 30Z M30 14 L16 32 L30 32Z" class="lt"/><path d="M4 54 Q12 50 20 54 T36 54 T52 54 T64 54" class="ln"/>',
  plague:'<circle cx="32" cy="30" r="14" class="lt"/><path d="M24 26 h4 M36 26 h4 M26 38 Q32 33 38 38" class="ln"/><g><circle cx="12" cy="12" r="2.5"/><circle cx="52" cy="14" r="2"/><circle cx="10" cy="48" r="2.2"/><circle cx="54" cy="50" r="2.6"/><circle cx="20" cy="56" r="1.8"/><circle cx="46" cy="56" r="1.8"/></g>',
  fire:'<path d="M32 6 C44 20 52 28 48 42 C44 54 20 54 16 42 C12 30 22 26 24 16 C28 24 30 22 32 6Z"/><path d="M32 30 C38 36 39 40 37 46 C35 50 29 50 27 46 C25 41 29 37 32 30Z" class="lt"/>',
  war:'<path d="M12 52 L46 14 M18 52 L12 46 M10 50 L16 56" class="ln w"/><path d="M52 52 L18 14 M46 52 L52 46 M54 50 L48 56" class="ln w"/><path d="M42 12 L50 8 L46 16Z M22 12 L14 8 L18 16Z"/>',
  riot:'<g><circle cx="16" cy="24" r="5"/><circle cx="32" cy="20" r="6"/><circle cx="48" cy="24" r="5"/><path d="M8 54 Q8 32 16 32 Q24 32 24 54Z M22 54 Q22 28 32 28 Q42 28 42 54Z M40 54 Q40 32 48 32 Q56 32 56 54Z"/></g><path d="M46 6 V20 M42 10 L50 10" class="ln"/>',
  coin:'<circle cx="26" cy="34" r="16"/><circle cx="26" cy="34" r="11" class="lt"/><circle cx="42" cy="26" r="14" class="lt"/><path d="M42 18 V34 M37 22 H47 M37 30 H47" class="ln"/>',
  ledger:'<rect x="10" y="12" width="44" height="40" rx="2"/><path d="M32 12 V52" class="ln w"/><path d="M15 20 h13 M15 26 h13 M15 32 h13 M36 20 h13 M36 26 h13 M36 32 h9" class="ln lt2"/>',
  bubble:'<circle cx="24" cy="36" r="14" class="lt"/><circle cx="42" cy="22" r="10" class="lt"/><circle cx="48" cy="44" r="6" class="lt"/><path d="M18 30 Q20 26 24 25" class="ln"/><path d="M10 54 L20 48 L28 52 L40 38 L54 50" class="ln w"/>',
  quake:'<path d="M6 46 H22 L26 30 L30 56 L34 24 L38 50 L42 40 H58" class="ln w"/><path d="M14 20 h10 v10 h-10Z M40 14 l10 3 -3 10 -10 -3Z" class="lt"/>',
  flood:'<path d="M4 30 Q12 24 20 30 T36 30 T52 30 T64 30 V64 H4Z"/><path d="M4 42 Q12 36 20 42 T36 42 T52 42 T64 42" class="ln lt2"/><path d="M18 22 L24 10 L30 22Z" class="lt"/>',
  letter:'<rect x="8" y="16" width="48" height="32" rx="2" class="lt"/><path d="M8 16 L32 36 L56 16" class="ln"/><circle cx="32" cy="38" r="5"/>',
  scales:'<path d="M32 8 V52 M18 52 H46 M12 18 H52" class="ln w"/><path d="M12 18 L6 34 H18Z M52 18 L46 34 H58Z" class="lt"/><path d="M4 34 Q12 42 20 34 M44 34 Q52 42 60 34"/>',
  cross:'<path d="M28 6 H36 V22 H52 V30 H36 V58 H28 V30 H12 V22 H28Z"/>',
  seal:'<circle cx="32" cy="30" r="16"/><circle cx="32" cy="30" r="10" class="lt"/><path d="M24 44 L20 58 L28 54 L32 60 L36 54 L44 58 L40 44" />',
  train:'<rect x="10" y="22" width="30" height="20"/><rect x="40" y="14" width="14" height="28"/><rect x="18" y="10" width="6" height="12"/><circle cx="18" cy="46" r="5" class="lt"/><circle cx="34" cy="46" r="5" class="lt"/><circle cx="48" cy="46" r="5" class="lt"/><path d="M4 54 H60" class="ln"/>',
  telegraph:'<path d="M12 58 V12 M52 58 V12 M6 16 H18 M46 16 H58" class="ln w"/><path d="M12 22 Q32 30 52 22 M12 28 Q32 36 52 28" class="ln"/><path d="M28 40 L34 46 L30 46 L36 54" class="ln"/>',
  screen:'<rect x="6" y="10" width="52" height="34" rx="2"/><path d="M12 36 L20 26 L28 30 L38 18 L52 24" class="ln lt2"/><path d="M24 52 H40 M32 44 V52" class="ln w"/>',
  factory:'<path d="M6 54 V30 L18 38 V30 L30 38 V30 L42 38 V18 H50 V54Z"/><path d="M44 14 Q46 8 52 8 Q58 6 60 2" class="ln"/>',
  gold:'<path d="M10 46 L18 34 H34 L42 46Z M26 34 L32 22 H48 L54 34Z"/><path d="M20 40 h12 M36 28 h10" class="ln lt2"/>',
  grain:'<path d="M32 58 V20" class="ln w"/><g><ellipse cx="26" cy="22" rx="4" ry="7" transform="rotate(-25 26 22)"/><ellipse cx="38" cy="22" rx="4" ry="7" transform="rotate(25 38 22)"/><ellipse cx="26" cy="34" rx="4" ry="7" transform="rotate(-25 26 34)"/><ellipse cx="38" cy="34" rx="4" ry="7" transform="rotate(25 38 34)"/><ellipse cx="32" cy="12" rx="3.5" ry="7"/></g>',
  harbour:'<path d="M4 44 H60 V60 H4Z" class="lt"/><path d="M8 44 V24 H22 V44 M42 44 V18 L50 12 L58 18 V44" /><path d="M26 40 L30 30 L34 40Z"/>',
};
function artSVG(key,st){ const a=ART[key]||ART.ledger; return `<svg viewBox="0 0 64 64" class="art st-${st}" aria-hidden="true"><defs><pattern id="ht-${st}" width="3" height="3" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r=".9" fill="currentColor"/></pattern><pattern id="hh-${st}" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><path d="M0 0V3" stroke="currentColor" stroke-width="1"/></pattern></defs><g class="mot">${a}</g></svg>`; }

/* ------------------------------------------------------------------ dispatches: this turn's cards */
function cardHTML(d,interactive){ const c=cardById(d.id); if(!c) return ''; const st=styleFor(d.year); const C=councilFor()||{};
  const advice=SEATS.map(s=>c.advice&&c.advice[s]&&C[s]?`<div class="cadv"><span class="cav">${portraitSVG(C[s].portrait||{},st,s)}</span><span><b>${esc(C[s].name.split(' ')[0])}</b> ${esc(c.advice[s])}</span></div>`:'').join('');
  const idx=interactive?S.choices.findIndex(x=>x.id===d.id):-1;
  const choices=(c.choice&&c.choice.length&&idx>=0)?`<div class="copts">${c.choice.map((o,j)=>`<button class="btn copt" data-ch="${idx}" data-opt="${j}"><b>${esc(o.label)}</b><span>${esc(o.result||'')}</span></button>`).join('')}</div>`:'';
  return `<article class="dcard st-${st}"><div class="dart">${artSVG(c.art,st)}</div><div class="dbody"><div class="dy">${d.year}${d.t&&d.t.city?' · '+esc(city(d.t.city).name):''}</div><h3>${esc(capFirst(fillText(c.title,d.t)))}</h3><p>${esc(fillText(c.text,d.t))}</p>${choices}<details class="dadv"><summary>The council</summary>${advice}</details><div class="dprec"><span>History remembers</span> ${esc(c.precedent||'')}${c.source?` <i>(${esc(c.source)})</i>`:''}</div></div></article>`; }
function showDispatches(done){ ensureDeckState(); const list=(S.dispatch||[]).slice(); S.dispatch=[]; save();
  if(AUTOPLAY||!list.length){ done&&done(); return; }
  const pend=()=>S.choices.length>0;
  const ys=list.map(d=>d.year), y0=Math.min(...ys), y1=Math.max(...ys);
  modal(`<div class="eyebrow">${y0===y1?y0:y0+'–'+y1} · dispatches</div><h2>${list.length===1?'News for the house':'News for the house: '+list.length+' dispatches'}</h2><div class="dcards">${list.map(d=>cardHTML(d,true)).join('')}</div><div class="acts"><button class="btn primary" id="d-ok"${pend()?' disabled':''}>${pend()?'Decide first':'To the ledger'}</button></div>`);
  const wire=()=>{ for(const b of $('modal-box').querySelectorAll('[data-ch]')) b.addEventListener('click',()=>{ resolveChoice(+b.dataset.ch,+b.dataset.opt); b.closest('.copts').innerHTML=`<div class="chosen">Decided: ${esc(b.querySelector('b').textContent)}</div>`; const ok=$('d-ok'); if(!pend()){ ok.disabled=false; ok.textContent='To the ledger'; } }); };
  wire(); $('d-ok').addEventListener('click',()=>{ if(pend()) return; $('modal').classList.remove('show'); done&&done(); }); }

/* ------------------------------------------------------------------ the seat, drawn */
function renderScene(){ const svg=$('scene'); if(!svg) return; const st=styleFor(), E=era().id, A=totalAssets(), n=clamp(Math.round(Math.log10(Math.max(A,10))*1.6),2,12);
  const kind=E==='rialto'||E==='medici'?'bench':E==='princes'||E==='northern'?'counting':E==='basel'?'floor':'hall'; const W=640,H=200;
  let s=`<rect width="${W}" height="${H}" class="sc-bg"/>`;
  const fig=(x,y,sc,c)=>`<g transform="translate(${x} ${y}) scale(${sc})" class="sc-fig"><circle cy="-30" r="7" fill="${c||'currentColor'}"/><path d="M-10 0 Q-11 -20 0 -21 Q11 -20 10 0Z" fill="${c||'currentColor'}"/></g>`;
  const pal=['#7a1f2a','#2f4f6f','#4a5a2a','#6a4a2a','#3a3a5a','#8a6417'];
  if(kind==='bench'){ // the porticoes of San Giacomo, a canal, the bench under its cloth
    for(let i=0;i<6;i++){ const x=40+i*100; s+=`<path d="M${x} 150 V70 Q${x+40} 30 ${x+80} 70 V150" class="sc-arch"/>`; }
    s+=`<rect x="0" y="150" width="${W}" height="50" class="sc-water"/><path d="M0 165 Q40 160 80 165 T160 165 T240 165 T320 165 T400 165 T480 165 T560 165 T640 165" class="sc-line"/>`;
    s+=`<path d="M60 186 Q100 176 150 184 L146 190 Q100 184 64 192Z" class="sc-dark"/>`;
    s+=`<path d="M220 100 H420 L410 82 H230Z" fill="#b0352a"/><path d="M250 82 L245 100 M290 82 V100 M330 82 V100 M370 82 V100 M400 82 L405 100" stroke="#f3e6c8" stroke-width="5"/><rect x="230" y="112" width="180" height="10" class="sc-dark"/><rect x="300" y="104" width="40" height="8" fill="#7a1f2a"/>`;
    for(let i=0;i<Math.min(n,8);i++) s+=fig(240+i*22,150,0.9,pal[i%pal.length]);
    for(let i=0;i<Math.min(n,6);i++) s+=`<circle cx="${380+i*5}" cy="${106-i*2}" r="4" fill="#e0b24a" stroke="#7a5a10"/>`;
  } else if(kind==='counting'){ // a merchant's counting house: beams, a window on the harbour, clerks at desks, the scales
    s+=`<path d="M0 30 H${W} M0 60 H${W}" class="sc-line"/>`; for(let i=0;i<8;i++) s+=`<rect x="${i*84}" y="0" width="14" height="30" class="sc-dark"/>`;
    s+=`<rect x="440" y="70" width="160" height="90" class="sc-win"/><path d="M520 70 V160 M440 115 H600" class="sc-line"/><path d="M460 140 Q480 128 500 140 L496 146 L464 146Z M540 150 L560 120 L566 150Z" class="sc-dark"/>`;
    for(let i=0;i<Math.min(n,7);i++){ const x=40+i*56; s+=`<rect x="${x-18}" y="140" width="40" height="8" class="sc-dark"/><path d="M${x-14} 148 V185 M${x+18} 148 V185" class="sc-line"/>`+fig(x,140,0.8,pal[i%pal.length]); }
    s+=`<path d="M410 90 V150 M390 96 H430 M390 96 L384 112 H396Z M430 96 L424 112 H436Z" class="sc-line w"/>`;
  } else if(kind==='hall'){ // a banking hall: columns, the counter and its grilles, a clock, customers
    for(let i=0;i<7;i++){ const x=30+i*96; s+=`<rect x="${x}" y="30" width="18" height="140" class="sc-col"/><rect x="${x-4}" y="24" width="26" height="8" class="sc-dark"/>`; }
    s+=`<rect x="0" y="16" width="${W}" height="10" class="sc-dark"/><circle cx="${W/2}" cy="60" r="18" class="sc-win"/><path d="M${W/2} 60 V48 M${W/2} 60 L${W/2+9} 64" class="sc-line w"/>`;
    s+=`<rect x="60" y="120" width="520" height="50" class="sc-dark"/>`; for(let i=0;i<10;i++) s+=`<path d="M${80+i*52} 92 V120" class="sc-line"/>`; s+=`<path d="M60 92 H580" class="sc-line"/>`;
    for(let i=0;i<Math.min(n,9);i++) s+=fig(90+i*56,118,0.7,pal[i%pal.length]);
    for(let i=0;i<Math.min(n,7);i++) s+=fig(110+i*70,196,0.95,'#2a2a2a');
  } else { // a trading floor: rows of screens, a ticker, the towers outside
    s+=`<rect x="0" y="0" width="${W}" height="70" class="sc-win"/>`; for(let i=0;i<14;i++){ const h=20+((i*37)%45); s+=`<rect x="${i*48}" y="${70-h}" width="34" height="${h}" class="sc-dark"/>`; }
    s+=`<rect x="0" y="72" width="${W}" height="16" fill="#111"/><text x="8" y="84" class="sc-tick">${tickerText()}</text>`;
    for(let r=0;r<2;r++) for(let i=0;i<Math.min(n,10);i++){ const x=30+i*60, y=130+r*50; s+=`<rect x="${x}" y="${y-30}" width="22" height="16" fill="#0f2a3a" stroke="#3a7ab0"/><rect x="${x+24}" y="${y-30}" width="22" height="16" fill="#0f2a3a" stroke="#3a7ab0"/><rect x="${x-4}" y="${y-12}" width="56" height="5" class="sc-dark"/>`+fig(x+22,y+14,0.6,pal[(i+r)%pal.length]); }
  }
  // a run draws a crowd at the door
  const ranLately=S.log.slice(0,6).some(e=>e.year>=S.year-era().turn_years&&/A run|run on the house/i.test(e.text+' '+e.title));
  if(ranLately){ const cy=kind==='bench'?148:198; for(let i=0;i<10;i++) s+=fig(24+i*16,cy,0.65,'#3a2a2a'); }
  svg.innerHTML=s; svg.setAttribute('class','scene st-'+st);
  $('scene-cap').textContent=(kind==='bench'?'The bench':kind==='counting'?'The counting house':kind==='hall'?'The banking hall':'The trading floor')+' at '+city(S.seat).name+' · '+branchIds().length+' branch'+(branchIds().length>1?'es':'')+' · '+fmtMoney(totalAssets())+' of assets'; }
function tickerText(){ const xs=['GILT','BUND','UST10','EURUSD','GBPUSD','FTSE','SPX','ITRX XO','CDX IG','SONIA']; let t=''; for(let i=0;i<xs.length;i++){ const v=((S.turn*13+i*29)%97)/10-4.8; t+=xs[i]+' '+(v>=0?'▲':'▼')+Math.abs(v).toFixed(2)+'   '; } return t; }

/* ------------------------------------------------------------------ rumours on the map */
function drawRumours(){ if(!MAP.built) return; let L=MAP.L.rum; if(!L){ L=MAP.L.rum=sel('g',{class:'L-rum'},MAP.svg); }
  MAP.marks=MAP.marks.filter(m=>!m.rum); L.innerHTML='';
  for(const r of (S.rumours||[])){ const c=cardById(r.id); if(!c) continue; const cid=r.t&&r.t.city?r.t.city:(r.t&&r.t.sov?sovSeat(r.t.sov):null); if(!cid||!cxy(cid)) continue; const [x,y]=cxy(cid);
    const g=sel('g',{class:'rum'},L); sel('circle',{r:9,class:'rum-r'},g); const t=sel('text',{class:'rum-t','text-anchor':'middle',y:4},g); t.textContent='?'; sel('title',null,g).textContent='Rumour: '+fillText(c.rumour.text,r.t);
    MAP.marks.push({el:g,x:x+14,y:y-14,s:1,rum:true}); }
  rescale&&rescale(); }

/* ------------------------------------------------------------------ the mode chooser */
function chooseMode(after){ modal(`<div class="eyebrow">a new ledger</div><h2>Which history?</h2><p>Both start on a bench on the Rialto in 1300 and end with Basel 3.1 in 2027. The rules of each age, the cities, the rival houses and the great epochs (the Black Death, the fall of Constantinople, the South Sea, 1914, 1929, 2008) are the same in both.</p>
  <div class="modes"><button class="btn mode" data-mode="deck"><b>As it might have been</b><span>Each age deals its own cards, like Civ: a king's default, a run, a lost fleet, a mania. You know what the age can do, not when. What you do changes the odds. Rumours come a turn ahead, and some are false. Every card notes the real episode it echoes.</span></button>
  <button class="btn mode" data-mode="history"><b>As it happened</b><span>Every crisis on its real date: Edward III in 1343, Philip II in 1557, Overend Gurney in 1866. The chronicle as a teaching text.</span></button></div>`);
  for(const b of $('modal-box').querySelectorAll('[data-mode]')) b.addEventListener('click',()=>{ $('modal').classList.remove('show'); after(b.dataset.mode); }); }
