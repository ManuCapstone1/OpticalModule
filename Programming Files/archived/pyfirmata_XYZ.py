from pyfirmata import Arduino, util, SERVO
import time
import pyfirmata

# Define pin numbers
enPin = 8
stepXPin = 2
dirXPin = 5
stepYPin = 3
dirYPin = 6
stepZPin = 4
dirZPin = 7

# Motion parameters
stepsPerRev = 200
pulseWidthMicros = 0.0001  # Converted to seconds
millisBtwnSteps = 0.001  # Converted to seconds

# Initialize board (Change 'COM3' to your board's port)
board = Arduino('/dev/ttyUSB0')  # Change to your serial port

# Set pin modes
board.digital[enPin].write(0)  # Enable stepper driver
board.digital[stepXPin].mode = pyfirmata.OUTPUT
board.digital[dirXPin].mode = pyfirmata.OUTPUT
board.digital[stepYPin].mode = pyfirmata.OUTPUT
board.digital[dirYPin].mode = pyfirmata.OUTPUT
board.digital[stepZPin].mode = pyfirmata.OUTPUT
board.digital[dirZPin].mode = pyfirmata.OUTPUT

def make_move(delta_x, delta_y):
    delta_a = delta_x + delta_y
    delta_b = delta_x - delta_y
    
    steps_a = abs(round(delta_a / 0.212058))
    steps_b = abs(round(delta_b / 0.212058))
    
    board.digital[dirXPin].write(1 if delta_a >= 0 else 0)
    board.digital[dirZPin].write(1 if delta_b >= 0 else 0)
    
    for _ in range(steps_a):
        board.digital[stepXPin].write(1)
        board.digital[stepZPin].write(1)
        time.sleep(pulseWidthMicros)
        board.digital[stepXPin].write(0)
        board.digital[stepZPin].write(0)
        time.sleep(millisBtwnSteps)

def make_z_move(delta_z):
    steps_z = abs(round(delta_z / 0.01))
    
    board.digital[dirZPin].write(1 if delta_z >= 0 else 0)
    
    for _ in range(steps_z):
        board.digital[stepZPin].write(1)
        time.sleep(pulseWidthMicros)
        board.digital[stepZPin].write(0)
        time.sleep(millisBtwnSteps)
	
        # Uncomment the following for additional movement
        # print("Step 2")
        # make_z_move(-5)
        # time.sleep(5)

if __name__ == '__main__':
    board = board
    print("Communication Successfully started")
    
while True:
	
    make_z_move(1)
    time.sleep(1)
    make_z_move(-1)
    time.sleep(1)
















































