/**
 * ============================================================================
 * ESP32-CAM Ultra-Low-Latency UDP Live Video Streamer & P2P Engine
 * Project: PetVision
 * Board: AI Thinker ESP32-CAM (OV2640 + 4MB External PSRAM)
 * 
 * High-Performance Zero-Overhead Architecture:
 *  - 100% Dedicated to Camera DMA and UDP Sockets (Zero HTTP Server Overhead)
 *  - 8-Byte Micro-Header with capture_time_ms for True Glass-to-Glass Latency
 *  - Dynamic P2P Target Auto-Discovery (Streams directly to sender of PING/Control)
 *  - Real-Time Hardware RSSI & Diagnostics Telemetry over UDP
 *  - Automated Wi-Fi & Sensor DMA Watchdogs (Auto-reboot on link or bus hang)
 * ============================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <esp_wifi.h>
#include <lwip/sockets.h>
#include <lwip/netdb.h>
#include "esp_timer.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ============================================================================
// Network Configuration
// ============================================================================
const char* WIFI_SSID     = "test_1";
const char* WIFI_PASSWORD = "12345678";

#define UDP_STREAM_PORT   5000
#define UDP_CHUNK_SIZE    1400

// ============================================================================
// AI-Thinker ESP32-CAM Pin Configuration
// ============================================================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// Hardware Pins
#define FLASH_LED_PIN      4   // High-power illumination LED
#define STATUS_LED_PIN    33   // Small onboard red LED (Active LOW)

// Flash LED PWM configuration
#define LEDC_FLASH_CHANNEL 7
#define LEDC_FLASH_FREQ    5000
#define LEDC_FLASH_RES     8

// ============================================================================
// 8-Byte Ultra-Lean Frame Packet Header (Timestamped for True Latency)
// ============================================================================
struct __attribute__((packed)) FastPacketHeader {
  uint16_t frame_id;        // Rolling frame counter (0 - 65535)
  uint8_t  part_id;         // Chunk index (0, 1, 2...)
  uint8_t  total_parts;     // Total chunks in this frame
  uint32_t capture_time_ms; // esp_timer_get_time() / 1000
};

// Global State
int udp_sock = -1;
struct sockaddr_in udp_target_addr;
bool target_discovered = false;
IPAddress default_target_ip(192, 168, 137, 1);

int current_light_value = 0;
int current_framesize   = FRAMESIZE_VGA;
int current_quality     = 20;
volatile bool streaming_enabled = true;
uint16_t global_frame_counter = 0;

// Reconnection & Watchdog Timers
unsigned long last_wifi_check = 0;
unsigned long disconnect_timestamp = 0;
int consecutive_fb_fails = 0;
volatile unsigned long last_frame_success_time = 0;

// ============================================================================
// Flashlight Control Helpers
// ============================================================================
void set_flash_light(int val) {
  if (val < 0) val = 0;
  if (val > 255) val = 255;
  current_light_value = val;
  
  #if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(FLASH_LED_PIN, current_light_value);
  #else
    ledcWrite(LEDC_FLASH_CHANNEL, current_light_value);
  #endif
}

// ============================================================================
// Socket Initialization Helper
// ============================================================================
bool init_udp_socket() {
  if (udp_sock >= 0) {
    close(udp_sock);
    udp_sock = -1;
  }

  udp_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
  if (udp_sock < 0) {
    Serial.println("[UDP] Socket creation failed");
    return false;
  }

  int sndbuf = 32768;
  setsockopt(udp_sock, SOL_SOCKET, SO_SNDBUF, &sndbuf, sizeof(sndbuf));
  int rcvbuf = 4096;
  setsockopt(udp_sock, SOL_SOCKET, SO_RCVBUF, &rcvbuf, sizeof(rcvbuf));

  // Enable non-blocking I/O
  int flags = fcntl(udp_sock, F_GETFL, 0);
  fcntl(udp_sock, F_SETFL, flags | O_NONBLOCK);

  // Bind to port 5000 for bi-directional P2P control & streaming
  struct sockaddr_in local_addr;
  memset(&local_addr, 0, sizeof(local_addr));
  local_addr.sin_family = AF_INET;
  local_addr.sin_addr.s_addr = INADDR_ANY;
  local_addr.sin_port = htons(UDP_STREAM_PORT);

  if (bind(udp_sock, (struct sockaddr *)&local_addr, sizeof(local_addr)) < 0) {
    Serial.println("[UDP] Bind failed");
    close(udp_sock);
    udp_sock = -1;
    return false;
  }

  Serial.println("[UDP] Non-blocking BSD socket ready on port 5000");
  return true;
}

// ============================================================================
// High-Speed UDP Streaming Task (Pinned to Core 1)
// ============================================================================
void udp_stream_task(void *pvParameters) {
  uint8_t packet_buffer[sizeof(FastPacketHeader) + UDP_CHUNK_SIZE];
  FastPacketHeader *hdr = (FastPacketHeader *)packet_buffer;
  uint8_t *payload = packet_buffer + sizeof(FastPacketHeader);

  Serial.println("[UDP] Streamer online on Core 1");

  while (true) {
    // 1. Process incoming reverse UDP commands & PINGs
    if (udp_sock >= 0) {
      struct sockaddr_in from_addr;
      socklen_t from_len = sizeof(from_addr);
      uint8_t cmd_buf[32];

      int len = recvfrom(udp_sock, cmd_buf, sizeof(cmd_buf), 0,
                         (struct sockaddr *)&from_addr, &from_len);

      if (len > 0) {
        // Auto-adopt sender as active stream destination
        udp_target_addr = from_addr;
        target_discovered = true;

        // PING Heartbeat Packet: b"PING" + 4-byte server_timestamp
        if (len >= 8 && memcmp(cmd_buf, "PING", 4) == 0) {
          uint32_t server_ts;
          memcpy(&server_ts, cmd_buf + 4, 4);

          // Build PONG response (16 bytes)
          uint8_t pong_resp[16];
          memcpy(pong_resp, "PONG", 4);
          memcpy(pong_resp + 4, &server_ts, 4); // Echoed server timestamp

          uint32_t esp_ts = (uint32_t)(esp_timer_get_time() / 1000);
          memcpy(pong_resp + 8, &esp_ts, 4);    // Actual ESP32 timestamp

          pong_resp[12] = (int8_t)WiFi.RSSI();  // Real hardware RSSI (dBm)
          pong_resp[13] = (uint8_t)current_light_value;
          pong_resp[14] = (uint8_t)current_framesize;
          pong_resp[15] = (uint8_t)current_quality;

          sendto(udp_sock, pong_resp, sizeof(pong_resp), 0,
                 (struct sockaddr *)&from_addr, from_len);
        }
        // Flashlight command: b"L" + 1-byte value (0-255)
        else if (cmd_buf[0] == 'L' && len >= 2) {
          set_flash_light(cmd_buf[1]);
        }
        // Resolution command: b"R" + 1-byte framesize (0-13)
        else if (cmd_buf[0] == 'R' && len >= 2) {
          int val = cmd_buf[1];
          if (val >= 0 && val <= 13 && val != current_framesize) {
            streaming_enabled = false;
            vTaskDelay(pdMS_TO_TICKS(50));
            sensor_t *s = esp_camera_sensor_get();
            if (s != NULL) {
              s->set_framesize(s, (framesize_t)val);
              current_framesize = val;
            }
            vTaskDelay(pdMS_TO_TICKS(30));
            streaming_enabled = true;
          }
        }
        // Quality command: b"Q" + 1-byte quality (10-63)
        else if (cmd_buf[0] == 'Q' && len >= 2) {
          int val = cmd_buf[1];
          if (val >= 10 && val <= 63) {
            sensor_t *s = esp_camera_sensor_get();
            if (s != NULL) {
              s->set_quality(s, val);
              current_quality = val;
            }
          }
        }
      }
    }

    // 2. Stream video frame
    if (!streaming_enabled || udp_sock < 0 || WiFi.status() != WL_CONNECTED) {
      vTaskDelay(pdMS_TO_TICKS(30));
      continue;
    }

    uint32_t frame_start_ms = (uint32_t)(esp_timer_get_time() / 1000);

    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      consecutive_fb_fails++;
      if (consecutive_fb_fails > 25) {
        Serial.println("[CAM] Sensor DMA lockup detected. Resetting camera...");
        esp_camera_deinit();
        vTaskDelay(pdMS_TO_TICKS(100));
      }
      taskYIELD();
      continue;
    }
    consecutive_fb_fails = 0;
    last_frame_success_time = millis();

    uint16_t fid = global_frame_counter++;
    uint8_t total_parts = (fb->len + UDP_CHUNK_SIZE - 1) / UDP_CHUNK_SIZE;
    uint32_t capture_time = (uint32_t)(esp_timer_get_time() / 1000);

    // Direct hardware DMA to UDP socket
    for (uint8_t p = 0; p < total_parts; p++) {
      size_t offset = p * UDP_CHUNK_SIZE;
      size_t chunk_len = (offset + UDP_CHUNK_SIZE <= fb->len) ? UDP_CHUNK_SIZE : (fb->len - offset);

      hdr->frame_id        = fid;
      hdr->part_id         = p;
      hdr->total_parts     = total_parts;
      hdr->capture_time_ms = capture_time;

      memcpy(payload, fb->buf + offset, chunk_len);

      int res = sendto(udp_sock, packet_buffer, sizeof(FastPacketHeader) + chunk_len, 0,
                       (struct sockaddr *)&udp_target_addr, sizeof(udp_target_addr));
      if (res < 0) {
        vTaskDelay(pdMS_TO_TICKS(1));
      } else {
        delayMicroseconds(60); // 60µs hardware pacing for zero lwIP TX buffer drops
      }
    }

    esp_camera_fb_return(fb);

    // Controlled 10 FPS Pacing (100ms period):
    // Leaves 50-70ms of pure idle time per frame for Wi-Fi MAC layer and lwIP network stack
    uint32_t frame_elapsed = (uint32_t)(esp_timer_get_time() / 1000) - frame_start_ms;
    const uint32_t TARGET_PERIOD_MS = 100; // 10 FPS target
    if (frame_elapsed < TARGET_PERIOD_MS) {
      vTaskDelay(pdMS_TO_TICKS(TARGET_PERIOD_MS - frame_elapsed));
    } else {
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

// ============================================================================
// Camera Sensor Initialization
// ============================================================================
esp_err_t init_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    Serial.println("[CAM] PSRAM active. Dual-buffer DMA enabled.");
    config.frame_size   = (framesize_t)current_framesize;
    config.jpeg_quality = current_quality;
    config.fb_count     = 2;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("[CAM] SRAM fallback mode.");
    config.frame_size   = FRAMESIZE_QVGA;
    config.jpeg_quality = 20;
    config.fb_count     = 1;
    config.fb_location  = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] Init error: 0x%x\n", err);
    return err;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s != NULL) {
    s->set_brightness(s, 1);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 0);
    s->set_gain_ctrl(s, 1);
    s->set_agc_gain(s, 0);
    s->set_gainceiling(s, (gainceiling_t)0);
    s->set_bpc(s, 0);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 1);
    s->set_lenc(s, 1);
    s->set_hmirror(s, 0);
    s->set_vflip(s, 0);
    s->set_dcw(s, 1);
  }

  Serial.println("[CAM] Sensor ready");
  return ESP_OK;
}

// ============================================================================
// Inter-ESP32 Hardware UART Command & Telemetry Handler (GPIO 16/17 Sync)
// ============================================================================
unsigned long last_uart_sync_time = 0;

void handle_serial_commands() {
  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) continue;

    // Flashlight control: L <val> (0-255)
    if (cmd.startsWith("L ") || cmd.startsWith("l ") || cmd.equalsIgnoreCase("L") || cmd.equalsIgnoreCase("l")) {
      int val = 0;
      int sp = cmd.indexOf(' ');
      if (sp != -1) {
        val = cmd.substring(sp + 1).toInt();
      } else {
        val = (current_light_value > 0) ? 0 : 255;
      }
      set_flash_light(val);
      Serial.printf("CAM_ACK:LIGHT=%d\n", current_light_value);
    }
    // Resolution control: R <framesize> (0-13)
    else if (cmd.startsWith("R ") || cmd.startsWith("r ")) {
      int val = cmd.substring(2).toInt();
      if (val >= 0 && val <= 13 && val != current_framesize) {
        streaming_enabled = false;
        vTaskDelay(pdMS_TO_TICKS(40));
        sensor_t *s = esp_camera_sensor_get();
        if (s != NULL) {
          s->set_framesize(s, (framesize_t)val);
          current_framesize = val;
        }
        streaming_enabled = true;
        Serial.printf("CAM_ACK:RES=%d\n", current_framesize);
      }
    }
    // Quality control: Q <val> (10-63)
    else if (cmd.startsWith("Q ") || cmd.startsWith("q ")) {
      int val = cmd.substring(2).toInt();
      if (val >= 10 && val <= 63) {
        sensor_t *s = esp_camera_sensor_get();
        if (s != NULL) {
          s->set_quality(s, val);
          current_quality = val;
          Serial.printf("CAM_ACK:QUAL=%d\n", current_quality);
        }
      }
    }
    // Query Camera IP: GET_IP
    else if (cmd.equalsIgnoreCase("GET_IP")) {
      if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("CAM_IP:%s\n", WiFi.localIP().toString().c_str());
      } else {
        Serial.println("CAM_IP:DISCONNECTED");
      }
    }
    // Heartbeat PING
    else if (cmd.equalsIgnoreCase("PING")) {
      Serial.printf("CAM_PONG:IP=%s,RSSI=%d,LIGHT=%d,RES=%d\n",
        WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "0.0.0.0",
        (int)WiFi.RSSI(),
        current_light_value,
        current_framesize);
    }
    // Reboot trigger
    else if (cmd.equalsIgnoreCase("REBOOT")) {
      Serial.println("CAM_ACK:REBOOTING");
      delay(100);
      esp_restart();
    }
  }
}

// ============================================================================
// Core 0 Dedicated Supervisor & UART Watchdog Task
// Pinned to Core 0: Completely immune to any I2S/DMA freezes on Core 1!
// ============================================================================
void core0_supervisor_task(void *pvParameters) {
  while (true) {
    // 1. Process Hardware UART Commands from Main ESP32 / USB
    handle_serial_commands();

    unsigned long now = millis();

    // 2. Periodic Heartbeat to Main ESP32 (every 1.0s)
    if (now - last_uart_sync_time >= 1000) {
      last_uart_sync_time = now;
      if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("CAM_HEARTBEAT:IP=%s,RSSI=%d,FPS=10\n", WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
        Serial.printf("CAM_IP:%s\n", WiFi.localIP().toString().c_str());
      } else {
        Serial.println("CAM_HEARTBEAT:WIFI=DISCONNECTED");
      }
    }

    // 3. Camera Sensor DMA Freeze Watchdog:
    // If target discovered, streaming enabled, and > 5 seconds since last frame:
    if (target_discovered && streaming_enabled && last_frame_success_time > 0 && (now - last_frame_success_time > 5000)) {
      Serial.println("[WATCHDOG] Camera sensor capture stalled > 5s! Self-rebooting ESP32-CAM...");
      delay(50);
      esp_restart();
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

// ============================================================================
// Setup
// ============================================================================
void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  Serial.begin(115200);
  Serial.setTimeout(5); // Non-blocking ultra-fast serial read for inter-ESP32 sync
  delay(200);
  Serial.println("\n--- PetVision UDP Video Engine & Hardware UART Sync ---");

  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW); // ON during setup

  #if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcAttach(FLASH_LED_PIN, LEDC_FLASH_FREQ, LEDC_FLASH_RES);
  #else
    ledcSetup(LEDC_FLASH_CHANNEL, LEDC_FLASH_FREQ, LEDC_FLASH_RES);
    ledcAttachPin(FLASH_LED_PIN, LEDC_FLASH_CHANNEL);
  #endif
  set_flash_light(0);

  if (init_camera() != ESP_OK) {
    Serial.println("[FATAL] Camera init failed. Halting.");
    while (true) {
      digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN));
      delay(150);
    }
  }

  // Connect to Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_ps(WIFI_PS_NONE);
  WiFi.setTxPower(WIFI_POWER_17dBm); // 17dBm stabilizes current spikes on 5V rail
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(300);
    Serial.print(".");
    digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN));
    tries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    WiFi.setSleep(false);
    esp_wifi_set_ps(WIFI_PS_NONE);
    esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT40);

    digitalWrite(STATUS_LED_PIN, HIGH); // OFF indicates connected
    Serial.println("\n[WIFI] Connected!");
    Serial.printf("[WIFI] IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("CAM_IP:%s\n", WiFi.localIP().toString().c_str());

    // Default target: Gateway IP (Host PC Hotspot)
    IPAddress gw = WiFi.gatewayIP();
    memset(&udp_target_addr, 0, sizeof(udp_target_addr));
    udp_target_addr.sin_family = AF_INET;
    udp_target_addr.sin_port = htons(UDP_STREAM_PORT);
    udp_target_addr.sin_addr.s_addr = inet_addr(gw.toString().c_str());
    Serial.printf("[UDP] Default Gateway Target: %s:5000\n", gw.toString().c_str());

    init_udp_socket();
  } else {
    Serial.println("\n[WIFI] Initial connection attempt timed out, watchdog will retry in loop.");
  }

  // Launch Core 0 supervisor & UART sync task (immune to Core 1 DMA hangs)
  xTaskCreatePinnedToCore(
    core0_supervisor_task,
    "cam_sup",
    3072,
    NULL,
    1,
    NULL,
    0
  );

  // Launch Core 1 streaming task
  xTaskCreatePinnedToCore(
    udp_stream_task,
    "udp_stream",
    4096,
    NULL,
    2,
    NULL,
    1
  );
}

// ============================================================================
// Loop: System Reconnection & Wi-Fi Health Watchdog
// ============================================================================
void loop() {
  unsigned long now = millis();

  // 1. Wi-Fi Reconnection & Health Watchdog
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(STATUS_LED_PIN, LOW); // LED on indicates disconnected

    if (disconnect_timestamp == 0) {
      disconnect_timestamp = now;
      Serial.println("[WIFI] Link dropped! Starting clean auto-reconnect...");
      Serial.println("CAM_IP:DISCONNECTED");
    }

    // Fail-safe hardware restart if disconnected for > 25 seconds
    if (now - disconnect_timestamp > 25000) {
      Serial.println("[WATCHDOG] Wi-Fi lost for 25s. Executing fail-safe reboot...");
      esp_restart();
    }

    // Clean radio reset every 3 seconds
    if (now - last_wifi_check >= 3000) {
      last_wifi_check = now;
      Serial.print("[WIFI] Clean reconnecting to ");
      Serial.println(WIFI_SSID);
      WiFi.disconnect(true);
      WiFi.mode(WIFI_OFF);
      delay(50);
      WiFi.mode(WIFI_STA);
      WiFi.setSleep(false);
      esp_wifi_set_ps(WIFI_PS_NONE);
      WiFi.setTxPower(WIFI_POWER_17dBm);
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
  } else {
    // Wi-Fi is connected
    if (disconnect_timestamp != 0) {
      disconnect_timestamp = 0;
      digitalWrite(STATUS_LED_PIN, HIGH);
      Serial.println("[WIFI] Reconnected successfully!");
      Serial.printf("CAM_IP:%s\n", WiFi.localIP().toString().c_str());
      WiFi.setSleep(false);
      esp_wifi_set_ps(WIFI_PS_NONE);

      // Re-init target address if not dynamically learned
      if (!target_discovered) {
        IPAddress gw = WiFi.gatewayIP();
        udp_target_addr.sin_addr.s_addr = inet_addr(gw.toString().c_str());
      }
      if (udp_sock < 0) {
        init_udp_socket();
      }
    }
  }

  // 4. Socket Recovery Watchdog
  if (WiFi.status() == WL_CONNECTED && udp_sock < 0) {
    init_udp_socket();
  }

  // 5. Camera DMA Recovery Watchdog
  if (consecutive_fb_fails > 25) {
    Serial.println("[WATCHDOG] Camera sensor stuck. Attempting recovery...");
    init_camera();
    consecutive_fb_fails = 0;
  }

  delay(10); // 10ms loop allows 100Hz responsiveness for UART commands
}
