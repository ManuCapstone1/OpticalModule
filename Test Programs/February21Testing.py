import pyfirmata
import time
import cv2
from picamera2 import Picamera2, Preview
	

# Constants
STEPDISTXY = 0.1984
STEPDISTZ = 0.01
PULSEWIDTH = 100 / 1000000.0 # microseconds
BTWNSTEPS = 1000 / 1000000.0

board = pyfirmata.Arduino('/dev/ttyUSB0') # replace with arduino path info
# cam = Picamera2(0)
# camera_config = cam.create_still_configuration({"size":(1920, 1080)})
# cam.configure(camera_config)

it = pyfirmata.util.Iterator(board)
it.start()

currX = 0
currY = 0
currZ = 0

# CNC Shield Arduino pins
enPin = board.get_pin('d:8:o') 
stepAPin = board.get_pin('d:2:o') # CNC shield X-slot
dirAPin = board.get_pin('d:5:o')
stepBPin = board.get_pin('d:3:o') # CNC shield Y-slot
dirBPin = board.get_pin('d:6:o')
stepZPin = board.get_pin('d:4:o')
dirZPin = board.get_pin('d:7:o')
limitSwitchX = board.get_pin('d:9:i')
limitSwitchY = board.get_pin('d:10:i')
limitSwitchZ = board.get_pin('d:11:i')

# Enable pullup resistors for limit switch pins


# Moves A and B belts by specified distances
def move_ab(deltaA: int, deltaB: int):
    steps = abs(round(deltaA / STEPDISTXY))
    print(steps)
    if deltaA >= 0:
        dirAPin.write(1)
    else:
        dirAPin.write(0)

    if deltaB >= 0:
        dirBPin.write(1)
    else:
        dirBPin.write(0)

    for i in range(steps):
        stepAPin.write(1)
        stepBPin.write(1)
        time.sleep(PULSEWIDTH)
        stepAPin.write(0)
        stepBPin.write(0)
        time.sleep(BTWNSTEPS)

# Moves carriage in x by a given linear distance (mm)
def move_x(deltaX=0):
    global currX
    deltaA = -deltaX
    deltaB = -deltaX
    currX = currX + deltaX 
    
    move_ab(deltaA, deltaB)

# Moves carriage in y by a given linear distance (mm)
def move_y(deltaY=0):
    global currY
    deltaA = -deltaY
    deltaB = deltaY
    currY = currY + deltaY
    
    move_ab(deltaA, deltaB)

# Moves platform in z by a given liner distance (mm)
def move_z(deltaZ=0):
    global currZ
    steps = abs(round(deltaZ / STEPDISTZ))
    currZ = currZ + deltaZ
    
    if deltaZ >= 0:
        dirZPin.write(1)
    else:
        dirZPin.write(0)

    for i in range(steps):
        stepZPin.write(1)
        time.sleep(PULSEWIDTH)
        stepZPin.write(0)
        time.sleep(BTWNSTEPS)
    

# Home all axes (sends carriage to back left corner)
def home_all():
    global currX, currY, currZ
	
    # Home X
    dirAPin.write(1)
    dirBPin.write(1)
    while not limitSwitchX.read():
        stepAPin.write(1)
        stepBPin.write(1)
        time.sleep(PULSEWIDTH)
        stepAPin.write(0)
        stepBPin.write(0)
        time.sleep(BTWNSTEPS)
    currX = 0

    # Home Y
    dirAPin.write(1)
    dirBPin.write(0)
    while not limitSwitchY.read():
        stepAPin.write(1)
        stepBPin.write(1)
        time.sleep(PULSEWIDTH)
        stepAPin.write(0)
        stepBPin.write(0)
        time.sleep(BTWNSTEPS)
    currY = 0

    # Home Z
    dirZPin.write(0)
    while not limitSwitchZ.read():
        stepZPin.write(1)
        time.sleep(PULSEWIDTH)
        stepZPin.write(0)
        time.sleep(BTWNSTEPS)
    currZ = 0

# Returns image from camera in array format
#def get_image_array(cam: Camera) -> any:

	#cam.start()
	#array = cam.capture_array("main")
	#cam.stop()

	#return array

# Moves camera to a specified coordinate position
def go_to(x=currX, y=currY, z=currZ):
    global currX, currY, currZ
	
    if not x == currX:
        move_x(x-currX)

    if not y == currY:
        move_y(y-currY)

    if not z == currZ:
        move_z(z-currZ)

# Finds and moves the platform to the best focus position 

    
    
if __name__ == "__main__":
    print('hello ')
    enPin.write(0)
    
    while True:
        print(limitSwitchX.read())
        time.sleep(0.5)
    

    print('hello')
