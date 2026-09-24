"""Observatory, radio mast, dish, solar array, crates, path lights, cables."""

import math
import random

import bpy
import bmesh
from mathutils import Vector, Matrix

from . import layout as L
from . import materials as M
from .util import (collection, mesh_object, empty, place_on, add_mod, bevel, subsurf,
                   bm_cylinder, bm_box, bm_torus, frame_from_up, basis_matrix)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def parent_to(obj, parent):
    obj.parent = parent
    obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def site(name, col, loc, up, fwd_hint):
    e = empty(name, col, size=0.6, kind='ARROWS')
    place_on(e, loc, up, fwd_hint)
    return e


def part(name, col, parent, build, mat, smooth=False, mods=()):
    bm = bmesh.new()
    build(bm)
    obj = mesh_object(name, bm, col, mat, smooth=smooth)
    parent_to(obj, parent)
    for m in mods:
        m(obj)
    return obj


def point_light(name, col, parent, loc, color, power, radius=0.05):
    ld = bpy.data.lights.new(name, 'POINT')
    ld.color = color
    ld.energy = power
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    col.objects.link(ob)
    parent_to(ob, parent)
    ob.location = loc
    return ob


def spot_light(name, col, parent, loc, direction, color, power, size_deg=100, blend=0.6, radius=0.03):
    ld = bpy.data.lights.new(name, 'SPOT')
    ld.color = color
    ld.energy = power
    ld.spot_size = math.radians(size_deg)
    ld.spot_blend = blend
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    col.objects.link(ob)
    parent_to(ob, parent)
    ob.location = loc
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = Vector(direction).normalized().to_track_quat('-Z', 'Y')
    return ob


def area_light(name, col, parent, loc, direction, color, power, size=0.5):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.color = color
    ld.energy = power
    ld.shape = 'DISK'
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    col.objects.link(ob)
    parent_to(ob, parent)
    ob.location = loc
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = Vector(direction).normalized().to_track_quat('-Z', 'Y')
    return ob


def polar(r, ang, z):
    return Vector((r * math.cos(ang), r * math.sin(ang), z))


def bm_arc_tube(bm, pts, r, segs=8):
    for a, b in zip(pts[:-1], pts[1:]):
        bm_cylinder(bm, a, b, r, segs=segs, caps=False)


# ---------------------------------------------------------------------------
# Observatory
# ---------------------------------------------------------------------------

DRUM_R = 1.70
DRUM_Z0 = 0.12
DRUM_Z1 = 2.36
DOME_R = 1.72
DOME_Z = 2.44
DOOR_W = 0.94
DOOR_H = 1.98


def build_observatory(col, sitee, mats, bh_local):
    lights = collection('Lights_Practical')
    door_ang = math.pi / 2       # local +Y

    # Foundation slab
    part('Obs_Foundation', col, sitee,
         lambda bm: bm_cylinder(bm, (0, 0, -0.45), (0, 0, DRUM_Z0), DRUM_R + 0.32, segs=96),
         mats['concrete'], mods=(lambda o: bevel(o, 0.035, 3),))
    # low step at the door
    part('Obs_Step', col, sitee,
         lambda bm: bm_box(bm, (0, DRUM_R + 0.45, -0.02), (1.2, 0.42, 0.22)),
         mats['concrete'], mods=(lambda o: bevel(o, 0.02, 2),))

    # Drum wall with a door opening
    drum = part('Obs_Drum', col, sitee,
                lambda bm: bm_cylinder(bm, (0, 0, DRUM_Z0), (0, 0, DRUM_Z1), DRUM_R, segs=96, caps=False),
                mats['drum'], smooth=True)
    add_mod(drum, 'SOLIDIFY', thickness=0.07, offset=-1.0, use_even_offset=True)
    cutter = part('Obs_DoorCutter', col, sitee,
                  lambda bm: bm_box(bm, (0, DRUM_R, 0.11 + DOOR_H / 2), (DOOR_W, 0.7, DOOR_H)), None)
    cutter.hide_render = True
    cutter.display_type = 'WIRE'
    boo = add_mod(drum, 'BOOLEAN', operation='DIFFERENCE', object=cutter, solver='EXACT')
    bevel(drum, 0.008, 2, angle=60)

    # Door frame
    def frame(bm):
        y = DRUM_R + 0.01
        zc = 0.11 + DOOR_H / 2
        bm_box(bm, (-DOOR_W / 2 - 0.04, y, zc), (0.08, 0.12, DOOR_H + 0.04))
        bm_box(bm, (DOOR_W / 2 + 0.04, y, zc), (0.08, 0.12, DOOR_H + 0.04))
        bm_box(bm, (0.0, y, 0.11 + DOOR_H + 0.04), (DOOR_W + 0.16, 0.12, 0.09))
    part('Obs_DoorFrame', col, sitee, frame, mats['darkmetal'], mods=(lambda o: bevel(o, 0.012, 2),))

    # Door leaf, swung open ~72 deg around its hinge
    hinge = Vector((DOOR_W / 2 - 0.02, DRUM_R + 0.07, 0.0))
    lw = DOOR_W - 0.06
    leaf = part('Obs_DoorLeaf', col, sitee,
                lambda bm: (bm_box(bm, (-lw / 2, 0.0, 0.12 + DOOR_H / 2), (lw, 0.05, DOOR_H - 0.03)),
                            bm_torus(bm, (-lw / 2, 0.03, 1.5), (0, 1, 0), 0.12, 0.02, 24, 8)),
                mats['drum'], mods=(lambda o: bevel(o, 0.01, 2),))
    leaf.location = hinge
    leaf.rotation_euler = (0, 0, math.radians(-72))
    port = part('Obs_DoorPort', col, sitee,
                lambda bm: bm_cylinder(bm, (-lw / 2, -0.01, 1.5), (-lw / 2, 0.03, 1.5), 0.11, segs=24),
                mats['glass_warm'])
    port.parent = leaf
    port.matrix_parent_inverse = Matrix.Identity(4)

    # Door lamp + spill light
    part('Obs_DoorLampHousing', col, sitee,
         lambda bm: bm_box(bm, (0, DRUM_R + 0.09, DRUM_Z1 - 0.12), (0.26, 0.15, 0.09)),
         mats['darkmetal'], mods=(lambda o: bevel(o, 0.01, 2),))
    part('Obs_DoorLampLens', col, sitee,
         lambda bm: bm_box(bm, (0, DRUM_R + 0.10, DRUM_Z1 - 0.167), (0.22, 0.11, 0.012)),
         mats['lamp_warm'])
    spot_light('Obs_DoorLamp', lights, sitee, (0, DRUM_R + 0.12, DRUM_Z1 - 0.2), (0, 0.55, -1),
               (1.0, 0.72, 0.45), 60.0, size_deg=120, blend=0.8, radius=0.06)

    # Interior: floor, ceiling, console with screens, warm light
    part('Obs_Ceiling', col, sitee,
         lambda bm: bm_cylinder(bm, (0, 0, DRUM_Z1 - 0.04), (0, 0, DRUM_Z1), DRUM_R - 0.02, segs=64),
         mats['interior'])

    def console(bm):
        bm_box(bm, (0.0, -1.05, 0.78), (1.3, 0.55, 0.07))           # desk
        bm_box(bm, (-0.58, -1.05, 0.45), (0.06, 0.5, 0.66))
        bm_box(bm, (0.58, -1.05, 0.45), (0.06, 0.5, 0.66))
        bm_box(bm, (0.0, -1.28, 1.12), (1.3, 0.05, 0.62))           # screen backplate
        bm_box(bm, (-1.05, -0.2, 0.9), (0.35, 0.9, 1.5))            # rack
        bm_box(bm, (0.95, 0.35, 0.55), (0.45, 0.45, 0.9))           # cabinet
        bm_cylinder(bm, (0.2, -0.55, 0.14), (0.2, -0.55, 0.5), 0.03, segs=8)
        bm_cylinder(bm, (0.2, -0.55, 0.5), (0.2, -0.55, 0.55), 0.2, segs=20)
    part('Obs_Console', col, sitee, console, mats['interior_dark'], mods=(lambda o: bevel(o, 0.01, 2),))

    def screens(bm):
        for i, x in enumerate((-0.42, 0.0, 0.42)):
            bm_box(bm, (x, -1.25, 1.14), (0.38, 0.01, 0.26))
    scr = part('Obs_Screens', col, sitee, screens, mats['screen'])
    _box_uvs(scr)
    def rack_leds(bm):
        for i in range(10):
            bm_box(bm, (-0.87, -0.55 + (i % 5) * 0.16, 0.5 + (i // 5) * 0.55), (0.01, 0.03, 0.015))
    part('Obs_RackLEDs', col, sitee, rack_leds, mats['led_green'])
    area_light('Obs_InteriorLight', lights, sitee, (0, 0, DRUM_Z1 - 0.1), (0, 0, -1),
               (1.0, 0.70, 0.46), 55.0, size=1.0)
    point_light('Obs_ScreenGlow', lights, sitee, (0, -0.9, 1.15), (0.35, 0.75, 1.0), 6.0, 0.2)

    # Portholes around the drum
    for k, ang in enumerate((door_ang + math.radians(62), door_ang - math.radians(58),
                             door_ang + math.radians(180))):
        d = polar(1.0, ang, 0.0)
        c = d * (DRUM_R + 0.012) + Vector((0, 0, 1.55))
        part(f'Obs_PortRing_{k}', col, sitee,
             lambda bm, c=c, d=d: bm_torus(bm, c, d, 0.13, 0.022, 32, 8),
             mats['darkmetal'], smooth=True)
        part(f'Obs_PortGlass_{k}', col, sitee,
             lambda bm, c=c, d=d: bm_cylinder(bm, c - d * 0.04, c + d * 0.004, 0.118, segs=32),
             mats['glass_warm'])

    # Utility box + pipes on the drum
    ang = door_ang - math.radians(100)
    d = polar(1.0, ang, 0)
    t = Vector((0, 0, 1)).cross(d)
    rot = Matrix((t, d, (0, 0, 1))).transposed()
    part('Obs_Utility', col, sitee,
         lambda bm: (bm_box(bm, d * (DRUM_R + 0.14) + Vector((0, 0, 0.55)), (0.55, 0.28, 0.6), rot),
                     bm_cylinder(bm, d * (DRUM_R + 0.1) + t * 0.2 + Vector((0, 0, 0.85)),
                                 d * (DRUM_R + 0.1) + t * 0.2 + Vector((0, 0, DRUM_Z1 - 0.04)), 0.03, segs=10),
                     bm_cylinder(bm, d * (DRUM_R + 0.1) - t * 0.18 + Vector((0, 0, 0.85)),
                                 d * (DRUM_R + 0.1) - t * 0.18 + Vector((0, 0, DRUM_Z1 - 0.04)), 0.022, segs=10)),
         mats['drum_dark'], mods=(lambda o: bevel(o, 0.012, 2),))
    part('Obs_UtilityLED', col, sitee,
         lambda bm: bm_box(bm, d * (DRUM_R + 0.285) + t * 0.17 + Vector((0, 0, 0.72)), (0.03, 0.01, 0.03), rot),
         mats['led_amber'])

    # Flange + catwalk + railing
    part('Obs_Flange', col, sitee,
         lambda bm: bm_cylinder(bm, (0, 0, DRUM_Z1 - 0.02), (0, 0, DOME_Z + 0.02), DRUM_R + 0.08, segs=96),
         mats['darkmetal'], mods=(lambda o: bevel(o, 0.012, 2),))

    def catwalk(bm):
        segs = 96
        r0, r1, z0, z1 = DRUM_R + 0.05, DRUM_R + 0.50, DRUM_Z1 - 0.01, DRUM_Z1 + 0.035
        rings = []
        for (r, z) in ((r0, z0), (r1, z0), (r1, z1), (r0, z1)):
            rings.append([bm.verts.new(polar(r, 2 * math.pi * i / segs, z)) for i in range(segs)])
        for k in range(4):
            a, b = rings[k], rings[(k + 1) % 4]
            for i in range(segs):
                j = (i + 1) % segs
                bm.faces.new((a[i], a[j], b[j], b[i]))
    part('Obs_Catwalk', col, sitee, catwalk, mats['grate'])

    rail_r = DRUM_R + 0.46
    ladder_ang = door_ang + math.radians(128)

    def railing(bm):
        zc = DRUM_Z1 + 0.035
        for i in range(18):
            a = 2 * math.pi * i / 18
            if abs(((a - ladder_ang + math.pi) % (2 * math.pi)) - math.pi) < math.radians(9):
                continue
            bm_cylinder(bm, polar(rail_r, a, zc), polar(rail_r, a, zc + 0.9), 0.016, segs=6)
        bm_torus(bm, (0, 0, zc + 0.9), (0, 0, 1), rail_r, 0.02, 96, 6)
        bm_torus(bm, (0, 0, zc + 0.47), (0, 0, 1), rail_r, 0.013, 96, 6)
        bm_torus(bm, (0, 0, zc + 0.08), (0, 0, 1), rail_r, 0.01, 96, 6)
    part('Obs_Railing', col, sitee, railing, mats['steel'], smooth=True)

    def ladder(bm):
        d = polar(1.0, ladder_ang, 0)
        t = Vector((0, 0, 1)).cross(d)
        top = d * (DRUM_R + 0.52) + Vector((0, 0, DRUM_Z1 + 0.05))
        bot = d * (DRUM_R + 0.95) + Vector((0, 0, -0.05))
        for s in (-0.22, 0.22):
            bm_cylinder(bm, bot + t * s, top + t * s + Vector((0, 0, 0.85)) + d * -0.02, 0.02, segs=8)
        n = 7
        for i in range(1, n):
            p = bot.lerp(top, i / n)
            bm_cylinder(bm, p - t * 0.22, p + t * 0.22, 0.014, segs=6)
    part('Obs_Ladder', col, sitee, ladder, mats['steel'], smooth=True)

    # Dome (rotated to face the hole), slit cut by boolean
    az = math.atan2(bh_local.y, bh_local.x) - math.pi / 2
    dome_root = empty('Obs_DomeRoot', col, size=0.4)
    parent_to(dome_root, sitee)
    dome_root.location = (0, 0, DOME_Z)
    dome_root.rotation_euler = (0, 0, az)

    def dome(bm):
        segs, rings = 96, 28
        verts = []
        for j in range(rings + 1):
            lat = (math.pi / 2) * j / rings
            row = []
            for i in range(segs):
                a = 2 * math.pi * i / segs
                if j == rings:
                    row = [bm.verts.new((0, 0, DOME_R))]
                    break
                row.append(bm.verts.new(polar(DOME_R * math.cos(lat), a, DOME_R * math.sin(lat))))
            verts.append(row)
        for j in range(rings):
            a, b = verts[j], verts[j + 1]
            for i in range(segs):
                i2 = (i + 1) % segs
                if len(b) == 1:
                    bm.faces.new((a[i], a[i2], b[0]))
                else:
                    bm.faces.new((a[i], a[i2], b[i2], b[i]))
    dm = part('Obs_Dome', col, dome_root, dome, mats['dome'], smooth=True)
    add_mod(dm, 'SOLIDIFY', thickness=0.05, offset=-1.0, use_even_offset=True)
    slit_w = 0.66
    sc = part('Obs_SlitCutter', col, dome_root,
              lambda bm: bm_box(bm, (0, 1.1, 1.1), (slit_w, 2.8, 1.7)), None)
    sc.hide_render = True
    sc.display_type = 'WIRE'
    add_mod(dm, 'BOOLEAN', operation='DIFFERENCE', object=sc, solver='EXACT')
    bevel(dm, 0.006, 2, angle=50)

    # slit lips (arched trims) and the slid-back shutter
    def lips(bm):
        for sx in (-1, 1):
            x = sx * (slit_w / 2 + 0.03)
            rr = math.sqrt(max(DOME_R ** 2 - x ** 2, 0.01)) + 0.02
            pts = []
            for k in range(25):
                th = math.radians(8 + (180 - 16) * k / 24)
                pts.append(Vector((x, rr * math.cos(th), rr * math.sin(th))))
            bm_arc_tube(bm, pts, 0.028, segs=8)
    part('Obs_SlitLips', col, dome_root, lips, mats['darkmetal'], smooth=True)

    def shutter(bm):
        rr = DOME_R + 0.05
        rows = []
        for k in range(21):
            th = math.radians(95 + 70 * k / 20)
            row = []
            for x in (-slit_w / 2 - 0.02, slit_w / 2 + 0.02):
                rxy = math.sqrt(max(rr ** 2 - x ** 2, 0.01))
                row.append(bm.verts.new(Vector((x, rxy * math.cos(th), rxy * math.sin(th)))))
            rows.append(row)
        for a, b in zip(rows[:-1], rows[1:]):
            bm.faces.new((a[0], a[1], b[1], b[0]))
    sh = part('Obs_Shutter', col, dome_root, shutter, mats['dome'], smooth=True)
    add_mod(sh, 'SOLIDIFY', thickness=0.035, offset=0.0)
    bevel(sh, 0.006, 2, angle=50)

    part('Obs_DomeRing', col, dome_root,
         lambda bm: bm_torus(bm, (0, 0, 0.02), (0, 0, 1), DOME_R + 0.02, 0.04, 96, 8),
         mats['darkmetal'], smooth=True)

    # Telescope aimed at the hole
    aim = bh_local.normalized()
    piv = Vector((0, 0, DOME_Z + 0.62))

    def scope(bm):
        bm_cylinder(bm, (0, 0, DRUM_Z1), (0, 0, DOME_Z + 0.35), 0.16, 0.12, segs=24)       # pier
        side = aim.cross(Vector((0, 0, 1))).normalized()
        base = Vector((0, 0, DOME_Z + 0.35))
        for s in (-1, 1):                                                              # fork
            bm_cylinder(bm, base + side * 0.28 * s, piv + side * 0.30 * s, 0.05, segs=10)
        bm_cylinder(bm, base - side * 0.3, base + side * 0.3, 0.07, segs=12)
    part('Obs_TelescopeMount', col, sitee, scope, mats['darkmetal'], smooth=True,
         mods=(lambda o: bevel(o, 0.01, 2),))
    part('Obs_TelescopeTube', col, sitee,
         lambda bm: bm_cylinder(bm, piv - aim * 0.85, piv + aim * 1.15, 0.23, segs=40),
         mats['scope_white'], smooth=True, mods=(lambda o: bevel(o, 0.01, 2, angle=60),))
    part('Obs_TelescopeRings', col, sitee,
         lambda bm: (bm_cylinder(bm, piv + aim * 0.95, piv + aim * 1.30, 0.25, segs=40),
                     bm_cylinder(bm, piv - aim * 0.9, piv - aim * 0.7, 0.245, segs=40),
                     bm_cylinder(bm, piv - aim * 0.1, piv + aim * 0.1, 0.25, segs=40),
                     bm_cylinder(bm, piv + aim * 0.2 + Vector((0, 0, 0.26)), piv + aim * 0.9 + Vector((0, 0, 0.26)), 0.05, segs=16)),
         mats['darkmetal'], smooth=True)
    part('Obs_TelescopeGlass', col, sitee,
         lambda bm: bm_cylinder(bm, piv + aim * 1.05, piv + aim * 1.06, 0.215, segs=40),
         mats['lens'])
    # dim red observing light inside the dome
    point_light('Obs_DomeRedLight', lights, sitee, (0, 0, DOME_Z + 0.9), (1.0, 0.05, 0.02), 22.0, 0.3)

    return dict(slit_dir=aim)


def _box_uvs(obj):
    """Planar UVs per face (0..1) so screen shaders have coordinates."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    uv = me.uv_layers.active.data
    for poly in me.polygons:
        vs = [me.vertices[me.loops[li].vertex_index].co for li in poly.loop_indices]
        n = poly.normal
        ax = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((0, 1, 0))
        t = ax.cross(n).normalized()
        b = n.cross(t)
        us = [v.dot(t) for v in vs]
        ws = [v.dot(b) for v in vs]
        u0, u1, w0, w1 = min(us), max(us), min(ws), max(ws)
        for li, u_, w_ in zip(poly.loop_indices, us, ws):
            uv[li].uv = ((u_ - u0) / max(u1 - u0, 1e-6), (w_ - w0) / max(w1 - w0, 1e-6))


# ---------------------------------------------------------------------------
# Radio mast
# ---------------------------------------------------------------------------

def build_mast(col, sitee, mats, bh_local):
    H = 5.9
    lights = collection('Lights_Practical')
    part('Mast_Base', col, sitee,
         lambda bm: bm_box(bm, (0, 0, -0.1), (0.9, 0.9, 0.34)),
         mats['concrete'], mods=(lambda o: bevel(o, 0.02, 2),))

    def lattice(bm):
        levels = 14
        def leg(i, z):
            r = 0.24 - 0.11 * (z / H)
            a = math.radians(90 + 120 * i)
            return Vector((r * math.cos(a), r * math.sin(a), z))
        for i in range(3):
            bm_cylinder(bm, leg(i, 0.1), leg(i, H), 0.022, 0.016, segs=8)
        for k in range(levels):
            z0 = 0.1 + (H - 0.1) * k / levels
            z1 = 0.1 + (H - 0.1) * (k + 1) / levels
            for i in range(3):
                j = (i + 1) % 3
                bm_cylinder(bm, leg(i, z1), leg(j, z1), 0.011, segs=6)
                if k % 2 == 0:
                    bm_cylinder(bm, leg(i, z0), leg(j, z1), 0.009, segs=6)
                else:
                    bm_cylinder(bm, leg(j, z0), leg(i, z1), 0.009, segs=6)
    part('Mast_Lattice', col, sitee, lattice, mats['mast'], smooth=True)

    # top hardware: whip, panel antennas, yagi aimed at the hole
    def hardware(bm):
        bm_cylinder(bm, (0, 0, H), (0, 0, H + 1.6), 0.012, 0.005, segs=8)
        for a in (0, 120, 240):
            d = polar(1.0, math.radians(a + 30), 0)
            t = Vector((0, 0, 1)).cross(d)
            rot = Matrix((t, d, (0, 0, 1))).transposed()
            bm_box(bm, d * 0.2 + Vector((0, 0, H - 0.8)), (0.16, 0.06, 0.62), rot)
        aimh = Vector((bh_local.x, bh_local.y, max(bh_local.z, 0.05))).normalized()
        c = Vector((0, 0, H - 1.6))
        bm_cylinder(bm, c, c + aimh * 1.3, 0.01, segs=6)
        side = aimh.cross(Vector((0, 0, 1))).normalized()
        for k in range(7):
            p = c + aimh * (0.1 + 0.19 * k)
            half = 0.26 - 0.022 * k
            bm_cylinder(bm, p - side * half, p + side * half, 0.005, segs=5)
    part('Mast_Hardware', col, sitee, hardware, mats['steel'], smooth=True)

    # Beacons (blink)
    bmat = mats['beacon']
    for k, z in enumerate((H + 0.05, 3.0)):
        part(f'Mast_Beacon_{k}', col, sitee,
             lambda bm, z=z: bm_torus(bm, (0, 0, z), (0, 0, 1), 0.035, 0.035, 16, 10),
             bmat, smooth=True)
        pl = point_light(f'Mast_BeaconLight_{k}', lights, sitee, (0, 0, z + 0.1),
                         (1.0, 0.08, 0.04), 0.0, 0.04)
        M.animate_blink(pl.data, 'energy', 60.0 if k == 0 else 25.0, 0.0, 36, phase=k * 18, pulse_frames=7)
    em = bmat.node_tree.nodes[bmat['emission_node']]
    M.animate_blink(em.inputs['Strength'], 'default_value', 60.0, 0.6, 36, phase=0, pulse_frames=7)

    # Guy wires
    def guys(bm):
        for a in (30, 150, 270):
            d = polar(1.0, math.radians(a), 0)
            top = d * 0.13 + Vector((0, 0, 4.1))
            anchor = d * 2.6 + Vector((0, 0, -0.35))
            bm_cylinder(bm, top, anchor, 0.0045, segs=5, caps=False)
            bm_box(bm, anchor + Vector((0, 0, 0.05)), (0.14, 0.14, 0.14))
    part('Mast_Guys', col, sitee, guys, mats['steel'])


# ---------------------------------------------------------------------------
# Dish
# ---------------------------------------------------------------------------

def build_dish(col, sitee, mats, aim_local):
    part('Dish_Base', col, sitee,
         lambda bm: (bm_box(bm, (0, 0, -0.08), (0.9, 0.9, 0.3)),
                     bm_cylinder(bm, (0, 0, 0.05), (0, 0, 1.0), 0.16, 0.13, segs=24)),
         mats['drum'], smooth=False, mods=(lambda o: bevel(o, 0.015, 2),))
    root = empty('Dish_Root', col, size=0.4)
    parent_to(root, sitee)
    root.location = (0, 0, 1.12)
    root.rotation_mode = 'QUATERNION'
    root.rotation_quaternion = Vector(aim_local).normalized().to_track_quat('Z', 'Y')

    Rd, f = 1.15, 0.62

    def bowl(bm):
        rings, segs = 22, 72
        verts = [[bm.verts.new((0, 0, 0))]]
        for j in range(1, rings + 1):
            r = Rd * j / rings
            verts.append([bm.verts.new(polar(r, 2 * math.pi * i / segs, r * r / (4 * f))) for i in range(segs)])
        for i in range(segs):
            bm.faces.new((verts[0][0], verts[1][i], verts[1][(i + 1) % segs]))
        for j in range(1, rings):
            a, b = verts[j], verts[j + 1]
            for i in range(segs):
                i2 = (i + 1) % segs
                bm.faces.new((a[i], b[i], b[i2], a[i2]))
    dish = part('Dish_Bowl', col, root, bowl, mats['dish'], smooth=True)
    add_mod(dish, 'SOLIDIFY', thickness=0.03, offset=-1.0)
    rim_z = Rd * Rd / (4 * f)

    def struts(bm):
        bm_torus(bm, (0, 0, rim_z), (0, 0, 1), Rd, 0.025, 72, 8)
        feed = Vector((0, 0, f))
        for a in (45, 135, 225, 315):
            p = polar(Rd * 0.92, math.radians(a), rim_z * 0.85)
            bm_cylinder(bm, p, feed + Vector((0, 0, -0.05)), 0.014, segs=6)
        bm_cylinder(bm, feed - Vector((0, 0, 0.12)), feed + Vector((0, 0, 0.06)), 0.07, 0.045, segs=16)
        # back truss
        for a in range(0, 360, 45):
            p = polar(Rd * 0.85, math.radians(a), (Rd * 0.85) ** 2 / (4 * f) - 0.05)
            bm_cylinder(bm, (0, 0, -0.18), p, 0.016, segs=6)
        bm_cylinder(bm, (0, 0, -0.35), (0, 0, 0.0), 0.12, segs=16)
    part('Dish_Struts', col, root, struts, mats['steel'], smooth=True)
    part('Dish_FeedTip', col, root,
         lambda bm: bm_cylinder(bm, (0, 0, f - 0.13), (0, 0, f - 0.12), 0.05, segs=16),
         mats['led_amber'])

    # yoke from pedestal to dish back (in site space)
    def yoke(bm):
        bm_box(bm, (0, 0, 1.05), (0.5, 0.25, 0.14))
        for s in (-0.22, 0.22):
            bm_box(bm, (s, 0, 1.16), (0.06, 0.2, 0.28))
    part('Dish_Yoke', col, sitee, yoke, mats['drum_dark'], mods=(lambda o: bevel(o, 0.01, 2),))


# ---------------------------------------------------------------------------
# Solar array, crates, lamps, cables
# ---------------------------------------------------------------------------

def build_solar(col, sitee, mats):
    def frame(bm):
        for i in range(3):
            x = (i - 1) * 1.12
            bm_cylinder(bm, (x, 0.0, -0.15), (x, 0.0, 0.62), 0.03, segs=8)
        bm_cylinder(bm, (-1.4, 0, 0.62), (1.4, 0, 0.62), 0.028, segs=8)
    part('Solar_Frame', col, sitee, frame, mats['steel'], smooth=True)
    tilt = Matrix.Rotation(math.radians(-38), 3, 'X')
    for i in range(3):
        x = (i - 1) * 1.12
        def panel(bm, x=x):
            bm_box(bm, (0, 0, 0), (1.05, 0.66, 0.025))
        p = part(f'Solar_Panel_{i}', col, sitee, panel, mats['solar'])
        _box_uvs(p)
        p.location = (x, 0.0, 0.66)
        p.rotation_euler = (math.radians(-38), 0, 0)
        fr = part(f'Solar_PanelFrame_{i}', col, sitee,
                  lambda bm: (bm_box(bm, (0, 0.335, 0), (1.07, 0.02, 0.035)),
                              bm_box(bm, (0, -0.335, 0), (1.07, 0.02, 0.035)),
                              bm_box(bm, (0.53, 0, 0), (0.02, 0.69, 0.035)),
                              bm_box(bm, (-0.53, 0, 0), (0.02, 0.69, 0.035))),
                  mats['steel'])
        fr.location = p.location
        fr.rotation_euler = p.rotation_euler


def build_crates(col, sitee, mats):
    specs = [((0, 0, 0.26), (0.7, 0.55, 0.55), 12, 'crate_a'),
             ((0.72, 0.1, 0.22), (0.55, 0.5, 0.46), -9, 'crate_b'),
             ((0.2, 0.05, 0.78), (0.5, 0.42, 0.44), 20, 'crate_a'),
             ((-0.6, 0.55, 0.14), (0.3, 0.3, 0.3), 35, 'crate_b')]
    for k, (c, s, rz, m) in enumerate(specs):
        o = part(f'Crate_{k}', col, sitee, lambda bm, s=s: bm_box(bm, (0, 0, 0), s), mats[m],
                 mods=(lambda o: bevel(o, 0.025, 3),))
        o.location = (c[0], c[1], c[2] - 0.12)
        o.rotation_euler = (0, 0, math.radians(rz))


def build_lamp(col, sitee, mats, name):
    lights = collection('Lights_Practical')
    part(f'{name}_Post', col, sitee,
         lambda bm: (bm_cylinder(bm, (0, 0, -0.2), (0, 0, 0.52), 0.032, 0.026, segs=12),
                     bm_cylinder(bm, (0, 0, 0.52), (0, 0, 0.60), 0.075, 0.06, segs=16),
                     bm_cylinder(bm, (0, 0, -0.2), (0, 0, 0.02), 0.07, segs=12)),
         mats['darkmetal'], smooth=True, mods=(lambda o: bevel(o, 0.006, 2, angle=60),))
    part(f'{name}_Lens', col, sitee,
         lambda bm: bm_cylinder(bm, (0, 0, 0.488), (0, 0, 0.522), 0.062, segs=16),
         mats['lamp_warm'], smooth=True)
    point_light(f'{name}_Light', lights, sitee, (0, 0, 0.47), (1.0, 0.66, 0.38), 14.0, 0.04)


def build_cable(col, ground, pa, pb, mat, name, seed=0, lift=0.018):
    rnd = random.Random(seed)
    da, db = Vector(pa).normalized(), Vector(pb).normalized()
    n = 48
    pts = []
    side = da.cross(db).normalized()
    ph = rnd.uniform(0, 6.28)
    for i in range(n + 1):
        t = i / n
        d = da.slerp(db, t) if da.dot(db) < 0.9999 else da
        wob = math.sin(t * math.pi * 3 + ph) * 0.12 * math.sin(t * math.pi)
        d = (d + side * wob / L.R).normalized()
        loc, nrm = ground.hit(d)
        pts.append(loc + d * lift)
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 0.016
    cu.bevel_resolution = 3
    sp = cu.splines.new('NURBS')
    sp.points.add(len(pts) - 1)
    for p, co in zip(sp.points, pts):
        p.co = (*co, 1.0)
    sp.use_endpoint_u = True
    sp.order_u = 4
    ob = bpy.data.objects.new(name, cu)
    col.objects.link(ob)
    cu.materials.append(mat)
    return ob


# ---------------------------------------------------------------------------

def make_materials():
    return dict(
        concrete=M.concrete(),
        drum=M.painted_panels('DrumPanels', (0.56, 0.545, 0.51), mode='CYL', pv=0.53, rough=0.5, wear=0.45),
        drum_dark=M.painted_panels('DarkPanels', (0.13, 0.135, 0.14), mode='BOX', pv=0.3, rough=0.45, wear=0.3),
        dome=M.painted_panels('DomePanels', (0.74, 0.735, 0.715), mode='SPH', pu=2 * math.pi * 1.5 / 24,
                              pv=0.42, rough=0.34, dust_bottom=0.0, wear=0.25),
        interior=M.plastic('InteriorPaint', (0.42, 0.38, 0.33), rough=0.6),
        interior_dark=M.plastic('InteriorDark', (0.06, 0.062, 0.068), rough=0.4),
        darkmetal=M.metal('DarkMetal', (0.07, 0.072, 0.078), rough=0.38, dirt=0.2),
        steel=M.metal('Steel', (0.5, 0.51, 0.53), rough=0.3),
        grate=M.metal('Grate', (0.16, 0.16, 0.17), rough=0.55, dirt=0.5),
        scope_white=M.plastic('ScopeWhite', (0.78, 0.78, 0.76), rough=0.25),
        lens=M.metal('Lens', (0.02, 0.025, 0.04), rough=0.05),
        glass_warm=M.glass_glow('WindowWarm', (1.0, 0.62, 0.30), 7.0),
        lamp_warm=M.glass_glow('LampWarm', (1.0, 0.70, 0.42), 30.0),
        screen=M.screen('ConsoleScreen'),
        led_green=M.glow('LEDGreen', (0.2, 1.0, 0.35), 12.0),
        led_amber=M.glow('LEDAmber', (1.0, 0.5, 0.1), 15.0),
        beacon=M.glow('BeaconRed', (1.0, 0.06, 0.03), 60.0),
        mast=M.striped_mast(),
        dish=M.dish_paint(),
        solar=M.solar_cells(),
        crate_a=M.hazard_crate('CrateOrange', (0.55, 0.20, 0.04)),
        crate_b=M.hazard_crate('CrateGray', (0.22, 0.23, 0.22)),
        rubber=M.rubber(),
        stencil=M.plastic('Stencil', (0.03, 0.03, 0.03), rough=0.6),
    )


def build_props(scene, ground, sites):
    col = collection('Observatory')
    mats = make_materials()

    def to_local(sitee, v):
        return sitee.matrix_world.to_3x3().inverted() @ Vector(v)

    # observatory
    loc, _ = ground.hit(sites['obs_up'])
    obs = site('Site_Observatory', col, loc, sites['obs_up'], sites['door_dir'])
    build_observatory(col, obs, mats, to_local(obs, L.BH_DIR))

    # mast
    mcol = collection('Antenna')
    loc, _ = ground.hit(L.MAST_DIR)
    mast = site('Site_Mast', mcol, loc, L.MAST_DIR, L.F_C)
    build_mast(mcol, mast, mats, to_local(mast, L.BH_DIR))

    # dish: points up-and-over towards the hole's azimuth
    loc, _ = ground.hit(L.DISH_DIR)
    dsite = site('Site_Dish', mcol, loc, L.DISH_DIR, L.BH_DIR)
    aim = to_local(dsite, (L.DISH_DIR * 0.75 + L.BH_DIR * 0.66).normalized())
    build_dish(mcol, dsite, mats, aim)

    # solar array
    loc, _ = ground.hit(L.SOLAR_DIR)
    ssite = site('Site_Solar', mcol, loc, L.SOLAR_DIR, -L.F_C + L.R_C * 0.3)
    build_solar(mcol, ssite, mats)

    # crates
    loc, _ = ground.hit(L.CRATE_DIR)
    csite = site('Site_Crates', col, loc, L.CRATE_DIR, L.F_C)
    build_crates(col, csite, mats)

    # path lights along the walkway
    lcol = collection('PathLights')
    wa, wb = Vector(sites['walk_a']), Vector(sites['walk_b'])
    for k, t in enumerate((0.12, 0.38, 0.64, 0.86)):
        p = wa.lerp(wb, t)
        up = p.normalized()
        side = (wb - wa).cross(up).normalized()
        d = (p + side * (0.62 if k % 2 == 0 else -0.62)).normalized()
        loc, _ = ground.hit(d)
        s = site(f'Site_Lamp_{k}', lcol, loc, d, wb - wa)
        build_lamp(lcol, s, mats, f'Lamp_{k}')

    # cables from the observatory to the mast and the dish
    ccol = collection('Cables')
    obs_side_mast = (obs.matrix_world @ Vector((-1.9, 0.3, 0))).normalized()
    obs_side_dish = (obs.matrix_world @ Vector((-1.2, 1.5, 0))).normalized()
    build_cable(ccol, ground, obs_side_mast, (mast.matrix_world @ Vector((0, 0.5, 0))), mats['rubber'], 'Cable_Mast', 1)
    build_cable(ccol, ground, obs_side_dish, (dsite.matrix_world @ Vector((0, 0.5, 0))), mats['rubber'], 'Cable_Dish', 2)
    build_cable(ccol, ground, (dsite.matrix_world @ Vector((0.3, 0.4, 0))),
                (ssite.matrix_world @ Vector((-1.2, 0.3, 0))), mats['rubber'], 'Cable_Solar', 3)
    return dict(observatory=obs, mast=mast, dish=dsite)
