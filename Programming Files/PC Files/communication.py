import zmq
import threading

class CommunicationHandler:
    def __init__(self):
        self.context = zmq.Context()

        #Requesting socket
        self.req_socket = self.context.socket(zmq.REQ)
        self.req_socket.connect("tcp://raspberrypi_ip:5555")

        #Suscribing socket
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect("tcp://raspberrypi_ip:5556")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    #Called within gui.py
    #Used as needed
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
    
    #Called in thread periodically in main
    def receive_status_updates(self, gui):
        """Listen for status updates from the Raspberry Pi and update the GUI."""
        while True:
            try:
                # Receive the status update from Raspberry Pi
                status_data = self.sub_socket.recv_json()
                print(f"Received status update: {status_data}")

                # Update the GUI with received status data
                gui.update_status_data(status_data)

            except Exception as e:
                print(f"Error receiving status update: {e}")
