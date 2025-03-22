import subprocess
import os

class ImageStitcher:
    def __init__(self, fiji_path=None, macro_path=None):
        """Initialize Stitcher with paths to Fiji/ImageJ and the macro file."""
        self.fiji_path = fiji_path or r"C:/Fiji.app/ImageJ-win64.exe"
        self.macro_path = macro_path or r"C:/Fiji.app/macros/StitchingMacro.ijm"

    def run_stitching(self):
        """Runs the image stitching macro in Fiji/ImageJ."""
        try:
            subprocess.run([self.fiji_path, "--headless", "-macro", self.macro_path], check=True)
            print("Stitching process finished successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error running stitching macro: {e}")
