import pyfirmata
import time
import cv2
from picamera2 import Picamera2, Preview
import threading
import os
import random

# Constants
STEPDISTXY = 0.212058
STEPDISTZ = 0.01
PULSEWIDTH = 100 / 1000000.0 # microseconds
BTWNSTEPS = 1000 / 1000000.0

class OpticalModule:
    """
        This class...
    """
    def __init__(self):
        self.board=pyfirmata.Arduino("/dev/ttyUSB0")
        # CNC Shield Arduino pins
        self.enPin = self.board.get_pin('d:8:o') 
        self.enPin.write(0)
        self.motorA = StepperMotor(2, 5, self.board)
        self.motorB = StepperMotor(3, 6, self.board)
        self.motorZ = StepperMotor(4, 7, self.board)
        
        self.eStop = True
        self.limitSwitchX = LimitSwitch(9, self.board)
        self.limitSwitchY = LimitSwitch(10, self.board)
        self.limitSwitchZ = LimitSwitch(11, self.board)

        # Create Camera
        self.cam = Picamera2(0)
        self.camera_config = self.cam.create_still_configuration({"size":(1920, 1080)})
        self.cam.configure(self.camera_config)
        self.saveDir = "/home/microscope/images"

        # Create variables to hold current position in terms of steps
        self.currX = 0 
        self.currY = 0
        self.CurrZ = 0

        self.currSample = None

    def add_sample(self, sampleID, sampleHeight, mmPerLayer):
        self.currSample = Sample(sampleID, sampleHeight, mmPerLayer)

    def move_ab(self, deltaA: int, deltaB: int):
        steps = abs(deltaA)

        if deltaA >= 0:
            self.motorA.dir_pin.write(1)
        else:
            self.motorA.dir_pin.write(0)

        if deltaB >= 0:
            self.motorB.dir_pin.write(1)
        else:
            self.motorB.dir_pin.write(0)

        for i in range(steps):
            self.motorA.step_pin.write(1)
            self.motorB.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorA.step_pin.write(0)
            self.motorB.step_pin.write(0)
            time.sleep(BTWNSTEPS)

    # Moves carriage in x by a given linear distance (mm)
    def move_x(self, deltaX=0):
        deltaA = -deltaX
        deltaB = -deltaX
        self.currX = self.currX + deltaX 
        
        self.move_ab(deltaA, deltaB)

    # Moves carriage in y by a given linear distance (mm)
    def move_y(self,deltaY=0):
        deltaA = -deltaY
        deltaB = deltaY
        self.currY = self.currY + deltaY
        
        self.move_ab(deltaA, deltaB)

    # Moves platform in z by a given liner distance (mm)
    def move_z(self, deltaZ=0):
        steps = abs(deltaZ)
        self.currZ = self.currZ + deltaZ
        
        if deltaZ >= 0:
            self.motorZ.dir_pin.write(1)
        else:
            self.motorZ.dir_pin.write(0)

        for i in range(steps):
            self.motorZ.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorZ.step_pin.write(0)
            time.sleep(BTWNSTEPS)
    
    # Moves camera to a specified coordinate position
    def go_to(self, x=None, y=None, z=None):
        x = round(x/STEPDISTXY) if x is not None else self.currX
        y = round(y/STEPDISTXY) if y is not None else self.currY
        z = round(z/STEPDISTZ) if z is not None else self.currZ
        
        if not x == self.currX:
            self.move_x(x-self.currX)

        if not y == self.currY:
            self.move_y(y-self.currY)

        if not z == self.currZ:
            self.move_z(z-self.currZ)

    def get_curr_pos_mm(self, axis):
        if axis == "x":
            return self.currX*STEPDISTXY
        elif axis == "y":
            return self.currY*STEPDISTXY
        elif axis == "z":
            return self.currZ*STEPDISTZ
        else: return 0

    def home_xy(self):
        print("Y")
        self.motorA.dir_pin.write(1)
        self.motorB.dir_pin.write(0)
        while not self.limitSwitchY.is_pressed():      
            self.motorA.step_pin.write(1)
            self.motorB.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorA.step_pin.write(0)
            self.motorB.step_pin.write(0)
            time.sleep(BTWNSTEPS)
        print("X")
        self.motorA.dir_pin.write(1)
        self.motorB.dir_pin.write(1)
        while not self.limitSwitchX.is_pressed():      
            self.motorA.step_pin.write(1)
            self.motorB.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorA.step_pin.write(0)
            self.motorB.step_pin.write(0)
            time.sleep(BTWNSTEPS)
    
    def home_all(self):
        self.home_xy()

        print("Z")
        self.motorZ.dir_pin.write(0)
        while not self.limitSwitchX.is_pressed():      
            self.motorZ.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorZ.step_pin.write(0)
            time.sleep(BTWNSTEPS)
    # Returns image from camera in array format
    def get_image_array(self) -> any:

        self.cam.start()
        array = self.cam.capture_array("main")
        self.cam.stop()

        return array
    
    def capture_and_save_image(self, dir: str) -> str:
        """
        Captures an image using Picamera2 and saves it to the specified directory.

        :return: The full path of the saved image.
        """
        
        # Ensure the save directory exists
        os.makedirs(dir, exist_ok=True)

        # Generate a unique filename using timestamp
        timestamp = time.strftime("%Y%m%d_%H%M%S")  # Format: YYYYMMDD_HHMMSS
        filename = f"{self.currSample.sampleID}_({self.get_curr_pos_mm("x")},{self.get_curr_pos_mm("y")},{self.get_curr_pos_mm("z")})_{timestamp}.jpg"
        file_path = os.path.join(dir, filename)

        try:
            # Start camera
            self.cam.start()
            time.sleep(0.5)  # Allow camera to adjust

            # Capture image
            image = self.cam.capture_array("main")

            # Convert image to RGB for saving
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # Save image
            cv2.imwrite(file_path, image_rgb)
            print(f"Image saved at: {file_path}")

            # Stop camera
            self.cam.stop()

            return file_path

        except Exception as e:
            print(f"Error capturing image: {e}")
            return ""

    def calculate_focus_score(self, imageArray, blur):

        # Apply filter to image to reduce impact of noise
        imageFiltered = cv2.medianBlur(imageArray, blur)

        # Apply the Laplacian filter to detect edges
        laplacian = cv2.Laplacian(imageFiltered, cv2.CV_64F)

        # Calculate the variance of the Laplacian (a measure of sharpness)
        return laplacian.var()
    
    # Finds and moves the platform to the best focus position 
    def auto_focus(self, zMin, zMax, stepSize, blur):
        bestFocusValue = -1
        bestZPosition = zMin

        # Move from zMin to zMax in steps of stepSize
        for z in range(zMin, zMax + stepSize, stepSize):
            # Move to the current z position using go_to
            self.go_to(z=z)

            # Capture the image array
            imageArray = self.get_image_array()
            focusScore = self.calculate_focus_score(imageArray, blur)

            # Check if this focus value is the best so far
            if focusScore > bestFocusValue:
                bestFocusValue = focusScore
                bestZPosition = z

        # Move to the z position with the best focus using go_to
        self.go_to(z=bestZPosition)

        return bestFocusValue
    
    def random_sampling(self, numImages, saveImages: bool):
        # Create list of captured images
        capturedImages = []
        # Extract x and y coordinates from the bounding box
        x_coords = [point[0] for point in self.currSample.boundingBox]
        y_coords = [point[1] for point in self.currSample.boundingBox]

        # Find the min and max values for x and y
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        

        # Generate n random points within the bounding box
        random_points = [(random.uniform(min_x, max_x), random.uniform(min_y, max_y)) for _ in range(numImages)]

        for point in random_points:
            self.go_to(x=point[0], y=point[1])
            time.sleep(1)
            if saveImages: self.capture_and_save_image(self.saveDir)
            imageArr = self.get_image_array()
            capturedImages.append(cv2.cvtColor(imageArr, cv2.COLOR_BGR2RGB))
        return capturedImages
    
    def execute(self, target, kwargs):
        #still need to add code to take target and key words as arguments
        targetThread = threading.Thread(target=self.move_ab, kwargs={"deltaA": 5, "deltaB": -5}, daemon=True)
        targetThread.start()
        while self.eStop and targetThread.is_alive():
            time.sleep(0.01)
        return
    

class StepperMotor:
    def __init__(self, step_pin, dir_pin, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.board = board
        self.step_pin = board.get_pin(f'd:{step_pin}:o')
        self.dir_pin = board.get_pin(f'd:{dir_pin}:o')



class LimitSwitch:
    def __init__(self, pin, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.board = board
        self.board.digital[pin].write(1)
        self.pin = self.board.get_pin(f'd:{pin}:i')

    def is_pressed(self):
        """Returns True if the switch is triggered."""
        if self.pin.read() == 0:
            self.pin.mode() = 1
            self.pin.write(1)
            self.pin.mode() = 0
        return self.pin.read() == 0 

class Sample:
    def __init__(self, sampleID, sampleHeight, mmPerLayer):
        self.sampleID = sampleID
        self.mmPerLayer = mmPerLayer
        self.sampleHeight = sampleHeight
        self.boundingBox = [(0,0), (0,0), (0,0), (0,0)]
        self.boundingIsSet = False

        self.currLayer = 0

    def set_bounding_box(self, coordsList):
        self.boundingBox = coordsList
        self.boundingIsSet = True

    def get_curr_height(self):
        return self.sampleHeight - (self.mmPerLayer * self.currLayer)