import pygame
import math
import time
import json

try:
    import Fluigent
    from Fluigent.SDK import fgt_init, fgt_close
    from Fluigent.SDK import fgt_set_pressure, fgt_get_pressure, fgt_get_pressureRange
    FLUIGENT_AVAILABLE = True
except ImportError:
    print("Warning: Fluigent SDK not available. Pump control will run in simulation mode.")
    FLUIGENT_AVAILABLE = False

class PumpController:
    def __init__(self, config_file="pump_config.json"):
        self.config = self.load_config(config_file)
        self.initialized = False
        self.gamepad = None
        self.pump_index = 0
        
        # State variables
        self.pressure_level = 0
        self.previous_pressure_level = 0
        self.offset = 0
        self.tick_counter = 0
        
        # Button state tracking
        self.prev_button_A = 0
        self.prev_button_Y = 0
        self.prev_button_LB = 0
        self.prev_button_RB = 0
        self.prev_button_back = 0    # Back button (button 6)
        self.prev_button_start = 0   # Start button (button 7)
        
        self.prev_button_B = 0
        self.prev_button_X = 0
        
        # AI control initial values
        self.forward = 0
        self.reverse = 0
        
        # AI control state
        self.ai_control_enabled = False
        self.ai_pressure_override = None
        
        self.update_initial_values_flag = 0
        
        # Timing
        self.print_interval = 15  # Print status every 15 ticks
        
        
        self.save_tracking_data_flag = 0
        
    def load_config(self, config_file="pump_config.json"):
        """Load pump configuration from JSON file"""
        default_config = {
            "pressure": {
                "min_pressure": -800,
                "max_pressure": 1000,
                "normal_max_pressure": 4,
                "multiplying_factor": 5,
                "divisor_factor": 2
            },
            "gamepad": {
                "controller_index": 0,
                "axis_mapping": {
                    "left_stick_vertical": 1,
                    "left_trigger": 4,
                    "right_trigger": 5
                },
                "button_mapping": {
                    "A": 0,
                    "Y": 3,
                    "LB": 4,
                    "RB": 5,
                    "back": 6,
                    "start": 7,
                    'X':2,
                    'B':1
                }
            },
            "pump": {
                "index": 0,
                "simulation_mode": False
            },
            "display": {
                "print_interval": 15,
                "verbose": False
            }
        }
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                print(f"Loaded pump configuration from {config_file}")
            else:
                config = default_config
                # Create default config file
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
                print(f"Created default pump configuration file: {config_file}")
            
            return config
        except Exception as e:
            print(f"Error loading pump config: {e}")
            print("Using default pump configuration")
            return default_config
    
    def initialize(self):
        """Initialize pygame, gamepad, and Fluigent SDK"""
        try:
            # Initialize pygame
            pygame.init()
            pygame.joystick.init()
            
            if pygame.joystick.get_count() == 0:
                print("No gamepad controllers found!")
                return False
            
            # Initialize gamepad
            controller_index = self.config["gamepad"]["controller_index"]
            if controller_index >= pygame.joystick.get_count():
                print(f"Controller index {controller_index} not available. Using controller 0.")
                controller_index = 0
            
            self.gamepad = pygame.joystick.Joystick(controller_index)
            self.gamepad.init()
            print(f"Initialized gamepad: {self.gamepad.get_name()}")
            
            # Initialize Fluigent SDK
            if FLUIGENT_AVAILABLE and not self.config["pump"]["simulation_mode"]:
                fgt_init()
                print("Fluigent SDK initialized")
            else:
                print("Running in simulation mode (no actual pump control)")
            
            self.pump_index = self.config["pump"]["index"]
            self.print_interval = self.config["display"]["print_interval"]
            self.initialized = True
            return True
            
        except Exception as e:
            print(f"Error initializing pump controller: {e}")
            return False
    
    def process_gamepad_input(self, ai_pressure_command=None):
        """Process gamepad input and update pump pressure
        
        Args:
            ai_pressure_command: Optional AI-generated pressure command to override manual control
        """
        if not self.initialized:
            return False
        
        try:
            # Process pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
            
            # Get axis values
            axis_config = self.config["gamepad"]["axis_mapping"]
            button_config = self.config["gamepad"]["button_mapping"]
            
            axis_1 = self.gamepad.get_axis(axis_config["left_stick_vertical"])  # Left stick vertical
            axis_4 = self.gamepad.get_axis(axis_config["left_trigger"])         # Left trigger
            axis_5 = self.gamepad.get_axis(axis_config["right_trigger"])        # Right trigger
            
            # Get button states
            button_A = self.gamepad.get_button(button_config["A"])
            button_Y = self.gamepad.get_button(button_config["Y"])
            button_LB = self.gamepad.get_button(button_config["LB"])
            button_RB = self.gamepad.get_button(button_config["RB"])
            button_X = self.gamepad.get_button(button_config["X"])
            button_B = self.gamepad.get_button(button_config["B"])
            
            
            button_back = self.gamepad.get_button(button_config["back"])     # AI toggle
            button_start = self.gamepad.get_button(button_config["start"])   # AI toggle alternative
            
            # Handle AI control toggle (start button)
            if (button_start == 1 and self.prev_button_start == 0):
                self.update_initial_values_flag = 1
                self.ai_control_enabled = not self.ai_control_enabled
                status = "ENABLED" if self.ai_control_enabled else "DISABLED"
                print(f"AI Control {status}")
                
            if (button_back == 1 and self.prev_button_back == 0):
                self.save_tracking_data_flag = 1
                # self.update_initial_values_flag = 1
                
            # Store AI pressure command if provided
            if ai_pressure_command is not None:
                self.ai_pressure_override = ai_pressure_command
            
            # Handle button presses (only on press, not hold)
            pressure_config = self.config["pressure"]
            
            if button_Y == 1 and self.prev_button_Y == 0:
                self.offset = self.previous_pressure_level
                if self.config["display"]["verbose"]:
                    print(f"Button Y pressed, offset set to: {self.previous_pressure_level}")
            
            if button_A == 1 and self.prev_button_A == 0:
                self.offset = 0
                if self.config["display"]["verbose"]:
                    print("Button A pressed, offset reset to 0")
            
            if button_LB == 1 and self.prev_button_LB == 0:
                self.offset = pressure_config["min_pressure"]
                if self.config["display"]["verbose"]:
                    # print(f"Button LB pressed, offset set to min: {pressure_config['min_pressure']}")
                    print("LB/RB disabled")
            
            if button_RB == 1 and self.prev_button_RB == 0:
                self.offset = pressure_config["max_pressure"]
                if self.config["display"]["verbose"]:
                    # print(f"Button RB pressed, offset set to max: {pressure_config['max_pressure']}")
                    print("LB/RB disabled")
            if button_X == 1 and self.prev_button_X==0:
                self.forward = self.previous_pressure_level
                
            if button_B == 1 and self.prev_button_B==0:
                self.reverse = self.previous_pressure_level
                
            # Calculate pressure level
            normal_max_pressure = pressure_config["normal_max_pressure"]
            multiplying_factor = pressure_config["multiplying_factor"]
            divisor_factor = pressure_config["divisor_factor"]
            
            # Determine final pressure based on control mode
            # if self.ai_control_enabled and self.ai_pressure_override is not None:
            if self.ai_control_enabled:
                # AI control mode - use AI pressure command
                pressure_level = self.ai_pressure_override
                if self.config["display"]["verbose"] and self.tick_counter % 30 == 0:  # Log less frequently
                    print(f"AI Control Active - Pressure: {pressure_level:.1f}")
            else:
                # Manual control mode - use gamepad
                pressure_level = axis_1 * normal_max_pressure
                pressure_level = pressure_level * (1 + ((axis_5 + 1) * multiplying_factor))
                pressure_level = pressure_level / (1 + ((axis_4 + 1) * divisor_factor))
                pressure_level = self.offset + (-1 * pressure_level)
            
            self.pressure_level = pressure_level
            
            # Set pressure
            if FLUIGENT_AVAILABLE and not self.config["pump"]["simulation_mode"]:
                fgt_set_pressure(self.pump_index, pressure_level)
            
            # Update button states
            self.prev_button_A = button_A
            self.prev_button_Y = button_Y
            self.prev_button_LB = button_LB
            self.prev_button_RB = button_RB
            self.prev_button_back = button_back
            self.prev_button_start = button_start
            
            # Print status periodically
            self.tick_counter += 1
            if self.tick_counter >= self.print_interval:
                if FLUIGENT_AVAILABLE and not self.config["pump"]["simulation_mode"]:
                    actual_pressure = fgt_get_pressure(self.pump_index)
                else:
                    actual_pressure = pressure_level  # Simulation
                
                if self.config["display"]["verbose"]:
                    print(f"Actual Pressure: {actual_pressure:.2f}, "
                          f"Set Pressure: {pressure_level:.2f}, "
                          f"Offset: {self.offset:.2f}")
                
                self.tick_counter = 0
            
            self.previous_pressure_level = pressure_level
            return True
            
        except Exception as e:
            print(f"Error processing gamepad input: {e}")
            return False
    
    def get_pressure_info(self):
        """Get current pressure information"""
        if FLUIGENT_AVAILABLE and not self.config["pump"]["simulation_mode"]:
            try:
                actual_pressure = fgt_get_pressure(self.pump_index)
            except:
                actual_pressure = self.pressure_level
        else:
            actual_pressure = self.pressure_level
        if self.pressure_level == None:
            self.pressure_level = 0
        return {
            "set_pressure": self.pressure_level,
            "actual_pressure": actual_pressure,
            "offset": self.offset,
            "previous_pressure": self.previous_pressure_level,
            "ai_control_enabled": self.ai_control_enabled,
            "control_mode": "AI" if self.ai_control_enabled else "Manual"
        }
    def read_update_initial_value_flag(self):
        return self.update_initial_values_flag
        
    def read_initial_values(self):
        self.update_initial_values_flag = 0
        return self.forward, self.reverse, self.ai_control_enabled
        
    def cleanup(self):
        """Clean up resources"""
        try:
            if FLUIGENT_AVAILABLE and not self.config["pump"]["simulation_mode"]:
                fgt_close()
            
            if self.gamepad:
                self.gamepad.quit()
            
            pygame.quit()
            print("Pump controller cleaned up")
            
        except Exception as e:
            print(f"Error during pump controller cleanup: {e}")

# Standalone function for simple integration
def create_pump_controller(config_file="pump_config.json"):
    """Factory function to create and initialize a pump controller"""
    controller = PumpController(config_file)
    if controller.initialize():
        return controller
    else:
        return None