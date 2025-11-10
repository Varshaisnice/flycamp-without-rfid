#!/usr/bin/env python3
"""
Hues Detected - main UI with MQTT and Gesture control integration,
extended to call an RC car control process when the game starts.

Changes:
- Added RC_CAR_CONTROL_PATH constant.
- Implemented start_rc_car_control() and stop_rc_car_control() to launch/stop an external
  RC car controller (executable or Python script).
- start_rc_car_control() is invoked when start_game() runs (after controller selection).
- stop_rc_car_control() is invoked when the game ends and at program exit for cleanup.

Adjust RC_CAR_CONTROL_PATH to point to your rc_car_control executable or script.
"""

import time
import tkinter as tk
import paho.mqtt.client as mqtt
import random
import sqlite3
import os
import json
import subprocess
import threading

# =================================================================
# === CONFIGURATION (CORRECTED) ===
# =================================================================
BROKER = "localhost"

NODE_COLORS = {
    "node2": "green",
    "node3": "blue",
    "node4": "yellow",
    "node5": "red"
}

COLOR_NODES = ["node2", "node3", "node4", "node5"]
ALL_NODES = ["node1"] + COLOR_NODES

HIT_TOPICS = [f"game/hit/{nid}" for nid in COLOR_NODES]
TRIGGER_TOPICS = {nid: f"game/trigger/{nid}" for nid in ALL_NODES}
RESET_TOPIC = "game/reset"
COLOR_TOPIC = "game/color"
PREPARE_TOPIC = "game/prepare"

GAME_DURATION = 30
SEQUENCE_LENGTH = 300

DB_PATH = "/home/devesh/Console/fly_camp_console/arcade.db"
FLAG_FILE = "/home/devesh/game_done.flag"
GESTURE_CONTROL_PATH = "/home/devesh/Gesture-Control/GuestureControl.py"
RC_CAR_CONTROL_PATH = "/home/devesh/Console/fly_camp_console/rc_car_control.py" 
META_PATH = "/home/devesh/game_meta.json"

# =================================================================
# === GAME STATE ===
# =================================================================
controller_type = None
hit_count = 0
start_time = None
game_started = False
timer_running = False
current_color_index = 0
color_sequence = []
color_to_node = {}
target_color = None

score_id = None
timer_arc_id = None
timer_circle_id = None

# -----------------------------------------------------------------
# === Gesture Control State ===
gesture_proc = None
gesture_thread = None
gesture_stop_event = threading.Event()
begin_ts_unix = None

# -----------------------------------------------------------------
# === RC Car Control State ===
rc_proc = None
rc_stop_event = threading.Event()

# =================================================================
# === CONTROLLER HELPERS ===
# =================================================================

def get_controller_type():
    return controller_type or 'joystick'


def get_drone_direction():
    # Not used in gesture-only mode; kept for compatibility.
    return 'hover'

# =================================================================
# === UI & GAME LOGIC ===
# =================================================================
root = tk.Tk()
root.title("Hues Detected")
root.attributes('-fullscreen', True)
root.configure(bg="#10375C")
canvas = tk.Canvas(root, bg="#10375C", highlightthickness=0)
canvas.pack(fill="both", expand=True)

exit_button = None

client = mqtt.Client("hues_detected_ui_v2")

def get_center():
    root.update_idletasks()
    w = root.winfo_screenwidth()
    h = root.winfo_screenheight()
    return w // 2, h // 2

def clear_screen():
    canvas.delete("all")
    global score_id, timer_arc_id, timer_circle_id
    score_id, timer_arc_id, timer_circle_id = None, None, None
    create_exit_button()

def create_exit_button():
    global exit_button
    exit_button = tk.Button(root, text="X", font=("Arial", 20, "bold"),
                            fg="white", bg="red", command=root.destroy, relief="flat")
    canvas.create_window(root.winfo_screenwidth() - 30, 30, window=exit_button, anchor="ne")

def draw_text_center(x, y, text, size=48, color="red", weight="bold", tag=None):
    canvas.create_text(x, y, text=text, fill=color, font=("Segoe UI", size, weight), tags=tag)

def draw_target_color():
    if not target_color:
        return
    cx, cy = get_center()
    canvas.delete("target_color")
    draw_text_center(cx, cy + 250, text=f"TARGET: {target_color.upper()}",
                     size=48, color=target_color, weight="bold", tag="target_color")

def generate_color_sequence():
    global color_sequence, color_to_node
    base_colors = list(NODE_COLORS.values())
    color_sequence = []
    last_color = None
    for _ in range(SEQUENCE_LENGTH):
        options = [c for c in base_colors if c != last_color]
        next_color = random.choice(options)
        color_sequence.append(next_color)
        last_color = next_color
    color_to_node = {color: node for node, color in NODE_COLORS.items()}
    print("Generated color sequence:", color_sequence[:10], "...")
    print("Color to node mapping:", color_to_node)

def trigger_next_node():
    global target_color
    if game_started and current_color_index < len(color_sequence):
        target_color = color_sequence[current_color_index]
        update_ui_elements()
        print(f"Triggering round {current_color_index + 1}: {target_color}")
        client.publish(COLOR_TOPIC, target_color)
        for node_id in ALL_NODES:
            client.publish(TRIGGER_TOPICS[node_id], "start")

def update_ui_elements():
    cx, cy = get_center()
    canvas.delete("score")
    draw_text_center(cx, cy, str(hit_count), 120, "white", "bold", "score")
    draw_target_color()

def update_timer_ring():
    if not game_started or not timer_running or start_time is None: return
    elapsed = time.time() - start_time
    percent = min(elapsed / GAME_DURATION, 1)
    cx, cy = get_center()
    radius = 180
    angle = percent * 360
    if timer_circle_id is None:
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                           outline="#D7F7F5", width=15, tags="timer_ring")
    canvas.delete("timer_arc")
    if angle > 0:
        canvas.create_arc(cx - radius, cy - radius, cx + radius, cy + radius,
                          start=90, extent=-angle, style="arc",
                          outline="#2ed573", width=20, tags="timer_arc")
    if elapsed >= GAME_DURATION: end_game()
    else: root.after(100, update_timer_ring)

def show_startup_countdown(seconds=3):
    clear_screen()
    cx, cy = get_center()
    draw_text_center(cx, cy - 260, "Hues Detected", 60, "#FFC300", tag="title")
    label_id = canvas.create_text(cx, cy, text="", fill="white", font=("Segoe UI", 60, "bold"))
    def update_count(count):
        if count > 0:
            canvas.itemconfig(label_id, text=f"Game starts in {count}...")
            root.after(1000, lambda: update_count(count - 1))
        else:
            canvas.itemconfig(label_id, text="Start!")
            root.after(500, start_game)
    canvas.itemconfig(label_id, text="Preparing nodes...")
    root.after(1000, lambda: update_count(seconds))

def show_main_screen():
    clear_screen()
    cx, cy = get_center()
    draw_text_center(cx, cy - 260, "Hues Detected", 60, "#FFC300", tag="title")
    update_ui_elements()

def start_game():
    global hit_count, start_time, timer_running, game_started, current_color_index
    hit_count, start_time, timer_running, game_started, current_color_index = 0, None, False, True, 0
    generate_color_sequence()
    show_main_screen()
    # Start selected controller helper
    try:
        with open(META_PATH, "r") as m:
            _meta = json.load(m)
            ct = str(_meta.get("controller", "joystick")).lower()
            if ct == "gesture":
                start_gesture_control()
            else:
                start_joystick_control()
    except Exception:
        start_joystick_control()

    # Start RC car control when the game starts
    start_rc_car_control()

    root.after(500, trigger_next_node)

# =================================================================
# === SCORE SUBMISSION (LOCAL DB) ===
# =================================================================
def submit_score(score):
    try:
        with open("rfid_token.txt", "r") as f:
            rfid_token = f.read().strip()
    except FileNotFoundError:
        print("RFID token not found.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # get token_id
        c.execute("SELECT token_id FROM RFIDTokens WHERE rfid_uid=?", (rfid_token,))
        row = c.fetchone()
        if not row:
            print("Unknown RFID token:", rfid_token)
            conn.close()
            return
        token_id = row[0]

        begin_ts = int(start_time) if start_time else int(time.time())
        end_ts = int(time.time())

        # Insert into GamePlays
        c.execute("""
            INSERT INTO GamePlays (token_id, game_number, level_number, score, begin_timestamp, end_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token_id, 2, 1, score, begin_ts, end_ts))  # game_number=2 for HuesTheBoss, level_number=1 fixed

        # Update PlayerBests
        c.execute("""
            SELECT highest_score FROM PlayerBests
            WHERE token_id=? AND game_number=? AND level_number=?
        """, (token_id, 2, 1))
        row = c.fetchone()
        if not row or score > row[0]:
            if row:
                c.execute("""
                    UPDATE PlayerBests SET highest_score=?, timestamp_achieved=?
                    WHERE token_id=? AND game_number=? AND level_number=?
                """, (score, end_ts, token_id, 2, 1))
            else:
                c.execute("""
                    INSERT INTO PlayerBests (token_id, game_number, level_number, highest_score, timestamp_achieved)
                    VALUES (?, ?, ?, ?, ?)
                """, (token_id, 2, 1, score, end_ts))

        conn.commit()
        conn.close()
        print(f"Score submitted to DB: {score}")
    except Exception as e:
        print("Error writing to DB:", e)
        
# =================================================================
# === GESTURECONTROL PROCESS INTEGRATION ===
# =================================================================
def _on_gesture_hit():
    global hit_count, start_time, timer_running, begin_ts_unix
    if not game_started:
        return

    if not timer_running:
        start_time = time.time()
        timer_running = True
        begin_ts_unix = int(time.time())
        update_timer_ring()

    # treat gesture hit like an MQTT 'hit'
    hit_count += 1
    update_ui_elements()
    trigger_next_node()

def _gesture_reader_thread(proc, stop_event):
    try:
        if proc.stdout is None:
            return
        for raw in proc.stdout:
            if stop_event.is_set():
                break
            line = raw.strip()
            if not line:
                continue
            if "hit" in line.lower():
                try:
                    root.after(0, _on_gesture_hit)
                except Exception:
                    pass
            else:
                print(f"[gesturecontrol] {line}")
    except Exception as e:
        print(f"Gesture reader thread error: {e}")
    finally:
        try:
            if proc.stderr:
                err = proc.stderr.read()
                if err:
                    print(f"[gesturecontrol:stderr] {err.strip()}")
        except Exception:
            pass

def start_gesture_control():
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

# =================================================================
# === RC CAR CONTROL PROCESS INTEGRATION ===
# =================================================================
def start_rc_car_control():
    """
    Start the RC car control process. RC_CAR_CONTROL_PATH can be:
      - an executable file (then it will be run directly), or
      - a Python script (ending with .py or readable) - will be run with python3.
    The function stores the subprocess in rc_proc for later shutdown.
    """
    global rc_proc, rc_stop_event
    if rc_proc is not None:
        return

    path = RC_CAR_CONTROL_PATH
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
        chosen = path  # fall back to what user configured; it may be in PATH

    try:
        rc_stop_event.clear()
        if chosen.endswith(".py") or not os.access(chosen, os.X_OK):
            cmd = ["python3", chosen]
        else:
            cmd = [chosen]

        print(f"Starting RC car control: {' '.join(cmd)}")
        # Start without capturing stdout/stderr to avoid blocking unless you want logs.
        rc_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        # Optionally, you could spawn a reader thread to log rc_proc stdout/stderr similar to gesture.
    except Exception as e:
        print(f"Failed to start RC car control ({chosen}): {e}")
        rc_proc = None
        rc_stop_event.clear()

def stop_rc_car_control():
    """
    Stop the RC car control process if it was started by start_rc_car_control().
    """
    global rc_proc, rc_stop_event
    try:
        rc_stop_event.set()
        if rc_proc:
            try:
                rc_proc.terminate()
            except Exception:
                pass
            try:
                rc_proc.wait(timeout=1.0)
            except Exception:
                try:
                    rc_proc.kill()
                except Exception:
                    pass
            # drain remaining output if any
            try:
                if rc_proc.stdout:
                    out = rc_proc.stdout.read()
                    if out:
                        print(f"[rc_car_control:stdout] {out.strip()}")
                if rc_proc.stderr:
                    err = rc_proc.stderr.read()
                    if err:
                        print(f"[rc_car_control:stderr] {err.strip()}")
            except Exception:
                pass
    except Exception as e:
        print(f"Error stopping RC car control: {e}")
    finally:
        rc_proc = None
        rc_stop_event.clear()

# =================================================================
# === JOYSTICK PLACEHOLDERS ===
# =================================================================
def start_joystick_control():
    # Placeholder for joystick start (no-op here)
    print("Joystick control started (placeholder).")

def stop_joystick_control():
    # Placeholder for joystick stop (no-op here)
    print("Joystick control stopped (placeholder).")

# =================================================================
# === GAME END HANDLING ===
# =================================================================
def end_game():
    global game_started, timer_running
    game_started, timer_running = False, False
    stop_gesture_control()  # Disable gesture control
    stop_rc_car_control()   # Stop RC car control when game ends
    try:
        stop_joystick_control()
    except Exception:
        pass
    client.publish(COLOR_TOPIC, "none")
    submit_score(hit_count)
    show_score_screen(hit_count)

def show_score_screen(score):
    clear_screen()
    cx, cy = get_center()
    draw_text_center(cx, cy - 80, "Your Score", size=60, color="gold", tag="score_title")
    draw_text_center(cx, cy + 20, str(score), size=100, color="#FFC300", tag="score_value")
    draw_text_center(cx, cy + 150, "Returning to console...", size=30, color="grey", tag="closing_message")
    root.after(4000, root.destroy)

# =================================================================
# === MQTT ===
# =================================================================
def on_connect(client, userdata, flags, rc):
    for topic in HIT_TOPICS: client.subscribe(topic)
    print(f"Subscribed to {len(HIT_TOPICS)} hit topics.")

def on_message(client, userdata, msg):
    global hit_count, start_time, timer_running, current_color_index, target_color
    topic = msg.topic
    payload = msg.payload.decode().strip().lower()
    if not game_started or target_color is None: return
    node_id = topic.split("/")[-1]
    expected_node = color_to_node.get(target_color)
    if payload == "hit" and node_id == expected_node:
        print(f"✅ Correct hit on {target_color} ({node_id})!")
        target_color = None
        if not timer_running:
            start_time = time.time()
            timer_running = True
            update_timer_ring()
        hit_count += 1
        current_color_index += 1
        update_ui_elements()
        if current_color_index < len(color_sequence): trigger_next_node()
        else: end_game()

def setup_mqtt():
    client.on_connect, client.on_message = on_connect, on_message
    try:
        client.connect(BROKER, 1883, 60); client.loop_start()
    except ConnectionRefusedError:
        print("MQTT connection refused."); root.destroy()

# =================================================================
# === MAIN EXECUTION ===
# =================================================================
if __name__ == "__main__":
    setup_mqtt()
    time.sleep(1)
    client.publish(PREPARE_TOPIC, "huestheboss", retain=False)

    # Read controller selection from meta if available
    try:
        with open(META_PATH, "r") as m:
            _meta = json.load(m)
            ct = _meta.get("controller")
            if isinstance(ct, str):
                globals()["controller_type"] = ct.lower()
    except Exception:
        pass

    show_startup_countdown(3)

    try:
        root.mainloop()
    finally:
        client.loop_stop()
        print("Game window closed.")
        stop_gesture_control()  # Cleanup gesture control at exit
        stop_rc_car_control()   # Cleanup RC car control at exit
        with open(FLAG_FILE, "w") as f: f.write("done")
