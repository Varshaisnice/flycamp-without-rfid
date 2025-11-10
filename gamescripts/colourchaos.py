#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Drone Confusion - with gesture and joystick controller support.

This is your provided Drone Confusion game, extended to:
- Launch an external gesture control helper (reads lines from stdout and treats lines containing "hit" as hits).
- Launch/stop an external joystick controller process.
- Read controller preference from META_PATH (if present) and start the selected controller when the game starts.
- Cleanly stop controller helpers when the game ends or UI exits.

Configuration:
  - GESTURE_CONTROL_PATH: path to the gesture helper (script/executable)
  - JOYSTICK_CONTROL_PATH: path to joystick helper (script/executable)

Note: This file keeps your original logic and UI, only adding controller process integration.
"""

import time
import tkinter as tk
import paho.mqtt.client as mqtt
import random
import requests
import os
import json
import subprocess
import threading

# =================================================================
# === CONFIGURATION (UPDATED) ===
# =================================================================
BROKER = "localhost"
GAME_DURATION_SECONDS = 30
POINTS_CORRECT = 50
POINTS_INCORRECT = -10

# UPDATED: New 5-color palette
COLOR_NODES_MAP = {
    "node1": "WHITE",
    "node2": "GREEN",
    "node3": "BLUE",    # Changed from CYAN
    "node4": "YELLOW",  # Changed from MAGENTA
    "node5": "RED"
}
ALL_NODES = list(COLOR_NODES_MAP.keys())
COLORS = list(COLOR_NODES_MAP.values())

# UPDATED: Corresponding hex codes for the UI
DISPLAY_COLORS = {
    'RED': '#ff4757',
    'GREEN': '#2ed573',
    'BLUE': '#007bff',   # Changed from CYAN
    'YELLOW': '#FFC300', # Changed from MAGENTA
    'WHITE': '#f0f0f0',
    'BACKGROUND_DEFAULT': '#10375C',
    'TEXT_DEFAULT': '#f0f0f0',
    'TIMER_RING': '#D7F7F5',
    'TIMER_ARC': '#2ed573'
}

# --- MQTT Topics ---
HIT_TOPICS = [f"game/hit/{nid}" for nid in ALL_NODES]
RESET_TOPIC = "game/reset"
PREPARE_TOPIC = "game/prepare"
HIT_FEEDBACK_TOPIC_TEMPLATE = "game/hit_feedback/{}"
SCORE_TOPIC = "game/score"
NODE_COLOR_TO_ID = {v: k for k, v in COLOR_NODES_MAP.items()}

# Controller helper paths (adjust as needed)
META_PATH = "/home/devesh/game_meta.json"
GESTURE_CONTROL_PATH = os.environ.get("GESTURE_CONTROL_PATH", "/home/devesh/Gesture-Control/GuestureControl.py")
JOYSTICK_CONTROL_PATH = os.environ.get("JOYSTICK_CONTROL_PATH", "/home/devesh/Joystick_Control/Joystick_Control.py")

# =================================================================
# === MASTER RULE SET FOR THE ENTIRE GAME ===
# =================================================================
CUE_TYPES = ['BACKGROUND', 'TEXT_COLOR', 'WORD']
MASTER_CUE_TYPE = random.choice(CUE_TYPES)
print("="*40)
print(f"SECRET MASTER RULE FOR THIS GAME: {MASTER_CUE_TYPE}")
print("="*40)
# =================================================================

# === GAME STATE & UI SETUP ===
score = 0
start_time = None
game_started = False
timer_running = False
accepting_input = True
current_puzzle = {}
controller_type = None  # 'gesture' or 'joystick' or None

# Gesture/joystick process state
gesture_proc = None
gesture_thread = None
gesture_stop_event = threading.Event()

joy_proc = None

root = tk.Tk()
root.title("Drone Confusion")
root.attributes('-fullscreen', True)
root.configure(bg=DISPLAY_COLORS['BACKGROUND_DEFAULT'])
canvas = tk.Canvas(root, bg=DISPLAY_COLORS['BACKGROUND_DEFAULT'], highlightthickness=0)
canvas.pack(fill="both", expand=True)
main_text_id, score_text_id, timer_arc_id, timer_circle_id, exit_button = None, None, None, None, None

# Using a more specific client ID to avoid conflicts
client = mqtt.Client("drone_confusion_ui_v7")

# =================================================================
# === CORE FUNCTIONS ===
# =================================================================

def set_new_puzzle():
    """Generates a new puzzle based on the new color rules and the consistent Master Rule."""
    global current_puzzle
    
    bg_color, word_color = random.sample(COLORS, 2)
    possible_text_colors = [c for c in COLORS if c != bg_color]
    text_color = random.choice(possible_text_colors)

    correct_cue = MASTER_CUE_TYPE 
    if correct_cue == 'BACKGROUND': correct_answer = bg_color
    elif correct_cue == 'TEXT_COLOR': correct_answer = text_color
    else: correct_answer = word_color
        
    current_puzzle = {
        "background_color": bg_color, "text_color": text_color,
        "word": word_color, "correct_answer": correct_answer,
    }

    update_puzzle_display()
    print(f"\n--- New Round ---")
    print(f"  Word: '{word_color}', Text Color: {text_color}, BG Color: {bg_color}")
    print(f"  Master Rule is '{MASTER_CUE_TYPE}', so Correct Answer is: {correct_answer}")


def update_puzzle_display():
    """Updates the puzzle display with a text shadow for visibility."""
    global main_text_id
    
    # Clear previous text elements to prevent artifacts
    canvas.delete("main_text_element")

    bg_hex = DISPLAY_COLORS.get(current_puzzle.get("background_color"), '#000')
    txt_hex = DISPLAY_COLORS.get(current_puzzle.get("text_color"), '#FFF')
    word = current_puzzle.get("word")
    
    root.configure(bg=bg_hex)
    canvas.configure(bg=bg_hex)
    
    cx, cy = get_center()
    font_size = int(root.winfo_screenwidth() * 0.08)
    main_font = ("Segoe UI", font_size, "bold")
    
    # NEW: Create a subtle black shadow for contrast
    # The shadow is drawn first, slightly offset
    shadow_offset = max(2, int(font_size * 0.02)) # Responsive shadow size
    canvas.create_text(cx + shadow_offset, cy + shadow_offset, text=word, fill="black", font=main_font, tags="main_text_element")

    # The main colored text is drawn on top
    main_text_id = canvas.create_text(cx, cy, text=word, fill=txt_hex, font=main_font, tags="main_text_element")
    
    update_score_display()


def on_message(client, userdata, msg):
    """Handles incoming hits and sends feedback commands back to the nodes."""
    global score, start_time, timer_running, accepting_input
    if not game_started or not accepting_input: return
    
    try:
        payload = msg.payload.decode().strip()
    except Exception:
        payload = ""
    if payload != "hit": return
        
    node_id = msg.topic.split("/")[-1]
    hit_color = COLOR_NODES_MAP.get(node_id)
    if not hit_color: return

    if not timer_running:
        start_time = time.time()
        timer_running = True
        update_timer_display()

    feedback_topic = HIT_FEEDBACK_TOPIC_TEMPLATE.format(node_id)

    if hit_color == current_puzzle["correct_answer"]:
        score += POINTS_CORRECT
        print(f"✅ Correct! Score: {score}")
        accepting_input = False
        client.publish(feedback_topic, "correct")
        client.publish(SCORE_TOPIC, str(score))
        flash_feedback(DISPLAY_COLORS['GREEN'])
        # re-enable accepting_input after delay and start new puzzle
        root.after(1000, lambda: (set_new_puzzle(), _set_accepting_input(True)))
    else:
        score += POINTS_INCORRECT
        print(f"❌ Incorrect. Score: {score}")
        client.publish(feedback_topic, "incorrect")
        client.publish(SCORE_TOPIC, str(score))
        flash_feedback(DISPLAY_COLORS['RED'])
    
    update_score_display()

def _set_accepting_input(val: bool):
    global accepting_input
    accepting_input = val

def start_game():
    """Initializes and starts the main game loop."""
    global score, start_time, game_started, timer_running, accepting_input, controller_type
    score, start_time, timer_running, game_started, accepting_input = 0, None, False, True, True
    clear_screen()
    update_score_display()
    client.publish(SCORE_TOPIC, "0")
    set_new_puzzle()

    # Read controller selection from meta if available
    try:
        with open(META_PATH, "r") as m:
            _meta = json.load(m)
            ct = _meta.get("controller")
            if isinstance(ct, str):
                controller_type = ct.lower()
    except Exception:
        # leave controller_type as is (None => default to gesture)
        pass

    # Start controller helper according to selection
    if controller_type == "joystick":
        start_joystick_control()
    else:
        start_gesture_control()
    
# --- The rest of the helper functions are unchanged ---
def get_center():
    root.update_idletasks(); w,h=root.winfo_screenwidth(),root.winfo_screenheight(); return w//2,h//2
def clear_screen():
    canvas.delete("all"); global main_text_id,score_text_id,timer_arc_id,timer_circle_id; main_text_id,score_text_id,timer_arc_id,timer_circle_id=None,None,None,None; create_exit_button()
def create_exit_button():
    global exit_button; exit_button = tk.Button(root, text="X", font=("Arial",20,"bold"),fg="white",bg="red",command=root.destroy,relief="flat"); canvas.create_window(root.winfo_screenwidth()-30,30,window=exit_button,anchor="ne")
def update_score_display():
    global score_text_id; cx,_=get_center()
    canvas.delete("score_text_element")
    score_text_id=canvas.create_text(cx,50,text=f"Score: {score}",fill=DISPLAY_COLORS['TEXT_DEFAULT'],font=("Segoe UI",36,"bold"), tags="score_text_element")
def flash_feedback(color_hex,duration_ms=150):
    canvas.configure(bg=color_hex); root.configure(bg=color_hex); root.after(duration_ms, lambda: update_puzzle_display())
def update_timer_display():
    if not game_started or not timer_running or start_time is None: return
    global timer_arc_id,timer_circle_id; cx,cy=get_center(); r=int(root.winfo_screenwidth()*0.15); elapsed=time.time()-start_time; p=min(elapsed/GAME_DURATION_SECONDS,1); angle=p*360
    if timer_circle_id is None: timer_circle_id=canvas.create_oval(cx-r,cy-r,cx+r,cy+r,outline=DISPLAY_COLORS['TIMER_RING'],width=12)
    if timer_arc_id is None: timer_arc_id=canvas.create_arc(cx-r,cy-r,cx+r,cy+r,start=90,extent=0,style="arc",outline=DISPLAY_COLORS['TIMER_ARC'],width=20)
    canvas.tag_raise("main_text_element"); canvas.tag_raise("score_text_element"); canvas.itemconfig(timer_arc_id,extent=-angle)
    if elapsed>=GAME_DURATION_SECONDS: end_game()
    else: root.after(100,update_timer_display)
def show_startup_countdown(seconds=3):
    clear_screen(); cx,cy=get_center(); font_size=int(root.winfo_screenwidth()*0.1); count_id=canvas.create_text(cx,cy,text=str(seconds),fill=DISPLAY_COLORS['TEXT_DEFAULT'],font=("Segoe UI",font_size,"bold"))
    def update_count(c):
        if c>0: canvas.itemconfig(count_id,text=str(c)); root.after(1000,lambda:update_count(c-1))
        else: canvas.itemconfig(count_id,text="Go!"); root.after(500,start_game)
    update_count(seconds)
def end_game():
    global game_started,timer_running,accepting_input
    if not game_started:return
    game_started,timer_running,accepting_input=False,False,False
    # Stop controllers
    stop_gesture_control()
    stop_joystick_control()
    client.publish(RESET_TOPIC,"reset")
    submit_score(score)
    show_score_screen(score)
def show_score_screen(final_score):
    clear_screen(); cx,cy=get_center(); canvas.configure(bg=DISPLAY_COLORS['BACKGROUND_DEFAULT']); root.configure(bg=DISPLAY_COLORS['BACKGROUND_DEFAULT']);
    canvas.create_text(cx,cy-80,text="Final Score",font=("Segoe UI",60,"bold"),fill="gold"); canvas.create_text(cx,cy+50,text=str(final_score),font=("Segoe UI",120,"bold"),fill=DISPLAY_COLORS['TEXT_DEFAULT']);
    canvas.create_text(cx,cy+180,text="Returning to console...",font=("Segoe UI",30,"italic"),fill="grey"); root.after(5000,root.destroy)
def submit_score(s):
    try:
        with open("rfid_token.txt","r") as f: rfid=f.read().strip()
    except FileNotFoundError: print("RFID token file not found."); return
    data={"rfid_token":rfid,"score":s}; url="http://localhost:5000/submit_score"
    try:
        res=requests.post(url,json=data)
        if res.status_code==200: print(f"Score ({s}) submitted successfully.")
        else: print(f"Score submission failed: {res.status_code}-{res.text}")
    except requests.exceptions.RequestException as e: print(f"Error submitting score: {e}")
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT Broker with result code {rc}");
    for topic in HIT_TOPICS: client.subscribe(topic)
def setup_mqtt():
    client.on_connect=on_connect; client.on_message=on_message
    try: client.connect(BROKER,1883,60); client.loop_start()
    except ConnectionRefusedError: print("MQTT Connection Refused."); root.destroy()

# =================================================================
# === GESTURECONTROL PROCESS INTEGRATION (mirrors hover_and_seek) ===
# =================================================================
def _on_gesture_hit():
    """
    Called on the Tk main thread when gesturecontrol indicates a hit.
    Mirrors the behaviour in on_message for MQTT hits.
    """
    global score, start_time, timer_running, accepting_input
    if not game_started:
        return

    if not timer_running:
        start_time = time.time()
        timer_running = True
        update_timer_display()

    # Treat gesture hit as a correct hit on the current target (simulate behaviour)
    # For Drone Confusion we simply accept a gesture as a "hit" that should be evaluated
    # against current puzzle's correct answer by picking a random node that generated it.
    # Simpler approach: convert gesture hit into the same logic as a node "hit" from MQTT
    # by pretending the player hit the correct node — increment score and proceed.
    # This keeps gesture semantics simple (gesture == "I hit correctly").
    score_increment_handler_for_gesture()


def score_increment_handler_for_gesture():
    """Handle a hit coming from gesture control as if it were correct."""
    global score, accepting_input
    if not accepting_input:
        return
    score += POINTS_CORRECT
    print(f"[gesture] Correct! Score: {score}")
    accepting_input = False
    client.publish(SCORE_TOPIC, str(score))
    flash_feedback(DISPLAY_COLORS['GREEN'])
    update_score_display()
    # Next puzzle after short delay
    root.after(800, lambda: (set_new_puzzle(), _set_accepting_input(True)))


def _gesture_reader_thread(proc, stop_event):
    """
    Background thread that reads stdout from the gesturecontrol process.
    Any line containing 'hit' (case-insensitive) is treated as a hit event.
    """
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
    """
    Start the gesturecontrol helper program if present and not already running.
    Spawns a background thread that listens to stdout for gesture events.
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
def start_joystick_control():
    global joy_proc
    if joy_proc is not None:
        return
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
            try:
                joy_proc.terminate()
            except Exception:
                pass
            try:
                joy_proc.wait(timeout=1.0)
            except Exception:
                try:
                    joy_proc.kill()
                except Exception:
                    pass
    except Exception as e:
        print(f"Error stopping joystick control: {e}")
    finally:
        joy_proc = None

# =================================================================
# === MAIN EXECUTION ===
# =================================================================
if __name__ == "__main__":
    # Read controller selection from meta if available (initial)
    try:
        with open(META_PATH, "r") as m:
            _meta = json.load(m)
            ct = _meta.get("controller")
            if isinstance(ct, str):
                controller_type = ct.lower()
    except Exception:
        controller_type = None

    setup_mqtt(); time.sleep(1); client.publish(PREPARE_TOPIC, "droneconfusion", retain=False)
    create_exit_button(); show_startup_countdown(3)
    try:
        root.mainloop()
    finally:
        client.loop_stop()
        print("Game window closed.")
        stop_gesture_control()
        stop_joystick_control()
        with open("/home/devesh/game_done.flag","w") as f: f.write("done")
