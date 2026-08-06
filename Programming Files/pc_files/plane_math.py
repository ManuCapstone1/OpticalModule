"""Best-fit reference plane math for tilt-corrected Z measurements."""

import numpy as np


def calculate_best_fit_plane(points):
    """Least-squares plane z = ax + by + c through N>=3 (x, y, z) pts. Returns (A, B, C, D)."""
    if len(points) < 3:
        raise ValueError("Need at least 3 points to fit a plane")

    pts = np.array(points, dtype=float)
    xs, ys, zs = pts[:, 0], pts[:, 1], pts[:, 2]

    # design matrix for z = a*x + b*y + c
    design = np.column_stack((xs, ys, np.ones_like(xs)))

    (a, b, c), _, rank, _ = np.linalg.lstsq(design, zs, rcond=None)

    if rank < 3:
        raise ValueError("Points are collinear or duplicate; no plane defined")

    # convert z = ax + by + c into Ax + By + Cz + D = 0 form
    return (a, b, -1.0, c)


def calculate_reference_plane(p1, p2, p3):
    """Fit plane Ax + By + Cz + D = 0 through 3 fiducial (x, y, z) pts. Returns (A, B, C, D)."""
    return calculate_best_fit_plane([p1, p2, p3])


def get_plane_z(x, y, plane_coeffs):
    """Theoretical Z of the reference plane at (x, y)."""
    a, b, c, d = plane_coeffs

    if c == 0:
        raise ValueError("Plane is vertical (C=0); Z is undefined at (x, y)")

    # solve Ax + By + Cz + D = 0 for z
    return -(a * x + b * y + d) / c


def get_corrected_height(x, y, raw_z, plane_coeffs):
    """Tilt-corrected height: raw reading minus the reference plane's Z at that point."""
    plane_z = get_plane_z(x, y, plane_coeffs)
    return raw_z - plane_z


def compare_planes(plane_a, plane_b, nodes):
    """Evaluate two plane fits at the same (x, y) locations (taken from
    `nodes`, an iterable of (x, y, ...) tuples -- only the x, y are used) and
    return one (x, y, z_a, z_b, delta_z) row per node. delta_z = z_a - z_b, so
    a positive value means plane A sits higher than plane B at that point.

    Comparing the fitted PLANES (rather than matching two independently
    measured point clouds by nearest neighbor) means any two sessions can be
    compared even if their points were never at the same (x, y) -- e.g. a
    Reference plane fit from fiducials on the sample holder's edge vs. a
    Set's plane fit from its own grid scan."""
    rows = []
    for (x, y, *_rest) in nodes:
        z_a = get_plane_z(x, y, plane_a)
        z_b = get_plane_z(x, y, plane_b)
        rows.append((x, y, z_a, z_b, z_a - z_b))
    return rows
