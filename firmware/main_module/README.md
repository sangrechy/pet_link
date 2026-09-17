# ESP32 Main Module Firmware

## Overview
This module runs on a standard **ESP32** board (NodeMCU-32S / ESP32 DevKit) and handles core robotics logic, including motion control, kinematics, 2-axis Pan/Tilt servo actuation, and command telemetry for the robot.

> **Note on Architecture:** Video streaming is offloaded to a separate dedicated module (`../cam_module` running on an ESP32-CAM).

---

## Hardware Configuration & Soldered GPIO Allocation

### Motor Driver 1 (TB6612FNG #1)
Controls **M1** (Back Left) and **M2** (Front Right).

| Signal | ESP32 Pin | Function |
| :--- | :--- | :--- |
| **PWMA** | **GPIO 25** | M1 Speed (LEDC PWM) |
| **AIN1** | **GPIO 27** | M1 Direction Pin 1 |
| **AIN2** | **GPIO 26** | M1 Direction Pin 2 |
| **PWMB** | **GPIO 13** | M2 Speed (LEDC PWM) |
| **BIN1** | **GPIO 32** | M2 Direction Pin 1 |
| **BIN2** | **GPIO 33** | M2 Direction Pin 2 |
| **STBY** | **GPIO 14** | Driver 1 Standby / Enable (Active HIGH) |

### Motor Driver 2 (TB6612FNG #2)
Controls **M3** (Front Left) and **M4** (Back Right).

| Signal | ESP32 Pin | Function |
| :--- | :--- | :--- |
| **PWMA** | **GPIO 18** | M3 Speed (LEDC PWM) |
| **AIN1** | **GPIO 21** | M3 Direction Pin 1 |
| **AIN2** | **GPIO 19** | M3 Direction Pin 2 |
| **PWMB** | **GPIO 4**  | M4 Speed (LEDC PWM) |
| **BIN1** | **GPIO 23** | M4 Direction Pin 1 |
| **BIN2** | **GPIO 15** | M4 Direction Pin 2 |
| **STBY** | **GPIO 22** | Driver 2 Standby / Enable (Active HIGH) |

### Servo Actuators (2-Axis Pan & Tilt)
Controls camera or sensor orientation.

| Actuator | ESP32 Pin | Function |
| :--- | :--- | :--- |
| **SERVO 1** | **GPIO 5** | Pan (Horizontal 0°–180°, LEDC 50 Hz PWM) |
| **SERVO 2** | **GPIO 2** | Tilt (Vertical 0°–180°, LEDC 50 Hz PWM) *(or GPIO 16 if exposed)* |

---

## Motor Mapping & Software Polarity

Because motors are mounted in opposing physical orientations across the chassis, physical forward motion requires software polarity inversion instead of altering physical wiring or soldering.

| Motor | Position | Driver | Software Polarity for Forward | Description |
| :--- | :--- | :--- | :--- | :--- |
| **M1** | Back Left | Driver 1 (A) | **Reversed** | Invert control logic (AIN1 LOW, AIN2 HIGH) |
| **M2** | Front Right | Driver 1 (B) | **Reversed** | Invert control logic (BIN1 LOW, BIN2 HIGH) |
| **M3** | Front Left | Driver 2 (A) | **Normal** | Direct control logic (AIN1 HIGH, AIN2 LOW) |
| **M4** | Back Right | Driver 2 (B) | **Normal** | Direct control logic (BIN1 HIGH, BIN2 LOW) |

### Movement Behavior Summary
- **Forward:** Drive all 4 motors according to the software polarity table above.
- **Backward:** Invert all directions relative to forward motion.
- **Spin Left:** Left motors (M1, M3) reverse; Right motors (M2, M4) forward.
- **Spin Right:** Left motors (M1, M3) forward; Right motors (M2, M4) reverse.
- **Physical Soldering:** Soldering and physical wiring remain untouched; directional corrections are handled strictly in the firmware control layer.
