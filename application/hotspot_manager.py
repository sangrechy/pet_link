import json
import os
import sys
import atexit
import signal
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("petvision-hotspot")

SESSION_FILE = Path(__file__).resolve().parent / ".hotspot_session.json"

PS_WINRT_PREAMBLE = """
Add-Type -AssemblyName System.Runtime.WindowsRuntime
function Await-Action($asyncAction) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and 
        $_.GetParameters().Count -eq 1 -and 
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
    })[0]
    $task = $asTask.Invoke($null, @($asyncAction))
    $task.Wait()
}
function Await-Operation($asyncOp, $resultType) {
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and 
        $_.GetParameters().Count -eq 1 -and 
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
    $asTask = $asTaskGeneric.MakeGenericMethod(@($resultType))
    $task = $asTask.Invoke($null, @($asyncOp))
    $task.Wait()
    return $task.Result
}
[Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.TetheringWiFiBand, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime] | Out-Null

$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if (-not $profile) {
    Write-Error "No active network profile found to share."
    exit 1
}
$mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
"""

def run_ps(script: str) -> subprocess.CompletedProcess:
    full_script = PS_WINRT_PREAMBLE + "\n" + script
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", full_script],
        capture_output=True,
        text=True,
        check=True
    )

class HotspotSessionManager:
    def __init__(self, session_ssid: str = "test_1", session_pass: str = "12345678"):
        self.session_ssid = session_ssid
        self.session_pass = session_pass
        self.is_active = False
        self._registered = False

    def get_current_config(self) -> dict:
        """Dynamically reads current Windows Mobile Hotspot configuration."""
        ps_code = """
        $cfg = $mgr.GetCurrentAccessPointConfiguration()
        $out = @{
            Ssid = $cfg.Ssid
            Passphrase = $cfg.Passphrase
            Band = $cfg.Band.ToString()
            State = $mgr.TetheringOperationalState.ToString()
        }
        $out | ConvertTo-Json -Compress
        """
        proc = run_ps(ps_code)
        return json.loads(proc.stdout.strip())

    def start_session(self):
        """Snapshots live configuration, changes to session hotspot, and turns it ON."""
        # 1. Dynamically read live current Windows config
        current = self.get_current_config()
        logger.info(f"Dynamically detected current hotspot: SSID='{current['Ssid']}', Band='{current['Band']}', State='{current['State']}'")

        # Save snapshot to disk so even across unexpected exits we know what to restore
        if not SESSION_FILE.exists():
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
            logger.info(f"Saved session snapshot to {SESSION_FILE.name}")
        else:
            logger.warning("Found existing session snapshot from a prior run. Preserving original backup.")

        # 2. Configure session hotspot (2.4 GHz for ESP32-CAM)
        ps_config_and_start = f"""
        $cfg = $mgr.GetCurrentAccessPointConfiguration()
        $cfg.Ssid = "{self.session_ssid}"
        $cfg.Passphrase = "{self.session_pass}"
        $cfg.Band = [Windows.Networking.NetworkOperators.TetheringWiFiBand]::TwoPointFourGigahertz
        Await-Action ($mgr.ConfigureAccessPointAsync($cfg))
        
        $resType = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult]
        $res = Await-Operation ($mgr.StartTetheringAsync()) $resType
        Write-Output "Status: $($res.Status)"
        """
        logger.info(f"Activating temporary session hotspot '{self.session_ssid}' on 2.4 GHz...")
        res = run_ps(ps_config_and_start)
        logger.info(f"Mobile Hotspot Started: {res.stdout.strip()}")
        self.is_active = True

        if not self._registered:
            atexit.register(self.end_session)
            signal.signal(signal.SIGINT, self._sig_handler)
            signal.signal(signal.SIGTERM, self._sig_handler)
            self._registered = True

    def end_session(self):
        """Restores the exact dynamically captured snapshot and resets state."""
        if not SESSION_FILE.exists():
            logger.info("No active session snapshot to restore.")
            return

        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                original = json.load(f)

            orig_ssid = original.get("Ssid", "")
            orig_pass = original.get("Passphrase", "")
            orig_band = original.get("Band", "Auto")
            orig_state = original.get("State", "Off")

            logger.info(f"Restoring original hotspot configuration: SSID='{orig_ssid}', Band='{orig_band}', State='{orig_state}'...")

            ps_restore = f"""
            $cfg = $mgr.GetCurrentAccessPointConfiguration()
            $cfg.Ssid = "{orig_ssid}"
            $cfg.Passphrase = "{orig_pass}"
            $cfg.Band = [Windows.Networking.NetworkOperators.TetheringWiFiBand]::{orig_band}
            Await-Action ($mgr.ConfigureAccessPointAsync($cfg))

            $resType = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult]
            if ("{orig_state}" -eq "Off") {{
                Await-Operation ($mgr.StopTetheringAsync()) $resType | Out-Null
            }}
            """
            run_ps(ps_restore)
            logger.info("Hotspot configuration successfully restored.")
        except Exception as e:
            logger.error(f"Failed to restore original hotspot settings: {e}")
        finally:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink(missing_ok=True)
            self.is_active = False

    def _sig_handler(self, signum, frame):
        logger.info(f"Received exit signal ({signum}), closing session...")
        self.end_session()
        sys.exit(0)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    mgr = HotspotSessionManager()
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "start":
        mgr.start_session()
        print("\nSession Active! Press Enter or Ctrl+C to stop and restore...")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
        mgr.end_session()
    elif action == "stop":
        mgr.end_session()
    elif action == "status":
        cfg = mgr.get_current_config()
        print(json.dumps(cfg, indent=2))
