"""Procedural material library for the props and the astronaut."""

import math

import bpy

from .util import new_material, principled, emission, NodeBuilder


def _obj_coords(nb):
    return nb.node('ShaderNodeTexCoord').outputs['Object']


def _dust(nb, base, amount_field, noise_scale=3.0, color=(0.20, 0.18, 0.16)):
    """Regolith dust settling on a surface."""
    tc = nb.node('ShaderNodeTexCoord').outputs['Object']
    n = nb.noise(tc, scale=noise_scale, detail=6.0, rough=0.6)
    m = nb.mul(amount_field, nb.smoothstep(0.35, 0.7, n.outputs['Factor']))
    return nb.mix(m, base, color), m


def _line_dist(nb, x, period):
    """Distance (in x units) to the nearest multiple of `period`."""
    f = nb.math('FRACT', nb.div(x, period))
    d = nb.sub(0.5, nb.math('ABSOLUTE', nb.sub(f, 0.5)))
    return nb.mul(d, period)


def panel_mask(nb, u, v, pu, pv, width):
    du = _line_dist(nb, u, pu)
    dv = _line_dist(nb, v, pv)
    d = nb.math('MINIMUM', du, dv)
    return nb.sub(1.0, nb.smoothstep(0.0, width, d)), du, dv


def rivets(nb, u, v, pu, pv, spacing, radius):
    """Rivet dots running along the seams."""
    du = _line_dist(nb, u, pu)
    dv = _line_dist(nb, v, pv)
    # along each seam, periodic dots
    alu = _line_dist(nb, nb.add(v, spacing * 0.5), spacing)
    alv = _line_dist(nb, nb.add(u, spacing * 0.5), spacing)
    offs = radius * 3.2
    r1 = nb.vmath('LENGTH', nb.combine(nb.sub(du, offs), alu, 0.0))
    r2 = nb.vmath('LENGTH', nb.combine(nb.sub(dv, offs), alv, 0.0))
    r = nb.math('MINIMUM', r1, r2)
    return nb.sub(1.0, nb.smoothstep(radius * 0.6, radius, r))


def painted_panels(name, color, mode='CYL', pu=None, pv=0.55, seam=0.004, rough=0.5,
                   dust_bottom=0.9, metallic=0.0, wear=0.35):
    """Painted metal cladding with procedural seams/rivets.
    mode CYL: u = arc length around object Z, v = z.
    mode SPH: u = longitude arc length, v = latitude arc length (radius ~1.5).
    mode BOX: u = x + y, v = z."""
    mat, nb, out = new_material(name)
    oc = _obj_coords(nb)
    x, y, z = nb.separate(oc)
    if mode in ('CYL', 'SPH'):
        ang = nb.math('ARCTAN2', y, x)
        rad = nb.vmath('LENGTH', nb.combine(x, y, 0.0))
        if mode == 'CYL':
            u = nb.mul(ang, 1.5)
            v = z
        else:
            r3 = nb.vmath('LENGTH', oc)
            lat = nb.math('ARCSINE', nb.math('DIVIDE', z, nb.math('MAXIMUM', r3, 1e-4), clamp=False))
            u = nb.mul(ang, 1.5)
            v = nb.mul(lat, 1.5)
    else:
        u = nb.add(x, y)
        v = z
    pu = pu or (2 * math.pi * 1.5 / 16)
    seam_m, du, dv = panel_mask(nb, u, v, pu, pv, seam)
    riv = rivets(nb, u, v, pu, pv, 0.09, 0.0055)

    # per-panel tint variation: hash panel index
    iu = nb.math('FLOOR', nb.div(u, pu))
    iv = nb.math('FLOOR', nb.div(v, pv))
    wn = nb.node('ShaderNodeTexWhiteNoise', {'Vector': nb.combine(iu, iv, 0.0)}, noise_dimensions='3D')
    tint = nb.maprange(wn.outputs['Value'], 0, 1, 0.93, 1.05)
    base = nb.mix(1.0, color, nb.combine(tint, tint, tint), blend='MULTIPLY')

    grime = nb.noise(oc, scale=6.0, detail=8.0, rough=0.65)
    streak = nb.noise(nb.vmath('MULTIPLY', oc, (4.0, 4.0, 0.35)), scale=5.0, detail=4.0)
    g = nb.mul(nb.smoothstep(0.55, 0.8, streak.outputs['Factor']), wear)
    base = nb.mix(g, base, nb.vmath('MULTIPLY', color, (0.55, 0.53, 0.5)))
    base = nb.mix(nb.mul(seam_m, 0.8), base, (0.02, 0.02, 0.02))
    base = nb.mix(nb.mul(riv, 0.5), base, (0.4, 0.4, 0.42))

    # dust creeping up from the ground
    low = nb.sub(1.0, nb.smoothstep(0.1, 0.8, z))
    base, dm = _dust(nb, base, nb.mul(low, dust_bottom))

    # chipped paint exposing metal
    chip = nb.noise(oc, scale=18.0, detail=6.0, rough=0.7)
    chipm = nb.mul(nb.smoothstep(0.66, 0.70, chip.outputs['Factor']), wear)
    base = nb.mix(chipm, base, (0.35, 0.35, 0.37))
    metal = nb.add(metallic, nb.mul(chipm, 0.9))

    r = nb.add(nb.maprange(grime.outputs['Factor'], 0.3, 0.7, rough - 0.1, rough + 0.12), nb.mul(dm, 0.35))
    h = nb.add(nb.mul(seam_m, -1.0), nb.add(nb.mul(riv, 0.6), nb.mul(chipm, -0.3)))
    bump = nb.node('ShaderNodeBump', {'Height': h, 'Strength': 0.5, 'Distance': 0.003})
    bsdf = principled(nb, base=base, rough=r, metal=metal, normal=bump, spec=0.5)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def concrete(name='Concrete'):
    mat, nb, out = new_material(name)
    oc = _obj_coords(nb)
    n = nb.noise(oc, scale=9.0, detail=10.0, rough=0.65)
    n2 = nb.noise(oc, scale=1.5, detail=4.0)
    base = nb.ramp(n.outputs['Factor'], [(0.3, (0.12, 0.118, 0.112)), (0.7, (0.24, 0.232, 0.22))])
    base = nb.mix(nb.mul(nb.smoothstep(0.4, 0.7, n2.outputs['Factor']), 0.4), base, (0.09, 0.085, 0.08))
    pits = nb.voronoi(oc, scale=40.0)
    ph = nb.smoothstep(0.0, 0.25, pits.outputs['Distance'])
    bump = nb.node('ShaderNodeBump', {'Height': nb.add(n.outputs['Factor'], nb.mul(ph, 0.3)),
                                      'Strength': 0.35, 'Distance': 0.005})
    bsdf = principled(nb, base=base, rough=0.92, normal=bump, spec=0.3)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def metal(name, color=(0.56, 0.57, 0.6), rough=0.32, aniso=0.0, dirt=0.3):
    mat, nb, out = new_material(name)
    oc = _obj_coords(nb)
    n = nb.noise(oc, scale=12.0, detail=8.0, rough=0.6)
    scratch = nb.noise(nb.vmath('MULTIPLY', oc, (40.0, 40.0, 1.5)), scale=4.0, detail=3.0)
    r = nb.add(nb.maprange(n.outputs['Factor'], 0.3, 0.7, rough - 0.08, rough + 0.12),
               nb.mul(nb.smoothstep(0.6, 0.75, scratch.outputs['Factor']), 0.15))
    base = nb.mix(nb.mul(nb.smoothstep(0.55, 0.75, n.outputs['Factor']), dirt), color,
                  nb.vmath('MULTIPLY', color, (0.5, 0.48, 0.45)))
    bsdf = principled(nb, base=base, metal=1.0, rough=r, aniso=aniso)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def plastic(name, color, rough=0.45, dust=0.0):
    mat, nb, out = new_material(name)
    oc = _obj_coords(nb)
    n = nb.noise(oc, scale=8.0, detail=6.0)
    base = color
    if dust:
        base, _ = _dust(nb, color, dust)
    r = nb.maprange(n.outputs['Factor'], 0.3, 0.7, rough - 0.05, rough + 0.1)
    bsdf = principled(nb, base=base, rough=r, spec=0.5)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def glow(name, color, strength, flicker=False):
    mat, nb, out = new_material(name)
    em = emission(nb, color, strength)
    nb.link(em, out.inputs['Surface'])
    mat['emission_node'] = em.name
    return mat


def glass_glow(name, color, strength):
    """Frosted lamp lens: emission layered with a glossy clear-coat look."""
    mat, nb, out = new_material(name)
    em = emission(nb, color, strength)
    gl = nb.node('ShaderNodeBsdfGlossy', {'Roughness': 0.08, 'Color': (1, 1, 1)})
    fres = nb.node('ShaderNodeFresnel', {'IOR': 1.5})
    mix = nb.node('ShaderNodeMixShader', {'Fac': fres, 1: em, 2: gl})
    nb.link(mix, out.inputs['Surface'])
    return mat


def striped_mast(name='MastPaint'):
    mat, nb, out = new_material(name)
    oc = _obj_coords(nb)
    x, y, z = nb.separate(oc)
    band = nb.math('FLOORED_MODULO', nb.math('FLOOR', nb.div(z, 0.72)), 2.0)
    red = (0.62, 0.075, 0.03)
    white = (0.62, 0.61, 0.58)
    base = nb.mix(band, red, white)
    n = nb.noise(oc, scale=20.0, detail=6.0, rough=0.6)
    base = nb.mix(nb.mul(nb.smoothstep(0.6, 0.8, n.outputs['Factor']), 0.4), base, (0.2, 0.19, 0.18))
    low = nb.sub(1.0, nb.smoothstep(0.0, 0.9, z))
    base, dm = _dust(nb, base, low)
    bsdf = principled(nb, base=base, rough=0.5, metal=0.2, spec=0.5)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def solar_cells(name='SolarCells'):
    mat, nb, out = new_material(name)
    tc = nb.node('ShaderNodeTexCoord').outputs['UV']
    brick = nb.node('ShaderNodeTexBrick', {'Vector': tc, 'Color1': (0.012, 0.02, 0.06),
                                           'Color2': (0.02, 0.03, 0.08), 'Mortar': (0.5, 0.52, 0.55),
                                           'Scale': 1.0, 'Mortar Size': 0.012, 'Mortar Smooth': 0.1,
                                           'Bias': 0.0, 'Brick Width': 0.1, 'Row Height': 0.166},
                     offset=0.0, squash=1.0)
    n = nb.noise(tc, scale=40.0, detail=4.0)
    fine = nb.node('ShaderNodeTexWave', {'Vector': tc, 'Scale': 180.0, 'Distortion': 0.0}, wave_type='BANDS')
    base = nb.mix(nb.mul(fine.outputs['Fac'], 0.15), brick.outputs['Color'], (0.05, 0.07, 0.16))
    bsdf = principled(nb, base=base, rough=nb.maprange(n.outputs['Factor'], 0, 1, 0.22, 0.34),
                      metal=0.1, coat=0.35, coat_rough=0.12, spec=0.45)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def hazard_crate(name, color):
    mat, nb, out = new_material(name)
    oc = _obj_coords(nb)
    x, y, z = nb.separate(oc)
    diag = nb.math('FLOORED_MODULO', nb.math('FLOOR', nb.div(nb.add(nb.add(x, y), z), 0.08)), 2.0)
    band = nb.mul(nb.smoothstep(0.24, 0.245, z), nb.sub(1.0, nb.smoothstep(0.31, 0.315, z)))
    stripe = nb.mul(diag, band)
    base = nb.mix(stripe, color, (0.02, 0.02, 0.02))
    n = nb.noise(oc, scale=10.0, detail=8.0, rough=0.6)
    base = nb.mix(nb.mul(nb.smoothstep(0.62, 0.72, n.outputs['Factor']), 0.7), base, (0.3, 0.3, 0.3))
    base, _ = _dust(nb, base, nb.sub(1.0, nb.smoothstep(0.0, 0.5, z)))
    bsdf = principled(nb, base=base, rough=0.55, spec=0.4)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def screen(name, color=(0.25, 0.75, 1.0), strength=3.0):
    """Console screen: scanlines + fake waveform readouts."""
    mat, nb, out = new_material(name)
    tc = nb.node('ShaderNodeTexCoord').outputs['UV']
    ux, uy, _ = nb.separate(tc)
    wave = nb.add(0.5, nb.mul(nb.math('SINE', nb.mul(ux, 28.0)), nb.mul(0.25, nb.math('SINE', nb.mul(ux, 3.0)))))
    line = nb.sub(1.0, nb.smoothstep(0.0, 0.03, nb.math('ABSOLUTE', nb.sub(uy, wave))))
    grid = nb.sub(1.0, nb.smoothstep(0.0, 0.02, _line_dist(nb, ux, 0.125)))
    scan = nb.maprange(nb.math('SINE', nb.mul(uy, 400.0)), -1, 1, 0.75, 1.0)
    lum = nb.mul(nb.add(nb.add(0.18, line), nb.mul(grid, 0.25)), scan)
    col = nb.mix(1.0, color, nb.combine(lum, lum, lum), blend='MULTIPLY')
    em = emission(nb, col, strength)
    nb.link(em, out.inputs['Surface'])
    return mat


def rubber(name='Rubber'):
    mat, nb, out = new_material(name)
    bsdf = principled(nb, base=(0.018, 0.018, 0.02), rough=0.7)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def dish_paint(name='DishPaint'):
    """White dish with petal seams, from dish-local polar coordinates."""
    mat, nb, out = new_material(name)
    oc = _obj_coords(nb)
    x, y, z = nb.separate(oc)
    ang = nb.math('ARCTAN2', y, x)
    rad = nb.vmath('LENGTH', nb.combine(x, y, 0.0))
    seam_m, _, _ = panel_mask(nb, nb.mul(ang, 1.0), rad, 2 * math.pi / 12, 0.36, 0.0035)
    n = nb.noise(oc, scale=7.0, detail=8.0, rough=0.6)
    base = nb.mix(nb.mul(nb.smoothstep(0.55, 0.8, n.outputs['Factor']), 0.35), (0.72, 0.71, 0.68), (0.45, 0.43, 0.4))
    base = nb.mix(nb.mul(seam_m, 0.7), base, (0.05, 0.05, 0.05))
    bump = nb.node('ShaderNodeBump', {'Height': nb.mul(seam_m, -1.0), 'Strength': 0.4, 'Distance': 0.002})
    bsdf = principled(nb, base=base, rough=0.42, normal=bump, spec=0.5)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def animate_blink(socket_owner, data_path, on_value, off_value, period_frames, phase=0,
                  pulse_frames=5, frames=144):
    """Beacon blink: short smooth pulse every period."""
    for f in range(1, frames + 1):
        t = (f - 1 + phase) % period_frames
        if t < pulse_frames:
            k = math.sin(math.pi * (t + 0.5) / pulse_frames)
        else:
            k = 0.0
        setattr(socket_owner, data_path, off_value + (on_value - off_value) * k)
        socket_owner.keyframe_insert(data_path, frame=f)
