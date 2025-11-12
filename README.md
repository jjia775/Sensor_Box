# Indoor Environmental Quality (IEQ) Monitoring Platform

This repository contains the end-to-end stack for an indoor environmental quality monitoring solution, from the ESP32-based sensor boxes that communicate via LoRaWAN to the FastAPI backend, PostgreSQL database, and the React/Vite dashboard. It also includes a simulation harness for generating synthetic data and validating alerting flows.

## System Architecture Overview

```text
[Sensor Box]
  • ESP32 MCU with 9 IEQ modules (temperature, humidity, CO₂, O₂, CO, NO₂, PM2.5, light, noise)
  • Local sensor fusion + LoRaWAN uplink frames
        │
        ▼
[LoRaWAN Gateway]
  • Forwards uplinks to network server (TTN/ChirpStack) using MQTT/HTTP integration
        │
        ▼
[Backend Ingestion API (FastAPI)]
  • /ingest endpoints receive decoded payloads from the LoRa network server
  • Stores metadata in PostgreSQL (households, sensors, sensor_readings)
  • Publishes live updates via WebSocket channels for dashboards
  • Evaluates thresholds and triggers SMTP alerts to household contacts
        │
        ▼
[Analytics & Dashboard]
  • React/Vite frontend fetches REST + WebSocket data
  • Visualizes time series, parameter correlations, and risk heat maps
  • Sensor box registration workflow assigns unique house IDs
        │
        ▼
[Email/SMS Infrastructure]
  • FastAPI alerting module sends notifications through an SMTP relay
```

### Key Repository Directories

| Path | Description |
| ---- | ----------- |
| `backend/` | FastAPI application, SQLAlchemy models, Alembic migrations, alerting services, and Docker image. |
| `frontend/` | React + Vite dashboard (HTML/CSS/JS) consuming the FastAPI REST/WebSocket APIs. |
| `Simulation/` | Python data generator that replays realistic readings for registered sensor boxes. |

## Prerequisites

Install the following tooling before running the stack locally:

- **Node.js 18+** (required for the Vite/React frontend).
- **Python 3.11+** (or Anaconda/Miniconda) for the FastAPI backend and simulation harness.
- **PostgreSQL 13+** with a listening port on `5432`.
- **DBeaver** (optional) for exploring the database; configure it as shown in `dbsetting-1.png`.
- **Docker & Docker Compose** for containerized deployment using `docker-compose.yml`.

All required software can be found in the /Installation Packages/ folder.

## Configuration Files

| File | Purpose |
| ---- | ------- |
| `backend/environment.yml` | Conda specification used to recreate the backend development environment. |
| `backend/requirements.txt` | Python pip requirements for running the FastAPI service without Conda. |
| `backend/app/.env` *(create manually)* | Environment overrides for the backend (see variables below). |
| `frontend/.env` | Vite environment variables (defaults `VITE_API_BASE=http://localhost:8000`). |
| `Simulation/config.json` | Simulation driver configuration: backend URL(s), sensor box metadata, and house IDs. |

### Backend Environment Variables

Create a `.env` file inside `backend/` (or export variables in your shell) with the following keys:

```ini
# Database connectivity
DATABASE_URL=postgresql+asyncpg://sensoruser:secret123@localhost:5432/sensordb
ALEMBIC_DATABASE_URL=${DATABASE_URL}

# CORS / session settings
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
SESSION_SECRET=change-me
SESSION_COOKIE=sid
SESSION_SAMESITE=lax
SESSION_HTTPS_ONLY=false

# SMTP alerting
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=sensorbox2025@gmail.com
SMTP_PASSWORD=maranmedical01
SMTP_FROM=sensorbox2025@gmail.com
ADMIN_EMAILS=sensorbox2025@gmail.com
```

Adjust credentials, ports, and hostnames to match your PostgreSQL and SMTP setups. Any variable can also be provided through Docker Compose or process managers.


## Two Methods to Setup and Run the Software

1. With Docker (Recommended): The easiest method. Running docker compose up will build and launch all services (backend, frontend, database, and simulation) automatically. 
2. Manually (Optional): Running the backend (Python) and frontend (Node.js) servers separately in an IDE (like VSCode).

## Docker-Based Workflow

1. Download Docker first !!!!!
2. A `docker-compose.yml` file is provided for local orchestration of the backend, frontend, PostgreSQL, and simulator services.
3. Open Visual Studio Code, open "Sensor_Box" folder. If folder is cloned from GitHub, use:

```bash
cd Sensor_Box-main
```

4. Open a new terminal, and type in the following commands:

```bash
docker compose build --no-cache
docker compose up
```

The compose file mounts `Simulation/config.json` into both backend and simulator containers. Override environment variables in the compose file or by creating an `.env` alongside it.

5. Wait until Docker Containers are fully comprised
6. Open Docker Desktop
7. In "Containers" tab, find "sensor_box-main", and click "Start" under Actions
8. Open http://localhost:5173/

## Database Setup (Optional)

If you prefer this way, go to /backend/app/.env, uncomment line 6: "; SIMULATION_API_BASE=http://localhost:8001" by removing ";" at the beginning.

1. Start PostgreSQL and create the database user + schema:
   ```sql
   CREATE USER sensoruser WITH PASSWORD 'secret123';
   CREATE DATABASE sensordb OWNER sensoruser;
   ```
2. Grant the user access to the public schema if needed:
   ```sql
   GRANT ALL PRIVILEGES ON DATABASE sensordb TO sensoruser;
   ```
3. (Optional) Use DBeaver to connect to `localhost:5432` with the same credentials for inspection.
4. Run Alembic migrations once the backend environment is ready:
   ```bash
   cd backend
   alembic upgrade head
   ```

## Backend Setup & Execution (Optional)

```bash
cd backend
conda init "$(basename "$SHELL")"   # only once, if you use Conda
conda env create -f environment.yml    # first time only
conda activate sensor1                 # or `python -m venv .venv && source .venv/bin/activate`
conda install --yes --file requirements.txt  # or `pip install -r requirements.txt`

# Apply migrations (if not already run)
alembic upgrade head

# Launch the FastAPI server
python -m app.main
```

The API is available at `http://127.0.0.1:8000`, with interactive docs at `http://127.0.0.1:8000/docs` and a `/health` endpoint for readiness checks.

### Running with Uvicorn Directly

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Setup & Execution (Optional)

```bash
cd frontend
npm install
npm run dev  # serves the dashboard at http://localhost:5173
```

Set `VITE_API_BASE` in `frontend/.env` if the backend is accessible through a different hostname or port.

## Simulation Harness (Optional)

The simulation mimics data produced by multiple sensor boxes and pushes them to the backend ingestion API.

1. Ensure the backend is running and `sensor_readings`, `sensors`, `sensor_configs`, and `households` tables are empty.
2. In the dashboard, register a new sensor box with serial number `SNBOX001` and note the generated house ID.
3. Update every unregistered boxes flagged with `"registered": false` if desired.
4. Activate the backend environment, then run:
   ```bash
   cd Simulation
   conda activate sensor1
   python simulation.py
   ```
5. Monitor the FastAPI logs and dashboard charts for incoming measurements.

## Useful Endpoints & Tools

- FastAPI interactive docs: `http://127.0.0.1:8000/docs`
- Health check: `GET http://127.0.0.1:8000/health`
- SMTP alert testing: `pytest tests/test_alerting_admin.py` (inside `backend/`)

## Troubleshooting Tips

- Ensure the PostgreSQL DSN in `DATABASE_URL` matches your local credentials and that the `asyncpg` driver is installed.
- If the frontend cannot reach the backend, verify `CORS_ORIGINS` includes the dashboard origin and that `VITE_API_BASE` points to the FastAPI host.
- For SMTP issues, enable `SMTP_DEBUG=true` to print transaction logs and confirm firewall access to your SMTP relay.

## References

- FastAPI documentation: <https://fastapi.tiangolo.com/>
- LoRaWAN network server integrations (The Things Stack / ChirpStack) for forwarding decoded payloads.
- PostgreSQL documentation: <https://www.postgresql.org/docs/>
