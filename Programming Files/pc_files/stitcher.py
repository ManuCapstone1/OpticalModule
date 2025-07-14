import subprocess

class ImageStitcher:
    """
    Handles image stitching using Fiji/ImageJ and a predefined macro script.
    """

    def __init__(self, fiji_path=None, macro_path=None):
        """
        Initialize the ImageStitcher with default or custom paths to Fiji/ImageJ and the macro.

        Args:
            fiji_path (str, optional): Path to the Fiji executable. Defaults to 'C:\\Fiji.app\\ImageJ-win64.exe'.
            macro_path (str, optional): Path to the ImageJ macro file. Defaults to 'C:\\Fiji.app\\macros\\StitchingMacro.ijm'.
        """
         
        self.fiji_path = fiji_path or r"C:\\Fiji.app\\ImageJ-win64.exe"
        self.macro_path = macro_path or r"C:\\Fiji.app\\macros\\StitchingMacro.ijm"
    

    def run_stitching(self, grid_x, grid_y, input_dir, output_dir, sample_id):
        """
        Run the image stitching macro in Fiji/ImageJ in headless mode.

        Args:
            grid_x (int): Number of images along the X axis in the grid.
            grid_y (int): Number of images along the Y axis in the grid.
            input_dir (str): Path to the folder containing input images.
            output_dir (str): Path to the folder where stitched images will be saved.
            sample_id (str): Unique identifier for the current sample (used in naming outputs).

        Notes:
            - Uses Fiji in headless mode to avoid launching the GUI.
            - Errors are caught and printed, but not re-raised.
        """
         
        try:
            macro_args = f'{grid_x},{grid_y},{input_dir},{output_dir},{sample_id}'

            # Use --console to debug with console output. Disabled in final use.
            # Example with console output:
            # subprocess.run([self.fiji_path, "--headless", "--console", "-macro", self.macro_path, macro_args], check=True)
            
            subprocess.run([self.fiji_path, "--headless", "-macro", self.macro_path, macro_args], check=True)
            print("Stitching process finished.")
        except subprocess.CalledProcessError as e:
            print(f"Error running stitching macro: {e}")
