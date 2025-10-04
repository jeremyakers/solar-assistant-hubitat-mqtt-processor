# MQTT Interceptor/Processor Service

A Python-based MQTT service that intercepts high-frequency Solar Assistant messages, aggregates them over configurable time periods, and publishes both aggregated data for Hubitat and real-time modified load values for EV charging systems.

## Features

- **Message Aggregation**: Collects high-frequency MQTT messages and publishes min/max/average statistics at configurable intervals
- **Modified Load Calculation**: Calculates intelligent load values based on house battery and EV battery state of charge
- **Dual MQTT Broker Support**: Can connect to different brokers for source and destination
- **Docker Ready**: Easy deployment with Docker and Docker Compose
- **Synology NAS Compatible**: Designed for easy deployment on Synology Container Manager
- **Comprehensive Monitoring**: Built-in monitoring and health check capabilities
- **Flexible Configuration**: YAML-based configuration with sensible defaults

## Architecture

```
Solar Assistant → MQTT Interceptor → Hubitat (aggregated data)
                                  → EVSE (modified load)
```

The service:
1. Subscribes to Solar Assistant MQTT topics (power, voltage, battery SoC, etc.)
2. Accumulates messages in time-based buffers
3. Publishes aggregated statistics (min/max/avg) to Hubitat at regular intervals
4. Calculates and publishes modified load values to EVSE in real-time

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Access to your MQTT broker(s)
- Knowledge of your Solar Assistant MQTT topic structure

### Installation

1. **Clone or download this repository**
   ```bash
   git clone <repository-url>
   cd MQTT_Processor
   ```

2. **Run the setup script**
   ```bash
   ./scripts/setup.sh
   ```

3. **Configure the service**
   Edit `config/config.yaml` with your MQTT broker details and topic names:
   ```yaml
   mqtt:
     source_broker:
       host: "192.168.1.100"  # Your Solar Assistant MQTT broker
       port: 1883
       username: ""
       password: ""
   ```

4. **Start the service**
   ```bash
   docker-compose up -d
   ```

5. **Check the logs**
   ```bash
   docker-compose logs -f
   ```

## Configuration

The service is configured via `config/config.yaml`. Key sections:

### MQTT Brokers
```yaml
mqtt:
  source_broker:      # Solar Assistant broker
    host: "192.168.1.100"
    port: 1883
    username: ""
    password: ""
  
  destination_broker: # Hubitat/EVSE broker (can be same as source)
    host: "192.168.1.100"
    port: 1883
    username: ""
    password: ""
```

### Topics
```yaml
topics:
  source:
    power: "solar_assistant/inverter_1/total_power/state"
    load: "solar_assistant/inverter_1/load_power/state"
    battery_soc: "solar_assistant/battery_1/state_of_charge/state"
    ev_battery_soc: "hubitat/ev_battery_soc"
    # ... other topics
  
  destination:
    aggregated_prefix: "solar_assistant_agg"
    modified_load: "evse/modified_load"
```

### Aggregation Settings
```yaml
aggregation:
  interval_seconds: 30           # How often to publish aggregated data
  buffer_max_age_seconds: 300    # How long to keep messages in buffer
  publish_individual_topics: true # Publish individual topic stats
```

### Load Modification
```yaml
load_modification:
  enabled: true
  high_frequency_updates: true   # Publish modified load on every load message
  ev_priority_threshold: 50      # EV battery % below which EV gets priority
  house_priority_threshold: 50   # House battery % above which house gets priority
```

## Deployment Options

### Docker Compose (Recommended)

```bash
docker-compose up -d
```

### Synology NAS Container Manager

1. Copy the project directory to your NAS
2. Open Container Manager
3. Go to Project tab
4. Click "Create"
5. Select the folder containing `docker-compose.yml`
6. Configure volume mappings:
   - `./config` → `/app/config`
   - `./logs` → `/app/logs`
7. Start the project

### Standalone Docker

```bash
docker build -t mqtt-interceptor .
docker run -d \
  --name mqtt-interceptor \
  --network host \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/logs:/app/logs \
  mqtt-interceptor
```

## Monitoring

### Built-in Monitor Script

```bash
python monitor.py --config config/config.yaml --duration 60
```

This will show:
- Connection status
- Recent message activity
- Last aggregated data update
- Last modified load update

### Docker Logs

```bash
docker-compose logs -f mqtt-interceptor
```

### Health Checks

The container includes health checks that verify the Python process is running.

### Algorithm Analysis and Tuning

For analyzing algorithm performance and tuning charging behavior:

```bash
# Enable algorithm logging in config/config.yaml
algorithm_logging:
  enabled: true
  log_every_n_calculations: 10  # Log every 10th calculation
```

This creates daily CSV files with all algorithm inputs and outputs in a single row format, perfect for Excel analysis. See [ALGORITHM_LOGGING.md](ALGORITHM_LOGGING.md) for complete details.

## Output Topics

### Aggregated Data

The service publishes aggregated statistics to topics under the configured prefix:

- `solar_assistant_agg/power/min` - Minimum power value
- `solar_assistant_agg/power/max` - Maximum power value  
- `solar_assistant_agg/power/avg` - Average power value
- `solar_assistant_agg/power/count` - Number of samples
- `solar_assistant_agg/combined` - JSON with all aggregated data

### Modified Load

Real-time modified load values are published to the configured EVSE topic:
- `evse/modified_load` - Modified load value for EV charging

## Modified Load Algorithm

The service implements the same load modification logic as your original Groovy driver:

1. **Battery Priority Calculation**:
   ```
   battery = house_battery_soc + (80 - ev_battery_soc)
   ```

2. **Load Modification**:
   ```
   if battery > house_priority_threshold:
       charge_mod = (battery - house_priority_threshold) * charge_modifier_multiplier
       load_mod = load_modifier_base * charge_mod / 100.0
   else:
       load_mod = 0.0
   
   modified_load = load - load_mod + load_modifier_base
   ```

This prioritizes:
- **EV charging** when house battery is high and EV battery is low
- **House battery charging** when EV battery is high and house battery is low

## Troubleshooting

### Service Won't Start

1. Check Docker logs: `docker-compose logs mqtt-interceptor`
2. Verify config file syntax: `python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"`
3. Test MQTT broker connectivity: `telnet <broker-ip> 1883`

### No Messages Received

1. Verify topic names in config match your Solar Assistant setup
2. Check MQTT broker authentication
3. Use an MQTT client to verify messages are being published by Solar Assistant

### Modified Load Not Working

1. Ensure `ev_battery_soc` topic is being published by your Hubitat EV driver
2. Check that `load_modification.enabled` is `true` in config
3. Verify EVSE is subscribed to the correct modified load topic

### High CPU/Memory Usage

1. Increase `aggregation.interval_seconds` to reduce processing frequency
2. Decrease `aggregation.buffer_max_age_seconds` to reduce memory usage
3. Set `aggregation.publish_individual_topics` to `false` to reduce MQTT traffic

## Integration with Hubitat

### Update Your Hubitat Driver

Modify your existing Solar Assistant driver to subscribe to the aggregated topics instead of the high-frequency Solar Assistant topics:

```groovy
// Instead of: solar_assistant/inverter_1/total_power/state
// Subscribe to: solar_assistant_agg/power/avg

// Or use the combined JSON topic: solar_assistant_agg/combined
```

### EV Battery SoC Publishing

Ensure your EV monitoring driver publishes the battery SoC to the configured topic:

```groovy
// In your EV driver
interfaces.mqtt.publish("hubitat/ev_battery_soc", ev_battery_soc.toString())
```

## Advanced Configuration

### Multiple Solar Assistant Devices

To handle multiple Solar Assistant devices, you can:

1. Run multiple interceptor instances with different configs
2. Modify the topic configuration to use wildcards (requires code changes)
3. Use MQTT broker topic routing

### Custom Aggregation Logic

The `MessageBuffer` class can be extended to implement custom aggregation algorithms beyond min/max/avg.

### Integration with Home Assistant

The service can easily integrate with Home Assistant by:

1. Publishing to Home Assistant MQTT discovery topics
2. Using Home Assistant's MQTT sensor platform
3. Creating Home Assistant automations based on aggregated data

## License

This project is licensed under the Apache License 2.0 - see the original Solar Assistant driver license for details.

## Support

For issues and questions:

1. Check the troubleshooting section above
2. Review the Docker logs for error messages
3. Test MQTT connectivity independently
4. Verify configuration file syntax

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test your changes thoroughly
4. Submit a pull request with a clear description
