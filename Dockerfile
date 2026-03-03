FROM python:3.11-slim

# FFmpeg is needed only for the generic pipeline.
# The USAEA pipeline (Revid.ai) does not require it, but we keep it
# so the generic pipeline remains functional.
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

CMD ["python3", "main.py"]
