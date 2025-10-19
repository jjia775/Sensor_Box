# from datetime import datetime, timedelta
# from home_env_sim import HomeEnvSim
# from lorawan_encode import encode_lorawan, to_hex
# from lorawan_decode import decode_lorawan
#
# # Choose any start time—for example 05:00 today—to match the dashboard’s selectable window.
# start = datetime.now().replace(hour=5, minute=0, second=0, microsecond=0)
# sim = HomeEnvSim(profile="intermittent", period_minutes=5, seed=123)
#
# window = sim.generate_window(start, hours=12)   # [(dt, esp), ...]
# for dt, esp in window:
#     payload = encode_lorawan(esp)
#     esp_back = decode_lorawan(payload)
#     # esp_back is exactly what the server would reconstruct
#     print(dt.strftime("%H:%M"), to_hex(payload), esp_back)
from datetime import datetime
import time
import requests
from home_env_sim import HomeEnvSim
from lorawan_encode import encode_lorawan

SERVER_URL = "http://localhost:8000/ingest/lorawan/raw"  # change to your server
HOUSE_ID = "H001"
SENSOR_ID = "esp32-01"

start = datetime.now().replace(hour=5, minute=0, second=0, microsecond=0)
sim = HomeEnvSim(profile="intermittent", period_minutes=5, seed=123)

for dt, esp in sim.generate_window(start, hours=12):
    payload = encode_lorawan(esp)
    headers = {
        "X-House-Id": HOUSE_ID,
        "X-Sensor-Id": SENSOR_ID,
        "X-Timestamp": dt.isoformat(),
        "Content-Type": "application/octet-stream"
    }
    r = requests.post(SERVER_URL, data=payload, headers=headers, timeout=5)
    r.raise_for_status()
    print(dt.strftime("%H:%M"), len(payload), "bytes ->", r.status_code)
    # time.sleep(1)
