# ThermoTrack

**ThermoTrack** is a universally designed smart monitoring system that observes room occupancy, temperature, and humidity to provide intelligent HVAC recommendations — promoting energy efficiency and comfort without directly controlling the system.

---

## Features

- **Secure login system** with hashed passwords and HTTPS
- **Smart recommendations** for HVAC adjustment based on occupancy
- **Real-time dashboard** for temperature, humidity, and occupancy data
- **Admin policies** for comfort settings and energy-saving rules

---

## Technology Stack

- **Frontend:** ![HTML5](https://img.shields.io/badge/HTML5-E34F26?logo=html5&logoColor=white) ![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?logo=tailwindcss&logoColor=white) ![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black) 
- **Backend:** ![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white) ![Flask](https://img.shields.io/badge/Flask-000000?logo=flask&logoColor=white) 
- **Database:** ![MariaDB](https://img.shields.io/badge/MariaDB-003545?logo=mariadb&logoColor=white) 
- **Hardware:** ![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-A22846?logo=raspberrypi&logoColor=white) ![DHT22](https://img.shields.io/badge/DHT22_Sensor-00BFFF?logo=sensors&logoColor=white) ![PIR Sensor](https://img.shields.io/badge/PIR_Sensor-FF4500?logo=sensors&logoColor=white) 
- **Realtime Communication:** ![PubNub](https://img.shields.io/badge/PubNub-E61C3F?logo=pubnub&logoColor=white) 
- **Security:** ![bcrypt](https://img.shields.io/badge/bcrypt-00BFA6?logo=lock&logoColor=white) ![HTTPS](https://img.shields.io/badge/HTTPS-00599C?logo=ssl&logoColor=white) 

---

## Setup Instructions

- **Clone the Repository:** cd ThermoTrack/src/web
- **Create Virtual Environment:** python -m venv venv, venv\Scripts\activate (windows)
- **Install Dependencies:** pip install flask,pip install flask-mysqldb, pip install python-dotenv, pip install flask-session
- **Run the Application:** flask run

---

## Setup Instructions Pi

- **Clone the Repository:** git clone https://github.com/Asystole-2/Thermo-Track.git , 
cd Thermo-Track
- **Install Raspberry Pi GPIO:** sudo apt install -y python3-rpi.gpio
- **create and activate your virtual environment:** python3 -m venv venv , 
source venv/bin/activate
- **Install dependencies:** pip install -U pip ,
pip install python-dotenv ,
pip install 'pubnub>=10.4.1'
- **Create your .env file:** nano .env (Use the .env.example template and replace your PUBNUB keys)
- **Set your path:** export PYTHONPATH="$PWD/src"

---

🌡️ DHT22 Sensor Setup 

1. Hardware Requirements

Single-Board Computer (SBC): Raspberry Pi (any model with GPIO pins, e.g., Pi 3, 4, or Zero).

Sensor: DHT22 (or DHT11/AM2302) temperature and humidity sensor.

Wiring: Jumper wires.

Optional: A 10kΩ pull-up resistor (often built into the sensor module, but required for the bare sensor).

2. Wiring the DHT22 Sensor

The DHT22 is a single-wire digital interface sensor. You will connect it to the Raspberry Pi's GPIO pins.

Pinout (Bare Sensor)

DHT22 Pin

Function

Raspberry Pi Pin

1

VCC (3.3V-5V)

Any 3.3V or 5V Power Pin (e.g., Pin 1 or 2)

2

Data Out

Any GPIO Pin (e.g., GPIO 4 / Pin 7)

3

N/C (Not Connected)

N/A

4

Ground

Any Ground Pin (e.g., Pin 6)

Wiring Steps

Connect the VCC (Power) pin of the DHT22 to the 3.3V (Pin 1) or 5V (Pin 2) power supply on the Raspberry Pi.

Connect the Ground pin of the DHT22 to a GND (Ground, e.g., Pin 6) pin on the Raspberry Pi.

Connect the Data Out pin of the DHT22 to a chosen GPIO pin. GPIO 4 (Pin 7) is typically used for examples and works well, but any available GPIO pin will suffice.

If using a bare sensor (not a module board), place a 10kΩ pull-up resistor between the VCC and Data Out pins.

3. Software Setup and Dependencies

The DHT22 script relies on the Adafruit Blinka library for low-level hardware access and the PubNub library for data transmission.

Run the following commands on your Raspberry Pi terminal:

# 1. Update package list
sudo apt-get update

# 2. Install Python 3 headers (required for Adafruit Blinka compilation)
sudo apt-get install python3-dev libgpiod-dev -y

# 3. Install necessary Python libraries (as defined in requirements.txt)
pip3 install adafruit-circuitpython-dht
pip3 install Adafruit-Blinka
pip3 install pubnub

