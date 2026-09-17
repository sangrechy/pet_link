# PetVision Host Application & Web Console

This is the host-side application for the PetVision robot. By hosting the web dashboard and control interface on your computer (instead of on the ESP32-CAM), the ESP32 saves memory and processing power, delivering a seamless, low-latency video stream.

---

## Features
- **Dynamic 2.4 GHz Hotspot Session (SHAREit Style):** Automatically snapshots your current Windows hotspot settings, launches a temporary 2.4 GHz session (`test_1` / `12345678`) for the ESP32-CAM, and automatically restores your original hotspot name and password when you close the server.
- **Zero-Overhead Camera Proxy:** Receives raw MJPEG from the ESP32-CAM and streams it directly to browser clients.
- **Flashlight Illumination Controls:** Toggle switch and PWM brightness slider (0% to 100%) for the onboard high-intensity LED on GPIO 4.
- **Hardware Telemetry HUD:** Displays real-time Wi-Fi signal strength (RSSI), free heap, and connection status.
- **One-Click Snapshots:** Capture and download JPEG frames directly to your computer.
- **Synthetic Offline Display:** If the camera is rebooting or disconnected, the dashboard displays a clear status card instead of a broken feed.

---

## Quick Start

### 1. Install Dependencies
Dependencies are already installed in your Python environment. If needed:
```bash
pip install -r requirements.txt
```

### 2. Start the Server
Double-click `run.bat`, or run from terminal:
```bash
cd application
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Open the Console
Open your browser and navigate to:
```
http://localhost:8000
```

### 4. Connect Your ESP32-CAM
1. Flash `../firmware/cam_module/cam_module.ino` to the ESP32-CAM.
2. Check the Arduino Serial Monitor (115200 baud) for the assigned IP address (e.g., `192.168.1.105`).
3. Enter the IP address into the **Camera IP** box in the header and click **Connect**.
