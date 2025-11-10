#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patched Flask console app (app.py)

- Adds verbose logging configuration
- Adds a RealSense D455 depth camera check (non-fatal if pyrealsense2 missing)
  using REALSENSE_SERIAL (env override supported)
- Ensures play_sound is robust and logs its activity
- Keeps the existing routes & start-game flow, with a verbose start_game_process
  that writes a logfile for the spawned game script
"""

from flask import Flask, render_template, jsonify, request
import sqlite3
import subprocess
import os
import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple, Optional, Dict, Any
import shutil
import logging

app = Flask(__name__, static_folder='static', template_folder='templates')

# --------------------------------------------------------------------------------------
# Logging configuration (verbose)
# --------------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger(__name__)
app.logger.setLevel(logging.DEBUG)
logging.getLogger("werkzeug").setLevel(logging.INFO)  # reduce request noise

# --------------------------------------------------------------------------------------
# Paths & constants
# --------------------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'flycamp_framework.db')
TOKEN_FILE = os.path.join(BASE_DIR, 'rfid_token.txt')
GAME_META_FILE = os.path.join(BASE_DIR, 'game_meta.json')
GAME_DONE_FLAG = os.path.join(BASE_DIR, 'game_done.flag')
SOUND_DIR = os.path.join(BASE_DIR, 'static', 'assets', 'sounds')

PREPARE_NODES_PATH = os.path.join(BASE_DIR, 'prepare_nodes.py')
PREPARE_CAR_PATH   = os.path.join(BASE_DIR, 'prepare_car.py')
# Drone connection check candidates (use *only* drone_ready.py)
POSSIBLE_DRONE_CHECK_SCRIPTS = [
    "drone_ready.py"
]

# Game script paths
HOVER_AND_SEEK = os.path.join(BASE_DIR, 'gamescripts', 'hoverandseek.py')
HUES_THE_BOSS  = os.path.join(BASE_DIR, 'gamescripts', 'huestheboss.py')
COLOR_CHAOS    = os.path.join(BASE_DIR, 'gamescripts', 'colourchaos.py')
# RealSense serial expected (can override via env)
REALSENSE_SERIAL = os.environ.get('REALSENSE_SERIAL', '049522251116')
# Joystick USB identifiers (override via env). If PID is 'any' or empty, accept any PID matching VID.
JOYSTICK_USB_VID = os.environ.get('JOYSTICK_USB_VID', '303a')
JOYSTICK_USB_PID = os.environ.get('JOYSTICK_USB_PID', 'any')
JOYSTICK_ALLOW_PRESENT_OK = os.environ.get('JOYSTICK_ALLOW_PRESENT_OK', '1')

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.set_trace_callback(lambda s: logger.debug("SQL: %s", s))
    except Exception:
        pass
    return conn

def play_sound(filename: str):
    """Play an MP3 sound file asynchronously using mpg123 (if present).
    Verbose: print file checks and warn if extension is unexpected.
    """
    full_path = os.path.join(SOUND_DIR, filename)
    logger.debug("[play_sound] Requested: %s -> %s", filename, full_path)
    if not os.path.exists(full_path):
        logger.warning("[play_sound] Missing file: %s", full_path)
        return
    ext = os.path.splitext(full_path)[1].lower()
    if ext != '.mp3':
        logger.warning("[play_sound] Playing file with extension %s (expected .mp3).", ext)
    mpg_path = shutil.which("mpg123")
    logger.debug("[play_sound] mpg123 detection: %s", mpg_path)

    def _runner():
        try:
            if mpg_path:
                subprocess.run([mpg_path, "-q", full_path], check=False)
            else:
                # Fall back to system default player (attempt)
                subprocess.run(["python3", "-m", "webbrowser"], check=False)  # harmless fallback placeholder
            logger.debug("[play_sound] Finished playing: %s", full_path)
        except Exception as e:
            logger.exception("[play_sound] Error running player for %s: %s", full_path, e)
    threading.Thread(target=_runner, daemon=True).start()

def _run_python_script(script_path: str, args: Optional[List[str]] = None, timeout: int = 40) -> Tuple[bool, str]:
    """Run a python script and return (ok, combined_output)."""
    args = args or []
    logger.debug("_run_python_script: %s args=%s timeout=%s", script_path, args, timeout)
    if not os.path.exists(script_path):
        logger.error("_run_python_script: Script not found: %s", script_path)
        return False, f"Script not found: {script_path}"
    try:
        proc = subprocess.run(
            ['python3', script_path] + args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        ok = (proc.returncode == 0)
        out = (proc.stdout or '') + (('\n' + proc.stderr) if proc.stderr else '')
        logger.debug("_run_python_script: rc=%s stdout=%s stderr=%s", proc.returncode, proc.stdout, proc.stderr)
        return ok, out.strip()
    except subprocess.TimeoutExpired:
        logger.error("_run_python_script: Timeout running %s", script_path)
        return False, f"Timeout after {timeout}s"
    except Exception as e:
        logger.exception("_run_python_script: Exception running %s: %s", script_path, e)
        return False, f"Exception: {e}"

def _find_existing_script(candidates: List[str]) -> Optional[str]:
    for p in candidates:
        if os.path.exists(p):
            logger.debug("_find_existing_script: found %s", p)
            return p
    logger.debug("_find_existing_script: none found in candidates=%s", candidates)
    return None

def _read_latest_selection_from_meta() -> Optional[int]:
    """Best effort: read last written game_number from GAME_META_FILE."""
    try:
        if os.path.exists(GAME_META_FILE):
            with open(GAME_META_FILE, 'r') as f:
                data = json.load(f)
                gn = int(data.get('game_number', 0))
                logger.debug("_read_latest_selection_from_meta read: %s", data)
                return gn if gn in (1, 2, 3) else None
    except Exception as e:
        logger.exception("[meta] Could not read %s: %s", GAME_META_FILE, e)
    return None

def check_depth_camera(expected_serial: Optional[str] = None) -> Tuple[bool, str]:
    """
    Check for connected Intel RealSense devices and optionally validate serial.
    Returns (ok, message). Does not raise if pyrealsense2 is missing.
    """
    try:
        import pyrealsense2 as rs  # local import to avoid hard dependency at app import
    except Exception as e:
        logger.warning("check_depth_camera: pyrealsense2 not available: %s", e)
        return (False, f"pyrealsense2 not available: {e}")

    try:
        ctx = rs.context()
        # ctx.query_devices() is available in newer wrappers; older wrappers expose ctx.devices
        devices = []
        try:
            devices = list(ctx.query_devices())
        except Exception:
            try:
                devices = list(ctx.devices)
            except Exception:
                devices = []
    except Exception as e:
        logger.exception("check_depth_camera: Failed to enumerate RealSense devices: %s", e)
        return (False, f"Failed to enumerate RealSense devices: {e}")

    if not devices:
        logger.debug("check_depth_camera: No RealSense devices detected")
        return (False, "No RealSense devices detected")

    found = []
    for dev in devices:
        try:
            name = dev.get_info(rs.camera_info.name) or "<unknown>"
        except Exception:
            name = "<unknown>"
        try:
            serial = dev.get_info(rs.camera_info.serial_number) or "<no-serial>"
        except Exception:
            serial = "<no-serial>"
        found.append(f"{name}:{serial}")
        if expected_serial and serial == expected_serial:
            logger.debug("check_depth_camera: Found expected device %s (serial=%s)", name, serial)
            return (True, f"Found {name} (serial={serial})")

    if expected_serial:
        logger.warning("check_depth_camera: Expected serial %s not found. Detected: %s", expected_serial, ', '.join(found))
        return (False, f"Device with serial {expected_serial} not found. Detected: {', '.join(found)}")
    return (True, f"Detected RealSense device(s): {', '.join(found)}")

def _read_sysfs_vid_pid_for_tty(tty_name: str) -> Tuple[Optional[str], Optional[str], str]:
    base = f"/sys/class/tty/{tty_name}/device"
    cur = base
    tried = []
    # Walk up to find USB interface parent containing idVendor/idProduct
    for _ in range(8):
        vid_path = os.path.join(cur, 'idVendor')
        pid_path = os.path.join(cur, 'idProduct')
        tried.append(cur)
        if os.path.exists(vid_path) and os.path.exists(pid_path):
            try:
                with open(vid_path) as vf:
                    vid = vf.read().strip().lower().replace('0x','')
                with open(pid_path) as pf:
                    pid = pf.read().strip().lower().replace('0x','')
                return vid, pid, f"found at {vid_path} & {pid_path}"
            except Exception as e:
                return None, None, f"read error: {e}"
        parent = os.path.abspath(os.path.join(cur, '..'))
        if parent == cur:
            break
        cur = parent
    return None, None, f"idVendor/idProduct not found; searched: {', '.join(tried)}"


def check_joystick_acm1(expected_vid: str = '303a', expected_pid: str = '1001') -> Tuple[bool, str]:
    """Check only /dev/ttyACM1 and validate USB VID/PID via sysfs.
    If expected_pid is 'any' or empty, accept any PID for matching VID.
    If JOYSTICK_ALLOW_PRESENT_OK=1 and VID/PID cannot be read but device exists, return present OK.
    """
    dev = '/dev/ttyACM0'
    if not os.path.exists(dev):
        return False, f"{dev} not present"
    tty_name = os.path.basename(dev)
    vid, pid, detail = _read_sysfs_vid_pid_for_tty(tty_name)
    if vid is None or pid is None:
        if (os.environ.get('JOYSTICK_ALLOW_PRESENT_OK', '1') == '1'):
            return True, f"{dev} present (VID/PID unknown: {detail})"
        return False, f"{dev}: unable to read VID/PID ({detail})"
    exp_vid = (expected_vid or '').lower()
    exp_pid = (expected_pid or '').lower()
    if vid == exp_vid and (exp_pid in ('', 'any') or pid == exp_pid):
        return True, f"{dev} ready (VID={vid}, PID={pid})"
    return False, f"{dev}: VID/PID mismatch (got {vid}:{pid}, need {exp_vid}:{exp_pid or 'any'})"


def run_initialisation_steps(game_number: Optional[int], controller: Optional[str] = None) -> Dict[str, Any]:
    """
    4(+1) line init:
      - Joystick/Gesture: simulated OK (placeholder)
      - Nodes: prepare_nodes.py for ALL games
      - Car: prepare_car.py only for Game 2
      - Depth Camera: check for Intel RealSense D455 (serial from REALSENSE_SERIAL)
      - Drone: connection_check.py (drone_ready.py here)
    """
    steps: List[Dict[str, Any]] = []

    logger.debug("run_initialisation_steps called with game_number=%s controller=%s", game_number, controller)

    # 1) Joystick/Gesture
    if (controller or '').lower() == 'joystick':
        ok_js, msg_js = check_joystick_acm1(JOYSTICK_USB_VID, JOYSTICK_USB_PID)
        steps.append({'name': 'Joystick/Gesture', 'ok': ok_js, 'message': msg_js})
    else:
        steps.append({'name': 'Joystick/Gesture', 'ok': True, 'message': 'Gesture selected'})

    # 2) Nodes prepare (ALL games)
    ok_nodes, msg_nodes = _run_python_script(PREPARE_NODES_PATH)
    steps.append({'name': 'Nodes', 'ok': ok_nodes, 'message': msg_nodes or ''})

    # 3) Car prepare (Game 2 only)
    if game_number == 4:
        ok_car, msg_car = _run_python_script(PREPARE_CAR_PATH)
        steps.append({'name': 'Car', 'ok': ok_car, 'message': msg_car or ''})
    else:
        steps.append({'name': 'Car', 'ok': True, 'message': 'Skipped (not required for this game)'})

    # 4) Depth camera check 
    try:
        ok_cam, msg_cam = check_depth_camera(REALSENSE_SERIAL)
        steps.append({'name': 'Depth Camera', 'ok': bool(ok_cam), 'message': msg_cam or ''})
    except Exception as e:
        logger.exception("Exception while checking Depth Camera: %s", e)
        steps.append({'name': 'Depth Camera', 'ok': False, 'message': f'Exception while checking camera: {e}'})

    # 4) Drone check (MUST run drone_ready.py; no simulated OK)
    check_script = _find_existing_script(POSSIBLE_DRONE_CHECK_SCRIPTS)
    if check_script is None:
        steps.append({'name': 'Drone', 'ok': False, 'message': 'drone_ready.py not found'})
    else:
        args = [
            '--uri', os.environ.get('CF_URI', 'radio://0/80/2M/E7E7E7E7E7'),
            '--name', 'drone',
            '--pos-timeout', '12',
            '--require-pos'
        ]
        ok_drone, msg_drone = _run_python_script(check_script, args=args)
        steps.append({
            'name': 'Drone',
            'ok': bool(ok_drone),
            'message': f"{os.path.basename(check_script)} rc={'0' if ok_drone else '1'}\n{msg_drone or ''}"
        })

    success = all(s.get('ok') for s in steps)
    logger.debug("run_initialisation_steps result success=%s steps=%s", success, steps)
    return {'success': success, 'game_number': game_number, 'steps': steps}

def start_game_process(game_number: int, level_number: int, controller: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Verbose variant: logs each step, validates script path, writes a logfile for the spawned process.
    """
    try:
        logger.info("[start_game_process] Requested G%s L%s", game_number, level_number)

        # Clear stale done flag
        try:
            if os.path.exists(GAME_DONE_FLAG):
                logger.debug("[start_game_process] Removing stale flag: %s", GAME_DONE_FLAG)
                os.remove(GAME_DONE_FLAG)
        except Exception as e:
            logger.exception("[start_game_process] Could not remove old flag: %s", e)

        # Persist selection for scripts to read
        try:
            logger.debug("[start_game_process] Writing meta to %s", GAME_META_FILE)
            with open(GAME_META_FILE, "w") as m:
                meta = {"game_number": game_number, "level_number": level_number}
                if controller in ("joystick", "gesture"):
                    meta["controller"] = controller
                json.dump(meta, m)
        except Exception as e:
            logger.exception("[start_game_process] Could not write game_meta.json: %s", e)

        # Map to script
        script = None
        if game_number == 1 and level_number in (1, 2):
            script = HOVER_AND_SEEK
        elif game_number == 2 and level_number == 1:
            script = HUES_THE_BOSS
        elif game_number == 3 and level_number in (1, 2):
            script = COLOR_CHAOS
        else:
            # Back-compat: legacy mapping where (2,2) launched Color Chaos
            if game_number == 2 and level_number == 2:
                script = COLOR_CHAOS
            else:
                err = f"Invalid game/level selection: G{game_number} L{level_number}"
                logger.error("[start_game_process] %s", err)
                return (False, err)

        logger.debug("[start_game_process] Selected script: %s", script)
        if not os.path.exists(script):
            err = f"Script not found: {script}"
            logger.error("[start_game_process] %s", err)
            return (False, err)

        # Sounds (verbose)
        logger.debug("[start_game_process] Playing selection and initializing sounds")
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/button selection.mp3")
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/initialising drone and nodes before game.mp3")

        # Spawn the script and direct stdout/stderr to a logfile for debugging
        try:
            logfile = f"/tmp/game_launch_G{game_number}_L{level_number}_{int(datetime.now().timestamp())}.log"
            logger.debug("[start_game_process] Launching %s with logfile %s", script, logfile)
            lf = open(logfile, "w")
            proc = subprocess.Popen(
                ['python3', script],
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            logger.info("[start_game_process] Spawned PID %s", proc.pid)
            # detach file handle in background thread to close later when process ends (best-effort)
            def _close_log_on_exit(p, fpath, fh):
                try:
                    p.wait(timeout=1)
                except Exception:
                    # don't block waiting for long-running game; leave logfile open for manual inspection
                    pass
                try:
                    fh.flush()
                    fh.close()
                    logger.debug("[start_game_process] Logfile descriptor closed (path: %s)", fpath)
                except Exception:
                    pass
            threading.Thread(target=_close_log_on_exit, args=(proc, logfile, lf), daemon=True).start()
        except Exception as e:
            logger.exception("[start_game_process] Failed to spawn script: %s", e)
            return (False, f"Failed to spawn script: {e}")

        play_sound("game_start.mp3")
        return (True, None)
    except Exception as e:
        logger.exception("[start_game_process] Unexpected exception: %s", e)
        return (False, str(e))

def get_token_id_from_script():
    try:
        result = subprocess.run(['python3', 'get_id.py'], capture_output=True, text=True, timeout=10)
        output = result.stdout.strip()
        if "Token ID:" in output:
            token_id = int(output.split("Token ID:")[1].strip())
            return token_id
        logger.warning("get_id.py did not return a Token ID. Full output: %s", output)
        return None
    except Exception as e:
        logger.exception("Error reading token ID from get_id.py: %s", e)
        return None

# --------------------------------------------------------------------------------------
# Routes: UI
# --------------------------------------------------------------------------------------
@app.route('/')
def index():
    # Render your single-page UI (cards etc.) at /templates/console.html
    return render_template('console.html')

# --------------------------------------------------------------------------------------
# Routes: RFID
# --------------------------------------------------------------------------------------
@app.route('/scan_rfid')
def scan_rfid():
    token_id = get_token_id_from_script()
    logger.debug("Scanned token_id: %s", token_id)

    if not token_id:
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/rfid_error.mp3")
        return jsonify({'success': False, 'error': 'No token ID found or script failed'})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT player_name FROM PlayerRegistrations WHERE token_id = ?", (token_id,))
        row = cursor.fetchone()
    finally:
        conn.close()

    if row:
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/name and rfid pops up.mp3")
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/rfid_success.mp3")
        return jsonify({'success': True, 'name': row['player_name'], 'token_id': token_id})
    else:
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/rfid_error.mp3")
        return jsonify({'success': False, 'error': 'Token not registered to any player'})

@app.route('/write_rfid_token', methods=['POST'])
def write_rfid_token():
    data = request.get_json(silent=True) or {}
    token_id = data.get('token_id')
    if token_id is not None:
        try:
            with open(TOKEN_FILE, "w") as f:
                f.write(str(token_id))
            logger.debug("Wrote token to %s: %s", TOKEN_FILE, token_id)
            return jsonify({'success': True})
        except Exception as e:
            logger.exception("Failed to write token file: %s", e)
            return jsonify({'success': False, 'error': f'Failed to write token file: {e}'})
    return jsonify({'success': False, 'error': 'No token_id provided'})

# --------------------------------------------------------------------------------------
# Routes: Init + Start
# --------------------------------------------------------------------------------------
@app.route('/api/connection_check', methods=['POST'])
def api_connection_check():
    payload = request.get_json(silent=True) or {}
    game_number = payload.get('game_number')
    controller  = (payload.get('controller') or '').lower() or None

    try:
        game_number = int(game_number) if game_number is not None else None
        if game_number not in (1, 2, 3):
            game_number = None
    except Exception:
        game_number = None

    if game_number is None:
        game_number = _read_latest_selection_from_meta()

    result = run_initialisation_steps(game_number, controller)

    # Optional: voice line on success
    #if result.get('success'):
        #play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/initialising drone and nodes before game.mp3")

    return jsonify(result)

@app.route('/api/start_game', methods=['POST'])
def api_start_game():
    data = request.get_json(force=True)
    logger.debug("[api_start_game] Payload: %s", data)
    try:
        game_number = int(data.get('game_number', 0))
        level_number = int(data.get('level_number', 0))
    except Exception as e:
        logger.exception("[api_start_game] Bad numeric conversion: %s", e)
        return jsonify({'success': False, 'error': 'Invalid game/level values', 'debug': str(e)})

    controller = data.get('controller')
    if controller is not None:
        controller = str(controller).lower()
        if controller not in ("joystick", "gesture"):
            return jsonify({'success': False, 'error': 'Invalid controller. Use "joystick" or "gesture".'})

    success, err = start_game_process(game_number, level_number, controller)
    if success:
        logger.info("[api_start_game] Start OK")
        return jsonify({'success': True})
    logger.error("[api_start_game] Start failed: %s", err)
    return jsonify({'success': False, 'error': err or 'Failed to start game', 'debug': 'See /tmp logfile and server stdout for details'})

# --------------------------------------------------------------------------------------
# Back-compat endpoints (still work; map to same scripts)
# --------------------------------------------------------------------------------------
@app.route('/start_hue_game')
def start_hue_game():
    try:
        if os.path.exists(GAME_DONE_FLAG):
            os.remove(GAME_DONE_FLAG)
        with open(GAME_META_FILE, "w") as m:
            json.dump({"game_number": 2, "level_number": 1}, m)

        _run_python_script(PREPARE_NODES_PATH)
        _run_python_script(PREPARE_CAR_PATH)

        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/button selection.mp3")
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/initialising drone and nodes before game.mp3")

        subprocess.Popen(['python3', HUES_THE_BOSS])
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/game_start.mp3")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("Error in start_hue_game: %s", e)
        return jsonify({'success': False, 'error': str(e)})

@app.route('/start_hover_game')
def start_hover_game():
    try:
        if os.path.exists(GAME_DONE_FLAG):
            os.remove(GAME_DONE_FLAG)
        with open(GAME_META_FILE, "w") as m:
            json.dump({"game_number": 1, "level_number": 1}, m)

        _run_python_script(PREPARE_NODES_PATH)

        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/button selection.mp3")
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/initialising drone and nodes before game.mp3")

        subprocess.Popen(['python3', HOVER_AND_SEEK])
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/game_start.mp3")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("Error in start_hover_game: %s", e)
        return jsonify({'success': False, 'error': str(e)})

# --------------------------------------------------------------------------------------
# Scores / Leaderboard
# --------------------------------------------------------------------------------------
@app.route('/submit_score', methods=['POST'])
def submit_score():
    """
    Expects: token_id (int), game_number (int), level_number (int), score (int)
    Inserts a row in GamePlays and updates PlayerBests (manual upsert).
    """
    data = request.get_json()
    token_id = data.get('token_id')
    game_number = data.get('game_number')
    level_number = data.get('level_number')
    score = data.get('score')

    if token_id is None or game_number is None or level_number is None or score is None:
        return jsonify({'success': False, 'error': 'Missing token_id, game_number, level_number, or score'})

    try:
        token_id = int(token_id)
        game_number = int(game_number)
        level_number = int(level_number)
        score = int(score)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid numeric fields'})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        now_ts = int(datetime.now(tz=ZoneInfo("Asia/Kolkata")).timestamp())

        # 1) Insert raw play
        cursor.execute("""
            INSERT INTO GamePlays (token_id, game_number, level_number, score, begin_timestamp, end_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token_id, game_number, level_number, score, now_ts, now_ts))

        # 2) Manual upsert for PlayerBests
        cursor.execute("""
            SELECT player_best_id, highest_score
            FROM PlayerBests
            WHERE token_id = ? AND game_number = ? AND level_number = ?
            ORDER BY player_best_id LIMIT 1
        """, (token_id, game_number, level_number))
        row = cursor.fetchone()

        if row is None:
            cursor.execute("""
                INSERT INTO PlayerBests (token_id, game_number, level_number, highest_score, timestamp_achieved)
                VALUES (?, ?, ?, ?, ?)
            """, (token_id, game_number, level_number, score, now_ts))
        else:
            player_best_id = row['player_best_id']
            prev = row['highest_score'] or 0
            if score > prev:
                cursor.execute("""
                    UPDATE PlayerBests
                    SET highest_score = ?, timestamp_achieved = ?
                    WHERE player_best_id = ?
                """, (score, now_ts, player_best_id))

        conn.commit()
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/final score display.mp3")
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/score_submit.mp3")
        return jsonify({'success': True, 'message': 'Score submitted and stats updated.'})

    except sqlite3.Error as e:
        conn.rollback()
        logger.exception("Database error in submit_score: %s", e)
        return jsonify({'success': False, 'error': f'Database error: {e}'})
    finally:
        conn.close()

@app.route('/get_leaderboard')
def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                pr.player_name,
                COALESCE(SUM(pb.highest_score), 0) AS total_score
            FROM PlayerBests AS pb
            JOIN PlayerRegistrations AS pr ON pb.token_id = pr.token_id
            GROUP BY pr.player_name
            ORDER BY total_score DESC
        """)
        rows = cursor.fetchall()
        leaderboard_data = [{'name': row['player_name'], 'score': row['total_score']} for row in rows]
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/final score display.mp3")
        play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/leaderboard.mp3")
        return jsonify({'success': True, 'leaderboard': leaderboard_data})
    except sqlite3.Error as e:
        logger.exception("Error fetching leaderboard data: %s", e)
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# --------------------------------------------------------------------------------------
# Game done flag
# --------------------------------------------------------------------------------------
@app.route('/game_done')
def game_done():
    if os.path.exists(GAME_DONE_FLAG):
        try:
            os.remove(GAME_DONE_FLAG)
            play_sound("/home/devesh/Console/fly_camp_console/static/assets/sounds/drone back to home.mp3")
            return jsonify({'done': True})
        except Exception as e:
            logger.exception("Error removing game_done flag: %s", e)
            return jsonify({'done': False, 'error': str(e)})
    else:
        return jsonify({'done': False})

# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
if __name__ == '__main__':
    logger.info("Starting Flask app (verbose mode enabled)")
    # Note: keep port/host consistent with your kiosk/Electron wrapper
    app.run(host='0.0.0.0', port=5000)
