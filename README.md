# pet_link 🐾🤖

**pet_link** is a high-performance, untethered robotics cockpit and live vision streaming system powered by dual ESP32 microcontrollers, a unified Python backend, and an interactive browser dashboard.

---

## 🌟 What is pet_link?

pet_link bridges low-latency computer vision, agile 4WD robotics mobility, and precision camera tracking into a single unified platform:

- **Live Video Streaming:** Zero-overhead UDP live streaming (Port 5000) from an ESP32-CAM directly to an HTML5 canvas with glass-to-glass latency under 60 ms.
- **High-Efficiency 4WD Skid-Steer Mobility:** Solves the classic 4-wheel tire scrub problem by combining a dynamic outer-wheel torque boost with a smooth, continuous inner-wheel deceleration and active counter-rotation curve.
- **2-Axis Pan & Tilt Gimbal:** High-precision 50 Hz PWM servo tracking (0°–180°) with instantaneous one-click centering (Button 11).
- **Wireless BLE & Dual-Channel Controls:** Wireless motion and gimbal control over Nordic UART Service (NUS) Bluetooth Low Energy, with parallel dispatch across hardware UART wires.
- **Anti-Freeze Dual-Supervisor Architecture:** An isolated Core 0 watchdog on the camera plus an external hardware supervisor on the Main ESP32 continuously monitor communication and automatically reboot/unfreeze the camera if a DMA or sensor hang occurs.
- **Native USB Joystick Support:** Plug-and-play game controller integration with 60 Hz polling, analog steering curves, and physical button shortcuts.

---

## 🧭 Repository & Documentation Guide

For detailed technical guides, hardware pinouts, and setup instructions, please refer to the dedicated README files in each subfolder:

| Directory | Documentation Link | What It Contains |
| :--- | :--- | :--- |
| **pplication/** | [**Application Software Guide**](application/README.md) | **How to install software dependencies**, launch the unified server, configure the 2.4 GHz hotspot, use the web cockpit, and map USB joystick controls. |
| **irmware/** | [**Firmware & Master Pinout Guide**](firmware/README.md) | **Complete soldered hardware pinout**, TB6612FNG motor driver connections, servo gimbal wiring, inter-ESP32 UART bridge, and power supply rules. |
| **irmware/main_module/** | [**Main ESP32 Robotics Module**](firmware/main_module/README.md) | 4WD motor kinematics, BLE GATT server (PetVision-Robot), failsafe motion watchdog, and camera supervisor over UART2. |
| **irmware/cam_module/** | [**ESP32-CAM Vision Module**](firmware/cam_module/README.md) | UDP live video engine, 10 FPS rate pacing, 17 dBm brownout protection, and Core 0 freeze watchdog. |

---

## 🏛️ System Architecture

`
+-----------------------------------------------------------------------------------+
|                              PETLINK UNIFIED COCKPIT                              |
|   Web Browser (Canvas Stream @ :8000)   <───>   FastAPI Unified Backend Server    |
|   USB Gamepad / Joystick (Pygame 60Hz)  ───►    (application/server.py)           |
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
`

---

## ⚡ Quick Start

1. **Install Software:** Follow the step-by-step setup in the [**Application Guide**](application/README.md).
2. **Review Pinouts & Wire Hardware:** Follow the [**Firmware & Pinout Guide**](firmware/README.md).
3. **Launch the System:**
   `ash
   cd application
   python launch.py
   `
   Open **http://localhost:8000** in your browser.
