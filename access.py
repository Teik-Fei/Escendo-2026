import mysql.connector
import serial  
import time
from datetime import datetime

SERIAL_PORT = 'COM4' 
BAUD_RATE = 115200

def get_medication_data():
    """Fetches all meds to check their schedules."""
    data = []
    try:
        connection = mysql.connector.connect(
            host="127.0.0.1", database="medication_tracker",
            user="med_user", password="", port="3306"
        )
        cursor = connection.cursor(dictionary=True)
        # We fetch everything to check schedules in Python
        cursor.execute("SELECT * FROM medications")
        data = cursor.fetchall()
        connection.close()
    except Exception as error:
        print(f"Database Error: {error}")
    return data

def update_pill_count(box_id, pills_dispensed):
    """Decrements the pill count in the database after dispensing."""
    try:
        connection = mysql.connector.connect(
            host="127.0.0.1", database="medication_tracker",
            user="med_user", password="", port="3306"
        )
        cursor = connection.cursor()
        
        # Debug: Check current value before update
        cursor.execute("SELECT total_pills FROM medications WHERE box_id = %s", (box_id,))
        before_result = cursor.fetchone()
        before_count = before_result[0] if before_result else None
        print(f"DEBUG: Box {box_id} had {before_count} pills before dispense")
        
        # Decrement total_pills by the amount dispensed
        query = """
            UPDATE medications 
            SET total_pills = GREATEST(total_pills - %s, 0)
            WHERE box_id = %s
        """
        cursor.execute(query, (pills_dispensed, box_id))
        rows_affected = cursor.rowcount
        connection.commit()
        
        print(f"DEBUG: SQL UPDATE affected {rows_affected} row(s) for box_id={box_id}")
        
        # Get the updated count to display
        cursor.execute("SELECT total_pills FROM medications WHERE box_id = %s", (box_id,))
        result = cursor.fetchone()
        remaining = result[0] if result else 0
        
        print(f"✓ Database updated: Box {box_id} now has {remaining} pills remaining (dispensed {pills_dispensed})")
        
        # Warn if stock is low
        if remaining <= 5 and remaining > 0:
            print(f"⚠️ WARNING: Box {box_id} is running low on medication! Only {remaining} pills left.")
        elif remaining == 0:
            print(f"🔴 CRITICAL: Box {box_id} is EMPTY! Refill immediately!")
        
        connection.close()
        return remaining
        
    except Exception as error:
        print(f"Database Update Error for Box {box_id}: {error}")
        import traceback
        traceback.print_exc()
        return None

def send_command(label, angle):
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
            time.sleep(2) 
            command = f"{label}{angle}\n"
            ser.write(command.encode())
            print(f"Sent to ESP32: {command.strip()}")
    except Exception as e:
        print(f"Serial Error: {e}")

def dispense(box_id, pills, medication_name):
    """Handles the physical servo movement sequence and updates database."""
    print(f"\n{'='*60}")
    print(f"!!! DISPENSING {pills} pill(s) from Box {box_id} ({medication_name}) !!!")
    print(f"{'='*60}")
    
    # 1. Set Divider Position
    angles = {1: 0, 2: 120, 3: 240}
    target_angle = angles.get(box_id, 0)
    
    send_command('D', target_angle)
    time.sleep(1)
    
    # 2. Trigger Collection (Repeat based on pills_per_intake)
    for i in range(pills):
        print(f"Dispensing pill {i+1}/{pills}...")
        send_command('C', 180)
        time.sleep(1)
        send_command('C', 0)
        time.sleep(1)
    
    # 3. Reset Divider
    send_command('D', 0)
    
    # 4. Update database with new pill count
    remaining = update_pill_count(box_id, pills)
    
    print(f"Dispense complete for Box {box_id}")
    print(f"{'='*60}\n")

def main():
    print("="*60)
    print("Medication Scheduler Started with Stock Tracking")
    print("="*60)
    print(f"Monitoring time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Press Ctrl+C to stop\n")
    
    last_checked_minute = -1
    
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M") # Format: "08:30"
        
        # Only check once per minute
        if now.minute != last_checked_minute:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Checking schedule...")
            meds = get_medication_data()
            
            if not meds:
                print("No medications found in database.")
            
            for row in meds:
                # Check if there are pills available
                if row['total_pills'] <= 0:
                    print(f"⚠️ Skipping Box {row['box_id']} ({row['medication_name']}): No pills available!")
                    continue
                
                # Check both schedule columns
                sched1 = str(row.get('schedule_time_1'))[:5] # Take "HH:MM"
                sched2 = str(row.get('schedule_time_2'))[:5] if row.get('schedule_time_2') else None
                
                if current_time == sched1 or (sched2 and current_time == sched2):
                    # Check if we have enough pills
                    if row['total_pills'] < row['pills_per_intake']:
                        print(f"⚠️ WARNING: Box {row['box_id']} ({row['medication_name']}) has only {row['total_pills']} pills but needs {row['pills_per_intake']}!")
                        print(f"Dispensing available {row['total_pills']} pill(s) instead...")
                        dispense(row['box_id'], row['total_pills'], row['medication_name'])
                    else:
                        dispense(row['box_id'], row['pills_per_intake'], row['medication_name'])
            
            last_checked_minute = now.minute
            
        time.sleep(10) # Wait 10 seconds before checking the clock again

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nScheduler stopped by user.")
    except Exception as e:
        print(f"\nFatal Error: {e}")