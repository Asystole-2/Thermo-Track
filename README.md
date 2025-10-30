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

 # 🌡️ DHT22 Sensor Setup Guide
**Hardware Requirements**
-Component	Description
-Single-Board Computer	Raspberry Pi (any model with GPIO pins - Pi 3, 4, or Zero)
-Sensor	DHT22 temperature and humidity sensor (compatible with DHT11/AM2302)
-Wiring	Jumper wires (female-to-female for sensor connection)
-Optional	10kΩ pull-up resistor (often built into sensor modules)
**🔌 Wiring the DHT22 Sensor**
-The DHT22 uses a single-wire digital interface. Follow this pinout configuration:

**DHT22 Pinout to Raspberry Pi**
-DHT22 Pin	Function	Raspberry Pi Pin
-1	VCC (3.3V-5V)	3.3V or 5V Power (Pin 1 or 2)
-2	Data Out	GPIO 4 (Pin 7) or any GPIO
-3	N/C (Not Connected)	—
-4	Ground	Ground (Pin 6)

**Wiring Steps**
-Power Connection: Connect DHT22 VCC to Raspberry Pi 3.3V (Pin 1) or 5V (Pin 2)

-Ground Connection: Connect DHT22 Ground to Raspberry Pi GND (Pin 6)

-Data Connection: Connect DHT22 Data Out to GPIO 4 (Pin 7) - or any available GPIO pin

-Optional: For bare sensors (not modules), add 10kΩ pull-up resistor between VCC and Data pins

**💻 Software Setup & Dependencies**
-The DHT22 integration requires these Python libraries for hardware access and data transmission:

Installation Commands
Run these commands on your Raspberry Pi terminal:

bash
** Update package list**
sudo apt-get update

**Install Python 3 headers (required for Adafruit Blinka compilation)**
sudo apt-get install python3-dev libgpiod-dev -y

** Install required Python libraries**
pip3 install adafruit-circuitpython-dht
pip3 install Adafruit-Blinka
pip3 install pubnub
Required Libraries
adafruit-circuitpython-dht: DHT sensor communication

Adafruit-Blinka: Hardware abstraction layer for GPIO access

pubnub: Real-time data transmission to Thermo-Track dashboard
