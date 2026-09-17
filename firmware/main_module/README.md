# Main ESP32 Robotics & BLE Controller Firmware 🤖⚙️

This module runs on a standard **ESP32** (NodeMCU-32S / ESP32 DevKit) and serves as the core robotics controller for mobility, gimbal tracking, BLE connectivity, and hardware supervision of the camera module.

---

## 🧭 Navigation

- [**Master Hardware Pinout Guide (../README.md)**](../README.md) — Complete pinout and GPIO mapping table.
- [**ESP32-CAM Vision Module (../cam_module/README.md)**](../cam_module/README.md) — UDP video streaming engine.
- [**Application Software Guide (../../application/README.md)**](../../application/README.md) — How to install software and run the web cockpit.
- [**Project Root Overview (../../README.md)**](../../README.md) — System features and architecture.

---

## 🌟 Key Responsibilities

1. **4WD Skid-Steer Motor Drive**:
   - Interfaces with 2x TB6612FNG dual H-bridge motor drivers over 20 kHz silent LEDC PWM.
   - Built-in software polarity correction for mirrored chassis motor mounting (no physical re-soldering needed).
   - Supports forward, backward, in-place spin, differential drive (M <left> <right>), and front/rear selective braking (MB <left> <right> <brake_mode>).

2. **2-Axis Pan & Tilt Servo Gimbal**:
   - 50 Hz PWM with 14-bit resolution on GPIO 5 (Tilt) and GPIO 2 (Pan).
   - Full 0°–180° range (500 µs – 2500 µs pulse width).
   - Instant home-centering to 90°/90° via H command (Joystick Button 11).

3. **High-Speed BLE GATT Server (Nordic UART Service)**:
   - Advertises as PetVision-Robot with perpetual advertising maintenance so reconnects are instantaneous.
   - Custom NUS UUIDs:
     - **Service UUID:** 6E400001-B5A3-F393-E0A9-E50E24DCCA9E
     - **RX Characteristic (Commands):** 6E400002-B5A3-F393-E0A9-E50E24DCCA9E
     - **TX Characteristic (Telemetry & IP):** 6E400003-B5A3-F393-E0A9-E50E24DCCA9E
   - Immediately pushes newly discovered camera IP to the connected controller via BLE notification.

4. **Inter-ESP32 Hardware UART2 Supervisor Watchdog**:
   - Uses hardware Serial2 (GPIO 16 RX2, GPIO 17 TX2 @ 115200 baud).
   - Listens for periodic camera heartbeats (CAM_HEARTBEAT:...).
   - If the camera becomes unresponsive for $>8\text{ seconds}$, the Main ESP32 automatically transmits a REBOOT\n pulse to unfreeze the camera.

5. **Motion Fail-Safe Watchdog**:
   - If communication is lost or no packet is received within 800 ms while the robot is moving, all 4 motors halt automatically.

---

## 📌 Hardware Pinout Summary

> For the comprehensive pinout and wiring diagram, refer to the [**Master Pinout Guide (../README.md)**](../README.md).

- **Driver 1 (M1 Back Left, M2 Front Right):** PWMA: IO25, AIN2: IO26, AIN1: IO27, BIN1: IO32, BIN2: IO33, PWMB: IO13, STBY: IO14
- **Driver 2 (M3 Front Left, M4 Back Right):** PWMA: IO18, AIN2: IO19, AIN1: IO21, BIN1: IO23, BIN2: IO15, PWMB: IO4, STBY: IO22
- **Servos:** Servo 1 (Tilt): IO5, Servo 2 (Pan): IO2
- **UART2 to Camera:** RX2: IO16 $\longleftarrow$ Camera TX, TX2: IO17 $\longrightarrow$ Camera RX

---

## 🛠️ How to Compile & Flash

Using rduino-cli:
`ash
tools/arduino-cli/arduino-cli.exe compile --fqbn esp32:esp32:esp32 firmware/main_module
tools/arduino-cli/arduino-cli.exe upload -p COM3 --fqbn esp32:esp32:esp32 firmware/main_module
`
*(Or open irmware/main_module/main_module.ino in the Arduino IDE and select board ESP32 Dev Module).*
