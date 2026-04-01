This code was used so that the Luminera Infinitty camera could be used.\
The preview from MATLAB would have a freeze time of couple seconds when recording the video,
this could be circumvented with the previous camera (Amscope 1080p HD) because it had an HDMI output,
the output could be split into two paths, one feeding into the computer with CAMLINK (HDMI to USB) module,
and the other would directly display to a monitor.

# pump_control_module.py
The pump is controlled with an X-BOX gamepad. This code holds the code.

# config.json
To reduce the video file size, we used ROI based microscopic video preview and recorded video file. The ROI can be set/configured/adjusted here

# udp_control_module.py
This python code receives commands from the MATLAB code through UDP packets. The port number is specified in `udp_config.json` file.
The commands would specify when to start recording, stop recording, where to save the video file etc.

# camera_module.py
handles how the microscope image/video preview is displayed and when asked to record the video, how it is done.

# Note
Attempt was made to automate the cell position control with the pump using microscopic video as input for the controller.\
However, it wasnt reliable enough to obtain a full 300+ minute time lapse, the code is still presented here for future work
`ai_vision_config.json`
`ai_vision_module_simple.py`

