import zmq
import threading

class CommunicationHandler:
    def __init__(self):
        self.context = zmq.Context()

        #Requesting socket for PC
        self.req_socket = self.context.socket(zmq.REQ)
        self.req_socket.connect("tcp://192.168.1.111:5555")

        #Suscribing socket for PC
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect("tcp://192.168.1.111:5556")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    #Function: send_data
    #Purpose: Send data to Raspberry Pi from PC, used as needed, called in gui.py
    #Parameters: data: json object
    #Return: response: json object response from raspberry pi
    def send_data(self, data):
        try:
            # Send data to Raspberry Pi
            self.req_socket.send_json(data)
            # Receive acknowledgment from Raspberry Pi
            response = self.req_socket.recv_json()
            return response
        except Exception as e:
            print(f"Error sending data: {e}")
            return None
    
    #Function: receive_status_updates
    #Purpose: Receive updates in json file from raspberry pi as suscriber every ~1 second
    #Parameters: gui.py
    def receive_status_updates(self, gui):
        """Listen for status updates from the Raspberry Pi and update the GUI."""
        while True:
            try:
                # Receive the status update from Raspberry Pi
                status_data = self.sub_socket.recv_json()
                print(f"Received status update: {status_data}")

                # Update the GUI with received status data
                gui.after(0, gui.update_status_data, status_data)
            except Exception as e:
                print(f"Error receiving status update: {e}")

