FROM python:3.11-slim

# FFmpeg kept for potential future local processing needs.
# The USAEA pipeline uses Shotstack for all rendering (no local FFmpeg required).
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Create output and temp directories
RUN mkdir -p output temp

# Railway sets PORT automatically; default to 8080 for local runs
ENV PORT=8080

# Expose the webhook server port
EXPOSE 8080

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
