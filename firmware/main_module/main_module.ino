/**
 * ============================================================================
 * ESP32 Main Module Robotics & BLE Remote Controller Firmware
 * Project: PetVision
 * Board: Standard ESP32 (NodeMCU-32S / ESP32 DevKit)
 * 
 * Hardware Setup:
 *  - 2x TB6612FNG Dual H-Bridge Motor Drivers (4-Wheel Drive)
 *  - 2-Axis Pan & Tilt Servo Gimbal (50 Hz LEDC PWM)
 *  - High-Speed BLE GATT Server (Nordic UART Service: 6E400001...)
 *  - Automatic Fail-Safe Watchdog: Motor auto-stop on timeout or disconnect
 * ============================================================================
 */

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ============================================================================
// BLE Nordic UART Service (NUS) UUIDs
// ============================================================================
#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;

// ============================================================================
// SOLDERED GPIO ALLOCATION (DO NOT ALTER)
// ============================================================================

// --- Motor Driver 1 (TB6612FNG #1) ---
// M1: Back Left
#define M1_PWMA_PIN       25
#define M1_AIN2_PIN       26
#define M1_AIN1_PIN       27

// M2: Front Right
#define M2_BIN1_PIN       32
#define M2_BIN2_PIN       33
#define M2_PWMB_PIN       13

#define DRIVER1_STBY_PIN  14

// --- Motor Driver 2 (TB6612FNG #2) ---
// M3: Front Left
#define M3_PWMA_PIN       18
#define M3_AIN2_PIN       19
#define M3_AIN1_PIN       21

// M4: Back Right
#define M4_BIN1_PIN       23
#define M4_BIN2_PIN       15
#define M4_PWMB_PIN        4

#define DRIVER2_STBY_PIN  22

// --- Servos (Pan & Tilt) ---
#define SERVO1_PIN         5   // Servo 1: UP / DOWN (Tilt)
#define SERVO2_PIN         2   // Servo 2: LEFT / RIGHT (Pan)

// --- Inter-ESP32 Hardware UART2 Link (Camera Sync) ---
#define CAM_UART_RX2_PIN  16   // ESP32 RX2 <--- Camera TX
#define CAM_UART_TX2_PIN  17   // ESP32 TX2 ---> Camera RX

String last_known_cam_ip = "";
unsigned long last_cam_heartbeat_time = 0;
bool cam_has_communicated = false;
unsigned long last_cam_reboot_attempt = 0;

// ============================================================================
// LEDC PWM Configuration
// ============================================================================
#define MOTOR_PWM_FREQ    20000 // 20 kHz silent motor drive
#define MOTOR_PWM_RES     8     // 8-bit resolution (0 - 255)

#define SERVO_PWM_FREQ    50    // 50 Hz standard servo frequency
#define SERVO_PWM_RES     14    // 14-bit resolution (0 - 16383)

// LEDC Channels (Core 2.x fallback)
#define CH_M1_PWM         0
#define CH_M2_PWM         1
#define CH_M3_PWM         2
#define CH_M4_PWM         3
#define CH_SERVO1         4
#define CH_SERVO2         5

// Active State & Angles
int current_tilt_angle = 90; // Servo 1 (5)
int current_pan_angle  = 90; // Servo 2 (2)

// Fail-safe Watchdog
unsigned long last_cmd_time = 0;
const unsigned long FAILSAFE_TIMEOUT_MS = 800; // Stop if no packet for 800ms
bool is_moving = false;

// ============================================================================
// Universal PWM Helper Functions
// ============================================================================
void init_pwm_pin(uint8_t pin, uint8_t channel, uint32_t freq, uint8_t res) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(pin, freq, res);
#else
  ledcSetup(channel, freq, res);
  ledcAttachPin(pin, channel);
#endif
}

void write_pwm(uint8_t pin, uint8_t channel, uint32_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pin, duty);
#else
  ledcWrite(channel, duty);
#endif
}

// ============================================================================
// Servo Control (Maps 0°–180° to 500µs–2500µs pulse width at 50Hz / 14-bit)
// ============================================================================
void set_servo_angle(uint8_t servo_id, int angle) {
  angle = constrain(angle, 0, 180);

  // Period = 20,000µs. 14-bit = 16384 ticks
  uint32_t pulse_us = map(angle, 0, 180, 500, 2500);
  uint32_t duty = (pulse_us * 16384) / 20000;

  if (servo_id == 1) {
    current_tilt_angle = angle;
    write_pwm(SERVO1_PIN, CH_SERVO1, duty);
  } else if (servo_id == 2) {
    current_pan_angle = angle;
    write_pwm(SERVO2_PIN, CH_SERVO2, duty);
  }
}

// ============================================================================
// Motor Primitives with Software Polarity Correction
// ============================================================================
// M1: Back Left   --> REVERSED (Forward = AIN1 LOW, AIN2 HIGH)
void set_motor_m1(int speed) {
  speed = constrain(speed, -255, 255);
  if (speed > 0) {
    digitalWrite(M1_AIN1_PIN, LOW);
    digitalWrite(M1_AIN2_PIN, HIGH);
    write_pwm(M1_PWMA_PIN, CH_M1_PWM, speed);
  } else if (speed < 0) {
    digitalWrite(M1_AIN1_PIN, HIGH);
    digitalWrite(M1_AIN2_PIN, LOW);
    write_pwm(M1_PWMA_PIN, CH_M1_PWM, -speed);
  } else {
    digitalWrite(M1_AIN1_PIN, LOW);
    digitalWrite(M1_AIN2_PIN, LOW);
    write_pwm(M1_PWMA_PIN, CH_M1_PWM, 0);
  }
}

// M2: Front Right --> REVERSED (Forward = BIN1 LOW, BIN2 HIGH)
void set_motor_m2(int speed) {
  speed = constrain(speed, -255, 255);
  if (speed > 0) {
    digitalWrite(M2_BIN1_PIN, LOW);
    digitalWrite(M2_BIN2_PIN, HIGH);
    write_pwm(M2_PWMB_PIN, CH_M2_PWM, speed);
  } else if (speed < 0) {
    digitalWrite(M2_BIN1_PIN, HIGH);
    digitalWrite(M2_BIN2_PIN, LOW);
    write_pwm(M2_PWMB_PIN, CH_M2_PWM, -speed);
  } else {
    digitalWrite(M2_BIN1_PIN, LOW);
    digitalWrite(M2_BIN2_PIN, LOW);
    write_pwm(M2_PWMB_PIN, CH_M2_PWM, 0);
  }
}

// M3: Front Left  --> NORMAL   (Forward = AIN1 HIGH, AIN2 LOW)
void set_motor_m3(int speed) {
  speed = constrain(speed, -255, 255);
  if (speed > 0) {
    digitalWrite(M3_AIN1_PIN, HIGH);
    digitalWrite(M3_AIN2_PIN, LOW);
    write_pwm(M3_PWMA_PIN, CH_M3_PWM, speed);
  } else if (speed < 0) {
    digitalWrite(M3_AIN1_PIN, LOW);
    digitalWrite(M3_AIN2_PIN, HIGH);
    write_pwm(M3_PWMA_PIN, CH_M3_PWM, -speed);
  } else {
    digitalWrite(M3_AIN1_PIN, LOW);
    digitalWrite(M3_AIN2_PIN, LOW);
    write_pwm(M3_PWMA_PIN, CH_M3_PWM, 0);
  }
}

// M4: Back Right  --> NORMAL (Inverted per user: Forward = BIN1 HIGH, BIN2 LOW)
void set_motor_m4(int speed) {
  speed = constrain(speed, -255, 255);
  if (speed > 0) {
    digitalWrite(M4_BIN1_PIN, HIGH);
    digitalWrite(M4_BIN2_PIN, LOW);
    write_pwm(M4_PWMB_PIN, CH_M4_PWM, speed);
  } else if (speed < 0) {
    digitalWrite(M4_BIN1_PIN, LOW);
    digitalWrite(M4_BIN2_PIN, HIGH);
    write_pwm(M4_PWMB_PIN, CH_M4_PWM, -speed);
  } else {
    digitalWrite(M4_BIN1_PIN, LOW);
    digitalWrite(M4_BIN2_PIN, LOW);
    write_pwm(M4_PWMB_PIN, CH_M4_PWM, 0);
  }
}

// ============================================================================
// High-Level Robot Kinematics
// ============================================================================
void set_wheels(int fl, int fr, int bl, int br) {
  set_motor_m3(fl); // Front Left
  set_motor_m2(fr); // Front Right
  set_motor_m1(bl); // Back Left
  set_motor_m4(br); // Back Right
  is_moving = (fl != 0 || fr != 0 || bl != 0 || br != 0);
  if (is_moving) {
    last_cmd_time = millis();
  }
}

void stop_motors() {
  set_wheels(0, 0, 0, 0);
  is_moving = false;
}

void move_forward(int speed) {
  set_wheels(speed, speed, speed, speed);
}

void move_backward(int speed) {
  set_wheels(-speed, -speed, -speed, -speed);
}

void spin_left(int speed) {
  set_wheels(-speed, speed, -speed, speed);
}

void spin_right(int speed) {
  set_wheels(speed, -speed, speed, -speed);
}

// Differential Steering Drive
// brake_mode: 0 = all 4 wheels active
//             1 = Front wheels OFF (high-speed front wheel braking)
//             2 = Back wheels OFF (high-speed rear wheel braking)
void drive_differential(int left_speed, int right_speed, int brake_mode = 0) {
  int fl = left_speed;
  int bl = left_speed;
  int fr = right_speed;
  int br = right_speed;

  if (brake_mode == 1) {
    fl = 0;
    fr = 0;
  } else if (brake_mode == 2) {
    bl = 0;
    br = 0;
  }

  set_wheels(fl, fr, bl, br);
}

// ============================================================================
// Command Parser (Unified Serial + BLE)
// Commands:
//   M <left> <right>           -> Differential drive (all 4 wheels)
//   MB <left> <right> <brake>  -> Differential drive with brake (1=front OFF, 2=back OFF)
//   W <fl> <fr> <bl> <br>      -> Direct 4-wheel independent velocity
//   F [speed]                  -> Forward (Default 220)
//   B [speed]                  -> Backward
//   L [speed]                  -> Dedicated Spin Left (in place)
//   R [speed]                  -> Dedicated Spin Right (in place)
//   S                          -> Stop all motors
//   U [step]                   -> Tilt Up (Servo 1, default step 8)
//   D [step]                   -> Tilt Down (Servo 1, default step 8)
//   A [step]                   -> Pan Left (Servo 2, default step 8)
//   C [step]                   -> Pan Right (Servo 2, default step 8)
//   H                          -> Home both servos to 90°
//   P <angle>                  -> Absolute Pan angle (0-180)
//   T <angle>                  -> Absolute Tilt angle (0-180)
// ============================================================================
void process_command(const String& cmd_str) {
  String trimmed = cmd_str;
  trimmed.trim();
  if (trimmed.length() == 0) return;

  // Inter-ESP32 Camera Hardware UART Sync Commands
  if (trimmed.equalsIgnoreCase("GET_CAM_IP")) {
    String ip_str = last_known_cam_ip.length() > 0 ? last_known_cam_ip : "DISCONNECTED";
    Serial.printf("CAM_IP:%s\n", ip_str.c_str());
    if (deviceConnected && pTxCharacteristic) {
      String notif = "CAM_IP:" + ip_str + "\n";
      pTxCharacteristic->setValue((uint8_t*)notif.c_str(), notif.length());
      pTxCharacteristic->notify();
    }
    return;
  } else if (trimmed.equalsIgnoreCase("CAM_REBOOT")) {
    Serial2.println("REBOOT");
    Serial.println("[SUPERVISOR] Sent REBOOT command to Camera over UART2.");
    return;
  } else if (trimmed.startsWith("CAM_") || trimmed.startsWith("cam_")) {
    Serial2.println(trimmed.substring(4));
    return;
  } else if (trimmed.startsWith("LIGHT ") || trimmed.startsWith("light ")) {
    Serial2.printf("L %s\n", trimmed.substring(6).c_str());
    return;
  }

  // 1. Check multi-character kinematics commands
  if (trimmed.startsWith("MB ") || trimmed.startsWith("mb ")) {
    int first_space = trimmed.indexOf(' ');
    int second_space = trimmed.indexOf(' ', first_space + 1);
    int third_space = (second_space != -1) ? trimmed.indexOf(' ', second_space + 1) : -1;

    if (first_space != -1 && second_space != -1) {
      int left_spd = trimmed.substring(first_space + 1, second_space).toInt();
      int right_spd = 0;
      int brake_mode = 0;
      if (third_space != -1) {
        right_spd = trimmed.substring(second_space + 1, third_space).toInt();
        brake_mode = trimmed.substring(third_space + 1).toInt();
      } else {
        right_spd = trimmed.substring(second_space + 1).toInt();
      }
      drive_differential(left_spd, right_spd, brake_mode);
      return;
    }
  } else if (trimmed.startsWith("M ") || trimmed.startsWith("m ")) {
    int first_space = trimmed.indexOf(' ');
    int second_space = trimmed.indexOf(' ', first_space + 1);
    if (first_space != -1 && second_space != -1) {
      int left_spd = trimmed.substring(first_space + 1, second_space).toInt();
      int right_spd = trimmed.substring(second_space + 1).toInt();
      drive_differential(left_spd, right_spd, 0);
      return;
    }
  } else if (trimmed.startsWith("W ") || trimmed.startsWith("w ")) {
    int s1 = trimmed.indexOf(' ');
    int s2 = (s1 != -1) ? trimmed.indexOf(' ', s1 + 1) : -1;
    int s3 = (s2 != -1) ? trimmed.indexOf(' ', s2 + 1) : -1;
    int s4 = (s3 != -1) ? trimmed.indexOf(' ', s3 + 1) : -1;
    if (s1 != -1 && s2 != -1 && s3 != -1 && s4 != -1) {
      int fl = trimmed.substring(s1 + 1, s2).toInt();
      int fr = trimmed.substring(s2 + 1, s3).toInt();
      int bl = trimmed.substring(s3 + 1, s4).toInt();
      int br = trimmed.substring(s4 + 1).toInt();
      set_wheels(fl, fr, bl, br);
      return;
    }
  }

  // 2. Single-character commands
  char type = toupper(trimmed.charAt(0));
  int val = 0;

  int space_idx = trimmed.indexOf(' ');
  if (space_idx != -1) {
    val = trimmed.substring(space_idx + 1).toInt();
  } else if (trimmed.length() > 1) {
    val = trimmed.substring(1).toInt();
  }

  switch (type) {
    // Car Motion
    case 'F': move_forward(val > 0 ? val : 220); break;
    case 'B': move_backward(val > 0 ? val : 220); break;
    case 'L': spin_left(val > 0 ? val : 200); break;
    case 'R': spin_right(val > 0 ? val : 200); break;
    case 'S': stop_motors(); break;

    // Servo Motion (Relative Steps)
    case 'U': // Tilt Up (Servo 1)
      set_servo_angle(1, current_tilt_angle - (val > 0 ? val : 8));
      break;
    case 'D': // Tilt Down (Servo 1)
      set_servo_angle(1, current_tilt_angle + (val > 0 ? val : 8));
      break;
    case 'A': // Pan Left (Servo 2)
      set_servo_angle(2, current_pan_angle + (val > 0 ? val : 8));
      break;
    case 'C': // Pan Right (Servo 2)
      set_servo_angle(2, current_pan_angle - (val > 0 ? val : 8));
      break;
    case 'H': // Home
      set_servo_angle(1, 90);
      set_servo_angle(2, 90);
      break;

    // Direct Absolute Angles
    case 'P': set_servo_angle(2, val); break;
    case 'T': set_servo_angle(1, val); break;

    default: break;
  }
}

// ============================================================================
// BLE Callbacks
// ============================================================================
class MyServerCallbacks: public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
    Serial.println("[BLE] Remote Controller Connected!");
  };

  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
    stop_motors(); // Immediate safety stop on disconnect
    Serial.println("[BLE] Remote Controller Disconnected. Motors halted.");
  }
};

class MyCallbacks: public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    String rxValue = pCharacteristic->getValue();
    if (rxValue.length() > 0) {
      process_command(rxValue);
    }
  }
};

// ============================================================================
// Setup
// ============================================================================
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(5); // Ultra-fast non-blocking serial read
  delay(100);
  Serial.println("\n========================================================");
  Serial.println("       PETVISION ROBOTICS - BLE REMOTE RECEIVER         ");
  Serial.println("========================================================");

  // 1. Initialize Driver 1 GPIOs
  pinMode(M1_AIN1_PIN, OUTPUT);
  pinMode(M1_AIN2_PIN, OUTPUT);
  pinMode(M2_BIN1_PIN, OUTPUT);
  pinMode(M2_BIN2_PIN, OUTPUT);
  pinMode(DRIVER1_STBY_PIN, OUTPUT);

  // 2. Initialize Driver 2 GPIOs
  pinMode(M3_AIN1_PIN, OUTPUT);
  pinMode(M3_AIN2_PIN, OUTPUT);
  pinMode(M4_BIN1_PIN, OUTPUT);
  pinMode(M4_BIN2_PIN, OUTPUT);
  pinMode(DRIVER2_STBY_PIN, OUTPUT);

  // 3. Enable Both Motor Drivers (Active HIGH)
  digitalWrite(DRIVER1_STBY_PIN, HIGH);
  digitalWrite(DRIVER2_STBY_PIN, HIGH);

  // 4. Initialize Motor PWM Channels
  init_pwm_pin(M1_PWMA_PIN, CH_M1_PWM, MOTOR_PWM_FREQ, MOTOR_PWM_RES);
  init_pwm_pin(M2_PWMB_PIN, CH_M2_PWM, MOTOR_PWM_FREQ, MOTOR_PWM_RES);
  init_pwm_pin(M3_PWMA_PIN, CH_M3_PWM, MOTOR_PWM_FREQ, MOTOR_PWM_RES);
  init_pwm_pin(M4_PWMB_PIN, CH_M4_PWM, MOTOR_PWM_FREQ, MOTOR_PWM_RES);

  // 5. Initialize Servo PWM Channels
  init_pwm_pin(SERVO1_PIN, CH_SERVO1, SERVO_PWM_FREQ, SERVO_PWM_RES);
  init_pwm_pin(SERVO2_PIN, CH_SERVO2, SERVO_PWM_FREQ, SERVO_PWM_RES);

  // Center Pan & Tilt servos at 90°
  set_servo_angle(1, 90);
  set_servo_angle(2, 90);
  stop_motors();

  Serial.println("[HARDWARE] Motor drivers active. Servos centered (Tilt: IO5, Pan: IO2).");

  // 6. Initialize BLE GATT Server
  BLEDevice::init("PetVision-Robot");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  // Create Nordic UART Service
  BLEService *pService = pServer->createService(SERVICE_UUID);

  // TX Characteristic (ESP32 -> Controller Telemetry)
  pTxCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID_TX,
    BLECharacteristic::PROPERTY_NOTIFY
  );
  pTxCharacteristic->addDescriptor(new BLE2902());

  // RX Characteristic (Controller -> ESP32 Commands)
  BLECharacteristic *pRxCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID_RX,
    BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
  );
  pRxCharacteristic->setCallbacks(new MyCallbacks());

  pService->start();

  // Start Advertising
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06); // Functions that help with iPhone connections issue
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println("[BLE] Advertising as 'PetVision-Robot'. Waiting for controller connection...");

  // 7. Initialize Hardware UART2 Link to ESP32-CAM (GPIO 16 RX2, GPIO 17 TX2)
  Serial2.begin(115200, SERIAL_8N1, CAM_UART_RX2_PIN, CAM_UART_TX2_PIN);
  Serial2.setTimeout(5);
  Serial.println("[HARDWARE] Inter-ESP32 UART2 bridge online (RX2: IO16, TX2: IO17).");
}

// ============================================================================
// Loop
// ============================================================================
void loop() {
  // 1. Process Serial Commands (USB Backup)
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    process_command(cmd);
  }

  // 2. Process Camera Messages over Hardware UART2
  while (Serial2.available() > 0) {
    String cam_msg = Serial2.readStringUntil('\n');
    cam_msg.trim();
    if (cam_msg.length() == 0) continue;

    last_cam_heartbeat_time = millis();
    cam_has_communicated = true;

    if (cam_msg.startsWith("CAM_IP:")) {
      last_known_cam_ip = cam_msg.substring(7);
      Serial.printf("[SYNC] Camera IP: %s\n", last_known_cam_ip.c_str());
      if (deviceConnected && pTxCharacteristic) {
        String notif = "CAM_IP:" + last_known_cam_ip + "\n";
        pTxCharacteristic->setValue((uint8_t*)notif.c_str(), notif.length());
        pTxCharacteristic->notify();
      }
    } else {
      Serial.printf("[CAM_RAW] %s\n", cam_msg.c_str());
    }
  }

  unsigned long now = millis();

  // 3. Camera Freeze Watchdog Supervisor
  // If camera was once alive and stops responding for >8 seconds, trigger automatic unfreeze reboot
  if (cam_has_communicated && (now - last_cam_heartbeat_time > 8000) && (now - last_cam_reboot_attempt > 10000)) {
    last_cam_reboot_attempt = now;
    Serial.println("[SUPERVISOR] Camera silence detected (>8s). Pulsing REBOOT command over UART2...");
    Serial2.println("REBOOT");
    if (deviceConnected && pTxCharacteristic) {
      String notif = "CAM_STATUS:FROZEN_REBOOTING\n";
      pTxCharacteristic->setValue((uint8_t*)notif.c_str(), notif.length());
      pTxCharacteristic->notify();
    }
  }

  // 4. Motion Fail-Safe Watchdog
  if (is_moving && (now - last_cmd_time > FAILSAFE_TIMEOUT_MS)) {
    stop_motors();
  }

  // 5. Perpetual BLE Advertising Maintenance & Reconnection
  static unsigned long last_adv_maintenance = 0;
  if (!deviceConnected) {
    if (now - last_adv_maintenance >= 2500) {
      last_adv_maintenance = now;
      pServer->startAdvertising();
    }
  }
  if (!deviceConnected && oldDeviceConnected) {
    delay(100);
    pServer->startAdvertising();
    Serial.println("[BLE] Client disconnected. Restarted advertising.");
    oldDeviceConnected = deviceConnected;
  }
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = deviceConnected;
    Serial.println("[BLE] Client connected.");
    // Automatically transmit latest known camera IP to newly connected controller
    if (last_known_cam_ip.length() > 0 && pTxCharacteristic) {
      String notif = "CAM_IP:" + last_known_cam_ip + "\n";
      pTxCharacteristic->setValue((uint8_t*)notif.c_str(), notif.length());
      pTxCharacteristic->notify();
    }
  }

  delay(2);
}
