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
| 🔐 **Secure Authentication** | Hashed passwords and secure session handling |
| 🧠 **Smart HVAC Recommendations** | AI-driven suggestions (Gemini AI) |
| 📊 **Real-time Dashboard** | Live temperature, humidity, and room activity |
| 📡 **Live Sensor Data** | PubNub-powered data streaming |
| ⚡ **Energy Efficiency** | System optimizes comfort & energy usage |
| 🔔 **Notification System** | Smart alerts for unsafe conditions |
| 🌍 **Weather‑Aware Adjustments** | Automatically adapts based on weather |
| 🔑 **Google Login Support** | OAuth 2.0 secure authentication |

---

## 🛠️ Technology Stack

### **Frontend**
- HTML5  
- Tailwind CSS  
- JavaScript  

### **Backend**
- Python  
- Flask  
- Flask‑MySQLdb  

### **Database**
- MariaDB / MySQL  

### **Hardware**
- Raspberry Pi  
- DHT22 Sensor  
- PIR Sensor  

### **Other Services**
- PubNub (live sensor communication)  
- Google Gemini AI (HVAC suggestions)  
- Google OAuth Login  

---

# 🚀 Setup Guide

## 1️⃣ Clone Repository
```bash
git clone https://github.com/Asystole-2/Thermo-Track.git
cd Thermo-Track/src/web
```

---

## 2️⃣ Create Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate  # Mac/Linux
```

---

## 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

If your project does not include a `requirements.txt`, install manually:

```bash
pip install flask flask-mysqldb flask-session python-dotenv google-auth google-auth-oauthlib google-auth-httplib2 pubnub google-generativeai requests
```

---

# 🔧 Environment Variables (`.env`)

Create a `.env` file inside `src/web/`:

```env
# MySQL
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=yourpassword
MYSQL_DB=thermotrack

# PubNub
PUBNUB_PUBLISH_KEY=your_pub_key
PUBNUB_SUBSCRIBE_KEY=your_sub_key
PUBNUB_CHANNEL=ThermoTrack

# AI
GEMINI_API_KEY=your_gemini_key
OPENWEATHER_API_KEY=your_weather_key
DEFAULT_CITY=Dublin
DEFAULT_COUNTRY=IE

# Google OAuth
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
OAUTH_REDIRECT_URI=http://localhost:5000/auth/google/callback
```

---

# 🔑 Google OAuth Setup

### 1. Go to Google Cloud Console  
https://console.cloud.google.com/

### 2. Enable APIs  
- Google People API  
- Google OAuth2.0  

### 3. Create OAuth Client  
```
Credentials → Create Credentials → OAuth Client ID
```

### 4. Set Authorized Redirect URI:
```
http://localhost:5000/auth/google/callback
```

### 5. Put the Client ID + Secret in `.env`

---

# 🤖 AI HVAC Condition Suggester

ThermoTrack uses **Google Gemini AI** to provide intelligent HVAC suggestions.

### Install AI dependencies:
```bash
pip install google-generativeai
```

---

# 📡 Raspberry Pi Sensor Setup

### Install GPIO support:
```bash
sudo apt install -y python3-rpi.gpio
```

### DHT22 Wiring

| DHT22 Pin | Raspberry Pi Pin |
|----------|------------------|
| VCC | 3.3V |
| DATA | GPIO 4 |
| GND | Ground |

### Install libraries:
```bash
sudo apt-get update
sudo apt-get install python3-dev libgpiod-dev -y
pip3 install adafruit-circuitpython-dht Adafruit-Blinka pubnub
```

---

# ▶️ Run the Web Application

```bash
flask run
```

---

# 📄 License
MIT License © 2025 ThermoTrack
