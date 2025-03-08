import tkinter as tk
import customtkinter as ctk
from tkinter import simpledialog

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Checking & waffles")
        self.geometry("750x400")

        # Dictionary to store different frames
        self.frames = {}

        # Create the four frames
        for name in ["Main", "Motion", "Image", "Settings"]:
            frame = ctk.CTkFrame(self, width=500, height=350, corner_radius=10)
            label = ctk.CTkLabel(frame, text=f"{name}", font=("Arial", 18))
            label.pack(pady=20)
            self.frames[name] = frame
        
        # Initially show the Main tab
        self.show_frame("Main")

        # Bottom frame to hold the buttons
        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Tab buttons
        for name in ["Main", "Motion", "Image", "Settings"]:
            button = ctk.CTkButton(bottom_frame, text=name, command=lambda n=name: self.show_frame(n))
            button.pack(side=tk.LEFT, expand=True, padx=5, pady=5)

        # Selection Box
        self.selection_var = tk.StringVar(value="Select Mode")
        selection_box = ctk.CTkOptionMenu(self, variable=self.selection_var, values=["Scanning", "Detailed"], command=self.open_popup)
        selection_box.pack(pady=10)

    def show_frame(self, name):
        for frame in self.frames.values():
            frame.pack_forget()
        self.frames[name].pack(fill=tk.BOTH, expand=True)

    def open_popup(self, selection):
        sample_param = simpledialog.askstring("Input", f"Enter sample parameters for {selection} mode:")
        if sample_param:
            print(f"{selection} mode selected with parameters: {sample_param}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
