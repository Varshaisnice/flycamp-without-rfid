let latestRFID = null;
let latestName = null;

const MAX_NAME_LEN = 32;
let randomPressCount = 0;

const FUN_NAMES = [
  "ROTORRANGER","PROPWASHPRO","YAWMASTER","PITCHPERFECT","ROLLRUNNER",
  "THROTTLEJOCKEY","ESCAPEARTIST","FPVFALCON","LIPOLEGEND","BRUSHLESSBANDIT",
  "GYROGURU","WAYPOINTWIZARD","RTHRANGER","LOITERLORD","SIGNALSEEKER",
  "IMUINSPECTOR","ALTITUDEACE","SKYCONTROLLER","MOTORMAVERICK","CARBONCRAFT",
  "FAILSAFEFOX","GPSNOMAD","TELEMETRYTITAN","FIRMWAREFLINGER","RANGEFINDER",
  "GIMBALGLIDER","QUADCOMMANDER","HEXAHUNTER","OCTOOVERLORD","PIDPIRATE",
  "RATEMODERIDER","HORIZONHERO","ACROARCHER","MAVLINKMAGE","PX4PILOT",
  "ARDUPILOTACE","PROPWASHPATROL","HOVERHAWK","BATTERYBANDIT","BLHELIBARON"
];

const LAME_NAMES = [
  "MYMOMNAMEDME","NAMEBUTTONABUSER","LASTBRAINCELL","OKAYTHISONE","STILLTAPPING",
  "INSERTNAMEHERE","USERNOTFOUND","DEFINITELYNOTABOT","LOADINGNICKNAME","CHOOSEFORMEPLS",
  "OUTOFIDEAS","TAPTAPTAP","BUTTONMASHER","RANDOMNAMEPLEASE","NAMEGOESHERE",
  "TEMPORARYHUMAN","CTRLZCREATIVITY","WHOAMIAGAIN","GENERICNICKNAME","FLYITANYWAY"
];


function setError(msg) {
  const m = document.getElementById('message');
  if (m) m.textContent = msg || '';
}
function clearError() { setError(''); }

function goToScreen(screenId) {
  // 1. --- First, handle all immediate UI and class changes ---
  document.querySelectorAll('.screen').forEach(div => div.classList.remove('active'));
  const targetScreen = document.getElementById(screenId);
  targetScreen.classList.add('active');

  // 2. --- Next, run the drone footer logic synchronously ---
  // This ensures the drone moves INSTANTLY when the function is called.
  const nodeMap = { 'welcome-screen': 0, 'form-screen': 1, 'waiting-screen': 2 };
  const index = nodeMap[screenId];
  const footerNodes = document.querySelectorAll('.footer-node');
  const drone = document.getElementById('footer-drone');

  footerNodes.forEach(n => n.classList.remove('active'));
  if (index !== undefined) {
    footerNodes[index].classList.add('active');
    const targetNode = footerNodes[index];
    const nodeRect = targetNode.getBoundingClientRect();
    const footerRect = document.getElementById('drone-footer').getBoundingClientRect();
    const x = nodeRect.left - footerRect.left + (nodeRect.width / 2) - 25; // 25 is half drone width
    drone.style.left = `${x}px`;
  }

  // 3. --- Finally, run screen-specific logic ---
  // This is where we isolate the complex, asynchronous polling.
  if (screenId === 'form-screen') {
    randomPressCount = 0;
    document.getElementById('name').value = '';
    setError('');
    const keyboardContainer = document.getElementById("keyboard");
    if (keyboardContainer) keyboardContainer.classList.remove('keyboard-visible');
  } else if (screenId === 'waiting-screen') {
    const waitingScreenElement = document.getElementById('waiting-screen');
    const scanTitle = waitingScreenElement.querySelector('.scan-title');

    // Reset UI to its initial scanning state
    waitingScreenElement.classList.add('state-scanning');
    waitingScreenElement.classList.remove('state-scanned');
    if (scanTitle) scanTitle.textContent = "Scanning for your token...";

    latestName = document.getElementById('name').value;

    // --- Start the Polling Process ---
    const pollForRFID = () => {
      fetch('/scan_uid')
        .then(res => {
          if (!res.ok) { throw new Error(`HTTP error! Status: ${res.status}`); }
          return res.json();
        })
        .then(data => {
          if (data.status === 'success') {
            // SUCCESS! Proceed with registration.
            latestRFID = data.token_id;
            fetch('/register', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: latestName, token_id: latestRFID })
            })
            .then(res => res.json())
            .then(result => {
              if (result.status === 'exists') {
                // TOKEN IS TAKEN: Go back to form screen. This recursive call will now
                // correctly trigger the drone footer logic at the top of the function.
                goToScreen('form-screen');
                setTimeout(() => {
                  const msg = document.getElementById('message');
                  msg.textContent = result.message || 'Token already used, pick another one!';
                  setTimeout(() => { msg.textContent = ''; }, 10000);
                }, 100);
              } else if (result.status === 'registered') {
                // ALL GOOD: Show final result.
                document.getElementById('result-username').textContent = latestName;
                document.getElementById('result-rfid').textContent = latestRFID;
                waitingScreenElement.classList.add('state-scanned');
                waitingScreenElement.classList.remove('state-scanning');
              }
            });
          } else if (data.status === 'pending' || data.status === 'scanning') {
            // STILL WAITING: Poll again after a short delay.
            setTimeout(pollForRFID, 500);
          } else {
            // DEFINITIVE FAILURE: Stop polling and show error.
            throw new Error(data.message || 'Scan failed or timed out.');
          }
        })
        .catch(error => {
          // CATCH-ALL: For network errors or thrown errors from above.
          console.error('Scan polling failed:', error);
          if (scanTitle) scanTitle.textContent = "Scan Failed. Please Try Again.";
        });
    };

    // Kick off the first poll.
    pollForRFID();
  }
}

// Helper: append a char if within limit
function tryAppendChar(nameInput, ch) {
  if (nameInput.value.length >= MAX_NAME_LEN) {
    setError('Keep it under 32 characters.');
    return;
  }
  nameInput.value += ch;
  clearError();
}

async function isNameAvailable(candidate) {
  try {
    const res = await fetch('/check_name', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: candidate })
    });
    const data = await res.json();
    return !data.exists; // true if available
  } catch {
    // On network hiccup, dont block selection
    return true;
  }
}


function submitForm() {
  const nameInput = document.getElementById('name');
  const name = nameInput.value.trim();
  const msg = document.getElementById('message');

  if (!name) {
    msg.textContent = 'Please enter a name.';
    nameInput.focus();
    return;
  }
  if (name.length > MAX_NAME_LEN) {
    msg.textContent = 'Keep it under 32 characters.';
    nameInput.focus();
    return;
  }

  fetch('/check_name', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name })
  })
  .then(res => res.json())
  .then(data => {
    if (data.exists) {
      msg.textContent = 'Pilot name taken. Choose another one!';
      setTimeout(() => { msg.textContent = ''; }, 10000);
    } else {
      msg.textContent = '';
      goToScreen('waiting-screen');
    }
  });
}

// --- INITIALIZATION ON PAGE LOAD ---
window.addEventListener("DOMContentLoaded", () => {
  goToScreen('welcome-screen');

  // Load and apply custom font ONLY to .key-char (alphabet keys)
  (function loadKeyboardFont() {
    const fontHref = '/static/fonts/flycampfont.ttf?v=1';

    const preload = document.createElement('link');
    preload.rel = 'preload';
    preload.as = 'font';
    preload.type = 'font/ttf';
    preload.href = fontHref;
    preload.crossOrigin = 'anonymous';
    document.head.appendChild(preload);

    const style = document.createElement('style');
    style.setAttribute('data-flycamp-kbd-font', 'true');
    style.textContent = `
@font-face {
  font-family: 'FlyCampKbd';
  src: url('/static/fonts/flycampfont.ttf?v=1') format('truetype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
/* Only the alphabet keys */
.key.key-char {
  font-family: 'FlyCampKbd' !important;
  font-weight: 400 !important;
  font-size: 0 !important; /* size controlled by inner span */
  line-height: 1 !important;
  letter-spacing: 0.02em;
}
`;
    document.head.appendChild(style);
  })();

  fetch('/queue-count')
    .then(res => res.json())
    .then(data => {
      const queueInfo = document.querySelector('.top-right-info');
      if (queueInfo) queueInfo.textContent = `Waiting in queue: ${data.count || 0}`;
    });

  // --- KEYBOARD SETUP ---
  const keyboardContainer = document.getElementById("keyboard");
  const nameInput = document.getElementById("name");

  // Guard hard limit for physical keyboard/paste too
  nameInput.setAttribute('maxlength', String(MAX_NAME_LEN));
  nameInput.addEventListener('input', () => {
    if (nameInput.value.length > MAX_NAME_LEN) {
      nameInput.value = nameInput.value.slice(0, MAX_NAME_LEN);
      setError('Keep it under 32 characters.');
    } else {
      clearError();
    }
  });

  let keyboardInitialized = false;

  const keyLayout = [
    ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
    ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
    ["Z", "X", "C", "V", "B", "N", "M"]
  ];

  function createKeyboard() {
    keyboardContainer.innerHTML = '';

    // Character keys
    keyLayout.forEach(row => {
      const rowDiv = document.createElement("div");
      rowDiv.className = "keyboard-row";
      row.forEach(char => {
        const keyBtn = document.createElement("button");
        keyBtn.className = "key key-char";

        const label = document.createElement("span");
        label.className = "key-char-label";
        label.textContent = char;

        keyBtn.appendChild(label);
        keyBtn.onclick = () => tryAppendChar(nameInput, char);

        rowDiv.appendChild(keyBtn);
      });
      keyboardContainer.appendChild(rowDiv);
    });

    // Special keys row (+ Random button)
    const specialKeysRow = document.createElement("div");
    specialKeysRow.className = "keyboard-row";
    specialKeysRow.style.display = "flex";
    specialKeysRow.style.gap = "5px";

    // Backspace
    const backspaceBtn = document.createElement("button");
    backspaceBtn.className = "key";
    backspaceBtn.classList.add("backspace-key");
    backspaceBtn.innerHTML = '&#x232B;';
    backspaceBtn.onclick = () => {
      nameInput.value = nameInput.value.slice(0, -1);
      clearError();
    };
    specialKeysRow.appendChild(backspaceBtn);

    // Random Name 🎲
    const randomBtn = document.createElement("button");
    randomBtn.className = "key";
    randomBtn.textContent = ":)";
    randomBtn.style.fontFamily = '"Segoe UI Emoji","Noto Color Emoji","Apple Color Emoji","JetBrains Mono",monospace';
    randomBtn.title = "Random pilot name";
    randomBtn.onclick = async () => {
  randomPressCount++;
  const pool = randomPressCount >= 10 ? LAME_NAMES : FUN_NAMES;

  const MAX_TRIES = 12; // try a few different names if taken
  for (let i = 0; i < MAX_TRIES; i++) {
    const pick = pool[Math.floor(Math.random() * pool.length)];
    const candidate = pick.slice(0, MAX_NAME_LEN);

    if (await isNameAvailable(candidate)) {
      nameInput.value = candidate;
      clearError();
      return;
    }
  }
  setError("All my ideas are taken. Try again!");
};

    specialKeysRow.appendChild(randomBtn);

    // Space
    const spaceBtn = document.createElement("button");
    spaceBtn.className = "key";
    spaceBtn.classList.add("space-key");
    spaceBtn.innerHTML = "_";
    spaceBtn.onclick = () => tryAppendChar(nameInput, " ");
    specialKeysRow.appendChild(spaceBtn);

    // Submit
    const submitBtn = document.createElement("button");
    submitBtn.className = "key";
    submitBtn.classList.add("submit-key");
    submitBtn.innerHTML = '->';
    submitBtn.onclick = submitForm;
    specialKeysRow.appendChild(submitBtn);

    keyboardContainer.appendChild(specialKeysRow);
  }

  // Show keyboard on focus
  nameInput.addEventListener("focus", () => {
    if (!keyboardInitialized) {
      createKeyboard();
      keyboardInitialized = true;
    }
    keyboardContainer.classList.add('keyboard-visible');
  });

  // Hide if focus leaves input + keyboard
  nameInput.addEventListener("blur", (e) => {
    if (!keyboardContainer.contains(e.relatedTarget)) {
      keyboardContainer.classList.remove('keyboard-visible');
    }
  });
});
