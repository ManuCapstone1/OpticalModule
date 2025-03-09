from picamzero import Camera
from time import sleep
from picamera2 import Picamera2, Preview

cam = Picamera2(0)

camera_config = cam.create_still_configuration({"size":(1920, 1080)})
cam.configure(camera_config)

def get_image(cam: Camera) -> any:

	cam.start()

	array = cam.capture_array("main")
	# Keep the preview window open for 5 seconds
	print(array[100,100])
	print(array.shape)
	sleep(5)
	cam.stop()
	
	return array



get_image(cam)