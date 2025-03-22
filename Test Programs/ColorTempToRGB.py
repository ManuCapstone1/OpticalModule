import math

def temperature_to_rgb(temperature):
    """
    Convert a color temperature in Kelvin (typically between 1000K and 40000K)
    to an RGB color tuple.
    
    Parameters:
        temperature (float): Temperature in Kelvin.
        
    Returns:
        tuple: (red, green, blue) values as integers (0-255)
    """
    # Scale the temperature by dividing by 100 as per pseudocode.
    temp = float(temperature) / 100.0

    # Calculate Red
    if temp <= 66:
        red = 255
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        red = max(0, min(red, 255))  # Clamp between 0 and 255

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

    # Round the values to the nearest integer and return as a tuple.
    return int(round(red)), int(round(green)), int(round(blue))


# Example usage:
if __name__ == "__main__":
    kelvin_temp = 6000 
    rgb = temperature_to_rgb(kelvin_temp)
    print(f"Temperature {kelvin_temp}K -> RGB: {rgb}")
