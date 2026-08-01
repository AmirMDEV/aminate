"""
maya_rig_scale_export.py

Non-destructive rig-scale export copy builder for Maya 2022-2026.
"""

from __future__ import absolute_import, division, print_function

import hashlib
import json
import os
import math
import struct
import subprocess
import sys
import tempfile
import time
import traceback

import maya_skinning_cleanup as skin_cleanup

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaAnim as oma

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    mel = None
    om = None
    oma = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtWidgets

    QT_BINDING = "PySide6"
except Exception:
    try:
        from PySide2 import QtWidgets

        QT_BINDING = "PySide2"
    except Exception:
        QtWidgets = None
        QT_BINDING = None


WINDOW_OBJECT_NAME = "mayaRigScaleExportWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
DEFAULT_COPY_SUFFIX = "_rigScaleExport"
GROUP_SCALE_ATTR = "amirRigScaleFactor"
GROUP_SCALE_PERCENT_ATTR = "aminateRigScalePercent"
GROUP_NOTE_ATTR = "amirExportNote"
VALUE_EPSILON = 1.0e-5
POINT_EPSILON = 1.0e-3
NORMAL_EPSILON = 1.0e-4
ANIMATION_DEFORMATION_RELATIVE_LIMIT = 2.0e-4
ANIMATION_DEFORMATION_MAX_CM = 0.05
# Maya can re-evaluate connected transforms with sub-micrometre float noise
# even when no authored value changes. Geometry/topology/weights/connections
# remain exact; only numeric transform/custom-channel reads use this tolerance.
SOURCE_STATE_EPSILON = 1.0e-6

# Scale specifications are deliberately represented as strings.  This keeps
# the controller easy to drive from Maya, Qt, and Maya-free contract tests.
SCALE_MODE_FACTOR_PERCENT = "factor_percent"
SCALE_MODE_TARGET_HEIGHT = "target_height"
SCALE_MODE_HEIGHT_CHANGE = "height_change"
SCALE_MODE_FACTOR = "factor"
SCALE_MODE_PERCENT = "percent"
UNIT_SCENE = "scene"
UNIT_MM = "mm"
UNIT_CM = "cm"
UNIT_M = "m"
MEASUREMENT_AXIS_DEFAULT = "Y"
MEASUREMENT_AXES = ("X", "Y", "Z")
LINEAR_UNIT_TO_CM = {
    "mm": 0.1,
    "cm": 1.0,
    "m": 100.0,
    "km": 100000.0,
    "in": 2.54,
    "ft": 30.48,
    "yd": 91.44,
    "mi": 160934.4,
    "um": 0.0001,
}
DISPLAY_UNIT_LABELS = {
    UNIT_SCENE: "Scene Units",
    UNIT_MM: "mm",
    UNIT_CM: "cm",
    UNIT_M: "m",
}
FBX_PLUGIN_NAME = "fbxmaya"

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None

_qt_flag = skin_cleanup._qt_flag
_style_donate_button = skin_cleanup._style_donate_button
_open_external_url = skin_cleanup._open_external_url
_maya_main_window = skin_cleanup._maya_main_window
_dedupe_preserve_order = skin_cleanup._dedupe_preserve_order
_short_name = skin_cleanup._short_name
_uuid_for_node = skin_cleanup._uuid_for_node
_node_long_name = skin_cleanup._node_long_name
_unique_name = skin_cleanup._unique_name
_dag_path = skin_cleanup._dag_path
_depend_node = skin_cleanup._depend_node
_mesh_fn = skin_cleanup._mesh_fn
_all_vertex_component = skin_cleanup._all_vertex_component
_distance_between_points = skin_cleanup._distance_between_points
_find_skin_cluster = skin_cleanup._find_skin_cluster
_unsupported_history_nodes = skin_cleanup._unsupported_history_nodes
_capture_shading_assignments = skin_cleanup._capture_shading_assignments
_normalized_shading_assignments = skin_cleanup._normalized_shading_assignments
_apply_shading_assignments = skin_cleanup._apply_shading_assignments
_capture_uv_summary = skin_cleanup._capture_uv_summary
_capture_color_summary = skin_cleanup._capture_color_summary
_capture_edge_smoothing = skin_cleanup._capture_edge_smoothing
_capture_world_normals = skin_cleanup._capture_world_normals
_capture_topology_signature = skin_cleanup._capture_topology_signature
_capture_world_points = skin_cleanup._capture_world_points
_capture_skin_data = skin_cleanup._capture_skin_data
_max_normal_delta = skin_cleanup._max_normal_delta
_unlock_transform_channels = skin_cleanup._unlock_transform_channels


def normalize_scale_mode(mode):
    """Return the canonical scale mode used by the controller."""
    value = str(mode or "").strip().lower().replace("-", "_").replace(" ", "_").replace("/", "_")
    value = value.replace("(", "").replace(")", "").replace("+", "")
    aliases = {
        "factor_percent": SCALE_MODE_FACTOR_PERCENT,
        "factor__percent": SCALE_MODE_FACTOR_PERCENT,
        "factor_percent_": SCALE_MODE_FACTOR_PERCENT,
        "factorpercent": SCALE_MODE_FACTOR_PERCENT,
        "factor": SCALE_MODE_FACTOR,
        "percent": SCALE_MODE_PERCENT,
        "percentage": SCALE_MODE_PERCENT,
        "target_height": SCALE_MODE_TARGET_HEIGHT,
        "targetheight": SCALE_MODE_TARGET_HEIGHT,
        "height_change": SCALE_MODE_HEIGHT_CHANGE,
        "height_change__": SCALE_MODE_HEIGHT_CHANGE,
        "height_change_": SCALE_MODE_HEIGHT_CHANGE,
        "heightchange": SCALE_MODE_HEIGHT_CHANGE,
        "delta": SCALE_MODE_HEIGHT_CHANGE,
    }
    if value not in aliases:
        raise ValueError("Unknown scale mode: {0}. Use Factor / Percent, Target Height, or Height Change.".format(mode))
    return aliases[value]


def normalize_measurement_axis(axis):
    value = str(axis or MEASUREMENT_AXIS_DEFAULT).strip().upper()
    if value not in MEASUREMENT_AXES:
        raise ValueError("Measurement axis must be X, Y, or Z.")
    return value


def normalize_linear_unit(unit, scene_unit="cm"):
    value = str(unit or UNIT_SCENE).strip().lower()
    if value in ("scene", "scene_units", "sceneunits"):
        return UNIT_SCENE
    if value not in LINEAR_UNIT_TO_CM:
        raise ValueError("Unsupported measurement unit: {0}. Use Scene Units, mm, cm, or m.".format(unit))
    return value


def linear_unit_to_cm(value, unit, scene_unit="cm"):
    """Convert a linear value to centimetres without changing Maya's scene unit."""
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError("Measurement values must be finite numbers.")
    unit_name = normalize_linear_unit(unit, scene_unit=scene_unit)
    if unit_name == UNIT_SCENE:
        scene_name = {
            "millimeter": "mm",
            "millimeters": "mm",
            "centimeter": "cm",
            "centimeters": "cm",
            "meter": "m",
            "meters": "m",
            "kilometer": "km",
            "kilometers": "km",
        }.get(str(scene_unit or UNIT_CM).strip().lower(), str(scene_unit or UNIT_CM).strip().lower())
        if scene_name not in LINEAR_UNIT_TO_CM:
            raise ValueError("Maya scene linear unit is not supported: {0}.".format(scene_unit))
        return numeric_value * LINEAR_UNIT_TO_CM[scene_name]
    return numeric_value * LINEAR_UNIT_TO_CM[unit_name]


def convert_linear_value(value, from_unit, to_unit, scene_unit="cm"):
    """Convert a value between Scene Units/mm/cm/m using Maya's scene unit."""
    centimetres = linear_unit_to_cm(value, from_unit, scene_unit=scene_unit)
    target = normalize_linear_unit(to_unit, scene_unit=scene_unit)
    if target == UNIT_SCENE:
        scene_name = {
            "millimeter": "mm",
            "millimeters": "mm",
            "centimeter": "cm",
            "centimeters": "cm",
            "meter": "m",
            "meters": "m",
            "kilometer": "km",
            "kilometers": "km",
        }.get(str(scene_unit or UNIT_CM).strip().lower(), str(scene_unit or UNIT_CM).strip().lower())
        if scene_name not in LINEAR_UNIT_TO_CM:
            raise ValueError("Maya scene linear unit is not supported: {0}.".format(scene_unit))
        return centimetres / LINEAR_UNIT_TO_CM[scene_name]
    return centimetres / LINEAR_UNIT_TO_CM[target]


def measure_world_points(points, axis=MEASUREMENT_AXIS_DEFAULT):
    """Measure a mesh-point bound along one world axis.

    Control curves and joints are intentionally not accepted here.  Callers
    pass the world points captured from analyzed skinned/render meshes.
    """
    axis_name = normalize_measurement_axis(axis)
    axis_index = MEASUREMENT_AXES.index(axis_name)
    values = []
    for point in points or []:
        try:
            value = getattr(point, axis_name.lower())
        except Exception:
            try:
                value = point[axis_index]
            except Exception:
                continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric_value):
            values.append(numeric_value)
    if not values:
        return {
            "axis": axis_name,
            "measurable": False,
            "min": None,
            "max": None,
            "height": None,
            "point_count": 0,
        }
    minimum = min(values)
    maximum = max(values)
    height = maximum - minimum
    return {
        "axis": axis_name,
        "measurable": bool(height > VALUE_EPSILON),
        "min": minimum,
        "max": maximum,
        "height": height,
        "point_count": len(values),
    }


def measure_mesh_reports(mesh_reports, axis=MEASUREMENT_AXIS_DEFAULT):
    points = []
    for mesh_report in mesh_reports or []:
        points.extend(mesh_report.get("world_points") or [])
    measurement = measure_world_points(points, axis=axis)
    measurement["mesh_count"] = len(mesh_reports or [])
    return measurement


def calculate_scale_factor(mode, value, current_height, unit=UNIT_SCENE, scene_unit="cm", axis=MEASUREMENT_AXIS_DEFAULT):
    """Derive an exact original-relative scale factor from a user specification."""
    mode_name = normalize_scale_mode(mode)
    try:
        height_scene = float(current_height)
    except (TypeError, ValueError):
        raise ValueError("No measurable skinned mesh height was found.")
    if not math.isfinite(height_scene) or height_scene <= VALUE_EPSILON:
        raise ValueError("No measurable skinned mesh height was found on measurement axis {0}.".format(normalize_measurement_axis(axis)))
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError("Scale values must be finite numbers.")

    if mode_name == SCALE_MODE_FACTOR:
        factor = numeric_value
    elif mode_name in (SCALE_MODE_FACTOR_PERCENT, SCALE_MODE_PERCENT):
        factor = numeric_value / 100.0
    else:
        target_scene = convert_linear_value(numeric_value, unit, UNIT_SCENE, scene_unit=scene_unit)
        if mode_name == SCALE_MODE_HEIGHT_CHANGE:
            target_scene += height_scene
        if not math.isfinite(target_scene) or target_scene <= VALUE_EPSILON:
            raise ValueError("The resulting character height must be greater than zero.")
        factor = target_scene / height_scene

    if not math.isfinite(factor) or factor <= VALUE_EPSILON:
        raise ValueError("The resulting scale must be greater than zero.")
    return float(factor)


def format_measurement(measurement, factor=None, display_unit=UNIT_SCENE, scene_unit="cm"):
    """Format current/result bounds for report and status surfaces."""
    if not measurement or not measurement.get("measurable"):
        return "Current height: unavailable (no measurable mesh points)."
    unit_name = normalize_linear_unit(display_unit, scene_unit=scene_unit)
    current_value = convert_linear_value(measurement["height"], UNIT_SCENE, unit_name, scene_unit=scene_unit)
    label = DISPLAY_UNIT_LABELS.get(unit_name, unit_name)
    text = "Current {0}-axis height: {1:.6g} {2}".format(measurement.get("axis", MEASUREMENT_AXIS_DEFAULT), current_value, label)
    if factor is not None:
        result_value = current_value * float(factor)
        text += " -> result {0:.6g} {1} ({2:.6g}x)".format(result_value, label, float(factor))
    return text


# Private aliases keep the math easy to discover for existing smoke helpers.
_calculate_scale_factor = calculate_scale_factor
_measure_world_points = measure_world_points
_measure_mesh_reports = measure_mesh_reports


def _debug(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayInfo("[Maya Rig Scale] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayWarning("[Maya Rig Scale] {0}".format(message))


def _selected_nodes():
    return cmds.ls(selection=True, long=True) or []


def _visible_mesh_shape(transform_name):
    shapes = cmds.listRelatives(transform_name, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
    return shapes[0] if shapes else ""


def _mesh_shapes(transform_name):
    return cmds.listRelatives(transform_name, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []


def _dedupe_mesh_targets(targets):
    seen = set()
    result = []
    for target in targets or []:
        key = (target.get("transform"), target.get("shape"), target.get("skin_cluster"))
        if key in seen:
            continue
        seen.add(key)
        result.append(target)
    return result


def _all_mesh_shapes(transform_name):
    return cmds.listRelatives(transform_name, shapes=True, fullPath=True, type="mesh") or []


def _capture_skin_data_with_compatible_shape(source_transform, preferred_shape, skin_cluster):
    candidates = _dedupe_preserve_order([preferred_shape] + _all_mesh_shapes(source_transform))
    last_error = None
    for shape_name in candidates:
        if not shape_name or not cmds.objExists(shape_name):
            continue
        try:
            return _capture_skin_data(shape_name, skin_cluster), _node_long_name(shape_name)
        except Exception as exc:
            last_error = exc
    try:
        return _capture_skin_data_with_skin_percent(source_transform, preferred_shape, skin_cluster), _node_long_name(preferred_shape)
    except Exception:
        if last_error:
            raise last_error
    return _capture_skin_data(preferred_shape, skin_cluster), _node_long_name(preferred_shape)


def _capture_skin_data_with_skin_percent(source_transform, source_shape, skin_cluster):
    mesh_fn = _mesh_fn(source_shape)
    vertex_count = int(mesh_fn.numVertices)
    vertex_component = "{0}.vtx[0:{1}]".format(source_transform, max(vertex_count - 1, 0))
    influences = []
    for influence_path in cmds.skinCluster(skin_cluster, query=True, influence=True) or []:
        weights = cmds.skinPercent(skin_cluster, vertex_component, query=True, transform=influence_path)
        if weights is None:
            weights = []
        if not isinstance(weights, (list, tuple)):
            weights = [weights]
        weights = [float(value) for value in weights]
        if len(weights) == 1 and vertex_count > 1:
            weights = weights * vertex_count
        if len(weights) != vertex_count:
            raise RuntimeError("Skin weight count mismatch for {0}: expected {1}, got {2}".format(_short_name(influence_path), vertex_count, len(weights)))
        influences.append(
            {
                "path": _node_long_name(influence_path),
                "uuid": _uuid_for_node(influence_path),
                "physical_index": len(influences),
                "weights": weights,
            }
        )
    settings = {}
    for attribute in (
        "skinningMethod",
        "normalizeWeights",
        "maintainMaxInfluences",
        "maxInfluences",
        "weightDistribution",
        "bindMethod",
        "useComponents",
        "deformUserNormals",
    ):
        if cmds.attributeQuery(attribute, node=skin_cluster, exists=True):
            try:
                settings[attribute] = cmds.getAttr("{0}.{1}".format(skin_cluster, attribute))
            except Exception:
                pass
    return {
        "influences": influences,
        "settings": settings,
        "blend_weights": [0.0] * vertex_count,
        "vertex_count": vertex_count,
    }


def _selected_character_candidate():
    selected = _selected_nodes()
    if not selected:
        return "", "Pick the character root or any object under the character first."
    node_name = selected[0]
    if cmds.nodeType(node_name) == "mesh":
        parent = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
        if parent:
            return parent[0], ""
    return _node_long_name(node_name), ""


def _selected_skeleton_candidate():
    selected = _selected_nodes()
    if not selected:
        return "", "Pick the top skeleton joint first."
    node_name = _node_long_name(selected[0])
    if cmds.nodeType(node_name) == "joint":
        return node_name, ""
    descendants = cmds.listRelatives(node_name, allDescendents=True, fullPath=True, type="joint") or []
    top_level = []
    for joint_name in descendants:
        parent = cmds.listRelatives(joint_name, parent=True, fullPath=True) or []
        if not parent or parent[0] == node_name or cmds.nodeType(parent[0]) != "joint":
            top_level.append(joint_name)
    top_level = sorted(_dedupe_preserve_order(top_level), key=lambda item: item.count("|"))
    if len(top_level) == 1:
        return top_level[0], ""
    if top_level:
        return "", "More than one top skeleton joint was found. Pick the exact skeleton root joint."
    return "", "The selected object does not contain a joint hierarchy."


def _is_descendant_or_same(node_name, root_name):
    long_node = _node_long_name(node_name)
    long_root = _node_long_name(root_name)
    return long_node == long_root or long_node.startswith(long_root + "|")


def _joint_hierarchy(root_joint):
    if not root_joint or not cmds.objExists(root_joint):
        return []
    descendants = cmds.listRelatives(root_joint, allDescendents=True, fullPath=True, type="joint") or []
    descendants = sorted(_dedupe_preserve_order(descendants), key=lambda item: item.count("|"))
    return [_node_long_name(root_joint)] + descendants


def _mesh_targets_under_character(character_root):
    roots = [_node_long_name(character_root)]
    descendants = cmds.listRelatives(character_root, allDescendents=True, fullPath=True, type="transform") or []
    targets = []
    for transform_name in _dedupe_preserve_order(roots + descendants):
        for shape_name in _mesh_shapes(transform_name):
            skin_cluster = _find_skin_cluster(shape_name)
            if not skin_cluster:
                continue
            targets.append(
                {
                    "transform": _node_long_name(transform_name),
                    "shape": _node_long_name(shape_name),
                    "skin_cluster": skin_cluster,
                }
            )
    return _dedupe_mesh_targets(targets)


def _mesh_targets_from_skeleton(skeleton_root, character_root=""):
    joint_names = _joint_hierarchy(skeleton_root)
    skin_clusters = []
    for joint_name in joint_names:
        skin_clusters.extend(cmds.listConnections(joint_name, source=False, destination=True, type="skinCluster") or [])
    targets = []
    for skin_cluster in _dedupe_preserve_order(skin_clusters):
        shapes = cmds.skinCluster(skin_cluster, query=True, geometry=True) or []
        for shape_name in shapes:
            if not cmds.objExists(shape_name):
                continue
            node_type = cmds.nodeType(shape_name)
            if node_type == "transform":
                transform_name = _node_long_name(shape_name)
                skinned_shapes = [item for item in _mesh_shapes(transform_name) if _find_skin_cluster(item) == skin_cluster]
                shape_name = skinned_shapes[0] if skinned_shapes else _visible_mesh_shape(transform_name)
            elif node_type == "mesh":
                parent = cmds.listRelatives(shape_name, parent=True, fullPath=True) or []
                if not parent:
                    continue
                transform_name = parent[0]
            else:
                continue
            if not shape_name:
                continue
            if character_root and not _is_descendant_or_same(transform_name, character_root):
                continue
            targets.append(
                {
                    "transform": _node_long_name(transform_name),
                    "shape": _node_long_name(shape_name),
                    "skin_cluster": skin_cluster,
                }
            )
    return _dedupe_mesh_targets(targets)


def _mesh_targets_from_skeletons(skeleton_roots, character_root=""):
    targets = []
    for skeleton_root in skeleton_roots or []:
        targets.extend(_mesh_targets_from_skeleton(skeleton_root, character_root=character_root))
    return _dedupe_mesh_targets(targets)


def _skin_clusters_for_targets(mesh_targets):
    return _dedupe_preserve_order([target.get("skin_cluster") for target in mesh_targets or [] if target.get("skin_cluster")])


def _top_joint_for_influence(joint_name):
    if not joint_name or not cmds.objExists(joint_name) or cmds.nodeType(joint_name) != "joint":
        return ""
    current = _node_long_name(joint_name)
    while current:
        parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
        if not parents or cmds.nodeType(parents[0]) != "joint":
            return current
        current = _node_long_name(parents[0])
    return _node_long_name(joint_name)


def _inferred_skeleton_roots_from_skin_clusters(skin_clusters, character_root=""):
    influences = []
    for skin_cluster in skin_clusters or []:
        try:
            influences.extend(cmds.skinCluster(skin_cluster, query=True, influence=True) or [])
        except Exception:
            continue

    roots = []
    for influence in _dedupe_preserve_order(influences):
        if not influence or not cmds.objExists(influence) or cmds.nodeType(influence) != "joint":
            continue
        top_joint = _top_joint_for_influence(influence)
        if not top_joint:
            continue
        if character_root and not _is_descendant_or_same(top_joint, character_root):
            continue
        roots.append(top_joint)
    roots = _dedupe_preserve_order(roots)
    result = []
    for root in sorted(roots, key=lambda item: item.count("|")):
        if any(_is_descendant_or_same(root, existing) for existing in result):
            continue
        result.append(root)
    return result


def _infer_skeleton_roots(character_root="", skeleton_hint="", mesh_targets=None):
    skeleton_hint = _node_long_name(skeleton_hint) if skeleton_hint and cmds.objExists(skeleton_hint) else ""
    if skeleton_hint and cmds.nodeType(skeleton_hint) == "joint":
        if character_root and not _is_descendant_or_same(skeleton_hint, character_root):
            hinted_targets = _mesh_targets_from_skeleton(skeleton_hint, character_root)
            if not hinted_targets:
                return []
        if character_root and not _mesh_targets_from_skeleton(skeleton_hint, character_root):
            pass
        else:
            return [skeleton_hint]

    if mesh_targets is None:
        mesh_targets = []
        if character_root:
            mesh_targets = _mesh_targets_under_character(character_root)
        if not mesh_targets and skeleton_hint:
            mesh_targets = _mesh_targets_under_character(skeleton_hint)
    skin_clusters = _skin_clusters_for_targets(mesh_targets)
    roots = _inferred_skeleton_roots_from_skin_clusters(skin_clusters, character_root=character_root or skeleton_hint)
    if not roots and character_root and skin_clusters:
        roots = _inferred_skeleton_roots_from_skin_clusters(skin_clusters, character_root="")
    if roots:
        return roots

    search_root = character_root or skeleton_hint
    if search_root:
        descendants = cmds.listRelatives(search_root, allDescendents=True, fullPath=True, type="joint") or []
        top_level = []
        for joint_name in descendants:
            parent = cmds.listRelatives(joint_name, parent=True, fullPath=True) or []
            if not parent or parent[0] == search_root or cmds.nodeType(parent[0]) != "joint":
                top_level.append(_node_long_name(joint_name))
        return _dedupe_preserve_order(sorted(top_level, key=lambda item: item.count("|")))
    return []


def _safe_get_vector_attr(node_name, attribute):
    plug = "{0}.{1}".format(node_name, attribute)
    if not cmds.objExists(plug):
        return (0.0, 0.0, 0.0)
    return tuple(float(value) for value in cmds.getAttr(plug)[0])


def _has_locked_normals(shape_name):
    try:
        values = cmds.polyNormalPerVertex(shape_name + ".vtxFace[*][*]", query=True, freezeNormal=True) or []
    except Exception:
        values = []
    return any(bool(value) for value in values)


def _is_transform_visible(transform_name):
    current = transform_name
    while current and cmds.objExists(current):
        plug = current + ".visibility"
        if cmds.objExists(plug):
            try:
                if not cmds.getAttr(plug):
                    return False
            except Exception:
                pass
        parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
        current = parents[0] if parents else ""
    return True


def _ancestor_transform_warnings(root_joint):
    warnings = []
    current = root_joint
    while True:
        parent = cmds.listRelatives(current, parent=True, fullPath=True) or []
        if not parent:
            break
        current = parent[0]
        scale = _safe_get_vector_attr(current, "scale")
        if any(abs(value - 1.0) > 0.001 for value in scale):
            warnings.append(
                "The parent group {0} is already scaled. The export copy will bake the current visible size, not a hidden original size.".format(
                    _short_name(current)
                )
            )
            if abs(scale[0] - scale[1]) > 0.001 or abs(scale[1] - scale[2]) > 0.001 or abs(scale[0] - scale[2]) > 0.001:
                warnings.append(
                    "The parent group {0} uses non-uniform scale. Exact shading normals may need manual cleanup after export.".format(
                        _short_name(current)
                    )
                )
            break
        rotation = _safe_get_vector_attr(current, "rotate")
        if any(abs(value) > 0.001 for value in rotation):
            warnings.append(
                "The parent group {0} is rotated. Exact viewport normals can differ after baking scale, so verify the export copy before sending it to Unreal.".format(
                    _short_name(current)
                )
            )
            break
    return warnings


def _linear_unit_warning():
    try:
        unit_name = cmds.currentUnit(query=True, linear=True)
    except Exception:
        return []
    if unit_name != "cm":
        return [
            "The scene unit is {0}. Height math converts it deterministically; Unreal FBX export is explicitly converted to centimetres.".format(
                unit_name
            )
        ]
    return []


def _scene_linear_unit():
    try:
        return str(cmds.currentUnit(query=True, linear=True) or UNIT_CM).strip().lower()
    except Exception:
        return UNIT_CM


def _node_has_animation(node_name):
    """Return true for keyed or animation-curve-driven non-skin nodes."""
    try:
        if cmds.keyframe(node_name, query=True, name=True):
            return True
    except Exception:
        pass
    try:
        if cmds.listConnections(node_name, source=True, destination=False, type="animCurve"):
            return True
    except Exception:
        pass
    return False


def _animated_unsupported_history_nodes(unsupported_history):
    animated = []
    for node_name, node_type in unsupported_history or []:
        if _node_has_animation(node_name):
            animated.append((node_name, node_type))
    return animated


def _safe_matrix_snapshot(node_name):
    try:
        node_type = cmds.nodeType(node_name)
    except Exception:
        node_type = ""
    if node_type not in ("transform", "joint"):
        return None
    try:
        return tuple(float(value) for value in (cmds.xform(node_name, query=True, worldSpace=True, matrix=True) or []))
    except Exception:
        return None


def _normalize_plug_identity(plug_name):
    plug_text = str(plug_name)
    node_text, separator, attribute_text = plug_text.partition(".")
    node_uuid = ""
    try:
        matches = cmds.ls(node_text, long=True) or []
        if len(matches) == 1:
            node_uuid = _uuid_for_node(matches[0]) or ""
    except Exception:
        node_uuid = ""
    normalized_node = "uuid:{0}".format(node_uuid) if node_uuid else node_text
    return normalized_node + (separator + attribute_text if separator else "")


def _snapshot_value(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0.0 else "-Infinity"
        return float(value)
    if isinstance(value, (list, tuple)):
        return tuple(_snapshot_value(item) for item in value)
    return str(value)


def _safe_key_snapshot(node_name):
    result = {}
    try:
        curves = cmds.keyframe(node_name, query=True, name=True) or []
    except Exception:
        curves = []
    for curve_name in sorted(_dedupe_preserve_order(curves)):
        try:
            destinations = cmds.listConnections(
                curve_name + ".output",
                source=False,
                destination=True,
                plugs=True,
            ) or []
        except Exception:
            destinations = []
        try:
            times = cmds.keyframe(curve_name, query=True, timeChange=True) or []
        except Exception:
            times = []
        try:
            values = cmds.keyframe(curve_name, query=True, valueChange=True) or []
        except Exception:
            values = []
        try:
            in_tangents = cmds.keyTangent(curve_name, query=True, inTangentType=True) or []
        except Exception:
            in_tangents = []
        try:
            out_tangents = cmds.keyTangent(curve_name, query=True, outTangentType=True) or []
        except Exception:
            out_tangents = []
        result[str(curve_name)] = {
            "destinations": tuple(sorted(_normalize_plug_identity(value) for value in destinations)),
            "times": tuple(float(value) for value in times),
            "values": tuple(float(value) for value in values),
            "in_tangents": tuple(str(value) for value in in_tangents),
            "out_tangents": tuple(str(value) for value in out_tangents),
        }
    return result


def _safe_connection_snapshot(node_name):
    try:
        values = cmds.listConnections(node_name, connections=True, plugs=True, source=True, destination=True) or []
    except Exception:
        values = []
    return tuple(sorted(_normalize_plug_identity(value) for value in values))


def _safe_custom_attribute_snapshot(node_name):
    result = {}
    readable_types = {
        "bool",
        "byte",
        "char",
        "double",
        "double2",
        "double3",
        "enum",
        "float",
        "float2",
        "float3",
        "long",
        "long2",
        "long3",
        "matrix",
        "short",
        "short2",
        "short3",
        "string",
        "time",
    }
    try:
        attributes = cmds.listAttr(node_name, userDefined=True) or []
    except Exception:
        attributes = []
    for attribute in sorted(_dedupe_preserve_order(attributes)):
        plug = "{0}.{1}".format(node_name, attribute)
        try:
            attribute_type = cmds.getAttr(plug, type=True)
        except Exception:
            attribute_type = ""
        try:
            is_multi = bool(cmds.attributeQuery(attribute, node=node_name, multi=True))
        except Exception:
            is_multi = False
        values = "<type-only>"
        if attribute_type in readable_types:
            try:
                if is_multi:
                    indices = cmds.getAttr(plug, multiIndices=True) or []
                    values = tuple(
                        (
                            int(index),
                            _snapshot_value(cmds.getAttr("{0}[{1}]".format(plug, index))),
                        )
                        for index in indices
                    )
                else:
                    values = _snapshot_value(cmds.getAttr(plug))
            except Exception as exc:
                values = "<unreadable:{0}>".format(type(exc).__name__)
        try:
            locked = bool(cmds.getAttr(plug, lock=True))
        except Exception:
            locked = False
        try:
            keyable = bool(cmds.getAttr(plug, keyable=True))
        except Exception:
            keyable = False
        try:
            channel_box = bool(cmds.getAttr(plug, channelBox=True))
        except Exception:
            channel_box = False
        result[str(attribute)] = {
            "type": str(attribute_type),
            "multi": is_multi,
            "value": values,
            "locked": locked,
            "keyable": keyable,
            "channel_box": channel_box,
        }
    return result


def _safe_channel_snapshot(node_name):
    try:
        node_type = str(cmds.nodeType(node_name))
    except Exception:
        node_type = ""
    if node_type not in ("transform", "joint"):
        return {}
    attributes = [
        "translate",
        "rotate",
        "scale",
        "shear",
        "rotateOrder",
        "rotateAxis",
        "visibility",
        "inheritsTransform",
    ]
    if node_type == "joint":
        attributes.extend(("jointOrient", "segmentScaleCompensate", "inverseScale"))
    result = {}
    for attribute in attributes:
        plug = "{0}.{1}".format(node_name, attribute)
        if not cmds.objExists(plug):
            continue
        try:
            value = _snapshot_value(cmds.getAttr(plug))
        except Exception:
            value = "<unreadable>"
        try:
            driven_plugs = [plug]
            children = cmds.attributeQuery(attribute, node=node_name, listChildren=True) or []
            driven_plugs.extend("{0}.{1}".format(node_name, child) for child in children)
            driven = any(
                cmds.listConnections(candidate, source=True, destination=False)
                for candidate in driven_plugs
            )
        except Exception:
            driven = False
        result[attribute] = {"value": value, "driven": driven}
    try:
        parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
    except Exception:
        parents = []
    result["parent"] = str(parents[0]) if parents else ""
    return result


def _hash_text(hasher, value):
    encoded = str(value).encode("utf-8", errors="backslashreplace")
    hasher.update(struct.pack("<Q", len(encoded)))
    hasher.update(encoded)


def _hash_number(hasher, value):
    hasher.update(struct.pack("<d", float(value)))


def _mesh_geometry_snapshot(shape_name):
    mesh_fn = _mesh_fn(shape_name)
    counts, indices = mesh_fn.getVertices()
    object_points = mesh_fn.getPoints(om.MSpace.kObject)
    world_points = mesh_fn.getPoints(om.MSpace.kWorld)
    topology_hasher = hashlib.sha256()
    for value in counts:
        topology_hasher.update(struct.pack("<q", int(value)))
    for value in indices:
        topology_hasher.update(struct.pack("<q", int(value)))
    object_hasher = hashlib.sha256()
    world_hasher = hashlib.sha256()
    for point in object_points:
        for value in (point.x, point.y, point.z, point.w):
            _hash_number(object_hasher, value)
    for point in world_points:
        for value in (point.x, point.y, point.z, point.w):
            _hash_number(world_hasher, value)
    return {
        "shape": str(shape_name),
        "vertex_count": int(mesh_fn.numVertices),
        "face_count": int(mesh_fn.numPolygons),
        "topology_sha256": topology_hasher.hexdigest(),
        "object_points_sha256": object_hasher.hexdigest(),
        "world_points_sha256": world_hasher.hexdigest(),
    }


def _skin_weight_snapshot(mesh_report, use_cached_data=False):
    source_transform = mesh_report.get("source_transform", "")
    source_shape = mesh_report.get("skin_shape") or mesh_report.get("source_shape", "")
    skin_cluster = mesh_report.get("skin_cluster", "")
    cached_skin_data = mesh_report.get("skin_data") if use_cached_data else None
    if cached_skin_data:
        skin_data = cached_skin_data
        resolved_shape = mesh_report.get("skin_shape") or source_shape
    else:
        skin_data, resolved_shape = _capture_skin_data_with_compatible_shape(
            source_transform,
            source_shape,
            skin_cluster,
        )
    weight_hasher = hashlib.sha256()
    _hash_text(weight_hasher, skin_cluster)
    _hash_text(weight_hasher, resolved_shape)
    for entry in skin_data.get("influences") or []:
        _hash_text(weight_hasher, entry.get("uuid") or entry.get("path") or "")
        for value in entry.get("weights") or []:
            _hash_number(weight_hasher, value)
    for value in skin_data.get("blend_weights") or []:
        _hash_number(weight_hasher, value)
    settings = tuple(
        sorted(
            (str(key), _snapshot_value(value))
            for key, value in (skin_data.get("settings") or {}).items()
        )
    )
    _hash_text(weight_hasher, settings)
    return {
        "skin_cluster": str(skin_cluster),
        "skin_shape": str(resolved_shape),
        "vertex_count": int(skin_data.get("vertex_count") or 0),
        "influence_count": len(skin_data.get("influences") or []),
        "settings": settings,
        "weights_sha256": weight_hasher.hexdigest(),
    }


def _source_scope_nodes(character_root, skeleton_roots, mesh_reports):
    nodes = _animation_nodes(character_root, skeleton_roots)
    for mesh_report in mesh_reports or []:
        nodes.extend(
            [
                mesh_report.get("source_transform", ""),
                mesh_report.get("source_shape", ""),
                mesh_report.get("skin_shape", ""),
                mesh_report.get("skin_cluster", ""),
            ]
        )
        try:
            history = cmds.listHistory(mesh_report.get("source_shape"), pruneDagObjects=True) or []
        except Exception:
            history = []
        nodes.extend(history)
        skin_shape = mesh_report.get("skin_shape")
        if skin_shape and skin_shape != mesh_report.get("source_shape"):
            try:
                nodes.extend(cmds.listHistory(skin_shape, pruneDagObjects=True) or [])
            except Exception:
                pass
    for node_name in list(nodes):
        if not node_name:
            continue
        try:
            nodes.extend(cmds.listConnections(node_name, type="animCurve") or [])
        except Exception:
            pass
    canonical = []
    for node_name in _dedupe_preserve_order(nodes):
        if not node_name or not cmds.objExists(node_name):
            continue
        try:
            canonical.append(_node_long_name(node_name))
        except Exception:
            canonical.append(str(node_name))
    return _dedupe_preserve_order(canonical)


def _capture_scene_state():
    state = {}
    try:
        state["current_time"] = float(cmds.currentTime(query=True))
    except Exception:
        state["current_time"] = None
    for label, unit_flag in (("linear_unit", "linear"), ("angle_unit", "angle"), ("time_unit", "time")):
        try:
            state[label] = str(cmds.currentUnit(query=True, **{unit_flag: True}))
        except Exception:
            state[label] = None
    for label, option in (
        ("playback_min", "minTime"),
        ("playback_max", "maxTime"),
        ("animation_start", "animationStartTime"),
        ("animation_end", "animationEndTime"),
    ):
        try:
            state[label] = float(cmds.playbackOptions(query=True, **{option: True}))
        except Exception:
            state[label] = None
    try:
        state["auto_key"] = bool(cmds.autoKeyframe(query=True, state=True))
    except Exception:
        state["auto_key"] = None
    return state


def _capture_source_snapshot(character_root, skeleton_roots, mesh_reports, baseline=None, use_cached_skin_data=False):
    """Capture deep source state that must be identical after copy/export."""
    if baseline and baseline.get("nodes"):
        nodes = list(baseline["nodes"])
    else:
        nodes = _source_scope_nodes(character_root, skeleton_roots, mesh_reports)
    snapshot = {"scene": _capture_scene_state(), "nodes": {}, "meshes": {}}
    try:
        snapshot["current_time"] = snapshot["scene"].get("current_time")
    except Exception:
        snapshot["current_time"] = None
    for node_name in _dedupe_preserve_order(nodes):
        if not node_name:
            continue
        try:
            if not cmds.objExists(node_name):
                snapshot["nodes"][str(node_name)] = {"missing": True}
                continue
            snapshot["nodes"][str(node_name)] = {
                "uuid": str(_uuid_for_node(node_name) or ""),
                "type": str(cmds.nodeType(node_name)),
                "matrix": _safe_matrix_snapshot(node_name),
                "channels": _safe_channel_snapshot(node_name),
                "custom_attributes": _safe_custom_attribute_snapshot(node_name),
                "keys": _safe_key_snapshot(node_name),
                "connections": _safe_connection_snapshot(node_name),
            }
        except Exception:
            snapshot["nodes"][str(node_name)] = {"unreadable": True}
    for mesh_report in mesh_reports or []:
        source_transform = mesh_report.get("source_transform", "")
        source_shape = mesh_report.get("source_shape", "")
        if not source_transform or not source_shape:
            continue
        mesh_snapshot = {"source_shape": str(source_shape)}
        try:
            mesh_snapshot["geometry"] = _mesh_geometry_snapshot(source_shape)
        except Exception as exc:
            mesh_snapshot["geometry_error"] = str(exc)
        try:
            mesh_snapshot["skin"] = _skin_weight_snapshot(mesh_report, use_cached_data=use_cached_skin_data)
        except Exception as exc:
            mesh_snapshot["skin_error"] = str(exc)
        snapshot["meshes"][str(source_transform)] = mesh_snapshot
    return snapshot


def _compact_source_snapshot(snapshot):
    """Retain only proof data needed after source comparison completes.

    The live snapshots contain per-node channel/key dictionaries and mesh
    hashes, but the full values are not needed for later copy-independence
    checks.  Keeping UUIDs plus scalar/hash summaries prevents a verified
    29-mesh result from retaining the complete before/after snapshots.
    """
    snapshot = snapshot or {}
    compact_nodes = {}
    for node_name, state in (snapshot.get("nodes") or {}).items():
        state = state or {}
        if state.get("uuid"):
            compact_nodes[str(node_name)] = {"uuid": str(state.get("uuid"))}
        elif state.get("missing"):
            compact_nodes[str(node_name)] = {"missing": True}
    geometry_fields = (
        "shape",
        "vertex_count",
        "face_count",
        "topology_sha256",
        "object_points_sha256",
        "world_points_sha256",
    )
    skin_fields = (
        "skin_cluster",
        "skin_shape",
        "vertex_count",
        "influence_count",
        "weights_sha256",
    )
    compact_meshes = {}
    for mesh_name, mesh_state in (snapshot.get("meshes") or {}).items():
        mesh_state = mesh_state or {}
        compact_mesh = {"source_shape": str(mesh_state.get("source_shape") or "")}
        for label, fields in (("geometry", geometry_fields), ("skin", skin_fields)):
            value = mesh_state.get(label)
            if isinstance(value, dict):
                compact_mesh[label] = {field: value.get(field) for field in fields if field in value}
            elif value is not None:
                compact_mesh[label + "_error"] = str(value)
        for error_label in ("geometry_error", "skin_error"):
            if mesh_state.get(error_label):
                compact_mesh[error_label] = str(mesh_state.get(error_label))
        compact_meshes[str(mesh_name)] = compact_mesh
    return {
        "scene": dict(snapshot.get("scene") or {}),
        "current_time": snapshot.get("current_time"),
        "nodes": compact_nodes,
        "meshes": compact_meshes,
    }


def _snapshot_values_match(first, second, epsilon=SOURCE_STATE_EPSILON):
    if isinstance(first, bool) or isinstance(second, bool):
        return first is second
    if isinstance(first, (int, float)) and isinstance(second, (int, float)):
        return abs(float(first) - float(second)) <= float(epsilon)
    if isinstance(first, dict) and isinstance(second, dict):
        if set(first) != set(second):
            return False
        return all(_snapshot_values_match(first[key], second[key], epsilon=epsilon) for key in first)
    if isinstance(first, (list, tuple)) and isinstance(second, (list, tuple)):
        return len(first) == len(second) and all(
            _snapshot_values_match(first_value, second_value, epsilon=epsilon)
            for first_value, second_value in zip(first, second)
        )
    return first == second


def _channel_snapshots_match(first, second, matrix_matches):
    first = first or {}
    second = second or {}
    if set(first) != set(second):
        return False
    matrix_covered_driven = {
        "translate",
        "rotate",
        "scale",
        "shear",
        "rotateAxis",
        "inverseScale",
    }
    for attribute in first:
        if attribute == "parent":
            if first[attribute] != second[attribute]:
                return False
            continue
        first_entry = first.get(attribute) or {}
        second_entry = second.get(attribute) or {}
        if bool(first_entry.get("driven")) != bool(second_entry.get("driven")):
            return False
        if (
            matrix_matches
            and attribute in matrix_covered_driven
            and first_entry.get("driven")
            and second_entry.get("driven")
        ):
            continue
        if not _snapshot_values_match(first_entry.get("value"), second_entry.get("value")):
            return False
    return True


def _compare_source_snapshots(before, after):
    before = before or {}
    after = after or {}
    differences = []
    if not _snapshot_values_match(before.get("scene"), after.get("scene")):
        differences.append("scene")
    if before.get("meshes") != after.get("meshes"):
        differences.append("mesh_points_or_skin_weights")
    before_nodes = before.get("nodes") or {}
    after_nodes = after.get("nodes") or {}
    if set(before_nodes) != set(after_nodes):
        differences.append("node_scope")
    for node_name in sorted(set(before_nodes) & set(after_nodes)):
        first = before_nodes[node_name]
        second = after_nodes[node_name]
        for field in ("uuid", "type", "parent", "keys", "connections"):
            if first.get(field) != second.get(field):
                differences.append("{0}:{1}".format(node_name, field))
        matrix_matches = _snapshot_values_match(first.get("matrix"), second.get("matrix"))
        if not matrix_matches:
            differences.append("{0}:matrix".format(node_name))
        if not _channel_snapshots_match(first.get("channels"), second.get("channels"), matrix_matches):
            differences.append("{0}:channels".format(node_name))
        if not _snapshot_values_match(first.get("custom_attributes"), second.get("custom_attributes")):
            differences.append("{0}:custom_attributes".format(node_name))
    return {
        "passed": not differences,
        "numeric_epsilon": SOURCE_STATE_EPSILON,
        "differences": differences,
    }


def _fbx_mel_commands(path, animation):
    """Return deterministic FBX settings for an Unreal skeletal export."""
    escaped_path = str(path).replace("\\", "/").replace('"', '\\"')
    commands = [
        'FBXExportInAscii -v false',
        'FBXExportSmoothingGroups -v true',
        'FBXExportHardEdges -v false',
        'FBXExportTangents -v true',
        'FBXExportSmoothMesh -v true',
        'FBXExportSkins -v true',
        'FBXExportShapes -v false',
        'FBXExportConstraints -v false',
        'FBXExportCameras -v false',
        'FBXExportLights -v false',
        'FBXExportInputConnections -v true',
        "FBXExportUpAxis y",
        'FBXExportConvertUnitString -v "cm"',
        'FBXExportFileVersion -v FBX202000',
        'FBXExportApplyConstantKeyReducer -v false',
    ]
    if (animation or {}).get("baked"):
        # The copied skeleton was keyed at the source's exact (possibly
        # fractional) times.  Re-baking in FBX would replace those sparse keys
        # with a dense whole-frame sequence.
        commands.append('FBXExportBakeComplexAnimation -v false')
    else:
        commands.append('FBXExportBakeComplexAnimation -v false')
    commands.append('FBXExport -f "{0}" -s'.format(escaped_path))
    return commands


def _valid_fbx_path(path):
    if isinstance(path, os.PathLike):
        path = os.fspath(path)
    if not isinstance(path, str) or not path.strip():
        return "", "Choose an explicit .fbx output path."
    normalized = os.path.abspath(path.strip())
    if os.path.splitext(normalized)[1].lower() != ".fbx":
        return "", "The Unreal export path must end with .fbx."
    parent = os.path.dirname(normalized)
    if not parent or not os.path.isdir(parent):
        return "", "The Unreal export folder does not exist: {0}".format(parent or "(empty)")
    return normalized, ""


_FBX_RESTORABLE_SETTINGS = (
    "FBXExportInAscii",
    "FBXExportSmoothingGroups",
    "FBXExportHardEdges",
    "FBXExportTangents",
    "FBXExportSmoothMesh",
    "FBXExportSkins",
    "FBXExportShapes",
    "FBXExportConstraints",
    "FBXExportCameras",
    "FBXExportLights",
    "FBXExportInputConnections",
    "FBXExportUpAxis",
    "FBXExportConvertUnitString",
    "FBXExportFileVersion",
    "FBXExportBakeComplexAnimation",
    "FBXExportBakeComplexStart",
    "FBXExportBakeComplexEnd",
    "FBXExportBakeComplexStep",
    "FBXExportApplyConstantKeyReducer",
)


def _capture_fbx_settings():
    captured = {}
    if not mel:
        return None
    failed = []
    for command_name in _FBX_RESTORABLE_SETTINGS:
        try:
            captured[command_name] = mel.eval("{0} -q".format(command_name))
        except Exception:
            failed.append(command_name)
    # An empty or partial capture cannot prove that restoration happened.  A
    # strict complete snapshot deliberately fails closed instead of allowing
    # ``all([])`` to report a vacuous settings match.
    if failed or set(captured) != set(_FBX_RESTORABLE_SETTINGS):
        return None
    return captured


def _restore_fbx_settings(captured):
    if not mel:
        return
    for command_name, value in (captured or {}).items():
        if command_name == "FBXExportUpAxis":
            try:
                mel.eval("{0} {1}".format(command_name, str(value).strip().lower()))
            except Exception:
                pass
            continue
        if isinstance(value, bool):
            literal = "true" if value else "false"
        elif isinstance(value, (int, float)):
            literal = str(value)
        else:
            literal = '"{0}"'.format(str(value).replace('"', '\\"'))
        try:
            mel.eval("{0} -v {1}".format(command_name, literal))
        except Exception:
            pass


def _fbx_settings_match(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    if not before or not after:
        return False
    expected_keys = set(_FBX_RESTORABLE_SETTINGS)
    if set(before) != expected_keys or set(after) != expected_keys:
        return False
    return all(after.get(key) == before.get(key) for key in expected_keys)


def _inspect_fbx_file(path):
    inspection = {
        "path": str(path),
        "file_exists": False,
        "file_size": 0,
        "header": "",
        "header_valid": False,
        "markers": {},
        "content_valid": False,
        "error": "",
    }
    if not os.path.isfile(path):
        inspection["error"] = "file_missing"
        return inspection
    try:
        inspection["file_exists"] = True
        inspection["file_size"] = int(os.path.getsize(path))
        markers = (b"Objects", b"Model", b"Geometry", b"Deformer")
        found = {marker: False for marker in markers}
        with open(path, "rb") as stream:
            header = stream.read(64)
            if header.startswith(b"Kaydara FBX Binary  \x00\x1a\x00"):
                inspection["header"] = "binary"
                inspection["header_valid"] = True
            elif header.lstrip().startswith(b"; FBX"):
                inspection["header"] = "ascii"
                inspection["header_valid"] = True
            carry = header
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                block = carry + chunk
                for marker in markers:
                    if not found[marker] and marker in block:
                        found[marker] = True
                carry = block[-32:]
        inspection["markers"] = {
            marker.decode("ascii"): bool(found[marker])
            for marker in markers
        }
        inspection["content_valid"] = bool(
            inspection["header_valid"]
            and inspection["file_size"] > 256
            and found[b"Objects"]
            and found[b"Model"]
            and found[b"Geometry"]
        )
    except Exception as exc:
        inspection["error"] = str(exc)
    return inspection


def _verify_fbx_import_content(path, expected_joint_count, expected_mesh_count, expected_animation=False):
    result = {
        "isolated_process": True,
        "imported": False,
        "joint_count": 0,
        "mesh_count": 0,
        "skin_cluster_count": 0,
        "skinned_mesh_count": 0,
        "influence_count": 0,
        "weighted_vertex_count": 0,
        "weight_sum_error_max": None,
        "animation_curve_count": 0,
        "animation_key_count": 0,
        "expected_joint_count": int(expected_joint_count or 0),
        "expected_mesh_count": int(expected_mesh_count or 0),
        "expected_animation": bool(expected_animation),
        "skin_verified": False,
        "animation_verified": False,
        "content_verified": False,
        "cleanup_verified": False,
        "error": "",
        "return_code": None,
        "output_tail": "",
    }
    maya_executable = str(sys.executable or "")
    mayapy_name = "mayapy.exe" if os.name == "nt" else "mayapy"
    mayapy_path = os.path.join(os.path.dirname(maya_executable), mayapy_name)
    if not os.path.isfile(mayapy_path):
        result["error"] = "Could not find the matching mayapy executable: {0}".format(mayapy_path)
        result["verified"] = False
        return result

    temp_root = tempfile.mkdtemp(prefix="aminate-rig-scale-fbx-verify-")
    script_path = os.path.join(temp_root, "verify_fbx_import.py")
    marker = "AMINATE_FBX_IMPORT_RESULT:"
    script_source = r'''
from __future__ import print_function
import json
import sys
import traceback

payload = {
    "imported": False,
    "joint_count": 0,
    "mesh_count": 0,
    "skin_cluster_count": 0,
    "skinned_mesh_count": 0,
    "influence_count": 0,
    "weighted_vertex_count": 0,
    "weight_sum_error_max": None,
    "animation_curve_count": 0,
    "animation_key_count": 0,
    "error": "",
}
try:
    import maya.standalone
    try:
        maya.standalone.initialize(name="python")
    except Exception:
        pass
    import maya.cmds as cmds
    if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
        cmds.loadPlugin("fbxmaya", quiet=True)
    cmds.file(new=True, force=True)
    cmds.file(
        sys.argv[1],
        i=True,
        type="FBX",
        ignoreVersion=True,
        returnNewNodes=True,
    )
    payload["imported"] = True
    payload["joint_count"] = len(cmds.ls(type="joint", long=True) or [])
    mesh_shapes = cmds.ls(type="mesh", noIntermediate=True, long=True) or []
    payload["mesh_count"] = len(mesh_shapes)
    skin_clusters = cmds.ls(type="skinCluster", long=True) or []
    payload["skin_cluster_count"] = len(skin_clusters)
    weighted_vertex_count = 0
    influence_count = 0
    weight_sum_error_max = 0.0
    for skin_cluster in skin_clusters:
        influences = cmds.skinCluster(skin_cluster, query=True, influence=True) or []
        influence_count += len(influences)
        geometries = cmds.skinCluster(skin_cluster, query=True, geometry=True) or []
        for geometry in geometries:
            if cmds.nodeType(geometry) == "transform":
                geometries_shapes = cmds.listRelatives(
                    geometry,
                    shapes=True,
                    noIntermediate=True,
                    fullPath=True,
                    type="mesh",
                ) or []
            elif cmds.nodeType(geometry) == "mesh":
                geometries_shapes = [geometry]
            else:
                geometries_shapes = []
            for shape in geometries_shapes:
                payload["skinned_mesh_count"] += 1
                vertex_count = int(cmds.polyEvaluate(shape, vertex=True) or 0)
                for vertex_index in range(vertex_count):
                    values = cmds.skinPercent(
                        skin_cluster,
                        "{0}.vtx[{1}]".format(shape, vertex_index),
                        query=True,
                        value=True,
                    ) or []
                    if not isinstance(values, (list, tuple)):
                        values = [values]
                    values = [float(value) for value in values]
                    if any(abs(value) > 1.0e-8 for value in values):
                        weighted_vertex_count += 1
                    if values:
                        weight_sum_error_max = max(
                            weight_sum_error_max,
                            abs(sum(values) - 1.0),
                        )
    payload["influence_count"] = influence_count
    payload["weighted_vertex_count"] = weighted_vertex_count
    payload["weight_sum_error_max"] = weight_sum_error_max
    animation_curves = cmds.ls(type="animCurve", long=True) or []
    payload["animation_curve_count"] = len(animation_curves)
    payload["animation_key_count"] = sum(
        int(cmds.keyframe(curve, query=True, keyframeCount=True) or 0)
        for curve in animation_curves
    )
except Exception as exc:
    payload["error"] = "{0}\n{1}".format(exc, traceback.format_exc())
print("AMINATE_FBX_IMPORT_RESULT:" + json.dumps(payload, sort_keys=True))
try:
    maya.standalone.uninitialize()
except Exception:
    pass
'''
    try:
        with open(script_path, "w", encoding="utf-8") as script_file:
            script_file.write(script_source)
        completed = subprocess.run(
            [mayapy_path, script_path, str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        result["return_code"] = int(completed.returncode)
        output = completed.stdout or ""
        result["output_tail"] = output[-4000:]
        payload = None
        for line in reversed(output.splitlines()):
            if line.startswith(marker):
                payload = json.loads(line[len(marker):])
                break
        if payload is None:
            result["error"] = "The isolated Maya import did not return a result marker."
        else:
            result["imported"] = bool(payload.get("imported"))
            result["joint_count"] = int(payload.get("joint_count") or 0)
            result["mesh_count"] = int(payload.get("mesh_count") or 0)
            result["skin_cluster_count"] = int(payload.get("skin_cluster_count") or 0)
            result["skinned_mesh_count"] = int(payload.get("skinned_mesh_count") or 0)
            result["influence_count"] = int(payload.get("influence_count") or 0)
            result["weighted_vertex_count"] = int(payload.get("weighted_vertex_count") or 0)
            result["weight_sum_error_max"] = payload.get("weight_sum_error_max")
            result["animation_curve_count"] = int(payload.get("animation_curve_count") or 0)
            result["animation_key_count"] = int(payload.get("animation_key_count") or 0)
            result["error"] = str(payload.get("error") or "")
        expected_joints = max(int(expected_joint_count or 0), 1)
        expected_meshes = max(int(expected_mesh_count or 0), 1)
        result["skin_verified"] = bool(
            result["skin_cluster_count"] >= expected_meshes
            and result["skinned_mesh_count"] >= expected_meshes
            and result["influence_count"] > 0
            and result["weighted_vertex_count"] > 0
            and result["weight_sum_error_max"] is not None
            and float(result["weight_sum_error_max"]) <= 1.0e-4
        )
        result["animation_verified"] = bool(
            not expected_animation
            or (
                result["animation_curve_count"] > 0
                and result["animation_key_count"] > 0
            )
        )
        result["content_verified"] = bool(
            result["joint_count"] == expected_joints
            and result["mesh_count"] == expected_meshes
            and result["skin_verified"]
            and result["animation_verified"]
        )
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        try:
            if os.path.isfile(script_path):
                os.remove(script_path)
        except Exception:
            pass
        try:
            os.rmdir(temp_root)
        except Exception:
            pass
        result["cleanup_verified"] = not os.path.exists(temp_root)
    result["verified"] = bool(
        result["imported"]
        and result["content_verified"]
        and result["cleanup_verified"]
        and result["return_code"] == 0
        and not result["error"]
    )
    return result


def _world_translation(node_name):
    values = cmds.xform(node_name, query=True, worldSpace=True, translation=True)
    return om.MVector(float(values[0]), float(values[1]), float(values[2]))


def _animation_nodes(controls_root, skeleton_roots):
    nodes = []
    if controls_root and cmds.objExists(controls_root):
        nodes.append(_node_long_name(controls_root))
        nodes.extend(cmds.listRelatives(controls_root, allDescendents=True, fullPath=True, type="transform") or [])
        nodes.extend(cmds.listRelatives(controls_root, allDescendents=True, fullPath=True, type="joint") or [])
    for skeleton_root in skeleton_roots or []:
        if skeleton_root and cmds.objExists(skeleton_root):
            nodes.extend(_joint_hierarchy(skeleton_root))
    return _dedupe_preserve_order(nodes)


def _animation_sample_times(controls_root, skeleton_roots):
    """Return the unique key times authored by the source animation.

    Rig Scale writes the scaled duplicate at these times only.  Keeping the
    source's sparse (and possibly fractional) timing preserves the original
    interpolation instead of inventing a key on every whole frame.
    """
    nodes = _animation_nodes(controls_root, skeleton_roots)
    if not nodes:
        return []
    try:
        keyed_times = cmds.keyframe(nodes, query=True, timeChange=True) or []
    except Exception:
        keyed_times = []
    if not keyed_times:
        return []
    return sorted(set(float(value) for value in keyed_times))


def _scale_sample_nodes(character_root, skeleton_roots):
    nodes = list(_animation_nodes(character_root, skeleton_roots))
    for skeleton_root in skeleton_roots or []:
        current = skeleton_root
        while current and cmds.objExists(current):
            try:
                parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
            except Exception:
                parents = []
            if not parents:
                break
            current = parents[0]
            nodes.append(current)
    result = []
    for node_name in _dedupe_preserve_order(nodes):
        if not node_name or not cmds.objExists(node_name):
            continue
        try:
            if cmds.nodeType(node_name) in ("transform", "joint"):
                result.append(_node_long_name(node_name))
        except Exception:
            continue
    return result


def _plug_has_time_dependency(plug_name, visited=None, depth=0):
    if not plug_name or not cmds.objExists(plug_name) or depth > 24:
        return False
    visited = set(visited or ())
    try:
        if cmds.keyframe(plug_name, query=True, name=True):
            return True
    except Exception:
        pass
    try:
        upstream_plugs = cmds.listConnections(
            plug_name,
            source=True,
            destination=False,
            plugs=True,
            skipConversionNodes=False,
        ) or []
    except Exception:
        upstream_plugs = []
    time_dependent_types = {
        "expression",
        "time",
        "animBlendNodeAdditive",
        "animBlendNodeAdditiveRotation",
        "animBlendNodeAdditiveScale",
        "animBlendNodeBoolean",
        "animBlendNodeEnum",
        "animBlendNodeTime",
    }
    for source_plug in upstream_plugs:
        node_name = str(source_plug).partition(".")[0]
        try:
            canonical = _node_long_name(node_name)
        except Exception:
            canonical = str(node_name)
        if canonical in visited:
            continue
        visited.add(canonical)
        try:
            node_type = str(cmds.nodeType(node_name))
        except Exception:
            node_type = ""
        if node_type.startswith("animCurve") or node_type in time_dependent_types:
            return True
        if node_type in ("transform", "joint"):
            try:
                if cmds.keyframe(node_name, query=True, name=True):
                    return True
            except Exception:
                pass
            continue
        if _plug_has_time_dependency(node_name, visited=visited, depth=depth + 1):
            return True
    return False


def _animated_scale_blockers(character_root, skeleton_roots, sample_times):
    nodes = _scale_sample_nodes(character_root, skeleton_roots)
    time_driven = []
    for node_name in nodes:
        if any(_plug_has_time_dependency(node_name + ".scale" + axis) for axis in ("X", "Y", "Z")):
            time_driven.append(node_name)

    # Static scale channels cannot vary between frames.  Do not change Maya's
    # current time merely to re-read those values: on a production rig that
    # can trigger the complete deformer/control dependency graph dozens of
    # times.  Only nodes whose scale plugs are proven time-dependent need the
    # frame-sampling pass below.
    time_driven = _dedupe_preserve_order(time_driven)
    if not time_driven:
        return {
            "time_driven": [],
            "varying": [],
            "sample_count": 0,
        }

    samples = [float(value) for value in (sample_times or [])]
    if len(samples) < 2:
        try:
            playback_min = float(cmds.playbackOptions(query=True, minTime=True))
            playback_max = float(cmds.playbackOptions(query=True, maxTime=True))
            samples = sorted(
                set(
                    samples
                    + [
                        float(cmds.currentTime(query=True)),
                        playback_min,
                        (playback_min + playback_max) * 0.5,
                        playback_max,
                    ]
                )
            )
        except Exception:
            pass
    if len(samples) > 33:
        indices = {0, len(samples) - 1}
        for index in range(1, 32):
            indices.add(int(round((len(samples) - 1) * (index / 32.0))))
        samples = [samples[index] for index in sorted(indices)]
    varying = []
    if samples:
        original_time = float(cmds.currentTime(query=True))
        first_values = {}
        try:
            for sample_time in samples:
                cmds.currentTime(sample_time, edit=True, update=True)
                for node_name in time_driven:
                    try:
                        current_scale = _safe_get_vector_attr(node_name, "scale")
                    except Exception:
                        continue
                    if node_name not in first_values:
                        first_values[node_name] = current_scale
                    elif any(
                        abs(float(current) - float(first)) > VALUE_EPSILON
                        for current, first in zip(current_scale, first_values[node_name])
                    ):
                        varying.append(node_name)
        finally:
            cmds.currentTime(original_time, edit=True, update=True)
    return {
        "time_driven": time_driven,
        "varying": _dedupe_preserve_order(varying),
        "sample_count": len(samples),
    }


def _set_world_matrix_without_scale(target_node, source_node):
    cmds.xform(
        target_node,
        worldSpace=True,
        matrix=_matrix_to_list(_world_matrix_without_scale(source_node)),
    )


def _scaled_world_matrix_about_anchor(source_node, anchor_point, scale_factor):
    source_matrix = _world_matrix_without_scale(source_node)
    source_transform = om.MTransformationMatrix(source_matrix)
    source_position = source_transform.translation(om.MSpace.kWorld)
    anchor = om.MVector(
        float(anchor_point.x),
        float(anchor_point.y),
        float(anchor_point.z),
    )
    scaled_position = anchor + ((source_position - anchor) * float(scale_factor))
    source_transform.setTranslation(scaled_position, om.MSpace.kWorld)
    return source_transform.asMatrix()


def _bake_scaled_skeleton_animation(joint_map, sample_times, scale_factor, anchor_node):
    if not sample_times:
        return {"baked": False, "sample_count": 0, "start": None, "end": None}
    if not anchor_node or not cmds.objExists(anchor_node):
        raise RuntimeError("Scaled animation baking requires the live character anchor.")
    original_time = float(cmds.currentTime(query=True))
    ordered_pairs = sorted(joint_map.items(), key=lambda item: item[0].count("|"))
    try:
        for sample_time in sample_times:
            cmds.currentTime(sample_time, edit=True, update=True)
            _force_geometry_evaluation()
            anchor_point = _world_translation(anchor_node)
            for source_joint, duplicate_joint in ordered_pairs:
                cmds.xform(
                    duplicate_joint,
                    worldSpace=True,
                    matrix=_matrix_to_list(
                        _scaled_world_matrix_about_anchor(
                            source_joint,
                            anchor_point,
                            scale_factor,
                        )
                    ),
                )
                cmds.setAttr(duplicate_joint + ".scaleX", 1.0)
                cmds.setAttr(duplicate_joint + ".scaleY", 1.0)
                cmds.setAttr(duplicate_joint + ".scaleZ", 1.0)
                cmds.setKeyframe(duplicate_joint, attribute=("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"), time=sample_time)
    finally:
        cmds.currentTime(original_time, edit=True, update=True)
    return {
        "baked": True,
        "sample_count": len(sample_times),
        "start": float(sample_times[0]),
        "end": float(sample_times[-1]),
    }


def _world_quaternion(node_name):
    matrix_values = cmds.xform(node_name, query=True, worldSpace=True, matrix=True)
    matrix = om.MMatrix(matrix_values)
    transform = om.MTransformationMatrix(matrix)
    return transform.rotation(asQuaternion=True)


def _matrix_to_list(matrix):
    return [matrix[index] for index in range(16)]


def _world_matrix_without_scale(node_name):
    source_matrix = om.MMatrix(cmds.xform(node_name, query=True, worldSpace=True, matrix=True))
    source_transform = om.MTransformationMatrix(source_matrix)
    clean_transform = om.MTransformationMatrix()
    clean_transform.setTranslation(source_transform.translation(om.MSpace.kWorld), om.MSpace.kWorld)
    clean_transform.setRotation(source_transform.rotation(asQuaternion=True))
    return clean_transform.asMatrix()


def _capture_true_world_points(shape_name):
    # MFnMesh returns the evaluated world-space array in one API call.  The
    # old per-vertex iterator made one Python/API round-trip per vertex on every
    # analyzed mesh and then repeated the same work during copy verification.
    return om.MFnMesh(_dag_path(shape_name)).getPoints(om.MSpace.kWorld)


def _capture_owned_world_points(shape_name):
    """Return point values that do not borrow an MPointArray's storage."""
    captured = _capture_true_world_points(shape_name)
    owned = om.MPointArray()
    for point in captured:
        owned.append(
            om.MPoint(
                float(point.x),
                float(point.y),
                float(point.z),
                float(point.w),
            )
        )
    return owned


# The Rig Scale action verifier executes generated Maya code that resolves this
# helper through the module object. Keep an explicit runtime reference so the
# accepted verifier API remains visible to static dead-code analysis.
_RIG_SCALE_VERIFIER_HELPERS = (_capture_owned_world_points,)


def _force_geometry_evaluation():
    """Force Maya to settle time-dependent geometry before proof reads.

    ``currentTime(update=True)`` normally evaluates the graph, but complex
    parallel rigs can leave a skinned output cached until the viewport or DG
    asks for another update. Rig Scale verification must never accept that
    stale output and then show a different result one read later.
    """
    try:
        cmds.dgdirty(allPlugs=True)
    except Exception:
        pass
    try:
        cmds.refresh(force=True)
    except Exception:
        pass


def _copy_joint_attribute(source_joint, duplicate_joint, attribute):
    source_plug = "{0}.{1}".format(source_joint, attribute)
    target_plug = "{0}.{1}".format(duplicate_joint, attribute)
    if not cmds.objExists(source_plug) or not cmds.objExists(target_plug):
        return
    try:
        value = cmds.getAttr(source_plug)
    except Exception:
        return
    try:
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], (list, tuple)):
            values = value[0]
            cmds.setAttr(target_plug, *values)
        elif isinstance(value, str):
            cmds.setAttr(target_plug, value, type="string")
        else:
            cmds.setAttr(target_plug, value)
    except Exception:
        pass


def _copy_joint_settings(source_joint, duplicate_joint):
    for attribute in (
        "rotateOrder",
        "jointOrient",
        "rotateAxis",
        "rotate",
        "preferredAngle",
        "segmentScaleCompensate",
        "radius",
        "side",
        "type",
        "drawStyle",
        "visibility",
    ):
        _copy_joint_attribute(source_joint, duplicate_joint, attribute)

    other_type_plug = source_joint + ".otherType"
    if cmds.objExists(other_type_plug):
        try:
            other_type = cmds.getAttr(other_type_plug)
            if isinstance(other_type, str):
                cmds.setAttr(duplicate_joint + ".otherType", other_type, type="string")
        except Exception:
            pass

    for axis in ("X", "Y", "Z"):
        _copy_joint_attribute(source_joint, duplicate_joint, "jointType" + axis)


def _connect_inverse_scale(parent_joint, child_joint):
    parent_scale = parent_joint + ".scale"
    child_inverse = child_joint + ".inverseScale"
    if not cmds.objExists(parent_scale) or not cmds.objExists(child_inverse):
        return
    existing = cmds.listConnections(child_inverse, source=True, destination=False, plugs=True) or []
    if existing:
        return
    try:
        cmds.connectAttr(parent_scale, child_inverse, force=True)
    except Exception:
        pass


def _scaled_points_about_anchor(points, anchor_point, scale_factor):
    scaled = om.MPointArray()
    anchor = om.MPoint(anchor_point.x, anchor_point.y, anchor_point.z)
    for point in points:
        scaled.append(
            om.MPoint(
                anchor.x + ((point.x - anchor.x) * scale_factor),
                anchor.y + ((point.y - anchor.y) * scale_factor),
                anchor.z + ((point.z - anchor.z) * scale_factor),
            )
        )
    return scaled


def _scale_mesh_points_about_anchor(shape_name, anchor_point, scale_factor):
    dag_path = _dag_path(shape_name)
    mesh_fn = om.MFnMesh(dag_path)
    inverse = dag_path.inclusiveMatrixInverse()
    scaled_object_points = om.MPointArray()
    world_points = mesh_fn.getPoints(om.MSpace.kWorld)
    for point in _scaled_points_about_anchor(world_points, anchor_point, scale_factor):
        scaled_object_points.append(point * inverse)
    mesh_fn.setPoints(scaled_object_points, om.MSpace.kObject)
    mesh_fn.updateSurface()


def _set_mesh_world_points(shape_name, world_points):
    dag_path = _dag_path(shape_name)
    mesh_fn = om.MFnMesh(dag_path)
    inverse = dag_path.inclusiveMatrixInverse()
    object_points = om.MPointArray()
    for point in world_points:
        object_points.append(point * inverse)
    mesh_fn.setPoints(object_points, om.MSpace.kObject)
    mesh_fn.updateSurface()


def _pair_joint_trees(source_joint, duplicate_joint, pairs):
    pairs.append((_node_long_name(source_joint), _node_long_name(duplicate_joint)))
    source_children = cmds.listRelatives(source_joint, children=True, fullPath=True, type="joint") or []
    duplicate_children = cmds.listRelatives(duplicate_joint, children=True, fullPath=True, type="joint") or []
    if len(source_children) != len(duplicate_children):
        raise RuntimeError("The copied skeleton no longer matches the source joint hierarchy.")
    for source_child, duplicate_child in zip(source_children, duplicate_children):
        _pair_joint_trees(source_child, duplicate_child, pairs)


def _rename_duplicate_joint_tree(source_joint, duplicate_joint):
    source_short = _short_name(source_joint)
    duplicate_short = _short_name(duplicate_joint)
    current_duplicate = duplicate_joint
    if source_short != duplicate_short:
        current_duplicate = _node_long_name(cmds.rename(duplicate_joint, source_short))
    source_children = cmds.listRelatives(source_joint, children=True, fullPath=True, type="joint") or []
    duplicate_children = cmds.listRelatives(current_duplicate, children=True, fullPath=True, type="joint") or []
    if len(source_children) != len(duplicate_children):
        raise RuntimeError("Could not rename the copied skeleton cleanly.")
    for source_child, duplicate_child in zip(source_children, duplicate_children):
        _rename_duplicate_joint_tree(source_child, duplicate_child)
    return current_duplicate


def _duplicate_scaled_skeleton(skeleton_root, export_group, scale_factor, anchor_point):
    joint_map = {}
    source_root = _node_long_name(skeleton_root)
    duplicate_root = ""

    def rebuild_joint(source_joint, duplicate_parent):
        nonlocal duplicate_root
        duplicate_joint = cmds.createNode("joint", name=_short_name(source_joint), parent=duplicate_parent, skipSelect=True)
        duplicate_joint = _node_long_name(duplicate_joint)
        joint_map[_node_long_name(source_joint)] = duplicate_joint
        if _node_long_name(source_joint) == source_root:
            duplicate_root = duplicate_joint

        _copy_joint_settings(source_joint, duplicate_joint)
        cmds.setAttr(duplicate_joint + ".scaleX", 1.0)
        cmds.setAttr(duplicate_joint + ".scaleY", 1.0)
        cmds.setAttr(duplicate_joint + ".scaleZ", 1.0)

        cmds.xform(
            duplicate_joint,
            worldSpace=True,
            matrix=_matrix_to_list(
                _scaled_world_matrix_about_anchor(
                    source_joint,
                    anchor_point,
                    scale_factor,
                )
            ),
        )
        cmds.setAttr(duplicate_joint + ".scaleX", 1.0)
        cmds.setAttr(duplicate_joint + ".scaleY", 1.0)
        cmds.setAttr(duplicate_joint + ".scaleZ", 1.0)
        duplicate_joint_parent = cmds.listRelatives(
            duplicate_joint,
            parent=True,
            fullPath=True,
            type="joint",
        ) or []
        if duplicate_joint_parent:
            _connect_inverse_scale(duplicate_joint_parent[0], duplicate_joint)

        return duplicate_joint

    duplicate_root = rebuild_joint(source_root, _node_long_name(export_group))
    for source_joint in _joint_hierarchy(source_root)[1:]:
        source_parent = cmds.listRelatives(source_joint, parent=True, fullPath=True, type="joint") or []
        if source_parent and _node_long_name(source_parent[0]) in joint_map:
            duplicate_parent = joint_map[_node_long_name(source_parent[0])]
            rebuild_joint(source_joint, duplicate_parent)
        else:
            rebuild_joint(source_joint, duplicate_root)
    return duplicate_root, joint_map


def _visible_mesh_shape_in_duplicate(transform_name):
    shapes = cmds.listRelatives(transform_name, shapes=True, fullPath=True, type="mesh") or []
    visible_shapes = []
    for shape_name in shapes:
        try:
            if cmds.getAttr(shape_name + ".intermediateObject"):
                continue
        except Exception:
            pass
        visible_shapes.append(shape_name)
    return visible_shapes[0] if visible_shapes else ""


def _copy_scope_nodes(export_group):
    if not export_group or not cmds.objExists(export_group):
        return []
    nodes = [_node_long_name(export_group)]
    nodes.extend(cmds.listRelatives(export_group, allDescendents=True, fullPath=True) or [])
    for node_name in list(nodes):
        if not node_name or not cmds.objExists(node_name):
            continue
        try:
            if cmds.nodeType(node_name) == "mesh":
                nodes.extend(cmds.listHistory(node_name, pruneDagObjects=True) or [])
        except Exception:
            pass
        try:
            nodes.extend(cmds.listConnections(node_name, type="animCurve") or [])
        except Exception:
            pass
    canonical = []
    for node_name in _dedupe_preserve_order(nodes):
        if not node_name or not cmds.objExists(node_name):
            continue
        try:
            canonical.append(_node_long_name(node_name))
        except Exception:
            canonical.append(str(node_name))
    return _dedupe_preserve_order(canonical)


def _verify_copy_independence(export_group, source_snapshot):
    source_by_uuid = {}
    for source_name, state in ((source_snapshot or {}).get("nodes") or {}).items():
        source_uuid = (state or {}).get("uuid")
        if source_uuid:
            source_by_uuid[str(source_uuid)] = str(source_name)
    copy_nodes = _copy_scope_nodes(export_group)
    copy_uuids = set()
    for node_name in copy_nodes:
        copy_uuid = _uuid_for_node(node_name)
        if copy_uuid:
            copy_uuids.add(copy_uuid)
    dependencies = []
    seen = set()
    for copy_node in copy_nodes:
        try:
            connected_nodes = cmds.listConnections(
                copy_node,
                source=True,
                destination=True,
            ) or []
        except Exception:
            connected_nodes = []
        for connected_node in connected_nodes:
            if not connected_node or not cmds.objExists(connected_node):
                continue
            source_uuid = _uuid_for_node(connected_node)
            if not source_uuid or source_uuid in copy_uuids or source_uuid not in source_by_uuid:
                continue
            key = (str(copy_node), str(source_uuid))
            if key in seen:
                continue
            seen.add(key)
            dependencies.append(
                {
                    "copy_node": str(copy_node),
                    "copy_type": str(cmds.nodeType(copy_node)),
                    "source_node": source_by_uuid[source_uuid],
                    "source_type": str(cmds.nodeType(connected_node)),
                }
            )
    return {
        "passed": not dependencies,
        "copy_node_count": len(copy_nodes),
        "source_node_count": len(source_by_uuid),
        "dependencies": dependencies,
    }


def _build_scaled_mesh_snapshot(mesh_report, export_group, anchor_point, scale_factor):
    source_transform = mesh_report["source_transform"]
    source_shape = mesh_report["source_shape"]
    duplicate_name = _unique_name(_short_name(source_transform) + "_scaledPreview")
    duplicate_transform = cmds.createNode(
        "transform",
        name=duplicate_name,
        parent=export_group,
        skipSelect=True,
    )
    duplicate_transform = _node_long_name(duplicate_transform)
    _set_world_matrix_without_scale(duplicate_transform, source_transform)

    mesh_copy_fn = om.MFnMesh()
    copied_shape_object = mesh_copy_fn.copy(
        _depend_node(source_shape),
        _depend_node(duplicate_transform),
    )
    duplicate_shape = om.MFnDagNode(copied_shape_object).fullPathName()
    duplicate_transform = _node_long_name(cmds.rename(duplicate_transform, _short_name(source_transform)))
    try:
        duplicate_shape = _node_long_name(
            cmds.rename(
                (cmds.listRelatives(duplicate_transform, shapes=True, fullPath=True, type="mesh") or [duplicate_shape])[0],
                _short_name(source_shape),
            )
        )
    except Exception:
        duplicate_shape = _visible_mesh_shape_in_duplicate(duplicate_transform)
    if not duplicate_shape:
        raise RuntimeError("Could not build a history-free mesh snapshot for {0}.".format(_short_name(source_transform)))

    _unlock_transform_channels(duplicate_transform)
    original_world_points = mesh_report.get("world_points") or _capture_true_world_points(duplicate_shape)
    cmds.setAttr(duplicate_transform + ".scaleX", 1.0)
    cmds.setAttr(duplicate_transform + ".scaleY", 1.0)
    cmds.setAttr(duplicate_transform + ".scaleZ", 1.0)
    _set_mesh_world_points(duplicate_shape, original_world_points)
    baseline_world_points = _capture_true_world_points(duplicate_shape)
    _scale_mesh_points_about_anchor(duplicate_shape, anchor_point, scale_factor)

    if mesh_report["uv_summary"].get("current"):
        try:
            cmds.polyUVSet(duplicate_shape, currentUVSet=True, uvSet=mesh_report["uv_summary"]["current"])
        except Exception:
            pass
    _apply_shading_assignments(duplicate_transform, duplicate_shape, mesh_report["shading_assignments"])
    return duplicate_transform, duplicate_shape, baseline_world_points


def _mapped_influences(mesh_report, joint_map):
    mapped = []
    missing = []
    for entry in mesh_report["skin_data"]["influences"]:
        source_path = entry.get("path", "")
        duplicate_path = joint_map.get(source_path)
        if not duplicate_path or not cmds.objExists(duplicate_path):
            missing.append(source_path or entry.get("uuid", ""))
            continue
        mapped.append(
            {
                "path": duplicate_path,
                "uuid": _uuid_for_node(duplicate_path),
                "weights": list(entry.get("weights", [])),
            }
        )
    return mapped, missing


def _bind_scaled_mesh(duplicate_transform, duplicate_shape, mesh_report, joint_map):
    mapped_influences, missing = _mapped_influences(mesh_report, joint_map)
    if missing:
        raise RuntimeError("Missing copied joints for: {0}".format(", ".join(_short_name(item) for item in missing if item)))

    skin_data = mesh_report["skin_data"]
    influence_paths = [entry["path"] for entry in mapped_influences]
    settings = skin_data["settings"]
    max_influences = max(int(settings.get("maxInfluences", 5)), len(influence_paths), 1)
    cluster_name = _unique_name(_short_name(mesh_report["skin_cluster"]) + "_scaled")
    new_skin_cluster = cmds.skinCluster(
        influence_paths,
        duplicate_transform,
        name=cluster_name,
        toSelectedBones=True,
        bindMethod=int(settings.get("bindMethod", 0)),
        skinMethod=int(settings.get("skinningMethod", 0)),
        normalizeWeights=0,
        maximumInfluences=max_influences,
        obeyMaxInfluences=False,
        weightDistribution=int(settings.get("weightDistribution", 0)),
        removeUnusedInfluence=False,
    )[0]

    for attribute in ("useComponents", "deformUserNormals"):
        if attribute in settings and cmds.attributeQuery(attribute, node=new_skin_cluster, exists=True):
            try:
                cmds.setAttr("{0}.{1}".format(new_skin_cluster, attribute), settings[attribute])
            except Exception:
                pass

    skin_fn = oma.MFnSkinCluster(_depend_node(new_skin_cluster))
    shape_dag = _dag_path(duplicate_shape)
    component = _all_vertex_component(skin_data["vertex_count"])

    influence_order = []
    for influence_dag in skin_fn.influenceObjects():
        physical_index = int(skin_fn.indexForInfluenceObject(influence_dag))
        full_path = influence_dag.fullPathName()
        influence_order.append(
            {
                "path": full_path,
                "uuid": _uuid_for_node(full_path),
                "physical_index": physical_index,
            }
        )
    influence_order.sort(key=lambda item: item["physical_index"])

    source_weight_map = {}
    for entry in mapped_influences:
        source_weight_map[entry["uuid"] or entry["path"]] = list(entry["weights"])

    indices = om.MIntArray()
    weights = om.MDoubleArray()
    for entry in influence_order:
        indices.append(entry["physical_index"])
    for vertex_index in range(skin_data["vertex_count"]):
        for entry in influence_order:
            weights.append(float(source_weight_map[entry["uuid"] or entry["path"]][vertex_index]))

    skin_fn.setWeights(shape_dag, component, indices, weights, normalize=False)
    skin_fn.setBlendWeights(shape_dag, component, om.MDoubleArray(skin_data["blend_weights"]))
    for attribute in ("normalizeWeights", "maintainMaxInfluences", "maxInfluences"):
        if attribute in settings and cmds.attributeQuery(attribute, node=new_skin_cluster, exists=True):
            try:
                cmds.setAttr("{0}.{1}".format(new_skin_cluster, attribute), settings[attribute])
            except Exception:
                pass
    return new_skin_cluster


def _max_point_delta(source_points, target_points):
    if len(source_points) != len(target_points):
        return float("inf")
    max_delta = 0.0
    for source_point, target_point in zip(source_points, target_points):
        max_delta = max(max_delta, _distance_between_points(source_point, target_point))
    return max_delta


def _verify_scaled_mesh(mesh_report, duplicate_transform, duplicate_shape, new_skin_cluster, joint_map, anchor_point, scale_factor, baseline_world_points):
    checks = []

    def add_check(label, passed, details):
        checks.append({"label": label, "passed": bool(passed), "details": details})

    duplicate_signature = _capture_topology_signature(duplicate_shape)
    source_signature = mesh_report["topology_signature"]
    topology_ok = (
        duplicate_signature["vertex_count"] == source_signature["vertex_count"]
        and duplicate_signature["face_count"] == source_signature["face_count"]
        and duplicate_signature["counts"] == source_signature["counts"]
        and duplicate_signature["indices"] == source_signature["indices"]
    )
    add_check("Topology + vertex order", topology_ok, "{0} verts, {1} faces".format(duplicate_signature["vertex_count"], duplicate_signature["face_count"]))

    scale = cmds.getAttr(duplicate_transform + ".scale")[0]
    scale_ok = all(abs(value - 1.0) <= VALUE_EPSILON for value in scale)
    add_check("Mesh scale is 1,1,1", scale_ok, "scale = {0:.6f}, {1:.6f}, {2:.6f}".format(scale[0], scale[1], scale[2]))

    expected_points = _scaled_points_about_anchor(baseline_world_points, anchor_point, scale_factor)
    duplicate_points = _capture_true_world_points(duplicate_shape)
    point_delta = _max_point_delta(expected_points, duplicate_points)
    add_check("Viewport shape matches scaled result", point_delta <= POINT_EPSILON, "max point delta = {0:.8f} limit = {1:.8f}".format(point_delta, POINT_EPSILON))

    duplicate_skin_data = _capture_skin_data(duplicate_shape, new_skin_cluster)
    source_weight_map = {}
    for entry in mesh_report["skin_data"]["influences"]:
        duplicate_path = joint_map.get(entry["path"])
        if duplicate_path:
            source_weight_map[_uuid_for_node(duplicate_path) or duplicate_path] = entry["weights"]

    max_weight_delta = 0.0
    influence_mismatch = []
    for entry in duplicate_skin_data["influences"]:
        key = entry["uuid"] or entry["path"]
        if key not in source_weight_map:
            influence_mismatch.append(entry["path"])
            continue
        for source_value, duplicate_value in zip(source_weight_map[key], entry["weights"]):
            max_weight_delta = max(max_weight_delta, abs(source_value - duplicate_value))
    add_check("Skin weights match by vertex", not influence_mismatch and max_weight_delta <= VALUE_EPSILON, "max weight delta = {0:.8f}".format(max_weight_delta))

    max_blend_delta = 0.0
    for source_value, duplicate_value in zip(mesh_report["skin_data"]["blend_weights"], duplicate_skin_data["blend_weights"]):
        max_blend_delta = max(max_blend_delta, abs(source_value - duplicate_value))
    add_check("Skin blend weights match", max_blend_delta <= VALUE_EPSILON, "max blend delta = {0:.8f}".format(max_blend_delta))

    duplicate_assignments = _capture_shading_assignments(duplicate_transform, duplicate_shape)
    add_check("Face-based materials match", _normalized_shading_assignments(duplicate_assignments) == _normalized_shading_assignments(mesh_report["shading_assignments"]), "{0} material slot groups".format(len(duplicate_assignments)))

    duplicate_uv = _capture_uv_summary(duplicate_shape)
    add_check("UV sets match", duplicate_uv["names"] == mesh_report["uv_summary"]["names"] and duplicate_uv["current"] == mesh_report["uv_summary"]["current"], "current UV set = {0}".format(duplicate_uv["current"] or "None"))

    duplicate_color = _capture_color_summary(duplicate_shape)
    add_check("Color sets match", duplicate_color["names"] == mesh_report["color_summary"]["names"] and duplicate_color["current"] == mesh_report["color_summary"]["current"], "current color set = {0}".format(duplicate_color["current"] or "None"))

    duplicate_smoothing = _capture_edge_smoothing(duplicate_shape)
    add_check("Hard/soft edges match", duplicate_smoothing == mesh_report["edge_smoothing"], "{0} edges checked".format(len(duplicate_smoothing)))

    duplicate_normals = _capture_world_normals(duplicate_shape)
    normal_delta = _max_normal_delta(mesh_report["world_normals"], duplicate_normals)
    add_check("Normals stay the same", normal_delta <= NORMAL_EPSILON, "max normal delta = {0:.8f}".format(normal_delta))

    non_blocking_labels = {"Color sets match", "Normals stay the same"}
    if not mesh_report.get("source_visible", True):
        non_blocking_labels.add("Viewport shape matches scaled result")
    blocking_failures = [check for check in checks if not check["passed"] and check["label"] not in non_blocking_labels]
    return {"checks": checks, "passed": not blocking_failures, "blocking_failures": blocking_failures}


def _bounded_animation_verification_times(sample_times, limit=9):
    ordered = sorted({float(value) for value in (sample_times or [])})
    sample_limit = max(2, int(limit))
    if len(ordered) <= sample_limit:
        return ordered
    last_index = len(ordered) - 1
    indices = {
        int(round(last_index * (float(index) / float(sample_limit - 1))))
        for index in range(sample_limit)
    }
    return [ordered[index] for index in sorted(indices)]


def _verify_scaled_animation_geometry(
    mesh_reports,
    mesh_results,
    joint_map,
    anchor_node,
    sample_times,
    scale_factor,
):
    verification_times = _bounded_animation_verification_times(sample_times)
    if not verification_times:
        return {
            "passed": True,
            "supported": False,
            "sample_count": 0,
            "sample_times": [],
            "mesh_checks": 0,
            "hidden_mesh_checks": 0,
            "point_checks": 0,
            "hidden_point_checks": 0,
            "max_point_delta": 0.0,
            "hidden_max_point_delta": 0.0,
            "joint_checks": 0,
            "max_joint_position_delta": 0.0,
            "max_joint_rotation_delta_degrees": 0.0,
            "joint_failures": [],
            "hidden_mesh_waivers": [],
            "failures": [],
        }
    if not anchor_node or not cmds.objExists(anchor_node):
        return {
            "passed": False,
            "supported": True,
            "sample_count": len(verification_times),
            "sample_times": verification_times,
            "mesh_checks": 0,
            "hidden_mesh_checks": 0,
            "point_checks": 0,
            "hidden_point_checks": 0,
            "max_point_delta": 0.0,
            "hidden_max_point_delta": 0.0,
            "joint_checks": 0,
            "max_joint_position_delta": 0.0,
            "max_joint_rotation_delta_degrees": 0.0,
            "joint_failures": [],
            "hidden_mesh_waivers": [],
            "failures": [{"reason": "missing_character_anchor", "anchor_node": str(anchor_node or "")}],
        }

    visible_mesh_reports = [
        item
        for item in (mesh_reports or [])
        if item.get("source_visible", True)
    ]
    visible_measurement = measure_mesh_reports(
        visible_mesh_reports,
        axis=MEASUREMENT_AXIS_DEFAULT,
    )
    source_height = float(visible_measurement.get("height") or 0.0)
    scene_unit = _scene_linear_unit()
    physical_max_scene = convert_linear_value(
        ANIMATION_DEFORMATION_MAX_CM,
        UNIT_CM,
        UNIT_SCENE,
        scene_unit=scene_unit,
    )
    animation_point_tolerance = max(
        float(POINT_EPSILON),
        source_height * float(ANIMATION_DEFORMATION_RELATIVE_LIMIT),
    )
    animation_point_tolerance = min(
        animation_point_tolerance,
        float(physical_max_scene),
    )

    results_by_source = {
        str(item.get("source_transform") or ""): item
        for item in (mesh_results or [])
        if item.get("source_transform")
    }
    failures = []
    hidden_mesh_waivers = []
    joint_failures = []
    mesh_checks = 0
    hidden_mesh_checks = 0
    point_checks = 0
    hidden_point_checks = 0
    max_point_delta = 0.0
    hidden_max_point_delta = 0.0
    max_delta_pair = {}
    joint_checks = 0
    max_joint_position_delta = 0.0
    max_joint_rotation_delta = 0.0
    max_joint_delta_pair = {}

    def _quaternion_delta_degrees(first, second):
        dot = abs(
            (float(first.x) * float(second.x))
            + (float(first.y) * float(second.y))
            + (float(first.z) * float(second.z))
            + (float(first.w) * float(second.w))
        )
        dot = max(-1.0, min(1.0, dot))
        return math.degrees(2.0 * math.acos(dot))

    original_time = float(cmds.currentTime(query=True))
    try:
        for sample_time in verification_times:
            cmds.currentTime(sample_time, edit=True, update=True)
            _force_geometry_evaluation()
            anchor_point = _world_translation(anchor_node)
            for source_joint, duplicate_joint in sorted(
                (joint_map or {}).items(),
                key=lambda item: item[0].count("|"),
            ):
                joint_checks += 1
                if (
                    not cmds.objExists(source_joint)
                    or not cmds.objExists(duplicate_joint)
                ):
                    joint_failures.append(
                        {
                            "time": float(sample_time),
                            "source_joint": str(source_joint),
                            "duplicate_joint": str(duplicate_joint),
                            "reason": "missing_source_or_copy_joint",
                        }
                    )
                    continue
                source_position = _world_translation(source_joint)
                expected_position = anchor_point + (
                    (source_position - anchor_point) * float(scale_factor)
                )
                duplicate_position = _world_translation(duplicate_joint)
                position_delta = _distance_between_points(
                    expected_position,
                    duplicate_position,
                )
                rotation_delta = _quaternion_delta_degrees(
                    _world_quaternion(source_joint),
                    _world_quaternion(duplicate_joint),
                )
                if (
                    position_delta > max_joint_position_delta
                    or rotation_delta > max_joint_rotation_delta
                ):
                    max_joint_delta_pair = {
                        "time": float(sample_time),
                        "source_joint": str(source_joint),
                        "duplicate_joint": str(duplicate_joint),
                        "position_delta": float(position_delta),
                        "rotation_delta_degrees": float(rotation_delta),
                    }
                max_joint_position_delta = max(
                    max_joint_position_delta,
                    float(position_delta),
                )
                max_joint_rotation_delta = max(
                    max_joint_rotation_delta,
                    float(rotation_delta),
                )
                if (
                    position_delta > POINT_EPSILON
                    or rotation_delta > 1.0e-4
                ):
                    joint_failures.append(
                        {
                            "time": float(sample_time),
                            "source_joint": str(source_joint),
                            "duplicate_joint": str(duplicate_joint),
                            "position_delta": float(position_delta),
                            "position_limit": float(POINT_EPSILON),
                            "rotation_delta_degrees": float(rotation_delta),
                            "rotation_limit_degrees": 1.0e-4,
                            "reason": "scaled_animation_joint_mismatch",
                        }
                    )
            for mesh_report in mesh_reports or []:
                source_transform = str(mesh_report.get("source_transform") or "")
                mesh_result = results_by_source.get(source_transform) or {}
                source_shape = mesh_report.get("source_shape") or ""
                duplicate_shape = mesh_result.get("duplicate_shape") or ""
                source_visible = bool(mesh_report.get("source_visible", True))
                issue_rows = failures if source_visible else hidden_mesh_waivers
                if source_visible:
                    mesh_checks += 1
                else:
                    hidden_mesh_checks += 1
                if (
                    not source_shape
                    or not duplicate_shape
                    or not cmds.objExists(source_shape)
                    or not cmds.objExists(duplicate_shape)
                ):
                    issue_rows.append(
                        {
                            "time": float(sample_time),
                            "source_transform": source_transform,
                            "reason": "missing_source_or_copy_shape",
                            "source_visible": source_visible,
                        }
                    )
                    continue
                try:
                    source_points = _capture_true_world_points(source_shape)
                    duplicate_points = _capture_true_world_points(duplicate_shape)
                    expected_points = _scaled_points_about_anchor(
                        source_points,
                        anchor_point,
                        scale_factor,
                    )
                    if source_visible:
                        point_checks += len(expected_points)
                    else:
                        hidden_point_checks += len(expected_points)
                    point_delta = _max_point_delta(expected_points, duplicate_points)
                except Exception as exc:
                    issue_rows.append(
                        {
                            "time": float(sample_time),
                            "source_transform": source_transform,
                            "reason": "geometry_read_failed",
                            "error": str(exc),
                            "source_visible": source_visible,
                        }
                    )
                    continue
                if source_visible and point_delta > max_point_delta:
                    max_point_delta = float(point_delta)
                    max_delta_pair = {
                        "time": float(sample_time),
                        "source_transform": source_transform,
                        "duplicate_shape": str(duplicate_shape),
                    }
                if not source_visible:
                    hidden_max_point_delta = max(
                        hidden_max_point_delta,
                        float(point_delta),
                    )
                if point_delta > animation_point_tolerance:
                    issue_rows.append(
                        {
                            "time": float(sample_time),
                            "source_transform": source_transform,
                            "duplicate_shape": str(duplicate_shape),
                            "max_point_delta": float(point_delta),
                            "limit": float(animation_point_tolerance),
                            "reason": "scaled_animation_shape_mismatch",
                            "source_visible": source_visible,
                        }
                    )
    finally:
        cmds.currentTime(original_time, edit=True, update=True)

    return {
        "passed": bool(
            mesh_checks
            and joint_checks
            and not failures
            and not joint_failures
        ),
        "supported": True,
        "sample_count": len(verification_times),
        "sample_times": verification_times,
        "scene_linear_unit": scene_unit,
        "source_height": source_height,
        "animation_point_tolerance": float(animation_point_tolerance),
        "animation_point_tolerance_cm": float(
            convert_linear_value(
                animation_point_tolerance,
                UNIT_SCENE,
                UNIT_CM,
                scene_unit=scene_unit,
            )
        ),
        "animation_relative_height_limit": float(
            ANIMATION_DEFORMATION_RELATIVE_LIMIT
        ),
        "animation_max_physical_tolerance_cm": float(
            ANIMATION_DEFORMATION_MAX_CM
        ),
        "mesh_checks": int(mesh_checks),
        "hidden_mesh_checks": int(hidden_mesh_checks),
        "point_checks": int(point_checks),
        "hidden_point_checks": int(hidden_point_checks),
        "max_point_delta": float(max_point_delta),
        "hidden_max_point_delta": float(hidden_max_point_delta),
        "max_delta_pair": max_delta_pair,
        "joint_checks": int(joint_checks),
        "max_joint_position_delta": float(max_joint_position_delta),
        "max_joint_rotation_delta_degrees": float(max_joint_rotation_delta),
        "max_joint_delta_pair": max_joint_delta_pair,
        "joint_failures": joint_failures[:16],
        "hidden_mesh_waivers": hidden_mesh_waivers[:16],
        "failures": failures[:16],
    }


def _validate_joint_scales(joint_names):
    failing = []
    for joint_name in joint_names:
        scale = _safe_get_vector_attr(joint_name, "scale")
        if any(abs(value - 1.0) > 0.001 for value in scale):
            failing.append("{0} ({1:.4f}, {2:.4f}, {3:.4f})".format(_short_name(joint_name), scale[0], scale[1], scale[2]))
    return failing


def _format_report(report):
    if not report:
        return "Pick one rig control plus the top skeleton joint, then click Check Setup."

    scale_factor = float(report.get("scale_factor") or 1.0)
    scale_mode = report.get("scale_mode") or SCALE_MODE_FACTOR_PERCENT
    mode_labels = {
        SCALE_MODE_FACTOR_PERCENT: "Factor / Percent",
        SCALE_MODE_FACTOR: "Factor",
        SCALE_MODE_PERCENT: "Percent",
        SCALE_MODE_TARGET_HEIGHT: "Target Height",
        SCALE_MODE_HEIGHT_CHANGE: "Height Change",
    }
    measurement = report.get("measurement") or {}
    measurement_text = format_measurement(
        measurement,
        factor=scale_factor if measurement.get("measurable") else None,
        display_unit=report.get("scale_unit") or UNIT_SCENE,
        scene_unit=report.get("scene_linear_unit") or UNIT_CM,
    )
    lines = [
        "Controls Root: {0}".format(report.get("controls_root") or report.get("character_root") or "(auto from skeleton)"),
        "Skeleton Root: {0}".format(report.get("skeleton_root") or "(none)"),
        "Scale: {0} = {1:.6g} (factor, {2:.4g}%)".format(mode_labels.get(scale_mode, scale_mode), report.get("scale_value", scale_factor * 100.0), scale_factor * 100.0),
        measurement_text,
        "Meshes Found: {0}".format(len(report.get("meshes", []))),
        "",
    ]

    errors = report.get("errors", [])
    warnings = report.get("warnings", [])
    if errors:
        lines.append("RED")
        for item in errors:
            lines.append("- " + item)
        lines.append("")
    if warnings:
        lines.append("YELLOW")
        for item in warnings:
            lines.append("- " + item)
        lines.append("")
    if not errors and not warnings:
        lines.append("GREEN")
        lines.append("- This setup looks ready for an export copy.")
        lines.append("")

    if report.get("meshes"):
        lines.append("Meshes")
        for mesh_report in report["meshes"]:
            lines.append("- {0}: {1} influences".format(_short_name(mesh_report["source_transform"]), len(mesh_report["skin_data"]["influences"])))
        lines.append("")

    result = report.get("result")
    if result:
        lines.append("Rig Copy")
        lines.append("- Group: {0}".format(result.get("export_group", "")))
        lines.append("- Joints kept at 1,1,1: {0}".format("Yes" if result.get("joints_verified") else "No"))
        lines.append("- Meshes rebuilt: {0}".format(len(result.get("mesh_results", []))))
        animation = result.get("animation") or {}
        if animation.get("baked"):
            lines.append(
                "- Animation baked: {0:g} to {1:g} across {2} samples".format(
                    animation.get("start", 0.0),
                    animation.get("end", 0.0),
                    animation.get("sample_count", 0),
                )
            )
        else:
            lines.append("- Animation baked: No keyed animation found")
        lines.append("")

        unreal_export = result.get("unreal_export") or {}
        if unreal_export:
            lines.append("Unreal FBX")
            lines.append("- Path: {0}".format(unreal_export.get("path", "")))
            lines.append("- Verified: {0}".format("Yes" if unreal_export.get("verified") else "No"))
            lines.append("- Source untouched: {0}".format("Yes" if unreal_export.get("source_untouched") else "No"))
            lines.append("")

    return "\n".join(lines).strip()


class MayaRigScaleExportController(object):
    def __init__(self):
        self.character_root = ""
        self.skeleton_root = ""
        self._scale_factor = 1.0
        self._scale_factor_override = False
        self._scale_mode = SCALE_MODE_FACTOR_PERCENT
        self._scale_value = 100.0
        self._scale_unit = UNIT_SCENE
        self._measurement_axis = MEASUREMENT_AXIS_DEFAULT
        self.copy_suffix = DEFAULT_COPY_SUFFIX
        self.report = None
        self.result = None
        self.status_callback = None
        # Optional, bounded diagnostics for heavy real-rig analysis.  Normal
        # UI callers leave this unset, so the production path has no logging
        # or file-I/O overhead.  A verifier may provide a callback to surface
        # the current mesh/substage before a long Maya API call.
        self.analysis_trace_callback = None
        self.analysis_trace = []
        self.build_trace_callback = None
        self.build_trace = []

    def _analysis_checkpoint(self, phase, **details):
        entry = {"phase": str(phase), "details": dict(details)}
        self.analysis_trace = (self.analysis_trace + [entry])[-64:]
        callback = self.analysis_trace_callback
        if callback is not None:
            try:
                callback(entry)
            except Exception:
                # Diagnostics must never change the result of a rig analysis.
                pass

    def _build_checkpoint(self, phase, **details):
        entry = {"phase": str(phase), "details": dict(details)}
        self.build_trace = (self.build_trace + [entry])[-64:]
        callback = self.build_trace_callback
        if callback is not None:
            try:
                callback(entry)
            except Exception:
                # Diagnostics must never change copy/export truth.
                pass

    @property
    def controls_root(self):
        return self.character_root

    @controls_root.setter
    def controls_root(self, value):
        self.character_root = value or ""

    @property
    def scale_factor(self):
        return float(self._scale_factor)

    @scale_factor.setter
    def scale_factor(self, value):
        self._scale_factor = float(value)
        self._scale_factor_override = True

    @property
    def scale_percent(self):
        return float(self.scale_factor) * 100.0

    @scale_percent.setter
    def scale_percent(self, value):
        self._scale_value = float(value)
        self._scale_mode = SCALE_MODE_FACTOR_PERCENT
        self._scale_factor = self._scale_value / 100.0
        self._scale_factor_override = True

    @property
    def scale_mode(self):
        return self._scale_mode

    @scale_mode.setter
    def scale_mode(self, value):
        self._scale_mode = normalize_scale_mode(value)
        self._scale_factor_override = False

    @property
    def scale_value(self):
        return float(self._scale_value)

    @scale_value.setter
    def scale_value(self, value):
        self._scale_value = float(value)
        self._scale_factor_override = False

    @property
    def scale_unit(self):
        return self._scale_unit

    @scale_unit.setter
    def scale_unit(self, value):
        self._scale_unit = normalize_linear_unit(value)
        self._scale_factor_override = False

    @property
    def measurement_axis(self):
        return self._measurement_axis

    @measurement_axis.setter
    def measurement_axis(self, value):
        self._measurement_axis = normalize_measurement_axis(value)

    def set_scale_specification(self, mode, value, unit=UNIT_SCENE, axis=MEASUREMENT_AXIS_DEFAULT):
        self._scale_mode = normalize_scale_mode(mode)
        self._scale_value = float(value)
        self._scale_unit = normalize_linear_unit(unit)
        self._measurement_axis = normalize_measurement_axis(axis)
        self._scale_factor_override = False

    def shutdown(self):
        pass

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _set_status(self, message, success):
        if self.status_callback:
            self.status_callback(message, success)
        if success:
            _debug(message)
        else:
            _warning(message)

    def report_text(self):
        return _format_report(self.report)

    def _input_signature(self):
        return (
            self.character_root or "",
            self.skeleton_root or "",
            round(float(self.scale_factor), 8),
            self.scale_mode,
            round(float(self.scale_value), 8),
            self.scale_unit,
            self.measurement_axis,
            bool(self._scale_factor_override),
            self.copy_suffix or DEFAULT_COPY_SUFFIX,
        )

    def _measurement_status(self):
        if not self.report:
            return ""
        measurement = self.report.get("measurement") or {}
        return format_measurement(
            measurement,
            factor=self.report.get("scale_factor") if measurement.get("measurable") else None,
            display_unit=self.report.get("scale_unit") or self.scale_unit,
            scene_unit=self.report.get("scene_linear_unit") or UNIT_CM,
        )

    def set_character_from_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        character_root, message = _selected_character_candidate()
        if not character_root:
            return False, message
        self.character_root = character_root
        return True, "Controls root set to {0}.".format(_short_name(character_root))

    def set_controls_from_selection(self):
        return self.set_character_from_selection()

    def set_skeleton_from_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        skeleton_root, message = _selected_skeleton_candidate()
        if not skeleton_root:
            return False, message
        self.skeleton_root = skeleton_root
        return True, "Skeleton root set to {0}.".format(_short_name(skeleton_root))

    def analyze_setup(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."

        character_root = _node_long_name(self.character_root) if self.character_root and cmds.objExists(self.character_root) else ""
        skeleton_root = _node_long_name(self.skeleton_root) if self.skeleton_root and cmds.objExists(self.skeleton_root) else ""
        errors = []
        warnings = []
        self.analysis_trace = []
        self._analysis_checkpoint(
            "analysis_start",
            character_root=character_root,
            skeleton_hint=skeleton_root,
        )

        mesh_targets = _mesh_targets_under_character(character_root) if character_root else []
        self._analysis_checkpoint(
            "mesh_targets_done",
            target_count=len(mesh_targets),
            character_root=character_root,
        )
        skeleton_roots = _infer_skeleton_roots(
            character_root=character_root,
            skeleton_hint=skeleton_root,
            mesh_targets=mesh_targets,
        )
        self._analysis_checkpoint(
            "skeleton_roots_done",
            root_count=len(skeleton_roots),
            roots=list(skeleton_roots[:8]),
        )
        if not skeleton_roots:
            errors.append("Pick the top skeleton joint first, or pick a character root that contains skinned joints.")

        if not errors:
            if not mesh_targets:
                mesh_targets = _mesh_targets_from_skeletons(skeleton_roots, character_root)
            if not mesh_targets:
                errors.append("No skinned polygon meshes were found for this character and skeleton.")

        joint_names = []
        for root_joint in skeleton_roots:
            joint_names.extend(_joint_hierarchy(root_joint))
        joint_names = _dedupe_preserve_order(joint_names)
        if joint_names:
            bad_scales = _validate_joint_scales(joint_names)
            if bad_scales:
                warnings.append("These source joints already have local scale values; Aminate will bake the visible result into a clean export skeleton: {0}".format(", ".join(bad_scales[:8])))
            for root_joint in skeleton_roots:
                warnings.extend(_ancestor_transform_warnings(root_joint))
        warnings.extend(_linear_unit_warning())
        self.character_root = character_root
        self.skeleton_root = skeleton_roots[0] if skeleton_roots else skeleton_root

        mesh_reports = []
        if not errors:
            joint_set = set(joint_names)
            ordered_targets = sorted(mesh_targets, key=lambda item: item["transform"].count("|"))
            target_count = len(ordered_targets)
            for mesh_index, target in enumerate(ordered_targets, 1):
                source_transform = target["transform"]
                source_shape = target["shape"]
                visible_shape = source_shape
                skin_cluster = target["skin_cluster"]
                mesh_errors = []
                mesh_warnings = []
                self._analysis_checkpoint(
                    "mesh_start",
                    index=mesh_index,
                    total=target_count,
                    mesh=source_transform,
                    shape=source_shape,
                    skin_cluster=skin_cluster,
                )
                unsupported_history = _unsupported_history_nodes(source_shape, skin_cluster)
                animated_unsupported = _animated_unsupported_history_nodes(unsupported_history)
                if unsupported_history:
                    names = ", ".join("{0} ({1})".format(_short_name(node_name), node_type) for node_name, node_type in unsupported_history)
                    if animated_unsupported:
                        animated_names = ", ".join("{0} ({1})".format(_short_name(node_name), node_type) for node_name, node_type in animated_unsupported)
                        mesh_errors.append(
                            "{0} has animated non-skin deformers that cannot be faithfully preserved in an Unreal skeletal FBX; export is blocked: {1}".format(
                                _short_name(source_transform),
                                animated_names,
                            )
                        )
                    else:
                        mesh_warnings.append(
                            "{0} has extra deformation history that will be baked into the export mesh: {1}".format(
                                _short_name(source_transform),
                                names,
                            )
                        )

                try:
                    self._analysis_checkpoint(
                        "mesh_skin_data_start",
                        index=mesh_index,
                        mesh=source_transform,
                    )
                    skin_data, skin_shape = _capture_skin_data_with_compatible_shape(source_transform, source_shape, skin_cluster)
                    self._analysis_checkpoint(
                        "mesh_skin_data_done",
                        index=mesh_index,
                        mesh=source_transform,
                        vertex_count=int(skin_data.get("vertex_count") or 0),
                        influence_count=len(skin_data.get("influences") or []),
                    )
                except Exception as exc:
                    self._analysis_checkpoint(
                        "mesh_skin_data_error",
                        index=mesh_index,
                        mesh=source_transform,
                        error=str(exc)[:240],
                    )
                    mesh_errors.append(
                        "Could not read skin weights for {0} through {1}: {2}".format(
                            _short_name(source_transform),
                            _short_name(skin_cluster),
                            exc,
                        )
                    )
                    mesh_reports.append(
                        {
                            "source_transform": source_transform,
                            "source_shape": source_shape,
                            "skin_shape": source_shape,
                            "skin_cluster": skin_cluster,
                            "skin_data": {"influences": []},
                            "shading_assignments": [],
                            "uv_summary": {},
                            "color_summary": {},
                            "edge_smoothing": [],
                            "world_normals": [],
                            "topology_signature": {},
                            "world_points": [],
                            "source_visible": _is_transform_visible(source_transform),
                            "unsupported_history": unsupported_history,
                            "animated_unsupported_history": animated_unsupported,
                            "errors": mesh_errors,
                            "warnings": mesh_warnings,
                        }
                    )
                    continue
                if skin_shape != source_shape:
                    mesh_warnings.append(
                        "{0} uses separate visible and skinCluster-owned shapes. Aminate will bake the evaluated visible shape while reading weights from the skin shape.".format(
                            _short_name(source_transform)
                        )
                    )
                    unsupported_history = _dedupe_preserve_order(
                        unsupported_history + _unsupported_history_nodes(skin_shape, skin_cluster)
                    )
                    animated_unsupported = _animated_unsupported_history_nodes(unsupported_history)
                    if animated_unsupported and not any("animated non-skin deformers" in item for item in mesh_errors):
                        animated_names = ", ".join("{0} ({1})".format(_short_name(node_name), node_type) for node_name, node_type in animated_unsupported)
                        mesh_errors.append(
                            "{0} has animated non-skin deformers that cannot be faithfully preserved in an Unreal skeletal FBX; export is blocked: {1}".format(
                                _short_name(source_transform),
                                animated_names,
                            )
                        )
                    elif unsupported_history and not any("extra deformation history" in item for item in mesh_warnings):
                        names = ", ".join("{0} ({1})".format(_short_name(node_name), node_type) for node_name, node_type in unsupported_history)
                        mesh_warnings.append(
                            "{0} has extra deformation history that will be baked into the export mesh: {1}".format(
                                _short_name(source_transform),
                                names,
                            )
                        )
                self._analysis_checkpoint("mesh_topology_start", index=mesh_index, mesh=source_transform)
                geometry_signature = _capture_topology_signature(visible_shape)
                self._analysis_checkpoint(
                    "mesh_topology_done",
                    index=mesh_index,
                    mesh=source_transform,
                    vertex_count=int(geometry_signature.get("vertex_count") or 0),
                    face_count=int(geometry_signature.get("face_count") or 0),
                )
                if int(skin_data.get("vertex_count") or 0) != int(geometry_signature.get("vertex_count") or 0):
                    mesh_errors.append(
                        "{0} has different vertex counts on its visible and skinned shapes ({1} versus {2}); weights cannot be mapped safely.".format(
                            _short_name(source_transform),
                            geometry_signature.get("vertex_count", 0),
                            skin_data.get("vertex_count", 0),
                        )
                    )
                outside_influences = []
                non_joint_influences = []
                for entry in skin_data["influences"]:
                    influence_path = entry.get("path", "")
                    if not cmds.objExists(influence_path):
                        outside_influences.append(influence_path or entry.get("uuid", ""))
                        continue
                    if cmds.nodeType(influence_path) != "joint":
                        non_joint_influences.append(influence_path)
                        continue
                    if influence_path not in joint_set:
                        outside_influences.append(influence_path)
                if non_joint_influences:
                    mesh_errors.append("{0} uses influences that are not joints: {1}".format(_short_name(source_transform), ", ".join(_short_name(item) for item in non_joint_influences[:8])))
                if outside_influences:
                    mesh_errors.append("{0} uses joints outside the chosen skeleton: {1}".format(_short_name(source_transform), ", ".join(_short_name(item) for item in outside_influences[:8])))

                self._analysis_checkpoint("mesh_fidelity_start", index=mesh_index, mesh=source_transform)
                shading_assignments = _capture_shading_assignments(source_transform, visible_shape)
                if len(shading_assignments) > 1:
                    mesh_warnings.append("{0} uses more than one material. The face-based split will be kept.".format(_short_name(source_transform)))
                if ":" in source_transform:
                    mesh_warnings.append("{0} uses extra name tags. The copy will keep checking full paths.".format(_short_name(source_transform)))
                if skin_cleanup._referenced_warning(source_transform):
                    mesh_warnings.append("{0} comes from a reference. The export copy is safe, but the source rig stays untouched.".format(_short_name(source_transform)))
                if _has_locked_normals(visible_shape):
                    mesh_warnings.append("{0} has locked normals. The tool will check them again on the export copy.".format(_short_name(source_transform)))

                mesh_reports.append(
                    {
                        "source_transform": source_transform,
                        "source_shape": visible_shape,
                        "skin_shape": skin_shape,
                        "skin_cluster": skin_cluster,
                        "skin_data": skin_data,
                        "shading_assignments": shading_assignments,
                        "uv_summary": _capture_uv_summary(visible_shape),
                        "color_summary": _capture_color_summary(visible_shape),
                        "edge_smoothing": _capture_edge_smoothing(visible_shape),
                        "world_normals": _capture_world_normals(visible_shape),
                        "topology_signature": geometry_signature,
                        "world_points": _capture_true_world_points(visible_shape),
                        "source_visible": _is_transform_visible(source_transform),
                        "unsupported_history": unsupported_history,
                        "animated_unsupported_history": animated_unsupported,
                        "errors": mesh_errors,
                        "warnings": mesh_warnings,
                    }
                )
                self._analysis_checkpoint(
                    "mesh_fidelity_done",
                    index=mesh_index,
                    mesh=source_transform,
                    edge_count=len(mesh_reports[-1].get("edge_smoothing") or []),
                    normal_count=len(mesh_reports[-1].get("world_normals") or []),
                    point_count=len(mesh_reports[-1].get("world_points") or []),
                )
            for mesh_report in mesh_reports:
                errors.extend(mesh_report["errors"])
                warnings.extend(mesh_report["warnings"])

        scene_unit = _scene_linear_unit()
        visible_measurement_meshes = [
            mesh_report
            for mesh_report in mesh_reports
            if mesh_report.get("source_visible", True)
        ]
        measurement = measure_mesh_reports(
            visible_measurement_meshes,
            axis=self.measurement_axis,
        )
        measurement["all_mesh_count"] = len(mesh_reports)
        measurement["excluded_hidden_mesh_count"] = (
            len(mesh_reports) - len(visible_measurement_meshes)
        )
        measurement["excluded_hidden_meshes"] = [
            mesh_report.get("source_transform") or ""
            for mesh_report in mesh_reports
            if not mesh_report.get("source_visible", True)
        ]
        resolved_factor = self.scale_factor
        if not measurement.get("measurable"):
            errors.append(
                "No measurable skinned mesh height was found on measurement axis {0}; control curves and joints are not used for height math.".format(
                    self.measurement_axis
                )
            )
        else:
            try:
                if self._scale_factor_override:
                    resolved_factor = calculate_scale_factor(
                        SCALE_MODE_FACTOR,
                        self.scale_factor,
                        measurement["height"],
                        unit=UNIT_SCENE,
                        scene_unit=scene_unit,
                        axis=self.measurement_axis,
                    )
                else:
                    resolved_factor = calculate_scale_factor(
                        self.scale_mode,
                        self.scale_value,
                        measurement["height"],
                        unit=self.scale_unit,
                        scene_unit=scene_unit,
                        axis=self.measurement_axis,
                    )
            except (TypeError, ValueError) as exc:
                errors.append(str(exc))
        self._scale_factor = float(resolved_factor)
        measurement["result_height"] = measurement.get("height") * self.scale_factor if measurement.get("measurable") else None
        self._analysis_checkpoint(
            "animation_scan_start",
            mesh_count=len(mesh_reports),
            skeleton_root_count=len(skeleton_roots),
        )
        animation_samples = _animation_sample_times(character_root, skeleton_roots)
        animated_scale = {"time_driven": [], "varying": [], "sample_count": 0}
        if skeleton_roots:
            try:
                animated_scale = _animated_scale_blockers(
                    character_root,
                    skeleton_roots,
                    animation_samples,
                )
            except Exception as exc:
                errors.append("Could not prove that source scale channels are static: {0}".format(exc))
        animated_scale_nodes = _dedupe_preserve_order(animated_scale.get("varying") or [])
        if animated_scale_nodes:
            errors.append(
                "Scale changes over the animation range and is not exported silently. Bake or remove scale animation first: {0}".format(
                    ", ".join(_short_name(node_name) for node_name in animated_scale_nodes[:12])
                )
            )
        elif animated_scale.get("time_driven"):
            warnings.append(
                "Time-driven scale networks were found, but their values stayed constant across {0} verification samples.".format(
                    animated_scale.get("sample_count") or 0
                )
            )
        self._analysis_checkpoint(
            "animation_scan_done",
            sample_count=len(animation_samples),
            time_driven_count=len(animated_scale.get("time_driven") or []),
            varying_count=len(animated_scale.get("varying") or []),
        )

        self.report = {
            "character_root": character_root,
            "controls_root": character_root,
            "skeleton_root": self.skeleton_root,
            "skeleton_roots": skeleton_roots,
            "scale_factor": float(self.scale_factor),
            "scale_percent": self.scale_percent,
            "scale_mode": self.scale_mode,
            "scale_value": self.scale_value,
            "scale_unit": self.scale_unit,
            "measurement_axis": self.measurement_axis,
            "scene_linear_unit": scene_unit,
            "measurement": measurement,
            "animation_samples": animation_samples,
            "animated_scale": animated_scale,
            "copy_suffix": self.copy_suffix or DEFAULT_COPY_SUFFIX,
            "errors": errors,
            "warnings": _dedupe_preserve_order(warnings),
            "meshes": mesh_reports,
            "analysis_trace": list(self.analysis_trace[-64:]),
            "result": None,
            "input_signature": self._input_signature(),
        }
        self.result = None

        if errors:
            return False, "The setup is not safe yet. Read the red notes below. {0}".format(format_measurement(measurement, factor=self.scale_factor if measurement.get("measurable") else None, display_unit=self.scale_unit, scene_unit=scene_unit))
        if warnings:
            return True, "The setup can work, but read the yellow notes first. {0}".format(self._measurement_status())
        return True, "The setup looks ready for a rig copy. {0}".format(self._measurement_status())

    def create_export_copy(self):
        report_signature = tuple((self.report or {}).get("input_signature") or ())
        if not self.report or self.report.get("errors") or report_signature != self._input_signature():
            success, message = self.analyze_setup()
            if not success:
                return False, message

        report = self.report
        animated_blockers = []
        for mesh_report in report.get("meshes") or []:
            animated_blockers.extend(mesh_report.get("animated_unsupported_history") or [])
        if animated_blockers:
            names = ", ".join("{0} ({1})".format(_short_name(node_name), node_type) for node_name, node_type in animated_blockers)
            return False, "Export is blocked because animated non-skin deformers cannot be faithfully preserved in an Unreal skeletal FBX: {0}".format(names)
        skeleton_roots = [root for root in (report.get("skeleton_roots") or [report.get("skeleton_root")]) if root and cmds.objExists(root)]
        if not skeleton_roots:
            return False, "No valid skeleton roots were found. Run Analyze again with a character root that contains skinned joints."
        anchor_node = report.get("character_root") if report.get("character_root") and cmds.objExists(report.get("character_root")) else skeleton_roots[0]
        anchor_point = _world_translation(anchor_node)
        export_group_name = _unique_name(_short_name(anchor_node) + (report["copy_suffix"] or DEFAULT_COPY_SUFFIX))
        selection_before = _selected_nodes()
        self.build_trace = []
        self._build_checkpoint(
            "build_start",
            mesh_count=len(report.get("meshes") or []),
            skeleton_root_count=len(skeleton_roots),
        )
        self._build_checkpoint("source_snapshot_before_start")
        _force_geometry_evaluation()
        source_snapshot_before = _capture_source_snapshot(
            report.get("character_root"),
            skeleton_roots,
            report.get("meshes") or [],
            use_cached_skin_data=True,
        )
        self._build_checkpoint(
            "source_snapshot_before_done",
            node_count=len(source_snapshot_before.get("nodes") or {}),
            mesh_count=len(source_snapshot_before.get("meshes") or {}),
        )
        source_snapshot_after = None
        source_untouched = True
        source_comparison = {"passed": True, "numeric_epsilon": SOURCE_STATE_EPSILON, "differences": []}
        export_group = ""
        duplicate_roots = []
        joint_map = {}
        mesh_results = []
        animation_result = {"baked": False, "sample_count": 0, "start": None, "end": None}
        animation_geometry = {
            "passed": True,
            "supported": False,
            "sample_count": 0,
            "sample_times": [],
            "mesh_checks": 0,
            "point_checks": 0,
            "max_point_delta": 0.0,
            "failures": [],
        }
        copy_independence = {"passed": False, "copy_node_count": 0, "source_node_count": 0, "dependencies": []}
        joints_verified = False
        verified = False

        try:
            export_group = _node_long_name(cmds.group(empty=True, name=export_group_name))
            _set_world_matrix_without_scale(export_group, anchor_node)
            self._build_checkpoint("skeleton_copy_start", root_count=len(skeleton_roots))
            for root_index, skeleton_root in enumerate(skeleton_roots, 1):
                duplicate_root, root_joint_map = _duplicate_scaled_skeleton(
                    skeleton_root,
                    export_group,
                    report["scale_factor"],
                    anchor_point,
                )
                duplicate_roots.append(duplicate_root)
                joint_map.update(root_joint_map)
                self._build_checkpoint(
                    "skeleton_copy_done",
                    index=root_index,
                    total=len(skeleton_roots),
                    root=skeleton_root,
                    joint_count=len(root_joint_map),
                )

            mesh_total = len(report["meshes"])
            for mesh_index, mesh_report in enumerate(report["meshes"], 1):
                self._build_checkpoint(
                    "mesh_duplicate_start",
                    index=mesh_index,
                    total=mesh_total,
                    mesh=mesh_report.get("source_transform", ""),
                )
                duplicate_transform, duplicate_shape, baseline_world_points = _build_scaled_mesh_snapshot(mesh_report, export_group, anchor_point, report["scale_factor"])
                self._build_checkpoint(
                    "mesh_duplicate_done",
                    index=mesh_index,
                    total=mesh_total,
                    mesh=mesh_report.get("source_transform", ""),
                )
                new_skin_cluster = _bind_scaled_mesh(duplicate_transform, duplicate_shape, mesh_report, joint_map)
                self._build_checkpoint(
                    "mesh_bind_done",
                    index=mesh_index,
                    total=mesh_total,
                    mesh=mesh_report.get("source_transform", ""),
                    skin_cluster=new_skin_cluster,
                )
                _apply_shading_assignments(duplicate_transform, duplicate_shape, mesh_report["shading_assignments"])
                verification = _verify_scaled_mesh(
                    mesh_report,
                    duplicate_transform,
                    duplicate_shape,
                    new_skin_cluster,
                    joint_map,
                    anchor_point,
                    report["scale_factor"],
                    baseline_world_points,
                )
                mesh_results.append(
                    {
                        "source_transform": mesh_report["source_transform"],
                        "duplicate_transform": duplicate_transform,
                        "duplicate_shape": duplicate_shape,
                        "skin_cluster": new_skin_cluster,
                        "baseline_world_point_count": len(baseline_world_points),
                        "verification": verification,
                    }
                )
                self._build_checkpoint(
                    "mesh_verify_done",
                    index=mesh_index,
                    total=mesh_total,
                    mesh=mesh_report.get("source_transform", ""),
                    passed=bool(verification.get("passed")),
                )

            self._build_checkpoint(
                "animation_bake_start",
                joint_count=len(joint_map),
                sample_count=len(report.get("animation_samples") or []),
            )
            animation_result = _bake_scaled_skeleton_animation(
                joint_map,
                report.get("animation_samples") or [],
                report["scale_factor"],
                anchor_node,
            )
            self._build_checkpoint("animation_bake_done", **animation_result)
            self._build_checkpoint(
                "animation_geometry_verify_start",
                mesh_count=len(report.get("meshes") or []),
                sample_count=len(report.get("animation_samples") or []),
            )
            animation_geometry = _verify_scaled_animation_geometry(
                report.get("meshes") or [],
                mesh_results,
                joint_map,
                anchor_node,
                report.get("animation_samples") or [],
                report["scale_factor"],
            )
            self._build_checkpoint(
                "animation_geometry_verify_done",
                passed=bool(animation_geometry.get("passed")),
                sample_count=int(animation_geometry.get("sample_count") or 0),
                mesh_checks=int(animation_geometry.get("mesh_checks") or 0),
                point_checks=int(animation_geometry.get("point_checks") or 0),
                joint_checks=int(animation_geometry.get("joint_checks") or 0),
                max_point_delta=float(animation_geometry.get("max_point_delta") or 0.0),
                max_joint_position_delta=float(animation_geometry.get("max_joint_position_delta") or 0.0),
                max_joint_rotation_delta_degrees=float(animation_geometry.get("max_joint_rotation_delta_degrees") or 0.0),
                failure_count=(
                    len(animation_geometry.get("failures") or [])
                    + len(animation_geometry.get("joint_failures") or [])
                ),
                hidden_waiver_count=len(animation_geometry.get("hidden_mesh_waivers") or []),
            )

            joints_verified = True
            for duplicate_joint in joint_map.values():
                scale = _safe_get_vector_attr(duplicate_joint, "scale")
                if any(abs(value - 1.0) > VALUE_EPSILON for value in scale):
                    joints_verified = False
                    break

            if not cmds.attributeQuery(GROUP_SCALE_ATTR, node=export_group, exists=True):
                cmds.addAttr(export_group, longName=GROUP_SCALE_ATTR, attributeType="double")
            cmds.setAttr(export_group + "." + GROUP_SCALE_ATTR, float(report["scale_factor"]))
            if not cmds.attributeQuery(GROUP_SCALE_PERCENT_ATTR, node=export_group, exists=True):
                cmds.addAttr(export_group, longName=GROUP_SCALE_PERCENT_ATTR, attributeType="double")
            cmds.setAttr(export_group + "." + GROUP_SCALE_PERCENT_ATTR, float(report["scale_percent"]))
            if not cmds.attributeQuery(GROUP_NOTE_ATTR, node=export_group, exists=True):
                cmds.addAttr(export_group, longName=GROUP_NOTE_ATTR, dataType="string")
            cmds.setAttr(
                export_group + "." + GROUP_NOTE_ATTR,
                "Built from the selected source rig at {0:.1f}% of its original size. Scaling is never cumulative. Source controls stay untouched. Joints are rebuilt with scale 1,1,1.".format(report["scale_percent"]),
                type="string",
            )

            self._build_checkpoint("copy_independence_start")
            copy_independence = _verify_copy_independence(export_group, source_snapshot_before)
            self._build_checkpoint(
                "copy_independence_done",
                passed=bool(copy_independence.get("passed")),
                copy_node_count=int(copy_independence.get("copy_node_count") or 0),
            )
            verified = (
                joints_verified
                and copy_independence.get("passed")
                and animation_geometry.get("passed")
                and all(item["verification"]["passed"] for item in mesh_results)
            )
        except Exception as exc:
            self._build_checkpoint("build_error", error=str(exc)[:240])
            _warning(traceback.format_exc())
            if export_group and cmds.objExists(export_group):
                try:
                    cmds.delete(export_group)
                except Exception:
                    pass
            try:
                cmds.select(selection_before, replace=True)
            except Exception:
                pass
            return False, "Could not build the export copy: {0}".format(exc)
        finally:
            self._build_checkpoint("build_cleanup_start")
            try:
                cmds.select(selection_before, replace=True)
            except Exception:
                pass
            try:
                if source_snapshot_before.get("current_time") is not None:
                    cmds.currentTime(source_snapshot_before["current_time"], edit=True, update=True)
            except Exception:
                pass
            self._build_checkpoint("build_cleanup_done")

        try:
            self._build_checkpoint("source_snapshot_after_start")
            _force_geometry_evaluation()
            source_snapshot_after = _capture_source_snapshot(
                report.get("character_root"),
                skeleton_roots,
                report.get("meshes") or [],
                baseline=source_snapshot_before,
            )
            self._build_checkpoint(
                "source_snapshot_after_done",
                node_count=len(source_snapshot_after.get("nodes") or {}),
                mesh_count=len(source_snapshot_after.get("meshes") or {}),
            )
            source_comparison = _compare_source_snapshots(source_snapshot_before, source_snapshot_after)
            source_untouched = bool(source_comparison.get("passed"))
            self._build_checkpoint(
                "source_comparison_done",
                passed=bool(source_comparison.get("passed")),
                difference_count=len(source_comparison.get("differences") or []),
            )
        except Exception:
            self._build_checkpoint("source_comparison_error")
            source_untouched = False
            source_comparison = {"passed": False, "numeric_epsilon": SOURCE_STATE_EPSILON, "differences": ["snapshot_error"]}
        compact_source_before = _compact_source_snapshot(source_snapshot_before)
        compact_source_after = _compact_source_snapshot(source_snapshot_after)
        if not source_untouched:
            if export_group and cmds.objExists(export_group):
                try:
                    cmds.delete(export_group)
                except Exception:
                    pass
            self.result = {
                "export_group": export_group,
                "duplicate_roots": duplicate_roots,
                "joint_map": joint_map,
                "mesh_results": mesh_results,
                "animation": animation_result,
                "animation_geometry_verification": animation_geometry,
                "copy_independence": copy_independence,
                "joints_verified": joints_verified,
                "verified": False,
                "source_untouched": False,
                "source_snapshot_comparison": source_comparison,
                "source_snapshot_before": compact_source_before,
                "source_snapshot_after": compact_source_after,
                "build_trace": list(self.build_trace[-64:]),
            }
            self.report["result"] = self.result
            return False, "The source rig changed while building the copy; the partial export copy was removed and no result is trusted."

        self.result = {
            "export_group": export_group,
            "duplicate_root": duplicate_roots[0] if duplicate_roots else "",
            "duplicate_roots": duplicate_roots,
            "joint_map": joint_map,
            "mesh_results": mesh_results,
            "animation": animation_result,
            "animation_geometry_verification": animation_geometry,
            "copy_independence": copy_independence,
            "joints_verified": joints_verified,
            "verified": verified,
            "source_untouched": source_untouched,
            "source_snapshot_comparison": source_comparison,
            "source_snapshot_before": compact_source_before,
            "source_snapshot_after": compact_source_after,
            "build_trace": list(self.build_trace[-64:]),
        }
        self.report["result"] = self.result

        if verified:
            if animation_result.get("baked"):
                return True, "Copy ready with baked animation and scaled shape checks. Export the copied group, not the control rig. {0}".format(self._measurement_status())
            return True, "Copy ready. Export the copied group, not the control rig. {0}".format(self._measurement_status())
        if not copy_independence.get("passed"):
            return False, "The export copy still depends on source rig nodes; no independent result is trusted."
        if not animation_geometry.get("passed"):
            return False, "The export copy changed shape during animation baking; no scaled result is trusted."
        return False, "The export copy was built, but one or more checks failed. The original rig is still untouched."

    def export_copy_for_unreal(self, path, verify=True):
        """Export only the verified duplicate group as a deterministic Unreal FBX."""
        if verify is not True:
            return False, "Unreal FBX verification cannot be disabled."
        normalized_path, path_error = _valid_fbx_path(path)
        if path_error:
            return False, path_error
        if os.path.exists(normalized_path):
            return False, "The Unreal FBX path already exists. Choose a new filename; Aminate will not overwrite or trust a stale file."
        if not self.result or not self.result.get("verified"):
            return False, "Build and verify an export copy before exporting Unreal FBX."
        export_group = self.result.get("export_group") or ""
        if not export_group or not cmds.objExists(export_group):
            return False, "The verified export copy no longer exists. Build it again before exporting."
        copy_independence = _verify_copy_independence(
            export_group,
            (self.result or {}).get("source_snapshot_before") or {},
        )
        if not copy_independence.get("passed"):
            return False, "The export copy has source-rig dependencies. Rebuild it before exporting."
        animated_blockers = []
        for mesh_report in (self.report or {}).get("meshes") or []:
            animated_blockers.extend(mesh_report.get("animated_unsupported_history") or [])
        if animated_blockers:
            names = ", ".join("{0} ({1})".format(_short_name(node_name), node_type) for node_name, node_type in animated_blockers)
            return False, "Unreal FBX export is blocked: animated non-skin deformers cannot be faithfully preserved ({0}).".format(names)

        try:
            plugin_loaded = bool(cmds.pluginInfo(FBX_PLUGIN_NAME, query=True, loaded=True))
        except Exception:
            plugin_loaded = False
        if not plugin_loaded:
            try:
                cmds.loadPlugin(FBX_PLUGIN_NAME, quiet=True)
            except Exception as exc:
                return False, "The fbxmaya plug-in could not be loaded: {0}".format(exc)
            try:
                plugin_loaded = bool(cmds.pluginInfo(FBX_PLUGIN_NAME, query=True, loaded=True))
            except Exception:
                plugin_loaded = False
        if not plugin_loaded:
            return False, "The fbxmaya plug-in is not loaded; no Unreal FBX was written."

        selection_before = _selected_nodes()
        source_before = _capture_source_snapshot((self.report or {}).get("character_root"), (self.report or {}).get("skeleton_roots") or [], (self.report or {}).get("meshes") or [])
        animation = self.result.get("animation") or {}
        commands = _fbx_mel_commands(normalized_path, animation)
        settings_before = _capture_fbx_settings()
        export_started = time.time()
        export_error = ""
        settings_applied = []
        try:
            cmds.select(export_group, replace=True)
            if mel:
                for command in commands[:-1]:
                    mel.eval(command)
                    settings_applied.append(command)
                mel.eval(commands[-1])
                settings_applied.append(commands[-1])
            if not os.path.isfile(normalized_path) or os.path.getsize(normalized_path) <= 0:
                # Maya's cmds.file route is a deterministic fallback for
                # sessions where FBXExport MEL is unavailable or deferred.
                cmds.file(normalized_path, force=True, type="FBX export", exportSelected=True)
        except Exception as exc:
            export_error = str(exc)
        finally:
            _restore_fbx_settings(settings_before)
            try:
                cmds.select(selection_before, replace=True)
            except Exception:
                pass
            try:
                if source_before.get("current_time") is not None:
                    cmds.currentTime(source_before["current_time"], edit=True, update=True)
            except Exception:
                pass

        settings_after = _capture_fbx_settings()
        settings_restored = _fbx_settings_match(settings_before, settings_after)
        file_exists = os.path.isfile(normalized_path)
        file_size = os.path.getsize(normalized_path) if file_exists else 0
        file_mtime = os.path.getmtime(normalized_path) if file_exists else 0.0
        fresh_output = bool(file_exists and file_size > 0 and file_mtime >= (export_started - 2.0))
        file_inspection = _inspect_fbx_file(normalized_path)
        import_verification = {
            "verified": False,
            "imported": False,
            "content_verified": False,
            "skin_verified": False,
            "animation_verified": False,
            "skin_cluster_count": 0,
            "skinned_mesh_count": 0,
            "influence_count": 0,
            "weighted_vertex_count": 0,
            "weight_sum_error_max": None,
            "animation_curve_count": 0,
            "animation_key_count": 0,
            "cleanup_verified": False,
            "error": "",
        }
        if not export_error and fresh_output and file_inspection.get("content_valid"):
            import_verification = _verify_fbx_import_content(
                normalized_path,
                expected_joint_count=len((self.result or {}).get("joint_map") or {}),
                expected_mesh_count=len((self.report or {}).get("meshes") or []),
                expected_animation=bool(animation.get("baked")),
            )
        try:
            source_after = _capture_source_snapshot(
                (self.report or {}).get("character_root"),
                (self.report or {}).get("skeleton_roots") or [],
                (self.report or {}).get("meshes") or [],
                baseline=source_before,
            )
            source_comparison = _compare_source_snapshots(source_before, source_after)
            source_untouched = bool(source_comparison.get("passed"))
        except Exception:
            source_after = None
            source_untouched = False
            source_comparison = {"passed": False, "numeric_epsilon": SOURCE_STATE_EPSILON, "differences": ["snapshot_error"]}
        copy_independence_after = _verify_copy_independence(export_group, source_before)
        compact_source_before = _compact_source_snapshot(source_before)
        compact_source_after = _compact_source_snapshot(source_after)
        verified_export = bool(
            not export_error
            and fresh_output
            and file_inspection.get("content_valid")
            and import_verification.get("verified")
            and settings_restored
            and source_untouched
            and copy_independence_after.get("passed")
        )
        manifest = {
            "path": normalized_path,
            "format": "FBX",
            "plugin": FBX_PLUGIN_NAME,
            "export_group": export_group,
            "selected_export": True,
            "settings": {
                "centimetre_conversion": True,
                "up_axis": "y",
                "skins": True,
                "skeleton": True,
                "baked_animation": bool(animation.get("baked")),
                "animation_start": animation.get("start"),
                "animation_end": animation.get("end"),
                "commands": list(settings_applied),
            },
            "file_exists": file_exists,
            "file_size": file_size,
            "file_mtime": file_mtime,
            "fresh_output": fresh_output,
            "file_inspection": file_inspection,
            "import_verification": import_verification,
            "settings_before": settings_before,
            "settings_after": settings_after,
            "settings_restored": settings_restored,
            "copy_independence": copy_independence_after,
            "source_untouched": source_untouched,
            "source_snapshot_comparison": source_comparison,
            "verified": verified_export,
            "error": export_error,
            "source_snapshot_before": compact_source_before,
            "source_snapshot_after": compact_source_after,
        }
        self.result["unreal_export"] = manifest
        self.report["result"] = self.result
        if not verified_export:
            if export_error:
                return False, "Unreal FBX export failed: {0}".format(export_error)
            if not file_exists or file_size <= 0:
                return False, "Maya reported export, but no non-empty .fbx file exists at {0}.".format(normalized_path)
            if not fresh_output:
                return False, "The FBX file is not provably fresh; it is not trusted."
            if not file_inspection.get("header_valid"):
                return False, "The exported file does not have a valid FBX header; it is not trusted."
            if not file_inspection.get("content_valid"):
                return False, "The FBX file is missing required object/model/geometry content; it is not trusted."
            if not import_verification.get("verified"):
                return False, "The FBX could not be freshly imported with verified joints, skinned weights, influences, and animation; it is not trusted."
            if not settings_restored:
                return False, "Maya's previous FBX export settings were not restored; the export is not trusted."
            if not copy_independence_after.get("passed"):
                return False, "The copied rig gained a source-rig dependency during export; the FBX is not trusted."
            return False, "The source rig changed during Unreal FBX export; the file is not trusted."
        return True, "Unreal FBX freshly exported and re-import verified from the copied group: {0} ({1} bytes).".format(normalized_path, file_size)

    def select_export_copy(self):
        if not self.result or not self.result.get("export_group") or not cmds.objExists(self.result["export_group"]):
            return False, "There is no export copy to select yet."
        cmds.select(self.result["export_group"], replace=True)
        return True, "Selected the export copy group."

    def delete_export_copy(self):
        if not self.result or not self.result.get("export_group"):
            return False, "There is no export copy to delete."
        export_group = self.result["export_group"]
        if cmds.objExists(export_group):
            cmds.delete(export_group)
        self.result = None
        if self.report:
            self.report["result"] = None
        return True, "Deleted the export copy."


class _WindowBase(QtWidgets.QDialog if QtWidgets else object):
    pass


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

        if MQtUtil.mainWindow() is not None:
            _WindowBase = type("MayaRigScaleExportBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
        else:
            _WindowBase = type("MayaRigScaleExportBase", (QtWidgets.QDialog,), {})
    except Exception:
        _WindowBase = type("MayaRigScaleExportBase", (QtWidgets.QDialog,), {})


if QtWidgets:
    class MayaRigScaleExportWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaRigScaleExportWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.set_status_callback(self._set_status)
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Rig Scale")
            self.setMinimumWidth(320)
            self.setMinimumHeight(440)
            self._build_ui()
            self._refresh_report()

        def _build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.setContentsMargins(12, 12, 12, 12)
            main_layout.setSpacing(10)

            description = QtWidgets.QLabel(
                "Create a clean resized copy. The selected control rig stays untouched."
            )
            description.setWordWrap(True)
            main_layout.addWidget(description)

            note = QtWidgets.QLabel(
                "Size always uses the selected rig's original size. 150% always means 1.5x original, never 1.5x the previous copy. Existing animation is baked onto the copied skeleton."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #B8D7FF;")
            main_layout.addWidget(note)

            roots_group = QtWidgets.QGroupBox("Rig Setup")
            form = QtWidgets.QGridLayout(roots_group)
            form.setHorizontalSpacing(6)
            form.setVerticalSpacing(6)
            self.character_line = QtWidgets.QLineEdit()
            self.character_line.setMinimumWidth(0)
            self.character_line.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.character_line.setPlaceholderText("Selected control or rig top group")
            self.skeleton_line = QtWidgets.QLineEdit()
            self.skeleton_line.setMinimumWidth(0)
            self.skeleton_line.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.skeleton_line.setPlaceholderText("Top skeleton joint")
            self.use_character_button = QtWidgets.QPushButton("Use This Control")
            self.use_skeleton_button = QtWidgets.QPushButton("Use This Skeleton Joint")
            for root_button in (self.use_character_button, self.use_skeleton_button):
                root_button.setMinimumWidth(0)
                root_button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.scale_mode_combo = QtWidgets.QComboBox()
            self.scale_mode_combo.addItem("Factor / Percent", SCALE_MODE_FACTOR_PERCENT)
            self.scale_mode_combo.addItem("Target Height", SCALE_MODE_TARGET_HEIGHT)
            self.scale_mode_combo.addItem("Height Change (+/-)", SCALE_MODE_HEIGHT_CHANGE)
            self.scale_unit_combo = QtWidgets.QComboBox()
            self.scale_unit_combo.addItem("Scene Units", UNIT_SCENE)
            self.scale_unit_combo.addItem("mm", UNIT_MM)
            self.scale_unit_combo.addItem("cm", UNIT_CM)
            self.scale_unit_combo.addItem("m", UNIT_M)
            self.axis_combo = QtWidgets.QComboBox()
            for axis_name in MEASUREMENT_AXES:
                self.axis_combo.addItem(axis_name, axis_name)
            self.axis_combo.setCurrentIndex(1)
            for scale_combo in (self.scale_mode_combo, self.scale_unit_combo, self.axis_combo):
                scale_combo.setMinimumWidth(0)
                scale_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self.scale_spin = QtWidgets.QDoubleSpinBox()
            self.scale_spin.setDecimals(1)
            self.scale_spin.setRange(1.0, 10000.0)
            self.scale_spin.setSingleStep(5.0)
            self.scale_spin.setValue(100.0)
            self.scale_spin.setSuffix(" %")
            self.suffix_line = QtWidgets.QLineEdit(DEFAULT_COPY_SUFFIX)

            form.addWidget(QtWidgets.QLabel("Controls Root"), 0, 0, 1, 2)
            form.addWidget(self.character_line, 1, 0, 1, 2)
            form.addWidget(self.use_character_button, 2, 0, 1, 2)
            form.addWidget(QtWidgets.QLabel("Skeleton Root"), 3, 0, 1, 2)
            form.addWidget(self.skeleton_line, 4, 0, 1, 2)
            form.addWidget(self.use_skeleton_button, 5, 0, 1, 2)
            form.addWidget(QtWidgets.QLabel("Scale Mode"), 6, 0)
            form.addWidget(self.scale_mode_combo, 6, 1)
            form.addWidget(QtWidgets.QLabel("Measurement Unit"), 7, 0)
            form.addWidget(self.scale_unit_combo, 7, 1)
            form.addWidget(QtWidgets.QLabel("Measure Axis"), 8, 0)
            form.addWidget(self.axis_combo, 8, 1)
            form.addWidget(QtWidgets.QLabel("Size"), 9, 0)
            form.addWidget(self.scale_spin, 9, 1)
            self.measurement_label = QtWidgets.QLabel("Current height: not measured yet")
            self.measurement_label.setWordWrap(True)
            form.addWidget(self.measurement_label, 10, 0, 1, 2)
            form.setColumnStretch(0, 1)
            form.setColumnStretch(1, 2)
            main_layout.addWidget(roots_group)

            action_row = QtWidgets.QHBoxLayout()
            action_row.setSpacing(8)
            self.analyze_button = QtWidgets.QPushButton("Check Setup")
            self.create_button = QtWidgets.QPushButton("Make Copy")
            self.create_button.setDefault(True)
            self.analyze_button.setMinimumHeight(36)
            self.create_button.setMinimumHeight(36)
            self.select_button = QtWidgets.QPushButton("Select Export Copy")
            self.delete_button = QtWidgets.QPushButton("Delete Export Copy")
            self.export_button = QtWidgets.QPushButton("Export Unreal FBX")
            action_row.addWidget(self.analyze_button, 1)
            action_row.addWidget(self.create_button, 2)
            main_layout.addLayout(action_row)

            self.advanced_toggle = QtWidgets.QToolButton()
            self.advanced_toggle.setText("Advanced / Export Copy")
            self.advanced_toggle.setCheckable(True)
            self.advanced_toggle.setChecked(False)
            self.advanced_toggle.setToolTip("Show copy naming, Unreal FBX export, selection, and cleanup actions.")
            self.advanced_body = QtWidgets.QWidget()
            advanced_layout = QtWidgets.QGridLayout(self.advanced_body)
            advanced_layout.setContentsMargins(0, 0, 0, 0)
            advanced_layout.setHorizontalSpacing(6)
            advanced_layout.setVerticalSpacing(6)
            self.suffix_line.setMinimumWidth(0)
            self.suffix_line.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            for copy_button in (self.select_button, self.delete_button, self.export_button):
                copy_button.setMinimumWidth(0)
                copy_button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            copy_name_label = QtWidgets.QLabel()
            copy_name_label.setText("Copy Name Ending")
            advanced_layout.addWidget(copy_name_label, 0, 0)
            advanced_layout.addWidget(self.suffix_line, 0, 1)
            advanced_layout.addWidget(self.select_button, 1, 0)
            advanced_layout.addWidget(self.delete_button, 1, 1)
            advanced_layout.addWidget(self.export_button, 2, 0, 1, 2)
            advanced_layout.setColumnStretch(0, 1)
            advanced_layout.setColumnStretch(1, 1)
            self.advanced_body.setVisible(False)
            self.advanced_toggle.toggled.connect(self.advanced_body.setVisible)
            main_layout.addWidget(self.advanced_toggle)
            main_layout.addWidget(self.advanced_body)

            self.report_text = QtWidgets.QPlainTextEdit()
            self.report_text.setReadOnly(True)
            self.report_text.setMinimumHeight(140)
            main_layout.addWidget(self.report_text, 1)

            self.status_label = QtWidgets.QLabel("Pick one rig control plus the top skeleton joint, then click Check Setup.")
            self.status_label.setWordWrap(True)
            selectable_flag = _qt_flag("TextInteractionFlag", "TextSelectableByMouse", 0)
            self.status_label.setTextInteractionFlags(selectable_flag)
            main_layout.addWidget(self.status_label)

            footer_layout = QtWidgets.QHBoxLayout()
            self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
            self.brand_label.setWordWrap(True)
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            footer_layout.addWidget(self.brand_label, 1)
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.setToolTip("Open Amir's PayPal donate link. Set AMIR_PAYPAL_DONATE_URL or AMIR_DONATE_URL to customize it.")
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

            self.use_character_button.clicked.connect(self._use_character)
            self.use_skeleton_button.clicked.connect(self._use_skeleton)
            self.analyze_button.clicked.connect(self._analyze)
            self.create_button.clicked.connect(self._create_copy)
            self.select_button.clicked.connect(self._select_copy)
            self.delete_button.clicked.connect(self._delete_copy)
            self.export_button.clicked.connect(self._export_unreal)
            self.scale_spin.valueChanged.connect(self._sync_controller_values)
            self.scale_mode_combo.currentIndexChanged.connect(self._scale_mode_changed)
            self.scale_unit_combo.currentIndexChanged.connect(self._scale_mode_changed)
            self.axis_combo.currentIndexChanged.connect(self._sync_controller_values)
            self.character_line.editingFinished.connect(self._sync_controller_values)
            self.skeleton_line.editingFinished.connect(self._sync_controller_values)
            self.suffix_line.editingFinished.connect(self._sync_controller_values)
            self._update_scale_input_ui()

        def _scale_mode_changed(self, *_args):
            self._update_scale_input_ui()
            self._sync_controller_values()

        def _update_scale_input_ui(self):
            mode = self.scale_mode_combo.currentData() or SCALE_MODE_FACTOR_PERCENT
            unit = self.scale_unit_combo.currentData() or UNIT_SCENE
            if mode in (SCALE_MODE_FACTOR_PERCENT, SCALE_MODE_PERCENT):
                self.scale_spin.setRange(0.001, 10000.0)
                self.scale_spin.setSuffix(" %")
                self.scale_spin.setSingleStep(5.0)
            elif mode == SCALE_MODE_TARGET_HEIGHT:
                self.scale_spin.setRange(0.0, 1000000000.0)
                self.scale_spin.setSuffix(" {0}".format(DISPLAY_UNIT_LABELS.get(unit, unit)))
                self.scale_spin.setSingleStep(1.0)
            else:
                self.scale_spin.setRange(-1000000000.0, 1000000000.0)
                self.scale_spin.setSuffix(" {0}".format(DISPLAY_UNIT_LABELS.get(unit, unit)))
                self.scale_spin.setSingleStep(1.0)

        def _sync_controller_values(self):
            self.controller.controls_root = self.character_line.text().strip()
            self.controller.skeleton_root = self.skeleton_line.text().strip()
            self.controller.set_scale_specification(
                self.scale_mode_combo.currentData() or SCALE_MODE_FACTOR_PERCENT,
                float(self.scale_spin.value()),
                self.scale_unit_combo.currentData() or UNIT_SCENE,
                self.axis_combo.currentData() or MEASUREMENT_AXIS_DEFAULT,
            )
            self.controller.copy_suffix = self.suffix_line.text().strip() or DEFAULT_COPY_SUFFIX

        def _refresh_report(self):
            self.report_text.setPlainText(self.controller.report_text())
            self.measurement_label.setText(self.controller._measurement_status() or "Current height: not measured yet")

        def _set_status(self, message, success):
            self.status_label.setText(message)

        def _use_character(self):
            success, message = self.controller.set_character_from_selection()
            if success:
                self.character_line.setText(self.controller.character_root)
            self._refresh_report()
            self._set_status(message, success)

        def _use_skeleton(self):
            success, message = self.controller.set_skeleton_from_selection()
            if success:
                self.skeleton_line.setText(self.controller.skeleton_root)
            self._refresh_report()
            self._set_status(message, success)

        def _analyze(self):
            self._sync_controller_values()
            success, message = self.controller.analyze_setup()
            self._refresh_report()
            self._set_status(message, success)

        def _create_copy(self):
            self._sync_controller_values()
            success, message = self.controller.create_export_copy()
            self._refresh_report()
            self._set_status(message, success)

        def _select_copy(self):
            success, message = self.controller.select_export_copy()
            self._set_status(message, success)

        def _delete_copy(self):
            success, message = self.controller.delete_export_copy()
            self._refresh_report()
            self._set_status(message, success)

        def _export_unreal(self):
            path, _filter = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Export Unreal FBX",
                "",
                "FBX files (*.fbx)",
            )
            if not path:
                return
            success, message = self.controller.export_copy_for_unreal(path)
            self._refresh_report()
            self._set_status(message, success)

        def _open_follow_url(self, url=None):
            if _open_external_url(url or FOLLOW_AMIR_URL):
                self._set_status("Opened followamir.com.", True)
            else:
                self._set_status("Could not open followamir.com from this Maya session.", False)

        def _open_donate_url(self):
            if not DONATE_URL:
                self._set_status("Donate link is not set. Use AMIR_PAYPAL_DONATE_URL or AMIR_DONATE_URL.", False)
                return
            if _open_external_url(DONATE_URL):
                self._set_status("Opened the donate page.", True)
            else:
                self._set_status("Could not open the donate page from this Maya session.", False)

        def closeEvent(self, event):
            # Maya owns dockable Qt wrappers.  Hide for reuse instead of
            # destroying the wrapper during a native close.
            self.hide()
            event.ignore()


def _close_existing_window():
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.hide()
        except Exception:
            pass


def launch_maya_rig_scale_export(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not MAYA_AVAILABLE:
        raise RuntimeError("maya_rig_scale_export.launch_maya_rig_scale_export() must run inside Autodesk Maya.")
    if not QtWidgets:
        raise RuntimeError("PySide is not available in this Maya session.")
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
            GLOBAL_CONTROLLER = None
    _close_existing_window()
    GLOBAL_CONTROLLER = MayaRigScaleExportController()
    GLOBAL_WINDOW = MayaRigScaleExportWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    try:
        GLOBAL_WINDOW.show(dockable=bool(dock), floating=not bool(dock), area="right")
    except TypeError:
        GLOBAL_WINDOW.show()
    GLOBAL_WINDOW.raise_()
    GLOBAL_WINDOW.activateWindow()
    return GLOBAL_WINDOW


__all__ = [
    "launch_maya_rig_scale_export",
    "MayaRigScaleExportController",
]
