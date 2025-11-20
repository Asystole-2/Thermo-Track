import time
from typing import Optional, Dict, Any
import threading
from flask import current_app

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


class HardwareController:
    """Controller for hardware components (Fan, Buzzer, etc.)"""

    # PIN CONFIGURATION (BCM numbering)
    BUZZER_PIN = 27
    FAN_PIN = 14
    LED_PIN = 22

    # Presets
    PRESETS = {
        'comfort': {'fan_auto': True, 'temp_threshold': 22.0},
        'energy_saver': {'fan_auto': True, 'temp_threshold': 24.0},
        'manual': {'fan_auto': False},
        'away': {'fan_auto': False, 'fan_state': False}
    }

    def __init__(self):
        self._gpio = GPIO
        self._setup_gpio()
        self.current_preset = 'comfort'
        self.fan_auto_mode = True
        self.temp_threshold = 22.0
        self.fan_state = False
        self.buzzer_state = False
        self._buzzer_timer = None

        print("[HardwareController] Initialized")

    def _setup_gpio(self):
        """Configure GPIO pins for outputs"""
        try:
            self._gpio.cleanup()
        except Exception:
            pass

        self._gpio.setmode(self._gpio.BCM)

        # Outputs
        self._gpio.setup(self.BUZZER_PIN, self._gpio.OUT, initial=self._gpio.LOW)
        self._gpio.setup(self.FAN_PIN, self._gpio.OUT, initial=self._gpio.LOW)
        self._gpio.setup(self.LED_PIN, self._gpio.OUT, initial=self._gpio.LOW)

        print(f"[HardwareController] GPIO configured - Buzzer:{self.BUZZER_PIN}, Fan:{self.FAN_PIN}")

    def set_fan_state(self, state: bool):
        """Manually control fan state"""
        self.fan_state = bool(state)
        self._gpio.output(self.FAN_PIN, self._gpio.HIGH if self.fan_state else self._gpio.LOW)
        print(f"[HardwareController] Fan {'ON' if self.fan_state else 'OFF'}")

        # Publish state change
        self._publish_state()

    def set_fan_auto_mode(self, auto_mode: bool):
        """Enable/disable automatic fan control based on temperature"""
        self.fan_auto_mode = bool(auto_mode)
        print(f"[HardwareController] Fan auto mode: {self.fan_auto_mode}")
        self._publish_state()

    def set_temperature_threshold(self, threshold: float):
        """Set temperature threshold for automatic fan control"""
        self.temp_threshold = float(threshold)
        print(f"[HardwareController] Temperature threshold set to {self.temp_threshold}°C")
        self._publish_state()

    def control_fan_based_on_temp(self, current_temp: Optional[float]):
        """Control fan automatically based on temperature (to be called from sensor loop)"""
        if not self.fan_auto_mode or current_temp is None:
            return

        should_turn_on = current_temp > self.temp_threshold

        if should_turn_on != self.fan_state:
            self.fan_state = should_turn_on
            self._gpio.output(self.FAN_PIN, self._gpio.HIGH if self.fan_state else self._gpio.LOW)
            print(f"[HardwareController] Auto fan {'ON' if self.fan_state else 'OFF'} (Temp: {current_temp}°C)")

    def buzzer_beep(self, duration: float = 0.8):
        """Activate buzzer for specified duration"""
        if self._buzzer_timer and self._buzzer_timer.is_alive():
            return  # Buzzer already active

        self.buzzer_state = True
        self._gpio.output(self.BUZZER_PIN, self._gpio.HIGH)
        print(f"[HardwareController] Buzzer ON for {duration}s")

        # Schedule turn off
        self._buzzer_timer = threading.Timer(duration, self._buzzer_off)
        self._buzzer_timer.start()

    def _buzzer_off(self):
        """Turn off buzzer (internal use)"""
        self.buzzer_state = False
        self._gpio.output(self.BUZZER_PIN, self._gpio.LOW)
        print("[HardwareController] Buzzer OFF")

    def set_buzzer_state(self, state: bool):
        """Manually control buzzer state (for admin/technician)"""
        if state:
            self.buzzer_beep(0.5)  # Short beep for manual activation
        else:
            if self._buzzer_timer and self._buzzer_timer.is_alive():
                self._buzzer_timer.cancel()
            self._buzzer_off()

    def apply_preset(self, preset_name: str):
        """Apply a predefined preset"""
        if preset_name not in self.PRESETS:
            print(f"[HardwareController] Unknown preset: {preset_name}")
            return False

        preset = self.PRESETS[preset_name]
        self.current_preset = preset_name

        if 'fan_auto' in preset:
            self.set_fan_auto_mode(preset['fan_auto'])

        if 'temp_threshold' in preset:
            self.set_temperature_threshold(preset['temp_threshold'])

        if 'fan_state' in preset:
            self.set_fan_state(preset['fan_state'])

        print(f"[HardwareController] Applied preset: {preset_name}")
        self._publish_state()
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get current hardware status"""
        return {
            'fan_state': self.fan_state,
            'fan_auto_mode': self.fan_auto_mode,
            'temp_threshold': self.temp_threshold,
            'buzzer_state': self.buzzer_state,
            'current_preset': self.current_preset,
            'presets': list(self.PRESETS.keys())
        }

    def _publish_state(self):
        """Publish state to PubNub (if available)"""
        try:
            from pubnub_client import publish_data
            publish_data({
                "event": "hardware_state",
                "device_uid": "hardware_controller",
                "state": self.get_status(),
                "at": int(time.time())
            })
        except ImportError:
            pass  # PubNub not available

    def cleanup(self):
        """Clean up resources"""
        print("[HardwareController] Cleaning up...")

        if self._buzzer_timer and self._buzzer_timer.is_alive():
            self._buzzer_timer.cancel()

        self._gpio.output(self.BUZZER_PIN, self._gpio.LOW)
        self._gpio.output(self.FAN_PIN, self._gpio.LOW)
        self._gpio.output(self.LED_PIN, self._gpio.LOW)
        self._gpio.cleanup()


# Global instance
hardware_controller = HardwareController()