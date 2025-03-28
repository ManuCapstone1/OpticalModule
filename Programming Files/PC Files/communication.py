import zmq
import time

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


    def send_data(self, data, retries=3, delay=2):
        '''
        Purpose: Send data to Raspberry Pi from PC, used as needed, called in gui.py
        Parameters: data: json object
        Return: response: json object response from raspberry pi
        '''

        for attempt in range(retries):
            try:
                self.req_socket.send_json(data)
                response = self.req_socket.recv_json()  # Blocking call, don't make it blocking
                return response
            except zmq.Again:  # In case of timeout or no response
                if attempt < retries - 1:
                    time.sleep(delay)
                    print(f"Retrying... attempt {attempt + 1}")
                else:
                    print(f"Failed to get response after {retries} attempts.")
                    return {"error": "Timeout", "message": "No response from Raspberry Pi"}
            except Exception as e:
                print(f"Error sending data: {e}")
                return {"error": "Send Error", "message": str(e)}

    def receive_status_updates(self, gui, stop_event):
        """
        Purpose: Receive updates in json file from raspberry pi as suscriber every ~1 second
        Parameters: gui.py
        """
        while not stop_event.is_set():
            try:
                # Receive the status update from Raspberry Pi
                status_data = self.sub_socket.recv_json(flags=zmq.NOBLOCK)
                #Status updates sent to terminal for debugging
                print(f"Received status update: {status_data['module_status']} {status_data['image_count']} {status_data['total_image']} {status_data['curr_sample_id']}")

                # Update the GUI with received status data
                gui.after(0, gui.update_status_data, status_data)
            except zmq.Again:
                stop_event.wait(0.1)  # Reduce CPU usage by waiting instead of busy looping
            except Exception as e:
                print(f"Error receiving status update: {e}")
                time.sleep(1)  # Avoid flooding errors

    def close(self):
        """
        Cleanup sockets when closing
        Called when gui window closes
        """

        self.req_socket.close()
        self.sub_socket.close()
        self.context.term()