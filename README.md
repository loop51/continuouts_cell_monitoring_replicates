# Continuouts Cell Monitoring For Replicate Data After First Revision
1) To Preview the microscope view and pump control, run the python file main.py
2) Multi_frequency_data_acquisition_Keysight_N5230A.m --> set what is being measured, device specification, frequencies, IFBW, VNA power.

# Instrument Details
1) For microwave S parameter measurements, Keysight N5230A VNA was used
2) For the replicated data, Lumenera Infinity 8 monochrome microscope camerra was used because of its high resolution and high frames per second
3) For pressure based flow control, Fluigent push pull pump was used

# How To
Turn on all the instruments, Pump, Thermal Controller, VNA, Camera.\
To run the system first run the `main.py` of the python code.\
Set the following variables in `Multi_frequency_data_acquisition_Keysight_N5230A.m`:
```
  NumPoints = 5001; % determines how long each measurement set is going to be based on the value of IFBW
  SenseType = '5um PS in DI'; % define what is being measured
  IFBW = 500; % set the VNA IFBW
  VNA_Power  = 10; % set the VNA power
  ML_width = 20e-6; % define the sensor microstrip line width
  MF_height = 10e-6; % define the sensor micofluidic channel height
  MF_width = 100e-6; % define the sensor microfluidic channel width
  times_to_repeat  = 1; % how many times to repeat this sequence of frequency measurement, 
```

  Include the frequencies to be measured: 
  ```
  frequency1  = 0.5e9;
  frequency2  = 1.5e9;
  frequency3  = 3.5e9;
  frequency4  = 4.5e9;
  frequency5  = 5.7e9;
  frequency6  = 10.5e9;
  % frequency7  = 11e9;
  % frequency8  = 17e9;
  
  frequency = [frequency1 frequency2 frequency3 frequency4 frequency5 frequency6]; 
  % in this example 6 frequencies will be measured in a sequence and repeat itself
  ```
Then bring a cell into the microscope view, when ready to start measuring the time lapse of the said cell,
run `Multi_frequency_data_acquisition_Keysight_N5230A.m`
