"""
maya_dynamic_parent_pivot.py

Combined Maya animation workflow tool with Dynamic Parenting, Hand / Foot Hold,
Surface Contact, Dynamic Pivot, Universal IK/FK, Controls Retargeter (Face and Body), Control Picker,
Animators Pencil, Onion Skin, Rotation Doctor, Character Skinning, Rig Scale, Video Reference, Timeline Notes, and Customization tabs.
"""

from __future__ import absolute_import, division, print_function

import json
import math
import os

import maya_shelf_utils
import maya_animation_assistant
import maya_animators_pencil
import maya_animation_styling
import maya_contact_hold
import maya_dynamic_parenting_tool
import maya_control_picker
import maya_face_retarget
import maya_history_timeline
import maya_reference_manager
import maya_onion_skin
import maya_surface_contact
import maya_timing_tools
import maya_rotation_doctor
import maya_skin_transfer
import maya_skinning_cleanup
import maya_rig_scale_export
import maya_timeline_notes
import maya_video_reference_tool
import maya_aminate_customization
import maya_smear_frames

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.api.OpenMaya as om
    import maya.OpenMayaUI as omui

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    mel = None
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


WINDOW_OBJECT_NAME = "mayaAnimWorkflowToolsWindow"
DOCK_HOST_OBJECT_NAME = WINDOW_OBJECT_NAME + "DockHost"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
LEGACY_WORKSPACE_CONTROL_NAME = DOCK_HOST_OBJECT_NAME + "WorkspaceControl"
DOCKED_WORKFLOW_MIN_WIDTH = 360
DOCKED_WORKFLOW_MIN_HEIGHT = 240
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
VERSION_LABEL = "Version 0.3.5 Beta"
TUTORIALS_DOCS_RELATIVE_PATH = os.path.join("docs", "index.html")
DEFAULT_SHELF_NAME = maya_shelf_utils.DEFAULT_SHELF_NAME
DEFAULT_SHELF_BUTTON_LABEL = "Aminate"
SHELF_BUTTON_DOC_TAG = "mayaAnimWorkflowShelfButton"
SHELF_ICON_FILE_NAME = "maya_anim_workflow_tools_icon.png"
SHELF_ICON_OVERLAY_LABEL = ""
AMINATE_ENABLE_APP_KEY_FILTER = "AMINATE_ENABLE_APP_KEY_FILTER"
ROOT_GROUP_NAME = "amirDynamicTools_GRP"
PARENTING_GROUP_NAME = "amirDynamicParenting_GRP"
PIVOT_GROUP_NAME = "amirDynamicPivot_GRP"
WORLD_LOCATOR_NAME = "amirDynamicWorld_LOC"
PIVOT_CTRL_NAME = "amirDynamicPivot_CTRL"
PARENT_SETUP_TYPE = "amirDynamicParentSetup"
PIVOT_TYPE = "amirDynamicPivot"
PROFILE_FILE_NAME = "amir_anim_workflow_ikfk_profiles.json"
PROFILE_VERSION = 1
DEFAULT_PV_DISTANCE_MULTIPLIER = 2.0
EPSILON = 1.0e-5
TAB_PARENTING = "Dynamic Parenting"
TAB_CONTACT_HOLD = "Hand / Foot Hold"
TAB_SURFACE_CONTACT = "Surface Contact"
TAB_PIVOT = "Dynamic Pivot"
TAB_IKFK = "Universal IK/FK"
TAB_FACE_RETARGET = "Controls Retargeter (Face and Body)"
TAB_CONTROL_PICKER = "Control Picker"
TAB_ANIMATORS_PENCIL = "Animators Pencil"
TAB_ANIMATION_ASSISTANT = "Animation Assistant"
TAB_ANIMATION_STYLING = "Animation Styling"
TAB_HISTORY_TIMELINE = "History Timeline"
TAB_ONION = "Onion Skin"
TAB_ROTATION = "Rotation Doctor"
TAB_SKIN = "Character Skinning"
TAB_RIG_SCALE = "Rig Scale"
TAB_VIDEO = "Video Reference"
TAB_TIMELINE = "Timeline Notes"
TAB_SMEAR_FRAMES = "Smear Frames"
TAB_CUSTOMIZATION = "Customization"
TAB_GUIDE = "Quick Start"
TAB_STUDENT_CORE = "Toolkit Bar"
TAB_TIMING = "Scene Helpers"
TAB_REFERENCE_MANAGER = "Reference Manager"
AMINATE_WINDOW_STYLESHEET = """
QDialog#mayaAnimWorkflowToolsWindow {
    background-color: #2B2B2B;
    color: #E8E8E8;
}
QWidget[aminateTabPage="true"] {
    background-color: #2B2B2B;
    color: #E8E8E8;
}
QScrollArea#mayaAnimWorkflowTabScroll {
    background-color: #2B2B2B;
    border: 0px;
}
QScrollArea#mayaAnimWorkflowTabScroll > QWidget > QWidget {
    background-color: #2B2B2B;
}
QTabWidget#mayaAnimWorkflowTabWidget::pane {
    background-color: #2B2B2B;
    border: 1px solid #3C3C3C;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background-color: #242424;
    color: #CFCFCF;
    border: 1px solid #3C3C3C;
    border-bottom-color: #2B2B2B;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 108px;
    max-width: 190px;
    padding: 7px 10px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #3A3A3A;
    color: #F2F2F2;
    border-color: #4CC9F0;
}
QTabBar::tab:hover {
    background-color: #333333;
    color: #FFFFFF;
}
QTabBar QToolButton {
    width: 0px;
    height: 0px;
    border: 0px;
    margin: 0px;
    padding: 0px;
    background: transparent;
}
QToolButton#mayaAnimWorkflowTabNavButton {
    min-width: 34px;
    max-width: 44px;
    min-height: 24px;
    max-height: 26px;
    padding: 2px 6px;
    border-radius: 7px;
    background-color: #113B4A;
    color: #FFFFFF;
    border: 1px solid #4CC9F0;
    font-weight: 800;
}
QToolButton#mayaAnimWorkflowTabNavButton:hover {
    background-color: #176075;
    border-color: #79E2FF;
}
QToolButton#mayaAnimWorkflowTabNavButton:pressed {
    background-color: #0E2C38;
    border-color: #B7F2FF;
}
QToolButton#mayaAnimWorkflowTabNavButton:disabled {
    background-color: #252525;
    color: #6E6E6E;
    border-color: #3A3A3A;
}
QFrame#mayaAnimWorkflowTabIntro {
    background-color: #353535;
    color: #E8E8E8;
    border: 1px solid #4A4A4A;
    border-left: 4px solid #4CC9F0;
    border-radius: 8px;
}
QLabel#mayaAnimWorkflowIntroTitle {
    color: #F2F2F2;
    font-weight: 700;
}
QLabel#mayaAnimWorkflowStatusLabel {
    background-color: #202020;
    color: #E8E8E8;
    border: 1px solid #3C3C3C;
    border-radius: 6px;
    padding: 6px 8px;
}
QLabel#mayaAnimWorkflowBrandLabel,
QLabel#mayaAnimWorkflowVersionLabel {
    color: #BDBDBD;
}
QPushButton,
QToolButton {
    background-color: #3A3A3A;
    color: #F2F2F2;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 5px 8px;
}
QPushButton:hover,
QToolButton:hover {
    background-color: #454545;
    border-color: #6A6A6A;
}
QPushButton:pressed,
QToolButton:pressed {
    background-color: #2F5D66;
    border-color: #4CC9F0;
}
QPushButton:disabled,
QToolButton:disabled {
    background-color: #262626;
    color: #777777;
    border-color: #363636;
}
QLineEdit,
QPlainTextEdit,
QTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    background-color: #1E1E1E;
    color: #F2F2F2;
    border: 1px solid #444444;
    border-radius: 5px;
    padding: 4px;
    selection-background-color: #335C67;
}
QLineEdit:focus,
QPlainTextEdit:focus,
QTextEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #4CC9F0;
}
QComboBox::drop-down {
    border: 0px;
    width: 20px;
}
QCheckBox,
QRadioButton,
QLabel {
    color: #E8E8E8;
}
QGroupBox {
    background-color: #303030;
    color: #F2F2F2;
    border: 1px solid #444444;
    border-radius: 8px;
    margin-top: 14px;
    padding: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0px 4px;
    color: #F2F2F2;
}
QTableWidget,
QTreeWidget,
QListWidget {
    background-color: #202020;
    color: #EFEFEF;
    gridline-color: #3C3C3C;
    border: 1px solid #3C3C3C;
    border-radius: 6px;
    selection-background-color: #335C67;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background-color: #303030;
    color: #F2F2F2;
    border: 1px solid #444444;
    padding: 4px;
}
QScrollBar:vertical,
QScrollBar:horizontal {
    background-color: #202020;
    border: 0px;
    margin: 0px;
}
QScrollBar:vertical {
    width: 14px;
}
QScrollBar:horizontal {
    height: 14px;
}
QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {
    background-color: #4A4A4A;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {
    background-color: #5A5A5A;
}
QScrollBar::add-line,
QScrollBar::sub-line {
    width: 0px;
    height: 0px;
}
"""
TAB_HELP_TEXT = {
    TAB_GUIDE: "Start here if you want the plain-English version of what each tab does and when to use it.",
    TAB_STUDENT_CORE: "Use this when you want the same Toolkit Bar that docks above Maya's timeline inside a tab: History Timeline strip, Animation Layer controls, timing helpers, workflow icons, package zip, and Game Animation Mode.",
    TAB_TIMING: "Use this when you want the Scene Helpers quick buttons for Auto Key, Auto Snap To Frames, Animation Layer Tint, Game Animation Mode, Load Textures, Open Last Autosave, Set Up Render Environment, Delete Render Environment, Camera Offset controls, and Camera Preset plus whole-frame timing cleanup.",
    TAB_REFERENCE_MANAGER: "Use this when you want one zip containing the saved Maya scene plus referenced scenes, textures, image planes, audio, caches, and a manifest so the shot can move to another machine.",
    TAB_PARENTING: "Use this when one prop or control needs to switch between hand, gun, world, or mixed parents without popping. Best for reloads, pickups, passes, and drops.",
    TAB_CONTACT_HOLD: "Use this when a hand or foot should stay planted on chosen world axes while the body keeps moving. The hold stays live, editable, and reversible.",
    TAB_SURFACE_CONTACT: "Use this when a hand, foot, or other control should stay clamped to a selected mesh surface in real time. The solver stays live, follows the selected mesh, and can be keyed on or off.",
    TAB_PIVOT: "Use this when you want to turn from a temporary pivot point without changing the real rig pivot.",
    TAB_IKFK: "Use this when you need to switch an arm or leg cleanly between IK and FK and keep the pose matched.",
    TAB_FACE_RETARGET: "Use this when you want face or body controls from one rig copied onto another rig. Put a source control on the left and its target control on the right. Empty rows are ignored. Auto Map By Name matches controls quickly from names, and Retarget All Controls bakes onto the target controls. Reduce Keys keeps only the original source keyframes.",
    TAB_CONTROL_PICKER: "Use this when you want a synced list and visual control map for a rig. It auto-finds likely controls by name, groups them by face, body, side, tail, wings, and FK/IK, keeps Maya and the picker in sync, lets you reorder the list, and shows the keyable attrs for the control you pick.",
    TAB_ANIMATORS_PENCIL: "Use this when you want expanded Blue Pencil-style drawing stored as real Maya curves and text in the scene. Pencil marks stay visible without this tool installed. Use it for 2D animation notes, layers, frame markers, ghosting, retiming, camera-based drawings, and quick annotation shapes.",
    TAB_ANIMATION_ASSISTANT: "Use this when you want Aminate to check pose balance. Pick a floor plane, add the controls that can touch the floor, pick a center of gravity control, and get a tiny balanced or unbalanced viewport light plus support area drawing.",
    TAB_ANIMATION_STYLING: "Use this when you want Into the Spider-Verse-style held keys. Set a hold length, auto-copy new key values into the future, and mark timeline ranges where nearby keys block that hold.",
    TAB_HISTORY_TIMELINE: "Use this when you want ZBrush-style restore points for animation work. It saves full Maya scene snapshots beside the scene, tracks branches, notes, file size, custom auto-save rules, and protected milestones.",
    TAB_ONION: "Use this when you want to see ghosted past and future poses to judge spacing, arcs, and timing.",
    TAB_ROTATION: "Use this when rotations are flipping, gimbaling, or reading strangely and you want the safest fix suggestion.",
    TAB_SKIN: "Use this for skinning fixes: freeze bad character mesh transforms safely, or copy exact skin weights from one same-topology mesh to another.",
    TAB_RIG_SCALE: "Use this when you need a safely scaled export copy of a character for game-engine export.",
    TAB_VIDEO: "Use this when you want video or image reference in the scene for tracing, timing, and annotation.",
    TAB_TIMELINE: "Use this when you want readable colored notes directly on the timeline so you can scrub and review shot notes.",
    TAB_SMEAR_FRAMES: "Use this when you want a quick static smear mesh for a fast motion accent. The first slice creates clean Unreal-friendly mesh geometry on the current frame without touching the rig.",
    TAB_CUSTOMIZATION: "Use this when you want one place for Aminate animation colors: timeline highlight, note ranges, keyframe emphasis, and Graph Editor tangent or curve accents where Maya exposes those native color slots.",
}
LEGACY_WORKFLOW_SHELF_DOC_TAGS = (
    maya_onion_skin.SHELF_BUTTON_DOC_TAG,
    maya_rotation_doctor.SHELF_BUTTON_DOC_TAG,
)
RELEASE_SPACES = {
    "World": "world",
    "Original Parent/Object": "original",
}
BAKE_MODES = {
    "Bake Keys": "keys",
    "Bake Frames": "frames",
}
BAKE_RANGES = {
    "Current Frame": "current",
    "Highlighted Timeline Range": "highlighted",
    "Playback Range": "playback",
}
PIVOT_MODES = {
    "Centered": "centered",
    "To Last Object": "last_object",
    "World Static": "world_static",
}
SEGMENT_TOKENS = {
    "arm": ("shoulder", "elbow", "wrist"),
    "leg": ("hip", "knee", "ankle"),
}
FK_SEGMENT_ALIASES = {
    "arm": {
        "shoulder": ("shoulder", "fk_1", "_1_"),
        "elbow": ("elbow", "fk_2", "_2_"),
        "wrist": ("wrist", "hand", "fk_3", "_3_"),
    },
    "leg": {
        "hip": ("hip", "fk_1", "_1_"),
        "knee": ("knee", "fk_2", "_2_"),
        "ankle": ("ankle", "foot", "fk_3", "_3_"),
    },
}
SIDE_TOKEN_SETS = {
    "left": ("left", "lf", "lft", "l_"),
    "right": ("right", "rt", "rgt", "r_"),
}

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None
GLOBAL_DOCK_HOST = None


def _debug(message):
    if MAYA_AVAILABLE:
        om.MGlobal.displayInfo("[Aminate] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE:
        om.MGlobal.displayWarning("[Aminate] {0}".format(message))


def _error(message):
    if MAYA_AVAILABLE:
        om.MGlobal.displayError("[Aminate] {0}".format(message))


def _qt_flag(scope_name, member_name, fallback=None):
    if not QtCore:
        return fallback
    if hasattr(QtCore.Qt, member_name):
        return getattr(QtCore.Qt, member_name)
    scoped_enum = getattr(QtCore.Qt, scope_name, None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return fallback


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


def _layout_size_constraint(member_name, fallback=None):
    if not QtWidgets:
        return fallback
    layout_class = getattr(QtWidgets, "QLayout", None)
    if not layout_class:
        return fallback
    if hasattr(layout_class, member_name):
        return getattr(layout_class, member_name)
    scoped_enum = getattr(layout_class, "SizeConstraint", None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return fallback


def _set_no_size_constraint(layout):
    if not layout:
        return
    constraint = _layout_size_constraint("SetNoConstraint")
    if constraint is None:
        return
    try:
        layout.setSizeConstraint(constraint)
    except Exception:
        pass


def _allow_tiny_shell_widget(widget):
    if not widget:
        return
    try:
        widget.setMinimumSize(0, 0)
    except Exception:
        try:
            widget.setMinimumWidth(0)
            widget.setMinimumHeight(0)
        except Exception:
            pass
    if hasattr(widget, "setSizePolicy") and QtWidgets:
        try:
            widget.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        except Exception:
            pass


def _style_donate_button(button):
    if not button or not QtWidgets:
        return
    button.setMinimumWidth(92)
    button.setStyleSheet(
        """
        QPushButton {
            background-color: #FFC439;
            color: #111111;
            border: 1px solid #E0B12F;
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #FFD35A;
        }
        QPushButton:pressed {
            background-color: #F0B92B;
        }
        """
    )


def _open_external_url(url):
    if not url:
        return False
    if QtGui and hasattr(QtGui, "QDesktopServices"):
        return QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
    return False


def _tutorials_index_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), TUTORIALS_DOCS_RELATIVE_PATH)


def _open_local_file(path):
    if not path or not os.path.exists(path):
        return False
    if QtGui and QtCore and hasattr(QtGui, "QDesktopServices"):
        if QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path)):
            return True
    if hasattr(os, "startfile"):
        try:
            os.startfile(path)
            return True
        except Exception:
            return False
    return False


def _ensure_attr(node_name, attr_name, attr_type="string"):
    if cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return
    if attr_type == "string":
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
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


def _frame_display(frame_value):
    frame_value = float(frame_value)
    if abs(frame_value - round(frame_value)) < 1.0e-3:
        return str(int(round(frame_value)))
    return "{0:.2f}".format(frame_value).rstrip("0").rstrip(".")


def _safe_node_name(node_name):
    return "".join(character if character.isalnum() else "_" for character in node_name).strip("_") or "node"


def _unique_name(base):
    if not cmds.objExists(base):
        return base
    index = 1
    while cmds.objExists("{0}{1}".format(base, index)):
        index += 1
    return "{0}{1}".format(base, index)


def _short_name(node_name):
    return node_name.split("|")[-1].split(":")[-1]


def _strip_namespace(node_name):
    return _short_name(node_name)


def _namespace_prefix(node_name):
    short = node_name.split("|")[-1]
    if ":" not in short:
        return ""
    return short.rsplit(":", 1)[0]


def _dedupe_preserve_order(items):
    deduped = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _selected_transforms():
    if not MAYA_AVAILABLE:
        return []
    return _dedupe_preserve_order(cmds.ls(selection=True, long=True, type="transform") or [])


def _selection_switch_target_candidate(setups=None):
    setups = setups or []
    if not MAYA_AVAILABLE:
        return ""
    setup_nodes = set()
    for setup_data in setups:
        setup_nodes.update(
            value
            for value in (
                setup_data.get("setup_group"),
                setup_data.get("driven"),
                setup_data.get("control"),
                setup_data.get("space_group"),
                setup_data.get("offset_group"),
            )
            if value
        )
    for node_name in reversed(_selected_transforms()):
        if node_name in setup_nodes:
            continue
        setup = _find_setup_for_node(node_name)
        if setup:
            continue
        return node_name
    return ""


def _describe_parenting_state(setup_data):
    driven_name = _short_name(setup_data.get("driven", "")) or "This control"
    current_space = setup_data.get("current_space") or "world"
    current_driver = setup_data.get("current_driver") or ""
    if current_space == "grab_release" and current_driver:
        return "{0} is following {1}.".format(driven_name, _short_name(current_driver))
    if current_space == "original":
        return "{0} is back on its original parent/object.".format(driven_name)
    if current_space == "world":
        return "{0} is free in world space.".format(driven_name)
    if current_driver:
        return "{0} is following {1}.".format(driven_name, _short_name(current_driver))
    return "{0} is using {1} space.".format(driven_name, current_space)


def _all_transforms_and_joints():
    transforms = cmds.ls(type="transform", long=True) or []
    joints = cmds.ls(type="joint", long=True) or []
    return _dedupe_preserve_order(transforms + joints)


def _maya_main_window():
    if not (MAYA_AVAILABLE and QtWidgets and shiboken and omui):
        return None
    pointer = omui.MQtUtil.mainWindow()
    if not pointer:
        return None
    return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)


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


def _safe_close_qt_widget(widget, delete_later=True):
    if not _qt_object_valid(widget):
        return
    try:
        widget.close()
    except Exception:
        pass
    if not delete_later or not _qt_object_valid(widget):
        return
    try:
        widget.setParent(None)
    except Exception:
        pass
    try:
        widget.deleteLater()
    except Exception:
        pass


def _delete_workspace_control(name):
    if MAYA_AVAILABLE and cmds and name and cmds.workspaceControl(name, exists=True):
        try:
            cmds.deleteUI(name, control=True)
        except Exception:
            cmds.deleteUI(name)


def _workflow_widgets():
    if not QtWidgets:
        return []
    app = QtWidgets.QApplication.instance()
    if not app:
        return []
    widgets = []
    for widget in app.allWidgets():
        try:
            if widget.objectName() in (WINDOW_OBJECT_NAME, DOCK_HOST_OBJECT_NAME, WORKSPACE_CONTROL_NAME, LEGACY_WORKSPACE_CONTROL_NAME):
                widgets.append(widget)
        except Exception:
            pass
    return widgets


def _widget_has_ancestor_object_name(widget, object_name):
    walker = widget
    while walker is not None:
        try:
            if walker.objectName() == object_name:
                return True
            walker = walker.parentWidget()
        except Exception:
            return False
    return False


def _widget_is_ancestor(possible_ancestor, widget):
    walker = widget
    while walker is not None:
        if walker is possible_ancestor:
            return True
        try:
            walker = walker.parentWidget()
        except Exception:
            return False
    return False


def _find_docked_workflow_widget():
    for widget in _workflow_widgets():
        if widget.objectName() == WINDOW_OBJECT_NAME and _widget_has_ancestor_object_name(widget, WORKSPACE_CONTROL_NAME):
            return widget
    return None


def _cleanup_duplicate_workflow_widgets(keep_widget=None):
    for widget in _workflow_widgets():
        if not _qt_object_valid(widget):
            continue
        if keep_widget is not None and widget is keep_widget:
            continue
        if keep_widget is not None and _widget_is_ancestor(widget, keep_widget):
            continue
        _safe_close_qt_widget(widget)
    try:
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    except Exception:
        pass


def _ensure_single_workflow_widget(keep_widget=None):
    if not QtWidgets:
        return
    _process_qt_events()
    _cleanup_duplicate_workflow_widgets(keep_widget=keep_widget)
    _process_qt_events()


def _close_existing_window():
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    global GLOBAL_DOCK_HOST
    if GLOBAL_WINDOW is not None and _qt_object_valid(GLOBAL_WINDOW):
        try:
            hide_extras = getattr(GLOBAL_WINDOW, "_hide_toolbar_extras_if_needed", None)
            if hide_extras:
                hide_extras()
        except Exception:
            pass
    docked_window = GLOBAL_WINDOW is not None and _qt_object_valid(GLOBAL_WINDOW) and _widget_has_ancestor_object_name(GLOBAL_WINDOW, WORKSPACE_CONTROL_NAME)
    if docked_window or _workspace_control_exists(WORKSPACE_CONTROL_NAME):
        _delete_workspace_control(WORKSPACE_CONTROL_NAME)
        _process_qt_events()
    else:
        _safe_close_qt_widget(GLOBAL_WINDOW)
    if _workspace_control_exists(LEGACY_WORKSPACE_CONTROL_NAME):
        _delete_workspace_control(LEGACY_WORKSPACE_CONTROL_NAME)
        _process_qt_events()
    else:
        _safe_close_qt_widget(GLOBAL_DOCK_HOST)
    for module in (
        maya_contact_hold,
        maya_surface_contact,
        maya_onion_skin,
        maya_rotation_doctor,
        maya_skin_transfer,
        maya_skinning_cleanup,
        maya_rig_scale_export,
        maya_video_reference_tool,
        maya_timeline_notes,
        maya_timing_tools,
        maya_face_retarget,
    ):
        try:
            close_fn = getattr(module, "_close_existing_window", None)
            if close_fn:
                close_fn()
        except Exception:
            pass
    GLOBAL_WINDOW = None
    GLOBAL_DOCK_HOST = None
    GLOBAL_CONTROLLER = None
    if not QtWidgets:
        return
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    try:
        app.processEvents()
    except Exception:
        pass
    _cleanup_duplicate_workflow_widgets()
    try:
        app.processEvents()
    except Exception:
        pass


def _matrix_from_node(node_name):
    return om.MMatrix(cmds.xform(node_name, query=True, matrix=True, worldSpace=True))


def _matrix_to_list(matrix):
    return [matrix[index] for index in range(16)]


def _set_world_matrix(node_name, matrix):
    cmds.xform(node_name, worldSpace=True, matrix=_matrix_to_list(matrix))


def _world_translation(node_name):
    return cmds.xform(node_name, query=True, worldSpace=True, translation=True) or [0.0, 0.0, 0.0]


def _world_rotation(node_name):
    return cmds.xform(node_name, query=True, worldSpace=True, rotation=True) or [0.0, 0.0, 0.0]


def _set_world_translation(node_name, values):
    cmds.xform(node_name, worldSpace=True, translation=values)


def _set_world_rotation(node_name, values):
    cmds.xform(node_name, worldSpace=True, rotation=values)


def _set_keyable_channels(node_name, attrs):
    for attr_name in attrs:
        plug = "{0}.{1}".format(node_name, attr_name)
        if not cmds.objExists(plug):
            continue
        if cmds.getAttr(plug, lock=True):
            continue
        try:
            cmds.setKeyframe(node_name, attribute=attr_name)
        except Exception:
            pass


def _parent_constraint_targets(constraint_name):
    targets = cmds.parentConstraint(constraint_name, query=True, targetList=True) or []
    aliases = cmds.parentConstraint(constraint_name, query=True, weightAliasList=True) or []
    mapping = {}
    for index, target in enumerate(targets):
        mapping[target] = aliases[index] if index < len(aliases) else ""
    return mapping


def _highest_weight_target(constraint_name):
    mapping = _parent_constraint_targets(constraint_name)
    best_target = ""
    best_weight = -1.0
    for target, alias in mapping.items():
        if not alias:
            continue
        value = cmds.getAttr("{0}.{1}".format(constraint_name, alias))
        if value > best_weight:
            best_target = target
            best_weight = value
    return best_target


def _set_constraint_target(constraint_name, constrained_node, target_name):
    mapping = _parent_constraint_targets(constraint_name)
    if target_name not in mapping:
        cmds.parentConstraint(target_name, constrained_node, edit=True, weight=0.0)
        mapping = _parent_constraint_targets(constraint_name)
    for candidate, alias in mapping.items():
        if not alias:
            continue
        cmds.setAttr("{0}.{1}".format(constraint_name, alias), 1.0 if candidate == target_name else 0.0)
        try:
            cmds.setKeyframe(constraint_name, attribute=alias)
        except Exception:
            pass


def _highlighted_time_range():
    try:
        playback_slider = mel.eval("$tmpVar=$gPlayBackSlider")
        if not playback_slider:
            return None
        if not cmds.timeControl(playback_slider, query=True, rangeVisible=True):
            return None
        values = cmds.timeControl(playback_slider, query=True, rangeArray=True) or []
        if len(values) != 2:
            return None
        start = float(values[0])
        end = float(values[1]) - 1.0
        if end <= start:
            return None
        return start, end
    except Exception:
        return None


def _bake_range_from_mode(mode):
    current_time = float(cmds.currentTime(query=True))
    if mode == "current":
        return current_time, current_time
    if mode == "highlighted":
        highlighted = _highlighted_time_range()
        if highlighted:
            return highlighted
    return (
        float(cmds.playbackOptions(query=True, minTime=True)),
        float(cmds.playbackOptions(query=True, maxTime=True)),
    )


def _profile_file_path():
    scripts_dir = os.path.join(cmds.internalVar(userAppDir=True), "scripts")
    if not os.path.isdir(scripts_dir):
        try:
            os.makedirs(scripts_dir)
        except OSError:
            pass
    return os.path.join(scripts_dir, PROFILE_FILE_NAME)


def _load_profile_store():
    path = _profile_file_path()
    if not os.path.exists(path):
        return {"version": PROFILE_VERSION, "profiles": []}
    try:
        with open(path, "r") as handle:
            data = json.load(handle)
    except Exception:
        return {"version": PROFILE_VERSION, "profiles": []}
    if not isinstance(data, dict):
        return {"version": PROFILE_VERSION, "profiles": []}
    data.setdefault("version", PROFILE_VERSION)
    data.setdefault("profiles", [])
    return data


def _save_profile_store(data):
    with open(_profile_file_path(), "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def _vector(values):
    return om.MVector(values[0], values[1], values[2])


def _pole_vector_position(start_values, middle_values, end_values):
    start_vector = _vector(start_values)
    middle_vector = _vector(middle_values)
    end_vector = _vector(end_values)
    start_to_end = end_vector - start_vector
    if start_to_end.length() < EPSILON:
        return list(middle_values)
    normal = start_to_end.normal()
    projection_length = (middle_vector - start_vector) * normal
    projected_point = start_vector + (normal * projection_length)
    arrow = middle_vector - projected_point
    if arrow.length() < EPSILON:
        arrow = (middle_vector - start_vector) ^ (end_vector - middle_vector)
        if arrow.length() < EPSILON:
            arrow = om.MVector(0.0, 1.0, 0.0)
    distance = max((middle_vector - start_vector).length(), (end_vector - middle_vector).length(), 1.0)
    pv_position = middle_vector + arrow.normal() * (distance * DEFAULT_PV_DISTANCE_MULTIPLIER)
    return [pv_position.x, pv_position.y, pv_position.z]


def _compose_around_pivot_matrix(pivot_position, rotation_degrees):
    pivot_matrix = om.MTransformationMatrix()
    pivot_matrix.setTranslation(om.MVector(*pivot_position), om.MSpace.kWorld)
    rotate_matrix = om.MTransformationMatrix()
    euler_rotation = om.MEulerRotation(
        math.radians(rotation_degrees[0]),
        math.radians(rotation_degrees[1]),
        math.radians(rotation_degrees[2]),
        om.MEulerRotation.kXYZ,
    )
    rotate_matrix.rotateBy(euler_rotation, om.MSpace.kTransform)
    inverse_pivot_matrix = om.MTransformationMatrix()
    inverse_pivot_matrix.setTranslation(om.MVector(*[-value for value in pivot_position]), om.MSpace.kWorld)
    return pivot_matrix.asMatrix() * rotate_matrix.asMatrix() * inverse_pivot_matrix.asMatrix()


def _apply_matrix_around_pivot(node_name, pivot_position, rotation_degrees):
    current_matrix = _matrix_from_node(node_name)
    delta_matrix = _compose_around_pivot_matrix(pivot_position, rotation_degrees)
    _set_world_matrix(node_name, current_matrix * delta_matrix)


def _current_rotation_values(node_name):
    return [
        cmds.getAttr("{0}.rotateX".format(node_name)),
        cmds.getAttr("{0}.rotateY".format(node_name)),
        cmds.getAttr("{0}.rotateZ".format(node_name)),
    ]


def _zero_rotation(node_name):
    for axis in ("X", "Y", "Z"):
        plug = "{0}.rotate{1}".format(node_name, axis)
        if cmds.objExists(plug) and not cmds.getAttr(plug, lock=True):
            cmds.setAttr(plug, 0.0)


def _create_circle_control(name, radius=1.5, normal=(1, 0, 0), color_index=17):
    result = cmds.circle(name=name, normal=normal, radius=radius, constructionHistory=False) or []
    transform = result[0]
    if len(result) > 1:
        shape = result[1]
    else:
        shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
        shape = shapes[0] if shapes else ""
    if not shape:
        return transform
    cmds.setAttr(shape + ".overrideEnabled", 1)
    cmds.setAttr(shape + ".overrideColor", color_index)
    return transform


def _lock_channels(node_name, attrs):
    for attr_name in attrs:
        plug = "{0}.{1}".format(node_name, attr_name)
        if cmds.objExists(plug):
            try:
                cmds.setAttr(plug, lock=True, keyable=False, channelBox=False)
            except Exception:
                pass


def _controller_radius_from_target(node_name):
    try:
        bbox = cmds.exactWorldBoundingBox(node_name)
        x_size = abs(bbox[3] - bbox[0])
        y_size = abs(bbox[4] - bbox[1])
        z_size = abs(bbox[5] - bbox[2])
        return max((x_size + y_size + z_size) / 6.0, 0.75)
    except Exception:
        return 1.25


def _ensure_root_hierarchy():
    if cmds.objExists(ROOT_GROUP_NAME):
        root_group = ROOT_GROUP_NAME
    else:
        root_group = cmds.createNode("transform", name=ROOT_GROUP_NAME)
    parenting_group = PARENTING_GROUP_NAME if cmds.objExists(PARENTING_GROUP_NAME) else cmds.createNode("transform", name=PARENTING_GROUP_NAME, parent=root_group)
    pivot_group = PIVOT_GROUP_NAME if cmds.objExists(PIVOT_GROUP_NAME) else cmds.createNode("transform", name=PIVOT_GROUP_NAME, parent=root_group)
    for group_name in (root_group, parenting_group, pivot_group):
        for attr_name in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ", "scaleX", "scaleY", "scaleZ"):
            try:
                cmds.setAttr("{0}.{1}".format(group_name, attr_name), lock=True, keyable=False, channelBox=False)
            except Exception:
                pass
    if cmds.objExists(WORLD_LOCATOR_NAME):
        world_locator = WORLD_LOCATOR_NAME
    else:
        world_locator = cmds.spaceLocator(name=WORLD_LOCATOR_NAME)[0]
        cmds.parent(world_locator, root_group)
        cmds.setAttr(world_locator + ".visibility", 0)
        _lock_channels(world_locator, ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
    return root_group, parenting_group, pivot_group, world_locator


def _find_parent_setup_groups():
    if not cmds.objExists(PARENTING_GROUP_NAME):
        return []
    children = cmds.listRelatives(PARENTING_GROUP_NAME, children=True, type="transform", fullPath=True) or []
    return [child for child in children if _get_string_attr(child, "adwSetupType") == PARENT_SETUP_TYPE]


def _parent_setup_data(setup_group):
    if not cmds.objExists(setup_group):
        return None
    data = {
        "setup_group": setup_group,
        "driven": _get_string_attr(setup_group, "adwDriven"),
        "original_parent": _get_string_attr(setup_group, "adwOriginalParent"),
        "space_group": _get_string_attr(setup_group, "adwSpaceGroup"),
        "offset_group": _get_string_attr(setup_group, "adwOffsetGroup"),
        "control": _get_string_attr(setup_group, "adwControl"),
        "space_constraint": _get_string_attr(setup_group, "adwSpaceConstraint"),
        "driven_constraint": _get_string_attr(setup_group, "adwDrivenConstraint"),
        "current_space": _get_string_attr(setup_group, "adwCurrentSpace", "world"),
        "current_driver": _get_string_attr(setup_group, "adwCurrentDriver"),
        "event_log": _get_json_attr(setup_group, "adwEventLog", []),
    }
    if not data["driven"] or not data["control"] or not cmds.objExists(data["control"]):
        return None
    return data


def _find_setup_for_node(node_name):
    node_name = (cmds.ls(node_name, long=True) or [node_name])[0]
    for setup_group in _find_parent_setup_groups():
        data = _parent_setup_data(setup_group)
        if not data:
            continue
        if node_name in (data["setup_group"], data["driven"], data["control"], data["space_group"], data["offset_group"]):
            return data
    return None


def _draw_temp_control(name, radius):
    control = _create_circle_control(name=name, radius=radius, normal=(1, 0, 0), color_index=6)
    extra = _create_circle_control(name=name + "_Y", radius=radius, normal=(0, 1, 0), color_index=18)
    extra2 = _create_circle_control(name=name + "_Z", radius=radius, normal=(0, 0, 1), color_index=13)
    for shape_parent in (extra, extra2):
        shapes = cmds.listRelatives(shape_parent, shapes=True, fullPath=True) or []
        for shape in shapes:
            cmds.parent(shape, control, add=True, shape=True)
        cmds.delete(shape_parent)
    return control


def _create_parent_setup(driven_node):
    driven_node = (cmds.ls(driven_node, long=True) or [driven_node])[0]
    existing = _find_setup_for_node(driven_node)
    if existing:
        return existing, False, "Temp control already exists for {0}.".format(_short_name(driven_node))

    _, parenting_group, _, world_locator = _ensure_root_hierarchy()
    short = _safe_node_name(_short_name(driven_node))
    setup_group = cmds.createNode("transform", name="{0}_admSetup_GRP".format(short), parent=parenting_group)
    _set_string_attr(setup_group, "adwSetupType", PARENT_SETUP_TYPE)
    _set_string_attr(setup_group, "adwDriven", driven_node)

    original_parent = cmds.listRelatives(driven_node, parent=True, fullPath=True) or []
    original_parent = original_parent[0] if original_parent else ""
    _set_string_attr(setup_group, "adwOriginalParent", original_parent)

    space_group = cmds.createNode("transform", name="{0}_admSpace_GRP".format(short), parent=setup_group)
    offset_group = cmds.createNode("transform", name="{0}_admOffset_GRP".format(short), parent=space_group)
    control = _draw_temp_control("{0}_adm_CTRL".format(short), _controller_radius_from_target(driven_node))
    control = cmds.parent(control, offset_group)[0]

    cmds.setAttr(space_group + ".visibility", 0)
    cmds.setAttr(offset_group + ".visibility", 0)
    for axis in ("X", "Y", "Z"):
        plug = "{0}.scale{1}".format(control, axis)
        if cmds.objExists(plug):
            try:
                cmds.setAttr(plug, keyable=False, channelBox=False)
            except Exception:
                pass

    original_target = original_parent if original_parent and cmds.objExists(original_parent) else world_locator
    constraint_targets = [world_locator]
    if original_target != world_locator:
        constraint_targets.append(original_target)
    space_constraint = cmds.parentConstraint(
        constraint_targets,
        space_group,
        maintainOffset=False,
        name="{0}_admSpace_parentConstraint".format(short),
    )[0]
    driven_constraint = cmds.parentConstraint(
        control,
        driven_node,
        maintainOffset=False,
        name="{0}_admDriven_parentConstraint".format(short),
    )[0]

    for target, alias in _parent_constraint_targets(space_constraint).items():
        if alias:
            cmds.setAttr("{0}.{1}".format(space_constraint, alias), 1.0 if target == world_locator else 0.0)
    _set_world_matrix(offset_group, _matrix_from_node(driven_node))
    _set_keyable_channels(offset_group, ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))

    _set_string_attr(setup_group, "adwSpaceGroup", space_group)
    _set_string_attr(setup_group, "adwOffsetGroup", offset_group)
    _set_string_attr(setup_group, "adwControl", control)
    _set_string_attr(setup_group, "adwSpaceConstraint", space_constraint)
    _set_string_attr(setup_group, "adwDrivenConstraint", driven_constraint)
    _set_string_attr(setup_group, "adwCurrentSpace", "world")
    _set_string_attr(setup_group, "adwCurrentDriver", "")
    _set_string_attr(setup_group, "adwEventLog", "[]")
    return _parent_setup_data(setup_group), True, "Created temp control for {0}.".format(_short_name(driven_node))


def _preserve_control_world(setup_data, target_node, current_space_label, current_driver):
    control_world_matrix = _matrix_from_node(setup_data["control"])
    _set_constraint_target(setup_data["space_constraint"], setup_data["space_group"], target_node)
    _set_world_matrix(setup_data["offset_group"], control_world_matrix)
    _set_keyable_channels(setup_data["offset_group"], ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
    _set_string_attr(setup_data["setup_group"], "adwCurrentSpace", current_space_label)
    _set_string_attr(setup_data["setup_group"], "adwCurrentDriver", current_driver or "")
    return True


def _save_parenting_event_log(setup_group, events):
    _set_string_attr(setup_group, "adwEventLog", json.dumps(events))


def _record_parenting_event(setup_data, action, target_node="", space_label=""):
    frame_value = float(cmds.currentTime(query=True))
    events = list(setup_data.get("event_log") or _get_json_attr(setup_data["setup_group"], "adwEventLog", []))
    filtered = []
    for event in events:
        try:
            event_frame = float(event.get("frame", 0.0))
        except Exception:
            event_frame = 0.0
        if abs(event_frame - frame_value) < EPSILON:
            continue
        filtered.append(event)
    filtered.append(
        {
            "frame": frame_value,
            "action": action,
            "target": target_node or "",
            "space": space_label or "",
            "driven": setup_data.get("driven", ""),
        }
    )
    filtered.sort(key=lambda item: (float(item.get("frame", 0.0)), item.get("action", ""), item.get("target", "")))
    _save_parenting_event_log(setup_data["setup_group"], filtered)
    setup_data["event_log"] = filtered
    return filtered


def _describe_parenting_event(event_data):
    frame_text = _frame_display(event_data.get("frame", 0.0))
    driven_name = _short_name(event_data.get("driven", "")) or "Control"
    target_name = _short_name(event_data.get("target", "")) if event_data.get("target") else ""
    action = event_data.get("action", "")
    space_label = event_data.get("space", "")
    if action == "pickup" and target_name:
        return "F{0}: Pickup {1} -> {2}".format(frame_text, driven_name, target_name)
    if action == "pass" and target_name:
        return "F{0}: Pass {1} -> {2}".format(frame_text, driven_name, target_name)
    if action == "drop" and space_label == "original":
        return "F{0}: Drop {1} -> original parent/object".format(frame_text, driven_name)
    if action == "drop":
        return "F{0}: Drop {1} -> world".format(frame_text, driven_name)
    if action == "follow" and target_name:
        return "F{0}: {1} -> {2}".format(frame_text, driven_name, target_name)
    if action == "release" and space_label == "original":
        return "F{0}: {1} -> original parent/object".format(frame_text, driven_name)
    if action == "release":
        return "F{0}: {1} -> world".format(frame_text, driven_name)
    return "F{0}: {1}".format(frame_text, driven_name)


def _time_for_manual_bake(setup_data, start_time, end_time):
    interesting_nodes = [setup_data["control"], setup_data["offset_group"], setup_data["space_constraint"]]
    attrs = ["translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"]
    times = set()
    for node_name in interesting_nodes:
        if not node_name or not cmds.objExists(node_name):
            continue
        query_attrs = list(attrs)
        if cmds.nodeType(node_name) == "parentConstraint":
            query_attrs = [alias for alias in _parent_constraint_targets(node_name).values() if alias]
        for attr_name in query_attrs:
            values = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
            for value in values:
                value = float(value)
                if start_time <= value <= end_time:
                    times.add(value)
    if not times:
        times.add(float(cmds.currentTime(query=True)))
    return sorted(times)


def _score_node_name(node_name, required_tokens, bonus_tokens):
    lowered = _strip_namespace(node_name).lower()
    score = 0

    def _token_matches(token_value):
        if not token_value:
            return False
        if token_value in SIDE_TOKEN_SETS:
            return any(alias in lowered for alias in SIDE_TOKEN_SETS[token_value])
        return token_value in lowered

    for token in required_tokens:
        if _token_matches(token):
            score += 5
        elif token:
            score -= 10
    for token in bonus_tokens:
        if token and token in lowered:
            score += 2
    if lowered.endswith("_ctrl") or lowered.endswith("_ctl"):
        score += 1
    return score


def _control_candidate_adjustment(node_name):
    lowered = _strip_namespace(node_name).lower()
    score = 0
    if "constraint" in lowered:
        score -= 40
    if "ikhandle" in lowered or lowered.endswith("_handle"):
        score -= 24
    if "effector" in lowered:
        score -= 18
    if "locator" in lowered or "_loc" in lowered:
        score -= 10
    if "avg" in lowered and ("loc" in lowered or "locator" in lowered):
        score -= 6
    if "seamless" in lowered:
        score -= 5
    if any(token in lowered for token in ("pv", "pole", "polevector", "vector", "aim", "up")):
        score -= 6
    if any(token in lowered for token in ("helper", "buffer", "null")):
        score -= 8
    if any(token in lowered for token in ("switch", "settings", "option", "options")):
        score -= 6
    if any(token in lowered for token in ("match", "space", "follow", "offset", "zero", "_grp", "group")):
        score -= 4
    if any(token in lowered for token in ("bind", "joint", "_jnt", "result", "driver", "driven", "proxy")):
        score -= 5
    if lowered.endswith("_ctrl") or lowered.endswith("_ctl") or "control" in lowered:
        score += 4
    if any(token in lowered for token in ("hand", "wrist", "foot", "ankle", "elbow", "knee", "shoulder", "hip")):
        score += 1
    return score


def _detect_side_from_nodes(nodes):
    combined = " ".join(_strip_namespace(node).lower() for node in nodes)
    if any(token in combined for token in SIDE_TOKEN_SETS["left"]):
        return "left"
    if any(token in combined for token in SIDE_TOKEN_SETS["right"]):
        return "right"
    return "left"


def _detect_limb_from_nodes(nodes):
    combined = " ".join(_strip_namespace(node).lower() for node in nodes)
    if "leg" in combined or "ankle" in combined or "knee" in combined or "foot" in combined:
        return "leg"
    return "arm"


def _top_parent(node_name):
    current = node_name
    parent = cmds.listRelatives(current, parent=True, fullPath=True) or []
    while parent:
        current = parent[0]
        parent = cmds.listRelatives(current, parent=True, fullPath=True) or []
    return current


def _candidate_nodes_for_profile(rig_root_hint=None):
    all_nodes = _all_transforms_and_joints()
    if not rig_root_hint or not cmds.objExists(rig_root_hint):
        return all_nodes
    filtered = []
    for node_name in all_nodes:
        if node_name == rig_root_hint or node_name.startswith(rig_root_hint + "|"):
            filtered.append(node_name)
    return filtered or all_nodes


def _anim_control_identity_score(node_name):
    lowered = _strip_namespace(node_name).lower()
    score = 0
    if lowered.endswith("_control"):
        score += 12
    elif lowered.endswith("_ctrl") or lowered.endswith("_ctl"):
        score += 10
    elif "control" in lowered:
        score += 6
    if any(token in lowered for token in ("transform", "group", "offset", "joint", "constraint", "locator", "shape")):
        score -= 6
    if "orient" in lowered:
        score -= 4
    return score


def _nearest_anim_control(node_name):
    if not node_name or not cmds.objExists(node_name):
        return node_name
    candidates = [(0, node_name)]
    current = node_name
    for distance in range(1, 6):
        parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
        if not parents:
            break
        current = parents[0]
        candidates.append((distance, current))
    descendants = cmds.listRelatives(node_name, allDescendents=True, type="transform", fullPath=True) or []
    for descendant in descendants[:20]:
        depth = max(1, descendant.count("|") - node_name.count("|"))
        candidates.append((depth, descendant))

    ranked = []
    for distance, candidate in candidates:
        identity_score = _anim_control_identity_score(candidate)
        if identity_score <= 0:
            continue
        ranked.append((identity_score - (distance * 2), -distance, candidate))
    ranked.sort(reverse=True)
    return ranked[0][2] if ranked else node_name


def _ranked_candidates(nodes, required_tokens, bonus_tokens, prefer_controls=False, score_fn=None):
    ranked = []
    for node_name in nodes:
        score = score_fn(node_name) if score_fn else _score_node_name(node_name, required_tokens, bonus_tokens)
        if prefer_controls:
            score += _control_candidate_adjustment(node_name)
        ranked.append((score, node_name))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item for item in ranked if item[0] > 0]


def _best_candidate(nodes, required_tokens, bonus_tokens, prefer_controls=False):
    ranked = _ranked_candidates(nodes, required_tokens, bonus_tokens, prefer_controls=prefer_controls)
    return ranked[0][1] if ranked else ""


def _best_chain_candidates(nodes, side, limb, control_type):
    segment_tokens = SEGMENT_TOKENS.get(limb, SEGMENT_TOKENS["arm"])
    prefix_tokens = [side, limb]
    fk_token = "fk" if control_type == "fk" else ""
    results = []
    used = set()
    for segment in segment_tokens:
        if control_type == "fk":
            aliases = FK_SEGMENT_ALIASES.get(limb, {}).get(segment, (segment,))

            def _fk_segment_score(node_name):
                lowered = _strip_namespace(node_name).lower()
                score = _score_node_name(node_name, prefix_tokens + [fk_token], ("ctrl", "ctl", "control"))
                score += _control_candidate_adjustment(node_name)
                if any(alias in lowered for alias in aliases):
                    score += 8
                    if segment in lowered:
                        score += 4
                else:
                    score -= 6
                return score

            ranked = _ranked_candidates(nodes, (), (), prefer_controls=False, score_fn=_fk_segment_score)
        else:
            required = list(prefix_tokens)
            if fk_token:
                required.append(fk_token)
            required.append(segment)
            ranked = _ranked_candidates(nodes, required, ("ctrl", "ctl"), prefer_controls=True)
        candidate = ""
        for _, node_name in ranked:
            resolved = _nearest_anim_control(node_name)
            if resolved in used:
                continue
            candidate = resolved
            break
        if candidate:
            used.add(candidate)
            results.append(candidate)
    return _dedupe_preserve_order([node_name for node_name in results if node_name])


def _ik_end_control_score(node_name, side, limb):
    lowered = _strip_namespace(node_name).lower()
    score = _score_node_name(node_name, (side, limb, "ik"), ("wrist", "hand", "ankle", "foot", "ctrl"))
    score += _control_candidate_adjustment(node_name)
    preferred_tokens = ("wrist", "hand") if limb == "arm" else ("ankle", "foot")
    if "ik" not in lowered:
        score -= 10
    if "fk" in lowered:
        score -= 14
    if any(token in lowered for token in preferred_tokens):
        score += 8
    if any(token in lowered for token in ("elbow", "knee", "shoulder", "hip")):
        score -= 5
    if any(token in lowered for token in ("pv", "pole", "polevector", "vector")):
        score -= 40
    return score


def _best_ik_end_control(nodes, side, limb, exclude=None):
    exclude = set(exclude or [])
    ranked = _ranked_candidates(
        nodes,
        (),
        (),
        prefer_controls=False,
        score_fn=lambda node_name: _ik_end_control_score(node_name, side, limb),
    )
    for _, node_name in ranked:
        resolved = _nearest_anim_control(node_name)
        if resolved not in exclude:
            return resolved
    return ""


def _pole_vector_score(node_name, side, limb):
    lowered = _strip_namespace(node_name).lower()
    score = _score_node_name(node_name, (side, limb), ("pv", "pole", "polevector", "vector", "ctrl"))
    score += _control_candidate_adjustment(node_name)
    if "fk" in lowered:
        score -= 8
    if any(token in lowered for token in ("pv", "pole", "polevector", "vector")):
        score += 12
    if any(token in lowered for token in ("wrist", "hand", "ankle", "foot")):
        score -= 10
    if any(token in lowered for token in ("ikhandle", "effector")):
        score -= 12
    return score


def _best_pole_vector_control(nodes, side, limb, exclude=None):
    exclude = set(exclude or [])
    ranked = _ranked_candidates(
        nodes,
        (),
        (),
        prefer_controls=False,
        score_fn=lambda node_name: _pole_vector_score(node_name, side, limb),
    )
    for _, node_name in ranked:
        resolved = _nearest_anim_control(node_name)
        if resolved not in exclude:
            return resolved
    return ""


def _detect_switch_attr(nodes, side, limb):
    token_sets = (("ikfk",), ("fkik",), ("ik_fk",), ("fk_ik",), ("blend",), ("ik", "fk"))
    candidates = []
    for node_name in nodes:
        attr_names = _dedupe_preserve_order((cmds.listAttr(node_name, keyable=True) or []) + (cmds.listAttr(node_name, userDefined=True) or []))
        for attr_name in attr_names:
            lowered = attr_name.lower()
            token_score = 0
            for token_group in token_sets:
                if all(token in lowered for token in token_group):
                    token_score += 6
            if token_score <= 0:
                continue
            score = token_score
            short = _strip_namespace(node_name).lower()
            if any(alias in short for alias in SIDE_TOKEN_SETS.get(side, (side,))):
                score += 1
            if limb in short:
                score += 1
            candidates.append((score, "{0}.{1}".format(node_name, attr_name)))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][1] if candidates else ""


def _detect_match_chain(nodes, side, limb):
    segment_tokens = SEGMENT_TOKENS.get(limb, SEGMENT_TOKENS["arm"])
    results = []
    for segment in segment_tokens:
        candidate = _best_candidate(nodes, (side, limb, segment), ("jnt", "joint", "bind", "result", "drv"))
        if candidate:
            results.append(candidate)
    return results


def _resolve_profile_node(node_name, rig_root_hint=""):
    if not node_name:
        return ""
    if cmds.objExists(node_name):
        return node_name
    stripped = _strip_namespace(node_name)
    candidates = []
    for candidate in _all_transforms_and_joints():
        if _strip_namespace(candidate) != stripped:
            continue
        score = 0
        if rig_root_hint and cmds.objExists(rig_root_hint):
            if candidate.startswith(rig_root_hint + "|"):
                score += 10
            root_short = _strip_namespace(rig_root_hint)
            if root_short and root_short in candidate:
                score += 5
        if _namespace_prefix(node_name) and _namespace_prefix(node_name) == _namespace_prefix(candidate):
            score += 3
        candidates.append((score, candidate))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][1] if candidates else ""


def _resolve_profile_attr(attr_path, rig_root_hint=""):
    if not attr_path or "." not in attr_path:
        return ""
    node_name, attr_name = attr_path.rsplit(".", 1)
    resolved = _resolve_profile_node(node_name, rig_root_hint=rig_root_hint)
    if not resolved:
        return ""
    plug = "{0}.{1}".format(resolved, attr_name)
    return plug if cmds.objExists(plug) else ""


class MayaAnimWorkflowController(object):
    def __init__(self):
        self.driver_node = ""
        self.release_space = "world"
        self.bake_mode = "frames"
        self.bake_range = "playback"
        self.dynamic_parenting_controller = maya_dynamic_parenting_tool.MayaDynamicParentingController() if MAYA_AVAILABLE else None
        self.contact_hold_controller = maya_contact_hold.MayaContactHoldController() if MAYA_AVAILABLE else None
        self.surface_contact_controller = None
        self.animators_pencil_controller = maya_animators_pencil.AnimatorsPencilController() if MAYA_AVAILABLE else None
        self.animation_assistant_controller = None
        self.animation_styling_controller = None
        self.control_picker_controller = maya_control_picker.ControlPickerController() if MAYA_AVAILABLE else None
        self.history_timeline_controller = maya_history_timeline.MayaHistoryTimelineController() if MAYA_AVAILABLE else None
        self.timing_controller = None
        self.onion_controller = maya_onion_skin.MayaOnionSkinController() if MAYA_AVAILABLE else None
        self.rotation_controller = maya_rotation_doctor.MayaRotationDoctorController() if MAYA_AVAILABLE else None
        self.skin_transfer_controller = maya_skin_transfer.MayaSkinTransferController() if MAYA_AVAILABLE else None
        self.skinning_controller = maya_skinning_cleanup.MayaSkinningCleanupController() if MAYA_AVAILABLE else None
        self.rig_scale_controller = maya_rig_scale_export.MayaRigScaleExportController() if MAYA_AVAILABLE else None
        self.video_reference_controller = maya_video_reference_tool.MayaVideoReferenceController() if MAYA_AVAILABLE else None
        self.timeline_notes_controller = None
        self.smear_frame_controller = maya_smear_frames.SmearFrameController() if MAYA_AVAILABLE else None
        self.customization_controller = maya_aminate_customization.AminateCustomizationController() if MAYA_AVAILABLE else None
        self.reference_manager_controller = maya_reference_manager.ReferencePackageController() if MAYA_AVAILABLE else None
        self.face_retarget_controller = maya_face_retarget.FaceRetargetController() if MAYA_AVAILABLE else None
        self.status_callback = None
        self.active_pivot = self._find_existing_pivot()
        self.profile_store = _load_profile_store() if MAYA_AVAILABLE else {"version": PROFILE_VERSION, "profiles": []}
        self.before_save_callback = None
        self.before_open_callback = None
        self.before_new_callback = None
        self._install_scene_callbacks()

    def _controller(self, attribute_name, factory):
        controller = getattr(self, attribute_name, None)
        if controller is None and MAYA_AVAILABLE:
            controller = factory()
            setattr(self, attribute_name, controller)
        return controller

    def get_surface_contact_controller(self):
        return self._controller("surface_contact_controller", maya_surface_contact.MayaSurfaceContactController)

    def get_animation_assistant_controller(self):
        return self._controller("animation_assistant_controller", maya_animation_assistant.AnimationAssistantController)

    def get_animation_styling_controller(self):
        return self._controller("animation_styling_controller", maya_animation_styling.AnimationStylingController)

    def get_timing_controller(self):
        return self._controller("timing_controller", maya_timing_tools.MayaTimingToolsController)

    def get_timeline_notes_controller(self):
        return self._controller("timeline_notes_controller", maya_timeline_notes.MayaTimelineNotesController)

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _set_status(self, message, ok=True):
        if self.status_callback:
            self.status_callback(message, ok)
        if ok:
            _debug(message)
        else:
            _warning(message)

    def shutdown(self):
        if self.dynamic_parenting_controller:
            try:
                self.dynamic_parenting_controller.shutdown()
            except Exception:
                pass
        if self.contact_hold_controller:
            try:
                self.contact_hold_controller.shutdown()
            except Exception:
                pass
        if self.surface_contact_controller:
            try:
                self.surface_contact_controller.shutdown()
            except Exception:
                pass
        if self.animation_assistant_controller:
            try:
                self.animation_assistant_controller.shutdown()
            except Exception:
                pass
        if self.animation_styling_controller:
            try:
                self.animation_styling_controller.shutdown()
            except Exception:
                pass
        if self.onion_controller:
            try:
                self.onion_controller.shutdown()
            except Exception:
                pass
        if self.rotation_controller:
            try:
                self.rotation_controller.shutdown()
            except Exception:
                pass
        if self.skin_transfer_controller:
            try:
                self.skin_transfer_controller.shutdown()
            except Exception:
                pass
        if self.skinning_controller:
            try:
                self.skinning_controller.shutdown()
            except Exception:
                pass
        if self.rig_scale_controller:
            try:
                self.rig_scale_controller.shutdown()
            except Exception:
                pass
        if self.video_reference_controller:
            try:
                self.video_reference_controller.shutdown()
            except Exception:
                pass
        if self.timeline_notes_controller:
            try:
                self.timeline_notes_controller.shutdown()
            except Exception:
                pass
        if self.customization_controller:
            try:
                self.customization_controller.shutdown()
            except Exception:
                pass
        if self.smear_frame_controller:
            try:
                self.smear_frame_controller.shutdown()
            except Exception:
                pass
        if self.face_retarget_controller:
            try:
                self.face_retarget_controller.shutdown()
            except Exception:
                pass
        if self.history_timeline_controller:
            try:
                self.history_timeline_controller.shutdown()
            except Exception:
                pass
        self._remove_scene_callbacks()

    def _install_scene_callbacks(self):
        if not MAYA_AVAILABLE or not om:
            return
        try:
            self.before_save_callback = om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeSave, self._before_scene_save)
            self.before_open_callback = om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeOpen, self._before_scene_open)
            self.before_new_callback = om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeNew, self._before_scene_new)
        except Exception:
            self.before_save_callback = None
            self.before_open_callback = None
            self.before_new_callback = None

    def _remove_scene_callbacks(self):
        if not MAYA_AVAILABLE or not om:
            return
        for callback_id in (self.before_save_callback, self.before_open_callback, self.before_new_callback):
            if callback_id is None:
                continue
            try:
                om.MMessage.removeCallback(callback_id)
            except Exception:
                pass
        self.before_save_callback = None
        self.before_open_callback = None
        self.before_new_callback = None

    def _before_scene_save(self, *args):
        if self.active_pivot:
            self.clear_pivot(silent=True)

    def _before_scene_open(self, *args):
        if self.active_pivot:
            self.clear_pivot(silent=True)

    def _before_scene_new(self, *args):
        if self.active_pivot:
            self.clear_pivot(silent=True)

    def _find_existing_pivot(self):
        if not MAYA_AVAILABLE or not cmds.objExists(PIVOT_GROUP_NAME):
            return ""
        children = cmds.listRelatives(PIVOT_GROUP_NAME, children=True, type="transform", fullPath=True) or []
        for child in children:
            if _get_string_attr(child, "adwPivotType") == PIVOT_TYPE:
                return child
        return ""

    def parenting_setups(self, from_selection=True):
        if not MAYA_AVAILABLE:
            return []
        if from_selection:
            selected = _selected_transforms()
            results = []
            for node_name in selected:
                data = _find_setup_for_node(node_name)
                if data:
                    results.append(data)
            if results:
                deduped = []
                seen = set()
                for item in results:
                    key = item["setup_group"]
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(item)
                return deduped
        return [data for data in (_parent_setup_data(group) for group in _find_parent_setup_groups()) if data]

    def create_temp_controls(self, driven_nodes=None):
        driven_nodes = driven_nodes or _selected_transforms()
        if not driven_nodes:
            return False, "Pick one or more controls first."
        created = []
        messages = []
        for node_name in driven_nodes:
            data, was_created, message = _create_parent_setup(node_name)
            if data:
                created.append(data)
            messages.append(message)
        if not created:
            return False, "\n".join(messages)
        return True, "\n".join(messages)

    def set_driver_from_selection(self):
        setups = self.parenting_setups(from_selection=True)
        driver = _selection_switch_target_candidate(setups)
        if not driver:
            selected = _selected_transforms()
            if not selected:
                return False, "Pick the thing that moves and the hand, gun, magazine, or prop it should follow next."
            driver = selected[-1]
        setup = _find_setup_for_node(driver)
        if setup:
            return False, "Pick the real hand, gun, prop, or other target, not one of this tool's helper controls."
        self.driver_node = driver
        return True, "Next follow target set to {0}.".format(_short_name(driver))

    def add_grab_current(self, driver_node="", event_action="follow"):
        setups = self.parenting_setups(from_selection=True)
        if not setups:
            return False, "Pick the control that should move first. If needed, click Make Helpers before switching."
        picked_target = _selection_switch_target_candidate(setups)
        driver_node = driver_node or picked_target or self.driver_node
        if not driver_node or not cmds.objExists(driver_node):
            return False, "Pick the moving control and the hand, gun, magazine, or prop it should follow next."
        self.driver_node = driver_node
        for setup_data in setups:
            _preserve_control_world(setup_data, driver_node, "grab_release", driver_node)
            _record_parenting_event(setup_data, event_action, driver_node, "grab_release")
        if event_action == "pickup":
            return True, "Made {0} picked control(s) pick up {1} on this frame.".format(len(setups), _short_name(driver_node))
        if event_action == "pass":
            return True, "Passed {0} picked control(s) to {1} on this frame.".format(len(setups), _short_name(driver_node))
        return True, "Switched {0} picked control(s) to follow {1} on this frame.".format(len(setups), _short_name(driver_node))

    def add_release_current(self, release_mode="world", event_action="release"):
        setups = self.parenting_setups(from_selection=True)
        if not setups:
            return False, "Pick the control that should stop following something first."
        _, _, _, world_locator = _ensure_root_hierarchy()
        for setup_data in setups:
            if release_mode == "original" and setup_data["original_parent"] and cmds.objExists(setup_data["original_parent"]):
                target = setup_data["original_parent"]
                label = "original"
            else:
                target = world_locator
                label = "world"
            _preserve_control_world(setup_data, target, label, "")
            _record_parenting_event(setup_data, event_action, "", label)
        if release_mode == "original":
            destination = "their original parent/object"
        else:
            destination = "world space"
        if event_action == "drop":
            return True, "Dropped {0} picked control(s) to {1} on this frame.".format(len(setups), destination)
        return True, "Made {0} picked control(s) stop following and go back to {1} on this frame.".format(len(setups), destination)

    def normalize_transitions(self):
        setups = self.parenting_setups(from_selection=True)
        if not setups:
            return False, "Pick the control with the pop or jump first."
        for setup_data in setups:
            current_target = _highest_weight_target(setup_data["space_constraint"])
            if not current_target:
                continue
            current_space = _get_string_attr(setup_data["setup_group"], "adwCurrentSpace", "world")
            current_driver = _get_string_attr(setup_data["setup_group"], "adwCurrentDriver", "")
            _preserve_control_world(setup_data, current_target, current_space, current_driver)
        return True, "Checked {0} picked control(s) and fixed any small pops on this frame.".format(len(setups))

    def bake_to_rig(self, clear_after=False):
        setups = self.parenting_setups(from_selection=False)
        if not setups:
            return False, "There are no helper controls to bake back."
        start_time, end_time = _bake_range_from_mode(self.bake_range)
        if self.bake_mode == "frames":
            driven_nodes = [setup_data["driven"] for setup_data in setups if setup_data["driven"]]
            try:
                cmds.bakeResults(
                    driven_nodes,
                    simulation=True,
                    time=(start_time, end_time),
                    sampleBy=1,
                    disableImplicitControl=True,
                    preserveOutsideKeys=True,
                    sparseAnimCurveBake=False,
                    at=("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"),
                )
            except Exception as exc:
                return False, "Bake Results failed: {0}".format(exc)
        else:
            baked_times = set()
            for setup_data in setups:
                for time_value in _time_for_manual_bake(setup_data, start_time, end_time):
                    baked_times.add(time_value)
            current_time = cmds.currentTime(query=True)
            try:
                for time_value in sorted(baked_times):
                    cmds.currentTime(time_value, edit=True)
                    for setup_data in setups:
                        _set_keyable_channels(setup_data["driven"], ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
            finally:
                cmds.currentTime(current_time, edit=True)

        for setup_data in setups:
            if setup_data["driven_constraint"] and cmds.objExists(setup_data["driven_constraint"]):
                try:
                    cmds.delete(setup_data["driven_constraint"])
                except Exception:
                    pass
                _set_string_attr(setup_data["setup_group"], "adwDrivenConstraint", "")

        if clear_after:
            self.clear_temp_setups(setups)
            return True, "Baked {0} helper setup(s) back to the rig and cleared them.".format(len(setups))
        return True, "Baked {0} helper setup(s) back to the rig.".format(len(setups))

    def clear_temp_setups(self, setups=None):
        setups = setups or self.parenting_setups(from_selection=False)
        if not setups:
            return False, "There are no helper controls to clear."
        for setup_data in setups:
            try:
                cmds.delete(setup_data["setup_group"])
            except Exception:
                pass
        return True, "Cleared {0} helper setup(s).".format(len(setups))

    def create_pivot(self, mode):
        targets = _selected_transforms()
        if not targets:
            return False, "Pick one or more objects first."
        self.clear_pivot(silent=True)
        _, _, pivot_group, _ = _ensure_root_hierarchy()
        pivot_ctrl = _draw_temp_control(_unique_name(PIVOT_CTRL_NAME), 1.6)
        pivot_ctrl = cmds.parent(pivot_ctrl, pivot_group)[0]
        _set_string_attr(pivot_ctrl, "adwPivotType", PIVOT_TYPE)
        _set_string_attr(pivot_ctrl, "adwPivotTargets", json.dumps(targets))
        if mode == "centered":
            positions = [_world_translation(node_name) for node_name in targets]
            pivot_position = [sum(values[index] for values in positions) / float(len(positions)) for index in range(3)]
        elif mode == "last_object":
            pivot_position = _world_translation(targets[-1])
        else:
            pivot_position = [0.0, 0.0, 0.0]
        _set_world_translation(pivot_ctrl, pivot_position)
        _zero_rotation(pivot_ctrl)
        self.active_pivot = pivot_ctrl
        return True, "Made a temporary pivot for {0} object(s).".format(len(targets))

    def edit_pivot_position(self):
        if not self.active_pivot or not cmds.objExists(self.active_pivot):
            return False, "Create a pivot first."
        cmds.select(self.active_pivot, replace=True)
        return True, "Pivot selected so you can move it."

    def apply_pivot_rotation(self):
        if not self.active_pivot or not cmds.objExists(self.active_pivot):
            return False, "Create a pivot first."
        rotation_values = _current_rotation_values(self.active_pivot)
        if all(abs(value) < EPSILON for value in rotation_values):
            return False, "Rotate the pivot marker first, then apply it."
        try:
            targets = json.loads(_get_string_attr(self.active_pivot, "adwPivotTargets"))
        except Exception:
            targets = []
        targets = [node_name for node_name in targets if cmds.objExists(node_name)]
        if not targets:
            return False, "The saved pivot objects are missing."
        pivot_position = _world_translation(self.active_pivot)
        for node_name in targets:
            _apply_matrix_around_pivot(node_name, pivot_position, rotation_values)
            _set_keyable_channels(node_name, ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
        _zero_rotation(self.active_pivot)
        return True, "Rotated {0} object(s) around the pivot.".format(len(targets))

    def clear_pivot(self, silent=False):
        pivot_name = self.active_pivot or self._find_existing_pivot()
        if not pivot_name or not cmds.objExists(pivot_name):
            self.active_pivot = ""
            return (True, "") if silent else (True, "There is no pivot to clear.")
        try:
            cmds.delete(pivot_name)
        except Exception:
            pass
        self.active_pivot = ""
        return (True, "") if silent else (True, "Cleared the pivot marker.")

    def profile_names(self):
        profiles = self.profile_store.get("profiles", [])
        return [profile.get("profile_name", "") for profile in profiles if profile.get("profile_name")]

    def detect_profile(self):
        selected = _selected_transforms()
        search_nodes = selected or _all_transforms_and_joints()
        side = _detect_side_from_nodes(search_nodes)
        limb = _detect_limb_from_nodes(search_nodes)
        rig_root = _top_parent(selected[0]) if selected else ""

        def _switch_score(plug_name):
            if not plug_name or "." not in plug_name:
                return -999
            node_name, attr_name = plug_name.rsplit(".", 1)
            lowered_attr = attr_name.lower()
            score = 0
            for token_group in (("ikfk",), ("fkik",), ("ik_fk",), ("fk_ik",), ("blend",), ("ik", "fk")):
                if all(token in lowered_attr for token in token_group):
                    score += 6
            short = _strip_namespace(node_name).lower()
            if any(alias in short for alias in SIDE_TOKEN_SETS.get(side, (side,))):
                score += 1
            if limb in short:
                score += 1
            return score

        def _match_score(nodes):
            return sum(_score_node_name(node_name, (side, limb), ("jnt", "joint", "bind", "result", "drv")) for node_name in nodes)

        def _detect_from_candidates(candidates):
            pole_vector_control = _best_pole_vector_control(candidates, side, limb)
            ik_control = _best_ik_end_control(candidates, side, limb, exclude=(pole_vector_control,))
            if not pole_vector_control:
                pole_vector_control = _best_pole_vector_control(candidates, side, limb, exclude=(ik_control,))
            return {
                "fk_controls": _best_chain_candidates(candidates, side, limb, "fk"),
                "ik_control": ik_control,
                "pole_vector_control": pole_vector_control,
                "switch_attr": _detect_switch_attr(candidates, side, limb),
                "match_nodes": _detect_match_chain(candidates, side, limb),
            }

        candidates = _candidate_nodes_for_profile(rig_root_hint=rig_root)
        detected_data = _detect_from_candidates(candidates)
        if (
            len(detected_data["fk_controls"]) < 3
            or not detected_data["ik_control"]
            or not detected_data["pole_vector_control"]
            or not detected_data["switch_attr"]
            or len(detected_data["match_nodes"]) < 3
        ):
            fallback_data = _detect_from_candidates(_all_transforms_and_joints())
            if len(fallback_data["fk_controls"]) >= len(detected_data["fk_controls"]):
                detected_data["fk_controls"] = fallback_data["fk_controls"]
            if _ik_end_control_score(fallback_data["ik_control"], side, limb) >= _ik_end_control_score(detected_data["ik_control"], side, limb) + 5:
                detected_data["ik_control"] = fallback_data["ik_control"]
            if _pole_vector_score(fallback_data["pole_vector_control"], side, limb) >= _pole_vector_score(detected_data["pole_vector_control"], side, limb) + 5:
                detected_data["pole_vector_control"] = fallback_data["pole_vector_control"]
            if _switch_score(fallback_data["switch_attr"]) >= _switch_score(detected_data["switch_attr"]) + 2:
                detected_data["switch_attr"] = fallback_data["switch_attr"]
            if _match_score(fallback_data["match_nodes"]) >= _match_score(detected_data["match_nodes"]) + 3:
                detected_data["match_nodes"] = fallback_data["match_nodes"]
        if detected_data["ik_control"] and detected_data["ik_control"] == detected_data["pole_vector_control"]:
            distinct_ik = _best_ik_end_control(_all_transforms_and_joints(), side, limb, exclude=(detected_data["pole_vector_control"],))
            if distinct_ik:
                detected_data["ik_control"] = distinct_ik
            distinct_pv = _best_pole_vector_control(_all_transforms_and_joints(), side, limb, exclude=(detected_data["ik_control"],))
            if distinct_pv:
                detected_data["pole_vector_control"] = distinct_pv

        detected = {
            "profile_name": "{0}_{1}".format(side, limb),
            "rig_root": rig_root,
            "namespace_hint": _namespace_prefix(selected[0]) if selected else "",
            "limb_type": limb,
            "side": side,
            "fk_controls": detected_data["fk_controls"],
            "ik_controls": _dedupe_preserve_order(
                [detected_data["ik_control"], detected_data["pole_vector_control"]]
            ),
            "ik_control": detected_data["ik_control"],
            "pole_vector_control": detected_data["pole_vector_control"],
            "switch_attr": detected_data["switch_attr"],
            "fk_value": 0.0,
            "ik_value": 1.0,
            "extra_controls": [],
            "match_nodes": detected_data["match_nodes"],
        }
        issues = []
        if len(detected_data["fk_controls"]) < 3:
            issues.append("Could not confidently find all 3 FK controls.")
        if not detected_data["ik_control"]:
            issues.append("Could not detect an IK control.")
        if not detected_data["pole_vector_control"]:
            issues.append("Could not detect a pole-vector control.")
        if detected_data["ik_control"] and detected_data["ik_control"] == detected_data["pole_vector_control"]:
            issues.append("The hand or foot control and the elbow or knee guide came back as the same object. Check the IK boxes.")
        if not detected_data["switch_attr"]:
            issues.append("Could not detect an IK/FK switch attribute.")
        if len(detected_data["match_nodes"]) < 3:
            issues.append("Could not detect a full match chain; IK -> FK may need manual setup.")
        return detected, issues

    def _normalize_profile(self, profile):
        normalized = dict(profile)
        normalized["profile_name"] = normalized.get("profile_name", "").strip()
        normalized["rig_root"] = normalized.get("rig_root", "").strip()
        normalized["namespace_hint"] = normalized.get("namespace_hint", "").strip()
        normalized["limb_type"] = (normalized.get("limb_type", "arm") or "arm").strip()
        normalized["side"] = (normalized.get("side", "left") or "left").strip()
        normalized["fk_controls"] = _dedupe_preserve_order(
            [item.strip() for item in normalized.get("fk_controls", []) if item and item.strip()]
        )
        normalized["ik_control"] = normalized.get("ik_control", "").strip()
        normalized["pole_vector_control"] = normalized.get("pole_vector_control", "").strip()
        ik_controls = [item.strip() for item in normalized.get("ik_controls", []) if item and item.strip()]
        if not ik_controls:
            ik_controls = [normalized["ik_control"], normalized["pole_vector_control"]]
        else:
            if normalized["ik_control"]:
                ik_controls.insert(0, normalized["ik_control"])
            if normalized["pole_vector_control"]:
                ik_controls.append(normalized["pole_vector_control"])
        normalized["ik_controls"] = _dedupe_preserve_order([item for item in ik_controls if item])
        normalized["switch_attr"] = normalized.get("switch_attr", "").strip()
        normalized["fk_value"] = float(normalized.get("fk_value", 0.0))
        normalized["ik_value"] = float(normalized.get("ik_value", 1.0))
        normalized["extra_controls"] = _dedupe_preserve_order(
            [item.strip() for item in normalized.get("extra_controls", []) if item and item.strip()]
        )
        normalized["match_nodes"] = _dedupe_preserve_order(
            [item.strip() for item in normalized.get("match_nodes", []) if item and item.strip()]
        )
        return normalized

    def _profile_from_fields(self, fields):
        profile = {
            "profile_name": fields.get("profile_name", "").strip(),
            "rig_root": fields.get("rig_root", "").strip(),
            "namespace_hint": fields.get("namespace_hint", "").strip(),
            "limb_type": fields.get("limb_type", "arm").strip() or "arm",
            "side": fields.get("side", "left").strip() or "left",
            "fk_controls": [item.strip() for item in fields.get("fk_controls", []) if item.strip()],
            "ik_controls": [item.strip() for item in fields.get("ik_controls", []) if item.strip()],
            "ik_control": fields.get("ik_control", "").strip(),
            "pole_vector_control": fields.get("pole_vector_control", "").strip(),
            "switch_attr": fields.get("switch_attr", "").strip(),
            "fk_value": float(fields.get("fk_value", 0.0)),
            "ik_value": float(fields.get("ik_value", 1.0)),
            "extra_controls": [item.strip() for item in fields.get("extra_controls", []) if item.strip()],
            "match_nodes": [item.strip() for item in fields.get("match_nodes", []) if item.strip()],
        }
        return self._normalize_profile(profile)

    def save_profile(self, fields):
        profile = self._profile_from_fields(fields)
        if not profile["profile_name"]:
            return False, "Give this saved switch a name first."
        profiles = self.profile_store.setdefault("profiles", [])
        replaced = False
        for index, existing in enumerate(profiles):
            if existing.get("profile_name") == profile["profile_name"]:
                profiles[index] = profile
                replaced = True
                break
        if not replaced:
            profiles.append(profile)
        _save_profile_store(self.profile_store)
        return True, "Saved switch '{0}'.".format(profile["profile_name"])

    def load_profile(self, profile_name):
        for profile in self.profile_store.get("profiles", []):
            if profile.get("profile_name") == profile_name:
                return True, self._normalize_profile(profile)
        return False, "Could not find saved switch '{0}'.".format(profile_name)

    def _resolved_profile(self, profile):
        profile = self._normalize_profile(profile)
        rig_root = _resolve_profile_node(profile.get("rig_root", ""), rig_root_hint=profile.get("rig_root", ""))
        resolved = dict(profile)
        resolved["rig_root"] = rig_root or profile.get("rig_root", "")
        resolved["fk_controls"] = [_resolve_profile_node(node_name, rig_root_hint=resolved["rig_root"]) for node_name in profile.get("fk_controls", [])]
        resolved["ik_controls"] = [_resolve_profile_node(node_name, rig_root_hint=resolved["rig_root"]) for node_name in profile.get("ik_controls", [])]
        resolved["ik_control"] = _resolve_profile_node(profile.get("ik_control", ""), rig_root_hint=resolved["rig_root"])
        resolved["pole_vector_control"] = _resolve_profile_node(profile.get("pole_vector_control", ""), rig_root_hint=resolved["rig_root"])
        resolved["ik_controls"] = _dedupe_preserve_order(
            [resolved["ik_control"], resolved["pole_vector_control"]] + [node_name for node_name in resolved["ik_controls"] if node_name]
        )
        resolved["switch_attr"] = _resolve_profile_attr(profile.get("switch_attr", ""), rig_root_hint=resolved["rig_root"])
        resolved["extra_controls"] = [_resolve_profile_node(node_name, rig_root_hint=resolved["rig_root"]) for node_name in profile.get("extra_controls", [])]
        resolved["match_nodes"] = [_resolve_profile_node(node_name, rig_root_hint=resolved["rig_root"]) for node_name in profile.get("match_nodes", [])]
        return resolved

    def _validate_profile(self, profile, direction):
        profile = self._resolved_profile(profile)
        issues = []
        if len([node_name for node_name in profile["fk_controls"] if node_name]) < 3:
            issues.append("This saved switch needs 3 FK controls.")
        if not profile["ik_control"]:
            issues.append("Profile needs an IK control.")
        if not profile["pole_vector_control"]:
            issues.append("Profile needs a pole-vector control.")
        if not profile["switch_attr"]:
            issues.append("Profile needs a switch attribute.")
        if direction == "ik_to_fk" and len([node_name for node_name in profile["match_nodes"] if node_name]) < 3:
            issues.append("IK -> FK requires a detected or assigned match chain.")
        return profile, issues

    def _key_switch_context(self, profile, source_value, current_time):
        previous_time = current_time - 1.0
        if profile["switch_attr"]:
            node_name, attr_name = profile["switch_attr"].rsplit(".", 1)
            cmds.currentTime(previous_time, edit=True)
            cmds.setAttr(profile["switch_attr"], source_value)
            cmds.setKeyframe(node_name, attribute=attr_name)
        nodes = profile["fk_controls"] + profile.get("ik_controls", []) + profile["extra_controls"]
        for node_name in _dedupe_preserve_order(nodes):
            if node_name and cmds.objExists(node_name):
                _set_keyable_channels(node_name, ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
        cmds.currentTime(current_time, edit=True)

    def switch_fk_to_ik(self, profile):
        profile, issues = self._validate_profile(profile, "fk_to_ik")
        if issues:
            return False, "; ".join(issues)
        current_time = float(cmds.currentTime(query=True))
        self._key_switch_context(profile, profile["fk_value"], current_time)
        source_points = profile["match_nodes"] if len([node_name for node_name in profile["match_nodes"] if node_name]) >= 3 else profile["fk_controls"]
        source_points = source_points[:3]
        start_point = _world_translation(source_points[0])
        middle_point = _world_translation(source_points[1])
        end_point = _world_translation(source_points[2])
        _set_world_translation(profile["ik_control"], end_point)
        _set_world_rotation(profile["ik_control"], _world_rotation(source_points[2]))
        _set_world_translation(profile["pole_vector_control"], _pole_vector_position(start_point, middle_point, end_point))
        _set_keyable_channels(profile["ik_control"], ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
        _set_keyable_channels(profile["pole_vector_control"], ("translateX", "translateY", "translateZ"))
        node_name, attr_name = profile["switch_attr"].rsplit(".", 1)
        cmds.setAttr(profile["switch_attr"], profile["ik_value"])
        cmds.setKeyframe(node_name, attribute=attr_name)
        return True, "Switched from FK to IK on frame {0}.".format(int(current_time))

    def switch_ik_to_fk(self, profile):
        profile, issues = self._validate_profile(profile, "ik_to_fk")
        if issues:
            return False, "; ".join(issues)
        current_time = float(cmds.currentTime(query=True))
        self._key_switch_context(profile, profile["ik_value"], current_time)
        for fk_control, match_node in zip(profile["fk_controls"][:3], profile["match_nodes"][:3]):
            if fk_control and match_node:
                _set_world_rotation(fk_control, _world_rotation(match_node))
                _set_keyable_channels(fk_control, ("rotateX", "rotateY", "rotateZ"))
        node_name, attr_name = profile["switch_attr"].rsplit(".", 1)
        cmds.setAttr(profile["switch_attr"], profile["fk_value"])
        cmds.setKeyframe(node_name, attribute=attr_name)
        return True, "Switched from IK to FK on frame {0}.".format(int(current_time))


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

        if MQtUtil.mainWindow() is not None:
            _WindowBase = type("MayaAnimWorkflowWindowBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
        else:
            _WindowBase = type("MayaAnimWorkflowWindowBase", (QtWidgets.QDialog,), {})
    except Exception:
        _WindowBase = type("MayaAnimWorkflowWindowBase", (QtWidgets.QDialog,), {})


    class MayaAnimWorkflowWindow(_WindowBase):
        def __init__(self, controller, parent=None, initial_tab=0):
            super(MayaAnimWorkflowWindow, self).__init__(parent)
            self.controller = controller
            self._toolbar_extras_hidden_for_close = False
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Aminate")
            self.setMinimumSize(DOCKED_WORKFLOW_MIN_WIDTH, DOCKED_WORKFLOW_MIN_HEIGHT)
            start_width, start_height = _screen_limited_size(
                1180,
                860,
                min_width=DOCKED_WORKFLOW_MIN_WIDTH,
                min_height=DOCKED_WORKFLOW_MIN_HEIGHT,
            )
            self.resize(start_width, start_height)
            if hasattr(self, "setSizePolicy"):
                self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
            self._build_ui()
            self._populate_profile_names()
            self._set_initial_tab(initial_tab)
            self._key_filter_installed = False
            if os.environ.get(AMINATE_ENABLE_APP_KEY_FILTER) == "1":
                self._install_key_passthrough_filter()

        def _install_key_passthrough_filter(self):
            app = QtWidgets.QApplication.instance()
            if not app:
                return
            try:
                app.installEventFilter(self)
                self._key_filter_installed = True
            except Exception:
                pass

        def _remove_key_passthrough_filter(self):
            app = QtWidgets.QApplication.instance()
            if not app:
                return
            try:
                app.removeEventFilter(self)
                self._key_filter_installed = False
            except Exception:
                pass

        def _is_widget_inside_window(self, widget):
            walker = widget
            while walker is not None:
                if walker is self:
                    return True
                try:
                    walker = walker.parentWidget()
                except Exception:
                    return False
            return False

        def _is_text_entry_widget(self, widget):
            text_widgets = (
                QtWidgets.QLineEdit,
                QtWidgets.QPlainTextEdit,
                QtWidgets.QTextEdit,
                QtWidgets.QSpinBox,
                QtWidgets.QDoubleSpinBox,
                QtWidgets.QComboBox,
            )
            return bool(widget and isinstance(widget, text_widgets))

        def _is_plain_s_key_event(self, event):
            if not event or event.type() != QtCore.QEvent.KeyPress:
                return False
            if event.key() != QtCore.Qt.Key_S:
                return False
            return int(event.modifiers()) == int(QtCore.Qt.NoModifier)

        def _set_key_from_maya_hotkey(self):
            if not MAYA_AVAILABLE or not cmds:
                return False
            try:
                if mel:
                    mel.eval('performSetKeyframeArgList 1 {"0", "animationList"}')
                else:
                    cmds.setKeyframe()
                self._set_status("Set key on current selection.", True)
                return True
            except Exception as exc:
                self._set_status("Could not set key from S: {0}".format(exc), False)
                return False

        def eventFilter(self, obj, event):
            try:
                if self._is_plain_s_key_event(event) and self._is_widget_inside_window(obj):
                    focus_widget = QtWidgets.QApplication.focusWidget()
                    if self._is_text_entry_widget(focus_widget):
                        return False
                    if self._set_key_from_maya_hotkey():
                        return True
            except Exception:
                pass
            return super(MayaAnimWorkflowWindow, self).eventFilter(obj, event)

        def _make_scroll_tab(self):
            page = QtWidgets.QWidget()
            page.setObjectName("mayaAnimWorkflowTabPage")
            page.setProperty("aminateTabPage", True)
            if hasattr(page, "setSizePolicy"):
                page.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            scroll = QtWidgets.QScrollArea()
            scroll.setObjectName("mayaAnimWorkflowTabScroll")
            scroll.setMinimumSize(0, 0)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAsNeeded", QtCore.Qt.ScrollBarAsNeeded))
            scroll.setVerticalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAsNeeded", QtCore.Qt.ScrollBarAsNeeded))
            if hasattr(scroll, "setSizePolicy"):
                scroll.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
            scroll.setWidget(page)
            return page, scroll

        def _build_ui(self):
            self.setStyleSheet(AMINATE_WINDOW_STYLESHEET)
            main_layout = QtWidgets.QVBoxLayout(self)
            _set_no_size_constraint(main_layout)
            main_layout.setContentsMargins(8, 8, 8, 8)
            main_layout.setSpacing(8)
            self.tab_widget = QtWidgets.QTabWidget()
            self.tab_widget.setObjectName("mayaAnimWorkflowTabWidget")
            _allow_tiny_shell_widget(self.tab_widget)
            self.tab_widget.setUsesScrollButtons(False)
            self.tab_widget.setMovable(True)
            self.tab_widget.setElideMode(_qt_flag("TextElideMode", "ElideRight", QtCore.Qt.ElideRight))
            self._configure_main_tab_bar()
            self.tab_widget.setCornerWidget(self._build_tab_navigation_button(-1), QtCore.Qt.TopLeftCorner)
            self.tab_widget.setCornerWidget(self._build_tab_navigation_button(1), QtCore.Qt.TopRightCorner)
            main_layout.addWidget(self.tab_widget, 1)
            self.parenting_page, self.parenting_tab = self._make_scroll_tab()
            self.contact_hold_page, self.contact_hold_tab = self._make_scroll_tab()
            self.surface_contact_page, self.surface_contact_tab = self._make_scroll_tab()
            self.pivot_page, self.pivot_tab = self._make_scroll_tab()
            self.ikfk_page, self.ikfk_tab = self._make_scroll_tab()
            self.face_retarget_page, self.face_retarget_tab = self._make_scroll_tab()
            self.control_picker_page, self.control_picker_tab = self._make_scroll_tab()
            self.animators_pencil_page, self.animators_pencil_tab = self._make_scroll_tab()
            self.animation_assistant_page, self.animation_assistant_tab = self._make_scroll_tab()
            self.animation_styling_page, self.animation_styling_tab = self._make_scroll_tab()
            self.history_timeline_page, self.history_timeline_tab = self._make_scroll_tab()
            self.onion_page, self.onion_tab = self._make_scroll_tab()
            self.rotation_page, self.rotation_tab = self._make_scroll_tab()
            self.skin_page, self.skin_tab = self._make_scroll_tab()
            self.rig_scale_page, self.rig_scale_tab = self._make_scroll_tab()
            self.video_page, self.video_tab = self._make_scroll_tab()
            self.timeline_page, self.timeline_tab = self._make_scroll_tab()
            self.smear_frames_page, self.smear_frames_tab = self._make_scroll_tab()
            self.customization_page, self.customization_tab = self._make_scroll_tab()
            self.guide_page, self.guide_tab = self._make_scroll_tab()
            self.student_core_page, self.student_core_tab = self._make_scroll_tab()
            self.timing_page, self.timing_tab = self._make_scroll_tab()
            self.reference_manager_page, self.reference_manager_tab = self._make_scroll_tab()
            self.tab_widget.addTab(self.guide_tab, TAB_GUIDE)
            self.tab_widget.addTab(self.student_core_tab, TAB_STUDENT_CORE)
            self.tab_widget.addTab(self.timing_tab, TAB_TIMING)
            self.tab_widget.addTab(self.reference_manager_tab, TAB_REFERENCE_MANAGER)
            self.tab_widget.addTab(self.parenting_tab, TAB_PARENTING)
            self.tab_widget.addTab(self.contact_hold_tab, TAB_CONTACT_HOLD)
            self.tab_widget.addTab(self.surface_contact_tab, TAB_SURFACE_CONTACT)
            self.tab_widget.addTab(self.pivot_tab, TAB_PIVOT)
            self.tab_widget.addTab(self.ikfk_tab, TAB_IKFK)
            self.tab_widget.addTab(self.face_retarget_tab, TAB_FACE_RETARGET)
            self.tab_widget.addTab(self.control_picker_tab, TAB_CONTROL_PICKER)
            self.tab_widget.addTab(self.animators_pencil_tab, TAB_ANIMATORS_PENCIL)
            self.tab_widget.addTab(self.animation_assistant_tab, TAB_ANIMATION_ASSISTANT)
            self.tab_widget.addTab(self.animation_styling_tab, TAB_ANIMATION_STYLING)
            self.tab_widget.addTab(self.history_timeline_tab, TAB_HISTORY_TIMELINE)
            self.tab_widget.addTab(self.onion_tab, TAB_ONION)
            self.tab_widget.addTab(self.rotation_tab, TAB_ROTATION)
            self.tab_widget.addTab(self.skin_tab, TAB_SKIN)
            self.tab_widget.addTab(self.rig_scale_tab, TAB_RIG_SCALE)
            self.tab_widget.addTab(self.video_tab, TAB_VIDEO)
            self.tab_widget.addTab(self.timeline_tab, TAB_TIMELINE)
            self.tab_widget.addTab(self.smear_frames_tab, TAB_SMEAR_FRAMES)
            self.tab_widget.addTab(self.customization_tab, TAB_CUSTOMIZATION)
            self._refresh_tab_tooltips()
            self.tab_intro_labels = {}
            self._built_tab_names = set()
            self._tab_builders = {
                TAB_GUIDE: self._build_guide_tab,
                TAB_STUDENT_CORE: self._build_student_core_tab,
                TAB_TIMING: self._build_timing_tab,
                TAB_REFERENCE_MANAGER: self._build_reference_manager_tab,
                TAB_PARENTING: self._build_parenting_tab,
                TAB_CONTACT_HOLD: self._build_contact_hold_tab,
                TAB_SURFACE_CONTACT: self._build_surface_contact_tab,
                TAB_PIVOT: self._build_pivot_tab,
                TAB_IKFK: self._build_ikfk_tab,
                TAB_FACE_RETARGET: self._build_face_retarget_tab,
                TAB_CONTROL_PICKER: self._build_control_picker_tab,
                TAB_ANIMATORS_PENCIL: self._build_animators_pencil_tab,
                TAB_ANIMATION_ASSISTANT: self._build_animation_assistant_tab,
                TAB_ANIMATION_STYLING: self._build_animation_styling_tab,
                TAB_HISTORY_TIMELINE: self._build_history_timeline_tab,
                TAB_ONION: self._build_onion_tab,
                TAB_ROTATION: self._build_rotation_tab,
                TAB_SKIN: self._build_skin_tab,
                TAB_RIG_SCALE: self._build_rig_scale_tab,
                TAB_VIDEO: self._build_video_tab,
                TAB_TIMELINE: self._build_timeline_tab,
                TAB_SMEAR_FRAMES: self._build_smear_frames_tab,
                TAB_CUSTOMIZATION: self._build_customization_tab,
            }
            self._ensure_tab_content(self.tab_widget.currentIndex())
            self.tab_widget.currentChanged.connect(self._update_tab_navigation_buttons)
            self.tab_widget.currentChanged.connect(self._ensure_tab_content)
            self._update_tab_navigation_buttons()
            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setObjectName("mayaAnimWorkflowStatusLabel")
            _allow_tiny_shell_widget(self.status_label)
            self.status_label.setWordWrap(True)
            main_layout.addWidget(self.status_label)
            footer_layout = QtWidgets.QHBoxLayout()
            _set_no_size_constraint(footer_layout)
            self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
            self.brand_label.setObjectName("mayaAnimWorkflowBrandLabel")
            _allow_tiny_shell_widget(self.brand_label)
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            self.brand_label.setWordWrap(True)
            footer_layout.addWidget(self.brand_label, 1)
            self.version_label = QtWidgets.QLabel(VERSION_LABEL)
            self.version_label.setObjectName("mayaAnimWorkflowVersionLabel")
            _allow_tiny_shell_widget(self.version_label)
            self.version_label.setToolTip("Current public student release label.")
            footer_layout.addWidget(self.version_label)
            self.donate_button = QtWidgets.QPushButton("Donate")
            self.donate_button.setMinimumWidth(0)
            _style_donate_button(self.donate_button)
            self.donate_button.setToolTip("Open Amir's PayPal donate link. Set AMIR_PAYPAL_DONATE_URL or AMIR_DONATE_URL to customize it.")
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

        def _ensure_tab_content(self, index):
            if not hasattr(self, "tab_widget") or index is None or index < 0:
                return
            tab_name = self.tab_widget.tabText(index)
            if tab_name in getattr(self, "_built_tab_names", set()):
                return
            builder = getattr(self, "_tab_builders", {}).get(tab_name)
            if not builder:
                return
            try:
                builder()
                self._built_tab_names.add(tab_name)
            except Exception as exc:
                page = self.tab_widget.widget(index)
                if page and not page.layout():
                    layout = QtWidgets.QVBoxLayout(page)
                    label = QtWidgets.QLabel("Could not open this Aminate tab: {0}".format(exc))
                    label.setWordWrap(True)
                    layout.addWidget(label)
                _warning("Could not build Aminate tab {0}: {1}".format(tab_name, exc))

        def _configure_main_tab_bar(self):
            tab_bar = self.tab_widget.tabBar() if self.tab_widget else None
            if not tab_bar:
                return
            try:
                tab_bar.setExpanding(False)
            except Exception:
                pass
            try:
                tab_bar.setUsesScrollButtons(False)
            except Exception:
                pass
            try:
                tab_bar.setElideMode(_qt_flag("TextElideMode", "ElideRight", QtCore.Qt.ElideRight))
            except Exception:
                pass
            if hasattr(tab_bar, "setSizePolicy"):
                try:
                    tab_bar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
                except Exception:
                    pass

        def _refresh_tab_tooltips(self):
            if not self.tab_widget:
                return
            for index in range(self.tab_widget.count()):
                label = self.tab_widget.tabText(index)
                try:
                    self.tab_widget.setTabToolTip(index, label)
                except Exception:
                    pass

        def _build_tab_navigation_button(self, direction):
            button = QtWidgets.QToolButton()
            button.setObjectName("mayaAnimWorkflowTabNavButton")
            if direction < 0:
                button.setText("<<")
                button.setToolTip("Go to the tab on the left.")
                button.clicked.connect(lambda: self._step_tab_navigation(-1))
                self.tab_nav_left_button = button
            else:
                button.setText(">>")
                button.setToolTip("Go to the tab on the right.")
                button.clicked.connect(lambda: self._step_tab_navigation(1))
                self.tab_nav_right_button = button
            return button

        def _step_tab_navigation(self, direction):
            if not self.tab_widget:
                return
            current_index = self.tab_widget.currentIndex()
            max_index = max(0, self.tab_widget.count() - 1)
            target_index = max(0, min(max_index, current_index + int(direction)))
            if target_index != current_index:
                self.tab_widget.setCurrentIndex(target_index)

        def _update_tab_navigation_buttons(self, *_args):
            if not self.tab_widget:
                return
            current_index = self.tab_widget.currentIndex()
            max_index = max(0, self.tab_widget.count() - 1)
            if hasattr(self, "tab_nav_left_button") and self.tab_nav_left_button:
                self.tab_nav_left_button.setEnabled(current_index > 0)
            if hasattr(self, "tab_nav_right_button") and self.tab_nav_right_button:
                self.tab_nav_right_button.setEnabled(current_index < max_index)

        def _build_tab_intro(self, tab_name):
            frame = QtWidgets.QFrame()
            frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            frame.setObjectName("mayaAnimWorkflowTabIntro")
            inner = QtWidgets.QVBoxLayout(frame)
            inner.setContentsMargins(10, 8, 10, 8)
            inner.setSpacing(4)
            title = QtWidgets.QLabel("What This Tab Helps With")
            title.setObjectName("mayaAnimWorkflowIntroTitle")
            body = QtWidgets.QLabel(TAB_HELP_TEXT.get(tab_name, ""))
            body.setWordWrap(True)
            inner.addWidget(title)
            inner.addWidget(body)
            self.tab_intro_labels[tab_name] = body
            return frame

        def _embed_tool_panel(self, panel, host_parent):
            if panel is None:
                return None
            if hasattr(panel, "brand_label"):
                panel.brand_label.hide()
            if hasattr(panel, "donate_button"):
                panel.donate_button.hide()
            widget_flag = _qt_flag("WindowType", "Widget", 0)
            try:
                panel.setWindowFlags(widget_flag)
            except Exception:
                pass
            try:
                panel.setParent(host_parent)
            except Exception:
                pass
            try:
                panel.setProperty("aminateEmbeddedPanel", True)
            except Exception:
                pass
            panel.setMinimumWidth(0)
            panel.setMinimumHeight(0)
            if hasattr(panel, "setSizePolicy"):
                panel.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            try:
                panel.show()
            except Exception:
                pass
            return panel

        def _build_parenting_tab(self):
            layout = QtWidgets.QVBoxLayout(self.parenting_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_PARENTING))
            self.parenting_panel = self._embed_tool_panel(
                maya_dynamic_parenting_tool.MayaDynamicParentingWindow(self.controller.dynamic_parenting_controller, parent=self.parenting_page),
                self.parenting_page,
            )
            layout.addWidget(self.parenting_panel, 1)

        def _build_pivot_tab(self):
            layout = QtWidgets.QVBoxLayout(self.pivot_page)
            layout.addWidget(self._build_tab_intro(TAB_PIVOT))
            layout.addWidget(QtWidgets.QLabel("Make a temporary turn point anywhere, spin around it, then remove it when you are done."))
            row = QtWidgets.QHBoxLayout()
            self.pivot_mode_combo = QtWidgets.QComboBox()
            self.pivot_mode_combo.addItems(list(PIVOT_MODES.keys()))
            self.pivot_mode_combo.setToolTip("Choose where the turn point starts before you move it by hand.")
            row.addWidget(QtWidgets.QLabel("Start Pivot At"))
            row.addWidget(self.pivot_mode_combo, 1)
            layout.addLayout(row)
            buttons = QtWidgets.QGridLayout()
            self.create_pivot_button = QtWidgets.QPushButton("Create Pivot")
            self.create_pivot_button.setToolTip("Make a temporary pivot marker for the selected objects.")
            self.edit_pivot_button = QtWidgets.QPushButton("Move Pivot")
            self.edit_pivot_button.setToolTip("Select the pivot marker so you can move it where you want.")
            self.apply_pivot_button = QtWidgets.QPushButton("Turn From Pivot")
            self.apply_pivot_button.setToolTip("Rotate the selected objects around the pivot marker you just moved.")
            self.clear_pivot_button = QtWidgets.QPushButton("Clear Pivot")
            self.clear_pivot_button.setToolTip("Remove the temporary pivot marker.")
            buttons.addWidget(self.create_pivot_button, 0, 0)
            buttons.addWidget(self.edit_pivot_button, 0, 1)
            buttons.addWidget(self.apply_pivot_button, 1, 0)
            buttons.addWidget(self.clear_pivot_button, 1, 1)
            layout.addLayout(buttons)
            self.pivot_help = QtWidgets.QPlainTextEdit()
            self.pivot_help.setReadOnly(True)
            self.pivot_help.setPlainText("1. Pick the object or objects.\n2. Click Create Pivot.\n3. Click Move Pivot and place it where you want.\n4. Rotate the pivot marker.\n5. Click Turn From Pivot.\n6. Click Clear Pivot when you are done.")
            layout.addWidget(self.pivot_help, 1)
            self.create_pivot_button.clicked.connect(self._create_pivot)
            self.edit_pivot_button.clicked.connect(self._edit_pivot)
            self.apply_pivot_button.clicked.connect(self._apply_pivot)
            self.clear_pivot_button.clicked.connect(self._clear_pivot)

        def _build_contact_hold_tab(self):
            layout = QtWidgets.QVBoxLayout(self.contact_hold_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_CONTACT_HOLD))
            self.contact_hold_panel = self._embed_tool_panel(
                maya_contact_hold.MayaContactHoldWindow(self.controller.contact_hold_controller, parent=self.contact_hold_page),
                self.contact_hold_page,
            )
            layout.addWidget(self.contact_hold_panel, 1)

        def _build_surface_contact_tab(self):
            layout = QtWidgets.QVBoxLayout(self.surface_contact_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_SURFACE_CONTACT))
            self.surface_contact_panel = self._embed_tool_panel(
                maya_surface_contact.MayaSurfaceContactWindow(
                    self.controller.get_surface_contact_controller(),
                    parent=self.surface_contact_page,
                ),
                self.surface_contact_page,
            )
            layout.addWidget(self.surface_contact_panel, 1)

        def _build_ikfk_tab(self):
            layout = QtWidgets.QVBoxLayout(self.ikfk_page)
            layout.addWidget(self._build_tab_intro(TAB_IKFK))
            layout.addWidget(QtWidgets.QLabel("Find an arm or leg switch setup, check it, save it, and switch without a pop."))
            top = QtWidgets.QHBoxLayout()
            self.profile_combo = QtWidgets.QComboBox()
            self.refresh_profiles_button = QtWidgets.QPushButton("Refresh")
            self.load_profile_button = QtWidgets.QPushButton("Load")
            self.profile_combo.setToolTip("Saved switches you can reuse later.")
            self.refresh_profiles_button.setToolTip("Reload the saved switch list.")
            self.load_profile_button.setToolTip("Load the saved switch into the boxes below.")
            top.addWidget(QtWidgets.QLabel("Saved Switch"))
            top.addWidget(self.profile_combo, 1)
            top.addWidget(self.refresh_profiles_button)
            top.addWidget(self.load_profile_button)
            layout.addLayout(top)
            meta_form = QtWidgets.QGridLayout()
            self.profile_name_line = QtWidgets.QLineEdit()
            self.rig_root_line = QtWidgets.QLineEdit()
            self.namespace_line = QtWidgets.QLineEdit()
            self.limb_type_combo = QtWidgets.QComboBox()
            self.limb_type_combo.addItems(["arm", "leg"])
            self.side_combo = QtWidgets.QComboBox()
            self.side_combo.addItems(["left", "right"])
            self.switch_attr_line = QtWidgets.QLineEdit()
            meta_rows = [
                ("Switch Name", self.profile_name_line, "Main Rig", self.rig_root_line),
                ("Limb Type", self.limb_type_combo, "Side", self.side_combo),
                ("Name Tag", self.namespace_line, "Switch Setting", self.switch_attr_line),
            ]
            self.profile_name_line.setToolTip("A name so you can save and load this switch later.")
            self.rig_root_line.setToolTip("The main top object for this rig. This is usually filled in for you.")
            self.namespace_line.setToolTip("Only needed if the rig names have extra tags and auto-find needs help.")
            self.switch_attr_line.setToolTip("The setting that changes the arm or leg between IK and FK.")
            for row_index, row in enumerate(meta_rows):
                meta_form.addWidget(QtWidgets.QLabel(row[0]), row_index, 0)
                meta_form.addWidget(row[1], row_index, 1)
                meta_form.addWidget(QtWidgets.QLabel(row[2]), row_index, 2)
                meta_form.addWidget(row[3], row_index, 3)
            layout.addLayout(meta_form)

            columns = QtWidgets.QHBoxLayout()

            fk_group = QtWidgets.QGroupBox("FK")
            fk_form = QtWidgets.QFormLayout(fk_group)
            self.fk_controls_line = QtWidgets.QLineEdit()
            self.fk_controls_line.setPlaceholderText("shoulder_ctrl, elbow_ctrl, wrist_ctrl")
            self.fk_controls_line.setToolTip("The three FK controls for the arm or leg, in order from top to end.")
            fk_form.addRow("FK Controls", self.fk_controls_line)
            self.fk_value_spin = QtWidgets.QDoubleSpinBox()
            self.fk_value_spin.setDecimals(3)
            self.fk_value_spin.setRange(-9999.0, 9999.0)
            self.fk_value_spin.setToolTip("The switch value that means FK is on.")
            fk_form.addRow("FK Value", self.fk_value_spin)
            columns.addWidget(fk_group, 1)

            ik_group = QtWidgets.QGroupBox("IK")
            ik_form = QtWidgets.QFormLayout(ik_group)
            self.ik_controls_line = QtWidgets.QLineEdit()
            self.ik_controls_line.setPlaceholderText("ik_ctrl, pole_vector_ctrl")
            self.ik_controls_line.setToolTip("The hand or foot control and the elbow or knee guide.")
            ik_form.addRow("IK Controls", self.ik_controls_line)
            self.ik_control_line = QtWidgets.QLineEdit()
            self.ik_control_line.setToolTip("Usually the hand or foot control.")
            ik_form.addRow("Hand/Foot Control", self.ik_control_line)
            self.pv_control_line = QtWidgets.QLineEdit()
            self.pv_control_line.setToolTip("The control that points the elbow or knee.")
            ik_form.addRow("Elbow/Knee Guide", self.pv_control_line)
            self.ik_value_spin = QtWidgets.QDoubleSpinBox()
            self.ik_value_spin.setDecimals(3)
            self.ik_value_spin.setRange(-9999.0, 9999.0)
            self.ik_value_spin.setValue(1.0)
            self.ik_value_spin.setToolTip("The switch value that means IK is on.")
            ik_form.addRow("IK Value", self.ik_value_spin)
            columns.addWidget(ik_group, 1)

            layout.addLayout(columns)

            details_form = QtWidgets.QGridLayout()
            self.extra_controls_line = QtWidgets.QLineEdit()
            self.extra_controls_line.setPlaceholderText("optional extra controls to key")
            self.extra_controls_line.setToolTip("Any extra controls that should also get keys when you switch.")
            self.match_nodes_line = QtWidgets.QLineEdit()
            self.match_nodes_line.setPlaceholderText("match_shoulder, match_elbow, match_wrist")
            self.match_nodes_line.setToolTip("The points the FK controls should copy when you switch.")
            detail_rows = [
                ("Match Controls", self.match_nodes_line, "Extra Controls To Key", self.extra_controls_line),
            ]
            for row_index, row in enumerate(detail_rows):
                details_form.addWidget(QtWidgets.QLabel(row[0]), row_index, 0)
                details_form.addWidget(row[1], row_index, 1)
                if row[2]:
                    details_form.addWidget(QtWidgets.QLabel(row[2]), row_index, 2)
                    details_form.addWidget(row[3], row_index, 3)
            layout.addLayout(details_form)
            buttons = QtWidgets.QGridLayout()
            self.detect_profile_button = QtWidgets.QPushButton("Find From What You Picked")
            self.detect_profile_button.setToolTip("Make a first guess from the selected arm or leg controls.")
            self.save_profile_button = QtWidgets.QPushButton("Save Switch")
            self.save_profile_button.setToolTip("Save the current boxes as a switch you can load later.")
            self.switch_fk_to_ik_button = QtWidgets.QPushButton("Switch FK -> IK")
            self.switch_fk_to_ik_button.setToolTip("Match the IK controls to the current FK pose and switch on this frame.")
            self.switch_ik_to_fk_button = QtWidgets.QPushButton("Switch IK -> FK")
            self.switch_ik_to_fk_button.setToolTip("Match the FK controls to the current IK pose and switch on this frame.")
            buttons.addWidget(self.detect_profile_button, 0, 0)
            buttons.addWidget(self.save_profile_button, 0, 1)
            buttons.addWidget(self.switch_fk_to_ik_button, 1, 0)
            buttons.addWidget(self.switch_ik_to_fk_button, 1, 1)
            layout.addLayout(buttons)
            self.ikfk_help = QtWidgets.QPlainTextEdit()
            self.ikfk_help.setReadOnly(True)
            layout.addWidget(self.ikfk_help, 1)
            self.refresh_profiles_button.clicked.connect(self._populate_profile_names)
            self.load_profile_button.clicked.connect(self._load_selected_profile)
            self.detect_profile_button.clicked.connect(self._detect_profile)
            self.save_profile_button.clicked.connect(self._save_profile)
            self.switch_fk_to_ik_button.clicked.connect(self._switch_fk_to_ik)
            self.switch_ik_to_fk_button.clicked.connect(self._switch_ik_to_fk)

        def _build_face_retarget_tab(self):
            layout = QtWidgets.QVBoxLayout(self.face_retarget_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_FACE_RETARGET))
            face_hint = QtWidgets.QLabel("Fill paired rows: source control on the left, target control on the right. A new empty row appears automatically and empty rows are ignored. Auto Map By Name pairs matching names quickly. Retarget All Controls bakes every completed row.")
            face_hint.setWordWrap(True)
            layout.addWidget(face_hint)
            self.face_retarget_panel = self._embed_tool_panel(
                maya_face_retarget.MayaFaceRetargetWindow(self.controller.face_retarget_controller, parent=self.face_retarget_page),
                self.face_retarget_page,
            )
            layout.addWidget(self.face_retarget_panel, 1)

        def _build_control_picker_tab(self):
            layout = QtWidgets.QVBoxLayout(self.control_picker_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_CONTROL_PICKER))
            self.control_picker_panel = maya_control_picker.ControlPickerPanel(
                controller=self.controller.control_picker_controller,
                parent=self.control_picker_page,
            )
            layout.addWidget(self.control_picker_panel, 1)

        def _build_animators_pencil_tab(self):
            layout = QtWidgets.QVBoxLayout(self.animators_pencil_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_ANIMATORS_PENCIL))
            self.animators_pencil_panel = maya_animators_pencil.AnimatorsPencilPanel(
                controller=self.controller.animators_pencil_controller,
                parent=self.animators_pencil_page,
            )
            layout.addWidget(self.animators_pencil_panel, 1)

        def _build_animation_assistant_tab(self):
            layout = QtWidgets.QVBoxLayout(self.animation_assistant_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_ANIMATION_ASSISTANT))
            self.animation_assistant_panel = maya_animation_assistant.AnimationAssistantPanel(
                controller=self.controller.get_animation_assistant_controller(),
                parent=self.animation_assistant_page,
                status_callback=self._set_status,
            )
            layout.addWidget(self.animation_assistant_panel, 1)

        def _build_animation_styling_tab(self):
            layout = QtWidgets.QVBoxLayout(self.animation_styling_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_ANIMATION_STYLING))
            self.animation_styling_panel = maya_animation_styling.AnimationStylingPanel(
                controller=self.controller.get_animation_styling_controller(),
                parent=self.animation_styling_page,
                status_callback=self._set_status,
            )
            layout.addWidget(self.animation_styling_panel, 1)

        def _build_history_timeline_tab(self):
            layout = QtWidgets.QVBoxLayout(self.history_timeline_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_HISTORY_TIMELINE))
            self.history_timeline_panel = maya_history_timeline.MayaHistoryTimelinePanel(
                controller=self.controller.history_timeline_controller,
                status_callback=self._set_status,
                parent=self.history_timeline_page,
            )
            layout.addWidget(self.history_timeline_panel, 1)

        def _build_onion_tab(self):
            layout = QtWidgets.QVBoxLayout(self.onion_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_ONION))
            self.onion_panel = self._embed_tool_panel(
                maya_onion_skin.MayaOnionSkinWindow(self.controller.onion_controller, parent=self.onion_page),
                self.onion_page,
            )
            layout.addWidget(self.onion_panel, 1)

        def _build_rotation_tab(self):
            layout = QtWidgets.QVBoxLayout(self.rotation_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_ROTATION))
            self.rotation_panel = self._embed_tool_panel(
                maya_rotation_doctor.MayaRotationDoctorWindow(self.controller.rotation_controller, parent=self.rotation_page),
                self.rotation_page,
            )
            layout.addWidget(self.rotation_panel, 1)

        def _build_skin_tab(self):
            layout = QtWidgets.QVBoxLayout(self.skin_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_SKIN))

            freeze_heading = QtWidgets.QLabel("Freeze Bad Mesh Transforms")
            freeze_heading.setStyleSheet("font-size: 15px; font-weight: 800; color: #F2F2F2;")
            layout.addWidget(freeze_heading)
            self.skin_panel = self._embed_tool_panel(
                maya_skinning_cleanup.MayaSkinningCleanupWindow(self.controller.skinning_controller, parent=self.skin_page),
                self.skin_page,
            )
            layout.addWidget(self.skin_panel, 1)

            transfer_heading = QtWidgets.QLabel("Copy Exact Skinning")
            transfer_heading.setStyleSheet("font-size: 15px; font-weight: 800; color: #F2F2F2;")
            layout.addWidget(transfer_heading)
            self.skin_transfer_panel = self._embed_tool_panel(
                maya_skin_transfer.MayaSkinTransferWindow(self.controller.skin_transfer_controller, parent=self.skin_page, show_footer=False),
                self.skin_page,
            )
            layout.addWidget(self.skin_transfer_panel, 0)

        def _build_rig_scale_tab(self):
            layout = QtWidgets.QVBoxLayout(self.rig_scale_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_RIG_SCALE))
            self.rig_scale_panel = self._embed_tool_panel(
                maya_rig_scale_export.MayaRigScaleExportWindow(self.controller.rig_scale_controller, parent=self.rig_scale_page),
                self.rig_scale_page,
            )
            layout.addWidget(self.rig_scale_panel, 1)

        def _build_video_tab(self):
            layout = QtWidgets.QVBoxLayout(self.video_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_VIDEO))
            self.video_panel = self._embed_tool_panel(
                maya_video_reference_tool.MayaVideoReferenceWindow(self.controller.video_reference_controller, parent=self.video_page),
                self.video_page,
            )
            layout.addWidget(self.video_panel, 1)

        def _build_timeline_tab(self):
            layout = QtWidgets.QVBoxLayout(self.timeline_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_TIMELINE))
            self.timeline_panel = self._embed_tool_panel(
                maya_timeline_notes.MayaTimelineNotesWindow(
                    self.controller.get_timeline_notes_controller(),
                    parent=self.timeline_page,
                ),
                self.timeline_page,
            )
            layout.addWidget(self.timeline_panel, 1)

        def _build_smear_frames_tab(self):
            layout = QtWidgets.QVBoxLayout(self.smear_frames_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_SMEAR_FRAMES))
            self.smear_frames_panel = self._embed_tool_panel(
                maya_smear_frames.SmearFrameWindow(
                    self.controller.smear_frame_controller,
                    parent=self.smear_frames_page,
                    show_footer=False,
                ),
                self.smear_frames_page,
            )
            layout.addWidget(self.smear_frames_panel, 1)

        def _build_customization_tab(self):
            layout = QtWidgets.QVBoxLayout(self.customization_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_CUSTOMIZATION))
            self.customization_panel = self._embed_tool_panel(
                maya_aminate_customization.AminateCustomizationWindow(
                    self.controller.customization_controller,
                    parent=self.customization_page,
                    show_footer=False,
                ),
                self.customization_page,
            )
            layout.addWidget(self.customization_panel, 1)

        def _build_guide_tab(self):
            layout = QtWidgets.QVBoxLayout(self.guide_page)
            layout.addWidget(self._build_tab_intro(TAB_GUIDE))
            tutorials_button = QtWidgets.QPushButton("Open Tutorials")
            tutorials_button.setToolTip("Open Aminate local tutorials and button docs.")
            tutorials_button.clicked.connect(self._open_tutorials_docs)
            layout.addWidget(tutorials_button)
            guide = QtWidgets.QPlainTextEdit()
            guide.setReadOnly(True)
            guide.setPlainText(
                "Toolkit Bar\n"
                "- Use this when you want compact, color-coded, animBot-style buttons for the basic animation jobs students repeat all day.\n"
                "- Use -1 and +1 to nudge selected Graph Editor keys, or all keys on selected controls.\n"
                "- Use In to add an inbetween key on the current frame, and Cut to remove keys on the current frame.\n"
                "- Use Zero to reset selected controls, 2s to bake selected controls every two frames, Anim to pick animated controls, and Clean to remove static curves.\n"
                "- Open the Toolkit Bar tab when you want the full docked Toolkit Bar strip inside the main Aminate window.\n\n"
                "Scene Helpers\n"
                "- Use this when you want Auto Key, Auto Snap To Frames, Game Animation Mode, Load Textures, Open Last Autosave, Set Up Render Environment, Camera Offset controls, and Camera Preset quick buttons.\n"
                "- Use Auto Key when you want Maya to key changes as you animate.\n"
                "- Leave Auto Snap To Frames on if you want the tool to watch for timing changes for you.\n"
                "- Click Snap Selected Keys To Frames if keys are already off-frame.\n"
                "- Click Load Textures when scene textures exist locally but Maya has not refreshed or repathed them yet.\n"
                "- Click Open Last Autosave if Maya crashed and you want to jump straight back to the latest autosave.\n"
                "- Click Game Animation Mode in Scene Helpers or the blue button at the far right of the Toolkit Bar to prep the scene for 30 fps, real-time playback, autosave, five backups, and a texture refresh.\n\n"
                "- Click Set Up Render Environment to build the cyclorama helper in Python and add the sky light, bookmarks, and render cameras around the selected character.\n"
                "- The camera preset menu starts on Perspective, then lets you jump to Front, Side, or Three Quarter.\n"
                "- Click Delete Render Environment to remove the whole render setup again when you want to start over.\n"
                "- Use Camera Height Offset and Camera Dolly Offset to move all helper cameras up/down or in/out together.\n"
                "- Use Camera Preset to jump between Perspective, Front, Side, and Three Quarter after the setup is built.\n\n"
                "Reference Manager\n"
                "- Use this when you want one zip that contains the saved scene and every referenced file the scene needs.\n"
                "- Save the shot once first so Maya knows where the scene lives.\n"
                "- Click Refresh Needed Files to check Maya references, textures, image planes, audio, and caches.\n"
                "- Click Package Scene To Zip.\n"
                "- The zip contains a packaged Maya ASCII scene, copied files, and a manifest listing anything missing.\n\n"
                "Dynamic Parenting\n"
                "- Use this when a prop or control needs to switch between hand, gun, world, or mixed parents without popping.\n"
                "- Pick the moving thing, like the magazine.\n"
                "- Leave Stay In Current Position At Start? on if you want it to stay where it is when you first add it.\n"
                "- Click Add Object.\n"
                "- Pick the new parent, like the gun or the hand, and click Pick Parent.\n"
                "- If you want it to jump onto that parent right now, click Snap To Parent.\n"
                "- If you want to place it yourself, move it where you want, leave Maintain Current Offset on, and click Switch to this Parent.\n"
                "- Click World if it should stop following everything.\n"
                "- Example: pick the magazine, leave Stay In Current Position At Start? on, click Add Object, pick the gun, click Pick Parent, place the magazine exactly where you want it, then click Switch to this Parent. On the next frame it follows the gun but stays in that exact place.\n"
                "- Open More if you want to remember extra parents, blend two parents, fix a jump, or delete saved switches.\n"
                "- To delete one saved switch, open More, pick it in History, and click Delete Picked Switch.\n"
                "- Remove Object deletes this tool's constraints, saved parents, and saved switches for that object.\n\n"
                "Controls Retargeter (Face and Body)\n"
                "- Use this when you want face or body controls from one rig copied onto another rig.\n"
                "- Pick the source face controls first, then click Load Selected Source.\n"
                "- Pick the target face controls second, then click Load Selected Target.\n"
                "- If you pick too many, select the extra source or target control and click Remove Selected Source or Remove Selected Target.\n"
                "- Keep the same order on both sides. Source item 1 maps to Target item 1, source item 2 maps to target item 2, and so on.\n"
                "- Example: brow, eye, mouth, jaw, or body controls can still pair even if one rig says source_brow_CTRL and the other says target_brow_CTRL.\n"
                "- If you need to fix one saved row, click its row first and use Quick Pair Edit. It only changes the selected row.\n"
                "- Click Pair By Order for order matching, or Auto Map By Name for loose name matching.\n"
                "- Click Retarget Selected Controls for one control pair row or Retarget All Controls for every control pair row.\n"
                "- The target controls get the keys, so you can still edit them after the transfer.\n\n"
                "Animators Pencil\n"
                "- Use this when you want Blue Pencil-style drawing for animation notes, arcs, contact fixes, or frame planning.\n"
                "- Drawings are real Maya curves and text placed in front of the current camera, so the scene still shows the marks without this script installed.\n"
                "- Click Add Layer, pick a tool, choose color, size, and opacity, then click Create Mark.\n"
                "- Use Static layers for notes that stay visible, Animation layers for frame-based drawings, and Locked layers when you do not want accidental edits.\n"
                "- Use Add Key, Duplicate Previous Key, Retime, Frame Marker, and Ghosts for drawing animation timing.\n"
                "- Use Copy, Cut, Paste, Erase Selected, or Maya's Move/Rotate/Scale tools to edit marks.\n\n"
                "History Timeline\n"
                "- Use this when you want ZBrush-style restore points that are safer than a long Maya undo chain.\n"
                "- Save the Maya scene once first so Aminate knows where to keep the history folder.\n"
                "- Click Save Step for normal work states or Save Milestone for protected important poses.\n"
                "- Click a block in the Toolkit Bar history strip, or pick a row in the History Timeline tab and click Restore.\n"
                "- Restoring saves a safety snapshot first, then opens the chosen full-scene snapshot.\n"
                "- Snapshot metadata is recorded for changed nodes, animation curves, constraints, branches, and notes.\n\n"
                "Hand / Foot Hold\n"
                "- Use this when a planted hand or foot should stay in the same place on chosen world axes while the body keeps moving.\n"
                "- Pick the hand or foot control.\n"
                "- If you want both sides, click Add Matching Other Side.\n"
                "- If you are not sure about the contact range, click Suggest Range first.\n"
                "- Go to the first frame where it sticks and click Use Current For Contact Start.\n"
                "- Go to the frame where it stops sticking and click Use Current For Lift End.\n"
                "- Turn on the world axes you want to keep still, like Z for forward travel.\n"
                "- Click Create / Update Hold.\n"
                "- Use Use Hold to turn the saved hold on again, Use Original Motion to turn it off, and Delete Hold to remove it.\n\n"
                "Surface Contact\n"
                "- Use this when a hand, foot, or other control should stay clamped to a selected mesh surface.\n"
                "- Pick the control first, then pick the surface mesh.\n"
                "- Turn on Follow Surface Normal if you want the control to turn with the surface.\n"
                "- Click Check Setup to make sure the control and surface are ready.\n"
                "- Click Create / Update Contact to make the clamp live.\n"
                "- Use Turn On Selected and Turn Off Selected to turn saved contacts on and off.\n"
                "- Use Key State if you want Maya to remember that on or off state on the current frame.\n"
                "- Use Refresh Now if you want the current frame solved again right away.\n\n"
                "Dynamic Pivot\n"
                "- Use this when you want a temporary turn point without changing the real pivot.\n"
                "- Pick the object or objects.\n"
                "- Click Create Pivot.\n"
                "- Click Move Pivot and place the pivot marker where you want to turn from.\n"
                "- Rotate the pivot marker.\n"
                "- Click Turn From Pivot.\n"
                "- Click Clear Pivot when you are done.\n\n"
                "Universal Arm/Leg Switch\n"
                "- Use this when you need to switch an arm or leg between IK and FK without a visible pop.\n"
                "- Pick the arm or leg controls.\n"
                "- Click Find From What You Picked.\n"
                "- Check that the FK box has the FK controls and the IK box has the hand or foot control plus the elbow or knee guide.\n"
                "- Click Save Switch if it looks right.\n"
                "- Use the switch buttons when you want to change modes. The tool also keys the frame before so it stays clean.\n\n"
                "Onion Skin\n"
                "- Use this when you want to see past and future poses as ghosts.\n"
                "- Pick a character and click Attach Selected.\n"
                "- The see-through copies show where the character was and where it will be.\n"
                "- Use Frame Step if you only want to see every second or third frame.\n\n"
                "Rotation Doctor\n"
                "- Use this when rotations are flipping or gimbaling and you want help fixing them.\n"
                "- Pick the animated controls and click Analyze Selected.\n"
                "- Read the warning list.\n"
                "- Click Use Best Fix for the safest quick fix, or choose a specific fix button if you know what you want.\n\n"
                "Character Skinning\n"
                "- Use this when a skinned mesh has bad translate, rotate, or scale values and you want a clean replacement copy.\n"
                "- Pick one skinned mesh, for example low on a RapidRig character.\n"
                "- Click Replace Mesh With Frozen Transform Mesh.\n"
                "- Aminate makes a checked frozen mesh, swaps it in, keeps skin weights, and hides the old mesh as a backup.\n\n"
                "- To copy exact skinning, select the skinned source mesh first, select the matching target mesh second, and click Copy Selected Pair Now.\n\n"
                "Rig Scale\n"
                "- Use this when you need an export-safe scaled copy for Unreal or another game engine.\n"
                "- Pick the character root or any object under the character and click Use Selected Character.\n"
                "- Pick the top skeleton joint and click Use Selected Skeleton.\n"
                "- Type the new Size Multiplier.\n"
                "- Click Check Setup.\n"
                "- Click Make Export Copy.\n"
                "- Export the copied group to Unreal, not the original rig.\n\n"
                "Video Reference\n"
                "- Use this when you want scene-based video reference for tracing or timing.\n"
                "- Click the viewport you want to trace in, then click Use Active View.\n"
                "- Pick the video or image sequence.\n"
                "- If you want the card behind the character, pick the control or object and click Use Selected Object.\n"
                "- Choose Behind Picked Object, Follow Picked Object, or Camera Overlay.\n"
                "- Set the Start Frame offset. If the card is already there, changing this field retimes that card.\n"
                "- If you want matching sound, turn on Import Audio Too and pick the audio file.\n"
                "- Click Make Tracing Card.\n"
                "- Use Open Drawing Manager and Start Drawing to add quick note lines even when Blue Pencil is missing.\n\n"
                "Timeline Notes\n"
                "- Use this when you want timeline notes you can read while scrubbing.\n"
                "- Highlight a time range on Maya's timeline.\n"
                "- Type a short title, pick a color, and write your note.\n"
                "- Leave Auto Use Highlighted Range on if you want the tool to follow the highlighted range for you.\n"
                "- Click Add Note.\n"
                "- Hover the colored range on the timeline or read the Notes At Current Frame box while you scrub.\n"
                "- Use Export Notes if you want to reuse them in another scene.\n\n"
                "Troubleshooting\n"
                "- If a grab or let-go pops, go to that frame and click Fix Jumps.\n"
                "- If the arm or leg switch finds the wrong controls, fix the boxes by hand and save the switch.\n"
                "- If the timeline note or video tools are not visible in the combined window, reopen Aminate after the latest script reload.\n\n"
                "Special Thanks\n"
                "- Brogan Bowen, for helping test the Controls Retargeter.\n"
                "- Alex Potter, for helping test Character Skinning reset.\n"
                "- Alex Lee, for the idea behind Tween Machine.\n"
                "- V Gerrard Lawless, for the idea behind the frozen character skinning system.\n"
                "- Wiktor Wisniewski, for the idea behind Dynamic Parenting."
            )
            layout.addWidget(guide)

        def _build_student_core_tab(self):
            layout = QtWidgets.QVBoxLayout(self.student_core_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_STUDENT_CORE))
            self.student_core_panel = self._embed_tool_panel(
                maya_timing_tools.StudentTimelineButtonBarWindow(
                    self.controller.get_timing_controller(),
                    self._set_status,
                    parent=self.student_core_page,
                    embedded=True,
                    start_history_watcher=False,
                    max_history_markers=36,
                ),
                self.student_core_page,
            )
            layout.addWidget(self.student_core_panel)
            help_box = QtWidgets.QPlainTextEdit()
            help_box.setReadOnly(True)
            help_box.setPlainText(
                "This tab mirrors the docked Toolkit Bar above Maya's timeline.\n\n"
                "- The History strip, Animation Layer controls, timing buttons, workflow icons, package zip, and Game Animation Mode button are all shown here.\n"
                "- Changes made from this tab use the same controller as the docked bar, so Game Animation Mode and animation layer state stay synced.\n"
                "- Use the docked bar for fast timeline work, or this tab when you want the same controls inside Aminate."
            )
            help_box.setMaximumHeight(135)
            layout.addWidget(help_box)
            open_button = QtWidgets.QPushButton("Open Bottom Toolkit Bar")
            open_button.setToolTip("Dock the small Toolkit Bar into the bottom of Maya near the native timeline.")
            open_button.clicked.connect(self._open_student_core_toolbar)
            layout.addWidget(open_button)
            layout.addStretch(1)

        def _open_student_core_toolbar(self):
            try:
                maya_timing_tools.launch_student_timeline_button_bar(
                    dock=True,
                    controller=self.controller.get_timing_controller(),
                    status_callback=self._set_status,
                )
                self._set_status("Toolkit Bar docked to the bottom of Maya.", True)
            except Exception as exc:
                self._set_status("Could not open Toolkit Bar: {0}".format(exc), False)

        def _build_timing_tab(self):
            layout = QtWidgets.QVBoxLayout(self.timing_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_TIMING))
            self.timing_panel = self._embed_tool_panel(
                maya_timing_tools.MayaTimingToolsWindow(
                    self.controller.get_timing_controller(),
                    parent=self.timing_page,
                ),
                self.timing_page,
            )
            layout.addWidget(self.timing_panel, 1)

        def _build_reference_manager_tab(self):
            layout = QtWidgets.QVBoxLayout(self.reference_manager_page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._build_tab_intro(TAB_REFERENCE_MANAGER))
            self.reference_manager_panel = maya_reference_manager.ReferenceManagerPanel(
                controller=self.controller.reference_manager_controller,
                status_callback=self._set_status,
                parent=self.reference_manager_page,
            )
            layout.addWidget(self.reference_manager_panel, 1)

        @staticmethod
        def _tab_key(value):
            if value is None:
                return ""
            cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value))
            return "_".join(part for part in cleaned.split("_") if part)

        def _find_tab_index(self, tab_name):
            lookup = {
                "guide": "quick_start",
                "quick_start": "quick_start",
                "student": "student_core",
                "student_core": "student_core",
                "core": "student_core",
                "temp_buttons": "student_core",
                "timeline_buttons": "student_core",
                "timing": "scene_helpers",
                "timing_helpers": "scene_helpers",
                "scene": "scene_helpers",
                "scene_helpers": "scene_helpers",
                "reference_manager": "reference_manager",
                "ref_manager": "reference_manager",
                "package": "reference_manager",
                "package_scene": "reference_manager",
                "archive": "reference_manager",
                "archive_scene": "reference_manager",
                "parenting": "dynamic_parenting",
                "dynamic_parenting": "dynamic_parenting",
                "contact": "hand_foot_hold",
                "contact_hold": "hand_foot_hold",
                "hold": "hand_foot_hold",
                "hold_still": "hand_foot_hold",
                "surface": "surface_contact",
                "surface_contact": "surface_contact",
                "contact_surface": "surface_contact",
                "pivot": "dynamic_pivot",
                "dynamic_pivot": "dynamic_pivot",
                "ikfk": "universal_ik_fk",
                "ik_fk": "universal_ik_fk",
                "switcher": "universal_ik_fk",
                "face": "controls_retargeter_face_and_body",
                "face_retarget": "controls_retargeter_face_and_body",
                "face_retargeter": "controls_retargeter_face_and_body",
                "facial_retarget": "controls_retargeter_face_and_body",
                "controls": "controls_retargeter_face_and_body",
                "controls_retargeter": "controls_retargeter_face_and_body",
                "controls_retargeter_face_and_body": "controls_retargeter_face_and_body",
                "control_picker": "control_picker",
                "picker": "control_picker",
                "animators_pencil": "animators_pencil",
                "animator_pencil": "animators_pencil",
                "pencil": "animators_pencil",
                "blue_pencil": "animators_pencil",
                "animation_assistant": "animation_assistant",
                "assistant": "animation_assistant",
                "balance": "animation_assistant",
                "pose_balance": "animation_assistant",
                "animation_styling": "animation_styling",
                "styling": "animation_styling",
                "spider_verse": "animation_styling",
                "held_keys": "animation_styling",
                "holds": "animation_styling",
                "history": "history_timeline",
                "history_timeline": "history_timeline",
                "snapshots": "history_timeline",
                "snapshot": "history_timeline",
                "restore": "history_timeline",
                "onion": "onion_skin",
                "onion_skin": "onion_skin",
                "rotation": "rotation_doctor",
                "rotation_doctor": "rotation_doctor",
                "skin_transfer": "character_skinning",
                "transfer_skin": "character_skinning",
                "copy_skin": "character_skinning",
                "skin_to_skin": "character_skinning",
                "skin": "character_skinning",
                "skinning": "character_skinning",
                "skinning_cleanup": "character_skinning",
                "freeze": "character_skinning",
                "character_freeze": "character_skinning",
                "character_skinning": "character_skinning",
                "transform_cleanup": "character_skinning",
                "rig_scale": "rig_scale",
                "scale": "rig_scale",
                "video": "video_reference",
                "video_reference": "video_reference",
                "reference": "video_reference",
                "timeline": "timeline_notes",
                "timeline_notes": "timeline_notes",
                "notes": "timeline_notes",
                "smear": "smear_frames",
                "smears": "smear_frames",
                "smear_frames": "smear_frames",
                "customization": "customization",
                "customize": "customization",
                "colors": "customization",
                "colours": "customization",
            }
            target_key = lookup.get(self._tab_key(tab_name), self._tab_key(tab_name))
            for index in range(self.tab_widget.count()):
                if self._tab_key(self.tab_widget.tabText(index)) == target_key:
                    return index
            return None

        def _set_initial_tab(self, initial_tab):
            if isinstance(initial_tab, str):
                found_index = self._find_tab_index(initial_tab)
                self.tab_widget.setCurrentIndex(0 if found_index is None else found_index)
                self._ensure_tab_content(self.tab_widget.currentIndex())
                return
            try:
                initial_index = int(initial_tab)
            except (TypeError, ValueError):
                initial_index = 0
            initial_index = max(0, min(initial_index, self.tab_widget.count() - 1))
            self.tab_widget.setCurrentIndex(initial_index)
            self._ensure_tab_content(self.tab_widget.currentIndex())

        def _set_status(self, message, success=True):
            if not hasattr(self, "status_label"):
                return
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)

        def _refresh_parenting_summary(self):
            setups = self.controller.parenting_setups(from_selection=False)
            if not setups:
                self.parenting_summary.setPlainText("No hold / swap helpers in the scene yet.")
                return
            lines = [_describe_parenting_state(item) for item in setups]
            self.parenting_summary.setPlainText("\n".join(lines))

        def _refresh_parenting_event_list(self):
            setups = self.controller.parenting_setups(from_selection=True)
            label_suffix = "picked controls"
            if not setups:
                setups = self.controller.parenting_setups(from_selection=False)
                label_suffix = "all helpers"
            self.parenting_events_label.setText("Swap History ({0})".format(label_suffix))
            self.parenting_event_list.clear()
            role = _qt_flag("ItemDataRole", "UserRole", 32)
            events = []
            for setup_data in setups:
                for event_data in setup_data.get("event_log") or []:
                    payload = dict(event_data)
                    payload["display"] = _describe_parenting_event(payload)
                    events.append(payload)
            events.sort(key=lambda item: (float(item.get("frame", 0.0)), item.get("display", "")))
            if not events:
                item = QtWidgets.QListWidgetItem("No swap events yet.")
                item.setFlags(item.flags() & ~_qt_flag("ItemFlag", "ItemIsSelectable", 1))
                self.parenting_event_list.addItem(item)
                return
            for event_data in events:
                item = QtWidgets.QListWidgetItem(event_data["display"])
                item.setData(role, event_data)
                self.parenting_event_list.addItem(item)
            self.parenting_event_list.setCurrentRow(0)

        def _jump_to_selected_parenting_event(self, item=None):
            current_item = item or self.parenting_event_list.currentItem()
            if not current_item:
                self._set_status("Pick a swap event first.", False)
                return
            role = _qt_flag("ItemDataRole", "UserRole", 32)
            event_data = current_item.data(role)
            if not isinstance(event_data, dict):
                self._set_status("There is no saved swap event to jump to yet.", False)
                return
            frame_value = float(event_data.get("frame", 0.0))
            cmds.currentTime(frame_value, edit=True)
            self._set_status("Jumped to frame {0}.".format(_frame_display(frame_value)), True)

        def _profile_fields(self):
            return {
                "profile_name": self.profile_name_line.text(),
                "rig_root": self.rig_root_line.text(),
                "namespace_hint": self.namespace_line.text(),
                "limb_type": self.limb_type_combo.currentText(),
                "side": self.side_combo.currentText(),
                "fk_controls": [item.strip() for item in self.fk_controls_line.text().split(",") if item.strip()],
                "ik_controls": [item.strip() for item in self.ik_controls_line.text().split(",") if item.strip()],
                "ik_control": self.ik_control_line.text(),
                "pole_vector_control": self.pv_control_line.text(),
                "switch_attr": self.switch_attr_line.text(),
                "fk_value": self.fk_value_spin.value(),
                "ik_value": self.ik_value_spin.value(),
                "extra_controls": [item.strip() for item in self.extra_controls_line.text().split(",") if item.strip()],
                "match_nodes": [item.strip() for item in self.match_nodes_line.text().split(",") if item.strip()],
            }

        def _populate_profile_fields(self, profile):
            self.profile_name_line.setText(profile.get("profile_name", ""))
            self.rig_root_line.setText(profile.get("rig_root", ""))
            self.namespace_line.setText(profile.get("namespace_hint", ""))
            self.limb_type_combo.setCurrentText(profile.get("limb_type", "arm"))
            self.side_combo.setCurrentText(profile.get("side", "left"))
            self.fk_controls_line.setText(", ".join(profile.get("fk_controls", [])))
            self.ik_controls_line.setText(", ".join(profile.get("ik_controls", [])))
            self.ik_control_line.setText(profile.get("ik_control", ""))
            self.pv_control_line.setText(profile.get("pole_vector_control", ""))
            self.switch_attr_line.setText(profile.get("switch_attr", ""))
            self.fk_value_spin.setValue(float(profile.get("fk_value", 0.0)))
            self.ik_value_spin.setValue(float(profile.get("ik_value", 1.0)))
            self.extra_controls_line.setText(", ".join(profile.get("extra_controls", [])))
            self.match_nodes_line.setText(", ".join(profile.get("match_nodes", [])))

        def _populate_profile_names(self):
            if not hasattr(self, "profile_combo"):
                return
            current = self.profile_combo.currentText()
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            self.controller.profile_store = _load_profile_store()
            for name in self.controller.profile_names():
                self.profile_combo.addItem(name)
            if current:
                index = self.profile_combo.findText(current)
                if index >= 0:
                    self.profile_combo.setCurrentIndex(index)
            self.profile_combo.blockSignals(False)

        def _use_selected_driver(self):
            success, message = self.controller.set_driver_from_selection()
            if success:
                self.driver_line.setText(_short_name(self.controller.driver_node))
            self._set_status(message, success)

        def _create_temp_controls(self):
            success, message = self.controller.create_temp_controls()
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _sync_parenting_options(self):
            self.controller.release_space = RELEASE_SPACES[self.release_combo.currentText()]
            self.controller.bake_mode = BAKE_MODES[self.bake_mode_combo.currentText()]
            self.controller.bake_range = BAKE_RANGES[self.bake_range_combo.currentText()]

        def _add_grab(self):
            success, message = self.controller.add_grab_current()
            if self.controller.driver_node:
                self.driver_line.setText(_short_name(self.controller.driver_node))
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _pickup_here(self):
            success, message = self.controller.add_grab_current(event_action="pickup")
            if self.controller.driver_node:
                self.driver_line.setText(_short_name(self.controller.driver_node))
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _pass_here(self):
            success, message = self.controller.add_grab_current(event_action="pass")
            if self.controller.driver_node:
                self.driver_line.setText(_short_name(self.controller.driver_node))
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _add_release(self):
            self._sync_parenting_options()
            success, message = self.controller.add_release_current(self.controller.release_space)
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _drop_here(self):
            self._sync_parenting_options()
            success, message = self.controller.add_release_current(self.controller.release_space, event_action="drop")
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _normalize_transitions(self):
            success, message = self.controller.normalize_transitions()
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _bake_to_rig(self):
            self._sync_parenting_options()
            success, message = self.controller.bake_to_rig(clear_after=False)
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _bake_and_clear(self):
            self._sync_parenting_options()
            success, message = self.controller.bake_to_rig(clear_after=True)
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _clear_parenting(self):
            success, message = self.controller.clear_temp_setups()
            self._refresh_parenting_summary()
            self._refresh_parenting_event_list()
            self._set_status(message, success)

        def _create_pivot(self):
            success, message = self.controller.create_pivot(PIVOT_MODES[self.pivot_mode_combo.currentText()])
            self._set_status(message, success)

        def _edit_pivot(self):
            success, message = self.controller.edit_pivot_position()
            self._set_status(message, success)

        def _apply_pivot(self):
            success, message = self.controller.apply_pivot_rotation()
            self._set_status(message, success)

        def _clear_pivot(self):
            success, message = self.controller.clear_pivot()
            self._set_status(message, success)

        def _load_selected_profile(self):
            profile_name = self.profile_combo.currentText()
            if not profile_name:
                self._set_status("Pick a saved switch first.", False)
                return
            success, payload = self.controller.load_profile(profile_name)
            if not success:
                self._set_status(payload, False)
                return
            self._populate_profile_fields(payload)
            self._set_status("Loaded switch '{0}'.".format(profile_name), True)

        def _detect_profile(self):
            profile, issues = self.controller.detect_profile()
            self._populate_profile_fields(profile)
            lines = ["We made a first guess from what is selected."]
            lines.append("Check both the FK Controls and IK Controls boxes before you save.")
            if issues:
                lines.append("")
                lines.extend("- " + issue for issue in issues)
            self.ikfk_help.setPlainText("\n".join(lines))
            self._set_status("First guess found. Check the boxes before saving.", True)

        def _save_profile(self):
            success, message = self.controller.save_profile(self._profile_fields())
            self._populate_profile_names()
            self._set_status(message, success)

        def _switch_fk_to_ik(self):
            success, message = self.controller.switch_fk_to_ik(self._profile_fields())
            self._set_status(message, success)

        def _switch_ik_to_fk(self):
            success, message = self.controller.switch_ik_to_fk(self._profile_fields())
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

        def _keep_toolbar_extras_on_hide(self):
            timing_controller = getattr(self.controller, "timing_controller", None)
            return bool(getattr(timing_controller, "keep_toolbar_extras_on_hide", False))

        def _hide_extra_qt_widgets_by_name(self):
            app = QtWidgets.QApplication.instance()
            if not app:
                return 0
            extra_names = {
                "studentCoreTimelineButtonBarWindow",
                "toolkitBarTweenMachinePopup",
                "aminateFloatingChannelBoxWindow",
                "aminateFloatingGraphEditorWindow",
            }
            hidden = 0
            for widget in list(app.allWidgets()):
                try:
                    if widget is self or self._is_widget_inside_window(widget):
                        continue
                    if widget.objectName() not in extra_names:
                        continue
                    if widget.isVisible():
                        hidden += 1
                    widget.close()
                except Exception:
                    pass
            return hidden

        def _hide_toolbar_extras_if_needed(self):
            if self._toolbar_extras_hidden_for_close:
                return
            self._toolbar_extras_hidden_for_close = True
            if self._keep_toolbar_extras_on_hide():
                return
            hidden_count = maya_timing_tools.hide_aminate_toolbar_extras()
            hidden_count += self._hide_extra_qt_widgets_by_name()
            if hidden_count:
                self._set_status("Aminate hidden. Cleared toolbar extras.", True)

        def _open_tutorials_docs(self):
            docs_path = _tutorials_index_path()
            if _open_local_file(docs_path):
                self._set_status("Opened Aminate tutorials.", True)
            else:
                self._set_status("Could not open Aminate tutorials: {0}".format(docs_path), False)

        def hideEvent(self, event):
            self._hide_toolbar_extras_if_needed()
            try:
                super(MayaAnimWorkflowWindow, self).hideEvent(event)
            except TypeError:
                QtWidgets.QDialog.hideEvent(self, event)

        def showEvent(self, event):
            self._toolbar_extras_hidden_for_close = False
            try:
                super(MayaAnimWorkflowWindow, self).showEvent(event)
            except TypeError:
                QtWidgets.QDialog.showEvent(self, event)

        def setVisible(self, visible):
            if not bool(visible):
                self._hide_toolbar_extras_if_needed()
            try:
                super(MayaAnimWorkflowWindow, self).setVisible(visible)
            except TypeError:
                QtWidgets.QDialog.setVisible(self, visible)

        def closeEvent(self, event):
            self._hide_toolbar_extras_if_needed()
            self._remove_key_passthrough_filter()
            try:
                self.controller.shutdown()
            except Exception:
                pass
            super(MayaAnimWorkflowWindow, self).closeEvent(event)

def _workspace_control_exists(name=WORKSPACE_CONTROL_NAME):
    return bool(MAYA_AVAILABLE and cmds and name and cmds.workspaceControl(name, exists=True))


def _process_qt_events():
    if not QtWidgets:
        return
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    try:
        app.processEvents()
    except Exception:
        pass


def _show_window_dockable(window, floating=True, area="right"):
    if not window:
        return False, "No Aminate window is available to show."
    try:
        window.show(dockable=True, floating=bool(floating), area=area)
        _process_qt_events()
    except Exception as exc:
        try:
            window.show()
        except Exception:
            pass
        return False, "Could not show the workflow tools as a dockable Maya panel: {0}".format(exc)
    if not _workspace_control_exists(WORKSPACE_CONTROL_NAME):
        return False, "The Maya workspace control did not open."
    return True, "Opened the workflow tools through Maya's dockable workspace control."


def _dock_workspace_control(name=WORKSPACE_CONTROL_NAME, area="right", tab=False):
    if not _workspace_control_exists(name):
        return False, "The dockable Maya workspace control is not open yet."
    try:
        cmds.workspaceControl(name, edit=True, dockToMainWindow=(area, bool(tab)))
        cmds.workspaceControl(name, edit=True, restore=True)
        for flag in ("minimumWidth", "initialWidth", "width", "resizeWidth"):
            try:
                cmds.workspaceControl(name, edit=True, **{flag: DOCKED_WORKFLOW_MIN_WIDTH})
            except Exception:
                pass
        _process_qt_events()
        floating = bool(cmds.workspaceControl(name, query=True, floating=True))
    except Exception as exc:
        return False, "Could not dock the Maya workspace control: {0}".format(exc)
    if floating:
        return False, "Maya kept the workflow panel floating instead of docking it."
    return True, "Docked the workflow panel into Maya's {0} layout.".format(area)


def _shelf_button_command(repo_path):
    return (
        "import sys\n"
        "repo_path = r\"{0}\"\n"
        "for _aminate_module_name in ('maya_dynamic_parent_pivot', 'maya_anim_workflow_tools'):\n"
        "    _aminate_module = sys.modules.get(_aminate_module_name)\n"
        "    if _aminate_module:\n"
        "        _aminate_impl = getattr(_aminate_module, '_impl', _aminate_module)\n"
        "        _aminate_close = getattr(_aminate_impl, '_close_existing_window', None)\n"
        "        if _aminate_close:\n"
        "            try:\n"
        "                _aminate_close()\n"
        "            except Exception:\n"
        "                pass\n"
        "while repo_path in sys.path:\n"
        "    sys.path.remove(repo_path)\n"
        "sys.path.insert(0, repo_path)\n"
        "import maya_anim_workflow_tools\n"
        "maya_anim_workflow_tools.launch_maya_anim_workflow_tools(dock=True)\n"
    ).format(repo_path.replace("\\", "\\\\"))


def _shelf_icon_path(repo_path):
    icon_path = os.path.join(repo_path, SHELF_ICON_FILE_NAME)
    if os.path.exists(icon_path):
        return icon_path
    return maya_shelf_utils.DEFAULT_SHELF_ICON


def install_maya_dynamic_parent_pivot_shelf_button(shelf_name=DEFAULT_SHELF_NAME, button_label=DEFAULT_SHELF_BUTTON_LABEL, repo_path=None):
    if not MAYA_AVAILABLE:
        raise RuntimeError("install_maya_dynamic_parent_pivot_shelf_button() must run inside Autodesk Maya.")
    repo_path = repo_path or os.path.dirname(os.path.abspath(__file__))
    shelf_top = maya_shelf_utils.shelf_top_level()
    shelf_layout = maya_shelf_utils.resolve_shelf_layout(shelf_top, shelf_name)
    for doc_tag in LEGACY_WORKFLOW_SHELF_DOC_TAGS:
        maya_shelf_utils.remove_buttons_by_doc_tag(shelf_layout, doc_tag)
    metadata = maya_shelf_utils.install_shelf_button(
        command_text=_shelf_button_command(repo_path),
        doc_tag=SHELF_BUTTON_DOC_TAG,
        annotation="Launch Aminate",
        button_label=button_label,
        image=_shelf_icon_path(repo_path),
        image_overlay_label=SHELF_ICON_OVERLAY_LABEL,
        shelf_name=shelf_name,
    )
    return metadata["button"]


def launch_maya_dynamic_parent_pivot(dock=True, initial_tab="quick_start"):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    global GLOBAL_DOCK_HOST
    if not MAYA_AVAILABLE:
        raise RuntimeError("maya_dynamic_parent_pivot.launch_maya_dynamic_parent_pivot() must run inside Autodesk Maya.")
    if not QtWidgets:
        raise RuntimeError("PySide is not available in this Maya session.")
    if GLOBAL_WINDOW is not None and not _qt_object_valid(GLOBAL_WINDOW):
        GLOBAL_WINDOW = None
    if GLOBAL_DOCK_HOST is not None and not _qt_object_valid(GLOBAL_DOCK_HOST):
        GLOBAL_DOCK_HOST = None
    if GLOBAL_WINDOW is not None:
        try:
            if dock and _workspace_control_exists(WORKSPACE_CONTROL_NAME):
                cmds.workspaceControl(WORKSPACE_CONTROL_NAME, edit=True, visible=True)
                _dock_workspace_control(WORKSPACE_CONTROL_NAME, area="right", tab=False)
                GLOBAL_WINDOW.show()
                _process_qt_events()
                if hasattr(GLOBAL_WINDOW, "_set_initial_tab"):
                    GLOBAL_WINDOW._set_initial_tab(initial_tab)
                return GLOBAL_WINDOW
            if not dock:
                GLOBAL_WINDOW.show()
                _process_qt_events()
                if hasattr(GLOBAL_WINDOW, "_set_initial_tab"):
                    GLOBAL_WINDOW._set_initial_tab(initial_tab)
                return GLOBAL_WINDOW
        except Exception:
            pass
    _close_existing_window()
    app = QtWidgets.QApplication.instance()
    _process_qt_events()
    GLOBAL_CONTROLLER = MayaAnimWorkflowController()
    GLOBAL_WINDOW = MayaAnimWorkflowWindow(GLOBAL_CONTROLLER, parent=_maya_main_window(), initial_tab=initial_tab)
    GLOBAL_DOCK_HOST = None
    if dock:
        _delete_workspace_control(WORKSPACE_CONTROL_NAME)
        _delete_workspace_control(LEGACY_WORKSPACE_CONTROL_NAME)
    success, _message = _show_window_dockable(GLOBAL_WINDOW, floating=not bool(dock), area="right")
    if dock and success:
        _dock_workspace_control(WORKSPACE_CONTROL_NAME, area="right", tab=False)
        if os.environ.get("AMINATE_AUTO_OPEN_TOOLKIT_BAR", "1") != "0":
            def _open_default_toolkit_bar():
                try:
                    if not _qt_object_valid(GLOBAL_WINDOW):
                        return
                    timing_controller = GLOBAL_CONTROLLER.get_timing_controller()
                    try:
                        timing_controller.set_keep_toolbar_extras_on_hide(True)
                    except Exception:
                        pass
                    bar_window = maya_timing_tools.launch_student_timeline_button_bar(
                        dock=True,
                        controller=timing_controller,
                        status_callback=GLOBAL_WINDOW._set_status,
                    )
                    def _reshow_default_toolkit_bar():
                        try:
                            if maya_timing_tools._qt_object_valid(bar_window):
                                maya_timing_tools._show_timeline_bar_as_safe_window(bar_window)
                        except Exception:
                            pass
                    try:
                        QtCore.QTimer.singleShot(900, _reshow_default_toolkit_bar)
                    except Exception:
                        _reshow_default_toolkit_bar()
                except Exception as exc:
                    _warning("Could not open Toolkit Bar: {0}".format(exc))

            try:
                QtCore.QTimer.singleShot(1500, _open_default_toolkit_bar)
            except Exception:
                _open_default_toolkit_bar()
    elif not success:
        GLOBAL_WINDOW.show()
        _process_qt_events()
    try:
        if not dock:
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
    except Exception:
        pass
    _ensure_single_workflow_widget(keep_widget=GLOBAL_WINDOW)
    return GLOBAL_WINDOW


__all__ = [
    "launch_maya_dynamic_parent_pivot",
    "install_maya_dynamic_parent_pivot_shelf_button",
    "MayaAnimWorkflowController",
]
