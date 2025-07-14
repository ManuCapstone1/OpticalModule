import threading
import paramiko
from gui import MainApp
from communication import CommunicationHandler
from tkinter import messagebox
from stitcher import ImageStitcher
from transfer_files import RaspberryPiTransfer

#Currently not being used, starting remotely works!
#BUT need to figure out how to close sockets on Raspberry Pi upon closing GUI on PC
def run_rpi_python_file():
    """
    SSH into the Raspberry Pi and execute a Python script remotely.

    This function connects to the Raspberry Pi using Paramiko, activates a
    virtual environment, and runs the main Python script (`rpmain.py`) that
    controls the mechanical system.

    If there's an error, it is displayed in a message box.
    """

    try:
        # Setup SSH connection to the Raspberry Pi
        rpi_ip = "192.168.1.111" 
        rpi_username = "microscope" 
        rpi_password = "microscope" 

        # Create an SSH client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Automatically add host keys

        # Connect to the Raspberry Pi
        client.connect(rpi_ip, username=rpi_username, password=rpi_password)

        # Command to run the Python file on the Raspberry Pi
        #Fist activate virtual environment, then start rpmain.py
        command = 'source /home/microscope/DIY_Eng_CV/bin/activate && python3 /home/microscope/rpmain.py'

        # Run the command
        stdin, stdout, stderr = client.exec_command(command)

        # Get output and error
        output = stdout.read().decode()
        error = stderr.read().decode()

        if output:
            print(f"Output: {output}")
        if error:
            print(f"Error: {error}")

        # Close the SSH connection
        client.close()

    except Exception as e:
        print(f"Error running Python file on Raspberry Pi: {e}")
        messagebox.showerror("Error", f"Could not run the Raspberry Pi Python file: {e}")

def main():
    """
    Initializes and starts the main GUI application.

    - Sets up communication with the Raspberry Pi over ZeroMQ.
    - Starts a background thread to receive status updates.
    - Initializes the image stitcher.
    - Sets up file transfer functionality.
    - Optionally starts the Raspberry Pi script over SSH. (Work in Progress)
    - Defines shutdown behavior when the GUI window closes.
    """

    gui = MainApp() #Instantiate gui
    stop_event = threading.Event()  #Stop event for killing theads when gui closes

    #Setup communication and thread for raspberry pi
    try:
        comms = CommunicationHandler() #instantiate communication handler

        #Connect communication between GUI and Raspberry Pi
        gui.set_communication(comms, stop_event)

        #Start thread for receiveing constant data status from raspberry pi
        status_thread = threading.Thread(target=comms.receive_status_updates, args=(gui, stop_event), daemon=True)
        status_thread.start()
     
        gui.stop_event = stop_event

    #Throw exception if raspberry pi is offline   
    except Exception as e:
        messagebox.showerror("Error", f"Could not establish communcation: {e}")

    #Image stitcher setup
    try:
        stitcher = ImageStitcher() #instantiate image stitcher
        gui.set_stitcher(stitcher) #Setup stitcher in gui

    except Exception as e:
        messagebox.showerror("Error", f"Could not setup image stitcher: {e}")

    #Raspberry Pi file transfer setup
    try:
        transfer = RaspberryPiTransfer()
        gui.set_rpi_transfer(transfer)

    except Exception as e:
        messagebox.showerror("Error", f"Could not transfer files: {e}")
    
    #Incomplete.
    # Run Raspberry Pi Python script via SSH in the background
    # Power cycle raspbery pi in order to reset sockets, or implement code to close sockets when gui closes
    threading.Thread(target=run_rpi_python_file, daemon=True).start()

    def on_closing():  
        """
        Callback function for closing the GUI window.

        - Stops all background threads.
        - Closes the GUI.
        - Cleans up communication sockets.
        """

        stop_event.set() 
        gui.destroy() 
        comms.close()

    gui.protocol("WM_DELETE_WINDOW", on_closing)

    gui.mainloop() #Start gui event loop

#START
if __name__ == "__main__":
    main()
