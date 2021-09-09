# The nanonis_programming_interface initializes a socket connection
# to Nanonis, allowing the user to send commands to Nanonis through
# a TCP/IP connection.

# This module is compatible with Python 2 and Python 3.

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

# Converts a ([A-Fa-f0-9]{2})* string to a sequence of bytes
def decode_hex_from_string(input_string):
    if python_major_version == 2:
        return input_string.decode('hex')
    elif python_major_version == 3:
        return bytes.fromhex(input_string)
    else:
        raise nanonisException('Unknown Python version')

# Converts input_data to a sequence of bytes based on the datatype
def to_binary(datatype, input_data):
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

# Converts a sequence of bytes input_data into a Python string, int, or float
def from_binary(datatype, input_data):
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

# Builds a 40 byte header with the Nanonis command name and body size in bytes
def construct_header(command_name, body_size, send_response_back = True):
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

# Builds the sequence of bytes to send to Nanonis.
# This function takes an odd number of arguments. The first argument is the command name.
# The following arguments come in pairs: a string specifying the data type, the value of the data.
def construct_command(command_name, *vargs):
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
    
    # By default, nanonis_programming_interface connects to port 6501 on the localhost.
    # Optional keyword IP is used to specify Nanonis software running on a different computer on the network.
    # Nanonis can only serve one client per port. If a port is being used, use 6502, 6503, or 6504.
    # If multiple clients connect to Nanonis, Nanonis will silently ignore the second or later connections.
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

    # Send a command to Nanonis.
    # This method takes an odd number of arguments (not including self). The first argument is the command name.
    # The following arguments come in pairs: a string specifying the data type, the value of the data.
    def send(self, command_name, *vargs):
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
    
    # nanonis_programming_interface.parse_response takes as its first argument the return value of nanonis_programming_interface.send
    # The following arguments are the data types of the information included in the body of the response message, not including the error message.
    # This method returns a dictionary with the response information and error information.
    # Note that the keys of the returned dictionary are strings of integers, not integers!
    @staticmethod
    def parse_response(response, *vargs):
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

    # Converts a number followed by an SI prefix into number * 10^{prefix exponent}
    def convert(self, input_data):
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
    
    # Set the Bias (V)
    def BiasSet(self, bias):
        if type(bias) is str:
            bias_val = self.convert(bias)
        else:
            bias_val = float(bias)
        if -self.BiasLimit <= bias_val <= self.BiasLimit:
            self.send('Bias.Set', 'float32', bias_val)
        else:
            raise nanonisException('Bias out of bounds')
    
    # Get the Bias (V)
    def BiasGet(self):
        return self.parse_response(self.send('Bias.Get'), 'float32')['0']

    # Set the X, Y tip coordinates (m)
    # By default, this method blocks until the tip is done moving.
    # Set wait = 0 to return immediately instead of blocking. Does not "scrub" wait parameter for invalid input.
    def TipXYSet(self, X, Y, wait = 1):
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

    # Returns a dictionary containing the X, Y tip coordinates (m)
    def TipXYGet(self, wait = 1):
        parsedResponse = self.parse_response(self.send('FolMe.XYPosGet', 'uint32', wait), 'float64', 'float64')
        return {'X': parsedResponse['0'], 'Y': parsedResponse['1']}

    # Set the Z tip height (m)
    def TipZSet(self, Z):
        if type(Z) is str:
            Z_val = self.convert(Z)
        else:
            Z_val = float(Z)
        if not (-self.ZScannerLimit <= Z_val <= self.ZScannerLimit):
            raise nanonisException('Z out of bounds')
        self.send('ZCtrl.ZPosSet', 'float32', Z_val)

    # Get the Z tip height (m)
    def TipZGet(self):
        parsedResponse = self.parse_response(self.send('ZCtrl.ZPosGet'), 'float32')['0']
        return parsedResponse

    # Turn on/off the Z-controller feedback
    # feedbackStatus can be 'On'/1 or 'Off'/0
    def FeedbackOnOffSet(self, feedbackStatus):
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

    # Returns the Z-controller feedback status as a string ('On' or 'Off')
    def FeedbackOnOffGet(self):
        parsedResponse = self.parse_response(self.send('ZCtrl.OnOffGet'), 'uint32')['0']
        if parsedResponse == 1:
            return 'On'
        elif parsedResponse == 0:
            return 'Off'
        else:
            raise nanonisException('Unknown Feedback State')

    # Turn off the feedback and fully withdraw the tip.
    # By default, this method blocks until the tip is fully withdrawn or timeout (ms) is exceeded.
    # timeout = -1 is infinite timeout.
    def Withdraw(self, wait = 1, timeout = -1):
        self.send('ZCtrl.Withdraw', 'uint32', wait, 'int', timeout)

    # Turn off feedback and move the tip to the Home position.
    def Home(self):
        self.send('ZCtrl.Home')

    # Set the setpoint value (usually the setpoint current (A))
    def SetpointSet(self, setpoint):
        if type(setpoint) is str:
            setpoint_val = self.convert(setpoint)
        else:
            setpoint_val = float(setpoint)
        if not (self.LowerSetpointLimit <= setpoint_val <= self.UpperSetpointLimit):
            raise nanonisException('Setpoint out of bounds')
        self.send('ZCtrl.SetpntSet', 'float32', setpoint_val)

    # Get the setpoint value (usually the setpoint current (A))
    def SetpointGet(self):
        parsedResponse = self.parse_response(self.send('ZCtrl.SetpntGet'), 'float32')['0']
        return parsedResponse

    # Get the value of the current (A)
    def CurrentGet(self):
        parsedResponse = self.parse_response(self.send('Current.Get'), 'float32')['0']
        return parsedResponse