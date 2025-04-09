# Overview
The purpose of this code is to communicate user requests to the Optical module code (i.e. Raspberry Pi). User requests are handled in a Graphical User Interface (GUI).
The code is designed to be run on a Windows PC that is connected to the Raspberry Pi with an Ethernet cable.

<p align="center">
  <img src="../../Images/Diagrams/RPFlowChart.drawio.png" alt="Raspberry Pi Program Diagram" width="700"/>
</p>

---
# Files

## opticalmodule.py
All the Python files for the PC, except for main, are simply classes. Main instantiates objects from the other Python files and then starts the program. It also assists with closing the sockets and the program smoothly when the GUI exits.

## rpmain.py
This Python file handles opening and closing sockets. The Python library to handle the sockets is ZeroMQ. There are two sockets used:


### Instantiation
At the top of the program, many variables are instantiated. Without some of these instantiations, errors may arise as some variables are updated every second from the Raspberry Pi, but would otherwise only be instantiated if that particular screen where the variable is displayed is open.

Note that it is in this section where the folder paths are instantiated. Change these directories as needed to match your directory.

### Graphics
Most of the code is simply widgets, frames, buttons, etc. to display the GUI. Key functionality to note is that many of the buttons use functions that send data to the Raspberry Pi. For example, the section of code that programs the "Stop" button will also have the code that sends the command to the Raspberry Pi.

### Communication
This section of code includes the image transferring (i.e., using transfer_files.py), code for starting the stitching thread, and the step-by-step processes for handling scanning and sampling processes. There are two key functions I want to note:

**update_status_data**

This function is run every second on a separate thread as it is used in the CommunicationHandler object. This function is run every second, so to ensure thread safety, only unpacking JSON data should be completed here, and everything else should be completed on the main thread.

**update_gui_elements**

This function is called within the update_status_data function like so:

`self.content_frame.after(0, self.update_gui_elements)`

This ensures all actions that need to take place in response to the Raspberry Pi's live data should happen here. This is where significant updates are coded, as well as the "state machine"-like code for running scanning and sampling.
Note that anything that takes more than ~1 second will cause the code to crash, as the function is called every second. Therefore, for any functions that require more time, run that function on a separate thread. For example, this is done for stitching as well as transferring the files from the Raspberry Pi.


---
# In Progress
## Calibration Routine
The platform and camera are leveled and aligned manually. To "calibrate" the camera should return focus score at each corner of the platform to assist the user in knowing what to level/adjust.

## Starting Raspberry Pi Remotely
Currently, there is code in main.py (i.e., run_rpi_python_file function) that can successfully start the Raspberry Pi upon running main.py on the PC. However, there is not any code yet that will close the sockets on the Raspberry Pi when the GUI closes, like there is in main.py. This needs to be completed before run_rpi_python_file should be uncommented.
