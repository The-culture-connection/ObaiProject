import bpy
import os
from mathutils import Vector

# =========================
# CONFIGURATION
# =========================

MM_TO_M = 0.001
BASE_DIR = r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings"

MARKER_PATHS = {
    "1": os.path.join(BASE_DIR, "ArucoMarker1.png"),
    "2": os.path.join(BASE_DIR, "ArucoMarker2.png"),
    "3": os.path.join(BASE_DIR, "ArucoMarker3.png"),
    "4": os.path.join(BASE_DIR, "ArucoMarker4.png"),
    "5": os.path.join(BASE_DIR, "ArucoMarker5.png"),
    "6": os.path.join(BASE_DIR, "ArucoMarker6.png"),
    "7": os.path.join(BASE_DIR, "ArucoMarker7.png"),
    "8": os.path.join(BASE_DIR, "ArucoMarker8.png"),
}

EXPORT_PATH = os.path.join(BASE_DIR, "D9_Trihedral_DesignB_6x5.glb")

# Dimensions (mm) - defaults (can be overridden by dimensionsdoc file)
PANEL_W = 108.0
PANEL_H = 94.0
PANEL_THICK = 0.8
CHECKER_COLS = 6
CHECKER_ROWS = 5
SQUARE_SIZE = 14.0
MARGIN = 12.0
MARKER_SIZE = 10.5
EPS = 0.05  # air gap above surface for markers
CUTOUT_WIDTH = 20.0  # width of bottom cutout (mm)
CUTOUT_DEPTH = 10.0  # depth of bottom cutout (mm)
OVERLAP = 0.1  # small overlap at edges to ensure panels intersect (mm)

DIMENSIONS_FILE = os.path.join(os.path.dirname(__file__), "dimensionsdoc")

# =========================
# HELPER FUNCTIONS
# =========================

def mm(x):
    """Convert millimeters to meters."""
    return x * MM_TO_M

def parse_dimensions_file(path, defaults):
    """Parse key=value pairs from a dimensions file and override defaults."""
    if not os.path.exists(path):
        print(f"ℹ️ Dimensions file not found: {path} (using defaults)")
        return defaults

    updates = {}
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
            elif ":" in line:
                key, value = line.split(":", 1)
            else:
                continue
            key = key.strip().upper()
            value = value.strip()
            if key not in defaults:
                continue
            default_value = defaults[key]
            try:
                if isinstance(default_value, int):
                    updates[key] = int(float(value))
                else:
                    updates[key] = float(value)
            except ValueError:
                print(f"⚠️ Skipping invalid value for {key}: {value}")
    merged = {**defaults, **updates}
    return merged

def load_dimensions():
    """Load dimensions from dimensionsdoc and compute derived defaults."""
    defaults = {
        "PANEL_W": PANEL_W,
        "PANEL_H": PANEL_H,
        "PANEL_THICK": PANEL_THICK,
        "CHECKER_COLS": CHECKER_COLS,
        "CHECKER_ROWS": CHECKER_ROWS,
        "SQUARE_SIZE": SQUARE_SIZE,
        "MARGIN": MARGIN,
        "MARKER_SIZE": MARKER_SIZE,
        "EPS": EPS,
        "CUTOUT_WIDTH": CUTOUT_WIDTH,
        "CUTOUT_DEPTH": CUTOUT_DEPTH,
        "OVERLAP": OVERLAP,
    }
    merged = parse_dimensions_file(DIMENSIONS_FILE, defaults)

    active_w = merged["CHECKER_COLS"] * merged["SQUARE_SIZE"]
    active_h = merged["CHECKER_ROWS"] * merged["SQUARE_SIZE"]

    if "PANEL_W" not in merged or merged["PANEL_W"] <= 0:
        merged["PANEL_W"] = active_w + 2 * merged["MARGIN"]
    if "PANEL_H" not in merged or merged["PANEL_H"] <= 0:
        merged["PANEL_H"] = active_h + 2 * merged["MARGIN"]

    expected_w = active_w + 2 * merged["MARGIN"]
    expected_h = active_h + 2 * merged["MARGIN"]
    if abs(merged["PANEL_W"] - expected_w) > 0.1 or abs(merged["PANEL_H"] - expected_h) > 0.1:
        print(
            "⚠️ Panel size does not match checker area + margins. "
            f"Expected {expected_w:.2f}×{expected_h:.2f}mm, got {merged['PANEL_W']:.2f}×{merged['PANEL_H']:.2f}mm."
        )

    return merged

def ensure_object_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

def clear_scene():
    """Delete all objects in the scene."""
    ensure_object_mode()
    # Select all objects using direct API
    for obj in bpy.context.scene.objects:
        obj.select_set(True)
    # Delete selected objects
    bpy.ops.object.delete(use_global=False)
    # Clear unused materials
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)

def set_units_mm_display():
    s = bpy.context.scene
    s.unit_settings.system = 'METRIC'
    s.unit_settings.length_unit = 'MILLIMETERS'

# =========================
# MATERIALS
# =========================

def make_checker_image(name, cols, rows, px_per_square=256):
    """Create a crisp black/white checker image in Blender."""
    w = cols * px_per_square
    h = rows * px_per_square
    img = bpy.data.images.new(name, width=w, height=h, alpha=True, float_buffer=False)

    # RGBA pixels flat list
    pixels = [0.0] * (w * h * 4)

    for y in range(h):
        r = y // px_per_square
        for x in range(w):
            c = x // px_per_square
            black = ((r + c) % 2 == 0)
            i = (y * w + x) * 4
            if black:
                pixels[i:i+4] = [0.0, 0.0, 0.0, 1.0]
            else:
                pixels[i:i+4] = [1.0, 1.0, 1.0, 1.0]

    img.pixels = pixels
    img.pack()  # important: embed into .blend and exportable
    return img

def make_checker_material(name, checker_img, panel_w_mm, panel_h_mm):
    """
    Principled material with checkerboard texture in active area, white in margins.
    Uses UV-based mask to show checkerboard only in active area (84×70mm with 12mm margins).
    """
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    bsdf.inputs["Roughness"].default_value = 0.9
    if "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.02
    elif "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.02

    # Texture coordinate
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-400, 0)
    
    # Mapping node to scale/position checkerboard in active area
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-200, 0)
    mapping.vector_type = 'POINT'
    
    # Active area dimensions
    active_w = CHECKER_COLS * SQUARE_SIZE  # 84mm
    active_h = CHECKER_ROWS * SQUARE_SIZE  # 70mm
    
    # Scale texture to fit active area in UV space
    # Active area occupies (active_w/panel_w) of UV space
    scale_u = panel_w_mm / active_w  # Scale up texture to fill active area
    scale_v = panel_h_mm / active_h
    
    # Offset to position active area correctly
    # Active area starts at MARGIN, so offset by -MARGIN/active_size
    offset_u = -MARGIN / active_w
    offset_v = -MARGIN / active_h
    
    mapping.inputs["Scale"].default_value = (scale_u, scale_v, 1.0)
    mapping.inputs["Location"].default_value = (offset_u, offset_v, 0.0)

    # Checkerboard texture
    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (0, 0)
    tex.image = checker_img
    tex.interpolation = 'Closest'
    tex.extension = 'CLIP'  # Don't repeat, show transparent/black outside
    
    # Create UV mask: 1.0 in active area, 0.0 in margins
    separate_uv = nodes.new("ShaderNodeSeparateXYZ")
    separate_uv.location = (-200, -200)
    
    # Check if UV is within active area bounds
    margin_u_min = MARGIN / panel_w_mm
    margin_u_max = 1.0 - margin_u_min
    margin_v_min = MARGIN / panel_h_mm
    margin_v_max = 1.0 - margin_v_min
    
    # U coordinate checks
    u_greater = nodes.new("ShaderNodeMath")
    u_greater.location = (-50, -150)
    u_greater.operation = 'GREATER_THAN'
    u_greater.inputs[1].default_value = margin_u_min
    
    u_less = nodes.new("ShaderNodeMath")
    u_less.location = (-50, -250)
    u_less.operation = 'LESS_THAN'
    u_less.inputs[1].default_value = margin_u_max
    
    # V coordinate checks
    v_greater = nodes.new("ShaderNodeMath")
    v_greater.location = (-50, -350)
    v_greater.operation = 'GREATER_THAN'
    v_greater.inputs[1].default_value = margin_v_min
    
    v_less = nodes.new("ShaderNodeMath")
    v_less.location = (-50, -450)
    v_less.operation = 'LESS_THAN'
    v_less.inputs[1].default_value = margin_v_max
    
    # Combine: (u_ok AND v_ok)
    u_ok = nodes.new("ShaderNodeMath")
    u_ok.location = (100, -200)
    u_ok.operation = 'MULTIPLY'
    
    v_ok = nodes.new("ShaderNodeMath")
    v_ok.location = (100, -400)
    v_ok.operation = 'MULTIPLY'
    
    mask = nodes.new("ShaderNodeMath")
    mask.location = (250, -300)
    mask.operation = 'MULTIPLY'
    
    # Connect UV mask
    links.new(tex_coord.outputs["UV"], separate_uv.inputs["Vector"])
    links.new(separate_uv.outputs["X"], u_greater.inputs[0])
    links.new(separate_uv.outputs["X"], u_less.inputs[0])
    links.new(separate_uv.outputs["Y"], v_greater.inputs[0])
    links.new(separate_uv.outputs["Y"], v_less.inputs[0])
    
    links.new(u_greater.outputs["Value"], u_ok.inputs[0])
    links.new(u_less.outputs["Value"], u_ok.inputs[1])
    links.new(v_greater.outputs["Value"], v_ok.inputs[0])
    links.new(v_less.outputs["Value"], v_ok.inputs[1])
    links.new(u_ok.outputs["Value"], mask.inputs[0])
    links.new(v_ok.outputs["Value"], mask.inputs[1])
    
    # Mix white (margins) and checkerboard (active area)
    mix = nodes.new("ShaderNodeMixRGB")
    mix.location = (400, 0)
    mix.blend_type = 'MIX'
    
    # Connect everything
    links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    links.new(mask.outputs["Value"], mix.inputs["Fac"])
    mix.inputs["Color1"].default_value = (0.95, 0.95, 0.95, 1.0)  # White for margins
    links.new(tex.outputs["Color"], mix.inputs["Color2"])  # Checkerboard
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    
    return mat

def create_marker_material(marker_id, image_path):
    """Create material for ArUco marker."""
    name = f"Marker_{marker_id}"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)

    # Unlit emission is best for reading in simulators
    em = nodes.new("ShaderNodeEmission")
    em.location = (200, 0)
    em.inputs["Strength"].default_value = 1.0

    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (-150, 0)
    tex.interpolation = 'Closest'

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Missing marker image: {image_path}")

    img = bpy.data.images.load(image_path, check_existing=True)
    tex.image = img

    links.new(tex.outputs["Color"], em.inputs["Color"])
    links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat

def assign_material(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# =========================
# GEOMETRY BUILDERS
# =========================

def add_box_from_corner(name, corner_world: Vector, size_world: Vector, mat=None):
    """
    Create a box by specifying the MIN corner (corner_world) and full sizes (size_world),
    in Blender units (meters).
    IMPORTANT: cube size=1.0 is 2 units across, so scale is HALF-dimensions
    """
    ensure_object_mode()
    center = corner_world + (size_world * 0.5)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    obj = bpy.context.active_object
    obj.name = name

    # IMPORTANT: scale is HALF-EXTENTS when size=1.0
    obj.scale = (size_world.x * 0.5, size_world.y * 0.5, size_world.z * 0.5)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    if mat:
        assign_material(obj, mat)
    return obj

def add_floor():
    """
    Floor in XY, thickness in Z, with a cutout at the bottom (front edge) for folding.
    Extended slightly at back and right edges to overlap with walls.
    """
    ensure_object_mode()
    
    # Create main floor panel - extend slightly at back (y) and right (x) edges to overlap walls
    # Floor extends from (0,0,0) to (PANEL_W + OVERLAP, PANEL_H + OVERLAP, PANEL_THICK)
    corner = Vector((0, 0, 0))
    size = Vector((mm(PANEL_W + OVERLAP), mm(PANEL_H + OVERLAP), mm(PANEL_THICK)))
    floor = add_box_from_corner("Floor", corner, size)
    
    # Create cutout box to subtract (boolean difference)
    # Cutout is centered on the front edge (y=0), extends inward
    cutout_center_x = mm(PANEL_W / 2.0)  # Center of floor width
    cutout_center_y = mm(-CUTOUT_DEPTH / 2.0)  # Half depth into floor
    cutout_center_z = mm(PANEL_THICK / 2.0)  # Center of thickness
    
    cutout_corner = Vector((
        cutout_center_x - mm(CUTOUT_WIDTH / 2.0),
        -mm(CUTOUT_DEPTH),
        -mm(PANEL_THICK)  # Extend below floor to ensure clean cut
    ))
    cutout_size = Vector((
        mm(CUTOUT_WIDTH),
        mm(CUTOUT_DEPTH * 2),  # Make sure it cuts through
        mm(PANEL_THICK * 3)  # Make sure it cuts through
    ))
    
    cutout_box = add_box_from_corner("CutoutBox", cutout_corner, cutout_size)
    
    # Boolean difference to create cutout
    ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    floor.select_set(True)
    cutout_box.select_set(True)
    bpy.context.view_layer.objects.active = floor
    
    bpy.ops.object.modifier_add(type='BOOLEAN')
    floor.modifiers[-1].operation = 'DIFFERENCE'
    floor.modifiers[-1].object = cutout_box
    bpy.ops.object.modifier_apply(modifier=floor.modifiers[-1].name)
    
    # Delete the cutout box
    bpy.ops.object.select_all(action='DESELECT')
    cutout_box.select_set(True)
    bpy.ops.object.delete(use_global=False)
    
    return floor

def add_back_wall():
    """
    Back wall sits on TOP of the floor (z = PANEL_THICK)
    and is hinged along the floor's back edge at y = PANEL_H.
    Thickness goes outward in +Y, so the INSIDE face is at y = PANEL_H.
    Extended slightly at right edge (x) to overlap with right wall, and extends into floor.
    """
    # Inside face must be at y = PANEL_H, so panel extends from y = PANEL_H - OVERLAP to y = PANEL_H + PANEL_THICK
    # This makes the inside face (at y = PANEL_H - OVERLAP) align with y = PANEL_H after accounting for overlap
    # Actually: inside face is at the back (smaller y), so corner at y = PANEL_H - OVERLAP, 
    # and inside face is at y = PANEL_H - OVERLAP. But we want it at y = PANEL_H.
    # So: corner at y = PANEL_H, inside face at y = PANEL_H, panel extends to y = PANEL_H + PANEL_THICK + OVERLAP
    wall_z = max(0.0, PANEL_THICK - OVERLAP)
    corner = Vector((0, mm(PANEL_H), mm(wall_z)))  # Inside face at y = PANEL_H
    size = Vector((mm(PANEL_W + OVERLAP), mm(PANEL_THICK + OVERLAP), mm(PANEL_H + OVERLAP)))  # Extend in +Y/+X/+Z
    return add_box_from_corner("BackWall", corner, size)

def add_right_wall():
    """
    Right wall sits on TOP of the floor (z = PANEL_THICK)
    and is hinged along the floor's right edge at x = PANEL_W.
    Thickness goes outward in +X, so the INSIDE face is at x = PANEL_W.
    
    IMPORTANT:
    The wall edge touching the floor runs along Y, so that dimension should be PANEL_H (94),
    not PANEL_W (108). Height is PANEL_H (94).
    Extended slightly at back edge (y) to overlap with back wall, and extends into floor.
    """
    # Inside face must be at x = PANEL_W, so panel extends from x = PANEL_W to x = PANEL_W + PANEL_THICK + OVERLAP
    wall_z = max(0.0, PANEL_THICK - OVERLAP)
    corner = Vector((mm(PANEL_W), 0, mm(wall_z)))  # Inside face at x = PANEL_W
    size = Vector((mm(PANEL_THICK + OVERLAP), mm(PANEL_H + OVERLAP), mm(PANEL_H + OVERLAP)))  # Extend in +X/+Y/+Z
    return add_box_from_corner("RightWall", corner, size)

# =========================
# UV MAPPING
# =========================

def ensure_uv(obj):
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")

def set_face_uv_to_full(obj, face_selector_fn):
    """
    Sets UVs of selected face to full 0..1. Assumes box has separate faces.
    face_selector_fn(poly) returns True for the face we want.
    """
    ensure_uv(obj)
    uv = obj.data.uv_layers.active.data

    # Each polygon has loop indices. We set each loop's UV.
    for poly in obj.data.polygons:
        if not face_selector_fn(poly):
            continue

        # For a quad face, assign UVs in order.
        # The loop order is consistent for the face; we'll map them to a full square.
        uvs = [(0,0), (1,0), (1,1), (0,1)]
        for li, (u,v) in zip(poly.loop_indices, uvs):
            uv[li].uv = (u, v)
        return  # done once

def set_face_uv_to_active_area(obj, face_selector_fn, active_w_mm, active_h_mm, panel_w_mm, panel_h_mm):
    """
    Sets UVs so checkerboard texture only covers the active area (centered with margins).
    Maps the entire face to 0-1 UV, then we'll use a Mapping node to scale/offset the texture.
    """
    ensure_uv(obj)
    uv = obj.data.uv_layers.active.data
    
    # Calculate UV scale and offset for active area
    # Active area: starts at MARGIN, ends at MARGIN + active_size
    # UV mapping: map panel coordinates to 0-1, then texture will be scaled/offset
    margin_u = MARGIN / panel_w_mm
    margin_v = MARGIN / panel_h_mm
    scale_u = active_w_mm / panel_w_mm
    scale_v = active_h_mm / panel_h_mm
    
    for poly in obj.data.polygons:
        if not face_selector_fn(poly):
            continue
        
        # Get vertex positions in local space to determine mapping
        verts_local = [obj.data.vertices[vi].co for vi in poly.vertices]
        normal = Vector(poly.normal)
        
        # Determine coordinate axes based on face orientation
        if abs(normal.z) > 0.9:  # Floor (XY plane)
            coords = [(v.x, v.y) for v in verts_local]
            panel_min = (0, 0)
            panel_max = (mm(panel_w_mm), mm(panel_h_mm))
        elif abs(normal.y) > 0.9:  # Back wall (XZ plane)
            coords = [(v.x, v.z) for v in verts_local]
            panel_min = (0, mm(PANEL_THICK))
            panel_max = (mm(panel_w_mm), mm(PANEL_THICK + panel_h_mm))
        else:  # Right wall (YZ plane)
            coords = [(v.y, v.z) for v in verts_local]
            panel_min = (0, mm(PANEL_THICK))
            panel_max = (mm(panel_h_mm), mm(PANEL_THICK + panel_h_mm))
        
        # Find bounding box of face in panel coordinates
        u_coords = [c[0] for c in coords]
        v_coords = [c[1] for c in coords]
        face_u_min, face_u_max = min(u_coords), max(u_coords)
        face_v_min, face_v_max = min(v_coords), max(v_coords)
        
        # Map each vertex to UV space
        for li, vi in zip(poly.loop_indices, poly.vertices):
            vert = obj.data.vertices[vi].co
            if abs(normal.z) > 0.9:  # Floor
                u_panel = vert.x
                v_panel = vert.y
            elif abs(normal.y) > 0.9:  # Back wall
                u_panel = vert.x
                v_panel = vert.z
            else:  # Right wall
                u_panel = vert.y
                v_panel = vert.z
            
            # Normalize to 0-1 based on panel bounds
            u_norm = (u_panel - panel_min[0]) / (panel_max[0] - panel_min[0]) if panel_max[0] != panel_min[0] else 0.5
            v_norm = (v_panel - panel_min[1]) / (panel_max[1] - panel_min[1]) if panel_max[1] != panel_min[1] else 0.5
            
            # Map to active area: scale and offset
            u = margin_u + u_norm * scale_u
            v = margin_v + v_norm * scale_v
            uv[li].uv = (u, v)
        return  # done once

def create_white_laminate_material():
    """Create white laminate material for margins."""
    mat = bpy.data.materials.get("Laminate_White") or bpy.data.materials.new(name="Laminate_White")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    for n in list(nodes):
        nodes.remove(n)
    
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf.location = (0, 0)
    out.location = (400, 0)
    
    bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.45
    bsdf.inputs["Metallic"].default_value = 0.0
    try:
        bsdf.inputs["Specular"].default_value = 0.20
    except KeyError:
        try:
            bsdf.inputs["Specular IOR Level"].default_value = 0.20
        except KeyError:
            pass
    
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def apply_checker_to_inside_faces(floor, back, right, checker_mat_floor, checker_mat_back, checker_mat_right):
    """
    Apply checkerboard materials to inside faces.
    Materials already have mapping configured for active area positioning.
    """
    # Assign materials to panels
    if floor.data.materials:
        floor.data.materials[0] = checker_mat_floor
    else:
        floor.data.materials.append(checker_mat_floor)
    
    if back.data.materials:
        back.data.materials[0] = checker_mat_back
    else:
        back.data.materials.append(checker_mat_back)
    
    if right.data.materials:
        right.data.materials[0] = checker_mat_right
    else:
        right.data.materials.append(checker_mat_right)
    
    # Set UVs to full 0-1 (mapping node handles active area positioning)
    set_face_uv_to_full(floor, lambda p: Vector(p.normal).z > 0.9)
    set_face_uv_to_full(back, lambda p: Vector(p.normal).y < -0.9)
    set_face_uv_to_full(right, lambda p: Vector(p.normal).x < -0.9)

# =========================
# MARKERS
# =========================

def panel_point(panel_origin, normal_dir, u_mm, v_mm, face_offset_mm=0.0):
    """
    panel_origin is the MIN corner of the WALL VOLUME (or floor volume).
    u_mm, v_mm are in-plane coords measured from that origin corner.
    face_offset_mm moves OUT from the print face along the print normal.

    normal_dir:
      'Z' floor print face normal is +Z
      'Y' back wall print face normal is -Y (inside face at panel_origin.y)
      'X' right wall print face normal is -X (inside face at panel_origin.x)
    """
    u = mm(u_mm)
    v = mm(v_mm)
    off = mm(face_offset_mm)

    if normal_dir == 'Z':
        # Floor: inside/top face is at z = panel_origin.z + PANEL_THICK
        return panel_origin + Vector((u, v, mm(PANEL_THICK) + off))

    elif normal_dir == 'Y':
        # Back wall: inside face is at y = panel_origin.y (normal -Y)
        # u along X, v along Z, offset goes toward -Y
        return panel_origin + Vector((u, -off, v))

    else:  # 'X'
        # Right wall: inside face is at x = panel_origin.x (normal -X)
        # u along Y, v along Z, offset goes toward -X
        return panel_origin + Vector((-off, u, v))

def add_marker_plane(marker_id, image_path, center_point, normal_vector, size_mm):
    """Add ArUco marker as textured plane."""
    ensure_object_mode()

    mat = create_marker_material(marker_id, image_path)
    s = mm(size_mm)
    eps = mm(EPS)

    # Position plane at center + epsilon offset
    pos = center_point + normal_vector * eps

    # Create plane
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=pos)
    plane = bpy.context.active_object
    plane.name = f"MarkerPlane_{marker_id}"

    # Scale to size
    # IMPORTANT: plane size=1.0 is 2 units across, so scale is HALF-dimension
    plane.scale = (s * 0.5, s * 0.5, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Rotate to face normal
    z_up = Vector((0, 0, 1))
    if normal_vector.dot(z_up) < 0.99:
        rot_quat = z_up.rotation_difference(normal_vector)
        plane.rotation_euler = rot_quat.to_euler()
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

    # Set UVs to simple 0-1 mapping
    mesh = plane.data
    if mesh.uv_layers:
        uv_layer = mesh.uv_layers.active
        if len(uv_layer.data) >= 4:
            uv_layer.data[0].uv = (0.0, 0.0)
            uv_layer.data[1].uv = (1.0, 0.0)
            uv_layer.data[2].uv = (1.0, 1.0)
            uv_layer.data[3].uv = (0.0, 1.0)

    # Assign material
    if plane.data.materials:
        plane.data.materials[0] = mat
    else:
        plane.data.materials.append(mat)

    return plane

def corner_center(width_mm, height_mm, corner_label):
    """Return center position for a marker in a given corner (panel coordinates)."""
    inset = MARGIN + MARKER_SIZE / 2.0
    max_x = width_mm - inset
    max_y = height_mm - inset

    if corner_label == "BL":
        return inset, inset
    if corner_label == "BR":
        return max_x, inset
    if corner_label == "TL":
        return inset, max_y
    if corner_label == "TR":
        return max_x, max_y
    raise ValueError(f"Unknown corner label: {corner_label}")

def place_markers():
    """Place all ArUco markers on panels."""
    # Floor markers on +Z face
    floor_origin = Vector((0, 0, 0))
    floor_normal = Vector((0, 0, 1))

    floor_bl = corner_center(PANEL_W, PANEL_H, "BL")
    floor_br = corner_center(PANEL_W, PANEL_H, "BR")
    floor_tl = corner_center(PANEL_W, PANEL_H, "TL")

    add_marker_plane("8", MARKER_PATHS["8"],
        panel_point(floor_origin, 'Z', floor_bl[0], floor_bl[1]),
        floor_normal, MARKER_SIZE)

    add_marker_plane("6", MARKER_PATHS["6"],
        panel_point(floor_origin, 'Z', floor_br[0], floor_br[1]),
        floor_normal, MARKER_SIZE)

    add_marker_plane("7", MARKER_PATHS["7"],
        panel_point(floor_origin, 'Z', floor_tl[0], floor_tl[1]),
        floor_normal, MARKER_SIZE)

    # Back wall: inside face is at y = PANEL_H (original position, not affected by overlap)
    # Panel starts at y = PANEL_H - OVERLAP, but inside face is still at y = PANEL_H
    back_origin = Vector((0, mm(PANEL_H), mm(PANEL_THICK)))
    back_normal = Vector((0, -1, 0))

    back_bl = corner_center(PANEL_W, PANEL_H, "BL")
    back_br = corner_center(PANEL_W, PANEL_H, "BR")
    back_tl = corner_center(PANEL_W, PANEL_H, "TL")
    back_tr = corner_center(PANEL_W, PANEL_H, "TR")

    add_marker_plane("5", MARKER_PATHS["5"],
        panel_point(back_origin, 'Y', back_bl[0], back_bl[1]),
        back_normal, MARKER_SIZE)

    add_marker_plane("1", MARKER_PATHS["1"],
        panel_point(back_origin, 'Y', back_tl[0], back_tl[1]),
        back_normal, MARKER_SIZE)

    add_marker_plane("2", MARKER_PATHS["2"],
        panel_point(back_origin, 'Y', back_br[0], back_br[1]),
        back_normal, MARKER_SIZE)

    add_marker_plane("3", MARKER_PATHS["3"],
        panel_point(back_origin, 'Y', back_tr[0], back_tr[1]),
        back_normal, MARKER_SIZE)

    # Right wall: inside face is at x = PANEL_W (original position, not affected by overlap)
    # Panel starts at x = PANEL_W - OVERLAP, but inside face is still at x = PANEL_W
    right_origin = Vector((mm(PANEL_W), 0, mm(PANEL_THICK)))
    right_normal = Vector((-1, 0, 0))

    right_tr = corner_center(PANEL_H, PANEL_H, "TR")

    add_marker_plane("4", MARKER_PATHS["4"],
        panel_point(right_origin, 'X', right_tr[0], right_tr[1]),
        right_normal, MARKER_SIZE)

# =========================
# EXPORT
# =========================

def export_glb(path):
    ensure_object_mode()
    export_dir = os.path.dirname(path)
    if export_dir and not os.path.exists(export_dir):
        os.makedirs(export_dir, exist_ok=True)

    kwargs = {
        'filepath': path,
        'export_format': 'GLB',
        'export_yup': True,
    }

    # Blender <5 had export_images option; GLB embeds anyway, but keep compatibility
    if bpy.app.version[0] < 5:
        kwargs['export_images'] = 'EMBEDDED'

    bpy.ops.export_scene.gltf(**kwargs)
    print(f"✅ Exported GLB: {path}")

def set_viewport_to_material_preview():
    """Switch viewport to Material Preview mode to see textures clearly."""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'
                    space.shading.color_type = 'TEXTURE'

# =========================
# MAIN
# =========================

def main():
    global PANEL_W, PANEL_H, PANEL_THICK, CHECKER_COLS, CHECKER_ROWS
    global SQUARE_SIZE, MARGIN, MARKER_SIZE, EPS, CUTOUT_WIDTH, CUTOUT_DEPTH, OVERLAP

    dims = load_dimensions()
    PANEL_W = dims["PANEL_W"]
    PANEL_H = dims["PANEL_H"]
    PANEL_THICK = dims["PANEL_THICK"]
    CHECKER_COLS = dims["CHECKER_COLS"]
    CHECKER_ROWS = dims["CHECKER_ROWS"]
    SQUARE_SIZE = dims["SQUARE_SIZE"]
    MARGIN = dims["MARGIN"]
    MARKER_SIZE = dims["MARKER_SIZE"]
    EPS = dims["EPS"]
    CUTOUT_WIDTH = dims["CUTOUT_WIDTH"]
    CUTOUT_DEPTH = dims["CUTOUT_DEPTH"]
    OVERLAP = dims["OVERLAP"]

    # Validate marker files
    missing = [p for p in MARKER_PATHS.values() if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError("Missing marker PNG(s):\n" + "\n".join(missing))

    clear_scene()
    set_units_mm_display()

    # Build panels
    floor = add_floor()
    back = add_back_wall()
    right = add_right_wall()

    # Create materials
    checker_img = make_checker_image("Checker_6x5", CHECKER_COLS, CHECKER_ROWS, px_per_square=256)
    
    # Create checker materials with proper mapping for each panel
    checker_mat_floor = make_checker_material("CheckerMat_Floor", checker_img, PANEL_W, PANEL_H)
    checker_mat_back = make_checker_material("CheckerMat_Back", checker_img, PANEL_W, PANEL_H)
    checker_mat_right = make_checker_material("CheckerMat_Right", checker_img, PANEL_H, PANEL_H)  # Right wall is 94×94

    # Apply checker texture to INSIDE faces (active area only, margins stay white)
    apply_checker_to_inside_faces(floor, back, right, checker_mat_floor, checker_mat_back, checker_mat_right)

    # Place ArUco marker planes
    place_markers()

    # Set viewport to Material Preview to see textures
    set_viewport_to_material_preview()

    # Export
    export_glb(EXPORT_PATH)

if __name__ == "__main__":
    main()
