#GUI imports
import customtkinter as ctk
from tkinter import filedialog, messagebox, font
from PIL import Image, ImageTk
from datetime import datetime
import os
 
# Global Variables
module_status = "OK"
alarm_status = "None"
sample_data = {}
 
 
# Sample Position Variables
current_x_pos = 50
current_y_pos = 50
current_z_pos = 50
speed_value = 10
 
# Sample Image Folder Paths
image_folder = "images_folder"
 
# ------------------ Main App ------------------ #
class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
 
        self.title("Control Panel")
        self.geometry("800x500")
        self.minsize(800, 550)  # Set the minimum width and height
        ctk.set_appearance_mode("dark")  # Options: "dark", "light", "system"
 
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
 
        self.status_label = ctk.CTkLabel(top_frame, text=f"Module Status: {module_status}")
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
 
        self.alarm_label = ctk.CTkLabel(bottom_frame, text=f"Alarms: {alarm_status}")
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
 
        #Setup frame padding on left and right
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)
 
        right_frame = ctk.CTkFrame(self.content_frame, width=400, height=400)
        right_frame.pack(side=ctk.RIGHT, expand=True, fill='both')

        # Image Display on Right
        self.display_placeholder_image(right_frame)
 
        # Buttons on Left Side
        sampling_btn = ctk.CTkButton(left_frame, text="Random Sampling", font=("Arial", 20), width = 200, height = 100, command=lambda: self.open_sample_dialog("Random Sampling"))
        scanning_btn = ctk.CTkButton(left_frame, text="Scanning", font=("Arial", 20), width = 200, height = 100, command=lambda: self.open_sample_dialog("Scanning"))
 
        sampling_btn.pack(pady=5, fill='x')
        scanning_btn.pack(pady=5, fill='x')

        calibration_btn = ctk.CTkButton(left_frame, width = 200, height = 100, text="Calibration", font=("Arial", 20))
        calibration_btn.pack(pady=5, fill='x')

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

        def toggleEntry():
            if sample_2_var.get() == True:
                sample_height_2.configure(state='normal')  # Enable entry
            else:
                sample_height_2.configure(state='disabled')  # Disable entry
 
        sample_2_var = ctk.BooleanVar()
        sample_2_check = ctk.CTkCheckBox(sample_window, text="Sample 2", variable=sample_2_var, command = toggleEntry)
        sample_2_check.pack(pady=5)

        sample_height_2 = ctk.CTkEntry(sample_window, state='disabled')
        sample_height_2.pack(pady=5)
 
        # OK / Cancel Buttons
        ok_button = ctk.CTkButton(sample_window, text="OK", state='disabled', command=lambda: self.store_sample_data(mode, mount_type.get(), sample_height.get(), sample_height_2.get(), sample_window))
        ok_button.pack(side=ctk.LEFT, padx=5, pady=10)
 
        ctk.CTkButton(sample_window, text="Cancel", command=sample_window.destroy).pack(side=ctk.RIGHT, padx=5, pady=10)

 
        # Enable OK Button if entries are filled
        def validate_entries(*args):
            if mount_type.get() and sample_height.get():
                ok_button.configure(state='normal')
            else:
                ok_button.configure(state='disabled')
 
        mount_type.bind("<<ComboboxSelected>>", validate_entries)
        sample_height.bind("<KeyRelease>", validate_entries)
 
    def store_sample_data(self, mode, mount_type, sample_height, sample_height_2, window):
        sample_data['mode'] = mode
        sample_data['mount_type'] = mount_type
        sample_data['sample_height'] = sample_height
        sample_data['sample_height_2'] = sample_height_2
        window.destroy()
 
    # ------------------ Motion Tab ------------------ #
    def display_motion_tab(self):
        left_frame = ctk.CTkFrame(self.content_frame)
        left_frame.pack(side=ctk.LEFT, fill='y', padx=10, pady=10)

        right_frame = ctk.CTkFrame(self.content_frame)
        right_frame.pack(side=ctk.RIGHT, expand=True, fill='both', padx=10, pady=10)

        # GoTo Button
        ctk.CTkButton(left_frame, text="Go To", font=("Arial", 20)).pack(padx=5, pady=5)

        # Coordinate Entries and Step Adjustment
        self.create_position_control(left_frame, "X", current_x_pos)
        self.create_position_control(left_frame, "Y", current_y_pos)
        self.create_position_control(left_frame, "Z", current_z_pos)

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
        ctk.CTkLabel(xy_graph, text="⬤", fg_color="red").place(relx=0.5, rely=0.5, anchor='center')
        ctk.CTkLabel(z_graph, text="━", fg_color="red").place(relx=0.5, rely=0.5, anchor='center')
 
    # ------------------ Time Updater ------------------ #
    def update_time(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.date_time_label.configure(text=now)
        self.after(1000, self.update_time)
 
 
#--------- PC to Raspberry Pi Communication ------------#
 
 
 
# ------------------ Run Application ------------------ #
if __name__ == "__main__":
    app = MainApp()
    app.mainloop()