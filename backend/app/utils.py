import re

def _normalize_name(s: str) -> str:
    return re.sub(r"[^A-Za-z]+", "", s or "").upper()

def build_house_id(zone: str, first_name: str, last_name: str, serial_number: str) -> str:
    zone_ = (zone or "").strip().upper()
    fn = _normalize_name(first_name)
    ln = _normalize_name(last_name)
    fn1 = (fn[:1] or "X")
    ln3 = (ln[:3] or "XXX").ljust(3, "X")
    digits = re.sub(r"\D", "", serial_number or "")
    tail3 = digits[-3:].rjust(3, "0")
    return f"{zone_}{fn1}{ln3}{tail3}"
