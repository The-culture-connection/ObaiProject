import bpy
import math
from mathutils import Vector, Euler

# =========================
# USER SETTINGS (EDIT THESE)
# =========================

EXPORT_GLB_PATH = r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\D9_Trihedral_WithMarkers.glb"

# Your actual marker files + IDs
MARKER_PATHS = {
    "1": r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\ArucoMarker1.png",
    "2": r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\ArucoMarker2.png",
    "3": r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\ArucoMarker3.png",
    "4": r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\ArucoMarker4.png",
    "5": r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\ArucoMarker5.png",
    "6": r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\ArucoMarker6.png",
    "7": r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\ArucoMarker7.png",
    "8": r"C:\Users\grace\OneDrive - University of Cincinnati\Documents\Obai Project\AutoCad Drawings\ArucoMarker8.png",
}

MARKER_SIZE_MM = 10.5
MARKER_EPS_MM  = 0.05          # lift off surface to avoid z-fighting
SMALL_PART_MAX_EXTENT_MM = 25.0

# =========================
# HELPERS
# =========================

def set_scene_units_mm():
    s = bpy.context.scene
    s.unit_settings.system = 'METRIC'
    s.unit_settings.length_unit = 'MILLIMETERS'

def ensure_object_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

def apply_all_transforms(obj):
    ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

def create_laminate_material(name, base_color, roughness, specular):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # keep output, clear others
    for n in list(nodes):
        if n.type != 'OUTPUT_MATERIAL':
            nodes.remove(n)

    out = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    
    # Handle Blender version differences: 4.0+ uses "Specular IOR Level" instead of "Specular"
    if "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = specular
    elif "Specular IOR Level" in bsdf.inputs:
        # Convert specular to IOR level (approximate conversion)
        bsdf.inputs["Specular IOR Level"].default_value = specular
    
    bsdf.inputs["Metallic"].default_value = 0.0

    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def create_marker_material(marker_id, image_path):
    name = f"Marker_{marker_id}"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # ensure principled + output exist
    bsdf = nodes.get("Principled BSDF") or nodes.new("ShaderNodeBsdfPrincipled")
    out  = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")

    bsdf.inputs["Roughness"].default_value = 0.35
    
    # Handle Blender version differences: 4.0+ uses "Specular IOR Level" instead of "Specular"
    if "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.40
    elif "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.40
    
    bsdf.inputs["Metallic"].default_value = 0.0

    tex = nodes.get("MarkerImage")
    if tex is None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.name = "MarkerImage"
        tex.label = "MarkerImage"
        tex.location = (-450, 0)

    try:
        img = bpy.data.images.load(image_path, check_existing=True)
    except Exception as e:
        raise RuntimeError(f"Could not load marker image: {image_path}\n{e}")

    tex.image = img
    tex.interpolation = 'Closest'  # keep marker crisp

    # connect image->base color (remove old links first)
    for l in list(links):
        if l.to_node == bsdf and l.to_socket.name == "Base Color":
            links.remove(l)

    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def get_world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    mx = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return corners, mn, mx

def guess_panel_normal_axis(obj):
    _, mn, mx = get_world_bbox(obj)
    ext = mx - mn
    axes = [('X', ext.x), ('Y', ext.y), ('Z', ext.z)]
    axes.sort(key=lambda t: t[1])   # smallest extent = thickness axis
    return axes[0][0]

def normal_vector_from_axis(axis, outward=True):
    if axis == 'X':
        return Vector((1,0,0)) if outward else Vector((-1,0,0))
    if axis == 'Y':
        return Vector((0,1,0)) if outward else Vector((0,-1,0))
    return Vector((0,0,1)) if outward else Vector((0,0,-1))

def plane_rotation_from_normal(n: Vector):
    n = n.normalized()
    z = Vector((0,0,1))
    q = z.rotation_difference(n)
    return q.to_euler()

def make_marker_plane(marker_id, location, normal_world, size_mm):
    mat = create_marker_material(marker_id, MARKER_PATHS[marker_id])

    bpy.ops.mesh.primitive_plane_add(size=1.0, location=location)
    plane = bpy.context.active_object
    plane.name = f"MarkerPlane_{marker_id}"

    size_m = size_mm / 1000.0
    plane.scale = (size_m/2.0, size_m/2.0, 1.0)
    apply_all_transforms(plane)

    plane.rotation_euler = plane_rotation_from_normal(normal_world)
    apply_all_transforms(plane)

    # UV unwrap (simple planar)
    ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    plane.select_set(True)
    bpy.context.view_layer.objects.active = plane
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.project_from_view(orthographic=True)
    bpy.ops.object.mode_set(mode='OBJECT')

    if plane.data.materials:
        plane.data.materials[0] = mat
    else:
        plane.data.materials.append(mat)

    return plane

def separate_loose_parts(obj):
    ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    return [o for o in bpy.context.selected_objects if o.type == 'MESH']

def assign_material_by_size(objects, mat_white, mat_black):
    for o in objects:
        _, mn, mx = get_world_bbox(o)
        ext = mx - mn
        ext_mm = Vector((ext.x*1000, ext.y*1000, ext.z*1000))
        max_extent = max(ext_mm.x, ext_mm.y, ext_mm.z)
        mat = mat_black if max_extent <= SMALL_PART_MAX_EXTENT_MM else mat_white
        if o.data.materials:
            o.data.materials[0] = mat
        else:
            o.data.materials.append(mat)

def bbox_volume(o):
    _, mn, mx = get_world_bbox(o)
    ext = mx - mn
    return ext.x * ext.y * ext.z

def pick_floor_and_walls(panels):
    # floor = panel with smallest extent along Z (thin axis Z) AND largest area in XY-ish
    # in practice: panel whose normal axis is Z
    floor = None
    walls = []
    for p in panels:
        if guess_panel_normal_axis(p) == 'Z' and floor is None:
            floor = p
        else:
            walls.append(p)
    if floor is None:
        floor = panels[0]
        walls = panels[1:]
    return floor, walls

def panel_corners_for_face(panel_obj, normal_axis, use_max_side=True):
    """
    Return 4 corners on the 'outer' face.
    For a panel with thickness axis=normal_axis, the 'outer' face can be
    either min or max on that axis. We choose max if use_max_side else min.
    """
    _, mn, mx = get_world_bbox(panel_obj)

    if normal_axis == 'Z':
        z = mx.z if use_max_side else mn.z
        return {
            "BL": Vector((mn.x, mn.y, z)),
            "BR": Vector((mx.x, mn.y, z)),
            "TL": Vector((mn.x, mx.y, z)),
            "TR": Vector((mx.x, mx.y, z)),
        }
    if normal_axis == 'X':
        x = mx.x if use_max_side else mn.x
        return {
            "BL": Vector((x, mn.y, mn.z)),
            "BR": Vector((x, mx.y, mn.z)),
            "TL": Vector((x, mn.y, mx.z)),
            "TR": Vector((x, mx.y, mx.z)),
        }
    # Y
    y = mx.y if use_max_side else mn.y
    return {
        "BL": Vector((mn.x, y, mn.z)),
        "BR": Vector((mx.x, y, mn.z)),
        "TL": Vector((mn.x, y, mx.z)),
        "TR": Vector((mx.x, y, mx.z)),
    }

# =========================
# MAIN
# =========================

def main():
    set_scene_units_mm()
    ensure_object_mode()

    sel = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not sel:
        raise RuntimeError("Select your imported model mesh object first, then Run Script.")
    base = sel[0]

    apply_all_transforms(base)

    # Laminate materials
    laminate_white = create_laminate_material(
        "Laminate_White",
        base_color=(0.95, 0.95, 0.95, 1.0),
        roughness=0.45,
        specular=0.35
    )
    laminate_black = create_laminate_material(
        "Laminate_Black",
        base_color=(0.03, 0.03, 0.03, 1.0),
        roughness=0.55,
        specular=0.30
    )

    # Separate parts -> material by size
    parts = separate_loose_parts(base)
    assign_material_by_size(parts, laminate_white, laminate_black)

    # Find 3 biggest panels
    parts_sorted = sorted(parts, key=bbox_volume, reverse=True)
    panels = parts_sorted[:3]
    floor, walls = pick_floor_and_walls(panels)

    # Decide which wall is "left" vs "right" by their X center
    def center_x(o):
        _, mn, mx = get_world_bbox(o)
        return (mn.x + mx.x) / 2.0
    walls = sorted(walls, key=center_x)

    left_wall  = walls[0] if len(walls) > 0 else None
    right_wall = walls[1] if len(walls) > 1 else None

    eps_m = MARKER_EPS_MM / 1000.0

    # -------------------------------
    # PLACE MARKERS BY YOUR MAP
    # -------------------------------

    # FLOOR markers: 6 (front-right), 8 (front-left), 7 (inner-ish)
    # We'll place 6 at BR, 8 at BL on the "top" face of floor.
    floor_axis = guess_panel_normal_axis(floor)
    floor_n = normal_vector_from_axis(floor_axis, outward=True)
    floor_corners = panel_corners_for_face(floor, floor_axis, use_max_side=True)

    make_marker_plane("6", floor_corners["BR"] + floor_n * eps_m, floor_n, MARKER_SIZE_MM)
    make_marker_plane("8", floor_corners["BL"] + floor_n * eps_m, floor_n, MARKER_SIZE_MM)

    # Marker 7: place near inner corner (toward hinge). Use TL corner as a reasonable default.
    make_marker_plane("7", floor_corners["TL"] + floor_n * eps_m, floor_n, MARKER_SIZE_MM)

    # LEFT WALL: 1 top-left, 5 bottom-left
    if left_wall:
        ax = guess_panel_normal_axis(left_wall)
        n  = normal_vector_from_axis(ax, outward=True)
        c  = panel_corners_for_face(left_wall, ax, use_max_side=True)
        make_marker_plane("1", c["TL"] + n * eps_m, n, MARKER_SIZE_MM)
        make_marker_plane("5", c["BL"] + n * eps_m, n, MARKER_SIZE_MM)

    # RIGHT WALL: 4 top-right
    if right_wall:
        ax = guess_panel_normal_axis(right_wall)
        n  = normal_vector_from_axis(ax, outward=True)
        c  = panel_corners_for_face(right_wall, ax, use_max_side=True)
        make_marker_plane("4", c["TR"] + n * eps_m, n, MARKER_SIZE_MM)

    # SPINE markers (2 mid spine, 3 top spine)
    # We’ll attach these to the wall that is closest to the hinge line by using its "inner" corners.
    # Use left wall TR as spine-ish; use right wall TL as spine-ish.
    # If you prefer both on the same wall face, tell me and I’ll lock it.
    if left_wall:
        ax = guess_panel_normal_axis(left_wall)
        n  = normal_vector_from_axis(ax, outward=True)
        c  = panel_corners_for_face(left_wall, ax, use_max_side=True)
        # 3 at top spine (use TR)
        make_marker_plane("3", c["TR"] + n * eps_m, n, MARKER_SIZE_MM)
        # 2 at mid spine: move halfway down from TR toward BR
        mid = (c["TR"] + c["BR"]) * 0.5
        make_marker_plane("2", mid + n * eps_m, n, MARKER_SIZE_MM)

    # If any marker planes ended up on the INSIDE of a wall, flip by changing use_max_side=False above.
    # (You’ll know because the marker will be between panels.)

    # Export GLB with embedded images
    bpy.ops.export_scene.gltf(
        filepath=EXPORT_GLB_PATH,
        export_format='GLB',
        export_images='EMBEDDED',
        export_yup=True
    )

    print(f"✅ Exported GLB with laminate + markers: {EXPORT_GLB_PATH}")

# Auto-run when script is executed
if __name__ == "__main__":
    main()
