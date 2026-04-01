%% Connect to instrument
clc; close all;
clearvars -except vid src MtrController myCom;
% settings by user
NumPoints = 5001;
CW_Freq = 3e9;
y_axis_range = 0.0025;
SenseType = '5um PS in DI';
IFBW = .5e3;
VNA_Power = 10;

% device specifications, in m
ML_width = 20e-6;
MF_height = 10e-6;
MF_width = 100e-6;

% for 1 hour use 72 times
% for 4 hours use 288
times_to_repeat = 1;
root_location = pwd;


frequency1  = 0.5e9;
frequency2  = 1.5e9;
frequency3  = 3.5e9;
frequency4  = 4.5e9;
frequency5  = 5.7e9;
frequency6  = 10.5e9;
% frequency7  = 11e9;
% frequency8  = 17e9;

frequency = [frequency1 frequency2 frequency3 frequency4 frequency5 frequency6];
% frequency = frequency6;

% frequency1  = 6e9;
% frequency2  = 10.5e9;
% frequency3  = 11e9;

% frequency = [frequency1 frequency2 frequency3];
for ii=1:length(frequency)
    mkdir(strcat(num2str(frequency(ii)/1e9),"GHz"));
end

%% create the folders
for ii=1:times_to_repeat
    for jj=1:length(frequency)
        mkdir(strcat(root_location, "\",num2str(frequency(jj)/1e9), "GHz\","set", num2str(ii)))
    end

end
%%

try
    vna_n5230 = visadev("TCPIP0::192.168.10.20::5025::SOCKET"); 
catch ME
    error ('Error initializing the N5230A:\n%s', ME.message);
end  
% vna_n5230.Timeout = 60;
% vna_n5230.ByteOrder= 'big-endian';
% 
% writeline(vna_n5230,'*cls');
% writeline(vna_n5230,'*rst');
% 
% ID_keysight = writeread(vna_n5230,'*IDN?');
% 
% writeline(vna_n5230,'CALC:PAR CH1_S21_2, S21')
% 
% writeline(vna_n5230,'display:window:trace2:feed CH1_S21_2');
% 
% writeline(vna_n5230, 'SENS:CORR:CSET:ACT "CalSet_03302026",ON');
% writeline(vna_n5230, ['Source:Power ' num2str(VNA_Power)]);
% 
% pause(10);

for ll=1:times_to_repeat
    disp(strcat("set: ", num2str(ll)));
    for pp=1:length(frequency)
        location_to_save = strcat(root_location, "\",num2str(frequency(pp)/1e9), "GHz\","set", num2str(ll),"\");
        CW_Freq = frequency(pp);
        disp(strcat("measuring frequency: ", num2str(frequency(pp)/1e9), "GHz"));
        try
            N5230a_oscillating_data_acquisition_with_video;
        catch
            disp("first try failed");
            try
                vna_n5230.flush;
                N5230a_oscillating_data_acquisition_with_video;
            catch
                disp("second try failed");
                vna_n5230.flush;
                N5230a_oscillating_data_acquisition_with_video;
            end
        end
    end

end

writeline(vna_n5230, 'initiate:continuous ON');
writeline(vna_n5230, 'sense:sweep:mode cont');

clear vna_n5230

