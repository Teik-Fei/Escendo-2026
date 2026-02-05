import cv2
import numpy as np
import pytesseract
import re
import time
import requests
import serial
from collections import Counter
from picamera2 import Picamera2
from datetime import datetime, timedelta

# ==========================================
#             CONFIGURATION
# ==========================================

# SERIAL PORTS
SERIAL_PORT_MOTOR = "/dev/ttyACM0"   # Arduino Controller
MOTOR_BAUD_RATE = 115200

RFID_SERIAL_PORT = "/dev/ttyACM1"    # ESP32 RFID board ACM
RFID_BAUD_RATE = 115200

# SYSTEM SETTINGS
MAX_MEDS = 3
CHECK_INTERVAL = 10

# API SETTINGS
API_URL = "https://unpontifical-leanora-ungraphable.ngrok-free.dev/medication_tracker/index.php"
API_KEY = "SECRET123"

# OCR SETTINGS
NUM_FRAMES = 5
CONFIDENCE_THRESHOLD = 0.3
SAFE_DOSAGE = (1, 12)

DOSAGE_PATTERNS = [
    r"TAKE\s+(\d+|ONE|TWO|THREE|FOUR)\s+TABLET(S)?\s+EVERY\s+(\d+|FOUR|SIX|EIGHT|TWELVE)\s+HOUR(S)?",
    r"TAKE\s+(\d+|ONE|TWO|THREE|FOUR)\s+TABLET(S)?\s+(EVERY\s+DAY|DAILY|ONCE\s+DAILY)",
    r"(EVERY\s+DAY|DAILY)"
]
QTY_PATTERNS = [
    r"(?:QTY|QUANTITY|TOTAL)\s*[:.]?\s*(\d+)",
    r"(\d+)\s+(?:TAB|TABLET|CAP|CAPSULE)S?\b"
]

TESS_CONFIG = (
    "--oem 3 --psm 6 "
    "-c preserve_interword_spaces=1 "
    "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:/-. "
)

WORD_TO_NUM = {
    "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4,
    "SIX": 6, "EIGHT": 8, "TWELVE": 12, "TWENTY": 20, "THIRTY": 30
}
VALID_PILL_COUNTS = {1, 2, 3, 4}
VALID_INTERVAL_HOURS = {4, 6, 8, 12, 24}

# CAMERA (RFID TOGGLE CONTROL)
camera = None
camera_active = False

def start_camera():
    global camera
    if camera is not None:
        return
    camera = Picamera2()
    camera.configure(camera.create_still_configuration(main={"size": (2592, 1944)}))
    camera.start()
    print("Camera STARTED")

def stop_camera():
    global camera
    if camera is None:
        return
    try:
        camera.stop()
    except Exception:
        pass
    camera = None
    cv2.destroyAllWindows()
    print("Camera STOPPED")

def capture_frame():
    if camera is None:
        raise RuntimeError("Camera is not active. Tap RFID to activate.")
    frame = camera.capture_array()
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

# PART 0: RFID LISTENER

def open_rfid_serial():
    try:
        ser = serial.Serial(RFID_SERIAL_PORT, RFID_BAUD_RATE, timeout=1)
        time.sleep(2)  # allow board reset / serial settle
        print(f"🪪 RFID serial connected: {RFID_SERIAL_PORT} @ {RFID_BAUD_RATE}")
        return ser
    except Exception as e:
        raise RuntimeError(f"Could not open RFID serial {RFID_SERIAL_PORT}: {e}")

def wait_for_rfid_toggle(ser):
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue
        print(f"[RFID] {line}")
        if line == "RFID_TOGGLE":
            return

# PART 1: DISPENSER LOGIC

def send_serial_command(label, angle):
    try:
        with serial.Serial(SERIAL_PORT_MOTOR, MOTOR_BAUD_RATE, timeout=1) as ser:
            time.sleep(2)
            ser.write(f"{label}{angle}\n".encode())
            print(f"[Motor Serial] Sent: {label}{angle}")
    except serial.SerialException as e:
        print(f"[Motor Serial Error] Could not open {SERIAL_PORT_MOTOR}: {e}")

def dispense_pills(box_id, pills, medication_name):
    print(f"\nACTION: DISPENSING {pills} pill(s) from Box {box_id} ({medication_name})")

    angles = {1: 0, 2: 120, 3: 240}

    send_serial_command('D', angles.get(box_id, 0))
    time.sleep(1)

    for _ in range(pills):
        send_serial_command('C', 180)
        time.sleep(1)
        send_serial_command('C', 0)
        time.sleep(1)

    send_serial_command('D', 0)

    try:
        payload = {"box_id": box_id, "dispensed": pills}
        headers = {"X-API-KEY": API_KEY}
        r = requests.post(API_URL, json=payload, headers=headers, timeout=10)
        print(f"[API Sync] Server replied: {r.text}")
    except Exception as e:
        print(f"[API Error] Failed to sync dispense event: {e}")

# PART 2: OCR & SCANNING LOGIC
def preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    separated = cv2.dilate(thresh, kernel, iterations=1)
    return separated

def word_or_digit_to_int(token):
    token = token.upper()
    if token.isdigit():
        return int(token)
    return WORD_TO_NUM.get(token)

def semantic_check(pills, interval_hours):
    if pills not in VALID_PILL_COUNTS:
        return False
    if interval_hours not in VALID_INTERVAL_HOURS:
        return False
    # Example safety rule: max 8 pills/day
    if (pills * (24 // interval_hours)) > 8:
        return False
    return True

def extract_info(text):
    text = text.upper().replace("EVERY DAY", "DAILY")
    dosage_info = None
    quantity_info = None

    for pattern in DOSAGE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            matched_str = match.group(0)
            pills = 1
            words = matched_str.split()
            for w in words:
                val = word_or_digit_to_int(w)
                if val:
                    pills = val
                    break

            if "HOUR" in matched_str:
                nums = [word_or_digit_to_int(w) for w in words if word_or_digit_to_int(w) is not None]
                interval = nums[-1] if len(nums) >= 2 else 6
            else:
                interval = 24

            dosage_info = (pills, interval)
            break

    for pattern in QTY_PATTERNS:
        match = re.search(pattern, text)
        if match:
            qty = int(match.group(1))
            if 5 <= qty <= 200:
                quantity_info = qty
                break

    return dosage_info, quantity_info

def upload_med_data(med_id, scan_result):
    print(f"Uploading MED {med_id} to database...")

    pills_per_dose = scan_result["dosage"][0]
    total_qty = scan_result["quantity"]

    now = datetime.now()
    schedule_1_dt = now
    schedule_2_dt = schedule_1_dt + timedelta(seconds=120)
    time_fmt = "%H:%M:%S"

    payload = {
        "box_id": int(med_id),
        "medication_id": 0,
        "medication_name": f"MED {med_id}",
        "total_pills": int(total_qty),
        "pills_per_intake": int(pills_per_dose),
        "schedule_time_1": schedule_1_dt.strftime(time_fmt),
        "schedule_time_2": schedule_2_dt.strftime(time_fmt),
        "dispensed": 0
    }

    headers = {"X-API-KEY": API_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post(API_URL, json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"Upload Success! {r.text}")
            return True
        else:
            print(f"Upload Failed: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"Network Error: {e}")
        return False

def run_single_scan(med_index):
    print(f"\nScanning Label for MED {med_index}...")
    dosage_results = []
    qty_results = []

    for i in range(NUM_FRAMES):
        frame = capture_frame()
        processed = preprocess(frame)

        # Debug View
        scale = 0.3
        h, w = frame.shape[:2]
        dim = (int(w * scale), int(h * scale))
        debug_view = cv2.resize(cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR), dim)
        cv2.putText(debug_view, f"SCANNING MED {med_index}...", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow("Scanner", debug_view)
        cv2.waitKey(1)

        text = pytesseract.image_to_string(processed, config=TESS_CONFIG)
        dosage, qty = extract_info(text)

        if dosage and semantic_check(dosage[0], dosage[1]):
            dosage_results.append(dosage)
        if qty:
            qty_results.append(qty)

        time.sleep(0.2)

    final_dosage = SAFE_DOSAGE
    final_qty = 0
    status = "FAILED"

    if dosage_results:
        most_common, count = Counter(dosage_results).most_common(1)[0]
        if count / NUM_FRAMES >= CONFIDENCE_THRESHOLD:
            final_dosage = most_common
            status = "SUCCESS"
        else:
            status = "LOW_CONFIDENCE"

    if qty_results:
        final_qty = Counter(qty_results).most_common(1)[0][0]

    return {"dosage": final_dosage, "quantity": final_qty, "status": status}

# PHASE 1: SETUP MODE (RFID)

def run_setup_phase_rfid():
    global camera_active
    print("PHASE 1: SETUP MODE (RFID TOGGLE CAMERA)")
    print("Tap RFID once  -> camera ON + start scanning MED 1..N")
    print("Tap RFID again -> camera OFF + stop setup immediately")
    med_angles = {1: 0, 2: 120, 3: 240}
    rfid_ser = open_rfid_serial()

    try:
        # 1) Wait for FIRST tap: start session
        print("\nTap RFID to START setup session...")
        wait_for_rfid_toggle(rfid_ser)
        camera_active = True
        start_camera()
        rfid_ser.timeout = 0 

        for i in range(1, MAX_MEDS + 1):
            line = rfid_ser.readline().decode(errors="ignore").strip()
            if line == "RFID_TOGGLE":
                print("Stop tap detected. Ending setup session early.")
                break

            print(f"\nScanning MED {i}/{MAX_MEDS}...")
            target_angle = med_angles.get(i, 0)
            print(f"Aligning motor to {target_angle}° for MED {i}...")
            send_serial_command('D', target_angle)
            time.sleep(2)
            print("Scanning now...")
            result = run_single_scan(i)
            print(f"Scan result: {result}")
            upload_med_data(i, result)
            send_serial_command('D', 0)
            time.sleep(1)

        if camera_active:
            print("\nTap RFID to END setup session (camera OFF)...")
            rfid_ser.timeout = 1
            wait_for_rfid_toggle(rfid_ser)

        camera_active = False
        stop_camera()
        print("\nSETUP COMPLETE.")

    finally:
        try:
            rfid_ser.close()
        except Exception:
            pass
        camera_active = False
        stop_camera()
        send_serial_command('D', 0)

# PHASE 2: SCHEDULER MODE

def run_scheduler_phase():
    print("PHASE 2: SCHEDULER MODE (ACTIVE)")
    print("System is now checking server for dispense times...")
    last_min = -1
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M") 

        if now.minute != last_min:
            print(f"[{current_time}] Syncing schedule with server...")

            try:
                r = requests.get(API_URL + "?api=list", timeout=10)
                if not r.ok:
                    print(f"[API Error] Status {r.status_code}")
                else:
                    meds = r.json()

                    for m in meds:
                        if int(m.get("total_pills", 0)) <= 0:
                            continue

                        t1 = m.get("schedule_time_1")  # "14:30"
                        t2 = m.get("schedule_time_2")

                        if current_time == t1 or current_time == t2:
                            dispense_pills(
                                box_id=int(m["box_id"]),
                                pills=int(m["pills_per_intake"]),
                                medication_name=m["medication_name"]
                            )

            except Exception as e:
                print(f"[System Error] Loop failed: {e}")

            last_min = now.minute

        time.sleep(CHECK_INTERVAL)

# MAIN ENTRY POINT

if __name__ == "__main__":
    try:
        run_setup_phase_rfid()
        run_scheduler_phase()
    except KeyboardInterrupt:
        print("\nSystem Stopped by User.")
        stop_camera()
        cv2.destroyAllWindows()


