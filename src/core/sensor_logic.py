import time
from typing import Optional
from hardware_controller import hardware_controller

# --- Hardware Libraries ---
try:
    import RPi.GPIO as GPIO
except ImportError:
    class MockGPIO:
        BOARD, BCM, IN, OUT, LOW, HIGH = 1, 2, 3, 4, 0, 1
        PUD_DOWN, PUD_UP = 5, 6

        def setmode(self, mode): print(f"Mock GPIO: Set mode {mode}")

        def setup(self, pin, mode, initial=None, pull_up_down=None):
            print(f"Mock GPIO: Setup pin {pin} as {mode}")

        def output(self, pin, value): print(f"Mock GPIO: Pin {pin} → {'HIGH' if value else 'LOW'}")

        def input(self, pin): return 0

        def cleanup(self): print("Mock GPIO: Cleanup")

        def setwarnings(self, flag): print(f"Mock GPIO: Warnings {flag}")


    GPIO = MockGPIO()

try:
    import adafruit_dht
    import board
except ImportError:
    print("Warning: adafruit_dht or board not found. DHT reading will be skipped.")
    adafruit_dht = None
    board = None

# --- PubNub Client Import ---
try:
    from pubnub_client import publish_data
except ImportError:
    print("Warning: Could not import pubnub_client. Using fallback.")


    def publish_data(payload):
        print(f"[PubNub Fallback] Would publish: {payload}")


# --- PIN CONFIGURATION (BCM numbering) ---
class PinConfig:
    # Inputs
    PIR_PIN = 6  # BCM 6  (BOARD 31)
    DHT_PIN = 4  # BCM 4  (BOARD 7)

    # Outputs
    BUZZER_PIN = 27  # BCM 27 (BOARD 13)
    LED_PIN = 22  # BCM 22 (BOARD 15)
    FAN_PIN = 14  # BCM 14 (BOARD 8)


# --- LOGIC THRESHOLDS ---
READ_INTERVAL_SECONDS = 2.0
TEMP_THRESHOLD_C = 20.0
MOTION_COOLDOWN = 2.0
BUZZER_DURATION = 0.8


class SmartHomeMonitor:
    """
    Monitors PIR and DHT22, controls LED, Buzzer, and Fan.
    """

    def __init__(self):
        self._gpio = GPIO
        self.dht_device = None

        self._gpio.setwarnings(False)

        if self._gpio.__class__.__name__ == 'MockGPIO':
            print(" Running in Mock Mode (No physical GPIO control)")

        self._setup_dht()
        self._setup_gpio()
        print("[Monitor] All components initialized")

    def _setup_dht(self):
        """Initialize DHT22 sensor."""
        if adafruit_dht and board:
            try:
                self.dht_device = adafruit_dht.DHT22(board.D4)
                print(f"[Monitor] DHT22 sensor initialized on BCM 4")
            except Exception as e:
                print(f"[Monitor] Error initializing DHT22: {e}")
                self.dht_device = None
        else:
            print("[Monitor] DHT22 libraries not available")

    def _setup_gpio(self):
        """Configure GPIO pins for all components."""
        try:
            self._gpio.cleanup()
        except Exception:
            pass

        self._gpio.setmode(self._gpio.BCM)

        # Inputs
        self._gpio.setup(PinConfig.PIR_PIN, self._gpio.IN, pull_up_down=self._gpio.PUD_DOWN)

        # Outputs
        self._gpio.setup(PinConfig.BUZZER_PIN, self._gpio.OUT, initial=self._gpio.LOW)
        self._gpio.setup(PinConfig.LED_PIN, self._gpio.OUT, initial=self._gpio.LOW)
        self._gpio.setup(PinConfig.FAN_PIN, self._gpio.OUT, initial=self._gpio.LOW)

        print(f"[Monitor] GPIO configured (BCM mode) - PIR:{PinConfig.PIR_PIN}, "
              f"Buzzer:{PinConfig.BUZZER_PIN}, LED:{PinConfig.LED_PIN}, Fan:{PinConfig.FAN_PIN}")

    def _beep_buzzer(self, duration=BUZZER_DURATION):
        """Activate buzzer for specified duration."""
        self._gpio.output(PinConfig.BUZZER_PIN, self._gpio.HIGH)
        time.sleep(duration)
        self._gpio.output(PinConfig.BUZZER_PIN, self._gpio.LOW)

    def _control_actuators(self, temp_c: Optional[float], motion_detected: bool):
        """Control actuators based on sensor readings."""

        # Motion - control LED and buzzer
        if motion_detected:
            self._gpio.output(PinConfig.LED_PIN, self._gpio.HIGH)
            hardware_controller.buzzer_beep()  # Use hardware controller for buzzer
            print("  [Actuator] Motion detected: LED ON, Buzzer beeped")
        else:
            self._gpio.output(PinConfig.LED_PIN, self._gpio.LOW)

        # Temperature/Fan - use hardware controller
        if temp_c is not None:
            hardware_controller.control_fan_based_on_temp(temp_c)

    def run(self):
        """Main monitoring loop."""
        print("\n--- Starting Unified Smart Home Monitor ---")
        print(f"Temperature threshold: {TEMP_THRESHOLD_C}°C")
        print(f"Motion cooldown: {MOTION_COOLDOWN}s")
        print(f"Read interval: {READ_INTERVAL_SECONDS}s")

        last_motion_state = self._gpio.LOW
        last_motion_time = 0
        motion_detected = False

        try:
            while True:
                ts = int(time.time())
                temp_c, humidity = None, None

                # Read DHT22
                if self.dht_device:
                    try:
                        temp_c = self.dht_device.temperature
                        humidity = self.dht_device.humidity

                        if temp_c is not None and humidity is not None:
                            print(f"[DHT22] Temp: {temp_c:5.1f}°C | Humidity: {humidity:3.1f}%")
                            publish_data({
                                "event": "dht22_reading",
                                "device_uid": "dht22_sensor_01",
                                "temperature_c": round(float(temp_c), 2),
                                "humidity": round(float(humidity), 2),
                                "at": ts
                            })
                        else:
                            print("[DHT22] Sensor read returned None")

                    except RuntimeError as err:
                        print(f"[DHT22] Read Error: {err}")
                    except Exception as e:
                        print(f"[DHT22] Unexpected Error: {e}")

                # PIR
                current_pir_state = self._gpio.input(PinConfig.PIR_PIN)
                motion_detected = False

                print(
                    f"[PIR] Current state: {'HIGH' if current_pir_state else 'LOW'}, Last state: {'HIGH' if last_motion_state else 'LOW'}")

                # Motion start
                if current_pir_state == self._gpio.HIGH and last_motion_state == self._gpio.LOW:
                    print("[PIR] MOTION DETECTED!")
                    motion_detected = True
                    last_motion_state = self._gpio.HIGH
                    last_motion_time = ts
                    publish_data({
                        "event": "motion",
                        "device_uid": "pir_sensor_01",
                        "occupied": 1,
                        "at": ts
                    })

                # Motion stop
                elif current_pir_state == self._gpio.LOW and last_motion_state == self._gpio.HIGH:
                    if ts - last_motion_time >= MOTION_COOLDOWN:
                        print("[PIR] No motion")
                        last_motion_state = self._gpio.LOW
                        publish_data({
                            "event": "motion",
                            "device_uid": "pir_sensor_01",
                            "occupied": 0,
                            "at": ts
                        })

                # Control actuators
                self._control_actuators(temp_c, motion_detected)

                time.sleep(READ_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n Stopping monitor service...")

        except Exception as e:
            print(f"\n[Monitor] Fatal error: {e}")

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up GPIO and DHT resources."""
        print("\n[Monitor] Cleaning up resources...")

        if self._gpio:
            self._gpio.output(PinConfig.BUZZER_PIN, self._gpio.LOW)
            self._gpio.output(PinConfig.LED_PIN, self._gpio.LOW)
            self._gpio.output(PinConfig.FAN_PIN, self._gpio.LOW)
            self._gpio.cleanup()
            print("[Monitor] GPIO cleaned up")

        if self.dht_device:
            self.dht_device.exit()
            print("[Monitor] DHT device exited")


if __name__ == "__main__":
    monitor = SmartHomeMonitor()
    monitor.run()
