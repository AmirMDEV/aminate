"""
maya_face_retarget.py

Simple control-based facial retargeter for Maya.

The workflow is intentionally direct:
- pick the source controls
- pick the target controls
- pair them by order
- retarget and bake onto the target controls

This tool stores its pair list inside the Maya file so the mapping can be
reopened and edited later without touching the source or target rigs.
The current workflow is simple on purpose:
- pick source controls
- pick target controls
- pair by order or by name
- edit any saved pair later from the quick pair editor
- bake onto target controls so the animator still edits controls instead of bones
"""

from __future__ import absolute_import, division, print_function

import json
import difflib
import math
import os
import re
import uuid

import maya_contact_hold as hold_utils

try:
    import maya.cmds as cmds
    import maya.OpenMayaUI as omui

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
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


WINDOW_OBJECT_NAME = "mayaFaceRetargetWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FACE_RETARGET_GROUP_NAME = "amirFaceRetarget_GRP"
FACE_RETARGET_MARKER_ATTR = "amirFaceRetargetMarker"
FACE_RETARGET_SOURCE_ATTR = "faceRetargetSource"
FACE_RETARGET_TARGET_ATTR = "faceRetargetTarget"
FACE_RETARGET_ENABLED_ATTR = "faceRetargetEnabled"
FACE_RETARGET_DATA_ATTR = "faceRetargetData"
DEFAULT_MAINTAIN_OFFSET = False
DEFAULT_FOLLOW_TRANSLATE = True
DEFAULT_FOLLOW_ROTATE = True
DEFAULT_REDUCE_KEYS = False
DEFAULT_VALUE_TOLERANCE = 0.01
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
PAIR_SOURCE_EDIT_LABEL = "Load Selected Source"
PAIR_TARGET_EDIT_LABEL = "Load Selected Target"
PAIR_APPLY_SOURCE_LABEL = "Set Selected Row Source"
PAIR_APPLY_TARGET_LABEL = "Set Selected Row Target"
PAIR_AUTO_MAP_LABEL = "Auto Map By Name"
PAIR_EDITOR_GROUP_LABEL = "Quick Pair Edit (Selected Pair Of Controls Only)"

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


def _screen_limited_size(preferred_width, preferred_height, min_width=420, min_height=360, margin=96):
    width = int(preferred_width)
    height = int(preferred_height)
    if not QtWidgets:
        return width, height
    try:
        app = QtWidgets.QApplication.instance()
        screen = None
        if app:
            if QtGui and hasattr(QtGui, "QCursor") and hasattr(app, "screenAt"):
                try:
                    screen = app.screenAt(QtGui.QCursor.pos())
                except Exception:
                    screen = None
            if screen is None and hasattr(app, "primaryScreen"):
                screen = app.primaryScreen()
        if screen and hasattr(screen, "availableGeometry"):
            geometry = screen.availableGeometry()
        elif app and hasattr(app, "desktop"):
            geometry = app.desktop().availableGeometry()
        else:
            return width, height
        available_width = max(int(min_width), int(geometry.width()) - int(margin))
        available_height = max(int(min_height), int(geometry.height()) - int(margin))
        return min(width, available_width), min(height, available_height)
    except Exception:
        return width, height


_SIDE_TOKEN_MIRRORS = {
    "left": "right",
    "right": "left",
    "l": "r",
    "r": "l",
    "lf": "rt",
    "rt": "lf",
}
_SIDE_TOKEN_NORMALS = {
    "left": "left",
    "l": "left",
    "lf": "left",
    "right": "right",
    "r": "right",
    "rt": "right",
}

_MATCH_IGNORE_TOKENS = {"ctrl", "ctl", "control", "controls", "source", "target", "src", "dst"}


def _scene_transform_candidates():
    if not MAYA_AVAILABLE or not cmds:
        return []
    ignored_names = {
        "persp",
        "top",
        "front",
        "side",
        "defaultLightSet",
        "defaultObjectSet",
        "initialShadingGroup",
        "initialParticleSE",
    }
    ignored_prefixes = (
        "UI",
        "shared",
        "characterThumbnail",
    )
    candidates = []
    for node_name in cmds.ls(type="transform", long=True) or []:
        short_name = _short_name(node_name)
        if not short_name or short_name in ignored_names:
            continue
        if any(short_name.startswith(prefix) for prefix in ignored_prefixes):
            continue
        candidates.append(_node_long_name(node_name))
    return _dedupe_preserve_order(candidates)


def _ensure_attr(node_name, attr_name, attr_type="string"):
    if cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return
    if attr_type == "string":
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
    elif attr_type == "bool":
        cmds.addAttr(node_name, longName=attr_name, attributeType="bool")
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


def _control_list_from_text(text_value):
    controls = []
    for line in (text_value or "").splitlines():
        for chunk in line.split(","):
            name = chunk.strip()
            if not name:
                continue
            if cmds.objExists(name):
                controls.append(_node_long_name(name))
    return _dedupe_preserve_order(controls)


def _controls_to_text(control_nodes):
    return "\n".join(_node_long_name(node_name) for node_name in control_nodes if node_name)


def _face_root(create=True):
    root_group = "|" + FACE_RETARGET_GROUP_NAME
    if cmds.objExists(root_group):
        return _node_long_name(root_group)
    if not create:
        return ""
    created = cmds.createNode("transform", name=FACE_RETARGET_GROUP_NAME)
    cmds.setAttr(created + ".visibility", 0)
    return _node_long_name(created)


def _record_name(source_node, target_node, suffix=None):
    safe_source = "".join(character if character.isalnum() else "_" for character in _short_name(source_node)).strip("_") or "source"
    safe_target = "".join(character if character.isalnum() else "_" for character in _short_name(target_node)).strip("_") or "target"
    parts = ["amirFaceRetarget", safe_source, safe_target]
    if suffix:
        parts.append(suffix)
    return "_".join(parts)


def _pair_record_payload(record_node):
    if not record_node or not cmds.objExists(record_node):
        return None
    payload = _load_json_attr(record_node, FACE_RETARGET_DATA_ATTR, {})
    source_node = _connected_source_node(record_node, FACE_RETARGET_SOURCE_ATTR) or payload.get("source", "")
    target_node = _connected_source_node(record_node, FACE_RETARGET_TARGET_ATTR) or payload.get("target", "")
    if source_node and not cmds.objExists(source_node):
        source_node = payload.get("source", "")
    if target_node and not cmds.objExists(target_node):
        target_node = payload.get("target", "")
    payload.update(
        {
            "record": _node_long_name(record_node),
            "source": _node_long_name(source_node) if source_node else "",
            "target": _node_long_name(target_node) if target_node else "",
            "enabled": _get_bool_attr(record_node, FACE_RETARGET_ENABLED_ATTR, bool(payload.get("enabled", True))),
            "maintain_offset": bool(payload.get("maintain_offset", DEFAULT_MAINTAIN_OFFSET)),
            "follow_translate": bool(payload.get("follow_translate", DEFAULT_FOLLOW_TRANSLATE)),
            "follow_rotate": bool(payload.get("follow_rotate", DEFAULT_FOLLOW_ROTATE)),
            "reduce_keys": bool(payload.get("reduce_keys", DEFAULT_REDUCE_KEYS)),
            "baked": bool(payload.get("baked", False)),
            "state": payload.get("state", "Saved"),
            "list_name": payload.get("list_name", "{0} -> {1}".format(_short_name(source_node), _short_name(target_node))),
            "source_label": payload.get("source_label", _short_name(source_node)),
            "target_label": payload.get("target_label", _short_name(target_node)),
            "notes": payload.get("notes", ""),
        }
    )
    return payload


def _set_pair_record_payload(record_node, payload):
    payload = dict(payload or {})
    payload.setdefault("enabled", True)
    payload.setdefault("maintain_offset", DEFAULT_MAINTAIN_OFFSET)
    payload.setdefault("follow_translate", DEFAULT_FOLLOW_TRANSLATE)
    payload.setdefault("follow_rotate", DEFAULT_FOLLOW_ROTATE)
    payload.setdefault("reduce_keys", DEFAULT_REDUCE_KEYS)
    payload.setdefault("baked", False)
    payload.setdefault("state", "Saved")
    payload.setdefault("notes", "")
    payload.setdefault("source_label", _short_name(payload.get("source", "")) if payload.get("source") else "")
    payload.setdefault("target_label", _short_name(payload.get("target", "")) if payload.get("target") else "")
    payload.setdefault("list_name", "{0} -> {1}".format(payload.get("source_label", "Source"), payload.get("target_label", "Target")))
    _store_json_attr(record_node, FACE_RETARGET_DATA_ATTR, payload)


def _all_pair_records():
    root_group = _face_root(create=False)
    if not root_group:
        return []
    children = cmds.listRelatives(root_group, children=True, type="transform", fullPath=True) or []
    return [_node_long_name(item) for item in children if _get_bool_attr(item, FACE_RETARGET_MARKER_ATTR, False)]


def _find_pair_record(source_node, target_node):
    source_long = _node_long_name(source_node)
    target_long = _node_long_name(target_node)
    for record_node in _all_pair_records():
        payload = _pair_record_payload(record_node)
        if not payload:
            continue
        if payload.get("source") == source_long and payload.get("target") == target_long:
            return record_node
    return ""


def _delete_record(record_node):
    if record_node and cmds.objExists(record_node):
        try:
            cmds.delete(record_node)
            return True
        except Exception:
            return False
    return False


def _playback_range():
    start_time = float(cmds.playbackOptions(query=True, minTime=True))
    end_time = float(cmds.playbackOptions(query=True, maxTime=True))
    return start_time, end_time


def _frame_label(frame_value):
    frame_value = float(frame_value)
    if abs(frame_value - round(frame_value)) < 1.0e-3:
        return str(int(round(frame_value)))
    return "{0:.2f}".format(frame_value).rstrip("0").rstrip(".")


def _bake_attributes(payload):
    attrs = []
    if payload.get("follow_translate", DEFAULT_FOLLOW_TRANSLATE):
        attrs.extend(["translateX", "translateY", "translateZ"])
    if payload.get("follow_rotate", DEFAULT_FOLLOW_ROTATE):
        attrs.extend(["rotateX", "rotateY", "rotateZ"])
    return attrs


def _create_or_update_pair(source_node, target_node, payload):
    root_group = _face_root(create=True)
    existing = _find_pair_record(source_node, target_node)
    if existing:
        record_node = existing
    else:
        record_node = cmds.createNode("transform", name=_record_name(source_node, target_node, uuid.uuid4().hex[:8]), parent=root_group)
        record_node = _node_long_name(record_node)
        cmds.setAttr(record_node + ".visibility", 0)
        _set_bool_attr(record_node, FACE_RETARGET_MARKER_ATTR, True)
        _set_bool_attr(record_node, FACE_RETARGET_ENABLED_ATTR, True)
        _ensure_message_attr(record_node, FACE_RETARGET_SOURCE_ATTR)
        _ensure_message_attr(record_node, FACE_RETARGET_TARGET_ATTR)
    _connect_message(source_node, record_node, FACE_RETARGET_SOURCE_ATTR)
    _connect_message(target_node, record_node, FACE_RETARGET_TARGET_ATTR)
    _set_bool_attr(record_node, FACE_RETARGET_ENABLED_ATTR, True)
    _set_pair_record_payload(record_node, payload)
    return record_node


def _pair_summary(payload):
    source_label = payload.get("source_label") or _short_name(payload.get("source", "")) or "Source"
    target_label = payload.get("target_label") or _short_name(payload.get("target", "")) or "Target"
    mode = []
    if payload.get("follow_translate"):
        mode.append("T")
    if payload.get("follow_rotate"):
        mode.append("R")
    return "{0} -> {1} ({2})".format(source_label, target_label, "".join(mode) or "-")


def _match_tokens(node_name):
    short_name = _short_name(node_name).replace("|", " ").replace(":", " ")
    short_name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", short_name)
    short_name = re.sub(r"[^a-zA-Z0-9]+", " ", short_name).lower()
    return [token for token in short_name.split() if token]


def _match_core_tokens(tokens):
    return [token for token in tokens if token not in _MATCH_IGNORE_TOKENS]


def _mirror_match_tokens(tokens):
    return [_SIDE_TOKEN_MIRRORS.get(token, token) for token in tokens]


def _match_string(node_name):
    return " ".join(_match_core_tokens(_match_tokens(node_name)))


def _mirrored_match_string(node_name):
    return " ".join(_match_core_tokens(_mirror_match_tokens(_match_tokens(node_name))))


def _side_token(node_name):
    for token in _match_tokens(node_name):
        if token in _SIDE_TOKEN_MIRRORS:
            return token
    return ""


def _normal_side_token(node_name):
    return _SIDE_TOKEN_NORMALS.get(_side_token(node_name), "")


def _name_match_score(source_node, target_node):
    source_normal = _match_string(source_node)
    target_normal = _match_string(target_node)
    mirrored_source = _mirrored_match_string(source_node)
    score = difflib.SequenceMatcher(None, mirrored_source, target_normal).ratio()
    score = max(score, difflib.SequenceMatcher(None, source_normal, target_normal).ratio() * 0.85)
    source_side = _normal_side_token(source_node)
    target_side = _normal_side_token(target_node)
    if source_side and target_side and source_side == target_side:
        score += 0.2
    elif source_side and target_side:
        score -= 0.15
    source_core = " ".join(_match_core_tokens(_match_tokens(source_node)))
    target_core = " ".join(_match_core_tokens(_match_tokens(target_node)))
    if source_core and source_core == target_core:
        score += 0.25
    if _short_name(source_node).lower() == _short_name(target_node).lower():
        score += 0.35
    return min(score, 1.0)


def _fast_match_key(node_name):
    return "".join(_match_core_tokens(_mirror_match_tokens(_match_tokens(node_name))))


def _normal_match_key(node_name):
    return "".join(_match_core_tokens(_match_tokens(node_name)))


def _source_key_times(source_node):
    times = cmds.keyframe(source_node, query=True, timeChange=True) or []
    rounded = []
    for time_value in times:
        rounded_time = int(round(float(time_value)))
        if rounded_time not in rounded:
            rounded.append(rounded_time)
    return sorted(rounded)


def _reduce_target_keys_to_source_times(source_node, target_node, bake_attrs, start_time, end_time):
    keep_times = set(_source_key_times(source_node))
    if not keep_times:
        return
    for attr_name in bake_attrs:
        target_times = cmds.keyframe(target_node, attribute=attr_name, query=True, timeChange=True) or []
        for time_value in target_times:
            rounded_time = int(round(float(time_value)))
            if rounded_time in keep_times:
                if abs(float(time_value) - float(rounded_time)) <= 1.0e-3:
                    continue
                try:
                    cmds.keyframe(
                        target_node,
                        attribute=attr_name,
                        edit=True,
                        time=(float(time_value), float(time_value)),
                        relative=True,
                        timeChange=float(rounded_time) - float(time_value),
                    )
                except Exception:
                    pass
                continue
            if float(start_time) - 1.0e-3 <= float(time_value) <= float(end_time) + 1.0e-3:
                try:
                    cmds.cutKey(target_node, attribute=attr_name, time=(float(time_value), float(time_value)), clear=True)
                except Exception:
                    pass


def _bake_sample_times(start_time, end_time):
    if abs(float(start_time) - float(end_time)) <= 1.0e-3:
        return [float(start_time)]
    first_frame = int(math.floor(float(start_time) + 0.0001))
    last_frame = int(math.ceil(float(end_time) - 0.0001))
    return [float(frame_value) for frame_value in range(first_frame, last_frame + 1)]


class FaceRetargetController(object):
    def __init__(self):
        self.source_nodes = []
        self.target_nodes = []
        self.selected_records = []
        self.maintain_offset = DEFAULT_MAINTAIN_OFFSET
        self.follow_translate = DEFAULT_FOLLOW_TRANSLATE
        self.follow_rotate = DEFAULT_FOLLOW_ROTATE
        self.reduce_keys = DEFAULT_REDUCE_KEYS
        self.value_tolerance = DEFAULT_VALUE_TOLERANCE
        self.report = {}

    def _pair_payload_for_nodes(self, source_node, target_node):
        payload = _pair_record_payload(_find_pair_record(source_node, target_node)) or {}
        payload.update(
            {
                "source": _node_long_name(source_node),
                "target": _node_long_name(target_node),
                "enabled": True,
                "maintain_offset": bool(self.maintain_offset),
                "follow_translate": bool(self.follow_translate),
                "follow_rotate": bool(self.follow_rotate),
                "reduce_keys": bool(self.reduce_keys),
                "state": "Saved",
                "baked": False,
                "source_label": _short_name(source_node),
                "target_label": _short_name(target_node),
                "list_name": "{0} -> {1}".format(_short_name(source_node), _short_name(target_node)),
            }
        )
        return payload

    def set_source_from_selection(self):
        self.source_nodes = _selected_controls()
        if not self.source_nodes:
            return False, "Pick the source controls first."
        return True, "Stored {0} source control(s).".format(len(self.source_nodes))

    def set_target_from_selection(self):
        self.target_nodes = _selected_controls()
        if not self.target_nodes:
            return False, "Pick the target controls first."
        return True, "Stored {0} target control(s).".format(len(self.target_nodes))

    def remove_source_from_selection(self):
        selected_nodes = _selected_controls()
        if not selected_nodes:
            return False, "Pick one or more source controls in the scene first."
        selected_nodes = _dedupe_preserve_order(_node_long_name(node_name) for node_name in selected_nodes if node_name)
        remaining = [node_name for node_name in self.source_nodes if node_name not in selected_nodes]
        removed_count = len(self.source_nodes) - len(remaining)
        if removed_count <= 0:
            return False, "The selected control(s) were not in the source list."
        self.source_nodes = remaining
        return True, "Removed {0} source control(s).".format(removed_count)

    def remove_target_from_selection(self):
        selected_nodes = _selected_controls()
        if not selected_nodes:
            return False, "Pick one or more target controls in the scene first."
        selected_nodes = _dedupe_preserve_order(_node_long_name(node_name) for node_name in selected_nodes if node_name)
        remaining = [node_name for node_name in self.target_nodes if node_name not in selected_nodes]
        removed_count = len(self.target_nodes) - len(remaining)
        if removed_count <= 0:
            return False, "The selected control(s) were not in the target list."
        self.target_nodes = remaining
        return True, "Removed {0} target control(s).".format(removed_count)

    def update_selected_pair(self, source_node=None, target_node=None):
        if not self.selected_records:
            return False, "Pick a saved control pair row first."
        payload = self.selected_record_payload()
        if not payload:
            return False, "Pick a saved control pair row first."
        source_value = _node_long_name(source_node or payload.get("source", ""))
        target_value = _node_long_name(target_node or payload.get("target", ""))
        if not source_value or not target_value:
            return False, "Pick a valid source and target control first."
        if not cmds.objExists(source_value) or not cmds.objExists(target_value):
            return False, "The chosen source or target control no longer exists."
        record_node = payload["record"]
        payload.update(
            {
                "source": source_value,
                "target": target_value,
                "source_label": _short_name(source_value),
                "target_label": _short_name(target_value),
                "list_name": "{0} -> {1}".format(_short_name(source_value), _short_name(target_value)),
                "state": "Saved",
                "baked": False,
                "enabled": True,
            }
        )
        _connect_message(source_value, record_node, FACE_RETARGET_SOURCE_ATTR)
        _connect_message(target_value, record_node, FACE_RETARGET_TARGET_ATTR)
        _set_bool_attr(record_node, FACE_RETARGET_ENABLED_ATTR, True)
        _set_pair_record_payload(record_node, payload)
        self.set_selected_records([record_node])
        self.analyze_setup()
        return True, "Updated the selected control pair."

    def update_selected_pair_source_from_selection(self):
        selected_nodes = _selected_controls()
        if not selected_nodes:
            return False, "Pick the new source control in the scene first."
        source_value = _node_long_name(selected_nodes[0])
        if source_value not in self.source_nodes:
            self.source_nodes = _dedupe_preserve_order(list(self.source_nodes) + [source_value])
        return self.update_selected_pair(source_node=source_value)

    def update_selected_pair_target_from_selection(self):
        selected_nodes = _selected_controls()
        if not selected_nodes:
            return False, "Pick the new target control in the scene first."
        target_value = _node_long_name(selected_nodes[0])
        if target_value not in self.target_nodes:
            self.target_nodes = _dedupe_preserve_order(list(self.target_nodes) + [target_value])
        return self.update_selected_pair(target_node=target_value)

    def set_selected_records(self, record_nodes):
        self.selected_records = _dedupe_preserve_order([
            _node_long_name(node_name)
            for node_name in (record_nodes or [])
            if node_name and cmds.objExists(node_name)
        ])

    def selected_record_payload(self):
        record_nodes = self.selected_records or _all_pair_records()
        if not record_nodes:
            return None
        return _pair_record_payload(record_nodes[0])

    def load_selected_pair(self):
        payload = self.selected_record_payload()
        if not payload:
            return False, "Pick a saved pair first."
        self.source_nodes = [payload.get("source", "")] if payload.get("source") else []
        self.target_nodes = [payload.get("target", "")] if payload.get("target") else []
        self.maintain_offset = bool(payload.get("maintain_offset", self.maintain_offset))
        self.follow_translate = bool(payload.get("follow_translate", self.follow_translate))
        self.follow_rotate = bool(payload.get("follow_rotate", self.follow_rotate))
        self.reduce_keys = bool(payload.get("reduce_keys", self.reduce_keys))
        return True, "Loaded {0}.".format(payload.get("list_name", "the selected pair"))

    def pair_entries(self, from_selection=False):
        records = self.selected_records if from_selection and self.selected_records else _all_pair_records()
        entries = []
        for record_node in records:
            payload = _pair_record_payload(record_node)
            if payload:
                entries.append(payload)
        return entries

    def analyze_setup(self):
        entries = self.pair_entries(from_selection=False)
        report = {
            "sources": list(self.source_nodes),
            "targets": list(self.target_nodes),
            "pairs": len(entries),
            "warnings": [],
            "errors": [],
            "entries": entries,
        }
        if not self.source_nodes:
            report["errors"].append("No source controls are loaded yet.")
        if not self.target_nodes:
            report["errors"].append("No target controls are loaded yet.")
        if self.source_nodes and self.target_nodes and len(self.source_nodes) != len(self.target_nodes):
            report["warnings"].append("Source and target counts do not match. Pair By Order will use the shortest list.")
        if not entries:
            report["warnings"].append("No saved control pairs are in the scene yet.")
        for payload in entries:
            if not payload.get("source") or not payload.get("target"):
                report["errors"].append("A saved control pair is missing its source or target.")
            if payload.get("source") == payload.get("target"):
                report["warnings"].append("{0} is mapped to itself.".format(payload.get("list_name", "A control pair")))
        self.report = report
        if report["errors"]:
            return False, "Check Setup found a problem."
        if report["warnings"]:
            return True, "Check Setup finished with a warning."
        return True, "Check Setup says the face retarget control pairs look ready."

    def _pair_count_message(self, count, extra_message=""):
        if extra_message:
            return "Saved {0} control pair(s). {1}".format(count, extra_message)
        return "Saved {0} control pair(s).".format(count)

    def upsert_pair(self, source_node, target_node):
        source_node = _node_long_name(source_node or "")
        target_node = _node_long_name(target_node or "")
        if not source_node or not target_node:
            return False, "Pick both a source control and a target control."
        if not cmds.objExists(source_node) or not cmds.objExists(target_node):
            return False, "The chosen source or target control no longer exists."
        payload = self._pair_payload_for_nodes(source_node, target_node)
        record_node = _create_or_update_pair(source_node, target_node, payload)
        self.source_nodes = _dedupe_preserve_order(list(self.source_nodes) + [source_node])
        self.target_nodes = _dedupe_preserve_order(list(self.target_nodes) + [target_node])
        self.set_selected_records([record_node])
        self.analyze_setup()
        return True, "Saved control pair: {0} -> {1}.".format(_short_name(source_node), _short_name(target_node))

    def pair_by_order(self):
        if not self.source_nodes:
            return False, "Pick the source controls first."
        if not self.target_nodes:
            return False, "Pick the target controls first."
        if not self.follow_translate and not self.follow_rotate:
            return False, "Turn on Follow Translation or Follow Rotation first."
        pair_count = min(len(self.source_nodes), len(self.target_nodes))
        if pair_count <= 0:
            return False, "Nothing to pair."
        extra_message = ""
        if len(self.source_nodes) != len(self.target_nodes):
            extra_message = "The longer list was trimmed to the first {0} item(s).".format(pair_count)
        paired_records = []
        for source_node, target_node in zip(self.source_nodes[:pair_count], self.target_nodes[:pair_count]):
            if not cmds.objExists(source_node) or not cmds.objExists(target_node):
                continue
            payload = self._pair_payload_for_nodes(source_node, target_node)
            record_node = _create_or_update_pair(source_node, target_node, payload)
            paired_records.append(record_node)
        self.set_selected_records(paired_records)
        self.analyze_setup()
        return True, self._pair_count_message(len(paired_records), extra_message)

    def pair_by_name(self):
        if not self.source_nodes:
            return False, "Pick the source controls first."
        if not self.target_nodes:
            return False, "Pick the target controls first."
        if not self.follow_translate and not self.follow_rotate:
            return False, "Turn on Follow Translation or Follow Rotation first."
        available_targets = [_node_long_name(node_name) for node_name in self.target_nodes if node_name and cmds.objExists(node_name)]
        if not available_targets:
            return False, "No valid target controls were found."
        paired_records = []
        skipped_sources = 0
        used_targets = set()
        target_key_map = {}
        target_mirror_key_map = {}
        for target_node in available_targets:
            normal_key = _normal_match_key(target_node)
            mirror_key = _fast_match_key(target_node)
            if normal_key and normal_key not in target_key_map:
                target_key_map[normal_key] = target_node
            if mirror_key and mirror_key not in target_mirror_key_map:
                target_mirror_key_map[mirror_key] = target_node
        for source_node in [_node_long_name(node_name) for node_name in self.source_nodes if node_name and cmds.objExists(node_name)]:
            best_target = ""
            best_score = 0.0
            normal_key = _normal_match_key(source_node)
            candidate = target_key_map.get(normal_key, "")
            if candidate and candidate not in used_targets:
                best_target = candidate
                best_score = 1.0
            if not best_target:
                mirror_key = _fast_match_key(source_node)
                candidate = target_mirror_key_map.get(mirror_key, "")
                if candidate and candidate not in used_targets:
                    best_target = candidate
                    best_score = 0.82
            if not best_target:
                source_tokens = set(_match_core_tokens(_match_tokens(source_node)))
                for target_node in available_targets:
                    if target_node in used_targets:
                        continue
                    target_tokens = set(_match_core_tokens(_match_tokens(target_node)))
                    if source_tokens and target_tokens and not (source_tokens & target_tokens):
                        continue
                    score = _name_match_score(source_node, target_node)
                    if score > best_score:
                        best_score = score
                        best_target = target_node
            if not best_target or best_score < 0.45:
                skipped_sources += 1
                continue
            payload = self._pair_payload_for_nodes(source_node, best_target)
            record_node = _create_or_update_pair(source_node, best_target, payload)
            paired_records.append(record_node)
            used_targets.add(best_target)
        if not paired_records:
            return False, "Auto Map By Name could not find any reliable matches."
        self.set_selected_records(paired_records)
        self.analyze_setup()
        message = self._pair_count_message(len(paired_records), "Matched control names by name.")
        if skipped_sources:
            message += " {0} source control(s) did not find a confident match.".format(skipped_sources)
        return True, message

    auto_pair_by_name = pair_by_name

    def _key_range_from_nodes(self, node_names):
        times = []
        for node_name in _dedupe_preserve_order([_node_long_name(node) for node in node_names if node and cmds.objExists(node)]):
            node_times = cmds.keyframe(node_name, query=True, timeChange=True) or []
            times.extend(float(time_value) for time_value in node_times)
        if not times:
            return _playback_range()
        start_time = min(times)
        end_time = max(times)
        if abs(start_time - end_time) < 1.0e-3:
            return start_time, end_time
        return math.floor(start_time + 0.0001), math.ceil(end_time - 0.0001)

    def _round_key_times_to_whole_frames(self, target_nodes, bake_attrs, start_time, end_time):
        for target_node in target_nodes:
            for attr_name in bake_attrs:
                key_times = cmds.keyframe(target_node, attribute=attr_name, query=True, timeChange=True) or []
                for time_value in key_times:
                    rounded_time = int(round(float(time_value)))
                    if abs(float(time_value) - float(rounded_time)) <= 1.0e-3:
                        continue
                    try:
                        cmds.keyframe(
                            target_node,
                            attribute=attr_name,
                            edit=True,
                            time=(float(time_value), float(time_value)),
                            relative=True,
                            timeChange=float(rounded_time) - float(time_value),
                        )
                    except Exception:
                        pass

    def retarget_selected_pairs(self):
        if not self.selected_records:
            return False, "Pick one or more control pair rows first."
        return self.retarget_and_bake(records=list(self.selected_records), action_label="selected")

    def retarget_selected_controls(self):
        return self.retarget_selected_pairs()

    def retarget_all_pairs(self):
        return self.retarget_and_bake(records=_all_pair_records(), action_label="all")

    def retarget_all_controls(self):
        return self.retarget_all_pairs()

    def delete_selected(self):
        record_nodes = self.selected_records or []
        if not record_nodes:
            return False, "Pick a saved control pair row first."
        deleted = 0
        for record_node in list(record_nodes):
            if _delete_record(record_node):
                deleted += 1
        self.selected_records = []
        self.analyze_setup()
        return True, "Deleted {0} saved control pair(s).".format(deleted)

    def delete_all(self):
        record_nodes = _all_pair_records()
        if not record_nodes:
            return False, "There are no saved control pairs to delete."
        deleted = 0
        for record_node in list(record_nodes):
            if _delete_record(record_node):
                deleted += 1
        self.selected_records = []
        self.analyze_setup()
        return True, "Deleted all {0} saved control pair(s).".format(deleted)

    def retarget_and_bake(self, records=None, action_label="selected"):
        records = list(records or (self.selected_records or _all_pair_records()))
        if not records:
            return False, "Pair the source and target controls first."
        entries = []
        for record_node in records:
            payload = _pair_record_payload(record_node)
            if not payload:
                continue
            if not payload.get("source") or not payload.get("target"):
                continue
            if not cmds.objExists(payload["source"]) or not cmds.objExists(payload["target"]):
                continue
            entries.append(payload)
        if not entries:
            return False, "No valid control pair rows were found."
        if not self.follow_translate and not self.follow_rotate:
            return False, "Turn on Follow Translation or Follow Rotation first."

        start_time, end_time = self._key_range_from_nodes([payload["source"] for payload in entries])
        if not entries or start_time is None or end_time is None:
            start_time, end_time = _playback_range()
        target_nodes = []
        bake_attrs = _bake_attributes({"follow_translate": self.follow_translate, "follow_rotate": self.follow_rotate})
        if not bake_attrs:
            return False, "There are no channels to bake."

        original_time = None
        try:
            cmds.undoInfo(openChunk=True)
        except Exception:
            pass

        try:
            try:
                original_time = float(cmds.currentTime(query=True))
            except Exception:
                original_time = None
            for payload in entries:
                source_node = payload["source"]
                target_node = payload["target"]
                target_nodes.append(target_node)
                source_start_time, _source_end_time = self._key_range_from_nodes([source_node])
                if source_start_time is None:
                    source_start_time = start_time
                cmds.currentTime(source_start_time, edit=True)
                baselines = {}
                for attr_name in bake_attrs:
                    source_attr = "{0}.{1}".format(source_node, attr_name)
                    target_attr = "{0}.{1}".format(target_node, attr_name)
                    if not cmds.objExists(source_attr) or not cmds.objExists(target_attr):
                        continue
                    try:
                        baselines[attr_name] = (
                            float(cmds.getAttr(source_attr)),
                            float(cmds.getAttr(target_attr)),
                        )
                    except Exception:
                        continue
                if source_node != target_node:
                    for attr_name in baselines:
                        try:
                            cmds.cutKey(target_node, attribute=attr_name, time=(start_time, end_time), clear=True)
                        except Exception:
                            pass
                for time_value in _bake_sample_times(start_time, end_time):
                    cmds.currentTime(time_value, edit=True)
                    for attr_name, baseline in baselines.items():
                        source_start_value, target_start_value = baseline
                        try:
                            source_value = float(cmds.getAttr("{0}.{1}".format(source_node, attr_name)))
                        except Exception:
                            continue
                        if self.maintain_offset:
                            target_value = target_start_value + (source_value - source_start_value)
                        else:
                            target_value = source_value
                        try:
                            cmds.setKeyframe(target_node, attribute=attr_name, time=time_value, value=target_value)
                        except Exception:
                            pass

            if self.reduce_keys:
                for payload in entries:
                    _reduce_target_keys_to_source_times(
                        payload["source"],
                        payload["target"],
                        bake_attrs,
                        start_time,
                        end_time,
                    )
            self._round_key_times_to_whole_frames(target_nodes, bake_attrs, start_time, end_time)

            for record_node in records:
                payload = _pair_record_payload(record_node)
                if not payload:
                    continue
                payload["baked"] = True
                payload["state"] = "Baked"
                _set_pair_record_payload(record_node, payload)

            self.analyze_setup()
            return True, "Baked {0} control pair(s) onto the target controls from frames {1} to {2}.".format(
                len(target_nodes),
                _frame_label(start_time),
                _frame_label(end_time),
            )
        except Exception as exc:
            return False, "Retarget and bake failed: {0}".format(exc)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
            if original_time is not None:
                try:
                    cmds.currentTime(original_time, edit=True)
                except Exception:
                    pass

    def shutdown(self):
        self.source_nodes = []
        self.target_nodes = []
        self.selected_records = []
        self.report = {}


MayaFaceRetargetController = FaceRetargetController


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

        if MQtUtil.mainWindow() is not None:
            _WindowBase = type("MayaFaceRetargetWindowBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
        else:
            _WindowBase = type("MayaFaceRetargetWindowBase", (QtWidgets.QDialog,), {})
    except Exception:
        _WindowBase = type("MayaFaceRetargetWindowBase", (QtWidgets.QDialog,), {})


    class MayaFaceRetargetWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaFaceRetargetWindow, self).__init__(parent)
            self.controller = controller
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Controls Retargeter (Face and Body)")
            self.setMinimumSize(420, 360)
            start_width, start_height = _screen_limited_size(900, 860, min_width=420, min_height=360)
            self.resize(start_width, start_height)
            if hasattr(self, "setSizePolicy"):
                self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self._build_ui()
            self._refresh_table()
            self._sync_from_controller()

        def _build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.setContentsMargins(12, 12, 12, 12)
            main_layout.setSpacing(10)

            intro_group = QtWidgets.QGroupBox("How To Use")
            intro_layout = QtWidgets.QVBoxLayout(intro_group)
            intro = QtWidgets.QLabel(
                "Put a source control on the left and its target control on the right. Each completed row becomes one retarget pair. Empty rows are ignored.\n"
                "Use Auto Map By Name for fast name matching, or fill rows manually from Maya selection.\n"
                "Click Retarget All Controls to bake source motion onto the target controls. Reduce Keys keeps only the original source keyframes."
            )
            intro.setWordWrap(True)
            intro_layout.addWidget(intro)
            main_layout.addWidget(intro_group)

            pair_map_group = QtWidgets.QGroupBox("Control Pairs")
            pair_map_layout = QtWidgets.QVBoxLayout(pair_map_group)
            pair_map_hint = QtWidgets.QLabel(
                "Each row is one source control paired to one target control. Pick controls into the boxes, or type names. A blank row is always added automatically and is ignored by Retarget."
            )
            pair_map_hint.setWordWrap(True)
            pair_map_layout.addWidget(pair_map_hint)
            self.pair_rows_layout = QtWidgets.QVBoxLayout()
            self.pair_rows_layout.setSpacing(8)
            pair_map_layout.addLayout(self.pair_rows_layout)
            load_row = QtWidgets.QHBoxLayout()
            self.use_source_button = QtWidgets.QPushButton("Load Selected Sources")
            self.use_source_button.setToolTip("Load the selected controls down the left side of the pair rows.")
            self.use_target_button = QtWidgets.QPushButton("Load Selected Targets")
            self.use_target_button.setToolTip("Load the selected controls down the right side of the pair rows.")
            self.remove_source_button = QtWidgets.QPushButton("Clear Sources")
            self.remove_target_button = QtWidgets.QPushButton("Clear Targets")
            load_row.addWidget(self.use_source_button)
            load_row.addWidget(self.use_target_button)
            load_row.addWidget(self.remove_source_button)
            load_row.addWidget(self.remove_target_button)
            pair_map_layout.addLayout(load_row)
            main_layout.addWidget(pair_map_group)

            self.source_box = QtWidgets.QPlainTextEdit()
            self.source_box.hide()
            self.target_box = QtWidgets.QPlainTextEdit()
            self.target_box.hide()
            self.pair_row_widgets = []

            options_row = QtWidgets.QHBoxLayout()
            self.maintain_offset_check = QtWidgets.QCheckBox("Keep Target Offset")
            self.maintain_offset_check.setChecked(DEFAULT_MAINTAIN_OFFSET)
            self.maintain_offset_check.setToolTip(
                "Off by default: target controls receive the source channel values directly. "
                "Turn on only when you want to preserve the target control's starting offset from the source."
            )
            self.follow_translate_check = QtWidgets.QCheckBox("Follow Translation")
            self.follow_translate_check.setChecked(DEFAULT_FOLLOW_TRANSLATE)
            self.follow_rotate_check = QtWidgets.QCheckBox("Follow Rotation")
            self.follow_rotate_check.setChecked(DEFAULT_FOLLOW_ROTATE)
            self.reduce_keys_check = QtWidgets.QCheckBox("Reduce Keys After Bake")
            self.reduce_keys_check.setChecked(DEFAULT_REDUCE_KEYS)
            options_row.addWidget(self.maintain_offset_check)
            options_row.addWidget(self.follow_translate_check)
            options_row.addWidget(self.follow_rotate_check)
            options_row.addWidget(self.reduce_keys_check)
            options_row.addStretch(1)
            main_layout.addLayout(options_row)

            action_row = QtWidgets.QHBoxLayout()
            self.pair_button = QtWidgets.QPushButton("Pair By Order")
            self.auto_map_button = QtWidgets.QPushButton("Auto Map By Name")
            self.check_button = QtWidgets.QPushButton("Check Setup")
            self.retarget_selected_button = QtWidgets.QPushButton("Retarget Selected Controls")
            self.retarget_all_button = QtWidgets.QPushButton("Retarget All Controls")
            self.bake_button = self.retarget_selected_button
            self.pair_button.setToolTip("Create or update saved pair of controls in the same order: source 1 to target 1, source 2 to target 2, and so on.")
            self.auto_map_button.setToolTip("Create or update saved pair of controls by loose name matching, like left eyebrow to right eyebrow, even if the rig names are not identical.")
            self.check_button.setToolTip("Check the current source list, target list, and saved control pairs.")
            self.retarget_selected_button.setToolTip("Bake the selected control pair row from the source controls onto the target controls.")
            self.retarget_all_button.setToolTip("Bake every saved control pair from the source controls onto the target controls.")
            action_row.addWidget(self.auto_map_button)
            main_layout.addLayout(action_row)

            retarget_row = QtWidgets.QHBoxLayout()
            retarget_row.addWidget(self.retarget_all_button)
            main_layout.addLayout(retarget_row)
            self.pair_button.hide()
            self.check_button.hide()
            self.retarget_selected_button.hide()

            quick_group = QtWidgets.QGroupBox(PAIR_EDITOR_GROUP_LABEL)
            quick_layout = QtWidgets.QVBoxLayout(quick_group)
            quick_hint = QtWidgets.QLabel(
                "Pick a saved pair of controls first. Quick Pair Edit only changes that selected row.\n"
                "The drop-downs list scene controls and also keep the loaded source and target lists handy.\n"
                "Pair By Order maps source item 1 to target item 1, source item 2 to target item 2, and so on."
            )
            quick_hint.setWordWrap(True)
            quick_layout.addWidget(quick_hint)
            self.quick_pair_group = quick_group

            source_edit_row = QtWidgets.QHBoxLayout()
            source_label = QtWidgets.QLabel("Source Control")
            self.pair_source_combo = QtWidgets.QComboBox()
            self.pair_source_combo.setEditable(True)
            self.pair_source_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
            self.pair_source_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.pair_source_combo.setMinimumContentsLength(14)
            self.apply_source_button = QtWidgets.QPushButton(PAIR_APPLY_SOURCE_LABEL)
            self.apply_source_button.setToolTip("Set the selected saved pair of controls row's source to the chosen scene control from the drop-down.")
            source_edit_row.addWidget(source_label)
            source_edit_row.addWidget(self.pair_source_combo, 1)
            source_edit_row.addWidget(self.apply_source_button)
            quick_layout.addLayout(source_edit_row)

            target_edit_row = QtWidgets.QHBoxLayout()
            target_label = QtWidgets.QLabel("Target Control")
            self.pair_target_combo = QtWidgets.QComboBox()
            self.pair_target_combo.setEditable(True)
            self.pair_target_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
            self.pair_target_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.pair_target_combo.setMinimumContentsLength(14)
            self.apply_target_button = QtWidgets.QPushButton(PAIR_APPLY_TARGET_LABEL)
            self.apply_target_button.setToolTip("Set the selected saved pair of controls row's target to the chosen scene control from the drop-down.")
            target_edit_row.addWidget(target_label)
            target_edit_row.addWidget(self.pair_target_combo, 1)
            target_edit_row.addWidget(self.apply_target_button)
            quick_layout.addLayout(target_edit_row)

            main_layout.addWidget(quick_group)
            quick_group.hide()

            pair_group = QtWidgets.QGroupBox("Saved Pair Of Controls In Scene")
            pair_layout = QtWidgets.QVBoxLayout(pair_group)
            self.pairs_table = QtWidgets.QTableWidget(0, 4)
            self.pairs_table.setHorizontalHeaderLabels(["Source", "Target", "Mode", "State"])
            self.pairs_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.pairs_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.pairs_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.pairs_table.setAlternatingRowColors(True)
            header = self.pairs_table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
            pair_layout.addWidget(self.pairs_table, 1)

            manage_row = QtWidgets.QHBoxLayout()
            self.load_pair_button = QtWidgets.QPushButton("Load Selected Pair Of Controls")
            self.delete_pair_button = QtWidgets.QPushButton("Delete Selected Pair Of Controls")
            self.delete_all_button = QtWidgets.QPushButton("Delete All Pair Of Controls")
            self.load_pair_button.setToolTip("Load the selected saved pair of controls row into the Source and Target lists.")
            self.delete_pair_button.setToolTip("Remove the selected saved pair of controls row from the scene.")
            self.delete_all_button.setToolTip("Remove every saved face pair of controls from the scene.")
            manage_row.addWidget(self.load_pair_button)
            manage_row.addWidget(self.delete_pair_button)
            manage_row.addWidget(self.delete_all_button)
            pair_layout.addLayout(manage_row)
            main_layout.addWidget(pair_group, 1)
            pair_group.hide()

            self.report_box = QtWidgets.QPlainTextEdit()
            self.report_box.setReadOnly(True)
            self.report_box.setToolTip("Simple feedback about the current source list, target list, and saved control pairs.")
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

            self.use_source_button.clicked.connect(self._use_selected_source)
            self.remove_source_button.clicked.connect(self._remove_selected_source)
            self.use_target_button.clicked.connect(self._use_selected_target)
            self.remove_target_button.clicked.connect(self._remove_selected_target)
            self.pair_button.clicked.connect(self._pair_by_order)
            self.auto_map_button.clicked.connect(self._pair_by_name)
            self.check_button.clicked.connect(self._check_setup)
            self.retarget_selected_button.clicked.connect(self._retarget_selected_pairs)
            self.retarget_all_button.clicked.connect(self._retarget_all_pairs)
            self.load_pair_button.clicked.connect(self._load_selected_pair)
            self.delete_pair_button.clicked.connect(self._delete_selected_pair)
            self.delete_all_button.clicked.connect(self._delete_all_pairs)
            self.apply_source_button.clicked.connect(self._apply_selected_pair_source)
            self.apply_target_button.clicked.connect(self._apply_selected_pair_target)
            self.maintain_offset_check.toggled.connect(self._sync_to_controller)
            self.follow_translate_check.toggled.connect(self._sync_to_controller)
            self.follow_rotate_check.toggled.connect(self._sync_to_controller)
            self.reduce_keys_check.toggled.connect(self._sync_to_controller)
            self.pairs_table.itemSelectionChanged.connect(self._on_pair_selection_changed)
            self.pairs_table.itemDoubleClicked.connect(self._load_selected_pair)

        def _clear_layout(self, layout):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                child_layout = item.layout()
                if widget:
                    widget.deleteLater()
                elif child_layout:
                    self._clear_layout(child_layout)

        def _make_pair_row(self, source_value="", target_value="", record_node="", row_index=0):
            row_layout = QtWidgets.QHBoxLayout()
            source_edit = QtWidgets.QLineEdit(source_value or "")
            source_edit.setPlaceholderText("Source control")
            target_edit = QtWidgets.QLineEdit(target_value or "")
            target_edit.setPlaceholderText("Target control")
            source_pick = QtWidgets.QPushButton("Pick Source")
            target_pick = QtWidgets.QPushButton("Pick Target")
            delete_button = QtWidgets.QPushButton("X")
            arrow_label = QtWidgets.QLabel("<->")
            arrow_label.setAlignment(QtCore.Qt.AlignCenter)
            row_layout.addWidget(source_edit, 3)
            row_layout.addWidget(source_pick)
            row_layout.addWidget(arrow_label)
            row_layout.addWidget(target_edit, 3)
            row_layout.addWidget(target_pick)
            row_layout.addWidget(delete_button)
            self.pair_rows_layout.addLayout(row_layout)
            row = {
                "source": source_edit,
                "target": target_edit,
                "record": record_node,
                "layout": row_layout,
            }
            self.pair_row_widgets.append(row)
            source_pick.clicked.connect(lambda _checked=False, index=row_index: self._row_use_selected_source(index))
            target_pick.clicked.connect(lambda _checked=False, index=row_index: self._row_use_selected_target(index))
            delete_button.clicked.connect(lambda _checked=False, index=row_index: self._delete_pair_row(index))
            source_edit.editingFinished.connect(lambda index=row_index: self._apply_pair_row(index))
            target_edit.editingFinished.connect(lambda index=row_index: self._apply_pair_row(index))

        def _row_values(self):
            rows = []
            for row in getattr(self, "pair_row_widgets", []):
                source_value = row["source"].text().strip()
                target_value = row["target"].text().strip()
                rows.append({"source": source_value, "target": target_value, "record": row.get("record", "")})
            return rows

        def _rebuild_pair_rows(self):
            if not hasattr(self, "pair_rows_layout"):
                return
            self._clear_layout(self.pair_rows_layout)
            self.pair_row_widgets = []
            rows = []
            for payload in self.controller.pair_entries(from_selection=False):
                rows.append(
                    {
                        "source": payload.get("source", ""),
                        "target": payload.get("target", ""),
                        "record": payload.get("record", ""),
                    }
                )
            if not rows and (self.controller.source_nodes or self.controller.target_nodes):
                row_count = max(len(self.controller.source_nodes), len(self.controller.target_nodes))
                for index in range(row_count):
                    rows.append(
                        {
                            "source": self.controller.source_nodes[index] if index < len(self.controller.source_nodes) else "",
                            "target": self.controller.target_nodes[index] if index < len(self.controller.target_nodes) else "",
                            "record": "",
                        }
                    )
            rows.append({"source": "", "target": "", "record": ""})
            for row_index, row in enumerate(rows):
                self._make_pair_row(row.get("source", ""), row.get("target", ""), row.get("record", ""), row_index)

        def _save_complete_rows(self):
            saved = 0
            for row in self._row_values():
                source_value = row["source"]
                target_value = row["target"]
                if not source_value and not target_value:
                    continue
                if source_value and target_value:
                    success, _message = self.controller.upsert_pair(source_value, target_value)
                    if success:
                        saved += 1
            return saved

        def _apply_pair_row(self, row_index):
            if row_index < 0 or row_index >= len(self.pair_row_widgets):
                return
            row = self.pair_row_widgets[row_index]
            source_value = row["source"].text().strip()
            target_value = row["target"].text().strip()
            if not source_value or not target_value:
                return
            success, message = self.controller.upsert_pair(source_value, target_value)
            self._sync_from_controller()
            self._set_status(message, success)

        def _row_use_selected_source(self, row_index):
            selected_nodes = _selected_controls()
            if not selected_nodes or row_index >= len(self.pair_row_widgets):
                self._set_status("Pick one source control in Maya first.", False)
                return
            self.pair_row_widgets[row_index]["source"].setText(_node_long_name(selected_nodes[0]))
            self._apply_pair_row(row_index)

        def _row_use_selected_target(self, row_index):
            selected_nodes = _selected_controls()
            if not selected_nodes or row_index >= len(self.pair_row_widgets):
                self._set_status("Pick one target control in Maya first.", False)
                return
            self.pair_row_widgets[row_index]["target"].setText(_node_long_name(selected_nodes[0]))
            self._apply_pair_row(row_index)

        def _delete_pair_row(self, row_index):
            if row_index < 0 or row_index >= len(self.pair_row_widgets):
                return
            record_node = self.pair_row_widgets[row_index].get("record", "")
            if record_node:
                self.controller.set_selected_records([record_node])
                success, message = self.controller.delete_selected()
            else:
                success, message = True, "Cleared the empty row."
            self._sync_from_controller()
            self._set_status(message, success)

        def _selected_table_records(self):
            rows = sorted(set(index.row() for index in self.pairs_table.selectionModel().selectedRows()))
            record_nodes = []
            for row_index in rows:
                item = self.pairs_table.item(row_index, 0)
                record_node = item.data(QtCore.Qt.UserRole) if item else ""
                if record_node:
                    record_nodes.append(record_node)
            return record_nodes

        def _populate_combo(self, combo, values, selected_value=""):
            combo.blockSignals(True)
            try:
                combo.clear()
                combo.addItem("(none)", "")
                for value in _dedupe_preserve_order([_node_long_name(node_name) for node_name in values if node_name and cmds.objExists(node_name)]):
                    combo.addItem(value, value)
                if selected_value:
                    index = combo.findData(_node_long_name(selected_value))
                    if index < 0:
                        index = combo.findText(_node_long_name(selected_value))
                    if index >= 0:
                        combo.setCurrentIndex(index)
                    elif combo.count() > 0:
                        combo.setCurrentIndex(0)
                elif combo.count() > 0:
                    combo.setCurrentIndex(0)
            finally:
                combo.blockSignals(False)

        def _refresh_pair_editor(self):
            selected_payload = self.controller.selected_record_payload() if self.controller.selected_records else None
            source_value = selected_payload.get("source", "") if selected_payload else ""
            target_value = selected_payload.get("target", "") if selected_payload else ""
            source_values = list(self.controller.source_nodes)
            target_values = list(self.controller.target_nodes)
            if getattr(self, "quick_pair_group", None) and self.quick_pair_group.isVisible():
                scene_values = _scene_transform_candidates()
                source_values.extend(scene_values)
                target_values.extend(scene_values)
            if source_value and source_value not in source_values:
                source_values.append(source_value)
            if target_value and target_value not in target_values:
                target_values.append(target_value)
            self._populate_combo(self.pair_source_combo, source_values, source_value)
            self._populate_combo(self.pair_target_combo, target_values, target_value)

        def _current_combo_value(self, combo):
            data = combo.currentData()
            if data:
                return str(data)
            value = combo.currentText().strip()
            return value if value and value != "(none)" else ""

        def _refresh_table(self):
            selected_records = set(self.controller.selected_records)
            payloads = self.controller.pair_entries(from_selection=False)
            self.pairs_table.setRowCount(len(payloads))
            for row_index, payload in enumerate(payloads):
                values = [
                    payload.get("source_label", _short_name(payload.get("source", ""))),
                    payload.get("target_label", _short_name(payload.get("target", ""))),
                    "".join([
                        "T" if payload.get("follow_translate") else "",
                        "R" if payload.get("follow_rotate") else "",
                    ]) or "-",
                    "Baked" if payload.get("baked") else ("Saved" if payload.get("enabled", True) else "Off"),
                ]
                for column_index, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    if column_index == 0:
                        item.setData(QtCore.Qt.UserRole, payload["record"])
                    self.pairs_table.setItem(row_index, column_index, item)
                if payload["record"] in selected_records:
                    self.pairs_table.selectRow(row_index)

        def _sync_from_controller(self):
            self.source_box.setPlainText(_controls_to_text(self.controller.source_nodes))
            self.target_box.setPlainText(_controls_to_text(self.controller.target_nodes))
            self.maintain_offset_check.blockSignals(True)
            self.follow_translate_check.blockSignals(True)
            self.follow_rotate_check.blockSignals(True)
            self.reduce_keys_check.blockSignals(True)
            self.maintain_offset_check.setChecked(bool(self.controller.maintain_offset))
            self.follow_translate_check.setChecked(bool(self.controller.follow_translate))
            self.follow_rotate_check.setChecked(bool(self.controller.follow_rotate))
            self.reduce_keys_check.setChecked(bool(self.controller.reduce_keys))
            self.maintain_offset_check.blockSignals(False)
            self.follow_translate_check.blockSignals(False)
            self.follow_rotate_check.blockSignals(False)
            self.reduce_keys_check.blockSignals(False)
            self._refresh_pair_editor()
            self._refresh_table()
            self._rebuild_pair_rows()
            self.report_box.setPlainText(self._report_text())

        def _sync_to_controller(self):
            row_values = self._row_values() if hasattr(self, "pair_row_widgets") else []
            if row_values:
                self.controller.source_nodes = _dedupe_preserve_order(
                    _node_long_name(row["source"]) for row in row_values if row.get("source") and cmds.objExists(row.get("source"))
                )
                self.controller.target_nodes = _dedupe_preserve_order(
                    _node_long_name(row["target"]) for row in row_values if row.get("target") and cmds.objExists(row.get("target"))
                )
            else:
                self.controller.source_nodes = _control_list_from_text(self.source_box.toPlainText())
                self.controller.target_nodes = _control_list_from_text(self.target_box.toPlainText())
            self.controller.maintain_offset = bool(self.maintain_offset_check.isChecked())
            self.controller.follow_translate = bool(self.follow_translate_check.isChecked())
            self.controller.follow_rotate = bool(self.follow_rotate_check.isChecked())
            self.controller.reduce_keys = bool(self.reduce_keys_check.isChecked())

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)
            self.report_box.setPlainText(self._report_text())
            self._refresh_table()

        def _report_text(self):
            report = self.controller.report or {}
            lines = [
                "Source controls: {0}".format(len(self.controller.source_nodes)),
                "Target controls: {0}".format(len(self.controller.target_nodes)),
                "Saved control pairs: {0}".format(len(self.controller.pair_entries(from_selection=False))),
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
            lines.append("- The selected controls and saved control pairs look ready.")
            lines.append("")
            if report.get("entries"):
                lines.append("Control Pairs")
                for entry in report["entries"]:
                    lines.append("- {0}".format(_pair_summary(entry)))
            return "\n".join(lines).strip()

        def _use_selected_source(self):
            success, message = self.controller.set_source_from_selection()
            self._sync_from_controller()
            self._set_status(message, success)

        def _remove_selected_source(self):
            self.controller.source_nodes = []
            success, message = True, "Cleared source rows."
            self._sync_from_controller()
            self._set_status(message, success)

        def _use_selected_target(self):
            success, message = self.controller.set_target_from_selection()
            self._sync_from_controller()
            self._set_status(message, success)

        def _remove_selected_target(self):
            self.controller.target_nodes = []
            success, message = True, "Cleared target rows."
            self._sync_from_controller()
            self._set_status(message, success)

        def _pair_by_order(self):
            self._sync_to_controller()
            success, message = self.controller.pair_by_order()
            self._sync_from_controller()
            self._set_status(message, success)

        def _pair_by_name(self):
            self._sync_to_controller()
            success, message = self.controller.pair_by_name()
            self._sync_from_controller()
            self._set_status(message, success)

        def _check_setup(self):
            self._sync_to_controller()
            success, message = self.controller.analyze_setup()
            self._sync_from_controller()
            self._set_status(message, success)

        def _retarget_selected_pairs(self):
            self._sync_to_controller()
            self._save_complete_rows()
            self.controller.set_selected_records(self._selected_table_records())
            success, message = self.controller.retarget_selected_pairs()
            self._sync_from_controller()
            self._set_status(message, success)

        def _retarget_all_pairs(self):
            self._sync_to_controller()
            self._save_complete_rows()
            success, message = self.controller.retarget_all_pairs()
            self._sync_from_controller()
            self._set_status(message, success)

        def _retarget_and_bake(self):
            self._retarget_selected_pairs()

        def _delete_selected_pair(self):
            self.controller.set_selected_records(self._selected_table_records())
            success, message = self.controller.delete_selected()
            self._sync_from_controller()
            self._set_status(message, success)

        def _delete_all_pairs(self):
            success, message = self.controller.delete_all()
            self._sync_from_controller()
            self._set_status(message, success)

        def _load_selected_pair(self, *_args):
            self.controller.set_selected_records(self._selected_table_records())
            success, message = self.controller.load_selected_pair()
            self._sync_from_controller()
            self._set_status(message, success)

        def _on_pair_selection_changed(self):
            self.controller.set_selected_records(self._selected_table_records())
            self._refresh_pair_editor()

        def _apply_selected_pair_source(self):
            self._sync_to_controller()
            source_value = self._current_combo_value(self.pair_source_combo)
            success, message = self.controller.update_selected_pair(source_node=source_value)
            self._sync_from_controller()
            self._set_status(message, success)

        def _apply_selected_pair_target(self):
            self._sync_to_controller()
            target_value = self._current_combo_value(self.pair_target_combo)
            success, message = self.controller.update_selected_pair(target_node=target_value)
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
                super(MayaFaceRetargetWindow, self).closeEvent(event)
            except TypeError:
                QtWidgets.QDialog.closeEvent(self, event)


def _delete_workspace_control(workspace_control_name):
    if MAYA_AVAILABLE and cmds and cmds.workspaceControl(workspace_control_name, exists=True):
        try:
            cmds.deleteUI(workspace_control_name, control=True)
        except Exception:
            pass


def _workspace_control_exists(workspace_control_name=WORKSPACE_CONTROL_NAME):
    return bool(MAYA_AVAILABLE and cmds and cmds.workspaceControl(workspace_control_name, exists=True))


def _process_qt_events():
    if not QtWidgets:
        return
    application = QtWidgets.QApplication.instance()
    if not application:
        return
    try:
        application.processEvents()
    except Exception:
        pass


def _dock_workspace_control(workspace_control_name=WORKSPACE_CONTROL_NAME, area="right", tab=False):
    if not _workspace_control_exists(workspace_control_name):
        return False, "The dockable Maya workspace control is not open yet."
    try:
        cmds.workspaceControl(workspace_control_name, edit=True, dockToMainWindow=(area, bool(tab)))
        cmds.workspaceControl(workspace_control_name, edit=True, restore=True)
        _process_qt_events()
        floating = bool(cmds.workspaceControl(workspace_control_name, query=True, floating=True))
    except Exception as exc:
        return False, "Could not dock the Maya workspace control: {0}".format(exc)
    if floating:
        return False, "Maya kept the Controls Retargeter panel floating instead of docking it."
    return True, "Docked the Controls Retargeter panel into Maya's {0} layout.".format(area)


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


def launch_maya_face_retarget(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not (MAYA_AVAILABLE and QtWidgets):
        raise RuntimeError("Maya Controls Retargeter (Face and Body) must be launched inside Maya with PySide available.")
    _close_existing_window()
    if dock:
        _delete_workspace_control(WORKSPACE_CONTROL_NAME)
    GLOBAL_CONTROLLER = FaceRetargetController()
    GLOBAL_WINDOW = MayaFaceRetargetWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    if dock:
        try:
            GLOBAL_WINDOW.show(dockable=True, floating=True, area="right")
        except Exception:
            GLOBAL_WINDOW.show()
        _process_qt_events()
        _dock_workspace_control(WORKSPACE_CONTROL_NAME, area="right", tab=False)
    else:
        GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "DONATE_URL",
    "FOLLOW_AMIR_URL",
    "FaceRetargetController",
    "MayaFaceRetargetController",
    "MayaFaceRetargetWindow",
    "launch_maya_face_retarget",
]
