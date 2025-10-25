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

- **Frontend:** HTML, Tailwind CSS, JavaScript
- **Backend:** Python (Flask Framework)
- **Database:** MariaDB
- **Hardware:** Raspberry Pi with PIR & DHT22 sensors
- **Realtime Communication:** PubNub
- **Security:** bcrypt password hashing

---

## Setup Instructions

- **Clone the Repository:** cd ThermoTrack/src/web
- **Create Virtual Environment:** python -m venv venv, venv\Scripts\activate (windows)
- **Install Dependencies:** pip install flask,pip install flask-mysqldb, pip install python-dotenv, pip install flask-session
- **Run the Application:** flask run
