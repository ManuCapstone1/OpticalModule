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
    "x_pos" : shabam.get_curr_pos_mm('x'),
    "y_pos" : shabam.get_curr_pos_mm('y'),
    "z_pos" : shabam.get_curr_pos_mm('z'),
    "brightness" : shabam.currBrightness,
    "contrast" : shabam.currContrast,
    "total_image": 0,
    "current_image": 0,
    "file_location": "Unknown"
}

# Send status updates periodically with JSON file
def send_status_updates():
    while True:
        # Simulate the Raspberry Pi periodically updating status data
        pub_socket.send_json(status_data)
        print("Sent status update to the PC...")
        time.sleep(1)  # Wait 1 second before sending the next update
def update_status_data():
    status_data["x_pos"] = shabam.get_curr_pos_mm('x')
    status_data["y_pos"] = shabam.get_curr_pos_mm('y')
    status_data["z_pos"] = shabam.get_curr_pos_mm('z')
    status_data["brightness"] = shabam.currBrightness
    status_data["contrast"] = shabam.currContrast
    


# Handler for receiving data from the PC
def handle_request():
    while True:
        try:
            message = rep_socket.recv_json(flags=zmq.NOBLOCK)  # Non-blocking receive
            print(f"Received request: {message}")

            if "exe_random" in message:
                status_data["module_status"] = "Random Sampling Running"
                # Execute random sampling routine

            if "exe_scanning" in message:
                status_data["module_status"] = "Scanning Running"
                # Execute scanning routine

            if "exe_homing" in message:
                status_data["module_status"] = "Homing" 
                # Execute homing routine

            if "exe_stop" in message:
                status_data["module_status"] = "Stopped"
                # Execute stopping routine


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
