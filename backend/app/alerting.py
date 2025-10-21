"""Alerting helpers for threshold breaches."""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)


THRESHOLDS: dict[str, dict] = {
    "co": {"unit": "ppm", "lines": [{"label": "WHO 1-h", "kind": "upper", "value": 30.0}]},
    "co2": {"unit": "ppm", "lines": [{"label": "ASHRAE", "kind": "upper", "value": 1000.0}]},
    "light_night": {
        "unit": "lux",
        "lines": [
            {"label": "IES", "kind": "lower", "value": 100.0},
            {"label": "IES", "kind": "upper", "value": 200.0},
        ],
    },
    "no2": {"unit": "ppb", "lines": [{"label": "WHO 24-h", "kind": "upper", "value": 13.0}]},
    "noise_night": {"unit": "dB(A)", "lines": [{"label": "WHO night 8h", "kind": "upper", "value": 30.0}]},
    "o2": {"unit": "% vol", "lines": [{"label": "OSHA", "kind": "lower", "value": 19.5}]},
    "pm25": {"unit": "µg/m³", "lines": [{"label": "WHO 24-h", "kind": "upper", "value": 15.0}]},
    "rh": {
        "unit": "%",
        "lines": [
            {"label": "WHO/ASHRAE", "kind": "lower", "value": 30.0},
            {"label": "WHO/ASHRAE", "kind": "upper", "value": 60.0},
        ],
    },
    "temp": {
        "unit": "°C",
        "lines": [
            {"label": "WHO", "kind": "lower", "value": 18.0},
            {"label": "WHO", "kind": "upper", "value": 24.0},
        ],
    },
}


def get_metric_unit(metric: str) -> str:
    """Return the display unit configured for *metric*."""

    return THRESHOLDS.get(metric, {}).get("unit", "")


def evaluate_thresholds(metric: str, value: float) -> list[dict]:
    """Return the threshold entries that are breached by *value* for *metric*."""

    cfg = THRESHOLDS.get(metric)
    if not cfg:
        return []

    triggered: list[dict] = []
    for line in cfg.get("lines", []):
        try:
            threshold_value = float(line["value"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Invalid threshold configuration for metric '%s': %s", metric, line)
            continue

        kind = str(line.get("kind", "")).lower()
        if kind == "upper" and value > threshold_value:
            triggered.append(line)
        elif kind == "lower" and value < threshold_value:
            triggered.append(line)

    return triggered


@dataclass(frozen=True)
class ThresholdBreach:
    """Information about a breached threshold."""

    metric: str
    value: float
    threshold: float
    threshold_kind: str
    label: str
    unit: str
    sensor_id: str
    sensor_name: str | None
    sensor_serial: str | None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recipients: tuple[str, ...] | None = None


@dataclass
class SMTPSettings:
    host: str
    port: int
    use_ssl: bool
    use_starttls: bool
    user: str
    password: str
    from_addr: str
    to_addrs: list[str]
    timeout: int
    debug: bool


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_addresses(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def load_smtp_settings() -> SMTPSettings:
    """Load SMTP settings from the environment with sensible defaults."""

    to_raw = os.getenv("SMTP_TO", os.getenv("SMTP_TO_ADDR", "sensorbox2025@gmail.com"))
    to_addrs = _split_addresses(to_raw)

    return SMTPSettings(
        host=os.getenv("SMTP_HOST", "smtp-relay.brevo.com"),
        port=int(os.getenv("SMTP_PORT", "587")),
        use_ssl=_env_bool("SMTP_USE_SSL", False),
        use_starttls=_env_bool("SMTP_USE_STARTTLS", True),
        user=os.getenv("SMTP_USER", "96cd03001@smtp-brevo.com"),
        password=os.getenv("SMTP_PASSWORD", "HAYjKfgbwDa7pI8J"),
        from_addr=os.getenv("SMTP_FROM", "sensorbox2025@gmail.com"),
        to_addrs=to_addrs,
        timeout=int(os.getenv("SMTP_TIMEOUT", "15")),
        debug=_env_bool("SMTP_DEBUG", False),
    )


def get_admin_recipients() -> list[str]:
    """Return the configured admin e-mail recipients.

    Falls back to the standard SMTP recipients if dedicated admin addresses are
    not configured.
    """

    admin_raw = (
        os.getenv("ADMIN_EMAILS")
        or os.getenv("ADMIN_EMAIL")
        or os.getenv("SMTP_ADMIN_TO")
    )

    admin_addrs = _split_addresses(admin_raw)
    if admin_addrs:
        return admin_addrs

    return load_smtp_settings().to_addrs


def _format_subject(event: ThresholdBreach) -> str:
    direction = "above" if event.threshold_kind.lower() == "upper" else "below"
    return f"Alert: {event.metric} {direction} threshold"


def _format_body(event: ThresholdBreach) -> str:
    parts = [
        f"Metric: {event.metric}",
        f"Sensor name: {event.sensor_name or 'n/a'}",
        f"Sensor serial: {event.sensor_serial or 'n/a'}",
        f"Value: {event.value} {event.unit}".strip(),
        f"Threshold: {event.threshold_kind} {event.threshold} {event.unit}".strip(),
        f"Label: {event.label}" if event.label else None,
        f"Recorded at: {event.recorded_at.isoformat()}",
    ]
    return "\n".join(filter(None, parts))


def _open_smtp_connection(settings: SMTPSettings) -> smtplib.SMTP:
    context = ssl.create_default_context()
    if settings.use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.host, settings.port, timeout=settings.timeout, context=context
        )
    else:
        server = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout)

    if settings.debug:
        server.set_debuglevel(1)

    server.ehlo()
    if settings.use_starttls and not settings.use_ssl:
        server.starttls(context=context)
        server.ehlo()

    if settings.user and settings.password:
        server.login(settings.user, settings.password)

    return server


def _normalize_recipients(addresses: Sequence[str] | None) -> list[str]:
    if not addresses:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for addr in addresses:
        if not isinstance(addr, str):
            continue
        trimmed = addr.strip()
        if not trimmed or trimmed in seen:
            continue
        normalized.append(trimmed)
        seen.add(trimmed)
    return normalized


def _send_all(events: Sequence[ThresholdBreach], settings: SMTPSettings) -> None:
    if not events:
        return

    fallback_recipients = _normalize_recipients(settings.to_addrs)
    if not fallback_recipients:
        logger.info("No default SMTP recipients configured; relying on event-specific recipients")

    try:
        server = _open_smtp_connection(settings)
    except Exception:
        logger.exception("Failed to open SMTP connection")
        return

    try:
        for event in events:
            try:
                recipients = _normalize_recipients(event.recipients)
                if not recipients:
                    recipients = list(fallback_recipients)
                if not recipients:
                    logger.warning(
                        "No recipients configured for alert on metric '%s'; skipping",
                        event.metric,
                    )
                    continue
                msg = EmailMessage()
                msg["From"] = settings.from_addr
                msg["To"] = ", ".join(recipients)
                msg["Subject"] = _format_subject(event)
                msg.set_content(_format_body(event))
                server.send_message(msg)
            except Exception:
                logger.exception("Failed to send alert email for metric '%s'", event.metric)
    finally:
        try:
            server.quit()
        except Exception:
            logger.exception("Failed to close SMTP connection")


def _send_message(subject: str, body: str, settings: SMTPSettings, recipients: Sequence[str]) -> None:
    normalized_recipients = _normalize_recipients(recipients)
    if not normalized_recipients:
        logger.warning("No SMTP recipients configured; skipping email with subject '%s'", subject)
        return

    try:
        server = _open_smtp_connection(settings)
    except Exception:
        logger.exception("Failed to open SMTP connection")
        return

    try:
        msg = EmailMessage()
        msg["From"] = settings.from_addr
        msg["To"] = ", ".join(normalized_recipients)
        msg["Subject"] = subject
        msg.set_content(body)
        server.send_message(msg)
    except Exception:
        logger.exception("Failed to send email with subject '%s'", subject)
    finally:
        try:
            server.quit()
        except Exception:
            logger.exception("Failed to close SMTP connection")


async def send_simple_email(
    subject: str, body: str, to_addrs: Sequence[str] | None = None
) -> None:
    """Send a simple e-mail message using the configured SMTP settings."""

    settings = load_smtp_settings()
    recipients = _normalize_recipients(to_addrs or settings.to_addrs)
    if not recipients:
        logger.warning("No SMTP recipients configured; skipping email with subject '%s'", subject)
        return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_message, subject, body, settings, recipients)


async def dispatch_alerts(events: Sequence[ThresholdBreach]) -> None:
    """Send alert e-mails for the supplied threshold breaches."""

    if not events:
        return

    settings = load_smtp_settings()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_all, events, settings)


def iter_thresholds() -> Iterable[tuple[str, dict]]:
    """Utility for iterating thresholds; used by API endpoints."""

    return THRESHOLDS.items()

