import time
import RPi.GPIO as GPIO
from pubnub_client import subscribe_to_updates

# --------------------------
# GPIO Setup
# --------------------------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Based on your wiring:
# - Right pin (black) -> pin 39 (GND) 
# - Middle pin (red) -> pin 2 (5V) - Power
# - Left pin (green) -> pin 9 (GPIO 14) - Control
FAN_PIN = 14  # GPIO 14 (physical pin 9)
BUZZER_PIN = 27

GPIO.setup(FAN_PIN, GPIO.OUT)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# Initialize fan to OFF
GPIO.output(FAN_PIN, GPIO.LOW)
print("[Pi] Fan initialized to OFF")

# --------------------------
# Handle commands
# --------------------------
def handle_command(msg: dict):
    cmd = msg.get("cmd")
    print(f"[Pi] Received: {cmd}")

    if cmd == "fan_on":
        GPIO.output(FAN_PIN, GPIO.HIGH)
        print("[Pi] FAN ON")

    elif cmd == "fan_off":
        GPIO.output(FAN_PIN, GPIO.LOW)
        print("[Pi] FAN OFF")

    elif cmd == "buzzer_on":
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        print("[Pi] BUZZER ON")

    elif cmd == "buzzer_off":
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        print("[Pi] BUZZER OFF")

# --------------------------
# Start listener
# --------------------------
subscribe_to_updates(handle_command)

print("[Pi] Listening for PubNub commands...")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("[Pi] Cleaning up GPIO...")
    GPIO.cleanup()