"""
maya_dynamic_parenting_tool.py

Simple scene-backed dynamic parenting for props and controls.
"""

from __future__ import absolute_import, division, print_function

import json
import math
import os
import uuid

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
except Exception:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
        import shiboken2 as shiboken
    except Exception:
        QtCore = None
        QtGui = None
        QtWidgets = None
        shiboken = None


WINDOW_OBJECT_NAME = "mayaDynamicParentingWindow"
DYNAMIC_PARENTING_MIN_WIDTH = 420
DYNAMIC_PARENTING_MIN_HEIGHT = 420
DYNAMIC_PARENTING_OBJECT_LIST_HEIGHT = 58
DYNAMIC_PARENTING_TARGET_LIST_MIN_HEIGHT = 104
DYNAMIC_PARENTING_TARGET_LIST_MAX_HEIGHT = 190
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
ROOT_GROUP_NAME = "amirDynamicParentingSystems_GRP"
WORLD_LOCATOR_NAME = "amirDynamicParentingWorld_LOC"
SETUP_TYPE = "amirDynamicParentSetupV2"
TARGETS_GROUP_SUFFIX = "_adpTargets_GRP"
TARGET_LOCATOR_SUFFIX = "_adpTarget_LOC"
FOLLOW_GROUP_SUFFIX = "_adpFollow_GRP"
DRIVEN_CONSTRAINT_SUFFIX = "_adpDriven_parentConstraint"
FOLLOW_CONSTRAINT_SUFFIX = "_adpFollow_parentConstraint"
EPSILON = 1.0e-4
DEFAULT_SWITCH_STEP = 1.0
ROTATE_ORDER_TO_EULER = (
    om.MEulerRotation.kXYZ if om else 0,
    om.MEulerRotation.kYZX if om else 1,
    om.MEulerRotation.kZXY if om else 2,
    om.MEulerRotation.kXZY if om else 3,
    om.MEulerRotation.kYXZ if om else 4,
    om.MEulerRotation.kZYX if om else 5,
)


def _debug(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayInfo("[Maya Dynamic Parenting] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayWarning("[Maya Dynamic Parenting] {0}".format(message))


def _qt_flag(scope_name, member_name, fallback=None):
    if not QtCore:
        return fallback
    if hasattr(QtCore.Qt, member_name):
        return getattr(QtCore.Qt, member_name)
    scoped_enum = getattr(QtCore.Qt, scope_name, None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return fallback


def _style_donate_button(button):
    if not button or not QtWidgets:
        return
    button.setMinimumWidth(92)
    button.setStyleSheet(
        """
        QPushButton {
            background-color: #FFC439;
            color: #111111;
            border: 1px solid #D9A000;
            border-radius: 5px;
            font-weight: 600;
            padding: 4px 12px;
        }
        QPushButton:hover {
            background-color: #FFD55C;
            border-color: #C89200;
        }
        QPushButton:pressed {
            background-color: #E6B12E;
            border-color: #AD7A00;
        }
        """
    )


def _open_external_url(url):
    if not url or not QtGui:
        return False
    return QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


def _maya_main_window():
    if not (MAYA_AVAILABLE and QtWidgets and shiboken and omui):
        return None
    pointer = omui.MQtUtil.mainWindow()
    if not pointer:
        return None
    return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)


def _dedupe_preserve_order(items):
    result = []
    seen = set()
    for item in items or []:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _short_name(node_name):
    return (node_name or "").split("|")[-1].split(":")[-1]


def _safe_node_name(node_name):
    return "".join(character if character.isalnum() else "_" for character in _short_name(node_name)).strip("_") or "node"


def _frame_display(frame_value):
    value = float(frame_value)
    if abs(value - round(value)) < 1.0e-3:
        return str(int(round(value)))
    return "{0:.2f}".format(value).rstrip("0").rstrip(".")


def _selected_transforms():
    if not MAYA_AVAILABLE:
        return []
    normalized = []
    for node_name in cmds.ls(selection=True, long=True) or []:
        if not cmds.objExists(node_name):
            continue
        if cmds.nodeType(node_name) == "transform":
            normalized.append((cmds.ls(node_name, long=True) or [node_name])[0])
            continue
        parents = cmds.listRelatives(node_name, parent=True, fullPath=True, type="transform") or []
        if parents:
            normalized.append(parents[0])
    return _dedupe_preserve_order(normalized)


def _matrix_to_list(matrix):
    return [matrix[index] for index in range(16)]


def _matrix_from_node(node_name):
    return om.MMatrix(cmds.xform(node_name, query=True, matrix=True, worldSpace=True))


def _visible_pose_matrix(node_name):
    if not om:
        return _matrix_from_node(node_name)
    temp_node = ""
    try:
        temp_node = cmds.createNode("transform", name="__adpVisiblePose_{0}".format(uuid.uuid4().hex[:8]))
        if cmds.objExists(node_name + ".rotateOrder") and cmds.objExists(temp_node + ".rotateOrder"):
            try:
                cmds.setAttr(temp_node + ".rotateOrder", int(cmds.getAttr(node_name + ".rotateOrder")))
            except Exception:
                pass
        translation = cmds.xform(node_name, query=True, worldSpace=True, translation=True)
        rotation = cmds.xform(node_name, query=True, worldSpace=True, rotation=True)
        cmds.xform(temp_node, worldSpace=True, translation=translation)
        cmds.xform(temp_node, worldSpace=True, rotation=rotation)
        return _matrix_from_node(temp_node)
    finally:
        if temp_node and cmds.objExists(temp_node):
            try:
                cmds.delete(temp_node)
            except Exception:
                pass


def _set_world_matrix(node_name, matrix):
    cmds.xform(node_name, worldSpace=True, matrix=_matrix_to_list(matrix))


def _identity_matrix():
    if om:
        return om.MMatrix()
    return (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _set_world_translation_rotation_preserve_scale(node_name, matrix):
    if not om:
        _set_world_matrix(node_name, matrix)
        return
    transform = om.MTransformationMatrix(matrix)
    translation = transform.translation(om.MSpace.kWorld)
    rotation = transform.rotation(asQuaternion=True).asEulerRotation()
    rotate_order = 0
    if cmds.objExists(node_name + ".rotateOrder"):
        try:
            rotate_order = int(cmds.getAttr(node_name + ".rotateOrder"))
        except Exception:
            rotate_order = 0
    rotation.reorderIt(ROTATE_ORDER_TO_EULER[rotate_order])
    cmds.xform(
        node_name,
        worldSpace=True,
        translation=(translation.x, translation.y, translation.z),
    )
    cmds.xform(
        node_name,
        worldSpace=True,
        rotation=tuple(math.degrees(angle) for angle in (rotation.x, rotation.y, rotation.z)),
    )


def _set_keyable_channels(node_name, attrs):
    for attr_name in attrs:
        plug = "{0}.{1}".format(node_name, attr_name)
        if not cmds.objExists(plug):
            continue
        try:
            if cmds.getAttr(plug, lock=True):
                continue
            cmds.setKeyframe(node_name, attribute=attr_name)
        except Exception:
            pass


def _dynamic_parent_blend_attrs(node_name):
    attrs = []
    all_attr_names = _dedupe_preserve_order((cmds.listAttr(node_name, keyable=True) or []) + (cmds.listAttr(node_name) or []))
    for attr_name in all_attr_names:
        lower_name = attr_name.lower()
        if not lower_name.startswith("blend"):
            continue
        if "adpdrivenparent" in lower_name or "parent" in lower_name:
            attrs.append(attr_name)
    if attrs:
        return attrs
    return [attr_name for attr_name in all_attr_names if attr_name.lower().startswith("blend")]


def _get_blend_attr_values(node_name):
    values = {}
    for attr_name in _dynamic_parent_blend_attrs(node_name):
        plug = "{0}.{1}".format(node_name, attr_name)
        if not cmds.objExists(plug):
            continue
        try:
            values[attr_name] = float(cmds.getAttr(plug))
        except Exception:
            continue
    return values


def _set_blend_attr_values(node_name, values, keyframe=True):
    for attr_name, value in (values or {}).items():
        plug = "{0}.{1}".format(node_name, attr_name)
        if not cmds.objExists(plug):
            continue
        try:
            cmds.setAttr(plug, float(value))
            if keyframe:
                cmds.setKeyframe(node_name, attribute=attr_name)
        except Exception:
            pass


def _ensure_attr(node_name, attr_name, attr_type="string", default_value=None):
    if cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return
    if attr_type == "string":
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
    elif attr_type == "bool":
        kwargs = {"attributeType": "bool"}
        if default_value is not None:
            kwargs["defaultValue"] = bool(default_value)
        cmds.addAttr(node_name, longName=attr_name, **kwargs)
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


def _get_bool_attr(node_name, attr_name, default=False):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return bool(default)
    try:
        return bool(cmds.getAttr("{0}.{1}".format(node_name, attr_name)))
    except Exception:
        return bool(default)


def _get_json_attr(node_name, attr_name, default=None):
    default = [] if default is None else default
    raw_value = _get_string_attr(node_name, attr_name, "")
    if not raw_value:
        return default
    try:
        payload = json.loads(raw_value)
    except Exception:
        return default
    return payload if isinstance(payload, type(default)) else default


def _set_matrix_attr(node_name, attr_name, matrix):
    _ensure_attr(node_name, attr_name, "string")
    plug = "{0}.{1}".format(node_name, attr_name)
    if matrix is None:
        cmds.setAttr(plug, "", type="string")
        return
    try:
        payload = _matrix_to_list(matrix)
    except Exception:
        payload = list(matrix) if isinstance(matrix, (list, tuple)) else []
    try:
        cmds.setAttr(plug, json.dumps(payload), type="string")
    except Exception:
        cmds.setAttr(plug, "", type="string")


def _get_matrix_attr(node_name, attr_name, default=None):
    raw_value = _get_string_attr(node_name, attr_name, "")
    if not raw_value:
        return default
    try:
        payload = json.loads(raw_value)
    except Exception:
        return default
    if not isinstance(payload, (list, tuple)) or len(payload) != 16:
        return default
    if om:
        try:
            return om.MMatrix(payload)
        except Exception:
            pass
    try:
        return tuple(float(value) for value in payload)
    except Exception:
        return default


def _parent_constraint_targets(constraint_name):
    targets = cmds.parentConstraint(constraint_name, query=True, targetList=True) or []
    aliases = cmds.parentConstraint(constraint_name, query=True, weightAliasList=True) or []
    mapping = {}
    for index, target in enumerate(targets):
        mapping[target] = aliases[index] if index < len(aliases) else ""
    return mapping


def _constraint_weight(constraint_name, target_name):
    alias = _parent_constraint_targets(constraint_name).get(target_name, "")
    if not alias:
        return 0.0
    try:
        return float(cmds.getAttr("{0}.{1}".format(constraint_name, alias)))
    except Exception:
        return 0.0


def _set_constraint_weights(constraint_name, weight_map, keyframe=True):
    target_map = _parent_constraint_targets(constraint_name)
    for target_name, alias in target_map.items():
        if not alias:
            continue
        value = float(weight_map.get(target_name, 0.0))
        cmds.setAttr("{0}.{1}".format(constraint_name, alias), value)
        if keyframe:
                try:
                    cmds.setKeyframe(constraint_name, attribute=alias)
                except Exception:
                    pass


def _constraint_target_index(constraint_name, target_node):
    target_list = cmds.parentConstraint(constraint_name, query=True, targetList=True) or []
    normalized_target = (cmds.ls(target_node, long=True) or [target_node])[0]
    normalized_targets = [(cmds.ls(target_name, long=True) or [target_name])[0] for target_name in target_list]
    try:
        return normalized_targets.index(normalized_target)
    except ValueError:
        return None


def _set_constraint_target_offsets(constraint_name, target_node, translate=(0.0, 0.0, 0.0), rotate=(0.0, 0.0, 0.0)):
    target_index = _constraint_target_index(constraint_name, target_node)
    if target_index is None:
        return
    plug_base = "{0}.target[{1}]".format(constraint_name, target_index)
    try:
        cmds.setAttr(plug_base + ".targetOffsetTranslate", float(translate[0]), float(translate[1]), float(translate[2]), type="double3")
    except Exception:
        pass
    try:
        cmds.setAttr(plug_base + ".targetOffsetRotate", float(rotate[0]), float(rotate[1]), float(rotate[2]), type="double3")
    except Exception:
        pass


def _ensure_root_hierarchy():
    if cmds.objExists(ROOT_GROUP_NAME):
        root_group = ROOT_GROUP_NAME
    else:
        root_group = cmds.createNode("transform", name=ROOT_GROUP_NAME)
    if cmds.objExists(WORLD_LOCATOR_NAME):
        world_locator = WORLD_LOCATOR_NAME
    else:
        world_locator = cmds.spaceLocator(name=WORLD_LOCATOR_NAME)[0]
        cmds.parent(world_locator, root_group)
        cmds.setAttr(world_locator + ".visibility", 0)
    return root_group, world_locator


def _is_dynamic_parenting_constraint(constraint_name):
    if not cmds.objExists(constraint_name):
        return False
    short_name = _short_name(constraint_name)
    if short_name.endswith(DRIVEN_CONSTRAINT_SUFFIX) or short_name.endswith(FOLLOW_CONSTRAINT_SUFFIX):
        return True
    try:
        target_list = cmds.parentConstraint(constraint_name, query=True, targetList=True) or []
    except Exception:
        target_list = []
    for target_name in target_list:
        if target_name.endswith(TARGET_LOCATOR_SUFFIX):
            return True
        if ROOT_GROUP_NAME in target_name:
            return True
    return False


def _dynamic_parenting_constraints_on_node(node_name):
    constraints = []
    for constraint_name in cmds.listConnections(node_name, source=True, destination=False, type="parentConstraint") or []:
        if _is_dynamic_parenting_constraint(constraint_name):
            constraints.append(constraint_name)
    return _dedupe_preserve_order(constraints)


def _find_setup_groups():
    if not MAYA_AVAILABLE or not cmds.objExists(ROOT_GROUP_NAME):
        return []
    children = cmds.listRelatives(ROOT_GROUP_NAME, children=True, type="transform", fullPath=True) or []
    return [child for child in children if _get_string_attr(child, "adpSetupType") == SETUP_TYPE]


def _save_target_entries(setup_group, entries):
    _set_string_attr(setup_group, "adpTargetsJson", json.dumps(entries, sort_keys=True))


def _save_event_log(setup_group, events):
    _set_string_attr(setup_group, "adpEventLog", json.dumps(events, sort_keys=True))


def _find_setup_for_driven(driven_node):
    if not driven_node:
        return None
    long_name = (cmds.ls(driven_node, long=True) or [driven_node])[0]
    for setup_group in _find_setup_groups():
        if _get_string_attr(setup_group, "adpDriven") == long_name:
            return setup_group
    return None


def _load_setup_data(setup_group):
    if not setup_group or not cmds.objExists(setup_group):
        return None
    driven_node = _get_string_attr(setup_group, "adpDriven")
    if not driven_node or not cmds.objExists(driven_node):
        return None
    data = {
        "setup_group": setup_group,
        "driven": driven_node,
        "label": _get_string_attr(setup_group, "adpLabel", _short_name(driven_node)),
        "targets_group": _get_string_attr(setup_group, "adpTargetsGroup"),
        "driven_constraint": _get_string_attr(setup_group, "adpDrivenConstraint"),
        "maintain_offset": _get_bool_attr(setup_group, "adpMaintainOffset", True),
        "targets": [],
        "event_log": _get_json_attr(setup_group, "adpEventLog", []),
        "switch_reference_matrix": _get_matrix_attr(setup_group, "adpSwitchReferenceMatrix", None),
    }
    for entry in _get_json_attr(setup_group, "adpTargetsJson", []):
        locator_name = entry.get("locator", "")
        if not locator_name or not cmds.objExists(locator_name):
            continue
        follow_constraint = entry.get("follow_constraint", "")
        driver_node = entry.get("driver", "")
        if driver_node and not cmds.objExists(driver_node):
            driver_node = ""
        data["targets"].append(
            {
                "id": entry.get("id", ""),
                "label": entry.get("label") or ("World" if entry.get("is_world") else _short_name(driver_node or locator_name)),
                "driver": driver_node,
                "locator": locator_name,
                "follow_group": entry.get("follow_group", "") if entry.get("follow_group", "") and cmds.objExists(entry.get("follow_group", "")) else "",
                "follow_constraint": follow_constraint if follow_constraint and cmds.objExists(follow_constraint) else "",
                "is_world": bool(entry.get("is_world")),
            }
        )
    return data


class MayaDynamicParentingController(object):
    def __init__(self):
        self.active_setup_group = ""
        self.pending_target_node = ""
        self.maintain_offset = True
        self.keep_current_position_on_add = True
        self.status_callback = None

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _set_status(self, message, ok=True):
        if self.status_callback:
            self.status_callback(message, ok)
        if ok:
            _debug(message)
        else:
            _warning(message)

    def all_setups(self):
        return [item for item in (_load_setup_data(group) for group in _find_setup_groups()) if item]

    def setup_payloads(self, from_selection=False):
        if from_selection:
            selected = []
            for node_name in _selected_transforms():
                setup_group = _find_setup_for_driven(node_name)
                if setup_group:
                    selected.append(setup_group)
            seen = set()
            payloads = []
            for setup_group in selected:
                if setup_group in seen:
                    continue
                seen.add(setup_group)
                data = _load_setup_data(setup_group)
                if data:
                    payloads.append(self._payload_for_setup(data))
            return payloads
        return [self._payload_for_setup(item) for item in self.all_setups()]

    def _payload_for_setup(self, setup_data):
        current_weights = self.current_weights(setup_data)
        active_names = [
            "{0} ({1:.2f})".format(target["label"], current_weights.get(target["id"], 0.0))
            for target in setup_data["targets"]
            if current_weights.get(target["id"], 0.0) > EPSILON
        ]
        return {
            "setup_group": setup_data["setup_group"],
            "driven": setup_data["driven"],
            "label": setup_data["label"],
            "maintain_offset": setup_data["maintain_offset"],
            "targets": list(setup_data["targets"]),
            "event_log": list(setup_data["event_log"]),
            "current_weights": current_weights,
            "state_text": ", ".join(active_names) if active_names else "Nothing active",
        }

    def current_setup(self):
        if self.active_setup_group:
            data = _load_setup_data(self.active_setup_group)
            if data:
                return data
        for node_name in _selected_transforms():
            setup_group = _find_setup_for_driven(node_name)
            if setup_group:
                self.active_setup_group = setup_group
                data = _load_setup_data(setup_group)
                if data:
                    self.maintain_offset = bool(data["maintain_offset"])
                return data
        all_setups = self.all_setups()
        if all_setups:
            self.active_setup_group = all_setups[0]["setup_group"]
            self.maintain_offset = bool(all_setups[0]["maintain_offset"])
            return all_setups[0]
        self.active_setup_group = ""
        return None

    def set_active_setup(self, setup_group):
        data = _load_setup_data(setup_group)
        if not data:
            return False, "Pick an object from the list first."
        self.active_setup_group = setup_group
        self.maintain_offset = bool(data["maintain_offset"])
        return True, "Now editing {0}.".format(data["label"])

    def _create_world_target_entry(self, driven_node, targets_group, reference_matrix=None, start_in_current_position=True):
        locator_name = cmds.spaceLocator(name="{0}_world{1}".format(_safe_node_name(driven_node), TARGET_LOCATOR_SUFFIX))[0]
        locator_name = cmds.parent(locator_name, targets_group)[0]
        cmds.setAttr(locator_name + ".visibility", 0)
        if start_in_current_position:
            if reference_matrix is None:
                reference_matrix = _visible_pose_matrix(driven_node)
            _set_world_matrix(locator_name, reference_matrix)
        else:
            _set_world_matrix(locator_name, _identity_matrix())
        return {
            "id": "world",
            "label": "World",
            "driver": "",
            "locator": locator_name,
            "follow_group": "",
            "follow_constraint": "",
            "is_world": True,
        }

    def _ensure_setup(self, driven_node, start_in_current_position=True):
        driven_node = (cmds.ls(driven_node, long=True) or [driven_node])[0]
        reference_matrix = _visible_pose_matrix(driven_node)
        existing = _find_setup_for_driven(driven_node)
        if existing:
            data = _load_setup_data(existing)
            if data:
                return data, False, "{0} is already in the constrained-object list.".format(data["label"])

        root_group, _world_locator = _ensure_root_hierarchy()
        safe_name = _safe_node_name(driven_node)
        setup_group = cmds.createNode("transform", name="{0}_adpSetup_GRP".format(safe_name), parent=root_group)
        targets_group = cmds.createNode("transform", name="{0}{1}".format(safe_name, TARGETS_GROUP_SUFFIX), parent=setup_group)
        _set_string_attr(setup_group, "adpSetupType", SETUP_TYPE)
        _set_string_attr(setup_group, "adpDriven", driven_node)
        _set_string_attr(setup_group, "adpTargetsGroup", targets_group)
        _set_string_attr(setup_group, "adpLabel", _short_name(driven_node))
        _ensure_attr(setup_group, "adpMaintainOffset", "bool", default_value=True)
        cmds.setAttr(setup_group + ".adpMaintainOffset", 1)

        world_entry = self._create_world_target_entry(
            driven_node,
            targets_group,
            reference_matrix=reference_matrix,
            start_in_current_position=start_in_current_position,
        )
        driven_constraint = cmds.parentConstraint(
            world_entry["locator"],
            driven_node,
            maintainOffset=False,
            name="{0}{1}".format(safe_name, DRIVEN_CONSTRAINT_SUFFIX),
        )[0]
        _set_constraint_target_offsets(driven_constraint, world_entry["locator"])
        if start_in_current_position:
            _set_world_translation_rotation_preserve_scale(driven_node, reference_matrix)
        _set_string_attr(setup_group, "adpDrivenConstraint", driven_constraint)
        _save_target_entries(setup_group, [world_entry])
        _save_event_log(setup_group, [])
        data = _load_setup_data(setup_group)
        self.active_setup_group = setup_group
        self.maintain_offset = True
        if start_in_current_position:
            return data, True, "Added {0}. It starts where it is right now.".format(_short_name(driven_node))
        return data, True, "Added {0}. It starts from World.".format(_short_name(driven_node))

    def add_driven_from_nodes(self, driven_nodes, start_in_current_position=True):
        created = []
        messages = []
        for node_name in _dedupe_preserve_order(driven_nodes or []):
            if not cmds.objExists(node_name):
                continue
            data, _was_created, message = self._ensure_setup(node_name, start_in_current_position=start_in_current_position)
            if data:
                created.append(data)
            messages.append(message)
        if not created:
            return False, "Pick one or more props or controls first."
        self.active_setup_group = created[-1]["setup_group"]
        self.maintain_offset = bool(created[-1]["maintain_offset"])
        self.keep_current_position_on_add = bool(start_in_current_position)
        return True, "\n".join(messages)

    def add_driven_from_selection(self, start_in_current_position=True):
        return self.add_driven_from_nodes(_selected_transforms(), start_in_current_position=start_in_current_position)

    def _delete_setup_nodes(self, setup):
        driven_node = setup["driven"]
        nodes_to_delete = []
        if setup.get("driven_constraint") and cmds.objExists(setup["driven_constraint"]):
            nodes_to_delete.append(setup["driven_constraint"])
        for target in setup.get("targets") or []:
            if target.get("follow_constraint") and cmds.objExists(target["follow_constraint"]):
                nodes_to_delete.append(target["follow_constraint"])
            if target.get("follow_group") and cmds.objExists(target["follow_group"]):
                nodes_to_delete.append(target["follow_group"])
            if target.get("locator") and cmds.objExists(target["locator"]):
                nodes_to_delete.append(target["locator"])
        if setup.get("setup_group") and cmds.objExists(setup["setup_group"]):
            nodes_to_delete.append(setup["setup_group"])
        for constraint_name in _dynamic_parenting_constraints_on_node(driven_node):
            nodes_to_delete.append(constraint_name)
        nodes_to_delete = [node_name for node_name in _dedupe_preserve_order(nodes_to_delete) if cmds.objExists(node_name)]
        if nodes_to_delete:
            try:
                cmds.delete(nodes_to_delete)
            except Exception:
                for node_name in nodes_to_delete:
                    if cmds.objExists(node_name):
                        try:
                            cmds.delete(node_name)
                        except Exception:
                            pass
        _set_blend_attr_values(driven_node, {attr_name: 0.0 for attr_name in _dynamic_parent_blend_attrs(driven_node)}, keyframe=False)
        if cmds.objExists(driven_node):
            try:
                cmds.select(driven_node, replace=True)
            except Exception:
                pass

    def remove_active_setup(self):
        setup = self.current_setup()
        if not setup:
            return False, "Pick a constrained object from the list first."
        label = setup["label"]
        self._delete_setup_nodes(setup)
        self.active_setup_group = ""
        self.pending_target_node = ""
        return True, "Removed {0} from the constrained-object list.".format(label)

    def rename_active_setup(self, label_text):
        setup = self.current_setup()
        if not setup:
            return False, "Pick a constrained object from the list first."
        label_text = (label_text or "").strip() or _short_name(setup["driven"])
        _set_string_attr(setup["setup_group"], "adpLabel", label_text)
        return True, "Renamed this list entry to {0}.".format(label_text)

    def set_pending_target_from_selection(self):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        for node_name in reversed(_selected_transforms()):
            if node_name == setup["driven"]:
                continue
            self.pending_target_node = node_name
            return True, "Picked {0} as the next parent choice.".format(_short_name(node_name))
        return False, "Pick the constrained object first, then also pick the hand, gun, or object it should follow."

    def _target_entry_by_id(self, setup, target_id):
        for target in setup["targets"]:
            if target["id"] == target_id:
                return target
        return None

    def _target_entry_by_driver(self, setup, driver_node):
        for target in setup["targets"]:
            if target["driver"] == driver_node:
                return target
        return None

    def _target_snap_matrix(self, target_entry):
        if not target_entry:
            return None
        if target_entry.get("driver") and cmds.objExists(target_entry["driver"]):
            return _visible_pose_matrix(target_entry["driver"])
        if target_entry.get("locator") and cmds.objExists(target_entry["locator"]):
            return _visible_pose_matrix(target_entry["locator"])
        return None

    def _save_targets(self, setup, targets):
        serialized = []
        for target in targets:
            serialized.append(
                {
                    "id": target["id"],
                    "label": target["label"],
                    "driver": target["driver"],
                    "locator": target["locator"],
                    "follow_group": target.get("follow_group", ""),
                    "follow_constraint": target["follow_constraint"],
                    "is_world": bool(target["is_world"]),
                }
            )
        _save_target_entries(setup["setup_group"], serialized)

    def add_targets_from_nodes(self, target_nodes):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        reference_matrix = _visible_pose_matrix(setup["driven"])
        if bool(setup.get("maintain_offset", True)):
            current_weights = self.current_weights(setup)
            for target in setup["targets"]:
                if float(current_weights.get(target["id"], 0.0)) > EPSILON:
                    self._reseed_target(setup, target, True, reference_matrix=reference_matrix)
        targets = list(setup["targets"])
        added_labels = []
        for target_node in _dedupe_preserve_order(target_nodes or []):
            if not cmds.objExists(target_node):
                continue
            target_node = (cmds.ls(target_node, long=True) or [target_node])[0]
            if target_node == setup["driven"]:
                continue
            existing = self._target_entry_by_driver(setup, target_node)
            if existing:
                continue
            target_matrix = _matrix_from_node(target_node)
            follow_group = cmds.createNode("transform", name="{0}{1}".format(_safe_node_name(target_node), FOLLOW_GROUP_SUFFIX), parent=setup["targets_group"])
            _set_world_matrix(follow_group, target_matrix)
            locator_name = cmds.spaceLocator(name="{0}{1}".format(_safe_node_name(target_node), TARGET_LOCATOR_SUFFIX))[0]
            locator_name = cmds.parent(locator_name, follow_group)[0]
            cmds.setAttr(locator_name + ".visibility", 0)
            for attr_name in ("translate", "rotate"):
                try:
                    cmds.setAttr(locator_name + "." + attr_name, 0.0, 0.0, 0.0, type="double3")
                except Exception:
                    pass
            follow_constraint = cmds.parentConstraint(
                target_node,
                follow_group,
                maintainOffset=False,
                name="{0}{1}".format(_safe_node_name(target_node), FOLLOW_CONSTRAINT_SUFFIX),
            )[0]
            _set_world_matrix(follow_group, target_matrix)
            cmds.parentConstraint(locator_name, setup["driven"], edit=True, weight=0.0)
            _set_constraint_target_offsets(setup["driven_constraint"], locator_name)
            target_entry = {
                "id": uuid.uuid4().hex[:8],
                "label": _short_name(target_node),
                "driver": target_node,
                "locator": locator_name,
                "follow_group": follow_group,
                "follow_constraint": follow_constraint,
                "is_world": False,
            }
            targets.append(target_entry)
            added_labels.append(target_entry["label"])
        if not added_labels:
            return False, "Pick at least one new hand, gun, or object to add."
        self._save_targets(setup, targets)
        if bool(setup.get("maintain_offset", True)):
            _set_world_translation_rotation_preserve_scale(setup["driven"], reference_matrix)
        return True, "Added parent choices: {0}.".format(", ".join(added_labels))

    def add_targets_from_selection(self):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        target_nodes = [node_name for node_name in _selected_transforms() if node_name != setup["driven"]]
        return self.add_targets_from_nodes(target_nodes)

    def set_maintain_offset(self, enabled):
        setup = self.current_setup()
        if not setup:
            return False, "Pick a constrained object from the list first."
        cmds.setAttr(setup["setup_group"] + ".adpMaintainOffset", int(bool(enabled)))
        self.maintain_offset = bool(enabled)
        return True, "Maintain Current Offset is now {0}.".format("on" if enabled else "off")

    def _stored_switch_reference_matrix(self, setup):
        if not setup:
            return None
        matrix = setup.get("switch_reference_matrix")
        if matrix is not None:
            return matrix
        matrix = _get_matrix_attr(setup["setup_group"], "adpSwitchReferenceMatrix", None)
        setup["switch_reference_matrix"] = matrix
        return matrix

    def _store_switch_reference_matrix(self, setup, matrix):
        if not setup or not setup.get("setup_group"):
            return
        _set_matrix_attr(setup["setup_group"], "adpSwitchReferenceMatrix", matrix)
        setup["switch_reference_matrix"] = matrix

    def snap_to_target_id(self, target_id):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        target_entry = self._target_entry_by_id(setup, target_id)
        if not target_entry:
            return False, "Pick a parent first."
        if target_entry.get("is_world"):
            return False, "World does not have a snap place. Move the object by hand, then switch to World."
        target_matrix = self._target_snap_matrix(target_entry)
        if target_matrix is None:
            return False, "That parent is missing."
        blend_values = self._active_constraint_blend_values(setup, active=False)
        if blend_values:
            _set_blend_attr_values(setup["driven"], blend_values, keyframe=True)
        _set_world_translation_rotation_preserve_scale(setup["driven"], target_matrix)
        _set_keyable_channels(setup["driven"], ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
        self._store_switch_reference_matrix(setup, target_matrix)
        return True, "Snapped {0} onto {1}. Move it if you want, then click Switch.".format(
            setup["label"],
            target_entry["label"],
        )

    def current_weights(self, setup=None):
        setup = setup or self.current_setup()
        if not setup or not setup.get("driven_constraint") or not cmds.objExists(setup["driven_constraint"]):
            return {}
        weights = {}
        for target in setup["targets"]:
            weights[target["id"]] = _constraint_weight(setup["driven_constraint"], target["locator"])
        return weights

    def _sanitize_weight_map(self, setup, weight_map):
        sanitized = {}
        total = 0.0
        for target in setup["targets"]:
            value = float(weight_map.get(target["id"], 0.0))
            value = max(0.0, min(1.0, value))
            sanitized[target["id"]] = value
            total += value
        return sanitized, total

    def _active_weight_labels(self, setup, weight_map):
        labels = []
        for target in setup["targets"]:
            weight_value = float(weight_map.get(target["id"], 0.0))
            if weight_value > EPSILON:
                labels.append("{0} {1:.2f}".format(target["label"], weight_value))
        return labels

    def _active_target_names(self, setup, weight_map):
        names = []
        for target in setup["targets"]:
            if float(weight_map.get(target["id"], 0.0)) > EPSILON:
                names.append(target["label"])
        return names

    def _reseed_target(self, setup, target_entry, maintain_offset, reference_matrix=None):
        constraint_name = setup.get("driven_constraint")
        locator_name = target_entry.get("locator", "")
        if not constraint_name or not cmds.objExists(constraint_name) or not locator_name or not cmds.objExists(locator_name):
            return
        if reference_matrix is None:
            reference_matrix = _visible_pose_matrix(setup["driven"])
        if target_entry.get("is_world"):
            if maintain_offset and reference_matrix is not None:
                _set_world_matrix(locator_name, reference_matrix)
            _set_constraint_target_offsets(constraint_name, locator_name)
            return

        driver_node = target_entry.get("driver")
        if not driver_node or not cmds.objExists(driver_node):
            return
        follow_group = target_entry.get("follow_group", "")
        if not follow_group or not cmds.objExists(follow_group):
            parents = cmds.listRelatives(locator_name, parent=True, fullPath=True, type="transform") or []
            follow_group = parents[0] if parents else ""
        if not follow_group or not cmds.objExists(follow_group):
            follow_group = cmds.createNode("transform", name="{0}{1}".format(_safe_node_name(driver_node), FOLLOW_GROUP_SUFFIX), parent=setup["targets_group"])
            target_entry["follow_group"] = follow_group
            try:
                locator_name = cmds.parent(locator_name, follow_group)[0]
                target_entry["locator"] = locator_name
            except Exception:
                pass

        follow_constraint = target_entry.get("follow_constraint", "")
        if follow_constraint and cmds.objExists(follow_constraint):
            try:
                cmds.delete(follow_constraint)
            except Exception:
                pass

        driver_matrix = _matrix_from_node(driver_node)
        _set_world_matrix(follow_group, driver_matrix)
        follow_constraint = cmds.parentConstraint(
            driver_node,
            follow_group,
            maintainOffset=False,
            name="{0}{1}".format(_safe_node_name(driver_node), FOLLOW_CONSTRAINT_SUFFIX),
        )[0]
        target_entry["follow_constraint"] = follow_constraint
        _set_world_matrix(follow_group, driver_matrix)
        if not maintain_offset:
            for attr_name, value in (
                ("translate", (0.0, 0.0, 0.0)),
                ("rotate", (0.0, 0.0, 0.0)),
            ):
                try:
                    cmds.setAttr(locator_name + "." + attr_name, value[0], value[1], value[2], type="double3")
                except Exception:
                    pass
            _set_constraint_target_offsets(constraint_name, locator_name)
            return
        _set_world_translation_rotation_preserve_scale(locator_name, reference_matrix)
        temp_target = ""
        temp_driven = ""
        temp_constraint = ""
        try:
            temp_target = cmds.createNode("transform", name="__adpTmpTarget_{0}".format(uuid.uuid4().hex[:8]))
            if cmds.objExists(locator_name + ".rotateOrder") and cmds.objExists(temp_target + ".rotateOrder"):
                try:
                    cmds.setAttr(temp_target + ".rotateOrder", int(cmds.getAttr(locator_name + ".rotateOrder")))
                except Exception:
                    pass
            _set_world_translation_rotation_preserve_scale(temp_target, _visible_pose_matrix(locator_name))
            duplicate_nodes = cmds.duplicate(
                setup["driven"],
                parentOnly=True,
                inputConnections=False,
                upstreamNodes=False,
                returnRootsOnly=True,
                name="__adpTmpDriven_{0}".format(uuid.uuid4().hex[:8]),
            ) or []
            if duplicate_nodes:
                temp_driven = duplicate_nodes[0]
            driven_parent = (cmds.listRelatives(setup["driven"], parent=True, fullPath=True) or [None])[0]
            if temp_driven and driven_parent:
                try:
                    parent_result = cmds.parent(temp_driven, driven_parent)
                    if parent_result:
                        temp_driven = parent_result[0]
                except Exception:
                    pass
            if temp_driven:
                _set_world_translation_rotation_preserve_scale(temp_driven, reference_matrix)
                temp_constraint = cmds.parentConstraint(temp_target, temp_driven, maintainOffset=True)[0]
                offset_translate = cmds.getAttr(temp_constraint + ".target[0].targetOffsetTranslate")[0]
                offset_rotate = cmds.getAttr(temp_constraint + ".target[0].targetOffsetRotate")[0]
                _set_constraint_target_offsets(constraint_name, locator_name, translate=offset_translate, rotate=offset_rotate)
            else:
                _set_constraint_target_offsets(constraint_name, locator_name)
        finally:
            nodes_to_delete = [node_name for node_name in (temp_constraint, temp_target, temp_driven) if node_name and cmds.objExists(node_name)]
            if nodes_to_delete:
                try:
                    cmds.delete(nodes_to_delete)
                except Exception:
                    pass
        for attr_name in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
            try:
                cmds.setKeyframe(locator_name, attribute=attr_name)
            except Exception:
                pass

    def _record_event(self, setup, action_label, weight_map):
        event_log = list(setup.get("event_log") or [])
        frame_value = float(cmds.currentTime(query=True))
        event_log = [
            item
            for item in event_log
            if abs(float(item.get("frame", 0.0)) - frame_value) >= EPSILON
        ]
        target_labels = {}
        for target in setup["targets"]:
            weight_value = float(weight_map.get(target["id"], 0.0))
            if weight_value > EPSILON:
                target_labels[target["label"]] = round(weight_value, 4)
        event_log.append(
            {
                "id": uuid.uuid4().hex[:8],
                "frame": frame_value,
                "action": action_label,
                "weights": target_labels,
                "maintain_offset": bool(setup.get("maintain_offset", True)),
            }
        )
        event_log.sort(key=lambda item: float(item.get("frame", 0.0)))
        _save_event_log(setup["setup_group"], event_log)
        setup["event_log"] = event_log

    def _key_weight_map_on_frame(self, setup, weight_map, maintain_offset, frame_value, action_label=None, record_event=False, reseed_active=False, reference_matrix=None):
        original_frame = float(cmds.currentTime(query=True))
        frame_value = float(frame_value)
        changed_time = abs(original_frame - frame_value) >= EPSILON
        if changed_time:
            cmds.currentTime(frame_value, edit=True)
        try:
            if reseed_active:
                for target in setup["targets"]:
                    if float(weight_map.get(target["id"], 0.0)) > EPSILON:
                        self._reseed_target(setup, target, maintain_offset, reference_matrix=reference_matrix)
                self._save_targets(setup, setup["targets"])
                if maintain_offset and reference_matrix is not None:
                    _set_world_translation_rotation_preserve_scale(setup["driven"], reference_matrix)
            constraint_weights = {}
            for target in setup["targets"]:
                constraint_weights[target["locator"]] = float(weight_map.get(target["id"], 0.0))
            _set_constraint_weights(setup["driven_constraint"], constraint_weights, keyframe=True)
            _set_keyable_channels(setup["driven"], ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
            blend_values = self._active_constraint_blend_values(setup, active=True)
            if blend_values:
                _set_blend_attr_values(setup["driven"], blend_values, keyframe=True)
            if maintain_offset and reference_matrix is not None:
                _set_world_translation_rotation_preserve_scale(setup["driven"], reference_matrix)
                _set_keyable_channels(setup["driven"], ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
            if reseed_active and maintain_offset and reference_matrix is not None:
                self._store_switch_reference_matrix(setup, reference_matrix)
            if record_event and action_label:
                self._record_event(setup, action_label, weight_map)
        finally:
            if changed_time:
                cmds.currentTime(original_frame, edit=True)

    def _active_constraint_blend_values(self, setup, active=True):
        active_value = 1.0 if active else 0.0
        current_values = _get_blend_attr_values(setup["driven"])
        if current_values:
            return {attr_name: active_value for attr_name in current_values}
        return {}

    def apply_weight_map(self, weight_map, action_label="blend"):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        maintain_offset = bool(self.maintain_offset)
        cmds.setAttr(setup["setup_group"] + ".adpMaintainOffset", int(maintain_offset))
        sanitized, total = self._sanitize_weight_map(setup, weight_map)
        if total <= EPSILON:
            return False, "Turn at least one parent on before you key the weights."
        # Always use the live pose at the moment of the switch so a stale
        # stored snap pose cannot pull the object back to an older position.
        reference_matrix = _visible_pose_matrix(setup["driven"])
        self._key_weight_map_on_frame(
            setup,
            sanitized,
            maintain_offset,
            frame_value=float(cmds.currentTime(query=True)),
            action_label=action_label,
            record_event=True,
            reseed_active=maintain_offset,
            reference_matrix=reference_matrix,
        )
        _set_blend_attr_values(setup["driven"], self._active_constraint_blend_values(setup, active=True), keyframe=True)
        return True, "Saved the parent weights on frame {0}.".format(_frame_display(cmds.currentTime(query=True)))

    def switch_weight_map_next_frame(self, weight_map, action_label="switch"):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        maintain_offset = bool(self.maintain_offset)
        cmds.setAttr(setup["setup_group"] + ".adpMaintainOffset", int(maintain_offset))
        sanitized, total = self._sanitize_weight_map(setup, weight_map)
        if total <= EPSILON:
            return False, "Turn at least one parent on before you switch."
        current_frame = float(cmds.currentTime(query=True))
        target_frame = current_frame + DEFAULT_SWITCH_STEP
        # Always use the live pose at the moment of the switch so a stale
        # stored snap pose cannot pull the object back to an older position.
        reference_matrix = _visible_pose_matrix(setup["driven"])
        current_weights = self.current_weights(setup)
        current_blend_values = _get_blend_attr_values(setup["driven"])
        same_target = all(
            abs(float(current_weights.get(target["id"], 0.0)) - float(sanitized.get(target["id"], 0.0))) < EPSILON
            for target in setup["targets"]
        )
        self._key_weight_map_on_frame(
            setup,
            current_weights,
            maintain_offset,
            frame_value=current_frame,
            action_label=None,
            record_event=False,
            reseed_active=maintain_offset,
            reference_matrix=reference_matrix,
        )
        if current_blend_values:
            original_frame = float(cmds.currentTime(query=True))
            cmds.currentTime(current_frame, edit=True)
            try:
                _set_blend_attr_values(setup["driven"], current_blend_values, keyframe=True)
            finally:
                cmds.currentTime(original_frame, edit=True)
        self._key_weight_map_on_frame(
            setup,
            sanitized,
            maintain_offset,
            frame_value=target_frame,
            action_label=action_label,
            record_event=True,
            reseed_active=maintain_offset,
            reference_matrix=reference_matrix,
        )
        original_frame = float(cmds.currentTime(query=True))
        cmds.currentTime(target_frame, edit=True)
        try:
            _set_blend_attr_values(setup["driven"], self._active_constraint_blend_values(setup, active=True), keyframe=True)
        finally:
            cmds.currentTime(original_frame, edit=True)
        cmds.currentTime(target_frame, edit=True)
        self._store_switch_reference_matrix(setup, reference_matrix)
        active_target_names = self._active_target_names(setup, sanitized)
        if len(active_target_names) == 1:
            target_text = active_target_names[0]
        else:
            target_text = ", ".join(active_target_names)
        if same_target:
            return True, "Refreshed {0} on frame {1} without changing parents.".format(
                target_text,
                _frame_display(target_frame),
            )
        return True, "Kept the old parent on frame {0} and switched to {1} on frame {2}.".format(
            _frame_display(current_frame),
            target_text,
            _frame_display(target_frame),
        )

    def parent_fully_to_target(self, target_id, action_label="switch"):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        if not self._target_entry_by_id(setup, target_id):
            return False, "Pick a parent row first."
        weight_map = {}
        for target in setup["targets"]:
            weight_map[target["id"]] = 1.0 if target["id"] == target_id else 0.0
        return self.switch_weight_map_next_frame(weight_map, action_label=action_label)

    def parent_to_world(self):
        return self.parent_fully_to_target("world", action_label="world")

    def apply_pending_target(self):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        target_node = self.pending_target_node
        if not target_node or not cmds.objExists(target_node):
            return False, "Pick the next hand, gun, prop, or object first."
        existing = self._target_entry_by_driver(setup, target_node)
        if not existing:
            success, message = self.add_targets_from_nodes([target_node])
            if not success:
                return success, message
            setup = self.current_setup()
            existing = self._target_entry_by_driver(setup, target_node)
        return self.parent_fully_to_target(existing["id"], action_label="switch")

    def snap_pending_target(self):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        target_node = self.pending_target_node
        if not target_node or not cmds.objExists(target_node):
            return False, "Pick the next hand, gun, prop, or object first."
        existing = self._target_entry_by_driver(setup, target_node)
        if not existing:
            success, message = self.add_targets_from_nodes([target_node])
            if not success:
                return success, message
            setup = self.current_setup()
            existing = self._target_entry_by_driver(setup, target_node)
        return self.snap_to_target_id(existing["id"])

    def save_offset_to_target_id(self, target_id):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        target_entry = self._target_entry_by_id(setup, target_id)
        if not target_entry:
            return False, "Pick a parent row first."
        reference_matrix = _visible_pose_matrix(setup["driven"])
        self._reseed_target(setup, target_entry, True, reference_matrix=reference_matrix)
        self._save_targets(setup, setup["targets"])
        self._store_switch_reference_matrix(setup, reference_matrix)
        if target_entry.get("is_world"):
            return True, "Saved the current spot as the World offset."
        return True, "Saved the current spot as the offset for {0}.".format(target_entry["label"])

    def save_offset_to_pending_target(self):
        setup = self.current_setup()
        if not setup:
            return False, "Add or pick the constrained object first."
        target_node = self.pending_target_node
        if not target_node or not cmds.objExists(target_node):
            return False, "Pick the next hand, gun, prop, or object first."
        existing = self._target_entry_by_driver(setup, target_node)
        if not existing:
            success, message = self.add_targets_from_nodes([target_node])
            if not success:
                return success, message
            setup = self.current_setup()
            existing = self._target_entry_by_driver(setup, target_node)
        return self.save_offset_to_target_id(existing["id"])

    def reseed_active_weights(self):
        setup = self.current_setup()
        if not setup:
            return False, "Pick a constrained object from the list first."
        return self.apply_weight_map(self.current_weights(setup), action_label="reseed")

    def remove_target_ids(self, target_ids):
        setup = self.current_setup()
        if not setup:
            return False, "Pick a constrained object from the list first."
        target_ids = set(target_ids or [])
        targets = []
        removed = []
        for target in setup["targets"]:
            if target["id"] in target_ids and not target["is_world"]:
                removed.append(target["label"])
                try:
                    cmds.parentConstraint(target["locator"], setup["driven"], edit=True, remove=True)
                except Exception:
                    pass
                if target["follow_constraint"] and cmds.objExists(target["follow_constraint"]):
                    try:
                        cmds.delete(target["follow_constraint"])
                    except Exception:
                        pass
                if target.get("follow_group") and cmds.objExists(target["follow_group"]):
                    try:
                        cmds.delete(target["follow_group"])
                    except Exception:
                        pass
                if target["locator"] and cmds.objExists(target["locator"]):
                    try:
                        cmds.delete(target["locator"])
                    except Exception:
                        pass
                continue
            targets.append(target)
        if not removed:
            return False, "Pick a non-World parent row first."
        self._save_targets(setup, targets)
        return True, "Removed parent choices: {0}.".format(", ".join(removed))

    def event_items(self, setup=None):
        setup = setup or self.current_setup()
        if not setup:
            return []
        results = []
        for index, item in enumerate(setup.get("event_log") or []):
            frame_value = float(item.get("frame", 0.0))
            weights = item.get("weights") or {}
            weight_text = ", ".join("{0} {1:.2f}".format(name, float(value)) for name, value in sorted(weights.items()))
            if not weight_text:
                weight_text = "nothing active"
            results.append(
                {
                    "id": item.get("id") or "legacy-{0}-{1}".format(index, _frame_display(frame_value)),
                    "frame": frame_value,
                    "display": "F{0}: {1} -> {2}".format(
                        _frame_display(frame_value),
                        item.get("action", "switch").title(),
                        weight_text,
                    ),
                }
            )
        return results

    def delete_event(self, event_id, frame_value=None):
        setup = self.current_setup()
        if not setup:
            return False, "Pick a saved object first."
        event_log = list(setup.get("event_log") or [])
        kept_events = []
        deleted_item = None
        for index, item in enumerate(event_log):
            current_event_id = item.get("id") or "legacy-{0}-{1}".format(index, _frame_display(float(item.get("frame", 0.0))))
            if deleted_item is None and current_event_id == event_id:
                deleted_item = item
                continue
            kept_events.append(item)
        if deleted_item is None and frame_value is not None:
            frame_value = float(frame_value)
            for index, item in enumerate(event_log):
                if abs(float(item.get("frame", 0.0)) - frame_value) < EPSILON:
                    deleted_item = item
                    kept_events = event_log[:index] + event_log[index + 1 :]
                    break
        if len(kept_events) == len(event_log):
            return False, "Pick a saved switch first."
        _save_event_log(setup["setup_group"], kept_events)
        setup["event_log"] = kept_events
        deleted_frame = float(deleted_item.get("frame", frame_value or 0.0))
        return True, "Deleted the saved switch on frame {0}.".format(_frame_display(deleted_frame))

    def clear_event_log(self):
        setup = self.current_setup()
        if not setup:
            return False, "Pick a saved object first."
        if not (setup.get("event_log") or []):
            return False, "There are no saved switches to delete."
        _save_event_log(setup["setup_group"], [])
        setup["event_log"] = []
        return True, "Deleted all saved switches for {0}.".format(setup["label"])

    def jump_to_event(self, frame_value):
        cmds.currentTime(float(frame_value), edit=True)
        return True, "Jumped to frame {0}.".format(_frame_display(frame_value))

    def summary_text(self, setup=None):
        setup = setup or self.current_setup()
        if not setup:
            return "Add an object, then add the hands, guns, world, or other things it should follow."
        current_weights = self.current_weights(setup)
        lines = [
            "Object: {0}".format(setup["label"]),
            "Real node: {0}".format(setup["driven"]),
            "Maintain Current Offset: {0}".format("On" if setup["maintain_offset"] else "Off"),
            "Parents:",
        ]
        for target in setup["targets"]:
            lines.append("- {0}: {1:.2f}".format(target["label"], current_weights.get(target["id"], 0.0)))
        return "\n".join(lines)

    def shutdown(self):
        return


class _WindowBase(QtWidgets.QDialog if QtWidgets else object):
    pass


if QtWidgets:
    class MayaDynamicParentingWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaDynamicParentingWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.set_status_callback(self._set_status)
            self._weight_widgets = {}
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Dynamic Parenting")
            self.setMinimumWidth(DYNAMIC_PARENTING_MIN_WIDTH)
            self.setMinimumHeight(DYNAMIC_PARENTING_MIN_HEIGHT)
            self._build_ui()
            self._sync_from_controller()

        def _build_ui(self):
            root_layout = QtWidgets.QVBoxLayout(self)
            root_layout.setContentsMargins(0, 0, 0, 0)
            scroll_area = QtWidgets.QScrollArea(self)
            scroll_area.setObjectName("aminateDynamicParentingScroll")
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAlwaysOff", QtCore.Qt.ScrollBarAlwaysOff))
            scroll_area.setVerticalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAsNeeded", QtCore.Qt.ScrollBarAsNeeded))
            scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
            content_widget = QtWidgets.QWidget()
            content_widget.setObjectName("aminateDynamicParentingContent")
            content_widget.setMinimumWidth(0)
            content_widget.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
            main_layout = QtWidgets.QVBoxLayout(content_widget)
            main_layout.setContentsMargins(6, 6, 6, 6)
            main_layout.setSpacing(6)

            # Keep the first viewport about the real task: choose a prop,
            # choose a target row, then switch on the next frame without a
            # pop.  Setup help and destructive/history actions live below More.
            intro = QtWidgets.QLabel(
                "Select a prop, choose a parent target, then switch on the next frame without a pop."
            )
            intro.setObjectName("aminateDynamicParentingIntro")
            intro.setWordWrap(True)
            main_layout.addWidget(intro)

            object_group = QtWidgets.QGroupBox("Current Object")
            object_layout = QtWidgets.QGridLayout(object_group)
            object_layout.setContentsMargins(6, 6, 6, 6)
            object_layout.setHorizontalSpacing(6)
            object_layout.setVerticalSpacing(4)
            self.objects_line = QtWidgets.QLineEdit()
            self.objects_line.setReadOnly(True)
            self.objects_line.setPlaceholderText("Pick the object that should switch parents, then add it here.")
            self.add_object_button = QtWidgets.QPushButton("Add Object")
            self.remove_object_button = QtWidgets.QPushButton("Remove Object")
            self.remove_object_button.setToolTip("Remove this object from Dynamic Parenting. This deletes this tool's constraints and saved switches for it.")
            self.start_in_place_check = QtWidgets.QCheckBox("Stay In Current Position At Start?")
            self.start_in_place_check.setChecked(True)
            self.start_in_place_check.setToolTip("Leave this on if Add Object should keep the object exactly where it is right now. Turn it off if you want it to start from World.")
            self.object_list = QtWidgets.QListWidget()
            self.object_list.setToolTip("Every saved object in this scene that uses parent switching.")
            self.object_list.setMinimumHeight(0)
            self.object_list.setMaximumHeight(DYNAMIC_PARENTING_OBJECT_LIST_HEIGHT)
            self.object_list.setHorizontalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAlwaysOff", QtCore.Qt.ScrollBarAlwaysOff))
            self.object_list.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            object_layout.addWidget(QtWidgets.QLabel("Object"), 0, 0)
            object_layout.addWidget(self.objects_line, 0, 1, 1, 3)
            object_layout.addWidget(self.add_object_button, 1, 0, 1, 2)
            object_layout.addWidget(self.start_in_place_check, 1, 2, 1, 2)
            object_layout.addWidget(QtWidgets.QLabel("Saved props"), 2, 0)
            object_layout.addWidget(self.object_list, 2, 1, 1, 3)
            main_layout.addWidget(object_group)

            target_group = QtWidgets.QGroupBox("Parent Targets")
            target_layout = QtWidgets.QVBoxLayout(target_group)
            target_layout.setContentsMargins(6, 6, 6, 6)
            target_layout.setSpacing(5)
            target_row = QtWidgets.QGridLayout()
            target_row.setHorizontalSpacing(6)
            self.target_line = QtWidgets.QLineEdit()
            self.target_line.setReadOnly(True)
            self.target_line.setPlaceholderText("Pick a hand, gun, or other thing to follow.")
            self.use_target_button = QtWidgets.QPushButton("Pick Parent")
            self.use_target_button.setToolTip("Take the thing you picked and put it into the Parent To box.")
            self.parent_to_picked_button = QtWidgets.QPushButton("Switch to this Parent")
            self.parent_to_picked_button.setToolTip("Keep the old parent on this frame, then turn this picked parent on next frame.")
            self.snap_to_picked_button = QtWidgets.QPushButton("Snap To Parent")
            self.snap_to_picked_button.setToolTip("Move the object onto this parent now and remember that pose for the next switch.")
            self.save_offset_button = QtWidgets.QPushButton("Save This Offset")
            self.save_offset_button.setToolTip("After you move the object where you want it, save that pose as the offset for this parent.")
            self.add_target_button = QtWidgets.QPushButton("Add Parent")
            self.add_target_button.setToolTip("Remember this parent so you can switch to it later.")
            target_row.addWidget(QtWidgets.QLabel("Pending parent"), 0, 0)
            target_row.addWidget(self.target_line, 0, 1, 1, 3)
            target_row.addWidget(self.use_target_button, 1, 0, 1, 2)
            target_row.addWidget(QtWidgets.QLabel("Select a row below to change the active parent."), 1, 2, 1, 2)
            target_layout.addLayout(target_row)

            self.maintain_offset_check = QtWidgets.QCheckBox("Maintain Current Offset")
            self.maintain_offset_check.setChecked(True)
            self.maintain_offset_check.setToolTip("Leave this on if the object should stay where it is when the new parent turns on. Turn it off if it should snap.")
            target_layout.addWidget(self.maintain_offset_check)

            self.parent_to_row_button = QtWidgets.QPushButton("Reparent to Selected Parent")
            self.parent_to_row_button.setProperty("aminateRole", "primary")
            self.parent_to_row_button.setMinimumHeight(28)
            self.parent_to_row_button.setToolTip("Switch to the selected parent on the next frame without a pop. Keep Maintain Current Offset on to preserve the current pose.")
            target_layout.addWidget(self.parent_to_row_button)
            switch_hint = QtWidgets.QLabel(
                "Choose a target row, then switch on the next frame without a pop."
            )
            switch_hint.setWordWrap(True)
            switch_hint.setProperty("aminateRole", "muted")
            target_layout.addWidget(switch_hint)

            self.targets_table = QtWidgets.QTableWidget(0, 4)
            self.targets_table.setObjectName("aminateDynamicParentingTargets")
            self.targets_table.setHorizontalHeaderLabels(["Parent", "Weight", "On", "Switch"])
            self.targets_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.targets_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.targets_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.targets_table.setWordWrap(False)
            self.targets_table.setTextElideMode(_qt_flag("TextElideMode", "ElideRight", QtCore.Qt.ElideRight))
            self.targets_table.setHorizontalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAlwaysOff", QtCore.Qt.ScrollBarAlwaysOff))
            self.targets_table.setMinimumHeight(DYNAMIC_PARENTING_TARGET_LIST_MIN_HEIGHT)
            self.targets_table.setMaximumHeight(DYNAMIC_PARENTING_TARGET_LIST_MAX_HEIGHT)
            self.targets_table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            header = self.targets_table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
            target_layout.addWidget(self.targets_table, 1)
            main_layout.addWidget(target_group, 1)

            self.advanced_toggle = QtWidgets.QToolButton()
            self.advanced_toggle.setText("More")
            self.advanced_toggle.setCheckable(True)
            self.advanced_toggle.setChecked(False)
            self.advanced_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            self.advanced_toggle.setToolTip("Show setup, offset, blending, history, and removal actions.")
            main_layout.addWidget(self.advanced_toggle)

            self.advanced_widget = QtWidgets.QWidget()
            self.advanced_widget.setObjectName("aminateDynamicParentingMore")
            self.advanced_widget.setVisible(False)
            advanced_layout = QtWidgets.QVBoxLayout(self.advanced_widget)
            advanced_layout.setContentsMargins(0, 0, 0, 0)
            advanced_layout.setSpacing(6)

            setup_group = QtWidgets.QGroupBox("Setup & Fine Control")
            setup_layout = QtWidgets.QVBoxLayout(setup_group)
            setup_layout.setContentsMargins(6, 6, 6, 6)
            setup_layout.setSpacing(5)
            setup_name_row = QtWidgets.QHBoxLayout()
            self.list_name_line = QtWidgets.QLineEdit()
            self.list_name_line.setPlaceholderText("Magazine")
            self.rename_button = QtWidgets.QPushButton("Rename")
            setup_name_row.addWidget(QtWidgets.QLabel("Label"))
            setup_name_row.addWidget(self.list_name_line, 1)
            setup_name_row.addWidget(self.rename_button)
            setup_layout.addLayout(setup_name_row)

            advanced_actions = QtWidgets.QGridLayout()
            advanced_actions.setHorizontalSpacing(6)
            advanced_actions.setVerticalSpacing(4)
            advanced_actions.addWidget(self.remove_object_button, 0, 0, 1, 2)
            advanced_actions.addWidget(self.parent_to_picked_button, 0, 2, 1, 2)
            advanced_actions.addWidget(self.add_target_button, 1, 0, 1, 2)
            advanced_actions.addWidget(self.snap_to_picked_button, 1, 2, 1, 2)
            advanced_actions.addWidget(self.save_offset_button, 2, 0, 1, 2)
            self.save_offset_row_button = QtWidgets.QPushButton("Save Offset For Selected Parent")
            self.save_offset_row_button.setToolTip("Save the object's current pose as the offset for the parent row you picked.")
            advanced_actions.addWidget(self.save_offset_row_button, 2, 2, 1, 2)
            self.parent_to_world_button = QtWidgets.QPushButton("World")
            self.parent_to_world_button.setToolTip("Stop following everything and switch to World on the next frame.")
            advanced_actions.addWidget(self.parent_to_world_button, 3, 0, 1, 2)
            self.apply_weights_button = QtWidgets.QPushButton("Blend Parents")
            self.apply_weights_button.setToolTip("Save the weights you see now on this frame, like half gun and half World.")
            advanced_actions.addWidget(self.apply_weights_button, 3, 2, 1, 2)
            self.fix_pop_button = QtWidgets.QPushButton("Fix Jump Here")
            self.fix_pop_button.setToolTip("If the object pops on this frame, click this to rebuild the current follow setup here.")
            advanced_actions.addWidget(self.fix_pop_button, 4, 0, 1, 2)
            self.remove_target_button = QtWidgets.QPushButton("Forget Parent")
            self.remove_target_button.setToolTip("Remove the picked parent row from this object's saved parent list.")
            advanced_actions.addWidget(self.remove_target_button, 4, 2, 1, 2)
            setup_layout.addLayout(advanced_actions)
            advanced_layout.addWidget(setup_group)

            step_box = QtWidgets.QGroupBox("How To Use")
            step_layout = QtWidgets.QVBoxLayout(step_box)
            for text in (
                "1. Pick the object that should move, then click Add Object.",
                "2. Pick a hand, gun, world, or other parent and click Pick Parent.",
                "3. Keep Maintain Current Offset on, select the target row, and click Reparent to Selected Parent.",
                "4. Use Snap To Parent, Save This Offset, Blend Parents, and World only when needed.",
                "5. Remove Object deletes this tool's constraints for the selected object.",
            ):
                label = QtWidgets.QLabel(text)
                label.setWordWrap(True)
                step_layout.addWidget(label)
            help_toggle = QtWidgets.QToolButton()
            help_toggle.setText("How To Use")
            help_toggle.setCheckable(True)
            help_toggle.setChecked(False)
            help_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            help_toggle.setToolTip("Show the short Dynamic Parenting setup guide.")
            step_box.setVisible(False)
            help_toggle.toggled.connect(step_box.setVisible)
            advanced_layout.addWidget(help_toggle)
            advanced_layout.addWidget(step_box)

            advanced_help = QtWidgets.QLabel(
                "Setup and fine-control actions stay here so the target list and no-pop switch remain visible first."
            )
            advanced_help.setWordWrap(True)
            advanced_help.setProperty("aminateRole", "muted")
            advanced_layout.addWidget(advanced_help)

            history_group = QtWidgets.QGroupBox("History")
            history_layout = QtWidgets.QVBoxLayout(history_group)
            self.event_list = QtWidgets.QListWidget()
            self.event_list.setToolTip("Every saved switch for this object in this scene.")
            self.event_list.setMinimumHeight(54)
            self.event_list.setMaximumHeight(140)
            history_layout.addWidget(self.event_list)
            history_button_row = QtWidgets.QGridLayout()
            self.jump_button = QtWidgets.QPushButton("Jump To Frame")
            self.delete_switch_button = QtWidgets.QPushButton("Delete Picked Switch")
            self.clear_switches_button = QtWidgets.QPushButton("Delete All Switches")
            self.delete_switch_button.setProperty("aminateRole", "danger")
            self.clear_switches_button.setProperty("aminateRole", "danger")
            history_button_row.addWidget(self.jump_button, 0, 0)
            history_button_row.addWidget(self.delete_switch_button, 0, 1)
            history_button_row.addWidget(self.clear_switches_button, 0, 2)
            history_layout.addLayout(history_button_row)
            advanced_layout.addWidget(history_group)

            self.summary_box = QtWidgets.QPlainTextEdit()
            self.summary_box.setReadOnly(True)
            self.summary_box.setMaximumHeight(120)
            advanced_layout.addWidget(self.summary_box)
            main_layout.addWidget(self.advanced_widget)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            main_layout.addWidget(self.status_label)

            footer_layout = QtWidgets.QHBoxLayout()
            self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            footer_layout.addWidget(self.brand_label, 1)
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

            self.add_object_button.clicked.connect(self._add_object)
            self.remove_object_button.clicked.connect(self._remove_object)
            self.object_list.itemSelectionChanged.connect(self._pick_object_from_list)
            self.rename_button.clicked.connect(self._rename_object)
            self.maintain_offset_check.toggled.connect(self._toggle_maintain_offset)
            self.use_target_button.clicked.connect(self._use_target)
            self.snap_to_picked_button.clicked.connect(self._snap_to_picked_target)
            self.save_offset_button.clicked.connect(self._save_offset_to_picked_target)
            self.parent_to_picked_button.clicked.connect(self._parent_to_picked_target)
            self.add_target_button.clicked.connect(self._add_target)
            self.parent_to_row_button.clicked.connect(self._parent_to_row)
            self.save_offset_row_button.clicked.connect(self._save_offset_to_row)
            self.parent_to_world_button.clicked.connect(self._parent_to_world)
            self.apply_weights_button.clicked.connect(self._apply_weights)
            self.fix_pop_button.clicked.connect(self._refresh_active_weights)
            self.remove_target_button.clicked.connect(self._remove_target)
            self.jump_button.clicked.connect(self._jump_to_event)
            self.delete_switch_button.clicked.connect(self._delete_event)
            self.clear_switches_button.clicked.connect(self._clear_events)
            self.event_list.itemDoubleClicked.connect(self._jump_to_event)
            self.advanced_toggle.toggled.connect(self._toggle_advanced)
            scroll_area.setWidget(content_widget)
            root_layout.addWidget(scroll_area)

        def _selected_target_ids(self):
            rows = sorted(set(index.row() for index in self.targets_table.selectionModel().selectedRows()))
            target_ids = []
            for row_index in rows:
                item = self.targets_table.item(row_index, 0)
                target_id = item.data(QtCore.Qt.UserRole) if item else ""
                if target_id:
                    target_ids.append(target_id)
            return target_ids

        def _selected_event_frame(self):
            item = self.event_list.currentItem()
            if not item:
                return None
            payload = item.data(QtCore.Qt.UserRole) or {}
            if not isinstance(payload, dict):
                return payload
            return payload.get("frame")

        def _selected_event_id(self):
            item = self.event_list.currentItem()
            if not item:
                return ""
            payload = item.data(QtCore.Qt.UserRole) or {}
            if not isinstance(payload, dict):
                return ""
            return payload.get("id") or ""

        def _weight_map_from_ui(self):
            return {target_id: float(spin_box.value()) for target_id, spin_box in self._weight_widgets.items()}

        def _sync_from_controller(self):
            setup = self.controller.current_setup()
            self.objects_line.setText(setup["driven"] if setup else "")
            self.target_line.setText(_short_name(self.controller.pending_target_node))
            self.object_list.blockSignals(True)
            self.object_list.clear()
            for payload in self.controller.setup_payloads(from_selection=False):
                item = QtWidgets.QListWidgetItem(payload["label"])
                item.setData(QtCore.Qt.UserRole, payload["setup_group"])
                item.setToolTip(payload["driven"])
                self.object_list.addItem(item)
                if setup and payload["setup_group"] == setup["setup_group"]:
                    self.object_list.setCurrentItem(item)
            self.object_list.blockSignals(False)
            self.list_name_line.setText(setup["label"] if setup else "")
            self.maintain_offset_check.blockSignals(True)
            self.maintain_offset_check.setChecked(bool(setup["maintain_offset"]) if setup else True)
            self.maintain_offset_check.blockSignals(False)

            self._weight_widgets = {}
            self.targets_table.setRowCount(0)
            self.event_list.clear()
            if setup:
                payload = self.controller._payload_for_setup(setup)
                for row_index, target in enumerate(payload["targets"]):
                    self.targets_table.insertRow(row_index)
                    name_item = QtWidgets.QTableWidgetItem(target["label"])
                    name_item.setData(QtCore.Qt.UserRole, target["id"])
                    self.targets_table.setItem(row_index, 0, name_item)
                    spin_box = QtWidgets.QDoubleSpinBox()
                    spin_box.setRange(0.0, 1.0)
                    spin_box.setDecimals(2)
                    spin_box.setSingleStep(0.1)
                    spin_box.setValue(float(payload["current_weights"].get(target["id"], 0.0)))
                    self.targets_table.setCellWidget(row_index, 1, spin_box)
                    self._weight_widgets[target["id"]] = spin_box
                    state_item = QtWidgets.QTableWidgetItem("On" if payload["current_weights"].get(target["id"], 0.0) > EPSILON else "Off")
                    self.targets_table.setItem(row_index, 2, state_item)
                    quick_button = QtWidgets.QPushButton("Switch to this Parent")
                    quick_button.setToolTip("Keep the current parent on this frame, then switch fully to this parent on the next frame.")
                    quick_button.clicked.connect(lambda _checked=False, target_id=target["id"]: self._parent_to_target_id(target_id))
                    self.targets_table.setCellWidget(row_index, 3, quick_button)
                for event in self.controller.event_items(setup):
                    item = QtWidgets.QListWidgetItem(event["display"])
                    item.setData(QtCore.Qt.UserRole, {"id": event.get("id", ""), "frame": event["frame"]})
                    self.event_list.addItem(item)
                if self.event_list.count():
                    self.event_list.setCurrentRow(self.event_list.count() - 1)
                self.summary_box.setPlainText(self.controller.summary_text(setup))
            else:
                self.summary_box.setPlainText(self.controller.summary_text(None))

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)
            self._sync_from_controller()

        def _toggle_advanced(self, enabled):
            self.advanced_widget.setVisible(bool(enabled))
            self.advanced_toggle.setText("Less" if enabled else "More")

        def _add_object(self):
            success, message = self.controller.add_driven_from_selection(
                start_in_current_position=self.start_in_place_check.isChecked()
            )
            self._set_status(message, success)

        def _remove_object(self):
            current_setup = self.controller.current_setup()
            if not current_setup:
                self._set_status("Pick a constrained object from the list first.", False)
                return
            answer = QtWidgets.QMessageBox.question(
                self,
                "Remove Object",
                "Remove {0} from Dynamic Parenting?\n\nThis will delete this tool's constraints, saved parent choices, and saved switches for this object.".format(current_setup["label"]),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                self._set_status("Kept {0} in Dynamic Parenting.".format(current_setup["label"]), True)
                return
            success, message = self.controller.remove_active_setup()
            self._set_status(message, success)

        def _pick_object_from_list(self):
            item = self.object_list.currentItem()
            if not item:
                return
            success, message = self.controller.set_active_setup(item.data(QtCore.Qt.UserRole))
            self._set_status(message, success)

        def _rename_object(self):
            success, message = self.controller.rename_active_setup(self.list_name_line.text())
            self._set_status(message, success)

        def _toggle_maintain_offset(self):
            success, message = self.controller.set_maintain_offset(self.maintain_offset_check.isChecked())
            self._set_status(message, success)

        def _use_target(self):
            success, message = self.controller.set_pending_target_from_selection()
            self._set_status(message, success)

        def _add_target(self):
            success, message = self.controller.add_targets_from_selection()
            self._set_status(message, success)

        def _parent_to_picked_target(self):
            if not self.controller.pending_target_node or not cmds.objExists(self.controller.pending_target_node):
                success, message = self.controller.set_pending_target_from_selection()
                if not success:
                    self._set_status(message, success)
                    return
            success, message = self.controller.apply_pending_target()
            self._set_status(message, success)

        def _snap_to_picked_target(self):
            if not self.controller.pending_target_node or not cmds.objExists(self.controller.pending_target_node):
                success, message = self.controller.set_pending_target_from_selection()
                if not success:
                    self._set_status(message, success)
                    return
            success, message = self.controller.snap_pending_target()
            self._set_status(message, success)

        def _save_offset_to_picked_target(self):
            if not self.controller.pending_target_node or not cmds.objExists(self.controller.pending_target_node):
                success, message = self.controller.set_pending_target_from_selection()
                if not success:
                    self._set_status(message, success)
                    return
            success, message = self.controller.save_offset_to_pending_target()
            self._set_status(message, success)

        def _parent_to_target_id(self, target_id):
            success, message = self.controller.parent_fully_to_target(target_id, action_label="switch")
            self._set_status(message, success)

        def _parent_to_row(self):
            target_ids = self._selected_target_ids()
            if not target_ids:
                self._set_status("Pick a parent row first.", False)
                return
            success, message = self.controller.parent_fully_to_target(target_ids[0], action_label="switch")
            self._set_status(message, success)

        def _save_offset_to_row(self):
            target_ids = self._selected_target_ids()
            if not target_ids:
                self._set_status("Pick a parent row first.", False)
                return
            success, message = self.controller.save_offset_to_target_id(target_ids[0])
            self._set_status(message, success)

        def _parent_to_world(self):
            success, message = self.controller.parent_to_world()
            self._set_status(message, success)

        def _apply_weights(self):
            success, message = self.controller.apply_weight_map(self._weight_map_from_ui(), action_label="blend")
            self._set_status(message, success)

        def _refresh_active_weights(self):
            success, message = self.controller.reseed_active_weights()
            self._set_status(message, success)

        def _remove_target(self):
            success, message = self.controller.remove_target_ids(self._selected_target_ids())
            self._set_status(message, success)

        def _jump_to_event(self, *_args):
            frame_value = self._selected_event_frame()
            if frame_value is None:
                self._set_status("Pick a saved switch first.", False)
                return
            success, message = self.controller.jump_to_event(frame_value)
            self._set_status(message, success)

        def _delete_event(self):
            event_id = self._selected_event_id()
            frame_value = self._selected_event_frame()
            if not event_id and frame_value is None:
                self._set_status("Pick a saved switch first.", False)
                return
            success, message = self.controller.delete_event(event_id, frame_value=frame_value)
            self._set_status(message, success)

        def _clear_events(self):
            success, message = self.controller.clear_event_log()
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


__all__ = ["MayaDynamicParentingController", "MayaDynamicParentingWindow"]
