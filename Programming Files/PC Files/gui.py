import customtkinter as ctk
from tkinter import filedialog, messagebox, font
from PIL import Image, ImageTk
from datetime import datetime
import numpy as np
import numpy as np
import os

from communication import CommunicationHandler


class MainApp(ctk.CTk):
    #============================ Appearance =================================================#
    def __init__(self):
        super().__init__()

        #---------- Raspberry Pi JSON Keys instatiate ----------#
        #Module states and data
        self.status = "Unknown"
        self.mode = "Manual"
        self.alarm_status = "Uknown"

        #Motion data
        self.speed = 0
        self.motor_A = False
        self.motor_B = False
        self.motor_Z = False
        self.current_pos_x = 0
        self.current_pos_y = 0
        self.current_pos_z = 0

        #Camera and image data
        self.total_image = 0
        self.current_image = 0
        self.image_json = {}
        self.file_location = "Uknown"
        self.brightness = "Unknown"
        self.contrast = "Unknown"

        #------ JSON Objects sent TO rapsberry pi ------
        #Sample data
        self.sample_data = {
            "mount_type" : "Unknown",
            "sample_height" : 0.0,
            "initial_height" : 0.0,
            "sample_id" : "Unknown"
        }

        #Random sampling method
        self.random_data = {
            "mode" : "Unknown",
            "status" : "Unknown",
            "num_images" : 0
        }

        #Scanning sampling method
        self.scanning_data = {
            "mode" : "Unknown",
            "status" : "Unknown",
            "step_x" : 0,
            "step_y" :0
        }

        #--------------------- GUI Instantiation ---------------------------#
        #Skeleton appearance
        self.title("Control Panel")
        self.geometry("800x500")
        self.minsize(800, 550)  # Set the minimum width and height
        ctk.set_appearance_mode("dark")  # Options: "dark", "light", "system"

        #Image related info from pi
        self.image_folder = "default_directory"

        # Top & Bottom Frames
        self.create_top_frame()
        self.create_bottom_frame()

        # Content Frame
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(expand=True, fill='both')

        self.display_main_tab()


    # ------------------ Top Frame ------------------ #
    def create_top_frame(self):
        top_frame = ctk.CTkFrame(self)

        #Space between the edge and the frame
        top_frame.pack(side=ctk.TOP, fill='x', padx=10, pady=5)

        self.status_label = ctk.CTkLabel(top_frame, text=f"Module Status: {self.status}")
        self.status_label.pack(side=ctk.LEFT, padx=10)

        self.date_time_label = ctk.CTkLabel(top_frame, text="")
        self.date_time_label.pack(side=ctk.RIGHT, padx=10)
        self.update_time()

    # ------------------ Bottom Frame (Tabs) ------------------ #
    def create_bottom_frame(self):
        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(side=ctk.BOTTOM, fill='x', padx=10, pady=5)

        tabs = ["Main", "Motion", "Image", "Details"]
        for tab in tabs:
            tab_btn = ctk.CTkButton(bottom_frame, text=tab, font=("Arial", 20), command=lambda t=tab: self.switch_tab(t))
            tab_btn.pack(side=ctk.LEFT, padx=5)

        self.alarm_label = ctk.CTkLabel(bottom_frame, text=f"Alarms: {self.alarm_status}")
        self.alarm_label.pack(side=ctk.LEFT, padx=20)

    # ------------------ Tab Navigation ------------------ #
    def switch_tab(self, tab_name):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        if tab_name == "Main":
            self.display_main_tab()
        elif tab_name == "Motion":
            self.display_motion_tab()

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
        #Random sampling and Scanning buttons open dialog
        sampling_btn = ctk.CTkButton(left_frame, text="Random Sampling", font=("Arial", 20), width = 200, height = 100, command=lambda: self.open_sample_dialog("Random Sampling"))
        scanning_btn = ctk.CTkButton(left_frame, text="Scanning", font=("Arial", 20), width = 200, height = 100, command=lambda: self.open_sample_dialog("Scanning"))

        sampling_btn.pack(pady=5, fill='x') #Sampling spacing
        scanning_btn.pack(pady=5, fill='x') #Scanning spacing

        calibration_btn = ctk.CTkButton(left_frame, width = 200, height = 100, text="Calibration", font=("Arial", 20))
        calibration_btn.pack(pady=5, fill='x')

        home_btn = ctk.CTkButton(left_frame, text="Homing", width = 200, height = 100, font=("Arial", 20), fg_color="green", text_color="white")

        home_btn = ctk.CTkButton(left_frame, text="Homing", width = 200, height = 100, font=("Arial", 20), fg_color="green", text_color="white")
        home_btn.pack(pady=5, fill='x')
    

    # ------------------ Image Placeholder ------------------ #
    def display_placeholder_image(self, frame):
        img = Image.open("C:/Users/a4iri/Desktop/Capstone/Test image.png")  # Replace with your image path
        img = img.resize((350, 350), Image.LANCZOS)


        # Create a CTkImage instance
        img_ctk = ctk.CTkImage(img, size=(350, 350))

        # Create the CTkLabel and display the CTkImage
        img_label = ctk.CTkLabel(frame, image=img_ctk, text="")
        img_label.pack(expand=True)


# ------------------ Sample Parameter Dialog ------------------ #
    def open_sample_dialog(self, mode):
        """Displays sample dialog and switches layout based on user choice."""

        #Window setup
        sample_window = ctk.CTkToplevel(self)
        sample_window.title(f"{mode} Parameters")
        sample_window.geometry("330x360")
        sample_window.minsize(330, 360)
        sample_window.maxsize(330, 360)

        sample_window.grab_set()

        #Mount type (ie puck, stub), drop down
        ctk.CTkLabel(sample_window, text="Select your mount type:").grid(row = 0, column = 0, columnspan = 4, padx=1, pady=5)
        mount_type = ctk.CTkComboBox(sample_window, values=["Puck", "Stub"])
        mount_type.grid(row = 1, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #Sample height 
        ctk.CTkLabel(sample_window, text="Enter sample height:").grid(row = 2, column = 0, columnspan = 4, padx=1, pady=5)
        sample_height = ctk.CTkEntry(sample_window)
        sample_height.grid(row = 3, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")
        sample_height.grid(row = 3, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #------Bounding box -----
        #Width
        ctk.CTkLabel(sample_window, text="Enter bounding box size:").grid(row = 4, column = 0, columnspan = 4, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(sample_window, text="Width:").grid(row=5, column=0, padx=1, pady=5, sticky = "e")
        sample_width = ctk.CTkEntry(sample_window, width = 50)
        sample_width.grid(row = 5, column = 1, padx=5, pady=5, sticky = "w")

        #Height
        ctk.CTkLabel(sample_window, text="Length:").grid(row=5, column=2, padx=5, pady=5, sticky = "e")
        sample_length = ctk.CTkEntry(sample_window, width = 50)
        sample_length.grid(row = 5, column = 3, padx=5, pady=10, sticky = "w")

        #Sample 2 check box
        def toggleEntry():
            if sample_2_var.get():
                sample_height_2.configure(state='normal')
            if sample_2_var.get():
                sample_height_2.configure(state='normal')
            else:
                sample_height_2.configure(state='disabled')

                sample_height_2.configure(state='disabled')

        sample_2_var = ctk.BooleanVar()
        sample_2_check = ctk.CTkCheckBox(sample_window, text="Sample 2", variable=sample_2_var, command=toggleEntry)
        sample_2_check.grid(row = 6, column = 0, columnspan = 4, padx=5, pady=10)

        #Sample 2 height
        sample_height_2 = ctk.CTkEntry(sample_window, state='disabled')
        sample_height_2.grid(row = 7, column = 1, columnspan = 2, padx=5, pady=5)

        #Function when ok pressed
        #Closes window and opens correct frame
        def ok_sampleDialog():
            sample_window.destroy()

            # Switch layout based on mode
            if mode == "Random Sampling":
                self.display_random_sampling_layout()
            elif mode == "Scanning":
                self.display_scanning_layout(images_x=4, images_y=3)

        #Ok button
        #Calls ok_sampleDialog() function and send_sampleData()
        ok_button = ctk.CTkButton(sample_window, text="OK", command=lambda: [ok_sampleDialog, self.send_sampleData], width = 80)
        ok_button.grid(row = 8, column = 0, padx=5, pady=5)

        #Cancel button, closes window
        ctk.CTkButton(sample_window, text="Cancel", command=sample_window.destroy, width = 80).grid(row = 8, column = 3,columnspan = 2, padx=5, pady=5)


    # ------------------ Motion Tab ------------------ #
    def display_motion_tab(self):
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)


        right_frame = ctk.CTkFrame(self.content_frame)
        right_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)

        ctk.CTkButton(left_frame, text="Go To", font=("Arial", 20)).grid(row=0, column=0, columnspan = 3, padx=5, pady=5, sticky="ew")

        # Position Controls
        self.create_position_control(left_frame, "X", self.current_x_pos, row=1)
        self.create_position_control(left_frame, "Y", self.current_y_pos, row=2)
        self.create_position_control(left_frame, "Z", self.current_z_pos, row=3)

        # Speed Display
        self.speed_label = ctk.CTkLabel(left_frame, text=f"Speed: {self.speed}")
        self.speed_label.pack(font=("Arial", 18)).grid(row=4, column=0, padx=5, pady=30, sticky='w')

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
        # Placeholder for X-Y Graph
        xy_graph = ctk.CTkFrame(parent, width=300, height=300, fg_color="blue")
        xy_graph.pack(padx=5, pady=5)


        # Placeholder for Z-Axis Graph
        z_graph = ctk.CTkFrame(parent, width=300, height=50, fg_color="blue")
        z_graph.pack(padx=5, pady=5)


        # Red Position Indicators (Mock)
        ctk.CTkLabel(xy_graph, text = "       ", fg_color="red").place(relx=self.current_x_pos*0.001, 
                                                                    rely=self.current_y_pos*0.001, anchor='center')
        ctk.CTkLabel(z_graph, text = "   ", fg_color="red").place(relx=0.5, rely=0.5, anchor='center')

    # ------------------ Time Updater ------------------ #
    def update_time(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.date_time_label.configure(text=now)
        self.after(1000, self.update_time)

    # ------------------ Displaying Scanning Layout ------------------ #
    def display_scanning_layout(self, images_x=4, images_y=3):
        """Displays the Scanning layout with a large image grid."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
        scanning_frame = ctk.CTkFrame(self.content_frame)
        scanning_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)

        self.scan_image_grid = []  # Store references to image labels

        img = Image.open("C:/Users/a4iri/Desktop/Capstone/Test image.png")  # Replace with your image path
        img = img.resize((350, 350), Image.LANCZOS)

        # Create a CTkImage instance
        img_ctk = ctk.CTkImage(img, size=(350, 350))

        # Create dynamic grid based on `images_x` and `images_y`
        for row in range(images_y):
            for col in range(images_x):
                img_placeholder = ctk.CTkLabel(scanning_frame, text=f"({row},{col})", width=80, height=80, fg_color="gray")
                img_placeholder.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
                img_placeholder.bind("<Button-1>", lambda e, img=img_placeholder: self.expand_image(img))
                self.scan_image_grid.append(img_placeholder)

        # STOP and Finish buttons
        ctk.CTkButton(scanning_frame, text="STOP", fg_color="red").grid(row=5, column=0, columnspan=5, pady=10, sticky='ew')
        ctk.CTkButton(scanning_frame, text="Finish", command=self.display_main_tab).grid(row=6, column=0, columnspan=5, pady=5, sticky='ew')

    def load_images_from_folder(self, folder):
        """Load image file paths from the specified folder."""
        return [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(('png', 'jpg', 'jpeg', 'gif'))]

    def display_random_sampling_layout(self, num_images=7):
        """Displays an evenly distributed grid layout for images with centering and proper button positioning."""
    
        # Clear previous content
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # Create a new frame with proper centering
        sampling_frame = ctk.CTkFrame(self.content_frame)
        sampling_frame.pack(expand=True, fill='both', padx=10, pady=10)

        # Load images
        images = self.load_images_from_folder(self.image_folder)
        self.image_labels = []  # Store image labels for reference

        # Calculate row distribution
        first_row_count = (num_images + 1) // 2  # Extra image goes to the first row if odd
        second_row_count = num_images // 2

        # Configure grid to center images
        total_columns = max(first_row_count, second_row_count)  # Use max columns for even spacing
        for col in range(total_columns):
            sampling_frame.grid_columnconfigure(col, weight=1)  # Make columns expand

        sampling_frame.grid_rowconfigure(0, weight=1)  # Center first row
        sampling_frame.grid_rowconfigure(1, weight=1)  # Center second row
        sampling_frame.grid_rowconfigure(2, weight=0)  # Ensure buttons are always visible

        # Display first row
        for col in range(first_row_count):
            img = Image.open(images[col])
            img = img.resize((100, 100), Image.LANCZOS)
            img_ctk = ctk.CTkImage(img, size=(100, 100))

            img_label = ctk.CTkLabel(sampling_frame, image=img_ctk, text="")
            img_label.grid(row=0, column=col, padx=10, pady=10, sticky='nsew')  # Centering adjustments

            img_label.bind("<Button-1>", lambda e, img_path=images[col]: self.expand_image(img_path))
            self.image_labels.append(img_label)

        # Display second row
        for col in range(second_row_count):
            img = Image.open(images[first_row_count + col])
            img = img.resize((100, 100), Image.LANCZOS)
            img_ctk = ctk.CTkImage(img, size=(100, 100))

            img_label = ctk.CTkLabel(sampling_frame, image=img_ctk, text="")
            img_label.grid(row=1, column=col, padx=10, pady=10, sticky='nsew')

            img_label.bind("<Button-1>", lambda e, img_path=images[first_row_count + col]: self.expand_image(img_path))
            self.image_labels.append(img_label)

        # Ensure button frame is separate and always visible
        button_frame = ctk.CTkFrame(self.content_frame)  # Placing it in content_frame instead of sampling_frame
        button_frame.pack(fill='x', pady=15)  # Fill the width to ensure centering

        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red")
        stop_button.pack(side='left', expand=True, padx=5, pady=5)

        finish_button = ctk.CTkButton(button_frame, text="Finish", command=self.display_main_tab)
        finish_button.pack(side='right', expand=True, padx=5, pady=5)

    def expand_image(self, img_label):
        """Opens a resizable window that scales the image proportionally."""
        expanded_window = ctk.CTkToplevel(self)
        expanded_window.title("Expanded Image")
        expanded_window.geometry("600x600")  # Default size
        expanded_window.minsize(300, 300)    # Minimum size to prevent excessive shrinking

        expanded_window.grab_set()

        # Load the original image
        original_img = Image.open(img_label)  # Replace with your image path
        self.resized_img = original_img.copy()  # Track the resized image

        # Create a Tkinter-compatible image for dynamic resizing
        self.img_ctk = ImageTk.PhotoImage(self.resized_img)

        # Display Image
        self.img_display = ctk.CTkLabel(expanded_window, image=self.img_ctk, text="")
        self.img_display.pack(expand=True, fill='both', padx=10, pady=10)

        # Dynamic resizing logic
        expanded_window.bind("<Configure>", lambda event: self.resize_image(event, original_img))

        # Back Button to close window
        ctk.CTkButton(expanded_window, text="Back", command=expanded_window.destroy).pack(pady=5)

    def resize_image(self, event, original_img):
        """Resizes the image proportionally based on window size."""
        # Maintain the original image's aspect ratio
        aspect_ratio = original_img.width / original_img.height

        # Calculate new dimensions based on window size
        new_width = min(event.width - 20, event.height - 20)  # Account for padding
        new_height = int(new_width / aspect_ratio)

        # Resize the image
        self.resized_img = original_img.resize((new_width, new_height), Image.LANCZOS)
        self.img_ctk = ImageTk.PhotoImage(self.resized_img)

        # Update the image in the label
        self.img_display.configure(image=self.img_ctk)

    #=============================== GUI Functionality ===============================#
    
    #------------------- Disable Buttons Function ----------------------#
    #DOESN"T WORK RIGHT NOW
    def disable_buttons(self, buttons, condition):
        """Disable or enable buttons based on condition."""
        for button in buttons:
            if condition:
                button.configure(state=ctk.DISABLED)  # Disable button
            else:
                button.configure(state=ctk.NORMAL)  # Enable button again


    #============================== Communcation ====================================#
    
    #Assign communication handler from main.py
    def set_communication(self, comms):
        self.comms = comms

    #Get all the data from the JSON file
    #From raspberry pi publisher
    def unpack_pi_JSON(self, data):
        # Extract values from the received data dictionary, with defaults for missing keys
        self.status = data.get("status", "Unknown")
        self.mode = data.get("mode", "Manual")
        self.alarm_status = data.get("alarm_status", "None")

        self.speed = data.get("speed", 0)
        self.motor_A = data.get("motor_A", 0)
        self.motor_B = data.get("motor_B", 0)
        self.motor_Z = data.get("motor_Z", 0)
        self.current_pos_x = data.get("x_pos", 0)
        self.current_pos_y = data.get("y_pos", 0)
        self.current_pos_z = data.get("z_pos", 0)

        self.total_image = data.get("total_image", 0)
        self.current_image = data.get("current_image", 0)
        self.file_location = data.get("file_location", "Unknown")
        self.brightness = data.get("brightness", 0)
        self.contrast = data.get("contrast", 0)

    #Unpack and update data from raspberry pi
    #Function is called in communication.py in the receive status updates
    def update_status_data(self, data):
        """Update GUI with received data"""
        # Extract values from the received data dictionary, with defaults for missing keys
        self.unpack_pi_JSON(data)

        # Update all GUI elements
        self.status_label.configure(text=f"Module Status: {self.status}")
        self.alarm_label.configure(text=f"Alarms: {self.alarm_status}")
        self.speed_label.configure(text=f"Speed: {self.speed}")


    #Function sends sample_data to raspberry pi
    #This function is called in function store_sample_data when the ok button is pressed
    def send_sampleData(self, mount_type, sample_height, initial_height, sample_id):
        """Stores sample data, sends it to the Raspberry Pi, and sends mode request."""
        # Store the sample data
        self.sample_data['mount_type'] = mount_type
        self.sample_data['sample_height'] = sample_height
        self.sample_data['initial_height'] = initial_height
        self.sample_data['sample_id'] = sample_id

        if self.comms:  # Ensure communication handler exists
            try:
                # Send the sample data to Raspberry Pi
                response = self.comms.send_data(self.sample_data)
                print(f"Response from Raspberry Pi: {response}")

                # Show confirmation in GUI
                messagebox.showinfo("Success", "Sample data sent successfully!")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to send sample data: {e}")

    #Send random samping data to raspberry pi
    #Called when ok is pressed in random sampling pop-up window
    def send_random_data(self, mode, status, num_images):
        if self.status == "Idle":
            #Store random sampling data
            self.random_data['mode'] = mode
            self.random_data['status'] = status
            self.random_data['num_images'] = num_images

            if self.comms:  # Ensure communication handler exists
                try:
                    # Send the sample data to Raspberry Pi
                    response = self.comms.send_data(self.random_data)
                    print(f"Response from Raspberry Pi: {response}")

                    # Show confirmation in GUI
                    messagebox.showinfo("Success", "Sample data sent successfully!")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to send sample data: {e}")
        else:
            print("Status not in idle, wait to requestion scanning mode.")
    
    #Send scanning data to raspberry pi
    #Called when ok is pressed in scanning sampling pop-up window
    def send_scanning_data(self, mode, status, step_x, step_y):
        if self.status == "Idle":
            #Store scanning sampling data
            self.scanning_data['mode'] = mode
            self.scanning_data['status'] = status
            self.scanning_data['step_x'] = step_x
            self.scanning_data['step_y'] = step_y

            if self.comms:  # Ensure communication handler exists
                try:
                    # Send the sample data to Raspberry Pi
                    response = self.comms.send_data(self.scanning_data)
                    print(f"Response from Raspberry Pi: {response}")

                    # Show confirmation in GUI
                    messagebox.showinfo("Success", "Sample data sent successfully!")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to send sample data: {e}")
        else:
            print("Status not in idle, wait to requestion scanning mode.")
