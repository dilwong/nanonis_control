r'''
The nanonis_programming_interface class initializes a socket connection
to Nanonis, allowing the user to send commands to Nanonis through a
TCP/IP connection.
'''

import socket
import sys
import atexit
import struct
import numpy as np

# Defines data types and their sizes in bytes
datatype_dict = {'int':'>i', \
                 'uint16':'>H', \
                 'uint32':'>I', \
                 'float32':'>f', \
                 'float64':'>d', \
                }
    
datasize_dict = {'int':4, \
                 'uint16':2, \
                 'uint32':4, \
                 'float32':4, \
                 'float64':8 \
                }
    
datatype_py_dict = {'int':int, \
                 'uint16':int, \
                 'uint32':int, \
                 'float32':float, \
                 'float64':float, \
                }

si_prefix = {'':1.0, \
             'a':1e-18, \
             'f':1e-15, \
             'p':1e-12, \
             'n':1e-9, \
             'u':1e-6, \
             'm':1e-3 \
            }

python_major_version = sys.version_info.major

class nanonisException(Exception):
    def __init__(self, message):
        super(nanonisException, self).__init__(message)

if python_major_version == 2:
    import thread
elif python_major_version == 3:
    import _thread as thread
else:
    raise nanonisException('Unknown Python version')

def decode_hex_from_string(input_string):
    r'''
    Converts a ([A-Fa-f0-9]{2})* string to a sequence of bytes
    '''
    if python_major_version == 2:
        return input_string.decode('hex')
    elif python_major_version == 3:
        return bytes.fromhex(input_string)
    else:
        raise nanonisException('Unknown Python version')

def to_binary(datatype, input_data):
    r'''
    Converts input_data to a sequence of bytes based on the datatype
    '''
    if datatype == 'string':
        if python_major_version == 2:
            return bytes(input_data)
        elif python_major_version == 3:
            return bytes(input_data,'utf-8')
        else:
            raise nanonisException('Unknown Python version')
    try:
        return struct.pack(datatype_dict[datatype], input_data)
    except KeyError:
        raise nanonisException('Unknown Data Type: ' + str(datatype))

def from_binary(datatype, input_data):
    r'''
    Converts a sequence of bytes input_data into a Python string, int, or float
    '''
    if datatype == 'string':
        if python_major_version == 2:
            return input_data
        elif python_major_version == 3:
            return input_data.decode('utf-8')
        else:
            raise nanonisException('Unknown Python version')
    try:
        return struct.unpack(datatype_dict[datatype], input_data)[0]
    except KeyError:
        raise nanonisException('Unknown Data Type ' + str(datatype))

def construct_header(command_name, body_size, send_response_back = True):
    r'''
    Builds a 40 byte header with the Nanonis command name and body size in bytes
    '''
    cmd_name_bytes = to_binary('string', command_name)
    len_cmd_name_bytes = len(cmd_name_bytes)
    cmd_name_bytes += b'\0' * (32 - len_cmd_name_bytes) # Pad command name with 0x00 to 32 bytes
    if send_response_back:
        response_flag = b'\x00\x01' # Tell Nanonis to send a response to client
    else:
        response_flag = b'\0\0' # Tell Nanonis to not send a response to client
    header = cmd_name_bytes + \
             to_binary('int', body_size) + \
             response_flag + b'\0\0'
    return header

def construct_command(command_name, *vargs):
    r'''
    Builds the sequence of bytes to send to Nanonis.
    This function takes an odd number of arguments. The first argument is the command name.
    The following arguments come in pairs: a string specifying the data type, the value of the data.
    '''
    if len(vargs) % 2 != 0:
        raise nanonisException('Unbalanced number of arguments')
    body_size = 0
    body = b''
    datatype = ''
    for idx, arg in enumerate(vargs):
        if idx % 2 == 0:
            #Check to see if the input type is a 1D array
            if arg.split("_")[0] == "1DArr":
                arrayDims = 1
                datatype = arg.split("_")[1] #Set the datatype to the second part of arg
                if type(vargs[idx-1]) == int: #Look for the argument that specifies array length (should be argument before for first array)
                    arrLen = vargs[idx-1] #Set the array length if arg two before current is int (if not will use previously set value)
                    if arrLen != len(vargs[idx+1]):
                        raise nanonisException('Array length ' + str(len(arg)) + ' but input array length is ' + str(arrLen))
                if datatype == 'string': #Special case to deal with an array of string
                    for string in vargs[idx+1]:
                        body_size += len(string)+4 #Adds on the number of bytes equal to str length + 4 for the integer containing string length
                else:
                    body_size += datasize_dict[datatype]*arrLen
                
            else:
                arrayDims = 0
                datatype = arg
                if datatype == 'string':
                    if vargs[idx-1] == len(vargs[idx+1]):
                        body_size += vargs[idx-1]
                    else:
                        raise nanonisException('String size is ' + str(len(arg)) + ' but input string length is ' + str(vargs[idx-1]))
                else:
                    body_size += datasize_dict[datatype]
        else:
            if arrayDims == 0 : #For data that is not in an array
                body += to_binary(datatype, arg)
            if arrayDims == 1:
                if datatype == 'string': #Special case for string
                    for string in arg:    
                        body += to_binary('int', len(string)) #Add an integer with the string length
                        body += to_binary(datatype, string) #Add the string to the body
                else:
                    for value in arg:
                        body += to_binary(datatype, value) #Add the value to the command body
            
    header = construct_header(command_name, body_size)
    return header + body

class nanonis_programming_interface:

    r'''
    API for interacting with Nanonis.

    Args:
        IP : str
            String containing IP address of computer running Nanonis.
            Defaults to localhost '127.0.0.1'.
        PORT: int
            Port number for Nanonis.
            Defaults to 6501.
            Nanonis can only serve one client per port. If a port is being used, use 6502, 6503, or 6504.
            If multiple clients connect to Nanonis, Nanonis will silently ignore the second or later connections.
    
    Attributes:
        BiasLimit : float (defaults to 10)
            Maximum absolute value of the bias (V).
        XScannerLimit : float (defaults to 1e-6)
            Maximum absolute value of the scanner range in the x direction (m).
        YScannerLimit : float (defaults to 1e-6)
            Maximum absolute value of the scanner range in the y direction (m).
        ZScannerLimit : float (defaults to 1e-7)
            Maximum absolute value of the scanner range in the z direction (m).
        LowerSetpointLimit : float (defaults to 0)
            Lowest possible value of the setpoint (A).
        UpperSetpointLimit : float (defaults to 1e-3)
            Largest possible value of the setpoint (A).

    Methods:
        send(command_name, *vargs)
        BiasSet(bias)
        BiasGet()
        TipXYSet(X, Y, wait = 1)
        TipXYGet(wait = 1)
        TipZSet(Z)
        TipZGet()
        FeedbackOnOffSet(feedbackStatus)
        FeedbackOnOffGet()
        Withdraw(wait = 1, timeout = -1)
        Home()
        SetpointSet(setpoint)
        SetpointGet()
        CurrentGet()
    '''
    
    def __init__(self, IP = '127.0.0.1', PORT = 6501):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((IP, PORT))
        self.lock = thread.allocate_lock()

        self.regex = None
        
        # Parameter limits in SI units (without prefixes, usually an SI base unit)
        self.BiasLimit = 10
        self.XScannerLimit = 1e-6
        self.YScannerLimit = 1e-6
        self.ZScannerLimit = 1e-7
        self.LowerSetpointLimit = 0
        self.UpperSetpointLimit = 1e-3

        # Executed at normal termination of Python interpreter
        @atexit.register
        def exit_handler():
            self.close()

    def close(self):
        self.socket.close()

    def transmit(self, message):
        self.socket.sendall(message)
        return self.socket.recv(1024)

    def send(self, command_name, *vargs):

        r'''
        Send a command to Nanonis.

        This method takes an odd number of arguments (not including self). The first argument is the command name.
        The following arguments come in pairs: a string specifying the data type, the value of the data.
        '''

        try:
            # Acquire an atomic lock to prevent receiving a response that is unrelated to the request.
            # This is actually unnecessary right now since there are no features that use concurrency.
            self.lock.acquire()

            response = self.transmit(construct_command(command_name, *vargs))
            returned_command = from_binary('string', response[:32])
            body_size = from_binary('int', response[32:36])
            body = response[40:]

            # Check to make sure the body size actually matches the body size specified in the response header.
            if body_size != len(body):
                errorMessage = 'Response body size error: ' + \
                                returned_command + ', ' + \
                                str(body_size) + ', ' + \
                                from_binary('string', body)
                raise nanonisException(errorMessage)
        except:
            raise
        finally:
            self.lock.release() # Release lock
        return {'command_name':returned_command, \
                'body_size':body_size, \
                'body':body \
                }
    
    @staticmethod
    def parse_response(response, *vargs):

        r'''
        Parse the response from Nanonis.

        Args:
            response: the return value of nanonis_programming_interface.send()
            *vargs: the data types of the information included in the body of the response message, not including the error message.

        Returns:
            Dictionary with the response information and error information.
            Note that the keys of the returned dictionary are strings of integers, not integers!
        '''

        bytecursor = 0
        parsed = {}
        for idx, arg in enumerate(vargs):
            if arg.split("_")[0] == "1DArr": #Check to see if data type is a 1D array
                #Search for the length of the array from previously parsed arguments (it will be the most recent integer argument)
                for _i in range(len(parsed)):
                    if type(parsed[str(idx-1-_i)]) == int:
                        arrLen = parsed[str(idx-1-_i)]
                        arrLenIdx = idx-_i
                        break
                        if idx-1-_i == 0:
                            raise nanonisException('No array length found for 1D array')    
                #array = np.zeros(arrLen) #Create a 1D array to put the values into
                if arg.split("_")[1] == "string": #Special case if the data type is string, need to find the byte size of each element in the array                   
                    array = np.zeros(arrLen, dtype=object)
                    for _j in range(arrLen):
                        bytesize = from_binary('int', response['body'][bytecursor:bytecursor + 4]) #Read in the integer that specifies the string length
                        bytecursor += 4
                        array[_j] = from_binary('string', response['body'][bytecursor:bytecursor + bytesize]) #Read the string for the current array element
                        bytecursor += bytesize

                else: #For non string data types
                    datatype = arg.split("_")[1]
                    bytesize = datasize_dict[datatype]
                    array = np.zeros(arrLen, dtype=datatype_py_dict[datatype]) #Initialise an array with the correct datatype
                    for _j in range(arrLen):
                        array[_j] = from_binary(datatype, response['body'][bytecursor:bytecursor + bytesize])
                        bytecursor += bytesize
                parsed[str(idx)] = array
            else:
                if arg == 'string':
                    bytesize = parsed[str(idx-1)]
                else:
                    bytesize = datasize_dict[arg]
                    parsed[str(idx)] = from_binary(arg, response['body'][bytecursor:bytecursor + bytesize])
                    bytecursor += bytesize
        parsed['Error status'] = from_binary('uint32', response['body'][bytecursor:bytecursor + 4])
        bytecursor += 4
        parsed['Error size'] = from_binary('int', response['body'][bytecursor:bytecursor + 4])
        bytecursor += 4
        if parsed['Error size'] != 0:
            parsed['Error description'] = from_binary('string', response['body'][bytecursor:bytecursor + parsed['Error size']])
            bytecursor += parsed['Error size']
        
        # If the total number of bytes requested by the user does not match body_size minus the error size, raise an exception.
        if bytecursor != response['body_size']:
            raise nanonisException('Response parse error: body_size = ' + str(response['body_size']))
        
        return parsed

    def convert(self, input_data):

        r'''
        Converts a number followed by an SI prefix into number * 10^{prefix exponent}

        Args:
            input_data : str
        
        Returns:
            Float
        '''

        if self.regex is None:
            import re
            self.regex = re.compile(r'^(-)?([0-9.]+)\s*([A-Za-z]*)$')
        match = self.regex.match(input_data)
        if match is None:
            raise nanonisException('Malformed number: Not a correctly formatted number')
        groups = match.groups()
        if groups[0] is None:
            sign = 1
        elif groups[0] == '-':
            sign = -1
        else:
            pass
        try:
            return sign * float(groups[1]) * si_prefix[groups[2]]
        except KeyError:
            raise nanonisException('Malformed number: SI prefix not recognized')
    
    def BiasSet(self, bias):

        r'''
        Set the bias (V).

        Args:
            bias : float

        Exceptions:
            nanonisException occurs when the absolute value of the bias exceeds BiasLimit.
        '''

        if type(bias) is str:
            bias_val = self.convert(bias)
        else:
            bias_val = float(bias)
        if -self.BiasLimit <= bias_val <= self.BiasLimit:
            self.send('Bias.Set', 'float32', bias_val)
        else:
            raise nanonisException('Bias out of bounds')
    
    def BiasGet(self):
        r'''Get the bias (V).'''
        return self.parse_response(self.send('Bias.Get'), 'float32')['0']

    # Does not "scrub" wait parameter for invalid input.
    def TipXYSet(self, X, Y, wait = 1):

        r'''
        Set the X, Y tip coordinates (m).

        Args:
            X : float
            Y : float
            wait : int
                By default, this method blocks until the tip is done moving.
                Set wait = 0 to return immediately instead of blocking.

        Exceptions:
            nanonisException occurs when the absolute value of X (Y) exceeds XScannerLimit (YScannerLimit).
        '''

        if type(X) is str:
            X_val = self.convert(X)
        else:
            X_val = float(X)
        if type(Y) is str:
            Y_val = self.convert(Y)
        else:
            Y_val = float(Y)
        if not (-self.XScannerLimit <= X_val <= self.XScannerLimit):
            raise nanonisException('X out of bounds')
        if not (-self.YScannerLimit <= Y_val <= self.YScannerLimit):
            raise nanonisException('Y out of bounds')
        self.send('FolMe.XYPosSet', 'float64', X_val, 'float64', Y_val, 'uint32', wait)

    def TipXYGet(self, wait = 1):
        r'''Returns a dictionary containing the X, Y tip coordinates (m).'''
        parsedResponse = self.parse_response(self.send('FolMe.XYPosGet', 'uint32', wait), 'float64', 'float64')
        return {'X': parsedResponse['0'], 'Y': parsedResponse['1']}

    def TipZSet(self, Z):

        r'''
        Set the Z tip height (m).

        Args:
            Z : float

        Exceptions:
            nanonisException occurs when the absolute value of Z exceeds ZScannerLimit.
        '''

        if type(Z) is str:
            Z_val = self.convert(Z)
        else:
            Z_val = float(Z)
        if not (-self.ZScannerLimit <= Z_val <= self.ZScannerLimit):
            raise nanonisException('Z out of bounds')
        self.send('ZCtrl.ZPosSet', 'float32', Z_val)

    def TipZGet(self):
        r'''Get the Z tip height (m).'''
        parsedResponse = self.parse_response(self.send('ZCtrl.ZPosGet'), 'float32')['0']
        return parsedResponse

    def FeedbackOnOffSet(self, feedbackStatus):

        r'''
        Turn on/off the Z-controller feedback.

        Args:
            feedbackStatus : Union[str, int]
                'On' or 1 to turn on the SPM feedback (closed).
                'Off' or 0 to turn off the SPM feedback (open).

        Exceptions:
            nanonisException occurs when feedbackStatus is not a valid input.
        '''
        
        if type(feedbackStatus) is str:
            if feedbackStatus.lower() == 'on':
                ZCtrlStatus = 1
            elif feedbackStatus.lower() == 'off':
                ZCtrlStatus = 0
            else:
                raise nanonisException('Feedback On or Off?')
        elif type(feedbackStatus) is int:
            if feedbackStatus == 1:
                ZCtrlStatus = 1
            elif feedbackStatus == 0:
                ZCtrlStatus = 0
            else:
                raise nanonisException('Feedback On or Off?')
        else:
            raise nanonisException('Feedback On or Off?')
        self.send('ZCtrl.OnOffSet', 'uint32', ZCtrlStatus)

    def FeedbackOnOffGet(self):
        r'''Returns the Z-controller feedback status as a string ('On' or 'Off')'''
        parsedResponse = self.parse_response(self.send('ZCtrl.OnOffGet'), 'uint32')['0']
        if parsedResponse == 1:
            return 'On'
        elif parsedResponse == 0:
            return 'Off'
        else:
            raise nanonisException('Unknown Feedback State')

    def Withdraw(self, wait = 1, timeout = -1):
        r'''
        Turn off the feedback and fully withdraw the tip.
        
        By default, this method blocks until the tip is fully withdrawn or timeout (ms) is exceeded.
        timeout = -1 is infinite timeout.
        '''
        self.send('ZCtrl.Withdraw', 'uint32', wait, 'int', timeout)

    def Home(self):
        r'''Turn off feedback and move the tip to the Home position.'''
        self.send('ZCtrl.Home')

    def SetpointSet(self, setpoint):

        r'''
        Set the setpoint value (usually the setpoint current (A)).

        Args:
            setpoint : float

        Exceptions:
            nanonisException occurs when setpoint is less than LowerSetpointLimit or greater than UpperSetpointLimit.
        '''

        if type(setpoint) is str:
            setpoint_val = self.convert(setpoint)
        else:
            setpoint_val = float(setpoint)
        if not (self.LowerSetpointLimit <= setpoint_val <= self.UpperSetpointLimit):
            raise nanonisException('Setpoint out of bounds')
        self.send('ZCtrl.SetpntSet', 'float32', setpoint_val)

    def SetpointGet(self):
        r'''Get the setpoint value (usually the setpoint current (A))'''
        parsedResponse = self.parse_response(self.send('ZCtrl.SetpntGet'), 'float32')['0']
        return parsedResponse

    def CurrentGet(self):
        r'''Get the value of the current (A)'''
        parsedResponse = self.parse_response(self.send('Current.Get'), 'float32')['0']
        return parsedResponse
    
    def AtomTrackCtrlSet(self, control, status):
        r'''Turns the selected Atom Tracking control (modulation, controller or drift measurement) on or off.
        
        Args:
            control : str or int
                'Modulation' or 0 to set the status of the Modulation control
                'Controller' or 1 to set the status of the AtomTracking controller
                'Drift' or 2 to set the status of the drift measuement control
            on : int or bool - True or 1 to turn the selected control on, False or 0 to turn the selected control off
            
        Exceptions:
            nanonisException occurs when an invalid argument for control is supplied
        '''
        #Convert control input to the necessary format
        if type(control) is str:
            if control.lower() == 'modulation':
                control = 0
            elif control.lower() == 'controller':
                control = 1
            elif control.lower() == 'drift':
                control = 2
            else:
                raise nanonisException('Invalid atom tracking control')
        
        #Convert from string to int if necessary
        if type(status) is str:
            if status.lower() == 'on':
                on = 1
            elif status.lower() == 'off':
                on = 0
            else:
                raise nanonisException('Feedback On or Off?')
        #Send the command
        if on:
            self.send('AtomTrack.CtrlSet', 'uint16', control, 'uint16', 1)
        else:
            self.send('AtomTrack.CtrlSet', 'uint16', control, 'uint16', 0)
    
    def AtomTrackStatusGet(self, control):
        r'''Get the status of the atom tracking control module.
        
        Args:
            control : Union[str, int]
            'Modulation' or 0 to check the status of the Modulation control (returns 0=off, 1=on)
            'Controller' or 1 to check the status of the AtomTracking controller (returns 0=off, 1=on)
            'Drift' or 2 to check the status of the drift measuement control (returns 0=off, 1=on)
            
        Exceptions:
            nanonisException occurs when an invalid argument for control is supplied
        '''
        if type(control) is str:
            if control.lower() == 'modulation':
                control = 0
            elif control.lower() == 'controller':
                control = 1
            elif control.lower() == 'drift':
                control = 2
            else:
                raise nanonisException('Invalid atom tracking control')
                
        parsedResponse = self.parse_response(self.send('AtomTrack.StatusGet', 'uint16', control), 'uint16')['0']
        return parsedResponse
    
    def AtomTrackPropsGet(self):
        r'''
        Get the atom tracking parameters.
        
        Args:
            None
            
        Returns a dictionary containing the following:
            iGain - float - gain of the atom tracking controller
            freq - float - frequency of modulation (Hz)
            amplitude - amplitude of the modulation (m)
            phase - float - phase of the modulation (°)
            soDelay - float - Switch off delay (s) Tracking position is averaged over this time before applying the position
        '''
        parsedResponse = self.parse_response(self.send('AtomTrack.PropsGet'), 'float32', 'float32', 'float32', 'float32', 'float32')
        #Check to see if error has been returned
        if parsedResponse['Error status']:
            raise nanonisException('Error executing AtomTrackPropsGet')
        else:
            return {'iGain': parsedResponse['0'], 'freq': parsedResponse['1'], 'amplitude': parsedResponse['2'], 'phase': parsedResponse['3'], 'soDelay': parsedResponse['4']}
    
    def FolMePSOnOffSet(self, psStatus):
        r'''Set the point and shoot option in follow me to on or off 
        
        Args:
             psStatus: Union[str, int]
            'Off' or 0 to turn point and shoot off
            'On' or 1 to turn point and shoot on
            
        Exceptions:
            nanonisException occurs when an invalid argument for psStatus is supplied'''
            
        if type(psStatus) is str:
            if psStatus.lower() == 'on':
                psStatus = 1
            elif psStatus.lower() == 'off':
                psStatus = 0
            else:
                raise nanonisException('Point and shoot On or Off?')
        elif type(psStatus) is int:
            if psStatus != 1 and psStatus!=0:
                raise nanonisException('Invalid point and shoot status value, use 0 for off and 1 for on')
        else:
            raise nanonisException('Invalid point and shoot status argument, expected int or string')
            
        self.send('FolMe.PSOnOffSet', 'uint32', psStatus)
        
    def ZCtrlTiplLiftSet(self, tipLift):
        r'''Set the value of the Z controller "tipLift" (the amount the tip moves in Z when Z controller is turned off) 
        
        Args:
             tipLift: float

            
        Exceptions:
            nanonisException occurs if the tipLift value set exceeds the Z scanner range'''
            
        if type(tipLift) is str:
            tipLiftVal = self.convert(tipLift)
        else:
            tipLiftVal = float(tipLift)
        if not (-self.ZScannerLimit <= tipLiftVal <= self.ZScannerLimit):
            raise nanonisException('Z out of bounds')
        self.send('ZCtrl.TipLiftSet', 'float32', tipLiftVal)
        
    def PiezoDriftCompGet(self):
        r''' Get the drift compensation parameters applied to the piezos. Returns a dictionary containing the following:
            Status - bool - Indicates whether drift compensation is on or off
            Vx - float - the linear speed (m/s) applied to the X piezo to compensate the drift
            Vy - float - the linear speed (m/s) applied to the Y piezo to compensate the drift
            Vz - float - the linear speed (m/s) applied to the z piezo to compensate the drift
            Xsat - bool - indicates if X drift correction has reached the limit (default is 10% of piezo range). If reached drift compensation stops for the axis.
            Ysat - bool - indicates if Y drift correction has reached the limit (default is 10% of piezo range). If reached drift compensation stops for the axis.
            Zsat - bool - indicates if Z drift correction has reached the limit (default is 10% of piezo range). If reached drift compensation stops for the axis.
            SatLim - float - the drift saturation limit in percent of the full piezo range and it applies to all axes
            Note, the saturation limit was added as a return argument in September 2022, this command will not work on older versions of Nanonis.
        '''
        parsedResponse = self.parse_response(self.send('Piezo.DriftCompGet'), 'uint32', 'float32', 'float32', 'float32', 'uint32', 'uint32', 'uint32', 'float32')
        if parsedResponse['Error status']:
            raise nanonisException('Error executing PiezoDriftCompGet')
        else:
            return {'Status': parsedResponse['0'], 'Vx': parsedResponse['1'], 'Vy': parsedResponse['2'], 'Vz': parsedResponse['3'], 'Xsat': bool(parsedResponse['4']), 'Ysat': bool(parsedResponse['5']), 'Zsat': bool(parsedResponse['6']), 'SatLim': bool(parsedResponse['7'])}
        
    def PiezoDriftCompSet(self, on, Vxyz, satLim=10):
        r''' Set the drift compensation parameters applied to the piezos.
            
            Args:
                 on : int - Activates or deactivates the drift compensation - (-1 = no change, 0 = off, 1 = on)
                 Vxyz : [float, float, float] - list of the linear speeds (m/s) applied to the X, Y an Z piezos to compensate the drift
                 satLim: float - the drift saturation limit in percent of the full piezo range and it applies to all axes - default 10%
        '''
        #Convert Vxyz values if input as strings
        for Vn, i in enumerate(Vxyz):
            if type(Vn) is str:
                Vxyz[i] = self.convert(Vn)
        
        self.send('Piezo.DriftCompSet', 'int', on, 'float32', Vxyz[0], 'float32', Vxyz[1], 'float32', Vxyz[2], 'float32', satLim)
        
    def ZSpectrPropsGet(self):
        r'''
        Get the Z Spectroscopy parameters.
        
        Args:
            None
            
        Returns a dictionary containing the following:
            backwardSweep - int - indicates if backward sweep is performed (1 for yes, 0 for no)
            numPoints - int - number of points to acquire over the sweep range
            channels - list - names of the acquired channels in the sweep
            parameters - list - parameters of the sweep
            fixedParameters - list - fixed parameters of the sweep
            numSweeps - int - number of sweeps to measure and average
            saveAll - int - indicates if data from individual sweeps is saved along with the average data (1 for yes, 0 for no)
            
        Raises:
            nanonisException - if there is an error executing the command
        '''
        parsedResponse = self.parse_response(self.send('ZSpectr.PropsGet'), 'uint16', 'int', 'string', 'string', 'string', 'uint16', 'uint16')
        
        # Check if an error has been returned
        if parsedResponse['Error status']:
            raise nanonisException('Error executing ZSpectrPropsGet')
        else:
            # Parse the channels, parameters, and fixed parameters arrays
            channels = parsedResponse['2'].split('\n')
            parameters = parsedResponse['3'].split('\n')
            fixedParameters = parsedResponse['4'].split('\n')
            
            return {
                'backwardSweep': parsedResponse['0'],
                'numPoints': parsedResponse['1'],
                'channels': channels,
                'parameters': parameters,
                'fixedParameters': fixedParameters,
                'numSweeps': parsedResponse['5'],
                'saveAll': parsedResponse['6']
            }
