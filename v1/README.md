# v1 🐾🤖

This is the **v1** working version of **project_pet_link**.

For now, this version is basically a 4WD remote-controlled car with a camera, powered using a power bank. It uses two ESP32 boards for the car control and camera system.

The hardware is still experimental and messy, so this is mainly the first working version of the project.

---

## 🏛️ System Architecture

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

## 📂 Project Structure

### Application
Contains the Python web cockpit, backend server and everything needed to control the robot from the PC.

👉 For installation and application setup, go to:  
[**Application README**](application/README.md) *(or [on GitHub](https://github.com/sangrechy/project_pet_link/blob/main/v1/application/README.md))*

It contains:
- Python environment setup
- Required packages
- Server setup
- Hotspot setup
- Web cockpit usage
- Joystick setup
- Running the application

---

### Firmware
Contains the ESP32 firmware and hardware-related setup.

👉 For wiring, pinouts and firmware setup, go to:  
[**Firmware README**](firmware/README.md) *(or [on GitHub](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/README.md))*

It contains:
- Complete hardware pinout
- TB6612FNG motor driver wiring
- Motor connections
- Servo connections
- ESP32 ↔ ESP32 UART connection
- Power connections
- Firmware setup and flashing

---

## 🧩 v1 Modules

```text
v1/
├── application/
│   └── README.md   → Software & installation
├── firmware/
│   └── README.md   → Hardware, pinout & firmware
└── tools/
    └── arduino-cli/ → Firmware flashing tools
```

For installation and setup, please refer to the application and firmware READMEs.
