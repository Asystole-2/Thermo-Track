
# Hardware Wiring Documentation

## Overview

This document contains the complete wiring details for the **ThermoTrack IoT System** including:

* PIR Motion Sensors
* DHT22 Temperature & Humidity Sensors
* Fan Control using GPIO
* Piezo Buzzer

This wiring guide is fully updated based on the final physical layout.

---

#  Raspberry Pi 4B/400 → Components Mapping

| Component                   | GPIO Pin | Physical Pin        | Notes                                       |
| --------------------------- | -------- | ------------------- | ------------------------------------------- |
| **DHT22 Data**              | GPIO 4   | Pin 7               | Uses 10k pull up resistor (already onboard) |
| **PIR Motion Sensor (OUT)** | GPIO 17  | Pin 11              | Trigger signal                              |
| **Piezo Buzzer (+)**        | GPIO 27  | Pin 13              | Active buzzer                               |
| **Fan PWM / Control**       | GPIO 14  | Pin 8               | Via NPN transistor                          |
| **3.3V Power**              | —        | Pin 1 / 17          | Powers PIR + DHT22                          |
| **5V Power**                | —        | Pin 2 / 4           | Powers DC Fan                               |
| **GND**                     | —        | Pin 6 / 9 / 14 / 20 | All grounds together                        |

---

#  Individual Component Wiring

##  DHT22 Sensor (Temperature + Humidity)

**Positions: e10, e11, e12, e13**

* **VCC → Pin 1 (3.3V)**
* **DATA → GPIO 4 (Pin 7)**
* **GND → Pin 6**
* Resistor board used: **b10, b11**

---

##  PIR Motion Sensors (e1, e2, e3)

### PIR Sensor A1 (Left Red Board)

* **OUT → GPIO 17 (Pin 11)**
* **VCC → 3.3V**
* **GND → Ground**

### PIR Sensor A2 (Middle Orange Board)

* **OUT → GPIO 31 (Not a GPIO — NOTE!)**
   *Pin 31 corresponds to GPIO 6 — confirm code if needed*

### PIR Sensor A3 (Right Brown Board)

* **OUT → GPIO 9**
   *Pin 21 corresponds to GPIO 9*

➡ If only **one PIR** is used in software, A1 is the primary.

---

##  Passive Piezo Buzzer (e16, e17)

### Blue board A16 → GPIO 14

### Purple board A17 → GPIO 12

**Final wiring used:**

* **Signal → GPIO 27 (Pin 13)**
* **GND → Pin 14/20**

---

##  Fan Control (DC Fan)

* **Red wire → Pin 2 (5V)**
* **Black wire → Pin 39 (GND)**



---

#  Notes & Safety

* Always power **sensors from 3.3V**, not 5V.
* All grounds must be connected together.

---


