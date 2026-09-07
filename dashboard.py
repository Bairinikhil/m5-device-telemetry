import json
import threading
import time
from collections import deque

import paho.mqtt.client as mqtt
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "devices/+/health"

latest = {}
history = deque(maxlen=60)
lock = threading.Lock()

app = FastAPI(title="M5 Device Telemetry")

HTML = """<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='10'><title>M5 Telemetry</title>
<style>body{font:18px system-ui;max-width:850px;margin:40px auto;background:#10151c;color:#eaf2f8}h1{color:#55d6be}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.card{background:#1b2530;padding:20px;border-radius:12px}.value{font-size:28px;font-weight:700;margin-top:8px}.ok{color:#55d6be}.bad{color:#ff7675}small{color:#9fb0bf}</style></head>
<body><h1>M5 Device Telemetry</h1>{content}<p><small>Refreshes every 10 seconds. MQTT topic: devices/+/health</small></p></body></html>"""


def mqtt_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode())
        data["received_at"] = time.time()
        with lock:
            latest.clear()
            latest.update(data)
            history.append(dict(data))
        print(f"Received {message.topic}: {data}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"Invalid telemetry: {exc}")


def mqtt_worker():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="m5-telemetry-dashboard")
    client.on_message = mqtt_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.subscribe(MQTT_TOPIC)
    client.loop_forever()


@app.get("/", response_class=HTMLResponse)
def dashboard():
    with lock:
        data = dict(latest)
    if not data:
        content = "<div class='card'>Waiting for telemetry...</div>"
    else:
        age = time.time() - data.get("received_at", 0)
        state = "ONLINE" if age < 30 else "OFFLINE"
        state_class = "ok" if state == "ONLINE" else "bad"
        content = f"""<div class='card'><div class='{state_class}'>{state}</div><small>{data.get('device_id','unknown')} · firmware {data.get('firmware','?')}</small></div>
<div class='grid'><div class='card'>Uptime<div class='value'>{data.get('uptime_s', 0)} s</div></div>
<div class='card'>Free heap<div class='value'>{int(data.get('free_heap', 0)/1024)} KB</div></div>
<div class='card'>Wi-Fi RSSI<div class='value'>{data.get('wifi_rssi', '?')} dBm</div></div></div>"""
    return HTML.format(content=content)


threading.Thread(target=mqtt_worker, daemon=True).start()
