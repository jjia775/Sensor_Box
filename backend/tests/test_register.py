import asyncio
import sys
import types
from pathlib import Path

import pytest

fastapi_stub = types.ModuleType("fastapi")


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _APIRouter:
    def __init__(self, *args, **kwargs):
        pass

    def post(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


def _depends(dep):
    return dep


fastapi_stub.APIRouter = _APIRouter
fastapi_stub.Depends = _depends
fastapi_stub.HTTPException = _HTTPException
fastapi_stub.status = types.SimpleNamespace(
    HTTP_201_CREATED=201,
    HTTP_404_NOT_FOUND=404,
    HTTP_409_CONFLICT=409,
    HTTP_422_UNPROCESSABLE_ENTITY=422,
    HTTP_500_INTERNAL_SERVER_ERROR=500,
)

sys.modules.setdefault("fastapi", fastapi_stub)

httpx_stub = types.ModuleType("httpx")


class _Timeout:
    def __init__(self, *args, **kwargs):
        pass


class _RequestError(Exception):
    pass


class _AsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        raise NotImplementedError


httpx_stub.AsyncClient = _AsyncClient
httpx_stub.Timeout = _Timeout
httpx_stub.RequestError = _RequestError


class _Response:
    def __init__(self, status_code: int = 200, data=None, text: str = ""):
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


httpx_stub.Response = _Response

sys.modules.setdefault("httpx", httpx_stub)

sqlalchemy_stub = types.ModuleType("sqlalchemy")


class _Select:
    def __init__(self, *args, **kwargs):
        pass

    def where(self, *args, **kwargs):
        return self


def _select(*args, **kwargs):
    return _Select(*args, **kwargs)


sqlalchemy_stub.select = _select
sqlalchemy_ext_stub = types.ModuleType("sqlalchemy.ext")
sqlalchemy_ext_asyncio_stub = types.ModuleType("sqlalchemy.ext.asyncio")


class _AsyncSession:
    pass


sqlalchemy_ext_asyncio_stub.AsyncSession = _AsyncSession
sqlalchemy_stub.ext = types.SimpleNamespace(asyncio=sqlalchemy_ext_asyncio_stub)

sys.modules.setdefault("sqlalchemy", sqlalchemy_stub)
sys.modules.setdefault("sqlalchemy.ext", sqlalchemy_ext_stub)
sys.modules.setdefault("sqlalchemy.ext.asyncio", sqlalchemy_ext_asyncio_stub)

app_alerting_stub = types.ModuleType("app.alerting")


async def _send_simple_email(*args, **kwargs):
    return None


def _get_admin_recipients() -> list[str]:
    return []


app_alerting_stub.send_simple_email = _send_simple_email
app_alerting_stub.get_admin_recipients = _get_admin_recipients

app_schemas_stub = types.ModuleType("app.schemas")


class _RegisterIn:
    pass


class _RegisterOut:
    def __init__(self, house_id: str):
        self.house_id = house_id


app_schemas_stub.RegisterIn = _RegisterIn
app_schemas_stub.RegisterOut = _RegisterOut

app_models_stub = types.ModuleType("app.models")


class _Column:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return self


class _Household:
    serial_number = _Column("serial_number")
    house_id = _Column("house_id")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


app_models_stub.Household = _Household

app_db_stub = types.ModuleType("app.db")


def _get_db():
    return None


app_db_stub.get_db = _get_db

sys.modules.setdefault("app.alerting", app_alerting_stub)
sys.modules.setdefault("app.schemas", app_schemas_stub)
sys.modules.setdefault("app.models", app_models_stub)
sys.modules.setdefault("app.db", app_db_stub)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import register as register_module  # noqa: E402


class DummyResult:
    def scalars(self):
        return self

    def first(self):
        return None


class DummySession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return DummyResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class DummyRegisterData:
    def __init__(
        self,
        *,
        serial_number: str,
        first_name: str,
        last_name: str,
        phone: str,
        email: str,
        address: str,
        zone: str,
    ) -> None:
        self.serial_number = serial_number
        self.first_name = first_name
        self.last_name = last_name
        self.phone = phone
        self.email = email
        self.address = address
        self.zone = zone


def _make_default_register_data() -> DummyRegisterData:
    return DummyRegisterData(
        serial_number="SNBOX001",
        first_name="Jane",
        last_name="Doe",
        phone="123456",
        email="jane@example.com",
        address="123 Main St",
        zone="N",
    )


def test_register_updates_simulation(monkeypatch):
    session = DummySession()
    data = _make_default_register_data()

    email_calls: list[tuple] = []

    async def fake_send_simple_email(*args, **kwargs):
        email_calls.append((args, kwargs))

    monkeypatch.setattr(register_module, "send_simple_email", fake_send_simple_email)
    monkeypatch.setattr(register_module, "get_admin_recipients", lambda: ["admin@example.com"])

    calls: list[tuple] = []

    async def fake_update(serial_number, *, new_house_id, registered):
        calls.append((serial_number, new_house_id, registered))
        return {
            "house_id": register_module._MISSING,
            "registered": register_module._MISSING,
        }

    monkeypatch.setattr(register_module, "_update_simulation_registration", fake_update)

    result = asyncio.run(register_module.register(data, session))

    assert result.house_id
    assert session.committed is True
    assert session.rolled_back is False
    assert email_calls, "Expected registration to send an email notification"
    assert calls == [(data.serial_number, result.house_id, True)]


def test_register_rejects_unknown_serial(monkeypatch):
    session = DummySession()
    data = _make_default_register_data()

    async def fake_update(*args, **kwargs):
        raise register_module.SimulationConfigSerialNotFound()

    monkeypatch.setattr(register_module, "_update_simulation_registration", fake_update)
    monkeypatch.setattr(register_module, "send_simple_email", pytest.fail)

    with pytest.raises(register_module.HTTPException) as excinfo:
        asyncio.run(register_module.register(data, session))

    assert excinfo.value.status_code == 422
    assert session.committed is False
    assert session.rolled_back is False


def test_register_rolls_back_simulation_on_commit_failure(monkeypatch):
    calls: list[tuple] = []

    async def fake_update(serial_number, *, new_house_id, registered):
        calls.append((serial_number, new_house_id, registered))
        return {
            "house_id": register_module._MISSING,
            "registered": register_module._MISSING,
        }

    monkeypatch.setattr(register_module, "_update_simulation_registration", fake_update)

    class FailingSession(DummySession):
        async def commit(self):  # type: ignore[override]
            raise RuntimeError("db failure")

    session = FailingSession()
    data = _make_default_register_data()

    with pytest.raises(RuntimeError):
        asyncio.run(register_module.register(data, session))

    assert len(calls) == 2
    first_call, second_call = calls
    assert first_call[0] == data.serial_number
    assert first_call[2] is True
    assert second_call[0] == data.serial_number
    assert second_call[1] is register_module._MISSING
    assert second_call[2] is register_module._MISSING

