import os
import time
import csv
import logging
import random
from datetime import datetime
from typing import Optional
from src.core.pubnub_client import publish_data

# Try importing hardware libs (may not be available on non-RPi environments)
try:
    import adafruit_dht  # type: ignore
    import board  # type: ignore
except Exception:
    adafruit_dht = None  # type: ignore
    board = None  # type: ignore

# Configuration
# Use centralized data directory for logs
LOG_FILE_PATH = os.getenv("DHT_LOG_FILE", "data/humidity.csv")
READ_INTERVAL_SECONDS = float(os.getenv("DHT_INTERVAL", "15.0"))

logger = logging.getLogger("dht22_logger")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class DummyDHT:
    """Simulated DHT device used when hardware libraries are not available."""

    def __init__(self):
        random.seed()

    @property
    def temperature(self) -> float:
        # Simulate ambient temp 20-26 C
        return round(random.uniform(20.0, 26.0), 1)

    @property
    def humidity(self) -> float:
        # Simulate humidity 30-70%
        return round(random.uniform(30.0, 70.0), 1)


def ensure_csv(path: str) -> Optional[csv.writer]:
    """Open CSV file for appending and return csv.writer (file kept open)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_exists = os.path.exists(path) and os.stat(path).st_size > 0
        f = open(path, "a", newline="", encoding="utf-8")
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Date", "Time", "Temperature C", "Temperature F", "Humidity %"])
            logger.info("Created new log file and wrote header: %s", path)
        return (f, writer)
    except Exception as e:
        logger.exception("Could not set up CSV log file (%s): %s", path, e)
        return None


def init_dht_device():
    """Initialize hardware DHT22 if available, otherwise return DummyDHT."""
    if adafruit_dht and board:
        try:
            pin = getattr(board, os.getenv("DHT_BOARD_PIN", "D4"))
            dev = adafruit_dht.DHT22(pin)
            logger.info("DHT22 sensor initialized on pin %s.", pin)
            return dev
        except Exception:
            logger.exception("Error initializing real DHT22 — falling back to simulation.")
    else:
        logger.warning("Hardware DHT libs not available; using simulated sensor.")
    return DummyDHT()


def main():
    csv_resource = ensure_csv(LOG_FILE_PATH)
    csv_file = None
    writer = None
    if csv_resource:
        csv_file, writer = csv_resource

    dht = init_dht_device()

    logger.info("Starting DHT22 monitoring (log=%s, interval=%.1f s)", LOG_FILE_PATH, READ_INTERVAL_SECONDS)

    try:
        while True:
            try:
                t_c = getattr(dht, "temperature", None)
                h = getattr(dht, "humidity", None)

                if t_c is None or h is None:
                    logger.warning("Sensor returned None. Retrying in 2s...")
                    time.sleep(2.0)
                    continue

                t_f = t_c * 9.0 / 5.0 + 32.0
                now = datetime.now()
                logger.info("Temp: %.1f°C / %.1f°F | Humidity: %.1f%%", t_c, t_f, h)

                if writer:
                    writer.writerow([now.strftime("%m/%d/%y"), now.strftime("%H:%M:%S"), f"{t_c:0.1f}", f"{t_f:0.1f}", f"{h:0.1f}"])
                    # Ensure data is flushed to disk
                    csv_file.flush()

                # Publish snapshot to PubNub (best-effort)
                try:
                    publish_data({
                        "event": "ThermoTrack_snapshot",
                        "temperature_c": round(float(t_c), 2),
                        "temperature_f": round(float(t_f), 2),
                        "humidity": round(float(h), 2),
                        "at": now.isoformat()
                    })
                except Exception:
                    logger.exception("PubNub publish error")

            except RuntimeError as err:
                logger.warning("Sensor read error: %s", str(err))
            except Exception:
                logger.exception("Unexpected error while reading sensor")

            time.sleep(READ_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Stopping DHT22 monitoring.")
    finally:
        if csv_file:
            try:
                csv_file.close()
                logger.info("CSV log closed.")
            except Exception:
                logger.exception("Error closing CSV log file")


if __name__ == "__main__":
    main()