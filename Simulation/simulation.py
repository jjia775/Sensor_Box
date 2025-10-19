import asyncio, random, json, httpx, time, math, hashlib, errno, shutil
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
from urllib.parse import quote_plus
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# SERVER = "http://localhost:8000"
SERVER = os.getenv("BACKEND_BASE", "http://backend:8000")
CONFIG_PATH = Path(__file__).resolve().with_name("config.json")
CONFIG_LOCK = asyncio.Lock()


# -------------------- Home environment simulator --------------------


@dataclass(frozen=True)
class FieldSpec:
    name: str
    unit: str
    lo: float
    hi: float
    scale: float
    signed: bool


FIELDS = [
    FieldSpec("serial", "-", 0, 65535, 1, False),
    FieldSpec("temp_c", "°C", -40.0, 85.0, 100, True),
    FieldSpec("rh_pct", "%RH", 0.0, 100.0, 100, False),
    FieldSpec("co2_ppm", "ppm", 400.0, 10000.0, 1, False),
    FieldSpec("o2_pct", "%vol", 0.0, 25.0, 100, False),
    FieldSpec("co_ppm", "ppm", 0.0, 500.0, 10, False),
    FieldSpec("pm25_ugm3", "µg/m³", 0.0, 1000.0, 1, False),
    FieldSpec("noise_dba", "dBA", 30.0, 130.0, 10, False),
    FieldSpec("no2_ppb", "ppb", 5.0, 80.0, 1, False),
    FieldSpec("lux", "lux", 0.0, 88000.0, 1, False),
    FieldSpec("bat_mv", "mV", 3200.0, 4300.0, 1, False),
]


IDX = {f.name: i for i, f in enumerate(FIELDS)}


def _clip(name: str, v: float) -> float:
    f = FIELDS[IDX[name]]
    return max(f.lo, min(f.hi, v))


def _lp(prev: float, target: float, alpha: float) -> float:
    """One-pole low-pass filter (alpha in (0,1])."""

    return (1 - alpha) * prev + alpha * target


def _daylength_hours(doy: int, amplitude: float = 4.0) -> float:
    """Approximate daylight length (hours) by day-of-year."""

    return 12.0 + amplitude * math.sin(2 * math.pi * (doy - 80) / 365.0)


def _sunrise_sunset(d: datetime) -> tuple[float, float]:
    """Return sunrise/sunset as decimal hours local time (0..24)."""

    doy = int(d.timetuple().tm_yday)
    length = _daylength_hours(doy)
    center = 12.5
    rise = center - length / 2
    set_ = center + length / 2
    return max(0.0, rise), min(24.0, set_)


def _occupancy_factor(hour: float, weekday: int, rng: random.Random, profile: str) -> float:
    """
    0..1 factor for 'people at home' (drives CO2, RH, noise).
    Weekends busier. Intermittent homes may have higher night occupancy; chronic higher all day.
    """

    weekend = weekday in (5, 6)
    if weekend:
        base = 0.65 + 0.25 * (hour >= 20 or hour < 8) + 0.1 * (10 <= hour <= 16)
    else:
        base = 0.75 if (hour >= 20 or hour < 7) else (0.4 if 9 <= hour < 17 else 0.55)
    if profile == "healthy":
        base -= 0.1
    elif profile == "chronic":
        base += 0.15
    base += rng.uniform(-0.05, 0.05)
    return min(1.0, max(0.0, base))


class _Event:
    def __init__(self, kind: str, duration_min: int):
        self.kind = kind
        self.remaining = float(duration_min)
        self.duration0 = float(duration_min)

    def weight(self) -> float:
        if self.duration0 <= 0:
            return 0.0
        phase = 1.0 - abs(0.5 - min(1.0, self.remaining / self.duration0)) * 2.0
        return max(0.0, phase)


class HomeEnvSim:
    """Generate ESP-style reads with realistic indoor dynamics."""

    MAX_STEP = {
        "temp_c": 0.6,
        "rh_pct": 3.0,
        "co2_ppm": 130.0,
        "o2_pct": 0.08,
        "co_ppm": 10.0,
        "pm25_ugm3": 25.0,
        "noise_dba": 7.0,
        "no2_ppb": 9.0,
        "lux": 2000.0,
        "bat_mv": 5.0,
    }

    def __init__(
        self,
        profile: str = "intermittent",
        period_minutes: float = 5.0,
        start_bat_mv: float = 4300.0,
        serial: int | None = None,
        seed: int | None = None,
        daily_battery_drop_mv_mean: float = 100.0,
    ) -> None:
        self.profile = profile.lower()
        self.period_minutes = max(0.5, float(period_minutes))
        seed_value = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(seed_value)
        self.serial = self.rng.randint(0, 65535) if serial is None else int(serial)

        self.state = {
            "temp_c": self.rng.uniform(14, 19),
            "rh_pct": self.rng.uniform(50, 65),
            "co2_ppm": self.rng.uniform(500, 900),
            "o2_pct": 20.9,
            "co_ppm": self.rng.uniform(0.0, 2.0),
            "pm25_ugm3": self.rng.uniform(5, 15),
            "noise_dba": self.rng.uniform(35, 55),
            "no2_ppb": self.rng.uniform(8, 24),
            "lux": self.rng.uniform(50, 500),
        }

        self.events: list[_Event] = []
        self.last_time: datetime | None = None

        self.bat_mv = float(start_bat_mv)
        self._day_drop_mean = float(daily_battery_drop_mv_mean)
        self._current_day_rate: float | None = None
        self._current_day: tuple[int, int] | None = None

    def _ensure_day_rate(self, when: datetime) -> None:
        year, doy = when.year, when.timetuple().tm_yday
        key = (year, doy)
        if key != self._current_day:
            jitter = self.rng.gauss(0, 10.0)
            factor = max(0.7, min(1.3, (self._day_drop_mean + jitter) / self._day_drop_mean))
            self._current_day_rate = factor * self._day_drop_mean
            self._current_day = key

    def _advance_battery(self, delta_min: float, when: datetime) -> None:
        if delta_min <= 0:
            return
        t = self.last_time if self.last_time else when - timedelta(minutes=delta_min)
        remaining = delta_min
        while remaining > 0:
            self._ensure_day_rate(t)
            assert self._current_day_rate is not None
            end_of_day = t.replace(hour=23, minute=59, second=59, microsecond=999999)
            minutes_to_eod = (end_of_day - t).total_seconds() / 60.0 + 1e-6
            step = min(remaining, minutes_to_eod)
            per_min = self._current_day_rate / 1440.0
            self.bat_mv = max(FIELDS[IDX["bat_mv"]].lo, self.bat_mv - per_min * step)
            t += timedelta(minutes=step)
            remaining -= step

    def _maybe_start_events(self, hour: float, weekday: int, occ: float) -> None:
        r = self.rng.random
        if 6.5 <= hour < 8.5 and occ > 0.4 and r() < 0.06:
            self.events.append(_Event("cook_small", self.rng.randint(10, 25)))
        if 17.0 <= hour < 20.5 and occ > 0.4 and r() < 0.14:
            self.events.append(_Event("cook_big", self.rng.randint(20, 60)))
        if (6.0 <= hour < 8.5 or 21.0 <= hour < 23.0) and occ > 0.3 and r() < 0.08:
            self.events.append(_Event("shower", self.rng.randint(8, 20)))
        if r() < 0.035:
            self.events.append(_Event("vent", self.rng.randint(10, 45)))
        if 7.0 <= hour < 19.0 and r() < 0.025:
            self.events.append(_Event("infiltration", self.rng.randint(15, 45)))
        if (self.profile in ("intermittent", "chronic")) and (hour >= 22 or hour < 6) and r() < 0.05:
            self.events.append(_Event("crowded_night", self.rng.randint(60, 210)))

    def _event_deltas(self) -> dict[str, float]:
        add = {k: 0.0 for k in self.state.keys()}
        done: list[_Event] = []
        for ev in self.events:
            w = ev.weight()
            if ev.kind == "cook_small":
                add["pm25_ugm3"] += 60.0 * w
                add["no2_ppb"] += 12.0 * w
                add["co_ppm"] += 2.5 * w
                add["co2_ppm"] += 120.0 * w
                add["noise_dba"] += 4.0 * w
                add["temp_c"] += 0.2 * w
            elif ev.kind == "cook_big":
                add["pm25_ugm3"] += 140.0 * w
                add["no2_ppb"] += 30.0 * w
                add["co_ppm"] += 6.0 * w
                add["co2_ppm"] += 280.0 * w
                add["noise_dba"] += 7.0 * w
                add["temp_c"] += 0.4 * w
            elif ev.kind == "shower":
                add["rh_pct"] += 20.0 * w
            elif ev.kind == "vent":
                add["co2_ppm"] -= 260.0 * w
                add["rh_pct"] -= 9.0 * w
                add["temp_c"] -= 0.7 * w
            elif ev.kind == "infiltration":
                add["pm25_ugm3"] += 25.0 * w
                add["no2_ppb"] += 10.0 * w
                add["noise_dba"] += 3.0 * w
            elif ev.kind == "crowded_night":
                add["co2_ppm"] += 340.0 * w
                add["rh_pct"] += 6.0 * w

            ev.remaining = max(0.0, ev.remaining - self.period_minutes)
            if ev.remaining <= 0.0:
                done.append(ev)
        for e in done:
            self.events.remove(e)
        return add

    def _cap_step(self, name: str, prev: float, target: float) -> float:
        cap = self.MAX_STEP[name]
        dv = target - prev
        if dv > cap:
            return prev + cap
        if dv < -cap:
            return prev - cap
        return target

    def next_read(self, dt: datetime) -> dict:
        dt = dt.astimezone() if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc).astimezone()
        hour = dt.hour + dt.minute / 60.0
        weekday = dt.weekday()

        if self.last_time is None:
            elapsed_min = 0.0
        else:
            elapsed_min = max(0.0, (dt - self.last_time).total_seconds() / 60.0)
        self._advance_battery(elapsed_min, dt)
        self.last_time = dt

        sunrise, sunset = _sunrise_sunset(dt)
        is_day = sunrise <= hour < sunset
        day_lux = 800.0 if 9 <= hour < 17 else 400.0
        night_lux = 40.0 if 22 <= hour or hour < 6 else 120.0
        lux_target = day_lux if is_day else night_lux

        occ = _occupancy_factor(hour, weekday, self.rng, self.profile)
        self._maybe_start_events(hour, weekday, occ)

        if self.profile == "healthy":
            t_base_night, t_base_day = 18.5, 20.0
            rh_base = 50.0
            vent_base = 0.006
        elif self.profile == "chronic":
            t_base_night, t_base_day = 11.5, 15.0
            rh_base = 70.0
            vent_base = 0.002
        else:
            t_base_night, t_base_day = 12.5, 17.0
            rh_base = 58.0
            vent_base = 0.004

        temp_target = t_base_day if 9 <= hour < 18 else t_base_night
        temp_target += 0.8 * math.sin((hour - 16.0) * math.pi / 12.0)

        rh_target = rh_base + 6.0 * math.sin((hour - 5.0) * math.pi / 12.0)

        outdoor_co2 = 420.0
        co2_gen = 1.8 + 1.2 * occ
        if self.profile == "chronic":
            co2_gen *= 1.4
        if weekday in (5, 6):
            co2_gen *= 1.15

        ev = self._event_deltas()

        alpha = 0.28
        new = dict(self.state)

        target = lux_target + self.rng.gauss(0, 60.0) + ev.get("lux", 0.0)
        target = max(0.0, target)
        target = self._cap_step("lux", new["lux"], target)
        new["lux"] = _clip("lux", _lp(new["lux"], target, alpha))

        target = temp_target + ev.get("temp_c", 0.0) + self.rng.gauss(0, 0.12)
        target = self._cap_step("temp_c", new["temp_c"], target)
        new["temp_c"] = _clip("temp_c", _lp(new["temp_c"], target, alpha))

        rh_occ = 2.5 * occ
        rh_vent = -10.0 * (ev.get("co2_ppm", 0.0) < 0)
        target = rh_target + rh_occ + rh_vent + ev.get("rh_pct", 0.0) + self.rng.gauss(0, 0.9)
        target = self._cap_step("rh_pct", new["rh_pct"], target)
        new["rh_pct"] = _clip("rh_pct", _lp(new["rh_pct"], target, alpha))

        dt_min = max(self.period_minutes, 0.5)
        co2 = new["co2_ppm"]
        k = vent_base
        if ev.get("co2_ppm", 0.0) < 0:
            k += 0.02
        co2_target = co2 + dt_min * (co2_gen + ev.get("co2_ppm", 0.0)) - dt_min * k * (co2 - outdoor_co2)
        co2_target += self.rng.gauss(0, 15.0)
        co2_target = self._cap_step("co2_ppm", co2, co2_target)
        new["co2_ppm"] = _clip("co2_ppm", _lp(co2, co2_target, 0.45))

        new["o2_pct"] = _clip("o2_pct", 20.9 - (new["co2_ppm"] - 420.0) / 20000.0 + self.rng.uniform(-0.02, 0.02))

        pm = new["pm25_ugm3"]
        pm_decay = math.exp(-dt_min / 80.0)
        pm_target = pm * pm_decay + ev.get("pm25_ugm3", 0.0) + self.rng.gauss(0, 2.0)
        pm_target = self._cap_step("pm25_ugm3", pm, pm_target)
        new["pm25_ugm3"] = _clip("pm25_ugm3", _lp(pm, pm_target, 0.5))

        no2 = new["no2_ppb"]
        no2_decay = math.exp(-dt_min / 120.0)
        no2_target = no2 * no2_decay + ev.get("no2_ppb", 0.0) + self.rng.gauss(0, 1.0)
        no2_target = self._cap_step("no2_ppb", no2, no2_target)
        new["no2_ppb"] = _clip("no2_ppb", _lp(no2, no2_target, 0.45))

        co = new["co_ppm"]
        co_decay = math.exp(-dt_min / 70.0)
        co_target = co * co_decay + ev.get("co_ppm", 0.0) + max(0.0, self.rng.gauss(0.05, 0.08))
        co_target = self._cap_step("co_ppm", co, co_target)
        new["co_ppm"] = _clip("co_ppm", _lp(co, co_target, 0.45))

        base_noise = 38.0 if (hour >= 23 or hour < 6) else (46.0 + 6.0 * occ)
        noise_target = base_noise + ev.get("noise_dba", 0.0) + max(0.0, self.rng.gauss(0.0, 1.2))
        noise_target = self._cap_step("noise_dba", new["noise_dba"], noise_target)
        new["noise_dba"] = _clip("noise_dba", _lp(new["noise_dba"], noise_target, 0.35))

        self.state = new

        return {
            "serial": self.serial,
            "temp_c": self.state["temp_c"],
            "rh_pct": self.state["rh_pct"],
            "co2_ppm": self.state["co2_ppm"],
            "o2_pct": self.state["o2_pct"],
            "co_ppm": self.state["co_ppm"],
            "pm25_ugm3": self.state["pm25_ugm3"],
            "noise_dba": self.state["noise_dba"],
            "no2_ppb": self.state["no2_ppb"],
            "lux": self.state["lux"],
            "bat_mv": round(_clip("bat_mv", self.bat_mv), 1),
        }


class BoxEnvironment:
    """Helper to share a HomeEnvSim across sensor workers in a box."""

    def __init__(self, sim: HomeEnvSim) -> None:
        self.sim = sim
        self._lock = asyncio.Lock()

    async def read(self, dt: datetime) -> dict:
        async with self._lock:
            return self.sim.next_read(dt)


_BOX_ENVS: dict[str, BoxEnvironment] = {}


TYPE_TO_FIELD = {
    "temperature": "temp_c",
    "humidity": "rh_pct",
    "co2": "co2_ppm",
    "o2": "o2_pct",
    "co": "co_ppm",
    "pm2_5": "pm25_ugm3",
    "sound_level": "noise_dba",
    "no2": "no2_ppb",
    "light": "lux",
}


def _seed_from_box(box_def: dict) -> int:
    seed_source = box_def.get("seed")
    if seed_source is not None:
        if isinstance(seed_source, int):
            return seed_source
        h = hashlib.sha256(str(seed_source).encode("utf-8")).hexdigest()
        return int(h[:16], 16)
    serial = box_def.get("serial_number") or box_def.get("name", "")
    h = hashlib.sha256(str(serial).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def get_box_environment(box_def: dict) -> BoxEnvironment:
    key = str(box_def.get("serial_number") or box_def.get("name"))
    env = _BOX_ENVS.get(key)
    if env is None:
        profile = str(box_def.get("profile", "intermittent")).lower()
        period_minutes = max(PERIOD_SEC / 60.0, 0.5)
        seed = _seed_from_box(box_def)
        serial_attr = box_def.get("serial_number")
        serial_value = None
        if serial_attr:
            try:
                serial_value = int(str(serial_attr)[-5:], 36)
            except ValueError:
                serial_value = None
        sim = HomeEnvSim(profile=profile, period_minutes=period_minutes, serial=serial_value, seed=seed)
        env = BoxEnvironment(sim)
        _BOX_ENVS[key] = env
    return env

_httpx_client: httpx.AsyncClient | None = None
_cfg_cache: dict[str, tuple[dict, float]] = {}
CFG_TTL_SEC = 30.0

# ====== Scheduling and throttling parameters (overridable in config.json) ======
PERIOD_SEC = 60.0         # Alignment period: default is every full minute
PHASE_MAX_MS = 10_000     # Stable phase per sensor within 0~10s to stagger traffic
MAX_INFLIGHT = 20         # Global upper bound for concurrent in-flight requests
_sema: asyncio.Semaphore | None = None
# ===================================================

# -------------------- HTTP client --------------------
async def get_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None:
        limits = httpx.Limits(max_connections=400, max_keepalive_connections=200)
        _httpx_client = httpx.AsyncClient(timeout=20, limits=limits, http2=True)
    return _httpx_client

def _get_sema() -> asyncio.Semaphore:
    global _sema
    if _sema is None:
        _sema = asyncio.Semaphore(MAX_INFLIGHT)
    return _sema

# -------------------- Household resolution --------------------
async def query_house_id_by_householder(householder: str) -> str | None:
    client = await get_client()
    paths = [
        f"{SERVER}/households?householder={quote_plus(householder)}",
        f"{SERVER}/api/households/resolve?householder={quote_plus(householder)}",
        f"{SERVER}/api/households?householder={quote_plus(householder)}",
    ]
    for url in paths:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and "house_id" in data:
                    return str(data["house_id"])
                if isinstance(data, list) and data:
                    first = data[0]
                    if isinstance(first, dict) and "house_id" in first:
                        return str(first["house_id"])
        except Exception:
            continue
    return None

async def resolve_house_id(box: dict) -> str:
    v = box.get("house_id")
    if v:
        return str(v)
    name = box.get("householder")
    if name:
        hid = await query_house_id_by_householder(str(name))
        if hid:
            return hid
    raise RuntimeError("house_id or householder is required in box definition")

# -------------------- Sensor creation --------------------
async def create_sensor(box: dict, sensor: dict, house_id: str) -> dict:
    client = await get_client()
    url = f"{SERVER}/sensors/?house_id={quote_plus(house_id)}"
    serial = sensor.get("serial") or sensor.get("serial_number") or box.get("serial_number")

    # Store redundant metadata to simplify troubleshooting
    meta = (sensor.get("meta") or {}) | {"house_id": house_id, "box": box.get("name")}
    payload = {
        "name": f"{box['name']}_{sensor['name']}",
        "type": sensor["type"],
        "location": box.get("location"),
        "metadata": meta,
    }
    if serial:
        payload["serial_number"] = serial

    print("POST", url, "payload.serial_number=", payload.get("serial_number"))
    r = await client.post(url, json=payload)
    r.raise_for_status()
    return r.json()

# -------------------- Configuration fetch (with cache) --------------------
async def fetch_config_raw(sensor_id: str, retries: int = 4, delay: float = 0.25) -> dict:
    client = await get_client()
    for i in range(retries):
        try:
            r = await client.get(f"{SERVER}/sensors/{sensor_id}")
            if r.status_code == 200:
                data = r.json()
                cfg = data.get("meta") or data.get("metadata") or {}
                return cfg or {}
            return {}
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.ReadTimeout):
            await asyncio.sleep(delay * (2 ** i))
    return {}

async def fetch_config_with_cache(sensor_id: str) -> dict:
    now = time.monotonic()
    hit = _cfg_cache.get(sensor_id)
    if hit and hit[1] > now:
        return hit[0]
    cfg = await fetch_config_raw(sensor_id)
    if not isinstance(cfg, dict):
        cfg = {}
    _cfg_cache[sensor_id] = (cfg, now + CFG_TTL_SEC)
    return cfg

# -------------------- Alignment scheduler (whole minute + stable phase) --------------------
def _next_tick(anchor: float, period: float) -> float:
    now = time.time()
    k = math.floor((now - anchor) / period) + 1
    return anchor + k * period

async def _sleep_until(ts_epoch: float):
    delay = ts_epoch - time.time()
    if delay > 0:
        await asyncio.sleep(delay)

def _stable_phase_seconds(sensor_id: str, max_ms: int) -> float:
    h = hashlib.md5(sensor_id.encode("utf-8")).hexdigest()
    ms = int(h, 16) % max_ms
    return ms / 1000.0

# -------------------- Write readings (with retry + concurrency throttling) --------------------
def _should_retry_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599

async def send_reading_with_retry(sensor_id: str, value: float, attributes: dict | None = None, max_retries: int = 3) -> bool:
    client = await get_client()
    sem = _get_sema()

    # Assemble payload (ensure it stays serializable)
    payload = {"sensor_id": str(sensor_id), "value": float(value), "attributes": {}}
    if attributes:
        for k, v in attributes.items():
            payload["attributes"][k] = v if isinstance(v, (str, int, float, bool)) or v is None else str(v)

    for attempt in range(max_retries + 1):
        try:
            async with sem:
                r = await client.post(f"{SERVER}/ingest", json=payload)
            if r.status_code < 300:
                return True
            if _should_retry_status(r.status_code) and attempt < max_retries:
                await asyncio.sleep((0.25 * (2 ** attempt)) + random.uniform(0, 0.25))
                continue
            else:
                print(f"[WARN] ingest HTTP {r.status_code}: {r.text[:200]}")
                return False
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            if attempt < max_retries:
                await asyncio.sleep((0.25 * (2 ** attempt)) + random.uniform(0, 0.25))
                continue
            print(f"[WARN] ingest network error: {e!r}")
            return False
        except Exception as e:
            print(f"[WARN] ingest unexpected error: {e!r}")
            return False

# -------------------- Sensor loop (runs every period and keeps going on failure) --------------------
async def sensor_worker(box_def: dict, s: dict, server_obj: dict, box_env: BoxEnvironment):
    sid = server_obj["id"]                          # Sensor UUID returned by the server
    phase = _stable_phase_seconds(sid, PHASE_MAX_MS)  # Stable phase within 0~PHASE_MAX_MS milliseconds
    anchor = 0.0                                    # Align with Unix epoch → whole minutes/5 minutes etc.

    # Align the first tick to "aligned period + stable phase"
    first_tick = _next_tick(anchor, PERIOD_SEC) + phase
    await _sleep_until(first_tick)

    while True:
        dt = datetime.now(timezone.utc)
        try:
            # Skip this cycle if disabled
            if not s.get("enabled", True):
                next_tick = _next_tick(anchor, PERIOD_SEC) + phase
                await _sleep_until(next_tick)
                continue

            # Generate value: read cached config first, fall back to definition defaults
            cfg = await fetch_config_with_cache(sid)
            base = s.get("meta") or {}
            lo = float(cfg.get("min", base.get("min", 0)))
            hi = float(cfg.get("max", base.get("max", 1)))
            if hi < lo:
                lo, hi = hi, lo

            field = TYPE_TO_FIELD.get(s["type"])
            if field:
                dt = datetime.now(timezone.utc)
                reading = await box_env.read(dt)
                raw_value = reading.get(field)
                if raw_value is None:
                    raise KeyError(f"simulator missing field {field}")
                value = float(raw_value)
            else:
                value = random.uniform(lo, hi)

            value = min(hi, max(lo, value))
        except Exception as e:
            print(f"[WARN] gen value failed for {sid}: {e}")
            value = 0.0

        serial_attr = s.get("serial") or s.get("serial_number") or box_def.get("serial_number")
        attributes = {
            "unit": s["type"],
            "box": box_def["name"],
            "serial_number": serial_attr,
        }
        if TYPE_TO_FIELD.get(s["type"]):
            attributes |= {
                "simulated": True,
                "sim_profile": box_env.sim.profile,
                "sample_time": dt.isoformat(),
            }
        else:
            attributes["simulated"] = False

        ok = await send_reading_with_retry(
            sid,
            value,
            attributes,
        )
        print(time.strftime("[%Y-%m-%d %H:%M:%S]"),
              f"{box_def['name']} {s['name']} -> {value:.2f} (phase {phase*1000:.0f}ms) ok={ok}")

        # Sleep until the next "aligned period + stable phase"
        next_tick = _next_tick(anchor, PERIOD_SEC) + phase
        await _sleep_until(next_tick)

# -------------------- Box main flow --------------------
async def simulate_box(box_def: dict):
    await get_client()  # Initialize HTTP client
    house_id = await resolve_house_id(box_def)

    # 1) Create every sensor
    sensors = []
    for s in (box_def.get("sensors") or []):
        resp = await create_sensor(box_def, s, house_id)
        sensors.append({"def": s, "server": resp})
        print(f"Created {resp['name']} id={resp['id']} enabled={s.get('enabled', True)}")

    # 2) One task per sensor: minute alignment + stable phase + throttling + retry
    box_env = get_box_environment(box_def)
    tasks = [
        asyncio.create_task(sensor_worker(box_def, s["def"], s["server"], box_env))
        for s in sensors
    ]
    await asyncio.gather(*tasks)

# -------------------- Entry point --------------------
def _box_signature(box_def: dict) -> str:
    try:
        return hashlib.sha1(json.dumps(box_def, sort_keys=True).encode("utf-8")).hexdigest()
    except TypeError:
        return hashlib.sha1(str(box_def).encode("utf-8")).hexdigest()


class _BoxRunner:
    def __init__(self, box_def: dict, key: str):
        self.box_def = box_def
        self.key = key
        self.signature = _box_signature(box_def)
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        backoff = 5.0
        while True:
            try:
                await simulate_box(self.box_def)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep simulator resilient
                print(
                    f"[WARN] Box {self.key} run failed: {exc}; retrying in {int(backoff)}s",
                    flush=True,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            else:
                backoff = 5.0

    async def stop(self):
        if self._task.done():
            with suppress(Exception):
                self._task.result()
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task


class _SimulationManager:
    def __init__(self):
        self._runners: dict[str, _BoxRunner] = {}
        self._global_signature: tuple[str, float, int, int] | None = None

    async def apply_config(self, config: dict):
        global SERVER, PERIOD_SEC, PHASE_MAX_MS, MAX_INFLIGHT, _sema

        SERVER = config.get("server_url", SERVER)
        PERIOD_SEC = float(config.get("period_seconds", PERIOD_SEC))
        PHASE_MAX_MS = int(config.get("phase_max_ms", PHASE_MAX_MS))
        MAX_INFLIGHT = int(config.get("max_inflight", MAX_INFLIGHT))
        _sema = asyncio.Semaphore(MAX_INFLIGHT)

        globals_sig = (SERVER, PERIOD_SEC, PHASE_MAX_MS, MAX_INFLIGHT)
        if self._global_signature and self._global_signature != globals_sig:
            await self._stop_all()
        self._global_signature = globals_sig

        boxes = config.get("boxes") or []
        seen_keys: set[str] = set()
        for idx, raw_box in enumerate(boxes):
            if not isinstance(raw_box, dict):
                continue
            key = str(raw_box.get("serial_number") or raw_box.get("name") or f"box_{idx}")
            seen_keys.add(key)

            if not raw_box.get("registered", False):
                print(f"Box {key} is not registered; waiting for next poll")
                runner = self._runners.pop(key, None)
                if runner:
                    await runner.stop()
                continue

            runner = self._runners.get(key)
            signature = _box_signature(raw_box)
            if runner and runner.signature == signature:
                continue

            if runner:
                await runner.stop()

            box_copy = json.loads(json.dumps(raw_box))
            self._runners[key] = _BoxRunner(box_copy, key)

        for key in list(self._runners.keys()):
            if key not in seen_keys:
                runner = self._runners.pop(key)
                await runner.stop()

    async def _stop_all(self):
        runners = list(self._runners.values())
        self._runners.clear()
        for runner in runners:
            await runner.stop()



manager = _SimulationManager()
POLL_INTERVAL = float(os.environ.get("SIMULATION_CONFIG_POLL_INTERVAL", "60.0"))
app = FastAPI(title="Simulation Service")
_poll_task: asyncio.Task | None = None


class FieldUpdate(BaseModel):
    action: Literal["set", "clear"]
    value: Any | None = None


class FieldState(BaseModel):
    present: bool
    value: Any | None = None


class RegistrationUpdate(BaseModel):
    serial_number: str
    house_id: FieldUpdate
    registered: FieldUpdate


class RegistrationUpdateResponse(BaseModel):
    previous_state: dict[str, FieldState]


def _write_config_file(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CONFIG_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    try:
        os.replace(tmp_path, CONFIG_PATH)
    except OSError as exc:  # pragma: no cover - requires docker bind mount
        if exc.errno != errno.EBUSY:
            raise

        # When CONFIG_PATH is a bind mount (as in docker-compose), the path is a
        # mount point and can't be replaced atomically. Fall back to copying the
        # contents into the mounted file instead.
        with tmp_path.open("r", encoding="utf-8") as src, CONFIG_PATH.open(
            "w", encoding="utf-8"
        ) as dst:
            shutil.copyfileobj(src, dst)

        tmp_path.unlink(missing_ok=True)


def _apply_field_update(target: dict[str, Any], key: str, update: FieldUpdate) -> FieldState:
    present = key in target
    previous_value = target.get(key)
    if update.action == "set":
        target[key] = update.value
    else:
        target.pop(key, None)
    return FieldState(present=present, value=previous_value if present else None)


@app.post("/api/simulation/register", response_model=RegistrationUpdateResponse)
async def update_registration(payload: RegistrationUpdate):
    print("1")
    async with CONFIG_LOCK:
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="Simulation config file not found") from exc
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="Simulation config file is invalid") from exc

        boxes = data.get("boxes")
        if not isinstance(boxes, list):
            raise HTTPException(status_code=500, detail="Simulation config file is missing sensor boxes")

        target_box: dict[str, Any] | None = None
        for box in boxes:
            if isinstance(box, dict) and box.get("serial_number") == payload.serial_number:
                target_box = box
                break

        if target_box is None:
            raise HTTPException(status_code=404, detail="Serial number not found in simulation config")

        previous_state = {
            "house_id": _apply_field_update(target_box, "house_id", payload.house_id),
            "registered": _apply_field_update(target_box, "registered", payload.registered),
        }

        _write_config_file(data)

    try:
        await manager.apply_config(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to apply config: {exc}") from exc

    return RegistrationUpdateResponse(previous_state=previous_state)


async def _poll_config_forever():
    while True:
        config = await _load_config()
        if config:
            try:
                await manager.apply_config(config)
            except Exception as exc:  # noqa: BLE001
                print(f"[ERROR] Failed to apply config: {exc}")
        else:
            await manager._stop_all()
        await asyncio.sleep(POLL_INTERVAL)


@app.on_event("startup")
async def _on_startup() -> None:
    global _poll_task
    _poll_task = asyncio.create_task(_poll_config_forever())


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    global _poll_task
    if _poll_task:
        _poll_task.cancel()
        with suppress(asyncio.CancelledError):
            await _poll_task
        _poll_task = None
    await manager._stop_all()


async def _load_config() -> dict | None:
    async with CONFIG_LOCK:
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            print(f"Simulation config file {CONFIG_PATH} not found; retrying later")
        except json.JSONDecodeError as exc:
            print(f"Failed to parse simulation config: {exc}")
    return None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "simulation:app",
        host="0.0.0.0",
        port=int(os.environ.get("SIMULATION_PORT", "8001")),
    )
