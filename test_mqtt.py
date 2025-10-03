#!/usr/bin/env python3
"""
MQTT Test Script

Simple script to test MQTT connectivity and simulate Solar Assistant messages
for testing the interceptor service.
"""

import json
import time
import random
from datetime import datetime
import yaml
import paho.mqtt.client as mqtt


class MQTTTester:
    """Test MQTT connectivity and simulate messages"""
    
    def __init__(self, config_file: str = "config/config.yaml"):
        self.config = self._load_config(config_file)
        self.client = None
    
    def _load_config(self, config_file: str):
        """Load configuration"""
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def setup_client(self):
        """Setup MQTT client"""
        self.client = mqtt.Client(client_id="mqtt_tester")
        
        broker_config = self.config["mqtt"]["source_broker"]
        
        if broker_config.get("username"):
            self.client.username_pw_set(
                broker_config["username"],
                broker_config.get("password", "")
            )
        
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
    
    def _on_connect(self, client, userdata, flags, rc):
        """Connection callback"""
        if rc == 0:
            print("✓ Connected to MQTT broker")
        else:
            print(f"✗ Failed to connect: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Disconnection callback"""
        print(f"Disconnected from broker: {rc}")
    
    def test_connectivity(self):
        """Test basic MQTT connectivity"""
        print("Testing MQTT connectivity...")
        
        broker_config = self.config["mqtt"]["source_broker"]
        
        try:
            self.client.connect(
                broker_config["host"],
                broker_config["port"],
                broker_config["keepalive"]
            )
            
            self.client.loop_start()
            time.sleep(2)  # Wait for connection
            
            if self.client.is_connected():
                print("✓ MQTT connectivity test passed")
                return True
            else:
                print("✗ MQTT connectivity test failed")
                return False
                
        except Exception as e:
            print(f"✗ MQTT connectivity error: {e}")
            return False
    
    def simulate_solar_assistant_messages(self, duration_seconds: int = 60):
        """Simulate Solar Assistant messages for testing"""
        print(f"Simulating Solar Assistant messages for {duration_seconds} seconds...")
        
        if not self.client.is_connected():
            print("✗ Not connected to MQTT broker")
            return
        
        topics = self.config["topics"]["source"]
        start_time = time.time()
        message_count = 0
        
        try:
            while (time.time() - start_time) < duration_seconds:
                # Simulate realistic solar data
                current_time = datetime.now()
                
                # Power (varies throughout the day)
                hour = current_time.hour
                if 6 <= hour <= 18:  # Daylight hours
                    base_power = 3000 + random.randint(-500, 2000)
                else:  # Night
                    base_power = random.randint(-200, 200)
                
                power = base_power + random.randint(-100, 100)
                
                # Load (household consumption)
                load = random.randint(800, 2500)
                
                # Battery voltage
                voltage = 48.0 + random.uniform(-2.0, 2.0)
                
                # Battery SoC
                battery_soc = random.randint(20, 100)
                
                # Temperature
                temperature = 25.0 + random.uniform(-5.0, 10.0)
                
                # Energy (cumulative)
                energy = random.uniform(10.0, 50.0)
                
                # Cell voltages
                min_cell_voltage = 3.2 + random.uniform(-0.1, 0.2)
                max_cell_voltage = 3.4 + random.uniform(-0.1, 0.2)
                
                # Publish messages
                messages = [
                    (topics.get("power"), power),
                    (topics.get("load"), load),
                    (topics.get("voltage"), voltage),
                    (topics.get("battery_soc"), battery_soc),
                    (topics.get("temperature"), temperature),
                    (topics.get("energy"), energy),
                    (topics.get("min_cell_voltage"), min_cell_voltage),
                    (topics.get("max_cell_voltage"), max_cell_voltage),
                ]
                
                for topic, value in messages:
                    if topic:  # Only publish if topic is configured
                        self.client.publish(topic, str(value))
                        message_count += 1
                
                # Also simulate EV battery SoC (from Hubitat)
                if topics.get("ev_battery_soc"):
                    ev_soc = random.randint(20, 90)
                    self.client.publish(topics["ev_battery_soc"], str(ev_soc))
                    message_count += 1
                
                print(f"Published {len([t for t, _ in messages if t]) + 1} messages "
                      f"(Power: {power}W, Load: {load}W, Battery: {battery_soc}%)")
                
                time.sleep(1)  # 1 second between message batches
        
        except KeyboardInterrupt:
            print("\nSimulation interrupted by user")
        
        print(f"Simulation complete. Published {message_count} total messages.")
    
    def listen_for_aggregated_data(self, duration_seconds: int = 60):
        """Listen for aggregated data from the interceptor"""
        print(f"Listening for aggregated data for {duration_seconds} seconds...")
        
        # Use destination broker for listening
        dest_client = mqtt.Client(client_id="mqtt_tester_listener")
        dest_config = self.config["mqtt"]["destination_broker"]
        
        if dest_config.get("username"):
            dest_client.username_pw_set(
                dest_config["username"],
                dest_config.get("password", "")
            )
        
        received_messages = []
        
        def on_message(client, userdata, msg):
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            timestamp = datetime.now()
            
            received_messages.append({
                "topic": topic,
                "payload": payload,
                "timestamp": timestamp
            })
            
            print(f"Received: {topic} = {payload}")
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print("✓ Connected to destination broker")
                # Subscribe to aggregated topics
                agg_prefix = self.config["topics"]["destination"]["aggregated_prefix"]
                client.subscribe(f"{agg_prefix}/+/+")
                client.subscribe(f"{agg_prefix}/combined")
                
                # Subscribe to modified load
                modified_load_topic = self.config["topics"]["destination"]["modified_load"]
                if modified_load_topic:
                    client.subscribe(modified_load_topic)
                
                print(f"Subscribed to {agg_prefix}/# and {modified_load_topic}")
            else:
                print(f"✗ Failed to connect to destination broker: {rc}")
        
        dest_client.on_connect = on_connect
        dest_client.on_message = on_message
        
        try:
            dest_client.connect(
                dest_config["host"],
                dest_config["port"],
                dest_config["keepalive"]
            )
            
            dest_client.loop_start()
            
            start_time = time.time()
            while (time.time() - start_time) < duration_seconds:
                time.sleep(1)
            
            dest_client.loop_stop()
            dest_client.disconnect()
            
            print(f"\nListening complete. Received {len(received_messages)} messages:")
            for msg in received_messages[-10:]:  # Show last 10 messages
                print(f"  {msg['timestamp'].strftime('%H:%M:%S')} - {msg['topic']}: {msg['payload'][:50]}...")
        
        except Exception as e:
            print(f"✗ Error listening for messages: {e}")
    
    def run_full_test(self):
        """Run a complete test sequence"""
        print("MQTT Interceptor Test Suite")
        print("=" * 40)
        
        self.setup_client()
        
        # Test 1: Connectivity
        if not self.test_connectivity():
            print("Connectivity test failed. Check your MQTT broker configuration.")
            return
        
        print("\n" + "-" * 40)
        
        # Test 2: Message simulation
        print("Starting message simulation...")
        print("Make sure the MQTT Interceptor service is running!")
        input("Press Enter to continue or Ctrl+C to cancel...")
        
        # Start listening in background (would need threading for real implementation)
        print("\nTo test aggregated output, run this in another terminal:")
        print("python test_mqtt.py --listen")
        
        # Simulate messages
        self.simulate_solar_assistant_messages(30)
        
        print("\nTest complete!")
        print("Check the interceptor logs and your MQTT broker for aggregated messages.")
    
    def cleanup(self):
        """Cleanup MQTT connections"""
        if self.client and self.client.is_connected():
            self.client.loop_stop()
            self.client.disconnect()


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MQTT Interceptor Test Script")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Configuration file path"
    )
    parser.add_argument(
        "--simulate",
        type=int,
        help="Simulate Solar Assistant messages for N seconds"
    )
    parser.add_argument(
        "--listen",
        type=int,
        help="Listen for aggregated messages for N seconds"
    )
    parser.add_argument(
        "--test-connectivity",
        action="store_true",
        help="Test MQTT broker connectivity only"
    )
    
    args = parser.parse_args()
    
    tester = MQTTTester(args.config)
    
    try:
        if args.test_connectivity:
            tester.setup_client()
            tester.test_connectivity()
        elif args.simulate:
            tester.setup_client()
            if tester.test_connectivity():
                tester.simulate_solar_assistant_messages(args.simulate)
        elif args.listen:
            tester.listen_for_aggregated_data(args.listen)
        else:
            tester.run_full_test()
    
    finally:
        tester.cleanup()


if __name__ == "__main__":
    main()
