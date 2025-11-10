#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_car.py
Checks readiness of your RC car (CAR_ID='car1') on your MQTT broker.

- Subscribes to:   game/ready/car1
- Publishes once:  game/reset = 'reset'   (prompts car to re-announce ready)
- Waits up to TIMEOUT seconds for payload 'ready'
- Exits code 0 (ready) or 1 (not ready)

Note: 'game/reset' is a global topic in your setup; other nodes may also reset and
publish their own ready acks to their own topics. This script listens ONLY to car1.
"""

import sys
import time
import paho.mqtt.client as mqtt

# === Broker & Device (from your car code) ===
BROKER = "192.168.0.18"
PORT = 1883
CAR_ID = "car1"

READY_TOPIC = f"game/ready/{CAR_ID}"   # from your sketch
RESET_TOPIC = "game/reset"             # from your sketch

TIMEOUT = 10.0      # seconds to wait for ready
SEND_RESET = True  # set False if you just want to listen

def main():
    got_ready = {"ok": False}

    def on_connect(cli, u, f, rc):
        if rc != 0:
            print(f"[prepare_car] MQTT connect failed (rc={rc})")
            sys.exit(1)
        print(f"[prepare_car] Connected to {BROKER}:{PORT} (rc={rc})")
        cli.subscribe(READY_TOPIC, qos=1)
        print(f"[prepare_car] Subscribed: {READY_TOPIC}")
        if SEND_RESET:
            cli.publish(RESET_TOPIC, "reset", qos=0, retain=False)
            print(f"[prepare_car] Sent reset on {RESET_TOPIC}")

    def on_message(cli, u, msg):
        if msg.topic != READY_TOPIC:
            return
        payload = msg.payload.decode().strip().lower()
        print(f"[prepare_car] {msg.topic} = {payload}")
        if payload == "ready":
            got_ready["ok"] = True

    client = mqtt.Client(client_id=f"prepare_car_{int(time.time())}", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, keepalive=30)
    except Exception as e:
        print(f"[prepare_car] ERROR connecting to broker: {e}")
        sys.exit(1)

    client.loop_start()
    start = time.time()
    try:
        while time.time() - start < TIMEOUT:
            if got_ready["ok"]:
                print("[prepare_car] Car is READY ✅")
                client.loop_stop()
                sys.exit(0)
            time.sleep(0.05)
    finally:
        client.loop_stop()

    print("[prepare_car] Timeout: did not see 'ready' from car1 ⚠️")
    print("Hints:")
    print(" • Ensure the car is powered, on Wi-Fi, and connected to MQTT")
    print(" • This script resets ALL devices listening to 'game/reset'")
    sys.exit(1)

if __name__ == "__main__":
    main()
