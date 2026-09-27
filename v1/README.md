# project_pet_link 🐾🤖

[![GitHub Repository](https://img.shields.io/badge/GitHub-project__pet__link-181717?style=flat&logo=github)](https://github.com/sangrechy/project_pet_link)

**project_pet_link** is a high-performance, untethered robotics cockpit and live vision streaming system powered by dual ESP32 microcontrollers, a unified Python backend, and an interactive browser dashboard.

---

## 📂 Repository Structure & Releases

The project code is organized into versioned release directories:

| Release | Status | Architecture & Highlights |
| :--- | :--- | :--- |
| [**`v1/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/README.md) | **Active / Production** | Dual-ESP32 4WD mobile robot with low-latency live UDP camera streaming, Pan/Tilt gimbal, USB joystick cockpit, hardware UART cross-supervision, BLE Nordic UART controls, and connection fail-safe. |

---

## 🧭 v1 Subfolder Documentation

For technical details, pinout tables, and setup instructions, refer to each subfolder inside `v1/`:

| Subfolder | Documentation | Highlights |
| :--- | :--- | :--- |
| [**`v1/application/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/application/README.md) | [**Application Software Guide**](https://github.com/sangrechy/project_pet_link/blob/main/v1/application/README.md) | How to install software dependencies, launch the unified server, configure the 2.4 GHz hotspot, use the web cockpit, and map USB joystick controls. |
| [**`v1/firmware/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/README.md) | [**Firmware & Pinout Guide**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/README.md) | Complete soldered hardware pinout, TB6612FNG motor driver connections, servo gimbal wiring, inter-ESP32 UART bridge, and power supply rules. |
| [**`v1/firmware/main_module/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/main_module/README.md) | [**Main ESP32 Robotics Module**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/main_module/README.md) | 4WD motor kinematics, BLE GATT server (`PetVision-Robot`), failsafe motion watchdog, and camera supervisor over UART2. |
| [**`v1/firmware/cam_module/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/cam_module/README.md) | [**ESP32-CAM Vision Module**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/cam_module/README.md) | UDP live video engine, 10 FPS rate pacing, 17 dBm brownout protection, and Core 0 freeze watchdog. |
| [**`v1/tools/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/tools/arduino-cli/LICENSE.txt) | [**Flashing Tools**](https://github.com/sangrechy/project_pet_link/blob/main/v1/tools/arduino-cli/LICENSE.txt) | Bundled standalone Arduino CLI toolchain for firmware compilation and uploading. |

---

## 🏛️ System Architecture (v1)

```text
+-----------------------------------------------------------------------------------+
|                           PROJECT_PET_LINK UNIFIED COCKPIT                        |
|   Web Browser (Canvas Stream @ :8000)   <───>   FastAPI Unified Backend Server    |
|   USB Gamepad / Joystick (Pygame 60Hz)  ───►    (v1/application/server.py)        |
+-----------------------------------------------------------------------------------+
                  │                                            │
         2.4 GHz Wi-Fi (UDP :5000)                      BLE Wireless Link
         (Raw JPEG Chunks + Telemetry)                  (Nordic UART Service NUS)
                  │                                            │
                  ▼                                            ▼
+------------------------------------+             +--------------------------------+
|     ESP32-CAM (Vision Engine)      |             |   Main ESP32 (Robotics & BLE)  |
|                                    |  Hardware   |                                |
| • OV2640 Sensor + 4MB PSRAM        |  UART Link  | • 4-Wheel Drive (2x TB6612FNG) |
| • 10 FPS Paced UDP Live Stream     |◄───────────►| • 2-Axis Pan/Tilt Gimbal       |
| • Core 0 Freeze Watchdog           | (GPIO 16/17)| • Hardware Camera Supervisor   |
+------------------------------------+             +--------------------------------+
```

---

## ⚡ Quick Start (v1)

1. **Clone & Explore:**
   ```bash
   git clone https://github.com/sangrechy/project_pet_link.git
   cd project_pet_link
   ```
2. **Install Dependencies:** Follow the setup in [**`v1/application/README.md`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/application/README.md).
3. **Review Pinouts:** Check wiring in [**`v1/firmware/README.md`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/README.md).
4. **Launch the System:**
   ```bash
   cd v1/application
   python launch.py
   ```
   Open **http://localhost:8000** in your browser.

---

## 🛠️ Web Development & Application Setup

Follow these installation steps to configure and run the web cockpit and backend server:

### 1. Prerequisites
- **Python:** 3.10, 3.11, or 3.12 installed on your system.
- **Node.js (Optional):** Not strictly required; backend and web application are natively served via FastAPI + HTML5 Canvas.
- **Hardware Controller (Optional):** Any standard USB Joystick / Gamepad (e.g., PS4, Xbox, Generic USB).
- **Network:** 2.4 GHz Wi-Fi or Windows Mobile Hotspot for the ESP32-CAM video stream.

### 2. Environment Setup & Dependency Installation

#### Option A: Windows PowerShell / Command Prompt
```powershell
# Navigate into the application directory
cd v1/application

# (Recommended) Create and activate a Python virtual environment
python -m venv venv
venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

#### Dependencies Installed:
- **`fastapi`** & **`uvicorn`** — Asynchronous web server hosting the REST endpoints and binary WebSockets.
- **`bleak`** — Asynchronous Bluetooth Low Energy (BLE) stack for Nordic UART Service.
- **`pygame-ce`** — Hardware gamepad polling worker (60 Hz analog curves).
- **`pyserial`** — Direct USB cable serial communication fallback.
- **`pydantic`** — Schema validation and telemetry serialization.

---

### 3. Launching the Web Application

#### Mode 1: Automated Hotspot Launcher (Recommended)
Automatically enables a temporary 2.4 GHz hotspot (`test_1` / `12345678`), binds the UDP stream, and launches the server:
```powershell
python launch.py
```
*(Or double-click `run.bat` in Windows File Explorer)*

#### Mode 2: Standalone Mode (Existing Wi-Fi / Hotspot)
If you are already connected to your router or phone hotspot:
```powershell
python launch.py --no-hotspot
```
*(Or execute `python server.py` directly)*

---

### 4. Accessing the Web Cockpit

Once started, open your web browser to:
```text
http://localhost:8000
```
> **Remote LAN Access:** If accessing from another PC, tablet, or phone on the same network:
> ```text
> http://<YOUR_COMPUTER_LOCAL_IP>:8000
> ```
> *(Example: `http://192.168.137.1:8000` when using Windows Mobile Hotspot)*

---

### 5. Web UI Features & Controls
- **Live Canvas:** Sub-60ms zero-wait binary JPEG rendering over WebSocket.
- **Dual-ESP Cross-Link Monitor:** Real-time health pulse showing camera and main microcontroller heartbeats.
- **Connection Manager (CONN Button):** 
  - Switch between **Wireless BLE** (with 1-click scan or direct MAC `70:4B:CA:83:A8:EE`) and **Direct USB Cable** (`COM3`).
- **Keyboard Driving:**
  - `W / A / S / D` — Move Forward, Turn Left, Move Backward, Turn Right.
  - `Space` — Instant Emergency Stop.
  - `Arrow Keys` — Pan/Tilt Camera Gimbal.
  - `H` — Re-center Gimbal.
- **USB Joystick:** Plug-and-play with left stick throttle/steer, right stick gimbal, button 0 light, button 1 snapshot.
