const int pirPin = 13;
const int ledPin = 14;
const int buzzerPin = 27;
int lastState = -1;

void setup() {
  pinMode(pirPin, INPUT_PULLDOWN);
  pinMode(ledPin, OUTPUT);
  Serial.begin(115200);
  Serial.println("Warming up PIR, wait 60 seconds...");
  delay(60000);
  Serial.println("Ready");
}

void loop() {
  int motion = digitalRead(pirPin);

  if (motion != lastState) {
    if (motion == HIGH) {
      Serial.println("Motion Detected!");
      tone(buzzerPin, 2500, 500);   // 2500 Hz for 500 ms
    } else {
      Serial.println("Motion Not Detected");
    }
    lastState = motion;
  }

  digitalWrite(ledPin, motion);
  delay(100);
}