# Overview
The purpose of this code is to communicate user requests to the Optical module code (i.e. Raspberry Pi). User requests are handled in a Graphical User Interface (GUI). 
The code is designed to be run on a Windows PC that is connected to the Raspberry Pi with an ethernet cable.

![pc files diagram](../../Images/Diagrams/pc_files_flow.png)

---
# Files

## main.py
All the python files for the pc, except for main, are simply classes. Main instantiates objects from the other python files, and then starts the program. It also assists with closing the sockests and program smoothly when the gui exits.

## communication.py
This python file handles opening and closing sockets. The python library to handle the sockets is ZeroMQ. There are two sockets used:

**SUB Socket**
The subscriber socket works in tandem with the Raspberry Pi's publisher socket. The Raspberry Pi sends live data to the PC every second.
This is run on a seperate thread, so that it can continue to get updates asynchronously.

**REQ Socket**
The request socket works in tandem with the Raspberry Pi's response socket. This is used to send JSON objects to the Raspberry Pi to detail user requests (e.g. exe_stop, number of sampling images).

**Note**
The IP address, host name, and password are hardcoded into the code. Change as needed to fit the specs of your Raspberry Pi, or whichever device you use.

![pc files diagram](../../Images/Diagrams/communication_graphic.png)

## stitcher.py
The stitcher program runs a macro that passes in arguments to ImageJ (i.e. FiJi). The image stitching process takes some time (up to 2 minutes). Therefore, this process is also run on a seperate thread when it is called.

## transfer_files.py
Images are stored in a folder on the Raspberry Pi called "image_buffer", regardles of the process being executed. A SFTP client connection must be opened in order to transfer those firles from a directory in the Rapsberry Pi, over to a directory in the PC. Fuurthermore, to empty the "image_buffer" folder, a SSH client connection is created and then closed after completeion. This python file handles all this communication and connections.

## gui.py
gui.py is basically the "main" code, as it handles all the graphical parts of the GUI, as well as uses the objects from the other files to communicate and sequence the use requests to the Raspberry Pi.

The code can be seperated into three main chunks, in order of how it was written: instantiation of variables, graphical components, message handling with the Raspberry Pi.



## Tips
1. Directories for where the images are stored in both the PC and Raspberry Pi are hard-coded into the code. When adapting to your code, ensure you change these directories.
2. Don't send any requests to the Raspberry Pi until it has been connexted. Look at the top left corner of the GUI to ensure the module status says "Idle".
3. If "Stop" is executed, the system needs to be re-homed.

---
# In Progress
## Calibration Routine
The platform and camera are leveled and aligned manually. To "calibrate" the camera should return focus 

## Starting Raspberry Pi Remotely
Currently, there is code in main.py (ie run_rpi_python_file function) that can succesfully start the Raspberry Pi upon running main.py on the PC. However, there is not any code yet that will close the sockets on the Raspberry Pi when the GUI closes, like there is in main.py. This needs to be completed before run_rpi_python_file should be uncommented.
