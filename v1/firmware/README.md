# PetVision Firmware & Hardware Pinout Guide 🔌⚡

This directory contains the firmware source code for the two ESP32 microcontrollers powering the robot, along with the master hardware wiring and GPIO allocation guide.

---

## 🧭 Submodule Navigation

- [**Main Robotics & BLE Module (`main_module/`)**](main_module/README.md) — 4WD motor drive, kinematics, 2-axis Pan/Tilt servo control, BLE GATT server, and UART2 camera supervisor.
- [**Vision & UDP Camera Module (`cam_module/`)**](cam_module/README.md) — ESP32-CAM zero-overhead UDP live video engine, 10 FPS rate pacing, and Core 0 freeze watchdog.
- [**Main Project Overview (`../README.md`)**](../README.md) — High-level architecture and system features.
- [**Application Software Guide (`../application/README.md`)**](../application/README.md) — How to install dependencies, run the backend, and use the web cockpit.

---

## 📌 Master Hardware Pinout (Soldered & Verified)

### Motor Driver 1 — TB6612FNG #1
Controls **M1** (Back Left) and **M2** (Front Right).

| Signal | ESP32 Pin | Target Motor / Function | Software Polarity for Forward |
| :--- | :--- | :--- | :--- |
| **PWMA** | **GPIO 25** | M1 Speed (LEDC PWM Channel 0) | — |
| **AIN2** | **GPIO 26** | M1 Direction Pin 2 | HIGH |
| **AIN1** | **GPIO 27** | M1 Direction Pin 1 | LOW (Reversed polarity) |
| **BIN1** | **GPIO 32** | M2 Direction Pin 1 | LOW (Reversed polarity) |
| **BIN2** | **GPIO 33** | M2 Direction Pin 2 | HIGH |
| **PWMB** | **GPIO 13** | M2 Speed (LEDC PWM Channel 1) | — |
| **STBY** | **GPIO 14** | Driver 1 Enable (Active HIGH) | — |

---

### Motor Driver 2 — TB6612FNG #2
Controls **M3** (Front Left) and **M4** (Back Right).

| Signal | ESP32 Pin | Target Motor / Function | Software Polarity for Forward |
| :--- | :--- | :--- | :--- |
| **PWMA** | **GPIO 18** | M3 Speed (LEDC PWM Channel 2) | — |
| **AIN2** | **GPIO 19** | M3 Direction Pin 2 | LOW |
| **AIN1** | **GPIO 21** | M3 Direction Pin 1 | HIGH (Normal polarity) |
| **BIN1** | **GPIO 23** | M4 Direction Pin 1 | HIGH (Normal polarity) |
| **BIN2** | **GPIO 15** | M4 Direction Pin 2 | LOW |
| **PWMB** | **GPIO 4**  | M4 Speed (LEDC PWM Channel 3) | — |
| **STBY** | **GPIO 22** | Driver 2 Enable (Active HIGH) | — |

---

### Pan & Tilt Servo Gimbal (50 Hz LEDC PWM)

| Servo | ESP32 Pin | Motion Axis | Pulse Width Range |
| :--- | :--- | :--- | :--- |
| **Servo 1** | **GPIO 5** | **Tilt (UP / DOWN)** | 500 µs (0°) — 2500 µs (180°), Center: 90° |
| **Servo 2** | **GPIO 2** | **Pan (LEFT / RIGHT)** | 500 µs (0°) — 2500 µs (180°), Center: 90° |

> **Power note:** Servo VCC (Red) connects to the **5V** rail; GND (Brown) connects to **common GND**.

---

### Inter-ESP32 Hardware Synchronization Bridge

A dedicated physical UART link connects the ESP32-CAM and Main ESP32 for instant telemetry, IP auto-discovery, and automated freeze recovery:

| Camera Wire | Camera Pin | Connected To | Main ESP32 Pin | Function |
| :--- | :--- | :--- | :--- | :--- |
| **Camera R (RX)** | GPIO 3 (U0RXD) | $\longleftrightarrow$ | **GPIO 17 (TX2)** | Main ESP32 commands Camera (Reboot, Light, Resolution) |
| **Camera T (TX)** | GPIO 1 (U0TXD) | $\longleftrightarrow$ | **GPIO 16 (RX2)** | Camera streams IP & Heartbeat to Main ESP32 |
| **Camera GND** | GND | $\longleftrightarrow$ | **GND** | Shared logic ground |

---

### Complete GPIO Master Allocation Table

```text
GPIO 2  ───► Servo 2 (Pan: Left / Right)
GPIO 4  ───► Motor M4 PWMB (Back Right Speed)
GPIO 5  ───► Servo 1 (Tilt: Up / Down)

GPIO 13 ───► Motor M2 PWMB (Front Right Speed)
GPIO 14 ───► Driver 1 STBY (Enable)
GPIO 15 ───► Motor M4 BIN2 (Back Right Dir 2)
GPIO 16 ───► Inter-ESP32 UART2 RX2 (from Camera TX)
GPIO 17 ───► Inter-ESP32 UART2 TX2 (to Camera RX)
GPIO 18 ───► Motor M3 PWMA (Front Left Speed)
GPIO 19 ───► Motor M3 AIN2 (Front Left Dir 2)

GPIO 21 ───► Motor M3 AIN1 (Front Left Dir 1)
GPIO 22 ───► Driver 2 STBY (Enable)
GPIO 23 ───► Motor M4 BIN1 (Back Right Dir 1)
GPIO 25 ───► Motor M1 PWMA (Back Left Speed)
GPIO 26 ───► Motor M1 AIN2 (Back Left Dir 2)
GPIO 27 ───► Motor M1 AIN1 (Back Left Dir 1)

GPIO 32 ───► Motor M2 BIN1 (Front Right Dir 1)
GPIO 33 ───► Motor M2 BIN2 (Front Right Dir 2)
```

---

## ⚡ Power Supply Guidelines

1. **Logic (3.3V / 5V)**:
   - ESP32 microcontrollers are powered via 5V VIN or USB.
   - Both boards must share a **common ground (GND)**.
2. **Motor Power (VM)**:
   - TB6612FNG VM pins must be powered from a 2S Li-ion / 7.4V battery pack capable of supplying at least 2A peak current.
   - Never draw motor power from the ESP32 3.3V or 5V regulator output.
