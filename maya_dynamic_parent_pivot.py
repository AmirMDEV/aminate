"""
maya_dynamic_parent_pivot.py

Combined Aminate with Dynamic Parenting, Hand / Foot Hold,
Surface Contact, Dynamic Pivot, Universal IK/FK, Controls Retargeter (Face and Body), Control Picker,
Animators Pencil, Onion Skin, Rotation Doctor, Character Skinning, Rig Scale, Video Reference, Timeline Notes, and Customization tabs.
"""

from __future__ import absolute_import, division, print_function

import json
import math
import os
import weakref

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
import maya_aminate_theme

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


WINDOW_OBJECT_NAME = "aminateWindow"
DOCK_HOST_OBJECT_NAME = WINDOW_OBJECT_NAME + "DockHost"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
LEGACY_WORKSPACE_CONTROL_NAME = DOCK_HOST_OBJECT_NAME + "WorkspaceControl"
DOCKED_WORKFLOW_MIN_WIDTH = 360
DOCKED_WORKFLOW_MIN_HEIGHT = 480
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
VERSION_LABEL = "Version 0.3.7"
TUTORIALS_DOCS_RELATIVE_PATH = os.path.join("docs", "index.html")
TUTORIAL_RELEASE_URL = "https://github.com/AmirMDEV/aminate/releases/download/v0.3.7/Aminate_v0.3.7_offline_tutorial.zip"
DEFAULT_SHELF_NAME = maya_shelf_utils.DEFAULT_SHELF_NAME
DEFAULT_SHELF_BUTTON_LABEL = "Aminate"
SHELF_BUTTON_DOC_TAG = "aminateShelfButton"
SHELF_ICON_FILE_NAME = "aminate_icon.png"
SHELF_ICON_OVERLAY_LABEL = ""
SHELF_BUTTON_STYLE = "iconAndTextHorizontal"
SHELF_BUTTON_WIDTH = 92
SHELF_BUTTON_HEIGHT = 34
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

# Project-local semantic roles for a compact Maya workbench.  The palette stays
# close to Maya's graphite chrome.  Colour communicates selection, status, and
# the one primary action; it is not used to brand every tool or draw accent
# borders around ordinary controls.
AMINATE_UI_TOKENS = {
    "background": "#373737",
    "surface": "#414141",
    "surface_alt": "#494949",
    "surface_raised": "#505050",
    "on_surface": "#F1F1F1",
    "on_surface_muted": "#B8B8B8",
    "on_surface_disabled": "#858585",
    "primary": "#7892A8",
    "primary_variant": "#4A5966",
    "primary_container": "#445A6D",
    "primary_hover": "#526B80",
    "primary_pressed": "#384A59",
    "primary_focus": "#8CA5BA",
    "primary_selection": "#566A7A",
    "outline": "#5C5C5C",
    "outline_variant": "#4B4B4B",
    "secondary_creative": "#F1F1F1",
    "secondary_rigging": "#F1F1F1",
    "secondary_review": "#F1F1F1",
    "success": "#78A67B",
    "warning": "#C49A5A",
    "error": "#C57878",
    "error_container": "#5A3434",
    "on_error": "#FFF0F0",
    "disabled_container": "#454545",
    "on_primary": "#FFFFFF",
}

# The category names are intentionally stable API for widget properties.  The
# values point back to the semantic token map so a palette change is made once
# and then rendered into the shared stylesheet below.
AMINATE_CATEGORY_TOKEN_KEYS = {
    "primary": "primary",
    "rigging": "secondary_rigging",
    "creative": "secondary_creative",
    "review": "secondary_review",
}


def _render_aminate_semantic_stylesheet():
    """Render token-backed role rules appended to the shared Aminate QSS."""
    token = AMINATE_UI_TOKENS
    category = AMINATE_CATEGORY_TOKEN_KEYS
    return """
QLabel#aminateIntroTitle[aminateCategory="primary"] {{
    color: {on_surface};
}}
QLabel#aminateIntroTitle[aminateCategory="rigging"] {{
    color: {on_surface};
}}
QLabel#aminateIntroTitle[aminateCategory="creative"] {{
    color: {on_surface};
}}
QLabel#aminateIntroTitle[aminateCategory="review"] {{
    color: {on_surface};
}}
QTabBar::tab:selected {{
    background-color: {primary_selection};
    border-color: {outline};
}}
QComboBox#aminateToolPicker QAbstractItemView {{
    selection-background-color: {primary_selection};
}}
QListWidget#aminateQuickStartToolList::item,
QListView#aminateQuickStartToolList::item {{
    background-color: {surface};
    color: {on_surface};
    padding: 5px 8px;
}}
QListWidget#aminateQuickStartToolList::item:alternate,
QListView#aminateQuickStartToolList::item:alternate {{
    background-color: {surface_alt};
    color: {on_surface};
}}
QListWidget#aminateQuickStartToolList::item:hover,
QListView#aminateQuickStartToolList::item:hover {{
    background-color: {primary_variant};
    color: {on_surface};
}}
QListWidget#aminateQuickStartToolList::item:selected,
QListView#aminateQuickStartToolList::item:selected {{
    background-color: {primary_selection};
    color: {on_surface};
}}
QListWidget#aminateQuickStartToolList::item:disabled,
QListView#aminateQuickStartToolList::item:disabled {{
    background-color: {background};
    color: {on_surface_disabled};
}}
QToolButton#animatorsPencilCameraNotesMenuButton {{
    background-color: {surface};
    color: {on_surface};
    border: 1px solid {outline};
    border-radius: 6px;
    padding: 5px 8px;
}}
QToolButton#animatorsPencilCameraNotesMenuButton:hover {{
    background-color: {primary_variant};
    border-color: {outline};
}}
QToolButton#animatorsPencilCameraNotesMenuButton:pressed,
QToolButton#animatorsPencilCameraNotesMenuButton:checked {{
    background-color: {primary_pressed};
    border-color: {outline};
}}
QToolButton#animatorsPencilCameraNotesMenuButton:disabled {{
    background-color: {background};
    color: {on_surface_disabled};
    border-color: {outline_variant};
}}
QMenu#animatorsPencilCameraNotesMenu {{
    background-color: {surface};
    color: {on_surface};
    border: 1px solid {outline};
    padding: 4px;
}}
QMenu#animatorsPencilCameraNotesMenu::item {{
    background-color: {surface};
    color: {on_surface};
    padding: 6px 10px;
}}
QMenu#animatorsPencilCameraNotesMenu::item:selected {{
    background-color: {primary_selection};
    color: {on_surface};
}}
QMenu#animatorsPencilCameraNotesMenu::item:disabled {{
    background-color: {surface};
    color: {on_surface_disabled};
}}
QPushButton[aminateRole="primary"] {{
    background-color: {primary_container};
    color: {on_primary};
    border-color: {primary_container};
}}
QPushButton[aminateRole="primary"]:hover {{
    background-color: {primary_hover};
    border-color: {primary_hover};
}}
QPushButton[aminateRole="primary"]:pressed {{
    background-color: {primary_pressed};
    border-color: {primary_pressed};
}}
QPushButton[aminateRole="primary"]:disabled {{
    background-color: {disabled_container};
    color: {on_surface_disabled};
    border-color: {outline_variant};
}}
QLabel[aminateRole="success"] {{
    color: {success};
}}
QLabel[aminateRole="warning"] {{
    color: {warning};
}}
QLabel[aminateRole="error"] {{
    color: {error};
}}
""".format(
        primary=token[category["primary"]],
        rigging=token[category["rigging"]],
        creative=token[category["creative"]],
        review=token[category["review"]],
        background=token["background"],
        surface=token["surface"],
        surface_alt=token["surface_alt"],
        on_surface=token["on_surface"],
        primary_variant=token["primary_variant"],
        primary_container=token["primary_container"],
        primary_selection=token["primary_selection"],
        on_primary=token["on_primary"],
        primary_hover=token["primary_hover"],
        primary_focus=token["primary_focus"],
        primary_pressed=token["primary_pressed"],
        disabled_container=token["disabled_container"],
        on_surface_disabled=token["on_surface_disabled"],
        outline=token["outline"],
        outline_variant=token["outline_variant"],
        success=token["success"],
        warning=token["warning"],
        error=token["error"],
    )

# Stable category mapping for new tab intros.  Unlisted names intentionally
# fall back to the blue primary role in _build_tab_intro().
AMINATE_TAB_CATEGORY = {
    TAB_GUIDE: "primary",
    TAB_STUDENT_CORE: "primary",
    TAB_TIMING: "primary",
    TAB_REFERENCE_MANAGER: "review",
    TAB_PARENTING: "rigging",
    TAB_CONTACT_HOLD: "rigging",
    TAB_SURFACE_CONTACT: "rigging",
    TAB_PIVOT: "primary",
    TAB_IKFK: "rigging",
    TAB_FACE_RETARGET: "rigging",
    TAB_CONTROL_PICKER: "rigging",
    TAB_ANIMATORS_PENCIL: "creative",
    TAB_ANIMATION_ASSISTANT: "primary",
    TAB_ANIMATION_STYLING: "creative",
    TAB_HISTORY_TIMELINE: "review",
    TAB_ONION: "creative",
    TAB_ROTATION: "primary",
    TAB_SKIN: "rigging",
    TAB_RIG_SCALE: "rigging",
    TAB_VIDEO: "review",
    TAB_TIMELINE: "review",
    TAB_SMEAR_FRAMES: "creative",
    TAB_CUSTOMIZATION: "creative",
}

# Aminate is a Maya work surface, not a second copy of its tutorial website.
# The active stylesheet therefore uses shallow neutral surfaces, compact native
# controls, and tonal selection.  No tool gets a coloured perimeter, rail, or
# underline.  Semantic colour is reserved for primary, success, warning, and
# destructive states.
AMINATE_WINDOW_STYLESHEET = """
QDialog#aminateWindow,
QWidget[aminateTabPage="true"],
QWidget[aminateEmbeddedPanel="true"],
QScrollArea#aminateTabScroll,
QScrollArea#aminateTabScroll > QWidget > QWidget {
    background-color: #373737;
    color: #F1F1F1;
}
QWidget[aminateEmbeddedPanel="true"] QScrollArea,
QWidget[aminateEmbeddedPanel="true"] QScrollArea > QWidget > QWidget {
    background-color: #373737;
    color: #F1F1F1;
}
QScrollArea#aminateTabScroll {
    border: 0px;
}
QTabWidget#aminateTabWidget::pane {
    background-color: #373737;
    border: 0px;
}
QTabBar::tab {
    background-color: #414141;
    color: #B8B8B8;
    border: 0px;
    min-width: 96px;
    max-width: 180px;
    padding: 5px 8px;
    margin-right: 1px;
}
QTabBar::tab:selected {
    background-color: #566A7A;
    color: #FFFFFF;
    font-weight: 700;
}
QTabBar::tab:hover {
    background-color: #505050;
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
QWidget#aminateToolNavigation {
    background-color: #414141;
    border: 0px;
}
QLabel#aminateToolNavigationLabel {
    color: #B8B8B8;
    font-weight: 700;
}
QComboBox#aminateToolPicker {
    min-height: 26px;
    background-color: #505050;
    color: #F1F1F1;
    border: 1px solid #5C5C5C;
    border-radius: 3px;
    padding: 2px 26px 2px 7px;
    selection-background-color: #566A7A;
}
QComboBox#aminateToolPicker:hover,
QComboBox#aminateToolPicker:focus,
QComboBox#aminateToolPicker:on {
    background-color: #585858;
    border-color: #6A6A6A;
}
QComboBox#aminateToolPicker::drop-down {
    width: 22px;
    border: 0px;
    border-left: 1px solid #5C5C5C;
    background-color: #4A4A4A;
}
QComboBox#aminateToolPicker::drop-down:hover {
    background-color: #5A5A5A;
}
QComboBox#aminateToolPicker QAbstractItemView {
    background-color: #414141;
    color: #F1F1F1;
    border: 1px solid #5C5C5C;
    selection-background-color: #566A7A;
    selection-color: #FFFFFF;
    outline: 0px;
    padding: 2px;
}
QFrame#aminateTabIntro {
    background-color: transparent;
    color: #F1F1F1;
    border: 0px;
}
QLabel#aminateIntroTitle {
    color: #F1F1F1;
    font-size: 15px;
    font-weight: 700;
}
QToolButton#aminateIntroToggle,
QToolButton#aminateSupportButton {
    min-width: 0px;
    padding: 3px 6px;
    color: #D4D4D4;
    background-color: transparent;
    border: 0px;
    border-radius: 3px;
}
QToolButton#aminateIntroToggle:hover,
QToolButton#aminateSupportButton:hover {
    background-color: #505050;
    color: #FFFFFF;
}
QToolButton#aminateIntroToggle:pressed,
QToolButton#aminateIntroToggle:checked,
QToolButton#aminateSupportButton:pressed {
    background-color: #494949;
    color: #FFFFFF;
}
QWidget#aminateIntroHelp {
    background-color: #414141;
    border: 0px;
}
QFrame#aminateCoach {
    background-color: transparent;
    border: 0px;
}
QLabel#aminateCoachTitle {
    color: #D7D7D7;
    font-weight: 700;
}
QLabel#aminateCoachStep {
    color: #C8C8C8;
}
QPushButton#aminateTutorialButton {
    background-color: transparent;
    color: #C7D7E4;
    border: 0px;
    padding: 3px 0px;
    min-height: 20px;
    text-align: left;
}
QPushButton#aminateTutorialButton:hover {
    background-color: transparent;
    color: #FFFFFF;
    text-decoration: underline;
}
QLabel#aminateStatusLabel {
    background-color: transparent;
    color: #B8B8B8;
    border: 0px;
    padding: 3px 1px;
}
QLabel#aminateBrandLabel,
QLabel#aminateVersionLabel {
    color: #9F9F9F;
}
QPushButton {
    background-color: #505050;
    color: #F1F1F1;
    border: 1px solid #5C5C5C;
    border-radius: 3px;
    padding: 4px 7px;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #5A5A5A;
    border-color: #666666;
}
QPushButton:pressed,
QPushButton:checked {
    background-color: #454545;
    border-color: #5C5C5C;
}
QPushButton#animatorsPencilStartDrawingButton[aminateDrawingActive="true"] {
    background-color: #1F7A43;
    color: #FFFFFF;
    border-color: #8F8F8F;
    font-weight: 700;
}
QPushButton#animatorsPencilStartDrawingButton[aminateDrawingActive="true"]:hover {
    background-color: #278E50;
    border-color: #A8A8A8;
}
QPushButton#animatorsPencilStartDrawingButton[aminateDrawingActive="true"]:focus {
    border-color: #FFFFFF;
}
QPushButton:focus {
    border-color: #6A6A6A;
}
QPushButton:disabled {
    background-color: #414141;
    color: #858585;
    border-color: #4B4B4B;
}
QPushButton[aminateRole="primary"] {
    background-color: #445A6D;
    color: #FFFFFF;
    border-color: #445A6D;
    font-weight: 700;
}
QPushButton[aminateRole="primary"]:hover {
    background-color: #526B80;
    border-color: #526B80;
}
QPushButton[aminateRole="primary"]:pressed {
    background-color: #384A59;
    border-color: #384A59;
}
QPushButton[aminateRole="primary"]:disabled {
    background-color: #454545;
    color: #858585;
    border-color: #454545;
}
QPushButton[aminateRole="danger"] {
    background-color: #5A3434;
    color: #FFF0F0;
    border-color: #5A3434;
}
QLabel[aminateRole="muted"] {
    color: #B8B8B8;
}
QLineEdit,
QPlainTextEdit,
QTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    background-color: #2F2F2F;
    color: #F1F1F1;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 3px;
    selection-background-color: #566A7A;
}
QLineEdit:focus,
QPlainTextEdit:focus,
QTextEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    background-color: #343434;
    border-color: #686868;
}
QComboBox::drop-down {
    border: 0px;
    width: 20px;
}
QCheckBox,
QRadioButton,
QLabel {
    color: #F1F1F1;
}
QGroupBox {
    background-color: transparent;
    color: #F1F1F1;
    border: 0px;
    margin-top: 12px;
    padding-top: 5px;
    font-weight: 400;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 0px;
    padding: 0px;
    color: #D7D7D7;
    font-weight: 700;
}
QTableWidget,
QTreeWidget,
QListWidget {
    background-color: #303030;
    color: #EFEFEF;
    gridline-color: #4B4B4B;
    border: 1px solid #4B4B4B;
    border-radius: 2px;
    selection-background-color: #566A7A;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background-color: #454545;
    color: #F1F1F1;
    border: 0px;
    border-right: 1px solid #555555;
    border-bottom: 1px solid #555555;
    padding: 4px;
}
QScrollBar:vertical,
QScrollBar:horizontal {
    background-color: #333333;
    border: 0px;
    margin: 0px;
}
QScrollBar:vertical {
    width: 12px;
}
QScrollBar:horizontal {
    height: 12px;
}
QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {
    background-color: #5A5A5A;
    border-radius: 3px;
    min-height: 22px;
    min-width: 22px;
}
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {
    background-color: #686868;
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
    TAB_CONTACT_HOLD: "Use this to manage several planted hand or foot ranges while the root keeps moving. Turn saved holds on for the held/on-the-spot result, or off to restore the original forward-moving animation.",
    TAB_SURFACE_CONTACT: "Use this when hand, foot, or object controls must stay on or outside one or more live mesh surfaces, including slopes, uneven ground, steps, and curved props.",
    TAB_PIVOT: "Use this when selected controls must turn around a temporary point for one frame or a highlighted Time Slider range, without changing the real rig pivot.",
    TAB_IKFK: "Use this when you need to switch an arm or leg cleanly between IK and FK and keep the pose matched.",
    TAB_FACE_RETARGET: "Use this when you want face or body controls from one rig copied onto another rig. Put a source control on the left and its target control on the right. Empty rows are ignored. Auto Map By Name matches controls quickly from names, and Retarget All Controls bakes onto the target controls. Reduce Keys keeps only the original source keyframes.",
    TAB_CONTROL_PICKER: "Choose any character or animal rig root and Aminate builds selection sets from its controls, hierarchy, body area, side, and FK/IK mode. Parent groups select every child, Ctrl/Shift combines groups, custom sets can mix any controls, and the live Front/Side map places buttons from the rig's real control positions.",
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
    TAB_CUSTOMIZATION: "Use this when you want one place for animation-data colours such as timeline highlights, note ranges, keyframe emphasis, and Graph Editor curves. These colours describe your scene; they do not change Aminate's product palette.",
}
TAB_WORKFLOW_STEPS = {
    TAB_GUIDE: (
        "Type the job you are trying to do.",
        "Pick the tool whose description matches.",
        "Open it, or use the picture tutorial for more help.",
    ),
    TAB_STUDENT_CORE: (
        "Select the animated controls or keys.",
        "Choose one timing or workflow button.",
        "Check the timeline before moving on.",
    ),
    TAB_TIMING: (
        "Choose the scene job you need.",
        "Check the selected objects and timeline range.",
        "Run one helper and read its status message.",
    ),
    TAB_REFERENCE_MANAGER: (
        "Save the Maya scene.",
        "Refresh and check the needed-file list.",
        "Package the scene and its files into one zip.",
    ),
    TAB_PARENTING: (
        "Add the prop that will change parents.",
        "Pick and save each hand, hip, or world target.",
        "Switch on the needed frame and check that it does not pop.",
    ),
    TAB_CONTACT_HOLD: (
        "Pick the hand or foot control.",
        "Choose the frames and axes that must stay still.",
        "Create the hold, then switch between held and original motion.",
    ),
    TAB_SURFACE_CONTACT: (
        "Pick the hand, foot, or object controls.",
        "Pick the floor, slope, or prop meshes.",
        "Check the setup, then create the collision.",
    ),
    TAB_PIVOT: (
        "Pick the controls, then create and move the temporary pivot marker.",
        "Highlight the frames to change, or leave the Time Slider unhighlighted for only the current frame.",
        "Rotate the marker and turn from it. Move the same marker and repeat for the next range.",
    ),
    TAB_IKFK: (
        "Pick one arm, leg, or chain.",
        "Find or fill in its FK, IK, and switch controls.",
        "Save the setup, then switch and check for a pop.",
    ),
    TAB_FACE_RETARGET: (
        "Load the source controls.",
        "Load the matching target controls and check the pairs.",
        "Retarget, then scrub the result before saving.",
    ),
    TAB_CONTROL_PICKER: (
        "Select the character or animal rig root, then click Scan Selected Rig.",
        "Open a limb or tail group and choose only FK or IK before keying.",
        "Ctrl/Shift-click groups, save useful mixes as Custom Sets, and check the live map.",
    ),
    TAB_ANIMATORS_PENCIL: (
        "Choose a saved view, drawing tool, colour, and layer.",
        "Start drawing and make the planning marks.",
        "Switch frames or views and check that each drawing stays where it belongs.",
    ),
    TAB_ANIMATION_ASSISTANT: (
        "Pick the floor and centre-of-gravity control.",
        "Add the hands, feet, or contact controls.",
        "Refresh and adjust the pose until the balance guide makes sense.",
    ),
    TAB_ANIMATION_STYLING: (
        "Select the controls and choose a hold length.",
        "Check the overlap warning.",
        "Apply the hold or stepped curves, then scrub the timing.",
    ),
    TAB_HISTORY_TIMELINE: (
        "Save the scene first.",
        "Make a step or protected milestone.",
        "Pick a restore point and restore only when you need it.",
    ),
    TAB_ONION: (
        "Select the animated character or mesh.",
        "Attach it and choose the past/future frame spacing.",
        "Judge the arc, then clear the ghosts when finished.",
    ),
    TAB_ROTATION: (
        "Select the controls with strange rotation.",
        "Analyze before changing anything.",
        "Use the suggested fix, then scrub through the repaired keys.",
    ),
    TAB_SKIN: (
        "Choose whether you are fixing transforms or copying weights.",
        "Load the source and target meshes carefully.",
        "Run the safe copy, read the report, and inspect the duplicate before replacing anything.",
    ),
    TAB_RIG_SCALE: (
        "Pick the rig control and top skeleton joint.",
        "Choose the exact size or percentage.",
        "Check the setup, make the copy, and export only the copy.",
    ),
    TAB_VIDEO: (
        "Choose the active view and video or image sequence.",
        "Set the placement, size, and start frame.",
        "Make the tracing card and scrub to check timing.",
    ),
    TAB_TIMELINE: (
        "Highlight the frame range.",
        "Write a short title and clear note.",
        "Add the note, then scrub into its range to check it.",
    ),
    TAB_SMEAR_FRAMES: (
        "Select the animated mesh on the smear frame.",
        "Choose the frame offsets and strength.",
        "Create the smear and check that only the intended frame shows it.",
    ),
    TAB_CUSTOMIZATION: (
        "Choose Maya Graphite or Studio Contrast.",
        "Pick only the colours you want to change.",
        "Apply, inspect the UI, and reset if the result is unclear.",
    ),
}
TAB_TUTORIAL_SECTION_IDS = {
    TAB_GUIDE: "quick-start",
    TAB_STUDENT_CORE: "toolkit-bar",
    TAB_TIMING: "scene-helpers",
    TAB_REFERENCE_MANAGER: "reference-manager",
    TAB_PARENTING: "dynamic-parenting",
    TAB_CONTACT_HOLD: "hand-foot-hold",
    TAB_SURFACE_CONTACT: "surface-contact",
    TAB_PIVOT: "dynamic-pivot",
    TAB_IKFK: "universal-ikfk",
    TAB_FACE_RETARGET: "retargeter",
    TAB_CONTROL_PICKER: "control-picker",
    TAB_ANIMATORS_PENCIL: "animators-pencil",
    TAB_ANIMATION_ASSISTANT: "animation-assistant",
    TAB_ANIMATION_STYLING: "animation-styling",
    TAB_HISTORY_TIMELINE: "history-timeline",
    TAB_ONION: "onion-skin",
    TAB_ROTATION: "rotation-doctor",
    TAB_SKIN: "character-skinning",
    TAB_RIG_SCALE: "rig-scale",
    TAB_VIDEO: "video-reference",
    TAB_TIMELINE: "timeline-notes",
    TAB_SMEAR_FRAMES: "smear-frames",
    TAB_CUSTOMIZATION: "customization",
}
AMINATE_EMBEDDED_PANEL_STYLESHEET = """
QWidget[aminateEmbeddedPanel="true"],
QWidget[aminateEmbeddedPanel="true"] QWidget,
QWidget[aminateEmbeddedPanel="true"] QScrollArea,
QWidget[aminateEmbeddedPanel="true"] QAbstractScrollArea,
QWidget[aminateEmbeddedPanel="true"] QWidget#qt_scrollarea_viewport {
    background-color: #373737;
    color: #F1F1F1;
}
QWidget[aminateEmbeddedPanel="true"] QLabel,
QWidget[aminateEmbeddedPanel="true"] QCheckBox,
QWidget[aminateEmbeddedPanel="true"] QRadioButton {
    background-color: transparent;
    color: #F1F1F1;
}
QWidget[aminateEmbeddedPanel="true"] QScrollArea,
QWidget[aminateEmbeddedPanel="true"] QAbstractScrollArea,
QWidget[aminateEmbeddedPanel="true"] QWidget#qt_scrollarea_viewport {
    border: 0px;
}
QWidget[aminateEmbeddedPanel="true"] QGroupBox {
    background-color: transparent;
    color: #F1F1F1;
    border: 0px;
    margin-top: 11px;
    padding-top: 5px;
}
QWidget[aminateEmbeddedPanel="true"] QGroupBox::title {
    subcontrol-origin: margin;
    left: 0px;
    padding: 0px;
    color: #D7D7D7;
    font-weight: 700;
}
QWidget[aminateEmbeddedPanel="true"] QLineEdit,
QWidget[aminateEmbeddedPanel="true"] QTextEdit,
QWidget[aminateEmbeddedPanel="true"] QPlainTextEdit,
QWidget[aminateEmbeddedPanel="true"] QSpinBox,
QWidget[aminateEmbeddedPanel="true"] QDoubleSpinBox,
QWidget[aminateEmbeddedPanel="true"] QComboBox,
QWidget[aminateEmbeddedPanel="true"] QListView,
QWidget[aminateEmbeddedPanel="true"] QTreeView,
QWidget[aminateEmbeddedPanel="true"] QTableView,
QWidget[aminateEmbeddedPanel="true"] QListWidget,
QWidget[aminateEmbeddedPanel="true"] QTreeWidget,
QWidget[aminateEmbeddedPanel="true"] QTableWidget {
    background-color: #303030;
    alternate-background-color: #3A3A3A;
    color: #F1F1F1;
    border: 1px solid #505050;
    border-radius: 3px;
    selection-background-color: #566A7A;
    selection-color: #FFFFFF;
}
QWidget[aminateEmbeddedPanel="true"] QHeaderView::section {
    background-color: #454545;
    color: #F1F1F1;
    border: 0px;
    border-right: 1px solid #555555;
    border-bottom: 1px solid #555555;
    padding: 4px 5px;
}
QWidget[aminateEmbeddedPanel="true"] QPushButton {
    background-color: #505050;
    color: #F1F1F1;
    border: 1px solid #5C5C5C;
    border-radius: 3px;
    padding: 4px 7px;
}
QWidget[aminateEmbeddedPanel="true"] QPushButton:hover {
    background-color: #5A5A5A;
    border-color: #666666;
}
QWidget[aminateEmbeddedPanel="true"] QPushButton:pressed {
    background-color: #454545;
    border-color: #5C5C5C;
}
QWidget[aminateEmbeddedPanel="true"] QPushButton[aminateRole="primary"] {
    background-color: #445A6D;
    border-color: #445A6D;
    color: #FFFFFF;
    font-weight: 700;
}
QWidget[aminateEmbeddedPanel="true"] QPushButton[aminateRole="danger"] {
    background-color: #5A3434;
    border-color: #5A3434;
    color: #FFF0F0;
}
QWidget[aminateEmbeddedPanel="true"] QTabWidget::pane {
    background-color: #373737;
    border: 0px;
}
QWidget[aminateEmbeddedPanel="true"] QTabBar::tab {
    background-color: #414141;
    color: #B8B8B8;
    border: 0px;
    padding: 4px 7px;
}
QWidget[aminateEmbeddedPanel="true"] QTabBar::tab:selected {
    background-color: #566A7A;
    color: #FFFFFF;
    font-weight: 700;
}
"""


AMINATE_PRIMARY_ACTION_LABELS = {
    "Package Scene To Zip",
    "Reparent to Selected Parent",
    "Create / Update Hold",
    "Create / Update Collision",
    "Turn From Pivot",
    "Switch FK -> IK",
    "Switch IK -> FK",
    "Retarget All Controls",
    "Start Drawing",
    "Apply Hold",
    "Save Step",
    "Attach Selected",
    "Use Best Fix",
    "Track A: Copy Whole Character (Safe)",
    "Transfer Skin (Auto)",
    "Make Copy",
    "Make Tracing Card",
    "Add Note",
    "Create Smear Frame",
    "Apply Colors",
}
AMINATE_DANGER_ACTION_LABELS = {
    "Clear Pivot",
    "Delete Picked Switch",
    "Delete Hold",
    "Delete Selected",
    "Delete All Collision",
    "Delete Frozen Copy",
    "Delete Export Copy",
    "Delete Picked Note",
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
    """Keep Aminate's canonical yellow Donate action compact and readable."""
    if not button or not QtWidgets:
        return
    button.setMinimumWidth(70)
    button.setCursor(_qt_flag("CursorShape", "PointingHandCursor", None))
    button.setStyleSheet(
        """
        QToolButton {
            background-color: #FFC439;
            color: #111111;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 4px 10px;
            font-weight: 600;
        }
        QToolButton:hover {
            background-color: #FFD35A;
        }
        QToolButton:pressed {
            background-color: #F0B92B;
        }
        QToolButton:focus {
            border-color: #FFFFFF;
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


def _open_local_file_at_fragment(path, fragment):
    if not path or not os.path.exists(path):
        return False
    if QtGui and QtCore and hasattr(QtGui, "QDesktopServices"):
        url = QtCore.QUrl.fromLocalFile(path)
        if fragment:
            url.setFragment(str(fragment))
        if QtGui.QDesktopServices.openUrl(url):
            return True
    return _open_local_file(path)


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


def _hide_workspace_control(name):
    # Maya 2026 can fault when a retained Aminate workspace changes native
    # visibility.  Launch paths reuse the existing dock instead of hiding it.
    return False


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


def _cleanup_duplicate_workflow_widgets(keep_widget=None):
    for widget in _workflow_widgets():
        if not _qt_object_valid(widget):
            continue
        if keep_widget is not None and widget is keep_widget:
            continue
        if keep_widget is not None and _widget_is_ancestor(widget, keep_widget):
            continue
        try:
            widget.hide()
        except Exception:
            pass


def _ensure_single_workflow_widget(keep_widget=None):
    if not QtWidgets:
        return
    _process_qt_events()
    _cleanup_duplicate_workflow_widgets(keep_widget=keep_widget)
    _process_qt_events()


def _close_existing_window():
    if GLOBAL_WINDOW is not None and _qt_object_valid(GLOBAL_WINDOW):
        docked_workspace = _workspace_control_exists(WORKSPACE_CONTROL_NAME)
        if docked_workspace:
            # Maya 2026 Qt6Core faults when retained dock visibility changes.
            # Keep one live dock plus window for safe reuse.
            return False
        pencil_panel = getattr(GLOBAL_WINDOW, "animators_pencil_panel", None)
        suspend_runtime = getattr(pencil_panel, "_deactivate_runtime_input", None)
        if suspend_runtime:
            try:
                suspend_runtime()
            except Exception:
                pass
        try:
            hide_extras = getattr(GLOBAL_WINDOW, "_hide_toolbar_extras_if_needed", None)
            if hide_extras:
                hide_extras()
        except Exception:
            pass
        try:
            GLOBAL_WINDOW._remove_key_passthrough_filter()
        except Exception:
            pass
        try:
            GLOBAL_WINDOW.setVisible(False)
        except Exception:
            pass
    _process_qt_events()
    return True


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


def _angle_delta(first, second):
    """Return the shortest Euler-angle delta in degrees."""
    return ((float(first) - float(second) + 180.0) % 360.0) - 180.0


def _pose_mismatches(node_name, translation, rotation):
    """Report world-space channels that still differ after a copy attempt."""
    mismatches = []
    try:
        current_translation = _world_translation(node_name)
    except Exception:
        current_translation = None
    if current_translation is None or len(current_translation) < 3:
        mismatches.extend(("translateX", "translateY", "translateZ"))
    else:
        for index, value in enumerate(translation[:3]):
            if abs(float(current_translation[index]) - float(value)) > 1.0e-4:
                mismatches.append(("translateX", "translateY", "translateZ")[index])
    try:
        current_rotation = _world_rotation(node_name)
    except Exception:
        current_rotation = None
    if current_rotation is None or len(current_rotation) < 3:
        mismatches.extend(("rotateX", "rotateY", "rotateZ"))
    else:
        for index, value in enumerate(rotation[:3]):
            if abs(_angle_delta(current_rotation[index], value)) > 1.0e-4:
                mismatches.append(("rotateX", "rotateY", "rotateZ")[index])
    return mismatches


def _copy_world_pose(target_node, source_node):
    """Copy world translation and rotation, returning honest pose/key status.

    Maya controls can expose locked translate or rotate channels.  A failed
    xform is intentionally retained as a mismatch instead of being reported as
    an exact match.  Callers can still finish the switch and surface the
    actionable mismatch to the user.
    """
    result = {
        "target": target_node,
        "source": source_node,
        "translation": False,
        "rotation": False,
        "mismatches": [],
        "locked": [],
    }
    if not target_node or not source_node:
        result["mismatches"] = ["missing target or source"]
        return result
    try:
        translation = list(_world_translation(source_node))
        rotation = list(_world_rotation(source_node))
    except Exception as exc:
        result["mismatches"] = ["could not read source pose: {0}".format(exc)]
        return result
    for attr_name in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
        plug = "{0}.{1}".format(target_node, attr_name)
        try:
            if cmds.objExists(plug) and cmds.getAttr(plug, lock=True):
                result["locked"].append(attr_name)
        except Exception:
            pass
    try:
        _set_world_translation(target_node, translation)
        result["translation"] = True
    except Exception:
        pass
    try:
        _set_world_rotation(target_node, rotation)
        result["rotation"] = True
    except Exception:
        pass
    result["mismatches"] = _pose_mismatches(target_node, translation, rotation)
    return result


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
        if end < start:
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
    inverse_pivot_matrix = om.MTransformationMatrix()
    inverse_pivot_matrix.setTranslation(om.MVector(*[-value for value in pivot_position]), om.MSpace.kWorld)
    rotate_matrix = om.MTransformationMatrix()
    euler_rotation = om.MEulerRotation(
        math.radians(rotation_degrees[0]),
        math.radians(rotation_degrees[1]),
        math.radians(rotation_degrees[2]),
        om.MEulerRotation.kXYZ,
    )
    rotate_matrix.rotateBy(euler_rotation, om.MSpace.kTransform)
    pivot_matrix = om.MTransformationMatrix()
    pivot_matrix.setTranslation(om.MVector(*pivot_position), om.MSpace.kWorld)
    # Maya points post-multiply matrices (P' = P * M), so a world-space
    # turn around P must move by -P, rotate, then move back by +P.
    return inverse_pivot_matrix.asMatrix() * rotate_matrix.asMatrix() * pivot_matrix.asMatrix()


PIVOT_TR_CHANNELS = (
    "translateX",
    "translateY",
    "translateZ",
    "rotateX",
    "rotateY",
    "rotateZ",
)

PIVOT_PROTECTED_CHANNELS = (
    "scaleX",
    "scaleY",
    "scaleZ",
    "shearXY",
    "shearXZ",
    "shearYZ",
    "rotateOrder",
    "rotateAxisX",
    "rotateAxisY",
    "rotateAxisZ",
    "rotatePivotX",
    "rotatePivotY",
    "rotatePivotZ",
    "rotatePivotTranslateX",
    "rotatePivotTranslateY",
    "rotatePivotTranslateZ",
    "scalePivotX",
    "scalePivotY",
    "scalePivotZ",
    "scalePivotTranslateX",
    "scalePivotTranslateY",
    "scalePivotTranslateZ",
    "jointOrientX",
    "jointOrientY",
    "jointOrientZ",
)


def _pivot_matrix_matches(first, second, tolerance=1.0e-4):
    """Return whether two world matrices are numerically equal."""
    try:
        return all(abs(float(first[index]) - float(second[index])) <= tolerance for index in range(16))
    except Exception:
        return False


def _pivot_world_rotate_pivot(node_name):
    """Return the animator-visible rotate pivot in world space."""
    values = cmds.xform(node_name, query=True, worldSpace=True, rotatePivot=True) or []
    if len(values) != 3:
        raise RuntimeError("Could not read the world rotate pivot for {0}.".format(node_name))
    return [float(value) for value in values]


def _pivot_point_after_delta(point, delta_matrix):
    transformed = om.MPoint(*[float(value) for value in point]) * om.MMatrix(delta_matrix)
    return [float(transformed.x), float(transformed.y), float(transformed.z)]


def _pivot_protected_values(node_name):
    """Snapshot fixed transform components Dynamic Pivot must never rewrite."""
    values = {}
    for attr_name in PIVOT_PROTECTED_CHANNELS:
        plug = "{0}.{1}".format(node_name, attr_name)
        if cmds.objExists(plug):
            values[attr_name] = float(cmds.getAttr(plug))
    return values


def _pivot_protected_differences(expected, actual, tolerance=1.0e-7):
    differences = []
    for attr_name in sorted(set(expected) | set(actual)):
        if attr_name not in expected or attr_name not in actual:
            differences.append(attr_name)
            continue
        if abs(float(expected[attr_name]) - float(actual[attr_name])) > float(tolerance):
            differences.append(attr_name)
    return differences


def _pivot_snapshot(node_name):
    return {
        "matrix": _matrix_from_node(node_name),
        "world_rotate_pivot": _pivot_world_rotate_pivot(node_name),
        "protected": _pivot_protected_values(node_name),
    }


def _pivot_expected_pose(snapshot, delta_matrix=None):
    expected_matrix = snapshot["matrix"]
    expected_rotate_pivot = list(snapshot["world_rotate_pivot"])
    if delta_matrix is not None:
        expected_matrix = expected_matrix * delta_matrix
        expected_rotate_pivot = _pivot_point_after_delta(expected_rotate_pivot, delta_matrix)
    return expected_matrix, expected_rotate_pivot


def _pivot_node_pose_matches(
    node_name,
    expected_matrix,
    expected_rotate_pivot,
    matrix_tolerance=1.0e-4,
    pivot_tolerance=1.0e-4,
):
    """Prove the full world transform and its animator-visible rotate pivot."""
    if not _pivot_matrix_matches(_matrix_from_node(node_name), expected_matrix, tolerance=matrix_tolerance):
        return False
    actual_rotate_pivot = _pivot_world_rotate_pivot(node_name)
    return max(
        abs(float(actual_rotate_pivot[index]) - float(expected_rotate_pivot[index]))
        for index in range(3)
    ) <= float(pivot_tolerance)


def _set_pivot_world_pose(node_name, expected_matrix, expected_rotate_pivot, protected_values=None):
    """Land an exact world pose while writing only animator translation/rotation."""
    transform = om.MTransformationMatrix(om.MMatrix(expected_matrix))
    euler = transform.rotation(asQuaternion=True).asEulerRotation()
    preserved = protected_values or _pivot_protected_values(node_name)
    cmds.xform(
        node_name,
        worldSpace=True,
        rotation=(
            math.degrees(euler.x),
            math.degrees(euler.y),
            math.degrees(euler.z),
        ),
    )
    # World translation queries include Maya's pivot compensation semantics.
    # Move by the rotate-pivot error instead of assigning matrix translation,
    # which would silently write rotatePivotTranslate on offset-pivot controls.
    for _attempt in range(2):
        actual_rotate_pivot = _pivot_world_rotate_pivot(node_name)
        correction = [
            float(expected_rotate_pivot[index]) - float(actual_rotate_pivot[index])
            for index in range(3)
        ]
        if max(abs(value) for value in correction) <= 1.0e-7:
            break
        current_translation = _world_translation(node_name)
        _set_world_translation(
            node_name,
            [
                float(current_translation[index]) + correction[index]
                for index in range(3)
            ],
        )
    changed = _pivot_protected_differences(preserved, _pivot_protected_values(node_name))
    if changed:
        raise RuntimeError(
            "Dynamic Pivot changed fixed transform data on {0}: {1}.".format(
                _short_name(node_name),
                ", ".join(changed[:6]),
            )
        )


def _pivot_parent_first_targets(targets):
    """Dedupe selected controls and order them from DAG parent to child."""
    ordered = []
    seen = set()
    for target in targets:
        if not target or not cmds.objExists(target):
            continue
        resolved = (cmds.ls(target, long=True) or [target])[0]
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return sorted(ordered, key=lambda node_name: (node_name.count("|"), ordered.index(node_name), node_name))


def _pivot_channel_blockers(node_name):
    """Return locked or non-animation driven channels that cannot be baked safely."""
    blockers = []
    for attr_name in PIVOT_TR_CHANNELS:
        plug = "{0}.{1}".format(node_name, attr_name)
        if not cmds.objExists(plug):
            blockers.append("{0} is missing".format(plug))
            continue
        try:
            if cmds.getAttr(plug, lock=True):
                blockers.append("{0} is locked".format(plug))
        except Exception as exc:
            blockers.append("{0} lock state could not be read: {1}".format(plug, exc))
        try:
            incoming = cmds.listConnections(plug, source=True, destination=False, plugs=True) or []
        except Exception as exc:
            blockers.append("{0} connections could not be read: {1}".format(plug, exc))
            incoming = []
        for source_plug in incoming:
            source_node = source_plug.rsplit(".", 1)[0]
            try:
                source_type = cmds.nodeType(source_node) or ""
            except Exception:
                source_type = ""
            if source_type.startswith("animCurve"):
                continue
            blockers.append("{0} is driven by {1}".format(plug, source_plug))
    return blockers


def _pivot_apply_times():
    """Return integer sampled frames and the source range metadata."""
    highlighted = _highlighted_time_range()
    if highlighted:
        start, end = highlighted
        first = int(math.ceil(float(start) - EPSILON))
        last = int(math.floor(float(end) + EPSILON))
        return list(range(first, last + 1)) if last >= first else [], ("highlighted", start, end)
    current_time = float(cmds.currentTime(query=True))
    return [current_time], ("current", current_time, current_time)


def _pivot_guard_times(sample_times):
    """Return one unchanged frame on either side of a Dynamic Pivot bake."""
    if not sample_times:
        return []
    ordered = sorted(float(frame_value) for frame_value in sample_times)
    return [ordered[0] - 1.0, ordered[-1] + 1.0]


def _pivot_range_text(range_info):
    kind, start, end = range_info
    if kind == "highlighted":
        first = int(math.ceil(float(start) - EPSILON))
        last = int(math.floor(float(end) + EPSILON))
        if last < first:
            return "Highlighted range has no whole frames to turn."
        return "Highlighted frames {0}-{1}: every whole frame will be turned.".format(
            _frame_display(first),
            _frame_display(last),
        )
    return "No highlighted range: only current frame {0} will be turned.".format(_frame_display(start))


def _key_pivot_channels(node_name, frame_value):
    """Key every pivot TR channel and fail if Maya did not create the key."""
    for attr_name in PIVOT_TR_CHANNELS:
        plug = "{0}.{1}".format(node_name, attr_name)
        try:
            cmds.setKeyframe(node_name, attribute=attr_name, time=(frame_value, frame_value))
        except Exception as exc:
            raise RuntimeError("Could not key {0} at frame {1}: {2}".format(plug, _frame_display(frame_value), exc))
        keyed_times = cmds.keyframe(
            node_name,
            attribute=attr_name,
            query=True,
            time=(frame_value, frame_value),
            timeChange=True,
        ) or []
        if not any(abs(float(keyed_time) - float(frame_value)) <= EPSILON for keyed_time in keyed_times):
            raise RuntimeError("Maya did not create the required key for {0} at frame {1}.".format(plug, _frame_display(frame_value)))


def _pivot_first_query_value(values, default=None):
    if isinstance(values, (list, tuple)):
        return values[0] if values else default
    return values if values is not None else default


def _pivot_guard_tangent_snapshot(node_name, attr_name, frame_value, side, had_curve):
    """Capture the outside-facing tangent after a shape-preserving guard-key insert."""
    type_flag = "inTangentType" if side == "in" else "outTangentType"
    angle_flag = "inAngle" if side == "in" else "outAngle"
    weight_flag = "inWeight" if side == "in" else "outWeight"
    query_args = {
        "attribute": attr_name,
        "query": True,
        "time": (frame_value, frame_value),
    }
    tangent_type = _pivot_first_query_value(
        cmds.keyTangent(node_name, **dict(query_args, **{type_flag: True})),
        "auto",
    )
    angle = float(_pivot_first_query_value(
        cmds.keyTangent(node_name, **dict(query_args, **{angle_flag: True})),
        0.0,
    ))
    weight = float(_pivot_first_query_value(
        cmds.keyTangent(node_name, **dict(query_args, **{weight_flag: True})),
        1.0,
    ))
    weighted = bool(_pivot_first_query_value(
        cmds.keyTangent(node_name, attribute=attr_name, query=True, weightedTangents=True),
        False,
    ))
    return {
        "node": node_name,
        "attribute": attr_name,
        "time": float(frame_value),
        "side": side,
        "type": tangent_type,
        "angle": angle,
        "weight": weight,
        "weighted": weighted,
        "preserve": bool(had_curve),
    }


def _insert_pivot_guard_keys(node_name, frame_value, side):
    """Insert unchanged guard keys and remember their outside curve shape."""
    snapshots = []
    for attr_name in PIVOT_TR_CHANNELS:
        existing_times = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
        had_curve = bool(existing_times)
        has_key_here = any(abs(float(key_time) - float(frame_value)) <= EPSILON for key_time in existing_times)
        if not has_key_here:
            try:
                cmds.setKeyframe(
                    node_name,
                    attribute=attr_name,
                    time=(frame_value, frame_value),
                    insert=had_curve,
                )
            except Exception:
                cmds.setKeyframe(node_name, attribute=attr_name, time=(frame_value, frame_value))
        keyed_times = cmds.keyframe(
            node_name,
            attribute=attr_name,
            query=True,
            time=(frame_value, frame_value),
            timeChange=True,
        ) or []
        if not any(abs(float(key_time) - float(frame_value)) <= EPSILON for key_time in keyed_times):
            raise RuntimeError(
                "Maya did not create the guard key for {0}.{1} at frame {2}.".format(
                    node_name,
                    attr_name,
                    _frame_display(frame_value),
                )
            )
        snapshots.append(_pivot_guard_tangent_snapshot(node_name, attr_name, frame_value, side, had_curve))
    return snapshots


def _restore_pivot_keyed_pose(
    node_name,
    frame_value,
    expected_matrix,
    expected_rotate_pivot,
    protected_values,
):
    """Re-assert a keyed pose after every range and guard key now exists.

    Maya can evaluate a keyed parent/child control differently at a guard frame
    after new keys are inserted inside the highlighted range.  Re-applying the
    expected world matrices once the full key topology exists stabilizes both
    the highlighted samples and their unchanged boundary frames.  The caller
    restores the captured outside-facing tangents afterwards.
    """
    _set_pivot_world_pose(
        node_name,
        expected_matrix,
        expected_rotate_pivot,
        protected_values=protected_values,
    )
    _key_pivot_channels(node_name, frame_value)
    if not _pivot_node_pose_matches(node_name, expected_matrix, expected_rotate_pivot):
        raise RuntimeError(
            "Could not restore {0} at guard frame {1}.".format(
                _short_name(node_name),
                _frame_display(frame_value),
            )
        )


def _restore_pivot_guard_tangent(snapshot):
    """Keep the curve segment outside the bake range looking as it did before."""
    if not snapshot.get("preserve"):
        return
    node_name = snapshot["node"]
    attr_name = snapshot["attribute"]
    frame_value = snapshot["time"]
    side = snapshot["side"]
    tangent_type = str(snapshot.get("type") or "auto")
    type_flag = "inTangentType" if side == "in" else "outTangentType"
    angle_flag = "inAngle" if side == "in" else "outAngle"
    weight_flag = "inWeight" if side == "in" else "outWeight"
    edit_args = {
        "attribute": attr_name,
        "edit": True,
        "time": (frame_value, frame_value),
        "lock": False,
    }
    cmds.keyTangent(node_name, **edit_args)
    if tangent_type in ("fixed", "spline", "auto", "clamped", "plateau"):
        fixed_args = dict(edit_args)
        fixed_args[type_flag] = "fixed"
        fixed_args[angle_flag] = float(snapshot.get("angle", 0.0))
        if snapshot.get("weighted"):
            fixed_args[weight_flag] = float(snapshot.get("weight", 1.0))
        cmds.keyTangent(node_name, **fixed_args)
    else:
        typed_args = dict(edit_args)
        typed_args[type_flag] = tangent_type
        cmds.keyTangent(node_name, **typed_args)


def _zero_rotation_strict(node_name):
    for axis in ("X", "Y", "Z"):
        plug = "{0}.rotate{1}".format(node_name, axis)
        if not cmds.objExists(plug):
            raise RuntimeError("Pivot marker channel {0} is missing.".format(plug))
        if cmds.getAttr(plug, lock=True):
            raise RuntimeError("Pivot marker channel {0} is locked.".format(plug))
        cmds.setAttr(plug, 0.0)
        if abs(float(cmds.getAttr(plug))) > EPSILON:
            raise RuntimeError("Pivot marker channel {0} could not be zeroed.".format(plug))


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


def _dynamic_pivot_radius(targets):
    """Size the temporary marker from the selected control shapes."""
    candidates = []
    for node_name in targets:
        shapes = cmds.listRelatives(
            node_name,
            shapes=True,
            noIntermediate=True,
            fullPath=True,
        ) or []
        if not shapes:
            continue
        try:
            bbox = cmds.exactWorldBoundingBox(*shapes)
            span = max(
                abs(float(bbox[index + 3]) - float(bbox[index]))
                for index in range(3)
            )
            if math.isfinite(span) and span > EPSILON:
                candidates.append(span * 0.35)
        except Exception:
            continue
    if not candidates:
        candidates = [
            _controller_radius_from_target(node_name)
            for node_name in targets
        ]
    return max(max(candidates or [1.6]), 1.6)


def _style_dynamic_pivot_marker(control):
    """Keep the temporary pivot readable through a busy character rig."""
    for shape in cmds.listRelatives(control, shapes=True, fullPath=True) or []:
        for attr_name, value in (("lineWidth", 3.5), ("alwaysDrawOnTop", True)):
            plug = "{0}.{1}".format(shape, attr_name)
            if cmds.objExists(plug):
                try:
                    cmds.setAttr(plug, value)
                except Exception:
                    pass


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
    if not rig_root_hint:
        return all_nodes
    if not cmds.objExists(rig_root_hint):
        return []
    filtered = []
    for node_name in all_nodes:
        if node_name == rig_root_hint or node_name.startswith(rig_root_hint + "|"):
            filtered.append(node_name)
    return filtered


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


def _detect_ik_match_node(nodes, ik_control, side, limb):
    if not ik_control:
        return ""
    ik_leaf = _strip_namespace(ik_control)
    exact_leaf_names = {
        ik_leaf + "_ikfk_seamless",
        ik_leaf + "_fkik_seamless",
        ik_leaf + "_ikfk_match",
        ik_leaf + "_fkik_match",
        ik_leaf + "_match",
    }
    exact = [
        node_name
        for node_name in nodes
        if _strip_namespace(node_name) in exact_leaf_names
    ]
    if len(exact) == 1:
        return exact[0]
    ranked = []
    for node_name in nodes:
        lowered = _strip_namespace(node_name).lower()
        if ik_leaf.lower() not in lowered:
            continue
        if not any(token in lowered for token in ("seamless", "match")):
            continue
        score = _score_node_name(node_name, (side, limb, "ik"), ("seamless", "match"))
        if "ikfk" in lowered or "fkik" in lowered:
            score += 8
        ranked.append((score, node_name))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not ranked:
        return ""
    best_score = ranked[0][0]
    best = [node_name for score, node_name in ranked if score == best_score]
    return best[0] if len(best) == 1 else ""


def _resolve_profile_node(node_name, rig_root_hint=""):
    if not node_name:
        return ""
    all_nodes = _all_transforms_and_joints()

    def _matches_name(candidate, requested):
        requested_leaf = requested.split("|")[-1]
        candidate_leaf = candidate.split("|")[-1]
        if ":" in requested_leaf:
            return candidate_leaf == requested_leaf
        return _strip_namespace(candidate) == _strip_namespace(requested)

    rig_root = rig_root_hint or ""
    if rig_root:
        if rig_root.startswith("|") and rig_root in all_nodes:
            root_candidates = [rig_root]
        else:
            root_candidates = [candidate for candidate in all_nodes if _matches_name(candidate, rig_root)]
        if len(root_candidates) != 1:
            return ""
        rig_root = root_candidates[0]
    if node_name.startswith("|") and node_name in all_nodes:
        candidates = [node_name]
        if rig_root and node_name != rig_root and not node_name.startswith(rig_root + "|"):
            candidates = []
    else:
        candidates = []
    if not candidates:
        for candidate in all_nodes:
            if not _matches_name(candidate, node_name):
                continue
            if rig_root and candidate != rig_root and not candidate.startswith(rig_root + "|"):
                continue
            candidates.append(candidate)
    # A short name is safe only when it resolves to one node in the selected
    # rig root.  Never let another character with the same short name win.
    if len(candidates) != 1:
        return ""
    return candidates[0]


def _resolve_profile_attr(attr_path, rig_root_hint=""):
    if not attr_path or "." not in attr_path:
        return ""
    node_name, attr_name = attr_path.rsplit(".", 1)
    resolved = _resolve_profile_node(node_name, rig_root_hint=rig_root_hint)
    if not resolved:
        return ""
    plug = "{0}.{1}".format(resolved, attr_name)
    return plug if cmds.objExists(plug) else ""


def _is_generic_chain(profile):
    """Whether a profile explicitly describes a paired multi-control chain."""
    mode = (profile.get("chain_mode", "") or "").strip().lower()
    if mode in ("generic", "chain", "explicit"):
        return True
    fk_controls = [node_name for node_name in profile.get("fk_controls", []) if node_name]
    ik_controls = [node_name for node_name in profile.get("ik_controls", []) if node_name]
    match_nodes = [node_name for node_name in profile.get("match_nodes", []) if node_name]
    return len(fk_controls) >= 3 and len(fk_controls) == len(ik_controls) == len(match_nodes)


class AminateController(object):
    def __init__(self):
        self.driver_node = ""
        self.release_space = "world"
        # Preserve the animator's source timing by default.  Dense whole-frame
        # baking remains available as an explicit Bake Frames choice.
        self.bake_mode = "keys"
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
        pivot_ctrl = _draw_temp_control(
            _unique_name(PIVOT_CTRL_NAME),
            _dynamic_pivot_radius(targets),
        )
        _style_dynamic_pivot_marker(pivot_ctrl)
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
        targets = _pivot_parent_first_targets(targets)
        blockers = []
        for node_name in targets:
            blockers.extend(_pivot_channel_blockers(node_name))
        if blockers:
            return False, "Cannot turn exactly; nothing was changed. " + "; ".join(blockers[:6])
        pivot_position = _world_translation(self.active_pivot)
        sample_times, range_info = _pivot_apply_times()
        if not sample_times:
            return False, "Cannot turn exactly; the highlighted range contains no whole frames."
        guard_times = _pivot_guard_times(sample_times)
        snapshot_times = sorted(set(float(frame_value) for frame_value in guard_times + sample_times))
        current_time = float(cmds.currentTime(query=True))
        original_selection = cmds.ls(selection=True, long=True) or []
        try:
            undo_enabled = bool(cmds.undoInfo(query=True, state=True))
        except Exception as exc:
            return False, "Cannot prove Maya Undo is available; nothing was changed. {0}".format(exc)
        if not undo_enabled:
            return False, "Cannot turn exactly while Maya Undo is disabled; enable Undo and try again."
        snapshots = {}
        delta_matrix = _compose_around_pivot_matrix(pivot_position, rotation_values)
        try:
            for frame_value in snapshot_times:
                cmds.currentTime(frame_value, edit=True)
                snapshots[frame_value] = {
                    node_name: _pivot_snapshot(node_name)
                    for node_name in targets
                }
        except Exception as exc:
            try:
                cmds.currentTime(current_time, edit=True)
            except Exception:
                pass
            return False, "Could not read every selected pose; nothing was changed. {0}".format(exc)

        undo_open = False
        writes_started = False
        guard_tangents = []
        try:
            cmds.undoInfo(openChunk=True, chunkName="Dynamic Pivot Range")
            undo_open = True
            for guard_index, frame_value in enumerate(guard_times):
                cmds.currentTime(frame_value, edit=True)
                tangent_side = "in" if guard_index == 0 else "out"
                for node_name in targets:
                    snapshot = snapshots[frame_value][node_name]
                    expected_matrix, expected_rotate_pivot = _pivot_expected_pose(snapshot)
                    writes_started = True
                    guard_tangents.extend(_insert_pivot_guard_keys(node_name, frame_value, tangent_side))
                    if not _pivot_node_pose_matches(node_name, expected_matrix, expected_rotate_pivot):
                        raise RuntimeError(
                            "Could not protect {0} at frame {1}.".format(
                                _short_name(node_name),
                                _frame_display(frame_value),
                            )
                        )
            for frame_value in sample_times:
                cmds.currentTime(frame_value, edit=True)
                for node_name in targets:
                    snapshot = snapshots[frame_value][node_name]
                    expected_matrix, expected_rotate_pivot = _pivot_expected_pose(snapshot, delta_matrix)
                    writes_started = True
                    _set_pivot_world_pose(
                        node_name,
                        expected_matrix,
                        expected_rotate_pivot,
                        protected_values=snapshot["protected"],
                    )
                    if not _pivot_node_pose_matches(node_name, expected_matrix, expected_rotate_pivot):
                        raise RuntimeError(
                            "Could not place {0} exactly at frame {1}.".format(
                                _short_name(node_name),
                                _frame_display(frame_value),
                            )
                        )
                    _key_pivot_channels(node_name, frame_value)
                    if not _pivot_node_pose_matches(node_name, expected_matrix, expected_rotate_pivot):
                        raise RuntimeError(
                            "Keying changed {0} at frame {1}.".format(
                                _short_name(node_name),
                                _frame_display(frame_value),
                            )
                        )
            # In Maya, inserting keys can change an evaluated keyed
            # parent/child pose.  Once every sample and guard key exists,
            # re-assert all expected matrices against that final key topology.
            sample_time_set = set(float(frame_value) for frame_value in sample_times)
            for frame_value in snapshot_times:
                cmds.currentTime(frame_value, edit=True)
                for node_name in targets:
                    writes_started = True
                    snapshot = snapshots[frame_value][node_name]
                    expected_matrix, expected_rotate_pivot = _pivot_expected_pose(
                        snapshot,
                        delta_matrix if float(frame_value) in sample_time_set else None,
                    )
                    _restore_pivot_keyed_pose(
                        node_name,
                        frame_value,
                        expected_matrix,
                        expected_rotate_pivot,
                        snapshot["protected"],
                    )
            for tangent_snapshot in guard_tangents:
                _restore_pivot_guard_tangent(tangent_snapshot)
            for frame_value in guard_times:
                cmds.currentTime(frame_value, edit=True)
                for node_name in targets:
                    snapshot = snapshots[frame_value][node_name]
                    expected_matrix, expected_rotate_pivot = _pivot_expected_pose(snapshot)
                    if not _pivot_node_pose_matches(node_name, expected_matrix, expected_rotate_pivot):
                        raise RuntimeError(
                            "The animation outside the range changed for {0} at frame {1}.".format(
                                _short_name(node_name),
                                _frame_display(frame_value),
                            )
                        )
            for frame_value in sample_times:
                cmds.currentTime(frame_value, edit=True)
                for node_name in targets:
                    snapshot = snapshots[frame_value][node_name]
                    expected_matrix, expected_rotate_pivot = _pivot_expected_pose(snapshot, delta_matrix)
                    if not _pivot_node_pose_matches(node_name, expected_matrix, expected_rotate_pivot):
                        raise RuntimeError(
                            "The keyed range pose changed for {0} at frame {1}.".format(
                                _short_name(node_name),
                                _frame_display(frame_value),
                            )
                        )
            writes_started = True
            _zero_rotation_strict(self.active_pivot)
            cmds.undoInfo(closeChunk=True)
            undo_open = False
        except Exception as exc:
            rollback_verified = True
            if undo_open:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass
                undo_open = False
                if writes_started:
                    try:
                        cmds.undo()
                    except Exception:
                        rollback_verified = False
            if rollback_verified:
                try:
                    for frame_value in snapshot_times:
                        cmds.currentTime(frame_value, edit=True)
                        for node_name in targets:
                            if not _pivot_matrix_matches(
                                _matrix_from_node(node_name),
                                snapshots[frame_value][node_name]["matrix"],
                            ):
                                rollback_verified = False
                                break
                        if not rollback_verified:
                            break
                except Exception:
                    rollback_verified = False
            if rollback_verified:
                return False, "Could not turn the selected controls exactly; everything was rolled back. {0}".format(exc)
            return False, "Could not turn the selected controls exactly, and rollback could not be proven. Use Undo immediately. {0}".format(exc)
        finally:
            if undo_open:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass
            try:
                cmds.currentTime(current_time, edit=True)
            except Exception:
                pass
            try:
                if original_selection:
                    cmds.select(original_selection, replace=True)
                else:
                    cmds.select(clear=True)
            except Exception:
                pass
        return True, "Turned {0} object(s) on {1}".format(len(targets), _pivot_range_text(range_info))

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
        if not selected:
            return {
                "profile_name": "",
                "rig_root": "",
                "namespace_hint": "",
                "limb_type": "arm",
                "side": "left",
                "fk_controls": [],
                "ik_controls": [],
                "ik_control": "",
                "pole_vector_control": "",
                "switch_attr": "",
                "fk_value": 0.0,
                "ik_value": 1.0,
                "extra_controls": [],
                "match_nodes": [],
                "ik_match_node": "",
            }, ["Select one or more controls from a single rig root before setting up an IK/FK switch."]
        roots = _dedupe_preserve_order([_top_parent(node_name) for node_name in selected if node_name])
        if len(roots) != 1:
            return {
                "profile_name": "",
                "rig_root": "",
                "namespace_hint": "",
                "limb_type": "arm",
                "side": "left",
                "fk_controls": [],
                "ik_controls": [],
                "ik_control": "",
                "pole_vector_control": "",
                "switch_attr": "",
                "fk_value": 0.0,
                "ik_value": 1.0,
                "extra_controls": [],
                "match_nodes": [],
                "ik_match_node": "",
            }, ["Select controls from one rig root only; the current selection spans multiple rigs."]
        search_nodes = selected
        side = _detect_side_from_nodes(search_nodes)
        limb = _detect_limb_from_nodes(search_nodes)
        rig_root = roots[0]

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
                "ik_match_node": _detect_ik_match_node(candidates, ik_control, side, limb),
            }

        candidates = _candidate_nodes_for_profile(rig_root_hint=rig_root)
        detected_data = _detect_from_candidates(candidates)
        if not candidates:
            return {
                "profile_name": "{0}_{1}".format(side, limb),
                "rig_root": rig_root,
                "namespace_hint": _namespace_prefix(selected[0]),
                "limb_type": limb,
                "side": side,
                "fk_controls": [],
                "ik_controls": [],
                "ik_control": "",
                "pole_vector_control": "",
                "switch_attr": "",
                "fk_value": 0.0,
                "ik_value": 1.0,
                "extra_controls": [],
                "match_nodes": [],
                "ik_match_node": "",
            }, ["Could not inspect the selected rig root; no IK/FK candidates were found inside it."]
        if detected_data["ik_control"] and detected_data["ik_control"] == detected_data["pole_vector_control"]:
            distinct_ik = _best_ik_end_control(candidates, side, limb, exclude=(detected_data["pole_vector_control"],))
            if distinct_ik:
                detected_data["ik_control"] = distinct_ik
            distinct_pv = _best_pole_vector_control(candidates, side, limb, exclude=(detected_data["ik_control"],))
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
            "ik_match_node": detected_data["ik_match_node"],
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
        normalized["chain_mode"] = (normalized.get("chain_mode", "") or "").strip().lower()
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
        normalized["ik_match_node"] = normalized.get("ik_match_node", "").strip()
        return normalized

    def _profile_from_fields(self, fields):
        profile = {
            "profile_name": fields.get("profile_name", "").strip(),
            "rig_root": fields.get("rig_root", "").strip(),
            "namespace_hint": fields.get("namespace_hint", "").strip(),
            "limb_type": fields.get("limb_type", "arm").strip() or "arm",
            "side": fields.get("side", "left").strip() or "left",
            "chain_mode": fields.get("chain_mode", "").strip().lower(),
            "fk_controls": [item.strip() for item in fields.get("fk_controls", []) if item.strip()],
            "ik_controls": [item.strip() for item in fields.get("ik_controls", []) if item.strip()],
            "ik_control": fields.get("ik_control", "").strip(),
            "pole_vector_control": fields.get("pole_vector_control", "").strip(),
            "switch_attr": fields.get("switch_attr", "").strip(),
            "fk_value": float(fields.get("fk_value", 0.0)),
            "ik_value": float(fields.get("ik_value", 1.0)),
            "extra_controls": [item.strip() for item in fields.get("extra_controls", []) if item.strip()],
            "match_nodes": [item.strip() for item in fields.get("match_nodes", []) if item.strip()],
            "ik_match_node": fields.get("ik_match_node", "").strip(),
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
        resolved["_rig_root_resolved"] = bool(rig_root)
        resolved["rig_root"] = rig_root or profile.get("rig_root", "")
        resolved["fk_controls"] = [_resolve_profile_node(node_name, rig_root_hint=resolved["rig_root"]) for node_name in profile.get("fk_controls", [])]
        resolved["ik_controls"] = [_resolve_profile_node(node_name, rig_root_hint=resolved["rig_root"]) for node_name in profile.get("ik_controls", [])]
        resolved["ik_control"] = _resolve_profile_node(profile.get("ik_control", ""), rig_root_hint=resolved["rig_root"])
        resolved["pole_vector_control"] = _resolve_profile_node(profile.get("pole_vector_control", ""), rig_root_hint=resolved["rig_root"])
        resolved["ik_controls"] = _dedupe_preserve_order(
            [node_name for node_name in (resolved["ik_control"], resolved["pole_vector_control"]) if node_name]
            + [node_name for node_name in resolved["ik_controls"] if node_name]
        )
        resolved["switch_attr"] = _resolve_profile_attr(profile.get("switch_attr", ""), rig_root_hint=resolved["rig_root"])
        resolved["extra_controls"] = [_resolve_profile_node(node_name, rig_root_hint=resolved["rig_root"]) for node_name in profile.get("extra_controls", [])]
        resolved["match_nodes"] = [_resolve_profile_node(node_name, rig_root_hint=resolved["rig_root"]) for node_name in profile.get("match_nodes", [])]
        resolved["ik_match_node"] = _resolve_profile_node(
            profile.get("ik_match_node", ""),
            rig_root_hint=resolved["rig_root"],
        )
        return resolved

    def _validate_profile(self, profile, direction):
        requested_profile = self._normalize_profile(profile)
        profile = self._resolved_profile(profile)
        issues = []
        generic_chain = _is_generic_chain(requested_profile) or _is_generic_chain(profile)
        if profile.get("rig_root") and not profile.get("_rig_root_resolved"):
            issues.append("Profile rig root could not be resolved uniquely; choose the exact rig root for this character.")
        if len([node_name for node_name in profile["fk_controls"] if node_name]) < 3:
            issues.append("This saved switch needs at least 3 FK controls.")
        if generic_chain:
            if len(profile["fk_controls"]) != len(profile["ik_controls"]) or len(profile["fk_controls"]) != len(profile["match_nodes"]):
                issues.append("Generic chain profiles need equal-length FK, IK, and match-node lists.")
            if any(not node_name for node_name in profile["fk_controls"] + profile["ik_controls"] + profile["match_nodes"]):
                issues.append("Generic chain profiles must resolve every paired control and match node inside the saved rig root.")
        else:
            if not profile["ik_control"]:
                issues.append("Profile needs an IK control.")
            if not profile["pole_vector_control"]:
                issues.append("Profile needs a pole-vector control.")
        if not profile["switch_attr"]:
            issues.append("Profile needs a switch attribute.")
        if direction == "ik_to_fk" and not generic_chain and len([node_name for node_name in profile["match_nodes"] if node_name]) < 3:
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

    def _switch_generic_chain(self, profile, direction, current_time):
        self._key_switch_context(profile, profile["fk_value"] if direction == "fk_to_ik" else profile["ik_value"], current_time)
        if direction == "fk_to_ik":
            pairs = zip(profile["ik_controls"], profile["match_nodes"])
        else:
            pairs = zip(profile["fk_controls"], profile["match_nodes"])
        mismatches = []
        for target_node, source_node in pairs:
            copy_result = _copy_world_pose(target_node, source_node)
            _set_keyable_channels(target_node, ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"))
            if copy_result["mismatches"]:
                mismatch_text = ", ".join(copy_result["mismatches"])
                if copy_result["locked"]:
                    mismatch_text += " (locked: {0})".format(", ".join(copy_result["locked"]))
                mismatches.append("{0}: {1}".format(_short_name(target_node), mismatch_text))
        node_name, attr_name = profile["switch_attr"].rsplit(".", 1)
        cmds.setAttr(profile["switch_attr"], profile["ik_value"] if direction == "fk_to_ik" else profile["fk_value"])
        cmds.setKeyframe(node_name, attribute=attr_name)
        if mismatches:
            return False, "Switched {0} on frame {1}, but exact world-pose matching was unavailable: {2}".format(
                "FK -> IK" if direction == "fk_to_ik" else "IK -> FK",
                int(current_time),
                "; ".join(mismatches),
            )
        return True, "Switched {0} on frame {1}.".format(
            "FK -> IK" if direction == "fk_to_ik" else "IK -> FK",
            int(current_time),
        )

    def switch_fk_to_ik(self, profile):
        profile, issues = self._validate_profile(profile, "fk_to_ik")
        if issues:
            return False, "; ".join(issues)
        current_time = float(cmds.currentTime(query=True))
        if _is_generic_chain(profile):
            return self._switch_generic_chain(profile, "fk_to_ik", current_time)
        self._key_switch_context(profile, profile["fk_value"], current_time)
        source_points = profile["match_nodes"] if len([node_name for node_name in profile["match_nodes"] if node_name]) >= 3 else profile["fk_controls"]
        source_points = source_points[:3]
        start_point = _world_translation(source_points[0])
        middle_point = _world_translation(source_points[1])
        end_point = _world_translation(source_points[2])
        ik_match_node = profile.get("ik_match_node") or _detect_ik_match_node(
            _candidate_nodes_for_profile(rig_root_hint=profile.get("rig_root", "")),
            profile["ik_control"],
            profile.get("side", ""),
            profile.get("limb_type", ""),
        )
        ik_pose_source = ik_match_node or source_points[2]
        _set_world_translation(profile["ik_control"], _world_translation(ik_pose_source))
        _set_world_rotation(profile["ik_control"], _world_rotation(ik_pose_source))
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
        if _is_generic_chain(profile):
            return self._switch_generic_chain(profile, "ik_to_fk", current_time)
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
            _WindowBase = type("AminateWindowBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
        else:
            _WindowBase = type("AminateWindowBase", (QtWidgets.QDialog,), {})
    except Exception:
        _WindowBase = type("AminateWindowBase", (QtWidgets.QDialog,), {})


    class AminateComboDropZone(QtWidgets.QFrame):
        """Small child surface that makes a combo's click target obvious."""

        def __init__(self, combo):
            super(AminateComboDropZone, self).__init__(combo)
            self._combo_ref = weakref.ref(combo)
            self._combo_view_ref = None
            self.setObjectName("aminateComboDropZone")
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
            self.setFocusPolicy(QtCore.Qt.NoFocus)
            self.setStyleSheet(
                """
QFrame#aminateComboDropZone {
    background-color: #303C46;
    border-left: 1px solid #536372;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
}
QFrame#aminateComboDropZone[aminateState="active"] {
    background-color: #24547F;
    border-left-color: #8FD6FF;
}
QFrame#aminateComboDropZone[aminateState="open"] {
    background-color: #1F4D78;
    border-left-color: #8FD6FF;
}
QFrame#aminateComboDropZone[aminateState="disabled"] {
    background-color: #29444D;
    border-left-color: #3E4A54;
}
"""
            )
            combo.installEventFilter(self)
            self._current_combo_view()
            self._refresh_state()
            self._reposition()

        def _combo_view(self):
            try:
                view = self._combo_view_ref() if self._combo_view_ref is not None else None
            except Exception:
                return None
            return view if _qt_object_valid(view) else None

        def _current_combo_view(self):
            """Return the live popup view, rebinding after Maya replaces it."""
            combo = self._combo_ref()
            if not _qt_object_valid(combo):
                return None
            try:
                view = combo.view()
            except Exception:
                return None
            if not _qt_object_valid(view):
                return None
            previous = self._combo_view()
            if previous is not view:
                if previous is not None:
                    try:
                        previous.removeEventFilter(self)
                    except Exception:
                        pass
                try:
                    view.installEventFilter(self)
                except Exception:
                    return None
                try:
                    self._combo_view_ref = weakref.ref(view)
                except TypeError:
                    # Never retain a popup wrapper strongly: Maya may delete
                    # and replace it while lazy panels are being rebuilt.
                    # Hosts without weak-reference support simply reacquire
                    # the current view on the next combo event.
                    self._combo_view_ref = None
            return view

        def _reposition(self):
            combo = self._combo_ref()
            if not _qt_object_valid(combo):
                return
            width = max(24, min(30, max(24, combo.width() - 20)))
            self.setGeometry(max(0, combo.width() - width), 1, width, max(1, combo.height() - 2))
            self.raise_()

        def _refresh_state(self):
            combo = self._combo_ref()
            if not _qt_object_valid(combo):
                return
            view = self._current_combo_view()
            try:
                view_open = bool(view is not None and view.isVisible())
            except Exception:
                # Maya can replace a popup QListView during lazy panel build.
                # Treat a wrapper that vanished between the validity check and
                # this read as closed; the next call will reacquire it.
                self._combo_view_ref = None
                view_open = False
            if not combo.isEnabled():
                state = "disabled"
                arrow_up = False
            elif view_open:
                state = "open"
                arrow_up = True
            elif combo.hasFocus() or combo.underMouse():
                state = "active"
                arrow_up = False
            else:
                state = "normal"
                arrow_up = False
            self.setProperty("aminateState", state)
            self._arrow_up = arrow_up
            style = self.style()
            if style:
                style.unpolish(self)
                style.polish(self)
            self.update()

        def paintEvent(self, event):
            super(AminateComboDropZone, self).paintEvent(event)
            painter = QtGui.QPainter(self)
            painter.setRenderHint(_qt_flag("RenderHint", "Antialiasing", QtGui.QPainter.Antialiasing), True)
            state = str(self.property("aminateState") or "normal")
            color = {
                "active": "#F2F7FA",
                "open": "#F7FBFC",
                "disabled": "#74818B",
            }.get(state, "#B8C4CD")
            pen = QtGui.QPen(QtGui.QColor(color), 1.8)
            pen.setCapStyle(_qt_flag("PenCapStyle", "RoundCap", QtCore.Qt.RoundCap))
            pen.setJoinStyle(_qt_flag("PenJoinStyle", "RoundJoin", QtCore.Qt.RoundJoin))
            painter.setPen(pen)
            center_x = float(self.width()) * 0.5
            center_y = float(self.height()) * 0.5 + (-1.0 if getattr(self, "_arrow_up", False) else 1.0)
            if getattr(self, "_arrow_up", False):
                points = (
                    QtCore.QPointF(center_x - 4.0, center_y + 2.0),
                    QtCore.QPointF(center_x, center_y - 2.0),
                    QtCore.QPointF(center_x + 4.0, center_y + 2.0),
                )
            else:
                points = (
                    QtCore.QPointF(center_x - 4.0, center_y - 2.0),
                    QtCore.QPointF(center_x, center_y + 2.0),
                    QtCore.QPointF(center_x + 4.0, center_y - 2.0),
                )
            painter.drawPolyline(points)
            painter.end()

        def closeEvent(self, event):
            # The child owns these filters. Remove them if the overlay is
            # explicitly closed; normal parent destruction remains Qt-owned.
            combo = self._combo_ref()
            try:
                if combo is not None:
                    combo.removeEventFilter(self)
            except Exception:
                pass
            view = self._combo_view()
            if view is not None:
                try:
                    view.removeEventFilter(self)
                except Exception:
                    pass
            return super(AminateComboDropZone, self).closeEvent(event)

        def eventFilter(self, obj, event):
            combo = self._combo_ref()
            if obj is combo and event.type() in (
                QtCore.QEvent.Resize,
                QtCore.QEvent.Show,
                QtCore.QEvent.FocusIn,
                QtCore.QEvent.FocusOut,
                QtCore.QEvent.Enter,
                QtCore.QEvent.Leave,
                QtCore.QEvent.EnabledChange,
            ):
                self._reposition()
                self._refresh_state()
            elif obj is self._combo_view() and event.type() in (QtCore.QEvent.Show, QtCore.QEvent.Hide):
                self._refresh_state()
            return super(AminateComboDropZone, self).eventFilter(obj, event)


    class AminateToolPickerCombo(QtWidgets.QComboBox):
        """Normal combo box with a reliable Maya-safe integrated chevron."""

        def paintEvent(self, event):
            super(AminateToolPickerCombo, self).paintEvent(event)
            if not QtGui:
                return
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            active = bool(self.hasFocus() or self.underMouse() or self.view().isVisible())
            color = QtGui.QColor("#F1F1F1" if active else "#B8B8B8")
            if not self.isEnabled():
                color = QtGui.QColor("#6E6E6E")
            pen = QtGui.QPen(color)
            pen.setWidthF(1.8)
            painter.setPen(pen)
            center_x = float(self.width() - 13)
            center_y = float(self.height()) * 0.5
            painter.drawLine(QtCore.QPointF(center_x - 3.5, center_y - 1.5), QtCore.QPointF(center_x, center_y + 2.0))
            painter.drawLine(QtCore.QPointF(center_x, center_y + 2.0), QtCore.QPointF(center_x + 3.5, center_y - 1.5))


    AMINATE_COMBO_AFFORDANCE_STYLESHEET = """
QComboBox[aminateComboAffordance="true"] {
    background-color: #303030;
    color: #F1F1F1;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 4px 34px 4px 8px;
    min-height: 24px;
    selection-background-color: #566A7A;
}
QComboBox[aminateComboAffordance="true"]:hover {
    background-color: #3A3A3A;
    border-color: #626262;
}
QComboBox[aminateComboAffordance="true"]:focus {
    background-color: #343434;
    border-color: #686868;
}
QComboBox[aminateComboAffordance="true"]:on {
    background-color: #414141;
    border-color: #686868;
}
QComboBox[aminateComboAffordance="true"]:disabled {
    background-color: #414141;
    color: #858585;
    border-color: #4B4B4B;
}
QComboBox[aminateComboAffordance="true"]::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border: 0px;
    background: transparent;
}
QComboBox[aminateComboAffordance="true"] QAbstractItemView {
    background-color: #414141;
    color: #F1F1F1;
    border: 1px solid #5C5C5C;
    selection-background-color: #566A7A;
    selection-color: #FFFFFF;
    outline: 0px;
    padding: 3px;
}
"""


    def _style_aminate_combo_box(combo):
        """Apply the shared drop-zone affordance to one Aminate combo.

        The Jump To control owns a more prominent custom chevron and is the
        one intentional exception.  All other QComboBox instances use this
        helper, including combos inside lazily-built embedded panels.
        """
        if not isinstance(combo, QtWidgets.QComboBox):
            return False
        if isinstance(combo, AminateToolPickerCombo) or combo.objectName() == "aminateToolPicker":
            return False
        if bool(combo.property("aminateComboAffordance")):
            return True
        combo.setProperty("aminateComboAffordance", True)
        combo.setProperty("aminateComboAffordanceWidth", 30)
        combo.setMinimumWidth(0)
        try:
            size_policy = combo.sizePolicy()
            size_policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Ignored)
            combo.setSizePolicy(size_policy)
            combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        except Exception:
            pass
        existing_stylesheet = combo.styleSheet().strip()
        combo.setStyleSheet(
            (existing_stylesheet + "\n" if existing_stylesheet else "")
            + AMINATE_COMBO_AFFORDANCE_STYLESHEET
        )
        try:
            drop_zone = AminateComboDropZone(combo)
            combo._aminate_combo_drop_zone = drop_zone
            drop_zone.show()
            drop_zone.raise_()
        except Exception:
            # Keep the stylesheet fallback if a host-specific Qt child cannot
            # be created. The native popup and selection still work.
            pass
        combo.setToolTip(combo.toolTip() or "Choose an option. Click the arrow to open the list.")
        combo.update()
        return True


    def _apply_aminate_combo_affordances(root):
        """Style every combo currently owned by an Aminate widget tree."""
        if not root or not QtWidgets:
            return 0
        combos = []
        if isinstance(root, QtWidgets.QComboBox):
            combos.append(root)
        try:
            combos.extend(root.findChildren(QtWidgets.QComboBox))
        except Exception:
            return 0
        styled = 0
        for combo in combos:
            if _style_aminate_combo_box(combo):
                styled += 1
        return styled


    class AminateWindow(_WindowBase):
        def __init__(self, controller, parent=None, initial_tab=0):
            super(AminateWindow, self).__init__(parent)
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
            _apply_aminate_combo_affordances(self)
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
            return super(AminateWindow, self).eventFilter(obj, event)

        def resizeEvent(self, event):
            try:
                super(AminateWindow, self).resizeEvent(event)
            except TypeError:
                QtWidgets.QDialog.resizeEvent(self, event)
            self._update_responsive_navigation()

        def _update_responsive_navigation(self):
            tab_widget = getattr(self, "tab_widget", None)
            if tab_widget is None:
                return
            width = max(0, int(self.width()))
            compact = width < 720
            tab_bar = tab_widget.tabBar()
            if tab_bar is not None:
                # Twenty-three web-style tabs compete with the work itself.
                # The searchable tool picker is the single navigation surface
                # at every width; QTabWidget remains only as the page stack.
                tab_bar.setVisible(False)
            navigation_label = getattr(self, "tool_navigation_label", None)
            if navigation_label is not None:
                navigation_label.setVisible(width >= 400)
            self.setProperty("aminateCompactNavigation", bool(compact))

        def _make_scroll_tab(self):
            page = QtWidgets.QWidget()
            page.setObjectName("aminateTabPage")
            page.setProperty("aminateTabPage", True)
            if hasattr(page, "setSizePolicy"):
                page.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            scroll = QtWidgets.QScrollArea()
            scroll.setObjectName("aminateTabScroll")
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
            # Keep the large shared QSS readable, then append the small set of
            # token-backed semantic role rules.  This makes the token map the
            # source of truth for category titles and action/status roles.
            self.setStyleSheet(AMINATE_WINDOW_STYLESHEET + _render_aminate_semantic_stylesheet())
            main_layout = QtWidgets.QVBoxLayout(self)
            _set_no_size_constraint(main_layout)
            main_layout.setContentsMargins(6, 6, 6, 5)
            main_layout.setSpacing(6)
            self.tool_navigation_widget = QtWidgets.QWidget()
            self.tool_navigation_widget.setObjectName("aminateToolNavigation")
            tool_navigation_layout = QtWidgets.QHBoxLayout(self.tool_navigation_widget)
            tool_navigation_layout.setContentsMargins(5, 4, 5, 4)
            tool_navigation_layout.setSpacing(5)
            self.tool_navigation_label = QtWidgets.QLabel("Tool")
            self.tool_navigation_label.setObjectName("aminateToolNavigationLabel")
            tool_navigation_layout.addWidget(self.tool_navigation_label)
            self.tool_picker_combo = AminateToolPickerCombo()
            self.tool_picker_combo.setObjectName("aminateToolPicker")
            self.tool_picker_combo.setEditable(False)
            self.tool_picker_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.tool_picker_combo.setMinimumContentsLength(12)
            self.tool_picker_combo.setMinimumWidth(0)
            self.tool_picker_combo.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.tool_picker_combo.setAccessibleName("Jump to Aminate tool")
            self.tool_picker_combo.setToolTip("Choose any Aminate tool directly. Use the arrow keys or type a tool name.")
            tool_navigation_layout.addWidget(self.tool_picker_combo, 1)
            main_layout.addWidget(self.tool_navigation_widget)
            self.tab_widget = QtWidgets.QTabWidget()
            self.tab_widget.setObjectName("aminateTabWidget")
            _allow_tiny_shell_widget(self.tab_widget)
            self.tab_widget.setUsesScrollButtons(True)
            self.tab_widget.setMovable(False)
            self.tab_widget.setElideMode(_qt_flag("TextElideMode", "ElideRight", QtCore.Qt.ElideRight))
            self._configure_main_tab_bar()
            main_layout.addWidget(self.tab_widget, 1)
            self.embedded_toolkit_bar = None
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
            # Every page keeps its stable manifest tool id for icons,
            # navigation, and compatibility. Themes no longer colour-code the
            # whole active tool.
            for tab_index in range(self.tab_widget.count()):
                page = self.tab_widget.widget(tab_index)
                tool_id = maya_aminate_theme.tool_id_for_tab(self.tab_widget.tabText(tab_index))
                if page is not None and tool_id:
                    page.setProperty("aminateToolId", tool_id)
            for tab_index in range(self.tab_widget.count()):
                self.tool_picker_combo.addItem(self.tab_widget.tabText(tab_index), tab_index)
            self.tool_picker_combo.currentIndexChanged.connect(self._jump_to_tool_picker_index)
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
            self.tab_widget.currentChanged.connect(self._sync_tool_picker)
            self.tab_widget.currentChanged.connect(self._sync_bottom_toolbar_selection)
            self.tab_widget.currentChanged.connect(self._ensure_tab_content)
            self._sync_tool_picker(self.tab_widget.currentIndex())
            self._sync_bottom_toolbar_selection(self.tab_widget.currentIndex())
            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setObjectName("aminateStatusLabel")
            _allow_tiny_shell_widget(self.status_label)
            self.status_label.setWordWrap(True)
            self.status_label.hide()
            main_layout.addWidget(self.status_label)
            footer_layout = QtWidgets.QHBoxLayout()
            _set_no_size_constraint(footer_layout)
            footer_layout.setSpacing(5)
            self.brand_label = QtWidgets.QLabel(
                'Made by Amir · <a href="{0}" style="color:#F1F1F1; text-decoration:underline; font-weight:600;">'
                "followamir.com ↗</a>".format(FOLLOW_AMIR_URL)
            )
            self.brand_label.setObjectName("aminateBrandLabel")
            _allow_tiny_shell_widget(self.brand_label)
            self.brand_label.setTextFormat(_qt_flag("TextFormat", "RichText", getattr(QtCore.Qt, "RichText", None)))
            link_mouse = _qt_flag(
                "TextInteractionFlag",
                "LinksAccessibleByMouse",
                getattr(QtCore.Qt, "LinksAccessibleByMouse", None),
            )
            link_keyboard = _qt_flag(
                "TextInteractionFlag",
                "LinksAccessibleByKeyboard",
                getattr(QtCore.Qt, "LinksAccessibleByKeyboard", None),
            )
            if link_mouse is not None and link_keyboard is not None:
                self.brand_label.setTextInteractionFlags(link_mouse | link_keyboard)
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            self.brand_label.setWordWrap(False)
            self.brand_label.setAccessibleName("Made by Amir. Open followamir.com.")
            self.brand_label.setToolTip("Open followamir.com in your web browser.")
            self.brand_label.setCursor(_qt_flag("CursorShape", "PointingHandCursor", None))
            self.brand_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            footer_layout.addWidget(self.brand_label, 1)
            self.version_label = QtWidgets.QLabel(VERSION_LABEL)
            self.version_label.setObjectName("aminateVersionLabel")
            self.version_label.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
            self.version_label.setToolTip("Current public student release label.")
            footer_layout.addWidget(self.version_label)
            self.donate_button = QtWidgets.QToolButton()
            self.donate_button.setObjectName("aminateSupportButton")
            self.donate_button.setText("Donate")
            self.donate_button.setAccessibleName("Donate to support the free Aminate tool")
            self.donate_button.setToolTip("Aminate is free. Open Amir's optional PayPal donation link.")
            self.donate_button.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
            _style_donate_button(self.donate_button)
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)
            self.apply_aminate_theme(maya_aminate_theme.load_theme_name())
            self._update_responsive_navigation()

        def apply_aminate_theme(self, theme_name=None):
            """Apply the selected neutral workbench theme immediately."""
            name = theme_name or self.property("aminateTheme") or maya_aminate_theme.load_theme_name()
            active_tool_id = ""
            if getattr(self, "tab_widget", None) is not None:
                current_index = self.tab_widget.currentIndex()
                if current_index >= 0:
                    active_tool_id = maya_aminate_theme.tool_id_for_tab(self.tab_widget.tabText(current_index))
            try:
                self.setProperty("aminateActiveTool", active_tool_id)
                navigation = getattr(self, "tool_navigation_widget", None)
                if navigation is not None:
                    navigation.setProperty("aminateActiveTool", active_tool_id)
                tab_bar = self.tab_widget.tabBar() if getattr(self, "tab_widget", None) is not None else None
                if tab_bar is not None:
                    tab_bar.setProperty("aminateActiveTool", active_tool_id)
                return maya_aminate_theme.apply_theme_to_window(
                    self,
                    name,
                    active_tool_id=active_tool_id,
                    active_accent=maya_aminate_theme.accent_map().get(active_tool_id),
                )
            except Exception:
                return name

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
                _apply_aminate_combo_affordances(self.tab_widget.widget(index))
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
                tab_bar.setUsesScrollButtons(True)
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

        def _jump_to_tool_picker_index(self, picker_index):
            if not self.tab_widget or not self.tool_picker_combo:
                return
            tab_index = self.tool_picker_combo.itemData(int(picker_index))
            try:
                tab_index = int(tab_index)
            except (TypeError, ValueError):
                tab_index = int(picker_index)
            if 0 <= tab_index < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(tab_index)

        def _sync_tool_picker(self, tab_index):
            if not getattr(self, "tool_picker_combo", None):
                return
            picker_index = self.tool_picker_combo.findData(int(tab_index))
            if picker_index < 0:
                return
            self.tool_picker_combo.blockSignals(True)
            self.tool_picker_combo.setCurrentIndex(picker_index)
            self.tool_picker_combo.blockSignals(False)

        def _sync_bottom_toolbar_selection(self, tab_index):
            if not self.tab_widget or tab_index < 0 or tab_index >= self.tab_widget.count():
                return
            tab_label = self.tab_widget.tabText(tab_index)
            self.apply_aminate_theme()
            tab_alias_by_label = {
                TAB_GUIDE: "quick_start",
                TAB_STUDENT_CORE: "toolkit_bar",
                TAB_TIMING: "scene_helpers",
                TAB_REFERENCE_MANAGER: "reference_manager",
                TAB_PARENTING: "dynamic_parenting",
                TAB_CONTACT_HOLD: "hand_foot_hold",
                TAB_SURFACE_CONTACT: "surface_contact",
                TAB_PIVOT: "dynamic_pivot",
                TAB_IKFK: "ikfk",
                TAB_FACE_RETARGET: "controls_retargeter",
                TAB_CONTROL_PICKER: "control_picker",
                TAB_ANIMATORS_PENCIL: "animators_pencil",
                TAB_ANIMATION_ASSISTANT: "animation_assistant",
                TAB_ANIMATION_STYLING: "animation_styling",
                TAB_HISTORY_TIMELINE: "history_timeline",
                TAB_ONION: "onion_skin",
                TAB_ROTATION: "rotation_doctor",
                TAB_SKIN: "skinning_cleanup",
                TAB_RIG_SCALE: "rig_scale",
                TAB_VIDEO: "video_reference",
                TAB_TIMELINE: "timeline_notes",
                TAB_SMEAR_FRAMES: "smear_frames",
                TAB_CUSTOMIZATION: "customization",
            }
            maya_timing_tools.sync_workflow_toolbar_selection(tab_alias_by_label.get(tab_label, self._tab_key(tab_label)))

        def _build_tab_intro(self, tab_name):
            frame = QtWidgets.QFrame()
            frame.setFrameShape(QtWidgets.QFrame.NoFrame)
            frame.setObjectName("aminateTabIntro")
            tool_id = maya_aminate_theme.tool_id_for_tab(tab_name)
            if tool_id:
                frame.setProperty("aminateToolId", tool_id)
            frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
            inner = QtWidgets.QVBoxLayout(frame)
            inner.setContentsMargins(2, 2, 2, 3)
            inner.setSpacing(3)
            title_row = QtWidgets.QHBoxLayout()
            title_row.setSpacing(6)
            title = QtWidgets.QLabel(tab_name)
            title.setObjectName("aminateIntroTitle")
            if tool_id:
                title.setProperty("aminateToolId", tool_id)
            category = AMINATE_TAB_CATEGORY.get(tab_name, "primary")
            if category not in AMINATE_CATEGORY_TOKEN_KEYS:
                category = "primary"
            title.setProperty("aminateCategory", category)
            toggle = QtWidgets.QToolButton()
            toggle.setObjectName("aminateIntroToggle")
            toggle.setCheckable(True)
            toggle.setChecked(False)
            toggle.setText("Help")
            toggle.setArrowType(_qt_flag("ArrowType", "RightArrow", QtCore.Qt.RightArrow))
            toggle.setToolButtonStyle(_qt_flag("ToolButtonStyle", "ToolButtonTextBesideIcon", QtCore.Qt.ToolButtonTextBesideIcon))
            toggle.setAccessibleName("Show or hide help for {0}".format(tab_name))
            toggle.setToolTip("Show a short explanation and the three-step workflow.")
            title_row.addWidget(title, 1)
            title_row.addWidget(toggle)
            inner.addLayout(title_row)

            help_panel = QtWidgets.QWidget()
            help_panel.setObjectName("aminateIntroHelp")
            help_panel.setVisible(False)
            help_layout = QtWidgets.QVBoxLayout(help_panel)
            help_layout.setContentsMargins(8, 6, 8, 6)
            help_layout.setSpacing(5)
            body = QtWidgets.QLabel(TAB_HELP_TEXT.get(tab_name, ""))
            body.setWordWrap(True)
            body.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            help_layout.addWidget(body)

            coach = QtWidgets.QFrame()
            coach.setObjectName("aminateCoach")
            coach.setFrameShape(QtWidgets.QFrame.NoFrame)
            coach_layout = QtWidgets.QVBoxLayout(coach)
            coach_layout.setContentsMargins(0, 2, 0, 0)
            coach_layout.setSpacing(3)
            coach_title = QtWidgets.QLabel("Do this in three small steps")
            coach_title.setObjectName("aminateCoachTitle")
            coach_layout.addWidget(coach_title)
            for step_number, step_text in enumerate(TAB_WORKFLOW_STEPS.get(tab_name, ()), 1):
                step = QtWidgets.QLabel("{0}. {1}".format(step_number, step_text))
                step.setObjectName("aminateCoachStep")
                step.setWordWrap(True)
                step.setAccessibleName("Step {0}: {1}".format(step_number, step_text))
                coach_layout.addWidget(step)
            help_layout.addWidget(coach)

            tutorial_button = QtWidgets.QPushButton(
                "Open tutorials and FAQ" if tab_name == TAB_GUIDE else "Open full tutorial"
            )
            tutorial_button.setObjectName("aminateTutorialButton")
            tutorial_button.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
            tutorial_button.setToolTip("Open the offline Aminate tutorial at this tool.")
            tutorial_button.clicked.connect(
                lambda _checked=False, name=tab_name: self._open_tutorial_section(name)
            )
            help_layout.addWidget(tutorial_button)
            help_panel.setVisible(False)
            inner.addWidget(help_panel)
            toggle.toggled.connect(
                lambda visible, panel=help_panel, button=toggle: self._toggle_tab_intro_help(
                    visible,
                    panel,
                    button,
                )
            )
            self.tab_intro_labels[tab_name] = body
            return frame

        @staticmethod
        def _toggle_tab_intro_help(visible, label, button):
            label.setVisible(bool(visible))
            button.setText("Hide help" if visible else "Help")
            button.setArrowType(
                _qt_flag("ArrowType", "DownArrow", QtCore.Qt.DownArrow)
                if visible
                else _qt_flag("ArrowType", "RightArrow", QtCore.Qt.RightArrow)
            )
            button.setToolTip(
                "Hide this explanation when you need more working space."
                if visible
                else "Show the plain-language explanation for this tool."
            )

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
            self._apply_embedded_dark_surface(panel)
            self._apply_embedded_action_hierarchy(panel)
            panel.setMinimumWidth(0)
            panel.setMinimumHeight(0)
            if hasattr(panel, "setSizePolicy"):
                panel.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            try:
                panel.show()
            except Exception:
                pass
            return panel

        @staticmethod
        def _apply_embedded_dark_surface(panel):
            widgets = [panel]
            try:
                palette = QtGui.QPalette(panel.palette())
                role_colors = (
                    (QtGui.QPalette.Window, "#373737"),
                    (QtGui.QPalette.WindowText, "#F1F1F1"),
                    (QtGui.QPalette.Base, "#303030"),
                    (QtGui.QPalette.AlternateBase, "#3A3A3A"),
                    (QtGui.QPalette.ToolTipBase, "#414141"),
                    (QtGui.QPalette.ToolTipText, "#F1F1F1"),
                    (QtGui.QPalette.Text, "#F1F1F1"),
                    (QtGui.QPalette.Button, "#505050"),
                    (QtGui.QPalette.ButtonText, "#F1F1F1"),
                    (QtGui.QPalette.Highlight, "#566A7A"),
                    (QtGui.QPalette.HighlightedText, "#FFFFFF"),
                    (QtGui.QPalette.Link, "#C7D7E4"),
                )
                for role, color in role_colors:
                    palette.setColor(role, QtGui.QColor(color))
                widgets.extend(panel.findChildren(QtWidgets.QWidget))
                for widget in widgets:
                    widget.setPalette(palette)
                for scroll_area in panel.findChildren(QtWidgets.QAbstractScrollArea):
                    viewport = scroll_area.viewport()
                    if viewport is not None:
                        viewport.setPalette(palette)
                        viewport.setAutoFillBackground(True)
            except Exception:
                pass
            try:
                style_roots = [panel]
                style_roots.extend(
                    widget
                    for widget in widgets[1:]
                    if widget.styleSheet().strip()
                    and widget.findChildren(QtWidgets.QWidget)
                )
                for style_root in style_roots:
                    style_root.setProperty("aminateEmbeddedPanel", True)
                    existing = style_root.styleSheet().strip()
                    style_root.setStyleSheet(
                        (existing + "\n" if existing else "")
                        + AMINATE_EMBEDDED_PANEL_STYLESHEET
                    )
                    style_root.style().unpolish(style_root)
                    style_root.style().polish(style_root)
            except Exception:
                pass

        @staticmethod
        def _apply_embedded_action_hierarchy(panel):
            try:
                buttons = panel.findChildren(QtWidgets.QPushButton)
            except Exception:
                return
            for button in buttons:
                label = str(button.text() or "").strip()
                if label in AMINATE_PRIMARY_ACTION_LABELS:
                    button.setProperty("aminateRole", "primary")
                elif label in AMINATE_DANGER_ACTION_LABELS:
                    button.setProperty("aminateRole", "danger")
                else:
                    continue
                try:
                    button.style().unpolish(button)
                    button.style().polish(button)
                except Exception:
                    pass

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
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            layout.addWidget(self._build_tab_intro(TAB_PIVOT))
            summary = QtWidgets.QLabel("Pick controls, place one temporary pivot, choose the range, then turn the controls.")
            summary.setWordWrap(True)
            layout.addWidget(summary)
            pivot_group = QtWidgets.QGroupBox("Pivot Setup")
            pivot_form = QtWidgets.QFormLayout(pivot_group)
            self.pivot_mode_combo = QtWidgets.QComboBox()
            self.pivot_mode_combo.addItems(list(PIVOT_MODES.keys()))
            self.pivot_mode_combo.setToolTip("Choose where the turn point starts before you move it by hand.")
            pivot_form.addRow("Start Pivot At", self.pivot_mode_combo)
            layout.addWidget(pivot_group)
            buttons = QtWidgets.QVBoxLayout()
            self.create_pivot_button = QtWidgets.QPushButton("Create & Move Pivot")
            self.create_pivot_button.setProperty("aminateRole", "primary")
            self.create_pivot_button.setToolTip("Make a temporary pivot for the selected objects, then select it for moving.")
            self.edit_pivot_button = QtWidgets.QPushButton("Move Pivot")
            self.edit_pivot_button.setToolTip("Select the pivot marker so you can move it where you want.")
            self.apply_pivot_button = QtWidgets.QPushButton("Turn From Pivot")
            self.apply_pivot_button.setProperty("aminateRole", "primary")
            self.apply_pivot_button.setToolTip(
                "Turn every whole frame in the highlighted Time Slider range; with no highlight, turn only the current frame."
            )
            self.clear_pivot_button = QtWidgets.QPushButton("Clear Pivot")
            self.clear_pivot_button.setProperty("aminateRole", "danger")
            self.clear_pivot_button.setToolTip("Remove the temporary pivot marker.")
            buttons.addWidget(self.create_pivot_button)
            buttons.addWidget(self.edit_pivot_button)
            buttons.addWidget(self.apply_pivot_button)
            buttons.addWidget(self.clear_pivot_button)
            layout.addLayout(buttons)
            self.pivot_range_status = QtWidgets.QLabel(_pivot_range_text(_pivot_apply_times()[1]))
            self.pivot_range_status.setWordWrap(True)
            self.pivot_range_status.setProperty("aminateRole", "muted")
            layout.addWidget(self.pivot_range_status)
            self.pivot_help = QtWidgets.QLabel(
                "Highlighted range = turn on all those frames. No highlight = only the current frame. "
                "Move the same pivot and apply again for the next range. Rotate the marker to choose the turn."
            )
            self.pivot_help.setWordWrap(True)
            self.pivot_help.setProperty("aminateRole", "muted")
            layout.addWidget(self.pivot_help)
            layout.addStretch(1)
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
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            layout.addWidget(self._build_tab_intro(TAB_IKFK))
            summary = QtWidgets.QLabel("Pick one arm or leg, set it up once, then switch without a visible pop.")
            summary.setWordWrap(True)
            layout.addWidget(summary)
            saved_group = QtWidgets.QGroupBox("Saved Switch")
            saved_layout = QtWidgets.QVBoxLayout(saved_group)
            self.profile_combo = QtWidgets.QComboBox()
            self.refresh_profiles_button = QtWidgets.QPushButton("Refresh")
            self.load_profile_button = QtWidgets.QPushButton("Load")
            self.profile_combo.setToolTip("Saved switches you can reuse later.")
            self.refresh_profiles_button.setToolTip("Reload the saved switch list.")
            self.load_profile_button.setToolTip("Load the saved switch into the boxes below.")
            saved_layout.addWidget(self.profile_combo)
            saved_buttons = QtWidgets.QHBoxLayout()
            saved_buttons.addWidget(self.load_profile_button, 1)
            saved_buttons.addWidget(self.refresh_profiles_button, 1)
            saved_layout.addLayout(saved_buttons)
            layout.addWidget(saved_group)
            setup_group = QtWidgets.QGroupBox("Switch Setup")
            meta_form = QtWidgets.QFormLayout(setup_group)
            self.profile_name_line = QtWidgets.QLineEdit()
            self.rig_root_line = QtWidgets.QLineEdit()
            self.namespace_line = QtWidgets.QLineEdit()
            self.limb_type_combo = QtWidgets.QComboBox()
            self.limb_type_combo.addItems(["arm", "leg"])
            self.side_combo = QtWidgets.QComboBox()
            self.side_combo.addItems(["left", "right"])
            self.switch_attr_line = QtWidgets.QLineEdit()
            self.profile_name_line.setToolTip("A name so you can save and load this switch later.")
            self.rig_root_line.setToolTip("The main top object for this rig. This is usually filled in for you.")
            self.namespace_line.setToolTip("Only needed if the rig names have extra tags and auto-find needs help.")
            self.switch_attr_line.setToolTip("The setting that changes the arm or leg between IK and FK.")
            meta_form.addRow("Switch Name", self.profile_name_line)
            meta_form.addRow("Main Rig", self.rig_root_line)
            meta_form.addRow("Limb Type", self.limb_type_combo)
            meta_form.addRow("Side", self.side_combo)
            meta_form.addRow("Name Tag", self.namespace_line)
            meta_form.addRow("Switch Setting", self.switch_attr_line)
            layout.addWidget(setup_group)

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
            layout.addWidget(fk_group)
            layout.addWidget(ik_group)

            details_group = QtWidgets.QGroupBox("Advanced Matching")
            details_form = QtWidgets.QFormLayout(details_group)
            self.extra_controls_line = QtWidgets.QLineEdit()
            self.extra_controls_line.setPlaceholderText("optional extra controls to key")
            self.extra_controls_line.setToolTip("Any extra controls that should also get keys when you switch.")
            self.match_nodes_line = QtWidgets.QLineEdit()
            self.match_nodes_line.setPlaceholderText("match_shoulder, match_elbow, match_wrist")
            self.match_nodes_line.setToolTip("The points the FK controls should copy when you switch.")
            self.ik_match_node_line = QtWidgets.QLineEdit()
            self.ik_match_node_line.setPlaceholderText("optional IK hand/foot match control")
            self.ik_match_node_line.setToolTip("Optional rig-provided point whose full world pose the IK hand or foot control should copy.")
            details_form.addRow("Match Controls", self.match_nodes_line)
            details_form.addRow("IK Match Control", self.ik_match_node_line)
            details_form.addRow("Extra Controls To Key", self.extra_controls_line)
            layout.addWidget(details_group)
            buttons = QtWidgets.QVBoxLayout()
            self.detect_profile_button = QtWidgets.QPushButton("Set Up From Selection")
            self.detect_profile_button.setProperty("aminateRole", "primary")
            self.detect_profile_button.setToolTip("Detect the selected arm or leg. Complete setups are saved automatically.")
            self.save_profile_button = QtWidgets.QPushButton("Save Switch")
            self.save_profile_button.setToolTip("Save the current boxes as a switch you can load later.")
            self.switch_fk_to_ik_button = QtWidgets.QPushButton("Switch FK -> IK")
            self.switch_fk_to_ik_button.setProperty("aminateRole", "primary")
            self.switch_fk_to_ik_button.setToolTip("Match the IK controls to the current FK pose and switch on this frame.")
            self.switch_ik_to_fk_button = QtWidgets.QPushButton("Switch IK -> FK")
            self.switch_ik_to_fk_button.setProperty("aminateRole", "primary")
            self.switch_ik_to_fk_button.setToolTip("Match the FK controls to the current IK pose and switch on this frame.")
            buttons.addWidget(self.detect_profile_button)
            buttons.addWidget(self.save_profile_button)
            buttons.addWidget(self.switch_fk_to_ik_button)
            buttons.addWidget(self.switch_ik_to_fk_button)
            layout.addLayout(buttons)
            self.ikfk_help = QtWidgets.QLabel("Select controls, then use Set Up From Selection.")
            self.ikfk_help.setWordWrap(True)
            self.ikfk_help.setProperty("aminateRole", "muted")
            layout.addWidget(self.ikfk_help)
            layout.addStretch(1)
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
            face_hint = QtWidgets.QLabel("Fill paired rows: source control on the left, target control on the right. A new empty row appears automatically and empty rows are ignored. Auto Map By Name pairs matching names quickly. Retarget All Controls matches the source starting pose and copies only the source's original key times.")
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
                video_reference_controller=self.controller.video_reference_controller,
                reference_package_controller=self.controller.reference_manager_controller,
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
            self.quick_start_search = QtWidgets.QLineEdit()
            self.quick_start_search.setClearButtonEnabled(True)
            self.quick_start_search.setPlaceholderText("What do you want to do? Try: draw, skin, switch, notes")
            self.quick_start_search.setAccessibleName("Search Aminate tools")
            layout.addWidget(self.quick_start_search)

            self.quick_start_count_label = QtWidgets.QLabel()
            self.quick_start_count_label.setObjectName("aminateQuickStartCount")
            self.quick_start_count_label.setProperty("aminateRole", "muted")
            layout.addWidget(self.quick_start_count_label)

            self.quick_start_tool_list = QtWidgets.QListWidget()
            self.quick_start_tool_list.setObjectName("aminateQuickStartToolList")
            self.quick_start_tool_list.setAlternatingRowColors(True)
            self.quick_start_tool_list.setMinimumHeight(200)
            self.quick_start_tool_list.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding,
            )
            role = _qt_flag("ItemDataRole", "UserRole", 32)
            for tab_index in range(1, self.tab_widget.count()):
                tab_name = self.tab_widget.tabText(tab_index)
                item = QtWidgets.QListWidgetItem(tab_name)
                item.setData(role, tab_index)
                item.setToolTip(TAB_HELP_TEXT.get(tab_name, ""))
                self.quick_start_tool_list.addItem(item)
            layout.addWidget(self.quick_start_tool_list, 1)

            self.quick_start_description = QtWidgets.QLabel()
            self.quick_start_description.setObjectName("aminateQuickStartDescription")
            self.quick_start_description.setWordWrap(True)
            self.quick_start_description.setMinimumHeight(64)
            self.quick_start_description.setAlignment(
                _qt_flag("AlignmentFlag", "AlignTop", QtCore.Qt.AlignTop)
                | _qt_flag("AlignmentFlag", "AlignLeft", QtCore.Qt.AlignLeft)
            )
            layout.addWidget(self.quick_start_description)

            self.quick_start_open_button = QtWidgets.QPushButton("Open Selected Tool")
            self.quick_start_open_button.setProperty("aminateRole", "primary")
            self.quick_start_open_button.setToolTip("Jump straight to the selected Aminate tool.")
            layout.addWidget(self.quick_start_open_button)

            self.quick_start_search.textChanged.connect(self._filter_quick_start_tools)
            self.quick_start_tool_list.currentItemChanged.connect(self._refresh_quick_start_description)
            self.quick_start_tool_list.itemDoubleClicked.connect(self._open_quick_start_tool)
            self.quick_start_open_button.clicked.connect(self._open_quick_start_tool)
            if self.quick_start_tool_list.count():
                self.quick_start_tool_list.setCurrentRow(0)
            self._filter_quick_start_tools("")
            return

        def _filter_quick_start_tools(self, query):
            if not hasattr(self, "quick_start_tool_list"):
                return
            query = str(query or "").strip().lower()
            first_visible = None
            visible_count = 0
            role = _qt_flag("ItemDataRole", "UserRole", 32)
            for row in range(self.quick_start_tool_list.count()):
                item = self.quick_start_tool_list.item(row)
                try:
                    tab_index = int(item.data(role))
                except (TypeError, ValueError):
                    tab_index = -1
                description = TAB_HELP_TEXT.get(self.tab_widget.tabText(tab_index), "") if tab_index >= 0 else ""
                visible = not query or query in item.text().lower() or query in description.lower()
                item.setHidden(not visible)
                if visible and first_visible is None:
                    first_visible = item
                if visible:
                    visible_count += 1
            current = self.quick_start_tool_list.currentItem()
            if current is None or current.isHidden():
                self.quick_start_tool_list.setCurrentItem(first_visible)
            self.quick_start_open_button.setEnabled(first_visible is not None)
            if hasattr(self, "quick_start_count_label"):
                self.quick_start_count_label.setText(
                    "{0} matching tool{1}".format(visible_count, "" if visible_count == 1 else "s")
                )
            if first_visible is None:
                self.quick_start_description.setText("No matching tool. Try a shorter task word.")

        def _refresh_quick_start_description(self, current, _previous=None):
            if not hasattr(self, "quick_start_description"):
                return
            if current is None:
                self.quick_start_description.setText("Choose a tool to see what it does.")
                return
            role = _qt_flag("ItemDataRole", "UserRole", 32)
            try:
                tab_index = int(current.data(role))
            except (TypeError, ValueError):
                tab_index = -1
            tab_name = self.tab_widget.tabText(tab_index) if 0 <= tab_index < self.tab_widget.count() else current.text()
            self.quick_start_description.setText(TAB_HELP_TEXT.get(tab_name, "Choose this tool to continue."))

        def _open_quick_start_tool(self, item=None):
            if not hasattr(self, "quick_start_tool_list"):
                return
            current = item if isinstance(item, QtWidgets.QListWidgetItem) else self.quick_start_tool_list.currentItem()
            if current is None:
                self._set_status("Choose a tool first.", False)
                return
            role = _qt_flag("ItemDataRole", "UserRole", 32)
            try:
                tab_index = int(current.data(role))
            except (TypeError, ValueError):
                tab_index = -1
            if 0 <= tab_index < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(tab_index)
                self._set_status("Opened {0}.".format(self.tab_widget.tabText(tab_index)), True)

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
                "This tab mirrors the fixed Toolkit Bar at the bottom of Maya.\n\n"
                "- The History strip, Animation Layer controls, timing buttons, workflow icons, package zip, and Game Animation Mode button are all shown here.\n"
                "- Changes made from this tab use the same controller as the fixed bar, so Game Animation Mode and animation layer state stay synced.\n"
                "- The bottom bar is pinned to Maya, cannot float or drag, and scrolls horizontally on narrow screens."
            )
            help_box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            layout.addWidget(help_box, 1)
            open_button = QtWidgets.QPushButton("Show Fixed Bottom Toolkit Bar")
            open_button.setToolTip("Show the non-draggable Toolkit Bar at the bottom of Maya.")
            open_button.clicked.connect(self._open_student_core_toolbar)
            layout.addWidget(open_button)
            layout.addStretch(1)

        def _open_student_core_toolbar(self):
            try:
                self.embedded_toolkit_bar = maya_timing_tools.launch_student_timeline_button_bar(
                    dock=True,
                    controller=self.controller.get_timing_controller(),
                    status_callback=self._set_status,
                )
                self._set_status("Toolkit Bar is pinned to the bottom of Maya.", True)
            except Exception as exc:
                self._set_status("Could not show fixed bottom Toolkit Bar: {0}".format(exc), False)

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
            self.reference_manager_panel = self._embed_tool_panel(
                maya_reference_manager.ReferenceManagerPanel(
                    controller=self.controller.reference_manager_controller,
                    status_callback=self._set_status,
                    parent=self.reference_manager_page,
                ),
                self.reference_manager_page,
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
                "student": "toolkit_bar",
                "student_core": "toolkit_bar",
                "toolkit": "toolkit_bar",
                "toolkit_bar": "toolkit_bar",
                "core": "toolkit_bar",
                "temp_buttons": "toolkit_bar",
                "timeline_buttons": "toolkit_bar",
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
            self.status_label.setVisible(bool(str(message or "").strip()))
            self.status_label.setProperty("aminateRole", "success" if success else "error")
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor(AMINATE_UI_TOKENS["success" if success else "error"]))
            self.status_label.setPalette(palette)
            style = self.status_label.style()
            if style:
                style.unpolish(self.status_label)
                style.polish(self.status_label)

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
                "ik_match_node": self.ik_match_node_line.text(),
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
            self.ik_match_node_line.setText(profile.get("ik_match_node", ""))

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
            if success:
                selected, select_message = self.controller.edit_pivot_position()
                if selected:
                    message = "{0} {1}".format(message, select_message)
            self.pivot_range_status.setText(_pivot_range_text(_pivot_apply_times()[1]))
            self._set_status(message, success)

        def _edit_pivot(self):
            success, message = self.controller.edit_pivot_position()
            self.pivot_range_status.setText(_pivot_range_text(_pivot_apply_times()[1]))
            self._set_status(message, success)

        def _apply_pivot(self):
            success, message = self.controller.apply_pivot_rotation()
            self.pivot_range_status.setText(_pivot_range_text(_pivot_apply_times()[1]))
            self._set_status(message, success)

        def _clear_pivot(self):
            success, message = self.controller.clear_pivot()
            self.pivot_range_status.setText(_pivot_range_text(_pivot_apply_times()[1]))
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
            lines = ["Setup detected from current selection."]
            if issues:
                lines.extend("- " + issue for issue in issues)
                lines.append("Fix highlighted details, then use Save Switch.")
                self.ikfk_help.setText("\n".join(lines))
                self._set_status("Setup found with details to check before saving.", False)
                return
            success, message = self.controller.save_profile(self._profile_fields())
            self._populate_profile_names()
            if success:
                lines.append("Complete setup saved. Switch buttons are ready.")
            else:
                lines.append(message)
            self.ikfk_help.setText("\n".join(lines))
            self._set_status(message, success)

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
                    widget.hide()
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
            elif _open_external_url(TUTORIAL_RELEASE_URL):
                self._set_status("Opened the separate offline tutorial download.", True)
            else:
                self._set_status("Could not open Aminate tutorials: {0}".format(docs_path), False)

        def _open_tutorial_section(self, tab_name):
            docs_path = _tutorials_index_path()
            section_id = TAB_TUTORIAL_SECTION_IDS.get(tab_name, "")
            if _open_local_file_at_fragment(docs_path, section_id):
                self._set_status("Opened the {0} tutorial.".format(tab_name), True)
            elif _open_external_url(TUTORIAL_RELEASE_URL):
                self._set_status("Opened the separate offline tutorial download.", True)
            else:
                self._set_status("Could not open Aminate tutorials: {0}".format(docs_path), False)

        def hideEvent(self, event):
            try:
                super(AminateWindow, self).hideEvent(event)
            except TypeError:
                QtWidgets.QDialog.hideEvent(self, event)

        def showEvent(self, event):
            self._toolbar_extras_hidden_for_close = False
            try:
                super(AminateWindow, self).showEvent(event)
            except TypeError:
                QtWidgets.QDialog.showEvent(self, event)

        def setVisible(self, visible):
            if not bool(visible) and _workspace_control_exists(WORKSPACE_CONTROL_NAME):
                return
            if not bool(visible):
                pencil_panel = getattr(self, "animators_pencil_panel", None)
                suspend_runtime = getattr(pencil_panel, "_deactivate_runtime_input", None)
                if suspend_runtime:
                    try:
                        suspend_runtime()
                    except Exception:
                        pass
                self._hide_toolbar_extras_if_needed()
            try:
                super(AminateWindow, self).setVisible(visible)
            except TypeError:
                QtWidgets.QDialog.setVisible(self, visible)

        def close(self):
            # Retained dock stays visible. Re-launch reuses this exact window.
            return False

        def closeEvent(self, event):
            # Never let Maya destroy this live dock wrapper from its native close event.
            event.ignore()

def _workspace_control_exists(name=WORKSPACE_CONTROL_NAME):
    return bool(MAYA_AVAILABLE and cmds and name and cmds.workspaceControl(name, exists=True))


def _normalize_main_dock_request(dock):
    # Compatibility-only argument: old shelf buttons may still pass False,
    # but the main Aminate panel has no supported floating mode.
    return True


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


def _show_window_dockable(window, area="right"):
    if not window:
        return False, "No Aminate window is available to show."
    try:
        window.show(dockable=True, floating=False, area=area)
        _process_qt_events()
    except Exception as exc:
        return False, "Could not show the Aminate as a dockable Maya panel: {0}".format(exc)
    if not _workspace_control_exists(WORKSPACE_CONTROL_NAME):
        return False, "The Maya workspace control did not open."
    try:
        # Shelf-like workspace controls do not expose Maya's crash-prone close affordance.
        cmds.workspaceControl(
            WORKSPACE_CONTROL_NAME,
            edit=True,
            retain=True,
            actLikeMayaUIElement=True,
        )
    except Exception:
        pass
    try:
        workspace_floating = bool(cmds.workspaceControl(WORKSPACE_CONTROL_NAME, query=True, floating=True))
    except Exception as exc:
        return False, "Could not verify the Maya workspace control state: {0}".format(exc)
    if workspace_floating:
        try:
            window.setVisible(False)
        except Exception:
            pass
        return False, "Maya kept the Aminate floating instead of docking them."
    return True, "Opened the Aminate through Maya's dockable workspace control."
def _size_workspace_control(name=WORKSPACE_CONTROL_NAME):
    if not _workspace_control_exists(name):
        return
    for flag in ("minimumWidth", "initialWidth", "width", "resizeWidth"):
        try:
            cmds.workspaceControl(name, edit=True, **{flag: DOCKED_WORKFLOW_MIN_WIDTH})
        except Exception:
            pass
    try:
        cmds.workspaceControl(name, edit=True, visible=True)
    except Exception:
        pass
    _process_qt_events()


def _shelf_button_command(repo_path):
    return (
        "import sys\n"
        "repo_path = r\"{0}\"\n"
        "while repo_path in sys.path:\n"
        "    sys.path.remove(repo_path)\n"
        "sys.path.insert(0, repo_path)\n"
        "import aminate\n"
        "aminate.launch_aminate(dock=True)\n"
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
        style=SHELF_BUTTON_STYLE,
        width=SHELF_BUTTON_WIDTH,
        height=SHELF_BUTTON_HEIGHT,
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
    # Old saved shelf buttons and old verifiers passed dock=False. Keep the
    # argument for compatibility, but permanently normalize the main panel to
    # the required docked mode.
    dock = _normalize_main_dock_request(dock)
    if GLOBAL_WINDOW is not None and not _qt_object_valid(GLOBAL_WINDOW):
        GLOBAL_WINDOW = None
    if GLOBAL_DOCK_HOST is not None and not _qt_object_valid(GLOBAL_DOCK_HOST):
        GLOBAL_DOCK_HOST = None
    if GLOBAL_WINDOW is not None:
        try:
            if _workspace_control_exists(WORKSPACE_CONTROL_NAME):
                workspace_floating = bool(cmds.workspaceControl(WORKSPACE_CONTROL_NAME, query=True, floating=True))
                if workspace_floating:
                    # Never redock, hide, close, or delete a live Maya 2026
                    # workspace here. Native dock-state mutation can fault
                    # Qt6Core. New launches cannot create this state; this
                    # branch only reports a retained legacy workspace.
                    _warning("Aminate is using a legacy floating workspace. Restart Maya once after updating the shelf button.")
                    GLOBAL_WINDOW.show()
                else:
                    _size_workspace_control(WORKSPACE_CONTROL_NAME)
                    GLOBAL_WINDOW.show()
            else:
                success, message = _show_window_dockable(GLOBAL_WINDOW, area="right")
                if not success:
                    _warning(message)
            if _workspace_control_exists(WORKSPACE_CONTROL_NAME):
                _size_workspace_control(WORKSPACE_CONTROL_NAME)
            _process_qt_events()
            if hasattr(GLOBAL_WINDOW, "_set_initial_tab"):
                GLOBAL_WINDOW._set_initial_tab(initial_tab)
            return GLOBAL_WINDOW
        except Exception:
            pass
    _close_existing_window()
    app = QtWidgets.QApplication.instance()
    _process_qt_events()
    GLOBAL_CONTROLLER = AminateController()
    GLOBAL_WINDOW = AminateWindow(GLOBAL_CONTROLLER, parent=_maya_main_window(), initial_tab=initial_tab)
    GLOBAL_DOCK_HOST = None
    _hide_workspace_control(LEGACY_WORKSPACE_CONTROL_NAME)
    success, _message = _show_window_dockable(GLOBAL_WINDOW, area="right")
    if success:
        _size_workspace_control(WORKSPACE_CONTROL_NAME)
    auto_open_setting = str(os.environ.get("AMINATE_AUTO_OPEN_TOOLKIT_BAR", "1") or "1").strip().lower()
    auto_open_toolkit_bar = auto_open_setting not in ("0", "false", "off", "no")
    if success and auto_open_toolkit_bar:
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
                    dock=auto_open_setting != "window",
                    controller=timing_controller,
                    status_callback=GLOBAL_WINDOW._set_status,
                )
                GLOBAL_WINDOW.embedded_toolkit_bar = bar_window
            except Exception as exc:
                _warning("Could not open Toolkit Bar: {0}".format(exc))

        try:
            QtCore.QTimer.singleShot(350, _open_default_toolkit_bar)
        except Exception:
            _open_default_toolkit_bar()
    elif not success:
        _warning(_message)
        _process_qt_events()
    _ensure_single_workflow_widget(keep_widget=GLOBAL_WINDOW)
    return GLOBAL_WINDOW


__all__ = [
    "launch_maya_dynamic_parent_pivot",
    "install_maya_dynamic_parent_pivot_shelf_button",
    "AminateController",
]
