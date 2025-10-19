# lorawan_decode.py
# Unpack 22-byte payload back into engineering units.

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

def decode_lorawan(payload: bytes) -> dict:
    if len(payload) != 2 * len(FIELDS):  # 22 bytes
        raise ValueError(f"Expected {2*len(FIELDS)} bytes, got {len(payload)}")
    fmt = ">Hh" + "H" * (len(FIELDS) - 2)
    vals = struct.unpack(fmt, payload)

    out = {}
    for spec, iv in zip(FIELDS, vals):
        if spec.name == "serial":
            out[spec.name] = int(iv)
        else:
            val = float(iv) / spec.scale
            # Clip back to physical range (lux limited to 65535 by encoder anyway)
            out[spec.name] = max(spec.lo, min(spec.hi if spec.name != "lux" else 65535.0, val))
    return out
