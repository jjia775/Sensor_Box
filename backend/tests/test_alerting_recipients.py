from app import alerting


class _DummyServer:
    def __init__(self):
        self.sent_messages = []

    def send_message(self, message):
        self.sent_messages.append(message)

    def quit(self):
        pass


def _smtp_settings():
    return alerting.SMTPSettings(
        host="smtp.example.com",
        port=25,
        use_ssl=False,
        use_starttls=False,
        user="",
        password="",
        from_addr="noreply@example.com",
        to_addrs=["admin@example.com"],
        timeout=10,
        debug=False,
    )


def _threshold_event(**kwargs):
    defaults = dict(
        metric="temp",
        value=30.0,
        threshold=25.0,
        threshold_kind="upper",
        label="Test",
        unit="°C",
        sensor_id="sensor-1",
        sensor_name="Sensor 1",
        sensor_serial="ABC123",
    )
    defaults.update(kwargs)
    return alerting.ThresholdBreach(**defaults)


def test_send_all_prefers_event_specific_recipients(monkeypatch):
    server = _DummyServer()
    monkeypatch.setattr(alerting, "_open_smtp_connection", lambda settings: server)

    event = _threshold_event(recipients=("user@example.com",))
    alerting._send_all([event], _smtp_settings())

    assert len(server.sent_messages) == 1
    message = server.sent_messages[0]
    assert message["To"] == "user@example.com"


def test_send_all_falls_back_to_default_recipients(monkeypatch):
    server = _DummyServer()
    monkeypatch.setattr(alerting, "_open_smtp_connection", lambda settings: server)

    event = _threshold_event(recipients=None)
    alerting._send_all([event], _smtp_settings())

    assert len(server.sent_messages) == 1
    message = server.sent_messages[0]
    assert message["To"] == "admin@example.com"
