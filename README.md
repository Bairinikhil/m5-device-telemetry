# M5 Device Telemetry

Health telemetry for the M5CoreS3 over MQTT.

```text
M5CoreS3 -> Wi-Fi -> MQTT -> monitoring dashboard
```

## Test

1. Install the Arduino `PubSubClient` library.
2. Open `m5_device_telemetry/m5_device_telemetry.ino`.
3. Enter Wi-Fi and MQTT broker details locally.
4. Upload by USB.
5. Subscribe to `devices/m5-device-01/health`.

The device publishes uptime, free heap, Wi-Fi signal strength, device ID, and firmware version every 10 seconds. Do not commit credentials.

## Dashboard

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start the dashboard while Mosquitto is running:

```powershell
python -m uvicorn dashboard:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080` in a browser. The dashboard shows the latest health packet and marks the device offline after 30 seconds without telemetry. Recent telemetry is stored locally in `telemetry.db`, so chart history survives dashboard restarts.
