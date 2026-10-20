import {initializeApp} from 'https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js';
import {getAuth, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged, setPersistence, browserLocalPersistence, browserSessionPersistence} from 'https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js';
const $=s=>document.querySelector(s), text=(s,v)=>{$(s).textContent=v}, esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>n==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(n));
let auth,user,state;
const embeddedBrowser=()=>/\b(CriOS|FxiOS)\b/.test(navigator.userAgent)?false:/(ChatGPT|FBAN|FBAV|Instagram|Line\/|GSA\/)/i.test(navigator.userAgent);
const ios=()=>/iPad|iPhone|iPod/.test(navigator.userAgent);


const ageSeconds=at=>{const ms=Date.parse(at||'');return Number.isFinite(ms)?Math.max(0,Math.floor((Date.now()-ms)/1000)):null};
function operationalAlerts(s){
  const alerts=[],age=ageSeconds(s.snapshot?.at),heartbeat=ageSeconds(s.worker?.at);
  if(!s.credentials_configured)alerts.push({level:'critical',message:'Paper broker credentials are missing. Refresh and orders cannot operate.'});
  if(!s.worker_running)alerts.push({level:'critical',message:'Worker stopped or stale. Broker-held exits may remain active; conditional entries are not assured.'});
  if(s.worker_running&&heartbeat!==null&&heartbeat>25)alerts.push({level:'warning',message:'Worker heartbeat is aging ('+heartbeat+' seconds).'});
  if(age===null)alerts.push({level:'warning',message:'No broker snapshot available. Holdings and cash cannot be verified.'});
  else if(age>120)alerts.push({level:'warning',message:'Account snapshot is '+Math.floor(age/60)+' minutes old. Refresh before making decisions.'});
  if(s.control?.entries_paused!==false)alerts.push({level:'info',message:'New entries are paused; this does not cancel protective exits.'});
  if(s.control?.close_all)alerts.push({level:'warning',message:'Close-all was requested. Verify remaining positions and orders at the broker.'});
  if((s.errors||[]).some(e=>e.order_uncertain))alerts.push({level:'critical',message:'ORDER UNCERTAIN recorded. Reconcile the Alpaca client order ID before resuming.'});
  const last=(s.errors||[])[0];if(last)alerts.push({level:'warning',message:'Most recent recorded error: '+String(last.message||'Unknown error')});
  return alerts;
}
function drawOperations(s){
  const alerts=operationalAlerts(s);
  text('#desk-freshness','Last checked '+new Date().toLocaleTimeString()+' · Worker heartbeat '+(ageSeconds(s.worker?.at)??'unknown')+'s old · Snapshot '+(ageSeconds(s.snapshot?.at)??'unknown')+'s old');
  $('#operational-alerts').innerHTML=alerts.map(a=>'<div class="row"><strong>'+esc(a.level.toUpperCase())+'</strong> · '+esc(a.message)+'</div>').join('')||'<p class="empty">No alerts detected in the latest server status. This does not guarantee broker or market availability.</p>';
}

function toast(v){text('#toast',v);$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,5000)}
async function api(path,body){if(!navigator.onLine)throw Error('Phone offline. Command was not sent.');if(!user)throw Error('Sign in first');const token=await user.getIdToken();const r=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',cache:'no-store',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail||d));return d}
async function copy(d){const v=typeof d==='string'?d:JSON.stringify(d,null,2);try{await navigator.clipboard.writeText(v);toast('Copied')}catch{$('#card-input').value=v;$('#card-input').focus();$('#card-input').select();toast('Clipboard unavailable; text selected in the card field.')}}
function draw(s){state=s;drawOperations(s);const snap=s.snapshot,a=snap?.account,paused=s.control?.entries_paused!==false;text('#connection',s.credentials_configured?'Paper credentials configured and bound to this account.':'Alpaca paper credentials are not configured.');text('#worker-status',s.worker_running?'Worker running':'WORKER STOPPED / STALE');text('#entry-status',paused?'New entries paused':'New entries enabled');text('#snapshot-time',snap?'Snapshot: '+new Date(snap.at).toLocaleString():'No account snapshot');text('#equity',money(a?.equity));text('#cash',money(a?.cash));text('#buying',money(a?.buying_power));const pos=snap?.positions||[];$('#empty-holdings').hidden=pos.length>0;$('#holdings').innerHTML=pos.map(p=>`<tr><td>${esc(p.symbol)}</td><td>${esc(p.qty)}</td><td>${money(p.avg_entry_price)}</td><td>${money(p.market_value)}</td><td>${money(p.unrealized_pl)}</td></tr>`).join('');$('#orders').innerHTML=(snap?.orders||[]).map(o=>`<div class="row">${esc(o.side)} ${esc(o.qty)} ${esc(o.symbol)} · ${esc(o.status)}<small>${esc(o.client_order_id||'external order')} · ${esc(o.id)}</small></div>`).join('')||'<p class="empty">No orders in the last snapshot</p>';$('#fills').innerHTML=(s.fills||[]).map(f=>`<div class="row">${esc(String(f.side).toUpperCase())} ${esc(f.qty)} ${esc(f.symbol)} ${f.price?'@ '+money(f.price):''}<small>${esc(new Date(f.at).toLocaleString())} · ${esc(f.broker_order_id)}</small></div>`).join('')||'<p class="empty">No REASON fills recorded</p>';$('#drafts').innerHTML=(s.cards||[]).map(c=>`<div class="row"><strong>${esc(c.card.card_id)}</strong><small>${esc(c.status)} · ${esc(new Date(c.at).toLocaleString())}</small>${esc(c.card.assessment)}</div>`).join('')||'<p class="empty">No Trade Cards saved</p>';$('#events').innerHTML=(s.events||[]).map(e=>`<div class="row">${esc(e.message)}<small>${esc(new Date(e.at).toLocaleString())} · ${esc(e.kind)}</small></div>`).join('')||'<p class="empty">No worker activity recorded</p>';$('#errors').innerHTML=(s.errors||[]).map(e=>`<div class="row">${esc(e.message)}<small>${esc(e.at)} · ${esc(e.id)}${e.order_uncertain?' · ORDER UNCERTAIN':''}</small></div>`).join('')||'<p class="empty">No recorded connection errors</p>';text('#network',s.worker_running?'Signed in · Worker online':'Signed in · Worker offline')}
async function load(){draw(await api('status'))}
// Poll server status only while the authenticated desk is visible. Never enqueue or replay commands.
setInterval(()=>{if(user&&!document.hidden&&navigator.onLine)load().catch(()=>{text('#desk-freshness','Status refresh failed · displayed data may be stale');text('#network','Connection degraded · data may be stale')})},30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&user&&navigator.onLine)load().catch(()=>text('#desk-freshness','Status refresh failed · data may be stale'))});
$('#check-now').onclick=()=>action($('#check-now'),async()=>{await load()});
async function action(button,fn){button.disabled=true;try{await fn()}catch(e){toast(e.message)}finally{button.disabled=false}}
$('#refresh').onclick=()=>action($('#refresh'),async()=>{await api('refresh',{});await load()});
$('#packet').onclick=()=>action($('#packet'),async()=>{await copy(await api('packet',{}));await load()});
$('#save').onclick=()=>action($('#save'),async()=>{try{const r=await api('cards',JSON.parse($('#card-input').value));text('#result',r.status==='duplicate'?'This exact card was already received.':'Card '+r.status+'. The paper worker will reconcile it.');await load()}catch(e){text('#result',e.message)}});
$('#ask').onclick=()=>toast('Paid AI is not connected. No call or charge occurred.');
$('#pause').onclick=()=>action($('#pause'),async()=>{await api('control/pause',{});await load()});
$('#resume').onclick=()=>action($('#resume'),async()=>{await api('control/resume',{});await load()});
$('#close-all').onclick=()=>action($('#close-all'),async()=>{if(!confirm('Close every paper position and cancel REASON-owned orders? External/manual orders will not be canceled.'))return;await api('control/close-all',{});await load()});
$('#diagnostics').onclick=()=>copy({at:new Date().toISOString(),mode:'paper',worker_running:state?.worker_running,worker:state?.worker,control:state?.control,snapshot_at:state?.snapshot?.at,active_card:state?.active_card?.card?.card_id,errors:state?.errors||[]});
$('#signout').onclick=()=>signOut(auth);
window.addEventListener('offline',()=>text('#network','Phone offline · Data may be stale'));
window.addEventListener('online',()=>{if(user)load().catch(e=>toast(e.message))});
try{const r=await fetch('/api/config',{cache:'no-store'});if(!r.ok)throw Error('Application configuration unavailable');const c=await r.json();auth=getAuth(initializeApp(c.firebase));try{await setPersistence(auth,browserLocalPersistence)}catch{await setPersistence(auth,browserSessionPersistence)};$('#signin').disabled=false;if(ios()&&embeddedBrowser())text('#login-error','You appear to be using an in-app browser. For reliable Google sign-in, open reason.directlinemedical.app directly in Safari.');$('#signin').onclick=()=>action($('#signin'),async()=>{const provider=new GoogleAuthProvider();provider.setCustomParameters({prompt:'select_account'});if(ios()&&embeddedBrowser())throw Error('Google sign-in may fail inside this app browser. Open reason.directlinemedical.app directly in Safari and sign in there.');try{await signInWithPopup(auth,provider)}catch(e){if(ios()&&/auth\/(popup-blocked|popup-closed-by-user|web-storage-unsupported|internal-error|missing-initial-state|operation-not-supported-in-this-environment)/.test(e.code||''))throw Error('iPhone sign-in could not preserve the Google session. Open reason.directlinemedical.app directly in Safari (not an in-app browser), then try again.');throw e}});onAuthStateChanged(auth,async u=>{user=u;if(!u){state=null;$('#desk').hidden=true;$('#login').hidden=false;return}try{const me=await api('me');await load();text('#identity',me.email+' · Private paper account');$('#desk').hidden=false;$('#login').hidden=true;text('#login-error','')}catch(e){text('#login-error',e.message);await signOut(auth)}})}catch(e){text('#login-error',e.message)}
if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});

// Session persistence uses durable local storage when available for Safari/PWA continuity; private API still re-verifies every token.
