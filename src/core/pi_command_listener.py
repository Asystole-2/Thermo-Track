import time
import RPi.GPIO as GPIO

from src.core.pubnub_client import subscribe_to_updates


# --------------------------
# GPIO Setup
# --------------------------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

FAN_PIN = 17  # Relay control pin
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
# TEMP SENSOR READER
# (replace with your real DHT read later)
# --------------------------
def read_temperature():
    """Temporary fake temperature reading.
    Replace with real DHT22 read later."""
    try:
        # TODO: read from DHT22 sensor
        return 23.5
    except:
        return None


# --------------------------
# PUBNUB COMMAND HANDLER
# --------------------------
def handle_command(msg: dict):
    global LAST_MANUAL, AUTO_MODE

    cmd = msg.get("cmd")
    print(f"[Pi] Received: {cmd}")

    # Any manual command pauses auto mode
    LAST_MANUAL = time.time()
    AUTO_MODE = False

    if cmd in ["fan_on", "Fan On", "FAN_ON"]:
        GPIO.output(FAN_PIN, GPIO.HIGH)
        print("[Pi] FAN ON (manual)")

    elif cmd in ["fan_off", "Fan Off", "FAN_OFF"]:
        GPIO.output(FAN_PIN, GPIO.LOW)
        print("[Pi] FAN OFF (manual)")

    elif cmd in ["buzzer_on", "Buzzer On", "BUZZER_ON"]:
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        print("[Pi] BUZZER ON")

    elif cmd in ["buzzer_off", "Buzzer Off", "BUZZER_OFF"]:
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        print("[Pi] BUZZER OFF")


# --------------------------
# AUTOMATIC FAN CONTROLLER
# --------------------------
def auto_fan_controller():
    global AUTO_MODE

    while True:
        # Resume auto mode if timeout passed
        if time.time() - LAST_MANUAL > MANUAL_TIMEOUT:
            AUTO_MODE = True

        if AUTO_MODE:
            temp = read_temperature()

            if temp is not None:
                print(f"[AUTO] Temperature: {temp}°C")

                if temp >= AUTO_THRESHOLD:
                    GPIO.output(FAN_PIN, GPIO.HIGH)
                    print("[AUTO] FAN ON (≥ threshold)")
                else:
                    GPIO.output(FAN_PIN, GPIO.LOW)
                    print("[AUTO] FAN OFF (< threshold)")

        time.sleep(3)


# --------------------------
# MAIN
# --------------------------
if __name__ == "__main__":
    print("[Pi] Starting PubNub Command Listener...")
    subscribe_to_updates(handle_command)

    print("[Pi] Auto Mode Enabled")
    print("[Pi] Now listening for commands + checking temperature...")

    try:
        auto_fan_controller()
    except KeyboardInterrupt:
        print("\n[Pi] Cleaning up GPIO...")
        GPIO.cleanup()
        print("[Pi] Stopped.")
