"""
PetVision Unified Server & Hotspot Session Launcher
"""

import sys
import time
import logging
import uvicorn
from hotspot_manager import HotspotSessionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("petvision-launcher")

def main():
    print("================================================================")
    print("           PETVISION ROBOTICS VISION SERVER                     ")
    print("================================================================")
    
    hotspot_mgr = HotspotSessionManager(session_ssid="test_1", session_pass="12345678")

    # Ask or auto-start session hotspot
    use_hotspot = True
    if len(sys.argv) > 1 and "--no-hotspot" in sys.argv:
        use_hotspot = False

    if use_hotspot:
        try:
            logger.info("Initializing dynamic temporary 2.4 GHz hotspot session...")
            hotspot_mgr.start_session()
            print("\n----------------------------------------------------------------")
            print("  >> TEMPORARY ROBOT HOTSPOT ONLINE <<")
            print("  SSID:       test_1")
            print("  Password:   12345678")
            print("  Band:       2.4 GHz (ESP32-CAM Compatible)")
            print("  Note: Your previous hotspot settings will be automatically")
            print("        restored when this server is stopped.")
            print("----------------------------------------------------------------\n")
        except Exception as e:
            logger.warning(f"Could not start automated hotspot: {e}")
            logger.info("Continuing server startup without automated hotspot...")

    print("Starting Web Console at: http://localhost:8000")
    print("Press CTRL+C anytime to stop server and restore previous Wi-Fi settings.\n")

    try:
        uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
    finally:
        if use_hotspot and hotspot_mgr.is_active:
            print("\nRestoring original Windows hotspot configuration...")
            hotspot_mgr.end_session()
            print("Restoration complete.")

if __name__ == "__main__":
    main()
