"""The astronaut: metaball EVA suit + hard-shell helmet, backpack, details.

Local frame: +Z up, +Y facing (towards the black hole), +X to the right.
"""

import math

import bpy
import bmesh
from mathutils import Vector, Matrix, Quaternion

from . import layout as L
from . import materials as M
from .util import (collection, mesh_object, empty, place_on, add_mod, bevel, subsurf,
                   bm_cylinder, bm_box, bm_torus, new_material, principled, emission)
from .props import parent_to, part


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def suit_fabric(joints=()):
    mat, nb, out = new_material('SuitFabric')
    oc = nb.node('ShaderNodeTexCoord').outputs['Object']
    x, y, z = nb.separate(oc)
    # soft pillowed wrinkles + woven Beta-cloth texture
    wr = nb.noise(nb.vmath('MULTIPLY', oc, (1.0, 1.0, 2.6)), scale=16.0, detail=4.0, rough=0.55, dist=0.4)
    weave_a = nb.node('ShaderNodeTexWave', {'Vector': oc, 'Scale': 260.0, 'Distortion': 0.0}, wave_type='BANDS',
                      bands_direction='X')
    weave_b = nb.node('ShaderNodeTexWave', {'Vector': oc, 'Scale': 260.0, 'Distortion': 0.0}, wave_type='BANDS',
                      bands_direction='Z')
    weave = nb.mul(weave_a.outputs['Fac'], weave_b.outputs['Fac'])
    grime = nb.noise(oc, scale=9.0, detail=8.0, rough=0.6)
    base = nb.mix(nb.mul(nb.smoothstep(0.5, 0.8, grime.outputs['Factor']), 0.35),
                  (0.70, 0.69, 0.655), (0.48, 0.46, 0.43))
    # regolith dust climbing the legs
    low = nb.sub(1.0, nb.smoothstep(0.15, 0.62, z))
    dn = nb.noise(oc, scale=14.0, detail=6.0, rough=0.7)
    dust = nb.mul(low, nb.smoothstep(0.35, 0.65, dn.outputs['Factor']))
    base = nb.mix(nb.mul(dust, 0.85), base, (0.23, 0.205, 0.18))
    h = nb.add(nb.mul(wr.outputs['Factor'], 1.0), nb.mul(weave, 0.12))
    # accordion pleats around knees and elbows
    for j, reach in joints:
        dj = nb.vmath('DISTANCE', oc, tuple(j))
        ring = nb.math('SINE', nb.mul(dj, 2 * math.pi / 0.028))
        fall = nb.sub(1.0, nb.smoothstep(reach * 0.35, reach, dj))
        h = nb.add(h, nb.mul(nb.mul(ring, fall), 0.9))
    bump = nb.node('ShaderNodeBump', {'Height': h, 'Strength': 0.35, 'Distance': 0.006})
    bsdf = principled(nb, base=base, rough=0.82, sheen=0.45, sheen_tint=(0.9, 0.9, 1.0), normal=bump, spec=0.3)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def visor_gold():
    mat, nb, out = new_material('VisorGold')
    lw = nb.node('ShaderNodeLayerWeight', {'Blend': 0.35})
    base = nb.mix(lw.outputs['Facing'], (1.0, 0.70, 0.30), (1.0, 0.86, 0.62))
    n = nb.noise(nb.node('ShaderNodeTexCoord').outputs['Object'], scale=30.0, detail=3.0)
    r = nb.maprange(n.outputs['Factor'], 0.3, 0.7, 0.025, 0.06)
    bsdf = principled(nb, base=base, metal=1.0, rough=r, coat=0.6, coat_rough=0.02,
                      thin_film=120.0)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def hard_shell(name, color, rough=0.32):
    mat, nb, out = new_material(name)
    oc = nb.node('ShaderNodeTexCoord').outputs['Object']
    n = nb.noise(oc, scale=11.0, detail=8.0, rough=0.6)
    sc = nb.noise(nb.vmath('MULTIPLY', oc, (30.0, 30.0, 2.0)), scale=5.0, detail=2.0)
    base = nb.mix(nb.mul(nb.smoothstep(0.58, 0.8, n.outputs['Factor']), 0.3), color,
                  nb.vmath('MULTIPLY', color, (0.62, 0.6, 0.57)))
    r = nb.add(nb.maprange(n.outputs['Factor'], 0.3, 0.7, rough - 0.06, rough + 0.1),
               nb.mul(nb.smoothstep(0.62, 0.7, sc.outputs['Factor']), 0.2))
    bsdf = principled(nb, base=base, rough=r, coat=0.35, coat_rough=0.1, spec=0.5)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _mb_capsule(mb, p0, p1, r, stiff=2.0):
    p0, p1 = Vector(p0), Vector(p1)
    el = mb.elements.new(type='CAPSULE')
    el.co = (p0 + p1) * 0.5
    d = p1 - p0
    el.size_x = d.length * 0.5
    el.radius = r
    el.stiffness = stiff
    el.rotation = Vector((1, 0, 0)).rotation_difference(d.normalized())
    return el


def _mb_ellipsoid(mb, c, size, r=1.0, stiff=2.0, rot=None):
    el = mb.elements.new(type='ELLIPSOID')
    el.co = c
    el.size_x, el.size_y, el.size_z = size
    el.radius = r
    el.stiffness = stiff
    if rot is not None:
        el.rotation = rot
    return el


def _mb_ball(mb, c, r, stiff=2.0):
    el = mb.elements.new(type='BALL')
    el.co = c
    el.radius = r
    el.stiffness = stiff
    return el


def bm_ellipsoid(bm, c, size, rot=None, segs=24, rings=14):
    c = Vector(c)
    rot = rot or Matrix.Identity(3)
    rows = []
    for j in range(rings + 1):
        lat = -math.pi / 2 + math.pi * j / rings
        row = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            v = Vector((math.cos(lat) * math.cos(a) * size[0],
                        math.cos(lat) * math.sin(a) * size[1],
                        math.sin(lat) * size[2]))
            row.append(bm.verts.new(c + rot @ v))
        rows.append(row)
    for j in range(rings):
        for i in range(segs):
            i2 = (i + 1) % segs
            bm.faces.new((rows[j][i], rows[j][i2], rows[j + 1][i2], rows[j + 1][i]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)


def bm_sphere_patch(bm, c, r, az_half, el_lo, el_hi, segs=48, rings=28, keep=None):
    """Patch of a sphere around +Y. keep(az, el) -> bool can punch holes."""
    c = Vector(c)
    grid = []
    for j in range(rings + 1):
        el = el_lo + (el_hi - el_lo) * j / rings
        row = []
        for i in range(segs + 1):
            az = -az_half + 2 * az_half * i / segs
            v = Vector((math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el))) * r
            row.append(bm.verts.new(c + v))
        grid.append(row)
    for j in range(rings):
        for i in range(segs):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

HELMET_C = Vector((0.0, 0.04, 1.70))
HS = 1.10   # helmet scale


def build_astronaut(scene, ground, sites):
    col = collection('Astronaut')
    loc, _ = ground.hit(L.AST_DIR)
    root = empty('Astronaut', col, size=0.5, kind='ARROWS')
    place_on(root, loc, L.AST_DIR, L.BH_DIR)
    # seat the figure: soles rest on the higher of the two boot contact areas
    mw = root.matrix_world.copy()
    lift = []
    for off in ((-0.145, 0.2, 0), (-0.145, -0.08, 0), (0.16, 0.12, 0), (0.16, -0.18, 0)):
        wp = mw @ Vector(off)
        g, _ = ground.hit(wp.normalized())
        lift.append((g - wp).dot(L.AST_DIR))
    place_on(root, loc + L.AST_DIR * (max(lift) - 0.012), L.AST_DIR, L.BH_DIR)

    shell = hard_shell('SuitHardShell', (0.80, 0.80, 0.78), rough=0.42)
    gold = visor_gold()
    glove = M.plastic('GloveRubber', (0.20, 0.21, 0.23), rough=0.55)
    boot = hard_shell('BootShell', (0.55, 0.55, 0.53), rough=0.55)
    sole = M.plastic('BootSole', (0.03, 0.03, 0.03), rough=0.8)
    ring_blue = M.metal('RingBlue', (0.10, 0.24, 0.62), rough=0.25, dirt=0.1)
    ring_red = M.metal('RingRed', (0.45, 0.09, 0.05), rough=0.35, dirt=0.2)
    band_red = M.plastic('CommanderStripe', (0.50, 0.045, 0.03), rough=0.7)
    dcm = M.plastic('DCMGray', (0.09, 0.095, 0.1), rough=0.4)
    led_g = M.glow('SuitLEDGreen', (0.25, 1.0, 0.4), 20.0)
    led_r = M.glow('SuitLEDRed', (1.0, 0.15, 0.08), 20.0)
    lamp = M.glass_glow('HelmetLamp', (0.85, 0.92, 1.0), 6.0)
    tablet_scr = M.screen('TabletScreen', (0.3, 0.85, 1.0), 2.5)
    hose_mat = M.plastic('Hose', (0.55, 0.56, 0.58), rough=0.4)

    # Soft suit body: metaballs blend into a pillowy EVA suit.
    mb = bpy.data.metaballs.new('SuitBody')
    mb.resolution = 0.03
    mb.render_resolution = 0.011
    mb.threshold = 0.6
    LH, LK, LA = Vector((-0.12, 0.02, 0.95)), Vector((-0.14, 0.085, 0.54)), Vector((-0.145, 0.06, 0.19))
    RH, RK, RA = Vector((0.12, -0.01, 0.95)), Vector((0.145, -0.03, 0.54)), Vector((0.16, -0.075, 0.19))
    LS, LE, LW = Vector((-0.29, -0.01, 1.40)), Vector((-0.35, 0.03, 1.12)), Vector((-0.335, 0.12, 0.90))
    RS, RE, RW = Vector((0.29, -0.01, 1.40)), Vector((0.37, 0.07, 1.14)), Vector((0.27, 0.31, 1.03))
    # Blender's metaball surface sits at r*sqrt(1-(t/s)^(1/3)) ~ 0.575 r for
    # threshold 0.6 / stiffness 2, so element radii are scaled up to match.
    k = 1.72
    ke = 1.72 * 0.93
    # legs (left slightly forward, right carrying weight)
    for a, b, r in ((LH, LK, 0.112), (LK, LA, 0.098), (RH, RK, 0.112), (RK, RA, 0.098)):
        _mb_capsule(mb, a, b, r * k)
    _mb_ball(mb, LK, 0.104 * k)
    _mb_ball(mb, RK, 0.104 * k)
    # pelvis / torso / chest
    _mb_ellipsoid(mb, (0, 0.0, 0.99), (0.215, 0.165, 0.13), r=ke)
    _mb_ellipsoid(mb, (0, -0.01, 1.21), (0.24, 0.175, 0.25), r=ke)
    _mb_ellipsoid(mb, (0, 0.005, 1.37), (0.265, 0.185, 0.14), r=ke)
    # shoulders + arms
    _mb_ball(mb, LS, 0.118 * k)
    _mb_ball(mb, RS, 0.118 * k)
    for a, b, r in ((LS, LE, 0.088), (LE, LW, 0.078), (RS, RE, 0.088), (RE, RW, 0.078)):
        _mb_capsule(mb, a, b, r * k)
    _mb_ball(mb, LE, 0.084 * k)
    _mb_ball(mb, RE, 0.084 * k)
    _mb_ball(mb, (0, 0.01, 1.50), 0.115 * k)
    fabric = suit_fabric(((LK, 0.13), (RK, 0.13), (LE, 0.10), (RE, 0.10)))
    body = bpy.data.objects.new('SuitBody', mb)
    col.objects.link(body)
    mb.materials.append(fabric)
    parent_to(body, root)

    # Joint rings / wrist rings / stripe
    def ring_between(bm, p0, p1, t, R, r):
        p = Vector(p0).lerp(Vector(p1), t)
        bm_torus(bm, p, Vector(p1) - Vector(p0), R, r, 32, 8)
    part('Suit_WristRings', col, root,
         lambda bm: (ring_between(bm, LE, LW, 0.95, 0.072, 0.022), ring_between(bm, RE, RW, 0.95, 0.072, 0.022)),
         ring_red, smooth=True)
    def stripes(bm):
        for S, E in ((RS, RE), (LS, LE)):
            d = (E - S).normalized()
            p = S.lerp(E, 0.52)
            bm_cylinder(bm, p - d * 0.045, p + d * 0.045, 0.1, segs=32, caps=False)
    st = part('Suit_Stripe', col, root, stripes, band_red, smooth=True)
    add_mod(st, 'SOLIDIFY', thickness=0.006, offset=1.0)
    part('Suit_NeckRing', col, root,
         lambda bm: bm_torus(bm, (0, 0.025, 1.53), (0, 0.08, 1), 0.158, 0.024, 48, 10),
         ring_blue, smooth=True)

    # Gloves
    def gloves(bm):
        for E, W, s in ((LE, LW, -1), (RE, RW, 1)):
            d = (W - E).normalized()
            rot = Vector((0, 0, 1)).rotation_difference(d).to_matrix()
            bm_ellipsoid(bm, W + d * 0.085, (0.056, 0.07, 0.095), rot)
            side = d.cross(Vector((0, 1, 0))).normalized() * s
            bm_ellipsoid(bm, W + d * 0.06 + side * 0.052 + Vector((0, 0.03, 0)), (0.025, 0.025, 0.05), rot)
    part('Suit_Gloves', col, root, gloves, glove, smooth=True, mods=(lambda o: subsurf(o, 1),))

    # Boots
    def boots(bm):
        for A, rz in ((LA, -6), (RA, 12)):
            rot = Matrix.Rotation(math.radians(rz), 3, 'Z')
            bm_box(bm, A + rot @ Vector((0, 0.05, -0.10)), (0.16, 0.33, 0.15), rot)
    b = part('Suit_Boots', col, root, boots, boot, mods=(lambda o: bevel(o, 0.035, 3),
                                                         lambda o: subsurf(o, 1)))

    def soles(bm):
        for A, rz in ((LA, -6), (RA, 12)):
            rot = Matrix.Rotation(math.radians(rz), 3, 'Z')
            bm_box(bm, A + rot @ Vector((0, 0.05, -0.172)), (0.17, 0.345, 0.04), rot)
    part('Suit_Soles', col, root, soles, sole, mods=(lambda o: bevel(o, 0.012, 2),))

    # Backpack (PLSS)
    plss_mat = M.painted_panels('PLSSPanels', (0.80, 0.80, 0.78), mode='BOX', pu=0.26, pv=0.22,
                                rough=0.38, dust_bottom=0.0, wear=0.2)
    part('Suit_PLSS', col, root,
         lambda bm: (bm_box(bm, (0, -0.33, 1.22), (0.52, 0.26, 0.68)),
                     bm_box(bm, (0, -0.31, 1.60), (0.44, 0.22, 0.08))),
         plss_mat, mods=(lambda o: bevel(o, 0.045, 4),))
    part('Suit_PLSSVents', col, root,
         lambda bm: [bm_box(bm, (0.0, -0.462, 0.96 + 0.026 * i), (0.26, 0.018, 0.012)) for i in range(6)],
         M.metal('VentMetal', (0.3, 0.3, 0.32), rough=0.4), mods=(lambda o: bevel(o, 0.003, 1),))
    part('Suit_PLSSDetail', col, root,
         lambda bm: (bm_box(bm, (0.0, -0.458, 1.27), (0.30, 0.02, 0.16)),
                     bm_cylinder(bm, (-0.2, -0.36, 1.64), (-0.2, -0.36, 1.95), 0.008, segs=6),
                     bm_box(bm, (0.16, -0.465, 1.40), (0.08, 0.02, 0.08))),
         dcm, mods=(lambda o: bevel(o, 0.008, 2),))

    # Chest control module
    tilt = Matrix.Rotation(math.radians(-18), 3, 'X')
    part('Suit_DCM', col, root,
         lambda bm: bm_box(bm, (0, 0.235, 1.20), (0.26, 0.10, 0.13), tilt),
         dcm, mods=(lambda o: bevel(o, 0.015, 3),))
    part('Suit_DCM_LEDs', col, root,
         lambda bm: [bm_box(bm, Vector((x, 0.288, 1.235)), (0.018, 0.008, 0.012), tilt)
                     for x in (-0.07, -0.04)],
         led_g)
    part('Suit_DCM_LEDr', col, root,
         lambda bm: bm_box(bm, Vector((0.075, 0.288, 1.235)), (0.018, 0.008, 0.012), tilt), led_r)

    # Hoses PLSS -> DCM
    for k_, s in enumerate((-1, 1)):
        cu = bpy.data.curves.new(f'Suit_Hose_{k_}', 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = 0.014
        cu.bevel_resolution = 3
        sp = cu.splines.new('BEZIER')
        pts = [Vector((s * 0.22, -0.2, 1.0)), Vector((s * 0.31, 0.06, 1.02)), Vector((s * 0.11, 0.27, 1.17))]
        sp.bezier_points.add(len(pts) - 1)
        for bp, p in zip(sp.bezier_points, pts):
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
        ob = bpy.data.objects.new(f'Suit_Hose_{k_}', cu)
        col.objects.link(ob)
        cu.materials.append(hose_mat)
        parent_to(ob, root)

    # Tablet in the right hand
    tab_rot = Matrix.Rotation(math.radians(-55), 3, 'X') @ Matrix.Rotation(math.radians(-20), 3, 'Z')
    tc = RW + Vector((-0.04, 0.10, 0.02))
    part('Suit_Tablet', col, root, lambda bm: bm_box(bm, tc, (0.19, 0.13, 0.014), tab_rot), dcm,
         mods=(lambda o: bevel(o, 0.006, 2),))
    tscr = part('Suit_TabletScreen', col, root,
                lambda bm: bm_box(bm, tc + tab_rot @ Vector((0, 0, 0.0075)), (0.165, 0.105, 0.001), tab_rot),
                tablet_scr)
    from .props import _box_uvs
    _box_uvs(tscr)

    # Helmet: tilt a little upward towards the hole
    helmet = empty('Helmet', col, size=0.2)
    parent_to(helmet, root)
    helmet.location = HELMET_C
    helmet.rotation_euler = (math.radians(9), 0, math.radians(-10))

    op_az, op_lo, op_hi = math.radians(64), math.radians(-40), math.radians(40)

    def hood(bm):
        R = 0.182 * HS
        segs, rings = 64, 40
        rows = []
        for j in range(rings + 1):
            el = -math.pi / 2 + math.pi * j / rings
            row = []
            for i in range(segs):
                a = 2 * math.pi * i / segs
                row.append(bm.verts.new(Vector((math.cos(el) * math.sin(a), math.cos(el) * math.cos(a),
                                                math.sin(el))) * R))
            rows.append(row)
        for j in range(rings):
            el_c = -math.pi / 2 + math.pi * (j + 0.5) / rings
            for i in range(segs):
                az_c = 2 * math.pi * (i + 0.5) / segs
                azs = (az_c + math.pi) % (2 * math.pi) - math.pi
                if abs(azs) < op_az and op_lo < el_c < op_hi:
                    continue                           # visor opening
                if el_c < math.radians(-58):
                    continue                           # neck opening
                i2 = (i + 1) % segs
                bm.faces.new((rows[j][i], rows[j][i2], rows[j + 1][i2], rows[j + 1][i]))
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    hd = part('Helmet_Hood', col, helmet, hood, shell, smooth=True)
    add_mod(hd, 'SOLIDIFY', thickness=0.014, offset=-1.0, use_even_offset=True)
    bevel(hd, 0.004, 2, angle=40)

    vz = part('Helmet_Visor', col, helmet,
              lambda bm: bm_sphere_patch(bm, (0, 0, 0), 0.174 * HS, op_az + 0.06, op_lo - 0.06, op_hi + 0.06),
              gold, smooth=True)
    add_mod(vz, 'SOLIDIFY', thickness=0.004, offset=-1.0)
    # inner bubble (dark, seen through nothing but keeps the silhouette solid)
    part('Helmet_Bubble', col, helmet,
         lambda bm: bm_ellipsoid(bm, (0, 0, 0), (0.160 * HS, 0.160 * HS, 0.160 * HS), segs=40, rings=24),
         M.plastic('HelmetInner', (0.02, 0.02, 0.025), rough=0.3), smooth=True)
    # helmet lamps + ear pods
    def pods(bm):
        for s in (-1, 1):
            bm_cylinder(bm, (s * 0.192, 0.03, 0.06), (s * 0.192, 0.13, 0.06), 0.026, segs=20)
            bm_cylinder(bm, (s * 0.188, -0.02, -0.01), (s * 0.212, -0.02, -0.01), 0.045, segs=24)
    part('Helmet_Pods', col, helmet, pods, dcm, smooth=True, mods=(lambda o: bevel(o, 0.004, 2, angle=50),))
    # reinforcing ridge over the crown + rear status light
    def ridge(bm):
        R = 0.182 * HS + 0.004
        pts = []
        for k in range(29):
            th = math.radians(62 + (230 - 62) * k / 28)
            pts.append(Vector((0.0, R * math.cos(th), R * math.sin(th))))
        for a, b in zip(pts[:-1], pts[1:]):
            bm_cylinder(bm, a, b, 0.011, segs=8, caps=False)
    part('Helmet_Ridge', col, helmet, ridge, shell, smooth=True)
    part('Helmet_RearLED', col, helmet,
         lambda bm: bm_box(bm, (0.0, -0.198, 0.07), (0.03, 0.012, 0.014),
                           Matrix.Rotation(math.radians(-20), 3, 'X')),
         led_r)
    part('Helmet_Lamps', col, helmet,
         lambda bm: [bm_cylinder(bm, (s * 0.192, 0.13, 0.06), (s * 0.192, 0.133, 0.06), 0.021, segs=20)
                     for s in (-1, 1)],
         lamp, smooth=True)

    focus = empty('FocusTarget', col, size=0.1)
    parent_to(focus, helmet)
    focus.location = (0.0, 0.05, 0.0)

    bpy.context.view_layer.update()
    return dict(root=root, helmet=helmet.matrix_world.translation.copy(), up=L.AST_DIR.copy(),
                focus=focus, forward=(root.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized())
