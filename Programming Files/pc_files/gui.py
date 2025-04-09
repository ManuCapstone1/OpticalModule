import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageTk
from datetime import datetime
import json
import re
import os
import shutil
from threading import Thread

class MainApp(ctk.CTk):
    def __init__(self):
        """
        Initialize the main application window and set up variables, flags, and threading.
        This function also handles the creation of necessary folders and GUI appearance.
        Lastly, it handles the user requests from the GUI and sends them to the Raspberry Pi.
        """

        super().__init__()

        #====================================================================================#
        #----------------------------- Variables and Instantiation -------------------------#
        #====================================================================================# 

        #---------- Raspberry Pi JSON Keys instatiate ----------#
        #Module states and data
        self.module_status = "Raspberry Pi Not Connected"
        self.alarm_status = "Unknown"
        self.mode = "Manual"

        #Motion data
        self.motors_enabled = False
        self.x_pos = 0
        self.y_pos = 0
        self.z_pos = 0

        #Camera and image data
        self.exposure_time = 0
        self.analog_gain = 0
        self.contrast = 0
        self.colour_temp = 0

        self.total_image = 0
        self.image_count = 0
        self.curr_sample_id = "Unknown"

        # Disable decompression bomb protection for stitched image
        Image.MAX_IMAGE_PIXELS = None 

        #------ JSON Objects sent to Rapsberry Pi ------#
        #Sample data
        self.sample_data = {
            "command" :"Unknown",
            "mode" : "Unknown",
            "mount_type" : "Unknown",
            "sample_id" : "Unknown",
            "initial_height" : 0.0,
            "layer_height" : 0.0,
            "width" : 0.0,
            "height" : 0.0
        }

        #Random sampling method json data
        self.sampling_data = {
            "command" :"Unknown",
            "mode" : "Unknown",
            "module_status" : "Unknown",
            "total_images" : 0
        }

        #Scanning sampling method json data
        self.scanning_data = {
            "command" : "Unknown",
            "mode" : "Unknown",
            "module_status" : "Unknown",
            "step_x" : 0,
            "step_y" :0
        }

        #-------------- Flags/States -----------------#
        self.sample_loaded = False
        self.sampling_state = 0
        self.scanning_state = 0 

        #--------------- Threading -------------------#
        self.transfer_rpi_thread = Thread()
        self.transfer_pc_imgs = Thread()
        self.stitching_thread = Thread()

        #----------------- Status Labels ---------------#
        #Update motor pane labels
        self.rpi_motors_enabled_var = ctk.StringVar(value="--")
        self.rpi_x_pos_var = ctk.StringVar(value="--")
        self.rpi_y_pos_var = ctk.StringVar(value="--")
        self.rpi_z_pos_var = ctk.StringVar(value="--")

        #Update camera pane labels
        self.rpi_exposure_var = ctk.StringVar(value="--")
        self.rpi_analog_gain_var = ctk.StringVar(value="--")
        self.rpi_contrast_var = ctk.StringVar(value="--")
        self.rpi_colour_temp_var = ctk.StringVar(value="--")

        # Update last refreshed time, used in camera and motor pane
        self.last_refreshed_var = ctk.StringVar(value="Last Updated: --")

        #-------------------- Directories ---------------------#
        #Images for GUI aesthetics
        self.img_gui = "C:/Users/GraemeJF/Documents/Capstone/Images/GUI"    

        #Buffer folders
        #Raw string in order to pass to Fiji succesfully for image stitching
        self.buffer_stitching_folder = r"C:\\Users\\GraemeJF\\Documents\\Capstone\\Images\\buffer\\stitching"
        self.buffer_sampling_folder = "C:/Users/GraemeJF/Documents/Capstone/Images/buffer/sampling"
        self.buffer_testing_folder = "C:/Users/GraemeJF/Documents/Capstone/Images/buffer/camera_tests"

        #Completed folders
        self.complete_stitching_folder = "C:/Users/GraemeJF/Documents/Capstone/Images/complete/stitching"
        self.complete_sampling_folder = "C:/Users/GraemeJF/Documents/Capstone/Images/complete/sampling"

        #Raspberry Pi files
        self.rpi_transfer = None

        #--------------------- GUI Appearance Variables ---------------------------#
        #Skeleton appearance
        self.title("Control Panel")
        self.geometry("950x650")
        self.minsize(900, 550)  # Set the minimum width and height
        ctk.set_appearance_mode("dark")  # Options: "dark", "light", "system"
        
        # Top & Bottom Frames
        self.create_top_frame()
        self.create_bottom_frame()

        # Content Frame
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(expand=True, fill='both')

        self.display_main_tab()

    #====================================================================================#
    #----------------------------- GUI Appearances and Main App -------------------------#
    #====================================================================================#

    #------------------------------- Main Frame ------------------------------------------#

    def create_top_frame(self):
        '''
        Creates the top frame that contains labels for module status, mode, current sample, 
        and alarm status.
        '''

        top_frame = ctk.CTkFrame(self)
        top_frame.pack(side=ctk.TOP, fill='x', padx=10, pady=5)
 
        self.status_label = ctk.CTkLabel(top_frame, text=f"Module Status: {self.module_status}")
        self.status_label.pack(side=ctk.LEFT, padx=10)

        self.mode_label = ctk.CTkLabel(top_frame, text=f"Mode: {self.mode}")
        self.mode_label.pack(side=ctk.LEFT, padx=30)

        self.sample_label = ctk.CTkLabel(top_frame, text=f"Current Sample: {self.curr_sample_id}")
        self.sample_label.pack(side=ctk.LEFT, padx=30)

        self.alarm_label = ctk.CTkLabel(top_frame, text=f"Alarms: {self.alarm_status}")
        self.alarm_label.pack(side=ctk.RIGHT, padx=10)

    def create_bottom_frame(self):
        '''
        Creates Bottom Frame with tab buttons and date and time
        '''

        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(side=ctk.BOTTOM, fill='x', padx=10, pady=5)

        tabs = ["Main", "Motion", "Image", "Details"]
        for tab in tabs:
            tab_btn = ctk.CTkButton(bottom_frame, text=tab, font=("Arial", 20), command=lambda t=tab: self.switch_tab(t))
            tab_btn.pack(side=ctk.LEFT, padx=5)

        self.date_time_label = ctk.CTkLabel(bottom_frame, text="", font = ("Arial", 14))
        self.date_time_label.pack(side=ctk.RIGHT, padx=5)
        self.update_time()

    def switch_tab(self, tab_name):
        '''
        Switches between different tabs on the bottom frame.

        Args:
            tab_name (str): The name of the tab to switch to.

        Returns:
            None
        '''   

        self.clear_frame(self.content_frame)

        if tab_name == "Main":
            self.display_main_tab()
        elif tab_name == "Motion":
            self.display_motion_tab()
        elif tab_name == "Image":
            self.display_image_tab()
        elif tab_name == "Details":
            self.display_details_tab()

    #Main Tab Frames
    def display_main_tab(self):
        """
        Displays the Main Frame with buttons on the left, and picture holder on the right
        """

        self.clear_frame(self.content_frame)

        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)

        self.main_right_frame = ctk.CTkFrame(self.content_frame, width=400, height=400)
        self.main_right_frame.pack(side=ctk.RIGHT, expand=True, fill='both')

        # Image Display on Right
        self.display_placeholder_image(self.main_right_frame)

        # Buttons on Left Side
        create_sample_btn = ctk.CTkButton(left_frame, text = "Create a New Sample", font = ("Arial", 20), 
                                          width = 200, height = 100, fg_color = "green", command = lambda: self.open_sample_dialog())
        sampling_btn = ctk.CTkButton(left_frame, text="Random Sampling", font=("Arial", 20), width = 200, height = 100, 
                                     command = lambda: self.open_sampling_dialog())
        scanning_btn = ctk.CTkButton(left_frame, text="Scanning", font=("Arial", 20), width = 200, height = 100, 
                                     command = lambda: self.open_scanning_dialog(self.main_right_frame))

        #Pack buttons
        create_sample_btn.pack(pady=5, fill='x')
        sampling_btn.pack(pady=5, fill='x')
        scanning_btn.pack(pady=5, fill='x')

        #Calibration button. Uncomment to use
        #"exe_calibration" is NOT currently seupt in Raspberry Pi (April 5, 2025)

        #calibration_btn = ctk.CTkButton(left_frame, width = 200, height = 50, text="Calibration", font=("Arial", 20),
        #                                command=lambda :self.send_simple_command("exe_calibration", True))
        #calibration_btn.pack(pady=5, fill='x')

    def display_placeholder_image(self, frame):
        '''
        Displays CAD image on the main tab in the right frame.

        Args:
            frame (ctk.CTkFrame): The frame in which the image will be displayed.
        
        Returns:
            None
        '''

        img = Image.open(f"{self.img_gui}/assy_centered.png")  # Path to CAD assembly image
        img = img.resize((1295, 1343), Image.LANCZOS)
        tilt_img = img.rotate(-1)

        img_ctk = ctk.CTkImage(tilt_img, size=(800, 800))

        img_label = ctk.CTkLabel(frame, image=img_ctk, text="")
        img_label.image = img_ctk  # Keep reference to the image

        # Center the image within the frame using place() method
        img_label.place(relx=0.5, rely=0.5, anchor="center")


    #------------------------------- Pop-up Windows ------------------------------------------#

    def open_sample_dialog(self):
        '''
        Pop-up window to enter in sample data parameters and then send to the Raspberry Pi.
        '''

        #Window setup
        sample_window = ctk.CTkToplevel(self)
        sample_window.title("Enter Sample Parameters")
        sample_window.geometry("330x450")
        sample_window.minsize(330, 450)
        sample_window.maxsize(330, 450)

        sample_window.grab_set()

        #Mount type (ie puck, stub), drop down menu
        ctk.CTkLabel(sample_window, text="Select your mount type:").grid(row = 0, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        mount_type = ctk.CTkComboBox(sample_window, values=["Puck", "Stub"])
        mount_type.grid(row = 1, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #Sample id input field
        ctk.CTkLabel(sample_window, text="Enter Sample ID:").grid(row=2, column=0, columnspan=4, padx=1, pady=1, sticky="ew")
        sample_id = ctk.CTkEntry(sample_window, placeholder_text = "e.g. Sample_24_03_2025")
        sample_id.grid(row=3, column=0, columnspan=4, padx=10, pady=5)

        #Sample height input field
        ctk.CTkLabel(sample_window, text="Enter starting sample height (mm):").grid(row = 4, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        initial_height = ctk.CTkEntry(sample_window, placeholder_text = "e.g. 12.36")
        initial_height.grid(row = 5, column = 1, columnspan = 2, padx=1, pady=1, sticky="ew")

        #Sample layer height input field
        ctk.CTkLabel(sample_window, text="Enter sample layer height (mm):").grid(row = 6, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        ctk.CTkLabel(sample_window, text="(i.e. Amount of material removed each layer):").grid(row = 7, column = 0, columnspan = 4, pady=1, sticky = "ew")
        ctk.CTkLabel(sample_window, text="(For scanning enter 0.)", font=("Arial",10,"italic")).grid(row = 8, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        layer_height = ctk.CTkEntry(sample_window, width = 50)
        layer_height.grid(row = 9, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #Width for bounding box input field
        ctk.CTkLabel(sample_window, text="Enter bounding box size:").grid(row = 10, column = 0, columnspan = 4, padx=5, pady=1, sticky="ew")
        ctk.CTkLabel(sample_window, text="Width (mm):").grid(row=11, column=0, padx=1, pady=1, sticky = "e")
        sample_width = ctk.CTkEntry(sample_window, width = 50, placeholder_text = "e.g. 10")
        sample_width.grid(row = 11, column = 1, padx=5, pady=5, sticky = "w")

        #Length for bounding box input field
        ctk.CTkLabel(sample_window, text="Length (mm):").grid(row=11, column=2, padx=5, pady=5, sticky = "e")
        sample_length = ctk.CTkEntry(sample_window, width = 50, placeholder_text = "e.g. 10")
        sample_length.grid(row = 11, column = 3, padx=5, pady=10, sticky = "w")

        # OK button - closes the window and calls function send_sample_data() on OK
        ok_button = ctk.CTkButton(sample_window, text="OK", 
                                  command=lambda: [self.send_sample_data(mount_type.get(), sample_id.get(),
                                                      float(initial_height.get()), float(layer_height.get()), 
                                                      float(sample_width.get()), float(sample_length.get())), 
                                                      sample_window.destroy()], width = 80)
        ok_button.grid(row = 12, column = 0, padx=5, pady=5)

        # Cancel button - closes window
        ctk.CTkButton(sample_window, text="Cancel", command=sample_window.destroy, width = 80).grid(row = 12, column = 3, columnspan = 2, padx=5, pady=5)

    def open_sampling_dialog(self):
        '''
        Pop-up window to enter in random sampling data and start process for samping.
        Ok button only enabled when input is valid.
        '''

        # Window setup
        image_sampling_window = ctk.CTkToplevel(self)
        image_sampling_window.title("Enter Sampling Parameters")
        image_sampling_window.geometry("370x135")  # Set initial size
        image_sampling_window.minsize(370, 135)   # Limit the minimum size
        image_sampling_window.maxsize(370, 135)   # Limit the maximum size

        image_sampling_window.grab_set()

        #Label for instructions
        label = ctk.CTkLabel(image_sampling_window, text="Enter in the number of images taken for random sampling:")
        label.grid(row=0, column=0, columnspan=4, padx=5, pady=10, sticky="ew")

        # Total images input field
        ctk.CTkLabel(image_sampling_window, text="Total Number of Images:").grid(row=1, column=0, columnspan = 2, padx=5, pady=5, sticky="e")
        total_images = ctk.CTkEntry(image_sampling_window, placeholder_text="e.g. 6")
        total_images.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # OK button (closes the window and processes input)
        ok_button = ctk.CTkButton(image_sampling_window, text="OK", 
                                command=lambda: [self.send_sampling_data(int(total_images.get())),
                                                self.display_random_sampling_layout(int(total_images.get()), self.main_right_frame),
                                                image_sampling_window.destroy()], width=80, state="disabled")  # Initially disabled
        ok_button.grid(row=2, column=0, padx=5, pady=10, sticky="ew")

        # Cancel button (closes the window)
        cancel_button = ctk.CTkButton(image_sampling_window, text="Cancel", command=image_sampling_window.destroy, width=80)
        cancel_button.grid(row=2, column=3, columnspan=2, padx=5, pady=10, sticky="ew")

        # Ensure the buttons are always at the bottom of the window
        image_sampling_window.grid_rowconfigure(3, weight=1)  # Add this line to allow the window to expand as needed
        image_sampling_window.grid_rowconfigure(2, weight=0)  # Ensure row 2 (buttons) stays at the bottom

        # Validates the input before enabling ok button
        def validate_input(*args):
            try:
                value = int(total_images.get())
                # Check if value is between 1 and 20
                if 1 <= value <= 20 and self.module_status == "Idle" :
                    ok_button.configure(state="normal")  # Enable OK button
                else:
                    ok_button.configure(state="disabled")  # Disable OK button
            except ValueError:
                ok_button.configure(state="disabled")  # Disable OK button if input is not a number

        # Trace the input changes and call validate_input
        total_images.bind("<KeyRelease>", validate_input)


    def open_scanning_dialog(self, frame):
        '''
        Scanning pop-up window to enter in data and start scanning process.
        Ok button disabled until inputs are valid.
        
        Args:
            frame (tk.Frame): The frame where scanning loading page will be displayed.
        
        Returns:
            None
        '''

        # Window setup
        image_scanning_window = ctk.CTkToplevel(self)
        image_scanning_window.title("Enter Scanning Parameters")
        image_scanning_window.geometry("335x210")  # Set initial size
        image_scanning_window.minsize(335, 210)   # Limit the minimum size
        image_scanning_window.maxsize(335, 200)   # Limit the maximum size

        image_scanning_window.grab_set()

        # Label with instructions
        label = ctk.CTkLabel(image_scanning_window, text="Please enter the scanning bounding box:", font=("Arial", 12, "bold"))
        label.grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky="e")
        tip_label = label = ctk.CTkLabel(image_scanning_window, text="Default is 5 for step x, and 4 for step y", font=("Arial", 12, "italic"))
        tip_label.grid(row=1, column=0, columnspan=4, padx=5, pady=3, sticky="e")

        # Step x input field
        ctk.CTkLabel(image_scanning_window, text="Step x:").grid(row=2, column=0, padx=5, pady=10, sticky="e")
        step_x = ctk.CTkEntry(image_scanning_window, placeholder_text="5")
        step_x.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Step y input field
        ctk.CTkLabel(image_scanning_window, text="Step y:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        step_y = ctk.CTkEntry(image_scanning_window, placeholder_text="4")
        step_y.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # OK button (closes the window, changes frame, empties rpi image buffer, sends scanning_data to rpi)
        ok_button = ctk.CTkButton(image_scanning_window, text="OK", 
                                command=lambda: [
                                    self.send_scanning_data(int(step_x.get()), int(step_y.get())),
                                    self.display_loading_frame(frame),
                                    image_scanning_window.destroy()], 
                                width=80, state="disabled")  # Initially disabled
        ok_button.grid(row=4, column=0, padx=5, pady=10, sticky="ew")

        # Cancel button (closes the window)
        cancel_button = ctk.CTkButton(image_scanning_window, text="Cancel", command=image_scanning_window.destroy, width=80)
        cancel_button.grid(row=4, column=3, columnspan=2, padx=5, pady=10, sticky="ew")

        # Ensure the buttons are always at the bottom of the window
        image_scanning_window.grid_rowconfigure(4, weight=1)  # Add this line to allow the window to expand as needed
        image_scanning_window.grid_rowconfigure(3, weight=0)  # Ensure row 3 (buttons) stays at the bottom

        # Simple validation function for Step x and Step y
        def validate_input(*args):
            try:
                value_x = float(step_x.get())
                value_y = float(step_y.get())
                # Check if both values are positive numbers
                if value_x > 0 and value_y > 0 and self.module_status == "Idle" :
                    ok_button.configure(state="normal")  # Enable OK button
                else:
                    ok_button.configure(state="disabled")  # Disable OK button
            except ValueError:
                ok_button.configure(state="disabled")  # Disable OK button if input is not a valid number

        # Trace the input changes and call validate_input
        step_x.bind("<KeyRelease>", validate_input)
        step_y.bind("<KeyRelease>", validate_input)

    def open_homing_dialog(self):
        '''
        Homing dialog box to request which type of homing routine to run, XY or All.
        '''

        # Window setup
        homing_window = ctk.CTkToplevel(self)
        homing_window.title("Select Homing Type")
        homing_window.geometry("300x250")  # Set initial size
        homing_window.minsize(300, 250)   # Limit the minimum size
        homing_window.maxsize(300, 250)   # Limit the maximum size

        homing_window.grab_set()  # Makes the window modal

        # Prompt label
        label = ctk.CTkLabel(homing_window, text="Select homing type:")
        label.pack(pady=10)

        # "Homing All" button
        homing_all_button = ctk.CTkButton(homing_window, text="Homing All", 
                                        command=lambda: [self.send_simple_command("exe_homing_all", True),homing_window.destroy()], 
                                        width=150)
        homing_all_button.pack(pady=5)

        # "Homing XY" button
        homing_xy_button = ctk.CTkButton(homing_window, text="Homing XY", 
                                        command=lambda: [self.send_simple_command("exe_homing_xy", True),homing_window.destroy()], 
                                        width=150)
        homing_xy_button.pack(pady=5)

        # Add vertical space before the cancel button
        ctk.CTkLabel(homing_window, text="").pack(pady=10)

        # Cancel button
        cancel_button = ctk.CTkButton(homing_window, text="Cancel", command=homing_window.destroy, width=150)
        cancel_button.pack(pady=5)

    #------------------------------- Motion, Image, Calibration, Details Tabs ------------------------------------------#

    # ------------------ Motion Tab ------------------ #
    def display_motion_tab(self):
        """
        Initializes and displays the Motion tab, including:
        - Coordinate entry controls (X, Y, Z)
        - Buttons for sending coordinates, refreshing motor positions, and controlling motors
        - Display labels for dynamic motor status and position
        """

        # Left frame: This frame will contain the coordinate entry controls        
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)

        # (Incomplete) Right frame: Intended for graph configuration (not connected to Raspberry Pi yet)
        #right_frame = ctk.CTkFrame(self.content_frame)
        #right_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)
        
        # Middle frame: Main frame to hold the status and display information
        main_frame = ctk.CTkFrame(self.content_frame)
        main_frame.pack(side=ctk.LEFT, expand=True, fill='both', padx=10, pady=10)

        # Coordinate frame inside the left_frame, to hold position controls and buttons
        coord_frame = ctk.CTkFrame(left_frame)
        coord_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=10)

        # Create a separate button frame inside left_frame (placed at the bottom)
        button_frame = ctk.CTkFrame(left_frame)
        button_frame.pack(side=ctk.BOTTOM, fill="x", padx=10, pady=10)

        # Left Frame: Entry Boxes and Buttons
        coord_label = ctk.CTkLabel(coord_frame, text="Enter in desired coordinates:", font=("Arial", 14, "bold"))
        coord_label.grid(row=0, column=0, columnspan = 3, padx=5, pady=5, sticky="ew")

        # Position Controls: Creates input fields and buttons for X, Y, Z positions
        self.create_position_control(coord_frame, "X", self.x_pos, row=1)
        self.create_position_control(coord_frame, "Y", self.y_pos, row=2)
        self.create_position_control(coord_frame, "Z", self.z_pos, row=3)

        # Send coordinates button: Sends the coordinates to the system
        send_coord_btn = ctk.CTkButton(coord_frame, text="Send Coordinates", font=("Arial", 14), 
                                       command=lambda: self.send_goto_command(float(self.x_entry.get()),float(self.y_entry.get()),float(self.z_entry.get())))
        send_coord_btn.grid(row=4, column=0, columnspan = 3, padx=5, pady=5, sticky="ew")

        # Refresh coordinates button: Updates the entry boxes with the current motor positions
        refresh_coord_btn = ctk.CTkButton(coord_frame, text="Refresh Coordinates", font=("Arial", 14), command=self.refresh_motor_coord)
        refresh_coord_btn.grid(row=5,column=0,columnspan = 3, padx=5, pady=5, sticky="ew")

        # Additional Controls (Buttons)
        # Homing Button: Starts homing procedure for the motors
        home_btn = ctk.CTkButton(button_frame, text="Homing", width = 200, height = 50, font=("Arial", 20), fg_color="blue", text_color="white",
                                 command = lambda: self.open_homing_dialog())        
        home_btn.pack(pady=5, fill='x')

        # Disable stepper motors button: Sends command to disable the motors
        disable_motors_btn = ctk.CTkButton(button_frame, text="Disable Stepper Motors", 
                                           command=lambda: self.send_simple_command("exe_disable_motors", True))
        disable_motors_btn.pack(pady=5, fill="x")

        # Graph Display
        #Incomplete. GUI functionality done, but not configured with Raspberry Pi info
        #self.create_graphs(right_frame)

        # Stop button: Stops ongoing GoTo movement, and any movement
        stop_btn = ctk.CTkButton(button_frame, text="STOP", fg_color="red", command=lambda: self.send_simple_command("exe_stop", False))
        stop_btn.pack(pady=5, fill="x")

        # Main Frame: Display dynamic data from Raspberry Pi
        motors_enabled_label = ctk.CTkLabel(main_frame, text="Motors Enabled")
        motors_enabled_label.pack(pady=5, fill='x')
        self.rpi_motors_enabled_var = ctk.StringVar(value="--")  # Dynamic variable
        self.rpi_motors_enabled_label = ctk.CTkLabel(main_frame, textvariable=self.rpi_motors_enabled_var)
        self.rpi_motors_enabled_label.pack(pady=5, fill='x')

        # X position label and display
        x_pos_label = ctk.CTkLabel(main_frame, text="X Position (mm)")
        x_pos_label.pack(pady=5, fill="x")
        self.rpi_x_pos_var = ctk.StringVar(value="--")
        self.rpi_x_pos_label = ctk.CTkLabel(main_frame, textvariable=self.rpi_x_pos_var)
        self.rpi_x_pos_label.pack(pady=5, fill='x')

        # Y position label and display
        y_pos_label = ctk.CTkLabel(main_frame, text="Y Position (mm)")
        y_pos_label.pack(pady=5, fill="x")
        self.rpi_y_pos_var = ctk.StringVar(value="--")
        self.rpi_y_pos_label = ctk.CTkLabel(main_frame, textvariable=self.rpi_y_pos_var)
        self.rpi_y_pos_label.pack(pady=5, fill='x')

        # Z position label and display
        z_pos_label = ctk.CTkLabel(main_frame, text="Z Position (mm)")
        z_pos_label.pack(pady=5, fill="x")
        self.rpi_z_pos_var = ctk.StringVar(value="--")
        self.rpi_z_pos_label = ctk.CTkLabel(main_frame, textvariable=self.rpi_z_pos_var)
        self.rpi_z_pos_label.pack(pady=5, fill='x')

        # Last Refreshed label: Shows when the positions were last updated        
        self.last_refreshed_var = ctk.StringVar(value="Last Updated: --")
        self.last_refreshed_label = ctk.CTkLabel(main_frame, textvariable=self.last_refreshed_var, font=("Arial", 12))
        self.last_refreshed_label.pack(pady=5)

    def refresh_motor_coord(self):
        """
        Fetch live data being updated from Raspberry Pi and update entries dynamically.
        Used for labels in motion tab's main frame.
        """

        # Refreshes X, Y, Z motor positions in the entry widgets
        self.x_entry.delete(0, "end")
        self.x_entry.insert(0, str(self.x_pos))

        self.y_entry.delete(0, "end")
        self.y_entry.insert(0, str(self.y_pos))

        self.z_entry.delete(0, "end")
        self.z_entry.insert(0, str(self.z_pos))

    def create_position_control(self, parent, label, value, row):
        """
        Creates a position control widget with a label, entry field, and step buttons for a specific axis.
        
        Args:
            parent (tk.Widget): The parent widget (e.g., frame) to contain this control.
            label (str): The label for the axis (e.g., "X", "Y", "Z").
            value (int or float): The initial value of the position.
            row (int): The row number for positioning the widget in the grid layout.
        
        Returns:
            None
        """

        # Label for the position (e.g., "X Position:")
        ctk.CTkLabel(parent, text=f"{label} Position:",font=("Arial", 18)).grid(row=row, column=0, padx=5, pady=2, sticky='w')

        # Entry widget for inputting position value
        entry = ctk.CTkEntry(parent, width=30)
        entry.insert(0, str(value))
        entry.grid(row=row, column=2, padx=3, pady=2)

        # Step buttons for adjusting the position (up/down buttons)
        self.create_step_buttons(parent, entry, row=row)

         # Store the entry in self for later access
        if label == "X":
            self.x_entry = entry
        elif label == "Y":
            self.y_entry = entry
        elif label == "Z":
            self.z_entry = entry

    def create_step_buttons(self, parent, entry_widget, step=1, row=0):
        """
        Creates step adjustment buttons for modifying the position value by a fixed step.
        
        Args:
            parent (tk.Widget): The parent widget (e.g., frame) to contain the buttons.
            entry_widget (tk.Entry): The entry widget to update when the button is clicked.
            step (int or float): The step value for incrementing or decrementing the position.
            row (int): The row number for positioning the buttons in the grid layout.
        
        Returns:
            None
        """

        # Frame to hold the step adjustment buttons
        btn_frame = ctk.CTkFrame(parent)
        btn_frame.grid(row=row, column=1, padx=5, pady=2)

        # Up button: Increases position value by the step
        ctk.CTkButton(btn_frame, text="▲", width=30, command=lambda: self.adjust_value(entry_widget, step)).grid(row=0, column=0, padx=2)

        # Down button: Decreases position value by the step
        ctk.CTkButton(btn_frame, text="▼", width=30, command=lambda: self.adjust_value(entry_widget, -step)).grid(row=0, column=1, padx=2)
    
    def adjust_value(self, entry, step):
        """
        Adjusts the value in the provided entry widget by the specified step (increment or decrement).
        
        Args:
            entry (tk.Entry): The entry widget containing the current value.
            step (int or float): The step value for adjusting the position (positive for increase, negative for decrease).
        
        Returns:
            None
        """

        try:
            # Get the current value from the entry, adjust it, and update the entry field
            current_value = int(entry.get())
            entry.delete(0, ctk.END)
            entry.insert(0, str(current_value + step))
        except ValueError:
            # If the entry is not a valid number, reset to 0
            entry.delete(0, ctk.END)
            entry.insert(0, "0")

    #Incomplete, not in use. Raspberry Pi coord not connected to grids.
    def create_graphs(self, parent):
        """
        Creates the graphical displays for showing the X-Y and Z-Axis motion control of the camera.
        
        Args:
            parent (tk.Widget): The parent widget (e.g., frame) to contain the graphs.
        
        Returns:
            None
        """
    
        # Frame to hold both the X-Y and Z-Axis graphs
        graph_frame = ctk.CTkFrame(parent)
        graph_frame.pack(expand=True, fill='both', padx=5, pady=5)

        # X-Y Graph (Square Graph) - Positioned on the left
        xy_graph = ctk.CTkFrame(graph_frame, width=300, height=300, fg_color="blue")
        xy_graph.pack(side=ctk.LEFT, padx=5, pady=5)

        # Z-Axis Graph (Vertical Rectangle) - Positioned on the right
        z_graph = ctk.CTkFrame(graph_frame, width=80, height=300, fg_color="blue")  # Narrower but taller
        z_graph.pack(side=ctk.RIGHT, padx=5, pady=5)

        # Red Position Indicator (Mock) for X-Y Graph
        ctk.CTkLabel(xy_graph, text="       ", fg_color="red").place(
            relx=self.x_pos * 0.001, rely=self.y_pos * 0.001, anchor='center')

        # Red Position Indicator (Mock) for Z-Axis Graph (Now aligned vertically)
        ctk.CTkLabel(z_graph, text="           ", fg_color="red").place(
            relx=0.5, rely=1 - (self.z_pos * 0.001), anchor='center')  # Flipped to align vertically

    
    # --------------------------- Image Tab ----------------------------- #

    def display_image_tab(self):
        """
        Displays the Image tab layout with parameter input, current values, and image preview.

        This method sets up the layout for the image control tab, including the display of camera 
        parameters (exposure, analog gain, contrast, and color temperature) and the functionality 
        to send data, refresh parameters, and display images.
        """

        # Clear previous content in the content frame
        self.clear_frame(self.content_frame)

        # Setup frames for organizing the UI components
        param_frame = ctk.CTkFrame(self.content_frame, width=300, height=400)
        param_frame.grid(row=0, column=0, sticky="ns", padx=10, pady=10)

        right_frame = ctk.CTkFrame(self.content_frame)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        # Make the right column expand with the window resizing
        self.content_frame.grid_columnconfigure(1, weight=1, minsize=200)  # Right column (column 1)
        self.content_frame.grid_rowconfigure(0, weight=1, minsize=400)  # Row 0 (the row containing the frames)

        # Left panel: Camera Parameters
        # Title label for the camera parameters section
        title_label = ctk.CTkLabel(param_frame, text="Camera Parameters", font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10), sticky="w")

        # New Labels for the column titles (bolded)
        enter_param_label = ctk.CTkLabel(param_frame, text="Enter in desired parameters:", font=("Arial", 12, "bold"))
        enter_param_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")

        current_param_label = ctk.CTkLabel(param_frame, text="Current Parameters:", font=("Arial", 12, "bold"))
        current_param_label.grid(row=2, column=2, padx=5, pady=5, sticky="ew")

        # Define a list of parameter labels for the camera settings
        param_labels = ["Exposure Time (microsec):", "Analog Gain (1=no gain):",
                        "Contrast (0-32, 1=no value):", "Colour Temperature (K):"]

        # Last updated timestamp
        self.last_refreshed_var = ctk.StringVar(value="Last Updated: --")
        self.last_refreshed_label = ctk.CTkLabel(param_frame, textvariable=self.last_refreshed_var, font=("Arial", 12))
        self.last_refreshed_label.grid(row=len(param_labels)+3, column=2, columnspan=1, sticky="w", pady=10, padx=5)

        # Initialize lists to store entry fields and current parameter values
        self.entries = []
        self.current_vars = []

        # Create entry fields for each parameter label and their current value labels
        for i, label_text in enumerate(param_labels):
            # Label and Entry (Column 0 for the labels)
            label = ctk.CTkLabel(param_frame, text=label_text)
            label.grid(row=i+3, column=0, sticky="w", padx=5, pady=5)

            #Input fields
            entry = ctk.CTkEntry(param_frame, width=100)
            entry.grid(row=i+3, column=1, sticky="w", padx=(20, 5), pady=5)  # Aligned to the left
            self.entries.append(entry)

            # Current Parameter Value
            var = ctk.StringVar(value="-Value Not Updated-")
            current_label = ctk.CTkLabel(param_frame, textvariable=var, font=("Arial", 12))
            current_label.grid(row=i+3, column=2, sticky="ew", padx=5, pady=5)
            self.current_vars.append(var)

        # Assign individual vars for future updates
        self.exposure_time_entry = self.entries[0]
        self.analog_gain_entry = self.entries[1]
        self.contrast_entry = self.entries[2]
        self.colour_temp_entry = self.entries[3]

        self.rpi_exposure_var = self.current_vars[0]
        self.rpi_analog_gain_var = self.current_vars[1]
        self.rpi_contrast_var = self.current_vars[2]
        self.rpi_colour_temp_var = self.current_vars[3]

        # Send data button
        send_data_btn = ctk.CTkButton(param_frame, text="Send Data", font=("Arial", 16),
                                    command=lambda: self.send_camera_data(
                                        float(self.exposure_time_entry.get()),
                                        float(self.analog_gain_entry.get()),
                                        float(self.contrast_entry.get()),
                                        float(self.colour_temp_entry.get())), width=100)
        send_data_btn.grid(row=len(param_labels)+4, column=0, padx=(5, 10), pady=10, sticky="ew")

        # Refresh Data Button 
        refresh_data_btn = ctk.CTkButton(param_frame, text="Refresh Data", font=("Arial", 16), width=100,
                                        command=self.refresh_camera_entries)
        refresh_data_btn.grid(row=len(param_labels)+4, column=1, padx=(10, 5), pady=10, sticky="ew")

        # Right panel: Displaying and taking images
        # Create a frame for buttons at the top of the right_frame
        button_frame = ctk.CTkFrame(right_frame)
        button_frame.pack(side="top", pady=10, fill='x')

        # Take image button
        take_img_btn = ctk.CTkButton(button_frame, text="Take Image", font=("Arial", 16), fg_color="green",
                                    command=lambda: [self.empty_folder_rpi(),
                                                    self.send_simple_command("exe_update_image", True),
                                                    self.empty_folder_pc(self.buffer_testing_folder)])
        take_img_btn.pack(side="left", padx=10, fill='x', expand=True)

        # Display button
        display_image_btn = ctk.CTkButton(button_frame, text="Display Image", font=("Arial", 16),
                                        command=lambda: [self.transfer_folder_rpi(self.buffer_testing_folder, False),
                                                        self.show_image(self.buffer_testing_folder, image_label)])
        display_image_btn.pack(side="left", padx=10, fill='x', expand=True)

        # Empty Raspberry Pi Image Buffer folder
        empty_buffer_rpi_btn = ctk.CTkButton(button_frame, text="Empty RPI Images", font=("Arial", 16), fg_color="grey",
                                            command=lambda: [self.empty_folder_rpi()])
        empty_buffer_rpi_btn.pack(side="left", padx=10, fill='x', expand=True)

        # Image label
        image_label = ctk.CTkLabel(right_frame, text="Image will appear here", fg_color="gray", width=400, height=400)
        image_label.pack(expand=True, fill='both', pady=20)

    def refresh_camera_entries(self):
        """
        Fetch data being updated from Raspberry Pi and update entries dynamically.
        """

        self.exposure_time_entry.delete(0, "end")
        self.exposure_time_entry.insert(0, self.exposure_time)

        self.analog_gain_entry.delete(0, "end")
        self.analog_gain_entry.insert(0, self.analog_gain)

        self.contrast_entry.delete(0, "end")
        self.contrast_entry.insert(0, self.contrast)

        self.colour_temp_entry.delete(0, "end")
        self.colour_temp_entry.insert(0, self.colour_temp)

    def show_image(self, image_folder, image_label):
        """
        Updates the image displayed in the right frame from a sent path in the folder.

        Args:
            image_folder (str): The path to the folder containing the image(s).
            image_label (tk.Widget): The label widget where the image will be displayed.

        Raises:
            Exception: If no valid images are found or an error occurs while displaying the image.
        
        Returns:
            None
        """
        
        try:
            # Get the .jpg files in the folder
            image_files = [f for f in os.listdir(image_folder) if f.lower().endswith('.jpg')]
            
            if not image_files:
                # If no .jpg files are found, show an error message or disable the button
                image_label.configure(image='', text="No .jpg files found", font=('Arial', 14, 'bold'), fg_color="red")
                image_label.image = None  # Clear the image reference
                print("Error: No .jpg files found in the specified folder.")
                
                return
            
            image_path = os.path.join(image_folder, image_files[0])  # Take the first .jpg image

            # Normalize the image path (in case of backslashes or other inconsistencies)
            image_path = os.path.normpath(image_path)

            # Open the image using PIL
            img_pil = Image.open(image_path)

            # Resize the image to fit within a specific width and height, maintaining aspect ratio
            label_width = image_label.winfo_width()  # Dynamically get the current label width
            label_height = image_label.winfo_height()  # Dynamically get the current label height

            aspect_ratio = img_pil.width / img_pil.height
            if aspect_ratio > 1:  # Wide image
                new_width = label_width
                new_height = int(label_width / aspect_ratio)
            else:  # Tall or square image
                new_height = label_height
                new_width = int(label_height * aspect_ratio)

            resized_img = img_pil.resize((new_width, new_height), Image.LANCZOS)

            # Convert the image to a format that can be used with Tkinter
            img_tk = ImageTk.PhotoImage(resized_img)

            # Update the label to show the image
            image_label.configure(image=img_tk)
            image_label.image = img_tk  # Store a reference to the image to avoid garbage collection

            # Make the image label clickable to expand the image
            image_label.bind("<Button-1>", lambda e: self.expand_image(image_path))  # Bind click event to expand image

            # Hide the "Image will appear here" text
            image_label.configure(text="")  # Clear the text

            print("Image updated successfully :)")
            
        except Exception as e:
            print(f"Error displaying image: {e}")
            image_label.configure(text="Failed to display image", fg_color="red")


    # -------------------------- Details Tab ------------------------ #

    def display_details_tab(self):
        """
        Displays the 'Details' tab with various sections like alarm status, instructions, and folder paths.
        """

        # Clear previous content in the content frame
        self.clear_frame(self.content_frame)

        # Main container frame (to hold both sections)
        main_frame = ctk.CTkFrame(self.content_frame)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Frame to display alarm status and refresh button
        alarm_frame = ctk.CTkFrame(main_frame)
        alarm_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=5)

        #Refresh button to reset alarm status
        refresh_button = ctk.CTkButton(alarm_frame, text="Refresh Alarm Status", command=lambda: [self.send_simple_command("exe_reset_alarm_status", False)])
        refresh_button.pack(side="right", padx=5, pady=5)

        #Instructions frame
        instructions_frame = ctk.CTkFrame(main_frame)
        instructions_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=5)

        #Intructions label
        instructions_label = ctk.CTkLabel(instructions_frame, text="Instructions", font=("Arial", 18, "bold"), anchor="w")
        instructions_label.pack(padx=10, pady=5, fill="x")

        # Detailed instructions text
        instructions_text = (
            "1. Navigate through functionality using the tabs at the bottom of the GUI.\n\n"
            "2. Ensure the Raspberry Pi is connected by checking ""Module Status"" at the top left it should say ""Idle""\n\n"
            "3. First create a new sample in the Main Tab \n\n"
            "4. Run ""Random Sampling"" or ""Scanning"". Use the ""Image Tab"" and ""Motion Tab"" for manual adjustements. \n\n"
            "TIP: Whenever \"Stop\" is selected, the module will need to be homed again."
        )

        instructions_details = ctk.CTkLabel(instructions_frame, text=instructions_text, font=("Arial", 14), anchor="w", justify="left", wraplength=500)
        instructions_details.pack(padx=10, pady=5, fill="x")

        # Frame for displaying folder paths
        folder_frame = ctk.CTkFrame(main_frame)
        folder_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=5)

        folder_label = ctk.CTkLabel(folder_frame, text="Image Directories", font=("Arial", 16, "bold"), anchor="w")
        folder_label.pack(padx=10, pady=5, fill="x")

        # List of folder names and corresponding paths
        folders = [
            ("GUI Images Folder", self.img_gui),
            ("Buffer Scanning Folder", self.buffer_stitching_folder),
            ("Buffer Sampling Folder", self.buffer_sampling_folder),
            ("Camera Testing Folder", self.buffer_testing_folder),
            ("Completed Scanning Folder", self.complete_stitching_folder),
            ("Completed Sampling Folder", self.complete_sampling_folder)
        ]

        for label, folder in folders:
            entry_frame = ctk.CTkFrame(folder_frame)
            entry_frame.pack(fill="x", padx=10, pady=2)

            # Bold label for folder name
            label_widget = ctk.CTkLabel(entry_frame, text=f"{label}: ", font=("Arial", 14, "bold"), anchor="w")
            label_widget.pack(side="left")

            # Folder path
            folder_widget = ctk.CTkLabel(entry_frame, text=folder, font=("Arial", 14), anchor="w", justify="left", wraplength=500)
            folder_widget.pack(side="left", fill="x", expand=True)

    # --------------------- Calibration Tab ------------------------- #

    #Not currently in use. Tied to calibration_btn in Main Frame.
    def display_calibration_layout(self, frame) :
        """
        Displays the calibration frame with a layout of buttons and image holder.

        Args:
            frame (ctk.CTkFrame): The frame in which the layout is to be displayed.
        
        Returns:
            None
        """
        
        self.clear_frame(frame)
        
        # Create the scanning frame to hold the images
        calibration_frame = ctk.CTkFrame(frame)
        calibration_frame.pack(side=ctk.TOP, expand=True, fill='both', padx=10, pady=10)

        # Create a frame for the buttons to always be at the bottom
        button_frame = ctk.CTkFrame(frame)
        button_frame.pack(side=ctk.BOTTOM, fill='x', pady=10)

        # Stop button - sends rpi command and clears image buffer in rpi
        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red", 
                                    command=lambda:[self.send_simple_command("exe_stop", False),
                                                    self.empty_folder_rpi()])
        stop_button.pack(side=ctk.LEFT, expand=True, padx=5, pady=5)

        #Finish button returns to main frame
        finish_button = ctk.CTkButton(button_frame, text="Finish", command=self.display_main_tab)
        finish_button.pack(side=ctk.LEFT, expand=True, padx=5, pady=5)

    # -------------------------------------- Display Scanning Frames ----------------------------------------- #

    def display_loading_frame(self, frame):
        """
        Displays a loading frame with a STOP button to stop ongoing processes.

        Args:
            frame (ctk.CTkFrame): The frame in which the loading layout is to be displayed.
        
        Returns:
            None
        """

        self.clear_frame(frame)
 
        # Save scanning layout parameters
        self.scanning_target_frame = frame
 
        # Main loading layout
        loading_frame = ctk.CTkFrame(frame)
        loading_frame.pack(expand=True, fill='both', padx=20, pady=20)
 
        self.loading_label = ctk.CTkLabel(loading_frame, text=f"{self.module_status}",font=("Arial", 20))
        self.loading_label.pack(pady=20)

        #Button frame
        button_frame = ctk.CTkFrame(loading_frame)
        button_frame.pack(side='bottom', fill='x', pady=15)

        # Stop button (centered at bottom)
        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red", 
                                    command=lambda:[self.display_main_tab(), 
                                                    self.send_simple_command("exe_stop", False),
                                                    self.empty_folder_rpi()])

        stop_button.pack(side='bottom', pady=5)
    
    def get_image_layout_parameters(self,images_x, images_y):
        """
        Dynamically calculates image size and spacing based on grid size.

        Args:
            images_x (int): Number of images in the X direction.
            images_y (int): Number of images in the Y direction.

        Returns:
            tuple (int, int): A tuple containing the calculated image size (int) and spacing (int).
        """
        
        grid_size = max(images_x, images_y)
        grid_size = max(grid_size, 1) # Clamp grid_size to a minimum of 1 to avoid division by zero

        # Dynamically interpolate img_size and spacing
        # Formula makes img_size shrink as grid grows
        img_size = int(300 / (0.35 * grid_size + 1))   # More generous base size + slower shrink
        spacing  = int(8 / (0.4 * grid_size + 1))      # Tighter spacing + quicker shrink

        return img_size, spacing # Return type: tuple (int, int)
 
    def display_scanning_layout(self, images_x, images_y, frame):
        """
        Displays the scanning layout with all the images that were scanned
        with a large image grid that updates as images are captured.

        Args:
            images_x (int): Number of images in the X direction.
            images_y (int): Number of images in the Y direction.
            frame (ctk.CTkFrame): The frame in which the scanning layout is to be displayed.
        
        Returns:
            None
        """
        self.clear_frame(frame)

        self.expected_image_count = images_x * images_y
        self.current_image_index = 0
        self.image_folder_path = self.buffer_stitching_folder  # Save path for reuse

        #Button frame
        button_frame = ctk.CTkFrame(frame)
        button_frame.pack(side=ctk.TOP, fill='x', pady=10)

        #Display sititched image
        stitched_img_path = f"{self.buffer_stitching_folder}\\stitched_{self.curr_sample_id}.jpg"
        self.complete_image_btn = ctk.CTkButton(button_frame, text="Image Stitching...", fg_color="green", width=150, height=30, 
                                                state="disabled", 
                                                command=lambda:[self.expand_image(stitched_img_path)])
        self.complete_image_btn.pack(side=ctk.LEFT, expand=True, padx=5, pady=1)

        #Finish button - creates new folder with time stamp, and transfers images from buffer to complete
        new_folder_path = f"{self.complete_stitching_folder}/{self.curr_sample_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        finish_button = ctk.CTkButton(button_frame, text="Finish", 
                                      command=lambda:[self.display_main_tab(), self.create_transfer_folder_pc(self.buffer_stitching_folder,new_folder_path)])
        finish_button.pack(side=ctk.RIGHT, expand=True, padx=1, pady=1)

        #Stop button
        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red", 
                                    command=lambda:[self.display_main_tab(), 
                                                    self.send_simple_command("exe_stop",False)])
        stop_button.pack(side=ctk.RIGHT, expand=True, padx=5, pady=1)

        #Layout
        scanning_frame = ctk.CTkFrame(frame)
        scanning_frame.pack(side=ctk.BOTTOM, expand=True, fill='both')

        grid_container = ctk.CTkFrame(scanning_frame)
        grid_container.grid(row=0, column=0, padx=40, pady=40)

        scanning_frame.grid_columnconfigure(0, weight=1)
        scanning_frame.grid_rowconfigure(0, weight=1)

        for i in range(images_y):
            grid_container.grid_rowconfigure(i, weight=1)
        for j in range(images_x):
            grid_container.grid_columnconfigure(j, weight=1)

        #Image Grid
        self.scan_image_grid = []
        self.image_labels = []  # Store label references for updating
        img_size, _ = self.get_image_layout_parameters(images_x, images_y)

        # Initialize blank placeholders
        for i in range(self.expected_image_count):
            col = i // images_y
            row = (images_y - 1) - (i % images_y)

            placeholder_label = ctk.CTkLabel(grid_container, text="")
            placeholder_label.grid(row=row, column=col, padx=0, pady=0, sticky='nsew')
            self.image_labels.append(placeholder_label)

        # Start watching for new images
        self.poll_for_new_images()

    
    def load_images_from_folder(self, folder_path):
        """
        Loads all supported image files from the specified folder.

        Args:
            folder_path (str): The path to the folder containing the images.

        Returns:
            list: A list of full paths (str) to valid image files in the folder.
        """
        supported_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
        images = []

        #Get all files in the folder
        for filename in sorted(os.listdir(folder_path)):
            if filename.lower().endswith(supported_extensions) and not filename.startswith("._"):
                full_path = os.path.join(folder_path, filename)
                try:
                    with Image.open(full_path) as img:
                        img.verify()
                    images.append(full_path)
                except Exception:
                    print(f"Skipping invalid image: {filename}")

        return images # Return type: list of str
    
    # ---------------------------------- Display Random Sampling Frames ---------------------------------------- #
    
    def display_random_sampling_layout(self, num_images, frame):
        """
        Displays an evenly distributed grid layout for random sampling images with live updates.

        Args:
            num_images (int): The number of images to display in the random sampling grid. from pop-up window.
            frame (ctk.CTkFrame): The parent frame where the random sampling layout will be displayed.
        
        Returns:
            None
        """
        
        # Clear previous content
        self.clear_frame(frame)

        #List for storing images
        self.image_labels = []
        self.random_sampling_frame = ctk.CTkFrame(frame)  # Store for use in polling
        self.random_sampling_frame.pack(expand=True, fill='both', padx=10, pady=10)

        self.target_num_images = num_images
        self.img_size = 200  # You can use dynamic scaling if needed

        # Initial population
        images = self.load_images_from_folder(self.buffer_sampling_folder)
        self.populate_image_grid(self.random_sampling_frame, images, num_images, self.img_size)

        # Start polling folder for new images
        self.random_sampling_image_update()
        
        #Frame for buttons
        button_frame = ctk.CTkFrame(self.random_sampling_frame)
        button_frame.grid(row = 2, column = 0, columnspan = self.total_columns, pady=5, padx=10)
 
        # STOP button 
        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red", 
                                    command=lambda: [self.display_main_tab(), 
                                                     self.send_simple_command("exe_stop", False),
                                                     self.empty_folder_rpi()])
        stop_button.pack(side='left', padx=5, fill = 'x', pady=5)
 
        # FINISH button - transfers images from buffer folder to complete folder, creates new folder with time stamp
        new_folder_path = f"{self.complete_sampling_folder}/{self.curr_sample_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"     

        finish_button = ctk.CTkButton(button_frame, text="Finish", 
                                      command=lambda:[self.display_main_tab(),self.create_transfer_folder_pc(self.buffer_sampling_folder,new_folder_path)])
        finish_button.pack(side='right',fill = 'x', padx=5, pady=5)

    def populate_image_grid(self, parent_frame, images, num_images, img_size):
        """
        Populate the image grid with images.

        Args:
            parent_frame (ctk.CTkFrame): The parent frame where images will be placed.
            images (list[str]): A list of image file paths to display.
            num_images (int): The total number of images to display.
            img_size (int): The size of each image in the grid.
        
        Returns:
            None
        """

        # Clear previous image labels
        for label in self.image_labels:
            label.destroy()

        self.image_labels = []  # Reset the list

        # Calculate row distribution
        first_row_count = (num_images + 1) // 2  # First row gets one extra if odd
        second_row_count = num_images // 2

        # Determine the maximum number of columns
        self.total_columns = max(first_row_count, second_row_count)

        # Configure grid to center images
        for col in range(self.total_columns):
            parent_frame.grid_columnconfigure(col, weight=1)  # Make columns expand evenly

        parent_frame.grid_rowconfigure(0, weight=1)  # Ensure images are centered
        parent_frame.grid_rowconfigure(1, weight=1)
        parent_frame.grid_rowconfigure(2, weight=0)  # Ensure buttons stay at bottom

        # Display first row (only if images exist)
        for col in range(first_row_count):
            if col >= len(images):  # Prevent index error
                break
            img = Image.open(images[col])
            img = img.resize((img_size, img_size), Image.LANCZOS)
            img_ctk = ctk.CTkImage(img, size=(img_size, img_size))

            img_label = ctk.CTkLabel(parent_frame, image=img_ctk, text="")
            img_label.grid(row=0, column=col, padx=10, pady=10, sticky='nsew')

            img_label.bind("<Button-1>", lambda e, img_path=images[col]: self.expand_image(img_path))
            self.image_labels.append(img_label)

        # Display second row (only if images exist)
        for col in range(second_row_count):
            image_index = first_row_count + col
            if image_index >= len(images):  # Prevent index error
                break
            img = Image.open(images[image_index])
            img = img.resize((img_size, img_size), Image.LANCZOS)
            img_ctk = ctk.CTkImage(img, size=(img_size, img_size))

            img_label = ctk.CTkLabel(parent_frame, image=img_ctk, text="")
            img_label.grid(row=1, column=col, padx=10, pady=10, sticky='nsew')

            img_label.bind("<Button-1>", lambda e, img_path=images[image_index]: self.expand_image(img_path))
            self.image_labels.append(img_label)

    def random_sampling_image_update(self):
        """
        Updates the random sampling layout by polling the image folder for new images.

        The function periodically checks the folder for new images and updates the
        displayed grid of images. If there are new images, it updates the grid layout 
        with the new images. It continues polling every second if the number of images 
        is below the expected target.

        """

        images = self.load_images_from_folder(self.buffer_sampling_folder)
        available = len(images)

        if available == 0:
            self.after(1000, self.random_sampling_image_update)
            return

        # Limit to desired number of images
        images_to_show = images[:self.target_num_images]

        # Only update if number of images changed
        if len(images_to_show) != len(self.image_labels):
            self.populate_image_grid(self.random_sampling_frame, images_to_show, self.target_num_images, self.img_size)

        # Stop polling if all expected images are loaded
        if len(images_to_show) < self.target_num_images:
            self.after(1000, self.random_sampling_image_update)  # Check again after 1 sec

    def poll_for_new_images(self):
        """
        Polls the specified image folder and updates the image grid with newly captured images.

        The function reads images from the folder and sorts them based on their numeric index.
        It updates the displayed images until the expected number of images are loaded. If there
        are new images that match the expected count, the complete image button is enabled.
        """

        images = self.load_images_from_folder(self.image_folder_path)

        # Match filenames that start with an integer index (e.g., "0_img.jpg", "15_picture.png")
        def extract_index(filename):
            match = re.match(r'^(\d+)', os.path.basename(filename))
            return int(match.group(1)) if match else float('inf')  # Put invalid files at the end

        # Sort based on extracted numeric index
        images = sorted(images, key=extract_index)

        # Only process up to the expected number of images
        for index, img_path in enumerate(images[:self.expected_image_count]):
            try:
                img = Image.open(img_path)
                img = img.resize((int(1.3342 * self.get_image_layout_parameters(1, 1)[0]),
                                self.get_image_layout_parameters(1, 1)[0]), Image.LANCZOS)
                img_ctk = ctk.CTkImage(img, size=(self.get_image_layout_parameters(1, 1)[0],
                                                self.get_image_layout_parameters(1, 1)[0]))

                label = self.image_labels[index]
                label.configure(image=img_ctk, text="")
                label.image = img_ctk  # Prevent garbage collection
                label.bind("<Button-1>", lambda e, path=img_path: self.expand_image(path))

            except Exception as e:
                print(f"Failed to load image {img_path}: {e}")

        # Enable button if all images are filled
        if len(images) >= self.expected_image_count:
            self.complete_image_btn.configure(state="normal")
        else:
            self.after(1000, self.poll_for_new_images)


    # --------------------------- Appearance Functions --------------------------- #

    def expand_image(self, img_path):
        """
        Opens a new window displaying the image and resizes it based on the window size.

        Args:
            img_path (str): The path to the image file to display.
        
        Returns:
            None
        """

        #Window setup
        expanded_window = ctk.CTkToplevel(self)
        expanded_window.title("Expanded Image")

        # Set initial window size to 600x600
        expanded_window.geometry("600x600")
        expanded_window.minsize(400, 400)
        expanded_window.maxsize(1000, 1000)

        expanded_window.grab_set()

        # Load the original image
        original_img = Image.open(img_path)

        # Resize the image to 600x600 initially (ignoring aspect ratio for now)
        initial_width = 600
        initial_height = 600
        resized_img = original_img.resize((initial_width, initial_height), Image.LANCZOS)

        # Create a Tkinter-compatible image for initial display
        self.img_ctk = ImageTk.PhotoImage(resized_img)

        # Create a frame to hold the image and button separately
        image_frame = ctk.CTkFrame(expanded_window)
        image_frame.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')

        # Display the image in the frame
        self.img_display = ctk.CTkLabel(image_frame, image=self.img_ctk, text="")

        self.img_display.pack(expand=True, padx=10, pady=10)

        # Back Button to close window (fixed at the bottom of the window)
        back_button = ctk.CTkButton(expanded_window, text="Back", command=expanded_window.destroy)
        back_button.grid(row=1, column=0, padx=5, pady=10, sticky='ew')  # Positioned at the bottom

        def resize_image_periodically():
            """
            Periodically resize the image based on window size.
            """

            # Get current window width and height
            window_width = expanded_window.winfo_width()
            window_height = expanded_window.winfo_height()

            # Maintain aspect ratio
            aspect_ratio = original_img.width / original_img.height

            # Calculate new dimensions, but scale the image down to fit the window
            new_width = window_width - 20  # Account for padding
            new_height = window_height - 20

            if new_width / aspect_ratio <= new_height:
                new_height = int(new_width / aspect_ratio)
            else:
                new_width = int(new_height * aspect_ratio)

            # Resize the image to the calculated size
            resized_img = original_img.resize((new_width, new_height), Image.LANCZOS)

            # Update the image displayed in the window
            self.img_ctk = ImageTk.PhotoImage(resized_img)
            self.img_display.configure(image=self.img_ctk)

            # Schedule the next resize check after 100ms
            expanded_window.after(50, resize_image_periodically)

        # Start the periodic resizing check
        resize_image_periodically()

        # Ensure the layout expands correctly
        expanded_window.grid_rowconfigure(0, weight=1)
        expanded_window.grid_rowconfigure(1, weight=0)  # Keep the back button at the bottom
        expanded_window.grid_columnconfigure(0, weight=1)

    #Update time
    def update_time(self):
        '''
        Updates the time displayed in the bottom frame.

        This method retrieves the current time and formats it as a string 
        in the format "%Y-%m-%d %H:%M:%S". It then updates the text of the 
        `date_time_label` to display the current time. The method is called 
        every second to continuously update the time.
        '''

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.date_time_label.configure(text=now)
        self.after(1000, self.update_time)

    #Clear frame
    def clear_frame(self, frame):
        """
        Destroys all widgets inside the given frame.

        Args:
            frame (ctk.CTkFrame): The frame whose widgets will be destroyed.
        """

        for widget in frame.winfo_children():
            widget.destroy()
    
    #====================================================================================#
    #---------------------------------- GUI Communication -------------------------------#
    #====================================================================================#

    # ------------------- Image transfer and folder handling ------------------------- #

    def create_transfer_folder_pc(self, src_folder, dest_folder):
        """
        Creates the destination folder and transfers files from the source folder to the destination folder.

        This method creates a new folder at the destination path if it doesn't exist and then moves all files 
        from the source folder to the destination folder. Subdirectories are ignored.

        Args:
            src_folder (str): The path to the source folder where files are located.
            dest_folder (str): The path to the destination folder where files will be moved.

        Returns:
            None
        """
        
        try:
            # Step 1: Create the destination folder if it doesn't exist
            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder)  # Create the new folder

            # Step 2: Move all files from the source folder to the destination folder
            for filename in os.listdir(src_folder):
                src_file = os.path.join(src_folder, filename)
                dest_file = os.path.join(dest_folder, filename)

                # Only move files (not subfolders)
                if os.path.isfile(src_file):
                    shutil.move(src_file, dest_file)  # Move file to new folder

            print(f"All files have been moved from {src_folder} to {dest_folder}.")

        except Exception as e:
            print(f"Error: {e}")
    
    def empty_folder_pc(self, dir_path):
        """
        Empties the specified folder by removing all files and subdirectories.

        This method checks if the provided directory exists and is valid. It then removes all files and subdirectories 
        within the folder.

        Args:
            dir_path (str): The path to the directory to be emptied.

        Returns:
            None
        """

        # Check if the directory exists
        if os.path.exists(dir_path) and os.path.isdir(dir_path):

            # Loop over the items in the folder and remove them
            for filename in os.listdir(dir_path):
                file_path = os.path.join(dir_path, filename)
                try:
                    if os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # Remove directory
                    else:
                        os.remove(file_path)  # Remove file
                except Exception as e:
                    print(f"Error removing {file_path}: {e}")
        else:
            print(f"The directory {dir_path} does not exist or is not a valid folder.")
        
    def extract_unique_positions(self, directory):
        """
        Extracts unique x and y positions from JSON objects in text files within the specified directory.

        This method searches for text files in the specified directory, parses them as JSON, 
        and extracts the x and y positions. It returns the count of unique x and y positions.

        Args:
            directory (str): The path to the directory containing the text files.

        Returns:
            tuple (int, int): A tuple containing the count of unique x and y positions.
        """
        
        unique_x_positions = set()  # Set to store unique x positions
        unique_y_positions = set()  # Set to store unique y positions

        # Iterate through all files in the specified directory
        for filename in os.listdir(directory):
            if filename.endswith(".txt"):  # Only process text files
                file_path = os.path.join(directory, filename)
                
                with open(file_path, 'r') as file:
                    try:
                        # Assuming the file contains one JSON object per line or a single JSON object
                        data = json.load(file)  # Load the JSON object from the file
                        
                        # Extract the x and y positions
                        x_pos = round(data.get("image_x_pos"))
                        y_pos = round(data.get("image_y_pos"))
                        
                        if x_pos is not None:
                            unique_x_positions.add(x_pos)  # Add to the set of unique x positions
                        if y_pos is not None:
                            unique_y_positions.add(y_pos)  # Add to the set of unique y positions
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON in file {filename}")
                    except Exception as e:
                        print(f"An error occurred while processing file {filename}: {e}")

        # Return the unique x and y positions
        return len(unique_x_positions), len(unique_y_positions)
    
    def set_rpi_transfer(self, transfer_obj):
        """
        Sets the RaspberryPiTransfer instance for use in the GUI.

        This method allows the transfer object to be set, enabling file transfer operations
        between the PC and Raspberry Pi.

        Args:
            transfer_obj: The instance of the RaspberryPiTransfer class.

        Returns:
            None
        """
        self.rpi_transfer = transfer_obj
    
    def transfer_folder_rpi(self, destination_path, new_filename):
        """
        Transfers a folder from the Raspberry Pi to the local machine (PC).

        This method connects to the Raspberry Pi with SFTP, transfers the image buffer folder, and then 
        closes the connection. The transfer is handled by the RaspberryPiTransfer instance.

        Args:
            destination_path (str): The local path to save the transferred files.
            new_filename (str): The name to be assigned to the transferred files.

        Returns:
            None
        """
        if not self.rpi_transfer:
            messagebox.showerror("Error", "Raspberry Pi connection is not established.")
            return

        remote_folder = "/home/microscope/image_buffer" #Folder path to where images are on RPI
        local_folder = destination_path
        
        try:
            # Create STFP, transfer images, then close STFP connection
            self.rpi_transfer.connect_sftp()
            self.rpi_transfer.transfer_folder(remote_folder, local_folder, new_filename)
            self.rpi_transfer.close_sftp_connection()
            print("Success", "Files successfully transferred!")
        except Exception as e:
            print("Error", f"File transfer failed: {e}")
    
    def empty_folder_rpi(self, remote_folder="/home/microscope/image_buffer") :
        """
        Empties the specified folder on the Raspberry Pi.

        This method connects to the Raspberry Pi via SSH, empties the specified folder, and then 
        closes the connection. The operation is handled by the RaspberryPiTransfer instance.

        Args:
            remote_folder (str): The path to the folder on the Raspberry Pi to be emptied.

        Returns:
            None
        """
        if not self.rpi_transfer:
            messagebox.showerror("Error", "Raspberry Pi connection is not established.")
            return
        
        try:
            # Create SSH, empty folder, then close SSH connection
            self.rpi_transfer.connect_ssh()
            self.rpi_transfer.empty_folder(remote_folder)
            self.rpi_transfer.close_ssh_connection()
            print("Success", f"Files successfully removed from {remote_folder}")
        except Exception as e:
            print("Error", f"Emptying folder failed: {e}")

    # ------------------- Raspberry Pi Communication Requests and Updates --------------- #
    
    def set_communication(self, comms, stop_event):
        """
        Assign a communication handler and stop event for managing Raspberry Pi communication.

        This method is used to set up the communication handler and the stop event for managing communication 
        with the Raspberry Pi. Object is instantiated and then passed into MainApp() from main.py

        Args:
            comms (object): The communication handler instance used for sending and receiving data.
            stop_event (threading.Event): The event that signals when the communication should stop.

        Returns:
            None
        """

        self.comms = comms
        self.stop_event = stop_event 

    def send_json_error_check(self, data, success_message):
        """
        Sends JSON data to the Raspberry Pi and handles different error responses.

        This method sends JSON data to the Raspberry Pi and checks the response for any errors. If an error 
        occurs, an error message is displayed; otherwise, a success message is shown.

        Args:
            data (dict): The JSON data to be sent to the Raspberry Pi.
            success_message (str): The message to be displayed if the transfer is successful.

        Returns:
            None
        """

        if self.comms:  # Ensure communication handler exists
            try:
                # Send data to Raspberry Pi
                response = self.comms.send_data(data)

                # If the response is successful
                if response and "error" in response:
                    # If there's an error in the response
                    messagebox.showerror("Error", f"Failed to send data: {response.get('message', 'Unknown error')}")
                else:
                    # Show success message in GUI
                    print(f"Response from Raspberry Pi: {response}")
                    messagebox.showinfo("Success", success_message)

            except Exception as e:
                messagebox.showerror("Error", f"Failed to send data: {e}")


    def unpack_pi_JSON(self, data):
        """
        Unpacks the status_data JSON file sent by the Raspberry Pi every second.
        Then stores them as instance variables for further processing.

        Args:
            data (dict): The JSON data received from the Raspberry Pi.

        Returns:
            None
        """

        try:
            #Module status
            self.module_status = data.get("module_status", "Raspberry Pi Not Connected")
            self.mode = data.get("mode", "Unknown")
            self.alarm_status = data.get("alarm_status", "Unknown")

            #Motion data
            self.motors_enabled = data.get("motors_enabled", False)
            self.x_pos = data.get("x_pos", 0)
            self.y_pos = data.get("y_pos", 0)
            self.z_pos = data.get("z_pos", 0)

            #Camera data
            self.exposure_time = data.get("exposure_time", 0)
            self.analog_gain = data.get("analog_gain", 0)
            self.contrast = data.get("contrast", 0)
            self.colour_temp = data.get("colour_temp", 0)

            #Image status and sample_id
            self.total_image = data.get("total_image", 0)
            self.image_count = data.get("image_count", 0)
            self.curr_sample_id = data.get("curr_sample_id", "Unknown")

        except Exception as e:
            print(f"Error unpacking JSON data: {e}")
    

    def update_status_data(self, data):
        """
        Unpacks and updates data from the Raspberry Pi.

        This method unpacks the status data received from the Raspberry Pi and updates the GUI 
        elements accordingly. It is typically called during the communication process.

        Args:
            data (dict): The status data received from the Raspberry Pi.

        Returns:
            None
        """

        # Extract values from the received data dictionary
        self.unpack_pi_JSON(data)

        #Update GUI elements on the main thread
        self.content_frame.after(0, self.update_gui_elements)


    def update_gui_elements(self):   
        """
        Updates the GUI elements based on the current status data.

        This method is called to refresh the GUI elements, including status labels, motor pane labels,
        camera pane labels, and the last updated time. It also controls the state machine for scanning 
        and random sampling.
        """  

        #Update top and bottom frame parts
        self.status_label.configure(text=f"Module Status: {self.module_status}")
        self.alarm_label.configure(text=f"Alarms: {self.alarm_status}")
        self.sample_label.configure(text=f"Current Sample: {self.curr_sample_id}")
        
        #Update motor pane labels
        self.rpi_motors_enabled_var.set(str(self.motors_enabled))
        self.rpi_x_pos_var.set(str(self.x_pos))
        self.rpi_y_pos_var.set(str(self.y_pos))
        self.rpi_z_pos_var.set(str(self.z_pos))

        #Update camera pane labels
        self.rpi_exposure_var.set(str(self.exposure_time))
        self.rpi_analog_gain_var.set(str(self.analog_gain))
        self.rpi_contrast_var.set(str(self.contrast))
        self.rpi_colour_temp_var.set(str(self.colour_temp))

        # Update last refreshed time, used in camera and motor pane
        self.last_refreshed_var.set(f"Last Updated: {datetime.now().strftime('%H:%M:%S')}")

        #Stitching Image Process
        #Change state to start scanning process
        if (self.scanning_state == 0 
            and (self.total_image - 1) == self.image_count
            and self.total_image != 0 
            and self.module_status == "Scanning Running"):

            self.scanning_state = 1 
        
        #Start transfer folder thread when all images have been taken
        if self.scanning_state == 1 and self.total_image == 0:
            self.transfer_rpi_thread = Thread(target=self.transfer_folder_rpi, kwargs={"destination_path": self.buffer_stitching_folder, "new_filename": True}, daemon=True)
            self.transfer_rpi_thread.start()
            
            self.scanning_state = 2

        #When folders transfered, calculate x and y grid, empty folder on rpi, and start image stitching thread
        if self.scanning_state == 2 and not self.transfer_rpi_thread.is_alive() :
            self.scanning_grid_x , self.scanning_grid_y = self.extract_unique_positions(self.buffer_stitching_folder) 
            self.start_stitching(self.scanning_grid_x, self.scanning_grid_y, self.buffer_stitching_folder, self.buffer_stitching_folder, self.curr_sample_id)
            self.display_scanning_layout(self.scanning_grid_x, self.scanning_grid_y, self.main_right_frame)
            self.empty_folder_rpi()

            self.scanning_state = 3 
        
        #Update button to show stitched image in gui when image stitching is done
        if self.scanning_state == 3 and not self.stitching_thread.is_alive() :
            self.complete_image_btn.configure(text="Completed Image Here", state="normal")

            self.scanning_state = 0 #Reset mini state machine
            
        #Random Samping Image Processing
        #Start mini state machine for random sampling process
        if (self.sampling_state == 0
            and (self.total_image - 1) == self.image_count 
            and self.total_image != 0 
            and self.module_status == "Random Sampling Running") :

            self.sampling_state = 1

        #When all images have been taken, start transfer folder thread
        if self.sampling_state == 1 and self.total_image == 0 :
            self.transfer_rpi_thread = Thread(target=self.transfer_folder_rpi, kwargs={"destination_path": self.buffer_sampling_folder, "new_filename": False}, daemon=True)
            self.transfer_rpi_thread.start()

            self.sampling_state = 2

        #Wait for the trasnfer folder thread to finish, then empty folder on Raspberry Pi
        if self.sampling_state == 2 and not self.transfer_rpi_thread.is_alive():
            self.empty_folder_rpi() 

            self.sampling_state = 0 #Reset mini state machine
        

    def send_sample_data(self, mount_type, sample_id, initial_height, layer_height, width, height):
        """
        Stores sample data, sends it to the Raspberry Pi, and sends command.

        Args:
            mount_type (str): The type of the mount.
            sample_id (str): The ID of the sample.
            initial_height (float): The initial height of the sample.
            layer_height (float): The layer height for the sample.
            width (float): The width of the bounding box.
            height (float): The height of the bounding box.

        Returns:
            None
        """

        # Store the sample data
        self.sample_data['command'] = "create_sample"
        self.sample_data['mode'] = "Manual"
        self.sample_data['mount_type'] = mount_type
        self.sample_data['sample_id'] = sample_id
        self.sample_data['initial_height'] = initial_height
        self.sample_data['layer_height'] = layer_height
        self.sample_data['width'] = width
        self.sample_data['height'] = height

        #Send sample data
        success_message = "Sample parameters sent."
        self.send_json_error_check(self.sample_data, success_message)
        
        #First sample loaded
        self.sample_loaded = True


    def send_simple_command(self, command, checkIdle):
        """
        Send JSON data to Raspberry Pi to request to run a method.
        Used for simple requests e.g., exe_homing_xy.

        Args:
            command (str): The command to send to Raspberry Pi.
            checkIdle (bool): A flag to check if the module status is "Idle".

        Returns:
            None
        """

        json_data = {
            "command" : command,
            "mode" : self.mode,
            "module_status" : self.module_status
        }

        #Prevent request from being sent of status is NOT "Idle"
        if self.module_status != "Idle" and checkIdle :
            messagebox.showerror("Status not in idle, wait before sending request.")
        else:
            success_message = "Request sent."
            self.send_json_error_check(json_data, success_message)


    def send_sampling_data(self, num_images):
        """Store and send random sampling data to Raspberry Pi.

        Args:
            num_images (int): The number of images to sample.

        Returns:
            None
        """

        #Prevents request from being sent if status is NOT "Idle"
        if self.module_status == "Idle":

            #Store random sampling data
            self.sampling_data['command'] = "exe_sampling"
            self.sampling_data['mode'] = self.mode
            self.sampling_data['module_status'] = self.module_status
            self.sampling_data['total_image'] = num_images

            #Send random sampling data
            success_message = "Random sampling request sent."
            self.send_json_error_check(self.sampling_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")
    

    def send_scanning_data(self, step_x, step_y):
        """
        Store and send scanning data to Raspberry Pi.

        Args:
            step_x (float): The step size in the x direction.
            step_y (float): The step size in the y direction.

        Returns:
            None
        """

        #Prevent request from being sent of status is NOT "Idle"
        if self.module_status == "Idle":

            #Check to see if step values are positive
            if step_x < 0 or step_y < 0:
                messagebox.showerror("Invalid input", "Step values must be positive numbers") 
                return   

            #Store scanning sampling data
            self.scanning_data['command'] = "exe_scanning"
            self.scanning_data['mode'] = self.mode
            self.scanning_data['module_status'] = self.module_status
            self.scanning_data['step_x'] = step_x
            self.scanning_data['step_y'] = step_y

            #Send scanning data
            success_message = "Scanning request sent."
            self.send_json_error_check(self.scanning_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")
    

    def send_camera_data(self, exposure_time, analog_gain, contrast, colour_temp):
        """
        Send updated camera settings to Raspberry Pi and update command.

        Args:
            exposure_time (float): The exposure time for the camera.
            analog_gain (float): The analog gain for the camera.
            contrast (float): The contrast for the camera.
            colour_temp (float): The color temperature for the camera.

        Returns:
            None
        """
        
        #Prevent request from being sent of status is NOT "Idle"
        if self.module_status == "Idle":
            camera_data = {
                "command" : "exe_camera_settings",
                "mode" : self.mode,
                "module_status" : self.module_status,
                "exposure_time" : exposure_time,
                "analog_gain" : analog_gain,
                "contrast" : contrast,
                "colour_temp" : colour_temp
            }

            #Send camera data
            success_message = "Updated camera settings sent."
            self.send_json_error_check(camera_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait before modifying camera settings.")
    

    def send_goto_command(self, req_x, req_y, req_z) :
        """
        Send goto data and command to Raspberry Pi, with x, y, z positions.

        Args:
            req_x (float): The requested x position.
            req_y (float): The requested y position.
            req_z (float): The requested z position.

        Returns:
            None
        """

        #Prevent request from being sent of status is NOT "Idle"
        if self.module_status == "Idle":

            #Checks if new positions are positive
            if req_x < 0 or req_y < 0 or req_z < 0:
                messagebox.showerror("Invalid input", "Step values must be positive numbers") 
                return   

            goto_data = {
                "command" : "exe_goto",
                "mode" : self.mode,
                "module_status" : self.module_status,
                "req_x_pos" : req_x,
                "req_y_pos" : req_y,
                "req_z_pos" : req_z
            }

            #Send goto data
            success_message = "Go to position sent."
            self.send_json_error_check(goto_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")

    # =============================== Image Stitching ==========================================#
    
    def set_stitcher(self, stitcher) :
        """
        
        Creates object of stitcher. 
        Object instantiated and passed into MainApp() in main.py

        Args:
            stitcher (object): The stitcher object to initialize.

        Returns:
            None
        """

        self.stitcher = stitcher

    def start_stitching(self, grid_x, grid_y, input_dir, output_dir, sample_id) :
        """
        
        Starts thread for stitching. 
        Pass in arguments needed to be passed to macro thats sent to ImageJ.

        Args:
            grid_x (int): The number of columns in the stitching grid.
            grid_y (int): The number of rows in the stitching grid.
            input_dir (str): The directory containing the images to stitch.
            output_dir (str): The directory to save the stitched image.
            sample_id (str): The ID of the current sample.

        Returns:
            None
        """

        # Using a lambda function to pass the arguments to run_stitching
        self.stitching_thread = Thread(target=lambda: self.stitcher.run_stitching(grid_x, grid_y, input_dir, output_dir, sample_id), daemon=True)
        self.stitching_thread.start()



#To do

#Calibration
#Fill in frame
#connect routine

#Camera settings
#Settings are properly sent to the raspberry Pi, but it doesn't actually uppdate

#Motion tab
#Graph is setup on the GUI, but it doesn't update based on Raspberry Pi live data


#Close sockets on raspberry pi on gui closing
