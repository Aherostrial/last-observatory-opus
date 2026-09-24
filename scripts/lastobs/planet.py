"""The planet: procedural terrain (Geometry Nodes), regolith, footprints, rocks."""

import math

import bpy
from mathutils import Vector

from . import layout as L
from .util import (NodeBuilder, new_geo_group, gn_modifier, new_material, principled,
                   collection, mesh_object)


# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------

def _crater_layer(nb, pos, scale, rmin, rmax, presence, depth_k, seed):
    """Returns (height, floor_mask, rim_mask) sockets for one crater layer."""
    p = nb.vmath('ADD', pos, (seed * 13.1, seed * 7.7, seed * 3.3))
    vor = nb.voronoi(p, scale=scale, rand=0.9)
    col = nb.separate(vor.outputs['Color'])
    rc = nb.maprange(col[0], 0.0, 1.0, rmin, rmax)                 # crater radius (cell units)
    x = nb.div(vor.outputs['Distance'], rc)
    bowl = nb.math('MINIMUM', nb.sub(nb.mul(x, x), 1.0), 0.0)        # -1 .. 0 inside
    t = nb.div(nb.sub(x, 1.0), 0.32)
    rim = nb.math('EXPONENT', nb.mul(nb.mul(t, t), -1.0))            # gaussian rim
    present = nb.math('LESS_THAN', col[1], presence)
    depth = nb.mul(nb.div(rc, scale), depth_k)                       # metres
    h = nb.mul(nb.mul(nb.add(bowl, nb.mul(rim, 0.38)), depth), present)
    floor = nb.mul(nb.mul(bowl, -1.0), present)
    rimm = nb.mul(rim, present)
    return h, floor, rimm


def build_terrain_group(pad_dir, walk_a, walk_b):
    ng, nb, gin, gout = new_geo_group(
        'PlanetTerrain',
        inputs=(('Radius', 'NodeSocketFloat', L.R),
                ('Subdivisions', 'NodeSocketInt', 8),
                ('Pad Radius', 'NodeSocketFloat', L.PAD_RADIUS),
                ('Material', 'NodeSocketMaterial')))

    ico = nb.node('GeometryNodeMeshIcoSphere', {'Radius': gin.outputs['Radius'],
                                                'Subdivisions': gin.outputs['Subdivisions']})
    pos = nb.node('GeometryNodeInputPosition').outputs[0]
    nrm = nb.vmath('NORMALIZE', pos)

    # Macro undulation + mid-frequency lumps
    n1 = nb.noise(pos, scale=0.11, detail=5.0, rough=0.55)
    h1 = nb.mul(nb.sub(n1.outputs['Factor'], 0.5), 1.25)
    n2 = nb.noise(pos, scale=0.55, detail=6.0, rough=0.6, dist=0.3)
    h2 = nb.mul(nb.sub(n2.outputs['Factor'], 0.5), 0.30)
    # Ridged detail
    n3 = nb.noise(pos, scale=1.9, detail=3.0, rough=0.5, ntype='RIDGED_MULTIFRACTAL', normalize=False)
    h3 = nb.mul(n3.outputs['Factor'], 0.035)

    cA, fA, rA = _crater_layer(nb, pos, 0.17, 0.20, 0.42, 0.55, 0.42, 1.0)
    cB, fB, rB = _crater_layer(nb, pos, 0.62, 0.18, 0.40, 0.50, 0.36, 2.0)
    cC, fC, rC = _crater_layer(nb, pos, 2.1, 0.20, 0.38, 0.35, 0.30, 3.0)

    # Walkway mask (door -> astronaut) and the levelled pad
    A = Vector(walk_a)
    B = Vector(walk_b)
    AB = B - A
    rel = nb.vmath('SUBTRACT', pos, tuple(A))
    t = nb.math('DIVIDE', nb.vmath('DOT_PRODUCT', rel, tuple(AB)), AB.length_squared, clamp=True)
    closest = nb.vmath('ADD', tuple(A), nb.vmath('SCALE', tuple(AB), scale=t))
    dwalk = nb.vmath('DISTANCE', pos, closest)
    walk = nb.sub(1.0, nb.smoothstep(0.7, 1.9, dwalk))

    dpad = nb.vmath('DISTANCE', nb.vmath('SCALE', nrm, scale=L.R), tuple(Vector(pad_dir) * L.R))
    pad = nb.sub(1.0, nb.smoothstep(nb.mul(gin.outputs['Pad Radius'], 0.72),
                                    nb.mul(gin.outputs['Pad Radius'], 1.45), dpad))

    craters = nb.add(nb.add(cA, cB), cC)
    tame = nb.sub(1.0, nb.mul(walk, 0.8))                 # soften craters on the path
    dspot = nb.vmath('DISTANCE', pos, tuple(B))
    spot = nb.sub(1.0, nb.smoothstep(0.55, 1.5, dspot))    # smooth standing spot
    tame = nb.mul(tame, nb.sub(1.0, spot))
    detail = nb.add(nb.mul(nb.add(h2, h3), nb.sub(1.0, nb.mul(spot, 0.85))), nb.mul(craters, tame))
    h = nb.add(h1, detail)
    # pad: blend to a flat shelf at the local macro height
    pad_h = 0.10
    h = nb.mix(pad, h, pad_h, kind='FLOAT')

    offset = nb.vmath('SCALE', nrm, scale=h)
    setpos = nb.node('GeometryNodeSetPosition', {'Geometry': ico.outputs['Mesh'], 'Offset': offset})

    keep = nb.sub(1.0, pad)
    floor = nb.mul(nb.math('MAXIMUM', nb.math('MAXIMUM', fA, fB), fC), keep)
    rim = nb.mul(nb.math('MAXIMUM', nb.math('MAXIMUM', rA, rB), rC), keep)

    g = setpos.outputs[0]
    for name, val in (('crater_floor', floor), ('crater_rim', rim), ('height', h), ('pad', pad)):
        st = nb.node('GeometryNodeStoreNamedAttribute', {'Geometry': g, 'Name': name, 'Value': val},
                     data_type='FLOAT', domain='POINT')
        g = st.outputs[0]
    smooth = nb.node('GeometryNodeSetShadeSmooth', {'Mesh': g, 'Shade Smooth': True})
    setmat = nb.node('GeometryNodeSetMaterial', {'Geometry': smooth, 'Material': gin.outputs['Material']})
    nb.link(setmat, gout.inputs['Geometry'])
    return ng


# ---------------------------------------------------------------------------
# Regolith material (with procedural footprints)
# ---------------------------------------------------------------------------

def _footprints(nb, pos, walk_a, walk_b):
    A = Vector(walk_a)
    B = Vector(walk_b)
    nmid = (A + B).normalized()
    tdir = (B - A)
    tdir = (tdir - nmid * tdir.dot(nmid)).normalized()
    sdir = tdir.cross(nmid).normalized()
    length = (B - A).length

    rel = nb.vmath('SUBTRACT', pos, tuple(A))
    u = nb.vmath('DOT_PRODUCT', rel, tuple(tdir))
    v = nb.vmath('DOT_PRODUCT', rel, tuple(sdir))
    stride = 0.70
    k = nb.math('FLOOR', nb.div(u, stride))
    fu = nb.sub(u, nb.mul(nb.add(k, 0.5), stride))
    side = nb.sub(nb.mul(nb.math('FLOORED_MODULO', k, 2.0), 2.0), 1.0)
    wn = nb.node('ShaderNodeTexWhiteNoise', {'W': k}, noise_dimensions='1D')
    jit = nb.sub(wn.outputs['Value'], 0.5)
    fv = nb.sub(v, nb.add(nb.mul(side, 0.125), nb.mul(jit, 0.05)))
    # slight toe-out rotation per foot
    ang = nb.mul(side, 0.12)
    ca, sa = math.cos(0.12), math.sin(0.12)
    fu2 = nb.sub(nb.mul(fu, ca), nb.mul(nb.mul(fv, side), sa))
    fv2 = nb.add(nb.mul(nb.mul(fu, side), sa), nb.mul(fv, ca))
    # boot outline: ellipse, slightly wider at the toe
    widen = nb.maprange(fu2, -0.15, 0.15, 0.052, 0.066)
    e = nb.vmath('LENGTH', nb.combine(nb.div(fu2, 0.155), nb.div(fv2, widen), 0.0))
    inside = nb.sub(1.0, nb.smoothstep(0.72, 1.0, e))
    tread = nb.math('SINE', nb.mul(fu2, 70.0))
    tread = nb.mul(nb.add(tread, 1.0), 0.5)
    rimr = nb.mul(nb.smoothstep(0.86, 1.02, e), nb.sub(1.0, nb.smoothstep(1.02, 1.45, e)))

    along = nb.mul(nb.smoothstep(0.35, 0.6, u), nb.sub(1.0, nb.smoothstep(length - 0.7, length - 0.45, u)))
    facing = nb.smoothstep(0.93, 0.96, nb.vmath('DOT_PRODUCT', nb.vmath('NORMALIZE', pos), tuple(nmid)))
    lateral = nb.sub(1.0, nb.smoothstep(0.35, 0.5, nb.math('ABSOLUTE', v)))
    mask = nb.mul(nb.mul(along, facing), lateral)

    height = nb.mul(nb.add(nb.mul(inside, nb.add(-1.0, nb.mul(tread, -0.35))), nb.mul(rimr, 0.3)), mask)
    darken = nb.mul(inside, mask)
    return height, darken


def build_regolith(walk_a, walk_b):
    mat, nb, out = new_material('Regolith')
    pos = nb.node('ShaderNodeNewGeometry').outputs['Position']
    attr = lambda n: nb.node('ShaderNodeAttribute', attribute_name=n, attribute_type='GEOMETRY').outputs['Fac']
    floor = attr('crater_floor')
    rim = attr('crater_rim')
    pad = attr('pad')

    macro = nb.noise(pos, scale=0.32, detail=6.0, rough=0.6)
    mid = nb.noise(pos, scale=2.4, detail=6.0, rough=0.62)
    fine = nb.noise(pos, scale=22.0, detail=8.0, rough=0.7)

    base = nb.ramp(macro.outputs['Factor'], [
        (0.30, (0.052, 0.050, 0.050)),
        (0.50, (0.105, 0.098, 0.092)),
        (0.68, (0.175, 0.160, 0.145)),
    ])
    # mid-scale mottling
    base = nb.mix(nb.smoothstep(0.42, 0.62, mid.outputs['Factor']), base,
                  (0.21, 0.19, 0.165), blend='MIX')
    base = nb.mix(0.35, base, nb.mix(fine.outputs['Factor'], (0.6, 0.6, 0.6), (1.3, 1.3, 1.3)), blend='MULTIPLY')
    # crater floors darker, rims carry bright ejecta
    base = nb.mix(nb.mul(floor, 0.55), base, (0.035, 0.034, 0.036))
    ej = nb.mul(rim, nb.smoothstep(0.35, 0.7, mid.outputs['Factor']))
    base = nb.mix(nb.mul(ej, 0.55), base, (0.26, 0.24, 0.21))
    # trodden pad: compacted, slightly darker and smoother
    base = nb.mix(nb.mul(pad, 0.35), base, (0.075, 0.07, 0.066))

    fp_h, fp_dark = _footprints(nb, pos, walk_a, walk_b)
    base = nb.mix(nb.mul(fp_dark, 0.55), base, (0.045, 0.042, 0.04))

    rough = nb.maprange(fine.outputs['Factor'], 0.3, 0.7, 0.82, 0.96)

    # Bump: grains + pebbles + footprints
    peb = nb.voronoi(pos, scale=11.0, feature='SMOOTH_F1', smooth=0.6)
    pebh = nb.sub(1.0, nb.smoothstep(0.0, 0.42, peb.outputs['Distance']))
    grains = nb.noise(pos, scale=60.0, detail=4.0, rough=0.6)
    hsum = nb.add(nb.add(nb.mul(fine.outputs['Factor'], 0.7), nb.mul(pebh, 0.55)),
                  nb.add(nb.mul(grains.outputs['Factor'], 0.25), nb.mul(fp_h, 1.6)))
    bump = nb.node('ShaderNodeBump', {'Height': hsum, 'Strength': 0.55, 'Distance': 0.012})

    bsdf = principled(nb, base=base, rough=rough, normal=bump, spec=0.35)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


# ---------------------------------------------------------------------------
# Rocks
# ---------------------------------------------------------------------------

def build_rock_material():
    mat, nb, out = new_material('Basalt')
    tc = nb.node('ShaderNodeTexCoord')
    obj = tc.outputs['Object']
    oi = nb.node('ShaderNodeObjectInfo')
    wpos = nb.node('ShaderNodeNewGeometry')
    p = nb.vmath('ADD', obj, nb.vmath('SCALE', (17.0, 31.0, 5.0), scale=oi.outputs['Random']))

    n1 = nb.noise(p, scale=2.2, detail=8.0, rough=0.65)
    n2 = nb.noise(p, scale=11.0, detail=6.0, rough=0.6)
    crack = nb.voronoi(p, scale=3.5, feature='DISTANCE_TO_EDGE')
    cr = nb.sub(1.0, nb.smoothstep(0.0, 0.05, crack.outputs['Distance']))

    base = nb.ramp(n1.outputs['Factor'], [
        (0.35, (0.030, 0.029, 0.030)),
        (0.60, (0.070, 0.066, 0.064)),
        (0.80, (0.120, 0.110, 0.100)),
    ])
    tint = nb.mix(oi.outputs['Random'], (0.9, 0.95, 1.0), (1.08, 1.0, 0.92))
    base = nb.mix(1.0, base, tint, blend='MULTIPLY')
    # dust settles on upward faces (relative to the planet)
    up = nb.vmath('NORMALIZE', wpos.outputs['Position'])
    facing = nb.vmath('DOT_PRODUCT', wpos.outputs['Normal'], up)
    dust = nb.mul(nb.smoothstep(0.35, 0.85, facing), nb.smoothstep(0.35, 0.65, n2.outputs['Factor']))
    base = nb.mix(nb.mul(dust, 0.8), base, (0.19, 0.175, 0.155))
    base = nb.mix(nb.mul(cr, 0.8), base, (0.012, 0.012, 0.012))

    rough = nb.mix(dust, 0.62, 0.92, kind='FLOAT')
    h = nb.add(nb.mul(n2.outputs['Factor'], 0.6), nb.mul(cr, -0.5))
    bump = nb.node('ShaderNodeBump', {'Height': h, 'Strength': 0.6, 'Distance': 0.02})
    bsdf = principled(nb, base=base, rough=rough, normal=bump, spec=0.4)
    nb.link(bsdf, out.inputs['Surface'])
    return mat


def build_rockgen_group():
    ng, nb, gin, gout = new_geo_group(
        'RockGen',
        inputs=(('Seed', 'NodeSocketFloat', 0.0),
                ('Squash', 'NodeSocketVector', (1.0, 0.8, 0.6)),
                ('Subdivisions', 'NodeSocketInt', 4),
                ('Material', 'NodeSocketMaterial')))
    ico = nb.node('GeometryNodeMeshIcoSphere', {'Radius': 1.0, 'Subdivisions': gin.outputs['Subdivisions']})
    xf = nb.node('GeometryNodeTransform', {'Geometry': ico.outputs['Mesh'], 'Scale': gin.outputs['Squash']})
    pos = nb.node('GeometryNodeInputPosition').outputs[0]
    nrm = nb.vmath('NORMALIZE', pos)
    seedv = nb.combine(gin.outputs['Seed'], nb.mul(gin.outputs['Seed'], 1.7), nb.mul(gin.outputs['Seed'], 2.3))
    p = nb.vmath('ADD', pos, seedv)
    big = nb.noise(p, scale=0.9, detail=2.0, rough=0.5)
    # chipped facets: Chebychev voronoi gives flat-ish planes
    fac = nb.voronoi(p, scale=1.6, metric='CHEBYCHEV')
    small = nb.noise(p, scale=4.5, detail=6.0, rough=0.62)
    d = nb.add(nb.add(nb.mul(nb.sub(big.outputs['Factor'], 0.5), 0.9),
                      nb.mul(fac.outputs['Distance'], -0.28)),
               nb.mul(nb.sub(small.outputs['Factor'], 0.5), 0.16))
    sp = nb.node('GeometryNodeSetPosition', {'Geometry': xf, 'Offset': nb.vmath('SCALE', nrm, scale=d)})
    # flatten the base so rocks sit on the ground
    pos2 = nb.node('GeometryNodeInputPosition').outputs[0]
    x, y, z = nb.separate(pos2)
    zf = nb.math('SMOOTH_MAX', z, -0.32, 0.12)
    sp2 = nb.node('GeometryNodeSetPosition', {'Geometry': sp, 'Position': nb.combine(x, y, zf)})
    sm = nb.node('GeometryNodeSetShadeSmooth', {'Mesh': sp2, 'Shade Smooth': True})
    mat = nb.node('GeometryNodeSetMaterial', {'Geometry': sm, 'Material': gin.outputs['Material']})
    nb.link(mat, gout.inputs['Geometry'])
    return ng


def build_rock_prototypes(col, rock_mat, count=9):
    group = build_rockgen_group()
    protos = []
    import random
    rnd = random.Random(7)
    for i in range(count):
        me = bpy.data.meshes.new(f'RockProto_{i}')
        ob = bpy.data.objects.new(f'RockProto_{i}', me)
        col.objects.link(ob)
        sq = (1.0, rnd.uniform(0.6, 1.0), rnd.uniform(0.45, 0.85))
        gn_modifier(ob, group, Seed=float(i * 3.7 + 1.3), Squash=sq,
                    Subdivisions=5 if i < 3 else 4, Material=rock_mat)
        protos.append(ob)
    return protos


def build_scatter_group():
    ng, nb, gin, gout = new_geo_group(
        'RockScatter',
        inputs=(('Planet', 'NodeSocketObject'),
                ('Mask', 'NodeSocketObject'),
                ('Rocks', 'NodeSocketCollection'),
                ('Density', 'NodeSocketFloat', 0.9),
                ('Pebble Center', 'NodeSocketVector', (0, 0, 0)),
                ('Pebble Density', 'NodeSocketFloat', 22.0),
                ('Seed', 'NodeSocketInt', 3)))
    pl = nb.node('GeometryNodeObjectInfo', {'Object': gin.outputs['Planet']}, transform_space='RELATIVE')
    mk = nb.node('GeometryNodeObjectInfo', {'Object': gin.outputs['Mask']}, transform_space='RELATIVE')
    colinfo = nb.node('GeometryNodeCollectionInfo', {'Collection': gin.outputs['Rocks'],
                                                     'Separate Children': True, 'Reset Children': True})
    nprot = 9

    def scatter(density, dmin, smin, sexp, smax, seed, pebble=False):
        pos = nb.node('GeometryNodeInputPosition').outputs[0]
        prox = nb.node('GeometryNodeProximity', {'Geometry': mk.outputs['Geometry'], 'Sample Position': pos},
                       target_element='POINTS')
        dens_f = nb.smoothstep(1.1, 2.3, prox.outputs['Distance'])
        if pebble:
            dc = nb.vmath('DISTANCE', pos, gin.outputs['Pebble Center'])
            dens_f = nb.mul(nb.sub(1.0, nb.smoothstep(3.0, 7.5, dc)),
                            nb.smoothstep(0.45, 0.9, prox.outputs['Distance']))
        dist = nb.node('GeometryNodeDistributePointsOnFaces',
                       {'Mesh': pl.outputs['Geometry'], 'Distance Min': dmin, 'Density Max': density,
                        'Density Factor': dens_f, 'Seed': nb.add(gin.outputs['Seed'], seed)},
                       distribute_method='POISSON')
        rv = nb.node('FunctionNodeRandomValue', {'Min': 0.0, 'Max': 1.0, 'Seed': seed * 11 + 1}, data_type='FLOAT')
        s = nb.add(smin, nb.mul(nb.math('POWER', rv, sexp), smax))
        # sink into the regolith
        nrm = dist.outputs['Normal']
        sink = nb.vmath('SCALE', nrm, scale=nb.mul(s, -0.22))
        sp = nb.node('GeometryNodeSetPosition', {'Geometry': dist.outputs['Points'], 'Offset': sink})
        align = nb.node('FunctionNodeAlignRotationToVector', {'Vector': nrm}, axis='Z')
        rot_rand = nb.node('FunctionNodeRandomValue', {'Min': (-0.35, -0.35, 0.0), 'Max': (0.35, 0.35, 6.283),
                                                       'Seed': seed * 7 + 3}, data_type='FLOAT_VECTOR')
        e2r = nb.node('FunctionNodeEulerToRotation', {'Euler': rot_rand})
        rot = nb.node('FunctionNodeRotateRotation', {'Rotation': align.outputs['Rotation'],
                                                     'Rotate By': e2r.outputs['Rotation']},
                      rotation_space='LOCAL')
        idx = nb.node('FunctionNodeRandomValue', {'Min': 0, 'Max': nprot - 1, 'Seed': seed * 5 + 2}, data_type='INT')
        inst = nb.node('GeometryNodeInstanceOnPoints',
                       {'Points': sp, 'Instance': colinfo, 'Pick Instance': True,
                        'Instance Index': idx,
                        'Rotation': rot, 'Scale': s})
        return inst

    rocks = scatter(gin.outputs['Density'], 0.35, 0.05, 3.4, 0.62, 1)
    boulders = scatter(0.035, 2.5, 0.35, 1.5, 0.55, 2)
    pebbles = scatter(gin.outputs['Pebble Density'], 0.05, 0.010, 2.0, 0.045, 3, pebble=True)
    join = nb.node('GeometryNodeJoinGeometry')
    for g in (rocks, boulders, pebbles):
        nb.link(g, join.inputs[0])
    nb.link(join, gout.inputs['Geometry'])
    return ng


def build_planet(scene, walk_a, walk_b, mask_points, pebble_center):
    col = collection('Planet')
    reg = build_regolith(walk_a, walk_b)
    group = build_terrain_group(L.OBS_DIR, walk_a, walk_b)
    me = bpy.data.meshes.new('Planet')
    planet = bpy.data.objects.new('Planet', me)
    col.objects.link(planet)
    gn_modifier(planet, group, Material=reg)

    # rocks
    protos_col = collection('RockPrototypes', col)
    rock_mat = build_rock_material()
    build_rock_prototypes(protos_col, rock_mat)
    protos_col.hide_render = True
    protos_col.hide_viewport = True
    # exclude the prototype collection from the view layer so they never render
    for lc in bpy.context.view_layer.layer_collection.children['Planet'].children:
        if lc.name == 'RockPrototypes':
            lc.exclude = True

    import bmesh
    bm = bmesh.new()
    for p in mask_points:
        bm.verts.new(p)
    mask = mesh_object('ScatterMask', bm, col)
    mask.hide_render = True
    mask.display_type = 'WIRE'

    scat = bpy.data.objects.new('Rocks', bpy.data.meshes.new('Rocks'))
    col.objects.link(scat)
    gn_modifier(scat, build_scatter_group(), Planet=planet, Mask=mask, Rocks=protos_col,
                **{'Pebble Center': Vector(pebble_center)})
    return planet, scat
