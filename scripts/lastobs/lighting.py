"""Key / fill / rim lighting.  Practical lights live with their props."""

import math

import bpy
from mathutils import Vector

from . import layout as L
from .util import collection


def sun(name, direction_to_light, color, strength, angle_deg, col, shadows=True):
    ld = bpy.data.lights.new(name, 'SUN')
    ld.color = color
    ld.energy = strength
    ld.angle = math.radians(angle_deg)
    ld.use_shadow = shadows
    ob = bpy.data.objects.new(name, ld)
    col.objects.link(ob)
    ob.rotation_mode = 'QUATERNION'
    # light travels from the source towards the scene
    ob.rotation_quaternion = L.sun_rotation_quat(-Vector(direction_to_light))
    return ob


def build_lights(scene):
    col = collection('Lighting')
    # Key: the inner accretion disk. Warm, fairly hard (the white-hot inner
    # ring is only a few degrees across), from the hole's direction.
    # Cheated ~40 deg towards camera-right so the planet shows a readable
    # crescent and the astronaut gets a side rim; still reads as coming from
    # the hole, which sits upper-right in frame.
    key_dir = (L.BH_DIR * 0.50 + L.R_C * 0.74 - L.F_C * 0.22 + L.U_C * 0.30).normalized()
    sun('Key_AccretionDisk', key_dir, (1.0, 0.60, 0.34), 6.5, 6.0, col)
    # Broad secondary glow from the outer disk / lensed arcs: softer, redder.
    sun('Key_DiskGlow', (L.BH_DIR + L.U_C * 0.12).normalized(), (1.0, 0.38, 0.16), 0.9, 28.0, col)
    # Fill: cold starlight from camera-left, very soft.
    fill_dir = (-L.F_C * 0.75 - L.R_C * 0.65 + L.U_C * 0.45).normalized()
    sun('Fill_Starlight', fill_dir, (0.50, 0.64, 1.0), 0.50, 40.0, col)
    # Under-rim: faint cool kiss on the planet's belly to keep its silhouette.
    rim_dir = (L.F_C * 0.8 - L.U_C * 0.6 - L.R_C * 0.2).normalized()
    sun('Rim_Under', rim_dir, (0.42, 0.55, 1.0), 0.8, 12.0, col, shadows=True)
    return col
