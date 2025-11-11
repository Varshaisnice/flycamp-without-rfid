// FlyCamp – unified version (RFID scan + game flow + initialization)

console.log('Loaded console.js version: v2');



let username = "";
let rfidTag = "";
let selectedGameId = null;
let selectedGameTitle = "";
let selectedGameDesc = "";
let scanInterval = null;
let scanningActive = true;

// Controller toggle
let controllerMode = 'joystick';
const WORD_A = 'Joystick Controller';
const WORD_B = 'Hand Gesture Controller';

// DOM helpers
const qs  = (s, r = document) => r.querySelector(s);
const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));

/* ------------------------------------------------------------------ */
/* Navigation                                                         */
/* ------------------------------------------------------------------ */
function goToPage(id){
  qsa('.screen').forEach(s => s.classList.remove('active'));
  const pageEl = qs(`#${id}`);
  if (pageEl) pageEl.classList.add('active');
  if (id === 'page_choose_game') {
    const slider = qs('#game-card-container');
    if (slider && typeof slider.centerOnSecondCard === 'function')
      slider.centerOnSecondCard();
  }
}

function backToChoose(){ goToPage('page_choose_game'); }

/* ------------------------------------------------------------------ */
/* Controller toggle                                                  */
/* ------------------------------------------------------------------ */
function updateControllerLabels(){
  const toWord   = (controllerMode === 'joystick') ? WORD_A : WORD_B;
  const fromWord = (controllerMode === 'joystick') ? WORD_B : WORD_A;
  document.body.innerHTML = document.body.innerHTML
    .replace(new RegExp(fromWord, 'ig'), toWord);
}

function registerControllerToggle(){
  const btn = qs('#logo-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    controllerMode = (controllerMode === 'joystick') ? 'gesture' : 'joystick';
    updateControllerLabels();
  });
}

/* ------------------------------------------------------------------ */
/* RFID scanning                                                      */
/* ------------------------------------------------------------------ */
function beginAutoScan(){
  const loader = qs('#loader1');
  if (loader) loader.textContent = 'Waiting for token...';
  scanInterval = setInterval(() => {
    if (!scanningActive) return;
    fetch('/scan_rfid')
      .then(r => r.json())
      .then(d => {
        if (d.success){
          username = d.name;
          rfidTag  = d.token_id;
          if (loader) loader.textContent = `Hi ${username}!`;
          setTimeout(() => {
            const greetingEl = qs('#greeting');
            const userInfoEl = qs('#user-info');
            if (greetingEl) greetingEl.textContent = `Hi ${username}!`;
            if (userInfoEl) userInfoEl.textContent = `Token number: ${rfidTag}`;
            goToPage('page2');
          }, 600);
        }
      })
      .catch(err => console.error('RFID scan error:', err));
  }, 5000);
}

function confirmPlayer(){
  scanningActive = false;
  if (scanInterval) clearInterval(scanInterval);
  fetch('/write_rfid_token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token_id: rfidTag })
  }).then(() => goToPage('page_choose_game'));
}

/* ------------------------------------------------------------------ */
/* Game selection slider                                              */
/* ------------------------------------------------------------------ */
function initializeCardSlider(selector){
  const slider = qs(selector);
  if (!slider) return;
  const cards = qsa('.card', slider);
  const getCardCenterIndex = () => {
    const centre = slider.scrollLeft + slider.clientWidth / 2;
    let bestIdx = 0, minDist = Infinity;
    cards.forEach((c, i) => {
      const dist = Math.abs((c.offsetLeft + c.offsetWidth / 2) - centre);
      if (dist < minDist){ minDist = dist; bestIdx = i; }
    });
    return bestIdx;
  };
  const scrollToIndex = (i) => {
    i = Math.max(0, Math.min(cards.length - 1, i));
    const c = cards[i];
    if (!c) return;
    const offset = c.offsetLeft - (slider.clientWidth - c.clientWidth)/2;
    slider.scrollTo({ left: offset, behavior: 'smooth' });
  };
  function updateActiveCard(){
    const idx = getCardCenterIndex();
    cards.forEach((c, i) => c.classList.toggle('is-active', i === idx));
  }
  slider.addEventListener('scroll', () => {
    clearTimeout(slider._scrollT);
    slider._scrollT = setTimeout(updateActiveCard, 80);
  });
  // Touch
  let sx=0, sy=0, st=0;
  slider.addEventListener('touchstart', e => {
    if (e.touches.length === 1){ sx=e.touches[0].clientX; sy=e.touches[0].clientY; st=Date.now(); }
  }, { passive: false });
  slider.addEventListener('touchend', e => {
    if (!e.changedTouches.length) return;
    const dx=e.changedTouches[0].clientX-sx, dy=e.changedTouches[0].clientY-sy;
    if (Math.abs(dx)>Math.abs(dy)&&Math.abs(dx)>30&&Date.now()-st<650)
      scrollToIndex(getCardCenterIndex()+(dx<0?1:-1));
    else scrollToIndex(getCardCenterIndex());
  });
  // Mouse
  let dragging=false,startX=0;
  slider.addEventListener('mousedown',e=>{dragging=true;startX=e.clientX;});
  window.addEventListener('mouseup',e=>{
    if(!dragging)return;dragging=false;
    const dx=e.clientX-startX;
    if(Math.abs(dx)>30)scrollToIndex(getCardCenterIndex()+(dx<0?1:-1));
    else scrollToIndex(getCardCenterIndex());
  });
  cards.forEach(c=>{
    c.addEventListener('click',()=>{
      selectedGameId=parseInt(c.dataset.gameId,10);
      selectedGameTitle=c.dataset.title||'';
      selectedGameDesc=c.dataset.desc||'';
      qs('#chosen-game-title').textContent=`You chose: ${selectedGameTitle}`;
      qs('#chosen-game-desc').textContent=selectedGameDesc;
      goToPage('page_confirm');
      window.__initStarted=false;window.__initReady=false;window.__initSuccess=false;
    });
  });
  slider.centerOnSecondCard = ()=>{
    const s=cards[1];if(!s)return;
    slider.scrollLeft=s.offsetLeft-slider.clientWidth/2+s.clientWidth/2;
    updateActiveCard();
  };
  setTimeout(slider.centerOnSecondCard,80);
}

/* ------------------------------------------------------------------ */
/* Confirm flow (no videos)                                           */
/* ------------------------------------------------------------------ */
function registerPreviewOverlay(){
  const confirmBtn = qs('#confirm-game-btn');
  if (!confirmBtn) return;
  confirmBtn.addEventListener('click', () => {
    if (selectedGameId === 1 || selectedGameId === 3)
      goToPage('page_choose_controller');
    else {
      controllerMode = 'gesture';
      goToPage('page_initializing');
      runConnectionCheckAndStart(3000, false);
    }
  });
}

/* ------------------------------------------------------------------ */
/* Initialization + Node Checks                                       */
/* ------------------------------------------------------------------ */
function clearSteps(){ const h=qs('#init-steps'); if(h) h.innerHTML=''; }
function addStepRow(name){
  const row=document.createElement('div');
  row.className='step';
  row.innerHTML=`<div>${name}</div><div>…</div>`;
  qs('#init-steps').appendChild(row);
  requestAnimationFrame(()=>row.classList.add('show'));
  return row;
}
function markRow(row,ok,msg){
  row.classList.toggle('ok',ok);
  row.classList.toggle('fail',!ok);
  row.lastChild.textContent=ok?'✓ OK':'✗ Failed';
  if(msg){
    const m=document.createElement('div');
    m.style.fontSize='12px';m.style.opacity='0.85';m.style.margin='4px 0 0 6px';
    m.textContent=msg;qs('#init-steps').appendChild(m);
  }
}

async function runConnectionCheckAndStart(delay=0){
  try{
    clearSteps();
    const statusEl=qs('#init-status');
    const errBox=qs('#init-error'); if(errBox) errBox.classList.add('hidden');
    if(statusEl) statusEl.textContent='Running connection checks...';
    const res=await fetch('/api/connection_check',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({game_number:selectedGameId||1,controller:controllerMode})});
    const data=await res.json();
    const order=(selectedGameId===2)?['Joystick/Gesture','Nodes','Car','Drone']
                :['Joystick/Gesture','Nodes','Drone'];
    for(const name of order){
      const step=(data.steps||[]).find(s=>s.name===name);
      if(!step)continue;
      const label=(name==='Joystick/Gesture')?
        ((controllerMode==='joystick')?'Joystick Controller':'Hand Gesture Controller'):step.name;
      const row=addStepRow(label);
      await new Promise(r=>setTimeout(r,200));
      markRow(row,!!step.ok,step.message||'');
    }
    if(!data.success){
      if(statusEl)statusEl.textContent='Initialisation failed.';
      if(errBox)errBox.classList.remove('hidden');return;
    }
    if(statusEl)statusEl.textContent='Connection OK. Preparing game...';
    await new Promise(r=>setTimeout(r,delay));
    await fetch('/write_rfid_token',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token_id:rfidTag})});
    const startRes=await fetch('/api/start_game',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({game_number:selectedGameId||1,level_number:1,controller:controllerMode})});
    const startData=await startRes.json();
    if(!startData.success){
      if(statusEl)statusEl.textContent=startData.error||'Failed to launch.';
      if(errBox)errBox.classList.remove('hidden');return;
    }
    if(statusEl)statusEl.textContent='Game started. Good luck!';
    checkGameDone();
  }catch(e){
    console.error('Init error:',e);
    const s=qs('#init-status'); if(s)s.textContent='Unexpected init error.';
    const ebox=qs('#init-error'); if(ebox)ebox.classList.remove('hidden');
  }
}

/* ------------------------------------------------------------------ */
/* Leaderboard                                                        */
/* ------------------------------------------------------------------ */
function checkGameDone(){
  const intv=setInterval(()=>{
    fetch('/game_done').then(r=>r.json()).then(d=>{
      if(d.done){clearInterval(intv);showLeaderboard();}
    }).catch(()=>clearInterval(intv));
  },1500);
}
function showLeaderboard(){
  goToPage('page16');
  const tbody=qs('#leaderboard-body'); if(!tbody)return;
  ['first','second','third'].forEach(cls=>{
    const pod=qs('.pod.'+cls);
    if(pod){pod.querySelector('.pod-name').textContent='';
      pod.querySelector('.pod-score').textContent='';}
  });
  tbody.innerHTML='<tr><td colspan="3">Loading...</td></tr>';
  fetch('/get_leaderboard').then(r=>r.json()).then(data=>{
    const players=data.leaderboard||[];
    ['first','second','third'].forEach((cls,idx)=>{
      const pod=qs('.pod.'+cls),p=players[idx];
      if(pod&&p){
        pod.querySelector('.pod-name').textContent=p.name;
        pod.querySelector('.pod-score').textContent=p.score;
      }
    });
    if(players.length<=3){
      tbody.innerHTML='<tr><td colspan="3">All players on podium!</td></tr>';return;
    }
    tbody.innerHTML=players.slice(3).map((p,i)=>
      `<tr><td>${i+4}</td><td>${p.name}</td><td>${p.score}</td></tr>`).join('');
  }).catch(()=>tbody.innerHTML='<tr><td colspan="3">Error loading leaderboard.</td></tr>');
}

/* ------------------------------------------------------------------ */
/* Boot                                                               */
/* ------------------------------------------------------------------ */
window.onload = function(){
  registerControllerToggle();
  beginAutoScan();
  initializeCardSlider('#game-card-container');
  registerPreviewOverlay();
};
window.goToPage = goToPage;
window.confirmPlayer = confirmPlayer;
window.retryConnectionCheck = ()=>runConnectionCheckAndStart(3000,false);
window.selectController = function(mode){
  controllerMode=(mode==='gesture')?'gesture':'joystick';
  updateControllerLabels();
  goToPage('page_initializing');
  runConnectionCheckAndStart(3000,false);
};
window.backToChoose = backToChoose;
window.backToHome  = function(){
  goToPage('page1');
  if(scanInterval)clearInterval(scanInterval);
  scanningActive=true;
  beginAutoScan();
};

/* ------------------------------------------------------------------ */
/* Rules Injection on Game Selection (Page 4)                         */
/* ------------------------------------------------------------------ */

let selectedGame = null;

document.querySelectorAll('.card').forEach(card => {
  card.addEventListener('click', () => {
    selectedGame = {
      title: card.getAttribute('data-title'),
      templateId: card.getAttribute('data-desc').replace('#rules-', 'rules-template-')
    };

    // Update title & clear description text
    const titleEl = document.getElementById('chosen-game-title');
    const descEl  = document.getElementById('chosen-game-desc');
    if (titleEl) titleEl.textContent = `You chose: ${selectedGame.title}`;
    if (descEl)  descEl.textContent  = '';

    // Inject rules into #active-rules
    const rulesContainer = document.getElementById('active-rules');
    rulesContainer.innerHTML = '';

    const template = document.getElementById(selectedGame.templateId);
    if (template) {
      const clone = template.content.cloneNode(true);
      rulesContainer.appendChild(clone);
    }

    goToPage('page_confirm');
  });
});

function confirmGame() {
  if (selectedGame) goToPage('page_choose_controller');
}
/* ------------------------------------------------------------------
   FINAL Initialisation Routine
   - Shows only failed components on detailed page
   - Works with your new HTML page_detailed_init
   ------------------------------------------------------------------ */
function createNodeCheckmarks() {
  const initContainer = document.getElementById('init-steps');
  if (initContainer) initContainer.innerHTML = '';

  const nodes = [
    { id: 'network', name: 'Network' },
    { id: 'camera', name: 'Camera' },
    { id: 'gesture', name: 'Gesture Sensor' },
    { id: 'drone', name: 'Drone Link' },
    { id: 'engine', name: 'Game Engine' }
  ];

  fetch('/api/init', {
    method: 'GET',
    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
  })
  .then(r => r.ok ? r.json() : Promise.reject('Network error'))
  .then(data => {
    nodes.forEach(n => n.status = data[n.id] === true ? 'ok' : 'fail');
  })
  .catch(() => nodes.forEach(n => n.status = 'fail'))
  .finally(() => {
    const failed = nodes.filter(n => n.status === 'fail');

    // === CASE 1: All components OK ===
    if (failed.length === 0) {
      const status = document.getElementById('init-status');
      if (status) status.innerHTML = `<span style="color:#4ade80;">All components initialised successfully!</span>`;
      document.getElementById('start-game-btn')?.classList.remove('hidden');
      document.getElementById('init-spinner').style.display = 'none';
      return;
    }

    // === CASE 2: Failures found – go to detailed init page ===
    goToPage('page_detailed_init');
    const container = document.getElementById('detailed-init-steps');
    const status = document.getElementById('detailed-init-status');
    const errorBox = document.getElementById('detailed-init-error');
    if (!container || !status) return;

    container.innerHTML = '';
    status.innerHTML = `<strong style="color:#ff66ff;">Checking components...</strong>`;

    // Build detailed display
    nodes.forEach((n, i) => {
      const item = document.createElement('div');
      item.className = 'node-item';
      item.style.cssText = `
        display:flex;
        justify-content:space-between;
        align-items:center;
        background:rgba(255,255,255,0.05);
        border-radius:12px;
        padding:14px 18px;
        margin:8px 0;
        border:1px solid ${n.status==='ok'?'#4ade80':'#ff66ff'};
        color:${n.status==='ok'?'#4ade80':'#ff66ff'};
        font-weight:600;
        opacity:0;
        transition:opacity .4s ease;
      `;
      item.innerHTML = `
        <span>${n.name}</span>
        <span>${n.status === 'ok' ? '✓ OK' : '✗ Failed'}</span>
      `;
      container.appendChild(item);
      setTimeout(() => { item.style.opacity = '1'; }, 200 * (i + 1));
    });

    // Update dynamic rules list too
    const rulesList = document.getElementById('rules-list-dynamic');
    if (rulesList) {
      rulesList.innerHTML = nodes.map(n =>
        `<li style="color:${n.status==='ok'?'#4ade80':'#ff66ff'};">
          ${n.name}: ${n.status==='ok'?'Initialised':'Failed'}
        </li>`
      ).join('');
    }

    // Update summary
    status.innerHTML = failed.length === nodes.length
      ? `<strong style="color:#ff66ff;">All components failed to initialise!</strong>`
      : `<strong style="color:#ff66ff;">Failed:</strong> ${failed.map(f=>f.name).join(', ')}`;

    document.querySelector('#page_detailed_init .spinner').style.display = 'none';
    errorBox.classList.remove('hidden');
  });
}

// === Ensure it's triggered when initialization page becomes active ===
document.addEventListener('DOMContentLoaded', () => {
  const initPage = document.getElementById('page_initializing');
  if (initPage && initPage.classList.contains('active')) {
    createNodeCheckmarks();
  }
});
