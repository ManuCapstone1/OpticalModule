import pyfirmata

#Level 0 Classes

class StepperMotor:
    def __init__(self, step_pin, dir_pin, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.board = board
        self.step_pin = board.get_pin(f'd:{step_pin}:o')
        self.dir_pin = board.get_pin(f'd:{dir_pin}:o')

class LimitSwitch:
    def __init__(self, pin, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.pin = board.get_pin(f'd:{pin}:i')

    def is_pressed(self):
        """Returns True if the switch is triggered."""
        status = self.pin.read() == 0 # Assuming LOW means triggered
        if status:
            self.pin.mode() = 1
            self.pin.write(1)
            self.pin.mode() = 0
        return status  



#Level 1 Classes

class Homing:
    def __init__(self, board=pyfirmata.Arduino("/dev/ttyUSB0")):
        self.board = board
        self.x_motor = StepperMotor(board, step_pin=2, dir_pin=5, enable_pin=8)
        self.y_motor = StepperMotor(board, step_pin=3, dir_pin=6, enable_pin=8)
        self.z_motor = StepperMotor(board, step_pin=4, dir_pin=7, enable_pin=8)

        self.x_limit = LimitSwitch(board, 9)
        self.y_limit = LimitSwitch(board, 10)
        self.z_limit = LimitSwitch(board, 11)

    def home_axis(self, motor, limit_switch, direction):
        """Move an axis until its limit switch is triggered."""
        while not limit_switch.is_pressed():
            motor.move_steps(1, direction)

    def home_all(self):
        """Home all axes sequentially."""
        self.home_axis(self.y_motor, self.y_limit, direction=0)
        self.home_axis(self.x_motor, self.x_limit, direction=0)
        self.home_axis(self.z_motor, self.z_limit, direction=1)


#Level 2 Classes