import subprocess

class ImageStitcher:

    #Initialize Stitcher with paths to Fiji/ImageJ and the macro file.
    def __init__(self, fiji_path=None, macro_path=None):
        self.fiji_path = fiji_path or r"C:\\Fiji.app\\ImageJ-win64.exe"
        self.macro_path = macro_path or r"C:\\Fiji.app\\macros\\StitchingMacro.ijm"
    
    #Runs the image stitching macro in Fiji/ImageJ.
    def run_stitching(self, grid_x, grid_y, input_dir, output_dir, sample_id):
         
        try:
            macro_args = f'{grid_x},{grid_y},{input_dir},{output_dir},{sample_id}'

            #Use --console to enable Fiji to write to console. DO NOT use for final code
            #Example: subprocess.run([self.fiji_path, "--headless", "--console", "-macro", self.macro_path, macro_args], check=True)
            subprocess.run([self.fiji_path, "--headless", "-macro", self.macro_path, macro_args], check=True)
            print("Stitching process finished.")
        except subprocess.CalledProcessError as e:
            print(f"Error running stitching macro: {e}")
