import pyfirmata
import time
import cv2


# Constants
STEPDISTXY = 0.212058
STEPDISTZ = 0.01
PULSEWIDTH = 50 / 1000000.0 # microseconds
BTWNSTEPS = 150 / 1000000.0

board = pyfirmata.Arduino('/dev/ttyUSB0') # replace with arduino path info


currX = 0
currY = 0
currZ = 0

# CNC Shield Arduino pins
enPin = board.get_pin('d:8:o') 
enPin.write(0)
stepAPin = board.get_pin('d:2:o') # CNC shield X-slot
dirAPin = board.get_pin('d:5:o')
stepBPin = board.get_pin('d:3:o') # CNC shield Y-slot
dirBPin = board.get_pin('d:6:o')
stepZPin = board.get_pin('d:4:o')
dirZPin = board.get_pin('d:7:o')
board.digital[9].write(1)
board.digital[10].write(1)
board.digital[11].write(1)
limitSwitchX = board.get_pin('d:9:i')
limitSwitchY = board.get_pin('d:10:i')
limitSwitchZ = board.get_pin('d:11:i')

# Home all axes (sends carriage to back left corner)
def home_all():
    # Start an iterator thread to prevent buffer overflow
    it = pyfirmata.util.Iterator(board)
    it.start()
    
    time.sleep(0.5)
    
    while limitSwitchY.read():
        
        print("Y")
        dirAPin.write(1)
        dirBPin.write(0)
                
        stepAPin.write(1)
        stepBPin.write(1)
        time.sleep(PULSEWIDTH)
        stepAPin.write(0)
        stepBPin.write(0)
        time.sleep(BTWNSTEPS)



    if limitSwitchY.read() is False:  # If the pin is LOW (triggered)
        # print("Pin triggered! Resetting to HIGH...")
        # Reset the pin to HIGH (manually write HIGH to the pin)
        limitSwitchY.mode = 1  # Set pin mode to OUTPUT (1)
        limitSwitchY.write(1)  # Set the pin HIGH to reset it
        limitSwitchY.mode = 0  # Set pin mode back to INPUT_PULLUP (2)
    

    while limitSwitchX.read():
        
        print("X")
        dirAPin.write(1)
        dirBPin.write(1)
                
        stepAPin.write(1)
        stepBPin.write(1)
        time.sleep(PULSEWIDTH)
        stepAPin.write(0)
        stepBPin.write(0)
        time.sleep(BTWNSTEPS)

            

    if limitSwitchX.read() is False:  # If the pin is LOW (triggered)
        # print("Pin triggered! Resetting to HIGH...")
        # Reset the pin to HIGH (manually write HIGH to the pin)
        limitSwitchX.mode = 1  # Set pin mode to OUTPUT (1)
        limitSwitchX.write(1)  # Set the pin HIGH to reset it
        limitSwitchX.mode = 0  # Set pin mode back to INPUT_PULLUP (2)
        
    
    while limitSwitchZ.read():

        print("Z")
        dirZPin.write(0)
        stepZPin.write(1)
        time.sleep(PULSEWIDTH)
        stepZPin.write(0)
        time.sleep(BTWNSTEPS)


    if limitSwitchZ.read() is False:  # If the pin is LOW (triggered)
        # print("Pin triggered! Resetting to HIGH...")
        # Reset the pin to HIGH (manually write HIGH to the pin)
        limitSwitchX.mode = 1  # Set pin mode to OUTPUT (1)
        limitSwitchX.write(1)  # Set the pin HIGH to reset it
        limitSwitchX.mode = 0  # Set pin mode back to INPUT_PULLUP (2)
        
        


if __name__ == "__main__":
    print('hello1')
    home_all()


    
    
