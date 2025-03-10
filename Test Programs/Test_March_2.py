import time
import pyfirmata
from pyfirmata import Arduino, util

# Change this to your Arduino's port (e.g., 'COM3' for Windows, '/dev/ttyUSB0' for Linux/Mac)
PORT = '/dev/ttyUSB0'  # Update as needed

# Connect to Arduino
board = Arduino(PORT)
PIN = 9 # Pin to test

# Start an iterator thread to prevent buffer overflow
it = util.Iterator(board)
it.start()

board.digital[PIN].write(1)  # Enable pull-up resistor (by writing HIGH to input pin)


# Set pin 9 as an input

#board.send_sysex(0xF4, [PIN, 0x02])  # 0xF4 is SET_PIN_MODE, 0x02 is INPUT_PULLUP

board.digital[PIN].mode = 0  # Set pin mode to OUTPUT (1)

print(f"Reading input from pin {PIN}... Press Ctrl+C to stop.")

try:
    while True:
        pin_state = board.digital[PIN].read()  # Read the pin state (HIGH or LOW)
        
        if pin_state is None:
            print("Waiting for valid reading...")
        else:
            print(f"Pin 9 State: {'HIGH' if pin_state else 'LOW'}")

        if pin_state is False:  # If the pin is LOW (triggered)
            # print("Pin triggered! Resetting to HIGH...")
            # Reset the pin to HIGH (manually write HIGH to the pin)
            board.digital[PIN].mode = 1  # Set pin mode to OUTPUT (1)
            board.digital[PIN].write(1)  # Set the pin HIGH to reset it
            board.digital[PIN].mode = 0  # Set pin mode back to INPUT_PULLUP (2)
        
        time.sleep(0.5)  # Adjust reading frequency if needed

except KeyboardInterrupt:
    print("\nExiting...")
    board.exit()
