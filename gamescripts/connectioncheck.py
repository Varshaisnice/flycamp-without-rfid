import time
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.log import LogConfig

# URI for the Crazyflie with your radio channel and address
URI = 'radio://0/80/2M/E7E7E7E7E7'

received_position = False

def position_callback(timestamp, data, logconf):
    global received_position
    x = round(data['kalman.stateX'], 2)
    y = round(data['kalman.stateY'], 2)
    z = round(data['kalman.stateZ'], 2)
    print(f"Received position: x={x}, y={y}, z={z}")
    received_position = True


def wait_for_position(uri):
    global received_position
    received_position = False

    cflib.crtp.init_drivers()

    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        print("Connected to Crazyflie, setting up logger...")
        # Setup position log (Lighthouse uses state estimator)
        log_conf = LogConfig(name='Position', period_in_ms=100)
        log_conf.add_variable('kalman.stateX', 'float')
        log_conf.add_variable('kalman.stateY', 'float')
        log_conf.add_variable('kalman.stateZ', 'float')
        scf.cf.log.add_config(log_conf)
        log_conf.data_received_cb.add_callback(position_callback)
        log_conf.start()

        t0 = time.time()
        timeout = 5  # seconds, adjust as needed

        while not received_position and (time.time() - t0) < timeout:
            time.sleep(0.1)

        log_conf.stop()

    return received_position

def main():
    if wait_for_position(URI):
        print("Successfully received Lighthouse xyz position!")
        return True
    else:
        print("Did not receive position data in time.")
        return False

if __name__ == '__main__':
    print(main())
