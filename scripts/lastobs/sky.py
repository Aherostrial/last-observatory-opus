"""World: OSL black hole sky."""

import os
import sys

import bpy
from mathutils import Vector

from . import layout as L
from .util import NodeBuilder

SHADER_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'shaders', 'black_hole_sky.osl')


def _ensure_oslquery():
    # The pip "bpy" wheel ships oslquery inside its bundled python tree.
    try:
        import oslquery  # noqa: F401  (present in regular Blender builds)
        return
    except ImportError:
        pass
    # .../bpy/<ver>/scripts/modules/bpy/__init__.py -> .../bpy/<ver>
    ver_root = os.path.abspath(os.path.join(os.path.dirname(bpy.__file__), '..', '..', '..'))
    cand = os.path.join(ver_root, 'python', 'lib')
    if os.path.isdir(cand):
        for py in os.listdir(cand):
            sp = os.path.join(cand, py, 'site-packages')
            if os.path.isdir(sp) and sp not in sys.path:
                sys.path.append(sp)


SKY_PARAMS = dict(
    ObsDist=30.0,
    DiskInner=3.0,
    DiskOuter=11.0,
    Omega=0.30,
    DiskGain=2.2,
    Doppler=0.85,
    HaloGain=0.006,
    StarGain=0.62,
    StarSize=0.00042,
    GalaxyGain=0.010,
    LobeGain=0.40,
    Ambient=(0.022, 0.028, 0.046),
    StepScale=0.06,
)


def build_world(scene):
    _ensure_oslquery()
    import cycles.osl as cosl

    world = bpy.data.worlds.new('BlackHoleSky')
    scene.world = world
    nt = world.node_tree
    nt.nodes.clear()
    nb = NodeBuilder(nt)

    text = bpy.data.texts.get('black_hole_sky.osl')
    if text is None:
        text = bpy.data.texts.new('black_hole_sky.osl')
    with open(os.path.abspath(SHADER_PATH)) as fh:
        text.from_string(fh.read())

    script = nb.node('ShaderNodeScript', loc=(-300, 0), label='Black Hole (OSL)')
    script.mode = 'INTERNAL'
    script.script = text
    ok = cosl.update_script_node(script, lambda kind, msg: print('OSL', kind, msg))
    if not ok:
        raise RuntimeError('OSL compile failed')

    script.inputs['BHDir'].default_value = L.BH_DIR
    script.inputs['DiskNormal'].default_value = L.DISK_NORMAL
    gal = (L.U_C * 0.55 + L.R_C * 0.75 - L.F_C * 0.35).normalized()
    script.inputs['GalaxyNormal'].default_value = gal
    for k, v in SKY_PARAMS.items():
        script.inputs[k].default_value = v if not isinstance(v, tuple) else (*v, 1.0)[:len(script.inputs[k].default_value)]

    # Disk rotation clock: keyframe seconds against frames (linear).
    tsock = script.inputs['Time']
    tsock.default_value = 0.0
    tsock.keyframe_insert('default_value', frame=1)
    tsock.default_value = (L.FRAMES - 1) / L.FPS
    tsock.keyframe_insert('default_value', frame=L.FRAMES)
    fcurve_linear(world.node_tree)

    bg = nb.node('ShaderNodeBackground', {'Color': script.outputs['Col'], 'Strength': 1.0}, loc=(0, 0))
    out = nb.node('ShaderNodeOutputWorld', loc=(250, 0))
    nb.link(bg, out.inputs['Surface'])

    # Only the smooth "cheap" branch is seen by indirect rays; importance
    # sampling a smooth low-energy world is wasted effort.
    world.cycles.sampling_method = 'NONE'
    world.cycles.max_bounces = 64
    return world, script


def fcurve_linear(idblock):
    ad = idblock.animation_data
    if not ad or not ad.action:
        return
    for fc in _iter_fcurves(ad.action):
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.extrapolation = 'LINEAR'


def _iter_fcurves(action):
    # Blender 4.4+ layered actions; fall back to legacy fcurves.
    if hasattr(action, 'layers') and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        yield fc
    elif hasattr(action, 'fcurves'):
        for fc in action.fcurves:
            yield fc
