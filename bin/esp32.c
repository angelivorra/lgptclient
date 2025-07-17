#include <WiFi.h>
#include <WiFiClient.h>

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128  // OLED display width, in pixels
#define SCREEN_HEIGHT 64  // OLED display height, in pixels

#define OLED_RESET -1  // Reset pin
#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

const char* ssid = "TP-Link_F710";
const char* password = "69528132";

const char* tcp_host = "192.168.0.10";
const uint16_t tcp_port = 12345;

WiFiClient client;

enum FingerState { OFF, MID, ON };
FingerState finger[5] = {OFF, MID, ON, OFF, MID}; // Simulación, reemplaza por tu lógica

const char* fingerNames[5] = {"Pul", "Ind", "Med", "Anu", "Meñ"};

unsigned long lastTcpCheck = 0;
bool lastTcpStatus = false;

void showStatusScreen() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  // Estado WiFi y TCP
  display.setCursor(0, 0);
  display.print("WiFi: ");
  display.println(WiFi.isConnected() ? "Conectado" : "Desconectado");
  display.print("TCP: ");
  display.println(client.connected() ? "Conectado" : "Desconectado");

  // Nombres de los dedos en una fila
  int x_start = 0;
  int y_names = 24;
  int y_states = 36;
  int col_width = 24; // Espacio horizontal para cada dedo
  for (int i = 0; i < 5; i++) {
    display.setCursor(x_start + i * col_width, y_names);
    display.print(fingerNames[i]);
  }

  // Estado de cada dedo justo debajo de su nombre
  for (int i = 0; i < 5; i++) {
    display.setCursor(x_start + i * col_width, y_states);
    switch (finger[i]) {
      case OFF: display.print("OFF"); break;
      case MID: display.print("MID"); break;
      case ON:  display.print("ON");  break;
    }
  }

  display.display();
}

void connectToTCP() {
  if (!client.connected() && WiFi.status() == WL_CONNECTED) {
    client.stop();
    client.connect(tcp_host, tcp_port);
  }
}

void setup() {
  Serial.begin(115200);
  display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS);
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(10, 28);
  display.println("Conectando");
  display.display();

  delay(1000);
  Serial.println();
  Serial.print("Conectando a ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi conectado!");
  Serial.print("Dirección IP: ");
  Serial.println(WiFi.localIP());

  // Ahora muestra la pantalla de estado
  showStatusScreen();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado. Reintentando...");
    WiFi.disconnect();
    WiFi.reconnect();
    unsigned long startAttemptTime = millis();
    // Espera hasta 10 segundos para reconectar
    while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < 10000) {
      delay(500);
      Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println();
      Serial.println("WiFi reconectado!");
      Serial.print("Dirección IP: ");
      Serial.println(WiFi.localIP());
    } else {
      Serial.println();
      Serial.println("No se pudo reconectar.");
    }
  }

  // Revisa TCP cada 2 segundos
  if (millis() - lastTcpCheck > 2000) {
    lastTcpCheck = millis();
    if (!client.connected() && WiFi.status() == WL_CONNECTED) {
      connectToTCP();
    }
    if (lastTcpStatus != client.connected()) {
      lastTcpStatus = client.connected();
      showStatusScreen();
    }
  }

  // Ejemplo de envío de datos si el estado de los dedos cambia:
  /*
  if (client.connected()) {
    String data = "D1:" + String(finger[0]) + ",D2:" + String(finger[1]) + "...";
    client.println(data);
  }
  */

  delay(1000);
}