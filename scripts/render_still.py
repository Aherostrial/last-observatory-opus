"""Render the hero still (the final, fully revealed frame).

    python scripts/render_still.py -- [--blend the_last_observatory.blend]
        [--out renders/the_last_observatory_still.png] [--res 2560x1440] [--spp 384]
    blender -b the_last_observatory.blend -P scripts/render_still.py -- ...
"""

import argparse
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', default=os.path.join(ROOT, 'the_last_observatory.blend'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'renders', 'the_last_observatory_still.png'))
    ap.add_argument('--res', default='2560x1440')
    ap.add_argument('--spp', type=int, default=384)
    ap.add_argument('--frame', type=int, default=None, help='defaults to the last frame')
    a = ap.parse_args(argv)

    if os.path.abspath(bpy.data.filepath or '') != os.path.abspath(a.blend):
        bpy.ops.wm.open_mainfile(filepath=a.blend)
    sc = bpy.context.scene
    w, h = (int(x) for x in a.res.lower().split('x'))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.compositor_device = 'CPU'
    sc.render.use_motion_blur = False          # crisp hero frame
    cy = sc.cycles
    cy.samples = a.spp
    cy.adaptive_threshold = 0.008
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 8, 3, 4
    sc.frame_set(a.frame if a.frame is not None else sc.frame_end)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sc.render.filepath = a.out
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_depth = '16'
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print(f'still written to {a.out} in {time.time() - t:.0f}s')


if __name__ == '__main__':
    main()
