/**
 * PetVision Unified Cockpit Engine
 * Ultra-Low Latency Canvas Streaming + Real-Time Robotics Kinematics & Servos
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- UI Elements: Status Badges ---
  const joystickStatusBadge = document.getElementById("joystick-status-badge");
  const joystickStatusText  = document.getElementById("joystick-status-text");
  const robotStatusBadge    = document.getElementById("robot-status-badge");
  const robotStatusText     = document.getElementById("robot-status-text");
  const camStatusBadge      = document.getElementById("cam-status-badge");
  const camStatusText       = document.getElementById("cam-status-text");

  // --- UI Elements: Canvas & Viewport ---
  const canvas              = document.getElementById("live-canvas");
  const ctx                 = canvas.getContext("2d");
  const viewportContainer   = document.getElementById("viewport-container");
  const btnSnapshot         = document.getElementById("btn-snapshot");
  const btnQuickLight       = document.getElementById("btn-quick-light");
  const quickLightText      = document.getElementById("quick-light-text");
  const btnFullscreen       = document.getElementById("btn-fullscreen");
  const fpsVal              = document.getElementById("fps-val");
  const resBadge            = document.getElementById("res-badge");
  const latencyVal          = document.getElementById("latency-val");
  const hudRssiVal          = document.getElementById("hud-rssi-val");

  // --- UI Elements: Rover Motion ---
  const roverState          = document.getElementById("rover-state");
  const btnForward          = document.getElementById("btn-forward");
  const btnBackward         = document.getElementById("btn-backward");
  const btnLeft             = document.getElementById("btn-left");
  const btnRight            = document.getElementById("btn-right");
  const btnStop             = document.getElementById("btn-stop");
  const speedSlider         = document.getElementById("speed-slider");
  const speedVal            = document.getElementById("speed-val");

  // --- UI Elements: Gimbal Servos ---
  const panDisplay          = document.getElementById("pan-display");
  const tiltDisplay         = document.getElementById("tilt-display");
  const btnTiltUp           = document.getElementById("btn-tilt-up");
  const btnTiltDown         = document.getElementById("btn-tilt-down");
  const btnPanLeft          = document.getElementById("btn-pan-left");
  const btnPanRight         = document.getElementById("btn-pan-right");
  const btnHome             = document.getElementById("btn-home");
  const stepSlider          = document.getElementById("step-slider");
  const stepVal             = document.getElementById("step-val");

  // --- UI Elements: Camera Settings ---
  const resolutionSelect    = document.getElementById("resolution-select");
  const lightToggle         = document.getElementById("light-toggle");
  const lightSlider         = document.getElementById("light-slider");
  const lightBrightnessVal  = document.getElementById("light-brightness-val");
  const logLastCmd          = document.getElementById("log-last-cmd");

  // --- Dynamic State ---
  let motorSpeed = 220;
  let cameraStep = 6;
  let currentPan = 90;
  let currentTilt = 90;
  let activeDriveKey = null;
  let currentDriveCmd = null;
  let driveInterval = null;

  let liveWs = null;
  let controlWs = null;
  let reconnectTimer = null;

  let renderFrames = 0;
  let lastFpsCalc = performance.now();

  const resLabels = {
    "5": "QVGA (320x240)",
    "6": "CIF (400x296)",
    "8": "VGA (640x480)",
    "9": "SVGA (800x600)",
    "11": "HD (1280x720)"
  };

  // ==========================================================================
  // 1. Live Video Stream WebSocket (Binary Frames with PV01 Telemetry)
  // ==========================================================================
  function initLiveWebSocket() {
    if (liveWs) {
      try { liveWs.close(); } catch (e) {}
      liveWs = null;
    }

    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/live`;
    liveWs = new WebSocket(wsUrl);
    liveWs.binaryType = "blob";

    liveWs.onopen = () => {
      console.log("[VIDEO WS] Connected to live video pipeline.");
      camStatusBadge.className = "status-pill online";
      camStatusText.textContent = "CAM: LIVE";
    };

    liveWs.onmessage = async (event) => {
      try {
        const rawBlob = event.data;
        let imgBlob = rawBlob;

        // Parse 10-byte telemetry header: PV01 (4B) + total_lat (2B) + rtt (2B) + rssi (1B) + flags (1B)
        if (rawBlob.size > 10) {
          const headerSlice = await rawBlob.slice(0, 10).arrayBuffer();
          const magicBytes = new Uint8Array(headerSlice, 0, 4);
          const magic = String.fromCharCode(...magicBytes);

          if (magic === "PV01") {
            const dv = new DataView(headerSlice);
            const latency = dv.getUint16(4, true);
            const rssi = dv.getInt8(8);

            if (latencyVal) latencyVal.textContent = `${latency}`;
            if (hudRssiVal) hudRssiVal.textContent = `${rssi} dBm`;

            imgBlob = rawBlob.slice(10);
          }
        }

        // Hardware GPU decode directly to canvas ImageBitmap
        const bitmap = await createImageBitmap(imgBlob);

        if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
          canvas.width = bitmap.width;
          canvas.height = bitmap.height;
        }

        ctx.drawImage(bitmap, 0, 0);
        bitmap.close();

        // FPS calculation
        renderFrames++;
        const now = performance.now();
        if (now - lastFpsCalc >= 1000) {
          const fps = Math.round((renderFrames * 1000) / (now - lastFpsCalc));
          fpsVal.textContent = `${fps}`;
          renderFrames = 0;
          lastFpsCalc = now;
        }
      } catch (err) {
        // Zero-wait drop-loss policy
      }
    };

    liveWs.onerror = () => {
      camStatusBadge.className = "status-pill offline";
      camStatusText.textContent = "CAM: OFFLINE";
    };

    liveWs.onclose = () => {
      camStatusBadge.className = "status-pill offline";
      camStatusText.textContent = "CAM: RECONNECTING...";
      setTimeout(initLiveWebSocket, 1500);
    };
  }

  // ==========================================================================
  // 2. Real-Time Robot Control WebSocket & Command Dispatcher
  // ==========================================================================
  function initControlWebSocket() {
    if (controlWs) {
      try { controlWs.close(); } catch (e) {}
      controlWs = null;
    }

    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/control`;
    controlWs = new WebSocket(wsUrl);

    controlWs.onopen = () => {
      console.log("[CONTROL WS] Connected to robotics control engine.");
    };

    controlWs.onclose = () => {
      setTimeout(initControlWebSocket, 2000);
    };
  }

  function sendRobotCmd(cmd) {
    cmd = cmd.trim();
    if (logLastCmd) {
      logLastCmd.textContent = `${cmd} (${new Date().toLocaleTimeString()})`;
    }

    if (controlWs && controlWs.readyState === WebSocket.OPEN) {
      controlWs.send(cmd);
    } else {
      fetch(`/api/robot/command?cmd=${encodeURIComponent(cmd)}`).catch(() => {});
    }
  }

  // ==========================================================================
  // 3. Rover Driving Handlers (Hold-to-drive with 200ms Watchdog Heartbeat)
  // ==========================================================================
  function startDrive(action, cmd) {
    if (currentDriveCmd === cmd && driveInterval !== null) {
      return;
    }

    currentDriveCmd = cmd;
    roverState.textContent = action;

    if (driveInterval) {
      clearInterval(driveInterval);
    }

    // Send immediate command
    sendRobotCmd(`${cmd} ${motorSpeed}`);

    // Maintain 200ms heartbeat while moving to prevent ESP32 800ms watchdog stop
    driveInterval = setInterval(() => {
      if (currentDriveCmd) {
        sendRobotCmd(`${currentDriveCmd} ${motorSpeed}`);
      }
    }, 200);
  }

  function stopDrive() {
    if (driveInterval) {
      clearInterval(driveInterval);
      driveInterval = null;
    }

    if (currentDriveCmd !== null || roverState.textContent !== "IDLE") {
      currentDriveCmd = null;
      roverState.textContent = "IDLE";
      sendRobotCmd("S");
    }
  }

  function clearVisualDriveButtons() {
    btnForward.classList.remove("active");
    btnBackward.classList.remove("active");
    btnLeft.classList.remove("active");
    btnRight.classList.remove("active");
  }

  function bindHoldButton(btn, action, cmd) {
    const start = (e) => {
      e.preventDefault();
      clearVisualDriveButtons();
      btn.classList.add("active");
      startDrive(action, cmd);
    };
    const end = (e) => {
      e.preventDefault();
      btn.classList.remove("active");
      stopDrive();
    };

    btn.addEventListener("pointerdown", start);
    btn.addEventListener("pointerup", end);
    btn.addEventListener("pointerleave", end);
    btn.addEventListener("pointercancel", end);
  }

  bindHoldButton(btnForward, "FORWARD", "F");
  bindHoldButton(btnBackward, "BACKWARD", "B");
  bindHoldButton(btnLeft, "SPIN LEFT", "L");
  bindHoldButton(btnRight, "SPIN RIGHT", "R");

  btnStop.addEventListener("click", () => {
    clearVisualDriveButtons();
    stopDrive();
  });

  // ==========================================================================
  // 4. Gimbal Servo Handlers
  // ==========================================================================
  function flashButton(btn) {
    if (!btn) return;
    btn.classList.add("active");
    setTimeout(() => btn.classList.remove("active"), 120);
  }

  function nudgeTiltUp() {
    currentTilt = Math.max(10, currentTilt - cameraStep);
    tiltDisplay.textContent = `TILT: ${currentTilt}°`;
    sendRobotCmd(`U ${cameraStep}`);
  }

  function nudgeTiltDown() {
    currentTilt = Math.min(170, currentTilt + cameraStep);
    tiltDisplay.textContent = `TILT: ${currentTilt}°`;
    sendRobotCmd(`D ${cameraStep}`);
  }

  function nudgePanLeft() {
    currentPan = Math.min(180, currentPan + cameraStep);
    panDisplay.textContent = `PAN: ${currentPan}°`;
    sendRobotCmd(`A ${cameraStep}`);
  }

  function nudgePanRight() {
    currentPan = Math.max(0, currentPan - cameraStep);
    panDisplay.textContent = `PAN: ${currentPan}°`;
    sendRobotCmd(`C ${cameraStep}`);
  }

  function homeServos() {
    currentPan = 90;
    currentTilt = 90;
    panDisplay.textContent = `PAN: 90°`;
    tiltDisplay.textContent = `TILT: 90°`;
    sendRobotCmd("H");
  }

  btnTiltUp.addEventListener("click", () => { nudgeTiltUp(); flashButton(btnTiltUp); });
  btnTiltDown.addEventListener("click", () => { nudgeTiltDown(); flashButton(btnTiltDown); });
  btnPanLeft.addEventListener("click", () => { nudgePanLeft(); flashButton(btnPanLeft); });
  btnPanRight.addEventListener("click", () => { nudgePanRight(); flashButton(btnPanRight); });
  btnHome.addEventListener("click", () => { homeServos(); flashButton(btnHome); });

  // ==========================================================================
  // 5. Sliders & Controls
  // ==========================================================================
  speedSlider.addEventListener("input", () => {
    motorSpeed = parseInt(speedSlider.value, 10);
    const pct = Math.round((motorSpeed / 255) * 100);
    speedVal.textContent = `${motorSpeed} (${pct}%)`;
  });

  stepSlider.addEventListener("input", () => {
    cameraStep = parseInt(stepSlider.value, 10);
    stepVal.textContent = `${cameraStep}° per step`;
  });

  resolutionSelect.addEventListener("change", () => {
    const val = parseInt(resolutionSelect.value, 10);
    fetch(`/api/resolution?val=${val}`);
    resBadge.textContent = resLabels[val] || `Res ${val}`;
  });

  lightToggle.addEventListener("change", () => {
    const isChecked = lightToggle.checked;
    const val = isChecked ? 255 : 0;
    lightSlider.value = val;
    lightBrightnessVal.textContent = isChecked ? "100%" : "0%";
    quickLightText.textContent = isChecked ? "Light ON" : "Light OFF";
    fetch(`/api/light?val=${val}`);
  });

  lightSlider.addEventListener("input", () => {
    const val = parseInt(lightSlider.value, 10);
    const pct = Math.round((val / 255) * 100);
    lightBrightnessVal.textContent = `${pct}%`;
    lightToggle.checked = val > 0;
    quickLightText.textContent = val > 0 ? `Light ${pct}%` : "Light OFF";
    fetch(`/api/light?val=${val}`);
  });

  btnQuickLight.addEventListener("click", () => {
    lightToggle.checked = !lightToggle.checked;
    lightToggle.dispatchEvent(new Event("change"));
  });

  const btnCamReboot = document.getElementById("btn-cam-reboot");
  if (btnCamReboot) {
    btnCamReboot.addEventListener("click", () => {
      btnCamReboot.style.opacity = "0.6";
      btnCamReboot.querySelector("span").textContent = "REBOOTING CAMERA...";
      fetch("/api/camera/reboot")
        .then(() => {
          setTimeout(() => {
            btnCamReboot.style.opacity = "1";
            btnCamReboot.querySelector("span").textContent = "UNFREEZE / REBOOT CAMERA";
          }, 3000);
        })
        .catch(() => {
          btnCamReboot.style.opacity = "1";
          btnCamReboot.querySelector("span").textContent = "UNFREEZE / REBOOT CAMERA";
        });
    });
  }

  btnSnapshot.addEventListener("click", () => {
    fetch("/api/snapshot").then(res => {
      if (res.ok) {
        return res.blob();
      }
    }).then(blob => {
      if (blob) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `snapshot_${new Date().toISOString().replace(/[:.]/g, "-")}.jpg`;
        a.click();
        URL.revokeObjectURL(url);
      }
    }).catch(() => {});
  });

  btnFullscreen.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      viewportContainer.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen();
    }
  });

  // ==========================================================================
  // 6. Desktop Keyboard Driving
  // [W][A][S][D] -> Rover
  // [Arrows]     -> Pan/Tilt Servos
  // [Space]      -> Stop
  // [H]          -> Home
  // ==========================================================================
  window.addEventListener("keydown", (e) => {
    if (e.repeat) return;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;

    switch (e.code) {
      case "KeyW":
        activeDriveKey = "KeyW";
        clearVisualDriveButtons();
        btnForward.classList.add("active");
        startDrive("FORWARD", "F");
        break;
      case "KeyS":
        activeDriveKey = "KeyS";
        clearVisualDriveButtons();
        btnBackward.classList.add("active");
        startDrive("BACKWARD", "B");
        break;
      case "KeyA":
        activeDriveKey = "KeyA";
        clearVisualDriveButtons();
        btnLeft.classList.add("active");
        startDrive("SPIN LEFT", "L");
        break;
      case "KeyD":
        activeDriveKey = "KeyD";
        clearVisualDriveButtons();
        btnRight.classList.add("active");
        startDrive("SPIN RIGHT", "R");
        break;
      case "Space":
        clearVisualDriveButtons();
        stopDrive();
        break;
      case "ArrowUp":
        nudgeTiltUp();
        flashButton(btnTiltUp);
        break;
      case "ArrowDown":
        nudgeTiltDown();
        flashButton(btnTiltDown);
        break;
      case "ArrowLeft":
        nudgePanLeft();
        flashButton(btnPanLeft);
        break;
      case "ArrowRight":
        nudgePanRight();
        flashButton(btnPanRight);
        break;
      case "KeyH":
        homeServos();
        flashButton(btnHome);
        break;
    }
  });

  window.addEventListener("keyup", (e) => {
    if (["KeyW", "KeyS", "KeyA", "KeyD"].includes(e.code)) {
      if (activeDriveKey === e.code) {
        activeDriveKey = null;
        clearVisualDriveButtons();
        stopDrive();
      }
    }
  });

  // ==========================================================================
  // 7. Status Polling Worker (/api/robot/status & /api/status)
  // ==========================================================================
  async function pollStatus() {
    try {
      const res = await fetch("/api/robot/status");
      if (res.ok) {
        const data = await res.json();

        // Robot Wireless BLE Connection
        if (data.connected) {
          robotStatusBadge.className = "status-pill online";
          robotStatusText.textContent = `ROBOT: BLE (${data.device_name || "CONNECTED"})`;
        } else {
          robotStatusBadge.className = "status-pill offline";
          robotStatusText.textContent = "ROBOT: DISCONNECTED";
        }

        // Joystick
        if (data.joystick && data.joystick.connected) {
          joystickStatusBadge.className = "status-pill online";
          joystickStatusText.textContent = `JOYSTICK: ${data.joystick.name.toUpperCase()}`;
        } else {
          joystickStatusBadge.className = "status-pill offline";
          joystickStatusText.textContent = "NO JOYSTICK";
        }

        // Sync angles & speeds if changed by joystick
        if (data.pan !== undefined && data.pan !== currentPan) {
          currentPan = data.pan;
          panDisplay.textContent = `PAN: ${currentPan}°`;
        }
        if (data.tilt !== undefined && data.tilt !== currentTilt) {
          currentTilt = data.tilt;
          tiltDisplay.textContent = `TILT: ${currentTilt}°`;
        }
        if (data.car_speed !== undefined && data.car_speed !== motorSpeed) {
          motorSpeed = data.car_speed;
          speedSlider.value = motorSpeed;
          const pct = Math.round((motorSpeed / 255) * 100);
          speedVal.textContent = `${motorSpeed} (${pct}%)`;
        }
        if (data.camera_speed !== undefined && data.camera_speed !== cameraStep) {
          cameraStep = data.camera_speed;
          stepSlider.value = cameraStep;
          stepVal.textContent = `${cameraStep}° per step`;
        }
      }
    } catch (e) {}

    setTimeout(pollStatus, 1000);
  }

  // Initialize WebSockets and Polling
  initLiveWebSocket();
  initControlWebSocket();
  pollStatus();
});
