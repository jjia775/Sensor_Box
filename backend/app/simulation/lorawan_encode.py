# lorawan_encode.py
# Scale and pack ESP reads into a 22-byte LoRaWAN payload (network byte order).

from __future__ import annotations
import struct
from dataclasses import dataclass

@dataclass(frozen=True)
class FieldSpec:
    name: str; unit: str; lo: float; hi: float; scale: float; signed: bool

FIELDS = [
    FieldSpec("serial","-",0,65535,1,False),
    FieldSpec("temp_c","°C",-40.0,85.0,100,True),
    FieldSpec("rh_pct","%RH",0.0,100.0,100,False),
    FieldSpec("co2_ppm","ppm",400.0,10000.0,1,False),
    FieldSpec("o2_pct","%vol",0.0,25.0,100,False),
    FieldSpec("co_ppm","ppm",0.0,500.0,10,False),
    FieldSpec("pm25_ugm3","µg/m³",0.0,1000.0,1,False),
    FieldSpec("noise_dba","dBA",30.0,130.0,10,False),
    FieldSpec("no2_ppb","ppb",5.0,80.0,1,False),
    FieldSpec("lux","lux",0.0,88000.0,1,False),
    FieldSpec("bat_mv","mV",3200.0,4300.0,1,False),
]
IDX = {f.name: i for i, f in enumerate(FIELDS)}

def _clip(name: str, v: float) -> float:
    f = FIELDS[IDX[name]]
    return max(f.lo, min(f.hi, v))

def _to_int(v: float, spec: FieldSpec) -> int:
    scaled = round(v * spec.scale)
    if spec.signed:
        return max(-32768, min(32767, int(scaled)))
    return max(0, min(65535, int(scaled)))

def encode_lorawan(esp: dict) -> bytes:
    """
    Payload order (22 bytes total):
      [serial u16][temp i16][rh u16][co2 u16][o2 u16][co u16]
      [pm25 u16][noise u16][no2 u16][lux u16][bat u16]
    Lux is saturated to 65535 at packing time (sensor may read up to 88000).
    """
    ints = []
    for spec in FIELDS:
        raw = esp[spec.name]
        if spec.name != "serial":
            raw = _clip(spec.name, float(raw))
            if spec.name == "lux":  # LoRaWAN uint16 ceiling
                raw = min(raw, 65535.0)
        ints.append(_to_int(raw, spec))

    fmt = ">Hh" + "H" * (len(FIELDS) - 2)
    return struct.pack(fmt, ints[0], ints[1], *ints[2:])

def to_hex(payload: bytes) -> str:
    return payload.hex().upper()
