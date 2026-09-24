"""Build 'The Last Observatory' from scratch and save the .blend.

Run with the Blender Python module (pip 'bpy' 5.2) or Blender itself:

    python scripts/build_scene.py -- [--out path.blend] [--preview out.png]
    blender -b -P scripts/build_scene.py -- ...
"""

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from lastobs import layout as L
from lastobs import sky, planet, props, astronaut, lighting, camera, render
from lastobs.util import frame_from_up


def parse_args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'the_last_observatory.blend'))
    ap.add_argument('--preview', default=None, help='render a preview still to this path')
    ap.add_argument('--frame', type=int, default=L.FRAMES)
    ap.add_argument('--res', type=float, default=0.5, help='preview resolution scale')
    ap.add_argument('--spp', type=int, default=32)
    ap.add_argument('--skip', default='', help='comma list: props,astronaut')
    return ap.parse_args(argv)


class Ground:
    """Ray-casts onto the evaluated planet so props sit on the terrain."""

    def __init__(self, planet_obj):
        dg = bpy.context.evaluated_depsgraph_get()
        ev = planet_obj.evaluated_get(dg)
        self.bvh = BVHTree.FromObject(ev, dg)

    def hit(self, direction):
        d = Vector(direction).normalized()
        loc, nrm, _, _ = self.bvh.ray_cast(d * (L.R + 6.0), -d)
        if loc is None:
            return d * L.R, d
        return loc, nrm


def tangent_toward(pos, up, target):
    v = Vector(target) - Vector(pos)
    v = v - up * v.dot(up)
    return v.normalized()


def main():
    args = parse_args()
    skip = set(filter(None, args.skip.split(',')))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = 'The Last Observatory'
    scene.render.fps = L.FPS
    scene.frame_start = 1
    scene.frame_end = L.FRAMES
    render.setup_render(scene)

    # --- Sites --------------------------------------------------------------
    obs_up = L.OBS_DIR
    obs_pos0 = obs_up * (L.R + 0.10)
    ast_pos0 = L.AST_DIR * L.R
    door_dir = tangent_toward(obs_pos0, obs_up, ast_pos0) + tangent_toward(obs_pos0, obs_up, obs_pos0 - L.F_C * 20)
    door_dir = (door_dir - obs_up * door_dir.dot(obs_up)).normalized()
    walk_a = (obs_pos0 + door_dir * 2.15).normalized() * L.R
    walk_b = (ast_pos0 - tangent_toward(ast_pos0, L.AST_DIR, walk_a) * -0.05)

    # keep-out points for scattering
    mask = []
    r_, f_, u_ = frame_from_up(obs_up, door_dir)
    mask.append(obs_pos0)
    for i in range(10):
        a = 2 * math.pi * i / 10
        mask.append(obs_pos0 + (r_ * math.cos(a) + f_ * math.sin(a)) * 1.25)
    for i in range(14):
        t = i / 13
        mask.append(((walk_a * (1 - t) + walk_b * t)).normalized() * L.R)
    for d in (L.MAST_DIR, L.DISH_DIR, L.SOLAR_DIR, L.CRATE_DIR):
        mask.append(d * L.R)

    world, sky_node = sky.build_world(scene)
    planet_obj, rocks = planet.build_planet(scene, walk_a, walk_b, mask, walk_b)
    ground = Ground(planet_obj)

    sites = dict(obs_up=obs_up, door_dir=door_dir, walk_a=walk_a, walk_b=walk_b)
    if 'props' not in skip:
        props.build_props(scene, ground, sites)
    ast = None
    if 'astronaut' not in skip:
        ast = astronaut.build_astronaut(scene, ground, sites)
    lighting.build_lights(scene)
    cam = camera.build_camera(scene, ast)
    render.setup_compositor(scene)

    scene.frame_set(args.frame)
    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print('saved', out)

    if args.preview:
        scene.render.resolution_percentage = int(args.res * 100)
        scene.cycles.samples = args.spp
        scene.render.filepath = os.path.abspath(args.preview)
        bpy.ops.render.render(write_still=True)
        print('preview', args.preview)


if __name__ == '__main__':
    main()
