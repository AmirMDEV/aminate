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
    import maya.OpenMayaUI as omui
    import maya.utils as maya_utils

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    omui = None
    maya_utils = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    import shiboken6 as shiboken

    QT_BINDING = "PySide6"
except Exception:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
        import shiboken2 as shiboken

        QT_BINDING = "PySide2"
    except Exception:
        QtCore = None
        QtGui = None
        QtWidgets = None
        shiboken = None
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
    selection = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    for node_name in selection:
        resolved = _surface_transform(node_name)
        if resolved:
            return resolved
    return ""


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


def _contact_constraint_nodes(payload):
    nodes = []
    for node_name in (payload or {}).get("constraint_nodes", []) or []:
        if node_name and cmds.objExists(node_name):
            nodes.append(_node_long_name(node_name))
    return _dedupe_preserve_order(nodes)


def _constraint_weight_aliases(constraint_node):
    aliases = []
    try:
        alias_data = cmds.aliasAttr(constraint_node, query=True) or []
    except Exception:
        alias_data = []
    for index in range(0, len(alias_data), 2):
        alias = alias_data[index]
        plug = alias_data[index + 1] if index + 1 < len(alias_data) else ""
        plug_lower = str(plug).lower()
        if "weight" in plug_lower or plug_lower.endswith("w0"):
            aliases.append(alias)
    if not aliases:
        for candidate in ("w0", "targetW0"):
            try:
                if cmds.attributeQuery(candidate, node=constraint_node, exists=True):
                    aliases.append(candidate)
                    break
            except Exception:
                pass
    return _dedupe_preserve_order(aliases)


def _set_constraint_enabled(constraint_nodes, enabled):
    value = 1.0 if enabled else 0.0
    for node_name in _contact_constraint_nodes({"constraint_nodes": constraint_nodes}):
        for alias in _constraint_weight_aliases(node_name):
            try:
                cmds.setAttr("{0}.{1}".format(node_name, alias), value)
            except Exception:
                pass


def _record_enabled_has_anim(record_node):
    plug = "{0}.{1}".format(record_node, SURFACE_CONTACT_ENABLED_ATTR)
    try:
        return bool(cmds.listConnections(plug, source=True, destination=False, type="animCurve") or [])
    except Exception:
        return False


def _set_record_enabled(record_node, enabled):
    _set_bool_attr(record_node, SURFACE_CONTACT_ENABLED_ATTR, bool(enabled))
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


def _sync_contact_constraints(record_node, payload, control_node, surface_node, recreate=False):
    if recreate:
        _delete_contact_constraints(payload)
    existing = _contact_constraint_nodes(payload)
    if existing and not recreate:
        _set_constraint_enabled(existing, bool(payload.get("enabled", True)))
        return True, None

    created_nodes = []
    try:
        point_constraint = cmds.pointOnPolyConstraint(surface_node, control_node)[0]
        created_nodes.append(_node_long_name(point_constraint))
    except Exception as exc:
        try:
            geometry_constraint = cmds.geometryConstraint(surface_node, control_node)[0]
            created_nodes.append(_node_long_name(geometry_constraint))
        except Exception as fallback_exc:
            return False, "Could not create the live surface clamp: {0}".format(fallback_exc or exc)

    if payload.get("follow_normal", DEFAULT_FOLLOW_NORMAL):
        try:
            normal_constraint = cmds.normalConstraint(surface_node, control_node)[0]
            created_nodes.append(_node_long_name(normal_constraint))
        except Exception as exc:
            _warning("Could not create the live surface normal follow: {0}".format(exc))

    payload["constraint_nodes"] = created_nodes
    _set_contact_payload(record_node, payload)
    _set_constraint_enabled(created_nodes, bool(payload.get("enabled", True)))
    return True, None


def _find_record(control_node, surface_node):
    control_long = _node_long_name(control_node)
    surface_long = _node_long_name(surface_node)
    for record_node in _all_contact_records():
        payload = _contact_payload(record_node)
        if not payload:
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


def _selected_record_nodes():
    selected = []
    for node_name in cmds.ls(selection=True, long=True, type="transform") or []:
        if _get_bool_attr(node_name, SURFACE_CONTACT_MARKER_ATTR, False):
            selected.append(_node_long_name(node_name))
    return _dedupe_preserve_order(selected)


def _node_mobject(node_name):
    if not MAYA_AVAILABLE or not node_name or not cmds.objExists(node_name):
        return None
    try:
        selection_list = om.MSelectionList()
        selection_list.add(node_name)
        return selection_list.getDependNode(0)
    except Exception:
        return None


def _apply_to_record_payload(payload, force=False):
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
        self.follow_surface_normal = DEFAULT_FOLLOW_NORMAL
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
            for node_name in (payload.get("control", ""), payload.get("surface", "")):
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
        return self.surface_node if self.surface_node and cmds.objExists(self.surface_node) else ""

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
        self.report = None
        return True, "Picked the surface {0}.".format(_short_name(surface_node))

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
        self.follow_surface_normal = bool(payload.get("follow_normal", DEFAULT_FOLLOW_NORMAL))
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

    def analyze_setup(self):
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
            return [record_node for record_node in self.selected_records if cmds.objExists(record_node)]
        records = []
        for node_name in self._resolved_controls():
            records.extend(_all_records_for_control(node_name))
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
                records.append(payload)
            if not records:
                return False
            solved_controls = {}
            for payload in records:
                solved_controls[payload.get("control", "")] = payload
            for payload in solved_controls.values():
                control_node = payload.get("control", "")
                surface_node = payload.get("surface", "")
                record_node = payload.get("record", "")
                self._mute_live_callbacks()
                _apply_to_record_payload(payload, force=bool(force))
            if force:
                self.analyze_setup()
            return True
        finally:
            self._mute_live_callbacks(0.25)
            self._solving = False


if QtWidgets:
    _WindowBase = type("MayaSurfaceContactWindowBase", (QtWidgets.QDialog,), {})


    class MayaSurfaceContactWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaSurfaceContactWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.set_status_callback(self._set_status)
            self._syncing_table = False
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Surface Contact")
            self.setMinimumWidth(640)
            self.setMinimumHeight(480)
            self.resize(820, 760)
            self._build_ui()
            self._sync_from_controller()

        def _build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            intro = QtWidgets.QLabel(
                "Use this for feet, hands, or any control that should stay on a selected mesh surface while the scene moves."
            )
            intro.setWordWrap(True)
            main_layout.addWidget(intro)

            control_row = QtWidgets.QHBoxLayout()
            self.controls_line = QtWidgets.QLineEdit()
            self.controls_line.setPlaceholderText("foot_ctrl, hand_ctrl")
            self.controls_line.setToolTip("The control or controls that should stick to the surface.")
            self.use_selection_button = QtWidgets.QPushButton("Load Selected Control(s)")
            self.use_selection_button.setToolTip("Load the selected control(s) from the current Maya selection into the control box.")
            control_row.addWidget(QtWidgets.QLabel("Control(s)"))
            control_row.addWidget(self.controls_line, 1)
            control_row.addWidget(self.use_selection_button)
            main_layout.addLayout(control_row)

            surface_row = QtWidgets.QHBoxLayout()
            self.surface_line = QtWidgets.QLineEdit()
            self.surface_line.setPlaceholderText("surface mesh")
            self.surface_line.setToolTip("The floor, wall, prop, or body mesh to stick to.")
            self.use_surface_button = QtWidgets.QPushButton("Load Selected Surface")
            self.use_surface_button.setToolTip("Load the selected surface mesh from the current Maya selection into the surface box.")
            surface_row.addWidget(QtWidgets.QLabel("Surface"))
            surface_row.addWidget(self.surface_line, 1)
            surface_row.addWidget(self.use_surface_button)
            main_layout.addLayout(surface_row)

            options_row = QtWidgets.QHBoxLayout()
            self.follow_normal_check = QtWidgets.QCheckBox("Follow Surface Normal")
            self.follow_normal_check.setToolTip("Turn this on to keep the control aligned to the surface normal.")
            options_row.addWidget(self.follow_normal_check)
            options_row.addStretch(1)
            main_layout.addLayout(options_row)

            action_row = QtWidgets.QHBoxLayout()
            self.check_button = QtWidgets.QPushButton("Check Setup")
            self.apply_button = QtWidgets.QPushButton("Create / Update Contact")
            self.key_state_button = QtWidgets.QPushButton("Key State")
            self.refresh_button = QtWidgets.QPushButton("Refresh Now")
            self.check_button.setToolTip("Check the selected control and surface before creating or updating the contact.")
            self.apply_button.setToolTip("Create or refresh the live surface contact clamp setup.")
            self.key_state_button.setToolTip("Key the selected contact state on the current frame so it can turn on or off in animation.")
            self.refresh_button.setToolTip("Force the live clamp to solve again on the current frame. The live callbacks also keep it updated while you move the control or surface.")
            action_row.addWidget(self.check_button)
            action_row.addWidget(self.apply_button)
            action_row.addWidget(self.key_state_button)
            action_row.addWidget(self.refresh_button)
            main_layout.addLayout(action_row)

            contact_group = QtWidgets.QGroupBox("Saved Contacts In Scene")
            contact_layout = QtWidgets.QVBoxLayout(contact_group)
            self.contacts_table = QtWidgets.QTableWidget(0, 5)
            self.contacts_table.setHorizontalHeaderLabels(["Control", "Surface", "Offset", "Normal", "State"])
            self.contacts_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.contacts_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.contacts_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.contacts_table.setAlternatingRowColors(True)
            self.contacts_table.setToolTip("Pick a saved row to turn it on, turn it off, key it, or delete it.")
            header = self.contacts_table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
            contact_layout.addWidget(self.contacts_table, 1)

            manage_row = QtWidgets.QHBoxLayout()
            self.enable_button = QtWidgets.QPushButton("Turn On Selected")
            self.disable_button = QtWidgets.QPushButton("Turn Off Selected")
            self.delete_button = QtWidgets.QPushButton("Delete Selected")
            self.delete_all_button = QtWidgets.QPushButton("Delete All Contacts")
            self.enable_button.setToolTip("Turn the selected surface contact rows on so they keep solving.")
            self.disable_button.setToolTip("Turn the selected surface contact rows off and leave the last solved pose in place.")
            self.delete_button.setToolTip("Remove the selected saved contact rows.")
            self.delete_all_button.setToolTip("Remove every saved surface contact from the scene.")
            manage_row.addWidget(self.enable_button)
            manage_row.addWidget(self.disable_button)
            manage_row.addWidget(self.delete_button)
            manage_row.addWidget(self.delete_all_button)
            contact_layout.addLayout(manage_row)
            main_layout.addWidget(contact_group, 1)

            self.report_box = QtWidgets.QPlainTextEdit()
            self.report_box.setReadOnly(True)
            self.report_box.setToolTip("Helpful notes about the selected control and surface.")
            main_layout.addWidget(self.report_box, 1)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            main_layout.addWidget(self.status_label)

            footer_layout = QtWidgets.QHBoxLayout()
            self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            self.brand_label.setWordWrap(True)
            footer_layout.addWidget(self.brand_label, 1)
            self.version_label = QtWidgets.QLabel("Version 0.3.5 Beta")
            footer_layout.addWidget(self.version_label)
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

            self.use_selection_button.clicked.connect(self._use_selected_controls)
            self.use_surface_button.clicked.connect(self._use_selected_surface)
            self.follow_normal_check.toggled.connect(self._sync_to_controller)
            self.check_button.clicked.connect(self._analyze)
            self.apply_button.clicked.connect(self._apply)
            self.key_state_button.clicked.connect(self._key_selected_state)
            self.refresh_button.clicked.connect(self._refresh_now)
            self.enable_button.clicked.connect(self._enable_selected)
            self.disable_button.clicked.connect(self._disable_selected)
            self.delete_button.clicked.connect(self._delete_selected)
            self.delete_all_button.clicked.connect(self._delete_all)
            self.contacts_table.itemSelectionChanged.connect(self._on_contact_selection_changed)
            self.contacts_table.itemDoubleClicked.connect(self._load_selected_contact)

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
            payloads = self.controller.contact_entries(from_selection=False)
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
                        "0.00",
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
            self.surface_line.setText(_short_name(self.controller.surface_node))
            self.follow_normal_check.blockSignals(True)
            self.follow_normal_check.setChecked(bool(self.controller.follow_surface_normal))
            self.follow_normal_check.blockSignals(False)
            self._refresh_contacts_table()
            self.report_box.setPlainText(_format_report(self.controller.report))

        def _sync_to_controller(self):
            self.controller.control_nodes = _resolve_controls_from_text(self.controls_line.text())
            resolved_surface = self.surface_line.text().strip()
            self.controller.surface_node = _node_long_name(resolved_surface) if resolved_surface and cmds.objExists(resolved_surface) else resolved_surface
            self.controller.follow_surface_normal = bool(self.follow_normal_check.isChecked())

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)
            self.report_box.setPlainText(_format_report(self.controller.report))
            self._refresh_contacts_table()

        def _use_selected_controls(self):
            success, message = self.controller.set_controls_from_selection()
            self._sync_from_controller()
            self._set_status(message, success)

        def _use_selected_surface(self):
            success, message = self.controller.set_surface_from_selection()
            self._sync_from_controller()
            self._set_status(message, success)

        def _analyze(self):
            self._sync_to_controller()
            success, message = self.controller.analyze_setup()
            self._set_status(message, success)

        def _apply(self):
            self._sync_to_controller()
            success, message = self.controller.create_or_update_contact()
            self._sync_from_controller()
            self._set_status(message, success)

        def _refresh_now(self):
            self._sync_to_controller()
            success, message = self.controller.refresh_now()
            self._sync_from_controller()
            self._set_status(message, success)

        def _key_selected_state(self):
            self.controller.set_selected_records(self._selected_table_records())
            success, message = self.controller.key_selected_state()
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
            success, message = self.controller.delete_all()
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
            try:
                self.controller.shutdown()
            except Exception:
                pass
            try:
                super(MayaSurfaceContactWindow, self).closeEvent(event)
            except TypeError:
                QtWidgets.QDialog.closeEvent(self, event)


def _delete_workspace_control(workspace_control_name):
    if MAYA_AVAILABLE and cmds.workspaceControl(workspace_control_name, exists=True):
        try:
            cmds.deleteUI(workspace_control_name, control=True)
        except Exception:
            pass


def _close_existing_window():
    global GLOBAL_WINDOW
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.close()
            GLOBAL_WINDOW.deleteLater()
        except Exception:
            pass
    GLOBAL_WINDOW = None
    _delete_workspace_control(WORKSPACE_CONTROL_NAME)
    if QtWidgets:
        application = QtWidgets.QApplication.instance()
        if application and hasattr(application, "topLevelWidgets"):
            for widget in application.topLevelWidgets():
                if widget is None:
                    continue
                try:
                    if getattr(widget, "objectName", lambda: "")() == WINDOW_OBJECT_NAME:
                        widget.close()
                        widget.deleteLater()
                except Exception:
                    pass


def launch_maya_surface_contact(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not (MAYA_AVAILABLE and QtWidgets):
        raise RuntimeError("Maya Surface Contact must be launched inside Maya with PySide available.")

    _close_existing_window()
    if dock:
        _delete_workspace_control(WORKSPACE_CONTROL_NAME)

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
