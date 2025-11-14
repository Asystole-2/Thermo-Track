import os
import time
import csv
import logging
import random
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from typing import Optional
from src.core.pubnub_client import publish_data

# Try to import the hardware libraries (only work on Raspberry Pi)
try:
    import adafruit_dht  # type: ignore
    import board  # type: ignore
except Exception:
    adafruit_dht = None  # type: ignore
    board = None  # type: ignore

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:
    GPIO = None  # type: ignore

# Load environment
load_dotenv(find_dotenv())

# GPIO pins (BCM numbering)
DHT_BOARD_PIN = getattr(board, os.getenv("DHT_BOARD_PIN", "D4"), None) if board else None
PIR_PIN = int(os.getenv("PIR_PIN", "17"))        # PIR → BCM 17 (physical pin 11)
BUZZER_PIN = int(os.getenv("BUZZER_PIN", "4"))   # Buzzer → BCM 4 (physical pin 7)

# File and timing setup
LOG_FILE_PATH = os.getenv("DHT_LOG_FILE", "data/humidity.csv")
READ_INTERVAL_SECONDS = float(os.getenv("DHT_INTERVAL", "5"))
BEEP_ON_MOTION = os.getenv("BEEP_ON_MOTION", "1") == "1"

logger = logging.getLogger("sensors")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class DummyDHT:
    def __init__(self):
        random.seed()

    @property
    def temperature(self) -> float:
        return round(random.uniform(20.0, 26.0), 1)

    @property
    def humidity(self) -> float:
        return round(random.uniform(30.0, 70.0), 1)


def ensure_csv(file_path: str):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        new_file = not (os.path.exists(file_path) and os.stat(file_path).st_size > 0)
        f = open(file_path, "a", newline="", encoding="utf-8")
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["Date", "Time", "Temperature C", "Temperature F", "Humidity %", "Motion Status"])
        return f, writer
    except Exception as e:
        logger.exception("[CSV] Error setting up log file: %s", e)
        return None, None


def init_dht():
    if not adafruit_dht or not DHT_BOARD_PIN:
        logger.warning("DHT22 not available. Running in simulation mode.")
        return DummyDHT()
    try:
        d = adafruit_dht.DHT22(DHT_BOARD_PIN)
        logger.info("[DHT22] Initialized on %s.", DHT_BOARD_PIN)
        return d
    except Exception as e:
        logger.exception("DHT22 init error: %s", e)
        return DummyDHT()


def init_gpio():
    if not GPIO:
        logger.warning("[GPIO] Not available — skipping PIR and buzzer.")
        return False, None, None

    GPIO.setwarnings(False)
    GPIO.cleanup()
    GPIO.setmode(GPIO.BCM)

    GPIO.setup(PIR_PIN, GPIO.IN)
    GPIO.setup(BUZZER_PIN, GPIO.OUT, initial=GPIO.LOW)
    logger.info("[GPIO] Mode=BCM | PIR=%s | BUZZER=%s", PIR_PIN, BUZZER_PIN)
    return True, PIR_PIN, BUZZER_PIN


def beep(duration=0.1, buzzer_pin=None):
    if not GPIO or buzzer_pin is None:
        return
    try:
        GPIO.output(buzzer_pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(buzzer_pin, GPIO.LOW)
    except Exception:
        logger.exception("Error while beeping")


def main():
    f, writer = ensure_csv(LOG_FILE_PATH)
    dht = init_dht()
    gpio_enabled, pir_pin, buzzer_pin = init_gpio()

    logger.info("--- DHT22 + PIR Monitoring Started ---")
    last_motion = None
    last_beep_at = 0
    beep_cooldown = 1.0

    try:
        while True:
            try:
                t_c = getattr(dht, 'temperature', None)
                h = getattr(dht, 'humidity', None)
            except RuntimeError as err:
                logger.warning("[DHT22] Read error: %s", str(err))
                time.sleep(2)
                continue

            if t_c is None or h is None:
                logger.warning("Sensor returned None. Retrying...")
                time.sleep(2)
                continue

            t_f = t_c * 9 / 5 + 32
            now = datetime.now()

            motion_state = "No Motion"
            motion_value = 0

            if gpio_enabled:
                motion_value = 1 if GPIO.input(pir_pin) else 0
                motion_state = "Yes Motion" if motion_value == 1 else "No Motion"

                now_ts = time.time()
                if motion_value == 1 and last_motion != 1:
                    logger.info("%s Motion detected!", now.strftime('%H:%M:%S'))
                    if BEEP_ON_MOTION and (now_ts - last_beep_at) > beep_cooldown:
                        beep(0.08, buzzer_pin)
                        last_beep_at = now_ts
                elif motion_value == 0 and last_motion != 0:
                    logger.info("%s No motion detected.", now.strftime('%H:%M:%S'))
                last_motion = motion_value

            logger.info("Temp: %0.1f°C / %0.1f°F | Humidity: %0.1f%% | Motion: %s", t_c, t_f, h, motion_state)

            if writer and f:
                writer.writerow([now.strftime('%m/%d/%y'), now.strftime('%H:%M:%S'), f"{t_c:0.1f}", f"{t_f:0.1f}", f"{h:0.1f}", motion_state])
                f.flush()

            try:
                publish_data({
                    "event": "ThermoTrack_snapshot",
                    "temperature_c": round(float(t_c), 2),
                    "temperature_f": round(float(t_f), 2),
                    "humidity": round(float(h), 2),
                    "motion": motion_state,
                    "at": now.isoformat()
                })
            except Exception:
                logger.exception("[PubNub] Publish error")

            time.sleep(READ_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("[Main] Stopping...")
    finally:
        if f:
            try:
                f.close()
            except Exception:
                logger.exception("Error closing CSV file")
        if GPIO:
            GPIO.cleanup()
        logger.info("[Cleanup] CSV closed and GPIO cleaned up.")


if __name__ == "__main__":
    main()