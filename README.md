# project_pet_link 🐾🤖

[![GitHub Repository](https://img.shields.io/badge/GitHub-project__pet__link-181717?style=flat&logo=github)](https://github.com/sangrechy/project_pet_link)

**project_pet_link** is an envisioned AI-powered, user-customized companion pet robotics platform designed to intelligently recognize and follow the user, interact with its environment, and serve as an adaptive personal companion.

---

## 🌟 Project Vision & Scope

The ultimate vision of `project_pet_link` is to create an autonomous, user-centric AI companion pet robot that:
- **Follows the User:** Tracks and follows the user smoothly and reliably using on-device vision and sensor fusion.
- **Customizable Pet System:** Adapts to user-defined behavior profiles, reaction speeds, and tracking preferences.
- **Interactive Vision & Sound:** Engages dynamically through real-time video feedback, status indications, and responsive physical gestures.

### ⚠️ Current Development Status (Early Hardware Baseline)
- **Current Milestone:** Foundational hardware and control architecture implementation.
- **Experimental Stage:** The current project represents an initial hardware baseline and proof-of-concept testbed (not yet a final prototype). It is intended to be iteratively tested, altered, and expanded.
- **What is Working Today:**
  - 4-Wheel Drive (4WD) skid-steer chassis with dynamic outer-wheel torque boost and tire-scrub reduction curves.
  - Dual ESP32 architecture: Main ESP32 (kinematics & BLE GATT) + ESP32-CAM (UDP vision streaming).
  - Mutual inter-microcontroller supervision and watchdog unfreeze over hardware UART (`GPIO 16 ⇄ GPIO 17`).
  - 2-Axis Pan/Tilt servo gimbal for camera tracking.
  - Unified Python web cockpit with zero-wait canvas rendering and native 60 Hz USB joystick support.
- **Future Roadmap:** Future development phases will introduce autonomous visual person-following, neural object detection, SLAM navigation, and voice interaction models.

---

## 📂 Repository Structure & Releases

The project code is organized into versioned release directories:

| Release | Status | Architecture & Highlights |
| :--- | :--- | :--- |
| [**`v1/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/README.md) | **Active / Production** | Dual-ESP32 4WD mobile robot with low-latency live UDP camera streaming, Pan/Tilt gimbal, USB joystick cockpit, hardware UART cross-supervision, BLE Nordic UART controls, and connection fail-safe. |

---

## 🧭 Subfolder Documentation Links

| Subfolder | Documentation | Highlights |
| :--- | :--- | :--- |
| [**`v1/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/README.md) | [**v1 Master Release Guide**](https://github.com/sangrechy/project_pet_link/blob/main/v1/README.md) | Full architectural breakdown, wiring guides, web installation steps, and quick-start instructions. |
| [**`v1/application/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/application/README.md) | [**Application Software Guide**](https://github.com/sangrechy/project_pet_link/blob/main/v1/application/README.md) | Web development installation steps, Python backend setup, 2.4 GHz hotspot config, and joystick mappings. |
| [**`v1/firmware/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/README.md) | [**Firmware & Pinout Guide**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/README.md) | Master hardware pinout table, TB6612FNG motor driver connections, servo gimbal wiring, and power rules. |
| [**`v1/firmware/main_module/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/main_module/README.md) | [**Main ESP32 Robotics Module**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/main_module/README.md) | 4WD motor kinematics, BLE GATT server (`PetVision-Robot`), failsafe motion watchdog, and camera supervisor over UART2. |
| [**`v1/firmware/cam_module/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/cam_module/README.md) | [**ESP32-CAM Vision Module**](https://github.com/sangrechy/project_pet_link/blob/main/v1/firmware/cam_module/README.md) | UDP live video engine, 10 FPS rate pacing, 17 dBm brownout protection, and Core 0 freeze watchdog. |
| [**`v1/tools/`**](https://github.com/sangrechy/project_pet_link/blob/main/v1/tools/arduino-cli/LICENSE.txt) | [**Flashing Tools**](https://github.com/sangrechy/project_pet_link/blob/main/v1/tools/arduino-cli/LICENSE.txt) | Bundled standalone Arduino CLI toolchain for firmware compilation and uploading. |

---

## ⚡ Quick Start (v1)

```bash
# 1. Clone repository
git clone https://github.com/sangrechy/project_pet_link.git
cd project_pet_link

# 2. Enter application directory
cd v1/application

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Launch web cockpit and server
python launch.py
```
Open **http://localhost:8000** in your browser.
