from __future__ import absolute_import, division, print_function

import collections
import json
import math
import os
import re
import textwrap
import time

import maya_aminate_icon_manifest
import maya_contact_hold as hold_utils
import maya_crash_recovery as crash_recovery
import maya_floating_channel_box
import maya_history_timeline

try:
    import maya.cmds as cmds
    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    MAYA_AVAILABLE = False

try:
    # Keep the Qt bridge owned by this module.  Do not reach through
    # maya_contact_hold for OpenMayaUI: Contact Hold is a feature module and
    # does not promise to export UI bridge dependencies.
    from maya import OpenMayaUI as omui
except Exception:
    omui = None

try:
    import maya.mel as mel
except Exception:
    mel = None

try:
    from PySide2 import QtCore, QtGui, QtWidgets
    import shiboken2 as shiboken
except Exception:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        import shiboken6 as shiboken
    except Exception:
        QtCore = QtGui = QtWidgets = None
        shiboken = None

try:
    import maya.api.OpenMaya as om2
except Exception:
    om2 = None

try:
    import maya.api.OpenMayaAnim as oma2
except Exception:
    oma2 = None


def _qt_enum_int(value, default=0):
    try:
        return int(value)
    except Exception:
        try:
            return int(getattr(value, "value", default))
        except Exception:
            return int(default)


def _qt_object_valid(widget):
    if widget is None:
        return False
    if shiboken:
        try:
            return bool(shiboken.isValid(widget))
        except Exception:
            pass
    try:
        widget.objectName()
        return True
    except Exception:
        return False


def _qt_cursor(name):
    if not QtCore or not QtGui:
        return None
    shape = getattr(QtCore.Qt, name, None)
    if shape is None:
        enum = getattr(QtCore.Qt, "CursorShape", None)
        if enum and hasattr(enum, name):
            shape = getattr(enum, name)
    if shape is None:
        shape = getattr(QtCore.Qt, "ArrowCursor", None)
    try:
        return QtGui.QCursor(shape)
    except Exception:
        return QtGui.QCursor()


def _qt_modifier_value(name):
    if not QtCore:
        return 0
    value = getattr(QtCore.Qt, name, None)
    if value is not None:
        return _qt_enum_int(value)
    enum = getattr(QtCore.Qt, "KeyboardModifier", None)
    if enum and hasattr(enum, name):
        return _qt_enum_int(getattr(enum, name))
    return 0


def _hotkey_name_from_qt_event(event):
    if not QtCore or event is None:
        return ""
    modifier_parts = []
    modifiers = _qt_enum_int(event.modifiers() if hasattr(event, "modifiers") else 0)
    for label, qt_name in (
        ("Ctrl", "ControlModifier"),
        ("Shift", "ShiftModifier"),
        ("Alt", "AltModifier"),
        ("Meta", "MetaModifier"),
    ):
        if modifiers & _qt_modifier_value(qt_name):
            modifier_parts.append(label)

    key_value = _qt_enum_int(event.key() if hasattr(event, "key") else 0)
    modifier_key_values = set()
    for key_name in (
        "Key_Control",
        "Key_Shift",
        "Key_Alt",
        "Key_Meta",
        "Key_unknown",
    ):
        value = getattr(QtCore.Qt, key_name, None)
        if value is not None:
            modifier_key_values.add(_qt_enum_int(value))
        enum = getattr(QtCore.Qt, "Key", None)
        if enum and hasattr(enum, key_name):
            modifier_key_values.add(_qt_enum_int(getattr(enum, key_name)))
    if key_value in modifier_key_values:
        return ""

    text_value = ""
    try:
        text_value = event.text() or ""
    except Exception:
        text_value = ""
    key_part = ""
    if text_value in ("#", ";", ":", "'", "`", "\\"):
        key_part = maya_floating_channel_box.normalize_hotkey(text_value)
    elif len(text_value) == 1 and text_value.strip():
        key_part = text_value.upper()

    if not key_part:
        for index in range(1, 25):
            qt_name = "Key_F{0}".format(index)
            value = getattr(QtCore.Qt, qt_name, None)
            if value is not None and key_value == _qt_enum_int(value):
                key_part = "F{0}".format(index)
                break
            enum = getattr(QtCore.Qt, "Key", None)
            if enum and hasattr(enum, qt_name) and key_value == _qt_enum_int(getattr(enum, qt_name)):
                key_part = "F{0}".format(index)
                break
    if not key_part and QtGui:
        try:
            key_part = QtGui.QKeySequence(key_value).toString() or ""
        except Exception:
            key_part = ""
    if not key_part:
        return ""
    return maya_floating_channel_box.normalize_hotkey("+".join(modifier_parts + [key_part]))

WINDOW_OBJECT_NAME = "mayaTimingToolsWindow"
STUDENT_TIMELINE_BAR_OBJECT_NAME = "studentCoreTimelineButtonBarWindow"
STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME = STUDENT_TIMELINE_BAR_OBJECT_NAME + "WorkspaceControl"
STUDENT_TIMELINE_BAR_FIXED_HOST_OBJECT_NAME = "aminateFixedBottomToolkitBarHost"
AUTO_SNAP_OPTION = "AmirAminateAutoSnapToFrames"
ANIMATION_LAYER_TINT_OPTION = "AmirAminateAnimationLayerTint"
KEEP_TOOLBAR_EXTRAS_ON_HIDE_OPTION = "AmirAminateKeepToolbarExtrasOnHide"
GAME_ANIMATION_MODE_OPTION = "AmirAminateGameAnimationMode"
GAME_ANIMATION_MODE_ACTION_OPTION_PREFIX = "AmirAminateGameAnimationModeAction"
FLOATING_CHANNEL_BOX_HOTKEY_OPTION = maya_floating_channel_box.HOTKEY_OPTION
TWEEN_MACHINE_HOTKEY_OPTION = "AmirAminateTweenMachineHotkey"
TWEEN_MACHINE_OPACITY_OPTION = "AmirAminateTweenMachineOpacity"
TOOLKIT_HOVER_ICON_PIXELS_OPTION = "AmirAminateToolkitHoverIconPixels"
TOOLKIT_HOVER_OPACITY_OPTION = "AmirAminateToolkitHoverOpacity"
TOOLKIT_HOVER_WORDING_MODE_OPTION = "AmirAminateToolkitHoverWordingMode"
DEFAULT_TWEEN_MACHINE_HOTKEY = "Backquote"
LEGACY_DEFAULT_TWEEN_MACHINE_HOTKEYS = ("Ctrl+Alt+T",)
DEFAULT_TWEEN_MACHINE_OPACITY = 0.82
DEFAULT_TOOLKIT_HOVER_ICON_PIXELS = 56
DEFAULT_TOOLKIT_HOVER_OPACITY = 0.96
DEFAULT_TOOLKIT_HOVER_WORDING_MODE = "simple"
TOOLKIT_HOVER_WORDING_MODES = ("simple", "kid", "technical")
TOOLKIT_CUSTOM_HOVER_CARDS_ENABLED = True
TOOLKIT_HOVER_DELAY_MS = 350
TOOLKIT_HOVER_ANIMATION_MS = 150
_TWEEN_MACHINE_HOTKEY_MANAGER = None
_TWEEN_MACHINE_POPUP = None
ANIMATION_LAYER_CUSTOM_COLOR_ATTR = "aminateLayerColor"
DEFAULT_AUTO_SNAP = True
DEFAULT_ANIMATION_LAYER_TINT = True
DEFAULT_KEEP_TOOLBAR_EXTRAS_ON_HIDE = True
DEFAULT_GAME_ANIMATION_MODE = False
DEFAULT_TIME_UNIT = "ntsc"
DEFAULT_PLAYBACK_SPEED = 1.0
DEFAULT_MAX_BACKUPS = 5
TEXTURE_BASENAME_INDEX_FILE_LIMIT = 15000
TEXTURE_BASENAME_INDEX_SECONDS_LIMIT = 2.0
GAME_ANIMATION_MODE_ICON_FILE = "game_animation_mode_icon.png"
COMBINE_FREEZE_PIVOT_ICON_FILE = "combine_freeze_pivot_icon.png"
STUDENT_CORE_ICON_FILES = {
    "toolkit_nudge_left": "toolkit_nudge_left_icon.png",
    "toolkit_nudge_right": "toolkit_nudge_right_icon.png",
    "toolkit_insert_inbetween": "toolkit_insert_inbetween_icon.png",
    "toolkit_tween_machine": "toolkit_tween_machine_icon.png",
    "toolkit_cut_key": "toolkit_cut_key_icon.png",
    "toolkit_reset_pose": "toolkit_reset_pose_icon.png",
    "toolkit_bake_twos": "toolkit_bake_twos_icon.png",
    "toolkit_select_animated": "toolkit_select_animated_icon.png",
    "toolkit_clean_static": "toolkit_clean_static_icon.png",
    "toolkit_package_zip": "toolkit_package_zip_icon.png",
    "playblast": "toolkit_package_zip_icon.png",
    "combine_freeze_pivot": COMBINE_FREEZE_PIVOT_ICON_FILE,
    "game": GAME_ANIMATION_MODE_ICON_FILE,
}
_WORKFLOW_ICON_CACHE = {}
_ACTION_ICON_CACHE = {}
ANIM_CURVE_TYPES = (
    "animCurveTA",
    "animCurveTL",
    "animCurveTT",
    "animCurveTU",
    "animCurveUA",
    "animCurveUL",
    "animCurveUT",
    "animCurveUU",
)
GAME_ANIMATION_MODE_ACTIONS = collections.OrderedDict(
    (
        ("time_unit", ("30 fps", "Set Maya time unit to 30 fps ntsc.")),
        ("playback_speed", ("Realtime", "Set playback speed to realtime.")),
        ("update_view_all", ("Update All Views", "Set Time Slider Update View to All.")),
        ("autosave", ("Autosave", "Enable autosave with five backups.")),
        ("activate_viewports", ("Activate Focused Viewport", "Mark the focused model panel as the active view.")),
        ("load_textures", ("Load Textures", "Refresh and repath texture nodes.")),
        ("weighted_tangents", ("Weighted Tangents", "Convert all existing animation curves and future tangent defaults to weighted tangents.")),
    )
)
MAYA_SECURITY_PROMPT_OPTION_VARS = (
    "SafeModeOption",
    "SafeModeImportOption",
    "SafeModeBuiltInCheck",
    "SafeModeUserSetupHashOption",
    "TrustCenterPathOption",
)
DEFAULT_RENDER_ENV_LIGHT_EXPOSURE = 1.5
DEFAULT_RENDER_ENV_LIGHT_INTENSITY = 0.2
DEFAULT_RENDER_ENV_SCALE_MULTIPLIER = 3.5
DEFAULT_SCENE_HELPERS_CAMERA_BASE_HEIGHT = 5.0
DEFAULT_SCENE_HELPERS_CAMERA_HEIGHT_OFFSET = 0.0
DEFAULT_SCENE_HELPERS_CAMERA_DOLLY_OFFSET = 0.0
DEFAULT_TEACHER_RIG_DUPLICATE_OFFSET_X = 50.0
AUTO_KEY_WARNING_TOAST_MESSAGE = "You're animating without Auto-Key, Amir suggests you turn on Auto-key."
GAME_ANIMATION_FPS_WARNING_TOAST_MESSAGE = "If you're creating a game animation, remember to set it to 30 frames per second."
GAME_MODE_AUTO_HISTORY_PROMPT_TITLE = "Auto History with Game Mode"
GAME_MODE_AUTO_HISTORY_PROMPT_TEXT = (
    "Do you want Auto History on?\n\n"
    "It auto saves snapshots every few actions and allows you to jump back in time on your work.\n\n"
    "Default is: 90 backups.\n\n"
    "File Size super intensive - this is the amount of Maya files it will save before deleting old saves.\n\n"
    "You can change this in the 'History Timeline Settings'."
)
AUTO_KEY_WARNING_TOAST_DURATION_MS = 4000
GAME_ANIMATION_FPS_WARNING_TOAST_DURATION_MS = 5000
AUTO_KEY_WARNING_TOAST_THROTTLE_SECONDS = 8.0
TEACHER_RIG_DUPLICATE_SUFFIX = "_AMINATE_TEACHER"
TEACHER_RIG_DUPLICATE_GROUP_SUFFIX = "_OFFSET_GRP"
TEACHER_RIG_DUPLICATE_LAYER_NAME = "aminateTeacherDuplicate_LYR"
TEACHER_RIG_DUPLICATE_MARKER_ATTR = "aminateTeacherDemoDuplicate"
TEACHER_RIG_DUPLICATE_SOURCE_ATTR = "teacherDemoSource"
TEACHER_RIG_DUPLICATE_EDIT_BASELINE_ATTR = "teacherDemoEditBaselineJson"
TEACHER_RIG_DUPLICATE_EDIT_LOG_TEXT_ATTR = "teacherDemoEditLogText"
TEACHER_RIG_DUPLICATE_EDIT_LOG_GROUP_NAME = "aminateTeacherDemoEditLog_GRP"
TEACHER_RIG_DUPLICATE_EDIT_LOG_MARKER_ATTR = "aminateTeacherDemoEditLog"
TEACHER_RIG_DUPLICATE_EDIT_LOG_DISPLAY_SCALE = 1.6
TEACHER_RIG_DUPLICATE_EDIT_LOG_WRAP_CHARS = 92
TEACHER_RIG_DUPLICATE_EDIT_VECTOR_ATTRS = collections.OrderedDict(
    (
        ("translate", ("moved", ("translateX", "translateY", "translateZ"))),
        ("rotate", ("rotated", ("rotateX", "rotateY", "rotateZ"))),
        ("scale", ("scaled", ("scaleX", "scaleY", "scaleZ"))),
    )
)
TEACHER_RIG_DUPLICATE_EDIT_STANDARD_ATTRS = set(
    attr_name
    for _group_name, (_verb, attr_names) in TEACHER_RIG_DUPLICATE_EDIT_VECTOR_ATTRS.items()
    for attr_name in attr_names
)
TEACHER_RIG_DUPLICATE_EDIT_VALUE_EPSILON = 1.0e-4
SCENE_TEXT_NOTE_ROOT_PREFIX = "aminateSceneTextNote"
SCENE_TEXT_NOTE_GROUP_NAME = "aminateSceneTextNotes_GRP"
SCENE_TEXT_NOTE_ATTR = "aminateSceneTextNote"
SCENE_TEXT_NOTE_TEXT_ATTR = "noteText"
SCENE_TEXT_NOTE_ANCHOR_ATTR = "anchorNode"
SCENE_TEXT_NOTE_COLOR_ATTR = "noteColor"
SCENE_TEXT_NOTE_LINE_ATTR = "lineNode"
SCENE_TEXT_NOTE_SIZE_ATTR = "noteSize"
SCENE_TEXT_NOTE_WRAP_ATTR = "wrapEnabled"
SCENE_TEXT_NOTE_BOX_WIDTH_ATTR = "wrapBoxWidth"
SCENE_TEXT_NOTE_BOX_HEIGHT_ATTR = "wrapBoxHeight"
SCENE_TEXT_NOTE_WRAP_BOX_CONTROL_ATTR = "wrapBoxControl"
SCENE_TEXT_NOTE_WRAP_BOX_OWNER_ATTR = "wrapBoxOwnerNote"
SCENE_TEXT_NOTE_WRAP_BOX_BASE_WIDTH_ATTR = "wrapBoxBaseWidth"
SCENE_TEXT_NOTE_WRAP_BOX_BASE_HEIGHT_ATTR = "wrapBoxBaseHeight"
SCENE_TEXT_NOTE_DEFAULT_COLOR = "#F6C85F"
SCENE_TEXT_NOTE_DEFAULT_SCALE = 15.0
SCENE_TEXT_NOTE_MIN_SCALE = 0.1
SCENE_TEXT_NOTE_MAX_SCALE = 500.0
SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED = True
SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH = 220.0
SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT = 90.0
SCENE_TEXT_NOTE_MIN_BOX_SIZE = 1.0
SCENE_TEXT_NOTE_MAX_BOX_SIZE = 10000.0
SCENE_TEXT_NOTE_WRAP_BOX_CONTROL_SUFFIX = "_WRAP_BOX_CTRL"
SCENE_TEXT_NOTE_WRAP_BOX_JOB_MARKER = "AMINATE_SCENE_TEXT_NOTE_WRAP_BOX_JOB"
SCENE_TEXT_NOTE_LINE_GROUP_SUFFIX = "_LINE_GRP"
SCENE_TEXT_NOTE_MIN_LINE_SPACING = 0.35
SCENE_TEXT_NOTE_OFFSET = (0.0, 0.0, 0.0)
SCENE_TEXT_NOTE_COLORS = collections.OrderedDict(
    (
        ("Yellow", "#F6C85F"),
        ("White", "#F4F4F4"),
        ("Cyan", "#55CBCD"),
        ("Green", "#7BD88F"),
        ("Red", "#EF6F6C"),
        ("Blue", "#72B7F2"),
        ("Pink", "#EF476F"),
    )
)
SCENE_HELPERS_ROOT_NAME = "amirSceneHelpers_GRP"
_AUTO_KEY_WARNING_CALLBACK_ID = None
_AUTO_KEY_WARNING_TOAST = None
_WARNING_TOAST_QUEUE = []
_WARNING_TOAST_ACTIVE = None
_WARNING_TOAST_LAST_SHOWN = {
    "auto_key": 0.0,
    "fps_game": 0.0,
}
_WARNING_TOAST_SESSION_SHOWN = set()
SCENE_HELPERS_RENDER_ROOT_NAME = "amirSceneRenderEnv_GRP"
SCENE_HELPERS_CAMERA_ROOT_NAME = "amirSceneRenderCameras_GRP"
SCENE_HELPERS_LIGHT_ROOT_NAME = "amirSceneRenderLights_GRP"
SCENE_HELPERS_FLOOR_NAME = "amirSceneRenderFloor_GEO"
SCENE_HELPERS_BACKDROP_NAME = "amirSceneRenderBackdrop_GEO"
SCENE_HELPERS_CYCLORAMA_NAME = "amirSceneCyclorama_GEO"
SCENE_HELPERS_CYCLORAMA_MAT_NAME = "sceneHelpersCyclorama_MAT"
SCENE_HELPERS_CYCLORAMA_SG_NAME = "sceneHelpersCyclorama_MATSG"
SCENE_HELPERS_CYCLORAMA_ATTR = "sceneHelpersCyclorama"
SCENE_HELPERS_INFINITY_WALL_NAME = SCENE_HELPERS_CYCLORAMA_NAME
SCENE_HELPERS_LEGACY_INFINITY_WALL_NAME = "amirSceneRenderInfinityWall_GEO"
SCENE_HELPERS_INFINITY_WALL_MAT_NAME = SCENE_HELPERS_CYCLORAMA_MAT_NAME
SCENE_HELPERS_INFINITY_WALL_SG_NAME = SCENE_HELPERS_CYCLORAMA_SG_NAME
ANIMATION_LAYER_TINT_PALETTE = (
    "#EF6F6C",
    "#55CBCD",
    "#F6C85F",
    "#B86BFF",
    "#7BD88F",
    "#72B7F2",
    "#F4A261",
    "#2A9D8F",
    "#EF476F",
    "#06D6A0",
    "#577590",
    "#CDB4DB",
)


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


def _node_short_name(node_name):
    return (node_name or "").split("|")[-1]


def _node_base_name(node_name):
    return _node_short_name(node_name).split(":")[-1]


def _safe_scene_node_name(raw_name, fallback="aminateNode"):
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", raw_name or "").strip("_")
    if not safe_name:
        safe_name = fallback
    if safe_name[0].isdigit():
        safe_name = "n_" + safe_name
    return safe_name


def _unique_scene_node_name(base_name):
    base_name = _safe_scene_node_name(base_name)
    if not MAYA_AVAILABLE or not cmds or not cmds.objExists(base_name):
        return base_name
    index = 1
    while cmds.objExists("{0}{1}".format(base_name, index)):
        index += 1
    return "{0}{1}".format(base_name, index)


def _long_scene_name(node_name):
    matches = cmds.ls(node_name, long=True) or []
    return matches[0] if matches else node_name


def _selected_transform_roots():
    if not MAYA_AVAILABLE or not cmds:
        return []
    selected = cmds.ls(selection=True, long=True) or []
    transforms = []
    for node_name in selected:
        node_type = cmds.nodeType(node_name)
        transform_node = node_name
        if node_type != "transform" and node_type != "joint":
            parent = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
            if parent and cmds.nodeType(parent[0]) in ("transform", "joint"):
                transform_node = parent[0]
            else:
                continue
        long_name = _long_scene_name(transform_node)
        if long_name not in transforms:
            transforms.append(long_name)
    roots = []
    for candidate in transforms:
        candidate_is_child = False
        for other in transforms:
            if candidate != other and candidate.startswith(other + "|"):
                candidate_is_child = True
                break
        if not candidate_is_child:
            roots.append(candidate)
    return roots


def _dag_hierarchy_in_order(root_node):
    root_node = _long_scene_name(root_node)
    ordered = [root_node]

    def _walk(parent_node):
        children = cmds.listRelatives(parent_node, children=True, fullPath=True) or []
        for child in children:
            ordered.append(child)
            _walk(child)

    _walk(root_node)
    return ordered


def _copy_keyed_attributes(source_node, target_node):
    copied_attrs = 0
    attrs = set(cmds.listAttr(source_node, keyable=True) or [])
    attrs.update(cmds.listAttr(source_node, channelBox=True) or [])
    for attr_name in sorted(attrs):
        target_attr = "{0}.{1}".format(target_node, attr_name)
        if not cmds.objExists(target_attr):
            continue
        try:
            if cmds.getAttr(target_attr, lock=True):
                continue
        except Exception:
            continue
        try:
            key_count = cmds.copyKey(source_node, attribute=attr_name)
        except Exception:
            key_count = 0
        if not key_count:
            continue
        try:
            cmds.cutKey(target_node, attribute=attr_name, clear=True)
        except Exception:
            pass
        try:
            cmds.pasteKey(target_node, attribute=attr_name, option="replaceCompletely")
            copied_attrs += 1
        except Exception:
            pass
    return copied_attrs


def _copy_hierarchy_keyframes(source_root, duplicate_root):
    source_nodes = _dag_hierarchy_in_order(source_root)
    duplicate_nodes = _dag_hierarchy_in_order(duplicate_root)
    copied_attrs = 0
    for source_node, duplicate_node in zip(source_nodes, duplicate_nodes):
        try:
            copied_attrs += _copy_keyed_attributes(source_node, duplicate_node)
        except Exception:
            pass
    return copied_attrs


def _remove_nodes_from_display_layers(nodes):
    removed = 0
    for node_name in nodes:
        if not node_name or not cmds.objExists(node_name):
            continue
        had_layer = bool(_display_layers_for_node(node_name))
        try:
            cmds.editDisplayLayerMembers("defaultLayer", node_name, noRecurse=True)
            if had_layer:
                removed += 1
        except Exception:
            try:
                cmds.editDisplayLayerMembers("defaultLayer", _node_short_name(node_name), noRecurse=True)
                if had_layer:
                    removed += 1
            except Exception:
                pass
    return removed


def _display_layers_for_node(node_name):
    return [layer for layer in (cmds.listConnections(node_name, type="displayLayer") or []) if layer != "defaultLayer"]


def _source_display_layer_visible(node_name):
    for layer_name in _display_layers_for_node(node_name):
        try:
            if not bool(cmds.getAttr(layer_name + ".visibility")):
                return False
        except Exception:
            pass
    return True


def _copy_numeric_attr_value(source_node, target_node, attr_name):
    source_attr = "{0}.{1}".format(source_node, attr_name)
    target_attr = "{0}.{1}".format(target_node, attr_name)
    if not cmds.objExists(source_attr) or not cmds.objExists(target_attr):
        return
    try:
        if cmds.getAttr(target_attr, lock=True):
            return
    except Exception:
        pass
    try:
        value = cmds.getAttr(source_attr)
    except Exception:
        return
    try:
        if attr_name == "overrideColorRGB":
            if isinstance(value, (list, tuple)) and value:
                rgb_value = value[0] if isinstance(value[0], (list, tuple)) else value
                cmds.setAttr(target_attr, float(rgb_value[0]), float(rgb_value[1]), float(rgb_value[2]), type="double3")
        else:
            cmds.setAttr(target_attr, value)
    except Exception:
        pass


def _copy_visual_state(source_node, target_node):
    for attr_name in (
        "visibility",
        "lodVisibility",
        "overrideEnabled",
        "overrideDisplayType",
        "overrideLevelOfDetail",
        "overrideShading",
        "overrideTexturing",
        "overridePlayback",
        "overrideVisibility",
        "overrideRGBColors",
        "overrideColor",
        "overrideColorRGB",
        "hideOnPlayback",
        "displayLocalAxis",
        "drawStyle",
        "radius",
    ):
        _copy_numeric_attr_value(source_node, target_node, attr_name)
    if not _source_display_layer_visible(source_node) and cmds.objExists(target_node + ".visibility"):
        try:
            cmds.setAttr(target_node + ".visibility", False)
        except Exception:
            pass


def _copy_visual_state_for_pairs(pairs):
    for source_node, duplicate_node in pairs:
        try:
            _copy_visual_state(source_node, duplicate_node)
        except Exception:
            pass


def _copy_shading_assignments_for_pairs(pairs):
    copied = 0
    for source_node, duplicate_node in pairs:
        try:
            if cmds.nodeType(source_node) not in ("mesh", "nurbsSurface", "subdiv"):
                continue
        except Exception:
            continue
        shading_groups = cmds.listConnections(source_node, source=False, destination=True, type="shadingEngine") or []
        for shading_group in _dedupe_preserve_order(shading_groups):
            try:
                cmds.sets(duplicate_node, edit=True, forceElement=shading_group)
                copied += 1
            except Exception:
                pass
    return copied


def _disable_skinned_geometry_inherits_transform(root_node):
    # The offset group moves controls and joints. Skinned meshes must not inherit
    # that same group offset or the geometry gets transformed twice.
    changed = 0
    seen_transforms = set()
    for node_name in _dag_hierarchy_in_order(root_node):
        try:
            if cmds.nodeType(node_name) not in ("mesh", "nurbsSurface", "subdiv"):
                continue
        except Exception:
            continue
        has_skin_cluster = False
        for history_node in cmds.listHistory(node_name) or []:
            try:
                if cmds.nodeType(history_node) == "skinCluster":
                    has_skin_cluster = True
                    break
            except Exception:
                pass
        if not has_skin_cluster:
            continue
        parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
        if not parents:
            continue
        transform_node = parents[0]
        if transform_node in seen_transforms or not cmds.objExists(transform_node + ".inheritsTransform"):
            continue
        seen_transforms.add(transform_node)
        try:
            if bool(cmds.getAttr(transform_node + ".inheritsTransform")):
                cmds.setAttr(transform_node + ".inheritsTransform", False)
                changed += 1
        except Exception:
            pass
    return changed


def _node_from_uuid(uuid_value):
    if not uuid_value:
        return ""
    try:
        matches = cmds.ls(uuid_value, long=True) or []
        return matches[0] if matches else ""
    except Exception:
        return ""


def _resolve_uuid_pairs(uuid_pairs):
    resolved_pairs = []
    for source_node, duplicate_uuid in uuid_pairs:
        duplicate_node = _node_from_uuid(duplicate_uuid)
        if duplicate_node and cmds.objExists(source_node) and cmds.objExists(duplicate_node):
            resolved_pairs.append((source_node, duplicate_node))
    return resolved_pairs


def _create_teacher_duplicate_display_layer(offset_group):
    layer_name = _unique_scene_node_name(TEACHER_RIG_DUPLICATE_LAYER_NAME)
    try:
        layer_name = cmds.createDisplayLayer(name=layer_name, empty=True)
        cmds.editDisplayLayerMembers(layer_name, offset_group, noRecurse=True)
        return layer_name
    except Exception:
        return ""


def _rename_teacher_duplicate_hierarchy(source_root, duplicate_root):
    source_nodes = _dag_hierarchy_in_order(source_root)
    duplicate_nodes = _dag_hierarchy_in_order(duplicate_root)
    paired_nodes = []
    for source_node, duplicate_node in zip(source_nodes, duplicate_nodes):
        duplicate_uuid = ""
        try:
            duplicate_uuid = (cmds.ls(duplicate_node, uuid=True) or [""])[0]
        except Exception:
            duplicate_uuid = ""
        paired_nodes.append((source_node, duplicate_node, duplicate_uuid))
    renamed = {}
    for source_node, duplicate_node, _duplicate_uuid in sorted(paired_nodes, key=lambda pair: pair[1].count("|"), reverse=True):
        base_name = _safe_scene_node_name(_node_base_name(source_node), "teacherDuplicate")
        target_name = _unique_scene_node_name(base_name + TEACHER_RIG_DUPLICATE_SUFFIX)
        try:
            renamed[duplicate_node] = cmds.rename(duplicate_node, target_name)
        except Exception:
            renamed[duplicate_node] = duplicate_node
    duplicate_root = renamed.get(duplicate_root, duplicate_root)
    uuid_pairs = [(source_node, duplicate_uuid) for source_node, _duplicate_node, duplicate_uuid in paired_nodes]
    return _long_scene_name(duplicate_root), uuid_pairs


def _teacher_demo_duplicate_roots():
    roots = []
    candidates = []
    try:
        candidates.extend(cmds.ls("*.{0}".format(TEACHER_RIG_DUPLICATE_MARKER_ATTR), objectsOnly=True, long=True) or [])
    except Exception:
        pass
    try:
        candidates.extend(cmds.ls("*{0}*".format(TEACHER_RIG_DUPLICATE_SUFFIX), type="transform", long=True) or [])
    except Exception:
        pass
    for node_name in _dedupe_preserve_order(candidates):
        is_teacher_duplicate = False
        if cmds.objExists(node_name + "." + TEACHER_RIG_DUPLICATE_MARKER_ATTR):
            try:
                is_teacher_duplicate = bool(cmds.getAttr(node_name + "." + TEACHER_RIG_DUPLICATE_MARKER_ATTR))
            except Exception:
                is_teacher_duplicate = True
        if not is_teacher_duplicate and TEACHER_RIG_DUPLICATE_SUFFIX in _node_short_name(node_name):
            is_teacher_duplicate = True
        if is_teacher_duplicate:
            roots.append(node_name)
    top_roots = []
    for candidate in roots:
        has_teacher_parent = False
        for other in roots:
            if candidate != other and candidate.startswith(other + "|"):
                has_teacher_parent = True
                break
        if not has_teacher_parent:
            top_roots.append(candidate)
    return _dedupe_preserve_order(top_roots)


def _delete_teacher_demo_duplicate_layers():
    deleted = 0
    for layer_name in cmds.ls(TEACHER_RIG_DUPLICATE_LAYER_NAME + "*", type="displayLayer") or []:
        if layer_name == "defaultLayer":
            continue
        try:
            cmds.delete(layer_name)
            deleted += 1
        except Exception:
            pass
    return deleted


def _delete_teacher_demo_duplicates():
    roots = _teacher_demo_duplicate_roots()
    deleted = 0
    for root_name in roots:
        if not cmds.objExists(root_name):
            continue
        try:
            cmds.delete(root_name)
            deleted += 1
        except Exception:
            pass
    deleted_layers = _delete_teacher_demo_duplicate_layers()
    _delete_teacher_demo_edit_log_scene_nodes()
    return deleted, deleted_layers


def _teacher_demo_student_name(node_name):
    label = _node_base_name(node_name)
    if TEACHER_RIG_DUPLICATE_SUFFIX in label:
        label = label.split(TEACHER_RIG_DUPLICATE_SUFFIX, 1)[0]
    return label or _node_short_name(node_name)


def _teacher_demo_value_from_attr(node_name, attr_name):
    attr_path = "{0}.{1}".format(node_name, attr_name)
    if not cmds.objExists(attr_path):
        return None
    try:
        value = cmds.getAttr(attr_path)
    except Exception:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    if isinstance(value, (list, tuple)):
        return [float(item) if isinstance(item, (int, float)) else item for item in value]
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _teacher_demo_vector_value(node_name, attr_names):
    values = []
    for attr_name in attr_names:
        value = _teacher_demo_value_from_attr(node_name, attr_name)
        if value is None:
            return None
        values.append(float(value))
    return values


def _teacher_demo_allowed_scalar_attr(node_name, attr_name):
    if attr_name in TEACHER_RIG_DUPLICATE_EDIT_STANDARD_ATTRS:
        return False
    if "." in attr_name:
        return False
    attr_path = "{0}.{1}".format(node_name, attr_name)
    if not cmds.objExists(attr_path):
        return False
    try:
        attr_type = cmds.getAttr(attr_path, type=True)
    except Exception:
        return False
    return attr_type in (
        "bool",
        "byte",
        "double",
        "doubleAngle",
        "doubleLinear",
        "enum",
        "float",
        "long",
        "short",
        "string",
    )


def _teacher_demo_collect_edit_state(root_nodes):
    state = {}
    for root_node in root_nodes or []:
        if not root_node or not cmds.objExists(root_node):
            continue
        for node_name in _dag_hierarchy_in_order(root_node):
            try:
                node_type = cmds.nodeType(node_name)
            except Exception:
                continue
            if node_type not in ("transform", "joint"):
                continue
            try:
                node_uuid = (cmds.ls(node_name, uuid=True) or [""])[0]
            except Exception:
                node_uuid = ""
            if not node_uuid:
                continue
            label = _teacher_demo_student_name(node_name)
            for group_name, (verb, attr_names) in TEACHER_RIG_DUPLICATE_EDIT_VECTOR_ATTRS.items():
                value = _teacher_demo_vector_value(node_name, attr_names)
                if value is None:
                    continue
                state["{0}|{1}".format(node_uuid, group_name)] = {
                    "uuid": node_uuid,
                    "node": node_name,
                    "label": label,
                    "attr": group_name,
                    "verb": verb,
                    "kind": "vector",
                    "value": value,
                }
            attrs = set(cmds.listAttr(node_name, keyable=True) or [])
            attrs.update(cmds.listAttr(node_name, channelBox=True) or [])
            for attr_name in sorted(attrs):
                if not _teacher_demo_allowed_scalar_attr(node_name, attr_name):
                    continue
                value = _teacher_demo_value_from_attr(node_name, attr_name)
                if value is None:
                    continue
                state["{0}|{1}".format(node_uuid, attr_name)] = {
                    "uuid": node_uuid,
                    "node": node_name,
                    "label": label,
                    "attr": attr_name,
                    "verb": "changed",
                    "kind": "scalar",
                    "value": value,
                }
    return state


def _teacher_demo_set_baseline(root_node):
    if not root_node or not cmds.objExists(root_node):
        return False
    state = _teacher_demo_collect_edit_state([root_node])
    _ensure_string_attr(root_node, TEACHER_RIG_DUPLICATE_EDIT_BASELINE_ATTR, "")
    _ensure_string_attr(root_node, TEACHER_RIG_DUPLICATE_EDIT_LOG_TEXT_ATTR, "")
    try:
        cmds.setAttr(root_node + "." + TEACHER_RIG_DUPLICATE_EDIT_BASELINE_ATTR, json.dumps(state, sort_keys=True), type="string")
        return True
    except Exception:
        return False


def _teacher_demo_baseline_for_root(root_node):
    if not root_node or not cmds.objExists(root_node):
        return {}
    attr_path = root_node + "." + TEACHER_RIG_DUPLICATE_EDIT_BASELINE_ATTR
    if not cmds.objExists(attr_path):
        _teacher_demo_set_baseline(root_node)
    try:
        text = cmds.getAttr(attr_path) if cmds.objExists(attr_path) else ""
        return json.loads(text or "{}")
    except Exception:
        return {}


def _teacher_demo_values_equal(left_value, right_value):
    if isinstance(left_value, (list, tuple)) or isinstance(right_value, (list, tuple)):
        if not isinstance(left_value, (list, tuple)) or not isinstance(right_value, (list, tuple)):
            return False
        if len(left_value) != len(right_value):
            return False
        return all(_teacher_demo_values_equal(left_item, right_item) for left_item, right_item in zip(left_value, right_value))
    if isinstance(left_value, (int, float)) or isinstance(right_value, (int, float)):
        try:
            return abs(float(left_value) - float(right_value)) <= TEACHER_RIG_DUPLICATE_EDIT_VALUE_EPSILON
        except Exception:
            return False
    return left_value == right_value


def _teacher_demo_format_value(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(_teacher_demo_format_value(item) for item in value)
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if abs(numeric_value - round(numeric_value)) <= TEACHER_RIG_DUPLICATE_EDIT_VALUE_EPSILON:
            return str(int(round(numeric_value)))
        return "{0:.3f}".format(numeric_value).rstrip("0").rstrip(".")
    return str(value)


def _teacher_demo_edit_sentence(baseline_item, current_item):
    label = current_item.get("label") or baseline_item.get("label") or "Teacher demo control"
    old_value = _teacher_demo_format_value(baseline_item.get("value"))
    new_value = _teacher_demo_format_value(current_item.get("value"))
    if current_item.get("kind") == "vector":
        return "{0} {1} from {2} to {3}".format(label, current_item.get("verb") or "changed", old_value, new_value)
    attr_label = current_item.get("attr") or baseline_item.get("attr") or "value"
    return "{0} changed {1} from {2} to {3}".format(label, attr_label, old_value, new_value)


def _teacher_demo_edit_log_lines(order, records):
    return ["- {0}".format(records[key]["sentence"]) for key in order if key in records]


def _teacher_demo_edit_log_root():
    if not MAYA_AVAILABLE or not cmds:
        return ""
    if cmds.objExists(TEACHER_RIG_DUPLICATE_EDIT_LOG_GROUP_NAME):
        log_root = _long_scene_name(TEACHER_RIG_DUPLICATE_EDIT_LOG_GROUP_NAME)
    else:
        parent_root = _ensure_scene_helpers_root()
        log_root = cmds.createNode("transform", name=TEACHER_RIG_DUPLICATE_EDIT_LOG_GROUP_NAME, parent=parent_root)
    _ensure_bool_attr(log_root, TEACHER_RIG_DUPLICATE_EDIT_LOG_MARKER_ATTR, True)
    _ensure_string_attr(log_root, TEACHER_RIG_DUPLICATE_EDIT_LOG_TEXT_ATTR, "")
    try:
        cmds.setAttr(log_root + ".visibility", True)
    except Exception:
        pass
    return _long_scene_name(log_root)


def _teacher_demo_edit_log_text_holders(log_root):
    if not log_root or not cmds.objExists(log_root):
        return []
    holders = []
    for child in cmds.listRelatives(log_root, children=True, type="transform", fullPath=True) or []:
        if _node_short_name(child).endswith("_TEXT_GRP"):
            holders.append(child)
    return holders


def _teacher_demo_edit_log_display_lines(text):
    output = ["Teacher Demo Edit Log"]
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        prefix = "- " if line.startswith("- ") else ""
        body = line[2:].strip() if prefix else line
        wrapped = textwrap.wrap(
            body,
            width=TEACHER_RIG_DUPLICATE_EDIT_LOG_WRAP_CHARS,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [body]
        for index, wrapped_line in enumerate(wrapped):
            if prefix:
                output.append("- {0}".format(wrapped_line) if index == 0 else "  {0}".format(wrapped_line))
            else:
                output.append(wrapped_line)
    return output


def _teacher_demo_edit_log_position(root_nodes):
    for root_name in root_nodes or []:
        if not root_name or not cmds.objExists(root_name):
            continue
        try:
            box = cmds.exactWorldBoundingBox(root_name)
            return (float(box[3]) + 4.0, float(box[4]) + 4.0, float(box[2]))
        except Exception:
            pass
    return (0.0, 10.0, 0.0)


def _delete_teacher_demo_edit_log_scene_nodes():
    if not MAYA_AVAILABLE or not cmds:
        return 0
    deleted = 0
    candidates = []
    if cmds.objExists(TEACHER_RIG_DUPLICATE_EDIT_LOG_GROUP_NAME):
        candidates.append(TEACHER_RIG_DUPLICATE_EDIT_LOG_GROUP_NAME)
    for node_name in cmds.ls(type="transform", long=True) or []:
        if not cmds.objExists(node_name + "." + TEACHER_RIG_DUPLICATE_EDIT_LOG_MARKER_ATTR):
            continue
        try:
            if bool(cmds.getAttr(node_name + "." + TEACHER_RIG_DUPLICATE_EDIT_LOG_MARKER_ATTR)):
                candidates.append(node_name)
        except Exception:
            pass
    for node_name in _dedupe_preserve_order(candidates):
        if not cmds.objExists(node_name):
            continue
        try:
            cmds.delete(node_name)
            deleted += 1
        except Exception:
            pass
    return deleted


def _sync_teacher_demo_edit_log_scene_storage(root_nodes, text):
    if not MAYA_AVAILABLE or not cmds:
        return ""
    root_nodes = [root_name for root_name in (root_nodes or []) if root_name and cmds.objExists(root_name)]
    clean_text = text or ""
    if not root_nodes and not clean_text:
        if not cmds.objExists(TEACHER_RIG_DUPLICATE_EDIT_LOG_GROUP_NAME):
            return ""
        undo_state = True
        try:
            undo_state = bool(cmds.undoInfo(query=True, state=True))
            cmds.undoInfo(stateWithoutFlush=False)
        except Exception:
            undo_state = True
        try:
            _delete_teacher_demo_edit_log_scene_nodes()
        finally:
            try:
                cmds.undoInfo(stateWithoutFlush=undo_state)
            except Exception:
                pass
        return ""
    desired_position = _teacher_demo_edit_log_position(root_nodes)
    undo_state = True
    try:
        undo_state = bool(cmds.undoInfo(query=True, state=True))
        cmds.undoInfo(stateWithoutFlush=False)
    except Exception:
        undo_state = True
    try:
        log_root = _teacher_demo_edit_log_root()
        for root_name in root_nodes:
            _ensure_string_attr(root_name, TEACHER_RIG_DUPLICATE_EDIT_LOG_TEXT_ATTR, "")
            try:
                cmds.setAttr(root_name + "." + TEACHER_RIG_DUPLICATE_EDIT_LOG_TEXT_ATTR, clean_text, type="string")
            except Exception:
                pass
        _ensure_string_attr(log_root, TEACHER_RIG_DUPLICATE_EDIT_LOG_TEXT_ATTR, "")
        attr_path = log_root + "." + TEACHER_RIG_DUPLICATE_EDIT_LOG_TEXT_ATTR
        try:
            current_text = cmds.getAttr(attr_path) if cmds.objExists(attr_path) else ""
        except Exception:
            current_text = ""
        current_holders = _teacher_demo_edit_log_text_holders(log_root)
        if current_text == clean_text and ((clean_text and current_holders) or (not clean_text and not current_holders)):
            try:
                cmds.xform(log_root, worldSpace=True, translation=desired_position)
            except Exception:
                pass
            return log_root
        cmds.setAttr(attr_path, clean_text, type="string")
        for holder in _teacher_demo_edit_log_text_holders(log_root):
            if cmds.objExists(holder):
                try:
                    cmds.delete(holder)
                except Exception:
                    pass
        if clean_text:
            text_holder = cmds.createNode(
                "transform",
                name=_unique_scene_node_name(_node_base_name(log_root) + "_TEXT_GRP"),
                parent=log_root,
            )
            for line_index, line_text in enumerate(_teacher_demo_edit_log_display_lines(clean_text)):
                _create_text_curves_for_scene_note_line(log_root, text_holder, line_text, line_index)
            try:
                cmds.setAttr(
                    text_holder + ".scale",
                    TEACHER_RIG_DUPLICATE_EDIT_LOG_DISPLAY_SCALE,
                    TEACHER_RIG_DUPLICATE_EDIT_LOG_DISPLAY_SCALE,
                    TEACHER_RIG_DUPLICATE_EDIT_LOG_DISPLAY_SCALE,
                    type="double3",
                )
            except Exception:
                pass
            _set_display_color(log_root, "#55CBCD")
        try:
            cmds.xform(log_root, worldSpace=True, translation=desired_position)
            cmds.setAttr(log_root + ".visibility", True)
        except Exception:
            pass
    finally:
        try:
            cmds.undoInfo(stateWithoutFlush=undo_state)
        except Exception:
            pass
    return log_root


def _duplicate_rig_root_for_teacher_demo(root_node, offset_x=DEFAULT_TEACHER_RIG_DUPLICATE_OFFSET_X):
    root_node = _long_scene_name(root_node)
    root_base = _safe_scene_node_name(_node_base_name(root_node), "rig")
    offset_group = None
    duplicate_root = None
    copied_attrs = 0
    try:
        cmds.undoInfo(openChunk=True, chunkName="AminateDuplicateRigForTeacherDemo")
    except Exception:
        pass
    try:
        duplicate_nodes = cmds.duplicate(
            root_node,
            renameChildren=True,
            upstreamNodes=True,
            inputConnections=False,
            returnRootsOnly=True,
        ) or []
        if not duplicate_nodes:
            return False, "Could not duplicate selected rig root.", {}
        duplicate_root = _long_scene_name(duplicate_nodes[0])
        copied_attrs = _copy_hierarchy_keyframes(root_node, duplicate_root)
        duplicate_root, uuid_pairs = _rename_teacher_duplicate_hierarchy(root_node, duplicate_root)
        offset_group_name = _unique_scene_node_name(root_base + TEACHER_RIG_DUPLICATE_SUFFIX + TEACHER_RIG_DUPLICATE_GROUP_SUFFIX)
        offset_group = cmds.group(empty=True, name=offset_group_name)
        _ensure_bool_attr(offset_group, TEACHER_RIG_DUPLICATE_MARKER_ATTR, True)
        _ensure_string_attr(offset_group, TEACHER_RIG_DUPLICATE_SOURCE_ATTR, root_node)
        duplicate_root = _long_scene_name((cmds.parent(duplicate_root, offset_group) or [duplicate_root])[0])
        cmds.setAttr(offset_group + ".translateX", float(offset_x))
        disabled_skin_inherits = _disable_skinned_geometry_inherits_transform(duplicate_root)
        _remove_nodes_from_display_layers([offset_group] + _dag_hierarchy_in_order(duplicate_root))
        current_pairs = _resolve_uuid_pairs(uuid_pairs)
        _copy_visual_state_for_pairs(current_pairs)
        copied_shading = _copy_shading_assignments_for_pairs(current_pairs)
        layer_name = _create_teacher_duplicate_display_layer(offset_group)
        _teacher_demo_set_baseline(offset_group)
        try:
            cmds.select(offset_group, replace=True)
        except Exception:
            pass
        detail = {
            "offset_group": offset_group,
            "duplicate_root": _long_scene_name(duplicate_root),
            "display_layer": layer_name,
            "copied_keyed_attributes": copied_attrs,
            "copied_shading_assignments": copied_shading,
            "disabled_skin_geometry_inherits": disabled_skin_inherits,
            "offset_x": float(offset_x),
        }
        message = "Duplicated rig for teacher demo: {0}. Copied keyframes on {1} attribute(s), copied {2} shading assignment(s), isolated {3} skinned mesh transform(s), and offset X by {4:g}.".format(
            _node_short_name(offset_group),
            copied_attrs,
            copied_shading,
            disabled_skin_inherits,
            float(offset_x),
        )
        return True, message, detail
    except Exception as exc:
        if offset_group and cmds.objExists(offset_group):
            try:
                cmds.delete(offset_group)
            except Exception:
                pass
        elif duplicate_root and cmds.objExists(duplicate_root):
            try:
                cmds.delete(duplicate_root)
            except Exception:
                pass
        return False, "Rig duplicate failed: {0}".format(exc), {}
    finally:
        try:
            cmds.undoInfo(closeChunk=True)
        except Exception:
            pass


def _ensure_bool_attr(node_name, attr_name, default_value=False):
    if not cmds.objExists(node_name + "." + attr_name):
        cmds.addAttr(node_name, longName=attr_name, attributeType="bool")
    try:
        cmds.setAttr(node_name + "." + attr_name, bool(default_value))
    except Exception:
        pass


def _ensure_string_attr(node_name, attr_name, value=""):
    if not cmds.objExists(node_name + "." + attr_name):
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
    try:
        cmds.setAttr(node_name + "." + attr_name, value or "", type="string")
    except Exception:
        pass


def _ensure_double_attr(node_name, attr_name, value=0.0):
    if not cmds.objExists(node_name + "." + attr_name):
        cmds.addAttr(node_name, longName=attr_name, attributeType="double")
    try:
        cmds.setAttr(node_name + "." + attr_name, float(value))
    except Exception:
        pass


def _scene_text_note_nodes():
    if not MAYA_AVAILABLE or not cmds:
        return []
    notes = []
    for node_name in cmds.ls(type="transform", long=True) or []:
        if not cmds.objExists(node_name + "." + SCENE_TEXT_NOTE_ATTR):
            continue
        try:
            if bool(cmds.getAttr(node_name + "." + SCENE_TEXT_NOTE_ATTR)):
                notes.append(node_name)
        except Exception:
            pass
    if notes:
        _migrate_scene_text_notes_to_root(notes)
    return sorted(notes, key=lambda item: _node_short_name(item).lower())


def _ensure_scene_text_note_root():
    if cmds.objExists(SCENE_TEXT_NOTE_GROUP_NAME):
        return _long_scene_name(SCENE_TEXT_NOTE_GROUP_NAME)
    root = cmds.createNode("transform", name=SCENE_TEXT_NOTE_GROUP_NAME)
    try:
        cmds.setAttr(root + ".visibility", True)
    except Exception:
        pass
    return _long_scene_name(root)


def _migrate_scene_text_notes_to_root(note_nodes=None):
    if not MAYA_AVAILABLE or not cmds:
        return ""
    candidate_notes = []
    for node_name in note_nodes or (cmds.ls(type="transform", long=True) or []):
        if not node_name or not cmds.objExists(node_name):
            continue
        if not cmds.objExists(node_name + "." + SCENE_TEXT_NOTE_ATTR):
            continue
        try:
            if bool(cmds.getAttr(node_name + "." + SCENE_TEXT_NOTE_ATTR)):
                candidate_notes.append(node_name)
        except Exception:
            pass
    if not candidate_notes and not cmds.objExists(SCENE_TEXT_NOTE_GROUP_NAME):
        return ""
    root = _ensure_scene_text_note_root()
    root_long = _long_scene_name(root)
    for node_name in candidate_notes:
        if node_name == root_long or node_name.startswith(root_long + "|"):
            continue
        try:
            cmds.parent(node_name, root_long)
        except Exception:
            pass
    return root_long


def _hex_to_rgb(color_hex):
    color_hex = (color_hex or SCENE_TEXT_NOTE_DEFAULT_COLOR).strip()
    if color_hex.startswith("#"):
        color_hex = color_hex[1:]
    if len(color_hex) != 6:
        color_hex = SCENE_TEXT_NOTE_DEFAULT_COLOR[1:]
    try:
        return (
            int(color_hex[0:2], 16) / 255.0,
            int(color_hex[2:4], 16) / 255.0,
            int(color_hex[4:6], 16) / 255.0,
        )
    except Exception:
        return _hex_to_rgb(SCENE_TEXT_NOTE_DEFAULT_COLOR)


def _set_display_color(node_name, color_hex):
    red, green, blue = _hex_to_rgb(color_hex)
    nodes = [node_name] + (cmds.listRelatives(node_name, allDescendents=True, fullPath=True) or [])
    for item in nodes:
        if not cmds.objExists(item):
            continue
        for attr_name, value in (
            ("overrideEnabled", True),
            ("overrideRGBColors", True),
            ("overrideColorRGB", (red, green, blue)),
        ):
            if not cmds.objExists(item + "." + attr_name):
                continue
            try:
                if isinstance(value, tuple):
                    cmds.setAttr(item + "." + attr_name, value[0], value[1], value[2], type="double3")
                else:
                    cmds.setAttr(item + "." + attr_name, value)
            except Exception:
                pass


def _force_scene_text_note_visible(node_name):
    nodes = [node_name] + (cmds.listRelatives(node_name, allDescendents=True, fullPath=True) or [])
    for item in nodes:
        if not cmds.objExists(item):
            continue
        if cmds.objExists(item + ".visibility"):
            try:
                cmds.setAttr(item + ".visibility", True)
            except Exception:
                pass
        if cmds.objExists(item + ".intermediateObject"):
            try:
                cmds.setAttr(item + ".intermediateObject", False)
            except Exception:
                pass


def _top_level_nodes_from_nodes(nodes):
    long_nodes = []
    for node_name in nodes or []:
        try:
            matches = cmds.ls(node_name, long=True) or []
            long_nodes.extend(matches)
        except Exception:
            pass
    unique_nodes = _dedupe_preserve_order(long_nodes)
    unique_lookup = set(unique_nodes)
    top_nodes = []
    for node_name in unique_nodes:
        parent_nodes = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
        if parent_nodes and parent_nodes[0] in unique_lookup:
            continue
        top_nodes.append(node_name)
    return top_nodes


def _clamp_scene_text_note_size(size):
    try:
        size = float(size)
    except Exception:
        size = SCENE_TEXT_NOTE_DEFAULT_SCALE
    return max(SCENE_TEXT_NOTE_MIN_SCALE, min(SCENE_TEXT_NOTE_MAX_SCALE, size))


def _clamp_scene_text_note_box_size(value, fallback):
    try:
        value = float(value)
    except Exception:
        value = fallback
    return max(SCENE_TEXT_NOTE_MIN_BOX_SIZE, min(SCENE_TEXT_NOTE_MAX_BOX_SIZE, value))


def _scene_text_note_wrap_char_count(box_width, size):
    box_width = _clamp_scene_text_note_box_size(box_width, SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
    size = _clamp_scene_text_note_size(size)
    average_character_width = max(size * 0.48, 0.1)
    return max(8, min(120, int(round(box_width / average_character_width))))


def _wrapped_scene_text_note_lines(text, wrap_enabled, box_width, size):
    text = (text or "Student note").strip() or "Student note"
    if not wrap_enabled:
        return [line or " " for line in text.splitlines()] or ["Student note"]
    max_chars = _scene_text_note_wrap_char_count(box_width, size)
    wrapped_lines = []
    for paragraph in text.splitlines() or [text]:
        paragraph = paragraph.strip()
        if not paragraph:
            wrapped_lines.append(" ")
            continue
        wrapped_lines.extend(textwrap.wrap(
            paragraph,
            width=max_chars,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [paragraph])
    return wrapped_lines or ["Student note"]


def _scene_text_note_text_holders(note_node):
    note_node = _long_scene_name(note_node)
    holders = []
    for child in cmds.listRelatives(note_node, children=True, type="transform", fullPath=True) or []:
        if _node_short_name(child).endswith("_TEXT_GRP"):
            holders.append(child)
    return holders


def _scene_text_note_wrap_box_control(note_node):
    note_node = _long_scene_name(note_node)
    try:
        control_node = cmds.getAttr(note_node + "." + SCENE_TEXT_NOTE_WRAP_BOX_CONTROL_ATTR) or ""
    except Exception:
        control_node = ""
    if control_node and cmds.objExists(control_node):
        return _long_scene_name(control_node)
    for child in cmds.listRelatives(note_node, children=True, type="transform", fullPath=True) or []:
        if _node_short_name(child).endswith(SCENE_TEXT_NOTE_WRAP_BOX_CONTROL_SUFFIX):
            return _long_scene_name(child)
    return ""


def _set_scene_text_note_wrap_box_points(control_node, box_width, box_height):
    box_width = _clamp_scene_text_note_box_size(box_width, SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
    box_height = _clamp_scene_text_note_box_size(box_height, SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT)
    half_width = box_width * 0.5
    half_height = box_height * 0.5
    points = (
        (-half_width, -half_height, 0.0),
        (half_width, -half_height, 0.0),
        (half_width, half_height, 0.0),
        (-half_width, half_height, 0.0),
        (-half_width, -half_height, 0.0),
    )
    for index, point in enumerate(points):
        try:
            cmds.xform("{0}.cv[{1}]".format(control_node, index), objectSpace=True, translation=point)
        except Exception:
            pass


def _install_scene_text_note_wrap_box_jobs(control_node):
    if not control_node or not cmds.objExists(control_node):
        return 0
    marker = "{0}:{1}".format(SCENE_TEXT_NOTE_WRAP_BOX_JOB_MARKER, control_node)
    _kill_script_jobs_with_marker(marker)
    installed = 0
    command = (
        "import maya_timing_tools as _aminate_mtt; "
        "_aminate_mtt._sync_scene_text_note_from_wrap_box_control({0!r}) # {1}"
    ).format(control_node, marker)
    for attr_name in ("scaleX", "scaleY"):
        try:
            cmds.scriptJob(attributeChange=[control_node + "." + attr_name, command], protected=True)
            installed += 1
        except Exception:
            pass
    return installed


def _create_or_update_scene_text_note_wrap_box_control(note_node):
    note_node = _long_scene_name(note_node)
    data = _scene_text_note_data(note_node)
    box_width = _clamp_scene_text_note_box_size(data.get("box_width"), SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
    box_height = _clamp_scene_text_note_box_size(data.get("box_height"), SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT)
    control_node = _scene_text_note_wrap_box_control(note_node)
    if not control_node or not cmds.objExists(control_node):
        control_node = cmds.curve(
            name=_unique_scene_node_name(_node_base_name(note_node) + SCENE_TEXT_NOTE_WRAP_BOX_CONTROL_SUFFIX),
            degree=1,
            point=[
                (-box_width * 0.5, -box_height * 0.5, 0.0),
                (box_width * 0.5, -box_height * 0.5, 0.0),
                (box_width * 0.5, box_height * 0.5, 0.0),
                (-box_width * 0.5, box_height * 0.5, 0.0),
                (-box_width * 0.5, -box_height * 0.5, 0.0),
            ],
        )
        control_node = cmds.parent(control_node, note_node)[0]
        control_node = _long_scene_name(control_node)
    _ensure_string_attr(note_node, SCENE_TEXT_NOTE_WRAP_BOX_CONTROL_ATTR, control_node)
    _ensure_string_attr(control_node, SCENE_TEXT_NOTE_WRAP_BOX_OWNER_ATTR, note_node)
    _ensure_double_attr(control_node, SCENE_TEXT_NOTE_WRAP_BOX_BASE_WIDTH_ATTR, box_width)
    _ensure_double_attr(control_node, SCENE_TEXT_NOTE_WRAP_BOX_BASE_HEIGHT_ATTR, box_height)
    try:
        cmds.setAttr(control_node + ".scale", 1.0, 1.0, 1.0, type="double3")
    except Exception:
        pass
    _set_scene_text_note_wrap_box_points(control_node, box_width, box_height)
    try:
        cmds.setAttr(control_node + ".visibility", bool(data.get("wrap_enabled", True)))
    except Exception:
        pass
    _set_display_color(control_node, data.get("color") or SCENE_TEXT_NOTE_DEFAULT_COLOR)
    _install_scene_text_note_wrap_box_jobs(control_node)
    return control_node


def _sync_scene_text_note_from_wrap_box_control(control_node):
    if not MAYA_AVAILABLE or not cmds or not control_node or not cmds.objExists(control_node):
        return False
    control_node = _long_scene_name(control_node)
    try:
        note_node = cmds.getAttr(control_node + "." + SCENE_TEXT_NOTE_WRAP_BOX_OWNER_ATTR) or ""
    except Exception:
        note_node = ""
    if not note_node or not cmds.objExists(note_node):
        return False
    note_node = _long_scene_name(note_node)
    try:
        base_width = cmds.getAttr(control_node + "." + SCENE_TEXT_NOTE_WRAP_BOX_BASE_WIDTH_ATTR)
    except Exception:
        base_width = SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH
    try:
        base_height = cmds.getAttr(control_node + "." + SCENE_TEXT_NOTE_WRAP_BOX_BASE_HEIGHT_ATTR)
    except Exception:
        base_height = SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT
    try:
        scale_x = abs(float(cmds.getAttr(control_node + ".scaleX")))
        scale_y = abs(float(cmds.getAttr(control_node + ".scaleY")))
    except Exception:
        return False
    if abs(scale_x - 1.0) < 0.001 and abs(scale_y - 1.0) < 0.001:
        return False
    new_width = _clamp_scene_text_note_box_size(float(base_width) * max(scale_x, 0.001), SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
    new_height = _clamp_scene_text_note_box_size(float(base_height) * max(scale_y, 0.001), SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT)
    _ensure_bool_attr(note_node, SCENE_TEXT_NOTE_WRAP_ATTR, True)
    _ensure_double_attr(note_node, SCENE_TEXT_NOTE_BOX_WIDTH_ATTR, new_width)
    _ensure_double_attr(note_node, SCENE_TEXT_NOTE_BOX_HEIGHT_ATTR, new_height)
    try:
        cmds.setAttr(control_node + ".scale", 1.0, 1.0, 1.0, type="double3")
    except Exception:
        pass
    _rebuild_scene_text_note_text(note_node, update_wrap_box=False)
    _create_or_update_scene_text_note_wrap_box_control(note_node)
    return True


def _scene_text_note_line_groups(text_holder):
    return cmds.listRelatives(text_holder, children=True, type="transform", fullPath=True) or []


def _create_text_curves_for_scene_note_line(note_node, text_holder, line_text, line_index):
    line_group = cmds.createNode(
        "transform",
        name=_unique_scene_node_name(_node_base_name(note_node) + SCENE_TEXT_NOTE_LINE_GROUP_SUFFIX),
        parent=text_holder,
    )
    try:
        text_nodes = cmds.textCurves(
            name=_unique_scene_node_name(_node_base_name(note_node) + "_TEXT"),
            text=line_text,
            font="Arial",
            constructionHistory=False,
        )
    except Exception:
        text_nodes = [cmds.curve(
            name=_unique_scene_node_name(_node_base_name(note_node) + "_TEXT"),
            degree=1,
            point=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        )]
    text_roots = _top_level_nodes_from_nodes(text_nodes)
    for text_root in text_roots:
        try:
            cmds.parent(text_root, line_group, absolute=True)
        except Exception:
            pass
    try:
        cmds.setAttr(line_group + ".translate", 0.0, 0.0, 0.0, type="double3")
    except Exception:
        pass
    return line_group


def _layout_scene_text_note_line_groups(text_holder):
    line_groups = _scene_text_note_line_groups(text_holder)
    if not line_groups:
        return
    try:
        cmds.refresh(currentView=False, force=True)
    except Exception:
        pass
    raw_entries = []
    valid_heights = []
    for line_group in line_groups:
        try:
            bounds = cmds.exactWorldBoundingBox(line_group)
            measured_height = max(float(bounds[4]) - float(bounds[1]), 0.0)
        except Exception:
            measured_height = 0.0
        if measured_height >= 1.0:
            valid_heights.append(measured_height)
            raw_entries.append((line_group, measured_height))
        else:
            raw_entries.append((line_group, None))
    fallback_height = max(SCENE_TEXT_NOTE_MIN_LINE_SPACING, (sum(valid_heights) / float(len(valid_heights))) if valid_heights else 8.0)
    line_entries = [(line_group, line_height if line_height is not None else fallback_height) for line_group, line_height in raw_entries]
    tallest_height = max([fallback_height] + [entry[1] for entry in line_entries])
    spacing = max(SCENE_TEXT_NOTE_MIN_LINE_SPACING, tallest_height * 0.18)
    total_height = sum(entry[1] for entry in line_entries) + max(0, len(line_entries) - 1) * spacing
    current_top = total_height * 0.5
    for line_group, line_height in line_entries:
        line_center_y = current_top - (line_height * 0.5)
        try:
            cmds.setAttr(line_group + ".translate", 0.0, line_center_y, 0.0, type="double3")
        except Exception:
            pass
        current_top -= line_height + spacing


def _fit_scene_text_note_holder_to_box(text_holder, base_size, box_width, box_height, enabled=True):
    base_size = _clamp_scene_text_note_size(base_size)
    try:
        cmds.setAttr(text_holder + ".scale", base_size, base_size, base_size, type="double3")
    except Exception:
        pass
    if not enabled:
        return base_size
    box_width = _clamp_scene_text_note_box_size(box_width, SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
    box_height = _clamp_scene_text_note_box_size(box_height, SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT)
    try:
        bounds = cmds.exactWorldBoundingBox(text_holder)
        current_width = max(float(bounds[3]) - float(bounds[0]), 0.001)
        current_height = max(float(bounds[4]) - float(bounds[1]), 0.001)
        fit_ratio = min(1.0, box_width / current_width, box_height / current_height)
        fitted_size = max(SCENE_TEXT_NOTE_MIN_SCALE, base_size * fit_ratio)
        cmds.setAttr(text_holder + ".scale", fitted_size, fitted_size, fitted_size, type="double3")
        return fitted_size
    except Exception:
        return base_size


def _rebuild_scene_text_note_text(note_node, update_wrap_box=True):
    note_node = _long_scene_name(note_node)
    data = _scene_text_note_data(note_node)
    for holder in _scene_text_note_text_holders(note_node):
        if cmds.objExists(holder):
            try:
                cmds.delete(holder)
            except Exception:
                pass
    text_holder = cmds.createNode("transform", name=_unique_scene_node_name(_node_base_name(note_node) + "_TEXT_GRP"), parent=note_node)
    lines = _wrapped_scene_text_note_lines(
        data.get("text") or "Student note",
        bool(data.get("wrap_enabled", SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED)),
        data.get("box_width", SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH),
        data.get("size", SCENE_TEXT_NOTE_DEFAULT_SCALE),
    )
    for line_index, line_text in enumerate(lines):
        _create_text_curves_for_scene_note_line(note_node, text_holder, line_text, line_index)
    _layout_scene_text_note_line_groups(text_holder)
    _fit_scene_text_note_holder_to_box(
        text_holder,
        data.get("size", SCENE_TEXT_NOTE_DEFAULT_SCALE),
        data.get("box_width", SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH),
        data.get("box_height", SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT),
        enabled=bool(data.get("wrap_enabled", SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED)),
    )
    _set_display_color(note_node, data.get("color") or SCENE_TEXT_NOTE_DEFAULT_COLOR)
    _force_scene_text_note_visible(note_node)
    if update_wrap_box:
        _create_or_update_scene_text_note_wrap_box_control(note_node)
    return text_holder


def _apply_scene_text_note_size(note_node, size):
    note_node = _long_scene_name(note_node)
    size = _clamp_scene_text_note_size(size)
    _ensure_double_attr(note_node, SCENE_TEXT_NOTE_SIZE_ATTR, size)
    _rebuild_scene_text_note_text(note_node)
    return size


def _world_center(node_name):
    if node_name and cmds.objExists(node_name):
        try:
            box = cmds.exactWorldBoundingBox(node_name)
            return (
                (box[0] + box[3]) * 0.5,
                (box[1] + box[4]) * 0.5,
                (box[2] + box[5]) * 0.5,
            )
        except Exception:
            pass
        try:
            position = cmds.xform(node_name, query=True, worldSpace=True, translation=True)
            return (float(position[0]), float(position[1]), float(position[2]))
        except Exception:
            pass
    return (0.0, 0.0, 0.0)


def _world_transform_position(node_name):
    if node_name and cmds.objExists(node_name):
        try:
            position = cmds.xform(node_name, query=True, worldSpace=True, translation=True)
            return (float(position[0]), float(position[1]), float(position[2]))
        except Exception:
            pass
    return _world_center(node_name)


def _vector_add(a_value, b_value):
    return (
        float(a_value[0]) + float(b_value[0]),
        float(a_value[1]) + float(b_value[1]),
        float(a_value[2]) + float(b_value[2]),
    )


def _selected_scene_text_anchor(exclude_note=None):
    selected_roots = _selected_transform_roots()
    exclude_long = _long_scene_name(exclude_note) if exclude_note else ""
    for node_name in selected_roots:
        if exclude_long and _long_scene_name(node_name) == exclude_long:
            continue
        if cmds.objExists(node_name + "." + SCENE_TEXT_NOTE_ATTR):
            continue
        return _long_scene_name(node_name)
    return ""


def _scene_text_note_data(note_node):
    note_node = _long_scene_name(note_node)
    text_value = ""
    anchor_value = ""
    color_value = SCENE_TEXT_NOTE_DEFAULT_COLOR
    line_value = ""
    size_value = SCENE_TEXT_NOTE_DEFAULT_SCALE
    wrap_enabled = SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED
    box_width = SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH
    box_height = SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT
    for attr_name, fallback in (
        (SCENE_TEXT_NOTE_TEXT_ATTR, ""),
        (SCENE_TEXT_NOTE_ANCHOR_ATTR, ""),
        (SCENE_TEXT_NOTE_COLOR_ATTR, SCENE_TEXT_NOTE_DEFAULT_COLOR),
        (SCENE_TEXT_NOTE_LINE_ATTR, ""),
        (SCENE_TEXT_NOTE_SIZE_ATTR, SCENE_TEXT_NOTE_DEFAULT_SCALE),
        (SCENE_TEXT_NOTE_WRAP_ATTR, SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED),
        (SCENE_TEXT_NOTE_BOX_WIDTH_ATTR, SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH),
        (SCENE_TEXT_NOTE_BOX_HEIGHT_ATTR, SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT),
    ):
        try:
            value = cmds.getAttr(note_node + "." + attr_name)
            if value is None:
                value = fallback
        except Exception:
            value = fallback
        if attr_name == SCENE_TEXT_NOTE_TEXT_ATTR:
            text_value = value
        elif attr_name == SCENE_TEXT_NOTE_ANCHOR_ATTR:
            anchor_value = value
        elif attr_name == SCENE_TEXT_NOTE_COLOR_ATTR:
            color_value = value
        elif attr_name == SCENE_TEXT_NOTE_LINE_ATTR:
            line_value = value
        elif attr_name == SCENE_TEXT_NOTE_SIZE_ATTR:
            size_value = _clamp_scene_text_note_size(value)
        elif attr_name == SCENE_TEXT_NOTE_WRAP_ATTR:
            wrap_enabled = bool(value)
        elif attr_name == SCENE_TEXT_NOTE_BOX_WIDTH_ATTR:
            box_width = _clamp_scene_text_note_box_size(value, SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
        elif attr_name == SCENE_TEXT_NOTE_BOX_HEIGHT_ATTR:
            box_height = _clamp_scene_text_note_box_size(value, SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT)
    if not cmds.objExists(note_node + "." + SCENE_TEXT_NOTE_SIZE_ATTR):
        holders = _scene_text_note_text_holders(note_node)
        if holders and cmds.objExists(holders[0] + ".scaleX"):
            try:
                size_value = _clamp_scene_text_note_size(cmds.getAttr(holders[0] + ".scaleX"))
            except Exception:
                pass
    visible = True
    try:
        visible = bool(cmds.getAttr(note_node + ".visibility"))
    except Exception:
        pass
    return {
        "node": note_node,
        "name": _node_short_name(note_node),
        "text": text_value,
        "anchor": anchor_value,
        "color": color_value,
        "line": line_value,
        "size": size_value,
        "wrap_enabled": wrap_enabled,
        "box_width": box_width,
        "box_height": box_height,
        "box_control": _scene_text_note_wrap_box_control(note_node),
        "visible": visible,
    }


def _scene_text_note_list():
    return [_scene_text_note_data(node_name) for node_name in _scene_text_note_nodes()]


def _rebuild_scene_text_note_line(note_node):
    note_node = _long_scene_name(note_node)
    data = _scene_text_note_data(note_node)
    old_line = data.get("line")
    if old_line and cmds.objExists(old_line):
        try:
            cmds.delete(old_line)
        except Exception:
            pass
    anchor_node = data.get("anchor") or ""
    if not anchor_node or not cmds.objExists(anchor_node):
        _ensure_string_attr(note_node, SCENE_TEXT_NOTE_LINE_ATTR, "")
        return ""
    note_position = cmds.xform(note_node, query=True, worldSpace=True, translation=True)
    try:
        anchor_position = cmds.xform(anchor_node, query=True, worldSpace=True, translation=True)
    except Exception:
        anchor_position = _world_center(anchor_node)
    note_root = _ensure_scene_text_note_root()
    line_group = cmds.createNode("transform", name=_unique_scene_node_name(_node_base_name(note_node) + "_LINE_GRP"), parent=note_root)
    line_curve = cmds.curve(name=_unique_scene_node_name(_node_base_name(note_node) + "_LINE_CRV"), degree=1, point=[note_position, anchor_position])
    line_curve = cmds.parent(line_curve, line_group)[0]
    try:
        start_cluster, start_handle = cmds.cluster(line_curve + ".cv[0]", name=_unique_scene_node_name(_node_base_name(note_node) + "_LINE_START_CLS"))
        end_cluster, end_handle = cmds.cluster(line_curve + ".cv[1]", name=_unique_scene_node_name(_node_base_name(note_node) + "_LINE_END_CLS"))
        cmds.parent([start_handle, end_handle], line_group)
        cmds.pointConstraint(note_node, start_handle, maintainOffset=False)
        cmds.pointConstraint(anchor_node, end_handle, maintainOffset=False)
        for helper_node in (start_handle, end_handle):
            if cmds.objExists(helper_node + ".visibility"):
                cmds.setAttr(helper_node + ".visibility", False)
    except Exception:
        pass
    line_group = _long_scene_name(line_group)
    _set_display_color(line_curve, data.get("color") or SCENE_TEXT_NOTE_DEFAULT_COLOR)
    _ensure_string_attr(note_node, SCENE_TEXT_NOTE_LINE_ATTR, line_group)
    return line_group


def _create_scene_text_note(
    text,
    color_hex=SCENE_TEXT_NOTE_DEFAULT_COLOR,
    anchor_node=None,
    size=SCENE_TEXT_NOTE_DEFAULT_SCALE,
    wrap_enabled=SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED,
    box_width=SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH,
    box_height=SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT,
):
    text = (text or "Student note").strip() or "Student note"
    color_hex = color_hex or SCENE_TEXT_NOTE_DEFAULT_COLOR
    size = _clamp_scene_text_note_size(size)
    box_width = _clamp_scene_text_note_box_size(box_width, SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
    box_height = _clamp_scene_text_note_box_size(box_height, SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT)
    anchor_node = _long_scene_name(anchor_node) if anchor_node else _selected_scene_text_anchor()
    anchor_position = _world_transform_position(anchor_node) if anchor_node else (0.0, 0.0, 0.0)
    note_position = _vector_add(anchor_position, SCENE_TEXT_NOTE_OFFSET)
    base_name = _safe_scene_node_name("{0}_{1}".format(SCENE_TEXT_NOTE_ROOT_PREFIX, text[:24]), SCENE_TEXT_NOTE_ROOT_PREFIX)
    note_group = cmds.group(empty=True, name=_unique_scene_node_name(base_name + "_GRP"))
    note_root = _ensure_scene_text_note_root()
    note_group = cmds.parent(note_group, note_root)[0]
    note_group = _long_scene_name(note_group)
    cmds.xform(note_group, worldSpace=True, translation=note_position)
    _ensure_bool_attr(note_group, SCENE_TEXT_NOTE_ATTR, True)
    _ensure_string_attr(note_group, SCENE_TEXT_NOTE_TEXT_ATTR, text)
    _ensure_string_attr(note_group, SCENE_TEXT_NOTE_ANCHOR_ATTR, anchor_node or "")
    _ensure_string_attr(note_group, SCENE_TEXT_NOTE_COLOR_ATTR, color_hex)
    _ensure_string_attr(note_group, SCENE_TEXT_NOTE_LINE_ATTR, "")
    _ensure_double_attr(note_group, SCENE_TEXT_NOTE_SIZE_ATTR, size)
    _ensure_bool_attr(note_group, SCENE_TEXT_NOTE_WRAP_ATTR, bool(wrap_enabled))
    _ensure_double_attr(note_group, SCENE_TEXT_NOTE_BOX_WIDTH_ATTR, box_width)
    _ensure_double_attr(note_group, SCENE_TEXT_NOTE_BOX_HEIGHT_ATTR, box_height)
    _rebuild_scene_text_note_text(note_group)
    _force_scene_text_note_visible(note_group)
    _set_display_color(note_group, color_hex)
    line_node = _rebuild_scene_text_note_line(note_group)
    try:
        cmds.select(note_group, replace=True)
    except Exception:
        pass
    return {
        "node": _long_scene_name(note_group),
        "text": text,
        "anchor": anchor_node or "",
        "color": color_hex,
        "line": line_node,
        "size": size,
        "wrap_enabled": bool(wrap_enabled),
        "box_width": box_width,
        "box_height": box_height,
        "box_control": _scene_text_note_wrap_box_control(note_group),
    }

_CYCLORAMA_POINTS = [
    (-336.44533901151135, 0.0, 173.6245593460942),
    (336.44533901151135, 0.0, 173.6245593460942),
    (-336.44533901151135, 415.02265454619277, -471.9410829452879),
    (336.44533901151135, 415.02265454619277, -471.9410829452879),
    (336.44533901151135, 415.02265454619277, -560.9881722280204),
    (-336.44533901151135, 415.02265454619277, -560.9881722280204),
    (-336.44533901151135, 0.0, -229.97837667726787),
    (-336.44533901151135, 3.195199236504672, -261.5608473856972),
    (-336.44533901151135, 12.72612560197932, -292.6029351690814),
    (-336.44533901151135, 28.429703910997215, -322.5734976907079),
    (-336.44533901151135, 50.03723998579082, -350.9597312510704),
    (-336.44533901151135, 77.17902629888164, -377.2759391242581),
    (-336.44533901151135, 109.39065100844118, -401.07184348011873),
    (-336.44533901151135, 146.12097833523038, -421.94029691294486),
    (-336.44533901151135, 186.74152334475124, -439.52422368116714),
    (-336.44533901151135, 230.55727299265646, -453.5227618622041),
    (-336.44533901151135, 276.8185212830406, -463.6963933331772),
    (-336.44533901151135, 324.73371853961305, -469.8710529387356),
    (-336.44533901151135, 373.4830466895025, -471.9410829452879),
    (336.44533901151135, 373.4830466895025, -471.9410829452879),
    (336.44533901151135, 324.73371853961305, -469.8710529387356),
    (336.44533901151135, 276.8185212830406, -463.6963933331772),
    (336.44533901151135, 230.55727299265646, -453.5227618622041),
    (336.44533901151135, 186.74152334475124, -439.52422368116714),
    (336.44533901151135, 146.12097833523038, -421.94029691294486),
    (336.44533901151135, 109.39065100844118, -401.07184348011873),
    (336.44533901151135, 77.17902629888164, -377.2759391242581),
    (336.44533901151135, 50.03723998579082, -350.9597312510704),
    (336.44533901151135, 28.429703910997215, -322.5734976907079),
    (336.44533901151135, 12.72612560197932, -292.6029351690814),
    (336.44533901151135, 3.195199236504672, -261.5608473856972),
    (336.44533901151135, 0.0, -229.97837667726787),
]
_CYCLORAMA_FACE_COUNTS = [4] * 15
_CYCLORAMA_FACE_CONNECTS = [
    2, 3, 4, 5,
    0, 1, 31, 6,
    18, 19, 3, 2,
    18, 17, 20, 19,
    17, 16, 21, 20,
    16, 15, 22, 21,
    15, 14, 23, 22,
    14, 13, 24, 23,
    13, 12, 25, 24,
    12, 11, 26, 25,
    11, 10, 27, 26,
    10, 9, 28, 27,
    9, 8, 29, 28,
    8, 7, 30, 29,
    7, 6, 31, 30,
]
SCENE_HELPERS_CAMERA_HEIGHT_OFFSET_OPTION = "AmirAminateSceneHelpersCameraHeightOffset"
SCENE_HELPERS_CAMERA_DOLLY_OFFSET_OPTION = "AmirAminateSceneHelpersCameraDollyOffset"
SCENE_HELPERS_CAMERA_NAMES = {
    "front": "amirSceneFront_cam",
    "side": "amirSceneSide_cam",
    "three_quarter": "amirSceneThreeQuarter_cam",
}
SCENE_HELPERS_CAMERA_PRESET_LABELS = {
    "perspective": "Perspective",
    "front": "Front",
    "side": "Side",
    "three_quarter": "Three Quarter",
}
SCENE_HELPERS_BOOKMARK_NAMES = {
    "front": "Scene Helpers - Front",
    "side": "Scene Helpers - Side",
    "three_quarter": "Scene Helpers - Three Quarter",
}
SCENE_HELPERS_CAMERA_MAP_ATTR = "sceneHelpersCameraMap"
SCENE_HELPERS_LIGHTS_ATTR = "sceneHelpersLights"
SCENE_HELPERS_LIGHT_MODE_ATTR = "sceneHelpersLightMode"
SCENE_HELPERS_CAMERA_HEIGHT_OFFSET_ATTR = "sceneHelpersCameraHeightOffset"
SCENE_HELPERS_CAMERA_DOLLY_OFFSET_ATTR = "sceneHelpersCameraDollyOffset"
SCENE_HELPERS_CAMERA_DISTANCE_ATTR = "sceneHelpersCameraDistance"
SCENE_HELPERS_HEIGHT_SPAN_ATTR = "sceneHelpersHeightSpan"
FOLLOW_AMIR_URL = hold_utils.FOLLOW_AMIR_URL
DEFAULT_DONATE_URL = hold_utils.DEFAULT_DONATE_URL
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
STUDENT_CORE_TEMP_POPUP_OBJECT = "studentCoreTimelineTempButtons"
STUDENT_CORE_TOOLS = (
    {
        "command": "nudge_left",
        "label": "-1",
        "group": "Timing",
        "color": "#EF6F6C",
        "glyph": "toolkit_nudge_left",
        "tooltip": "Move selected Graph Editor keys, or all keys on selected controls, one frame earlier.",
    },
    {
        "command": "nudge_right",
        "label": "+1",
        "group": "Timing",
        "color": "#55CBCD",
        "glyph": "toolkit_nudge_right",
        "tooltip": "Move selected Graph Editor keys, or all keys on selected controls, one frame later.",
    },
    {
        "command": "insert_inbetween",
        "label": "In",
        "group": "Keys",
        "color": "#F6C85F",
        "glyph": "toolkit_insert_inbetween",
        "tooltip": "Insert an inbetween key on the current frame for selected animated controls.",
    },
    {
        "command": "tween_machine",
        "label": "Tween",
        "group": "Keys",
        "color": "#4CC9F0",
        "glyph": "toolkit_tween_machine",
        "tooltip": "Open Tween Machine: create a current-frame key as a percentage between the previous and next keys.",
    },
    {
        "command": "remove_current",
        "label": "Cut",
        "group": "Keys",
        "color": "#B86BFF",
        "glyph": "toolkit_cut_key",
        "tooltip": "Remove keys on the current frame for selected animated controls.",
    },
    {
        "command": "reset_pose",
        "label": "Zero",
        "group": "Pose",
        "color": "#7BD88F",
        "glyph": "toolkit_reset_pose",
        "tooltip": "Reset selected controls to translate 0, rotate 0, scale 1.",
    },
    {
        "command": "bake_twos",
        "label": "2s",
        "group": "Bake",
        "color": "#72B7F2",
        "glyph": "toolkit_bake_twos",
        "tooltip": "Bake selected controls over the playback range every 2 frames.",
    },
    {
        "command": "select_animated",
        "label": "Anim",
        "group": "Select",
        "color": "#95E6E8",
        "glyph": "toolkit_select_animated",
        "tooltip": "Select every transform in the scene with animation curves.",
    },
    {
        "command": "clean_static",
        "label": "Clean",
        "group": "Clean",
        "color": "#B9E769",
        "glyph": "toolkit_clean_static",
        "tooltip": "Delete static animation curves on selected controls when every keyed value is the same.",
    },
    {
        "command": "combine_freeze_pivot",
        "label": "CFP",
        "group": "Mesh",
        "color": "#55CBCD",
        "glyph": "combine_freeze_pivot",
        "tooltip": "Combine selected mesh transforms into one mesh, freeze transforms, then enter Edit Pivot mode.",
    },
    {
        "command": "package_scene_zip",
        "label": "Zip",
        "group": "Package",
        "color": "#F4A261",
        "glyph": "toolkit_package_zip",
        "tooltip": "One click: save the scene, zip the scene plus references, textures, image planes, audio, and caches, then open the package folder.",
    },
    {
        "command": "playblast_1080p",
        "label": "PB",
        "group": "Review",
        "color": "#FF7A59",
        "glyph": "playblast",
        "tooltip": "Playblast the playback range to your C:\\Users\\<you>\\Documents folder as a 1920x1080, 100% AVI movie.",
    },
)
WORKFLOW_BAR_TOOLS = maya_aminate_icon_manifest.workflow_toolbar_tools()


def _central_action_toolbar_tools():
    """Hydrate legacy action metadata from the shared icon manifest.

    Keep command names and historical groups intact so button callbacks stay
    unchanged while accents, icons, hover copy, and accessibility labels have
    one source of truth.
    """
    legacy_groups = dict(
        (str(tool.get("command") or ""), tool.get("group") or "Action")
        for tool in STUDENT_CORE_TOOLS
    )
    hydrated = []
    for entry in maya_aminate_icon_manifest.action_toolbar_tools():
        item = dict(entry)
        command = str(item.get("command") or "")
        if command == "game_animation_mode":
            continue
        item["group"] = legacy_groups.get(command, "Action")
        item["color"] = item.get("accent") or "#56D7E8"
        item["glyph"] = item.get("id") or command
        item["tooltip"] = "{0}: {1} {2}".format(
            item.get("display_name") or command,
            item.get("purpose") or "Use this Aminate action.",
            item.get("help") or "",
        ).strip()
        item["accessible_name"] = item.get("accessible_label") or item.get("display_name") or command
        item["accessible_description"] = "{0} {1}".format(
            item.get("purpose") or "",
            item.get("help") or "",
        ).strip()
        hydrated.append(item)
    return tuple(hydrated)


# Compatibility shape retained for existing callers. Values now come from
# ACTION_ICON_MANIFEST, so bottom-bar action visuals and help cannot drift.
STUDENT_CORE_TOOLS = _central_action_toolbar_tools()
TOOLKIT_BAR_SIMPLE_HELP = {
    "nudge_left": "Move the selected keys one frame earlier.",
    "nudge_right": "Move the selected keys one frame later.",
    "insert_inbetween": "Add a new pose key on this frame.",
    "tween_machine": "Blend this pose between the key before and the key after.",
    "remove_current": "Remove keys on the frame you are standing on.",
    "reset_pose": "Put the selected controls back to their normal pose.",
    "bake_twos": "Make a stepped animation key every two frames.",
    "select_animated": "Find all controls that already have animation.",
    "clean_static": "Remove keys that do not change anything.",
    "combine_freeze_pivot": "Join selected meshes, freeze them, then edit the pivot.",
    "package_scene_zip": "Collect this scene and its files into one zip.",
    "playblast_1080p": "Playblast this shot to Documents at 1080p full scale.",
    "export_selected_animation_fbx": "Export selected animation with the visible playback range.",
    "workflow_quick_start": "Open the beginner guide for choosing the right Aminate tool.",
    "workflow_scene_helpers": "Open the helper tools for safer scene setup.",
    "workflow_reference_manager": "Open the packager for scene files and references.",
    "workflow_dynamic_parenting": "Open the tool for switching what a prop follows.",
    "workflow_hand_foot_hold": "Open the tool that keeps hands or feet planted.",
    "workflow_surface_contact": "Open the tool that sticks controls to a surface.",
    "workflow_dynamic_pivot": "Open the tool for rotating around a temporary point.",
    "workflow_ikfk": "Open the IK/FK switch helper.",
    "workflow_retarget": "Open the tool for copying animation to another rig.",
    "workflow_picker": "Open the control picker for selecting rig parts.",
    "workflow_pencil": "Open drawing tools for notes and animation arcs.",
    "workflow_history": "Open saved scene snapshots so you can jump back.",
    "workflow_onion": "Open pose ghosts for checking spacing.",
    "workflow_rotation": "Open rotation checks for flips and gimbal problems.",
    "workflow_skin": "Open skinning cleanup tools.",
    "workflow_rig_scale": "Open the rig scale helper for game export sizes.",
    "workflow_video": "Open video and image reference cards.",
    "workflow_timeline": "Open timeline notes for colored shot comments.",
    "toolkitBarDragGrip": "Restore safe bottom docking without floating the Maya workspace.",
    "studentTimelineBarAnimationLayerTint": "Choose which animation layer you are working on.",
    "toolkitBarAnimationLayerAddButton": "Make a new animation layer.",
    "toolkitBarAnimationLayerDeleteButton": "Delete the current animation layer.",
    "toolkitBarAnimationLayerAddSelectedButton": "Put selected controls on this layer.",
    "toolkitBarAnimationLayerRemoveSelectedButton": "Take selected controls off this layer.",
    "toolkitBarAnimationLayerMuteButton": "Turn this layer off without deleting it.",
    "toolkitBarAnimationLayerSoloButton": "Show only this layer's animation.",
    "toolkitBarAnimationLayerLockButton": "Lock this layer so it cannot be changed by accident.",
    "toolkitBarGameAnimationModeButton": "Switch Maya into fast game-animation settings.",
}
TOOLKIT_BAR_KID_HELP = {
    "nudge_left": "Scoot selected keys one tiny step back in time.",
    "nudge_right": "Scoot selected keys one tiny step forward in time.",
    "insert_inbetween": "Make a new middle pose right where the timeline is.",
    "tween_machine": "Mix the pose before and after, like a pose slider.",
    "remove_current": "Erase keys from this exact frame.",
    "reset_pose": "Put picked controls back to their starting pose.",
    "bake_twos": "Make chunky cartoon timing with keys every two frames.",
    "select_animated": "Find the controls that already move.",
    "clean_static": "Throw away keys that do nothing.",
    "combine_freeze_pivot": "Glue picked meshes together, clean transforms, then move the pivot.",
    "package_scene_zip": "Pack scene files into one zip folder.",
    "playblast_1080p": "Make a full-size 1080p movie in Documents.",
    "export_selected_animation_fbx": "Send picked animation to an FBX using the visible range.",
    "workflow_quick_start": "Open the beginner map for Aminate.",
    "workflow_scene_helpers": "Open helpers for clean Maya scene setup.",
    "workflow_reference_manager": "Open the file packer.",
    "workflow_dynamic_parenting": "Choose what a prop follows over time.",
    "workflow_hand_foot_hold": "Keep a hand or foot stuck in place.",
    "workflow_surface_contact": "Keep a control touching a surface.",
    "workflow_dynamic_pivot": "Spin something around a temporary point.",
    "workflow_ikfk": "Switch arms or legs between IK and FK.",
    "workflow_retarget": "Copy animation from one rig to another.",
    "workflow_picker": "Pick rig body parts from a friendly panel.",
    "workflow_pencil": "Draw notes and arcs in the scene.",
    "workflow_history": "Jump between saved scene moments.",
    "workflow_onion": "Show ghost poses before and after this frame.",
    "workflow_rotation": "Find rotation flips before they cause trouble.",
    "workflow_skin": "Clean skinning problems.",
    "workflow_rig_scale": "Make rig size right for game export.",
    "workflow_video": "Put reference images or video in Maya.",
    "workflow_timeline": "Put colored notes on the timeline.",
    "toolkitBarDragGrip": "Click to make sure the bar stays docked at the bottom.",
    "studentTimelineBarAnimationLayerTint": "Pick which animation layer gets your keys.",
    "toolkitBarAnimationLayerAddButton": "Make a fresh animation layer.",
    "toolkitBarAnimationLayerDeleteButton": "Remove this animation layer.",
    "toolkitBarAnimationLayerAddSelectedButton": "Add picked controls to this layer.",
    "toolkitBarAnimationLayerRemoveSelectedButton": "Remove picked controls from this layer.",
    "toolkitBarAnimationLayerMuteButton": "Hide this layer's motion for now.",
    "toolkitBarAnimationLayerSoloButton": "Listen to only this layer.",
    "toolkitBarAnimationLayerLockButton": "Protect this layer from accidental edits.",
    "toolkitBarGameAnimationModeButton": "Turn on fast game-animation scene settings.",
}
TOOLKIT_BAR_HELP_TITLES = {
    "nudge_left": "Nudge Left",
    "nudge_right": "Nudge Right",
    "insert_inbetween": "Insert Inbetween",
    "tween_machine": "Tween Machine",
    "remove_current": "Cut Current Key",
    "reset_pose": "Reset Pose",
    "bake_twos": "Bake On Twos",
    "select_animated": "Select Animated",
    "clean_static": "Clean Static Keys",
    "combine_freeze_pivot": "Combine Freeze Pivot",
    "package_scene_zip": "Package Scene",
    "playblast_1080p": "Playblast 1080p AVI",
    "export_selected_animation_fbx": "Export Selected Animation FBX",
    "toolkitBarDragGrip": "Move Toolkit Bar",
    "studentTimelineBarAnimationLayerTint": "Animation Layer",
    "toolkitBarAnimationLayerAddButton": "New Layer",
    "toolkitBarAnimationLayerDeleteButton": "Delete Layer",
    "toolkitBarAnimationLayerAddSelectedButton": "Add Selection",
    "toolkitBarAnimationLayerRemoveSelectedButton": "Remove Selection",
    "toolkitBarAnimationLayerMuteButton": "Mute Layer",
    "toolkitBarAnimationLayerSoloButton": "Solo Layer",
    "toolkitBarAnimationLayerLockButton": "Lock Layer",
    "toolkitBarGameAnimationModeButton": "Game Animation Mode",
}

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None
GLOBAL_TIMELINE_BAR_CONTROLLER = None
GLOBAL_TIMELINE_BAR_WINDOW = None
GLOBAL_TIMELINE_BAR_HOST = None
GLOBAL_TIMELINE_BAR_WIDGETS = []
CURRENT_WORKFLOW_TAB_ALIAS = "quick_start"

_qt_flag = hold_utils._qt_flag
_style_donate_button = hold_utils._style_donate_button
_open_external_url = hold_utils._open_external_url
_maya_main_window = hold_utils._maya_main_window


def _register_timeline_bar_widget(widget):
    if widget is not None and widget not in GLOBAL_TIMELINE_BAR_WIDGETS:
        GLOBAL_TIMELINE_BAR_WIDGETS.append(widget)


def _sync_timeline_bar_game_buttons(controller):
    enabled = bool(getattr(controller, "game_animation_mode_enabled", False))
    for widget in list(GLOBAL_TIMELINE_BAR_WIDGETS):
        try:
            if widget is None:
                GLOBAL_TIMELINE_BAR_WIDGETS.remove(widget)
                continue
            setter = getattr(widget, "_set_game_button_checked", None)
            if setter:
                setter(enabled)
        except Exception:
            try:
                GLOBAL_TIMELINE_BAR_WIDGETS.remove(widget)
            except Exception:
                pass
    for window in (GLOBAL_WINDOW,):
        if window is not None and hasattr(window, "game_mode_button"):
            try:
                window.game_mode_button.blockSignals(True)
                window.game_mode_button.setChecked(enabled)
                window.game_mode_button.blockSignals(False)
                _set_game_mode_button_glow(window.game_mode_button, enabled)
            except Exception:
                pass


def hide_aminate_toolbar_extras():
    hidden = 0
    if _TWEEN_MACHINE_POPUP is not None:
        try:
            if _TWEEN_MACHINE_POPUP.isVisible():
                hidden += 1
        except Exception:
            pass
        try:
            _TWEEN_MACHINE_POPUP.hide()
        except Exception:
            pass
    for widget in list(GLOBAL_TIMELINE_BAR_WIDGETS):
        if widget is None:
            continue
        try:
            if not getattr(widget, "embedded", False):
                if widget.isVisible():
                    hidden += 1
                widget.hide()
        except Exception:
            pass
    # Legacy native Toolkit Bar workspaces remain visible.  Maya 2026 can
    # fault when retained workspace visibility changes during Aminate hide.
    try:
        hidden += int(maya_floating_channel_box.hide_floating_channel_box_and_graph_editor() or 0)
    except Exception:
        pass
    return hidden


def _tool_button_popup_mode(member_name):
    if not QtWidgets:
        return 2
    if hasattr(QtWidgets.QToolButton, member_name):
        return getattr(QtWidgets.QToolButton, member_name)
    scoped_enum = getattr(QtWidgets.QToolButton, "ToolButtonPopupMode", None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return getattr(QtWidgets.QToolButton, "InstantPopup", 2)


def _dedupe_preserve_order(values):
    seen = set()
    ordered = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def _short_name(node_name):
    return (node_name or "").split("|")[-1]


def _is_base_animation_layer(layer_name):
    label = _short_name(layer_name).lower()
    compact = "".join(char for char in label if char.isalnum())
    return compact in ("baseanimation", "baseanim")


def _base_animation_layer_name(layers=None):
    for layer_name in layers or (cmds.ls(type="animLayer") if cmds else []) or []:
        if _is_base_animation_layer(layer_name):
            return layer_name
    return ""


def _animation_layer_label(layer_name):
    return "Base Animation" if _is_base_animation_layer(layer_name) else _short_name(layer_name)


def _stable_palette_color(name):
    label = _animation_layer_label(name) or "Base Animation"
    total = sum(ord(char) for char in label)
    return ANIMATION_LAYER_TINT_PALETTE[total % len(ANIMATION_LAYER_TINT_PALETTE)]


def _next_animation_layer_palette_color(layer_name):
    current_color = _normalize_hex_color(_animation_layer_color(layer_name), _stable_palette_color(layer_name))
    palette = [_normalize_hex_color(color) for color in ANIMATION_LAYER_TINT_PALETTE]
    try:
        current_index = palette.index(current_color)
    except ValueError:
        current_index = sum(ord(char) for char in _animation_layer_label(layer_name)) % len(palette)
    return palette[(current_index + 1) % len(palette)]


def _normalize_hex_color(value, fallback="#4A4A4A"):
    text = str(value or "").strip()
    if not text:
        return fallback
    if not text.startswith("#"):
        text = "#" + text
    if len(text) != 7:
        return fallback
    try:
        int(text[1:], 16)
    except Exception:
        return fallback
    return text.upper()


def _hex_to_rgb01(color_hex):
    color_hex = _normalize_hex_color(color_hex)
    return (
        int(color_hex[1:3], 16) / 255.0,
        int(color_hex[3:5], 16) / 255.0,
        int(color_hex[5:7], 16) / 255.0,
    )


def _maya_color_index_from_hex(color_hex):
    target = _hex_to_rgb01(color_hex)
    best_index = 0
    best_distance = 999.0
    for index in range(32):
        maya_hex = _maya_color_index_to_hex(index)
        if not maya_hex:
            continue
        candidate = _hex_to_rgb01(maya_hex)
        distance = sum((candidate[channel] - target[channel]) ** 2 for channel in range(3))
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index


def _maya_color_index_to_hex(index_value):
    maya_colors = (
        "#9B9B9B", "#000000", "#3F3F3F", "#666666", "#A6A6A6", "#600000", "#000060", "#004060",
        "#006000", "#600060", "#402000", "#602000", "#404000", "#204000", "#004020", "#004040",
        "#002040", "#400040", "#600040", "#400000", "#604000", "#606000", "#406000", "#006020",
        "#006060", "#004060", "#000060", "#402060", "#602060", "#600020", "#FF0000", "#00FF00",
    )
    try:
        index = int(index_value)
    except Exception:
        return ""
    if index < 0:
        return ""
    return maya_colors[index % len(maya_colors)]


def _animation_layer_color(layer_name):
    if not cmds or not layer_name or not cmds.objExists(layer_name):
        return _stable_palette_color(layer_name)
    try:
        if cmds.attributeQuery(ANIMATION_LAYER_CUSTOM_COLOR_ATTR, node=layer_name, exists=True):
            custom_color = cmds.getAttr("{0}.{1}".format(layer_name, ANIMATION_LAYER_CUSTOM_COLOR_ATTR))
            if custom_color:
                return _normalize_hex_color(custom_color, _stable_palette_color(layer_name))
    except Exception:
        pass
    for attr_name in ("color", "displayColor", "ghostColor"):
        try:
            if not cmds.attributeQuery(attr_name, node=layer_name, exists=True):
                continue
            value = cmds.getAttr("{0}.{1}".format(layer_name, attr_name))
            if isinstance(value, (list, tuple)):
                if value and isinstance(value[0], (list, tuple)) and len(value[0]) >= 3:
                    r_value, g_value, b_value = value[0][:3]
                    return "#{0:02X}{1:02X}{2:02X}".format(
                        max(0, min(255, int(float(r_value) * 255.0))),
                        max(0, min(255, int(float(g_value) * 255.0))),
                        max(0, min(255, int(float(b_value) * 255.0))),
                    )
                if len(value) >= 3:
                    return "#{0:02X}{1:02X}{2:02X}".format(
                        max(0, min(255, int(float(value[0]) * 255.0))),
                        max(0, min(255, int(float(value[1]) * 255.0))),
                        max(0, min(255, int(float(value[2]) * 255.0))),
                    )
            color_hex = _maya_color_index_to_hex(value)
            if color_hex:
                return color_hex
        except Exception:
            continue
    return _stable_palette_color(layer_name)


def _animation_layer_names(include_base=False):
    if not cmds:
        return []
    try:
        layers = cmds.ls(type="animLayer") or []
    except Exception:
        layers = []
    ordered = []
    for layer_name in layers:
        if not layer_name:
            continue
        if _is_base_animation_layer(layer_name) and not include_base:
            continue
        if layer_name not in ordered:
            ordered.append(layer_name)
    if include_base and not _base_animation_layer_name(ordered):
        ordered.insert(0, "")
    return ordered


def _set_animation_layer_selected(layer_name):
    if not cmds:
        return False, "This tool only works inside Maya."
    target_layer = layer_name or _base_animation_layer_name()
    if not target_layer:
        for other_layer in _animation_layer_names(include_base=True):
            if other_layer:
                for flag_name in ("selected", "preferred"):
                    try:
                        cmds.animLayer(other_layer, edit=True, **{flag_name: False})
                    except Exception:
                        continue
        return True, "Animation layer changed to Base Animation."
    if target_layer and not cmds.objExists(target_layer):
        return False, "Animation layer no longer exists: {0}".format(layer_name)
    changed = False
    for other_layer in _animation_layer_names(include_base=True):
        for flag_name in ("selected", "preferred"):
            try:
                cmds.animLayer(other_layer, edit=True, **{flag_name: bool(other_layer == target_layer)})
                changed = True
            except Exception:
                continue
    if target_layer:
        return True, "Animation layer changed to {0}.".format(_animation_layer_label(target_layer))
    return True, "Animation layer changed to Base Animation."


def _rename_animation_layer(layer_name, new_name):
    if not cmds:
        return False, "This tool only works inside Maya.", layer_name
    if not layer_name or not cmds.objExists(layer_name):
        return False, "Pick an animation layer before renaming.", layer_name
    if _is_base_animation_layer(layer_name):
        return False, "Base Animation cannot be renamed.", layer_name
    cleaned = str(new_name or "").strip()
    if not cleaned:
        return False, "Type a new animation layer name.", layer_name
    try:
        renamed = cmds.rename(layer_name, cleaned)
    except Exception as exc:
        return False, "Could not rename animation layer: {0}".format(exc), layer_name
    return True, "Renamed animation layer to {0}.".format(_short_name(renamed)), renamed


def _set_animation_layer_color(layer_name, color_hex):
    if not cmds:
        return False, "This tool only works inside Maya."
    if not layer_name or not cmds.objExists(layer_name):
        return False, "Pick an animation layer before setting color."
    if _is_base_animation_layer(layer_name):
        return False, "Base Animation uses Maya's default layer color."
    color_hex = _normalize_hex_color(color_hex, _stable_palette_color(layer_name))
    try:
        if not cmds.attributeQuery(ANIMATION_LAYER_CUSTOM_COLOR_ATTR, node=layer_name, exists=True):
            cmds.addAttr(layer_name, longName=ANIMATION_LAYER_CUSTOM_COLOR_ATTR, dataType="string")
        cmds.setAttr("{0}.{1}".format(layer_name, ANIMATION_LAYER_CUSTOM_COLOR_ATTR), color_hex, type="string")
    except Exception:
        pass
    r_value, g_value, b_value = _hex_to_rgb01(color_hex)
    color_index = _maya_color_index_from_hex(color_hex)
    for attr_name in ("color", "displayColor", "ghostColor"):
        try:
            if not cmds.attributeQuery(attr_name, node=layer_name, exists=True):
                continue
            attr_type = cmds.getAttr("{0}.{1}".format(layer_name, attr_name), type=True)
            plug = "{0}.{1}".format(layer_name, attr_name)
            if attr_type in ("double3", "float3"):
                cmds.setAttr(plug, r_value, g_value, b_value, type=attr_type)
            else:
                cmds.setAttr(plug, color_index)
        except Exception:
            continue
    return True, "Changed {0} color to {1}.".format(_short_name(layer_name), color_hex)


def _unique_animation_layer_name(base_name="AnimLayer"):
    if not cmds:
        return base_name
    safe_base = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(base_name or "AnimLayer")).strip("_") or "AnimLayer"
    if not cmds.objExists(safe_base):
        return safe_base
    index = 1
    while cmds.objExists("{0}{1}".format(safe_base, index)):
        index += 1
    return "{0}{1}".format(safe_base, index)


def _create_animation_layer(name=None, add_selected=True):
    if not cmds:
        return False, "This tool only works inside Maya.", ""
    layer_name = _unique_animation_layer_name(name or "AnimLayer")
    try:
        created_layer = cmds.animLayer(layer_name)
        if add_selected and cmds.ls(selection=True):
            try:
                cmds.animLayer(created_layer, edit=True, addSelectedObjects=True)
            except Exception:
                pass
        _set_animation_layer_selected(created_layer)
    except Exception as exc:
        return False, "Could not create animation layer: {0}".format(exc), ""
    return True, "Created animation layer {0}.".format(_short_name(created_layer)), created_layer


def _duplicate_animation_layer(layer_name, name=None):
    if not cmds:
        return False, "This tool only works inside Maya.", ""
    if not layer_name or not cmds.objExists(layer_name):
        return False, "Pick an animation layer before copying.", ""
    if _is_base_animation_layer(layer_name):
        return False, "Base Animation cannot be copied with this button.", ""
    created_layer = ""
    try:
        created_layer = cmds.animLayer(_unique_animation_layer_name(name or "{0}_copy".format(_short_name(layer_name))))
        cmds.animLayer(created_layer, edit=True, copy=layer_name)
        _set_animation_layer_selected(created_layer)
    except Exception as exc:
        if created_layer and cmds.objExists(created_layer):
            try:
                cmds.delete(created_layer)
            except Exception:
                pass
        return False, "Could not copy animation layer: {0}".format(exc), ""
    return True, "Copied {0} to {1}.".format(_short_name(layer_name), _short_name(created_layer)), created_layer


def _animation_layer_key_times(layer_names):
    times = []
    for layer_name in layer_names:
        try:
            curves = cmds.animLayer(layer_name, query=True, animCurves=True) or []
            times.extend(cmds.keyframe(curves, query=True, timeChange=True) or [])
        except Exception:
            continue
    result = set()
    for value in times:
        try:
            result.add(float(value))
        except (TypeError, ValueError):
            continue
    return sorted(result)


def _consolidate_other_animation_layers(current_layer, name=None):
    if not cmds:
        return False, "This tool only works inside Maya.", ""
    source_layers = [
        layer_name for layer_name in _animation_layer_names(include_base=False)
        if layer_name != current_layer
    ]
    if not source_layers:
        return False, "No other animation layers exist to consolidate.", ""
    attributes = _dedupe_preserve_order(
        attribute
        for layer_name in source_layers
        for attribute in (cmds.animLayer(layer_name, query=True, attribute=True) or [])
    )
    key_times = _animation_layer_key_times(source_layers)
    if not attributes or not key_times:
        return False, "Other animation layers contain no keyed attributes.", ""

    created_layer = ""
    tracked_layers = list(source_layers)
    if current_layer and cmds.objExists(current_layer):
        tracked_layers.append(current_layer)
    original_states = {layer_name: _animation_layer_state(layer_name) for layer_name in tracked_layers}
    try:
        created_layer = cmds.animLayer(_unique_animation_layer_name(name or "OtherLayers_merged"))
        for attribute in attributes:
            cmds.animLayer(created_layer, edit=True, attribute=attribute)
        for source_layer in source_layers:
            cmds.animLayer(source_layer, edit=True, mute=False, solo=False, lock=False)
        if current_layer and cmds.objExists(current_layer) and not _is_base_animation_layer(current_layer):
            cmds.animLayer(current_layer, edit=True, mute=True, solo=False, lock=False)
        # Evaluate the combined source layers only at their original key times.
        # ``bakeResults(sampleBy=1)`` would invent a key on every whole frame,
        # including between fractional keys, and makes the review layer harder
        # to edit.  The destination layer is addressed explicitly so the
        # selected layer cannot change where the keys land.
        _set_animation_layer_selected(created_layer)
        original_time = float(cmds.currentTime(query=True))
        try:
            for time_value in key_times:
                cmds.currentTime(time_value, edit=True, update=True)
                for attribute in attributes:
                    cmds.setKeyframe(attribute, time=time_value, animLayer=created_layer)
        finally:
            cmds.currentTime(original_time, edit=True, update=True)
        cmds.animLayer(created_layer, edit=True, mute=True)
        _set_animation_layer_selected(created_layer)
    except Exception as exc:
        if created_layer and cmds.objExists(created_layer):
            try:
                cmds.delete(created_layer)
            except Exception:
                pass
        return False, "Could not consolidate animation layers: {0}".format(exc), ""
    finally:
        for layer_name, state in original_states.items():
            if not cmds.objExists(layer_name):
                continue
            for flag_name in ("mute", "solo", "lock"):
                try:
                    cmds.animLayer(layer_name, edit=True, **{flag_name: bool(state.get(flag_name))})
                except Exception:
                    pass
    return True, "Consolidated {0} other layers into muted layer {1}.".format(len(source_layers), _short_name(created_layer)), created_layer


def _clear_animation_layer_solos():
    if not cmds:
        return False, "This tool only works inside Maya."
    changed = 0
    for layer_name in _animation_layer_names(include_base=False):
        try:
            if cmds.animLayer(layer_name, query=True, solo=True):
                cmds.animLayer(layer_name, edit=True, solo=False)
                changed += 1
        except Exception:
            continue
    return True, "Cleared solo on {0} animation layer{1}.".format(changed, "" if changed == 1 else "s")


def _delete_animation_layer(layer_name):
    if not cmds:
        return False, "This tool only works inside Maya."
    if not layer_name or not cmds.objExists(layer_name):
        return False, "Pick an animation layer before deleting."
    if _is_base_animation_layer(layer_name):
        return False, "Base Animation cannot be deleted."
    try:
        cmds.delete(layer_name)
    except Exception as exc:
        return False, "Could not delete animation layer: {0}".format(exc)
    return True, "Deleted animation layer {0}.".format(_short_name(layer_name))


def _animation_layer_state(layer_name):
    state = {"can_edit": bool(layer_name and cmds and cmds.objExists(layer_name) and not _is_base_animation_layer(layer_name)), "mute": False, "solo": False, "lock": False, "weight": 1.0}
    if not state["can_edit"]:
        return state
    for flag_name in ("mute", "solo", "lock"):
        try:
            state[flag_name] = bool(cmds.animLayer(layer_name, query=True, **{flag_name: True}))
        except Exception:
            state[flag_name] = False
    try:
        state["weight"] = float(cmds.animLayer(layer_name, query=True, weight=True))
    except Exception:
        state["weight"] = 1.0
    return state


def _set_animation_layer_flag(layer_name, flag_name, enabled):
    if not cmds:
        return False, "This tool only works inside Maya."
    if flag_name not in ("mute", "solo", "lock"):
        return False, "Unknown animation layer flag: {0}".format(flag_name)
    if not layer_name or not cmds.objExists(layer_name):
        return False, "Pick an animation layer before changing {0}.".format(flag_name)
    if _is_base_animation_layer(layer_name):
        return False, "Base Animation cannot change {0}.".format(flag_name)
    try:
        cmds.animLayer(layer_name, edit=True, **{flag_name: bool(enabled)})
    except Exception as exc:
        return False, "Could not change {0}: {1}".format(flag_name, exc)
    return True, "Set {0} {1} to {2}.".format(_short_name(layer_name), flag_name, "on" if enabled else "off")


def _set_animation_layer_weight(layer_name, weight):
    if not cmds:
        return False, "This tool only works inside Maya."
    if not layer_name or not cmds.objExists(layer_name):
        return False, "Pick an animation layer before setting weight."
    if _is_base_animation_layer(layer_name):
        return False, "Base Animation weight cannot be changed."
    try:
        clamped = max(0.0, min(1.0, float(weight)))
        cmds.animLayer(layer_name, edit=True, weight=clamped)
    except Exception as exc:
        return False, "Could not set animation layer weight: {0}".format(exc)
    return True, "Set {0} weight to {1:.2f}.".format(_short_name(layer_name), clamped)


def _edit_selected_objects_on_animation_layer(layer_name, add=True):
    if not cmds:
        return False, "This tool only works inside Maya."
    if not layer_name or not cmds.objExists(layer_name):
        return False, "Pick an animation layer first."
    if _is_base_animation_layer(layer_name):
        return False, "Base Animation membership is controlled by Maya."
    if not cmds.ls(selection=True):
        return False, "Select controls before changing layer membership."
    flag_name = "addSelectedObjects" if add else "removeSelectedObjects"
    try:
        cmds.animLayer(layer_name, edit=True, **{flag_name: True})
    except Exception as exc:
        return False, "Could not update selected controls on layer: {0}".format(exc)
    verb = "Added selected controls to" if add else "Removed selected controls from"
    return True, "{0} {1}.".format(verb, _short_name(layer_name))


def _animation_layer_is_selected(layer_name):
    if not cmds or not layer_name or not cmds.objExists(layer_name):
        return False
    for flag_name in ("selected", "preferred"):
        try:
            if cmds.animLayer(layer_name, query=True, **{flag_name: True}):
                return True
        except Exception:
            continue
    return False


def _active_animation_layer_name():
    if not cmds:
        return ""
    try:
        layers = cmds.ls(type="animLayer") or []
    except Exception:
        layers = []
    if not layers:
        return ""
    for layer_name in layers:
        if _animation_layer_is_selected(layer_name):
            return layer_name
    for layer_name in layers:
        if not _is_base_animation_layer(layer_name):
            return layer_name
    return _base_animation_layer_name(layers)


def _option_var_bool(option_name, default):
    if not cmds or not cmds.optionVar(exists=option_name):
        return bool(default)
    try:
        return bool(cmds.optionVar(query=option_name))
    except Exception:
        return bool(default)


def _save_option_var_bool(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(intValue=(option_name, int(bool(value))))
    except Exception:
        pass


def _game_animation_mode_action_option_name(action_key):
    return "{0}_{1}".format(GAME_ANIMATION_MODE_ACTION_OPTION_PREFIX, action_key)


def _game_animation_mode_action_settings():
    return collections.OrderedDict(
        (key, _option_var_bool(_game_animation_mode_action_option_name(key), True))
        for key in GAME_ANIMATION_MODE_ACTIONS
    )


def _prompt_game_mode_auto_history(parent=None):
    if not QtWidgets:
        return True
    answer = QtWidgets.QMessageBox.question(
        parent,
        GAME_MODE_AUTO_HISTORY_PROMPT_TITLE,
        GAME_MODE_AUTO_HISTORY_PROMPT_TEXT,
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.Yes,
    )
    return answer == QtWidgets.QMessageBox.Yes


def _option_var_float(option_name, default):
    if not cmds or not cmds.optionVar(exists=option_name):
        return float(default)
    try:
        return float(cmds.optionVar(query=option_name))
    except Exception:
        return float(default)


def _save_option_var_float(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(floatValue=(option_name, float(value)))
    except Exception:
        pass


def _option_var_string(option_name, default):
    if not cmds or not cmds.optionVar(exists=option_name):
        return default
    try:
        value = cmds.optionVar(query=option_name)
        return value if value else default
    except Exception:
        return default


def _save_option_var_string(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(stringValue=(option_name, value or ""))
    except Exception:
        pass


def _clamp_float(value, minimum, maximum, default):
    try:
        value = float(value)
    except Exception:
        value = float(default)
    return max(float(minimum), min(float(maximum), value))


def _clamp_int(value, minimum, maximum, default):
    try:
        value = int(round(float(value)))
    except Exception:
        value = int(default)
    return max(int(minimum), min(int(maximum), value))


def toolkit_hover_settings():
    wording_mode = str(_option_var_string(TOOLKIT_HOVER_WORDING_MODE_OPTION, DEFAULT_TOOLKIT_HOVER_WORDING_MODE) or DEFAULT_TOOLKIT_HOVER_WORDING_MODE).strip().lower()
    if wording_mode not in TOOLKIT_HOVER_WORDING_MODES:
        wording_mode = DEFAULT_TOOLKIT_HOVER_WORDING_MODE
    return {
        "icon_pixels": _clamp_int(_option_var_float(TOOLKIT_HOVER_ICON_PIXELS_OPTION, DEFAULT_TOOLKIT_HOVER_ICON_PIXELS), 40, 96, DEFAULT_TOOLKIT_HOVER_ICON_PIXELS),
        "opacity": _clamp_float(_option_var_float(TOOLKIT_HOVER_OPACITY_OPTION, DEFAULT_TOOLKIT_HOVER_OPACITY), 0.50, 1.0, DEFAULT_TOOLKIT_HOVER_OPACITY),
        "wording_mode": wording_mode,
    }


def set_toolkit_hover_settings(icon_pixels=None, opacity=None, wording_mode=None):
    current = toolkit_hover_settings()
    if icon_pixels is not None:
        current["icon_pixels"] = _clamp_int(icon_pixels, 40, 96, DEFAULT_TOOLKIT_HOVER_ICON_PIXELS)
        _save_option_var_float(TOOLKIT_HOVER_ICON_PIXELS_OPTION, current["icon_pixels"])
    if opacity is not None:
        current["opacity"] = _clamp_float(opacity, 0.50, 1.0, DEFAULT_TOOLKIT_HOVER_OPACITY)
        _save_option_var_float(TOOLKIT_HOVER_OPACITY_OPTION, current["opacity"])
    if wording_mode is not None:
        wording_mode = str(wording_mode or DEFAULT_TOOLKIT_HOVER_WORDING_MODE).strip().lower()
        if wording_mode not in TOOLKIT_HOVER_WORDING_MODES:
            wording_mode = DEFAULT_TOOLKIT_HOVER_WORDING_MODE
        current["wording_mode"] = wording_mode
        _save_option_var_string(TOOLKIT_HOVER_WORDING_MODE_OPTION, wording_mode)
    refresh_toolkit_hover_cards()
    return toolkit_hover_settings()


def reset_toolkit_hover_settings():
    return set_toolkit_hover_settings(
        icon_pixels=DEFAULT_TOOLKIT_HOVER_ICON_PIXELS,
        opacity=DEFAULT_TOOLKIT_HOVER_OPACITY,
        wording_mode=DEFAULT_TOOLKIT_HOVER_WORDING_MODE,
    )


def _current_time_unit():
    if not cmds:
        return DEFAULT_TIME_UNIT
    try:
        return cmds.currentUnit(query=True, time=True) or DEFAULT_TIME_UNIT
    except Exception:
        return DEFAULT_TIME_UNIT


def _current_auto_key_state():
    if not cmds:
        return False
    try:
        return bool(cmds.autoKeyframe(query=True, state=True))
    except Exception:
        return False


def _current_time_unit_is_game_fps():
    return _current_time_unit() in ("ntsc", "30fps", "ntscf", "60fps")


def _maya_main_qt_window():
    if not (QtWidgets and omui and shiboken):
        return None
    try:
        pointer = omui.MQtUtil.mainWindow()
    except Exception:
        pointer = None
    if not pointer:
        return None
    try:
        return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)
    except Exception:
        return None


def _warning_toast_allowed(kind, now=None):
    if kind not in _WARNING_TOAST_LAST_SHOWN:
        return False
    now = time.time() if now is None else float(now)
    if now - float(_WARNING_TOAST_LAST_SHOWN.get(kind) or 0.0) < AUTO_KEY_WARNING_TOAST_THROTTLE_SECONDS:
        return False
    _WARNING_TOAST_LAST_SHOWN[kind] = now
    return True


def _auto_key_warning_allowed(now=None):
    if _current_auto_key_state():
        return False
    return _warning_toast_allowed("auto_key", now=now)


def _queue_warning_toast(message, kind, duration_ms):
    global _WARNING_TOAST_QUEUE
    if not message or not kind:
        return
    _WARNING_TOAST_QUEUE.append(
        {
            "message": message,
            "kind": kind,
            "duration_ms": int(max(1, duration_ms)),
        }
    )


def _dequeue_warning_toast():
    global _WARNING_TOAST_QUEUE
    if not _WARNING_TOAST_QUEUE:
        return None
    item = _WARNING_TOAST_QUEUE[0]
    _WARNING_TOAST_QUEUE = _WARNING_TOAST_QUEUE[1:]
    return item


def _warning_toast_anchor_widget():
    if not (QtWidgets and omui and shiboken and cmds):
        return _maya_main_qt_window()
    panel_name = ""
    try:
        panel_name = cmds.getPanel(withFocus=True) or ""
    except Exception:
        panel_name = ""
    panel_names = []
    if panel_name:
        panel_names.append(panel_name)
    try:
        panel_names.extend(cmds.getPanel(type="modelPanel") or [])
    except Exception:
        pass
    for panel_name in _dedupe_preserve_order(panel_names):
        if not panel_name:
            continue
        try:
            if cmds.getPanel(typeOf=panel_name) != "modelPanel":
                continue
        except Exception:
            continue
        pointer = None
        for finder in (omui.MQtUtil.findControl, omui.MQtUtil.findLayout):
            try:
                pointer = finder(panel_name)
            except Exception:
                pointer = None
            if pointer:
                break
        if not pointer:
            continue
        try:
            widget = shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)
        except Exception:
            widget = None
        if widget is not None:
            return widget
    return _maya_main_qt_window()


def _auto_key_warning_callback(_curve_objects=None, _client_data=None):
    now = time.time()
    if MAYA_AVAILABLE and cmds and not _current_auto_key_state() and _warning_toast_allowed("auto_key", now=now):
        _queue_warning_toast(AUTO_KEY_WARNING_TOAST_MESSAGE, "auto_key", AUTO_KEY_WARNING_TOAST_DURATION_MS)
    if (
        MAYA_AVAILABLE
        and cmds
        and not _current_time_unit_is_game_fps()
        and "fps_game" not in _WARNING_TOAST_SESSION_SHOWN
        and _warning_toast_allowed("fps_game", now=now)
    ):
        _queue_warning_toast(
            GAME_ANIMATION_FPS_WARNING_TOAST_MESSAGE,
            "fps_game",
            GAME_ANIMATION_FPS_WARNING_TOAST_DURATION_MS,
        )
        _WARNING_TOAST_SESSION_SHOWN.add("fps_game")
    if not _WARNING_TOAST_QUEUE and _WARNING_TOAST_ACTIVE is None:
        return
    if not (QtCore and QtWidgets):
        item = _dequeue_warning_toast()
        if item:
            try:
                om2.MGlobal.displayWarning(item.get("message") or AUTO_KEY_WARNING_TOAST_MESSAGE)
            except Exception:
                pass
        return
    try:
        QtCore.QTimer.singleShot(0, _show_next_warning_toast)
    except Exception:
        item = _dequeue_warning_toast()
        if item:
            try:
                om2.MGlobal.displayWarning(item.get("message") or AUTO_KEY_WARNING_TOAST_MESSAGE)
            except Exception:
                pass


def _install_auto_key_warning_callback():
    global _AUTO_KEY_WARNING_CALLBACK_ID, _WARNING_TOAST_QUEUE, _WARNING_TOAST_ACTIVE
    if not MAYA_AVAILABLE or not oma2 or _AUTO_KEY_WARNING_CALLBACK_ID is not None:
        return _AUTO_KEY_WARNING_CALLBACK_ID
    _WARNING_TOAST_QUEUE = []
    _WARNING_TOAST_ACTIVE = None
    _WARNING_TOAST_SESSION_SHOWN.clear()
    for key_name in _WARNING_TOAST_LAST_SHOWN:
        _WARNING_TOAST_LAST_SHOWN[key_name] = 0.0
    try:
        _AUTO_KEY_WARNING_CALLBACK_ID = oma2.MAnimMessage.addAnimKeyframeEditedCallback(_auto_key_warning_callback)
    except Exception:
        _AUTO_KEY_WARNING_CALLBACK_ID = None
    return _AUTO_KEY_WARNING_CALLBACK_ID


def _remove_auto_key_warning_callback():
    global _AUTO_KEY_WARNING_CALLBACK_ID, _WARNING_TOAST_QUEUE, _WARNING_TOAST_ACTIVE
    if _AUTO_KEY_WARNING_CALLBACK_ID is None:
        return
    try:
        if om2:
            om2.MMessage.removeCallback(_AUTO_KEY_WARNING_CALLBACK_ID)
    except Exception:
        pass
    _AUTO_KEY_WARNING_CALLBACK_ID = None
    _WARNING_TOAST_QUEUE = []
    _WARNING_TOAST_ACTIVE = None
    _WARNING_TOAST_SESSION_SHOWN.clear()
    for key_name in _WARNING_TOAST_LAST_SHOWN:
        _WARNING_TOAST_LAST_SHOWN[key_name] = 0.0


if QtWidgets:
    class _AutoKeyWarningToast(QtWidgets.QFrame):
        def __init__(self, parent=None):
            super(_AutoKeyWarningToast, self).__init__(parent)
            self.setObjectName("aminateAutoKeyWarningToast")
            self._hide_timer = QtCore.QTimer(self)
            self._hide_timer.setSingleShot(True)
            self._hide_timer.timeout.connect(self._animate_out)
            self._current_item = None
            self._animations = []
            flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            self.setWindowOpacity(0.96)
            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(18, 12, 18, 12)
            self.label = QtWidgets.QLabel(AUTO_KEY_WARNING_TOAST_MESSAGE)
            self.label.setWordWrap(True)
            self.label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(self.label)
            self.setStyleSheet(
                """
                QFrame#aminateAutoKeyWarningToast {
                    background-color: rgba(18, 22, 28, 235);
                    color: #F8FAFC;
                    border: 1px solid #4CC9F0;
                    border-radius: 10px;
                }
                QLabel {
                    color: #F8FAFC;
                    font-weight: 700;
                    font-size: 13px;
                }
                """
            )

        def _anchor_global_rect(self):
            anchor = _warning_toast_anchor_widget()
            if anchor is not None:
                try:
                    top_left = anchor.mapToGlobal(QtCore.QPoint(0, 0))
                    return QtCore.QRect(top_left.x(), top_left.y(), max(anchor.width(), 1), max(anchor.height(), 1))
                except Exception:
                    pass
            screen = None
            try:
                cursor_pos = QtGui.QCursor.pos()
                screen = QtWidgets.QApplication.screenAt(cursor_pos)
            except Exception:
                screen = None
            if screen is None:
                try:
                    screen = QtWidgets.QApplication.primaryScreen()
                except Exception:
                    screen = None
            if screen:
                return screen.availableGeometry()
            return QtCore.QRect(0, 0, 1280, 720)

        def show_toast(self, message, duration_ms=AUTO_KEY_WARNING_TOAST_DURATION_MS, kind=""):
            self._current_item = {
                "message": message or AUTO_KEY_WARNING_TOAST_MESSAGE,
                "duration_ms": int(max(1, duration_ms)),
                "kind": kind or "",
            }
            self.label.setText(self._current_item["message"])
            self.setWindowOpacity(0.96)
            self.adjustSize()
            width = max(420, min(620, self.sizeHint().width()))
            height = max(54, self.sizeHint().height())
            self.resize(width, height)
            rect = self._anchor_global_rect()
            x_pos = rect.left() + (rect.width() - width) // 2
            y_pos = rect.bottom() - height - 18
            self.move(x_pos, y_pos)
            self.show()
            try:
                self.raise_()
            except Exception:
                pass
            self._hide_timer.start(self._current_item["duration_ms"])

        def _animate_out(self):
            global _WARNING_TOAST_ACTIVE
            rect = self._anchor_global_rect()
            start_pos = self.pos()
            end_pos = QtCore.QPoint(start_pos.x(), rect.bottom() + 10)
            move_anim = QtCore.QPropertyAnimation(self, b"pos", self)
            move_anim.setDuration(420)
            move_anim.setStartValue(start_pos)
            move_anim.setEndValue(end_pos)
            move_anim.setEasingCurve(QtCore.QEasingCurve.InCubic)
            fade_anim = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
            fade_anim.setDuration(320)
            fade_anim.setStartValue(float(self.windowOpacity()))
            fade_anim.setEndValue(0.0)
            group = QtCore.QParallelAnimationGroup(self)
            group.addAnimation(move_anim)
            group.addAnimation(fade_anim)
            item = dict(self._current_item or {})
            _WARNING_TOAST_ACTIVE = item or None
            group.finished.connect(self.hide)
            group.finished.connect(self._toast_finished)
            self._animations = [group, move_anim, fade_anim]
            group.start(QtCore.QAbstractAnimation.DeleteWhenStopped)

        def _toast_finished(self):
            global _WARNING_TOAST_ACTIVE
            _WARNING_TOAST_ACTIVE = None
            self._current_item = None
            try:
                QtCore.QTimer.singleShot(0, _show_next_warning_toast)
            except Exception:
                pass


def _show_next_warning_toast():
    global _WARNING_TOAST_ACTIVE
    if _WARNING_TOAST_ACTIVE is not None:
        return False
    item = _dequeue_warning_toast()
    if not item:
        return False
    return _show_auto_key_warning_toast(
        message=item.get("message"),
        duration_ms=item.get("duration_ms", AUTO_KEY_WARNING_TOAST_DURATION_MS),
        kind=item.get("kind", ""),
    )


def _show_auto_key_warning_toast(message=None, duration_ms=AUTO_KEY_WARNING_TOAST_DURATION_MS, kind=""):
    global _AUTO_KEY_WARNING_TOAST, _WARNING_TOAST_ACTIVE
    if not (QtCore and QtWidgets):
        return False
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    parent = _maya_main_qt_window()
    if _AUTO_KEY_WARNING_TOAST is None:
        _AUTO_KEY_WARNING_TOAST = _AutoKeyWarningToast(parent)
    _WARNING_TOAST_ACTIVE = {
        "message": message or AUTO_KEY_WARNING_TOAST_MESSAGE,
        "duration_ms": int(max(1, duration_ms)),
        "kind": kind or "",
    }
    _AUTO_KEY_WARNING_TOAST.show_toast(
        _WARNING_TOAST_ACTIVE["message"],
        duration_ms=_WARNING_TOAST_ACTIVE["duration_ms"],
        kind=_WARNING_TOAST_ACTIVE["kind"],
    )
    return True


def _scene_anim_curves():
    if not cmds:
        return []
    curves = []
    for curve_type in ANIM_CURVE_TYPES:
        try:
            curves.extend(cmds.ls(type=curve_type) or [])
        except Exception:
            continue
    return _dedupe_preserve_order(curves)


def _convert_anim_curves_to_weighted_tangents(curves=None):
    if not cmds:
        return 0
    curve_names = _dedupe_preserve_order(curves or _scene_anim_curves())
    try:
        cmds.keyTangent(global_=True, edit=True, weightedTangents=True)
    except Exception:
        try:
            cmds.keyTangent(g=True, edit=True, weightedTangents=True)
        except Exception:
            pass
    converted = 0
    try:
        cmds.undoInfo(openChunk=True, chunkName="AminateGameModeWeightedTangents")
    except Exception:
        pass
    try:
        for curve_name in curve_names:
            if not curve_name or not cmds.objExists(curve_name):
                continue
            try:
                cmds.keyTangent(curve_name, edit=True, weightedTangents=True)
                converted += 1
            except Exception:
                continue
    finally:
        try:
            cmds.undoInfo(closeChunk=True)
        except Exception:
            pass
    return converted


def _scene_texture_node_specs():
    specs = [("file", "fileTextureName")]
    if cmds:
        try:
            if "aiImage" in (cmds.allNodeTypes() or []):
                specs.append(("aiImage", "filename"))
        except Exception:
            pass
    return tuple(specs)


def _workspace_sourceimages_root():
    if not cmds:
        return ""
    workspace_root = cmds.workspace(query=True, rootDirectory=True) or ""
    if not workspace_root:
        return ""
    try:
        source_rule = cmds.workspace(fileRuleEntry="sourceImages") or ""
    except Exception:
        source_rule = ""
    if source_rule:
        if os.path.isabs(source_rule):
            return os.path.normpath(source_rule)
        return os.path.normpath(os.path.join(workspace_root, source_rule))
    return os.path.normpath(os.path.join(workspace_root, "sourceimages"))


def _texture_search_roots():
    if not cmds:
        return []
    roots = []
    workspace_root = cmds.workspace(query=True, rootDirectory=True) or ""
    scene_name = cmds.file(query=True, sceneName=True) or ""
    scene_dir = os.path.dirname(scene_name) if scene_name else ""
    sourceimages_root = _workspace_sourceimages_root()
    for root_path in (
        sourceimages_root,
        workspace_root,
        scene_dir,
        os.path.join(workspace_root, "textures") if workspace_root else "",
        os.path.join(workspace_root, "images") if workspace_root else "",
        os.path.join(scene_dir, "textures") if scene_dir else "",
        os.path.join(scene_dir, "images") if scene_dir else "",
    ):
        if not root_path:
            continue
        normalized = os.path.normpath(root_path)
        if os.path.isdir(normalized) and normalized not in roots:
            roots.append(normalized)
    return roots


def _build_texture_basename_index(search_roots):
    basename_map = collections.defaultdict(list)
    indexed_files = 0
    deadline = time.perf_counter() + TEXTURE_BASENAME_INDEX_SECONDS_LIMIT
    for root_path in search_roots or []:
        try:
            for current_root, dir_names, file_names in os.walk(root_path):
                dir_names[:] = [name for name in dir_names if not name.startswith(".")]
                for file_name in file_names:
                    if indexed_files >= TEXTURE_BASENAME_INDEX_FILE_LIMIT or time.perf_counter() >= deadline:
                        return dict(basename_map)
                    key_name = file_name.lower()
                    full_path = os.path.normpath(os.path.join(current_root, file_name))
                    basename_map[key_name].append(full_path)
                    indexed_files += 1
        except Exception:
            continue
    return dict(basename_map)


def _texture_refresh_mel_hooks(node_name):
    if not mel or not node_name:
        return
    safe_node_name = node_name.replace("\\", "\\\\").replace('"', '\\"')
    if cmds and cmds.objExists(node_name):
        try:
            mel.eval(
                'if (`exists updateFileNodeSwatch`) {{ catchQuiet(`updateFileNodeSwatch "{0}"`); }}'.format(
                    safe_node_name
                )
            )
        except Exception:
            pass
    try:
        mel.eval('if (`exists generateAllUvTilePreviews`) { catchQuiet(`generateAllUvTilePreviews`); }')
    except Exception:
        pass


def _refresh_texture_node(node_name, attr_name, texture_path):
    if not cmds or not node_name or not attr_name or not texture_path:
        return False
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return False
    try:
        if cmds.attributeQuery("disableFileLoad", node=node_name, exists=True):
            cmds.setAttr(node_name + ".disableFileLoad", 0)
    except Exception:
        pass
    try:
        cmds.setAttr(node_name + "." + attr_name, texture_path, type="string")
    except Exception:
        return False
    try:
        cmds.dgdirty(node_name)
    except Exception:
        pass
    _texture_refresh_mel_hooks(node_name)
    return True


def _resolve_texture_path(current_path, basename_map, search_roots):
    normalized_path = os.path.normpath(current_path) if current_path else ""
    if normalized_path and os.path.exists(normalized_path):
        return normalized_path, False
    base_name = os.path.basename(current_path or "").strip()
    if not base_name:
        return "", False
    key_name = base_name.lower()
    matches = list(basename_map.get(key_name) or [])
    if len(matches) == 1:
        return matches[0], True
    direct_candidates = []
    for root_path in search_roots or []:
        for subfolder in ("", "sourceimages", "textures", "images", os.path.join("sourceimages", "textures")):
            candidate = os.path.normpath(os.path.join(root_path, subfolder, base_name))
            if os.path.exists(candidate):
                direct_candidates.append(candidate)
    direct_candidates = _dedupe_preserve_order(direct_candidates)
    if len(direct_candidates) == 1:
        return direct_candidates[0], True
    return "", False


def _selected_transform_nodes():
    if not cmds:
        return []
    selected = cmds.ls(selection=True, long=True) or []
    transforms = []
    for node_name in selected:
        if not node_name or not cmds.objExists(node_name):
            continue
        try:
            if cmds.nodeType(node_name) == "transform":
                transforms.append(node_name)
                continue
        except Exception:
            pass
        try:
            parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
        except Exception:
            parents = []
        for parent_name in parents:
            if parent_name and cmds.objExists(parent_name):
                try:
                    if cmds.nodeType(parent_name) == "transform":
                        transforms.append(parent_name)
                except Exception:
                    continue
    return _dedupe_preserve_order(transforms)


def _mesh_shapes_under_transform(transform_name):
    if not cmds or not transform_name or not cmds.objExists(transform_name):
        return []
    try:
        shapes = cmds.listRelatives(transform_name, shapes=True, fullPath=True, noIntermediate=True) or []
    except TypeError:
        shapes = cmds.listRelatives(transform_name, shapes=True, fullPath=True) or []
    except Exception:
        shapes = []
    mesh_shapes = []
    for shape_name in shapes:
        try:
            if cmds.nodeType(shape_name) == "mesh" and not bool(cmds.getAttr(shape_name + ".intermediateObject")):
                mesh_shapes.append(shape_name)
        except Exception:
            continue
    return mesh_shapes


def _selected_mesh_transform_nodes():
    if not cmds:
        return []
    mesh_transforms = []
    for node_name in cmds.ls(selection=True, long=True) or []:
        if not node_name or not cmds.objExists(node_name):
            continue
        transform_name = ""
        try:
            node_type = cmds.nodeType(node_name)
        except Exception:
            node_type = ""
        if node_type == "transform":
            transform_name = node_name
        elif node_type == "mesh":
            parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
            transform_name = parents[0] if parents else ""
        if transform_name and _mesh_shapes_under_transform(transform_name):
            mesh_transforms.append(transform_name)
    return _dedupe_preserve_order(mesh_transforms)


def _scene_keyed_transforms():
    if not cmds:
        return []
    try:
        anim_curves = cmds.ls(type="animCurve") or []
    except Exception:
        anim_curves = []
    if not anim_curves:
        return []
    try:
        destinations = cmds.listConnections(anim_curves, source=False, destination=True, plugs=True) or []
    except Exception:
        destinations = []
    nodes = []
    seen = set()
    for plug_name in destinations:
        node_name = (plug_name or "").split(".", 1)[0]
        if not node_name or node_name in seen:
            continue
        seen.add(node_name)
        try:
            if cmds.nodeType(node_name) == "transform":
                nodes.append(node_name)
                continue
        except Exception:
            pass
        try:
            parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
        except Exception:
            parents = []
        for parent_name in parents:
            if not parent_name or parent_name in seen:
                continue
            seen.add(parent_name)
            try:
                if cmds.nodeType(parent_name) == "transform":
                    nodes.append(parent_name)
            except Exception:
                continue
    return _dedupe_preserve_order(nodes)


def _settable_keyable_attrs(node_name):
    attrs = set(cmds.listAttr(node_name, keyable=True) or [])
    attrs.update(cmds.listAttr(node_name, channelBox=True) or [])
    settable_attrs = []
    for attr_name in sorted(attrs):
        plug = "{0}.{1}".format(node_name, attr_name)
        try:
            if cmds.objExists(plug) and not cmds.getAttr(plug, lock=True) and cmds.getAttr(plug, settable=True):
                settable_attrs.append(attr_name)
        except Exception:
            continue
    return settable_attrs


def _all_model_panels():
    if not cmds:
        return []
    try:
        return cmds.getPanel(type="modelPanel") or []
    except Exception:
        return []


def _scene_helpers_perspective_camera():
    if not cmds:
        return "persp"
    for camera_name in ("persp", "perspShape"):
        try:
            if cmds.objExists(camera_name):
                return camera_name
        except Exception:
            pass
    try:
        for panel_name in _all_model_panels():
            try:
                camera_name = cmds.modelEditor(panel_name, query=True, camera=True) or ""
            except Exception:
                camera_name = ""
            if _short_name(camera_name).lower().startswith("persp"):
                return camera_name
    except Exception:
        pass
    return "persp"


def _snap_curve_times(node_name, attr_name):
    times = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
    if not times:
        return 0
    unique_times = sorted({float(time_value) for time_value in times})
    if not unique_times:
        return 0

    if len(unique_times) == 1:
        snapped_times = [int(round(unique_times[0]))]
    else:
        start_time = unique_times[0]
        end_time = unique_times[-1]
        start_frame = int(round(start_time))
        total_span = float(end_time - start_time)
        target_span = max(1, int(round(end_time - start_time)), len(unique_times) - 1)
        snapped_times = []
        previous_time = None
        for time_value in unique_times:
            if total_span <= 1.0e-8:
                candidate_time = start_frame
            else:
                normalized = (time_value - start_time) / total_span
                candidate_time = int(round(start_frame + normalized * float(target_span)))
            if previous_time is not None and candidate_time <= previous_time:
                candidate_time = previous_time + 1
            snapped_times.append(candidate_time)
            previous_time = candidate_time

    changed = 0
    for old_time, new_time in zip(unique_times, snapped_times):
        delta = float(new_time) - float(old_time)
        if abs(delta) <= 1.0e-8:
            continue
        cmds.keyframe(
            node_name,
            attribute=attr_name,
            edit=True,
            time=(float(old_time), float(old_time)),
            relative=True,
            timeChange=delta,
        )
        changed += 1
    return changed


def _retime_curve_times(node_name, attr_name, step):
    times = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
    unique_times = sorted({float(value) for value in times}, reverse=True)
    changed = 0
    for old_time in unique_times:
        new_time = float(int(round(old_time / float(step))) * int(step))
        delta = new_time - old_time
        if abs(delta) <= 1.0e-8:
            continue
        cmds.keyframe(node_name, attribute=attr_name, edit=True, time=(old_time, old_time), relative=True, timeChange=delta)
        changed += 1
    return changed


def _make_snap_icon():
    if not QtGui:
        return QtGui.QIcon() if QtGui else None
    pixmap = QtGui.QPixmap(24, 24)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        frame_pen = QtGui.QPen(QtGui.QColor("#2F80ED"))
        frame_pen.setWidth(2)
        painter.setPen(frame_pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(4, 4, 16, 16, 2, 2)
        painter.drawLine(4, 12, 20, 12)
        painter.drawLine(12, 4, 12, 20)
        arrow_pen = QtGui.QPen(QtGui.QColor("#EAF2FF"))
        arrow_pen.setWidth(2)
        painter.setPen(arrow_pen)
        painter.drawLine(7, 7, 17, 17)
        painter.drawLine(17, 17, 14, 17)
        painter.drawLine(17, 17, 17, 14)
    finally:
        painter.end()
    return QtGui.QIcon(pixmap)


def _make_key_icon():
    if not QtGui:
        return QtGui.QIcon() if QtGui else None
    pixmap = QtGui.QPixmap(24, 24)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        outline_pen = QtGui.QPen(QtGui.QColor("#D4A017"))
        outline_pen.setWidth(2)
        painter.setPen(outline_pen)
        painter.setBrush(QtGui.QColor("#F5D76E"))
        painter.drawEllipse(4, 7, 7, 7)
        painter.drawRect(10, 9, 10, 3)
        painter.drawRect(16, 7, 2, 7)
        painter.drawRect(18, 7, 2, 5)
    finally:
        painter.end()
    return QtGui.QIcon(pixmap)


def _make_student_core_icon(color_hex, glyph):
    if not QtGui:
        return QtGui.QIcon() if QtGui else None
    if glyph in STUDENT_CORE_ICON_FILES:
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), STUDENT_CORE_ICON_FILES[glyph])
        if os.path.exists(icon_path):
            custom_pixmap = QtGui.QPixmap(icon_path)
            if not custom_pixmap.isNull():
                return QtGui.QIcon(custom_pixmap)
    pixmap = QtGui.QPixmap(30, 30)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        color = QtGui.QColor(color_hex or "#55CBCD")
        darker = QtGui.QColor(color).darker(145)
        light = QtGui.QColor("#F1F3F4")
        painter.setPen(QtGui.QPen(darker, 2))
        painter.setBrush(color)
        painter.drawRoundedRect(4, 4, 22, 22, 5, 5)
        painter.setPen(QtGui.QPen(QtGui.QColor("#2C2C2C"), 2))
        painter.setBrush(QtGui.QColor("#2C2C2C"))
        if glyph == "left":
            points = [QtCore.QPoint(18, 9), QtCore.QPoint(10, 15), QtCore.QPoint(18, 21)]
            painter.drawPolygon(QtGui.QPolygon(points))
        elif glyph == "right":
            points = [QtCore.QPoint(12, 9), QtCore.QPoint(20, 15), QtCore.QPoint(12, 21)]
            painter.drawPolygon(QtGui.QPolygon(points))
        elif glyph == "diamond":
            points = [QtCore.QPoint(15, 7), QtCore.QPoint(23, 15), QtCore.QPoint(15, 23), QtCore.QPoint(7, 15)]
            painter.drawPolygon(QtGui.QPolygon(points))
        elif glyph == "tween":
            painter.setPen(QtGui.QPen(QtGui.QColor("#2C2C2C"), 2))
            painter.setBrush(light)
            painter.drawEllipse(7, 12, 5, 5)
            painter.drawEllipse(18, 12, 5, 5)
            painter.setBrush(QtGui.QColor("#2C2C2C"))
            painter.drawEllipse(13, 12, 5, 5)
            painter.drawLine(12, 15, 13, 15)
            painter.drawLine(18, 15, 18, 15)
            painter.setPen(QtGui.QPen(light, 2))
            painter.drawLine(10, 22, 20, 22)
            painter.drawLine(15, 19, 15, 24)
        elif glyph == "cut":
            painter.drawLine(10, 9, 20, 21)
            painter.drawLine(20, 9, 10, 21)
        elif glyph == "zero":
            painter.setPen(QtGui.QPen(light, 2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(10, 9, 10, 12)
        elif glyph == "bars":
            painter.drawRect(9, 9, 3, 12)
            painter.drawRect(15, 9, 3, 12)
            painter.drawRect(21, 9, 3, 12)
        elif glyph == "dots":
            painter.drawEllipse(9, 10, 4, 4)
            painter.drawEllipse(17, 10, 4, 4)
            painter.drawEllipse(13, 18, 4, 4)
        elif glyph == "clean":
            painter.setPen(QtGui.QPen(light, 2))
            painter.drawLine(9, 20, 20, 9)
            painter.drawLine(16, 20, 21, 15)
        elif glyph == "guide":
            painter.setPen(QtGui.QPen(QtGui.QColor("#2C2C2C"), 2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(10, 7, 10, 16)
            painter.drawLine(13, 11, 18, 11)
            painter.drawLine(13, 15, 18, 15)
            painter.drawLine(13, 19, 17, 19)
        elif glyph == "scene":
            painter.drawRect(8, 13, 14, 8)
            painter.drawEllipse(11, 9, 8, 6)
            painter.setBrush(light)
            painter.drawEllipse(13, 15, 4, 4)
        elif glyph == "package":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(8, 11, 14, 10)
            painter.drawLine(8, 11, 15, 7)
            painter.drawLine(22, 11, 15, 7)
            painter.drawLine(15, 7, 15, 17)
        elif glyph == "folder":
            painter.setBrush(light)
            painter.setPen(QtGui.QPen(QtGui.QColor("#2C2C2C"), 2))
            painter.drawRoundedRect(7, 11, 16, 10, 2, 2)
            painter.drawRect(9, 8, 7, 4)
            painter.setPen(QtGui.QPen(color.darker(190), 2))
            painter.drawLine(10, 16, 20, 16)
            painter.drawLine(10, 19, 18, 19)
        elif glyph == "drag":
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(light)
            for x_pos in (11, 18):
                for y_pos in (9, 15, 21):
                    painter.drawEllipse(QtCore.QPoint(x_pos, y_pos), 2, 2)
        elif glyph == "history":
            painter.setPen(QtGui.QPen(QtGui.QColor("#2C2C2C"), 2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawArc(8, 8, 14, 14, 40 * 16, 285 * 16)
            painter.drawLine(10, 9, 9, 15)
            painter.drawLine(10, 9, 15, 8)
            painter.setBrush(light)
            painter.drawRoundedRect(13, 13, 8, 6, 2, 2)
        elif glyph == "parent":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(8, 8, 6, 6)
            painter.drawEllipse(17, 17, 6, 6)
            painter.drawLine(14, 14, 17, 17)
        elif glyph == "hold":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(8, 12, 6, 9)
            painter.drawEllipse(15, 10, 7, 11)
            painter.drawLine(8, 22, 22, 22)
        elif glyph == "surface":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawArc(6, 14, 18, 8, 0, 180 * 16)
            painter.setBrush(light)
            painter.drawEllipse(13, 9, 5, 5)
            painter.drawLine(15, 14, 15, 20)
        elif glyph == "pivot":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(9, 9, 12, 12)
            painter.drawLine(15, 7, 15, 23)
            painter.drawLine(7, 15, 23, 15)
            painter.drawArc(8, 8, 14, 14, 35 * 16, 230 * 16)
        elif glyph == "ikfk":
            painter.setBrush(light)
            painter.drawEllipse(7, 18, 4, 4)
            painter.drawEllipse(13, 11, 4, 4)
            painter.drawEllipse(20, 18, 4, 4)
            painter.drawLine(11, 18, 14, 14)
            painter.drawLine(17, 14, 20, 18)
        elif glyph == "retarget":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(7, 9, 6, 6)
            painter.drawEllipse(18, 16, 6, 6)
            painter.drawLine(13, 12, 19, 17)
            painter.drawLine(19, 17, 16, 17)
            painter.drawLine(19, 17, 18, 14)
        elif glyph == "picker":
            painter.setBrush(light)
            for x_value in (8, 15, 22):
                for y_value in (9, 16):
                    painter.drawEllipse(x_value - 2, y_value - 2, 4, 4)
            painter.setBrush(QtGui.QColor("#2C2C2C"))
            points = [QtCore.QPoint(12, 19), QtCore.QPoint(21, 22), QtCore.QPoint(16, 24)]
            painter.drawPolygon(QtGui.QPolygon(points))
        elif glyph == "pencil":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawLine(9, 21, 20, 10)
            painter.drawLine(12, 23, 23, 12)
            painter.drawLine(20, 10, 23, 12)
            painter.drawLine(9, 21, 12, 23)
        elif glyph == "onion":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(light, 2))
            painter.drawEllipse(8, 9, 10, 12)
            painter.drawEllipse(12, 9, 10, 12)
            painter.drawLine(15, 8, 17, 5)
        elif glyph == "rotation":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawArc(8, 8, 14, 14, 30 * 16, 285 * 16)
            points = [QtCore.QPoint(20, 8), QtCore.QPoint(23, 14), QtCore.QPoint(17, 12)]
            painter.setBrush(QtGui.QColor("#2C2C2C"))
            painter.drawPolygon(QtGui.QPolygon(points))
        elif glyph == "skin":
            painter.setBrush(QtCore.Qt.NoBrush)
            for x_value in (9, 15, 21):
                painter.drawLine(x_value, 8, x_value, 22)
            for y_value in (10, 16, 22):
                painter.drawLine(8, y_value, 22, y_value)
        elif glyph == "scale":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawLine(10, 20, 20, 10)
            painter.drawLine(20, 10, 20, 15)
            painter.drawLine(20, 10, 15, 10)
            painter.drawLine(10, 20, 10, 15)
            painter.drawLine(10, 20, 15, 20)
        elif glyph == "video":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(8, 9, 14, 12)
            painter.setBrush(light)
            painter.drawPolygon(QtGui.QPolygon([QtCore.QPoint(13, 12), QtCore.QPoint(19, 15), QtCore.QPoint(13, 18)]))
        elif glyph == "playblast":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(8, 11, 14, 11)
            painter.drawLine(9, 9, 22, 7)
            painter.drawLine(12, 8, 14, 11)
            painter.drawLine(17, 7, 19, 10)
            painter.setBrush(light)
            painter.drawPolygon(QtGui.QPolygon([QtCore.QPoint(13, 14), QtCore.QPoint(19, 17), QtCore.QPoint(13, 20)]))
        elif glyph == "notes":
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(9, 8, 12, 14)
            painter.drawLine(12, 12, 18, 12)
            painter.drawLine(12, 16, 18, 16)
            painter.drawLine(12, 20, 16, 20)
        elif glyph == "game":
            painter.setPen(QtGui.QPen(light, 3, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            painter.setBrush(light)
            painter.drawEllipse(12, 7, 6, 6)
            painter.drawLine(15, 14, 15, 20)
            painter.drawLine(15, 15, 10, 18)
            painter.drawLine(15, 15, 20, 18)
            painter.drawLine(15, 20, 11, 24)
            painter.drawLine(15, 20, 21, 24)
            painter.drawLine(11, 24, 9, 24)
            painter.drawLine(21, 24, 23, 24)
        elif glyph == "combine_freeze_pivot":
            painter.setPen(QtGui.QPen(light, 2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(7, 8, 6, 5)
            painter.drawRect(7, 18, 6, 5)
            painter.drawRect(18, 13, 6, 6)
            painter.drawLine(13, 10, 18, 16)
            painter.drawLine(13, 20, 18, 16)
            painter.setPen(QtGui.QPen(QtGui.QColor("#2C2C2C"), 2))
            painter.drawLine(21, 10, 21, 22)
            painter.drawLine(15, 16, 27, 16)
            painter.setBrush(QtGui.QColor("#F6C85F"))
            painter.drawEllipse(18, 13, 6, 6)
        else:
            painter.setPen(QtGui.QPen(light, 2))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(7 if len(str(glyph)) > 1 else 9)
            painter.setFont(font)
            painter.drawText(QtCore.QRect(5, 6, 20, 18), int(QtCore.Qt.AlignCenter), str(glyph or "?")[:2])
    finally:
        painter.end()
    return QtGui.QIcon(pixmap)


def _make_workflow_icon(tool):
    if not QtGui:
        return QtGui.QIcon() if QtGui else None
    command = str((tool or {}).get("command") or "")
    cached = _WORKFLOW_ICON_CACHE.get(command)
    if cached is not None and not cached.isNull():
        return cached
    icon_path = maya_aminate_icon_manifest.icon_path(
        command=command,
        module_root=os.path.dirname(os.path.abspath(__file__)),
    )
    icon = QtGui.QIcon(icon_path) if icon_path and os.path.exists(icon_path) else QtGui.QIcon()
    if icon.isNull():
        icon = _make_student_core_icon(tool.get("color") or "#56D7E8", tool.get("glyph") or "guide")
    _WORKFLOW_ICON_CACHE[command] = icon
    return icon


def _make_action_icon(tool, active=False):
    """Load one of the central manifest action SVGs with a safe fallback."""
    if not QtGui:
        return QtGui.QIcon() if QtGui else None
    command = str((tool or {}).get("command") or "")
    cache_key = "action:{0}:{1}".format(command, "active" if active else "inactive")
    cached = _ACTION_ICON_CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached
    icon_path = maya_aminate_icon_manifest.icon_path(
        command=command,
        module_root=os.path.dirname(os.path.abspath(__file__)),
        active=bool(active),
    )
    icon = QtGui.QIcon(icon_path) if icon_path and os.path.exists(icon_path) else QtGui.QIcon()
    if icon.isNull():
        icon = _make_student_core_icon(
            tool.get("color") or tool.get("accent") or "#56D7E8",
            tool.get("glyph") or tool.get("id") or command,
        )
    _ACTION_ICON_CACHE[cache_key] = icon
    return icon


def _apply_manifest_button_metadata(button, command, icon=None):
    """Attach manifest copy and accessibility data to any Aminate tile."""
    if not button:
        return None
    entry = maya_aminate_icon_manifest.icon_entry(command=command) or {}
    command = str(command or entry.get("command") or "")
    if command:
        button.setProperty("_aminateIconCommand", command)
    if entry:
        accent = entry.get("accent") or "#56D7E8"
        purpose = entry.get("purpose") or "Use this Aminate tool."
        help_text = entry.get("help") or ""
        shortcut = entry.get("shortcut") or ""
        shortcut_help = entry.get("shortcut_help") or ""
        title = entry.get("display_name") or command or "Tool"
        accessible_name = entry.get("accessible_label") or title
        accessible_description = "{0} {1}".format(purpose, help_text).strip()
        button.setProperty("_aminateHoverAccent", accent)
        button.setProperty("_aminateHoverTitle", title)
        button.setProperty("_aminateHoverDescription", purpose)
        button.setProperty("_aminateHoverHelp", help_text)
        button.setProperty("_aminateHoverShortcut", shortcut)
        button.setProperty("_aminateHoverShortcutHelp", shortcut_help)
        try:
            button.setAccessibleName(str(accessible_name))
            button.setAccessibleDescription(str(accessible_description))
            button.setStatusTip(str(accessible_description))
        except Exception:
            pass
        if icon is not None:
            try:
                button.setIcon(icon)
            except Exception:
                pass
    return entry


def _style_student_core_button(button, color_hex):
    if not button:
        return
    button.setIconSize(QtCore.QSize(34, 34))
    button.setMinimumWidth(64)
    button.setMinimumHeight(56)
    button.setStyleSheet(
        """
        QToolButton {
            background-color: #414141;
            color: #F1F1F1;
            border: 1px solid #5C5C5C;
            border-radius: 4px;
            padding: 4px;
            font-weight: 600;
        }
        QToolButton:hover {
            background-color: #505050;
            border-color: #666666;
        }
        QToolButton:pressed {
            background-color: #384A59;
            color: #FFFFFF;
        }
        """
    )


def _style_student_timeline_bar_button(button, color_hex):
    if not button:
        return
    button.setIconSize(QtCore.QSize(24, 24))
    button.setMinimumSize(34, 32)
    button.setMaximumSize(38, 34)
    button.setStyleSheet(
        """
        QToolButton {
            background-color: #414141;
            color: #F1F1F1;
            border: 1px solid #5C5C5C;
            border-radius: 4px;
            padding: 2px;
            font-weight: 600;
        }
        QToolButton:hover {
            background-color: #505050;
            border-color: #666666;
        }
        QToolButton:pressed {
            background-color: #384A59;
            color: #FFFFFF;
        }
        QToolButton:checked {
            background-color: #566A7A;
            border: 1px solid #5C5C5C;
        }
        QToolButton:focus {
            background-color: #505050;
            border: 2px solid #8CA5BA;
        }
        QToolButton:disabled {
            background-color: #373737;
            border-color: #4B4B4B;
            color: #858585;
        }
        """
    )


def _style_animation_layer_bar_button(button, color_hex="#55CBCD"):
    if not button:
        return
    button.setMinimumHeight(24)
    button.setMaximumHeight(28)
    button.setStyleSheet(
        """
        QToolButton {
            background-color: #414141;
            color: #F1F1F1;
            border: 1px solid #5C5C5C;
            border-radius: 4px;
            padding: 1px 6px;
            font-size: 10px;
            font-weight: 700;
        }
        QToolButton:hover {
            background-color: #505050;
            border-color: #666666;
        }
        QToolButton:checked {
            background-color: #566A7A;
            color: #FFFFFF;
        }
        QToolButton:disabled {
            color: #777777;
            background-color: #373737;
            border-color: #4B4B4B;
        }
        """
    )


def _style_toolkit_game_mode_button(button, accent=None):
    if not button:
        return
    accent = "#7892A8"
    button.setIconSize(QtCore.QSize(24, 24))
    button.setMinimumSize(38, 32)
    button.setMaximumSize(44, 34)
    button.setStyleSheet(
        """
        QToolButton {
            background-color: #414141;
            color: #EAF7FF;
            border: 1px solid #5C5C5C;
            border-radius: 4px;
            padding: 2px;
            font-weight: 700;
        }
        QToolButton:hover {
            background-color: #505050;
            border-color: #666666;
        }
        QToolButton:checked {
            background-color: #566A7A;
            color: #EAF7FF;
            border: 1px solid #5C5C5C;
        }
        QToolButton:pressed {
            background-color: #384A59;
            color: #EAF7FF;
        }
        """
    )
    if not bool(button.property("_aminateGameModeGlowBound")):
        button.toggled.connect(
            lambda checked, target=button, color=str(accent): _set_game_mode_button_glow(target, checked, color)
        )
        button.setProperty("_aminateGameModeGlowBound", True)
    _set_game_mode_button_glow(button, button.isChecked(), accent)


def _toolkit_help_title(text, fallback="Tool"):
    text = str(text or "").strip()
    if not text:
        return fallback or "Tool"
    return text.split(":", 1)[0].strip() or fallback or "Tool"


def _toolkit_title_for(command_or_name, tooltip="", fallback="Tool"):
    key = str(command_or_name or "").strip()
    icon_entry = maya_aminate_icon_manifest.icon_entry(command=key)
    if icon_entry:
        return icon_entry["display_name"]
    title = TOOLKIT_BAR_HELP_TITLES.get(key)
    if title:
        return title
    tooltip = str(tooltip or "").strip()
    if ":" in tooltip:
        return tooltip.split(":", 1)[0].strip() or fallback or "Tool"
    return _toolkit_help_title(tooltip, fallback)


def _toolkit_help_description(command_or_name, tooltip):
    key = str(command_or_name or "").strip()
    icon_entry = maya_aminate_icon_manifest.icon_entry(command=key)
    if icon_entry:
        return "{0} {1}".format(icon_entry["purpose"], icon_entry["help"])
    settings = toolkit_hover_settings()
    if settings.get("wording_mode") == "kid":
        description = TOOLKIT_BAR_KID_HELP.get(key) or TOOLKIT_BAR_SIMPLE_HELP.get(key)
        if description:
            return description
    if settings.get("wording_mode") == "simple":
        description = TOOLKIT_BAR_SIMPLE_HELP.get(key)
        if description:
            return description
    tooltip = str(tooltip or "").strip()
    if ":" in tooltip:
        tooltip = tooltip.split(":", 1)[1].strip()
    return tooltip or "Use this Aminate button."


def _toolkit_native_tooltip(title, description, details=""):
    lines = [str(title or "Tool").strip(), str(description or "").strip()]
    details = str(details or "").strip()
    if details and details not in lines:
        lines.append(details)
    return "\n".join(line for line in lines if line)


def _qt_event_type(name):
    if not QtCore:
        return None
    value = getattr(QtCore.QEvent, name, None)
    if value is not None:
        return value
    enum = getattr(QtCore.QEvent, "Type", None)
    if enum and hasattr(enum, name):
        return getattr(enum, name)
    return None


def _install_toolkit_hover_card(
    widget,
    title,
    description,
    owner=None,
    icon=None,
    accent="#56D7E8",
    help_text="",
    shortcut="",
    shortcut_help="",
):
    if not (QtCore and QtWidgets and widget):
        return
    try:
        settings = toolkit_hover_settings()
        card_owner = owner or widget.window() or _maya_main_window()
        old_filter = getattr(widget, "_aminate_toolkit_hover_filter", None)
        if old_filter is not None:
            try:
                widget.removeEventFilter(old_filter)
            except Exception:
                pass
            widget._aminate_toolkit_hover_filter = None
        widget.setProperty("_aminateLargeTooltip", True)
        widget.setProperty("_aminateHoverTitle", str(title or "Tool"))
        widget.setProperty("_aminateHoverDescription", str(description or "Use this Aminate button."))
        widget.setProperty("_aminateHoverHelp", str(help_text or ""))
        widget.setProperty("_aminateHoverAccent", str(accent or "#56D7E8"))
        widget.setProperty("_aminateHoverShortcut", str(shortcut or ""))
        widget.setProperty("_aminateHoverShortcutHelp", str(shortcut_help or ""))
        widget.setProperty("_aminateHoverIconPixels", int(settings["icon_pixels"]))
        if icon is not None:
            widget._aminate_hover_icon = icon
        widget.setToolTip(_toolkit_native_tooltip(title, description, widget.toolTip()))
        try:
            widget.setAccessibleName(str(title or "Tool"))
            widget.setAccessibleDescription(str(description or "Use this Aminate button."))
        except Exception:
            pass
        if not TOOLKIT_CUSTOM_HOVER_CARDS_ENABLED:
            card = getattr(card_owner, "_aminate_toolkit_hover_card", None)
            if card is not None:
                try:
                    card.hide()
                except Exception:
                    pass
            return
        card = getattr(card_owner, "_aminate_toolkit_hover_card", None)
        if card is None:
            card = _ToolkitBarHoverCard(card_owner)
            setattr(card_owner, "_aminate_toolkit_hover_card", card)
        card.apply_settings(settings)
        event_filter = _ToolkitBarHoverFilter(widget, card)
        widget.installEventFilter(event_filter)
        widget._aminate_toolkit_hover_filter = event_filter
    except Exception:
        pass


def refresh_toolkit_hover_cards():
    if not QtWidgets:
        return False
    refreshed = False
    for bar in list(GLOBAL_TIMELINE_BAR_WIDGETS):
        try:
            if bar is not None and hasattr(bar, "_apply_large_hover_help"):
                bar._apply_large_hover_help(force=True)
                refreshed = True
        except Exception:
            continue
    return refreshed


if QtWidgets:
    class _ToolkitBarHoverCard(QtWidgets.QFrame):
        def __init__(self, parent=None):
            flags = (
                _qt_flag("WindowType", "ToolTip", getattr(QtCore.Qt, "ToolTip", 0))
                | _qt_flag("WindowType", "FramelessWindowHint", getattr(QtCore.Qt, "FramelessWindowHint", 0))
            )
            super(_ToolkitBarHoverCard, self).__init__(None, flags)
            self.setObjectName("aminateToolkitLargeHoverCard")
            self._settings = toolkit_hover_settings()
            self._accent = "#56D7E8"
            self._target_opacity = float(self._settings["opacity"])
            self._active_widget = None
            self._opacity_animation = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
            self._opacity_animation.setDuration(TOOLKIT_HOVER_ANIMATION_MS)
            self._position_animation = QtCore.QPropertyAnimation(self, b"pos", self)
            self._position_animation.setDuration(TOOLKIT_HOVER_ANIMATION_MS)
            easing = getattr(QtCore.QEasingCurve, "OutCubic", None)
            if easing is None:
                easing_enum = getattr(QtCore.QEasingCurve, "Type", None)
                easing = getattr(easing_enum, "OutCubic", None) if easing_enum else None
            if easing is not None:
                self._opacity_animation.setEasingCurve(easing)
                self._position_animation.setEasingCurve(easing)
            self.setWindowOpacity(0.0)
            try:
                self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
            except Exception:
                pass
            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(10, 9, 10, 9)
            layout.setSpacing(10)
            self.icon_label = QtWidgets.QLabel()
            self.icon_label.setObjectName("aminateToolkitLargeHoverIcon")
            self.icon_label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(self.icon_label)
            text_layout = QtWidgets.QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(3)
            self.title_label = QtWidgets.QLabel()
            self.title_label.setObjectName("aminateToolkitLargeHoverTitle")
            self.description_label = QtWidgets.QLabel()
            self.description_label.setObjectName("aminateToolkitLargeHoverDescription")
            self.description_label.setWordWrap(True)
            self.description_label.setMinimumWidth(220)
            self.description_label.setMaximumWidth(245)
            self.help_label = QtWidgets.QLabel()
            self.help_label.setObjectName("aminateToolkitLargeHoverHelp")
            self.help_label.setWordWrap(True)
            self.help_label.setMaximumWidth(245)
            self.divider = QtWidgets.QFrame()
            self.divider.setObjectName("aminateToolkitLargeHoverDivider")
            self.divider.setFrameShape(QtWidgets.QFrame.HLine)
            self.shortcut_row = QtWidgets.QWidget()
            shortcut_layout = QtWidgets.QHBoxLayout(self.shortcut_row)
            shortcut_layout.setContentsMargins(0, 0, 0, 0)
            shortcut_layout.setSpacing(8)
            self.shortcut_badge = QtWidgets.QLabel()
            self.shortcut_badge.setObjectName("aminateToolkitLargeHoverShortcutBadge")
            self.shortcut_help_label = QtWidgets.QLabel()
            self.shortcut_help_label.setObjectName("aminateToolkitLargeHoverShortcutHelp")
            self.shortcut_help_label.setWordWrap(True)
            self.shortcut_help_label.setMaximumWidth(200)
            shortcut_layout.addWidget(self.shortcut_badge)
            shortcut_layout.addWidget(self.shortcut_help_label, 1)
            text_layout.addWidget(self.title_label)
            text_layout.addWidget(self.description_label)
            text_layout.addWidget(self.help_label)
            text_layout.addWidget(self.divider)
            text_layout.addWidget(self.shortcut_row)
            layout.addLayout(text_layout)
            self.setMinimumWidth(320)
            self.setMaximumWidth(360)
            self._apply_accent_style()
            self.apply_settings(self._settings)

        def _apply_accent_style(self):
            self.setStyleSheet(
                """
                QFrame#aminateToolkitLargeHoverCard {
                    background-color: #373737;
                    border: 1px solid #5C5C5C;
                    border-radius: 8px;
                }
                QLabel#aminateToolkitLargeHoverIcon {
                    background-color: #414141;
                    border: 1px solid #5C5C5C;
                    border-radius: 7px;
                }
                QLabel#aminateToolkitLargeHoverTitle {
                    color: #F1F1F1;
                    font-size: 15px;
                    font-weight: 800;
                }
                QLabel#aminateToolkitLargeHoverDescription,
                QLabel#aminateToolkitLargeHoverHelp,
                QLabel#aminateToolkitLargeHoverShortcutHelp {
                    color: #D7E1E8;
                    font-size: 12px;
                }
                QFrame#aminateToolkitLargeHoverDivider {
                    color: #323C46;
                    background-color: #323C46;
                    border: 0px;
                    max-height: 1px;
                }
                QLabel#aminateToolkitLargeHoverShortcutBadge {
                    color: #F7F9FB;
                    background-color: #505050;
                    border: 1px solid #5C5C5C;
                    border-radius: 4px;
                    padding: 2px 7px;
                    font-weight: 700;
                }
                """
            )

        def apply_settings(self, settings=None):
            self._settings = settings or toolkit_hover_settings()
            icon_pixels = int(self._settings.get("icon_pixels", DEFAULT_TOOLKIT_HOVER_ICON_PIXELS))
            self._target_opacity = float(self._settings.get("opacity", DEFAULT_TOOLKIT_HOVER_OPACITY))
            self.icon_label.setFixedSize(icon_pixels + 6, icon_pixels + 6)

        def hide_card(self):
            self._opacity_animation.stop()
            self._position_animation.stop()
            self._active_widget = None
            self.hide()

        def show_for(self, widget):
            if not widget or not _qt_object_valid(widget) or not widget.isVisible():
                return
            self._active_widget = widget
            self.apply_settings(toolkit_hover_settings())
            title = str(widget.property("_aminateHoverTitle") or widget.accessibleName() or "Tool")
            description = str(widget.property("_aminateHoverDescription") or widget.accessibleDescription() or "Use this Aminate button.")
            help_text = str(widget.property("_aminateHoverHelp") or "")
            accent = str(widget.property("_aminateHoverAccent") or "#56D7E8")
            shortcut = str(widget.property("_aminateHoverShortcut") or "")
            shortcut_help = str(widget.property("_aminateHoverShortcutHelp") or "")
            if accent != self._accent:
                self._accent = accent
                self._apply_accent_style()
            self.title_label.setText(title)
            self.description_label.setText(description)
            self.help_label.setText(help_text)
            self.help_label.setVisible(bool(help_text))
            self.shortcut_badge.setText(shortcut)
            self.shortcut_help_label.setText(shortcut_help)
            self.shortcut_row.setVisible(bool(shortcut))
            self.divider.setVisible(bool(shortcut))
            icon_pixels = int(self._settings.get("icon_pixels", DEFAULT_TOOLKIT_HOVER_ICON_PIXELS))
            icon = getattr(widget, "_aminate_hover_icon", None)
            if icon is None:
                icon = widget.icon() if hasattr(widget, "icon") else QtGui.QIcon()
            pixmap = None
            try:
                if icon and not icon.isNull():
                    pixmap = icon.pixmap(icon_pixels, icon_pixels)
            except Exception:
                pixmap = None
            if pixmap is None or pixmap.isNull():
                pixmap = _make_student_core_icon("#6C757D", "?").pixmap(icon_pixels, icon_pixels)
            self.icon_label.setPixmap(pixmap)
            self.adjustSize()
            anchor = widget.mapToGlobal(QtCore.QPoint(0, 0))
            pos = QtCore.QPoint(anchor.x() + int((widget.width() - self.width()) / 2), anchor.y() - self.height() - 10)
            try:
                screen = QtWidgets.QApplication.screenAt(anchor)
            except Exception:
                screen = None
            if screen is None:
                try:
                    screen = QtWidgets.QApplication.primaryScreen()
                except Exception:
                    screen = None
            if screen:
                rect = screen.availableGeometry()
                try:
                    owner_window = widget.window()
                    owner_rect = owner_window.frameGeometry() if owner_window and owner_window.isVisible() else None
                    if owner_rect and owner_rect.width() >= self.width() + 16:
                        rect = rect.intersected(owner_rect)
                except Exception:
                    pass
                if pos.y() < rect.top():
                    pos.setY(anchor.y() + widget.height() + 8)
                if pos.x() + self.width() > rect.right():
                    pos.setX(max(rect.left(), rect.right() - self.width() - 8))
                if pos.x() < rect.left():
                    pos.setX(rect.left() + 8)
            start_pos = QtCore.QPoint(pos.x(), pos.y() + 8)
            self._opacity_animation.stop()
            self._position_animation.stop()
            self.setWindowOpacity(0.0)
            self.move(start_pos)
            self.show()
            self.raise_()
            self._opacity_animation.setStartValue(0.0)
            self._opacity_animation.setEndValue(self._target_opacity)
            self._position_animation.setStartValue(start_pos)
            self._position_animation.setEndValue(pos)
            self._opacity_animation.start()
            self._position_animation.start()

    class _ToolkitBarHoverFilter(QtCore.QObject):
        def __init__(self, widget, card):
            super(_ToolkitBarHoverFilter, self).__init__(widget)
            self._card = card
            self._watched = widget
            self._show_timer = QtCore.QTimer(self)
            self._show_timer.setSingleShot(True)
            self._show_timer.setInterval(TOOLKIT_HOVER_DELAY_MS)
            self._show_timer.timeout.connect(self._show_if_valid)

        def _show_if_valid(self):
            if _qt_object_valid(self._watched) and self._watched.isVisible():
                self._card.show_for(self._watched)

        def eventFilter(self, watched, event):
            event_type = event.type() if event else None
            enter = _qt_event_type("Enter")
            tooltip = _qt_event_type("ToolTip")
            leave = _qt_event_type("Leave")
            hide = _qt_event_type("Hide")
            press = _qt_event_type("MouseButtonPress")
            focus_in = _qt_event_type("FocusIn")
            focus_out = _qt_event_type("FocusOut")
            if event_type in (enter, tooltip, focus_in):
                self._show_timer.start()
                return event_type == tooltip
            if event_type in (leave, hide, press, focus_out):
                self._show_timer.stop()
                self._card.hide_card()
            return False


def _set_game_mode_button_glow(button, enabled, accent=None):
    if not button or not QtWidgets or not QtGui:
        return
    entry = maya_aminate_icon_manifest.icon_entry(command="game_animation_mode") or {}
    icon = _make_action_icon(entry, active=bool(enabled))
    if icon is not None and not icon.isNull():
        button.setIcon(icon)
        button._aminate_hover_icon = icon
    button.setProperty("_aminateGameModeIconState", "active" if enabled else "inactive")
    try:
        # The active SVG plus checked QSS provide one clean state indicator.
        # A drop shadow can black out sibling tiles in Maya's Qt6 grab path.
        button.setGraphicsEffect(None)
    except Exception:
        pass


def _set_workflow_button_glow(button, enabled, accent="#56D7E8"):
    if not button or not QtWidgets or not QtGui:
        return
    try:
        # Checked workflow buttons use one accent outline from their QSS.
        # A second drop shadow made Animator's Pencil look permanently
        # double-selected, especially beside its normal accent underline.
        button.setGraphicsEffect(None)
        button.setProperty("_aminateWorkflowSelected", bool(enabled))
    except Exception:
        pass


def sync_workflow_toolbar_selection(tab_alias):
    global CURRENT_WORKFLOW_TAB_ALIAS
    CURRENT_WORKFLOW_TAB_ALIAS = str(tab_alias or CURRENT_WORKFLOW_TAB_ALIAS)
    synced = False
    for bar in list(GLOBAL_TIMELINE_BAR_WIDGETS):
        try:
            if bar is not None and hasattr(bar, "select_workflow_tab"):
                synced = bool(bar.select_workflow_tab(tab_alias)) or synced
        except Exception:
            continue
    return synced


def _open_workflow_tab(tab_alias):
    if not MAYA_AVAILABLE:
        return False, "Workflow tabs only open inside Maya."
    try:
        import maya_dynamic_parent_pivot as workflow
        window = getattr(workflow, "GLOBAL_WINDOW", None)
        if window and hasattr(window, "_set_initial_tab"):
            window._set_initial_tab(tab_alias)
            try:
                window.show()
            except Exception:
                pass
            return True, "Opened {0}.".format(tab_alias.replace("_", " ").title())
    except Exception:
        pass
    try:
        import aminate
        aminate.launch_aminate(dock=True, initial_tab=tab_alias)
        return True, "Opened {0}.".format(tab_alias.replace("_", " ").title())
    except Exception as exc:
        return False, "Could not open workflow tab: {0}".format(exc)


def _set_attr_if_settable(node_name, attr_name, value):
    plug = "{0}.{1}".format(node_name, attr_name)
    if not cmds or not cmds.objExists(plug):
        return False
    try:
        if cmds.getAttr(plug, lock=True):
            return False
    except Exception:
        pass
    try:
        cmds.setAttr(plug, value)
        return True
    except Exception:
        return False


def _primary_transform(node_name):
    if not node_name:
        return ""
    try:
        if cmds.nodeType(node_name) == "transform":
            return node_name
    except Exception:
        pass
    try:
        parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
    except Exception:
        parents = []
    return parents[0] if parents else node_name


def _delete_if_exists(node_name):
    if not cmds or not node_name:
        return
    try:
        if cmds.objExists(node_name):
            try:
                cmds.lockNode(node_name, lock=False)
            except Exception:
                pass
            cmds.delete(node_name)
    except Exception:
        pass


def _delete_numbered_scene_helper_nodes(base_name):
    if not cmds or not base_name:
        return
    candidates = set()
    try:
        candidates.update(cmds.ls(base_name, long=True) or [])
    except Exception:
        pass
    if any(char.isspace() for char in base_name):
        _delete_if_exists(base_name)
        return
    try:
        candidates.update(cmds.ls(base_name + "*", long=True) or [])
    except Exception:
        pass
    for node_name in sorted(candidates, key=len, reverse=True):
        short_name = _short_name(node_name)
        if short_name == base_name:
            _delete_if_exists(node_name)
            continue
        if short_name.startswith(base_name) and short_name[len(base_name):].isdigit():
            _delete_if_exists(node_name)


def _selected_render_targets():
    if not cmds:
        return []
    selected = cmds.ls(selection=True, long=True) or []
    targets = []
    for node_name in selected:
        if not node_name or not cmds.objExists(node_name):
            continue
        if _is_scene_helpers_transform(node_name):
            continue
        try:
            if cmds.nodeType(node_name) == "transform":
                targets.append(node_name)
                continue
        except Exception:
            pass
        try:
            parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
        except Exception:
            parents = []
        for parent_name in parents:
            if parent_name and cmds.objExists(parent_name):
                try:
                    if cmds.nodeType(parent_name) == "transform":
                        targets.append(parent_name)
                except Exception:
                    continue
    return _dedupe_preserve_order(targets)


def _mesh_transforms_in_scene():
    if not cmds:
        return []
    transforms = []
    for shape_name in cmds.ls(type="mesh", long=True) or []:
        try:
            if cmds.getAttr(shape_name + ".intermediateObject"):
                continue
        except Exception:
            pass
        try:
            parent_names = cmds.listRelatives(shape_name, parent=True, fullPath=True) or []
        except Exception:
            parent_names = []
        for parent_name in parent_names:
            if parent_name and cmds.objExists(parent_name):
                try:
                    if cmds.nodeType(parent_name) == "transform":
                        if _is_scene_helpers_transform(parent_name):
                            continue
                        transforms.append(parent_name)
                except Exception:
                    continue
    return _dedupe_preserve_order(transforms)


def _visible_mesh_transforms():
    if not cmds:
        return []
    transforms = []
    for transform_name in _mesh_transforms_in_scene():
        if _is_scene_helpers_transform(transform_name):
            continue
        try:
            if not cmds.getAttr(transform_name + ".visibility"):
                continue
        except Exception:
            pass
        transforms.append(transform_name)
    return transforms


def _transform_bbox(node_name):
    if not cmds or not node_name or not cmds.objExists(node_name):
        return None
    try:
        bounds = cmds.exactWorldBoundingBox(node_name)
    except Exception:
        return None
    if not bounds or len(bounds) != 6:
        return None
    return [float(value) for value in bounds]


def _union_bbox(bboxes):
    valid = [bbox for bbox in bboxes if bbox]
    if not valid:
        return None
    min_x = min(bbox[0] for bbox in valid)
    min_y = min(bbox[1] for bbox in valid)
    min_z = min(bbox[2] for bbox in valid)
    max_x = max(bbox[3] for bbox in valid)
    max_y = max(bbox[4] for bbox in valid)
    max_z = max(bbox[5] for bbox in valid)
    return [min_x, min_y, min_z, max_x, max_y, max_z]


def _scene_helpers_target_nodes():
    selected_targets = _selected_render_targets()
    if selected_targets:
        return selected_targets
    visible_meshes = _visible_mesh_transforms()
    if visible_meshes:
        largest = []
        largest_volume = -1.0
        for transform_name in visible_meshes:
            bbox = _transform_bbox(transform_name)
            if not bbox:
                continue
            span_x = max(bbox[3] - bbox[0], 0.0)
            span_y = max(bbox[4] - bbox[1], 0.0)
            span_z = max(bbox[5] - bbox[2], 0.0)
            volume = span_x * span_y * span_z
            if volume >= largest_volume:
                largest_volume = volume
                largest = [transform_name]
        if largest:
            return largest
    scene_meshes = _mesh_transforms_in_scene()
    return scene_meshes[:1]


def _is_scene_helpers_transform(node_name):
    if not node_name:
        return False
    short_name = _short_name(node_name)
    return short_name.startswith("amirSceneHelpers") or short_name.startswith("amirSceneRender") or short_name.startswith("sceneHelpers")


def _scene_helpers_focus_bbox():
    target_nodes = _scene_helpers_target_nodes()
    if not target_nodes:
        return None, []
    bbox = _union_bbox([_transform_bbox(node_name) for node_name in target_nodes])
    if not bbox:
        return None, target_nodes
    return bbox, target_nodes


def _center_from_bbox(bbox):
    return [
        (bbox[0] + bbox[3]) * 0.5,
        (bbox[1] + bbox[4]) * 0.5,
        (bbox[2] + bbox[5]) * 0.5,
    ]


def _span_from_bbox(bbox):
    return max(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2], 1.0)


def _ensure_scene_helpers_root():
    if cmds.objExists(SCENE_HELPERS_ROOT_NAME):
        return SCENE_HELPERS_ROOT_NAME
    return cmds.createNode("transform", name=SCENE_HELPERS_ROOT_NAME)


def _delete_existing_scene_helpers():
    for node_name in (
        SCENE_HELPERS_ROOT_NAME,
        SCENE_HELPERS_RENDER_ROOT_NAME,
        SCENE_HELPERS_CAMERA_ROOT_NAME,
        SCENE_HELPERS_LIGHT_ROOT_NAME,
        SCENE_HELPERS_INFINITY_WALL_NAME,
        SCENE_HELPERS_LEGACY_INFINITY_WALL_NAME,
    ):
        _delete_numbered_scene_helper_nodes(node_name)
    for node_name in list(SCENE_HELPERS_CAMERA_NAMES.values()) + list(SCENE_HELPERS_BOOKMARK_NAMES.values()) + [SCENE_HELPERS_FLOOR_NAME, SCENE_HELPERS_BACKDROP_NAME, SCENE_HELPERS_INFINITY_WALL_MAT_NAME, SCENE_HELPERS_INFINITY_WALL_SG_NAME]:
        _delete_numbered_scene_helper_nodes(node_name)


def _set_arnold_light_settings(light_shape, exposure):
    if not light_shape or not cmds.objExists(light_shape):
        return
    for attr_name, value in (("aiExposure", exposure), ("aiSamples", 2), ("intensity", DEFAULT_RENDER_ENV_LIGHT_INTENSITY)):
        try:
            if cmds.attributeQuery(attr_name, node=light_shape, exists=True):
                cmds.setAttr("{0}.{1}".format(light_shape, attr_name), value)
        except Exception:
            pass


def _make_camera(name, offset, focal_length=55.0):
    camera_result = cmds.camera(name=name) or []
    camera_transform = camera_result[0] if camera_result else name
    camera_shape = camera_result[1] if len(camera_result) > 1 else ""
    if camera_transform and cmds.objExists(camera_transform):
        try:
            cmds.setAttr(camera_shape + ".focalLength", focal_length)
        except Exception:
            pass
    return camera_transform, camera_shape


def _scene_helpers_camera_driver(camera_name, camera_root=""):
    if not cmds or not camera_name or not cmds.objExists(camera_name):
        return ""
    parent_name = ""
    try:
        parent_name = (cmds.listRelatives(camera_name, parent=True, fullPath=False) or [""])[0]
    except Exception:
        parent_name = ""
    if parent_name and parent_name.endswith("_pivot_GRP") and cmds.objExists(parent_name):
        if not camera_root:
            return parent_name
        try:
            driver_parent = (cmds.listRelatives(parent_name, parent=True, fullPath=False) or [""])[0]
        except Exception:
            driver_parent = ""
        if not driver_parent or driver_parent == camera_root:
            return parent_name
    return camera_name


def _scene_helpers_camera_specs(height_span, camera_distance):
    return {
        "front": ((0.0, DEFAULT_SCENE_HELPERS_CAMERA_BASE_HEIGHT, camera_distance), 55.0),
        "side": ((camera_distance, DEFAULT_SCENE_HELPERS_CAMERA_BASE_HEIGHT, 0.0), 55.0),
        "three_quarter": ((camera_distance * 0.72, DEFAULT_SCENE_HELPERS_CAMERA_BASE_HEIGHT, camera_distance * 0.72), 50.0),
    }


def _apply_scene_helpers_camera_offsets(render_root, center, height_span, camera_distance, height_offset, dolly_offset):
    if not cmds or not render_root or not cmds.objExists(render_root):
        return False, "Create the render environment first."
    camera_map_payload = ""
    try:
        camera_map_payload = cmds.getAttr(render_root + "." + SCENE_HELPERS_CAMERA_MAP_ATTR)
    except Exception:
        camera_map_payload = ""
    try:
        camera_map = json.loads(camera_map_payload or "{}")
    except Exception:
        camera_map = {}
    if not camera_map:
        return False, "Create the render environment first."

    specs = _scene_helpers_camera_specs(height_span, camera_distance)
    changed = 0
    camera_root = SCENE_HELPERS_CAMERA_ROOT_NAME if cmds.objExists(SCENE_HELPERS_CAMERA_ROOT_NAME) else ""
    if camera_root:
        try:
            cmds.xform(camera_root, worldSpace=True, translation=center)
        except Exception:
            pass
    for preset_key, (base_offset, _focal_length) in specs.items():
        camera_name = camera_map.get(preset_key) or SCENE_HELPERS_CAMERA_NAMES.get(preset_key, "")
        if not camera_name or not cmds.objExists(camera_name):
            continue
        final_offset = _scene_helpers_camera_offset_vector(base_offset, height_offset, dolly_offset)
        driver_name = _scene_helpers_camera_driver(camera_name, camera_root)
        try:
            cmds.xform(
                driver_name,
                worldSpace=True,
                translation=(
                    float(center[0] + final_offset[0]),
                    float(center[1] + final_offset[1]),
                    float(center[2] + final_offset[2]),
                ),
            )
            changed += 1
        except Exception:
            continue
    for attr_name, value in (
        (SCENE_HELPERS_CAMERA_HEIGHT_OFFSET_ATTR, float(height_offset)),
        (SCENE_HELPERS_CAMERA_DOLLY_OFFSET_ATTR, float(dolly_offset)),
        (SCENE_HELPERS_CAMERA_DISTANCE_ATTR, float(camera_distance)),
        (SCENE_HELPERS_HEIGHT_SPAN_ATTR, float(height_span)),
    ):
        try:
            if cmds.attributeQuery(attr_name, node=render_root, exists=True):
                cmds.setAttr("{0}.{1}".format(render_root, attr_name), value)
            else:
                cmds.addAttr(render_root, longName=attr_name, attributeType="double")
                cmds.setAttr("{0}.{1}".format(render_root, attr_name), value)
        except Exception:
            pass
    return True, "Updated helper camera offsets for {0} camera(s).".format(changed)


def _look_at(camera_transform, center):
    aim_locator = cmds.spaceLocator(name=camera_transform + "_aim_LOC")[0]
    cmds.xform(aim_locator, worldSpace=True, translation=(center[0], center[1], center[2]))
    try:
        aim_constraint = cmds.aimConstraint(
            aim_locator,
            camera_transform,
            aimVector=(0, 0, -1),
            upVector=(0, 1, 0),
            worldUpType="scene",
            maintainOffset=False,
        ) or []
        if aim_constraint:
            cmds.delete(aim_constraint)
    finally:
        _delete_if_exists(aim_locator)


def _scene_helpers_camera_offset_vector(base_offset, height_offset=0.0, dolly_offset=0.0):
    x_value, y_value, z_value = base_offset
    y_value += float(height_offset)
    dolly_offset = float(dolly_offset)
    if abs(dolly_offset) <= 1.0e-8:
        return x_value, y_value, z_value
    horizontal_length = math.sqrt((x_value * x_value) + (z_value * z_value))
    if horizontal_length <= 1.0e-8:
        z_value += dolly_offset
        return x_value, y_value, z_value
    x_value += (x_value / horizontal_length) * dolly_offset
    z_value += (z_value / horizontal_length) * dolly_offset
    return x_value, y_value, z_value
def _create_scene_helpers_bookmark(camera_transform, bookmark_name):
    if not camera_transform or not cmds.objExists(camera_transform):
        return ""
    try:
        bookmark = cmds.cameraView(camera=camera_transform, name=bookmark_name, ab=True)
    except TypeError:
        try:
            bookmark = cmds.cameraView(camera=camera_transform, name=bookmark_name)
        except Exception:
            bookmark = ""
        except Exception:
            bookmark = ""
    return bookmark or bookmark_name


def _maya_arnold_available():
    if not cmds:
        return False
    plugin_names = ("mtoa", "mtoa.mll")
    for plugin_name in plugin_names:
        try:
            if cmds.pluginInfo(plugin_name, query=True, loaded=True):
                return True
        except Exception:
            pass
    return False


def _active_model_panel():
    if not cmds:
        return ""
    try:
        focused_panel = cmds.getPanel(withFocus=True) or ""
    except Exception:
        focused_panel = ""
    if focused_panel:
        try:
            if cmds.getPanel(typeOf=focused_panel) == "modelPanel":
                return focused_panel
        except Exception:
            pass
    return (_all_model_panels() or [""])[0]


def _set_model_panel_camera(camera_name, display_label=""):
    if not cmds or not camera_name or not cmds.objExists(camera_name):
        return False, "Camera preset is not available."
    panel = _active_model_panel()
    if not panel:
        label = display_label or _short_name(camera_name)
        return True, "Ready to use {0}. Click a viewport to apply it.".format(label)
    try:
        cmds.modelEditor(panel, edit=True, camera=camera_name)
    except Exception:
        try:
            cmds.lookThru(panel, camera_name)
        except Exception as exc:
            return False, "Could not switch the viewport camera: {0}".format(exc)
    label = ""
    short_name = _short_name(camera_name).lower()
    if short_name.startswith("persp"):
        label = SCENE_HELPERS_CAMERA_PRESET_LABELS.get("perspective", "Perspective")
    for preset_key, preset_label in SCENE_HELPERS_CAMERA_PRESET_LABELS.items():
        if camera_name == SCENE_HELPERS_CAMERA_NAMES.get(preset_key, ""):
            label = preset_label
            break
    return True, "Switched the viewport to {0}.".format(label or _short_name(camera_name))


def _apply_scene_helpers_camera_preset(preset_key):
    preset_key = (preset_key or "").strip().lower().replace(" ", "_").replace("-", "_")
    display_label = SCENE_HELPERS_CAMERA_PRESET_LABELS.get(preset_key, preset_key.replace("_", " ").title())
    if preset_key == "perspective":
        camera_name = _scene_helpers_perspective_camera()
        return _set_model_panel_camera(camera_name, display_label)
    if preset_key not in SCENE_HELPERS_CAMERA_NAMES:
        return False, "Choose Perspective, Front, Side, or Three-Quarter."
    if not cmds.objExists(SCENE_HELPERS_RENDER_ROOT_NAME):
        return False, "Create the render environment first."
    camera_map_payload = ""
    try:
        camera_map_payload = cmds.getAttr(SCENE_HELPERS_RENDER_ROOT_NAME + "." + SCENE_HELPERS_CAMERA_MAP_ATTR)
    except Exception:
        camera_map_payload = ""
    try:
        camera_map = json.loads(camera_map_payload or "{}")
    except Exception:
        camera_map = {}
    camera_name = camera_map.get(preset_key) or SCENE_HELPERS_CAMERA_NAMES.get(preset_key, "")
    if not camera_name or not cmds.objExists(camera_name):
        return False, "The {0} camera is missing. Rebuild the render environment.".format(display_label)
    return _set_model_panel_camera(camera_name, display_label)


def _ensure_cgab_blast_panel_opt_change_callback():
    if not mel:
        return
    # Maya calls this callback with a single panel string on this machine.
    # Keep the stub matching that exact signature so the viewport activation step stays quiet.
    try:
        mel.eval("global proc CgAbBlastPanelOptChangeCallback(string $panel) {}")
    except Exception:
        pass


def _create_scene_helpers_sky_light(light_root, center, render_scale):
    light_mode = "fallback_directional"
    light_transform = ""
    light_shape = ""
    if _maya_arnold_available():
        try:
            light_node = cmds.shadingNode("aiSkyDomeLight", asLight=True, name="sceneHelpersSkyDomeLight")
        except Exception:
            light_node = ""
        light_transform = _primary_transform(light_node)
        if light_transform and cmds.objExists(light_transform):
            try:
                parent_result = cmds.parent(light_transform, light_root) or []
                if parent_result:
                    light_transform = _primary_transform(parent_result[0]) or light_transform
            except Exception:
                pass
            try:
                cmds.xform(light_transform, worldSpace=True, translation=center)
            except Exception:
                pass
            light_shape = (cmds.listRelatives(light_transform, shapes=True, fullPath=True) or [""])[0]
            if light_shape:
                _set_arnold_light_settings(light_shape, DEFAULT_RENDER_ENV_LIGHT_EXPOSURE * 1.1)
                try:
                    if cmds.attributeQuery("color", node=light_shape, exists=True):
                        cmds.setAttr(light_shape + ".color", 0.92, 0.96, 1.0, type="double3")
                except Exception:
                    pass
            light_mode = "arnold_skydome"
    if not light_transform or not cmds.objExists(light_transform):
        try:
            light_node = cmds.directionalLight(name="sceneHelpersSkyFallbackLight")
        except Exception:
            light_node = ""
        light_transform = _primary_transform(light_node)
        if light_transform and cmds.objExists(light_transform):
            try:
                parent_result = cmds.parent(light_transform, light_root) or []
                if parent_result:
                    light_transform = _primary_transform(parent_result[0]) or light_transform
            except Exception:
                pass
            try:
                cmds.xform(light_transform, worldSpace=True, translation=(center[0] + render_scale * 0.4, center[1] + render_scale * 0.9, center[2] + render_scale * 0.7))
            except Exception:
                pass
            try:
                _look_at(light_transform, center)
            except Exception:
                pass
            light_shape = (cmds.listRelatives(light_transform, shapes=True, fullPath=True) or [""])[0]
            if light_shape:
                try:
                    if cmds.attributeQuery("intensity", node=light_shape, exists=True):
                        cmds.setAttr(light_shape + ".intensity", 0.85)
                except Exception:
                    pass
            light_mode = "fallback_directional"
    return light_transform, light_shape, light_mode


def _create_scene_helpers_cyclorama(render_root, center, bbox, render_scale):
    wall = ""
    if om2 is not None and cmds:
        try:
            transform_name = cmds.createNode("transform", name=SCENE_HELPERS_CYCLORAMA_NAME)
            selection = om2.MSelectionList()
            selection.add(transform_name)
            transform_obj = selection.getDependNode(0)
            point_array = om2.MPointArray()
            for point in _CYCLORAMA_POINTS:
                point_array.append(om2.MPoint(*point))
            face_counts = om2.MIntArray()
            for face_count in _CYCLORAMA_FACE_COUNTS:
                face_counts.append(int(face_count))
            face_connects = om2.MIntArray()
            for face_index in _CYCLORAMA_FACE_CONNECTS:
                face_connects.append(int(face_index))
            mesh_fn = om2.MFnMesh()
            mesh_fn.create(point_array, face_counts, face_connects, parent=transform_obj)
            wall = transform_name
            try:
                base_width = abs(_CYCLORAMA_POINTS[1][0] - _CYCLORAMA_POINTS[0][0]) or 1.0
                target_width = max(render_scale * 4.2, 8.0)
                scale_factor = float(target_width) / float(base_width)
                cmds.xform(wall, scale=(scale_factor, scale_factor, scale_factor))
            except Exception:
                pass
        except Exception:
            wall = ""

    if not wall or not cmds.objExists(wall):
        return "", "Could not build the cyclorama helper."

    try:
        cmds.parent(wall, render_root)
    except Exception:
        pass

    wall_shape = (cmds.listRelatives(wall, shapes=True, fullPath=True) or [""])[0]
    if wall_shape:
        for attr_name, value in (("doubleSided", 1), ("castsShadows", 0), ("receiveShadows", 0)):
            try:
                if cmds.attributeQuery(attr_name, node=wall_shape, exists=True):
                    cmds.setAttr("{0}.{1}".format(wall_shape, attr_name), value)
            except Exception:
                pass
        try:
            if not cmds.objExists(SCENE_HELPERS_INFINITY_WALL_MAT_NAME):
                mat = cmds.shadingNode("lambert", asShader=True, name=SCENE_HELPERS_INFINITY_WALL_MAT_NAME)
                try:
                    cmds.setAttr(mat + ".color", 0.965, 0.965, 0.965, type="double3")
                    cmds.setAttr(mat + ".diffuse", 0.9)
                except Exception:
                    pass
                sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=SCENE_HELPERS_INFINITY_WALL_SG_NAME)
                cmds.connectAttr(mat + ".outColor", sg + ".surfaceShader", force=True)
            try:
                cmds.setAttr(wall_shape + ".doubleSided", 1)
            except Exception:
                pass
            cmds.sets(wall_shape, edit=True, forceElement=SCENE_HELPERS_INFINITY_WALL_SG_NAME)
        except Exception:
            pass
    try:
        cmds.xform(wall, worldSpace=True, translation=(center[0], bbox[1], center[2] - max(render_scale * 0.48, 1.0)))
    except Exception:
        pass

    return wall, "Built the cyclorama helper in Python."


def _apply_scene_helpers_render_environment(camera_height_offset=0.0, camera_dolly_offset=0.0):
    if not MAYA_AVAILABLE:
        return False, "This tool only works inside Maya."
    bbox, target_nodes = _scene_helpers_focus_bbox()
    if not bbox:
        return False, "Select a character or open a scene with visible geometry first."

    center = _center_from_bbox(bbox)
    span = _span_from_bbox(bbox)
    render_scale = max(span * DEFAULT_RENDER_ENV_SCALE_MULTIPLIER, 10.0)
    height_span = max(bbox[4] - bbox[1], 1.0)
    # Keep the default helper cameras tight around the character.
    # Students can dolly out manually if a specific shot needs more room.
    camera_distance = 20.0

    _delete_existing_scene_helpers()
    root_group = _ensure_scene_helpers_root()

    render_root = cmds.createNode("transform", name=SCENE_HELPERS_RENDER_ROOT_NAME, parent=root_group)
    camera_root = cmds.createNode("transform", name=SCENE_HELPERS_CAMERA_ROOT_NAME, parent=render_root)
    light_root = cmds.createNode("transform", name=SCENE_HELPERS_LIGHT_ROOT_NAME, parent=render_root)

    infinity_wall, infinity_wall_message = _create_scene_helpers_cyclorama(render_root, center, bbox, render_scale)

    camera_specs = _scene_helpers_camera_specs(height_span, camera_distance)
    created_cameras = {}
    created_bookmarks = []
    try:
        cmds.xform(camera_root, worldSpace=True, translation=center)
    except Exception:
        pass
    for key, (offset, focal_length) in camera_specs.items():
        camera_name = SCENE_HELPERS_CAMERA_NAMES[key]
        adjusted_offset = _scene_helpers_camera_offset_vector(offset, camera_height_offset, camera_dolly_offset)
        camera_transform, camera_shape = _make_camera(camera_name, adjusted_offset, focal_length=focal_length)
        if camera_transform:
            camera_pivot = cmds.createNode("transform", name=camera_name + "_pivot_GRP", parent=camera_root)
            cmds.parent(camera_transform, camera_pivot)
            try:
                cmds.setAttr(camera_transform + ".translateX", 0.0)
                cmds.setAttr(camera_transform + ".translateY", 0.0)
                cmds.setAttr(camera_transform + ".translateZ", 0.0)
                cmds.xform(
                    camera_pivot,
                    worldSpace=True,
                    translation=(
                        float(center[0] + adjusted_offset[0]),
                        float(center[1] + adjusted_offset[1]),
                        float(center[2] + adjusted_offset[2]),
                    ),
                )
            except Exception:
                pass
            _look_at(camera_pivot, (center[0], center[1] + float(camera_height_offset), center[2]))
            try:
                cmds.setAttr(camera_shape + ".renderable", 1)
            except Exception:
                pass
            created_cameras[key] = camera_transform
            bookmark_name = _create_scene_helpers_bookmark(camera_transform, SCENE_HELPERS_BOOKMARK_NAMES[key])
            if bookmark_name:
                created_bookmarks.append(bookmark_name)

    light_transform, light_shape, light_mode = _create_scene_helpers_sky_light(light_root, center, render_scale)
    created_lights = [light_transform] if light_transform else []

    hold_utils._set_string_attr(render_root, "sceneHelpersTarget", "|".join(target_nodes))
    hold_utils._set_string_attr(render_root, "sceneHelpersCameras", json.dumps(list(created_cameras.values())))
    hold_utils._set_string_attr(render_root, "sceneHelpersCameraMap", json.dumps(created_cameras))
    hold_utils._set_string_attr(render_root, "sceneHelpersBookmarks", json.dumps(created_bookmarks))
    hold_utils._set_string_attr(render_root, "sceneHelpersLights", json.dumps(created_lights))
    hold_utils._set_string_attr(render_root, "sceneHelpersLightMode", light_mode)
    hold_utils._set_string_attr(render_root, SCENE_HELPERS_CYCLORAMA_ATTR, infinity_wall or "")
    hold_utils._set_string_attr(render_root, "sceneHelpersInfinityWall", infinity_wall or "")
    hold_utils._set_string_attr(render_root, "sceneHelpersScale", "{0:.3f}".format(render_scale))
    hold_utils._set_string_attr(render_root, "sceneHelpersCenter", json.dumps(center))
    for attr_name, value in (
        (SCENE_HELPERS_CAMERA_HEIGHT_OFFSET_ATTR, float(camera_height_offset)),
        (SCENE_HELPERS_CAMERA_DOLLY_OFFSET_ATTR, float(camera_dolly_offset)),
        (SCENE_HELPERS_CAMERA_DISTANCE_ATTR, float(camera_distance)),
        (SCENE_HELPERS_HEIGHT_SPAN_ATTR, float(height_span)),
    ):
        try:
            if cmds.attributeQuery(attr_name, node=render_root, exists=True):
                cmds.setAttr("{0}.{1}".format(render_root, attr_name), value)
            else:
                cmds.addAttr(render_root, longName=attr_name, attributeType="double")
                cmds.setAttr("{0}.{1}".format(render_root, attr_name), value)
        except Exception:
            pass

    try:
        cmds.select(clear=True)
    except Exception:
        pass

    light_message = "Arnold sky dome" if light_mode == "arnold_skydome" else "fallback directional light"
    message = "Set up render environment for {0} target object(s): cameras, the cyclorama helper, and {1}.".format(len(target_nodes), light_message)
    if infinity_wall_message:
        message = "{0} {1}".format(message, infinity_wall_message)
    return True, message


class MayaTimingToolsController(object):
    def __init__(self):
        self.auto_snap_enabled = _option_var_bool(AUTO_SNAP_OPTION, DEFAULT_AUTO_SNAP)
        self.animation_layer_tint_enabled = _option_var_bool(ANIMATION_LAYER_TINT_OPTION, DEFAULT_ANIMATION_LAYER_TINT)
        self.keep_toolbar_extras_on_hide = _option_var_bool(KEEP_TOOLBAR_EXTRAS_ON_HIDE_OPTION, DEFAULT_KEEP_TOOLBAR_EXTRAS_ON_HIDE)
        self.game_animation_mode_enabled = _option_var_bool(GAME_ANIMATION_MODE_OPTION, DEFAULT_GAME_ANIMATION_MODE)
        self.game_animation_mode_actions = _game_animation_mode_action_settings()
        self.auto_key_enabled = _current_auto_key_state()
        self._last_time_unit = _current_time_unit()
        self._idle_script_job_id = None
        self._idle_watch_event = ""
        self._last_auto_snap_idle_check = 0.0
        self.status_callback = None
        self._history_auto_snapshot_controller = None
        self.last_render_camera_preset = "perspective"
        self.scene_helpers_camera_height_offset = 0.0
        self.scene_helpers_camera_dolly_offset = 0.0
        self.floating_channel_box_hotkey = maya_floating_channel_box.get_hotkey()
        self.floating_channel_box_opacity = maya_floating_channel_box.get_channel_opacity()
        self.floating_graph_editor_hotkey = maya_floating_channel_box.get_graph_editor_hotkey()
        self.floating_graph_editor_opacity = maya_floating_channel_box.get_graph_editor_opacity()
        self.tween_machine_hotkey = self.get_tween_machine_hotkey()
        self.tween_machine_opacity = self.get_tween_machine_opacity()
        self.teacher_demo_edit_order = []
        self.teacher_demo_edit_records = {}
        self._last_teacher_demo_synced_roots = None
        self._last_teacher_demo_synced_text = None
        try:
            crash_recovery.bootstrap_crash_recovery(startup_prompt=False)
        except Exception:
            pass
        self._floating_channel_box_manager = maya_floating_channel_box.install_global_hotkey(
            self.floating_channel_box_hotkey,
            self.floating_graph_editor_hotkey,
        )
        self._tween_machine_hotkey_manager = install_tween_machine_hotkey(
            self,
            self.tween_machine_hotkey,
        )
        _install_auto_key_warning_callback()
        self._install_idle_watch()

    def set_animation_layer_tint_enabled(self, enabled):
        self.animation_layer_tint_enabled = bool(enabled)
        _save_option_var_bool(ANIMATION_LAYER_TINT_OPTION, self.animation_layer_tint_enabled)
        if self.animation_layer_tint_enabled:
            info = self.animation_layer_tint_info()
            message = "Animation Layer Tint is on. Showing {0}.".format(info.get("label") or "Base Animation")
        else:
            message = "Animation Layer Tint is off."
        self._emit_status(message, True)
        return True, message

    def set_keep_toolbar_extras_on_hide(self, enabled):
        self.keep_toolbar_extras_on_hide = bool(enabled)
        _save_option_var_bool(KEEP_TOOLBAR_EXTRAS_ON_HIDE_OPTION, self.keep_toolbar_extras_on_hide)
        if self.keep_toolbar_extras_on_hide:
            message = "Aminate hide will keep the docked Toolkit Bar and floating helpers visible."
        else:
            message = "Aminate hide will clear the docked Toolkit Bar and floating helpers."
        self._emit_status(message, True)
        return True, message

    def animation_layer_tint_info(self):
        if not MAYA_AVAILABLE or not cmds:
            return {
                "enabled": False,
                "layer": "",
                "label": "Maya not available",
                "color": "#3A3A3A",
            }
        if not self.animation_layer_tint_enabled:
            return {
                "enabled": False,
                "layer": "",
                "label": "Animation Layer Tint Off",
                "color": "#3A3A3A",
            }
        layer_name = _active_animation_layer_name()
        if not layer_name:
            return {
                "enabled": True,
                "layer": "",
                "label": "Base Animation",
                "color": "#4A4A4A",
            }
        return {
            "enabled": True,
            "layer": layer_name,
            "label": _animation_layer_label(layer_name),
            "color": _animation_layer_color(layer_name),
        }

    def animation_layer_choices(self):
        active_layer = _active_animation_layer_name()
        choices = []
        for layer_name in _animation_layer_names(include_base=True):
            choices.append(
                {
                    "layer": layer_name,
                    "label": _animation_layer_label(layer_name),
                    "color": _animation_layer_color(layer_name),
                    "active": bool(layer_name == active_layer),
                }
            )
        if not choices:
            choices.append({"layer": "", "label": "Base Animation", "color": "#4A4A4A", "active": True})
        return choices

    def select_animation_layer_from_bar(self, layer_name):
        success, message = _set_animation_layer_selected(layer_name)
        self._emit_status(message, success)
        return success, message

    def rename_animation_layer_from_bar(self, layer_name, new_name):
        success, message, renamed = _rename_animation_layer(layer_name, new_name)
        self._emit_status(message, success)
        return success, message, renamed

    def color_animation_layer_from_bar(self, layer_name, color_hex):
        success, message = _set_animation_layer_color(layer_name, color_hex)
        self._emit_status(message, success)
        return success, message

    def create_history_auto_snapshot(self, reason):
        try:
            if self._history_auto_snapshot_controller is None:
                self._history_auto_snapshot_controller = maya_history_timeline.MayaHistoryTimelineController()
            history_controller = self._history_auto_snapshot_controller
            success, message, _record = history_controller.create_auto_snapshot(reason)
            return success, message
        except Exception as exc:
            return False, "History Timeline auto snapshot skipped: {0}".format(exc)

    def disable_maya_security_popups(self):
        if not MAYA_AVAILABLE or not cmds:
            return False, "Maya is not available."
        previous_values = []
        for option_name in MAYA_SECURITY_PROMPT_OPTION_VARS:
            try:
                previous = cmds.optionVar(query=option_name) if cmds.optionVar(exists=option_name) else "<missing>"
                cmds.optionVar(intValue=(option_name, 0))
                previous_values.append("{0}={1}".format(option_name, previous))
            except Exception:
                pass
        try:
            cmds.savePrefs(general=True)
        except Exception:
            try:
                cmds.savePrefs()
            except Exception:
                pass
        if not previous_values:
            return False, "Could not find Maya security popup settings to change."
        message = "Maya security popups disabled for trusted rigs. Restart Maya if an already-open scene keeps warning."
        self._emit_status(message, True)
        return True, message

    def create_animation_layer_from_bar(self, name=None, add_selected=True):
        try:
            cmds.undoInfo(openChunk=True, chunkName="ToolkitBarCreateAnimationLayer")
        except Exception:
            pass
        try:
            success, message, created = _create_animation_layer(name=name, add_selected=add_selected)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._emit_status(message, success)
        return success, message, created

    def duplicate_current_animation_layer(self):
        layer_name = _active_animation_layer_name()
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersDuplicateAnimationLayer")
        except Exception:
            pass
        try:
            success, message, created = _duplicate_animation_layer(layer_name)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._emit_status(message, success)
        return success, message, created

    def consolidate_other_animation_layers(self):
        current_layer = _active_animation_layer_name()
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersConsolidateOtherAnimationLayers")
        except Exception:
            pass
        try:
            success, message, created = _consolidate_other_animation_layers(current_layer)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._emit_status(message, success)
        return success, message, created

    def set_current_animation_layer_solo(self, enabled):
        layer_name = _active_animation_layer_name()
        return self.set_animation_layer_flag_from_bar(layer_name, "solo", enabled)

    def clear_animation_layer_solos(self):
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersClearAnimationLayerSolos")
        except Exception:
            pass
        try:
            success, message = _clear_animation_layer_solos()
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._emit_status(message, success)
        return success, message

    def delete_animation_layer_from_bar(self, layer_name):
        self.create_history_auto_snapshot("Before animation layer delete")
        try:
            cmds.undoInfo(openChunk=True, chunkName="ToolkitBarDeleteAnimationLayer")
        except Exception:
            pass
        try:
            success, message = _delete_animation_layer(layer_name)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._emit_status(message, success)
        return success, message

    def animation_layer_state(self, layer_name):
        return _animation_layer_state(layer_name)

    def set_animation_layer_flag_from_bar(self, layer_name, flag_name, enabled):
        try:
            cmds.undoInfo(openChunk=True, chunkName="ToolkitBarSetAnimationLayerFlag")
        except Exception:
            pass
        try:
            success, message = _set_animation_layer_flag(layer_name, flag_name, enabled)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._emit_status(message, success)
        return success, message

    def set_animation_layer_weight_from_bar(self, layer_name, weight):
        try:
            cmds.undoInfo(openChunk=True, chunkName="ToolkitBarSetAnimationLayerWeight")
        except Exception:
            pass
        try:
            success, message = _set_animation_layer_weight(layer_name, weight)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._emit_status(message, success)
        return success, message

    def edit_selected_objects_on_animation_layer_from_bar(self, layer_name, add=True):
        try:
            cmds.undoInfo(openChunk=True, chunkName="ToolkitBarEditAnimationLayerMembership")
        except Exception:
            pass
        try:
            success, message = _edit_selected_objects_on_animation_layer(layer_name, add=add)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        self._emit_status(message, success)
        return success, message

    def reset_scene_helpers_camera_offsets(self):
        self.scene_helpers_camera_height_offset = 0.0
        self.scene_helpers_camera_dolly_offset = 0.0
        return True, "Reset render camera offsets to zero."

    def set_status_callback(self, callback):
        self.status_callback = callback

    def shutdown(self):
        self._remove_idle_watch()
        _remove_auto_key_warning_callback()
        try:
            maya_floating_channel_box.shutdown_global_hotkey()
        except Exception:
            pass
        try:
            shutdown_tween_machine_hotkey(self._tween_machine_hotkey_manager)
        except Exception:
            pass
        self._tween_machine_hotkey_manager = None

    def set_floating_channel_box_hotkey(self, hotkey_text):
        normalized, message = self._validate_helper_hotkey(
            "Floating Channel Box",
            hotkey_text,
            default_value=maya_floating_channel_box.DEFAULT_HOTKEY,
            existing={
                "Tween Machine": self.tween_machine_hotkey,
                "Floating Graph Editor": self.floating_graph_editor_hotkey,
            },
        )
        if not normalized:
            self._emit_status(message, False)
            return False, message
        self.floating_channel_box_hotkey = maya_floating_channel_box.set_hotkey(normalized)
        self._floating_channel_box_manager = maya_floating_channel_box.install_global_hotkey(
            self.floating_channel_box_hotkey,
            self.floating_graph_editor_hotkey,
        )
        message = "Floating Channel Box hotkey set to {0}.".format(self.floating_channel_box_hotkey)
        self._emit_status(message, True)
        return True, message

    def set_floating_channel_box_opacity(self, opacity):
        self.floating_channel_box_opacity = maya_floating_channel_box.set_channel_opacity(opacity)
        message = "Floating Channel Box opacity set to {0:.2f}.".format(self.floating_channel_box_opacity)
        self._emit_status(message, True)
        return True, message

    def get_tween_machine_hotkey(self):
        hotkey_text = maya_floating_channel_box.normalize_hotkey(
            _option_var_string(TWEEN_MACHINE_HOTKEY_OPTION, DEFAULT_TWEEN_MACHINE_HOTKEY),
            default_value=DEFAULT_TWEEN_MACHINE_HOTKEY,
        )
        if hotkey_text in LEGACY_DEFAULT_TWEEN_MACHINE_HOTKEYS:
            _save_option_var_string(TWEEN_MACHINE_HOTKEY_OPTION, DEFAULT_TWEEN_MACHINE_HOTKEY)
            return DEFAULT_TWEEN_MACHINE_HOTKEY
        return hotkey_text

    def set_tween_machine_hotkey(self, hotkey_text):
        normalized, message = self._validate_helper_hotkey(
            "Tween Machine",
            hotkey_text,
            default_value=DEFAULT_TWEEN_MACHINE_HOTKEY,
            existing={
                "Floating Channel Box": self.floating_channel_box_hotkey,
                "Floating Graph Editor": self.floating_graph_editor_hotkey,
            },
        )
        if not normalized:
            self._emit_status(message, False)
            return False, message
        self.tween_machine_hotkey = normalized
        _save_option_var_string(TWEEN_MACHINE_HOTKEY_OPTION, self.tween_machine_hotkey)
        self._tween_machine_hotkey_manager = install_tween_machine_hotkey(
            self,
            self.tween_machine_hotkey,
        )
        message = "Tween Machine hotkey set to {0}.".format(self.tween_machine_hotkey)
        self._emit_status(message, True)
        return True, message

    def get_tween_machine_opacity(self):
        return max(0.2, min(1.0, _option_var_float(TWEEN_MACHINE_OPACITY_OPTION, DEFAULT_TWEEN_MACHINE_OPACITY)))

    def set_tween_machine_opacity(self, opacity):
        self.tween_machine_opacity = max(0.2, min(1.0, float(opacity)))
        _save_option_var_float(TWEEN_MACHINE_OPACITY_OPTION, self.tween_machine_opacity)
        message = "Tween Machine opacity set to {0:.2f}.".format(self.tween_machine_opacity)
        self._emit_status(message, True)
        return True, message

    def show_tween_machine(self):
        popup = show_tween_machine_popup_for_controller(self)
        success = bool(popup)
        message = "Tween Machine opened." if success else "Tween Machine needs Maya and Qt."
        self._emit_status(message, success)
        return success, message

    def set_floating_graph_editor_hotkey(self, hotkey_text):
        normalized, message = self._validate_helper_hotkey(
            "Floating Graph Editor",
            hotkey_text,
            default_value=maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_HOTKEY,
            existing={
                "Tween Machine": self.tween_machine_hotkey,
                "Floating Channel Box": self.floating_channel_box_hotkey,
            },
        )
        if not normalized:
            self._emit_status(message, False)
            return False, message
        self.floating_graph_editor_hotkey = maya_floating_channel_box.set_graph_editor_hotkey(normalized)
        self._floating_channel_box_manager = maya_floating_channel_box.install_global_hotkey(
            self.floating_channel_box_hotkey,
            self.floating_graph_editor_hotkey,
        )
        message = "Floating Graph Editor hotkey set to {0}.".format(self.floating_graph_editor_hotkey)
        self._emit_status(message, True)
        return True, message

    def set_floating_graph_editor_opacity(self, opacity):
        self.floating_graph_editor_opacity = maya_floating_channel_box.set_graph_editor_opacity(opacity)
        message = "Floating Graph Editor opacity set to {0:.2f}.".format(self.floating_graph_editor_opacity)
        self._emit_status(message, True)
        return True, message

    def show_floating_channel_box(self):
        success, message = maya_floating_channel_box.show_floating_channel_box()
        self._emit_status(message, success)
        return success, message

    def _validate_helper_hotkey(self, label, hotkey_text, default_value, existing=None):
        normalized = maya_floating_channel_box.normalize_hotkey(hotkey_text, default_value=default_value)
        parts = maya_floating_channel_box.hotkey_to_parts(normalized)
        if parts.get("key") is None:
            return "", "{0} hotkey '{1}' is not a recognized key.".format(label, normalized)
        normalized_lower = normalized.lower()
        for other_label, other_hotkey in (existing or {}).items():
            other_normalized = maya_floating_channel_box.normalize_hotkey(other_hotkey, default_value=other_hotkey or "")
            if other_normalized and other_normalized.lower() == normalized_lower:
                return "", "{0} already uses {1}. Pick a different hotkey for {2}.".format(other_label, normalized, label)
        return normalized, ""

    def show_floating_graph_editor(self):
        success, message = maya_floating_channel_box.show_floating_graph_editor()
        self._emit_status(message, success)
        return success, message

    def _emit_status(self, message, success=True):
        if self.status_callback:
            try:
                self.status_callback(message, success)
            except Exception:
                pass

    def _remove_idle_watch(self):
        if not cmds:
            self._idle_script_job_id = None
            return
        if self._idle_script_job_id is not None:
            try:
                cmds.scriptJob(kill=self._idle_script_job_id, force=True)
            except Exception:
                pass
        self._idle_script_job_id = None

    def _install_idle_watch(self):
        if not cmds or not self.auto_snap_enabled:
            return
        self._remove_idle_watch()
        _kill_script_jobs_with_marker("MayaTimingToolsController._on_idle")
        for event_name in ("timeUnitChanged", "idle"):
            try:
                self._idle_script_job_id = cmds.scriptJob(event=[event_name, self._on_idle], protected=True)
                self._idle_watch_event = event_name
                break
            except Exception:
                self._idle_script_job_id = None
                self._idle_watch_event = ""

    def _on_idle(self, *_args):
        if not self.auto_snap_enabled or not cmds:
            return
        if self._idle_watch_event == "idle":
            now = time.perf_counter()
            if now - self._last_auto_snap_idle_check < 1.0:
                return
            self._last_auto_snap_idle_check = now
        current_unit = _current_time_unit()
        if current_unit == self._last_time_unit:
            return
        self._last_time_unit = current_unit
        success, message = self.snap_current_targets()
        self._emit_status(message, success)

    def set_auto_snap_enabled(self, enabled):
        enabled = bool(enabled)
        self.auto_snap_enabled = enabled
        _save_option_var_bool(AUTO_SNAP_OPTION, enabled)
        self._last_time_unit = _current_time_unit()
        if enabled:
            self._install_idle_watch()
            return True, "Auto Snap To Frames is on."
        self._remove_idle_watch()
        return True, "Auto Snap To Frames is off."

    def set_auto_key_enabled(self, enabled):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        enabled = bool(enabled)
        try:
            cmds.autoKeyframe(state=enabled)
        except Exception as exc:
            self.auto_key_enabled = _current_auto_key_state()
            return False, "Could not change Auto Key: {0}".format(exc)
        self.auto_key_enabled = enabled
        return True, "Auto Key is {0}.".format("on" if enabled else "off")

    def _set_game_mode_auto_history_enabled(self, enabled, parent=None):
        if self._history_auto_snapshot_controller is None:
            self._history_auto_snapshot_controller = maya_history_timeline.MayaHistoryTimelineController(
                status_callback=self.status_callback
            )
        else:
            self._history_auto_snapshot_controller.set_status_callback(self.status_callback)
        return self._history_auto_snapshot_controller.set_auto_snapshot_enabled(
            bool(enabled),
            parent=parent,
            interval_ms=2000,
        )

    def set_game_animation_mode_enabled(self, enabled, parent=None):
        enabled = bool(enabled)
        if enabled:
            success, message = self.apply_game_animation_mode()
            if not success:
                return success, message
            auto_history_enabled = _prompt_game_mode_auto_history(parent=parent)
            history_success, history_message = self._set_game_mode_auto_history_enabled(
                auto_history_enabled,
                parent=parent,
            )
            combined_message = "{0} {1}".format(message, history_message)
            self._emit_status(combined_message, history_success)
            return history_success, combined_message
        self.game_animation_mode_enabled = False
        _save_option_var_bool(GAME_ANIMATION_MODE_OPTION, False)
        message = "Game Animation Mode visual toggle is off. Scene settings were not changed back."
        self._emit_status(message, True)
        return True, message

    def set_game_animation_mode_action_enabled(self, action_key, enabled):
        action_key = (action_key or "").strip()
        if action_key not in GAME_ANIMATION_MODE_ACTIONS:
            return False, "Unknown Game Animation Mode option: {0}".format(action_key)
        enabled = bool(enabled)
        self.game_animation_mode_actions[action_key] = enabled
        _save_option_var_bool(_game_animation_mode_action_option_name(action_key), enabled)
        label = GAME_ANIMATION_MODE_ACTIONS[action_key][0]
        message = "Game Animation Mode option {0} is {1}.".format(label, "on" if enabled else "off")
        self._emit_status(message, True)
        return True, message

    def snap_current_targets(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        nodes = _selected_transform_nodes()
        scope_label = "selected controls"
        if not nodes:
            nodes = _scene_keyed_transforms()
            scope_label = "all keyed controls"
        if not nodes:
            return False, "There are no keyed controls to snap."

        total_keys = 0
        changed_keys = 0
        changed_nodes = 0
        for node_name in nodes:
            node_changed = False
            keyable_attrs = cmds.listAttr(node_name, keyable=True) or []
            for attr_name in keyable_attrs:
                times = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
                if not times:
                    continue
                total_keys += len(times)
                changed = _snap_curve_times(node_name, attr_name)
                if changed:
                    node_changed = True
                    changed_keys += changed
            if node_changed:
                changed_nodes += 1

        if not changed_keys:
            return True, "All snapped keys were already on whole frames."
        return True, "Snapped {0} key group(s) across {1} {2}.".format(changed_keys, changed_nodes, scope_label)

    def retime_selected_keys_to_every_n_frames(self, step):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        try:
            step = int(step)
        except (TypeError, ValueError):
            return False, "Enter a whole frame step of 1 or more."
        if step < 1:
            return False, "Enter a whole frame step of 1 or more."
        nodes = _selected_transform_nodes()
        if not nodes:
            return False, "Select the rig controls to retime first."
        attrs_by_node = {}
        keyed_frames = set()
        for node_name in nodes:
            attrs = []
            for attr_name in _settable_keyable_attrs(node_name):
                try:
                    times = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
                except Exception:
                    times = []
                if times:
                    attrs.append(attr_name)
                    keyed_frames.update(float(value) for value in times)
            attrs_by_node[node_name] = attrs
        if not keyed_frames:
            return False, "Selected controls do not have any keyframes to retime."
        original_time = float(cmds.currentTime(query=True))
        changed_keys = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersRetimeEveryNFrames")
        except Exception:
            pass
        refresh_suspended = False
        try:
            try:
                cmds.refresh(suspend=True)
                refresh_suspended = True
            except Exception:
                pass
            for node_name, attrs in attrs_by_node.items():
                for attr_name in attrs:
                    try:
                        changed_keys += _retime_curve_times(node_name, attr_name, step)
                    except Exception:
                        continue
            all_times = []
            for node_name, attrs in attrs_by_node.items():
                for attr_name in attrs:
                    try:
                        all_times.extend(float(value) for value in (cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []))
                    except Exception:
                        continue
            if all_times:
                cmds.playbackOptions(edit=True, minTime=min(all_times), maxTime=max(all_times))
        finally:
            try:
                cmds.currentTime(original_time, edit=True)
            except Exception:
                pass
            if refresh_suspended:
                try:
                    cmds.refresh(suspend=False)
                except Exception:
                    pass
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        return True, "Retime complete: {0} key(s) moved to every {1} frame(s); timeline expanded to keyed range.".format(changed_keys, step)

    def key_selected_controls_on_union_frames(self, include_translation=True, include_rotation=True, include_other=False):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        include_translation = bool(include_translation)
        include_rotation = bool(include_rotation)
        include_other = bool(include_other)
        if not any((include_translation, include_rotation, include_other)):
            return False, "Choose Translation, Rotation, or Other keyable attributes first."
        nodes = _selected_transform_nodes()
        if not nodes:
            return False, "Select the rig controls to key first."
        translation_attrs = {"translateX", "translateY", "translateZ"}
        rotation_attrs = {"rotateX", "rotateY", "rotateZ"}
        keyed_frames = set()
        attrs_by_node = {}
        for node_name in nodes:
            attrs_by_node[node_name] = [
                attr_name
                for attr_name in _settable_keyable_attrs(node_name)
                if (include_translation and attr_name in translation_attrs)
                or (include_rotation and attr_name in rotation_attrs)
                or (include_other and attr_name not in translation_attrs and attr_name not in rotation_attrs)
            ]
            try:
                for time_value in cmds.keyframe(node_name, query=True, timeChange=True) or []:
                    keyed_frames.add(float(time_value))
            except Exception:
                continue
        frames = sorted(keyed_frames)
        if not frames:
            return False, "Selected controls do not have any existing keyframes to match."
        if not any(attrs_by_node.values()):
            return False, "Selected controls do not have settable keyable channels."
        original_time = float(cmds.currentTime(query=True))
        keyed_plugs = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersKeyFullBlockingPoses")
        except Exception:
            pass
        refresh_suspended = False
        try:
            try:
                cmds.refresh(suspend=True)
                refresh_suspended = True
            except Exception:
                pass
            for frame in frames:
                cmds.currentTime(frame, edit=True)
                for node_name in nodes:
                    attrs = attrs_by_node.get(node_name) or []
                    if not attrs:
                        continue
                    try:
                        cmds.setKeyframe(node_name, attribute=attrs, time=frame)
                        keyed_plugs += len(attrs)
                    except Exception:
                        for attr_name in attrs:
                            try:
                                cmds.setKeyframe(node_name, attribute=attr_name, time=frame)
                                keyed_plugs += 1
                            except Exception:
                                continue
        finally:
            try:
                cmds.currentTime(original_time, edit=True)
            except Exception:
                pass
            if refresh_suspended:
                try:
                    cmds.refresh(suspend=False)
                except Exception:
                    pass
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not keyed_plugs:
            return False, "No selected control channels could be keyed."
        channel_groups = []
        if include_translation:
            channel_groups.append("Translation")
        if include_rotation:
            channel_groups.append("Rotation")
        if include_other:
            channel_groups.append("Other")
        return True, "Keyed {0} selected control(s) on {1} shared blocking frame(s): {2}.".format(
            len(nodes), len(frames), ", ".join(channel_groups)
        )

    def _student_core_targets(self):
        nodes = _selected_transform_nodes()
        if nodes:
            return nodes, "selected controls"
        nodes = _scene_keyed_transforms()
        return nodes, "all keyed controls"

    def nudge_keys(self, frame_delta):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        frame_delta = int(frame_delta)
        if not frame_delta:
            return False, "Choose a non-zero frame move."

        selected_curves = []
        try:
            selected_curves = cmds.keyframe(query=True, selected=True, name=True) or []
        except Exception:
            selected_curves = []
        if selected_curves:
            try:
                cmds.undoInfo(openChunk=True, chunkName="StudentCoreNudgeSelectedKeys")
            except Exception:
                pass
            try:
                cmds.keyframe(edit=True, selected=True, relative=True, timeChange=frame_delta)
            finally:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass
            direction = "later" if frame_delta > 0 else "earlier"
            return True, "Moved selected Graph Editor keys {0} frame(s) {1}.".format(abs(frame_delta), direction)

        nodes, scope_label = self._student_core_targets()
        if not nodes:
            return False, "Select animated controls or selected keys first."
        try:
            cmds.undoInfo(openChunk=True, chunkName="StudentCoreNudgeControlKeys")
        except Exception:
            pass
        changed_nodes = 0
        try:
            for node_name in nodes:
                try:
                    key_count = len(cmds.keyframe(node_name, query=True, timeChange=True) or [])
                except Exception:
                    key_count = 0
                if not key_count:
                    continue
                cmds.keyframe(node_name, edit=True, relative=True, timeChange=frame_delta)
                changed_nodes += 1
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not changed_nodes:
            return False, "No keyed controls found to move."
        direction = "later" if frame_delta > 0 else "earlier"
        return True, "Moved keys on {0} {1} {2} frame(s) {3}.".format(changed_nodes, scope_label, abs(frame_delta), direction)

    def insert_inbetween_key(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        nodes, scope_label = self._student_core_targets()
        if not nodes:
            return False, "Select animated controls first."
        current_time = float(cmds.currentTime(query=True))
        inserted = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="StudentCoreInsertInbetween")
        except Exception:
            pass
        try:
            for node_name in nodes:
                keyable_attrs = cmds.listAttr(node_name, keyable=True) or []
                for attr_name in keyable_attrs:
                    try:
                        existing = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
                    except Exception:
                        existing = []
                    if not existing:
                        continue
                    if any(abs(float(time_value) - current_time) <= 1.0e-4 for time_value in existing):
                        continue
                    try:
                        cmds.setKeyframe(node_name, attribute=attr_name, time=current_time, insert=True)
                        inserted += 1
                    except Exception:
                        continue
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not inserted:
            return False, "No inbetweens were added. Pick controls with animation and move to an unkeyed frame."
        return True, "Inserted {0} inbetween key(s) on {1}.".format(inserted, scope_label)

    def build_tween_machine_context(self):
        if not MAYA_AVAILABLE:
            return {"items": [], "message": "This tool only works inside Maya.", "valid": False}
        nodes = _selected_transform_nodes()
        if not nodes:
            return {"items": [], "message": "Select animated controls before using Tween Machine.", "valid": False}
        current_time = float(cmds.currentTime(query=True))
        items = []
        missing_pairs = 0
        for node_name in nodes:
            keyable_attrs = cmds.listAttr(node_name, keyable=True) or []
            for attr_name in keyable_attrs:
                plug = "{0}.{1}".format(node_name, attr_name)
                try:
                    if cmds.getAttr(plug, lock=True) or not cmds.getAttr(plug, settable=True):
                        continue
                except Exception:
                    continue
                try:
                    times = [float(value) for value in (cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or [])]
                except Exception:
                    times = []
                left_time = None
                right_time = None
                for time_value in times:
                    if time_value < current_time - 1.0e-4:
                        if left_time is None or time_value > left_time:
                            left_time = time_value
                    elif time_value > current_time + 1.0e-4:
                        if right_time is None or time_value < right_time:
                            right_time = time_value
                if left_time is None or right_time is None:
                    missing_pairs += 1
                    continue
                try:
                    left_value = float(cmds.getAttr(plug, time=left_time))
                    right_value = float(cmds.getAttr(plug, time=right_time))
                except Exception:
                    continue
                items.append(
                    {
                        "node": node_name,
                        "attribute": attr_name,
                        "plug": plug,
                        "left_value": left_value,
                        "right_value": right_value,
                    }
                )
        if not items:
            if missing_pairs:
                message = "Tween Machine needs a previous and next key around the current frame."
            else:
                message = "No settable keyed channels were found for Tween Machine."
            return {"items": [], "message": message, "valid": False}
        return {"items": items, "time": current_time, "message": "Tween Machine ready.", "valid": True}

    def apply_tween_machine(self, percent, context=None, key=True):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        try:
            percent = max(0.0, min(100.0, float(percent)))
        except Exception:
            percent = 50.0
        blend = percent / 100.0
        context = context or self.build_tween_machine_context()
        items = list((context or {}).get("items") or [])
        if not items:
            return False, (context or {}).get("message") or "Tween Machine needs a previous and next key around the current frame."
        current_time = float((context or {}).get("time") or cmds.currentTime(query=True))
        changed_attrs = 0
        values_by_index = []
        items_by_node_attr = {}
        for index, item in enumerate(items):
            node_name = item.get("node")
            attr_name = item.get("attribute")
            left_value = float(item.get("left_value", 0.0))
            tween_value = left_value + ((float(item.get("right_value", 0.0)) - left_value) * blend)
            values_by_index.append((item, tween_value))
            if node_name and attr_name:
                items_by_node_attr.setdefault(node_name, {})[attr_name] = (index, item, tween_value)
        if key:
            try:
                cmds.undoInfo(openChunk=True, chunkName="StudentCoreTweenMachine")
            except Exception:
                pass
        try:
            applied_indices = set()
            compound_sets = (
                ("translate", ("translateX", "translateY", "translateZ")),
                ("rotate", ("rotateX", "rotateY", "rotateZ")),
                ("scale", ("scaleX", "scaleY", "scaleZ")),
            )
            for node_name, attr_map in items_by_node_attr.items():
                for compound_attr, component_attrs in compound_sets:
                    if not all(attr_name in attr_map for attr_name in component_attrs):
                        continue
                    indices = [attr_map[attr_name][0] for attr_name in component_attrs]
                    if any(index in applied_indices for index in indices):
                        continue
                    values = [attr_map[attr_name][2] for attr_name in component_attrs]
                    try:
                        cmds.setAttr("{0}.{1}".format(node_name, compound_attr), values[0], values[1], values[2])
                        if key:
                            try:
                                cmds.setKeyframe(node_name, attribute=compound_attr, time=current_time)
                            except Exception:
                                for attr_name in component_attrs:
                                    cmds.setKeyframe(node_name, attribute=attr_name, time=current_time, value=attr_map[attr_name][2])
                        applied_indices.update(indices)
                        changed_attrs += len(indices)
                    except Exception:
                        continue
            for index, (item, tween_value) in enumerate(values_by_index):
                if index in applied_indices:
                    continue
                plug = item.get("plug") or "{0}.{1}".format(item.get("node"), item.get("attribute"))
                try:
                    cmds.setAttr(plug, tween_value)
                    if key:
                        cmds.setKeyframe(item.get("node"), attribute=item.get("attribute"), time=current_time, value=tween_value)
                    changed_attrs += 1
                except Exception:
                    continue
        finally:
            if key:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass
        if not changed_attrs:
            return False, "No settable keyed channels were found for Tween Machine."
        if not key:
            return True, "Tween Machine previewed {0} channel(s) at {1:.0f}%.".format(changed_attrs, percent)
        return True, "Tween Machine keyed {0} channel(s) at {1:.0f}% between previous and next keys.".format(changed_attrs, percent)

    def remove_current_keys(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        nodes, scope_label = self._student_core_targets()
        if not nodes:
            return False, "Select animated controls first."
        current_time = float(cmds.currentTime(query=True))
        removed = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="StudentCoreRemoveCurrentKeys")
        except Exception:
            pass
        try:
            for node_name in nodes:
                keyable_attrs = cmds.listAttr(node_name, keyable=True) or []
                for attr_name in keyable_attrs:
                    try:
                        times = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
                    except Exception:
                        times = []
                    if not any(abs(float(time_value) - current_time) <= 1.0e-4 for time_value in times):
                        continue
                    try:
                        cmds.cutKey(node_name, attribute=attr_name, time=(current_time, current_time), option="keys")
                        removed += 1
                    except Exception:
                        continue
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not removed:
            return False, "There were no keys on this frame for the chosen controls."
        return True, "Removed {0} key(s) on frame {1:g} from {2}.".format(removed, current_time, scope_label)

    def reset_selected_transforms(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        nodes = _selected_transform_nodes()
        if not nodes:
            return False, "Select controls to reset first."
        changed = 0
        keyed = 0
        reset_values = (
            ("translateX", 0.0), ("translateY", 0.0), ("translateZ", 0.0),
            ("rotateX", 0.0), ("rotateY", 0.0), ("rotateZ", 0.0),
            ("scaleX", 1.0), ("scaleY", 1.0), ("scaleZ", 1.0),
        )
        should_key = _current_auto_key_state()
        try:
            cmds.undoInfo(openChunk=True, chunkName="StudentCoreResetPose")
        except Exception:
            pass
        try:
            for node_name in nodes:
                for attr_name, value in reset_values:
                    if _set_attr_if_settable(node_name, attr_name, value):
                        changed += 1
                        if should_key:
                            try:
                                cmds.setKeyframe(node_name, attribute=attr_name)
                                keyed += 1
                            except Exception:
                                pass
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not changed:
            return False, "Selected controls did not have settable transform channels."
        message = "Reset {0} transform channel(s) on {1} control(s).".format(changed, len(nodes))
        if keyed:
            message = "{0} Keyed {1} reset channel(s) because Auto Key is on.".format(message, keyed)
        return True, message

    def bake_selected_interval(self, frame_step=2):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        nodes = _selected_transform_nodes()
        if not nodes:
            return False, "Select controls to bake first."
        frame_step = max(1, int(frame_step or 1))
        start_time = float(cmds.playbackOptions(query=True, minTime=True))
        end_time = float(cmds.playbackOptions(query=True, maxTime=True))
        attrs = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")
        try:
            cmds.undoInfo(openChunk=True, chunkName="StudentCoreBakeInterval")
        except Exception:
            pass
        try:
            cmds.bakeResults(
                nodes,
                time=(start_time, end_time),
                sampleBy=frame_step,
                simulation=True,
                preserveOutsideKeys=True,
                sparseAnimCurveBake=False,
                disableImplicitControl=True,
                attribute=attrs,
            )
        except Exception as exc:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
            return False, "Could not bake selected controls: {0}".format(exc)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        return True, "Baked {0} selected control(s) from frame {1:g} to {2:g} every {3} frame(s).".format(len(nodes), start_time, end_time, frame_step)

    def select_animated_controls(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        nodes = _scene_keyed_transforms()
        if not nodes:
            return False, "No animated transform controls found."
        cmds.select(nodes, replace=True)
        return True, "Selected {0} animated control(s).".format(len(nodes))

    def remove_static_animation_curves(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        nodes = _selected_transform_nodes()
        if not nodes:
            return False, "Select controls before cleaning static curves."
        deleted = 0
        try:
            cmds.undoInfo(openChunk=True, chunkName="StudentCoreCleanStaticCurves")
        except Exception:
            pass
        try:
            for node_name in nodes:
                curves = cmds.listConnections(node_name, source=True, destination=False, type="animCurve") or []
                for curve_name in _dedupe_preserve_order(curves):
                    try:
                        values = cmds.keyframe(curve_name, query=True, valueChange=True) or []
                    except Exception:
                        values = []
                    if len(values) <= 1:
                        continue
                    first_value = float(values[0])
                    if not all(abs(float(value) - first_value) <= 1.0e-5 for value in values):
                        continue
                    try:
                        cmds.delete(curve_name)
                        deleted += 1
                    except Exception:
                        continue
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        if not deleted:
            return True, "No static curves needed cleaning on selected controls."
        return True, "Deleted {0} static animation curve(s) on selected controls.".format(deleted)

    def combine_selected_meshes_freeze_edit_pivot(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        mesh_nodes = _selected_mesh_transform_nodes()
        if len(mesh_nodes) < 2:
            return False, "Select at least two mesh objects before using Combine Freeze Pivot."
        combined = ""
        try:
            cmds.undoInfo(openChunk=True, chunkName="ToolkitBarCombineFreezeEditPivot")
        except Exception:
            pass
        try:
            combined_nodes = cmds.polyUnite(
                mesh_nodes,
                constructionHistory=False,
                mergeUVSets=True,
                name="combined_mesh_GEO",
            ) or []
            combined = combined_nodes[0] if combined_nodes else ""
            if not combined or not cmds.objExists(combined):
                return False, "Maya did not create a combined mesh."
            try:
                cmds.delete(combined, constructionHistory=True)
            except Exception:
                pass
            cmds.makeIdentity(combined, apply=True, translate=True, rotate=True, scale=True, normal=0)
            cmds.select(combined, replace=True)
            try:
                cmds.setToolTo("moveSuperContext")
            except Exception:
                pass
            if mel:
                try:
                    mel.eval("ctxEditMode;")
                except Exception:
                    pass
        except Exception as exc:
            return False, "Could not combine selected meshes: {0}".format(exc)
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        message = "Combined {0} mesh objects, froze transforms, and entered Edit Pivot mode.".format(len(mesh_nodes))
        self._emit_status(message, True)
        return True, message

    def package_scene_to_zip_from_bar(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        self.create_history_auto_snapshot("Before Reference Manager package")
        try:
            import maya_reference_manager
            controller = maya_reference_manager.ReferencePackageController()
            result = controller.package_current_scene(
                include_references=True,
                include_external=True,
                save_scene=True,
                retarget_package_scene=True,
            )
        except Exception as exc:
            return False, "Could not package scene to zip: {0}".format(exc)

        package_dir = result.get("package_dir") or os.path.dirname(result.get("zip_path") or "")
        opened_folder = False
        if package_dir and os.path.isdir(package_dir):
            try:
                os.startfile(package_dir)
                opened_folder = True
            except Exception:
                opened_folder = False
        zip_path = result.get("zip_path") or ""
        copied_count = int(result.get("copied_count") or 0)
        missing_count = int(result.get("missing_count") or 0)
        if opened_folder:
            message = "Packaged scene zip and opened folder: {0}".format(zip_path)
        else:
            message = "Packaged scene zip: {0}".format(zip_path)
        if copied_count or missing_count:
            message = "{0} Copied {1} file(s), missing {2}.".format(message, copied_count, missing_count)
        success = not bool(missing_count)
        self._emit_status(message, success)
        return success, message

    def playblast_documents_1080p(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        documents_dir = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), "Documents")
        try:
            if not os.path.isdir(documents_dir):
                os.makedirs(documents_dir)
            scene_name = cmds.file(query=True, sceneName=True) or "untitled"
            scene_stem = os.path.splitext(os.path.basename(scene_name))[0] or "untitled"
            scene_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", scene_stem)
            output_path = os.path.join(
                documents_dir,
                "Aminate_Playblast_{0}_{1}.avi".format(scene_stem, time.strftime("%Y%m%d_%H%M%S")),
            )
            cmds.playblast(
                completeFilename=output_path,
                format="avi",
                compression="none",
                widthHeight=(1920, 1080),
                percent=100,
                quality=100,
                forceOverwrite=True,
                viewer=False,
                showOrnaments=True,
                offScreen=True,
                throwOnError=True,
            )
        except Exception as exc:
            return False, "Could not create 1080p AVI playblast: {0}".format(exc)
        if not os.path.isfile(output_path):
            return False, "Maya completed the playblast without creating the expected AVI file."
        return True, "1080p full-scale AVI playblast saved to {0}.".format(output_path)

    def export_selected_animation_fbx_from_bar(self, parent=None):
        """Open the selected-animation FBX options panel from the Toolkit Bar."""
        if not MAYA_AVAILABLE:
            return False, "Selected-animation FBX export only works inside Maya."
        try:
            import maya_selected_animation_fbx_export as exporter

            return exporter.show_selected_animation_fbx_options(
                parent=parent,
                status_callback=self._emit_status,
                controller=self,
            )
        except Exception as exc:
            message = "Could not open selected-animation FBX export: {0}".format(exc)
            self._emit_status(message, False)
            return False, message

    # Short alias keeps controller dispatch discoverable to external callers.
    show_selected_animation_fbx_export = export_selected_animation_fbx_from_bar

    def run_student_core_command(self, command):
        command = (command or "").strip().lower()
        if command == "nudge_left":
            return self.nudge_keys(-1)
        if command == "nudge_right":
            return self.nudge_keys(1)
        if command == "insert_inbetween":
            return self.insert_inbetween_key()
        if command == "tween_machine":
            return True, "Open Tween Machine from the Toolkit Bar slider."
        if command == "remove_current":
            return self.remove_current_keys()
        if command == "reset_pose":
            return self.reset_selected_transforms()
        if command == "bake_twos":
            return self.bake_selected_interval(2)
        if command == "select_animated":
            return self.select_animated_controls()
        if command == "clean_static":
            return self.remove_static_animation_curves()
        if command == "combine_freeze_pivot":
            return self.combine_selected_meshes_freeze_edit_pivot()
        if command == "package_scene_zip":
            return self.package_scene_to_zip_from_bar()
        if command == "playblast_1080p":
            return self.playblast_documents_1080p()
        if command == "export_selected_animation_fbx":
            return self.export_selected_animation_fbx_from_bar()
        return False, "Unknown Toolkit Bar command: {0}".format(command)

    def apply_game_animation_mode(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        actions = dict(getattr(self, "game_animation_mode_actions", {}) or _game_animation_mode_action_settings())
        completed = []

        if actions.get("time_unit", True):
            try:
                cmds.currentUnit(time=DEFAULT_TIME_UNIT)
                completed.append("30 fps")
            except Exception as exc:
                return False, "Could not set the scene to 30 fps: {0}".format(exc)

        if actions.get("playback_speed", True):
            try:
                cmds.playbackOptions(edit=True, playbackSpeed=DEFAULT_PLAYBACK_SPEED)
                completed.append("real-time playback")
            except Exception as exc:
                return False, "Could not set playback to real-time: {0}".format(exc)

        if actions.get("update_view_all", True):
            try:
                cmds.playbackOptions(edit=True, view="all")
                completed.append("Time Slider update view All")
            except Exception as exc:
                return False, "Could not set Time Slider update view to All: {0}".format(exc)

        if actions.get("autosave", True):
            try:
                cmds.autoSave(enable=True, limitBackups=True, maxBackups=DEFAULT_MAX_BACKUPS)
                completed.append("autosave backups")
            except Exception as exc:
                return False, "Could not enable autosave backups: {0}".format(exc)

        weighted_curve_count = 0
        if actions.get("weighted_tangents", True):
            weighted_curve_count = _convert_anim_curves_to_weighted_tangents()
            completed.append("{0} weighted tangent curve(s)".format(weighted_curve_count))

        active_panels = 0
        if actions.get("activate_viewports", True):
            _ensure_cgab_blast_panel_opt_change_callback()
            if os.environ.get("AMINATE_GAME_MODE_ALL_VIEWPORTS") == "1":
                panel_names = _all_model_panels()
            else:
                active_panel = _active_model_panel()
                panel_names = [active_panel] if active_panel else []
            for panel_name in panel_names:
                try:
                    cmds.modelEditor(panel_name, edit=True, activeView=True)
                    active_panels += 1
                except Exception:
                    pass
            completed.append("{0} active viewport(s)".format(active_panels))

        texture_message = ""
        if actions.get("load_textures", True):
            _texture_success, texture_message, _texture_details = self.load_scene_textures(emit_status=False)
            if texture_message:
                completed.append(texture_message)

        self._last_time_unit = _current_time_unit()
        self.game_animation_mode_enabled = True
        _save_option_var_bool(GAME_ANIMATION_MODE_OPTION, True)
        if completed:
            message = "Game Animation Mode is on. {0}.".format("; ".join(completed))
        else:
            message = "Game Animation Mode is on. No setup options are enabled."
        self._emit_status(message, True)
        return True, message

    def load_scene_textures(self, emit_status=True):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}

        search_roots = _texture_search_roots()
        basename_map = _build_texture_basename_index(search_roots)
        scanned_nodes = 0
        reloaded_nodes = 0
        repathed_nodes = 0
        missing_nodes = []
        processed_nodes = []

        for node_type, attr_name in _scene_texture_node_specs():
            for node_name in cmds.ls(type=node_type) or []:
                scanned_nodes += 1
                try:
                    current_path = cmds.getAttr(node_name + "." + attr_name) or ""
                except Exception:
                    current_path = ""
                resolved_path, was_repathed = _resolve_texture_path(current_path, basename_map, search_roots)
                if not resolved_path:
                    missing_nodes.append(node_name)
                    continue
                if _refresh_texture_node(node_name, attr_name, resolved_path):
                    processed_nodes.append(node_name)
                    reloaded_nodes += 1
                    if was_repathed or os.path.normpath(current_path or "") != os.path.normpath(resolved_path):
                        repathed_nodes += 1
                else:
                    missing_nodes.append(node_name)

        try:
            cmds.filePathEditor(refresh=True)
        except Exception:
            pass
        try:
            cmds.refresh(force=True)
        except Exception:
            pass

        detail = {
            "scanned_nodes": scanned_nodes,
            "reloaded_nodes": reloaded_nodes,
            "repathed_nodes": repathed_nodes,
            "missing_nodes": list(missing_nodes),
            "search_roots": list(search_roots),
            "processed_nodes": list(processed_nodes),
        }

        if not scanned_nodes:
            message = "There were no scene texture nodes to load."
            success = True
        else:
            parts = ["Loaded {0} texture node(s)".format(reloaded_nodes)]
            if repathed_nodes:
                parts.append("fixed {0} broken path(s)".format(repathed_nodes))
            if missing_nodes:
                parts.append("{0} still missing".format(len(missing_nodes)))
            message = ". ".join(parts) + "."
            success = True

        if emit_status:
            self._emit_status(message, success)
        return success, message, detail

    def recover_last_autosave(self, prompt=True, force=False, prefer_current_scene=True):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}
        return crash_recovery.recover_last_autosave(
            prompt=prompt,
            force=force,
            prefer_current_scene=prefer_current_scene,
        )

    def setup_render_environment(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        self.reset_scene_helpers_camera_offsets()
        success, message = _apply_scene_helpers_render_environment(
            camera_height_offset=self.scene_helpers_camera_height_offset,
            camera_dolly_offset=self.scene_helpers_camera_dolly_offset,
        )
        if success:
            self.last_render_camera_preset = "perspective"
            preset_success, preset_message = _apply_scene_helpers_camera_preset("perspective")
            if preset_success:
                message = "{0} {1}".format(message, preset_message)
        self._emit_status(message, success)
        return success, message

    def delete_render_environment(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not cmds.objExists(SCENE_HELPERS_RENDER_ROOT_NAME) and not cmds.objExists(SCENE_HELPERS_ROOT_NAME):
            self.reset_scene_helpers_camera_offsets()
            self.last_render_camera_preset = "perspective"
            preset_success, preset_message = _apply_scene_helpers_camera_preset("perspective")
            message = "No render environment to delete."
            if preset_success:
                message = "{0} {1}".format(message, preset_message)
            self._emit_status(message, True)
            return True, message
        self.create_history_auto_snapshot("Before render environment delete")
        _delete_existing_scene_helpers()
        self.reset_scene_helpers_camera_offsets()
        self.last_render_camera_preset = "perspective"
        message = "Deleted the render environment."
        preset_success, preset_message = _apply_scene_helpers_camera_preset("perspective")
        if preset_success:
            message = "{0} {1}".format(message, preset_message)
        self._emit_status(message, True)
        return True, message

    def duplicate_selected_rig_for_teacher_demo(self, offset_x=DEFAULT_TEACHER_RIG_DUPLICATE_OFFSET_X):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}
        roots = _selected_transform_roots()
        if not roots:
            message = "Select one rig root group, then click Duplicate Rig For Teacher Demo."
            self._emit_status(message, False)
            return False, message, {}
        if len(roots) > 1:
            message = "Select only one rig root group. Found {0} selected roots.".format(len(roots))
            self._emit_status(message, False)
            return False, message, {}
        success, message, detail = _duplicate_rig_root_for_teacher_demo(roots[0], offset_x=offset_x)
        if success:
            self.reset_teacher_demo_edit_log()
        self._emit_status(message, success)
        return success, message, detail

    def delete_teacher_demo_duplicates(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        try:
            cmds.undoInfo(openChunk=True, chunkName="AminateDeleteTeacherDemoDuplicates")
        except Exception:
            pass
        try:
            deleted, deleted_layers = _delete_teacher_demo_duplicates()
            if not deleted and not deleted_layers:
                message = "No teacher demo duplicates found."
                self._emit_status(message, True)
                return True, message
            self.teacher_demo_edit_order = []
            self.teacher_demo_edit_records = {}
            message = "Deleted {0} teacher demo duplicate(s) and {1} teacher demo layer(s).".format(deleted, deleted_layers)
            self._emit_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not delete teacher demo duplicates: {0}".format(exc)
            self._emit_status(message, False)
            return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    def reset_teacher_demo_edit_log(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}
        roots = _teacher_demo_duplicate_roots()
        for root_name in roots:
            _teacher_demo_set_baseline(root_name)
        _sync_teacher_demo_edit_log_scene_storage(roots, "")
        self.teacher_demo_edit_order = []
        self.teacher_demo_edit_records = {}
        self._last_teacher_demo_synced_roots = tuple(roots)
        self._last_teacher_demo_synced_text = ""
        message = "Teacher demo edit log reset from the current duplicate rig pose."
        return True, message, {"lines": [], "text": "", "count": 0}

    def refresh_teacher_demo_edit_log(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}
        roots = _teacher_demo_duplicate_roots()
        if not roots:
            self.teacher_demo_edit_order = []
            self.teacher_demo_edit_records = {}
            _sync_teacher_demo_edit_log_scene_storage([], "")
            return True, "No teacher demo duplicate found.", {"lines": [], "text": "", "count": 0}
        baseline = {}
        for root_name in roots:
            baseline.update(_teacher_demo_baseline_for_root(root_name))
        current = _teacher_demo_collect_edit_state(roots)
        active_keys = set()
        for key, baseline_item in baseline.items():
            current_item = current.get(key)
            if not current_item:
                continue
            if _teacher_demo_values_equal(baseline_item.get("value"), current_item.get("value")):
                continue
            active_keys.add(key)
            if key not in self.teacher_demo_edit_order:
                self.teacher_demo_edit_order.append(key)
            self.teacher_demo_edit_records[key] = {
                "sentence": _teacher_demo_edit_sentence(baseline_item, current_item),
                "baseline": baseline_item,
                "current": current_item,
            }
        for key in list(self.teacher_demo_edit_records):
            if key not in active_keys:
                self.teacher_demo_edit_records.pop(key, None)
        self.teacher_demo_edit_order = [key for key in self.teacher_demo_edit_order if key in self.teacher_demo_edit_records]
        lines = _teacher_demo_edit_log_lines(self.teacher_demo_edit_order, self.teacher_demo_edit_records)
        text = "\n".join(lines)
        root_signature = tuple(roots)
        if (
            self._last_teacher_demo_synced_roots != root_signature
            or self._last_teacher_demo_synced_text != text
        ):
            _sync_teacher_demo_edit_log_scene_storage(roots, text)
            self._last_teacher_demo_synced_roots = root_signature
            self._last_teacher_demo_synced_text = text
        message = "Teacher demo edit log has {0} item(s).".format(len(lines))
        return True, message, {"lines": lines, "text": text, "count": len(lines)}

    def list_scene_text_notes(self):
        if not MAYA_AVAILABLE:
            return []
        return _scene_text_note_list()

    def create_scene_text_note(
        self,
        text,
        color_hex=SCENE_TEXT_NOTE_DEFAULT_COLOR,
        size=SCENE_TEXT_NOTE_DEFAULT_SCALE,
        wrap_enabled=SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED,
        box_width=SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH,
        box_height=SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT,
    ):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersCreateTextNote")
        except Exception:
            pass
        try:
            note = _create_scene_text_note(
                text,
                color_hex=color_hex,
                size=size,
                wrap_enabled=wrap_enabled,
                box_width=box_width,
                box_height=box_height,
            )
            message = "Created scene text note: {0}.".format(_node_short_name(note.get("node")))
            self._emit_status(message, True)
            return True, message, note
        except Exception as exc:
            message = "Could not create scene text note: {0}".format(exc)
            self._emit_status(message, False)
            return False, message, {}
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    def set_scene_text_note_text(self, note_node, text):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not note_node or not cmds.objExists(note_node):
            return False, "Pick a scene text note first."
        note_node = _long_scene_name(note_node)
        text = (text or "Student note").strip() or "Student note"
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersSetTextNoteText")
        except Exception:
            pass
        try:
            _ensure_string_attr(note_node, SCENE_TEXT_NOTE_TEXT_ATTR, text)
            _rebuild_scene_text_note_text(note_node)
            message = "Updated text note wording: {0}.".format(_node_short_name(note_node))
            self._emit_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not update text note wording: {0}".format(exc)
            self._emit_status(message, False)
            return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    def set_scene_text_note_layout(
        self,
        note_node,
        wrap_enabled=SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED,
        box_width=SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH,
        box_height=SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT,
    ):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not note_node or not cmds.objExists(note_node):
            return False, "Pick a scene text note first."
        note_node = _long_scene_name(note_node)
        box_width = _clamp_scene_text_note_box_size(box_width, SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
        box_height = _clamp_scene_text_note_box_size(box_height, SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT)
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersSetTextNoteLayout")
        except Exception:
            pass
        try:
            _ensure_bool_attr(note_node, SCENE_TEXT_NOTE_WRAP_ATTR, bool(wrap_enabled))
            _ensure_double_attr(note_node, SCENE_TEXT_NOTE_BOX_WIDTH_ATTR, box_width)
            _ensure_double_attr(note_node, SCENE_TEXT_NOTE_BOX_HEIGHT_ATTR, box_height)
            _rebuild_scene_text_note_text(note_node)
            message = "Updated text note wrap box: {0:g} x {1:g}.".format(box_width, box_height)
            self._emit_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not update text note wrap box: {0}".format(exc)
            self._emit_status(message, False)
            return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    def set_scene_text_note_size(self, note_node, size):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not note_node or not cmds.objExists(note_node):
            return False, "Pick a scene text note first."
        note_node = _long_scene_name(note_node)
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersSetTextNoteSize")
        except Exception:
            pass
        try:
            applied_size = _apply_scene_text_note_size(note_node, size)
            message = "Changed text note size to {0:g}: {1}.".format(applied_size, _node_short_name(note_node))
            self._emit_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not change text note size: {0}".format(exc)
            self._emit_status(message, False)
            return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    def select_scene_text_note_wrap_box(self, note_node):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not note_node or not cmds.objExists(note_node):
            return False, "Pick a scene text note first."
        try:
            control_node = _create_or_update_scene_text_note_wrap_box_control(note_node)
            if control_node and cmds.objExists(control_node):
                cmds.select(control_node, replace=True)
                message = "Selected resize box. Use Maya Scale to drag the wrap width or height."
                self._emit_status(message, True)
                return True, message
        except Exception as exc:
            message = "Could not select text note resize box: {0}".format(exc)
            self._emit_status(message, False)
            return False, message
        return False, "Could not find the resize box for that note."

    def key_scene_text_note_visibility(self, note_node, visible=True):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not note_node or not cmds.objExists(note_node):
            return False, "Pick a scene text note first."
        note_node = _long_scene_name(note_node)
        frame = cmds.currentTime(query=True)
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersKeyTextNoteVisibility")
        except Exception:
            pass
        try:
            cmds.setAttr(note_node + ".visibility", bool(visible))
            cmds.setKeyframe(note_node, attribute="visibility", time=frame, value=1 if visible else 0)
            message = "Keyed {0} {1} on frame {2:g}.".format(
                _node_short_name(note_node),
                "on" if visible else "off",
                frame,
            )
            self._emit_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not key scene text note visibility: {0}".format(exc)
            self._emit_status(message, False)
            return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    def set_scene_text_note_color(self, note_node, color_hex):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not note_node or not cmds.objExists(note_node):
            return False, "Pick a scene text note first."
        note_node = _long_scene_name(note_node)
        color_hex = color_hex or SCENE_TEXT_NOTE_DEFAULT_COLOR
        try:
            _ensure_string_attr(note_node, SCENE_TEXT_NOTE_COLOR_ATTR, color_hex)
            _set_display_color(note_node, color_hex)
            _rebuild_scene_text_note_line(note_node)
            message = "Changed text note color: {0}.".format(_node_short_name(note_node))
            self._emit_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not change text note color: {0}".format(exc)
            self._emit_status(message, False)
            return False, message

    def move_scene_text_note_to_selection(self, note_node):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not note_node or not cmds.objExists(note_node):
            return False, "Pick a scene text note first."
        note_node = _long_scene_name(note_node)
        anchor_node = _selected_scene_text_anchor(exclude_note=note_node)
        if not anchor_node:
            return False, "Select a body part or control to move the text note beside."
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersMoveTextNote")
        except Exception:
            pass
        try:
            note_position = _vector_add(_world_transform_position(anchor_node), SCENE_TEXT_NOTE_OFFSET)
            cmds.xform(note_node, worldSpace=True, translation=note_position)
            _ensure_string_attr(note_node, SCENE_TEXT_NOTE_ANCHOR_ATTR, anchor_node)
            _rebuild_scene_text_note_line(note_node)
            message = "Moved {0} beside {1}.".format(_node_short_name(note_node), _node_short_name(anchor_node))
            self._emit_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not move scene text note: {0}".format(exc)
            self._emit_status(message, False)
            return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    def delete_scene_text_note(self, note_node):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not note_node or not cmds.objExists(note_node):
            return False, "Pick a scene text note first."
        note_node = _long_scene_name(note_node)
        try:
            cmds.undoInfo(openChunk=True, chunkName="SceneHelpersDeleteTextNote")
        except Exception:
            pass
        try:
            note_name = _node_short_name(note_node)
            line_node = ""
            try:
                line_node = cmds.getAttr(note_node + "." + SCENE_TEXT_NOTE_LINE_ATTR) or ""
            except Exception:
                line_node = ""
            if line_node and cmds.objExists(line_node):
                try:
                    cmds.delete(line_node)
                except Exception:
                    pass
            control_node = _scene_text_note_wrap_box_control(note_node)
            if control_node:
                _kill_script_jobs_with_marker("{0}:{1}".format(SCENE_TEXT_NOTE_WRAP_BOX_JOB_MARKER, control_node))
                if cmds.objExists(control_node):
                    try:
                        cmds.delete(control_node)
                    except Exception:
                        pass
            cmds.delete(note_node)
            message = "Deleted scene text note: {0}.".format(note_name)
            self._emit_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not delete scene text note: {0}".format(exc)
            self._emit_status(message, False)
            return False, message
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

    def set_scene_helpers_camera_offsets(self, height_offset=None, dolly_offset=None):
        if height_offset is not None:
            self.scene_helpers_camera_height_offset = float(height_offset)
        if dolly_offset is not None:
            self.scene_helpers_camera_dolly_offset = float(dolly_offset)
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not cmds.objExists(SCENE_HELPERS_RENDER_ROOT_NAME):
            return True, "Camera offsets saved. Build the render environment to apply them."
        camera_map_payload = ""
        try:
            camera_map_payload = cmds.getAttr(SCENE_HELPERS_RENDER_ROOT_NAME + "." + SCENE_HELPERS_CAMERA_MAP_ATTR)
        except Exception:
            camera_map_payload = ""
        try:
            camera_map = json.loads(camera_map_payload or "{}")
        except Exception:
            camera_map = {}
        height_span = 1.0
        camera_distance = 1.0
        try:
            height_span = float(cmds.getAttr(SCENE_HELPERS_RENDER_ROOT_NAME + "." + SCENE_HELPERS_HEIGHT_SPAN_ATTR))
        except Exception:
            pass
        try:
            camera_distance = float(cmds.getAttr(SCENE_HELPERS_RENDER_ROOT_NAME + "." + SCENE_HELPERS_CAMERA_DISTANCE_ATTR))
        except Exception:
            pass
        try:
            center_payload = cmds.getAttr(SCENE_HELPERS_RENDER_ROOT_NAME + "." + "sceneHelpersCenter")
            center = json.loads(center_payload or "[0,0,0]")
        except Exception:
            center = [0.0, 0.0, 0.0]
        success, message = _apply_scene_helpers_camera_offsets(
            SCENE_HELPERS_RENDER_ROOT_NAME,
            center,
            height_span,
            camera_distance,
            self.scene_helpers_camera_height_offset,
            self.scene_helpers_camera_dolly_offset,
        )
        if success:
            message = "Updated helper cameras: up/down {0:.2f}, in/out {1:.2f}.".format(
                self.scene_helpers_camera_height_offset,
                self.scene_helpers_camera_dolly_offset,
            )
        self._emit_status(message, success)
        return success, message

    def activate_scene_camera_preset(self, preset_key):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        normalized_key = (preset_key or "").strip().lower().replace(" ", "_").replace("-", "_")
        success, message = _apply_scene_helpers_camera_preset(normalized_key)
        if success and (normalized_key in SCENE_HELPERS_CAMERA_NAMES or normalized_key == "perspective"):
            self.last_render_camera_preset = normalized_key
        self._emit_status(message, success)
        return success, message


if QtWidgets:
    _WindowBase = type("MayaTimingToolsWindowBase", (QtWidgets.QDialog,), {})

    class HotkeyCaptureLineEdit(QtWidgets.QLineEdit):
        def __init__(self, default_hotkey="", parent=None):
            super(HotkeyCaptureLineEdit, self).__init__(parent)
            self.default_hotkey = default_hotkey or ""
            self.setPlaceholderText("Click, then press a key")
            self.setToolTip("Click this field and press the hotkey you want. You can also type names like Backquote, N, #, or Ctrl+Semicolon.")

        def focusInEvent(self, event):
            super(HotkeyCaptureLineEdit, self).focusInEvent(event)
            try:
                self.selectAll()
            except Exception:
                pass

        def keyPressEvent(self, event):
            captured = _hotkey_name_from_qt_event(event)
            if captured:
                self.setText(captured)
                try:
                    self.selectAll()
                except Exception:
                    pass
                event.accept()
                return
            super(HotkeyCaptureLineEdit, self).keyPressEvent(event)

    class StudentTimelineButtonPopup(QtWidgets.QDialog):
        def __init__(self, controller, status_callback=None, parent=None):
            super(StudentTimelineButtonPopup, self).__init__(parent)
            self.controller = controller
            self.status_callback = status_callback
            self._tween_machine_popup = None
            self.setObjectName(STUDENT_CORE_TEMP_POPUP_OBJECT)
            self.setWindowTitle("Toolkit Buttons")
            flags = _qt_flag("WindowType", "Tool", QtCore.Qt.Tool)
            frameless = _qt_flag("WindowType", "FramelessWindowHint", QtCore.Qt.FramelessWindowHint)
            try:
                self.setWindowFlags(flags | frameless)
            except Exception:
                pass
            self._build_ui()

        def _build_ui(self):
            self.setStyleSheet(
                """
                QDialog#studentCoreTimelineTempButtons {
                    background-color: #2A2A2A;
                    border: 1px solid #454545;
                    border-radius: 6px;
                }
                QLabel {
                    color: #D8D8D8;
                }
                """
            )
            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(6)
            label = QtWidgets.QLabel("Timeline")
            label.setStyleSheet("font-weight: 600;")
            layout.addWidget(label)
            for tool in STUDENT_CORE_TOOLS:
                button = QtWidgets.QToolButton()
                button.setObjectName("studentCoreTemp_{0}".format(tool["command"]))
                button.setText(tool["label"])
                icon = _make_action_icon(tool)
                button.setIcon(icon)
                button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
                entry = _apply_manifest_button_metadata(button, tool["command"], icon=icon)
                button.setToolTip((entry or tool).get("tooltip") or tool["tooltip"])
                _style_student_core_button(button, tool["color"])
                _install_toolkit_hover_card(
                    button,
                    (entry or tool).get("display_name") or tool["label"],
                    (entry or tool).get("purpose") or tool["tooltip"],
                    owner=self,
                    accent=(entry or tool).get("accent") or tool["color"],
                    help_text=(entry or tool).get("help") or "",
                    shortcut=(entry or tool).get("shortcut") or "",
                    shortcut_help=(entry or tool).get("shortcut_help") or "",
                )
                button.clicked.connect(lambda _checked=False, command=tool["command"]: self._run(command))
                layout.addWidget(button)
            close_button = QtWidgets.QToolButton()
            close_button.setText("x")
            close_button.setToolTip("Hide these temporary timeline buttons.")
            close_button.clicked.connect(self.hide)
            close_button.setStyleSheet(
                """
                QToolButton {
                    background-color: #3A3A3A;
                    color: #E0E0E0;
                    border: 1px solid #555555;
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-weight: 700;
                }
                QToolButton:hover { background-color: #4A4A4A; }
                """
            )
            layout.addWidget(close_button)

        def _run(self, command):
            if (command or "").strip().lower() == "tween_machine":
                _show_tween_machine_popup(self.controller, self.status_callback, parent=self, anchor=self)
                return
            if (command or "").strip().lower() == "export_selected_animation_fbx":
                success, message = self.controller.export_selected_animation_fbx_from_bar(parent=self)
                if self.status_callback:
                    self.status_callback(message, success)
                return
            success, message = self.controller.run_student_core_command(command)
            if self.status_callback:
                self.status_callback(message, success)


    def _position_popup_near_cursor(popup):
        if not popup or not QtCore or not QtGui:
            return
        try:
            popup.adjustSize()
        except Exception:
            pass
        cursor_pos = QtGui.QCursor.pos()
        popup_width = max(popup.width(), popup.sizeHint().width(), 420)
        popup_height = max(popup.height(), popup.sizeHint().height(), 70)
        x_pos = cursor_pos.x() + 16
        y_pos = cursor_pos.y() + 16
        screen = None
        try:
            screen = QtWidgets.QApplication.screenAt(cursor_pos)
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = QtWidgets.QApplication.primaryScreen()
            except Exception:
                screen = None
        if screen is not None:
            try:
                available = screen.availableGeometry()
                if x_pos + popup_width > available.right():
                    x_pos = cursor_pos.x() - popup_width - 16
                if y_pos + popup_height > available.bottom():
                    y_pos = cursor_pos.y() - popup_height - 16
                x_pos = min(max(available.left(), x_pos), max(available.left(), available.right() - popup_width))
                y_pos = min(max(available.top(), y_pos), max(available.top(), available.bottom() - popup_height))
            except Exception:
                pass
        popup.move(int(x_pos), int(y_pos))


    class TweenMachinePopup(QtWidgets.QDialog):
        def __init__(self, controller, status_callback=None, post_apply_callback=None, parent=None):
            super(TweenMachinePopup, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.status_callback = status_callback
            self.post_apply_callback = post_apply_callback
            self.context = self.controller.build_tween_machine_context()
            self._last_applied_value = None
            self.setObjectName("toolkitBarTweenMachinePopup")
            self.setWindowTitle("Tween Machine")
            flags = _qt_flag("WindowType", "Tool", QtCore.Qt.Tool)
            try:
                self.setWindowFlags(flags)
            except Exception:
                pass
            try:
                self.setSizeGripEnabled(True)
            except Exception:
                pass
            try:
                self.setWindowOpacity(getattr(self.controller, "tween_machine_opacity", DEFAULT_TWEEN_MACHINE_OPACITY))
            except Exception:
                pass
            self._apply_timer = QtCore.QTimer(self)
            self._apply_timer.setSingleShot(True)
            self._apply_timer.setInterval(45)
            self._apply_timer.timeout.connect(lambda: self._apply_current_value(create_history=False))
            self._build_ui()

        def _build_ui(self):
            self.setStyleSheet(
                """
                QDialog#toolkitBarTweenMachinePopup {
                    background-color: #202020;
                    color: #F2F2F2;
                    border: 1px solid #4A4A4A;
                    border-radius: 8px;
                }
                QFrame#tweenMachineHeader {
                    background-color: #303030;
                    border-radius: 6px;
                }
                QLabel#tweenMachineHeaderTitle {
                    color: #FFFFFF;
                    font-size: 12px;
                    font-weight: 800;
                }
                QLabel#tweenMachineTitle {
                    color: #F2F2F2;
                    font-size: 24px;
                    font-weight: 700;
                }
                QLabel#tweenMachinePercentLabel {
                    color: #F2F2F2;
                    font-size: 24px;
                    font-weight: 700;
                }
                QLabel#tweenMachineValueLabel {
                    color: #4CC9F0;
                    font-size: 12px;
                    font-weight: 800;
                }
                QSlider::groove:horizontal {
                    height: 5px;
                    background-color: #111111;
                    border: 1px solid #555555;
                    border-radius: 3px;
                }
                QSlider::sub-page:horizontal {
                    background-color: #244E55;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background-color: #4CC9F0;
                    border: 1px solid #BDEFFF;
                    width: 8px;
                    height: 30px;
                    margin: -14px 0;
                    border-radius: 4px;
                }
                QToolButton#tweenMachineTick {
                    background-color: #4CC9F0;
                    border: 1px solid #83DDF7;
                    border-radius: 2px;
                    min-width: 5px;
                    max-width: 5px;
                    min-height: 26px;
                    max-height: 26px;
                    padding: 0px;
                }
                QToolButton#tweenMachineTick:hover {
                    background-color: #FFFFFF;
                    border-color: #4CC9F0;
                }
                QPushButton#tweenMachineCloseButton {
                    background-color: #333333;
                    color: #F2F2F2;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 2px 6px;
                    min-width: 24px;
                    max-width: 24px;
                }
                QPushButton#tweenMachineCloseButton:hover {
                    background-color: #3A3A3A;
                    border-color: #4CC9F0;
                }
                QSizeGrip {
                    width: 12px;
                    height: 12px;
                    background-color: transparent;
                }
                """
            )
            self.setMinimumSize(260, 92)
            self.resize(360, 118)
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(7, 7, 7, 7)
            layout.setSpacing(5)
            header_frame = QtWidgets.QFrame()
            header_frame.setObjectName("tweenMachineHeader")
            header_layout = QtWidgets.QHBoxLayout(header_frame)
            header_layout.setContentsMargins(6, 3, 6, 3)
            header_layout.setSpacing(5)
            header_title = QtWidgets.QLabel("Tween Machine")
            header_title.setObjectName("tweenMachineHeaderTitle")
            header_layout.addWidget(header_title, 1)
            self.value_label = QtWidgets.QLabel("50%")
            self.value_label.setObjectName("tweenMachineValueLabel")
            self.value_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            header_layout.addWidget(self.value_label)
            close_button = QtWidgets.QPushButton("X")
            close_button.setObjectName("tweenMachineCloseButton")
            close_button.setToolTip("Close Tween Machine.")
            close_button.clicked.connect(self.hide)
            header_layout.addWidget(close_button)
            layout.addWidget(header_frame)
            header = QtWidgets.QHBoxLayout()
            header.setSpacing(7)
            title = QtWidgets.QLabel("0%")
            title.setObjectName("tweenMachineTitle")
            header.addWidget(title)

            self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            self.slider.setObjectName("toolkitBarTweenMachineSlider")
            self.slider.setRange(0, 100)
            self.slider.setValue(50)
            self.slider.setTickPosition(QtWidgets.QSlider.NoTicks)
            self.slider.setToolTip("0% matches the previous key, 100% matches the next key, 50% is halfway.")
            slider_stack = QtWidgets.QWidget()
            slider_stack.setMinimumWidth(160)
            slider_stack.setMinimumHeight(40)
            slider_stack.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            slider_layout = QtWidgets.QVBoxLayout(slider_stack)
            slider_layout.setContentsMargins(0, 0, 0, 0)
            slider_layout.setSpacing(3)
            ticks = QtWidgets.QHBoxLayout()
            ticks.setContentsMargins(0, 0, 0, 0)
            ticks.setSpacing(0)
            for value in range(0, 101, 10):
                button = QtWidgets.QToolButton()
                button.setObjectName("tweenMachineTick")
                button.setToolTip("{0}%".format(value))
                button.clicked.connect(lambda _checked=False, slider_value=value: self._set_slider_value(slider_value))
                ticks.addStretch(1)
                ticks.addWidget(button)
            ticks.addStretch(1)
            slider_layout.addLayout(ticks)
            slider_layout.addWidget(self.slider)
            header.addWidget(slider_stack, 1)

            self.percent_label = QtWidgets.QLabel("100%")
            self.percent_label.setObjectName("tweenMachinePercentLabel")
            header.addWidget(self.percent_label)
            layout.addLayout(header)

            self.slider.valueChanged.connect(self._slider_changed)
            self.slider.sliderReleased.connect(lambda: self._apply_current_value(create_history=True))
            if not self.context.get("valid"):
                self.setToolTip(self.context.get("message") or "Select animated controls and move between two keys.")
            else:
                self.setToolTip("Drag the blue marker or click a tick to key the current frame between the previous and next keys.")

        def _set_slider_value(self, value):
            self.slider.setValue(int(value))
            self._apply_current_value(create_history=True)

        def _slider_changed(self, value):
            self.slider.setToolTip("{0}%".format(int(value)))
            self.value_label.setText("{0}%".format(int(value)))
            self._apply_timer.start()

        def _apply_current_value(self, create_history=True):
            if self._apply_timer.isActive():
                self._apply_timer.stop()
            if self._last_applied_value == self.slider.value() and not create_history:
                return
            self._last_applied_value = self.slider.value()
            success, message = self.controller.apply_tween_machine(
                self.slider.value(),
                context=self.context,
                key=bool(create_history),
            )
            self.setToolTip(message)
            if self.status_callback:
                self.status_callback(message, success)
            if create_history and self.post_apply_callback:
                self.post_apply_callback(success)


    def _show_tween_machine_popup(controller, status_callback=None, parent=None, post_apply_callback=None, anchor=None):
        global _TWEEN_MACHINE_POPUP
        existing = None
        if parent is not None:
            existing = getattr(parent, "_tween_machine_popup", None)
        if existing is None:
            existing = _TWEEN_MACHINE_POPUP
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.hide()
                    return existing
            except Exception:
                pass
            try:
                _position_popup_near_cursor(existing)
                existing.show()
                existing.raise_()
                return existing
            except Exception:
                pass
        popup = TweenMachinePopup(
            controller,
            status_callback=status_callback,
            post_apply_callback=post_apply_callback,
            parent=parent,
        )
        _TWEEN_MACHINE_POPUP = popup
        if parent is not None:
            try:
                parent._tween_machine_popup = popup
            except Exception:
                pass
        _position_popup_near_cursor(popup)
        popup.show()
        try:
            popup.raise_()
        except Exception:
            pass
        return popup


    def show_tween_machine_popup_for_controller(controller, status_callback=None, post_apply_callback=None):
        return _show_tween_machine_popup(
            controller,
            status_callback=status_callback or getattr(controller, "status_callback", None),
            post_apply_callback=post_apply_callback,
        )


    class TweenMachineHotkeyManager(QtCore.QObject):
        def __init__(self, controller, hotkey_text=None, parent=None):
            super(TweenMachineHotkeyManager, self).__init__(parent)
            self.controller = controller
            self.hotkey_text = maya_floating_channel_box.normalize_hotkey(
                hotkey_text or DEFAULT_TWEEN_MACHINE_HOTKEY,
                default_value=DEFAULT_TWEEN_MACHINE_HOTKEY,
            )
            self.hotkey_parts = maya_floating_channel_box.hotkey_to_parts(self.hotkey_text)
            self.popup = None
            self._last_trigger_time = 0.0
            app = QtWidgets.QApplication.instance()
            if app:
                app.installEventFilter(self)

        def set_hotkey(self, hotkey_text):
            self.hotkey_text = maya_floating_channel_box.normalize_hotkey(
                hotkey_text,
                default_value=DEFAULT_TWEEN_MACHINE_HOTKEY,
            )
            self.hotkey_parts = maya_floating_channel_box.hotkey_to_parts(self.hotkey_text)

        def shutdown(self):
            global _TWEEN_MACHINE_POPUP
            app = QtWidgets.QApplication.instance()
            if app:
                try:
                    app.removeEventFilter(self)
                except Exception:
                    pass
            if _qt_object_valid(self.popup):
                try:
                    self.popup.hide()
                except Exception:
                    pass
            self.popup = None
            if _qt_object_valid(_TWEEN_MACHINE_POPUP):
                try:
                    _TWEEN_MACHINE_POPUP.hide()
                except Exception:
                    pass
            _TWEEN_MACHINE_POPUP = None

        def _event_matches(self, event):
            if event.type() != QtCore.QEvent.KeyPress:
                return False
            if hasattr(event, "isAutoRepeat") and event.isAutoRepeat():
                return False
            return maya_floating_channel_box.FloatingChannelBoxHotkeyManager._event_matches(self, event, self.hotkey_parts)

        def eventFilter(self, obj, event):
            try:
                maya_floating_channel_box._track_text_entry_focus(obj, event)
                if not self._event_matches(event):
                    return False
                if maya_floating_channel_box._has_text_entry_focus():
                    return False
                now = time.time()
                if now - self._last_trigger_time < 0.2:
                    return True
                self._last_trigger_time = now
                if self.popup and self.popup.isVisible():
                    self.popup.hide()
                    return True
                self.popup = _show_tween_machine_popup(
                    self.controller,
                    status_callback=getattr(self.controller, "status_callback", None),
                )
                return True
            except Exception:
                return False


    def install_tween_machine_hotkey(controller, hotkey_text=None):
        global _TWEEN_MACHINE_HOTKEY_MANAGER
        if not QtWidgets or not QtCore or controller is None:
            return None
        hotkey_text = maya_floating_channel_box.normalize_hotkey(
            hotkey_text or DEFAULT_TWEEN_MACHINE_HOTKEY,
            default_value=DEFAULT_TWEEN_MACHINE_HOTKEY,
        )
        if _TWEEN_MACHINE_HOTKEY_MANAGER is None or _TWEEN_MACHINE_HOTKEY_MANAGER.controller is not controller:
            if _TWEEN_MACHINE_HOTKEY_MANAGER is not None:
                try:
                    _TWEEN_MACHINE_HOTKEY_MANAGER.shutdown()
                except Exception:
                    pass
            _TWEEN_MACHINE_HOTKEY_MANAGER = TweenMachineHotkeyManager(controller, hotkey_text)
        else:
            _TWEEN_MACHINE_HOTKEY_MANAGER.set_hotkey(hotkey_text)
        return _TWEEN_MACHINE_HOTKEY_MANAGER


    def shutdown_tween_machine_hotkey(manager=None):
        global _TWEEN_MACHINE_HOTKEY_MANAGER
        target = manager or _TWEEN_MACHINE_HOTKEY_MANAGER
        if target is not None:
            try:
                target.shutdown()
            except Exception:
                pass
        if target is _TWEEN_MACHINE_HOTKEY_MANAGER:
            _TWEEN_MACHINE_HOTKEY_MANAGER = None


    class StudentCoreToolbarPanel(QtWidgets.QFrame):
        def __init__(self, controller, status_callback=None, parent=None):
            super(StudentCoreToolbarPanel, self).__init__(parent)
            self.controller = controller
            self.status_callback = status_callback
            self._temp_popup = None
            self._tween_machine_popup = None
            self.setObjectName("studentCoreToolbarPanel")
            self._build_ui()

        def _build_ui(self):
            self.setStyleSheet(
                """
                QFrame#studentCoreToolbarPanel {
                    background-color: #202020;
                    border: 1px solid #3A3A3A;
                    border-radius: 6px;
                }
                QLabel#studentCoreTitle {
                    color: #F0F0F0;
                    font-weight: 700;
                }
                QLabel#studentCoreHint {
                    color: #B8B8B8;
                }
                QFrame#studentCoreTimelineTrack {
                    background-color: #151515;
                    border: 1px solid #303030;
                    border-radius: 5px;
                }
                """
            )
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(10, 8, 10, 10)
            layout.setSpacing(8)

            header = QtWidgets.QHBoxLayout()
            title = QtWidgets.QLabel("Toolkit Bar")
            title.setObjectName("studentCoreTitle")
            header.addWidget(title)
            hint = QtWidgets.QLabel("Compact color buttons for the timing jobs students use most.")
            hint.setObjectName("studentCoreHint")
            hint.setWordWrap(True)
            header.addWidget(hint, 1)
            self.show_temp_button = QtWidgets.QPushButton("Show Embedded Toolkit Bar")
            self.show_temp_button.setText("Show Embedded Toolkit Bar")
            self.show_temp_button.setToolTip("Use the permanent Toolkit Bar embedded at the bottom of Aminate.")
            self.show_temp_button.clicked.connect(self._show_temporary_buttons)
            header.addWidget(self.show_temp_button)
            layout.addLayout(header)

            track = QtWidgets.QFrame()
            track.setObjectName("studentCoreTimelineTrack")
            track_layout = QtWidgets.QHBoxLayout(track)
            track_layout.setContentsMargins(8, 6, 8, 6)
            track_layout.setSpacing(6)
            for index, tool in enumerate(STUDENT_CORE_TOOLS):
                tick = QtWidgets.QLabel("|")
                tick.setStyleSheet("color: #4D4D4D;")
                tick.setAlignment(QtCore.Qt.AlignCenter)
                track_layout.addWidget(tick)
                button = QtWidgets.QToolButton()
                button.setObjectName("studentCoreTool_{0}".format(tool["command"]))
                button.setText(tool["label"])
                icon = _make_action_icon(tool)
                button.setIcon(icon)
                button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
                entry = _apply_manifest_button_metadata(button, tool["command"], icon=icon)
                button.setToolTip(
                    "{0}: {1}".format(
                        tool["group"],
                        (entry or tool).get("tooltip") or tool["tooltip"],
                    )
                )
                _style_student_core_button(button, tool["color"])
                _install_toolkit_hover_card(
                    button,
                    (entry or tool).get("display_name") or tool["label"],
                    (entry or tool).get("purpose") or tool["tooltip"],
                    owner=self,
                    accent=(entry or tool).get("accent") or tool["color"],
                    help_text=(entry or tool).get("help") or "",
                    shortcut=(entry or tool).get("shortcut") or "",
                    shortcut_help=(entry or tool).get("shortcut_help") or "",
                )
                button.clicked.connect(lambda _checked=False, command=tool["command"]: self._run(command))
                track_layout.addWidget(button)
            track_layout.addStretch(1)
            layout.addWidget(track)

        def _run(self, command):
            if (command or "").strip().lower() == "tween_machine":
                _show_tween_machine_popup(self.controller, self.status_callback, parent=self, anchor=self)
                return
            if (command or "").strip().lower() == "export_selected_animation_fbx":
                success, message = self.controller.export_selected_animation_fbx_from_bar(parent=self)
                if self.status_callback:
                    self.status_callback(message, success)
                return
            success, message = self.controller.run_student_core_command(command)
            if self.status_callback:
                self.status_callback(message, success)

        def _show_temporary_buttons(self):
            if self.status_callback:
                self.status_callback("Toolkit Bar is embedded at the bottom of Aminate.", True)


    class StudentTimelineButtonBarWindow(_WindowBase):
        def __init__(
            self,
            controller,
            status_callback=None,
            parent=None,
            owns_controller=False,
            embedded=False,
            start_history_watcher=False,
            start_layer_tint_timer=False,
            max_history_markers=18,
        ):
            base_parent = parent if parent is not None else (None if embedded else _maya_main_window())
            super(StudentTimelineButtonBarWindow, self).__init__(base_parent)
            self.controller = controller
            self.status_callback = status_callback
            self.owns_controller = bool(owns_controller)
            self.embedded = bool(embedded)
            self.start_history_watcher = bool(start_history_watcher)
            self.start_layer_tint_timer = bool(start_layer_tint_timer)
            self.max_history_markers = max(1, int(max_history_markers or 18))
            self.history_controller = maya_history_timeline.MayaHistoryTimelineController(status_callback=status_callback)
            self.setObjectName("studentCoreTimelineButtonBarEmbeddedPanel" if self.embedded else STUDENT_TIMELINE_BAR_OBJECT_NAME)
            self.setWindowTitle("" if not self.embedded else "Toolkit Bar")
            self._tween_machine_popup = None
            if self.embedded:
                try:
                    self.setWindowFlags(_qt_flag("WindowType", "Widget", 0))
                except Exception:
                    pass
                self.setMinimumSize(0, 92)
                self.setMaximumHeight(124)
            else:
                self.setMinimumSize(360, 92)
                self.setMaximumHeight(124)
            if hasattr(self, "setSizePolicy"):
                self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self._layer_tint_timer = None
            self._refreshing_animation_layer_controls = False
            self._workflow_buttons = {}
            self._workflow_button_group = QtWidgets.QButtonGroup(self)
            self._workflow_button_group.setExclusive(True)
            self._build_ui()
            _register_timeline_bar_widget(self)
            self.select_workflow_tab(CURRENT_WORKFLOW_TAB_ALIAS)
            if self.start_history_watcher:
                self.history_controller.start_default_action_snapshots(parent=self, interval_ms=2000)
            self._refresh_animation_layer_tint()
            if self.start_layer_tint_timer:
                self._start_animation_layer_tint_timer()

        def _make_horizontal_overflow_strip(self, layout, object_name, minimum_height, maximum_height):
            content = QtWidgets.QWidget(self)
            content.setObjectName(object_name + "Content")
            content.setLayout(layout)
            content.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
            content.setMinimumWidth(max(0, int(content.minimumSizeHint().width())))

            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName(object_name)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAsNeeded", QtCore.Qt.ScrollBarAsNeeded))
            scroll.setVerticalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAlwaysOff", QtCore.Qt.ScrollBarAlwaysOff))
            scroll.setMinimumHeight(int(minimum_height))
            scroll.setMaximumHeight(int(maximum_height))
            scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            scroll.setWidget(content)
            scroll.horizontalScrollBar().setSingleStep(38)
            return scroll

        def _build_ui(self):
            self.setStyleSheet(
                """
                QDialog#studentCoreTimelineButtonBarWindow,
                QDialog#studentCoreTimelineButtonBarEmbeddedPanel,
                QDialog#aminateFixedBottomToolkitBarPanel {
                    background-color: #2B2B2B;
                    border: 1px solid #3A3A3A;
                }
                QScrollArea#toolkitBarLayerScroll,
                QScrollArea#toolkitBarToolScroll,
                QWidget#toolkitBarLayerScrollContent,
                QWidget#toolkitBarToolScrollContent {
                    background-color: transparent;
                    border: 0px;
                }
                """
            )
            root_layout = QtWidgets.QHBoxLayout(self)
            root_layout.setContentsMargins(2, 2, 5, 3)
            root_layout.setSpacing(3)

            self.drag_grip = QtWidgets.QToolButton()
            self.drag_grip.setObjectName("toolkitBarDragGrip")
            self.drag_grip.setIcon(_make_student_core_icon("#6C757D", "drag"))
            self.drag_grip.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
            self.drag_grip.setToolTip("Toolkit Bar grip: available only in the explicit legacy native-dock diagnostic path.")
            self.drag_grip.setEnabled(not self.embedded)
            self.drag_grip.setVisible(not self.embedded)
            self.drag_grip.setCursor(_qt_cursor("SizeAllCursor") if not self.embedded else _qt_cursor("ArrowCursor"))
            self.drag_grip.setMinimumSize(18, 52)
            self.drag_grip.setMaximumSize(20, 60)
            self.drag_grip.setIconSize(QtCore.QSize(16, 16))
            self.drag_grip.setStyleSheet(
                """
                QToolButton#toolkitBarDragGrip {
                    background-color: #202020;
                    border: 1px solid #3A3A3A;
                    border-radius: 4px;
                    padding: 2px;
                }
                QToolButton#toolkitBarDragGrip:hover {
                    background-color: #2F2F2F;
                    border: 1px solid #6C757D;
                }
                QToolButton#toolkitBarDragGrip:pressed {
                    background-color: #6C757D;
                }
                QToolButton#toolkitBarDragGrip:disabled {
                    background-color: #202020;
                    border: 1px solid #3A3A3A;
                }
                """
            )
            self.drag_grip.clicked.connect(self._toggle_dock_float_from_grip)
            if not self.embedded:
                root_layout.addWidget(self.drag_grip)

            main_layout = QtWidgets.QVBoxLayout()
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(2)
            root_layout.addLayout(main_layout, 1)

            history_layout = QtWidgets.QHBoxLayout()
            history_layout.setContentsMargins(0, 0, 0, 0)
            history_layout.setSpacing(4)
            self.history_strip = maya_history_timeline.HistoryTimelineStrip(
                controller=self.history_controller,
                status_callback=self.status_callback,
                parent=self,
                max_markers=self.max_history_markers,
            )
            self.history_strip.setToolTip(
                "History Timeline: small ZBrush-style snapshot strip. Saves after Maya actions by default. Click H+ to save now, or click a block to restore."
            )
            self.history_strip.setMaximumHeight(22)
            history_layout.addWidget(self.history_strip)
            main_layout.addLayout(history_layout)

            layer_layout = QtWidgets.QHBoxLayout()
            layer_layout.setContentsMargins(0, 0, 0, 0)
            layer_layout.setSpacing(4)
            self.animation_layer_tint_label = QtWidgets.QToolButton()
            self.animation_layer_tint_label.setObjectName("studentTimelineBarAnimationLayerTint")
            self.animation_layer_tint_label.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            self.animation_layer_tint_label.setPopupMode(_tool_button_popup_mode("InstantPopup"))
            self.animation_layer_tint_label.setMinimumHeight(26)
            self.animation_layer_tint_label.setMaximumHeight(30)
            self.animation_layer_tint_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self.animation_layer_tint_label.setToolTip(
                "Animation Layer: spans the Toolkit Bar. Click to switch, add, delete, rename, recolor, mute, solo, lock, or change layer weight."
            )
            self.animation_layer_tint_menu = QtWidgets.QMenu(self.animation_layer_tint_label)
            self.animation_layer_tint_menu.aboutToShow.connect(self._refresh_animation_layer_menu)
            self.animation_layer_tint_label.setMenu(self.animation_layer_tint_menu)
            layer_layout.addWidget(self.animation_layer_tint_label, 8)

            self.add_animation_layer_button = self._make_layer_control_button(
                "toolkitBarAnimationLayerAddButton",
                "+Layer",
                "Create a new animation layer and make it current. Selected controls are added if any are selected.",
                "#55CBCD",
            )
            self.delete_animation_layer_button = self._make_layer_control_button(
                "toolkitBarAnimationLayerDeleteButton",
                "Delete",
                "Delete the current animation layer after a confirmation prompt.",
                "#EF6F6C",
            )
            self.add_selected_to_layer_button = self._make_layer_control_button(
                "toolkitBarAnimationLayerAddSelectedButton",
                "+Sel",
                "Add selected controls to the current animation layer.",
                "#7BD88F",
            )
            self.remove_selected_from_layer_button = self._make_layer_control_button(
                "toolkitBarAnimationLayerRemoveSelectedButton",
                "-Sel",
                "Remove selected controls from the current animation layer.",
                "#F6C85F",
            )
            self.mute_animation_layer_button = self._make_layer_control_button(
                "toolkitBarAnimationLayerMuteButton",
                "Mute",
                "Toggle mute on the current animation layer.",
                "#A0A0A0",
                checkable=True,
            )
            self.solo_animation_layer_button = self._make_layer_control_button(
                "toolkitBarAnimationLayerSoloButton",
                "Solo",
                "Toggle solo on the current animation layer.",
                "#72B7F2",
                checkable=True,
            )
            self.lock_animation_layer_button = self._make_layer_control_button(
                "toolkitBarAnimationLayerLockButton",
                "Lock",
                "Toggle lock on the current animation layer.",
                "#B86BFF",
                checkable=True,
            )
            self.animation_layer_weight_spin = QtWidgets.QDoubleSpinBox()
            self.animation_layer_weight_spin.setObjectName("toolkitBarAnimationLayerWeightSpin")
            self.animation_layer_weight_spin.setRange(0.0, 1.0)
            self.animation_layer_weight_spin.setSingleStep(0.05)
            self.animation_layer_weight_spin.setDecimals(2)
            self.animation_layer_weight_spin.setToolTip("Set the current animation layer weight from 0 to 1.")
            self.animation_layer_weight_spin.setMinimumWidth(58)
            self.animation_layer_weight_spin.setMaximumWidth(70)
            self.animation_layer_weight_spin.setMaximumHeight(28)
            self.animation_layer_weight_spin.setStyleSheet(
                """
                QDoubleSpinBox {
                    background-color: #202020;
                    color: #F2F2F2;
                    border: 1px solid #3A3A3A;
                    border-radius: 4px;
                    padding: 1px 4px;
                    font-size: 10px;
                    font-weight: 700;
                }
                QDoubleSpinBox:disabled {
                    color: #777777;
                    background-color: #242424;
                }
                """
            )
            for layer_button in (
                self.add_animation_layer_button,
                self.delete_animation_layer_button,
                self.add_selected_to_layer_button,
                self.remove_selected_from_layer_button,
                self.mute_animation_layer_button,
                self.solo_animation_layer_button,
                self.lock_animation_layer_button,
            ):
                layer_layout.addWidget(layer_button)
            layer_layout.addWidget(self.animation_layer_weight_spin)
            self.layer_scroll = self._make_horizontal_overflow_strip(
                layer_layout,
                "toolkitBarLayerScroll",
                31,
                43,
            )
            main_layout.addWidget(self.layer_scroll)

            self.add_animation_layer_button.clicked.connect(self._create_animation_layer_from_bar)
            self.delete_animation_layer_button.clicked.connect(self._delete_current_animation_layer_from_bar)
            self.add_selected_to_layer_button.clicked.connect(lambda _checked=False: self._edit_selected_on_current_layer(True))
            self.remove_selected_from_layer_button.clicked.connect(lambda _checked=False: self._edit_selected_on_current_layer(False))
            self.mute_animation_layer_button.toggled.connect(lambda checked: self._toggle_current_animation_layer_flag("mute", checked))
            self.solo_animation_layer_button.toggled.connect(lambda checked: self._toggle_current_animation_layer_flag("solo", checked))
            self.lock_animation_layer_button.toggled.connect(lambda checked: self._toggle_current_animation_layer_flag("lock", checked))
            self.animation_layer_weight_spin.valueChanged.connect(self._set_current_animation_layer_weight)

            layout = QtWidgets.QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(3)
            for tool in STUDENT_CORE_TOOLS:
                button = QtWidgets.QToolButton()
                button.setObjectName("studentTimelineBar_{0}".format(tool["command"]))
                icon = _make_action_icon(tool)
                button.setIcon(icon)
                button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
                entry = _apply_manifest_button_metadata(button, tool["command"], icon=icon)
                button.setToolTip(
                    "{0}: {1}".format(
                        tool["label"],
                        (entry or tool).get("tooltip") or tool["tooltip"],
                    )
                )
                _style_student_timeline_bar_button(button, tool["color"])
                _install_toolkit_hover_card(
                    button,
                    (entry or tool).get("display_name") or tool["label"],
                    (entry or tool).get("purpose") or tool["tooltip"],
                    owner=self,
                    icon=icon,
                    accent=(entry or tool).get("accent") or tool["color"],
                    help_text=(entry or tool).get("help") or "",
                    shortcut=(entry or tool).get("shortcut") or "",
                    shortcut_help=(entry or tool).get("shortcut_help") or "",
                )
                if self.embedded:
                    button.setIconSize(QtCore.QSize(24, 24))
                    button.setMinimumSize(34, 32)
                    button.setMaximumSize(38, 34)
                button.clicked.connect(lambda _checked=False, command=tool["command"]: self._run(command))
                layout.addWidget(button)
            separator = QtWidgets.QFrame()
            separator.setObjectName("studentTimelineBarSeparator")
            separator.setFrameShape(QtWidgets.QFrame.VLine)
            separator.setStyleSheet("color: #4A4A4A;")
            layout.addWidget(separator)
            # Read the manifest when the bar is built. A long-lived Maya session
            # may refresh the manifest module without reloading this UI module.
            for tool in maya_aminate_icon_manifest.workflow_toolbar_tools():
                button = QtWidgets.QToolButton()
                button.setObjectName("studentTimelineBar_{0}".format(tool["command"]))
                workflow_icon = _make_workflow_icon(tool)
                button.setIcon(workflow_icon)
                button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
                entry = _apply_manifest_button_metadata(
                    button,
                    tool["command"],
                    icon=workflow_icon,
                )
                button.setToolTip("{0}: {1}".format(tool["label"], tool["tooltip"]))
                button.setCheckable(True)
                button.setProperty("_aminateWorkflowTab", tool["tab"])
                button.setProperty("_aminateHoverAccent", tool["color"])
                button.setProperty("_aminateHoverHelp", tool.get("help") or "")
                button.setProperty("_aminateHoverShortcut", tool.get("shortcut") or "")
                button.setProperty("_aminateHoverShortcutHelp", tool.get("shortcut_help") or "")
                try:
                    button.setFocusPolicy(_qt_flag("FocusPolicy", "StrongFocus", QtCore.Qt.StrongFocus))
                except Exception:
                    pass
                _style_student_timeline_bar_button(button, tool["color"])
                _install_toolkit_hover_card(
                    button,
                    (entry or tool).get("display_name") or tool["label"],
                    (entry or tool).get("purpose") or tool["tooltip"],
                    owner=self,
                    icon=workflow_icon,
                    accent=(entry or tool).get("accent") or tool["color"],
                    help_text=(entry or tool).get("help") or "",
                    shortcut=(entry or tool).get("shortcut") or "",
                    shortcut_help=(entry or tool).get("shortcut_help") or "",
                )
                if self.embedded:
                    button.setIconSize(QtCore.QSize(24, 24))
                    button.setMinimumSize(34, 32)
                    button.setMaximumSize(38, 34)
                button.toggled.connect(
                    lambda checked, target=button, accent=tool["color"]: _set_workflow_button_glow(target, checked, accent)
                )
                button.clicked.connect(lambda _checked=False, tab=tool["tab"]: self._open_workflow_tab(tab))
                self._workflow_button_group.addButton(button)
                self._workflow_buttons[tool["tab"]] = button
                layout.addWidget(button)
            layout.addStretch(1)
            self.game_mode_button = QtWidgets.QToolButton()
            self.game_mode_button.setObjectName("toolkitBarGameAnimationModeButton")
            self.game_mode_button.setCheckable(True)
            self.game_mode_button.setChecked(bool(getattr(self.controller, "game_animation_mode_enabled", False)))
            game_entry = maya_aminate_icon_manifest.icon_entry(command="game_animation_mode") or {}
            game_icon = _make_action_icon(game_entry)
            self.game_mode_button.setIcon(game_icon)
            self.game_mode_button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
            _apply_manifest_button_metadata(self.game_mode_button, "game_animation_mode", icon=game_icon)
            self.game_mode_button.setToolTip(
                "{0}: {1} {2}".format(
                    game_entry.get("display_name") or "Game Animation Mode",
                    game_entry.get("purpose") or "Apply game animation settings.",
                    game_entry.get("help") or "",
                ).strip()
            )
            _style_toolkit_game_mode_button(self.game_mode_button, game_entry.get("accent") or "#176BFF")
            _install_toolkit_hover_card(
                self.game_mode_button,
                game_entry.get("display_name") or "Game Animation Mode",
                game_entry.get("purpose") or "Apply game animation settings.",
                owner=self,
                icon=self.game_mode_button.icon(),
                accent=game_entry.get("accent") or "#176BFF",
                help_text=game_entry.get("help") or "",
                shortcut=game_entry.get("shortcut") or "",
                shortcut_help=game_entry.get("shortcut_help") or "",
            )
            if self.embedded:
                self.game_mode_button.setIconSize(QtCore.QSize(24, 24))
                self.game_mode_button.setMinimumSize(36, 32)
                self.game_mode_button.setMaximumSize(40, 34)
            self.game_mode_button.toggled.connect(self._toggle_game_animation_mode)
            layout.addWidget(self.game_mode_button)
            self.tool_scroll = self._make_horizontal_overflow_strip(
                layout,
                "toolkitBarToolScroll",
                36,
                48,
            )
            main_layout.addWidget(self.tool_scroll)
            self._apply_large_hover_help()

        def _toggle_dock_float_from_grip(self):
            if not MAYA_AVAILABLE or not cmds:
                return
            workspace = STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME
            if not _timeline_bar_workspace_exists():
                if self.status_callback:
                    self.status_callback("Toolkit Bar workspace is not available. Open Toolkit Bar again to let Maya create a fresh bottom dock.", True)
                return
            docked, message = _dock_timeline_bar_workspace("bottom")
            if self.status_callback:
                self.status_callback(message, docked)

        def _apply_large_hover_help(self, force=False):
            if not QtWidgets:
                return
            for button in self.findChildren(QtWidgets.QToolButton):
                try:
                    if bool(button.property("_aminateLargeTooltip")) and not force:
                        continue
                    object_name = button.objectName() or ""
                    command_or_name = button.property("_aminateIconCommand") or object_name
                    if object_name.startswith("studentTimelineBar_"):
                        command_or_name = button.property("_aminateIconCommand") or object_name.replace(
                            "studentTimelineBar_", "", 1
                        )
                    raw_tooltip = button.toolTip() or button.text() or object_name
                    title = _toolkit_title_for(command_or_name, raw_tooltip, button.text() or object_name or "Tool")
                    description = _toolkit_help_description(command_or_name, raw_tooltip)
                    tool_entry = maya_aminate_icon_manifest.icon_entry(command=command_or_name) or {}
                    icon = None
                    try:
                        icon = button.icon()
                        if icon.isNull():
                            glyph_text = re.sub(r"[^A-Za-z0-9]", "", title)[:2] or "?"
                            icon = _make_student_core_icon("#6C757D", glyph_text)
                    except Exception:
                        icon = None
                    _install_toolkit_hover_card(
                        button,
                        title,
                        tool_entry.get("purpose") or description,
                        owner=self,
                        icon=icon,
                        accent=tool_entry.get("accent") or button.property("_aminateHoverAccent") or "#56D7E8",
                        help_text=tool_entry.get("help") or button.property("_aminateHoverHelp") or "",
                        shortcut=tool_entry.get("shortcut") or button.property("_aminateHoverShortcut") or "",
                        shortcut_help=tool_entry.get("shortcut_help") or button.property("_aminateHoverShortcutHelp") or "",
                    )
                except Exception:
                    continue

        def select_workflow_tab(self, tab_alias):
            tab_alias = str(tab_alias or "")
            button = self._workflow_buttons.get(tab_alias)
            if button is None:
                return False
            if not button.isChecked():
                button.setChecked(True)
            return True

        def _make_layer_control_button(self, object_name, text, tooltip, color_hex, checkable=False):
            button = QtWidgets.QToolButton()
            button.setObjectName(object_name)
            button.setText(text)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            button.setCheckable(bool(checkable))
            button.setToolTip(tooltip)
            _style_animation_layer_bar_button(button, color_hex)
            return button

        def _start_animation_layer_tint_timer(self):
            if not QtCore:
                return
            self._layer_tint_timer = QtCore.QTimer(self)
            self._layer_tint_timer.setInterval(1000)
            self._layer_tint_timer.timeout.connect(self._refresh_animation_layer_tint)
            self._layer_tint_timer.start()

        def _refresh_animation_layer_tint(self):
            if not getattr(self, "animation_layer_tint_label", None):
                return
            try:
                info = self.controller.animation_layer_tint_info()
            except Exception:
                info = {"enabled": False, "label": "Animation Layer Tint", "color": "#3A3A3A"}
            color_hex = info.get("color") or "#3A3A3A"
            label = info.get("label") or "Base Animation"
            if info.get("enabled"):
                text = "Animation Layer: {0}".format(label)
                text_color = "#F6F6F6"
                border_color = color_hex
            else:
                text = str(label)
                text_color = "#A8A8A8"
                border_color = "#4A4A4A"
            state = self.controller.animation_layer_state(info.get("layer") or "")
            display_signature = (
                bool(info.get("enabled")),
                info.get("layer") or "",
                text,
                color_hex,
                text_color,
                border_color,
                bool(state.get("can_edit")),
                bool(state.get("mute")),
                bool(state.get("solo")),
                bool(state.get("lock")),
                float(state.get("weight", 1.0)),
            )
            if getattr(self, "_last_animation_layer_display_signature", None) == display_signature:
                return
            self._last_animation_layer_display_signature = display_signature
            self.animation_layer_tint_label.setText(text)
            self.animation_layer_tint_label.setStyleSheet(
                """
                QToolButton#studentTimelineBarAnimationLayerTint {{
                    background-color: {color};
                    color: {text_color};
                    border: 1px solid {border_color};
                    border-radius: 5px;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 2px 10px;
                }}
                QToolButton#studentTimelineBarAnimationLayerTint::menu-indicator {{
                    width: 0px;
                }}
                """.format(color=color_hex, text_color=text_color, border_color=border_color)
            )
            self._refresh_animation_layer_controls(info, state=state)

        def _refresh_animation_layer_controls(self, info=None, state=None):
            info = info or self.controller.animation_layer_tint_info()
            layer_name = info.get("layer") or ""
            state = state or self.controller.animation_layer_state(layer_name)
            can_edit = bool(state.get("can_edit"))
            self._refreshing_animation_layer_controls = True
            try:
                for button in (
                    self.delete_animation_layer_button,
                    self.add_selected_to_layer_button,
                    self.remove_selected_from_layer_button,
                    self.mute_animation_layer_button,
                    self.solo_animation_layer_button,
                    self.lock_animation_layer_button,
                ):
                    button.setEnabled(can_edit)
                self.mute_animation_layer_button.setChecked(bool(state.get("mute")))
                self.solo_animation_layer_button.setChecked(bool(state.get("solo")))
                self.lock_animation_layer_button.setChecked(bool(state.get("lock")))
                self.animation_layer_weight_spin.setEnabled(can_edit)
                self.animation_layer_weight_spin.setValue(float(state.get("weight", 1.0)))
            finally:
                self._refreshing_animation_layer_controls = False

        def _refresh_animation_layer_menu(self):
            if not getattr(self, "animation_layer_tint_menu", None):
                return
            self.animation_layer_tint_menu.clear()
            title_action = self.animation_layer_tint_menu.addAction("Change Animation Layer")
            title_action.setEnabled(False)
            for choice in self.controller.animation_layer_choices():
                action = self.animation_layer_tint_menu.addAction(
                    _make_student_core_icon(choice.get("color") or "#4A4A4A", "bars"),
                    choice.get("label") or "Base Animation",
                )
                action.setCheckable(True)
                action.setChecked(bool(choice.get("active")))
                action.triggered.connect(lambda _checked=False, layer=choice.get("layer", ""): self._select_animation_layer_from_bar(layer))
            self.animation_layer_tint_menu.addSeparator()
            add_action = self.animation_layer_tint_menu.addAction("Create New Layer")
            add_action.triggered.connect(self._create_animation_layer_from_bar)
            delete_action = self.animation_layer_tint_menu.addAction("Delete Current Layer...")
            delete_action.triggered.connect(self._delete_current_animation_layer_from_bar)
            self.animation_layer_tint_menu.addSeparator()
            add_selected_action = self.animation_layer_tint_menu.addAction("Add Selected Controls To Current Layer")
            add_selected_action.triggered.connect(lambda _checked=False: self._edit_selected_on_current_layer(True))
            remove_selected_action = self.animation_layer_tint_menu.addAction("Remove Selected Controls From Current Layer")
            remove_selected_action.triggered.connect(lambda _checked=False: self._edit_selected_on_current_layer(False))
            self.animation_layer_tint_menu.addSeparator()
            rename_action = self.animation_layer_tint_menu.addAction("Rename Current Layer...")
            rename_action.triggered.connect(self._rename_current_animation_layer_from_bar)
            color_action = self.animation_layer_tint_menu.addAction("Auto Set Current Layer Color")
            color_action.triggered.connect(self._auto_set_current_animation_layer_color_from_bar)

        def _select_animation_layer_from_bar(self, layer_name):
            success, message = self.controller.select_animation_layer_from_bar(layer_name)
            self._snapshot_after_toolkit_action("animation layer select", success)
            self._refresh_animation_layer_tint()
            if self.status_callback:
                self.status_callback(message, success)

        def _rename_current_animation_layer_from_bar(self):
            info = self.controller.animation_layer_tint_info()
            layer_name = info.get("layer") or ""
            if not layer_name:
                if self.status_callback:
                    self.status_callback("Pick an animation layer before renaming.", False)
                return
            current_name = info.get("label") or _short_name(layer_name)
            new_name, accepted = QtWidgets.QInputDialog.getText(
                self,
                "Rename Animation Layer",
                "New layer name:",
                QtWidgets.QLineEdit.Normal,
                current_name,
            )
            if not accepted:
                return
            success, message, _renamed = self.controller.rename_animation_layer_from_bar(layer_name, new_name)
            self._snapshot_after_toolkit_action("animation layer rename", success)
            self._refresh_animation_layer_tint()
            if self.status_callback:
                self.status_callback(message, success)

        def _auto_set_current_animation_layer_color_from_bar(self):
            info = self.controller.animation_layer_tint_info()
            layer_name = info.get("layer") or ""
            if not layer_name:
                if self.status_callback:
                    self.status_callback("Pick an animation layer before setting color.", False)
                return
            color_hex = _next_animation_layer_palette_color(layer_name)
            success, message = self.controller.color_animation_layer_from_bar(layer_name, color_hex)
            self._snapshot_after_toolkit_action("animation layer color", success)
            self._refresh_animation_layer_tint()
            if self.status_callback:
                self.status_callback(message, success)

        def _create_animation_layer_from_bar(self):
            success, message, _created = self.controller.create_animation_layer_from_bar()
            self._snapshot_after_toolkit_action("animation layer create", success)
            self._refresh_animation_layer_tint()
            if self.status_callback:
                self.status_callback(message, success)

        def _delete_current_animation_layer_from_bar(self):
            info = self.controller.animation_layer_tint_info()
            layer_name = info.get("layer") or ""
            if not layer_name:
                if self.status_callback:
                    self.status_callback("Pick an animation layer before deleting.", False)
                return
            result = QtWidgets.QMessageBox.question(
                self,
                "Delete Animation Layer",
                "Delete animation layer {0}? This removes that animation layer from the scene.".format(_short_name(layer_name)),
            )
            if result != QtWidgets.QMessageBox.Yes:
                return
            success, message = self.controller.delete_animation_layer_from_bar(layer_name)
            self._snapshot_after_toolkit_action("animation layer delete", success)
            self._refresh_animation_layer_tint()
            if self.status_callback:
                self.status_callback(message, success)

        def _edit_selected_on_current_layer(self, add=True):
            info = self.controller.animation_layer_tint_info()
            layer_name = info.get("layer") or ""
            success, message = self.controller.edit_selected_objects_on_animation_layer_from_bar(layer_name, add=add)
            self._snapshot_after_toolkit_action("animation layer membership", success)
            self._refresh_animation_layer_tint()
            if self.status_callback:
                self.status_callback(message, success)

        def _toggle_current_animation_layer_flag(self, flag_name, enabled):
            if getattr(self, "_refreshing_animation_layer_controls", False):
                return
            info = self.controller.animation_layer_tint_info()
            layer_name = info.get("layer") or ""
            success, message = self.controller.set_animation_layer_flag_from_bar(layer_name, flag_name, enabled)
            self._snapshot_after_toolkit_action("animation layer {0}".format(flag_name), success)
            self._refresh_animation_layer_tint()
            if self.status_callback:
                self.status_callback(message, success)

        def _set_current_animation_layer_weight(self, weight):
            if getattr(self, "_refreshing_animation_layer_controls", False):
                return
            info = self.controller.animation_layer_tint_info()
            layer_name = info.get("layer") or ""
            success, message = self.controller.set_animation_layer_weight_from_bar(layer_name, weight)
            self._snapshot_after_toolkit_action("animation layer weight", success)
            self._refresh_animation_layer_tint()
            if self.status_callback:
                self.status_callback(message, success)

        def _run(self, command):
            if (command or "").strip().lower() == "tween_machine":
                _show_tween_machine_popup(
                    self.controller,
                    self.status_callback,
                    parent=self,
                    post_apply_callback=lambda success: self._snapshot_after_toolkit_action("tween machine", success),
                    anchor=self,
                )
                return
            if (command or "").strip().lower() == "export_selected_animation_fbx":
                success, message = self.controller.export_selected_animation_fbx_from_bar(parent=self)
                self._snapshot_after_toolkit_action(command, success)
                if self.status_callback:
                    self.status_callback(message, success)
                elif MAYA_AVAILABLE and om2:
                    if success:
                        om2.MGlobal.displayInfo("[Toolkit Bar] {0}".format(message))
                    else:
                        om2.MGlobal.displayWarning("[Toolkit Bar] {0}".format(message))
                return
            success, message = self.controller.run_student_core_command(command)
            self._snapshot_after_toolkit_action(command, success)
            if self.status_callback:
                self.status_callback(message, success)
            elif MAYA_AVAILABLE and om2:
                if success:
                    om2.MGlobal.displayInfo("[Toolkit Bar] {0}".format(message))
                else:
                    om2.MGlobal.displayWarning("[Toolkit Bar] {0}".format(message))

        def _set_game_button_checked(self, enabled):
            if not getattr(self, "game_mode_button", None):
                return
            self.game_mode_button.blockSignals(True)
            self.game_mode_button.setChecked(bool(enabled))
            self.game_mode_button.blockSignals(False)
            _set_game_mode_button_glow(self.game_mode_button, bool(enabled))

        def _toggle_game_animation_mode(self, enabled):
            success, message = self.controller.set_game_animation_mode_enabled(enabled, parent=self)
            self._snapshot_after_toolkit_action("game animation mode", success)
            self._set_game_button_checked(bool(getattr(self.controller, "game_animation_mode_enabled", False)))
            self._sync_game_mode_buttons()
            if self.status_callback:
                self.status_callback(message, success)
            elif MAYA_AVAILABLE and om2:
                if success:
                    om2.MGlobal.displayInfo("[Toolkit Bar] {0}".format(message))
                else:
                    om2.MGlobal.displayWarning("[Toolkit Bar] {0}".format(message))

        def _snapshot_after_toolkit_action(self, reason, action_success):
            if not action_success or not getattr(self, "history_controller", None):
                return
            success, message, _record = self.history_controller.create_post_action_snapshot(reason)
            if getattr(self, "history_strip", None):
                self.history_strip._set_status(message, success)
                self.history_strip.refresh()

        def _sync_game_mode_buttons(self):
            _sync_timeline_bar_game_buttons(self.controller)

        def _open_workflow_tab(self, tab_alias):
            success, message = _open_workflow_tab(tab_alias)
            if self.status_callback:
                self.status_callback(message, success)
            elif MAYA_AVAILABLE and om2:
                if success:
                    om2.MGlobal.displayInfo("[Toolkit Bar] {0}".format(message))
                else:
                    om2.MGlobal.displayWarning("[Toolkit Bar] {0}".format(message))

        def closeEvent(self, event):
            try:
                self.hide()
            except Exception:
                pass
            try:
                event.ignore()
            except Exception:
                pass


    class MayaTimingToolsWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaTimingToolsWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.set_status_callback(self._set_status)
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Scene Helpers")
            self.setMinimumSize(360, 480)
            if hasattr(self, "setSizePolicy"):
                self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self._build_ui()
            self._sync_from_controller()

        def _build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.setContentsMargins(12, 12, 12, 12)
            main_layout.setSpacing(10)

            section_scroll = QtWidgets.QScrollArea()
            section_scroll.setObjectName("sceneHelpersSectionScroll")
            section_scroll.setWidgetResizable(True)
            section_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            section_content = QtWidgets.QWidget()
            section_content.setObjectName("sceneHelpersSectionContent")
            section_content_layout = QtWidgets.QVBoxLayout(section_content)
            section_content_layout.setContentsMargins(0, 0, 0, 0)
            section_content_layout.setSpacing(10)
            blocking_page = QtWidgets.QWidget()
            scene_setup_page = QtWidgets.QWidget()
            notes_page = QtWidgets.QWidget()
            help_page = QtWidgets.QWidget()
            for page in (blocking_page, scene_setup_page, notes_page):
                page.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
            help_page.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
            blocking_layout = QtWidgets.QVBoxLayout(blocking_page)
            scene_setup_layout = QtWidgets.QVBoxLayout(scene_setup_page)
            notes_layout = QtWidgets.QVBoxLayout(notes_page)
            help_layout = QtWidgets.QVBoxLayout(help_page)
            for page_layout in (blocking_layout, scene_setup_layout, notes_layout, help_layout):
                page_layout.setContentsMargins(8, 8, 8, 8)
                page_layout.setSpacing(10)
            section_groups = (
                ("Blocking & Timing", blocking_page, "Keying, blocking poses, timing helpers, and animation utility controls."),
                ("Scene Setup", scene_setup_page, "Auto Key, scene setup, render cameras, game mode, and teacher demo tools."),
                ("Scene Notes", notes_page, "Create, resize, key, move, style, and delete scene text notes."),
                ("Help", help_page, "Short descriptions for each Scene Helpers workflow."),
            )
            for title, page, tooltip in section_groups:
                group = QtWidgets.QGroupBox(title)
                group.setToolTip(tooltip)
                group.setSizePolicy(
                    QtWidgets.QSizePolicy.Preferred,
                    QtWidgets.QSizePolicy.Expanding if title == "Help" else QtWidgets.QSizePolicy.Maximum,
                )
                group_layout = QtWidgets.QVBoxLayout(group)
                group_layout.setContentsMargins(4, 4, 4, 4)
                group_layout.addWidget(page)
                section_content_layout.addWidget(group, 1 if title == "Help" else 0)
            section_scroll.setWidget(section_content)
            main_layout.addWidget(section_scroll, 1)

            action_row = QtWidgets.QHBoxLayout()
            action_row.setSpacing(8)
            self.auto_key_button = QtWidgets.QToolButton()
            self.auto_key_button.setCheckable(True)
            self.auto_key_button.setChecked(self.controller.auto_key_enabled)
            self.auto_key_button.setText("Auto Key")
            self.auto_key_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            self.auto_key_button.setIcon(_make_key_icon())
            self.auto_key_button.setToolTip(
                "Toggle Maya's Auto Key button on or off. Use this when you want Maya to key changes as you move controls."
            )
            action_row.addWidget(self.auto_key_button, 1)

            self.auto_snap_button = QtWidgets.QToolButton()
            self.auto_snap_button.setCheckable(True)
            self.auto_snap_button.setChecked(self.controller.auto_snap_enabled)
            self.auto_snap_button.setText("Auto Snap To Frames")
            self.auto_snap_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            self.auto_snap_button.setIcon(_make_snap_icon())
            self.auto_snap_button.setToolTip(
                "Keep keyframes snapped to whole frames when the time unit changes. "
                "When this is on, the tool watches for a frame-rate change and snaps the current controls or "
                "keyed scene controls into whole frames."
            )
            action_row.addWidget(self.auto_snap_button, 1)

            self.load_textures_button = QtWidgets.QPushButton("Load Textures")
            self.load_textures_button.setToolTip(
                "Reload scene texture nodes and try to fix broken texture paths from the current Maya project "
                "folders like sourceimages, textures, and images."
            )
            action_row.addWidget(self.load_textures_button, 1)
            self.recover_autosave_button = QtWidgets.QPushButton("Open Last Autosave")
            self.recover_autosave_button.setToolTip(
                "Open the latest autosave for the current scene, or recover the last crash if Maya closed unexpectedly."
            )
            action_row.addWidget(self.recover_autosave_button, 1)
            self.disable_security_popups_button = QtWidgets.QPushButton("Disable Maya Security Popups")
            self.disable_security_popups_button.setObjectName("sceneHelpersDisableSecurityPopupsButton")
            self.disable_security_popups_button.setToolTip(
                "Turn off Maya Safe Mode / Trust Center popup checks for trusted classroom rigs that repeatedly block scene load and History Timeline restore. Only use this for rigs you trust."
            )
            action_row.addWidget(self.disable_security_popups_button, 1)
            scene_setup_layout.addLayout(action_row)

            self.game_mode_group = QtWidgets.QGroupBox("Game Animation Mode")
            self.game_mode_group.setObjectName("sceneHelpersGameAnimationModeGroup")
            game_mode_layout = QtWidgets.QVBoxLayout(self.game_mode_group)
            game_mode_layout.setContentsMargins(10, 8, 10, 8)
            game_mode_layout.setSpacing(6)
            game_mode_top_row = QtWidgets.QHBoxLayout()
            game_mode_top_row.setSpacing(8)
            self.game_mode_button = QtWidgets.QToolButton()
            self.game_mode_button.setObjectName("sceneHelpersGameAnimationModeButton")
            self.game_mode_button.setCheckable(True)
            self.game_mode_button.setChecked(bool(getattr(self.controller, "game_animation_mode_enabled", False)))
            self.game_mode_button.setText("Game Animation Mode")
            scene_game_entry = maya_aminate_icon_manifest.icon_entry(command="game_animation_mode") or {}
            scene_game_icon = _make_action_icon(scene_game_entry)
            self.game_mode_button.setIcon(scene_game_icon)
            self.game_mode_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            _apply_manifest_button_metadata(self.game_mode_button, "game_animation_mode", icon=scene_game_icon)
            _style_toolkit_game_mode_button(self.game_mode_button, scene_game_entry.get("accent") or "#176BFF")
            self.game_mode_button.setToolTip(
                "{0}: {1} {2}".format(
                    scene_game_entry.get("display_name") or "Game Animation Mode",
                    scene_game_entry.get("purpose") or "Apply game animation settings.",
                    scene_game_entry.get("help") or "",
                ).strip()
            )
            game_mode_top_row.addWidget(self.game_mode_button, 0)
            game_mode_hint = QtWidgets.QLabel("Choose exactly what the blue game button applies to this scene.")
            game_mode_hint.setWordWrap(True)
            game_mode_top_row.addWidget(game_mode_hint, 1)
            game_mode_layout.addLayout(game_mode_top_row)
            game_mode_checks = QtWidgets.QGridLayout()
            game_mode_checks.setHorizontalSpacing(12)
            game_mode_checks.setVerticalSpacing(4)
            self.game_mode_action_checks = {}
            action_settings = getattr(self.controller, "game_animation_mode_actions", _game_animation_mode_action_settings())
            for index, (action_key, action_info) in enumerate(GAME_ANIMATION_MODE_ACTIONS.items()):
                action_label, action_tooltip = action_info
                checkbox = QtWidgets.QCheckBox(action_label)
                checkbox.setObjectName("sceneHelpersGameModeOption_{0}".format(action_key))
                checkbox.setChecked(bool(action_settings.get(action_key, True)))
                checkbox.setToolTip(action_tooltip)
                self.game_mode_action_checks[action_key] = checkbox
                game_mode_checks.addWidget(checkbox, index // 3, index % 3)
            game_mode_layout.addLayout(game_mode_checks)
            scene_setup_layout.addWidget(self.game_mode_group)

            setup_row = QtWidgets.QHBoxLayout()
            setup_row.setSpacing(8)
            self.render_env_button = QtWidgets.QPushButton("Set Up Render Environment")
            self.render_env_button.setProperty("aminateRole", "primary")
            self.render_env_button.setToolTip(
                "Build a first-pass render setup around the selected character or largest visible mesh. "
                "The tool builds the cyclorama helper directly in Python, then adds front, side, and three-quarter cameras, a sky dome when Arnold is available, and camera bookmarks."
            )
            setup_row.addWidget(self.render_env_button, 1)
            self.delete_render_env_button = QtWidgets.QPushButton("Delete Render Environment")
            self.delete_render_env_button.setProperty("aminateRole", "danger")
            self.delete_render_env_button.setToolTip("Delete the Scene Helpers render environment, including the cameras, cyclorama, sky light, and bookmarks.")
            setup_row.addWidget(self.delete_render_env_button, 1)
            self.duplicate_teacher_rig_button = QtWidgets.QPushButton("Duplicate Rig For Teacher Demo")
            self.duplicate_teacher_rig_button.setObjectName("sceneHelpersDuplicateTeacherRigButton")
            self.duplicate_teacher_rig_button.setToolTip(
                "Select one rig root group, then duplicate an isolated teacher-demo copy with the same keyed animation. "
                "The copy is moved by an offset group so the original keyframes are not changed."
            )
            setup_row.addWidget(self.duplicate_teacher_rig_button, 1)
            self.delete_teacher_rig_button = QtWidgets.QPushButton("Delete Teacher Demo")
            self.delete_teacher_rig_button.setProperty("aminateRole", "danger")
            self.delete_teacher_rig_button.setObjectName("sceneHelpersDeleteTeacherRigButton")
            self.delete_teacher_rig_button.setToolTip(
                "Delete every teacher-demo rig duplicate and its helper display layer from this scene."
            )
            setup_row.addWidget(self.delete_teacher_rig_button, 1)
            scene_setup_layout.addLayout(setup_row)

            teacher_log_group = QtWidgets.QGroupBox("Teacher Demo Edit Log")
            teacher_log_group.setObjectName("sceneHelpersTeacherDemoEditLogGroup")
            teacher_log_layout = QtWidgets.QVBoxLayout(teacher_log_group)
            teacher_log_layout.setContentsMargins(10, 8, 10, 8)
            teacher_log_layout.setSpacing(6)
            self.teacher_demo_edit_log = QtWidgets.QPlainTextEdit()
            self.teacher_demo_edit_log.setObjectName("sceneHelpersTeacherDemoEditLog")
            self.teacher_demo_edit_log.setReadOnly(True)
            self.teacher_demo_edit_log.setMaximumHeight(130)
            self.teacher_demo_edit_log.setPlaceholderText("Duplicate a rig for teacher demo, then edit the duplicate. Changes appear here as student-readable bullet points.")
            self.teacher_demo_edit_log.setToolTip(
                "Plain-English list of edits made to the teacher-demo duplicate. If an edit is undone back to its original value, the bullet disappears."
            )
            teacher_log_layout.addWidget(self.teacher_demo_edit_log)
            teacher_log_buttons = QtWidgets.QHBoxLayout()
            teacher_log_buttons.setSpacing(8)
            self.refresh_teacher_demo_log_button = QtWidgets.QPushButton("Refresh Edit Log")
            self.refresh_teacher_demo_log_button.setObjectName("sceneHelpersRefreshTeacherDemoLogButton")
            self.refresh_teacher_demo_log_button.setToolTip("Refresh the teacher-demo edit list from the current duplicate rig values.")
            self.reset_teacher_demo_log_button = QtWidgets.QPushButton("Reset Log From Current Pose")
            self.reset_teacher_demo_log_button.setObjectName("sceneHelpersResetTeacherDemoLogButton")
            self.reset_teacher_demo_log_button.setToolTip("Clear the current list and treat the current teacher-demo duplicate pose as the new starting point.")
            teacher_log_buttons.addWidget(self.refresh_teacher_demo_log_button, 1)
            teacher_log_buttons.addWidget(self.reset_teacher_demo_log_button, 1)
            teacher_log_layout.addLayout(teacher_log_buttons)
            scene_setup_layout.addWidget(teacher_log_group)

            camera_row = QtWidgets.QHBoxLayout()
            camera_row.setSpacing(8)
            camera_row.addWidget(QtWidgets.QLabel("Camera Preset"))
            self.render_preset_combo = QtWidgets.QComboBox()
            self.render_preset_combo.setObjectName("sceneHelpersCameraPresetCombo")
            for preset_key, preset_label in SCENE_HELPERS_CAMERA_PRESET_LABELS.items():
                self.render_preset_combo.addItem(preset_label, preset_key)
            self.render_preset_combo.setToolTip("Pick which helper camera to show in the viewport.")
            camera_row.addWidget(self.render_preset_combo, 1)
            self.render_preset_button = QtWidgets.QPushButton("Switch View")
            self.render_preset_button.setObjectName("sceneHelpersCameraPresetButton")
            self.render_preset_button.setToolTip("Switch the active viewport to the selected helper camera preset.")
            camera_row.addWidget(self.render_preset_button)
            scene_setup_layout.addLayout(camera_row)

            offset_row = QtWidgets.QHBoxLayout()
            offset_row.setSpacing(8)
            offset_row.addWidget(QtWidgets.QLabel("Camera Height Offset"))
            self.camera_height_offset_spin = QtWidgets.QDoubleSpinBox()
            self.camera_height_offset_spin.setObjectName("sceneHelpersCameraHeightOffsetSpin")
            self.camera_height_offset_spin.setRange(-100.0, 100.0)
            self.camera_height_offset_spin.setDecimals(2)
            self.camera_height_offset_spin.setSingleStep(0.25)
            self.camera_height_offset_spin.setToolTip("Move all helper cameras up or down together.")
            offset_row.addWidget(self.camera_height_offset_spin)
            offset_row.addWidget(QtWidgets.QLabel("Camera Dolly Offset"))
            self.camera_dolly_offset_spin = QtWidgets.QDoubleSpinBox()
            self.camera_dolly_offset_spin.setObjectName("sceneHelpersCameraDollyOffsetSpin")
            self.camera_dolly_offset_spin.setRange(-100.0, 100.0)
            self.camera_dolly_offset_spin.setDecimals(2)
            self.camera_dolly_offset_spin.setSingleStep(0.25)
            self.camera_dolly_offset_spin.setToolTip("Move the helper cameras closer or farther in their view direction.")
            offset_row.addWidget(self.camera_dolly_offset_spin)
            offset_row.addWidget(QtWidgets.QLabel("Rig Copy Offset X"))
            self.teacher_rig_offset_spin = QtWidgets.QDoubleSpinBox()
            self.teacher_rig_offset_spin.setObjectName("sceneHelpersTeacherRigOffsetSpin")
            self.teacher_rig_offset_spin.setRange(-1000.0, 1000.0)
            self.teacher_rig_offset_spin.setDecimals(2)
            self.teacher_rig_offset_spin.setSingleStep(5.0)
            self.teacher_rig_offset_spin.setValue(DEFAULT_TEACHER_RIG_DUPLICATE_OFFSET_X)
            self.teacher_rig_offset_spin.setToolTip("Move the duplicated teacher-demo rig left or right without changing its own animation keys.")
            offset_row.addWidget(self.teacher_rig_offset_spin)
            scene_setup_layout.addLayout(offset_row)

            snap_row = QtWidgets.QHBoxLayout()
            snap_row.setSpacing(8)
            self.snap_now_button = QtWidgets.QPushButton("Snap Selected Keys To Frames")
            self.snap_now_button.setProperty("aminateRole", "primary")
            self.snap_now_button.setToolTip(
                "Snap the currently selected controls to whole frames right now. If nothing is selected, the tool "
                "snaps the keyed controls it can find in the scene."
            )
            snap_row.addWidget(self.snap_now_button, 1)
            self.key_blocking_poses_button = QtWidgets.QPushButton("Key Full Blocking Poses")
            self.key_blocking_poses_button.setProperty("aminateRole", "primary")
            self.key_blocking_poses_button.setObjectName("sceneHelpersKeyFullBlockingPosesButton")
            self.key_blocking_poses_button.setToolTip(
                "For selected controls, find every keyed frame on any selected control, then key selected channel groups on every selected control at those frames."
            )
            snap_row.addWidget(self.key_blocking_poses_button, 1)
            retime_row = QtWidgets.QHBoxLayout()
            retime_row.setSpacing(8)
            retime_row.addWidget(QtWidgets.QLabel("Retime Every"))
            self.retime_every_n_spin = QtWidgets.QSpinBox()
            self.retime_every_n_spin.setObjectName("sceneHelpersRetimeEveryNSpin")
            self.retime_every_n_spin.setRange(1, 100)
            self.retime_every_n_spin.setValue(5)
            self.retime_every_n_spin.setSuffix(" frames")
            self.retime_every_n_spin.setToolTip("Choose the spacing used by Retime To Every N Frames. Keys snap to the nearest multiple of this value.")
            retime_row.addWidget(self.retime_every_n_spin)
            self.retime_every_n_button = QtWidgets.QPushButton("Retime To Every N Frames")
            self.retime_every_n_button.setProperty("aminateRole", "primary")
            self.retime_every_n_button.setObjectName("sceneHelpersRetimeEveryNButton")
            self.retime_every_n_button.setToolTip("Move all keys on the selected controls to the nearest Nth frame, then expand Maya's visible timeline to the resulting keyed range.")
            retime_row.addWidget(self.retime_every_n_button, 1)
            blocking_layout.addLayout(retime_row)

            self.animation_layer_tint_button = QtWidgets.QToolButton()
            self.animation_layer_tint_button.setObjectName("sceneHelpersAnimationLayerTintButton")
            self.animation_layer_tint_button.setCheckable(True)
            self.animation_layer_tint_button.setText("Animation Layer Tint")
            self.animation_layer_tint_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            self.animation_layer_tint_button.setIcon(_make_student_core_icon("#55CBCD", "bars"))
            self.animation_layer_tint_button.setToolTip(
                "Show a colored strip above Maya's timeline using the current selected animation layer name and color."
            )
            self.keep_toolbar_extras_on_hide_check = QtWidgets.QCheckBox("Keep Toolbar Extras On Aminate Hide")
            self.keep_toolbar_extras_on_hide_check.setObjectName("sceneHelpersKeepToolbarExtrasOnHideCheck")
            self.keep_toolbar_extras_on_hide_check.setToolTip(
                "When this is off, hiding or closing Aminate also hides the docked Toolkit Bar, Tween Machine popup, Floating Channel Box, and Floating Graph Editor."
            )
            self.refresh_layer_tint_button = QtWidgets.QPushButton("Refresh Layer Tint")
            self.refresh_layer_tint_button.setObjectName("sceneHelpersRefreshLayerTintButton")
            self.refresh_layer_tint_button.setToolTip("Refresh the docked timeline layer tint strip after changing animation layers.")
            blocking_layout.addLayout(snap_row)

            layer_row = QtWidgets.QHBoxLayout()
            layer_row.setSpacing(8)
            layer_row.addWidget(self.animation_layer_tint_button, 1)
            layer_row.addWidget(self.keep_toolbar_extras_on_hide_check, 1)
            layer_row.addWidget(self.refresh_layer_tint_button, 1)
            blocking_layout.addLayout(layer_row)

            animation_layers_group = QtWidgets.QGroupBox("Animation Layers")
            animation_layers_group.setObjectName("sceneHelpersAnimationLayersGroup")
            animation_layers_layout = QtWidgets.QGridLayout(animation_layers_group)
            animation_layers_layout.setContentsMargins(10, 8, 10, 10)
            animation_layers_layout.setHorizontalSpacing(8)
            animation_layers_layout.setVerticalSpacing(8)
            self.duplicate_current_layer_button = QtWidgets.QPushButton("Duplicate Current Layer")
            self.duplicate_current_layer_button.setProperty("aminateRole", "primary")
            self.duplicate_current_layer_button.setObjectName("sceneHelpersDuplicateCurrentLayerButton")
            self.duplicate_current_layer_button.setToolTip("Copy every attribute and animation curve from the selected animation layer into a new layer. The source layer stays unchanged.")
            animation_layers_layout.addWidget(self.duplicate_current_layer_button, 0, 0)
            self.consolidate_other_layers_button = QtWidgets.QPushButton("Consolidate Other Layers")
            self.consolidate_other_layers_button.setProperty("aminateRole", "primary")
            self.consolidate_other_layers_button.setObjectName("sceneHelpersConsolidateOtherLayersButton")
            self.consolidate_other_layers_button.setToolTip("Bake every non-current animation layer into one new muted layer. Original layers stay unchanged so the scene does not double the animation.")
            animation_layers_layout.addWidget(self.consolidate_other_layers_button, 0, 1)
            self.solo_current_layer_button = QtWidgets.QPushButton("Solo Current Layer")
            self.solo_current_layer_button.setObjectName("sceneHelpersSoloCurrentLayerButton")
            self.solo_current_layer_button.setCheckable(True)
            self.solo_current_layer_button.setToolTip("Solo the animation layer selected in the Animation Layer Tint control. Click again to remove solo.")
            animation_layers_layout.addWidget(self.solo_current_layer_button, 1, 0)
            self.clear_layer_solos_button = QtWidgets.QPushButton("Clear All Layer Solos")
            self.clear_layer_solos_button.setObjectName("sceneHelpersClearLayerSolosButton")
            self.clear_layer_solos_button.setToolTip("Turn Solo off for every non-base animation layer.")
            animation_layers_layout.addWidget(self.clear_layer_solos_button, 1, 1)
            blocking_layout.addWidget(animation_layers_group)

            blocking_options_row = QtWidgets.QHBoxLayout()
            blocking_options_row.setSpacing(8)
            blocking_options_row.addWidget(QtWidgets.QLabel("Blocking Pose Channels"))
            self.key_blocking_translation_check = QtWidgets.QCheckBox("Translation")
            self.key_blocking_translation_check.setObjectName("sceneHelpersKeyBlockingTranslationCheck")
            self.key_blocking_translation_check.setChecked(True)
            self.key_blocking_translation_check.setToolTip("Key translate X, Y, and Z on every shared keyed frame.")
            blocking_options_row.addWidget(self.key_blocking_translation_check)
            self.key_blocking_rotation_check = QtWidgets.QCheckBox("Rotation")
            self.key_blocking_rotation_check.setObjectName("sceneHelpersKeyBlockingRotationCheck")
            self.key_blocking_rotation_check.setChecked(True)
            self.key_blocking_rotation_check.setToolTip("Key rotate X, Y, and Z on every shared keyed frame.")
            blocking_options_row.addWidget(self.key_blocking_rotation_check)
            self.key_blocking_other_check = QtWidgets.QCheckBox("Other keyable attributes")
            self.key_blocking_other_check.setObjectName("sceneHelpersKeyBlockingOtherCheck")
            self.key_blocking_other_check.setChecked(False)
            self.key_blocking_other_check.setToolTip("Include scale, visibility, and unlocked custom keyable attributes.")
            blocking_options_row.addWidget(self.key_blocking_other_check)
            blocking_options_row.addStretch(1)
            blocking_layout.addLayout(blocking_options_row)

            tween_machine_row = QtWidgets.QHBoxLayout()
            tween_machine_row.setSpacing(8)
            tween_machine_row.addWidget(QtWidgets.QLabel("Tween Machine Hotkey"))
            self.tween_machine_hotkey_edit = HotkeyCaptureLineEdit(DEFAULT_TWEEN_MACHINE_HOTKEY)
            self.tween_machine_hotkey_edit.setObjectName("sceneHelpersTweenMachineHotkeyEdit")
            self.tween_machine_hotkey_edit.setText(getattr(self.controller, "tween_machine_hotkey", DEFAULT_TWEEN_MACHINE_HOTKEY))
            self.tween_machine_hotkey_edit.setToolTip("Press a collision-free hotkey, then press Enter or leave the field to save automatically.")
            tween_machine_row.addWidget(self.tween_machine_hotkey_edit, 1)
            tween_machine_row.addWidget(QtWidgets.QLabel("Opacity"))
            self.tween_machine_opacity_spin = QtWidgets.QDoubleSpinBox()
            self.tween_machine_opacity_spin.setObjectName("sceneHelpersTweenMachineOpacitySpin")
            self.tween_machine_opacity_spin.setRange(0.2, 1.0)
            self.tween_machine_opacity_spin.setDecimals(2)
            self.tween_machine_opacity_spin.setSingleStep(0.05)
            self.tween_machine_opacity_spin.setValue(getattr(self.controller, "tween_machine_opacity", DEFAULT_TWEEN_MACHINE_OPACITY))
            self.tween_machine_opacity_spin.setToolTip("Transparency for the Tween Machine popup. Lower is more see-through.")
            tween_machine_row.addWidget(self.tween_machine_opacity_spin)
            self.set_tween_machine_hotkey_button = QtWidgets.QPushButton("Set Hotkey")
            self.set_tween_machine_hotkey_button.setObjectName("sceneHelpersSetTweenMachineHotkeyButton")
            self.set_tween_machine_hotkey_button.setToolTip("Save the custom hotkey for Tween Machine.")
            self.set_tween_machine_hotkey_button.setVisible(False)
            tween_machine_row.addWidget(self.set_tween_machine_hotkey_button)
            self.open_tween_machine_button = QtWidgets.QPushButton("Open Tween Machine")
            self.open_tween_machine_button.setObjectName("sceneHelpersOpenTweenMachineButton")
            self.open_tween_machine_button.setToolTip("Open the translucent inbetween popup next to the cursor.")
            tween_machine_row.addWidget(self.open_tween_machine_button)
            blocking_layout.addLayout(tween_machine_row)

            floating_channel_row = QtWidgets.QHBoxLayout()
            floating_channel_row.setSpacing(8)
            floating_channel_row.addWidget(QtWidgets.QLabel("Floating Channel Box Hotkey"))
            self.floating_channel_hotkey_edit = HotkeyCaptureLineEdit(maya_floating_channel_box.DEFAULT_HOTKEY)
            self.floating_channel_hotkey_edit.setObjectName("sceneHelpersFloatingChannelHotkeyEdit")
            self.floating_channel_hotkey_edit.setText(getattr(self.controller, "floating_channel_box_hotkey", maya_floating_channel_box.DEFAULT_HOTKEY))
            self.floating_channel_hotkey_edit.setToolTip("Press a collision-free hotkey, then press Enter or leave the field to save automatically.")
            floating_channel_row.addWidget(self.floating_channel_hotkey_edit, 1)
            floating_channel_row.addWidget(QtWidgets.QLabel("Opacity"))
            self.floating_channel_opacity_spin = QtWidgets.QDoubleSpinBox()
            self.floating_channel_opacity_spin.setObjectName("sceneHelpersFloatingChannelOpacitySpin")
            self.floating_channel_opacity_spin.setRange(0.2, 1.0)
            self.floating_channel_opacity_spin.setDecimals(2)
            self.floating_channel_opacity_spin.setSingleStep(0.05)
            self.floating_channel_opacity_spin.setValue(getattr(self.controller, "floating_channel_box_opacity", maya_floating_channel_box.DEFAULT_CHANNEL_OPACITY))
            self.floating_channel_opacity_spin.setToolTip("Transparency for the Floating Channel Box. Lower is more see-through.")
            floating_channel_row.addWidget(self.floating_channel_opacity_spin)
            self.set_floating_channel_hotkey_button = QtWidgets.QPushButton("Set Hotkey")
            self.set_floating_channel_hotkey_button.setObjectName("sceneHelpersSetFloatingChannelHotkeyButton")
            self.set_floating_channel_hotkey_button.setToolTip("Save the custom hotkey for the Floating Channel Box.")
            self.set_floating_channel_hotkey_button.setVisible(False)
            floating_channel_row.addWidget(self.set_floating_channel_hotkey_button)
            self.open_floating_channel_box_button = QtWidgets.QPushButton("Open Floating Channel Box")
            self.open_floating_channel_box_button.setObjectName("sceneHelpersOpenFloatingChannelBoxButton")
            self.open_floating_channel_box_button.setToolTip("Open the semi-transparent floating channel editor for the current selection.")
            floating_channel_row.addWidget(self.open_floating_channel_box_button)
            blocking_layout.addLayout(floating_channel_row)

            floating_graph_row = QtWidgets.QHBoxLayout()
            floating_graph_row.setSpacing(8)
            floating_graph_row.addWidget(QtWidgets.QLabel("Floating Graph Editor Hotkey"))
            self.floating_graph_hotkey_edit = HotkeyCaptureLineEdit(maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_HOTKEY)
            self.floating_graph_hotkey_edit.setObjectName("sceneHelpersFloatingGraphHotkeyEdit")
            self.floating_graph_hotkey_edit.setText(getattr(self.controller, "floating_graph_editor_hotkey", maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_HOTKEY))
            self.floating_graph_hotkey_edit.setToolTip("Press a collision-free hotkey, then press Enter or leave the field to save automatically.")
            floating_graph_row.addWidget(self.floating_graph_hotkey_edit, 1)
            floating_graph_row.addWidget(QtWidgets.QLabel("Opacity"))
            self.floating_graph_opacity_spin = QtWidgets.QDoubleSpinBox()
            self.floating_graph_opacity_spin.setObjectName("sceneHelpersFloatingGraphOpacitySpin")
            self.floating_graph_opacity_spin.setRange(0.2, 1.0)
            self.floating_graph_opacity_spin.setDecimals(2)
            self.floating_graph_opacity_spin.setSingleStep(0.05)
            self.floating_graph_opacity_spin.setValue(getattr(self.controller, "floating_graph_editor_opacity", maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_OPACITY))
            self.floating_graph_opacity_spin.setToolTip("Transparency for the Floating Graph Editor. Lower is more see-through.")
            floating_graph_row.addWidget(self.floating_graph_opacity_spin)
            self.set_floating_graph_hotkey_button = QtWidgets.QPushButton("Set Hotkey")
            self.set_floating_graph_hotkey_button.setObjectName("sceneHelpersSetFloatingGraphHotkeyButton")
            self.set_floating_graph_hotkey_button.setToolTip("Save the custom hotkey for the Floating Graph Editor.")
            self.set_floating_graph_hotkey_button.setVisible(False)
            floating_graph_row.addWidget(self.set_floating_graph_hotkey_button)
            self.open_floating_graph_button = QtWidgets.QPushButton("Open Floating Graph Editor")
            self.open_floating_graph_button.setObjectName("sceneHelpersOpenFloatingGraphButton")
            self.open_floating_graph_button.setToolTip("Open a semi-transparent native Maya Graph Editor clone that can float or dock without creating duplicates.")
            floating_graph_row.addWidget(self.open_floating_graph_button)
            blocking_layout.addLayout(floating_graph_row)

            help_box = QtWidgets.QPlainTextEdit()
            help_box.setReadOnly(True)
            help_box.setPlainText(
                "1. Use Auto Key when you want Maya to key changes as you animate.\n"
                "2. Leave Auto Snap To Frames on if you want the tool to catch timing changes for you.\n"
                "3. If keys are already off-frame, click Snap Selected Keys To Frames.\n"
                "4. Leave Animation Layer Tint on if you want the bar above the timeline to show the current animation layer.\n"
                "5. Use Animation Layers to duplicate the current layer, consolidate every other layer into one muted copy, solo the current layer, or clear all solos.\n"
                "6. Click Load Textures when textures exist locally but Maya has not refreshed or repathed them yet.\n"
                "7. Click Open Last Autosave if Maya crashed and you want to jump straight back to the latest autosave.\n"
                "8. If you are setting up a student game shot, click Game Animation Mode.\n"
                "9. Use Set Up Render Environment to build the cyclorama helper, then add the cameras and sky light for the shot.\n"
                "10. Use Delete Render Environment when you want to remove that whole setup again.\n"
                "11. Use Camera Height Offset and Camera Dolly Offset to move all helper cameras up/down or in/out together.\n"
                "12. Use Camera Preset to jump between the Front, Side, and Three Quarter cameras.\n"
                "13. Select a rig root and use Duplicate Rig For Teacher Demo when you want a separate animated copy for a student demonstration.\n"
                "14. Use Delete Teacher Demo to remove every teacher-demo duplicate and its helper display layer.\n"
                "15. Tap Backquote (`) to open the Tween Machine beside the cursor, or change the hotkey here.\n"
                "16. Tap # to open the Floating Channel Box, or change the hotkey here.\n"
                "17. Use Floating Graph Editor for a translucent native Maya Graph Editor clone that you can dock into Maya.\n"
                "18. Select controls first when you want the snap to act only on part of the scene."
            )
            help_box.setMinimumHeight(140)
            help_box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            help_layout.addWidget(help_box, 1)

            text_note_label = QtWidgets.QLabel("Scene Text Notes")
            text_note_label.setStyleSheet("font-weight: 600;")
            notes_layout.addWidget(text_note_label)

            text_note_row = QtWidgets.QHBoxLayout()
            text_note_row.setSpacing(8)
            self.scene_text_input = QtWidgets.QLineEdit()
            self.scene_text_input.setObjectName("sceneHelpersTextNoteInput")
            self.scene_text_input.setPlaceholderText("Type feedback note here")
            self.scene_text_input.setToolTip("Text for a scene-native feedback note. Select a control first to place the note beside it.")
            text_note_row.addWidget(self.scene_text_input, 2)
            self.scene_text_color_combo = QtWidgets.QComboBox()
            self.scene_text_color_combo.setObjectName("sceneHelpersTextNoteColorCombo")
            for color_name, color_hex in SCENE_TEXT_NOTE_COLORS.items():
                self.scene_text_color_combo.addItem(color_name, color_hex)
            self.scene_text_color_combo.setToolTip("Pick the note color.")
            text_note_row.addWidget(self.scene_text_color_combo, 1)
            self.scene_text_size_spin = QtWidgets.QDoubleSpinBox()
            self.scene_text_size_spin.setObjectName("sceneHelpersTextNoteSizeSpin")
            self.scene_text_size_spin.setRange(SCENE_TEXT_NOTE_MIN_SCALE, SCENE_TEXT_NOTE_MAX_SCALE)
            self.scene_text_size_spin.setDecimals(2)
            self.scene_text_size_spin.setSingleStep(1.0)
            self.scene_text_size_spin.setValue(SCENE_TEXT_NOTE_DEFAULT_SCALE)
            self.scene_text_size_spin.setPrefix("Size ")
            self.scene_text_size_spin.setToolTip("Size for new text notes. Select an existing note and change this value to resize it live, or type an exact number.")
            text_note_row.addWidget(self.scene_text_size_spin, 1)
            self.create_scene_text_note_button = QtWidgets.QPushButton("Create Text Note")
            self.create_scene_text_note_button.setObjectName("sceneHelpersCreateTextNoteButton")
            self.create_scene_text_note_button.setToolTip("Create a Maya text-curve note beside the selected body part or control.")
            text_note_row.addWidget(self.create_scene_text_note_button, 1)
            notes_layout.addLayout(text_note_row)

            text_note_wrap_row = QtWidgets.QHBoxLayout()
            text_note_wrap_row.setSpacing(8)
            self.scene_text_wrap_check = QtWidgets.QCheckBox("Auto Wrap")
            self.scene_text_wrap_check.setObjectName("sceneHelpersTextNoteWrapCheck")
            self.scene_text_wrap_check.setChecked(SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED)
            self.scene_text_wrap_check.setToolTip("Wrap scene text into multiple Maya text-curve lines and fit them inside the box below.")
            text_note_wrap_row.addWidget(self.scene_text_wrap_check, 1)
            self.scene_text_box_width_spin = QtWidgets.QDoubleSpinBox()
            self.scene_text_box_width_spin.setObjectName("sceneHelpersTextNoteBoxWidthSpin")
            self.scene_text_box_width_spin.setRange(SCENE_TEXT_NOTE_MIN_BOX_SIZE, SCENE_TEXT_NOTE_MAX_BOX_SIZE)
            self.scene_text_box_width_spin.setDecimals(1)
            self.scene_text_box_width_spin.setSingleStep(10.0)
            self.scene_text_box_width_spin.setValue(SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH)
            self.scene_text_box_width_spin.setPrefix("Box W ")
            self.scene_text_box_width_spin.setToolTip("World-space width for the selected note wrap box. Text scales down if it would exceed this width.")
            text_note_wrap_row.addWidget(self.scene_text_box_width_spin, 1)
            self.scene_text_box_height_spin = QtWidgets.QDoubleSpinBox()
            self.scene_text_box_height_spin.setObjectName("sceneHelpersTextNoteBoxHeightSpin")
            self.scene_text_box_height_spin.setRange(SCENE_TEXT_NOTE_MIN_BOX_SIZE, SCENE_TEXT_NOTE_MAX_BOX_SIZE)
            self.scene_text_box_height_spin.setDecimals(1)
            self.scene_text_box_height_spin.setSingleStep(10.0)
            self.scene_text_box_height_spin.setValue(SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT)
            self.scene_text_box_height_spin.setPrefix("Box H ")
            self.scene_text_box_height_spin.setToolTip("World-space height for the selected note wrap box. Text scales down if it would exceed this height.")
            text_note_wrap_row.addWidget(self.scene_text_box_height_spin, 1)
            self.apply_text_note_box_button = QtWidgets.QPushButton("Apply Box")
            self.apply_text_note_box_button.setObjectName("sceneHelpersTextNoteApplyBoxButton")
            self.apply_text_note_box_button.setToolTip("Apply current wrap, width, and height to the selected text note.")
            text_note_wrap_row.addWidget(self.apply_text_note_box_button, 1)
            self.select_text_note_box_button = QtWidgets.QPushButton("Resize In Viewport")
            self.select_text_note_box_button.setObjectName("sceneHelpersTextNoteSelectBoxButton")
            self.select_text_note_box_button.setToolTip("Select the note's viewport resize box. Scale it in Maya and the text wrap updates to fit.")
            text_note_wrap_row.addWidget(self.select_text_note_box_button, 1)
            notes_layout.addLayout(text_note_wrap_row)

            text_note_list_row = QtWidgets.QHBoxLayout()
            text_note_list_row.setSpacing(8)
            self.scene_text_note_list = QtWidgets.QListWidget()
            self.scene_text_note_list.setObjectName("sceneHelpersTextNoteList")
            self.scene_text_note_list.setMaximumHeight(92)
            self.scene_text_note_list.setToolTip("All Aminate scene text notes in this Maya scene.")
            text_note_list_row.addWidget(self.scene_text_note_list, 2)
            text_note_buttons = QtWidgets.QVBoxLayout()
            text_note_buttons.setSpacing(4)
            self.key_text_note_on_button = QtWidgets.QPushButton("Key On")
            self.key_text_note_on_button.setToolTip("Key the selected text note visible on the current frame.")
            self.key_text_note_off_button = QtWidgets.QPushButton("Key Off")
            self.key_text_note_off_button.setToolTip("Key the selected text note hidden on the current frame.")
            self.move_text_note_button = QtWidgets.QPushButton("Move To Selected")
            self.move_text_note_button.setToolTip("Move the selected text note beside the currently selected body part or control and redraw its pointer line.")
            self.apply_text_note_color_button = QtWidgets.QPushButton("Apply Style")
            self.apply_text_note_color_button.setToolTip("Apply the chosen color and size to the selected text note and its pointer line.")
            self.delete_text_note_button = QtWidgets.QPushButton("Delete Text Note")
            self.delete_text_note_button.setToolTip("Delete the selected scene text note. Anything the UI can add should be deletable from the UI.")
            self.refresh_text_notes_button = QtWidgets.QPushButton("Refresh List")
            self.refresh_text_notes_button.setToolTip("Refresh the list of scene text notes.")
            for button in (
                self.key_text_note_on_button,
                self.key_text_note_off_button,
                self.move_text_note_button,
                self.apply_text_note_color_button,
                self.delete_text_note_button,
                self.refresh_text_notes_button,
            ):
                text_note_buttons.addWidget(button)
            text_note_list_row.addLayout(text_note_buttons, 1)
            notes_layout.addLayout(text_note_list_row)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            main_layout.addWidget(self.status_label)

            footer_layout = QtWidgets.QHBoxLayout()
            self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            self.brand_label.setWordWrap(True)
            footer_layout.addWidget(self.brand_label, 1)
            self.version_label = QtWidgets.QLabel("Version 0.3.6")
            footer_layout.addWidget(self.version_label)
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

            self.auto_key_button.toggled.connect(self._toggle_auto_key)
            self.auto_snap_button.toggled.connect(self._toggle_auto_snap)
            self.animation_layer_tint_button.toggled.connect(self._toggle_animation_layer_tint)
            self.keep_toolbar_extras_on_hide_check.toggled.connect(self._toggle_keep_toolbar_extras_on_hide)
            self.refresh_layer_tint_button.clicked.connect(self._refresh_animation_layer_tint)
            self.duplicate_current_layer_button.clicked.connect(self._duplicate_current_animation_layer)
            self.consolidate_other_layers_button.clicked.connect(self._consolidate_other_animation_layers)
            self.solo_current_layer_button.toggled.connect(self._solo_current_animation_layer)
            self.clear_layer_solos_button.clicked.connect(self._clear_animation_layer_solos)
            self.set_tween_machine_hotkey_button.clicked.connect(self._set_tween_machine_hotkey)
            self.tween_machine_hotkey_edit.editingFinished.connect(self._set_tween_machine_hotkey)
            self.tween_machine_opacity_spin.valueChanged.connect(self._set_tween_machine_opacity)
            self.open_tween_machine_button.clicked.connect(self._open_tween_machine)
            self.set_floating_channel_hotkey_button.clicked.connect(self._set_floating_channel_hotkey)
            self.floating_channel_hotkey_edit.editingFinished.connect(self._set_floating_channel_hotkey)
            self.floating_channel_opacity_spin.valueChanged.connect(self._set_floating_channel_opacity)
            self.open_floating_channel_box_button.clicked.connect(self._open_floating_channel_box)
            self.set_floating_graph_hotkey_button.clicked.connect(self._set_floating_graph_hotkey)
            self.floating_graph_hotkey_edit.editingFinished.connect(self._set_floating_graph_hotkey)
            self.floating_graph_opacity_spin.valueChanged.connect(self._set_floating_graph_opacity)
            self.open_floating_graph_button.clicked.connect(self._open_floating_graph_editor)
            self.snap_now_button.clicked.connect(self._snap_now)
            self.key_blocking_poses_button.clicked.connect(self._key_blocking_poses)
            self.retime_every_n_button.clicked.connect(self._retime_every_n_frames)
            self.game_mode_button.toggled.connect(self._toggle_game_mode)
            for action_key, checkbox in getattr(self, "game_mode_action_checks", {}).items():
                checkbox.toggled.connect(lambda enabled, key=action_key: self._toggle_game_mode_action(key, enabled))
            self.load_textures_button.clicked.connect(self._load_textures)
            self.recover_autosave_button.clicked.connect(self._recover_autosave)
            self.disable_security_popups_button.clicked.connect(self._disable_maya_security_popups)
            self.render_env_button.clicked.connect(self._render_environment)
            self.delete_render_env_button.clicked.connect(self._delete_render_environment)
            self.duplicate_teacher_rig_button.clicked.connect(self._duplicate_teacher_rig)
            self.delete_teacher_rig_button.clicked.connect(self._delete_teacher_rig)
            self.refresh_teacher_demo_log_button.clicked.connect(lambda: self._refresh_teacher_demo_edit_log(force_status=True))
            self.reset_teacher_demo_log_button.clicked.connect(self._reset_teacher_demo_edit_log)
            self.render_preset_button.clicked.connect(self._go_to_render_camera)
            self.camera_height_offset_spin.valueChanged.connect(self._camera_offsets_changed)
            self.camera_dolly_offset_spin.valueChanged.connect(self._camera_offsets_changed)
            self.create_scene_text_note_button.clicked.connect(self._create_scene_text_note)
            self.scene_text_size_spin.valueChanged.connect(self._scene_text_note_size_changed)
            self.scene_text_wrap_check.toggled.connect(self._scene_text_note_layout_changed)
            self.scene_text_box_width_spin.valueChanged.connect(self._scene_text_note_layout_changed)
            self.scene_text_box_height_spin.valueChanged.connect(self._scene_text_note_layout_changed)
            self.apply_text_note_box_button.clicked.connect(self._apply_scene_text_note_box)
            self.select_text_note_box_button.clicked.connect(self._select_scene_text_note_box)
            self.key_text_note_on_button.clicked.connect(lambda: self._key_scene_text_note(True))
            self.key_text_note_off_button.clicked.connect(lambda: self._key_scene_text_note(False))
            self.move_text_note_button.clicked.connect(self._move_scene_text_note)
            self.apply_text_note_color_button.clicked.connect(self._apply_scene_text_note_style)
            self.delete_text_note_button.clicked.connect(self._delete_scene_text_note)
            self.refresh_text_notes_button.clicked.connect(self._refresh_scene_text_notes)
            self.scene_text_note_list.itemSelectionChanged.connect(self._scene_text_note_selected)
            self._refresh_scene_text_notes()
            self._last_teacher_demo_log_text = None
            self.teacher_demo_log_timer = QtCore.QTimer(self)
            self.teacher_demo_log_timer.setInterval(2000)
            self.teacher_demo_log_timer.timeout.connect(self._refresh_teacher_demo_edit_log)
            self.teacher_demo_log_timer.start()
            self._refresh_teacher_demo_edit_log()

        def _sync_from_controller(self):
            self.auto_key_button.blockSignals(True)
            self.auto_key_button.setChecked(bool(self.controller.auto_key_enabled))
            self.auto_key_button.blockSignals(False)
            self.auto_snap_button.blockSignals(True)
            self.auto_snap_button.setChecked(bool(self.controller.auto_snap_enabled))
            self.auto_snap_button.blockSignals(False)
            self.game_mode_button.blockSignals(True)
            self.game_mode_button.setChecked(bool(getattr(self.controller, "game_animation_mode_enabled", False)))
            self.game_mode_button.blockSignals(False)
            _set_game_mode_button_glow(self.game_mode_button, bool(getattr(self.controller, "game_animation_mode_enabled", False)))
            self.animation_layer_tint_button.blockSignals(True)
            self.animation_layer_tint_button.setChecked(bool(getattr(self.controller, "animation_layer_tint_enabled", True)))
            self.animation_layer_tint_button.blockSignals(False)
            active_layer_state = self.controller.animation_layer_state(_active_animation_layer_name())
            self.solo_current_layer_button.blockSignals(True)
            self.solo_current_layer_button.setChecked(bool(active_layer_state.get("solo")))
            self.solo_current_layer_button.blockSignals(False)
            self.keep_toolbar_extras_on_hide_check.blockSignals(True)
            self.keep_toolbar_extras_on_hide_check.setChecked(bool(getattr(self.controller, "keep_toolbar_extras_on_hide", False)))
            self.keep_toolbar_extras_on_hide_check.blockSignals(False)
            self.render_preset_combo.blockSignals(True)
            current_key = getattr(self.controller, "last_render_camera_preset", "front")
            target_index = self.render_preset_combo.findData(current_key)
            if target_index < 0:
                target_index = 0
            self.render_preset_combo.setCurrentIndex(target_index)
            self.render_preset_combo.blockSignals(False)
            self.camera_height_offset_spin.blockSignals(True)
            self.camera_height_offset_spin.setValue(float(getattr(self.controller, "scene_helpers_camera_height_offset", 0.0)))
            self.camera_height_offset_spin.blockSignals(False)
            self.camera_dolly_offset_spin.blockSignals(True)
            self.camera_dolly_offset_spin.setValue(float(getattr(self.controller, "scene_helpers_camera_dolly_offset", 0.0)))
            self.camera_dolly_offset_spin.blockSignals(False)
            self.tween_machine_hotkey_edit.setText(getattr(self.controller, "tween_machine_hotkey", DEFAULT_TWEEN_MACHINE_HOTKEY))
            self.tween_machine_opacity_spin.blockSignals(True)
            self.tween_machine_opacity_spin.setValue(float(getattr(self.controller, "tween_machine_opacity", DEFAULT_TWEEN_MACHINE_OPACITY)))
            self.tween_machine_opacity_spin.blockSignals(False)
            self.floating_channel_hotkey_edit.setText(getattr(self.controller, "floating_channel_box_hotkey", maya_floating_channel_box.DEFAULT_HOTKEY))
            self.floating_channel_opacity_spin.blockSignals(True)
            self.floating_channel_opacity_spin.setValue(float(getattr(self.controller, "floating_channel_box_opacity", maya_floating_channel_box.DEFAULT_CHANNEL_OPACITY)))
            self.floating_channel_opacity_spin.blockSignals(False)
            self.floating_graph_hotkey_edit.setText(getattr(self.controller, "floating_graph_editor_hotkey", maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_HOTKEY))
            self.floating_graph_opacity_spin.blockSignals(True)
            self.floating_graph_opacity_spin.setValue(float(getattr(self.controller, "floating_graph_editor_opacity", maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_OPACITY)))
            self.floating_graph_opacity_spin.blockSignals(False)
            action_settings = getattr(self.controller, "game_animation_mode_actions", _game_animation_mode_action_settings())
            for action_key, checkbox in getattr(self, "game_mode_action_checks", {}).items():
                checkbox.blockSignals(True)
                checkbox.setChecked(bool(action_settings.get(action_key, True)))
                checkbox.blockSignals(False)

        def _toggle_auto_key(self, enabled):
            success, message = self.controller.set_auto_key_enabled(enabled)
            if not success:
                self.auto_key_button.blockSignals(True)
                self.auto_key_button.setChecked(bool(self.controller.auto_key_enabled))
                self.auto_key_button.blockSignals(False)
            self._set_status(message, success)

        def _toggle_auto_snap(self, enabled):
            success, message = self.controller.set_auto_snap_enabled(enabled)
            self._set_status(message, success)

        def _toggle_animation_layer_tint(self, enabled):
            success, message = self.controller.set_animation_layer_tint_enabled(enabled)
            for bar_window in list(GLOBAL_TIMELINE_BAR_WIDGETS):
                try:
                    if bar_window is not None and hasattr(bar_window, "_refresh_animation_layer_tint"):
                        bar_window._refresh_animation_layer_tint()
                except Exception:
                    pass
            self._set_status(message, success)

        def _toggle_keep_toolbar_extras_on_hide(self, enabled):
            success, message = self.controller.set_keep_toolbar_extras_on_hide(enabled)
            self._set_status(message, success)

        def _refresh_animation_layer_tint(self):
            info = self.controller.animation_layer_tint_info()
            for bar_window in list(GLOBAL_TIMELINE_BAR_WIDGETS):
                try:
                    if bar_window is not None and hasattr(bar_window, "_refresh_animation_layer_tint"):
                        bar_window._refresh_animation_layer_tint()
                except Exception:
                    pass
            layer_state = self.controller.animation_layer_state(info.get("layer") or "")
            self.solo_current_layer_button.blockSignals(True)
            self.solo_current_layer_button.setChecked(bool(layer_state.get("solo")))
            self.solo_current_layer_button.blockSignals(False)
            self._set_status("Animation Layer Tint refreshed: {0}.".format(info.get("label") or "Base Animation"), True)

        def _duplicate_current_animation_layer(self):
            success, message, _created = self.controller.duplicate_current_animation_layer()
            self._refresh_animation_layer_tint()
            self._set_status(message, success)

        def _consolidate_other_animation_layers(self):
            success, message, _created = self.controller.consolidate_other_animation_layers()
            self._refresh_animation_layer_tint()
            self._set_status(message, success)

        def _solo_current_animation_layer(self, enabled):
            success, message = self.controller.set_current_animation_layer_solo(enabled)
            if not success:
                self.solo_current_layer_button.blockSignals(True)
                self.solo_current_layer_button.setChecked(False)
                self.solo_current_layer_button.blockSignals(False)
            self._refresh_animation_layer_tint()
            self._set_status(message, success)

        def _clear_animation_layer_solos(self):
            success, message = self.controller.clear_animation_layer_solos()
            self._refresh_animation_layer_tint()
            self._set_status(message, success)

        def _snap_now(self):
            success, message = self.controller.snap_current_targets()
            self._set_status(message, success)

        def _retime_every_n_frames(self):
            success, message = self.controller.retime_selected_keys_to_every_n_frames(self.retime_every_n_spin.value())
            self._set_status(message, success)

        def _key_blocking_poses(self):
            success, message = self.controller.key_selected_controls_on_union_frames(
                include_translation=self.key_blocking_translation_check.isChecked(),
                include_rotation=self.key_blocking_rotation_check.isChecked(),
                include_other=self.key_blocking_other_check.isChecked(),
            )
            self._set_status(message, success)

        def _set_tween_machine_hotkey(self):
            success, message = self.controller.set_tween_machine_hotkey(self.tween_machine_hotkey_edit.text())
            self.tween_machine_hotkey_edit.setText(getattr(self.controller, "tween_machine_hotkey", DEFAULT_TWEEN_MACHINE_HOTKEY))
            self._set_status(message, success)

        def _set_tween_machine_opacity(self, opacity):
            success, message = self.controller.set_tween_machine_opacity(opacity)
            self._set_status(message, success)

        def _open_tween_machine(self):
            success, message = self.controller.show_tween_machine()
            self._set_status(message, success)

        def _set_floating_channel_hotkey(self):
            success, message = self.controller.set_floating_channel_box_hotkey(self.floating_channel_hotkey_edit.text())
            self.floating_channel_hotkey_edit.setText(getattr(self.controller, "floating_channel_box_hotkey", maya_floating_channel_box.DEFAULT_HOTKEY))
            self._set_status(message, success)

        def _set_floating_channel_opacity(self, opacity):
            success, message = self.controller.set_floating_channel_box_opacity(opacity)
            self._set_status(message, success)

        def _open_floating_channel_box(self):
            success, message = self.controller.show_floating_channel_box()
            self._set_status(message, success)

        def _set_floating_graph_hotkey(self):
            success, message = self.controller.set_floating_graph_editor_hotkey(self.floating_graph_hotkey_edit.text())
            self.floating_graph_hotkey_edit.setText(getattr(self.controller, "floating_graph_editor_hotkey", maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_HOTKEY))
            self._set_status(message, success)

        def _set_floating_graph_opacity(self, opacity):
            success, message = self.controller.set_floating_graph_editor_opacity(opacity)
            self._set_status(message, success)

        def _open_floating_graph_editor(self):
            success, message = self.controller.show_floating_graph_editor()
            self._set_status(message, success)

        def _toggle_game_mode(self, enabled):
            success, message = self.controller.set_game_animation_mode_enabled(enabled, parent=self)
            if not success:
                self.game_mode_button.blockSignals(True)
                self.game_mode_button.setChecked(bool(getattr(self.controller, "game_animation_mode_enabled", False)))
                self.game_mode_button.blockSignals(False)
            _sync_timeline_bar_game_buttons(self.controller)
            self._set_status(message, success)

        def _toggle_game_mode_action(self, action_key, enabled):
            success, message = self.controller.set_game_animation_mode_action_enabled(action_key, enabled)
            if not success:
                checkbox = getattr(self, "game_mode_action_checks", {}).get(action_key)
                if checkbox:
                    checkbox.blockSignals(True)
                    checkbox.setChecked(bool(getattr(self.controller, "game_animation_mode_actions", {}).get(action_key, True)))
                    checkbox.blockSignals(False)
            self._set_status(message, success)

        def _load_textures(self):
            success, message, _details = self.controller.load_scene_textures()
            self._set_status(message, success)

        def _recover_autosave(self):
            success, message, _details = self.controller.recover_last_autosave(
                prompt=True,
                force=True,
                prefer_current_scene=True,
            )
            self._set_status(message, success)

        def _disable_maya_security_popups(self):
            if QtWidgets:
                result = QtWidgets.QMessageBox.warning(
                    self,
                    "Disable Maya Security Popups",
                    "Only do this for rigs you trust.\n\nThis turns off Maya Safe Mode / Trust Center popup checks that can interrupt Aminate History Timeline save and restore. Unknown downloaded rigs can contain unsafe scripts.",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No,
                )
                if result != QtWidgets.QMessageBox.Yes:
                    self._set_status("Kept Maya security popup settings unchanged.", True)
                    return
            success, message = self.controller.disable_maya_security_popups()
            self._set_status(message, success)

        def _render_environment(self):
            success, message = self.controller.setup_render_environment()
            self._sync_from_controller()
            self._set_status(message, success)

        def _delete_render_environment(self):
            if QtWidgets:
                delete_result = QtWidgets.QMessageBox.question(
                    self,
                    "Delete Render Environment",
                    "Delete the Scene Helpers render environment? This removes the cameras, cyclorama, sky light, and bookmarks.",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No,
                )
                if delete_result != QtWidgets.QMessageBox.Yes:
                    self._set_status("Kept the render environment.", True)
                    return
            success, message = self.controller.delete_render_environment()
            self._sync_from_controller()
            self._set_status(message, success)

        def _duplicate_teacher_rig(self):
            success, message, _detail = self.controller.duplicate_selected_rig_for_teacher_demo(
                offset_x=self.teacher_rig_offset_spin.value()
            )
            self._refresh_teacher_demo_edit_log()
            self._set_status(message, success)

        def _delete_teacher_rig(self):
            if QtWidgets:
                delete_result = QtWidgets.QMessageBox.question(
                    self,
                    "Delete Teacher Demo",
                    "Delete all teacher-demo rig duplicates from this scene?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No,
                )
                if delete_result != QtWidgets.QMessageBox.Yes:
                    self._set_status("Kept teacher demo duplicates.", True)
                    return
            success, message = self.controller.delete_teacher_demo_duplicates()
            self._refresh_teacher_demo_edit_log()
            self._set_status(message, success)

        def _refresh_teacher_demo_edit_log(self, force_status=False):
            if not force_status and not self.isVisible():
                return
            success, message, detail = self.controller.refresh_teacher_demo_edit_log()
            text = detail.get("text") or "No teacher demo edits yet."
            if getattr(self, "_last_teacher_demo_log_text", None) != text:
                self.teacher_demo_edit_log.setPlainText(text)
                self._last_teacher_demo_log_text = text
            if force_status:
                self._set_status(message, success)

        def _reset_teacher_demo_edit_log(self):
            success, message, _detail = self.controller.reset_teacher_demo_edit_log()
            self._last_teacher_demo_log_text = None
            self._refresh_teacher_demo_edit_log()
            self._set_status(message, success)

        def _selected_scene_text_note(self):
            item = self.scene_text_note_list.currentItem()
            if not item:
                return ""
            return item.data(QtCore.Qt.UserRole) or ""

        def _refresh_scene_text_notes(self):
            current_note = self._selected_scene_text_note() if hasattr(self, "scene_text_note_list") else ""
            self.scene_text_note_list.blockSignals(True)
            self.scene_text_note_list.clear()
            target_row = -1
            for index, note_data in enumerate(self.controller.list_scene_text_notes()):
                label = "{0}  |  {1}".format(note_data.get("name") or "Text Note", note_data.get("text") or "")
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.UserRole, note_data.get("node") or "")
                item.setToolTip("Text: {0}\nAnchor: {1}\nSize: {2:g}\nVisible: {3}".format(
                    note_data.get("text") or "",
                    note_data.get("anchor") or "None",
                    float(note_data.get("size") or SCENE_TEXT_NOTE_DEFAULT_SCALE),
                    "yes" if note_data.get("visible") else "no",
                ) + "\nAuto Wrap: {0}\nBox: {1:g} x {2:g}".format(
                    "yes" if note_data.get("wrap_enabled", SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED) else "no",
                    float(note_data.get("box_width") or SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH),
                    float(note_data.get("box_height") or SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT),
                ))
                self.scene_text_note_list.addItem(item)
                if current_note and note_data.get("node") == current_note:
                    target_row = index
            if target_row >= 0:
                self.scene_text_note_list.setCurrentRow(target_row)
            self.scene_text_note_list.blockSignals(False)

        def _scene_text_note_selected(self):
            note_node = self._selected_scene_text_note()
            if not note_node:
                return
            for note_data in self.controller.list_scene_text_notes():
                if note_data.get("node") != note_node:
                    continue
                self.scene_text_input.setText(note_data.get("text") or "")
                color_hex = note_data.get("color") or SCENE_TEXT_NOTE_DEFAULT_COLOR
                index = self.scene_text_color_combo.findData(color_hex)
                if index >= 0:
                    self.scene_text_color_combo.setCurrentIndex(index)
                self.scene_text_size_spin.blockSignals(True)
                self.scene_text_size_spin.setValue(float(note_data.get("size") or SCENE_TEXT_NOTE_DEFAULT_SCALE))
                self.scene_text_size_spin.blockSignals(False)
                self.scene_text_wrap_check.blockSignals(True)
                self.scene_text_wrap_check.setChecked(bool(note_data.get("wrap_enabled", SCENE_TEXT_NOTE_DEFAULT_WRAP_ENABLED)))
                self.scene_text_wrap_check.blockSignals(False)
                self.scene_text_box_width_spin.blockSignals(True)
                self.scene_text_box_width_spin.setValue(float(note_data.get("box_width") or SCENE_TEXT_NOTE_DEFAULT_BOX_WIDTH))
                self.scene_text_box_width_spin.blockSignals(False)
                self.scene_text_box_height_spin.blockSignals(True)
                self.scene_text_box_height_spin.setValue(float(note_data.get("box_height") or SCENE_TEXT_NOTE_DEFAULT_BOX_HEIGHT))
                self.scene_text_box_height_spin.blockSignals(False)
                break

        def _create_scene_text_note(self):
            success, message, detail = self.controller.create_scene_text_note(
                self.scene_text_input.text(),
                color_hex=self.scene_text_color_combo.currentData() or SCENE_TEXT_NOTE_DEFAULT_COLOR,
                size=self.scene_text_size_spin.value(),
                wrap_enabled=self.scene_text_wrap_check.isChecked(),
                box_width=self.scene_text_box_width_spin.value(),
                box_height=self.scene_text_box_height_spin.value(),
            )
            self._refresh_scene_text_notes()
            if detail.get("node"):
                for row in range(self.scene_text_note_list.count()):
                    item = self.scene_text_note_list.item(row)
                    if item and item.data(QtCore.Qt.UserRole) == detail.get("node"):
                        self.scene_text_note_list.setCurrentRow(row)
                        break
            self._set_status(message, success)

        def _key_scene_text_note(self, visible):
            success, message = self.controller.key_scene_text_note_visibility(self._selected_scene_text_note(), visible=visible)
            self._refresh_scene_text_notes()
            self._set_status(message, success)

        def _apply_scene_text_note_style(self):
            note_node = self._selected_scene_text_note()
            success, message = self.controller.set_scene_text_note_text(note_node, self.scene_text_input.text())
            if success:
                success, message = self.controller.set_scene_text_note_color(
                    note_node,
                    self.scene_text_color_combo.currentData() or SCENE_TEXT_NOTE_DEFAULT_COLOR,
                )
            if success:
                success, message = self.controller.set_scene_text_note_size(note_node, self.scene_text_size_spin.value())
            if success:
                success, message = self.controller.set_scene_text_note_layout(
                    note_node,
                    wrap_enabled=self.scene_text_wrap_check.isChecked(),
                    box_width=self.scene_text_box_width_spin.value(),
                    box_height=self.scene_text_box_height_spin.value(),
                )
            self._refresh_scene_text_notes()
            self._set_status(message, success)

        def _scene_text_note_size_changed(self, value):
            note_node = self._selected_scene_text_note()
            if not note_node:
                return
            success, message = self.controller.set_scene_text_note_size(note_node, value)
            self._set_status(message, success)

        def _apply_scene_text_note_box(self):
            note_node = self._selected_scene_text_note()
            success, message = self.controller.set_scene_text_note_layout(
                note_node,
                wrap_enabled=self.scene_text_wrap_check.isChecked(),
                box_width=self.scene_text_box_width_spin.value(),
                box_height=self.scene_text_box_height_spin.value(),
            )
            self._refresh_scene_text_notes()
            self._set_status(message, success)

        def _select_scene_text_note_box(self):
            success, message = self.controller.select_scene_text_note_wrap_box(self._selected_scene_text_note())
            self._set_status(message, success)

        def _scene_text_note_layout_changed(self, *_args):
            note_node = self._selected_scene_text_note()
            if not note_node:
                return
            success, message = self.controller.set_scene_text_note_layout(
                note_node,
                wrap_enabled=self.scene_text_wrap_check.isChecked(),
                box_width=self.scene_text_box_width_spin.value(),
                box_height=self.scene_text_box_height_spin.value(),
            )
            self._set_status(message, success)

        def _move_scene_text_note(self):
            success, message = self.controller.move_scene_text_note_to_selection(self._selected_scene_text_note())
            self._refresh_scene_text_notes()
            self._set_status(message, success)

        def _delete_scene_text_note(self):
            success, message = self.controller.delete_scene_text_note(self._selected_scene_text_note())
            self._refresh_scene_text_notes()
            self._set_status(message, success)

        def _go_to_render_camera(self):
            preset_key = self.render_preset_combo.currentData() or "front"
            success, message = self.controller.activate_scene_camera_preset(preset_key)
            self._set_status(message, success)

        def _camera_offsets_changed(self, *_args):
            success, message = self.controller.set_scene_helpers_camera_offsets(
                height_offset=self.camera_height_offset_spin.value(),
                dolly_offset=self.camera_dolly_offset_spin.value(),
            )
            self._set_status(message, success)

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)

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
                self.hide()
            except Exception:
                pass
            try:
                event.ignore()
            except Exception:
                pass


def _close_existing_window():
    window = GLOBAL_WINDOW
    if window is not None and _qt_object_valid(window):
        try:
            window.hide()
        except Exception:
            pass
    _process_timeline_bar_events()


def _timeline_bar_workspace_exists():
    return bool(MAYA_AVAILABLE and cmds and cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, exists=True))


def _native_timeline_bar_dock_enabled():
    enabled = os.environ.get("AMINATE_ENABLE_NATIVE_BOTTOM_TOOLKIT_DOCK") == "1"
    danger_accepted = os.environ.get("AMINATE_ALLOW_NATIVE_BOTTOM_TOOLKIT_DOCK_CRASH_RISK") == "1"
    if enabled and not danger_accepted:
        _warn_timeline_bar_docking(
            "Native bottom Toolkit Bar docking is disabled unless AMINATE_ALLOW_NATIVE_BOTTOM_TOOLKIT_DOCK_CRASH_RISK=1 is also set."
        )
    return bool(enabled and danger_accepted)


def _fixed_timeline_bar_host():
    global GLOBAL_TIMELINE_BAR_HOST
    if _qt_object_valid(GLOBAL_TIMELINE_BAR_HOST):
        return GLOBAL_TIMELINE_BAR_HOST
    GLOBAL_TIMELINE_BAR_HOST = None
    if not QtWidgets:
        return None
    main_window = _maya_main_window()
    if (
        (not _qt_object_valid(main_window) or not hasattr(main_window, "addToolBar"))
        and omui
        and shiboken
        and hasattr(QtWidgets, "QMainWindow")
    ):
        try:
            pointer = omui.MQtUtil.mainWindow()
            if pointer:
                main_window = shiboken.wrapInstance(
                    int(pointer),
                    QtWidgets.QMainWindow,
                )
        except Exception:
            main_window = None
    if not _qt_object_valid(main_window) or not hasattr(main_window, "addToolBar"):
        app = QtWidgets.QApplication.instance()
        main_window = None
        for candidate in app.topLevelWidgets() if app else []:
            try:
                if hasattr(candidate, "addToolBar") and candidate.objectName() == "MayaWindow":
                    main_window = candidate
                    break
            except RuntimeError:
                continue
    if not _qt_object_valid(main_window) or not hasattr(main_window, "addToolBar"):
        return None
    try:
        existing = main_window.findChild(
            QtWidgets.QToolBar,
            STUDENT_TIMELINE_BAR_FIXED_HOST_OBJECT_NAME,
        )
    except Exception:
        existing = None
    if _qt_object_valid(existing):
        GLOBAL_TIMELINE_BAR_HOST = existing
        return existing
    host = QtWidgets.QToolBar("Aminate", main_window)
    host.setObjectName(STUDENT_TIMELINE_BAR_FIXED_HOST_OBJECT_NAME)
    host.setWindowTitle("Aminate")
    host.setMovable(False)
    host.setFloatable(False)
    host.setOrientation(_qt_flag("Orientation", "Horizontal", QtCore.Qt.Horizontal))
    bottom_area = _qt_flag("ToolBarArea", "BottomToolBarArea", QtCore.Qt.BottomToolBarArea)
    host.setAllowedAreas(bottom_area)
    host.setMinimumSize(0, 96)
    host.setMaximumHeight(124)
    host.setContentsMargins(0, 0, 0, 0)
    host.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
    try:
        host.setContextMenuPolicy(
            _qt_flag("ContextMenuPolicy", "NoContextMenu", QtCore.Qt.NoContextMenu)
        )
    except Exception:
        pass
    host.setStyleSheet(
        "QToolBar#%s { background-color: #2B2B2B; border: 0px; spacing: 0px; } "
        "QToolBar#%s::handle { width: 0px; image: none; }"
        % (STUDENT_TIMELINE_BAR_FIXED_HOST_OBJECT_NAME, STUDENT_TIMELINE_BAR_FIXED_HOST_OBJECT_NAME)
    )
    main_window.addToolBar(bottom_area, host)
    try:
        host.toggleViewAction().setVisible(False)
    except Exception:
        pass
    GLOBAL_TIMELINE_BAR_HOST = host
    return host


def _show_timeline_bar_in_fixed_host(window):
    if not _qt_object_valid(window):
        return False, "Toolkit Bar Qt panel is not valid."
    host = _fixed_timeline_bar_host()
    if not _qt_object_valid(host):
        return False, "Maya main window cannot host the fixed Aminate bottom bar."
    try:
        window.setWindowFlags(_qt_flag("WindowType", "Widget", QtCore.Qt.Widget))
    except Exception:
        pass
    window.setObjectName("aminateFixedBottomToolkitBarPanel")
    window.setMinimumWidth(0)
    window.setMaximumHeight(124)
    hosted = False
    for action in host.actions():
        try:
            if hasattr(action, "defaultWidget") and action.defaultWidget() is window:
                hosted = True
                break
        except RuntimeError:
            continue
    if not hosted:
        window.setParent(host)
        host.addWidget(window)
    window.show()
    host.show()
    try:
        host.raise_()
    except Exception:
        pass
    _process_timeline_bar_events()
    return True, "Pinned Toolkit Bar to Maya's fixed bottom toolbar area."


def _position_timeline_bar_near_maya_bottom(window):
    if not QtWidgets or not _qt_object_valid(window):
        return
    try:
        main_window = _maya_main_window()
        if main_window and _qt_object_valid(main_window):
            geometry = main_window.frameGeometry()
        else:
            geometry = QtWidgets.QApplication.primaryScreen().availableGeometry()
        width = min(max(int(geometry.width()) - 80, 760), 1500)
        height = 124
        x_pos = int(geometry.x()) + max(20, int((geometry.width() - width) / 2))
        y_pos = int(geometry.y()) + max(20, int(geometry.height()) - height - 78)
        window.resize(width, height)
        window.move(x_pos, y_pos)
    except Exception:
        pass


def _show_timeline_bar_as_safe_window(window):
    try:
        window.show(dockable=False)
    except TypeError:
        window.show()
    except Exception:
        window.show()
    _position_timeline_bar_near_maya_bottom(window)
    try:
        window.raise_()
    except Exception:
        pass


def _process_timeline_bar_events():
    if not QtWidgets:
        return
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    try:
        app.processEvents()
    except Exception:
        pass


def _timeline_bar_workspace_floating():
    if not _timeline_bar_workspace_exists():
        return None
    try:
        return bool(cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, query=True, floating=True))
    except Exception:
        return None


def _warn_timeline_bar_docking(message):
    if MAYA_AVAILABLE and om2:
        try:
            om2.MGlobal.displayWarning("[Toolkit Bar] {0}".format(message))
        except Exception:
            pass


def _dock_timeline_bar_workspace(area="bottom"):
    if not MAYA_AVAILABLE or not cmds:
        return False, "Maya commands are not available."
    if not _timeline_bar_workspace_exists():
        return False, "Maya did not create the Toolkit Bar workspace control."
    try:
        floating = bool(cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, query=True, floating=True))
    except Exception:
        floating = None
    if floating is False:
        try:
            cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, edit=True, visible=True)
        except Exception:
            pass
        return True, "Toolkit Bar is already docked into Maya's {0} layout.".format(area)
    try:
        cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, edit=True, visible=True)
    except Exception:
        pass
    _process_timeline_bar_events()
    return False, "Maya kept the Toolkit Bar floating, so Aminate left it open instead of forcing a risky re-dock."


def _hide_timeline_bar_workspace():
    # Legacy native Toolkit Bar workspaces stay visible until Maya exits.
    # Maya 2026 has repeatedly faulted during native dock hide/close calls.
    return False


def _close_existing_timeline_bar():
    global GLOBAL_TIMELINE_BAR_CONTROLLER
    global GLOBAL_TIMELINE_BAR_WINDOW
    global GLOBAL_TIMELINE_BAR_HOST
    window = GLOBAL_TIMELINE_BAR_WINDOW
    if _qt_object_valid(window):
        try:
            window.hide()
        except Exception:
            pass
    if _qt_object_valid(GLOBAL_TIMELINE_BAR_HOST):
        try:
            GLOBAL_TIMELINE_BAR_HOST.hide()
        except Exception:
            pass
    # Never change native workspace visibility during ordinary close.  The
    # supported fixed QToolBar host above is hidden and reused safely.


def _reset_stale_timeline_bar_workspace():
    if not _timeline_bar_workspace_exists():
        return True
    _hide_timeline_bar_workspace()
    _process_timeline_bar_events()
    return False


def _show_timeline_bar_in_native_workspace(window, area="bottom"):
    if not (MAYA_AVAILABLE and cmds and QtWidgets and omui and shiboken):
        return False, "Maya native workspace parenting is not available."
    if not _qt_object_valid(window):
        return False, "Toolkit Bar Qt window is not valid."
    if _timeline_bar_workspace_exists():
        _hide_timeline_bar_workspace()
        return False, "A stale native Toolkit Bar workspace exists. Aminate left it open instead of touching Maya's unsafe native close path."
    try:
        cmds.workspaceControl(
            STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME,
            label=" ",
            retain=False,
            floating=False,
            dockToMainWindow=(area, False),
            initialHeight=124,
            minimumHeight=96,
        )
    except Exception as exc:
        return False, "Could not create Toolkit Bar workspace control: {0}".format(exc)
    pointer = omui.MQtUtil.findControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME)
    if not pointer:
        return False, "Maya created no Toolkit Bar workspace pointer."
    try:
        workspace_widget = shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)
    except Exception as exc:
        return False, "Could not wrap Toolkit Bar workspace: {0}".format(exc)
    try:
        window.setWindowFlags(QtCore.Qt.Widget)
    except Exception:
        pass
    try:
        window.setParent(workspace_widget)
    except Exception as exc:
        return False, "Could not parent Toolkit Bar into workspace: {0}".format(exc)
    layout = workspace_widget.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(workspace_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
    layout.addWidget(window)
    window.show()
    _process_timeline_bar_events()
    try:
        cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, edit=True, visible=True, restore=True)
    except Exception:
        pass
    return True, "Docked Toolkit Bar into Maya's {0} layout.".format(area)


def launch_student_timeline_button_bar(dock=True, controller=None, status_callback=None):
    global GLOBAL_TIMELINE_BAR_CONTROLLER
    global GLOBAL_TIMELINE_BAR_WINDOW
    if not MAYA_AVAILABLE:
        raise RuntimeError("launch_student_timeline_button_bar() must run inside Autodesk Maya.")
    if not QtWidgets:
        raise RuntimeError("launch_student_timeline_button_bar() needs PySide inside Maya.")
    requested_native_dock = bool(dock and _native_timeline_bar_dock_enabled())
    fixed_bottom_host = bool(dock and not requested_native_dock)
    if GLOBAL_TIMELINE_BAR_WINDOW is not None and not _qt_object_valid(GLOBAL_TIMELINE_BAR_WINDOW):
        GLOBAL_TIMELINE_BAR_WINDOW = None
    if fixed_bottom_host and GLOBAL_TIMELINE_BAR_WINDOW is None:
        host = _fixed_timeline_bar_host()
        if _qt_object_valid(host):
            try:
                existing_panel = host.findChild(
                    QtWidgets.QWidget,
                    "aminateFixedBottomToolkitBarPanel",
                )
            except Exception:
                existing_panel = None
            if _qt_object_valid(existing_panel):
                GLOBAL_TIMELINE_BAR_WINDOW = existing_panel
                GLOBAL_TIMELINE_BAR_CONTROLLER = getattr(existing_panel, "controller", controller)
    if GLOBAL_TIMELINE_BAR_WINDOW is not None:
        try:
            existing = GLOBAL_TIMELINE_BAR_WINDOW
            if fixed_bottom_host:
                pinned, pin_message = _show_timeline_bar_in_fixed_host(existing)
                if not pinned:
                    raise RuntimeError(pin_message)
                return existing
            if requested_native_dock and _timeline_bar_workspace_exists():
                try:
                    cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, edit=True, visible=True)
                except Exception:
                    pass
                existing.show()
                _process_timeline_bar_events()
                if _timeline_bar_workspace_floating() is not False:
                    _warn_timeline_bar_docking(
                        "Maya kept the Toolkit Bar floating, so Aminate left it open instead of forcing a risky re-dock."
                    )
                return existing
            if not dock:
                existing.show()
                _process_timeline_bar_events()
                return existing
            if requested_native_dock and not _timeline_bar_workspace_exists():
                raise RuntimeError("Maya native Toolkit Bar workspace is unavailable.")
        except RuntimeError:
            if fixed_bottom_host:
                raise
    if requested_native_dock and GLOBAL_TIMELINE_BAR_WINDOW is None and _timeline_bar_workspace_exists():
        if not _reset_stale_timeline_bar_workspace():
            dock_message = "Maya kept a stale Toolkit Bar workspace open, so Aminate did not create a duplicate bottom bar."
            _warn_timeline_bar_docking(dock_message)
            raise RuntimeError(dock_message)
    owns_controller = controller is None
    GLOBAL_TIMELINE_BAR_CONTROLLER = controller or MayaTimingToolsController()
    parent_widget = None if (fixed_bottom_host or requested_native_dock) else _maya_main_window()
    GLOBAL_TIMELINE_BAR_WINDOW = StudentTimelineButtonBarWindow(
        GLOBAL_TIMELINE_BAR_CONTROLLER,
        status_callback=status_callback,
        parent=parent_widget,
        owns_controller=owns_controller,
        embedded=bool(fixed_bottom_host or requested_native_dock),
    )
    if requested_native_dock:
        try:
            GLOBAL_TIMELINE_BAR_WINDOW.setObjectName(STUDENT_TIMELINE_BAR_OBJECT_NAME)
        except Exception:
            pass
    if requested_native_dock:
        docked, dock_message = _show_timeline_bar_in_native_workspace(GLOBAL_TIMELINE_BAR_WINDOW, "bottom")
        if not docked:
            _warn_timeline_bar_docking(dock_message)
            try:
                GLOBAL_TIMELINE_BAR_WINDOW.hide()
            except Exception:
                pass
            raise RuntimeError(dock_message)
    elif fixed_bottom_host:
        pinned, pin_message = _show_timeline_bar_in_fixed_host(GLOBAL_TIMELINE_BAR_WINDOW)
        if not pinned:
            raise RuntimeError(pin_message)
    else:
        GLOBAL_TIMELINE_BAR_WINDOW.show()
        _process_timeline_bar_events()
    if requested_native_dock and _timeline_bar_workspace_exists():
        if _timeline_bar_workspace_floating() is not False:
            _warn_timeline_bar_docking(
                "Maya kept the Toolkit Bar floating, so Aminate left it open instead of forcing a risky re-dock."
            )
        try:
            cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, edit=True, label="")
        except Exception:
            try:
                cmds.workspaceControl(STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME, edit=True, label=" ")
            except Exception:
                pass
    elif requested_native_dock:
        dock_message = "Maya did not create the Toolkit Bar workspace control."
        _warn_timeline_bar_docking(dock_message)
        try:
            GLOBAL_TIMELINE_BAR_WINDOW.hide()
        except Exception:
            pass
        raise RuntimeError(dock_message)
    try:
        GLOBAL_TIMELINE_BAR_WINDOW.setMaximumHeight(124)
    except Exception:
        pass
    return GLOBAL_TIMELINE_BAR_WINDOW


def launch_maya_timing_tools(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not MAYA_AVAILABLE:
        raise RuntimeError("maya_timing_tools.launch_maya_timing_tools() must run inside Autodesk Maya.")
    if not QtWidgets:
        raise RuntimeError("maya_timing_tools.launch_maya_timing_tools() needs PySide inside Maya.")
    if GLOBAL_WINDOW is not None and _qt_object_valid(GLOBAL_WINDOW):
        GLOBAL_WINDOW.show()
        _process_timeline_bar_events()
        return GLOBAL_WINDOW
    _close_existing_window()
    GLOBAL_CONTROLLER = MayaTimingToolsController()
    GLOBAL_WINDOW = MayaTimingToolsWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    if dock and hasattr(GLOBAL_WINDOW, "show"):
        try:
            GLOBAL_WINDOW.show(dockable=True, floating=True, area="right")
        except Exception:
            GLOBAL_WINDOW.show()
    else:
        GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "MayaTimingToolsController",
    "MayaTimingToolsWindow",
    "StudentTimelineButtonBarWindow",
    "STUDENT_TIMELINE_BAR_WORKSPACE_CONTROL_NAME",
    "hide_aminate_toolbar_extras",
    "launch_maya_timing_tools",
    "launch_student_timeline_button_bar",
]
