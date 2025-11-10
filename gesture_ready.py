import cv2
import mediapipe as mp
import time
import pyrealsense2 as rs
import numpy as np
import math

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.high_level_commander import HighLevelCommander
from cflib.crazyflie.log import LogConfig
from cflib.utils import uri_helper

# ------------------ Config ------------------
URI = uri_helper.uri_from_env(default='radio://0/80/2M')
DEFAULT_HEIGHT = 0.5  # meters
FENCE_LIMIT = 1
SCALE = 0.1
PIXELS_PER_CM = 37.0

# ------------------ RealSense Init ------------------
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
pipeline.start(config)

# ------------------ MediaPipe Init ------------------
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)
mp_draw = mp.solutions.drawing_utils

CAMERA_ORIENTATION = 'landscape'
origin_x, origin_y = None, None
current_x, current_y = 0.0, 0.0

# ----------- Battery voltage monitor ------------
battery_voltage = None
def battery_log_callback(timestamp, data, logconf):
    global battery_voltage
    battery_voltage = data['pm.vbat']

# ----------- Utils ------------
def adjust_coordinates(cx, cy, w, h):
    if CAMERA_ORIENTATION == 'landscape':
        new_cx = cy
        new_cy = w - cx
        return new_cx, new_cy
    else:
        return cx, cy

def hand_tracking_preview():
    global origin_x, origin_y
    print("👉 Detecting hand continuously for 3 seconds to take off. Press 'q' to quit.")
    hand_detected_start = None
    while True:
        frames = pipeline.wait_for_frames()
        color_frame = frames.get_color_frame()
        if not color_frame:
            continue
        frame = np.asanyarray(color_frame.get_data())
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)
        hand_present = False
        if result.multi_hand_landmarks:
            hand_present = True
            for hand_landmarks in result.multi_hand_landmarks:
                palm_indices = [0, 5, 9, 13, 17]
                palm_x = sum(hand_landmarks.landmark[i].x for i in palm_indices) / len(palm_indices)
                palm_y = sum(hand_landmarks.landmark[i].y for i in palm_indices) / len(palm_indices)
                cx_raw = int(palm_x * w)
                cy_raw = int(palm_y * h)
                cx, cy = adjust_coordinates(cx_raw, cy_raw, w, h)
                cv2.circle(frame, (cx_raw, cy_raw), 10, (0, 255, 0), -1)
                mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
        current_time = time.time()
        if hand_present:
            if hand_detected_start is None:
                hand_detected_start = current_time
            elapsed = current_time - hand_detected_start
            countdown = max(0, 3 - int(elapsed))
            cv2.putText(frame, f'Takeoff in {countdown}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            if elapsed >= 3:
                origin_x, origin_y = w // 2, h // 2
                print(f"✅ Origin (center of frame) set at: X={origin_x}, Y={origin_y}")
                return True
        else:
            hand_detected_start = None
            cv2.putText(frame, 'Show your hand to auto takeoff', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow("Drone Hand Control - Preview", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            return False

def is_finger_extended(landmarks, tip, pip, mcp):
    wrist = landmarks.landmark[0]
    tip_dist = math.hypot(landmarks.landmark[tip].x - wrist.x, landmarks.landmark[tip].y - wrist.y)
    pip_dist = math.hypot(landmarks.landmark[pip].x - wrist.x, landmarks.landmark[pip].y - wrist.y)
    mcp_dist = math.hypot(landmarks.landmark[mcp].x - wrist.x, landmarks.landmark[mcp].y - wrist.y)
    return tip_dist > pip_dist and pip_dist > mcp_dist

def angle_between_three_points(a, b, c):
    ab = (a.x - b.x, a.y - b.y)
    cb = (c.x - b.x, c.y - b.y)
    dot = ab[0] * cb[0] + ab[1] * cb[1]
    norm_ab = math.hypot(*ab)
    norm_cb = math.hypot(*cb)
    angle = math.acos(dot / (norm_ab * norm_cb + 1e-7))
    return math.degrees(angle)

def is_l_gesture(hand_landmarks):
    thumb_extended = is_finger_extended(hand_landmarks, 4, 3, 2)
    index_extended = is_finger_extended(hand_landmarks, 8, 7, 5)
    middle_extended = is_finger_extended(hand_landmarks, 12, 11, 9)
    ring_extended = is_finger_extended(hand_landmarks, 16, 15, 13)
    pinky_extended = is_finger_extended(hand_landmarks, 20, 19, 17)
    if thumb_extended and index_extended and not middle_extended and not ring_extended and not pinky_extended:
        wrist = hand_landmarks.landmark[0]
        thumb_tip = hand_landmarks.landmark[4]
        index_tip = hand_landmarks.landmark[8]
        angle = angle_between_three_points(thumb_tip, wrist, index_tip)
        if 60 < angle < 120:
            return True
    return False

def hand_tracking_control(hlc, flight_time=60):
    global origin_x, origin_y, current_x, current_y, battery_voltage
    takeoff_time = time.time()
    flight_timer_enabled = True
    while True:
        frames = pipeline.wait_for_frames()
        color_frame = frames.get_color_frame()
        if not color_frame:
            continue
        frame = np.asanyarray(color_frame.get_data())
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        if origin_x is None or origin_y is None:
            origin_x, origin_y = w // 2, h // 2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        # L-gesture for landing
        if result.multi_hand_landmarks:
            for hand_landmarks in result.multi_hand_landmarks:
                if is_l_gesture(hand_landmarks):
                    print("✋ 'L' gesture detected - returning to launch and landing...")
                    hlc.go_to(0, 0, DEFAULT_HEIGHT, 0.0, 2.0, relative=False)
                    time.sleep(2.0)
                    hlc.land(0.0, 2.0)
                    time.sleep(2.5)
                    return True

        if result.multi_hand_landmarks:
            for hand_landmarks in result.multi_hand_landmarks:
                palm_indices = [0, 5, 9, 13, 17]
                palm_x = sum(hand_landmarks.landmark[i].x for i in palm_indices) / len(palm_indices)
                palm_y = sum(hand_landmarks.landmark[i].y for i in palm_indices) / len(palm_indices)
                cx_raw = int(palm_x * w)
                cy_raw = int(palm_y * h)
                cx, cy = adjust_coordinates(cx_raw, cy_raw, w, h)
                hand_disp = np.array([cx - origin_x, cy - origin_y], dtype=np.float32)
                disp_cm_x = hand_disp[0] / PIXELS_PER_CM
                disp_cm_y = hand_disp[1] / PIXELS_PER_CM
                desired_x = max(min(disp_cm_x * SCALE, FENCE_LIMIT), -FENCE_LIMIT)
                desired_y = max(min(-disp_cm_y * SCALE, FENCE_LIMIT), -FENCE_LIMIT)
                if abs(desired_x - current_x) > 0.02 or abs(desired_y - current_y) > 0.02:
                    hlc.go_to(desired_x, desired_y, DEFAULT_HEIGHT, 0.0, 0.5, relative=False)
                    current_x, current_y = desired_x, desired_y
                    print(f"🎯 Position Target: ({current_x:.2f}, {current_y:.2f}, {DEFAULT_HEIGHT})")
                cv2.circle(frame, (cx_raw, cy_raw), 10, (0, 255, 0), -1)
                mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

        # STATUS and BATTERY overlays
        status_text = f"Flight timer: {'ON' if flight_timer_enabled else 'DISABLED - show L to land'}"
        cv2.putText(frame, status_text, (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        if battery_voltage is not None:
            cv2.putText(frame, f'Battery: {battery_voltage:.2f} V', (10, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

        # Timer
        if flight_timer_enabled:
            time_left = int(max(0, flight_time - (time.time() - takeoff_time)))
            cv2.putText(frame, f'Flight time left: {time_left}s', (10, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
            if time_left <= 0:
                print("⏰ Flight time ended, returning to launch and landing...")
                hlc.go_to(0, 0, DEFAULT_HEIGHT, 0.0, 2.0, relative=False)
                time.sleep(2.0)
                hlc.land(0.0, 2.0)
                time.sleep(2.5)
                return True

        cv2.imshow("Drone Hand Control - Live", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('x') and flight_timer_enabled:
            print("'x' pressed - disabling flight timer, land by showing 'L' gesture")
            flight_timer_enabled = False
    return False

# ---------- Flight time (in seconds) ----------
FLIGHT_TIME = 60

if __name__ == "__main__":
    cflib.crtp.init_drivers()
    hlc = None
    battery_logconf = None
    try:
        takeoff = hand_tracking_preview()
        if not takeoff:
            print("❌ Takeoff aborted.")
            pipeline.stop()
            cv2.destroyAllWindows()
            exit()
        with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
            hlc = HighLevelCommander(scf.cf)
            battery_logconf = LogConfig(name='Battery', period_in_ms=500)
            battery_logconf.add_variable('pm.vbat', 'float')
            scf.cf.log.add_config(battery_logconf)
            battery_logconf.data_received_cb.add_callback(battery_log_callback)
            battery_logconf.start()

            print("🛫 Taking off...")
            hlc.takeoff(DEFAULT_HEIGHT, 2.0)
            time.sleep(2.5)
            landed_inside = hand_tracking_control(hlc, flight_time=FLIGHT_TIME)
            print("🛬 Landing...")
            if not landed_inside:
                hlc.go_to(0, 0, DEFAULT_HEIGHT, 0.0, 2.0, relative=False)
                time.sleep(2.0)
                hlc.land(0.0, 2.0)
                time.sleep(2.5)
    except KeyboardInterrupt:
        print("\n[!] KeyboardInterrupt — landing drone!")
    except Exception as e:
        print(f"\n[!] Exception: {e}\nLanding drone for safety!")
    finally:
        try:
            if battery_logconf is not None:
                battery_logconf.stop()
        except Exception:
            pass
        try:
            if hlc:
                hlc.go_to(0, 0, DEFAULT_HEIGHT, 0.0, 2.0, relative=False)
                time.sleep(2.0)
                hlc.land(0.0, 2.0)
                time.sleep(2.0)
        except Exception:
            pass
        try:
            pipeline.stop()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
