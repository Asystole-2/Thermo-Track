import time
import RPi.GPIO as GPIO
from src.core.pubnub_client import subscribe_to_updates

# --------------------------
# GPIO Setup
# --------------------------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

FAN_PIN = 14
BUZZER_PIN = 27

GPIO.setup(FAN_PIN, GPIO.OUT)
GPIO.setup(BUZZER_PIN, GPIO.OUT)


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

while True:
    time.sleep(1)
