import os
import time
import adafruit_dht
import board
from datetime import datetime

#PubNub publisher
from core.pubnub_client import publish_data

# --- CONFIGURATION ---
# Sensor is connected to GPIO 4 (BCM numbering)
DHT_PIN = board.D4 
LOG_FILE_PATH = 'CA/Thermo-Track/src/core/dht22/humidity.csv'
READ_INTERVAL_SECONDS = 15.0 # Log and print every 15 seconds

# Initialize the DHT22 device
try:
    dht_device = adafruit_dht.DHT22(DHT_PIN)
    print(f"DHT22 sensor initialized on pin {DHT_PIN}.")
except Exception as e:
    print(f"Error initializing DHT22: {e}")
    exit()

# --- CSV LOGGING SETUP ---
try:
    # 1. Ensure the directory exists
    os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
    
    # 2. Check if the file needs a header
    file_exists = os.path.exists(LOG_FILE_PATH) and os.stat(LOG_FILE_PATH).st_size > 0
    
    f = open(LOG_FILE_PATH, 'a', buffering=1) 
    if not file_exists:
        f.write('Date,Time,Temperature C,Temperature F,Humidity %\r\n')
        print(f"Created new log file and wrote header: {LOG_FILE_PATH}")
        
except Exception as e:
    print(f"FATAL: Could not set up log file at {LOG_FILE_PATH}. Logging disabled.")
    print(f"Error details: {e}")
    # Set log file handle to None so we don't try to write to it later
    f = None

print("\n--- Starting Unified DHT22 Monitoring and Logging + PubNub ---")

# --- MAIN LOOP ---
while True:
    try:
        # 1. Read the sensor data
        temperature_c = dht_device.temperature
        humidity = dht_device.humidity
        
        # Check for bad reads (sometimes they return None)
        if temperature_c is None or humidity is None:
             print(f"[{datetime.now().strftime('%H:%M:%S')}] Sensor read failed (returned None). Retrying...")
             time.sleep(2.0)
             continue
             
        # 2. Calculate Fahrenheit
        temperature_f = temperature_c * (9 / 5) + 32

        # 3. Console Output (Real-time monitoring)
        current_time = datetime.now().strftime('%H:%M:%S')
        print(f"[{current_time}] Temp:{temperature_c:5.1f} C / {temperature_f:5.1f} F    Humidity: {humidity:3.1f}%")
        
        # 4. CSV Logging
        if f:
            # Format time/date for CSV logging
            date_str = datetime.now().strftime('%m/%d/%y')
            time_str = datetime.now().strftime('%H:%M:%S')
            ts = int(time.time())
            
            # Write to CSV
            log_line = f"{date_str},{time_str},{temperature_c:0.1f},{temperature_f:0.1f},{humidity:0.1f}\r\n"
            f.write(log_line)
            #publish to PubNub
        try:
            payload = {
                "event": "dht22_reading",
                "temperature_c": round(float(temperature_c), 2),
                "humidity": round(float(humidity), 2),
                "at": ts
            }
            publish_data(payload)
        except Exception as e:
            print(f"[DHT22] PubNub publish error: {e}")

    except RuntimeError as err:
        # Handle specific sensor read errors (like bad checksum)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sensor Read Error: {err.args[0]}")
    except KeyboardInterrupt:
        print("\n[DHT22] stopping...")
        break
    
    except Exception as e:
        # Handle all other unexpected errors
        print(f"[{datetime.now().strftime('%H:%M:%S')}] An unexpected error occurred: {e}")
        # Optionally break the loop if a severe non-RuntimeError occurs
        # break 

    # 5. Wait for the next read cycle
    time.sleep(READ_INTERVAL_SECONDS)

# Ensure the log file is closed if the loop is somehow exited
if f:
    f.close()
    print("Script terminated. Log file closed.")
