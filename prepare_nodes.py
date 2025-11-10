#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_nodes.py
Prime nodes, play a visible animation, and verify readiness.

- Publishes: game/reset = 'reset'        (optional: --no-reset)
- Publishes: game/prepare = <visual>     (defaults to 'shieldworld')
- Subscribes: game/ready/<node> ('ready')
- Exits 0 when all listed nodes ack; else 1 on timeout.

Examples:
  python prepare_nodes.py
  python prepare_nodes.py --visual huestheboss
  python prepare_nodes.py --visual post          # if firmware supports 'post' -> colorCyclePOST()
  python prepare_nodes.py --nodes node1,node2    # subset
  python prepare_nodes.py --timeout 10
"""

import sys
import time
import argparse
import paho.mqtt.client as mqtt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="192.168.0.18", help="MQTT broker host/IP")
    ap.add_argument("--port", type=int, default=1883, help="MQTT port")
    ap.add_argument("--nodes", default="node1,node2,node3,node4,node5",
                    help="Comma-separated node IDs to check")
    ap.add_argument("--visual", default="shieldworld",
                    help="Value to publish to game/prepare (e.g. shieldworld, huestheboss, droneconfusion, post)")
    ap.add_argument("--timeout", type=float, default=10.0, help="Seconds to wait for all readies")
    ap.add_argument("--no-reset", action="store_true", help="Do not send game/reset before prepare")
    ap.add_argument("--no-prepare", action="store_true", help="Do not send game/prepare visual")
    args = ap.parse_args()

    nodes = [n.strip() for n in args.nodes.split(",") if n.strip()]
    ready_topics = [f"game/ready/{n}" for n in nodes]
    RESET_TOPIC = "game/reset"
    PREPARE_TOPIC = "game/prepare"

    seen = set()

    def on_connect(cli, u, f, rc):
        if rc != 0:
            print(f"[prep] MQTT connect failed rc={rc}")
            sys.exit(1)
        for t in ready_topics:
            cli.subscribe(t, qos=1)
        # 1) reset (clean state)
        if not args.no_reset:
            cli.publish(RESET_TOPIC, "reset", qos=0, retain=False)
            print("[prep] sent: game/reset=reset")
            # brief grace so nodes finish reset handlers before visual
            time.sleep(0.2)
        # 2) visual prepare (blink/animation you can see)
        if not args.no_prepare:
            cli.publish(PREPARE_TOPIC, args.visual, qos=0, retain=False)
            print(f"[prep] sent: game/prepare={args.visual}")
        print("[prep] waiting for ready acks…")

    def on_message(cli, u, msg):
        payload = msg.payload.decode().strip().lower()
        if payload != "ready":
            return
        nid = msg.topic.split("/")[-1]
        if nid not in seen:
            print(f"[prep] {nid} READY ✅")
        seen.add(nid)

    client = mqtt.Client(client_id=f"nodes_preparer_{int(time.time())}", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.broker, args.port, keepalive=60)
    except Exception as e:
        print(f"[prep] connect error: {e}")
        sys.exit(1)

    client.loop_start()
    start = time.time()
    try:
        while time.time() - start < args.timeout:
            if len(seen) == len(nodes):
                print("[prep] ALL nodes ready ✅")
                client.loop_stop()
                sys.exit(0)
            time.sleep(0.05)
    finally:
        client.loop_stop()

    missing = [n for n in nodes if n not in seen]
    print(f"[prep] timeout. Missing: {missing} ❌")
    sys.exit(1)

if __name__ == "__main__":
    main()
