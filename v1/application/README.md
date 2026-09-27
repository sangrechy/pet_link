# project_pet_link — Host Application & Web Cockpit 🚀💻

The `application/` folder contains the Python backend, browser cockpit and USB joystick controller for **project_pet_link**.

---

## 📦 Requirements

Before starting, make sure you have:
- **Operating System:** Windows 10/11
- **Python:** Python 3.10 or higher
- **Joystick (Optional):** A USB joystick/game controller if you want physical joystick control.

---

## 🛠️ Installation

Open PowerShell or Command Prompt inside the project folder.

### 1. Go to the application folder
```bash
cd v1\application
```

### 2. Create a virtual environment
*(Recommended)*
```bash
python -m venv venv
```

### 3. Activate the virtual environment
```powershell
venv\Scripts\activate
```
After activation, you should see something like:
```text
(venv) C:\...\project_pet_link\v1\application>
```

### 4. Install the required packages
```bash
pip install -r requirements.txt
```

This installs the packages required by the application, including:
- **`fastapi`**
- **`uvicorn`**
- **`bleak`**
- **`pygame-ce`**
- **`pyserial`**
- **`pydantic`**

---

## 🚀 Running the Application

There are two ways to start the application:

### Option 1 — Automatic Hotspot (Recommended)
This is the recommended method.
```bash
python launch.py
```
The launcher automatically creates the temporary 2.4 GHz Windows hotspot used by the system:
- **SSID:** `test_1`
- **Password:** `12345678`

You can also double-click:
```text
run.bat
```
to start it.

### Option 2 — Existing Hotspot / Wi-Fi
If you already have a 2.4 GHz hotspot or Wi-Fi network configured:
```bash
python launch.py --no-hotspot
```
You can also start the server directly:
```bash
python server.py
```

---

## 🌐 Open the Web Cockpit

Once the application starts, open your browser and go to:

👉 **[http://localhost:8000](http://localhost:8000)**

The browser cockpit provides the interface for controlling the robot and viewing the live camera stream.

---

## 🎮 Joystick

If a USB joystick/gamepad is connected, the application automatically detects it.

The main controls are:

| Input | Function |
| :--- | :--- |
| **Left Stick** | Move the car |
| **Right Stick** | Pan / Tilt camera |
| **D-Pad** | Brake / Spin controls |
| **Button 0** | Flashlight |
| **Button 1** | Snapshot |
| **Button 11** | Center camera |
| **Button 4 / 5** | Car speed − / + |
| **Button 6 / 7** | Camera speed − / + |

---

## 📁 Related Documentation

For the other parts of the project:
- **Hardware & Pinout:** [../firmware/README.md](../firmware/README.md)
- **Main ESP32 Firmware:** [../firmware/main_module/README.md](../firmware/main_module/README.md)
- **ESP32-CAM Firmware:** [../firmware/cam_module/README.md](../firmware/cam_module/README.md)

For hardware wiring and firmware setup, refer to the [Firmware README](../firmware/README.md).
