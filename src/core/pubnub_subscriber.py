import os
import sys
import time
from dotenv import load_dotenv, find_dotenv

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Now import your existing modules
from src.core.pubnub_client import create_pubnub_client, CHANNEL

# Import database utilities from your existing app
try:
    from app import mysql, db_cursor

    print("[Subscriber] Using existing Flask MySQL connection")
    USE_FLASK_DB = True
except ImportError:
    print("[Subscriber] Flask app not available, using direct MySQL connection")
    USE_FLASK_DB = False
    import mysql.connector

load_dotenv(find_dotenv())


class DatabaseHandler:
    def __init__(self):
        if USE_FLASK_DB:
            self.use_flask_db = True
        else:
            self.use_flask_db = False
            self.db_config = {
                'host': os.getenv("MYSQL_HOST"),
                'user': os.getenv("MYSQL_USER"),
                'password': os.getenv("MYSQL_PASSWORD"),
                'database': os.getenv("MYSQL_DB"),
                'port': int(os.getenv("MYSQL_PORT", "3306"))
            }

    def save_sensor_reading(self, device_uid, temperature=None, humidity=None, motion_detected=None):
        """Save sensor reading to database"""

        if self.use_flask_db:
            # Use existing Flask database connection
            return self._save_with_flask_db(device_uid, temperature, humidity, motion_detected)
        else:
            # Use direct MySQL connection
            return self._save_with_direct_db(device_uid, temperature, humidity, motion_detected)

    def _save_with_flask_db(self, device_uid, temperature, humidity, motion_detected):
        """Save using Flask's MySQL connection"""
        cursor = db_cursor()

        try:
            # Get or create device ID
            cursor.execute(
                "SELECT id, room_id FROM devices WHERE device_uid = %s",
                (device_uid,)
            )
            device_result = cursor.fetchone()

            if not device_result:
                print(f"[DB] Device UID {device_uid} not found. Creating new device...")
                # Create a new device entry in the first room
                cursor.execute("SELECT id FROM rooms LIMIT 1")
                room_result = cursor.fetchone()
                room_id = room_result['id'] if room_result else 1

                cursor.execute(
                    "INSERT INTO devices (room_id, name, device_uid, type, status) VALUES (%s, %s, %s, %s, %s)",
                    (room_id, f"Sensor {device_uid}", device_uid, 'Temperature', 'active')
                )
                device_id = cursor.lastrowid
                print(f"[DB] Created new device with ID: {device_id}")
            else:
                device_id = device_result['id']

            # Insert reading
            cursor.execute("""
                           INSERT INTO readings
                               (device_id, temperature, humidity, motion_detected, recorded_at)
                           VALUES (%s, %s, %s, %s, NOW())
                           """, (device_id, temperature, humidity, motion_detected))

            # Update device last_seen
            cursor.execute("""
                           UPDATE devices
                           SET last_seen_at = NOW()
                           WHERE id = %s
                           """, (device_id,))

            mysql.connection.commit()
            print(
                f"[DB] ✓ Saved reading for {device_uid}: Temp={temperature}, Humidity={humidity}, Motion={motion_detected}")
            return True

        except Exception as e:
            print(f"[DB] ✗ Error saving reading: {e}")
            mysql.connection.rollback()
            return False
        finally:
            cursor.close()

    def _save_with_direct_db(self, device_uid, temperature, humidity, motion_detected):
        """Save using direct MySQL connection"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()

        try:
            # Similar logic as above but with mysql.connector
            cursor.execute(
                "SELECT id FROM devices WHERE device_uid = %s",
                (device_uid,)
            )
            device_result = cursor.fetchone()

            if not device_result:
                print(f"[DB] Device UID {device_uid} not found in database")
                return False

            device_id = device_result[0]

            # Insert reading
            cursor.execute("""
                           INSERT INTO readings
                               (device_id, temperature, humidity, motion_detected, recorded_at)
                           VALUES (%s, %s, %s, %s, NOW())
                           """, (device_id, temperature, humidity, motion_detected))

            # Update device last_seen
            cursor.execute("""
                           UPDATE devices
                           SET last_seen_at = NOW()
                           WHERE id = %s
                           """, (device_id,))

            conn.commit()
            print(f"[DB] Saved reading for device {device_uid}")
            return True

        except Exception as e:
            print(f"[DB] Error saving reading: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()


from pubnub.callbacks import SubscribeCallback
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub


class SensorSubscriber(SubscribeCallback):
    def __init__(self):
        self.db_handler = DatabaseHandler()

    def message(self, pubnub, message):
        try:
            data = message.message
            print(f"[PubNub] Received: {data}")

            event_type = data.get('event')

            if event_type == 'dht22_reading':
                self._handle_dht22_reading(data)
            elif event_type == 'motion':
                self._handle_motion_reading(data)
            else:
                print(f"[PubNub] Unknown event type: {event_type}")

        except Exception as e:
            print(f"[PubNub] Error processing message: {e}")

    def _handle_dht22_reading(self, data):
        """Handle DHT22 temperature/humidity readings"""
        device_uid = data.get('device_uid', 'dht22_sensor_01')
        temperature = data.get('temperature_c')
        humidity = data.get('humidity')

        self.db_handler.save_sensor_reading(
            device_uid=device_uid,
            temperature=temperature,
            humidity=humidity,
            motion_detected=False
        )

    def _handle_motion_reading(self, data):
        """Handle PIR motion sensor readings"""
        device_uid = data.get('device_uid', 'pir_sensor_01')
        motion_detected = data.get('occupied', 0) == 1

        self.db_handler.save_sensor_reading(
            device_uid=device_uid,
            temperature=None,
            humidity=None,
            motion_detected=motion_detected
        )


def start_subscriber():
    """Start the PubNub subscriber"""
    pnconfig = PNConfiguration()
    pnconfig.subscribe_key = os.getenv("PUBNUB_SUBSCRIBE_KEY")
    pnconfig.publish_key = os.getenv("PUBNUB_PUBLISH_KEY")
    pnconfig.uuid = "ThermoTrack_Subscriber"

    pubnub = PubNub(pnconfig)
    subscriber = SensorSubscriber()

    pubnub.add_listener(subscriber)
    pubnub.subscribe().channels(CHANNEL).execute()

    print(f"[PubNub] Subscriber started. Listening on channel: {CHANNEL}")
    print("[PubNub] Press Ctrl+C to stop...")

    # Keep the subscriber running
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n[PubNub]  Subscriber stopped gracefully")


if __name__ == "__main__":
    start_subscriber()