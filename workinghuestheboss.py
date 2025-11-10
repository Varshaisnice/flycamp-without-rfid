import time
import tkinter as tk
import paho.mqtt.client as mqtt
import random

# === CONFIG ===
BROKER = "localhost"
NODES = ["node1", "node2", "node3", "node4", "node5"]
HIT_TOPICS = [f"game/hit/{nid}" for nid in NODES]
TRIGGER_TOPICS = {nid: f"game/trigger/{nid}" for nid in NODES}
RESET_TOPIC = "game/reset"
COLOR_TOPIC = "game/color"
GAME_DURATION = 60  # seconds
SEQUENCE_LENGTH = 60  # set this to any number of colors you want in the sequence

# === GAME STATE ===
hit_count = 0
start_time = None
game_started = False
timer_running = False
current_color_index = 0
color_sequence = []
color_to_node = {}
target_color = None

# === FIXED NODE COLORS (MATCH NODE FIRMWARE) ===
NODE_COLORS = {
    "node1": "green",
    "node2": "white",
    "node3": "cyan",
    "node4": "yellow",
    "node5": "orange"
}

# === GUI ===
root = tk.Tk()
root.title("ShieldWorld")
root.attributes('-fullscreen', True)
root.configure(bg="black")

canvas = tk.Canvas(root, bg="black", highlightthickness=0)
canvas.pack(fill="both", expand=True)

power_button = None
exit_button = None
power_button_pressed = False
hold_start_time = 0

client = mqtt.Client("shieldworld_ui")

# === UTILITIES ===
def get_center():
    root.update_idletasks()
    w = root.winfo_screenwidth()
    h = root.winfo_screenheight()
    return w // 2, h // 2

def clear_screen():
    canvas.delete("all")

def draw_circle_progress(x, y, r, percent, color):
    canvas.create_oval(x - r, y - r, x + r, y + r, outline="deepskyblue", width=12, tags="timer")
    angle = percent * 360
    canvas.create_arc(x - r, y - r, x + r, y + r, start=90, extent=-angle,
                      style="arc", outline=color, width=20, tags="timer")

def draw_text_center(x, y, text, size=48, color="red", weight="bold", tag=None):
    canvas.create_text(x, y, text=text, fill=color, font=("Myriad Pro", size, weight), tags=tag)

def draw_target_color():
    if not target_color:
        return
    cx, cy = get_center()
    canvas.delete("target_color")
    draw_text_center(cx, cy + 200, f"TARGET: {target_color.upper()}", 48, target_color, tag="target_color")

def generate_color_sequence():
    global color_sequence, color_to_node
    base_colors = list(NODE_COLORS.values())
    color_sequence = [random.choice(base_colors) for _ in range(SEQUENCE_LENGTH)]
    color_to_node = {color: node for node, color in NODE_COLORS.items()}
    print("🎯 Color sequence:", color_sequence)
    print("🎯 Color → Node:", color_to_node)

def trigger_next_node():
    global target_color
    if game_started and current_color_index < len(color_sequence):
        target_color = color_sequence[current_color_index]
        draw_target_color()
        print(f"🚀 Triggering round {current_color_index + 1}: {target_color}")

        client.publish(COLOR_TOPIC, target_color, retain=True)

        for node_id in NODES:
            client.publish(TRIGGER_TOPICS[node_id], "start")

def update_main_screen():
    global game_started, start_time
    if not game_started or not timer_running or start_time is None:
        return

    elapsed = time.time() - start_time
    percent = min(elapsed / GAME_DURATION, 1)
    remaining = GAME_DURATION - elapsed

    canvas.delete("timer")
    canvas.delete("score")
    cx, cy = get_center()
    draw_circle_progress(cx, cy - 20, 160, percent, "green")
    draw_text_center(cx, cy - 20, str(hit_count), 72, "white", tag="score")
    draw_target_color()

    if remaining <= 0:
        end_game()
    else:
        root.after(100, update_main_screen)

def show_main_screen():
    global power_button, exit_button
    clear_screen()
    cx, cy = get_center()
    draw_text_center(cx, cy - 260, "Hues Detected", 54, "white", tag="title")
    draw_circle_progress(cx, cy - 20, 160, 0, "white")
    draw_text_center(cx, cy - 20, str(hit_count), 72, "white", tag="score")
    draw_target_color()

    if not game_started:
        power_button = tk.Button(root, text="START", font=("Myriad Pro", 36, "bold"),
                                 fg="black", bg="lime", activeforeground="black",
                                 activebackground="green", relief="flat", width=10, height=1)
        power_button.bind("<ButtonPress>", lambda e: on_button_press())
        power_button.bind("<ButtonRelease>", lambda e: on_button_release())
        canvas.create_window(100, root.winfo_screenheight() - 60, window=power_button, anchor="sw")

    exit_button = tk.Button(root, text="X", font=("Arial", 20, "bold"),
                            fg="white", bg="red", command=root.destroy)
    canvas.create_window(root.winfo_screenwidth() - 30, 30, window=exit_button, anchor="ne")

def start_game():
    global hit_count, start_time, game_started, timer_running, current_color_index
    hit_count = 0
    start_time = None
    timer_running = False
    game_started = True
    current_color_index = 0
    generate_color_sequence()
    show_main_screen()
    root.after(500, trigger_next_node)

def end_game():
    global game_started, timer_running
    game_started = False
    timer_running = False
    show_main_screen()

def on_button_press():
    global power_button_pressed, hold_start_time
    power_button_pressed = True
    hold_start_time = time.time()
    check_hold()

def on_button_release():
    global power_button_pressed
    power_button_pressed = False
    if not game_started:
        start_game()

def check_hold():
    if power_button_pressed:
        if time.time() - hold_start_time > 5:
            root.destroy()
        else:
            root.after(100, check_hold)

# === MQTT CALLBACKS ===
def on_connect(client, userdata, flags, rc):
    for topic in HIT_TOPICS:
        print(f"🔔 Subscribed to {topic}")
        client.subscribe(topic)

def on_message(client, userdata, msg):
    global hit_count, start_time, timer_running, current_color_index, target_color
    if not game_started:
        return

    node = msg.topic.split("/")[-1].lower()
    payload = msg.payload.decode().strip().lower()
    print("📩 MQTT HIT:", node, payload)

    expected_node = color_to_node.get(target_color, "").lower()
    print("🔍 Expected:", expected_node, "| Got:", node)

    if payload == "hit" and node == expected_node:
        print("✅ Correct hit!")
        if hit_count == 0 and not timer_running:
            start_time = time.time()
            timer_running = True
            update_main_screen()
        hit_count += 1
        current_color_index += 1
        trigger_next_node() if current_color_index < len(color_sequence) else end_game()
    else:
        print("❌ Wrong hit or no match.")

# === MQTT INIT ===
def setup_mqtt():
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    client.loop_start()
    client.publish(RESET_TOPIC, "reset")

# === MAIN ===
setup_mqtt()
show_main_screen()
root.mainloop()
