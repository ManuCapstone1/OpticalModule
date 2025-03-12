import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
import time

class Application(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Custom GUI")
        self.geometry("750x400")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        #Font configurations
        small_font = ctk.CTkFont(family = "Arial", size = 8)
        large_font = ctk.CTkFont(family = "Arial", size = 13)
        bold_font = ctk.CTkFont(family = "Arial", size = 13, weight = 'bold')

        # Top Frame configuration
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)

        #Progress bar at the top frame
        self.progress_bar = ctk.CTkProgressBar(self.top_frame, width=200)
        self.progress_bar.pack(side="left", padx=10)
        current_progress = 0.5 #Need to find a way to display completion metric
        self.progress_bar.set(current_progress) 

        # Main Content Area
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=1, column=1, sticky="nsew")
        
        # Bottom Frame with Tabs
        self.bottom_frame = ctk.CTkFrame(self)
        self.bottom_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.bottom_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)
        
        self.main_btn = ctk.CTkButton(self.bottom_frame, text="Main", command=lambda: self.show_frame("main"), font = large_font)
        self.main_btn.grid(row=0, column=0, sticky="ew")
        
        self.motion_btn = ctk.CTkButton(self.bottom_frame, text="Motion", command=lambda: self.show_frame("motion"), font = large_font)
        self.motion_btn.grid(row=0, column=1, sticky="ew")
        
        self.image_btn = ctk.CTkButton(self.bottom_frame, text="Image", command=lambda: self.show_frame("image"), font = large_font)
        self.image_btn.grid(row=0, column=2, sticky="ew")
        
        self.settings_btn = ctk.CTkButton(self.bottom_frame, text="Settings", command=lambda: self.show_frame("settings"), font = large_font)
        self.settings_btn.grid(row=0, column=3, sticky="ew")
        
        self.status_label_bottom = ctk.CTkLabel(self.bottom_frame, text="Module Status: OK | Alarms: None", font = small_font)
        self.status_label_bottom.grid(row=0, column=4, sticky="e", padx=10)
        
        self.time_label = ctk.CTkLabel(self.bottom_frame, text="Time: ", font = small_font)
        self.time_label.grid(row=0, column=5, sticky="e", padx=10)
        self.update_time()
    
        # Creating Frames for Each Tab
        self.frames = {}
        for frame_name in ("main", "motion", "image", "settings"):
            frame = ctk.CTkFrame(self.main_frame)
            self.frames[frame_name] = frame
        
        # Main Frame Content
        home_button = ctk.CTkButton(self.frames["main"], text="HOME")
        home_button.pack(pady=10)

        self.scanning_button = ctk.CTkButton(self.frames["main"], text="Scanning", command=self.show_popup)
        self.scanning_button.pack(pady=5)
        
        self.detailed_button = ctk.CTkButton(self.frames["main"], text="Detailed", command=self.show_popup)
        self.detailed_button.pack(pady=5)
        




        # Motion Frame Content
        ctk.CTkLabel(self.frames["motion"], text="Move To:").pack()
        
        coord_frame = ctk.CTkFrame(self.frames["motion"])
        coord_frame.pack()
        
        ctk.CTkLabel(coord_frame, text="X:").grid(row=0, column=0)
        self.x_entry = ctk.CTkEntry(coord_frame)
        self.x_entry.grid(row=0, column=1, padx=5)
        
        ctk.CTkLabel(coord_frame, text="Y:").grid(row=1, column=0)
        self.y_entry = ctk.CTkEntry(coord_frame)
        self.y_entry.grid(row=1, column=1, padx=5)
        
        ctk.CTkLabel(coord_frame, text="Z:").grid(row=2, column=0)
        self.z_entry = ctk.CTkEntry(coord_frame)
        self.z_entry.grid(row=2, column=1, padx=5)
        




        # Settings Frame Content
        settings_frame = ctk.CTkFrame(self.frames["settings"])
        settings_frame.pack(anchor="w", padx=10)
        ctk.CTkLabel(settings_frame, text="Motor Status: OK").pack(anchor="w")
        ctk.CTkLabel(settings_frame, text="Camera Status: Active").pack(anchor="w")
        ctk.CTkLabel(settings_frame, text="Image Processing: Running").pack(anchor="w")
        



        # Image Frame Content
        ctk.CTkLabel(self.frames["image"], text="Current folder path:").pack()
        self.folder_path_entry = ctk.CTkEntry(self.frames["image"], width=300)
        self.folder_path_entry.pack(pady=5)
        
        self.show_frame("main")
    
        #configuring the fonts
        small_font.configure(family = "Arial")
        large_font.configure(family = "Arial")
        bold_font.configure(family = "Arial")


    def show_frame(self, frame_name):
        for frame in self.frames.values():
            frame.pack_forget()
        self.frames[frame_name].pack(fill="both", expand=True)
    
    def show_popup(self):
        messagebox.showinfo("Sample Parameters", "Enter sample parameters here.")
    
    def update_time(self):
        current_time = time.strftime("%H:%M:%S")
        self.time_label.configure(text=f"Time: {current_time}")
        self.after(1000, self.update_time)
        
if __name__ == "__main__":
    app = Application()
    app.mainloop()