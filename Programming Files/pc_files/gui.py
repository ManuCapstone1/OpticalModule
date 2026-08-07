import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
from datetime import datetime
import json
import time
import re
import os
import csv
import shutil
import socket
import math
from threading import Thread, Lock
from stage import home_smaract, open_smaract, close_smaract, get_position, move_to_absolute, CHANNEL_X, CHANNEL_Y
from plane_math import calculate_best_fit_plane, get_corrected_height, compare_planes

# Confocal sensor network settings 
_CONFOCAL_IP           = "169.254.0.20"
_CONFOCAL_PORT         = 24685
_CONFOCAL_TIMEOUT      = 2.0

# SmarAct stage: fixed position for the optical to park above the SmarAct 
SMARACT_PARK_X = 6.401500875
SMARACT_PARK_Y = 201.070744875
SMARACT_PARK_Z = 70.0
# confocal's own ideal Z for a zero-height SmarAct sample, derived empirically:
# 70.0 (SMARACT_PARK_Z) - 3.0278 (confocal reading, bare stage, no sample) = 66.9722
# distinct from SMARACT_PARK_Z, which is calibrated for the camera's focus, not
# the confocal's ~15mm standoff -- the two sensors sit at different heights on the assembly
SMARACT_CONFOCAL_FOCUS_Z = 66.9722
# Settling delay: time (ms) to wait after the motor controller reports "Idle" before triggering a measurement.
_SETTLING_DELAY_MS     = 275
# piezo stage still rings briefly after the controller reports target-reached.
# 100ms wasn't enough margin — blur kept showing up late in a 9-point run
# (points 8-9), suggesting some creep/ringing outlasts the exposure window too
# (default exposure is itself ~100ms). bumped up, still needs real tuning.
SMARACT_SETTLING_DELAY_MS = 300
# Confocal XY offset from the optical
_CONFOCAL_DX = -1.418137875
_CONFOCAL_DY = -72.258765875
# Where the confocal needs to be to sit over the SmarAct
SMARACT_CONFOCAL_PARK_X = SMARACT_PARK_X + _CONFOCAL_DX
SMARACT_CONFOCAL_PARK_Y = SMARACT_PARK_Y + _CONFOCAL_DY
# SmarAct SLC-1720  hard-stop travel limits (mm)
SMARACT_TRAVEL_MIN = -6.0
SMARACT_TRAVEL_MAX = 6.0
SMARACT_TRAVEL_MIN_NM = round(SMARACT_TRAVEL_MIN * 1_000_000)
SMARACT_TRAVEL_MAX_NM = round(SMARACT_TRAVEL_MAX * 1_000_000)
# center of travel + full bounds box size (12mm x 12mm)
SMARACT_CENTRE_X = (SMARACT_TRAVEL_MIN + SMARACT_TRAVEL_MAX) / 2.0
SMARACT_CENTRE_Y = (SMARACT_TRAVEL_MIN + SMARACT_TRAVEL_MAX) / 2.0
SMARACT_BOUNDS_W_MM = SMARACT_TRAVEL_MAX - SMARACT_TRAVEL_MIN
SMARACT_BOUNDS_H_MM = SMARACT_TRAVEL_MAX - SMARACT_TRAVEL_MIN
# Safety clearance height: Z is raised before any XY move during confocal auto-focus
_SAFE_CLEARANCE_Z_MM = 90.0
# The confocal auto-focus datum step starts from a single estimated Z (compensated for
# sample height) but that estimate can miss the sensor's narrow valid window (CL-Navigator's
# working range is roughly its ~15mm standoff +/- 1.3mm). Rather than fail outright on one
# guess, sweep Z around the estimate until a valid (non -99.9999) reading is found. Step must
# be smaller than the ~2.6mm-wide valid window so at least one step always lands inside it.
_AUTOFOCUS_SWEEP_RANGE_MM = 2.0
_AUTOFOCUS_SWEEP_STEP_MM = 0.5
# Bench-measured estimates for grid-scan "Est. Duration" readout:
# ~21 s fixed overhead to move to the SmarAct and home, common to both stages,
# then a per-point rate that differs by stage (SmarAct is much faster per point).
_GRID_SCAN_SETUP_S              = 21.0
_GRID_SCAN_PER_POINT_S_SMARACT  = 0.4356
_GRID_SCAN_PER_POINT_S_MODULE   = 3.152

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
        self.is_at_confocal = False

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

        # Which physical stage the current sample is mounted on, set from the
        # "Create New Sample" dialog's sample_location selection.
        self.use_smaract_stage = False
        self._compute_overlap = True  # mechanical vs visual stitch toggle, set per-scan
        self._smaract_scan_abort = False
        self._smaract_handle = None
        # Shared SmarAct connection state: the live Motion-tab position display and
        # an active scan both reuse the same handle; the lock serializes every
        # stage.py call against it, and the two "active" flags decide when it's
        # safe to actually close the connection.
        self._smaract_lock = Lock()
        self._smaract_poll_active = False
        self._smaract_scan_running = False
        self._smaract_move_active = False
        self._smaract_homing_active = False
        # Keeps the connection alive for the whole app session once opened at
        # startup, so Motion tab opens/scans never re-pay SA_OpenSystem's ~4s.
        # Only close_smaract_on_exit() clears this.
        self._smaract_startup_active = True
        self.current_tab = None
        # Grid parameters recorded by the most recent SmarAct scan, and whether
        # the currently-displayed stitched image was produced by one (lets
        # stitched-image click-to-move route to the right stage).
        self._smaract_last_grid = None
        self._last_stitched_was_smaract = False

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
        self.stitching_generation = 0    # incremented each scan; stale pollers use this to self-discard
        self.scan_in_progress = False    # set when scan command sent; cleared on state 0→1
        self.saw_scanning_status = False # True once Pi sends a "Scanning" status; prevents premature 0→1 trigger
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
        self._grid_datum_ij = (0, 0)     # (i, j) screen-space grid node used as the grid-scan datum;
                                          # (0, 0) = visual top-left, the default until overridden
        self._canvas_disp_w = 0          # displayed image width on canvas (px)
        self._canvas_disp_h = 0          # displayed image height on canvas (px)
        self._canvas_orig_w = 0          # original image width (sensor px)
        self._canvas_orig_h = 0          # original image height (sensor px)
        self._canvas_img_path = None     # path of image currently on canvas
        self._image_tab_render_pending = False   # debounce guard for resize re-render
        self._scan_progress_dot_id = None       # canvas item id of the live grid-scan dot
        self._scan_progress_dot_canvas = None   # which canvas that dot lives on
        # Custom point-selection state (right-click markers)
        self.custom_measure_points = []   # list of (phys_x_mm, phys_y_mm) tuples
        self._canvas_click_cache = {}     # (phys_x, phys_y) → (canvas_px, canvas_py) for Image tab
        self.measured_data = []           # list of (phys_x, phys_y, height) after a sequence
        self.analysis_selected_indices = []  # indices into measured_data currently highlighted
        self._show_heights_mode = False   # False: labels show point index, True: show measured height
        self.datum_point = None           # (phys_x, phys_y) of Ctrl+RClick datum, or None
        self._sequence_active = False     # True for the whole duration of a measurement/grid sequence

        # Material Removal tracking: every session (Reference + each Set) collects
        # its own points and fits its own best-fit plane; consecutive sessions'
        # plane-corrected points are then compared for material removed.
        self.material_sessions = {"Reference": []}    # session name -> [(x,y,z), ...] not-yet-baked points
        self.material_session_names = ["Reference"]   # ordered, grows via "New"
        self.material_active_session = "Reference"
        self.material_planes = {"Reference": None}    # session name -> (A,B,C,D) once calculated
        self.removal_data = {}                        # session name -> [(x,y,corrected_z), ...] from its own plane
        self._material_drawer_collapsed = True     # closed until the user clicks the arrow to open it
        self._material_capture_armed = False      # True while "Collect Points" is active
        self._material_drawer_frame = None
        self._material_drawer_anchor = None
        self._material_drawer_grid_column = None
        self._material_compare_a = None    # session names picked in the "Compare" dropdowns
        self._material_compare_b = None

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
        # created here (not just in display_motion_tab) so they exist even if the
        # Image tab or a sample gets created before Motion has ever been visited,
        # and because polling now starts at app launch, before Motion is ever built
        self.smaract_x_pos_var = ctk.StringVar(value="--")
        self.smaract_y_pos_var = ctk.StringVar(value="--")
        self.smaract_enabled_var = ctk.StringVar(value="--")

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

        # Connect to the SmarAct once, in the background, so opening the Motion
        # tab or starting a scan later doesn't block on SA_OpenSystem's ~4s.
        Thread(target=self._smaract_startup_connect, daemon=True).start()

        # Live SmarAct X/Y readout: runs for the whole session (not just while the
        # Motion tab is open), same as the module stage's own Live Position, since
        # the Image tab's Live Position also reads from this when a SmarAct sample
        # is active.
        self._start_smaract_position_polling()

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

        self.current_tab = tab_name

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

        # Right-side content: restore stitched map, or an in-progress/just-finished
        # scan's grid view, if one is active; else CAD placeholder
        if self.active_main_view == "stitched" and self.current_stitched_img_path:
            self.display_stitched_inline(self.current_stitched_img_path)
        elif self.active_main_view == "scanning":
            self.display_scanning_layout(self.scanning_grid_x, self.scanning_grid_y, self.main_right_frame)
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

        upload_csv_btn = ctk.CTkButton(left_frame, text="Import Coordinates", font=("Arial", 20),
                                       width=200, height=100, command=self.load_csv_points)
        upload_csv_btn.pack(pady=5, fill='x')

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

        # This can be entered directly (e.g. the "Image Stitching..." button)
        # without content_frame having been cleared first, so tear down any
        # drawer left over from a previous render before rebuilding one below.
        if self._material_drawer_frame is not None and self._material_drawer_frame.winfo_exists():
            self._material_drawer_frame.destroy()

        grid_x = getattr(self, 'scanning_grid_x', 1)
        grid_y = getattr(self, 'scanning_grid_y', 1)

        # ── Rebuild right frame content ───────────────────────────────────────
        self.clear_frame(self.main_right_frame)
        self._roi_active_canvas = None   # detach any ROI from a previous view

        # Button bar
        btn_bar = ctk.CTkFrame(self.main_right_frame)
        btn_bar.pack(side=ctk.TOP, fill='x', padx=5, pady=(5, 0))

        # Finish: save files, reset state, return to default main view.
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

        # smaract travel bounds box (12mm x 12mm, centered on smaract travel center)
        # only computed when this stitched image actually came from a smaract scan,
        # since converting mm -> stitched px needs that scan's grid pitch
        smaract_bounds_cx_px = None
        smaract_bounds_cy_px = None
        smaract_bounds_half_w_px = None
        smaract_bounds_half_h_px = None
        if self.use_smaract_stage and self._last_stitched_was_smaract and self._smaract_last_grid is not None:
            _sb_grid = self._smaract_last_grid
            _sb_t0x, _sb_t0y, _sb_nm_per_px_x, _sb_nm_per_px_y = self._smaract_stitched_tile_geometry(
                stitched_w, stitched_h, grid_x, grid_y, _sb_grid)
            _sb_cx_nm = SMARACT_CENTRE_X * 1_000_000
            _sb_cy_nm = SMARACT_CENTRE_Y * 1_000_000
            smaract_bounds_cx_px = _sb_t0x + (_sb_cx_nm - _sb_grid['start_x_nm']) / _sb_nm_per_px_x
            smaract_bounds_cy_px = _sb_t0y - (_sb_grid['start_y_nm'] - _sb_cy_nm) / _sb_nm_per_px_y
            smaract_bounds_half_w_px = (SMARACT_BOUNDS_W_MM * 1_000_000 / _sb_nm_per_px_x) / 2.0
            smaract_bounds_half_h_px = (SMARACT_BOUNDS_H_MM * 1_000_000 / _sb_nm_per_px_y) / 2.0

        # ── Initial FOV centre: inverse-map current hardware position ─────────
        tile0_cx = tile_w / 2.0
        tile0_cy = (grid_y - 1) * step_px_y + tile_h / 2.0

        if self._last_stitched_was_smaract and self._smaract_last_grid is not None:
            # SmarAct: same inverse as calculate_stitched_smaract_coords, using
            # the recorded grid spacing (exact) instead of the camera matrix,
            # against the SmarAct's own live position instead of the parked
            # optical carriage's.
            grid_params = self._smaract_last_grid
            step_px_x = tile_w * (1.0 - OVERLAP)
            if self._smaract_ensure_open():
                with self._smaract_lock:
                    curr_x_nm = get_position(self._smaract_handle, CHANNEL_X)
                    curr_y_nm = get_position(self._smaract_handle, CHANNEL_Y)
                col = (curr_x_nm - grid_params['start_x_nm']) / grid_params['step_x_nm']
                # SmarAct Y mounted opposite the camera's Y axis, same flip as the
                # scan route and the stitched-click inverse.
                row = (grid_params['start_y_nm'] - curr_y_nm) / grid_params['step_y_nm']
                init_fov_px = tile0_cx + col * step_px_x
                init_fov_py = tile0_cy - row * step_px_y
            else:
                init_fov_px, init_fov_py = tile0_cx, tile0_cy
        else:
            # Applies the same 2×2 matrix inverse used in
            # calculate_phys_to_stitched_pixel_coords, stopping before the canvas-
            # scale step since _s stores positions in full-res stitched pixels.
            A11, A12 = -0.001479,  0.000044
            A21, A22 =  0.000018,  0.001459
            det_B = A11 * A22 - A12 * A21          # = det(A)

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
            'bounds_half_w': 0.0, 'bounds_half_h': 0.0,
            'bounds_rect_id': None, 'bounds_label_id': None,
        }

        canvas = tk.Canvas(self.main_right_frame, bg="#1a1a1a",
                           highlightthickness=0, cursor="arrow")
        # Stashed so external callers (e.g. load_csv_points) can trigger a
        # lightweight re-render without rebuilding the whole stitched layout.
        self._stitched_canvas = canvas

        # ── ROI measurement control strip (BOTTOM, packed before canvas) ──────
        _stitch_strip = ctk.CTkFrame(self.main_right_frame)
        _stitch_strip.pack(side=ctk.BOTTOM, fill='x', padx=10, pady=(0, 5))

        _coord_strip = ctk.CTkFrame(self.main_right_frame, fg_color="transparent", height=20)
        _coord_strip.pack(side=ctk.BOTTOM, fill='x', padx=15, pady=(0, 5))

        ctk.CTkLabel(_coord_strip, text="Live Position: ", font=("Arial", 12, "bold")).pack(side="left")
        ctk.CTkLabel(_coord_strip, text="X:").pack(side="left", padx=(10, 2))
        ctk.CTkLabel(_coord_strip, textvariable=self.rpi_x_pos_var, text_color="cyan", font=("Arial", 12, "bold")).pack(side="left")
        ctk.CTkLabel(_coord_strip, text="Y:").pack(side="left", padx=(15, 2))
        ctk.CTkLabel(_coord_strip, textvariable=self.rpi_y_pos_var, text_color="cyan", font=("Arial", 12, "bold")).pack(side="left")
        ctk.CTkLabel(_coord_strip, text="Z:").pack(side="left", padx=(15, 2))
        ctk.CTkLabel(_coord_strip, textvariable=self.rpi_z_pos_var, text_color="cyan", font=("Arial", 12, "bold")).pack(side="left")

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
        # Start enabled if points/datum were already loaded (e.g. via CSV import)
        # before this view was ever rendered. otherwise the button would be
        # stuck disabled despite there being points ready to measure.
        self._stitch_measure_heights_btn = ctk.CTkButton(
            _ss_row1, text="Measure Heights", fg_color="#1f6aa5",
            state="normal" if (self.custom_measure_points or self.datum_point is not None) else "disabled",
            command=self.execute_custom_measurements)
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

        # Analysis readout + Display Heights/Indices toggle, stacked in the same
        # footprint as the two-button _stitch_action_frame beside it.
        _stitch_analysis_frame = ctk.CTkFrame(_ss_row2, fg_color="transparent")
        _stitch_analysis_frame.pack(side="left", padx=(8, 5))

        ctk.CTkLabel(_stitch_analysis_frame, textvariable=self.analysis_result_var,
                     font=("Arial", 12, "bold"), text_color="#00CFFF",
                     width=260).pack(side="top", pady=(0, 2))

        self._stitch_display_heights_btn = ctk.CTkButton(
            _stitch_analysis_frame,
            text="Display Indices" if self._show_heights_mode else "Display Heights",
            fg_color="#555555", state="disabled", width=260, height=24,
            command=self._toggle_display_heights_mode)
        self._stitch_display_heights_btn.pack(side="top", pady=0, fill="x")

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

        def _draw_smaract_bounds():
            # subtle thin dashed grey box marking the smaract's reachable travel area
            cx = _s['ox'] + smaract_bounds_cx_px * _s['sx']
            cy = _s['oy'] + smaract_bounds_cy_px * _s['sy']
            r_id = canvas.create_rectangle(
                cx - _s['bounds_half_w'], cy - _s['bounds_half_h'],
                cx + _s['bounds_half_w'], cy + _s['bounds_half_h'],
                outline="#888888", width=1, dash=(2, 4))
            l_id = canvas.create_text(
                cx - _s['bounds_half_w'] + 4, cy - _s['bounds_half_h'] + 4,
                anchor="nw", text="SmarAct Bounds", fill="#888888",
                font=("Arial", 8))
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

            # smaract travel bounds box, only for a smaract-sourced stitched image
            if smaract_bounds_cx_px is not None:
                _s['bounds_half_w'] = smaract_bounds_half_w_px * _s['sx']
                _s['bounds_half_h'] = smaract_bounds_half_h_px * _s['sy']
                _s['bounds_rect_id'], _s['bounds_label_id'] = _draw_smaract_bounds()

            # Reproject ROI grid using the fresh _s transform (zoom / pan safe)
            if (self._roi_active_canvas is canvas
                    and self.roi_phys_x_start is not None):
                if self._last_stitched_was_smaract and self._smaract_last_grid is not None:
                    # smaract points live in the smaract's own coordinate frame,
                    # not the camera/module-stage frame the matrix below assumes
                    _sg = self._smaract_last_grid
                    _t0x, _t0y, _nm_per_px_x, _nm_per_px_y = self._smaract_stitched_tile_geometry(
                        stitched_w, stitched_h, grid_x, grid_y, _sg)

                    def _p2c(pm_x, pm_y):
                        x_nm = pm_x * 1_000_000
                        y_nm = pm_y * 1_000_000
                        d_px = (x_nm - _sg['start_x_nm']) / _nm_per_px_x
                        d_py = (_sg['start_y_nm'] - y_nm) / _nm_per_px_y
                        fpx = _t0x + d_px
                        fpy = _t0y - d_py
                        return _s['ox'] + fpx * _s['sx'], _s['oy'] + fpy * _s['sy']
                else:
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

            # Redraw any custom measurement points (zoom/pan safe via _s)
            self._redraw_custom_points_stitched(
                canvas, _s, stitched_w, stitched_h,
                grid_x, grid_y, scan_origin_x, scan_origin_y)

            # Draw Dynamic FOV Scale Bar in Bottom Right
            # The canvas pixel width of the FOV is 2 * _s['half_cw']
            bar_px = _s['half_cw'] * 2

            # 30px padding from the bottom right corner
            margin = 30
            x1 = cw - margin
            y1 = ch - margin
            x0 = x1 - bar_px

            label_text = "5.60 mm"

            # Draw the scale bar line and end-caps
            canvas.create_line(x0, y1, x1, y1, fill="white", width=3)
            canvas.create_line(x0, y1-6, x0, y1+6, fill="white", width=3)
            canvas.create_line(x1, y1-6, x1, y1+6, fill="white", width=3)

            # Draw the text label
            canvas.create_text((x0 + x1) / 2, y1 - 15, text=label_text,
                               fill="white", font=("Arial", 12, "bold"))

        def _on_click(event):
            if self.module_status != "Idle":
                return
            if getattr(self, '_sequence_active', False):
                return

            full_px = (event.x - _s['ox']) / _s['sx']
            full_py = (event.y - _s['oy']) / _s['sy']

            if self._last_stitched_was_smaract:
                grid_params = self._smaract_last_grid
                if grid_params is None:
                    return
                x_nm, y_nm = self.calculate_stitched_smaract_coords(
                    full_px, full_py,
                    stitched_w, stitched_h,
                    grid_x, grid_y,
                    grid_params,
                )

                cx, cy = event.x, event.y

                def _on_smaract_click_move_complete():
                    # Only move the FOV rectangle once the SmarAct move actually
                    # succeeds. a rejected (e.g. negative-coordinate) or failed
                    # move must leave the rectangle exactly where it was.
                    _s['fov_px'] = full_px
                    _s['fov_py'] = full_py
                    if _s['rect_id'] is not None and _s['label_id'] is not None:
                        canvas.coords(_s['rect_id'],
                                       cx - _s['half_cw'], cy - _s['half_ch'],
                                       cx + _s['half_cw'], cy + _s['half_ch'])
                        canvas.coords(_s['label_id'],
                                       cx - _s['half_cw'] + 4, cy - _s['half_ch'] + 4)
                    else:
                        _s['rect_id'], _s['label_id'] = _draw_fov()

                self._smaract_move_to(x_nm, y_nm, on_complete=_on_smaract_click_move_complete)
                return

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

        # Stashed for the same reason as self._stitched_canvas above: lets
        # load_csv_points (and similar) request a redraw without a full rebuild.
        self._schedule_render = _schedule_render

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
        canvas.bind("<Control-ButtonRelease-3>",
                    lambda e, _c=canvas, _ss=_s: self._on_datum_point_stitched(
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

        # Material Removal drawer: left of the stitched canvas, right of left_frame
        self._build_material_drawer(self.content_frame, before_widget=self.main_right_frame)

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
        image_scanning_window.geometry("335x245")  # Set initial size
        image_scanning_window.minsize(335, 245)   # Limit the minimum size
        image_scanning_window.maxsize(335, 245)   # Limit the maximum size

        image_scanning_window.after(100, image_scanning_window.grab_set)

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

        # toggle mechanical vs visual stitch, sized to match the label text, no hover fill
        compute_overlap_var = ctk.BooleanVar(value=True)
        compute_overlap_check = ctk.CTkCheckBox(image_scanning_window, text="Compute Image Overlap",
                                                variable=compute_overlap_var,
                                                font=("Arial", 12), checkbox_width=16, checkbox_height=16,
                                                hover=False)
        compute_overlap_check.grid(row=4, column=0, columnspan=4, padx=5, pady=5, sticky="ew")

        # OK button (closes the window, changes frame, empties rpi image buffer, starts scan)
        ok_button = ctk.CTkButton(image_scanning_window, text="OK",
                                command=lambda: [
                                    self._start_scan(int(step_x.get()), int(step_y.get()), frame, compute_overlap_var.get()),
                                    image_scanning_window.destroy()],
                                width=80, state="disabled")  # Initially disabled
        ok_button.grid(row=5, column=0, padx=5, pady=10, sticky="ew")

        # Cancel button (closes the window)
        cancel_button = ctk.CTkButton(image_scanning_window, text="Cancel", command=image_scanning_window.destroy, width=80)
        cancel_button.grid(row=5, column=3, columnspan=2, padx=5, pady=10, sticky="ew")

        # Ensure the buttons are always at the bottom of the window
        image_scanning_window.grid_rowconfigure(5, weight=1)  # Add this line to allow the window to expand as needed
        image_scanning_window.grid_rowconfigure(4, weight=0)  # Ensure row 4 (buttons) stays at the bottom

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
        # Toggle button: Switch stage between Confocal and Optical positions
        self.confocal_toggle_btn = ctk.CTkButton(
            button_frame,
            text="Confocal",
            font=("Arial", 14),
            fg_color="green",
            command=self.toggle_interferometer_camera
        )
        self.confocal_toggle_btn.pack(pady=5, fill='x')

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
        ctk.CTkLabel(main_frame, text="Optical Stage:", font=("Arial", 14, "bold")).pack(pady=(10, 2), fill='x')

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

        # SmarAct Stage: live position display (nanometers from the MCS1, shown in mm)
        ctk.CTkLabel(main_frame, text="SmarAct Stage:", font=("Arial", 14, "bold")).pack(pady=(15, 2), fill='x')

        smaract_enabled_label = ctk.CTkLabel(main_frame, text="SmarAct Enabled")
        smaract_enabled_label.pack(pady=5, fill='x')
        # var lives in __init__ (see above); only the label is rebuilt here
        ctk.CTkLabel(main_frame, textvariable=self.smaract_enabled_var).pack(pady=5, fill='x')

        smaract_x_pos_label = ctk.CTkLabel(main_frame, text="X Position (mm)")
        smaract_x_pos_label.pack(pady=5, fill="x")
        # var itself lives in __init__ (persistent across tab rebuilds); only the
        # label is rebuilt here, so other readouts bound to it (e.g. the Image
        # tab's Live Position) don't get orphaned on a Motion tab revisit
        ctk.CTkLabel(main_frame, textvariable=self.smaract_x_pos_var).pack(pady=5, fill='x')

        smaract_y_pos_label = ctk.CTkLabel(main_frame, text="Y Position (mm)")
        smaract_y_pos_label.pack(pady=5, fill="x")
        ctk.CTkLabel(main_frame, textvariable=self.smaract_y_pos_var).pack(pady=5, fill='x')
        # polling itself now runs for the whole app session (started once at
        # launch), not restarted per tab visit — see __init__

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

        # Material Removal drawer occupies column 1, between the camera params
        # and the image canvas.
        self._build_material_drawer(self.content_frame, grid_column=1)

        right_frame = ctk.CTkFrame(self.content_frame)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=10, pady=10)

        # Make the right column expand with the window resizing
        self.content_frame.grid_columnconfigure(2, weight=1, minsize=200)  # Image column (column 2)
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
        def _render_image_tab():
            self._image_tab_render_pending = False
            if not self._image_tab_canvas.winfo_exists() or self._canvas_img_path is None:
                return
            self._show_image_on_canvas(os.path.dirname(self._canvas_img_path), self._image_tab_canvas)

        def _schedule_image_tab_render(e):
            # keep the placeholder text centered even before an image is ever loaded
            self._image_tab_canvas.coords("placeholder_text", e.width / 2, e.height / 2)
            # A real size change (e.g. the Material Removal drawer opening/closing)
            # moves where the image itself gets drawn, so cached exact-pixel marker
            # positions go stale. Drop them so the redraw falls back to the
            # physics-based transform, which tracks the new canvas size correctly.
            last_wh = getattr(self, '_image_tab_canvas_last_wh', None)
            if last_wh != (e.width, e.height):
                self._image_tab_canvas_last_wh = (e.width, e.height)
                self._canvas_click_cache.clear()
            if self._canvas_img_path is None:
                return
            if not self._image_tab_render_pending:
                self._image_tab_render_pending = True
                self.after(60, _render_image_tab)

        self._image_tab_canvas.bind("<Configure>", _schedule_image_tab_render)

        coord_strip = ctk.CTkFrame(right_frame, fg_color="transparent", height=20)
        coord_strip.pack(fill='x', padx=15, pady=(0, 5))

        ctk.CTkLabel(coord_strip, text="Live Position: ", font=("Arial", 12, "bold")).pack(side="left")
        ctk.CTkLabel(coord_strip, text="X:").pack(side="left", padx=(10, 2))
        # X/Y textvariable swaps to the SmarAct's own live position when a SmarAct
        # sample is active (see send_sample_data); Z always stays the optical
        # assembly's, since the SmarAct doesn't track its own Z.
        _init_x_var = self.smaract_x_pos_var if self.use_smaract_stage else self.rpi_x_pos_var
        _init_y_var = self.smaract_y_pos_var if self.use_smaract_stage else self.rpi_y_pos_var
        self._image_tab_x_pos_label = ctk.CTkLabel(
            coord_strip, textvariable=_init_x_var, text_color="cyan", font=("Arial", 12, "bold"))
        self._image_tab_x_pos_label.pack(side="left")
        ctk.CTkLabel(coord_strip, text="Y:").pack(side="left", padx=(15, 2))
        self._image_tab_y_pos_label = ctk.CTkLabel(
            coord_strip, textvariable=_init_y_var, text_color="cyan", font=("Arial", 12, "bold"))
        self._image_tab_y_pos_label.pack(side="left")
        ctk.CTkLabel(coord_strip, text="Z:").pack(side="left", padx=(15, 2))
        ctk.CTkLabel(coord_strip, textvariable=self.rpi_z_pos_var, text_color="cyan", font=("Arial", 12, "bold")).pack(side="left")

        # ROI measurement control strip (two rows)
        self._roi_active_canvas = None   # reset on each Image tab load
        roi_strip = ctk.CTkFrame(right_frame)
        roi_strip.pack(fill='x', padx=10, pady=(0, 10))

        # ── Row 1: inputs (left) + Measure Heights (right) ───────────────────────
        row1 = ctk.CTkFrame(roi_strip)
        row1.pack(fill='x', padx=5, pady=(5, 2))

        # Measure Heights owns the far-right of row1; packed first to claim space
        # Start enabled if points/datum were already loaded (e.g. via CSV import)
        # before this tab was ever rendered. otherwise the button would be stuck
        # disabled despite there being points ready to measure.
        self._measure_heights_btn = ctk.CTkButton(
            row1, text="Measure Heights", fg_color="#1E6FA8",
            state="normal" if (self.custom_measure_points or self.datum_point is not None) else "disabled",
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

        # Analysis result + Display Heights/Indices toggle, stacked in the same
        # footprint as the two-button _action_frame beside it so this row doesn't grow.
        _analysis_frame = ctk.CTkFrame(row2, fg_color="transparent")
        _analysis_frame.pack(side="left", padx=(8, 5))

        self.analysis_result_var = ctk.StringVar(value="Analysis:")
        ctk.CTkLabel(_analysis_frame, textvariable=self.analysis_result_var,
                     font=("Arial", 12, "bold"), text_color="#00CFFF",
                     width=260).pack(side="top", pady=(0, 2))

        self._display_heights_btn = ctk.CTkButton(
            _analysis_frame,
            text="Display Indices" if self._show_heights_mode else "Display Heights",
            fg_color="#555555", state="disabled", width=260, height=24,
            command=self._toggle_display_heights_mode)
        self._display_heights_btn.pack(side="top", pady=0, fill="x")

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

    def click_to_move(self, event):
        """
        Translates image clicks into stage movement
        """
        if event.state & 0x0004:  # Ctrl held: ROI draw mode, not a move command
            return
        if getattr(self, '_roi_pan_active', False):  # ROI box drag in progress
            return
        if self.module_status != "Idle":
            return
        if getattr(self, '_sequence_active', False):
            return

        # Read the current display geometry directly (same source of truth as
        # _canvas_pixel_to_phys) instead of a value captured once at image-load
        # time, so this stays correct even if the canvas was resized since.
        img_disp_width  = self._canvas_disp_w
        img_disp_height = self._canvas_disp_h
        orig_img_width  = self._canvas_orig_w
        orig_img_height = self._canvas_orig_h
        if img_disp_width == 0 or img_disp_height == 0:
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

        if self.use_smaract_stage:
            # Same camera/optics, so the pixel->mm delta is reused as-is; it's
            # added to the SmarAct's own live position instead of the optical
            # carriage's, and sent via the SmarAct move primitive (Z untouched).
            if not self._smaract_ensure_open():
                messagebox.showerror("SmarAct Error", "Could not open SmarAct system.")
                return
            with self._smaract_lock:
                curr_x_nm = get_position(self._smaract_handle, CHANNEL_X)
                curr_y_nm = get_position(self._smaract_handle, CHANNEL_Y)
            # SmarAct Y is mounted opposite the camera's Y axis, flip it
            x_nm = curr_x_nm + round(delta_x * 1_000_000)
            y_nm = curr_y_nm - round(delta_y * 1_000_000)
            print(f"Moving SmarAct to X: {x_nm} nm, Y: {y_nm} nm")

            image_label = event.widget

            def _capture_after_smaract_move():
                # mirrors sequence_wait_for_move's tail once the SmarAct arrives
                self.empty_folder_rpi()
                self.send_simple_command("exe_update_image", checkIdle=False, show_success=False)
                self.empty_folder_pc(self.buffer_testing_folder)
                self.module_status = "Capturing Image"
                self.status_lockout_time = time.time() + 0.5
                self.sequence_wait_for_capture(image_label)

            self._smaract_move_to(x_nm, y_nm, on_complete=_capture_after_smaract_move)
            return

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
            # Only a genuinely new photo means the stage was actually at "now"
            # when the pixels were captured. A redraw of the SAME image (e.g.
            # the Material Removal drawer toggling and resizing this canvas)
            # must NOT re-stamp the physical reference position, or the ROI/
            # grid box (which is re-projected from that reference on every
            # redraw) visually drifts away from the still-unchanged image.
            is_new_image = (image_path != getattr(self, '_canvas_img_path', None))
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

                # fit to canvas preserving aspect ratio: compare image aspect vs
                # canvas aspect (not just the image's own aspect) so a canvas
                # proportionally wider/taller than the image doesn't overflow and
                # get clipped by the canvas bounds. same pattern as the stitched
                # view's _render().
                if img_pil.width / img_pil.height > canvas_w / canvas_h:
                    new_width  = canvas_w
                    new_height = int(canvas_w * img_pil.height / img_pil.width)
                else:
                    new_height = canvas_h
                    new_width  = int(canvas_h * img_pil.width / img_pil.height)

                new_width  = max(new_width, 1)
                new_height = max(new_height, 1)

                self._canvas_disp_w = new_width
                self._canvas_disp_h = new_height
                self._canvas_orig_w = img_pil.width
                self._canvas_orig_h = img_pil.height
                # Capture hardware position so _phys_to_canvas_pixel has a stable
                # reference even if the stage moves before the next redraw. Only
                # do this for a genuinely new photo (see is_new_image above) —
                # re-stamping it on every redraw of the same image is what let
                # the ROI/grid box drift after the stage moved mid-scan.
                if is_new_image or not hasattr(self, '_image_tab_ref_x'):
                    self._image_tab_ref_x = float(self.x_pos)
                    self._image_tab_ref_y = float(self.y_pos)
                    # SmarAct samples: points are stored in the SmarAct's own coordinate
                    # frame (see _canvas_pixel_to_phys), not the gantry's, so the redraw
                    # path needs the SmarAct's live position at capture time too.
                    if self.use_smaract_stage and self._smaract_ensure_open():
                        with self._smaract_lock:
                            self._image_tab_ref_smaract_x = get_position(self._smaract_handle, CHANNEL_X) / 1_000_000
                            self._image_tab_ref_smaract_y = get_position(self._smaract_handle, CHANNEL_Y) / 1_000_000

                resized_img = img_pil.resize((new_width, new_height), Image.LANCZOS)
                self._canvas_img_tk = ImageTk.PhotoImage(resized_img)

                canvas.delete("all")
                canvas.create_image(canvas_w // 2, canvas_h // 2, anchor="center",
                                    image=self._canvas_img_tk)

                # Redraw any custom measurement points that survived the canvas wipe
                self._redraw_custom_points_image_tab(canvas, canvas_w, canvas_h)

                # Reproject the ROI/Map-Surface grid box too, so it doesn't visually
                # detach from the image after a resize (image geometry above may have
                # just changed; the grid's stored canvas coords would otherwise be stale).
                if self._roi_active_canvas is canvas and self.roi_phys_x_start is not None:
                    if self.use_smaract_stage:
                        _roi_ref_x = getattr(self, '_image_tab_ref_smaract_x', None)
                        _roi_ref_y = getattr(self, '_image_tab_ref_smaract_y', None)
                    else:
                        _roi_ref_x = getattr(self, '_image_tab_ref_x', float(self.x_pos))
                        _roi_ref_y = getattr(self, '_image_tab_ref_y', float(self.y_pos))
                    if _roi_ref_x is not None and _roi_ref_y is not None:
                        rx0, ry0 = self._phys_to_canvas_pixel(
                            self.roi_phys_x_start, self.roi_phys_y_start,
                            _roi_ref_x, _roi_ref_y, canvas_w, canvas_h)
                        rx1, ry1 = self._phys_to_canvas_pixel(
                            self.roi_phys_x_end, self.roi_phys_y_end,
                            _roi_ref_x, _roi_ref_y, canvas_w, canvas_h)
                        if rx0 is not None and rx1 is not None:
                            self._roi_canvas_x0 = min(rx0, rx1)
                            self._roi_canvas_y0 = min(ry0, ry1)
                            self._roi_canvas_x1 = max(rx0, rx1)
                            self._roi_canvas_y1 = max(ry0, ry1)
                            self._roi_redraw_grid(canvas, self._roi_canvas_x0, self._roi_canvas_y0,
                                                  self._roi_canvas_x1, self._roi_canvas_y1)

                canvas.bind("<Double-Button-1>", lambda e: self.expand_image(image_path))
                # <Button-1> dispatches to pan-drag (if inside ROI box) or click-to-move
                canvas.bind("<Button-1>",        lambda e: self._roi_or_move_press(e, canvas))
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
                canvas.bind("<Control-ButtonRelease-3>",
                            lambda e: self._on_datum_point_image(e, canvas))

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

        delta_x = A11 * delta_i + A12 * delta_j
        delta_y = A21 * delta_i + A22 * delta_j

        if self.use_smaract_stage:
            # Same camera/optics as the optical case, so the delta-mm math is
            # reused as-is; only the position it's added to differs. Points
            # produced here (ROI corners, measurement points) end up as
            # absolute SmarAct-frame mm coordinates, self-consistent for the
            # rest of the session since the SmarAct doesn't move again until
            # a sequence explicitly commands it.
            if not self._smaract_ensure_open():
                return None, None
            with self._smaract_lock:
                curr_x_nm = get_position(self._smaract_handle, CHANNEL_X)
                curr_y_nm = get_position(self._smaract_handle, CHANNEL_Y)
            # SmarAct Y is mounted opposite the camera's Y axis, flip it
            phys_x = curr_x_nm / 1_000_000 + delta_x
            phys_y = curr_y_nm / 1_000_000 - delta_y
            # No max(0.0, ...) clamp here, unlike the module-stage branch below:
            # the SmarAct's travel range is symmetric (SMARACT_TRAVEL_MIN/MAX,
            # negative values are legitimate), and the callers that actually
            # dispatch a move already validate against that real range with a
            # proper error dialog — clamping to 0 here would silently corrupt
            # the coordinate instead (e.g. two ROI corners that are both
            # genuinely negative would both clamp to 0.0, collapsing the
            # dragged box to a zero-size region).
            return phys_x, phys_y

        phys_x = float(self.x_pos) + delta_x
        phys_y = float(self.y_pos) + delta_y

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
                           was captured (the stage position at scan start).
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
        # sits at the largest y values (its top edge is at (grid_y-1)*step_px_y).
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

    def calculate_stitched_smaract_coords(
        self,
        px: float,
        py: float,
        stitched_w: int,
        stitched_h: int,
        grid_x: int,
        grid_y: int,
        smaract_grid: dict,
    ) -> tuple:
        """
        Convert a pixel position on a SmarAct-produced stitched image to an
        absolute SmarAct nanometer coordinate.

        Unlike calculate_stitched_phys_coords, this doesn't use the camera's
        empirical calibration matrix — the SmarAct's own recorded grid pitch
        (nm per tile step) gives an exact nm-per-pixel scale instead, and the
        click interpolates continuously against it, same as the optical case.
        Snapping to the nearest tile center was the old (wrong) behavior here.

        Same tile geometry/ordering as calculate_stitched_phys_coords (Fiji
        "Grid: column-by-column, Up & Right", tile 0 = physical bottom-left).
        """
        tile0_cx, tile0_cy, nm_per_px_x, nm_per_px_y = self._smaract_stitched_tile_geometry(
            stitched_w, stitched_h, grid_x, grid_y, smaract_grid)

        d_px = px - tile0_cx
        d_py = tile0_cy - py  # image y grows downward, visual position grows upward

        # SmarAct Y is mounted opposite the camera's Y axis (same fact fixed for
        # click-to-move and the scan route): ascending visual position means
        # descending native Y, so this is a minus, not a plus.
        x_nm = smaract_grid['start_x_nm'] + d_px * nm_per_px_x
        y_nm = smaract_grid['start_y_nm'] - d_py * nm_per_px_y

        return round(x_nm), round(y_nm)

    def _smaract_stitched_tile_geometry(self, stitched_w, stitched_h, grid_x, grid_y, smaract_grid):
        """Shared tile geometry + nm-per-pixel scale for a SmarAct-produced stitched
        image (used by calculate_stitched_smaract_coords and the stitched-view ROI-drag
        handlers, which need the same scale to convert a desired mm cell size back into
        canvas pixels)."""
        OVERLAP = 0.20
        tile_w = stitched_w / (1.0 + (grid_x - 1) * (1.0 - OVERLAP))
        tile_h = stitched_h / (1.0 + (grid_y - 1) * (1.0 - OVERLAP))
        step_px_x = tile_w * (1.0 - OVERLAP)
        step_px_y = tile_h * (1.0 - OVERLAP)

        tile0_cx = tile_w / 2.0
        tile0_cy = (grid_y - 1) * step_px_y + tile_h / 2.0

        nm_per_px_x = smaract_grid['step_x_nm'] / step_px_x
        nm_per_px_y = smaract_grid['step_y_nm'] / step_px_y

        return tile0_cx, tile0_cy, nm_per_px_x, nm_per_px_y

    def _stitched_pixel_to_phys(self, full_px, full_py, stitched_w, stitched_h,
                                 grid_x, grid_y, scan_origin_x, scan_origin_y):
        """Full-res stitched-image pixel -> physical mm. Routes through the SmarAct-aware
        conversion when the active stitched image came from a SmarAct scan (matching the
        point-placement and click-to-move handlers); otherwise the camera/module-stage path.
        Returns (None, None) if a SmarAct image is active but its grid params aren't
        available (shouldn't normally happen, but avoids a crash if it does)."""
        if self._last_stitched_was_smaract:
            grid_params = self._smaract_last_grid
            if grid_params is None:
                return None, None
            x_nm, y_nm = self.calculate_stitched_smaract_coords(
                full_px, full_py, stitched_w, stitched_h, grid_x, grid_y, grid_params)
            return x_nm / 1_000_000, y_nm / 1_000_000
        return self.calculate_stitched_phys_coords(
            full_px, full_py, stitched_w, stitched_h, grid_x, grid_y, scan_origin_x, scan_origin_y)

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
                                 the position is outside the scanned area (no
                                 boundary clamping is applied, edge-behaviour rule).
        """
        OVERLAP = 0.20

        # ── Step 1: Tile geometry (identical to the forward function) ─────────
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

    def calculate_smaract_phys_to_stitched_pixel_coords(
        self, phys_x, phys_y, stitched_w, stitched_h, grid_x, grid_y,
        smaract_grid, canvas_w, canvas_h,
    ):
        """Inverse of calculate_stitched_smaract_coords: SmarAct-frame mm -> canvas pixel
        on the displayed stitched image. Same role as calculate_phys_to_stitched_pixel_coords
        but using the SmarAct's own recorded grid pitch instead of the camera calibration
        matrix, since SmarAct points live in a different coordinate frame (see
        calculate_stitched_smaract_coords)."""
        tile0_cx, tile0_cy, nm_per_px_x, nm_per_px_y = self._smaract_stitched_tile_geometry(
            stitched_w, stitched_h, grid_x, grid_y, smaract_grid)

        x_nm = phys_x * 1_000_000
        y_nm = phys_y * 1_000_000
        d_px = (x_nm - smaract_grid['start_x_nm']) / nm_per_px_x
        d_py = (smaract_grid['start_y_nm'] - y_nm) / nm_per_px_y
        full_px = tile0_cx + d_px
        full_py = tile0_cy - d_py

        # Canvas display layout (mirrors _render in display_stitched_inline; same
        # simplification as calculate_phys_to_stitched_pixel_coords — assumes no
        # zoom/pan, i.e. fit-to-canvas).
        if stitched_w / stitched_h > canvas_w / canvas_h:
            disp_w = canvas_w
            disp_h = max(1, int(canvas_w * stitched_h / stitched_w))
        else:
            disp_h = canvas_h
            disp_w = max(1, int(canvas_h * stitched_w / stitched_h))
        ox = (canvas_w - disp_w) / 2.0
        oy = (canvas_h - disp_h) / 2.0
        sx = disp_w / stitched_w
        sy = disp_h / stitched_h

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
        """Begin a new Ctrl+drag ROI (clears the previous grid)."""
        # Prevent overwriting ROI globals from the micro-view while macro-view is active
        if getattr(self, 'active_main_view', 'default') == 'stitched' and canvas is getattr(self, '_image_tab_canvas', None):
            messagebox.showwarning("Action Blocked", "Please click 'Finish' on the stitched image tab (Main) first before drawing regions on the Image tab.")
            return
        self._roi_drag_start = (event.x, event.y)
        canvas.delete("roi_grid")
        self._grid_datum_ij = (0, 0)   # new grid: reset the datum pick back to top-left
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

    def _draw_datum_pt_marker(self, canvas, cx, cy):
        """Draw the cyan crosshair + pink dot datum marker at canvas position (cx, cy)."""
        R = 10
        canvas.create_line(cx - R, cy, cx + R, cy,
                           fill="#00CFFF", width=2, tags="datum_pt")
        canvas.create_line(cx, cy - R, cx, cy + R,
                           fill="#00CFFF", width=2, tags="datum_pt")
        canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                           fill="pink", outline="#00CFFF", width=1, tags="datum_pt")

    def _resolve_point_canvas_xy(self, phys_x, phys_y, ref_x, ref_y, canvas_w, canvas_h):
        """Canvas pixel position for a measurement point/datum on the (non-stitched)
        Image tab. Always prefers the exact pixel position cached at click time
        (_canvas_click_cache), so markers and labels never drift or vanish on redraw
        even if the live stage position has changed since the points were placed —
        this is what makes them stay put across a Display Heights/Indices toggle.
        Only falls back to the physics-based inverse transform (which can be off if
        the reference position has since moved) when no cache entry exists at all,
        and always logs that fact so a genuine cache miss is never silent."""
        cached = self._canvas_click_cache.get((phys_x, phys_y))
        if cached is not None:
            return cached
        print(f"[canvas] WARNING: no cached click position for ({phys_x:.6f}, {phys_y:.6f}) mm "
              f"— using computed fallback position (may be approximate)")
        if ref_x is None or ref_y is None:
            return None, None
        return self._phys_to_canvas_pixel(phys_x, phys_y, ref_x, ref_y, canvas_w, canvas_h)

    def _redraw_custom_points_image_tab(self, canvas, canvas_w, canvas_h):
        """Re-stamp all custom_measure_points and measured_data text on the Image
        tab canvas after a canvas.delete('all'). Every marker/label is placed at its
        exact click-time pixel position (see _resolve_point_canvas_xy), so nothing
        drifts even though the live stage position may have changed since (e.g.
        after a SmarAct measurement sequence parks somewhere else)."""
        if not self.custom_measure_points and not self.measured_data and self.datum_point is None:
            return
        if self.use_smaract_stage:
            ref_x = getattr(self, '_image_tab_ref_smaract_x', None)
            ref_y = getattr(self, '_image_tab_ref_smaract_y', None)
        else:
            ref_x = getattr(self, '_image_tab_ref_x', float(self.x_pos))
            ref_y = getattr(self, '_image_tab_ref_y', float(self.y_pos))
        # Re-draw datum marker if one was placed
        if self.datum_point is not None:
            dcx, dcy = self._resolve_point_canvas_xy(
                self.datum_point[0], self.datum_point[1], ref_x, ref_y, canvas_w, canvas_h)
            if dcx is not None:
                self._draw_datum_pt_marker(canvas, dcx, dcy)
        for i, (phys_x, phys_y) in enumerate(self.custom_measure_points):
            cx, cy = self._resolve_point_canvas_xy(phys_x, phys_y, ref_x, ref_y,
                                                    canvas_w, canvas_h)
            if cx is None:
                continue
            self._draw_custom_pt_marker(canvas, cx, cy)
        # Re-draw height text for any completed measurements
        for i, (phys_x, phys_y, height) in enumerate(self.measured_data):
            cx, cy = self._resolve_point_canvas_xy(phys_x, phys_y, ref_x, ref_y, canvas_w, canvas_h)
            if cx is None:
                continue
            is_datum = (self.datum_point is not None and (phys_x, phys_y) == self.datum_point)
            label, fill = self._measurement_label_fill(i, height, is_datum)
            canvas.create_text(cx, cy - 15, text=label,
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
        if not self.custom_measure_points and not self.measured_data and self.datum_point is None:
            return

        if self._last_stitched_was_smaract:
            # SmarAct points live in the SmarAct's own coordinate frame, not the
            # camera/module-stage frame the calibration matrix below assumes (see
            # calculate_stitched_smaract_coords) — use its recorded grid pitch instead.
            grid_params = self._smaract_last_grid
            if grid_params is None:
                return
            _t0x, _t0y, _nm_per_px_x, _nm_per_px_y = self._smaract_stitched_tile_geometry(
                stitched_w, stitched_h, grid_x, grid_y, grid_params)

            def _phys_to_canvas(phys_x, phys_y):
                x_nm = phys_x * 1_000_000
                y_nm = phys_y * 1_000_000
                d_px = (x_nm - grid_params['start_x_nm']) / _nm_per_px_x
                d_py = (grid_params['start_y_nm'] - y_nm) / _nm_per_px_y
                fpx = _t0x + d_px
                fpy = _t0y - d_py
                return _s['ox'] + fpx * _s['sx'], _s['oy'] + fpy * _s['sy']
        else:
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

        # Re-draw datum marker if one was placed
        if self.datum_point is not None:
            dcx, dcy = _phys_to_canvas(self.datum_point[0], self.datum_point[1])
            self._draw_datum_pt_marker(canvas, dcx, dcy)

        # Crosshair markers for custom measurement points
        for i, (phys_x, phys_y) in enumerate(self.custom_measure_points):
            cx, cy = _phys_to_canvas(phys_x, phys_y)
            self._draw_custom_pt_marker(canvas, cx, cy)

        # Height text (measured_data is in optimised order; use its own phys coords)
        for i, (phys_x, phys_y, height) in enumerate(self.measured_data):
            cx, cy = _phys_to_canvas(phys_x, phys_y)
            is_datum = (self.datum_point is not None and (phys_x, phys_y) == self.datum_point)
            label, fill = self._measurement_label_fill(i, height, is_datum)
            canvas.create_text(cx, cy - 15, text=label,
                               fill=fill, font=("Arial", 12, "bold"),
                               tags=("custom_pt", "measurement_text", f"meas_idx_{i}"))

        if self.measured_data:
            canvas.tag_bind("measurement_text", "<Button-1>", self._toggle_analysis_point)

    def _on_right_click_point(self, event, canvas):
        """<Button-3>: drop a measurement marker at the clicked canvas position."""
        if getattr(self, 'active_main_view', 'default') == 'stitched':
            messagebox.showwarning("Action Blocked",
                "Please click 'Finish' on the stitched image tab (Main) first "
                "before taking measurements on the Image tab.")
            return
        if event.state & 0x4:  # Ctrl held: this is a datum drop, handled separately
            return
        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        phys_x, phys_y = self._canvas_pixel_to_phys(event.x, event.y, canvas_w, canvas_h)
        if phys_x is None or phys_y is None:
            return

        self.custom_measure_points.append((phys_x, phys_y))
        self._canvas_click_cache[(phys_x, phys_y)] = (event.x, event.y)
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

    def _smaract_point_out_of_bounds(self, phys_x, phys_y):
        """True (and shows the error) if (phys_x, phys_y) falls outside the
        SmarAct's [-6, 6] mm travel box — only meaningful for a SmarAct-sourced
        stitched image, where that box is what's actually drawn on screen."""
        if not (SMARACT_TRAVEL_MIN <= phys_x <= SMARACT_TRAVEL_MAX
                and SMARACT_TRAVEL_MIN <= phys_y <= SMARACT_TRAVEL_MAX):
            messagebox.showerror("Out of Bounds",
                "Height measurements must be taken within the SmarAct's boundary.")
            return True
        return False

    def _on_stitched_right_click_point(self, event, canvas, _s,
                                       stitched_w, stitched_h,
                                       grid_x, grid_y,
                                       scan_origin_x, scan_origin_y):
        """<ButtonRelease-3> handler for the stitched canvas.

        Drops a custom measurement marker only when the release follows a clean
        right-click (no significant pan drag).  Converts canvas pixels → full
        stitched-image pixels → physical mm using the standard helper.
        """
        # Ctrl+RClick is a datum drop: let _on_datum_point_stitched handle it
        if event.state & 0x4:
            return
        # Ignore if the user was panning (drag threshold = 5 px).
        # Use _pan_origin_x/y (set once on press) not _pan_start_x/y (reset each
        # _do_pan tick), so the total drag distance is measured correctly.
        start_x = getattr(canvas, '_pan_origin_x', event.x)
        start_y = getattr(canvas, '_pan_origin_y', event.y)
        if abs(event.x - start_x) > 5 or abs(event.y - start_y) > 5:
            return

        # Canvas px → full-res stitched px → physical mm
        full_px = (event.x - _s['ox']) / _s['sx']
        full_py = (event.y - _s['oy']) / _s['sy']
        if self._last_stitched_was_smaract:
            grid_params = self._smaract_last_grid
            if grid_params is None:
                return
            x_nm, y_nm = self.calculate_stitched_smaract_coords(
                full_px, full_py,
                stitched_w, stitched_h,
                grid_x, grid_y,
                grid_params,
            )
            phys_x, phys_y = x_nm / 1_000_000, y_nm / 1_000_000
            if self._smaract_point_out_of_bounds(phys_x, phys_y):
                return
        else:
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

    def _pick_grid_datum_node(self, event, canvas):
        """If a grid is currently drawn on *canvas*, snap this Ctrl+Right-Click to the
        nearest grid node and use it as the grid-scan datum instead of an arbitrary
        point. Returns True if handled (caller should return without falling through
        to the ordinary arbitrary-datum-point logic), False if no grid is present."""
        if not (self._roi_active_canvas is canvas
                and self._roi_canvas_x0 < self._roi_canvas_x1):
            return False
        x0, y0 = self._roi_canvas_x0, self._roi_canvas_y0
        x1, y1 = self._roi_canvas_x1, self._roi_canvas_y1
        nx = max(2, self.map_grid_x)
        ny = max(2, self.map_grid_y)
        i, j = self._nearest_grid_node(event.x, event.y, x0, y0, x1, y1, nx, ny)
        self._grid_datum_ij = (i, j)
        self._roi_redraw_grid(canvas, x0, y0, x1, y1)
        print(f"[grid_datum] node ({i},{j}) selected as grid-scan datum")
        return True

    def _on_datum_point_image(self, event, canvas):
        """<Control-ButtonRelease-3> on the Image tab: place or replace the datum marker."""
        if getattr(self, 'active_main_view', 'default') == 'stitched':
            messagebox.showwarning("Action Blocked",
                "Please click 'Finish' on the stitched image tab (Main) first "
                "before taking measurements on the Image tab.")
            return
        if self._pick_grid_datum_node(event, canvas):
            return
        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        phys_x, phys_y = self._canvas_pixel_to_phys(event.x, event.y, canvas_w, canvas_h)
        if phys_x is None or phys_y is None:
            return
        self.datum_point = (phys_x, phys_y)
        self._canvas_click_cache[(phys_x, phys_y)] = (event.x, event.y)
        self._roi_active_canvas = canvas
        canvas.delete("datum_pt")
        self._draw_datum_pt_marker(canvas, event.x, event.y)
        print(f"[datum] set at ({phys_x:.4f} mm, {phys_y:.4f} mm)")

    def _on_datum_point_stitched(self, event, canvas, _s,
                                  stitched_w, stitched_h,
                                  grid_x, grid_y,
                                  scan_origin_x, scan_origin_y):
        """<Control-ButtonRelease-3> on the stitched canvas: place or replace the datum marker."""
        # Ignore if the button was released after a pan drag (same 5 px threshold).
        # Use _pan_origin_x/y (set once on press) not _pan_start_x/y (reset each tick).
        start_x = getattr(canvas, '_pan_origin_x', event.x)
        start_y = getattr(canvas, '_pan_origin_y', event.y)
        if abs(event.x - start_x) > 5 or abs(event.y - start_y) > 5:
            return
        if self._pick_grid_datum_node(event, canvas):
            return
        full_px = (event.x - _s['ox']) / _s['sx']
        full_py = (event.y - _s['oy']) / _s['sy']
        if self._last_stitched_was_smaract:
            grid_params = self._smaract_last_grid
            if grid_params is None:
                return
            x_nm, y_nm = self.calculate_stitched_smaract_coords(
                full_px, full_py,
                stitched_w, stitched_h,
                grid_x, grid_y,
                grid_params,
            )
            phys_x, phys_y = x_nm / 1_000_000, y_nm / 1_000_000
            if self._smaract_point_out_of_bounds(phys_x, phys_y):
                return
        else:
            phys_x, phys_y = self.calculate_stitched_phys_coords(
                full_px, full_py,
                stitched_w, stitched_h,
                grid_x, grid_y,
                scan_origin_x, scan_origin_y,
            )
        self.datum_point = (phys_x, phys_y)
        self._roi_active_canvas = canvas
        canvas.delete("datum_pt")
        self._draw_datum_pt_marker(canvas, event.x, event.y)
        print(f"[datum/stitched] set at ({phys_x:.4f} mm, {phys_y:.4f} mm)")

    def _clear_custom_points(self):
        """Universal canvas clear: wipes right-click measurement points AND the
        Ctrl+Drag ROI grid, resetting all related state and UI to neutral."""
        # ── Measurement point state ───────────────────────────────────────────
        self.custom_measure_points.clear()
        self._canvas_click_cache.clear()
        self.measured_data.clear()
        self.analysis_selected_indices.clear()
        self.datum_point = None
        if hasattr(self, 'analysis_result_var'):
            self.analysis_result_var.set("Analysis:")
        self._show_heights_mode = False
        self._safe_btn('_display_heights_btn', text="Display Heights", state="disabled")
        self._safe_btn('_stitch_display_heights_btn', text="Display Heights", state="disabled")

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
            self._roi_active_canvas.delete("datum_pt")

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

    # ──────────────────────────────────────────────────────────────────────────
    # Material Removal drawer: fiducial/session capture plumbing
    # ──────────────────────────────────────────────────────────────────────────

    def _material_clear_pending_clicks(self):
        """Drop not-yet-measured canvas clicks without touching datum_point/ROI
        state (unlike _clear_custom_points, which resets the whole tab)."""
        self.custom_measure_points.clear()
        self._canvas_click_cache.clear()
        if self._roi_active_canvas is not None and self._roi_active_canvas.winfo_exists():
            self._roi_active_canvas.delete("custom_pt")

    def _fire_material_session_callback(self, raw_points):
        """Called once ANY measurement sequence finishes — a single-point
        Measure Heights run or a full grid Map Surface scan. If 'Collect
        Points' is armed, route the raw heights into the active session
        either way; the drawer doesn't care which UI action produced them."""
        if self._material_capture_armed:
            self._on_material_points_measured(raw_points)

    def _material_start_collect(self):
        """Arm capture mode: right-click points as usual, then click the tab's
        own Measure Heights button (bottom bar) to add them to the active
        session — no separate capture button. Only the button itself (not
        Escape) turns this back off."""
        self._material_capture_armed = True
        self._refresh_material_drawer()

    def _material_cancel_collect(self, event=None):
        """'Stop Collecting' button: discard pending clicks, leave already-saved
        session points untouched."""
        self._material_clear_pending_clicks()
        self._material_capture_armed = False
        self._refresh_material_drawer()

    def _on_material_points_measured(self, measured_points):
        """Fired when Measure Heights completes while 'Collect Points' is
        armed: route this run's raw heights into the active session. Leaves
        custom_measure_points/canvas markers alone — Measure Heights is a
        shared button and its normal post-measurement view must stay intact."""
        session = self.material_active_session
        valid_pts = [(x, y, z) for (x, y, z) in measured_points if not math.isnan(z)]
        if len(valid_pts) < len(measured_points):
            messagebox.showwarning("Sensor Error",
                "One or more points returned no reading (NaN) and were skipped.")
        self.material_sessions.setdefault(session, []).extend(valid_pts)

        self._material_capture_armed = False
        self._refresh_material_drawer()
        print(f"[material] {len(valid_pts)} point(s) added to session '{session}' via Measure Heights")

    def _material_add_new_set(self):
        """Append the next 'Set N' session (N = number of sets so far, 1-indexed;
        'Reference' doesn't count as a set)."""
        set_num = len(self.material_session_names)
        name = f"Set {set_num}"
        self.material_session_names.append(name)
        self.material_sessions[name] = []
        self.material_active_session = name
        self._refresh_material_drawer()

    def _material_delete_set(self):
        """Delete the active session (not 'Reference'): drops its collected
        points and any grid map, then falls back to whichever session precedes
        it. Remaining sets keep their original names/order — no renumbering."""
        session = self.material_active_session
        if session == "Reference":
            return
        if not messagebox.askyesno("Delete Set",
                "Are you sure you want to delete the current set?"):
            return
        idx = self.material_session_names.index(session)
        self.material_session_names.pop(idx)
        self.material_sessions.pop(session, None)
        self.material_planes.pop(session, None)
        self.removal_data.pop(session, None)
        self.material_active_session = self.material_session_names[max(0, idx - 1)]
        self._refresh_material_drawer()

    def _material_reset_reference(self):
        """Clear all collected Reference points and any calculated plane.
        Every Set's stored heights were measured from the current Reference
        plane as their datum, so they go stale the moment it's cleared."""
        if not messagebox.askyesno("Reset Reference",
                "Clear all reference points and reset the reference plane? "
                "Any sets already calculated were measured from the current plane "
                "and won't match the new plane."):
            return
        self.material_sessions["Reference"] = []
        self.material_planes["Reference"] = None
        self.removal_data.pop("Reference", None)
        self._refresh_material_drawer()

    def _material_reset_points(self):
        """'Reset Points': clear just the active session's not-yet-calculated
        points. Leaves any plane already calculated from a prior round alone."""
        session = self.material_active_session
        self.material_sessions[session] = []
        self._refresh_material_drawer()

    def _material_on_session_selected(self, value):
        self.material_active_session = value
        self._refresh_material_drawer()

    def _material_calculate_plane(self):
        """Fit a best-fit plane from the active session's currently collected
        points (same mechanism for Reference and every Set — more points, e.g.
        via a grid scan rather than a few single clicks, means a more accurate
        fit). Reference is the true flat datum (the sample holder's edges);
        every Set's points are measured FROM that datum plane, not leveled
        against a plane fit from the set's own points. The points stay in the
        list afterward (so Re-calculate keeps refitting from everything
        collected so far) — only "Reset Points" clears them."""
        session = self.material_active_session
        is_reference = (session == "Reference")
        label = "Reference Plane" if is_reference else "Plane"

        if not is_reference and self.material_planes.get("Reference") is None:
            messagebox.showerror("No Reference Plane",
                "Calculate the Reference plane before calculating a set's plane.")
            return

        pts = self.material_sessions.get(session, [])
        if len(pts) < 3:
            messagebox.showerror(label, f"{label} needs at least three points")
            return
        try:
            plane = calculate_best_fit_plane(pts)
        except ValueError as e:
            messagebox.showerror("Plane Error", str(e))
            return
        self.material_planes[session] = plane

        if is_reference:
            # Reference IS the datum — nothing to measure its own points against.
            self.removal_data[session] = list(pts)
        else:
            # Measure this Set's points from the reference plane as their datum.
            reference_plane = self.material_planes["Reference"]
            corrected = []
            for (x, y, z) in pts:
                if math.isnan(z):
                    corrected.append((x, y, float('nan')))
                    continue
                corrected.append((x, y, get_corrected_height(x, y, z, reference_plane)))
            self.removal_data[session] = corrected

        if is_reference:
            messagebox.showinfo("Reference Plane",
                "Reference plane formed from selected points. "
                "Each Set measures its heights from this plane as a datum.")
        else:
            messagebox.showinfo("Plane", f"Plane formed for '{session}' from the selected points.")
        self._refresh_material_drawer()

    def _material_planed_sessions(self):
        """Sessions (in collection order) that have a calculated plane."""
        return [name for name in self.material_session_names
                if self.material_planes.get(name) is not None]

    def _material_compare(self, name_a, name_b):
        """Compare two sessions' own fitted planes (not their raw stored
        points -- Reference's own points aren't on the same Z convention as a
        Set's corrected points, so this is the only comparison that works for
        ANY pair). Returns (x, y, z_a, z_b, delta) rows, or None if either
        session has no plane yet or there are no nodes to evaluate at."""
        plane_a = self.material_planes.get(name_a)
        plane_b = self.material_planes.get(name_b)
        if plane_a is None or plane_b is None:
            return None
        nodes = self.removal_data.get(name_b) or self.removal_data.get(name_a)
        if not nodes:
            return None
        rows = compare_planes(plane_a, plane_b, nodes)
        return rows or None

    def _material_set_compare_a(self, value):
        self._material_compare_a = value
        self._refresh_material_drawer()

    def _material_set_compare_b(self, value):
        self._material_compare_b = value
        self._refresh_material_drawer()

    def _material_write_comparison_csv(self, writer, name_a, name_b, rows):
        """Shared block writer: plane coefficients for both sides + per-node
        delta rows. Used by both the single-pair and bulk exports."""
        for name in (name_a, name_b):
            a, b, c, d = self.material_planes[name]
            writer.writerow([f'# {name} Plane Coefficients A,B,C,D',
                              f"{a:.6f}", f"{b:.6f}", f"{c:.6f}", f"{d:.6f}"])
        writer.writerow(['Node_X', 'Node_Y', f'{name_a}_Plane_Z', f'{name_b}_Plane_Z',
                          'Material_Removed_Delta_Z'])
        for (x, y, za, zb, delta) in rows:
            writer.writerow([f"{x:.4f}", f"{y:.4f}", f"{za:.4f}", f"{zb:.4f}", f"{delta:.4f}"])

    def _material_export_comparison_csv(self):
        """Export just the currently-picked Compare pair (any two calculated
        planes, not just adjacent sessions)."""
        name_a, name_b = self._material_compare_a, self._material_compare_b
        rows = self._material_compare(name_a, name_b) if (name_a and name_b) else None
        if not rows:
            messagebox.showwarning("Not Ready",
                "Pick two sessions with a calculated plane to export.")
            return

        default_name = f"MaterialRemoval_{name_a}_vs_{name_b}_{self.curr_sample_id}.csv".replace(" ", "_")
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=default_name,
            filetypes=[("CSV files", "*.csv")])
        if not file_path:
            return
        try:
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['# Material Removal Report'])
                writer.writerow(['# Sample', self.curr_sample_id])
                writer.writerow(['# Comparing', name_a, 'vs', name_b])
                self._material_write_comparison_csv(writer, name_a, name_b, rows)
            print(f"[material] exported {len(rows)} row(s) to {file_path}")
            messagebox.showinfo("Export Complete", f"Comparison data saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to save CSV:\n{e}")

    def _material_export_plane_csv(self):
        """Standalone export of just the active session's own plane
        coefficients and points -- no comparison involved."""
        session = self.material_active_session
        plane = self.material_planes.get(session)
        if plane is None:
            messagebox.showwarning("No Plane", "This session doesn't have a calculated plane yet.")
            return

        default_name = f"Plane_{session}_{self.curr_sample_id}.csv".replace(" ", "_")
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=default_name,
            filetypes=[("CSV files", "*.csv")])
        if not file_path:
            return
        try:
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['# Plane Export'])
                writer.writerow(['# Sample', self.curr_sample_id])
                writer.writerow(['# Session', session])
                a, b, c, d = plane
                writer.writerow(['# Plane Coefficients A,B,C,D',
                                  f"{a:.6f}", f"{b:.6f}", f"{c:.6f}", f"{d:.6f}"])
                writer.writerow([])
                z_label = 'Raw_Z' if session == 'Reference' else 'Corrected_Z'
                writer.writerow(['Node_X', 'Node_Y', z_label])
                for (x, y, z) in self.removal_data.get(session, []):
                    z_str = f"{z:.4f}" if not math.isnan(z) else "NaN"
                    writer.writerow([f"{x:.4f}", f"{y:.4f}", z_str])
            messagebox.showinfo("Export Complete", f"Plane data saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to save CSV:\n{e}")

    def _material_export_all_csv(self):
        """Bulk export: Total Material Removed (Reference vs the most recent
        Set) plus every consecutive session-to-session comparison, all in one
        CSV, one click."""
        planed = self._material_planed_sessions()
        if len(planed) < 2:
            messagebox.showwarning("Not Ready", "Need at least two calculated planes to export.")
            return

        default_name = f"MaterialRemoval_All_{self.curr_sample_id}.csv".replace(" ", "_")
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=default_name,
            filetypes=[("CSV files", "*.csv")])
        if not file_path:
            return
        try:
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['# Material Removal Report -- All Comparisons'])
                writer.writerow(['# Sample', self.curr_sample_id])
                writer.writerow([])

                set_names = [n for n in planed if n != "Reference"]
                if "Reference" in planed and set_names:
                    latest = set_names[-1]
                    total_rows = self._material_compare("Reference", latest)
                    if total_rows:
                        avg = sum(r[4] for r in total_rows) / len(total_rows)
                        writer.writerow([f'# Total Material Removed (Reference vs {latest})'])
                        writer.writerow(['# Average Delta Z (mm)', f"{avg:.4f}"])
                        writer.writerow([])

                for name_a, name_b in zip(planed, planed[1:]):
                    rows = self._material_compare(name_a, name_b)
                    if not rows:
                        continue
                    writer.writerow([f'# {name_a} vs {name_b}'])
                    self._material_write_comparison_csv(writer, name_a, name_b, rows)
                    writer.writerow([])
            messagebox.showinfo("Export Complete", f"All comparisons saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to save CSV:\n{e}")

    def _material_toggle_drawer(self):
        self._material_drawer_collapsed = not self._material_drawer_collapsed
        self._refresh_material_drawer()

    def _build_material_drawer(self, parent, before_widget=None, grid_column=None):
        """Left-side collapsible 'Material Removal' drawer, shared by the Main
        (stitched) and Image tabs. Pass before_widget for a pack()-managed parent
        (Main tab) or grid_column for a grid()-managed parent (Image tab)."""
        self._material_drawer_anchor = before_widget
        self._material_drawer_grid_column = grid_column

        width = 26 if self._material_drawer_collapsed else 220
        outer = ctk.CTkFrame(parent, width=width)
        if grid_column is not None:
            outer.grid(row=0, column=grid_column, sticky="ns", padx=(0, 5), pady=10)
            outer.grid_propagate(False)
        else:
            pack_kw = dict(side=ctk.LEFT, fill='y', padx=(0, 5))
            if before_widget is not None:
                outer.pack(before=before_widget, **pack_kw)
            else:
                outer.pack(**pack_kw)
            outer.pack_propagate(False)
        self._material_drawer_frame = outer

        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(side=ctk.TOP, fill='x', pady=(5, 0), padx=3)
        toggle_txt = "»" if self._material_drawer_collapsed else "«"
        ctk.CTkButton(header, text=toggle_txt, width=24,
                      command=self._material_toggle_drawer).pack(side=ctk.RIGHT)
        if not self._material_drawer_collapsed:
            ctk.CTkLabel(header, text="Material Removal",
                         font=("Arial", 13, "bold")).pack(side=ctk.LEFT, padx=(2, 0))

        if self._material_drawer_collapsed:
            return outer   # body hidden; only the toggle strip shows

        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.pack(side=ctk.TOP, fill='both', expand=True, padx=5, pady=5)

        # Session selector, all in one line: "Set X", "New", "Delete"/"Reset"
        sess_row = ctk.CTkFrame(body, fg_color="transparent")
        sess_row.pack(side=ctk.TOP, fill='x', pady=(0, 5))
        session_menu = ctk.CTkOptionMenu(
            sess_row, values=list(self.material_session_names),
            command=self._material_on_session_selected, width=85)
        session_menu.set(self.material_active_session)
        session_menu.pack(side=ctk.LEFT)
        ctk.CTkButton(sess_row, text="New", fg_color="#2E8B57", width=45,
                      command=self._material_add_new_set).pack(side=ctk.LEFT, padx=(4, 0))
        if self.material_active_session == "Reference":
            ctk.CTkButton(sess_row, text="Reset", fg_color="#8B2E2E", width=55,
                          command=self._material_reset_reference).pack(side=ctk.LEFT, padx=(4, 0))
        else:
            ctk.CTkButton(sess_row, text="Delete", fg_color="#8B2E2E", width=55,
                          command=self._material_delete_set).pack(side=ctk.LEFT, padx=(4, 0))

        # Collect / cancel toggle
        collect_btn = ctk.CTkButton(
            body,
            text="Stop Collecting" if self._material_capture_armed else "Collect Points",
            fg_color="#B33A3A" if self._material_capture_armed else "#1f6aa5",
            command=(self._material_cancel_collect if self._material_capture_armed
                     else self._material_start_collect))
        collect_btn.pack(side=ctk.TOP, fill='x', pady=(0, 8))

        # Collected points for the active session
        ctk.CTkLabel(body, text="Points:",
                     font=("Arial", 11, "bold")).pack(side=ctk.TOP, anchor="w")
        list_wrap = ctk.CTkFrame(body, fg_color="#2b2b2b", corner_radius=8)
        list_wrap.pack(side=ctk.TOP, fill='both', expand=True, pady=(2, 8))
        listbox = tk.Listbox(list_wrap, bg="#2b2b2b", fg="white",
                              highlightthickness=0, borderwidth=0, font=("Arial", 10))
        # Inset from list_wrap's edges so its rounded corners stay visible
        # instead of being covered by the listbox's own square corners.
        listbox.pack(fill='both', expand=True, padx=3, pady=3)
        for i, (x, y, z) in enumerate(self.material_sessions.get(self.material_active_session, [])):
            listbox.insert("end", f"{i}. ({x:.4f}, {y:.4f}, {z:.4f})")

        # Analysis: always-open sub-section (Total Material Removed / Compare /
        # Export All) -- no toggle, can't be collapsed. The card is grey,
        # matching the Points listbox background.
        analysis_card = ctk.CTkFrame(body, fg_color="#2f2f2f", corner_radius=6)
        analysis_card.pack(side=ctk.TOP, fill='x', pady=(0, 8))

        analysis_header = ctk.CTkFrame(analysis_card, fg_color="transparent")
        analysis_header.pack(side=ctk.TOP, fill='x', pady=(5, 0), padx=3)
        ctk.CTkLabel(analysis_header, text="Analysis",
                     font=("Arial", 13, "bold")).pack(side=ctk.LEFT, padx=(2, 0))

        analysis_body = ctk.CTkFrame(analysis_card, fg_color="transparent")
        analysis_body.pack(side=ctk.TOP, fill='x', padx=8, pady=(6, 8))

        planed = self._material_planed_sessions()

        if len(planed) < 2:
            ctk.CTkLabel(analysis_body, text="Measure at least two planes before analysis.",
                         font=("Arial", 11, "italic"), text_color="gray",
                         wraplength=190, justify="left").pack(side=ctk.TOP, anchor="w")

        # Compare: pick any two calculated planes, not just adjacent sessions
        if len(planed) >= 2:
            if self._material_compare_a not in planed:
                self._material_compare_a = planed[0]
            if self._material_compare_b not in planed:
                self._material_compare_b = planed[-1]

            cmp_row = ctk.CTkFrame(analysis_body, fg_color="transparent")
            cmp_row.pack(side=ctk.TOP, fill='x', pady=(0, 4))
            a_menu = ctk.CTkOptionMenu(cmp_row, values=planed, width=80,
                                       command=self._material_set_compare_a)
            a_menu.set(self._material_compare_a)
            a_menu.pack(side=ctk.LEFT)
            ctk.CTkLabel(cmp_row, text="vs").pack(side=ctk.LEFT, padx=4)
            b_menu = ctk.CTkOptionMenu(cmp_row, values=planed, width=80,
                                       command=self._material_set_compare_b)
            b_menu.set(self._material_compare_b)
            b_menu.pack(side=ctk.LEFT)

            rows = self._material_compare(self._material_compare_a, self._material_compare_b)
            if rows:
                delta_zs = [r[4] for r in rows]
                ctk.CTkLabel(analysis_body, text=f"Max Removed: {max(delta_zs):.4f} mm",
                             font=("Arial", 11, "bold"), text_color="white").pack(side=ctk.TOP, anchor="w")
                ctk.CTkLabel(analysis_body, text=f"Avg Removed: {sum(delta_zs) / len(delta_zs):.4f} mm",
                             font=("Arial", 11, "bold"), text_color="white").pack(side=ctk.TOP, anchor="w")

                # Total Removed: headline stat, Reference vs whichever Set was
                # calculated most recently. Same top padding as Avg Removed's
                # (none) had above Max Removed, so the gaps read as identical.
                set_names = [n for n in planed if n != "Reference"]
                if "Reference" in planed and set_names:
                    latest = set_names[-1]
                    total_rows = self._material_compare("Reference", latest)
                    if total_rows:
                        total_avg = sum(r[4] for r in total_rows) / len(total_rows)
                        ctk.CTkLabel(analysis_body, text=f"Total Removed: {total_avg:.4f} mm",
                                     font=("Arial", 11, "bold"), text_color="white").pack(
                                     side=ctk.TOP, anchor="w")

                ctk.CTkButton(analysis_body, text="Export Comparison", fg_color="#555555",
                              command=self._material_export_comparison_csv).pack(side=ctk.TOP, fill='x', pady=(4, 8))

            ctk.CTkButton(analysis_body, text="Export All", fg_color="#1f6aa5",
                          command=self._material_export_all_csv).pack(side=ctk.TOP, fill='x')

        # Plane calculation: same mechanism for Reference and every Set. No
        # count gate on the button itself: clicking with < 3 points is how the
        # "needs at least three points" error (and points reset) gets triggered.
        is_reference = (self.material_active_session == "Reference")
        plane_exists = self.material_planes.get(self.material_active_session) is not None
        if is_reference:
            calc_text = "Re-calculate Reference Plane" if plane_exists else "Calculate Reference Plane"
        else:
            calc_text = "Re-calculate Plane" if plane_exists else "Calculate Plane"
        ctk.CTkButton(
            body, text=calc_text, fg_color="#7B2FBE",
            command=self._material_calculate_plane).pack(side=ctk.TOP, fill='x')

        if plane_exists:
            ctk.CTkLabel(body, text="Plane Created", text_color="#00FF88").pack(side=ctk.TOP, pady=(4, 0))
            ctk.CTkButton(body, text="Export Plane CSV", fg_color="#555555",
                          command=self._material_export_plane_csv).pack(side=ctk.TOP, fill='x', pady=(2, 0))

        ctk.CTkButton(body, text="Reset Points", fg_color="#555555",
                      command=self._material_reset_points).pack(side=ctk.TOP, fill='x', pady=(4, 0))

        return outer

    def _refresh_material_drawer(self):
        """Rebuild the drawer in place, preserving whichever tab/position it's
        currently mounted at."""
        frame = self._material_drawer_frame
        if frame is None or not frame.winfo_exists():
            return
        parent = frame.master
        before = self._material_drawer_anchor
        grid_col = self._material_drawer_grid_column
        frame.destroy()
        self._build_material_drawer(parent, before_widget=before, grid_column=grid_col)

    def load_csv_points(self):
        """Bulk-load measurement points from a CSV (Site, X_mm, Y_mm, ...).
        Independent of any stitched scan: Site 0 becomes the datum point,
        every other row is appended to custom_measure_points."""
        # Placeholder stage travel limits. adjust STAGE_MAX_X/Y once the actual
        # hardware travel range is known. Only a lower bound (0 mm) is enforced
        # elsewhere in this file today; this is the first upper-bound check.
        STAGE_MIN_X, STAGE_MAX_X = 0.0, 150.0
        STAGE_MIN_Y, STAGE_MAX_Y = 0.0, 150.0

        file_path = filedialog.askopenfilename(
            title="Select Points CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                header = next(reader, None)

                # Validate only the first three columns. extra trailing columns
                # (e.g. Z_mm, Height_mm) are accepted and simply ignored below.
                if not header or len(header) < 3:
                    messagebox.showerror("Format Error", "CSV must have at least 3 columns: Site, X_mm, Y_mm")
                    return

                h_site, h_x, h_y = header[0].lower(), header[1].lower(), header[2].lower()
                if 'site' not in h_site or 'x' not in h_x or 'y' not in h_y:
                    messagebox.showerror("Format Error", f"The first three columns must be Site, X, Y.\nFound: {header[0]}, {header[1]}, {header[2]}")
                    return

                self._clear_custom_points()

                for row in reader:
                    if len(row) < 3:
                        continue   # skip empty or malformed rows

                    try:
                        site = row[0].strip()
                        x_val = float(row[1])
                        y_val = float(row[2])
                    except (ValueError, IndexError):
                        messagebox.showerror("Parse Error", f"Invalid number format in CSV row: {row}")
                        self._clear_custom_points()
                        return

                    # Pre-flight bounds check.
                    # SmarAct: the CSV coordinate is already a SmarAct-frame point (no
                    # confocal offset applied, same as everywhere else in this file),
                    # checked against the SLC-1720's own symmetric travel range —
                    # negative values are fine there, unlike the module stage.
                    if self.use_smaract_stage:
                        if not (SMARACT_TRAVEL_MIN <= x_val <= SMARACT_TRAVEL_MAX
                                and SMARACT_TRAVEL_MIN <= y_val <= SMARACT_TRAVEL_MAX):
                            messagebox.showerror(
                                "Hardware Safety Fault",
                                f"CSV Import Aborted.\n\nSite {site} ({x_val}, {y_val}) is outside "
                                f"the SmarAct stage's {SMARACT_TRAVEL_MIN:.1f} to "
                                f"{SMARACT_TRAVEL_MAX:.1f} mm travel range.\n\n"
                                f"Please correct the CSV and try again."
                            )
                            self._clear_custom_points()   # wipe any partially loaded points
                            return
                    else:
                        # validate the actual motor destination (point + confocal-sensor
                        # offset), not the raw CSV coordinate, matching the offset applied
                        # everywhere else in this file.
                        motor_dest_x = x_val + _CONFOCAL_DX
                        motor_dest_y = y_val + _CONFOCAL_DY
                        if not (STAGE_MIN_X <= motor_dest_x <= STAGE_MAX_X) or not (STAGE_MIN_Y <= motor_dest_y <= STAGE_MAX_Y):
                            messagebox.showerror(
                                "Hardware Safety Fault",
                                f"CSV Import Aborted.\n\nSite {site} ({x_val}, {y_val}) will push the motors "
                                f"out of bounds after applying the Confocal offset.\n"
                                f"Target Motor X: {motor_dest_x:.2f}\nTarget Motor Y: {motor_dest_y:.2f}\n\n"
                                f"Please correct the CSV and try again."
                            )
                            self._clear_custom_points()   # wipe any partially loaded points
                            return

                    if site == "0":
                        self.datum_point = (x_val, y_val)
                    else:
                        self.custom_measure_points.append((x_val, y_val))
        except Exception as e:
            messagebox.showerror("CSV Load Error", f"Failed to load points:\n{e}")
            return

        for btn_name in ('_measure_heights_btn', '_clear_points_btn',
                         '_stitch_measure_heights_btn', '_stitch_clear_points_btn'):
            self._safe_btn(btn_name, state="normal")

        # ── Make the loaded points visible immediately and give "Clear Points" a
        # canvas to act on. without this, self._roi_active_canvas stays whatever
        # it was before the import (often None), so Clear Points can't wipe the
        # on-screen markers until the user clicks the canvas at least once.
        if (getattr(self, 'active_main_view', 'default') == 'stitched'
                and getattr(self, '_stitched_canvas', None) is not None
                and self._stitched_canvas.winfo_exists()):
            self._roi_active_canvas = self._stitched_canvas
            if getattr(self, '_schedule_render', None) is not None:
                self._schedule_render()
        elif (getattr(self, '_image_tab_canvas', None) is not None
                and self._image_tab_canvas.winfo_exists()):
            self._roi_active_canvas = self._image_tab_canvas
            # _redraw_custom_points_image_tab assumes a pre-wiped canvas; clear any
            # stale markers first in case this canvas wasn't self._roi_active_canvas
            # the last time points were cleared (i.e. exactly bug #1's scenario).
            self._image_tab_canvas.delete("custom_pt", "measurement_text", "datum_pt")
            self._redraw_custom_points_image_tab(
                self._image_tab_canvas,
                self._image_tab_canvas.winfo_width(),
                self._image_tab_canvas.winfo_height())

        print(f"[csv_import] loaded {len(self.custom_measure_points)} point(s) "
              f"{'with datum' if self.datum_point is not None else 'without datum'} from {file_path}")

    def launch_gwyddion(self):
        """Strip the 'Site' column from the last-exported CSV, save a clean
        X, Y, Z .xyz file, and open it in Gwyddion via subprocess."""
        if not hasattr(self, 'last_exported_csv') or not os.path.exists(self.last_exported_csv):
            messagebox.showerror("Error", "No recent CSV found to export.")
            return

        base, _ = os.path.splitext(self.last_exported_csv)
        xyz_path = base + "_gwyddion.xyz"

        try:
            with open(self.last_exported_csv, 'r') as infile, open(xyz_path, 'w', newline='') as outfile:
                reader = csv.reader(infile)
                writer = csv.writer(outfile)

                header = next(reader, None)
                # Points export header: Site, X_mm, Y_mm, Z_mm, Height_mm (5 cols):
                # the measured height is Height_mm (index 4).
                # Grid export header: Site, X_mm, Y_mm, Z_mm (4 cols): the measured
                # height is Z_mm itself (index 3). Both keep X/Y at indices 1/2.
                is_points_format = header and len(header) >= 5

                for row in reader:
                    if not row:
                        continue
                    if is_points_format:
                        if len(row) >= 5 and row[4].strip().lower() != "nan":
                            writer.writerow([row[1], row[2], row[4]])
                    else:
                        if len(row) >= 4 and row[3].strip().lower() != "nan":
                            writer.writerow([row[1], row[2], row[3]])

            import subprocess
            subprocess.Popen(["gwyddion", xyz_path])
        except FileNotFoundError:
            messagebox.showerror("Launch Error", "Could not find 'gwyddion' executable.\nPlease ensure Gwyddion is installed and added to your system PATH.")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to prepare file for Gwyddion:\n{e}")

    def _measurement_label_fill(self, i, height, is_datum):
        """Shared label/fill logic for the three places that stamp measurement text
        (Image tab, stitched view, and right after a sequence completes). Only the
        label text depends on _show_heights_mode. the datum/out-of-range/selected
        colouring is unchanged from before."""
        if math.isnan(height):
            return "Out of Range", "red"
        if is_datum:
            return "0", "magenta"
        label = f"{height:.3f}" if self._show_heights_mode else str(i + 1)
        fill = "#00FF44" if i in self.analysis_selected_indices else "cyan"
        return label, fill

    def _toggle_display_heights_mode(self):
        """Flip between showing point indices and measured heights on the canvas
        labels, then redraw whichever canvas is currently active."""
        if not self.measured_data:
            return
        self._show_heights_mode = not self._show_heights_mode
        new_text = "Display Indices" if self._show_heights_mode else "Display Heights"
        self._safe_btn('_display_heights_btn', text=new_text)
        self._safe_btn('_stitch_display_heights_btn', text=new_text)

        if (getattr(self, 'active_main_view', 'default') == 'stitched'
                and getattr(self, '_stitched_canvas', None) is not None
                and self._stitched_canvas.winfo_exists()):
            if getattr(self, '_schedule_render', None) is not None:
                self._schedule_render()
        elif (getattr(self, '_image_tab_canvas', None) is not None
                and self._image_tab_canvas.winfo_exists()):
            self._image_tab_canvas.delete("custom_pt", "measurement_text", "datum_pt")
            self._redraw_custom_points_image_tab(
                self._image_tab_canvas,
                self._image_tab_canvas.winfo_width(),
                self._image_tab_canvas.winfo_height())

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
            text = "Analysis:"
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

        # ── Datum check ───────────────────────────────────────────────────────
        if self.datum_point is None:
            proceed = messagebox.askyesno(
                "No Datum Selected",
                "No datum point selected (Ctrl + Right-Click). Heights will be measured "
                "with the default sensor datum.\n\nDo you want to proceed?"
            )
            if not proceed:
                return

        # ── Save camera assembly origin before any movement ───────────────────
        # Must be captured here, before the confocal offset shifts the targets.
        self._sequence_origin_x = float(self.x_pos)
        self._sequence_origin_y = float(self.y_pos)
        self._sequence_origin_z = float(self.z_pos)

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

        # ── Append datum point so the sensor physically visits it ────────────
        # The datum is appended after the nearest-neighbour sort so it is always
        # the last point visited, minimising unnecessary travel.
        if self.datum_point is not None:
            optimized_route.append(self.datum_point)

        # ── Apply confocal-camera offset to every target point ────────────────
        # The confocal sensor is offset from the camera by this fixed amount.
        # SmarAct samples: skip this (the confocal offset is baked into the
        # one-time confocal-over-SmarAct parking step instead of per point,
        # since route points here are already SmarAct-frame coordinates).
        if self.use_smaract_stage:
            offset_route = optimized_route
        else:
            CONFOCAL_DX = -1.418137875
            CONFOCAL_DY = -72.258765875
            offset_route = [(x + CONFOCAL_DX, y + CONFOCAL_DY) for x, y in optimized_route]

        print(f"[execute_custom_measurements] {len(offset_route)} point(s) — nearest-neighbour order (confocal offset applied):")
        for i, (x, y) in enumerate(offset_route, 1):
            print(f"  {i:>3}. ({x:.4f} mm, {y:.4f} mm)")

        # ── Pre-flight: confirm all confocal targets are within stage bounds ──
        # Loop through every offset point; abort on the first violation so the
        # error message references a single concrete bad coordinate.
        # SmarAct: points are SmarAct-frame coordinates on the SLC-1720 piezo stage,
        # whose legitimate travel range is symmetric (SMARACT_TRAVEL_MIN/MAX, i.e.
        # negative values are fine) — not the module stage's "must be >= 0" rule.
        if self.use_smaract_stage:
            for target_x, target_y in offset_route:
                if not (SMARACT_TRAVEL_MIN <= target_x <= SMARACT_TRAVEL_MAX
                        and SMARACT_TRAVEL_MIN <= target_y <= SMARACT_TRAVEL_MAX):
                    messagebox.showerror(
                        "Cannot Reach Sample",
                        f"Cannot Reach Sample: point ({target_x:.4f} mm, {target_y:.4f} mm) "
                        f"is outside the SmarAct stage's {SMARACT_TRAVEL_MIN:.1f} to "
                        f"{SMARACT_TRAVEL_MAX:.1f} mm travel range."
                    )
                    return
        else:
            for target_x, target_y in offset_route:
                if target_x < 0 or target_y < 0:
                    messagebox.showerror(
                        "Cannot Reach Sample",
                        f"Cannot Reach Sample: Point requires stage to move to "
                        f"({target_x:.2f} mm, {target_y:.2f} mm), which is past the module's limit (0 mm).\n\n"
                        f"Please manually unmount and shift your sample at least "
                        f"{max(abs(target_x), abs(target_y)) + 1.0:.2f} mm further away from the limit."
                    )
                    return

        # ── Open persistent Confocal socket; send R0 exactly once ────────────
        # Keeping the socket open for the whole sequence mirrors confocal_looped.py:
        # the CL-Navigator's AGC and averaging buffer stay warm, eliminating the
        # per-point state-machine reset that caused measurement instability.
        try:
            _cs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _cs.settimeout(_CONFOCAL_TIMEOUT)
            _cs.connect((_CONFOCAL_IP, _CONFOCAL_PORT))
            _cs.sendall("R0\r".encode('ascii'))
            _cs.recv(1024)   # drain mode-switch acknowledgement
            self._confocal_socket = _cs
            print("[confocal] persistent socket open; measurement mode active")
        except Exception as _e:
            messagebox.showerror(
                "Confocal Unreachable",
                f"Cannot connect to the Confocal sensor:\n{_e}\n\n"
                f"Check that CL-Navigator is running and the network cable is connected."
            )
            return

        # Disable action buttons on both tabs for the duration of the sequence
        for _btn in ('_measure_heights_btn', '_clear_points_btn', '_map_surface_btn',
                     '_stitch_measure_heights_btn', '_stitch_clear_points_btn',
                     '_stitch_map_surface_btn'):
            self._safe_btn(_btn, state="disabled")
        # Click-to-move must stay off for the whole sequence, not just while the
        # RPi reports non-Idle (it can go Idle mid-sequence between move/read steps)
        self._sequence_active = True

        # Preserve optimised order so _process_measurement_results can pair
        # each height with the correct physical coordinate.
        self._optimized_route = optimized_route

        if self.datum_point is None:
            self._sequence_measure_point(offset_route, 0, [])   # no datum: unchanged behavior
        else:
            self._begin_autofocus_datum(offset_route)

    def _update_scan_progress_dot(self, index):
        """Move (or create) the live orange dot marking the grid node currently being
        measured. Only active during a grid (Map Surface) scan, not individual custom
        points.

        Deliberately does NOT run its own phys->pixel transform (that's what the
        earlier version did, and it could land a few px off the actual node due to
        independent rounding vs _roi_redraw_grid's own pixel math). Instead this
        reuses _roi_redraw_grid's exact interpolation formula and the exact same
        self._roi_canvas_x0/y0/x1/y1 + map_grid_x/y it draws the nodes from, so the
        dot is mathematically guaranteed to land exactly on the node's center.

        index is the point's position in the grid scan's route (see
        start_surface_map's snake_route). No-ops quietly if the canvas active when
        the grid was drawn isn't on screen right now (e.g. user tabbed away)."""
        if getattr(self, '_sequence_mode', 'custom') != "grid":
            return

        is_stitched = (self.active_main_view == "stitched")
        canvas = getattr(self, '_stitched_canvas' if is_stitched else '_image_tab_canvas', None)
        if canvas is None or not canvas.winfo_exists():
            return
        if not (self._roi_active_canvas is canvas and self.roi_phys_x_start is not None):
            return

        nx = max(2, self.map_grid_x)
        ny = max(2, self.map_grid_y)
        row, pos_in_row = divmod(index, nx)
        # odd rows were swept in reverse (snake/boustrophedon route order)
        col = pos_in_row if row % 2 == 0 else (nx - 1 - pos_in_row)

        x0, y0 = self._roi_canvas_x0, self._roi_canvas_y0
        x1, y1 = self._roi_canvas_x1, self._roi_canvas_y1
        cx = x0 + col * (x1 - x0) / (nx - 1)
        cy = y0 + row * (y1 - y0) / (ny - 1)

        R = 5  # a bit bigger than the grid's own node dots (DOT_R=3)
        if self._scan_progress_dot_id is not None and canvas is self._scan_progress_dot_canvas:
            try:
                canvas.coords(self._scan_progress_dot_id, cx - R, cy - R, cx + R, cy + R)
                canvas.tag_raise(self._scan_progress_dot_id)
                canvas.update_idletasks()
                return
            except tk.TclError:
                # dot got wiped by an unrelated canvas.delete("all") redraw; fall through and recreate
                self._scan_progress_dot_id = None

        self._scan_progress_dot_id = canvas.create_oval(
            cx - R, cy - R, cx + R, cy + R,
            fill="#FF8C00", outline="#FFD580", width=1, tags="active_node_indicator")
        self._scan_progress_dot_canvas = canvas
        # force an immediate repaint so the dot visibly moves before the settling
        # delay/measurement step, without blocking the mainloop or hardware timing
        canvas.update_idletasks()

    def _clear_scan_progress_dot(self):
        # hide the active-node indicator once the scan finishes or aborts
        canvas = self._scan_progress_dot_canvas
        if canvas is not None and canvas.winfo_exists():
            canvas.delete("active_node_indicator")
        self._scan_progress_dot_id = None
        self._scan_progress_dot_canvas = None

    def _sequence_measure_point(self, route, index, results):
        """Non-blocking dispatcher: move to route[index] when the stage is Idle,
        then hand off to the arrival-wait sub-sequence."""
        if index >= len(route):
            self._process_measurement_results(results)
            return

        if self.module_status != "Idle":
            self.after(100, lambda: self._sequence_measure_point(route, index, results))
            return

        target_x, target_y = route[index]

        if self.use_smaract_stage:
            # route points are absolute SmarAct-frame mm coordinates (computed by
            # _canvas_pixel_to_phys against the SmarAct's own live position at
            # click/ROI-drag time). Z is never sent here, it stays fixed on the
            # optical stage from the one-time datum/autofocus step.
            x_nm = round(target_x * 1_000_000)
            y_nm = round(target_y * 1_000_000)
            print(f"[sequence] moving SmarAct to point {index + 1}/{len(route)}: ({x_nm} nm, {y_nm} nm)")

            def _on_complete():
                # X/Y move is done, about to settle then measure Z: move the active
                # scan indicator to this node
                self._update_scan_progress_dot(index)
                self.after(_SETTLING_DELAY_MS, lambda: self._sequence_fire_sensor_read(route, index, results))

            def _on_error():
                self._close_confocal_socket()
                self._sequence_unlock_buttons()

            self._smaract_move_to(x_nm, y_nm, on_complete=_on_complete, on_error=_on_error)
            return

        if target_x < 0 or target_y < 0 or float(self.z_pos) < 0:
            print(f"[sequence] ERROR: point {index + 1} ({target_x:.4f}, {target_y:.4f}) "
                  f"out of range — aborting sequence")
            messagebox.showerror(
                "Sequence Aborted",
                f"Point {index + 1}/{len(route)} ({target_x:.4f}, {target_y:.4f} mm) "
                f"is out of stage range.\nSequence aborted."
            )
            self._close_confocal_socket()
            self._sequence_unlock_buttons()
            return

        print(f"[sequence] moving to point {index + 1}/{len(route)}: ({target_x:.4f}, {target_y:.4f}) mm")
        self.send_goto_command(target_x, target_y, float(self.z_pos), show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0

        self.after(100, lambda: self._sequence_wait_then_measure(route, index, results))

    def _sequence_wait_then_measure(self, route, index, results):
        """Poll until the stage reaches Idle, wait for mechanical settling, then
        fire a daemon thread to read the confocal sensor without blocking the GUI."""
        if self.module_status != "Idle":
            self.after(100, lambda: self._sequence_wait_then_measure(route, index, results))
            return

        # X/Y move is done, about to settle then measure Z: move the active scan
        # indicator to this node
        self._update_scan_progress_dot(index)

        # Insert a mandatory settling delay before measuring.  The motor controller
        # reports "Idle" when the servo encoder is within dead-band, but the physical
        # camera assembly continues to ring for hundreds of milliseconds afterward.
        # Measuring without this delay was the confirmed primary cause of the 269 µm
        # run-to-run tramming discrepancy.
        print(f"[sequence] stage idle — waiting {_SETTLING_DELAY_MS} ms for mechanical settling "
              f"(point {index + 1}/{len(route)})")
        self.after(_SETTLING_DELAY_MS, lambda: self._sequence_fire_sensor_read(route, index, results))

    def _sequence_fire_sensor_read(self, route, index, results):
        """Called after the mechanical settling delay has elapsed; starts the
        confocal read thread and schedules the result-polling loop."""
        print(f"[sequence] settling complete — reading confocal sensor at point {index + 1}/{len(route)}")
        result_holder = [None]   # thread writes float/NaN here; None means not done yet
        t = Thread(target=self._confocal_read_worker, args=(result_holder,), daemon=True)
        t.start()
        self.after(100, lambda: self._sequence_poll_sensor_result(route, index, results, result_holder, t))

    def _confocal_read_worker(self, result_holder):
        """Read one height from the persistent socket opened by execute_custom_measurements.
        Runs in a daemon thread.  R0 is NOT re-sent here: the socket is already in
        measurement mode and the CL-Navigator's internal AGC/averaging state is stable.

        Two-phase MS read: flush one buffered sample (may have been captured at the
        exact moment the assembly stopped), then take the authoritative reading."""
        try:
            s = self._confocal_socket
            # Flush: discard the sample most recently buffered by the controller
            s.sendall("MS,1,1\r".encode('ascii'))
            s.recv(1024)
            # Real measurement: freshly acquired after the flush round-trip
            s.sendall("MS,1,1\r".encode('ascii'))
            response = s.recv(1024).decode('ascii')
            parts = response.split(',')
            if len(parts) >= 2:
                result_holder[0] = float(parts[1].strip())
            else:
                print(f"[confocal] unexpected response: {response!r}")
                result_holder[0] = float('nan')
        except Exception as e:
            print(f"[confocal] WARNING: sensor read failed — {e}")
            result_holder[0] = float('nan')

    def _close_confocal_socket(self):
        """Safely close and discard the persistent Confocal TCP socket.
        Safe to call even if the socket was never opened or already closed."""
        s = getattr(self, '_confocal_socket', None)
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
            self._confocal_socket = None

    def _sequence_poll_sensor_result(self, route, index, results, result_holder, thread):
        """Poll every 100 ms until the confocal read thread finishes, then
        pass the height to _sequence_record_height to advance the sequence."""
        if thread.is_alive():
            self.after(100, lambda: self._sequence_poll_sensor_result(
                route, index, results, result_holder, thread))
            return
        height = result_holder[0]
        if height is None or math.isnan(height):
            print(f"[sequence] WARNING: sensor returned no data at point {index + 1} — recording NaN")
            height = float('nan')
        self._sequence_record_height(route, index, results, height)

    def _sequence_record_height(self, route, index, results, height):
        """Record the live confocal height and advance to the next point."""
        results.append(height)
        height_str = f"{height:.4f} mm" if not math.isnan(height) else "NaN (sensor error)"
        print(f"[sequence] point {index + 1}/{len(route)}: height = {height_str}")
        self._sequence_measure_point(route, index + 1, results)

    # ── Auto-focus-datum calibration ────────────────────────────────────────
    # Automatic pre-step, run once before the real measurement route starts:
    # drive to the datum (confocal-offset applied), read the sensor once, then
    # jog Z so the confocal reads ~0 mm there. Mirrors the _sequence_* .after()
    # idiom above (never blocks the main thread; only the socket read runs in
    # a background Thread, via the existing _confocal_read_worker).

    def _begin_autofocus_datum(self, route):
        """Entry point: called once the persistent confocal socket is already open
        and action buttons are already disabled (a drop-in replacement for the
        final self._sequence_measure_point(route, 0, []) call in each launcher."""
        if self.use_smaract_stage:
            # SmarAct samples: the confocal is fixed at the puck's park position —
            # it's the SAMPLE that has to move (via the SmarAct stage) so the
            # user-picked datum point ends up underneath it, before the module
            # carriage parks there and the Z-sweep calibrates against it. Without
            # this move the sweep runs wherever the SmarAct last happened to be
            # sitting, which is very likely not over any sample surface at all.
            datum_x_nm = round(self.datum_point[0] * 1_000_000)
            datum_y_nm = round(self.datum_point[1] * 1_000_000)

            def _on_smaract_datum_error():
                self._close_confocal_socket()
                self._sequence_unlock_buttons()

            def _on_smaract_at_datum():
                print(f"[autofocus] SmarAct at datum ({self.datum_point[0]:.4f}, "
                      f"{self.datum_point[1]:.4f}) mm — parking confocal carriage")
                self._autofocus_raise_z(route, SMARACT_CONFOCAL_PARK_X, SMARACT_CONFOCAL_PARK_Y)

            print(f"[autofocus] moving SmarAct to datum ({self.datum_point[0]:.4f}, "
                  f"{self.datum_point[1]:.4f}) mm before confocal calibration")
            self._smaract_move_to(datum_x_nm, datum_y_nm,
                                   on_complete=_on_smaract_at_datum, on_error=_on_smaract_datum_error)
            return

        datum_x = self.datum_point[0] + _CONFOCAL_DX
        datum_y = self.datum_point[1] + _CONFOCAL_DY
        if datum_x < 0 or datum_y < 0:
            messagebox.showerror(
                "Cannot Reach Datum",
                f"Auto-focus aborted: the datum plus confocal offset requires the stage "
                f"to move to ({datum_x:.4f}, {datum_y:.4f}) mm, which exceeds the "
                f"hardware limit (0 mm)."
            )
            self._close_confocal_socket()
            self._sequence_unlock_buttons()
            return
        print(f"[autofocus] datum target ({datum_x:.4f}, {datum_y:.4f}) mm — "
              f"starting auto-focus calibration")
        self._autofocus_raise_z(route, datum_x, datum_y)

    def _autofocus_raise_z(self, route, datum_x, datum_y):
        """Hardware safety: raise Z to a clearance height at the CURRENT XY position
        before moving XY to the datum, so the assembly never crosses to a new XY
        position while sitting at an arbitrary (possibly collision-risk) Z.

        SmarAct samples sit on a mount higher than the module stage, so their
        clearance height is height-compensated around SMARACT_CONFOCAL_FOCUS_Z
        (the confocal's own zero-height focus Z, not the camera's SMARACT_PARK_Z),
        not the module stage's 90mm clearance — going to 90mm would overshoot
        the mount.
        """
        if self.module_status != "Idle":
            self.after(100, lambda: self._autofocus_raise_z(route, datum_x, datum_y))
            return
        if self.use_smaract_stage:
            sample_height_mm = float(self.sample_data.get('initial_height', 0.0))
            clearance_z = SMARACT_CONFOCAL_FOCUS_Z - sample_height_mm
        else:
            clearance_z = _SAFE_CLEARANCE_Z_MM
        print(f"[autofocus] raising Z to {clearance_z:.1f} mm clearance before XY move")
        self.send_goto_command(float(self.x_pos), float(self.y_pos), clearance_z, show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0
        self.after(100, lambda: self._autofocus_wait_z_clear(route, datum_x, datum_y))

    def _autofocus_wait_z_clear(self, route, datum_x, datum_y):
        if self.module_status != "Idle":
            self.after(100, lambda: self._autofocus_wait_z_clear(route, datum_x, datum_y))
            return
        self._autofocus_goto_datum(route, datum_x, datum_y)

    def _autofocus_goto_datum(self, route, datum_x, datum_y):
        if self.module_status != "Idle":
            self.after(100, lambda: self._autofocus_goto_datum(route, datum_x, datum_y))
            return
        self.send_goto_command(datum_x, datum_y, float(self.z_pos), show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0
        self.after(100, lambda: self._autofocus_wait_arrival(route, datum_x, datum_y))

    def _autofocus_wait_arrival(self, route, datum_x, datum_y):
        if self.module_status != "Idle":
            self.after(100, lambda: self._autofocus_wait_arrival(route, datum_x, datum_y))
            return
        print(f"[autofocus] at datum — waiting {_SETTLING_DELAY_MS} ms for mechanical settling")
        base_z = float(self.z_pos)
        offsets = self._autofocus_sweep_offsets(_AUTOFOCUS_SWEEP_RANGE_MM, _AUTOFOCUS_SWEEP_STEP_MM)
        self.after(_SETTLING_DELAY_MS,
                   lambda: self._autofocus_sweep_step(route, datum_x, datum_y, base_z, offsets, 0))

    def _autofocus_sweep_offsets(self, range_mm, step_mm):
        """Center-out Z offsets (0, +step, -step, +2*step, -2*step, ...) so a good initial
        estimate resolves fast, while a worse one still gets covered within +/-range_mm."""
        offsets = [0.0]
        steps = int(round(range_mm / step_mm))
        for i in range(1, steps + 1):
            offsets.append(i * step_mm)
            offsets.append(-i * step_mm)
        return offsets

    def _autofocus_sweep_step(self, route, datum_x, datum_y, base_z, offsets, idx):
        """Move Z to the next sweep offset and read the confocal there; advances to the
        next offset on an out-of-range reading, or fails after the whole sweep is exhausted."""
        if idx >= len(offsets):
            print(f"[autofocus] ERROR: confocal sensor found no valid reading anywhere in a "
                  f"+/-{_AUTOFOCUS_SWEEP_RANGE_MM:.1f} mm sweep around {base_z:.4f} mm — aborting")
            messagebox.showerror(
                "Auto-Focus Failed",
                f"Auto-focus datum calibration failed: the confocal sensor returned an "
                f"invalid reading at every Z in a +/-{_AUTOFOCUS_SWEEP_RANGE_MM:.1f} mm sweep "
                f"around {base_z:.4f} mm.\nCheck the CL-Navigator connection and datum position, "
                f"then try again."
            )
            self._close_confocal_socket()
            self._sequence_unlock_buttons()
            return

        target_z = base_z + offsets[idx]
        if target_z < 0:
            self._autofocus_sweep_step(route, datum_x, datum_y, base_z, offsets, idx + 1)
            return

        self.send_goto_command(datum_x, datum_y, target_z, show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0
        self.after(100, lambda: self._autofocus_sweep_wait_move(
            route, datum_x, datum_y, base_z, offsets, idx, target_z))

    def _autofocus_sweep_wait_move(self, route, datum_x, datum_y, base_z, offsets, idx, target_z):
        if self.module_status != "Idle":
            self.after(100, lambda: self._autofocus_sweep_wait_move(
                route, datum_x, datum_y, base_z, offsets, idx, target_z))
            return
        self.after(_SETTLING_DELAY_MS, lambda: self._autofocus_sweep_fire_read(
            route, datum_x, datum_y, base_z, offsets, idx, target_z))

    def _autofocus_sweep_fire_read(self, route, datum_x, datum_y, base_z, offsets, idx, target_z):
        result_holder = [None]
        t = Thread(target=self._confocal_read_worker, args=(result_holder,), daemon=True)
        t.start()
        self.after(100, lambda: self._autofocus_sweep_poll_read(
            route, datum_x, datum_y, base_z, offsets, idx, target_z, result_holder, t))

    def _autofocus_sweep_poll_read(self, route, datum_x, datum_y, base_z, offsets, idx, target_z,
                                    result_holder, thread):
        if thread.is_alive():
            self.after(100, lambda: self._autofocus_sweep_poll_read(
                route, datum_x, datum_y, base_z, offsets, idx, target_z, result_holder, thread))
            return
        reading = result_holder[0]
        if reading is None or math.isnan(reading) or reading < -90.0:
            print(f"[autofocus] sweep {idx + 1}/{len(offsets)}: Z={target_z:.4f} mm — "
                  f"out of range, trying next offset")
            self._autofocus_sweep_step(route, datum_x, datum_y, base_z, offsets, idx + 1)
            return

        new_z = target_z - reading
        if new_z < 0:
            print(f"[autofocus] ERROR: computed Z jog ({new_z:.4f} mm) out of range — aborting")
            messagebox.showerror(
                "Auto-Focus Failed",
                f"Auto-focus datum calibration failed: the computed Z position "
                f"({new_z:.4f} mm) is out of stage range.\nSequence aborted."
            )
            self._close_confocal_socket()
            self._sequence_unlock_buttons()
            return

        print(f"[autofocus] sweep {idx + 1}/{len(offsets)}: Z={target_z:.4f} mm, reading={reading:.4f} mm "
              f"-> new_z={new_z:.4f} mm")
        self.send_goto_command(datum_x, datum_y, new_z, show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0
        self.after(100, lambda: self._autofocus_wait_z_settle(route))

    def _autofocus_wait_z_settle(self, route):
        if self.module_status != "Idle":
            self.after(100, lambda: self._autofocus_wait_z_settle(route))
            return
        self.after(_SETTLING_DELAY_MS, lambda: self._autofocus_complete(route))

    def _autofocus_complete(self, route):
        print("[autofocus] datum Z calibration complete — starting main measurement sequence")
        self._sequence_measure_point(route, 0, [])

    def _phys_to_canvas_pixel(self, phys_x, phys_y, ref_x, ref_y, canvas_w, canvas_h):
        """Inverse of _canvas_pixel_to_phys: map physical mm coords back to canvas pixels.
        ref_x/ref_y must be the camera assembly position (or, for a SmarAct sample, the
        SmarAct's own live position) at the moment the image was displayed."""
        if self._canvas_disp_w == 0 or self._canvas_orig_w == 0:
            return None, None
        A11, A12 = -0.001479,  0.000044
        A21, A22 =  0.000018,  0.001459
        det = A11 * A22 - A12 * A21
        dp_x = phys_x - ref_x
        # SmarAct Y is mounted opposite the camera's Y axis (see _canvas_pixel_to_phys).
        dp_y = (ref_y - phys_y) if self.use_smaract_stage else (phys_y - ref_y)
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

        # Raw (absolute) heights, kept separate from the datum-relative
        # measured_data below: the datum node moves between runs (a fresh grid
        # pick, or none at all for custom points), so material-plane fitting/
        # correction needs the same absolute Z frame across every session, not
        # whatever local datum happened to be active for a given run.
        raw_points_all = []
        for (px, py), h in zip(ordered_points, results):
            if h < -90.0 or math.isnan(h) or abs(h) < 0.000001:
                raw_points_all.append((px, py, float('nan')))
            else:
                raw_points_all.append((px, py, h))

        # ── Persist measurement data for analysis mode ────────────────────────
        # Subtract datum Z so every height is relative to the datum. applies to
        # both custom-points scans and grid scans (grid scans always have a valid
        # self.datum_point: the picked/default grid node, see start_surface_map).
        datum_z = 0.0
        if self.datum_point is not None:
            for (px, py), h in zip(ordered_points, results):
                if (px, py) == self.datum_point:
                    datum_z = h
                    break
        # Treat sensor error codes (e.g. -99.9999) as NaN so they don't silently
        # cancel out in subtraction and produce a false 0.000 mm reading.
        if datum_z < -90.0 or math.isnan(datum_z) or abs(datum_z) < 0.000001:
            datum_z = float('nan')
        self.measured_data = []
        for (px, py), h in zip(ordered_points, results):
            if h < -90.0 or math.isnan(h) or abs(h) < 0.000001 or math.isnan(datum_z):
                self.measured_data.append((px, py, float('nan')))
            else:
                self.measured_data.append((px, py, h - datum_z))
        self.analysis_selected_indices = []
        if hasattr(self, 'analysis_result_var'):
            self.analysis_result_var.set("Analysis:")

        # ── Draw height values directly above each marker on the canvas ───────
        canvas = self._roi_active_canvas
        if canvas is not None:
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()

            # Determine whether the active canvas is the stitched view or the
            # standard Image tab, and pick the matching inverse-transform path.
            is_stitched = (self.active_main_view == "stitched")

            # Skip per-point canvas labels for grid scans. thousands of labels
            # would be unreadable and slow; data is captured in the CSV instead.
            if getattr(self, '_sequence_mode', 'custom') != "grid":
                for i, (phys_x, phys_y, height) in enumerate(self.measured_data):
                    if is_stitched:
                        # Use stitched-image coordinate helper (zoom/pan-aware via _s
                        # was already applied at click time; use stored scan geometry).
                        grid_x  = getattr(self, 'scanning_grid_x', 1)
                        grid_y  = getattr(self, 'scanning_grid_y', 1)
                        stitched_w = getattr(self, '_stitch_img_w', cw)
                        stitched_h = getattr(self, '_stitch_img_h', ch)
                        if self._last_stitched_was_smaract:
                            grid_params = self._smaract_last_grid
                            if grid_params is None:
                                cx, cy = None, None
                            else:
                                cx, cy = self.calculate_smaract_phys_to_stitched_pixel_coords(
                                    phys_x, phys_y,
                                    stitched_w, stitched_h,
                                    grid_x, grid_y,
                                    grid_params,
                                    cw, ch,
                                )
                        else:
                            step_x  = self.scanning_data.get('step_x', 1.0)
                            step_y  = self.scanning_data.get('step_y', 1.0)
                            scan_end_x   = getattr(self, 'scan_end_x', 0.0)
                            scan_end_y   = getattr(self, 'scan_end_y', 0.0)
                            scan_origin_x = scan_end_x - (grid_x - 1) * step_x
                            scan_origin_y = scan_end_y - (grid_y - 1) * step_y
                            cx, cy = self.calculate_phys_to_stitched_pixel_coords(
                                phys_x, phys_y,
                                stitched_w, stitched_h,
                                grid_x, grid_y,
                                scan_origin_x, scan_origin_y,
                                cw, ch,
                            )
                    else:
                        # Use the pixel coords recorded at click time (avoids
                        # geometry recalculation drift that clusters labels together).
                        # Falls back to a computed position (and logs a warning) in
                        # the rare case the click cache is missing an entry, so a
                        # label is never silently dropped.
                        if self.use_smaract_stage:
                            _ref_x = getattr(self, '_image_tab_ref_smaract_x', None)
                            _ref_y = getattr(self, '_image_tab_ref_smaract_y', None)
                        else:
                            _ref_x = getattr(self, '_image_tab_ref_x', float(self.x_pos))
                            _ref_y = getattr(self, '_image_tab_ref_y', float(self.y_pos))
                        cx, cy = self._resolve_point_canvas_xy(phys_x, phys_y, _ref_x, _ref_y, cw, ch)

                    if cx is not None:
                        is_datum = (self.datum_point is not None
                                    and (phys_x, phys_y) == self.datum_point)
                        label, fill = self._measurement_label_fill(i, height, is_datum)
                        canvas.create_text(
                            cx, cy - 15,
                            text=label,
                            fill=fill, font=("Arial", 12, "bold"),
                            tags=("custom_pt", "measurement_text", f"meas_idx_{i}"))

                # Bind left-click on text labels to toggle analysis selection
                canvas.tag_bind("measurement_text", "<Button-1>", self._toggle_analysis_point)

                # Point labels exist now: enable the Display Heights/Indices toggle
                if self.measured_data:
                    self._safe_btn('_display_heights_btn', state="normal")
                    self._safe_btn('_stitch_display_heights_btn', state="normal")

        # ── CSV Export Logic ──────────────────────────────────────────────────
        export_base = os.path.join(os.path.expanduser('~'), 'optical_module', 'Data_Exports')
        map_dir = os.path.join(export_base, 'Mapped_Surfaces')
        pts_dir = os.path.join(export_base, 'Individual_Points')
        os.makedirs(map_dir, exist_ok=True)
        os.makedirs(pts_dir, exist_ok=True)

        def show_custom_success_popup(file_path, is_grid=True):
            """Scan-complete confirmation. Gwyddion only makes sense for a dense
            grid scan (a handful of sparse individual points can't be turned into
            a surface, so that branch only ever gets a Close button)."""
            popup = ctk.CTkToplevel(self)
            popup.title("Scan Complete")
            # Grid scans get a second (Gwyddion) button on the same row, but the
            # window height doesn't depend on that -- the individual-points case
            # was reusing the grid size and left empty space at the bottom.
            popup.geometry("450x200" if is_grid else "450x150")
            popup.attributes("-topmost", True)
            popup.grab_set()   # focus lock

            ctk.CTkLabel(popup, text="Measurement successfully completed",
                         font=("Arial", 16, "bold")).pack(pady=(20, 5))
            ctk.CTkLabel(popup, text=f"Data saved to:\n{file_path}",
                         wraplength=400).pack(pady=(0, 20), padx=20)

            btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
            btn_frame.pack(fill="x", pady=10)

            if is_grid:
                btn_frame.grid_columnconfigure(0, weight=1)
                btn_frame.grid_columnconfigure(3, weight=1)

                close_btn = ctk.CTkButton(btn_frame, text="Close", width=120, command=popup.destroy)
                close_btn.grid(row=0, column=1, padx=10)

                gwyddion_btn = ctk.CTkButton(
                    btn_frame, text="View in Gwyddion", fg_color="purple", width=150,
                    command=lambda: [self.launch_gwyddion(), popup.destroy()])
                gwyddion_btn.grid(row=0, column=2, padx=10)
            else:
                close_btn = ctk.CTkButton(btn_frame, text="Close", width=120, command=popup.destroy)
                close_btn.pack(pady=10)

        if getattr(self, '_sequence_mode', 'custom') == "grid":
            csv_path = os.path.join(map_dir, self._sequence_csv)
            try:
                with open(csv_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Site', 'X_mm', 'Y_mm', 'Z_mm'])
                    for i, (px, py, h) in enumerate(self.measured_data):
                        is_datum = (self.datum_point is not None and (px, py) == self.datum_point)
                        site_label = "0" if is_datum else str(i + 1)
                        writer.writerow([site_label, f"{px:.4f}", f"{py:.4f}", f"{h:.4f}"])
                print(f"[surface_map] Grid scan complete. Data saved to {csv_path}")
                self.last_exported_csv = csv_path
                show_custom_success_popup(csv_path, is_grid=True)
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save CSV:\n{e}")
            self._sequence_mode = "custom"   # reset so the next custom scan draws labels

        else:
            # Automatically export Individual Points
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            sample_id = getattr(self, 'curr_sample_id', 'Unknown')
            csv_path = os.path.join(pts_dir, f"Points_{sample_id}_{timestamp}.csv")
            try:
                with open(csv_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Site', 'X_mm', 'Y_mm', 'Z_mm', 'Height_mm'])
                    current_z = self.z_pos
                    for i, (px, py, h) in enumerate(self.measured_data):
                        is_datum = (self.datum_point is not None and (px, py) == self.datum_point)
                        site_label = "0" if is_datum else str(i + 1)
                        h_str = f"{h:.4f}" if not math.isnan(h) else "NaN"
                        writer.writerow([site_label, f"{px:.4f}", f"{py:.4f}", current_z, h_str])
                print(f"[custom_scan] Individual points saved to {csv_path}")
                self.last_exported_csv = csv_path
                show_custom_success_popup(csv_path, is_grid=False)
            except Exception as e:
                print(f"Failed to save individual points CSV: {e}")

        # ── Close Confocal socket now that all measurements are complete ─────
        self._close_confocal_socket()

        # ── Return Optical assembly to its pre-sequence position ──────────────
        # Z must be restored too, not just X/Y: the confocal auto-focus/measurement
        # steps leave Z parked at the confocal's focal height, not the camera's.
        origin_x = getattr(self, '_sequence_origin_x', float(self.x_pos))
        origin_y = getattr(self, '_sequence_origin_y', float(self.y_pos))
        origin_z = getattr(self, '_sequence_origin_z', float(self.z_pos))
        print(f"[sequence] returning to origin ({origin_x:.4f}, {origin_y:.4f}, {origin_z:.4f}) mm")
        self.send_goto_command(origin_x, origin_y, origin_z, show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0

        # Material Removal drawer hook: deliver heights if a session capture is pending
        self._fire_material_session_callback(raw_points_all)

        self.after(100, self._sequence_unlock_buttons)

    def _sequence_unlock_buttons(self):
        """Poll until the return-to-origin move finishes, then re-enable all
        three action buttons."""
        if self.module_status != "Idle":
            self.after(100, self._sequence_unlock_buttons)
            return

        # Safety-net: close socket in case any abort path didn't reach _process_measurement_results
        self._close_confocal_socket()

        # scan is over (done or aborted): hide the active-node dot
        self._clear_scan_progress_dot()

        # Sequence is fully done: click-to-move is safe again
        self._sequence_active = False

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
        """Legacy shim: delegates to start_surface_map."""
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
        # The node at self._grid_datum_ij (default (0,0) = visual top-left) is the
        # grid-scan datum; rendered pink and slightly larger so it stands out
        # (matches the pink used for a datum that lands on a corner handle).
        datum_ij = getattr(self, '_grid_datum_ij', (0, 0))
        for i in range(nx):
            xi = x0 + i * (x1 - x0) / (nx - 1)
            for j in range(ny):
                yj = y0 + j * (y1 - y0) / (ny - 1)
                is_datum = (i, j) == datum_ij
                r = DOT_R + 2 if is_datum else DOT_R
                color = "pink" if is_datum else "#00FF88"
                canvas.create_oval(xi - r, yj - r,
                                    xi + r, yj + r,
                                    fill=color, outline="",
                                    tags="roi_grid")

        # ── Corner handles (drawn last so they sit on top) ────────────────────
        # A corner handle sits at the same position as a grid node. if that node
        # is the current datum, tint the handle pink instead of gold so the datum
        # stays visible (it would otherwise be hidden under the opaque handle).
        corner_ij = {(x0, y0): (0, 0), (x1, y0): (nx - 1, 0),
                     (x0, y1): (0, ny - 1), (x1, y1): (nx - 1, ny - 1)}
        for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            is_datum_corner = corner_ij[(cx, cy)] == datum_ij
            canvas.create_oval(cx - HANDLE_R, cy - HANDLE_R,
                                cx + HANDLE_R, cy + HANDLE_R,
                                fill="pink" if is_datum_corner else "#FFD700",
                                outline="#FFFFFF", width=1,
                                tags="roi_grid")

    def _nearest_grid_node(self, mx, my, x0, y0, x1, y1, nx, ny):
        """Return the (i, j) screen-space grid node closest to canvas point (mx, my).
        i = column (0=left), j = row (0=top): same indexing _roi_redraw_grid uses."""
        best_ij = (0, 0)
        best_dist = None
        for i in range(nx):
            xi = x0 + i * (x1 - x0) / (nx - 1)
            for j in range(ny):
                yj = y0 + j * (y1 - y0) / (ny - 1)
                dist = (mx - xi) ** 2 + (my - yj) ** 2
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_ij = (i, j)
        return best_ij

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
        # Bench calibration: ~21 s fixed overhead (move to the SmarAct + home)
        # plus a per-point rate that differs by stage (see constants above).
        per_point_s = _GRID_SCAN_PER_POINT_S_SMARACT if self.use_smaract_stage else _GRID_SCAN_PER_POINT_S_MODULE
        est_s  = _GRID_SCAN_SETUP_S + total * per_point_s
        self._roi_info_area.set(f"Total Area: {area_x:.3f} × {area_y:.3f} mm")
        self._roi_info_count.set(f"Total Points: {total}")
        self._roi_info_time.set(f"Est. Duration: ~{est_s:.1f} s")

    # ──────────────────────────────────────────────────────────────────────────
    # ROI pan-drag (reposition box without Ctrl)
    # ──────────────────────────────────────────────────────────────────────────

    def _roi_or_move_press(self, event, canvas):
        """<Button-1> three-way dispatcher.

        Priority (checked in order):
          0. Click on an analysis marker / label → ignore (let tag_bind handle it).
          1. Click within CORNER_R of a corner handle → resize mode.
          2. Click inside the grid box → move mode.
          3. Click outside → fall through to click_to_move (hardware command).
        """
        # Prevent moving ROI globals from the micro-view while macro-view is active
        if getattr(self, 'active_main_view', 'default') == 'stitched' and canvas is getattr(self, '_image_tab_canvas', None):
            messagebox.showwarning("Action Blocked", "Please click 'Finish' on the stitched image tab (Main) first before taking measurements on the Image tab.")
            return
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
                    canvas.configure(cursor="hand2")   # clenched: actively grabbing
                    return

            # ── 2. Inside box → move mode ─────────────────────────────────────
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self._roi_mode       = "move"
                self._roi_pan_active = True
                self._roi_pan_start  = (event.x, event.y)
                canvas.configure(cursor="fleur")       # 4-way: actively moving
                return

        # ── 3. Outside / no ROI → hardware click-to-move ─────────────────────
        self._roi_mode       = "none"
        self._roi_pan_active = False
        self.click_to_move(event)

    def _roi_pan_motion(self, event, canvas):
        """<B1-Motion>: translate (move mode) or snap-resize (resize mode) the grid.

        Move mode:  Box translates rigidly. cell sizes and measurement counts
                    stay unchanged.

        Resize mode: The fixed anchor corner is held in place.  The dragged
                     corner snaps to the nearest whole-cell boundary so that the
                     physical cell size never changes.  Measurement counts update
                     live in the bottom-menu entries.
        """
        if not self._roi_pan_active:
            return

        # Moving/resizing the grid invalidates any index/height labels drawn
        # from a previous scan at the grid's old position — drop them rather
        # than leave them stuck pointing at nodes that no longer exist there.
        canvas.delete("measurement_text")

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
            print("[roi_resize] aborted: no resize anchor set")
            return
        if self._canvas_disp_w == 0 or self._canvas_orig_w == 0:
            print(f"[roi_resize] aborted: canvas geometry not ready "
                  f"(disp_w={self._canvas_disp_w}, orig_w={self._canvas_orig_w})")
            return

        try:
            cell_x = float(self._roi_cell_x.get())
            cell_y = float(self._roi_cell_y.get())
        except (ValueError, AttributeError, tk.TclError) as e:
            print(f"[roi_resize] aborted: could not read cell size entries — {e}")
            return
        if cell_x <= 0 or cell_y <= 0:
            print(f"[roi_resize] aborted: non-positive cell size ({cell_x}, {cell_y})")
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

        # ── Step 3: discretise (snap to nearest whole-cell count) ─────────────
        if px_per_cell_x <= 0 or px_per_cell_y <= 0:
            print(f"[roi_resize] aborted: non-positive pixel pitch "
                  f"(px_per_cell_x={px_per_cell_x}, px_per_cell_y={px_per_cell_y})")
            return
        cols = max(1, round(raw_px / px_per_cell_x))
        rows = max(1, round(raw_py / px_per_cell_y))
        # Sanity clamp: an unexpectedly tiny px_per_cell (e.g. canvas geometry not
        # yet realized) would otherwise blow this up to thousands of cells and hang
        # the UI redrawing them, which looks indistinguishable from "nothing happens".
        MAX_CELLS = 200
        if cols > MAX_CELLS or rows > MAX_CELLS:
            print(f"[roi_resize] WARNING: computed {cols}x{rows} cells "
                  f"(px_per_cell=({px_per_cell_x:.4f}, {px_per_cell_y:.4f})) — "
                  f"clamping to {MAX_CELLS} to avoid hanging the redraw")
            cols = min(cols, MAX_CELLS)
            rows = min(rows, MAX_CELLS)
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

        Move mode:   Only the position changed. cell sizes are locked, so we
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
        has_roi = (self._roi_active_canvas is canvas
                   and self._roi_canvas_x0 < self._roi_canvas_x1)

        # 0. Ctrl held → crosshair regardless of position, plus a live grid-node
        # hover preview (yellow) so the user can see which node Ctrl+Right-Click
        # would select as the grid-scan datum before committing.
        if event.state & 0x0004:
            canvas.configure(cursor="crosshair")
            if has_roi:
                x0, y0 = self._roi_canvas_x0, self._roi_canvas_y0
                x1, y1 = self._roi_canvas_x1, self._roi_canvas_y1
                nx = max(2, self.map_grid_x)
                ny = max(2, self.map_grid_y)
                i, j = self._nearest_grid_node(event.x, event.y, x0, y0, x1, y1, nx, ny)
                xi = x0 + i * (x1 - x0) / (nx - 1)
                yj = y0 + j * (y1 - y0) / (ny - 1)
                R = 5
                canvas.delete("roi_grid_hover")
                canvas.create_oval(xi - R, yj - R, xi + R, yj + R,
                                    fill="yellow", outline="",
                                    tags="roi_grid_hover")
            else:
                canvas.delete("roi_grid_hover")
            return

        canvas.delete("roi_grid_hover")   # Ctrl released: clear any hover preview

        # No active ROI on this canvas → plain arrow
        if not has_roi:
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
    # Stitched-view ROI: coord math uses calculate_stitched_phys_coords
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
        per_point_s = _GRID_SCAN_PER_POINT_S_SMARACT if self.use_smaract_stage else _GRID_SCAN_PER_POINT_S_MODULE
        est_s  = _GRID_SCAN_SETUP_S + total * per_point_s
        self._stitch_roi_info_area.set(f"Total Area: {area_x:.3f} × {area_y:.3f} mm")
        self._stitch_roi_info_count.set(f"Total Points: {total}")
        self._stitch_roi_info_time.set(f"Est. Duration: ~{est_s:.1f} s")

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
            return self._stitched_pixel_to_phys(
                fpx, fpy, stitched_w, stitched_h,
                grid_x, grid_y, scan_origin_x, scan_origin_y)

        px0, py0 = _c2p(self._roi_canvas_x0, self._roi_canvas_y0)
        px1, py1 = _c2p(self._roi_canvas_x1, self._roi_canvas_y1)
        if px0 is None or px1 is None:
            return

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
        Resize snap uses _s['sx']/_s['sy']: the live stitched-image scale.
        """
        if not self._roi_pan_active:
            return

        # Moving/resizing the grid invalidates any index/height labels drawn
        # from a previous scan at the grid's old position.
        canvas.delete("measurement_text")

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
            return self._stitched_pixel_to_phys(
                fpx, fpy, stitched_w, stitched_h,
                grid_x, grid_y, scan_origin_x, scan_origin_y)

        px0, py0 = _c2p(self._roi_canvas_x0, self._roi_canvas_y0)
        px1, py1 = _c2p(self._roi_canvas_x1, self._roi_canvas_y1)
        if px0 is None or px1 is None:
            return

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
        if self._last_stitched_was_smaract:
            grid_params = self._smaract_last_grid
            if grid_params is None:
                return
            _, _, nm_per_px_x, nm_per_px_y = self._smaract_stitched_tile_geometry(
                stitched_w, stitched_h, grid_x, grid_y, grid_params)
            dcx = cell_x * (nx - 1) * _s['sx'] * 1_000_000 / nm_per_px_x
            dcy = cell_y * (ny - 1) * _s['sy'] * 1_000_000 / nm_per_px_y
        else:
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
            return self._stitched_pixel_to_phys(
                fpx, fpy, stitched_w, stitched_h,
                grid_x, grid_y, scan_origin_x, scan_origin_y)

        px0, py0 = _c2p(self._roi_canvas_x0, self._roi_canvas_y0)
        px1, py1 = _c2p(self._roi_canvas_x1, self._roi_canvas_y1)
        if px0 is None or px1 is None:
            return
        self.roi_phys_x_start = min(px0, px1)
        self.roi_phys_x_end   = max(px0, px1)
        self.roi_phys_y_start = min(py0, py1)
        self.roi_phys_y_end   = max(py0, py1)

    # ──────────────────────────────────────────────────────────────────────────
    # Map Surface: validate and (WIP) launch scan
    # ──────────────────────────────────────────────────────────────────────────

    def start_surface_map(self):
        """Validate all ROI / grid parameters and confirm the surface mapping job.

        Hardware scan execution is WIP: a TODO comment marks where
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

        self.map_grid_x = nx
        self.map_grid_y = ny

        # ── Phase 2: Generate raster-snake Optical coordinates ───────────────
        dx = (self.roi_phys_x_end - self.roi_phys_x_start) / (nx - 1) if nx > 1 else 0
        dy = (self.roi_phys_y_end - self.roi_phys_y_start) / (ny - 1) if ny > 1 else 0
        snake_route = []
        for j in range(ny):
            y = self.roi_phys_y_start + j * dy
            x_indices = range(nx) if j % 2 == 0 else reversed(range(nx))
            for i in x_indices:
                snake_route.append((self.roi_phys_x_start + i * dx, y))
        self._optimized_route = snake_route

        # ── Datum: convert the picked/default grid node (screen-space i,j) to a
        # physical point. Screen-row 0 is the visual top row (roi_phys_y_end),
        # but snake_route's own j=0 is roi_phys_y_start (visual bottom): flip.
        gi, gj_screen = self._grid_datum_ij
        gi = min(max(gi, 0), nx - 1)
        gj_screen = min(max(gj_screen, 0), ny - 1)
        gj_route = (ny - 1) - gj_screen
        self.datum_point = (self.roi_phys_x_start + gi * dx,
                             self.roi_phys_y_start + gj_route * dy)

        # ── Phase 2: Apply Confocal→Optical offset and bounds check ──────────
        # SmarAct samples: skip this (route points are already SmarAct-frame
        # coordinates, and the confocal offset is baked into the one-time
        # confocal-over-SmarAct parking step instead of per point).
        if self.use_smaract_stage:
            offset_route = snake_route
        else:
            CONFOCAL_DX = -1.418137875
            CONFOCAL_DY = -72.258765875
            offset_route = [(x + CONFOCAL_DX, y + CONFOCAL_DY) for x, y in snake_route]

        # SmarAct's legitimate travel range is symmetric (SMARACT_TRAVEL_MIN/MAX,
        # negative values are fine) — not the module stage's "must be >= 0" rule.
        if self.use_smaract_stage:
            for target_x, target_y in offset_route:
                if not (SMARACT_TRAVEL_MIN <= target_x <= SMARACT_TRAVEL_MAX
                        and SMARACT_TRAVEL_MIN <= target_y <= SMARACT_TRAVEL_MAX):
                    messagebox.showerror(
                        "Hardware Limit Exceeded",
                        f"Cannot execute grid scan: point ({target_x:.3f} mm, {target_y:.3f} mm) "
                        f"is outside the SmarAct stage's {SMARACT_TRAVEL_MIN:.1f} to "
                        f"{SMARACT_TRAVEL_MAX:.1f} mm travel range.\n\n"
                        f"Please reposition the sample so the entire scan region is within stage bounds."
                    )
                    return
        else:
            for target_x, target_y in offset_route:
                if target_x < 0 or target_y < 0:
                    messagebox.showerror(
                        "Hardware Limit Exceeded",
                        f"Cannot execute grid scan: point requires moving to "
                        f"({target_x:.3f} mm, {target_y:.3f} mm), which exceeds "
                        f"the hardware limit of 0 mm.\n\n"
                        f"Please reposition the sample so the entire scan region is within stage bounds."
                    )
                    return

        # ── Phase 3: Launch execution ─────────────────────────────────────────
        self._sequence_mode     = "grid"
        self._sequence_csv      = csv_name if csv_name.endswith('.csv') else f"{csv_name}.csv"
        self._sequence_origin_x = float(self.x_pos)
        self._sequence_origin_y = float(self.y_pos)
        self._sequence_origin_z = float(self.z_pos)

        # Open persistent Confocal socket; send R0 exactly once before the sequence.
        try:
            _cs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _cs.settimeout(_CONFOCAL_TIMEOUT)
            _cs.connect((_CONFOCAL_IP, _CONFOCAL_PORT))
            _cs.sendall("R0\r".encode('ascii'))
            _cs.recv(1024)
            self._confocal_socket = _cs
            print("[confocal] persistent socket open; measurement mode active")
        except Exception as _e:
            messagebox.showerror(
                "Confocal Unreachable",
                f"Cannot connect to the Confocal sensor:\n{_e}\n\n"
                f"Check that CL-Navigator is running and the network cable is connected."
            )
            return

        for _btn in ('_measure_heights_btn', '_clear_points_btn', '_map_surface_btn',
                     '_stitch_measure_heights_btn', '_stitch_clear_points_btn',
                     '_stitch_map_surface_btn'):
            self._safe_btn(_btn, state="disabled")
        self._sequence_active = True

        print(f"[surface_map] Grid {nx}×{ny} = {len(offset_route)} pts  "
              f"origin ({self._sequence_origin_x:.4f}, {self._sequence_origin_y:.4f}) mm  "
              f"datum ({self.datum_point[0]:.4f}, {self.datum_point[1]:.4f}) mm  "
              f"→ {self._sequence_csv}")
        self._begin_autofocus_datum(offset_route)

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

        self.map_grid_x = nx
        self.map_grid_y = ny

        # ── Phase 2: Generate raster-snake Optical coordinates ───────────────
        dx = (self.roi_phys_x_end - self.roi_phys_x_start) / (nx - 1) if nx > 1 else 0
        dy = (self.roi_phys_y_end - self.roi_phys_y_start) / (ny - 1) if ny > 1 else 0
        snake_route = []
        for j in range(ny):
            y = self.roi_phys_y_start + j * dy
            x_indices = range(nx) if j % 2 == 0 else reversed(range(nx))
            for i in x_indices:
                snake_route.append((self.roi_phys_x_start + i * dx, y))
        self._optimized_route = snake_route

        # ── Datum: convert the picked/default grid node (screen-space i,j) to a
        # physical point. Screen-row 0 is the visual top row (roi_phys_y_end),
        # but snake_route's own j=0 is roi_phys_y_start (visual bottom): flip.
        gi, gj_screen = self._grid_datum_ij
        gi = min(max(gi, 0), nx - 1)
        gj_screen = min(max(gj_screen, 0), ny - 1)
        gj_route = (ny - 1) - gj_screen
        self.datum_point = (self.roi_phys_x_start + gi * dx,
                             self.roi_phys_y_start + gj_route * dy)

        # ── Phase 2: Apply Confocal→Optical offset and bounds check ──────────
        # SmarAct samples: skip this (route points are already SmarAct-frame
        # coordinates, and the confocal offset is baked into the one-time
        # confocal-over-SmarAct parking step instead of per point).
        if self.use_smaract_stage:
            offset_route = snake_route
        else:
            CONFOCAL_DX = -1.418137875
            CONFOCAL_DY = -72.258765875
            offset_route = [(x + CONFOCAL_DX, y + CONFOCAL_DY) for x, y in snake_route]

        # SmarAct's legitimate travel range is symmetric (SMARACT_TRAVEL_MIN/MAX,
        # negative values are fine) — not the module stage's "must be >= 0" rule.
        if self.use_smaract_stage:
            for target_x, target_y in offset_route:
                if not (SMARACT_TRAVEL_MIN <= target_x <= SMARACT_TRAVEL_MAX
                        and SMARACT_TRAVEL_MIN <= target_y <= SMARACT_TRAVEL_MAX):
                    messagebox.showerror(
                        "Hardware Limit Exceeded",
                        f"Cannot execute grid scan: point ({target_x:.3f} mm, {target_y:.3f} mm) "
                        f"is outside the SmarAct stage's {SMARACT_TRAVEL_MIN:.1f} to "
                        f"{SMARACT_TRAVEL_MAX:.1f} mm travel range.\n\n"
                        f"Please reposition the sample so the entire scan region is within stage bounds."
                    )
                    return
        else:
            for target_x, target_y in offset_route:
                if target_x < 0 or target_y < 0:
                    messagebox.showerror(
                        "Hardware Limit Exceeded",
                        f"Cannot execute grid scan: point requires moving to "
                        f"({target_x:.3f} mm, {target_y:.3f} mm), which exceeds "
                        f"the hardware limit of 0 mm.\n\n"
                        f"Please reposition the sample so the entire scan region is within stage bounds."
                    )
                    return

        # ── Phase 3: Launch execution ─────────────────────────────────────────
        self._sequence_mode     = "grid"
        self._sequence_csv      = csv_name if csv_name.endswith('.csv') else f"{csv_name}.csv"
        self._sequence_origin_x = float(self.x_pos)
        self._sequence_origin_y = float(self.y_pos)
        self._sequence_origin_z = float(self.z_pos)

        # Open persistent Confocal socket; send R0 exactly once before the sequence.
        try:
            _cs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _cs.settimeout(_CONFOCAL_TIMEOUT)
            _cs.connect((_CONFOCAL_IP, _CONFOCAL_PORT))
            _cs.sendall("R0\r".encode('ascii'))
            _cs.recv(1024)
            self._confocal_socket = _cs
            print("[confocal] persistent socket open; measurement mode active")
        except Exception as _e:
            messagebox.showerror(
                "Confocal Unreachable",
                f"Cannot connect to the Confocal sensor:\n{_e}\n\n"
                f"Check that CL-Navigator is running and the network cable is connected."
            )
            return

        for _btn in ('_measure_heights_btn', '_clear_points_btn', '_map_surface_btn',
                     '_stitch_measure_heights_btn', '_stitch_clear_points_btn',
                     '_stitch_map_surface_btn'):
            self._safe_btn(_btn, state="disabled")
        self._sequence_active = True

        print(f"[surface_map_stitched] Grid {nx}×{ny} = {len(offset_route)} pts  "
              f"origin ({self._sequence_origin_x:.4f}, {self._sequence_origin_y:.4f}) mm  "
              f"datum ({self.datum_point[0]:.4f}, {self.datum_point[1]:.4f}) mm  "
              f"→ {self._sequence_csv}")
        self._begin_autofocus_datum(offset_route)

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
                                                    self.empty_folder_rpi(),
                                                    self._abort_smaract_scan_if_active()])

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
        # Stitching may have already finished while the user was on another
        # tab (this layout gets rebuilt fresh every time Main is revisited) --
        # reflect that immediately instead of always starting back at
        # "Image Stitching..." / disabled regardless of true progress.
        _stitched_ready = os.path.exists(stitched_img_path)
        self.complete_image_btn = ctk.CTkButton(
            button_frame,
            text="Open Completed Image" if _stitched_ready else "Image Stitching...",
            fg_color="green", width=150, height=30,
            state="normal" if _stitched_ready else "disabled",
            command=lambda: self.after(10, lambda: self.display_stitched_inline(stitched_img_path)))
        self.complete_image_btn.pack(side=ctk.LEFT, expand=True, padx=5, pady=1)

        #Finish button - creates new folder with time stamp, and transfers images from buffer to complete
        new_folder_path = f"{self.complete_stitching_folder}/{self.curr_sample_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        finish_button = ctk.CTkButton(button_frame, text="Finish",
                                      command=lambda:[setattr(self, 'active_main_view', 'default'),
                                                       self.display_main_tab(), self.create_transfer_folder_pc(self.buffer_stitching_folder,new_folder_path)])
        finish_button.pack(side=ctk.RIGHT, expand=True, padx=1, pady=1)

        #Stop button
        stop_button = ctk.CTkButton(button_frame, text="STOP", fg_color="red",
                                    command=lambda:[setattr(self, 'active_main_view', 'default'),
                                                    self.display_main_tab(),
                                                    self.send_simple_command("exe_stop", False),
                                                    setattr(self, 'scan_in_progress', False),
                                                    setattr(self, 'saw_scanning_status', False),
                                                    setattr(self, 'scanning_state', 0),
                                                    self._abort_smaract_scan_if_active()])
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
            if filename.lower().endswith(supported_extensions) and not filename.startswith("._") and not filename.startswith("stitched_"):
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
        # grid placeholders are filled positionally: a missing tile shifts
        # every subsequent image into the wrong cell.
        if len(images) < self.expected_image_count:
            self.after(1000, self.poll_for_new_images)
            return

        # Full set confirmed. sort numerically by integer prefix so the grid
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

        # All tiles loaded: unlock the stitched-image button. Guarded: this
        # keeps firing on its .after() schedule even if the user has since
        # navigated off the Main tab and this button no longer exists.
        self._safe_btn('complete_image_btn', state="normal")


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
        # Track when Pi reports a scanning status so we only trigger the 0→1
        # transition on a genuine Scanning→Idle edge, not on a spurious Idle
        # that arrives before the hardware starts moving.
        if "Scanning" in self.module_status:
            self.saw_scanning_status = True

        #Change state to start scanning process
        if (self.scanning_state == 0
            and self.scan_in_progress
            and self.module_status == "Idle"
            and self.saw_scanning_status):

            # Module returned to Idle after a commanded scan. stage is at the
            # last tile (top-right corner). Snapshot for click-to-move maths.
            self.saw_scanning_status = False
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
            self._last_stitched_was_smaract = False

            # Remove any stitched file left by a previous run's Fiji thread that finished
            # after empty_folder_pc ran, so it cannot bleed into the new tile grid.
            _stale_stitched = os.path.join(self.buffer_stitching_folder, f"stitched_{self.curr_sample_id}.jpg")
            if os.path.exists(_stale_stitched):
                os.remove(_stale_stitched)

            self.start_stitching(self.scanning_grid_x, self.scanning_grid_y, self.buffer_stitching_folder, self.buffer_stitching_folder, self.curr_sample_id)

            # Only rebuild the live scanning-layout UI if Main's "scanning" view
            # is actually the one on screen right now. This runs on every status
            # poll regardless of which tab the user is looking at, and
            # main_right_frame gets destroyed the moment they switch away from
            # Main -- rebuilding against a destroyed frame raised here, which
            # left scanning_state stuck at 2 forever (re-spawning a new
            # start_stitching() thread on every subsequent poll) until the user
            # revisited Main tab and happened to provide a fresh frame.
            _mrf = getattr(self, 'main_right_frame', None)
            if self.active_main_view == "scanning" and _mrf is not None and _mrf.winfo_exists():
                self.display_scanning_layout(self.scanning_grid_x, self.scanning_grid_y, _mrf)

            self.scanning_state = 3
        
        # Stitching thread has finished; file-ready polling is already running
        # via .after() from start_stitching. only reset the state machine here.
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
            self.use_smaract_stage = (sample_location == "SmarAct Stage")
            # Image tab's Live Position readout: show the SmarAct's own live X/Y
            # (already polled in Motion, see _smaract_poll_tick) instead of the
            # optical assembly's when a SmarAct sample is active.
            # hasattr alone isn't enough: a tab switch destroys the Image tab's
            # widgets (clear_frame), which leaves a stale Python reference behind
            # that still passes hasattr but throws on .configure().
            if (hasattr(self, '_image_tab_x_pos_label')
                    and self._image_tab_x_pos_label.winfo_exists()):
                _pos_x_var = self.smaract_x_pos_var if self.use_smaract_stage else self.rpi_x_pos_var
                _pos_y_var = self.smaract_y_pos_var if self.use_smaract_stage else self.rpi_y_pos_var
                self._image_tab_x_pos_label.configure(textvariable=_pos_x_var)
                self._image_tab_y_pos_label.configure(textvariable=_pos_y_var)
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


    def _start_scan(self, step_x, step_y, frame, compute_overlap=True):
        """
        Dispatches the "Scanning" OK action to the correct execution path:
        the Pi-driven optical-stage scan (exe_scanning) for Module Stage
        samples, or a PC-driven SmarAct MCS1 grid scan for SmarAct samples.
        """
        self._compute_overlap = compute_overlap
        self.empty_folder_pc(self.buffer_stitching_folder)
        if self.use_smaract_stage:
            self.start_smaract_scan(step_x, step_y, frame)
        else:
            self.send_scanning_data(step_x, step_y)
            self.display_loading_frame(frame)

    def _abort_smaract_scan_if_active(self):
        """Aborts an in-progress SmarAct-driven scan (called from STOP buttons)."""
        if self.use_smaract_stage:
            self._smaract_scan_abort = True
            self._smaract_scan_cleanup()

    # ------------------------- Shared SmarAct connection ------------------------- #
    # Opened once at startup and held for the app's lifetime (_smaract_startup_active).
    # Motion tab polling, scans, homing, and moves all reuse this same handle;
    # _smaract_lock serializes every stage.py call against it.

    def _smaract_ensure_open(self):
        """Opens the shared SmarAct handle if not already open. Returns success bool."""
        if self._smaract_handle is not None:
            return True
        with self._smaract_lock:
            if self._smaract_handle is not None:
                return True
            try:
                self._smaract_handle = open_smaract()
            except Exception as e:
                print(f"Warning: could not open SmarAct system — {e}")
                return False
        return True

    def _smaract_startup_connect(self):
        """Opens the shared handle once at launch. Runs on a background thread
        so a slow/absent SmarAct never blocks the window from appearing."""
        if not self._smaract_ensure_open():
            print("Warning: SmarAct not connected at startup (hardware unplugged?)")

    def close_smaract_on_exit(self):
        """Force-closes the connection regardless of in-progress activity.
        Only call this from the app's shutdown handler."""
        self._smaract_startup_active = False
        self._smaract_poll_active = False
        self._smaract_scan_running = False
        self._smaract_move_active = False
        self._smaract_homing_active = False
        self._smaract_maybe_close()

    def _smaract_maybe_close(self):
        """Closes the shared SmarAct handle if nothing still needs it."""
        if (self._smaract_poll_active or self._smaract_scan_running
                or self._smaract_move_active or self._smaract_homing_active
                or self._smaract_startup_active):
            return
        if self._smaract_handle is None:
            return
        with self._smaract_lock:
            if self._smaract_handle is None:
                return
            try:
                close_smaract(self._smaract_handle)
            except Exception as e:
                print(f"Warning: error closing SmarAct system — {e}")
            self._smaract_handle = None

    def _smaract_move_to(self, x_nm, y_nm, on_complete=None, on_error=None):
        """
        Moves the SmarAct stage to an absolute (x_nm, y_nm) target: shared by
        click-to-move, custom/grid measurement points, and stitched-image
        click-to-move. Z is never touched here; it always stays on the optical
        stage, and is handled separately (once, before any SmarAct point move)
        by the datum/autofocus setup. Rejects targets outside the SLC-1720's
        physical hard-stop travel range (SMARACT_TRAVEL_MIN/MAX) with an error
        dialog and aborts the move, rather than clamping them (negative
        coordinates themselves are fine, the stage just can't exceed ±6 mm).
        """
        if not (SMARACT_TRAVEL_MIN_NM <= x_nm <= SMARACT_TRAVEL_MAX_NM
                and SMARACT_TRAVEL_MIN_NM <= y_nm <= SMARACT_TRAVEL_MAX_NM):
            messagebox.showerror(
                "SmarAct Error",
                f"Cannot move SmarAct stage to ({x_nm / 1_000_000:.4f} mm, "
                f"{y_nm / 1_000_000:.4f} mm) — outside the stage's "
                f"{SMARACT_TRAVEL_MIN:.1f} to {SMARACT_TRAVEL_MAX:.1f} mm travel range. "
                f"Move rejected."
            )
            if on_error:
                on_error()
            return

        self._smaract_move_active = True
        if not self._smaract_ensure_open():
            messagebox.showerror("SmarAct Error", "Could not open SmarAct system.")
            self._smaract_move_active = False
            self._smaract_maybe_close()
            if on_error:
                on_error()
            return

        move_result = {}

        def _move():
            try:
                with self._smaract_lock:
                    move_to_absolute(self._smaract_handle, CHANNEL_X, CHANNEL_Y, x_nm, y_nm)
            except Exception as e:
                move_result['error'] = str(e)

        move_thread = Thread(target=_move, daemon=True)
        move_thread.start()
        self._smaract_move_wait(move_thread, move_result, on_complete, on_error)

    def _smaract_move_wait(self, move_thread, move_result, on_complete, on_error):
        if move_thread.is_alive():
            self.after(50, lambda: self._smaract_move_wait(move_thread, move_result, on_complete, on_error))
            return

        self._smaract_move_active = False
        self._smaract_maybe_close()

        if 'error' in move_result:
            messagebox.showerror("SmarAct Error", f"Move failed: {move_result['error']}")
            if on_error:
                on_error()
            return
        if on_complete:
            on_complete()

    def _start_smaract_position_polling(self):
        """Starts the live SmarAct X/Y position readout (smaract_x_pos_var/
        smaract_y_pos_var). Runs for the whole app session, not just while the
        Motion tab is open — the Image tab's Live Position reads from the same
        vars when a SmarAct sample is active."""
        self._smaract_poll_active = True
        self._smaract_poll_tick()

    def _smaract_poll_tick(self):
        if not self._smaract_poll_active:
            return

        if not self._smaract_ensure_open():
            self.smaract_enabled_var.set("No")
            self.smaract_x_pos_var.set("--")
            self.smaract_y_pos_var.set("--")
            self.after(5000, self._smaract_poll_tick)
            return

        if self._smaract_lock.acquire(blocking=False):
            try:
                x_nm = get_position(self._smaract_handle, CHANNEL_X)
                y_nm = get_position(self._smaract_handle, CHANNEL_Y)
                self.smaract_enabled_var.set("Yes")
                self.smaract_x_pos_var.set(f"{x_nm / 1_000_000:.6f}")
                self.smaract_y_pos_var.set(f"{y_nm / 1_000_000:.6f}")
            except Exception as e:
                print(f"Warning: SmarAct position read failed — {e}")
                self.smaract_enabled_var.set("No")
                self.smaract_x_pos_var.set("--")
                self.smaract_y_pos_var.set("--")
                self._smaract_handle = None
            finally:
                self._smaract_lock.release()
        # else: a scan move currently holds the lock. skip this tick's read and
        # leave the last displayed values in place.

        self.after(1000, self._smaract_poll_tick)

    def start_smaract_scan(self, step_x, step_y, frame):
        """
        Entry point for a SmarAct-driven grid scan: parks the optical carriage
        at the SmarAct focal position, then drives the real SmarAct MCS1 piezo
        stage through a grid, triggering a Pi image capture at each point.
        """
        if self.module_status != "Idle":
            messagebox.showerror("Status not in idle, wait to request scanning mode.")
            return
        if step_x <= 0 or step_y <= 0:
            messagebox.showerror("Invalid input", "Step values must be positive numbers")
            return

        self._smaract_scan_abort = False
        self._smaract_scan_running = True
        self._smaract_manifest = []
        self._smaract_step_x_mm = step_x
        self._smaract_step_y_mm = step_y

        self.display_loading_frame(frame)

        self._smaract_scan_auto_home()

    def _smaract_scan_auto_home(self):
        # blocking call, needs its own thread. reuses the shared handle so it
        # doesn't fight the persistent connection for the port (Resource Busy).
        def _worker():
            try:
                if not self._smaract_ensure_open():
                    print("[scan] ERROR: could not open SmarAct system for auto-home")
                else:
                    with self._smaract_lock:
                        home_smaract(self._smaract_handle)
            finally:
                self.after(0, self._smaract_scan_after_home)

        Thread(target=_worker, daemon=True).start()

    def _smaract_scan_after_home(self):
        if self._smaract_scan_abort:
            self._smaract_scan_cleanup()
            return

        self.empty_folder_rpi()
        # Each SmarAct scan captures its own 0..N-1 sequence, independent of
        # whatever a prior scan/sampling run left the Pi's image counter at.
        self.send_simple_command("exe_reset_image_count", checkIdle=False, show_success=False)

        # Park the camera carriage at the SmarAct focal position and hold it there
        # for the whole scan; only the SmarAct piezo stage moves point-to-point.
        self.send_goto_command(req_x=SMARACT_PARK_X, req_y=SMARACT_PARK_Y, req_z=SMARACT_PARK_Z, show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0
        self.after(500, self._smaract_scan_wait_park)

    def _smaract_scan_wait_park(self):
        if self._smaract_scan_abort:
            return
        if self.module_status != "Idle":
            self.after(200, self._smaract_scan_wait_park)
            return

        if not self._smaract_ensure_open():
            messagebox.showerror("SmarAct Error", "Could not open SmarAct system.")
            self._smaract_scan_running = False
            return

        # camera's parked, now lock in Z before touching X/Y
        self._smaract_scan_autofocus()

    def _smaract_scan_autofocus(self):
        if self._smaract_scan_abort:
            self._smaract_scan_cleanup()
            return

        # taller sample sits closer to the lens, needs a lower Z. center the
        # sweep on the sample's own height instead of a fixed window, same
        # idea as the module stage's STAGEFOCUSHEIGHT - get_curr_height()
        sample_height_mm = float(self.sample_data.get('initial_height', 0.0))
        z_center = SMARACT_PARK_Z - sample_height_mm

        autofocus_data = {
            "command": "exe_smaract_autofocus",
            "mode": self.mode,
            "module_status": self.module_status,
            "z_min": z_center - 1,
            "z_max": z_center + 1,
            "step_size": 0.05,
        }
        self.send_json_error_check(autofocus_data, "Autofocus request sent.", show_success=False)
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0
        self.after(200, self._smaract_scan_wait_autofocus)

    def _smaract_scan_wait_autofocus(self):
        if self._smaract_scan_abort:
            self._smaract_scan_cleanup()
            return
        if self.module_status != "Idle":
            self.after(200, self._smaract_scan_wait_autofocus)
            return

        # Z locked in, now build the X/Y grid. centered on wherever the SmarAct stage sits right now. since
        # the scan auto-homes first, that's the post-home reference position,
        # not necessarily wherever the sample actually is.
        with self._smaract_lock:
            center_x_nm = get_position(self._smaract_handle, CHANNEL_X)
            center_y_nm = get_position(self._smaract_handle, CHANNEL_Y)

        width_mm = float(self.sample_data.get('width', 0.0))
        height_mm = float(self.sample_data.get('height', 0.0))
        step_x_nm = round(self._smaract_step_x_mm * 1_000_000)
        step_y_nm = round(self._smaract_step_y_mm * 1_000_000)

        nx = max(int(width_mm // self._smaract_step_x_mm) + 1, 1)
        ny = max(int(height_mm // self._smaract_step_y_mm) + 1, 1)

        start_x_nm = center_x_nm - round((nx - 1) * step_x_nm / 2)
        # SmarAct Y is mounted opposite the camera's Y axis (same fact fixed for
        # click-to-move): ascending native Y = descending visual position. Start
        # at the high native-Y extreme so ascending row still means ascending
        # visual position, matching what Fiji expects from "order=[Up & Right]".
        start_y_nm = center_y_nm + round((ny - 1) * step_y_nm / 2)

        # Column-by-column, bottom-to-top within a column, then left-to-right:
        # matches the Fiji stitching macro's "type=[Grid: column-by-column]
        # order=[Up & Right]" tile-ordering assumption (StitchingMacro.ijm).
        route = []
        for col in range(nx):
            x_nm = start_x_nm + col * step_x_nm
            for row in range(ny):
                y_nm = start_y_nm - row * step_y_nm
                route.append((x_nm, y_nm))

        self._smaract_route = route
        self._smaract_nx = nx
        self._smaract_ny = ny
        self._smaract_index = 0
        # Recorded so a stitched-image click-to-move can map a tile-pixel click
        # directly back to the exact SmarAct nm coordinate that produced it.
        self._smaract_last_grid = {
            'start_x_nm': start_x_nm, 'start_y_nm': start_y_nm,
            'step_x_nm': step_x_nm, 'step_y_nm': step_y_nm,
            'nx': nx, 'ny': ny,
        }

        self._smaract_scan_next_point()

    def _smaract_scan_next_point(self):
        if self._smaract_scan_abort:
            self._smaract_scan_cleanup()
            return
        if self._smaract_index >= len(self._smaract_route):
            self._smaract_scan_finish()
            return

        x_nm, y_nm = self._smaract_route[self._smaract_index]
        move_result = {}

        def _move():
            try:
                with self._smaract_lock:
                    move_to_absolute(self._smaract_handle, CHANNEL_X, CHANNEL_Y, x_nm, y_nm)
            except Exception as e:
                move_result['error'] = str(e)

        move_thread = Thread(target=_move, daemon=True)
        move_thread.start()
        self.after(50, lambda: self._smaract_scan_wait_move(move_thread, move_result))

    def _smaract_scan_wait_move(self, move_thread, move_result):
        if self._smaract_scan_abort:
            self._smaract_scan_cleanup()
            return
        if move_thread.is_alive():
            self.after(50, lambda: self._smaract_scan_wait_move(move_thread, move_result))
            return
        if 'error' in move_result:
            messagebox.showerror("SmarAct Error", f"Move failed: {move_result['error']}")
            self._smaract_scan_cleanup()
            return

        self.after(SMARACT_SETTLING_DELAY_MS, self._smaract_scan_fire_capture)

    def _smaract_scan_fire_capture(self):
        if self._smaract_scan_abort:
            self._smaract_scan_cleanup()
            return

        x_nm, y_nm = self._smaract_route[self._smaract_index]
        self._smaract_manifest.append((self._smaract_index, x_nm, y_nm))

        self.send_simple_command("exe_scan_capture", checkIdle=False, show_success=False)
        self.module_status = "Capturing Image"
        self.status_lockout_time = time.time() + 0.5
        self.after(100, self._smaract_scan_wait_capture)

    def _smaract_scan_wait_capture(self):
        if self._smaract_scan_abort:
            self._smaract_scan_cleanup()
            return
        if self.module_status != "Idle":
            self.after(100, self._smaract_scan_wait_capture)
            return

        self._smaract_index += 1
        self._smaract_scan_next_point()

    def _smaract_scan_finish(self):
        self._smaract_scan_running = False
        self._smaract_maybe_close()

        self.transfer_rpi_thread = Thread(
            target=self.transfer_folder_rpi,
            kwargs={"destination_path": self.buffer_stitching_folder, "new_filename": True},
            daemon=True)
        self.transfer_rpi_thread.start()
        self.after(200, self._smaract_scan_wait_transfer)

    def _smaract_scan_wait_transfer(self):
        if self.transfer_rpi_thread.is_alive():
            self.after(200, self._smaract_scan_wait_transfer)
            return

        # The Pi-embedded image position metadata is meaningless here (the carriage
        # never moved), so use the grid shape computed from the SmarAct route instead
        # of extract_unique_positions.
        self.scanning_grid_x, self.scanning_grid_y = self._smaract_nx, self._smaract_ny

        stale_stitched = os.path.join(self.buffer_stitching_folder, f"stitched_{self.curr_sample_id}.jpg")
        if os.path.exists(stale_stitched):
            os.remove(stale_stitched)

        self._last_stitched_was_smaract = True

        self.start_stitching(self.scanning_grid_x, self.scanning_grid_y, self.buffer_stitching_folder, self.buffer_stitching_folder, self.curr_sample_id)

        # Recorded regardless of the current tab so display_main_tab can restore
        # the grid view (with the "Image Stitching..." button) when the user
        # comes back to Main, even if that happens after this scan's after()-chain
        # has already finished.
        self.active_main_view = "scanning"

        if self.current_tab != "Main":
            # main_right_frame dies on every tab switch (clear_frame nukes it),
            # so painting into it here would crash. stitching still runs fine in
            # the background either way; display_main_tab restores the grid view
            # (via active_main_view == "scanning") when the user comes back.
            return

        self.display_scanning_layout(self.scanning_grid_x, self.scanning_grid_y, self.main_right_frame)

        # optical scans get repainted for free by the ~1s Pi status heartbeat
        # (update_gui_elements), which keeps firing long after the scan itself
        # is done. SmarAct's after()-chain just ends here, no heartbeat, so one
        # update_idletasks() call isn't reliably enough for CTk to finish
        # blitting the new layout — fake that heartbeat for under a second.
        self._smaract_force_repaint(6)

    def _smaract_force_repaint(self, ticks_left):
        if ticks_left <= 0 or self.current_tab != "Main":
            return
        try:
            self.main_right_frame.update_idletasks()
        except Exception:
            return
        self.after(150, lambda: self._smaract_force_repaint(ticks_left - 1))

    def _smaract_scan_cleanup(self):
        """Called on abort (STOP) or a fatal error to release the scan's hold on the SmarAct handle."""
        self._smaract_scan_running = False
        self._smaract_maybe_close()

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
            self.scanning_state = 0  # reset state machine so 0→1 can fire on scan completion
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
        # raise Z first, holding X/Y, so the head clears before it swings over
        self.send_goto_command(
            req_x=float(self.x_pos),
            req_y=float(self.y_pos),
            req_z=SMARACT_PARK_Z,
            show_success=False
        )
        # local lock so a delayed Pi ack doesn't overwrite this before the move starts
        self.module_status = "Changing Position"
        self.status_lockout_time = time.time() + 2.0
        self.after(500, self._smaract_wait_then_xy)

    def _smaract_wait_then_xy(self):
        if self.module_status != "Idle":
            self.after(500, self._smaract_wait_then_xy)
            return
        self.send_goto_command(
            req_x=SMARACT_PARK_X,
            req_y=SMARACT_PARK_Y,
            req_z=SMARACT_PARK_Z
        )

    def toggle_interferometer_camera(self):
        if not self.is_at_confocal:
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
            messagebox.showerror(
                "Cannot Toggle",
                f"Toggle move rejected: target ({target_x:.4f}, {target_y:.4f}, {target_z:.4f}) mm "
                f"contains a negative value, which is past the stage's limit (0 mm)."
            )
            return

        try:
            self.send_goto_command(target_x, target_y, target_z, show_success=False)
        except Exception as e:
            print(f"Warning: toggle move failed — {e}")
            messagebox.showerror("Error", f"Toggle move failed: {e}")
            return

        self.is_at_confocal = not self.is_at_confocal
        self.confocal_toggle_btn.configure(text=new_label)

    def _start_smaract_homing(self):
        """
        Launch home_smaract() on a daemon Thread so the GUI stays responsive
        while the stage physically drives to its reference marks.

        Reuses the shared persistent SmarAct connection (the same one used by
        the Motion tab's live position polling and scans) instead of opening a
        second connection to the device. opening two connections to the same
        USB controller fails with SA_OpenSystem code 3 ("Resource Busy") if
        the shared handle is already open (e.g. Motion tab visible, or a scan
        in progress).

        The button is disabled and relabelled for the duration of the sequence,
        then restored on the main thread via after() once the thread finishes.
        A try/except guards against the button having been destroyed if the
        operator switches tabs before homing completes.
        """
        self.smaract_home_btn.configure(state="disabled", text="Homing...")

        def _worker():
            self._smaract_homing_active = True
            try:
                if not self._smaract_ensure_open():
                    print("[homing] ERROR: could not open SmarAct system")
                    return
                with self._smaract_lock:
                    home_smaract(self._smaract_handle)
            finally:
                self._smaract_homing_active = False
                self._smaract_maybe_close()
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

    def check_stitched_file_ready(self, filepath, retries=120, generation=0):
        """
        Non-blocking poll for the stitched output JPEG. Always called from the
        Tkinter main thread via .after(): never from the stitching thread.

        The generation parameter matches self.stitching_generation at spawn time.
        If a newer scan has started, the generation will differ and this stale
        poller silently exits, preventing it from enabling the new scan's button.

        Args:
            filepath (str): Absolute path to the expected stitched JPEG.
            retries (int): Remaining 500 ms poll attempts (default 120 = 60 s).
            generation (int): Scan generation at the time this poller was created.
        """
        if generation != self.stitching_generation:
            return  # stale poller from a previous scan: discard
        if os.path.exists(filepath):
            self.is_stitching = False
            try:
                self.complete_image_btn.configure(text="Open Completed Image", state="normal")
            except Exception:
                pass  # button's gone if the user tabbed away mid-scan, nothing to update
        elif retries > 0:
            self.after(500, lambda: self.check_stitched_file_ready(filepath, retries - 1, generation))
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

        # Increment generation so any poller from a previous scan self-discards.
        self.stitching_generation += 1
        gen = self.stitching_generation

        # Arm lock and start poll on the main thread before the thread begins
        self.is_stitching = True
        self.after(500, lambda: self.check_stitched_file_ready(stitched_path, generation=gen))

        compute_overlap = getattr(self, '_compute_overlap', True)
        self.stitching_thread = Thread(
            target=lambda: self.stitcher.run_stitching(grid_x, grid_y, input_dir, output_dir, sample_id, compute_overlap),
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
