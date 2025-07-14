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
STEPDISTXY = 0.212058/16 # linear distance moved in x and y each motor step (using 1/16 microstepping)
STEPDISTZ = 0.01/4 # linear distance moved in z each motor step (using 1/4 microstepping)
PULSEWIDTH = 100 / 1000000.0 # microseconds
BTWNSTEPS = 1000 / 1000000.0
STAGEFOCUSHEIGHT = 36860*STEPDISTZ # z height at which the stage is in focus (this may change with calibration)
STAGECENTRE = (8281, 7005) # Stage centre location in steps

class OpticalModule:
    """
        This class is a digital representation of the physical system. 
        It includes fields for the system parameters and methods for operating the system.
        Attributes:
            board: Pyfirmata Arduino board object
            enPin: Arduino pin used to enable and disable motors
            motorA (StepperMotor): Upper left stepper motor when viewed from the front
            motorB (StepperMotor): Upper right stepper motor when viewed from the front
            motorZ (StepperMotor): Motor connected to ball screw
            limitSwitchX (LimitSwitch): Limit switch for x-axis (back right corner)
            limitSwitchY (LimitSwitch): Limit switch for y-axis (back left corner)
            limitSwitchZ (LimitSwitch): Limit switch for z-axis (z motor bracket)
            cam (Camera): Camera object containing camera methods and attributes
            currX (int): Current x position of the camera carriage in steps
            currY (int): Current y position of the camera carriage in steps
            currZ (int): Current z position of the stage in steps
            currSample (Sample): Current sample in the system - this may be replaced with a list in the future for use with multiple samples
            totalImages (int): Total number of images to be captured in the current operation
            currImageMetadata: System parameters to be saved when an image is captured
            bufferDir (str): Directory where images are saved to be transferred to the PC
            alarmStatus (str): Alarm status to be displayed in the GUI
            positionLock (threading.Lock): Thread lock for updating or reading current position
            imageCountLock (threading.Lock): Thread lock for updating or reading image count information
            alarmLock (threading.Lock): Thread lock for updating or reading alarmStatus
            stop (threading.Event): Threading event used to indicate stop requested
            resetIdle (threading.Event): Threading event used to indicate that the module status should be reset to "Idle"
            isHomed (threading.Event): Threading event set when the system is homed; cleared if system is stopped or motors disabled
            motorsEnabled (threading.Event): Threading event to indicate whether motors are enabled

    """
    def __init__(self):

        # Instantiate pyfirmata Arduino board and iterator which allows limit switches to work
        self.board=pyfirmata.Arduino("/dev/ttyUSB0")
        it = pyfirmata.util.Iterator(self.board)
        it.start()
        
        # Set up enable pin to allow us to enable and disable motors for manual movement
        self.enPin = self.board.get_pin('d:8:o') 
        self.enPin.write(0)

        # Instantiate motor objects for the three motors. Motors A&B function according to CoreXY (see corexy.com for details)
        self.motorA = StepperMotor(2, 5, self.board)
        self.motorB = StepperMotor(3, 6, self.board)
        self.motorZ = StepperMotor(4, 7, self.board)
        
        # Instantiate limit switch objects
        self.limitSwitchX = LimitSwitch(9, self.board)
        self.limitSwitchY = LimitSwitch(10, self.board)
        self.limitSwitchZ = LimitSwitch(11, self.board)

        # Instantiate Camera
        self.cam = Camera()

        # Create variables to hold current position in terms of steps
        self.currX = 0 
        self.currY = 0
        self.currZ = 0
        self.currSample = None

        # Image variables
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


        self.bufferDir = "/home/microscope/image_buffer"
        self.alarmStatus = "None"

        # Threading locks and events
        self.positionLock = threading.Lock()
        self.imageCountLock = threading.Lock()
        self.alarmLock = threading.Lock()
        self.stop = threading.Event()
        self.resetIdle = threading.Event()
        self.isHomed = threading.Event()
        self.motorsEnabled = threading.Event()

    def add_sample(self, mountType, sampleID, initialHeight, mmPerLayer, width, height):
        """
        Instantiates new sample and holds it as self.currSample
        Parameters:
            mountType: eg. puck or stub
            sampleID: User defined name for the current sample
            initialHeight: The initial z height of the sample in mm - how far above the stage is the surface of the sample
            mmPerLayer: Sample height reduction in each polishing step (in mm)
            width: Bounding box width in mm (x-direction)
            height Bounding box height in mm (y-direction)
        """
        self.currSample = Sample(mountType, sampleID, initialHeight, mmPerLayer, width, height)

    def disable_motors(self):
        """
        Disables stepper motors to allow for manual adjustment (system must run homing after)
        """
        self.enPin.write(1)
        self.motorsEnabled.clear() # motors not enabled
        self.isHomed.clear() # system not homed

    def enable_motors(self):
        """
        Enables stepper motors for continued use
        """
        self.enPin.write(0)
        self.motorsEnabled.set() # motors are enabled

    def _move_ab(self, deltaA: int, deltaB: int):
        """
        Internal method for moving the carriage in x and y

        Parameters:
            deltaA: How far and which direction to move motor A in steps
            deltaB: How far and which direction to move motor B in steps        
        """
        # Total number of steps to move the motors
        # Because we are only moving in cartesian directions the number of steps by each motor will always be the same
        # This may need to be changed in the future if diagonal or circular motion is required
        steps = abs(deltaA)

        # Set the direction of motors A and B
        if deltaA >= 0:
            self.motorA.dir_pin.write(1)
        else:
            self.motorA.dir_pin.write(0)

        if deltaB >= 0:
            self.motorB.dir_pin.write(1)
        else:
            self.motorB.dir_pin.write(0)

        # Move the motors the required number of steps
        for i in range(steps):
            # Stop system if stop is requested
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


    def move_x(self, deltaX=0):
        """
        Move system in the x-direction
        Parameters:
            deltaX: Distance to move in x-direction (in steps)
        """
        # Determine distance and direction to move each motor (based on CoreXY)
        deltaA = -deltaX
        deltaB = -deltaX

        # Update current position
        with self.positionLock:
            self.currX = self.currX + deltaX 
        
        # Move motors
        self._move_ab(deltaA, deltaB)

    # Moves carriage in y by a given linear distance (mm)
    def move_y(self,deltaY=0):
        """
        Move system in the y-direction
        Parameters:
            deltaY: Distance to move in y-direction (in steps)
        """
        # Determine distance and direction to move each motor (based on CoreXY)
        deltaA = -deltaY
        deltaB = deltaY

        # Update current position
        with self.positionLock:
            self.currY = self.currY + deltaY
        
        # Move motors
        self._move_ab(deltaA, deltaB)

    def move_z(self, deltaZ=0):
        """
        Move platform in z-direction
        Parameters:
            deltaZ: distance to move in the z-direction (in steps)
        """
        # Find number of steps to move
        steps = abs(deltaZ)

        # Update current z-position
        with self.positionLock:
            self.currZ = self.currZ + deltaZ
        
        # Establish motion direction of motors
        if deltaZ >= 0:
            self.motorZ.dir_pin.write(1)
        else:
            self.motorZ.dir_pin.write(0)

        # Move z motor by specified number of steps
        for i in range(steps):
            # Stop motion if stop is requested
            if self.stop.is_set():
                self.resetIdle.set()
                self.isHomed.clear()
                return
            self.motorZ.step_pin.write(1)
            time.sleep(PULSEWIDTH)
            self.motorZ.step_pin.write(0)
            time.sleep(BTWNSTEPS)
    
    def go_to(self, x=None, y=None, z=None):
        """
        Moves system to specified (x, y, z) position (in mm)
        Parameters:
            x: x position relative to homed position (mm)
            y: y position relative to homed position (mm)
            z: z position relative to homed position (mm)
        """
        # If mm values are passed system calculates steps. If not remains at current position
        x = round(x/STEPDISTXY) if x is not None else self.currX
        y = round(y/STEPDISTXY) if y is not None else self.currY
        z = round(z/STEPDISTZ) if z is not None else self.currZ
        
        # If new values are passed move to specified position
        if not x == self.currX:
            self.move_x(x-self.currX)

        if not y == self.currY:
            self.move_y(y-self.currY)

        if not z == self.currZ:
            self.move_z(z-self.currZ)

    def get_curr_pos_mm(self, axis):
        """
        Gets the current mm position of a specified axis.
        Parameters:
            axis: String (eg. "x") of axis to return
        Returns:
            Millimeter position of specified axis
        """
        if axis == "x":
            return self.currX*STEPDISTXY
        elif axis == "y":
            return self.currY*STEPDISTXY
        elif axis == "z":
            return self.currZ*STEPDISTZ
        else: return 0

    def home_xy(self):
        """
        Moves the camera carriage to the homed position in the x-y plane.
        """
        # This code was added to avoid a bug where the limit switch was not reset before homing
        # This caused the system to attempt to home x without homing y first resulting in a crash
        # By reading the limit switches several times it forces them to reset before homing
        # There is probably a better solution for this but this method works.
        for i in range(10):
            if not self.limitSwitchY.is_pressed() and not self.limitSwitchX.is_pressed():
                break
            if i == 9:
                print('limit reset failed')
                with self.alarmLock:
                    self.alarmStatus = "Limit Switch Failed"
        
        # Home Y axis
        print("Y")
        self.motorA.dir_pin.write(1)
        self.motorB.dir_pin.write(0)
        while not self.limitSwitchY.is_pressed():
            # Allows system to stop if stop requested  
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
        # Set current position to 0
        with self.positionLock:
            self.currY = 0

        # Home X axis
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
        """
        Moves system to home position in all axes. Also clears stop condition and resets homed status.
        """
        self.stop.clear() # clears stop condition
        self.enable_motors() # enable stepper motors
        self.home_xy() # home x and y axes

        # Reset z limit switch (see HomeXY for details)
        for i in range(10):
            if not self.limitSwitchZ.is_pressed():
                break
            if i == 9:
                print('limit reset failed')
                with self.alarmLock:
                    self.alarmStatus = "Limit Switch Failed"
        
        # Home Z axis
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
        # Set Z position to 0
        with self.positionLock:
            self.currZ = 0
            self.isHomed.set() # system is homed

    
    def auto_focus(self, zMin=None, zMax=None, stepSize=None):
        """
        Finds the best focus position in a given range of heights by calculating the focus score (laplacian variance) every step of a given mm size.
        If no parameters are passed, the best focus position will be determined within +/- 1 mm of the current theoretical sample height with a step
        size of 0.05 mm
        Parameters:
            zMin: Lower bound of focus range (mm position)
            zMax: Upper bound of focus range (mm position)
            stepSize: distance to move between each focus score calculation
        Returns:
            Focus score of best position in range
        """
        # Calculate the range based on current sample height if parameters are not passed
        if zMin is None or zMax is None or stepSize is None:
            zMin = STAGEFOCUSHEIGHT - self.currSample.get_curr_height() - 1 
            zMax = STAGEFOCUSHEIGHT - self.currSample.get_curr_height() + 1 
            stepSize = 0.05
        bestFocusValue = -1
        bestZPosition = zMin

        # Convert all mm values to microns to allow for direct use of for loops
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
            # print(focusScore)
            # Check if this focus value is the best so far
            if focusScore > bestFocusValue:
                bestFocusValue = focusScore
                bestZPosition = z/1000

        # Move to the z position with the best focus using go_to
        self.go_to(z=bestZPosition)

        return bestFocusValue
    
    def update_image_metadata(self, save=False):
        """
        Update image metadata based on current status
        Parameters:
            save: Will the metadata be saved to a .txt file in the buffer directory (boolean)
        """
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
        """
        Captures image and saves image and metadata file to buffer directory
        """
        # Capture image
        image = self.cam.update_curr_image(self.currSample)
        filename = f"{self.cam.currImageName}.jpg"
        file_path = os.path.join(self.bufferDir, filename)

        # Convert image to RGB for saving
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Save image and updated metadata
        cv2.imwrite(file_path, image_rgb)
        self.update_image_metadata(True)

        return image
    

    def random_sampling(self, numImages, saveImages: bool):
        """
        Takes images at a specified number of random positions within the sample bounding box.
        Parameters:
            numImages: how many random samples to take
            saveImages: should the images be saved? This was added to make defect detection possible in the future without saving all images; 
                however, in its current state the program will save images regardless. Setting this parameter to True will save the images 
                without metadata, False will save the images with metadata. This should be changed in the future.
        Returns:
            List of captured images to be used for applications like defect detection
        """
        # Cancel the operation if no sample bounding box set
        if self.currSample is None or not self.currSample.boundingIsSet:
            print("Bounding box not set. Cannot take images.")
            with self.alarmLock:
                    self.alarmStatus = "No Bounding Box Set"
            return
        
        # Home system if stopped or not homed
        if not self.isHomed.is_set() or self.stop.is_set():
            self.home_all()
        
        # Move carriage to stage center and complete autofocus operation on sample
        self.go_to(x=STAGECENTRE[0]*STEPDISTXY, y=STAGECENTRE[1]*STEPDISTXY)
        self.auto_focus()

        # If the sample is not in position it will have a low focus score
        # (this may need to be changed in the future as clean samples also have a low focus score)
        if self.cam.calculate_focus_score() < 1:
            print("Sample not detected or not in focus")
            with self.alarmLock:
                    self.alarmStatus = "Sample not detected or not in focus"
            return
        
        # Update total images 
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
            # Stop program if stop requested
            if self.stop.is_set():
                self.resetIdle.set()
                return
            
            # Go to the random position
            self.go_to(x=point[0], y=point[1])

            # Allow system to stabilize 
            time.sleep(0.5)

            # Save images without or with metadata file (this should be changed in the future)
            if saveImages: 
                imageArr = self.cam.save_image(self.bufferDir, self.currSample)
            else:
                imageArr = self.update_image()

            # Increment image count and save current image to captured images list
            with self.imageCountLock:
                self.cam.imageCount = self.cam.imageCount + 1
            capturedImages.append(cv2.cvtColor(imageArr, cv2.COLOR_BGR2RGB))

        # Reset image counters and increment current sample layer
        with self.imageCountLock:
            self.totalImages = 0
            self.cam.imageCount = 0

        self.currSample.currLayer = self.currSample.currLayer + 1 # This may need to be changed in the future if a layer is not always removed

        # Return camera carriage to home position for robot sample pickup
        self.home_xy()
        return capturedImages
    
    def scanning_images(self, step_size_x, step_size_y, saveImages: bool):
        """
        Takes a series of overlapping images to cover the entire area of the bounding box for image stitching.
        Parameters:
            step_size_x: How far (in mm) the camera carriage should move in the x-direction between images. 
                X distance between the centre points of neighboring images
            step_size_y: How far (in mm) the camera carriage should move in the y-direction between images. 
                Y distance between the centre points of neighboring images
            saveImages: should the images be saved? This was added to make defect detection possible in the future without saving all images; 
                however, in its current state the program will save images regardless. Setting this parameter to True will save the images 
                without metadata, False will save the images with metadata. This should be changed in the future.
        """
        # Cancel the operation if no sample bounding box set
        if self.currSample is None or not self.currSample.boundingIsSet:
            print("Bounding box not set. Cannot take images.")
            with self.alarmLock:
                    self.alarmStatus = "No Bounding Box Set"
            return

        # Home system if stopped or not homed
        if not self.isHomed.is_set() or self.stop.is_set():
            self.home_all()

        # Move carriage to stage center and complete autofocus operation on sample
        self.go_to(x=STAGECENTRE[0]*STEPDISTXY, y=STAGECENTRE[1]*STEPDISTXY)
        self.auto_focus()

        # If the sample is not in position it will have a low focus score
        # (this may need to be changed in the future as clean samples also have a low focus score)        
        if self.cam.calculate_focus_score() < 1:
            print("Sample not detected or not in focus")
            with self.alarmLock:
                    self.alarmStatus = "Sample not detected or not in focus"
            return
        
        # Create list of captured images
        capturedImages = []

        # Create list of X and Y positions to capture overlapping images covering the bounding box area
        x_coords = [point[0] for point in self.currSample.boundingBox]
        y_coords = [point[1] for point in self.currSample.boundingBox]

        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)

        x_positions = list(range(int(min_x), int(max_x) + step_size_x, step_size_x))
        y_positions = list(range(int(min_y), int(max_y) + step_size_y, step_size_y))

        # Set image counters to correct values
        with self.imageCountLock:
            self.totalImages = len(x_positions) * len(y_positions)
            self.cam.imageCount = 0
        
        # Loop through grid positions in up & right pattern
        for x in x_positions:
            for y in y_positions:
                # Stop system if stop requested
                if self.stop.is_set():
                    self.resetIdle.set()
                    return
                
                # Go to grid position
                self.go_to(x=x, y=y)

                # Allow system to stabilize
                time.sleep(0.5)  
                
                # Save images without or with metadata file (this should be changed in the future)
                if saveImages:
                    imageArr = self.cam.save_image(self.saveDir, self.currSample)
                else:    
                    imageArr = self.update_image()

                # Update image count and captured image list
                with self.imageCountLock:
                    self.cam.imageCount = self.cam.imageCount + 1
                capturedImages.append(cv2.cvtColor(imageArr, cv2.COLOR_BGR2RGB))  
        
        # Reset image counters and increment current sample layer
        with self.imageCountLock:
            self.totalImages = 0
            self.imageCount = 0
        
        self.currSample.currLayer = self.currSample.currLayer + 1 # This may need to be changed in the future if a layer is not always removed
        
        # Return camera carriage to home position for robot sample pickup
        self.home_xy()
        return capturedImages
        
    def calibrate_platform(self):
        """
        Performs autofocus operation at four corners of the stage and returns focus height. This can be used in the future to assist with platform leveling
        Returns:
            List of in-focus heights (in steps) of the four corners of the platform
        """
        self.home_all()

        # Corner 1
        self.go_to(x=49, y=28)
        self.auto_focus(88,94,0.05)
        Z1 = self.currZ
        print(Z1)

        # Corner 2
        self.go_to(x=46, y=155)
        self.auto_focus(88,94,0.05)
        Z2 = self.currZ
        print(Z2)

        # Corner 3
        self.go_to(x=173, y=155.5)
        self.auto_focus(88,94,0.05)
        Z3 = self.currZ
        print(Z3)

        # Corner 4
        self.go_to(x=172.5, y=30)
        self.auto_focus(88,94,0.05)
        Z4 = self.currZ
        print(Z4)

        # Create and return list of heights
        zdistlist = [Z1,Z2,Z3,Z4]
        return zdistlist
    
    def matrix_transform(self):
        """
        This is an automatic method of establishing scaling and rotation aspects of affine transformation, 
        the method returns the transformation matrix. However, because the code is looking for random features on the images, 
        it is hard to consistently get the same absolute zero every time, even with a crosshair marker. 
        Output images with markers indicating the same feature will be saved in the microscope folder.
        """
        if not self.isHomed.is_set():
            self.home_all()

        self.go_to(x=49, y=28)
        self.auto_focus(88,94,0.05)
        img1 = self.cam.get_image_array(True)
        self.go_to(x=49, y=27)
        img2 = self.cam.get_image_array(True)
        self.go_to(x=50, y=27)
        img3 = self.cam.get_image_array(True)

        # Convert to grayscale for feature detection
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        gray3 = cv2.cvtColor(img3, cv2.COLOR_BGR2GRAY)

        # Initialize ORB detector
        orb = cv2.ORB_create()

        # Detect features in all images
        kp1, des1 = orb.detectAndCompute(gray1, None)
        kp2, des2 = orb.detectAndCompute(gray2, None)
        kp3, des3 = orb.detectAndCompute(gray3, None)

        # Create BFMatcher with cross-check
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        # Match Image1 with Image2 and Image3
        matches_12 = bf.match(des1, des2)
        matches_13 = bf.match(des1, des3)

        # Create dictionaries for quick lookup
        match12_dict = {m.queryIdx: m for m in matches_12}
        match13_dict = {m.queryIdx: m for m in matches_13}

        # Find common features present in all matches
        common_features = []
        for q_idx in set(match12_dict.keys()) & set(match13_dict.keys()):
            m12 = match12_dict[q_idx]
            m13 = match13_dict[q_idx]
            total_distance = m12.distance + m13.distance
            common_features.append((
                q_idx,        # Image1 keypoint index
                m12.trainIdx,  # Image2 keypoint index
                m13.trainIdx,  # Image3 keypoint index
                total_distance
            ))

        # Sort by match quality (lower distance = better)
        common_features.sort(key=lambda x: x[3])

        # Select top 1 common feature
        top_matches = common_features[:1]

        # Draw markers on all images
        colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0)]  # Red, Green, Blue
        marker_type = cv2.MARKER_CROSS
        marker_size = 500
        thickness = 10

        for i, (q_idx, t12_idx, t13_idx, _) in enumerate(top_matches):
            # Image 1
            x1, y1 = map(int, kp1[q_idx].pt)
            cv2.drawMarker(img1, (x1, y1), colors[i],
                        marker_type, marker_size, thickness)

            # Image 2
            x2, y2 = map(int, kp2[t12_idx].pt)
            cv2.drawMarker(img2, (x2, y2), colors[i],
                        marker_type, marker_size, thickness)

            # Image 3
            x3, y3 = map(int, kp3[t13_idx].pt)
            cv2.drawMarker(img3, (x3, y3), colors[i],
                        marker_type, marker_size, thickness)

        # Save and display results
        cv2.imwrite('image1_x=49_y=28.jpg', img1)
        cv2.imwrite('image2_x=49_y=27.jpg', img2)
        cv2.imwrite('image3_x=50_y=27.jpg', img3)

        camera_pts = np.float32([kp1[q_idx].pt, kp2[t12_idx].pt, kp3[t13_idx].pt])

        stage_pts = np.float32([[0,0], [0,1], [1,1]])

        # Compute affine transformation matrix
        T = cv2.getAffineTransform(stage_pts, camera_pts)

        return T
        

    def execute(self, targetMethod, **kwargs):
        """
        Calls specified method on a thread and resets module status to "Idle" when complete. 
        This method is meant to be used with methods that cause motion and its main purpose is to reset the module status.
        There is almost certainly a more lightweight way to do this with threading events and this method should be eliminated in the future.
        Parameters:
            targetMethod: Method in OpticalModule class to be called
            kwargs: list of keyword arguments in the format {"keyword": "argument", "keyword2": "argument2"}
        """
        # Get the target method
        target = getattr(self, targetMethod, None)

        if callable(target):
            # Create thread for target method
            targetThread = threading.Thread(target=target, kwargs=kwargs, daemon=True)
            targetThread.start()

            # Wait for target method to complete and set event to reset module status
            targetThread.join()
            self.resetIdle.set()

        else:
            raise AttributeError(f"'{type(self).__name__}' has no callable method '{targetMethod}'")
            

    def call_method_from_console(self):
        """
        This method was created during testing to provide a way of calling OpticalModule methods from the console before the GUI was developed.
        It does not work very well but could have some usefulness in the future so I will leave it here
        """
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
    """
    This is  class for the stepper motors. It allows pin information to be held in a motor object.
    Attributes:
        board: pyfirmata Arduino board
        step_pin: pin used for motor step pulses
        dir_pin: pin used to set motor rotation direction
    """
    def __init__(self, step_pin, dir_pin, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.board = board
        self.step_pin = board.get_pin(f'd:{step_pin}:o')
        self.dir_pin = board.get_pin(f'd:{dir_pin}:o')

class Camera:
    """
    Class for system camera. Contains camera settings information and related methods.
    Attributes:
        picam (Picamera2): Picamera object for system camera
        currExposureTime: Exposure time used when capturing images
        currAnalogGain: Analog gain applied to camera sensor data (1.0 = no gain)
        currContrast: Contrast adjustment applied to images (1.0 = no adjustment)
        currColourTemp: Lighting colour temperature (currently not implemented)
        camera_config: Picamera camera configuration
        currImage: Most recently captured image
        currImageName: File name of most recently captured image
        imageCount: Number of images captured in current operation
        settingsLock (threading.Lock): Thread lock for updating or reading the camera settings
        imageLock (threading.Lock): Thread lock for updating or reading currImage or currImageName
    """
    def __init__(self):
        # Create Camera
        self.picam = Picamera2(0)
        
        # Create variables for camera settings
        self.currExposureTime = 100000      # Default exposure time in microseconds
        self.currAnalogGain = 2             # Default analogue gain (1.0 = no gain)
        self.currContrast = 1.0             # Default contrast (1.0 is neutral)
        self.currColourTemp = 6000          # Default colour temperature in Kelvin (ring light colour temp is 6000)

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
        In testing, this method was not working and likely needs improvement.
        
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
        *Note: because the conversion from colour temp to gains was not working it is left out of the controls directory
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
        """
        Updates the currImageName and currImage fields of the Camera object
        """
        self.update_image_name(sample)
        return self.get_image_array(True)

    def calculate_focus_score(self, imageArray=None, blur=5):
        """
        Calculates the focus of an image using the Laplacian variance.

        Parameters:
            imageArray: Image used to calculate focus score (image will be captured if not provided).
            blur: level of blur applied (to reduce impact of noise)

        Returns:
            Focus score (Laplacian variance) 
        
        """

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
        """
        Captures image from Raspberry Pi camera.

        Parameters:
            updateImage: Updates captured image to Camera object currImage field if True

        Returns:
            Captured image as an array

        """
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
    
    def save_image(self, dir: str, sample, image=None):
        """
        Captures an image using Picamera2 and saves it to the specified directory.

        Parameters:
            dir: Directory to save image as a string
            sample: Sample object - used to update image name
            image: Optionally pass image array to be saved

        Returns:
            image as an array
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
        """
        Updates the currImageName field of the camera object.

        Parameters:
            sample: Sample object - currLayer and sampleID included in image name
            imageCount: image number in current sampling or scanning operation (taken from Camera imageCount field if not provided)
        
        Returns:
            New image name as a string


        """
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

        This method currently does not work and requires future updates for manual colour temperature control
        
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
    """
    Class for limit switches. Includes pin information and method to read switch status.
    Attributes:
        board: Pyfirmata Arduino board
        pin: Arduino digital pin connected to limit switch
    """
    def __init__(self, pin, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.board = board
        self.board.digital[pin].write(1)
        self.pin = self.board.get_pin(f'd:{pin}:i')

    def is_pressed(self):
        """Returns True if the switch is triggered."""

        state = self.pin.read() == 0

        # Manually reset pin state due to a quirk with pyfirmata where pin status never resets once pressed
        if self.pin.read() == 0:
            self.pin.mode = 1
            self.pin.write(1)
            self.pin.mode = 0
        return state 

class Sample:
    """
    Class for samples used in the system.
    Attributes:
        mountType (str): How the sample is mounted (not currently used but may be useful for future applications)
        sampleID (str): User defined name for the sample 
        mmPerLayer (float): Millimeters of material removed at each polishing step
        sampleHeight (float): The initial z height of the sample in mm - how far above the stage is the surface of the sample
        boundingBox: List of tuples representing the (x, y) coordinates of the bounding box corners.
        boundingIsSet: True if bounding box is set for the sample
        currLayer (int): The current layer of the sample (how many polishing steps have been completed)
    """
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
        """Returns the current height of the sample based on the number of layers removed"""
        return self.sampleHeight - (self.mmPerLayer * self.currLayer)
