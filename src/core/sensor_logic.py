import time
from typing import Optional

# --- Hardware Libraries ---
try:
    import RPi.GPIO as GPIO
except ImportError:

    class MockGPIO:
        BOARD, BCM, IN, OUT, LOW, HIGH = 1, 2, 3, 4, 0, 1
        PUD_DOWN, PUD_UP = 5, 6

        def setmode(self, mode):
            print(f"Mock GPIO: Set mode {mode}")

        def setup(self, pin, mode, initial=None, pull_up_down=None):
            print(f"Mock GPIO: Setup pin {pin} as {mode}")

        def output(self, pin, value):
            print(f"Mock GPIO: Pin {pin} → {'HIGH' if value else 'LOW'}")

        def input(self, pin):
            return 0

        def cleanup(self):
            print("Mock GPIO: Cleanup")

        def setwarnings(self, flag):
            print(f"Mock GPIO: Warnings {flag}")

    GPIO = MockGPIO()

try:
    import adafruit_dht
    import board
except ImportError:
    print("Warning: adafruit_dht or board not found. DHT reading skipped.")
    adafruit_dht = None
    board = None

# --- PubNub Client Import ---
try:
    from pubnub_client import publish_data, subscribe_to_updates
except ImportError:
    print("Warning: PubNub client missing (mock mode enabled)")

    def publish_data(data):
        print(f"[PubNub Mock] Would publish: {data}")

    def subscribe_to_updates(cb):
        print("[PubNub Mock] No real listener added")


# --- PIN CONFIGURATION ---
class PinConfig:
    PIR_PIN = 6
    DHT_PIN = 4
    BUZZER_PIN = 27
    LED_PIN = 22
    FAN_PIN = 17


# --- AUTO MODE SETTINGS ---
AUTO_MODE = True
AUTO_THRESHOLD = 24  # Fan ON at >= 24°C
LAST_MANUAL = 0  # Time manual button pressed
MANUAL_TIMEOUT = 10  # Auto mode resumes after 10 sec


# -----------------------
# SENSOR MONITOR CLASS
# -----------------------
class SmartHomeMonitor:

    def __init__(self):
        self._gpio = GPIO
        self.dht_device = None

        self._gpio.setwarnings(False)
        self._setup_gpio()
        self._setup_dht()

        print("[Monitor] Components initialized.")

    # GPIO Setup
    def _setup_gpio(self):
        try:
            self._gpio.cleanup()
        except:
            pass

        self._gpio.setmode(self._gpio.BCM)

        self._gpio.setup(
            PinConfig.PIR_PIN, self._gpio.IN, pull_up_down=self._gpio.PUD_DOWN
        )
        self._gpio.setup(PinConfig.BUZZER_PIN, self._gpio.OUT, initial=self._gpio.LOW)
        self._gpio.setup(PinConfig.LED_PIN, self._gpio.OUT, initial=self._gpio.LOW)
        self._gpio.setup(PinConfig.FAN_PIN, self._gpio.OUT, initial=self._gpio.LOW)

        print("[Monitor] GPIO configured.")

    # DHT Setup
    def _setup_dht(self):
        if adafruit_dht and board:
            try:
                self.dht_device = adafruit_dht.DHT22(board.D4)
                print("[Monitor] DHT22 initialized.")
            except:
                print("[Monitor] DHT22 failed.")
                self.dht_device = None

    # CMD Handler for PubNub
    def handle_command(self, msg: dict):
        global AUTO_MODE, LAST_MANUAL

        cmd = msg.get("cmd")
        print(f"[Pi] CMD Received → {cmd}")

        # turns off auto mode temporarily
        if cmd in ["fan_on", "Fan On"]:
            GPIO.output(PinConfig.FAN_PIN, GPIO.HIGH)
            print("[MANUAL] Fan ON")
            LAST_MANUAL = time.time()
            AUTO_MODE = False

        elif cmd in ["fan_off", "Fan Off"]:
            GPIO.output(PinConfig.FAN_PIN, GPIO.LOW)
            print("[MANUAL] Fan OFF")
            LAST_MANUAL = time.time()
            AUTO_MODE = False

        elif cmd == "buzzer_on":
            GPIO.output(PinConfig.BUZZER_PIN, GPIO.HIGH)
            print("[MANUAL] Buzzer ON")

        elif cmd == "buzzer_off":
            GPIO.output(PinConfig.BUZZER_PIN, GPIO.LOW)
            print("[MANUAL] Buzzer OFF")

        elif cmd == "auto_on":
            AUTO_MODE = True
            print("[Pi] AUTO MODE ENABLED")

        elif cmd == "auto_off":
            AUTO_MODE = False
            print("[Pi] AUTO MODE DISABLED")

        else:
            print("[Pi] Unknown command")

    # AUTO FAN LOGIC
    def auto_fan(self, temp_c):
        if temp_c is None:
            return

        if temp_c >= AUTO_THRESHOLD:
            GPIO.output(PinConfig.FAN_PIN, GPIO.HIGH)
            print(f"[AUTO] Temp {temp_c}°C → FAN ON")
        else:
            GPIO.output(PinConfig.FAN_PIN, GPIO.LOW)
            print(f"[AUTO] Temp {temp_c}°C → FAN OFF")

    # MAIN LOOP
    def run(self):
        print("[Pi] Starting Smart Home Monitor...")
        subscribe_to_updates(self.handle_command)

        last_motion = GPIO.LOW
        last_motion_time = 0

        while True:
            ts = int(time.time())
            temp_c = None

            # Read DHT22
            if self.dht_device:
                try:
                    temp_c = self.dht_device.temperature
                    humidity = self.dht_device.humidity

                    if temp_c is not None:
                        publish_data(
                            {
                                "event": "dht22_reading",
                                "device_uid": "dht22_sensor_01",
                                "temperature_c": round(float(temp_c), 2),
                                "humidity": round(float(humidity), 2),
                                "at": ts,
                            }
                        )

                except Exception as e:
                    print(f"[DHT22] Error: {e}")

            # PIR Motion
            current_motion = GPIO.input(PinConfig.PIR_PIN)
            motion_detected = current_motion == GPIO.HIGH

            if motion_detected and last_motion == GPIO.LOW:
                print("[PIR] MOTION DETECTED")
                publish_data(
                    {
                        "event": "motion",
                        "device_uid": "pir_sensor_01",
                        "occupied": 1,
                        "at": ts,
                    }
                )
                GPIO.output(PinConfig.LED_PIN, GPIO.HIGH)
                GPIO.output(PinConfig.BUZZER_PIN, GPIO.HIGH)
                time.sleep(0.3)
                GPIO.output(PinConfig.BUZZER_PIN, GPIO.LOW)

            elif not motion_detected and last_motion == GPIO.HIGH:
                if ts - last_motion_time >= 2:
                    print("[PIR] Motion stopped")
                    publish_data(
                        {
                            "event": "motion",
                            "device_uid": "pir_sensor_01",
                            "occupied": 0,
                            "at": ts,
                        }
                    )
                GPIO.output(PinConfig.LED_PIN, GPIO.LOW)

            last_motion = current_motion

            # FAN AUTO MODE with MANUAL TIMEOUT
            global AUTO_MODE
            if time.time() - LAST_MANUAL > MANUAL_TIMEOUT:
                AUTO_MODE = True

            if AUTO_MODE:
                self.auto_fan(temp_c)

            time.sleep(2)


# Run Monitor
if __name__ == "__main__":
    monitor = SmartHomeMonitor()
    monitor.run()
