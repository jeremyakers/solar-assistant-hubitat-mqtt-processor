#!/bin/bash

# MQTT Interceptor Setup Script
# This script helps set up the MQTT Interceptor service on your system

set -e

echo "MQTT Interceptor Setup Script"
echo "============================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p config
mkdir -p logs
mkdir -p data

# Set permissions
chmod 755 config
chmod 755 logs
chmod 755 data

# Copy example config if config.yaml doesn't exist
if [ ! -f "config/config.yaml" ]; then
    if [ -f "config/config.example.yaml" ]; then
        cp config/config.example.yaml config/config.yaml
        echo "Created config/config.yaml from example template"
    else
        echo "Warning: config/config.example.yaml not found."
        echo "The application will create a default config file on first run."
    fi
    echo "You'll need to edit config/config.yaml with your MQTT broker details."
fi

# Build the Docker image
echo "Building Docker image..."
docker-compose build

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config/config.yaml with your MQTT broker details and topic names"
echo "2. Run 'docker-compose up -d' to start the service"
echo "3. Check logs with 'docker-compose logs -f'"
echo "4. Monitor with 'python monitor.py' (requires paho-mqtt and PyYAML)"
echo ""
echo "For Synology NAS:"
echo "1. Copy this entire directory to your NAS"
echo "2. Open Container Manager"
echo "3. Import the docker-compose.yml file"
echo "4. Configure the volumes to point to your config directory"
echo "5. Start the container"
