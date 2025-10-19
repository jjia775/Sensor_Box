# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal \
    PROJ_LIB=/usr/lib/x86_64-linux-gnu/proj

WORKDIR /app

# Install system dependencies required by scientific/geospatial Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gdal-bin \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
        proj-bin \
        proj-data \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better Docker caching
COPY requirements-linux.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the simulation source code
COPY . .

# Default command runs the simulation entry-point
CMD ["python", "simulation.py"]
