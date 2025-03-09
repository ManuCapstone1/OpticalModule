import pyfirmata
import time
#import cv2
#from picamera2 import Picamera2, Preview
import threading

# Constants
STEPDISTXY = 0.212058
STEPDISTZ = 0.01
PULSEWIDTH = 100 / 1000000.0 # microseconds
BTWNSTEPS = 1000 / 1000000.0

class OpticalModule:
    def __init__(self):
        self.board=pyfirmata.Arduino("/dev/ttyUSB0")
        # CNC Shield Arduino pins
        self.enPin = self.board.get_pin('d:8:o') 
        self.enPin.write(0)
        self.stepAPin = self.board.get_pin('d:2:o') # CNC shield X-slot
        self.dirAPin = self.board.get_pin('d:5:o')
        self.stepBPin = self.board.get_pin('d:3:o') # CNC shield Y-slot
        self.dirBPin = self.board.get_pin('d:6:o')
        self.stepZPin = self.board.get_pin('d:4:o')
        self.dirZPin = self.board.get_pin('d:7:o')
        self.eStop = True
        # Enable pullup resistors for limit switch pins
        for i in range(9,12):
            self.board.digital[i].write(1)

        self.limitSwitchX = self.board.get_pin('d:9:i')
        self.limitSwitchY = self.board.get_pin('d:10:i')
        self.limitSwitchZ = self.board.get_pin('d:11:i')

    def move_ab(self, deltaA: int, deltaB: int):
        steps = abs(round(deltaA / STEPDISTXY))

        if deltaA >= 0:
            self.dirAPin.write(1)
        else:
            self.dirAPin.write(0)

        if deltaB >= 0:
            self.dirBPin.write(1)
        else:
            self.dirBPin.write(0)

        for i in range(steps):
            self.stepAPin.write(1)
            self.stepBPin.write(1)
            time.sleep(PULSEWIDTH)
            self.stepAPin.write(0)
            self.stepBPin.write(0)
            time.sleep(BTWNSTEPS)

    def execute(self, target, kwargs):
        #still need to add code to take target and key words as arguments
        targetThread = threading.Thread(target=self.move_ab, kwargs={"deltaA": 5, "deltaB": -5}, daemon=True)
        targetThread.start()
        while self.eStop and targetThread.is_alive():
            time.sleep(0.01)
        return

    