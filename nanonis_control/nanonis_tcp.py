r'''
The nanonis_programming_interface class initializes a socket connection
to Nanonis, allowing the user to send commands to Nanonis through a
TCP/IP connection.
'''

import socket
import sys
import atexit
import struct

# Defines data types and their sizes in bytes
datatype_dict = {'int':'>i', \
                 'uint16':'>H', \
                 'uint32':'>I', \
                 'float32':'>f', \
                 'float64':'>d' \
                }
datasize_dict = {'int':4, \
                 'uint16':2, \
                 'uint32':4, \
                 'float32':4, \
                 'float64':8 \
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
            datatype = arg
            body_size += datasize_dict[datatype]
        else:
            body += to_binary(datatype, arg)
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