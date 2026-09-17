# ESP32-CAM Module Firmware

## Overview
This module runs on an **ESP32-CAM** (AI-Thinker form factor) board.

## Architecture & Purpose
- **Sole Responsibility:** Video capture, streaming, and onboard flashlight illumination.
- **Zero Web UI on ESP32:** To maximize framerate and eliminate RAM/CPU overhead, the ESP32 does not serve any HTML, CSS, or JS. All user interfaces and controls are hosted on the host computer server (`../../application`).
- **Separation of Concerns:** Offloads vision tasks entirely from the main ESP32 (`../main_module`), ensuring neither motor control timing nor video latency degrade each other.

---

## Hardware Specifications (Detected via COM4)

- **Port:** `COM4` (USB-SERIAL CH340)
- **SoC Model:** `ESP32-D0WD-V3` (Silicon Revision `v3.1`)
- **CPU:** Dual Core Xtensa LX6 @ 240 MHz
- **Flash Memory:** 4 MB (32 Mbit), 3.3V
- **RAM:** Internal SRAM + 4 MB External SPI PSRAM
- **Camera Sensor:** OV2640 (2 Megapixel)
- **Flashlight LED:** High-power LED on `GPIO 4` (LEDC PWM controlled)
- **MAC Address:** `b0:cb:d8:f0:23:04`

---

## AI-Thinker OV2640 Pinout Configuration

| Signal | GPIO Pin | Description |
| :--- | :--- | :--- |
| **PWDN** | `GPIO 32` | Power Down control |
| **RESET** | `-1` | Software reset |
| **XCLK** | `GPIO 0` | Camera clock (20 MHz) |
| **SIOD** | `GPIO 26` | SCCB / I2C Data |
| **SIOC** | `GPIO 27` | SCCB / I2C Clock |
| **Y9** | `GPIO 35` | Video data bit 7 |
| **Y8** | `GPIO 34` | Video data bit 6 |
| **Y7** | `GPIO 39` | Video data bit 5 |
| **Y6** | `GPIO 36` | Video data bit 4 |
| **Y5** | `GPIO 21` | Video data bit 3 |
| **Y4** | `GPIO 19` | Video data bit 2 |
| **Y3** | `GPIO 18` | Video data bit 1 |
| **Y2** | `GPIO 5` | Video data bit 0 |
| **VSYNC** | `GPIO 25` | Vertical Sync |
| **HREF** | `GPIO 23` | Horizontal Reference |
| **PCLK** | `GPIO 22` | Pixel Clock |
| **FLASH LED**| `GPIO 4` | White Illumination LED |

---

## Flashing Instructions (Arduino IDE / PlatformIO)

### 1. Arduino IDE Board Settings
- **Board:** `AI Thinker ESP32-CAM`
- **CPU Frequency:** `240MHz (WiFi/BT)`
- **Flash Frequency:** `80MHz`
- **Flash Mode:** `QIO`
- **Partition Scheme:** `Huge APP (3MB No OTA/1MB SPIFFS)`
- **PSRAM:** `Enabled`
- **Port:** `COM4` (or your detected CH340 COM port)

### 2. Wiring for Flashing
> [!IMPORTANT]
> If using an FTDI or standalone programmer without auto-reset:
> 1. Connect **GPIO 0 to GND**.
> 2. Press the **RST** (Reset) button or replug the USB cable to enter Bootloader mode.
> 3. Click **Upload** in the IDE.
> 4. Once upload completes, **disconnect GPIO 0 from GND** and press the **RST** button to start normal execution.
>
> *(Note: If using an ESP32-CAM-MB daughterboard with CH340, flashing mode is triggered automatically by RTS/DTR).*

---

## HTTP Endpoints Reference

The ESP32 runs a high-throughput HTTP server on port `80`:

| Endpoint | Method | Params / Query | Description |
| :--- | :--- | :--- | :--- |
| `/stream` | `GET` | None | Continuous MJPEG stream (`multipart/x-mixed-replace; boundary=frame`) |
| `/light` | `GET` | `state=1` or `0`<br>`val=0..255` | Sets flash LED on/off or adjusts PWM brightness |
| `/status` | `GET` | None | Returns JSON with RSSI, Free Heap, and Light state |
