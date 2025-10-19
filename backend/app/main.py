# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from sqlalchemy import delete
#
# from app.db import AsyncSessionLocal
# from app.models import Sensor, SensorReading, Household
# from app.routers import (
#     sensors,
#     ingest,
#     readings,
#     register,
#     auth,
#     analytics,
#     diseases,
#     households,
# )
# from app.routers import ai
# import os
# from starlette.middleware.sessions import SessionMiddleware
# app = FastAPI()
# origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # frontend origins
#     allow_credentials=True,  # allow cookies to be sent
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# app.add_middleware(
#     SessionMiddleware,
#     secret_key="please-change-me",  # replace with a random long string
#     session_cookie="sid",           # optional custom cookie name
#     same_site="lax",                # use Lax for same-site traffic; use "none" + HTTPS when cross-site
#     https_only=False,               # set to True in production (HTTPS only)
# )
# app.include_router(sensors.router)
# app.include_router(ingest.router)
# app.include_router(readings.router)
#
# app.include_router(diseases.router)
#
# app.include_router(register.router)
#
# app.include_router(analytics.router)
#
# app.include_router(households.router)
#
# app.include_router(ai.router)
#
# # app.include_router(auth_router)
#
#
# @app.on_event("startup")
# async def clear_sensor_tables() -> None:
#     """Remove sensor metadata and readings on each application restart."""
#
#     async with AsyncSessionLocal() as session:
#         await session.execute(delete(SensorReading))
#         await session.execute(delete(Sensor))
#         await session.execute(delete(Household))
#         await session.commit()
#
#
# @app.get("/health")
# def health():
#     return {"ok": True}
#
#
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    sensors,
    ingest,
    readings,
    register,
    auth,
    analytics,
    diseases,
    households,
    ai,
)
import os
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# 允许从环境变量配置多个来源，逗号分隔
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "please-change-me"),
    session_cookie=os.getenv("SESSION_COOKIE", "sid"),
    same_site=os.getenv("SESSION_SAMESITE", "lax"),
    https_only=os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true",
)

# 路由注册
app.include_router(sensors.router)
app.include_router(ingest.router)
app.include_router(readings.router)
app.include_router(diseases.router)
app.include_router(register.router)
app.include_router(analytics.router)
app.include_router(households.router)
app.include_router(ai.router)

@app.get("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
