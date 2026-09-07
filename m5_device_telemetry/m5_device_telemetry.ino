#include <M5CoreS3.h>
#include <WiFi.h>
#include <PubSubClient.h>

const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* MQTT_HOST = "YOUR_MQTT_BROKER";
const int MQTT_PORT = 1883;
const char* DEVICE_ID = "m5-device-01";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
unsigned long lastPublish = 0;

void connectMqtt() {
    while (!mqtt.connected()) {
        Serial.print("MQTT connecting...");
        if (mqtt.connect(DEVICE_ID)) Serial.println(" connected");
        else {
            Serial.printf(" failed, state=%d\n", mqtt.state());
            delay(3000);
        }
    }
}

void setup() {
    Serial.begin(115200);
    CoreS3.begin();
    CoreS3.Display.setTextSize(2);
    CoreS3.Display.println("Telemetry starting...");

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
    Serial.printf("\nWi-Fi: %s\n", WiFi.localIP().toString().c_str());

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    CoreS3.Display.println("Telemetry ready");
}

void publishHealth() {
    char payload[256];
    snprintf(payload, sizeof(payload),
        "{\"device_id\":\"%s\",\"firmware\":\"0.1.0\",\"uptime_s\":%lu,\"free_heap\":%lu,\"wifi_rssi\":%d}",
        DEVICE_ID, millis() / 1000, ESP.getFreeHeap(), WiFi.RSSI());
    String topic = String("devices/") + DEVICE_ID + "/health";
    mqtt.publish(topic.c_str(), payload, true);
    Serial.printf("Published %s: %s\n", topic.c_str(), payload);
}

void loop() {
    CoreS3.update();
    if (!mqtt.connected()) connectMqtt();
    mqtt.loop();
    if (millis() - lastPublish >= 10000) {
        publishHealth();
        lastPublish = millis();
    }
    delay(10);
}
