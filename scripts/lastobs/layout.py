"""Scene layout.

Everything is derived from the *final* (fully pulled back) camera framing, so
composition is designed first and geometry follows:

    * the planet sits low-left, the black hole looms upper-right
    * the astronaut stands on the upper-right limb, seen from behind,
      silhouetted against the lensed accretion disk (a Rueckenfigur)
    * the observatory crowns the planet, the radio mast breaks the left limb
"""

import math
from mathutils import Vector, Matrix

R = 9.0                     # planet radius [m]
FPS = 24
FRAMES = 144                # 6 seconds

# Final (revealed) camera
CAM_END = Vector((-16.5, -65.5, 2.3))
CAM_END_TARGET = Vector((4.2, 0.0, 7.6))
LENS_END = 36.0
SENSOR = 36.0
RES = (1920, 1080)


def cam_basis(loc, target, up=Vector((0, 0, 1))):
    f = (target - loc).normalized()
    r = f.cross(up).normalized()
    u = r.cross(f).normalized()
    return r, u, f


R_C, U_C, F_C = cam_basis(CAM_END, CAM_END_TARGET)


def ndc_direction(ndc_x, ndc_y, lens=LENS_END, basis=(R_C, U_C, F_C)):
    r, u, f = basis
    aspect = RES[1] / RES[0]
    tx = (ndc_x * 2 - 1) * (SENSOR * 0.5 / lens)
    ty = (ndc_y * 2 - 1) * (SENSOR * 0.5 / lens) * aspect
    return (f + r * tx + u * ty).normalized()


# Black hole: direction observer -> hole, chosen to land upper-right in the
# final frame.
BH_DIR = ndc_direction(0.655, 0.64)

# Disk plane: observer ~8.5 deg above the disk, the major axis rolled so it
# descends towards the planet (leads the eye from the hole to the planet).
_INC = math.radians(8.5)
_ROLL = math.radians(15.0)
_upp = (U_C - BH_DIR * U_C.dot(BH_DIR)).normalized()
_rgt = BH_DIR.cross(_upp).normalized()
_up_rolled = (_upp * math.cos(_ROLL) - _rgt * math.sin(_ROLL)).normalized()
DISK_NORMAL = (_up_rolled * math.cos(_INC) - BH_DIR * math.sin(_INC)).normalized()


def surf_dir(ang_right_deg, toward_cam=0.0):
    """Direction from the planet centre: rotated ang degrees clockwise from
    the image 'up', tilted towards (+) / away from (-) the final camera."""
    a = math.radians(ang_right_deg)
    d = U_C * math.cos(a) + R_C * math.sin(a) - F_C * toward_cam
    return d.normalized()


# Key sites on the planet (unit directions from the centre)
AST_DIR = surf_dir(27.0, 0.02)          # astronaut on the upper-right limb
OBS_DIR = surf_dir(-8.0, -0.04)         # observatory crowning the planet
MAST_DIR = surf_dir(-41.0, 0.02)        # radio mast breaking the left limb
DISH_DIR = surf_dir(-23.0, 0.62)        # dish on the camera-facing slope
SOLAR_DIR = surf_dir(40.0, 0.62)        # small solar array, front right
CRATE_DIR = surf_dir(-26.0, -0.25)      # supply crates behind the dome

PAD_RADIUS = 3.6                        # levelled observatory pad [m]


def sun_rotation_quat(direction_from_light):
    """Blender lights shine along local -Z."""
    d = Vector(direction_from_light).normalized()
    return d.to_track_quat('-Z', 'Y')
