#

import socket
import sys
import atexit
import struct

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
    if python_major_version == 2:
        return input_string.decode('hex')
    elif python_major_version == 3:
        return bytes.fromhex(input_string)
    else:
        raise nanonisException('Unknown Python version')

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

def construct_header(command_name, body_size, send_response_back = True):
    cmd_name_bytes = to_binary('string', command_name)
    len_cmd_name_bytes = len(cmd_name_bytes)
    cmd_name_bytes += b'\0' * (32 - len_cmd_name_bytes)
    if send_response_back:
        response_flag = b'\x00\x01'
    else:
        response_flag = b'\0\0'
    header = cmd_name_bytes + \
             to_binary('int', body_size) + \
             response_flag + b'\0\0'
    return header

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

    def __init__(self, IP = '127.0.0.1', PORT = 6501):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((IP, PORT))
        self.lock = thread.allocate_lock()

        @atexit.register
        def exit_handler():
            self.close()

    def close(self):
        self.socket.close()

    def transmit(self, message):
        self.socket.sendall(message)
        return self.socket.recv(1024)

    def send(self, command_name, *vargs):
        try:
            self.lock.acquire()
            response = self.transmit(construct_command(command_name, *vargs))
            returned_command = from_binary('string', response[:32])
            body_size = from_binary('int', response[32:36])
            body = response[40:]
            if body_size != len(body):
                errorMessage = 'Response body size error: ' + \
                                returned_command + ', ' + \
                                str(body_size) + ', ' + \
                                from_binary('string', body)
                raise nanonisException(errorMessage)
        except:
            raise
        finally:
            self.lock.release()
        return {'command_name':returned_command, \
                'body_size':body_size, \
                'body':body \
                }
    
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
        return parsed

    def BiasSet(self, bias):
        if -10 <= float(bias) <= 10:
            self.send('Bias.Set', 'float32', float(bias))
        else:
            raise nanonisException('Bias out of bounds')
    
    def BiasGet(self):
        return self.parse_response(self.send('Bias.Get'), 'float32')['0']

    def TipXYSet(self, X, Y, wait = 1):
        if not (-1e-6 <= float(X) <= 1e-6):
            raise nanonisException('X out of bounds')
        if not (-1e-6 <= float(Y) <= 1e-6):
            raise nanonisException('Y out of bounds')
        self.send('FolMe.XYPosSet', 'float64', float(X), 'float64', float(Y), 'uint32', wait)

    def TipXYGet(self, wait = 1):
        parsedResponse = self.parse_response(self.send('FolMe.XYPosGet', 'uint32', wait), 'float64', 'float64')
        return {'X': parsedResponse['0'], 'Y': parsedResponse['1']}