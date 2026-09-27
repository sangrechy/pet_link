# project_pet_link 🐾🤖

[![GitHub Repository](https://img.shields.io/badge/GitHub-project__pet__link-181717?style=flat&logo=github)](https://github.com/sangrechy/project_pet_link)

**project_pet_link** is a high-performance, untethered robotics cockpit and live vision streaming system powered by dual ESP32 microcontrollers, a unified Python backend, and an interactive browser dashboard.

---

## 📂 Repository Structure & Releases

The project code is organized into versioned release directories:

| Release | Status | Architecture & Highlights |
| :--- | :--- | :--- |
| [**`v1/`**](v1/README.md) | **Active / Production** | Dual-ESP32 4WD mobile robot with low-latency live UDP camera streaming, Pan/Tilt gimbal, USB joystick cockpit, hardware UART cross-supervision, BLE Nordic UART controls, and connection fail-safe. |

---

## 🧭 v1 Subfolder Documentation

For technical details, pinout tables, and setup instructions, refer to each subfolder inside `v1/`:

| Subfolder | Documentation | Highlights |
| :--- | :--- | :--- |
| [**`v1/application/`**](v1/application/README.md) | [**Application Software Guide**](v1/application/README.md) | **How to install software dependencies**, launch the unified server, configure the 2.4 GHz hotspot, use the web cockpit, and map USB joystick controls. |
| [**`v1/firmware/`**](v1/firmware/README.md) | [**Firmware & Pinout Guide**](v1/firmware/README.md) | **Complete soldered hardware pinout**, TB6612FNG motor driver connections, servo gimbal wiring, inter-ESP32 UART bridge, and power supply rules. |
| [**`v1/firmware/main_module/`**](v1/firmware/main_module/README.md) | [**Main ESP32 Robotics Module**](v1/firmware/main_module/README.md) | 4WD motor kinematics, BLE GATT server (`PetVision-Robot`), failsafe motion watchdog, and camera supervisor over UART2. |
| [**`v1/firmware/cam_module/`**](v1/firmware/cam_module/README.md) | [**ESP32-CAM Vision Module**](v1/firmware/cam_module/README.md) | UDP live video engine, 10 FPS rate pacing, 17 dBm brownout protection, and Core 0 freeze watchdog. |
| [**`v1/tools/`**](v1/tools/arduino-cli/LICENSE.txt) | [**Flashing Tools**](v1/tools/arduino-cli/LICENSE.txt) | Bundled standalone Arduino CLI toolchain for firmware compilation and uploading. |

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
2. **Install Dependencies:** Follow the setup in [**`v1/application/README.md`**](v1/application/README.md).
3. **Review Pinouts:** Check wiring in [**`v1/firmware/README.md`**](v1/firmware/README.md).
4. **Launch the System:**
   ```bash
   cd v1/application
   python launch.py
   ```
   Open **http://localhost:8000** in your browser.
