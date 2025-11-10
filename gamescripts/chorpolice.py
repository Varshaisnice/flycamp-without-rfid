#!/usr/bin/env python3
"""
rpi_pololu_bridge.py

Simple Raspberry Pi MQTT client to control the ESP M3 you flashed with the sketch
you provided. Publishes to:
 - pololu/initialise
 - pololu/start
 - pololu/stop

And subscribes to:
 - pololu/duration

Usage:
  Interactive:
    python3 rpi_pololu_bridge.py --broker 192.168.0.18

  Single-shot send:
    python3 rpi_pololu_bridge.py --broker 192.168.0.18 --send start

Defaults:
  broker: 192.168.0.18
  port: 1883
"""
import argparse
import time
import sys
import threading
import paho.mqtt.client as mqtt

DEFAULT_BROKER = "192.168.0.18"
DEFAULT_PORT = 1883

TOPIC_INITIALISE = "pololu/initialise"
TOPIC_START      = "pololu/start"
TOPIC_STOP       = "pololu/stop"
TOPIC_DURATION   = "pololu/duration"

COMMAND_TOPICS = {
    "initialise": TOPIC_INITIALISE,
    "start":      TOPIC_START,
    "stop":       TOPIC_STOP
}

connected_flag = threading.Event()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker.")
        # subscribe to duration topic to receive lines from the ESP (Pololu -> ESP -> MQTT)
        client.subscribe(TOPIC_DURATION)
        print("Subscribed to:", TOPIC_DURATION)
        connected_flag.set()
    else:
        print("Failed to connect, return code:", rc)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8', errors='replace')
    except Exception:
        payload = "<non-decodable payload>"
    print("\nMQTT message received:")
    print("  topic:", msg.topic)
    print("  payload:", payload)
    # Re-print prompt marker if interactive
    if userdata.get("interactive"):
        print("> ", end="", flush=True)

def on_disconnect(client, userdata, rc):
    print("Disconnected from broker (rc={})".format(rc))
    connected_flag.clear()

def send_command(client, cmd_name):
    cmd_name = cmd_name.lower()
    if cmd_name not in COMMAND_TOPICS:
        print("Unknown command:", cmd_name)
        return False
    topic = COMMAND_TOPICS[cmd_name]
    # Payload is not used by your ESP code; topic is enough. We'll send a short payload for clarity.
    payload = cmd_name.upper()
    result = client.publish(topic, payload)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("Published '{}' -> {}".format(payload, topic))
        return True
    else:
        print("Publish failed (rc={})".format(result.rc))
        return False

def interactive_loop(client):
    print("Interactive mode. Type one of: initialise, start, stop, exit")
    try:
        while True:
            cmd = input("> ").strip()
            if not cmd:
                continue
            if cmd.lower() in ("exit", "quit", "q"):
                print("Exiting interactive mode.")
                break
            send_command(client, cmd)
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted, exiting.")

def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi MQTT bridge for ESP M3 / Pololu")
    parser.add_argument("--broker", "-b", default=DEFAULT_BROKER, help="MQTT broker address (default {})".format(DEFAULT_BROKER))
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_PORT, help="MQTT broker port (default 1883)")
    parser.add_argument("--send", "-s", help="Send a single command and exit (initialise|start|stop)")
    parser.add_argument("--clientid", default="rpi_pololu_bridge", help="MQTT client id")
    args = parser.parse_args()

    client = mqtt.Client(client_id=args.clientid, userdata={"interactive": bool(not args.send)})
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    try:
        client.connect(args.broker, args.port, keepalive=60)
    except Exception as e:
        print("Unable to connect to broker {}:{} -> {}".format(args.broker, args.port, e))
        sys.exit(1)

    # Start network loop in background thread
    client.loop_start()

    # Wait for connection (timeout)
    if not connected_flag.wait(timeout=5):
        print("Warning: not connected to broker after 5s. Continuing anyway; client will retry in background.")

    if args.send:
        cmd = args.send.lower()
        if send_command(client, cmd):
            # give the broker a moment to send message
            time.sleep(0.2)
        # Stop loop and exit
        client.loop_stop()
        client.disconnect()
        return

    # interactive mode: show any incoming duration messages and allow sending commands
    interactive_loop(client)

    # clean shutdown
    print("Shutting down MQTT client...")
    client.loop_stop()
    client.disconnect()
    time.sleep(0.1)

if __name__ == "__main__":
    main()
