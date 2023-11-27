# nanonis_control

Software for controlling SPECS Nanonis. Tested for Nanonis V5 R12671. Originally written to work with Python 2.7 and Python 3 but more recent functions have only been tested in python 3.

The main component of this package is nanonis_tcp.py, which contains a class named nanonis_programming_interface, which allows easy control of Nanonis through TCP/IP.
To find a full list of commands, download the documentation for the nanonis TCP interface from specs. 

To use nanonis_programming_interface, create an instance:
```
nanonis = nanonis_programming_interface(IP = '127.0.0.1', PORT = 6501)
```

Then send a command to Nanonis through the send method. For example, to set the bias to -1:
```
nanonis.send('Bias.Set', 'float32', -1.0)
```

Here, 'Bias.Set' is the name of the command, 'float32' is the data type, and -1.0 is the desired value.

Or as a shortcut, some commands have been built into nanonis_programming_interface as python functions e.g.:
```
nanonis.BiasSet(-1.0) # Set the bias to -1.0 V
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

To further demonstrate how the interface works, a script "atom_tracking_script.py" has been included, which uses the atom tracking module in nanonis to record a series of images,
correcting for drift after each one. 