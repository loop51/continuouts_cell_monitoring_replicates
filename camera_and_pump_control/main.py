import cv2
import os
from camera_module import CameraROI
from pump_control_module import create_pump_controller
from udp_control_module import create_udp_controller
from ai_vision_module_simple import create_ai_vision_controller

def main():
    # Initialize camera module
    camera = CameraROI("config.json")
    
    # Initialize camera
    if not camera.initialize_camera():
        print("Failed to initialize camera")
        return
    
    # Initialize pump controller (optional)
    pump_controller = None
    if os.path.exists("pump_config.json"):
        pump_controller = create_pump_controller("pump_config.json")
        if pump_controller:
            print("Pump controller initialized successfully")
        else:
            print("Failed to initialize pump controller")
    else:
        print("No pump configuration found, running camera only")
    
    # Initialize UDP controller (optional)
    udp_controller = None
    if os.path.exists("udp_config.json"):
        udp_controller = create_udp_controller("udp_config.json")
        if udp_controller:
            # Set up event callbacks
            udp_controller.on_start_recording = lambda filepath: camera.start_recording(filepath)
            udp_controller.on_stop_recording = lambda: camera.stop_recording()
            udp_controller.on_command_received = lambda msg, addr: print(f"UDP Command: {msg['command']} from {addr}")
            
            # Start listening
            if udp_controller.start_listening():
                print("UDP controller initialized and listening")
            else:
                print("Failed to start UDP controller")
                udp_controller = None
        else:
            print("Failed to initialize UDP controller")
    else:
        print("No UDP configuration found, running without UDP control")
    
    # Initialize AI vision controller (optional)
    ai_vision = None
    if os.path.exists("ai_vision_config.json"):
        ai_vision = create_ai_vision_controller("ai_vision_config.json")
        if ai_vision:
            print("AI Vision Controller initialized successfully")
        else:
            print("Failed to initialize AI Vision Controller")
    else:
        print("No AI vision configuration found, running without AI control")
    
    print("\nControls:")
    print("Camera (Keyboard):")
    print("  's' - Start recording")
    print("  'e' - End/Stop recording")
    print("  'r' - Reload configuration")
    print("  'f' - Show current FPS")
    print("  'a' - Toggle AI Vision Control")
    print("  'i' - Show AI Vision Status")
    print("  'l' - Toggle Horizontal Lines (AI Vision)")
    print("  'p' - Show Pump Status")
    print("  'u' - Show UDP Status")
    print("  'q' - Quit")
    
    if pump_controller:
        print("\nPump (Gamepad):")
        print("  Left Stick (Up/Down) - Base pressure control")
        print("  Right Trigger (RT) - Multiply pressure")
        print("  Left Trigger (LT) - Divide pressure")
        print("  Button A - Reset offset to 0")
        print("  Button Y - Set offset to current pressure")
        print("  Button LB - Set offset to minimum pressure")
        print("  Button RB - Set offset to maximum pressure")
        print("  Back/Start Button - Toggle AI Vision Control")
    
    if udp_controller:
        config = udp_controller.config
        print(f"\nUDP Control (Network):")
        print(f"  Listening on: {config['network']['ip']}:{config['network']['port']}")
        print("  Commands:")
        print("    JSON: {\"command\": \"start_recording\", \"filepath\": \"path\", \"filename\": \"name\", \"duration\": 60}")
        print("    Text: START_REC|path|filename|duration")
        print("    Text: STOP_REC")
        print("    Text: PING")
    
    if ai_vision:
        print("\nAI Vision Control:")
        print("  Back/Start Button (Gamepad) - Toggle AI control on/off")
        print("  'a' key (Keyboard) - Toggle AI control on/off")
        print("  When AI enabled: Pump controlled by computer vision")
        print("  When AI disabled: Manual gamepad control")
    # Get pump data if available
    pump_data = None
    ai_pressure_command = None
            
    # Process camera frame first to get roi_frame
    success, display_frame, roi_frame = camera.process_frame(pump_data)
    
    ai_vision.setup_background(roi_frame)
    
    try:
        while True:
            # Get pump data if available
            pump_data = None
            ai_pressure_command = None
            
            # Process camera frame first to get roi_frame
            success, display_frame, roi_frame = camera.process_frame(pump_data)
            
            if not success:
                break
            
            # Skip if no frame was captured
            if display_frame is None:
                continue
            
            
                
            # Process AI vision if available
            if ai_vision and pump_controller and roi_frame is not None:
                if pump_controller.read_update_initial_value_flag:
                    f, r, c = pump_controller.read_initial_values()
                    # f--> forward, r--> reverse, c--> control
                    ai_vision.update_control_initial_params(f,r,c)
                
                
                current_pressure = pump_controller.get_pressure_info()["set_pressure"]
                # print(f"current pressure: {current_pressure}")
                ai_pressure_command = ai_vision.process_frame(roi_frame, current_pressure)
            
            if pump_controller:
                pump_data = pump_controller.get_pressure_info()
                # Process pump controller input with AI override
                if not pump_controller.process_gamepad_input(ai_pressure_command):
                    print("Pump controller error or quit signal")
                    # Update pump data after processing
                    pump_data = pump_controller.get_pressure_info()
            
            
            # Re-process camera frame with updated pump data
            success, display_frame, roi_frame = camera.process_frame(pump_data)
            
            if not success:
                break
            
            # Skip if no frame was captured
            if display_frame is None:
                continue
            
            # Add AI vision overlay if available
            if ai_vision and roi_frame is not None:
                display_frame = ai_vision.add_visualization(display_frame, pump_data)
            
            # Show the frame
            cv2.namedWindow(camera.window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
            cv2.imshow(camera.window_name, display_frame)
            if pump_controller.save_tracking_data_flag:
                ai_vision.reload_config()
                camera.reload_config()
                pump_controller.save_tracking_data_flag=0
            # Handle keyboard input (camera controls)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('s'):
                camera.start_recording()
            
            elif key == ord('e'):
                camera.stop_recording()
            
            elif key == ord('f'):
                camera.show_fps_info()
                # Also show pump info if available
                if pump_controller:
                    pressure_info = pump_controller.get_pressure_info()
                    print(f"Pump - Set: {pressure_info['set_pressure']:.2f}, "
                          f"Actual: {pressure_info['actual_pressure']:.2f}, "
                          f"Offset: {pressure_info['offset']:.2f}")
            
            elif key == ord('r'):
                camera.reload_config()
            
            elif key == ord('p'):
                # Print pump status
                if pump_controller:
                    pressure_info = pump_controller.get_pressure_info()
                    print(f"Pump Status - Set: {pressure_info['set_pressure']:.2f}, "
                          f"Actual: {pressure_info['actual_pressure']:.2f}, "
                          f"Offset: {pressure_info['offset']:.2f}, "
                          f"Control: {pressure_info['control_mode']}")
                else:
                    print("No pump controller available")
            
            elif key == ord('u'):
                # Print UDP status
                if udp_controller:
                    print(f"UDP Controller running on {udp_controller.config['network']['ip']}:{udp_controller.config['network']['port']}")
                else:
                    print("No UDP controller available")
            
            elif key == ord('a'):
                # Toggle AI vision control
                if ai_vision:
                    status = ai_vision.toggle()
                    print(f"AI Vision Control: {'ENABLED' if status else 'DISABLED'}")
                else:
                    print("No AI vision controller available")
            
            elif key == ord('l'):
                # Toggle horizontal lines visibility
                if ai_vision:
                    current_state = ai_vision.config["horizontal_lines"]["show_lines"]
                    ai_vision.config["horizontal_lines"]["show_lines"] = not current_state
                    new_state = ai_vision.config["horizontal_lines"]["show_lines"]
                    print(f"Horizontal Lines: {'VISIBLE' if new_state else 'HIDDEN'}")
                else:
                    print("No AI vision controller available")
            
            elif key == ord('i'):
                # Print AI vision status
                if ai_vision:
                    status = ai_vision.get_status()
                    print(f"AI Vision - Enabled: {status['enabled']}, "
                          f"Target Pressure: {status['target_pressure']:.1f}, "
                          f"Detections: {status['detection_count']}")
                else:
                    print("No AI vision controller available")
            elif key == ord('v'):
                # Toggle velocity plotting
                if ai_vision:
                    status = ai_vision.toggle_velocity_plot()
                    print(f"Velocity plotting: {'ENABLED' if status else 'DISABLED'}")
            
            elif key == ord('q'):
                break
            
            # You can add other modules/processing here
            # For example:
            # if roi_frame is not None:
            #     data_logger.log_frame(roi_frame, ai_vision.get_status() if ai_vision else None, pump_data)
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        # Clean up
        camera.cleanup()
        if pump_controller:
            pump_controller.cleanup()
        if udp_controller:
            udp_controller.cleanup()
        if ai_vision:
            ai_vision.cleanup()

if __name__ == "__main__":
    main()