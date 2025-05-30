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

# Instantiate OpticalModule object
shabam = OpticalModule()


# Create JSON object to hold module information to be sent to GUI
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
    "curr_sample_id": "None",
    "total_image": 0,
    "image_count": 0,
    "motors_enabled" : shabam.motorsEnabled.is_set()
}


def send_status_updates():
    """
    Publishes updated module status data every second.
    """
    while True:
        # Update data
        update_status_data()

        # Send data to the PC
        print("sending")
        pub_socket.send_json(status_data)
        print("Sent status update to the PC...")

        time.sleep(1)  # Wait 1 second before sending the next update

def update_status_data():
    """Updates status_data with the current data"""

    # Update positional data
    with shabam.positionLock:
        status_data["x_pos"] = shabam.get_curr_pos_mm('x')
        status_data["y_pos"] = shabam.get_curr_pos_mm('y')
        status_data["z_pos"] = shabam.get_curr_pos_mm('z')
    
    # Update camera settings data
    with shabam.cam.settingsLock:
        status_data["exposure_time"] = shabam.cam.currExposureTime,
        status_data["analog_gain"] = shabam.cam.currAnalogGain,
        status_data["contrast"] = shabam.cam.currContrast,
        status_data["colour_temp"] = shabam.cam.currColourTemp,
    
    # Update image count data
    with shabam.imageCountLock:
        status_data["image_count"] = shabam.cam.imageCount
        status_data["total_image"] = shabam.totalImages
    
    # Update alarm status data
    with shabam.alarmLock:
        status_data["alarm_status"] = shabam.alarmStatus

    # Reset module_status to "Idle" if threading event indicates it should be
    if shabam.resetIdle.is_set():
        status_data["module_status"] = "Idle"
        shabam.resetIdle.clear()
    
    # Update motor enabled data
    status_data["motors_enabled"] = shabam.motorsEnabled.is_set()

    # Update current sample ID data
    if shabam.currSample != None:
        status_data["curr_sample_id"] = shabam.currSample.sampleID

# Handler for receiving data from the PC
def handle_request():
    """Handles incoming requests from the PC and calls requested methods on a new thread"""

    thread = threading.Thread()
    status_data["module_status"] = "Idle" # Set initial status to Idle

    while True:
        
        try:            
            message = rep_socket.recv_json()  # blocking receive - wait for a new request from the PC
            print(f"Received request: {message}")
            response = {"status": "received"}

            # Incomplete implementation - return error message if thread is running  
            if thread.is_alive():
                #response["error"] = "Process Incomplete"
                #rep_socket.send_json(response)
                pass
                
            if shabam.stop.is_set():
                #response["error"] = "System stopped; homing required"
                pass
            
            # Update camera settings (currently does not work and requires debugging)
            if message["command"] == "update_settings" and not thread.is_alive():
                thread = threading.Thread(target=shabam.cam.update_settings, kwargs={"exposureTime": message["exposure_time"], 
                                                                                     "analogGain": message["analog_gain"], 
                                                                                     "contrast": message["contrast"], 
                                                                                     "colourTemperature": message["colour_temp"]})
                thread.start()
            
            # Disable stepper motors for manual system movement
            if message["command"] == "exe_disable_motors" and not thread.is_alive():
                thread = threading.Thread(target=shabam.disable_motors)
                thread.start()

            # Create new sample
            if message["command"] == "create_sample" and not thread.is_alive():
                thread = threading.Thread(target=shabam.add_sample, kwargs={"mountType": message["mount_type"],
                                                                            "sampleID": message["sample_id"],
                                                                            "initialHeight": message["initial_height"],
                                                                            "mmPerLayer": message["layer_height"],
                                                                            "width": message["width"],
                                                                            "height": message["height"]})                                                                     
                thread.start()

            # Run random sampling routine
            if message["command"] == "exe_sampling" and not thread.is_alive():
                status_data["module_status"] = "Random Sampling Running"
                status_data["total_image"] = message["total_image"]
                status_data["image_count"] = 0
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "random_sampling", 
                                                                         "numImages": message["total_image"], 
                                                                         "saveImages": False})
                thread.start()

            # Run scanning routine
            if message["command"] == "exe_scanning" and not thread.is_alive():
                print("t1")
                status_data["module_status"] = "Scanning Running"
                status_data["total_image"] = 0
                status_data["image_count"] = 0
                
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "scanning_images", 
                                                                         "step_size_x": message["step_x"], 
                                                                         "step_size_y": message["step_y"], 
                                                                         "saveImages": False})
                thread.start()

            # Home XY position
            if message["command"] == "exe_homing_xy" and not thread.is_alive():
                status_data["module_status"] = "Homing XY" 
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "home_xy"})
                thread.start()
            
            # Home X, Y, and Z position
            if message["command"] == "exe_homing_all" and not thread.is_alive():
                status_data["module_status"] = "Homing All" 
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "home_all"})
                thread.start()
            
            # Go to a specified X, Y, and Z position
            if message["command"] == "exe_goto" and not thread.is_alive():
                status_data["module_status"] = "Changing Position" 
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "go_to", 
                                                                         "x": message["req_x_pos"],
                                                                         "y": message["req_y_pos"],
                                                                         "z": message["req_z_pos"]})
                thread.start()

            # Capture and save a single image to the buffer directory
            if message["command"] == "exe_update_image" and not thread.is_alive():
                thread = threading.Thread(target=shabam.update_image)
                thread.start()
            
            # Reset module alarm status
            if message["command"] == "exe_reset_alarm_status" and not thread.is_alive():
                with shabam.alarmLock:
                    shabam.alarmStatus = "None"

            # Stop system by setting stop event
            if message["command"] == "exe_stop":
                status_data["module_status"] = "Stopping..."
                shabam.stop.set()
                status_data["module_status"] = "Idle"

            rep_socket.send_json(response)  # Acknowledge request

        # This was created when this function used a non-blocking receive can probably be removed
        except zmq.Again:  # No message received, continue loop
            if status_data["module_status"] != "Idle" and thread.is_alive() == False:
                status_data["module_status"] = "Idle"


#---------------------------- Threading ------------------------------------------#

# Start both the status update and request handler functions in separate threads
status_thread = threading.Thread(target=send_status_updates, daemon=True)
status_thread.start()

request_thread = threading.Thread(target=handle_request, daemon=True)
request_thread.start()

# Keep the Raspberry Pi running until keyboard interrupt 
try:
    while True :
        time.sleep(1)  # Keep the main thread alive
except KeyboardInterrupt:
    print("Server interrupted and shutting down.")

