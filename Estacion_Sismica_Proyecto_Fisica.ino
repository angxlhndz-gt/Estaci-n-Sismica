// === Estación Sísmica robusta (anti-cuelgues I2C) ===
// UNO + GY-521 (MPU-6050) + LED D7 + BUZZER D8
// - Serial 115200, CSV a 5 Hz: t_ms,ax,ay,az,intensidad,alarm
// - Lectura segura del MPU con timeout y watchdog de recuperación

#include <Wire.h>
#include <MPU6050.h>
#include <math.h>

// ---------- Pines ----------
#define LED_PIN    7
#define BUZZER_PIN 8

// ---------- Serial / impresión ----------
#define BAUD       115200
#define PRINT_HZ   5
const unsigned long PRINT_PERIOD_MS = 1000UL / PRINT_HZ;

// ---------- Muestreo ----------
const unsigned long SAMPLE_PERIOD_MS = 10;   // ~100 Hz

// ---------- Detección (anti-falsos) ----------
float threshold_on_g  = 0.06f;   // encender
float hysteresis_g    = 0.02f;   // apagar por debajo de on - hysteresis
int   arm_consec      = 5;       // muestras seguidas para ENCENDER
int   clear_consec    = 15;      // muestras seguidas para APAGAR
unsigned long cooldown_ms = 1000; // pausa tras apagar

float threshold_off_g = 0.04f;   // se calcula en recalibración

// ---------- Estados ----------
enum Estado { NORMAL, ALARMA, COOLDOWN } estado = NORMAL;
int cnt_arm = 0, cnt_clear = 0;
unsigned long tCooldownHasta = 0;

// ---------- MPU / I2C ----------
MPU6050 mpu;                      // Jeff Rowberg library
const uint8_t MPU_ADDR = 0x68;    // ADO a GND
const uint8_t REG_ACCEL_XOUT_H = 0x3B;

int i2cFailCount = 0;             // contador de fallos para watchdog

// ---------- Tiempos ----------
unsigned long tPrevSample = 0;
unsigned long tPrevPrint  = 0;
unsigned long t0_ms       = 0;
unsigned long lastProgress = 0;   // última vez que logramos imprimir (para “perro guardián”)

// ---------- Helpers buzzer ----------
void buzOn()  { tone(BUZZER_PIN, 1000); }
void buzOff() { noTone(BUZZER_PIN); }

// ---------- Lectura segura del MPU (sin bloquear) ----------
bool safeReadAccel(float &ax_g, float &ay_g, float &az_g) {
  // 1) posicionar puntero de registro
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(REG_ACCEL_XOUT_H);
  if (Wire.endTransmission(false) != 0) {      // NACK o error
    i2cFailCount++;
    return false;
  }
  // 2) pedir 6 bytes (AX,AY,AZ)
  uint8_t n = Wire.requestFrom(MPU_ADDR, (uint8_t)6);
  if (n < 6) {                                  // timeout / bytes incompletos
    i2cFailCount++;
    return false;
  }
  // 3) convertir
  int16_t x = (Wire.read() << 8) | Wire.read();
  int16_t y = (Wire.read() << 8) | Wire.read();
  int16_t z = (Wire.read() << 8) | Wire.read();
  ax_g = x / 16384.0f;
  ay_g = y / 16384.0f;
  az_g = z / 16384.0f;

  i2cFailCount = 0;  // lectura OK → resetea contador
  return true;
}

// ---------- Watchdog de recuperación I2C ----------
void i2cRecoverIfNeeded(const char* motivo) {
  if (i2cFailCount >= 3) {
    // Apaga salidas para evitar ruido durante la recuperación
    buzOff();
    digitalWrite(LED_PIN, LOW);
    Serial.print("# I2C fallo ("); Serial.print(motivo); Serial.println("): reiniciando bus/MPU...");

    // Reinicia TWI y el MPU
    Wire.end(); delay(5);
    Wire.begin();
    Wire.setWireTimeout(3000, true);   // timeout + auto reset TWI
    // Wire.setClock(100000);          // descomenta si usas cables largos

    mpu.initialize();
    delay(50);

    i2cFailCount = 0;
    // tras recuperar, no dispares alarma inmediatamente
    estado = COOLDOWN;
    tCooldownHasta = millis() + 500;
  }
}

// ---------- Recalibración de umbrales en reposo (5 s) ----------
void recalibrar() {
  const unsigned long T = 5000;
  unsigned long t0 = millis();
  long n = 0;
  double sum = 0, sum2 = 0;

  while (millis() - t0 < T) {
    float ax, ay, az;
    if (safeReadAccel(ax, ay, az)) {
      float mag = sqrt(ax*ax + ay*ay + az*az);
      float intensidad = fabs(mag - 1.0f);
      sum += intensidad;
      sum2 += (double)intensidad * (double)intensidad;
      n++;
    } else {
      i2cRecoverIfNeeded("cal");
    }
    delay(SAMPLE_PERIOD_MS);
  }

  double mean = (n>0) ? sum/n : 0.0;
  double var  = (n>0) ? (sum2/n) - mean*mean : 0.0;
  double stdv = (var>0) ? sqrt(var) : 0.0;

  threshold_on_g  = (float)(fabs(mean) + 5.0*stdv);
  if (threshold_on_g < 0.06f) threshold_on_g = 0.06f;
  threshold_off_g = max(0.0f, threshold_on_g - hysteresis_g);

  Serial.print("# Umbral on=");  Serial.print(threshold_on_g, 3);
  Serial.print(" off=");         Serial.println(threshold_off_g, 3);
}

// ---------- Setup ----------
void setup() {
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); buzOff();

  Serial.begin(BAUD);

  Wire.begin();
  Wire.setWireTimeout(3000, true);   // timeout I2C + reset TWI si se cuelga
  // Wire.setClock(100000);          // opcional: 100 kHz

  mpu.initialize();
  if (!mpu.testConnection()) {
    Serial.println("# ERROR: MPU6050 no conectado.");
    // seguimos, el watchdog intentará recuperar si aparece luego
  }

  // Auto-test corto
  digitalWrite(LED_PIN, HIGH); buzOn(); delay(400);
  digitalWrite(LED_PIN, LOW);  buzOff();

  Serial.println("# Calibrando 5s, no mover...");
  recalibrar();
  Serial.println("# READY");
  Serial.println("# t_ms,ax_g,ay_g,az_g,intensidad_g,alarm");

  t0_ms = millis();
  lastProgress = millis();
}

// ---------- Loop ----------
void loop() {
  unsigned long now = millis();

  // Muestreo ~100 Hz (no bloquear)
  if (now - tPrevSample < SAMPLE_PERIOD_MS) return;
  tPrevSample = now;

  // Leer aceleración (segura)
  float ax, ay, az;
  if (!safeReadAccel(ax, ay, az)) {
    i2cRecoverIfNeeded("read");
    // watchdog adicional: si no hay progreso en 700 ms, fuerza recuperacion
    if (now - lastProgress > 700) { i2cFailCount = 3; i2cRecoverIfNeeded("stall"); }
    return;  // esta vuelta no seguimos (evita usar datos inválidos)
  }

  // Intensidad (|a| - 1g)
  float mag = sqrt(ax*ax + ay*ay + az*az);
  float intensidad = fabs(mag - 1.0f);

  // FSM con histéresis + consecutivos + cooldown
  switch (estado) {
    case NORMAL:
      if (intensidad > threshold_on_g) { cnt_arm++; } else { cnt_arm = 0; }
      if (cnt_arm >= arm_consec) { estado = ALARMA; cnt_arm = 0; cnt_clear = 0; }
      break;

    case ALARMA:
      digitalWrite(LED_PIN, HIGH); buzOn();
      if (intensidad < threshold_off_g) { cnt_clear++; } else { cnt_clear = 0; }
      if (cnt_clear >= clear_consec) {
        digitalWrite(LED_PIN, LOW); buzOff();
        estado = COOLDOWN; tCooldownHasta = now + cooldown_ms;
      }
      break;

    case COOLDOWN:
      digitalWrite(LED_PIN, LOW); buzOff();
      if (now >= tCooldownHasta) estado = NORMAL;
      break;
  }

  // Salida CSV a 5 Hz
  if (now - tPrevPrint >= PRINT_PERIOD_MS) {
    tPrevPrint = now;
    int alarmFlag = (estado == ALARMA) ? 1 : 0;
    unsigned long t_ms = now - t0_ms;

    Serial.print(t_ms); Serial.print(',');
    Serial.print(ax, 3); Serial.print(',');
    Serial.print(ay, 3); Serial.print(',');
    Serial.print(az, 3); Serial.print(',');
    Serial.print(intensidad, 3); Serial.print(',');
    Serial.println(alarmFlag);

    lastProgress = now;           // hubo progreso → resetea anti-“pegado”
  }

  // Si por alguna razón pasan >700 ms sin imprimir, dispara recuperación
  if (now - lastProgress > 700) { i2cFailCount = 3; i2cRecoverIfNeeded("stall"); }
}
