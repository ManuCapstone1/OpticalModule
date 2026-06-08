import socket
import time

# Controller configuration
IP_ADDRESS = "169.254.0.20"  # Preset IP address for the CL controller
PORT = 24685  # Port set in the CL_Navigator software, under the Environment menu
TIMEOUT = 2.0

def send_command(command, s):
    command_code = command[:2]

    s.sendall(command.encode('ascii'))
    response = s.recv(1024).decode('ascii')

    if response.startswith("R0"):
        print("Set to measurement mode")
    elif response.startswith(command_code):
        data = response.split(',')
        measurement_value = data[1].strip()
        return float(measurement_value)
    else:
        print(f"Unexpected response: {response}")
        return None

def continuous_measurement():
    try:
        # Create a TCP/IP socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((IP_ADDRESS, PORT))

            # Send command to switch controller to measurement mode
            measurement_mode_command = "R0\r"
            send_command(measurement_mode_command, s)
            
            print("\nReading continuous measurements. Press Ctrl+C to stop.")
            print("-" * 50)

            # Loop forever until the user stops the script
            while True:
                # Command format: MS, measurement value (1-7), out # (1-8)\r
                command = "MS,1,1\r"
                
                # Sends command to take a measurement and stores the returned value
                returned_value = send_command(command, s)

                if returned_value is not None:
                    print(f"Measured Distance: {returned_value} mm          ", end="\r")

                # Wait half a second
                time.sleep(0.5)

    except KeyboardInterrupt:
        # Catches Ctrl+C
        print("\n\nMeasurement stopped by user.")
    except Exception as e:
        print(f"\nConnection error: {e}")

# Usage
if __name__ == "__main__":
    continuous_measurement()