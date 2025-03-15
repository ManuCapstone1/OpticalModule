import threading
from gui import MainApp
from communication import CommunicationHandler
from tkinter import messagebox

def main():
    gui = MainApp() #instantiate gui
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

    #Open and start GUI
    gui.mainloop()

if __name__ == "__main__":
    main()
