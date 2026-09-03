# CityFlow commit 81ee0f uses pybind11 2.3.0, which is compatible with CPython 3.10
# but not CPython 3.11+.
FROM python:3.10-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake git && rm -rf /var/lib/apt/lists/*
COPY third_party/CityFlow /opt/CityFlow
RUN python -m pip install numpy && python -m pip install /opt/CityFlow
COPY data ./data
COPY src ./src
COPY docs ./docs
RUN python src/validate_scenario.py && python src/check_cityflow.py
ENTRYPOINT ["python", "src/run_cityflow.py"]
