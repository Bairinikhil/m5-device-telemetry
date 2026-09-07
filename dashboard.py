import json
import asyncio
import threading
import time
from collections import deque

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "devices/+/health"

latest = {}
history = deque(maxlen=60)
lock = threading.Lock()
clients = set()
event_loop = None

app = FastAPI(title="M5 Device Telemetry")

HTML = """<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='10'><meta name='viewport' content='width=device-width,initial-scale=1'><title>M5 Telemetry</title>
<style>*{{box-sizing:border-box}}body{{font:16px system-ui,sans-serif;max-width:980px;margin:0 auto;padding:42px 22px;background:linear-gradient(135deg,#0b1220,#121d2b);color:#eaf2f8;min-height:100vh}}header{{display:flex;justify-content:space-between;align-items:end;margin-bottom:28px}}h1{{margin:0;color:#70f0d0;font-size:32px}}.sub{{color:#8fa6b8;margin-top:6px}}.card{{background:rgba(28,42,57,.9);border:1px solid #2d4558;padding:22px;border-radius:16px;box-shadow:0 10px 30px #0003;margin-bottom:16px}}.device{{display:flex;justify-content:space-between;align-items:center}}.device-name{{font-size:20px;font-weight:700}}.badge{{padding:7px 13px;border-radius:99px;font-weight:700;font-size:13px;letter-spacing:.5px}}.ok{{background:#123e3a;color:#70f0d0}}.bad{{background:#4a2027;color:#ff9ca3}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}.label{{color:#8fa6b8;font-size:14px}}.value{{font-size:30px;font-weight:750;margin-top:8px}}footer{{color:#71899b;font-size:13px;margin-top:24px}}@media(max-width:650px){{header{{display:block}}h1{{font-size:27px}}.grid{{grid-template-columns:1fr}}}}</style></head>
<body><header><div><h1>M5 Device Telemetry</h1><div class='sub'>Live health monitor for your edge device</div></div></header><div id='dashboard'>{content}</div><div class='card'><div class='label'>LIVE HISTORY · HEAP / WI-FI</div><canvas id='historyChart' height='150'></canvas></div><footer>Live via WebSocket · MQTT: devices/+/health</footer><script>
const chartData=[];const canvas=document.getElementById('historyChart');const ctx=canvas.getContext('2d');
function updateChart(d){chartData.push({heap:d.free_heap/1024,rssi:d.wifi_rssi});if(chartData.length>30)chartData.shift();drawChart()}
function drawChart(){const w=canvas.clientWidth||700,h=150;canvas.width=w*devicePixelRatio;canvas.height=h*devicePixelRatio;ctx.scale(devicePixelRatio,devicePixelRatio);ctx.clearRect(0,0,w,h);if(chartData.length<2)return;const minHeap=Math.min(...chartData.map(x=>x.heap))-5,maxHeap=Math.max(...chartData.map(x=>x.heap))+5;const minRssi=Math.min(...chartData.map(x=>x.rssi))-5,maxRssi=Math.max(...chartData.map(x=>x.rssi))+5;function line(key,min,max,color){ctx.beginPath();chartData.forEach((x,i)=>{const px=10+i*(w-20)/(chartData.length-1),py=h-10-(x[key]-min)/(max-min)*(h-20);i?ctx.lineTo(px,py):ctx.moveTo(px,py)});ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke()}line('heap',minHeap,maxHeap,'#70f0d0');line('rssi',minRssi,maxRssi,'#ffc857')}
const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
ws.onmessage=(e)=>{const d=JSON.parse(e.data);if(d.type==='history'){d.items.forEach(updateChart);return}const online=(Date.now()/1000-d.received_at)<30;document.getElementById('dashboard').innerHTML=`<div class='card device'><div><div class='device-name'>${d.device_id}</div><div class='sub'>Firmware ${d.firmware}</div></div><div class='badge ${online?'ok':'bad'}'>${online?'ONLINE':'OFFLINE'}</div></div><div class='grid'><div class='card'><div class='label'>UPTIME</div><div class='value'>${d.uptime_s} s</div></div><div class='card'><div class='label'>FREE HEAP</div><div class='value'>${Math.round(d.free_heap/1024)} KB</div></div><div class='card'><div class='label'>WI-FI SIGNAL</div><div class='value'>${d.wifi_rssi} dBm</div></div></div>`;updateChart(d)};
</script></body></html>"""
HTML = HTML.replace("{{", "{").replace("}}", "}")


def mqtt_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode())
        data["received_at"] = time.time()
        with lock:
            latest.clear()
            latest.update(data)
            history.append(dict(data))
        if event_loop and event_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(data), event_loop)
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
        content = "<div class='card'><div class='label'>DEVICE STATUS</div><div class='value'>Waiting for telemetry...</div><div class='sub'>Start the M5 device to receive its first health packet.</div></div>"
    else:
        age = time.time() - data.get("received_at", 0)
        state = "ONLINE" if age < 30 else "OFFLINE"
        state_class = "ok" if state == "ONLINE" else "bad"
        content = f"""<div class='card'><div class='{state_class}'>{state}</div><small>{data.get('device_id','unknown')} · firmware {data.get('firmware','?')}</small></div>
<div class='grid'><div class='card'>Uptime<div class='value'>{data.get('uptime_s', 0)} s</div></div>
<div class='card'>Free heap<div class='value'>{int(data.get('free_heap', 0)/1024)} KB</div></div>
<div class='card'>Wi-Fi RSSI<div class='value'>{data.get('wifi_rssi', '?')} dBm</div></div></div>"""
    return HTML.replace("{content}", content)


async def broadcast(data):
    stale = set()
    for client in clients:
        try:
            await client.send_json(data)
        except Exception:
            stale.add(client)
    clients.difference_update(stale)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global event_loop
    await websocket.accept()
    event_loop = asyncio.get_running_loop()
    clients.add(websocket)
    try:
        with lock:
            data = dict(latest)
        if data:
            await websocket.send_json(data)
        with lock:
            saved_history = list(history)
        await websocket.send_json({"type": "history", "items": saved_history})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        clients.discard(websocket)


threading.Thread(target=mqtt_worker, daemon=True).start()
