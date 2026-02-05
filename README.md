# 💊 Smart Medication Dispenser System

An automated medication dispensing system with RFID security, OCR label scanning, and web-based management dashboard built for Escendo 2026 Hackathon.

## 🎯 Project Overview

This system automates medication dispensing using a multi-compartment dispenser controlled by servo motors. It features:
- **RFID-based security** for authorized access
- **OCR label scanning** to automatically configure medication schedules
- **Scheduled dispensing** based on prescription requirements
- **Real-time inventory tracking** with low stock alerts
- **Web dashboard** for medication management

## 📁 Project Structure

```
├── RFID.ino           # ESP32 RFID access control firmware
├── access.py          # Medication scheduler with database integration
├── Med_dispenser.py   # OCR scanning + RFID-triggered setup mode
└── index.php          # Web dashboard for medication management
```

## 🔧 Hardware Requirements

### Electronics
- **ESP32 Development Board** (x2)
  - One for RFID access control
  - One for motor control
- **MFRC522 RFID Reader Module**
- **Servo Motors** (x2)
  - Divider servo (rotating compartment selector)
  - Collection servo (pill dispenser)
- **Raspberry Pi** (with camera module)
- **USB Serial Connections** (COM4, /dev/ttyACM0, /dev/ttyACM1)

### Mechanical
- 3 medication compartments (Box 1, 2, 3)
- Pill dispensing mechanism
- Rotating divider platform (0°, 120°, 240° positions)

## 💻 Software Requirements

### Python Dependencies
```bash
pip install mysql-connector-python
pip install pyserial
pip install opencv-python
pip install numpy
pip install pytesseract
pip install requests
pip install picamera2
```

### Additional Software
- **Tesseract OCR** - Install on Raspberry Pi
- **MySQL Database Server** (v8.0+)
- **PHP** (v7.4+ or v8.0+)
- **Arduino IDE** - For ESP32 firmware upload

### ESP32 Libraries
- MFRC522 (RFID library)
- ESP32Servo

## 🗄️ Database Setup

1. Create MySQL database:
```sql
CREATE DATABASE medication_tracker;
CREATE USER 'med_user'@'localhost' IDENTIFIED BY '';
GRANT ALL PRIVILEGES ON medication_tracker.* TO 'med_user'@'localhost';
```

2. Create medications table:
```sql
CREATE TABLE medications (
    box_id INT PRIMARY KEY,
    medication_id INT,
    medication_name VARCHAR(100),
    total_pills INT DEFAULT 0,
    pills_per_intake INT DEFAULT 1,
    schedule_time_1 TIME,
    schedule_time_2 TIME
);
```

## 🚀 Installation & Setup

### 1. Hardware Setup
1. Connect RFID reader to ESP32 (SPI pins: SS=5, RST=22)
2. Connect servo to ESP32 (Pin 13 or 27)
3. Connect both ESP32s to Raspberry Pi via USB
4. Mount Raspberry Pi camera module

### 2. Configure RFID
Edit [RFID.ino](RFID.ino) and update:
```cpp
byte allowedUID[4] = {0x40, 0xC5, 0xFC, 0x61}; // Your RFID card UID
```

Upload to ESP32 using Arduino IDE.

### 3. Configure Serial Ports
Update port settings in Python files:

**Med_dispenser.py:**
```python
SERIAL_PORT_MOTOR = "/dev/ttyACM0"   # Motor controller
RFID_SERIAL_PORT = "/dev/ttyACM1"    # RFID reader
```

**access.py:**
```python
SERIAL_PORT = 'COM4'  # Windows system
```

### 4. Setup Web Dashboard
1. Place [index.php](index.php) in web server directory
2. Update database credentials if needed
3. Access via: `http://localhost/index.php`

### 5. Configure API Endpoint
Update API URL in [Med_dispenser.py](Med_dispenser.py):
```python
API_URL = "https://your-ngrok-url.ngrok-free.dev/medication_tracker/index.php"
API_KEY = "-Your-API-Key"
```

## 📖 Usage Guide

### Phase 1: Setup Mode (OCR Scanning)

1. **Start setup:** Run `Med_dispenser.py`
2. **Activate camera:** Tap RFID card once
3. **Automatic scanning:** System scans all 3 medication boxes
   - Extracts dosage (e.g., "Take 1 tablet every 6 hours")
   - Extracts quantity (total pills)
   - Uploads to database
4. **Stop setup:** Tap RFID card again

### Phase 2: Scheduler Mode

Run `access.py` for scheduled dispensing:
- Monitors database for medication schedules
- Automatically dispenses at configured times
- Updates inventory after each dispense
- Shows low stock warnings

### Web Dashboard Management

Access the dashboard to:
- **Add medications** manually to boxes 1-3
- **Set schedules** (1x or 2x daily)
- **Update inventory** levels
- **View alerts** for low/critical stock
- **Delete medications** when boxes are refilled

## 🔍 Key Features

### 1. OCR Label Recognition
- Reads prescription labels automatically
- Extracts dosage patterns: "Take X tablet(s) every Y hours"
- Identifies quantities: "QTY: 30"
- Multi-frame scanning for accuracy (5 frames, 30% confidence threshold)

### 2. Smart Dispensing
- **3-box system** with 120° rotation intervals
- **Multi-pill support** (1-4 pills per dose)
- **Precise timing** (minute-level accuracy)
- **Safe operation** with dosage validation

### 3. Inventory Management
- Real-time stock tracking
- Low stock warnings (≤10 pills)
- Critical alerts (≤5 pills)
- Empty box detection
- Auto-decrement after dispensing

### 4. Security
- RFID authentication required
- API key protection
- Database access control

## 📊 Dosage Patterns Recognized

- `TAKE 1 TABLET EVERY 6 HOURS`
- `TAKE 2 TABLETS DAILY`
- `TAKE ONE TABLET ONCE DAILY`
- Valid intervals: 4, 6, 8, 12, 24 hours
- Valid pills per dose: 1-4 tablets

## 🔔 Alert System

| Status | Pills Remaining | Action |
|--------|----------------|--------|
| 🟢 OK | >10 | Normal operation |
| 🟡 LOW | 6-10 | Warning displayed |
| 🔴 CRITICAL | 1-5 | Urgent refill needed |
| ⚫ EMPTY | 0 | Refill immediately |

## 🛠️ Troubleshooting

### Serial Connection Issues
- Check USB connections
- Verify port names: `ls /dev/tty*` (Linux) or Device Manager (Windows)
- Ensure correct baud rates (115200)

### OCR Not Reading Labels
- Improve lighting conditions
- Adjust camera focus
- Clean camera lens
- Ensure label text is clear and horizontal

### Servo Not Moving
- Check power supply to servos
- Verify pin connections
- Test servo angles manually

### Database Connection Failed
- Verify MySQL service is running
- Check credentials in PHP/Python files
- Confirm database and table exist

## 📝 Configuration Files

### Servo Angles
```python
angles = {
    1: 0,     # Box 1
    2: 120,   # Box 2
    3: 240    # Box 3
}
```

### Schedule Times
- Format: `HH:MM` (24-hour)
- Supports 2 daily doses
- Example: `08:00` and `20:00`

## 🎓 Technical Details

### Serial Command Protocol
- **Divider:** `D<angle>` (e.g., `D120`)
- **Collection:** `C<angle>` (e.g., `C180`)
- **RFID Toggle:** `RFID_TOGGLE`

### Camera Settings
- Resolution: 2592x1944
- Format: RGB → BGR conversion
- Preprocessing: OTSU thresholding

## 📄 License

Built for Escendo 2026 Hackathon

## 👥 Contributors
- [@weiores](https://github.com/Weiores) - Database & Backend   
Team Escendo 2026

## 📧 Support

For issues or questions, please refer to the project documentation or contact the development team.

---

**Last Updated:** 12 January, 2026
