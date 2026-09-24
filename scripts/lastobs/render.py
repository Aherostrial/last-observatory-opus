"""Render + colour management + compositor."""

import bpy

from . import layout as L
from .util import NodeBuilder


def setup_render(scene):
    scene.render.engine = 'CYCLES'
    cy = scene.cycles
    cy.device = 'CPU'
    cy.shading_system = True            # OSL: the black hole sky is an OSL shader
    cy.samples = 256
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.015
    cy.use_denoising = True
    cy.denoiser = 'OPENIMAGEDENOISE'
    cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    cy.denoising_prefilter = 'ACCURATE'
    cy.max_bounces = 8
    cy.diffuse_bounces = 3
    cy.glossy_bounces = 4
    cy.transmission_bounces = 6
    cy.volume_bounces = 0
    cy.transparent_max_bounces = 8
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = 6.0
    cy.blur_glossy = 1.0
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.film_exposure = 1.0
    cy.pixel_filter_type = 'BLACKMAN_HARRIS'
    cy.filter_width = 1.5
    cy.seed = 0
    cy.use_animated_seed = True

    r = scene.render
    r.resolution_x, r.resolution_y = L.RES
    r.resolution_percentage = 100
    r.use_persistent_data = True
    r.use_motion_blur = True
    r.motion_blur_shutter = 0.4
    r.compositor_device = 'CPU'          # headless: no GPU context available
    r.compositor_denoise_device = 'CPU'
    r.compositor_precision = 'FULL'
    r.film_transparent = False
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_depth = '16'

    vs = scene.view_settings
    vs.view_transform = 'AgX'
    for look in ('AgX - Medium High Contrast', 'Medium High Contrast', 'AgX - Punchy'):
        try:
            vs.look = look
            break
        except TypeError:
            continue
    vs.exposure = 0.0
    vs.gamma = 1.0
    scene.display_settings.display_device = 'sRGB'


def _find(node, name, outputs=False, kind=None):
    socks = node.outputs if outputs else node.inputs
    for s in socks:
        if s.name == name and s.enabled and (kind is None or kind in s.bl_idname):
            return s
    return None


def _set(node, name, value, kind=None):
    s = _find(node, name, kind=kind)
    if s is None:
        raise KeyError(f'{node.bl_idname}: no input {name!r}')
    s.default_value = value


def setup_compositor(scene):
    ng = bpy.data.node_groups.new('LastObservatoryComp', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    scene.compositing_node_group = ng
    nb = NodeBuilder(ng)
    rl = nb.node('CompositorNodeRLayers', loc=(-900, 0))

    # Bloom around the accretion disk and the practical lights.
    glare = nb.node('CompositorNodeGlare', loc=(-600, 0))
    nb.link(rl.outputs['Image'], glare.inputs['Image'])
    _set(glare, 'Type', 'Bloom')
    _set(glare, 'Quality', 'High')
    _set(glare, 'Threshold', 1.0)
    _set(glare, 'Smoothness', 0.35)
    _set(glare, 'Strength', 0.30)
    _set(glare, 'Size', 0.65)

    # Very subtle lens dispersion.
    lens = nb.node('CompositorNodeLensdist', loc=(-350, 0))
    nb.link(glare.outputs['Image'], lens.inputs['Image'])
    _set(lens, 'Distortion', -0.004)
    _set(lens, 'Dispersion', 0.012)
    _set(lens, 'Fit', True)

    # Vignette: soft ellipse, remapped so corners darken but never crush.
    mask = nb.node('CompositorNodeEllipseMask', loc=(-350, -300))
    _set(mask, 'Size', (0.95, 0.80))
    blur = nb.node('CompositorNodeBlur', loc=(-150, -300))
    nb.link(mask.outputs['Mask'], blur.inputs['Image'])
    _set(blur, 'Size', (420.0, 420.0))
    mr = nb.node('ShaderNodeMapRange', loc=(0, -300))
    nb.link(blur.outputs['Image'], _find(mr, 'Value'))
    _find(mr, 'To Min').default_value = 0.42
    vig = nb.node('ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY', loc=(100, 0))
    _find(vig, 'Factor').default_value = 1.0
    nb.link(lens.outputs['Image'], _find(vig, 'A', kind='Color'))
    nb.link(_find(mr, 'Result', outputs=True), _find(vig, 'B', kind='Color'))

    # Gentle grade: shadows toward blue, highlights warm.
    cb = nb.node('CompositorNodeColorBalance', loc=(350, 0))
    nb.link(_find(vig, 'Result', outputs=True, kind='Color'), cb.inputs['Image'])
    _set(cb, 'Lift', (0.985, 1.0, 1.035, 1.0), kind='Color')
    _set(cb, 'Gain', (1.03, 1.0, 0.965, 1.0), kind='Color')

    out = nb.node('NodeGroupOutput', loc=(650, 0))
    nb.link(cb.outputs['Image'], out.inputs['Image'])
    view = nb.node('CompositorNodeViewer', loc=(650, -200))
    nb.link(cb.outputs['Image'], view.inputs['Image'])
    return ng
