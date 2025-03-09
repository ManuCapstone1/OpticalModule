import os
import time
import cv2
from picamera2 import Picamera2

# Define the save directory
save_dir = "/home/microscope/images"  # Ensure this is a valid directory on your Raspberry Pi

# Initialize the camera
cam = Picamera2(0)
camera_config = cam.create_still_configuration({"size": (1920, 1080)})
cam.configure(camera_config)

# Capture and save an image
image_path = capture_and_save_image(cam, save_dir)

if image_path:
    print(f"Image successfully saved: {image_path}")
else:
    print("Failed to capture image.")


def capture_and_save_image(cam: Picamera2, save_dir: str, prefix: str = "image") -> str:
    """
    Captures an image using Picamera2 and saves it to the specified directory.

    :param cam: The Picamera2 instance.
    :param save_dir: The directory where the image will be saved.
    :param prefix: A prefix for the filename (default is "image").
    :return: The full path of the saved image.
    """
    
    # Ensure the save directory exists
    os.makedirs(save_dir, exist_ok=True)

    # Generate a unique filename using timestamp
    timestamp = time.strftime("%Y%m%d_%H%M%S")  # Format: YYYYMMDD_HHMMSS
    filename = f"{prefix}_{timestamp}.jpg"
    file_path = os.path.join(save_dir, filename)

    try:
        # Start camera
        cam.start()
        time.sleep(0.5)  # Allow camera to adjust

        # Capture image
        image = cam.capture_array("main")

        # Convert image to RGB for saving
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Save image
        cv2.imwrite(file_path, image_rgb)
        print(f"Image saved at: {file_path}")

        # Stop camera
        cam.stop()

        return file_path

    except Exception as e:
        print(f"Error capturing image: {e}")
        return ""