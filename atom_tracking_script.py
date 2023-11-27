# -*- coding: utf-8 -*-
"""
Created on Fri May 26 10:09:19 2023
This is a simple script for obtaining a sequence of SPM images in a row, using atom tracking between each image to correct
the drift. To use the script, the nanonis software must be running, with the tip locked onto a surface feature using the atom
tracking tool. It is preferable to have the drift as corrected as possible before starting the script. The script can be run in
constant height mode, where the script will perform a sequence of constant height images defined by the step size and start/end
heights defined below. It can also be run in constant current mode by selecting zCtrlOn. The script will run indefinitely
if the latter is selected.

After each image, the script puts the tip back in tracking, calculates how much the tracking position has moved since the last 
tracking event and then adjusts the drift compensation and scan window position accordingly. The script will use the parameters 
set when the script is started for tracking but a different bias is set in the script for imaging. 

While running, the script plots a graph of the drift vectors in X, Y and Z.
@author: phypbl
"""

import numpy as np
import scipy
import sys
import os
import time
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

##Add the path to the nanonis control files##
dir_cwd = os.getcwd() #Get the current directory name
dir_nanonis = os.path.join(dir_cwd, 'nanonis_control') #Get the path to one with the nanonis_tcp.py file
sys.path.append(dir_nanonis) #Add the new directory to the system paths

#import the nanonis API
import nanonis_tcp 

"""User defined variables"""

startHeight = 0 #Tip height (m) in first image
endHeight = '-400p' #Tip height (m) in final image
stepSize = '-100p' #Step size (m) between images
imagingBias = '10m' #Bias (V) used when imaging
t_tracking = 10 #Time (s) spent in tracking for drift measurements
t_wait = 2 #Delay in tracking (s) before measureing drift
moveHeight = '100p' #Height (m) of tip when moving the tip in X and Y (not during image)
biasSlew = 1 #Max slew rate (V/s) when changing the bias
zCtrlOn = True #Set whether to image in feedback or not. Script will run indefinitely if set to True.

#Connection parameters
ip = '127.0.0.1' #IP address of the nanonis controller
port = 6501 #Port on the nanonis controller to connect to - Options are 6501-6504. Controller can maintain up to four connections simultaneously

#Attributes to feed to the API - these act as safeguards to prevent nonsensical values being communicated to the software
biasLimit = 10
lowerSetpointLimit = 0
upperSetpointLimit = 100e-9

"""Setting up the connection"""

#Create an instance of the nanonis control interface
nanonis = nanonis_tcp.nanonis_programming_interface(IP=ip, PORT=port)

piezoRange = nanonis.parse_response(nanonis.send('Piezo.RangeGet'), 'float32', 'float32', 'float32') #This is an example of using a TCP command that hasn't been added as a function to nanonis_tcp.py
#Set all of the atrributes defined above
nanonis.BiasLimit=biasLimit
nanonis.XScannerLimit=piezoRange['0']/2
nanonis.YScannerLimit=piezoRange['1']/2
nanonis.ZScannerLimit=piezoRange['2']/2
nanonis.LowerSetpointLimit=lowerSetpointLimit
nanonis.UpperSetpointLimit=upperSetpointLimit

def error_exit(message):
    """
    Function for closing the script in the case of an error
    """
    nanonis.close()
    sys.exit(message)

def getTrackPos(nanonis, t_tracking):
    """
    Function for getting the tracking position. Returns the X,Y and Z positions averaged over time t_tracking as a numpy array.
    Returns the time when the last position was recorded.
    """
    #Get tip positions and create an array
    zPos = nanonis.TipZGet()
    xyPos = nanonis.TipXYGet()
    tipPos = np.array([xyPos['X'], xyPos['Y'], zPos], ndmin=2)

    #Get the start time
    startTime = time.time()

    while True:
        currentTime = time.time()
        elapsedTime = currentTime - startTime
        zPos = nanonis.TipZGet()
        xyPos = nanonis.TipXYGet()
        tipPos = np.append(tipPos, [[xyPos['X'], xyPos['Y'], zPos]], axis=0)
        
        if elapsedTime >= t_tracking:
            break
    avgTipPos = tipPos.mean(axis=0)
    return avgTipPos, currentTime

def slowBiasChange(nanonis, newBias, slewRate, tStep=0.01):
    """
    Function for changing the bias in nanonis with a maximum slew rate
    
    Parameters
    ----------
    nanonis : instance of the nanonis class that handles the TCP communication
    newBias : float - target bias to be set by the function (V)
    slewRate : float - maximum slew rate when setting the bias (V/s)
    tStep : float - optional - Time step between increments in the set bias (s) The default is 0.01 s

    Returns
    -------
    None.

    """
    if type(newBias) == str:
        newBias = nanonis.convert(newBias)
    if type(slewRate) == str:
        slewRate = nanonis.convert(slewRate)
    
    if slewRate == 0:
        print('Voltage slew rate was set to zero, using value of 0.1 V per second instead')
        slewRate = 0.1
    currBias = nanonis.BiasGet() #Get the starting bias
    biasChange = newBias-currBias #Get the change in bias
    if biasChange != 0: #Check that the bias needs changing  
        biasStep = slewRate*tStep*np.sign(biasChange) #Set the biasStep with the correct sign
        nSteps = int(abs(biasChange//biasStep)) #Determine the size of each step required to obtain the slew rate with tStep steps
        for _i in range(nSteps):     #Create a loop to deal with the bias change
            bias = currBias+biasStep*(_i+1)
            nanonis.BiasSet(bias) #Change the bias to the new value
            time.sleep(tStep)
        nanonis.BiasSet(newBias)#Final step in case a non-integer number of steps is required
    

"""Start of script"""

#Check that atom tracking is on
modStatus = nanonis.AtomTrackStatusGet('modulation')
ctrlStatus = nanonis.AtomTrackStatusGet('controller')

#Check to ensure that atom tracking is on at the start of the script
if not modStatus or not ctrlStatus:
    error_exit("Atom tracking was not on at the start, aborting script")

#Get the bias to store as the bias for tracking
biasTrack = nanonis.BiasGet()

#Turn point and shoot off
nanonis.FolMePSOnOffSet('Off')

#Set the initial tip lift value to zero
nanonis.ZCtrlTipLiftSet(0)
#Get the atom tracking properties
atomTrackProps = nanonis.AtomTrackPropsGet()

#Get the intial tracking position
trackPos, trackTime = getTrackPos(nanonis, t_tracking)

#Convert any numbers used for step calculation that are input as strings 
if type(startHeight) == str:
    startHeight = nanonis.convert(startHeight)
if type(endHeight) == str:
    endHeight = nanonis.convert(endHeight)
if type(stepSize) == str:
    stepSize = nanonis.convert(stepSize)
    
#Convert the move height if it is input as string
if type(moveHeight) == str:
    moveHeight = nanonis.convert(moveHeight)

#Calculate the number of steps needed    
nSteps = int((endHeight-startHeight) // stepSize)
if ((endHeight-startHeight) % stepSize)*stepSize <= 1e-12: #If the number of steps is exactly divisible (within numerical error < 1pm), add an additional step on
    nSteps += 1

#Get drift compensation parameters
driftCompParams = nanonis.PiezoDriftCompGet()

#Check the drift compensation parameters
#If the drift is not actively being compensated, set existing drift values to zero
if not driftCompParams['Status']:
    nanonis.PiezoDriftCompSet(1, [0, 0, 0]) #Turns drift compensation on with vectors set to zero
    #Get the drift compensation parameters again
    driftCompParams = nanonis.PiezoDriftCompGet()

#Set up plot for showing drift compensation
# Create empty lists to store data
tData = []
xData = []
yData = []
zData = []

# Enable interactive plotting mode
plt.ion()

# Set up the figure and axes
fig, ax = plt.subplots()
line1, = ax.plot(tData, xData, 'r-', label='X drift')
line2, = ax.plot(tData, yData, 'g-', label='Y drift')
line3, = ax.plot(tData, zData, 'b-', label='Z drift')
ax.legend()
plt.ylabel("Drift [pm/s]")
plt.xlabel("Time")
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S')) # Format the x axis to take timestamps
plt.gcf().autofmt_xdate(rotation=45)
plt.tight_layout()

"""Main for loop"""

for i in range(nSteps):
    #Determine the offset height for the current step
    zOffset = startHeight+stepSize*i
    
    #Turn off atom tracking by turning the controller and then the modulation
    nanonis.AtomTrackCtrlSet('controller', 'off')
    time.sleep(atomTrackProps['soDelay']+0.1) #Wait for the switch off delay to take effect (additional 0.1 to ensure that the switch off is complete before moving on)
    nanonis.AtomTrackCtrlSet('modulation', 'off')
    time.sleep(1) #Wait one second to allow the tip to be in the centre of the tracking modulation before moving on - Change this time to be set by amplitude and scan speed
    
    #Turn off the Z controller if taking constant height
    if not zCtrlOn:
        nanonis.FeedbackOnOffSet('off')
    
    #Change the bias to the imaging bias
    slowBiasChange(nanonis, imagingBias, biasSlew)
    
    #Set the tip to the moving height if constant height imaging
    if not zCtrlOn:
        #Get the Z height and then add on the move height
        zZero = nanonis.TipZGet()
        zMove = zZero + moveHeight
        #Set z to the move height
        nanonis.TipZSet(zMove)      
    
    #Get the scan frame parameters
    scanFrame = nanonis.ScanFrameGet()
    scanFrameXY = scanFrame['centre']
    scanFrameSize = scanFrame['size']
    scanFrameAngle = (scanFrame['angle']*np.pi)/180 #Get the scan angle in radians
    
    #Determine the scan frame origin. The line below handles relevant trigonometry to get the scan frame origin from scan dimensions and centre.
    scanFrameOrigin = [scanFrameXY[0]+(((-scanFrameSize[0]/2)*np.cos(scanFrameAngle))+(-scanFrameSize[1]/2)*np.sin(scanFrameAngle)), scanFrameXY[1]+(((scanFrameSize[0]/2)*np.sin(scanFrameAngle))+(-scanFrameSize[1]/2)*np.cos(scanFrameAngle))]
    
    #Move to the scan frame origin
    nanonis.TipXYSet(scanFrameOrigin[0], scanFrameOrigin[1])
    
    #Set the tip to the imaging height if constant height imaging
    if not zCtrlOn:
        #Get the Z height and then add on the move height
        zImage = zZero + zOffset
        #Set z to the move height
        nanonis.TipZSet(zImage)
        #Set the tip lift value to match the current zOffset
        nanonis.ZCtrlTipLiftSet(zOffset)  
    
    #Start the scan and wait for it to finish
    nanonis.ScanAction(0, 1)
    nanonis.ScanWaitEndOfScan()
    
    #Set the tip to the moving height if constant height imaging
    if not zCtrlOn:
        nanonis.TipZSet(zMove)
    
    #Move back to the tracking position
    nanonis.TipXYSet(trackPos[0], trackPos[1])
    #Change the bias back to the tracking bias
    slowBiasChange(nanonis, biasTrack, biasSlew)
    #Turn on the Z-controller if constant height imaging
    if not zCtrlOn:
        nanonis.FeedbackOnOffSet('on')
        #Reset tip lift to zero
        nanonis.ZCtrlTipLiftSet(0)
    
    #Turn on atom tracking (turning the controller on also turns modulation on)
    nanonis.AtomTrackCtrlSet('controller', 'on')
    time.sleep(t_wait) #Wait the appropriate amount of time for tracking to settle (defined by user)
    #Get the new tracking position
    newTrackPos, newTrackTime = getTrackPos(nanonis, t_tracking)
    
    #Correct for drift
    drift = (newTrackPos-trackPos)/(newTrackTime-trackTime) #Get an array of drift values (m/s) in the three dimensions
    driftComp = [driftCompParams['Vx']+drift[0], driftCompParams['Vy']+drift[1], driftCompParams['Vz']+drift[2]] #Create a list of the new drift parameters
    nanonis.PiezoDriftCompSet(1, driftComp, satLim=10)
    
    #Get the new drift compensation parameters
    driftCompParams = nanonis.PiezoDriftCompGet()
    #Set the current tracking position and time as the new tracking position and time
    trackPos = newTrackPos
    trackTime = newTrackTime
    
    #For testing, print out the current tracking and drift parameters
    print(trackTime)
    print(driftComp)
    print(trackPos)
    
    #Put new data into the drift compensation data list - converting to pm/s
    tData.append(datetime.fromtimestamp(trackTime))
    xData.append(driftComp[0]*1e12)
    yData.append(driftComp[1]*1e12)
    zData.append(driftComp[2]*1e12)
    
    # Update the plot with the new data
    line1.set_data(tData, xData)
    line2.set_data(tData, yData)
    line3.set_data(tData, zData)

    # Adjust the plot limits if necessary
    ax.relim()
    ax.autoscale_view()

    # Redraw the plot
    plt.draw()
    plt.pause(0.1)  # Adjust the pause duration as needed - This was added so that the plot would not freeze
    
#Small script for getting and setting a new tip position
# tipPos = nanonis.TipXYGet()
# newPos = [tipPos['X']+10e-9, tipPos['Y']+10e-9]
# nanonis.TipXYSet(newPos[0], newPos[1])

#Close the connection to the Nanonis controller so following scripts will run properly
nanonis.close()