import cv2
import datetime
import os
import json
import numpy as np
import time

class CameraROI:
    def __init__(self, config_file="config.json"):
        self.config = self.load_config(config_file)
        self.cap = None
        self.out = None
        self.recording = False
        self.fps = 30
        self.window_name = 'Webcam ROI'
        self.fps_counter = 0
        self.fps_timer = cv2.getTickCount()
        self.frame_count = 0
        
        # Recording state management (simplified - no timers)
        self.last_successful_codec = None
        self.recording_start_time = None
        
    def load_config(self, config_file="config.json"):
        """Load configuration from JSON file"""
        default_config = {
            "roi": {
                "x": 800,
                "y": 0,
                "width": 170,
                "height": 1104,
                "enabled": True
            },
            "camera": {
                "width": 1608,
                "height": 1104,
                "fps": "max",
                "index": 0
            },
            "recording": {
                "codec": "mp4v",
                "filename_prefix": "recording",
                "retry_codecs": ["mp4v", "XVID", "MJPG", "X264"],
                "cleanup_delay": 0.15
            },
            "display": {
                "center_content": True,
                "scale_factor": 0.85,
                "background_color": [0, 0, 0]
            }
        }
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                print(f"Loaded configuration from {config_file}")
            else:
                config = default_config
                # Create default config file
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
                print(f"Created default configuration file: {config_file}")
            
            return config
        except Exception as e:
            print(f"Error loading config: {e}")
            print("Using default configuration")
            return default_config
    
    def find_max_fps(self, cap):
        """Find the maximum FPS supported by the camera"""
        print("Testing maximum FPS...")
        
        # Common FPS values to test (in descending order)
        fps_values_to_test = [240, 120, 96, 60, 50, 30, 25, 20, 15, 10]
        
        max_fps = 30  # Default fallback
        
        for test_fps in fps_values_to_test:
            cap.set(cv2.CAP_PROP_FPS, test_fps)
            actual_fps = cap.get(cv2.CAP_PROP_FPS)
            
            # Test if we can actually achieve this FPS by reading a few frames
            frame_times = []
            for i in range(5):  # Test with 5 frames
                start_time = cv2.getTickCount()
                ret, frame = cap.read()
                if not ret:
                    break
                end_time = cv2.getTickCount()
                frame_time = (end_time - start_time) / cv2.getTickFrequency()
                frame_times.append(frame_time)
            
            if frame_times:
                avg_frame_time = sum(frame_times) / len(frame_times)
                measured_fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
                
                print(f"Testing FPS {test_fps}: Set={actual_fps:.1f}, Measured={measured_fps:.1f}")
                
                # If measured FPS is close to what we set (within 20% tolerance)
                if measured_fps >= test_fps * 0.8:
                    max_fps = test_fps
                    print(f"Maximum achievable FPS: {max_fps}")
                    break
        
        # Set the maximum FPS we found
        cap.set(cv2.CAP_PROP_FPS, max_fps)
        return max_fps

    def apply_roi(self, frame, roi_config):
        """Apply Region of Interest to frame"""
        if not roi_config.get("enabled", True):
            return frame
        
        x = roi_config.get("x", 0)
        y = roi_config.get("y", 0)
        width = roi_config.get("width", frame.shape[1])
        height = roi_config.get("height", frame.shape[0])
        
        # Ensure ROI is within frame bounds
        frame_height, frame_width = frame.shape[:2]
        x = max(0, min(x, frame_width))
        y = max(0, min(y, frame_height))
        width = min(width, frame_width - x)
        height = min(height, frame_height - y)
        
        if width <= 0 or height <= 0:
            print("Warning: Invalid ROI dimensions, using full frame")
            return frame
        
        return frame[y:y+height, x:x+width]
    
    def center_roi_content(self, roi_frame):
        """Center and scale the ROI content in a larger canvas"""
        display_config = self.config.get("display", {})
        
        if not display_config.get("center_content", True):
            return roi_frame
        
        # Get ROI dimensions
        roi_height, roi_width = roi_frame.shape[:2]
        
        # Scale factor
        scale_factor = display_config.get("scale_factor", 0.92)
        
        # Calculate new dimensions
        new_width = int(roi_width * scale_factor)
        new_height = int(roi_height * scale_factor)
        
        # Resize the ROI frame
        scaled_roi = cv2.resize(roi_frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        
        # Create canvas (use original dimensions plus some padding)
        canvas_width = roi_width + 100
        canvas_height = roi_height + 0
        
        # Create black canvas
        bg_color = display_config.get("background_color", [0, 0, 0])
        
        if len(roi_frame.shape) == 3:  # Color image
            canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
            canvas[:] = bg_color
        else:  # Grayscale
            canvas = np.zeros((canvas_height, canvas_width), dtype=np.uint8)
            canvas[:] = bg_color[0] if isinstance(bg_color, list) else bg_color
        
        # Calculate center position for the scaled frame
        start_x = (canvas_width - new_width) // 2
        start_y = (canvas_height - new_height) // 2 - 40
        
        # Place scaled ROI content in center
        canvas[start_y:start_y + new_height, start_x:start_x + new_width] = scaled_roi
        
        return canvas
    
    def initialize_camera(self):
        """Initialize camera connection"""
        # Try different backends and camera indices
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        
        print("Attempting to connect to camera...")
        
        # Try different backends
        for backend in backends:
            try:
                self.cap = cv2.VideoCapture(self.config["camera"]["index"], backend)
                if self.cap.isOpened():
                    # Try to read a test frame
                    ret, test_frame = self.cap.read()
                    if ret:
                        print(f"Successfully connected using backend: {backend}")
                        break
                    else:
                        self.cap.release()
                        self.cap = None
                else:
                    if self.cap:
                        self.cap.release()
                    self.cap = None
            except Exception as e:
                print(f"Backend {backend} failed: {e}")
                if self.cap:
                    self.cap.release()
                self.cap = None
        
        # If still no success, try different camera indices with DirectShow
        if self.cap is None:
            print("Trying different camera indices...")
            for i in range(3):  # Try cameras 0, 1, 2
                try:
                    self.cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                    if self.cap.isOpened():
                        ret, test_frame = self.cap.read()
                        if ret:
                            print(f"Successfully connected to camera {i}")
                            break
                    self.cap.release()
                    self.cap = None
                except:
                    if self.cap:
                        self.cap.release()
                    self.cap = None
        
        if self.cap is None or not self.cap.isOpened():
            print("Error: Could not open any camera")
            return False
        
        # Set camera resolution first
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config["camera"]["width"])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config["camera"]["height"])
        
        # Handle FPS setting
        fps_config = self.config["camera"]["fps"]
        if fps_config == "max":
            self.fps = self.find_max_fps(self.cap)
        else:
            self.fps = int(fps_config)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        # Get actual camera properties
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        camera_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        camera_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        print(f"Camera resolution: {camera_width}x{camera_height} at {actual_fps:.1f} FPS")
        
        # Print ROI info
        roi_config = self.config["roi"]
        if roi_config.get("enabled", True):
            print(f"ROI enabled: x={roi_config['x']}, y={roi_config['y']}, "
                  f"width={roi_config['width']}, height={roi_config['height']}")
        else:
            print("ROI disabled - using full frame")
        
        # Create window
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        
        return True
    
    def process_frame(self, pump_data=None):
        """Process a single frame - returns (success, display_frame, roi_frame)
        
        Args:
            pump_data: Dictionary with pump information (optional)
                      Expected format: {'set_pressure': float, 'actual_pressure': float, 'offset': float}
        """
        # Read frame from camera
        ret, frame = self.cap.read()
        
        if not ret:
            print(f"Warning: Could not read frame {self.frame_count}")
            self.frame_count += 1
            if self.frame_count > 10:  # If we fail to read 10 frames in a row
                print("Too many failed frame reads.")
                return False, None, None
            return True, None, None  # Continue trying
        
        self.frame_count = 0  # Reset counter on successful read
        self.fps_counter += 1
        
        # Apply ROI
        roi_frame = self.apply_roi(frame, self.config["roi"])
        
        # Get actual ROI dimensions
        roi_height, roi_width = roi_frame.shape[:2]
        
        # Calculate and display actual FPS every second
        current_time = cv2.getTickCount()
        time_elapsed = (current_time - self.fps_timer) / cv2.getTickFrequency()
        
        if time_elapsed >= 1.0:  # Update every second
            actual_fps_display = self.fps_counter / time_elapsed
            self.fps_counter = 0
            self.fps_timer = current_time
        else:
            actual_fps_display = self.fps_counter / time_elapsed if time_elapsed > 0 else 0
        
        # Display recording status and FPS on frame
        y_pos = 20
        if self.recording:
            cv2.putText(roi_frame, "REC", (5, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            cv2.circle(roi_frame, (roi_width - 15, 15), 8, (0, 0, 255), -1)
            
            # Show recording duration
            if self.recording_start_time:
                elapsed = time.time() - self.recording_start_time
                cv2.putText(roi_frame, f"{elapsed:.1f}s", (5, y_pos + 25), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
        else:
            cv2.putText(roi_frame, "PREV", (5, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Display FPS
        y_pos += 50
        cv2.putText(roi_frame, f"FPS:{actual_fps_display:.0f}", (5, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        # Display pump data if available
        if pump_data:
            y_pos += 20
            cv2.putText(roi_frame, f"Set:{pump_data['set_pressure']:.1f}", (5, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
            
            y_pos += 15
            cv2.putText(roi_frame, f"Act:{pump_data['actual_pressure']:.1f}", (5, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
            
            y_pos += 15
            cv2.putText(roi_frame, f"Off:{pump_data['offset']:.1f}", (5, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
        
        # Write frame to video file if recording
        if self.recording and self.out is not None:
            try:
                self.out.write(roi_frame)
            except Exception as e:
                print(f"Error writing frame to video: {e}")
        
        return True, roi_frame, roi_frame
    
    def _create_video_writer(self, filename, roi_width, roi_height):
        """Create video writer with codec fallback"""
        recording_config = self.config.get("recording", {})
        
        # Get codec list to try
        codecs_to_try = recording_config.get("retry_codecs", ["mp4v", "XVID", "MJPG", "X264"])
        
        # If we have a successful codec from before, try it first
        if self.last_successful_codec and isinstance(self.last_successful_codec, str):
            if self.last_successful_codec not in codecs_to_try:
                codecs_to_try = [self.last_successful_codec] + codecs_to_try
            else:
                # Move successful codec to front
                codecs_to_try = [self.last_successful_codec] + [c for c in codecs_to_try if c != self.last_successful_codec]
        
        for codec_name in codecs_to_try:
            try:
                print(f"Attempting to create video writer with codec: {codec_name}")
                fourcc = cv2.VideoWriter_fourcc(*codec_name)
                out = cv2.VideoWriter(filename, fourcc, self.fps, (roi_width, roi_height))
                
                if out.isOpened():
                    self.last_successful_codec = codec_name
                    print(f"Successfully created video writer with codec: {codec_name}")
                    return out
                else:
                    out.release()
                    
            except Exception as e:
                print(f"Codec {codec_name} failed: {e}")
                continue
        
        print("Error: Could not create video writer with any codec")
        return None
    
    def start_recording(self, filepath=None):
        """Start recording video with improved error handling
        
        Args:
            filepath: Optional path to save the video. If None, saves in current directory
                     Can be a directory path or full file path
        
        Returns:
            bool: True if recording started successfully, False otherwise
        """
        if self.recording:
            print("Already recording!")
            return False
        
        try:
            # Generate timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Handle filepath input
            if filepath is None:
                # Save in current directory with default naming
                filename = f"video_record_{timestamp}.mp4"
            else:
                # Check if filepath is a directory or full file path
                if os.path.isdir(filepath):
                    # It's a directory, add default filename
                    filename = os.path.join(filepath, f"video_record_{timestamp}.mp4")
                elif os.path.dirname(filepath):
                    # It's a full path, use it but add timestamp before extension
                    dir_path = os.path.dirname(filepath)
                    base_name = os.path.splitext(os.path.basename(filepath))[0]
                    extension = os.path.splitext(os.path.basename(filepath))[1] or ".mp4"
                    filename = os.path.join(dir_path, f"{base_name}_{timestamp}{extension}")
                else:
                    # It's just a filename, add timestamp
                    base_name = os.path.splitext(filepath)[0]
                    extension = os.path.splitext(filepath)[1] or ".mp4"
                    filename = f"{base_name}_{timestamp}{extension}"
            
            print(f"Starting recording to: {filename}")
            
            # Ensure directory exists
            dir_path = os.path.dirname(filename) if os.path.dirname(filename) else "."
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path)
                    print(f"Created directory: {dir_path}")
                except OSError as e:
                    print(f"Error creating directory {dir_path}: {e}")
                    return False
            
            # Get ROI dimensions for recording
            roi_config = self.config["roi"]
            if roi_config.get("enabled", True):
                roi_width = roi_config["width"]
                roi_height = roi_config["height"]
            else:
                roi_width = self.config["camera"]["width"]
                roi_height = self.config["camera"]["height"]
            
            # Create video writer
            self.out = self._create_video_writer(filename, roi_width, roi_height)
            
            if self.out is None:
                return False
            
            self.recording = True
            self.recording_start_time = time.time()
            print(f"Recording started: {filename}")
            print(f"Recording resolution: {roi_width}x{roi_height} at {self.fps} FPS")
            print("Recording will continue until manually stopped")
            return True
            
        except Exception as e:
            print(f"Error starting recording: {e}")
            if self.out:
                try:
                    self.out.release()
                except:
                    pass
                self.out = None
            return False
    
    def stop_recording(self):
        """Stop recording video with proper cleanup"""
        if not self.recording:
            print("Not currently recording!")
            return False
        
        # Calculate recording duration
        duration = time.time() - self.recording_start_time if self.recording_start_time else 0
        print(f"Stopping recording after {duration:.1f} seconds...")
        
        try:
            # Set recording flag to false first to stop new frames from being written
            self.recording = False
            
            # Give a small delay to ensure any pending frame writes complete
            cleanup_delay = self.config.get("recording", {}).get("cleanup_delay", 0.15)
            time.sleep(cleanup_delay)
            
            # Now safely close the video writer
            if self.out is not None:
                try:
                    # Ensure any remaining frames are flushed
                    self.out.release()
                    print("Video writer closed successfully")
                except Exception as e:
                    print(f"Warning during video writer cleanup: {e}")
                finally:
                    self.out = None
            
            # Reset timing
            self.recording_start_time = None
            
            print(f"Recording stopped successfully after {duration:.1f}s")
            return True
            
        except Exception as e:
            print(f"Error stopping recording: {e}")
            # Ensure cleanup even on error
            if self.out is not None:
                try:
                    self.out.release()
                except:
                    pass
                finally:
                    self.out = None
            self.recording = False
            self.recording_start_time = None
            return False
    
    def reload_config(self):
        """Reload configuration from file"""
        print("Reloading configuration...")
        self.config = self.load_config()
        roi_config = self.config["roi"]
        if roi_config.get("enabled", True):
            print(f"ROI updated: x={roi_config['x']}, y={roi_config['y']}, "
                  f"width={roi_config['width']}, height={roi_config['height']}")
        else:
            print("ROI disabled")
    
    def show_fps_info(self):
        """Display FPS information"""
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS) if self.cap else 0
        current_time = cv2.getTickCount()
        time_elapsed = (current_time - self.fps_timer) / cv2.getTickFrequency()
        measured_fps = self.fps_counter / time_elapsed if time_elapsed > 0 else 0
        print(f"Set FPS: {self.fps}, Actual FPS: {actual_fps:.1f}, Measured FPS: {measured_fps:.1f}")
    
    def get_recording_status(self):
        """Get current recording status"""
        status = {
            "recording": self.recording,
            "output_file": getattr(self.out, 'filename', None) if self.out else None,
            "last_successful_codec": self.last_successful_codec
        }
        
        if self.recording and self.recording_start_time:
            status["duration"] = time.time() - self.recording_start_time
        
        return status
    
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up camera resources...")
        
        # Stop recording if active
        if self.recording:
            self.stop_recording()
        
        # Release camera
        if self.cap is not None:
            self.cap.release()
        
        # Close OpenCV windows
        cv2.destroyAllWindows()
        print("Camera module cleaned up")