import time
from typing import Optional

from core.pubnub_client import publish_data

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class MotionService:
    """
    Detects motion using a PIR sensor and triggers a buzzer + PubNub event.
    """

    def __init__(self, pir_pin: int = 11, buzzer_pin: int = 7, cooldown: float = 2.0):
        self.pir_pin = pir_pin
        self.buzzer_pin = buzzer_pin
        self.cooldown = cooldown
        self._gpio = GPIO
        self._setup_gpio()

    def _setup_gpio(self) -> None:
        """Configure GPIO in BOARD mode and set pin directions."""
        if not self._gpio:
            raise RuntimeError("RPi.GPIO not available")

        self._gpio.setmode(self._gpio.BOARD)
        self._gpio.setup(self.pir_pin, self._gpio.IN)  # PIR sensor output
        self._gpio.setup(
            self.buzzer_pin, self._gpio.OUT, initial=self._gpio.LOW
        )  # active buzzer

        print(
            f"[MotionService] Ready (BOARD). PIR={self.pir_pin}  BUZZER={self.buzzer_pin}"
        )

    def _beep(self, duration: float = 0.8) -> None:
        """Short beep to indicate motion."""
        self._gpio.output(self.buzzer_pin, self._gpio.HIGH)
        time.sleep(duration)
        self._gpio.output(self.buzzer_pin, self._gpio.LOW)

    def run(self, on_event: Optional[callable] = None) -> None:
        """
        - If motion detected, beep and publish an event to PubNub.
        - Optional on_event callback receives the payload dict.
        """
        print("Waiting for motion... (Ctrl+C to stop)")
        try:
            while True:
                if self._gpio.input(self.pir_pin):
                    print("[Motion] DETECTED!")
                    self._beep()

                    payload = {"event": "motion", "occupied": 1, "at": int(time.time())}
                    try:
                        publish_data(payload)  # → PubNub (channel from .env)
                    except Exception as e:
                        print(f"[Motion] PubNub publish error: {e}")

                    if on_event:
                        try:
                            on_event(payload)
                        except Exception as e:
                            print(f"[Motion] on_event error: {e}")

                    time.sleep(self.cooldown)  # cooldown to avoid rapid retriggers
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping motion service...")
        finally:
            self._gpio.cleanup()
            print("[MotionService] GPIO cleaned up.")
