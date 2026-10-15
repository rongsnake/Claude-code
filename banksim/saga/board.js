/* ------------------------------------------------------------------ the board
   The map is the game board. It is drawn once (sea, land, the chart's lines)
   and redrawn in layers when the state changes (routes, fog, cities, the
   house's buildings, the rivals' banners, the moving pieces). A single
   animation frame loop moves the camera, the pieces and the turn's playback.

   Nothing here touches the game's random stream: the pieces' positions use
   Math.random, so animation can never change an outcome, and the headless
   autoplay skips playback altogether.                                         */
const G=D.geo, NS='http://www.w3.org/2000/svg';
const MAP={svg:null,L:{},vb:null,target:null,follow:true,px:0.33,lastPx:0,W:800,H:480,tokens:[],marks:[],sprites:[],fxq:[],playing:false,playDone:null,playT:0,playEnd:0,anim:true,last:0,routeGeom:[],cityEls:{},rivalEls:{},pop:null,built:false,drag:null,pointers:{}};
let AUTOPLAY=false;
try{ MAP.anim=localStorage.getItem('longledger.anim')!=='off'; }catch(e){}
const REDUCED=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);
const PRIVATE=['merchants','trade_bills','commodities','discount_market','acceptances','mortgages','industry','retail','trading_book'];
const LABEL_DIR={bruges:'w',london:'w',lisbon:'w',edinburgh:'w',genoa:'w',canton:'w',avignon:'s',rome:'s',seville:'s',zurich:'s',paris:'s',antwerp:'e',amsterdam:'n',hamburg:'e',venice:'n',florence:'e',lyon:'e',hong_kong:'e',bombay:'w',goa:'w',batavia:'s',singapore:'s',frankfurt:'e',augsburg:'e',constantinople:'e',alexandria:'s',new_york:'w',tokyo:'e',sydney:'e',buenos_aires:'w',calcutta:'e',dubai:'s'};
const RIVAL_COLORS=['#8b3a8f','#2f6f8f','#9a4a2a','#2f8a5a','#8a702a','#3f4f9a','#9a2f5f','#5f8a2f','#6a5a8a','#2a7a7a','#a0522d','#4a7a9a'];

const SYMBOLS=`
<symbol id="s-galley" viewBox="-12 -12 24 24" overflow="visible"><path d="M-11 2 L11 2 L8.5 5.5 L-8.5 5.5 Z" fill="currentColor"/><path d="M-6 5.5l-2 4M-2 5.5l-2 4M2 5.5l-2 4M6 5.5l-2 4" stroke="currentColor" stroke-width="1" fill="none"/><path d="M0 2V-9" stroke="currentColor" stroke-width="1.2"/><path d="M1 -9 L9.5 -0.5 L-6 1.2 Z" style="fill:var(--m-sail)" stroke="currentColor" stroke-width=".8"/></symbol>
<symbol id="s-carrack" viewBox="-12 -12 24 24" overflow="visible"><path d="M-11 0 Q-10 6 -6 6 L7 6 Q10.5 5 11.5 -1 L6 1 L-6 1 L-9 -1 Z" fill="currentColor"/><path d="M-5 1V-8M1 1V-10M6 1V-6" stroke="currentColor" stroke-width="1"/><rect x="-7.5" y="-7" width="5" height="5" rx=".6" style="fill:var(--m-sail)" stroke="currentColor" stroke-width=".7"/><rect x="-2" y="-9" width="6" height="6.5" rx=".6" style="fill:var(--m-sail)" stroke="currentColor" stroke-width=".7"/><rect x="4" y="-5.5" width="4" height="4" rx=".6" style="fill:var(--m-sail)" stroke="currentColor" stroke-width=".7"/></symbol>
<symbol id="s-steamer" viewBox="-12 -12 24 24" overflow="visible"><path d="M-11.5 1 L11.5 1 L9.5 5.5 L-9.5 5.5 Z" fill="currentColor"/><rect x="-6" y="-2.5" width="10" height="3.5" style="fill:var(--m-sail)" stroke="currentColor" stroke-width=".8"/><rect x="-1" y="-8" width="3" height="5.5" fill="currentColor"/><circle cx="2" cy="-10.5" r="1.8" fill="currentColor" opacity=".35"/><circle cx="4.5" cy="-11.5" r="1.4" fill="currentColor" opacity=".22"/></symbol>
<symbol id="s-boxship" viewBox="-12 -12 24 24" overflow="visible"><path d="M-12 1 L12 1 L10 5.5 L-10 5.5 Z" fill="currentColor"/><rect x="-9" y="-3" width="4" height="4" fill="#c0503c"/><rect x="-5" y="-3" width="4" height="4" fill="#3c78b4"/><rect x="-1" y="-3" width="4" height="4" fill="#d8a028"/><rect x="-5" y="-7" width="4" height="4" fill="#3ca078"/><rect x="5" y="-6" width="4" height="7" style="fill:var(--m-sail)" stroke="currentColor" stroke-width=".8"/></symbol>
<symbol id="s-letter" viewBox="-12 -12 24 24" overflow="visible"><rect x="-8" y="-5.5" width="16" height="11" rx="1" style="fill:var(--m-sail)" stroke="currentColor" stroke-width="1.2"/><path d="M-8 -5.5 L0 1 L8 -5.5" fill="none" stroke="currentColor" stroke-width="1"/><circle cx="0" cy="1.5" r="2.4" fill="#b0352a"/></symbol>
<symbol id="s-pulse" viewBox="-12 -12 24 24" overflow="visible"><circle r="6" fill="currentColor" opacity=".25"/><circle r="3" fill="currentColor"/></symbol>
<symbol id="s-plane" viewBox="-12 -12 24 24" overflow="visible"><path d="M11 0 L-3 -1.6 L-7 -8 L-9.5 -8 L-7 -1.8 L-10.5 -1.4 L-12 -4 L-13 -4 L-12 0 L-13 4 L-12 4 L-10.5 1.4 L-7 1.8 L-9.5 8 L-7 8 L-3 1.6 Z" fill="currentColor"/></symbol>
<symbol id="s-chest" viewBox="-12 -12 24 24" overflow="visible"><rect x="-8" y="-3" width="16" height="9" rx="1" fill="#8a5a2b" stroke="#3b250f" stroke-width="1"/><path d="M-8 -3 Q0 -9 8 -3 Z" fill="#a06a32" stroke="#3b250f" stroke-width="1"/><rect x="-1.6" y="-1" width="3.2" height="4" fill="#e0b24a" stroke="#3b250f" stroke-width=".6"/><circle cx="-4" cy="-5" r="1.6" fill="#e8c050"/><circle cx="3" cy="-5.6" r="1.6" fill="#e8c050"/></symbol>
<symbol id="s-coin" viewBox="-12 -12 24 24" overflow="visible"><circle r="5.5" fill="#e0b24a" stroke="#7a5a10" stroke-width="1"/><circle r="3.2" fill="none" stroke="#7a5a10" stroke-width=".7"/></symbol>
<symbol id="s-person" viewBox="-12 -12 24 24" overflow="visible"><circle cy="-6" r="3" fill="currentColor"/><path d="M-4.5 6 Q-4.5 -2 0 -2 Q4.5 -2 4.5 6 Z" fill="currentColor"/></symbol>
<symbol id="s-bench" viewBox="-12 -12 24 24" overflow="visible"><path d="M-10 -4 L10 -4 L8 -10 L-8 -10 Z" fill="#b0352a" stroke="currentColor" stroke-width="1"/><path d="M-5 -10 L-6 -4 M0 -10 V-4 M5 -10 L6 -4" stroke="#f3e6c8" stroke-width="2"/><rect x="-9" y="0" width="18" height="2.5" fill="currentColor"/><path d="M-7 2.5 V8 M7 2.5 V8 M-9 -4 V0 M9 -4 V0" stroke="currentColor" stroke-width="1.5"/><rect x="-3" y="-2.2" width="6" height="2.2" style="fill:var(--m-sail)" stroke="currentColor" stroke-width=".7"/></symbol>
<symbol id="s-house" viewBox="-12 -12 24 24" overflow="visible"><path d="M-8 -1 L0 -10 L8 -1 Z" fill="currentColor"/><rect x="-7" y="-1" width="14" height="10" style="fill:var(--m-sail)" stroke="currentColor" stroke-width="1.3"/><rect x="-2" y="3" width="4" height="6" fill="currentColor"/><rect x="-5.5" y="1" width="2.5" height="2.5" fill="currentColor"/><rect x="3" y="1" width="2.5" height="2.5" fill="currentColor"/></symbol>
<symbol id="s-bank" viewBox="-12 -12 24 24" overflow="visible"><path d="M-11 -4 L0 -11 L11 -4 Z" fill="currentColor"/><rect x="-10" y="-4" width="20" height="2" fill="currentColor"/><path d="M-7.5 -2 V6 M-2.5 -2 V6 M2.5 -2 V6 M7.5 -2 V6" stroke="currentColor" stroke-width="2.3"/><rect x="-11" y="6" width="22" height="3" fill="currentColor"/><path d="M-11 -4 L0 -11 L11 -4" fill="none" style="stroke:var(--m-sail)" stroke-width=".8"/></symbol>
<symbol id="s-tower" viewBox="-12 -12 24 24" overflow="visible"><rect x="-5" y="-11" width="10" height="20" fill="currentColor"/><path d="M0 -11 V-14" stroke="currentColor" stroke-width="1"/><path d="M-3 -8h2m2 0h2M-3 -5h2m2 0h2M-3 -2h2m2 0h2M-3 1h2m2 0h2M-3 4h2m2 0h2" style="stroke:var(--m-sail)" stroke-width="1.4"/><rect x="5" y="-3" width="5" height="12" fill="currentColor" opacity=".75"/><rect x="-10" y="1" width="5" height="8" fill="currentColor" opacity=".6"/></symbol>
<symbol id="s-flag" viewBox="-12 -12 24 24" overflow="visible"><path d="M0 0 V-12" stroke="currentColor" stroke-width="1.2"/><path d="M0 -12 L8 -10 L0 -8 Z" fill="#b0352a"/></symbol>
<symbol id="s-banner" viewBox="-12 -12 24 24" overflow="visible"><path d="M-6 9 V-10" stroke="#3a2a14" stroke-width="1.4"/><path d="M-6 -10 H7 L4 -5 L7 0 H-6 Z" fill="currentColor" stroke="#3a2a14" stroke-width=".8"/></symbol>
<symbol id="s-burst" viewBox="-12 -12 24 24" overflow="visible"><path d="M0 -11 L2.5 -4 L9.5 -6.5 L5 -1 L11 3 L3.5 3.5 L4 11 L0 5 L-4 11 L-3.5 3.5 L-11 3 L-5 -1 L-9.5 -6.5 L-2.5 -4 Z" fill="#d03b3b" stroke="#6e1414" stroke-width=".8"/></symbol>
<symbol id="s-flame" viewBox="-12 -12 24 24" overflow="visible"><path d="M0 -11 C5 -5 8 -2 6 4 C4.5 8 -4.5 8 -6 4 C-7.5 0 -4 -2 -3 -6 C-1.5 -3 0 -4 0 -11 Z" fill="#e2701f"/><path d="M0 -3 C3 0 3.5 2 2.5 4.5 C1.5 6.5 -2 6.5 -2.8 4.5 C-3.5 2.5 -1 1 0 -3 Z" fill="#f6c443"/></symbol>
<symbol id="s-rose" viewBox="-12 -12 24 24" overflow="visible"><circle r="9" fill="none" stroke="currentColor" stroke-width=".35"/><circle r="6.5" fill="none" stroke="currentColor" stroke-width=".25"/><path d="M0 -11 L1.6 -1.6 L11 0 L1.6 1.6 L0 11 L-1.6 1.6 L-11 0 L-1.6 -1.6 Z" fill="currentColor" opacity=".55"/><path d="M0 -11 L1.6 -1.6 L0 0 Z M11 0 L1.6 1.6 L0 0 Z M0 11 L-1.6 1.6 L0 0 Z M-11 0 L-1.6 -1.6 L0 0 Z" fill="currentColor"/><path d="M5.5 -5.5 L1.2 0 L-5.5 5.5 L-1.2 0 Z M-5.5 -5.5 L0 -1.2 L5.5 5.5 L0 1.2 Z" fill="#b0352a" opacity=".6"/><path d="M0 -13.5 L-1.2 -11.5 H1.2 Z" fill="#b0352a"/></symbol>
<radialGradient id="g-hole"><stop offset="0" stop-color="#000" stop-opacity="1"/><stop offset=".55" stop-color="#000" stop-opacity=".92"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>
<radialGradient id="g-halo"><stop offset="0" style="stop-color:var(--m-halo)" stop-opacity=".55"/><stop offset=".6" style="stop-color:var(--m-halo)" stop-opacity=".18"/><stop offset="1" style="stop-color:var(--m-halo)" stop-opacity="0"/></radialGradient>
<pattern id="p-hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><path d="M0 0V10" style="stroke:var(--m-coast)" stroke-width="1.1" opacity=".35"/></pattern>
<mask id="m-fog" maskUnits="userSpaceOnUse" x="-600" y="-300" width="4200" height="2400"><rect x="-600" y="-300" width="4200" height="2400" fill="#fff"/><g id="fog-holes"></g></mask>`;

function sel(tag,attrs,parent){ const e=document.createElementNS(NS,tag); if(attrs) for(const k in attrs) e.setAttribute(k,attrs[k]); if(parent) parent.appendChild(e); return e; }
function cxy(cid){ return G.cities[cid]; }
function citySov(cid){ const cs=S.cityState&&S.cityState[cid]; return (cs&&cs.sovereign)||city(cid).sovereign; }
function sovSeat(s){ const v=D.sovereigns[s]; if(!v) return S.seat; let seat=v.seat; for(const [y,c] of (v.seat_by_year||[])) if(S.year>=y) seat=c; return seat; }
function isKnown(cid){ const k=G.known[cid]; return k==null||S.year>=k; }
function mapStyle(){ return S.year<1700?'portolan':S.year<1950?'engraved':'modern'; }
function buildingFor(){ const e=era().id; return e==='rialto'||e==='medici'?'bench':e==='princes'||e==='northern'?'house':e==='basel'?'tower':'bank'; }
function shipFor(){ return S.year<1500?'galley':S.year<1850?'carrack':S.year<1950?'steamer':'boxship'; }
function rivalColor(rid){ const i=D.rivals.findIndex(r=>r.id===rid); return RIVAL_COLORS[i%RIVAL_COLORS.length]; }

/* geometry: the routes are smoothed through their waypoints, and sampled evenly for the pieces */
function catmull(pts){ const segs=[]; for(let i=0;i<pts.length-1;i++){ const p0=pts[i-1]||pts[i], p1=pts[i], p2=pts[i+1], p3=pts[i+2]||p2;
  segs.push([p1,[p1[0]+(p2[0]-p0[0])/6,p1[1]+(p2[1]-p0[1])/6],[p2[0]-(p3[0]-p1[0])/6,p2[1]-(p3[1]-p1[1])/6],p2]); } return segs; }
function arcPts(a,b,lift){ const [x0,y0]=a,[x1,y1]=b, mx=(x0+x1)/2, my=(y0+y1)/2-Math.hypot(x1-x0,y1-y0)*lift, out=[]; for(let i=0;i<=24;i++){ const t=i/24,u=1-t; out.push([u*u*x0+2*u*t*mx+t*t*x1,u*u*y0+2*u*t*my+t*t*y1]); } return out; }
function routeGeom(r){
  const pts=r.air?arcPts(cxy(r.a),cxy(r.b),0.16):(!r.sea&&r.pts.length===2)?arcPts(cxy(r.a),cxy(r.b),0.05):r.pts;
  const segs=catmull(pts); let d='M'+pts[0][0].toFixed(1)+' '+pts[0][1].toFixed(1); const raw=[pts[0]];
  for(const [p1,c1,c2,p2] of segs){ d+=' C'+c1[0].toFixed(1)+' '+c1[1].toFixed(1)+' '+c2[0].toFixed(1)+' '+c2[1].toFixed(1)+' '+p2[0].toFixed(1)+' '+p2[1].toFixed(1);
    for(let k=1;k<=12;k++){ const t=k/12,u=1-t; raw.push([u*u*u*p1[0]+3*u*u*t*c1[0]+3*u*t*t*c2[0]+t*t*t*p2[0],u*u*u*p1[1]+3*u*u*t*c1[1]+3*u*t*t*c2[1]+t*t*t*p2[1]]); } }
  const step=2, s=[raw[0]]; let carry=0; for(let i=1;i<raw.length;i++){ let [x0,y0]=raw[i-1]; const [x1,y1]=raw[i]; let seg=Math.hypot(x1-x0,y1-y0);
    while(carry+seg>=step&&seg>0){ const f=(step-carry)/seg; x0+=(x1-x0)*f; y0+=(y1-y0)*f; s.push([x0,y0]); seg=Math.hypot(x1-x0,y1-y0); carry=0; } carry+=seg; }
  s.push(raw[raw.length-1]); return {d,pts:s}; }

/* --------------------------------------------------------------- building the board once */
function buildBoard(){
  const svg=$('map'); MAP.svg=svg; svg.innerHTML='';
  const defs=sel('defs',null,svg); defs.innerHTML=SYMBOLS;
  for(const n of ['sea','grat','rhumb','land','halo','routes','fog','hints','cities','rivals','tokens','fx']) MAP.L[n]=sel('g',{class:'L-'+n},svg);
  sel('rect',{x:-600,y:-300,width:4200,height:2400,class:'sea'},MAP.L.sea);
  let gd=''; for(let lon=-180;lon<=180;lon+=10){ const x=((lon+180)*G.kx).toFixed(1); gd+='M'+x+' 100V1500'; } for(let lat=-60;lat<=80;lat+=10){ gd+='M0 '+((90-lat)*G.units_per_degree)+'H'+(360*G.kx).toFixed(0); }
  sel('path',{d:gd,class:'grat'},MAP.L.grat);
  // the portolan's rhumb lines: thirty-two winds from three roses, in the chart-makers' black, green and red
  const rd=['','','']; for(const [lon,lat] of [[6,40.5],[24,36.5],[-9,46]]){ const x=(lon+180)*G.kx, y=(90-lat)*G.units_per_degree;
    for(let i=0;i<32;i++){ const a=i*Math.PI/16, k=i%4===0?0:i%2===0?1:2; rd[k]+='M'+x.toFixed(1)+' '+y.toFixed(1)+'l'+(Math.cos(a)*1100).toFixed(1)+' '+(Math.sin(a)*1100).toFixed(1); } }
  rd.forEach((d,i)=>sel('path',{d,class:'rhumb r'+i},MAP.L.rhumb));
  sel('use',{href:'#s-rose',class:'rose',transform:'translate('+((6+180)*G.kx).toFixed(1)+' '+((90-40.5)*G.units_per_degree)+') scale(2.6)'},MAP.L.rhumb);
  sel('path',{d:G.land.join(''),class:'land'},MAP.L.land);
  MAP.routeGeom=G.routes.map(r=>{ const g=routeGeom(r); g.el=sel('path',{d:g.d,class:'route off'},MAP.L.routes); return g; });
  sel('rect',{x:-600,y:-300,width:4200,height:2400,class:'fog',mask:'url(#m-fog)'},MAP.L.fog);
  sel('rect',{x:-600,y:-300,width:4200,height:2400,class:'fog-hatch',fill:'url(#p-hatch)',mask:'url(#m-fog)'},MAP.L.fog);
  for(const c of D.cities){ const [x,y]=cxy(c.id);
    const g=sel('g',{class:'city',tabindex:'0',role:'button','aria-label':c.name},MAP.L.cities);
    const halo=sel('circle',{class:'halo',cx:x,cy:y,r:20,fill:'url(#g-halo)'},MAP.L.halo);
    const ring=sel('circle',{class:'ring',r:9},g), dot=sel('circle',{class:'dot',r:4},g);
    const bld=sel('use',{class:'bld',href:'#s-bench',x:-12,y:-12,width:24,height:24},g), flag=sel('use',{class:'seatflag',href:'#s-flag',x:-12,y:-24,width:24,height:24},g);
    const lbl=sel('text',{class:'lbl'},g); lbl.textContent=c.name;
    const title=sel('title',null,g);
    const hint=sel('g',{class:'hint'},MAP.L.hints); const ht=sel('text',{class:'hint-t','text-anchor':'middle',y:4},hint); ht.textContent=(G.rumour[c.id]||'')+'?'; sel('circle',{class:'hint-d',r:2.5,cy:-8},hint);
    MAP.cityEls[c.id]={g,dot,ring,bld,flag,lbl,title,halo,hint};
    MAP.marks.push({el:g,x,y,s:1},{el:hint,x,y,s:1});
    g.addEventListener('click',ev=>{ ev.stopPropagation(); openPop(c.id); });
    g.addEventListener('keydown',ev=>{ if(ev.key==='Enter'||ev.key===' '){ ev.preventDefault(); openPop(c.id); } });
  }
  for(const r of D.rivals){ const g=sel('g',{class:'rival'},MAP.L.rivals); const u=sel('use',{href:'#s-banner',x:-12,y:-12,width:24,height:24},g); u.style.color=rivalColor(r.id);
    const t=sel('text',{class:'rival-t',x:0.5,y:-4.2,'text-anchor':'middle'},g); t.textContent=r.short[0]; sel('title',null,g).textContent=r.name.replace(/^the /,'The ');
    MAP.rivalEls[r.id]={g}; MAP.marks.push({el:g,x:0,y:0,s:0.85,rival:r.id}); }
  wireBoard(); sizeBoard(); MAP.vb=fitBox(G.opening_view.slice()); MAP.target=MAP.vb.slice(); MAP.built=true; applyCam(true);
  requestAnimationFrame(tick);
}

/* --------------------------------------------------------------- redrawing on every change of state */
function renderBoard(){
  if(!MAP.built) return;
  const yr=S.year, E=era(), board=$('board'); board.dataset.style=mapStyle();
  $('c-year').textContent=yr; $('c-era').textContent=E.name; $('c-sub').textContent=E.subtitle;
  // routes: known lanes faint, the house's own in its colour
  MAP.routeGeom.forEach((g,i)=>{ const r=G.routes[i]; const live=yr>=r.from&&yr<r.until&&isKnown(r.a)&&isKnown(r.b);
    const a=!!S.branches[r.a], b=!!S.branches[r.b];
    g.live=live; g.mine=live&&a&&b; g.reach=live&&(a||b);
    g.el.setAttribute('class','route '+(r.air?'air':r.sea?'sea':'land')+(live?'':' off')+(g.mine?' mine':g.reach?' reach':'')); });
  // the fog: cleared round the known world, along known lanes, and widely round the house's branches
  const holes=document.getElementById('fog-holes'); let h='';
  const eu=[G.opening_view[0]+G.opening_view[2]*0.5,G.opening_view[1]+G.opening_view[3]*0.52];
  h+=`<ellipse cx="${eu[0]}" cy="${eu[1]}" rx="${G.opening_view[2]*0.62}" ry="${G.opening_view[3]*0.66}" fill="url(#g-hole)"/>`;
  for(const c of D.cities){ if(!isKnown(c.id)) continue; const [x,y]=cxy(c.id); const r=S.branches[c.id]?170:70; h+=`<circle cx="${x}" cy="${y}" r="${r}" fill="url(#g-hole)"/>`; }
  let rd=''; MAP.routeGeom.forEach(g=>{ if(g.live) rd+=g.d; });
  if(rd) h+=`<path d="${rd}" fill="none" stroke="#000" stroke-width="80" stroke-opacity=".35" stroke-linecap="round" stroke-linejoin="round"/><path d="${rd}" fill="none" stroke="#000" stroke-width="44" stroke-opacity=".7" stroke-linecap="round" stroke-linejoin="round"/>`;
  holes.innerHTML=h;
  // the world's charts fill in with the centuries: thick fog to 1500, thinning to a light haze by the jet age
  MAP.L.fog.style.opacity=(yr<1500?1:yr<1950?1-0.55*(yr-1500)/450:0.4).toFixed(2);
  // cities, the house's buildings, the centre of gravity
  const att=cityAttribution(), bsym='#s-'+buildingFor();
  for(const c of D.cities){ const e=MAP.cityEls[c.id], known=isKnown(c.id), cs=S.cityState[c.id], open=cs.open&&yr>=c.opens, p=prosperity(c.id), br=S.branches[c.id], seat=c.id===S.seat, centre=c.id===S.centre;
    const live=known&&open&&(p>0||br);
    e.g.style.display=known?'':'none'; e.hint.style.display=(!known&&G.rumour[c.id])?'':'none';
    e.g.setAttribute('class','city'+(live?'':' dim')+(br?' mine':'')+(seat?' seat':'')+(centre?' centre':'')+(cs.sacked?' sacked':''));
    e.dot.setAttribute('r',(2.2+4.6*Math.sqrt(Math.max(0,p))).toFixed(2));
    e.ring.setAttribute('r',(6+4.6*Math.sqrt(Math.max(0,p))).toFixed(2));
    e.bld.setAttribute('href',bsym); e.bld.style.display=br?'':'none'; e.flag.style.display=seat?'':'none'; e.dot.style.display=br?'none':'';
    const scale=br?(0.8+0.75*Math.sqrt(att[c.id]||0)):1; e.bld.setAttribute('transform','scale('+scale.toFixed(3)+')'); e.flag.setAttribute('transform','translate(0 '+(-(scale-1)*12).toFixed(1)+')');
    const dir=LABEL_DIR[c.id]||'e', off=br?14*scale:8; const [lx,ly,anc]=dir==='w'?[-off,4,'end']:dir==='n'?[0,-off-3,'middle']:dir==='s'?[0,off+10,'middle']:[off,4,'start'];
    e.lbl.setAttribute('x',lx); e.lbl.setAttribute('y',ly); e.lbl.setAttribute('text-anchor',anc);
    e.lbl.textContent=c.name+(!open&&known&&c.opens>yr?' ('+c.opens+')':'');
    e.title.textContent=c.name+' — '+(br?(seat?'your seat':'your branch'):live?'prosperity '+Math.round(p*100):'not yet open')+(centre?' · centre of gravity':'');
    e.prosperity=p; e.important=!!(br||centre||seat);
    const com=(S.commerce&&S.commerce[c.id])||1; e.halo.setAttribute('r',(16+42*Math.max(0,p)).toFixed(1)); e.halo.style.opacity=live?(0.35+0.9*(com-1)+0.35*p).toFixed(2):0;
  }
  // the rival houses' banners, stacked at their homes
  const stack={}; for(const r of D.rivals){ const m=MAP.marks.find(k=>k.rival===r.id), g=MAP.rivalEls[r.id].g; const live=rivalActive(r)&&isKnown(r.home);
    g.style.display=live?'':'none'; if(!live) continue; const n=(stack[r.home]=(stack[r.home]||0)+1); const [x,y]=cxy(r.home); m.x=x; m.y=y; m.off=[-10-12*(n-1),-6]; }
  buildTokens();
  if(MAP.follow) MAP.target=frameTarget();
  MAP.lastPx=0; renderLegend(); if(MAP.pop) renderPop();
}

/* --------------------------------------------------------------- the moving pieces */
function buildTokens(){
  const L=MAP.L.tokens; L.innerHTML=''; MAP.tokens=[]; const yr=S.year, att=cityAttribution(), T=Math.max(1,totalAssets());
  let pc=0; for(const k of PRIVATE) pc+=amount(k); pc/=T;
  const ship=shipFor(), sp={galley:11,carrack:15,steamer:24,boxship:30}[ship];
  const bills=(amount('trade_bills')+amount('acceptances')+amount('discount_market'))/T;
  const rivalAt={}; D.rivals.forEach(r=>{ if(rivalActive(r)&&isKnown(r.home)) (rivalAt[r.home]=rivalAt[r.home]||[]).push(r.id); });
  let neutral=0, rships=0;
  MAP.routeGeom.forEach((g,i)=>{ if(!g.live) return; const r=G.routes[i], a=!!S.branches[r.a], b=!!S.branches[r.b];
    if(r.air){ if(a&&b) addTok(g.pts,'plane',{speed:140,size:.7,cls:'tk-mine',rotate:true,dwell:.3}); return; }
    if(!r.sea){ if(a&&b){ if(yr<1850){ const n=clamp(Math.round(1+bills*10),1,3); for(let k=0;k<n;k++) addTok(g.pts,'letter',{speed:20,size:.55,cls:'tk-mine'}); } else addTok(g.pts,'pulse',{speed:110,size:.5,cls:'tk-mine',dwell:.2}); } return; }
    const w=(att[r.a]||0)+(att[r.b]||0);
    if(a||b){ const n=clamp(Math.round(1+w*7*pc+(a&&b?1:0)),1,5); for(let k=0;k<n;k++) addTok(g.pts,ship,{speed:sp,size:.78,cls:'tk-mine'}); }
    else if(neutral<16){ addTok(g.pts,ship,{speed:sp*0.85,size:.6,cls:'tk-neutral'}); neutral++; }
    for(const end of [r.a,r.b]) for(const rid of (rivalAt[end]||[])) if(rships<14&&Math.random()<0.6){ addTok(g.pts,ship,{speed:sp,size:.66,cls:'tk-rival',color:rivalColor(rid)}); rships++; }
  });
}
function addTok(pts,sym,o){ const e=sel('use',{href:'#s-'+sym,class:'tok '+o.cls,x:-12,y:-12,width:24,height:24},MAP.L.tokens); if(o.color) e.style.color=o.color;
  const tk={el:e,pts,pos:Math.random()*(pts.length-1),dir:Math.random()<.5?1:-1,speed:o.speed,size:o.size,rotate:!!o.rotate,wait:Math.random()*0.6,dwell:o.dwell??0.9}; MAP.tokens.push(tk); placeTok(tk); }
function placeTok(tk){ const n=tk.pts.length-1, i=Math.min(n,Math.floor(tk.pos)), f=tk.pos-i, a=tk.pts[i], b=tk.pts[Math.min(i+1,n)], c=tk.pts[Math.max(0,Math.min(i+1,n)-1)];
  const x=a[0]+(b[0]-a[0])*f, y=a[1]+(b[1]-a[1])*f, dx=((b[0]-c[0])||0.0001)*tk.dir, dy=(b[1]-c[1])*tk.dir, s=MAP.px*tk.size;
  tk.el.setAttribute('transform',tk.rotate?`translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${(Math.atan2(dy,dx)*57.2958).toFixed(1)}) scale(${s.toFixed(4)})`:`translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(${(dx<0?-s:s).toFixed(4)} ${s.toFixed(4)})`); }
function stepTok(tk,dt){ if(tk.wait>0){ tk.wait-=dt; return; } const n=tk.pts.length-1; tk.pos+=tk.dir*tk.speed*dt/2;
  if(tk.pos>=n){ tk.pos=n; tk.dir=-1; tk.wait=tk.dwell; } else if(tk.pos<=0){ tk.pos=0; tk.dir=1; tk.wait=tk.dwell; } placeTok(tk); }

/* --------------------------------------------------------------- the camera */
function sizeBoard(){ const r=MAP.svg.getBoundingClientRect(); MAP.W=Math.max(200,r.width||800); MAP.H=Math.max(200,r.height||480); }
function fitBox(b){ const ar=MAP.H/MAP.W; let [x,y,w,h]=b; if(h/w<ar){ const nh=w*ar; y-=(nh-h)/2; h=nh; } else { const nw=h/ar; x-=(nw-w)/2; w=nw; } return [x,y,w,h]; }
function frameTarget(){ const o=G.opening_view; let x0=o[0],y0=o[1],x1=o[0]+o[2],y1=o[1]+o[3];
  const add=([x,y])=>{ x0=Math.min(x0,x); y0=Math.min(y0,y); x1=Math.max(x1,x); y1=Math.max(y1,y); };
  for(const c of branchIds()) add(cxy(c));
  for(const cls of SOV_SCALAR) for(const s in (S.assets[cls]||{})) if(S.assets[cls][s]>0.5) add(cxy(sovSeat(s)));
  const pw=(x1-x0)*0.06+24, ph=(y1-y0)*0.08+24; return fitBox([x0-pw,y0-ph,x1-x0+2*pw,y1-y0+2*ph]); }
function applyCam(force){ const v=MAP.vb; MAP.svg.setAttribute('viewBox',v.map(n=>n.toFixed(2)).join(' ')); MAP.px=v[2]/MAP.W;
  if(force||!MAP.lastPx||Math.abs(MAP.px-MAP.lastPx)/MAP.px>0.003){ MAP.lastPx=MAP.px; rescale(); } placePop(); edgeHints(); }
function rescale(){ const px=MAP.px;
  for(const m of MAP.marks){ if(m.el.style.display==='none') continue; const off=m.off?` translate(${m.off[0]} ${m.off[1]})`:''; m.el.setAttribute('transform',`translate(${m.x} ${m.y}) scale(${(px*m.s).toFixed(4)})${off}`); }
  // labels thin out as the map zooms out: branches, the seat and the centre always; then by prosperity
  const thr=px<0.45?-1:px<0.8?0.4:px<1.3?0.6:0.75;
  for(const c of D.cities){ const e=MAP.cityEls[c.id]; if(!e) continue; e.lbl.style.display=(e.important||(e.prosperity||0)>thr)?'':'none'; }
  for(const tk of MAP.tokens) placeTok(tk);
  for(const sp of MAP.sprites) sp.place&&sp.place(); }
function zoomAt(f,sx,sy){ const v=MAP.target||MAP.vb, mx=v[0]+sx/MAP.W*v[2], my=v[1]+sy/MAP.H*v[3]; const w=clamp(v[2]/f,90,2900), h=w*MAP.H/MAP.W;
  MAP.target=[mx-sx/MAP.W*w,my-sy/MAP.H*h,w,h]; MAP.follow=false; }
function panBy(dx,dy){ const v=MAP.vb, k=v[2]/MAP.W; for(const b of [MAP.vb,MAP.target]) if(b){ b[0]-=dx*k; b[1]-=dy*k; } MAP.follow=false; applyCam(); }
function wireBoard(){ const svg=MAP.svg;
  svg.addEventListener('wheel',ev=>{ ev.preventDefault(); const r=svg.getBoundingClientRect(); zoomAt(Math.exp(-ev.deltaY*0.0016),ev.clientX-r.left,ev.clientY-r.top); },{passive:false});
  svg.addEventListener('pointerdown',ev=>{ MAP.pointers[ev.pointerId]=[ev.clientX,ev.clientY]; MAP.moved=0; svg.setPointerCapture&&svg.setPointerCapture(ev.pointerId); });
  svg.addEventListener('pointermove',ev=>{ const p=MAP.pointers[ev.pointerId]; if(!p) return; const ids=Object.keys(MAP.pointers);
    if(ids.length===2){ const [a,b]=ids.map(i=>MAP.pointers[i]); const d0=Math.hypot(a[0]-b[0],a[1]-b[1]); MAP.pointers[ev.pointerId]=[ev.clientX,ev.clientY]; const [c,d]=ids.map(i=>MAP.pointers[i]); const d1=Math.hypot(c[0]-d[0],c[1]-d[1]);
      const r=svg.getBoundingClientRect(); if(d0>0){ zoomAt(d1/d0,(c[0]+d[0])/2-r.left,(c[1]+d[1])/2-r.top); MAP.vb=MAP.target.slice(); applyCam(); } MAP.moved+=99; return; }
    const dx=ev.clientX-p[0], dy=ev.clientY-p[1]; MAP.moved+=Math.abs(dx)+Math.abs(dy); MAP.pointers[ev.pointerId]=[ev.clientX,ev.clientY]; if(MAP.moved>4) panBy(dx,dy); });
  const up=ev=>{ delete MAP.pointers[ev.pointerId]; };
  svg.addEventListener('pointerup',ev=>{ const click=MAP.moved<=4; up(ev); if(click&&!ev.target.closest('.city')) closePop(); });
  svg.addEventListener('pointercancel',up); svg.addEventListener('pointerleave',up);
  $('z-in').addEventListener('click',()=>zoomAt(1.5,MAP.W/2,MAP.H/2));
  $('z-out').addEventListener('click',()=>zoomAt(1/1.5,MAP.W/2,MAP.H/2));
  $('z-frame').addEventListener('click',()=>{ MAP.follow=true; MAP.target=frameTarget(); });
  window.addEventListener('resize',()=>{ sizeBoard(); MAP.vb=fitBox(MAP.vb); MAP.target=MAP.follow?frameTarget():fitBox(MAP.target||MAP.vb); applyCam(true); });
  document.addEventListener('keydown',ev=>{ if(ev.key==='Escape') closePop(); });
}

/* --------------------------------------------------------------- the frame loop */
function tick(t){ requestAnimationFrame(tick); const dt=Math.min(0.05,((t-(MAP.last||t))/1000)); MAP.last=t; if(document.hidden||!MAP.built) return;
  if(MAP.target){ const v=MAP.vb, g=MAP.target, k=Math.min(1,dt*4.5); let moved=false; for(let i=0;i<4;i++){ const d=g[i]-v[i]; if(Math.abs(d)>0.02*Math.max(1,v[2]/400)){ v[i]+=d*k; moved=true; } else if(v[i]!==g[i]){ v[i]=g[i]; moved=true; } } if(moved) applyCam(); }
  if(MAP.anim&&!REDUCED) for(const tk of MAP.tokens) stepTok(tk,dt);
  stepFx(dt); }

/* --------------------------------------------------------------- the turn, played back on the map */
function locOf(f){ if(f.city) return cxy(f.city); if(f.sov) return cxy(sovSeat(f.sov)); if(f.cities&&f.cities.length) return cxy(f.cities.find(c=>S.branches[c])||f.cities[0]); return null; }
function play(fx,done){ flushPlay(); if(AUTOPLAY||!MAP.anim||REDUCED||!MAP.built||!fx||!fx.length){ if(!AUTOPLAY&&fx&&fx.length) showNews(fx); done&&done(); return; }
  let t=0.15; MAP.fxq=fx.map(f=>{ const it={...f,at:t}; t+=f.k==='news'?0.55:0.22; return it; }); MAP.playT=0; MAP.playEnd=t+1.3; MAP.playDone=done; MAP.playing=true; $('board').classList.add('playing'); document.body.classList.add('playing'); }
function flushPlay(){ if(!MAP.playing) return; MAP.playing=false; MAP.fxq=[]; $('board').classList.remove('playing'); document.body.classList.remove('playing'); const d=MAP.playDone; MAP.playDone=null; d&&d(); }
function stepFx(dt){ if(MAP.playing){ MAP.playT+=dt; while(MAP.fxq.length&&MAP.fxq[0].at<=MAP.playT) spawnFx(MAP.fxq.shift()); if(!MAP.fxq.length&&MAP.playT>=MAP.playEnd) flushPlay(); }
  MAP.sprites=MAP.sprites.filter(sp=>{ sp.t+=dt; if(sp.t>=sp.dur){ sp.el.remove(); return false; } sp.update(sp.t/sp.dur); return true; }); }
function sprite(el,dur,update,place){ const sp={el,t:0,dur,update,place}; MAP.sprites.push(sp); update(0); return sp; }
function spriteAt(sym,x,y,size,cls){ const u=sel('use',{href:'#s-'+sym,x:-12,y:-12,width:24,height:24,class:cls||''},MAP.L.fx); u.setAttribute('transform',`translate(${x} ${y}) scale(${(MAP.px*size).toFixed(4)})`); return u; }
function floatText(x,y,text,tone,dur){ const g=sel('g',null,MAP.L.fx), t=sel('text',{class:'fx-t '+(tone||''),'text-anchor':'middle'},g); t.textContent=text;
  sprite(g,dur||1.8,f=>{ g.setAttribute('transform',`translate(${x} ${y}) scale(${MAP.px.toFixed(4)}) translate(0 ${(-14-26*f).toFixed(1)})`); g.style.opacity=(f<0.75?1:1-(f-0.75)/0.25).toFixed(2); }); }
function pulseAt(x,y,tone){ const c=sel('circle',{class:'fx-ring '+(tone||''),cx:x,cy:y,r:1},MAP.L.fx); sprite(c,1.3,f=>{ c.setAttribute('r',(MAP.px*(6+40*f)).toFixed(2)); c.style.opacity=(1-f).toFixed(2); c.setAttribute('stroke-width',(MAP.px*2.2).toFixed(2)); }); }
function flyAt(sym,a,b,size,dur,lift){ const u=spriteAt(sym,a[0],a[1],size); const mx=(a[0]+b[0])/2, my=(a[1]+b[1])/2-Math.hypot(b[0]-a[0],b[1]-a[1])*(lift??0.22);
  sprite(u,dur,f=>{ const e=f<.5?2*f*f:1-Math.pow(-2*f+2,2)/2, v=1-e; const x=v*v*a[0]+2*v*e*mx+e*e*b[0], y=v*v*a[1]+2*v*e*my+e*e*b[1]; u.setAttribute('transform',`translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(${(MAP.px*size).toFixed(4)})`); u.style.opacity=f>0.9?((1-f)*10).toFixed(2):1; }); }
function spawnFx(f){ const p=locOf(f);
  switch(f.k){
    case 'news': showNews([f]); if(f.cities&&f.cities.length) f.cities.slice(0,4).forEach(c=>{ const q=cxy(c); if(q&&isKnown(c)) pulseAt(q[0],q[1],f.tone); }); else if(p) pulseAt(p[0],p[1],f.tone); break;
    case 'burst': if(!p) break; { const u=spriteAt('burst',p[0],p[1],1); sprite(u,1.4,g=>{ u.setAttribute('transform',`translate(${p[0]} ${p[1]}) scale(${(MAP.px*(0.4+1.1*Math.min(1,g*3))).toFixed(4)}) rotate(${(g*40).toFixed(1)})`); u.style.opacity=(g<0.7?1:1-(g-0.7)/0.3).toFixed(2); }); } if(f.text) floatText(p[0],p[1],f.text,'bad',2); break;
    case 'smoke': if(!p) break; { const u=spriteAt('flame',p[0],p[1],1); sprite(u,1.8,g=>{ u.setAttribute('transform',`translate(${p[0]} ${p[1]-MAP.px*8}) scale(${(MAP.px*(0.8+0.2*Math.sin(g*30))).toFixed(4)})`); u.style.opacity=(g<0.8?1:1-(g-0.8)/0.2).toFixed(2); }); } if(f.text) floatText(p[0],p[1],f.text,'bad',2); break;
    case 'float': if(p) floatText(p[0],p[1],f.text,f.tone); break;
    case 'coins': { const a=locOf({city:f.from}), b=locOf({city:f.to}); if(a&&b) for(let i=0;i<3;i++) setTimeout(()=>flyAt('coin',a,b,0.6,1.3,0.18),i*140); break; }
    case 'chest': { const a=locOf({city:f.from}), b=locOf({city:f.to}); if(a&&b) flyAt('chest',a,b,1,1.5,0.25); break; }
    case 'crowd': if(!p) break; for(let i=0;i<9;i++){ const ang=i/9*Math.PI*2, g=sel('use',{href:'#s-person',x:-12,y:-12,width:24,height:24,class:'fx-person'},MAP.L.fx);
        sprite(g,2.2,t=>{ const r=(f.held?(t<0.5?1-t*1.4:0.3+(t-0.5)*1.6):(1-Math.min(1,t*1.6)*0.75))*30; const x=p[0]+Math.cos(ang)*r*MAP.px, y=p[1]+Math.sin(ang)*r*MAP.px*0.7; g.setAttribute('transform',`translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(${(MAP.px*0.5).toFixed(4)})`); g.style.opacity=t>0.85?((1-t)/0.15).toFixed(2):1; }); }
      if(f.text) floatText(p[0],p[1],f.text,f.held?'':'bad',2.2); break;
    case 'fall': if(p){ pulseAt(p[0],p[1],'bad'); floatText(p[0],p[1],f.text,'hist',2.2); } break;
    case 'open': if(p){ pulseAt(p[0],p[1],'good'); floatText(p[0],p[1],f.text,'good'); } break;
  } }
function showNews(items){ const n=$('news'); const it=items[items.length-1]; if(!it||!it.title) return; n.innerHTML=`<span class="news-y">${it.year||S.year}</span> ${esc(it.title)}`; n.dataset.tone=it.tone||''; n.classList.add('show'); clearTimeout(MAP.newsT); MAP.newsT=setTimeout(()=>n.classList.remove('show'),5200); }
function flash(f){ if(AUTOPLAY||!MAP.built) return; spawnFx(f); }

/* --------------------------------------------------------------- the city card */
function openPop(cid){ MAP.pop=cid; renderPop(); }
function focusCity(cid){ const [x,y]=cxy(cid), v=MAP.target||MAP.vb, w=Math.min(v[2],700), h=w*MAP.H/MAP.W; MAP.target=[x-w/2,y-h/2,w,h]; MAP.follow=false;
  $('board').scrollIntoView({behavior:'smooth',block:'nearest'}); openPop(cid); }
function closePop(){ MAP.pop=null; const p=$('pop'); p.hidden=true; }
function renderPop(){ const cid=MAP.pop, p=$('pop'); if(!cid){ p.hidden=true; return; } const c=city(cid), cs=S.cityState[cid], E=era();
  const known=isKnown(cid), open=known&&cs.open&&S.year>=c.opens, base=baseProsperity(cid), com=(S.commerce&&S.commerce[cid])||1, br=S.branches[cid], seat=cid===S.seat;
  const sov=citySov(cid), court=D.sovereigns[sov], rivals=D.rivals.filter(r=>rivalActive(r)&&r.cities.includes(cid)), att=cityAttribution()[cid]||0;
  const offers=S.offers.filter(o=>o.sovereign===sov);
  let acts='';
  if(open&&!br&&!cs.sacked) acts+=`<button class="btn sm accent" data-a="open">Open a branch · ${fmtMoney(branchCost(cid))}</button>`;
  if(br&&!seat) acts+=`<button class="btn sm" data-a="seat">Move the seat here · ${fmtMoney(0.12*equity())}</button><button class="btn sm danger" data-a="close">Close</button>`;
  if(offers.length) acts+=`<button class="btn sm" data-a="court">${esc(court.title)} is asking ›</button>`;
  p.innerHTML=`<div class="pop-h"><div><b>${esc(known?c.name:(G.rumour[cid]||c.name))}</b><span>${esc(c.region)}${known?' · '+esc(court.name):''}</span></div><button class="pop-x" aria-label="Close">×</button></div>
    <p class="pop-b">${known?esc(c.blurb):'Known only by rumour. The charts of '+S.year+' put something here; no one you know has been.'}</p>
    ${known?`<div class="pop-bars">
      <div><span>Prosperity</span><i><b style="width:${Math.round(Math.min(1,base)*100)}%"></b></i><em>${open?Math.round(base*100):'—'}</em></div>
      <div><span>Commerce</span><i><b class="com" style="width:${Math.round(clamp((com-0.5)/0.95,0,1)*100)}%"></b></i><em>×${com.toFixed(2)}</em></div>
    </div>`:''}
    <div class="pop-m">${!known?'':!open?`Opens to you in ${c.opens}.`:br?(seat?'<b>Your seat.</b> ':'<b>Your branch.</b> ')+Math.round(att*100)+'% of the house\'s business'+(seat?'':' · control '+Math.round(br.control*100)+'%')+'.':'No house of yours here.'}
      ${known&&open?`<br>Court: ${esc(court.title)} · your standing ${Math.round(S.standing.crown[sov]||0)}.`:''}
      ${rivals.length?'<br>Rivals here: '+rivals.map(r=>`<span class="pop-rv" style="--rv:${rivalColor(r.id)}">${esc(r.short)}</span>`).join(' '):''}
      ${cid===S.centre?'<br><b>The centre of gravity</b> of the age.':''}${cs.sacked?'<br><b>Sacked.</b>':''}</div>
    ${acts?`<div class="pop-a">${acts}</div>`:''}`;
  p.hidden=false;
  p.querySelector('.pop-x').addEventListener('click',closePop);
  for(const b of p.querySelectorAll('[data-a]')) b.addEventListener('click',()=>{ const a=b.dataset.a;
    if(a==='open'){ if(!openBranch(cid)) toast('Cannot afford to open there.'); }
    else if(a==='seat'){ if(!moveSeat(cid)) toast('Cannot afford the move.'); }
    else if(a==='close'){ closeBranch(cid); }
    else if(a==='court'){ $('card-court').scrollIntoView({behavior:'smooth',block:'start'}); } });
  placePop(); }
function placePop(){ if(!MAP.pop) return; const p=$('pop'); if(p.hidden) return; if(window.innerWidth<640){ p.style.left=''; p.style.top=''; return; }
  const [x,y]=cxy(MAP.pop), v=MAP.vb, sx=(x-v[0])/v[2]*MAP.W, sy=(y-v[1])/v[3]*MAP.H, pw=p.offsetWidth||280, ph=p.offsetHeight||200;
  let left=sx+18; if(left+pw>MAP.W-10) left=sx-18-pw; left=clamp(left,10,Math.max(10,MAP.W-pw-10)); const top=clamp(sy-ph/2,10,Math.max(10,MAP.H-ph-10));
  p.style.left=left+'px'; p.style.top=top+'px'; }

/* --------------------------------------------------------------- rumours at the edge of the chart */
function edgeHints(){ const box=$('edges'); if(!box||!MAP.vb) return; const v=MAP.vb; let h=''; const placed=[];
  for(const c of D.cities){ if(isKnown(c.id)||!G.rumour[c.id]) continue; const [x,y]=cxy(c.id); if(x>=v[0]&&x<=v[0]+v[2]&&y>=v[1]&&y<=v[1]+v[3]) continue;
    const cx=v[0]+v[2]/2, cy=v[1]+v[3]/2, dx=x-cx, dy=y-cy, sxk=(MAP.W/2-60)/Math.abs(dx/v[2]*MAP.W||1e-9), syk=(MAP.H/2-26)/Math.abs(dy/v[3]*MAP.H||1e-9), k=Math.min(sxk,syk);
    const ang=Math.atan2(dy,dx), wid=7.2*G.rumour[c.id].length+30;
    // clamp inside the frame first, then slide inward along the edge past any label already placed
    let px2=clamp(MAP.W/2+dx/v[2]*MAP.W*k,wid/2+6,MAP.W-wid/2-6), py=clamp(MAP.H/2+dy/v[3]*MAP.H*k,14,MAP.H-14);
    const onTB=py<34||py>MAP.H-34;
    for(let n=0;n<12;n++){ const hit=placed.find(q=>Math.abs(q[0]-px2)<(q[2]+wid)/2+4&&Math.abs(q[1]-py)<20); if(!hit) break;
      if(onTB) px2=hit[0]+(px2>MAP.W/2?-1:1)*((hit[2]+wid)/2+8); else py=hit[1]+(py>MAP.H/2?-1:1)*22; }
    placed.push([px2,py,wid]);
    const arr=['→','↘','↓','↙','←','↖','↑','↗'][(Math.round(ang/(Math.PI/4))+8)%8];
    h+=`<span class="edge" style="left:${px2.toFixed(0)}px;top:${py.toFixed(0)}px">${arr==='←'||arr==='↖'||arr==='↙'?arr+' ':''}${esc(G.rumour[c.id])}${arr==='←'||arr==='↖'||arr==='↙'?'':' '+arr}</span>`; }
  box.innerHTML=h; }

function renderLegend(){ const b=buildingFor(), s=shipFor();
  $('legend').innerHTML=`<summary>Key</summary>
  <div><svg viewBox="-12 -12 24 24"><use href="#s-${b}" class="lg-mine"/></svg>Your house — size by business</div>
  <div><svg viewBox="-12 -12 24 24"><use href="#s-${s}" class="lg-mine"/></svg>Trade you finance</div>
  <div><svg viewBox="-12 -12 24 24"><use href="#s-${s}" class="lg-neutral"/></svg>Others' trade</div>
  ${S.year<1850?`<div><svg viewBox="-12 -12 24 24"><use href="#s-letter" class="lg-mine"/></svg>Bills between your branches</div>`:''}
  <div><svg viewBox="-12 -12 24 24"><use href="#s-banner" style="color:${RIVAL_COLORS[0]}"/></svg>A rival house</div>
  <div><svg viewBox="-12 -12 24 24"><circle r="8" class="lg-ring"/><circle r="3" class="lg-dot"/></svg>Centre of gravity</div>
  <div><svg viewBox="-12 -12 24 24"><circle r="10" class="lg-halo"/></svg>Commerce — grows where you lend</div>
  <div><svg viewBox="-12 -12 24 24"><rect x="-10" y="-8" width="20" height="16" class="lg-fog"/></svg>Unknown to you</div>`; }
