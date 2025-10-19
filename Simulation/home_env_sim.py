# home_env_sim.py
# Realistic ESP "read" generator for at-risk homes with arbitrary time windows.
# Profiles: "healthy", "intermittent", "chronic" (most at-risk).
# Battery continuity across days is enforced (per-day drain rate).

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math, random

# -------------------- Field schema (one source of truth) --------------------

@dataclass(frozen=True)
class FieldSpec:
    name: str
    unit: str
    lo: float
    hi: float
    scale: float     # multiply before integer cast
    signed: bool     # int16 if True, else uint16

FIELDS = [
    FieldSpec("serial","-",0,65535,1,False),
    FieldSpec("temp_c","°C",-40.0,85.0,100,True),           # ×100, int16
    FieldSpec("rh_pct","%RH",0.0,100.0,100,False),          # ×100
    FieldSpec("co2_ppm","ppm",400.0,10000.0,1,False),       # ×1
    FieldSpec("o2_pct","%vol",0.0,25.0,100,False),          # ×100
    FieldSpec("co_ppm","ppm",0.0,500.0,10,False),           # ×10 (1dp)
    FieldSpec("pm25_ugm3","µg/m³",0.0,1000.0,1,False),      # ×1
    FieldSpec("noise_dba","dBA",30.0,130.0,10,False),       # ×10 (0.1 dB)
    FieldSpec("no2_ppb","ppb",5.0,80.0,1,False),            # ×1
    FieldSpec("lux","lux",0.0,88000.0,1,False),             # ×1 (saturates to 65535 on encode)
    FieldSpec("bat_mv","mV",3200.0,4300.0,1,False),         # ×1
]

IDX = {f.name: i for i, f in enumerate(FIELDS)}

# -------------------- Utility helpers --------------------

def _clip(name: str, v: float) -> float:
    f = FIELDS[IDX[name]]
    return max(f.lo, min(f.hi, v))

def _lp(prev: float, target: float, alpha: float) -> float:
    """One-pole low-pass filter (alpha in (0,1])."""
    return (1 - alpha) * prev + alpha * target

# Approximate daylight length (hours) by day-of-year (rough but good enough for realism)
def _daylength_hours(doy: int, amplitude: float = 4.0) -> float:
    # 12h ± amplitude; peak ~DOY 172 (June solstice in S hemisphere negative but acceptable here)
    return 12.0 + amplitude * math.sin(2 * math.pi * (doy - 80) / 365.0)

def _sunrise_sunset(d: datetime) -> tuple[float, float]:
    # Return sunrise, sunset as decimal hours local time (0..24). Center day around 12:30 for "midday".
    doy = int(d.timetuple().tm_yday)
    L = _daylength_hours(doy)
    center = 12.5
    rise = center - L / 2
    set_  = center + L / 2
    return max(0.0, rise), min(24.0, set_)

def _occupancy_factor(hour: float, weekday: int, rng: random.Random, profile: str) -> float:
    """
    0..1 factor for 'people at home' (drives CO2, RH, noise). Weekends busier. Intermittent homes
    may have higher night occupancy; chronic have higher all day (poor ventilation/overcrowding).
    """
    wknd = weekday in (5, 6)
    # Base curve: high evening/night, low midday on weekdays
    if wknd:
        base = 0.65 + 0.25 * (hour >= 20 or hour < 8) + 0.1 * (10 <= hour <= 16)
    else:
        base = (0.75 if (hour >= 20 or hour < 7) else (0.4 if 9 <= hour < 17 else 0.55))
    # Profile bias
    if profile == "healthy":
        base -= 0.1
    elif profile == "chronic":
        base += 0.15
    # Gentle daily jitter
    base += rng.uniform(-0.05, 0.05)
    return min(1.0, max(0.0, base))

# -------------------- Event model --------------------

class _Event:
    def __init__(self, kind: str, duration_min: int):
        self.kind = kind
        self.remaining = duration_min
        self.duration0 = duration_min  # for symmetric triangular envelope

    def weight(self) -> float:
        # Triangular envelope 0..1
        if self.duration0 <= 0: return 0.0
        phase = 1.0 - abs(0.5 - min(1.0, self.remaining / self.duration0)) * 2.0
        return max(0.0, phase)

# -------------------- Simulator --------------------

class HomeEnvSim:
    """
    Generate ESP read dicts with realistic dynamics for any chosen 12h window.
    Call next_read(dt) with monotonically increasing datetimes (any start time).
    Battery continuity across days is maintained by a per-day drain rate that
    changes only at midnight (with small day-to-day jitter).
    """

    # Max per-step change to prevent unrealistic jumps (for 5–10 min sampling)
    MAX_STEP = {
        "temp_c":     0.6,
        "rh_pct":     3.0,
        "co2_ppm":    130.0,
        "o2_pct":     0.08,
        "co_ppm":     10.0,
        "pm25_ugm3":  25.0,
        "noise_dba":  7.0,
        "no2_ppb":    9.0,
        "lux":        2000.0,
        "bat_mv":     5.0,
    }

    def __init__(
        self,
        profile: str = "intermittent",     # "healthy" | "intermittent" | "chronic"
        period_minutes: int = 5,
        start_bat_mv: float = 4300.0,
        serial: int | None = None,
        seed: int | None = None,
        daily_battery_drop_mv_mean: float = 100.0,  # ~100 mV/day example
    ):
        self.profile = profile.lower()
        self.period_minutes = int(period_minutes)
        self.rng = random.Random(seed if seed is not None else random.randrange(1 << 30))
        self.serial = self.rng.randint(0, 65535) if serial is None else int(serial)

        # Internal state
        self.state = {
            "temp_c":    self.rng.uniform(14, 19),
            "rh_pct":    self.rng.uniform(50, 65),
            "co2_ppm":   self.rng.uniform(500, 900),
            "o2_pct":    20.9,
            "co_ppm":    self.rng.uniform(0.0, 2.0),
            "pm25_ugm3": self.rng.uniform(5, 15),
            "noise_dba": self.rng.uniform(35, 55),
            "no2_ppb":   self.rng.uniform(8, 24),
            "lux":       self.rng.uniform(50, 500),
        }

        # Events & timing
        self.events: list[_Event] = []
        self.last_time: datetime | None = None

        # Battery model (continuity across days)
        self.bat_mv = float(start_bat_mv)
        self._day_drop_mean = float(daily_battery_drop_mv_mean)
        self._current_day_rate = None   # mV/day
        self._current_day = None        # (year, doy)

    # -------------------- private pieces --------------------

    def _ensure_day_rate(self, when: datetime):
        year, doy = when.year, when.timetuple().tm_yday
        key = (year, doy)
        if key != self._current_day:
            # New day's drain rate: N(mean, 10mV) clipped to [0.7, 1.3]×mean
            jitter = self.rng.gauss(0, 10.0)
            rate = max(0.7, min(1.3, (self._day_drop_mean + jitter) / self._day_drop_mean)) * self._day_drop_mean
            self._current_day_rate = rate  # mV/day
            self._current_day = key

    def _advance_battery(self, delta_min: float, when: datetime):
        """
        Decrease battery by integrating per-day rate across midnight boundaries.
        """
        if delta_min <= 0: return
        t = self.last_time if self.last_time else when - timedelta(minutes=delta_min)
        remaining = delta_min
        while remaining > 0:
            self._ensure_day_rate(t)
            # minutes until local midnight
            end_of_day = (t.replace(hour=23, minute=59, second=59, microsecond=999999))
            minutes_to_eod = (end_of_day - t).total_seconds() / 60.0 + 1e-6
            step = min(remaining, minutes_to_eod)
            per_min = self._current_day_rate / 1440.0
            self.bat_mv = max(FIELDS[IDX["bat_mv"]].lo, self.bat_mv - per_min * step)
            t += timedelta(minutes=step)
            remaining -= step

    def _maybe_start_events(self, hour: float, weekday: int, occ: float):
        r = self.rng.random
        # Cooking: breakfast (6.5–8.5) small; dinner (17–20.5) larger. Only if someone is home.
        if 6.5 <= hour < 8.5 and occ > 0.4 and r() < 0.06:
            self.events.append(_Event("cook_small", self.rng.randint(10, 25)))
        if 17.0 <= hour < 20.5 and occ > 0.4 and r() < 0.14:
            self.events.append(_Event("cook_big", self.rng.randint(20, 60)))

        # Shower (6–8.5 and 21–23): humidity burst
        if (6.0 <= hour < 8.5 or 21.0 <= hour < 23.0) and occ > 0.3 and r() < 0.08:
            self.events.append(_Event("shower", self.rng.randint(8, 20)))

        # Ventilation (window open) any time: reduces CO2/RH, cools slightly
        if r() < 0.035:
            self.events.append(_Event("vent", self.rng.randint(10, 45)))

        # Outdoor infiltration (traffic/dust) daytime
        if 7.0 <= hour < 19.0 and r() < 0.025:
            self.events.append(_Event("infiltration", self.rng.randint(15, 45)))

        # Crowded sleep (intermittent/chronic) late night
        if (self.profile in ("intermittent","chronic")) and (hour >= 22 or hour < 6) and r() < 0.05:
            self.events.append(_Event("crowded_night", self.rng.randint(60, 210)))

    def _event_deltas(self) -> dict[str, float]:
        add = {k: 0.0 for k in self.state.keys()}
        done = []
        for ev in self.events:
            w = ev.weight()
            if ev.kind == "cook_small":
                add["pm25_ugm3"] += 60.0 * w
                add["no2_ppb"]   += 12.0 * w
                add["co_ppm"]    += 2.5  * w
                add["co2_ppm"]   += 120.0* w
                add["noise_dba"] += 4.0  * w
                add["temp_c"]    += 0.2  * w
            elif ev.kind == "cook_big":
                add["pm25_ugm3"] += 140.0 * w
                add["no2_ppb"]   += 30.0  * w
                add["co_ppm"]    += 6.0   * w
                add["co2_ppm"]   += 280.0 * w
                add["noise_dba"] += 7.0   * w
                add["temp_c"]    += 0.4   * w
            elif ev.kind == "shower":
                add["rh_pct"]    += 20.0  * w
            elif ev.kind == "vent":
                add["co2_ppm"]   -= 260.0 * w
                add["rh_pct"]    -= 9.0   * w
                add["temp_c"]    -= 0.7   * w
            elif ev.kind == "infiltration":
                add["pm25_ugm3"] += 25.0  * w
                add["no2_ppb"]   += 10.0  * w
                add["noise_dba"] += 3.0   * w
            elif ev.kind == "crowded_night":
                add["co2_ppm"]   += 340.0 * w
                add["rh_pct"]    += 6.0   * w

            # advance event time
            ev.remaining = max(0, ev.remaining - self.period_minutes)
            if ev.remaining == 0: done.append(ev)
        for e in done:
            self.events.remove(e)
        return add

    # -------------------- the main step --------------------

    def next_read(self, dt: datetime) -> dict:
        """
        Generate one ESP 'read' at the requested datetime (engineering units).
        Call with monotonically increasing dt (any start time / any 12h window).
        """
        dt = dt.astimezone() if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc).astimezone()
        hour = dt.hour + dt.minute / 60.0
        weekday = dt.weekday()

        # Battery continuity across elapsed minutes
        if self.last_time is None:
            elapsed_min = 0.0
        else:
            elapsed_min = max(0.0, (dt - self.last_time).total_seconds() / 60.0)
        self._advance_battery(elapsed_min, dt)
        self.last_time = dt

        # Daylight & indoor light
        sunrise, sunset = _sunrise_sunset(dt)
        is_day = sunrise <= hour < sunset
        # indoor daylight proxy (typical indoors << outdoor)
        day_lux = 800.0 if 9 <= hour < 17 else 400.0
        night_lux = 40.0 if 22 <= hour or hour < 6 else 120.0
        lux_target = day_lux if is_day else night_lux

        # Occupancy & profile
        occ = _occupancy_factor(hour, weekday, self.rng, self.profile)
        self._maybe_start_events(hour, weekday, occ)

        # Baselines by profile
        if self.profile == "healthy":
            t_base_night, t_base_day = 18.5, 20.0
            rh_base = 50.0
            vent_base = 0.006  # 0.36 h^-1 equivalent
        elif self.profile == "chronic":  # persistently under-heated & damp, low ventilation
            t_base_night, t_base_day = 11.5, 15.0
            rh_base = 70.0
            vent_base = 0.002  # very poor ventilation
        else:  # intermittent at-risk (some periods unhealthy)
            t_base_night, t_base_day = 12.5, 17.0
            rh_base = 58.0
            vent_base = 0.004

        temp_target = t_base_day if 9 <= hour < 18 else t_base_night
        temp_target += 0.8 * math.sin((hour - 16.0) * math.pi / 12.0)  # afternoon bump

        rh_target = rh_base + 6.0 * math.sin((hour - 5.0) * math.pi / 12.0)

        # CO2 dynamics (ppm/min): generation proportional to occupancy
        outdoor_co2 = 420.0
        co2_gen = (1.8 + 1.2 * occ)  # ppm/min per "household"
        if self.profile == "chronic": co2_gen *= 1.4
        if weekday in (5,6): co2_gen *= 1.15   # weekends busier

        # Apply event deltas (bumps/dips)
        ev = self._event_deltas()

        # --- Update channels with smoothing + step caps ---
        alpha = 0.28  # smoothing
        new = dict(self.state)

        # Light
        target = lux_target + self.rng.gauss(0, 60.0) + ev.get("lux", 0.0)
        target = max(0.0, target)
        target = self._cap_step("lux", new["lux"], target)
        new["lux"] = _clip("lux", _lp(new["lux"], target, alpha))

        # Temperature
        target = temp_target + ev.get("temp_c", 0.0) + self.rng.gauss(0, 0.12)
        target = self._cap_step("temp_c", new["temp_c"], target)
        new["temp_c"] = _clip("temp_c", _lp(new["temp_c"], target, alpha))

        # Humidity (RH): base + occupancy moisture + events - ventilation drying
        rh_occ = 2.5 * occ
        rh_vent = -10.0 * (ev.get("co2_ppm", 0.0) < 0)  # if venting event, RH dips
        target = rh_target + rh_occ + rh_vent + ev.get("rh_pct", 0.0) + self.rng.gauss(0, 0.9)
        target = self._cap_step("rh_pct", new["rh_pct"], target)
        new["rh_pct"] = _clip("rh_pct", _lp(new["rh_pct"], target, alpha))

        # CO2 (first-order with ventilation sink)
        dt_min = max(self.period_minutes, 1)
        co2 = new["co2_ppm"]
        # base ventilation sink
        k = vent_base
        if ev.get("co2_ppm", 0.0) < 0:   # extra venting during window open
            k += 0.02
        # discrete update
        co2_target = co2 + dt_min * (co2_gen + ev.get("co2_ppm", 0.0)) - dt_min * k * (co2 - outdoor_co2)
        co2_target += self.rng.gauss(0, 15.0)
        co2_target = self._cap_step("co2_ppm", co2, co2_target)
        new["co2_ppm"] = _clip("co2_ppm", _lp(co2, co2_target, 0.45))

        # O2 inverse to CO2 (tight bounds)
        new["o2_pct"] = _clip("o2_pct", 20.9 - (new["co2_ppm"] - 420.0) / 20000.0 + self.rng.uniform(-0.02, 0.02))

        # PM2.5 decay + events
        pm = new["pm25_ugm3"]
        pm_decay = math.exp(-dt_min / 80.0)  # ~80 min time constant indoors
        pm_target = pm * pm_decay + ev.get("pm25_ugm3", 0.0) + self.rng.gauss(0, 2.0)
        pm_target = self._cap_step("pm25_ugm3", pm, pm_target)
        new["pm25_ugm3"] = _clip("pm25_ugm3", _lp(pm, pm_target, 0.5))

        # NO2 decay + events
        no2 = new["no2_ppb"]
        no2_decay = math.exp(-dt_min / 120.0)  # slower decay
        no2_target = no2 * no2_decay + ev.get("no2_ppb", 0.0) + self.rng.gauss(0, 1.0)
        no2_target = self._cap_step("no2_ppb", no2, no2_target)
        new["no2_ppb"] = _clip("no2_ppb", _lp(no2, no2_target, 0.45))

        # CO small spikes + decay
        co = new["co_ppm"]
        co_decay = math.exp(-dt_min / 70.0)
        co_target = co * co_decay + ev.get("co_ppm", 0.0) + max(0.0, self.rng.gauss(0.05, 0.08))
        co_target = self._cap_step("co_ppm", co, co_target)
        new["co_ppm"] = _clip("co_ppm", _lp(co, co_target, 0.45))

        # Noise
        base_noise = 38.0 if (hour >= 23 or hour < 6) else (46.0 + 6.0 * occ)
        noise_target = base_noise + ev.get("noise_dba", 0.0) + max(0.0, self.rng.gauss(0.0, 1.2))
        noise_target = self._cap_step("noise_dba", new["noise_dba"], noise_target)
        new["noise_dba"] = _clip("noise_dba", _lp(new["noise_dba"], noise_target, 0.35))

        # Commit state
        self.state = new

        # Assemble the ESP read
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

    # cap helper
    def _cap_step(self, name: str, prev: float, target: float) -> float:
        cap = self.MAX_STEP[name]
        dv = target - prev
        if dv > cap:   return prev + cap
        if dv < -cap:  return prev - cap
        return target

    # Convenience for a 12h (or any) window
    def generate_window(self, start: datetime, hours: float = 12.0) -> list[tuple[datetime, dict]]:
        steps = int(round(hours * 60 / self.period_minutes))
        t = start
        out = []
        for _ in range(steps):
            out.append((t, self.next_read(t)))
            t += timedelta(minutes=self.period_minutes)
        return out
