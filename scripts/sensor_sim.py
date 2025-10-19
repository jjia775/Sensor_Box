import time, uuid, requests, random, os

API = os.getenv("API", "http://localhost:8000")
sensor_id = os.getenv("SENSOR_ID")

def ensure_sensor():
    global sensor_id
    if sensor_id: return sensor_id
    r = requests.post(f"{API}/api/sensors", json={
        "name":"Temp #1","type":"temperature","location":"lab-1","metadata":{"unit":"°C"}
    })
    r.raise_for_status()
    sensor_id = r.json()["id"]
    print("Created sensor:", sensor_id)
    return sensor_id

def main():
    sid = ensure_sensor()
    while True:
        val = round(22.0 + random.uniform(-1.0, 1.0), 3)
        r = requests.post(f"{API}/ingest", json={"sensor_id":sid, "value":val})
        print(r.status_code, r.json())
        time.sleep(1)

if __name__ == "__main__":
    main()
