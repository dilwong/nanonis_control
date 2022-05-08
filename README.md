# nanonis_control

Software for controlling SPECS Nanonis. Tested for Nanonis V5 R10811, Python 2.7 and Python 3.

The main component of this package is nanonis_tcp.py, which contains a class named nanonis_programming_interface, which allows easy control of Nanonis through TCP/IP.

To use nanonis_programming_interface, create an instance:
```
nanonis = nanonis_programming_interface(IP = '127.0.0.1', PORT = 6501)
```

Then send a command to Nanonis through the send method. For example, to set the bias to -1:
```
nanonis.send('Bias.Set', 'float32', -1.0)
```

Here, 'Bias.Set' is the name of the command, 'float32' is the data type, and -1.0 is the desired value.

Or as a shortcut:
```
nanonis.BiasSet(-1.0)
nanonis.BiasGet() # Return the value of the bias
```

You can also move the tip to a new location (X = 100 nm, Y = -200 nm):
```
nanonis.TipXYSet(100e-9, -200e-9)
# nanonis.TipXYSet('100n', '-200n') also works
```
Methods such as nanonis_programming_interface.BiasSet and nanonis_programming_interface.TipXYSet accept floats and strings. These methods internally convert a string with a SI prefix attached at the end to a float using nanonis_programming_interface.convert.

Turn on the feedback or withdraw the tip with:
```
nanonis.FeedbackOnOffSet('on')
nanonis.Withdraw()
```

To close the connection:
```
nanonis.close()
```
Or just exit the Python interpreter.