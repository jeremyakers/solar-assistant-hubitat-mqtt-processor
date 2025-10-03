#!/usr/bin/env python3
"""
MQTT Interceptor Monitor

A simple monitoring script to check the health and status of the MQTT interceptor service.
Can be used for debugging or as a health check endpoint.
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, Any
import yaml

import paho.mqtt.client as mqtt


class MQTTMonitor:
    """Monitor for MQTT Interceptor service"""
    
    def __init__(self, config_file: str = "config/config.yaml"):
        self.config = self._load_config(config_file)
        self.setup_logging()
        
        self.client = None
        self.received_messages = {}
        self.last_aggregated_update = None
        self.last_modified_load_update = None
        
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from YAML file"""
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_mqtt_client(self):
        """Setup MQTT client for monitoring"""
        self.client = mqtt.Client(client_id="mqtt_interceptor_monitor")
        
        # Use destination broker config to monitor output
        dest_config = self.config["mqtt"]["destination_broker"]
        
        if dest_config.get("username"):
            self.client.username_pw_set(
                dest_config["username"],
                dest_config.get("password", "")
            )
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection"""
        if rc == 0:
            self.logger.info("Connected to MQTT broker for monitoring")
            self._subscribe_to_output_topics()
        else:
            self.logger.error(f"Failed to connect to broker: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        self.logger.warning(f"Disconnected from broker: {rc}")
    
    def _subscribe_to_output_topics(self):
        """Subscribe to interceptor output topics"""
        dest_config = self.config["topics"]["destination"]
        
        # Subscribe to aggregated data
        agg_prefix = dest_config["aggregated_prefix"]
        self.client.subscribe(f"{agg_prefix}/+/+")  # Individual topic stats
        self.client.subscribe(f"{agg_prefix}/combined")  # Combined JSON
        
        # Subscribe to modified load
        if dest_config.get("modified_load"):
            self.client.subscribe(dest_config["modified_load"])
        
        self.logger.info("Subscribed to interceptor output topics")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming monitoring messages"""
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        timestamp = datetime.now()
        
        self.received_messages[topic] = {
            "payload": payload,
            "timestamp": timestamp
        }
        
        # Track specific message types
        dest_config = self.config["topics"]["destination"]
        agg_prefix = dest_config["aggregated_prefix"]
        
        if topic == f"{agg_prefix}/combined":
            self.last_aggregated_update = timestamp
            self.logger.info(f"Received aggregated data update at {timestamp}")
        
        if topic == dest_config.get("modified_load"):
            self.last_modified_load_update = timestamp
            self.logger.debug(f"Received modified load: {payload}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the interceptor service"""
        now = datetime.now()
        
        status = {
            "timestamp": now.isoformat(),
            "monitoring_active": self.client and self.client.is_connected(),
            "total_messages_received": len(self.received_messages),
            "last_aggregated_update": self.last_aggregated_update.isoformat() if self.last_aggregated_update else None,
            "last_modified_load_update": self.last_modified_load_update.isoformat() if self.last_modified_load_update else None,
            "recent_topics": []
        }
        
        # Add recent message info
        for topic, msg_info in self.received_messages.items():
            time_diff = (now - msg_info["timestamp"]).total_seconds()
            if time_diff < 300:  # Last 5 minutes
                status["recent_topics"].append({
                    "topic": topic,
                    "last_update": msg_info["timestamp"].isoformat(),
                    "seconds_ago": round(time_diff, 1),
                    "payload_preview": msg_info["payload"][:100] + "..." if len(msg_info["payload"]) > 100 else msg_info["payload"]
                })
        
        # Sort by most recent
        status["recent_topics"].sort(key=lambda x: x["seconds_ago"])
        
        return status
    
    def print_status(self):
        """Print current status to console"""
        status = self.get_status()
        
        print("\n" + "="*60)
        print("MQTT INTERCEPTOR MONITOR STATUS")
        print("="*60)
        print(f"Timestamp: {status['timestamp']}")
        print(f"Monitoring Active: {status['monitoring_active']}")
        print(f"Total Messages Received: {status['total_messages_received']}")
        
        if status['last_aggregated_update']:
            print(f"Last Aggregated Update: {status['last_aggregated_update']}")
        else:
            print("Last Aggregated Update: None")
        
        if status['last_modified_load_update']:
            print(f"Last Modified Load Update: {status['last_modified_load_update']}")
        else:
            print("Last Modified Load Update: None")
        
        print(f"\nRecent Topics ({len(status['recent_topics'])}):")
        for topic_info in status['recent_topics'][:10]:  # Show top 10
            print(f"  {topic_info['topic']} ({topic_info['seconds_ago']}s ago)")
            print(f"    {topic_info['payload_preview']}")
        
        print("="*60)
    
    def start_monitoring(self, duration_seconds: int = None):
        """Start monitoring for a specified duration or indefinitely"""
        self.setup_mqtt_client()
        
        dest_config = self.config["mqtt"]["destination_broker"]
        
        try:
            self.client.connect(
                dest_config["host"],
                dest_config["port"],
                dest_config["keepalive"]
            )
            
            self.client.loop_start()
            
            self.logger.info(f"Started monitoring for {duration_seconds}s" if duration_seconds else "Started monitoring indefinitely")
            
            start_time = time.time()
            
            try:
                while True:
                    time.sleep(10)  # Print status every 10 seconds
                    self.print_status()
                    
                    if duration_seconds and (time.time() - start_time) > duration_seconds:
                        break
                        
            except KeyboardInterrupt:
                self.logger.info("Monitoring interrupted by user")
            
        except Exception as e:
            self.logger.error(f"Error during monitoring: {e}")
        
        finally:
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
            
            self.logger.info("Monitoring stopped")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MQTT Interceptor Monitor")
    parser.add_argument(
        "--config", 
        default="config/config.yaml",
        help="Configuration file path (default: config/config.yaml)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Monitoring duration in seconds (default: indefinite)"
    )
    
    args = parser.parse_args()
    
    monitor = MQTTMonitor(args.config)
    monitor.start_monitoring(args.duration)


if __name__ == "__main__":
    main()
