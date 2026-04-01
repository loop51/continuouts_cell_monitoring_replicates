function udp_record(action, varargin)
    % Simple UDP Camera Control Functions
    %
    % Usage:
    %   udp_record('start')                          % Start with default settings
    %   udp_record('start', 'duration', 30)         % Start 30-second recording
    %   udp_record('start', 'filename', 'test.mp4') % Start with custom filename
    %   udp_record('start', 'filepath', 'data/')    % Start in specific folder
    %   udp_record('stop')                          % Stop recording
    %   udp_record('ping')                          % Test connection
    %
    % Examples:
    %   udp_record('start', 'duration', 60, 'filename', 'experiment1.mp4', 'filepath', 'data/')
    %   udp_record('stop')
    
    % Default configuration
    HOST = 'localhost';
    PORT = 12345;
    
    % Parse input arguments
    p = inputParser;
    addRequired(p, 'action', @(x) ischar(x) || isstring(x));
    addParameter(p, 'duration', 10, @isnumeric);
    addParameter(p, 'filename', '', @(x) ischar(x) || isstring(x));
    addParameter(p, 'filepath', '.', @(x) ischar(x) || isstring(x));
    addParameter(p, 'host', HOST, @(x) ischar(x) || isstring(x));
    addParameter(p, 'port', PORT, @isnumeric);
    
    parse(p, action, varargin{:});
    
    action = lower(char(p.Results.action));
    duration = p.Results.duration;
    filename = char(p.Results.filename);
    filepath = char(p.Results.filepath);
    host = char(p.Results.host);
    port = p.Results.port;
    
    try
        switch action
            case 'start'
                start_recording(host, port, duration, filename, filepath);
            case 'stop'
                stop_recording(host, port);
            case 'ping'
                ping_server(host, port);
            otherwise
                fprintf('Unknown action: %s\n', action);
                fprintf('Valid actions: start, stop, ping\n');
        end
    catch ME
        fprintf('Error: %s\n', ME.message);
        fprintf('Make sure your Python camera system is running.\n');
    end
end

function start_recording(host, port, duration, filename, filepath)
    % Start recording with specified parameters
    
    % Generate filename if not provided
    if isempty(filename)
        timestamp = datestr(now, 'yyyymmdd_HHMMSS');
        filename = sprintf('matlab_recording_%s.mp4', timestamp);
    end
    
    % Create UDP object
    udp_obj = udpport("LocalPort", 0);
    
    try
        % Create JSON command
        command_struct.command = 'start_recording';
        command_struct.filepath = filepath;
        command_struct.filename = filename;
        command_struct.duration = duration;
        
        json_command = jsonencode(command_struct);
        
        fprintf('Starting recording...\n');
        fprintf('File: %s/%s\n', filepath, filename);
        fprintf('Duration: %d seconds\n', duration);
        fprintf('Sending to: %s:%d\n', host, port);
        
        % Send command
        write(udp_obj, uint8(json_command), host, port);
        
        fprintf('✓ Recording command sent successfully!\n');
        fprintf('Check your camera system for confirmation.\n');
        
    catch ME
        fprintf('✗ Failed to start recording: %s\n', ME.message);
        rethrow(ME);
    end
    
    % Clean up
    clear udp_obj;
end

function stop_recording(host, port)
    % Stop current recording
    
    % Create UDP object
    udp_obj = udpport("LocalPort", 0);
    
    try
        command = 'STOP_REC';
        
        fprintf('Stopping recording...\n');
        fprintf('Sending to: %s:%d\n', host, port);
        
        % Send command
        write(udp_obj, uint8(command), host, port);
        
        fprintf('✓ Stop command sent successfully!\n');
        
    catch ME
        fprintf('✗ Failed to stop recording: %s\n', ME.message);
        rethrow(ME);
    end
    
    % Clean up
    clear udp_obj;
end

function ping_server(host, port)
    % Test connection to camera system
    
    % Create UDP object
    udp_obj = udpport("LocalPort", 0);
    
    try
        command = 'PING';
        
        fprintf('Testing connection to %s:%d...\n', host, port);
        
        % Send ping
        write(udp_obj, uint8(command), host, port);
        fprintf('Ping sent. Check camera system console for response.\n');
        
    catch ME
        fprintf('✗ Failed to ping server: %s\n', ME.message);
        rethrow(ME);
    end
    
    % Clean up
    clear udp_obj;
end