import subprocess
import os

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
            Defaults above are for Windows install. For Linux the defaults are 
            fiji_path (str, optional): /home/graeme/Fiji/ImageJ
            macro_path (str, optional): /home/graeme/Fiji/macros/StichingMacro.ijm
        """
         
        self.fiji_path = fiji_path or os.path.join(os.path.expanduser('~'), "Fiji", "ImageJ")
        self.macro_path = macro_path or os.path.join(os.path.expanduser('~'), "Fiji", "macros", "StitchingMacro.ijm")
    

    def run_stitching(self, grid_x, grid_y, input_dir, output_dir, sample_id):
        """
        Run the image stitching macro in Fiji/ImageJ via xvfb-run.

        Args:
            grid_x (int): Number of images along the X axis in the grid.
            grid_y (int): Number of images along the Y axis in the grid.
            input_dir (str): Path to the folder containing input images.
            output_dir (str): Path to the folder where stitched images will be saved.
            sample_id (str): Unique identifier for the current sample (used in naming outputs).
        """

        macro_args = f'{grid_x},{grid_y},{input_dir},{output_dir},{sample_id}'

        print("=" * 60)
        print("FIJI SUBPROCESS LAUNCH")
        print(f"  fiji_path  : {self.fiji_path}")
        print(f"  macro_path : {self.macro_path}")
        print(f"  macro_args : {macro_args}")
        print("=" * 60)

        try:
            result = subprocess.run(
                ["xvfb-run", "-a", self.fiji_path, "-macro", self.macro_path, macro_args],
                capture_output=True,
                text=True
            )

            print("--- FIJI STDOUT ---")
            print(result.stdout if result.stdout.strip() else "(no stdout)")
            print("--- FIJI STDERR ---")
            print(result.stderr if result.stderr.strip() else "(no stderr)")
            print("--- END FIJI OUTPUT ---")

            if result.returncode != 0:
                print(f"[WARNING] Fiji exited with non-zero return code: {result.returncode}")
            else:
                print("Stitching process finished successfully.")

        except Exception as e:
            print()
            print("!" * 60)
            print("!!! FIJI SUBPROCESS FAILED TO LAUNCH !!!")
            print(f"!!! Exception type : {type(e).__name__}")
            print(f"!!! Exception msg  : {e}")
            print(f"!!! fiji_path used : {self.fiji_path}")
            print(f"!!! Does fiji_path exist? {os.path.exists(self.fiji_path)}")
            print("!" * 60)
            print()
