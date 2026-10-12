# Una misma imagen pequeña para los dos nodos y el receptor.
FROM python:3.12.15-alpine3.24
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Reutiliza el paquete oficial previamente descargado y verificado.
COPY dependencias/paho_mqtt-2.1.0-py3-none-any.whl /tmp/dependencias/
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --no-index --find-links=/tmp/dependencias -r requirements.txt

COPY src/ ./src/
USER 10001:10001
CMD ["python", "src/sensor_simulado.py", "--mqtt", "--broker", "emqx"]
