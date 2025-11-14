import time
import os
from typing import Optional

# --- Hardware Libraries ---
try:
    # Attempt to import RPi.GPIO for actuator control
    import RPi.GPIO as GPIO
except ImportError:
    # Mock GPIO for non-Pi environments to allow testing logic
    class MockGPIO:
        BOARD, BCM, IN, OUT, LOW, HIGH = 1, 2, 3, 4, 0, 1

        def setmode(self, mode): print("Mock GPIO: Set mode")

        def setup(self, pin, mode, initial=None): print(f"Mock GPIO: Setup pin {pin}")

        def output(self, pin, value): print(f"Mock GPIO: Pin {pin} {'HIGH (ON)' if value else 'LOW (OFF)'}")

        def input(self, pin): return 0  # Mock no motion

        def cleanup(self): print("Mock GPIO: Cleanup")


    GPIO = MockGPIO()

try:
    # Library for DHT22
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
    print("FATAL ERROR: Could not import pubnub_client. Ensure pubnub_client.py is available.")


    # Define a safe fallback if import fails
    def publish_data(payload):
        print(f"[PubNub Fallback] Failed to publish: {payload}")

# --- DHT PIN RESOLUTION FIX ---
# Resolve the DHT pin outside the class to prevent AttributeError if 'board' is None.
# If 'board' is available, use the D4 object. Otherwise, set it to None
if board is not None:
    DHT_PIN_RESOLVED = board.D4
else:
    # Use None if the 'board' module failed to load.
    DHT_PIN_RESOLVED = None


# --- CONFIGURATION ---
class PinConfig:
    """Defines the BOARD pin numbers for all components."""
    # Sensors (Inputs)
    PIR_PIN = 11  # BOARD pin 11 (GPIO 17) for PIR motion sensor
    # FIX: Use the resolved variable to avoid the 'NoneType' error during class definition
    DHT_DATA_PIN = DHT_PIN_RESOLVED  # BCM 4 (BOARD pin 7) for DHT22 data pin

    # Actuators (Outputs) - **Conflict Resolved**
    BUZZER_PIN = 13  # BOARD pin 13 (GPIO 27) - Used for motion alert
    LED_PIN = 15  # BOARD pin 15 (GPIO 22) - Used for motion alert
    FAN_PIN = 8  # BOARD pin 8 (GPIO 14)  - Used for cooling


# --- LOGIC THRESHOLDS ---
READ_INTERVAL_SECONDS = 1.0  # Main loop delay
TEMP_THRESHOLD_C = 26.0  # Temperature above which the fan turns on
MOTION_COOLDOWN = 2.0  # Time to wait after detecting motion to prevent re-triggering


class SmartHomeMonitor:
    """
    Monitors PIR and DHT22, and controls LED, Buzzer, and Fan.
    """

    def __init__(self):
        self._gpio = GPIO
        self.dht_device = None

        if self._gpio.__class__.__name__ == 'MockGPIO':
            print("⚠️ Running in Mock Mode (No physical GPIO control or PIR input)")

        self._setup_dht()
        self._setup_gpio()

    def _setup_dht(self):
        """Initializes the DHT22 device."""
        if adafruit_dht and PinConfig.DHT_DATA_PIN:
            try:
                self.dht_device = adafruit_dht.DHT22(PinConfig.DHT_DATA_PIN)
                print(f"[Monitor] DHT22 sensor initialized on pin {PinConfig.DHT_DATA_PIN}.")
            except Exception as e:
                print(f"[Monitor] Error initializing DHT22: {e}. DHT monitoring disabled.")
                self.dht_device = None

    def _setup_gpio(self) -> None:
        """Configure GPIO in BOARD mode and set pin directions for all components."""
        self._gpio.setmode(self._gpio.BOARD)

        # Inputs
        self._gpio.setup(PinConfig.PIR_PIN, self._gpio.IN)

        # Outputs
        self._gpio.setup(PinConfig.BUZZER_PIN, self._gpio.OUT, initial=self._gpio.LOW)
        self._gpio.setup(PinConfig.LED_PIN, self._gpio.OUT, initial=self._gpio.LOW)
        self._gpio.setup(PinConfig.FAN_PIN, self._gpio.OUT, initial=self._gpio.LOW)

        print(
            f"[Monitor] GPIO Ready. PIR={PinConfig.PIR_PIN}, BUZZER={PinConfig.BUZZER_PIN}, LED={PinConfig.LED_PIN}, FAN={PinConfig.FAN_PIN}"
        )

    def _control_actuators(self, temp_c: Optional[float], motion_detected: bool) -> None:
        """Applies control logic based on sensor data."""

        # 1. PIR/Motion Logic (Buzzer & LED)
        if motion_detected:
            self._gpio.output(PinConfig.BUZZER_PIN, self._gpio.HIGH)
            self._gpio.output(PinConfig.LED_PIN, self._gpio.HIGH)
            print("  [Actuator] Motion: LED/Buzzer ON.")
        else:
            self._gpio.output(PinConfig.BUZZER_PIN, self._gpio.LOW)
            self._gpio.output(PinConfig.LED_PIN, self._gpio.LOW)
            # print("  [Actuator] Motion: LED/Buzzer OFF.")

        # 2. DHT22/Temperature Logic (Fan)
        if temp_c is not None:
            if temp_c > TEMP_THRESHOLD_C:
                self._gpio.output(PinConfig.FAN_PIN, self._gpio.HIGH)
                print(f"  [Actuator] Temp {temp_c:.1f}C > {TEMP_THRESHOLD_C}C: Fan ON.")
            else:
                self._gpio.output(PinConfig.FAN_PIN, self._gpio.LOW)
                print(f"  [Actuator] Temp {temp_c:.1f}C <= {TEMP_THRESHOLD_C}C: Fan OFF.")

    def run(self) -> None:
        """Main monitoring loop."""
        print("\n--- Starting Unified Smart Home Monitor ---")
        last_motion_state = 0
        last_motion_time = 0

        try:
            while True:
                ts = int(time.time())
                temp_c, humidity = None, None

                # --- A. Read DHT22 Sensor ---
                if self.dht_device:
                    try:
                        temp_c = self.dht_device.temperature
                        humidity = self.dht_device.humidity

                        if temp_c is not None and humidity is not None:
                            # Log and publish DHT data
                            print(f"[DHT22] Temp: {temp_c:5.1f}C | Humidity: {humidity:3.1f}%")
                            publish_data({
                                "event": "dht22_reading",
                                "temperature_c": round(float(temp_c), 2),
                                "humidity": round(float(humidity), 2),
                                "at": ts
                            })
                        else:
                            # Don't consider a read failure a critical error, just skip this cycle
                            print("[DHT22] Sensor read failed (returned None).")

                    except RuntimeError as err:
                        print(f"[DHT22] Sensor Read Error: {err.args[0]}")
                        # Clean up the DHT device on hard errors
                        self.dht_device.exit()
                        self.dht_device = None
                    except Exception as e:
                        print(f"[DHT22] Unexpected Error: {e}")

                # --- B. Read PIR Sensor ---
                current_pir_state = self._gpio.input(PinConfig.PIR_PIN)
                motion_detected = False

                if current_pir_state == self._gpio.HIGH and last_motion_state == self._gpio.LOW:
                    # Motion detected (rising edge)
                    print("[PIR] MOTION DETECTED!")
                    motion_detected = True
                    last_motion_state = self._gpio.HIGH
                    last_motion_time = ts
                    publish_data({"event": "motion", "occupied": 1, "at": ts})

                elif current_pir_state == self._gpio.LOW and last_motion_state == self._gpio.HIGH:
                    # Motion stopped (falling edge)
                    if ts - last_motion_time > MOTION_COOLDOWN:
                        print("[PIR] No motion detected.")
                        last_motion_state = self._gpio.LOW
                        publish_data({"event": "motion", "occupied": 0, "at": ts})
                    # If motion just stopped, keep the state HIGH for the cooldown period
                    # to prevent flicker and excessive off/on cycles.

                elif current_pir_state == self._gpio.HIGH:
                    # If motion continues, keep status active
                    motion_detected = True

                # --- C. Control Actuators ---
                self._control_actuators(temp_c, motion_detected)

                # --- D. Wait for next cycle ---
                time.sleep(READ_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nStopping monitor service...")

        except Exception as e:
            print(f"\n[Monitor] Fatal error: {e}")

        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Cleans up GPIO and DHT resources."""
        if self._gpio:
            self._gpio.cleanup()
            print("[Monitor] GPIO cleaned up.")
        if self.dht_device:
            self.dht_device.exit()
            print("[Monitor] DHT device exited.")


if __name__ == "__main__":
    monitor = SmartHomeMonitor()
    monitor.run()