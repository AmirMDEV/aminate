"""
maya_contact_hold.py

Keep picked hand or foot controls locked to the same world-space spot across
an animation frame range.
"""

from __future__ import absolute_import, division, print_function

import math
import os
import re
import traceback
import uuid

import maya_skinning_cleanup as skin_cleanup

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    import maya.OpenMayaUI as omui

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    omui = None
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


WINDOW_OBJECT_NAME = "mayaContactHoldWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
VALUE_EPSILON = 1.0e-5
DEFAULT_CONTACT_MIN_FRAMES = 3
CONTACT_HOLD_GROUP_NAME = "amirContactHold_GRP"
CONTACT_HOLD_MARKER_ATTR = "amirContactHoldMarker"
CONTACT_HOLD_HUB_MARKER_ATTR = "amirContactHoldHubMarker"
CONTACT_HOLD_ID_ATTR = "amirContactHoldId"
CONTACT_HOLD_LABEL_ATTR = "amirContactHoldLabel"
CONTACT_HOLD_FRIENDLY_NAME_ATTR = "amirContactHoldFriendlyName"
CONTACT_HOLD_AXES_ATTR = "amirContactHoldAxes"
CONTACT_HOLD_START_ATTR = "amirContactHoldStartFrame"
CONTACT_HOLD_END_ATTR = "amirContactHoldEndFrame"
CONTACT_HOLD_KEEP_ROTATION_ATTR = "amirContactHoldKeepRotation"
CONTACT_HOLD_ENABLED_ATTR = "amirContactHoldEnabled"
CONTACT_HOLD_CONTROL_ATTR = "heldControl"
CONTACT_HOLD_HUB_ATTR = "holdHub"
CONTACT_HOLD_SOURCE_LOCATOR_ATTR = "holdSourceLocator"
CONTACT_HOLD_MANAGED_NODES_ATTR = "managedNodes"
CONTACT_HOLD_WORLD_SOURCE_DECOMP_ATTR = "holdWorldSourceDecompose"
CONTACT_HOLD_WORLD_ANCHOR_DECOMP_ATTR = "holdWorldAnchorDecompose"
CONTACT_HOLD_WORLD_BLEND_ATTR = "holdWorldBlend"
CONTACT_HOLD_LOCAL_POINT_ATTR = "holdLocalPointSolver"
CONTACT_HOLD_ROTATE_SOURCE_DECOMP_ATTR = "holdRotateSourceDecompose"
CONTACT_HOLD_ROTATE_ANCHOR_MM_ATTR = "holdRotateAnchorLocalMatrix"
CONTACT_HOLD_ROTATE_ANCHOR_DECOMP_ATTR = "holdRotateAnchorLocalDecompose"
CONTACT_HOLD_ROTATE_BLEND_ATTR = "holdRotateBlend"
DEFAULT_HOLD_AXES = ("z",)

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None

_qt_flag = skin_cleanup._qt_flag
_style_donate_button = skin_cleanup._style_donate_button
_open_external_url = skin_cleanup._open_external_url
_maya_main_window = skin_cleanup._maya_main_window
_dedupe_preserve_order = skin_cleanup._dedupe_preserve_order
_short_name = skin_cleanup._short_name
_node_long_name = skin_cleanup._node_long_name


def _debug(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayInfo("[Maya Contact Hold] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayWarning("[Maya Contact Hold] {0}".format(message))


def _selected_controls():
    transforms = cmds.ls(selection=True, long=True, type="transform") or []
    joints = cmds.ls(selection=True, long=True, type="joint") or []
    return _dedupe_preserve_order(transforms + joints)


def _current_frame():
    return int(round(float(cmds.currentTime(query=True))))


def _stabilize_contact_hold_evaluation():
    if not MAYA_AVAILABLE:
        return
    try:
        cmds.evaluationManager(mode="serial")
    except Exception:
        pass
    try:
        cmds.evaluator(name="gpuOverride", enable=False)
    except Exception:
        pass


def _leaf_name(node_name):
    return node_name.rsplit("|", 1)[-1]


def _split_namespace(node_name):
    leaf_name = _leaf_name(node_name)
    if ":" in leaf_name:
        namespace, local_name = leaf_name.rsplit(":", 1)
        return namespace + ":", local_name
    return "", leaf_name


def _swap_side_names(local_name):
    swaps = []
    boundary = r"(^|[_.\-])"
    tail = r"(?=$|[_.\-])"
    pattern_pairs = [
        (boundary + r"left" + tail, r"\1right"),
        (boundary + r"right" + tail, r"\1left"),
        (boundary + r"Left" + tail, r"\1Right"),
        (boundary + r"Right" + tail, r"\1Left"),
        (boundary + r"LEFT" + tail, r"\1RIGHT"),
        (boundary + r"RIGHT" + tail, r"\1LEFT"),
        (boundary + r"lft" + tail, r"\1rgt"),
        (boundary + r"rgt" + tail, r"\1lft"),
        (boundary + r"lf" + tail, r"\1rt"),
        (boundary + r"rt" + tail, r"\1lf"),
        (boundary + r"l" + tail, r"\1r"),
        (boundary + r"r" + tail, r"\1l"),
        (boundary + r"L" + tail, r"\1R"),
        (boundary + r"R" + tail, r"\1L"),
    ]
    for pattern, replacement in pattern_pairs:
        swapped_name, count = re.subn(pattern, replacement, local_name, count=1)
        if count and swapped_name != local_name:
            swaps.append(swapped_name)

    edge_pairs = [
        ("left", "right"),
        ("right", "left"),
        ("Left", "Right"),
        ("Right", "Left"),
        ("LEFT", "RIGHT"),
        ("RIGHT", "LEFT"),
        ("lft", "rgt"),
        ("rgt", "lft"),
        ("lf", "rt"),
        ("rt", "lf"),
    ]
    for source, replacement in edge_pairs:
        if local_name.startswith(source):
            swaps.append(replacement + local_name[len(source):])
        if local_name.endswith(source):
            swaps.append(local_name[:-len(source)] + replacement)

    return _dedupe_preserve_order(swaps)


def _scene_controls():
    transforms = cmds.ls(long=True, type="transform") or []
    joints = cmds.ls(long=True, type="joint") or []
    return _dedupe_preserve_order(transforms + joints)


def _find_other_side_control(node_name, taken_nodes=None):
    taken_lookup = set(_node_long_name(item) for item in (taken_nodes or []))
    current_name = _node_long_name(node_name)
    taken_lookup.add(current_name)

    namespace, local_name = _split_namespace(node_name)
    candidate_leaves = [namespace + item for item in _swap_side_names(local_name)]
    if not candidate_leaves:
        return None, "{0} does not look like a left or right control name yet.".format(_short_name(node_name))

    all_controls = _scene_controls()
    for candidate_leaf in candidate_leaves:
        matches = []
        for candidate_node in all_controls:
            candidate_long = _node_long_name(candidate_node)
            if candidate_long in taken_lookup:
                continue
            if _leaf_name(candidate_node) == candidate_leaf:
                matches.append(candidate_long)
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, "Found more than one match for {0}. Pick the other side by hand for this one.".format(_short_name(node_name))

    return None, "Could not find the matching other-side control for {0}.".format(_short_name(node_name))


def _world_matrix(node_name):
    return cmds.xform(node_name, query=True, worldSpace=True, matrix=True)


def _world_translation(node_name):
    return cmds.xform(node_name, query=True, worldSpace=True, translation=True) or [0.0, 0.0, 0.0]


def _world_rotation(node_name):
    return cmds.xform(node_name, query=True, worldSpace=True, rotation=True) or [0.0, 0.0, 0.0]


def _playback_frame_range():
    start_frame = int(round(float(cmds.playbackOptions(query=True, minTime=True))))
    end_frame = int(round(float(cmds.playbackOptions(query=True, maxTime=True))))
    if end_frame < start_frame:
        start_frame, end_frame = end_frame, start_frame
    return start_frame, end_frame


def _distance(a_values, b_values):
    return math.sqrt(sum((float(a_values[index]) - float(b_values[index])) ** 2 for index in range(min(len(a_values), len(b_values)))))


def _wrapped_angle_delta(value_a, value_b):
    delta = (float(value_b) - float(value_a) + 180.0) % 360.0 - 180.0
    return abs(delta)


def _max_rotation_delta(rotation_a, rotation_b):
    return max(_wrapped_angle_delta(rotation_a[index], rotation_b[index]) for index in range(min(len(rotation_a), len(rotation_b))))


def _percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, float(fraction))) * float(len(ordered) - 1)
    low_index = int(math.floor(position))
    high_index = int(math.ceil(position))
    if low_index == high_index:
        return ordered[low_index]
    blend = position - float(low_index)
    return ordered[low_index] * (1.0 - blend) + ordered[high_index] * blend


def _sample_contact_metrics(control_nodes, start_frame, end_frame, keep_rotation):
    if end_frame <= start_frame:
        return []
    current_time = float(cmds.currentTime(query=True))
    try:
        previous_data = None
        metrics = []
        for frame_value in range(start_frame, end_frame + 1):
            cmds.currentTime(frame_value, edit=True)
            frame_data = {}
            for node_name in control_nodes:
                frame_data[node_name] = {
                    "translation": [float(value) for value in _world_translation(node_name)],
                }
                if keep_rotation:
                    frame_data[node_name]["rotation"] = [float(value) for value in _world_rotation(node_name)]
            if previous_data is not None:
                max_distance = 0.0
                max_height = 0.0
                max_rotation = 0.0
                for node_name in control_nodes:
                    previous_pose = previous_data[node_name]
                    current_pose = frame_data[node_name]
                    max_distance = max(max_distance, _distance(previous_pose["translation"], current_pose["translation"]))
                    max_height = max(max_height, abs(float(previous_pose["translation"][1]) - float(current_pose["translation"][1])))
                    if keep_rotation:
                        max_rotation = max(max_rotation, _max_rotation_delta(previous_pose["rotation"], current_pose["rotation"]))
                metrics.append(
                    {
                        "prev_frame": int(frame_value - 1),
                        "frame": int(frame_value),
                        "distance": float(max_distance),
                        "height": float(max_height),
                        "rotation": float(max_rotation),
                    }
                )
            previous_data = frame_data
    finally:
        cmds.currentTime(current_time, edit=True)
    return metrics


def _suggest_contact_run(control_nodes, current_frame, keep_rotation):
    playback_start, playback_end = _playback_frame_range()
    metrics = _sample_contact_metrics(control_nodes, playback_start, playback_end, keep_rotation)
    if not metrics:
        return None

    distances = [item["distance"] for item in metrics]
    heights = [item["height"] for item in metrics]
    rotations = [item["rotation"] for item in metrics] if keep_rotation else []
    move_threshold = max(0.05, _percentile(distances, 0.25) * 2.5)
    height_threshold = max(0.02, _percentile(heights, 0.25) * 2.5)
    rotation_threshold = max(4.0, _percentile(rotations, 0.25) * 2.5) if keep_rotation else None

    runs = []
    index = 0
    while index < len(metrics):
        item = metrics[index]
        calm = item["distance"] <= move_threshold and item["height"] <= height_threshold
        if calm and keep_rotation:
            calm = item["rotation"] <= rotation_threshold
        if not calm:
            index += 1
            continue
        run_start = item["prev_frame"]
        run_end = item["frame"]
        total_distance = item["distance"]
        total_height = item["height"]
        total_rotation = item["rotation"]
        sample_count = 1
        index += 1
        while index < len(metrics):
            next_item = metrics[index]
            next_calm = next_item["distance"] <= move_threshold and next_item["height"] <= height_threshold
            if next_calm and keep_rotation:
                next_calm = next_item["rotation"] <= rotation_threshold
            if not next_calm:
                break
            run_end = next_item["frame"]
            total_distance += next_item["distance"]
            total_height += next_item["height"]
            total_rotation += next_item["rotation"]
            sample_count += 1
            index += 1
        if int(run_end - run_start + 1) >= DEFAULT_CONTACT_MIN_FRAMES:
            runs.append(
                {
                    "start_frame": int(run_start),
                    "end_frame": int(run_end),
                    "avg_distance": total_distance / float(sample_count),
                    "avg_height": total_height / float(sample_count),
                    "avg_rotation": total_rotation / float(sample_count) if keep_rotation else 0.0,
                    "move_threshold": move_threshold,
                    "height_threshold": height_threshold,
                    "rotation_threshold": rotation_threshold,
                }
            )
        index += 1

    if not runs:
        return None

    inside_runs = [item for item in runs if item["start_frame"] <= int(current_frame) <= item["end_frame"]]
    if inside_runs:
        return sorted(inside_runs, key=lambda item: (item["avg_distance"], item["avg_height"], -(item["end_frame"] - item["start_frame"])))[0]

    return sorted(
        runs,
        key=lambda item: (
            min(abs(int(current_frame) - item["start_frame"]), abs(int(current_frame) - item["end_frame"])),
            item["avg_distance"],
            item["avg_height"],
            -(item["end_frame"] - item["start_frame"]),
        ),
    )[0]


def _attr_unlocked(node_name, attribute):
    plug = "{0}.{1}".format(node_name, attribute)
    if not cmds.objExists(plug):
        return False
    try:
        return not bool(cmds.getAttr(plug, lock=True))
    except Exception:
        return False


def _set_string_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), value or "", type="string")


def _set_bool_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="bool")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), bool(value))


def _set_long_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="long")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), int(value))


def _set_double_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="double")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), float(value))


def _get_string_attr(node_name, attr_name, default=""):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return default
    value = cmds.getAttr("{0}.{1}".format(node_name, attr_name))
    return value if value is not None else default


def _get_bool_attr(node_name, attr_name, default=False):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return bool(default)
    return bool(cmds.getAttr("{0}.{1}".format(node_name, attr_name)))


def _get_long_attr(node_name, attr_name, default=0):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return int(default)
    return int(round(float(cmds.getAttr("{0}.{1}".format(node_name, attr_name)))))


def _get_double_attr(node_name, attr_name, default=0.0):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return float(default)
    return float(cmds.getAttr("{0}.{1}".format(node_name, attr_name)))


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


def _normalized_hold_axes(hold_axes):
    result = []
    for axis_name in hold_axes or []:
        axis = str(axis_name).strip().lower()
        if axis in ("x", "y", "z") and axis not in result:
            result.append(axis)
    return tuple(result)


def _hold_axis_label(hold_axes):
    axes = _normalized_hold_axes(hold_axes)
    if not axes:
        return "None"
    return ", ".join(axis.upper() for axis in axes)


def _channel_source_attr_name(attribute):
    return "orig{0}Source".format(attribute[0].upper() + attribute[1:])


def _channel_value_attr_name(attribute):
    return "orig{0}Value".format(attribute[0].upper() + attribute[1:])


def _has_original_channel_state(locator_node, attribute):
    source_attr = _channel_source_attr_name(attribute)
    value_attr = _channel_value_attr_name(attribute)
    return cmds.attributeQuery(source_attr, node=locator_node, exists=True) or cmds.attributeQuery(value_attr, node=locator_node, exists=True)


def _disconnect_destination(plug_name):
    incoming = cmds.listConnections(plug_name, source=True, destination=False, plugs=True) or []
    for source_plug in incoming:
        try:
            cmds.disconnectAttr(source_plug, plug_name)
        except Exception:
            pass


def _ensure_connected(source_plug, destination_plug):
    existing = cmds.listConnections(destination_plug, source=True, destination=False, plugs=True) or []
    if len(existing) == 1 and existing[0] == source_plug:
        return
    _disconnect_destination(destination_plug)
    cmds.connectAttr(source_plug, destination_plug, force=True)


def _solver_node_name(control_node, suffix):
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", _short_name(control_node))
    return "amirContactHold_{0}_{1}".format(safe_name, suffix)


def _source_locator_name(control_node):
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", _short_name(control_node))
    return "amirContactHold_{0}_SRC".format(safe_name)


def _ensure_utility_node(node_type, name):
    if cmds.objExists(name):
        return name
    return cmds.createNode(node_type, name=name)


def _channels_for_hold(node_name, hold_axes, keep_rotation):
    attributes = []
    axes = _normalized_hold_axes(hold_axes)
    for axis_name in axes:
        attribute = "translate{0}".format(axis_name.upper())
        if _attr_unlocked(node_name, attribute):
            attributes.append(attribute)
    if keep_rotation:
        for attribute in ("rotateX", "rotateY", "rotateZ"):
            if _attr_unlocked(node_name, attribute):
                attributes.append(attribute)
    return attributes


def _contact_hold_group(create=True):
    group_name = "|" + CONTACT_HOLD_GROUP_NAME
    if cmds.objExists(group_name):
        return _node_long_name(group_name)
    if not create:
        return ""
    group_name = cmds.createNode("transform", name=CONTACT_HOLD_GROUP_NAME)
    cmds.setAttr(group_name + ".visibility", 0)
    return _node_long_name(group_name)


def _hold_locator_name(control_node):
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", _short_name(control_node))
    return "amirContactHold_{0}_LOC".format(safe_name)


def _all_hold_locators():
    root_group = _contact_hold_group(create=False)
    if not root_group:
        return []
    children = cmds.listRelatives(root_group, children=True, type="transform", fullPath=True) or []
    return [item for item in children if _get_bool_attr(item, CONTACT_HOLD_MARKER_ATTR, False)]


def _find_hold_locator(control_node):
    control_long = _node_long_name(control_node)
    for locator_node in _all_hold_locators():
        held_control = _connected_source_node(locator_node, CONTACT_HOLD_CONTROL_ATTR)
        if held_control == control_long:
            return locator_node
    return ""


def _ensure_hold_locator(control_node):
    existing = _find_hold_locator(control_node)
    if existing and cmds.objExists(existing):
        return existing
    root_group = _contact_hold_group(create=True)
    locator_node = cmds.spaceLocator(name=_hold_locator_name(control_node))[0]
    locator_node = cmds.parent(locator_node, root_group)[0]
    locator_node = _node_long_name(locator_node)
    _set_bool_attr(locator_node, CONTACT_HOLD_MARKER_ATTR, True)
    _set_bool_attr(locator_node, CONTACT_HOLD_ENABLED_ATTR, True)
    _ensure_message_attr(locator_node, CONTACT_HOLD_CONTROL_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_WORLD_SOURCE_DECOMP_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_WORLD_ANCHOR_DECOMP_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_WORLD_BLEND_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_LOCAL_POINT_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_ROTATE_SOURCE_DECOMP_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_ROTATE_ANCHOR_MM_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_ROTATE_ANCHOR_DECOMP_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_ROTATE_BLEND_ATTR)
    _connect_message(control_node, locator_node, CONTACT_HOLD_CONTROL_ATTR)
    locator_shape = (cmds.listRelatives(locator_node, shapes=True, fullPath=True) or [None])[0]
    if locator_shape:
        for attr_name in ("localScaleX", "localScaleY", "localScaleZ"):
            try:
                cmds.setAttr(locator_shape + "." + attr_name, 0.35)
            except Exception:
                pass
    return locator_node


def _ensure_source_locator(control_node, locator_node):
    existing = _connected_source_node(locator_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
    if existing and cmds.objExists(existing):
        return existing
    parent_node = (cmds.listRelatives(control_node, parent=True, fullPath=True) or [None])[0]
    source_locator = cmds.spaceLocator(name=_source_locator_name(control_node))[0]
    if parent_node:
        source_locator = cmds.parent(source_locator, parent_node)[0]
    source_locator = _node_long_name(source_locator)
    cmds.setAttr(source_locator + ".visibility", 0)
    source_shape = (cmds.listRelatives(source_locator, shapes=True, fullPath=True) or [None])[0]
    if source_shape:
        for attr_name in ("localScaleX", "localScaleY", "localScaleZ"):
            try:
                cmds.setAttr(source_shape + "." + attr_name, 0.2)
            except Exception:
                pass
    _connect_message(source_locator, locator_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
    return source_locator


def _capture_original_channel_state(locator_node, control_node, attribute):
    source_attr = _channel_source_attr_name(attribute)
    value_attr = _channel_value_attr_name(attribute)
    if cmds.attributeQuery(source_attr, node=locator_node, exists=True):
        return
    control_plug = "{0}.{1}".format(control_node, attribute)
    incoming = cmds.listConnections(control_plug, source=True, destination=False, plugs=True) or []
    _set_string_attr(locator_node, source_attr, incoming[0] if incoming else "")
    _set_double_attr(locator_node, value_attr, cmds.getAttr(control_plug))


def _ensure_source_channel(control_node, source_locator, locator_node, attribute):
    _capture_original_channel_state(locator_node, control_node, attribute)
    source_attr = _channel_source_attr_name(attribute)
    value_attr = _channel_value_attr_name(attribute)
    source_plug = _get_string_attr(locator_node, source_attr, "")
    target_plug = "{0}.{1}".format(source_locator, attribute)
    _disconnect_destination(target_plug)
    if source_plug:
        try:
            _ensure_connected(source_plug, target_plug)
            return
        except Exception:
            pass
    cmds.setAttr(target_plug, _get_double_attr(locator_node, value_attr, cmds.getAttr("{0}.{1}".format(control_node, attribute))))


def _restore_original_channel(control_node, locator_node, attribute):
    if not _has_original_channel_state(locator_node, attribute):
        return
    control_plug = "{0}.{1}".format(control_node, attribute)
    _disconnect_destination(control_plug)
    source_attr = _channel_source_attr_name(attribute)
    value_attr = _channel_value_attr_name(attribute)
    source_plug = _get_string_attr(locator_node, source_attr, "")
    if source_plug:
        try:
            cmds.connectAttr(source_plug, control_plug, force=True)
            return
        except Exception:
            pass
    try:
        cmds.setAttr(control_plug, _get_double_attr(locator_node, value_attr, cmds.getAttr(control_plug)))
    except Exception:
        pass


def _delete_hold_nodes(locator_node, attr_names):
    for attr_name in attr_names:
        node_name = _connected_source_node(locator_node, attr_name)
        if node_name and cmds.objExists(node_name):
            try:
                cmds.delete(node_name)
            except Exception:
                pass


def _snap_hold_locator(locator_node, control_node, _keep_rotation):
    cmds.xform(locator_node, worldSpace=True, matrix=list(_world_matrix(control_node)))


def _ensure_translation_hold_network(locator_node, control_node, hold_axes):
    source_locator = _ensure_source_locator(control_node, locator_node)
    for attribute in ("translateX", "translateY", "translateZ"):
        _ensure_source_channel(control_node, source_locator, locator_node, attribute)

    source_decomp = _ensure_utility_node("decomposeMatrix", _solver_node_name(control_node, "worldSource_dcmp"))
    anchor_decomp = _ensure_utility_node("decomposeMatrix", _solver_node_name(control_node, "worldAnchor_dcmp"))
    world_blend = _ensure_utility_node("blendColors", _solver_node_name(control_node, "worldBlend"))
    point_solver = _ensure_utility_node("vectorProduct", _solver_node_name(control_node, "localPoint_vp"))
    _connect_message(source_decomp, locator_node, CONTACT_HOLD_WORLD_SOURCE_DECOMP_ATTR)
    _connect_message(anchor_decomp, locator_node, CONTACT_HOLD_WORLD_ANCHOR_DECOMP_ATTR)
    _connect_message(world_blend, locator_node, CONTACT_HOLD_WORLD_BLEND_ATTR)
    _connect_message(point_solver, locator_node, CONTACT_HOLD_LOCAL_POINT_ATTR)

    _ensure_connected(source_locator + ".worldMatrix[0]", source_decomp + ".inputMatrix")
    _ensure_connected(locator_node + ".worldMatrix[0]", anchor_decomp + ".inputMatrix")
    cmds.setAttr(point_solver + ".operation", 4)
    _ensure_connected(control_node + ".parentInverseMatrix[0]", point_solver + ".matrix")
    _ensure_connected(locator_node + "." + CONTACT_HOLD_ENABLED_ATTR, world_blend + ".blender")

    axis_map = (("x", "X", "R"), ("y", "Y", "G"), ("z", "Z", "B"))
    held_axes = set(_normalized_hold_axes(hold_axes))
    for axis_name, axis_suffix, color_suffix in axis_map:
        source_node = anchor_decomp if axis_name in held_axes else source_decomp
        _ensure_connected(source_node + ".outputTranslate" + axis_suffix, world_blend + ".color1" + color_suffix)
        _ensure_connected(source_decomp + ".outputTranslate" + axis_suffix, world_blend + ".color2" + color_suffix)
        _ensure_connected(world_blend + ".output" + color_suffix, point_solver + ".input1" + axis_suffix)
        _ensure_connected(point_solver + ".output" + axis_suffix, control_node + ".translate" + axis_suffix)

    return source_locator


def _clear_rotation_hold_network(locator_node, control_node):
    for attribute in ("rotateX", "rotateY", "rotateZ"):
        if _has_original_channel_state(locator_node, attribute):
            _restore_original_channel(control_node, locator_node, attribute)
    _delete_hold_nodes(
        locator_node,
        (
            CONTACT_HOLD_ROTATE_SOURCE_DECOMP_ATTR,
            CONTACT_HOLD_ROTATE_ANCHOR_MM_ATTR,
            CONTACT_HOLD_ROTATE_ANCHOR_DECOMP_ATTR,
            CONTACT_HOLD_ROTATE_BLEND_ATTR,
        ),
    )


def _ensure_rotation_hold_network(locator_node, control_node):
    source_locator = _ensure_source_locator(control_node, locator_node)
    for attribute in ("rotateX", "rotateY", "rotateZ"):
        _ensure_source_channel(control_node, source_locator, locator_node, attribute)

    anchor_local_mm = _ensure_utility_node("multMatrix", _solver_node_name(control_node, "rotateAnchorLocal_mm"))
    anchor_local_decomp = _ensure_utility_node("decomposeMatrix", _solver_node_name(control_node, "rotateAnchorLocal_dcmp"))
    rotate_blend = _ensure_utility_node("blendColors", _solver_node_name(control_node, "rotateBlend"))
    _connect_message(anchor_local_mm, locator_node, CONTACT_HOLD_ROTATE_ANCHOR_MM_ATTR)
    _connect_message(anchor_local_decomp, locator_node, CONTACT_HOLD_ROTATE_ANCHOR_DECOMP_ATTR)
    _connect_message(rotate_blend, locator_node, CONTACT_HOLD_ROTATE_BLEND_ATTR)

    _ensure_connected(locator_node + ".worldMatrix[0]", anchor_local_mm + ".matrixIn[0]")
    _ensure_connected(control_node + ".parentInverseMatrix[0]", anchor_local_mm + ".matrixIn[1]")
    _ensure_connected(anchor_local_mm + ".matrixSum", anchor_local_decomp + ".inputMatrix")
    _ensure_connected(locator_node + "." + CONTACT_HOLD_ENABLED_ATTR, rotate_blend + ".blender")

    axis_map = (("X", "R"), ("Y", "G"), ("Z", "B"))
    for axis_suffix, color_suffix in axis_map:
        _ensure_connected(anchor_local_decomp + ".outputRotate" + axis_suffix, rotate_blend + ".color1" + color_suffix)
        _ensure_connected(source_locator + ".rotate" + axis_suffix, rotate_blend + ".color2" + color_suffix)
        _ensure_connected(rotate_blend + ".output" + color_suffix, control_node + ".rotate" + axis_suffix)


def _set_step_key(attr_path, frame_value, key_value):
    cmds.setKeyframe(attr_path, time=(float(frame_value), float(frame_value)), value=float(key_value))


def _hold_enabled_attr(locator_node):
    return "{0}.{1}".format(locator_node, CONTACT_HOLD_ENABLED_ATTR)


def _set_hold_enabled(locator_node, enabled, start_frame=None, end_frame=None):
    start = int(start_frame if start_frame is not None else _get_long_attr(locator_node, CONTACT_HOLD_START_ATTR, 1))
    end = int(end_frame if end_frame is not None else _get_long_attr(locator_node, CONTACT_HOLD_END_ATTR, start))
    if end < start:
        start, end = end, start
    enabled_attr = _hold_enabled_attr(locator_node)
    weight_keys = [
        (start - 1, 0.0),
        (start, 1.0 if enabled else 0.0),
        (end, 1.0 if enabled else 0.0),
        (end + 1, 0.0),
    ]
    keyed_frames = set()
    for frame_value, key_value in weight_keys:
        frame_key = float(frame_value)
        if frame_key in keyed_frames:
            continue
        _set_step_key(enabled_attr, frame_value, key_value)
        keyed_frames.add(frame_key)
    _set_bool_attr(locator_node, CONTACT_HOLD_ENABLED_ATTR, enabled)
    return True, "Hold turned {0}.".format("on" if enabled else "off")


def _hold_payload(locator_node):
    if not locator_node or not cmds.objExists(locator_node):
        return None
    control_node = _connected_source_node(locator_node, CONTACT_HOLD_CONTROL_ATTR)
    source_locator = _connected_source_node(locator_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
    return {
        "locator": locator_node,
        "control": control_node,
        "source_locator": source_locator,
        "enabled_attr": _hold_enabled_attr(locator_node),
        "start_frame": _get_long_attr(locator_node, CONTACT_HOLD_START_ATTR, 1),
        "end_frame": _get_long_attr(locator_node, CONTACT_HOLD_END_ATTR, 1),
        "axes": _normalized_hold_axes(_get_string_attr(locator_node, CONTACT_HOLD_AXES_ATTR, "").split(",")),
        "keep_rotation": _get_bool_attr(locator_node, CONTACT_HOLD_KEEP_ROTATION_ATTR, False),
        "enabled": _get_bool_attr(locator_node, CONTACT_HOLD_ENABLED_ATTR, True),
    }


def _capture_pose(node_name, keep_rotation):
    data = {
        "translation": [float(value) for value in _world_translation(node_name)],
    }
    if keep_rotation:
        data["matrix"] = [float(value) for value in _world_matrix(node_name)]
    return data


def _apply_pose(node_name, pose, keep_rotation):
    if keep_rotation and pose.get("matrix"):
        cmds.xform(node_name, worldSpace=True, matrix=list(pose["matrix"]))
        return
    cmds.xform(node_name, worldSpace=True, translation=list(pose["translation"]))


def _format_report(report):
    if not report:
        return "Pick the hand or foot control, choose the contact frame range, choose the world axis to hold, then click Check Setup."

    lines = [
        "Controls: {0}".format(len(report.get("controls", []))),
        "Start Frame: {0}".format(int(report.get("start_frame", 0))),
        "End Frame: {0}".format(int(report.get("end_frame", 0))),
        "Held World Axes: {0}".format(_hold_axis_label(report.get("axes", ()))),
        "Keep Turn Too: {0}".format("Yes" if report.get("keep_rotation", True) else "No"),
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
        lines.append("- This hold looks ready to create as a live editable setup.")
        lines.append("")

    if report.get("controls"):
        lines.append("Picked Controls")
        for node_name in report["controls"]:
            lines.append("- " + _short_name(node_name))

    existing_setups = report.get("existing_setups", [])
    if existing_setups:
        lines.append("")
        lines.append("Existing Live Holds")
        for item in existing_setups:
            lines.append(
                "- {0}: {1}-{2}, axes {3}, {4}".format(
                    _short_name(item["control"]),
                    int(item["start_frame"]),
                    int(item["end_frame"]),
                    _hold_axis_label(item.get("axes", ())),
                    "on" if item.get("enabled") else "off",
                )
            )

    suggestion = report.get("suggestion")
    if suggestion:
        lines.append("")
        lines.append("Suggested Plant Range")
        lines.append("- Frames: {0} to {1}".format(int(suggestion["start_frame"]), int(suggestion["end_frame"])))
        lines.append("- Calm move limit used: {0:.3f}".format(float(suggestion["move_threshold"])))
        lines.append("- Calm height limit used: {0:.3f}".format(float(suggestion["height_threshold"])))
        if report.get("keep_rotation") and suggestion.get("rotation_threshold") is not None:
            lines.append("- Calm turn limit used: {0:.3f}".format(float(suggestion["rotation_threshold"])))

    return "\n".join(lines).strip()


def _safe_token(node_name):
    return re.sub(r"[^A-Za-z0-9_]+", "_", _short_name(node_name))


def _control_list_name(control_node):
    label = _get_string_attr(control_node, CONTACT_HOLD_FRIENDLY_NAME_ATTR, "").strip()
    return label or _short_name(control_node)


def _set_control_list_name(control_node, label):
    label = (label or "").strip()
    if not label:
        if cmds.attributeQuery(CONTACT_HOLD_FRIENDLY_NAME_ATTR, node=control_node, exists=True):
            try:
                cmds.deleteAttr("{0}.{1}".format(control_node, CONTACT_HOLD_FRIENDLY_NAME_ATTR))
            except Exception:
                _set_string_attr(control_node, CONTACT_HOLD_FRIENDLY_NAME_ATTR, "")
        return
    _set_string_attr(control_node, CONTACT_HOLD_FRIENDLY_NAME_ATTR, label)


def _hold_locator_name(control_node, hold_id=None):
    safe_name = _safe_token(control_node)
    if hold_id:
        return "amirContactHold_{0}_{1}_LOC".format(safe_name, str(hold_id).replace("-", "_"))
    return "amirContactHold_{0}_LOC".format(safe_name)


def _hold_hub_name(control_node):
    return "amirContactHold_{0}_HUB".format(_safe_token(control_node))


def _ensure_message_multi_attr(node_name, attr_name):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="message", multi=True)


def _managed_nodes(hub_node):
    if not hub_node or not cmds.objExists(hub_node) or not cmds.attributeQuery(CONTACT_HOLD_MANAGED_NODES_ATTR, node=hub_node, exists=True):
        return []
    nodes = cmds.listConnections("{0}.{1}".format(hub_node, CONTACT_HOLD_MANAGED_NODES_ATTR), source=True, destination=False) or []
    return _dedupe_preserve_order(_node_long_name(node_name) for node_name in nodes if node_name and cmds.objExists(node_name))


def _register_managed_node(hub_node, node_name):
    if not hub_node or not node_name or not cmds.objExists(hub_node) or not cmds.objExists(node_name):
        return node_name
    node_long = _node_long_name(node_name)
    if node_long in _managed_nodes(hub_node):
        return node_long
    _ensure_message_multi_attr(hub_node, CONTACT_HOLD_MANAGED_NODES_ATTR)
    next_index = int(cmds.getAttr("{0}.{1}".format(hub_node, CONTACT_HOLD_MANAGED_NODES_ATTR), size=True) or 0)
    cmds.connectAttr(node_long + ".message", "{0}.{1}[{2}]".format(hub_node, CONTACT_HOLD_MANAGED_NODES_ATTR, next_index), force=True)
    return node_long


def _delete_managed_nodes(hub_node):
    for node_name in _managed_nodes(hub_node):
        if cmds.objExists(node_name):
            try:
                cmds.delete(node_name)
            except Exception:
                pass


def _all_hold_hubs():
    root_group = _contact_hold_group(create=False)
    if not root_group:
        return []
    children = cmds.listRelatives(root_group, children=True, type="transform", fullPath=True) or []
    return [item for item in children if _get_bool_attr(item, CONTACT_HOLD_HUB_MARKER_ATTR, False)]


def _all_hold_locators():
    root_group = _contact_hold_group(create=False)
    if not root_group:
        return []
    children = cmds.listRelatives(root_group, children=True, type="transform", fullPath=True) or []
    return [item for item in children if _get_bool_attr(item, CONTACT_HOLD_MARKER_ATTR, False) and not _get_bool_attr(item, CONTACT_HOLD_HUB_MARKER_ATTR, False)]


def _hold_entries_for_control(control_node):
    control_long = _node_long_name(control_node)
    result = []
    for locator_node in _all_hold_locators():
        held_control = _connected_source_node(locator_node, CONTACT_HOLD_CONTROL_ATTR)
        if held_control == control_long:
            result.append(_node_long_name(locator_node))
    return _dedupe_preserve_order(result)


def _find_hold_hub(control_node):
    control_long = _node_long_name(control_node)
    for hub_node in _all_hold_hubs():
        held_control = _connected_source_node(hub_node, CONTACT_HOLD_CONTROL_ATTR)
        if held_control == control_long:
            return _node_long_name(hub_node)
    return ""


def _ensure_hold_hub(control_node):
    existing = _find_hold_hub(control_node)
    if existing and cmds.objExists(existing):
        return existing
    root_group = _contact_hold_group(create=True)
    hub_node = cmds.createNode("transform", name=_hold_hub_name(control_node), parent=root_group)
    hub_node = _node_long_name(hub_node)
    cmds.setAttr(hub_node + ".visibility", 0)
    _set_bool_attr(hub_node, CONTACT_HOLD_HUB_MARKER_ATTR, True)
    _ensure_message_attr(hub_node, CONTACT_HOLD_CONTROL_ATTR)
    _ensure_message_attr(hub_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
    _ensure_message_multi_attr(hub_node, CONTACT_HOLD_MANAGED_NODES_ATTR)
    _connect_message(control_node, hub_node, CONTACT_HOLD_CONTROL_ATTR)
    return hub_node


def _copy_original_channel_state(target_node, source_node, attribute):
    source_attr = _channel_source_attr_name(attribute)
    value_attr = _channel_value_attr_name(attribute)
    if not cmds.attributeQuery(source_attr, node=source_node, exists=True) and not cmds.attributeQuery(value_attr, node=source_node, exists=True):
        return False
    _set_string_attr(target_node, source_attr, _get_string_attr(source_node, source_attr, ""))
    _set_double_attr(target_node, value_attr, _get_double_attr(source_node, value_attr, 0.0))
    return True


def _capture_original_channel_state(storage_node, control_node, attribute, fallback_entries=None):
    source_attr = _channel_source_attr_name(attribute)
    if cmds.attributeQuery(source_attr, node=storage_node, exists=True):
        return
    for entry_node in fallback_entries or []:
        if _copy_original_channel_state(storage_node, entry_node, attribute):
            return
    control_plug = "{0}.{1}".format(control_node, attribute)
    incoming = cmds.listConnections(control_plug, source=True, destination=False, plugs=True) or []
    _set_string_attr(storage_node, source_attr, incoming[0] if incoming else "")
    _set_double_attr(storage_node, _channel_value_attr_name(attribute), cmds.getAttr(control_plug))


def _ensure_source_locator(control_node, hub_node, fallback_entries=None):
    existing = _connected_source_node(hub_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
    if existing and cmds.objExists(existing):
        return existing
    for entry_node in fallback_entries or []:
        seeded = _connected_source_node(entry_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
        if seeded and cmds.objExists(seeded):
            _connect_message(seeded, hub_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
            return seeded
    parent_node = (cmds.listRelatives(control_node, parent=True, fullPath=True) or [None])[0]
    source_locator = cmds.spaceLocator(name=_source_locator_name(control_node))[0]
    if parent_node:
        source_locator = cmds.parent(source_locator, parent_node)[0]
    source_locator = _node_long_name(source_locator)
    cmds.setAttr(source_locator + ".visibility", 0)
    source_shape = (cmds.listRelatives(source_locator, shapes=True, fullPath=True) or [None])[0]
    if source_shape:
        for attr_name in ("localScaleX", "localScaleY", "localScaleZ"):
            try:
                cmds.setAttr(source_shape + "." + attr_name, 0.2)
            except Exception:
                pass
    _connect_message(source_locator, hub_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
    return source_locator


def _ensure_source_channel(control_node, source_locator, storage_node, attribute, fallback_entries=None):
    _capture_original_channel_state(storage_node, control_node, attribute, fallback_entries=fallback_entries)
    source_attr = _channel_source_attr_name(attribute)
    value_attr = _channel_value_attr_name(attribute)
    source_plug = _get_string_attr(storage_node, source_attr, "")
    target_plug = "{0}.{1}".format(source_locator, attribute)
    _disconnect_destination(target_plug)
    if source_plug:
        try:
            _ensure_connected(source_plug, target_plug)
            return
        except Exception:
            pass
    cmds.setAttr(target_plug, _get_double_attr(storage_node, value_attr, cmds.getAttr("{0}.{1}".format(control_node, attribute))))


def _restore_original_channel(control_node, storage_node, attribute):
    if not _has_original_channel_state(storage_node, attribute):
        return
    control_plug = "{0}.{1}".format(control_node, attribute)
    _disconnect_destination(control_plug)
    source_attr = _channel_source_attr_name(attribute)
    value_attr = _channel_value_attr_name(attribute)
    source_plug = _get_string_attr(storage_node, source_attr, "")
    if source_plug:
        try:
            cmds.connectAttr(source_plug, control_plug, force=True)
            return
        except Exception:
            pass
    try:
        cmds.setAttr(control_plug, _get_double_attr(storage_node, value_attr, cmds.getAttr(control_plug)))
    except Exception:
        pass


def _clear_legacy_entry_nodes(entry_nodes):
    node_attrs = (
        CONTACT_HOLD_WORLD_SOURCE_DECOMP_ATTR,
        CONTACT_HOLD_WORLD_ANCHOR_DECOMP_ATTR,
        CONTACT_HOLD_WORLD_BLEND_ATTR,
        CONTACT_HOLD_LOCAL_POINT_ATTR,
        CONTACT_HOLD_ROTATE_SOURCE_DECOMP_ATTR,
        CONTACT_HOLD_ROTATE_ANCHOR_MM_ATTR,
        CONTACT_HOLD_ROTATE_ANCHOR_DECOMP_ATTR,
        CONTACT_HOLD_ROTATE_BLEND_ATTR,
    )
    for entry_node in entry_nodes:
        _delete_hold_nodes(entry_node, node_attrs)


def _create_hold_locator(control_node):
    root_group = _contact_hold_group(create=True)
    hold_id = uuid.uuid4().hex[:8]
    locator_node = cmds.spaceLocator(name=_hold_locator_name(control_node, hold_id))[0]
    locator_node = cmds.parent(locator_node, root_group)[0]
    locator_node = _node_long_name(locator_node)
    _set_bool_attr(locator_node, CONTACT_HOLD_MARKER_ATTR, True)
    _set_bool_attr(locator_node, CONTACT_HOLD_ENABLED_ATTR, True)
    _set_string_attr(locator_node, CONTACT_HOLD_ID_ATTR, hold_id)
    _ensure_message_attr(locator_node, CONTACT_HOLD_CONTROL_ATTR)
    _ensure_message_attr(locator_node, CONTACT_HOLD_HUB_ATTR)
    _connect_message(control_node, locator_node, CONTACT_HOLD_CONTROL_ATTR)
    locator_shape = (cmds.listRelatives(locator_node, shapes=True, fullPath=True) or [None])[0]
    if locator_shape:
        for attr_name in ("localScaleX", "localScaleY", "localScaleZ"):
            try:
                cmds.setAttr(locator_shape + "." + attr_name, 0.35)
            except Exception:
                pass
    return locator_node


def _hold_enabled_attr(locator_node):
    return "{0}.{1}".format(locator_node, CONTACT_HOLD_ENABLED_ATTR)


def _clear_hold_enabled_keys(locator_node):
    enabled_attr = _hold_enabled_attr(locator_node)
    if cmds.keyframe(enabled_attr, query=True, keyframeCount=True):
        try:
            cmds.cutKey(enabled_attr, clear=True)
        except Exception:
            pass


def _set_hold_enabled(locator_node, enabled, start_frame=None, end_frame=None):
    start = int(start_frame if start_frame is not None else _get_long_attr(locator_node, CONTACT_HOLD_START_ATTR, 1))
    end = int(end_frame if end_frame is not None else _get_long_attr(locator_node, CONTACT_HOLD_END_ATTR, start))
    if end < start:
        start, end = end, start
    enabled_attr = _hold_enabled_attr(locator_node)
    _clear_hold_enabled_keys(locator_node)
    weight_keys = [
        (start - 1, 0.0),
        (start, 1.0 if enabled else 0.0),
        (end, 1.0 if enabled else 0.0),
        (end + 1, 0.0),
    ]
    keyed_frames = set()
    for frame_value, key_value in weight_keys:
        frame_key = float(frame_value)
        if frame_key in keyed_frames:
            continue
        _set_step_key(enabled_attr, frame_value, key_value)
        keyed_frames.add(frame_key)
    _set_bool_attr(locator_node, CONTACT_HOLD_ENABLED_ATTR, enabled)
    return True, "Hold turned {0}.".format("on" if enabled else "off")


def _hold_payload(locator_node):
    if not locator_node or not cmds.objExists(locator_node):
        return None
    control_node = _connected_source_node(locator_node, CONTACT_HOLD_CONTROL_ATTR)
    if not control_node:
        return None
    hub_node = _connected_source_node(locator_node, CONTACT_HOLD_HUB_ATTR) or _find_hold_hub(control_node)
    enabled = _get_bool_attr(locator_node, CONTACT_HOLD_ENABLED_ATTR, True)
    return {
        "locator": _node_long_name(locator_node),
        "id": _get_string_attr(locator_node, CONTACT_HOLD_ID_ATTR, _short_name(locator_node)),
        "control": _node_long_name(control_node),
        "hub": _node_long_name(hub_node) if hub_node else "",
        "source_locator": _connected_source_node(hub_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR) if hub_node else "",
        "enabled_attr": _hold_enabled_attr(locator_node),
        "start_frame": _get_long_attr(locator_node, CONTACT_HOLD_START_ATTR, 1),
        "end_frame": _get_long_attr(locator_node, CONTACT_HOLD_END_ATTR, 1),
        "axes": _normalized_hold_axes(_get_string_attr(locator_node, CONTACT_HOLD_AXES_ATTR, "").split(",")),
        "keep_rotation": _get_bool_attr(locator_node, CONTACT_HOLD_KEEP_ROTATION_ATTR, False),
        "enabled": enabled,
        "list_name": _control_list_name(control_node),
        "state_text": "Hold" if enabled else "Original Motion",
    }


def _sorted_hold_entries(control_node=None):
    entry_nodes = _hold_entries_for_control(control_node) if control_node else _all_hold_locators()
    payloads = []
    for locator_node in entry_nodes:
        payload = _hold_payload(locator_node)
        if payload:
            payloads.append(payload)
    payloads.sort(
        key=lambda item: (
            item.get("list_name", "").lower(),
            int(item.get("start_frame", 0)),
            int(item.get("end_frame", 0)),
            item.get("id", ""),
        )
    )
    return payloads


def _find_hold_locator(control_node):
    payloads = _sorted_hold_entries(control_node)
    if not payloads:
        return ""
    return payloads[0]["locator"]


def _create_entry_blend_node(hub_node, control_node, locator_node, suffix, node_type="blendColors"):
    hold_id = _get_string_attr(locator_node, CONTACT_HOLD_ID_ATTR, "") or uuid.uuid4().hex[:8]
    node_name = _ensure_utility_node(node_type, _solver_node_name(control_node, "{0}_{1}".format(hold_id, suffix)))
    return _register_managed_node(hub_node, node_name)


def _rebuild_translation_hold_network(hub_node, control_node, entry_payloads):
    entry_nodes = [item["locator"] for item in entry_payloads]
    source_locator = _ensure_source_locator(control_node, hub_node, entry_nodes)
    for attribute in ("translateX", "translateY", "translateZ"):
        _ensure_source_channel(control_node, source_locator, hub_node, attribute, fallback_entries=entry_nodes)

    source_decomp = _register_managed_node(hub_node, _ensure_utility_node("decomposeMatrix", _solver_node_name(control_node, "worldSource_dcmp")))
    point_solver = _register_managed_node(hub_node, _ensure_utility_node("vectorProduct", _solver_node_name(control_node, "localPoint_vp")))
    _ensure_connected(source_locator + ".worldMatrix[0]", source_decomp + ".inputMatrix")
    cmds.setAttr(point_solver + ".operation", 4)
    _ensure_connected(control_node + ".parentInverseMatrix[0]", point_solver + ".matrix")

    current_outputs = {
        "x": source_decomp + ".outputTranslateX",
        "y": source_decomp + ".outputTranslateY",
        "z": source_decomp + ".outputTranslateZ",
    }
    axis_map = {"x": ("X", "R"), "y": ("Y", "G"), "z": ("Z", "B")}
    for payload in entry_payloads:
        locator_node = payload["locator"]
        held_axes = set(payload.get("axes") or ())
        anchor_decomp = _register_managed_node(hub_node, _ensure_utility_node("decomposeMatrix", _solver_node_name(control_node, "{0}_anchor_dcmp".format(payload["id"]))))
        blend_node = _create_entry_blend_node(hub_node, control_node, locator_node, "worldBlend")
        _ensure_connected(locator_node + ".worldMatrix[0]", anchor_decomp + ".inputMatrix")
        _ensure_connected(locator_node + "." + CONTACT_HOLD_ENABLED_ATTR, blend_node + ".blender")
        next_outputs = {}
        for axis_name, (axis_suffix, color_suffix) in axis_map.items():
            previous_output = current_outputs[axis_name]
            held_output = anchor_decomp + ".outputTranslate" + axis_suffix if axis_name in held_axes else previous_output
            _ensure_connected(held_output, blend_node + ".color1" + color_suffix)
            _ensure_connected(previous_output, blend_node + ".color2" + color_suffix)
            next_outputs[axis_name] = blend_node + ".output" + color_suffix
        current_outputs = next_outputs

    for axis_name, axis_suffix in (("x", "X"), ("y", "Y"), ("z", "Z")):
        _ensure_connected(current_outputs[axis_name], point_solver + ".input1" + axis_suffix)
        _ensure_connected(point_solver + ".output" + axis_suffix, control_node + ".translate" + axis_suffix)


def _rebuild_rotation_hold_network(hub_node, control_node, entry_payloads):
    keep_rotation_entries = [item for item in entry_payloads if item.get("keep_rotation")]
    if not keep_rotation_entries:
        for attribute in ("rotateX", "rotateY", "rotateZ"):
            _restore_original_channel(control_node, hub_node, attribute)
        return

    entry_nodes = [item["locator"] for item in entry_payloads]
    source_locator = _ensure_source_locator(control_node, hub_node, entry_nodes)
    for attribute in ("rotateX", "rotateY", "rotateZ"):
        _ensure_source_channel(control_node, source_locator, hub_node, attribute, fallback_entries=entry_nodes)

    current_outputs = {
        "X": source_locator + ".rotateX",
        "Y": source_locator + ".rotateY",
        "Z": source_locator + ".rotateZ",
    }
    for payload in keep_rotation_entries:
        locator_node = payload["locator"]
        anchor_local_mm = _register_managed_node(hub_node, _ensure_utility_node("multMatrix", _solver_node_name(control_node, "{0}_rotateAnchorLocal_mm".format(payload["id"]))))
        anchor_local_decomp = _register_managed_node(hub_node, _ensure_utility_node("decomposeMatrix", _solver_node_name(control_node, "{0}_rotateAnchorLocal_dcmp".format(payload["id"]))))
        rotate_blend = _create_entry_blend_node(hub_node, control_node, locator_node, "rotateBlend")
        _ensure_connected(locator_node + ".worldMatrix[0]", anchor_local_mm + ".matrixIn[0]")
        _ensure_connected(control_node + ".parentInverseMatrix[0]", anchor_local_mm + ".matrixIn[1]")
        _ensure_connected(anchor_local_mm + ".matrixSum", anchor_local_decomp + ".inputMatrix")
        _ensure_connected(locator_node + "." + CONTACT_HOLD_ENABLED_ATTR, rotate_blend + ".blender")
        for axis_suffix, color_suffix in (("X", "R"), ("Y", "G"), ("Z", "B")):
            _ensure_connected(anchor_local_decomp + ".outputRotate" + axis_suffix, rotate_blend + ".color1" + color_suffix)
            _ensure_connected(current_outputs[axis_suffix], rotate_blend + ".color2" + color_suffix)
            current_outputs[axis_suffix] = rotate_blend + ".output" + color_suffix

    for axis_suffix in ("X", "Y", "Z"):
        _ensure_connected(current_outputs[axis_suffix], control_node + ".rotate" + axis_suffix)


def _rebuild_control_hold_network(control_node):
    control_long = _node_long_name(control_node)
    entry_payloads = _sorted_hold_entries(control_long)
    hub_node = _find_hold_hub(control_long)
    if not hub_node and not entry_payloads:
        return
    hub_node = hub_node or _ensure_hold_hub(control_long)
    entry_nodes = [item["locator"] for item in entry_payloads]
    for entry_node in entry_nodes:
        _connect_message(hub_node, entry_node, CONTACT_HOLD_HUB_ATTR)
    for attribute in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
        _capture_original_channel_state(hub_node, control_long, attribute, fallback_entries=entry_nodes)

    _clear_legacy_entry_nodes(entry_nodes)
    _delete_managed_nodes(hub_node)
    if not entry_payloads:
        for attribute in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
            _restore_original_channel(control_long, hub_node, attribute)
        source_locator = _connected_source_node(hub_node, CONTACT_HOLD_SOURCE_LOCATOR_ATTR)
        if source_locator and cmds.objExists(source_locator):
            try:
                cmds.delete(source_locator)
            except Exception:
                pass
        if cmds.objExists(hub_node):
            try:
                cmds.delete(hub_node)
            except Exception:
                pass
        root_group = _contact_hold_group(create=False)
        if root_group and not (cmds.listRelatives(root_group, children=True, fullPath=True) or []):
            try:
                cmds.delete(root_group)
            except Exception:
                pass
        return

    _rebuild_translation_hold_network(hub_node, control_long, entry_payloads)
    _rebuild_rotation_hold_network(hub_node, control_long, entry_payloads)


def _remove_hold_entry(locator_node):
    payload = _hold_payload(locator_node)
    if not payload:
        return
    control_node = payload["control"]
    if cmds.objExists(locator_node):
        try:
            cmds.delete(locator_node)
        except Exception:
            pass
    _rebuild_control_hold_network(control_node)


def _delete_all_holds():
    payloads = _sorted_hold_entries()
    if not payloads:
        return 0
    controls = _dedupe_preserve_order(item["control"] for item in payloads if item.get("control"))
    for payload in payloads:
        locator_node = payload["locator"]
        if cmds.objExists(locator_node):
            try:
                cmds.delete(locator_node)
            except Exception:
                pass
    for control_node in controls:
        _rebuild_control_hold_network(control_node)
    return len(payloads)


def _format_report(report):
    if not report:
        return "Pick the hand or foot control, choose the contact frame range, choose the world axis to hold, then click Check Setup."

    lines = [
        "Controls: {0}".format(len(report.get("controls", []))),
        "Start Frame: {0}".format(int(report.get("start_frame", 0))),
        "End Frame: {0}".format(int(report.get("end_frame", 0))),
        "Held World Axes: {0}".format(_hold_axis_label(report.get("axes", ()))),
        "Keep Turn Too: {0}".format("Yes" if report.get("keep_rotation", True) else "No"),
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
        lines.append("- This hold looks ready to create as a live editable setup.")
        lines.append("")

    if report.get("controls"):
        lines.append("Picked Controls")
        for node_name in report["controls"]:
            lines.append("- " + _control_list_name(node_name))

    existing_setups = report.get("existing_setups", [])
    if existing_setups:
        lines.append("")
        lines.append("Saved Holds In Scene")
        for item in existing_setups:
            lines.append(
                "- {0}: {1}-{2}, axes {3}, {4}".format(
                    item.get("list_name", _short_name(item["control"])),
                    int(item["start_frame"]),
                    int(item["end_frame"]),
                    _hold_axis_label(item.get("axes", ())),
                    item.get("state_text", "Hold"),
                )
            )

    suggestion = report.get("suggestion")
    if suggestion:
        lines.append("")
        lines.append("Suggested Plant Range")
        lines.append("- Frames: {0} to {1}".format(int(suggestion["start_frame"]), int(suggestion["end_frame"])))
        lines.append("- Calm move limit used: {0:.3f}".format(float(suggestion["move_threshold"])))
        lines.append("- Calm height limit used: {0:.3f}".format(float(suggestion["height_threshold"])))
        if report.get("keep_rotation") and suggestion.get("rotation_threshold") is not None:
            lines.append("- Calm turn limit used: {0:.3f}".format(float(suggestion["rotation_threshold"])))

    return "\n".join(lines).strip()


class MayaContactHoldController(object):
    def __init__(self):
        self.control_nodes = []
        self.selected_hold_locators = []
        self.start_frame = 1
        self.end_frame = 1
        self.keep_rotation = False
        self.hold_axes = tuple(DEFAULT_HOLD_AXES)
        self.report = None
        self.last_suggestion = None
        self.status_callback = None
        if MAYA_AVAILABLE:
            current = _current_frame()
            self.start_frame = current
            self.end_frame = current

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

    def _resolved_controls(self):
        controls = []
        for node_name in self.control_nodes:
            if node_name and cmds.objExists(node_name):
                controls.append(_node_long_name(node_name))
        self.control_nodes = _dedupe_preserve_order(controls)
        return list(self.control_nodes)

    def _load_first_existing_setup(self):
        controls = self._resolved_controls()
        if not controls:
            return None
        payloads = _sorted_hold_entries(controls[0])
        if not payloads:
            return None
        payload = payloads[0]
        self.start_frame = int(payload["start_frame"])
        self.end_frame = int(payload["end_frame"])
        self.keep_rotation = bool(payload["keep_rotation"])
        self.hold_axes = tuple(payload.get("axes") or DEFAULT_HOLD_AXES)
        return payload

    def _resolved_selected_hold_locators(self):
        locators = []
        for locator_node in self.selected_hold_locators:
            if locator_node and cmds.objExists(locator_node):
                payload = _hold_payload(locator_node)
                if payload:
                    locators.append(payload["locator"])
        self.selected_hold_locators = _dedupe_preserve_order(locators)
        return list(self.selected_hold_locators)

    def hold_entries(self):
        return _sorted_hold_entries()

    def set_selected_hold_locators(self, locator_nodes):
        self.selected_hold_locators = []
        for locator_node in locator_nodes or []:
            payload = _hold_payload(locator_node)
            if payload:
                self.selected_hold_locators.append(payload["locator"])
        self.selected_hold_locators = _dedupe_preserve_order(self.selected_hold_locators)
        return list(self.selected_hold_locators)

    def _hold_targets(self):
        selected_locators = self._resolved_selected_hold_locators()
        if selected_locators:
            return selected_locators
        locators = []
        for control_node in self._resolved_controls():
            locators.extend(_hold_entries_for_control(control_node))
        return _dedupe_preserve_order(locators)

    def selected_hold_payload(self):
        selected_locators = self._resolved_selected_hold_locators()
        if not selected_locators:
            return None
        return _hold_payload(selected_locators[0])

    def load_selected_hold(self):
        payload = self.selected_hold_payload()
        if not payload:
            return False, "Pick a saved hold in the list first."
        self.control_nodes = [payload["control"]]
        self.start_frame = int(payload["start_frame"])
        self.end_frame = int(payload["end_frame"])
        self.keep_rotation = bool(payload["keep_rotation"])
        self.hold_axes = tuple(payload.get("axes") or DEFAULT_HOLD_AXES)
        return True, "Loaded {0} from frames {1} to {2}.".format(payload["list_name"], self.start_frame, self.end_frame)

    def set_control_list_name(self, label):
        controls = self._resolved_controls()
        payload = self.selected_hold_payload()
        if payload:
            controls = [payload["control"]]
        if not controls:
            return False, "Pick a hand or foot, or pick a saved hold in the list first."
        for control_node in controls:
            _set_control_list_name(control_node, label)
        return True, "Updated the list name for {0} control(s).".format(len(controls))

    def set_controls_from_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        control_nodes = _selected_controls()
        if not control_nodes:
            return False, "Pick one or more hand or foot controls first."
        self.control_nodes = control_nodes
        self.selected_hold_locators = []
        self.last_suggestion = None
        payloads = _sorted_hold_entries(self.control_nodes[0]) if self.control_nodes else []
        payload = payloads[0] if payloads else None
        if payload:
            self.start_frame = int(payload["start_frame"])
            self.end_frame = int(payload["end_frame"])
            self.keep_rotation = bool(payload["keep_rotation"])
            self.hold_axes = tuple(payload.get("axes") or DEFAULT_HOLD_AXES)
            return True, "Picked {0} control(s) and loaded the saved hold range from {1}.".format(
                len(self.control_nodes),
                payload["list_name"],
            )
        return True, "Picked {0} control(s).".format(len(control_nodes))

    def add_matching_other_side(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not self.control_nodes:
            return False, "Pick a hand or foot first, then add the matching other side."

        current_nodes = [_node_long_name(node_name) for node_name in self.control_nodes if node_name and cmds.objExists(node_name)]
        current_nodes = _dedupe_preserve_order(current_nodes)
        if not current_nodes:
            self.control_nodes = []
            return False, "Your picked controls are no longer in the scene."

        added_nodes = []
        notes = []
        for node_name in current_nodes:
            match, note = _find_other_side_control(node_name, taken_nodes=current_nodes + added_nodes)
            if match:
                added_nodes.append(match)
            elif note:
                notes.append(note)

        added_nodes = _dedupe_preserve_order(added_nodes)
        if not added_nodes:
            message = "I could not find a matching other-side control."
            if notes:
                message += " " + " ".join(notes)
            return False, message

        self.control_nodes = _dedupe_preserve_order(current_nodes + added_nodes)
        self.last_suggestion = None
        self._load_first_existing_setup()
        message = "Added {0} matching other-side control(s).".format(len(added_nodes))
        if notes:
            message += " " + " ".join(notes)
        return True, message

    def set_start_from_current(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        self.start_frame = _current_frame()
        if self.end_frame < self.start_frame:
            self.end_frame = self.start_frame
        return True, "Start frame set to {0}.".format(int(self.start_frame))

    def set_end_from_current(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        self.end_frame = _current_frame()
        if self.end_frame < self.start_frame:
            self.start_frame = self.end_frame
        return True, "End frame set to {0}.".format(int(self.end_frame))

    def suggest_range(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        controls = []
        for node_name in self.control_nodes:
            if node_name and cmds.objExists(node_name):
                controls.append(_node_long_name(node_name))
        controls = _dedupe_preserve_order(controls)
        if not controls:
            return False, "Pick one or more hand or foot controls first."

        suggestion = _suggest_contact_run(controls, _current_frame(), self.keep_rotation)
        if not suggestion:
            return False, "I could not find a calm planted range in the playback range yet."

        self.control_nodes = controls
        self.start_frame = int(suggestion["start_frame"])
        self.end_frame = int(suggestion["end_frame"])
        self.last_suggestion = suggestion
        return True, "Suggested frames {0} to {1} from the calmest nearby contact range.".format(self.start_frame, self.end_frame)

    def analyze_setup(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."

        controls = self._resolved_controls()
        errors = []
        warnings = []
        hold_axes = _normalized_hold_axes(self.hold_axes)
        existing_setups = []

        if not controls:
            errors.append("Pick one or more hand or foot controls first.")
        if int(self.end_frame) < int(self.start_frame):
            errors.append("End Frame must be the same as or after Start Frame.")
        if not hold_axes and not self.keep_rotation:
            errors.append("Turn on at least one world axis to hold, or turn on Keep Turn Too.")

        for node_name in controls:
            key_channels = _channels_for_hold(node_name, ("x", "y", "z"), self.keep_rotation)
            if len([item for item in key_channels if item.startswith("translate")]) < 3:
                errors.append("{0} needs unlocked move channels on X, Y, and Z so the live world-axis hold can solve cleanly.".format(_short_name(node_name)))
            if self.keep_rotation and len([item for item in key_channels if item.startswith("rotate")]) < 3:
                errors.append("{0} needs unlocked turn channels, or turn off Keep Turn Too.".format(_short_name(node_name)))
            existing_setups.extend(_sorted_hold_entries(node_name))

        if int(self.start_frame) == int(self.end_frame):
            warnings.append("Start and End are the same frame, so this will only make a one-frame hold.")

        self.report = {
            "controls": controls,
            "start_frame": int(self.start_frame),
            "end_frame": int(self.end_frame),
            "axes": hold_axes,
            "keep_rotation": bool(self.keep_rotation),
            "existing_setups": existing_setups,
            "suggestion": dict(self.last_suggestion) if self.last_suggestion else None,
            "errors": _dedupe_preserve_order(errors),
            "warnings": _dedupe_preserve_order(warnings),
        }

        if errors:
            return False, "This hold is not safe yet. Read the red notes below."
        if warnings:
            return True, "This hold can work, but read the yellow notes first."
        return True, "This hold looks ready."

    def apply_hold(self):
        if not self.report or self.report.get("errors"):
            success, message = self.analyze_setup()
            if not success:
                return False, message
        _stabilize_contact_hold_evaluation()

        controls = list(self.report["controls"])
        start_frame = int(self.report["start_frame"])
        end_frame = int(self.report["end_frame"])
        hold_axes = tuple(self.report.get("axes") or ())
        keep_rotation = bool(self.report["keep_rotation"])
        current_time = float(cmds.currentTime(query=True))

        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaContactHold")
            cmds.currentTime(start_frame, edit=True)
            created_locators = []
            for node_name in controls:
                matching_entries = [
                    item
                    for item in _sorted_hold_entries(node_name)
                    if int(item.get("start_frame", 0)) == start_frame
                    and int(item.get("end_frame", 0)) == end_frame
                    and tuple(item.get("axes") or ()) == hold_axes
                    and bool(item.get("keep_rotation")) == keep_rotation
                ]
                if matching_entries:
                    continue
                hub_node = _ensure_hold_hub(node_name)
                locator_node = _create_hold_locator(node_name)
                _snap_hold_locator(locator_node, node_name, keep_rotation)
                _set_string_attr(locator_node, CONTACT_HOLD_AXES_ATTR, ",".join(hold_axes))
                _set_long_attr(locator_node, CONTACT_HOLD_START_ATTR, start_frame)
                _set_long_attr(locator_node, CONTACT_HOLD_END_ATTR, end_frame)
                _set_bool_attr(locator_node, CONTACT_HOLD_KEEP_ROTATION_ATTR, keep_rotation)
                _connect_message(hub_node, locator_node, CONTACT_HOLD_HUB_ATTR)
                success, message = _set_hold_enabled(locator_node, True, start_frame, end_frame)
                if not success:
                    return False, message
                _rebuild_control_hold_network(node_name)
                created_locators.append(locator_node)
        except Exception as exc:
            _warning(traceback.format_exc())
            return False, "Could not make the hold: {0}".format(exc)
        finally:
            try:
                cmds.currentTime(current_time, edit=True)
            except Exception:
                pass
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

        self.report = None
        self.selected_hold_locators = _dedupe_preserve_order(created_locators)
        return True, "Saved {0} new live hold(s) from frame {1} to {2} on world axis {3}.".format(
            len(created_locators),
            start_frame,
            end_frame,
            _hold_axis_label(hold_axes),
        )

    def update_selected_hold(self):
        locator_nodes = self._resolved_selected_hold_locators()
        if not locator_nodes:
            return False, "Pick one or more saved hold rows in the list first."
        _stabilize_contact_hold_evaluation()
        hold_axes = _normalized_hold_axes(self.hold_axes)
        start_frame = int(self.start_frame)
        end_frame = int(self.end_frame)
        keep_rotation = bool(self.keep_rotation)
        current_time = float(cmds.currentTime(query=True))
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaContactHoldUpdate")
            cmds.currentTime(start_frame, edit=True)
            updated = 0
            for locator_node in locator_nodes:
                payload = _hold_payload(locator_node)
                if not payload:
                    continue
                _snap_hold_locator(locator_node, payload["control"], keep_rotation)
                _set_string_attr(locator_node, CONTACT_HOLD_AXES_ATTR, ",".join(hold_axes))
                _set_long_attr(locator_node, CONTACT_HOLD_START_ATTR, start_frame)
                _set_long_attr(locator_node, CONTACT_HOLD_END_ATTR, end_frame)
                _set_bool_attr(locator_node, CONTACT_HOLD_KEEP_ROTATION_ATTR, keep_rotation)
                success, message = _set_hold_enabled(locator_node, payload["enabled"], start_frame, end_frame)
                if not success:
                    return False, message
                _rebuild_control_hold_network(payload["control"])
                updated += 1
        finally:
            try:
                cmds.currentTime(current_time, edit=True)
            except Exception:
                pass
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self.report = None
        return True, "Updated {0} picked hold row(s).".format(updated)

    def enable_hold(self):
        locator_nodes = self._hold_targets()
        if not locator_nodes:
            return False, "Pick the hand or foot control with the saved hold first, or pick saved rows in the list."
        _stabilize_contact_hold_evaluation()
        updated = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaContactHoldEnable")
            for locator_node in locator_nodes:
                success, message = _set_hold_enabled(locator_node, True)
                if not success:
                    return False, message
                updated += 1
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not updated:
            return False, "I could not find a saved hold to turn on."
        self.report = None
        return True, "Turned the picked saved hold(s) back on for {0} row(s).".format(updated)

    def disable_hold(self):
        locator_nodes = self._hold_targets()
        if not locator_nodes:
            return False, "Pick the hand or foot control with the saved hold first, or pick saved rows in the list."
        _stabilize_contact_hold_evaluation()
        updated = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaContactHoldDisable")
            for locator_node in locator_nodes:
                success, message = _set_hold_enabled(locator_node, False)
                if not success:
                    return False, message
                updated += 1
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not updated:
            return False, "I could not find a saved hold to turn off."
        self.report = None
        return True, "Switched the picked saved hold(s) back to the original motion for {0} row(s).".format(updated)

    def delete_hold(self):
        locator_nodes = self._hold_targets()
        if not locator_nodes:
            return False, "Pick the hand or foot control with the saved hold first, or pick saved rows in the list."
        _stabilize_contact_hold_evaluation()
        deleted = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaContactHoldDelete")
            for locator_node in locator_nodes:
                if not _hold_payload(locator_node):
                    continue
                _remove_hold_entry(locator_node)
                deleted += 1
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not deleted:
            return False, "I could not find a saved hold to delete."
        self.report = None
        self.selected_hold_locators = []
        return True, "Deleted {0} saved hold row(s).".format(deleted)

    def delete_all_holds(self):
        _stabilize_contact_hold_evaluation()
        try:
            cmds.undoInfo(openChunk=True, chunkName="MayaContactHoldDeleteAll")
            deleted = _delete_all_holds()
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not deleted:
            return False, "There are no saved holds to delete yet."
        self.report = None
        self.selected_hold_locators = []
        return True, "Deleted all {0} saved hold rows from the scene.".format(deleted)


class _WindowBase(QtWidgets.QDialog if QtWidgets else object):
    pass


if QtWidgets:
    class MayaContactHoldWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaContactHoldWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.set_status_callback(self._set_status)
            self._syncing_table = False
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Hand / Foot Hold")
            self.setMinimumWidth(640)
            self.setMinimumHeight(520)
            self._build_ui()
            self._sync_from_controller()

        def _build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            intro = QtWidgets.QLabel(
                "Make a live hand or foot hold that stays editable. "
                "Pick the control, choose the contact range, choose which world axis should stay locked, and the tool builds a reversible setup instead of baking every frame. "
                "Each saved hold shows up in the list below so you can tweak or remove it later."
            )
            intro.setWordWrap(True)
            main_layout.addWidget(intro)

            controls_row = QtWidgets.QHBoxLayout()
            self.controls_line = QtWidgets.QLineEdit()
            self.controls_line.setReadOnly(True)
            self.controls_line.setToolTip("The hand or foot controls this tool will keep in place.")
            self.use_selection_button = QtWidgets.QPushButton("Use Picked Hand / Foot")
            self.use_selection_button.setToolTip("Pick one or more hand or foot controls in Maya, then click this.")
            self.add_other_side_button = QtWidgets.QPushButton("Add Matching Other Side")
            self.add_other_side_button.setToolTip("Try to find the other hand or foot that matches the one you picked, like left foot to right foot.")
            controls_row.addWidget(QtWidgets.QLabel("Picked Controls"))
            controls_row.addWidget(self.controls_line, 1)
            controls_row.addWidget(self.use_selection_button)
            controls_row.addWidget(self.add_other_side_button)
            main_layout.addLayout(controls_row)

            alias_row = QtWidgets.QHBoxLayout()
            self.list_name_line = QtWidgets.QLineEdit()
            self.list_name_line.setPlaceholderText("Friendly list name, like Right Foot")
            self.list_name_line.setToolTip("This changes the label shown in the saved hold list. It does not rename the real rig control.")
            self.rename_button = QtWidgets.QPushButton("Rename In List")
            self.rename_button.setToolTip("Save a friendlier list name for the picked control or the picked saved hold.")
            alias_row.addWidget(QtWidgets.QLabel("List Name"))
            alias_row.addWidget(self.list_name_line, 1)
            alias_row.addWidget(self.rename_button)
            main_layout.addLayout(alias_row)

            frame_grid = QtWidgets.QGridLayout()
            self.start_spin = QtWidgets.QSpinBox()
            self.start_spin.setRange(-100000, 100000)
            self.start_spin.setToolTip("The first frame where the hand or foot touches and should start staying locked.")
            self.use_start_button = QtWidgets.QPushButton("Use Current For Contact Start")
            self.use_start_button.setToolTip("Go to the first planted frame in Maya, then click this.")
            self.end_spin = QtWidgets.QSpinBox()
            self.end_spin.setRange(-100000, 100000)
            self.end_spin.setToolTip("The last frame where the hand or foot should stay locked before it lifts or slides away.")
            self.use_end_button = QtWidgets.QPushButton("Use Current For Lift End")
            self.use_end_button.setToolTip("Go to the frame where the hand or foot stops sticking, then click this.")
            self.suggest_range_button = QtWidgets.QPushButton("Suggest Range")
            self.suggest_range_button.setToolTip("Look through the playback range and guess a calm planted range near the current frame.")
            frame_grid.addWidget(QtWidgets.QLabel("Start Frame"), 0, 0)
            frame_grid.addWidget(self.start_spin, 0, 1)
            frame_grid.addWidget(self.use_start_button, 0, 2)
            frame_grid.addWidget(QtWidgets.QLabel("End Frame"), 1, 0)
            frame_grid.addWidget(self.end_spin, 1, 1)
            frame_grid.addWidget(self.use_end_button, 1, 2)
            frame_grid.addWidget(self.suggest_range_button, 2, 1, 1, 2)
            main_layout.addLayout(frame_grid)

            axis_box = QtWidgets.QGroupBox("World Axes To Keep Still")
            axis_layout = QtWidgets.QHBoxLayout(axis_box)
            self.hold_x_check = QtWidgets.QCheckBox("Hold X")
            self.hold_x_check.setToolTip("Keep the world X position locked through the hold range.")
            self.hold_y_check = QtWidgets.QCheckBox("Hold Y")
            self.hold_y_check.setToolTip("Keep the world Y position locked through the hold range.")
            self.hold_z_check = QtWidgets.QCheckBox("Hold Z")
            self.hold_z_check.setToolTip("Keep the world Z position locked through the hold range.")
            axis_layout.addWidget(self.hold_x_check)
            axis_layout.addWidget(self.hold_y_check)
            axis_layout.addWidget(self.hold_z_check)
            axis_layout.addStretch(1)
            main_layout.addWidget(axis_box)

            self.keep_rotation_check = QtWidgets.QCheckBox("Keep Turn Too")
            self.keep_rotation_check.setToolTip("Turn this on only if the hand or foot should also keep the same world rotation. Leave it off if the foot needs to roll while planted.")
            main_layout.addWidget(self.keep_rotation_check)

            create_row = QtWidgets.QHBoxLayout()
            self.analyze_button = QtWidgets.QPushButton("Check Setup")
            self.analyze_button.setToolTip("Check that the picked controls, frame range, and chosen axes are ready.")
            self.apply_button = QtWidgets.QPushButton("Save New Hold")
            self.apply_button.setToolTip("Save a brand-new hold row for the picked controls. This does not overwrite older hold rows.")
            self.update_button = QtWidgets.QPushButton("Update Picked Hold")
            self.update_button.setToolTip("Refresh the picked saved hold row using the current frame range, axes, and Keep Turn Too setting.")
            create_row.addWidget(self.analyze_button)
            create_row.addWidget(self.apply_button)
            create_row.addWidget(self.update_button)
            main_layout.addLayout(create_row)

            hold_group = QtWidgets.QGroupBox("Saved Holds In Scene")
            hold_layout = QtWidgets.QVBoxLayout(hold_group)
            self.holds_table = QtWidgets.QTableWidget(0, 6)
            self.holds_table.setHorizontalHeaderLabels(["Name", "Control", "Frames", "Axes", "Turn", "State"])
            self.holds_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.holds_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.holds_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.holds_table.setAlternatingRowColors(True)
            self.holds_table.setToolTip("Pick a saved row to load it back into the frame and axis boxes. You can multi-pick rows to turn them on, turn them off, or delete them together.")
            header = self.holds_table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
            hold_layout.addWidget(self.holds_table, 1)

            manage_row = QtWidgets.QHBoxLayout()
            self.enable_button = QtWidgets.QPushButton("Use Hold On Picked")
            self.enable_button.setToolTip("Turn the picked saved hold rows back on.")
            self.disable_button = QtWidgets.QPushButton("Use Original Motion On Picked")
            self.disable_button.setToolTip("Turn the picked saved hold rows off so those ranges follow the original animation again.")
            self.delete_button = QtWidgets.QPushButton("Delete Picked Hold")
            self.delete_button.setToolTip("Remove just the picked saved hold rows.")
            self.delete_all_button = QtWidgets.QPushButton("Delete All Holds")
            self.delete_all_button.setToolTip("Remove every saved hand and foot hold from the whole scene.")
            manage_row.addWidget(self.enable_button)
            manage_row.addWidget(self.disable_button)
            manage_row.addWidget(self.delete_button)
            manage_row.addWidget(self.delete_all_button)
            hold_layout.addLayout(manage_row)
            main_layout.addWidget(hold_group, 1)

            self.report_box = QtWidgets.QPlainTextEdit()
            self.report_box.setReadOnly(True)
            self.report_box.setToolTip("Helpful notes about the current hold setup.")
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
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.setToolTip("Open Amir's PayPal donate link. Set AMIR_PAYPAL_DONATE_URL or AMIR_DONATE_URL to customize it.")
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

            self.use_selection_button.clicked.connect(self._use_selection)
            self.add_other_side_button.clicked.connect(self._add_other_side)
            self.rename_button.clicked.connect(self._rename_list_name)
            self.use_start_button.clicked.connect(self._use_start_frame)
            self.use_end_button.clicked.connect(self._use_end_frame)
            self.suggest_range_button.clicked.connect(self._suggest_range)
            self.keep_rotation_check.toggled.connect(self._sync_to_controller)
            self.hold_x_check.toggled.connect(self._sync_to_controller)
            self.hold_y_check.toggled.connect(self._sync_to_controller)
            self.hold_z_check.toggled.connect(self._sync_to_controller)
            self.start_spin.valueChanged.connect(self._sync_to_controller)
            self.end_spin.valueChanged.connect(self._sync_to_controller)
            self.analyze_button.clicked.connect(self._analyze)
            self.apply_button.clicked.connect(self._apply)
            self.update_button.clicked.connect(self._update_hold)
            self.enable_button.clicked.connect(self._enable_hold)
            self.disable_button.clicked.connect(self._disable_hold)
            self.delete_button.clicked.connect(self._delete_hold)
            self.delete_all_button.clicked.connect(self._delete_all_holds)
            self.holds_table.itemSelectionChanged.connect(self._on_hold_selection_changed)
            self.holds_table.itemDoubleClicked.connect(self._load_picked_hold)

        def _selected_table_locators(self):
            rows = sorted(set(index.row() for index in self.holds_table.selectionModel().selectedRows()))
            locator_nodes = []
            for row_index in rows:
                item = self.holds_table.item(row_index, 0)
                locator_node = item.data(QtCore.Qt.UserRole) if item else ""
                if locator_node:
                    locator_nodes.append(locator_node)
            return locator_nodes

        def _refresh_hold_table(self):
            selected_locators = set(self.controller._resolved_selected_hold_locators())
            payloads = self.controller.hold_entries()
            self._syncing_table = True
            blocker = QtCore.QSignalBlocker(self.holds_table)
            try:
                self.holds_table.clearSelection()
                self.holds_table.setRowCount(len(payloads))
                rows_to_select = []
                for row_index, payload in enumerate(payloads):
                    row_values = [
                        payload.get("list_name", ""),
                        _short_name(payload.get("control", "")),
                        "{0}-{1}".format(int(payload.get("start_frame", 0)), int(payload.get("end_frame", 0))),
                        _hold_axis_label(payload.get("axes", ())),
                        "Keep Turn" if payload.get("keep_rotation") else "Keep Original Turn",
                        payload.get("state_text", "Hold"),
                    ]
                    for column_index, value in enumerate(row_values):
                        item = QtWidgets.QTableWidgetItem(str(value))
                        if column_index == 0:
                            item.setData(QtCore.Qt.UserRole, payload["locator"])
                        self.holds_table.setItem(row_index, column_index, item)
                    if payload["locator"] in selected_locators:
                        rows_to_select.append(row_index)
                del blocker
                for row_index in rows_to_select:
                    self.holds_table.selectRow(row_index)
            finally:
                self._syncing_table = False

        def _sync_from_controller(self):
            self.controls_line.setText(", ".join(_control_list_name(node_name) for node_name in self.controller.control_nodes))
            self.start_spin.blockSignals(True)
            self.end_spin.blockSignals(True)
            self.keep_rotation_check.blockSignals(True)
            self.hold_x_check.blockSignals(True)
            self.hold_y_check.blockSignals(True)
            self.hold_z_check.blockSignals(True)
            self.start_spin.setValue(int(self.controller.start_frame))
            self.end_spin.setValue(int(self.controller.end_frame))
            self.keep_rotation_check.setChecked(bool(self.controller.keep_rotation))
            hold_axes = set(_normalized_hold_axes(self.controller.hold_axes))
            self.hold_x_check.setChecked("x" in hold_axes)
            self.hold_y_check.setChecked("y" in hold_axes)
            self.hold_z_check.setChecked("z" in hold_axes)
            self.start_spin.blockSignals(False)
            self.end_spin.blockSignals(False)
            self.keep_rotation_check.blockSignals(False)
            self.hold_x_check.blockSignals(False)
            self.hold_y_check.blockSignals(False)
            self.hold_z_check.blockSignals(False)
            payload = self.controller.selected_hold_payload()
            if payload:
                self.list_name_line.setText(payload["list_name"])
            elif self.controller.control_nodes:
                self.list_name_line.setText(_control_list_name(self.controller.control_nodes[0]))
            else:
                self.list_name_line.clear()
            self._refresh_hold_table()
            self.report_box.setPlainText(self.controller.report_text())

        def _sync_to_controller(self):
            self.controller.start_frame = int(self.start_spin.value())
            self.controller.end_frame = int(self.end_spin.value())
            self.controller.keep_rotation = bool(self.keep_rotation_check.isChecked())
            axes = []
            if self.hold_x_check.isChecked():
                axes.append("x")
            if self.hold_y_check.isChecked():
                axes.append("y")
            if self.hold_z_check.isChecked():
                axes.append("z")
            self.controller.hold_axes = tuple(axes)

        def _on_hold_selection_changed(self):
            if self._syncing_table:
                return
            locator_nodes = self._selected_table_locators()
            self.controller.set_selected_hold_locators(locator_nodes)
            if len(locator_nodes) == 1:
                self.controller.load_selected_hold()
            self._sync_from_controller()

        def _load_picked_hold(self, *_args):
            locator_nodes = self._selected_table_locators()
            self.controller.set_selected_hold_locators(locator_nodes)
            success, message = self.controller.load_selected_hold()
            self._sync_from_controller()
            self._set_status(message, success)

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)
            self._refresh_hold_table()
            self.report_box.setPlainText(self.controller.report_text())

        def _use_selection(self):
            success, message = self.controller.set_controls_from_selection()
            self._sync_from_controller()
            self._set_status(message, success)

        def _add_other_side(self):
            success, message = self.controller.add_matching_other_side()
            self._sync_from_controller()
            self._set_status(message, success)

        def _rename_list_name(self):
            success, message = self.controller.set_control_list_name(self.list_name_line.text())
            self._sync_from_controller()
            self._set_status(message, success)

        def _use_start_frame(self):
            success, message = self.controller.set_start_from_current()
            self._sync_from_controller()
            self._set_status(message, success)

        def _use_end_frame(self):
            success, message = self.controller.set_end_from_current()
            self._sync_from_controller()
            self._set_status(message, success)

        def _suggest_range(self):
            self._sync_to_controller()
            success, message = self.controller.suggest_range()
            self._sync_from_controller()
            self._set_status(message, success)

        def _analyze(self):
            self._sync_to_controller()
            success, message = self.controller.analyze_setup()
            self._sync_from_controller()
            self._set_status(message, success)

        def _apply(self):
            self._sync_to_controller()
            success, message = self.controller.apply_hold()
            self._sync_from_controller()
            self._set_status(message, success)

        def _update_hold(self):
            self._sync_to_controller()
            success, message = self.controller.update_selected_hold()
            self._sync_from_controller()
            self._set_status(message, success)

        def _enable_hold(self):
            self._sync_to_controller()
            success, message = self.controller.enable_hold()
            self._sync_from_controller()
            self._set_status(message, success)

        def _disable_hold(self):
            self._sync_to_controller()
            success, message = self.controller.disable_hold()
            self._sync_from_controller()
            self._set_status(message, success)

        def _delete_hold(self):
            self._sync_to_controller()
            self.holds_table.clearSelection()
            success, message = self.controller.delete_hold()
            self._sync_from_controller()
            self._set_status(message, success)

        def _delete_all_holds(self):
            self._sync_to_controller()
            self.holds_table.clearSelection()
            success, message = self.controller.delete_all_holds()
            self._sync_from_controller()
            self._set_status(message, success)

        def _open_follow_url(self, *_args):
            _open_external_url(FOLLOW_AMIR_URL)

        def _open_donate_url(self):
            _open_external_url(DONATE_URL)


def _close_existing_window():
    global GLOBAL_WINDOW
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.close()
            GLOBAL_WINDOW.deleteLater()
        except Exception:
            pass
    GLOBAL_WINDOW = None
    if not QtWidgets:
        return
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    for widget in app.topLevelWidgets():
        try:
            if widget.objectName() == WINDOW_OBJECT_NAME:
                widget.close()
                widget.deleteLater()
        except Exception:
            pass


if QtWidgets:
    def _delete_workspace_control(name):
        if MAYA_AVAILABLE and cmds and cmds.workspaceControl(name, exists=True):
            cmds.deleteUI(name)


def launch_maya_contact_hold(dock=False):
    global GLOBAL_CONTROLLER, GLOBAL_WINDOW
    if not (MAYA_AVAILABLE and QtWidgets):
        raise RuntimeError("Maya Contact Hold must be launched inside Maya with PySide available.")

    _close_existing_window()
    if dock:
        _delete_workspace_control(WORKSPACE_CONTROL_NAME)

    GLOBAL_CONTROLLER = MayaContactHoldController()
    GLOBAL_WINDOW = MayaContactHoldWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "DONATE_URL",
    "FOLLOW_AMIR_URL",
    "MayaContactHoldController",
    "MayaContactHoldWindow",
    "launch_maya_contact_hold",
]
