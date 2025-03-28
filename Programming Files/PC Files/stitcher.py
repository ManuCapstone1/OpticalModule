import subprocess

class ImageStitcher:

    #Initialize Stitcher with paths to Fiji/ImageJ and the macro file.
    def __init__(self, fiji_path=None, macro_path=None):
        self.fiji_path = fiji_path or r"C:\\Fiji.app\\ImageJ-win64.exe"
        self.macro_path = macro_path or r"C:\\Fiji.app\\macros\\StitchingMacro.ijm"

        
    
    #Runs the image stitching macro in Fiji/ImageJ.
    def run_stitching(self, grid_x, grid_y, input_dir, output_dir, sample_id):

        print(grid_x)
        print(grid_y)
        print(input_dir)
        print(output_dir)
        print(sample_id)
        
        try:
            macro_args = f'{grid_x},{grid_y},"{input_dir}","{output_dir}","{sample_id}"'
# trying with an extra flag --console to try to redirect the print statements and the error messages to the command prompt
# the bad side effect with --console is that it prevents the command prompt from "returning" after execution
#            subprocess.run([self.fiji_path, "--headless", "--console", "-macro", self.macro_path, macro_args], check=True)
#
# something to try, get rid of the --headless so that the GUI opens and the macro executes
            print([self.fiji_path, "--headless", "-macro", self.macro_path, macro_args])
            subprocess.run([self.fiji_path, "--headless", "-macro", self.macro_path, macro_args], check=True)
            print("Stitching process finished successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error running stitching macro: {e}")
