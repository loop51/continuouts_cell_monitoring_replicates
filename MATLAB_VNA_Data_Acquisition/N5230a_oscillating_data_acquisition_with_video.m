% clc;
% clearvars -except ax cam fig frame im;
close all;
clearvars x x_axis_time s11 s21 

filename_data = strcat(location_to_save,string(datetime('today')),'_sensor_data_', SenseType, '_at_', string(CW_Freq/1e9), '_GHZ');
%%
% NumPoints = 20001;
% CW_Freq = 10.5e9;
% y_axis_range = 0.0025;
% SenseType = 'test';
% IFBW = .5e3;
% VNA_Power = 10;
% 
% % device specifications, in m
% ML_width = 20e-6;
% MF_height = 10e-6;
% MF_width = 100e-6;

FrameRate = 60;
%%
  
vna_n5230.Timeout = 60;
vna_n5230.ByteOrder= 'big-endian';

writeline(vna_n5230,'*cls');
writeline(vna_n5230,'*rst');

ID_keysight = writeread(vna_n5230,'*IDN?');

writeline(vna_n5230,'CALC:PAR CH1_S21_2, S21')

writeline(vna_n5230,'display:window:trace2:feed CH1_S21_2');

writeline(vna_n5230, ['Source:Power ' num2str(VNA_Power)]);
%%

% writeline(vna_n5230, '*cls');
writeline(vna_n5230, 'sense:sweep:type CW');
writeline(vna_n5230, ['sense:freq ' num2str(CW_Freq)]);


writeline(vna_n5230, ['sense:sweep:points ' num2str(NumPoints)]);

writeline(vna_n5230, 'format real,64')
writeline(vna_n5230, 'format:data real,64');


writeline(vna_n5230, 'initiate:continuous off');

writeline(vna_n5230, 'calc:par:sel CH1_S11_1');

writeline(vna_n5230, ['sense:BWID ' num2str(IFBW)]);



%% video capture
% vid.FramesPerTrigger = round((NumPoints * (1/IFBW)) / (1/FrameRate));
% vid.LoggingMode = "memory";
% vidWriter.FrameCounts
video_duration = round(NumPoints * (1/IFBW))+2;


%% initiate VNA video record
writeline(vna_n5230, 'initiate:immediate');
init_time = datetime('now');

%%
% this will acquire the frames per trigger number of frames
% start(vid);
% wait(vid,Inf);
% % this will have the frames with time stamps
% [frames, time] = getdata(vid, get(vid, 'FramesAvailable'));
% framerate = mean(1./diff(time));
disp('recording');
% udp_record('start', 'duration', video_duration, 'filepath', location_to_save, 'filename', 'video_log.mp4');
udp_record('start', 'filename', 'video_log.mp4', 'filepath', location_to_save)
% disp("done recording");
%% video log section
% vidWriter = VideoWriter(strcat(location_to_save, "set", num2str(ll), '_video_log.avi'));
% set the framerate of the video with 
% the framerate from the camera
% vidWriter.FrameRate = framerate;    
% open(vidWriter);
% writeVideo(vidWriter, frames);
% close(vidWriter);
%keep a log of the raw images and the time stamps as well
% save('image_log.mat', 'frames', 'time');
% clear frames time
% clear frames




%%
pause((NumPoints*(1/IFBW))+2)
busy = str2num(writeread(vna_n5230,'*OPC?'));
while (busy == 0)
    busy = str2num(writeread(vna_n5230,'*OPC?'));
end

udp_record('stop');
pause(3.5);
disp("done recording");
%% get the data

writeline(vna_n5230, 'calc:data? sdata');

x = readbinblock(vna_n5230, "double");

if length(x) ~= NumPoints*2
    disp('error S11');
    writeline(vna_n5230, 'calc:data? sdata');
    x = readbinblock(vna_n5230, "double");
end

s11 =  ones(NumPoints,1);
jj=1;
for ii=1:2:length(x)
    s11(jj) = x(ii) +(1i*x(ii+1));
    jj= jj+1;
end

writeline(vna_n5230, 'calc:par:sel CH1_S21_2');
writeline(vna_n5230, 'calc:data? sdata');
x = readbinblock(vna_n5230, "double");

if length(x) ~= NumPoints*2
    disp('error S21');
    writeline(vna_n5230, 'calc:data? sdata');
    x = readbinblock(vna_n5230, "double");
end


s21 =  ones(NumPoints,1);
jj=1;
for ii=1:2:length(x)
    s21(jj) = x(ii) +(1i*x(ii+1));
    jj= jj+1;
end

% need to get time as well
% fprintf(obj1, 'SENSE:X?');
writeline(vna_n5230, 'SENSE:X?');
x_axis_time = readbinblock(vna_n5230, "double");
if length(x_axis_time) ~= NumPoints
    disp('error time');
    writeline(vna_n5230, 'SENSE:X?');
    x_axis_time = readbinblock(vna_n5230, "double");
end

%%

% writeline(vna_n5230, 'initiate:continuous ON');
% writeline(vna_n5230, 'sense:sweep:mode cont');


%%
data_s11 = s11;
data_s21 = s21;

data_in_dB = 20*log10(abs(data_s11));
subplot(2,2,1);
plot(x_axis_time,data_in_dB);

title(strcat('s11 vs time,', string(datetime('now')), ' channel has, ', SenseType,  ' at,', string(CW_Freq/1e9), 'GHz' ));
ylabel('s11 in dB');

xlabel('time in seconds');
ylim_max = max(data_in_dB)+y_axis_range;
ylim_min = min(data_in_dB)-y_axis_range;
ylim([ylim_min ylim_max])
grid on;
subplot(2,2,3);
data_in_dB = 20*log10(abs(data_s21));
plot(x_axis_time,data_in_dB);

title(strcat('s21 vs time,', string(datetime('now')), ' channel has, ', SenseType,  ' at,', string(CW_Freq/1e9), 'GHz' ));

ylabel('s21 in dB');

xlabel('time in seconds');
ylim_max = max(data_in_dB)+y_axis_range;
ylim_min = min(data_in_dB)-y_axis_range;
ylim([ylim_min ylim_max])
grid on;

data_in_dB = rad2deg(angle(data_s11));
subplot(2,2,2);
plot(x_axis_time,data_in_dB);
% title(['s21 vs frequency with 1601 data points, ' string(datetime('now')) ' channel has air' sprintf('\n') 'long cable']);
title(strcat('\angle s11 vs time,', string(datetime('now')), ' channel has, ', SenseType,  ' at,', string(CW_Freq/1e9), 'GHz' ));
ylabel('\angle s11 in degrees');
% title(['s21 vs frequency with 1601 data points for just the cable (phase shifter) and attenuator line, ' string(datetime('now')) ' channel has air' sprintf('\n') 'long cable']);ylabel('s21 in dB');
xlabel('time in seconds');
ylim_max = max(data_in_dB)+y_axis_range;
ylim_min = min(data_in_dB)-y_axis_range;
ylim([ylim_min ylim_max])
grid on;

subplot(2,2,4);
data_in_dB = rad2deg(angle(data_s21));
plot(x_axis_time,data_in_dB);
% title(['s21 vs frequency with 1601 data points, ' string(datetime('now')) ' channel has air' sprintf('\n') 'long cable']);
title(strcat('\angle s21 vs time,', string(datetime('now')), ' channel has, ', SenseType,  ' at,', string(CW_Freq/1e9), 'GHz' ));

ylabel('\angle s21 in degrees');
% title(['s21 vs frequency with 1601 data points for just the cable (phase shifter) and attenuator line, ' string(datetime('now')) ' channel has air' sprintf('\n') 'long cable']);ylabel('s21 in dB');
xlabel('time in seconds');
ylim_max = max(data_in_dB)+y_axis_range;
ylim_min = min(data_in_dB)-y_axis_range;
ylim([ylim_min ylim_max])
grid on;


ax1 = subplot(2,2,1);
ax2 = subplot(2,2,2);
ax3 = subplot(2,2,3);
ax4 = subplot(2,2,4);

linkaxes([ax1,ax2,ax3,ax4],'x');

%%


dlmwrite(strcat(filename_data,'_S11'), s11,'delimiter', ',', 'precision', 16);

% csvwrite(strcat(filename_data, '_S21') , data_s21);
dlmwrite(strcat(filename_data,'_S21'), s21,'delimiter', ',', 'precision', 16);

% csvwrite(strcat(filename_data, '_x_axis_time') ,x_axis_time);
dlmwrite(strcat(filename_data,'_x_axis_time'), x_axis_time,'delimiter', ',', 'precision', 16);

%write the frame time stamps of the video log
% dlmwrite(strcat(filename_data,'_video_time_stamp'), time,'delimiter', ',', 'precision', 16);

% saveas(gcf, strcat(filename_data,'.jpeg'),'jpeg');
saveas(gcf, strcat(filename_data,'.fig'),'fig');

% csvwrite(strcat(filename_data, 'x_axis_time') ,x_axis_time);


%% more information logging
text_filename = strcat(location_to_save, "Experiment_Log.txt");
try
    delete text_filename
catch ME
    error ('No Existing Previous File:\n%s', ME.message);
end

fileID = fopen(text_filename, 'w');
init_time.Format = 'dd-MMM-uuuu HH:mm:ss.SSS';

% write the sampling initiation time
line = strcat("Data Acquisition Start Time = ", string(init_time)');
writelines(line,text_filename,WriteMode="append");

% write the DiPlexer Part Number
% line = strcat("DiPlexer Part Number = ", diplexer) ;
% writelines(line,text_filename,WriteMode="append");

% write the Experiment location
line = "Experiment Location = BRC 202" ;
writelines(line,text_filename,WriteMode="append");


% write frequencies used
% line = strcat("frequency1 = ", num2str(CW_Freq1/1e9), "GHz");
% writelines(line,text_filename,WriteMode="append");
% line = strcat("frequency2 = ", num2str(CW_Freq2/1e9), "GHz");
% writelines(line,text_filename,WriteMode="append");
line = strcat("frequency = ", num2str(CW_Freq/1e9), "GHz");
writelines(line,text_filename,WriteMode="append");

% write instruments used
% line = strcat("Instrument for f1 --> ", ID_1);
% writelines(line,text_filename,WriteMode="append");
% line = strcat("Instrument for f2 --> ", ID_2);
% writelines(line,text_filename,WriteMode="append");
line = strcat("Instrument --> ", ID_keysight);
writelines(line,text_filename,WriteMode="append");

% write IFBW used
line = strcat("Instrument IFBW --> ", num2str(IFBW), 'Hz');
writelines(line,text_filename,WriteMode="append");
% line = strcat("Instrument IFBW for f2 --> ", num2str(IFBW), 'Hz');
% writelines(line,text_filename,WriteMode="append");

% write instrumetn Power used
line = strcat("Instrument Power --> ", num2str(VNA_Power), 'dBm');
writelines(line,text_filename,WriteMode="append");
% line = strcat("Instrument Power for f2 --> ", num2str(VNA_Power), 'dBm');
% writelines(line,text_filename,WriteMode="append");

% write instrumetn DUT used
line = strcat("Device Under Test ", SenseType);
writelines(line,text_filename,WriteMode="append");

% write device specifications
line = strcat("Device Nominal Microstrip Line Width = ", num2str(ML_width*1e6), "um");
writelines(line,text_filename,WriteMode="append");
line = strcat("Device Nominal Microfluidic Channel Height = ", num2str(MF_height*1e6), "um");
writelines(line,text_filename,WriteMode="append");
line = strcat("Device Nominal Microfluidic Channel Width = ", num2str(MF_width*1e6), "um");
writelines(line,text_filename,WriteMode="append");

% write about averaging
line = "no Averaging was used in either VNA";
writelines(line,text_filename,WriteMode="append");
fclose(fileID);
clear fileID;

%% 
% clear vna_n5230