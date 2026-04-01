import cv2
print("OpenCV version:", cv2.__version__)
import json
import os
import numpy as np
import time
import math
import matplotlib.pyplot as plt
from collections import deque
import pprint
import csv
CSV_FILE_PATH = r'L:\My Drive\Clemson Classes\Measurements\VNA\VNA N5230A\Nature_Bio_Replicate\Python_Saiful_Fall2025\vs2\data.csv'
class AIVisionController:
    def __init__(self, config_file="ai_vision_config.json"):
        self.config = self.load_config(config_file)
        self.enabled = False
        self.last_detection_time = 0
        self.detection_results = {}
        self.cell_lost_count = 0
        
        # self.logging_csv = False
        
        # Pump control parameters
        self.target_pressure = 0
        self.pressure_limits = (-800, 1000)

        # OpenCV Multi-tracker system
        self.multi_tracker = cv2.legacy.MultiTracker_create()
        self.tracked_objects = {}  # Dictionary of track info by ID
        self.next_track_id = 1     # Counter for assigning new track IDs
        self.tracker_type = "CSRT"  # Can be CSRT, KCF, MOSSE, MIL, etc.
        self.min_detection_area = 25  # Minimum area to start tracking
        
        # Velocity plotting setup
        self.velocity_history = deque(maxlen=1000)  # Store up to 1000 data points
        self.time_history = deque(maxlen=1000)
        self.plot_enabled = self.config.get("velocity_plotting", {}).get("enabled", True)
        self.plot_window_size = self.config.get("velocity_plotting", {}).get("window_size_seconds", 20.0)
        self.fig = None
        self.ax = None
        self.velocity_line = None
        
        # dumb method to control
        self.line_top = self.config["horizontal_lines"]["c_line_y"] - self.config["horizontal_lines"]["gap_l"]
        self.line_bottom = self.config["horizontal_lines"]["c_line_y"] + self.config["horizontal_lines"]["gap_l"]
        self.pressure_from_top = 0
        self.pressure_from_bottom = 0
        self.time_to_last_check_point= 0
        self.cell_direction = 1 # 1 forward, -1 reverse
        self.velocity_target = self.config["tracking_config"]["target_velocity"]
        self.prev_error = 0
        self.integral = 0
        self.adjusment_val = 0.2
        
        self.start_time = time.time()
        # state machine to track
        self.tracking_vars = {
                        "state" : "Search", # states are --> "Search", "Acquiring", "Track"
                        'bbox' : [],
                        "centers" : [],
                        "area" : [],
                        "contour" : [],
                        "w" : [],
                        "h" : [],
                        "time_stamps" : [],
                        "velocities" : [],
                        "acceleration" : [],
                        "future_velocity" : [],
                        "future_position" : [],
                        "TrackState" : "Regular" # it can be --> "Regular" or "OcclusionZone"
        }
        
        # background edge removal
        self.background_frame = {
                        "raw_frame": None,
                        "edge_frame": None,
                        "threshold_frame": None
                        }
                            
        try:
            os.remove(CSV_FILE_PATH)
        except:
            print("no data.csv file")
                
        # Initialize plotting if enabled
        if self.plot_enabled:
            self.setup_velocity_plot()
    
    def setup_background(self, frame):
        canny_low = self.config["detection"]["canny_low"]
        canny_high = self.config["detection"]["canny_high"]
        threshold_value = self.config["detection"]["threshold_value"]
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur_kernel = self.config["detection"]["blur_kernel"]
        dilate_kernel = self.config["detection"]["dilate_kernel"]
        if blur_kernel >= 1:
            blurred = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)
        frame = blurred
        kernel_bg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_kernel, dilate_kernel))
        kernel_edges = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_kernel, dilate_kernel))
        
        
        edges = cv2.Canny(gray, canny_low, canny_high)
        
        _, thresh_binary = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY_INV)
        
        thresh_binary = cv2.dilate(thresh_binary, kernel_bg, iterations=2)
        edges = cv2.dilate(edges, kernel_edges, iterations=1)
        
        self.background_frame = {
                        "raw_frame": frame,
                        "edge_frame": edges,
                        "threshold_frame": thresh_binary
        }
        
    def update_control_initial_params(self, x, y, control):
        # self.config = self.load_config("ai_vision_config.json")
        self.pressure_from_top = x
        self.pressure_from_bottom = y
        self.enabled = control
        
        
    def load_config(self, config_file="ai_vision_config.json"):
        """Load AI vision configuration from JSON file"""
        default_config = {
            "detection": {
                "detection_interval": 0.1,  # seconds between detections
                "min_contour_area": 100,
                "blur_kernel": 5,
                "find_most_spherical": True
            },
            "horizontal_lines": {
                "c_line_y": 300,        # Y coordinate of the center line
                "gap_l": 50,            # Vertical pixels between lines
                "show_lines": True,     # Show lines in verbose mode
                "line_color": [255, 0, 0],  # Blue color for lines
                "c_line_color": [0, 0, 255],  # Red color for center line
                "line_thickness": 1
            },
            "pump_control": {
                "base_pressure": 0,
                "max_pressure_change": 200,
                "smoothing_factor": 0.3,
                "deadband": 10,  # minimum change to trigger response
                "pressure_limits": [-10, 10]  # Changed to +/-10 range
            },
            "position_control": {
                "enabled": True,
                "control_gain": 0.5,        # How aggressive the response is (0-1)
                "target_zone_lines": 1,     # Use first line above/below C line as boundaries
                "reverse_on_overshoot": True, # Reverse direction on overshoot
                "velocity_control": True,   # Enable velocity-based control
                "target_velocity": 40.0,    # Target velocity: 100px / 2.5s = 40 px/s
                "velocity_tolerance": 5.0,  # Acceptable velocity range (Â±5 px/s)
                "velocity_gain": 0.3        # How much velocity error affects pressure
            },
            "area_mapping": {
                "min_area": 500,      # Minimum area to trigger response
                "max_area": 5000,     # Maximum area for full response
                "min_pressure": -100, # Pressure for min area
                "max_pressure": 100   # Pressure for max area
            },
            "spherical_detection": {
                "circularity_threshold": 0.7,  # 0.7 = 70% circular
                "prefer_near_c_line": True,     # Prefer objects near C line
                "distance_weight": 0.5          # Weight for distance vs circularity
            },
            "visualization": {
                "show_detections": True,
                "show_pressure_overlay": True,
                "detection_color": [0, 255, 0],
                "selected_object_color": [0, 255, 255],  # Yellow for selected object
                "text_color": [255, 255, 255],
                "verbose_mode": True
            },
            "logging": {
                "verbose": True
            },
            "velocity_plotting": {
                "enabled": True,
                "window_size_seconds": 20.0,
                "update_interval": 0.1,
                "y_range": [-100, 100]
            }
        }
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                print(f"Loaded AI vision configuration from {config_file}")
            else:
                config = default_config
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
                print(f"Created default AI vision configuration file: {config_file}")
            
            return config
        except Exception as e:
            print(f"Error loading AI vision config: {e}")
            return default_config
    
    def setup_velocity_plot(self):
        """Initialize the velocity plotting system"""
        if not self.plot_enabled:
            return
            
        try:
            # Set up matplotlib for real-time plotting
            plt.ion()  # Turn on interactive mode
            
            # Create figure and axis
            self.fig, self.ax = plt.subplots(figsize=(10, 6))
            self.ax.set_title('Selected Object Velocity Over Time')
            self.ax.set_xlabel('Time (seconds ago)')
            self.ax.set_ylabel('Velocity (px/s)')
            self.ax.grid(True, alpha=0.3)
            
            # Initialize empty line for velocity data
            self.velocity_line, = self.ax.plot([], [], 'b-', linewidth=2, label='Velocity')
            
            # Add target velocity line if position control is enabled
            if self.config.get("position_control", {}).get("enabled", False):
                target_vel = self.config["position_control"].get("target_velocity", 40)
                self.ax.axhline(y=target_vel, color='g', linestyle='--', alpha=0.7, label='Target Velocity')
                self.ax.axhline(y=-target_vel, color='g', linestyle='--', alpha=0.7)
            
            self.ax.legend()
            self.ax.set_xlim(-self.plot_window_size, 0)
            self.ax.set_ylim(-100, 100)  # Adjust based on expected velocity range
            
            # Show the plot window
            plt.show(block=False)
            plt.draw()
            
            if self.config["logging"]["verbose"]:
                print("Velocity plotting initialized")
            
        except Exception as e:
            print(f"Error setting up velocity plot: {e}")
            self.plot_enabled = False

    def update_velocity_plot(self, current_time, velocity):
        """Update the velocity plot with new data"""
        if not self.plot_enabled or not hasattr(self, 'fig') or self.fig is None:
            return
            
        try:
            # Add new data point
            self.velocity_history.append(velocity if velocity is not None else 0)
            self.time_history.append(current_time)
            
            # Remove data points older than window size
            cutoff_time = current_time - self.plot_window_size
            while self.time_history and self.time_history[0] < cutoff_time:
                self.time_history.popleft()
                self.velocity_history.popleft()
            
            # Convert to lists for plotting
            if len(self.time_history) > 1:
                # Convert absolute timestamps to relative (seconds ago)
                times_relative = [t - current_time for t in self.time_history]
                velocities = list(self.velocity_history)
                
                # Update the plot data
                self.velocity_line.set_data(times_relative, velocities)
                
                # Auto-scale Y axis based on data
                if velocities:
                    y_min = min(velocities) - 10
                    y_max = max(velocities) + 10
                    self.ax.set_ylim(y_min, y_max)
                
                # Refresh the plot
                plt.draw()
                plt.pause(0.001)  # Small pause to allow plot update
                
        except Exception as e:
            if self.config["logging"]["verbose"]:
                print(f"Error updating velocity plot: {e}")

    def toggle_velocity_plot(self):
        """Toggle velocity plotting on/off"""
        if self.plot_enabled and hasattr(self, 'fig') and self.fig is not None:
            self.plot_enabled = False
            plt.close(self.fig)
            self.fig = None
            print("Velocity plotting disabled")
        else:
            self.plot_enabled = True
            self.setup_velocity_plot()
            print("Velocity plotting enabled")
        return self.plot_enabled
    
    def initialize(self):
        """Initialize the AI vision system"""
        try:
            
            # Get tracker type from config
            # self.tracker_type = self.config["velocity_tracking"].get("tracker_type", "CSRT")
            # self.min_detection_area = self.config["velocity_tracking"].get("min_tracking_area", 25)
            
            # Initialize pressure limits
            # self.pressure_limits = tuple(self.config["pump_control"]["pressure_limits"])
            
            if self.config["logging"]["verbose"]:
                print("AI Vision Controller initialized")
                print(f"Detection: Contour-based (Most Spherical)")
                print(f"Control: Proportional")
                print(f"C-Line Y: {self.config['horizontal_lines']['c_line_y']}")
                print(f"Gap L: {self.config['horizontal_lines']['gap_l']}")
                print(f"Pressure limits: {self.pressure_limits}")
                print(f"Velocity plotting: {'Enabled' if self.plot_enabled else 'Disabled'}")
            
            return True
            
        except Exception as e:
            print(f"Error initializing AI vision controller: {e}")
            return False
    def reload_config(self):
        config_file="ai_vision_config.json"
        self.config = self.load_config(config_file)
        self.start_time = self.start_time - 60
        # self.setup_background()

    def save_tracking_data(self):
        if self.tracking_vars["state"] == "Track":
            t = self.tracking_vars["time_stamps"]
            # v = self.tracking_vars["velocities"]
            pos_x = self.tracking_vars["centers"][:,0]
            pos_y = self.tracking_vars["centers"][:,1]
            
            v = self.tracking_vars["velocities"]
            # data = np.vstack((t,v)).T
            
            data = np.vstack((t,pos_x, pos_y)).T
            np.savetext('position_tracking_log.csv', data, delimiter=',')
            np.savetext('velocity_log.csv', v, delimiter = ',')
        
    def track_search_state(self, detections):
        # this functions, searches for a detection self.config["tracking_config"]["search_range"] away from
        # the center line
        top_bound = self.config["horizontal_lines"]["c_line_y"] - self.config["tracking_config"]["search_range"]
        bottom_bound = self.config["horizontal_lines"]["c_line_y"] + self.config["tracking_config"]["search_range"]
        
        in_range = []
        for tracks in detections:
            # result = top_bound <= tracks["bbox"][1] <= bottom_bound
            # print(f"Is track in range: {result}")
            
            if  top_bound <= tracks["bbox"][1] <= bottom_bound:
                in_range.append(tracks)
        
        if in_range:
            selected_detection = self.find_smallest_near_c_line(in_range)
            return selected_detection
        else:
            return None
            
    
    def track_acquire_state(self, detections):
        cell = []
        # print(f'number of tracks: {len(detections)}')
        for tracks in detections:
            contour = tracks["contour"]
            match_factor = cv2.matchShapes(self.tracking_vars["contour"][-1],contour, cv2.CONTOURS_MATCH_I1, 0.0) # closer to 0 means more match

            area = tracks["area"]
            # print('getting previous information...')
            prev_area = self.tracking_vars["area"][-1]
            # print(f"previous area: {prev_area}")
            area_error = self.config["tracking_config"]["matching_area"]
            
            # print(f" match_factor now: {match_factor}, area: {area}")
            # print(f" match_factor prev: {match_factor}, area: {prev_area}")
            if prev_area * (1-area_error) <= area <= prev_area * (1+area_error) and match_factor < self.config["tracking_config"]["matching_shape_constant"]:
                cell = tracks
        # hopefuly there will be only one cell that matches 
        if not cell:
            print(f"match factor: {match_factor}, current area: {area}, prev area: {prev_area}")
        return cell
    
    def append_track_variable(self, selected_detection):
        self.tracking_vars["centers"].append(selected_detection["center"])
        self.tracking_vars["bbox"].append(selected_detection["bbox"])
        self.tracking_vars["contour"].append(selected_detection["contour"])
        
        
        self.tracking_vars["w"].append(selected_detection["width"])
        self.tracking_vars["h"].append(selected_detection["height"])
        
        
        self.tracking_vars["time_stamps"].append(selected_detection["timestamp"])
        self.tracking_vars["area"].append(selected_detection["area"])
    
    def trim_array_inplace(self, arr):
        hs = self.config["tracking_config"]["history_size"]
        if len(arr) > hs:
        # Remove excess elements from the front
            del arr[:-hs]
        return arr
    
    def trim_track_variable(self):
        for key in self.tracking_vars:
            self.trim_array_inplace(self.tracking_vars[key])
                                    
    def clear_track_variable(self,state="Search"):
        
        self.tracking_vars = {
                        "state" : state, # states are --> "Search", "Acquiring", "Track"
                        'bbox' : [],
                        "centers" : [],
                        "area" : [],
                        "contour" : [],
                        "w" : [],
                        "h" : [],
                        "time_stamps" : [],
                        "velocities" : [],
                        "acceleration" : [],
                        "future_velocity" : [],
                        "future_position" : [],
                        "TrackState" : "Regular" # it can be --> "Regular" or "OcclusionZone"
        }
    def tracking_algo_execution_new(self, detections):
        selected_detection = []
        occlusion_zone = self.config["tracking_config"]["occlusion_zone_extent"]
        c_line = self.config["horizontal_lines"]["c_line_y"]
        position_tolerance = self.config["tracking_config"]["tracked_object_tolerance"]
        wait_to_find_another_limit = self.config["tracking_config"]["lost_wait"]
        gap_l = self.config["horizontal_lines"]["gap_l"]
        frames_to_use = self.config["tracking_config"]["acquiring_frames"]
        condition = c_line - gap_l * 6
        
        if self.tracking_vars["future_position"]:
            
            fp_x = self.tracking_vars["future_position"][-1][0]
            fp_y = self.tracking_vars["future_position"][-1][1]
            '''
            for track in detections:
                x = track["center"][0]
                y = track["center"][1]
                
                if abs(x-fp_x) < position_tolerance and abs(y-fp_y) < position_tolerance:
                    
                    if track["center"][1] < condition:
                        selected_detection = []
                
                    else:
                        selected_detection = track
                        self.cell_lost_count =0
                else:
                    print(f"mismatch, fp_x: {fp_x}, x: {x}, fp_y:{fp_y}, y:{y}")
            
            '''
            print('checkpoint: 1')
            selected_detection = self.find_smallest_near_y(detections, fp_y)
            print('checkpoint: 2')
            if not selected_detection:
                
                self.cell_lost_count += 1
                if self.cell_lost_count > self.config["tracking_config"]["lost_wait"]:
                    self.clear_track_variable()
        else:
            
            # self.clear_track_variable()
            selected_detection = self.find_smallest_near_c_line(detections)
                
        if selected_detection and self.tracking_vars["velocities"]:
            
            current_time = selected_detection["timestamp"]
            
            prev_time = self.tracking_vars["time_stamps"][-1]
            
            elapsed_time  = current_time - prev_time
            u = self.tracking_vars["velocities"][-1]
            
            
            # acceleration = []
            # avg_acceleration = 0
            # if len(self.tracking_vars["velocities"]) > frames_to_use:
            #     # if enough velocity points are present then calculate acceleration as well
            #     # print('checkpoint: 4')  
                
            #     for i in range(-frames_to_use, -1):  # -frames_to_use to -2
                                     
            #         v1 = self.tracking_vars["centers"][i]
            #         v2 = self.tracking_vars["centers"][i+1]
            #         t1 = self.tracking_vars["time_stamps"][i]
            #         t2 = self.tracking_vars["time_stamps"][i+1]
                    
            #         if t2!=t1:
            #             a = (v2-v1)/(t2-t1)
            #             acceleration.append(a)
            
            # if acceleration:
                
            #     avg_acceleration = sum(acceleration)/len(acceleration)
                
            # else:
            #     avg_acceleration = 0
            
            # fp = u * elapsed_time + ((0.5) * avg_acceleration * (elapsed_time**2))
            fp = u * elapsed_time 
            fp_y = self.tracking_vars["centers"][-1][1] + fp
            fp_x = self.tracking_vars["centers"][-1][0]
              
            self.tracking_vars["future_position"].append((fp_x, fp_y))
            # print('checkpoint: 5')  
            # track["center"][1] < condition:
        if selected_detection["center"][1] < condition:
            selected_detection = []
        
        return selected_detection
    
    def tracking_algo_execution(self, detections):
        selected_detection = []
        occlusion_zone = self.config["tracking_config"]["occlusion_zone_extent"]
        c_line = self.config["horizontal_lines"]["c_line_y"]
        # print(f"number of detections: {len(detections)}")
        
        if self.tracking_vars["TrackState"] == "OcclusionZone":  
            '''    
            self.tracking_vars["future_position"] = []
            best_track = None
            best_score = float('Inf')
            for track in detections:
                contour = track["contour"]
                
                area = track["area"]
                track_x, track_y = track["center"]
                print("checkpoint: 1")
                condition = abs(track_y - self.config["horizontal_lines"]["c_line_y"])
                
                if not (condition > occlusion_zone and condition < 50):
                    continue  

                prev_contour = self.tracking_vars["contour"][-1]
                prev_area = self.tracking_vars["area"][-1]
                prev_x,prev_y = self.tracking_vars["centers"][-1]
                
                match_factor = cv2.matchShapes(prev_contour,contour, cv2.CONTOURS_MATCH_I1, 0.0) # closer to 0 means more match
                
                x_diff = abs(track_x - prev_x)
                area_diff = abs(area - prev_area)
                
                # Combine into a single score (you may want to adjust weights)
                # score = x_diff + area_diff + match_factor * 100  # Scale match_factor since it's typically small
                score = x_diff
                
                if score < best_score:
                    best_score = score
                    best_track = track
                    
                if best_track is not None:
                    selected_detection = best_track
                    self.tracking_vars["TrackState"] == "Regular"
                
            '''
            if self.tracking_vars['bbox']:
                x = self.tracking_vars['bbox'][-1][0]
                y = self.tracking_vars['bbox'][-1][1]
                w = self.tracking_vars['width'][-1]
                h = self.tracking_vars['height'][-1]
                area = self.tracking_vars['area'][-1]
                contour = self.tracking_vars['contour'][-1]
            
                if self.tracking_vars["velocities"]:
                    current_time = track["timestamp"]
                    prev_time = self.tracking_vars["time_stamps"][-1]
                    elapsed_time  = current_time - prev_time
                    u = self.tracking_vars["velocities"][-1]
                    fp = u * elapsed_time
                    fp_y = self.tracking_vars["centers"][-1][1] + fp
                    fp_x = self.tracking_vars["centers"][-1][0]
                    
                    self.tracking_vars["future_position"].append((fp_x, fp_y))
                        
                if abs(y - c_line) > occlusion_zone:
                    
                    selected_detection = self.find_smallest_near_c_line(detections)
                    self.tracking_vars["TrackState"] = "Regular"
                    return selected_detection
                else:
                    if not fp_x or not fp_y:
                        x = self.tracking_vars["future_position"][-1][0]
                        y = self.tracking_vars["future_position"][-1][1]
                    else:
                        x = fp_x
                        y = fp_y    
                    
                    dummy_detection = {
                        'bbox': [x, y, x + w, y + h],
                        'area': area,
                        'center': [x + w/2, y + h/2],
                        'contour': contour,
                        'width': w,
                        'height': h,
                        'distance_to_c_line': abs((y + h/2) - self.config['horizontal_lines']['c_line_y']),
                        'velocity': None,  # Will be filled in later by velocity tracking
                        'timestamp': time.time(),
                        'direction': None
                        
                        }
                    return dummy_detection
            else:
                self.tracking_vars["future_position"] = []
                best_track = None
                best_score = float('Inf')
                for track in detections:
                    contour = track["contour"]
                    
                    area = track["area"]
                    track_x, track_y = track["center"]
                    # print("checkpoint: 1")
                    condition = abs(track_y - self.config["horizontal_lines"]["c_line_y"])
                    
                    if not (condition > occlusion_zone and condition < 50):
                        continue  

                    prev_contour = self.tracking_vars["contour"][-1]
                    prev_area = self.tracking_vars["area"][-1]
                    prev_x,prev_y = self.tracking_vars["centers"][-1]
                    
                    match_factor = cv2.matchShapes(prev_contour,contour, cv2.CONTOURS_MATCH_I1, 0.0) # closer to 0 means more match
                    
                    x_diff = abs(track_x - prev_x)
                    area_diff = abs(area - prev_area)
                    
                    # Combine into a single score (you may want to adjust weights)
                    # score = x_diff + area_diff + match_factor * 100  # Scale match_factor since it's typically small
                    score = x_diff
                    
                    if score < best_score:
                        best_score = score
                        best_track = track
                        
                    if best_track is not None:
                        selected_detection = best_track
                        self.tracking_vars["TrackState"] == "Regular"
                    # '''         
        elif self.tracking_vars["TrackState"] == "Regular":
            
            
            best_track = None
            best_score = float('Inf')
            # pprint.pprint(self.tracking_vars)
            if not self.tracking_vars["centers"]:
                # print("checkpoint: 1")
                selected_detection = self.find_smallest_near_c_line(detections)
                
                return selected_detection
            
            for track in detections:
                contour = track["contour"]
                
                area = track["area"]
                # print("checkpoint: 1")
                
                (track_x, track_y) = track["center"]
                
                
                condition = abs(track_y - self.config["horizontal_lines"]["c_line_y"])
                occlusion_zone = self.config["tracking_config"]["occlusion_zone_extent"]
                if condition < occlusion_zone:
                    self.tracking_vars["TrackState"] == "OcclusionZone"
                       
                
                
                if self.tracking_vars["velocities"]:
                    current_time = track["timestamp"]
                    prev_time = self.tracking_vars["time_stamps"][-1]
                    elapsed_time  = current_time - prev_time
                    u = self.tracking_vars["velocities"][-1]
                    fp = u * elapsed_time
                    fp_y = self.tracking_vars["centers"][-1][1] + fp
                    fp_x = self.tracking_vars["centers"][-1][0]
                    
                    self.tracking_vars["future_position"].append((fp_x, fp_y))
                    if abs(fp_y - self.config["horizontal_lines"]["c_line_y"]) < occlusion_zone:
                        
                        self.tracking_vars["TrackState"] == "OcclusionZone"
                        
                        continue
                
                
                
                
                
                prev_contour = self.tracking_vars["contour"][-1]
                prev_area = self.tracking_vars["area"][-1]
                prev_x,prev_y = self.tracking_vars["centers"][-1]
                
                match_factor = cv2.matchShapes(prev_contour,contour, cv2.CONTOURS_MATCH_I1, 0.0) # closer to 0 m
                area_diff = area - prev_area
                
                
                if self.tracking_vars["future_position"]:  # Not empty list
                    
                    # print(f"future positions: {self.tracking_vars['future_position'][-1]}")
                    fp_x, fp_y = self.tracking_vars["future_position"][-1]
                    
                    x_diff = abs(track_x - fp_x)
                    y_diff = abs(track_y - fp_y)
                    position_diff = np.sqrt(x_diff**2 + y_diff**2)
                    
                    # score = position_diff + area_diff + match_factor * 100
                    score = position_diff
                    if score < best_score:
                        best_score = score
                        best_track = track
                        
                    if best_track is not None:
                        selected_detection = best_track
                else:
                    # Empty list - no position component in score
                    selected_detection = self.find_smallest_near_c_line(detections)
                    # score = area_diff + match_factor * 100                
                
                
        c_line = self.config["horizontal_lines"]["c_line_y"]
        gap_l  = self.config["horizontal_lines"]["gap_l"]
        top_limit = self.config["tracking_config"]["top_limit"]
        bottom_limit = self.config["tracking_config"]["bottom_limit"]
        
        condition = c_line - gap_l * top_limit
        condition1 = c_line + gap_l * bottom_limit
        if selected_detection["center"][1] < condition or selected_detection["center"][1] > condition1:
            selected_detection = []
        return selected_detection
    def process_frame(self, frame, current_pressure):
        """Process a frame and return pressure command"""
        if not self.enabled:
            self.clear_track_variable()
            self.prev_error = 0
            return current_pressure
        
        # Check detection interval
        current_time = time.time()
        elapsed_time = current_time - self.start_time
        if current_time - self.last_detection_time < self.config["detection"]["detection_interval"]:
            return self.target_pressure
        
        
        
        if elapsed_time  > 30:
            self.start_time = time.time()
            self.setup_background(frame)
            
        self.last_detection_time = current_time
        
        try:
            
            detections, debug_images = self.detect_contours(frame)
            # cv2.imshow('canny', debug_images['canny'])
            # cv2.imshow('threshold', debug_images['threshold'])
            cv2.imshow('final', debug_images['final'])
            
            # Find small object closest to C line
            # selected_detection = self.find_smallest_near_c_line(detections)
            
            if self.config["tracking_config"]["new_algorithm"]:
                
                selected_detection = self.tracking_algo_execution_new(detections)    
            else:
                selected_detection = self.tracking_algo_execution(detections)    
            if selected_detection:
                self.append_track_variable(selected_detection)
                if len(self.tracking_vars["centers"]) >=5:
                    self.calculate_object_velocity()
            
                
            # self.log_track_vars()   
            self.trim_track_variable()
            # now do the pressure control
            
            pressure_command = self.calculate_pressure_command(selected_detection, current_pressure)

            # print(f"Current Pressure: {pressure_command}")
            # if selected_detection:
                # pprint.pprint(selected_detection)
        
            
            # Store results
            self.detection_results = {
                'all_detections': detections,
                'selected_detection': selected_detection,
                'pressure_command': pressure_command,
                'timestamp': current_time
            }
            
            # if self.config["video"]["show_debug_windows"]:
                # debug_images = {
                    # 'gray': gray,
                    # 'canny': edges_original,
                    # 'canny': edges,
                    # 'threshold': thresh_binary,
                    # 'combined': thresh_combined,
                    # 'final': thresh_final,
                    # 'walls': wall_mask
                # }
            # cv2.imshow('final', debug_images['final'])
            
            
            self.target_pressure = pressure_command
            return pressure_command
            
        except Exception as e:
            if self.config["logging"]["verbose"]:
                print(f"Error processing frame: {e}")
            return 0
    

    
    def calculate_line_crossing_velocity(self, track_info):
        """Calculate velocity based on line crossings"""
        line_crossings = track_info.get('line_crossings', [])
        
        if len(line_crossings) < 2:
            return None
        
        # Sort by timestamp
        sorted_crossings = sorted(line_crossings, key=lambda x: x['timestamp'])
        
        # Use first and last crossing
        first = sorted_crossings[0]
        last = sorted_crossings[-1]
        
        # Calculate velocity
        distance = abs(last['line_y'] - first['line_y'])
        time_diff = last['timestamp'] - first['timestamp']
        
        if time_diff <= 0:
            return None
        
        velocity = distance / time_diff
        
        # Apply direction (positive = downward, negative = upward)
        if last['line_y'] > first['line_y']:
            velocity = velocity  # Moving down (positive)
        else:
            velocity = -velocity  # Moving up (negative)
        
        return velocity
    
 
    def detect_contours(self, frame):
        """Detect objects using contour detection"""
        try:
            '''
                # old code 09/01/2025 5:55pm            
                # Convert to grayscale
                
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Apply blur
                blur_kernel = self.config["detection"]["blur_kernel"]
                if blur_kernel > 1:
                    gray = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)
                
                # Apply adaptive threshold
                thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                             cv2.THRESH_BINARY, 5, 2)
                                             
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                # end of old code 09/01/2025 5:55pm
                
            ''' 
            blur_kernel = self.config["detection"]["blur_kernel"]
            threshold_value = self.config["detection"]["threshold_value"]
            canny_low = self.config["detection"]["canny_low"]
            canny_high = self.config["detection"]["canny_high"]
            combination_mode = self.config["detection"]["combination_mode"]
    
            use_hough = self.config["wall_detection"]["use_hough_lines"]
            hough_threshold = self.config["wall_detection"]["hough_threshold"]
            min_line_length = self.config["wall_detection"]["min_line_length"]
            max_line_gap = self.config["wall_detection"]["max_line_gap"]
            wall_mask_width = self.config["wall_detection"]["wall_mask_width"]
            
            morph_kernel_size = self.config["morphology"]["kernel_size"]
            morph_kernel_shape = self.config["morphology"]["kernel_shape"]
            close_iterations = self.config["morphology"]["close_iterations"]
            open_iterations = self.config["morphology"]["open_iterations"]
    
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Apply blur
            blur_kernel = self.config["detection"]["blur_kernel"]
            if blur_kernel >= 1:
                blurred = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)
            
            # Step 1: Get Canny edges
            edges = cv2.Canny(blurred, canny_low, canny_high)
            edges_original = edges.copy()  # Keep original for visualization
            
            
            # Step 2: Get binary threshold image
            _, thresh_binary = cv2.threshold(blurred, threshold_value, 255, cv2.THRESH_BINARY_INV)
            thresh_original = thresh_binary.copy()  # Keep original for visualization
            
            # Step 3: Create masks (ROI and wall detection)
            h, w = gray.shape
            # Detect and mask walls using Hough transform
            wall_mask = None
            detected_lines = []
            wall_angles = []
            
            line1_x = self.config["vertical_lines"]["line1_x"]
            line2_x = self.config["vertical_lines"]["line2_x"]
            poly_w = self.config["vertical_lines"]["poly_width"]
            c_line_y = self.config["horizontal_lines"]["c_line_y"]
            
            xtl = self.config["taper_lines"]["xtl"]
            xtr = self.config["taper_lines"]["xtr"]
            xbl = self.config["taper_lines"]["xbl"]
            xbr = self.config["taper_lines"]["xbr"]
        
            xtr = w + xtr
            xbr = w + xbr
            if use_hough:
                lines = cv2.HoughLinesP(edges, 1, np.pi/180, hough_threshold, 
                                       minLineLength=min_line_length, 
                                       maxLineGap=max_line_gap)
                
                if lines is not None:
                    wall_mask = np.ones((h, w), dtype=np.uint8) * 255
                    
                    for line in lines:
                        x1, y1, x2, y2 = line[0]
                        # ~ length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
                        if x1 > line2_x or x2 > line2_x:
                            pts = np.array([[x1,y1],[w,y1],[w,y2],[x2,y2]], np.int32)
                            pts = pts.reshape((-1,1,2))
                            cv2.fillPoly(wall_mask, [pts], True, 0)
                            
                        if x1 < line1_x or x2 < line1_x:
                            pts = np.array([[x1,y1],[0,y1],[0,y2],[x2,y2]], np.int32)
                            pts = pts.reshape((-1,1,2))
                            cv2.fillPoly(wall_mask, [pts], True, 0)
                    
                    pts = np.array([[0,c_line_y-poly_w],[line1_x, c_line_y-poly_w], [line1_x,c_line_y+poly_w], [0,c_line_y+poly_w]],np.int32)
                    pts = pts.reshape((-1,1,2))
                    cv2.fillPoly(wall_mask, [pts], True, 0)
                    
                    pts = np.array([[line2_x,c_line_y-poly_w],[w, c_line_y-poly_w], [w,c_line_y+poly_w], [line2_x,c_line_y+poly_w]],np.int32)
                    pts = pts.reshape((-1,1,2))
                    cv2.fillPoly(wall_mask, [pts], True, 0)
                    
                    # top left taper polygon
                    pts = np.array([[0,c_line_y+poly_w],[line1_x, c_line_y+poly_w], [xtl,0], [0,0]],np.int32)
                    pts = pts.reshape((-1,1,2))
                    cv2.fillPoly(wall_mask, [pts], True, 0)
                    
                    # bottom left taper polygon
                    pts = np.array([[0,c_line_y-poly_w],[line1_x, c_line_y-poly_w], [xbl,h], [0,h]],np.int32)
                    pts = pts.reshape((-1,1,2))
                    cv2.fillPoly(wall_mask, [pts], True, 0)
                    
                    # top right taper polygon
                    pts = np.array([[w,c_line_y+poly_w],[line2_x, c_line_y+poly_w], [xtr,0], [w,0]],np.int32)
                    pts = pts.reshape((-1,1,2))
                    cv2.fillPoly(wall_mask, [pts], True, 0)
                    
                    # bottom right taper polygon
                    pts = np.array([[w,c_line_y-poly_w],[line2_x, c_line_y-poly_w], [xbr,h], [w,h]],np.int32)
                    pts = pts.reshape((-1,1,2))
                    cv2.fillPoly(wall_mask, [pts], True, 0)
                    
            edges = cv2.subtract(edges, self.background_frame["edge_frame"])
            thresh_binary = cv2.subtract(thresh_binary, self.background_frame["threshold_frame"])
            
            # Step 4: Apply masks to both images        
            if use_hough and wall_mask is not None:
                edges = cv2.bitwise_and(edges, wall_mask)
                thresh_binary = cv2.bitwise_and(thresh_binary, wall_mask)
    
            
            # Step 5: Combine edge and threshold information based on mode
            if combination_mode == "intersection":
                # Only keep pixels that are both edges AND in threshold
                thresh_combined = cv2.bitwise_and(thresh_binary, edges)
            elif combination_mode == "union":
                # Keep pixels that are either edges OR in threshold
                thresh_combined = cv2.bitwise_or(thresh_binary, edges)
            elif combination_mode == "weighted":
                # Weighted combination
                t_weight = self.config["detection"]["combination_weights"]["threshold_weight"]
                c_weight = self.config["detection"]["combination_weights"]["canny_weight"]
                thresh_combined = cv2.addWeighted(thresh_binary, t_weight, edges, c_weight, 0)
                _, thresh_combined = cv2.threshold(thresh_combined, 127, 255, cv2.THRESH_BINARY)
            else:
                thresh_combined = cv2.bitwise_and(thresh_binary, edges)  # Default to intersection
    
    
            # Step 6: Morphological operations to clean up
            if morph_kernel_shape == "ellipse":
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_kernel_size, morph_kernel_size))
            elif morph_kernel_shape == "rect":
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (morph_kernel_size, morph_kernel_size))
            else:
                kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (morph_kernel_size, morph_kernel_size))
            
            thresh_final = cv2.morphologyEx(thresh_combined, cv2.MORPH_CLOSE, kernel, iterations=close_iterations)
            thresh_final = cv2.morphologyEx(thresh_final, cv2.MORPH_OPEN, kernel, iterations=open_iterations)
            
    
            
            # Find contours
            contours, _ = cv2.findContours(thresh_final, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
            detections = []
            min_area = self.config["detection"]["min_contour_area"]
            max_area = self.config["detection"]["max_contour_area"]
            aspect_ratio = self.config["detection"]["aspect_ratio"]
            
            # Prepare debug images
            debug_images = None
            if self.config["video"]["show_debug_windows"]:
                debug_images = {
                    'gray': gray,
                    #'canny': edges_original,
                    'canny': edges,
                    'threshold': thresh_binary,
                    'combined': thresh_combined,
                    'final': thresh_final,
                    'walls': wall_mask
                }
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if min_area <= area <= max_area:
                # if min_area <= area:
                    x, y, w, h = cv2.boundingRect(contour)
                    # ar = x/y
                    ar = 2*(w+h)/ (2*np.pi*max(w,h))
                    # ar = 1
                    # if 0.5 <= ar <= 0.637:
                    detection = {
                        'bbox': [x, y, x + w, y + h],
                        'area': area,
                        'center': [x + w/2, y + h/2],
                        'contour': contour,
                        'width': w,
                        'height': h,
                        'distance_to_c_line': abs((y + h/2) - self.config['horizontal_lines']['c_line_y']),
                        'velocity': None,  # Will be filled in later by velocity tracking
                        'timestamp': time.time(),
                        'direction': None
                    }
                    detections.append(detection)
            
            return detections, debug_images
            
        except Exception as e:
            if self.config["logging"]["verbose"]:
                print(f"Contour detection error: {e}")
            return [], None
    
    def find_smallest_near_c_line(self, detections):
        """Find the object closest to the C line"""
        # Return object closest to C line
        if detections:
            closest_detection = min(detections, key=lambda d: d['distance_to_c_line'])
        else:
            closest_detection = []

        return closest_detection
    
    def find_smallest_near_y(self, detections, y):
        """Find the object closest to the C line"""
        # Return object closest to C line
        # abs((y + h/2) - self.config['horizontal_lines']['c_line_y']
        
        min_distance = float('inf')
        if detections:
            for track in detections:
                center_y = track["center"][1]
                distance = abs(center_y - y)
                if distance < min_distance:
                    closest_detection = track
        else:
            closest_detection = []
        # closest_detection = min(detections, key=lambda d: d['distance_to_c_line'])
        

        return closest_detection
    
    def get_horizontal_line_positions(self, frame_height):
        """Get Y positions of all horizontal lines"""
        c_line_y = self.config['horizontal_lines']['c_line_y']
        gap_l = self.config['horizontal_lines']['gap_l']
        
        lines = [c_line_y]  # Start with C line
        
        # Lines above C line
        y = c_line_y - gap_l
        while y >= 0:
            lines.append(y)
            y -= gap_l
        
        # Lines below C line
        y = c_line_y + gap_l
        while y < frame_height:
            lines.append(y)
            y += gap_l
        
        return sorted(lines)
    
    
    def record_line_crossing(self, object_id, line_y, timestamp, x, y):
        """Record when an object crosses a horizontal line"""
        if object_id not in self.line_crossings:
            self.line_crossings[object_id] = []
        
        # Check if this is a new crossing (not too close to previous ones)
        crossings = self.line_crossings[object_id]
        for crossing in crossings:
            if abs(crossing['line_y'] - line_y) < 10 and abs(crossing['timestamp'] - timestamp) < 0.2:
                return  # Too close to existing crossing, ignore
        
        # Record new crossing
        crossing_data = {
            'line_y': line_y,
            'timestamp': timestamp,
            'x': x,
            'y': y
        }
        crossings.append(crossing_data)
        
        # Keep only recent crossings
        self.line_crossings[object_id] = [c for c in crossings if timestamp - c['timestamp'] < 2.0]
    
    # def calculate_object_velocity(self, object_id, current_time):
    def calculate_object_velocity(self):
        if len(self.tracking_vars["centers"]) >= self.config["tracking_config"]["acquiring_frames"]:
            # Get the window of frames
            frames_to_use = self.config["tracking_config"]["acquiring_frames"]
            
            # Calculate velocity between each consecutive pair
            velocities = []
            for i in range(-frames_to_use, -1):  # -frames_to_use to -2
                y1 = self.tracking_vars["centers"][i][1]
                y2 = self.tracking_vars["centers"][i+1][1]
                t1 = self.tracking_vars["time_stamps"][i]
                t2 = self.tracking_vars["time_stamps"][i+1]
                
                if t2 != t1:  # Avoid division by zero
                    v = (y2 - y1) / (t2 - t1)
                    velocities.append(v)
            
            # Average the velocities
            if velocities:
                avg_velocity = sum(velocities) / len(velocities)
                self.tracking_vars["velocities"].append(avg_velocity)
                
    def calculate_object_velocity_old(self):
        if len(self.tracking_vars["centers"]) >= self.config["tracking_config"]["acquiring_frames"]:
            y2 = self.tracking_vars["centers"][-1][1]
            # print(f"calculate velocity, y2: {y2}")
            y1 = self.tracking_vars["centers"][-1*self.config["tracking_config"]["acquiring_frames"]][1]
            # print(f"calculate velocity, y1: {y1}")
            t2 = self.tracking_vars["time_stamps"][-1]
            # print(f"calculate velocity, t2: {t2}")
            t1 = self.tracking_vars["time_stamps"][-1*self.config["tracking_config"]["acquiring_frames"]]
            # print(f"calculate velocity, t1: {t1}")
            
            v = (y2-y1)/(t2-t1)
            # print(f"calculated velocity: {v}")
            self.tracking_vars["velocities"].append(v)
            
        # """Calculate velocity based on line crossings"""
        # if object_id not in self.line_crossings:
            # return None
        
        # crossings = self.line_crossings[object_id]
        # min_crossings = self.config["velocity_tracking"]["min_line_crossings"]
        
        # if len(crossings) < min_crossings:
            # return None
        
        # # Sort crossings by time
        # crossings = sorted(crossings, key=lambda c: c['timestamp'])
        
        # # Calculate velocity using first and last crossing
        # first_crossing = crossings[0]
        # last_crossing = crossings[-1]
        
        # # Calculate distance and time
        # distance_pixels = abs(last_crossing['line_y'] - first_crossing['line_y'])
        # time_diff = last_crossing['timestamp'] - first_crossing['timestamp']
        
        # if time_diff <= 0:
            # return None
        
        # # Velocity in pixels per second
        # velocity_pps = distance_pixels / time_diff
        
        # # Apply smoothing
        # smoothing = self.config["velocity_tracking"]["velocity_smoothing"]
        # if object_id in self.current_velocities:
            # old_velocity = self.current_velocities[object_id]
            # velocity_pps = old_velocity * smoothing + velocity_pps * (1 - smoothing)
        
        # return velocity_pps
    def log_track_vars(self,log):
        '''
        log = {
            'timestamp': current_time,
            'velocity_m': vm,
            'velocity_t': vt,
            'pressure_out': pressure_command,
            'error': e,
            'correction': correction,
            'proportional_correction': proportional_correction,
            'integral_correction': integral_correction,
            'differential_correction': differential_correction
            }
        '''
        # print('logging')
        with open('data.csv', 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            # writer.writerow(['time_stamp', 'center', 'v'])
            csvfile.seek(0, 2) 
            data_row = list(log.values())
            writer.writerow(data_row)
            csvfile.flush()
        
    def get_object_velocity(self, center_x, center_y):
        """Get velocity for object at given position"""
        position_tolerance = self.config["velocity_tracking"]["position_tolerance"]
        
        # Find closest tracked object
        for object_id, velocity in self.current_velocities.items():
            # Parse object_id to get approximate position
            try:
                id_x, id_y = map(float, object_id.split('_'))
                if (abs(center_x - id_x) < position_tolerance and 
                    abs(center_y - id_y) < position_tolerance):
                    return velocity
            except:
                continue
        
        return None
    
    
    def calculate_pressure_command(self, selected_detection, current_pressure):
        """Calculate pressure command using position-based control"""
        
        if not selected_detection:
            return current_pressure
        # print('no issues')
        # print("checkpoint: 1")
        current_time = time.time()
        elapsed_time = current_time - self.time_to_last_check_point
        self.time_to_last_check_point = current_time
        # print(f"Cell location: {selected_detection['center'][1]}")
        kp = self.config["tracking_config"]["proportional_kp"]
        ki = self.config["tracking_config"]["integral_ki"]
        kd = self.config["tracking_config"]["differential_kd"]
        vt = self.config["tracking_config"]["target_velocity"] # velocity target
        
        kp_fwd = self.config["tracking_config"]["kp_fwd"]
        kp_rev = self.config["tracking_config"]["kp_rev"]
        control_symmetry = self.config["tracking_config"]["symmetrical"]
        
        initial_offset = 0
        # print("check1")
        # pprint.pprint(self.tracking_vars)
        if self.tracking_vars["velocities"]:
            # print(f"velocity now: {self.tracking_vars['velocities']}")
            try:
                vm = self.tracking_vars["velocities"][-1] # measured velocity          
            except:
                return current_pressure
                    
        else:
            # print("velocity now: self.tracking_vars["velocities"][-1]")
            # print("checkpoint: 2")
            return current_pressure
        # print("checkpoint: 3")
        if selected_detection["center"][1] < self.line_top:
            if self.cell_direction == -1:
                self.prev_error = 0
                self.integral = 0
            self.cell_direction = 1
            # current_pressure = self.pressure_from_top if current_pressure == 0 else current_pressure
            initial_offset = self.pressure_from_top - current_pressure
        elif selected_detection["center"][1] > self.line_bottom:
            if self.cell_direction == 1:
                self.prev_error = 0
                self.integral = 0
            self.cell_direction = -1
            # current_pressure = self.pressure_from_bottom if current_pressure == 0 else current_pressure
            initial_offset = self.pressure_from_bottom - current_pressure
        
        
        vt = vt * self.cell_direction        
        e = vt-vm
        self.integral += e*elapsed_time
        
        ei = self.integral
        
        ed = (e - self.prev_error)/elapsed_time
        
        
        self.prev_error = e
        integral_correction = ei * ki
        differential_correction = ed * kd
        
        # print(f"control_symmetry: {control_symmetry}")
        if control_symmetry:
            proportional_correction = e * kp
            
        else:
            
            if vt >0:
                proportional_correction = e * kp_fwd
                # integral_correction = ei * ki
            else:
                proportional_correction = e * kp_rev
        
        # print("no issues here")
        pid_correction = proportional_correction + integral_correction + differential_correction 
        use_PID = self.config["tracking_config"]["use_PID"]
        # pressure_command = current_pressure + initial_offset + proportional_correction + integral_correction   
        if use_PID:
            correction = pid_correction 
            # print(f"current pressure: {current_pressure}, correction: {pid_correction}")
        else:
            correction = proportional_correction
            
        
        pressure_command = current_pressure + correction          
        # print('creating log variable')
        print(f"current pressure: {current_pressure}, correction: {correction}")
        
        
        if self.config["tracking_config"]["log_in_file"]:
            
            log = {
                'timestamp': current_time,
                'velocity_m': vm,
                'velocity_t': vt,
                'pressure_out': pressure_command,
                'error': e,
                'correction': correction,
                'proportional_correction': proportional_correction,
                'integral_correction': integral_correction,
                'differential_correction': differential_correction
                }
            self.log_track_vars(log)
            
        return pressure_command
            
    def position_based_control(self, detection, current_pressure):
        """Control pump based on object position and velocity relative to target zone"""
        config = self.config["position_control"]
        c_line_y = self.config['horizontal_lines']['c_line_y']
        gap_l = self.config['horizontal_lines']['gap_l']
        target_zone_lines = config["target_zone_lines"]
        control_gain = config["control_gain"]
        
        # Define target zone boundaries
        upper_boundary = c_line_y - (gap_l * target_zone_lines)  # First blue line above C
        lower_boundary = c_line_y + (gap_l * target_zone_lines)  # First blue line below C
        
        # Get object position and velocity
        object_y = detection['center'][1]
        object_velocity = detection.get('velocity', 0) or 0  # Current velocity (px/s)
        
        # Position-based pressure calculation
        position_pressure = 0
        if object_y < upper_boundary:
            # Object is above target zone - need to push down (increase pressure)
            position_error = upper_boundary - object_y
            position_pressure = position_error * control_gain
        elif object_y > lower_boundary:
            # Object is below target zone - need to pull up (decrease pressure)
            position_error = object_y - lower_boundary
            position_pressure = -position_error * control_gain
        
        # Velocity-based pressure calculation (if enabled)
        velocity_pressure = 0
        if config.get("velocity_control", False):
            target_velocity = config["target_velocity"]  # 40 px/s
            velocity_tolerance = config.get("velocity_tolerance", 5.0)
            velocity_gain = config.get("velocity_gain", 0.3)
            
            # Calculate velocity error
            velocity_error = abs(object_velocity) - target_velocity
            
            # Only apply velocity correction if outside tolerance
            if abs(velocity_error) > velocity_tolerance:
                if object_velocity > 0:  # Moving down (positive Y direction)
                    if velocity_error > 0:  # Too fast
                        velocity_pressure = -velocity_error * velocity_gain  # Reduce pressure
                    else:  # Too slow
                        velocity_pressure = abs(velocity_error) * velocity_gain  # Increase pressure
                elif object_velocity < 0:  # Moving up (negative Y direction) 
                    if velocity_error > 0:  # Too fast up
                        velocity_pressure = velocity_error * velocity_gain  # Increase pressure (slow upward)
                    else:  # Too slow up
                        velocity_pressure = -abs(velocity_error) * velocity_gain  # Reduce pressure (speed up upward)
        
        # Combine position and velocity control
        target_pressure = position_pressure + velocity_pressure
        
        # Apply pressure limits
        pressure_limits = self.config["pump_control"]["pressure_limits"]
        target_pressure = np.clip(target_pressure, *pressure_limits)
        
        # Add base pressure
        target_pressure += self.config["pump_control"]["base_pressure"]
        
        # Smooth transition
        return self.smooth_pressure_change(current_pressure, target_pressure)
    
 
    def smooth_pressure_change(self, current_pressure, target_pressure):
        """Apply smoothing to pressure changes"""
        max_change = self.config["pump_control"]["max_pressure_change"]
        smoothing = self.config["pump_control"]["smoothing_factor"]
        deadband = self.config["pump_control"]["deadband"]
        
        # Calculate pressure difference
        pressure_diff = target_pressure - current_pressure
        
        # Apply deadband
        if abs(pressure_diff) < deadband:
            return current_pressure
        
        # Limit maximum change
        if abs(pressure_diff) > max_change:
            pressure_diff = np.sign(pressure_diff) * max_change
        
        # Apply smoothing
        smooth_pressure = current_pressure + (pressure_diff * smoothing)
        
        # Apply limits
        return np.clip(smooth_pressure, *self.pressure_limits)
    
    def add_visualization(self, frame, pump_data=None):
        """Add detection and pressure visualization to frame"""
        annotated_frame = frame.copy()
        
        # Draw horizontal lines if verbose mode is on
        if (self.config["visualization"]["verbose_mode"] and 
            self.config["horizontal_lines"]["show_lines"]):
            self.draw_horizontal_lines(annotated_frame)
            self.draw_vertical_lines(annotated_frame)
        
        # Draw detections if available and AI is enabled
        if (self.config["visualization"]["show_detections"] and 
            self.detection_results):  # â† Added self.enabled condition
            self.draw_detections(annotated_frame)
        
        # Add pressure overlay
        if self.config["visualization"]["show_pressure_overlay"] and pump_data:
            self.draw_pressure_overlay(annotated_frame, pump_data)
        
        return annotated_frame
    
    def draw_horizontal_lines(self, frame):
        """Draw horizontal reference lines with target zone highlighted"""
        config = self.config["horizontal_lines"]
        c_line_y = config["c_line_y"]
        gap_l = config["gap_l"]
        line_color = tuple(config["line_color"])
        c_line_color = tuple(config["c_line_color"])
        thickness = config["line_thickness"]
        
        top_bound = self.config["horizontal_lines"]["c_line_y"] - self.config["tracking_config"]["search_range"]
        bottom_bound = self.config["horizontal_lines"]["c_line_y"] + self.config["tracking_config"]["search_range"]
        
        frame_height, frame_width = frame.shape[:2]
        
        # Calculate target zone boundaries
        target_zone_lines = self.config["position_control"]["target_zone_lines"]
        upper_boundary = c_line_y - (gap_l * target_zone_lines)
        lower_boundary = c_line_y + (gap_l * target_zone_lines)
        
        # Draw C line (center line) in different color
        cv2.line(frame, (0, c_line_y), (frame_width, c_line_y), c_line_color, thickness + 1)
        cv2.putText(frame, "C", (frame_width - 20, c_line_y - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, c_line_color, 1)
                   
        cv2.line(frame, (0, top_bound), (frame_width, top_bound), c_line_color, thickness + 1)
        cv2.putText(frame, f"{top_bound}", (frame_width - 40, top_bound - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, c_line_color, 1)
        
        cv2.line(frame, (0, bottom_bound), (frame_width, bottom_bound), c_line_color, thickness + 1)
        cv2.putText(frame, f"{bottom_bound}", (frame_width - 40, bottom_bound - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, c_line_color, 1)
        
        occlusion_zone_top = c_line_y - self.config["tracking_config"]["occlusion_zone_extent"]
        occlusion_zone_bottom = c_line_y + self.config["tracking_config"]["occlusion_zone_extent"]
        
        cv2.line(frame, (0, occlusion_zone_top), (frame_width, occlusion_zone_top), c_line_color, thickness + 1)
        cv2.line(frame, (0, occlusion_zone_bottom), (frame_width, occlusion_zone_bottom), c_line_color, thickness + 1)
        
        # Draw lines above C line
        y = c_line_y - gap_l
        line_num = 1
        while y >= 0:
            # Highlight target zone boundaries
            if y == upper_boundary:
                cv2.line(frame, (0, y), (frame_width, y), (0, 255, 255), thickness + 1)  # Yellow
                cv2.putText(frame, "TARGET", (5, y - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            else:
                cv2.line(frame, (0, y), (frame_width, y), line_color, thickness)
            y -= gap_l
            line_num += 1
        
        # Draw lines below C line
        y = c_line_y + gap_l
        line_num = 1
        while y < frame_height:
            # Highlight target zone boundaries
            if y == lower_boundary:
                cv2.line(frame, (0, y), (frame_width, y), (0, 255, 255), thickness + 1)  # Yellow
                cv2.putText(frame, "TARGET", (5, y + 15), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            else:
                cv2.line(frame, (0, y), (frame_width, y), line_color, thickness)
            y += gap_l
            line_num += 1
        
        # Draw target zone background (optional)
        if self.config["position_control"]["enabled"]:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, int(upper_boundary)), (frame_width, int(lower_boundary)), 
                         (0, 255, 0), -1)  # Green target zone
            cv2.addWeighted(frame, 0.9, overlay, 0.1, 0, frame)
            
    def draw_vertical_lines(self, frame):
        """ Draw vertical reference lines"""
        config = self.config["vertical_lines"]
        line_color = tuple(config["line_color"])
        thickness = config["line_thickness"]
        
        frame_height, frame_width = frame.shape[:2]
        line1_x = config["line1_x"]
        line2_x = config["line2_x"]
        c_line_y = self.config["horizontal_lines"]["c_line_y"]
        poly_w = config["poly_width"]
        cv2.line(frame, (line1_x, c_line_y-poly_w), (line1_x, c_line_y+poly_w), line_color, thickness + 1)
        cv2.line(frame, (line2_x, c_line_y-poly_w), (line2_x, c_line_y+poly_w), line_color, thickness + 1)
        
        
        # draw taper lines
        
        xtl = self.config["taper_lines"]["xtl"]
        xtr = self.config["taper_lines"]["xtr"]
        xbl = self.config["taper_lines"]["xbl"]
        xbr = self.config["taper_lines"]["xbr"]
        
        xtr = frame_width + xtr
        xbr = frame_width + xbr
        # bottom left taper
        cv2.line(frame, (line1_x, c_line_y+poly_w), (xbl, frame_height), line_color, thickness + 1)
        
        # bottom right taper
        cv2.line(frame, (line2_x, c_line_y+poly_w), (xbr, frame_height), line_color, thickness + 1)
        
        # top left taper
        cv2.line(frame, (line1_x, c_line_y-poly_w), (xtl, 0), line_color, thickness + 1)
        
        # top right taper
        cv2.line(frame, (line2_x, c_line_y-poly_w), (xtr, 0), line_color, thickness + 1)
        
        label = f"Pressure_Calc:{self.target_pressure:.1f}"
        cv2.putText(frame, label, (15, 125), 
                           cv2.FONT_HERSHEY_SIMPLEX, .4, (0,0,0), 1)
        
    def draw_detections(self, frame):
        """Draw detection boxes and information"""
        if not self.detection_results:
            return
        
        all_detections = self.detection_results.get('all_detections', [])
        selected_detection = self.detection_results.get('selected_detection')
        
        detection_color = tuple(self.config["visualization"]["detection_color"])
        selected_color = tuple(self.config["visualization"]["selected_object_color"])
        text_color = tuple(self.config["visualization"]["text_color"])
        
        detection_method = self.config["detection"]["method"]
        
        # Draw all detections
        for detection in all_detections:

            # Original contour detection visualization
            bbox = detection['bbox']
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), detection_color, 1)
            
            # Add size, distance, and velocity info with target velocity comparison
            width = detection.get('width', 0)
            height = detection.get('height', 0)
            distance = detection.get('distance_to_c_line', 0)
            velocity = detection.get('velocity', None)
            
            if velocity is not None:
                target_velocity = self.config["position_control"]["target_velocity"]
                velocity_status = "OK" if abs(abs(velocity) - target_velocity) <= 5 else "ERR"
                label = f"W:{width} H:{height} V:{velocity:.0f}({velocity_status})"
            else:
                label = f"W:{width} H:{height} D:{distance:.0f}"
            cv2.putText(frame, label, (bbox[0], bbox[1] - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.3, text_color, 1)
    
        # Draw selected detection with thicker border
        if selected_detection:

            # Original contour detection visualization for selected object
            bbox = selected_detection['bbox']
            # Ensure bbox coordinates are integers before drawing
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            cv2.rectangle(frame, (x1, y1), (x2, y2), selected_color, 1)
            # cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), selected_color, 3)
            
            # Add selected object info with velocity control status
            area = selected_detection['area']
            width = selected_detection.get('width', 0)
            height = selected_detection.get('height', 0)
            velocity = selected_detection.get('velocity', None)
            
            if velocity is not None:
                target_velocity = self.config["position_control"]["target_velocity"]
                velocity_error = abs(abs(velocity) - target_velocity)
                status = "TARGET" if velocity_error <= 5 else f"Â±{velocity_error:.0f}"
                label = f"SELECTED: V:{velocity:.0f}â†'{target_velocity:.0f}({status})"
            else:
                # label = f"SELECTED: A:{int(area)} W:{width} H:{height}"
                label = f"SELECTED: A:{int(area)} W:{width} H:{height}"
            cv2.putText(frame, label, (x1, y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, selected_color, 1)
    
    
    def enable(self):
        """Enable AI vision control"""
        self.enabled = True
        if self.config["logging"]["verbose"]:
            print("AI Vision Controller ENABLED")
    
    def disable(self):
        """Disable AI vision control"""
        self.enabled = False
        if self.config["logging"]["verbose"]:
            print("AI Vision Controller DISABLED")
    
    def toggle(self):
        """Toggle AI vision control"""
        if self.enabled:
            self.disable()
        else:
            self.enable()
        return self.enabled
    
    def get_status(self):
        """Get current status and results"""
        return {
            'enabled': self.enabled,
            'target_pressure': self.target_pressure,
            'last_detection': self.detection_results,
            'detection_count': len(self.detection_results.get('all_detections', [])) if self.detection_results else 0,
            'selected_object': self.detection_results.get('selected_detection') is not None if self.detection_results else False
        }
    
    def cleanup(self):
        """Clean up resources"""
        self.enabled = False
        
        # Close velocity plot
        if self.plot_enabled and hasattr(self, 'fig') and self.fig is not None:
            try:
                plt.close(self.fig)
            except:
                pass
        
        if self.config["logging"]["verbose"]:
            print("AI Vision Controller cleaned up")
            
    def match_detection_to_tracked(self, detection, tracked_detections):
        """Match a raw detection to its corresponding tracked object"""
        if not tracked_detections:
            return None
        
        detection_center = detection['center']
        max_distance = 30  # Maximum distance to consider a match (pixels)
        
        best_match = None
        min_distance = float('inf')
        
        for tracked_detection in tracked_detections:
            tracked_center = tracked_detection['center']
            
            # Calculate distance between detection and tracked object
            distance = math.sqrt(
                (detection_center[0] - tracked_center[0])**2 + 
                (detection_center[1] - tracked_center[1])**2
            )
            
            # Check if this is the closest match within range
            if distance < max_distance and distance < min_distance:
                min_distance = distance
                best_match = tracked_detection
        
        if best_match and self.config["logging"]["verbose"]:
            print(f"Matched detection at {detection_center} to tracked object at {best_match['center']} "
                  f"(distance: {min_distance:.1f}px, velocity: {best_match.get('velocity', 'None')})")
        
        return best_match

# Factory function
def create_ai_vision_controller(config_file="ai_vision_config.json"):
    """Factory function to create AI vision controller"""
    controller = AIVisionController(config_file)
    if controller.initialize():
        return controller
    else:
        return None
        