# PetVision Host Application & Web Cockpit 🚀💻

The pplication/ folder contains the single unified Python backend, browser cockpit, and USB joystick controller for the PetVision robot.

---

## 🧭 Project Navigation

- [**Main Project Overview (../README.md)**](../README.md) — System features and architectural overview.
- [**Hardware Pinout Guide (../firmware/README.md)**](../firmware/README.md) — Complete GPIO pinout table and motor driver wiring.
- [**Main ESP32 Robotics Firmware (../firmware/main_module/README.md)**](../firmware/main_module/README.md) — Motion control & BLE GATT details.
- [**ESP32-CAM Vision Firmware (../firmware/cam_module/README.md)**](../firmware/cam_module/README.md) — UDP live streaming & watchdog details.

---

## 📦 How to Install Software

### 1. Prerequisites
- **Operating System:** Windows 10/11
- **Python Version:** Python 3.10 or higher
- **Hardware:** Standard USB joystick or game controller

### 2. Install Dependencies
Open PowerShell or Command Prompt in this folder and install the required Python packages:

`ash
cd application
pip install -r requirements.txt
`

#### Packages Installed:
- **astapi** & **uvicorn** — High-performance asynchronous REST and WebSocket web server.
- **leak** — Cross-platform Bluetooth Low Energy (BLE) client for wireless robot communication.
- **pygame-ce** — Hardware joystick input driver with native 60 Hz polling.
- **pydantic** — Request validation and schema parsing.

---

## 🚀 How to Launch the Application

### Option A: Automated Session Launcher (Recommended)
The launcher automatically sets up a temporary Windows 2.4 GHz hotspot (	est_1 / 12345678), starts the server, and restores your previous hotspot configuration upon exit:

`ash
cd application
python launch.py
`
*(Or double-click un.bat in Windows Explorer).*

### Option B: Manual Launcher (Without Automated Hotspot)
If you already have a 2.4 GHz mobile hotspot enabled on your phone:
`ash
cd application
python launch.py --no-hotspot
`
*(Or run python server.py directly).*

---

## 🌐 Opening the Web Cockpit

Once the server is running, open your web browser and navigate to:

**[http://localhost:8000](http://localhost:8000)**

### Cockpit Interface Features:
- **GPU-Accelerated HTML5 Canvas:** Live video stream with glass-to-glass latency under 60 ms.
- **Real-Time Telemetry HUD:** Live FPS counter, active resolution, round-trip time (RTT), and Wi-Fi RSSI.
- **Illumination Control:** Slider (0–255 PWM) and one-click toggle for the onboard LED flashlight.
- **Resolution Switcher:** Instant dynamic switching between QVGA, CIF, VGA, SVGA, and HD.
- **One-Click Unfreeze / Reboot:** Triggers an immediate hardware reboot pulse across UDP and UART2 to recover a stalled camera.
- **Snapshot Capture:** Saves full-resolution JPEG frames directly to snapshots/.

---

## 🎮 USB Joystick Control Mapping

The application runs a dedicated background Pygame thread that automatically detects when a USB joystick is connected (hotplug supported):

| Physical Input | Pygame ID | Function | Action Details |
| :--- | :--- | :--- | :--- |
| **Left Stick Y** | AXIS_1 | **Vehicle Throttle** | Forward / Backward proportional speed |
| **Left Stick X** | AXIS_0 | **Skid-Steer Steering** | Linear inner-wheel deceleration + dynamic outer-wheel boost |
| **Right Stick X / Y** | AXIS_2 / 3 | **Camera Gimbal** | Pan (GPIO 2) & Tilt (GPIO 5) servo positioning |
| **Button 11** | BUTTON_11 | **Center Camera** | Instantly centers Pan & Tilt servos to 90° / 90° |
| **D-Pad UP** | HAT (0, 1) | **Front Wheel Brake** | Cuts power to front motors only |
| **D-Pad DOWN** | HAT (0, -1) | **Rear Wheel Brake** | Cuts power to rear motors only |
| **D-Pad LEFT / RIGHT**| HAT (±1, 0) | **Dedicated Spin** | High-speed zero-radius in-place spin |
| **Button 0** | BUTTON_0 | **Flashlight Toggle** | Dual-path toggle via UDP and hardware UART wire (<1 ms) |
| **Button 1** | BUTTON_1 | **Snapshot** | Saves timestamped JPEG to disk |
| **Button 4 / 5** | BUTTON_4 / 5| **Car Speed − / +** | Decrements / Increments vehicle max speed by 20 PWM |
| **Button 6 / 7** | BUTTON_6 / 7| **Camera Speed − / +**| Decrements / Increments gimbal step angle by 1° |

---

## 📡 REST & WebSocket API Endpoints

| Endpoint | Method | Protocol | Description |
| :--- | :--- | :--- | :--- |
| /ws/live | WebSocket | Binary | Ultra-low-latency binary video stream with PV01 telemetry header |
| /ws/control | WebSocket | Text | Bi-directional motion and gimbal command stream |
| /api/config | GET / POST | JSON | Read or update camera network configuration and state |
| /api/light | GET | JSON | Adjust or toggle flashlight PWM brightness |
| /api/resolution | GET | JSON | Dynamically change camera resolution (framesize 0–13) |
| /api/quality | GET | JSON | Adjust JPEG compression quality (10–63) |
| /api/camera/reboot| GET | JSON | Dispatches reboot trigger simultaneously via UDP and UART2 bridge |
| /api/robot/command| GET / POST | JSON | Sends a raw motion/gimbal command to the robot |
| /api/robot/status | GET | JSON | Reads BLE connection status, current angles, and joystick state |
| /api/snapshot | GET | Image/JPEG | Captures and downloads the latest frame |
