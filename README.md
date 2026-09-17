# pet_link 🐾🤖

High-performance, ultra-low-latency live vision streaming cockpit and 4WD robotics remote controller powered by dual ESP32 microcontrollers and a unified Python backend.

---

## 🌟 System Overview

pet_link combines real-time computer vision with robust skid-steer robot mobility and gimbal tracking:

1. **ESP32-CAM Vision Engine**:
   - Zero-overhead UDP frame streaming (Port 5000) using custom micro-headers and hardware timestamping.
   - Paced 10 FPS rate limiter leaving 60–70ms FreeRTOS idle cycles per frame for networking stability.
   - Optimized RF transmission power (17 dBm) eliminating voltage sags on 5V USB rails.
   - Autonomous Core 0 watchdog supervisor that monitors sensor DMA health and restarts upon stalls.

2. **Main ESP32 Robotics & BLE Controller**:
   - High-efficiency 4WD skid-steer kinematics overcoming tire scrub via dynamic outer-wheel torque boost and continuous inner-wheel counter-rotation.
   - 2-Axis Pan & Tilt servo gimbal (50 Hz PWM).
   - High-speed BLE GATT Nordic UART Service (PetVision-Robot) with perpetual advertising maintenance.
   - Hardware Supervisor on UART2 that continuously monitors the ESP32-CAM and unfreezes it automatically.

3. **Inter-ESP32 Hardware Synchronization Bridge**:
   - Direct physical UART link: Camera RX/TX $\longleftrightarrow$ Main ESP32 TX2/RX2 (GPIO 17/16).
   - Automatic IP auto-discovery: Camera broadcasts its IP on connection, immediately forwarded via BLE.
   - Zero-latency dual-dispatch for flashlight, resolution, and reboot triggers (<1 ms).

4. **Unified Python Cockpit**:
   - FastAPI backend with GPU-accelerated HTML5 Canvas live video stream (/ws/live).
   - Embedded native 60 Hz Pygame-ce USB joystick driver with hotplug support.
   - Automatic 2.4 GHz Windows hotspot management (	est_1 / 12345678).

---

## 🔌 Hardware Pinout & Wiring

### Motor Driver 1 (TB6612FNG #1)
- **M1 (Back Left)**: PWMA $\to$ GPIO 25, AIN2 $\to$ GPIO 26, AIN1 $\to$ GPIO 27
- **M2 (Front Right)**: PWMB $\to$ GPIO 13, BIN2 $\to$ GPIO 33, BIN1 $\to$ GPIO 32
- **STBY**: GPIO 14

### Motor Driver 2 (TB6612FNG #2)
- **M3 (Front Left)**: PWMA $\to$ GPIO 18, AIN2 $\to$ GPIO 19, AIN1 $\to$ GPIO 21
- **M4 (Back Right)**: PWMB $\to$ GPIO 4, BIN2 $\to$ GPIO 15, BIN1 $\to$ GPIO 23
- **STBY**: GPIO 22

### Servos (Pan & Tilt Gimbal)
- **Servo 1 (Tilt - UP/DOWN)**: Signal $\to$ GPIO 5, VCC $\to$ 5V, GND $\to$ GND
- **Servo 2 (Pan - LEFT/RIGHT)**: Signal $\to$ GPIO 2, VCC $\to$ 5V, GND $\to$ GND

### Inter-ESP32 Hardware Sync Bridge
- **Camera RX (GPIO 3)** $\longleftrightarrow$ **Main ESP32 TX2 (GPIO 17)**
- **Camera TX (GPIO 1)** $\longleftrightarrow$ **Main ESP32 RX2 (GPIO 16)**
- **Camera GND** $\longleftrightarrow$ **Main ESP32 GND**

---

## 🎮 Controller Mapping (USB Joystick)

| Physical Control | Pygame ID | Action |
| :--- | :--- | :--- |
| **Left Stick Y** | AXIS_1 | Vehicle Throttle (Forward / Backward) |
| **Left Stick X** | AXIS_0 | High-Efficiency Steering (Linear slowdown + counter-rotation) |
| **Right Stick X / Y** | AXIS_2 / 3 | Camera Pan (GPIO 2) & Tilt (GPIO 5) Gimbal |
| **Button 11** | BUTTON_11 | Camera Center (Homes Pan & Tilt to 90° / 90°) |
| **D-Pad UP** | HAT (0, 1) | Front Wheel Brake (Front wheels OFF) |
| **D-Pad DOWN** | HAT (0, -1) | Rear Wheel Brake (Rear wheels OFF) |
| **D-Pad LEFT / RIGHT** | HAT (±1, 0) | Dedicated High-Speed Zero-Radius Spin |
| **Button 0** | BUTTON_0 | Flashlight Toggle (Dual-path UDP + UART2) |
| **Button 1** | BUTTON_1 | Snapshot Photo Capture |
| **Button 4 / 5** | BUTTON_4 / 5 | Vehicle Speed Decrement / Increment |
| **Button 6 / 7** | BUTTON_6 / 7 | Camera Step Size Decrement / Increment |

---

## 🚀 Quickstart

### 1. Requirements
- Python 3.10+
- Install dependencies:
  ```bash
  pip install -r application/requirements.txt
  ```

### 2. Wi-Fi Hotspot Setup
- Turn on a **2.4 GHz** mobile hotspot or use the automated launcher:
  - **SSID**: `test_1`
  - **Password**: `12345678`

### 3. Launching the Cockpit
```bash
cd application
python launch.py
```
Open your browser at **http://localhost:8000**.
