from pyfirmata import Arduino, util
import time
import pyfirmata
from picamzero import Camera
from time import sleep
from picamera2 import Picamera2, Preview
import cv2
from matplotlib import pyplot as plt
import os

cam = Picamera2(0)

camera_config = cam.create_still_configuration({"size":(1920, 1080)})
cam.configure(camera_config)

SHOW_STEP_IMAGES = True
focus_scores: list[float] = []

# Define the save directory
save_dir = "Documents/images"
os.makedirs(save_dir, exist_ok=True)  # Create directory if it doesn't exist

count = 0  # Counter for unique filenames



# Define pin numbers
enPin = 8
stepXPin = 2
dirXPin = 5
stepYPin = 3
dirYPin = 6
stepZPin = 4
dirZPin = 7

# Motion parameters
stepsPerRev = 200
pulseWidthMicros = 0.0001  # Converted to seconds
millisBtwnSteps = 0.001  # Converted to seconds

# Initialize board (Change 'COM3' to your board's port)
board = Arduino('/dev/ttyUSB0')  # Change to your serial port

# Set pin modes
board.digital[enPin].write(0)  # Enable stepper driver
board.digital[stepXPin].mode = pyfirmata.OUTPUT
board.digital[dirXPin].mode = pyfirmata.OUTPUT
board.digital[stepYPin].mode = pyfirmata.OUTPUT
board.digital[dirYPin].mode = pyfirmata.OUTPUT
board.digital[stepZPin].mode = pyfirmata.OUTPUT
board.digital[dirZPin].mode = pyfirmata.OUTPUT

def get_image(cam: Camera) -> any:

	cam.start()

	array = cam.capture_array("main")
	# Keep the preview window open for 5 seconds
	print(array[100,100])
	print(array.shape)
	sleep(0.01)
	cam.stop()
	
	return array
	
def make_move(delta_x, delta_y):
    delta_a = delta_x + delta_y
    delta_b = delta_x - delta_y
    
    steps_a = abs(round(delta_a / 0.212058))
    steps_b = abs(round(delta_b / 0.212058))
    
    board.digital[dirXPin].write(1 if delta_a >= 0 else 0)
    board.digital[dirZPin].write(1 if delta_b >= 0 else 0)
    
    for _ in range(steps_a):
        board.digital[stepXPin].write(1)
        board.digital[stepZPin].write(1)
        time.sleep(pulseWidthMicros)
        board.digital[stepXPin].write(0)
        board.digital[stepZPin].write(0)
        time.sleep(millisBtwnSteps)

def make_z_move(delta_z):
    steps_z = abs(round(delta_z / 0.01))
    
    board.digital[dirZPin].write(1 if delta_z >= 0 else 0)
    
    for _ in range(steps_z):
        board.digital[stepZPin].write(1)
        time.sleep(pulseWidthMicros)
        board.digital[stepZPin].write(0)
        time.sleep(millisBtwnSteps)
	
        # Uncomment the following for additional movement
        # print("Step 2")
        # make_z_move(-5)
        # time.sleep(5)
        
def figure_file_name(position: float) -> str:
    """
    Return a filename for a plot of data at a specific position.

    :param position: The position in mm.
    """
    position_mm = int(position // 1)
    position_frac = round((position - position_mm) * 1000)
    return f"at_{position_mm}_{position_frac}.png"
        
def calculate_focus_score(image: any, blur: int, position: float) -> float:
    """
    Calculate a score representing how well the image is focussed.

    :param image: The image to evaluate.
    :param blur: The blur to apply.
    :param position: The position in mm the image was captured at.
    """
    image_filtered = cv2.medianBlur(image, blur)
    laplacian = cv2.Laplacian(image_filtered, cv2.CV_64F)
    focus_score: float = laplacian.var()

    if SHOW_STEP_IMAGES:
        focus_scores.append(focus_score)
        grayscale_laplacian = cv2.convertScaleAbs(laplacian, alpha=50)
        # plt.imshow(image_filtered, cmap="gray")
        # plt.show()
        # plt.savefig(figure_file_name(position))
    return focus_score
    
    
    
def find_best_focus(
    start_mm: float, end_mm: float, step_size_mm: float, blur: int) -> None:
    """
    Find best focus by changing the focal distance and taking images with the camera.

    :param start_mm: The position, in mm, to start at.
    :param end_mm: The position, in mm, to end at.
    :param step_size_mm: The distance, in mm, to move between taking images with the camera.
    :param microscope_serial_port: The name of the serial port connected to the microscope.
    :param blur: The blur to apply to images during processing.
    """
    best_focus_score = 0.0
    best_focus_position = 0.0
    # How many steps to take to achieve the desired step size, +1 to check end_mm
    steps = math.ceil((end_mm - start_mm) / step_size_mm) + 1
    for step in range(0, steps):
		position = min(start_mm + step * step_size_mm, end_mm)
		make_z_move(step_size_mm)
		image = get_image(cam)
		focus_score = calculate_focus_score(image, blur, position)
		if focus_score > best_focus_score:
			best_focus_position = position
            best_focus_score = focus_score
        if SHOW_STEP_INFO:
			print(f"focus {position}: {focus_score}")
		
        print("final delta z",position-best_focus_position)
        best_image = get_image(cam)
        
    
    
if __name__ == '__main__':
    board = board
    print("Communication Successfully started")

start_time = time.time()  # Record the starting time

while True:
    # make_z_move(0.2)  # Move Z-axis
    # time.sleep(0.01)   # Adjust delay if needed

    # image = get_image(cam)  # Capture image
    # image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    # score = calculate_focus_score(image, 5, 1)  # Compute focus score

    # elapsed_time = round(time.time() - start_time, 2)  # Time since script started (rounded to 2 decimal places)
    # focus_score = round(score, 2)  # Round focus score for filename

    # print(f"Focus score is {focus_score}")

    # # Create filename with elapsed time and focus score
    # filename = os.path.join(save_dir, f"image_{elapsed_time:.2f}s_score_{focus_score:.2f}.jpg")
    # cv2.imwrite(filename, image_rgb)
    # print(f"Saved {filename}")
	
	
