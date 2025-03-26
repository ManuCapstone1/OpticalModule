import threading
from gui import MainApp
from communication import CommunicationHandler
from tkinter import messagebox
from stitcher import ImageStitcher

def main():

    gui = MainApp() #Instantiate gui
    stop_event = threading.Event()  #Stop event for killing theads when gui closes

    '''Setup communication and thread for raspberry pi'''
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

    '''Image stitcher setup'''
    try:
        stitcher = ImageStitcher() #instantiate image stitcher
        gui.set_stitcher(stitcher) #Setup stitcher in gui

    except Exception as e:
        messagebox.showerror("Error", f"Could not setup image stitcher: {e}")

    #Closes sockets and gui
    def on_closing():
        stop_event.set()  # Signal the thread to stop
        gui.destroy()  # Close the GUI
        comms.close() # Close ZMQ sockets

    gui.protocol("WM_DELETE_WINDOW", on_closing)

    gui.mainloop() #Start gui

#START
if __name__ == "__main__":
    main()
