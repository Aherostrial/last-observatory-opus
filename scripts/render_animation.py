"""Render the 6 second pull-back as a PNG sequence, then encode an MP4.

    python scripts/render_animation.py -- [--res 1280x720] [--spp 32]
        [--frames 1-144] [--outdir renders/frames] [--encode renders/the_last_observatory.mp4]

Frames that already exist are skipped, so an interrupted render resumes.
Encoding uses ffmpeg from PATH or the imageio-ffmpeg wheel.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))


def ffmpeg_exe():
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def encode(outdir, mp4, fps):
    exe = ffmpeg_exe()
    if not exe:
        print('ffmpeg not found; PNG sequence left in', outdir)
        return
    cmd = [exe, '-y', '-framerate', str(fps), '-start_number', '1',
           '-i', os.path.join(outdir, 'frame_%04d.png'),
           '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', mp4]
    subprocess.run(cmd, check=True)
    print('encoded', mp4)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', default=os.path.join(ROOT, 'the_last_observatory.blend'))
    ap.add_argument('--outdir', default=os.path.join(ROOT, 'renders', 'frames'))
    ap.add_argument('--encode', default=os.path.join(ROOT, 'renders', 'the_last_observatory.mp4'))
    ap.add_argument('--res', default='1280x720')
    ap.add_argument('--spp', type=int, default=32)
    ap.add_argument('--frames', default=None, help='e.g. 1-144')
    ap.add_argument('--no-encode', action='store_true')
    a = ap.parse_args(argv)

    if os.path.abspath(bpy.data.filepath or '') != os.path.abspath(a.blend):
        bpy.ops.wm.open_mainfile(filepath=a.blend)
    sc = bpy.context.scene
    w, h = (int(x) for x in a.res.lower().split('x'))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.compositor_device = 'CPU'
    sc.render.use_persistent_data = True
    cy = sc.cycles
    cy.samples = a.spp
    cy.adaptive_threshold = 0.03
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 6, 2, 2
    cy.use_animated_seed = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_depth = '8'

    f0, f1 = sc.frame_start, sc.frame_end
    if a.frames:
        f0, f1 = (int(x) for x in a.frames.split('-'))
    os.makedirs(a.outdir, exist_ok=True)
    t_all = time.time()
    for f in range(f0, f1 + 1):
        path = os.path.join(a.outdir, f'frame_{f:04d}.png')
        if os.path.exists(path):
            continue
        t = time.time()
        sc.frame_set(f)
        sc.render.filepath = path + '.tmp.png'
        bpy.ops.render.render(write_still=True)
        os.replace(path + '.tmp.png', path)
        print(f'frame {f} done in {time.time() - t:.1f}s', flush=True)
    print(f'all frames in {time.time() - t_all:.0f}s')
    if not a.no_encode:
        encode(a.outdir, a.encode, sc.render.fps)


if __name__ == '__main__':
    main()
