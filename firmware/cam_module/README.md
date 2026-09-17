# ESP32-CAM Vision Module Firmware 📷📡

This module runs on an **AI-Thinker ESP32-CAM** (OV2640 sensor + 4 MB external PSRAM) and provides live live video streaming, flashlight illumination, and hardware sync with the Main ESP32.

---

## 🧭 Navigation

- [**Master Hardware Pinout Guide (../README.md)**](../README.md) — Complete pinout and GPIO mapping table.
- [**Main ESP32 Robotics Module (../main_module/README.md)**](../main_module/README.md) — Motion control & BLE GATT details.
- [**Application Software Guide (../../application/README.md)**](../../application/README.md) — How to install software and run the web cockpit.
- [**Project Root Overview (../../README.md)**](../../README.md) — System features and architecture.

---

## 🌟 Key Responsibilities

1. **Zero-Overhead UDP Streaming Engine**:
   - Streams raw JPEG chunks directly over non-blocking BSD UDP sockets (Port 5000).
   - Custom 8-byte FastPacketHeader containing frame counter, chunk index, and microsecond capture timestamp.
   - P2P auto-discovery: Streams video directly to any client that sends a control or PING packet.

2. **Controlled 10 FPS Pacing & Brownout Prevention**:
   - Fixed pacing period of 100 ms (10 FPS). Each frame takes ~30–40 ms for DMA capture and packet transmission, leaving **60–70 ms of pure FreeRTOS idle time** for lwIP and the Wi-Fi MAC layer.
   - Wi-Fi TX power is capped at WIFI_POWER_17dBm to stop 450 mA current surges from dropping the 5V/3.3V rail.

3. **Core 0 Dedicated Supervisor & Watchdog Task**:
   - The UART command parser and health monitor run in a dedicated task pinned to **Core 0**.
   - Because Core 0 is physically separate from Core 1 (where camera DMA runs), **it never starves**.
   - If the camera sensor DMA stalls on Core 1 for $>5\text{ seconds}$, Core 0 automatically detects the stall and triggers esp_restart().

4. **Inter-ESP32 Hardware UART Sync**:
   - Listens on Serial (GPIO 1 TX, GPIO 3 RX) connected to Main ESP32 Serial2.
   - Periodically sends CAM_IP:<ip> and CAM_HEARTBEAT:... every 1.0 s.
   - Executes immediate hardware commands from Main ESP32:
     - L <val> — Set flashlight brightness (0–255 PWM).
     - R <val> — Switch resolution (framesize 0–13).
     - Q <val> — Adjust JPEG quality (10–63).
     - REBOOT — Trigger instant hardware reset.

5. **Clean Wi-Fi Reconnect State Machine**:
   - If the link drops, it cleanly cycles the radio (WiFi.disconnect(true) $\to$ WiFi.mode(WIFI_OFF) $\to$ WiFi.mode(WIFI_STA) $\to$ WiFi.begin) every 3 seconds.
   - Reboots automatically after 25 seconds of continuous disconnection to recover from hung access points.

---

## 📌 Hardware Pinout Summary

> For the comprehensive pinout and wiring diagram, refer to the [**Master Pinout Guide (../README.md)**](../README.md).

- **Flashlight LED:** GPIO 4 (LEDC PWM Channel 7, 5000 Hz)
- **Status LED:** GPIO 33 (Active LOW)
- **UART Sync to Main ESP32:** RX (GPIO 3) $\longleftarrow$ Main ESP32 TX2, TX (GPIO 1) $\longrightarrow$ Main ESP32 RX2, GND $\longleftrightarrow$ GND
- **OV2640 Sensor:** D0–D7 on IO5/18/19/21/36/39/34/35, XCLK: IO0, PCLK: IO22, VSYNC: IO25, HREF: IO23, SIOD: IO26, SIOC: IO27, PWDN: IO32

---

## 🛠️ How to Compile & Flash

### Board Settings (Arduino IDE / rduino-cli):
- **FQBN:** esp32:esp32:esp32cam
- **Board:** AI Thinker ESP32-CAM
- **CPU Frequency:** 240MHz (WiFi/BT)
- **Flash Frequency:** 80MHz
- **Flash Mode:** QIO
- **Partition Scheme:** Huge APP (3MB No OTA/1MB SPIFFS)
- **PSRAM:** Enabled

### Flashing via rduino-cli:
`ash
tools/arduino-cli/arduino-cli.exe compile --fqbn esp32:esp32:esp32cam firmware/cam_module
tools/arduino-cli/arduino-cli.exe upload -p COM5 --fqbn esp32:esp32:esp32cam firmware/cam_module
`
*(If using a USB-TTL programmer without auto-reset, bridge **GPIO 0 to GND** before powering on to enter bootloader mode, flash, and then remove the bridge).*
