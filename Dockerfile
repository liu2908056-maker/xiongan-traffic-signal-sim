FROM danielda1/ugat:latest
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY . .
# Compile the pinned official CityFlow source included in this project. This
# prevents silently using a different preinstalled Python extension.
RUN python -m pip install --no-cache-dir ./third_party/CityFlow
RUN python src/validate_scenario.py
ENTRYPOINT ["python", "src/run_cityflow.py"]
