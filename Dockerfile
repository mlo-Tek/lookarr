FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Config-Verzeichnis für Unraid-Volume-Mount
VOLUME ["/config"]

EXPOSE 32500

CMD ["python", "main.py"]
