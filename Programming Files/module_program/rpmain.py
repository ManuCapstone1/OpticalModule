import zmq
import time
import json
import threading
from opticalmodule import OpticalModule

#----------------------Zero MQ setup and communication -----------------------------#

context = zmq.Context() # Create a context for ZeroMQ

# Set up the REP (Reply) socket for receiving data from the PC (GUI)
rep_socket = context.socket(zmq.REP)
rep_socket.bind("tcp://*:5555")  # Bind to port 5555

# Set up the PUB (Publisher) socket for sending data updates to the PC (GUI)
pub_socket = context.socket(zmq.PUB)
pub_socket.bind("tcp://*:5556")  # Bind to port 5556

# Data sent to PC every second
# Setup as JSON file
shabam = OpticalModule()

#=========================NEED TO REPLACE WITH REAL DATA=============================#
status_data = {
    "module_status": "Unknown",
    "alarm_status": "None",
    "mode": "Manual",
    "x_pos" : shabam.get_curr_pos_mm('x'),
    "y_pos" : shabam.get_curr_pos_mm('y'),
    "z_pos" : shabam.get_curr_pos_mm('z'),
    "exposure_time" : shabam.cam.currExposureTime,
    "analog_gain" : shabam.cam.currAnalogGain,
    "contrast" : shabam.cam.currContrast,
    "colour_temp" : shabam.cam.currColourTemp,
    "total_image": 0,
    "image_count": 0,
    "current_image" : shabam.cam.currImage,
    "image_metadata" : shabam.currImageMetadata,
    "motors_enabled" : shabam.motorsEnabled
}

# Send status updates periodically with JSON file
def send_status_updates():
    while True:
        # Simulate the Raspberry Pi periodically updating status data
        update_status_data()
        pub_socket.send_json(status_data)
        print("Sent status update to the PC...")
        time.sleep(1)  # Wait 1 second before sending the next update

def update_status_data():
    with shabam.positionLock:
        status_data["x_pos"] = shabam.get_curr_pos_mm('x')
        status_data["y_pos"] = shabam.get_curr_pos_mm('y')
        status_data["z_pos"] = shabam.get_curr_pos_mm('z')
    with shabam.cam.settingsLock:
        status_data["exposure_time"] = shabam.cam.currExposureTime,
        status_data["analog_gain"] = shabam.cam.currAnalogGain,
        status_data["contrast"] = shabam.cam.currContrast,
        status_data["colour_temp"] = shabam.cam.currColourTemp,
    with shabam.imageCountLock:
        status_data["image_count"] = shabam.cam.imageCount
        status_data["total_image"] = shabam.totalImages
    with shabam.cam.imageLock:
        status_data["current_image"] = shabam.cam.currImage
        status_data["image_metadata"] = shabam.currImageMetadata


# Handler for receiving data from the PC
def handle_request():
    while True:
        try:
            message = rep_socket.recv_json(flags=zmq.NOBLOCK)  # Non-blocking receive
            print(f"Received request: {message}")
            thread = threading.Thread()
            if message["command"] is "exe_sampling" and not thread.is_alive():
                status_data["module_status"] = "Random Sampling Running"
                status_data["total_image"] = message["total_image"]
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "random_sampling", "numImages": message["total_image"], "saveImages": False})
                thread.start()

            if message["command"] is "exe_scanning" and not thread.is_alive():
                status_data["module_status"] = "Scanning Running"
                # Execute scanning routine

            if message["command"] is "exe_homing_xy" and not thread.is_alive():
                status_data["module_status"] = "Homing XY" 
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "home_xy"})
                thread.start()
                # Execute homing routine
            
            if message["command"] is "exe_homing_all" and not thread.is_alive():
                status_data["module_status"] = "Homing All" 
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "home_all"})
                # Execute homing routine

            if message["command"] is "exe_update_image" and not thread.is_alive():
                status_data["module_status"] = "Homing All" 
                thread = threading.Thread(target=shabam.update_image)
                # Execute update image

            if message["command"] is "exe_stop":
                status_data["module_status"] = "Stopping..."
                
                shabam.Stop = True
                with shabam.homeLock:
                    shabam.isHomed = False
                # Execute stopping routine

            if status_data["module_status"] is not "idle" and not thread.is_alive():
                status_data["module_status"] = "idle"


            rep_socket.send_json({"status": "received"})  # Acknowledge request

        except zmq.Again:  # No message received, continue loop
            pass

#---------------------------- Threading ------------------------------------------#
# Start both the status update and request handler functions in separate threads
status_thread = threading.Thread(target=send_status_updates, daemon=True)
status_thread.start()

request_thread = threading.Thread(target=handle_request, daemon=True)
request_thread.start()

# Keep the Raspberry Pi running
try:
    while True:
        time.sleep(1)  # Keep the main thread alive
except KeyboardInterrupt:
    print("Server interrupted and shutting down.")
