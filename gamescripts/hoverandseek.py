#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hover and Seek — full UI + MQTT game script
- MQTT-driven node triggers & hit handling
- Tkinter UI with timer ring and simple, light visuals (FlyCamp blue/yellow)
- DIRECT DB WRITE on completion:
    - INSERT into GamePlays
    - Manual UPSERT into PlayerBests (no UNIQUE constraint required)
- Signals completion with /home/devesh/game_done.flag
  (now written immediately after DB write so the web UI can show the leaderboard
   while this game still displays its final score screen)
- Reads token_id from /home/devesh/rfid_token.txt
- Reads game/level from /home/devesh/game_meta.json (preferred) or /home/devesh/current_choice.json (fallback)

This variant launches an external "gesturecontrol" helper program (as a separate process)
when the game starts and treats any line on its stdout that contains "hit" (case-insensitive)
as a hit event. The gesture control process is terminated when the game ends.
"""

import json
import os
import random
import sqlite3
import time
import tkinter as tk
from datetime import datetime
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt

# New imports for launching gesturecontrol as an external process
import subprocess
import threading

import os
import logging
import threading
import subprocess
import shutil


# =================================================================
# === SOUNDS ===
# =================================================================
# Set SOUND_DIR appropriately, e.g.:
SOUND_DIR = "/home/devesh/Console/fly_camp_console/static/assets/sounds"

# If not already set, create logger for standalone use
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)

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

# =================================================================
# === PATHS & CONSTANTS ===
# =================================================================
BROKER = "localhost"

# Node IDs for this game
NODES = ["node1", "node2", "node3", "node4", "node5"]
COLOR_TARGET_NODES = ["node1", "node2", "node3", "node4", "node5"]  # hits come from these

HIT_TOPICS = [f"game/hit/{nid}" for nid in COLOR_TARGET_NODES]
TRIGGER_TOPICS = {nid: f"game/trigger/{nid}" for nid in NODES}
RESET_TOPIC = "game/reset"
PREPARE_TOPIC = "game/prepare"

# Controller executables
JOYSTICK_CONTROL_PATH = os.environ.get("JOYSTICK_CONTROL_PATH", "/home/devesh/Joystick_Control/Joystick_Control.py")

# Gameplay
GAME_DURATION = 15  # seconds
SCORE_DISPLAY_DURATION = 10  # seconds after game ends (UI) — extended to give time for leaderboard

# Files & DB
TOKEN_FILE  = "/home/devesh/Console/fly_camp_console/rfid_token.txt"       # consoleapp writes token_id here (absolute path)
META_PATH   = "/home/devesh/game_meta.json"        # consoleapp writes {"game_number": X, "level_number": Y}
CHOICE_FILE = "/home/devesh/current_choice.json"   # optional legacy fallback
FLAG_FILE   = "/home/devesh/game_done.flag"

DB_PATH = "/home/devesh/Console/fly_camp_console/flycamp_framework.db"

# Game identity defaults
DEFAULT_GAME_NUMBER = 1
DEFAULT_LEVEL_NUMBER = 1

# Path to gesturecontrol program (can be an executable or a python script).
# Configure via environment variable GESTURE_CONTROL_PATH, otherwise default to ./gesturecontrol
GESTURE_CONTROL_PATH = "/home/devesh/Gesture-Control/GuestureControl.py"

# =================================================================
# === THEME (simple FlyCamp blue/yellow) ===
# =================================================================
FONT_FAMILY = "Segoe UI"
BACKGROUND_COLOR = "#10375C"   # FlyCamp deep blue
ACCENT_YELLOW   = "#F3C522"    # FlyCamp yellow
ACCENT_BLUE     = "#1B4F72"    # darker blue for boxes/outline
TEXT_LIGHT      = "#FFFFFF"

# =================================================================
# === STATE ===
# =================================================================
hit_count = 0
start_time = None
begin_ts_unix = None  # when timer actually starts (first valid hit)
end_ts_unix = None
game_started = False
timer_running = False
last_node = None
available_nodes = COLOR_TARGET_NODES.copy()

# Metadata read at start
token_id = None                 # INTEGER token_id for the player (from TOKEN_FILE)
game_number = DEFAULT_GAME_NUMBER
level_number = DEFAULT_LEVEL_NUMBER
controller_type = None          # 'joystick' or 'gesture'

# Gesturecontrol integration state
gesture_proc = None            # subprocess.Popen instance for gesturecontrol
gesture_thread = None          # thread reading gestureproc stdout
gesture_stop_event = threading.Event()

# =================================================================
# === UI ===
# =================================================================
root = tk.Tk()
root.title("Hover and Seek")
root.attributes('-fullscreen', True)
root.configure(bg=BACKGROUND_COLOR)

canvas = tk.Canvas(root, bg=BACKGROUND_COLOR, highlightthickness=0)
canvas.pack(fill="both", expand=True)

# Dedicated MQTT client id (avoid collision)
client = mqtt.Client("hover_and_seek_ui_v1")


# =================================================================
# === UTILITIES — FILES, DB, TIME ===
# =================================================================
def read_token_id():
    """
    Read integer token_id for this session.
    Priority: TOKEN_FILE -> ENV (RFID_TOKEN or TOKEN_ID or TOKEN) -> None
    """
    # 1) file
    try:
        with open(TOKEN_FILE, "r") as f:
            s = f.read().strip()
            if s.isdigit():
                return int(s)
    except FileNotFoundError:
        pass

    # 2) env fallbacks
    envs = [os.getenv("RFID_TOKEN"), os.getenv("TOKEN_ID"), os.getenv("TOKEN")]
    for v in envs:
        if v and str(v).isdigit():
            return int(v)

    print("WARNING: No token_id found (rfid_token.txt missing or not numeric).")
    return None


def read_choice():
    """
    Read {game_number, level_number, controller}.
    Preferred: META_PATH written by consoleapp at launch.
    Fallback: CHOICE_FILE if present.
    """
    def parse(d):
        g = int(d.get("game_number", DEFAULT_GAME_NUMBER))
        l = int(d.get("level_number", DEFAULT_LEVEL_NUMBER))
        c = d.get("controller")
        if isinstance(c, str):
            c = c.lower()
        return g, l, c

    if os.path.exists(META_PATH):
        try:
            with open(META_PATH, "r") as m:
                data = json.load(m)
            return parse(data)
        except Exception as e:
            print(f"NOTE: Could not parse {META_PATH}: {e}")

    if os.path.exists(CHOICE_FILE):
        try:
            with open(CHOICE_FILE, "r") as f:
                data = json.load(f)
            return parse(data)
        except Exception as e:
            print(f"NOTE: Could not parse {CHOICE_FILE}: {e}")

    return DEFAULT_GAME_NUMBER, DEFAULT_LEVEL_NUMBER, None


def now_ist_unix():
    return int(datetime.now(tz=ZoneInfo("Asia/Kolkata")).timestamp())


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def record_result_to_db(token_id_val: int, game_no: int, level_no: int, score_val: int,
                        begin_ts: int, end_ts: int):
    """
    - INSERT into GamePlays
    - Manual UPSERT into PlayerBests (no UNIQUE needed):
        * If row exists for (token_id, game_number, level_number), update only if higher.
        * Else insert.
    """
    conn = db_conn()
    cur = conn.cursor()
    try:
        # 1) raw play
        cur.execute("""
            INSERT INTO GamePlays (token_id, game_number, level_number, score, begin_timestamp, end_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token_id_val, game_no, level_no, score_val, begin_ts, end_ts))

        # 2) manual upsert into PlayerBests
        cur.execute("""
            SELECT player_best_id, highest_score
            FROM PlayerBests
            WHERE token_id = ? AND game_number = ? AND level_number = ?
            ORDER BY player_best_id
            LIMIT 1
        """, (token_id_val, game_no, level_no))
        row = cur.fetchone()

        if row is None:
            cur.execute("""
                INSERT INTO PlayerBests (token_id, game_number, level_number, highest_score, timestamp_achieved)
                VALUES (?, ?, ?, ?, ?)
            """, (token_id_val, game_no, level_no, score_val, end_ts))
        else:
            player_best_id = row["player_best_id"]
            prev = row["highest_score"] or 0
            if score_val > prev:
                cur.execute("""
                    UPDATE PlayerBests
                    SET highest_score = ?, timestamp_achieved = ?
                    WHERE player_best_id = ?
                """, (score_val, end_ts, player_best_id))

        conn.commit()
        print("DB write success (GamePlays + PlayerBests).")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"DB error: {e}")
    finally:
        conn.close()


# =================================================================
# === CONTROLLER HELPERS ===
# =================================================================

def get_controller_type():
    return controller_type or 'joystick'

# =================================================================
# === DRAWING HELPERS (lightweight) ===
# =================================================================
def get_center():
    root.update_idletasks()
    w = root.winfo_screenwidth()
    h = root.winfo_screenheight()
    return w // 2, h // 2


def clear_screen():
    canvas.delete("all")


def draw_card(x1, y1, x2, y2):
    # simple rounded-rect look using two rectangles (fast)
    canvas.create_rectangle(x1, y1, x2, y2, fill=ACCENT_BLUE, outline=ACCENT_BLUE, width=1)
    canvas.create_rectangle(x1+2, y1+2, x2-2, y2-2, outline=ACCENT_YELLOW, width=2)


def draw_circle_progress(x, y, r, percent):
    # very lightweight progress ring
    canvas.create_oval(x - r, y - r, x + r, y + r, outline=ACCENT_YELLOW, width=6, tags="timer")
    angle = percent * 360
    if angle > 0:
        canvas.create_arc(x - r, y - r, x + r, y + r, start=90, extent=-angle,
                          style="arc", outline=TEXT_LIGHT, width=8, tags="timer")


def draw_text_center(x, y, text, size=48, color=ACCENT_YELLOW, weight="bold", tag=None):
    canvas.create_text(x, y, text=text, fill=color, font=(FONT_FAMILY, size, weight), tags=tag)


def animate_score_pop():
    # keep this subtle to reduce CPU; one quick size toggle
    canvas.itemconfig("score_text", font=(FONT_FAMILY, 88, "bold"), fill=ACCENT_YELLOW)
    root.after(120, lambda: canvas.itemconfig("score_text", font=(FONT_FAMILY, 76, "bold"), fill=TEXT_LIGHT))


# =================================================================
# === CONTROLLER PROCESS INTEGRATION ===
# =================================================================
def _on_gesture_hit():
    """
    Called on the Tk main thread when gesturecontrol indicates a hit.
    Mirrors the behaviour in on_message for MQTT hits.
    """
    global hit_count, start_time, timer_running, begin_ts_unix
    if not game_started:
        return

    if not timer_running:
        start_time = time.time()
        timer_running = True
        begin_ts_unix = now_ist_unix()
        update_main_screen()

    hit_count += 1
    canvas.itemconfig("score_text", text=str(hit_count))
    animate_score_pop()
    trigger_next_node()
    play_sound("target hit.wav")


def _gesture_reader_thread(proc, stop_event):
    """
    Background thread that reads stdout from the gesturecontrol process.
    Any line containing 'hit' (case-insensitive) is treated as a hit event.
    """
    try:
        # Iterate over stdout lines
        if proc.stdout is None:
            return
        for raw in proc.stdout:
            if stop_event.is_set():
                break
            line = raw.strip()
            if not line:
                continue
            # Treat 'hit' substring (case-insensitive) as a hit
            if "hit" in line.lower():
                try:
                    root.after(0, _on_gesture_hit)
                except Exception:
                    pass
            else:
                # Debug visibility; do not spam UI
                print(f"[gesturecontrol] {line}")
    except Exception as e:
        print(f"Gesture reader thread error: {e}")
    finally:
        # attempt to capture stderr for diagnostics
        try:
            if proc.stderr:
                err = proc.stderr.read()
                if err:
                    print(f"[gesturecontrol:stderr] {err.strip()}")
        except Exception:
            pass


def start_gesture_control():
    """
    Start the gesturecontrol helper program if present and not already running.
    Spawns a background thread that listens to stdout for gesture events.
    The path can be configured via GESTURE_CONTROL_PATH environment variable.
    """
    global gesture_proc, gesture_thread, gesture_stop_event

    if gesture_proc is not None:
        return

    path = GESTURE_CONTROL_PATH
    candidates = [path]
    if not path.endswith(".py"):
        candidates.append(f"{path}.py")
        candidates.append(os.path.join(os.path.dirname(__file__), f"{path}.py"))

    chosen = None
    for p in candidates:
        if os.path.exists(p) and os.access(p, os.R_OK):
            chosen = p
            break

    if chosen is None:
        # try running the given path as executable (maybe in PATH)
        chosen = path

    try:
        gesture_stop_event.clear()
        if chosen.endswith(".py") or not os.access(chosen, os.X_OK):
            cmd = ["python3", chosen]
        else:
            cmd = [chosen]

        print(f"Starting gesturecontrol: {' '.join(cmd)}")
        gesture_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        gesture_thread = threading.Thread(target=_gesture_reader_thread, args=(gesture_proc, gesture_stop_event), daemon=True)
        gesture_thread.start()
    except Exception as e:
        print(f"Failed to start gesturecontrol ({chosen}): {e}")
        gesture_proc = None
        gesture_thread = None
        gesture_stop_event.clear()


def stop_gesture_control():
    """
    Stop the gesturecontrol process and its reader thread cleanly.
    """
    global gesture_proc, gesture_thread, gesture_stop_event
    try:
        gesture_stop_event.set()
        if gesture_proc:
            try:
                gesture_proc.terminate()
            except Exception:
                pass
            try:
                gesture_proc.wait(timeout=1.0)
            except Exception:
                try:
                    gesture_proc.kill()
                except Exception:
                    pass
        if gesture_thread and gesture_thread.is_alive():
            gesture_thread.join(timeout=1.0)
    except Exception as e:
        print(f"Error stopping gesturecontrol: {e}")
    finally:
        gesture_proc = None
        gesture_thread = None
        gesture_stop_event.clear()

# --- Joystick control (simple spawn/stop) ---
joy_proc = None

def send_esp32_mode(mode: int, device: str = "/dev/ttyACM1"):
    try:
        with open(device, "wb", buffering=0) as f:
            f.write(bytes([mode & 0xFF]))
        print(f"ESP32S3 mode 0x{mode:02X} sent to {device}")
    except Exception as e:
        print(f"ESP32S3 mode send failed on {device}: {e}")


def start_joystick_control():
    global joy_proc
    if joy_proc is not None:
        return
    # ESP32S3 mode signaling disabled (no 0x01 sent)
    path = JOYSTICK_CONTROL_PATH
    try:
        if path.endswith('.py'):
            cmd = ['python3', path]
        else:
            cmd = [path]
        print(f"Starting joystick control: {' '.join(cmd)}")
        joy_proc = subprocess.Popen(cmd)
    except Exception as e:
        print(f"Failed to start joystick control ({path}): {e}")
        joy_proc = None


def stop_joystick_control():
    global joy_proc
    try:
        if joy_proc:
            joy_proc.terminate()
            try:
                joy_proc.wait(timeout=1.0)
            except Exception:
                joy_proc.kill()
    except Exception:
        pass
    finally:
        joy_proc = None


# =================================================================
# === GAME MECHANICS ===
# =================================================================

def choose_random_node():
    global available_nodes, last_node
    if not available_nodes:
        available_nodes = COLOR_TARGET_NODES.copy()
    pool = [n for n in available_nodes if n != last_node] or COLOR_TARGET_NODES
    node = random.choice(pool)
    if node in available_nodes:
        available_nodes.remove(node)
    last_node = node
    return node


def trigger_next_node():
    if game_started:
        node = choose_random_node()
        client.publish(TRIGGER_TOPICS[node], "start")


def update_main_screen():
    global game_started, timer_running
    if not game_started or not timer_running or start_time is None:
        return

    elapsed = time.time() - start_time
    percent = min(elapsed / GAME_DURATION, 1.0)

    canvas.delete("timer")
    cx, cy = get_center()
    draw_circle_progress(cx, cy - 20, 120, percent)
    canvas.itemconfig("score_text", text=str(hit_count))

    if elapsed >= GAME_DURATION:
        end_game()
    else:
        root.after(120, update_main_screen)


def show_main_screen():
    clear_screen()
    cx, cy = get_center()

    # simple card container
    draw_card(cx - 240, cy - 220, cx + 240, cy + 180)

    draw_text_center(cx, cy - 270, "Hover and Seek", 44, ACCENT_YELLOW, weight="bold", tag="title")

    draw_circle_progress(cx, cy - 20, 120, 0)
    draw_text_center(cx, cy - 40, str(hit_count), 76, TEXT_LIGHT, tag="score_text")
    draw_text_center(cx, cy + 36, "HITS", 24, TEXT_LIGHT, weight="normal", tag="score_label")

    # Exit button (top-right)
    exit_x, exit_y, exit_r = root.winfo_screenwidth() - 45, 45, 25
    canvas.create_oval(
        exit_x - exit_r, exit_y - exit_r, exit_x + exit_r, exit_y + exit_r,
        fill=ACCENT_YELLOW, outline="", tags="exit_btn"
    )
    canvas.create_text(
        exit_x, exit_y, text="X", font=(FONT_FAMILY, 18, "bold"),
        fill=BACKGROUND_COLOR, tags="exit_btn"
    )
    canvas.tag_bind("exit_btn", "<Button-1>", lambda e: root.destroy())


def show_score_screen():
    clear_screen()
    cx, cy = get_center()

    draw_card(cx - 260, cy - 160, cx + 260, cy + 160)
    draw_text_center(cx, cy - 70, "Final Score", 48, TEXT_LIGHT, weight="bold")
    draw_text_center(cx, cy + 20, str(hit_count), 120, ACCENT_YELLOW, weight="bold")


def show_startup_countdown(seconds=3):
    cx, cy = get_center()
    countdown_text = canvas.create_text(cx, cy + 220, text="", fill=TEXT_LIGHT,
                                        font=(FONT_FAMILY, 1, "bold"), tags="countdown_text")

    def animate_zoom_in(tag, max_size, steps, current_step=1):
        if current_step <= steps:
            size = int(max_size * (current_step / steps))
            canvas.itemconfig(tag, font=(FONT_FAMILY, size, "bold"))
            root.after(12, lambda: animate_zoom_in(tag, max_size, steps, current_step + 1))

    def update_count(count):
        if count > 0:
            canvas.itemconfig(countdown_text, text=str(count), font=(FONT_FAMILY, 1, "bold"))
            animate_zoom_in("countdown_text", 140, 18)
            root.after(1000, lambda: update_count(count - 1))
        else:
            canvas.itemconfig(countdown_text, text="GO!", font=(FONT_FAMILY, 1, "bold"))
            animate_zoom_in("countdown_text", 160, 14)
            root.after(600, start_game)

    canvas.itemconfig(countdown_text, text="Get Ready...", font=(FONT_FAMILY, 40, "normal"))
    root.after(1500, lambda: update_count(seconds))


def start_game():
    global hit_count, start_time, game_started, timer_running, last_node, available_nodes, begin_ts_unix
    hit_count = 0
    start_time = None
    timer_running = False
    game_started = True
    last_node = None
    available_nodes = COLOR_TARGET_NODES.copy()
    begin_ts_unix = None  # will be set on first hit
    show_main_screen()
    # Start selected controller helper
    if controller_type == 'joystick':
        start_joystick_control()
    else:
        # Default to gesture control when unspecified or any other value
        start_gesture_control()
    root.after(400, trigger_next_node)


def end_game():
    """Finish gameplay, write DB, signal completion immediately, then show score screen."""
    global game_started, timer_running, end_ts_unix
    if not game_started:
        return

    game_started = False
    timer_running = False
    end_ts_unix = now_ist_unix()

    # Stop controllers immediately
    stop_gesture_control()
    stop_joystick_control()

    # Reset nodes
    try:
        client.publish(RESET_TOPIC, "reset")
    except Exception:
        pass

    # Fallback begin timestamp if never started (no hits)
    begin_ts = end_ts_unix if begin_ts_unix is None else begin_ts_unix

    # Persist to DB (only if we have a token_id)
    if token_id is not None:
        print(f"DB write -> token={token_id}, game={game_number}, level={level_number}, score={hit_count}")
        record_result_to_db(token_id, game_number, level_number, hit_count, begin_ts, end_ts_unix)
    else:
        print("Skipping DB write: token_id is None.")

    # >>> Signal completion NOW so the web UI can switch to leaderboard while we display score
    try:
        with open(FLAG_FILE, "w") as f:
            f.write("done")
        print("Flag written (post-DB).")
    except Exception as e:
        print(f"Could not write flag file: {e}")

    # Show final score on this screen for a short while, then exit
    show_score_screen()
    root.after(SCORE_DISPLAY_DURATION * 1000, finish_and_exit)


def finish_and_exit():
    # Flag was already written in end_game(); just exit the UI cleanly
    print("Exiting game UI.")
    root.destroy()


# =================================================================
# === MQTT ===
# =================================================================
def on_connect(client, userdata, flags, rc):
    for topic in HIT_TOPICS:
        client.subscribe(topic)
    print(f"Subscribed to hit topics; rc={rc}")


def on_message(client, userdata, msg):
    global hit_count, start_time, timer_running, begin_ts_unix
    payload = msg.payload.decode().strip().lower()
    if not game_started:
        return
    if payload != "hit":
        return

    # Start timer on first valid hit
    if not timer_running:
        start_time = time.time()
        timer_running = True
        begin_ts_unix = now_ist_unix()
        update_main_screen()

    hit_count += 1
    canvas.itemconfig("score_text", text=str(hit_count))
    animate_score_pop()
    trigger_next_node()
    play_sound("target hit.wav")


def setup_mqtt():
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(BROKER, 1883, 60)
        client.loop_start()
        # small grace to let it connect
        time.sleep(0.5)
        # tell nodes we're preparing this game
        client.publish(PREPARE_TOPIC, "hoverandseek", retain=False)
        # clear node state
        client.publish(RESET_TOPIC, "reset")
    except Exception as e:
        print(f"MQTT Connection Error: {e}")
        # Minimal visual error message (avoid heavy drawing)
        cx, cy = get_center()
        draw_text_center(cx, cy, "MQTT CONNECTION FAILED", 28, ACCENT_YELLOW)
        draw_text_center(cx, cy + 40, "Is the broker running?", 20, TEXT_LIGHT, "normal")


# =================================================================
# === MAIN ===
# =================================================================
if __name__ == "__main__":
    # Read identity + chosen level
    token_id = read_token_id()
    game_number, level_number, controller_type = read_choice()
    if isinstance(controller_type, str):
        controller_type = controller_type.lower()
    print(f"Session -> token_id={token_id}, game={game_number}, level={level_number}, controller={controller_type}")

    setup_mqtt()

    # Initial UI + countdown
    clear_screen()
    show_main_screen()
    show_startup_countdown(3)

    try:
        root.mainloop()
    finally:
        # Cleanup MQTT loop
        try:
            client.loop_stop()
        except Exception:
            pass
        # Ensure controller helpers are stopped if UI closed early
        stop_gesture_control()
        stop_joystick_control()
