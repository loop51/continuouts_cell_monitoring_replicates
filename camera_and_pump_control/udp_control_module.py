import socket
import json
import threading
import time
import os
from datetime import datetime

class UDPController:
    def __init__(self, config_file="udp_config.json"):
        self.config = self.load_config(config_file)
        self.socket = None
        self.running = False
        self.thread = None
        
        # Event callbacks
        self.on_start_recording = None
        self.on_stop_recording = None
        self.on_command_received = None
        
        # Recording state management (simplified - no timers)
        self.recording_start_time = None
        self.is_recording = False
        
    def load_config(self, config_file="udp_config.json"):
        """Load UDP configuration from JSON file"""
        default_config = {
            "network": {
                "ip": "0.0.0.0",
                "port": 12345,
                "buffer_size": 1024,
                "timeout": 1.0
            },
            "commands": {
                "start_recording": "START_REC",
                "stop_recording": "STOP_REC",
                "status": "STATUS",
                "ping": "PING"
            },
            "recording": {
                "force_stop_delay": 1.0
            },
            "security": {
                "validate_commands": True,
                "allowed_ips": []
            },
            "logging": {
                "verbose": True,
                "log_commands": True
            }
        }
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                print(f"Loaded UDP configuration from {config_file}")
            else:
                config = default_config
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
                print(f"Created default UDP configuration file: {config_file}")
            
            return config
        except Exception as e:
            print(f"Error loading UDP config: {e}")
            print("Using default UDP configuration")
            return default_config
    
    def initialize(self):
        """Initialize UDP socket"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(self.config["network"]["timeout"])
            
            ip = self.config["network"]["ip"]
            port = self.config["network"]["port"]
            
            self.socket.bind((ip, port))
            
            if self.config["logging"]["verbose"]:
                print(f"UDP server listening on {ip}:{port}")
            
            return True
            
        except Exception as e:
            print(f"Error initializing UDP socket: {e}")
            return False
    
    def parse_command(self, data, addr):
        """Parse received UDP packet and extract command"""
        try:
            # Try to parse as JSON first
            try:
                message = json.loads(data.decode('utf-8'))
                if self.config["logging"]["log_commands"]:
                    print(f"Received JSON command from {addr}: {message}")
                return message
            except json.JSONDecodeError:
                # Fall back to plain text parsing
                text = data.decode('utf-8').strip()
                if self.config["logging"]["log_commands"]:
                    print(f"Received text command from {addr}: {text}")
                
                # Parse simple text commands
                parts = text.split('|')
                command = parts[0]
                
                if command == self.config["commands"]["start_recording"]:
                    parsed = {
                        "command": "start_recording",
                        "filepath": parts[1] if len(parts) > 1 else None,
                        "filename": parts[2] if len(parts) > 2 else None
                    }
                elif command == self.config["commands"]["stop_recording"]:
                    parsed = {"command": "stop_recording"}
                elif command == self.config["commands"]["status"]:
                    parsed = {"command": "status"}
                elif command == self.config["commands"]["ping"]:
                    parsed = {"command": "ping"}
                else:
                    parsed = {"command": "unknown", "raw": text}
                
                return parsed
                
        except Exception as e:
            print(f"Error parsing command: {e}")
            return {"command": "error", "error": str(e)}
    
    def validate_command(self, message, addr):
        """Validate received command"""
        if not self.config["security"]["validate_commands"]:
            return True
        
        # Check allowed IPs
        allowed_ips = self.config["security"]["allowed_ips"]
        if allowed_ips and addr[0] not in allowed_ips:
            print(f"Rejected command from unauthorized IP: {addr[0]}")
            return False
        
        # Validate command structure
        if not isinstance(message, dict) or "command" not in message:
            print(f"Invalid command structure from {addr}")
            return False
        
        return True
    
    def handle_command(self, message, addr):
        """Handle parsed command"""
        if not self.validate_command(message, addr):
            return
        
        command = message.get("command")
        
        try:
            if command == "start_recording":
                self.handle_start_recording(message, addr)
            elif command == "stop_recording":
                self.handle_stop_recording(message, addr)
            elif command == "status":
                self.handle_status(message, addr)
            elif command == "ping":
                self.handle_ping(message, addr)
            else:
                if self.config["logging"]["verbose"]:
                    print(f"Unknown command: {command}")
        
        except Exception as e:
            print(f"Error handling command '{command}': {e}")
        
        # Call user-defined callback
        if self.on_command_received:
            try:
                self.on_command_received(message, addr)
            except Exception as e:
                print(f"Error in command callback: {e}")
    
    def _force_stop_current_recording(self):
        """Force stop any current recording"""
        if not self.is_recording:
            return
            
        print("DEBUG: Force stopping current recording for new request")
        
        # Call stop callback
        callback_success = False
        if self.on_stop_recording:
            try:
                print("DEBUG: Calling on_stop_recording callback")
                self.on_stop_recording()
                callback_success = True
                print("DEBUG: on_stop_recording callback completed")
            except Exception as e:
                print(f"Error in force stop: {e}")
        
        # Reset state
        self.is_recording = False
        self.recording_start_time = None
        
        if callback_success:
            print("DEBUG: Force stop completed successfully")
        else:
            print("DEBUG: Force stop completed with callback errors")
    
    def handle_start_recording(self, message, addr):
        """Handle start recording command (no timer setup)"""
        filepath = message.get("filepath")
        filename = message.get("filename")
        
        print(f"DEBUG: Start recording request - filepath='{filepath}', filename='{filename}'")
        
        # Build full path
        full_path = None
        if filepath and filename:
            full_path = os.path.join(filepath, filename)
            print(f"DEBUG: Built full path from filepath+filename: '{full_path}'")
        elif filepath:
            full_path = filepath
            print(f"DEBUG: Using filepath as full path: '{full_path}'")
        elif filename:
            full_path = filename
            print(f"DEBUG: Using filename as full path: '{full_path}'")
        else:
            print("DEBUG: No filepath or filename provided, using None")
        
        print(f"DEBUG: Final path for recording: '{full_path}'")
        
        # Check if already recording
        if self.is_recording:
            force_delay = self.config["recording"].get("force_stop_delay", 1.0)
            print(f"DEBUG: Already recording, force_stop_delay={force_delay}")
            
            if force_delay > 0:
                print(f"Already recording, force stopping in {force_delay}s...")
                self._force_stop_current_recording()
                time.sleep(force_delay)
            else:
                print("Already recording! Ignoring new request")
                return
        
        # Start recording
        print(f"DEBUG: About to call on_start_recording callback with path: '{full_path}'")
        
        if self.on_start_recording:
            try:
                print(f"DEBUG: Calling on_start_recording('{full_path}')")
                result = self.on_start_recording(full_path)
                print(f"DEBUG: on_start_recording returned: {result} (type: {type(result)})")
                
                # Determine success
                if result is True:
                    success = True
                    print("DEBUG: Recording start confirmed successful (returned True)")
                elif result is False:
                    success = False
                    print("DEBUG: Recording start failed (returned False)")
                else:
                    # Assume success for None or other return values
                    success = True
                    print(f"DEBUG: Recording start assumed successful (returned {result})")
                
                if success:
                    self.is_recording = True
                    self.recording_start_time = time.time()
                    
                    print(f"DEBUG: Set recording state - is_recording={self.is_recording}, start_time={self.recording_start_time}")
                    print("Recording started successfully (manual stop required)")
                else:
                    print("Failed to start recording - callback returned False")
                    
            except Exception as e:
                print(f"Error starting recording: {e}")
                import traceback
                print(f"DEBUG: Full traceback: {traceback.format_exc()}")
                
                # Reset state on exception
                self.is_recording = False
                self.recording_start_time = None
        else:
            print("DEBUG: No on_start_recording callback set!")
    
    def handle_stop_recording(self, message, addr):
        """Handle stop recording command"""
        print("DEBUG: Stop recording command received")
        
        if not self.is_recording:
            print("Not currently recording")
            return
        
        # Calculate actual recording duration for logging
        actual_duration = time.time() - self.recording_start_time if self.recording_start_time else 0
        print(f"DEBUG: Manual stop after {actual_duration:.1f}s")
        
        # Mark as not recording
        self.is_recording = False
        
        # Call stop recording callback
        callback_success = False
        if self.on_stop_recording:
            try:
                print("DEBUG: Calling on_stop_recording callback")
                self.on_stop_recording()
                callback_success = True
                print("DEBUG: on_stop_recording callback completed")
            except Exception as e:
                print(f"Error stopping recording: {e}")
        
        # Final state cleanup
        self.recording_start_time = None
        
        if callback_success:
            print(f"Recording stopped successfully after {actual_duration:.1f}s")
        else:
            print(f"Recording stopped with errors after {actual_duration:.1f}s")
    
    def handle_status(self, message, addr):
        """Handle status request"""
        status = {
            "recording": self.is_recording,
            "elapsed_time": None
        }
        
        if self.is_recording and self.recording_start_time:
            elapsed = time.time() - self.recording_start_time
            status["elapsed_time"] = f"{elapsed:.1f}s"
        
        print(f"DEBUG: Status request from {addr}: {status}")
        
        # Send status response
        try:
            response = json.dumps(status)
            self.socket.sendto(response.encode('utf-8'), addr)
        except Exception as e:
            print(f"Error sending status response: {e}")
    
    def handle_ping(self, message, addr):
        """Handle ping request"""
        print(f"DEBUG: Ping from {addr}")
        
        try:
            response = "PONG"
            self.socket.sendto(response.encode('utf-8'), addr)
        except Exception as e:
            print(f"Error sending pong: {e}")
    
    def listen_loop(self):
        """Main listening loop (runs in separate thread)"""
        buffer_size = self.config["network"]["buffer_size"]
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(buffer_size)
                message = self.parse_command(data, addr)
                self.handle_command(message, addr)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error in UDP listen loop: {e}")
                break
    
    def start_listening(self):
        """Start UDP listening in background thread"""
        if self.running:
            print("UDP controller already running")
            return False
        
        if not self.initialize():
            return False
        
        self.running = True
        self.thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.thread.start()
        
        print("DEBUG: UDP controller started (manual stop mode)")
        
        return True
    
    def stop_listening(self):
        """Stop UDP listening"""
        self.running = False
        
        # Clean up recording state
        self.is_recording = False
        self.recording_start_time = None
        
        if self.socket:
            self.socket.close()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        
        print("DEBUG: UDP controller stopped")
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_listening()

# Factory function for easy integration
def create_udp_controller(config_file="udp_config.json"):
    """Factory function to create UDP controller"""
    return UDPController(config_file)