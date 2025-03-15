import customtkinter as ctk
from tkinter import filedialog, messagebox, font
from PIL import Image, ImageTk
from datetime import datetime
import os

from communication import CommunicationHandler


class MainApp(ctk.CTk):
    #============================ Appearance =================================================#
    def __init__(self):
        super().__init__()
    
        #Skeleton appearance
        self.title("Control Panel")
        self.geometry("900x600")
        self.minsize(900, 600)  # Set the minimum width and height
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

        #Data recieved from raspberry pi
        self.module_status = "Idle"
        self.alarm_status = "OK"

        #Motor varaibles from pi
        self.current_x_pos = 50
        self.current_y_pos = 50
        self.current_z_pos = 50

        #data sent to raspberry pi
        self.sample_data = {}
        self.mode_req = {}

    # ------------------ Top Frame ------------------ #
    def create_top_frame(self):
        top_frame = ctk.CTkFrame(self)
 
        #Space between the edge and the frame
        top_frame.pack(side=ctk.TOP, fill='x', padx=10, pady=5)
 
        self.status_label = ctk.CTkLabel(top_frame, text=f"Module Status: {self.module_status}")
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

    # ------------------ Time Updater ------------------ #
    def update_time(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.date_time_label.configure(text=now)
        self.after(1000, self.update_time)
 
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
 
        #Setup frame padding on left and right
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)
 
        right_frame = ctk.CTkFrame(self.content_frame, width=400, height=400)
        right_frame.pack(side=ctk.RIGHT, expand=True, fill='both')
 
        # Image Display on Right
        self.display_placeholder_image(right_frame)
 
        # Buttons on Left Side
        sampling_btn = ctk.CTkButton(left_frame, text="Random Sampling", font=("Arial", 20), width = 200, height = 100, 
            command=lambda: self.open_sample_dialog("Random Sampling"))
        scanning_btn = ctk.CTkButton(left_frame, text="Scanning", font=("Arial", 20), width = 200, height = 100, 
            command=lambda: self.open_sample_dialog("Scanning"))
 
        sampling_btn.pack(pady=5, fill='x')
        scanning_btn.pack(pady=5, fill='x')
 
        calibration_btn = ctk.CTkButton(left_frame, width = 200, height = 100, text="Calibration", font=("Arial", 20),
            command=lambda : self.store_send_mode("exe_calibration"))
        calibration_btn.pack(pady=5, fill='x')
 
        home_btn = ctk.CTkButton(left_frame, text="Homing", width = 200, height = 100, font=("Arial", 20), 
            command=lambda: self.store_send_mode("exe_homing"), fg_color="green", text_color="white")
        home_btn.pack(pady=5, fill='x')
       
   
    # ------------------ Image Placeholder ------------------ #
    def display_placeholder_image(self, frame):
        img = Image.open("C:/Users/Steph/Downloads/dog.jpg")  # Replace with your image path
        img = img.resize((350, 350), Image.LANCZOS)
 
        # Create a CTkImage instance
        try:
            img = Image.open("C:/Users/Steph/Downloads/dog.jpg")
        except FileNotFoundError:
            messagebox.showerror("Error", "Image file not found.")
            return
   
        # Create the CTkLabel and display the CTkImage
        img_label = ctk.CTkLabel(frame, image=img_ctk, text="")
        img_label.pack(expand=True)
 
    # ------------------ Sample Parameter Dialog ------------------ #
    def open_sample_dialog(self, mode):
 
        sample_window = ctk.CTkToplevel(self)
        sample_window.title(f"{mode} Parameters")
        sample_window.geometry("300x300")
 
        # Ensure the new window appears on top
        sample_window.grab_set()
 
        ctk.CTkLabel(sample_window, text="Select your mount type:").pack(pady=5)
        mount_type = ctk.CTkComboBox(sample_window, values=["Puck", "Stub"])
        mount_type.pack(pady=5)
 
        ctk.CTkLabel(sample_window, text="Enter sample height:").pack(pady=5)
        sample_height = ctk.CTkEntry(sample_window)
        sample_height.pack(pady=5)

        #Greys out sample 2 if it is unchecked
        def toggleEntry():
            if sample_2_var.get() == True:
                sample_height_2.configure(state='normal')  # Enable entry
            else:
                sample_height_2.configure(state='disabled')  # Disable entry
 
        sample_2_var = ctk.BooleanVar()
        sample_2_check = ctk.CTkCheckBox(sample_window, text="Sample 2", variable=sample_2_var, command=toggleEntry)
        sample_2_check.pack(pady=5)
 
        sample_height_2 = ctk.CTkEntry(sample_window, state='disabled')
        sample_height_2.pack(pady=5)
 
        # OK / Cancel Buttons
        ok_button = ctk.CTkButton(sample_window, text="OK", state='disabled', 
            command=lambda: self.store_sample_data(mode, mount_type.get(), 
            sample_height.get(), sample_height_2.get(), sample_window))
        ok_button.pack(side=ctk.LEFT, padx=5, pady=10)
        
        ctk.CTkButton(sample_window, text="Cancel", command=sample_window.destroy).pack(side=ctk.RIGHT, padx=5, pady=10)
 
 
        # # Enable OK Button if entries are filled
        def validate_entries(*args):
            if mount_type.get() and sample_height.get():
                ok_button.configure(state='normal')
            else:
                ok_button.configure(state='disabled')
 
        mount_type.bind("<<ComboboxSelected>>", validate_entries)
        sample_height.bind("<KeyRelease>", validate_entries)
 
    # ------------------ Motion Tab ------------------ #
    def display_motion_tab(self):
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)
 
        right_frame = ctk.CTkFrame(self.content_frame)
        right_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)
 
        # GoTo Button
        ctk.CTkButton(left_frame, text="Go To", font=("Arial", 20)).pack(padx=5, pady=5)
 
        # Coordinate Entries and Step Adjustment
        self.create_position_control(left_frame, "X", self.current_x_pos)
        self.create_position_control(left_frame, "Y", self.current_y_pos)
        self.create_position_control(left_frame, "Z", self.current_z_pos)
 
        # Speed Control
        ctk.CTkLabel(left_frame, text="Speed").pack(padx=5, pady=2)
        self.speed_entry = ctk.CTkEntry(left_frame, width=30)
        self.speed_entry.insert(0, str(speed_value))
        self.speed_entry.pack(padx=5, pady=2)
 
        # Speed Increment/Decrement
        self.create_step_buttons(left_frame, self.speed_entry, step=1)
 
        # Disable Steppers, Homing, and Calibration
        ctk.CTkButton(left_frame, text="Disable Stepper Motors").pack(padx=5, pady=5)
        ctk.CTkButton(left_frame, text="Homing", fg_color="green").pack(padx=5, pady=5)
        ctk.CTkButton(left_frame, text="Calibration").pack(padx=5, pady=5)
 
        # Graph Display
        self.create_graphs(right_frame)
 
        ctk.CTkButton(right_frame, text="STOP", fg_color="red").pack(padx=10, pady=5)
        ctk.CTkButton(right_frame, text="Finish").pack(padx=50, pady=5)
 
   # ------------------ Position Control ------------------ #
    def create_position_control(self, parent, label, value):
        ctk.CTkLabel(parent, text=f"{label} Position:").pack(padx=5, pady=2)
        entry = ctk.CTkEntry(parent, width=30)
        entry.insert(0, str(value))
        entry.pack(padx=5, pady=2)
 
        # Arrows for Step Adjustments
        self.create_step_buttons(parent, entry)
 
    # ------------------ Step Adjustment Buttons ------------------ #
    def create_step_buttons(self, parent, entry_widget, step=1):
        btn_frame = ctk.CTkFrame(parent)
        btn_frame.pack(padx=5, pady=2)
 
        ctk.CTkButton(btn_frame, text="▲", width=30, command=lambda: self.adjust_value(entry_widget, step)).pack(side=ctk.LEFT, padx=2)
        ctk.CTkButton(btn_frame, text="▼", width=30, command=lambda: self.adjust_value(entry_widget, -step)).pack(side=ctk.LEFT, padx=2)
 
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
        ctk.CTkLabel(xy_graph, text = "       ", fg_color="red").place(relx=0.5, rely=0.5, anchor='center')
        ctk.CTkLabel(z_graph, text = "   ", fg_color="red").place(relx=0.5, rely=0.5, anchor='center')
 
    #=============================== GUI Functionality ===============================#
    
    #------------------- Disable Buttons Function ------------#
    def disable_buttons(self, buttons, condition):
        """Disable or enable buttons based on condition."""
        for button in buttons:
            if condition:
                button.configure(state=ctk.DISABLED)  # Disable button
            else:
                button.configure(state=ctk.NORMAL)  # Enable button again


    #============================== Communcation ====================================#
    def set_communication(self, comms):
        """Assigns the communication handler"""
        self.comms = comms

    #Get status data from raspberry pi. updates every second
    #Function is called in communication.py in the receive status updates
    def update_status_data(self, data):
        """Update GUI with received data"""
        # Extract values from the received data dictionary, with defaults for missing keys
        self.module_status = data.get("module_status", "Unknown")
        self.alarm_status = data.get("alarm_status", "None")
        self.motor_A = data.get("motor_A", 0)
        self.motor_B = data.get("motor_B", 0)
        self.motor_Z = data.get("motor_Z", 0)
        self.current_pos_x = data.get("x_pos", 0)
        self.current_pos_y = data.get("y_pos", 0)
        self.current_pos_z = data.get("z_pos", 0)
        self.total_image = data.get("total_image", 0)
        self.current_image = data.get("current_image", 0)
        self.file_location = data.get("file_location", "Unknown")

        # Update all GUI elements
        self.status_label.configure(text=f"Module Status: {self.module_status}")
        self.alarm_label.configure(text=f"Alarms: {self.alarm_status}")
        
        # Add additional GUI updates for new fields



    #Function sends sample_data to raspberry pi
    #This function is called in function store_sample_data when the ok button is pressed
        #Function stores the sample data just endered into the pop-up window
    def store_send_sampleData(self, mode, mount_type, sample_height, sample_height_2, window):
        """Stores sample data, sends it to the Raspberry Pi, and sends mode request."""
        
        # Store the sample data
        self.sample_data['mount_type'] = mount_type
        self.sample_data['sample_height'] = sample_height
        self.sample_data['sample_height_2'] = sample_height_2
        
        window.destroy()  # Close the window before sending data

        if self.comms:  # Ensure communication handler exists
            # Prepare the sample data for sending
            sample_data = {
                "sample_data": {
                    "mount_type": self.sample_data.get("mount_type", "Unknown"),
                    "sample_height": self.sample_data.get("sample_height", "0"),
                    "sample_height_2": self.sample_data.get("sample_height_2", "0")
                }
            }

            try:
                # Send the sample data to Raspberry Pi
                response = self.comms.send_data(sample_data)
                print(f"Response from Raspberry Pi: {response}")

                # Show confirmation in GUI
                messagebox.showinfo("Success", "Sample data sent successfully!")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to send sample data: {e}")

        # Send mode request based on the mode passed
        if mode == "Random Sampling":
            self.store_send_mode("exe_random")
        elif mode == "Scanning":
            self.store_send_mode("exe_scanning")



    #Send request mode
    #Will only send request if module is in "Idle"
    def store_send_mode(self, mode):
        self.mode_req['mode_req'] = mode

        if self.comms and self.module_status == "Idle"
            mode_req = {
                "mode" : {
                    "mode_req" : self.mode_req.get("mode_req", "Uknown")
                } 
            }

            try:
                response = self.comms.send_data(mode_req)
                print(f"Response from Raspberry Pi: {response}")

                # Show confirmation in GUI
                messagebox.showinfo("Success", "Mode request sent successfully!")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to send Mode request: {e}")

            disable_buttons([sampling_btn,scanning_btn,homing_btn,calibration_btn], True)
        else :
            self.mode_req['mode_req'] = "failed"
            disable_buttons([sampling_btn,scanning_btn,homing_btn,calibration_btn], False)




