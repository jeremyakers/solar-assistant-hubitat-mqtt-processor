#!/usr/bin/env python3
"""
MQTT Interceptor/Processor Service

This service subscribes to high-frequency Solar Assistant MQTT messages,
aggregates them over configurable time periods, and publishes:
1. Aggregated data (min/max/avg) to topics for Hubitat consumption
2. Real-time modified load values to EVSE based on battery priorities

Author: Jeremy Akers
"""

import csv
import json
import logging
import os
import signal
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

import paho.mqtt.client as mqtt

# Version information
VERSION = '1.2.1'

@dataclass
class MessageBuffer:
    """Buffer for accumulating messages over time"""
    values: deque = field(default_factory=deque)
    timestamps: deque = field(default_factory=deque)
    max_age_seconds: float = 300  # 5 minutes default
    
    def add_value(self, value: float, timestamp: Optional[datetime] = None):
        """Add a value to the buffer with timestamp"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.values.append(value)
        self.timestamps.append(timestamp)
        
        # Clean old values
        self._clean_old_values()
    
    def _clean_old_values(self):
        """Remove values older than max_age_seconds"""
        cutoff_time = datetime.now() - timedelta(seconds=self.max_age_seconds)
        
        while self.timestamps and self.timestamps[0] < cutoff_time:
            self.timestamps.popleft()
            self.values.popleft()
    
    def get_stats(self) -> Dict[str, float]:
        """Get min, max, average, and count of current values"""
        self._clean_old_values()
        
        if not self.values:
            return {"min": 0.0, "max": 0.0, "avg": 0.0, "count": 0}
        
        values_list = list(self.values)
        return {
            "min": min(values_list),
            "max": max(values_list),
            "avg": sum(values_list) / len(values_list),
            "count": len(values_list)
        }
    
    def get_latest(self) -> Optional[float]:
        """Get the most recent value"""
        self._clean_old_values()
        return self.values[-1] if self.values else None


class AlgorithmLogger:
    """Simple CSV logger for algorithm inputs and outputs"""
    
    def __init__(self, config: Dict):
        self.enabled = config.get("algorithm_logging", {}).get("enabled", False)
        if not self.enabled:
            return
            
        self.log_every_n = config.get("algorithm_logging", {}).get("log_every_n_calculations", 10)
        self.max_age_days = config.get("algorithm_logging", {}).get("max_age_days", 30)
        self.log_dir = Path(config.get("algorithm_logging", {}).get("log_directory", "data/algorithm_logs"))
        
        # Create log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Counter for logging frequency
        self.calculation_count = 0
        
        # Current log file
        self.current_date = None
        self.csv_file = None
        self.csv_writer = None
        
        self.logger = logging.getLogger(f"{__name__}.AlgorithmLogger")
        
    def log_algorithm_calculation(self, timestamp: datetime, house_battery_soc: float, 
                                 ev_battery_soc: float, original_load: float, 
                                 modified_load: float, battery_priority_score: float,
                                 charging_priority: str):
        """Log algorithm calculation if enabled and due for logging"""
        if not self.enabled:
            return
            
        self.calculation_count += 1
        
        # Only log every N calculations
        if self.calculation_count % self.log_every_n != 0:
            return
            
        try:
            # Check if we need a new file (new day)
            current_date = timestamp.date()
            if current_date != self.current_date:
                self._rotate_log_file(current_date)
            
            # Write the log entry
            load_difference = modified_load - original_load
            
            self.csv_writer.writerow([
                timestamp.isoformat(),
                house_battery_soc,
                ev_battery_soc,
                original_load,
                modified_load,
                load_difference,
                battery_priority_score,
                charging_priority
            ])
            
            # Flush to ensure data is written
            self.csv_file.flush()
            
            self.logger.debug(f"Logged algorithm calculation #{self.calculation_count}")
            
        except Exception as e:
            self.logger.error(f"Error logging algorithm calculation: {e}")
    
    def _rotate_log_file(self, date):
        """Rotate to a new log file for the given date"""
        # Close current file if open
        if self.csv_file:
            self.csv_file.close()
        
        # Create new file for the date
        filename = f"algorithm_log_{date.strftime('%Y-%m-%d')}.csv"
        filepath = self.log_dir / filename
        
        # Open new file
        file_exists = filepath.exists()
        self.csv_file = open(filepath, 'a', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        
        # Write header if new file
        if not file_exists:
            self.csv_writer.writerow([
                'timestamp',
                'house_battery_soc',
                'ev_battery_soc', 
                'original_load',
                'modified_load',
                'load_difference',
                'battery_priority_score',
                'charging_priority'
            ])
        
        self.current_date = date
        self.logger.info(f"Rotated to new log file: {filepath}")
        
        # Clean up old files
        self._cleanup_old_files()
    
    def _cleanup_old_files(self):
        """Remove log files older than max_age_days"""
        try:
            cutoff_date = datetime.now().date() - timedelta(days=self.max_age_days)
            
            for file_path in self.log_dir.glob("algorithm_log_*.csv"):
                try:
                    # Extract date from filename
                    date_str = file_path.stem.replace("algorithm_log_", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    
                    if file_date < cutoff_date:
                        file_path.unlink()
                        self.logger.info(f"Deleted old log file: {file_path}")
                        
                except (ValueError, OSError) as e:
                    self.logger.warning(f"Could not process/delete file {file_path}: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error during log cleanup: {e}")
    
    def close(self):
        """Close the current log file"""
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None


class MQTTInterceptor:
    """Main MQTT Interceptor service"""
    
    def __init__(self, config_file: str = "config.yaml"):
        self.config = self._load_config(config_file)
        self.setup_logging()
        
        # Message buffers for different topics
        self.buffers: Dict[str, MessageBuffer] = {}
        
        # Algorithm logger
        self.algorithm_logger = AlgorithmLogger(self.config)
        
        # Current state values
        self.current_values = {}
        self.house_battery_soc = 0.0
        self.ev_battery_soc = 0.0
        self.last_load_value = 0.0
        
        # MQTT clients
        self.source_client = None
        self.dest_client = None
        
        # Threading
        self.running = False
        self.aggregation_thread = None
        self.lock = threading.Lock()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logging.error(f"Config file {config_file} not found. Creating default config.")
            self._create_default_config(config_file)
            sys.exit(1)
    
    def _create_default_config(self, config_file: str):
        """Create a default configuration file"""
        default_config = {
            "mqtt": {
                "source_broker": {
                    "host": "192.168.1.100",
                    "port": 1883,
                    "username": "",
                    "password": "",
                    "keepalive": 60
                },
                "destination_broker": {
                    "host": "192.168.1.100", 
                    "port": 1883,
                    "username": "",
                    "password": "",
                    "keepalive": 60
                }
            },
            "topics": {
                "source": {
                    "power": "solar_assistant/inverter_1/total_power/state",
                    "load": "solar_assistant/inverter_1/load_power/state", 
                    "voltage": "solar_assistant/battery_1/voltage/state",
                    "min_cell_voltage": "solar_assistant/battery_1/min_cell_voltage/state",
                    "max_cell_voltage": "solar_assistant/battery_1/max_cell_voltage/state",
                    "battery_soc": "solar_assistant/battery_1/state_of_charge/state",
                    "temperature": "solar_assistant/battery_1/temperature/state",
                    "energy": "solar_assistant/inverter_1/daily_energy/state",
                    "ev_battery_soc": "hubitat/ev_battery_soc"
                },
                "destination": {
                    "aggregated_suffix": "_agg",
                    "modified_load": "evse/modified_load"
                }
            },
            "aggregation": {
                "interval_seconds": 30,
                "buffer_max_age_seconds": 300,
                "publish_individual_topics": True
            },
            "load_modification": {
                "enabled": True,
                "high_frequency_updates": True,
                "ev_priority_threshold": 50,
                "house_priority_threshold": 50,
                "charge_modifier_multiplier": 2.0,
                "load_modifier_base": 10000.0,
                "min_charge_power_offset": 11000.0
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        }
        
        with open(config_file, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, indent=2)
        
        print(f"Created default config file: {config_file}")
        print("Please edit the configuration file with your MQTT broker details and topic names.")
    
    def setup_logging(self):
        """Setup logging configuration with file output"""
        log_config = self.config.get("logging", {})
        level = getattr(logging, log_config.get("level", "INFO").upper())
        format_str = log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        
        # Create logs directory
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Setup logging to both file and console
        logging.basicConfig(
            level=level,
            format=format_str,
            handlers=[
                logging.FileHandler(log_dir / "mqtt_interceptor.log"),
                logging.StreamHandler()  # This goes to Docker logs
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Log version information on startup
        self.logger.info(f"MQTT Interceptor v{VERSION} starting up")
        self.logger.info(f"Python version: {sys.version}")
        self.logger.info(f"Log level: {logging.getLevelName(level)}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def setup_mqtt_clients(self):
        """Setup MQTT client connections"""
        # Source client (subscribes to Solar Assistant)
        self.source_client = mqtt.Client(client_id="mqtt_interceptor_source")
        source_config = self.config["mqtt"]["source_broker"]
        
        if source_config.get("username"):
            self.source_client.username_pw_set(
                source_config["username"], 
                source_config.get("password", "")
            )
        
        self.source_client.on_connect = self._on_source_connect
        self.source_client.on_message = self._on_source_message
        self.source_client.on_disconnect = self._on_source_disconnect
        
        # Destination client (publishes to Hubitat/EVSE)
        self.dest_client = mqtt.Client(client_id="mqtt_interceptor_dest")
        dest_config = self.config["mqtt"]["destination_broker"]
        
        if dest_config.get("username"):
            self.dest_client.username_pw_set(
                dest_config["username"],
                dest_config.get("password", "")
            )
        
        self.dest_client.on_connect = self._on_dest_connect
        self.dest_client.on_disconnect = self._on_dest_disconnect
    
    def _on_source_connect(self, client, userdata, flags, rc):
        """Callback for source MQTT connection"""
        if rc == 0:
            self.logger.info("Connected to source MQTT broker")
            self._subscribe_to_topics()
        else:
            self.logger.error(f"Failed to connect to source broker: {rc}")
    
    def _on_dest_connect(self, client, userdata, flags, rc):
        """Callback for destination MQTT connection"""
        if rc == 0:
            self.logger.info("Connected to destination MQTT broker")
        else:
            self.logger.error(f"Failed to connect to destination broker: {rc}")
    
    def _on_source_disconnect(self, client, userdata, rc):
        """Callback for source MQTT disconnection"""
        self.logger.warning(f"Disconnected from source broker: {rc}")
    
    def _on_dest_disconnect(self, client, userdata, rc):
        """Callback for destination MQTT disconnection"""
        self.logger.warning(f"Disconnected from destination broker: {rc}")
    
    def _subscribe_to_topics(self):
        """Subscribe to all configured source topics"""
        source_topics = self.config["topics"]["source"]
        
        for topic_name, topic_path in source_topics.items():
            if topic_path:  # Only subscribe if topic is configured
                self.source_client.subscribe(topic_path)
                self.logger.info(f"Subscribed to {topic_name}: {topic_path}")
                
                # Initialize buffer for this topic
                buffer_age = self.config["aggregation"]["buffer_max_age_seconds"]
                self.buffers[topic_name] = MessageBuffer(max_age_seconds=buffer_age)
    
    def _on_source_message(self, client, userdata, msg):
        """Handle incoming messages from source broker"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            # Find which configured topic this message belongs to
            topic_name = self._identify_topic(topic)
            if not topic_name:
                return
            
            # Parse payload
            try:
                # Try JSON first
                data = json.loads(payload)
                if isinstance(data, dict) and 'value' in data:
                    value = float(data['value'])
                else:
                    value = float(data)
            except (json.JSONDecodeError, ValueError):
                # Try direct float conversion
                try:
                    value = float(payload)
                except ValueError:
                    self.logger.warning(f"Could not parse payload for {topic}: {payload}")
                    return
            
            # Store the value
            with self.lock:
                self.current_values[topic_name] = value
                
                # Add to buffer for aggregation (except for EV battery SoC which comes from Hubitat)
                if topic_name != "ev_battery_soc":
                    self.buffers[topic_name].add_value(value)
                else:
                    self.ev_battery_soc = value
                
                # Update house battery SoC
                if topic_name == "battery_soc":
                    self.house_battery_soc = value
                
                # Handle load topic for real-time modified load calculation
                if topic_name == "load" and self.config["load_modification"]["enabled"]:
                    self.last_load_value = value
                    if self.config["load_modification"]["high_frequency_updates"]:
                        self._calculate_and_publish_modified_load(value)
            
            self.logger.debug(f"Received {topic_name}: {value}")
            
        except Exception as e:
            self.logger.error(f"Error processing message from {topic}: {e}")
    
    def _identify_topic(self, received_topic: str) -> Optional[str]:
        """Identify which configured topic a received message belongs to"""
        source_topics = self.config["topics"]["source"]
        
        for topic_name, configured_topic in source_topics.items():
            if configured_topic and received_topic == configured_topic:
                return topic_name
        
        return None
    
    def _calculate_and_publish_modified_load(self, load_value: float):
        """Calculate and publish modified load value for EVSE (matches original Groovy logic exactly)"""
        try:
            config = self.config["load_modification"]
            timestamp = datetime.now()
            
            # Get current battery levels (matching Groovy variable names)
            mybattery = self.house_battery_soc
            ev_battery = self.ev_battery_soc
            
            # Calculate combined battery score (exact Groovy logic)
            battery = mybattery + (80 - ev_battery)
            
            # Apply load modification (exact Groovy logic)
            if battery > 50:
                chargemod = (battery - 50) * 2
                loadmod = 10000.0 * chargemod / 100.0
                charging_priority = "ACTIVE_MODIFICATION"
            else:
                loadmod = 0.0
                charging_priority = "NO_MODIFICATION"
            
            # Calculate modified load (exact Groovy formula)
            modified_load = load_value - loadmod + 10000
            
            # Log algorithm calculation (only every N times based on config)
            self.algorithm_logger.log_algorithm_calculation(
                timestamp=timestamp,
                house_battery_soc=mybattery,
                ev_battery_soc=ev_battery,
                original_load=load_value,
                modified_load=modified_load,
                battery_priority_score=battery,
                charging_priority=charging_priority
            )
            
            # Publish modified load
            dest_topic = self.config["topics"]["destination"]["modified_load"]
            if dest_topic:
                self.dest_client.publish(dest_topic, str(modified_load))
                
                self.logger.debug(
                    f"Modified load: house_battery={mybattery}%, ev_battery={ev_battery}%, "
                    f"battery_score={battery}, load={load_value}W→{modified_load}W, "
                    f"chargemod={chargemod}, loadmod={loadmod}, priority={charging_priority}"
                )
        
        except Exception as e:
            self.logger.error(f"Error calculating modified load: {e}")
    
    def start_aggregation_thread(self):
        """Start the aggregation thread"""
        self.aggregation_thread = threading.Thread(target=self._aggregation_loop)
        self.aggregation_thread.daemon = True
        self.aggregation_thread.start()
    
    def _aggregation_loop(self):
        """Main aggregation loop that runs in a separate thread"""
        interval = self.config["aggregation"]["interval_seconds"]
        
        while self.running:
            try:
                time.sleep(interval)
                if self.running:
                    self._publish_aggregated_data()
            except Exception as e:
                self.logger.error(f"Error in aggregation loop: {e}")
    
    def _publish_aggregated_data(self):
        """Publish aggregated data to destination topics with suffix approach"""
        try:
            with self.lock:
                dest_suffix = self.config["topics"]["destination"]["aggregated_suffix"]
                publish_individual = self.config["aggregation"]["publish_individual_topics"]
                source_topics = self.config["topics"]["source"]
                
                aggregated_data = {}
                
                for topic_name, buffer in self.buffers.items():
                    if topic_name == "ev_battery_soc":  # Skip EV battery - it comes from Hubitat
                        continue
                        
                    stats = buffer.get_stats()
                    if stats["count"] > 0:
                        aggregated_data[topic_name] = stats
                        
                        # Get original topic path and create aggregated version
                        original_topic = source_topics.get(topic_name, "")
                        if original_topic:
                            # Extract base topic (first part before first slash)
                            parts = original_topic.split("/", 1)
                            if len(parts) >= 2:
                                base_topic = parts[0]
                                remaining_path = parts[1]
                                aggregated_topic_base = f"{base_topic}{dest_suffix}/{remaining_path}"
                            else:
                                # No slash in topic, just add suffix
                                aggregated_topic_base = f"{original_topic}{dest_suffix}"
                            
                            # Publish individual topic stats if enabled
                            if publish_individual:
                                self.dest_client.publish(f"{aggregated_topic_base}/min", stats["min"])
                                self.dest_client.publish(f"{aggregated_topic_base}/max", stats["max"])
                                self.dest_client.publish(f"{aggregated_topic_base}/avg", stats["avg"])
                                self.dest_client.publish(f"{aggregated_topic_base}/count", stats["count"])
                
                # Publish combined aggregated data as JSON (using first source topic base + suffix)
                if aggregated_data and source_topics:
                    # Use the first source topic to determine combined topic location
                    first_topic = next(iter(source_topics.values()))
                    base_topic = first_topic.split("/", 1)[0] if "/" in first_topic else first_topic
                    combined_topic = f"{base_topic}{dest_suffix}/combined"
                    combined_payload = json.dumps(aggregated_data, indent=2)
                    self.dest_client.publish(combined_topic, combined_payload)
                    
                    self.logger.info(f"Published aggregated data for {len(aggregated_data)} topics")
        
        except Exception as e:
            self.logger.error(f"Error publishing aggregated data: {e}")
    
    def start(self):
        """Start the MQTT interceptor service"""
        self.logger.info("Starting MQTT Interceptor service...")
        
        self.running = True
        
        # Setup MQTT clients
        self.setup_mqtt_clients()
        
        # Connect to brokers
        source_config = self.config["mqtt"]["source_broker"]
        dest_config = self.config["mqtt"]["destination_broker"]
        
        try:
            self.source_client.connect(
                source_config["host"],
                source_config["port"],
                source_config["keepalive"]
            )
            
            self.dest_client.connect(
                dest_config["host"],
                dest_config["port"],
                dest_config["keepalive"]
            )
            
            # Start MQTT loops
            self.source_client.loop_start()
            self.dest_client.loop_start()
            
            # Start aggregation thread
            self.start_aggregation_thread()
            
            self.logger.info("MQTT Interceptor service started successfully")
            
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error starting service: {e}")
            self.stop()
    
    def stop(self):
        """Stop the MQTT interceptor service"""
        self.logger.info("Stopping MQTT Interceptor service...")
        
        self.running = False
        
        if self.source_client:
            self.source_client.loop_stop()
            self.source_client.disconnect()
        
        if self.dest_client:
            self.dest_client.loop_stop()
            self.dest_client.disconnect()
        
        if self.aggregation_thread and self.aggregation_thread.is_alive():
            self.aggregation_thread.join(timeout=5)
        
        # Close algorithm logger
        self.algorithm_logger.close()
        
        self.logger.info("MQTT Interceptor service stopped")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MQTT Interceptor/Processor Service")
    parser.add_argument(
        "--config", 
        default="config.yaml",
        help="Configuration file path (default: config.yaml)"
    )
    
    args = parser.parse_args()
    
    interceptor = MQTTInterceptor(args.config)
    interceptor.start()


if __name__ == "__main__":
    main()
