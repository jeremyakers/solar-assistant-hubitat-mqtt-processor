FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY mqtt_interceptor.py .

# Create a non-root user
RUN useradd -m -u 1000 mqtt_user && chown -R mqtt_user:mqtt_user /app
USER mqtt_user

# Create config directory
RUN mkdir -p /app/config

# Expose any ports if needed (none required for MQTT client)
# EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Run the application
CMD ["python", "mqtt_interceptor.py", "--config", "/app/config/config.yaml"]
