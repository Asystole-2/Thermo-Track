# 🌡️ ThermoTrack

<div align="center">

**Smart Environmental Monitoring System**

*A universally designed smart monitoring system that observes room occupancy, temperature, and humidity to provide intelligent HVAC recommendations*

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.0+-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔐 **Secure Authentication** | Hashed passwords with HTTPS encryption |
| 🧠 **Smart HVAC Recommendations** | AI-driven suggestions based on occupancy and environmental data |
| 📊 **Real-time Dashboard** | Live monitoring of temperature, humidity, and occupancy |
| ⚡ **Energy Efficiency** | Promotes energy savings through intelligent recommendations |
| 👨‍💼 **Admin Policies** | Customizable comfort settings and energy-saving rules |
| 📱 **Universal Design** | Accessible and responsive for all users |

---

## 🛠️ Technology Stack

### **Frontend & Styling**
![HTML5](https://img.shields.io/badge/HTML5-E34F26?logo=html5&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?logo=tailwindcss&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black)

### **Backend & Database**
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?logo=flask&logoColor=white)
![MariaDB](https://img.shields.io/badge/MariaDB-003545?logo=mariadb&logoColor=white)

### **Hardware & Sensors**
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-A22846?logo=raspberrypi&logoColor=white)
![DHT22 Sensor](https://img.shields.io/badge/DHT22_Sensor-00BFFF?logo=sensors&logoColor=white)
![PIR Sensor](https://img.shields.io/badge/PIR_Sensor-FF4500?logo=sensors&logoColor=white)

### **Communication & Security**
![PubNub](https://img.shields.io/badge/PubNub-E61C3F?logo=pubnub&logoColor=white)
![bcrypt](https://img.shields.io/badge/bcrypt-00BFA6?logo=lock&logoColor=white)
![HTTPS](https://img.shields.io/badge/HTTPS-00599C?logo=ssl&logoColor=white)

---

## 🚀 Quick Start

### **Web Application Setup**

```bash
# Clone the repository
git clone https://github.com/Asystole-2/Thermo-Track.git
cd ThermoTrack/src/web

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install flask flask-mysqldb python-dotenv flask-session

# Run the application
flask run

# Clone the repository
git clone https://github.com/Asystole-2/Thermo-Track.git
cd Thermo-Track

# Install Raspberry Pi GPIO
sudo apt install -y python3-rpi.gpio

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -U pip
pip install python-dotenv 'pubnub>=10.4.1'

# Set up environment variables
cp .env.example .env
nano .env  # Add your PUBNUB keys

# Set Python path
export PYTHONPATH="$PWD/src"
```
---

## DHT22 Setup
```bash

DHT22 Pin → Raspberry Pi Pin
─────────────────────────────
VCC (Pin 1)   → 3.3V Power (Pin 1)
Data (Pin 2)  → GPIO 4 (Pin 7)
Ground (Pin 4) → Ground (Pin 6)

# Update package list
sudo apt-get update

# Install Python headers and GPIO dependencies
sudo apt-get install python3-dev libgpiod-dev -y

# Install required Python libraries
pip3 install adafruit-circuitpython-dht Adafruit-Blinka pubnub
```
---

### **🤖 AI Condition Suggester**
```bash
The AI-powered condition suggester analyzes real-time
environmental data (temperature, humidity, occupancy)
combined with local weather forecasts to provide
intelligent HVAC recommendations.
It uses Googles Gemini AI to generate
context-aware suggestions for optimal
comfort and energy efficiency.

# Install AI and weather dependencies
pip install google-generativeai requests python-dotenv

# Or install all dependencies at once:
pip install google-generativeai requests python-dotenv

# API Configuration
# AI and Weather API Keys
GEMINI_API_KEY=your_gemini_api_key_here
OPENWEATHER_API_KEY=your_openweather_api_key_here

# Optional: Default location for weather data
DEFAULT_CITY=Dublin
DEFAULT_COUNTRY=IE

🔑 Obtaining API Keys

-Google Gemini API
Visit Google AI Studio

Sign in with your Google account

Click "Create API Key" in the sidebar

Copy the generated key and add it to your .env file as GEMINI_API_KEY

-OpenWeather API
Register at OpenWeatherMap

Verify your email address

Navigate to the "API Keys" tab in your dashboard

Generate a new key (free tier includes 1,000 calls/day)

Copy the key and add it to your .env file as OPENWEATHER_API_KEY
