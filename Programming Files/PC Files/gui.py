import customtkinter as ctk
from tkinter import filedialog, messagebox, font
from PIL import Image, ImageTk
from datetime import datetime
import numpy as np
import os

from communication import CommunicationHandler


class MainApp(ctk.CTk):
    def __init__(self):
    #====================================================================================#
    #----------------------------- Variables and Instantiation -------------------------#
    #====================================================================================#
        super().__init__()

        #---------- Raspberry Pi JSON Keys instatiate ----------#
        #Module states and data
        self.module_status = "Unknown"
        self.alarm_status = "Uknown"
        self.mode = "Manual"

        #Motion data
        self.motors_enabled : False
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
        self.current_image = []
        self.image_metadata = {}

        #------ JSON Objects sent TO rapsberry pi ------#
        #Sample data
        self.sample_data = {
            "mount_type" : "Unknown",
            "sample_height" : 0.0,
            "initial_height" : 0.0,
            "sample_id" : "Unknown"
        }

        #Random sampling method json data
        self.sampling_data = {
            "command" :"Uknown",
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

        #Not related JSON data
        self.sample_loaded = False

        #--------------------- GUI Appearance Variables ---------------------------#
        #Skeleton appearance
        self.title("Control Panel")
        self.geometry("800x600")
        self.minsize(800, 550)  # Set the minimum width and height
        ctk.set_appearance_mode("dark")  # Options: "dark", "light", "system"

        #Image related info from pi
        self.image_folder = "C:/Users/Steph/OneDrive - UBC/4th Year/MANU 430/Programming/Test Pictures"

        # Top & Bottom Frames
        self.create_top_frame()
        self.create_bottom_frame()

        # Content Frame
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(expand=True, fill='both')

        self.display_main_tab()

    #====================================================================================#
    #----------------------------- GUI Appearances and Main app -------------------------#
    #====================================================================================#

    #------------------- Add Buttons -----------------#
    #Add a button to GUI
    def add_button(self, frame, name, text, command=None, *args, **kwargs):
        """Helper function to create buttons and add them to the dictionary."""
        button = ctk.CTkButton(frame, text=text, font=("Arial", 20), width=200, 
                               height=100, command=lambda: command(*args) if command else None, **kwargs)
        button.pack(pady=5, fill='x')

        #Add buttons to dictionary for enabling and disabling
        self.buttons[name] = button

    # ------------------ Top Frame ------------------ #
    def create_top_frame(self):
        top_frame = ctk.CTkFrame(self)
 
        #Space between the edge and the frame
        top_frame.pack(side=ctk.TOP, fill='x', padx=10, pady=5)
 
        self.status_label = ctk.CTkLabel(top_frame, text=f"Module Status: {self.module_status}")
        self.status_label.pack(side=ctk.LEFT, padx=10)

        self.mode_label = ctk.CTkLabel(top_frame, text=f"Mode: {self.mode}")
        self.mode_label.pack(side=ctk.LEFT, padx=30)

        self.sample_label = ctk.CTkLabel(top_frame, text=f"Current Sample: {self.sample_data['sample_id']}")
        self.sample_label.pack(side=ctk.LEFT, padx=80)

        self.alarm_label = ctk.CTkLabel(top_frame, text=f"Alarms: {self.alarm_status}")
        self.alarm_label.pack(side=ctk.RIGHT, padx=10)

    # ------------------ Bottom Frame (Tabs) ------------------ #
    def create_bottom_frame(self):
        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(side=ctk.BOTTOM, fill='x', padx=10, pady=5)

        tabs = ["Main", "Motion", "Image", "Details"]
        for tab in tabs:
            tab_btn = ctk.CTkButton(bottom_frame, text=tab, font=("Arial", 20), command=lambda t=tab: self.switch_tab(t))
            tab_btn.pack(side=ctk.LEFT, padx=5)

        self.date_time_label = ctk.CTkLabel(bottom_frame, text="", font = ("Arial", 14))
        self.date_time_label.pack(side=ctk.RIGHT, padx=5)
        self.update_time()

    # ------------------ Tab Navigation ------------------ #
    def switch_tab(self, tab_name):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        if tab_name == "Main":
            self.display_main_tab()
        elif tab_name == "Motion":
            self.display_motion_tab()
        elif tab_name == "Image":
            self.display_image_tab()

    # ------------------ Main Tab Buttons ------------------ #
    def display_main_tab(self):
        """Displays the Scanning layout with a large image grid."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        """Displays the Scanning layout with a large image grid."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        #Setup frame padding on left and right
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)

        right_frame = ctk.CTkFrame(self.content_frame, width=400, height=400)
        right_frame.pack(side=ctk.RIGHT, expand=True, fill='both')


        # Image Display on Right
        self.display_placeholder_image(right_frame)

        # Buttons on Left Side
        create_sample_btn = ctk.CTkButton(left_frame, text = "Create a new sample", font = ("Arial", 20), 
                                          width = 200, height = 100, fg_color = "green", command = lambda: self.open_sample_dialog())
        sampling_btn = ctk.CTkButton(left_frame, text="Random Sampling", font=("Arial", 20), width = 200, height = 100, command = lambda: self.open_sampling_dialog(right_frame))
        #sampling_btn = ctk.CTkButton(left_frame, text="Random Sampling", font=("Arial", 20), width = 200, height = 100, command = lambda: self.display_random_sampling_layout(8, right_frame))
        scanning_btn = ctk.CTkButton(left_frame, text="Scanning", font=("Arial", 20), 
                                        width = 200, height = 100, command = lambda: self.display_scanning_layout(7,6,right_frame))

        create_sample_btn.pack(pady=5, fill='x')
        sampling_btn.pack(pady=5, fill='x')
        scanning_btn.pack(pady=5, fill='x')

        calibration_btn = ctk.CTkButton(left_frame, width = 200, height = 50, text="Calibration", font=("Arial", 20))
        calibration_btn.pack(pady=5, fill='x')

        home_btn = ctk.CTkButton(left_frame, text="Homing", width = 200, height = 50, font=("Arial", 20), fg_color="blue", text_color="white")
        home_btn.pack(pady=5, fill='x')
    

    # ------------------ Image Placeholder ------------------ #
    def display_placeholder_image(self, frame):
        img = Image.open("C:/Users/Steph/OneDrive - UBC/4th Year/MANU 430/Programming/Test Pictures/dog.jpg")  # Replace with your image path
        img = img.resize((2169, 1651), Image.LANCZOS)
        tilt_img = img.rotate(-1)

        # Create a CTkImage instance
        img_ctk = ctk.CTkImage(tilt_img, size=(800, 600))

        # Create the CTkLabel and display the CTkImage
        img_label = ctk.CTkLabel(frame, image=img_ctk, text="")
        img_label.image = img_ctk  # Keep reference to the image

        # Center the image within the frame using place() method
        img_label.place(relx=0.5, rely=0.5, anchor="center")  # This centers the image in the frame

#-----------------------Random Sampling Pop-up ---------------- #
    def open_sampling_dialog(self, frame):
        # Window setup
        image_sample_window = ctk.CTkToplevel(self)
        image_sample_window.title("Enter Sampling Parameters")
        image_sample_window.geometry("350x135")  # Set initial size
        image_sample_window.minsize(350, 135)   # Limit the minimum size
        image_sample_window.maxsize(350, 135)   # Limit the maximum size

        image_sample_window.grab_set()

        # New prompt text
        label = ctk.CTkLabel(image_sample_window, text="Enter in the number of images taken for random sampling:")
        label.grid(row=0, column=0, columnspan=4, padx=5, pady=10, sticky="ew")

        # Total images input field
        ctk.CTkLabel(image_sample_window, text="Total Images:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        total_images = ctk.CTkEntry(image_sample_window, placeholder_text="6")
        total_images.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # OK button (closes the window and processes input)
        ok_button = ctk.CTkButton(image_sample_window, text="OK", 
                                  command=lambda: [image_sample_window.destroy(), self.display_random_sampling_layout(total_images, frame), self.send_sampling_data(total_images)], width=80)
        ok_button.grid(row=2, column=0, padx=5, pady=10, sticky="ew")

        # Cancel button (closes the window)
        cancel_button = ctk.CTkButton(image_sample_window, text="Cancel", command=image_sample_window.destroy, width=80)
        cancel_button.grid(row=2, column=3, columnspan=2, padx=5, pady=10, sticky="ew")

        # Ensure the buttons are always at the bottom of the window
        image_sample_window.grid_rowconfigure(3, weight=1)  # Add this line to allow the window to expand as needed
        image_sample_window.grid_rowconfigure(2, weight=0)  # Ensure row 2 (buttons) stays at the bottom

        # Simple validation function
        def validate_input(*args):
            try:
                value = int(total_images.get())
                # Check if value is between 1 and 8
                if 1 <= value <= 8:
                    ok_button.configure(state="normal")  # Enable OK button
                else:
                    ok_button.configure(state="disabled")  # Disable OK button
            except ValueError:
                ok_button.configure(state="disabled")  # Disable OK button if input is not a number

        # Trace the input changes and call validate_input
        total_images.bind("<KeyRelease>", validate_input)

# ------------------ Sample Parameter Dialog ------------------ #
    def open_sample_dialog(self):
        #Window setup
        sample_window = ctk.CTkToplevel(self)
        sample_window.title("Enter Sample Parameters")
        sample_window.geometry("320x390")
        sample_window.minsize(320, 350)
        sample_window.maxsize(320, 350)

        sample_window.grab_set()

        #Mount type (ie puck, stub), drop down
        ctk.CTkLabel(sample_window, text="Select your mount type:").grid(row = 0, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        mount_type = ctk.CTkComboBox(sample_window, values=["Puck", "Stub"])
        mount_type.grid(row = 1, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #Sample height
        ctk.CTkLabel(sample_window, text="Enter starting sample height:").grid(row = 2, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        sample_height = ctk.CTkEntry(sample_window, placeholder_text = "20")
        sample_height.grid(row = 3, column = 1, columnspan = 2, padx=1, pady=1, sticky="ew")

        #Sample layer height
        ctk.CTkLabel(sample_window, text="Enter sample layer height:").grid(row = 4, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        ctk.CTkLabel(sample_window, text="(i.e. Amount of material removed each layer):").grid(row = 5, column = 0, columnspan = 4, pady=1, sticky = "ew")
        layer_height = ctk.CTkEntry(sample_window)
        layer_height. grid(row = 6, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #------Bounding box -----
        #Width
        ctk.CTkLabel(sample_window, text="Enter bounding box size:").grid(row = 7, column = 0, columnspan = 4, padx=5, pady=1, sticky="ew")
        ctk.CTkLabel(sample_window, text="Width:").grid(row=8, column=0, padx=1, pady=1, sticky = "e")
        sample_width = ctk.CTkEntry(sample_window, width = 50)
        sample_width.grid(row = 8, column = 1, padx=5, pady=5, sticky = "w")

        #Length
        ctk.CTkLabel(sample_window, text="Length:").grid(row=8, column=2, padx=5, pady=5, sticky = "e")
        sample_length = ctk.CTkEntry(sample_window, width = 50)
        sample_length.grid(row = 8, column = 3, padx=5, pady=10, sticky = "w")

        #Ok button
        #Closes the window and calls function send_sampleData() on ok
        ok_button = ctk.CTkButton(sample_window, text="OK", command=lambda: [sample_window.destroy(), self.send_sampleData], width = 80)
        ok_button.grid(row = 9, column = 0, padx=5, pady=5)

        #Cancel button, closes window
        ctk.CTkButton(sample_window, text="Cancel", command=sample_window.destroy, width = 80).grid(row = 9, column = 3,columnspan = 2, padx=5, pady=5)

    # ------------------ Motion Tab ------------------ #
    def display_motion_tab(self):
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)

        right_frame = ctk.CTkFrame(self.content_frame)
        right_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)

        ctk.CTkButton(left_frame, text="Go To", font=("Arial", 20)).grid(row=0, column=0, columnspan = 3, padx=5, pady=5, sticky="ew")

        # Position Controls
        self.create_position_control(left_frame, "X", self.x_pos, row=1)
        self.create_position_control(left_frame, "Y", self.y_pos, row=2)
        self.create_position_control(left_frame, "Z", self.z_pos, row=3)

        # Additional Controls
        ctk.CTkButton(left_frame, text="Disable Stepper Motors").grid(row=7, column=0, columnspan = 3, padx=5, pady=5, sticky='ew')
        ctk.CTkButton(left_frame, text="Homing", fg_color="green").grid(row=8, column=0, columnspan = 3, padx=5, pady=5, sticky='ew')
        ctk.CTkButton(left_frame, text="Calibration").grid(row=9, column=0, columnspan = 3, padx=5, pady=5, sticky='ew')

        # Graph Display
        self.create_graphs(right_frame)

        ctk.CTkButton(right_frame, text="STOP", fg_color="red").pack(padx=10, pady=5)
        ctk.CTkButton(right_frame, text="Finish").pack(padx=50, pady=5)


    # ------------------ Position Control ------------------ #
    def create_position_control(self, parent, label, value, row):
        ctk.CTkLabel(parent, text=f"{label} Position:",font=("Arial", 18)).grid(row=row, column=0, padx=5, pady=2, sticky='w')
        entry = ctk.CTkEntry(parent, width=30)
        entry.insert(0, str(value))
        entry.grid(row=row, column=2, padx=3, pady=2)
        self.create_step_buttons(parent, entry, row=row)

        entry.grid(row=row, column=2, padx=3, pady=2)
        self.create_step_buttons(parent, entry, row=row)

    # ------------------ Step Adjustment Buttons ------------------ #
    def create_step_buttons(self, parent, entry_widget, step=1, row=0):
        btn_frame = ctk.CTkFrame(parent)
        btn_frame.grid(row=row, column=1, padx=5, pady=2)

        ctk.CTkButton(btn_frame, text="▲", width=30, command=lambda: self.adjust_value(entry_widget, step)).grid(row=0, column=0, padx=2)
        ctk.CTkButton(btn_frame, text="▼", width=30, command=lambda: self.adjust_value(entry_widget, -step)).grid(row=0, column=1, padx=2)
        btn_frame.grid(row=row, column=1, padx=5, pady=2)

        ctk.CTkButton(btn_frame, text="▲", width=30, command=lambda: self.adjust_value(entry_widget, step)).grid(row=0, column=0, padx=2)
        ctk.CTkButton(btn_frame, text="▼", width=30, command=lambda: self.adjust_value(entry_widget, -step)).grid(row=0, column=1, padx=2)
    
    def adjust_value(self, entry, step):
        try:
            current_value = int(entry.get())
            entry.delete(0, ctk.END)
            entry.insert(0, str(current_value + step))
        except ValueError:
            entry.delete(0, ctk.END)
            entry.insert(0, "0")

    # ------------------ Graphs ------------------ #
    def create_graphs(self, parent):
    
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

    # ------------------ Time Updater ------------------ #
    def update_time(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.date_time_label.configure(text=now)
        self.after(1000, self.update_time)

      # ------------------ Image Tab ------------------ #
    def display_image_tab(self):
        """Displays the Image tab layout with entry boxes on the left and image display on the right."""

        # Clear previous content in the content frame
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # Setup left and right frames
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)

        right_frame = ctk.CTkFrame(self.content_frame)
        right_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)

        # Left Frame: Entry Boxes and Buttons
        # Exposure Time (microsec)
        exposure_time_label = ctk.CTkLabel(left_frame, text="Exposure Time (microsec):")
        exposure_time_label.pack(pady=5, anchor='w')
        self.exposure_time_entry = ctk.CTkEntry(left_frame)
        self.exposure_time_entry.pack(pady=5, fill='x')

        # Analog Gain (1=no gain)
        analog_gain_label = ctk.CTkLabel(left_frame, text="Analog Gain (1=no gain):")
        analog_gain_label.pack(pady=5, anchor='w')
        self.analog_gain_entry = ctk.CTkEntry(left_frame)
        self.analog_gain_entry.pack(pady=5, fill='x')

        # Contrast (0-32, 1=no value)
        contrast_label = ctk.CTkLabel(left_frame, text="Contrast (0-32, 1=no value):")
        contrast_label.pack(pady=5, anchor='w')
        self.contrast_entry = ctk.CTkEntry(left_frame)
        self.contrast_entry.pack(pady=5, fill='x')

        # Colour Temperature (K)
        colour_temp_label = ctk.CTkLabel(left_frame, text="Colour Temperature (K):")
        colour_temp_label.pack(pady=5, anchor='w')
        self.colour_temp_entry = ctk.CTkEntry(left_frame)
        self.colour_temp_entry.pack(pady=5, fill='x')

        # Buttons below entry boxes
        button_frame = ctk.CTkFrame(left_frame)
        button_frame.pack(pady=10, fill='x')

        update_image_btn = ctk.CTkButton(button_frame, text="Update Image", font=("Arial", 16), command=self.update_image)
        update_image_btn.pack(side="left", padx=10, fill='x', expand=True)

        save_image_btn = ctk.CTkButton(button_frame, text="Save Image", font=("Arial", 16), command=self.save_image)
        save_image_btn.pack(side="right", padx=10, fill='x', expand=True)

        # Right Frame: Image Display
        image_label = ctk.CTkLabel(right_frame, text="Image will appear here", fg_color="gray")
        image_label.pack(expand=True, fill='both')

    # ------------------ Displaying Scanning Layout ------------------ #
    def display_scanning_layout(self, images_x, images_y, frame):
        """Displays the Scanning layout with a large image grid."""
        for widget in frame.winfo_children():
            widget.destroy()
    
        scanning_frame = ctk.CTkFrame(frame)
        scanning_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)

        self.scan_image_grid = []  # Store references to image labels

        img = Image.open("C:/Users/Steph/OneDrive - UBC/4th Year/MANU 430/Programming/Test Pictures/dog.jpg")  # Replace with your image path
        img = img.resize((50, 50), Image.LANCZOS)

        # Create a CTkImage instance
        img_ctk = ctk.CTkImage(img, size=(50, 50))

        # Create dynamic grid based on `images_x` and `images_y`
        for row in range(images_y):
            for col in range(images_x):
                img_placeholder = ctk.CTkLabel(scanning_frame, text="", image = img_ctk)
                img_placeholder.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
                img_placeholder.bind("<Button-1>", lambda e, img=img_placeholder: self.expand_image(img))
                self.scan_image_grid.append(img_placeholder)

        # STOP and Finish buttons
         # Ensure button frame always appears, even if no images are loaded
        button_frame = ctk.CTkFrame(scanning_frame)
        button_frame.grid(row=images_y, column=images_x/2, columnspan=images_x, pady=15, sticky='ew')

        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red")
        stop_button.grid(row=0, column=0, padx=5, pady=5, sticky='ew')

        finish_button = ctk.CTkButton(button_frame, text="Finish", command=self.display_main_tab)
        finish_button.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

    def load_images_from_folder(self, folder):
        """Load image file paths from the specified folder."""
        return [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(('png', 'jpg', 'jpeg', 'gif'))]

    def display_random_sampling_layout(self, num_images, frame):
        """Displays an evenly distributed grid layout for images, handling missing images gracefully."""
        
        # Clear previous content
        for widget in frame.winfo_children():
            widget.destroy()

        # Create a new frame
        sampling_frame = ctk.CTkFrame(frame)
        sampling_frame.pack(expand=True, fill='both', padx=10, pady=10)

        # Load available images
        images = self.load_images_from_folder(self.testing_pictures)
        available_images = len(images)

        # Adjust num_images to the available images count
        num_images = min(num_images, available_images)  # Prevents out-of-range errors

        self.image_labels = []  # Store image labels for reference

        # Calculate row distribution
        first_row_count = (num_images + 1) // 2  # First row gets one extra if odd
        second_row_count = num_images // 2

        # Determine the maximum number of columns
        total_columns = max(first_row_count, second_row_count)

        #Scaling the image size depending on the number of images
        img_size = 200

        # Configure grid to center images
        for col in range(total_columns):
            sampling_frame.grid_columnconfigure(col, weight=1)  # Make columns expand evenly

        sampling_frame.grid_rowconfigure(0, weight=1)  # Ensure images are centered
        sampling_frame.grid_rowconfigure(1, weight=1)
        sampling_frame.grid_rowconfigure(2, weight=0)  # Ensure buttons stay at bottom

        # Display first row (only if images exist)
        for col in range(first_row_count):
            if col >= available_images:  # Prevent index error
                break
            img = Image.open(images[col])
            img = img.resize((img_size, img_size), Image.LANCZOS)
            img_ctk = ctk.CTkImage(img, size=(img_size, img_size))

            img_label = ctk.CTkLabel(sampling_frame, image=img_ctk, text="")
            img_label.grid(row=0, column=col, padx=10, pady=10, sticky='nsew')

            img_label.bind("<Button-1>", lambda e, img_path=images[col]: self.expand_image(img_path))
            self.image_labels.append(img_label)

        # Display second row (only if images exist)
        for col in range(second_row_count):
            image_index = first_row_count + col
            if image_index >= available_images:  # Prevent index error
                break
            img = Image.open(images[image_index])
            img = img.resize((img_size, img_size), Image.LANCZOS)
            img_ctk = ctk.CTkImage(img, size=(img_size, img_size))

            img_label = ctk.CTkLabel(sampling_frame, image=img_ctk, text="")
            img_label.grid(row=1, column=col, padx=10, pady=10, sticky='nsew')

            img_label.bind("<Button-1>", lambda e, img_path=images[image_index]: self.expand_image(img_path))
            self.image_labels.append(img_label)

        # Ensure button frame always appears, even if no images are loaded
        button_frame = ctk.CTkFrame(sampling_frame)
        button_frame.grid(row=2, column=0, columnspan=total_columns, pady=15, sticky='ew')

        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red")
        stop_button.grid(row=0, column=0, padx=5, pady=5, sticky='ew')

        finish_button = ctk.CTkButton(button_frame, text="Finish", command=self.display_main_tab)
        finish_button.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        # Call the update function every 5 seconds to check for changes in the folder
        self.master.after(5000, self.check_for_new_images)

    def check_for_new_images(self):
        """Check for new images in the folder and update the layout."""
        images = self.load_images_from_folder(self.testing_pictures)
        available_images = len(images)

        if available_images != len(self.image_labels):
            self.display_random_sampling_layout()  # Re-display layout with updated images

        # Schedule the next check in 5 seconds
        self.master.after(5000, self.check_for_new_images)

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
    
    #------------------- Disable Buttons Function ----------------------#
    #Enable and disable buttons based on status
    def disable_buttons(self, module_status, sample_data_loaded):
        
        #Set everything to disabled, and empty enable
        buttons_to_disable = []
        buttons_to_disable = list(self.buttons.keys())  # All button names
        buttons_to_enable = []

        # Based on the status, decide which buttons to disable/enable
        if module_status == "Idle":
            buttons_to_enable = list(self.buttons.keys())  # All buttons

            #Scanning and sampling disabled if sample data hasn't been loaded yet
            if not sample_data_loaded:
                buttons_to_disable = ["scanning", "sampling", "stop_btn"]
            else:
                buttons_to_disable = ["stop_btn"]

        elif module_status == "Scanning" or module_status == "Sampling" or module_status == "Stopping":
            buttons_to_enable = ["main_tab", "motion_tab", "details_tab", "image_tab", "stop_btn"]

        elif module_status == "Calibrating":
            buttons_to_enable = ["main_tab", "motion_tab", "details_tab", "image_tab", "stop_btn", "load_sample_btn"]

        # Enable or disable buttons based on their names
        for name in self.buttons:
            if name in buttons_to_enable:
                self.buttons[name].configure(state=ctk.NORMAL)
            else:
                self.buttons[name].configure(state=ctk.DISABLED)


    #============================== Communcation ====================================#
    
    #Assign communication handler from main.py
    def set_communication(self, comms, stop_event):
        self.comms = comms
        self.stop_event = stop_event 
    
     #Send JSON file to raspberry pi, and handle errors
    def send_json_error_check(self, data, success_message):
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

    #Get all the data from the JSON file
    #From raspberry pi publisher
    def unpack_pi_JSON(self, data):
        # Extract values from the received data dictionary, with defaults for missing keys
        self.module_status = data.get("module_status", "Unknown")
        self.mode = data.get("mode", "Unknown")
        self.alarm_status = data.get("alarm_status", "Unknown")

        self.motors_enabled = data.get("motors_enabled", "Unknown")
        self.x_pos = data.get("x_pos", 0)
        self.y_pos = data.get("y_pos", 0)
        self.z_pos = data.get("z_pos", 0)

        self.exposure_time = data.get("exposure_time", 0)
        self.analog_gain = data.get("analog_gain", 0)
        self.contrast = data.get("contrast", 0)
        self.colour_temp = data.get("colour_temp", 0)

        self.total_image = data.get("total_image", 0)
        self.image_count = data.get("image_count", 0)
        self.current_image = data.get("current_image", [])
        self.image_metadata = data.get("image_metadata", {})

    #Unpack and update data from raspberry pi
    #Function is called in communication.py in the receive status updates
    def update_status_data(self, data):
        #Store previous status before update
        prev_module_status = self.module_status
        prev_image_count = self.image_count

        # Extract values from the received data dictionary, with defaults for missing keys
        self.unpack_pi_JSON(data)

        # Update all GUI elements
        self.status_label.configure(text=f"Module Status: {self.module_status}")
        self.alarm_label.configure(text=f"Alarms: {self.alarm_status}")

        #Update buttons only during status changes
        if prev_module_status != self.module_status :
            self.disable_buttons(self.module_status, self.sample_loaded)
        
        if prev_image_count != self.image_count :
            #Update images
            return

    #Function sends sample_data to raspberry pi
    #This function is called in function store_sample_data when the ok button is pressed
    def send_sample_data(self, mount_type, sample_height, initial_height, sample_id):
        """Stores sample data, sends it to the Raspberry Pi, and sends mode request."""
        # Store the sample data
        self.sample_data['mount_type'] = mount_type
        self.sample_data['sample_height'] = sample_height
        self.sample_data['initial_height'] = initial_height
        self.sample_data['sample_id'] = sample_id

        #Send sample data
        success_message = "Sample data sent."
        self.send_json_error_check(self.sample_data, success_message)

    #Send JSON data to raspberry pi to request to run a method
    #Use for simple requests: Homing_xy, update_image etc.
    def send_simple_command(self, command):
        json_data = {
            "command" : command,
            "mode" : self.mode,
            "module_status" : self.module_status
        }

        success_message = "JSON data sent."
        self.send_json_error_check(json_data, success_message)

    #Send random samping data to raspberry pi
    #Called when ok is pressed in random sampling pop-up window
    def send_sampling_data(self, num_images):
        if self.module_status == "Idle":
            #Store random sampling data
            self.sampling_data['command'] = "exe_sampling"
            self.sampling_data['mode'] = self.mode
            self.sampling_data['module_status'] = self.module_status
            self.sampling_data['num_images'] = num_images

            #Send random sampling data
            success_message = "Random sampling data sent."
            self.send_json_error_check(self.sampling_data, success_message)

            self.sample_loaded = True
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")
    
    #Send scanning data to raspberry pi
    #Called when ok is pressed in scanning sampling pop-up window
    def send_scanning_data(self, step_x, step_y):
        if self.module_status == "Idle":

            #Check step if valid entry
            if step_x <= 0 or step_y <= 0:
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

    # =============================== Image Stitching ==========================================#
    def set_stitcher(self, stitcher) :
        self.stitcher = stitcher


#To do
# populate labels with data (e.g. temperature, speed)
# Implement button names and addButton function
# Populate images as they come in

#Image tab

#Image stitching: calling it, threading, transferring files