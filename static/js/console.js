// FlyCamp – base functionality with videos removed
//
// Video playback/preview overlay removed. Confirming a game now
// immediately runs connection checks and shows the initialising page.

let username = "";
let rfidTag = "";
let selectedGameId = null;
let selectedGameTitle = "";
let selectedGameDesc = "";
let scanInterval = null;
let scanningActive = true;

// Controller toggle (UI-only text swap)
let controllerMode = 'joystick'; // default
const WORD_A = 'Joystick Controller';
const WORD_B = 'Hand Gesture Controller';

// Helpers to query DOM
const qs  = (s, r = document) => r.querySelector(s);
const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));

/* ------------------------------------------------------------------ */
/* Navigation                                                         */
/* ------------------------------------------------------------------ */

function goToPage(id){
  qsa('.screen').forEach(s => s.classList.remove('active'));
  const pageEl = qs(`#${id}`);
  if (pageEl) pageEl.classList.add('active');
  document.body.style.backgroundColor =
    getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
  if (id === 'page_choose_game') {
    const slider = qs('#game-card-container');
    if (slider && typeof slider.centerOnSecondCard === 'function') {
      slider.centerOnSecondCard();
    }
  }
}

function backToChoose(){
  goToPage('page_choose_game');
}

/* ------------------------------------------------------------------ */
/* Controller toggle                                                   */
/* ------------------------------------------------------------------ */

function updateControllerLabels(){
  const root = document.body;
  const toWord   = (controllerMode === 'joystick') ? WORD_A : WORD_B;
  const fromWord = (controllerMode === 'joystick') ? WORD_B : WORD_A;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node){
      const txt = node.nodeValue;
      if (!txt) return NodeFilter.FILTER_SKIP;
      const lower = txt.toLowerCase();
      if (lower.includes(WORD_A.toLowerCase()) ||
          lower.includes(WORD_B.toLowerCase())) {
        const p = node.parentElement;
        if (p && p.offsetParent !== null) return NodeFilter.FILTER_ACCEPT;
      }
      return NodeFilter.FILTER_SKIP;
    }
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node => {
    let t = node.nodeValue;
    t = t.replace(new RegExp(WORD_A, 'ig'), WORD_A);
    t = t.replace(new RegExp(WORD_B, 'ig'), WORD_B);
    t = t.replace(new RegExp(fromWord, 'ig'), toWord);
    node.nodeValue = t;
  });
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

  // PATCH: Write the correct token_id into rfid_token.txt on confirm
  fetch('/write_rfid_token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token_id: rfidTag })
  }).then(() => {
    goToPage('page_choose_game');
  });
}

/* ------------------------------------------------------------------ */
/* Game selection slider + SWIPE/DRAG/KEYBOARD logic & selection prevention   */
/* ------------------------------------------------------------------ */

let isDraggingSlider = false;

function initializeCardSlider(selector){
  const slider = qs(selector);
  if (!slider) return;
  const cards = qsa('.card', slider);

  // --- Swiping Helpers ---
  const getCardCenterIndex = () => {
    const centre = slider.scrollLeft + slider.clientWidth / 2;
    let bestIdx = 0, minDist = Infinity;
    cards.forEach((card, i) => {
      const cCentre = card.offsetLeft + card.offsetWidth / 2;
      const dist = Math.abs(cCentre - centre);
      if (dist < minDist) { minDist = dist; bestIdx = i; }
    });
    return bestIdx;
  };

  const scrollToIndex = (i) => {
    i = Math.max(0, Math.min(cards.length-1, i));
    const card = cards[i];
    if (!card) return;
    const offset = card.offsetLeft - (slider.clientWidth - card.clientWidth)/2;
    slider.scrollTo({ left: offset, behavior: 'smooth' });
  };

  function updateActiveCard(){
    const idx = getCardCenterIndex();
    cards.forEach((c, i) => {
      if (i === idx){
        c.classList.add('is-active');
      } else {
        c.classList.remove('is-active');
      }
    });
  }

  let scrollTimeout;
  slider.addEventListener('scroll', () => {
    if (scrollTimeout) clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(updateActiveCard, 80);
  });

  // --- Touch swipe ---
  let touchStartX = 0, touchStartY = 0, touchStartTime = 0;
  slider.addEventListener('touchstart', (e) => {
    slider.classList.add('dragging');
    document.body.style.userSelect = 'none'; // Prevent selection on touch
    if (e.touches && e.touches.length === 1) {
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchStartTime = Date.now();
    }
  }, { passive: false });

  slider.addEventListener('touchend', (e) => {
    slider.classList.remove('dragging');
    document.body.style.userSelect = ''; // Restore after drag
    if (!e.changedTouches || e.changedTouches.length === 0) return;
    const dx = e.changedTouches[0].clientX - touchStartX;
    const dy = e.changedTouches[0].clientY - touchStartY;
    const dt = Date.now() - touchStartTime;
    const isHorizontal = Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 30 && dt < 650;
    if (isHorizontal) {
      const current = getCardCenterIndex();
      if (dx < 0) { scrollToIndex(current + 1); }
      else { scrollToIndex(current - 1); }
    } else {
      scrollToIndex(getCardCenterIndex());
    }
  });

  // --- Mouse drag ---
  let dragStartX = 0;
  slider.addEventListener('mousedown', (e) => {
    isDraggingSlider = true;
    dragStartX = e.clientX;
    slider.classList.add('dragging');
    document.body.style.userSelect = 'none'; // Prevent selection on drag
  });
  window.addEventListener('mouseup', (e) => {
    if (!isDraggingSlider) return;
    isDraggingSlider = false;
    slider.classList.remove('dragging');
    document.body.style.userSelect = '';
    const dx = e.clientX - dragStartX;
    if (Math.abs(dx) > 30) {
      const current = getCardCenterIndex();
      if (dx < 0) scrollToIndex(current + 1);
      else scrollToIndex(current - 1);
    } else {
      scrollToIndex(getCardCenterIndex());
    }
  });

  // --- Card click ---
  cards.forEach(card => {
    card.addEventListener('click', () => {
      selectedGameId    = parseInt(card.getAttribute('data-game-id'), 10);
      selectedGameTitle = card.getAttribute('data-title') || '';
      selectedGameDesc  = card.getAttribute('data-desc')  || '';
      const titleEl = qs('#chosen-game-title');
      const descEl  = qs('#chosen-game-desc');
      if (titleEl) titleEl.textContent = `You chose: ${selectedGameTitle}`;
      if (descEl)  descEl.textContent  = selectedGameDesc;
      goToPage('page_confirm');
      window.__initStarted = false;
      window.__initReady   = false;
      window.__initSuccess = false;
    });
  });

  // --- Keyboard navigation ---
  slider.setAttribute('tabindex', '0');
  slider.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      scrollToIndex(getCardCenterIndex() - 1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      scrollToIndex(getCardCenterIndex() + 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      scrollToIndex(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      scrollToIndex(cards.length - 1);
    }
  });

  function centreOnSecondCard(){
    const second = cards[1];
    if (!second) return;
    const offset = second.offsetLeft - (slider.clientWidth / 2) + (second.clientWidth / 2);
    slider.scrollLeft = offset;
    updateActiveCard();
  }

  slider.centerOnSecondCard = centreOnSecondCard;
  setTimeout(centreOnSecondCard, 80);

  setTimeout(() => { updateActiveCard(); scrollToIndex(getCardCenterIndex()); }, 120);
}

/* ------------------------------------------------------------------ */
/* Confirm & simplified flow (videos removed)                         */
/* ------------------------------------------------------------------ */
function registerPreviewOverlay(){
  const confirmBtn = qs('#confirm-game-btn');
  const closeBtn   = qs('#close-video');
  if (!confirmBtn) return;

  confirmBtn.addEventListener('click', () => {
    if (selectedGameId === 1 || selectedGameId === 3){
      goToPage('page_choose_controller');
    } else {
      controllerMode = 'gesture';
      goToPage('page_initializing');
      runConnectionCheckAndStart(3000, false);
    }
  });

  if (closeBtn){
    closeBtn.addEventListener('click', () => {
      goToPage('page_choose_game');
    });
  }
}

function clearSteps(){
  const host = qs('#init-steps');
  if (host) host.innerHTML = '';
}

function addStepRow(name){
  const row = document.createElement('div');
  row.className = 'step';
  row.innerHTML = `<div>${name}</div><div>…</div>`;
  qs('#init-steps').appendChild(row);
  requestAnimationFrame(() => row.classList.add('show'));
  return row;
}

function markRow(row, ok, msg){
  row.classList.toggle('ok', ok);
  row.classList.toggle('fail', !ok);
  row.lastChild.textContent = ok ? '✓ OK' : '✗ Failed';
  if (msg){
    const m = document.createElement('div');
    m.style.fontSize = '12px';
    m.style.opacity  = '0.85';
    m.style.margin   = '4px 0 0 6px';
    m.textContent    = msg;
    qs('#init-steps').appendChild(m);
  }
}

async function runConnectionCheckAndStart(delayStartMs = 0, skipStart = false){
  try {
    clearSteps();
    const errBox = qs('#init-error');
    if (errBox) errBox.classList.add('hidden');
    const statusEl = qs('#init-status');
    if (statusEl) statusEl.textContent = 'Running connection checks...';

    const res  = await fetch('/api/connection_check', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ game_number: selectedGameId || 1, controller: controllerMode })
    });
    const data = await res.json();

    const base = ['Joystick/Gesture', 'Nodes', 'Car', 'Drone'];
    const order = (selectedGameId === 2) ? base : base.filter(n => n !== 'Car');

    const results = [];
    for (const name of order){
      const step = (data.steps || []).find(s => s.name === name);
      if (!step) continue;
      let label;
      if (name === 'Joystick/Gesture'){
        label = (controllerMode === 'joystick') ? 'Joystick Controller' : 'Hand Gesture Controller';
      } else {
        label = step.name;
      }
      results.push({ displayName: label, ok: !!step.ok, message: step.message || '' });
      if (!skipStart){
        const row = addStepRow(label);
        await new Promise(r => setTimeout(r, 200));
        markRow(row, !!step.ok, step.message || '');
      }
    }

    window.__initStoredResults = { results: results, success: !!data.success };
    window.__initReady   = true;
    window.__initSuccess = !!data.success;

    if (skipStart){ return; }

    if (!data.success){
      if (statusEl) statusEl.textContent = 'Initialisation failed.';
      if (errBox) errBox.classList.remove('hidden');
      return;
    }

    if (statusEl) statusEl.textContent = 'Connection OK. Preparing game...';
    if (delayStartMs > 0){
      await new Promise(resolve => setTimeout(resolve, delayStartMs));
    }
    try {
      await fetch('/write_rfid_token', {
        method:'POST',
        headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({ token_id: rfidTag })
      });
      const startRes  = await fetch('/api/start_game', {
        method:'POST',
        headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({ game_number: selectedGameId || 1, level_number: 1, controller: controllerMode })
      });
      const startData = await startRes.json();
      if (!startData.success){
        if (statusEl) statusEl.textContent = startData.error || 'Failed to launch the game.';
        if (errBox) errBox.classList.remove('hidden');
        return;
      }
      if (statusEl) statusEl.textContent = 'Game started. Good luck!';
      checkGameDone();
    } catch (err) {
      console.error('Unexpected error during start:', err);
      if (statusEl) statusEl.textContent = 'Unexpected error during start.';
      if (errBox) errBox.classList.remove('hidden');
    }
  } catch (e){
    console.error('Init/start error:', e);
    const statusEl = qs('#init-status');
    if (statusEl) statusEl.textContent = 'Unexpected error during initialisation.';
    const errBox = qs('#init-error');
    if (errBox) errBox.classList.remove('hidden');
  }
}

function showStoredInitResultsSequentially(){
  const stored = window.__initStoredResults;
  if (!stored || !stored.results) return;
  clearSteps();
  const errBox = qs('#init-error');
  if (errBox) errBox.classList.add('hidden');
  const statusEl = qs('#init-status');
  if (statusEl) statusEl.textContent = 'Running connection checks...';
  const steps = stored.results;
  let idx = 0;
  function displayNext(){
    if (idx < steps.length){
      const step = steps[idx++];
      const row  = addStepRow(step.displayName);
      setTimeout(() => {
        markRow(row, step.ok, step.message);
        setTimeout(displayNext, 200);
      }, 200);
    } else {
      if (!stored.success){
        if (statusEl) statusEl.textContent = 'Initialisation failed.';
        if (errBox) errBox.classList.remove('hidden');
      } else {
        if (statusEl) statusEl.textContent = 'Connection OK. Preparing game...';
      }
    }
  }
  displayNext();
}

function retryConnectionCheck(){
  const errBox = qs('#init-error');
  if (errBox) errBox.classList.add('hidden');
  window.__initStarted = false;
  window.__initReady   = false;
  window.__initSuccess = false;
  runConnectionCheckAndStart(3000, false);
}

/* ------------------------------------------------------------------ */
/* Leaderboard                                                        */
/* ------------------------------------------------------------------ */

function checkGameDone(){
  const intv = setInterval(() => {
    fetch('/game_done')
      .then(r => r.json())
      .then(d => {
        if (d.done){
          clearInterval(intv);
          showLeaderboard();
        }
      })
      .catch(err => {
        clearInterval(intv);
      });
  }, 1500);
}

function showLeaderboard(){
  goToPage('page16');
  const tbody = qs('#leaderboard-body');
  if (!tbody) return;
  ['first','second','third'].forEach(cls => {
    const pod = qs('.pod.' + cls);
    if (pod){
      const nameEl  = pod.querySelector('.pod-name');
      const scoreEl = pod.querySelector('.pod-score');
      if (nameEl)  nameEl.textContent  = '';
      if (scoreEl) scoreEl.textContent = '';
    }
  });
  tbody.innerHTML = '<tr><td colspan="3">Loading...</td></tr>';
  fetch('/get_leaderboard')
    .then(r => r.json())
    .then(data => {
      const players = (data && data.leaderboard) ? data.leaderboard : [];
      const podium  = [players[0], players[1], players[2]];
      ['first','second','third'].forEach((cls, idx) => {
        const pod   = qs('.pod.' + cls);
        const player = podium[idx];
        if (pod){
          const nameEl  = pod.querySelector('.pod-name');
          const scoreEl = pod.querySelector('.pod-score');
          if (nameEl)  nameEl.textContent  = player ? player.name  : '';
          if (scoreEl) scoreEl.textContent = player ? player.score : '';
        }
      });
      if (players.length <= 3){
        tbody.innerHTML = '<tr><td colspan="3">All players are on the podium!</td></tr>';
        return;
      }
      tbody.innerHTML = players.slice(3).map((p,i) =>
        `<tr><td>${i+4}</td><td>${p.name}</td><td>${p.score}</td></tr>`
      ).join('');
    })
    .catch(err => {
      tbody.innerHTML = '<tr><td colspan="3">Error loading leaderboard.</td></tr>';
    });
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
window.retryConnectionCheck = retryConnectionCheck;
window.selectController = function(mode){
  controllerMode = (mode === 'gesture') ? 'gesture' : 'joystick';
  updateControllerLabels();
  goToPage('page_initializing');
  runConnectionCheckAndStart(3000, false);
};
window.backToChoose = backToChoose;
window.backToHome  = function(){
  goToPage('page1');
  if (scanInterval) clearInterval(scanInterval);
  scanningActive = true;
  beginAutoScan();
};
