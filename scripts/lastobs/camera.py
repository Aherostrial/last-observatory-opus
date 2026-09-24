"""Camera and its 6 second pull-back.

The move is baked per frame (quaternion + location keys) so every aspect of
it is controlled analytically:

    * distance to the astronaut grows exponentially (log-space dolly), which
      keeps the apparent expansion of the frame steady instead of lurching;
    * the view swings from over the astronaut's right shoulder to the wide
      composition; the look target drifts from the helmet to the frame's
      final centre in proportion to the frame size;
    * the camera 'up' rolls from the astronaut's local vertical to world up,
      so the horizon tilts away as the planet's curvature is revealed;
    * a slight focal-length push makes the hole loom larger as we retreat.
"""

import math

import bpy
from mathutils import Vector, Quaternion

from . import layout as L
from .util import collection, look_at_quat, frame_from_up


# Start framing, expressed in the astronaut's local frame (metres)
START_BACK = 1.30
START_RIGHT = 0.78
START_UP = -0.06
START_LOOK_BH = 0.55        # 0 = look at helmet, 1 = look at hole
LENS_START = 30.0
FSTOP = 5.6


def smootherstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (x * 6 - 15) + 10)


def ease_io(x, a=2.2):
    x = min(max(x, 0.0), 1.0)
    return x ** a / (x ** a + (1 - x) ** a)


def slerp_vec(a, b, t):
    a = a.normalized()
    b = b.normalized()
    d = max(-1.0, min(1.0, a.dot(b)))
    th = math.acos(d)
    if th < 1e-5:
        return a.lerp(b, t).normalized()
    s = math.sin(th)
    return (a * (math.sin((1 - t) * th) / s) + b * (math.sin(t * th) / s)).normalized()


def camera_path(helmet, ast_up, n=L.FRAMES):
    H = Vector(helmet)
    r_a, f_a, u_a = frame_from_up(ast_up, L.BH_DIR)
    C0 = H - f_a * START_BACK + r_a * START_RIGHT + u_a * START_UP
    d0 = (C0 - H).length
    look0 = ((H - C0).normalized() * (1 - START_LOOK_BH) + L.BH_DIR * START_LOOK_BH).normalized()
    T0 = C0 + look0 * d0

    C1 = L.CAM_END
    T1 = L.CAM_END_TARGET
    d1 = (C1 - H).length
    dir0 = (C0 - H) / d0
    dir1 = (C1 - H) / d1
    up0 = u_a
    up1 = Vector((0, 0, 1))

    keys = []
    for i in range(n):
        s = i / (n - 1)
        # hold a beat on the astronaut, accelerate, then settle
        g = 0.86 * ease_io(s, 1.9) + 0.14 * s
        d = d0 * (d1 / d0) ** g
        # swing happens mostly while we are still close
        dirv = slerp_vec(dir0, dir1, smootherstep(min(1.0, g * 1.15)))
        C = H + dirv * d
        lin = (d - d0) / (d1 - d0)
        T = T0.lerp(T1, smootherstep(lin ** 0.6))
        up = slerp_vec(up0, up1, smootherstep(g ** 0.9))
        fwd = (T - C).normalized()
        lens = LENS_START + (L.LENS_END - LENS_START) * smootherstep(s)
        keys.append((C, look_at_quat(fwd, up), lens))
    return keys


def build_camera(scene, ast=None):
    col = collection('Camera')
    cd = bpy.data.cameras.new('ShotCam')
    cd.sensor_fit = 'HORIZONTAL'
    cd.sensor_width = L.SENSOR
    cd.clip_start = 0.02
    cd.clip_end = 2000.0
    cam = bpy.data.objects.new('ShotCam', cd)
    col.objects.link(cam)
    scene.camera = cam
    cam.rotation_mode = 'QUATERNION'

    if ast is not None:
        helmet, ast_up, focus_obj = ast['helmet'], ast['up'], ast['focus']
    else:
        ast_up = L.AST_DIR
        helmet = L.AST_DIR * (L.R + 1.62)
        focus_obj = None

    cd.dof.use_dof = True
    cd.dof.aperture_fstop = FSTOP
    cd.dof.aperture_blades = 7
    cd.dof.aperture_rotation = math.radians(12)
    if focus_obj is not None:
        cd.dof.focus_object = focus_obj

    prev_q = None
    for i, (C, q, lens) in enumerate(camera_path(helmet, ast_up)):
        f = i + 1
        if prev_q is not None and prev_q.dot(q) < 0:
            q = -q                              # keep quaternion continuity
        prev_q = q
        cam.location = C
        cam.rotation_quaternion = q
        cd.lens = lens
        cam.keyframe_insert('location', frame=f)
        cam.keyframe_insert('rotation_quaternion', frame=f)
        cd.keyframe_insert('lens', frame=f)
        if focus_obj is None:
            cd.dof.focus_distance = (Vector(helmet) - C).length
            cd.dof.keyframe_insert('focus_distance', frame=f)

    for idb in (cam, cd):
        ad = idb.animation_data
        if ad and ad.action:
            from .sky import _iter_fcurves
            for fc in _iter_fcurves(ad.action):
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
    return cam
