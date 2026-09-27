# project_pet_link — Firmware & Hardware Pinout Guide 🔌⚡

This directory contains the firmware for the two ESP32 boards used in **project_pet_link**, along with the complete hardware wiring and GPIO pinout.

---

## 🧭 Submodule Navigation

- [**Main Robotics & BLE Module — `main_module/`**](main_module/README.md) — 4WD motor control, kinematics, 2-axis Pan/Tilt servo control, BLE GATT and camera supervision.
- [**Vision & UDP Camera Module — `cam_module/`**](cam_module/README.md) — ESP32-CAM UDP video streaming, 10 FPS rate control and freeze watchdog.

---

## 📌 Master Hardware Pinout

The following pinout is the soldered and verified hardware configuration used in v1.

### 🚗 Motor Driver 1 — TB6612FNG #1
Controls **M1** (Back Left) and **M2** (Front Right).

| Signal | GPIO | Meaning | Forward State |
| :--- | :--- | :--- | :--- |
| **PWMA** | **25** | M1 speed control (PWM) | — |
| **AIN2** | **26** | M1 direction input 2 | HIGH |
| **AIN1** | **27** | M1 direction input 1 | LOW |
| **BIN1** | **32** | M2 direction input 1 | LOW |
| **BIN2** | **33** | M2 direction input 2 | HIGH |
| **PWMB** | **13** | M2 speed control (PWM) | — |
| **STBY** | **14** | Driver enable / standby | HIGH |

**Motor orientation:**
- **M1** → Back Left
- **M2** → Front Right
- **AIN1 + AIN2** → M1 direction control
- **BIN1 + BIN2** → M2 direction control
- **PWMA** → M1 speed
- **PWMB** → M2 speed

---

### 🚗 Motor Driver 2 — TB6612FNG #2
Controls **M3** (Front Left) and **M4** (Back Right).

| Signal | GPIO | Meaning | Forward State |
| :--- | :--- | :--- | :--- |
| **PWMA** | **18** | M3 speed control (PWM) | — |
| **AIN2** | **19** | M3 direction input 2 | LOW |
| **AIN1** | **21** | M3 direction input 1 | HIGH |
| **BIN1** | **23** | M4 direction input 1 | HIGH |
| **BIN2** | **15** | M4 direction input 2 | LOW |
| **PWMB** | **4** | M4 speed control (PWM) | — |
| **STBY** | **22** | Driver enable / standby | HIGH |

**Motor orientation:**
- **M3** → Front Left
- **M4** → Back Right
- **AIN1 + AIN2** → M3 direction control
- **BIN1 + BIN2** → M4 direction control
- **PWMA** → M3 speed
- **PWMB** → M4 speed

---

### 🎥 Pan & Tilt Servo Gimbal

| Servo | GPIO | Meaning |
| :--- | :--- | :--- |
| **Servo 1** | **5** | Tilt — Up / Down |
| **Servo 2** | **2** | Pan — Left / Right |

- **PWM frequency:** 50 Hz
- **Pulse range:** 500–2500 µs
- **Center position:** 90°
- **Servo VCC** → 5V
- **Servo GND** → Common GND

---

### 🔄 Inter-ESP32 UART Bridge

| Camera Signal | Camera GPIO | Main ESP32 GPIO | Meaning |
| :--- | :--- | :--- | :--- |
| **RX** | **3** | **17 (TX2)** | Main ESP32 → Camera |
| **TX** | **1** | **16 (RX2)** | Camera → Main ESP32 |
| **GND** | **GND** | **GND** | Common ground |

---

### ⚡ Power Supply

#### Logic Power
- ESP32 boards are powered through 5V VIN or USB.
- Both ESP32 boards must share a common GND.

#### Motor Power
- TB6612FNG VM is powered from the motor battery supply.
- Use a suitable 2S Li-ion / 7.4V battery pack capable of handling the required motor current.
- **Do not power the motors from the ESP32 3.3V or 5V output.**

---

For the actual firmware code, go to [`main_module/`](main_module/README.md) or [`cam_module/`](cam_module/README.md).
