# Synology NAS Deployment Guide

This guide walks you through deploying the MQTT Interceptor service on your Synology NAS using Container Manager.

## Prerequisites

- Synology NAS with DSM 7.0 or later
- Container Manager package installed
- SSH access to your NAS (optional, for advanced setup)
- Basic knowledge of Docker containers

## Method 1: Container Manager GUI (Recommended)

### Step 1: Prepare Files

1. **Copy project files to your NAS**
   - Create a folder on your NAS: `/docker/mqtt-interceptor/`
   - Upload all project files to this folder
   - Ensure the folder structure looks like:
     ```
     /docker/mqtt-interceptor/
     ├── mqtt_interceptor.py
     ├── monitor.py
     ├── requirements.txt
     ├── Dockerfile
     ├── docker-compose.yml
     ├── config/
     │   └── config.yaml
     ├── logs/
     └── scripts/
         └── setup.sh
     ```

### Step 2: Configure the Service

1. **Edit the configuration file**
   - Open `config/config.yaml` in Text Editor
   - Update MQTT broker settings:
     ```yaml
     mqtt:
       source_broker:
         host: "192.168.1.100"  # Your Solar Assistant IP
         port: 1883
         username: ""  # If required
         password: ""  # If required
     ```
   - Update topic names to match your Solar Assistant setup
   - Save the file

### Step 3: Deploy with Container Manager

1. **Open Container Manager**
   - Go to Package Center → Container Manager
   - Open Container Manager

2. **Create Project**
   - Click on "Project" tab
   - Click "Create"
   - Choose "Create docker-compose.yml"

3. **Configure Project**
   - Project name: `mqtt-interceptor`
   - Path: Select `/docker/mqtt-interceptor/`
   - Source: Select "Use existing docker-compose.yml"

4. **Review Configuration**
   - Container Manager will read your `docker-compose.yml`
   - Verify the volume mappings:
     - `./config` → `/app/config`
     - `./logs` → `/app/logs`

5. **Start the Project**
   - Click "Next" → "Done"
   - The container will build and start automatically

### Step 4: Verify Deployment

1. **Check Container Status**
   - Go to "Container" tab
   - Look for `mqtt-interceptor` container
   - Status should be "Running"

2. **View Logs**
   - Select the container
   - Click "Details" → "Log"
   - Look for successful MQTT connections

3. **Monitor Output**
   - Check your MQTT broker for new topics under `solar_assistant_agg/`
   - Verify modified load messages on your EVSE topic

## Method 2: SSH Command Line

If you prefer command line deployment:

### Step 1: SSH to Your NAS

```bash
ssh admin@your-nas-ip
```

### Step 2: Navigate to Docker Directory

```bash
cd /volume1/docker/mqtt-interceptor/
```

### Step 3: Build and Start

```bash
# Make setup script executable
chmod +x scripts/setup.sh

# Run setup
./scripts/setup.sh

# Start the service
docker-compose up -d
```

### Step 4: Check Status

```bash
# View logs
docker-compose logs -f

# Check container status
docker-compose ps
```

## Configuration for Synology

### Network Settings

The default configuration uses `network_mode: host` which works well on Synology. If you need to use bridge networking:

1. **Edit docker-compose.yml**:
   ```yaml
   services:
     mqtt-interceptor:
       # Remove: network_mode: host
       # Add port mappings if needed:
       ports:
         - "8080:8080"  # Only if you add a web interface
   ```

### Volume Mappings

Ensure your volume paths are correct for Synology:

```yaml
volumes:
  - /volume1/docker/mqtt-interceptor/config:/app/config:ro
  - /volume1/docker/mqtt-interceptor/logs:/app/logs
```

### Resource Limits

The default resource limits are conservative. Adjust if needed:

```yaml
deploy:
  resources:
    limits:
      memory: 256M  # Increase if needed
      cpus: '1.0'   # Increase if needed
```

## Monitoring on Synology

### Container Manager Monitoring

1. **Container Health**
   - Container Manager → Container tab
   - Check container status and resource usage

2. **Log Viewing**
   - Select container → Details → Log
   - Real-time log viewing

3. **Resource Monitoring**
   - Details → Terminal (if needed for debugging)

### External Monitoring

1. **Install Python on NAS** (optional):
   ```bash
   # Enable SSH and install Python packages
   sudo python3 -m pip install paho-mqtt PyYAML
   ```

2. **Run Monitor Script**:
   ```bash
   cd /volume1/docker/mqtt-interceptor/
   python3 monitor.py --config config/config.yaml
   ```

## Troubleshooting on Synology

### Container Won't Start

1. **Check Docker Compose Syntax**:
   ```bash
   cd /volume1/docker/mqtt-interceptor/
   docker-compose config
   ```

2. **Check File Permissions**:
   ```bash
   ls -la config/
   # Ensure config.yaml is readable
   ```

3. **View Build Logs**:
   ```bash
   docker-compose build --no-cache
   ```

### Network Issues

1. **Test MQTT Connectivity**:
   ```bash
   # From NAS command line
   telnet your-mqtt-broker-ip 1883
   ```

2. **Check Firewall Settings**:
   - Control Panel → Security → Firewall
   - Ensure MQTT ports (1883, 8883) are allowed

3. **Network Mode Issues**:
   - If host networking doesn't work, switch to bridge mode
   - Add explicit port mappings if needed

### Storage Issues

1. **Check Disk Space**:
   ```bash
   df -h /volume1/
   ```

2. **Log Rotation**:
   - Logs are automatically rotated by Docker
   - Adjust in docker-compose.yml if needed:
     ```yaml
     logging:
       options:
         max-size: "5m"  # Smaller log files
         max-file: "2"   # Fewer log files
     ```

## Automatic Startup

The container is configured with `restart: unless-stopped`, so it will:
- Start automatically when the NAS boots
- Restart if it crashes
- Stay stopped if manually stopped

## Updating the Service

### Method 1: Container Manager

1. Stop the project
2. Update files on NAS
3. Rebuild: Project → Select → Action → Build
4. Start the project

### Method 2: Command Line

```bash
cd /volume1/docker/mqtt-interceptor/
docker-compose down
# Update files as needed
docker-compose build --no-cache
docker-compose up -d
```

## Backup and Restore

### Backup Configuration

```bash
# Backup entire project directory
tar -czf mqtt-interceptor-backup.tar.gz /volume1/docker/mqtt-interceptor/
```

### Restore Configuration

```bash
# Extract backup
tar -xzf mqtt-interceptor-backup.tar.gz -C /volume1/docker/
```

## Performance Optimization

### For Low-Power NAS Models

1. **Reduce Processing Frequency**:
   ```yaml
   aggregation:
     interval_seconds: 60  # Increase from 30
   ```

2. **Limit Resource Usage**:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 64M
         cpus: '0.25'
   ```

3. **Disable Individual Topic Publishing**:
   ```yaml
   aggregation:
     publish_individual_topics: false
   ```

### For High-Performance NAS Models

1. **Increase Buffer Size**:
   ```yaml
   aggregation:
     buffer_max_age_seconds: 600  # 10 minutes
   ```

2. **Enable Debug Logging** (temporarily):
   ```yaml
   logging:
     level: "DEBUG"
   ```

## Integration with Synology Services

### DSM Notifications

You can integrate with DSM notifications by adding a webhook endpoint to the service (requires code modification).

### Synology MQTT Broker

If running Mosquitto on your Synology:
1. Install Mosquitto broker package
2. Configure both source and destination brokers to use localhost
3. Use different topics to avoid loops

This completes the Synology deployment guide. The service should now be running reliably on your NAS!
