import time
from datetime import datetime

import camera_capture
import config
import n8n_client
import requests

# When person is detected
def person_detected() -> bool:
    # resp = requests.get(
    #     config.MERAKI_URL,
    #     headers={"X-Cisco-Meraki-API-Key": config.MERAKI_API_KEY},
    #     timeout=config.REQUEST_TIMEOUT,
    # )
    # resp.raise_for_status()
    # zones = resp.json()

    # full_frame = next((z for z in zones if z.get("zoneId") == "0"), None)
    # if full_frame is None:
    #     return False
    
    # avg = float(full_frame.get("averageCount", 0) or 0)
    # return avg > 0
    return True

# When it is within working hours
def within_working_hours() -> bool:
    hour = datetime.now().hour
    return config.WORK_START <= hour < config.WORK_END

def report_ppe(ppe: dict) -> None:
    missing = [n8n_client.PPE_NAMES[key] for key, worn in ppe.items() if not worn]

    if missing:
        print(f"[{datetime.now().strftime("%H:%M:%S")}] Person is missing: {', '.join(missing)}. Reporting to manager...")
    else:
        print(f"[{datetime.now().strftime("%H:%M:%S")}] All PPE present. Person is protected.")

def report_hazards(hazards: dict) -> None:
    found = [n8n_client.HAZARD_NAMES[key] for key, present in hazards.items() if present]
    if found:
        print(f"[{datetime.now().strftime("%H:%M:%S")}] Hazards near person: {', '.join(found)}. Reporting to manager IMMEDIATELY...")
    else:
        print(f"[{datetime.now().strftime("%H:%M:%S")}] No hazards detected.")

def main():
    print("Safety monitoring program initiated. Press Ctrl-C to end.")
    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")
            print("Looking for person...")

            if person_detected():
                try:
                    snapshot_path = camera_capture.capture_snapshot()
                    print(f"[{now}] Snapshot saved: {snapshot_path}")
                except Exception as e:
                    print(f"    ! Snapshot failed: {e}")

                if within_working_hours():
                    print(f"[{now}] Person detected -> running PPE check...")
                    try:
                        result = n8n_client.call_checks()
                        report_ppe(result["ppe"])
                        report_hazards(result["hazards"])
                    except Exception as e:
                        print(f"    ! Check failed: {e}")

                else:
                    print(f"[{now}] Person detected outside working hours. Reporting to manager...")
                    print("Checking for Hazards...")
                    hazards = n8n_client.call_hazards()
                    report_hazards(hazards)

            else:
                print(f"[{now}] No person detected.")

            time.sleep(config.SCAN_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nShutting down safety monitor. Goodbye.")


if __name__ == "__main__":
    main()