import math

def temperature_to_rgb(temperature):
    """
    Convert a color temperature (in Kelvin) to an RGB triple.
    The temperature is first scaled by dividing by 100.
    Returns red, green, blue values (floats in the range 0-255).
    """
    # Scale the temperature
    temp = float(temperature) / 100.0

    # Calculate Red
    if temp <= 66:
        red = 255
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        red = max(0, min(red, 255))

    # Calculate Green
    if temp <= 66:
        green = 99.4708025861 * math.log(temp) - 161.1195681661
        green = max(0, min(green, 255))
    else:
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)
        green = max(0, min(green, 255))

    # Calculate Blue
    if temp >= 66:
        blue = 255
    elif temp <= 19:
        blue = 0
    else:
        blue = 138.5177312231 * math.log(temp - 10) - 305.0447927307
        blue = max(0, min(blue, 255))

    return red, green, blue

def temperature_to_white_balance(temperature):
    """
    Converts a Kelvin temperature to a white balance control dictionary.
    This function computes an RGB value using the Kelvin-to-RGB conversion,
    then derives red and blue multipliers relative to the green channel.
    The returned dictionary is formatted to be passed into picamera2's set_controls().
    
    Example output:
        {
          "awb_enable": False,
          "awb_gains": (red_gain, blue_gain)
        }
    """
    red, green, blue = temperature_to_rgb(temperature)
    # Use green as the reference channel. Prevent division by zero.
    if green == 0:
        red_gain, blue_gain = 1.0, 1.0
    else:
        red_gain = red / green
        blue_gain = blue / green

    return {"awb_enable": False, "awb_gains": (red_gain, blue_gain)}

# Example usage:
if __name__ == "__main__":
    kelvin_temp = 6000  # Ring light color temp
    controls = temperature_to_white_balance(kelvin_temp)
    print(f"For {kelvin_temp}K, white balance controls: {controls}")
    # In your Picamera2 code, you would use:
    # picam2.set_controls(controls)
