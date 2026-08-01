"""
maya_surface_contact.py

Live surface contact solver for feet, hands, and other controls that should
stay clamped to a selected mesh surface while the scene plays.
"""

from __future__ import absolute_import, division, print_function

import json
import math
import os
import time
import uuid

import maya_contact_hold as hold_utils

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    import maya.utils as maya_utils

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    maya_utils = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtCore, QtGui, QtWidgets

    QT_BINDING = "PySide6"
except Exception:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets

        QT_BINDING = "PySide2"
    except Exception:
        QtCore = None
        QtGui = None
        QtWidgets = None
        QT_BINDING = None


WINDOW_OBJECT_NAME = "mayaSurfaceContactWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
SURFACE_CONTACT_GROUP_NAME = "amirSurfaceContact_GRP"
SURFACE_CONTACT_MARKER_ATTR = "amirSurfaceContactMarker"
SURFACE_CONTACT_ENABLED_ATTR = "amirSurfaceContactEnabled"
SURFACE_CONTACT_CONTROL_ATTR = "surfaceContactControl"
SURFACE_CONTACT_SURFACE_ATTR = "surfaceContactSurface"
SURFACE_CONTACT_DATA_ATTR = "surfaceContactData"
DEFAULT_FOLLOW_NORMAL = True
# Surface Contact keeps its historical normal-follow behaviour.  The mesh
# collision contract uses separate, explicit defaults so a zero-sized proxy
# does not invent a foot/hand volume or rotate a control behind the animator's
# back.
LIVE_MESH_COLLISION_MODE = "live_mesh_collision"
SURFACE_CONTACT_MODE = "surface_contact"
DEFAULT_COLLISION_OFFSET = 0.0
DEFAULT_COLLISION_RADIUS = 0.0
DEFAULT_COLLISION_FOLLOW_NORMAL = False
COLLISION_EPSILON = 1.0e-6
COLLISION_MAX_ITERATIONS = 8
LIVE_SOLVE_DELAY_MS = 100

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None

_qt_flag = hold_utils._qt_flag
_style_donate_button = hold_utils._style_donate_button
_open_external_url = hold_utils._open_external_url
_maya_main_window = hold_utils._maya_main_window
_dedupe_preserve_order = hold_utils._dedupe_preserve_order
_short_name = hold_utils._short_name
_node_long_name = hold_utils._node_long_name
_selected_controls = hold_utils._selected_controls


# ---------------------------------------------------------------------------
# Maya-free collision core
# ---------------------------------------------------------------------------
# These helpers intentionally operate on ordinary tuples/dicts.  They are
# useful to tests and to callers that already have a mesh query result, and
# they keep the actual collision policy independent from Maya API objects.


def _collision_point(value):
    """Return a finite 3-tuple without requiring maya.api.OpenMaya."""
    try:
        values = list(value)
        if len(values) < 3:
            raise ValueError
        result = (float(values[0]), float(values[1]), float(values[2]))
    except Exception:
        return (0.0, 0.0, 0.0)
    if not all(math.isfinite(item) for item in result):
        return (0.0, 0.0, 0.0)
    return result


def _collision_sub(a, b):
    a = _collision_point(a)
    b = _collision_point(b)
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _collision_add(a, b):
    a = _collision_point(a)
    b = _collision_point(b)
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _collision_scale(value, scale):
    value = _collision_point(value)
    scale = float(scale)
    return (value[0] * scale, value[1] * scale, value[2] * scale)


def _collision_dot(a, b):
    a = _collision_point(a)
    b = _collision_point(b)
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _collision_length(value):
    return math.sqrt(max(0.0, _collision_dot(value, value)))


def _collision_normal(value, fallback=(0.0, 1.0, 0.0)):
    value = _collision_point(value)
    length = _collision_length(value)
    if length <= COLLISION_EPSILON:
        value = _collision_point(fallback)
        length = _collision_length(value)
    if length <= COLLISION_EPSILON:
        return (0.0, 1.0, 0.0)
    return _collision_scale(value, 1.0 / length)


def _collision_outward_normal(normal, closest_point, query_point, inside=False):
    """Return the shortest geometric direction away from a closed mesh."""
    normal = _collision_normal(normal)
    if inside:
        hint = _collision_sub(closest_point, query_point)
    else:
        hint = _collision_sub(query_point, closest_point)
    if _collision_length(hint) > COLLISION_EPSILON:
        normal = _collision_normal(hint, fallback=normal)
    return normal


def _collision_unique_parameters(values, tolerance=1.0e-5):
    unique = []
    for value in sorted(float(item) for item in values):
        if not unique or abs(value - unique[-1]) > float(tolerance):
            unique.append(value)
    return unique


def _collision_close(a, b, epsilon=COLLISION_EPSILON):
    return _collision_length(_collision_sub(a, b)) <= float(epsilon)


def segment_plane_intersection(start, end, plane_point, plane_normal, epsilon=COLLISION_EPSILON):
    """Return the first segment/plane hit as ``{point, normal, t}``.

    ``None`` means the finite segment does not cross the plane.  This helper
    deliberately does not treat a coplanar segment as a hit; the caller can
    then use the normal-side test for the ordinary non-penetration case.
    """
    start = _collision_point(start)
    end = _collision_point(end)
    plane_point = _collision_point(plane_point)
    normal = _collision_normal(plane_normal)
    delta = _collision_sub(end, start)
    denominator = _collision_dot(delta, normal)
    if abs(denominator) <= float(epsilon):
        return None
    t = _collision_dot(_collision_sub(plane_point, start), normal) / denominator
    if t < -float(epsilon) or t > 1.0 + float(epsilon):
        return None
    t = max(0.0, min(1.0, float(t)))
    return {"point": _collision_add(start, _collision_scale(delta, t)), "normal": normal, "t": t}


def segment_sphere_intersection(start, end, center, radius, epsilon=COLLISION_EPSILON):
    """Return the first segment/sphere hit as ``{point, normal, t}``."""
    start = _collision_point(start)
    end = _collision_point(end)
    center = _collision_point(center)
    radius = max(0.0, float(radius))
    delta = _collision_sub(end, start)
    offset = _collision_sub(start, center)
    a_value = _collision_dot(delta, delta)
    if a_value <= float(epsilon):
        return None
    b_value = 2.0 * _collision_dot(offset, delta)
    c_value = _collision_dot(offset, offset) - radius * radius
    discriminant = b_value * b_value - 4.0 * a_value * c_value
    if discriminant < -float(epsilon):
        return None
    root = math.sqrt(max(0.0, discriminant))
    roots = sorted(((-b_value - root) / (2.0 * a_value), (-b_value + root) / (2.0 * a_value)))
    hit_t = next((item for item in roots if -float(epsilon) <= item <= 1.0 + float(epsilon)), None)
    if hit_t is None:
        return None
    hit_t = max(0.0, min(1.0, float(hit_t)))
    hit_point = _collision_add(start, _collision_scale(delta, hit_t))
    return {"point": hit_point, "normal": _collision_normal(_collision_sub(hit_point, center)), "t": hit_t}


def _collision_surface_key(index, surface):
    if callable(surface):
        return ("", int(index))
    surface = surface or {}
    return (str(surface.get("surface_id") or surface.get("surface") or surface.get("record") or ""), int(index))


def _collision_surface_sample(surface, point, previous_point):
    if callable(surface):
        try:
            result = surface(point, previous_point)
        except TypeError:
            result = surface(point)
        return dict(result or {})
    return dict(surface or {})


def _collision_sweep_hit(surface, point, previous_point, normal):
    explicit_hit = surface.get("sweep_hit") if isinstance(surface, dict) else None
    if isinstance(explicit_hit, dict) and explicit_hit.get("point") is not None:
        return {
            "point": _collision_point(explicit_hit.get("point")),
            "normal": _collision_normal(explicit_hit.get("normal") or normal),
            "t": float(explicit_hit.get("t", 0.0)),
        }
    if isinstance(surface, dict) and surface.get("plane_point") is not None:
        return segment_plane_intersection(previous_point, point, surface.get("plane_point"), normal)
    if isinstance(surface, dict) and surface.get("sphere_center") is not None and surface.get("sphere_radius") is not None:
        return segment_sphere_intersection(previous_point, point, surface.get("sphere_center"), surface.get("sphere_radius"))
    return None


def _collision_candidate(surface, point, previous_point, clearance):
    sample = _collision_surface_sample(surface, point, previous_point)
    closest = sample.get("closest_point") or sample.get("projection") or sample.get("point")
    normal = sample.get("normal") or sample.get("contact_normal")
    if closest is None or normal is None:
        return None, sample, "missing surface point or normal"
    closest = _collision_point(closest)
    normal = _collision_normal(normal)
    sample_clearance = max(0.0, float(sample.get("clearance", clearance) or 0.0))
    point_delta = _collision_sub(point, closest)
    signed_distance = _collision_dot(point_delta, normal)
    tangent_distance = _collision_length(
        _collision_sub(point_delta, _collision_scale(normal, signed_distance))
    )
    inside = bool(sample.get("inside", False))
    closed = bool(sample.get("closed", False))
    # A sweep is checked before endpoint penetration so a large interactive
    # jump cannot cross a surface and emerge on the far side in one event.
    sweep_hit = _collision_sweep_hit(sample, point, previous_point, normal)
    sweep_t = float(sweep_hit.get("t", 0.0)) if sweep_hit else 1.0
    sweep_starts_on_surface = sweep_t <= COLLISION_EPSILON
    should_sweep = bool(
        sweep_hit
        and sweep_t < 1.0 - COLLISION_EPSILON
        and (signed_distance < sample_clearance - COLLISION_EPSILON or (closed and not sweep_starts_on_surface))
    )
    if should_sweep:
        hit_normal = _collision_normal(sweep_hit.get("normal") or normal, fallback=normal)
        return _collision_add(_collision_point(sweep_hit["point"]), _collision_scale(hit_normal, sample_clearance)), sample, "sweep"

    endpoint_overlaps_finite_surface = bool(
        signed_distance < sample_clearance - COLLISION_EPSILON
        and tangent_distance <= sample_clearance + COLLISION_EPSILON
    )
    if inside or endpoint_overlaps_finite_surface:
        return _collision_add(closest, _collision_scale(normal, sample_clearance)), sample, "penetration"
    return None, sample, "clear"


def solve_live_mesh_collision(
    point,
    previous_point=None,
    surfaces=None,
    offset=DEFAULT_COLLISION_OFFSET,
    radius=DEFAULT_COLLISION_RADIUS,
    max_iterations=COLLISION_MAX_ITERATIONS,
):
    """Project one control origin outside all supplied collision surfaces.

    ``surfaces`` is a sequence of query-result dictionaries or callables.  A
    query dictionary may contain ``closest_point``, ``normal``, ``closed``,
    ``inside``, ``sweep_hit`` (or ``plane_point``/``sphere_center`` helpers),
    and an optional ``locked`` flag.  The stable surface key and input order
    decide arbitration, so multiple records for one control are never
    collapsed.  The result is truthful when a locked control cannot move.
    """
    current = _collision_point(point)
    previous = _collision_point(previous_point if previous_point is not None else point)
    clearance = max(0.0, float(offset)) + max(0.0, float(radius))
    indexed = list(enumerate(surfaces or []))
    indexed.sort(key=lambda pair: _collision_surface_key(pair[0], pair[1]))
    collisions = []
    changed = False
    failure = ""

    for _iteration in range(max(1, int(max_iterations))):
        pass_changed = False
        sweep_previous = previous if _iteration == 0 else current
        for index, surface in indexed:
            candidate, sample, reason = _collision_candidate(surface, current, sweep_previous, clearance)
            if candidate is None:
                continue
            candidate = _collision_point(candidate)
            if _collision_close(candidate, current):
                continue
            if isinstance(sample, dict) and sample.get("locked"):
                failure = "The control is locked or constrained and cannot be corrected on {0}.".format(
                    sample.get("surface_id") or sample.get("surface") or "the selected surface"
                )
                return {
                    "success": False,
                    "position": current,
                    "changed": changed,
                    "collisions": collisions,
                    "nonpenetrating": False,
                    "failure": failure,
                    "iterations": _iteration + 1,
                }
            current = candidate
            collisions.append(
                {
                    "surface_id": (sample or {}).get("surface_id") or (sample or {}).get("surface") or str(index),
                    "reason": reason,
                    "position": current,
                }
            )
            changed = True
            pass_changed = True
        if not pass_changed:
            break

    nonpenetrating = True
    for index, surface in indexed:
        sample = _collision_surface_sample(surface, current, previous)
        validator = sample.get("validate") if isinstance(sample, dict) else None
        if callable(validator):
            try:
                valid = validator(current)
            except TypeError:
                valid = validator(current, clearance)
            if isinstance(valid, dict):
                valid = valid.get("nonpenetrating", valid.get("valid", True))
            if not bool(valid):
                nonpenetrating = False
                failure = "The solved control remains inside {0}.".format(sample.get("surface_id") or sample.get("surface") or str(index))
                break
        else:
            closest = sample.get("closest_point") or sample.get("projection") or sample.get("point")
            normal = sample.get("normal") or sample.get("contact_normal")
            if closest is None or normal is None:
                continue
            normal = _collision_normal(normal)
            point_delta = _collision_sub(current, closest)
            signed = _collision_dot(point_delta, normal)
            tangent_distance = _collision_length(
                _collision_sub(point_delta, _collision_scale(normal, signed))
            )
            sample_clearance = max(0.0, float(sample.get("clearance", clearance) or 0.0))
            endpoint_overlap = bool(
                signed < sample_clearance - COLLISION_EPSILON
                and tangent_distance <= sample_clearance + COLLISION_EPSILON
            )
            if bool(sample.get("inside", False)) or endpoint_overlap:
                nonpenetrating = False
                failure = "The solved control remains inside {0}.".format(sample.get("surface_id") or sample.get("surface") or str(index))
                break

    return {
        "success": bool(nonpenetrating),
        "position": current,
        "changed": changed,
        "collisions": collisions,
        "nonpenetrating": bool(nonpenetrating),
        "failure": failure,
        "iterations": max(1, int(max_iterations)),
    }


# Friendly aliases for callers/tests that describe the operation as a
# projection rather than a solve.
project_live_mesh_collision = solve_live_mesh_collision
solve_collision_point = solve_live_mesh_collision


def _debug(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayInfo("[Maya Surface Contact] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayWarning("[Maya Surface Contact] {0}".format(message))


def _kill_script_jobs_with_marker(marker):
    if not MAYA_AVAILABLE or not cmds:
        return 0
    killed = 0
    try:
        jobs = cmds.scriptJob(listJobs=True) or []
    except Exception:
        jobs = []
    for job_text in jobs:
        text = str(job_text)
        if marker not in text:
            continue
        try:
            job_id = int(text.split(":", 1)[0].strip())
            cmds.scriptJob(kill=job_id, force=True)
            killed += 1
        except Exception:
            pass
    return killed


def _safe_token(node_name):
    return "".join(character if character.isalnum() else "_" for character in _short_name(node_name)).strip("_") or "node"


def _ensure_attr(node_name, attr_name, attr_type="string"):
    if cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return
    if attr_type == "string":
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
    elif attr_type == "bool":
        cmds.addAttr(node_name, longName=attr_name, attributeType="bool")
    elif attr_type == "long":
        cmds.addAttr(node_name, longName=attr_name, attributeType="long")
    else:
        cmds.addAttr(node_name, longName=attr_name, attributeType=attr_type)


def _set_string_attr(node_name, attr_name, value):
    _ensure_attr(node_name, attr_name, "string")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), value or "", type="string")


def _get_string_attr(node_name, attr_name, default=""):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return default
    value = cmds.getAttr("{0}.{1}".format(node_name, attr_name))
    return value if value is not None else default


def _set_bool_attr(node_name, attr_name, value):
    _ensure_attr(node_name, attr_name, "bool")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), bool(value))


def _get_bool_attr(node_name, attr_name, default=False):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return bool(default)
    return bool(cmds.getAttr("{0}.{1}".format(node_name, attr_name)))


def _ensure_message_attr(node_name, attr_name):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="message")


def _connect_message(source_node, target_node, target_attr):
    _ensure_message_attr(target_node, target_attr)
    target_plug = "{0}.{1}".format(target_node, target_attr)
    existing = cmds.listConnections(target_plug, source=True, destination=False, plugs=True) or []
    for source_plug in existing:
        try:
            cmds.disconnectAttr(source_plug, target_plug)
        except Exception:
            pass
    cmds.connectAttr(source_node + ".message", target_plug, force=True)


def _connected_source_node(node_name, attr_name):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return ""
    connections = cmds.listConnections("{0}.{1}".format(node_name, attr_name), source=True, destination=False) or []
    if not connections:
        return ""
    return _node_long_name(connections[0])


def _load_json_attr(node_name, attr_name, default=None):
    default = {} if default is None else default
    raw_value = _get_string_attr(node_name, attr_name, "")
    if not raw_value:
        return default
    try:
        payload = json.loads(raw_value)
    except Exception:
        return default
    return payload if isinstance(payload, dict) else default


def _store_json_attr(node_name, attr_name, payload):
    _set_string_attr(node_name, attr_name, json.dumps(payload, sort_keys=True))


def _vector(values):
    return om.MVector(float(values[0]), float(values[1]), float(values[2]))


def _vector_tuple(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def _dot(a, b):
    return float(a.x) * float(b.x) + float(a.y) * float(b.y) + float(a.z) * float(b.z)


def _cross(a, b):
    return om.MVector(
        float(a.y) * float(b.z) - float(a.z) * float(b.y),
        float(a.z) * float(b.x) - float(a.x) * float(b.z),
        float(a.x) * float(b.y) - float(a.y) * float(b.x),
    )


def _length(vector):
    return math.sqrt(_dot(vector, vector))


def _normalize(vector):
    magnitude = _length(vector)
    if magnitude <= 1.0e-8:
        return om.MVector(0.0, 0.0, 0.0)
    return om.MVector(vector.x / magnitude, vector.y / magnitude, vector.z / magnitude)


def _project_onto_plane(vector, normal):
    normal = _normalize(normal)
    return vector - normal * _dot(vector, normal)


def _matrix_axes(matrix_values):
    return (
        _normalize(_vector(matrix_values[0:3])),
        _normalize(_vector(matrix_values[4:7])),
        _normalize(_vector(matrix_values[8:11])),
    )


def _matrix_from_axes(origin, x_axis, y_axis, z_axis):
    return [
        float(x_axis.x), float(x_axis.y), float(x_axis.z), 0.0,
        float(y_axis.x), float(y_axis.y), float(y_axis.z), 0.0,
        float(z_axis.x), float(z_axis.y), float(z_axis.z), 0.0,
        float(origin.x), float(origin.y), float(origin.z), 1.0,
    ]


def _world_matrix(node_name):
    return cmds.xform(node_name, query=True, worldSpace=True, matrix=True) or [1.0, 0.0, 0.0, 0.0,
                                                                               0.0, 1.0, 0.0, 0.0,
                                                                               0.0, 0.0, 1.0, 0.0,
                                                                               0.0, 0.0, 0.0, 1.0]


def _world_translation(node_name):
    return cmds.xform(node_name, query=True, worldSpace=True, translation=True) or [0.0, 0.0, 0.0]


def _world_scale(node_name):
    try:
        return cmds.xform(node_name, query=True, worldSpace=True, scale=True) or [1.0, 1.0, 1.0]
    except Exception:
        return [1.0, 1.0, 1.0]


def _set_world_matrix(node_name, matrix_values):
    current_scale = _world_scale(node_name)
    cmds.xform(node_name, worldSpace=True, matrix=list(matrix_values))
    try:
        cmds.xform(node_name, worldSpace=True, scale=list(current_scale))
    except Exception:
        pass


def _set_world_translation(node_name, translation_values):
    current_scale = _world_scale(node_name)
    cmds.xform(node_name, worldSpace=True, translation=list(translation_values))
    try:
        cmds.xform(node_name, worldSpace=True, scale=list(current_scale))
    except Exception:
        pass


def _surface_shape(surface_node):
    if not surface_node or not cmds.objExists(surface_node):
        return ""
    if cmds.nodeType(surface_node) == "mesh":
        shape_node = _node_long_name(surface_node)
        return shape_node if _surface_shape_is_sampleable(shape_node) else ""
    if cmds.nodeType(surface_node) in ("transform", "joint"):
        shapes = cmds.listRelatives(surface_node, shapes=True, fullPath=True, type="mesh") or []
        for shape_node in shapes:
            shape_node = _node_long_name(shape_node)
            if _surface_shape_is_sampleable(shape_node):
                return shape_node
    return ""


def _surface_shape_is_sampleable(shape_node):
    if not shape_node or not cmds.objExists(shape_node):
        return False
    try:
        if cmds.getAttr(shape_node + ".intermediateObject"):
            return False
    except Exception:
        pass
    try:
        return int(cmds.polyEvaluate(shape_node, face=True) or 0) > 0
    except Exception:
        return False


def _surface_transform(surface_node):
    if not surface_node or not cmds.objExists(surface_node):
        return ""
    if cmds.nodeType(surface_node) == "mesh":
        parent = cmds.listRelatives(surface_node, parent=True, fullPath=True) or []
        return _node_long_name(parent[0]) if parent else ""
    if cmds.nodeType(surface_node) in ("transform", "joint"):
        return _node_long_name(surface_node) if _surface_shape(surface_node) else ""
    return ""


def _selected_surface_node():
    nodes = _selected_surface_nodes()
    return nodes[0] if nodes else ""


def _selected_surface_nodes():
    selection = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    resolved_nodes = []
    for node_name in selection:
        resolved = _surface_transform(node_name)
        if resolved:
            resolved_nodes.append(resolved)
    return _dedupe_preserve_order(resolved_nodes)


def _surface_dag_path(surface_node):
    shape_node = _surface_shape(surface_node)
    if not shape_node:
        return None
    try:
        selection = om.MSelectionList()
        selection.add(shape_node)
        return selection.getDagPath(0)
    except Exception:
        return None


def _closest_point_and_normal(surface_node, point_values):
    dag_path = _surface_dag_path(surface_node)
    if dag_path is None:
        return None, None, None
    try:
        fn_mesh = om.MFnMesh(dag_path)
        point = om.MPoint(float(point_values[0]), float(point_values[1]), float(point_values[2]))
        closest_point, normal, face_index = fn_mesh.getClosestPointAndNormal(point, om.MSpace.kWorld)
    except Exception:
        try:
            closest_point, face_index = fn_mesh.getClosestPoint(point, om.MSpace.kWorld)
            normal, _ = fn_mesh.getClosestNormal(point, om.MSpace.kWorld)
        except Exception:
            return None, None, None
    return [closest_point.x, closest_point.y, closest_point.z], [normal.x, normal.y, normal.z], int(face_index)


def _mesh_is_closed(surface_node):
    """Best-effort closed-mesh query used only by the collision mode."""
    dag_path = _surface_dag_path(surface_node)
    if dag_path is None:
        return False
    try:
        fn_mesh = om.MFnMesh(dag_path)
        value = getattr(fn_mesh, "isClosed", None)
        if value is not None and bool(value() if callable(value) else value):
            return True
    except Exception:
        return False
    # Maya 2026 Python API 2.0 does not expose MFnMesh.isClosed.  Determine
    # closure from topology instead: a polygon mesh is closed only when it has
    # edges and none of them are boundary edges.
    try:
        edge_iterator = om.MItMeshEdge(dag_path)
        saw_edge = False
        while not edge_iterator.isDone():
            saw_edge = True
            if edge_iterator.onBoundary():
                return False
            edge_iterator.next()
        return saw_edge
    except Exception:
        return False


def _point_inside_mesh(surface_node, point_values):
    """Return whether a point is inside a closed mesh when Maya exposes it."""
    dag_path = _surface_dag_path(surface_node)
    if dag_path is None:
        return False
    try:
        fn_mesh = om.MFnMesh(dag_path)
        point = om.MPoint(float(point_values[0]), float(point_values[1]), float(point_values[2]))
        checker = getattr(fn_mesh, "isPointInMesh", None)
        if checker is not None:
            for args in (
                (point, 1.0e-5, om.MSpace.kWorld),
                (point, om.MSpace.kWorld),
                (point,),
            ):
                try:
                    return bool(checker(*args))
                except Exception:
                    continue
    except Exception:
        pass
    # Older Maya API builds do not expose isPointInMesh.  A parity ray keeps
    # closed-ball correction working without relying on polygon winding.
    try:
        fn_mesh = om.MFnMesh(dag_path)
        point = om.MFloatPoint(float(point_values[0]), float(point_values[1]), float(point_values[2]))
        direction = om.MFloatVector(1.0, 0.17320508, 0.097531)
        # Python API 2.0 uses (source, direction, space, maxParam,
        # testBothDirections, ...).  The old API-1-style optional argument
        # order silently failed every parity query in Maya 2026.
        intersections = fn_mesh.allIntersections(
            point,
            direction,
            om.MSpace.kWorld,
            1.0e8,
            False,
        )
        if isinstance(intersections, (tuple, list)):
            # API 2.0 returns a tuple whose first item is MFloatPointArray,
            # not a Python list/tuple.
            points = intersections[0] if intersections else []
            ray_params = intersections[1] if len(intersections) > 1 else []
            if len(ray_params):
                parameters = [ray_params[index] for index in range(len(ray_params))]
            else:
                parameters = [
                    (points[index].x - point.x) * direction.x
                    + (points[index].y - point.y) * direction.y
                    + (points[index].z - point.z) * direction.z
                    for index in range(len(points))
                ]
            return bool(len(_collision_unique_parameters(parameters)) % 2)
        if hasattr(intersections, "__len__"):
            return bool(len(intersections) % 2)
    except Exception:
        pass
    return False


def _segment_mesh_intersection(surface_node, start_values, end_values):
    """Return the first finite segment hit using MFnMesh when available."""
    dag_path = _surface_dag_path(surface_node)
    if dag_path is None:
        return None
    start = om.MFloatPoint(float(start_values[0]), float(start_values[1]), float(start_values[2]))
    delta = om.MFloatVector(
        float(end_values[0]) - float(start_values[0]),
        float(end_values[1]) - float(start_values[1]),
        float(end_values[2]) - float(start_values[2]),
    )
    distance = float(delta.length())
    if distance <= COLLISION_EPSILON:
        return None
    direction = delta / distance
    try:
        fn_mesh = om.MFnMesh(dag_path)
    except Exception:
        return None

    try:
        hit = fn_mesh.closestIntersection(
            start,
            direction,
            om.MSpace.kWorld,
            distance,
            False,
        )
    except Exception:
        hit = None
    if not hit:
        return None
    try:
        hit_point = hit[0] if isinstance(hit, (tuple, list)) else hit
        hit_param = float(hit[1]) if isinstance(hit, (tuple, list)) and len(hit) > 1 else 0.0
        face_index = int(hit[2]) if isinstance(hit, (tuple, list)) and len(hit) > 2 else -1
    except Exception:
        return None
    if not hasattr(hit_point, "x"):
        return None
    try:
        _, normal_values, _ = _closest_point_and_normal(surface_node, [hit_point.x, hit_point.y, hit_point.z])
    except Exception:
        normal_values = [0.0, 1.0, 0.0]
    return {
        "point": [hit_point.x, hit_point.y, hit_point.z],
        "normal": normal_values,
        "t": max(0.0, min(1.0, hit_param / distance if distance else 0.0)),
        "face_index": face_index,
    }


def _mesh_collision_query(surface_node, point_values, previous_point=None, contact_normal=None):
    """Query one mesh for the shared live collision solver."""
    surface_point, surface_normal, face_index = _closest_point_and_normal(surface_node, point_values)
    if not surface_point or not surface_normal:
        return None
    normal = _collision_normal(surface_normal)
    closed = _mesh_is_closed(surface_node)
    if contact_normal and not closed:
        preferred = _collision_normal(contact_normal, fallback=normal)
        if _collision_dot(normal, preferred) < 0.0:
            normal = _collision_scale(normal, -1.0)
    inside = _point_inside_mesh(surface_node, point_values) if closed else False
    if closed:
        normal = _collision_outward_normal(normal, surface_point, point_values, inside=inside)
    sweep_hit = None
    if previous_point is not None:
        sweep_hit = _segment_mesh_intersection(surface_node, previous_point, point_values)
        if sweep_hit and closed:
            hit_normal = _collision_normal(sweep_hit.get("normal") or normal, fallback=normal)
            hit_point = _collision_point(sweep_hit.get("point"))
            hit_normal = _collision_outward_normal(hit_normal, hit_point, previous_point, inside=False)
            sweep_hit["normal"] = list(hit_normal)
    return {
        "surface_id": _node_long_name(surface_node),
        "surface": _node_long_name(surface_node),
        "closest_point": list(surface_point),
        "normal": list(normal),
        "face_index": int(face_index),
        "closed": bool(closed),
        "inside": bool(inside),
        "sweep_hit": sweep_hit,
    }


def _contact_group(create=True):
    root_group = "|" + SURFACE_CONTACT_GROUP_NAME
    if cmds.objExists(root_group):
        return _node_long_name(root_group)
    if not create:
        return ""
    created = cmds.createNode("transform", name=SURFACE_CONTACT_GROUP_NAME)
    cmds.setAttr(created + ".visibility", 0)
    return _node_long_name(created)


def _all_contact_records():
    root_group = _contact_group(create=False)
    if not root_group:
        return []
    children = cmds.listRelatives(root_group, children=True, type="transform", fullPath=True) or []
    return [_node_long_name(item) for item in children if _get_bool_attr(item, SURFACE_CONTACT_MARKER_ATTR, False)]


def _record_name(control_node, suffix=None):
    safe_name = _safe_token(control_node)
    if suffix:
        return "amirSurfaceContact_{0}_{1}".format(safe_name, suffix)
    return "amirSurfaceContact_{0}".format(safe_name)


def _contact_payload(record_node):
    if not record_node or not cmds.objExists(record_node):
        return None
    payload = _load_json_attr(record_node, SURFACE_CONTACT_DATA_ATTR, {})
    control_node = _connected_source_node(record_node, SURFACE_CONTACT_CONTROL_ATTR) or payload.get("control", "")
    surface_node = _connected_source_node(record_node, SURFACE_CONTACT_SURFACE_ATTR) or payload.get("surface", "")
    if control_node and not cmds.objExists(control_node):
        control_node = payload.get("control", "")
    if surface_node and not cmds.objExists(surface_node):
        surface_node = payload.get("surface", "")
    payload.update(
        {
            "record": _node_long_name(record_node),
            "control": _node_long_name(control_node) if control_node else "",
            "surface": _node_long_name(surface_node) if surface_node else "",
            "enabled": _get_bool_attr(record_node, SURFACE_CONTACT_ENABLED_ATTR, bool(payload.get("enabled", True))),
            "follow_normal": bool(payload.get("follow_normal", DEFAULT_FOLLOW_NORMAL)),
            "tangent_hint": payload.get("tangent_hint", [1.0, 0.0, 0.0]),
            "constraint_nodes": payload.get("constraint_nodes", []),
            "list_name": payload.get("list_name", _short_name(control_node) if control_node else _short_name(record_node)),
            "control_label": payload.get("control_label", _short_name(control_node) if control_node else ""),
            # New collision records are scene-backed beside legacy Surface
            # Contact records.  Missing fields retain the old contract.
            "mode": payload.get("mode", SURFACE_CONTACT_MODE),
            "offset": float(payload.get("offset", DEFAULT_COLLISION_OFFSET) or 0.0),
            "radius": float(payload.get("radius", DEFAULT_COLLISION_RADIUS) or 0.0),
            "previous_valid_point": payload.get("previous_valid_point"),
            "last_solved_point": payload.get("last_solved_point"),
            "last_error": payload.get("last_error", ""),
        }
    )
    return payload


def _set_contact_payload(record_node, payload):
    payload = dict(payload or {})
    payload.setdefault("enabled", True)
    payload.setdefault("follow_normal", DEFAULT_FOLLOW_NORMAL)
    payload.setdefault("tangent_hint", [1.0, 0.0, 0.0])
    payload.setdefault("constraint_nodes", [])
    payload.setdefault("list_name", _short_name(payload.get("control", "")) if payload.get("control") else _short_name(record_node))
    payload.setdefault("control_label", _short_name(payload.get("control", "")) if payload.get("control") else "")
    payload.setdefault("mode", SURFACE_CONTACT_MODE)
    payload.setdefault("offset", DEFAULT_COLLISION_OFFSET)
    payload.setdefault("radius", DEFAULT_COLLISION_RADIUS)
    payload.setdefault("previous_valid_point", None)
    payload.setdefault("last_solved_point", None)
    payload.setdefault("last_error", "")
    _store_json_attr(record_node, SURFACE_CONTACT_DATA_ATTR, payload)


def _create_contact_record(control_node, surface_node, payload):
    root_group = _contact_group(create=True)
    record_node = cmds.createNode("transform", name=_record_name(control_node, uuid.uuid4().hex[:8]), parent=root_group)
    record_node = _node_long_name(record_node)
    cmds.setAttr(record_node + ".visibility", 0)
    _set_bool_attr(record_node, SURFACE_CONTACT_MARKER_ATTR, True)
    _set_bool_attr(record_node, SURFACE_CONTACT_ENABLED_ATTR, bool(payload.get("enabled", True)))
    _ensure_message_attr(record_node, SURFACE_CONTACT_CONTROL_ATTR)
    _ensure_message_attr(record_node, SURFACE_CONTACT_SURFACE_ATTR)
    _connect_message(control_node, record_node, SURFACE_CONTACT_CONTROL_ATTR)
    _connect_message(surface_node, record_node, SURFACE_CONTACT_SURFACE_ATTR)
    _set_contact_payload(record_node, payload)
    return record_node


def _create_collision_record(control_node, surface_node, payload):
    """Create a Live Mesh Collision record without changing legacy records."""
    collision_payload = dict(payload or {})
    collision_payload["mode"] = LIVE_MESH_COLLISION_MODE
    collision_payload.setdefault("follow_normal", DEFAULT_COLLISION_FOLLOW_NORMAL)
    collision_payload.setdefault("offset", DEFAULT_COLLISION_OFFSET)
    collision_payload.setdefault("radius", DEFAULT_COLLISION_RADIUS)
    collision_payload.setdefault("previous_valid_point", _collision_point(_world_translation(control_node)))
    collision_payload.setdefault("last_solved_point", collision_payload.get("previous_valid_point"))
    return _create_contact_record(control_node, surface_node, collision_payload)


def _collision_record_from_inputs(control_node, surface_node, existing_payload=None, offset=DEFAULT_COLLISION_OFFSET, radius=DEFAULT_COLLISION_RADIUS, follow_normal=DEFAULT_COLLISION_FOLLOW_NORMAL):
    """Build a conservative collision record without snapping a free control."""
    existing_payload = dict(existing_payload or {})
    current = _collision_point(_world_translation(control_node))
    query = _mesh_collision_query(surface_node, current, previous_point=current, contact_normal=existing_payload.get("contact_normal"))
    if not query:
        return None, "Could not sample the selected collision surface."
    normal = _collision_normal(query.get("normal"))
    if not query.get("closed"):
        closest = _collision_point(query.get("closest_point"))
        if _collision_dot(_collision_sub(current, closest), normal) < 0.0:
            normal = _collision_scale(normal, -1.0)
    payload = {
        "id": existing_payload.get("id") or uuid.uuid4().hex[:8],
        "control": _node_long_name(control_node),
        "surface": _node_long_name(surface_node),
        "control_label": _short_name(control_node),
        "list_name": existing_payload.get("list_name") or _short_name(control_node),
        "enabled": bool(existing_payload.get("enabled", True)),
        "mode": LIVE_MESH_COLLISION_MODE,
        "follow_normal": bool(follow_normal),
        "offset": max(0.0, float(offset)),
        "radius": max(0.0, float(radius)),
        "contact_normal": list(normal),
        "previous_valid_point": list(existing_payload.get("previous_valid_point") or current),
        "last_solved_point": list(existing_payload.get("last_solved_point") or current),
        "last_error": "",
    }
    return payload, None


def _contact_constraint_nodes(payload):
    nodes = []
    for node_name in (payload or {}).get("constraint_nodes", []) or []:
        if node_name and cmds.objExists(node_name):
            nodes.append(_node_long_name(node_name))
    return _dedupe_preserve_order(nodes)


def _record_enabled_has_anim(record_node):
    plug = "{0}.{1}".format(record_node, SURFACE_CONTACT_ENABLED_ATTR)
    try:
        return bool(cmds.listConnections(plug, source=True, destination=False, type="animCurve") or [])
    except Exception:
        return False


def _set_record_enabled(record_node, enabled):
    _set_bool_attr(record_node, SURFACE_CONTACT_ENABLED_ATTR, bool(enabled))
    if enabled:
        payload = _contact_payload(record_node)
        control_node = (payload or {}).get("control", "")
        if (
            payload
            and payload.get("mode") == LIVE_MESH_COLLISION_MODE
            and control_node
            and cmds.objExists(control_node)
        ):
            current = list(_collision_point(_world_translation(control_node)))
            payload["previous_valid_point"] = current
            payload["last_solved_point"] = current
            payload["last_error"] = ""
            _set_contact_payload(record_node, payload)
    if _record_enabled_has_anim(record_node):
        try:
            cmds.setKeyframe(
                record_node,
                attribute=SURFACE_CONTACT_ENABLED_ATTR,
                time=cmds.currentTime(query=True),
                value=1.0 if enabled else 0.0,
            )
        except Exception:
            pass


def _delete_contact_constraints(payload):
    deleted = []
    for node_name in _contact_constraint_nodes(payload):
        try:
            cmds.delete(node_name)
            deleted.append(node_name)
        except Exception:
            pass
    payload["constraint_nodes"] = []
    return deleted


def _find_record(control_node, surface_node):
    control_long = _node_long_name(control_node)
    surface_long = _node_long_name(surface_node)
    for record_node in _all_contact_records():
        payload = _contact_payload(record_node)
        if not payload:
            continue
        if payload.get("mode", SURFACE_CONTACT_MODE) == SURFACE_CONTACT_MODE and payload.get("control") == control_long and payload.get("surface") == surface_long:
            return record_node
    return ""


def _find_collision_record(control_node, surface_node):
    control_long = _node_long_name(control_node)
    surface_long = _node_long_name(surface_node)
    for record_node in _all_contact_records():
        payload = _contact_payload(record_node)
        if not payload or payload.get("mode") != LIVE_MESH_COLLISION_MODE:
            continue
        if payload.get("control") == control_long and payload.get("surface") == surface_long:
            return record_node
    return ""


def _all_records_for_control(control_node):
    control_long = _node_long_name(control_node)
    result = []
    for record_node in _all_contact_records():
        payload = _contact_payload(record_node)
        if payload and payload.get("control") == control_long:
            result.append(record_node)
    return _dedupe_preserve_order(result)


def _delete_record(record_node):
    if record_node and cmds.objExists(record_node):
        try:
            payload = _contact_payload(record_node) or {}
            _delete_contact_constraints(payload)
            cmds.delete(record_node)
            return True
        except Exception:
            return False
    return False


def _remove_all_records():
    deleted = 0
    for record_node in _all_contact_records():
        if _delete_record(record_node):
            deleted += 1
    return deleted


def _resolve_controls_from_text(text_value):
    controls = []
    for chunk in (text_value or "").split(","):
        name = chunk.strip()
        if not name:
            continue
        if cmds.objExists(name):
            controls.append(_node_long_name(name))
    return _dedupe_preserve_order(controls)


def _basis_from_surface(surface_normal, tangent_hint, fallback_matrix=None):
    normal = _normalize(_vector(surface_normal))
    tangent = _project_onto_plane(_vector(tangent_hint), normal)
    if _length(tangent) <= 1.0e-8 and fallback_matrix:
        fallback_axes = _matrix_axes(fallback_matrix)
        tangent = _project_onto_plane(fallback_axes[0], normal)
    if _length(tangent) <= 1.0e-8:
        fallback = om.MVector(1.0, 0.0, 0.0)
        if abs(_dot(fallback, normal)) > 0.95:
            fallback = om.MVector(0.0, 0.0, 1.0)
        tangent = _project_onto_plane(fallback, normal)
    tangent = _normalize(tangent)
    bitangent = _normalize(_cross(tangent, normal))
    if _length(bitangent) <= 1.0e-8:
        bitangent = _normalize(_cross(normal, tangent))
    return tangent, normal, bitangent


def _node_mobject(node_name):
    if not MAYA_AVAILABLE or not node_name or not cmds.objExists(node_name):
        return None
    try:
        selection_list = om.MSelectionList()
        selection_list.add(node_name)
        return selection_list.getDependNode(0)
    except Exception:
        return None


def _collision_translation_unlocked(control_node):
    return all(
        bool(hold_utils._attr_unlocked(control_node, attribute))
        for attribute in ("translateX", "translateY", "translateZ")
    )


def _apply_collision_group(payloads, force=False):
    """Solve every enabled collision record for one control as one system."""
    payloads = [dict(item or {}) for item in (payloads or []) if item]
    if not payloads:
        return False, "There are no collision records to solve."
    control_node = payloads[0].get("control", "")
    if not control_node or not cmds.objExists(control_node):
        return False, "The driven control no longer exists."
    current = _collision_point(_world_translation(control_node))
    previous = None
    for payload in payloads:
        candidate = payload.get("previous_valid_point") or payload.get("last_solved_point")
        if candidate is not None:
            previous = _collision_point(candidate)
            break
    if previous is None:
        previous = current
    samples = []
    for payload in sorted(payloads, key=lambda item: (str(item.get("surface", "")), str(item.get("record", "")))):
        surface_node = payload.get("surface", "")
        if not surface_node or not cmds.objExists(surface_node):
            return False, "The collision surface no longer exists."
        initial_sample = _mesh_collision_query(
            surface_node,
            current,
            previous_point=previous,
            contact_normal=payload.get("contact_normal"),
        )
        if not initial_sample:
            return False, "Could not sample collision surface {0}.".format(_short_name(surface_node))
        clearance = max(
            0.0,
            float(payload.get("offset", DEFAULT_COLLISION_OFFSET) or 0.0),
        ) + max(0.0, float(payload.get("radius", DEFAULT_COLLISION_RADIUS) or 0.0))
        locked = not _collision_translation_unlocked(control_node)

        def _query(point, query_previous, _surface_node=surface_node, _payload=payload, _clearance=clearance, _locked=locked):
            sample = _mesh_collision_query(
                _surface_node,
                point,
                previous_point=query_previous,
                contact_normal=_payload.get("contact_normal"),
            ) or {}
            sample["record"] = _payload.get("record", "")
            sample["clearance"] = _clearance
            sample["locked"] = _locked
            return sample

        samples.append(_query)

    result = solve_live_mesh_collision(current, previous_point=previous, surfaces=samples, max_iterations=COLLISION_MAX_ITERATIONS)
    if not result.get("success"):
        message = result.get("failure") or "The control could not be corrected without penetrating a collision surface."
        for payload in payloads:
            payload["last_error"] = message
            if payload.get("record") and cmds.objExists(payload["record"]):
                _set_contact_payload(payload["record"], payload)
        return False, message

    solved_point = _collision_point(result.get("position", current))
    if result.get("changed") and not _collision_close(solved_point, current):
        try:
            _set_world_translation(control_node, solved_point)
        except Exception as exc:
            message = "The control could not be corrected: {0}".format(exc)
            for payload in payloads:
                payload["last_error"] = message
                if payload.get("record") and cmds.objExists(payload["record"]):
                    _set_contact_payload(payload["record"], payload)
            return False, message

    # Maya/evaluation may clamp, redirect, or reject a transform write.  Do
    # not store the requested/previous solver point as proof: read back the
    # actual world translation and validate that exact point against the same
    # collision system before updating the saved payload.
    actual_position = _collision_point(_world_translation(control_node))
    if not _collision_close(actual_position, solved_point, epsilon=1.0e-4):
        message = (
            "The control did not reach the solved collision point "
            "(requested {0}, actual {1})."
        ).format(tuple(solved_point), tuple(actual_position))
        for payload in payloads:
            payload["last_error"] = message
            if payload.get("record") and cmds.objExists(payload["record"]):
                _set_contact_payload(payload["record"], payload)
        return False, message
    validation = solve_live_mesh_collision(
        actual_position,
        previous_point=actual_position,
        surfaces=samples,
        max_iterations=COLLISION_MAX_ITERATIONS,
    )
    if not validation.get("success") or validation.get("changed") or not _collision_close(
        _collision_point(validation.get("position", actual_position)),
        actual_position,
        epsilon=1.0e-4,
    ):
        message = "The actual control world translation failed post-correction collision validation."
        for payload in payloads:
            payload["last_error"] = message
            if payload.get("record") and cmds.objExists(payload["record"]):
                _set_contact_payload(payload["record"], payload)
        return False, message

    for payload in payloads:
        payload["previous_valid_point"] = list(actual_position)
        payload["last_solved_point"] = list(actual_position)
        payload["last_error"] = ""
        if payload.get("record") and cmds.objExists(payload["record"]):
            _set_contact_payload(payload["record"], payload)
    return True, "Solved {0} collision surface(s) for {1}.".format(len(payloads), _short_name(control_node))


def _apply_to_record_payload(payload, force=False):
    if (payload or {}).get("mode") == LIVE_MESH_COLLISION_MODE:
        if not payload.get("enabled", True):
            return True, "Collision for {0} is disabled.".format(_short_name(payload.get("control", "")))
        return _apply_collision_group([payload], force=force)
    control_node = payload.get("control", "")
    surface_node = payload.get("surface", "")
    record_node = payload.get("record", "")
    if not control_node or not surface_node:
        return False, "The saved contact is missing its control or surface."
    if not cmds.objExists(control_node):
        return False, "The driven control no longer exists."
    if not cmds.objExists(surface_node):
        return False, "The surface mesh no longer exists."

    constraint_nodes = _contact_constraint_nodes(payload)
    if constraint_nodes:
        _delete_contact_constraints(payload)
        if record_node and cmds.objExists(record_node):
            _set_contact_payload(record_node, payload)

    if not payload.get("enabled", True):
        return True, "Solved {0} on the selected surface.".format(_short_name(control_node))

    surface_point, surface_normal, _face_index = _closest_point_and_normal(surface_node, _world_translation(control_node))
    if not surface_point or not surface_normal:
        return False, "Could not sample the selected surface."
    fallback_matrix = _world_matrix(control_node)
    contact_normal = _normalize(_vector(payload.get("contact_normal") or surface_normal))
    current_surface_normal = _normalize(_vector(surface_normal))
    if _dot(current_surface_normal, contact_normal) < 0.0:
        current_surface_normal = current_surface_normal * -1.0
    current_position = _vector(_world_translation(control_node))
    surface_point_vector = _vector(surface_point)
    signed_distance = _dot(current_position - surface_point_vector, current_surface_normal)
    if force or signed_distance < -1.0e-4:
        tangent, normal, bitangent = _basis_from_surface(current_surface_normal, payload.get("tangent_hint", [1.0, 0.0, 0.0]), fallback_matrix=fallback_matrix)
        if payload.get("follow_normal", DEFAULT_FOLLOW_NORMAL):
            matrix = _matrix_from_axes(om.MPoint(*surface_point), tangent, normal, bitangent)
            _set_world_matrix(control_node, matrix)
        else:
            _set_world_translation(control_node, surface_point)
        # Validate the transform that Maya actually accepted.  A cached
        # requested point is not enough when constraints, locks, or evaluation
        # order redirect the write.
        actual_position = _collision_point(_world_translation(control_node))
        expected_position = _collision_point(surface_point)
        if not _collision_close(actual_position, expected_position, epsilon=1.0e-4):
            return False, "The control did not reach the solved surface-contact point."
        actual_surface_point, actual_surface_normal, _actual_face_index = _closest_point_and_normal(
            surface_node,
            actual_position,
        )
        if not actual_surface_point or not actual_surface_normal:
            return False, "Could not validate the corrected surface contact."
        actual_normal = _normalize(_vector(actual_surface_normal))
        if _dot(actual_normal, contact_normal) < 0.0:
            actual_normal = actual_normal * -1.0
        actual_signed_distance = _dot(
            _vector(actual_position) - _vector(actual_surface_point),
            actual_normal,
        )
        if actual_signed_distance < -1.0e-4:
            return False, "The actual corrected control remains inside the selected surface."
    return True, "Solved {0} on the selected surface.".format(_short_name(control_node))


def _current_contact_summary(payload):
    return "{0} -> {1} ({2})".format(
        payload.get("control_label") or _short_name(payload.get("control", "")),
        _short_name(payload.get("surface", "")),
        "On" if payload.get("enabled") else "Off",
    )


def _frame_label(value):
    value = float(value)
    rounded = int(round(value))
    if abs(value - float(rounded)) <= 0.001:
        return str(rounded)
    return ("{0:.3f}".format(value)).rstrip("0").rstrip(".")


def _format_report(report):
    if not report:
        return "Pick a control and a surface, then click Check Setup."

    lines = [
        "Controls: {0}".format(len(report.get("controls", []))),
        "Surface: {0}".format(_short_name(report.get("surface", "")) or "None"),
        "Follow Surface Normal: {0}".format("Yes" if report.get("follow_normal") else "No"),
        "",
    ]
    if report.get("surfaces"):
        lines.insert(2, "Collision Surfaces: {0}".format(", ".join(_short_name(item) for item in report.get("surfaces", []))))

    errors = report.get("errors", [])
    warnings = report.get("warnings", [])
    if errors:
        lines.append("RED")
        lines.extend("- " + item for item in errors)
        lines.append("")
    if warnings:
        lines.append("YELLOW")
        lines.extend("- " + item for item in warnings)
        lines.append("")
    if not errors and not warnings:
        lines.append("GREEN")
        lines.append("- The selected surface contact looks ready to create or update.")
        lines.append("")

    if report.get("closest_point") and report.get("surface_normal"):
        closest = report["closest_point"]
        normal = report["surface_normal"]
        lines.append("Preview Contact Point")
        lines.append("- Point: {0:.3f}, {1:.3f}, {2:.3f}".format(closest[0], closest[1], closest[2]))
        lines.append("- Normal: {0:.3f}, {1:.3f}, {2:.3f}".format(normal[0], normal[1], normal[2]))
        lines.append("")

    if report.get("controls"):
        lines.append("Picked Controls")
        lines.extend("- " + _short_name(item) for item in report["controls"])

    if report.get("existing_setups"):
        lines.append("")
        lines.append("Existing Surface Contacts")
        for item in report["existing_setups"]:
            lines.append("- " + _current_contact_summary(item))

    return "\n".join(lines).strip()


class MayaSurfaceContactController(object):
    def __init__(self):
        self.control_nodes = []
        self.surface_node = ""
        self.surface_nodes = []
        self.follow_surface_normal = DEFAULT_COLLISION_FOLLOW_NORMAL
        self.mode = LIVE_MESH_COLLISION_MODE
        self.collision_offset = DEFAULT_COLLISION_OFFSET
        self.collision_radius = DEFAULT_COLLISION_RADIUS
        self.collision_follow_normal = DEFAULT_COLLISION_FOLLOW_NORMAL
        self.report = None
        self.status_callback = None
        self.selected_records = []
        self.callback_ids = []
        self.live_callback_ids = []
        self.idle_script_job_id = None
        self.script_job_id = None
        self._live_solve_pending = False
        self._live_solve_force = False
        self._solving = False
        self._live_callback_muted_until = 0.0
        self._shutdown_requested = False
        if MAYA_AVAILABLE:
            self._refresh_live_callbacks()

    def shutdown(self):
        self._shutdown_requested = True
        self._remove_time_callbacks()
        self._remove_live_callbacks()
        self._remove_idle_callback()

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _set_status(self, message, success=True):
        if self.status_callback:
            self.status_callback(message, success)
        if success:
            _debug(message)
        else:
            _warning(message)

    def _install_time_callbacks(self):
        if not MAYA_AVAILABLE:
            return
        if self.callback_ids or self.script_job_id:
            return
        try:
            callback_id = om.MEventMessage.addEventCallback("timeChanged", self._on_time_changed)
            self.callback_ids.append(callback_id)
        except Exception:
            self.callback_ids = []
            try:
                self.script_job_id = cmds.scriptJob(event=["timeChanged", self._on_time_changed], protected=True)
            except Exception as exc:
                _warning("Could not install timeChanged callback: {0}".format(exc))

    def _remove_time_callbacks(self):
        for callback_id in self.callback_ids:
            try:
                om.MMessage.removeCallback(callback_id)
            except Exception:
                pass
        self.callback_ids = []
        if self.script_job_id:
            try:
                cmds.scriptJob(kill=self.script_job_id, force=True)
            except Exception:
                pass
        self.script_job_id = None

    def _install_idle_callback(self):
        if not MAYA_AVAILABLE or self.idle_script_job_id:
            return
        try:
            _kill_script_jobs_with_marker("MayaSurfaceContactController._on_idle")
            self.idle_script_job_id = cmds.scriptJob(idleEvent=self._on_idle, protected=True)
        except Exception as exc:
            _warning("Could not install idle solver callback: {0}".format(exc))
            self.idle_script_job_id = None

    def _remove_idle_callback(self):
        if self.idle_script_job_id:
            try:
                cmds.scriptJob(kill=self.idle_script_job_id, force=True)
            except Exception:
                pass
        self.idle_script_job_id = None

    def _remove_live_callbacks(self):
        for callback_id in self.live_callback_ids:
            try:
                om.MMessage.removeCallback(callback_id)
            except Exception:
                pass
        self.live_callback_ids = []

    def _mute_live_callbacks(self, seconds=0.75):
        self._live_callback_muted_until = max(self._live_callback_muted_until, time.time() + float(seconds))

    def _live_callbacks_muted(self):
        return time.time() < self._live_callback_muted_until

    def _schedule_live_solve(self, force=False):
        if not MAYA_AVAILABLE or self._shutdown_requested or self._solving:
            return
        if force:
            self._live_solve_force = True
        if self._live_solve_pending:
            return
        self._live_solve_pending = True
        try:
            if QtCore and QtWidgets and QtWidgets.QApplication.instance():
                QtCore.QTimer.singleShot(LIVE_SOLVE_DELAY_MS, self._run_live_solve)
            elif maya_utils and hasattr(maya_utils, "executeDeferred"):
                maya_utils.executeDeferred(self._run_live_solve)
            else:
                cmds.evalDeferred(self._run_live_solve)
        except Exception:
            self._live_solve_pending = False
            self._live_solve_force = False
            try:
                self.solve_active_contacts(force=force)
            except Exception:
                pass

    def _run_live_solve(self):
        if not MAYA_AVAILABLE or self._shutdown_requested or not self._live_solve_pending:
            return
        if self._solving:
            return
        force = bool(self._live_solve_force)
        self._live_solve_pending = False
        self._live_solve_force = False
        try:
            self.solve_active_contacts(force=force)
        finally:
            if self._live_solve_pending:
                try:
                    if maya_utils and hasattr(maya_utils, "executeDeferred"):
                        maya_utils.executeDeferred(self._run_live_solve)
                    else:
                        cmds.evalDeferred(self._run_live_solve)
                except Exception:
                    pass

    def _live_callback_nodes(self):
        nodes = []
        for payload in [_contact_payload(record_node) for record_node in _all_contact_records()]:
            if not payload:
                continue
            if not payload.get("enabled", True):
                continue
            surface_shape = _surface_shape(payload.get("surface", ""))
            for node_name in (payload.get("record", ""), payload.get("control", ""), payload.get("surface", ""), surface_shape):
                if node_name and cmds.objExists(node_name):
                    nodes.append(_node_long_name(node_name))
        return _dedupe_preserve_order(nodes)

    def _refresh_live_callbacks(self):
        if not MAYA_AVAILABLE:
            return
        self._remove_live_callbacks()
        live_nodes = self._live_callback_nodes()
        if not live_nodes:
            self._remove_time_callbacks()
            self._remove_idle_callback()
            return
        self._install_time_callbacks()
        self._remove_idle_callback()
        for node_name in live_nodes:
            mobject = _node_mobject(node_name)
            if mobject is None:
                continue
            try:
                callback_id = om.MNodeMessage.addAttributeChangedCallback(mobject, self._on_node_attribute_changed)
                self.live_callback_ids.append(callback_id)
            except Exception as exc:
                _warning("Could not install live callback for {0}: {1}".format(_short_name(node_name), exc))

    def _on_time_changed(self, *_args):
        try:
            self._schedule_live_solve()
        except Exception:
            pass

    def _on_idle(self, *_args):
        try:
            self._schedule_live_solve()
        except Exception:
            pass

    def _on_node_attribute_changed(self, *_args):
        if self._live_callbacks_muted():
            return
        try:
            self._schedule_live_solve(force=False)
        except Exception:
            pass

    def _resolved_controls(self):
        return [node_name for node_name in self.control_nodes if node_name and cmds.objExists(node_name)]

    def _resolved_surface(self):
        surfaces = self._resolved_surfaces()
        return surfaces[0] if surfaces else ""

    def _resolved_surfaces(self):
        surfaces = []
        candidates = list(self.surface_nodes or [])
        if self.surface_node:
            candidates.insert(0, self.surface_node)
        for node_name in candidates:
            if node_name and cmds.objExists(node_name) and _surface_shape(node_name):
                surfaces.append(_node_long_name(node_name))
        self.surface_nodes = _dedupe_preserve_order(surfaces)
        self.surface_node = self.surface_nodes[0] if self.surface_nodes else ""
        return list(self.surface_nodes)

    def set_mode(self, mode):
        mode = str(mode or SURFACE_CONTACT_MODE)
        if mode not in (SURFACE_CONTACT_MODE, LIVE_MESH_COLLISION_MODE):
            return False, "Unknown surface contact mode: {0}".format(mode)
        self.mode = mode
        return True, mode

    def set_controls_from_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        control_nodes = _selected_controls()
        if not control_nodes:
            return False, "Pick one or more hand, foot, or object controls first."
        self.control_nodes = control_nodes
        self.report = None
        return True, "Picked {0} control(s).".format(len(control_nodes))

    def set_surface_from_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        surface_node = _selected_surface_node()
        if not surface_node:
            return False, "Pick a mesh surface first."
        self.surface_node = surface_node
        self.surface_nodes = [surface_node]
        self.report = None
        return True, "Picked the surface {0}.".format(_short_name(surface_node))

    def set_surfaces_from_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        surface_nodes = _selected_surface_nodes()
        if not surface_nodes:
            return False, "Pick one or more mesh collision surfaces first."
        self.surface_nodes = surface_nodes
        self.surface_node = surface_nodes[0]
        self.report = None
        return True, "Picked {0} collision surface(s).".format(len(surface_nodes))

    def set_inputs_from_selection(self):
        """Resolve one surface plus controls atomically without self-contact records."""
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        surface_node = self._resolved_surface() or _selected_surface_node()
        controls = self._resolved_controls() or _selected_controls()
        if surface_node:
            surface_long_name = _node_long_name(surface_node)
            controls = [
                control_node
                for control_node in controls
                if _node_long_name(control_node) != surface_long_name
            ]
        if not surface_node:
            return False, "Pick one mesh surface with the controls first."
        if not controls:
            return False, "Pick one or more controls with the mesh surface first."
        self.surface_node = surface_node
        self.surface_nodes = [surface_node]
        self.control_nodes = _dedupe_preserve_order(controls)
        self.report = None
        return True, "Picked {0} control(s) plus surface {1}.".format(
            len(self.control_nodes),
            _short_name(surface_node),
        )

    def set_collision_inputs_from_selection(self):
        """Resolve multiple controls and multiple mesh surfaces atomically."""
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        # This button means "use the current combined selection."  Reusing
        # previously-resolved inputs here prevented artists from changing the
        # collision object after the first setup.
        surface_nodes = _selected_surface_nodes()
        controls = _selected_controls()
        surface_lookup = set(_node_long_name(item) for item in surface_nodes)
        controls = [item for item in controls if _node_long_name(item) not in surface_lookup]
        if not surface_nodes:
            return False, "Pick one or more mesh collision surfaces with the controls."
        if not controls:
            return False, "Pick one or more controls with the collision surfaces."
        self.surface_nodes = _dedupe_preserve_order(surface_nodes)
        self.surface_node = self.surface_nodes[0]
        self.control_nodes = _dedupe_preserve_order(controls)
        self.mode = LIVE_MESH_COLLISION_MODE
        self.report = None
        return True, "Picked {0} control(s) and {1} collision surface(s).".format(len(self.control_nodes), len(self.surface_nodes))

    def set_selected_records(self, record_nodes):
        self.selected_records = []
        for record_node in record_nodes or []:
            payload = _contact_payload(record_node)
            if payload:
                self.selected_records.append(payload["record"])
        self.selected_records = _dedupe_preserve_order(self.selected_records)
        return list(self.selected_records)

    def selected_record_payload(self):
        if not self.selected_records:
            return None
        return _contact_payload(self.selected_records[0])

    def load_selected_contact(self):
        payload = self.selected_record_payload()
        if not payload:
            return False, "Pick a saved contact in the list first."
        self.control_nodes = [payload["control"]]
        self.surface_node = payload["surface"]
        self.surface_nodes = [payload["surface"]]
        self.follow_surface_normal = bool(payload.get("follow_normal", DEFAULT_FOLLOW_NORMAL))
        self.mode = payload.get("mode", SURFACE_CONTACT_MODE)
        self.collision_offset = float(payload.get("offset", DEFAULT_COLLISION_OFFSET) or 0.0)
        self.collision_radius = float(payload.get("radius", DEFAULT_COLLISION_RADIUS) or 0.0)
        self.collision_follow_normal = bool(payload.get("follow_normal", DEFAULT_COLLISION_FOLLOW_NORMAL))
        self._refresh_live_callbacks()
        return True, "Loaded {0}.".format(payload["list_name"])

    def contact_entries(self, from_selection=True):
        if from_selection:
            selected_records = self.selected_records
            if selected_records:
                payloads = [_contact_payload(record_node) for record_node in selected_records]
                payloads = [payload for payload in payloads if payload]
                if payloads:
                    return payloads
            if self.control_nodes:
                payloads = []
                for node_name in self.control_nodes:
                    payloads.extend(_contact_payload(record_node) for record_node in _all_records_for_control(node_name))
                payloads = [payload for payload in payloads if payload]
                if payloads:
                    return _dedupe_preserve_order(payloads)
        return [_contact_payload(record_node) for record_node in _all_contact_records() if _contact_payload(record_node)]

    def collision_entries(self, from_selection=True):
        return [
            payload
            for payload in self.contact_entries(from_selection=from_selection)
            if payload and payload.get("mode") == LIVE_MESH_COLLISION_MODE
        ]

    def analyze_collision_setup(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        controls = self._resolved_controls()
        surfaces = self._resolved_surfaces()
        errors = []
        warnings = []
        existing_setups = []
        if not controls:
            errors.append("Pick one or more hand, foot, or object controls first.")
        if not surfaces:
            errors.append("Pick one or more mesh collision surfaces first.")
        for surface_node in surfaces:
            if not _surface_shape(surface_node):
                errors.append("{0} is not a sampleable mesh surface.".format(_short_name(surface_node)))
        for control_node in controls:
            existing_setups.extend(
                _contact_payload(record_node)
                for record_node in _all_records_for_control(control_node)
                if (_contact_payload(record_node) or {}).get("mode") == LIVE_MESH_COLLISION_MODE
            )
        existing_setups = [item for item in existing_setups if item]
        preview = None
        if controls and surfaces and _surface_shape(surfaces[0]):
            try:
                preview = _mesh_collision_query(surfaces[0], _world_translation(controls[0]))
            except Exception as exc:
                errors.append("Could not sample the selected collision surface: {0}".format(exc))
        if len(surfaces) > 1:
            warnings.append("All selected collision surfaces will be solved deterministically for every picked control.")
        if self.collision_radius <= 0.0:
            warnings.append("Proxy radius is 0.000 by default; no foot or hand volume is assumed.")
        self.report = {
            "mode": LIVE_MESH_COLLISION_MODE,
            "controls": controls,
            "surfaces": surfaces,
            "surface": surfaces[0] if surfaces else "",
            "offset": max(0.0, float(self.collision_offset)),
            "radius": max(0.0, float(self.collision_radius)),
            "follow_normal": bool(self.collision_follow_normal),
            "errors": _dedupe_preserve_order(errors),
            "warnings": _dedupe_preserve_order(warnings),
            "existing_setups": existing_setups,
            "preview": preview,
        }
        if errors:
            return False, "This mesh collision setup is not safe yet. Read the red notes below."
        if warnings:
            return True, "This mesh collision setup can work, but read the yellow notes first."
        return True, "This mesh collision setup looks ready."

    def create_or_update_collision(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        controls = self._resolved_controls()
        surfaces = self._resolved_surfaces()
        if not controls:
            return False, "Pick one or more controls first."
        if not surfaces:
            return False, "Pick one or more mesh collision surfaces first."
        updated = 0
        created = 0
        self.mode = LIVE_MESH_COLLISION_MODE
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaLiveMeshCollisionCreate")
            for control_node in controls:
                for surface_node in surfaces:
                    existing_record = _find_collision_record(control_node, surface_node)
                    existing_payload = _contact_payload(existing_record) if existing_record else {}
                    record_payload, error = _collision_record_from_inputs(
                        control_node,
                        surface_node,
                        existing_payload,
                        offset=self.collision_offset,
                        radius=self.collision_radius,
                        follow_normal=self.collision_follow_normal,
                    )
                    if error:
                        return False, error
                    if existing_record:
                        success, message = self._save_record_payload(existing_record, record_payload, control_node, surface_node)
                        if not success:
                            return False, message
                        target_record = existing_record
                        updated += 1
                    else:
                        target_record = _create_collision_record(control_node, surface_node, record_payload)
                        created += 1
                    if not _contact_payload(target_record):
                        return False, "The collision record could not be reloaded."
            for control_node in controls:
                group = [
                    _contact_payload(record_node)
                    for record_node in _all_records_for_control(control_node)
                ]
                group = [item for item in group if item and item.get("mode") == LIVE_MESH_COLLISION_MODE and item.get("enabled", True)]
                if group:
                    self._mute_live_callbacks()
                    solved, message = _apply_collision_group(group, force=False)
                    if not solved:
                        return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._refresh_live_callbacks()
        self.report = None
        total = updated + created
        if not total:
            return False, "Nothing was created or updated."
        if created and updated:
            return True, "Created {0} collision record(s) and updated {1}.".format(created, updated)
        if created:
            return True, "Created {0} live mesh collision record(s).".format(created)
        return True, "Updated {0} live mesh collision record(s).".format(updated)

    def analyze_setup(self):
        if self.mode == LIVE_MESH_COLLISION_MODE:
            return self.analyze_collision_setup()
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."

        controls = self._resolved_controls()
        surface_node = self._resolved_surface()
        errors = []
        warnings = []
        existing_setups = []
        closest_point = None
        surface_normal = None

        if not controls:
            errors.append("Pick one or more controls first.")
        if not surface_node:
            errors.append("Pick a mesh surface first.")
        if surface_node and not _surface_shape(surface_node):
            errors.append("The selected surface is not a mesh.")

        for node_name in controls:
            if not cmds.objExists(node_name):
                errors.append("{0} no longer exists.".format(_short_name(node_name)))
                continue
            existing_setups.extend(_contact_payload(record_node) for record_node in _all_records_for_control(node_name))

        existing_setups = [item for item in existing_setups if item]

        if controls and surface_node and _surface_shape(surface_node):
            try:
                closest_point, surface_normal, _ = _closest_point_and_normal(surface_node, _world_translation(controls[0]))
            except Exception as exc:
                errors.append("Could not sample the selected surface: {0}".format(exc))

        if not errors and not warnings and len(controls) > 1:
            warnings.append("This will create or update one contact record per control.")

        self.report = {
            "controls": controls,
            "surface": surface_node,
            "follow_normal": bool(self.follow_surface_normal),
            "errors": errors,
            "warnings": warnings,
            "existing_setups": existing_setups,
            "closest_point": closest_point,
            "surface_normal": surface_normal,
        }
        return True, _format_report(self.report)

    def report_text(self):
        return _format_report(self.report)

    def _save_record_payload(self, record_node, payload, control_node, surface_node):
        if not cmds.objExists(record_node):
            return False, "The saved record no longer exists."
        _set_bool_attr(record_node, SURFACE_CONTACT_ENABLED_ATTR, bool(payload.get("enabled", True)))
        _connect_message(control_node, record_node, SURFACE_CONTACT_CONTROL_ATTR)
        _connect_message(surface_node, record_node, SURFACE_CONTACT_SURFACE_ATTR)
        _set_contact_payload(record_node, payload)
        return True, "Updated {0}.".format(payload.get("list_name", _short_name(control_node)))

    def _record_from_inputs(self, control_node, surface_node, existing_payload=None):
        existing_payload = dict(existing_payload or {})
        current_matrix = _world_matrix(control_node)
        current_axes = _matrix_axes(current_matrix)
        control_position = _world_translation(control_node)
        closest_point, surface_normal, _face_index = _closest_point_and_normal(surface_node, control_position)
        if not closest_point or not surface_normal:
            return None, "Could not sample the selected surface."
        tangent_hint = existing_payload.get("tangent_hint") or _vector_tuple(current_axes[0])
        surface_normal_vector = _normalize(_vector(surface_normal))
        contact_normal = surface_normal_vector
        if _dot(_vector(control_position) - _vector(closest_point), contact_normal) < 0.0:
            contact_normal = contact_normal * -1.0
        tangent = _project_onto_plane(_vector(tangent_hint), contact_normal)
        if _length(tangent) <= 1.0e-8:
            tangent = _project_onto_plane(current_axes[0], contact_normal)
        if _length(tangent) <= 1.0e-8:
            tangent = _project_onto_plane(current_axes[2], contact_normal)
        if _length(tangent) <= 1.0e-8:
            tangent = om.MVector(1.0, 0.0, 0.0)
        tangent = _normalize(tangent)
        record_payload = {
            "id": existing_payload.get("id") or uuid.uuid4().hex[:8],
            "control": _node_long_name(control_node),
            "surface": _node_long_name(surface_node),
            "control_label": _short_name(control_node),
            "list_name": existing_payload.get("list_name") or _short_name(control_node),
            "enabled": bool(existing_payload.get("enabled", True)),
            "follow_normal": bool(self.follow_surface_normal),
            "tangent_hint": _vector_tuple(tangent),
            "contact_normal": _vector_tuple(contact_normal),
        }
        return record_payload, None

    def create_or_update_contact(self):
        if self.mode == LIVE_MESH_COLLISION_MODE:
            return self.create_or_update_collision()
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        controls = self._resolved_controls()
        surface_node = self._resolved_surface()
        if not controls:
            return False, "Pick one or more controls first."
        if not surface_node:
            return False, "Pick a mesh surface first."
        if not _surface_shape(surface_node):
            return False, "The selected surface is not a mesh."

        updated = 0
        created = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaSurfaceContactCreate")
            for control_node in controls:
                existing_record = _find_record(control_node, surface_node)
                existing_payload = _contact_payload(existing_record) if existing_record else {}
                record_payload, error = self._record_from_inputs(control_node, surface_node, existing_payload)
                if error:
                    return False, error
                if existing_record:
                    success, message = self._save_record_payload(existing_record, record_payload, control_node, surface_node)
                    if not success:
                        return False, message
                    updated += 1
                    target_record = existing_record
                else:
                    target_record = _create_contact_record(control_node, surface_node, record_payload)
                    created += 1
                current_payload = _contact_payload(target_record)
                if not current_payload:
                    return False, "The surface contact record could not be reloaded."
                self._mute_live_callbacks()
                solved, message = _apply_to_record_payload(current_payload, force=True)
                if not solved:
                    return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

        self.solve_active_contacts(force=True)
        self._refresh_live_callbacks()
        self.report = None
        total = updated + created
        if total == 0:
            return False, "Nothing was created or updated."
        if created and updated:
            return True, "Created {0} new contact(s) and updated {1} existing contact(s).".format(created, updated)
        if created:
            return True, "Created {0} new contact(s).".format(created)
        return True, "Updated {0} contact(s).".format(updated)

    def _target_records(self):
        if self.selected_records:
            records = [record_node for record_node in self.selected_records if cmds.objExists(record_node)]
        else:
            records = []
            for node_name in self._resolved_controls():
                records.extend(_all_records_for_control(node_name))
        if self.mode == LIVE_MESH_COLLISION_MODE:
            records = [
                record_node
                for record_node in records
                if (_contact_payload(record_node) or {}).get("mode") == LIVE_MESH_COLLISION_MODE
            ]
        return _dedupe_preserve_order(records)

    def enable_selected(self):
        records = self._target_records()
        if not records:
            return False, "Pick a saved contact first, or pick a control with saved contacts."
        count = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaSurfaceContactEnable")
            for record_node in records:
                if not cmds.objExists(record_node):
                    continue
                _set_record_enabled(record_node, True)
                count += 1
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self.solve_active_contacts(force=True)
        self._refresh_live_callbacks()
        self.report = None
        return True, "Enabled {0} contact(s).".format(count)

    def disable_selected(self):
        records = self._target_records()
        if not records:
            return False, "Pick a saved contact first, or pick a control with saved contacts."
        count = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaSurfaceContactDisable")
            for record_node in records:
                if not cmds.objExists(record_node):
                    continue
                _set_record_enabled(record_node, False)
                count += 1
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self.solve_active_contacts(force=True)
        self._refresh_live_callbacks()
        self.report = None
        return True, "Disabled {0} contact(s).".format(count)

    def delete_selected(self):
        records = self._target_records()
        if not records:
            return False, "Pick one or more saved contacts first."
        count = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaSurfaceContactDelete")
            for record_node in records:
                if _delete_record(record_node):
                    count += 1
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self.selected_records = []
        self.solve_active_contacts(force=True)
        self._refresh_live_callbacks()
        self.report = None
        return True, "Deleted {0} contact(s).".format(count)

    def delete_all(self):
        if self.mode == LIVE_MESH_COLLISION_MODE:
            return self.delete_all_collision()
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaSurfaceContactDeleteAll")
            deleted = _remove_all_records()
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self.selected_records = []
        self.solve_active_contacts(force=True)
        self._refresh_live_callbacks()
        self.report = None
        if not deleted:
            return False, "There are no saved surface contacts yet."
        return True, "Deleted all {0} saved contact(s).".format(deleted)

    def delete_all_collision(self):
        records = [
            payload.get("record")
            for record_node in _all_contact_records()
            for payload in [_contact_payload(record_node)]
            if payload and payload.get("mode") == LIVE_MESH_COLLISION_MODE
        ]
        records = [record_node for record_node in _dedupe_preserve_order(records) if record_node and cmds.objExists(record_node)]
        if not records:
            return False, "There are no saved mesh collision records yet."
        deleted = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaSurfaceContactDeleteAllCollision")
            for record_node in records:
                if _delete_record(record_node):
                    deleted += 1
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self.selected_records = []
        self.solve_active_contacts(force=True)
        self._refresh_live_callbacks()
        self.report = None
        return True, "Deleted all {0} mesh collision record(s).".format(deleted)

    def key_selected_state(self):
        records = self._target_records()
        if not records:
            return False, "Pick a saved contact first, or pick a control with saved contacts."
        current_time = float(cmds.currentTime(query=True))
        count = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaSurfaceContactKeyState")
            for record_node in records:
                if not cmds.objExists(record_node):
                    continue
                _set_bool_attr(record_node, SURFACE_CONTACT_ENABLED_ATTR, bool(_get_bool_attr(record_node, SURFACE_CONTACT_ENABLED_ATTR, True)))
                try:
                    cmds.setKeyframe(record_node, attribute=SURFACE_CONTACT_ENABLED_ATTR, time=current_time)
                    count += 1
                except Exception as exc:
                    return False, "Could not key the selected surface contact state: {0}".format(exc)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self.solve_active_contacts(force=True)
        self._refresh_live_callbacks()
        return True, "Keyed {0} contact state(s) on frame {1}.".format(count, _frame_label(current_time))

    def refresh_now(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        enabled_records = []
        for record_node in _all_contact_records():
            payload = _contact_payload(record_node)
            if payload and payload.get("enabled"):
                enabled_records.append(payload)
        if not enabled_records:
            return False, "There are no enabled surface contacts to refresh."
        solved = self.solve_active_contacts(force=True)
        if not solved:
            return False, "There are no enabled surface contacts to refresh."
        return True, "Clamped the active surface contacts on the current frame."

    def solve_active_contacts(self, force=False):
        if not MAYA_AVAILABLE or self._solving:
            return False
        self._solving = True
        try:
            records = []
            for record_node in _all_contact_records():
                payload = _contact_payload(record_node)
                if not payload:
                    continue
                if self.mode == LIVE_MESH_COLLISION_MODE and payload.get("mode") != LIVE_MESH_COLLISION_MODE:
                    continue
                records.append(payload)
            if not records:
                return False
            grouped = {}
            for payload in records:
                control_name = payload.get("control", "")
                if not control_name:
                    continue
                grouped.setdefault(control_name, []).append(payload)
            for control_name in sorted(grouped):
                payloads = grouped[control_name]
                enabled_payloads = [item for item in payloads if item.get("enabled", True)]
                collision_payloads = [item for item in enabled_payloads if item.get("mode") == LIVE_MESH_COLLISION_MODE]
                if collision_payloads:
                    self._mute_live_callbacks()
                    solved, message = _apply_collision_group(collision_payloads, force=bool(force))
                    if not solved:
                        self._set_status(message, success=False)
                        return False
                for payload in enabled_payloads:
                    if payload.get("mode") == LIVE_MESH_COLLISION_MODE:
                        continue
                    self._mute_live_callbacks()
                    solved, message = _apply_to_record_payload(payload, force=bool(force))
                    if not solved:
                        self._set_status(message, success=False)
                        return False
            if force:
                self.analyze_setup()
            return True
        finally:
            self._mute_live_callbacks(0.25)
            self._solving = False


class MayaLiveMeshCollisionController(MayaSurfaceContactController):
    """Explicit collision-mode controller for Surface Contact integrations."""

    def __init__(self):
        super(MayaLiveMeshCollisionController, self).__init__()
        self.mode = LIVE_MESH_COLLISION_MODE
        self.follow_surface_normal = DEFAULT_COLLISION_FOLLOW_NORMAL
        self.collision_follow_normal = DEFAULT_COLLISION_FOLLOW_NORMAL

    def analyze_setup(self):
        return self.analyze_collision_setup()

    def create_or_update_contact(self):
        return self.create_or_update_collision()


if QtWidgets:
    _WindowBase = type("MayaSurfaceContactWindowBase", (QtWidgets.QDialog,), {})


    class MayaSurfaceContactWindow(_WindowBase):
        """Collision-first Surface Contact window.

        The visible tool is deliberately mesh-collision only.  Legacy
        single-surface records remain readable by the backend for old scenes,
        but they are not exposed as the default workflow.
        """

        def __init__(self, controller, parent=None):
            super(MayaSurfaceContactWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.set_mode(LIVE_MESH_COLLISION_MODE)
            self.controller.set_status_callback(self._set_status)
            self._syncing_table = False
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Surface Contact")
            self.setMinimumWidth(560)
            self.setMinimumHeight(430)
            self.resize(760, 680)
            self._build_ui()
            self._sync_from_controller()

        def _build_ui(self):
            root_layout = QtWidgets.QVBoxLayout(self)
            root_layout.setContentsMargins(0, 0, 0, 0)
            scroll_area = QtWidgets.QScrollArea(self)
            scroll_area.setObjectName("aminateSurfaceContactScroll")
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAlwaysOff", QtCore.Qt.ScrollBarAlwaysOff))
            scroll_area.setVerticalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAsNeeded", QtCore.Qt.ScrollBarAsNeeded))
            scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
            content_widget = QtWidgets.QWidget()
            content_widget.setObjectName("aminateSurfaceContactContent")
            content_widget.setMinimumWidth(0)
            content_widget.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
            main_layout = QtWidgets.QVBoxLayout(content_widget)

            intro = QtWidgets.QLabel(
                "Keep hand, foot, or object controls on or outside one or more live mesh surfaces. "
                "Pick controls and meshes together, then create editable collision records."
            )
            intro.setWordWrap(True)
            main_layout.addWidget(intro)

            controls_row = QtWidgets.QGridLayout()
            self.controls_line = QtWidgets.QLineEdit()
            self.controls_line.setReadOnly(True)
            self.controls_line.setPlaceholderText("foot_ctrl, hand_ctrl")
            self.controls_line.setToolTip("Controls that must stay on or outside the selected collision meshes.")
            self.use_inputs_button = QtWidgets.QPushButton("Use Controls + Meshes")
            self.use_inputs_button.setToolTip(
                "Select one or more hand, foot, or object controls and one or more mesh surfaces in Maya, then load them together."
            )
            controls_row.addWidget(QtWidgets.QLabel("Controls"), 0, 0)
            controls_row.addWidget(self.controls_line, 0, 1)
            controls_row.addWidget(self.use_inputs_button, 1, 0, 1, 2)
            main_layout.addLayout(controls_row)

            surfaces_row = QtWidgets.QGridLayout()
            self.surface_line = QtWidgets.QLineEdit()
            self.surface_line.setReadOnly(True)
            self.surface_line.setPlaceholderText("floor, slope, step, ball")
            self.surface_line.setToolTip("One or more mesh surfaces used as collision objects.")
            self.use_surfaces_button = QtWidgets.QPushButton("Use Selected Meshes")
            self.use_surfaces_button.setToolTip(
                "Select one or more mesh surfaces in Maya and load them as the collision set."
            )
            surfaces_row.addWidget(QtWidgets.QLabel("Meshes"), 0, 0)
            surfaces_row.addWidget(self.surface_line, 0, 1)
            surfaces_row.addWidget(self.use_surfaces_button, 1, 0, 1, 2)
            main_layout.addLayout(surfaces_row)

            options_group = QtWidgets.QGroupBox("Collision Options")
            options_layout = QtWidgets.QGridLayout(options_group)
            self.offset_spin = QtWidgets.QDoubleSpinBox()
            self.offset_spin.setRange(0.0, 100000.0)
            self.offset_spin.setDecimals(4)
            self.offset_spin.setToolTip("Explicit distance to keep the control origin outside each mesh surface.")
            self.radius_spin = QtWidgets.QDoubleSpinBox()
            self.radius_spin.setRange(0.0, 100000.0)
            self.radius_spin.setDecimals(4)
            self.radius_spin.setToolTip("Explicit proxy radius for the hand or foot volume. Zero means no assumed radius.")
            self.follow_normal_check = QtWidgets.QCheckBox("Follow Surface Normal (Explicit)")
            self.follow_normal_check.setToolTip(
                "When enabled, rotate the control to the sampled surface normal. It is off until you choose it."
            )
            options_layout.addWidget(QtWidgets.QLabel("Offset"), 0, 0)
            options_layout.addWidget(self.offset_spin, 0, 1)
            options_layout.addWidget(QtWidgets.QLabel("Proxy Radius"), 0, 2)
            options_layout.addWidget(self.radius_spin, 0, 3)
            options_layout.addWidget(self.follow_normal_check, 1, 0, 1, 4)
            main_layout.addWidget(options_group)

            action_layout = QtWidgets.QVBoxLayout()
            self.check_button = QtWidgets.QPushButton("Check Setup")
            self.apply_button = QtWidgets.QPushButton("Create / Update Collision")
            self.refresh_button = QtWidgets.QPushButton("Refresh Now")
            self.apply_button.setProperty("aminateRole", "primary")
            self.check_button.setToolTip("Validate controls, meshes, offset, radius, and collision samples.")
            self.apply_button.setToolTip("Create or update live mesh collision records for every selected control and mesh.")
            self.refresh_button.setToolTip("Solve enabled collision records again on the current frame.")
            action_layout.addWidget(self.apply_button)
            secondary_action_grid = QtWidgets.QGridLayout()
            secondary_action_grid.setHorizontalSpacing(6)
            secondary_action_grid.setVerticalSpacing(6)
            secondary_action_grid.addWidget(self.check_button, 0, 0)
            secondary_action_grid.addWidget(self.refresh_button, 0, 1)
            secondary_action_grid.setColumnStretch(0, 1)
            secondary_action_grid.setColumnStretch(1, 1)
            action_layout.addLayout(secondary_action_grid)
            main_layout.addLayout(action_layout)

            collision_group = QtWidgets.QGroupBox("Saved Mesh Collision Records")
            collision_layout = QtWidgets.QVBoxLayout(collision_group)
            self.contacts_table = QtWidgets.QTableWidget(0, 6)
            self.contacts_table.setHorizontalHeaderLabels(
                ["Control", "Mesh", "Offset", "Radius", "Follow Normal", "State"]
            )
            self.contacts_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.contacts_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.contacts_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.contacts_table.setAlternatingRowColors(True)
            self.contacts_table.setToolTip(
                "Saved collision records. Select one or more rows to enable, disable, or delete them."
            )
            header = self.contacts_table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            for column_index in range(2, 6):
                header.setSectionResizeMode(column_index, QtWidgets.QHeaderView.ResizeToContents)
            collision_layout.addWidget(self.contacts_table, 1)

            management_grid = QtWidgets.QGridLayout()
            self.enable_button = QtWidgets.QPushButton("Enable Selected")
            self.disable_button = QtWidgets.QPushButton("Disable Selected")
            self.delete_button = QtWidgets.QPushButton("Delete Selected")
            self.delete_all_button = QtWidgets.QPushButton("Delete All Collision")
            self.delete_button.setProperty("aminateRole", "danger")
            self.delete_all_button.setProperty("aminateRole", "danger")
            self.enable_button.setToolTip("Enable the selected mesh collision records.")
            self.disable_button.setToolTip("Disable the selected mesh collision records without deleting them.")
            self.delete_button.setToolTip("Delete the selected mesh collision records.")
            self.delete_all_button.setToolTip("Delete every live mesh collision record while leaving legacy records untouched.")
            management_grid.setHorizontalSpacing(6)
            management_grid.setVerticalSpacing(6)
            management_grid.addWidget(self.enable_button, 0, 0)
            management_grid.addWidget(self.disable_button, 0, 1)
            management_grid.addWidget(self.delete_button, 1, 0)
            management_grid.addWidget(self.delete_all_button, 1, 1)
            management_grid.setColumnStretch(0, 1)
            management_grid.setColumnStretch(1, 1)
            collision_layout.addLayout(management_grid)
            main_layout.addWidget(collision_group, 1)

            self.report_box = QtWidgets.QPlainTextEdit()
            self.report_box.setReadOnly(True)
            self.report_box.setToolTip("Validation and collision-solver notes.")
            main_layout.addWidget(self.report_box, 1)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            main_layout.addWidget(self.status_label)

            footer_layout = QtWidgets.QVBoxLayout()
            self.brand_label = QtWidgets.QLabel(
                'Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL)
            )
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            self.brand_label.setWordWrap(True)
            footer_layout.addWidget(self.brand_label, 1)
            self.version_label = QtWidgets.QLabel("Version 0.3.6")
            footer_layout.addWidget(self.version_label)
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.setToolTip("Open Amir's Donate link.")
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

            self.use_inputs_button.clicked.connect(self._use_selected_inputs)
            self.use_surfaces_button.clicked.connect(self._use_selected_surfaces)
            self.offset_spin.valueChanged.connect(self._sync_to_controller)
            self.radius_spin.valueChanged.connect(self._sync_to_controller)
            self.follow_normal_check.toggled.connect(self._sync_to_controller)
            self.check_button.clicked.connect(self._analyze)
            self.apply_button.clicked.connect(self._apply)
            self.refresh_button.clicked.connect(self._refresh_now)
            self.enable_button.clicked.connect(self._enable_selected)
            self.disable_button.clicked.connect(self._disable_selected)
            self.delete_button.clicked.connect(self._delete_selected)
            self.delete_all_button.clicked.connect(self._delete_all)
            self.contacts_table.itemSelectionChanged.connect(self._on_contact_selection_changed)
            self.contacts_table.itemDoubleClicked.connect(self._load_selected_contact)
            scroll_area.setWidget(content_widget)
            root_layout.addWidget(scroll_area)

        def _selected_table_records(self):
            rows = sorted(set(index.row() for index in self.contacts_table.selectionModel().selectedRows()))
            record_nodes = []
            for row_index in rows:
                item = self.contacts_table.item(row_index, 0)
                record_node = item.data(QtCore.Qt.UserRole) if item else ""
                if record_node:
                    record_nodes.append(record_node)
            return record_nodes

        def _refresh_contacts_table(self):
            selected_records = set(self.controller.selected_records)
            payloads = self.controller.collision_entries(from_selection=False)
            self._syncing_table = True
            blocker = QtCore.QSignalBlocker(self.contacts_table)
            try:
                self.contacts_table.clearSelection()
                self.contacts_table.setRowCount(len(payloads))
                rows_to_select = []
                for row_index, payload in enumerate(payloads):
                    row_values = [
                        payload.get("control_label", _short_name(payload.get("control", ""))),
                        _short_name(payload.get("surface", "")),
                        "{0:.4f}".format(float(payload.get("offset", 0.0))),
                        "{0:.4f}".format(float(payload.get("radius", 0.0))),
                        "Yes" if payload.get("follow_normal") else "No",
                        "On" if payload.get("enabled") else "Off",
                    ]
                    for column_index, value in enumerate(row_values):
                        item = QtWidgets.QTableWidgetItem(str(value))
                        if column_index == 0:
                            item.setData(QtCore.Qt.UserRole, payload["record"])
                        self.contacts_table.setItem(row_index, column_index, item)
                    if payload["record"] in selected_records:
                        rows_to_select.append(row_index)
                del blocker
                for row_index in rows_to_select:
                    self.contacts_table.selectRow(row_index)
            finally:
                self._syncing_table = False

        def _sync_from_controller(self):
            self.controls_line.setText(", ".join(_short_name(node_name) for node_name in self.controller.control_nodes))
            self.surface_line.setText(", ".join(_short_name(node_name) for node_name in self.controller.surface_nodes))
            self.offset_spin.blockSignals(True)
            self.radius_spin.blockSignals(True)
            self.follow_normal_check.blockSignals(True)
            self.offset_spin.setValue(float(self.controller.collision_offset))
            self.radius_spin.setValue(float(self.controller.collision_radius))
            self.follow_normal_check.setChecked(bool(self.controller.collision_follow_normal))
            self.offset_spin.blockSignals(False)
            self.radius_spin.blockSignals(False)
            self.follow_normal_check.blockSignals(False)
            self._refresh_contacts_table()
            self.report_box.setPlainText(_format_report(self.controller.report))

        def _sync_to_controller(self):
            self.controller.set_mode(LIVE_MESH_COLLISION_MODE)
            self.controller.control_nodes = _resolve_controls_from_text(self.controls_line.text())
            self.controller.collision_offset = max(0.0, float(self.offset_spin.value()))
            self.controller.collision_radius = max(0.0, float(self.radius_spin.value()))
            self.controller.collision_follow_normal = bool(self.follow_normal_check.isChecked())
            self.controller.follow_surface_normal = self.controller.collision_follow_normal

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)
            self.report_box.setPlainText(_format_report(self.controller.report))
            self._refresh_contacts_table()

        def _use_selected_inputs(self):
            success, message = self.controller.set_collision_inputs_from_selection()
            self._sync_from_controller()
            self._set_status(message, success)

        def _use_selected_surfaces(self):
            success, message = self.controller.set_surfaces_from_selection()
            self._sync_from_controller()
            self._set_status(message, success)

        def _analyze(self):
            self._sync_to_controller()
            success, message = self.controller.analyze_collision_setup()
            self._set_status(message, success)

        def _apply(self):
            self._sync_to_controller()
            if not self.controller._resolved_controls() or not self.controller._resolved_surfaces():
                success, message = self.controller.set_collision_inputs_from_selection()
                if not success:
                    self._set_status(message, False)
                    return False
            success, message = self.controller.create_or_update_collision()
            self._sync_from_controller()
            self._set_status(message, success)
            return success

        def _refresh_now(self):
            self._sync_to_controller()
            success, message = self.controller.refresh_now()
            self._sync_from_controller()
            self._set_status(message, success)

        def _enable_selected(self):
            self.controller.set_selected_records(self._selected_table_records())
            success, message = self.controller.enable_selected()
            self._sync_from_controller()
            self._set_status(message, success)

        def _disable_selected(self):
            self.controller.set_selected_records(self._selected_table_records())
            success, message = self.controller.disable_selected()
            self._sync_from_controller()
            self._set_status(message, success)

        def _delete_selected(self):
            self.controller.set_selected_records(self._selected_table_records())
            success, message = self.controller.delete_selected()
            self._sync_from_controller()
            self._set_status(message, success)

        def _delete_all(self):
            success, message = self.controller.delete_all_collision()
            self._sync_from_controller()
            self._set_status(message, success)

        def _on_contact_selection_changed(self):
            if self._syncing_table:
                return
            record_nodes = self._selected_table_records()
            self.controller.set_selected_records(record_nodes)
            if len(record_nodes) == 1:
                self.controller.load_selected_contact()
            self._sync_from_controller()

        def _load_selected_contact(self, *_args):
            record_nodes = self._selected_table_records()
            self.controller.set_selected_records(record_nodes)
            success, message = self.controller.load_selected_contact()
            self._sync_from_controller()
            self._set_status(message, success)

        def _open_follow_url(self, url=None):
            if _open_external_url(url or FOLLOW_AMIR_URL):
                self._set_status("Opened followamir.com.", True)
            else:
                self._set_status("Could not open followamir.com from this Maya session.", False)

        def _open_donate_url(self):
            if DONATE_URL and _open_external_url(DONATE_URL):
                self._set_status("Opened the Donate link.", True)
            else:
                self._set_status("Could not open the Donate link from this Maya session.", False)

        def closeEvent(self, event):
            # Keep callbacks and the Qt wrapper alive for Maya 2026.
            self.hide()
            event.accept()

def _close_existing_window():
    """Hide and return the existing window instead of destroying Qt state."""
    global GLOBAL_CONTROLLER, GLOBAL_WINDOW
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.hide()
            GLOBAL_CONTROLLER = getattr(GLOBAL_WINDOW, "controller", GLOBAL_CONTROLLER)
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
    if QtWidgets:
        application = QtWidgets.QApplication.instance()
        if application and hasattr(application, "topLevelWidgets"):
            for widget in application.topLevelWidgets():
                if widget is None:
                    continue
                try:
                    if getattr(widget, "objectName", lambda: "")() == WINDOW_OBJECT_NAME:
                        widget.hide()
                        GLOBAL_WINDOW = widget
                        GLOBAL_CONTROLLER = getattr(widget, "controller", GLOBAL_CONTROLLER)
                        return widget
                except Exception:
                    pass
    return None


def launch_maya_surface_contact(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not (MAYA_AVAILABLE and QtWidgets):
        raise RuntimeError("Maya Surface Contact must be launched inside Maya with PySide available.")

    existing = _close_existing_window()
    if existing is not None:
        existing.show()
        try:
            existing.raise_()
            existing.activateWindow()
        except Exception:
            pass
        return existing

    GLOBAL_CONTROLLER = MayaSurfaceContactController()
    GLOBAL_WINDOW = MayaSurfaceContactWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "DONATE_URL",
    "FOLLOW_AMIR_URL",
    "MayaSurfaceContactController",
    "MayaSurfaceContactWindow",
    "launch_maya_surface_contact",
]
