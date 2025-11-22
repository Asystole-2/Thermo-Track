import time
import RPi.GPIO as GPIO

from src.core.pubnub_client import subscribe_to_updates
from src.core.dht22.dht22 import (
    read_temperature,
)  # adjust if your function is named differently

# --------------------------
# GPIO Setup
# --------------------------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

FAN_PIN = 14  # Relay control pin
BUZZER_PIN = 27  # Buzzer control pin

GPIO.setup(FAN_PIN, GPIO.OUT)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# --------------------------
# Auto Mode Settings
# --------------------------
AUTO_THRESHOLD = 24  # fan turns on at 24°C or higher
AUTO_MODE = True  # auto mode enabled by default
LAST_MANUAL = 0  # time of last manual override
MANUAL_TIMEOUT = 20  # seconds of manual control before auto mode resumes


# --------------------------
# Handle PubNub Commands (Manual Control)
# --------------------------
def handle_command(msg: dict):
    global LAST_MANUAL

    cmd = msg.get("cmd")
    print(f"[Pi] Received: {cmd}")

    # Record manual override time
    LAST_MANUAL = time.time()

    if cmd == "fan_on":
        GPIO.output(FAN_PIN, GPIO.HIGH)
        print("[MANUAL] FAN ON")

    elif cmd == "fan_off":
        GPIO.output(FAN_PIN, GPIO.LOW)
        print("[MANUAL] FAN OFF")

    elif cmd == "buzzer_on":
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        print("[MANUAL] BUZZER ON")

    elif cmd == "buzzer_off":
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        print("[MANUAL] BUZZER OFF")


# --------------------------
# Automatic Fan Control (Fallback)
# --------------------------
def auto_fan_controller():
    """Automatically turn fan on/off based on temperature."""
    global AUTO_MODE

    while True:
        # If no manual override recently, auto mode is active
        if time.time() - LAST_MANUAL > MANUAL_TIMEOUT:
            AUTO_MODE = True
        else:
            AUTO_MODE = False

        if AUTO_MODE:
            temp = read_temperature()

            if temp is not None:
                print(f"[AUTO] Temperature: {temp}°C")

                if temp >= AUTO_THRESHOLD:
                    GPIO.output(FAN_PIN, GPIO.HIGH)
                    print("[AUTO] FAN ON (>= 24°C)")

                else:
                    GPIO.output(FAN_PIN, GPIO.LOW)
                    print("[AUTO] FAN OFF (< 24°C)")

        time.sleep(3)


# --------------------------
# Main Program
# --------------------------
if __name__ == "__main__":
    print("[Pi] Starting PubNub Command Listener...")
    subscribe_to_updates(handle_command)

    print(f"[Pi] Auto Fan Control Enabled (threshold = {AUTO_THRESHOLD}°C)")
    print("[Pi] Listening for commands + monitoring temperature...")

    # RUN AUTO MODE LOOP
    try:
        auto_fan_controller()

    except KeyboardInterrupt:
        print("\n[Pi] Cleaning up GPIO...")
        GPIO.cleanup()
        print("[Pi] Stopped.")
