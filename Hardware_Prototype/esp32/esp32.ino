const int pirPin = 13;
const int ledPin = 14;
const int buzzerPin = 27;

const unsigned long holdTime = 3000;   // ms with no motion before stopping
unsigned long lastMotion = 0;
bool alarmOn = false;

void setup() {
  pinMode(pirPin, INPUT_PULLDOWN);
  pinMode(ledPin, OUTPUT);
  pinMode(buzzerPin, OUTPUT);
  digitalWrite(buzzerPin, HIGH);   // idle level
  Serial.begin(115200);
  Serial.println("Warming up PIR, wait 10 seconds...");
  delay(10000);
  Serial.println("Ready");
}

void loop() {
  if (digitalRead(pirPin) == HIGH) {
    lastMotion = millis();
    if (!alarmOn) {
      alarmOn = true;
      Serial.println("Motion Detected!");
      tone(buzzerPin, 2500);
      digitalWrite(ledPin, HIGH);
    }
  }

  if (alarmOn && millis() - lastMotion > holdTime) {
    alarmOn = false;
    Serial.println("Motion Not Detected");
    noTone(buzzerPin);
    digitalWrite(buzzerPin, HIGH);
    digitalWrite(ledPin, LOW);
  }

  delay(50);
}