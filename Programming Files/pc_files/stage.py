"""
stage.py: SmarAct MCS1 raster scan

Step 1: movement only, no confocal yet. Mock print stands in for each
measurement. Step 2 wires up confocal_looped.py.

Channel 0 = X, Channel 1 = Y.
Positions are nanometers, signed int, per the MCS1 API.
"""

import sys
import os
import time
import ctypes as ct
import subprocess

# unbinds the ftdi_sio kernel driver lock so the SmarAct can grab the port
subprocess.run('echo -n "1-4:1.0" | sudo tee /sys/bus/usb/drivers/ftdi_sio/unbind > /dev/null', shell=True)

# smaract_api/ needs to be on sys.path so the wrapper can find MCSControl.dll
_API_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smaract_api")
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

# wildcard import: need MCS_lib (raw cdll handle) for direct DLL calls below
from smaract_api.MCSControl_PythonWrapper import *  # noqa: E402, F401, F403

CHANNEL_X = ct.c_uint(0)
CHANNEL_Y = ct.c_uint(1)

# holdTime=0: stage drops closed-loop hold right after hitting target, so the
# snake scan can fire the next move with no delay
HOLD_TIME = 0


# ---------------------------------------------------------------------------
# Helper: API error checking
# ---------------------------------------------------------------------------
def _check(status: int, label: str = "") -> None:
    """Raise RuntimeError with a human-readable message on any non-SA_OK return."""
    if status != SA_OK:
        error_msg = ct.c_char_p()
        SA_GetStatusInfo(status, error_msg)
        decoded = error_msg.value[:].decode("utf-8") if error_msg.value else "unknown error"
        tag = f" [{label}]" if label else ""
        raise RuntimeError(f"SmarAct MCS error{tag}: {decoded} (code {status})")


# wait for physical stage to settle
def _wait_for_axes_stopped(mcs_handle: ct.c_ulong,
                            ch_x: ct.c_ulong,
                            ch_y: ct.c_ulong) -> None:
    """
    Blocks until both axes hit SA_TARGET_STATUS or SA_STOPPED_STATUS.
    10ms between polls so we don't hammer the USB bus.
    """
    status_x = ct.c_uint()
    status_y = ct.c_uint()

    while True:
        _check(SA_GetStatus_S(mcs_handle, ch_x, status_x), "GetStatus X")
        _check(SA_GetStatus_S(mcs_handle, ch_y, status_y), "GetStatus Y")

        x_idle = status_x.value in (SA_TARGET_STATUS, SA_STOPPED_STATUS)
        y_idle = status_y.value in (SA_TARGET_STATUS, SA_STOPPED_STATUS)

        if x_idle and y_idle:
            break

        time.sleep(0.01)  # 10 ms: prevents CPU thrashing on the polling loop


# ---------------------------------------------------------------------------
# Connection management (persistent handle, for use outside the __main__ demo)
# ---------------------------------------------------------------------------
def open_smaract():
    """Opens the MCS1 connection, enables sensors. Caller must close_smaract() when done."""
    _locator = ct.create_string_buffer(b"usb:ix:0")
    _options = ct.create_string_buffer(b"sync,reset")
    mcs_handle = ct.c_uint()

    status = MCS_lib.SA_OpenSystem(
        ct.byref(mcs_handle),
        ct.cast(_locator, ct.c_char_p),
        ct.cast(_options, ct.c_char_p),
    )
    if status != SA_OK:
        raise RuntimeError(f"SA_OpenSystem failed (code {status})")

    _check(SA_SetSensorEnabled_S(mcs_handle, SA_SENSOR_ENABLED), "SetSensorEnabled")

    return mcs_handle


def close_smaract(mcs_handle) -> None:
    """Closes a SmarAct MCS1 system handle opened by open_smaract()."""
    SA_CloseSystem(mcs_handle)


def get_position(mcs_handle: ct.c_ulong, channel: ct.c_uint) -> int:
    """Returns the current absolute position (nanometers) of the given channel."""
    position = ct.c_int()
    _check(SA_GetPosition_S(mcs_handle, channel, position), "GetPosition")
    return position.value


def move_to_absolute(mcs_handle, ch_x, ch_y, x_nm: int, y_nm: int) -> None:
    """Moves both axes at once, blocks until stopped. Positions are absolute nm."""
    _check(
        SA_GotoPositionAbsolute_S(mcs_handle, ch_x, x_nm, HOLD_TIME),
        "GotoPositionAbsolute X",
    )
    _check(
        SA_GotoPositionAbsolute_S(mcs_handle, ch_y, y_nm, HOLD_TIME),
        "GotoPositionAbsolute Y",
    )
    _wait_for_axes_stopped(mcs_handle, ch_x, ch_y)


def run_topography_map(
    mcs_handle,
    ch_x,
    ch_y,
    start_x: int,
    start_y: int,
    step_size_nm: int,
    num_points_x: int,
    num_points_y: int,
) -> list:
    """
    Drive a 2D snake raster scan and collect (mock) topography data.

    Parameters
    ----------
    mcs_handle    : ct.c_ulong handle returned by SA_OpenSystem (init in __main__).
    ch_x          : ct.c_ulong channel index for the X axis.
    ch_y          : ct.c_ulong channel index for the Y axis.
    start_x       : Absolute X start position in nanometers.
    start_y       : Absolute Y start position in nanometers.
    step_size_nm  : Grid step size in nanometers (same for X and Y).
    num_points_x  : Number of grid columns (X direction).
    num_points_y  : Number of grid rows    (Y direction).

    Returns
    -------
    list of (x_nm, y_nm, z_value) tuples, one per grid point.
    z_value is None until Step 2 wires up the Keyence CL-P015 confocal reading.

    Snake pattern: even rows go left→right, odd rows right→left.
    Every move is absolute from the origin, never relative, so rounding error
    can't accumulate over the scan.
    """
    scan_data: list = []
    total_points = num_points_x * num_points_y

    print(
        f"[scan] Grid: {num_points_y} rows × {num_points_x} cols = {total_points} points\n"
        f"       Origin: ({start_x} nm, {start_y} nm)  Step: {step_size_nm} nm"
    )

    point_index = 0

    for row in range(num_points_y):

        # Y stays fixed across this row
        abs_y = start_y + row * step_size_nm

        # snake: left→right on even rows, right→left on odd
        if row % 2 == 0:
            col_sequence = range(num_points_x)
        else:
            col_sequence = range(num_points_x - 1, -1, -1)

        for col in col_sequence:

            abs_x = start_x + col * step_size_nm

            move_to_absolute(mcs_handle, ch_x, ch_y, abs_x, abs_y)

            # piezo still rings a little after the encoder says we're there
            time.sleep(0.05)

            # TODO Step 2: z_reading = send_command("MS,1,1\r", confocal_socket)
            mock_z = None
            point_index += 1
            print(
                f"[MOCK MEASUREMENT] {point_index:>4}/{total_points}  "
                f"row={row:03d}  col={col:03d}  "
                f"X={abs_x:>12,} nm  Y={abs_y:>12,} nm  "
                f"Z=<confocal not yet connected>"
            )

            scan_data.append((abs_x, abs_y, mock_z))

    print(
        f"\n[done] Scan complete - {len(scan_data)} of {total_points} points collected."
    )
    return scan_data


# ---------------------------------------------------------------------------
# Operator entry point: manually edit scan parameters before running.
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    print("Starting Movement in 3 seconds...")
    time.sleep(3)

    # SA_FindSystems on Linux throws SA_DRIVER_ERROR (24) even with good
    # hardware, so skip discovery and open the first USB device by index.
    #
    # ct.cast to c_char_p needed for strict argtype validation on SA_OpenSystem.
    # mcs_handle is c_uint not c_ulong: SA_INDEX is 32-bit in the C API,
    # c_ulong is 8 bytes on Linux.
    _locator    = ct.create_string_buffer(b"usb:ix:0")
    _options    = ct.create_string_buffer(b"sync,reset")
    mcs_handle  = ct.c_uint()
    status = MCS_lib.SA_OpenSystem(
        ct.byref(mcs_handle),
        ct.cast(_locator, ct.c_char_p),
        ct.cast(_options, ct.c_char_p),
    )
    if status != SA_OK:
        raise RuntimeError(f"SA_OpenSystem failed (code {status})")
    print(f"[init] System opened (handle={mcs_handle.value})")

    # sensor enable is global, not per-axis. no confocal socket yet in Step 1
    _check(SA_SetSensorEnabled_S(mcs_handle, SA_SENSOR_ENABLED), "SetSensorEnabled")
    print("[init] Closed-loop sensors enabled")

    # finally block covers Ctrl+C too, so the port always gets released
    try:
        results = run_topography_map(
            mcs_handle   = mcs_handle,
            ch_x         = CHANNEL_X,
            ch_y         = CHANNEL_Y,
            start_x      = 0,       # nm (adjust after homing the stage)
            start_y      = 0,       # nm
            step_size_nm = 1_000,   # 1 µm step
            num_points_x = 3,
            num_points_y = 3,
        )
    finally:
        print("[cleanup] Closing SmarAct system...")
        SA_CloseSystem(mcs_handle)
        print("\nTest Complete. System closed safely.")

    print("\nCollected scan coordinates:")
    print(f"{'#':>4}  {'X (nm)':>12}  {'Y (nm)':>12}  Z")
    for i, (x, y, z) in enumerate(results, 1):
        print(f"{i:>4}  {x:>12,}  {y:>12,}  {z}")


def home_smaract(mcs_handle=None):
    """
    Drive both axes to their physical reference marks (true absolute zero).

    Parameters
    ----------
    mcs_handle : pass an already-open connection to reuse it (caller keeps
        ownership). Opening a second connection to the same USB device fails
        with SA_OpenSystem code 3 "Resource Busy", so this matters whenever
        the GUI's live polling or a scan already has the device open. Omit
        it for standalone use and this opens/closes its own connection.

    SA_FindReferenceMark_S returns immediately, doesn't block until homing's
    actually done, so we poll SA_GetStatus_S below.

    Safe to call from a background Thread, no GUI interaction.
    """
    owns_handle = mcs_handle is None
    if owns_handle:
        print("[homing] Opening SmarAct system...")
        try:
            mcs_handle = open_smaract()
        except Exception as e:
            print(f"[homing] ERROR: {e}")
            return
        print(f"[homing] System opened (handle={mcs_handle.value})")

    try:
        # sensors must be on for reference-mark detection to work
        _check(SA_SetSensorEnabled_S(mcs_handle, SA_SENSOR_ENABLED), "SetSensorEnabled")

        for channel_idx, axis_name in [(0, "X"), (1, "Y")]:
            channel = ct.c_uint(channel_idx)
            print(f"[homing] Searching for reference mark on {axis_name} axis...")

            result = SA_FindReferenceMark_S(
                mcs_handle,
                channel,
                SA_FORWARD_DIRECTION,  # scan toward positive end first
                0,                     # holdTime = 0 ms (release on arrival)
                1,                     # autoZero = 1 (set position to 0 nm on find)
            )

            if result != SA_OK:
                print(
                    f"[homing] ERROR: SA_FindReferenceMark_S failed on "
                    f"{axis_name} axis (code {result})"
                )
                return

            # 7 = still searching, break on stopped(0) or target-reached(4)
            poll_status = ct.c_uint()
            while True:
                _check(
                    SA_GetStatus_S(mcs_handle, channel, poll_status),
                    f"GetStatus {axis_name}",
                )
                if poll_status.value in (SA_STOPPED_STATUS, SA_TARGET_STATUS):
                    break
                time.sleep(0.1)

            print(f"[homing] {axis_name} axis homed - position = 0 nm.")

        print("[homing] Stage successfully homed. True absolute zero established.")

    except Exception as e:
        print(f"[homing] ERROR during homing sequence: {e}")

    finally:
        if owns_handle:
            SA_CloseSystem(mcs_handle)
            print("[homing] System closed.")