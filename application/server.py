"""
============================================================================
PetVision Unified Robotics & Vision Server
Unified Single Backend for ESP32-CAM (UDP Video) + Main ESP32 (Motion/Gimbal)
Includes:
 - Pure BSD Zero-Wait UDP Stream Reassembly Engine (Port 5000)
 - High-Speed WebSocket Live Stream (/ws/live) & Control (/ws/control)
 - Direct USB Serial to Main ESP32 (COM3 @ 115200) with Watchdog Keep-Alive
 - Native Embedded USB Joystick Thread (Pygame-ce 60Hz Polling)
 - Camera Controls: Light PWM, Snapshot Capture, Dynamic Resolution Switching
============================================================================
"""

import os
import sys
import time
import struct
import socket
import asyncio
import queue
import logging
import datetime
import threading
from typing import Optional, Set
from pathlib import Path

import bleak
from bleak import BleakClient, BleakScanner

from fastapi import FastAPI, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Silence pygame banner
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("petvision-unified-server")

app = FastAPI(title="PetVision Unified Robotics & Vision Server", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
SNAPSHOT_DIR = BASE_DIR / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)

def get_now_ms() -> int:
    return int(time.monotonic() * 1000) & 0xFFFFFFFF

# ============================================================================
# 1. Camera UDP Vision Pipeline State & Constants
# ============================================================================
class CamState:
    cam_ip: str = "192.168.137.75"
    light_level: int = 0
    is_connected: bool = False
    fps: float = 0.0
    frames_received: int = 0
    frames_dropped: int = 0
    last_frame_time: float = 0.0
    rtt_ms: float = 0.0
    frame_transit_ms: float = 0.0
    total_latency_ms: float = 0.0
    rssi: int = -50
    clock_offset_ms: float = 0.0
    last_pong_time: float = 0.0
    current_resolution: int = 8 # VGA default
    main_esp_online_via_cam: bool = False
    vflip: bool = True

cam_state = CamState()

# WebSocket client queues for zero-latency frame push
client_queues: Set[asyncio.Queue] = set()

# Latest assembled JPEG frame
latest_frame: Optional[bytes] = None
latest_frame_lock = threading.Lock()

# Event loop & UDP socket references
main_loop: Optional[asyncio.AbstractEventLoop] = None
udp_socket_ref: Optional[socket.socket] = None

# Micro-Header: uint16 frame_id, uint8 part_id, uint8 total_parts, uint32 capture_time_ms = 8 bytes
HEADER_FORMAT = "<HBBI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

RESOLUTION_STEPS = [5, 8, 9, 11]
RES_NAMES = {5: "QVGA (320x240)", 6: "CIF (400x296)", 8: "VGA (640x480)", 9: "SVGA (800x600)", 11: "HD (1280x720)"}

# ============================================================================
# 2. Camera UDP Receiver & Heartbeat Background Workers
# ============================================================================
def udp_receiver_worker():
    global latest_frame, main_loop, udp_socket_ref

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    except Exception:
        pass

    sock.bind(("0.0.0.0", 5000))
    sock.settimeout(0.5)
    udp_socket_ref = sock
    logger.info("UDP Vision Streamer listening on 0.0.0.0:5000 (Pure Zero-Wait Mode)")

    current_frame_id = None
    parts_map = {}
    expected_parts = 0
    current_capture_time = 0

    fps_counter = 0
    fps_timer = time.time()

    def emit_frame(raw_parts: dict, num_parts: int, cap_time: int, is_partial: bool):
        nonlocal fps_counter
        full_frame = bytearray()
        for pid in range(num_parts):
            part = raw_parts.get(pid)
            if part:
                full_frame.extend(part)

        if len(full_frame) < 150:
            return

        # Ensure JPEG ends with EOI (FF D9) so browser decodes partial or complete scanlines
        if not full_frame.endswith(b"\xff\xd9"):
            full_frame.extend(b"\xff\xd9")

        frame_bytes = bytes(full_frame)
        with latest_frame_lock:
            latest_frame = frame_bytes

        cam_state.frames_received += 1
        cam_state.last_frame_time = time.time()
        cam_state.is_connected = True
        fps_counter += 1

        # Glass-to-glass latency
        now_ms = get_now_ms()
        transit = max(1.0, float(now_ms - cap_time - cam_state.clock_offset_ms))
        cam_state.frame_transit_ms = round(transit, 1)
        cam_state.total_latency_ms = round(transit + (cam_state.rtt_ms / 2.0), 1)

        # Broadcast to connected WebSocket clients with 10-byte telemetry header
        # Flags byte (byte 9): 1 = partial live frame, 0 = complete frame
        telemetry_hdr = struct.pack(
            "<4sHHbB",
            b"PV01",
            int(min(65535, max(0, cam_state.total_latency_ms))),
            int(min(65535, max(0, cam_state.rtt_ms))),
            int(cam_state.rssi),
            1 if is_partial else 0
        )
        dispatch_frame(bytes(telemetry_hdr + frame_bytes))

    while True:
        try:
            packet, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except Exception as e:
            time.sleep(0.05)
            continue

        # 1. PONG Heartbeat packet (16 to 18 bytes)
        if len(packet) >= 16 and packet.startswith(b"PONG"):
            try:
                _, s_ts, esp_ts, rssi_val, light_val, fs_val, q_val = struct.unpack("<4sIIbBBB", packet[:16])
                now_ms = get_now_ms()
                rtt = max(1.0, float((now_ms - s_ts) & 0xFFFFFFFF))
                cam_state.rtt_ms = round(rtt, 1)
                cam_state.clock_offset_ms = now_ms - esp_ts - (rtt / 2.0)
                cam_state.rssi = int(rssi_val)
                cam_state.light_level = int(light_val)
                cam_state.current_resolution = int(fs_val)
                if len(packet) >= 17:
                    cam_state.main_esp_online_via_cam = bool(packet[16])
                if len(packet) >= 18:
                    cam_state.vflip = bool(packet[17])
                cam_state.last_pong_time = time.time()
                cam_state.is_connected = True
                if cam_state.cam_ip != addr[0]:
                    cam_state.cam_ip = addr[0]
                    logger.info(f"PONG heartbeat received: camera discovered at {addr[0]}")
            except Exception:
                pass
            continue

        if len(packet) <= HEADER_SIZE:
            continue

        if cam_state.cam_ip != addr[0]:
            cam_state.cam_ip = addr[0]
            logger.info(f"Active ESP32-CAM detected at {addr[0]}")

        frame_id, part_id, total_parts, capture_time_ms = struct.unpack(
            HEADER_FORMAT, packet[:HEADER_SIZE]
        )
        chunk = packet[HEADER_SIZE:]

        diff = (frame_id - current_frame_id) & 0xFFFF if current_frame_id is not None else 1
        is_newer = 0 < diff < 32768

        if current_frame_id is None or is_newer:
            if current_frame_id is not None and expected_parts > 0 and len(parts_map) < expected_parts:
                # Resilient Video Stream: User accepts partial/broken frames as long as it never freezes
                if 0 in parts_map and len(parts_map) >= max(1, expected_parts // 3):
                    emit_frame(parts_map, expected_parts, current_capture_time, is_partial=True)
                else:
                    cam_state.frames_dropped += 1
            current_frame_id = frame_id
            parts_map = {part_id: chunk}
            expected_parts = total_parts
            current_capture_time = capture_time_ms
        elif frame_id == current_frame_id:
            parts_map[part_id] = chunk

        if expected_parts > 0 and len(parts_map) == expected_parts:
            emit_frame(parts_map, expected_parts, current_capture_time, is_partial=False)
            current_frame_id = None
            parts_map.clear()
            expected_parts = 0

        now = time.time()
        if now - fps_timer >= 1.0:
            cam_state.fps = fps_counter / (now - fps_timer)
            fps_counter = 0
            fps_timer = now

def dispatch_frame(frame_bytes: bytes):
    for q in list(client_queues):
        if q.full():
            try:
                q.get_nowait()
            except Exception:
                pass
        try:
            q.put_nowait(frame_bytes)
        except Exception:
            pass

def udp_heartbeat_worker():
    while True:
        time.sleep(0.8)
        if udp_socket_ref:
            try:
                now_ms = get_now_ms()
                ping_pkt = b"PING" + struct.pack("<I", now_ms)
                if cam_state.cam_ip:
                    try:
                        udp_socket_ref.sendto(ping_pkt, (cam_state.cam_ip, 5000))
                    except Exception:
                        pass
                try:
                    udp_socket_ref.sendto(ping_pkt, ("192.168.137.255", 5000))
                except Exception:
                    pass
            except Exception:
                pass

# Start UDP streaming threads
threading.Thread(target=udp_receiver_worker, daemon=True).start()
threading.Thread(target=udp_heartbeat_worker, daemon=True).start()

# ============================================================================
# 3. Wireless Robot BLE Manager (PetVision-Robot Nordic UART Service)
# ============================================================================
BLE_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
BLE_RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
BLE_TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

class RobotBLEManager:
    def __init__(self, device_name: str = "PetVision-Robot"):
        self.device_name = device_name
        self.target_address: Optional[str] = None
        self.client: Optional[BleakClient] = None
        self.is_connected: bool = False
        self.connection_type: str = "ble" # "ble" or "serial"
        self.connection_mode: str = "ble" # "ble" or "serial"
        self.port: str = f"{device_name} (BLE)"
        self.status_msg: str = "Initializing BLE..."

        # Serial connection fail-safe
        self.serial_conn = None
        self.serial_port: Optional[str] = None

        # Dynamic Car & Camera State
        self.car_speed: int = 220
        self.camera_speed: int = 6
        self.current_pan: int = 90
        self.current_tilt: int = 90
        self.last_cmd: str = "S"
        self.last_cmd_time: float = 0.0
        self.is_moving: bool = False

        # Joystick State
        self.joystick_connected: bool = False
        self.joystick_name: str = "None"

        # Inter-ESP Crosslink Telemetry
        self.last_cam_sync_time: float = 0.0
        self.cam_online_via_main: bool = False

        # Thread-safe queue for fast non-blocking command dispatch
        self.cmd_queue = queue.Queue(maxsize=100)
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Dedicated background thread with asyncio loop for WinRT BLE
        self.thread = threading.Thread(target=self._run_ble_thread, daemon=True, name="RobotBLEThread")
        self.thread.start()

    def _run_ble_thread(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._ble_worker_loop())

    def _handle_telemetry_msg(self, msg: str):
        try:
            if msg.startswith("CROSSLINK:"):
                self.last_cam_sync_time = time.time()
                pairs = dict(item.split("=") for item in msg.split(":", 1)[1].split(",") if "=" in item)
                self.cam_online_via_main = (pairs.get("CAM") == "1")
                ip = pairs.get("IP", "")
                if ip and ip not in ("0.0.0.0", "DISCONNECTED"):
                    cam_state.cam_ip = ip
            elif msg.startswith("CAM_IP:"):
                self.last_cam_sync_time = time.time()
                new_ip = msg.split(":", 1)[1].strip()
                if new_ip and new_ip not in ("DISCONNECTED", "0.0.0.0"):
                    cam_state.cam_ip = new_ip
                    self.cam_online_via_main = True
                    logger.info(f"[CAMERA_SYNC] Auto-discovered IP via Main ESP32 UART2 bridge: {new_ip}")
            elif msg.startswith("CAM_STATUS:"):
                if "OFFLINE" in msg:
                    self.cam_online_via_main = False
        except Exception as notif_e:
            logger.warning(f"[TELEMETRY] Parse error: {notif_e}")

    def _run_serial_reader(self):
        logger.info(f"[SERIAL] Background reader active on {self.serial_port}")
        while self.connection_mode == "serial" and self.serial_conn and self.serial_conn.is_open:
            try:
                line = self.serial_conn.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    time.sleep(0.01)
                    continue
                self._handle_telemetry_msg(line)
            except Exception as e:
                logger.warning(f"[SERIAL] Reader error: {e}")
                break
        if self.connection_mode == "serial":
            self.is_connected = False
            self.status_msg = "USB Serial Disconnected"

    def connect_serial(self, port: str = "COM3", baud: int = 115200) -> bool:
        """Switch to USB Serial mode for direct laptop connection fail-safe."""
        # Disconnect BLE if active
        if self.client and self.client.is_connected and self.loop:
            asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)

        self.connection_mode = "serial"
        self.connection_type = "serial"
        self.serial_port = port

        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

        try:
            import serial
            s = serial.Serial(port, baud, timeout=0.05)
            s.dtr = False
            s.rts = False
            self.serial_conn = s
            self.is_connected = True
            self.port = f"{port} (USB Serial)"
            self.status_msg = f"Connected via USB {port}"
            logger.info(f"[SERIAL] Successfully opened direct USB link on {port}")

            threading.Thread(target=self._run_serial_reader, daemon=True, name="RobotSerialThread").start()

            self.send_command("GET_CAM_IP")
            self.send_command("GET_CROSSLINK")
            return True
        except Exception as e:
            logger.error(f"[SERIAL] Failed to open {port}: {e}")
            self.status_msg = f"USB Serial error: {e}"
            self.is_connected = False
            return False

    def connect_ble(self, target: Optional[str] = None):
        """Switch to BLE mode and target specific MAC address or name."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

        self.connection_mode = "ble"
        self.connection_type = "ble"

        if target:
            target = target.strip()
            if (":" in target or "-" in target) and len(target) >= 12:
                self.target_address = target.upper()
                self.status_msg = f"Targeting MAC: {self.target_address}"
            else:
                self.device_name = target
                self.status_msg = f"Targeting Name: {self.device_name}"

        # Trigger immediate reconnect by disconnecting active client
        if self.client and self.client.is_connected and self.loop:
            asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
        return True

    def disconnect_all(self):
        """Disconnect both BLE and Serial."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

        if self.client and self.client.is_connected and self.loop:
            asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)

        self.is_connected = False
        self.status_msg = "Disconnected by user"

    async def _ble_worker_loop(self):
        while True:
            if self.connection_mode != "ble":
                await asyncio.sleep(0.5)
                continue

            try:
                target_mac = self.target_address
                target_name = self.device_name

                self.status_msg = f"Scanning for {target_mac or target_name}..."
                device = None

                # 1. Target MAC address specified
                if target_mac:
                    try:
                        device = await BleakScanner.find_device_by_address(target_mac, timeout=3.5)
                    except Exception:
                        pass

                    if not device:
                        devices = await BleakScanner.discover(timeout=3.0, return_adv=True)
                        for addr, (d, adv) in devices.items():
                            if addr.upper() == target_mac.upper():
                                device = d
                                break

                # 2. Target Name or fallback
                if not device:
                    device = await BleakScanner.find_device_by_name(target_name, timeout=3.5)
                    if not device:
                        devices = await BleakScanner.discover(timeout=3.0, return_adv=True)
                        for addr, (d, adv) in devices.items():
                            name = (d.name or adv.local_name or "").lower()
                            if "petvision" in name or "robot" in name:
                                device = d
                                self.target_address = addr
                                break

                if not device:
                    self.status_msg = f"Waiting for {target_mac or target_name}..."
                    await asyncio.sleep(2.0)
                    continue

                d_addr = getattr(device, "address", str(device))
                d_name = getattr(device, "name", target_name)
                self.status_msg = f"Connecting to {d_name} [{d_addr}]..."
                logger.info(f"[BLE] Found {d_name} [{d_addr}]. Connecting...")

                def on_disconnect(c):
                    logger.warning("[BLE] Robot disconnected!")
                    self.is_connected = False
                    self.client = None
                    self.status_msg = "Disconnected"

                client = BleakClient(device, disconnected_callback=on_disconnect, winrt={"use_cached_services": False})
                await client.connect(timeout=6.0)

                if client.is_connected:
                    self.client = client
                    self.is_connected = True
                    self.port = f"{d_name} ({d_addr})"
                    self.status_msg = f"Connected ({d_name})"
                    logger.info(f"[BLE] Successfully connected to {d_name} [{d_addr}] over BLE!")

                    def on_notification(sender, data: bytearray):
                        msg = data.decode("utf-8", errors="replace").strip()
                        self._handle_telemetry_msg(msg)

                    try:
                        await client.start_notify(BLE_TX_CHAR_UUID, on_notification)
                        logger.info("[BLE] Subscribed to robot TX notifications.")
                        await client.write_gatt_char(BLE_RX_CHAR_UUID, b"GET_CAM_IP\n", response=False)
                        await client.write_gatt_char(BLE_RX_CHAR_UUID, b"GET_CROSSLINK\n", response=False)
                    except Exception as sub_err:
                        logger.warning(f"[BLE] Could not subscribe to notifications: {sub_err}")

                    # Continuous command transmission & keep-alive loop
                    while self.is_connected and client.is_connected and self.connection_mode == "ble":
                        cmd_to_send = None
                        try:
                            cmd_to_send = self.cmd_queue.get_nowait()
                        except queue.Empty:
                            pass

                        now = time.time()
                        if cmd_to_send is None and self.is_moving and self.last_cmd != "S":
                            if now - self.last_cmd_time >= 0.18:
                                cmd_to_send = self.last_cmd

                        if cmd_to_send:
                            payload = (cmd_to_send.strip() + "\n").encode("utf-8")
                            try:
                                await client.write_gatt_char(BLE_RX_CHAR_UUID, payload, response=False)
                                self.last_cmd_time = time.time()
                            except Exception as write_err:
                                logger.error(f"[BLE] Write failed: {write_err}")
                                break

                        await asyncio.sleep(0.015)

            except Exception as e:
                logger.warning(f"[BLE] Connection error: {e}")
                self.is_connected = False
                self.client = None
                self.status_msg = f"Error: {e}"
                await asyncio.sleep(2.0)

    def send_command(self, cmd: str) -> bool:
        cmd_str = cmd.strip()
        if not cmd_str:
            return False

        self.last_cmd = cmd_str
        self.is_moving = (cmd_str != "S")

        # Track Pan/Tilt servo angles locally
        parts = cmd_str.split()
        if len(parts) >= 1:
            opcode = parts[0].upper()
            step = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else self.camera_speed
            if opcode == "U":
                self.current_tilt = max(10, self.current_tilt - step)
            elif opcode == "D":
                self.current_tilt = min(170, self.current_tilt + step)
            elif opcode == "A":
                self.current_pan = min(180, self.current_pan + step)
            elif opcode == "C":
                self.current_pan = max(0, self.current_pan - step)
            elif opcode == "H":
                self.current_pan = 90
                self.current_tilt = 90

        # If in direct USB Serial mode: write directly to hardware port
        if self.connection_mode == "serial" and self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write((cmd_str + "\n").encode("utf-8"))
                self.last_cmd_time = time.time()
                return True
            except Exception as write_err:
                logger.error(f"[SERIAL] Write failed: {write_err}")
                self.is_connected = False
                return False

        # If in BLE mode: enqueue for background thread
        if self.cmd_queue.qsize() > 4:
            try:
                while self.cmd_queue.qsize() > 1:
                    self.cmd_queue.get_nowait()
            except queue.Empty:
                pass

        try:
            self.cmd_queue.put_nowait(cmd_str)
            return True
        except queue.Full:
            return False

robot_mgr = RobotBLEManager(device_name="PetVision-Robot")

# ============================================================================
# 4. Embedded USB Joystick Controller (Pygame-ce 60 Hz Background Worker)
# ============================================================================
def joystick_worker():
    logger.info("Initializing embedded USB Joystick worker...")
    pygame.init()
    pygame.joystick.init()

    active_joystick: Optional[pygame.joystick.Joystick] = None
    prev_buttons = {}
    last_gimbal_time = 0.0
    deadzone_stick = 0.12
    deadzone_gimbal = 0.22

    while True:
        time.sleep(0.016) # ~60 Hz loop
        pygame.event.pump()

        count = pygame.joystick.get_count()
        if count == 0:
            if robot_mgr.joystick_connected:
                robot_mgr.joystick_connected = False
                robot_mgr.joystick_name = "None"
                active_joystick = None
                logger.info("USB Joystick disconnected.")
                robot_mgr.send_command("S")
            time.sleep(0.5)
            continue

        if active_joystick is None:
            try:
                active_joystick = pygame.joystick.Joystick(0)
                robot_mgr.joystick_connected = True
                robot_mgr.joystick_name = active_joystick.get_name()
                logger.info(f"Attached to physical Joystick: {robot_mgr.joystick_name} ({active_joystick.get_numaxes()} axes, {active_joystick.get_numbuttons()} buttons, {active_joystick.get_numhats()} hats)")
            except Exception as e:
                time.sleep(0.5)
                continue

        now = time.time()

        # ---------------------------------------------------------------------
        # 1. BUTTON PRESSES (Edge-Triggered)
        # ---------------------------------------------------------------------
        num_buttons = active_joystick.get_numbuttons()
        for btn_id in range(min(12, num_buttons)):
            is_down = bool(active_joystick.get_button(btn_id))
            was_down = prev_buttons.get(btn_id, False)
            prev_buttons[btn_id] = is_down

            if is_down and not was_down:
                # Right Button 1 (BUTTON_0): Light ON/OFF toggle
                if btn_id == 0:
                    toggle_flashlight()
                # Right Button 2 (BUTTON_1): Take snapshot
                elif btn_id == 1:
                    save_snapshot_disk()
                # Right Button 3 (BUTTON_2): Increase resolution
                elif btn_id == 2:
                    change_resolution_step(+1)
                # Right Button 4 (BUTTON_3): Decrease resolution
                elif btn_id == 3:
                    change_resolution_step(-1)
                # Upper-Left 1 (BUTTON_4): Decrease CAR speed
                elif btn_id == 4:
                    robot_mgr.car_speed = max(100, robot_mgr.car_speed - 20)
                    logger.info(f"[JOYSTICK] Car Speed: {robot_mgr.car_speed}")
                # Upper-Right 1 (BUTTON_5): Increase CAR speed
                elif btn_id == 5:
                    robot_mgr.car_speed = min(255, robot_mgr.car_speed + 20)
                    logger.info(f"[JOYSTICK] Car Speed: {robot_mgr.car_speed}")
                # Upper-Left 2 (BUTTON_6): Decrease CAMERA speed
                elif btn_id == 6:
                    robot_mgr.camera_speed = max(1, robot_mgr.camera_speed - 1)
                    logger.info(f"[JOYSTICK] Camera Speed: {robot_mgr.camera_speed}")
                # Upper-Right 2 (BUTTON_7): Increase CAMERA speed
                elif btn_id == 7:
                    robot_mgr.camera_speed = min(15, robot_mgr.camera_speed + 1)
                    logger.info(f"[JOYSTICK] Camera Speed: {robot_mgr.camera_speed}")
                # Button 11 (BUTTON_11): Camera Center (Home Pan/Tilt Servos to 90°/90°)
                elif btn_id == 11:
                    robot_mgr.current_pan = 90
                    robot_mgr.current_tilt = 90
                    robot_mgr.send_command("H")
                    logger.info("[JOYSTICK] Button 11: Camera Centered (90°/90°)")

        # ---------------------------------------------------------------------
        # 2. CAR MOVEMENT & BRAKING (Left Stick & D-Pad)
        # ---------------------------------------------------------------------
        hat_x, hat_y = (0, 0)
        if active_joystick.get_numhats() > 0:
            hat_x, hat_y = active_joystick.get_hat(0)

        raw_x = active_joystick.get_axis(0) if active_joystick.get_numaxes() > 0 else 0.0
        raw_y = active_joystick.get_axis(1) if active_joystick.get_numaxes() > 1 else 0.0

        stick_x = raw_x if abs(raw_x) > deadzone_stick else 0.0
        stick_y = -raw_y if abs(raw_y) > deadzone_stick else 0.0

        target_cmd = None

        # Dedicated In-Place Rotation via D-Pad LEFT / RIGHT
        if hat_x == -1:
            target_cmd = f"L {robot_mgr.car_speed}"
        elif hat_x == 1:
            target_cmd = f"R {robot_mgr.car_speed}"
        elif abs(stick_y) > 0.0:
            # High-Efficiency 4WD Skid-Steer Kinematics (Overcomes Tire Scrub)
            # - Point Front: Drives straight forward with maximum traction (Left = Right = base_speed)
            # - Point Front + Steering: Outer wheel receives dynamic torque boost (+35% * steer) to pull chassis;
            #   Inner wheel smoothly and proportionally decelerates (factor = 1.0 - 2.0 * steer_mag),
            #   reaching 0 at 50% stick (pivot turn), and actively counter-rotating in reverse > 50%
            #   to break 4WD tire scrub effortlessly!
            throttle = stick_y # positive = forward, negative = backward
            base_speed = throttle * robot_mgr.car_speed
            steer = stick_x
            steer_mag = abs(steer)

            # 1. Dynamic Outer Wheel Torque Boost (pulls chassis around turning arc)
            boost = int(steer_mag * 0.35 * robot_mgr.car_speed)
            if throttle > 0:
                outer_spd = min(255, int(base_speed + boost))
            else:
                outer_spd = max(-255, int(base_speed - boost))

            # 2. Continuous Linear Inner Wheel Deceleration & Counter-Rotation Curve
            # Smoothly drops from 100% (steer=0) -> 0% (steer=0.5) -> -100% (steer=1.0)
            inner_factor = 1.0 - (steer_mag * 2.0)
            inner_spd = int(base_speed * inner_factor)
            inner_spd = max(-255, min(255, inner_spd))

            if stick_x < 0:
                # Turning LEFT: Left is inner (slowed/reversed), Right is outer (boosted)
                left_spd = inner_spd
                right_spd = outer_spd
            elif stick_x > 0:
                # Turning RIGHT: Right is inner (slowed/reversed), Left is outer (boosted)
                left_spd = outer_spd
                right_spd = inner_spd
            else:
                # Straight forward / backward
                left_spd = int(base_speed)
                right_spd = int(base_speed)

            # D-Pad UP: Front Wheels Brake (1) | D-Pad DOWN: Back Wheels Brake (2)
            if hat_y == 1:
                target_cmd = f"MB {left_spd} {right_spd} 1"
            elif hat_y == -1:
                target_cmd = f"MB {left_spd} {right_spd} 2"
            else:
                target_cmd = f"M {left_spd} {right_spd}"

        elif abs(stick_x) > 0.0:
            # High-Torque Zero-Radius In-Place Spin (when throttle stick is centered)
            steer_mag = abs(stick_x)
            spin_spd = int(steer_mag * robot_mgr.car_speed * 0.90)
            spin_spd = max(110, min(255, spin_spd)) # Minimum 110 PWM ensures enough torque to overcome static friction
            if stick_x < 0:
                target_cmd = f"M {-spin_spd} {spin_spd}"
            else:
                target_cmd = f"M {spin_spd} {-spin_spd}"
        else:
            target_cmd = "S"

        if target_cmd != robot_mgr.last_cmd:
            robot_mgr.send_command(target_cmd)

        # ---------------------------------------------------------------------
        # 3. CAMERA GIMBAL (Right Stick AXIS_2 & AXIS_3)
        # ---------------------------------------------------------------------
        rx = active_joystick.get_axis(2) if active_joystick.get_numaxes() > 2 else 0.0
        ry = active_joystick.get_axis(3) if active_joystick.get_numaxes() > 3 else 0.0

        if now - last_gimbal_time >= 0.08:
            if abs(rx) > deadzone_gimbal or abs(ry) > deadzone_gimbal:
                if abs(rx) > deadzone_gimbal:
                    pan_step = max(1, int(abs(rx) * robot_mgr.camera_speed))
                    pan_cmd = f"A {pan_step}" if rx < 0 else f"C {pan_step}"
                    robot_mgr.send_command(pan_cmd)

                if abs(ry) > deadzone_gimbal:
                    tilt_step = max(1, int(abs(ry) * robot_mgr.camera_speed))
                    tilt_cmd = f"U {tilt_step}" if ry < 0 else f"D {tilt_step}"
                    robot_mgr.send_command(tilt_cmd)

                last_gimbal_time = now

# Start Joystick Thread
threading.Thread(target=joystick_worker, daemon=True).start()

# ============================================================================
# 5. Camera Control Action Helpers
# ============================================================================
def send_cam_udp_packet(pkt: bytes):
    if udp_socket_ref:
        for _ in range(2):
            try:
                if cam_state.cam_ip:
                    udp_socket_ref.sendto(pkt, (cam_state.cam_ip, 5000))
                udp_socket_ref.sendto(pkt, ("192.168.137.255", 5000))
            except Exception:
                pass

def toggle_flashlight():
    target = 0 if cam_state.light_level > 0 else 255
    cam_state.light_level = target
    send_cam_udp_packet(b"L" + bytes([target]))
    # Route through hardware UART2 bridge on Main ESP32 for instant <1ms sync
    robot_mgr.send_command(f"LIGHT {target}")
    logger.info(f"[CAMERA] Flashlight toggled: {'ON' if target > 0 else 'OFF'}")

def change_resolution_step(step: int):
    curr = cam_state.current_resolution
    try:
        idx = RESOLUTION_STEPS.index(curr)
    except ValueError:
        idx = 1
    new_idx = max(0, min(len(RESOLUTION_STEPS) - 1, idx + step))
    new_res = RESOLUTION_STEPS[new_idx]
    cam_state.current_resolution = new_res
    send_cam_udp_packet(b"R" + bytes([new_res]))
    robot_mgr.send_command(f"CAM_R {new_res}")
    logger.info(f"[CAMERA] Resolution set to: {RES_NAMES.get(new_res, new_res)}")

def save_snapshot_disk():
    with latest_frame_lock:
        if latest_frame:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = SNAPSHOT_DIR / f"snapshot_{timestamp}.jpg"
            with open(file_path, "wb") as f:
                f.write(latest_frame)
            logger.info(f"[SNAPSHOT] Saved to {file_path} ({len(latest_frame)} bytes)")

# ============================================================================
# 6. WebSocket Endpoints
# ============================================================================
@app.on_event("startup")
async def on_startup():
    global main_loop
    main_loop = asyncio.get_running_loop()

@app.websocket("/ws/live")
async def websocket_live_stream(websocket: WebSocket):
    """Ultra-low-latency binary WebSocket endpoint delivering JPEG frames directly to HTML5 canvas."""
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    client_queues.add(q)

    async def sender():
        try:
            while True:
                frame_bytes = await q.get()
                await websocket.send_bytes(frame_bytes)
        except Exception:
            pass

    async def receiver():
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            pass

    sender_task = asyncio.create_task(sender())
    receiver_task = asyncio.create_task(receiver())

    try:
        await asyncio.wait([sender_task, receiver_task], return_when=asyncio.FIRST_COMPLETED)
    except Exception:
        pass
    finally:
        client_queues.discard(q)
        sender_task.cancel()
        receiver_task.cancel()

active_control_sockets: Set[WebSocket] = set()

@app.websocket("/ws/control")
async def websocket_robot_control(websocket: WebSocket):
    """Real-time bi-directional WebSocket for robot drive & gimbal commands."""
    await websocket.accept()
    active_control_sockets.add(websocket)
    logger.info("Web control client connected.")

    try:
        while True:
            cmd = await websocket.receive_text()
            if cmd:
                robot_mgr.send_command(cmd)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Control WebSocket error: {e}")
    finally:
        active_control_sockets.discard(websocket)

# ============================================================================
# 7. REST API Endpoints (Camera + Robot)
# ============================================================================
@app.get("/api/config")
async def get_config():
    return {
        "cam_ip": cam_state.cam_ip,
        "is_connected": cam_state.is_connected,
        "light_level": cam_state.light_level,
        "fps": round(cam_state.fps, 1),
        "latency_ms": cam_state.total_latency_ms,
        "rtt_ms": cam_state.rtt_ms,
        "rssi": cam_state.rssi,
        "frames_received": cam_state.frames_received,
        "frames_dropped": cam_state.frames_dropped,
        "resolution": cam_state.current_resolution
    }

class CamConfigRequest(BaseModel):
    cam_ip: str

@app.post("/api/config")
async def update_config(payload: CamConfigRequest):
    cleaned_ip = payload.cam_ip.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
    if not cleaned_ip:
        raise HTTPException(status_code=400, detail="Invalid IP address")
    cam_state.cam_ip = cleaned_ip
    return {"status": "ok", "cam_ip": cam_state.cam_ip}

@app.get("/api/resolution")
async def set_resolution(val: int = Query(..., ge=0, le=13)):
    cam_state.current_resolution = val
    send_cam_udp_packet(b"R" + bytes([val]))
    robot_mgr.send_command(f"CAM_R {val}")
    return {"status": "ok", "framesize": val}

@app.get("/api/quality")
async def set_quality(val: int = Query(..., ge=10, le=63)):
    send_cam_udp_packet(b"Q" + bytes([val]))
    robot_mgr.send_command(f"CAM_Q {val}")
    return {"status": "ok", "quality": val}

@app.get("/api/camera/reboot")
async def reboot_camera():
    send_cam_udp_packet(b"REBOOT")
    robot_mgr.send_command("CAM_REBOOT")
    logger.info("[CAMERA] Triggered reboot via UDP and Main ESP32 UART2 bridge.")
    return {"status": "ok", "message": "Reboot command dispatched to camera"}

@app.get("/api/light")
async def set_light(
    state: Optional[str] = Query(None),
    val: Optional[int] = Query(None, ge=0, le=255)
):
    if val is not None:
        target_val = val
    elif state is not None:
        if state.lower() == "toggle":
            target_val = 0 if cam_state.light_level > 0 else 255
        else:
            target_val = 255 if state.lower() in ["on", "1", "true"] else 0
    else:
        raise HTTPException(status_code=400, detail="Provide 'state' or 'val'")

    cam_state.light_level = target_val
    send_cam_udp_packet(b"L" + bytes([target_val]))
    robot_mgr.send_command(f"LIGHT {target_val}")
    return {"status": "ok", "light": target_val}

@app.get("/api/snapshot")
async def capture_snapshot():
    save_snapshot_disk()
    with latest_frame_lock:
        if latest_frame:
            return Response(content=latest_frame, media_type="image/jpeg")
    return Response(content=b"", status_code=503)

@app.get("/api/status")
async def get_camera_status():
    is_live_udp = (time.time() - cam_state.last_frame_time) < 3.0 or (time.time() - cam_state.last_pong_time) < 3.0
    cam_state.is_connected = is_live_udp

    return {
        "status": "online" if is_live_udp else "offline",
        "cam_ip": cam_state.cam_ip,
        "is_connected": is_live_udp,
        "light": cam_state.light_level,
        "fps": round(cam_state.fps, 1),
        "latency_ms": cam_state.total_latency_ms,
        "rtt_ms": cam_state.rtt_ms,
        "rssi": cam_state.rssi,
        "frames_dropped": cam_state.frames_dropped,
        "frames_received": cam_state.frames_received,
        "resolution": cam_state.current_resolution
    }

# --- Robot Endpoints ---
class RobotCommandRequest(BaseModel):
    cmd: str

@app.post("/api/robot/command")
async def post_robot_command(payload: RobotCommandRequest):
    success = robot_mgr.send_command(payload.cmd)
    return {"status": "ok" if success else "failed", "cmd": payload.cmd}

@app.get("/api/robot/command")
async def get_robot_command(cmd: str = Query(...)):
    success = robot_mgr.send_command(cmd)
    return {"status": "ok" if success else "failed", "cmd": cmd}

@app.get("/api/robot/status")
async def get_robot_status():
    return {
        "connected": robot_mgr.is_connected,
        "connection_type": robot_mgr.connection_type,
        "connection_mode": robot_mgr.connection_mode,
        "status_msg": robot_mgr.status_msg,
        "target_address": robot_mgr.target_address,
        "device_name": robot_mgr.device_name,
        "port": robot_mgr.port,
        "car_speed": robot_mgr.car_speed,
        "camera_speed": robot_mgr.camera_speed,
        "pan": robot_mgr.current_pan,
        "tilt": robot_mgr.current_tilt,
        "last_cmd": robot_mgr.last_cmd,
        "is_moving": robot_mgr.is_moving,
        "joystick": {
            "connected": robot_mgr.joystick_connected,
            "name": robot_mgr.joystick_name
        }
    }

# --- Connection Management Endpoints (Manual BLE + USB Serial Fail-Safe) ---
class BLEConnectRequest(BaseModel):
    target: str

@app.get("/api/ble/scan")
async def scan_ble_devices():
    """Scans for nearby BLE devices and returns list with robot recognition."""
    try:
        devices = await BleakScanner.discover(timeout=3.5, return_adv=True)
        results = []
        for addr, (d, adv) in devices.items():
            name = d.name or adv.local_name or "Unknown Device"
            rssi = adv.rssi if hasattr(adv, "rssi") else 0
            is_robot = ("petvision" in name.lower() or "robot" in name.lower() or addr.upper() == "70:4B:CA:83:A8:EE")
            results.append({
                "address": addr,
                "name": name,
                "rssi": rssi,
                "is_robot": is_robot
            })
        results.sort(key=lambda x: (not x["is_robot"], -x["rssi"]))
        return {"status": "ok", "devices": results}
    except Exception as e:
        logger.warning(f"[BLE_SCAN] Scan failed: {e}")
        return {"status": "error", "message": str(e), "devices": []}

@app.post("/api/ble/connect")
async def connect_ble_device(payload: BLEConnectRequest):
    target = payload.target.strip()
    if not target:
        raise HTTPException(status_code=400, detail="Target MAC or device name required")
    success = robot_mgr.connect_ble(target)
    return {
        "status": "ok" if success else "failed",
        "target": target,
        "message": robot_mgr.status_msg
    }

@app.post("/api/ble/disconnect")
async def disconnect_robot_endpoint():
    robot_mgr.disconnect_all()
    return {"status": "ok", "message": "Robot disconnected"}

@app.get("/api/serial/ports")
async def get_serial_ports():
    ports = []
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            desc = p.description or ""
            ports.append({"port": p.device, "description": desc})
    except Exception:
        pass

    if not ports:
        import serial
        for i in range(1, 17):
            pname = f"COM{i}"
            try:
                s = serial.Serial(pname)
                s.close()
                ports.append({"port": pname, "description": f"Serial Port ({pname})"})
            except Exception:
                pass

    return {"status": "ok", "ports": ports}

class SerialConnectRequest(BaseModel):
    port: str = "COM3"
    baud: int = 115200

@app.post("/api/serial/connect")
async def connect_serial_device(payload: SerialConnectRequest):
    port = payload.port.strip()
    success = robot_mgr.connect_serial(port=port, baud=payload.baud)
    return {
        "status": "ok" if success else "failed",
        "port": port,
        "connected": robot_mgr.is_connected,
        "message": robot_mgr.status_msg
    }

@app.get("/api/camera/flip")
async def toggle_camera_flip(val: Optional[int] = Query(None)):
    target = (1 if val else 0) if val is not None else (0 if cam_state.vflip else 1)
    cam_state.vflip = bool(target)
    send_cam_udp_packet(b"P" + bytes([target]))
    robot_mgr.send_command(f"FLIP {target}")
    logger.info(f"[CAMERA] Orientation flip set to: {target}")
    return {"status": "ok", "vflip": target}

@app.get("/api/crosslink/status")
async def get_crosslink_status():
    is_live_udp = (time.time() - cam_state.last_frame_time) < 3.0 or (time.time() - cam_state.last_pong_time) < 3.0
    cam_state.is_connected = is_live_udp
    now = time.time()

    cam_online = is_live_udp or robot_mgr.cam_online_via_main
    main_online = robot_mgr.is_connected or cam_state.main_esp_online_via_cam
    uart_synced = cam_state.main_esp_online_via_cam or (now - robot_mgr.last_cam_sync_time < 4.5)

    last_hb_diff = None
    if cam_state.last_pong_time > 0 or robot_mgr.last_cam_sync_time > 0:
        last_hb_diff = round(now - max(cam_state.last_pong_time, robot_mgr.last_cam_sync_time), 1)

    return {
        "status": "ok",
        "timestamp": round(now, 2),
        "camera": {
            "online": cam_online,
            "ip": cam_state.cam_ip,
            "fps": round(cam_state.fps, 1),
            "latency_ms": cam_state.total_latency_ms,
            "rtt_ms": cam_state.rtt_ms,
            "rssi": cam_state.rssi,
            "frames_received": cam_state.frames_received,
            "frames_dropped": cam_state.frames_dropped,
            "vflip": cam_state.vflip,
            "light": cam_state.light_level,
            "resolution": cam_state.current_resolution
        },
        "main_esp": {
            "online": main_online,
            "ble_connected": robot_mgr.is_connected,
            "connection_mode": robot_mgr.connection_mode,
            "connection_type": robot_mgr.connection_type,
            "port": robot_mgr.port,
            "status_msg": robot_mgr.status_msg,
            "target_address": robot_mgr.target_address,
            "device_name": robot_mgr.device_name,
            "car_speed": robot_mgr.car_speed,
            "camera_speed": robot_mgr.camera_speed,
            "pan": robot_mgr.current_pan,
            "tilt": robot_mgr.current_tilt,
            "is_moving": robot_mgr.is_moving,
            "last_cmd": robot_mgr.last_cmd
        },
        "uart_bridge": {
            "synced": uart_synced,
            "cam_sees_main": cam_state.main_esp_online_via_cam,
            "main_sees_cam": robot_mgr.cam_online_via_main,
            "last_heartbeat_s": last_hb_diff
        },
        "joystick": {
            "connected": robot_mgr.joystick_connected,
            "name": robot_mgr.joystick_name
        }
    }

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
