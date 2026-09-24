"""Small helpers for building node trees, meshes and objects from Python."""

import math

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector


# ---------------------------------------------------------------------------
# Scene / object helpers
# ---------------------------------------------------------------------------

def collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def link(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def mesh_object(name, bm_or_mesh, col, mat=None, smooth=False):
    if isinstance(bm_or_mesh, bmesh.types.BMesh):
        me = bpy.data.meshes.new(name)
        bm_or_mesh.to_mesh(me)
        bm_or_mesh.free()
    else:
        me = bm_or_mesh
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    if mat is not None:
        me.materials.append(mat)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return obj


def empty(name, col, loc=(0, 0, 0), size=0.2, kind='PLAIN_AXES'):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = kind
    obj.empty_display_size = size
    obj.location = loc
    col.objects.link(obj)
    return obj


def add_mod(obj, kind, name=None, **props):
    mod = obj.modifiers.new(name or kind.title(), kind)
    for k, v in props.items():
        setattr(mod, k, v)
    return mod


def bevel(obj, width=0.01, segments=2, angle=35.0):
    return add_mod(obj, 'BEVEL', width=width, segments=segments,
                   limit_method='ANGLE', angle_limit=math.radians(angle),
                   harden_normals=False)


def subsurf(obj, levels=2, render=None):
    return add_mod(obj, 'SUBSURF', levels=levels,
                   render_levels=render if render is not None else levels)


def frame_from_up(up, forward_hint):
    """Orthonormal basis (right, forward, up) with 'up' exact and forward as
    close to forward_hint as possible."""
    up = Vector(up).normalized()
    f = Vector(forward_hint)
    f = (f - up * f.dot(up))
    if f.length < 1e-6:
        f = up.orthogonal()
    f.normalize()
    r = f.cross(up).normalized()
    return r, f, up


def basis_matrix(right, forward, up, loc=(0, 0, 0)):
    m = Matrix((
        (right.x, forward.x, up.x, loc[0]),
        (right.y, forward.y, up.y, loc[1]),
        (right.z, forward.z, up.z, loc[2]),
        (0, 0, 0, 1),
    ))
    return m


def place_on(obj, loc, up, forward_hint):
    r, f, u = frame_from_up(up, forward_hint)
    obj.matrix_world = basis_matrix(r, f, u, loc)
    return obj


def look_at_quat(forward, up):
    """Quaternion for a camera/light (looks down -Z, up is +Y)."""
    f = Vector(forward).normalized()
    u = Vector(up)
    r = f.cross(u).normalized()
    u = r.cross(f).normalized()
    m = Matrix(((r.x, u.x, -f.x), (r.y, u.y, -f.y), (r.z, u.z, -f.z)))
    return m.to_quaternion()


# ---------------------------------------------------------------------------
# bmesh primitives
# ---------------------------------------------------------------------------

def bm_cylinder(bm, p0, p1, r0, r1=None, segs=16, caps=True):
    """Tapered cylinder between two points, appended to bm."""
    r1 = r0 if r1 is None else r1
    p0, p1 = Vector(p0), Vector(p1)
    axis = p1 - p0
    length = axis.length
    if length < 1e-6:
        return
    z = axis / length
    x = z.orthogonal().normalized()
    y = z.cross(x)
    ring0, ring1 = [], []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        d = x * math.cos(a) + y * math.sin(a)
        ring0.append(bm.verts.new(p0 + d * r0))
        ring1.append(bm.verts.new(p1 + d * r1))
    for i in range(segs):
        j = (i + 1) % segs
        bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i]))
    if caps:
        bm.faces.new(list(reversed(ring0)))
        bm.faces.new(ring1)


def bm_box(bm, center, size, rot=None):
    c = Vector(center)
    sx, sy, sz = (s * 0.5 for s in size)
    corners = [Vector((x, y, z)) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
    if rot is not None:
        corners = [rot @ v for v in corners]
    vs = [bm.verts.new(c + v) for v in corners]
    idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    for f in idx:
        bm.faces.new([vs[i] for i in f])


def bm_torus(bm, center, axis, R, r, segs=32, rsegs=8):
    axis = Vector(axis).normalized()
    x = axis.orthogonal().normalized()
    y = axis.cross(x)
    c = Vector(center)
    rings = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        d = x * math.cos(a) + y * math.sin(a)
        ring = []
        for j in range(rsegs):
            b = 2 * math.pi * j / rsegs
            ring.append(bm.verts.new(c + d * (R + r * math.cos(b)) + axis * (r * math.sin(b))))
        rings.append(ring)
    for i in range(segs):
        i2 = (i + 1) % segs
        for j in range(rsegs):
            j2 = (j + 1) % rsegs
            bm.faces.new((rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2]))


# ---------------------------------------------------------------------------
# Node tree helpers
# ---------------------------------------------------------------------------

class NodeBuilder:
    """Terse node creation/linking for shader, geometry and compositor trees.

    Socket arguments may be sockets, nodes (first output is used) or plain
    values (assigned to the input's default_value)."""

    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links
        self._x = 0

    def _out(self, s):
        if isinstance(s, bpy.types.Node):
            for o in s.outputs:
                if o.enabled:
                    return o
            return s.outputs[0]
        return s

    def set_input(self, node, key, value):
        sock = None
        if isinstance(key, int):
            sock = node.inputs[key]
        else:
            # prefer enabled socket with that name (Mix/Math nodes have duplicates)
            for i in node.inputs:
                if (i.name == key or i.identifier == key) and i.enabled:
                    sock = i
                    break
            if sock is None:
                sock = node.inputs[key]
        if isinstance(value, (bpy.types.NodeSocket, bpy.types.Node)):
            self.links.new(self._out(value), sock)
        else:
            try:
                sock.default_value = value
            except (TypeError, ValueError):
                if hasattr(value, '__len__') and len(value) == 3 and len(sock.default_value) == 4:
                    sock.default_value = (*value, 1.0)
                else:
                    raise
        return sock

    def node(self, kind, inputs=None, loc=None, label=None, **props):
        n = self.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        if inputs:
            for k, v in inputs.items():
                self.set_input(n, k, v)
        if label:
            n.label = label
        self._x += 1
        n.location = loc if loc is not None else (self._x * 40 % 4000, -(self._x // 100) * 300)
        return n

    def link(self, a, b):
        self.links.new(self._out(a), b)

    # math ---------------------------------------------------------------
    def math(self, op, a, b=None, c=None, clamp=False):
        n = self.node('ShaderNodeMath', operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.set_input(n, i, v)
        return n.outputs[0]

    def add(self, a, b):
        return self.math('ADD', a, b)

    def sub(self, a, b):
        return self.math('SUBTRACT', a, b)

    def mul(self, a, b):
        return self.math('MULTIPLY', a, b)

    def div(self, a, b):
        return self.math('DIVIDE', a, b)

    def mad(self, a, b, c):
        return self.math('MULTIPLY_ADD', a, b, c)

    def vmath(self, op, a, b=None, c=None, scale=None):
        n = self.node('ShaderNodeVectorMath', operation=op)
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.set_input(n, i, v)
        if scale is not None:
            self.set_input(n, 'Scale', scale)
        if op in ('DOT_PRODUCT', 'LENGTH', 'DISTANCE'):
            return n.outputs['Value']
        return n.outputs['Vector']

    def smoothstep(self, e0, e1, x):
        n = self.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP')
        self.set_input(n, 'Value', x)
        self.set_input(n, 'From Min', e0)
        self.set_input(n, 'From Max', e1)
        return n.outputs['Result']

    def maprange(self, x, a, b, c, d, clamp=True):
        n = self.node('ShaderNodeMapRange', clamp=clamp)
        self.set_input(n, 'Value', x)
        self.set_input(n, 'From Min', a)
        self.set_input(n, 'From Max', b)
        self.set_input(n, 'To Min', c)
        self.set_input(n, 'To Max', d)
        return n.outputs['Result']

    def mix(self, fac, a, b, kind='RGBA', blend='MIX'):
        n = self.node('ShaderNodeMix', data_type=kind, blend_type=blend)
        self.set_input(n, 'Factor', fac)
        self.set_input(n, 'A', a)
        self.set_input(n, 'B', b)
        for o in n.outputs:
            if o.enabled:
                return o

    def combine(self, x, y, z):
        return self.node('ShaderNodeCombineXYZ', {'X': x, 'Y': y, 'Z': z}).outputs[0]

    def separate(self, v):
        n = self.node('ShaderNodeSeparateXYZ', {'Vector': v})
        return n.outputs['X'], n.outputs['Y'], n.outputs['Z']

    def noise(self, vec=None, scale=5.0, detail=2.0, rough=0.5, lac=2.0, dist=0.0,
              dims='3D', ntype='FBM', w=None, normalize=True):
        n = self.node('ShaderNodeTexNoise', noise_dimensions=dims, noise_type=ntype,
                      normalize=normalize)
        if vec is not None:
            self.set_input(n, 'Vector', vec)
        self.set_input(n, 'Scale', scale)
        self.set_input(n, 'Detail', detail)
        self.set_input(n, 'Roughness', rough)
        self.set_input(n, 'Lacunarity', lac)
        self.set_input(n, 'Distortion', dist)
        if w is not None:
            self.set_input(n, 'W', w)
        return n

    def voronoi(self, vec=None, scale=5.0, feature='F1', metric='EUCLIDEAN', rand=1.0,
                dims='3D', smooth=None):
        n = self.node('ShaderNodeTexVoronoi', voronoi_dimensions=dims, feature=feature,
                      distance=metric)
        if vec is not None:
            self.set_input(n, 'Vector', vec)
        self.set_input(n, 'Scale', scale)
        self.set_input(n, 'Randomness', rand)
        if smooth is not None:
            self.set_input(n, 'Smoothness', smooth)
        return n

    def ramp(self, fac, stops):
        """stops: list of (pos, (r,g,b[,a]))"""
        n = self.node('ShaderNodeValToRGB')
        self.set_input(n, 'Fac', fac)
        els = n.color_ramp.elements
        while len(els) > len(stops):
            els.remove(els[-1])
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position = pos
            el.color = (*col, 1.0) if len(col) == 3 else col
        return n.outputs['Color']


# ---------------------------------------------------------------------------
# Geometry node group helper
# ---------------------------------------------------------------------------

def new_geo_group(name, inputs=(), outputs=(('Geometry', 'NodeSocketGeometry'),)):
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    for sname, stype, *default in inputs:
        s = ng.interface.new_socket(sname, in_out='INPUT', socket_type=stype)
        if default:
            s.default_value = default[0]
    for sname, stype in outputs:
        ng.interface.new_socket(sname, in_out='OUTPUT', socket_type=stype)
    nb = NodeBuilder(ng)
    gin = nb.node('NodeGroupInput', loc=(-1400, 0))
    gout = nb.node('NodeGroupOutput', loc=(1400, 0))
    return ng, nb, gin, gout


def gn_modifier(obj, group, name=None, **inputs):
    mod = obj.modifiers.new(name or group.name, 'NODES')
    mod.node_group = group
    for key, value in inputs.items():
        ident = None
        for item in group.interface.items_tree:
            if getattr(item, 'in_out', None) == 'INPUT' and item.name == key:
                ident = item.identifier
        if ident is None:
            raise KeyError(key)
        props = getattr(mod, 'properties', None)
        if props is not None and hasattr(props, 'inputs'):
            getattr(props.inputs, ident).value = value      # Blender 5.x
        else:
            mod[ident] = value                              # Blender <= 4.x
    return mod


def new_material(name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    nb = NodeBuilder(nt)
    out = nb.node('ShaderNodeOutputMaterial', loc=(1200, 0))
    return mat, nb, out


def principled(nb, **inputs):
    mapping = {
        'base': 'Base Color', 'metal': 'Metallic', 'rough': 'Roughness',
        'normal': 'Normal', 'emit': 'Emission Color', 'emit_strength': 'Emission Strength',
        'coat': 'Coat Weight', 'coat_rough': 'Coat Roughness', 'sheen': 'Sheen Weight',
        'sheen_tint': 'Sheen Tint', 'spec': 'Specular IOR Level', 'ior': 'IOR',
        'trans': 'Transmission Weight', 'alpha': 'Alpha', 'sss': 'Subsurface Weight',
        'aniso': 'Anisotropic', 'thin_film': 'Thin Film Thickness',
    }
    n = nb.node('ShaderNodeBsdfPrincipled')
    for k, v in inputs.items():
        nb.set_input(n, mapping.get(k, k), v)
    return n


def emission(nb, color, strength):
    return nb.node('ShaderNodeEmission', {'Color': color, 'Strength': strength})
