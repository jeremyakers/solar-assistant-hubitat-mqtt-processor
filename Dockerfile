FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY mqtt_interceptor.py .

# Create directories
RUN mkdir -p /app/config /app/data /app/logs

# Run the application
CMD ["python", "mqtt_interceptor.py", "--config", "/app/config/config.yaml"]