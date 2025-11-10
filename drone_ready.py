#!/usr/bin/env python3
import os
import sys
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.log import LogConfig


# === Config (env-overridable) ===
URI = os.environ.get('CF_URI', 'radio://0/80/2M/E7E7E7E7E7')
POS_TIMEOUT_S = float(os.environ.get('POS_TIMEOUT_S', '10'))  # seconds


received_position = False
var_names_in_use = ("", "", "")


def position_callback(timestamp, data, logconf):
    """Called for each log packet; sets global flag when we get a valid pose."""
    global received_position
    try:
        # Read using the names we chose (stateEstimate.* or kalman.state*)
        x_name, y_name, z_name = var_names_in_use
        x = float(data.get(x_name, 0.0))
        y = float(data.get(y_name, 0.0))
        z = float(data.get(z_name, 0.0))
        print(f"[pos] x={x:.2f}, y={y:.2f}, z={z:.2f}")
        received_position = True
    except Exception as e:
        # Keep calm—just don't flip the flag on parse errors
        print(f"[warn] position_callback parse issue: {e}")


def _discover_pose_vars(log_toc_names):
    """
    Given a set of 'group.name' strings in the Log TOC, pick the 3 pose vars to use.
    Prefer stateEstimate.{x,y,z}, else fall back to kalman.stateX/Y/Z.
    Return a tuple of (x_name, y_name, z_name) or None if neither set is present.
    """
    prefer = ('stateEstimate.x', 'stateEstimate.y', 'stateEstimate.z')
    fallback = ('kalman.stateX', 'kalman.stateY', 'kalman.stateZ')

    if all(n in log_toc_names for n in prefer):
        return prefer
    if all(n in log_toc_names for n in fallback):
        return fallback

    # Partial presence? give up; we require a complete triplet
    return None


def wait_for_position(uri: str, timeout_s: float = POS_TIMEOUT_S) -> bool:
    """
    Connect to Crazyflie, subscribe to pose logs, and wait up to timeout_s for a packet.
    Returns True if a pose packet arrives; False otherwise.
    """
    global received_position, var_names_in_use
    received_position = False
    var_names_in_use = ("", "", "")

    # Init radio drivers (Crazyradio PA)
    cflib.crtp.init_drivers()

    # Connect and configure
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        print(f"[link] Connected to {uri}")

        # Make sure the estimator is Kalman so pose vars actually update
        try:
            scf.cf.param.set_value('stabilizer.estimator', '2')
        except Exception as e:
            print(f"[warn] couldn't set stabilizer.estimator to 2 (Kalman): {e}")

        # Build a set of all available 'group.name' log variables from the TOC
        names = set()
        try:
            # scf.cf.log.toc.toc is a dict: {group: {name: LogVariable}}
            toc = scf.cf.log.toc.toc
            for grp, vars_ in toc.items():
                for nm in vars_.keys():
                    names.add(f"{grp}.{nm}")
        except Exception as e:
            print(f"[warn] couldn't read Log TOC: {e}")

        pose_vars = _discover_pose_vars(names)
        if not pose_vars:
            print("[-] No known pose variables found in firmware (missing stateEstimate.* and kalman.state*).")
            print("    Check firmware build / estimator / deck / geometry.")
            return False

        var_names_in_use = pose_vars
        print(f"[info] Using pose vars: {pose_vars[0]}, {pose_vars[1]}, {pose_vars[2]}")

        # Set up log block
        log_conf = LogConfig(name='Position', period_in_ms=100)
        for full in pose_vars:
            # full is like 'stateEstimate.x' or 'kalman.stateX'
            log_conf.add_variable(full, 'float')

        # Add + start the log config
        scf.cf.log.add_config(log_conf)
        log_conf.data_received_cb.add_callback(position_callback)

        try:
            log_conf.start()
        except Exception as e:
            print(f"[-] Failed to start log block for pose: {e}")
            return False

        # Wait for a packet or timeout
        t0 = time.time()
        while not received_position and (time.time() - t0) < timeout_s:
            time.sleep(0.1)

        # Always stop the log block
        try:
            log_conf.stop()
        except Exception:
            pass

    return received_position


def main() -> int:
    ok = wait_for_position(URI, POS_TIMEOUT_S)
    if ok:
        print("[OK] Received position within timeout.")
        return 0
    else:
        print("[FAIL] Did not receive position data in time.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
