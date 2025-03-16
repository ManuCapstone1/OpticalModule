#GUI imports
import customtkinter as ctk
from tkinter import filedialog, messagebox, font
from PIL import Image, ImageTk
from datetime import datetime
import numpy as np
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
        """Displays sample dialog and switches layout based on user choice."""
        sample_window = ctk.CTkToplevel(self)
        sample_window.title(f"{mode} Parameters")
        sample_window.geometry("330x360")
        sample_window.minsize(330, 360)
        sample_window.maxsize(330, 360)
        

        sample_window.grab_set()

        ctk.CTkLabel(sample_window, text="Select your mount type:").grid(row = 0, column = 0, columnspan = 4, padx=1, pady=5)
        mount_type = ctk.CTkComboBox(sample_window, values=["Puck", "Stub"])
        mount_type.grid(row = 1, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        ctk.CTkLabel(sample_window, text="Enter sample height:").grid(row = 2, column = 0, columnspan = 4, padx=1, pady=5)
        sample_height = ctk.CTkEntry(sample_window)
        sample_height.grid(row = 3, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        ctk.CTkLabel(sample_window, text="Enter bounding box size:").grid(row = 4, column = 0, columnspan = 4, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(sample_window, text="Width:").grid(row=5, column=0, padx=1, pady=5, sticky = "e")
        sample_width = ctk.CTkEntry(sample_window, width = 50)
        sample_width.grid(row = 5, column = 1, padx=5, pady=5, sticky = "w")
        ctk.CTkLabel(sample_window, text="Length:").grid(row=5, column=2, padx=5, pady=5, sticky = "e")
        sample_length = ctk.CTkEntry(sample_window, width = 50)
        sample_length.grid(row = 5, column = 3, padx=5, pady=10, sticky = "w")


        def toggleEntry():
            if sample_2_var.get():
                sample_height_2.configure(state='normal')
            else:
                sample_height_2.configure(state='disabled')

        sample_2_var = ctk.BooleanVar()
        sample_2_check = ctk.CTkCheckBox(sample_window, text="Sample 2", variable=sample_2_var, command=toggleEntry)
        sample_2_check.grid(row = 6, column = 0, columnspan = 4, padx=5, pady=10)

        sample_height_2 = ctk.CTkEntry(sample_window, state='disabled')
        sample_height_2.grid(row = 7, column = 1, columnspan = 2, padx=5, pady=5)

        def on_ok():
            sample_data['mode'] = mode
            sample_data['mount_type'] = mount_type.get()
            sample_data['sample_height'] = sample_height.get()
            sample_data['sample_height_2'] = sample_height_2.get()
            sample_window.destroy()

            # Switch layout based on mode
            if mode == "Random Sampling":
                self.display_random_sampling_layout()
            elif mode == "Scanning":
                self.display_scanning_layout(images_x=4, images_y=3)

        ok_button = ctk.CTkButton(sample_window, text="OK", command=on_ok, width = 80)
        ok_button.grid(row = 8, column = 0, padx=5, pady=5)

        ctk.CTkButton(sample_window, text="Cancel", command=sample_window.destroy, width = 80).grid(row = 8, column = 3,columnspan = 2, padx=5, pady=5)
 
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

        ctk.CTkButton(left_frame, text="Go To", font=("Arial", 20)).grid(row=0, column=0, columnspan = 3, padx=5, pady=5, sticky="ew")

        # Position Controls
        self.create_position_control(left_frame, "X", current_x_pos, row=1)
        self.create_position_control(left_frame, "Y", current_y_pos, row=2)
        self.create_position_control(left_frame, "Z", current_z_pos, row=3)

        # Speed Control
        ctk.CTkLabel(left_frame, text="Speed", font=("Arial", 18)).grid(row=4, column=0, padx=5, pady=30, sticky='w')
        self.speed_entry = ctk.CTkEntry(left_frame, width=30)
        self.speed_entry.insert(0, str(speed_value))
        self.speed_entry.grid(row=4, column=2, padx=5, pady=30)

        self.create_step_buttons(left_frame, self.speed_entry, step=1, row=4)

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

    # ------------------ Step Adjustment Buttons ------------------ #
    def create_step_buttons(self, parent, entry_widget, step=1, row=0):
        btn_frame = ctk.CTkFrame(parent)
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
        ctk.CTkLabel(xy_graph, text = "       ", fg_color="red").place(relx=current_x_pos*0.001, rely=current_y_pos*0.001, anchor='center')
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

    # ------------------ Random Sampling Layout ------------------ #
    def display_random_sampling_layout(self, num_images=6):
        """Displays adjustable grid layout for Random Sampling with up to 10 images."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # New layout for Random Sampling
        sampling_frame = ctk.CTkFrame(self.content_frame)
        sampling_frame.pack(expand=True, fill='both', padx=10, pady=10)

        # Image placeholders logic
        self.image_labels = []  # Store image labels for future updates

        # Determine row/column distribution
        first_row_count = min(5, num_images)  # Max 5 in first row
        second_row_count = num_images - first_row_count

        # Create 1st row of image placeholders
        for col in range(first_row_count):
            img_placeholder = ctk.CTkLabel(sampling_frame, text=f"Image {col + 1}", width=100, height=100, fg_color="gray")
            img_placeholder.grid(row=0, column=col, padx=5, pady=5, sticky='nsew')
            img_placeholder.bind("<Button-1>", lambda e, img=img_placeholder: self.expand_image(img))
            self.image_labels.append(img_placeholder)

        # Create 2nd row if needed
        for col in range(second_row_count):
            img_placeholder = ctk.CTkLabel(sampling_frame, text=f"Image {first_row_count + col + 1}", width=100, height=100, fg_color="gray")
            img_placeholder.grid(row=1, column=col, padx=5, pady=5, sticky='nsew')
            img_placeholder.bind("<Button-1>", lambda e, img=img_placeholder: self.expand_image(img))
            self.image_labels.append(img_placeholder)

        # STOP and Finish buttons
        ctk.CTkButton(sampling_frame, text="STOP", fg_color="red").grid(row=2, column=2, columnspan=5, pady=10, sticky='ew')
        ctk.CTkButton(sampling_frame, text="Finish", command=self.display_main_tab).grid(row=3, column=2, columnspan=5, pady=5, sticky='ew')

    def expand_image(self, img_label):
        """Opens a resizable window that scales the image proportionally."""
        expanded_window = ctk.CTkToplevel(self)
        expanded_window.title("Expanded Image")
        expanded_window.geometry("600x600")  # Default size
        expanded_window.minsize(300, 300)    # Minimum size to prevent excessive shrinking

        expanded_window.grab_set()

        # Load the original image
        original_img = Image.open("C:/Users/a4iri/Desktop/Capstone/Test Image.png")  # Replace with your image path
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


    
#--------- PC to Raspberry Pi Communication ------------#
 
 
 
# ------------------ Run Application ------------------ #
if __name__ == "__main__":
    app = MainApp()
    app.mainloop()