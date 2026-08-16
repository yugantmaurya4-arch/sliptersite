FROM python:3.11-slim

# Install ffmpeg and cleanup apt cache to keep image small
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render sets $PORT automatically; default to 5000 for local docker runs
ENV PORT=5000
EXPOSE 5000

CMD gunicorn -w 1 -b 0.0.0.0:$PORT app:app --timeout 300
