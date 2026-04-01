clc;
% clear;
clearvars -except vid src;
%% Instrument Connection
NumPoints = 20001;
StartFreq = 10e6;
StopFreq = 20e9;
MUT = 'water at 32C no calibration';
IFBW = .5e3;
VNA_power = 10;


%%
try
    vna_n5230 = visadev("TCPIP0::192.168.10.20::5025::SOCKET"); 
catch ME
    error ('Error initializing the N5230A:\n%s', ME.message);
end    
vna_n5230.Timeout = 120;
vna_n5230.ByteOrder= 'big-endian';

writeline(vna_n5230,'*cls');
ID_keysight = writeread(vna_n5230,'*IDN?');
writeline(vna_n5230,'*rst');

%%
writeline(vna_n5230,'CALC:PAR CH1_S21_2, S21');

writeline(vna_n5230,'display:window:trace2:feed CH1_S21_2');


writeline(vna_n5230,'CALC:PAR CH1_S12_3, S12');

writeline(vna_n5230,'display:window:trace3:feed CH1_S12_3');

writeline(vna_n5230,'CALC:PAR CH1_S22_4, S22');

writeline(vna_n5230,'display:window:trace4:feed CH1_S22_4');

writeline(vna_n5230, ['Source:Power ' num2str(VNA_power)]);
% writeread(vna_n5230,'Source:Power?');

% writeline(vna_n5230, 'SENS:CORR:CSET:ACT "CalSet_03302026",ON');
% pause(10);
%%
writeline(vna_n5230, 'format real,64')
writeline(vna_n5230, 'format:data real,64')
% writeread(vna_n5230, 'format:data?')
%%
% writeline(vna_n5230, '*cls');

writeline(vna_n5230, ['sense:BWID ' num2str(IFBW)]);
writeline(vna_n5230, ['sense:sweep:points ' num2str(NumPoints)]);

%%
writeline(vna_n5230, 'initiate:continuous off');
writeline(vna_n5230, 'sense:sweep:type LIN');
% fprintf(obj1, 'sense:freq:start %d', StartFreq);
writeline(vna_n5230, ['sense:freq:start ' num2str(StartFreq)]);
% fprintf(obj1, 'sense:freq:stop %d', StopFreq);
writeline(vna_n5230, ['sense:freq:stop ' num2str(StopFreq)]);

%%
writeline(vna_n5230, 'calc:par:sel CH1_S11_1');
% writeline(vna_n5230, 'format:data real,64');
writeline(vna_n5230, 'initiate:immediate');

%%
busy = str2num(writeread(vna_n5230,'*OPC?'));
while (busy == 0)
    busy = str2num(writeread(vna_n5230,'*OPC?'))
end
% pause(40);
%% get the data

% flush(vna_n5230);
vna_n5230.flush;

try
    writeline(vna_n5230, 'calc:data? sdata');
    % vna_n5230.NumBytesAvailable
    x = readbinblock(vna_n5230, "double");
catch

end

data_s11 =  ones(length(x)/2,1);
jj=1;
for ii=1:2:length(x)
    data_s11(jj) = x(ii) +(1i*x(ii+1));
    jj= jj+1;
end
vna_n5230.flush;

% s21
writeline(vna_n5230, 'calc:par:sel CH1_S21_2');
try
    writeline(vna_n5230, 'calc:data? sdata');
    % vna_n5230.NumBytesAvailable
    x = readbinblock(vna_n5230, "double");
catch

end

data_s21 =  ones(length(x)/2,1);
jj=1;
for ii=1:2:length(x)
    data_s21(jj) = x(ii) +(1i*x(ii+1));
    jj= jj+1;
end
vna_n5230.flush;

% s12
writeline(vna_n5230, 'calc:par:sel CH1_S12_3');
try
    writeline(vna_n5230, 'calc:data? sdata');
    % vna_n5230.NumBytesAvailable
    x = readbinblock(vna_n5230, "double");
catch

end

data_s12 =  ones(length(x)/2,1);
jj=1;
for ii=1:2:length(x)
    data_s12(jj) = x(ii) +(1i*x(ii+1));
    jj= jj+1;
end
vna_n5230.flush;

% s22
writeline(vna_n5230, 'calc:par:sel CH1_S22_4');
try
    writeline(vna_n5230, 'calc:data? sdata');
    % vna_n5230.NumBytesAvailable
    x = readbinblock(vna_n5230, "double");
catch

end

data_s22 =  ones(length(x)/2,1);
jj=1;
for ii=1:2:length(x)
    data_s22(jj) = x(ii) +(1i*x(ii+1));
    jj= jj+1;
end
vna_n5230.flush;

% need to get frequency as well
try
    writeline(vna_n5230, 'SENSE:X?');
    % vna_n5230.NumBytesAvailable
    f = readbinblock(vna_n5230, "double");
catch

end

%%

writeline(vna_n5230, 'initiate:continuous ON');
writeline(vna_n5230, 'sense:sweep:mode cont');

%% save data
filename_data = strcat(string(datetime('today')),'_sensor_data_', MUT, '_IFBW_is_', string(IFBW), '_NumPoints_is_', string(NumPoints));
dlmwrite(strcat(filename_data, '_S11') , data_s11,'delimiter', ',', 'precision', 16);
dlmwrite(strcat(filename_data, '_S21') , data_s21,'delimiter', ',', 'precision', 16);

dlmwrite(strcat(filename_data, '_S12') , data_s12,'delimiter', ',', 'precision', 16);
dlmwrite(strcat(filename_data, '_S22') , data_s22,'delimiter', ',', 'precision', 16);
dlmwrite(strcat(filename_data, '_Frequency') , f,'delimiter', ',', 'precision', 16);

%%
figure();
plot(f,20*log10(abs(data_s11)))
hold on;
plot(f,20*log10(abs(data_s21)))
plot(f,20*log10(abs(data_s12)))
plot(f,20*log10(abs(data_s22)))

% title(['s21 vs frequency with 1601 data points, ' string(datetime('now')) ' channel has air' sprintf('\n') 'long cable']);
title(strcat('S-parameter magnitude vs frequency,', string(datetime('now')), ' channel has ', MUT));
ylabel('|S| in dB');
xlabel('Frequency Hz');
legend('|S_1_1|','|S_2_1|', '|S_1_2|', '|S_2_2|', 'Location','southeast')
grid on;

saveas(gcf, strcat(filename_data, ' mag','.jpeg'),'jpeg');
saveas(gcf, strcat(filename_data, ' mag','.fig'),'fig');

figure();
plot(f, rad2deg(angle(data_s11)));
hold on;
plot(f, rad2deg(angle(data_s21)));

plot(f, rad2deg(angle(data_s12)));
hold on;
plot(f, rad2deg(angle(data_s22)));

title(strcat('S-parameters phase vs frequency,', string(datetime('now')), ' channel has ', MUT));
ylabel('\angle S in dB');
xlabel('Frequency Hz');
legend('\angle S_1_1', '\angle S_2_1', '\angle S_1_2', '\angle S_2_2', 'Location','southeast')
ylabel('\angle S-parameters in degrees');
xlabel('Frequency Hz');
grid on;

saveas(gcf, strcat(filename_data, ' phase','.jpeg'),'jpeg');
saveas(gcf, strcat(filename_data, ' phase','.fig'),'fig');