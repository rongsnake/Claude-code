/* ------------------------------------------------------------------ sound and art: wiring
   music.js (window.LedgerSound) and art.js (window.LedgerArt) know nothing of the game;
   this block connects them. Nothing here touches the game's random numbers or state,
   and every hook is a no-op in headless autoplay. */
const FX_SOUND={coins:'coins', chest:'coin', crowd:'crowd', fall:'gong', war:'cannon', storm:'storm', wreck:'storm', quake:'storm', open:'bell', burst:'seal'};
const FX_MOOD={crowd:'tension', war:'tension', plague:'tension', fall:'grief'};
function soundFor(f){ const L=window.LedgerSound; if(!L||AUTOPLAY) return;
  try{ if(f.k==='news') L.sfx(S.year>=1850?'telegraph':'page');
    else if(FX_SOUND[f.k]) L.sfx(FX_SOUND[f.k]);
    if(FX_MOOD[f.k]) L.mood(FX_MOOD[f.k]); else if(f.k==='coins'&&f.tone!=='bad') L.mood('triumph'); }catch(e){} }
function soundSync(){ const L=window.LedgerSound; if(!L) return;
  try{ L.setEra(era().id); L.setYear(S.year); if(!S.alive) L.mood('grief'); }catch(e){} }

(function wireSoundAndArt(){
  const L=window.LedgerSound, A=window.LedgerArt;
  if(L){ try{ L.init(); }catch(e){} }
  // music follows the year shown on the ledger
  const _render=render; render=function(){ const r=_render.apply(this,arguments); if(!AUTOPLAY) soundSync(); return r; };
  // the turn's playback ends calm unless the house fell
  const _finish=finishTurn; finishTurn=function(){ const r=_finish.apply(this,arguments); if(!AUTOPLAY&&L){ try{ L.mood(S.alive?'calm':'grief'); }catch(e){} } return r; };
  // a decision is sealed
  const _resolve=resolveChoice; resolveChoice=function(){ const r=_resolve.apply(this,arguments); if(!AUTOPLAY&&L){ try{ L.sfx('seal'); }catch(e){} } return r; };
  // a new age is announced in its own manner before its page opens
  if(A&&A.eraCard){ const _showEra=showEra; showEra=function(E){ if(AUTOPLAY){ return _showEra(E); } let done=false; const go=()=>{ if(done) return; done=true; _showEra(E); };
      try{ if(L) L.sfx('page'); A.eraCard(E,go); }catch(e){ go(); } }; }
  // the chart's decorations before 1700: sea monsters, a galleon and a cartouche, drawn in the rhumb layer
  // so the portolan style shows them and later charts hide them with it
  if(A&&A.portolanSymbols){ const _build=buildBoard; buildBoard=function(){ const r=_build.apply(this,arguments);
    try{ const svg=MAP.svg, NS='http://www.w3.org/2000/svg', defs=svg.querySelector('defs'); defs.insertAdjacentHTML('beforeend',A.portolanSymbols());
      const at=(lon,lat)=>[(lon+180)*G.kx,(90-lat)*G.units_per_degree];
      const put=(id,lon,lat,w,h,flip)=>{ const [x,y]=at(lon,lat); const u=document.createElementNS(NS,'use'); u.setAttribute('href','#'+id); u.setAttribute('width',w); u.setAttribute('height',h);
        u.setAttribute('transform',`translate(${(x-w/2).toFixed(1)} ${(y-h/2).toFixed(1)})${flip?` translate(${w} 0) scale(-1 1)`:''}`); u.setAttribute('class','pt-deco'); MAP.L.rhumb.appendChild(u); };
      put('s-monster',-28,44,150,75,false); put('s-monster',62,-8,140,70,true); put('s-monster',-38,22,120,60,true);
      put('s-galleon',-14,33,70,70,false); put('s-rose',-30,30,150,150,false); put('s-cartouche',-22,58,260,98,false);
    }catch(e){} return r; }; }
})();

window.LedgerUI={ boot(resumed){ const A=window.LedgerArt; if(!A||!A.titleScreen||AUTOPLAY) return;
  try{ A.titleScreen({hasSave:!!resumed,
    onContinue(){},
    onBegin(){ if(resumed) chooseMode(m=>startNew(undefined,m)); } }); }catch(e){} } };
