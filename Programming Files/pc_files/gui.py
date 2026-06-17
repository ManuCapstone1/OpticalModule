import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
from datetime import datetime
import json
import time
import re
import os
import shutil
from threading import Thread
from stage import home_smaract

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
        self.status_lockout_time = 0.0
        self.alarm_status = "Unknown"
        self.mode = "Manual"

        #Motion data
        self.motors_enabled = False
        self.x_pos = 0
        self.y_pos = 0
        self.z_pos = 0
        self.is_at_interferometer = False

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

        #------ JSON Objects sent to Raspberry Pi ------#
        #Sample data
        self.sample_data = {
            "command" :"Unknown",
            "mode" : "Unknown",
            "mount_type" : "Unknown",
            "sample_location" : "Unknown",
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
        self.is_stitching = False
        self.scan_in_progress = False    # set when scan command sent; cleared on state 0→1
        self.sample_in_progress = False  # set when sampling command sent; cleared on state 0→1

        #-------------- Main Tab View State -----------------#
        self.active_main_view = "default"       # "default" | "stitched"
        self.current_stitched_img_path = None   # path persists across tab switches
        self.scan_end_x = 0.0                   # stage X at last tile (top-right corner)
        self.scan_end_y = 0.0                   # stage Y at last tile (top-right corner)

        #--------------- Threading -------------------#
        self.transfer_rpi_thread = Thread()
        self.transfer_pc_imgs = Thread()
        self.stitching_thread = Thread()

        #--------------- Area Capture State -------------------#
        self._roi_drag_start = None      # (canvas_x, canvas_y) when Ctrl+drag begins
        self._roi_rect_id = None         # kept for legacy; grid uses "roi_grid" tag
        self.roi_phys_x_start = None     # mm
        self.roi_phys_x_end = None       # mm
        self.roi_phys_y_start = None     # mm
        self.roi_phys_y_end = None       # mm
        self.map_grid_x = 4              # measurement point count in X (lines incl. border)
        self.map_grid_y = 4              # measurement point count in Y (lines incl. border)
        self._canvas_disp_w = 0          # displayed image width on canvas (px)
        self._canvas_disp_h = 0          # displayed image height on canvas (px)
        self._canvas_orig_w = 0          # original image width (sensor px)
        self._canvas_orig_h = 0          # original image height (sensor px)
        self._canvas_img_path = None     # path of image currently on canvas
        # Custom point-selection state (right-click markers)
        self.custom_measure_points = []   # list of (phys_x_mm, phys_y_mm) tuples
        self.measured_data = []           # list of (phys_x, phys_y, height) after a sequence
        self.analysis_selected_indices = []  # indices into measured_data currently highlighted

        # ROI bounding box in canvas pixels (normalized: x0<x1, y0<y1)
        self._roi_canvas_x0 = 0.0
        self._roi_canvas_y0 = 0.0
        self._roi_canvas_x1 = 0.0
        self._roi_canvas_y1 = 0.0
        # Interaction state machine
        self._roi_pan_active    = False   # True when any drag gesture is live (move OR resize)
        self._roi_pan_start     = None    # (cx, cy) start for move drags
        self._roi_active_canvas = None    # canvas widget that currently holds the grid
        # Resize-specific state
        self._roi_mode           = "none"   # "none" | "move" | "resize"
        self._roi_drag_corner    = None     # "nw" | "ne" | "sw" | "se"
        self._roi_resize_anchor  = None     # (cx, cy) of the fixed opposite corner

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
        self.img_gui = os.path.join(os.path.expanduser('~'), 'optical_module', 'Images', 'GUI')    
        #Buffer folders
        #Raw string in order to pass to Fiji succesfully for image stitching
        self.buffer_stitching_folder = os.path.join(os.path.expanduser('~'), 'optical_module', 'Images', 'buffer', 'stitching')
        self.buffer_sampling_folder =  os.path.join(os.path.expanduser('~'), 'optical_module', 'Images', 'buffer', 'sampling') 
        self.buffer_testing_folder =  os.path.join(os.path.expanduser('~'), 'optical_module', 'Images', 'buffer', 'camera_tests') 

        #Completed folders
        self.complete_stitching_folder = os.path.join(os.path.expanduser('~'), 'optical_module', 'Images', 'complete', 'stitching')  
        self.complete_sampling_folder = os.path.join(os.path.expanduser('~'), 'optical_module', 'Images', 'complete', 'sampling')

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

        # Right-side content: restore stitched map if one is active, else CAD placeholder
        if self.active_main_view == "stitched" and self.current_stitched_img_path:
            self.display_stitched_inline(self.current_stitched_img_path)
        else:
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

    def display_stitched_inline(self, img_path):
        """
        Replaces the right side of the Main tab with an inline stitched-image
        canvas + FOV overlay.  Also acts as the state-restoration path: called
        directly from display_main_tab when active_main_view == "stitched".

        Sets active_main_view = "stitched" and stores img_path so the view
        survives tab switches.  The Finish button resets both before returning
        to the default main view.

        Args:
            img_path (str): Absolute path to the stitched JPEG.
        """
        if not os.path.exists(img_path):
            print(f"display_stitched_inline: file not found — {img_path}")
            return

        # ── Persist state so tab navigation can restore this view ────────────
        self.active_main_view = "stitched"
        self.current_stitched_img_path = img_path

        grid_x = getattr(self, 'scanning_grid_x', 1)
        grid_y = getattr(self, 'scanning_grid_y', 1)

        # ── Rebuild right frame content ───────────────────────────────────────
        self.clear_frame(self.main_right_frame)
        self._roi_active_canvas = None   # detach any ROI from a previous view

        # Button bar
        btn_bar = ctk.CTkFrame(self.main_right_frame)
        btn_bar.pack(side=ctk.TOP, fill='x', padx=5, pady=(5, 0))

        # Finish — save files, reset state, return to default main view.
        # new_folder_path is evaluated now so the timestamp reflects when the
        # user clicked Finish, consistent with the rest of the codebase.
        new_folder_path = (
            f"{self.complete_stitching_folder}/"
            f"{self.curr_sample_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        )

        def _finish():
            self.active_main_view = "default"
            self.current_stitched_img_path = None
            self.display_main_tab()
            self.create_transfer_folder_pc(self.buffer_stitching_folder, new_folder_path)

        ctk.CTkButton(btn_bar, text="Finish", command=_finish).pack(
            side=ctk.RIGHT, padx=5, pady=3)

        # ── Inline stitched-image canvas with FOV overlay ─────────────────────
        try:
            stitched_pil = Image.open(img_path)
        except Exception as e:
            ctk.CTkLabel(self.main_right_frame,
                         text=f"Could not load image:\n{e}",
                         text_color="red").pack(expand=True)
            return

        stitched_w, stitched_h = stitched_pil.size
        # Persisted so _process_measurement_results can reconstruct canvas coords
        self._stitch_img_w = stitched_w
        self._stitch_img_h = stitched_h
        OVERLAP = 0.20

        tile_w = stitched_w / (1.0 + (grid_x - 1) * (1.0 - OVERLAP))
        tile_h = stitched_h / (1.0 + (grid_y - 1) * (1.0 - OVERLAP))
        step_px_y = tile_h * (1.0 - OVERLAP)

        # Tile 0 (bottom-left) physical position back-computed from the known
        # scan end position (top-right corner, captured on the last tile).
        # The RPi grid is: x_positions = range(min_x, max_x+step_x, step_x),
        # so max_x = min_x + (grid_x-1)*step_x  →  min_x = max_x - (grid_x-1)*step_x.
        scan_end_x  = getattr(self, 'scan_end_x', 0.0)
        scan_end_y  = getattr(self, 'scan_end_y', 0.0)
        step_x      = self.scanning_data.get('step_x', 1.0)
        step_y      = self.scanning_data.get('step_y', 1.0)
        scan_origin_x = scan_end_x - (grid_x - 1) * step_x
        scan_origin_y = scan_end_y - (grid_y - 1) * step_y

        # ── Physical FOV dimensions → stitched-pixel half-sizes ───────────────
        # These constants are used by _render() to size the rectangle and are
        # defined once here so they are accessible to the _render() closure.
        FOV_W_MM  = 5.60    # camera FOV width  in mm
        FOV_H_MM  = 4.20    # camera FOV height in mm
        SCALE_X   = 0.001479  # mm per pixel  |A11|
        SCALE_Y   = 0.001459  # mm per pixel  |A22|
        fov_half_w_px = (FOV_W_MM / SCALE_X) / 2.0   # half-width  in stitched pixels
        fov_half_h_px = (FOV_H_MM / SCALE_Y) / 2.0   # half-height in stitched pixels

        # ── Initial FOV centre: inverse-map current hardware position ─────────
        # Applies the same 2×2 matrix inverse used in
        # calculate_phys_to_stitched_pixel_coords, stopping before the canvas-
        # scale step since _s stores positions in full-res stitched pixels.
        A11, A12 = -0.001479,  0.000044
        A21, A22 =  0.000018,  0.001459
        det_B = A11 * A22 - A12 * A21          # = det(A)

        tile0_cx = tile_w / 2.0
        tile0_cy = (grid_y - 1) * step_px_y + tile_h / 2.0

        delta_x = float(self.x_pos) - scan_origin_x
        delta_y = float(self.y_pos) - scan_origin_y

        init_fov_px = tile0_cx + ((-A22) * delta_x + A12 * delta_y) / det_B
        init_fov_py = tile0_cy + ( A21   * delta_x - A11 * delta_y) / det_B

        _s = {
            'ox': 0.0, 'oy': 0.0,
            'sx': 1.0, 'sy': 1.0,
            'half_cw': 0.0, 'half_ch': 0.0,
            'fov_px': init_fov_px,   # hardware position at load time
            'fov_py': init_fov_py,
            'rect_id': None, 'label_id': None,
            'zoom': 1.0, 'pan_x': 0.0, 'pan_y': 0.0,
        }

        canvas = tk.Canvas(self.main_right_frame, bg="#1a1a1a",
                           highlightthickness=0, cursor="arrow")

        # ── ROI measurement control strip (BOTTOM, packed before canvas) ──────
        _stitch_strip = ctk.CTkFrame(self.main_right_frame)
        _stitch_strip.pack(side=ctk.BOTTOM, fill='x', padx=10, pady=(0, 5))

        _ss_row1 = ctk.CTkFrame(_stitch_strip)
        _ss_row1.pack(fill='x', padx=5, pady=(5, 2))

        ctk.CTkLabel(_ss_row1,
                     text="Ctrl+Drag: Draw  |  Drag Center: Move  |  Drag Corners: Resize",
                     font=("Arial", 11, "italic"), text_color="gray").pack(side="left", padx=(5, 20))

        ctk.CTkLabel(_ss_row1, text="Points (X × Y):").pack(side="left", padx=(0, 4))
        self._stitch_roi_spin_x = ctk.CTkEntry(_ss_row1, width=46)
        self._stitch_roi_spin_x.insert(0, "4")
        self._stitch_roi_spin_x.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(_ss_row1, text="×", font=("Arial", 12)).pack(side="left", padx=(0, 2))
        self._stitch_roi_spin_y = ctk.CTkEntry(_ss_row1, width=46)
        self._stitch_roi_spin_y.insert(0, "4")
        self._stitch_roi_spin_y.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(_ss_row1, text="Step Size (mm):").pack(side="left", padx=(0, 4))
        self._stitch_roi_cell_x = ctk.CTkEntry(_ss_row1, width=64)
        self._stitch_roi_cell_x.insert(0, "0.1000")
        self._stitch_roi_cell_x.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(_ss_row1, text="×", font=("Arial", 12)).pack(side="left", padx=(0, 2))
        self._stitch_roi_cell_y = ctk.CTkEntry(_ss_row1, width=64)
        self._stitch_roi_cell_y.insert(0, "0.1000")
        self._stitch_roi_cell_y.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(_ss_row1, text="Save As:").pack(side="left", padx=(0, 4))
        self._stitch_roi_csv_name = ctk.CTkEntry(_ss_row1, width=130, placeholder_text="filename.csv")
        self._stitch_roi_csv_name.pack(side="left", padx=(0, 5))

        # "Measure Heights" claims the far-right of row 1 (mirroring the Image tab)
        self._stitch_measure_heights_btn = ctk.CTkButton(
            _ss_row1, text="Measure Heights", fg_color="#1f6aa5",
            state="disabled", command=self.execute_custom_measurements)
        self._stitch_measure_heights_btn.pack(side="right", padx=(10, 5))

        # ── Row 2: info labels + analysis label + Clear Points / Map Surface ──────
        _ss_row2 = ctk.CTkFrame(_stitch_strip)
        _ss_row2.pack(fill='x', padx=5, pady=(2, 5))

        self._stitch_roi_info_area  = ctk.StringVar(value="Total Area: -- × -- mm")
        self._stitch_roi_info_count = ctk.StringVar(value="Total Points: --")
        self._stitch_roi_info_time  = ctk.StringVar(value="Est. Duration: -- s")

        # Action frame: Clear Points + Map Surface stacked on the far right
        _stitch_action_frame = ctk.CTkFrame(_ss_row2, fg_color="transparent")
        _stitch_action_frame.pack(side="right", padx=(10, 5))

        self._stitch_clear_points_btn = ctk.CTkButton(
            _stitch_action_frame, text="Clear Points", fg_color="#555555",
            state="disabled", command=self._clear_custom_points)
        self._stitch_clear_points_btn.pack(side="top", pady=(0, 2), fill="x")

        self._stitch_map_surface_btn = ctk.CTkButton(
            _stitch_action_frame, text="Map Surface", fg_color="#7B2FBE",
            state="disabled", command=self.start_surface_map_stitched)
        self._stitch_map_surface_btn.pack(side="top", pady=0, fill="x")

        ctk.CTkLabel(_ss_row2, textvariable=self._stitch_roi_info_time,
                     font=("Arial", 12, "bold"), text_color="orange").pack(side="right", padx=(12, 5))
        ctk.CTkLabel(_ss_row2, textvariable=self._stitch_roi_info_count,
                     font=("Arial", 12, "bold"), text_color="#00FF88").pack(side="right", padx=(12, 5))
        ctk.CTkLabel(_ss_row2, textvariable=self._stitch_roi_info_area).pack(side="right", padx=(12, 5))

        # Analysis readout — fixed width prevents frame resize on text change
        ctk.CTkLabel(_ss_row2, textvariable=self.analysis_result_var,
                     font=("Arial", 12, "bold"), text_color="#00CFFF",
                     width=260).pack(side="left", padx=(8, 5))

        canvas.pack(expand=True, fill="both", padx=5, pady=(5, 0))

        self.main_right_frame._stitch_img_tk = None
        self.main_right_frame._render_pending = False

        def _draw_fov():
            cx = _s['ox'] + _s['fov_px'] * _s['sx']
            cy = _s['oy'] + _s['fov_py'] * _s['sy']
            r_id = canvas.create_rectangle(
                cx - _s['half_cw'], cy - _s['half_ch'],
                cx + _s['half_cw'], cy + _s['half_ch'],
                outline="#00FF88", width=2, dash=(6, 3))
            l_id = canvas.create_text(
                cx - _s['half_cw'] + 4, cy - _s['half_ch'] + 4,
                anchor="nw", text="FOV", fill="#00FF88",
                font=("Arial", 10, "bold"))
            return r_id, l_id

        def _render():
            self.main_right_frame._render_pending = False
            canvas.delete("all")
            canvas.update_idletasks()
            cw = max(canvas.winfo_width(),  400)
            ch = max(canvas.winfo_height(), 400)

            # Base fit at zoom=1 (fit-to-canvas)
            if stitched_w / stitched_h > cw / ch:
                base_disp_w = cw
                base_disp_h = max(1, int(cw * stitched_h / stitched_w))
            else:
                base_disp_h = ch
                base_disp_w = max(1, int(ch * stitched_w / stitched_h))

            # Apply zoom and pan
            disp_w = max(1, int(base_disp_w * _s['zoom']))
            disp_h = max(1, int(base_disp_h * _s['zoom']))

            _s['ox'] = (cw - disp_w) / 2.0 + _s['pan_x']
            _s['oy'] = (ch - disp_h) / 2.0 + _s['pan_y']
            _s['sx'] = disp_w / stitched_w
            _s['sy'] = disp_h / stitched_h
            _s['half_cw'] = fov_half_w_px * _s['sx']   # physical FOV width  → canvas px
            _s['half_ch'] = fov_half_h_px * _s['sy']   # physical FOV height → canvas px

            resized = stitched_pil.resize((disp_w, disp_h), Image.LANCZOS)
            self.main_right_frame._stitch_img_tk = ImageTk.PhotoImage(resized)
            canvas.create_image(int(_s['ox'] + disp_w / 2.0), int(_s['oy'] + disp_h / 2.0),
                                anchor="center",
                                image=self.main_right_frame._stitch_img_tk)

            _s['rect_id'], _s['label_id'] = _draw_fov()

            # Reproject ROI grid using the fresh _s transform (zoom / pan safe)
            if (self._roi_active_canvas is canvas
                    and self.roi_phys_x_start is not None):
                _OVL = 0.20
                _tw  = stitched_w / (1.0 + (grid_x - 1) * (1.0 - _OVL))
                _th  = stitched_h / (1.0 + (grid_y - 1) * (1.0 - _OVL))
                _t0x = _tw / 2.0
                _t0y = (grid_y - 1) * _th * (1.0 - _OVL) + _th / 2.0
                _A11, _A12 = -0.001479, 0.000044
                _A21, _A22 =  0.000018, 0.001459
                _det = _A11 * _A22 - _A12 * _A21

                def _p2c(pm_x, pm_y):
                    dx = pm_x - scan_origin_x;  dy = pm_y - scan_origin_y
                    fpx = _t0x + ((-_A22) * dx + _A12 * dy) / _det
                    fpy = _t0y + ( _A21   * dx - _A11 * dy) / _det
                    return _s['ox'] + fpx * _s['sx'], _s['oy'] + fpy * _s['sy']

                cx0, cy0 = _p2c(self.roi_phys_x_start, self.roi_phys_y_start)
                cx1, cy1 = _p2c(self.roi_phys_x_end,   self.roi_phys_y_end)
                self._roi_canvas_x0 = min(cx0, cx1)
                self._roi_canvas_y0 = min(cy0, cy1)
                self._roi_canvas_x1 = max(cx0, cx1)
                self._roi_canvas_y1 = max(cy0, cy1)
                self._roi_redraw_grid(canvas,
                                      self._roi_canvas_x0, self._roi_canvas_y0,
                                      self._roi_canvas_x1, self._roi_canvas_y1)

            # Redraw any custom measurement points — zoom/pan safe via _s
            self._redraw_custom_points_stitched(
                canvas, _s, stitched_w, stitched_h,
                grid_x, grid_y, scan_origin_x, scan_origin_y)

        def _on_click(event):
            if self.module_status != "Idle":
                return

            full_px = (event.x - _s['ox']) / _s['sx']
            full_py = (event.y - _s['oy']) / _s['sy']

            target_x, target_y = self.calculate_stitched_phys_coords(
                full_px, full_py,
                stitched_w, stitched_h,
                grid_x, grid_y,
                scan_origin_x, scan_origin_y,
            )

            self.send_goto_command(target_x, target_y, float(self.z_pos),
                                   show_success=False)

            _s['fov_px'] = full_px
            _s['fov_py'] = full_py

            if _s['rect_id'] is not None and _s['label_id'] is not None:
                cx, cy = event.x, event.y
                canvas.coords(_s['rect_id'],
                               cx - _s['half_cw'], cy - _s['half_ch'],
                               cx + _s['half_cw'], cy + _s['half_ch'])
                canvas.coords(_s['label_id'],
                               cx - _s['half_cw'] + 4, cy - _s['half_ch'] + 4)
            else:
                _s['rect_id'], _s['label_id'] = _draw_fov()

        def _schedule_render(event=None):
            if not self.main_right_frame._render_pending:
                self.main_right_frame._render_pending = True
                self.main_right_frame.after(60, _render)

        def _start_pan(event):
            canvas._pan_start_x  = event.x
            canvas._pan_start_y  = event.y
            canvas._pan_origin_x = event.x   # total-distance anchor
            canvas._pan_origin_y = event.y

        def _do_pan(event):
            dx = event.x - canvas._pan_start_x
            dy = event.y - canvas._pan_start_y
            _s['pan_x'] += dx
            _s['pan_y'] += dy
            canvas._pan_start_x = event.x
            canvas._pan_start_y = event.y
            # Suppress renders for sub-5-px jitter so a right-click-to-drop-point
            # doesn't accidentally flash the canvas.
            total_drag = ((event.x - canvas._pan_origin_x) ** 2 +
                          (event.y - canvas._pan_origin_y) ** 2) ** 0.5
            if total_drag > 5:
                _schedule_render()

        def _zoom(event):
            cw = max(canvas.winfo_width(), 400)
            ch = max(canvas.winfo_height(), 400)

            # Recompute base fit dimensions (zoom=1)
            if stitched_w / stitched_h > cw / ch:
                base_disp_w = cw
                base_disp_h = max(1, int(cw * stitched_h / stitched_w))
            else:
                base_disp_h = ch
                base_disp_w = max(1, int(ch * stitched_w / stitched_h))

            # Stitched pixel under cursor before zoom changes
            img_x = (event.x - _s['ox']) / _s['sx']
            img_y = (event.y - _s['oy']) / _s['sy']

            factor = 1.1 if event.num == 4 else 1.0 / 1.1
            new_zoom = max(1.0, min(20.0, _s['zoom'] * factor))

            new_disp_w = base_disp_w * new_zoom
            new_disp_h = base_disp_h * new_zoom
            new_sx = new_disp_w / stitched_w
            new_sy = new_disp_h / stitched_h

            # Shift pan so the pixel under the cursor stays fixed
            _s['pan_x'] = event.x - img_x * new_sx - (cw - new_disp_w) / 2.0
            _s['pan_y'] = event.y - img_y * new_sy - (ch - new_disp_h) / 2.0
            _s['zoom']  = new_zoom

            # Snap back to centre when fully zoomed out
            if _s['zoom'] == 1.0:
                _s['pan_x'] = 0.0
                _s['pan_y'] = 0.0

            _schedule_render()

        # Bind entry KeyRelease now that canvas and _s exist
        for _se in (self._stitch_roi_spin_x, self._stitch_roi_spin_y,
                    self._stitch_roi_cell_x, self._stitch_roi_cell_y):
            _se.bind("<KeyRelease>",
                     lambda e, _c=canvas, _ss=_s: self._update_roi_from_entries_stitched(
                         e, _c, _ss, stitched_w, stitched_h,
                         grid_x, grid_y, scan_origin_x, scan_origin_y))

        canvas.bind("<Configure>",               _schedule_render)
        # <Button-1>: ROI corner / move / click-to-move dispatcher
        canvas.bind("<Button-1>",
                    lambda e: self._roi_or_move_press_stitched(e, canvas, _on_click))
        canvas.bind("<B1-Motion>",
                    lambda e: self._roi_pan_motion_stitched(e, canvas, _s))
        canvas.bind("<ButtonRelease-1>",
                    lambda e: self._roi_pan_release_stitched(
                        e, canvas, _s, stitched_w, stitched_h,
                        grid_x, grid_y, scan_origin_x, scan_origin_y))
        # Ctrl+drag draws a new grid
        canvas.bind("<Control-ButtonPress-1>",
                    lambda e: self._roi_press(e, canvas))
        canvas.bind("<Control-B1-Motion>",
                    lambda e: self._roi_drag(e, canvas))
        canvas.bind("<Control-ButtonRelease-1>",
                    lambda e: self._roi_release_stitched(
                        e, canvas, _s, stitched_w, stitched_h,
                        grid_x, grid_y, scan_origin_x, scan_origin_y))
        # Contextual hover cursors
        canvas.bind("<Motion>",               lambda e: self._on_canvas_motion(e, canvas))
        canvas.bind("<Enter>",                lambda e: canvas.focus_set())
        canvas.bind("<KeyPress-Control_L>",   lambda e: canvas.configure(cursor="crosshair"))
        canvas.bind("<KeyPress-Control_R>",   lambda e: canvas.configure(cursor="crosshair"))
        canvas.bind("<KeyRelease-Control_L>", lambda e: canvas.configure(cursor="arrow"))
        canvas.bind("<KeyRelease-Control_R>", lambda e: canvas.configure(cursor="arrow"))
        # Right-click: pan on drag, point-drop on clean release (no drag)
        canvas.bind("<ButtonPress-3>",  _start_pan)
        canvas.bind("<B3-Motion>",      _do_pan)
        canvas.bind("<ButtonRelease-3>",
                    lambda e, _c=canvas, _ss=_s: self._on_stitched_right_click_point(
                        e, _c, _ss, stitched_w, stitched_h,
                        grid_x, grid_y, scan_origin_x, scan_origin_y))
        canvas.bind("<Button-4>",      _zoom)
        canvas.bind("<Button-5>",      _zoom)
        # Poll until the canvas has real dimensions, then render once.
        # Avoids the race where winfo_width() still returns 1 even after <Map>.
        def _wait_for_geometry():
            if not canvas.winfo_exists():
                return
            if canvas.winfo_width() <= 10 or canvas.winfo_height() <= 10:
                self.after(50, _wait_for_geometry)
            else:
                _render()
        _wait_for_geometry()

    #------------------------------- Pop-up Windows ------------------------------------------#

    def open_sample_dialog(self):
        '''
        Pop-up window to enter in sample data parameters and then send to the Raspberry Pi.
        '''

        #Window setup
        sample_window = ctk.CTkToplevel(self)
        sample_window.title("Enter Sample Parameters")
        sample_window.geometry("330x520")
        sample_window.minsize(330, 520)
        sample_window.maxsize(330, 520)

        sample_window.wait_visibility()
        sample_window.grab_set()

        #Mount type (ie puck, stub), drop down menu
        ctk.CTkLabel(sample_window, text="Select your mount type:").grid(row = 0, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        mount_type = ctk.CTkComboBox(sample_window, values=["Puck", "Stub"])
        mount_type.grid(row = 1, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #Sample location (which stage to use), drop down menu
        ctk.CTkLabel(sample_window, text="Select your sample location:").grid(row = 2, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        sample_location = ctk.CTkComboBox(sample_window, values=["Module Stage", "SmarAct Stage"])
        sample_location.grid(row = 3, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #Sample id input field
        ctk.CTkLabel(sample_window, text="Enter Sample ID:").grid(row=4, column=0, columnspan=4, padx=1, pady=1, sticky="ew")
        sample_id = ctk.CTkEntry(sample_window, placeholder_text = "e.g. Sample_24_03_2025")
        sample_id.grid(row=5, column=0, columnspan=4, padx=10, pady=5)

        #Sample height input field
        ctk.CTkLabel(sample_window, text="Enter starting sample height (mm):").grid(row = 6, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        initial_height = ctk.CTkEntry(sample_window, placeholder_text = "e.g. 12.36")
        initial_height.grid(row = 7, column = 1, columnspan = 2, padx=1, pady=1, sticky="ew")

        #Sample layer height input field
        ctk.CTkLabel(sample_window, text="Enter sample layer height (mm):").grid(row = 8, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        ctk.CTkLabel(sample_window, text="(i.e. Amount of material removed each layer):").grid(row = 9, column = 0, columnspan = 4, pady=1, sticky = "ew")
        ctk.CTkLabel(sample_window, text="(For scanning enter 0.)", font=("Arial",10,"italic")).grid(row = 10, column = 0, columnspan = 4, padx=1, pady=1, sticky = "ew")
        layer_height = ctk.CTkEntry(sample_window, width = 50)
        layer_height.grid(row = 11, column = 1, columnspan = 2, padx=1, pady=5, sticky="ew")

        #Width for bounding box input field
        ctk.CTkLabel(sample_window, text="Enter bounding box size:").grid(row = 12, column = 0, columnspan = 4, padx=5, pady=1, sticky="ew")
        ctk.CTkLabel(sample_window, text="Width (mm):").grid(row=13, column=0, padx=1, pady=1, sticky = "e")
        sample_width = ctk.CTkEntry(sample_window, width = 50, placeholder_text = "e.g. 10")
        sample_width.grid(row = 13, column = 1, padx=5, pady=5, sticky = "w")

        #Length for bounding box input field
        ctk.CTkLabel(sample_window, text="Length (mm):").grid(row=13, column=2, padx=5, pady=5, sticky = "e")
        sample_length = ctk.CTkEntry(sample_window, width = 50, placeholder_text = "e.g. 10")
        sample_length.grid(row = 13, column = 3, padx=5, pady=10, sticky = "w")

        # OK button - closes the window and calls function send_sample_data() on OK
        ok_button = ctk.CTkButton(sample_window, text="OK",
                                  command=lambda: [self.send_sample_data(mount_type.get(), sample_location.get(), sample_id.get(),
                                                      float(initial_height.get()), float(layer_height.get()),
                                                      float(sample_width.get()), float(sample_length.get())),
                                                      sample_window.destroy()], width = 80)
        ok_button.grid(row = 14, column = 0, padx=5, pady=5)

        # Cancel button - closes window
        ctk.CTkButton(sample_window, text="Cancel", command=sample_window.destroy, width = 80).grid(row = 14, column = 3, columnspan = 2, padx=5, pady=5)

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

        image_sampling_window.wait_visibility()
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

        image_scanning_window.wait_visibility()
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
                                    self.empty_folder_pc(self.buffer_stitching_folder),
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

        homing_window.wait_visibility()
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

        # ----  SmarAct stage controls ----
        smaract_frame = ctk.CTkFrame(left_frame)
        smaract_frame.pack(side=ctk.TOP, fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            smaract_frame, text="SmarAct:", font=("Arial", 14, "bold")
        ).pack(pady=(8, 2), fill="x", padx=5)

        smaract_stage_btn = ctk.CTkButton(
            smaract_frame,
            text="Move to SmarAct",
            font=("Arial", 14),
            fg_color="blue",
            text_color="white",
            command=self.send_smaract_stage_command,
        )
        smaract_stage_btn.pack(pady=5, fill="x", padx=5)

        self.smaract_home_btn = ctk.CTkButton(
            smaract_frame,
            text="Homing",
            font=("Arial", 14),
            command=self._start_smaract_homing,
        )
        self.smaract_home_btn.pack(pady=5, fill="x", padx=5)
        # ---- End Middle Group ----

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



        # Preset-position button: Moves to a fixed position 
        preset_measure_btn = ctk.CTkButton(
            coord_frame,
            text="Send Preset Coordinates",
            font=("Arial", 14),
            fg_color="green",
            command=self.send_preset_measure_command
        )
        preset_measure_btn.grid(row=6, column=0, columnspan=3, padx=5, pady=5, sticky="ew")


        # Refresh coordinates button: Updates the entry boxes with the current motor positions
        refresh_coord_btn = ctk.CTkButton(coord_frame, text="Refresh Coordinates", font=("Arial", 14), command=self.refresh_motor_coord)
        refresh_coord_btn.grid(row=5,column=0,columnspan = 3, padx=5, pady=5, sticky="ew")

        # Additional Controls (Buttons)
        # Toggle button: Switch stage between interferometer and camera positions
        self.interferometer_toggle_btn = ctk.CTkButton(
            button_frame,
            text="Confocal",
            font=("Arial", 14),
            fg_color="green",
            command=self.toggle_interferometer_camera
        )
        self.interferometer_toggle_btn.pack(pady=5, fill='x')

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
                                                        self.show_image(self.buffer_testing_folder, self._image_tab_canvas)])
        display_image_btn.pack(side="left", padx=10, fill='x', expand=True)

        # Empty Raspberry Pi Image Buffer folder
        empty_buffer_rpi_btn = ctk.CTkButton(button_frame, text="Empty RPI Images", font=("Arial", 16), fg_color="grey",
                                            command=lambda: [self.empty_folder_rpi()])
        empty_buffer_rpi_btn.pack(side="left", padx=10, fill='x', expand=True)

        # Image canvas (replaces CTkLabel to support Region of Interest rectangle overlay
        self._image_tab_canvas = tk.Canvas(right_frame, bg="#2b2b2b", highlightthickness=0, cursor="arrow")
        self._image_tab_canvas.pack(expand=True, fill='both', pady=(20, 5))
        self._image_tab_canvas.create_text(200, 200, text="Image will appear here",
                                           fill="white", font=("Arial", 14),
                                           tags="placeholder_text")
        self._image_tab_canvas.bind(
            "<Configure>",
            lambda e: self._image_tab_canvas.coords(
                "placeholder_text", e.width / 2, e.height / 2))

        # ROI measurement control strip (two rows)
        self._roi_active_canvas = None   # reset on each Image tab load
        roi_strip = ctk.CTkFrame(right_frame)
        roi_strip.pack(fill='x', padx=10, pady=(0, 10))

        # ── Row 1: inputs (left) + Measure Heights (right) ───────────────────────
        row1 = ctk.CTkFrame(roi_strip)
        row1.pack(fill='x', padx=5, pady=(5, 2))

        # Measure Heights owns the far-right of row1; packed first to claim space
        self._measure_heights_btn = ctk.CTkButton(
            row1, text="Measure Heights", fg_color="#1E6FA8", state="disabled",
            command=self.execute_custom_measurements)
        self._measure_heights_btn.pack(side="right", padx=(10, 5))

        ctk.CTkLabel(row1, text="Ctrl+Drag: Draw  |  Drag Center: Move  |  Drag Corners: Resize",
                     font=("Arial", 11, "italic"), text_color="gray").pack(side="left", padx=(5, 20))

        # Points (X × Y)
        ctk.CTkLabel(row1, text="Points (X × Y):").pack(side="left", padx=(0, 4))
        self._roi_spin_x = ctk.CTkEntry(row1, width=46)
        self._roi_spin_x.insert(0, "4")
        self._roi_spin_x.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(row1, text="×", font=("Arial", 12)).pack(side="left", padx=(0, 2))
        self._roi_spin_y = ctk.CTkEntry(row1, width=46)
        self._roi_spin_y.insert(0, "4")
        self._roi_spin_y.pack(side="left", padx=(0, 16))

        # Step Size (mm)
        ctk.CTkLabel(row1, text="Step Size (mm):").pack(side="left", padx=(0, 4))
        self._roi_cell_x = ctk.CTkEntry(row1, width=64)
        self._roi_cell_x.insert(0, "0.1000")
        self._roi_cell_x.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(row1, text="×", font=("Arial", 12)).pack(side="left", padx=(0, 2))
        self._roi_cell_y = ctk.CTkEntry(row1, width=64)
        self._roi_cell_y.insert(0, "0.1000")
        self._roi_cell_y.pack(side="left", padx=(0, 16))

        # Save As
        ctk.CTkLabel(row1, text="Save As:").pack(side="left", padx=(0, 4))
        self._roi_csv_name = ctk.CTkEntry(row1, width=130, placeholder_text="filename.csv")
        self._roi_csv_name.pack(side="left", padx=(0, 5))

        # ── Row 2: info labels + Clear Points / Map Surface (right) ──────────────
        row2 = ctk.CTkFrame(roi_strip)
        row2.pack(fill='x', padx=5, pady=(2, 5))

        self._roi_info_area  = ctk.StringVar(value="Total Area: -- × -- mm")
        self._roi_info_count = ctk.StringVar(value="Total Points: --")
        self._roi_info_time  = ctk.StringVar(value="Est. Duration: -- s")

        # Action frame: Clear Points + Map Surface stacked on the far right.
        # Packed first so it claims the rightmost column; labels fill to the left.
        _action_frame = ctk.CTkFrame(row2, fg_color="transparent")
        _action_frame.pack(side="right", padx=(10, 5))

        self._clear_points_btn = ctk.CTkButton(
            _action_frame, text="Clear Points", fg_color="#555555", state="disabled",
            command=self._clear_custom_points)
        self._clear_points_btn.pack(side="top", pady=(0, 2), fill="x")

        self._map_surface_btn = ctk.CTkButton(
            _action_frame, text="Map Surface", fg_color="#7B2FBE",
            state="disabled", command=self.start_surface_map)
        self._map_surface_btn.pack(side="top", pady=0, fill="x")

        ctk.CTkLabel(row2, textvariable=self._roi_info_time,
                     font=("Arial", 12, "bold"), text_color="orange").pack(side="right", padx=(12, 5))

        ctk.CTkLabel(row2, textvariable=self._roi_info_count,
                     font=("Arial", 12, "bold"), text_color="#00FF88").pack(side="right", padx=(12, 5))

        ctk.CTkLabel(row2, textvariable=self._roi_info_area).pack(side="right", padx=(12, 5))

        # Analysis result — fixed width prevents frame resize on text change
        self.analysis_result_var = ctk.StringVar(value="Analysis: Select points...")
        ctk.CTkLabel(row2, textvariable=self.analysis_result_var,
                     font=("Arial", 12, "bold"), text_color="#00CFFF",
                     width=260).pack(side="left", padx=(8, 5))

        # Bind live updates: any keystroke in the dimension entries redraws the grid
        for _e in (self._roi_spin_x, self._roi_spin_y, self._roi_cell_x, self._roi_cell_y):
            _e.bind("<KeyRelease>", self._update_roi_from_entries)

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

        if isinstance(image_label, tk.Canvas):
            self._show_image_on_canvas(image_folder, image_label)
            return

        try:
            # Get the .jpg files in the folder
            image_files = [f for f in sorted(os.listdir(image_folder)) if f.lower().endswith('.jpg')]
            
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

            # Make image label clickable to expand the image (double click)
            image_label.bind("<Double-Button-1>", lambda e: self.expand_image(image_path))
            # Make the image label clickable to move the stage (single click)
            image_label.bind("<Button-1>", lambda e: self.click_to_move(e, new_width, new_height, img_pil.width, img_pil.height))


            # Hide the "Image will appear here" text
            image_label.configure(text="")  # Clear the text

            print("Image updated successfully :)")
            
        except Exception as e:
            print(f"Error displaying image: {e}")
            image_label.configure(text="Failed to display image", fg_color="red")

    def click_to_move(self, event, img_disp_width, img_disp_height, orig_img_width, orig_img_height):
        """
        Translates image clicks into stage movement
        """
        if event.state & 0x0004:  # Ctrl held — ROI draw mode, not a move command
            return
        if getattr(self, '_roi_pan_active', False):  # ROI box drag in progress
            return
        if self.module_status != "Idle":
            return
        
        # Get current label dimensions (in case window is resized)
        label_width = event.widget.winfo_width()
        label_height = event.widget.winfo_height()
        
        # Calculate image padding
        x_offset = (label_width - img_disp_width) / 2.0
        y_offset = (label_height - img_disp_height) / 2.0

        # Adjust coordinates to be relative to the image
        img_click_x = event.x - x_offset
        img_click_y = event.y - y_offset

        # Ignore clicks on gray padding around image
        if img_click_x < 0 or img_click_x > img_disp_width or img_click_y < 0 or img_click_y > img_disp_height:
            return

        # Scales click to the sensor resolution 
        i_click = img_click_x * (orig_img_width / img_disp_width)
        j_click = img_click_y * (orig_img_height / img_disp_height)

        # Calculate distance from the mathematical center of the sensor
        i_center = orig_img_width / 2.0
        j_center = orig_img_height / 2.0

        delta_i = i_center - i_click
        delta_j = j_center - j_click

        # Apply transformation matrix
        A11, A12 = -0.001479, 0.000044
        A21, A22 =  0.000018, 0.001459

        delta_x = (A11 * delta_i) + (A12 * delta_j)
        delta_y = (A21 * delta_i) + (A22 * delta_j)

        # Calculate new target position (using current positions tracked from the Raspberry Pi)
        target_x = float(self.x_pos) + delta_x
        target_y = float(self.y_pos) + delta_y
        current_z = float(self.z_pos)

        # Prevent sending negative coordinates that could crash the stage into limits
        target_x = max(0.0, target_x)
        target_y = max(0.0, target_y)

        

        # Send command
        print(f"Moving stage to X: {target_x:.4f}, Y: {target_y:.4f}")
        self.send_goto_command(target_x, target_y, current_z, show_success=False)

        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 0.5

        self.sequence_wait_for_move(event.widget)

    # -------------------- Canvas Image Display (Image Tab) -------------------- #

    def _show_image_on_canvas(self, image_folder, canvas):
        """
        Displays an image on a tk.Canvas, binding click-to-move, double-click expand,
        and Ctrl+drag ROI selection on top of the image.
        """
        try:
            image_files = [f for f in sorted(os.listdir(image_folder)) if f.lower().endswith('.jpg')]

            if not image_files:
                canvas.delete("all")
                cw = max(canvas.winfo_width(), 200)
                ch = max(canvas.winfo_height(), 200)
                canvas.create_text(cw // 2, ch // 2, text="No .jpg files found",
                                   fill="red", font=("Arial", 14))
                print("Error: No .jpg files found in the specified folder.")
                return

            image_path = os.path.normpath(os.path.join(image_folder, image_files[0]))
            self._canvas_img_path = image_path
            img_pil = Image.open(image_path)

            # PIL is open; defer canvas drawing until geometry is ready.
            def _wait_for_geometry():
                if not canvas.winfo_exists():
                    return
                if canvas.winfo_width() <= 10 or canvas.winfo_height() <= 10:
                    self.after(50, _wait_for_geometry)
                    return

                canvas_w = canvas.winfo_width()
                canvas_h = canvas.winfo_height()

                aspect_ratio = img_pil.width / img_pil.height
                if aspect_ratio > 1:
                    new_width  = canvas_w
                    new_height = int(canvas_w / aspect_ratio)
                else:
                    new_height = canvas_h
                    new_width  = int(canvas_h * aspect_ratio)

                new_width  = max(new_width, 1)
                new_height = max(new_height, 1)

                self._canvas_disp_w = new_width
                self._canvas_disp_h = new_height
                self._canvas_orig_w = img_pil.width
                self._canvas_orig_h = img_pil.height
                # Capture hardware position so _phys_to_canvas_pixel has a stable
                # reference even if the stage moves before the next redraw.
                self._image_tab_ref_x = float(self.x_pos)
                self._image_tab_ref_y = float(self.y_pos)

                resized_img = img_pil.resize((new_width, new_height), Image.LANCZOS)
                self._canvas_img_tk = ImageTk.PhotoImage(resized_img)

                canvas.delete("all")
                canvas.create_image(canvas_w // 2, canvas_h // 2, anchor="center",
                                    image=self._canvas_img_tk)

                # Redraw any custom measurement points that survived the canvas wipe
                self._redraw_custom_points_image_tab(canvas, canvas_w, canvas_h)

                canvas.bind("<Double-Button-1>", lambda e: self.expand_image(image_path))
                # <Button-1> dispatches to pan-drag (if inside ROI box) or click-to-move
                canvas.bind("<Button-1>",        lambda e: self._roi_or_move_press(
                    e, canvas, new_width, new_height, img_pil.width, img_pil.height))
                canvas.bind("<B1-Motion>",        lambda e: self._roi_pan_motion(e, canvas))
                canvas.bind("<ButtonRelease-1>",  lambda e: self._roi_pan_release(e, canvas))
                canvas.bind("<Control-ButtonPress-1>",   lambda e: self._roi_press(e, canvas))
                canvas.bind("<Control-B1-Motion>",        lambda e: self._roi_drag(e, canvas))
                canvas.bind("<Control-ButtonRelease-1>", lambda e: self._roi_release(e, canvas))

                canvas.bind("<Motion>",               lambda e: self._on_canvas_motion(e, canvas))
                canvas.bind("<Enter>",                lambda e: canvas.focus_set())
                canvas.bind("<KeyPress-Control_L>",   lambda e: canvas.configure(cursor="crosshair"))
                canvas.bind("<KeyPress-Control_R>",   lambda e: canvas.configure(cursor="crosshair"))
                canvas.bind("<KeyRelease-Control_L>", lambda e: canvas.configure(cursor="arrow"))
                canvas.bind("<KeyRelease-Control_R>", lambda e: canvas.configure(cursor="arrow"))

                canvas.bind("<Button-3>", lambda e: self._on_right_click_point(e, canvas))

                print("Image updated successfully :)")

            _wait_for_geometry()

        except Exception as e:
            print(f"Error displaying image on canvas: {e}")

    def _canvas_pixel_to_phys(self, canvas_px, canvas_py, canvas_w, canvas_h):
        """
        Converts a canvas pixel position to physical stage mm coordinates using
        the same matrix as click_to_move.
        """
        if self._canvas_disp_w == 0 or self._canvas_disp_h == 0:
            return None, None

        x_offset = (canvas_w - self._canvas_disp_w) / 2.0
        y_offset = (canvas_h - self._canvas_disp_h) / 2.0

        sensor_x = (canvas_px - x_offset) * (self._canvas_orig_w / self._canvas_disp_w)
        sensor_y = (canvas_py - y_offset) * (self._canvas_orig_h / self._canvas_disp_h)

        i_center = self._canvas_orig_w / 2.0
        j_center = self._canvas_orig_h / 2.0

        delta_i = i_center - sensor_x
        delta_j = j_center - sensor_y

        A11, A12 = -0.001479, 0.000044
        A21, A22 =  0.000018, 0.001459

        phys_x = float(self.x_pos) + A11 * delta_i + A12 * delta_j
        phys_y = float(self.y_pos) + A21 * delta_i + A22 * delta_j

        return max(0.0, phys_x), max(0.0, phys_y)

    def calculate_stitched_phys_coords(
        self,
        px: float,
        py: float,
        stitched_w: int,
        stitched_h: int,
        grid_x: int,
        grid_y: int,
        scan_origin_x: float,
        scan_origin_y: float,
    ) -> tuple:
        """
        Convert a pixel position on the full-resolution stitched image to
        absolute physical stage coordinates (mm).

        The stitched image is produced by Fiji using:
          - "Grid: column-by-column, Up & Right" scan order
          - 20 % tile overlap

        Parameters
        ----------
        px, py           : click in full-resolution stitched image pixels
                           (0, 0 = top-left corner)
        stitched_w/h     : pixel dimensions of the full-resolution stitched image
        grid_x, grid_y   : number of tile columns and rows (e.g. step_x=5, step_y=4)
        scan_origin_x/y  : absolute stage coordinates (mm) at the moment tile 0
                           was captured — the stage position at scan start.
                           NOTE: caller must capture self.x_pos / self.y_pos
                           before sending the scan command and pass them here.

        Returns
        -------
        (target_x, target_y) : absolute stage coordinates in mm, clamped to ≥ 0.
        """
        OVERLAP = 0.20

        # Scale factors from the single-frame calibration matrix (diagonal terms).
        # A11 = -0.001479 → 1 px rightward in sensor = +0.001479 mm in X.
        # A22 =  0.001459 → 1 px upward   in sensor = +0.001459 mm in Y.
        # Cross-terms (A12=0.000044, A21=0.000018) are ~3 % of the diagonals
        # and are negligible at the stitched-image scale.
        SCALE_X = 0.001479  # mm per pixel, right  → +X stage
        SCALE_Y = 0.001459  # mm per pixel, upward → +Y stage

        # ── Step 1: Recover individual tile pixel dimensions ─────────────────
        # Fiji places N tiles with (1-overlap) steps:
        #   stitched_size = tile_size * (1 + (N-1) * (1 - overlap))
        tile_w = stitched_w / (1.0 + (grid_x - 1) * (1.0 - OVERLAP))
        tile_h = stitched_h / (1.0 + (grid_y - 1) * (1.0 - OVERLAP))

        # Pixel distance between adjacent tile left-/top-edges in the stitched image
        step_px_x = tile_w * (1.0 - OVERLAP)
        step_px_y = tile_h * (1.0 - OVERLAP)

        # ── Step 2: Tile-0 centre in stitched image coordinates ──────────────
        # "Up & Right" → tile 0 is the physical bottom-left of the scan area.
        # In the stitched image (y=0 at top), the physically-lowest row (row 0)
        # sits at the largest y values — its top edge is at (grid_y-1)*step_px_y.
        tile0_cx = tile_w / 2.0
        tile0_cy = (grid_y - 1) * step_px_y + tile_h / 2.0

        # ── Step 3: Pixel displacement from tile-0 centre ────────────────────
        d_px = px - tile0_cx   # positive = rightward in image = +X stage
        d_py = py - tile0_cy   # positive = downward  in image = −Y stage

        # ── Step 4: Convert pixel displacement → physical mm ─────────────────
        delta_x =  d_px * SCALE_X   # right  → +X
        delta_y = -d_py * SCALE_Y   # down   → −Y  (sign flip)

        # ── Step 5: Absolute stage coordinates with hardware safety clamp ─────
        target_x = max(0.0, scan_origin_x + delta_x)
        target_y = max(0.0, scan_origin_y + delta_y)

        return target_x, target_y

    def calculate_phys_to_stitched_pixel_coords(
        self,
        phys_x: float,
        phys_y: float,
        stitched_w: int,
        stitched_h: int,
        grid_x: int,
        grid_y: int,
        scan_origin_x: float,
        scan_origin_y: float,
        canvas_w: int,
        canvas_h: int,
    ) -> tuple:
        """
        Inverse of calculate_stitched_phys_coords.

        Converts an absolute physical stage position (mm) to the canvas pixel
        that corresponds to that location on the displayed stitched image.
        Used to position the FOV rectangle at the camera's current location
        when the stitched image first loads.

        Mathematical derivation
        -----------------------
        The single-frame calibration matrix A maps sensor-pixel offsets to
        stage-mm offsets:

            [delta_x]   [A11  A12] [δi]
            [delta_y] = [A21  A22] [δj]

        where δi = i_centre − i_click (+left) and δj = j_centre − j_click (+up).

        In stitched-image space the displacement from the tile-0 centre is:
            d_px = px − tile0_cx  (+right)
            d_py = py − tile0_cy  (+down)

        Because right-in-image ↔ i_click > i_centre we have δi = −d_px and
        δj = −d_py, giving an effective matrix B = −A (stitched-axis form):

            [delta_x]   [−A11  −A12] [d_px]
            [delta_y] = [−A21  −A22] [d_py]

        Inverting analytically (2×2 formula: inv = (1/det)·[[d,−b],[−c,a]]):

            det(B) = (−A11)(−A22) − (−A12)(−A21) = A11·A22 − A12·A21

            [d_px]             1    [−A22   A12] [delta_x]
            [d_py] = ─────────── · [ A21  −A11] [delta_y]
                     A11·A22−A12·A21

        Cross-terms are included for full accuracy (they were dropped in the
        forward function for negligibility, but the inverse is used to set an
        initial visual position where precision matters more).

        Parameters
        ----------
        phys_x, phys_y       : absolute stage coordinates in mm
        stitched_w/h         : full-resolution pixel dimensions of the stitched image
        grid_x, grid_y       : number of tile columns and rows
        scan_origin_x/y      : stage coordinates when tile 0 was captured
        canvas_w, canvas_h   : current canvas dimensions in pixels
                               (pass canvas.winfo_width() / winfo_height())

        Returns
        -------
        (canvas_px, canvas_py) : canvas pixel coordinates for the physical position.
                                 May lie outside [0, canvas_w] × [0, canvas_h] when
                                 the position is outside the scanned area — no
                                 boundary clamping is applied (edge-behaviour rule).
        """
        OVERLAP = 0.20

        # ── Step 1: Tile geometry — identical to the forward function ─────────
        tile_w = stitched_w / (1.0 + (grid_x - 1) * (1.0 - OVERLAP))
        tile_h = stitched_h / (1.0 + (grid_y - 1) * (1.0 - OVERLAP))
        step_px_y = tile_h * (1.0 - OVERLAP)

        # Tile-0 centre in full-resolution stitched pixels
        # ("Up & Right" → tile 0 is physical bottom-left, largest y in image)
        tile0_cx = tile_w / 2.0
        tile0_cy = (grid_y - 1) * step_px_y + tile_h / 2.0

        # ── Step 2: Physical displacement from scan origin ────────────────────
        delta_x = phys_x - scan_origin_x   # mm, +X stage direction
        delta_y = phys_y - scan_origin_y   # mm, +Y stage direction

        # ── Step 3: Invert B = −A to recover stitched-pixel displacement ──────
        # Calibration matrix constants (same values used everywhere in the file)
        A11, A12 = -0.001479,  0.000044
        A21, A22 =  0.000018,  0.001459

        # det(B) = det(−A) = det(A) = A11·A22 − A12·A21
        det_B = A11 * A22 - A12 * A21

        # B⁻¹ analytically: (1/det)·[[ −A22,  A12],
        #                             [  A21, −A11]]
        d_px = ((-A22) * delta_x + A12 * delta_y) / det_B   # px, +right in image
        d_py = ( A21   * delta_x - A11 * delta_y) / det_B   # px, +down  in image

        # ── Step 4: Full-resolution stitched image pixel ──────────────────────
        full_px = tile0_cx + d_px
        full_py = tile0_cy + d_py

        # ── Step 5: Canvas display layout (mirrors _render in display_stitched_inline)
        if stitched_w / stitched_h > canvas_w / canvas_h:
            disp_w = canvas_w
            disp_h = max(1, int(canvas_w * stitched_h / stitched_w))
        else:
            disp_h = canvas_h
            disp_w = max(1, int(canvas_h * stitched_w / stitched_h))

        ox = (canvas_w - disp_w) / 2.0   # image left edge on canvas
        oy = (canvas_h - disp_h) / 2.0   # image top  edge on canvas
        sx = disp_w / stitched_w
        sy = disp_h / stitched_h

        # ── Step 6: Canvas pixel (no boundary clamp) ──────────────────────────
        canvas_px = ox + full_px * sx
        canvas_py = oy + full_py * sy

        return canvas_px, canvas_py

    def _safe_btn(self, attr_name, **kw):
        """Configure a CTk button widget only if it still exists in the widget tree.
        Prevents TclError when stitched-view buttons are configured after the frame
        they live in has been destroyed by clear_frame / view switching."""
        try:
            w = getattr(self, attr_name, None)
            if w is not None and w.winfo_exists():
                w.configure(**kw)
        except Exception:
            pass

    def _roi_press(self, event, canvas):
        """Begin a new Ctrl+drag ROI — clears the previous grid."""
        self._roi_drag_start = (event.x, event.y)
        canvas.delete("roi_grid")
        self._roi_active_canvas = canvas
        canvas.configure(cursor="crosshair")
        for _ms in ('_map_surface_btn', '_stitch_map_surface_btn'):
            self._safe_btn(_ms, state="disabled")

    def _roi_drag(self, event, canvas):
        """Live-redraw the measurement grid as the user drags."""
        if self._roi_drag_start is None:
            return
        x0, y0 = self._roi_drag_start
        self._roi_redraw_grid(canvas, x0, y0, event.x, event.y)

    def _roi_release(self, event, canvas):
        """Finalise ROI: store normalised canvas coords, compute physical mm bounds,
        sync the cell-size entries (Canvas → UI), and update info labels."""
        if self._roi_drag_start is None:
            return

        x0, y0 = self._roi_drag_start
        x1, y1 = event.x, event.y
        self._roi_drag_start = None

        # Normalise so x0 < x1, y0 < y1
        self._roi_canvas_x0 = min(x0, x1)
        self._roi_canvas_y0 = min(y0, y1)
        self._roi_canvas_x1 = max(x0, x1)
        self._roi_canvas_y1 = max(y0, y1)

        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        px0, py0 = self._canvas_pixel_to_phys(self._roi_canvas_x0, self._roi_canvas_y0, canvas_w, canvas_h)
        px1, py1 = self._canvas_pixel_to_phys(self._roi_canvas_x1, self._roi_canvas_y1, canvas_w, canvas_h)

        if px0 is None or px1 is None:
            print("ROI: display an image first before selecting a region.")
            return

        self.roi_phys_x_start = min(px0, px1)
        self.roi_phys_x_end   = max(px0, px1)
        self.roi_phys_y_start = min(py0, py1)
        self.roi_phys_y_end   = max(py0, py1)

        # Canvas → UI: update cell-size entries from the dragged physical extent
        phys_w = self.roi_phys_x_end - self.roi_phys_x_start
        phys_h = self.roi_phys_y_end - self.roi_phys_y_start
        try:
            nx = max(2, int(self._roi_spin_x.get()))
            ny = max(2, int(self._roi_spin_y.get()))
        except (ValueError, AttributeError):
            nx, ny = 4, 4
        self.map_grid_x = nx
        self.map_grid_y = ny
        if hasattr(self, '_roi_cell_x') and nx > 1:
            self._roi_cell_x.delete(0, "end")
            self._roi_cell_x.insert(0, f"{phys_w / (nx - 1):.4f}")
        if hasattr(self, '_roi_cell_y') and ny > 1:
            self._roi_cell_y.delete(0, "end")
            self._roi_cell_y.insert(0, f"{phys_h / (ny - 1):.4f}")

        self._roi_redraw_grid(canvas, self._roi_canvas_x0, self._roi_canvas_y0,
                              self._roi_canvas_x1, self._roi_canvas_y1)
        self._update_roi_info_labels()
        self._safe_btn('_map_surface_btn', state="normal")
        self._safe_btn('_clear_points_btn', state="normal")
        print(f"ROI selected: X=[{self.roi_phys_x_start:.4f}, {self.roi_phys_x_end:.4f}] mm  "
              f"Y=[{self.roi_phys_y_start:.4f}, {self.roi_phys_y_end:.4f}] mm  "
              f"Grid={nx}×{ny}")
        # Ctrl is still held at this point; restore once the key is released.
        # The <KeyRelease-Control_L/R> binding will set cursor="arrow", and the
        # next <Motion> event will refine it to the correct zone cursor.
        canvas.configure(cursor="crosshair")

    # ──────────────────────────────────────────────────────────────────────────
    # Custom point-selection (right-click markers)
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_custom_pt_marker(self, canvas, cx, cy):
        """Draw the standard yellow crosshair + red dot at canvas position (cx, cy)."""
        R = 8
        canvas.create_line(cx - R, cy, cx + R, cy,
                           fill="#FFE000", width=2, tags="custom_pt")
        canvas.create_line(cx, cy - R, cx, cy + R,
                           fill="#FFE000", width=2, tags="custom_pt")
        canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                           fill="#FF4500", outline="#FFE000", width=1, tags="custom_pt")

    def _redraw_custom_points_image_tab(self, canvas, canvas_w, canvas_h):
        """Re-stamp all custom_measure_points and measured_data text on the Image
        tab canvas after a canvas.delete('all').  Uses _image_tab_ref_x/y as the
        stable camera-position anchor so the inverse transform is consistent."""
        if not self.custom_measure_points:
            return
        ref_x = getattr(self, '_image_tab_ref_x', float(self.x_pos))
        ref_y = getattr(self, '_image_tab_ref_y', float(self.y_pos))
        measured_indices = {i for i, _ in enumerate(self.measured_data)}
        for i, (phys_x, phys_y) in enumerate(self.custom_measure_points):
            cx, cy = self._phys_to_canvas_pixel(phys_x, phys_y, ref_x, ref_y,
                                                canvas_w, canvas_h)
            if cx is None:
                continue
            self._draw_custom_pt_marker(canvas, cx, cy)
        # Re-draw height text for any completed measurements
        for i, (phys_x, phys_y, height) in enumerate(self.measured_data):
            cx, cy = self._phys_to_canvas_pixel(phys_x, phys_y, ref_x, ref_y,
                                                canvas_w, canvas_h)
            if cx is None:
                continue
            fill = "#00FF44" if i in self.analysis_selected_indices else "cyan"
            canvas.create_text(cx, cy - 15, text=f"{height:.3f} mm",
                               fill=fill, font=("Arial", 12, "bold"),
                               tags=("custom_pt", "measurement_text", f"meas_idx_{i}"))
        if self.measured_data:
            canvas.tag_bind("measurement_text", "<Button-1>", self._toggle_analysis_point)

    def _redraw_custom_points_stitched(self, canvas, _s,
                                       stitched_w, stitched_h,
                                       grid_x, grid_y,
                                       scan_origin_x, scan_origin_y):
        """Re-stamp all custom_measure_points and measured_data text on the
        stitched canvas after canvas.delete('all').  Uses _s directly so markers
        remain correct at any zoom/pan level."""
        if not self.custom_measure_points and not self.measured_data:
            return

        # Tile-0 centre in full-res stitched pixels (same constants as _render)
        OVERLAP = 0.20
        _tile_w = stitched_w / (1.0 + (grid_x - 1) * (1.0 - OVERLAP))
        _tile_h = stitched_h / (1.0 + (grid_y - 1) * (1.0 - OVERLAP))
        _t0x = _tile_w / 2.0
        _t0y = (grid_y - 1) * _tile_h * (1.0 - OVERLAP) + _tile_h / 2.0
        _A11, _A12 = -0.001479,  0.000044
        _A21, _A22 =  0.000018,  0.001459
        _det_B = _A11 * _A22 - _A12 * _A21

        def _phys_to_canvas(phys_x, phys_y):
            dx = phys_x - scan_origin_x
            dy = phys_y - scan_origin_y
            d_px = ((-_A22) * dx + _A12 * dy) / _det_B
            d_py = ( _A21   * dx - _A11 * dy) / _det_B
            fpx = _t0x + d_px
            fpy = _t0y + d_py
            return _s['ox'] + fpx * _s['sx'], _s['oy'] + fpy * _s['sy']

        # Crosshair markers (only for points not yet in measured_data)
        measured_set = set(range(len(self.measured_data)))
        for i, (phys_x, phys_y) in enumerate(self.custom_measure_points):
            cx, cy = _phys_to_canvas(phys_x, phys_y)
            self._draw_custom_pt_marker(canvas, cx, cy)

        # Height text (measured_data is in optimised order; use its own phys coords)
        for i, (phys_x, phys_y, height) in enumerate(self.measured_data):
            cx, cy = _phys_to_canvas(phys_x, phys_y)
            fill = "#00FF44" if i in self.analysis_selected_indices else "cyan"
            canvas.create_text(cx, cy - 15, text=f"{height:.3f} mm",
                               fill=fill, font=("Arial", 12, "bold"),
                               tags=("custom_pt", "measurement_text", f"meas_idx_{i}"))

        if self.measured_data:
            canvas.tag_bind("measurement_text", "<Button-1>", self._toggle_analysis_point)

    def _on_right_click_point(self, event, canvas):
        """<Button-3>: drop a measurement marker at the clicked canvas position."""
        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        phys_x, phys_y = self._canvas_pixel_to_phys(event.x, event.y, canvas_w, canvas_h)
        if phys_x is None or phys_y is None:
            return

        self.custom_measure_points.append((phys_x, phys_y))
        self._roi_active_canvas = canvas   # ensure Clear Points can find this canvas

        # Draw a bright yellow crosshair at the clicked position
        R = 8
        canvas.create_line(event.x - R, event.y, event.x + R, event.y,
                           fill="#FFE000", width=2, tags="custom_pt")
        canvas.create_line(event.x, event.y - R, event.x, event.y + R,
                           fill="#FFE000", width=2, tags="custom_pt")
        canvas.create_oval(event.x - 3, event.y - 3, event.x + 3, event.y + 3,
                           fill="#FF4500", outline="#FFE000", width=1, tags="custom_pt")

        self._safe_btn('_measure_heights_btn', state="normal")
        self._safe_btn('_clear_points_btn', state="normal")

        print(f"[custom_pt] point {len(self.custom_measure_points)}: "
              f"({phys_x:.4f} mm, {phys_y:.4f} mm)")

    def _on_stitched_right_click_point(self, event, canvas, _s,
                                       stitched_w, stitched_h,
                                       grid_x, grid_y,
                                       scan_origin_x, scan_origin_y):
        """<ButtonRelease-3> handler for the stitched canvas.

        Drops a custom measurement marker only when the release follows a clean
        right-click (no significant pan drag).  Converts canvas pixels → full
        stitched-image pixels → physical mm using the standard helper.
        """
        # Ignore if the user was panning (drag threshold = 5 px)
        start_x = getattr(canvas, '_pan_start_x', event.x)
        start_y = getattr(canvas, '_pan_start_y', event.y)
        if abs(event.x - start_x) > 5 or abs(event.y - start_y) > 5:
            return

        # Canvas px → full-res stitched px → physical mm
        full_px = (event.x - _s['ox']) / _s['sx']
        full_py = (event.y - _s['oy']) / _s['sy']
        phys_x, phys_y = self.calculate_stitched_phys_coords(
            full_px, full_py,
            stitched_w, stitched_h,
            grid_x, grid_y,
            scan_origin_x, scan_origin_y,
        )

        self.custom_measure_points.append((phys_x, phys_y))
        self._roi_active_canvas = canvas

        # Draw yellow crosshair marker at the canvas click position
        R = 8
        canvas.create_line(event.x - R, event.y, event.x + R, event.y,
                           fill="#FFE000", width=2, tags="custom_pt")
        canvas.create_line(event.x, event.y - R, event.x, event.y + R,
                           fill="#FFE000", width=2, tags="custom_pt")
        canvas.create_oval(event.x - 3, event.y - 3, event.x + 3, event.y + 3,
                           fill="#FF4500", outline="#FFE000", width=1, tags="custom_pt")

        # Enable action buttons
        for btn_name in ('_stitch_measure_heights_btn', '_stitch_clear_points_btn',
                         '_measure_heights_btn', '_clear_points_btn'):
            self._safe_btn(btn_name, state="normal")

        print(f"[custom_pt/stitched] point {len(self.custom_measure_points)}: "
              f"({phys_x:.4f} mm, {phys_y:.4f} mm)")

    def _clear_custom_points(self):
        """Universal canvas clear: wipes right-click measurement points AND the
        Ctrl+Drag ROI grid, resetting all related state and UI to neutral."""
        # ── Measurement point state ───────────────────────────────────────────
        self.custom_measure_points.clear()
        self.measured_data.clear()
        self.analysis_selected_indices.clear()
        if hasattr(self, 'analysis_result_var'):
            self.analysis_result_var.set("Analysis: Select points...")

        # ── ROI grid state ────────────────────────────────────────────────────
        self.roi_phys_x_start = None
        self.roi_phys_x_end   = None
        self.roi_phys_y_start = None
        self.roi_phys_y_end   = None
        self._roi_canvas_x0 = 0.0
        self._roi_canvas_y0 = 0.0
        self._roi_canvas_x1 = 0.0
        self._roi_canvas_y1 = 0.0

        # ── Canvas visuals ────────────────────────────────────────────────────
        if self._roi_active_canvas is not None:
            self._roi_active_canvas.tag_unbind("measurement_text", "<Button-1>")
            self._roi_active_canvas.delete("custom_pt")
            self._roi_active_canvas.delete("roi_grid")

        # ── Info label readouts → neutral dashes ─────────────────────────────
        for _var, _val in (
            ('_roi_info_area',        "Total Area: -- × -- mm"),
            ('_roi_info_count',       "Total Points: --"),
            ('_roi_info_time',        "Est. Duration: -- s"),
            ('_stitch_roi_info_area', "Total Area: -- × -- mm"),
            ('_stitch_roi_info_count',"Total Points: --"),
            ('_stitch_roi_info_time', "Est. Duration: -- s"),
        ):
            if hasattr(self, _var):
                getattr(self, _var).set(_val)

        # ── Button state: lock everything back to neutral ─────────────────────
        for btn_name in ('_measure_heights_btn', '_clear_points_btn',
                         '_map_surface_btn',
                         '_stitch_measure_heights_btn', '_stitch_clear_points_btn',
                         '_stitch_map_surface_btn'):
            self._safe_btn(btn_name, state="disabled")

        print("[clear] measurement points and ROI grid cleared")

    def _toggle_analysis_point(self, event):
        """Toggle selection of a measured point label; update the analysis readout."""
        canvas = self._roi_active_canvas
        if canvas is None or not self.measured_data:
            return

        # Identify which canvas item was clicked and extract its meas_idx_N tag
        item = canvas.find_withtag("current")
        if not item:
            return
        item_id = item[0]
        idx = None
        for tag in canvas.gettags(item_id):
            if tag.startswith("meas_idx_"):
                idx = int(tag[len("meas_idx_"):])
                break
        if idx is None:
            return

        # Toggle selection state and recolour the text label
        if idx in self.analysis_selected_indices:
            self.analysis_selected_indices.remove(idx)
            canvas.itemconfigure(item_id, fill="cyan")
        else:
            self.analysis_selected_indices.append(idx)
            canvas.itemconfigure(item_id, fill="#00FF44")

        # Update the analysis readout label
        sel = self.analysis_selected_indices
        n_sel = len(sel)
        if n_sel == 0:
            text = "Analysis: Select points..."
        elif n_sel == 1:
            h = self.measured_data[sel[0]][2]
            text = f"Height: {h:.4f} mm"
        elif n_sel == 2:
            h1 = self.measured_data[sel[0]][2]
            h2 = self.measured_data[sel[1]][2]
            text = f"Delta Z: {abs(h1 - h2):.4f} mm"
        else:
            text = f"{n_sel} Points Selected (Plane Gen WIP)"

        if hasattr(self, 'analysis_result_var'):
            self.analysis_result_var.set(text)

        return "break"   # stop event propagating to the canvas click-to-move binding

    def execute_custom_measurements(self):
        """Sort captured points via nearest-neighbour, apply confocal offset, then
        kick off the non-blocking .after() measurement sequence."""
        if not self.custom_measure_points:
            messagebox.showwarning("No Points", "Right-click the image to add measurement points first.")
            return

        # ── Save camera assembly origin before any movement ───────────────────
        # Must be captured here, before the confocal offset shifts the targets.
        self._sequence_origin_x = float(self.x_pos)
        self._sequence_origin_y = float(self.y_pos)

        # ── Nearest-neighbour path optimisation ───────────────────────────────
        current_x = float(self.x_pos)
        current_y = float(self.y_pos)
        unvisited = list(self.custom_measure_points)
        optimized_route = []

        while unvisited:
            nearest = min(unvisited,
                          key=lambda p: (p[0] - current_x) ** 2 + (p[1] - current_y) ** 2)
            unvisited.remove(nearest)
            optimized_route.append(nearest)
            current_x, current_y = nearest

        # ── Apply confocal-camera offset to every target point ────────────────
        # The confocal sensor is offset from the camera by this fixed amount.
        CONFOCAL_DX = -1.418137875
        CONFOCAL_DY = -72.258765875
        offset_route = [(x + CONFOCAL_DX, y + CONFOCAL_DY) for x, y in optimized_route]

        print(f"[execute_custom_measurements] {len(offset_route)} point(s) — nearest-neighbour order (confocal offset applied):")
        for i, (x, y) in enumerate(offset_route, 1):
            print(f"  {i:>3}. ({x:.4f} mm, {y:.4f} mm)")

        # ── Pre-flight: confirm all confocal targets are within stage bounds ──
        # Loop through every offset point; abort on the first violation so the
        # error message references a single concrete bad coordinate.
        for target_x, target_y in offset_route:
            if target_x < 0 or target_y < 0:
                messagebox.showerror(
                    "Cannot Reach Sample",
                    f"Cannot Reach Sample: Point requires stage to move to "
                    f"Y = {target_y:.2f} mm, which is past the module's limit (0 mm).\n\n"
                    f"Please manually unmount and shift your sample at least "
                    f"{abs(target_y) + 1.0:.2f} mm further away from the limit."
                )
                return

        # Disable action buttons on both tabs for the duration of the sequence
        for _btn in ('_measure_heights_btn', '_clear_points_btn', '_map_surface_btn',
                     '_stitch_measure_heights_btn', '_stitch_clear_points_btn',
                     '_stitch_map_surface_btn'):
            self._safe_btn(_btn, state="disabled")

        # Preserve optimised order so _process_measurement_results can pair
        # each height with the correct physical coordinate.
        self._optimized_route = optimized_route

        self._sequence_measure_point(offset_route, 0, [])

    def _sequence_measure_point(self, route, index, results):
        """Non-blocking dispatcher: move to route[index] when the stage is Idle,
        then hand off to the arrival-wait sub-sequence."""
        if index >= len(route):
            self._process_measurement_results(results)
            return

        if self.module_status != "Idle":
            self.after(500, lambda: self._sequence_measure_point(route, index, results))
            return

        target_x, target_y = route[index]

        if target_x < 0 or target_y < 0 or float(self.z_pos) < 0:
            print(f"[sequence] ERROR: point {index + 1} ({target_x:.4f}, {target_y:.4f}) "
                  f"out of range — aborting sequence")
            messagebox.showerror(
                "Sequence Aborted",
                f"Point {index + 1}/{len(route)} ({target_x:.4f}, {target_y:.4f} mm) "
                f"is out of stage range.\nSequence aborted."
            )
            self._sequence_unlock_buttons()
            return

        print(f"[sequence] moving to point {index + 1}/{len(route)}: ({target_x:.4f}, {target_y:.4f}) mm")
        self.send_goto_command(target_x, target_y, float(self.z_pos), show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0

        self.after(500, lambda: self._sequence_wait_then_measure(route, index, results))

    def _sequence_wait_then_measure(self, route, index, results):
        """Poll until the stage reaches Idle (move complete), then simulate a
        measurement dwell before recording the (dummy) height."""
        if self.module_status != "Idle":
            self.after(500, lambda: self._sequence_wait_then_measure(route, index, results))
            return

        print(f"[sequence] stage idle — simulating measurement dwell at point {index + 1}/{len(route)}")
        # No hardware measurement command is sent while in simulation mode.
        # A 500 ms delay simulates sensor dwell time before reading back the value.
        self.after(500, lambda: self._sequence_record_height(route, index, results))

    def _sequence_record_height(self, route, index, results):
        """Record the (dummy) height reading and advance to the next point."""
        dummy_height = 0.0  # TODO: replace with actual confocal sensor readback
        results.append(dummy_height)
        print(f"[sequence] point {index + 1}/{len(route)}: height = {dummy_height:.4f} mm (placeholder)")
        self._sequence_measure_point(route, index + 1, results)

    def _phys_to_canvas_pixel(self, phys_x, phys_y, ref_x, ref_y, canvas_w, canvas_h):
        """Inverse of _canvas_pixel_to_phys: map physical mm coords back to canvas pixels.
        ref_x/ref_y must be the camera assembly position when the image was displayed."""
        if self._canvas_disp_w == 0 or self._canvas_orig_w == 0:
            return None, None
        A11, A12 = -0.001479,  0.000044
        A21, A22 =  0.000018,  0.001459
        det = A11 * A22 - A12 * A21
        dp_x = phys_x - ref_x
        dp_y = phys_y - ref_y
        delta_i = ( A22 * dp_x - A12 * dp_y) / det
        delta_j = (-A21 * dp_x + A11 * dp_y) / det
        sensor_x = self._canvas_orig_w / 2.0 - delta_i
        sensor_y = self._canvas_orig_h / 2.0 - delta_j
        x_offset = (canvas_w - self._canvas_disp_w) / 2.0
        y_offset = (canvas_h - self._canvas_disp_h) / 2.0
        canvas_px = sensor_x * (self._canvas_disp_w / self._canvas_orig_w) + x_offset
        canvas_py = sensor_y * (self._canvas_disp_h / self._canvas_orig_h) + y_offset
        return canvas_px, canvas_py

    def _process_measurement_results(self, results):
        """Draw height labels on the canvas, enter analysis mode, then return to origin."""
        print(f"[sequence] all {len(results)} measurement(s) complete: {results}")

        # Use the optimised order (same order results were collected in) so
        # each height is paired with the correct physical coordinate.
        ordered_points = getattr(self, '_optimized_route', self.custom_measure_points)

        # ── Persist measurement data for analysis mode ────────────────────────
        self.measured_data = [(px, py, h) for (px, py), h in zip(ordered_points, results)]
        self.analysis_selected_indices = []
        if hasattr(self, 'analysis_result_var'):
            self.analysis_result_var.set("Analysis: Select points...")

        # ── Draw height values directly above each marker on the canvas ───────
        canvas = self._roi_active_canvas
        if canvas is not None:
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()

            # Determine whether the active canvas is the stitched view or the
            # standard Image tab, and pick the matching inverse-transform path.
            is_stitched = (self.active_main_view == "stitched")

            for i, (phys_x, phys_y, height) in enumerate(self.measured_data):
                if is_stitched:
                    # Use stitched-image coordinate helper (zoom/pan-aware via _s
                    # was already applied at click time; use stored scan geometry).
                    grid_x  = getattr(self, 'scanning_grid_x', 1)
                    grid_y  = getattr(self, 'scanning_grid_y', 1)
                    step_x  = self.scanning_data.get('step_x', 1.0)
                    step_y  = self.scanning_data.get('step_y', 1.0)
                    scan_end_x   = getattr(self, 'scan_end_x', 0.0)
                    scan_end_y   = getattr(self, 'scan_end_y', 0.0)
                    scan_origin_x = scan_end_x - (grid_x - 1) * step_x
                    scan_origin_y = scan_end_y - (grid_y - 1) * step_y
                    stitched_w = getattr(self, '_stitch_img_w', cw)
                    stitched_h = getattr(self, '_stitch_img_h', ch)
                    cx, cy = self.calculate_phys_to_stitched_pixel_coords(
                        phys_x, phys_y,
                        stitched_w, stitched_h,
                        grid_x, grid_y,
                        scan_origin_x, scan_origin_y,
                        cw, ch,
                    )
                else:
                    if self._canvas_disp_w == 0:
                        continue
                    ref_x = getattr(self, '_sequence_origin_x', float(self.x_pos))
                    ref_y = getattr(self, '_sequence_origin_y', float(self.y_pos))
                    cx, cy = self._phys_to_canvas_pixel(phys_x, phys_y, ref_x, ref_y, cw, ch)

                if cx is not None:
                    canvas.create_text(
                        cx, cy - 15,
                        text=f"{height:.3f} mm",
                        fill="cyan", font=("Arial", 12, "bold"),
                        tags=("custom_pt", "measurement_text", f"meas_idx_{i}"))

            # Bind left-click on text labels to toggle analysis selection
            canvas.tag_bind("measurement_text", "<Button-1>", self._toggle_analysis_point)

        # ── Return camera assembly to its pre-sequence position ───────────────
        origin_x = getattr(self, '_sequence_origin_x', float(self.x_pos))
        origin_y = getattr(self, '_sequence_origin_y', float(self.y_pos))
        print(f"[sequence] returning to origin ({origin_x:.4f}, {origin_y:.4f}) mm")
        self.send_goto_command(origin_x, origin_y, float(self.z_pos), show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0

        self.after(500, self._sequence_unlock_buttons)

    def _sequence_unlock_buttons(self):
        """Poll until the return-to-origin move finishes, then re-enable all
        three action buttons."""
        if self.module_status != "Idle":
            self.after(500, self._sequence_unlock_buttons)
            return

        print("[sequence] origin reached — unlocking action buttons")
        # Re-enable whichever tab's buttons are currently in the widget tree
        for btn_name in ('_measure_heights_btn', '_stitch_measure_heights_btn',
                         '_clear_points_btn', '_stitch_clear_points_btn'):
            self._safe_btn(btn_name, state="normal")
        # Map Surface re-enables only if the grid is still valid
        if self.roi_phys_x_start is not None:
            for ms_btn in ('_map_surface_btn', '_stitch_map_surface_btn'):
                self._safe_btn(ms_btn, state="normal")

    def confirm_map_measurements(self):
        """Legacy shim — delegates to start_surface_map."""
        self.start_surface_map()

    # ──────────────────────────────────────────────────────────────────────────
    # ROI Grid helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _roi_redraw_grid(self, canvas, x0, y0, x1, y1):
        """Erase and redraw the measurement grid on *canvas* between (x0,y0)–(x1,y1).

        map_grid_x × map_grid_y = total measurement points (lines incl. border).
        4 × 4 → 3 × 3 cell grid → 16 measurement dots.

        Visual elements (all tagged "roi_grid"):
          • Dashed grid lines (outer border + internal)
          • Cyan filled dot at every measurement intersection
          • Gold corner handles marking the 4 resize grab points
        """
        canvas.delete("roi_grid")
        nx = max(2, self.map_grid_x)
        ny = max(2, self.map_grid_y)

        DOT_R    = 3   # radius of measurement intersection dots (px)
        HANDLE_R = 7   # radius of corner drag handles (px)

        # ── Grid lines ────────────────────────────────────────────────────────
        # Outer border
        canvas.create_rectangle(x0, y0, x1, y1,
                                 outline="#00FF88", width=2, dash=(6, 3),
                                 tags="roi_grid")
        # Internal vertical lines
        for i in range(1, nx - 1):
            xv = x0 + i * (x1 - x0) / (nx - 1)
            canvas.create_line(xv, y0, xv, y1,
                                fill="#00FF88", width=1, dash=(4, 3),
                                tags="roi_grid")
        # Internal horizontal lines
        for j in range(1, ny - 1):
            yh = y0 + j * (y1 - y0) / (ny - 1)
            canvas.create_line(x0, yh, x1, yh,
                                fill="#00FF88", width=1, dash=(4, 3),
                                tags="roi_grid")

        # ── Measurement dots at every intersection ────────────────────────────
        for i in range(nx):
            xi = x0 + i * (x1 - x0) / (nx - 1)
            for j in range(ny):
                yj = y0 + j * (y1 - y0) / (ny - 1)
                canvas.create_oval(xi - DOT_R, yj - DOT_R,
                                    xi + DOT_R, yj + DOT_R,
                                    fill="#00FF88", outline="",
                                    tags="roi_grid")

        # ── Corner handles (drawn last so they sit on top) ────────────────────
        for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            canvas.create_oval(cx - HANDLE_R, cy - HANDLE_R,
                                cx + HANDLE_R, cy + HANDLE_R,
                                fill="#FFD700", outline="#FFFFFF", width=1,
                                tags="roi_grid")

    def _phys_dist_to_canvas_px(self, phys_dx_mm, phys_dy_mm):
        """Convert a physical distance (mm) to canvas-pixel distances.

        Inverts the scale relationship used in _canvas_pixel_to_phys:
            canvas_px_delta = phys_mm_delta * (disp_px / orig_px) / SCALE_mm_per_sensor_px
        """
        if self._canvas_disp_w == 0 or self._canvas_orig_w == 0:
            return 0.0, 0.0
        SCALE_X = 0.001479   # mm per sensor pixel (|A11|)
        SCALE_Y = 0.001459   # mm per sensor pixel (|A22|)
        dcx = abs(phys_dx_mm) / SCALE_X * (self._canvas_disp_w / self._canvas_orig_w)
        dcy = abs(phys_dy_mm) / SCALE_Y * (self._canvas_disp_h / self._canvas_orig_h)
        return dcx, dcy

    def _update_roi_info_labels(self):
        """Recompute and refresh the calculated output labels in the ROI strip."""
        if not hasattr(self, '_roi_info_count'):
            return
        try:
            nx     = max(2, int(self._roi_spin_x.get()))
            ny     = max(2, int(self._roi_spin_y.get()))
            cell_x = float(self._roi_cell_x.get())
            cell_y = float(self._roi_cell_y.get())
        except (ValueError, AttributeError):
            return
        total  = nx * ny
        area_x = cell_x * (nx - 1)
        area_y = cell_y * (ny - 1)
        est_s  = total * 4
        self._roi_info_area.set(f"Total Area: {area_x:.3f} × {area_y:.3f} mm")
        self._roi_info_count.set(f"Total Points: {total}")
        self._roi_info_time.set(f"Est. Duration: ~{est_s} s")

    # ──────────────────────────────────────────────────────────────────────────
    # ROI pan-drag (reposition box without Ctrl)
    # ──────────────────────────────────────────────────────────────────────────

    def _roi_or_move_press(self, event, canvas, img_disp_w, img_disp_h, orig_img_w, orig_img_h):
        """<Button-1> three-way dispatcher.

        Priority (checked in order):
          0. Click on an analysis marker / label → ignore (let tag_bind handle it).
          1. Click within CORNER_R of a corner handle → resize mode.
          2. Click inside the grid box → move mode.
          3. Click outside → fall through to click_to_move (hardware command).
        """
        # Guard: if the click landed on a measured-point marker or label, do nothing.
        # _toggle_analysis_point (tag_bind) owns that event and returns "break".
        current_items = canvas.find_withtag("current")
        if current_items:
            item_tags = canvas.gettags(current_items[0])
            if "custom_pt" in item_tags or "measurement_text" in item_tags:
                return

        has_roi = (
            self._roi_active_canvas is canvas
            and self._roi_canvas_x0 < self._roi_canvas_x1
        )

        if has_roi:
            CORNER_R = 10   # hit-test radius for corner handles (canvas px)

            x0, y0 = self._roi_canvas_x0, self._roi_canvas_y0
            x1, y1 = self._roi_canvas_x1, self._roi_canvas_y1

            corners = {
                "nw": (x0, y0),
                "ne": (x1, y0),
                "sw": (x0, y1),
                "se": (x1, y1),
            }
            opposite = {"nw": "se", "ne": "sw", "sw": "ne", "se": "nw"}

            # ── 1. Corner hit-test → resize mode ─────────────────────────────
            for name, (cx, cy) in corners.items():
                if abs(event.x - cx) <= CORNER_R and abs(event.y - cy) <= CORNER_R:
                    self._roi_mode          = "resize"
                    self._roi_drag_corner   = name
                    self._roi_resize_anchor = corners[opposite[name]]
                    self._roi_pan_active    = True
                    canvas.configure(cursor="hand2")   # clenched — actively grabbing
                    return

            # ── 2. Inside box → move mode ─────────────────────────────────────
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self._roi_mode       = "move"
                self._roi_pan_active = True
                self._roi_pan_start  = (event.x, event.y)
                canvas.configure(cursor="fleur")       # 4-way — actively moving
                return

        # ── 3. Outside / no ROI → hardware click-to-move ─────────────────────
        self._roi_mode       = "none"
        self._roi_pan_active = False
        self.click_to_move(event, img_disp_w, img_disp_h, orig_img_w, orig_img_h)

    def _roi_pan_motion(self, event, canvas):
        """<B1-Motion>: translate (move mode) or snap-resize (resize mode) the grid.

        Move mode:  Box translates rigidly — cell sizes and measurement counts
                    stay unchanged.

        Resize mode: The fixed anchor corner is held in place.  The dragged
                     corner snaps to the nearest whole-cell boundary so that the
                     physical cell size never changes.  Measurement counts update
                     live in the bottom-menu entries.
        """
        if not self._roi_pan_active:
            return

        # ── MOVE ─────────────────────────────────────────────────────────────
        if self._roi_mode == "move":
            if self._roi_pan_start is None:
                return
            canvas.configure(cursor="fleur")
            dx = event.x - self._roi_pan_start[0]
            dy = event.y - self._roi_pan_start[1]
            self._roi_pan_start = (event.x, event.y)
            self._roi_canvas_x0 += dx
            self._roi_canvas_y0 += dy
            self._roi_canvas_x1 += dx
            self._roi_canvas_y1 += dy
            self._roi_redraw_grid(canvas,
                                  self._roi_canvas_x0, self._roi_canvas_y0,
                                  self._roi_canvas_x1, self._roi_canvas_y1)
            return

        # ── RESIZE ───────────────────────────────────────────────────────────
        if self._roi_mode != "resize":
            return
        if self._roi_resize_anchor is None:
            return
        if self._canvas_disp_w == 0 or self._canvas_orig_w == 0:
            return

        try:
            cell_x = float(self._roi_cell_x.get())
            cell_y = float(self._roi_cell_y.get())
        except (ValueError, AttributeError):
            return
        if cell_x <= 0 or cell_y <= 0:
            return

        canvas.configure(cursor="hand2")   # keep clenched hand throughout resize drag
        # ── Step 1: fixed canvas-pixel pitch per cell ─────────────────────────
        # Derived directly from the locked cell sizes via the A11/A22 scale
        # factors (mm per sensor pixel).  Computing this once in pixel space
        # avoids any canvas-px → mm → canvas-px double-conversion drift.
        SCALE_X = 0.001479   # |A11|: mm per sensor pixel
        SCALE_Y = 0.001459   # |A22|: mm per sensor pixel
        px_per_cell_x = cell_x / SCALE_X * (self._canvas_disp_w / self._canvas_orig_w)
        px_per_cell_y = cell_y / SCALE_Y * (self._canvas_disp_h / self._canvas_orig_h)

        # ── Step 2: raw pixel delta from fixed anchor corner to cursor ─────────
        anchor_x, anchor_y = self._roi_resize_anchor
        raw_px = abs(event.x - anchor_x)
        raw_py = abs(event.y - anchor_y)

        # ── Step 3: discretise — snap to nearest whole-cell count ─────────────
        cols = max(1, round(raw_px / px_per_cell_x))
        rows = max(1, round(raw_py / px_per_cell_y))
        nx   = cols + 1
        ny   = rows + 1

        # ── Step 4: force the bounding box to exact integer-cell multiples ─────
        # The dragged corner lands at anchor ± cols*px_per_cell, NOT at the raw
        # cursor position.  This guarantees every cell is exactly px_per_cell
        # wide/tall with no fractional remainder.
        sign_x    = +1 if event.x >= anchor_x else -1
        sign_y    = +1 if event.y >= anchor_y else -1
        snapped_x = anchor_x + sign_x * cols * px_per_cell_x
        snapped_y = anchor_y + sign_y * rows * px_per_cell_y

        self._roi_canvas_x0 = min(anchor_x, snapped_x)
        self._roi_canvas_y0 = min(anchor_y, snapped_y)
        self._roi_canvas_x1 = max(anchor_x, snapped_x)
        self._roi_canvas_y1 = max(anchor_y, snapped_y)
        self.map_grid_x = nx
        self.map_grid_y = ny

        # Live-update measurement count entries (cell-size entries stay locked)
        self._roi_spin_x.delete(0, "end")
        self._roi_spin_x.insert(0, str(nx))
        self._roi_spin_y.delete(0, "end")
        self._roi_spin_y.insert(0, str(ny))

        self._roi_redraw_grid(canvas,
                              self._roi_canvas_x0, self._roi_canvas_y0,
                              self._roi_canvas_x1, self._roi_canvas_y1)
        self._update_roi_info_labels()

    def _roi_pan_release(self, event, canvas):
        """<ButtonRelease-1>: finalise a move or resize drag.

        Move mode:   Only the position changed — cell sizes are locked, so we
                     simply update the physical origin/end without touching
                     the cell-size entries.

        Resize mode: The measurement counts were already updated live during
                     motion.  Cell sizes remain locked (never touched here).
                     We just commit the final physical bounds.
        """
        if not self._roi_pan_active:
            return

        # Capture mode before clearing state
        mode = self._roi_mode

        # Clear all drag state
        self._roi_pan_active    = False
        self._roi_pan_start     = None
        self._roi_mode          = "none"
        self._roi_drag_corner   = None
        self._roi_resize_anchor = None

        # Recompute physical bounds from the final canvas coords
        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        px0, py0 = self._canvas_pixel_to_phys(
            self._roi_canvas_x0, self._roi_canvas_y0, canvas_w, canvas_h)
        px1, py1 = self._canvas_pixel_to_phys(
            self._roi_canvas_x1, self._roi_canvas_y1, canvas_w, canvas_h)
        if px0 is None or px1 is None:
            return

        self.roi_phys_x_start = min(px0, px1)
        self.roi_phys_x_end   = max(px0, px1)
        self.roi_phys_y_start = min(py0, py1)
        self.roi_phys_y_end   = max(py0, py1)

        # Move mode only: cell sizes are locked, but recompute from physical
        # extent so minor floating-point drift doesn't accumulate over many drags.
        if mode == "move" and self.map_grid_x > 1 and self.map_grid_y > 1:
            phys_w = self.roi_phys_x_end - self.roi_phys_x_start
            phys_h = self.roi_phys_y_end - self.roi_phys_y_start
            if hasattr(self, '_roi_cell_x'):
                self._roi_cell_x.delete(0, "end")
                self._roi_cell_x.insert(0, f"{phys_w / (self.map_grid_x - 1):.4f}")
            if hasattr(self, '_roi_cell_y'):
                self._roi_cell_y.delete(0, "end")
                self._roi_cell_y.insert(0, f"{phys_h / (self.map_grid_y - 1):.4f}")

        # Resize mode: meas count entries were updated live; cell-size entries
        # are intentionally left unchanged (cell sizes are strictly locked).

        self._update_roi_info_labels()

        # Restore contextual cursor: run the hover-zone logic at the release point
        # so the cursor never gets stuck as hand2 / fleur after a drag ends.
        self._on_canvas_motion(event, canvas)

    # ──────────────────────────────────────────────────────────────────────────
    # Contextual cursor
    # ──────────────────────────────────────────────────────────────────────────

    def _on_canvas_motion(self, event, canvas):
        """<Motion> handler: update the canvas cursor based on hover zone.

        Zone priority (checked in order):
          0. Ctrl held (event.state bit 2) → "crosshair"  (drawing mode)
          1. Within CORNER_R of a corner handle → "hand1"  (open grab)
          2. Inside the grid bounding box     → "fleur"   (4-way move)
          3. Outside / no ROI                → "arrow"   (default)

        Also called explicitly from _roi_pan_release so the cursor is never
        left stuck in "hand2" or "fleur" after a drag completes.
        """
        # 0. Ctrl held → crosshair regardless of position
        if event.state & 0x0004:
            canvas.configure(cursor="crosshair")
            return

        # No active ROI on this canvas → plain arrow
        if (self._roi_active_canvas is not canvas
                or self._roi_canvas_x0 >= self._roi_canvas_x1):
            canvas.configure(cursor="arrow")
            return

        CORNER_R = 10   # must match the hit-radius used in _roi_or_move_press
        x0, y0 = self._roi_canvas_x0, self._roi_canvas_y0
        x1, y1 = self._roi_canvas_x1, self._roi_canvas_y1
        mx, my = event.x, event.y

        # 1. Corner handles → open hand
        for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            if abs(mx - cx) <= CORNER_R and abs(my - cy) <= CORNER_R:
                canvas.configure(cursor="hand1")
                return

        # 2. Inside box → 4-way move
        if x0 <= mx <= x1 and y0 <= my <= y1:
            canvas.configure(cursor="fleur")
            return

        # 3. Outside → default arrow
        canvas.configure(cursor="arrow")

    # ──────────────────────────────────────────────────────────────────────────
    # UI → Canvas sync (entry edits resize / recount the grid)
    # ──────────────────────────────────────────────────────────────────────────

    def _update_roi_from_entries(self, event=None):
        """Called on <KeyRelease> in any dimension entry.

        Parses the current measurement counts and cell sizes, resizes the canvas
        grid (keeping the top-left corner fixed), recomputes physical bounds, and
        refreshes the info labels.
        """
        self._update_roi_info_labels()   # always refresh labels even if no canvas ROI

        if self._roi_active_canvas is None:
            return
        try:
            nx     = max(2, int(self._roi_spin_x.get()))
            ny     = max(2, int(self._roi_spin_y.get()))
            cell_x = float(self._roi_cell_x.get())
            cell_y = float(self._roi_cell_y.get())
        except (ValueError, AttributeError):
            return
        if cell_x <= 0 or cell_y <= 0:
            return

        self.map_grid_x = nx
        self.map_grid_y = ny

        # UI → Canvas: total physical extent → canvas pixel dimensions
        total_phys_x = cell_x * (nx - 1)
        total_phys_y = cell_y * (ny - 1)
        dcx, dcy = self._phys_dist_to_canvas_px(total_phys_x, total_phys_y)

        # Keep top-left corner fixed; stretch bottom-right
        self._roi_canvas_x1 = self._roi_canvas_x0 + dcx
        self._roi_canvas_y1 = self._roi_canvas_y0 + dcy

        self._roi_redraw_grid(self._roi_active_canvas,
                              self._roi_canvas_x0, self._roi_canvas_y0,
                              self._roi_canvas_x1, self._roi_canvas_y1)

        # Update physical bounds to match new dimensions
        canvas   = self._roi_active_canvas
        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        px0, py0 = self._canvas_pixel_to_phys(self._roi_canvas_x0, self._roi_canvas_y0, canvas_w, canvas_h)
        px1, py1 = self._canvas_pixel_to_phys(self._roi_canvas_x1, self._roi_canvas_y1, canvas_w, canvas_h)
        if px0 is not None:
            self.roi_phys_x_start = min(px0, px1)
            self.roi_phys_x_end   = max(px0, px1)
            self.roi_phys_y_start = min(py0, py1)
            self.roi_phys_y_end   = max(py0, py1)

    # ──────────────────────────────────────────────────────────────────────────
    # Stitched-view ROI — coord math uses calculate_stitched_phys_coords
    # ──────────────────────────────────────────────────────────────────────────

    def _update_stitched_roi_info_labels(self):
        """Refresh the calculated output labels in the stitched-view ROI strip."""
        if not hasattr(self, '_stitch_roi_info_count'):
            return
        try:
            nx     = max(2, int(self._stitch_roi_spin_x.get()))
            ny     = max(2, int(self._stitch_roi_spin_y.get()))
            cell_x = float(self._stitch_roi_cell_x.get())
            cell_y = float(self._stitch_roi_cell_y.get())
        except (ValueError, AttributeError):
            return
        total  = nx * ny
        area_x = cell_x * (nx - 1)
        area_y = cell_y * (ny - 1)
        self._stitch_roi_info_area.set(f"Total Area: {area_x:.3f} × {area_y:.3f} mm")
        self._stitch_roi_info_count.set(f"Total Points: {total}")
        self._stitch_roi_info_time.set(f"Est. Duration: ~{total * 4} s")

    def _roi_release_stitched(self, event, canvas, _s,
                               stitched_w, stitched_h,
                               grid_x, grid_y, scan_origin_x, scan_origin_y):
        """Finalise Ctrl+drag ROI on the stitched canvas.

        Converts canvas pixels → full-res stitched pixels → physical mm using
        the stitched-image mapping; never calls _canvas_pixel_to_phys.
        """
        if self._roi_drag_start is None:
            return
        x0, y0 = self._roi_drag_start
        x1, y1 = event.x, event.y
        self._roi_drag_start = None

        self._roi_canvas_x0 = min(x0, x1)
        self._roi_canvas_y0 = min(y0, y1)
        self._roi_canvas_x1 = max(x0, x1)
        self._roi_canvas_y1 = max(y0, y1)

        def _c2p(cx, cy):
            fpx = (cx - _s['ox']) / _s['sx']
            fpy = (cy - _s['oy']) / _s['sy']
            return self.calculate_stitched_phys_coords(
                fpx, fpy, stitched_w, stitched_h,
                grid_x, grid_y, scan_origin_x, scan_origin_y)

        px0, py0 = _c2p(self._roi_canvas_x0, self._roi_canvas_y0)
        px1, py1 = _c2p(self._roi_canvas_x1, self._roi_canvas_y1)

        self.roi_phys_x_start = min(px0, px1)
        self.roi_phys_x_end   = max(px0, px1)
        self.roi_phys_y_start = min(py0, py1)
        self.roi_phys_y_end   = max(py0, py1)

        phys_w = self.roi_phys_x_end - self.roi_phys_x_start
        phys_h = self.roi_phys_y_end - self.roi_phys_y_start
        try:
            nx = max(2, int(self._stitch_roi_spin_x.get()))
            ny = max(2, int(self._stitch_roi_spin_y.get()))
        except (ValueError, AttributeError):
            nx, ny = 4, 4
        self.map_grid_x = nx
        self.map_grid_y = ny
        if nx > 1:
            self._stitch_roi_cell_x.delete(0, "end")
            self._stitch_roi_cell_x.insert(0, f"{phys_w / (nx - 1):.4f}")
        if ny > 1:
            self._stitch_roi_cell_y.delete(0, "end")
            self._stitch_roi_cell_y.insert(0, f"{phys_h / (ny - 1):.4f}")

        self._roi_redraw_grid(canvas, self._roi_canvas_x0, self._roi_canvas_y0,
                              self._roi_canvas_x1, self._roi_canvas_y1)
        self._update_stitched_roi_info_labels()
        self._safe_btn('_stitch_map_surface_btn', state="normal")
        self._safe_btn('_stitch_clear_points_btn', state="normal")
        canvas.configure(cursor="crosshair")

    def _roi_or_move_press_stitched(self, event, canvas, on_click_fn):
        """<Button-1> dispatcher for the stitched canvas.

        Priority:
          0. Click on an analysis marker / label → ignore (tag_bind owns it).
          1. Within CORNER_R of a corner handle → resize mode.
          2. Inside the grid box → move mode.
          3. Otherwise → delegate to on_click_fn (hardware click-to-move).
        """
        current_items = canvas.find_withtag("current")
        if current_items:
            item_tags = canvas.gettags(current_items[0])
            if "custom_pt" in item_tags or "measurement_text" in item_tags:
                return

        has_roi = (
            self._roi_active_canvas is canvas
            and self._roi_canvas_x0 < self._roi_canvas_x1
        )
        if has_roi:
            CORNER_R = 10
            x0, y0 = self._roi_canvas_x0, self._roi_canvas_y0
            x1, y1 = self._roi_canvas_x1, self._roi_canvas_y1
            corners  = {"nw": (x0, y0), "ne": (x1, y0), "sw": (x0, y1), "se": (x1, y1)}
            opposite = {"nw": "se", "ne": "sw", "sw": "ne", "se": "nw"}
            for name, (cx, cy) in corners.items():
                if abs(event.x - cx) <= CORNER_R and abs(event.y - cy) <= CORNER_R:
                    self._roi_mode          = "resize"
                    self._roi_drag_corner   = name
                    self._roi_resize_anchor = corners[opposite[name]]
                    self._roi_pan_active    = True
                    canvas.configure(cursor="hand2")
                    return
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self._roi_mode       = "move"
                self._roi_pan_active = True
                self._roi_pan_start  = (event.x, event.y)
                canvas.configure(cursor="fleur")
                return
        self._roi_mode       = "none"
        self._roi_pan_active = False
        on_click_fn(event)

    def _roi_pan_motion_stitched(self, event, canvas, _s):
        """<B1-Motion> for the stitched canvas: translate (move) or snap-resize.

        Move mode is coord-agnostic (pure canvas-pixel translation).
        Resize snap uses _s['sx']/_s['sy'] — the live stitched-image scale.
        """
        if not self._roi_pan_active:
            return

        if self._roi_mode == "move":
            if self._roi_pan_start is None:
                return
            canvas.configure(cursor="fleur")
            dx = event.x - self._roi_pan_start[0]
            dy = event.y - self._roi_pan_start[1]
            self._roi_pan_start = (event.x, event.y)
            self._roi_canvas_x0 += dx;  self._roi_canvas_y0 += dy
            self._roi_canvas_x1 += dx;  self._roi_canvas_y1 += dy
            self._roi_redraw_grid(canvas,
                                  self._roi_canvas_x0, self._roi_canvas_y0,
                                  self._roi_canvas_x1, self._roi_canvas_y1)
            return

        if self._roi_mode != "resize" or self._roi_resize_anchor is None:
            return
        try:
            cell_x = float(self._stitch_roi_cell_x.get())
            cell_y = float(self._stitch_roi_cell_y.get())
        except (ValueError, AttributeError):
            return
        if cell_x <= 0 or cell_y <= 0:
            return

        canvas.configure(cursor="hand2")
        SCALE_X, SCALE_Y = 0.001479, 0.001459
        px_per_cell_x = cell_x * _s['sx'] / SCALE_X
        px_per_cell_y = cell_y * _s['sy'] / SCALE_Y

        anchor_x, anchor_y = self._roi_resize_anchor
        cols = max(1, round(abs(event.x - anchor_x) / px_per_cell_x))
        rows = max(1, round(abs(event.y - anchor_y) / px_per_cell_y))
        nx, ny = cols + 1, rows + 1

        sign_x = +1 if event.x >= anchor_x else -1
        sign_y = +1 if event.y >= anchor_y else -1
        snapped_x = anchor_x + sign_x * cols * px_per_cell_x
        snapped_y = anchor_y + sign_y * rows * px_per_cell_y

        self._roi_canvas_x0 = min(anchor_x, snapped_x)
        self._roi_canvas_y0 = min(anchor_y, snapped_y)
        self._roi_canvas_x1 = max(anchor_x, snapped_x)
        self._roi_canvas_y1 = max(anchor_y, snapped_y)
        self.map_grid_x = nx;  self.map_grid_y = ny

        self._stitch_roi_spin_x.delete(0, "end");  self._stitch_roi_spin_x.insert(0, str(nx))
        self._stitch_roi_spin_y.delete(0, "end");  self._stitch_roi_spin_y.insert(0, str(ny))

        self._roi_redraw_grid(canvas,
                              self._roi_canvas_x0, self._roi_canvas_y0,
                              self._roi_canvas_x1, self._roi_canvas_y1)
        self._update_stitched_roi_info_labels()

    def _roi_pan_release_stitched(self, event, canvas, _s,
                                   stitched_w, stitched_h,
                                   grid_x, grid_y, scan_origin_x, scan_origin_y):
        """<ButtonRelease-1>: commit the final physical bounds for the stitched canvas."""
        if not self._roi_pan_active:
            return

        mode = self._roi_mode
        self._roi_pan_active    = False
        self._roi_pan_start     = None
        self._roi_mode          = "none"
        self._roi_drag_corner   = None
        self._roi_resize_anchor = None

        def _c2p(cx, cy):
            fpx = (cx - _s['ox']) / _s['sx']
            fpy = (cy - _s['oy']) / _s['sy']
            return self.calculate_stitched_phys_coords(
                fpx, fpy, stitched_w, stitched_h,
                grid_x, grid_y, scan_origin_x, scan_origin_y)

        px0, py0 = _c2p(self._roi_canvas_x0, self._roi_canvas_y0)
        px1, py1 = _c2p(self._roi_canvas_x1, self._roi_canvas_y1)

        self.roi_phys_x_start = min(px0, px1)
        self.roi_phys_x_end   = max(px0, px1)
        self.roi_phys_y_start = min(py0, py1)
        self.roi_phys_y_end   = max(py0, py1)

        # Move mode: recompute cell sizes from the new physical extent
        if mode == "move" and self.map_grid_x > 1 and self.map_grid_y > 1:
            phys_w = self.roi_phys_x_end - self.roi_phys_x_start
            phys_h = self.roi_phys_y_end - self.roi_phys_y_start
            self._stitch_roi_cell_x.delete(0, "end")
            self._stitch_roi_cell_x.insert(0, f"{phys_w / (self.map_grid_x - 1):.4f}")
            self._stitch_roi_cell_y.delete(0, "end")
            self._stitch_roi_cell_y.insert(0, f"{phys_h / (self.map_grid_y - 1):.4f}")

        self._update_stitched_roi_info_labels()
        self._on_canvas_motion(event, canvas)

    def _update_roi_from_entries_stitched(self, event, canvas, _s,
                                           stitched_w, stitched_h,
                                           grid_x, grid_y, scan_origin_x, scan_origin_y):
        """Called on <KeyRelease> in any stitched-view dimension entry.

        Resizes the canvas grid (top-left fixed) using the stitched scale
        factors and recomputes physical bounds.
        """
        self._update_stitched_roi_info_labels()

        if self._roi_active_canvas is not canvas:
            return
        try:
            nx     = max(2, int(self._stitch_roi_spin_x.get()))
            ny     = max(2, int(self._stitch_roi_spin_y.get()))
            cell_x = float(self._stitch_roi_cell_x.get())
            cell_y = float(self._stitch_roi_cell_y.get())
        except (ValueError, AttributeError):
            return
        if cell_x <= 0 or cell_y <= 0:
            return

        self.map_grid_x = nx;  self.map_grid_y = ny
        SCALE_X, SCALE_Y = 0.001479, 0.001459
        dcx = cell_x * (nx - 1) * _s['sx'] / SCALE_X
        dcy = cell_y * (ny - 1) * _s['sy'] / SCALE_Y

        self._roi_canvas_x1 = self._roi_canvas_x0 + dcx
        self._roi_canvas_y1 = self._roi_canvas_y0 + dcy
        self._roi_redraw_grid(canvas, self._roi_canvas_x0, self._roi_canvas_y0,
                              self._roi_canvas_x1, self._roi_canvas_y1)

        def _c2p(cx, cy):
            fpx = (cx - _s['ox']) / _s['sx']
            fpy = (cy - _s['oy']) / _s['sy']
            return self.calculate_stitched_phys_coords(
                fpx, fpy, stitched_w, stitched_h,
                grid_x, grid_y, scan_origin_x, scan_origin_y)

        px0, py0 = _c2p(self._roi_canvas_x0, self._roi_canvas_y0)
        px1, py1 = _c2p(self._roi_canvas_x1, self._roi_canvas_y1)
        self.roi_phys_x_start = min(px0, px1)
        self.roi_phys_x_end   = max(px0, px1)
        self.roi_phys_y_start = min(py0, py1)
        self.roi_phys_y_end   = max(py0, py1)

    # ──────────────────────────────────────────────────────────────────────────
    # Map Surface — validate and (WIP) launch scan
    # ──────────────────────────────────────────────────────────────────────────

    def start_surface_map(self):
        """Validate all ROI / grid parameters and confirm the surface mapping job.

        Hardware scan execution is WIP — a TODO comment marks where
        run_topography_map() should be called in a background Thread.
        """
        # ── Validate grid counts ────────────────────────────────────────────
        try:
            nx = int(self._roi_spin_x.get())
            ny = int(self._roi_spin_y.get())
        except (ValueError, AttributeError):
            messagebox.showerror("Invalid Input", "Measurement counts must be integers ≥ 2.")
            return
        if nx < 2 or ny < 2:
            messagebox.showerror("Invalid Input", "Measurement counts must be ≥ 2.")
            return

        # ── Validate cell sizes ─────────────────────────────────────────────
        try:
            cell_x = float(self._roi_cell_x.get())
            cell_y = float(self._roi_cell_y.get())
        except (ValueError, AttributeError):
            messagebox.showerror("Invalid Input", "Cell sizes must be positive numbers (mm).")
            return
        if cell_x <= 0 or cell_y <= 0:
            messagebox.showerror("Invalid Input", "Cell sizes must be positive.")
            return

        # ── Validate CSV name ───────────────────────────────────────────────
        csv_name = self._roi_csv_name.get().strip()
        if not csv_name:
            messagebox.showerror("Invalid Input", "Please enter a CSV output file name.")
            return

        # ── Require a drawn ROI ─────────────────────────────────────────────
        if self.roi_phys_x_start is None:
            messagebox.showerror("No ROI", "Draw a region first: hold Ctrl and drag on the image.")
            return

        # ── Convert to nanometres for the SmarAct API ───────────────────────
        start_x_nm  = round(self.roi_phys_x_start * 1_000_000)
        start_y_nm  = round(self.roi_phys_y_start * 1_000_000)
        step_x_nm   = round(cell_x * 1_000_000)
        step_y_nm   = round(cell_y * 1_000_000)   # reserved; see TODO below
        total_pts   = nx * ny
        est_sec     = total_pts * 4

        self.map_grid_x = nx
        self.map_grid_y = ny

        print(
            f"[surface_map] Grid: {nx}×{ny} = {total_pts} points\n"
            f"  Origin:  ({self.roi_phys_x_start:.4f} mm, {self.roi_phys_y_start:.4f} mm)\n"
            f"  Step X:  {cell_x:.4f} mm  ({step_x_nm} nm)\n"
            f"  Step Y:  {cell_y:.4f} mm  ({step_y_nm} nm)\n"
            f"  Output:  {csv_name}.csv"
        )

        messagebox.showinfo(
            "Map Surface — WIP",
            f"Surface map parameters confirmed:\n\n"
            f"  Grid:          {nx} × {ny} = {total_pts} points\n"
            f"  Cell size:     {cell_x:.4f} mm × {cell_y:.4f} mm\n"
            f"  Coverage:      {cell_x*(nx-1):.3f} mm × {cell_y*(ny-1):.3f} mm\n"
            f"  Estimated time: WIP (~{est_sec} s)\n"
            f"  Output file:   {csv_name}.csv\n\n"
            "Scan execution is WIP — hardware call not yet wired."
        )

        # TODO: call run_topography_map() in a background Thread and write results
        #   to {csv_name}.csv.  Note: run_topography_map() currently accepts a single
        #   step_size_nm; separate X/Y step sizes will require a future API change.
        #   Suggested call once the API is updated:
        #     Thread(target=_run_scan, daemon=True).start()
        #   where _run_scan opens the MCS handle, calls run_topography_map with
        #   start_x_nm, start_y_nm, step_x_nm, step_y_nm, nx, ny, then writes CSV.

    def start_surface_map_stitched(self):
        """Variant of start_surface_map that reads from the stitched-view ROI entries."""
        try:
            nx = int(self._stitch_roi_spin_x.get())
            ny = int(self._stitch_roi_spin_y.get())
        except (ValueError, AttributeError):
            messagebox.showerror("Invalid Input", "Measurement counts must be integers ≥ 2.")
            return
        if nx < 2 or ny < 2:
            messagebox.showerror("Invalid Input", "Measurement counts must be ≥ 2.")
            return
        try:
            cell_x = float(self._stitch_roi_cell_x.get())
            cell_y = float(self._stitch_roi_cell_y.get())
        except (ValueError, AttributeError):
            messagebox.showerror("Invalid Input", "Cell sizes must be positive numbers (mm).")
            return
        if cell_x <= 0 or cell_y <= 0:
            messagebox.showerror("Invalid Input", "Cell sizes must be positive.")
            return
        csv_name = self._stitch_roi_csv_name.get().strip()
        if not csv_name:
            messagebox.showerror("Invalid Input", "Please enter a CSV output file name.")
            return
        if self.roi_phys_x_start is None:
            messagebox.showerror("No ROI", "Draw a region first: hold Ctrl and drag on the image.")
            return

        step_x_nm = round(cell_x * 1_000_000)
        step_y_nm = round(cell_y * 1_000_000)
        total_pts = nx * ny
        est_sec   = total_pts * 4
        self.map_grid_x = nx
        self.map_grid_y = ny

        print(
            f"[surface_map_stitched] Grid: {nx}×{ny} = {total_pts} points\n"
            f"  Origin:  ({self.roi_phys_x_start:.4f} mm, {self.roi_phys_y_start:.4f} mm)\n"
            f"  Step X:  {cell_x:.4f} mm  ({step_x_nm} nm)\n"
            f"  Step Y:  {cell_y:.4f} mm  ({step_y_nm} nm)\n"
            f"  Output:  {csv_name}.csv"
        )
        messagebox.showinfo(
            "Map Surface — WIP",
            f"Surface map parameters confirmed:\n\n"
            f"  Grid:          {nx} × {ny} = {total_pts} points\n"
            f"  Cell size:     {cell_x:.4f} mm × {cell_y:.4f} mm\n"
            f"  Coverage:      {cell_x*(nx-1):.3f} mm × {cell_y*(ny-1):.3f} mm\n"
            f"  Estimated time: ~{est_sec} s\n"
            f"  Output file:   {csv_name}.csv\n\n"
            "Scan execution is WIP — hardware call not yet wired."
        )

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
        stitched_img_path = f"{self.buffer_stitching_folder}/stitched_{self.curr_sample_id}.jpg"
        self.complete_image_btn = ctk.CTkButton(button_frame, text="Image Stitching...", fg_color="green", width=150, height=30,
                                                state="disabled",
                                                command=lambda: self.display_stitched_inline(stitched_img_path))
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

        #Get all files in the folder, sorted numerically by integer prefix (e.g. 1_V.jpg, 2_V.jpg, 10_V.jpg)
        for filename in sorted(os.listdir(folder_path), key=lambda x: int(x.split('_')[0]) if x.split('_')[0].isdigit() else float('inf')):
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

        # Wait until every tile in the grid is present before rendering.
        # Rendering a partial set produces a scrambled preview because the
        # grid placeholders are filled positionally — a missing tile shifts
        # every subsequent image into the wrong cell.
        if len(images) < self.expected_image_count:
            self.after(1000, self.poll_for_new_images)
            return

        # Full set confirmed — sort numerically by integer prefix so the grid
        # is assembled in capture order regardless of OS filesystem ordering.
        def extract_index(filename):
            match = re.match(r'^(\d+)', os.path.basename(filename))
            return int(match.group(1)) if match else float('inf')

        images = sorted(images, key=extract_index)

        # Render exactly expected_image_count tiles into the grid placeholders
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

        # All tiles loaded — unlock the stitched-image button
        self.complete_image_btn.configure(state="normal")


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

        expanded_window.wait_visibility()
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
            for filename in sorted(os.listdir(src_folder)):
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
            for filename in sorted(os.listdir(dir_path)):
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
        for filename in sorted(os.listdir(directory)):
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

    def send_json_error_check(self, data, success_message, show_success=True):
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
                    if show_success:
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
        if time.time() < self.status_lockout_time:
            return

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
            and self.scan_in_progress
            and self.module_status == "Idle"):

            # Module returned to Idle after a commanded scan — stage is at the
            # last tile (top-right corner). Snapshot for click-to-move maths.
            self.scan_end_x = float(self.x_pos)
            self.scan_end_y = float(self.y_pos)
            self.scan_in_progress = False
            self.scanning_state = 1

        #Start transfer folder thread when all images have been taken
        if self.scanning_state == 1:
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
        
        # Stitching thread has finished; file-ready polling is already running
        # via .after() from start_stitching — only reset the state machine here.
        if self.scanning_state == 3 and not self.stitching_thread.is_alive():
            self.scanning_state = 0
            
        #Random Samping Image Processing
        #Start mini state machine for random sampling process
        if (self.sampling_state == 0
            and self.sample_in_progress
            and self.module_status == "Idle"):

            self.sample_in_progress = False
            self.sampling_state = 1

        #When all images have been taken, start transfer folder thread
        if self.sampling_state == 1:
            self.transfer_rpi_thread = Thread(target=self.transfer_folder_rpi, kwargs={"destination_path": self.buffer_sampling_folder, "new_filename": False}, daemon=True)
            self.transfer_rpi_thread.start()

            self.sampling_state = 2

        #Wait for the transfer folder thread to finish, then empty folder on Raspberry Pi
        if self.sampling_state == 2 and not self.transfer_rpi_thread.is_alive():
            self.empty_folder_rpi() 

            self.sampling_state = 0 #Reset mini state machine
        

    def send_sample_data(self, mount_type, sample_location, sample_id, initial_height, layer_height, width, height):
        """
        Stores sample data, sends it to the Raspberry Pi, and sends command.

        Args:
            mount_type (str): The type of the mount.
            sample_location (str): The physical location of the sample (which stage to use).
            sample_id (str): The ID of the sample.
            initial_height (float): The initial height of the sample.
            layer_height (float): The layer height for the sample.
            width (float): The width of the bounding box.
            height (float): The height of the bounding box.

        Returns:
            None
        """
        if self.module_status == "Idle":

            # Store the sample data
            self.sample_data['command'] = "create_sample"
            self.sample_data['mode'] = "Manual"
            self.sample_data['mount_type'] = mount_type
            self.sample_data['sample_location'] = sample_location
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
            
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")

    def send_simple_command(self, command, checkIdle, show_success=True):
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
            self.send_json_error_check(json_data, success_message, show_success=show_success)


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
            self.sample_in_progress = True
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

            # Snapshot the stage position at scan-start so the stitched-image
            # click-to-move can compute absolute physical coordinates later.
            self.scan_origin_x = float(self.x_pos)
            self.scan_origin_y = float(self.y_pos)

            # Purge stale images from the Pi buffer BEFORE issuing the scan
            # command so the Pi cannot re-transmit leftover images from a
            # previous session.  The SSH rm runs in a background thread to
            # avoid blocking the Tkinter main loop; the scan command is then
            # dispatched back to the main thread via after(0) only after the
            # remote folder is confirmed empty.
            scanning_data_snapshot = dict(self.scanning_data)

            def _clear_pi_then_scan():
                remote_folder = "/home/microscope/image_buffer"
                if self.rpi_transfer:
                    try:
                        self.rpi_transfer.connect_ssh()
                        self.rpi_transfer.empty_folder(remote_folder)
                        self.rpi_transfer.close_ssh_connection()
                        print(f"Pi buffer cleared before scan: {remote_folder}")
                    except Exception as e:
                        print(f"Warning: could not clear Pi buffer before scan — {e}")
                self.after(0, lambda: self.send_json_error_check(scanning_data_snapshot, "Scanning request sent."))

            self.scan_in_progress = True
            Thread(target=_clear_pi_then_scan, daemon=True).start()
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
    

    def send_preset_measure_command(self):
    # Send a request to the Raspberry Pi to move to a preset position.
        if self.module_status == "Idle":
            preset_data = {
                "command": "exe_goto_preset_measure",
                "mode": self.mode,
                "module_status": self.module_status
            }

            success_message = "Preset move request sent."
            self.send_json_error_check(preset_data, success_message)
        else:
            messagebox.showerror("Status not in idle, wait before sending request.")



    def send_smaract_stage_command(self):
        # Step 1: Move Z to safe height first, holding X and Y at their current positions.
        self.send_goto_command(
            req_x=float(self.x_pos),
            req_y=float(self.y_pos),
            req_z=70.0,
            show_success=False
        )
        # Lock status locally so the Pi's delayed acknowledgement doesn't overwrite it
        # before the move has actually started (same pattern as click-to-move).
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0
        # Step 2: Poll until Z move completes, then transit X and Y.
        self.after(500, self._smaract_wait_then_xy)

    def _smaract_wait_then_xy(self):
        if self.module_status != "Idle":
            self.after(500, self._smaract_wait_then_xy)
            return
        self.send_goto_command(
            req_x=0.437369625,
            req_y=203.456397375,
            req_z=70.0
        )

    def toggle_interferometer_camera(self):
        if not self.is_at_interferometer:
            dx, dy = -1.418137875, -72.258765875
            new_label = "Optical"
        else:
            dx, dy = 1.418137875, 72.258765875
            new_label = "Confocal"

        target_x = float(self.x_pos) + dx
        target_y = float(self.y_pos) + dy
        target_z = float(self.z_pos)

        # Mirror send_goto_command's guards so state only flips when the move will succeed.
        if self.module_status != "Idle":
            messagebox.showerror("Error", "Status not in idle, wait before sending request.")
            return
        if target_x < 0 or target_y < 0 or target_z < 0:
            print(f"Warning: toggle move rejected — target ({target_x:.6f}, {target_y:.6f}, {target_z:.6f}) contains a negative value.")
            return

        try:
            self.send_goto_command(target_x, target_y, target_z, show_success=False)
        except Exception as e:
            print(f"Warning: toggle move failed — {e}")
            return

        self.is_at_interferometer = not self.is_at_interferometer
        self.interferometer_toggle_btn.configure(text=new_label)

    def _start_smaract_homing(self):
        """
        Launch home_smaract() on a daemon Thread so the GUI stays responsive
        while the stage physically drives to its reference marks.

        The button is disabled and relabelled for the duration of the sequence,
        then restored on the main thread via after() once the thread finishes.
        A try/except guards against the button having been destroyed if the
        operator switches tabs before homing completes.
        """
        self.smaract_home_btn.configure(state="disabled", text="Homing...")

        def _worker():
            home_smaract()
            # Restore the button on the Tk main thread
            try:
                self.after(
                    0,
                    lambda: self.smaract_home_btn.configure(
                        state="normal", text="Homing"
                    ),
                )
            except Exception:
                pass  # Button was destroyed when the tab was switched

        Thread(target=_worker, daemon=True).start()

    def send_goto_command(self, req_x, req_y, req_z, show_success=True) :
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
            self.send_json_error_check(goto_data, success_message, show_success=show_success)
        else:
            messagebox.showerror("Status not in idle, wait to request scanning mode.")

    def sequence_wait_for_move(self, image_label):
        if self.module_status != "Idle":
            self.after(100, lambda: self.sequence_wait_for_move(image_label))
            return

        self.empty_folder_rpi()
        self.send_simple_command("exe_update_image", checkIdle=False, show_success=False)
        self.empty_folder_pc(self.buffer_testing_folder)

        self.module_status = "Capturing Image"
        self.status_lockout_time = time.time() + 0.5

        self.sequence_wait_for_capture(image_label)

    def sequence_wait_for_capture(self, image_label):
        if self.module_status != "Idle":
            self.after(100, lambda: self.sequence_wait_for_capture(image_label))
            return

        try:
            image_label.winfo_exists()
        except Exception:
            return
        self.sequence_transfer_and_display(image_label)

    def sequence_transfer_and_display(self, image_label):
        self.transfer_folder_rpi(self.buffer_testing_folder, False)
        self.show_image(self.buffer_testing_folder, image_label)





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

    def check_stitched_file_ready(self, filepath, retries=120):
        """
        Non-blocking poll for the stitched output JPEG. Always called from the
        Tkinter main thread via .after() — never from the stitching thread.

        The is_stitching lock prevents the button from being enabled more than
        once per scan and blocks spurious triggers if the file already existed
        from a previous run before the new one is written.

        Args:
            filepath (str): Absolute path to the expected stitched JPEG.
            retries (int): Remaining 500 ms poll attempts (default 120 = 60 s).
        """
        if os.path.exists(filepath):
            # File confirmed on disk — disarm lock and update button unconditionally.
            # check_stitched_file_ready is always invoked from the Tkinter main thread
            # via .after(), so no after(0) indirection is required here.
            self.is_stitching = False
            self.complete_image_btn.configure(text="Open Completed Image", state="normal")
        elif retries > 0:
            self.after(500, lambda: self.check_stitched_file_ready(filepath, retries - 1))
        else:
            self.is_stitching = False
            print(f"Stitched file transfer timed out: {filepath}")

    def start_stitching(self, grid_x, grid_y, input_dir, output_dir, sample_id):
        """
        Arms the stitching lock, starts the .after() file-ready poll on the
        main thread, then spawns the background Fiji subprocess thread.

        The poll and the thread are started together here so there is exactly
        one poller per scan and it always runs on the Tkinter main thread.

        Args:
            grid_x (int): Number of columns in the stitching grid.
            grid_y (int): Number of rows in the stitching grid.
            input_dir (str): Directory containing the tile images.
            output_dir (str): Directory where Fiji writes the stitched JPEG.
            sample_id (str): Sample identifier used in the output filename.
        """
        stitched_path = os.path.join(output_dir, f"stitched_{sample_id}.jpg")

        # Arm lock and start poll on the main thread before the thread begins
        self.is_stitching = True
        self.after(500, lambda: self.check_stitched_file_ready(stitched_path))

        self.stitching_thread = Thread(
            target=lambda: self.stitcher.run_stitching(grid_x, grid_y, input_dir, output_dir, sample_id),
            daemon=True
        )
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
