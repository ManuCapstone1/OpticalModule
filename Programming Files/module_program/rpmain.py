from email.mime import message

import zmq
import time
import json
import threading

from opticalmodule import OpticalModule

#----------------------Zero MQ setup and communication -----------------------------#

context = zmq.Context()

# REP socket: PC sends commands here
rep_socket = context.socket(zmq.REP)
rep_socket.bind("tcp://*:5555")

# PUB socket: status broadcasts to the PC
pub_socket = context.socket(zmq.PUB)
pub_socket.bind("tcp://*:5556")

shabam = OpticalModule()

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
        try:
            update_status_data()

            print("sending")
            pub_socket.send_json(status_data)
            print("Sent status update to the PC...")
        except Exception as e:
            print(f"Error in send_status_updates: {e}")

        time.sleep(1)

def update_status_data():
    """Updates status_data with the current data"""
    if hasattr(shabam, "latest_measurements"):
        status_data["latest_measurements"] = shabam.latest_measurements
    else:
        status_data["latest_measurements"] = []

    with shabam.positionLock:
        status_data["x_pos"] = shabam.get_curr_pos_mm('x')
        status_data["y_pos"] = shabam.get_curr_pos_mm('y')
        status_data["z_pos"] = shabam.get_curr_pos_mm('z')

    with shabam.cam.settingsLock:
        status_data["exposure_time"] = shabam.cam.currExposureTime
        status_data["analog_gain"] = shabam.cam.currAnalogGain
        status_data["contrast"] = shabam.cam.currContrast
        status_data["colour_temp"] = shabam.cam.currColourTemp

    with shabam.imageCountLock:
        status_data["image_count"] = shabam.cam.imageCount
        status_data["total_image"] = shabam.totalImages

    with shabam.alarmLock:
        status_data["alarm_status"] = shabam.alarmStatus

    # background thread sets this when a command finishes, avoids a lock
    if shabam.resetIdle.is_set():
        status_data["module_status"] = "Idle"
        shabam.resetIdle.clear()

    status_data["motors_enabled"] = shabam.motorsEnabled.is_set()

    if shabam.currSample != None:
        status_data["curr_sample_id"] = shabam.currSample.sampleID

def handle_request():
    """Handles incoming requests from the PC and calls requested methods on a new thread"""

    thread = threading.Thread()
    status_data["module_status"] = "Idle"

    while True:

        try:
            message = rep_socket.recv_json()  # blocks until PC sends something
            print(f"Received request: {message}")
            response = {"status": "received"}

            # should bounce busy requests here, doesn't yet
            if thread.is_alive():
                #response["error"] = "Process Incomplete"
                #rep_socket.send_json(response)
                pass

            if shabam.stop.is_set():
                #response["error"] = "System stopped; homing required"
                pass

            # broken, needs debugging
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

            if message["command"] == "create_sample" and not thread.is_alive():
                thread = threading.Thread(target=shabam.add_sample, kwargs={"mountType": message["mount_type"],
                                                                            "sampleID": message["sample_id"],
                                                                            "initialHeight": message["initial_height"],
                                                                            "mmPerLayer": message["layer_height"],
                                                                            "width": message["width"],
                                                                            "height": message["height"],
                                                                            "useSmaractStage": message["sample_location"] == "SmarAct Stage"})
                thread.start()

            if message["command"] == "exe_sampling" and not thread.is_alive():
                status_data["module_status"] = "Random Sampling Running"
                status_data["total_image"] = message["total_image"]
                status_data["image_count"] = 0
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "random_sampling",
                                                                         "numImages": message["total_image"],
                                                                         "saveImages": False})
                thread.start()

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

            if message["command"] == "exe_homing_xy" and not thread.is_alive():
                status_data["module_status"] = "Homing XY"
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "home_xy"})
                thread.start()

            if message["command"] == "exe_homing_all" and not thread.is_alive():
                status_data["module_status"] = "Homing All"
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "home_all"})
                thread.start()

            if message["command"] == "exe_goto" and not thread.is_alive():
                status_data["module_status"] = "Changing Position"
                thread = threading.Thread(target=shabam.execute, kwargs={"targetMethod": "go_to",
                                                                         "x": message["req_x_pos"],
                                                                         "y": message["req_y_pos"],
                                                                         "z": message["req_z_pos"]})
                thread.start()




            if message["command"] == "exe_goto_preset_measure" and not thread.is_alive():
                status_data["module_status"] = "Preset Move + Measure"
                thread = threading.Thread(
                    target=shabam.execute,
                    kwargs={
                        "targetMethod": "move_to_preset_and_measure",
                        "num_measurements": 2
                    }
                )
                thread.start()



            if message["command"] == "exe_update_image" and not thread.is_alive():
                status_data["module_status"] = "Capturing Image"
                def _capture_then_idle():
                    shabam.execute(targetMethod="update_image")
                    status_data["module_status"] = "Idle"
                thread = threading.Thread(target=_capture_then_idle)
                thread.start()

            # resets counter before a SmarAct capture sequence
            if message["command"] == "exe_reset_image_count" and not thread.is_alive():
                thread = threading.Thread(target=shabam.reset_image_count)
                thread.start()

            # SmarAct per-point capture, advances counter
            if message["command"] == "exe_scan_capture" and not thread.is_alive():
                status_data["module_status"] = "Capturing Image"
                def _scan_capture_then_idle():
                    shabam.execute(targetMethod="capture_scan_image")
                    status_data["module_status"] = "Idle"
                thread = threading.Thread(target=_scan_capture_then_idle)
                thread.start()

            # one-time z-axis autofocus for smaract scan
            if message["command"] == "exe_smaract_autofocus" and not thread.is_alive():
                status_data["module_status"] = "Changing Position"
                thread = threading.Thread(target=shabam.execute, kwargs={
                    "targetMethod": "auto_focus",
                    "zMin": message["z_min"],
                    "zMax": message["z_max"],
                    "stepSize": message["step_size"],
                })
                thread.start()

            if message["command"] == "exe_reset_alarm_status" and not thread.is_alive():
                with shabam.alarmLock:
                    shabam.alarmStatus = "None"

            if message["command"] == "exe_stop":
                status_data["module_status"] = "Stopping..."
                shabam.stop.set()
                status_data["module_status"] = "Idle"

            rep_socket.send_json(response)

        # leftover from a non-blocking recv, probably dead code
        except zmq.Again:
            if status_data["module_status"] != "Idle" and thread.is_alive() == False:
                status_data["module_status"] = "Idle"


#---------------------------- Threading ------------------------------------------#

status_thread = threading.Thread(target=send_status_updates, daemon=True)
status_thread.start()

request_thread = threading.Thread(target=handle_request, daemon=True)
request_thread.start()

try:
    while True :
        time.sleep(1)  # avoid busy-spinning main thread
except KeyboardInterrupt:
    print("Server interrupted and shutting down.")
