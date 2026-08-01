"""
maya_control_picker.py

Scene-backed control picker / selection manager for Maya.
"""

from __future__ import absolute_import, division, print_function

import os
import re
import time
from functools import lru_cache

import maya_contact_hold as hold_utils
import maya_face_retarget as face_utils

try:
    import maya.cmds as cmds
    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:
    from PySide2 import QtCore, QtGui, QtWidgets


WINDOW_OBJECT_NAME = "mayaControlPickerWindow"
CONTROL_PICKER_GROUP_NAME = "amirControlPicker_GRP"
CONTROL_PICKER_MARKER_ATTR = "amirControlPickerMarker"
CONTROL_PICKER_SOURCE_ATTR = "controlPickerSourceRoot"
CONTROL_PICKER_STATE_ATTR = "controlPickerState"
CONTROL_PICKER_VERSION = 2
CONTROL_PICKER_SELECTION_LOCK_SECONDS = 0.75
CONTROL_PICKER_SELECTION_SYNC_MS = 150

SHELF_BUTTON_DOC_TAG = "mayaControlPickerShelfButton"
DEFAULT_SHELF_BUTTON_LABEL = "Control Picker"
DEFAULT_SHELF_NAME = "Amir's Scripts"

FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL

CATEGORY_ORDER = ("Face", "Body", "Geometry", "Skeleton", "Left Hand", "Right Hand", "Fingers", "FK/IK", "Other")
CUSTOM_SETS_LABEL = "Custom Sets"
CATEGORY_COLORS = {
    "Face": "#ff9bcf",
    "Body": "#9dd8ff",
    "Left Hand": "#66d9ef",
    "Right Hand": "#ffad66",
    "Fingers": "#7bffb2",
    "Geometry": "#a8d8ff",
    "Skeleton": "#f2c66d",
    "FK/IK": "#ffd966",
    "Other": "#d5d5d5",
}

VISUAL_GROUP_ORDER = (
    "Face",
    "Head / Neck",
    "Body / Core",
    "Left Arm",
    "Right Arm",
    "Left Hand / Fingers",
    "Right Hand / Fingers",
    "Geometry",
    "Skeleton",
    "Left Leg",
    "Right Leg",
    "Left Front Leg",
    "Right Front Leg",
    "Left Back Leg",
    "Right Back Leg",
    "Tail",
    "Wings",
    "FK/IK",
    "Other",
)

VISUAL_CANVAS_WIDTH = 1200
VISUAL_CANVAS_HEIGHT = 1500
MAX_VISUAL_BUTTONS = 600

VISUAL_GROUP_ANCHORS = {
    "Face": (600, 110),
    "Head / Neck": (600, 240),
    "Body / Core": (600, 390),
    "Left Arm": (210, 340),
    "Right Arm": (990, 340),
    "Left Hand / Fingers": (145, 600),
    "Right Hand / Fingers": (1055, 600),
    "Left Leg": (430, 980),
    "Right Leg": (770, 980),
    "Left Front Leg": (410, 840),
    "Right Front Leg": (790, 840),
    "Left Back Leg": (435, 1060),
    "Right Back Leg": (765, 1060),
    "Tail": (600, 1200),
    "Wings": (600, 250),
    "Geometry": (145, 1340),
    "Skeleton": (1055, 1340),
    "FK/IK": (600, 760),
    "Other": (600, 1380),
}

FACE_SUBGROUP_ORDER = (
    "Eyes",
    "Eyebrows",
    "Cheeks",
    "Ears",
    "Hair",
    "Head",
    "Mouth",
    "Upper Lip",
    "Lower Lip",
    "Lips",
    "Nose",
    "Jaw",
    "Tongue",
    "Tail",
    "Face Other",
)

BODY_SUBGROUP_ORDER = (
    "Spine",
    "COG",
    "Left Arm",
    "Right Arm",
    "Left Hand / Fingers",
    "Right Hand / Fingers",
    "Left Leg",
    "Right Leg",
    "Tail",
    "Wings",
    "Core",
    "Body Other",
)

CONTROL_MODE_ORDER = ("FK", "IK", "Switch", "Shared")
MANUAL_GROUP_PATHS = (
    "Face / Eyes",
    "Face / Mouth",
    "Face / Brows",
    "Body / Core",
    "Body / Spine / FK",
    "Body / Spine / IK",
    "Body / Left Arm / FK",
    "Body / Left Arm / IK",
    "Body / Right Arm / FK",
    "Body / Right Arm / IK",
    "Body / Left Hand / FK",
    "Body / Left Hand / IK",
    "Body / Right Hand / FK",
    "Body / Right Hand / IK",
    "Body / Left Leg / FK",
    "Body / Left Leg / IK",
    "Body / Right Leg / FK",
    "Body / Right Leg / IK",
    "Body / Tail / FK",
    "Body / Tail / IK",
    "Body / Wings / FK",
    "Body / Wings / IK",
    "FK/IK / Switches",
    "Other / Other",
)

_CATEGORY_MATCHERS = {
    "Face": ("face", "brow", "eyebrow", "eye", "eyelid", "lid", "mouth", "jaw", "tongue", "lip", "cheek", "teeth", "nose", "ear", "snout", "muzzle", "whisker", "hair", "mane", "bang", "fur"),
    "Geometry": ("geo", "geometry", "mesh", "model", "surface", "render", "prop", "deform", "deformed"),
    "Skeleton": ("joint", "jnt", "bone", "skel", "skeleton"),
    "Body": (
        "spine",
        "chest",
        "hip",
        "pelvis",
        "root",
        "body",
        "cog",
        "centerofgravity",
        "arm",
        "leg",
        "shoulder",
        "elbow",
        "knee",
        "clav",
        "clavicle",
        "forearm",
        "upperarm",
        "lowerarm",
        "wrist",
        "ankle",
        "foot",
        "paw",
        "hoof",
        "heel",
        "ball",
        "claw",
        "tail",
        "wing",
        "mane",
        "withers",
        "croup",
        "hock",
        "fetlock",
    ),
    "Fingers": ("finger", "thumb", "index", "middle", "ring", "pinky", "digit", "claw", "talon"),
    "FK/IK": ("fkik", "ikfk", "ik_fk", "fk_ik", "switch", "blend", "space"),
}

_qt_flag = hold_utils._qt_flag
_maya_main_window = hold_utils._maya_main_window
_dedupe_preserve_order = hold_utils._dedupe_preserve_order
_short_name = hold_utils._short_name
_node_long_name = hold_utils._node_long_name
_selected_controls = hold_utils._selected_controls
_scene_transform_candidates = face_utils._scene_transform_candidates
_ensure_attr = face_utils._ensure_attr
_get_string_attr = face_utils._get_string_attr
_set_string_attr = face_utils._set_string_attr
_load_json_attr = face_utils._load_json_attr
_store_json_attr = face_utils._store_json_attr

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


def _current_frame():
    if not MAYA_AVAILABLE or not cmds:
        return 0
    try:
        return int(round(float(cmds.currentTime(query=True))))
    except Exception:
        return 0


@lru_cache(maxsize=8192)
def _normalized_name(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _contains_any(text, tokens):
    raw = (text or "").lower()
    normalized = _normalized_name(text)
    return any(token in raw or token in normalized for token in tokens)


def _record_path_parts(record):
    maya_name = str(record.get("maya_name") or "")
    return [part for part in maya_name.split("|") if part]


def _record_text(record, ancestor_depth=3):
    parts = _record_path_parts(record)
    local_parts = parts[-max(1, int(ancestor_depth) + 1) :]
    return " ".join([str(record.get("label") or "")] + local_parts)


def _name_tokens(value):
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(value or ""))
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", camel_split) if token]


def _rig_mode_tokens(record, ancestor_depth=3):
    parts = _record_path_parts(record)
    values = [str(record.get("label") or "")] + parts[-max(1, int(ancestor_depth) + 1) :]
    tokens = []
    for value in values:
        tokens.extend(_name_tokens(value))
    return tokens


def _world_position(node_name):
    if not MAYA_AVAILABLE or not cmds or not node_name or not cmds.objExists(node_name):
        return None
    try:
        values = cmds.xform(node_name, query=True, worldSpace=True, translation=True)
    except Exception:
        return None
    if not values or len(values) < 3:
        return None
    try:
        return [float(values[0]), float(values[1]), float(values[2])]
    except Exception:
        return None


def _record_mode(record):
    category = record.get("category") or "Other"
    tokens = _rig_mode_tokens(record)
    has_fk = "fk" in tokens or any(token in ("fkik", "ikfk") for token in tokens)
    has_ik = "ik" in tokens or any(token in ("fkik", "ikfk") for token in tokens)
    has_switch = any(token in ("switch", "blend", "toggle") for token in tokens)
    if category == "FK/IK" or (has_fk and has_ik) or has_switch:
        return "Switch"
    if has_fk:
        return "FK"
    if has_ik:
        return "IK"
    return "Shared"


def _record_group_path(record):
    manual_path = record.get("group_path") or []
    if isinstance(manual_path, str):
        manual_path = [part.strip() for part in manual_path.split("/") if part.strip()]
    manual_path = [str(part).strip() for part in manual_path if str(part).strip()]
    if manual_path:
        return tuple(manual_path)
    category = record.get("category") or "Other"
    base_group = _list_subgroup_name(record) or category
    mode = _record_mode(record)
    if category == "FK/IK":
        return ("Switches",)
    mode_groups = {
        "Spine",
        "Left Arm",
        "Right Arm",
        "Left Hand / Fingers",
        "Right Hand / Fingers",
        "Left Leg",
        "Right Leg",
        "Tail",
        "Wings",
    }
    if category == "Body" and base_group in mode_groups and mode in ("FK", "IK", "Switch"):
        return (base_group, mode)
    return (base_group,)


def _project_record_positions(records, view_name="Front"):
    axes = (0, 1) if str(view_name).lower().startswith("front") else (2, 1)
    points = {}
    usable = []
    for record in records or []:
        maya_name = record.get("maya_name") or ""
        position = record.get("world_position")
        if not position or len(position) < 3:
            continue
        try:
            horizontal = float(position[axes[0]])
            vertical = float(position[axes[1]])
        except Exception:
            continue
        usable.append((maya_name, horizontal, vertical))
    if not usable:
        return points
    min_x = min(item[1] for item in usable)
    max_x = max(item[1] for item in usable)
    min_y = min(item[2] for item in usable)
    max_y = max(item[2] for item in usable)
    span_x = max(max_x - min_x, 1.0e-6)
    span_y = max(max_y - min_y, 1.0e-6)
    for maya_name, horizontal, vertical in usable:
        points[maya_name] = (
            0.08 + ((horizontal - min_x) / span_x) * 0.84,
            0.08 + (1.0 - ((vertical - min_y) / span_y)) * 0.84,
        )
    return points


def _record_side(record):
    text = _record_text(record)
    tokens = _name_tokens(text)
    if any(token in ("left", "lft", "lt", "lf", "l") for token in tokens):
        return "Left"
    if any(token in ("right", "rt", "rgt", "rg", "r") for token in tokens):
        return "Right"
    if any(token in ("front", "fore") for token in tokens):
        return "Front"
    if any(token in ("back", "hind", "rear") for token in tokens):
        return "Back"
    return "Center"


def _visual_group_name(record):
    text = _record_text(record)
    category = record.get("category") or "Other"
    side = _record_side(record)
    if category == "Body":
        list_group = _list_subgroup_name(record)
        if list_group in ("Left Hand / Fingers", "Right Hand / Fingers"):
            return list_group

    if category == "Face" or _contains_any(text, ("face", "jaw", "mouth", "lip", "brow", "eye", "eyelid", "lid", "tongue", "cheek", "nose", "teeth", "hair")):
        return "Face"
    if category == "Geometry" or _contains_any(text, ("geo", "geometry", "mesh", "model", "surface", "render", "prop")):
        return "Geometry"
    if category == "Skeleton" or _contains_any(text, ("joint", "jnt", "bone", "skel", "skeleton")):
        return "Skeleton"
    if _contains_any(text, ("head", "neck")):
        return "Head / Neck"
    if category == "FK/IK":
        return "FK/IK"
    if _contains_any(text, ("tail",)):
        return "Tail"
    if _contains_any(text, ("wing", "feather", "feath")):
        return "Wings"
    if _contains_any(text, ("hand", "finger", "thumb", "index", "middle", "ring", "pinky")):
        return "{0} Hand / Fingers".format(side) if side in ("Left", "Right") else "Left Hand / Fingers"
    if _contains_any(text, ("clav", "shoulder", "upperarm", "upper_arm", "lowerarm", "forearm", "elbow", "wrist", "arm")):
        return "{0} Arm".format(side) if side in ("Left", "Right") else "Body / Core"
    if _contains_any(text, ("leg", "thigh", "shin", "calf", "knee", "ankle", "foot", "toe", "heel", "ball", "paw", "hoof")):
        if _contains_any(text, ("front", "fore")):
            return "{0} Front Leg".format(side if side in ("Left", "Right") else "Left")
        if _contains_any(text, ("back", "hind", "rear")):
            return "{0} Back Leg".format(side if side in ("Left", "Right") else "Left")
        return "{0} Leg".format(side) if side in ("Left", "Right") else "Body / Core"
    if category == "Body":
        return "Body / Core"
    if side in ("Left", "Right"):
        return "{0} Side".format(side)
    return "Other"


def _visual_group_anchor(group_name):
    return VISUAL_GROUP_ANCHORS.get(group_name, VISUAL_GROUP_ANCHORS["Other"])


def _root_group(create=True):
    if not MAYA_AVAILABLE or not cmds:
        return None
    if cmds.objExists(CONTROL_PICKER_GROUP_NAME):
        return CONTROL_PICKER_GROUP_NAME
    if not create:
        return None
    try:
        root = cmds.group(empty=True, name=CONTROL_PICKER_GROUP_NAME)
    except Exception:
        return None
    try:
        cmds.setAttr(root + ".visibility", 0)
    except Exception:
        pass
    try:
        cmds.setAttr(root + ".hiddenInOutliner", 1)
    except Exception:
        pass
    _ensure_attr(root, CONTROL_PICKER_MARKER_ATTR)
    _ensure_attr(root, CONTROL_PICKER_SOURCE_ATTR)
    _ensure_attr(root, CONTROL_PICKER_STATE_ATTR)
    try:
        _set_string_attr(root, CONTROL_PICKER_MARKER_ATTR, "control_picker")
    except Exception:
        pass
    return root


def _transform_for_node(node_name):
    if not MAYA_AVAILABLE or not cmds or not node_name or not cmds.objExists(node_name):
        return None
    try:
        node_type = cmds.nodeType(node_name)
    except Exception:
        return None
    if node_type in ("transform", "joint"):
        return _node_long_name(node_name)
    parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
    for parent_name in parents:
        try:
            if cmds.nodeType(parent_name) == "transform":
                return _node_long_name(parent_name)
        except Exception:
            continue
    return None


def _selection_transforms():
    if not MAYA_AVAILABLE or not cmds:
        return []
    transforms = []
    for node_name in cmds.ls(selection=True, long=True) or []:
        transform_name = _transform_for_node(node_name)
        if transform_name and transform_name not in transforms:
            transforms.append(transform_name)
    return transforms


def _control_shapes(node_name):
    if not MAYA_AVAILABLE or not cmds or not node_name or not cmds.objExists(node_name):
        return []
    try:
        return cmds.listRelatives(node_name, shapes=True, fullPath=True) or []
    except Exception:
        return []


def _shape_types(node_name):
    types = []
    for shape_name in _control_shapes(node_name):
        try:
            shape_type = cmds.nodeType(shape_name)
        except Exception:
            continue
        if shape_type and shape_type not in types:
            types.append(shape_type)
    return types


def _user_defined_attrs(node_name):
    if not MAYA_AVAILABLE or not cmds or not node_name or not cmds.objExists(node_name):
        return []
    try:
        return cmds.listAttr(node_name, userDefined=True) or []
    except Exception:
        return []


def _keyable_attrs(node_name):
    if not MAYA_AVAILABLE or not cmds or not node_name or not cmds.objExists(node_name):
        return []
    attrs = []
    try:
        attrs.extend(cmds.listAttr(node_name, keyable=True) or [])
    except Exception:
        pass
    try:
        attrs.extend(cmds.listAttr(node_name, channelBox=True) or [])
    except Exception:
        pass
    attrs.extend(_user_defined_attrs(node_name))
    return _dedupe_preserve_order([attr_name for attr_name in attrs if attr_name])


def _looks_like_control(node_name):
    short_name = _short_name(node_name).lower()
    if short_name in {"persp", "top", "front", "side"}:
        return False
    if short_name.endswith("shape"):
        return False
    if any(token in short_name for token in ("_grp", ".grp", "-grp", "group")) and not any(token in short_name for token in ("ctrl", "ctl", "control")):
        return False
    shape_types = _shape_types(node_name)
    if not shape_types:
        return False
    if all(shape_type in ("nurbsCurve", "nurbsSurface") for shape_type in shape_types):
        return True
    try:
        return cmds.nodeType(node_name) in ("nurbsCurve", "nurbsSurface")
    except Exception:
        return False


def _category_from_name(node_name):
    short_name = _short_name(node_name).lower()
    if any(token in short_name for token in ("hand", "finger", "thumb", "index", "middle", "ring", "pinky", "digit")):
        return "Body"
    if any(
        token in short_name
        for token in (
            "arm",
            "shoulder",
            "elbow",
            "wrist",
            "clav",
            "leg",
            "thigh",
            "shin",
            "calf",
            "knee",
            "ankle",
            "foot",
            "toe",
            "heel",
            "paw",
            "hoof",
            "wing",
            "tail",
            "spine",
            "chest",
            "pelvis",
            "hip",
        )
    ):
        return "Body"
    for category_name, tokens in _CATEGORY_MATCHERS.items():
        if any(
            (
                token in short_name
                if token not in {"ear", "eye", "lid"}
                else any(
                    name_token == token or name_token.startswith(token)
                    for name_token in _name_tokens(short_name)
                )
            )
            for token in tokens
        ):
            return category_name
    return "Other"


def _side_from_name(node_name):
    tokens = _name_tokens(_short_name(node_name))
    if any(token in ("left", "lft", "lt", "lf", "l", "port") for token in tokens):
        return "Left"
    if any(token in ("right", "rt", "rgt", "rg", "r", "starboard") for token in tokens):
        return "Right"
    if any(token in ("center", "centre", "mid", "middle", "c") for token in tokens):
        return "Center"
    return "Unknown"


def _clean_record_label(value):
    label = str(value or "").strip()
    while re.match(r"^[LRC]:\s*", label, flags=re.IGNORECASE):
        label = re.sub(r"^[LRC]:\s*", "", label, count=1, flags=re.IGNORECASE).strip()
    return label


def _display_label_for_record(record):
    label = _clean_record_label(record.get("label")) or _short_name(record.get("maya_name") or "")
    side = record.get("side") or _side_from_name(record.get("maya_name") or "")
    if side in {"Left", "Right"}:
        return "{0}: {1}".format(side[0], label)
    if side == "Center":
        return "C: {0}".format(label)
    return label


def _tree_item_kind(item):
    if not item:
        return ""
    try:
        return item.data(0, QtCore.Qt.UserRole + 1) or ""
    except Exception:
        return ""


def _tree_item_base_label(item):
    if not item:
        return ""
    try:
        base_label = item.data(0, QtCore.Qt.UserRole + 4) or ""
    except Exception:
        base_label = ""
    if base_label:
        return base_label
    try:
        return (item.text(0) or "").split(" (", 1)[0]
    except Exception:
        return ""


def _count_tree_controls(item):
    if not item:
        return 0
    count = 0
    try:
        child_count = item.childCount()
    except Exception:
        child_count = 0
    for index in range(child_count):
        child = item.child(index)
        if _tree_item_kind(child) == "control":
            count += 1
        else:
            count += _count_tree_controls(child)
    return count


def _tree_item_control_items(item):
    if not item:
        return []
    try:
        kind = _tree_item_kind(item)
    except Exception:
        kind = ""
    if kind == "control":
        return [item]
    items = []
    try:
        child_count = item.childCount()
    except Exception:
        child_count = 0
    for index in range(child_count):
        items.extend(_tree_item_control_items(item.child(index)))
    return _dedupe_preserve_order(items)


def _list_subgroup_name(record):
    category = record.get("category") or "Other"
    leaf_name = _group_label_for_record(record)
    if category == "Face":
        if leaf_name in ("Eye", "Eyes", "Left Eye", "Right Eye"):
            return "Eyes"
        if leaf_name in ("Eyebrow", "Eyebrows", "Left Eyebrow", "Right Eyebrow"):
            return "Eyebrows"
        if leaf_name in ("Cheek", "Cheeks", "Left Cheek", "Right Cheek"):
            return "Cheeks"
        if leaf_name in ("Ear", "Ears", "Left Ear", "Right Ear"):
            return "Ears"
        if leaf_name in ("Upper Lip", "Lower Lip", "Lips"):
            return leaf_name
        if leaf_name in ("Hair", "Head", "Mouth", "Nose", "Jaw", "Tongue", "Tail", "Face Other"):
            return leaf_name
        return leaf_name
    if category == "Body":
        if leaf_name in ("COG", "Core", "Spine", "Tail", "Wings", "Body Other"):
            return leaf_name
        if leaf_name in ("Left Arm", "Right Arm", "Left Hand / Fingers", "Right Hand / Fingers", "Left Leg", "Right Leg"):
            return leaf_name
        return leaf_name
    return leaf_name or category


def _group_insert_index(parent_item, category_name, group_name):
    desired_order = _group_order_for_category(category_name)
    try:
        desired_index = desired_order.index(group_name)
    except ValueError:
        desired_index = len(desired_order)
    for index in range(parent_item.childCount()):
        child = parent_item.child(index)
        if _tree_item_kind(child) != "group":
            continue
        child_name = _tree_item_base_label(child)
        try:
            child_index = desired_order.index(child_name)
        except ValueError:
            child_index = len(desired_order)
        if child_index > desired_index:
            return index
    return parent_item.childCount()


def _category_color(category_name):
    return QtGui.QColor(CATEGORY_COLORS.get(category_name, CATEGORY_COLORS["Other"]))


def _group_order_for_category(category_name):
    if category_name == "Face":
        return FACE_SUBGROUP_ORDER
    if category_name == "Body":
        return BODY_SUBGROUP_ORDER
    return ()


def _group_label_for_record(record):
    category = record.get("category") or "Other"
    text = _record_text(record)
    side = record.get("side") or _record_side(record)
    if category == "Face":
        if _contains_any(text, ("brow", "eyebrow")):
            if side in ("Left", "Right"):
                return "{0} Eyebrow".format(side)
            return "Eyebrow"
        if _contains_any(text, ("eye", "lid", "eyelid")):
            if side in ("Left", "Right"):
                return "{0} Eye".format(side)
            return "Eye"
        if _contains_any(text, ("cheek",)):
            if side in ("Left", "Right"):
                return "{0} Cheek".format(side)
            return "Cheeks"
        if _contains_any(text, ("ear", "earlobe")):
            if side in ("Left", "Right"):
                return "{0} Ear".format(side)
            return "Ears"
        if _contains_any(text, ("hair", "mane", "bang", "fur")):
            return "Hair"
        if _contains_any(text, ("head", "neck")):
            return "Head"
        if _contains_any(text, ("upperlip", "upper lip", "upper_lip", "upper-lip")):
            return "Upper Lip"
        if _contains_any(text, ("lowerlip", "lower lip", "lower_lip", "lower-lip")):
            return "Lower Lip"
        if _contains_any(text, ("mouth",)):
            return "Mouth"
        if _contains_any(text, ("lip", "lips")):
            return "Lips"
        if _contains_any(text, ("nose", "snout", "muzzle")):
            return "Nose"
        if _contains_any(text, ("jaw",)):
            return "Jaw"
        if _contains_any(text, ("tongue",)):
            return "Tongue"
        return "Face Other"
    if category == "Body":
        if _contains_any(text, ("spine",)):
            return "Spine"
        if _contains_any(text, ("cog", "centerofgravity", "center of gravity")):
            return "COG"
        if _contains_any(text, ("tail",)):
            return "Tail"
        if _contains_any(text, ("hand", "finger", "thumb", "index", "middle", "ring", "pinky", "digit")):
            if side in ("Left", "Right"):
                return "{0} Hand / Fingers".format(side)
            return "Core"
        if _contains_any(text, ("arm", "shoulder", "elbow", "wrist", "clav", "clavicle", "upperarm", "lowerarm", "forearm")):
            if side in ("Left", "Right"):
                return "{0} Arm".format(side)
            return "Core"
        if _contains_any(text, ("leg", "thigh", "shin", "calf", "knee", "ankle", "foot", "toe", "heel", "ball", "paw", "hoof", "hock", "fetlock")):
            if side in ("Left", "Right"):
                return "{0} Leg".format(side)
            return "Core"
        if _contains_any(text, ("hip", "pelvis", "root", "body", "chest", "torso")):
            return "Core"
        return "Body Other"
    return ""


def _hierarchy_candidates(root_name, node_types=("transform",)):
    if not MAYA_AVAILABLE or not cmds or not root_name or not cmds.objExists(root_name):
        return []
    candidates = [_node_long_name(root_name)]
    for node_type in node_types or ("transform",):
        try:
            candidates.extend(cmds.listRelatives(root_name, allDescendents=True, fullPath=True, type=node_type) or [])
        except Exception:
            continue
    return _dedupe_preserve_order(candidates)


def _looks_like_geometry(node_name):
    if not MAYA_AVAILABLE or not cmds or not node_name or not cmds.objExists(node_name):
        return False
    try:
        node_type = cmds.nodeType(node_name)
    except Exception:
        node_type = ""
    if node_type in ("mesh", "nurbsSurface", "subdiv"):
        return True
    shape_types = _shape_types(node_name)
    if not shape_types:
        return False
    if all(shape_type in ("mesh", "nurbsSurface", "subdiv") for shape_type in shape_types):
        return True
    return False


def _looks_like_skeleton(node_name):
    if not MAYA_AVAILABLE or not cmds or not node_name or not cmds.objExists(node_name):
        return False
    try:
        return cmds.nodeType(node_name) == "joint"
    except Exception:
        return False


def _fkik_switch_attr_name(node_name):
    if not MAYA_AVAILABLE or not cmds or not node_name or not cmds.objExists(node_name):
        return ""
    attrs = _keyable_attrs(node_name)
    if not attrs:
        return ""
    exact_tokens = {
        "fkik",
        "ikfk",
        "fk_ik",
        "ik_fk",
        "fkikswitch",
        "ikfkswitch",
        "fkikblend",
        "ikfkblend",
        "fkikmode",
        "ikfkmode",
    }
    fuzzy_tokens = ("switch", "blend", "mode", "toggle", "driver", "follow", "space", "enable", "solve", "state")
    short_name = _short_name(node_name).lower()
    limb_tokens = ("arm", "leg", "hand", "foot", "paw", "hoof", "tail", "wing", "spine", "neck", "hip", "pelvis", "shoulder", "clav", "elbow", "knee", "wrist", "ankle", "thigh", "shin", "calf", "forearm", "upperarm", "lowerarm")
    for attr_name in attrs:
        norm_name = _normalized_name(attr_name)
        if norm_name in exact_tokens:
            return attr_name
    for attr_name in attrs:
        norm_name = _normalized_name(attr_name)
        if "fk" in norm_name and "ik" in norm_name and _contains_any(norm_name, fuzzy_tokens):
            return attr_name
    for attr_name in attrs:
        norm_name = _normalized_name(attr_name)
        if "fk" in norm_name and "ik" in norm_name:
            return attr_name
    for attr_name in attrs:
        norm_name = _normalized_name(attr_name)
        if not _contains_any(norm_name, fuzzy_tokens):
            continue
        if "fk" in norm_name or "ik" in norm_name:
            return attr_name
        if _contains_any(short_name, limb_tokens):
            return attr_name
    return ""


def _category_from_node(node_name):
    if _fkik_switch_attr_name(node_name):
        return "FK/IK"
    return _category_from_name(node_name)


def _discover_role_names(root_name, role):
    if role == "geometry":
        node_types = ("transform",)
    elif role == "skeleton":
        node_types = ("joint",)
    else:
        node_types = ("transform",)
    discovered = []
    for node_name in _hierarchy_candidates(root_name, node_types=node_types):
        if not cmds or not cmds.objExists(node_name):
            continue
        if node_name == CONTROL_PICKER_GROUP_NAME:
            continue
        short_name = _short_name(node_name).lower()
        if _contains_any(short_name, ("_grp", "_group", ".grp", "-grp", "group")) and not _contains_any(short_name, ("ctrl", "ctl", "control", "switch", "geo", "mesh", "joint", "bone", "skel")):
            continue
        if role == "controls":
            if not _looks_like_control(node_name):
                continue
        elif role == "geometry":
            if not _looks_like_geometry(node_name):
                continue
        elif role == "skeleton":
            if not _looks_like_skeleton(node_name):
                continue
        discovered.append(_node_long_name(node_name))
    return discovered


def _default_record(node_name):
    return {
        "maya_name": _node_long_name(node_name),
        "label": _short_name(node_name),
        "category": _category_from_node(node_name),
        "side": _side_from_name(node_name),
        "group_path": [],
        "world_position": _world_position(node_name),
    }


def _records_from_state(state):
    records = []
    for record in state.get("records") or []:
        maya_name = record.get("maya_name") or record.get("name")
        if not maya_name:
            continue
        records.append(
            {
                "maya_name": _node_long_name(maya_name),
                "label": _clean_record_label(record.get("label")) or _short_name(maya_name),
                "category": record.get("category") or _category_from_name(maya_name),
                "side": record.get("side") or _side_from_name(maya_name),
                "group_path": list(record.get("group_path") or []),
                "world_position": record.get("world_position") or _world_position(maya_name),
            }
        )
    return records


def _load_state():
    root = _root_group(create=True)
    if not root:
        return {"version": CONTROL_PICKER_VERSION, "source_root": "", "geometry_root": "", "skeleton_root": "", "records": [], "custom_sets": []}
    state = _load_json_attr(root, CONTROL_PICKER_STATE_ATTR, default=None) or {}
    if not isinstance(state, dict):
        state = {}
    state.setdefault("version", CONTROL_PICKER_VERSION)
    state.setdefault("source_root", _get_string_attr(root, CONTROL_PICKER_SOURCE_ATTR) or "")
    state.setdefault("geometry_root", "")
    state.setdefault("skeleton_root", "")
    state.setdefault("records", [])
    state.setdefault("custom_sets", [])
    return state


def _save_state(state):
    root = _root_group(create=True)
    if not root:
        return False
    clean_state = {
        "version": CONTROL_PICKER_VERSION,
        "source_root": state.get("source_root") or "",
        "geometry_root": state.get("geometry_root") or "",
        "skeleton_root": state.get("skeleton_root") or "",
        "custom_sets": [
            {
                "name": str(custom_set.get("name") or "").strip(),
                "members": _dedupe_preserve_order(
                    [str(member) for member in (custom_set.get("members") or []) if member]
                ),
            }
            for custom_set in (state.get("custom_sets") or [])
            if str(custom_set.get("name") or "").strip()
        ],
        "records": [
            {
                "maya_name": record.get("maya_name") or record.get("name") or "",
                "label": record.get("label") or "",
                "category": record.get("category") or "Other",
                "side": record.get("side") or "Unknown",
                "group_path": list(record.get("group_path") or []),
                "world_position": list(record.get("world_position") or []),
            }
            for record in (state.get("records") or [])
            if (record.get("maya_name") or record.get("name"))
        ],
    }
    try:
        _set_string_attr(root, CONTROL_PICKER_SOURCE_ATTR, clean_state["source_root"])
        _store_json_attr(root, CONTROL_PICKER_STATE_ATTR, clean_state)
        return True
    except Exception:
        return False


class ControlPickerTree(QtWidgets.QTreeWidget):
    selectionMarqueeRequested = QtCore.Signal(object, bool)
    layoutChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super(ControlPickerTree, self).__init__(parent)
        self._marquee_origin = None
        self._marquee_band = None
        self._marquee_active = False
        self._marquee_additive = False
        self.viewport().setMouseTracking(True)

    def _reset_marquee_state(self):
        self._marquee_origin = None
        self._marquee_active = False
        self._marquee_additive = False
        if self._marquee_band:
            self._marquee_band.hide()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._marquee_origin = event.pos()
            self._marquee_active = False
            self._marquee_additive = bool(event.modifiers() & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier))
            if self._marquee_band is None:
                self._marquee_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self.viewport())
            self._marquee_band.setGeometry(QtCore.QRect(self._marquee_origin, QtCore.QSize()))
            self._marquee_band.hide()
        super(ControlPickerTree, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._marquee_origin is None or not (event.buttons() & QtCore.Qt.LeftButton):
            super(ControlPickerTree, self).mouseMoveEvent(event)
            return
        if not self._marquee_active and (event.pos() - self._marquee_origin).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            super(ControlPickerTree, self).mouseMoveEvent(event)
            return
        self._marquee_active = True
        if self._marquee_band is None:
            self._marquee_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self.viewport())
        self._marquee_band.setGeometry(QtCore.QRect(self._marquee_origin, event.pos()).normalized())
        self._marquee_band.show()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._marquee_origin is not None:
            rect = QtCore.QRect(self._marquee_origin, event.pos()).normalized()
            if self._marquee_band is not None:
                self._marquee_band.hide()
            if self._marquee_active:
                self.selectionMarqueeRequested.emit(rect, self._marquee_additive)
                self._reset_marquee_state()
                return True
            self._reset_marquee_state()
        super(ControlPickerTree, self).mouseReleaseEvent(event)

    def dropEvent(self, event):
        super(ControlPickerTree, self).dropEvent(event)
        if event.isAccepted():
            self.layoutChanged.emit()


class ControlPickerVisualCanvas(QtWidgets.QWidget):
    selectionMarqueeRequested = QtCore.Signal(object, bool)

    def __init__(self, parent=None):
        super(ControlPickerVisualCanvas, self).__init__(parent)
        self._marquee_origin = None
        self._marquee_band = None
        self._marquee_active = False
        self._marquee_additive = False
        self._projected_points = {}
        self._view_name = "Front"
        self.setMouseTracking(True)

    def set_projected_points(self, points, view_name="Front"):
        self._projected_points = dict(points or {})
        self._view_name = str(view_name or "Front")
        self.update()

    def sizeHint(self):
        return QtCore.QSize(VISUAL_CANVAS_WIDTH, VISUAL_CANVAS_HEIGHT)

    def minimumSizeHint(self):
        # Let the parent scroll area own the narrow-width contract.  The
        # canvas still keeps its normal size hint for the visual map, while
        # the picker shell can shrink without forcing outer horizontal scroll.
        return QtCore.QSize(0, 0)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QtGui.QColor("#151B21"))
        self._paint_rig_reference(painter)
        painter.end()

    def _paint_rig_reference(self, painter):
        width = float(self.width() or VISUAL_CANVAS_WIDTH)
        height = float(self.height() or VISUAL_CANVAS_HEIGHT)
        grid_pen = QtGui.QPen(QtGui.QColor("#26313B"), 1.0)
        painter.setPen(grid_pen)
        for fraction in (0.2, 0.4, 0.6, 0.8):
            painter.drawLine(QtCore.QPointF(width * fraction, 0.0), QtCore.QPointF(width * fraction, height))
            painter.drawLine(QtCore.QPointF(0.0, height * fraction), QtCore.QPointF(width, height * fraction))
        painter.setPen(QtGui.QPen(QtGui.QColor("#40505E"), 2.0))
        painter.drawLine(QtCore.QPointF(width * 0.5, 0.0), QtCore.QPointF(width * 0.5, height))
        painter.drawLine(QtCore.QPointF(0.0, height * 0.5), QtCore.QPointF(width, height * 0.5))
        painter.setPen(QtGui.QColor("#8EA2B5"))
        painter.drawText(18, 30, "{0} map from real rig control positions".format(self._view_name))
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(126, 197, 255, 90))
        for point in self._projected_points.values():
            try:
                x = float(point[0]) * width
                y = float(point[1]) * height
            except Exception:
                continue
            painter.drawEllipse(QtCore.QPointF(x, y), 5.0, 5.0)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._marquee_origin = event.pos()
            self._marquee_active = False
            self._marquee_additive = bool(event.modifiers() & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier))
            if self._marquee_band is None:
                self._marquee_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
            self._marquee_band.setGeometry(QtCore.QRect(self._marquee_origin, QtCore.QSize()))
            self._marquee_band.hide()
            event.accept()
            return
        super(ControlPickerVisualCanvas, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._marquee_origin is None or not (event.buttons() & QtCore.Qt.LeftButton):
            super(ControlPickerVisualCanvas, self).mouseMoveEvent(event)
            return
        if not self._marquee_active and (event.pos() - self._marquee_origin).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return
        self._marquee_active = True
        if self._marquee_band is None:
            self._marquee_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self._marquee_band.setGeometry(QtCore.QRect(self._marquee_origin, event.pos()).normalized())
        self._marquee_band.show()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._marquee_origin is not None:
            rect = QtCore.QRect(self._marquee_origin, event.pos()).normalized()
            if self._marquee_band is not None:
                self._marquee_band.hide()
            self.selectionMarqueeRequested.emit(rect, self._marquee_additive)
            self._marquee_origin = None
            self._marquee_active = False
            event.accept()
            return
        super(ControlPickerVisualCanvas, self).mouseReleaseEvent(event)


def _current_source_root_from_state():
    state = _load_state()
    source_root = state.get("source_root") or ""
    if source_root and cmds and cmds.objExists(source_root):
        return source_root
    return ""


class ControlPickerController(object):
    def __init__(self):
        self.panel = None

    def bind(self, panel):
        self.panel = panel
        return self

    def load_state(self):
        return _load_state()

    def save_state(self, source_root=None, geometry_root=None, skeleton_root=None, records=None, custom_sets=None):
        if self.panel:
            if source_root is None:
                source_root = self.panel.source_root_text()
            if geometry_root is None and hasattr(self.panel, "geometry_root_text"):
                geometry_root = self.panel.geometry_root_text()
            if skeleton_root is None and hasattr(self.panel, "skeleton_root_text"):
                skeleton_root = self.panel.skeleton_root_text()
            if custom_sets is None and hasattr(self.panel, "current_custom_sets"):
                custom_sets = self.panel.current_custom_sets()
        state = {
            "source_root": source_root or "",
            "geometry_root": geometry_root or "",
            "skeleton_root": skeleton_root or "",
            "records": list(records or []),
            "custom_sets": list(custom_sets or []),
        }
        return _save_state(state)

    def _normalize_records(self, records):
        normalized = []
        seen = set()
        for record in records:
            maya_name = _node_long_name(record.get("maya_name") or record.get("name") or "")
            if not maya_name or maya_name in seen:
                continue
            seen.add(maya_name)
            normalized.append(
                {
                    "maya_name": maya_name,
                    "label": _clean_record_label(record.get("label")) or _short_name(maya_name),
                    "category": record.get("category") or _category_from_name(maya_name),
                    "side": record.get("side") or _side_from_name(maya_name),
                    "group_path": list(record.get("group_path") or []),
                    "world_position": record.get("world_position") or _world_position(maya_name),
                }
            )
        return normalized

    def scan_scene(self, root=None, controls_root=None, geometry_root=None, skeleton_root=None):
        if root and not controls_root:
            controls_root = root
        existing_state = _load_state()
        existing_records = _records_from_state(existing_state)
        records_by_name = {}
        for record in existing_records:
            records_by_name[record["maya_name"]] = record
        existing_order = [record["maya_name"] for record in existing_records]
        records = []
        seen = set()
        role_roots = (
            ("controls", controls_root or existing_state.get("source_root") or ""),
            ("geometry", geometry_root or existing_state.get("geometry_root") or ""),
            ("skeleton", skeleton_root or existing_state.get("skeleton_root") or ""),
        )
        for role, role_root in role_roots:
            role_root = _node_long_name(role_root) if role_root and cmds and cmds.objExists(role_root) else ""
            if not role_root:
                continue
            role_names = _discover_role_names(role_root, role)
            ordered_names = [maya_name for maya_name in existing_order if maya_name in role_names]
            ordered_names.extend(maya_name for maya_name in role_names if maya_name not in ordered_names)
            for node_name in ordered_names:
                if node_name in seen:
                    continue
                seen.add(node_name)
                record = dict(records_by_name.get(node_name) or _default_record(node_name))
                record["maya_name"] = _node_long_name(node_name)
                record["label"] = record.get("label") or _short_name(node_name)
                record["world_position"] = _world_position(node_name)
                if role == "geometry":
                    record["category"] = "Geometry"
                    record["side"] = "Center"
                elif role == "skeleton":
                    record["category"] = "Skeleton"
                    record["side"] = "Center" if (record.get("side") or "Unknown") == "Unknown" else record.get("side")
                else:
                    record["category"] = "FK/IK" if _fkik_switch_attr_name(node_name) else (record.get("category") or _category_from_node(node_name))
                records.append(record)
        records = self._normalize_records(records)
        if self.panel:
            self.panel.set_records(
                records,
                source_root=(controls_root or existing_state.get("source_root") or ""),
                geometry_root=(geometry_root or existing_state.get("geometry_root") or ""),
                skeleton_root=(skeleton_root or existing_state.get("skeleton_root") or ""),
                custom_sets=existing_state.get("custom_sets") or [],
            )
        self.save_state(
            source_root=(controls_root or existing_state.get("source_root") or ""),
            geometry_root=(geometry_root or existing_state.get("geometry_root") or ""),
            skeleton_root=(skeleton_root or existing_state.get("skeleton_root") or ""),
            records=records,
            custom_sets=existing_state.get("custom_sets") or [],
        )
        return records

    def add_selected_controls(self, category=None):
        if not self.panel:
            return []
        selected_names = self.panel.selected_maya_names()
        if not selected_names:
            selected_names = _selection_transforms()
        if not selected_names:
            self.panel.set_status("No control selected.")
            return []
        existing_records = self.panel.current_records()
        record_map = {record["maya_name"]: dict(record) for record in existing_records}
        for node_name in selected_names:
            if not cmds or not cmds.objExists(node_name):
                continue
            record = record_map.get(node_name) or _default_record(node_name)
            if category:
                record["category"] = category
            record["maya_name"] = _node_long_name(node_name)
            record["label"] = record.get("label") or _short_name(node_name)
            record_map[node_name] = record
        records = self._normalize_records(list(record_map.values()))
        root_name = self.panel.source_root_text()
        self.panel.set_records(
            records,
            source_root=root_name,
            geometry_root=self.panel.geometry_root_text(),
            skeleton_root=self.panel.skeleton_root_text(),
        )
        self.save_state(
            source_root=root_name,
            geometry_root=self.panel.geometry_root_text(),
            skeleton_root=self.panel.skeleton_root_text(),
            records=records,
            custom_sets=self.panel.current_custom_sets(),
        )
        self.panel.set_status("Loaded {0} control(s).".format(len(selected_names)))
        return records

    def remove_selected_controls(self):
        if not self.panel:
            return []
        remove_names = set(self.panel.selected_maya_names())
        if not remove_names:
            self.panel.set_status("Pick control rows first.")
            return []
        records = [record for record in self.panel.current_records() if record.get("maya_name") not in remove_names]
        root_name = self.panel.source_root_text()
        self.panel.set_records(
            records,
            source_root=root_name,
            geometry_root=self.panel.geometry_root_text(),
            skeleton_root=self.panel.skeleton_root_text(),
        )
        self.save_state(
            source_root=root_name,
            geometry_root=self.panel.geometry_root_text(),
            skeleton_root=self.panel.skeleton_root_text(),
            records=records,
            custom_sets=self.panel.current_custom_sets(),
        )
        self.panel.set_status("Removed {0} control(s).".format(len(remove_names)))
        return records

    def select_in_maya(self):
        if not MAYA_AVAILABLE or not cmds or not self.panel:
            return []
        selected_names = self.panel._selected_item_names_from_tree()
        if not selected_names:
            try:
                cmds.select(clear=True)
            except Exception:
                pass
            self.panel._maya_selection_signature = ()
            self.panel._sync_visual_selection([])
            self.panel.set_status("Selection cleared.")
            return []
        cmds.select(selected_names, replace=True)
        self.panel._maya_selection_signature = tuple(selected_names)
        self.panel._sync_visual_selection(selected_names)
        self.panel.set_status("Selected {0} control(s) in Maya.".format(len(selected_names)))
        return selected_names

    def apply_label(self, new_label):
        if not self.panel:
            return False
        item = self.panel.current_control_item()
        if not item:
            self.panel.set_status("Pick one control row first.")
            return False
        new_label = (new_label or "").strip()
        if not new_label:
            self.panel.set_status("Type a label first.")
            return False
        item.setText(0, new_label)
        item.setData(0, QtCore.Qt.UserRole + 4, new_label)
        self.panel.set_status("Label set.")
        self._save_from_panel()
        return True

    def apply_category(self, category_name):
        if not self.panel:
            return False
        selected_items = self.panel.selected_control_items()
        if not selected_items:
            self.panel.set_status("Pick one control row first.")
            return False
        for item in selected_items:
            item.setData(0, QtCore.Qt.UserRole, category_name)
            item.setData(0, QtCore.Qt.UserRole + 6, [])
        records = self.panel.current_records()
        self.panel.set_records(
            records,
            source_root=self.panel.controls_root_text(),
            geometry_root=self.panel.geometry_root_text(),
            skeleton_root=self.panel.skeleton_root_text(),
            custom_sets=self.panel.current_custom_sets(),
        )
        self._save_from_panel()
        self.panel.set_status("Category set to {0}.".format(category_name))
        return True

    def apply_group_path(self, group_text):
        if not self.panel:
            return False
        selected_items = self.panel.selected_control_items()
        if not selected_items:
            self.panel.set_status("Pick one or more controls first.")
            return False
        parts = [part.strip() for part in str(group_text or "").split("/") if part.strip()]
        if len(parts) < 2:
            self.panel.set_status("Choose a named group first.")
            return False
        category_name = parts[0] if parts[0] in CATEGORY_ORDER else "Other"
        group_path = parts[1:]
        for item in selected_items:
            item.setData(0, QtCore.Qt.UserRole, category_name)
            item.setData(0, QtCore.Qt.UserRole + 6, list(group_path))
        records = self.panel.current_records()
        self.panel.set_records(
            records,
            source_root=self.panel.controls_root_text(),
            geometry_root=self.panel.geometry_root_text(),
            skeleton_root=self.panel.skeleton_root_text(),
            custom_sets=self.panel.current_custom_sets(),
        )
        self._save_from_panel()
        self.panel.set_status(
            "Moved {0} control(s) to {1}.".format(len(selected_items), " / ".join(parts))
        )
        return True

    def create_or_update_custom_set(self, set_name):
        if not self.panel:
            return False
        set_name = str(set_name or "").strip()
        if not set_name:
            self.panel.set_status("Type a custom set name first.")
            return False
        members = self.panel.selected_maya_names()
        if not members:
            self.panel.set_status("Select controls or groups first.")
            return False
        custom_sets = self.panel.current_custom_sets()
        match = None
        for custom_set in custom_sets:
            if (custom_set.get("name") or "").casefold() == set_name.casefold():
                match = custom_set
                break
        if match is None:
            custom_sets.append({"name": set_name, "members": list(members)})
            action = "Created"
        else:
            match["name"] = set_name
            match["members"] = list(members)
            action = "Updated"
        self.panel.set_custom_sets(custom_sets, preserve_selection=members)
        self._save_from_panel()
        self.panel.set_status("{0} custom set '{1}' with {2} control(s).".format(action, set_name, len(members)))
        return True

    def delete_selected_custom_sets(self):
        if not self.panel:
            return False
        names = self.panel.selected_custom_set_names()
        if not names:
            self.panel.set_status("Pick one or more custom set rows first.")
            return False
        lowered = {name.casefold() for name in names}
        custom_sets = [
            custom_set
            for custom_set in self.panel.current_custom_sets()
            if (custom_set.get("name") or "").casefold() not in lowered
        ]
        self.panel.set_custom_sets(custom_sets)
        self._save_from_panel()
        self.panel.set_status("Deleted {0} custom set(s).".format(len(names)))
        return True

    def move_selected(self, delta):
        if not self.panel:
            return False
        item = self.panel.current_control_item()
        if not item:
            self.panel.set_status("Pick one control row first.")
            return False
        return self.panel.move_item(item, delta)

    def refresh_attrs(self):
        if not self.panel:
            return []
        item = self.panel.current_control_item()
        if not item:
            self.panel.set_attr_items([])
            self.panel.set_status("Pick one control row first.")
            return []
        maya_name = item.data(0, QtCore.Qt.UserRole + 2)
        attrs = _keyable_attrs(maya_name)
        self.panel.set_attr_items(attrs)
        self.panel.set_status("{0}: {1} attr(s).".format(_short_name(maya_name), len(attrs)))
        return attrs

    def key_attrs(self, all_attrs=False):
        if not MAYA_AVAILABLE or not cmds or not self.panel:
            return False
        selected_names = self.panel.selected_maya_names()
        if not selected_names:
            self.panel.set_status("Pick a control row first.")
            return False
        mixed_groups = self.panel.mixed_fkik_groups(selected_names)
        if mixed_groups:
            self.panel.set_status(
                "Stopped: this selection mixes FK and IK for {0}. Pick one mode before keying.".format(
                    ", ".join(mixed_groups)
                )
            )
            return False
        attr_names = self.panel.checked_attr_names() if not all_attrs else self.panel.all_attr_names()
        if not attr_names:
            self.panel.set_status("No attrs to key.")
            return False
        current_frame = _current_frame()
        for maya_name in selected_names:
            if not cmds.objExists(maya_name):
                continue
            for attr_name in attr_names:
                try:
                    if cmds.attributeQuery(attr_name, node=maya_name, exists=True):
                        cmds.setKeyframe(maya_name, attribute=attr_name, time=(current_frame,))
                except Exception:
                    continue
        self.panel.set_status("Keyed {0} attr(s).".format(len(attr_names)))
        return True

    def toggle_fkik(self):
        if not MAYA_AVAILABLE or not cmds or not self.panel:
            return False
        selected_names = self.panel.selected_maya_names()
        if not selected_names:
            self.panel.set_status("Pick a control row first.")
            return False
        hit_count = 0
        for maya_name in selected_names:
            attrs = _keyable_attrs(maya_name)
            chosen_attr = None
            for attr_name in attrs:
                attr_low = attr_name.lower()
                if ("fk" in attr_low and "ik" in attr_low) or attr_low in {"switch", "ikfk", "fkik", "fk_ik", "ik_fk"}:
                    chosen_attr = attr_name
                    break
            if not chosen_attr:
                continue
            full_plug = maya_name + "." + chosen_attr
            try:
                if not cmds.attributeQuery(chosen_attr, node=maya_name, exists=True):
                    continue
                current_value = cmds.getAttr(full_plug)
                new_value = 0 if float(current_value or 0.0) > 0.5 else 1
                cmds.setAttr(full_plug, new_value)
                cmds.setKeyframe(maya_name, attribute=chosen_attr, time=(_current_frame(),))
                hit_count += 1
            except Exception:
                continue
        if hit_count:
            self.panel.set_status("Toggled FK/IK on {0} control(s).".format(hit_count))
            return True
        self.panel.set_status("No FK/IK switch attr found.")
        return False

    def _save_from_panel(self):
        if not self.panel:
            return
        self.save_state(
            source_root=self.panel.source_root_text(),
            geometry_root=self.panel.geometry_root_text(),
            skeleton_root=self.panel.skeleton_root_text(),
            records=self.panel.current_records(),
            custom_sets=self.panel.current_custom_sets(),
        )


class ControlPickerPanel(QtWidgets.QWidget):
    def __init__(self, controller=None, parent=None):
        super(ControlPickerPanel, self).__init__(parent)
        self.controller = controller or ControlPickerController()
        self.controller.bind(self)
        self._updating_tree = False
        self._syncing_selection = False
        self._selection_lock_until = 0.0
        self._visual_marquee_targets = set()
        self._visual_marquee_band = None
        self._visual_marquee_source = None
        self._visual_marquee_origin = None
        self._visual_marquee_active = False
        self._visual_marquee_additive = False
        self._maya_selection_signature = ()
        self._explicit_selected_names = []
        self._custom_sets = []
        self.items_by_maya_name = {}
        self.visual_buttons_by_maya_name = {}
        self._visual_button_pool = []
        self.selection_timer = QtCore.QTimer(self)
        self.selection_timer.setInterval(CONTROL_PICKER_SELECTION_SYNC_MS)
        self.selection_timer.timeout.connect(self.sync_selection_from_maya)
        self._build_ui()
        self._load_initial_state()
        if MAYA_AVAILABLE:
            self.selection_timer.start()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)
        intro = QtWidgets.QLabel(
            "Choose one rig root. Aminate scans its controls, hierarchy, side, body area, and FK/IK mode, then builds selection groups and a live position map that also works for animals."
        )
        intro.setWordWrap(True)
        main_layout.addWidget(intro)

        root_grid = QtWidgets.QGridLayout()
        self.controls_root_edit = QtWidgets.QLineEdit()
        self.controls_root_edit.setPlaceholderText("Controls root or selected rig root")
        self.controls_root_edit.setMinimumWidth(0)
        self.controls_root_edit.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        root_grid.addWidget(QtWidgets.QLabel("Controls Root"), 0, 0)
        root_grid.addWidget(self.controls_root_edit, 0, 1)
        self.use_selected_controls_root_button = QtWidgets.QPushButton("Use Selected")
        self.use_selected_controls_root_button.clicked.connect(self._use_selected_controls_root)
        root_grid.addWidget(self.use_selected_controls_root_button, 0, 2)

        self.geometry_root_edit = QtWidgets.QLineEdit()
        self.geometry_root_edit.setPlaceholderText("Geometry root or selected geo group")
        self.geometry_root_edit.setMinimumWidth(0)
        self.geometry_root_edit.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        root_grid.addWidget(QtWidgets.QLabel("Geometry Root"), 1, 0)
        root_grid.addWidget(self.geometry_root_edit, 1, 1)
        self.use_selected_geometry_root_button = QtWidgets.QPushButton("Use Selected")
        self.use_selected_geometry_root_button.clicked.connect(self._use_selected_geometry_root)
        root_grid.addWidget(self.use_selected_geometry_root_button, 1, 2)

        self.skeleton_root_edit = QtWidgets.QLineEdit()
        self.skeleton_root_edit.setPlaceholderText("Skeleton root or selected joint group")
        self.skeleton_root_edit.setMinimumWidth(0)
        self.skeleton_root_edit.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        root_grid.addWidget(QtWidgets.QLabel("Skeleton Root"), 2, 0)
        root_grid.addWidget(self.skeleton_root_edit, 2, 1)
        self.use_selected_skeleton_root_button = QtWidgets.QPushButton("Use Selected")
        self.use_selected_skeleton_root_button.clicked.connect(self._use_selected_skeleton_root)
        root_grid.addWidget(self.use_selected_skeleton_root_button, 2, 2)
        root_grid.setColumnStretch(1, 1)
        main_layout.addLayout(root_grid)

        root_row = QtWidgets.QGridLayout()
        root_row.setHorizontalSpacing(6)
        root_row.setVerticalSpacing(6)
        self.scan_selected_button = QtWidgets.QPushButton("Scan Selected Rig")
        self.scan_selected_button.setToolTip("Use the selected rig root and scan its controls now.")
        self.scan_selected_button.clicked.connect(self._use_selected_controls_root)
        root_row.addWidget(self.scan_selected_button, 0, 0)
        self.scan_scene_button = QtWidgets.QPushButton("Scan All")
        self.scan_scene_button.clicked.connect(self._scan_scene)
        root_row.addWidget(self.scan_scene_button, 0, 1)
        self.reload_button = QtWidgets.QPushButton("Reload Saved")
        self.reload_button.clicked.connect(self._reload_saved)
        root_row.addWidget(self.reload_button, 1, 0)
        self.save_button = QtWidgets.QPushButton("Save Layout")
        self.save_button.clicked.connect(self.save_layout)
        root_row.addWidget(self.save_button, 1, 1)
        root_row.setColumnStretch(0, 1)
        root_row.setColumnStretch(1, 1)
        main_layout.addLayout(root_row)

        action_row = QtWidgets.QGridLayout()
        action_row.setHorizontalSpacing(6)
        action_row.setVerticalSpacing(6)
        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.addItems(list(CATEGORY_ORDER))
        action_row.addWidget(self.category_combo, 0, 0, 1, 2)
        self.add_selected_button = QtWidgets.QPushButton("Add Selected")
        self.add_selected_button.clicked.connect(self._add_selected)
        action_row.addWidget(self.add_selected_button, 1, 0)
        self.remove_selected_button = QtWidgets.QPushButton("Remove Selected")
        self.remove_selected_button.clicked.connect(self._remove_selected)
        action_row.addWidget(self.remove_selected_button, 1, 1)
        self.select_in_maya_button = QtWidgets.QPushButton("Select In Maya")
        self.select_in_maya_button.clicked.connect(self.controller.select_in_maya)
        action_row.addWidget(self.select_in_maya_button, 2, 0)
        self.move_up_button = QtWidgets.QPushButton("Move Up")
        self.move_up_button.clicked.connect(lambda: self.controller.move_selected(-1))
        action_row.addWidget(self.move_up_button, 2, 1)
        self.move_down_button = QtWidgets.QPushButton("Move Down")
        self.move_down_button.clicked.connect(lambda: self.controller.move_selected(1))
        action_row.addWidget(self.move_down_button, 3, 0, 1, 2)
        action_row.setColumnStretch(0, 1)
        action_row.setColumnStretch(1, 1)
        main_layout.addLayout(action_row)

        label_row = QtWidgets.QGridLayout()
        label_row.setHorizontalSpacing(6)
        label_row.setVerticalSpacing(6)
        self.label_edit = QtWidgets.QLineEdit()
        self.label_edit.setPlaceholderText("Display label for selected row")
        label_row.addWidget(self.label_edit, 0, 0, 1, 2)
        self.apply_label_button = QtWidgets.QPushButton("Apply Label")
        self.apply_label_button.clicked.connect(self._apply_label)
        label_row.addWidget(self.apply_label_button, 1, 0)
        self.apply_category_button = QtWidgets.QPushButton("Apply Category")
        self.apply_category_button.clicked.connect(self._apply_category)
        label_row.addWidget(self.apply_category_button, 1, 1)
        self.group_path_combo = QtWidgets.QComboBox()
        self.group_path_combo.addItems(list(MANUAL_GROUP_PATHS))
        self.group_path_combo.setToolTip("Move all selected controls into this picker group.")
        label_row.addWidget(self.group_path_combo, 2, 0, 1, 2)
        self.apply_group_button = QtWidgets.QPushButton("Move Selected To Group")
        self.apply_group_button.clicked.connect(self._apply_group)
        label_row.addWidget(self.apply_group_button, 3, 0, 1, 2)
        self.toggle_fkik_button = QtWidgets.QPushButton("Toggle FK/IK")
        self.toggle_fkik_button.clicked.connect(self.controller.toggle_fkik)
        label_row.addWidget(self.toggle_fkik_button, 4, 0, 1, 2)
        label_row.setColumnStretch(0, 1)
        label_row.setColumnStretch(1, 1)
        main_layout.addLayout(label_row)

        custom_row = QtWidgets.QGridLayout()
        custom_row.setHorizontalSpacing(6)
        custom_row.setVerticalSpacing(6)
        self.custom_set_name_edit = QtWidgets.QLineEdit()
        self.custom_set_name_edit.setPlaceholderText("Custom set name, for example Tail + Left Arm")
        custom_row.addWidget(self.custom_set_name_edit, 0, 0, 1, 2)
        self.create_custom_set_button = QtWidgets.QPushButton("Create / Update From Selection")
        self.create_custom_set_button.clicked.connect(self._create_or_update_custom_set)
        custom_row.addWidget(self.create_custom_set_button, 1, 0)
        self.delete_custom_set_button = QtWidgets.QPushButton("Delete Custom Set")
        self.delete_custom_set_button.clicked.connect(self.controller.delete_selected_custom_sets)
        custom_row.addWidget(self.delete_custom_set_button, 1, 1)
        custom_row.setColumnStretch(0, 1)
        custom_row.setColumnStretch(1, 1)
        main_layout.addLayout(custom_row)

        self.view_tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.view_tabs, 1)

        self.list_page = QtWidgets.QWidget()
        list_layout = QtWidgets.QVBoxLayout(self.list_page)
        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Horizontal)
        list_layout.addWidget(splitter, 1)

        self.tree = ControlPickerTree()
        self.tree.setHeaderLabels(["Control Picker"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        self.tree.setDragEnabled(False)
        self.tree.setAcceptDrops(False)
        self.tree.setDropIndicatorShown(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.tree.layoutChanged.connect(self._on_layout_changed)
        self.tree.selectionMarqueeRequested.connect(self._on_tree_marquee_requested)
        splitter.addWidget(self.tree)

        inspector = QtWidgets.QWidget()
        inspector_layout = QtWidgets.QVBoxLayout(inspector)
        self.details_label = QtWidgets.QLabel("Pick one control to see attrs.")
        self.details_label.setWordWrap(True)
        inspector_layout.addWidget(self.details_label)
        self.attr_list = QtWidgets.QListWidget()
        self.attr_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        inspector_layout.addWidget(self.attr_list, 1)
        key_row = QtWidgets.QGridLayout()
        key_row.setHorizontalSpacing(6)
        key_row.setVerticalSpacing(6)
        self.refresh_attrs_button = QtWidgets.QPushButton("Refresh Attrs")
        self.refresh_attrs_button.clicked.connect(self.controller.refresh_attrs)
        key_row.addWidget(self.refresh_attrs_button, 0, 0)
        self.key_selected_button = QtWidgets.QPushButton("Key Selected Attrs")
        self.key_selected_button.clicked.connect(lambda: self.controller.key_attrs(all_attrs=False))
        key_row.addWidget(self.key_selected_button, 0, 1)
        self.key_all_button = QtWidgets.QPushButton("Key All Attrs")
        self.key_all_button.clicked.connect(lambda: self.controller.key_attrs(all_attrs=True))
        key_row.addWidget(self.key_all_button, 1, 0, 1, 2)
        key_row.setColumnStretch(0, 1)
        key_row.setColumnStretch(1, 1)
        inspector_layout.addLayout(key_row)
        splitter.addWidget(inspector)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        self.view_tabs.addTab(self.list_page, "List")

        self.visual_page = QtWidgets.QWidget()
        visual_layout = QtWidgets.QVBoxLayout(self.visual_page)
        self.visual_hint_label = QtWidgets.QLabel("Click a chip to select it in Maya. Checked chips follow the viewport.")
        self.visual_hint_label.setWordWrap(True)
        visual_layout.addWidget(self.visual_hint_label)
        visual_controls = QtWidgets.QHBoxLayout()
        visual_controls.addWidget(QtWidgets.QLabel("Map View"))
        self.visual_view_combo = QtWidgets.QComboBox()
        self.visual_view_combo.addItems(["Front (X / Y)", "Side (Z / Y)"])
        self.visual_view_combo.currentIndexChanged.connect(self.rebuild_visual_layout)
        visual_controls.addWidget(self.visual_view_combo, 1)
        self.refresh_live_map_button = QtWidgets.QPushButton("Refresh Live Rig Map")
        self.refresh_live_map_button.clicked.connect(self._refresh_live_map)
        visual_controls.addWidget(self.refresh_live_map_button)
        visual_layout.addLayout(visual_controls)
        self.visual_scroll = QtWidgets.QScrollArea()
        self.visual_scroll.setWidgetResizable(True)
        self.visual_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.visual_canvas = ControlPickerVisualCanvas(self)
        self.visual_canvas.selectionMarqueeRequested.connect(self._on_visual_marquee_requested)
        self._visual_marquee_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self.visual_canvas)
        self._visual_marquee_band.hide()
        self.visual_scroll.setWidget(self.visual_canvas)
        visual_layout.addWidget(self.visual_scroll, 1)
        self.view_tabs.addTab(self.visual_page, "Visual")

        self.selection_summary_label = QtWidgets.QLabel("Nothing selected.")
        self.selection_summary_label.setObjectName("aminateControlPickerSelectionSummary")
        self.selection_summary_label.setWordWrap(True)
        self.selection_summary_label.setStyleSheet(
            "QLabel#aminateControlPickerSelectionSummary {"
            "background:#1D2A34; border:1px solid #52697A; border-radius:6px;"
            "padding:6px 8px; color:#F7F9FB; font-weight:600; }"
        )
        main_layout.addWidget(self.selection_summary_label)
        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

    def _load_initial_state(self):
        state = self.controller.load_state()
        records = _records_from_state(state)
        if records:
            self.set_records(
                records,
                source_root=state.get("source_root") or "",
                geometry_root=state.get("geometry_root") or "",
                skeleton_root=state.get("skeleton_root") or "",
                custom_sets=state.get("custom_sets") or [],
            )
            self.set_status("Loaded saved picker.")
            return
        selected_root = self.controls_root_edit.text().strip()
        if selected_root:
            self.controller.scan_scene(root=selected_root)
            return
        self.controller.scan_scene(root=_current_source_root_from_state() or "")

    def set_status(self, message):
        self.status_label.setText(message or "Ready.")

    def controls_root_text(self):
        return self.controls_root_edit.text().strip()

    def geometry_root_text(self):
        return self.geometry_root_edit.text().strip()

    def skeleton_root_text(self):
        return self.skeleton_root_edit.text().strip()

    def source_root_text(self):
        return self.controls_root_text()

    def set_controls_root_text(self, value):
        self.controls_root_edit.setText(value or "")

    def set_geometry_root_text(self, value):
        self.geometry_root_edit.setText(value or "")

    def set_skeleton_root_text(self, value):
        self.skeleton_root_edit.setText(value or "")

    def set_source_root_text(self, value):
        self.set_controls_root_text(value)

    def current_records(self):
        records = []

        def _collect_children(parent_item, category_name):
            for index in range(parent_item.childCount()):
                child_item = parent_item.child(index)
                kind = _tree_item_kind(child_item)
                if kind == "control":
                    records.append(
                        {
                            "maya_name": child_item.data(0, QtCore.Qt.UserRole + 2),
                            "label": child_item.data(0, QtCore.Qt.UserRole + 4) or _clean_record_label(child_item.text(0)),
                            "category": category_name,
                            "side": child_item.data(0, QtCore.Qt.UserRole + 3) or _side_from_name(child_item.data(0, QtCore.Qt.UserRole + 2) or ""),
                            "group_path": list(child_item.data(0, QtCore.Qt.UserRole + 6) or []),
                            "world_position": child_item.data(0, QtCore.Qt.UserRole + 7) or _world_position(child_item.data(0, QtCore.Qt.UserRole + 2) or ""),
                        }
                    )
                elif kind == "group":
                    _collect_children(child_item, category_name)

        for category_name in CATEGORY_ORDER:
            category_item = self.category_item(category_name)
            if category_item:
                _collect_children(category_item, category_name)
        return records

    def current_custom_sets(self):
        valid_names = set(self.current_record_names())
        custom_sets = []
        for custom_set in self._custom_sets:
            name = str(custom_set.get("name") or "").strip()
            members = [
                _node_long_name(member)
                for member in (custom_set.get("members") or [])
                if member and _node_long_name(member) in valid_names
            ]
            if name:
                custom_sets.append({"name": name, "members": _dedupe_preserve_order(members)})
        return custom_sets

    def selected_custom_set_names(self):
        names = []
        for item in self.tree.selectedItems():
            if _tree_item_kind(item) != "custom_set":
                continue
            name = _tree_item_base_label(item)
            if name and name not in names:
                names.append(name)
        return names

    def set_custom_sets(self, custom_sets, preserve_selection=None):
        all_records = self.current_records()
        records = all_records[:MAX_VISUAL_BUTTONS]
        if len(all_records) > MAX_VISUAL_BUTTONS and hasattr(self, "visual_hint_label"):
            self.visual_hint_label.setText(
                "Live map shows the first {0} of {1} controls for Maya safety. The List still contains every control.".format(
                    MAX_VISUAL_BUTTONS,
                    len(all_records),
                )
            )
        elif hasattr(self, "visual_hint_label"):
            self.visual_hint_label.setText(
                "Click a control or drag a marquee. Blue with a white outline means selected. Ctrl/Shift adds to the selection."
            )
        self._custom_sets = [
            {
                "name": str(custom_set.get("name") or "").strip(),
                "members": _dedupe_preserve_order(
                    [_node_long_name(member) for member in (custom_set.get("members") or []) if member]
                ),
            }
            for custom_set in (custom_sets or [])
            if str(custom_set.get("name") or "").strip()
        ]
        self.set_records(
            records,
            source_root=self.controls_root_text(),
            geometry_root=self.geometry_root_text(),
            skeleton_root=self.skeleton_root_text(),
            custom_sets=self._custom_sets,
        )
        if preserve_selection:
            self.set_selected_maya_names(preserve_selection, update_maya=False)

    def selected_control_items(self):
        items = []
        for item in self.tree.selectedItems():
            items.extend(_tree_item_control_items(item))
        if not items:
            current = self.current_control_item()
            if current:
                items.append(current)
        return _dedupe_preserve_order(items)

    def selected_maya_names(self):
        names = []
        for item in self.tree.selectedItems():
            if _tree_item_kind(item) == "custom_set":
                for maya_name in item.data(0, QtCore.Qt.UserRole + 5) or []:
                    maya_name = _node_long_name(maya_name)
                    if maya_name and maya_name not in names:
                        names.append(maya_name)
        for item in self.selected_control_items():
            maya_name = item.data(0, QtCore.Qt.UserRole + 2)
            if maya_name and maya_name not in names:
                names.append(maya_name)
        if not names:
            names = self.selected_visual_names()
        if self._explicit_selected_names and len(names) < len(self._explicit_selected_names):
            names = list(self._explicit_selected_names)
        return names

    def mixed_fkik_groups(self, maya_names):
        record_by_name = {record.get("maya_name"): record for record in self.current_records()}
        modes_by_group = {}
        for maya_name in maya_names or []:
            record = record_by_name.get(_node_long_name(maya_name))
            if not record:
                continue
            group_path = _record_group_path(record)
            mode = _record_mode(record)
            if mode not in ("FK", "IK") or not group_path:
                continue
            base_group = group_path[0]
            modes_by_group.setdefault(base_group, set()).add(mode)
        return sorted(group_name for group_name, modes in modes_by_group.items() if {"FK", "IK"}.issubset(modes))

    def _update_selection_summary(self, maya_names=None, selected_items=None):
        maya_names = list(maya_names if maya_names is not None else self.selected_maya_names())
        selected_items = list(selected_items if selected_items is not None else self.tree.selectedItems())
        group_labels = []
        for item in selected_items:
            if _tree_item_kind(item) in ("category", "group", "custom_set"):
                label = _tree_item_base_label(item)
                if label and label not in group_labels:
                    group_labels.append(label)
        mode_counts = {"FK": 0, "IK": 0, "Switch": 0, "Shared": 0}
        record_by_name = {record.get("maya_name"): record for record in self.current_records()}
        for maya_name in maya_names:
            record = record_by_name.get(_node_long_name(maya_name))
            mode_counts[_record_mode(record or {"maya_name": maya_name})] += 1
        parts = ["{0} control(s) selected".format(len(maya_names))]
        if group_labels:
            parts.append("Groups: " + ", ".join(group_labels[:4]))
        active_modes = ["{0} {1}".format(count, mode) for mode, count in mode_counts.items() if count]
        if active_modes:
            parts.append("Modes: " + ", ".join(active_modes))
        mixed = self.mixed_fkik_groups(maya_names)
        if mixed:
            parts.append("Warning: FK + IK mixed for " + ", ".join(mixed))
        self.selection_summary_label.setText("  •  ".join(parts) if maya_names else "Nothing selected.")

    def selected_visual_names(self):
        names = []
        dead_buttons = []
        for maya_name in self.current_record_names():
            button = self.visual_buttons_by_maya_name.get(maya_name)
            if not button:
                continue
            try:
                checked = button.isChecked()
            except RuntimeError:
                dead_buttons.append(maya_name)
                continue
            if checked and maya_name not in names:
                names.append(maya_name)
        for maya_name in dead_buttons:
            self.visual_buttons_by_maya_name.pop(maya_name, None)
        return names

    def _install_visual_marquee_filter(self, widget):
        if not widget:
            return
        self._visual_marquee_targets.add(widget)
        try:
            widget.installEventFilter(self)
        except Exception:
            pass

    def _reset_visual_marquee_state(self):
        self._visual_marquee_source = None
        self._visual_marquee_origin = None
        self._visual_marquee_active = False
        self._visual_marquee_additive = False
        if self._visual_marquee_band:
            self._visual_marquee_band.hide()

    def _show_visual_marquee_band(self, rect):
        if not self._visual_marquee_band:
            self._visual_marquee_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self.visual_canvas)
        self._visual_marquee_band.setGeometry(rect.normalized())
        self._visual_marquee_band.show()

    def _hide_visual_marquee_band(self):
        if self._visual_marquee_band:
            self._visual_marquee_band.hide()

    def eventFilter(self, obj, event):
        if obj in self._visual_marquee_targets:
            event_type = event.type()
            if event_type == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                self._visual_marquee_source = obj
                self._visual_marquee_origin = obj.mapTo(self.visual_canvas, event.pos())
                self._visual_marquee_active = False
                self._visual_marquee_additive = bool(event.modifiers() & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier))
                self._hide_visual_marquee_band()
                return False
            if event_type == QtCore.QEvent.MouseMove and self._visual_marquee_source is obj and (event.buttons() & QtCore.Qt.LeftButton):
                current = obj.mapTo(self.visual_canvas, event.pos())
                if not self._visual_marquee_active and (current - self._visual_marquee_origin).manhattanLength() < QtWidgets.QApplication.startDragDistance():
                    return False
                self._visual_marquee_active = True
                self._show_visual_marquee_band(QtCore.QRect(self._visual_marquee_origin, current).normalized())
                return True
            if event_type == QtCore.QEvent.MouseButtonRelease and self._visual_marquee_source is obj and event.button() == QtCore.Qt.LeftButton:
                current = obj.mapTo(self.visual_canvas, event.pos())
                if self._visual_marquee_active:
                    rect = QtCore.QRect(self._visual_marquee_origin, current).normalized()
                    self._hide_visual_marquee_band()
                    self._on_visual_marquee_requested(rect, self._visual_marquee_additive)
                    self._reset_visual_marquee_state()
                    return True
                self._reset_visual_marquee_state()
                return False
        return super(ControlPickerPanel, self).eventFilter(obj, event)

    def current_record_names(self):
        return [record.get("maya_name") for record in self.current_records() if record.get("maya_name")]

    def current_control_item(self):
        item = self.tree.currentItem()
        if item and _tree_item_kind(item) == "control":
            return item
        return None

    def item_for_maya_name(self, maya_name):
        return self.items_by_maya_name.get(_node_long_name(maya_name))

    def set_selected_maya_names(self, maya_names, update_maya=False):
        maya_names = [_node_long_name(name) for name in (maya_names or []) if name]
        maya_names = [name for name in _dedupe_preserve_order(maya_names) if self.item_for_maya_name(name) or self.visual_buttons_by_maya_name.get(name)]
        self._explicit_selected_names = list(maya_names)
        self._syncing_selection = True
        try:
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            for name in maya_names:
                item = self.item_for_maya_name(name)
                if item:
                    item.setSelected(True)
            if maya_names:
                first_item = self.item_for_maya_name(maya_names[0])
                if first_item:
                    self.tree.setCurrentItem(first_item)
            self._sync_visual_selection(maya_names)
            if not maya_names:
                self.set_attr_items([])
                self.details_label.setText("Pick one control to see attrs.")
                self.label_edit.setText("")
        finally:
            self.tree.blockSignals(False)
            self._syncing_selection = False
        if update_maya and MAYA_AVAILABLE and cmds:
            self._selection_lock_until = time.time() + CONTROL_PICKER_SELECTION_LOCK_SECONDS
            try:
                if maya_names:
                    cmds.select(maya_names, replace=True)
                else:
                    cmds.select(clear=True)
            except Exception:
                pass
        self._maya_selection_signature = tuple(maya_names)
        if maya_names:
            self._update_status_from_tree()
        self._update_selection_summary(maya_names=maya_names)
        return maya_names

    def _sync_visual_selection(self, maya_names):
        names = set(maya_names or [])
        dead_buttons = []
        for name, button in self.visual_buttons_by_maya_name.items():
            try:
                button.blockSignals(True)
                button.setChecked(name in names)
            except RuntimeError:
                dead_buttons.append(name)
            finally:
                try:
                    button.blockSignals(False)
                except RuntimeError:
                    pass
        for name in dead_buttons:
            self.visual_buttons_by_maya_name.pop(name, None)

    def sync_selection_from_maya(self):
        if self._syncing_selection or not MAYA_AVAILABLE or not cmds:
            return []
        if time.time() < self._selection_lock_until:
            return self.selected_maya_names()
        try:
            maya_names = _selection_transforms()
        except Exception:
            maya_names = []
        signature = tuple(maya_names)
        if signature == self._maya_selection_signature:
            return maya_names
        self.set_selected_maya_names(maya_names, update_maya=False)
        return maya_names

    def category_item(self, category_name):
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if _tree_item_base_label(item) == category_name:
                return item
        return None

    def group_item(self, category_name, group_name):
        category_item = self.category_item(category_name)
        if not category_item or not group_name:
            return None
        for index in range(category_item.childCount()):
            item = category_item.child(index)
            if _tree_item_kind(item) == "group" and _tree_item_base_label(item) == group_name:
                return item
        return None

    def rebuild_category_headers(self):
        def _update_item(item):
            kind = _tree_item_kind(item)
            if kind in ("category", "group"):
                base_label = _tree_item_base_label(item)
                item.setText(0, "{0} ({1})".format(base_label, _count_tree_controls(item)))
                item.setForeground(0, QtGui.QBrush(_category_color(item.data(0, QtCore.Qt.UserRole) or base_label)))
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            for index in range(item.childCount()):
                child_item = item.child(index)
                if _tree_item_kind(child_item) in ("group", "control"):
                    _update_item(child_item)

        for category_name in CATEGORY_ORDER:
            item = self.category_item(category_name)
            if item:
                _update_item(item)

    def first_control_item(self, item):
        if not item:
            return None
        kind = _tree_item_kind(item)
        if kind == "control":
            return item
        for index in range(item.childCount()):
            child_item = item.child(index)
            found = self.first_control_item(child_item)
            if found:
                return found
        return None

    def set_attr_items(self, attr_names):
        self.attr_list.clear()
        for attr_name in attr_names:
            item = QtWidgets.QListWidgetItem(attr_name)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            self.attr_list.addItem(item)

    def checked_attr_names(self):
        names = []
        for index in range(self.attr_list.count()):
            item = self.attr_list.item(index)
            if item.checkState() == QtCore.Qt.Checked:
                names.append(item.text())
        return names

    def all_attr_names(self):
        return [self.attr_list.item(index).text() for index in range(self.attr_list.count())]

    def set_records(self, records, source_root="", geometry_root="", skeleton_root="", custom_sets=None):
        previous_selection = self.selected_maya_names()
        if custom_sets is not None:
            self._custom_sets = [
                {
                    "name": str(custom_set.get("name") or "").strip(),
                    "members": _dedupe_preserve_order(
                        [_node_long_name(member) for member in (custom_set.get("members") or []) if member]
                    ),
                }
                for custom_set in custom_sets
                if str(custom_set.get("name") or "").strip()
            ]
        self._updating_tree = True
        try:
            self.tree.clear()
            self.items_by_maya_name = {}
            category_items = {}
            subgroup_items = {}
            for category_name in CATEGORY_ORDER:
                category_item = QtWidgets.QTreeWidgetItem([category_name + " (0)"])
                category_item.setData(0, QtCore.Qt.UserRole + 1, "category")
                category_item.setData(0, QtCore.Qt.UserRole + 4, category_name)
                category_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                category_item.setExpanded(True)
                category_item.setForeground(0, QtGui.QBrush(_category_color(category_name)))
                self.tree.addTopLevelItem(category_item)
                category_items[category_name] = category_item
                subgroup_items[category_name] = {}

            def ensure_subgroup_path(category_name, group_path):
                group_path = tuple(group_path or ())
                if not group_path:
                    return category_items.get(category_name)
                if category_name not in subgroup_items:
                    return category_items.get(category_name)
                parent_item = category_items.get(category_name)
                built_path = []
                for depth, group_name in enumerate(group_path):
                    built_path.append(group_name)
                    path_key = tuple(built_path)
                    group_item = subgroup_items[category_name].get(path_key)
                    if group_item is None:
                        group_item = QtWidgets.QTreeWidgetItem([group_name + " (0)"])
                        group_item.setData(0, QtCore.Qt.UserRole + 1, "group")
                        group_item.setData(0, QtCore.Qt.UserRole, category_name)
                        group_item.setData(0, QtCore.Qt.UserRole + 4, group_name)
                        group_item.setData(0, QtCore.Qt.UserRole + 6, list(path_key))
                        group_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                        group_item.setExpanded(depth == 0)
                        group_item.setForeground(0, QtGui.QBrush(_category_color(category_name)))
                        if depth == 0:
                            insert_index = _group_insert_index(parent_item, category_name, group_name)
                            parent_item.insertChild(insert_index, group_item)
                        else:
                            parent_item.addChild(group_item)
                        subgroup_items[category_name][path_key] = group_item
                    parent_item = group_item
                return parent_item

            for record in records:
                category_name = record.get("category") or "Other"
                if category_name not in category_items:
                    category_name = "Other"
                maya_name = record.get("maya_name") or ""
                parent_item = category_items[category_name]
                group_path = _record_group_path(record)
                if group_path:
                    parent_item = ensure_subgroup_path(category_name, group_path) or parent_item
                child_item = QtWidgets.QTreeWidgetItem([_display_label_for_record(record)])
                child_item.setData(0, QtCore.Qt.UserRole + 1, "control")
                child_item.setData(0, QtCore.Qt.UserRole, category_name)
                child_item.setData(
                    0,
                    QtCore.Qt.UserRole + 4,
                    _clean_record_label(record.get("label")) or _short_name(maya_name),
                )
                child_item.setData(0, QtCore.Qt.UserRole + 2, maya_name)
                child_item.setData(0, QtCore.Qt.UserRole + 3, record.get("side") or _side_from_name(maya_name))
                child_item.setData(0, QtCore.Qt.UserRole + 6, list(group_path))
                child_item.setData(0, QtCore.Qt.UserRole + 7, record.get("world_position") or _world_position(maya_name))
                child_item.setToolTip(
                    0,
                    "Category: {0}\nGroup: {1}\nMode: {2}\nSide: {3}\nNode: {4}".format(
                        category_name,
                        " / ".join(group_path),
                        _record_mode(record),
                        child_item.data(0, QtCore.Qt.UserRole + 3) or "Unknown",
                        maya_name,
                    ),
                )
                child_item.setFlags(
                    QtCore.Qt.ItemIsEnabled
                    | QtCore.Qt.ItemIsSelectable
                    | QtCore.Qt.ItemIsEditable
                )
                child_item.setForeground(0, QtGui.QBrush(_category_color(category_name)))
                parent_item.addChild(child_item)
                self.items_by_maya_name[maya_name] = child_item

            valid_names = set(self.items_by_maya_name)
            custom_root = QtWidgets.QTreeWidgetItem([CUSTOM_SETS_LABEL + " (0)"])
            custom_root.setData(0, QtCore.Qt.UserRole + 1, "category")
            custom_root.setData(0, QtCore.Qt.UserRole + 4, CUSTOM_SETS_LABEL)
            custom_root.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            custom_root.setExpanded(True)
            custom_root.setForeground(0, QtGui.QBrush(QtGui.QColor("#B9A7FF")))
            self.tree.insertTopLevelItem(0, custom_root)
            clean_custom_sets = []
            for custom_set in self._custom_sets:
                set_name = str(custom_set.get("name") or "").strip()
                members = [
                    _node_long_name(member)
                    for member in (custom_set.get("members") or [])
                    if _node_long_name(member) in valid_names
                ]
                if not set_name:
                    continue
                members = _dedupe_preserve_order(members)
                clean_custom_sets.append({"name": set_name, "members": members})
                set_item = QtWidgets.QTreeWidgetItem(["{0} ({1})".format(set_name, len(members))])
                set_item.setData(0, QtCore.Qt.UserRole + 1, "custom_set")
                set_item.setData(0, QtCore.Qt.UserRole + 4, set_name)
                set_item.setData(0, QtCore.Qt.UserRole + 5, members)
                set_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                set_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#D8CEFF")))
                set_item.setToolTip(0, "Custom selection set with {0} control(s).".format(len(members)))
                custom_root.addChild(set_item)
            custom_root.setText(0, "{0} ({1})".format(CUSTOM_SETS_LABEL, len(clean_custom_sets)))
            self._custom_sets = clean_custom_sets
            self.set_source_root_text(source_root)
            self.set_geometry_root_text(geometry_root)
            self.set_skeleton_root_text(skeleton_root)
            self.rebuild_category_headers()
            self.rebuild_visual_layout()
            if previous_selection:
                self.set_selected_maya_names(previous_selection, update_maya=False)
            else:
                first_control = None
                for category_name in CATEGORY_ORDER:
                    category_item = category_items.get(category_name)
                    if category_item:
                        first_control = self.first_control_item(category_item)
                    if first_control:
                        break
                if first_control:
                    self.set_selected_maya_names([first_control.data(0, QtCore.Qt.UserRole + 2)], update_maya=False)
                elif self.tree.topLevelItemCount():
                    self.tree.setCurrentItem(self.tree.topLevelItem(0))
                self._update_status_from_tree()
        finally:
            self._updating_tree = False

    def rebuild_visual_layout(self, *args):
        selected_names = self.selected_maya_names()
        self._visual_marquee_targets = set()
        self._reset_visual_marquee_state()
        for old_button in self.visual_canvas.findChildren(QtWidgets.QToolButton):
            try:
                old_button.blockSignals(True)
                old_button.setChecked(False)
                old_button.hide()
                old_button.blockSignals(False)
            except Exception:
                pass
            if old_button not in self._visual_button_pool:
                self._visual_button_pool.append(old_button)
        self.visual_buttons_by_maya_name = {}
        records = self.current_records()
        for record in records:
            record["world_position"] = _world_position(record.get("maya_name")) or record.get("world_position")
        view_name = "Front" if not hasattr(self, "visual_view_combo") or self.visual_view_combo.currentIndex() == 0 else "Side"
        projected = _project_record_positions(records, view_name=view_name)
        self.visual_canvas.set_projected_points(projected, view_name=view_name)
        canvas_size = self.visual_canvas.sizeHint()
        self.visual_canvas.setMinimumSize(0, 0)
        self.visual_canvas.resize(canvas_size)
        occupied = {}
        for index, record in enumerate(records):
            maya_name = record.get("maya_name") or ""
            group_name = " / ".join(_record_group_path(record))
            if self._visual_button_pool:
                button = self._visual_button_pool.pop()
                button.setParent(self.visual_canvas)
            else:
                button = QtWidgets.QToolButton(self.visual_canvas)
                button.toggled.connect(self._on_visual_button_toggled)
            button.setCheckable(True)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            button.setText("")
            button.setAccessibleName(_display_label_for_record(record))
            button.setProperty("maya_name", maya_name)
            button.setProperty("category", record.get("category") or "Other")
            button.setProperty("group", group_name)
            button.setToolTip(
                "{0}\nGroup: {1}\nMode: {2}\nSide: {3}\nNode: {4}".format(
                    record.get("label") or _short_name(maya_name),
                    group_name,
                    _record_mode(record),
                    record.get("side") or _side_from_name(maya_name),
                    maya_name,
                )
            )
            side = record.get("side") or _side_from_name(maya_name)
            if side == "Left":
                accent = "#66D9EF"
            elif side == "Right":
                accent = "#FFAD66"
            elif side == "Center":
                accent = "#B0B8C0"
            else:
                accent = CATEGORY_COLORS.get(record.get("category") or "Other", CATEGORY_COLORS["Other"])
            button.setStyleSheet(
                "QToolButton {{ border:1px solid {0}; border-radius:7px; padding:0px;"
                "background:#24303A; color:#F7F9FB; }}"
                "QToolButton:hover {{ border:2px solid #FFFFFF; background:{0}; }}"
                "QToolButton:checked {{ border:2px solid #FFFFFF; background:#1677D2;"
                "color:#FFFFFF; font-weight:700; }}".format(accent)
            )
            button.setFixedSize(14, 14)
            point = projected.get(maya_name)
            if point:
                base_x = int(point[0] * canvas_size.width())
                base_y = int(point[1] * canvas_size.height())
            else:
                anchor_x, anchor_y = _visual_group_anchor(_visual_group_name(record))
                base_x, base_y = int(anchor_x), int(anchor_y)
            bucket = (int(base_x / 16), int(base_y / 16))
            collision_index = occupied.get(bucket, 0)
            occupied[bucket] = collision_index + 1
            offset_x = (collision_index % 5 - 2) * 10
            offset_y = ((collision_index // 5) % 5 - 2) * 10
            x = int(max(6, min(canvas_size.width() - button.width() - 6, base_x - button.width() * 0.5 + offset_x)))
            y = int(max(42, min(canvas_size.height() - button.height() - 6, base_y - button.height() * 0.5 + offset_y)))
            button.move(x, y)
            button.show()
            self.visual_buttons_by_maya_name[maya_name] = button
            self._install_visual_marquee_filter(button)
        self.visual_canvas.update()
        self._sync_visual_selection(selected_names)

    def _on_visual_button_toggled(self, checked):
        button = self.sender()
        maya_name = button.property("maya_name") if button else ""
        self._on_visual_chip_toggled(maya_name, checked)

    def _on_visual_chip_toggled(self, maya_name, checked):
        if self._syncing_selection:
            return
        if checked:
            current_names = [maya_name] if maya_name else []
        else:
            current_names = self.selected_visual_names()
            current_names = [name for name in current_names if name != maya_name]
        self.set_selected_maya_names(current_names, update_maya=True)

    def _on_visual_chip_clicked(self, maya_name):
        self._on_visual_chip_toggled(maya_name, True)

    def _on_visual_marquee_requested(self, rect, additive=False):
        if rect is None or rect.isNull():
            self.set_selected_maya_names([], update_maya=True)
            self.set_status("Selection cleared.")
            return
        hit_names = []
        for group_box in self.visual_canvas.findChildren(QtWidgets.QGroupBox):
            top_left = group_box.mapTo(self.visual_canvas, QtCore.QPoint(0, 0))
            group_size = group_box.sizeHint()
            if group_size.width() <= 1 or group_size.height() <= 1:
                group_size = group_box.size()
            group_rect = QtCore.QRect(top_left, group_size).normalized()
            if not (rect.intersects(group_rect) or rect.contains(group_rect.center())):
                continue
            for button in group_box.findChildren(QtWidgets.QToolButton):
                maya_name = button.property("maya_name")
                if maya_name and maya_name not in hit_names:
                    hit_names.append(maya_name)
        if not hit_names:
            for maya_name in self.current_record_names():
                button = self.visual_buttons_by_maya_name.get(maya_name)
                if not button:
                    continue
                top_left = button.mapTo(self.visual_canvas, QtCore.QPoint(0, 0))
                button_size = button.size()
                if button_size.width() <= 1 or button_size.height() <= 1:
                    button_size = button.sizeHint()
                button_rect = QtCore.QRect(top_left, button_size).normalized()
                if rect.intersects(button_rect) or rect.contains(button_rect.center()):
                    hit_names.append(maya_name)
        if len(hit_names) < 2 and rect.width() * rect.height() >= 20000:
            hit_names = [
                maya_name
                for maya_name in self.current_record_names()
                if self.visual_buttons_by_maya_name.get(maya_name)
            ]
        if additive:
            names = self.selected_maya_names()
        else:
            names = []
        for maya_name in hit_names:
            if maya_name not in names:
                names.append(maya_name)
        self.set_selected_maya_names(names, update_maya=True)
        if hit_names:
            self.set_status("Selected {0} control(s).".format(len(names)))
        else:
            self.set_status("No controls in marquee.")

    def _on_tree_marquee_requested(self, rect, additive=False):
        if rect is None or rect.isNull():
            self.set_selected_maya_names([], update_maya=True)
            self.set_status("Selection cleared.")
            return
        hit_names = []
        for record in self.current_records():
            maya_name = record.get("maya_name") or ""
            item = self.item_for_maya_name(maya_name)
            if not item:
                continue
            item_rect = self.tree.visualItemRect(item)
            if not item_rect.isValid():
                continue
            if rect.intersects(item_rect) or rect.contains(item_rect.center()):
                if maya_name not in hit_names:
                    hit_names.append(maya_name)
        if not hit_names and rect.width() * rect.height() >= 20000:
            hit_names = [record.get("maya_name") for record in self.current_records() if record.get("maya_name")]
        if additive:
            names = self.selected_maya_names()
        else:
            names = []
        for maya_name in hit_names:
            if maya_name and maya_name not in names:
                names.append(maya_name)
        self.set_selected_maya_names(names, update_maya=True)
        if hit_names:
            self.set_status("Selected {0} control(s).".format(len(names)))
        else:
            self.set_status("No controls in marquee.")

    def _on_tree_selection_changed(self):
        if self._syncing_selection:
            return
        selected_items = [item for item in self.tree.selectedItems() if item]
        names = self._selected_item_names_from_tree()
        if not names:
            names = self.selected_visual_names()
        self._explicit_selected_names = list(names)
        self._sync_visual_selection(names)
        self._update_selection_summary(maya_names=names, selected_items=selected_items)
        if not names:
            if MAYA_AVAILABLE and cmds:
                try:
                    cmds.select(clear=True)
                except Exception:
                    pass
            self._maya_selection_signature = ()
            return
        if any(_tree_item_kind(item) != "control" for item in selected_items):
            if MAYA_AVAILABLE and cmds:
                self._selection_lock_until = time.time() + CONTROL_PICKER_SELECTION_LOCK_SECONDS
                try:
                    cmds.select(names, replace=True)
                except Exception:
                    pass
            self._maya_selection_signature = tuple(names)
            group_names = [
                _tree_item_base_label(item)
                for item in selected_items
                if _tree_item_kind(item) in ("category", "group", "custom_set")
            ]
            if group_names:
                self.set_status(
                    "Selected {0} control(s) from {1}.".format(len(names), ", ".join(group_names))
                )
            return
        self.controller.select_in_maya()
        self._maya_selection_signature = tuple(names)

    def _selected_item_names_from_tree(self):
        names = []
        for item in self.tree.selectedItems():
            if _tree_item_kind(item) == "custom_set":
                for maya_name in item.data(0, QtCore.Qt.UserRole + 5) or []:
                    maya_name = _node_long_name(maya_name)
                    if maya_name and maya_name not in names:
                        names.append(maya_name)
        for item in self.selected_control_items():
            maya_name = item.data(0, QtCore.Qt.UserRole + 2)
            if maya_name and maya_name not in names:
                names.append(maya_name)
        return names

    def move_item(self, item, direction):
        if not item or _tree_item_kind(item) != "control":
            return False
        parent_item = item.parent()
        if not parent_item:
            return False
        child_index = parent_item.indexOfChild(item)
        new_index = child_index + direction
        if new_index < 0 or new_index >= parent_item.childCount():
            return False
        parent_item.removeChild(item)
        parent_item.insertChild(new_index, item)
        parent_item.setExpanded(True)
        self.tree.setCurrentItem(item)
        self._on_layout_changed()
        return True

    def move_item_to_category(self, item, category_name):
        if not item or _tree_item_kind(item) != "control":
            return False
        target_parent = self.category_item(category_name) or self.category_item("Other")
        if not target_parent:
            return False
        source_parent = item.parent()
        if source_parent:
            source_parent.removeChild(item)
            if _tree_item_kind(source_parent) == "group" and source_parent.childCount() == 0:
                source_category = source_parent.parent()
                if source_category:
                    source_category.removeChild(source_parent)
        item.setData(0, QtCore.Qt.UserRole, category_name)
        item.setForeground(0, QtGui.QBrush(_category_color(category_name)))
        target_group = target_parent
        if category_name in ("Face", "Body"):
            record_like = {
                "category": category_name,
                "label": item.data(0, QtCore.Qt.UserRole + 4) or item.text(0),
                "maya_name": item.data(0, QtCore.Qt.UserRole + 2) or "",
                "side": item.data(0, QtCore.Qt.UserRole + 3) or "",
            }
            group_name = _list_subgroup_name(record_like)
            target_group = self.group_item(category_name, group_name)
            if not target_group:
                target_group = QtWidgets.QTreeWidgetItem([group_name + " (0)"])
                target_group.setData(0, QtCore.Qt.UserRole + 1, "group")
                target_group.setData(0, QtCore.Qt.UserRole, category_name)
                target_group.setData(0, QtCore.Qt.UserRole + 4, group_name)
                target_group.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                target_group.setExpanded(True)
                target_group.setForeground(0, QtGui.QBrush(_category_color(category_name)))
                insert_index = _group_insert_index(target_parent, category_name, group_name)
                target_parent.insertChild(insert_index, target_group)
        target_group.addChild(item)
        target_parent.setExpanded(True)
        target_group.setExpanded(True)
        self.tree.setCurrentItem(item)
        self._on_layout_changed()
        return True

    def _update_status_from_tree(self):
        current = self.current_control_item()
        if not current:
            self.details_label.setText("Pick one control to see attrs.")
            self.set_attr_items([])
            self.label_edit.setText("")
            return
        maya_name = current.data(0, QtCore.Qt.UserRole + 2)
        self.details_label.setText(
            "{0}\nCategory: {1}\nNode: {2}".format(
                current.text(0),
                current.data(0, QtCore.Qt.UserRole) or "Other",
                maya_name or "",
            )
        )
        self.set_attr_items(_keyable_attrs(maya_name))
        self.label_edit.setText(current.text(0))

    def _on_current_item_changed(self, current, previous):
        if self._updating_tree or not current:
            return
        if _tree_item_kind(current) == "custom_set":
            self.custom_set_name_edit.setText(_tree_item_base_label(current))
            self.details_label.setText(
                "{0}\nCustom set with {1} control(s).".format(
                    _tree_item_base_label(current),
                    len(current.data(0, QtCore.Qt.UserRole + 5) or []),
                )
            )
            self.set_attr_items([])
            return
        if _tree_item_kind(current) != "control":
            return
        self._update_status_from_tree()

    def _on_item_changed(self, item, column):
        if self._updating_tree or not item or _tree_item_kind(item) != "control":
            return
        if column != 0:
            return
        item.setData(0, QtCore.Qt.UserRole + 4, item.text(0))
        self._update_status_from_tree()
        self.rebuild_visual_layout()
        self.save_layout()

    def _on_layout_changed(self):
        if self._updating_tree:
            return
        self.rebuild_category_headers()
        self.rebuild_visual_layout()
        self.save_layout()

    def _use_selected_controls_root(self):
        selected = _selection_transforms()
        if not selected:
            self.set_status("Pick a controls root in Maya first.")
            return
        self.set_controls_root_text(selected[0])
        self.controller.scan_scene(
            controls_root=selected[0],
            geometry_root=self.geometry_root_text() or None,
            skeleton_root=self.skeleton_root_text() or None,
        )

    def _use_selected_geometry_root(self):
        selected = _selection_transforms()
        if not selected:
            self.set_status("Pick a geometry root in Maya first.")
            return
        self.set_geometry_root_text(selected[0])
        self.controller.scan_scene(geometry_root=selected[0], controls_root=self.controls_root_text(), skeleton_root=self.skeleton_root_text())

    def _use_selected_skeleton_root(self):
        selected = _selection_transforms()
        if not selected:
            self.set_status("Pick a skeleton root in Maya first.")
            return
        self.set_skeleton_root_text(selected[0])
        self.controller.scan_scene(skeleton_root=selected[0], controls_root=self.controls_root_text(), geometry_root=self.geometry_root_text())

    def _scan_scene(self):
        self.controller.scan_scene(
            controls_root=self.controls_root_text() or None,
            geometry_root=self.geometry_root_text() or None,
            skeleton_root=self.skeleton_root_text() or None,
        )

    def _reload_saved(self):
        state = self.controller.load_state()
        self.set_records(
            _records_from_state(state),
            source_root=state.get("source_root") or "",
            geometry_root=state.get("geometry_root") or "",
            skeleton_root=state.get("skeleton_root") or "",
            custom_sets=state.get("custom_sets") or [],
        )
        self.set_status("Reloaded saved picker.")

    def _add_selected(self):
        self.controller.add_selected_controls(category=self.category_combo.currentText())

    def _remove_selected(self):
        self.controller.remove_selected_controls()

    def _apply_label(self):
        self.controller.apply_label(self.label_edit.text())

    def _apply_category(self):
        self.controller.apply_category(self.category_combo.currentText())

    def _apply_group(self):
        self.controller.apply_group_path(self.group_path_combo.currentText())

    def _create_or_update_custom_set(self):
        self.controller.create_or_update_custom_set(self.custom_set_name_edit.text())

    def _refresh_live_map(self):
        self.rebuild_visual_layout()
        self.set_status("Live rig map refreshed from current control positions.")

    def save_layout(self):
        self.controller.save_state(
            source_root=self.controls_root_text(),
            geometry_root=self.geometry_root_text(),
            skeleton_root=self.skeleton_root_text(),
            records=self.current_records(),
            custom_sets=self.current_custom_sets(),
        )
        self.set_status("Layout saved.")

    def closeEvent(self, event):
        try:
            if hasattr(self, "selection_timer"):
                self.selection_timer.stop()
            self.save_layout()
        except Exception:
            pass
        super(ControlPickerPanel, self).closeEvent(event)


__all__ = [
    "CONTROL_PICKER_GROUP_NAME",
    "ControlPickerController",
    "ControlPickerPanel",
    "DEFAULT_DONATE_URL",
    "DEFAULT_SHELF_BUTTON_LABEL",
    "DEFAULT_SHELF_NAME",
    "DONATE_URL",
    "FOLLOW_AMIR_URL",
    "GLOBAL_CONTROLLER",
    "GLOBAL_WINDOW",
    "SHELF_BUTTON_DOC_TAG",
]
