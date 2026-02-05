#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>

#define SS_PIN     5
#define RST_PIN    22
#define SERVO_PIN  13   // You can change to 27 if needed

MFRC522 rfid(SS_PIN, RST_PIN);
Servo doorServo;

// 🔐 Replace with YOUR card UID
byte allowedUID[4] = {0x40, 0xC5, 0xFC, 0x61};


bool doorOpen = false;   // current door state

void setup() {
  Serial.begin(115200);
  SPI.begin();
  rfid.PCD_Init();

  doorServo.attach(SERVO_PIN);
  doorServo.write(0);    // start CLOSED

  Serial.println("Scan RFID to toggle door");
}

void loop() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  Serial.print("UID: ");
  for (byte i = 0; i < rfid.uid.size; i++) {
    Serial.print(rfid.uid.uidByte[i], HEX);
    Serial.print(" ");
  }
  Serial.println();

  if (isAuthorized()) {
    toggleDoor();
  } else {
    Serial.println("Access Denied");
  }

  // prevent repeated triggers
  delay(1000);

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

void toggleDoor() {
  if (doorOpen) {
    Serial.println("Closing door");
    doorServo.write(0);
    doorOpen = false;
  } else {
    Serial.println("Opening door");
    doorServo.write(90);
    doorOpen = true;
  }
}

bool isAuthorized() {
  for (byte i = 0; i < 4; i++) {
    if (rfid.uid.uidByte[i] != allowedUID[i]) {
      return false;
    }
  }
  return true;
}
