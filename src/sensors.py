import os
import time
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from core.pubnub_client import publish_data

# Try to import the hardware libraries (only work on Raspberry Pi)
try:
    import adafruit_dht
    import board
except Exception:
    adafruit_dht = None
    board = None

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None

# Load environment
load_dotenv(find_dotenv())

# GPIO pins (BCM numbering)
DHT_BOARD_PIN = getattr(board, os.getenv("DHT_BOARD_PIN", "D4"), None) if board else None
PIR_PIN = int(os.getenv("PIR_PIN", "17"))        # PIR → BCM 17 (physical pin 11)
BUZZER_PIN = int(os.getenv("BUZZER_PIN", "4"))   # Buzzer → BCM 4 (physical pin 7)

# File and timing setup
LOG_FILE_PATH = 'data/humidity.csv'
READ_INTERVAL_SECONDS = float(os.getenv("DHT_INTERVAL", "5"))
BEEP_ON_MOTION = os.getenv("BEEP_ON_MOTION", "1") == "1"

# Create or open the CSV file
def ensure_csv(file_path: str):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        new_file = not (os.path.exists(file_path) and os.stat(file_path).st_size > 0)
        f = open(file_path, "a", buffering=1)
        if new_file:
            f.write("Date,Time,Temperature C,Temperature F,Humidity %,Motion Status\r\n")
        return f
    except Exception as e:
        print(f"[CSV] Error setting up log file: {e}")
        return None

# Initialize DHT22
def init_dht():
    if not adafruit_dht or not DHT_BOARD_PIN:
        raise RuntimeError("DHT22 not available. Run this on Raspberry Pi with adafruit_dht installed.")
    try:
        d = adafruit_dht.DHT22(DHT_BOARD_PIN)
        print(f"[DHT22] Initialized on {DHT_BOARD_PIN}.")
        return d
    except Exception as e:
        raise RuntimeError(f"DHT22 init error: {e}")

# Initialize GPIO
def init_gpio():
    if not GPIO:
        print("[GPIO] Not available — skipping PIR and buzzer.")
        return False, None, None

    GPIO.setwarnings(False)
    GPIO.cleanup()
    GPIO.setmode(GPIO.BCM)

    GPIO.setup(PIR_PIN, GPIO.IN)
    GPIO.setup(BUZZER_PIN, GPIO.OUT, initial=GPIO.LOW)
    print(f"[GPIO] Mode=BCM | PIR={PIR_PIN} | BUZZER={BUZZER_PIN}")
    return True, PIR_PIN, BUZZER_PIN

# Simple buzzer beep
def beep(duration=0.1, buzzer_pin=None):
    if not GPIO or buzzer_pin is None:
        return
    try:
        GPIO.output(buzzer_pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(buzzer_pin, GPIO.LOW)
    except Exception:
        pass

# Main program
def main():
    f = ensure_csv(LOG_FILE_PATH)
    dht = init_dht()
    gpio_enabled, pir_pin, buzzer_pin = init_gpio()

    print("\n--- DHT22 + PIR Monitoring Started ---")
    last_motion = None
    last_beep_at = 0
    beep_cooldown = 1.0

    try:
        while True:
            # Read DHT22
            try:
                t_c = dht.temperature
                h = dht.humidity
            except RuntimeError as err:
                print(f"[DHT22 {datetime.now().strftime('%H:%M:%S')}] Read error: {err.args[0]}")
                time.sleep(2)
                continue

            if t_c is None or h is None:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Sensor returned None. Retrying...")
                time.sleep(2)
                continue

            t_f = t_c * 9 / 5 + 32
            now = datetime.now()

            # Check motion
            motion_state = "No Motion"
            motion_value = 0

            if gpio_enabled:
                motion_value = 1 if GPIO.input(pir_pin) else 0
                motion_state = "Yes Motion" if motion_value == 1 else "No Motion"

                now_ts = time.time()
                if motion_value == 1 and last_motion != 1:
                    print(f"[{now.strftime('%H:%M:%S')}] Motion detected!")
                    if BEEP_ON_MOTION and (now_ts - last_beep_at) > beep_cooldown:
                        beep(0.08, buzzer_pin)
                        last_beep_at = now_ts
                elif motion_value == 0 and last_motion != 0:
                    print(f"[{now.strftime('%H:%M:%S')}] No motion detected.")
                last_motion = motion_value

            # Print readings
            print(f"[{now.strftime('%H:%M:%S')}] Temp: {t_c:0.1f}°C / {t_f:0.1f}°F | Humidity: {h:0.1f}% | Motion: {motion_state}")

            # Write to CSV
            if f:
                f.write(f"{now.strftime('%m/%d/%y')},{now.strftime('%H:%M:%S')},{t_c:0.1f},{t_f:0.1f},{h:0.1f},{motion_state}\r\n")

            # Publish to PubNub
            try:
                publish_data({
                    "event": "ThermoTrack_snapshot",
                    "temperature_c": round(float(t_c), 2),
                    "temperature_f": round(float(t_f), 2),
                    "humidity": round(float(h), 2),
                    "motion": motion_state,
                    "at": now.isoformat()
                })
            except Exception as e:
                print(f"[PubNub] Publish error: {e}")

            time.sleep(READ_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[Main] Stopping...")
    finally:
        if f:
            f.close()
        if GPIO:
            GPIO.cleanup()
        print("[Cleanup] CSV closed and GPIO cleaned up.")


if __name__ == "__main__":
    main()
