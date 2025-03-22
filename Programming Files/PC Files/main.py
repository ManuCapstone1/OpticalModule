import threading
from gui import MainApp
from communication import CommunicationHandler
from tkinter import messagebox
from stitcher import ImageStitcher

def main():

    #Instantiate gui app
    gui = MainApp() 

    #--------------Setup communication and thread for raspberry pi -----------------------
    try:
        comms = CommunicationHandler() #instantiate communication handler

        #Connect communication between GUI and Raspberry Pi
        gui.set_communication(comms)

        #Start thread for receiveing constant data status from raspberry pi
        status_thread = threading.Thread(target=comms.receive_status_updates, args=(gui,), daemon=True)
        status_thread.start()

    #Throw exception if raspberry pi is offline   
    except Exception as e:
        messagebox.showerror("Error", f"Could not establish communcation: {e}")

    #------------------------- Setup image stitcher --------------------------------
    try:
        stitcher = ImageStitcher() #instantiate image stitcher
        gui.set_stitcher(stitcher) #Setup stitcher in gui
        
    #Throw error if image stitcher fails
    except Exception as e:
        messagebox.showerror("Error", f"Could not setup image stitcher: {e}")

    #Open and start GUI app
    gui.mainloop()

#START ALL PC CODE HERE
if __name__ == "__main__":
    main()
