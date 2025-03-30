import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageTk
from datetime import datetime
import time
import json
import re
import os
import shutil
from threading import Thread

from communication import CommunicationHandler


class MainApp(ctk.CTk):
    def __init__(self):
    #====================================================================================#
    #----------------------------- Variables and Instantiation -------------------------#
    #====================================================================================#
        super().__init__()

        # Disable decompression bomb protection for stitched image
        Image.MAX_IMAGE_PIXELS = None  

        #---------- Raspberry Pi JSON Keys instatiate ----------#
        #Module states and data
        self.module_status = "Unknown"
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

        #------ JSON Objects sent to rapsberry pi ------#
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

        #-------------- Flags -----------------------#
        self.sample_loaded = False
        self.sampling_state = 0
        self.scanning_state = 0 

        self.req_download_sampling = False
        self.req_download_scanning = False
        self.req_sampling_empty = False
        self.req_scanning_part2 = False

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

        # Update last refreshed time
        #Used in camera and motor pane
        self.last_refreshed_var = ctk.StringVar(value="Last Updated: --")

        #--------------------- GUI Appearance Variables ---------------------------#
        #Skeleton appearance
        self.title("Control Panel")
        self.geometry("800x600")
        self.minsize(800, 550)  # Set the minimum width and height
        ctk.set_appearance_mode("dark")  # Options: "dark", "light", "system"

        #Image related info from pi
        #Images for GUI aesthetics
        self.img_gui = "C:/Users/GraemeJF/Documents/Capstone/Images/GUI"
        #Raw string in order to pass to Fiji succesfully for image stitching
        self.img_scanning_folder = r"C:\\Users\\GraemeJF\\Documents\\Capstone\\Images\\buffer\\stitching"
        self.img_sampling_folder = "C:/Users/GraemeJF/Documents/Capstone/Images/buffer/sampling"
        self.img_testing_folder = "C:/Users/GraemeJF/Documents/Capstone/Images/buffer/camera_tests"

        # Top & Bottom Frames
        self.create_top_frame()
        self.create_bottom_frame()

        # Content Frame
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(expand=True, fill='both')

        #Raspberry Pi files
        self.rpi_transfer = None

        self.display_main_tab()

    #====================================================================================#
    #----------------------------- GUI Appearances and Main app -------------------------#
    #====================================================================================#

    #------------------------------- Main Frame ------------------------------------------#

    #Top Frame
    def create_top_frame(self):
        '''Creates top frame with mode, status, and alarm labels'''

        top_frame = ctk.CTkFrame(self)
 
        #Space between the edge and the frame
        top_frame.pack(side=ctk.TOP, fill='x', padx=10, pady=5)
 
        self.status_label = ctk.CTkLabel(top_frame, text=f"Module Status: {self.module_status}")
        self.status_label.pack(side=ctk.LEFT, padx=10)

        self.mode_label = ctk.CTkLabel(top_frame, text=f"Mode: {self.mode}")
        self.mode_label.pack(side=ctk.LEFT, padx=30)

        self.sample_label = ctk.CTkLabel(top_frame, text=f"Current Sample: {self.curr_sample_id}")
        self.sample_label.pack(side=ctk.LEFT, padx=30)

        self.alarm_label = ctk.CTkLabel(top_frame, text=f"Alarms: {self.alarm_status}")
        self.alarm_label.pack(side=ctk.RIGHT, padx=10)

    #Bottom frame
    def create_bottom_frame(self):
        '''Creates Bottom Frame with tab buttons and date and time'''

        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(side=ctk.BOTTOM, fill='x', padx=10, pady=5)

        tabs = ["Main", "Motion", "Image", "Details"]
        for tab in tabs:
            tab_btn = ctk.CTkButton(bottom_frame, text=tab, font=("Arial", 20), command=lambda t=tab: self.switch_tab(t))
            tab_btn.pack(side=ctk.LEFT, padx=5)

        self.date_time_label = ctk.CTkLabel(bottom_frame, text="", font = ("Arial", 14))
        self.date_time_label.pack(side=ctk.RIGHT, padx=5)
        self.update_time()

    #Tab Navigation
    def switch_tab(self, tab_name):
        '''Functionality to switch between tabs on bottom frame'''

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
        """Displays the Main Frame with buttons on the left, and picture holder on the right"""

        self.clear_frame(self.content_frame)

        #Setup frame padding on left and right
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
                                     command = lambda: self.open_sampling_dialog(self.main_right_frame))
        scanning_btn = ctk.CTkButton(left_frame, text="Scanning", font=("Arial", 20), width = 200, height = 100, 
                                     command = lambda: self.open_scanning_dialog(self.main_right_frame))

        create_sample_btn.pack(pady=5, fill='x')
        sampling_btn.pack(pady=5, fill='x')
        scanning_btn.pack(pady=5, fill='x')

        calibration_btn = ctk.CTkButton(left_frame, width = 200, height = 50, text="Calibration", font=("Arial", 20),
                                        command=lambda :self.send_simple_command("exe_calibration", True))
        calibration_btn.pack(pady=5, fill='x')

    #Image Place Holder
    def display_placeholder_image(self, frame):
        '''Displays image on main tab in the right frame'''

        #dir
        img = Image.open(f"{self.img_gui}/assy_centered.png")  # Replace with your image path
        img = img.resize((1295, 1343), Image.LANCZOS)
        tilt_img = img.rotate(-1)

        # Create a CTkImage instance
        img_ctk = ctk.CTkImage(tilt_img, size=(800, 800))

        # Create the CTkLabel and display the CTkImage
        img_label = ctk.CTkLabel(frame, image=img_ctk, text="")
        img_label.image = img_ctk  # Keep reference to the image

        # Center the image within the frame using place() method
        img_label.place(relx=0.5, rely=0.5, anchor="center")  # This centers the image in the frame


    #------------------------------- Dialogs and Pop-ups ------------------------------------------#

    #Sample data dialog box
    def open_sample_dialog(self):
        '''Pop-up window to enter in sample data parameters and then send to the raspberry pi'''

        #Window setup
        sample_window = ctk.CTkToplevel(self)
        sample_window.title("Enter Sample Parameters")
        sample_window.geometry("320x420")
        sample_window.minsize(320, 440)
        #sample_window.maxsize(320, 440)

        sample_window.grab_set()

        #Mount type (ie puck, stub), drop down
        ctk.CTkLabel(sample_window, text="Select your mount type:").grid(row = 0, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        mount_type = ctk.CTkComboBox(sample_window, values=["Puck", "Stub"])
        mount_type.grid(row = 1, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #sample id
        ctk.CTkLabel(sample_window, text="Enter Sample ID:").grid(row=2, column=0, columnspan=4, padx=1, pady=1, sticky="ew")
        sample_id = ctk.CTkEntry(sample_window, placeholder_text = "e.g. Sample_24_03_2025")
        sample_id.grid(row=3, column=0, columnspan=4, padx=10, pady=5)

        #Sample height
        ctk.CTkLabel(sample_window, text="Enter starting sample height:").grid(row = 4, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        initial_height = ctk.CTkEntry(sample_window)
        initial_height.grid(row = 5, column = 1, columnspan = 2, padx=1, pady=1, sticky="ew")

        #Sample layer height
        ctk.CTkLabel(sample_window, text="Enter sample layer height:").grid(row = 6, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        ctk.CTkLabel(sample_window, text="(For scanning enter 0.)", font=("Arial",12,"italic")).grid(row = 7, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        ctk.CTkLabel(sample_window, text="(i.e. Amount of material removed each layer):").grid(row = 8, column = 0, columnspan = 4, pady=1, sticky = "ew")
        layer_height = ctk.CTkEntry(sample_window, width = 50)
        layer_height.grid(row = 9, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #------Bounding box -----
        #Width
        ctk.CTkLabel(sample_window, text="Enter bounding box size:").grid(row = 10, column = 0, columnspan = 4, padx=5, pady=1, sticky="ew")
        ctk.CTkLabel(sample_window, text="Width:").grid(row=11, column=0, padx=1, pady=1, sticky = "e")
        sample_width = ctk.CTkEntry(sample_window, width = 50)
        sample_width.grid(row = 11, column = 1, padx=5, pady=5, sticky = "w")

        #Length
        ctk.CTkLabel(sample_window, text="Length:").grid(row=11, column=2, padx=5, pady=5, sticky = "e")
        sample_length = ctk.CTkEntry(sample_window, width = 50)
        sample_length.grid(row = 11, column = 3, padx=5, pady=10, sticky = "w")

        #Ok button
        #Closes the window and calls function send_sample_data() on ok
        ok_button = ctk.CTkButton(sample_window, text="OK", 
                                  command=lambda: [self.send_sample_data(mount_type.get(), sample_id.get(),
                                                      float(initial_height.get()), float(layer_height.get()), 
                                                      float(sample_width.get()), float(sample_length.get())), 
                                                      sample_window.destroy()], width = 80)

        ok_button.grid(row = 12, column = 0, padx=5, pady=5)

        #Cancel button, closes window
        ctk.CTkButton(sample_window, text="Cancel", command=sample_window.destroy, width = 80).grid(row = 12, column = 3, columnspan = 2, padx=5, pady=5)

    #Random sampling data dialog
    def open_sampling_dialog(self, frame):
        '''Dialog box to enter in random sampling data and send request'''

        # Window setup
        image_sampling_window = ctk.CTkToplevel(self)
        image_sampling_window.title("Enter Sampling Parameters")
        image_sampling_window.geometry("350x135")  # Set initial size
        image_sampling_window.minsize(350, 135)   # Limit the minimum size
        #image_sampling_window.maxsize(400, 135)   # Limit the maximum size

        image_sampling_window.grab_set()

        # New prompt text
        label = ctk.CTkLabel(image_sampling_window, text="Enter in the number of images taken for random sampling:")
        label.grid(row=0, column=0, columnspan=4, padx=5, pady=10, sticky="ew")

        # Total images input field
        ctk.CTkLabel(image_sampling_window, text="Total Number of Images:").grid(row=1, column=0, columnspan = 2, padx=5, pady=5, sticky="e")
        total_images = ctk.CTkEntry(image_sampling_window, placeholder_text="6")
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

        # Simple validation function
        def validate_input(*args):
            try:
                value = int(total_images.get())
                # Check if value is between 1 and 15
                if 1 <= value <= 40 and self.module_status == "Idle" :
                    ok_button.configure(state="normal")  # Enable OK button
                else:
                    ok_button.configure(state="disabled")  # Disable OK button
            except ValueError:
                ok_button.configure(state="disabled")  # Disable OK button if input is not a number

        # Trace the input changes and call validate_input
        total_images.bind("<KeyRelease>", validate_input)

    #Scanning Parameter Dialog
    def open_scanning_dialog(self, frame):
        '''Scanning dialog box to enter in data and send request to raspberry pi'''

        # Window setup
        image_scanning_window = ctk.CTkToplevel(self)
        image_scanning_window.title("Enter Scanning Parameters")
        image_scanning_window.geometry("335x210")  # Set initial size
        image_scanning_window.minsize(335, 210)   # Limit the minimum size
        image_scanning_window.maxsize(335, 200)   # Limit the maximum size

        image_scanning_window.grab_set()

        # New prompt text
        label = ctk.CTkLabel(image_scanning_window, text="Please enter the scanning bounding box:", font=("Arial", 12, "bold"))
        label.grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky="e")
        tip_label = label = ctk.CTkLabel(image_scanning_window, text="Default is 5 for step x, and 4 for step y", font=("Arial", 12, "italic"))
        tip_label.grid(row=1, column=0, columnspan=4, padx=5, pady=3, sticky="e")

        # Step x input field
        ctk.CTkLabel(image_scanning_window, text="Step x:").grid(row=2, column=0, padx=5, pady=10, sticky="e")
        step_x = ctk.CTkEntry(image_scanning_window, placeholder_text="1")
        step_x.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Step y input field
        ctk.CTkLabel(image_scanning_window, text="Step y:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        step_y = ctk.CTkEntry(image_scanning_window, placeholder_text="1")
        step_y.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # OK button (closes the window, changes frame, sends scanning_data
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
                if value_x > 0 and value_y > 0:
                    ok_button.configure(state="normal")  # Enable OK button
                else:
                    ok_button.configure(state="disabled")  # Disable OK button
            except ValueError:
                ok_button.configure(state="disabled")  # Disable OK button if input is not a valid number

        # Trace the input changes and call validate_input
        step_x.bind("<KeyRelease>", validate_input)
        step_y.bind("<KeyRelease>", validate_input)

    #Homing Dialog Box
    def open_homing_dialog(self):
        '''Homing dialog box to request which type of homing routine to run, XY or All'''

        # Window setup
        homing_window = ctk.CTkToplevel(self)
        homing_window.title("Select Homing Type")
        homing_window.geometry("300x250")  # Set initial size
        homing_window.minsize(300, 250)   # Limit the minimum size
        homing_window.maxsize(300, 250)   # Limit the maximum size

        homing_window.grab_set()  # Makes the window modal

        # Prompt text
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
        '''Appearances and functinality for the Motion tab frames'''

        #Left frame
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)

        #right_frame = ctk.CTkFrame(self.content_frame)
        #right_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)
        
        #Middle frame
        main_frame = ctk.CTkFrame(self.content_frame)
        main_frame.pack(side=ctk.LEFT, expand=True, fill='both', padx=10, pady=10)

        coord_frame = ctk.CTkFrame(left_frame)
        coord_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=10)

        # Create a separate button frame inside left_frame (placed at the bottom)
        button_frame = ctk.CTkFrame(left_frame)
        button_frame.pack(side=ctk.BOTTOM, fill="x", padx=10, pady=10)

        # Left Frame: Entry Boxes and Buttons
        coord_label = ctk.CTkLabel(coord_frame, text="Enter in desired coordinates:", font=("Arial", 14, "bold"))
        coord_label.grid(row=0, column=0, columnspan = 3, padx=5, pady=5, sticky="ew")

        # Position Controls
        self.create_position_control(coord_frame, "X", self.x_pos, row=1)
        self.create_position_control(coord_frame, "Y", self.y_pos, row=2)
        self.create_position_control(coord_frame, "Z", self.z_pos, row=3)

        #Send coordinates button
        send_coord_btn = ctk.CTkButton(coord_frame, text="Send Coordinates", font=("Arial", 14), 
                                       command=lambda: self.send_goto_command(float(self.x_entry.get()),float(self.y_entry.get()),float(self.z_entry.get())))
        send_coord_btn.grid(row=4, column=0, columnspan = 3, padx=5, pady=5, sticky="ew")

        #Refresh the coordinates with the current ones
        refresh_coord_btn = ctk.CTkButton(coord_frame, text="Refresh Coordinates", font=("Arial", 14), command=self.refresh_motor_coord)
        refresh_coord_btn.grid(row=5,column=0,columnspan = 3, padx=5, pady=5, sticky="ew")

        # Additional Controls
        #Homing Button
        home_btn = ctk.CTkButton(button_frame, text="Homing", width = 200, height = 50, font=("Arial", 20), fg_color="blue", text_color="white",
                                 command = lambda: self.open_homing_dialog())        
        home_btn.pack(pady=5, fill='x')

        #Disable stepper motors, checks if Idle
        disable_motors_btn = ctk.CTkButton(button_frame, text="Disable Stepper Motors", 
                                           command=lambda: self.send_simple_command("exe_disable_motors", True))
        disable_motors_btn.pack(pady=5, fill="x")

        # Graph Display
        #self.create_graphs(right_frame)

        #Stop button, for if running GoTo
        stop_btn = ctk.CTkButton(button_frame, text="STOP", fg_color="red", command=lambda: self.send_simple_command("exe_stop", False))
        stop_btn.pack(pady=5, fill="x")

        #Data from Raspberry Pi in Main Tab
        #Motors Enabled
        motors_enabled_label = ctk.CTkLabel(main_frame, text="Motors Enabled")
        motors_enabled_label.pack(pady=5, fill='x')
        self.rpi_motors_enabled_var = ctk.StringVar(value="--")  # Dynamic variable
        self.rpi_motors_enabled_label = ctk.CTkLabel(main_frame, textvariable=self.rpi_motors_enabled_var)
        self.rpi_motors_enabled_label.pack(pady=5, fill='x')

        # X position
        x_pos_label = ctk.CTkLabel(main_frame, text="X Position (mm)")
        x_pos_label.pack(pady=5, fill="x")
        self.rpi_x_pos_var = ctk.StringVar(value="--")
        self.rpi_x_pos_label = ctk.CTkLabel(main_frame, textvariable=self.rpi_x_pos_var)
        self.rpi_x_pos_label.pack(pady=5, fill='x')

        # Y position
        y_pos_label = ctk.CTkLabel(main_frame, text="Y Position (mm)")
        y_pos_label.pack(pady=5, fill="x")
        self.rpi_y_pos_var = ctk.StringVar(value="--")
        self.rpi_y_pos_label = ctk.CTkLabel(main_frame, textvariable=self.rpi_y_pos_var)
        self.rpi_y_pos_label.pack(pady=5, fill='x')

        # Z position
        z_pos_label = ctk.CTkLabel(main_frame, text="Z Position (mm)")
        z_pos_label.pack(pady=5, fill="x")
        self.rpi_z_pos_var = ctk.StringVar(value="--")
        self.rpi_z_pos_label = ctk.CTkLabel(main_frame, textvariable=self.rpi_z_pos_var)
        self.rpi_z_pos_label.pack(pady=5, fill='x')

        # Last Refreshed Label
        self.last_refreshed_var = ctk.StringVar(value="Last Updated: --")
        self.last_refreshed_label = ctk.CTkLabel(main_frame, textvariable=self.last_refreshed_var, font=("Arial", 12))
        self.last_refreshed_label.pack(pady=5)

    #Refresh motor data
    def refresh_motor_coord(self):
        """Fetch data being updated from raspberry pi and update entries dynamically"""

        self.x_entry.delete(0, "end")
        self.x_entry.insert(0, str(self.x_pos))

        self.y_entry.delete(0, "end")
        self.y_entry.insert(0, str(self.y_pos))

        self.z_entry.delete(0, "end")
        self.z_entry.insert(0, str(self.z_pos))


    #Position control
    def create_position_control(self, parent, label, value, row):
        '''Create label, buttons, and entries for a single position'''

        ctk.CTkLabel(parent, text=f"{label} Position:",font=("Arial", 18)).grid(row=row, column=0, padx=5, pady=2, sticky='w')
        entry = ctk.CTkEntry(parent, width=30)
        entry.insert(0, str(value))
        entry.grid(row=row, column=2, padx=3, pady=2)
        self.create_step_buttons(parent, entry, row=row)

        entry.grid(row=row, column=2, padx=3, pady=2)

         # Store the entry in self for later access
        if label == "X":
            self.x_entry = entry
        elif label == "Y":
            self.y_entry = entry
        elif label == "Z":
            self.z_entry = entry

        self.create_step_buttons(parent, entry, row=row)

    #Step Adjustement buttons
    def create_step_buttons(self, parent, entry_widget, step=1, row=0):
        '''Create up and down buttons for motion control tab'''

        btn_frame = ctk.CTkFrame(parent)
        btn_frame.grid(row=row, column=1, padx=5, pady=2)

        ctk.CTkButton(btn_frame, text="▲", width=30, command=lambda: self.adjust_value(entry_widget, step)).grid(row=0, column=0, padx=2)
        ctk.CTkButton(btn_frame, text="▼", width=30, command=lambda: self.adjust_value(entry_widget, -step)).grid(row=0, column=1, padx=2)
        btn_frame.grid(row=row, column=1, padx=5, pady=2)

        ctk.CTkButton(btn_frame, text="▲", width=30, command=lambda: self.adjust_value(entry_widget, step)).grid(row=0, column=0, padx=2)
        ctk.CTkButton(btn_frame, text="▼", width=30, command=lambda: self.adjust_value(entry_widget, -step)).grid(row=0, column=1, padx=2)
    
    #Adjust entries for position coord
    def adjust_value(self, entry, step):
        '''Takes the entry widget, and updates it based on step adjustements'''

        try:
            current_value = int(entry.get())
            entry.delete(0, ctk.END)
            entry.insert(0, str(current_value + step))
        except ValueError:
            entry.delete(0, ctk.END)
            entry.insert(0, "0")

    #Grid that shows location of camera and z-axis
    #Not in use
    def create_graphs(self, parent):
        '''Create graphs for displaying motion control location of camera'''
    
        # Create a frame to hold both graphs
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

    # ------------------ Image Tab ------------------ #
    def display_image_tab(self):
        """Displays the Image tab layout with parameter input, current values, and image preview."""
 
        # Clear previous content in the content frame
        self.clear_frame(self.content_frame)
 
        # Setup frames
        param_frame = ctk.CTkFrame(self.content_frame, width=300, height = 400)
        param_frame.grid(row=0, column=0, sticky="ns", padx=10, pady=10)
 
        right_frame = ctk.CTkFrame(self.content_frame)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
 
        # --- LEFT PANEL with TWO COLUMNS ---
        title_label = ctk.CTkLabel(param_frame, text="Camera Parameters", font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, columnspan=1, pady=(0, 10),  sticky="w")
 
       
        curr_param_label = ctk.CTkLabel(param_frame, text="Current Parameters", font=("Arial", 12))
        curr_param_label.grid(row=1, column=1, columnspan=1, pady=(0, 10), padx = 10, sticky="ew")
 
        # Last updated timestamp
        self.last_refreshed_var = ctk.StringVar(value="Last Updated: --")
        self.last_refreshed_label = ctk.CTkLabel(param_frame, textvariable=self.last_refreshed_var, font=("Arial", 12))
        self.last_refreshed_label.grid(row=1, column=0, columnspan=1, sticky="w", pady=10, padx=5)
 
        param_labels = ["Exposure Time (microsec):", "Analog Gain (1=no gain):",
                        "Contrast (0-32, 1=no value):", "Colour Temperature (K):"]
       
        self.entries = []
        self.current_vars = []
 
        for i, label_text in enumerate(param_labels):
            # Label and Entry (Column 0)
            label = ctk.CTkLabel(param_frame, text=label_text)
            label.grid(row=i+2, column=0, sticky="w", padx=5, pady=5)
 
            entry = ctk.CTkEntry(param_frame, width = 50)
            entry.grid(row=i+2, column=0, sticky="e", padx=(170, 5), pady=5)
            self.entries.append(entry)
 
            # Current Parameter Value (Column 1)
            var = ctk.StringVar(value="-Value Not Updated-")
            current_label = ctk.CTkLabel(param_frame, textvariable=var, font = ("Arial", 12))
            current_label.grid(row=i+2, column=1, sticky="ew", padx=5, pady=5)
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
 
        # SEND DATA Button
        send_data_btn = ctk.CTkButton(param_frame, text="Send Data", font=("Arial", 16),
                                    command=lambda: self.send_camera_data(
                                        float(self.exposure_time_entry.get()),
                                        float(self.analog_gain_entry.get()),
                                        float(self.contrast_entry.get()),
                                        float(self.colour_temp_entry.get())), width = 100)
        send_data_btn.grid(row=len(param_labels)+2, column=0, columnspan=1, pady=10)
 
        #Refresh Button
        refresh_data_btn = ctk.CTkButton(param_frame, text = "Refresh Data", font=("Arial", 16), width = 100, command=self.refresh_camera_entries)
        refresh_data_btn.grid(row=len(param_labels)+2, column=1, columnspan=1, pady=10)
 
        # --- RIGHT PANEL: IMAGE AND BUTTONS ---
        image_label = ctk.CTkLabel(right_frame, text="Image will appear here", fg_color="gray", width=400, height=400)
        image_label.pack(expand=True, fill='both', pady=20)
 
        button_frame = ctk.CTkFrame(right_frame)
        button_frame.pack(pady=10, fill='x')
 
        # Rename "Request Image" -> "Take Image"
        req_image_btn = ctk.CTkButton(button_frame, text="Take Image", font=("Arial", 16),
                                    command=lambda:[self.send_simple_command("exe_update_image", True),self.transfer_folder_rpi(self.img_testing_folder)])
        req_image_btn.pack(side="left", padx=10, fill='x', expand=True)
 
        # Combine Grab + Display
        display_image_btn = ctk.CTkButton(button_frame, text="Display Image", font=("Arial", 16),
                                        command=lambda: (self.transfer_folder_rpi(self.img_testing_folder),
                                                        self.show_image(self.img_testing_folder, image_label)))
        display_image_btn.pack(side="right", padx=10, fill='x', expand=True)

        #Refresh motor data
    def refresh_camera_entries(self):
        """Fetch data being updated from raspberry pi and update entries dynamically"""

        self.exposure_time_entry.delete(0, "end")
        self.exposure_time_entry.insert(0, self.exposure_time)

        self.analog_gain_entry.delete(0, "end")
        self.analog_gain_entry.insert(0, self.analog_gain)

        self.contrast_entry.delete(0, "end")
        self.contrast_entry.insert(0, self.contrast)

        self.colour_temp_entry.delete(0, "end")
        self.colour_temp_entry.insert(0, self.colour_temp)

    def show_image(self, image_folder, image_label):
        """Function to update the image displayed in the right frame from a sent!path in the folder."""
    
        try:
            # Get the first image file in the folder (adjust as needed for multiple images)
            image_files = [f for f in os.listdir(image_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            
            if image_files:
                image_path = os.path.join(image_folder, image_files[0])  # Take the first image

                # Normalize the image path (in case of backslashes or other inconsistencies)
                image_path = os.path.normpath(image_path)

                # Open the image using PIL
                img_pil = Image.open(image_path)

                # Convert the image to a format that can be used with Tkinter
                img_tk = ImageTk.PhotoImage(img_pil)

                # Update the label to show the image
                image_label.configure(image=img_tk)
                image_label.image = img_tk  # Store a reference to the image to avoid garbage collection

                print("Image updated successfully :)")
            else:
                print("No image files found in the specified folder.")
                image_label.configure(text="No image found", fg_color="red")
        except Exception as e:
            print(f"Error displaying image: {e}")
            image_label.configure(text="Failed to display image", fg_color="red")

    # ------------------ Details Tab ------------------ #
    def display_details_tab(self):
        # Clear previous content in the content frame
        self.clear_frame(self.content_frame)

        # Main container frame (to hold both sections)
        main_frame = ctk.CTkFrame(self.content_frame)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        alarm_frame = ctk.CTkFrame(main_frame)
        alarm_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=5)

        refresh_button = ctk.CTkButton(alarm_frame, text="Refresh Alarm Status", command=lambda: [self.send_simple_command("exe_reset_alarm_status", False)])
        refresh_button.pack(side="right", padx=5, pady=5)

        #Instructions frame
        instructions_frame = ctk.CTkFrame(main_frame)
        instructions_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=5)

        instructions_label = ctk.CTkLabel(instructions_frame, text="Instructions", font=("Arial", 18, "bold"), anchor="w")
        instructions_label.pack(padx=10, pady=5, fill="x")

        instructions_text = (
            "1. Navigate through functionality using the tabs at the bottom of the GUI.\n\n"
            "2. The two key methods 'Random Sampling' and 'Scanning' can be found on the main frame.\n\n"
            "3. Before running one of the two methods, ensure you have loaded the sample data in "
            "\"Create a New Sample\" located on the top left in the \"Main tab\"\n\n"
            "4. Calibration is a routine that will give you a focused score on the cross-hairs on the platform. "
            "This is intended for occasional use to level the platform and lens manually.\n\n"
            "5. The motion tab provides functionality to disable the stepper motors, go to a coordinate, and home the system.\n\n"
            "6. The image tab allows for changing the image and camera settings.\n\n"
            "7. TIP: Whenever \"Stop\" is selected, the module will need to be homed again."
        )

        instructions_details = ctk.CTkLabel(instructions_frame, text=instructions_text, font=("Arial", 14), anchor="w", justify="left", wraplength=500)
        instructions_details.pack(padx=10, pady=5, fill="x")

        #Folder path
        folder_frame = ctk.CTkFrame(main_frame)
        folder_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=5)

        folder_label = ctk.CTkLabel(folder_frame, text="Image Directories", font=("Arial", 16, "bold"), anchor="w")
        folder_label.pack(padx=10, pady=5, fill="x")

        folders = [
            ("GUI Images Folder", self.img_gui),
            ("Scanning Folder", self.img_scanning_folder),
            ("Sampling Folder", self.img_sampling_folder)
        ]

        for label, folder in folders:
            entry_frame = ctk.CTkFrame(folder_frame)
            entry_frame.pack(fill="x", padx=10, pady=2)

            # Bold label
            label_widget = ctk.CTkLabel(entry_frame, text=f"{label}: ", font=("Arial", 14, "bold"), anchor="w")
            label_widget.pack(side="left")

            # Folder path
            folder_widget = ctk.CTkLabel(entry_frame, text=folder, font=("Arial", 14), anchor="w", justify="left", wraplength=500)
            folder_widget.pack(side="left", fill="x", expand=True)

    # --------------------- Display Calibration Frame ------------------ #
    def display_calibration_layout(self, frame) :
        '''Displays Calibration Frame'''
        
        self.clear_frame(frame)
        
        # Create the scanning frame to hold the images
        calibration_frame = ctk.CTkFrame(frame)
        calibration_frame.pack(side=ctk.TOP, expand=True, fill='both', padx=10, pady=10)

        # Create a frame for the buttons to always be at the bottom
        button_frame = ctk.CTkFrame(frame)
        button_frame.pack(side=ctk.BOTTOM, fill='x', pady=10)

        # Create and place the buttons inside the button frame
        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red", command=lambda:[self.send_simple_command("exe_stop", False)])
        stop_button.pack(side=ctk.LEFT, expand=True, padx=5, pady=5)

        finish_button = ctk.CTkButton(button_frame, text="Finish", command=self.display_main_tab)
        finish_button.pack(side=ctk.LEFT, expand=True, padx=5, pady=5)

    def get_image_layout_parameters(self,images_x, images_y):
        """
        Dynamically calculate image size and spacing based on grid size.

        Returns:
            tuple: (img_size, spacing)
        """
        grid_size = max(images_x, images_y)

        # Clamp grid_size to a minimum of 1 to avoid division by zero
        grid_size = max(grid_size, 1)

        # Dynamically interpolate img_size and spacing
        # Formula makes img_size shrink as grid grows
        img_size = int(300 / (0.35 * grid_size + 1))   # More generous base size + slower shrink
        spacing  = int(8 / (0.4 * grid_size + 1))      # Tighter spacing + quicker shrink

        return img_size, spacing

    # --------------------- Displaying Scanning Layout ------------------ #
    def display_loading_frame(self, frame):
        self.clear_frame(frame)
 
        self.current_image_index = 0
 
        # Save scanning layout parameters
        self.scanning_target_frame = frame
 
        # Main loading layout
        loading_frame = ctk.CTkFrame(frame)
        loading_frame.pack(expand=True, fill='both', padx=20, pady=20)
 
        self.loading_label = ctk.CTkLabel(loading_frame, text=f"{self.module_status}",font=("Arial", 20))
        self.loading_label.pack(pady=20)

        # STOP button (centered at bottom)
        button_frame = ctk.CTkFrame(loading_frame)
        button_frame.pack(side='bottom', fill='x', pady=15)
 
        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red", command=lambda:[self.display_main_tab(), self.send_simple_command("exe_stop", False)])

        stop_button.pack(side='bottom', pady=5)
 
    def display_scanning_layout(self, images_x, images_y, frame):
        """Displays the Scanning layout with a large image grid that updates as images are captured."""
        self.clear_frame(frame)

        self.expected_image_count = images_x * images_y
        self.current_image_index = 0
        self.image_folder_path = self.img_scanning_folder  # Save path for reuse

        # ----- Buttons -----
        button_frame = ctk.CTkFrame(frame)
        button_frame.pack(side=ctk.TOP, fill='x', pady=10)

        #Display sititched image
        stitched_img_path = f"{self.img_scanning_folder}\\stitched_{self.curr_sample_id}.jpg"
        self.complete_image_btn = ctk.CTkButton(button_frame, text="Image Stitching...", fg_color="green", width=150, height=30, 
                                                state="disabled", 
                                                command=lambda:[self.expand_image(stitched_img_path)])
        self.complete_image_btn.pack(side=ctk.LEFT, expand=True, padx=5, pady=1)

        #heyo
        #stephie
        new_folder_path = f"C:/Users/GraemeJF/Documents/Capstone/Images/complete/scanning/{self.curr_sample_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        finish_button = ctk.CTkButton(button_frame, text="Finish", 
                                      command=lambda:[self.display_main_tab(), self.create_transfer_folder_pc(self.img_scanning_folder,new_folder_path)])
        finish_button.pack(side=ctk.RIGHT, expand=True, padx=1, pady=1)

        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red", command=lambda:[self.display_main_tab(),self.send_simple_command("exe_stop",False)])
        stop_button.pack(side=ctk.RIGHT, expand=True, padx=5, pady=1)

        # ----- Layout -----
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

        # ----- Image Grid -----
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
        supported_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
        images = []

        for filename in sorted(os.listdir(folder_path)):
            if filename.lower().endswith(supported_extensions) and not filename.startswith("._"):
                full_path = os.path.join(folder_path, filename)
                try:
                    with Image.open(full_path) as img:
                        img.verify()
                    images.append(full_path)
                except Exception:
                    print(f"Skipping invalid image: {filename}")
        return images
    # ------------------ Displaying Random Sampling Layout ------------------ #
    def display_random_sampling_layout(self, num_images, frame):
        """Displays an evenly distributed grid layout for random sampling with live updates."""
        
        # Clear previous content
        self.clear_frame(frame)

        self.image_labels = []
        self.random_sampling_frame = ctk.CTkFrame(frame)  # Store for use in polling
        self.random_sampling_frame.pack(expand=True, fill='both', padx=10, pady=10)

        self.target_num_images = num_images
        self.img_size = 200  # You can use dynamic scaling if needed

        # Initial population
        images = self.load_images_from_folder(self.img_sampling_folder)
        self.populate_image_grid(self.random_sampling_frame, images, num_images, self.img_size)

        # Start polling folder for new images
        self.random_sampling_image_update()
        
        button_frame = ctk.CTkFrame(self.random_sampling_frame)
        button_frame.grid(row = 2, column = 0, columnspan = self.total_columns, pady=5, padx=10)
 
        # STOP button - aligned left
        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red", 
                                    command=lambda: [self.display_main_tab(), self.send_simple_command("exe_stop", False)])
        stop_button.pack(side='left', padx=5, fill = 'x', pady=5)
 
        # FINISH button - aligned right
        #heyo 
        #stephie
        new_folder_path = f"C:/Users/GraemeJF/Documents/Capstone/Images/complete/sampling/{self.curr_sample_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"     

        finish_button = ctk.CTkButton(button_frame, text="Finish", 
                                      command=lambda:[self.display_main_tab(),self.create_transfer_folder_pc(self.img_scanning_folder,new_folder_path)])
        finish_button.pack(side='right',fill = 'x', padx=5, pady=5)

        
# ------------------Populating image grid for the random sampling method ------------------ #
    def populate_image_grid(self, parent_frame, images, num_images, img_size):
        """Populate the image grid with images."""

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


    # ------------------ RANDOM SAMPLING Update the number of expected images ------------------ #
    def random_sampling_image_update(self):

        images = self.load_images_from_folder(self.img_sampling_folder)
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

    # ------------------ SCANNING Update the number of expected images ------------------ #
    def poll_for_new_images(self):
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

    #Expand images
    def expand_image(self, img_path):
        """Opens a new window displaying the image and resizes it based on the window size."""

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

        # Resize the image periodically based on window size
        def resize_image_periodically():
            """Periodically resize the image based on window size."""

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

    #====================================================================================#
    #-------------------------- GUI Communication and Functions -------------------------#
    #====================================================================================#

    # -------------------------------------- Funtcions ---------------------------------- #
    #Update time
    def update_time(self):
        '''Update timeer, used in bottom frame'''

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.date_time_label.configure(text=now)
        self.after(1000, self.update_time)

    #Clear frame
    def clear_frame(self, frame):
        """Destroys all widgets inside the given frame."""

        for widget in frame.winfo_children():
            widget.destroy()

    def create_transfer_folder_pc(self, src_folder, dest_folder):
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
        
    #Get unique positions for calculating grid for image stitching
    def extract_unique_positions(self, directory):
        """Extracts unique x and y positions from JSON objects in text files within the specified directory."""
        
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

    #============================== Communcation ====================================#
    
    #Setup communication
    def set_communication(self, comms, stop_event):
        '''Assign a communication handler from main.py'''

        self.comms = comms
        self.stop_event = stop_event 
    
    #Setup raspberry pi paramiko
    def set_rpi_transfer(self, transfer_obj):
        """Sets the RaspberryPiTransfer instance in the GUI."""
        self.rpi_transfer = transfer_obj
    
    #Get everything from raspberry pi folder and put in another folder
    def transfer_folder_rpi(self, destination_path, new_filename):
        """Call the transfer_folder method of RaspberryPiTransfer."""
        if not self.rpi_transfer:
            messagebox.showerror("Error", "Raspberry Pi connection is not established.")
            return

        remote_folder = "/home/microscope/image_buffer"
        local_folder = destination_path
        
        try:
            self.rpi_transfer.connect_sftp()
            self.rpi_transfer.transfer_folder(remote_folder, local_folder, new_filename)
            self.rpi_transfer.close_sftp_connection()
            print("Success", "Files successfully transferred!")
        except Exception as e:
            print("Error", f"File transfer failed: {e}")
    
    def empty_folder_rpi(self, remote_folder="/home/microscope/image_buffer") :
        """Empty image_buffer on raspberry pi."""
        if not self.rpi_transfer:
            messagebox.showerror("Error", "Raspberry Pi connection is not established.")
            return
        
        try:
            self.rpi_transfer.connect_ssh()
            print("connected")
            self.rpi_transfer.empty_folder(remote_folder)
            print("Emptied folder")
            self.rpi_transfer.close_ssh_connection()
            print("closed  connection")
            print("Success", f"Files successfully removed from {remote_folder}")
        except Exception as e:
            print("Error", f"Emptying folder failed: {e}")
        

    #Send json data
    def send_json_error_check(self, data, success_message):
        '''Send a JSON file to the rapsberry pi and communicate different errors'''

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

    #Unpack JSON data
    def unpack_pi_JSON(self, data):
        '''Unpack the status_data JSON file that the raspberry pi sends every second'''

        try:
            self.module_status = data.get("module_status", "Unknown")
            self.mode = data.get("mode", "Unknown")
            self.alarm_status = data.get("alarm_status", "Unknown")

            self.motors_enabled = data.get("motors_enabled", False)
            self.x_pos = data.get("x_pos", 0)
            self.y_pos = data.get("y_pos", 0)
            self.z_pos = data.get("z_pos", 0)

            self.exposure_time = data.get("exposure_time", 0)
            self.analog_gain = data.get("analog_gain", 0)
            self.contrast = data.get("contrast", 0)
            self.colour_temp = data.get("colour_temp", 0)

            self.total_image = data.get("total_image", 0)
            self.image_count = data.get("image_count", 0)
            self.curr_sample_id = data.get("curr_sample_id", "Unknown")

        except Exception as e:
            print(f"Error unpacking JSON data: {e}")
    
    #Update status data
    def update_status_data(self, data):
        '''
        Unpack and update data from raspberry pi
        Function is called in communication.py in the receive status updates
        '''

        #Store previous status before update
        prev_module_status = self.module_status
        #prev_image_count = self.image_count

        # Extract values from the received data dictionary, with defaults for missing keys
        self.unpack_pi_JSON(data)

        #Update GUI elements on seperate thread
        self.content_frame.after(0, self.update_gui_elements, prev_module_status)

    #Update GUI elements
    def update_gui_elements(self, prev_module_status):   
        '''Update GUI elements. Function created to be completed on the main thread'''   

        #Update top and bottom frame parts
        self.status_label.configure(text=f"Module Status: {self.module_status}")
        self.alarm_label.configure(text=f"Alarms: {self.alarm_status}")
        self.sample_label.configure(text=f"Current Sample: {self.curr_sample_id}")

        '''
        if self.module_status == "Scanning Running":
            if self.total_image == 0 :
                self.loading_label.configure(text=f"Running...")
            else:
                self.loading_label.configure(text=f"Taking images: {self.image_count+1}/{self.total_image}")
        '''
        
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

        # Update last refreshed time
        #Used in camera and motor pane
        self.last_refreshed_var.set(f"Last Updated: {datetime.now().strftime('%H:%M:%S')}")

        #Stitching Image Process
        #Change state to start scanning process
        if (self.scanning_state == 0 
            and (self.total_image - 1) == self.image_count
            and self.total_image != 0 
            and self.module_status == "Scanning Running"):

            print("set scanning state to 1")

            self.scanning_state = 1 
        
        #Start transfer folder thread
        if self.scanning_state == 1 and self.total_image == 0:
            print("Starting transfer folder")
            self.transfer_rpi_thread = Thread(target=self.transfer_folder_rpi, kwargs={"destination_path": self.img_scanning_folder, "new_filename": True}, daemon=True)
            self.transfer_rpi_thread.start()
            print("Finished transfer") 
            
            self.scanning_state = 2

        #When folders transfered, calculated x and y grid, empty folder, and start imaging thread
        if self.scanning_state == 2 and not self.transfer_rpi_thread.is_alive() :
            self.scanning_grid_x , self.scanning_grid_y = self.extract_unique_positions(self.img_scanning_folder) 
            self.start_stitching(self.scanning_grid_x, self.scanning_grid_y, self.img_scanning_folder, self.img_scanning_folder, self.curr_sample_id)
            print(" pt3, started stitching thread")
            self.display_scanning_layout(self.scanning_grid_x, self.scanning_grid_y, self.main_right_frame)
            print(" pt4 gui displayed")
            self.empty_folder_rpi()

            self.scanning_state = 3 
        
        #Update button to show stitched image in gui
        if self.scanning_state == 3 and not self.stitching_thread.is_alive() :
            self.complete_image_btn.configure(text="Completed Image Here", state="normal")

            self.scanning_state = 0 #Reset mini state machine
            
        #Random Samping Image Processing
        #Setup f,lag to notify system to download images
        if (self.sampling_state == 0
            and (self.total_image - 1) == self.image_count 
            and self.total_image != 0 
            and self.module_status == "Random Sampling Running") :

            self.sampling_state = 1

            
        #Use state to start thread that transfers folders
        if self.sampling_state == 1 and self.total_image == 0 :
            print("Starting transfer folder rpi")
            self.transfer_rpi_thread = Thread(target=self.transfer_folder_rpi, kwargs={"destination_path": self.img_sampling_folder, "new_filename": False}, daemon=True)
            self.transfer_rpi_thread.start()
            print("Finished transfer rpi")

            self.sampling_state = 2

        #Wait for the trasnfer folder thread to finish to raspberry pi folder
        if self.sampling_state == 2 and not self.transfer_rpi_thread.is_alive():
            self.empty_folder_rpi() 

            self.sampling_state = 0 #Reset mini state machine
        

    #Send sample data
    def send_sample_data(self, mount_type, sample_id, initial_height, layer_height, width, height):
        """Stores sample data, sends it to the Raspberry Pi, and sends command."""

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
        success_message = "Sample data sent."
        self.send_json_error_check(self.sample_data, success_message)
        
        #First sample loaded
        self.sample_loaded = True

    #Send simple command to raspberry pi
    def send_simple_command(self, command, checkIdle):
        '''Send JSON data to raspberry pi to request to run a method
            Used for simple requests e.g. exe_homing_xy'''

        json_data = {
            "command" : command,
            "mode" : self.mode,
            "module_status" : self.module_status
        }

        if self.module_status != "Idle" and checkIdle :
            messagebox.showerror("Status not in idle, wait before sending request.")
        else:
            success_message = "JSON data sent."
            self.send_json_error_check(json_data, success_message)

    #Send random sampling data
    def send_sampling_data(self, num_images):
        '''
        Send random samping data to raspberry pi
        Called when ok is pressed in random sampling pop-up window'''

        if self.module_status == "Idle":
            #Store random sampling data
            self.sampling_data['command'] = "exe_sampling"
            self.sampling_data['mode'] = self.mode
            self.sampling_data['module_status'] = self.module_status
            self.sampling_data['total_image'] = num_images

            #Send random sampling data
            success_message = "Random sampling data sent."
            self.send_json_error_check(self.sampling_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")
    
    #Send scanning data
    def send_scanning_data(self, step_x, step_y):
        '''
        Send scanning data to raspberry pi
        Called when ok is pressed in scanning sampling pop-up window'''

        if self.module_status == "Idle":

            #Check step if valid entry
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
            success_message = "Scanning sampling data sent."
            self.send_json_error_check(self.scanning_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")
    
    #Send camera coniguration data
    def send_camera_data(self, exposure_time, analog_gain, contrast, colour_temp):
        '''Sends updated camera settings to raspberry pi'''
        
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

            #Send scanning data
            success_message = "Updated camera settings data sent."
            self.send_json_error_check(camera_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait before modifying camera settings.")
    
    #Send goto command
    def send_goto_command(self, req_x, req_y, req_z) :
        '''Send goto data and command to rapsberry pi, x y z positions'''

        if self.module_status == "Idle":

            #Check step if valid entry
            if req_x < 0 or req_y < 0 or req_z < 0:
                messagebox.showerror("Invalid input", "Step values must be positive numbers") 
                return   

            #Store scanning sampling data
            goto_data = {
                "command" : "exe_goto",
                "mode" : self.mode,
                "module_status" : self.module_status,
                "req_x_pos" : req_x,
                "req_y_pos" : req_y,
                "req_z_pos" : req_z
            }

            #Send scanning data
            success_message = "Go to data sent."
            self.send_json_error_check(goto_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")


    # =============================== Image Stitching ==========================================#
    
    def set_stitcher(self, stitcher) :
        '''Creates object of stitcher'''

        self.stitcher = stitcher

    def start_stitching(self, grid_x, grid_y, input_dir, output_dir, sample_id) :
        '''Creates thread for stitching'''

        # Using a lambda function to pass the arguments to run_stitching
        self.stitching_thread = Thread(target=lambda: self.stitcher.run_stitching(grid_x, grid_y, input_dir, output_dir, sample_id), daemon=True)
        self.stitching_thread.start()



#To do

#Calibration
#Fill in frame

#Scanning
#Change label to say 5 and 4
#Validation???
#Folder sysem

#Random sampling
#Folder system


#Image tab
#Configure save image
#Configure update image
#Display image
#Configure requestion image and the displaying one
#Folder system

#.bat file

#Close sockets on raspberry pi on gui closing


'''
import os

# Create a single folder (will raise error if it exists)
os.mkdir("my_folder")

# Create nested folders safely (does not raise error if it exists)
os.makedirs("parent_folder/child_folder", exist_ok=True)
'''