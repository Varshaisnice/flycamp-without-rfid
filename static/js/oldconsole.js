let username = "";
let rfidTag = "";              // token_id (integer from backend)
let selectedLevel = null;
let selectedGame = null;       // 1 = Hover & Seek, 2 = Hue/ColourChaos
let scanInterval = null;
let scanningActive = true;

// ---------- Navigation / Screen helpers ----------
function goToPage(pageNumber) {
  const screens = document.querySelectorAll(".screen");
  screens.forEach(screen => screen.classList.remove("active"));

  const page = document.getElementById(`page${pageNumber}`);
  if (page) page.classList.add("active");

  if (pageNumber === 1) {
    // Reset to waiting state
    username = "";
    rfidTag = "";
    selectedLevel = null;
    selectedGame = null;
    const tokenInput = document.getElementById("rfidToken");
    if (tokenInput) tokenInput.value = "";
    const loader1 = document.getElementById("loader1");
    if (loader1) loader1.innerText = "Waiting for token...";
    scanningActive = true; // resume auto scanning
  }

  if (pageNumber === 2) {
    document.getElementById("greeting").innerText = `Hi ${username}!`;
    document.getElementById("user-info").innerText = `Token number: ${rfidTag}`;
  }
}

// Go to the init screen (separate from numeric pages)
function goToInitPage() {
  const screens = document.querySelectorAll(".screen");
  screens.forEach(screen => screen.classList.remove("active"));
  const initPage = document.getElementById("page_init");
  if (initPage) initPage.classList.add("active");
}

// ---------- RFID Scan ----------
function beginAutoScan() {
  const loader = document.getElementById("loader1");
  if (loader) loader.innerText = "Waiting for token...";

  scanInterval = setInterval(() => {
    if (!scanningActive) return;

    fetch('/scan_rfid')
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          username = data.name;
          rfidTag = data.token_id; // integer
          const tokenInput = document.getElementById("rfidToken");
          if (tokenInput) tokenInput.value = rfidTag;

          if (loader) loader.innerText = `Hi ${username}!`;
          setTimeout(() => goToPage(2), 1000);
        }
      })
      .catch(err => console.error("RFID scan error:", err));
  }, 5000); // 5s between attempts
}

function confirmPlayer() {
  scanningActive = false; // stop future scans
  if (scanInterval) clearInterval(scanInterval);
  goToPage(4); // Game selection
}

// ---------- Init Screen Flow ----------
function showInitUIStatus(msg, isError = false) {
  const status = document.getElementById("init-status");
  const errBox = document.getElementById("init-error");
  const errText = document.getElementById("init-error-text");

  if (status) status.textContent = msg || "";
  if (errBox) {
    if (isError) {
      errBox.classList.remove("hidden");
      if (errText && msg) errText.textContent = msg;
    } else {
      errBox.classList.add("hidden");
    }
  }
}

function writeRFIDTokenToFile() {
  // Backend expects { token_id: <int> }
  return fetch('/write_rfid_token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token_id: rfidTag })
  }).then(res => res.json()).catch(() => ({}));
}

async function runConnectionCheckAndStart() {
  try {
    showInitUIStatus("Running connection checks...");
    const checkRes = await fetch('/api/connection_check', { method: 'POST' });
    const checkData = await checkRes.json();

    if (!checkData.success) {
      showInitUIStatus("Initialisation failed. Please retry.", true);
      return;
    }

    // Connection OK – write token (so the game can read it) and then start the game
    showInitUIStatus("Connection OK. Preparing game...");
    await writeRFIDTokenToFile();

    const payload = { game_number: selectedGame, level_number: selectedLevel };
    const startRes = await fetch('/api/start_game', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const startData = await startRes.json();

    if (!startData.success) {
      const msg = startData.error || "Failed to launch the game.";
      showInitUIStatus(msg, true);
      return;
    }

    // Game launched – start polling for completion
    showInitUIStatus("Game started. Good luck!");
    checkGameDone();
  } catch (e) {
    console.error("Init/start error:", e);
    showInitUIStatus("Unexpected error during initialisation.", true);
  }
}

function retryConnectionCheck() {
  // Called by the Retry button on the init screen
  showInitUIStatus("Retrying connection checks...");
  runConnectionCheckAndStart();
}

function backToLevelSelect() {
  // Send user back to the correct level-select page
  if (selectedGame === 1) {
    goToPage(13); // Hover & Seek level page
  } else if (selectedGame === 2) {
    goToPage(12); // Hue/ColourChaos level page
  } else {
    goToPage(4);  // game selection fallback
  }
}

// ---------- Level Selection (Game 1) ----------
function startGameLevel(level) {
  // Game 1: Hover & Seek (both levels 1 and 2)
  selectedGame = 1;
  selectedLevel = level;

  // Move to Initialising page (AFTER selection)
  goToInitPage();
  // Kick off the init flow
  runConnectionCheckAndStart();
}

// ---------- Level Selection (Game 2) ----------
function startHueGameLevel(level) {
  // Game 2: Level 1 -> huestheboss.py, Level 2 -> colourchaos.py
  selectedGame = 2;
  selectedLevel = level;

  // Move to Initialising page (AFTER selection)
  goToInitPage();
  // Kick off the init flow
  runConnectionCheckAndStart();
}

// ---------- Game done polling ----------
function checkGameDone() {
  // Poll every 1.5s for /game_done flag
  const interval = setInterval(() => {
    fetch('/game_done')
      .then(res => res.json())
      .then(data => {
        if (data.done) {
          clearInterval(interval);
          showLeaderboard();
        }
      })
      .catch(err => {
        console.error("Error checking game status, stopping poll:", err);
        clearInterval(interval);
      });
  }, 1500);
}

// ---------- Leaderboard ----------
function showLeaderboard() {
  goToPage(16);

  fetch('/get_leaderboard')
    .then(res => res.json())
    .then(data => {
      if (!data.success || !data.leaderboard) {
        console.error("Failed to load leaderboard.");
        const tbody = document.getElementById('leaderboard-body');
        if (tbody) tbody.innerHTML = '<tr><td colspan="3">Unable to load leaderboard.</td></tr>';
        return;
      }

      const players = data.leaderboard;

      // Podium
      const podiumSpots = [
        { player: players[0], selector: '.first' },
        { player: players[1], selector: '.second' },
        { player: players[2], selector: '.third' }
      ];

      podiumSpots.forEach(spot => {
        const avatarElement = document.querySelector(`${spot.selector} .avatar`);
        const scoreElement = document.querySelector(`${spot.selector} .score`);
        if (spot.player) {
          if (avatarElement) avatarElement.textContent = spot.player.name;
          if (scoreElement) scoreElement.textContent = spot.player.score;
        } else {
          if (avatarElement) avatarElement.textContent = '';
          if (scoreElement) scoreElement.textContent = '';
        }
      });

      // Table rows (4th and onwards)
      const leaderboardBody = document.getElementById('leaderboard-body');
      if (!leaderboardBody) return;

      if (players.length <= 3) {
        leaderboardBody.innerHTML =
          '<tr><td colspan="3">All players are on the podium!</td></tr>';
        return;
      }

      // Build rows
      const rows = players.slice(3).map((p, idx) => {
        const rank = idx + 4;
        return `<tr>
                  <td>${rank}</td>
                  <td>${p.name}</td>
                  <td>${p.score}</td>
                </tr>`;
      }).join("");
      leaderboardBody.innerHTML = rows;
    })
    .catch(err => {
      console.error("Leaderboard fetch error:", err);
      const tbody = document.getElementById('leaderboard-body');
      if (tbody) tbody.innerHTML = '<tr><td colspan="3">Error loading leaderboard.</td></tr>';
    });
}

// ---------- Boot ----------
window.onload = beginAutoScan;
