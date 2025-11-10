// FlyCamp console client
// - No video logic (HTML left unchanged)
// - Adds "Depth Camera" to the initialisation flow shown in the GUI
// - Runs connection checks and displays step-by-step results

let selectedGameId = null;
let selectedGameTitle = '';
let selectedGameDesc = '';

/* ------------------------------ Navigation ------------------------------ */
function goToPage(pageId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const page = document.getElementById(pageId);
  if (page) page.classList.add('active');
}

function backToChoose() {
  goToPage('page_choose_game');
}

/* --------------------------- Card slider/select -------------------------- */
function initializeCardSlider(containerSelector) {
  const slider = document.querySelector(containerSelector);
  if (!slider) return;

  const cards = slider.querySelectorAll('.card');
  const body = document.body;

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting && entry.intersectionRatio >= 0.75) {
        const bgColor = entry.target.getAttribute('data-bg-color');
        if (bgColor) body.style.backgroundColor = bgColor;
        entry.target.classList.add('is-active');
      } else {
        entry.target.classList.remove('is-active');
      }
    });
  }, { root: slider, threshold: 0.75 });

  cards.forEach(card => observer.observe(card));

  // Click on card → fill confirm info (no video) → go to confirm page
  cards.forEach(card => {
    card.addEventListener('click', () => {
      selectedGameId    = parseInt(card.getAttribute('data-game-id'), 10) || 1;
      selectedGameTitle = card.getAttribute('data-title') || '';
      selectedGameDesc  = card.getAttribute('data-desc')  || '';

      const titleEl = document.getElementById('chosen-game-title');
      const descEl  = document.getElementById('chosen-game-desc');
      if (titleEl) titleEl.innerText = `You chose: ${selectedGameTitle}`;
      if (descEl)  descEl.innerText  = selectedGameDesc;

      goToPage('page_confirm');
    });
  });

  // Center the middle card instantly
  const middleIndex = Math.floor(cards.length / 2);
  const middleCard = cards[middleIndex];
  if (middleCard) {
    const offset = middleCard.offsetLeft - (slider.clientWidth / 2) + (middleCard.clientWidth / 2);
    slider.scrollLeft = offset;
  }

  // Hook up Confirm button to start checks immediately (no video flow)
  const confirmBtn = document.getElementById('confirm-game-btn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', () => {
      goToPage('page_initializing');
      runConnectionCheckAndStart(3000, false);
    });
  }
}

/* ------------------------- Init steps UI helpers ------------------------- */
function clearSteps() {
  const host = document.getElementById('init-steps');
  if (host) host.innerHTML = '';
}

function addStepRow(name) {
  const host = document.getElementById('init-steps');
  if (!host) return null;
  const row = document.createElement('div');
  row.className = 'step';
  row.innerHTML = `<div>${name}</div><div>…</div>`;
  host.appendChild(row);
  requestAnimationFrame(() => row.classList.add('show'));
  return row;
}

function markRow(row, ok, msg) {
  if (!row) return;
  row.classList.toggle('ok', ok);
  row.classList.toggle('fail', !ok);
  // status cell is the last child div we created
  const statusCell = row.lastChild;
  if (statusCell && statusCell.nodeType === 1) {
    statusCell.textContent = ok ? '✓ OK' : '✗ Failed';
  }
  if (msg) {
    const host = document.getElementById('init-steps');
    if (host) {
      const m = document.createElement('div');
      m.style.fontSize = '12px';
      m.style.opacity  = '0.85';
      m.style.margin   = '4px 0 0 6px';
      m.textContent    = msg;
      host.appendChild(m);
    }
  }
}

/* ----------------------- Connection check + start ------------------------ */
/**
 * Runs server connection checks and animates step results in the GUI.
 * Includes "Depth Camera" in the order, between "Car" and "Drone".
 *
 * delayStartMs: wait time before starting the game if checks succeed
 * skipStart: if true, only store results, do not animate or start
 */
async function runConnectionCheckAndStart(delayStartMs = 0, skipStart = false) {
  try {
    clearSteps();
    const errBox = document.getElementById('init-error');
    const statusEl = document.getElementById('init-status');
    if (errBox) errBox.classList.add('hidden');
    if (statusEl) statusEl.textContent = 'Running connection checks...';

    const res = await fetch('/api/connection_check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game_number: selectedGameId || 1 })
    });
    const data = await res.json();

    // Order includes Depth Camera
    const base = ['Joystick/Gesture', 'Nodes', 'Car', 'Depth Camera', 'Drone'];
    const order = (selectedGameId === 2) ? base : base.filter(n => n !== 'Car');

    const results = [];
    for (const step of (data.steps || [])) {
    const label = step.name;
    const row = addStepRow(label);
    await new Promise(r => setTimeout(r, 200));
    markRow(row, !!step.ok, step.message || '');
    }

    window.__initStoredResults = { results, success: !!data.success };
    window.__initReady   = true;
    window.__initSuccess = !!data.success;

    if (skipStart) return;

    if (!data.success) {
      if (statusEl) statusEl.textContent = 'Initialisation failed.';
      if (errBox) errBox.classList.remove('hidden');
      return;
    }

    if (statusEl) statusEl.textContent = 'Connection OK. Preparing game...';
    if (delayStartMs > 0) {
      await new Promise(resolve => setTimeout(resolve, delayStartMs));
    }

    // Start the game after successful checks
    try {
      const startRes = await fetch('/api/start_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_number: selectedGameId || 1, level_number: 1 })
      });
      const startData = await startRes.json();
      if (!startData.success) {
        if (statusEl) statusEl.textContent = startData.error || 'Failed to launch the game.';
        if (errBox) errBox.classList.remove('hidden');
        return;
      }
      if (statusEl) statusEl.textContent = 'Game started. Good luck!';
      checkGameDone();
    } catch (err) {
      console.error('Error starting game:', err);
      if (statusEl) statusEl.textContent = 'Unexpected error during start.';
      if (errBox) errBox.classList.remove('hidden');
    }
  } catch (e) {
    console.error('Init/start error:', e);
    const statusEl = document.getElementById('init-status');
    if (statusEl) statusEl.textContent = 'Unexpected error during initialisation.';
    const errBox = document.getElementById('init-error');
    if (errBox) errBox.classList.remove('hidden');
  }
}

function retryConnectionCheck() {
  const errBox = document.getElementById('init-error');
  if (errBox) errBox.classList.add('hidden');
  window.__initStarted = false;
  window.__initReady   = false;
  window.__initSuccess = false;
  runConnectionCheckAndStart(3000, false);
}

/* -------------------------- Leaderboard / polling ------------------------- */
function checkGameDone() {
  const intv = setInterval(() => {
    fetch('/game_done')
      .then(r => r.json())
      .then(d => {
        if (d.done) {
          clearInterval(intv);
          showLeaderboard();
        }
      })
      .catch(() => {
        clearInterval(intv);
      });
  }, 1500);
}

function showLeaderboard() {
  goToPage('page16');
  const tbody = document.getElementById('leaderboard-body');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="3">Loading...</td></tr>';
  fetch('/get_leaderboard')
    .then(r => r.json())
    .then(data => {
      const players = (data && data.leaderboard) ? data.leaderboard : [];
      if (players.length <= 3) {
        tbody.innerHTML = '<tr><td colspan="3">All players are on the podium!</td></tr>';
        return;
      }
      tbody.innerHTML = players.slice(3).map((p, i) =>
        `<tr><td>${i + 4}</td><td>${p.name}</td><td>${p.score}</td></tr>`
      ).join('');
    })
    .catch(() => {
      tbody.innerHTML = '<tr><td colspan="3">Error loading leaderboard.</td></tr>';
    });
}

/* --------------------------------- Boot ---------------------------------- */
window.onload = () => {
  // Default to game select page
  goToPage('page_choose_game');
  initializeCardSlider('#game-card-container');
};

// Expose globally for inline handlers in HTML
window.goToPage = goToPage;
window.retryConnectionCheck = retryConnectionCheck;
window.backToChoose = backToChoose;
