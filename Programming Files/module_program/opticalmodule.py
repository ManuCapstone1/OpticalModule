import pyfirmata
import time
import math
import cv2
import numpy as np
from picamera2 import Picamera2, Preview
import threading
import os
import random
import json

# Constants
STEPDISTXY = 0.212058/16
STEPDISTZ = 0.01/4
PULSEWIDTH = 100 / 1000000.0 # microseconds
BTWNSTEPS = 1000 / 1000000.0
STAGEFOCUSHEIGHT = 36860*STEPDISTZ 
STAGECENTRE = (8281, 7005) # Stage centre location in steps

class OpticalModule:
    """
        This class...
    """
    def __init__(self):
        self.board=pyfirmata.Arduino("/dev/ttyUSB0")
        it = pyfirmata.util.Iterator(self.board)
        it.start()
        
        # CNC Shield Arduino pins
        self.enPin = self.board.get_pin('d:8:o') 
        self.enPin.write(0)
        #self.motorsEnabled = True
        self.motorA = StepperMotor(2, 5, self.board)
        self.motorB = StepperMotor(3, 6, self.board)
        self.motorZ = StepperMotor(4, 7, self.board)
        
        self.limitSwitchX = LimitSwitch(9, self.board)
        self.limitSwitchY = LimitSwitch(10, self.board)
        self.limitSwitchZ = LimitSwitch(11, self.board)

        # Create Camera
        self.cam = Camera()

        # Create variables to hold current position in terms of steps
        self.currX = 0 
        self.currY = 0
        self.currZ = 0
        self.currSample = None

        # Misc variables
        self.totalImages = 0
        self.currImageMetadata = {
            "image_name" : "None",
            "sample_id" : "None",
            "timestamp" : time.strftime("%Y%m%d_%H%M%S"),  # Format: YYYYMMDD_HHMMSS
            "sample_layer" : 0,
            "image_number" : 0,
            "image_x_pos" : 0,
            "image_y_pos" : 0,
            "image_z_pos" : 0,
            "exposure_time" : self.cam.currExposureTime,
            "analog_gain" : self.cam.currAnalogGain,
            "contrast" : self.cam.currContrast,
            "colour_temp" : self.cam.currColourTemp
        }
        #self.isHomed = False
        #self.Stop = False
        #self.resetIdle = False
        self.bufferDir = "/home/microscope/image_buffer"

        # Threading Lock
        self.positionLock = threading.Lock()
        self.cameraLock = threading.Lock()
        self.imageCountLock = threading.Lock()
        #self.homeLock = threading.Lock()
        #self.motorStateLock = threading.Lock()
        self.stop = threading.Event()
        self.resetIdle = threading.Event()
        self.isHomed = threading.Event()
        self.motorsEnabled = threading.Event()

    def add_sample(self, mountType, sampleID, initialHeight, mmPerLayer, width, height):
        self.currSample = Sample(mountType, sampleID, initialHeight, mmPerLayer, width, height)

    def disable_motors(self):
        self.enPin.write(1)
        self.motorsEnabled.clear()
        self.isHomed.clear()

    def enable_motors(self):
        self.enPin.write(0)
        self.motorsEnabled.set()

    def _move_ab(self, deltaA: int, deltaB: int):
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
            if self.stop.is_set():
                self.resetIdle.set()
                self.isHomed.clear()
                return
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
        with self.positionLock:
            self.currX = self.currX + deltaX 
        
        self._move_ab(deltaA, deltaB)

    # Moves carriage in y by a given linear distance (mm)
    def move_y(self,deltaY=0):
        deltaA = -deltaY
        deltaB = deltaY
        with self.positionLock:
            self.currY = self.currY + deltaY
        
        self._move_ab(deltaA, deltaB)

    # Moves platform in z by a given liner distance (mm)
    def move_z(self, deltaZ=0):
        steps = abs(deltaZ)
        self.currZ = self.currZ + deltaZ
        
        if deltaZ >= 0:
            self.motorZ.dir_pin.write(1)
        else:
            self.motorZ.dir_pin.write(0)

        for i in range(steps):
            if self.stop.is_set():
                self.resetIdle.set()
                self.isHomed.clear()
                return
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
            if self.stop.is_set():
                self.resetIdle.set()
                self.isHomed.clear()
                return
            self.motorA.step_pin.write(1)
            self.motorB.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorA.step_pin.write(0)
            self.motorB.step_pin.write(0)
            time.sleep(BTWNSTEPS)
        with self.positionLock:
            self.currY = 0
        print("X")
        self.motorA.dir_pin.write(1)
        self.motorB.dir_pin.write(1)
        while not self.limitSwitchX.is_pressed():
            if self.stop.is_set():
                self.resetIdle.set()
                self.isHomed.clear()
                return      
            self.motorA.step_pin.write(1)
            self.motorB.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorA.step_pin.write(0)
            self.motorB.step_pin.write(0)
            time.sleep(BTWNSTEPS)
        with self.positionLock:
            self.currX = 0
    
    def home_all(self):
        self.stop.clear()
        self.enable_motors()
        self.home_xy()

        print("Z")
        self.motorZ.dir_pin.write(0)
        while not self.limitSwitchZ.is_pressed():
            if self.stop.is_set():
                self.resetIdle.set()
                return      
            self.motorZ.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorZ.step_pin.write(0)
            time.sleep(BTWNSTEPS)
        with self.positionLock:
            self.currZ = 0
            self.isHomed.set()

    # # Returns image from camera in array format
    # def get_image_array(self, updateImage=False) -> any:

    #     self.cam.start()
    #     array = self.cam.capture_array("main")
    #     self.cam.stop()

    #     return array
    
    # def capture_and_save_image(self, dir: str) -> str:
    #     """
    #     Captures an image using Picamera2 and saves it to the specified directory.

    #     :return: The full path of the saved image.
    #     """
        
    #     # Ensure the save directory exists
    #     os.makedirs(dir, exist_ok=True)

    #     # Generate a unique filename using timestamp
    #     timestamp = time.strftime("%Y%m%d_%H%M%S")  # Format: YYYYMMDD_HHMMSS
    #     filename = f"{self.currSample.sampleID}_({self.get_curr_pos_mm('x')},{self.get_curr_pos_mm('y')},{self.get_curr_pos_mm('z')})_{timestamp}.jpg"
    #     file_path = os.path.join(dir, filename)


    #     try:
    #         # Start camera
    #         self.cam.start()
    #         time.sleep(0.5)  # Allow camera to adjust

    #         # Capture image
    #         image = self.cam.capture_array("main")

    #         # Convert image to RGB for saving
    #         image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    #         # Save image
    #         cv2.imwrite(file_path, image_rgb)
    #         print(f"Image saved at: {file_path}")

    #         # Stop camera
    #         self.cam.stop()

    #         return file_path

    #     except Exception as e:
    #         print(f"Error capturing image: {e}")
    #         return ""

    # def calculate_focus_score(self, imageArray, blur):

    #     # Apply filter to image to reduce impact of noise
    #     imageFiltered = cv2.medianBlur(imageArray, blur)

    #     # Apply the Laplacian filter to detect edges
    #     laplacian = cv2.Laplacian(imageFiltered, cv2.CV_64F)

    #     # Calculate the variance of the Laplacian (a measure of sharpness)
    #     #print(laplacian.var())
    #     return laplacian.var()
    
    # Finds and moves the platform to the best focus position 
    def auto_focus(self, zMin=None, zMax=None, stepSize=None, blur=5):
        if zMin is None or zMax is None or stepSize is None:
            zMin = STAGEFOCUSHEIGHT - self.currSample.get_curr_height() - 1
            zMax = STAGEFOCUSHEIGHT - self.currSample.get_curr_height() + 1
            stepSize = 0.05
        bestFocusValue = -1
        bestZPosition = zMin
        zMinMicron = int(zMin*1000)
        zMaxMicron = int(zMax*1000)
        stepSizeMicron = int(stepSize*1000)

        # Move from zMin to zMax in steps of stepSize
        for z in range(zMinMicron, zMaxMicron + stepSizeMicron, stepSizeMicron):
            if self.stop.is_set():
                self.resetIdle.set()
                return
            # Move to the current z position using go_to
            self.go_to(z=z/1000)

            # Get the focus score
            focusScore = self.cam.calculate_focus_score()
            print(focusScore)
            # Check if this focus value is the best so far
            if focusScore > bestFocusValue:
                bestFocusValue = focusScore
                bestZPosition = z/1000

        # Move to the z position with the best focus using go_to
        self.go_to(z=bestZPosition)

        return bestFocusValue
    
    def update_image_metadata(self, save=False):
        self.currImageMetadata["image_name"] = self.cam.currImageName
        self.currImageMetadata["sample_id"] = self.currSample.sampleID
        self.currImageMetadata["timestamp"] = time.strftime("%Y%m%d_%H%M%S")  # Format: YYYYMMDD_HHMMSS
        self.currImageMetadata["sample_layer"] = self.currSample.currLayer
        self.currImageMetadata["image_number"] = self.cam.imageCount
        self.currImageMetadata["image_x_pos"] = self.get_curr_pos_mm('x')
        self.currImageMetadata["image_y_pos"] = self.get_curr_pos_mm('y')
        self.currImageMetadata["image_z_pos"] = self.get_curr_pos_mm('z')
        self.currImageMetadata["exposure_time"] = self.cam.currExposureTime
        self.currImageMetadata["analog_gain"] = self.cam.currAnalogGain
        self.currImageMetadata["contrast"] = self.cam.currContrast
        self.currImageMetadata["colour_temp"] = self.cam.currColourTemp
        if save:
            filepath = os.path.join(self.bufferDir, f"{self.currImageMetadata['image_name']}.txt")
            with open(filepath, "w") as file:
                json.dump(self.currImageMetadata, file, indent=4)

    def update_image(self):
        print("update Image")
        image = self.cam.update_curr_image(self.currSample)
        filename = f"{self.cam.currImageName}.jpg"
        file_path = os.path.join(self.bufferDir, filename)

        # Convert image to RGB for saving
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Save image
        cv2.imwrite(file_path, image_rgb)
        self.update_image_metadata(True)

        return image
    
    def random_sampling(self, numImages, saveImages: bool):
        if self.currSample is None or not self.currSample.boundingIsSet:
            print("Bounding box not set. Cannot take images.")
            return
        
        if not self.isHomed.is_set():
            self.home_all()
        self.go_to(x=STAGECENTRE[0]*STEPDISTXY, y=STAGECENTRE[1]*STEPDISTXY)
        self.auto_focus()
        if self.cam.calculate_focus_score() < 1:
            print("Sample not detected or not in focus")
            return
        with self.imageCountLock:   
            self.totalImages = numImages
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
        with self.imageCountLock:
            self.cam.imageCount = 0
        for point in random_points:
            if self.stop.is_set():
                self.resetIdle.set()
                return
            self.go_to(x=point[0], y=point[1])
            with self.imageCountLock:
                self.cam.imageCount = self.cam.imageCount + 1
            time.sleep(0.5)
            if saveImages: 
                imageArr = self.cam.save_image(self.saveDir, self.currSample)
            else:
                imageArr = self.update_image()
            capturedImages.append(cv2.cvtColor(imageArr, cv2.COLOR_BGR2RGB))
        self.currSample.currLayer = self.currSample.currLayer + 1
        #limit switches need to be reset.
        self.limitSwitchX.is_pressed()
        self.limitSwitchY.is_pressed()
        self.home_xy()
        return capturedImages
    
    def scanning_images(self, step_size_x, step_size_y, saveImages: bool):
        if self.currSample is None or not self.currSample.boundingIsSet:
            print("Bounding box not set. Cannot take images.")
            return
        if self.cam.calculate_focus_score() < 1:
            print("Sample not detected or not in focus")
            return
        if not self.isHomed.is_set():
            self.home_all()
        self.go_to(x=STAGECENTRE[0]*STEPDISTXY, y=STAGECENTRE[1]*STEPDISTXY)
        self.auto_focus()
        capturedImages = []

        x_coords = [point[0] for point in self.currSample.boundingBox]
        y_coords = [point[1] for point in self.currSample.boundingBox]

        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)

        x_positions = list(range(int(min_x), int(max_x) + step_size_x, step_size_x))
        y_positions = list(range(int(min_y), int(max_y) + step_size_y, step_size_y))
        with self.imageCountLock:
            self.totalImages = len(x_positions) * len(y_positions)
            self.cam.imageCount = 0
        for x in x_positions:
            for y in y_positions:
                if self.stop.is_set():
                    self.resetIdle.set()
                    return
                self.go_to(x=x, y=y)
                time.sleep(0.5)  # Allow system to stabilize
                with self.imageCountLock:
                    self.cam.imageCount = self.cam.imageCount + 1
                if saveImages:
                    imageArr = self.cam.save_image(self.saveDir, self.currSample)
                else:    
                    imageArr = self.update_image()
                capturedImages.append(cv2.cvtColor(imageArr, cv2.COLOR_BGR2RGB))              
        self.currSample.currLayer = self.currSample.currLayer + 1
        self.home_xy()
        return capturedImages

    
    def execute(self, targetMethod, **kwargs):
        # Get the target method
        target = getattr(self, targetMethod, None)
        if callable(target):
            targetThread = threading.Thread(target=target, kwargs=kwargs, daemon=True)
            targetThread.start()
            targetThread.join()
            self.resetIdle.set()

            print("here1")
        else:
            raise AttributeError(f"'{type(self).__name__}' has no callable method '{targetMethod}'")

    # This method was written by copilot and still requires testing
    def call_method_from_console(self):
        while True:
            method_name = input("Enter the method name (or 'exit' to quit): ").strip()
            if method_name.lower() == "exit":
                print("Exiting...")
                break

            # Check if the method exists in the class
            if not hasattr(self, method_name):
                print(f"Method '{method_name}' does not exist. Please try again.")
                continue

            method = getattr(self, method_name)
            if callable(method):
                # Get the number of required arguments
                import inspect
                params = inspect.signature(method).parameters
                if params:
                    # Ask the user for each required argument
                    args = []
                    for param in params:
                        user_input = input(f"Enter value for '{param}': ")
                        args.append(user_input)
                    # Call the method with the provided arguments
                    method(*args)
                else:
                    # Call the method directly if it takes no arguments
                    method()
            else:
                print(f"'{method_name}' is not callable. Please try again.")
       

class StepperMotor:
    def __init__(self, step_pin, dir_pin, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.board = board
        self.step_pin = board.get_pin(f'd:{step_pin}:o')
        self.dir_pin = board.get_pin(f'd:{dir_pin}:o')

class Camera:
    def __init__(self):
        # Create Camera
        self.picam = Picamera2(0)
        
        # Create variables for camera settings
        self.currExposureTime = 100000       # Example exposure time in microseconds
        self.currAnalogGain = 2           # Default analogue gain (1.0 = no gain)
        self.currContrast = 1.0             # Default contrast (1.0 is neutral)
        self.currColourTemp = 6000          # Default colour temperature in Kelvin

        # Create camera configuration
        # https://www.raspberrypi.com/documentation/accessories/camera.html
        self.camera_config = self.picam.create_still_configuration({"size":(4056,3040)}) 
        self.picam.configure(self.camera_config)
        self._apply_settings()

        # Misc Variables
        self.currImage = np.array([])
        self.currImageName = "None"
        self.imageCount = 0

        # Thread locking
        self.settingsLock = threading.Lock()
        self.imageLock = threading.Lock()


    def update_settings(self, exposureTime=None, analogGain=None, contrast=None, colourTemperature=None):
        """
        Update the camera settings. For any parameter that is None, the existing setting is maintained.
        
        Parameters:
            exposureTime: New exposure time in microseconds.
            analogGain: New analogue gain (float).
            contrast: New contrast setting.
            colorTemperature: New color temperature in Kelvin.
        """
        with self.settingsLock:
            if exposureTime is not None:
                self.currExposureTime = exposureTime
            if analogGain is not None:
                self.currAnalogGain = analogGain
            if contrast is not None:
                self.currContrast = contrast
            if colourTemperature is not None:
                self.currColourTemp = colourTemperature

        # Re-apply all settings after updates.
        self._apply_settings()

    def _apply_settings(self):
        """
        Convert the current color temperature to ColourGains using the RGB conversion algorithm
        and apply all controls to the camera.
        """
        # Get red and blue gains calculated from the color temperature.
        redGain, blueGain = self._convert_temperature_to_gains(self.currColourTemp)
        
        # Build the controls dictionary.
        controls = {
            "ExposureTime": self.currExposureTime,
            "AnalogueGain": self.currAnalogGain,
            "Contrast": self.currContrast,
        }
        #            "ColourGains": (redGain, blueGain)
        # Apply the controls to the camera.
        self.picam.set_controls(controls)
    
    def update_curr_image(self, sample):
        print("in cam")
        self.update_image_name(sample)
        return self.get_image_array(True)

    def calculate_focus_score(self, imageArray=None, blur=5):

        if imageArray is None:
            imageArray = self.get_image_array()

        # Apply filter to image to reduce impact of noise
        imageFiltered = cv2.medianBlur(imageArray, blur)

        # Apply the Laplacian filter to detect edges
        laplacian = cv2.Laplacian(imageFiltered, cv2.CV_64F)

        # Calculate the variance of the Laplacian (a measure of sharpness)
        #print(laplacian.var())
        return laplacian.var()
    
    def get_image_array(self, updateImage=False) -> any:
        print("getting image arr")
        try:
            self.picam.start()
            array = self.picam.capture_array("main")
            self.picam.stop()

            if updateImage:
                with self.imageLock:
                    self.currImage = array

            return array
        
        except Exception as e:
            print(f"Error capturing image: {e}")
            return ""
    
    def save_image(self, dir: str, sample, image=None) -> str:
        """
        Captures an image using Picamera2 and saves it to the specified directory.

        :return: The full path of the saved image.
        """
        
        # Ensure the save directory exists
        os.makedirs(dir, exist_ok=True)

        # Generate a unique filename using timestamp
        timestamp = time.strftime("%Y%m%d_%H%M%S")  # Format: YYYYMMDD_HHMMSS
        imageName = self.update_image_name(sample)
        filename = f"{imageName}_{timestamp}.jpg"
        file_path = os.path.join(dir, filename)

        try:
            if image is None:
                # Capture image
                image = self.get_image_array(True)

            # Convert image to RGB for saving
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # Save image
            cv2.imwrite(file_path, image_rgb)
            print(f"Image saved at: {file_path}")

            return image

        except Exception as e:
            print(f"Error capturing image: {e}")
            return ""
    def update_image_name(self, sample, imageCount=None):
        if imageCount is None: imageCount = self.imageCount
        imageName = f"{imageCount}_{sample.currLayer}_{sample.sampleID}"
        with self.imageLock:
            self.currImageName = imageName
        return imageName

    def _convert_temperature_to_gains(self, kelvin):
        """
        Convert a given color temperature in Kelvin to a pair of red and blue gain multipliers
        using Tanner Helland's RGB conversion algorithm.
        
        This function calculates the red, green, and blue components corresponding to the
        specified Kelvin temperature. It then normalizes the red and blue values relative to the
        green channel (which is assumed to be at unity gain) to compute the gains.
        
        For more details on the algorithm, see:
        https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html
        
        Parameters:
            kelvin: Color temperature in Kelvin.
            
        Returns:
            A tuple (redGain, blueGain).
        """
        # Convert Kelvin to a scaled temperature value
        temperature = kelvin / 100.0

        # Calculate red component
        if temperature <= 66:
            red = 255
        else:
            red = 329.698727446 * ((temperature - 60) ** -0.1332047592)
            red = max(0, min(red, 255))
        
        # Calculate green component
        if temperature <= 66:
            green = 99.4708025861 * math.log(temperature) - 161.1195681661
            green = max(0, min(green, 255))
        else:
            green = 288.1221695283 * ((temperature - 60) ** -0.0755148492)
            green = max(0, min(green, 255))
        
        # Calculate blue component
        if temperature >= 66:
            blue = 255
        elif temperature <= 19:
            blue = 0
        else:
            blue = 138.5177312231 * math.log(temperature - 10) - 305.0447927307
            blue = max(0, min(blue, 255))
        
        # Normalize red and blue relative to green (green is used as reference gain of 1.0)
        # Prevent division by zero if green is 0.
        if green == 0:
            green = 1
        redGain = red / green
        blueGain = blue / green
        return redGain, blueGain



class LimitSwitch:
    def __init__(self, pin, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.board = board
        self.board.digital[pin].write(1)
        self.pin = self.board.get_pin(f'd:{pin}:i')

    def is_pressed(self):
        """Returns True if the switch is triggered."""

        state = self.pin.read() == 0
        if self.pin.read() == 0:
            self.pin.mode = 1
            self.pin.write(1)
            self.pin.mode = 0
        return state 

class Sample:
    def __init__(self, mountType, sampleID, initialHeight, mmPerLayer, width, height):
        self.mountType = mountType
        self.sampleID = sampleID
        self.mmPerLayer = mmPerLayer
        self.sampleHeight = initialHeight
        self.boundingBox = [(0,0), (0,0), (0,0), (0,0)]
        self.boundingIsSet = False
        self.set_bounding_box(width, height)
        self.currLayer = 0

    def set_bounding_box(self, width: float, height: float):
        """
        Given the width and height in millimeters, compute the four corners of the bounding box.
        
        The center point of the bounding box is determined by the constant STAGECENTRE,
        which is provided in steps and converted to mm using STEPDISTXY.
        
        Returns:
            List of tuples representing the (x, y) coordinates of the bounding box corners.
            Order: [bottom left, bottom right, top right, top left]
        """
        # Convert center from steps to mm.
        center_x_mm = STAGECENTRE[0] * STEPDISTXY
        center_y_mm = STAGECENTRE[1] * STEPDISTXY
        
        half_width = width / 2.0
        half_height = height / 2.0

        # Calculate corners of the bounding box
        bottom_left  = (center_x_mm - half_width, center_y_mm - half_height)
        bottom_right = (center_x_mm + half_width, center_y_mm - half_height)
        top_right    = (center_x_mm + half_width, center_y_mm + half_height)
        top_left     = (center_x_mm - half_width, center_y_mm + half_height)
        
        self.boundingBox = [bottom_left, bottom_right, top_right, top_left]
        self.boundingIsSet = True
        return self.boundingBox

    def get_curr_height(self):
        return self.sampleHeight - (self.mmPerLayer * self.currLayer)
