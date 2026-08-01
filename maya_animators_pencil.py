"""
maya_animators_pencil.py

Scene-native drawing layer tool for Maya animators.
"""

from __future__ import absolute_import, division, print_function

import json
import math
import os
import time

import maya_reference_manager
import maya_video_reference_tool

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.OpenMaya as om
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
except Exception:
    from PySide2 import QtCore, QtGui, QtWidgets
    try:
        import shiboken2 as shiboken
    except Exception:
        shiboken = None


WINDOW_OBJECT_NAME = "mayaAnimatorsPencilWindow"
ROOT_GROUP_NAME = "amirAnimatorsPencil_GRP"
ROOT_MARKER_ATTR = "amirAnimatorsPencilRoot"
ROOT_STATE_ATTR = "animatorsPencilState"
LAYER_MARKER_ATTR = "amirAnimatorsPencilLayer"
LAYER_USER_VISIBILITY_ATTR = "animatorsPencilLayerUserVisible"
LAYER_OPACITY_ATTR = "animatorsPencilLayerOpacity"
CAMERA_SPACE_ANCHOR_ATTR = "animatorsPencilCameraSpaceAnchor"
CAMERA_SPACE_ANCHOR_CAMERA_ATTR = "animatorsPencilCameraSpaceAnchorCamera"
CAMERA_SPACE_ALIGNMENT_ATTR = "animatorsPencilCameraSpaceAlignmentVersion"
DRAWING_VIEW_ATTR = "animatorsPencilDrawingView"
DRAWING_VIEW_LABEL_ATTR = "animatorsPencilDrawingViewLabel"
DRAWING_VIEW_INDEX_ATTR = "animatorsPencilDrawingViewIndex"
DRAWING_VIEW_SOURCE_ATTR = "animatorsPencilDrawingViewSource"
MARK_MARKER_ATTR = "amirAnimatorsPencilMark"
# Version 2 records the camera-space parenting fix.  Version-1 scenes may
# contain layers parented absolutely below an anchor, which bakes the inverse
# camera rotation into the layer and makes stamps lie on the world grid.
LAYER_VERSION = 2
DEFAULT_ONE_FRAME_ONLY = True

FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL

DEFAULT_COLORS = {
    "Red": (1.0, 0.05, 0.05),
    "Blue": (0.15, 0.38, 1.0),
    "Green": (0.1, 0.8, 0.25),
    "Yellow": (1.0, 0.9, 0.05),
    "White": (1.0, 1.0, 1.0),
    "Black": (0.0, 0.0, 0.0),
}

LAYER_STATES = ("Animation", "Static", "Locked")
TOOL_NAMES = (
    "Pencil",
    "Brush",
    "Eraser",
    "Text",
    "Line",
    "Arrow",
    "Rectangle",
    "Ellipse",
    "Circle",
    "Oval",
    "Star",
)
STROKE_PATH_TOOLS = ("Pencil", "Brush", "Eraser")
SHAPE_TOOL_NAMES = ("Line", "Arrow", "Rectangle", "Ellipse", "Circle", "Oval", "Star")
SHAPE_LIBRARY = {
    "Circle": {"tool": "Ellipse", "points": [(math.cos((math.pi * 2.0) * (float(i) / 32.0)) * 0.72, math.sin((math.pi * 2.0) * (float(i) / 32.0)) * 0.72, 0.0) for i in range(33)]},
    "Square": {"tool": "Rectangle", "points": [(-0.7, -0.7, 0.0), (0.7, -0.7, 0.0), (0.7, 0.7, 0.0), (-0.7, 0.7, 0.0), (-0.7, -0.7, 0.0)]},
    "Triangle": {"tool": "Pencil", "points": [(0.0, 0.8, 0.0), (0.8, -0.65, 0.0), (-0.8, -0.65, 0.0), (0.0, 0.8, 0.0)]},
    "Cross": {"tool": "Pencil", "points": [(-0.8, -0.2, 0.0), (-0.2, -0.2, 0.0), (-0.2, -0.8, 0.0), (0.2, -0.8, 0.0), (0.2, -0.2, 0.0), (0.8, -0.2, 0.0), (0.8, 0.2, 0.0), (0.2, 0.2, 0.0), (0.2, 0.8, 0.0), (-0.2, 0.8, 0.0), (-0.2, 0.2, 0.0), (-0.8, 0.2, 0.0), (-0.8, -0.2, 0.0)]},
    "Star": {"tool": "Pencil", "points": [(math.cos((math.pi * 2.0) * (float(i) / 10.0) - (math.pi / 2.0)) * (0.8 if i % 2 == 0 else 0.35), math.sin((math.pi * 2.0) * (float(i) / 10.0) - (math.pi / 2.0)) * (0.8 if i % 2 == 0 else 0.35), 0.0) for i in range(11)]},
}


def _canonical_shape_tool(tool):
    """Return the drag-shape name used by the geometry helpers.

    ``Ellipse`` was the original public name.  Keep accepting it in scene
    data, shortcuts, and callers while exposing the clearer ``Oval`` label in
    the current tool list.
    """
    return "Oval" if str(tool or "") == "Ellipse" else str(tool or "")


def _shape_points_from_drag(tool, start_point, end_point, minimum_span=0.0):
    """Build deterministic viewport-space points for the simple drag shapes.

    The shape is fitted to the drag rectangle.  A Circle and Star use the
    rectangle centre; Circle uses the smaller half-span so its radii are
    equal, while Oval keeps the two independent spans.  ``minimum_span`` is
    used only by the live viewport path to keep a click from making a
    zero-area curve.
    """
    sx, sy = float(start_point[0]), float(start_point[1])
    ex, ey = float(end_point[0]), float(end_point[1])
    minimum_span = max(0.0, float(minimum_span))
    min_x, max_x = min(sx, ex), max(sx, ex)
    min_y, max_y = min(sy, ey), max(sy, ey)
    width = max(max_x - min_x, minimum_span)
    height = max(max_y - min_y, minimum_span)
    cx = (sx + ex) * 0.5
    cy = (sy + ey) * 0.5
    canonical = _canonical_shape_tool(tool)
    if canonical == "Circle":
        radius = max(min(width, height) * 0.5, minimum_span * 0.5)
        points = [
            (
                cx + (math.cos((math.pi * 2.0) * (float(index) / 48.0)) * radius),
                cy + (math.sin((math.pi * 2.0) * (float(index) / 48.0)) * radius),
                0.0,
            )
            for index in range(49)
        ]
        points[-1] = points[0]
        return points
    if canonical == "Oval":
        rx = max(width * 0.5, minimum_span * 0.5)
        ry = max(height * 0.5, minimum_span * 0.5)
        points = [
            (
                cx + (math.cos((math.pi * 2.0) * (float(index) / 48.0)) * rx),
                cy + (math.sin((math.pi * 2.0) * (float(index) / 48.0)) * ry),
                0.0,
            )
            for index in range(49)
        ]
        points[-1] = points[0]
        return points
    if canonical == "Star":
        rx = max(width * 0.5, minimum_span * 0.5)
        ry = max(height * 0.5, minimum_span * 0.5)
        points = [
            (
                cx + (math.cos((math.pi * 2.0) * (float(index) / 10.0) - (math.pi / 2.0)) * rx * (1.0 if index % 2 == 0 else 0.4375)),
                cy + (math.sin((math.pi * 2.0) * (float(index) / 10.0) - (math.pi / 2.0)) * ry * (1.0 if index % 2 == 0 else 0.4375)),
                0.0,
            )
            for index in range(11)
        ]
        points[-1] = points[0]
        return points
    return []
CAMERA_NOTES_NAME = "amirAnimatorsPencilNotes_CAM"
CAMERA_NOTES_SHAPE_NAME = CAMERA_NOTES_NAME + "Shape"
CAMERA_NOTES_ATTR = "animatorsPencilCameraNotes"
DRAW_CONTEXT_NAME = "aminateAnimatorsPencilDrawContext"
MARQUEE_CONTEXT_NAME = "aminateAnimatorsPencilMarqueeContext"
DRAW_PREVIEW_NAME = "aminateAnimatorsPencilLivePreview"
ERASER_PREVIEW_NAME = "aminateAnimatorsPencilLiveErase"
MARQUEE_PREVIEW_NAME = "aminateAnimatorsPencilMarqueePreview"
MARQUEE_TRANSFORM_BOX_NAME = "aminateAnimatorsPencilMarqueeTransformBox"
MARQUEE_TRANSFORM_BOX_ATTR = "animatorsPencilMarqueeTransformBox"
DRAW_PRESS_MEL_COMMAND = "import maya_animators_pencil; maya_animators_pencil._animators_pencil_draw_press()"
DRAW_DRAG_MEL_COMMAND = "import maya_animators_pencil; maya_animators_pencil._animators_pencil_draw_drag()"
DRAW_RELEASE_MEL_COMMAND = "import maya_animators_pencil; maya_animators_pencil._animators_pencil_draw_release()"
MARQUEE_PRESS_MEL_COMMAND = "import maya_animators_pencil; maya_animators_pencil._animators_pencil_marquee_press()"
MARQUEE_DRAG_MEL_COMMAND = "import maya_animators_pencil; maya_animators_pencil._animators_pencil_marquee_drag()"
MARQUEE_RELEASE_MEL_COMMAND = "import maya_animators_pencil; maya_animators_pencil._animators_pencil_marquee_release()"
MARKING_MENU_PREFIX = "aminateAnimatorsPencilMarkingMenu"
RGB_SWATCH_MARKING_MENU_LABEL = "RGB Colour + Swatches..."
TRANSLUCENT_MARKS_ATTR = "animatorsPencilTranslucentMarks"
SWATCHES_ATTR = "animatorsPencilSwatches"
SHAPE_PRESETS_ATTR = "animatorsPencilShapePresets"
DEFAULT_SHORTCUTS = {
    "drag_draw": "D",
    "marquee_select": "M",
    "eraser_tool": "E",
    "erase_selected": "Delete",
    "toggle_translucent": "T",
    "brush_smaller": "[",
    "brush_larger": "]",
}
BRUSH_SHORTCUT_PAIRS = (
    ("[", "]"),
    ("Ctrl+[", "Ctrl+]"),
    ("Alt+[", "Alt+]"),
    ("Ctrl+Alt+[", "Ctrl+Alt+]"),
    ("Shift+Alt+[", "Shift+Alt+]"),
    ("Ctrl+Shift+[", "Ctrl+Shift+]"),
)
MARKING_MENU_TRIGGERS = (
    ("Ctrl+Shift+RMB", {"ctrlModifier": True, "shiftModifier": True, "altModifier": False}),
    ("Ctrl+Alt+RMB", {"ctrlModifier": True, "shiftModifier": False, "altModifier": True}),
    ("Shift+Alt+RMB", {"ctrlModifier": False, "shiftModifier": True, "altModifier": True}),
)
GLOBAL_DRAG_CONTEXT_CONTROLLER = None
REFERENCE_VIEWER_WINDOW_NAME = "aminatePencilReferenceViewerWindow"
REFERENCE_VIEWER_LAYOUT_NAME = "aminatePencilReferenceViewerLayout"
REFERENCE_VIEWER_PANEL_NAME = "aminatePencilReferenceViewerPanel"
# Maya needs two CVs for a degree-one curve.  A press/release without a move
# therefore gets the smallest possible local segment so it renders as a dot,
# rather than falling through to the old arbitrary drag defaults.
SINGLE_CLICK_STROKE_EPSILON = 1.0e-4
VIDEO_VIEWER_MODE_ATTR = "amirVideoViewerMode"
VIDEO_VIEWER_VISIBLE_ATTR = "amirVideoViewerVisible"
VIDEO_VIEWER_PLACEMENT_ATTR = "amirVideoViewerPlacement"
VIDEO_VIEWER_SCALE_ATTR = "amirVideoViewerScale"
VIDEO_VIEWER_FREEFORM_GEOMETRY_ATTR = "amirVideoViewerFreeformGeometry"


def _qt_flag(scope_name, member_name, fallback=None):
    if hasattr(QtCore.Qt, member_name):
        return getattr(QtCore.Qt, member_name)
    scoped_enum = getattr(QtCore.Qt, scope_name, None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return fallback


def _tool_button_popup_mode(member_name):
    if hasattr(QtWidgets.QToolButton, member_name):
        return getattr(QtWidgets.QToolButton, member_name)
    scoped_enum = getattr(QtWidgets.QToolButton, "ToolButtonPopupMode", None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return getattr(QtWidgets.QToolButton, "InstantPopup", 2)


def _color_dialog_option(member_name):
    if hasattr(QtWidgets.QColorDialog, member_name):
        return getattr(QtWidgets.QColorDialog, member_name)
    scoped_enum = getattr(QtWidgets.QColorDialog, "ColorDialogOption", None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return None


def _size_policy_value(member_name):
    if hasattr(QtWidgets.QSizePolicy, member_name):
        return getattr(QtWidgets.QSizePolicy, member_name)
    scoped_enum = getattr(QtWidgets.QSizePolicy, "Policy", None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return None


def _shortcut_class():
    return getattr(QtWidgets, "QShortcut", None) or getattr(QtGui, "QShortcut", None)


def _qt_object_valid(obj):
    if obj is None:
        return False
    try:
        return bool(shiboken is None or shiboken.isValid(obj))
    except Exception:
        return False


def _maya_main_qt_window():
    if not (MAYA_AVAILABLE and omui and shiboken):
        return None
    try:
        pointer = omui.MQtUtil.mainWindow()
        return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
    except Exception:
        return None


def _maya_ui_qt_widget(ui_name):
    if not (MAYA_AVAILABLE and omui and shiboken and ui_name):
        return None
    pointer = None
    for finder_name in ("findWindow", "findControl", "findLayout"):
        try:
            pointer = getattr(omui.MQtUtil, finder_name)(ui_name)
        except Exception:
            pointer = None
        if pointer:
            break
    try:
        return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
    except Exception:
        return None


def _model_panel_qt_widget(panel_name):
    if not (MAYA_AVAILABLE and omui and shiboken and panel_name):
        return None
    try:
        control_name = cmds.modelPanel(panel_name, query=True, control=True)
    except Exception:
        control_name = ""
    if not control_name:
        return None
    pointer = None
    for finder in (omui.MQtUtil.findControl, omui.MQtUtil.findLayout):
        try:
            pointer = finder(control_name)
        except Exception:
            pointer = None
        if pointer:
            break
    try:
        return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
    except Exception:
        return None


def _model_panel_viewport_widget(panel_name):
    """Return the largest visible QmayaGLWidget owned by a model panel."""
    root = _model_panel_qt_widget(panel_name)
    if _qt_object_valid(root):
        try:
            if root.isVisible() and root.metaObject().className() == "QmayaGLWidget":
                return root
            candidates = [
                child for child in root.findChildren(QtWidgets.QWidget)
                if _qt_object_valid(child)
                and child.isVisible()
                and child.metaObject().className() == "QmayaGLWidget"
            ]
            if candidates:
                candidate = max(candidates, key=lambda child: child.width() * child.height())
                return candidate if _qt_object_valid(candidate) else None
        except Exception:
            pass

    # Maya can keep stale MQtUtil wrappers after a named panel-layout change.
    # Fall back to the live Qt widget tree and require the requested modelPanel
    # objectName in the viewport widget's valid ancestor chain.
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    candidates = []
    try:
        all_widgets = list(QtWidgets.QApplication.allWidgets())
    except Exception:
        all_widgets = []
    for widget in all_widgets:
        if not _qt_object_valid(widget):
            continue
        try:
            if not widget.isVisible() or widget.metaObject().className() != "QmayaGLWidget":
                continue
        except Exception:
            continue
        owner = widget
        owns_requested_panel = False
        while _qt_object_valid(owner):
            try:
                if str(owner.objectName() or "") == str(panel_name):
                    owns_requested_panel = True
                    break
                owner = owner.parentWidget()
            except Exception:
                owner = None
        if owns_requested_panel and _qt_object_valid(widget):
            candidates.append(widget)
    if not candidates:
        return None
    candidate = max(candidates, key=lambda child: child.width() * child.height())
    return candidate if _qt_object_valid(candidate) else None


def _qt_event_type(name):
    event_type = getattr(QtCore.QEvent, name, None)
    if event_type is not None:
        return event_type
    scoped_enum = getattr(QtCore.QEvent, "Type", None)
    return getattr(scoped_enum, name, None) if scoped_enum is not None else None


def _model_panel_for_viewport_widget(widget):
    if not (MAYA_AVAILABLE and _qt_object_valid(widget)):
        return ""
    panel_names = set(cmds.getPanel(type="modelPanel") or [])
    owner = widget
    while _qt_object_valid(owner):
        try:
            object_name = str(owner.objectName() or "")
        except Exception:
            object_name = ""
        if object_name in panel_names:
            return object_name
        try:
            owner = owner.parentWidget()
        except Exception:
            owner = None
    for panel_name in panel_names:
        if _model_panel_viewport_widget(panel_name) is widget:
            return panel_name
    return ""


def _panel_camera_transform(panel_name):
    if not (MAYA_AVAILABLE and panel_name):
        return ""
    try:
        camera = cmds.modelPanel(panel_name, query=True, camera=True) or ""
        if camera and cmds.nodeType(camera) == "camera":
            parents = cmds.listRelatives(camera, parent=True, fullPath=True) or []
            return parents[0] if parents else camera
        return camera
    except Exception:
        return ""


def _normalized_freehand_points(points):
    """Return clean layer points and whether the input was a single click.

    A degree-one Maya curve cannot be created from one CV.  Keep a genuine
    click at its exact mapped position, then add only a tiny local epsilon so
    the resulting curve displays as a dot.  Empty input is intentionally
    rejected instead of inventing the historical diagonal drag.
    """
    clean_points = [(float(point[0]), float(point[1]), 0.0) for point in (points or [])]
    single_click = len(clean_points) == 1
    if single_click:
        x, y, z = clean_points[0]
        clean_points.append((x + SINGLE_CLICK_STROKE_EPSILON, y, z))
    return clean_points, single_click


def _drawing_input_camera():
    """Return the camera that owns the viewport receiving drawing input.

    The ordinary active-camera helpers deliberately ignore the retained
    Reference Viewer so a pinned viewer never hijacks main-viewport navigation.
    Drawing and marquee gestures are the opposite: if the user presses inside
    that viewer, its modelPanel is the coordinate system for the gesture.
    """
    if not MAYA_AVAILABLE:
        return ""
    panel = _active_model_panel(include_reference_viewer=True)
    return _panel_camera_transform(panel) or _current_camera()


def _set_camera_for_viewport_widget(widget, camera_transform):
    if not (MAYA_AVAILABLE and camera_transform and cmds.objExists(camera_transform)):
        return False
    # Maya destroys/recreates QmayaGLWidget wrappers when a modelPanel camera
    # changes.  A wrapper captured just before that rebuild can therefore be
    # invalid by the time navigation runs.  Resolve the panel while the
    # wrapper is live, then fall back to Maya's focused main panel when it is
    # already stale.  The caller only uses this helper for the active main
    # viewport, so the fallback cannot retarget the pinned Reference Viewer.
    panel_name = _model_panel_for_viewport_widget(widget) if _qt_object_valid(widget) else ""
    if not panel_name:
        panel_name = _active_model_panel()
    if not panel_name or panel_name == REFERENCE_VIEWER_PANEL_NAME:
        return False
    if not panel_name:
        return False
    try:
        cmds.modelPanel(panel_name, edit=True, camera=camera_transform)
        return _panel_camera_transform(panel_name) == camera_transform or _short_name(_panel_camera_transform(panel_name)) == _short_name(camera_transform)
    except Exception:
        return False


def _is_drawing_view_camera(camera_transform):
    return bool(camera_transform and cmds.objExists(camera_transform) and _get_string_attr(camera_transform, DRAWING_VIEW_ATTR, "") == "drawing_view")


def _maya_hotkey_name(sequence):
    if not MAYA_AVAILABLE:
        return ""
    text = QtGui.QKeySequence(sequence).toString()
    parts = [part.strip() for part in text.split("+") if part.strip()]
    if not parts:
        return ""
    modifiers = {part.lower() for part in parts[:-1]}
    kwargs = {
        "keyShortcut": parts[-1],
        "altModifier": "alt" in modifiers,
        "ctlModifier": "ctrl" in modifiers,
        "shiftModifier": "shift" in modifiers,
    }
    try:
        press_name = cmds.hotkey(query=True, name=True, **kwargs) or ""
        release_name = cmds.hotkey(query=True, releaseName=True, **kwargs) or ""
        return press_name or release_name
    except Exception:
        return ""


def _qt_shortcut_in_use(sequence, root_widget=None):
    root_widget = root_widget or _maya_main_qt_window()
    if not _qt_object_valid(root_widget):
        return False
    target = QtGui.QKeySequence(sequence)
    shortcut_type = _shortcut_class()
    if shortcut_type is not None:
        for shortcut in root_widget.findChildren(shortcut_type):
            try:
                if shortcut.isEnabled() and shortcut.key() == target:
                    return True
            except Exception:
                continue
    action_type = getattr(QtGui, "QAction", None) or getattr(QtWidgets, "QAction", None)
    if action_type is not None:
        for action in root_widget.findChildren(action_type):
            try:
                if action.isEnabled() and target in action.shortcuts():
                    return True
            except Exception:
                continue
    return False


def _split_polyline_by_eraser(points, eraser_points, radius):
    """Return untouched fragments after a paint-style eraser pass.

    The old implementation densified *every* stroke segment and then compared
    every generated point with every eraser segment.  A long stroke therefore
    became an O(points x eraser-points) loop with a large Python allocation on
    every drag release.  Keep the same data-space behaviour, but use a small
    spatial grid and squared-distance segment tests.  Only source segments
    whose bounds overlap the eraser are adaptively sampled; untouched runs are
    copied straight through.
    """
    clean_points = [(float(point[0]), float(point[1]), 0.0) for point in (points or [])]
    clean_eraser = [(float(point[0]), float(point[1]), 0.0) for point in (eraser_points or [])]
    radius = max(0.001, float(radius))
    if len(clean_points) < 2 or not clean_eraser:
        return False, [clean_points] if len(clean_points) >= 2 else []

    radius_sq = radius * radius

    def point_segment_distance_sq(point, start, end):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_squared = (dx * dx) + (dy * dy)
        if length_squared <= 1e-12:
            return ((point[0] - start[0]) ** 2.0) + ((point[1] - start[1]) ** 2.0)
        amount = max(0.0, min(1.0, (((point[0] - start[0]) * dx) + ((point[1] - start[1]) * dy)) / length_squared))
        nearest = (start[0] + (amount * dx), start[1] + (amount * dy))
        return ((point[0] - nearest[0]) ** 2.0) + ((point[1] - nearest[1]) ** 2.0)

    def orientation(a, b, c):
        return ((b[0] - a[0]) * (c[1] - a[1])) - ((b[1] - a[1]) * (c[0] - a[0]))

    def on_segment(a, b, point):
        return (
            min(a[0], b[0]) - 1e-12 <= point[0] <= max(a[0], b[0]) + 1e-12
            and min(a[1], b[1]) - 1e-12 <= point[1] <= max(a[1], b[1]) + 1e-12
        )

    def segments_intersect(a, b, c, d):
        first = orientation(a, b, c)
        second = orientation(a, b, d)
        third = orientation(c, d, a)
        fourth = orientation(c, d, b)
        if ((first > 1e-12 and second < -1e-12) or (first < -1e-12 and second > 1e-12)) and ((third > 1e-12 and fourth < -1e-12) or (third < -1e-12 and fourth > 1e-12)):
            return True
        return (
            abs(first) <= 1e-12 and on_segment(a, b, c)
            or abs(second) <= 1e-12 and on_segment(a, b, d)
            or abs(third) <= 1e-12 and on_segment(c, d, a)
            or abs(fourth) <= 1e-12 and on_segment(c, d, b)
        )

    def segment_distance_sq(start, end, other_start, other_end):
        if segments_intersect(start, end, other_start, other_end):
            return 0.0
        return min(
            point_segment_distance_sq(start, other_start, other_end),
            point_segment_distance_sq(end, other_start, other_end),
            point_segment_distance_sq(other_start, start, end),
            point_segment_distance_sq(other_end, start, end),
        )

    eraser_segments = []
    cell_size = max(radius * 4.0, 0.05)
    eraser_grid = {}
    if len(clean_eraser) == 1:
        clean_eraser.append(clean_eraser[0])
    for index, (start, end) in enumerate(zip(clean_eraser[:-1], clean_eraser[1:])):
        bounds = (
            min(start[0], end[0]) - radius,
            min(start[1], end[1]) - radius,
            max(start[0], end[0]) + radius,
            max(start[1], end[1]) + radius,
        )
        eraser_segments.append((start, end, bounds))
        cell_min_x = int(math.floor(bounds[0] / cell_size))
        cell_max_x = int(math.floor(bounds[2] / cell_size))
        cell_min_y = int(math.floor(bounds[1] / cell_size))
        cell_max_y = int(math.floor(bounds[3] / cell_size))
        for cell_x in range(cell_min_x, cell_max_x + 1):
            for cell_y in range(cell_min_y, cell_max_y + 1):
                eraser_grid.setdefault((cell_x, cell_y), []).append(index)

    def candidate_indices(start, end):
        min_x = min(start[0], end[0]) - radius
        max_x = max(start[0], end[0]) + radius
        min_y = min(start[1], end[1]) - radius
        max_y = max(start[1], end[1]) + radius
        result = set()
        for cell_x in range(int(math.floor(min_x / cell_size)), int(math.floor(max_x / cell_size)) + 1):
            for cell_y in range(int(math.floor(min_y / cell_size)), int(math.floor(max_y / cell_size)) + 1):
                result.update(eraser_grid.get((cell_x, cell_y), ()))
        return result

    def point_distance_to_eraser_sq(point):
        candidates = candidate_indices(point, point)
        if not candidates:
            return float("inf")
        best = float("inf")
        for index in candidates:
            start, end, bounds = eraser_segments[index]
            if point[0] < bounds[0] or point[0] > bounds[2] or point[1] < bounds[1] or point[1] > bounds[3]:
                continue
            best = min(best, point_segment_distance_sq(point, start, end))
        return best

    touched = False
    fragments = []
    current = [] if point_distance_to_eraser_sq(clean_points[0]) <= radius_sq else [clean_points[0]]
    touched = bool(not current)
    for start, end in zip(clean_points[:-1], clean_points[1:]):
        stroke_bounds = (
            min(start[0], end[0]) - radius,
            min(start[1], end[1]) - radius,
            max(start[0], end[0]) + radius,
            max(start[1], end[1]) + radius,
        )
        candidate_ids = candidate_indices(start, end)
        hit = any(
            not (
                stroke_bounds[2] < eraser_segments[index][2][0]
                or stroke_bounds[0] > eraser_segments[index][2][2]
                or stroke_bounds[3] < eraser_segments[index][2][1]
                or stroke_bounds[1] > eraser_segments[index][2][3]
            )
            and segment_distance_sq(start, end, eraser_segments[index][0], eraser_segments[index][1]) <= radius_sq
            for index in candidate_ids
        )
        if not hit:
            current.append(end)
            continue

        touched = True
        # A touched source segment is the only place that needs adaptive
        # samples. This retains surviving pieces when an eraser crosses the
        # middle of a coarse segment without expanding the whole stroke.
        segment_length = math.sqrt(((end[0] - start[0]) ** 2.0) + ((end[1] - start[1]) ** 2.0))
        steps = max(8, min(1024, int(math.ceil(segment_length / max(radius * 0.25, 0.001)))))
        for step in range(1, steps + 1):
            amount = float(step) / float(steps)
            sample = (
                start[0] + ((end[0] - start[0]) * amount),
                start[1] + ((end[1] - start[1]) * amount),
                0.0,
            )
            if point_distance_to_eraser_sq(sample) <= radius_sq:
                if len(current) >= 2:
                    fragments.append(current)
                current = []
            else:
                current.append(sample)
    if len(current) >= 2:
        fragments.append(current)
    return touched, fragments if touched else [clean_points]


def _segment_polyline_by_box(points, bounds, closed=None):
    """Clip a polyline into ordered inside/outside box fragments.

    Each returned item is ``(inside, points)``.  Segment/rectangle
    intersections are inserted even when the source stroke has no CV at the
    boundary, so a marquee can move only the part of a curve that lies inside
    the box.  Fragments shorter than one meaningful segment are discarded.
    """
    clean_points = [
        (float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0)
        for point in (points or [])
    ]
    if len(clean_points) < 2:
        return []
    box_values = list(bounds or [])
    if len(box_values) >= 6:
        min_x, min_y, max_x, max_y = (
            float(box_values[0]),
            float(box_values[1]),
            float(box_values[3]),
            float(box_values[4]),
        )
    elif len(box_values) >= 4:
        min_x, min_y, max_x, max_y = [float(value) for value in box_values[:4]]
    else:
        return []
    min_x, max_x = min(min_x, max_x), max(min_x, max_x)
    min_y, max_y = min(min_y, max_y), max(min_y, max_y)
    epsilon = 1.0e-9
    point_epsilon_sq = 1.0e-16

    def same_point(first, second):
        return (
            (first[0] - second[0]) ** 2.0
            + (first[1] - second[1]) ** 2.0
            + (first[2] - second[2]) ** 2.0
        ) <= point_epsilon_sq

    def interpolate(start, end, amount):
        return (
            start[0] + ((end[0] - start[0]) * amount),
            start[1] + ((end[1] - start[1]) * amount),
            start[2] + ((end[2] - start[2]) * amount),
        )

    def inside(point):
        return (
            min_x - epsilon <= point[0] <= max_x + epsilon
            and min_y - epsilon <= point[1] <= max_y + epsilon
        )

    def segment_parameters(start, end):
        values = [0.0, 1.0]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        if abs(dx) > epsilon:
            for edge in (min_x, max_x):
                amount = (edge - start[0]) / dx
                if epsilon < amount < 1.0 - epsilon:
                    y_value = start[1] + (dy * amount)
                    if min_y - epsilon <= y_value <= max_y + epsilon:
                        values.append(amount)
        if abs(dy) > epsilon:
            for edge in (min_y, max_y):
                amount = (edge - start[1]) / dy
                if epsilon < amount < 1.0 - epsilon:
                    x_value = start[0] + (dx * amount)
                    if min_x - epsilon <= x_value <= max_x + epsilon:
                        values.append(amount)
        values.sort()
        unique = []
        for amount in values:
            if not unique or abs(amount - unique[-1]) > epsilon:
                unique.append(amount)
        return unique

    is_closed = bool(closed) if closed is not None else same_point(clean_points[0], clean_points[-1])
    segments = list(zip(clean_points[:-1], clean_points[1:]))
    if is_closed and not same_point(clean_points[-1], clean_points[0]):
        segments.append((clean_points[-1], clean_points[0]))

    result = []
    current_inside = None
    current_points = []

    def flush():
        nonlocal current_inside, current_points
        if current_inside is not None and len(current_points) >= 2:
            if not same_point(current_points[0], current_points[-1]):
                result.append((bool(current_inside), current_points))
            elif len(current_points) > 2:
                # A closed fragment may legitimately start/end at the same
                # point, but a two-point duplicate is only zero-length noise.
                result.append((bool(current_inside), current_points))
        current_inside = None
        current_points = []

    for start, end in segments:
        if same_point(start, end):
            continue
        parameters = segment_parameters(start, end)
        for first_amount, second_amount in zip(parameters[:-1], parameters[1:]):
            if second_amount - first_amount <= epsilon:
                continue
            first_point = interpolate(start, end, first_amount)
            second_point = interpolate(start, end, second_amount)
            if same_point(first_point, second_point):
                continue
            midpoint = interpolate(start, end, (first_amount + second_amount) * 0.5)
            piece_inside = inside(midpoint)
            if current_inside is None:
                current_inside = piece_inside
                current_points = [first_point, second_point]
                continue
            if piece_inside != current_inside:
                flush()
                current_inside = piece_inside
                current_points = [first_point, second_point]
                continue
            if not current_points:
                current_points = [first_point, second_point]
            else:
                if not same_point(current_points[-1], first_point):
                    current_points.append(first_point)
                if not same_point(current_points[-1], second_point):
                    current_points.append(second_point)
    flush()
    return result


def _matrix_transform_point(point, matrix, inverse=False):
    """Transform one mark-local point through a Maya row-vector matrix.

    Marquee bounds are expressed in the owning layer's camera plane, while a
    mark's stored ``points`` are expressed in that mark's local space.  Keep
    this conversion in one helper so clipping and fragment reconstruction use
    the same matrix convention as Maya's ``cmds.xform`` readback.
    """
    clean_point = (
        float(point[0]),
        float(point[1]),
        float(point[2]) if len(point) > 2 else 0.0,
    )
    if not matrix or len(matrix) < 16:
        return clean_point
    if om:
        try:
            maya_matrix = om.MMatrix()
            om.MScriptUtil.createMatrixFromList(matrix, maya_matrix)
            if inverse:
                maya_matrix = maya_matrix.inverse()
            transformed = om.MPoint(*clean_point) * maya_matrix
            return (float(transformed.x), float(transformed.y), float(transformed.z))
        except Exception:
            pass
    # This fallback keeps the helper useful in Maya-free contract tests.  The
    # object-space matrices used here are affine, so a small 3x3 inverse is
    # enough when the Maya API is not importable.
    a, b, c = float(matrix[0]), float(matrix[4]), float(matrix[8])
    d, e, f = float(matrix[1]), float(matrix[5]), float(matrix[9])
    g, h, i = float(matrix[2]), float(matrix[6]), float(matrix[10])
    tx, ty, tz = float(matrix[12]), float(matrix[13]), float(matrix[14])
    if not inverse:
        return (
            (clean_point[0] * a) + (clean_point[1] * b) + (clean_point[2] * c) + tx,
            (clean_point[0] * d) + (clean_point[1] * e) + (clean_point[2] * f) + ty,
            (clean_point[0] * g) + (clean_point[1] * h) + (clean_point[2] * i) + tz,
        )
    wx, wy, wz = clean_point[0] - tx, clean_point[1] - ty, clean_point[2] - tz
    determinant = (a * ((e * i) - (f * h))) - (b * ((d * i) - (f * g))) + (c * ((d * h) - (e * g)))
    if abs(determinant) <= 1.0e-12:
        return clean_point
    inverse_matrix = (
        ((e * i) - (f * h)) / determinant,
        ((c * h) - (b * i)) / determinant,
        ((b * f) - (c * e)) / determinant,
        ((f * g) - (d * i)) / determinant,
        ((a * i) - (c * g)) / determinant,
        ((c * d) - (a * f)) / determinant,
        ((d * h) - (e * g)) / determinant,
        ((b * g) - (a * h)) / determinant,
        ((a * e) - (b * d)) / determinant,
    )
    return (
        (wx * inverse_matrix[0]) + (wy * inverse_matrix[3]) + (wz * inverse_matrix[6]),
        (wx * inverse_matrix[1]) + (wy * inverse_matrix[4]) + (wz * inverse_matrix[7]),
        (wx * inverse_matrix[2]) + (wy * inverse_matrix[5]) + (wz * inverse_matrix[8]),
    )


def _split_polyline_by_box(points, bounds, closed=None):
    """Return ``(inside_fragments, outside_fragments)`` in path order."""
    segments = _segment_polyline_by_box(points, bounds, closed=closed)
    inside_fragments = [fragment for is_inside, fragment in segments if is_inside]
    outside_fragments = [fragment for is_inside, fragment in segments if not is_inside]
    return inside_fragments, outside_fragments


def _short_name(node_name):
    return (node_name or "").split("|")[-1].split(":")[-1]


def _long_name(node_name):
    if not MAYA_AVAILABLE or not node_name:
        return node_name
    try:
        matches = cmds.ls(node_name, long=True) or []
    except Exception:
        return node_name
    return matches[0] if matches else node_name


def _safe_name(value):
    clean = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in (value or "Layer"))
    clean = clean.strip("_") or "Layer"
    return clean[:48]


def _ensure_attr(node_name, attr_name, attr_type="string", default=None):
    if not MAYA_AVAILABLE or not cmds.objExists(node_name):
        return
    if cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return
    if attr_type == "string":
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
        if default is not None:
            cmds.setAttr("{0}.{1}".format(node_name, attr_name), default, type="string")
    elif attr_type == "bool":
        cmds.addAttr(node_name, longName=attr_name, attributeType="bool", defaultValue=bool(default))
    elif attr_type == "double":
        cmds.addAttr(node_name, longName=attr_name, attributeType="double", defaultValue=float(default or 0.0))
    elif attr_type == "long":
        cmds.addAttr(node_name, longName=attr_name, attributeType="long", defaultValue=int(default or 0))


def _set_string_attr(node_name, attr_name, value):
    _ensure_attr(node_name, attr_name, "string")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), value or "", type="string")


def _get_string_attr(node_name, attr_name, default=""):
    if not MAYA_AVAILABLE or not cmds.objExists(node_name):
        return default
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return default
    value = cmds.getAttr("{0}.{1}".format(node_name, attr_name))
    return value if value is not None else default


def _set_json_attr(node_name, attr_name, value):
    _set_string_attr(node_name, attr_name, json.dumps(value, sort_keys=True))


def _get_json_attr(node_name, attr_name, default=None):
    raw = _get_string_attr(node_name, attr_name, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _current_frame():
    if not MAYA_AVAILABLE:
        return 0
    return int(round(float(cmds.currentTime(query=True))))


def _current_camera():
    if not MAYA_AVAILABLE:
        return "persp"
    try:
        panel = _active_model_panel()
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            camera = cmds.modelPanel(panel, query=True, camera=True)
            if camera:
                parents = cmds.listRelatives(camera, parent=True, fullPath=False) or []
                return parents[0] if cmds.nodeType(camera) == "camera" and parents else camera
    except Exception:
        pass
    for fallback in ("persp", "camera1"):
        if cmds.objExists(fallback):
            return fallback
    cameras = cmds.ls(type="camera") or []
    if cameras:
        parents = cmds.listRelatives(cameras[0], parent=True, fullPath=False) or []
        return parents[0] if parents else cameras[0]
    return ""


def _camera_shape(camera_transform):
    if not MAYA_AVAILABLE or not camera_transform or not cmds.objExists(camera_transform):
        return ""
    try:
        if cmds.nodeType(camera_transform) == "camera":
            return camera_transform
    except Exception:
        return ""
    shapes = cmds.listRelatives(camera_transform, shapes=True, noIntermediate=True, fullPath=False) or []
    for shape in shapes:
        try:
            if cmds.nodeType(shape) == "camera":
                return shape
        except Exception:
            continue
    return ""


def _set_camera_for_model_panels(camera_transform):
    if not MAYA_AVAILABLE or not camera_transform or not cmds.objExists(camera_transform):
        return False
    changed = False
    try:
        panel = _active_model_panel()
        if panel and panel != REFERENCE_VIEWER_PANEL_NAME and cmds.getPanel(typeOf=panel) == "modelPanel":
            cmds.modelPanel(panel, edit=True, camera=camera_transform)
            changed = True
    except Exception:
        pass
    if changed:
        return True
    for panel in _main_model_panels():
        try:
            cmds.modelPanel(panel, edit=True, camera=camera_transform)
            return True
        except Exception:
            continue
    return False


def _main_model_panel_names(panel_names):
    """Return Maya model panels that belong to the main workspace.

    The retained Animator's Pencil Reference Viewer is a real Maya
    ``modelPanel`` in a separate window.  Maya reports it through
    ``getPanel(withFocus=True)`` when the viewer is clicked, but saved Pencil
    View switches must never retarget that pinned reference camera.  Keep the
    exclusion in one small, Maya-free helper so every panel-selection path
    applies the same rule without changing ordinary multi-panel behaviour.
    """
    return [panel for panel in (panel_names or []) if panel and panel != REFERENCE_VIEWER_PANEL_NAME]


def _main_model_panels():
    if not MAYA_AVAILABLE:
        return []
    try:
        return _main_model_panel_names(cmds.getPanel(type="modelPanel") or [])
    except Exception:
        return []


def _active_model_panel(include_reference_viewer=False):
    if not MAYA_AVAILABLE:
        return ""
    if include_reference_viewer:
        try:
            panels = list(cmds.getPanel(type="modelPanel") or [])
        except Exception:
            panels = []
    else:
        panels = _main_model_panels()
    # Maya's focus query is the best signal when the dock has just handed
    # focus back to a viewport.  Do this before the Qt wrapper scan: stale
    # wrappers for old model panels can otherwise make a live modelPanel
    # disappear from the visible list and route camera changes elsewhere.
    try:
        focused = cmds.getPanel(withFocus=True)
        if focused in panels and cmds.getPanel(typeOf=focused) == "modelPanel":
            return focused
    except Exception:
        pass
    visible = []
    if QtGui and QtWidgets:
        try:
            cursor = QtGui.QCursor.pos()
            for panel in panels:
                widget = _model_panel_viewport_widget(panel)
                if not _qt_object_valid(widget):
                    continue
                visible.append((panel, widget))
                if widget.rect().contains(widget.mapFromGlobal(cursor)):
                    return panel
        except Exception:
            visible = []
    if visible:
        return max(visible, key=lambda item: item[1].width() * item[1].height())[0]
    return panels[0] if panels else ""


def _active_model_panel_size():
    if not MAYA_AVAILABLE:
        return 1280.0, 720.0
    panel = _active_model_panel()
    try:
        control = cmds.modelPanel(panel, query=True, control=True) if panel else ""
        if control:
            width = float(cmds.control(control, query=True, width=True) or 1280.0)
            height = float(cmds.control(control, query=True, height=True) or 720.0)
            return max(width, 1.0), max(height, 1.0)
    except Exception:
        pass
    return 1280.0, 720.0


def _active_model_viewport_size():
    """Return the logical QmayaGLWidget size for the active model panel."""
    panel = _active_model_panel()
    widget = _model_panel_viewport_widget(panel)
    if widget:
        try:
            return max(float(widget.width()), 1.0), max(float(widget.height()), 1.0)
        except Exception:
            pass
    return _active_model_panel_size()


class _AnimatorsPencilReferenceViewerCloseFilter(QtCore.QObject):
    def __init__(self, viewer, parent=None):
        super(_AnimatorsPencilReferenceViewerCloseFilter, self).__init__(parent)
        self.viewer = viewer

    def eventFilter(self, watched, event):
        close_type = _qt_event_type("Close")
        if close_type is not None and event.type() == close_type:
            try:
                if QtWidgets.QApplication.closingDown():
                    return False
            except Exception:
                pass
            try:
                watched.hide()
                event.ignore()
                self.viewer._visible = False
            except Exception:
                pass
            return True
        try:
            self.viewer._record_window_event(watched, event)
        except Exception:
            pass
        return super(_AnimatorsPencilReferenceViewerCloseFilter, self).eventFilter(watched, event)


class AnimatorsPencilReferenceViewer(object):
    """One retained Maya modelPanel used as an annotatable video reference.

    The Maya window and modelPanel are created once, then only shown, moved,
    resized, reassigned to a Pencil camera, or hidden.  Normal use never closes
    a workspaceControl or deletes native Maya UI.
    """

    def __init__(self):
        self._close_filter = None
        self._visible = False
        self.mode = "pinned"
        self.placement = "top_right"
        self.scale_percent = 38.0
        self.anchor_panel = ""
        self.camera = ""
        self._floating_geometry = None
        self._pinned_geometry_snapshot = None
        self._geometry_update_depth = 0
        self._freeform_transition_pending = False
        self._freeform_geometry_dirty = False

    def _root_widget(self):
        return _maya_ui_qt_widget(REFERENCE_VIEWER_WINDOW_NAME)

    def _panel_exists(self):
        try:
            return bool(cmds.modelPanel(REFERENCE_VIEWER_PANEL_NAME, exists=True))
        except Exception:
            return False

    def exists(self):
        if not MAYA_AVAILABLE:
            return False
        try:
            return bool(cmds.window(REFERENCE_VIEWER_WINDOW_NAME, exists=True) and self._panel_exists())
        except Exception:
            return False

    def ensure(self, camera):
        if not MAYA_AVAILABLE:
            return False, "Reference Viewer needs Maya."
        if not camera or not cmds.objExists(camera):
            return False, "Choose or create a Pencil View first."
        window_exists = bool(cmds.window(REFERENCE_VIEWER_WINDOW_NAME, exists=True))
        panel_exists = self._panel_exists()
        if window_exists != panel_exists:
            return False, "The retained Reference Viewer is incomplete. Restart Maya before reopening it."
        if not window_exists:
            try:
                cmds.window(
                    REFERENCE_VIEWER_WINDOW_NAME,
                    title="Aminate Reference Viewer",
                    retain=True,
                    sizeable=True,
                    widthHeight=(640, 360),
                )
                cmds.formLayout(REFERENCE_VIEWER_LAYOUT_NAME)
                panel_name = cmds.modelPanel(
                    REFERENCE_VIEWER_PANEL_NAME,
                    label="Aminate Annotatable Reference",
                    menuBarVisible=False,
                    parent=REFERENCE_VIEWER_LAYOUT_NAME,
                )
                panel_control = cmds.modelPanel(panel_name, query=True, control=True) or panel_name
                cmds.formLayout(
                    REFERENCE_VIEWER_LAYOUT_NAME,
                    edit=True,
                    attachForm=[
                        (panel_control, "top", 0),
                        (panel_control, "left", 0),
                        (panel_control, "right", 0),
                        (panel_control, "bottom", 0),
                    ],
                )
                try:
                    cmds.modelEditor(
                        REFERENCE_VIEWER_PANEL_NAME,
                        edit=True,
                        grid=False,
                        headsUpDisplay=False,
                        displayAppearance="smoothShaded",
                    )
                except Exception:
                    pass
            except Exception as exc:
                return False, "Could not create the retained Reference Viewer: {0}".format(exc)
        try:
            cmds.modelPanel(REFERENCE_VIEWER_PANEL_NAME, edit=True, camera=camera)
        except Exception as exc:
            return False, "Could not assign the Pencil View to the Reference Viewer: {0}".format(exc)
        root = self._root_widget()
        if not _qt_object_valid(root):
            return False, "Maya created the Reference Viewer but its Qt window is not ready yet."
        delete_on_close = _qt_flag("WidgetAttribute", "WA_DeleteOnClose", None)
        if delete_on_close is not None:
            try:
                root.setAttribute(delete_on_close, False)
            except Exception:
                pass
        if self._close_filter is not None:
            try:
                root.removeEventFilter(self._close_filter)
            except Exception:
                pass
            self._close_filter = None
        self._close_filter = _AnimatorsPencilReferenceViewerCloseFilter(self, root)
        root.installEventFilter(self._close_filter)
        self.camera = _long_name(camera)
        return True, "Reference Viewer ready."

    def is_visible(self):
        root = self._root_widget()
        if not _qt_object_valid(root):
            return False
        try:
            self._visible = bool(root.isVisible())
        except Exception:
            self._visible = False
        return self._visible

    def hide(self):
        root = self._root_widget()
        if _qt_object_valid(root):
            try:
                if self.mode == "floating":
                    self._remember_freeform_geometry(root.geometry())
                root.hide()
            except Exception:
                return False
        self._visible = False
        return True

    def _anchor_widget(self, requested_panel=""):
        panels = []
        if requested_panel and requested_panel != REFERENCE_VIEWER_PANEL_NAME:
            panels.append(requested_panel)
        try:
            focused = cmds.getPanel(withFocus=True)
            if focused and focused != REFERENCE_VIEWER_PANEL_NAME and cmds.getPanel(typeOf=focused) == "modelPanel":
                panels.append(focused)
        except Exception:
            pass
        try:
            panels.extend(
                panel for panel in (cmds.getPanel(type="modelPanel") or [])
                if panel != REFERENCE_VIEWER_PANEL_NAME and panel not in panels
            )
        except Exception:
            pass
        candidates = []
        for panel in panels:
            widget = _model_panel_viewport_widget(panel)
            if not _qt_object_valid(widget):
                continue
            try:
                if widget.isVisible():
                    candidates.append((panel, widget))
            except Exception:
                continue
        if not candidates:
            return "", None
        if requested_panel:
            for panel, widget in candidates:
                if panel == requested_panel:
                    return panel, widget
        return max(candidates, key=lambda item: item[1].width() * item[1].height())

    def _pinned_geometry(self, placement, scale_percent, anchor_panel=""):
        panel, widget = self._anchor_widget(anchor_panel)
        if not _qt_object_valid(widget):
            return panel, None
        origin = widget.mapToGlobal(QtCore.QPoint(0, 0))
        viewport = QtCore.QRect(origin.x(), origin.y(), max(widget.width(), 1), max(widget.height(), 1))
        placement = str(placement or "top_right").lower()
        if placement == "full_view":
            return panel, viewport
        scale = max(0.10, min(1.0, float(scale_percent) / 100.0))
        width = min(viewport.width(), max(280, int(round(viewport.width() * scale))))
        height = min(viewport.height(), max(158, int(round(viewport.height() * scale))))
        margin = 8
        x = viewport.left() + margin
        y = viewport.top() + margin
        if placement in ("top_right", "bottom_right"):
            x = viewport.right() - width - margin + 1
        if placement in ("bottom_left", "bottom_right"):
            y = viewport.bottom() - height - margin + 1
        return panel, QtCore.QRect(x, y, width, height)

    def _apply_geometry(self, root, geometry):
        """Set retained-window bounds without mistaking our own move for a detach."""
        if not (_qt_object_valid(root) and geometry is not None):
            return False
        self._geometry_update_depth += 1
        try:
            root.setGeometry(QtCore.QRect(geometry))
        finally:
            self._geometry_update_depth = max(0, self._geometry_update_depth - 1)
        return True

    @staticmethod
    def _geometry_differs(first, second, tolerance=2):
        if first is None or second is None:
            return True
        return any(
            abs(int(getattr(first, name)()) - int(getattr(second, name)())) > int(tolerance)
            for name in ("x", "y", "width", "height")
        )

    @staticmethod
    def _position_differs(first, second, tolerance=2):
        if first is None or second is None:
            return True
        return any(
            abs(int(getattr(first, name)()) - int(getattr(second, name)())) > int(tolerance)
            for name in ("x", "y")
        )

    def _screen_safe_freeform_geometry(self, geometry):
        """Keep a restored freeform viewer usable after monitor changes."""
        if geometry is None:
            return None
        rect = QtCore.QRect(geometry)
        try:
            screens = list(QtGui.QGuiApplication.screens() or [])
        except Exception:
            screens = []
        if not screens:
            return rect
        best_screen = None
        best_area = -1
        for screen in screens:
            available = screen.availableGeometry()
            intersection = available.intersected(rect)
            area = max(0, intersection.width()) * max(0, intersection.height())
            if area > best_area:
                best_area = area
                best_screen = screen
        if best_screen is None or best_area <= 0:
            try:
                best_screen = QtGui.QGuiApplication.screenAt(rect.center())
            except Exception:
                best_screen = None
        if best_screen is None:
            best_screen = screens[0]
        available = best_screen.availableGeometry()
        width = min(max(280, rect.width()), max(280, available.width()))
        height = min(max(158, rect.height()), max(158, available.height()))
        max_x = available.right() - width + 1
        max_y = available.bottom() - height + 1
        x = min(max(rect.x(), available.left()), max_x)
        y = min(max(rect.y(), available.top()), max_y)
        return QtCore.QRect(int(x), int(y), int(width), int(height))

    def _remember_freeform_geometry(self, geometry, changed=True):
        safe_geometry = self._screen_safe_freeform_geometry(geometry)
        if safe_geometry is None:
            return False
        if self._geometry_differs(self._floating_geometry, safe_geometry, tolerance=0):
            self._floating_geometry = QtCore.QRect(safe_geometry)
            self._freeform_geometry_dirty = bool(changed)
            return True
        return False

    def set_floating_geometry(self, geometry):
        """Restore an earlier manual position without forcing the PIP anchor."""
        if geometry is None:
            return False
        self._remember_freeform_geometry(geometry, changed=False)
        return self._floating_geometry is not None

    def floating_geometry(self):
        if self._floating_geometry is None:
            return None
        return QtCore.QRect(self._floating_geometry)

    def consume_freeform_transition(self):
        pending = bool(self._freeform_transition_pending)
        self._freeform_transition_pending = False
        return pending

    def consume_freeform_geometry_dirty(self):
        dirty = bool(self._freeform_geometry_dirty)
        self._freeform_geometry_dirty = False
        return dirty

    def _record_window_event(self, root, event):
        """Detach PIP after a real window move; retain every later manual resize."""
        if self._geometry_update_depth or not self._visible or not _qt_object_valid(root):
            return False
        event_type = event.type()
        move_type = _qt_event_type("Move")
        resize_type = _qt_event_type("Resize")
        if event_type not in (move_type, resize_type):
            return False
        geometry = QtCore.QRect(root.geometry())
        if self.mode == "pinned":
            # Maya may emit geometry events while showing a retained window.
            # Only a position that leaves the current PIP location is a user
            # detach; a resize alone does not change the placement contract.
            if event_type != move_type or not self._position_differs(geometry, self._pinned_geometry_snapshot):
                return False
            self.mode = "floating"
            self._freeform_transition_pending = True
        if self.mode == "floating":
            return self._remember_freeform_geometry(geometry)
        return False

    def show(self, camera, mode="pinned", placement="top_right", scale_percent=38.0, anchor_panel=""):
        success, message = self.ensure(camera)
        if not success:
            return False, message
        root = self._root_widget()
        old_mode = self.mode
        if old_mode == "floating" and mode != "floating" and _qt_object_valid(root):
            self._floating_geometry = QtCore.QRect(root.geometry())
        self.mode = "floating" if str(mode) == "floating" else "pinned"
        self.placement = str(placement or "top_right")
        self.scale_percent = float(scale_percent)
        self._visible = False
        if self.mode == "pinned":
            panel, geometry = self._pinned_geometry(self.placement, self.scale_percent, anchor_panel)
            if geometry is None:
                return False, "Could not find the main Maya viewport for the Reference Viewer."
            self.anchor_panel = panel
            self._pinned_geometry_snapshot = QtCore.QRect(geometry)
            self._apply_geometry(root, geometry)
        else:
            _panel, sized_geometry = self._pinned_geometry("top_right", self.scale_percent, anchor_panel)
            target_size = sized_geometry.size() if sized_geometry is not None else QtCore.QSize(640, 360)
            if self._floating_geometry is not None:
                self._apply_geometry(root, self._screen_safe_freeform_geometry(self._floating_geometry))
            else:
                root.resize(target_size)
        try:
            cmds.window(REFERENCE_VIEWER_WINDOW_NAME, edit=True, visible=True)
        except Exception:
            root.show()
        # Maya may restore the retained window's previous geometry while it is
        # being shown. Reapply the requested geometry after visibility so PIP
        # does not reopen at its last Full View size.
        if self.mode == "pinned" and geometry is not None:
            self._pinned_geometry_snapshot = QtCore.QRect(geometry)
            self._apply_geometry(root, geometry)
        try:
            root.raise_()
        except Exception:
            pass
        self._visible = True
        return True, "Reference Viewer shown {0}.".format("as a floating window" if self.mode == "floating" else "over the main viewport")

    def sync_pinned_geometry(self):
        if self.mode != "pinned" or not self.is_visible():
            return False
        panel, geometry = self._pinned_geometry(self.placement, self.scale_percent, self.anchor_panel)
        root = self._root_widget()
        if geometry is None or not _qt_object_valid(root):
            return False
        self.anchor_panel = panel
        if root.geometry() != geometry:
            self._pinned_geometry_snapshot = QtCore.QRect(geometry)
            self._apply_geometry(root, geometry)
        return True


GLOBAL_REFERENCE_VIEWER = None


def _reference_viewer():
    global GLOBAL_REFERENCE_VIEWER
    if GLOBAL_REFERENCE_VIEWER is None:
        GLOBAL_REFERENCE_VIEWER = AnimatorsPencilReferenceViewer()
    return GLOBAL_REFERENCE_VIEWER


def _active_m3dview_widget(include_reference_viewer=False):
    """Return the cursor panel's exact M3dView and Qt drawing widget as one pair."""
    if not (MAYA_AVAILABLE and omui and QtWidgets and shiboken):
        return None, None
    try:
        # Normal camera/navigation queries intentionally exclude the retained
        # Reference Viewer.  Drawing input is different: when the user clicks
        # that modelPanel, the drag coordinates belong to its own widget and
        # must be paired with its own M3dView or every projected shape skews.
        panel = _active_model_panel(include_reference_viewer=include_reference_viewer)
        if panel:
            view = omui.M3dView()
            omui.M3dView.getM3dViewFromModelPanel(panel, view)
        else:
            view = omui.M3dView.active3dView()
        pointer = view.widget()
        widget = shiboken.wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
        return view, widget if _qt_object_valid(widget) else None
    except Exception:
        return None, None


def _active_m3dview_cursor_point(view=None, widget=None):
    """Return M3dView bottom-origin port coordinates from the OS cursor.

    ``draggerContext`` coordinates are useful for synthetic Maya/Qt events, but
    can belong to a different logical viewport after focus changes or Windows
    DPI conversion.  Couple the cursor widget to the *same* M3dView used for
    the ray so normal mouse drawing has one unambiguous coordinate system.
    """
    if not (MAYA_AVAILABLE and omui and QtCore and QtGui and QtWidgets and shiboken):
        return None, None
    try:
        view, widget = (view, widget) if view and _qt_object_valid(widget) else _active_m3dview_widget(include_reference_viewer=True)
        if not _qt_object_valid(widget):
            return view, None
        local = widget.mapFromGlobal(QtGui.QCursor.pos())
        if not widget.rect().contains(local):
            return view, None
        widget_width = max(float(widget.width()), 1.0)
        widget_height = max(float(widget.height()), 1.0)
        port_width = max(float(view.portWidth()), 1.0)
        port_height = max(float(view.portHeight()), 1.0)
        x = int(round(float(local.x()) * port_width / widget_width))
        y = int(round((widget_height - float(local.y())) * port_height / widget_height))
        return view, (max(0, min(x, int(port_width) - 1)), max(0, min(y, int(port_height) - 1)))
    except Exception:
        return None, None


def _active_m3dview_logical_cursor_point(view=None, widget=None):
    """Return the current cursor in draggerContext logical bottom-origin pixels.

    ``_active_m3dview_cursor_point`` intentionally returns M3dView port pixels
    for the freehand hitch sampler.  Shape and marquee gestures need the
    logical widget coordinates that ``draggerContext`` uses, so keep this
    conversion separate instead of feeding port pixels back through the scale
    step a second time.
    """
    if not (MAYA_AVAILABLE and QtCore and QtGui and QtWidgets and shiboken):
        return None
    try:
        view, widget = (view, widget) if view and _qt_object_valid(widget) else _active_m3dview_widget(include_reference_viewer=True)
        if not _qt_object_valid(widget):
            return None
        local = widget.mapFromGlobal(QtGui.QCursor.pos())
        if not widget.rect().contains(local):
            return None
        return (
            int(round(float(local.x()))),
            int(round(float(widget.height()) - float(local.y()))),
            0.0,
        )
    except Exception:
        return None


def _screen_to_layer_point(layer_node, screen_point, mapping_cache=None):
    """Map a draggerContext point onto the real drawing layer plane.

    Maya already knows the current model view's projection.  Using its viewport
    ray keeps marks under the cursor when a panel is resized, panned, zoomed,
    orthographic, or has film-fit/overscan settings.  The old FOV calculation
    remains only as a defensive fallback for headless or unusual views.
    """
    try:
        if om and omui and layer_node and cmds.objExists(layer_node):
            view = mapping_cache.get("view") if mapping_cache else None
            widget = mapping_cache.get("widget") if mapping_cache else None
            if view is None:
                view, widget = _active_m3dview_widget(include_reference_viewer=True)
            if screen_point:
                # Maya gives draggerContext points in the actual draw widget's
                # logical bottom-origin coordinates. The old code paired them
                # with an unrelated focused panel after a dock click.
                x = int(round(float(screen_point[0])))
                y = int(round(float(screen_point[1])))
                logical_width = (mapping_cache.get("logical_width") if mapping_cache else None) or (max(float(widget.width()), 1.0) if _qt_object_valid(widget) else _active_model_viewport_size()[0])
                logical_height = (mapping_cache.get("logical_height") if mapping_cache else None) or (max(float(widget.height()), 1.0) if _qt_object_valid(widget) else _active_model_viewport_size()[1])
                port_width = (mapping_cache.get("port_width") if mapping_cache else None) or (max(float(view.portWidth()), 1.0) if view else logical_width)
                port_height = (mapping_cache.get("port_height") if mapping_cache else None) or (max(float(view.portHeight()), 1.0) if view else logical_height)
                x = int(round(float(x) * port_width / logical_width))
                # draggerContext and M3dView.viewToWorld both use bottom-origin
                # viewport Y. Flipping here mirrors the stroke vertically.
                y = int(round(float(y) * port_height / logical_height))
            else:
                view, cursor_point = _active_m3dview_cursor_point(view, widget)
                if cursor_point:
                    # No raw event point: use real OS cursor -> exact widget -> port.
                    x, y = cursor_point
                else:
                    _viewport_width, _viewport_height = _active_model_viewport_size()
                    x, y = int(round(_viewport_width * 0.5)), int(round(_viewport_height * 0.5))
            view = view or omui.M3dView.active3dView()
            x = max(0, min(x, int(view.portWidth()) - 1))
            y = max(0, min(y, int(view.portHeight()) - 1))
            ray_origin = om.MPoint()
            ray_direction = om.MVector()
            view.viewToWorld(x, y, ray_origin, ray_direction)
            layer_matrix = mapping_cache.get("layer_matrix") if mapping_cache else None
            layer_inverse = mapping_cache.get("layer_inverse") if mapping_cache else None
            plane_origin = mapping_cache.get("plane_origin") if mapping_cache else None
            plane_normal = mapping_cache.get("plane_normal") if mapping_cache else None
            if layer_matrix is None:
                layer_matrix = om.MMatrix()
                om.MScriptUtil.createMatrixFromList(
                    cmds.xform(layer_node, query=True, matrix=True, worldSpace=True),
                    layer_matrix,
                )
                layer_inverse = layer_matrix.inverse()
                plane_origin = om.MPoint(0.0, 0.0, 0.0) * layer_matrix
                plane_normal = om.MVector(0.0, 0.0, 1.0) * layer_matrix
            if plane_normal.length() > 0.000001:
                plane_normal.normalize()
                denominator = ray_direction * plane_normal
                if abs(denominator) > 0.000001:
                    distance = ((plane_origin - ray_origin) * plane_normal) / denominator
                    if abs(distance) < 1000000.0:
                        hit = ray_origin + (ray_direction * distance)
                        local = hit * layer_inverse
                        return (float(local.x), float(local.y), float(local.z))
    except Exception:
        pass

    width, height = _active_model_panel_size()
    x = float(screen_point[0] if screen_point else width * 0.5)
    y = float(screen_point[1] if screen_point else height * 0.5)
    distance = 10.0
    camera = ""
    if layer_node and cmds.objExists(layer_node):
        camera = _get_string_attr(layer_node, "animatorsPencilCamera", "")
        try:
            distance = abs(float(cmds.getAttr(layer_node + ".translateZ") or 10.0))
        except Exception:
            distance = 10.0
    camera = camera or _current_camera()
    camera_shape = _camera_shape(camera)
    focal = 35.0
    vertical_aperture = 0.945
    if camera_shape:
        try:
            focal = float(cmds.getAttr(camera_shape + ".focalLength") or focal)
        except Exception:
            pass
        try:
            vertical_aperture = float(cmds.getAttr(camera_shape + ".verticalFilmAperture") or vertical_aperture)
        except Exception:
            pass
    vertical_fov = 2.0 * math.atan((vertical_aperture * 25.4) / (2.0 * max(focal, 0.001)))
    half_height = math.tan(vertical_fov * 0.5) * max(distance, 0.1)
    half_width = half_height * (width / max(height, 1.0))
    local_x = ((x / width) - 0.5) * 2.0 * half_width
    local_y = (0.5 - (y / height)) * 2.0 * half_height
    return (local_x, local_y, 0.0)


def _run_mel(command):
    if not MAYA_AVAILABLE or not mel:
        return None
    try:
        return mel.eval(command)
    except Exception:
        return None


def _open_undo_chunk(name):
    if MAYA_AVAILABLE:
        try:
            cmds.undoInfo(openChunk=True, chunkName=name)
        except Exception:
            pass


def _close_undo_chunk():
    if MAYA_AVAILABLE:
        try:
            cmds.undoInfo(closeChunk=True)
        except Exception:
            pass


def _set_display_color(node_name, color, opacity=1.0, line_width=2.0):
    shapes = cmds.listRelatives(node_name, shapes=True, noIntermediate=True, fullPath=True) or []
    children = cmds.listRelatives(node_name, allDescendents=True, fullPath=True) or []
    for child in children:
        if cmds.nodeType(child) in ("nurbsCurve", "nurbsSurface", "mesh"):
            shapes.append(child)
    seen = set()
    for shape in shapes:
        if shape in seen or not cmds.objExists(shape):
            continue
        seen.add(shape)
        for attr, value in (
            ("overrideEnabled", True),
            ("overrideRGBColors", True),
        ):
            if cmds.objExists("{0}.{1}".format(shape, attr)):
                cmds.setAttr("{0}.{1}".format(shape, attr), value)
        if cmds.objExists(shape + ".overrideColorRGB"):
            cmds.setAttr(shape + ".overrideColorRGB", color[0], color[1], color[2])
        if cmds.objExists(shape + ".overrideColorA"):
            cmds.setAttr(shape + ".overrideColorA", _clamp_opacity(opacity))
        if cmds.objExists(shape + ".lineWidth"):
            cmds.setAttr(shape + ".lineWidth", max(1.0, float(line_width)))
        if cmds.objExists(shape + ".overrideDisplayType"):
            cmds.setAttr(shape + ".overrideDisplayType", 0)
    if cmds.objExists(node_name + ".visibility"):
        cmds.setAttr(node_name + ".visibility", True)
    _ensure_attr(node_name, "animatorsPencilOpacity", "double", opacity)
    cmds.setAttr(node_name + ".animatorsPencilOpacity", float(opacity))


def _mark_shapes(mark):
    if not mark or not cmds.objExists(mark):
        return []
    shapes = cmds.listRelatives(mark, shapes=True, noIntermediate=True, fullPath=True) or []
    descendants = cmds.listRelatives(mark, allDescendents=True, fullPath=True) or []
    for child in descendants:
        try:
            if cmds.nodeType(child) in ("nurbsCurve", "nurbsSurface", "mesh"):
                shapes.append(child)
        except Exception:
            continue
    result = []
    seen = set()
    for shape in shapes:
        if shape in seen or not cmds.objExists(shape):
            continue
        seen.add(shape)
        result.append(shape)
    return result


def _clamp_opacity(value, default=1.0):
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return float(default)


def _set_mark_effective_opacity(mark, layer_opacity=1.0):
    """Keep per-mark opacity intact while applying the layer alpha to shapes."""
    if not mark or not cmds.objExists(mark):
        return False
    data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
    mark_opacity = data.get("opacity", 1.0)
    if cmds.attributeQuery("animatorsPencilOpacity", node=mark, exists=True):
        try:
            mark_opacity = cmds.getAttr(mark + ".animatorsPencilOpacity")
        except Exception:
            pass
    effective = _clamp_opacity(mark_opacity) * _clamp_opacity(layer_opacity)
    _ensure_attr(mark, "animatorsPencilEffectiveOpacity", "double", effective)
    cmds.setAttr(mark + ".animatorsPencilEffectiveOpacity", effective)
    for shape in _mark_shapes(mark):
        if cmds.objExists(shape + ".overrideColorA"):
            cmds.setAttr(shape + ".overrideColorA", effective)
    return True


def _curve_node(name, points, parent, color, opacity, size, degree=1):
    curve = cmds.curve(name=name, degree=degree, point=points)
    if parent:
        # `points` are already expressed in the drawing layer's local space.
        # Preserve those local CV coordinates when attaching the curve.
        curve = cmds.parent(curve, parent, relative=True)[0]
    curve = _long_name(curve)
    _set_display_color(curve, color, opacity=opacity, line_width=size)
    return curve


def _delete_drag_context(name):
    if not MAYA_AVAILABLE:
        return
    try:
        if cmds.draggerContext(name, exists=True):
            cmds.deleteUI(name)
    except Exception:
        pass


def _make_tool_icon(tool_name, color=None):
    if not QtGui:
        return QtGui.QIcon() if QtGui else None
    color = color or QtGui.QColor("#66D9EF")
    pixmap = QtGui.QPixmap(28, 28)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(color), 2)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        dark = QtGui.QColor("#202020")
        light = QtGui.QColor("#F6F6F6")
        tool = str(tool_name or "").lower()
        if tool == "pencil":
            painter.drawLine(7, 21, 19, 9)
            painter.drawLine(10, 23, 22, 11)
            painter.drawLine(19, 9, 22, 11)
            painter.drawLine(7, 21, 10, 23)
        elif tool == "brush":
            painter.drawLine(8, 20, 19, 9)
            painter.setBrush(QtGui.QColor(color))
            painter.drawEllipse(6, 18, 7, 5)
        elif tool == "eraser":
            painter.setBrush(QtGui.QColor(color))
            painter.drawPolygon(QtGui.QPolygon([QtCore.QPoint(8, 19), QtCore.QPoint(15, 12), QtCore.QPoint(21, 18), QtCore.QPoint(14, 24)]))
            painter.setPen(QtGui.QPen(light, 1))
            painter.drawLine(12, 15, 18, 21)
        elif tool == "text":
            font = painter.font()
            font.setBold(True)
            font.setPointSize(14)
            painter.setFont(font)
            painter.drawText(QtCore.QRect(5, 3, 20, 22), int(QtCore.Qt.AlignCenter), "T")
        elif tool == "line":
            painter.drawLine(7, 21, 21, 7)
        elif tool == "arrow":
            painter.drawLine(7, 20, 21, 8)
            painter.drawLine(21, 8, 15, 8)
            painter.drawLine(21, 8, 21, 14)
        elif tool == "rectangle":
            painter.drawRect(7, 8, 14, 12)
        elif tool in ("ellipse", "oval"):
            painter.drawEllipse(6, 8, 16, 12)
        elif tool == "circle":
            painter.drawEllipse(6, 6, 16, 16)
        elif tool == "star":
            star_points = []
            for index in range(10):
                angle = (math.pi * 2.0) * (float(index) / 10.0) - (math.pi / 2.0)
                radius = 9.0 if index % 2 == 0 else 4.0
                star_points.append(QtCore.QPoint(int(round(14.0 + math.cos(angle) * radius)), int(round(14.0 + math.sin(angle) * radius))))
            painter.drawPolygon(QtGui.QPolygon(star_points))
        elif tool == "camera":
            painter.setBrush(QtGui.QColor(color))
            painter.drawRoundedRect(6, 10, 13, 9, 2, 2)
            painter.drawPolygon(QtGui.QPolygon([QtCore.QPoint(19, 12), QtCore.QPoint(24, 9), QtCore.QPoint(24, 21), QtCore.QPoint(19, 18)]))
            painter.setPen(QtGui.QPen(dark, 1))
            painter.drawEllipse(10, 12, 5, 5)
        else:
            painter.drawEllipse(7, 7, 14, 14)
    finally:
        painter.end()
    return QtGui.QIcon(pixmap)


def _parent_if_needed(node_name, parent_name):
    if not parent_name or not cmds.objExists(node_name) or not cmds.objExists(parent_name):
        return node_name
    node_name = _long_name(node_name)
    parent_name = _long_name(parent_name)
    current_parent = (cmds.listRelatives(node_name, parent=True, fullPath=True) or [""])[0]
    if current_parent == parent_name or _short_name(current_parent) == _short_name(parent_name):
        return node_name
    result = cmds.parent(node_name, parent_name)
    return _long_name(result[0]) if result else node_name


class AnimatorsPencilController(object):
    def __init__(self):
        self.clipboard = []
        self.status_callback = None
        self._drag_options = {}
        self._drag_anchor = None
        self._drag_start_point = None
        self._drag_points = []
        self._drag_screen_points = []
        self._drag_preview = ""
        self._drag_preview_pending_points = []
        self._drag_preview_last_update = 0.0
        self._drag_preview_style = None
        self._drag_preview_interval = 1.0 / 45.0
        self._drag_preview_refresh_pending = False
        self._drag_preview_refresh_generation = 0
        self._drag_preview_undo_suppressed = False
        # Paint-style erasing is previewed against the original mark data.
        # Source shapes are temporarily hidden and the surviving fragments are
        # drawn in layer space until release commits the same split.  Keeping
        # this state separate from the Pencil preview avoids rebuilding the
        # source curve (and avoids undo entries) on every mouse sample.
        self._eraser_preview_marks = {}
        self._eraser_preview_layer = ""
        self._eraser_preview_last_update = 0.0
        self._eraser_preview_interval = 1.0 / 45.0
        self._drag_mapping_cache = None
        # Maya can briefly stop delivering draggerContext callbacks while a
        # heavy scene evaluates.  Keep one cheap cursor sampler alive for a
        # freehand gesture so the final stroke is not truncated at the last
        # callback Maya happened to deliver before that hitch.
        self._drag_capture_active = False
        self._drag_capture_generation = 0
        self._drag_capture_interval_ms = 16
        self._marquee_options = {}
        self._marquee_anchor = None
        self._marquee_start_point = None
        self._marquee_screen_points = []
        self._marquee_blocked_press = False
        self._marquee_mapping_cache = None
        self._marquee_preview = ""
        self._marquee_preview_last_update = 0.0
        self._marquee_transform_box = ""
        self._marquee_transform_layer = ""
        self._marquee_selection_job = 0
        self._marquee_commit_guard = False
        self._onion_job = 0
        self._onion_options = {}
        self._camera_scope_enabled = True
        self._camera_scope_dirty = True
        self._last_camera_scope_identity = None
        self._additional_visible_cameras = set()

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _status(self, message):
        if self.status_callback:
            self.status_callback(message)
        elif MAYA_AVAILABLE:
            try:
                import maya.api.OpenMaya as om
                om.MGlobal.displayInfo("[Animators Pencil] {0}".format(message))
            except Exception:
                pass

    def root(self):
        if not MAYA_AVAILABLE:
            return ""
        if cmds.objExists(ROOT_GROUP_NAME):
            return ROOT_GROUP_NAME
        root = cmds.createNode("transform", name=ROOT_GROUP_NAME)
        _set_string_attr(root, ROOT_MARKER_ATTR, "animators_pencil")
        _set_json_attr(root, ROOT_STATE_ATTR, {"version": LAYER_VERSION, "created": time.time()})
        return root

    def open_native_blue_pencil(self):
        if not MAYA_AVAILABLE:
            return False
        try:
            if not cmds.pluginInfo("bluePencil", query=True, loaded=True):
                cmds.loadPlugin("bluePencil", quiet=True)
        except Exception:
            pass
        result = _run_mel("OpenBluePencil;")
        _run_mel("ToggleBluePencilToolBar;")
        self._status("Native Blue Pencil opened.")
        return result is not None

    def set_native_tool(self, tool):
        command_map = {
            "Pencil": "bluePencilUtil -pencilTool;",
            "Brush": "bluePencilUtil -brushTool;",
            "Eraser": "bluePencilUtil -eraserTool;",
            "Text": "bluePencilUtil -textTool;",
            "Line": "bluePencilUtil -lineTool;",
            "Arrow": "bluePencilUtil -arrowTool;",
            "Rectangle": "bluePencilUtil -rectangleTool;",
            "Ellipse": "bluePencilUtil -ellipseTool;",
            # Maya's native Blue Pencil has no separate Circle/Oval/Star
            # tools.  Keep those names as Animator's Pencil drag tools while
            # mapping the nearest native fallback for callers that request
            # native options explicitly.
            "Circle": "bluePencilUtil -ellipseTool;",
            "Oval": "bluePencilUtil -ellipseTool;",
            "Star": "bluePencilUtil -pencilTool;",
        }
        self.open_native_blue_pencil()
        _run_mel(command_map.get(tool, "bluePencilUtil -pencilTool;"))
        self._status("Native Blue Pencil tool: {0}".format(tool))

    def apply_native_options(self, tool, color, size, opacity):
        self.open_native_blue_pencil()
        r, g, b = color
        _run_mel("bluePencilUtil -e -drawColor {0} {1} {2};".format(r, g, b))
        int_size = max(1, int(round(size)))
        int_opacity = max(1, min(100, int(round(opacity * 100.0))))
        if tool == "Brush":
            _run_mel("bluePencilUtil -brushOptions {0} {1} 50 false false;".format(int_size, int_opacity))
        elif tool == "Eraser":
            _run_mel("bluePencilUtil -eraserOptions {0} {1} 50 false false;".format(int_size, int_opacity))
        elif tool == "Text":
            _run_mel('bluePencilUtil -textOptions {0} {1} "Arial";'.format(int_size, int_opacity))
        elif tool == "Line":
            _run_mel("bluePencilUtil -lineOptions {0} {1};".format(int_size, int_opacity))
        elif tool == "Arrow":
            _run_mel("bluePencilUtil -arrowOptions {0} {1};".format(int_size, int_opacity))
        elif tool in ("Ellipse", "Oval", "Circle"):
            _run_mel("bluePencilUtil -ellipseOptions {0} {1};".format(int_size, int_opacity))
        elif tool == "Rectangle":
            _run_mel("bluePencilUtil -rectangleOptions {0} {1};".format(int_size, int_opacity))
        else:
            _run_mel("bluePencilUtil -pencilOptions {0} {1} false false;".format(int_size, int_opacity))
        self.set_native_tool(tool)

    def native_frame_command(self, action):
        command_map = {
            "insert": "bluePencilFrame -insert;",
            "delete": "bluePencilFrame -delete;",
            "duplicate": "bluePencilFrame -duplicate;",
            "cut": "bluePencilFrame -cut;",
            "copy": "bluePencilFrame -copy;",
            "paste": "bluePencilFrame -paste;",
            "clear": "bluePencilFrame -clear;",
            "step_back": "bluePencilFrame -stepBack;",
            "step_forward": "bluePencilFrame -stepForward;",
        }
        self.open_native_blue_pencil()
        _run_mel(command_map.get(action, "bluePencilFrame -duplicate;"))
        self._status("Native Blue Pencil frame: {0}".format(action.replace("_", " ")))

    def configure_native_ghosting(self, previous_count=2, next_count=2, previous_color=(0.1, 0.6, 1.0), next_color=(1.0, 0.4, 0.1)):
        self.open_native_blue_pencil()
        _run_mel("bluePencilUtil -e -ghostPrevious true;")
        _run_mel("bluePencilUtil -e -ghostNext true;")
        _run_mel("bluePencilUtil -e -ghostPreviousCount {0};".format(int(previous_count)))
        _run_mel("bluePencilUtil -e -ghostNextCount {0};".format(int(next_count)))
        _run_mel("bluePencilUtil -e -ghostColorOverride true;")
        _run_mel("bluePencilUtil -e -ghostColorPrevious {0} {1} {2};".format(previous_color[0], previous_color[1], previous_color[2]))
        _run_mel("bluePencilUtil -e -ghostColorNext {0} {1} {2};".format(next_color[0], next_color[1], next_color[2]))
        self._status("Native Blue Pencil ghosting configured.")

    def _tagged_transforms(self, marker_attr, marker_value):
        """Find Pencil-owned transforms without a Python scan of every rig node."""
        try:
            candidates = cmds.ls(
                "*.{0}".format(marker_attr),
                objectsOnly=True,
                long=True,
            ) or []
        except (TypeError, RuntimeError):
            candidates = cmds.ls(type="transform", long=True) or []
        result = []
        seen = set()
        for candidate in candidates:
            node = str(candidate).rsplit(".", 1)[0]
            if node in seen or not cmds.objExists(node):
                continue
            try:
                if cmds.nodeType(node) != "transform":
                    continue
            except Exception:
                continue
            if _get_string_attr(node, marker_attr, "") != marker_value:
                continue
            seen.add(node)
            result.append(_long_name(node))
        return result

    def layers(self, include_count=True):
        if not MAYA_AVAILABLE:
            return []
        result = []
        for node in self._tagged_transforms(LAYER_MARKER_ATTR, "layer"):
            node = self._migrate_layer_to_camera_anchor(node)
            data = self.layer_data(node, include_count=include_count)
            result.append(data)
        result.sort(key=lambda item: (item.get("order", 0), item.get("name", "")))
        return result

    def layer_data(self, layer_node, include_count=True):
        layer_node = _long_name(layer_node)
        data = _get_json_attr(layer_node, "animatorsPencilLayerData", {}) or {}
        data["node"] = layer_node
        data.setdefault("name", _short_name(layer_node))
        data.setdefault("camera", _get_string_attr(layer_node, "animatorsPencilCamera", ""))
        data.setdefault("state", _get_string_attr(layer_node, "animatorsPencilLayerState", "Animation"))
        data.setdefault("order", int(cmds.getAttr(layer_node + ".animatorsPencilLayerOrder")) if cmds.objExists(layer_node + ".animatorsPencilLayerOrder") else 0)
        data.setdefault("locked", bool(cmds.getAttr(layer_node + ".animatorsPencilLayerLocked")) if cmds.objExists(layer_node + ".animatorsPencilLayerLocked") else False)
        data["visible"] = self._layer_user_visible(layer_node)
        data["effective_visible"] = self._layer_effective_visible(layer_node)
        data["camera_filtered"] = bool(data["visible"] and not data["effective_visible"])
        data["opacity"] = self._layer_opacity(layer_node)
        data["opacity_percent"] = int(round(data["opacity"] * 100.0))
        if include_count:
            data["count"] = len(self.marks(layer_node))
        return data

    def _layer_matches_camera(self, layer_node, active_camera=None):
        layer_camera = _short_name(_get_string_attr(layer_node, "animatorsPencilCamera", "") if layer_node else "")
        active_camera = _short_name(active_camera or _current_camera())
        additional = {_short_name(camera) for camera in self._additional_visible_cameras if camera}
        return not layer_camera or not active_camera or layer_camera == active_camera or layer_camera in additional

    def set_additional_visible_cameras(self, cameras=None):
        normalized = {
            _long_name(camera) for camera in (cameras or [])
            if camera and cmds.objExists(camera)
        } if MAYA_AVAILABLE else set()
        if normalized == self._additional_visible_cameras:
            return False
        self._additional_visible_cameras = normalized
        self._camera_scope_dirty = True
        # The additional-camera identity is part of ``refresh_camera_scope``'s
        # cache key. Marking the scope dirty is enough to update it immediately
        # while avoiding a forced second pass during Reference Viewer restore.
        self.refresh_camera_scope()
        return True

    def _layer_user_visible(self, layer_node):
        """Return persistent user visibility, separate from camera filtering."""
        if not layer_node or not cmds.objExists(layer_node):
            return False
        attr = layer_node + "." + LAYER_USER_VISIBILITY_ATTR
        if not cmds.attributeQuery(LAYER_USER_VISIBILITY_ATTR, node=layer_node, exists=True):
            # Existing off-camera layers may be hidden only by camera scope.  Do
            # not accidentally turn that temporary state into a permanent hide.
            current = bool(cmds.getAttr(layer_node + ".visibility")) if cmds.objExists(layer_node + ".visibility") else True
            initial = current if (not self._camera_scope_enabled or self._layer_matches_camera(layer_node)) else True
            _ensure_attr(layer_node, LAYER_USER_VISIBILITY_ATTR, "bool", initial)
        try:
            return bool(cmds.getAttr(attr))
        except Exception:
            return True

    def _layer_opacity(self, layer_node):
        if not layer_node or not cmds.objExists(layer_node):
            return 1.0
        attr = layer_node + "." + LAYER_OPACITY_ATTR
        if not cmds.attributeQuery(LAYER_OPACITY_ATTR, node=layer_node, exists=True):
            data = _get_json_attr(layer_node, "animatorsPencilLayerData", {}) or {}
            _ensure_attr(layer_node, LAYER_OPACITY_ATTR, "double", _clamp_opacity(data.get("opacity", 1.0)))
        try:
            return _clamp_opacity(cmds.getAttr(attr))
        except Exception:
            return 1.0

    def _layer_effective_visible(self, layer_node, active_camera=None):
        if not layer_node or not cmds.objExists(layer_node):
            return False
        return bool(
            self._layer_user_visible(layer_node)
            and ((not self._camera_scope_enabled) or self._layer_matches_camera(layer_node, active_camera))
        )

    def _force_layer_display_evaluation(self, layer_node):
        """Dirty changed Pencil layer roots without blocking the camera switch.

        Pencil marks are DAG children of their layer transform.  Maya propagates
        a transform's visibility through that hierarchy, so walking every curve
        and synchronously repainting the viewport are both redundant and very
        expensive on a saved view with many marks.  The camera assignment already
        queues a viewport redraw, so this method only dirties the changed roots and
        lets Maya's normal event loop paint them with that camera update.
        """
        layer_nodes = list(layer_node) if isinstance(layer_node, (list, tuple, set)) else [layer_node]
        layer_nodes = [node for node in layer_nodes if node and cmds.objExists(node)]
        if not layer_nodes:
            return False
        dirty_ok = False
        try:
            # Maya accepts a node collection here. Dirtying only the layer roots
            # lets DAG visibility propagation handle every child mark.
            cmds.dgdirty(layer_nodes, allPlugs=True)
            dirty_ok = True
        except (TypeError, RuntimeError):
            # Older Maya wrappers may reject a list even though the root-level
            # command is valid. Keep the compatibility fallback root-only.
            for node in layer_nodes:
                try:
                    cmds.dgdirty(node, allPlugs=True)
                    dirty_ok = True
                except TypeError:
                    try:
                        cmds.dgdirty(node)
                        dirty_ok = True
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass
        return dirty_ok

    def _apply_layer_visibility(self, layer_node, active_camera=None, changed_layers=None):
        if not layer_node or not cmds.objExists(layer_node + ".visibility"):
            return False
        try:
            desired_visible = bool(self._layer_effective_visible(layer_node, active_camera))
            current_visible = bool(cmds.getAttr(layer_node + ".visibility"))
            # Camera switches commonly leave most off-camera layers in the
            # same state. Avoid rewriting and re-evaluating unchanged layers;
            # only layers whose effective state changed need a DAG update.
            if current_visible == desired_visible:
                return True
            cmds.setAttr(layer_node + ".visibility", desired_visible)
            if changed_layers is not None:
                changed_layers.append(layer_node)
                return True
            return self._force_layer_display_evaluation(layer_node)
        except Exception:
            return False

    def active_layer(self):
        state = _get_json_attr(self.root(), ROOT_STATE_ATTR, {}) or {}
        layer = state.get("active_layer")
        if layer and cmds.objExists(layer):
            return _long_name(layer)
        layers = self.layers(include_count=False)
        if layers:
            return layers[0]["node"]
        return self.create_layer("Pencil Layer")

    def active_layer_for_camera(self, preferred_layer=None, create=True, camera=None, layer_data=None):
        camera = camera or _current_camera()
        camera_identity = _long_name(camera) if camera and cmds.objExists(camera) else camera
        preferred_layer = _long_name(preferred_layer) if preferred_layer and cmds.objExists(preferred_layer) else ""
        if preferred_layer:
            data = self.layer_data(preferred_layer, include_count=False)
            stored_camera = data.get("camera") or ""
            stored_identity = _long_name(stored_camera) if stored_camera and cmds.objExists(stored_camera) else stored_camera
            if stored_identity == camera_identity and data.get("state") != "Locked":
                self.set_active_layer(preferred_layer)
                return preferred_layer
        for data in (layer_data if layer_data is not None else self.layers(include_count=False)):
            stored_camera = data.get("camera") or ""
            stored_identity = _long_name(stored_camera) if stored_camera and cmds.objExists(stored_camera) else stored_camera
            if stored_identity == camera_identity and data.get("state") != "Locked":
                self.set_active_layer(data["node"])
                return data["node"]
        if not create:
            return ""
        return self.create_layer("Pencil Layer", camera=camera)

    def is_drawing_view(self, camera):
        if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
            return False
        camera = _long_name(camera)
        if cmds.nodeType(camera) == "camera":
            parents = cmds.listRelatives(camera, parent=True, fullPath=True) or []
            camera = parents[0] if parents else camera
        return _get_string_attr(camera, DRAWING_VIEW_ATTR, "") == "drawing_view"

    def drawing_view_data(self, camera):
        if not self.is_drawing_view(camera):
            return {}
        camera = _long_name(camera)
        index = 0
        if cmds.attributeQuery(DRAWING_VIEW_INDEX_ATTR, node=camera, exists=True):
            try:
                index = int(cmds.getAttr(camera + "." + DRAWING_VIEW_INDEX_ATTR))
            except Exception:
                index = 0
        return {
            "node": camera,
            "name": _short_name(camera),
            "label": _get_string_attr(camera, DRAWING_VIEW_LABEL_ATTR, "") or "Pencil View {0}".format(index or 1),
            "index": index,
            "source": _get_string_attr(camera, DRAWING_VIEW_SOURCE_ATTR, ""),
        }

    def drawing_views(self):
        if not MAYA_AVAILABLE:
            return []
        views = []
        for node in self._tagged_transforms(DRAWING_VIEW_ATTR, "drawing_view"):
            data = self.drawing_view_data(node)
            if data:
                views.append(data)
        views.sort(key=lambda item: (item.get("index", 0), item.get("label", ""), item.get("name", "")))
        return views

    def rename_drawing_view(self, camera, label):
        """Rename a saved Pencil View without changing its camera or layer links."""
        if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera) or not self.is_drawing_view(camera):
            return False, "Choose a saved Pencil View first."
        label = (label or "").strip()
        if not label:
            return False, "Enter a name for the saved Pencil View."
        label = label[:64]
        identity = _long_name(camera)
        folded = label.casefold()
        for view in self.drawing_views():
            if _long_name(view.get("node") or "") == identity:
                continue
            if str(view.get("label") or "").strip().casefold() == folded:
                return False, "That Pencil View name is already in use."
        _set_string_attr(identity, DRAWING_VIEW_LABEL_ATTR, label)
        self._status("Renamed saved drawing view: {0}.".format(label))
        return True, label

    def _copy_camera_settings(self, source_camera, target_camera):
        source_shape = _camera_shape(source_camera)
        target_shape = _camera_shape(target_camera)
        if not source_shape or not target_shape:
            return
        for attr_name in (
            "focalLength",
            "horizontalFilmAperture",
            "verticalFilmAperture",
            "lensSqueezeRatio",
            "filmFit",
            "filmFitOffset",
            "nearClipPlane",
            "farClipPlane",
            "orthographic",
            "orthographicWidth",
            "overscan",
            "panZoomEnabled",
            "horizontalPan",
            "verticalPan",
            "zoom",
            "cameraScale",
        ):
            try:
                if cmds.objExists(source_shape + "." + attr_name) and cmds.objExists(target_shape + "." + attr_name):
                    cmds.setAttr(target_shape + "." + attr_name, cmds.getAttr(source_shape + "." + attr_name))
            except Exception:
                continue

    def create_drawing_view_from_current_view(self, name=None, switch=True, source_camera=None):
        if not MAYA_AVAILABLE:
            return ""
        source_camera = source_camera or _current_camera()
        if not source_camera or not cmds.objExists(source_camera):
            self._status("No active Maya camera is available to save.")
            return ""
        source_camera = _long_name(source_camera)
        if cmds.nodeType(source_camera) == "camera":
            parents = cmds.listRelatives(source_camera, parent=True, fullPath=True) or []
            source_camera = parents[0] if parents else source_camera
        if self.is_drawing_view(source_camera):
            if switch:
                self.switch_to_drawing_view(source_camera)
            return source_camera

        index = max([int(item.get("index", 0)) for item in self.drawing_views()] or [0]) + 1
        label = (name or "Pencil View {0}".format(index)).strip() or "Pencil View {0}".format(index)
        camera, _shape = cmds.camera(name="amirPencilView{0}_CAM".format(index))
        world_matrix = cmds.xform(source_camera, query=True, matrix=True, worldSpace=True)
        camera = _parent_if_needed(camera, self.root())
        camera = _long_name(camera)
        cmds.xform(camera, matrix=world_matrix, worldSpace=True)
        self._copy_camera_settings(source_camera, camera)
        _set_string_attr(camera, DRAWING_VIEW_ATTR, "drawing_view")
        _set_string_attr(camera, DRAWING_VIEW_LABEL_ATTR, label[:64])
        _set_string_attr(camera, DRAWING_VIEW_SOURCE_ATTR, source_camera)
        _ensure_attr(camera, DRAWING_VIEW_INDEX_ATTR, "long", index)
        cmds.setAttr(camera + "." + DRAWING_VIEW_INDEX_ATTR, index)
        shape = _camera_shape(camera)
        if shape:
            _set_string_attr(shape, DRAWING_VIEW_ATTR, "drawing_view")
        try:
            cmds.setAttr(camera + ".visibility", False)
        except Exception:
            pass
        if switch:
            self.switch_to_drawing_view(camera)
        self._status("Saved drawing view: {0}.".format(label[:64]))
        return camera

    def switch_to_drawing_view(self, camera):
        if not self.is_drawing_view(camera):
            self._status("Choose a saved Pencil View.")
            return ""
        camera = _long_name(camera)
        if not _set_camera_for_model_panels(camera):
            self._status("Could not switch the active viewport to the saved drawing view.")
            return ""
        # Discover and migrate Pencil layers once, then reuse that snapshot for
        # active-layer selection and camera-scope visibility evaluation.
        scope_layers = self.layers(include_count=False)
        self.active_layer_for_camera(camera=camera, layer_data=scope_layers)
        # The camera assignment above changes the scope identity. Let the
        # normal dirty/identity guard skip a no-op reselect of the same Pencil
        # View instead of forcing every layer through DAG evaluation again.
        self.refresh_camera_scope(layer_data=scope_layers)
        self._status("Viewing through {0}.".format(self.drawing_view_data(camera).get("label", _short_name(camera))))
        return camera

    def ensure_drawing_view_for_drawing(self, preferred_layer=None, camera=None):
        if not MAYA_AVAILABLE:
            return {"camera": "", "layer": "", "created": False}
        camera = camera or _current_camera()
        created = False
        if not self.is_drawing_view(camera):
            camera = self.create_drawing_view_from_current_view(switch=True, source_camera=camera)
            created = bool(camera)
        if not camera:
            return {"camera": "", "layer": "", "created": created}
        layer = self.active_layer_for_camera(preferred_layer=preferred_layer, camera=camera)
        return {"camera": _long_name(camera), "layer": layer, "created": created}

    def set_active_layer(self, layer_node):
        root = self.root()
        state = _get_json_attr(root, ROOT_STATE_ATTR, {}) or {}
        state["active_layer"] = _long_name(layer_node)
        _set_json_attr(root, ROOT_STATE_ATTR, state)

    def shape_library(self):
        library = {name: dict(data) for name, data in SHAPE_LIBRARY.items()}
        if MAYA_AVAILABLE:
            custom = _get_json_attr(self.root(), SHAPE_PRESETS_ATTR, {}) or {}
            for name, data in custom.items():
                if isinstance(data, dict) and data.get("points"):
                    entry = dict(data)
                    entry["user"] = True
                    library[name] = entry
        return library

    def shape_presets(self):
        if not MAYA_AVAILABLE:
            return {}
        return _get_json_attr(self.root(), SHAPE_PRESETS_ATTR, {}) or {}

    def save_shape_preset(self, name, mark=None):
        name = (name or "").strip()
        if not name:
            return False, "Enter a preset name."
        mark = mark or (self.selected_marks() or [None])[0]
        if not mark or not cmds.objExists(mark):
            return False, "Select one pencil mark to save as a preset."
        data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
        points = data.get("points") or []
        if len(points) < 2:
            return False, "Selected mark has no reusable points."
        presets = self.shape_presets()
        presets[name[:48]] = {
            "tool": data.get("tool", "Pencil"),
            "points": [[float(point[0]), float(point[1]), 0.0] for point in points],
            "source": _short_name(mark),
        }
        _set_json_attr(self.root(), SHAPE_PRESETS_ATTR, presets)
        self._status("Shape preset saved: {0}.".format(name[:48]))
        return True, "Shape preset saved: {0}.".format(name[:48])

    def delete_shape_preset(self, name):
        presets = self.shape_presets()
        if name not in presets:
            return False, "User preset not found."
        presets.pop(name, None)
        _set_json_attr(self.root(), SHAPE_PRESETS_ATTR, presets)
        self._status("Shape preset deleted: {0}.".format(name))
        return True, "Shape preset deleted: {0}.".format(name)

    def create_shape_preset(self, name, layer_node=None, color=(1.0, 0.05, 0.05), size=3.0, opacity=1.0, camera_note=False, camera_snap=True, one_frame=False):
        # `shape_library()` combines built-in shapes with user-saved presets.
        preset = self.shape_library().get(name)
        if not preset:
            return ""
        return self.create_mark(
            tool=preset.get("tool", "Pencil"),
            layer_node=layer_node,
            color=color,
            size=size,
            opacity=opacity,
            camera_note=camera_note,
            camera_snap=camera_snap,
            points=list(preset.get("points") or []),
            one_frame=one_frame,
        )

    def swatches(self):
        if not MAYA_AVAILABLE:
            return [list(color) for color in DEFAULT_COLORS.values()]
        values = _get_json_attr(self.root(), SWATCHES_ATTR, None)
        if not isinstance(values, list) or not values:
            values = [list(color) for color in DEFAULT_COLORS.values()]
            _set_json_attr(self.root(), SWATCHES_ATTR, values)
        return [list(value) for value in values if isinstance(value, (list, tuple)) and len(value) == 3]

    def save_swatch(self, color):
        normalized = [max(0.0, min(1.0, float(value))) for value in (color or (1.0, 0.05, 0.05))]
        swatches = self.swatches()
        swatches = [item for item in swatches if any(abs(float(item[index]) - normalized[index]) > 1.0e-5 for index in range(3))]
        swatches.insert(0, normalized)
        swatches = swatches[:12]
        if MAYA_AVAILABLE:
            _set_json_attr(self.root(), SWATCHES_ATTR, swatches)
        self._status("Saved pencil color swatch.")
        return swatches

    def create_shape_library_mark(self, name, layer_node=None, color=(1.0, 0.05, 0.05), size=3.0, opacity=1.0, camera_note=False, camera_snap=True, one_frame=False):
        return self.create_shape_preset(name, layer_node, color, size, opacity, camera_note, camera_snap, one_frame)

    def _camera_space_anchor(self, camera):
        """Return a visible transform constrained to camera space.

        Camera transforms are normally hidden in Maya. Drawing layers must not
        inherit that hidden visibility, so they live below this constrained
        transform rather than directly below the camera transform.
        """
        camera = _long_name(camera) if camera and cmds.objExists(camera) else ""
        if not camera:
            return ""
        # Saved-view switches call ``layers()`` more than once. Do not scan
        # every transform in a production character rig for each Pencil layer;
        # the marker query returns only Pencil-owned anchors.
        for node in self._tagged_transforms(CAMERA_SPACE_ANCHOR_ATTR, "camera_space_anchor"):
            if _get_string_attr(node, CAMERA_SPACE_ANCHOR_CAMERA_ATTR, "") == camera:
                return node
        anchor_name = "amirPencil_{0}_CameraSpace_GRP".format(_safe_name(camera))
        anchor = cmds.createNode("transform", name=anchor_name)
        anchor = _parent_if_needed(anchor, self.root())
        anchor = _long_name(anchor)
        _set_string_attr(anchor, CAMERA_SPACE_ANCHOR_ATTR, "camera_space_anchor")
        _set_string_attr(anchor, CAMERA_SPACE_ANCHOR_CAMERA_ATTR, camera)
        cmds.parentConstraint(camera, anchor, maintainOffset=False)
        return anchor

    def _migrate_layer_to_camera_anchor(self, layer_node):
        """Move legacy camera-parented layers below a visible camera-space anchor."""
        if not layer_node or not cmds.objExists(layer_node):
            return layer_node
        layer_node = _long_name(layer_node)
        camera = _get_string_attr(layer_node, "animatorsPencilCamera", "")
        if not camera or not cmds.objExists(camera):
            return layer_node
        anchor = self._camera_space_anchor(camera)
        if not anchor:
            return layer_node
        current_parent = (cmds.listRelatives(layer_node, parent=True, fullPath=True) or [""])[0]
        if current_parent == anchor:
            self._migrate_camera_space_alignment(layer_node)
            return layer_node
        if current_parent == _long_name(camera):
            # Preserve existing local camera-space offsets for old Pencil data.
            layer_node = cmds.parent(layer_node, anchor, relative=True)[0]
        else:
            world_matrix = cmds.xform(layer_node, query=True, matrix=True, worldSpace=True)
            layer_node = cmds.parent(layer_node, anchor)[0]
            cmds.xform(layer_node, matrix=world_matrix, worldSpace=True)
        # Affected version-1 layers may already be below the anchor but have
        # an inverse camera rotation from the old absolute-parent operation.
        # Normalize them once, preserving their camera-space depth and order.
        self._migrate_camera_space_alignment(layer_node)
        return _long_name(layer_node)

    def _migrate_camera_space_alignment(self, layer_node):
        """Normalize one legacy layer without clobbering later user edits."""
        if not layer_node or not cmds.objExists(layer_node):
            return False
        marker = layer_node + "." + CAMERA_SPACE_ALIGNMENT_ATTR
        try:
            current_version = int(cmds.getAttr(marker)) if cmds.objExists(marker) else 0
        except Exception:
            current_version = 0
        data = _get_json_attr(layer_node, "animatorsPencilLayerData", {}) or {}
        try:
            data_version = int(data.get("version", 0))
        except Exception:
            data_version = 0
        if current_version >= LAYER_VERSION and data_version >= LAYER_VERSION:
            return False
        lock_order = (
            "rotate",
            "scale",
            "rotateX",
            "rotateY",
            "rotateZ",
            "scaleX",
            "scaleY",
            "scaleZ",
        )
        lock_state = {}
        try:
            for attr_name in lock_order:
                attr = layer_node + "." + attr_name
                lock_state[attr_name] = bool(cmds.getAttr(attr, lock=True))
            # Locked Pencil layers lock the child channels (rx/ry/rz and
            # sx/sy/sz), while some legacy scenes can lock the compound too.
            # Unlock both forms before normalizing, then restore the exact
            # original lock state below.
            for attr_name in lock_order:
                try:
                    cmds.setAttr(layer_node + "." + attr_name, lock=False)
                except Exception:
                    if lock_state.get(attr_name):
                        raise
            cmds.setAttr(layer_node + ".rotate", 0.0, 0.0, 0.0, type="double3")
            cmds.setAttr(layer_node + ".scale", 1.0, 1.0, 1.0, type="double3")
        except Exception:
            return False
        finally:
            # Restore child locks before compound locks so Maya never blocks
            # restoration of an individually locked channel.
            restore_order = lock_order[2:] + lock_order[:2]
            for attr_name in restore_order:
                try:
                    cmds.setAttr(layer_node + "." + attr_name, lock=bool(lock_state.get(attr_name, False)))
                except Exception:
                    pass
        _ensure_attr(layer_node, CAMERA_SPACE_ALIGNMENT_ATTR, "long", LAYER_VERSION)
        cmds.setAttr(marker, LAYER_VERSION)
        data["version"] = LAYER_VERSION
        _set_json_attr(layer_node, "animatorsPencilLayerData", data)
        return True

    def create_layer(self, name="Pencil Layer", camera=None, state="Animation"):
        if not MAYA_AVAILABLE:
            return ""
        camera = camera or _current_camera()
        if camera and cmds.objExists(camera):
            camera = _long_name(camera)
        order = len(self.layers(include_count=False))
        layer_name = "amirPencil_{0}_{1}_LYR".format(_safe_name(camera), _safe_name(name))
        layer = cmds.createNode("transform", name=layer_name)
        if camera and cmds.objExists(camera):
            anchor = self._camera_space_anchor(camera)
            if anchor:
                # Keep the new layer's local rotation at identity.  The
                # default absolute parent mode preserves the layer's world
                # matrix, which means Maya writes the inverse camera rotation
                # into the child.  The anchor then cancels that rotation and
                # stamped curves lie on the world XY grid instead of facing
                # the saved Pencil View.  Relative parenting keeps the layer
                # in camera space so every stamp and freehand mark shares the
                # active camera's screen plane.
                layer = cmds.parent(layer, anchor, relative=True)[0]
        layer = _long_name(layer)
        cmds.setAttr(layer + ".translate", 0, 0, -10.0 - (order * 0.03), type="double3")
        _set_string_attr(layer, LAYER_MARKER_ATTR, "layer")
        _set_string_attr(layer, "animatorsPencilCamera", camera or "")
        _set_string_attr(layer, "animatorsPencilLayerState", state)
        _ensure_attr(layer, "animatorsPencilLayerOrder", "long", order)
        _ensure_attr(layer, "animatorsPencilLayerLocked", "bool", False)
        _ensure_attr(layer, CAMERA_SPACE_ALIGNMENT_ATTR, "long", LAYER_VERSION)
        _ensure_attr(layer, LAYER_USER_VISIBILITY_ATTR, "bool", True)
        _ensure_attr(layer, LAYER_OPACITY_ATTR, "double", 1.0)
        data = {"version": LAYER_VERSION, "name": name, "camera": camera, "state": state, "order": order, "locked": False, "opacity": 1.0}
        _set_json_attr(layer, "animatorsPencilLayerData", data)
        self._camera_scope_dirty = True
        self.set_active_layer(layer)
        self._status("Layer created: {0}".format(name))
        return layer

    def rename_layer(self, layer_node, name):
        name = (name or "").strip()
        if not layer_node or not cmds.objExists(layer_node) or not name:
            return False
        data = self.layer_data(layer_node)
        data["name"] = name[:64]
        _set_json_attr(layer_node, "animatorsPencilLayerData", data)
        self._status("Layer renamed: {0}".format(data["name"]))
        return True

    def delete_layer(self, layer_node):
        if layer_node and cmds.objExists(layer_node):
            cmds.delete(layer_node)
            self._camera_scope_dirty = True
            self._status("Layer deleted.")

    def set_layer_state(self, layer_node, state):
        if not layer_node or not cmds.objExists(layer_node):
            return
        locked = state == "Locked"
        _set_string_attr(layer_node, "animatorsPencilLayerState", state)
        if cmds.objExists(layer_node + ".animatorsPencilLayerLocked"):
            cmds.setAttr(layer_node + ".animatorsPencilLayerLocked", locked)
        data = self.layer_data(layer_node)
        data["state"] = state
        data["locked"] = locked
        _set_json_attr(layer_node, "animatorsPencilLayerData", data)
        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
            try:
                cmds.setAttr("{0}.{1}".format(layer_node, attr), lock=locked)
            except Exception:
                pass
        self._camera_scope_dirty = True

    def set_layer_visibility(self, layer_node, visible):
        if not layer_node or not cmds.objExists(layer_node):
            return False
        try:
            _ensure_attr(layer_node, LAYER_USER_VISIBILITY_ATTR, "bool", bool(visible))
            cmds.setAttr(layer_node + "." + LAYER_USER_VISIBILITY_ATTR, bool(visible))
        except Exception:
            return False
        if not self._apply_layer_visibility(layer_node):
            return False
        self._camera_scope_dirty = True
        self._status("Layer {0}: {1}".format("shown" if visible else "hidden", self.layer_data(layer_node).get("name", _short_name(layer_node))))
        return True

    def set_layer_opacity(self, layer_node, opacity):
        if not layer_node or not cmds.objExists(layer_node):
            return False
        value = _clamp_opacity(opacity)
        try:
            _ensure_attr(layer_node, LAYER_OPACITY_ATTR, "double", value)
            cmds.setAttr(layer_node + "." + LAYER_OPACITY_ATTR, value)
            data = self.layer_data(layer_node, include_count=False)
            data["opacity"] = value
            data["opacity_percent"] = int(round(value * 100.0))
            _set_json_attr(layer_node, "animatorsPencilLayerData", data)
            for mark in self.marks(layer_node):
                _set_mark_effective_opacity(mark, value)
            self._force_layer_display_evaluation(layer_node)
            self._status("Layer {0} opacity: {1}%".format(data.get("name", _short_name(layer_node)), int(round(value * 100.0))))
            return True
        except Exception:
            return False

    def set_all_layers_visibility(self, visible):
        changed = 0
        for layer in self.layers(include_count=False):
            if self.set_layer_visibility(layer.get("node"), visible):
                changed += 1
        self._status("{0} pencil layer(s) {1}.".format(changed, "shown" if visible else "hidden"))
        return changed

    def move_layer_order(self, layer_node, delta):
        layers = self.layers(include_count=False)
        nodes = [item["node"] for item in layers]
        if layer_node not in nodes:
            return
        index = nodes.index(layer_node)
        new_index = max(0, min(len(nodes) - 1, index + delta))
        nodes.insert(new_index, nodes.pop(index))
        for order, node in enumerate(nodes):
            if cmds.objExists(node + ".animatorsPencilLayerOrder"):
                cmds.setAttr(node + ".animatorsPencilLayerOrder", order)
            data = self.layer_data(node)
            data["order"] = order
            _set_json_attr(node, "animatorsPencilLayerData", data)
            cmds.setAttr(node + ".translateZ", -10.0 - (order * 0.03))

    def move_layer_to_camera(self, layer_node, camera=None):
        camera = camera or _current_camera()
        if not layer_node or not camera or not cmds.objExists(layer_node) or not cmds.objExists(camera):
            return
        camera = _long_name(camera)
        world_matrix = cmds.xform(layer_node, query=True, matrix=True, worldSpace=True)
        anchor = self._camera_space_anchor(camera)
        if not anchor:
            return
        layer_node = cmds.parent(layer_node, anchor)[0]
        layer_node = _long_name(layer_node)
        cmds.xform(layer_node, matrix=world_matrix, worldSpace=True)
        _set_string_attr(layer_node, "animatorsPencilCamera", camera)
        data = self.layer_data(layer_node)
        data["camera"] = camera
        _set_json_attr(layer_node, "animatorsPencilLayerData", data)
        self._camera_scope_dirty = True
        self._status("Layer moved to camera: {0}".format(camera))

    def camera_notes_camera(self, create=True):
        if not MAYA_AVAILABLE:
            return ""
        for node_name in cmds.ls(type="transform", long=True) or []:
            if _get_string_attr(node_name, CAMERA_NOTES_ATTR, "") == "camera_notes":
                return node_name
        matches = cmds.ls(CAMERA_NOTES_NAME, long=True) or []
        if matches:
            return matches[0]
        if not create:
            return ""
        camera_transform, camera_shape = cmds.camera(name=CAMERA_NOTES_NAME)
        if camera_shape != CAMERA_NOTES_SHAPE_NAME:
            try:
                camera_shape = cmds.rename(camera_shape, CAMERA_NOTES_SHAPE_NAME)
            except Exception:
                pass
        try:
            camera_transform = _parent_if_needed(camera_transform, self.root())
        except Exception:
            pass
        camera_transform = _long_name(camera_transform)
        _set_string_attr(camera_transform, CAMERA_NOTES_ATTR, "camera_notes")
        shape = _camera_shape(camera_transform)
        if shape:
            _set_string_attr(shape, CAMERA_NOTES_ATTR, "camera_notes")
        return camera_transform

    def key_camera_notes_to_current_view(self, snap=True, switch_to_camera=False):
        if not MAYA_AVAILABLE:
            return ""
        source_camera = _current_camera()
        notes_camera = self.camera_notes_camera(create=True)
        if not notes_camera or not cmds.objExists(notes_camera):
            self._status("Could not create Camera Notes camera.")
            return ""
        if source_camera and cmds.objExists(source_camera) and _short_name(source_camera) != _short_name(notes_camera):
            try:
                translation = cmds.xform(source_camera, query=True, worldSpace=True, translation=True)
                rotation = cmds.xform(source_camera, query=True, worldSpace=True, rotation=True)
                cmds.xform(notes_camera, worldSpace=True, translation=translation)
                cmds.xform(notes_camera, worldSpace=True, rotation=rotation)
            except Exception:
                pass
            source_shape = _camera_shape(source_camera)
            notes_shape = _camera_shape(notes_camera)
            if source_shape and notes_shape:
                for attr_name in ("focalLength", "horizontalFilmAperture", "verticalFilmAperture", "nearClipPlane", "farClipPlane"):
                    try:
                        if cmds.objExists(source_shape + "." + attr_name) and cmds.objExists(notes_shape + "." + attr_name):
                            cmds.setAttr(notes_shape + "." + attr_name, cmds.getAttr(source_shape + "." + attr_name))
                    except Exception:
                        continue
        frame = _current_frame()
        for attr_name in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
            try:
                cmds.setKeyframe(notes_camera, attribute=attr_name, time=frame)
            except Exception:
                pass
        notes_shape = _camera_shape(notes_camera)
        if notes_shape:
            for attr_name in ("focalLength", "horizontalFilmAperture", "verticalFilmAperture"):
                try:
                    cmds.setKeyframe(notes_shape, attribute=attr_name, time=frame)
                except Exception:
                    pass
        if snap:
            for node_name in [notes_camera, notes_shape]:
                if not node_name:
                    continue
                try:
                    cmds.keyTangent(node_name, time=(frame, frame), edit=True, inTangentType="linear", outTangentType="step")
                except Exception:
                    pass
        if switch_to_camera:
            _set_camera_for_model_panels(notes_camera)
        self._status("Camera Notes keyed to current view on frame {0}.".format(frame))
        return notes_camera

    def switch_to_camera_notes(self):
        camera = self.camera_notes_camera(create=True)
        if camera and _set_camera_for_model_panels(camera):
            self._status("Viewing through Camera Notes camera.")
        return camera

    def marks(self, layer_node=None):
        if not MAYA_AVAILABLE:
            return []
        layer_node = layer_node or self.active_layer()
        if not layer_node or not cmds.objExists(layer_node):
            return []
        layer_node = _long_name(layer_node)
        # A marquee transform box temporarily parents its selected fragments so
        # Maya can move and scale them as one screen-aligned selection. Marks
        # must therefore remain discoverable below the layer, not only as its
        # direct children.
        children = cmds.listRelatives(layer_node, allDescendents=True, type="transform", fullPath=True) or []
        return [child for child in children if _get_string_attr(child, MARK_MARKER_ATTR, "") == "mark"]

    def selected_marks(self):
        if not MAYA_AVAILABLE:
            return []
        selected = cmds.ls(selection=True, type="transform", long=True) or []
        marks = []
        for node in selected:
            if _get_string_attr(node, MARK_MARKER_ATTR, "") == "mark":
                marks.append(node)
                continue
            if not bool(_get_string_attr(node, MARQUEE_TRANSFORM_BOX_ATTR, "")):
                continue
            descendants = cmds.listRelatives(node, allDescendents=True, type="transform", fullPath=True) or []
            marks.extend(
                child for child in descendants
                if _get_string_attr(child, MARK_MARKER_ATTR, "") == "mark"
            )
        return list(dict.fromkeys(marks))

    def _mark_node(self, node, layer_node, tool, color, opacity, size, frame=None, one_frame=False):
        node = _long_name(node)
        layer_node = _long_name(layer_node)
        frame = _current_frame() if frame is None else int(frame)
        _set_string_attr(node, MARK_MARKER_ATTR, "mark")
        data = {
            "version": LAYER_VERSION,
            "tool": tool,
            "layer": layer_node,
            "frame": frame,
            "color": list(color),
            "opacity": float(opacity),
            "size": float(size),
            "oneFrame": bool(one_frame),
        }
        _set_json_attr(node, "animatorsPencilMarkData", data)
        _ensure_attr(node, "animatorsPencilFrame", "long", frame)
        cmds.setAttr(node + ".animatorsPencilFrame", frame)
        self._key_mark_visibility(node, layer_node, frame, one_frame=one_frame)
        _set_mark_effective_opacity(node, self._layer_opacity(layer_node))
        return node

    def _key_mark_visibility(self, node, layer_node, frame, one_frame=False):
        layer_state = _get_string_attr(layer_node, "animatorsPencilLayerState", "Animation")
        if layer_state == "Static":
            cmds.setAttr(node + ".visibility", True)
            return
        cmds.setKeyframe(node, attribute="visibility", time=frame - 1, value=0, shape=False)
        cmds.setKeyframe(node, attribute="visibility", time=frame, value=1, shape=False)
        if one_frame:
            cmds.setKeyframe(node, attribute="visibility", time=frame + 1, value=0, shape=False)
        key_end = frame + 1 if one_frame else frame
        cmds.keyTangent(
            node,
            attribute="visibility",
            time=(frame - 1, key_end),
            outTangentType="step",
        )
        # Maya can retain the pre-key `False` cache at the current frame until
        # the graph is dirtied, making a newly drawn stroke exist but vanish.
        cmds.dgdirty(node)

    def _tool_points(self, tool):
        if tool == "Brush":
            return [(-1.0, -0.15, 0.0), (-0.45, 0.25, 0.0), (0.1, -0.05, 0.0), (0.75, 0.28, 0.0)]
        if tool == "Line":
            return [(-0.8, 0.0, 0.0), (0.8, 0.0, 0.0)]
        if tool == "Arrow":
            return [(-0.9, 0.0, 0.0), (0.75, 0.0, 0.0), (0.45, 0.22, 0.0), (0.75, 0.0, 0.0), (0.45, -0.22, 0.0)]
        if tool == "Rectangle":
            return [(-0.7, -0.45, 0.0), (0.7, -0.45, 0.0), (0.7, 0.45, 0.0), (-0.7, 0.45, 0.0), (-0.7, -0.45, 0.0)]
        if _canonical_shape_tool(tool) == "Circle":
            return _shape_points_from_drag("Circle", (-0.72, -0.72, 0.0), (0.72, 0.72, 0.0))
        if _canonical_shape_tool(tool) == "Oval":
            return _shape_points_from_drag("Oval", (-0.72, -0.45, 0.0), (0.72, 0.45, 0.0))
        if _canonical_shape_tool(tool) == "Star":
            return _shape_points_from_drag("Star", (-0.8, -0.8, 0.0), (0.8, 0.8, 0.0))
        return [(-0.9, 0.0, 0.0), (-0.55, 0.18, 0.0), (-0.1, -0.1, 0.0), (0.35, 0.24, 0.0), (0.9, 0.0, 0.0)]

    def _tool_points_from_drag(self, tool, start_point, end_point):
        sx, sy = float(start_point[0]), float(start_point[1])
        ex, ey = float(end_point[0]), float(end_point[1])
        if abs(ex - sx) < 0.05 and abs(ey - sy) < 0.05:
            ex = sx + 0.35
            ey = sy - 0.25
        min_x, max_x = min(sx, ex), max(sx, ex)
        min_y, max_y = min(sy, ey), max(sy, ey)
        cx = (sx + ex) * 0.5
        cy = (sy + ey) * 0.5
        tool = tool or "Pencil"
        if tool == "Line":
            return [(sx, sy, 0.0), (ex, ey, 0.0)]
        if tool == "Arrow":
            dx, dy = ex - sx, ey - sy
            length = max(math.sqrt((dx * dx) + (dy * dy)), 0.001)
            ux, uy = dx / length, dy / length
            px, py = -uy, ux
            head = min(length * 0.28, 0.45)
            left = (ex - (ux * head) + (px * head * 0.55), ey - (uy * head) + (py * head * 0.55), 0.0)
            right = (ex - (ux * head) - (px * head * 0.55), ey - (uy * head) - (py * head * 0.55), 0.0)
            return [(sx, sy, 0.0), (ex, ey, 0.0), left, (ex, ey, 0.0), right]
        if tool == "Rectangle":
            return [(min_x, min_y, 0.0), (max_x, min_y, 0.0), (max_x, max_y, 0.0), (min_x, max_y, 0.0), (min_x, min_y, 0.0)]
        if _canonical_shape_tool(tool) in ("Circle", "Oval", "Star"):
            return _shape_points_from_drag(tool, (sx, sy, 0.0), (ex, ey, 0.0), minimum_span=0.05)
        if tool == "Brush":
            return [(sx, sy, 0.0), ((sx + cx) * 0.5, cy + 0.15, 0.0), (cx, cy - 0.12, 0.0), ((ex + cx) * 0.5, cy + 0.18, 0.0), (ex, ey, 0.0)]
        return [(sx, sy, 0.0), ((sx + cx) * 0.5, cy + 0.1, 0.0), (cx, cy - 0.08, 0.0), ((ex + cx) * 0.5, cy + 0.12, 0.0), (ex, ey, 0.0)]

    def _tool_screen_points_from_drag(self, tool, start_point, end_point):
        """Build viewport-aligned shape points before mapping them to the layer.

        A rectangle assembled from only two layer-space corners can become a
        rhombus when the active camera has film roll or another projected
        transform. Mapping every screen-space corner preserves what the user
        actually dragged in the viewport.
        """
        sx, sy = float(start_point[0]), float(start_point[1])
        ex, ey = float(end_point[0]), float(end_point[1])
        if abs(ex - sx) < 2.0 and abs(ey - sy) < 2.0:
            ex = sx + 24.0
            ey = sy - 18.0
        min_x, max_x = min(sx, ex), max(sx, ex)
        min_y, max_y = min(sy, ey), max(sy, ey)
        cx = (sx + ex) * 0.5
        cy = (sy + ey) * 0.5
        tool = tool or "Line"
        if tool == "Line":
            return [(sx, sy, 0.0), (ex, ey, 0.0)]
        if tool == "Arrow":
            dx, dy = ex - sx, ey - sy
            length = max(math.sqrt((dx * dx) + (dy * dy)), 0.001)
            ux, uy = dx / length, dy / length
            px, py = -uy, ux
            head = min(length * 0.28, 32.0)
            left = (ex - (ux * head) + (px * head * 0.55), ey - (uy * head) + (py * head * 0.55), 0.0)
            right = (ex - (ux * head) - (px * head * 0.55), ey - (uy * head) - (py * head * 0.55), 0.0)
            return [(sx, sy, 0.0), (ex, ey, 0.0), left, (ex, ey, 0.0), right]
        if tool == "Rectangle":
            return [(min_x, min_y, 0.0), (max_x, min_y, 0.0), (max_x, max_y, 0.0), (min_x, max_y, 0.0), (min_x, min_y, 0.0)]
        if _canonical_shape_tool(tool) in ("Circle", "Oval", "Star"):
            return _shape_points_from_drag(tool, (sx, sy, 0.0), (ex, ey, 0.0), minimum_span=2.0)
        return [(sx, sy, 0.0), (ex, ey, 0.0)]

    def _tool_points_from_screen_drag(self, tool, layer_node, start_point, end_point):
        return self._tool_points_from_screen_drag_cached(tool, layer_node, start_point, end_point, None)

    def _tool_points_from_screen_drag_cached(self, tool, layer_node, start_point, end_point, mapping_cache=None):
        return [
            _screen_to_layer_point(layer_node, point, mapping_cache=mapping_cache)
            for point in self._tool_screen_points_from_drag(tool, start_point, end_point)
        ]

    def _run_without_undo(self, callback):
        undo_enabled = False
        try:
            undo_enabled = bool(cmds.undoInfo(query=True, state=True))
        except Exception:
            pass
        try:
            if undo_enabled:
                cmds.undoInfo(stateWithoutFlush=False)
            return callback()
        finally:
            if undo_enabled:
                cmds.undoInfo(stateWithoutFlush=True)

    def _begin_drag_preview_session(self):
        self._end_drag_preview_session()
        self._cancel_drag_preview_refresh()
        self._drag_preview_undo_suppressed = False
        try:
            if bool(cmds.undoInfo(query=True, state=True)):
                cmds.undoInfo(stateWithoutFlush=False)
                self._drag_preview_undo_suppressed = True
        except Exception:
            self._drag_preview_undo_suppressed = False

    def _end_drag_preview_session(self):
        if not self._drag_preview_undo_suppressed:
            return
        try:
            cmds.undoInfo(stateWithoutFlush=True)
        finally:
            self._drag_preview_undo_suppressed = False

    def _cancel_drag_preview_refresh(self):
        """Invalidate a queued preview repaint after a gesture ends."""
        self._drag_preview_refresh_generation = int(getattr(self, "_drag_preview_refresh_generation", 0)) + 1
        self._drag_preview_refresh_pending = False

    def _append_drag_sample(self, layer, screen_point=None, layer_point=None, minimum_distance=0.025):
        """Keep one distinct freehand sample without rebuilding a curve.

        ``draggerContext`` can skip mouse-move callbacks while Maya is busy.
        Both its callback and the lightweight cursor sampler flow through this
        helper, so a late sample extends the existing stroke instead of making
        a second or backward path.
        """
        if self._drag_options.get("tool") not in STROKE_PATH_TOOLS:
            return False
        if screen_point and (
            not self._drag_screen_points
            or tuple(screen_point[:2]) != tuple(self._drag_screen_points[-1][:2])
        ):
            self._drag_screen_points.append(screen_point)
            if len(self._drag_screen_points) > 8192:
                self._drag_screen_points = self._drag_screen_points[::2]
        if layer_point is None and screen_point:
            layer_point = _screen_to_layer_point(layer, screen_point, mapping_cache=self._drag_mapping_cache)
        if layer_point is None:
            return False
        minimum_distance = max(0.0, float(minimum_distance))
        if self._drag_points and self._point_distance_squared(layer_point, self._drag_points[-1]) < minimum_distance ** 2.0:
            return False
        self._drag_points.append(layer_point)
        # Very long drags can otherwise retain tens of thousands of points and
        # make each preview replacement progressively more expensive. Keep the
        # path accurate at normal scale while bounding worst-case memory and
        # curve rebuild cost.
        if len(self._drag_points) > 8192:
            self._drag_points = self._drag_points[::2]
        return True

    def _capture_drag_cursor_tail(self, layer=None):
        """Sample the actual cursor in the cached draw widget after a hitch."""
        if not getattr(self, "_drag_capture_active", False):
            return False
        layer = layer or self._drag_options.get("layer_node") or self.active_layer()
        if not layer or not cmds.objExists(layer):
            return False
        cache = self._drag_mapping_cache or {}
        _view, cursor_point = _active_m3dview_cursor_point(cache.get("view"), cache.get("widget"))
        if not cursor_point:
            return False
        # ``cursor_point`` is already in M3dView port pixels; pass ``None`` to
        # the mapper so it takes its port-pixel cursor branch instead of
        # treating those values as draggerContext logical-widget coordinates.
        layer_point = _screen_to_layer_point(layer, None, mapping_cache=cache)
        appended = self._append_drag_sample(layer, screen_point=cursor_point, layer_point=layer_point)
        if appended and self._drag_options.get("tool") in ("Pencil", "Brush"):
            # Reuse the normal 45 Hz preview throttle. Cursor recovery stays
            # visible without adding an unbounded redraw path during a hitch.
            self._update_drag_preview(self._drag_points)
        elif appended and self._drag_options.get("tool") == "Eraser":
            self._update_eraser_preview(self._drag_points)
        return appended

    def _stop_drag_cursor_capture(self):
        self._drag_capture_active = False
        self._drag_capture_generation = int(getattr(self, "_drag_capture_generation", 0)) + 1

    def _start_drag_cursor_capture(self):
        self._stop_drag_cursor_capture()
        if self._drag_options.get("tool") not in STROKE_PATH_TOOLS:
            return
        if not (QtCore and getattr(QtCore, "QTimer", None)):
            return
        self._drag_capture_active = True
        generation = self._drag_capture_generation

        def sample_cursor():
            if (
                generation != getattr(self, "_drag_capture_generation", 0)
                or not getattr(self, "_drag_capture_active", False)
            ):
                return
            self._capture_drag_cursor_tail()
            try:
                QtCore.QTimer.singleShot(int(self._drag_capture_interval_ms), sample_cursor)
            except Exception:
                self._stop_drag_cursor_capture()

        try:
            QtCore.QTimer.singleShot(int(self._drag_capture_interval_ms), sample_cursor)
        except Exception:
            self._stop_drag_cursor_capture()

    def _request_drag_preview_refresh(self):
        """Let Maya repaint the live curve between dragger callbacks.

        Updating a curve inside ``draggerContext`` dirties its shape, but Maya
        can defer that paint until the mouse button is released.  Queue one
        ordinary current-view refresh on Qt's next event-loop turn instead of
        forcing a blocking refresh in every high-frequency callback.
        """
        if getattr(self, "_drag_preview_refresh_pending", False):
            return
        self._drag_preview_refresh_pending = True
        generation = getattr(self, "_drag_preview_refresh_generation", 0)

        def refresh_preview():
            if generation != getattr(self, "_drag_preview_refresh_generation", 0):
                return
            self._drag_preview_refresh_pending = False
            preview = self._drag_preview
            has_eraser_preview = bool(getattr(self, "_eraser_preview_marks", {}))
            if (not preview or not cmds.objExists(preview)) and not has_eraser_preview:
                return
            try:
                cmds.refresh(currentView=True)
            except Exception:
                pass

        try:
            QtCore.QTimer.singleShot(0, refresh_preview)
            return
        except Exception:
            # Headless tests and unusual hosts have no Qt event loop.  The
            # fallback still paints the preview rather than hiding it until
            # release, but normal interactive Maya always takes the queued path.
            refresh_preview()

    def _discard_drag_preview(self):
        self._cancel_drag_preview_refresh()
        preview = self._drag_preview
        self._drag_preview = ""
        self._drag_preview_pending_points = []
        self._drag_preview_style = None
        if not preview or not cmds.objExists(preview):
            return
        if self._drag_preview_undo_suppressed:
            cmds.delete(preview)
        else:
            self._run_without_undo(lambda: cmds.delete(preview))

    def _mark_points_in_layer_space(self, mark, metadata=None):
        """Return stored mark points transformed into the owning layer plane."""
        data = dict(metadata or _get_json_attr(mark, "animatorsPencilMarkData", {}) or {})
        points = data.get("points") or []
        try:
            matrix = cmds.xform(mark, query=True, matrix=True, objectSpace=True) or []
        except Exception:
            matrix = []
        if len(matrix) < 16:
            matrix = [
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ]
        return [_matrix_transform_point(point, matrix) for point in points], matrix

    @staticmethod
    def _eraser_preview_point_bounds_hit(points, bounds, radius):
        if not points or not bounds or len(bounds) < 4:
            return False
        min_x, min_y, max_x, max_y = [float(value) for value in bounds[:4]]
        radius = max(0.0, float(radius))
        min_x -= radius
        min_y -= radius
        max_x += radius
        max_y += radius
        for point in points:
            if min_x <= float(point[0]) <= max_x and min_y <= float(point[1]) <= max_y:
                return True
        for start, end in zip(points[:-1], points[1:]):
            segment_min_x = min(float(start[0]), float(end[0]))
            segment_max_x = max(float(start[0]), float(end[0]))
            segment_min_y = min(float(start[1]), float(end[1]))
            segment_max_y = max(float(start[1]), float(end[1]))
            if (
                segment_max_x >= min_x
                and segment_min_x <= max_x
                and segment_max_y >= min_y
                and segment_min_y <= max_y
            ):
                return True
        return False

    def _capture_eraser_preview_state(self, mark):
        state = self._eraser_preview_marks.get(mark)
        if state is not None:
            return state
        state = {
            "shapes": [],
            "transform_visibility": None,
            "nodes": [],
            "style": None,
        }
        for shape in _mark_shapes(mark):
            if not cmds.objExists(shape):
                continue
            try:
                enabled = bool(cmds.getAttr(shape + ".overrideEnabled"))
            except Exception:
                enabled = False
            try:
                visible = bool(cmds.getAttr(shape + ".overrideVisibility"))
            except Exception:
                visible = True
            state["shapes"].append((shape, enabled, visible))
        if not state["shapes"] and cmds.objExists(mark + ".visibility"):
            try:
                state["transform_visibility"] = bool(cmds.getAttr(mark + ".visibility"))
            except Exception:
                state["transform_visibility"] = True
        self._eraser_preview_marks[mark] = state
        return state

    @staticmethod
    def _hide_eraser_preview_source(mark, state):
        for shape, _enabled, _visible in state.get("shapes", []):
            if not cmds.objExists(shape):
                continue
            try:
                if cmds.objExists(shape + ".overrideEnabled"):
                    cmds.setAttr(shape + ".overrideEnabled", True)
                if cmds.objExists(shape + ".overrideVisibility"):
                    cmds.setAttr(shape + ".overrideVisibility", False)
            except Exception:
                continue
        if not state.get("shapes") and state.get("transform_visibility") is not None and cmds.objExists(mark + ".visibility"):
            try:
                cmds.setAttr(mark + ".visibility", False)
            except Exception:
                pass

    @staticmethod
    def _restore_eraser_preview_source(mark, state):
        for shape, enabled, visible in state.get("shapes", []):
            if not cmds.objExists(shape):
                continue
            try:
                if cmds.objExists(shape + ".overrideVisibility"):
                    cmds.setAttr(shape + ".overrideVisibility", bool(visible))
                if cmds.objExists(shape + ".overrideEnabled"):
                    cmds.setAttr(shape + ".overrideEnabled", bool(enabled))
            except Exception:
                continue
        if not state.get("shapes") and state.get("transform_visibility") is not None and cmds.objExists(mark + ".visibility"):
            try:
                cmds.setAttr(mark + ".visibility", bool(state["transform_visibility"]))
            except Exception:
                pass

    @staticmethod
    def _delete_eraser_preview_nodes(state):
        for node in list(state.get("nodes", [])):
            if node and cmds.objExists(node):
                try:
                    cmds.delete(node)
                except Exception:
                    pass
        state["nodes"] = []
        state["style"] = None

    def _replace_eraser_preview_nodes(self, mark, state, fragments, layer_node, metadata):
        fragments = [
            [
                (float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0)
                for point in fragment
            ]
            for fragment in (fragments or [])
            if len(fragment or []) >= 2
        ]
        nodes = list(state.get("nodes", []))
        active_nodes = []
        color = tuple(metadata.get("color") or DEFAULT_COLORS["Red"])
        opacity = _clamp_opacity(metadata.get("opacity", 1.0)) * self._layer_opacity(layer_node)
        size = float(metadata.get("size", 2.0))
        style = (color, opacity, size)
        for fragment_index, fragment_points in enumerate(fragments, 1):
            node = nodes[fragment_index - 1] if fragment_index <= len(nodes) else ""
            if node and cmds.objExists(node):
                try:
                    cmds.curve(node, replace=True, degree=1, point=fragment_points)
                except Exception:
                    node = ""
            if not node:
                try:
                    node = _curve_node(
                        "{0}_{1}_part{2}".format(
                            ERASER_PREVIEW_NAME,
                            _safe_name(_short_name(mark)),
                            fragment_index,
                        ),
                        fragment_points,
                        layer_node,
                        color,
                        opacity,
                        size,
                    )
                except Exception:
                    for preview_node in list(active_nodes):
                        if preview_node and cmds.objExists(preview_node):
                            try:
                                cmds.delete(preview_node)
                            except Exception:
                                pass
                    self._delete_eraser_preview_nodes(state)
                    return False
            active_nodes.append(_long_name(node))
            if style != state.get("style"):
                _set_display_color(node, color, opacity=opacity, line_width=size)
        for stale in nodes[len(active_nodes):]:
            if stale and cmds.objExists(stale):
                try:
                    cmds.delete(stale)
                except Exception:
                    pass
        state["nodes"] = active_nodes
        state["style"] = style
        return bool(active_nodes)

    def _discard_eraser_preview(self):
        """Restore source shapes and remove all temporary eraser fragments."""
        self._cancel_drag_preview_refresh()
        entries = list(self._eraser_preview_marks.items())
        self._eraser_preview_marks = {}
        self._eraser_preview_layer = ""
        self._eraser_preview_last_update = 0.0
        if not entries:
            return

        def cleanup():
            for mark, state in entries:
                if mark and cmds.objExists(mark):
                    self._restore_eraser_preview_source(mark, state)
                self._delete_eraser_preview_nodes(state)

        if self._drag_preview_undo_suppressed:
            cleanup()
        else:
            self._run_without_undo(cleanup)

    def _update_eraser_preview(self, points, force=False):
        """Show the exact surviving mark fragments while an eraser is held."""
        options = dict(self._drag_options)
        layer = options.get("layer_node") or self.active_layer()
        source_points = points if isinstance(points, list) else list(points or [])
        if not source_points or not layer or not cmds.objExists(layer):
            return False
        now = time.monotonic()
        if not force and (now - self._eraser_preview_last_update) < self._eraser_preview_interval:
            return bool(self._eraser_preview_marks)
        radius = max(0.04, float(options.get("size", 2.0)) * 0.03)
        active_marks = set()

        def update():
            for mark in list(self.marks(layer)):
                if not cmds.objExists(mark) or self._mark_is_locked(mark):
                    continue
                # Erasing is an edit to the selected Pencil layer, not a
                # visibility-only operation.  Current-frame-only marks are
                # intentionally hidden outside their key, but they must still
                # be previewable/editable when the artist erases across the
                # layer; otherwise only the last keyed stroke can be changed.
                metadata = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
                tool = metadata.get("tool", "Pencil")
                mark_points, source_matrix = self._mark_points_in_layer_space(mark, metadata=metadata)
                fragments = []
                touched = False
                if tool != "Text" and len(mark_points) >= 2:
                    touched, fragments = _split_polyline_by_eraser(mark_points, source_points, radius)
                else:
                    layer_points = self._marquee_points_in_layer_space(mark, metadata=metadata)
                    if layer_points:
                        bounds = [
                            min(point[0] for point in layer_points),
                            min(point[1] for point in layer_points),
                            max(point[0] for point in layer_points),
                            max(point[1] for point in layer_points),
                        ]
                        touched = self._eraser_preview_point_bounds_hit(source_points, bounds, radius)
                if not touched:
                    continue
                state = self._capture_eraser_preview_state(mark)
                # Fragments are already in layer space.  They are temporary
                # curves, so no source transform is applied a second time.
                preview_ok = self._replace_eraser_preview_nodes(mark, state, fragments, layer, metadata)
                if fragments and not preview_ok:
                    continue
                self._hide_eraser_preview_source(mark, state)
                active_marks.add(mark)

            for mark, state in list(self._eraser_preview_marks.items()):
                if mark in active_marks:
                    continue
                if mark and cmds.objExists(mark):
                    self._restore_eraser_preview_source(mark, state)
                self._delete_eraser_preview_nodes(state)
                self._eraser_preview_marks.pop(mark, None)
            self._eraser_preview_layer = _long_name(layer)
            return bool(active_marks)

        result = update() if self._drag_preview_undo_suppressed else self._run_without_undo(update)
        self._eraser_preview_last_update = time.monotonic()
        if result:
            self._request_drag_preview_refresh()
        return bool(result)

    def _update_drag_preview(self, points, force=False):
        options = dict(self._drag_options)
        layer = options.get("layer_node") or self.active_layer()
        # Keep the live gesture list by reference between preview ticks. The
        # previous code converted the entire accumulated stroke to floats on
        # every dragger callback, even when the 45 Hz throttle skipped the
        # actual Maya curve rebuild. That hidden O(points) copy was the main
        # source of lag on long Pencil/Brush drags.
        source_points = points if isinstance(points, list) else list(points or [])
        if len(source_points) < 2 or not layer or not cmds.objExists(layer):
            return ""
        self._drag_preview_pending_points = source_points
        now = time.monotonic()
        preview_exists = bool(self._drag_preview and cmds.objExists(self._drag_preview))
        if preview_exists and not force and (now - self._drag_preview_last_update) < self._drag_preview_interval:
            return self._drag_preview
        clean_points = [(float(point[0]), float(point[1]), 0.0) for point in source_points]
        style = (
            tuple(options.get("color", (1.0, 0.05, 0.05))),
            float(options.get("opacity", 1.0)),
            float(options.get("size", 2.0)),
        )

        def update():
            created = False
            if self._drag_preview and cmds.objExists(self._drag_preview):
                cmds.curve(self._drag_preview, replace=True, degree=1, point=clean_points)
            else:
                preview = cmds.curve(name=DRAW_PREVIEW_NAME, degree=1, point=clean_points)
                preview = cmds.parent(preview, layer, relative=True)[0]
                self._drag_preview = _long_name(preview)
                created = True
            if created or style != self._drag_preview_style:
                _set_display_color(
                    self._drag_preview,
                    options.get("color", (1.0, 0.05, 0.05)),
                    opacity=options.get("opacity", 1.0),
                    line_width=options.get("size", 2.0),
                )
                self._drag_preview_style = style
            return self._drag_preview

        result = update() if self._drag_preview_undo_suppressed else self._run_without_undo(update)
        # Start the cooldown after Maya has finished replacing the curve and
        # refreshing the viewport. Recording ``now`` from before that work
        # lets a heavy rebuild consume the whole interval and collapses the
        # nominal 45 Hz throttle into one rebuild per drag callback.
        self._drag_preview_last_update = time.monotonic()
        self._request_drag_preview_refresh()
        return result

    def _bounds_from_points(self, points):
        xs = [float(point[0]) for point in points] or [0.0]
        ys = [float(point[1]) for point in points] or [0.0]
        return [min(xs), min(ys), max(xs), max(ys)]

    def _point_distance(self, point_a, point_b):
        return math.sqrt(((float(point_a[0]) - float(point_b[0])) ** 2.0) + ((float(point_a[1]) - float(point_b[1])) ** 2.0))

    def _point_distance_squared(self, point_a, point_b):
        """Cheap drag sampling comparison that avoids a sqrt per callback."""
        return ((float(point_a[0]) - float(point_b[0])) ** 2.0) + ((float(point_a[1]) - float(point_b[1])) ** 2.0)

    def create_mark(self, tool="Pencil", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True, points=None, one_frame=False):
        if not MAYA_AVAILABLE:
            return ""
        layer_node = layer_node or self.active_layer()
        if not layer_node or not cmds.objExists(layer_node):
            layer_node = self.create_layer()
        if _get_string_attr(layer_node, "animatorsPencilLayerState", "Animation") == "Locked":
            self._status("Layer locked.")
            return ""
        _open_undo_chunk("Animators Pencil Create {0}".format(tool))
        try:
            if tool == "Eraser":
                self.delete_selected_marks()
                return ""
            notes_camera = ""
            if camera_note:
                notes_camera = self.key_camera_notes_to_current_view(snap=camera_snap, switch_to_camera=False)
            if tool == "Text":
                group = cmds.textCurves(name="amirPencilText_MARK", text=text or "Note", font="Arial", constructionHistory=False)[0]
                # Text stamps are camera-space geometry too.  Absolute
                # parenting would bake the inverse layer rotation into the
                # text transform and make it face the world grid.
                group = cmds.parent(group, layer_node, relative=True)[0]
                group = _long_name(group)
                cmds.setAttr(group + ".translate", -0.55, 0.0, 0.0, type="double3")
                cmds.setAttr(group + ".scale", 0.025, 0.025, 0.025, type="double3")
                mark = group
                _set_display_color(mark, color, opacity=opacity, line_width=size)
            else:
                mark_points = points or self._tool_points(tool)
                mark = _curve_node("amirPencil{0}_MARK".format(tool), mark_points, layer_node, color, opacity, size)
            self._mark_node(mark, layer_node, tool, color, opacity, size, one_frame=one_frame)
            mark_data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            mark_data["points"] = [[float(point[0]), float(point[1]), 0.0] for point in (points or self._tool_points(tool))]
            _set_json_attr(mark, "animatorsPencilMarkData", mark_data)
            if points:
                data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
                data["dragBounds"] = self._bounds_from_points(points)
                data["dragDrawn"] = True
                _set_json_attr(mark, "animatorsPencilMarkData", data)
            if notes_camera:
                _set_string_attr(mark, "animatorsPencilCameraNotesCamera", notes_camera)
            cmds.select(mark, replace=True)
            self._status("{0} mark created.".format(tool))
            return mark
        finally:
            _close_undo_chunk()

    def create_mark_from_drag(self, tool="Rectangle", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True, start_point=(-0.5, 0.35, 0.0), end_point=(0.5, -0.35, 0.0), one_frame=False, screen_start=None, screen_end=None, mapping_cache=None):
        points = (
            self._tool_points_from_screen_drag_cached(tool, layer_node, screen_start, screen_end, mapping_cache=mapping_cache)
            if screen_start is not None and screen_end is not None
            else self._tool_points_from_drag(tool, start_point, end_point)
        )
        mark = self.create_mark(tool, layer_node, color, size, opacity, text, camera_note, camera_snap, points=points, one_frame=one_frame)
        if mark and cmds.objExists(mark):
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            data["dragStart"] = [float(start_point[0]), float(start_point[1])]
            data["dragEnd"] = [float(end_point[0]), float(end_point[1])]
            data["dragBounds"] = self._bounds_from_points(points)
            if screen_start is not None and screen_end is not None:
                data["screenDragStart"] = [float(screen_start[0]), float(screen_start[1])]
                data["screenDragEnd"] = [float(screen_end[0]), float(screen_end[1])]
            _set_json_attr(mark, "animatorsPencilMarkData", data)
        return mark

    def create_freehand_mark(self, tool="Pencil", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True, points=None, one_frame=False):
        clean_points, single_click = _normalized_freehand_points(points)
        if not clean_points:
            # Never turn a missing freehand sample into the old arbitrary
            # diagonal.  A real press always supplies one mapped point, which
            # is normalized above into a two-CV dot.
            return ""
        mark = self.create_mark(tool, layer_node, color, size, opacity, text, camera_note, camera_snap, points=clean_points, one_frame=one_frame)
        if mark and cmds.objExists(mark):
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            data["freehandDrawn"] = True
            data["freehandPointCount"] = len(clean_points)
            data["singleClickDot"] = bool(single_click)
            data["freehandSourcePointCount"] = 1 if single_click else len(clean_points)
            data["dragStart"] = [clean_points[0][0], clean_points[0][1]]
            data["dragEnd"] = [clean_points[-1][0], clean_points[-1][1]]
            data["dragBounds"] = self._bounds_from_points(clean_points)
            _set_json_attr(mark, "animatorsPencilMarkData", data)
        return mark

    def _mark_is_locked(self, mark):
        """Return whether a mark itself is protected from replacement."""
        if not mark or not cmds.objExists(mark):
            return True
        if _get_string_attr(mark, "animatorsPencilMarkState", "") == "Locked":
            return True
        try:
            if cmds.attributeQuery("animatorsPencilMarkLocked", node=mark, exists=True) and cmds.getAttr(mark + ".animatorsPencilMarkLocked"):
                return True
        except Exception:
            pass
        # Transform-level locks are uncommon on marks, but honour them when a
        # user or a previous tool has explicitly applied one.
        for attr_name in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
            try:
                if cmds.objExists(mark + "." + attr_name) and cmds.getAttr(mark + "." + attr_name, lock=True):
                    return True
            except Exception:
                continue
        return False

    def _mark_visibility_snapshot(self, mark):
        try:
            times = cmds.keyframe(mark, attribute="visibility", query=True, timeChange=True) or []
        except Exception:
            times = []
        try:
            values = cmds.keyframe(mark, attribute="visibility", query=True, valueChange=True) or []
        except Exception:
            values = []
        try:
            current = bool(cmds.getAttr(mark + ".visibility"))
        except Exception:
            current = True
        return times, values, current

    def _rebuild_mark_fragments(self, mark, fragment_entries, layer_node=None, metadata=None, reason="partial"):
        """Clone curve fragments and delete ``mark`` only after all succeed.

        ``fragment_entries`` may contain point lists or ``(inside, points)``
        pairs.  The latter lets marquee selection rebuild both sides in path
        order while returning only the inside fragments for selection.  The
        helper is shared with the paint-style eraser so frame visibility,
        camera links, transforms, and display style stay in one place.
        """
        if not mark or not cmds.objExists(mark) or self._mark_is_locked(mark):
            return [], []
        layer_node = layer_node or self.active_layer()
        if not layer_node or not cmds.objExists(layer_node):
            return [], []
        data = dict(metadata or _get_json_attr(mark, "animatorsPencilMarkData", {}) or {})
        tool = data.get("tool", "Pencil")
        if tool == "Text":
            return [], []
        color = tuple(data.get("color") or DEFAULT_COLORS["Red"])
        opacity = float(data.get("opacity", 1.0))
        size = float(data.get("size", 2.0))
        frame = int(data.get("frame", _current_frame()))
        one_frame = bool(data.get("oneFrame", False))
        camera_link = _get_string_attr(mark, "animatorsPencilCameraNotesCamera", "")
        visibility_times, visibility_values, visibility_value = self._mark_visibility_snapshot(mark)
        try:
            source_matrix = cmds.xform(mark, query=True, matrix=True, objectSpace=True)
        except Exception:
            source_matrix = None
        try:
            translucent = bool(
                cmds.attributeQuery(TRANSLUCENT_MARKS_ATTR, node=mark, exists=True)
                and cmds.getAttr(mark + "." + TRANSLUCENT_MARKS_ATTR)
            )
        except Exception:
            translucent = False

        normalized_entries = []
        for entry in list(fragment_entries or []):
            inside = False
            fragment_points = entry
            if isinstance(entry, (tuple, list)) and len(entry) == 2 and isinstance(entry[0], bool):
                inside, fragment_points = entry
            clean_points = [
                (float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0)
                for point in (fragment_points or [])
            ]
            if len(clean_points) >= 2:
                normalized_entries.append((bool(inside), clean_points))
        if not normalized_entries:
            return [], []

        created = []
        selected_inside = []
        try:
            for fragment_index, (is_inside, fragment_points) in enumerate(normalized_entries, 1):
                fragment = _curve_node(
                    "{0}_part{1}_MARK".format(_safe_name(tool), fragment_index),
                    fragment_points,
                    layer_node,
                    color,
                    opacity,
                    size,
                )
                if not fragment or not cmds.objExists(fragment):
                    raise RuntimeError("Maya did not create a Pencil fragment")
                self._mark_node(fragment, layer_node, tool, color, opacity, size, frame=frame, one_frame=one_frame)
                fragment_data = dict(data)
                fragment_data["layer"] = _long_name(layer_node)
                fragment_data["points"] = [[float(point[0]), float(point[1]), float(point[2])] for point in fragment_points]
                fragment_data["dragBounds"] = self._bounds_from_points(fragment_points)
                fragment_data["freehandPointCount"] = len(fragment_points)
                if reason == "eraser":
                    fragment_data["partialErased"] = True
                elif reason == "marquee":
                    fragment_data["partialMarquee"] = True
                _set_json_attr(fragment, "animatorsPencilMarkData", fragment_data)
                if camera_link:
                    _set_string_attr(fragment, "animatorsPencilCameraNotesCamera", camera_link)
                if source_matrix:
                    cmds.xform(fragment, matrix=source_matrix, objectSpace=True)
                cmds.cutKey(fragment, attribute="visibility", clear=True)
                cmds.setAttr(fragment + ".visibility", visibility_value)
                for key_time, key_value in zip(visibility_times, visibility_values):
                    cmds.setKeyframe(fragment, attribute="visibility", time=float(key_time), value=float(key_value), shape=False)
                # Maya can keep the pre-key visibility cache after a marquee
                # fragment is rebuilt. Dirty the new transform so the current
                # frame evaluates the copied off/on keys immediately instead
                # of making the selected line appear to disappear.
                try:
                    cmds.dgdirty(fragment)
                except Exception:
                    pass
                if translucent:
                    _ensure_attr(fragment, TRANSLUCENT_MARKS_ATTR, "bool", True)
                    cmds.setAttr(fragment + "." + TRANSLUCENT_MARKS_ATTR, True)
                    for shape in _mark_shapes(fragment):
                        if cmds.objExists(shape + ".overrideEnabled"):
                            cmds.setAttr(shape + ".overrideEnabled", True)
                        if cmds.objExists(shape + ".overrideDisplayType"):
                            cmds.setAttr(shape + ".overrideDisplayType", 1)
                created.append(fragment)
                if is_inside:
                    selected_inside.append(fragment)
            # The source is removed only after every requested replacement has
            # a valid node and copied metadata/style.  If deletion fails, keep
            # the original and clean up the new nodes to avoid duplicates.
            cmds.delete(mark)
            return created, selected_inside
        except Exception:
            for fragment in list(created):
                try:
                    if cmds.objExists(fragment):
                        cmds.delete(fragment)
                except Exception:
                    pass
            return [], []

    @staticmethod
    def _marquee_points_in_layer_space(mark, metadata=None):
        """Return editable mark points in the owning layer's camera plane."""
        metadata = metadata or _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
        points = metadata.get("points") or []
        if not points:
            try:
                bounds = cmds.xform(mark, query=True, boundingBox=True, objectSpace=True) or []
                if len(bounds) >= 6:
                    points = [
                        (bounds[0], bounds[1], bounds[2]),
                        (bounds[3], bounds[1], bounds[2]),
                        (bounds[3], bounds[4], bounds[2]),
                        (bounds[0], bounds[4], bounds[2]),
                    ]
            except Exception:
                points = []
        if not points:
            return []
        try:
            matrix = cmds.xform(mark, query=True, matrix=True, objectSpace=True) or []
        except Exception:
            matrix = []
        if len(matrix) < 16:
            matrix = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        return [_matrix_transform_point(point, matrix) for point in points]

    def _marquee_selection_bounds(self, marks):
        points = []
        for mark in marks or []:
            if not cmds.objExists(mark):
                continue
            points.extend(self._marquee_points_in_layer_space(mark))
        if not points:
            return None
        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)
        # A one-point or perfectly horizontal stroke still needs a handle that
        # can be seen and grabbed in the viewport.
        minimum_span = 0.08
        if max_x - min_x < minimum_span:
            center_x = (min_x + max_x) * 0.5
            min_x, max_x = center_x - (minimum_span * 0.5), center_x + (minimum_span * 0.5)
        if max_y - min_y < minimum_span:
            center_y = (min_y + max_y) * 0.5
            min_y, max_y = center_y - (minimum_span * 0.5), center_y + (minimum_span * 0.5)
        return min_x, min_y, max_x, max_y

    @staticmethod
    def _marquee_box_points(bounds, z_offset=0.002):
        min_x, min_y, max_x, max_y = bounds
        return [
            (min_x, min_y, z_offset),
            (max_x, min_y, z_offset),
            (max_x, max_y, z_offset),
            (min_x, max_y, z_offset),
            (min_x, min_y, z_offset),
        ]

    def _discard_marquee_preview(self):
        preview = self._marquee_preview
        self._marquee_preview = ""
        if not preview or not cmds.objExists(preview):
            return
        self._run_without_undo(lambda: cmds.delete(preview))

    def _update_marquee_preview(self, bounds=None, layer_node=None, force=False, points=None):
        """Draw the marquee in the active layer's camera-space plane.

        Interactive drags pass the ordered layer points produced by the shared
        screen-space rectangle mapper.  That matters when the input viewport
        is rolled, perspective, or the retained Reference Viewer: reducing
        two mapped corners to local min/max values makes a skewed rhombus.
        ``bounds`` remains supported for programmatic callers and transform
        box compatibility.
        """
        if not bounds and not points:
            return ""
        now = time.monotonic()
        if not force and (now - self._marquee_preview_last_update) < (1.0 / 30.0):
            return self._marquee_preview
        preview_points = [
            (float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0)
            for point in (points or self._marquee_box_points(bounds))
        ]

        def update():
            if self._marquee_preview and cmds.objExists(self._marquee_preview):
                cmds.curve(self._marquee_preview, replace=True, degree=1, point=preview_points)
            else:
                self._marquee_preview = cmds.curve(name=MARQUEE_PREVIEW_NAME, degree=1, point=preview_points)
                _set_display_color(self._marquee_preview, (0.45, 0.72, 0.95), opacity=0.9, line_width=1.5)
            if layer_node and cmds.objExists(layer_node):
                preview_parent = (cmds.listRelatives(self._marquee_preview, parent=True, fullPath=True) or [""])[0]
                if preview_parent != _long_name(layer_node):
                    self._marquee_preview = cmds.parent(self._marquee_preview, layer_node, relative=True)[0]
            try:
                cmds.refresh(currentView=True)
            except Exception:
                pass
            return self._marquee_preview

        self._marquee_preview_last_update = now
        return self._run_without_undo(update)

    def _remove_marquee_selection_monitor(self):
        job = int(getattr(self, "_marquee_selection_job", 0) or 0)
        self._marquee_selection_job = 0
        if not job or not MAYA_AVAILABLE:
            return
        try:
            if cmds.scriptJob(exists=job):
                cmds.scriptJob(kill=job, force=True)
        except Exception:
            pass

    def _install_marquee_selection_monitor(self):
        self._remove_marquee_selection_monitor()
        if not MAYA_AVAILABLE or not self._marquee_transform_box:
            return False
        try:
            self._marquee_selection_job = cmds.scriptJob(
                event=["SelectionChanged", self._marquee_selection_changed],
                protected=True,
                killWithScene=True,
            )
            self._marquee_selection_job = int(self._marquee_selection_job or 0)
        except Exception:
            self._marquee_selection_job = 0
        return bool(self._marquee_selection_job)

    def _marquee_selection_changed(self):
        """Commit the active box when the user clicks a different selection."""
        if getattr(self, "_marquee_commit_guard", False):
            return
        box = self._marquee_transform_box
        if not box:
            self._remove_marquee_selection_monitor()
            return
        try:
            if not cmds.objExists(box):
                self._marquee_transform_box = ""
                self._marquee_transform_layer = ""
                self._remove_marquee_selection_monitor()
                return
            selected = cmds.ls(selection=True, long=True) or []
        except Exception:
            return
        if _long_name(box) not in selected:
            self._commit_marquee_transform_box()

    def _marquee_transform_box_candidates(self):
        """Return only active Pencil transform boxes, including orphaned ones."""
        candidates = []
        tracked = self._marquee_transform_box
        if tracked and cmds.objExists(tracked):
            candidates.append(_long_name(tracked))
        try:
            tagged = cmds.ls(
                "*.{0}".format(MARQUEE_TRANSFORM_BOX_ATTR),
                objectsOnly=True,
                long=True,
            ) or []
        except Exception:
            tagged = []
        for node in tagged:
            node = _long_name(node)
            if node in candidates or not cmds.objExists(node):
                continue
            if _get_string_attr(node, MARQUEE_TRANSFORM_BOX_ATTR, "") == "active":
                candidates.append(node)
        return candidates

    def _commit_marquee_transform_box(self):
        """Bake selected marks back to the layer and remove the yellow box.

        Maya emits ``SelectionChanged`` while parenting/deleting nodes.  Kill
        the scoped watcher and hold a re-entry guard before touching the DAG,
        otherwise the cleanup callback can interrupt its own reparent pass.
        """
        if getattr(self, "_marquee_commit_guard", False):
            return False
        self._marquee_commit_guard = True
        self._remove_marquee_selection_monitor()
        boxes = self._marquee_transform_box_candidates()
        tracked_box = self._marquee_transform_box
        tracked_layer = self._marquee_transform_layer
        self._marquee_transform_box = ""
        self._marquee_transform_layer = ""
        changed = False
        try:
            for box in boxes:
                if not box or not cmds.objExists(box):
                    continue
                layer = (
                    tracked_layer
                    if box == tracked_box and tracked_layer and cmds.objExists(tracked_layer)
                    else ""
                )
                if not layer:
                    parents = cmds.listRelatives(box, parent=True, fullPath=True) or []
                    layer = parents[0] if parents else ""
                marks = [
                    node for node in (
                        cmds.listRelatives(box, allDescendents=True, type="transform", fullPath=True) or []
                    )
                    if _get_string_attr(node, MARK_MARKER_ATTR, "") == "mark"
                ]
                for mark in marks:
                    try:
                        if layer and cmds.objExists(layer):
                            cmds.parent(mark, layer, absolute=True)
                    except Exception:
                        continue
                try:
                    cmds.delete(box)
                    changed = bool(marks) or changed
                except Exception:
                    continue
        finally:
            self._marquee_commit_guard = False
        return changed

    def _show_marquee_transform_box(self, layer_node, marks):
        if not layer_node or not cmds.objExists(layer_node) or not marks:
            return ""
        self._commit_marquee_transform_box()
        bounds = self._marquee_selection_bounds(marks)
        if not bounds:
            return ""
        try:
            box = cmds.curve(name=MARQUEE_TRANSFORM_BOX_NAME, degree=1, point=self._marquee_box_points(bounds, z_offset=0.004))
            box = _long_name(cmds.parent(box, layer_node, relative=True)[0])
            _set_string_attr(box, MARQUEE_TRANSFORM_BOX_ATTR, "active")
            _set_display_color(box, (0.83, 0.71, 0.30), opacity=1.0, line_width=2.0)
            center_x = (bounds[0] + bounds[2]) * 0.5
            center_y = (bounds[1] + bounds[3]) * 0.5
            cmds.xform(box, pivots=(center_x, center_y, 0.0), objectSpace=True)
            for mark in marks:
                if cmds.objExists(mark):
                    cmds.parent(mark, box, relative=True)
            self._marquee_transform_box = box
            self._marquee_transform_layer = _long_name(layer_node)
            self._install_marquee_selection_monitor()
            cmds.select(box, replace=True)
            cmds.setToolTo("moveSuperContext")
            return box
        except Exception:
            self._remove_marquee_selection_monitor()
            self._marquee_transform_box = ""
            self._marquee_transform_layer = ""
            if 'box' in locals() and box and cmds.objExists(box):
                try:
                    cmds.delete(box)
                except Exception:
                    pass
            return ""

    def select_marks_in_box(self, layer_node=None, start_point=(-1.0, -1.0, 0.0), end_point=(1.0, 1.0, 0.0), add=False):
        if not MAYA_AVAILABLE:
            return []
        layer_node = layer_node or self.active_layer()
        if not layer_node or not cmds.objExists(layer_node):
            return []
        if _get_string_attr(layer_node, "animatorsPencilLayerState", "Animation") == "Locked":
            self._status("Layer locked. Marquee left marks unchanged.")
            return []
        min_x, max_x = min(float(start_point[0]), float(end_point[0])), max(float(start_point[0]), float(end_point[0]))
        min_y, max_y = min(float(start_point[1]), float(end_point[1])), max(float(start_point[1]), float(end_point[1]))
        picked = []
        previous_selection = cmds.ls(selection=True, long=True) or [] if add else []
        _open_undo_chunk("Animators Pencil Marquee Select")
        try:
            for mark in self.marks(layer_node):
                if not cmds.objExists(mark) or self._mark_is_locked(mark):
                    continue
                data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
                mark_points = data.get("points") or []
                tool = data.get("tool", "Pencil")
                # Curve marks can be clipped at the box boundary.  Text and
                # legacy marks without point data retain the old bounding-box
                # selection behaviour because they have no safe polyline to
                # rebuild.
                if tool != "Text" and len(mark_points) >= 2:
                    try:
                        source_matrix = cmds.xform(mark, query=True, matrix=True, objectSpace=True) or []
                    except Exception:
                        source_matrix = []
                    # The dragger rectangle was projected onto the owning
                    # layer plane.  Stored CV metadata, however, is local to
                    # the mark and may include a prior move/rotate/scale. Clip
                    # in one space, then map each surviving fragment back to
                    # mark-local before _rebuild_mark_fragments reapplies the
                    # original transform.
                    layer_points = [
                        _matrix_transform_point(point, source_matrix)
                        for point in mark_points
                    ]
                    segments = _segment_polyline_by_box(
                        layer_points,
                        (min_x, min_y, max_x, max_y),
                        closed=data.get("closed"),
                    )
                    inside_segments = [points for is_inside, points in segments if is_inside]
                    outside_segments = [points for is_inside, points in segments if not is_inside]
                    if not inside_segments:
                        continue
                    if not outside_segments:
                        # Whole-inside marks are kept intact so their
                        # existing transform history and node identity stay
                        # unchanged.
                        picked.append(mark)
                        continue
                    local_segments = [
                        (
                            is_inside,
                            [
                                _matrix_transform_point(point, source_matrix, inverse=True)
                                for point in points
                            ],
                        )
                        for is_inside, points in segments
                    ]
                    _created, selected_inside = self._rebuild_mark_fragments(
                        mark,
                        local_segments,
                        layer_node=layer_node,
                        metadata=data,
                        reason="marquee",
                    )
                    picked.extend(selected_inside)
                    continue

                layer_space_points = self._marquee_points_in_layer_space(mark, metadata=data)
                bounds = None
                if layer_space_points:
                    bounds = [
                        min(point[0] for point in layer_space_points),
                        min(point[1] for point in layer_space_points),
                        max(point[0] for point in layer_space_points),
                        max(point[1] for point in layer_space_points),
                    ]
                if not bounds:
                    bounds = data.get("dragBounds")
                if not bounds or len(bounds) < 4:
                    continue
                bx1, by1, bx2, by2 = float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])
                if bx2 < min_x or bx1 > max_x or by2 < min_y or by1 > max_y:
                    continue
                picked.append(mark)
        finally:
            surviving_previous = [node for node in previous_selection if cmds.objExists(node)]
            surviving_picked = [node for node in picked if cmds.objExists(node)]
            selection = []
            for node in surviving_previous + surviving_picked:
                if node not in selection:
                    selection.append(node)
            if selection:
                cmds.select(selection, replace=True)
            else:
                cmds.select(clear=True)
            _close_undo_chunk()
        self._status("Marquee selected {0} pencil mark(s).".format(len(picked)))
        return picked

    def erase_marks_with_stroke(self, layer_node=None, points=None, radius=0.1, whole_stroke=False):
        layer_node = layer_node or self.active_layer()
        points = list(points or [])
        if not layer_node or not cmds.objExists(layer_node) or not points:
            return 0
        if _get_string_attr(layer_node, "animatorsPencilLayerState", "Animation") == "Locked":
            self._status("Layer locked. Nothing erased.")
            return 0
        radius = max(0.01, float(radius))
        affected = 0
        fragments_created = 0
        previous_selection = cmds.ls(selection=True, long=True) or []
        _open_undo_chunk("Animators Pencil Partial Erase")
        try:
            for mark in list(self.marks(layer_node)):
                if not cmds.objExists(mark) or self._mark_is_locked(mark):
                    continue
                # Do not filter by evaluated visibility here.  A layer can
                # contain one-frame/keyframed marks whose visibility is false
                # at the current time; the eraser still needs to edit those
                # stored marks so it is not limited to the latest drawing.
                data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
                mark_points = data.get("points") or []
                if data.get("tool") != "Text" and len(mark_points) >= 2:
                    layer_points, source_matrix = self._mark_points_in_layer_space(mark, metadata=data)
                    touched, fragments = _split_polyline_by_eraser(layer_points, points, radius)
                    if not touched:
                        continue
                    affected += 1
                    if whole_stroke:
                        cmds.delete(mark)
                        continue
                    created, _selected = self._rebuild_mark_fragments(
                        mark,
                        [
                            [
                                _matrix_transform_point(point, source_matrix, inverse=True)
                                for point in fragment
                            ]
                            for fragment in fragments
                        ],
                        layer_node=layer_node,
                        metadata=data,
                        reason="eraser",
                    )
                    if not created:
                        # A failed rebuild leaves the source mark untouched.
                        affected -= 1
                        continue
                    fragments_created += len(created)
                    continue

                bounds = data.get("dragBounds")
                if not bounds:
                    try:
                        bbox = cmds.xform(mark, query=True, boundingBox=True, objectSpace=True) or []
                        bounds = [bbox[0], bbox[1], bbox[3], bbox[4]] if len(bbox) >= 6 else None
                    except Exception:
                        bounds = None
                if not bounds or len(bounds) < 4:
                    continue
                min_x, min_y, max_x, max_y = [float(value) for value in bounds[:4]]
                if any(min_x - radius <= float(point[0]) <= max_x + radius and min_y - radius <= float(point[1]) <= max_y + radius for point in points):
                    cmds.delete(mark)
                    affected += 1
        finally:
            surviving_selection = [node for node in previous_selection if cmds.objExists(node)]
            if surviving_selection:
                cmds.select(surviving_selection, replace=True)
            else:
                cmds.select(clear=True)
            _close_undo_chunk()
        if whole_stroke:
            self._status("Whole-stroke eraser removed {0} mark(s).".format(affected))
        else:
            self._status("Partial eraser changed {0} mark(s), kept {1} fragment(s).".format(affected, fragments_created))
        return affected

    def _build_drag_mapping_cache(self, layer_node):
        """Cache the stable viewport and layer plane state for one drag."""
        if not (layer_node and cmds.objExists(layer_node) and om and omui):
            return None
        try:
            # A drag may begin in the retained Reference Viewer.  Cache the
            # exact modelPanel that owns the mouse, including that viewer, so
            # every corner is projected through the same camera that the user
            # can actually see.
            view, widget = _active_m3dview_widget(include_reference_viewer=True)
            if view is None:
                return None
            logical_width = max(float(widget.width()), 1.0) if _qt_object_valid(widget) else _active_model_viewport_size()[0]
            logical_height = max(float(widget.height()), 1.0) if _qt_object_valid(widget) else _active_model_viewport_size()[1]
            port_width = max(float(view.portWidth()), 1.0)
            port_height = max(float(view.portHeight()), 1.0)
            layer_matrix = om.MMatrix()
            om.MScriptUtil.createMatrixFromList(
                cmds.xform(layer_node, query=True, matrix=True, worldSpace=True),
                layer_matrix,
            )
            return {
                "view": view,
                "widget": widget,
                "logical_width": logical_width,
                "logical_height": logical_height,
                "port_width": port_width,
                "port_height": port_height,
                "layer_matrix": layer_matrix,
                "layer_inverse": layer_matrix.inverse(),
                "plane_origin": om.MPoint(0.0, 0.0, 0.0) * layer_matrix,
                "plane_normal": om.MVector(0.0, 0.0, 1.0) * layer_matrix,
            }
        except Exception:
            return None

    def update_drag_draw_options(self, tool="Rectangle", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True, one_frame=False, eraser_mode="partial"):
        global GLOBAL_DRAG_CONTEXT_CONTROLLER
        GLOBAL_DRAG_CONTEXT_CONTROLLER = self
        self._drag_options = {
            "tool": tool,
            "layer_node": layer_node or self.active_layer_for_camera(),
            "color": color,
            "size": size,
            "opacity": opacity,
            "text": text,
            "camera_note": camera_note,
            "camera_snap": camera_snap,
            "one_frame": bool(one_frame),
            "eraser_mode": "whole" if str(eraser_mode).lower().startswith("whole") else "partial",
        }
        return dict(self._drag_options)

    def activate_drag_draw_context(self, tool="Rectangle", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True, one_frame=False, eraser_mode="partial"):
        if not MAYA_AVAILABLE:
            return False
        if str(tool) == "Eraser":
            # Finish any temporary marquee parent before caching mark points.
            # The preview and release path must use one layer-space geometry.
            self._commit_marquee_transform_box()
        drawing_view = self.ensure_drawing_view_for_drawing(layer_node)
        layer_node = drawing_view.get("layer") or layer_node
        self.update_drag_draw_options(tool, layer_node, color, size, opacity, text, camera_note, camera_snap, one_frame, eraser_mode)
        self._drag_anchor = None
        self._drag_start_point = None
        self._drag_points = []
        self._drag_screen_points = []
        self._drag_mapping_cache = None
        self._stop_drag_cursor_capture()
        self._end_drag_preview_session()
        self._discard_drag_preview()
        self._discard_eraser_preview()
        # Maya draggerContext executes these command strings as Python. Wrapping
        # them in MEL python() makes Python look for a name called ``python`` and
        # raises NameError on the first viewport drag.
        context_options = {
            "pressCommand": DRAW_PRESS_MEL_COMMAND,
            "dragCommand": DRAW_DRAG_MEL_COMMAND,
            "releaseCommand": DRAW_RELEASE_MEL_COMMAND,
            "cursor": "crossHair",
            "undoMode": "step",
        }
        if cmds.draggerContext(DRAW_CONTEXT_NAME, exists=True):
            cmds.draggerContext(DRAW_CONTEXT_NAME, edit=True, **context_options)
        else:
            cmds.draggerContext(DRAW_CONTEXT_NAME, **context_options)
        cmds.setToolTo(DRAW_CONTEXT_NAME)
        self._status("Drag in viewport to draw {0}.".format(tool))
        return True

    def activate_marquee_select_context(self, layer_node=None, add=False):
        if not MAYA_AVAILABLE:
            return False
        global GLOBAL_DRAG_CONTEXT_CONTROLLER
        GLOBAL_DRAG_CONTEXT_CONTROLLER = self
        self._discard_marquee_preview()
        self._commit_marquee_transform_box()
        self._marquee_options = {"layer_node": layer_node or self.active_layer(), "add": bool(add)}
        self._marquee_anchor = None
        self._marquee_start_point = None
        self._marquee_screen_points = []
        self._marquee_blocked_press = False
        self._marquee_mapping_cache = None
        _delete_drag_context(MARQUEE_CONTEXT_NAME)
        cmds.draggerContext(
            MARQUEE_CONTEXT_NAME,
            pressCommand=MARQUEE_PRESS_MEL_COMMAND,
            dragCommand=MARQUEE_DRAG_MEL_COMMAND,
            releaseCommand=MARQUEE_RELEASE_MEL_COMMAND,
            cursor="crossHair",
            undoMode="step",
        )
        cmds.setToolTo(MARQUEE_CONTEXT_NAME)
        self._status("Drag a box over pencil lines. The selected line sections get a move-and-scale box.")
        return True

    def _draw_context_press(self):
        try:
            self._drag_anchor = cmds.draggerContext(DRAW_CONTEXT_NAME, query=True, anchorPoint=True)
        except Exception:
            self._drag_anchor = None
        options = dict(self._drag_options)
        self._drag_options["blocked_press"] = False
        expected_layer = options.get("layer_node") or ""
        expected_camera = _get_string_attr(expected_layer, "animatorsPencilCamera", "") if expected_layer and cmds.objExists(expected_layer) else ""
        active_camera = _drawing_input_camera()
        if expected_camera and active_camera and _long_name(expected_camera) != _long_name(active_camera):
            self._drag_options["blocked_press"] = True
            self._drag_anchor = None
            self._drag_points = []
            self._drag_screen_points = []
            self._drag_mapping_cache = None
            self._stop_drag_cursor_capture()
            self._status("Draw inside the Aminate Reference Viewer so marks stay aligned with the video.")
            return False
        drawing_view = self.ensure_drawing_view_for_drawing(options.get("layer_node"), camera=active_camera)
        layer = drawing_view.get("layer") or self.active_layer_for_camera(options.get("layer_node"))
        self._drag_options["layer_node"] = layer
        self._drag_mapping_cache = self._build_drag_mapping_cache(layer)
        self._begin_drag_preview_session()
        try:
            self._drag_start_point = _screen_to_layer_point(layer, self._drag_anchor or (640, 360, 0), mapping_cache=self._drag_mapping_cache)
            self._drag_points = [self._drag_start_point]
            self._drag_screen_points = [self._drag_anchor] if self._drag_anchor else []
            self._discard_drag_preview()
            self._discard_eraser_preview()
            self._start_drag_cursor_capture()
        except Exception:
            self._stop_drag_cursor_capture()
            self._end_drag_preview_session()
            self._drag_mapping_cache = None
            raise

    def _draw_context_drag(self):
        if self._drag_options.get("blocked_press"):
            return False
        try:
            options = dict(self._drag_options)
            layer = options.get("layer_node") or self.active_layer()
            try:
                drag_point = cmds.draggerContext(DRAW_CONTEXT_NAME, query=True, dragPoint=True)
            except Exception:
                drag_point = None
            if options.get("tool") in STROKE_PATH_TOOLS:
                if drag_point:
                    point = _screen_to_layer_point(layer, drag_point, mapping_cache=self._drag_mapping_cache)
                    self._append_drag_sample(layer, screen_point=drag_point, layer_point=point)
                else:
                    # A busy video/image-plane viewport can miss a
                    # draggerContext callback. Do not turn that gap into the
                    # press point: sample the real cursor in the same widget.
                    self._capture_drag_cursor_tail(layer)
            if options.get("tool") in ("Pencil", "Brush"):
                self._update_drag_preview(self._drag_points)
            elif options.get("tool") == "Eraser":
                self._update_eraser_preview(self._drag_points)
            elif options.get("tool") in SHAPE_TOOL_NAMES:
                mapping_cache = self._drag_mapping_cache or {}
                screen_start = self._drag_anchor or (self._drag_screen_points[0] if self._drag_screen_points else None)
                cursor_screen = _active_m3dview_logical_cursor_point(
                    mapping_cache.get("view"), mapping_cache.get("widget")
                )
                screen_end = cursor_screen or drag_point or (self._drag_screen_points[-1] if self._drag_screen_points else None)
                if screen_start and screen_end:
                    if not self._drag_screen_points:
                        self._drag_screen_points = [screen_start]
                    if tuple(self._drag_screen_points[-1][:2]) != tuple(screen_end[:2]):
                        # Shape tools do not need a full stroke history, but the
                        # last real screen endpoint is essential when Maya's
                        # release callback arrives one tick late.
                        self._drag_screen_points.append(screen_end)
                    self._update_drag_preview(self._tool_points_from_screen_drag_cached(options.get("tool"), layer, screen_start, screen_end, mapping_cache=self._drag_mapping_cache))
        except Exception:
            # Treat a transient viewport/mapping error as a dropped sample. A
            # preview failure must not end a mouse-held Pencil gesture early;
            # release still captures the current cursor and performs cleanup.
            try:
                self._capture_drag_cursor_tail()
            except Exception:
                pass
            return False

    def _draw_context_release(self):
        if self._drag_options.get("blocked_press"):
            self._drag_options["blocked_press"] = False
            return False
        try:
            drag_point = cmds.draggerContext(DRAW_CONTEXT_NAME, query=True, dragPoint=True)
        except Exception:
            drag_point = None
        options = dict(self._drag_options)
        layer = options.get("layer_node") or self.active_layer()
        try:
            # Press uses an earlier cursor position.  Re-reading QCursor during
            # release would collapse lines, arrows, rectangles, and ellipses to a
            # point, so retain the mapped press point for the whole gesture.
            mapping_cache = self._drag_mapping_cache or {}
            cursor_screen = _active_m3dview_logical_cursor_point(mapping_cache.get("view"), mapping_cache.get("widget"))
            screen_start = self._drag_anchor or (self._drag_screen_points[0] if self._drag_screen_points else None) or cursor_screen or (640, 360, 0)
            last_shape_screen = self._drag_screen_points[-1] if self._drag_screen_points else None
            # Prefer the exact release cursor when it is inside the cached
            # widget. If Maya omitted that callback, the last drag sample is
            # still a real screen endpoint; never fall back to two layer-local
            # corners for an interactive rectangle.
            screen_end = cursor_screen or drag_point or last_shape_screen or screen_start
            start_point = self._drag_start_point or _screen_to_layer_point(layer, screen_start, mapping_cache=self._drag_mapping_cache)
            end_point = _screen_to_layer_point(layer, screen_end, mapping_cache=self._drag_mapping_cache) if options.get("tool") not in STROKE_PATH_TOOLS else start_point
            if options.get("tool") == "Eraser":
                if drag_point:
                    release_point = _screen_to_layer_point(layer, drag_point, mapping_cache=self._drag_mapping_cache)
                    self._append_drag_sample(layer, screen_point=drag_point, layer_point=release_point, minimum_distance=0.001)
                self._capture_drag_cursor_tail(layer)
                self._update_eraser_preview(self._drag_points, force=True)
                self._discard_eraser_preview()
                self._discard_drag_preview()
                self._end_drag_preview_session()
                self.erase_marks_with_stroke(
                    layer,
                    self._drag_points or [start_point, end_point],
                    radius=max(0.04, float(options.get("size", 2.0)) * 0.03),
                    whole_stroke=options.get("eraser_mode") == "whole",
                )
                return
            create_options = dict(options)
            create_options.pop("eraser_mode", None)
            create_options.pop("blocked_press", None)
            if options.get("tool") in ("Pencil", "Brush"):
                if drag_point:
                    release_point = _screen_to_layer_point(layer, drag_point, mapping_cache=self._drag_mapping_cache)
                    self._append_drag_sample(layer, screen_point=drag_point, layer_point=release_point, minimum_distance=0.001)
                # The draggerContext release coordinate can still be the last
                # pre-hitch callback. Append the actual cursor only after that
                # callback point so the tail never bends backwards.
                self._capture_drag_cursor_tail(layer)
                self._update_drag_preview(self._drag_points, force=True)
                self._discard_drag_preview()
                self._end_drag_preview_session()
                self.create_freehand_mark(points=self._drag_points, **create_options)
            else:
                preview_points = self._tool_points_from_screen_drag_cached(
                    options.get("tool"),
                    layer,
                    screen_start,
                    screen_end,
                    mapping_cache=self._drag_mapping_cache,
                ) if screen_start is not None and screen_end is not None else []
                if preview_points:
                    self._update_drag_preview(preview_points, force=True)
                self._discard_drag_preview()
                self._end_drag_preview_session()
                self.create_mark_from_drag(
                    start_point=start_point,
                    end_point=end_point,
                    screen_start=screen_start,
                    screen_end=screen_end,
                    mapping_cache=self._drag_mapping_cache,
                    **create_options
                )
        finally:
            self._stop_drag_cursor_capture()
            self._discard_eraser_preview()
            self._discard_drag_preview()
            self._end_drag_preview_session()
            self._drag_mapping_cache = None

    def _marquee_context_press(self):
        try:
            self._marquee_anchor = cmds.draggerContext(MARQUEE_CONTEXT_NAME, query=True, anchorPoint=True)
        except Exception:
            self._marquee_anchor = None
        options = dict(self._marquee_options)
        self._marquee_blocked_press = False
        layer = options.get("layer_node") or self.active_layer()
        expected_camera = _get_string_attr(layer, "animatorsPencilCamera", "") if layer and cmds.objExists(layer) else ""
        input_camera = _drawing_input_camera()
        if expected_camera and input_camera and _long_name(expected_camera) != _long_name(input_camera):
            self._marquee_blocked_press = True
            self._marquee_screen_points = []
            self._marquee_start_point = None
            self._marquee_mapping_cache = None
            self._status("Marquee inside the Aminate Reference Viewer or its Pencil View so the box stays in camera perspective.")
            return False
        if not layer or not cmds.objExists(layer):
            return False
        self._marquee_mapping_cache = self._build_drag_mapping_cache(layer)
        anchor = self._marquee_anchor or _active_m3dview_logical_cursor_point(
            (self._marquee_mapping_cache or {}).get("view"),
            (self._marquee_mapping_cache or {}).get("widget"),
        ) or (0, 0, 0)
        self._marquee_anchor = anchor
        self._marquee_screen_points = [anchor]
        self._marquee_start_point = _screen_to_layer_point(
            layer,
            anchor,
            mapping_cache=self._marquee_mapping_cache,
        )
        self._discard_marquee_preview()

    def _marquee_context_drag(self):
        if self._marquee_blocked_press:
            return False
        try:
            drag_point = cmds.draggerContext(MARQUEE_CONTEXT_NAME, query=True, dragPoint=True)
        except Exception:
            drag_point = None
        layer = self._marquee_options.get("layer_node") or self.active_layer()
        if not layer or not cmds.objExists(layer):
            return False
        mapping_cache = self._marquee_mapping_cache or {}
        screen_start = self._marquee_screen_points[0] if self._marquee_screen_points else self._marquee_anchor or (0, 0, 0)
        cursor_screen = _active_m3dview_logical_cursor_point(
            mapping_cache.get("view"), mapping_cache.get("widget")
        )
        screen_end = cursor_screen or drag_point or (self._marquee_screen_points[-1] if self._marquee_screen_points else screen_start)
        if not self._marquee_screen_points:
            self._marquee_screen_points = [screen_start]
        if tuple(self._marquee_screen_points[-1][:2]) != tuple(screen_end[:2]):
            self._marquee_screen_points.append(screen_end)
        rectangle_points = self._tool_points_from_screen_drag_cached(
            "Rectangle",
            layer,
            screen_start,
            screen_end,
            mapping_cache=self._marquee_mapping_cache,
        )
        bounds = self._bounds_from_points(rectangle_points)
        self._update_marquee_preview(bounds, layer_node=layer, points=rectangle_points)
        return True

    def _marquee_context_release(self):
        try:
            drag_point = cmds.draggerContext(MARQUEE_CONTEXT_NAME, query=True, dragPoint=True)
        except Exception:
            drag_point = None
        if self._marquee_blocked_press:
            self._marquee_blocked_press = False
            self._marquee_anchor = None
            self._marquee_screen_points = []
            self._marquee_start_point = None
            self._marquee_mapping_cache = None
            return False
        options = dict(self._marquee_options)
        layer = options.get("layer_node") or self.active_layer()
        mapping_cache = self._marquee_mapping_cache or {}
        screen_start = self._marquee_screen_points[0] if self._marquee_screen_points else self._marquee_anchor or (0, 0, 0)
        cursor_screen = _active_m3dview_logical_cursor_point(
            mapping_cache.get("view"), mapping_cache.get("widget")
        )
        screen_end = cursor_screen or drag_point or (self._marquee_screen_points[-1] if self._marquee_screen_points else screen_start)
        rectangle_points = self._tool_points_from_screen_drag_cached(
            "Rectangle",
            layer,
            screen_start,
            screen_end,
            mapping_cache=self._marquee_mapping_cache,
        )
        bounds = self._bounds_from_points(rectangle_points)
        self._discard_marquee_preview()
        self._marquee_blocked_press = False
        self._marquee_anchor = None
        self._marquee_screen_points = []
        self._marquee_start_point = None
        self._marquee_mapping_cache = None
        picked = self.select_marks_in_box(
            layer,
            (bounds[0], bounds[1], 0.0),
            (bounds[2], bounds[3], 0.0),
            add=options.get("add", False),
        )
        transform_box = self._show_marquee_transform_box(layer, picked)
        if transform_box:
            self._status(
                "Marquee kept {0} pencil section(s). Drag the screen box to move; use Scale Gizmo to resize.".format(len(picked))
            )
        elif picked:
            self._status("Marquee selected {0} complete pencil mark(s).".format(len(picked)))

    def delete_selected_marks(self):
        marks = self.selected_marks()
        if marks:
            cmds.delete(marks)
            self._status("Selected pencil marks deleted.")

    def copy_selected_marks(self, cut=False):
        self.clipboard = []
        for mark in self.selected_marks():
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            data["source"] = mark
            data["matrix"] = cmds.xform(mark, query=True, matrix=True, objectSpace=True)
            self.clipboard.append(data)
        if cut and self.selected_marks():
            cmds.delete(self.selected_marks())
        self._status("{0} mark(s) copied.".format(len(self.clipboard)))

    def paste_marks(self, layer_node=None):
        layer_node = layer_node or self.active_layer()
        pasted = []
        for item in self.clipboard:
            source = item.get("source")
            if source and cmds.objExists(source):
                dup = cmds.duplicate(source, name="amirPencilPasted_MARK")[0]
                dup = _parent_if_needed(dup, layer_node)
                cmds.xform(dup, matrix=item.get("matrix"), objectSpace=True)
                cmds.move(0.2, -0.2, 0.0, dup, relative=True, objectSpace=True)
                self._mark_node(dup, layer_node, item.get("tool", "Pencil"), item.get("color", (1, 0, 0)), item.get("opacity", 1.0), item.get("size", 2.0))
                pasted.append(dup)
        if pasted:
            cmds.select(pasted, replace=True)
        self._status("{0} mark(s) pasted.".format(len(pasted)))
        return pasted

    def transform_selected(self, tx=0.0, ty=0.0, rotate=0.0, scale=1.0):
        marks = self.selected_marks()
        for mark in marks:
            cmds.move(tx, ty, 0.0, mark, relative=True, objectSpace=True)
            if rotate:
                cmds.rotate(0.0, 0.0, rotate, mark, relative=True, objectSpace=True)
            if abs(scale - 1.0) > 0.001:
                cmds.scale(scale, scale, scale, mark, relative=True, objectSpace=True)
        self._status("Transformed {0} mark(s).".format(len(marks)))

    def set_marks_translucent(self, layer_node=None, enabled=True):
        layer_node = layer_node or self.active_layer()
        marks = self.selected_marks() or self.marks(layer_node)
        display_type = 1 if enabled else 0
        changed = 0
        for mark in marks:
            _ensure_attr(mark, TRANSLUCENT_MARKS_ATTR, "bool", bool(enabled))
            cmds.setAttr(mark + "." + TRANSLUCENT_MARKS_ATTR, bool(enabled))
            for shape in _mark_shapes(mark):
                if cmds.objExists(shape + ".overrideEnabled"):
                    cmds.setAttr(shape + ".overrideEnabled", True)
                if cmds.objExists(shape + ".overrideDisplayType"):
                    cmds.setAttr(shape + ".overrideDisplayType", display_type)
                    changed += 1
        self._status("{0} translucent pencil mark shape(s).".format("Enabled" if enabled else "Disabled"))
        return {"enabled": bool(enabled), "marks": len(marks), "shapes": changed}

    def toggle_marks_translucent(self, layer_node=None):
        layer_node = layer_node or self.active_layer()
        marks = self.selected_marks() or self.marks(layer_node)
        any_enabled = False
        for mark in marks:
            if cmds.attributeQuery(TRANSLUCENT_MARKS_ATTR, node=mark, exists=True) and cmds.getAttr(mark + "." + TRANSLUCENT_MARKS_ATTR):
                any_enabled = True
                break
        return self.set_marks_translucent(layer_node, enabled=not any_enabled)

    def default_shortcut_bindings(self):
        return dict(DEFAULT_SHORTCUTS)

    def activate_viewport_transform(self, mode="move"):
        marks = self.selected_marks()
        if not marks:
            marks = self.marks()
            if marks:
                cmds.select(marks, replace=True)
        if not marks:
            self._status("No pencil marks to transform.")
            return False
        mode = (mode or "move").lower()
        context_map = {
            "move": "moveSuperContext",
            "rotate": "RotateSuperContext",
            "scale": "scaleSuperContext",
        }
        context = context_map.get(mode, "moveSuperContext")
        try:
            cmds.setToolTo(context)
        except Exception:
            context = "selectSuperContext"
            cmds.setToolTo(context)
        self._status("Viewport {0} gizmo is active for {1} pencil mark(s).".format(mode, len(marks)))
        return True

    def transform_layer(self, layer_node=None, tx=0.0, ty=0.0, rotate=0.0, scale=1.0):
        layer_node = layer_node or self.active_layer()
        if not layer_node or not cmds.objExists(layer_node):
            return
        cmds.move(tx, ty, 0.0, layer_node, relative=True, objectSpace=True)
        if rotate:
            cmds.rotate(0.0, 0.0, rotate, layer_node, relative=True, objectSpace=True)
        if abs(scale - 1.0) > 0.001:
            cmds.scale(scale, scale, scale, layer_node, relative=True, objectSpace=True)
        self._status("Layer transformed.")

    def add_key(self):
        marks = self.selected_marks() or self.marks()
        for mark in marks:
            cmds.setKeyframe(mark, attribute=("translate", "rotate", "scale", "visibility"), time=_current_frame(), shape=False)
        self._status("Keyed {0} mark(s).".format(len(marks)))

    def remove_key(self):
        marks = self.selected_marks() or self.marks()
        frame = _current_frame()
        for mark in marks:
            cmds.cutKey(mark, time=(frame, frame), clear=True)
        self._status("Removed keys on frame {0}.".format(frame))

    def duplicate_previous_key(self, layer_node=None):
        layer_node = layer_node or self.active_layer()
        frame = _current_frame()
        created = []
        candidates = []
        for mark in self.marks(layer_node):
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            mark_frame = int(data.get("frame", cmds.getAttr(mark + ".animatorsPencilFrame") if cmds.objExists(mark + ".animatorsPencilFrame") else 0))
            if mark_frame < frame:
                candidates.append((mark_frame, mark))
        if not candidates:
            self._status("No previous drawing key found.")
            return []
        previous_frame = max(item[0] for item in candidates)
        for _, mark in [item for item in candidates if item[0] == previous_frame]:
            dup = cmds.duplicate(mark, name="amirPencilDupKey_MARK")[0]
            dup = _parent_if_needed(dup, layer_node)
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            self._mark_node(dup, layer_node, data.get("tool", "Pencil"), data.get("color", (1, 0, 0)), data.get("opacity", 1.0), data.get("size", 2.0), frame=frame)
            created.append(dup)
        if created:
            cmds.select(created, replace=True)
        self._status("Duplicated frame {0} drawing to frame {1}.".format(previous_frame, frame))
        return created

    def retime_selected(self, offset=1):
        marks = self.selected_marks()
        for mark in marks:
            if not cmds.objExists(mark + ".animatorsPencilFrame"):
                continue
            old_frame = int(cmds.getAttr(mark + ".animatorsPencilFrame"))
            new_frame = old_frame + int(offset)
            cmds.setAttr(mark + ".animatorsPencilFrame", new_frame)
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            data["frame"] = new_frame
            _set_json_attr(mark, "animatorsPencilMarkData", data)
            self._key_mark_visibility(mark, data.get("layer") or self.active_layer(), new_frame)
        self._status("Retimed {0} mark(s).".format(len(marks)))

    def create_frame_marker(self, color=(1.0, 0.9, 0.05), label="Marker"):
        layer = self.active_layer()
        mark = self.create_mark("Text", layer, color=color, size=2.0, opacity=1.0, text="{0} F{1}".format(label, _current_frame()))
        if mark:
            _set_string_attr(mark, "animatorsPencilFrameMarker", "marker")
        return mark

    def refresh_camera_scope(self, force=False, layer_data=None):
        if not MAYA_AVAILABLE or not self._camera_scope_enabled:
            return False
        active_camera = _current_camera()
        active_identity = (
            _long_name(active_camera) if active_camera and cmds.objExists(active_camera) else active_camera,
            tuple(sorted(self._additional_visible_cameras)),
        )
        if not force and not self._camera_scope_dirty and active_identity == self._last_camera_scope_identity:
            return False
        changed_layers = []
        for layer in (layer_data if layer_data is not None else self.layers(include_count=False)):
            node = layer.get("node")
            self._apply_layer_visibility(node, active_camera, changed_layers=changed_layers)
        if changed_layers:
            self._force_layer_display_evaluation(changed_layers)
        self._last_camera_scope_identity = active_identity
        self._camera_scope_dirty = False
        return True

    def set_camera_scope(self, enabled=True):
        self._camera_scope_enabled = bool(enabled)
        if self._camera_scope_enabled:
            self._camera_scope_dirty = True
            self.refresh_camera_scope(force=True)
        else:
            for layer in self.layers(include_count=False):
                node = layer.get("node")
                self._apply_layer_visibility(node)
            self._last_camera_scope_identity = None
            self._camera_scope_dirty = False
        self._status("Camera layer scope {0}.".format("enabled" if self._camera_scope_enabled else "showing all layers"))

    def refresh_onion_skin(self):
        if not MAYA_AVAILABLE or not self._onion_options:
            return
        options = dict(self._onion_options)
        self.make_ghosts(
            options.get("layer_node") or self.active_layer(),
            before=options.get("before", 1),
            after=options.get("after", 1),
            before_color=options.get("before_color", (0.1, 0.6, 1.0)),
            after_color=options.get("after_color", (1.0, 0.4, 0.1)),
            opacity=options.get("opacity", 0.35),
        )
        self.refresh_camera_scope()

    def enable_onion_skin(self, layer_node=None, before=1, after=1, opacity=0.35, before_color=(0.1, 0.6, 1.0), after_color=(1.0, 0.4, 0.1)):
        self._onion_options = {
            "layer_node": layer_node or self.active_layer(),
            "before": max(0, int(before)),
            "after": max(0, int(after)),
            "opacity": max(0.05, min(1.0, float(opacity))),
            "before_color": tuple(before_color),
            "after_color": tuple(after_color),
        }
        if not self._onion_job:
            try:
                self._onion_job = cmds.scriptJob(event=["timeChanged", self.refresh_onion_skin], protected=True, killWithScene=True)
            except Exception:
                self._onion_job = 0
        self.refresh_onion_skin()
        self._status("Live Onion Skin enabled.")
        return self._onion_job

    def disable_onion_skin(self):
        if self._onion_job:
            try:
                if cmds.scriptJob(exists=self._onion_job):
                    cmds.scriptJob(kill=self._onion_job)
            except Exception:
                pass
        self._onion_job = 0
        self._onion_options = {}
        self.clear_ghosts()
        self._status("Live Onion Skin disabled.")

    def make_ghosts(self, layer_node=None, before=1, after=1, before_color=(0.1, 0.6, 1.0), after_color=(1.0, 0.4, 0.1), opacity=0.35):
        layer_node = layer_node or self.active_layer()
        ghost_root = "amirAnimatorsPencilGhosts_GRP"
        if cmds.objExists(ghost_root):
            cmds.delete(ghost_root)
        ghost_root = cmds.createNode("transform", name=ghost_root)
        frame = _current_frame()
        count = 0
        for mark in self.marks(layer_node):
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            mark_frame = int(data.get("frame", 0))
            if frame - before <= mark_frame < frame:
                color = before_color
            elif frame < mark_frame <= frame + after:
                color = after_color
            else:
                continue
            dup = cmds.duplicate(mark, name="amirPencilGhost_MARK")[0]
            dup = _parent_if_needed(dup, ghost_root)
            try:
                cmds.cutKey(dup, attribute="visibility", clear=True)
                cmds.setAttr(dup + ".visibility", True)
            except Exception:
                pass
            _set_display_color(dup, color, opacity=opacity, line_width=max(1.0, float(data.get("size", 2.0)) * 0.75))
            count += 1
        self._status("Ghosts rebuilt: {0}".format(count))
        return ghost_root

    def clear_ghosts(self):
        if cmds.objExists("amirAnimatorsPencilGhosts_GRP"):
            cmds.delete("amirAnimatorsPencilGhosts_GRP")

    def undo(self):
        if MAYA_AVAILABLE:
            cmds.undo()

    def redo(self):
        if MAYA_AVAILABLE:
            cmds.redo()


def _animators_pencil_draw_press():
    if GLOBAL_DRAG_CONTEXT_CONTROLLER:
        GLOBAL_DRAG_CONTEXT_CONTROLLER._draw_context_press()


def _animators_pencil_draw_drag():
    if GLOBAL_DRAG_CONTEXT_CONTROLLER:
        GLOBAL_DRAG_CONTEXT_CONTROLLER._draw_context_drag()


def _animators_pencil_draw_release():
    if GLOBAL_DRAG_CONTEXT_CONTROLLER:
        GLOBAL_DRAG_CONTEXT_CONTROLLER._draw_context_release()


def _animators_pencil_marquee_press():
    if GLOBAL_DRAG_CONTEXT_CONTROLLER:
        GLOBAL_DRAG_CONTEXT_CONTROLLER._marquee_context_press()


def _animators_pencil_marquee_drag():
    if GLOBAL_DRAG_CONTEXT_CONTROLLER:
        GLOBAL_DRAG_CONTEXT_CONTROLLER._marquee_context_drag()


def _animators_pencil_marquee_release():
    if GLOBAL_DRAG_CONTEXT_CONTROLLER:
        GLOBAL_DRAG_CONTEXT_CONTROLLER._marquee_context_release()


class AnimatorsPencilShapeLibraryWindow(QtWidgets.QDialog):
    def __init__(self, controller, create_callback, parent=None):
        super(AnimatorsPencilShapeLibraryWindow, self).__init__(parent)
        self.controller = controller
        self.create_callback = create_callback
        self.setObjectName("mayaAnimatorsPencilShapeLibraryWindow")
        self.setWindowTitle("Animator's Pencil Shape Library")
        self.setMinimumSize(320, 300)
        self.resize(420, 420)
        layout = QtWidgets.QVBoxLayout(self)
        self.layout_root = layout
        hint = QtWidgets.QLabel("Choose a preset. The shape is created on the active layer at the current frame.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.preset_name = QtWidgets.QLineEdit()
        self.preset_name.setPlaceholderText("Name selected mark preset")
        self.save_preset_button = QtWidgets.QPushButton("Save Selected As Preset")
        self.delete_preset_button = QtWidgets.QPushButton("Delete User Preset")
        preset_row = QtWidgets.QHBoxLayout()
        preset_row.addWidget(self.preset_name, 1)
        preset_row.addWidget(self.save_preset_button)
        preset_row.addWidget(self.delete_preset_button)
        layout.addLayout(preset_row)
        self.grid = QtWidgets.QGridLayout()
        layout.addLayout(self.grid)
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.hide)
        layout.addWidget(close_button)
        self.save_preset_button.clicked.connect(self._save_selected_preset)
        self.delete_preset_button.clicked.connect(self._delete_user_preset)
        self._build_buttons()

    def _build_buttons(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        library = self.controller.shape_library()
        for index, name in enumerate(library.keys()):
            button = QtWidgets.QPushButton(name)
            button.setIcon(_make_tool_icon(library[name].get("tool", "Pencil")))
            button.setToolTip("Create {0} preset.".format(name))
            button.clicked.connect(lambda _checked=False, shape_name=name: self.create_callback(shape_name))
            self.grid.addWidget(button, index // 3, index % 3)

    def _save_selected_preset(self):
        name = self.preset_name.text().strip()
        success, _message = self.controller.save_shape_preset(name)
        if success:
            self._build_buttons()

    def _delete_user_preset(self):
        name = self.preset_name.text().strip()
        success, _message = self.controller.delete_shape_preset(name)
        if success:
            self._build_buttons()


class AnimatorsPencilViewportNavigationFilter(QtCore.QObject):
    """Switch one fixed Pencil View to persp before Maya handles navigation."""

    def __init__(self, panel):
        super(AnimatorsPencilViewportNavigationFilter, self).__init__(panel)
        self.panel = panel
        self._widgets = []

    def refresh(self):
        if not MAYA_AVAILABLE:
            self.clear()
            return
        resolved = []
        for panel_name in cmds.getPanel(type="modelPanel") or []:
            widget = _model_panel_viewport_widget(panel_name)
            if not (_qt_object_valid(widget) and widget.isVisible()):
                continue
            candidates = [widget]
            owner = widget.parentWidget()
            while _qt_object_valid(owner):
                candidates.append(owner)
                if str(owner.objectName() or "") == panel_name:
                    break
                owner = owner.parentWidget()
            resolved_ids = {id(candidate) for candidate in resolved}
            for candidate in candidates:
                if id(candidate) not in resolved_ids:
                    resolved.append(candidate)
                    resolved_ids.add(id(candidate))
        resolved_ids = {id(widget) for widget in resolved}
        for widget in list(self._widgets):
            if id(widget) not in resolved_ids or not _qt_object_valid(widget):
                try:
                    if _qt_object_valid(widget):
                        widget.removeEventFilter(self)
                except Exception:
                    pass
                self._widgets.remove(widget)
        installed_ids = {id(widget) for widget in self._widgets}
        for widget in resolved:
            if id(widget) in installed_ids:
                continue
            try:
                widget.installEventFilter(self)
                self._widgets.append(widget)
                installed_ids.add(id(widget))
            except Exception:
                continue

    def clear(self):
        for widget in list(self._widgets):
            try:
                if _qt_object_valid(widget):
                    widget.removeEventFilter(self)
            except Exception:
                pass
        self._widgets = []

    def _is_alt_navigation_event(self, event):
        alt_modifier = _qt_flag("KeyboardModifier", "AltModifier", None)
        try:
            has_alt = bool(alt_modifier is not None and event.modifiers() & alt_modifier)
        except Exception:
            has_alt = False
        event_type = event.type()
        if event_type == _qt_event_type("Wheel"):
            return has_alt
        if event_type == _qt_event_type("MouseButtonPress"):
            try:
                buttons = event.button()
            except Exception:
                return False
        elif event_type == _qt_event_type("MouseMove"):
            try:
                buttons = event.buttons()
            except Exception:
                return False
        else:
            return False
        left = _qt_flag("MouseButton", "LeftButton", None)
        middle = _qt_flag("MouseButton", "MiddleButton", None)
        right = _qt_flag("MouseButton", "RightButton", None)
        if not has_alt:
            # Maya's middle-button viewport navigation is the safe fallback
            # when a transport cannot carry the Alt modifier.  Left-button
            # drawing and right-button context actions must remain untouched.
            return middle is not None and bool(buttons & middle)
        return any(button is not None and bool(buttons & button) for button in (left, middle, right))

    def eventFilter(self, watched, event):
        if self._is_alt_navigation_event(event):
            self.panel._prepare_viewport_navigation(watched)
        return False


class AnimatorsPencilColorSwatchWindow(QtWidgets.QDialog):
    def __init__(self, panel, parent=None):
        super(AnimatorsPencilColorSwatchWindow, self).__init__(parent)
        self.panel = panel
        self._syncing_color = False
        self._swatch_values = []
        self.swatch_buttons = []
        self.setObjectName("mayaAnimatorsPencilColorSwatchWindow")
        self.setWindowTitle("Animator's Pencil Colour Picker + Swatches")
        self.setMinimumSize(360, 420)
        self.resize(460, 520)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        heading = QtWidgets.QLabel("Colour Picker + Saved Swatches")
        heading.setObjectName("animatorsPencilColorSwatchHeading")
        heading.setAccessibleName("RGB Colour and Saved Swatches")
        layout.addWidget(heading)

        hint = QtWidgets.QLabel("Change RGB values or choose a saved swatch. The next stroke updates immediately.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.color_dialog = QtWidgets.QColorDialog(self)
        self.color_dialog.setObjectName("animatorsPencilEmbeddedRgbColorDialog")
        self.color_dialog.setAccessibleName("Animator Pencil RGB colour picker")
        for option_name in ("DontUseNativeDialog", "NoButtons", "ShowAlphaChannel"):
            option = _color_dialog_option(option_name)
            if option is not None:
                self.color_dialog.setOption(option, option_name != "ShowAlphaChannel")
        widget_flag = _qt_flag("WindowType", "Widget", getattr(QtCore.Qt, "Widget", None))
        if widget_flag is not None:
            self.color_dialog.setWindowFlags(widget_flag)
        expanding_policy = _size_policy_value("Expanding")
        if expanding_policy is not None:
            self.color_dialog.setSizePolicy(expanding_policy, expanding_policy)
        self.color_dialog.setMinimumHeight(240)
        layout.addWidget(self.color_dialog, 1)

        swatch_label = QtWidgets.QLabel("Saved Swatches")
        swatch_label.setAccessibleName("Saved pencil colour swatches")
        layout.addWidget(swatch_label)
        self.swatch_grid = QtWidgets.QGridLayout()
        self.swatch_grid.setContentsMargins(0, 0, 0, 0)
        self.swatch_grid.setSpacing(6)
        layout.addLayout(self.swatch_grid)

        buttons = QtWidgets.QHBoxLayout()
        self.save_button = QtWidgets.QPushButton("Save Current Swatch")
        self.save_button.setObjectName("animatorsPencilSaveCurrentSwatchButton")
        self.save_button.setAccessibleName("Save current pencil colour as a swatch")
        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.setObjectName("animatorsPencilCloseColorSwatchButton")
        buttons.addWidget(self.save_button, 1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.color_dialog.currentColorChanged.connect(self._color_changed)
        self.save_button.clicked.connect(self.panel._save_swatch)
        self.close_button.clicked.connect(self.hide)

    def show_for_color(self, color):
        self.set_current_color(color)
        self.refresh_swatches()
        self.show()
        self.raise_()
        self.activateWindow()

    def set_current_color(self, color):
        self._syncing_color = True
        try:
            self.color_dialog.setCurrentColor(QtGui.QColor.fromRgbF(*tuple(color)))
        finally:
            self._syncing_color = False

    def _color_changed(self, color):
        if self._syncing_color or not color.isValid():
            return
        self.panel._apply_selected_color((color.redF(), color.greenF(), color.blueF()), update_window=False)

    def _use_swatch_button(self, button):
        raw_index = button.property("aminateSwatchIndex")
        index = int(raw_index) if raw_index is not None else -1
        if 0 <= index < len(self._swatch_values):
            self.panel._use_swatch(self._swatch_values[index])

    def refresh_swatches(self):
        self._swatch_values = [tuple(value) for value in self.panel.controller.swatches()]
        while len(self.swatch_buttons) < len(self._swatch_values):
            button = QtWidgets.QPushButton()
            button.setMinimumHeight(30)
            button.clicked.connect(lambda _checked=False, widget=button: self._use_swatch_button(widget))
            self.swatch_grid.addWidget(button, len(self.swatch_buttons) // 4, len(self.swatch_buttons) % 4)
            self.swatch_buttons.append(button)
        for index, button in enumerate(self.swatch_buttons):
            if index >= len(self._swatch_values):
                button.hide()
                continue
            color = self._swatch_values[index]
            button.setProperty("aminateSwatchIndex", index)
            button.setText("Swatch {0}".format(index + 1))
            button.setAccessibleName("Use saved pencil swatch {0}".format(index + 1))
            button.setToolTip("Use saved pencil swatch {0}".format(index + 1))
            self.panel._set_color_button(button, color)
            button.show()
    def closeEvent(self, event):
        self.hide()
        event.ignore()


class AnimatorsPencilPanel(QtWidgets.QWidget):
    def __init__(self, controller=None, parent=None, video_reference_controller=None, reference_package_controller=None):
        super(AnimatorsPencilPanel, self).__init__(parent)
        self.controller = controller or AnimatorsPencilController()
        self.video_reference_controller = video_reference_controller or maya_video_reference_tool.MayaVideoReferenceController()
        self.reference_package_controller = reference_package_controller or maya_reference_manager.ReferencePackageController()
        self._selected_color = tuple(DEFAULT_COLORS["Red"])
        self._onion_before_color = (0.1, 0.6, 1.0)
        self._onion_after_color = (1.0, 0.4, 0.1)
        self._shape_library_window = None
        self._color_swatch_window = None
        self.controller.set_status_callback(self._set_status)
        self.current_layer = ""
        self._shortcuts = {}
        self._runtime_shortcuts = {}
        self._runtime_shortcut_root = None
        self._brush_shortcut_pair = ()
        self._marking_menus = []
        self._marking_menu_conflicts = []
        self._marking_menu_errors = []
        self._marking_menu_trigger = ""
        self._cursor_widgets = []
        self._brush_cursor_radius = 0
        self._runtime_input_active = False
        self._drawing_enabled = False
        # Track the viewport gesture that owns Maya's current dragger context.
        # Qt setting edits can briefly move focus away from the viewport; the
        # next edit must restore the same gesture instead of stranding it.
        self._viewport_input_mode = ""
        self._video_overlay_camera = ""
        self._video_overlay_transform = ""
        self._video_normal_camera = ""
        self._video_in_draw_over_mode = False
        # Pinned/floating viewers keep their window behaviour, but attaching
        # a video also hands its Pencil View to the active main viewport.  The
        # flag makes that handoff reversible without conflating it with the
        # legacy full-main-view mode above.
        self._video_camera_handoff_active = False
        self._video_display_mode = "pinned"
        self._video_anchor_panel = ""
        self._video_viewer_visible = False
        # The retained reference viewer needs its camera layer globally alive
        # for its own modelPanel, while the ordinary Maya panels must continue
        # to be clean animation workspaces.  These per-panel connections hold
        # the current scene list with only the viewer-camera Pencil nodes
        # removed; they are temporary and are rebuilt when that layer changes.
        self._reference_viewer_panel_states = {}
        self._reference_viewer_panel_connections = {}
        self._reference_viewer_scope_signature = None
        self._video_scale_user_edited = False
        self._video_last_placement = "top_right"
        self._pending_package_scene_state = None
        self._previous_tool_context = ""
        self._viewport_navigation_filter = AnimatorsPencilViewportNavigationFilter(self)
        self._build_ui()
        self._reflow_action_groups()
        self._install_shortcuts()
        if MAYA_AVAILABLE:
            self.current_layer = self.controller.active_layer()
            self._restore_video_draw_over_state()
        self.refresh_drawing_views()
        self.refresh_layers()
        self._refresh_swatches()
        self._apply_selected_color(self._selected_color, update_window=False)
        self._set_color_button(self.onion_before_color_button, self._onion_before_color)
        self._set_color_button(self.onion_after_color_button, self._onion_after_color)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        # Keep a small, readable breathing room while allowing the full Pencil
        # panel to reflow inside a 360px Maya dock (the outer scroll viewport
        # is only 328px wide at that size).
        layout.setContentsMargins(6, 6, 6, 6)

        intro = QtWidgets.QLabel(
            "Choose a tool and colour, then press Start Drawing once. Aminate saves the current angle as a fixed Pencil "
            "View and draws on its camera layer. Tool, colour, size, opacity, and layer changes update the next stroke. "
            "New marks use the current frame by default. Press E for current-layer erasure."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.active_tool_strip = QtWidgets.QGroupBox("Active Drawing")
        self.active_tool_strip.setObjectName("animatorsPencilActiveToolStrip")
        self.active_tool_strip.setAccessibleName("Animator Pencil active drawing tools")
        self.active_tool_strip.setToolTip("Pinned drawing controls. These two rows stay directly above Pencil layers.")
        self.active_tool_layout = QtWidgets.QGridLayout(self.active_tool_strip)
        self.active_tool_layout.setContentsMargins(6, 6, 6, 6)
        self.active_tool_layout.setHorizontalSpacing(5)
        self.active_tool_layout.setVerticalSpacing(5)

        self.start_drawing_button = QtWidgets.QPushButton("Start Drawing")
        self.start_drawing_button.setObjectName("animatorsPencilStartDrawingButton")
        self.start_drawing_button.setAccessibleName("Start or stop Animator Pencil drawing")
        self.start_drawing_button.setProperty("aminateDrawingActive", False)
        self.start_drawing_button.setCheckable(True)
        self.start_drawing_button.setIcon(_make_tool_icon("Pencil", QtGui.QColor("#7BD88F")))
        self.start_drawing_button.setToolTip("Start persistent drawing in the active Maya viewport. Click again to stop.")
        self.drag_draw_button = self.start_drawing_button

        self.tool_combo = QtWidgets.QComboBox()
        self.tool_combo.setObjectName("animatorsPencilToolCombo")
        self.tool_combo.setAccessibleName("Active Animator Pencil tool")
        self.tool_combo.setToolTip("Open this list to choose any drawing or shape tool. Selection arms the tool immediately.")
        for tool_name in TOOL_NAMES:
            self.tool_combo.addItem(_make_tool_icon(tool_name), tool_name)

        self.pick_color_button = QtWidgets.QPushButton("Pick Colour…")
        self.pick_color_button.setObjectName("animatorsPencilOpenColorSwatchButton")
        self.pick_color_button.setIcon(_make_tool_icon("ColorPicker", QtGui.QColor("#F8FAFC")))
        self.pick_color_button.setAccessibleName("Open the Animator Pencil colour picker")
        self.pick_color_button.setToolTip("Open the colour picker for the active drawing colour.")

        self.swatch_buttons = []
        self.quick_swatches_widget = QtWidgets.QWidget(self.active_tool_strip)
        self.quick_swatches_widget.setObjectName("animatorsPencilQuickSwatches")
        self.quick_swatches_widget.setAccessibleName("Animator Pencil quick colour swatches")
        self.quick_swatches_widget.setToolTip("One-click quick colour swatches. The outlined swatch is active.")
        self.quick_swatches_layout = QtWidgets.QGridLayout(self.quick_swatches_widget)
        # Keep the swatch row taller than the native button paint area. Maya's
        # dock stylesheet can draw a border outside a 22px button rect; the
        # extra inset prevents the bottom edge (especially the black swatch)
        # from being clipped by the following Size field at narrow widths.
        self.quick_swatches_layout.setContentsMargins(3, 3, 3, 3)
        self.quick_swatches_layout.setSpacing(3)
        self.quick_swatches_widget.setMinimumHeight(30)

        self.size_spin = QtWidgets.QDoubleSpinBox()
        self.size_spin.setObjectName("animatorsPencilBrushSizeSpin")
        self.size_spin.setAccessibleName("Pencil brush size")
        self.size_spin.setRange(1.0, 24.0)
        self.size_spin.setSingleStep(1.0)
        self.size_spin.setDecimals(0)
        self.size_spin.setPrefix("Size ")
        self.size_spin.setValue(3.0)
        self.size_spin.setToolTip("Brush size. Aminate assigns [ and ] only when those shortcuts are free.")

        self.opacity_spin = QtWidgets.QDoubleSpinBox()
        self.opacity_spin.setObjectName("animatorsPencilOpacityPercentSpin")
        self.opacity_spin.setAccessibleName("Pencil opacity percentage")
        self.opacity_spin.setRange(5.0, 100.0)
        self.opacity_spin.setSingleStep(5.0)
        self.opacity_spin.setDecimals(0)
        self.opacity_spin.setPrefix("Opacity ")
        self.opacity_spin.setSuffix("%")
        self.opacity_spin.setValue(100.0)

        self.eraser_mode_combo = QtWidgets.QComboBox()
        self.eraser_mode_combo.setObjectName("animatorsPencilEraserModeCombo")
        self.eraser_mode_combo.setAccessibleName("Animator Pencil eraser mode")
        self.eraser_mode_combo.addItem("Partial Stroke", "partial")
        self.eraser_mode_combo.addItem("Whole Stroke", "whole")
        self.eraser_mode_combo.setToolTip("Partial Stroke cuts touched sections. Whole Stroke removes every touched stroke.")
        self.eraser_mode_combo.setVisible(False)

        ignored_policy = _size_policy_value("Ignored")
        compact_widths = (
            (self.start_drawing_button, 78),
            (self.tool_combo, 58),
            (self.pick_color_button, 82),
            (self.quick_swatches_widget, 0),
            (self.size_spin, 58),
            (self.opacity_spin, 70),
            (self.eraser_mode_combo, 76),
        )
        for widget, minimum_width in compact_widths:
            widget.setMinimumWidth(minimum_width)
            if ignored_policy is not None:
                size_policy = widget.sizePolicy()
                size_policy.setHorizontalPolicy(ignored_policy)
                widget.setSizePolicy(size_policy)

        self.active_tool_layout.addWidget(self.start_drawing_button, 0, 0)
        self.active_tool_layout.addWidget(self.tool_combo, 0, 1, 1, 2)
        self.active_tool_layout.addWidget(self.pick_color_button, 0, 3)
        self.active_tool_layout.addWidget(self.quick_swatches_widget, 1, 0, 1, 2)
        self.active_tool_layout.addWidget(self.size_spin, 1, 2)
        self.active_tool_layout.addWidget(self.opacity_spin, 1, 3)
        self.active_tool_layout.addWidget(self.eraser_mode_combo, 2, 0)
        for column in range(4):
            self.active_tool_layout.setColumnStretch(column, 1)
        layout.addWidget(self.active_tool_strip)

        drawing_views = QtWidgets.QGroupBox("Saved Drawing Views")
        drawing_views.setObjectName("animatorsPencilDrawingViewsGroup")
        drawing_views.setToolTip("Fixed camera views used by Animator's Pencil. Each saved view has its own drawing layer.")
        drawing_views_layout = QtWidgets.QGridLayout(drawing_views)
        drawing_views_layout.setContentsMargins(6, 6, 6, 6)
        self.drawing_view_combo = QtWidgets.QComboBox()
        self.drawing_view_combo.setObjectName("animatorsPencilDrawingViewCombo")
        self.drawing_view_combo.setAccessibleName("Saved Animator Pencil drawing views")
        self.drawing_view_combo.setToolTip("Choose a fixed Pencil View. Marks and layers stay scoped to that camera.")
        self.drawing_view_combo.setEditable(True)
        no_insert_policy = _qt_flag("InsertPolicy", "NoInsert", None)
        if no_insert_policy is not None:
            self.drawing_view_combo.setInsertPolicy(no_insert_policy)
        self.drawing_view_name_edit = self.drawing_view_combo.lineEdit()
        self.drawing_view_name_edit.setReadOnly(True)
        self.drawing_view_name_edit.setAccessibleName("Saved Pencil View name")
        self.drawing_view_name_edit.setToolTip("Double-click the view name to rename it, or use Rename.")
        self.drawing_view_name_edit.installEventFilter(self)
        self.save_drawing_view_button = QtWidgets.QPushButton("Save Current View")
        self.save_drawing_view_button.setObjectName("animatorsPencilSaveDrawingViewButton")
        self.save_drawing_view_button.setToolTip("Copy the current viewport into a new fixed Pencil View.")
        self.switch_drawing_view_button = QtWidgets.QPushButton("Switch")
        self.switch_drawing_view_button.setObjectName("animatorsPencilSwitchDrawingViewButton")
        self.switch_drawing_view_button.setToolTip("Look through the selected Pencil View and use its drawing layer.")
        self.rename_drawing_view_button = QtWidgets.QPushButton("Rename")
        self.rename_drawing_view_button.setObjectName("animatorsPencilRenameDrawingViewButton")
        self.rename_drawing_view_button.setAccessibleName("Rename selected Pencil View")
        self.rename_drawing_view_button.setToolTip("Rename the selected Pencil View. You can also double-click its name.")
        drawing_views_layout.addWidget(self.drawing_view_combo, 0, 0, 1, 2)
        drawing_views_layout.addWidget(self.save_drawing_view_button, 1, 0)
        drawing_views_layout.addWidget(self.switch_drawing_view_button, 1, 1)
        drawing_views_layout.addWidget(self.rename_drawing_view_button, 2, 0, 1, 2)
        drawing_views_layout.setColumnStretch(0, 1)
        drawing_views_layout.setColumnStretch(1, 1)
        layout.addWidget(drawing_views)

        self.video_draw_over_group = QtWidgets.QGroupBox("Video Draw-Over")
        self.video_draw_over_group.setObjectName("animatorsPencilVideoDrawOverGroup")
        self.video_draw_over_group.setAccessibleName("Animator Pencil Video Draw-Over")
        self.video_draw_over_group.setToolTip("Attach a timeline-synced video to the fixed Pencil View and draw with every Pencil tool over it.")
        video_layout = QtWidgets.QGridLayout(self.video_draw_over_group)
        video_layout.setContentsMargins(6, 6, 6, 6)
        video_layout.setHorizontalSpacing(5)
        video_layout.setVerticalSpacing(5)
        self.attach_video_button = QtWidgets.QPushButton("Attach Video")
        self.attach_video_button.setObjectName("animatorsPencilAttachVideoButton")
        self.attach_video_button.setAccessibleName("Attach video for Animator Pencil draw-over")
        self.attach_video_button.setToolTip("Pick an MP4 or image sequence. Aminate proxies video through the shared Maya Video Reference controller.")
        self.video_display_combo = QtWidgets.QComboBox()
        self.video_display_combo.setObjectName("animatorsPencilVideoDisplayCombo")
        self.video_display_combo.setAccessibleName("Video reference display mode")
        self.video_display_combo.setToolTip("Choose a PIP over the main viewport, a freeform viewer, or the legacy main viewport. Drag a PIP viewer by its title bar to detach it into freeform mode.")
        self.video_display_combo.addItem("Over Main Viewport", "pinned")
        self.video_display_combo.addItem("Freeform Window", "floating")
        self.video_display_combo.addItem("Main Viewport (Legacy)", "main_view")
        self.video_placement_combo = QtWidgets.QComboBox()
        self.video_placement_combo.setObjectName("animatorsPencilVideoPlacementCombo")
        self.video_placement_combo.setAccessibleName("Video draw-over placement")
        self.video_placement_combo.setToolTip("Choose the starting PIP placement. Dragging its title bar switches the viewer to freeform mode.")
        for label, key in (
            ("Full View", "full_view"),
            ("Top Right", "top_right"),
            ("Top Left", "top_left"),
            ("Bottom Right", "bottom_right"),
            ("Bottom Left", "bottom_left"),
        ):
            self.video_placement_combo.addItem(label, key)
        self.video_placement_combo.setCurrentIndex(max(0, self.video_placement_combo.findData("top_right")))
        self.video_start_frame_spin = QtWidgets.QSpinBox()
        self.video_start_frame_spin.setObjectName("animatorsPencilVideoStartFrameSpin")
        self.video_start_frame_spin.setAccessibleName("Video draw-over start frame")
        self.video_start_frame_spin.setRange(-100000, 100000)
        self.video_start_frame_spin.setValue(int(round(float(cmds.currentTime(query=True)))) if MAYA_AVAILABLE else 1)
        self.video_start_frame_spin.setPrefix("Start frame ")
        self.video_start_frame_spin.setToolTip("Start frame: the Maya timeline frame where the first video frame appears. This is the numeric field that may show a value such as 5.")
        self.video_scale_spin = QtWidgets.QDoubleSpinBox()
        self.video_scale_spin.setObjectName("animatorsPencilVideoScalePercentSpin")
        self.video_scale_spin.setAccessibleName("Video draw-over size percentage")
        self.video_scale_spin.setRange(10.0, 200.0)
        self.video_scale_spin.setSingleStep(5.0)
        self.video_scale_spin.setDecimals(0)
        self.video_scale_spin.setPrefix("Viewer Size ")
        self.video_scale_spin.setSuffix("%")
        self.video_scale_spin.setValue(38.0)
        self.video_scale_spin.setToolTip("Viewer size as a percentage of the main viewport. 100% fills it; 38% is the compact PIP default. A freeform viewer keeps its manual size.")
        self.video_opacity_spin = QtWidgets.QDoubleSpinBox()
        self.video_opacity_spin.setObjectName("animatorsPencilVideoOpacityPercentSpin")
        self.video_opacity_spin.setAccessibleName("Video draw-over opacity percentage")
        self.video_opacity_spin.setRange(0.0, 100.0)
        self.video_opacity_spin.setSingleStep(5.0)
        self.video_opacity_spin.setDecimals(0)
        self.video_opacity_spin.setPrefix("Video Opacity ")
        self.video_opacity_spin.setSuffix("%")
        self.video_opacity_spin.setValue(80.0)
        self.video_opacity_spin.setToolTip("Opacity of the attached video image plane. Changes apply immediately and persist in the scene.")
        self.video_line_opacity_spin = QtWidgets.QDoubleSpinBox()
        self.video_line_opacity_spin.setObjectName("animatorsPencilVideoLineOpacityPercentSpin")
        self.video_line_opacity_spin.setAccessibleName("Pencil line opacity percentage")
        self.video_line_opacity_spin.setRange(0.0, 100.0)
        self.video_line_opacity_spin.setSingleStep(5.0)
        self.video_line_opacity_spin.setDecimals(0)
        self.video_line_opacity_spin.setPrefix("Lines Opacity ")
        self.video_line_opacity_spin.setSuffix("%")
        self.video_line_opacity_spin.setValue(100.0)
        self.video_line_opacity_spin.setToolTip("Opacity of marks on the active Pencil layer. Existing and future marks update immediately.")
        self.video_include_audio_box = QtWidgets.QCheckBox("Include Audio")
        self.video_include_audio_box.setObjectName("animatorsPencilVideoIncludeAudioCheckBox")
        self.video_include_audio_box.setAccessibleName("Include video audio")
        self.video_include_audio_box.setToolTip("Extract and attach the source video's audio when the format contains audio.")
        self.video_keep_strokes_on_top_box = QtWidgets.QCheckBox("Keep Strokes On Top")
        self.video_keep_strokes_on_top_box.setObjectName("animatorsPencilVideoKeepStrokesOnTopCheckBox")
        self.video_keep_strokes_on_top_box.setAccessibleName("Keep Pencil strokes above video")
        self.video_keep_strokes_on_top_box.setChecked(True)
        self.video_keep_strokes_on_top_box.setToolTip("Put the camera image plane behind Pencil layers without changing the overlay's apparent size.")
        self.show_pencil_view_button = QtWidgets.QPushButton("Show Reference Viewer")
        self.show_pencil_view_button.setObjectName("animatorsPencilShowPencilViewButton")
        self.show_pencil_view_button.setAccessibleName("Switch Video Draw-Over mode")
        self.show_pencil_view_button.setToolTip("Show or hide the complete video-and-annotations Reference Viewer without changing the perspective camera.")
        self.show_pencil_view_button.setEnabled(False)
        self.package_annotated_scene_button = QtWidgets.QPushButton("Package Scene")
        self.package_annotated_scene_button.setObjectName("animatorsPencilPackageAnnotatedSceneButton")
        self.package_annotated_scene_button.setAccessibleName("Package scene with references and draw-overs")
        self.package_annotated_scene_button.setToolTip("Save and package the Maya scene with references, the original/proxy video, audio, and all Pencil draw-overs. Extracted packages use portable paths and rediscover these items when opened.")
        self.clear_video_status_button = QtWidgets.QToolButton()
        self.clear_video_status_button.setText("Clear")
        self.clear_video_status_button.setObjectName("animatorsPencilClearVideoSourceStatusButton")
        self.clear_video_status_button.setAccessibleName("Clear video source status")
        self.clear_video_status_button.setToolTip("Clear this panel's source message. The attached scene nodes stay unchanged.")
        self.video_source_status = QtWidgets.QLabel("No video attached.")
        self.video_source_status.setObjectName("animatorsPencilVideoSourceStatusLabel")
        self.video_source_status.setAccessibleName("Video source status")
        self.video_source_status.setToolTip("Current Video Draw-Over source and proxy status.")
        self.video_source_status.setWordWrap(True)
        ignored_policy = _size_policy_value("Ignored")
        for widget, minimum_width in ((self.video_scale_spin, 76), (self.video_opacity_spin, 76), (self.video_line_opacity_spin, 76)):
            widget.setMinimumWidth(minimum_width)
            if ignored_policy is not None:
                size_policy = widget.sizePolicy()
                size_policy.setHorizontalPolicy(ignored_policy)
                widget.setSizePolicy(size_policy)
        # Two columns are enough for every control and avoid summing three
        # intrinsic widget widths into a hard minimum wider than a 360px dock.
        # The long package action and status keep a full row, so no text is
        # clipped when the panel is narrow.
        video_layout.addWidget(self.attach_video_button, 0, 0)
        video_layout.addWidget(self.video_display_combo, 0, 1)
        video_layout.addWidget(self.video_placement_combo, 1, 0)
        video_layout.addWidget(self.video_scale_spin, 1, 1)
        video_layout.addWidget(self.video_start_frame_spin, 2, 0)
        video_layout.addWidget(self.video_opacity_spin, 2, 1)
        video_layout.addWidget(self.video_line_opacity_spin, 3, 0)
        video_layout.addWidget(self.video_include_audio_box, 3, 1)
        video_layout.addWidget(self.video_keep_strokes_on_top_box, 4, 0)
        video_layout.addWidget(self.show_pencil_view_button, 4, 1)
        video_layout.addWidget(self.package_annotated_scene_button, 5, 0, 1, 2)
        video_layout.addWidget(self.video_source_status, 6, 0)
        video_layout.addWidget(self.clear_video_status_button, 6, 1)
        for column in range(2):
            video_layout.setColumnStretch(column, 1)
        layout.addWidget(self.video_draw_over_group)

        # Keep all layer-owned controls together.  The previous layout placed
        # the layer table, mark editing actions and history in one flat column,
        # which made it unclear whether a button changed a layer or a mark.
        layer_group = QtWidgets.QGroupBox("Layer Controls")
        layer_group.setObjectName("animatorsPencilLayerControlsGroup")
        layer_group.setAccessibleName("Animator Pencil layer controls")
        layer_group.setToolTip(
            "Controls in this section change the selected Pencil layer: its name, visibility, order, camera, state, and opacity."
        )
        layer_group_layout = QtWidgets.QVBoxLayout(layer_group)
        layer_group_layout.setContentsMargins(6, 8, 6, 6)
        layer_group_layout.setSpacing(5)

        layer_help = QtWidgets.QLabel(
            "Selected layer: rename, show or hide, change its state and opacity, or move it in the layer stack."
        )
        layer_help.setObjectName("animatorsPencilLayerControlsHelp")
        layer_help.setWordWrap(True)
        layer_help.setToolTip(layer_group.toolTip())
        layer_group_layout.addWidget(layer_help)

        top = QtWidgets.QGridLayout()
        self.layer_top_layout = top
        self.layer_name = QtWidgets.QLineEdit("Pencil Layer")
        self.layer_name.setAccessibleName("Selected Pencil layer name")
        self.layer_name.setToolTip("Name for the selected Pencil layer. Double-click a layer name in the table to rename it too.")
        self.layer_name_label = QtWidgets.QLabel("Layer")
        top.addWidget(self.layer_name_label, 0, 0)
        top.addWidget(self.layer_name, 0, 1, 1, 3)
        self.add_layer_button = QtWidgets.QPushButton("Add Layer")
        self.add_layer_button.setAccessibleName("Add a new Pencil layer")
        self.add_layer_button.setToolTip("Create a new Pencil layer using the name above.")
        self.rename_layer_button = QtWidgets.QPushButton("Rename Layer")
        self.rename_layer_button.setObjectName("animatorsPencilRenameLayerButton")
        self.rename_layer_button.setAccessibleName("Rename selected Pencil layer")
        self.rename_layer_button.setToolTip("Rename the selected Pencil layer using the name above. Double-clicking its table name works too.")
        self.delete_layer_button = QtWidgets.QPushButton("Delete Layer")
        self.delete_layer_button.setAccessibleName("Delete selected Pencil layer")
        self.delete_layer_button.setToolTip("Delete the selected Pencil layer and its marks.")
        top.addWidget(self.add_layer_button, 1, 1)
        top.addWidget(self.rename_layer_button, 1, 2)
        top.addWidget(self.delete_layer_button, 1, 3)
        self.hide_all_layers_button = QtWidgets.QPushButton("Hide All")
        self.hide_all_layers_button.setObjectName("animatorsPencilHideAllLayersButton")
        self.hide_all_layers_button.setToolTip("Hide every Animator's Pencil layer for a clean playblast.")
        self.show_all_layers_button = QtWidgets.QPushButton("Show All")
        self.show_all_layers_button.setObjectName("animatorsPencilShowAllLayersButton")
        self.show_all_layers_button.setToolTip("Show every Animator's Pencil layer again.")
        top.addWidget(self.hide_all_layers_button, 2, 1)
        top.addWidget(self.show_all_layers_button, 2, 2, 1, 2)
        layer_group_layout.addLayout(top)

        self.layer_table = QtWidgets.QTableWidget(0, 7)
        self.layer_table.setHorizontalHeaderLabels(["Layer", "Visible", "Effective", "Camera", "State", "Locked", "Marks"])
        header = self.layer_table.horizontalHeader()
        resize_modes = getattr(QtWidgets.QHeaderView, "ResizeMode", QtWidgets.QHeaderView)
        stretch_mode = getattr(QtWidgets.QHeaderView, "Stretch", getattr(resize_modes, "Stretch"))
        contents_mode = getattr(QtWidgets.QHeaderView, "ResizeToContents", getattr(resize_modes, "ResizeToContents"))
        header.setSectionResizeMode(0, stretch_mode)
        for section in range(1, 7):
            header.setSectionResizeMode(section, contents_mode)
        self.layer_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.layer_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        edit_triggers = getattr(QtWidgets.QAbstractItemView, "EditTrigger", QtWidgets.QAbstractItemView)
        self.layer_table.setEditTriggers(
            _qt_flag("EditTrigger", "DoubleClicked", getattr(edit_triggers, "DoubleClicked"))
            | _qt_flag("EditTrigger", "EditKeyPressed", getattr(edit_triggers, "EditKeyPressed"))
        )
        self.layer_table.setContextMenuPolicy(_qt_flag("ContextMenuPolicy", "CustomContextMenu", QtCore.Qt.CustomContextMenu))
        self.layer_table.setMinimumWidth(0)
        self.layer_table.setHorizontalScrollBarPolicy(
            _qt_flag("ScrollBarPolicy", "ScrollBarAsNeeded", QtCore.Qt.ScrollBarAsNeeded)
        )
        layer_buttons = QtWidgets.QGridLayout()
        layer_buttons.setHorizontalSpacing(5)
        layer_buttons.setVerticalSpacing(5)
        self.state_combo = QtWidgets.QComboBox()
        self.state_combo.setObjectName("animatorsPencilLayerStateCombo")
        self.state_combo.setAccessibleName("Selected Pencil layer state")
        self.state_combo.setToolTip("Choose whether the selected Pencil layer is animated, static, or locked.")
        self.state_combo.addItems(LAYER_STATES)
        self.layer_opacity_spin = QtWidgets.QDoubleSpinBox()
        self.layer_opacity_spin.setObjectName("animatorsPencilLayerOpacityPercentSpin")
        self.layer_opacity_spin.setAccessibleName("Selected Pencil layer opacity percentage")
        self.layer_opacity_spin.setRange(0.0, 100.0)
        self.layer_opacity_spin.setSingleStep(5.0)
        self.layer_opacity_spin.setDecimals(0)
        self.layer_opacity_spin.setPrefix("Layer ")
        self.layer_opacity_spin.setSuffix("%")
        self.layer_opacity_spin.setToolTip("Persistent opacity for every existing and future mark in the selected layer.")
        self.layer_up_button = QtWidgets.QPushButton("Layer Up")
        self.layer_up_button.setAccessibleName("Move selected Pencil layer up")
        self.layer_up_button.setToolTip("Move the selected Pencil layer one step higher in the layer stack.")
        self.layer_down_button = QtWidgets.QPushButton("Layer Down")
        self.layer_down_button.setAccessibleName("Move selected Pencil layer down")
        self.layer_down_button.setToolTip("Move the selected Pencil layer one step lower in the layer stack.")
        self.move_camera_button = QtWidgets.QPushButton("Move To Current Camera")
        self.move_camera_button.setAccessibleName("Move selected Pencil layer to current camera")
        self.move_camera_button.setToolTip("Attach the selected Pencil layer to the camera currently shown in the active viewport.")
        self.layer_state_label = QtWidgets.QLabel("State")
        self.layer_opacity_label = QtWidgets.QLabel("Opacity")
        layer_buttons.addWidget(self.layer_state_label, 0, 0)
        layer_buttons.addWidget(self.state_combo, 0, 1)
        layer_buttons.addWidget(self.layer_opacity_label, 0, 2)
        layer_buttons.addWidget(self.layer_opacity_spin, 0, 3)
        layer_buttons.addWidget(self.layer_up_button, 1, 0)
        layer_buttons.addWidget(self.layer_down_button, 1, 1)
        layer_buttons.addWidget(self.move_camera_button, 2, 0, 1, 4)
        layer_group_layout.addLayout(layer_buttons)
        layer_group.setMinimumSize(0, 0)
        layout.addWidget(layer_group)
        self.layer_controls_group = layer_group
        self.layer_buttons_layout = layer_buttons

        # Keep the live layer list as a first-class root item.  This preserves
        # the visual contract that the Active Drawing strip and Video
        # Draw-Over controls precede the actual Layers surface, while the
        # selected-layer setup controls remain grouped above it.
        layers_heading = QtWidgets.QLabel("Layers")
        layers_heading.setObjectName("animatorsPencilLayersHeading")
        layers_heading.setAccessibleName("Animator Pencil layers")
        layout.addWidget(layers_heading)
        layout.addWidget(self.layer_table, 1)

        self.drawing_settings = QtWidgets.QWidget(self.active_tool_strip)
        self.drawing_settings.setObjectName("animatorsPencilDrawingSettings")
        tool_layout = QtWidgets.QGridLayout(self.drawing_settings)
        tool_layout.setContentsMargins(0, 4, 0, 0)
        tool_layout.setHorizontalSpacing(5)
        tool_layout.setVerticalSpacing(5)
        self.shape_library_button = QtWidgets.QPushButton("Shape Library")
        self.shape_library_button.setObjectName("animatorsPencilShapeLibraryButton")
        self.shape_library_button.setToolTip("Open the floating preset shape library.")
        self.brush_shortcut_label = QtWidgets.QLabel("Size keys: checking")
        self.brush_shortcut_label.setObjectName("animatorsPencilBrushShortcutLabel")
        self.brush_shortcut_label.setToolTip("Aminate uses [ and ] when free, then tries modified pairs. Existing Maya or Qt shortcuts are never replaced.")
        self.text_field = QtWidgets.QLineEdit("Note")
        self.draw_button = QtWidgets.QPushButton("Stamp Current Tool", self.drawing_settings)
        self.draw_button.setObjectName("animatorsPencilCreateMarkButton")
        self.draw_button.setIcon(_make_tool_icon("Pencil"))
        self.draw_button.setToolTip("Create one default mark with the selected tool without dragging.")
        self.marquee_select_button = QtWidgets.QPushButton("Marquee & Transform")
        self.marquee_select_button.setObjectName("animatorsPencilMarqueeSelectButton")
        self.marquee_select_button.setAccessibleName("Marquee select and transform Animator Pencil line sections")
        self.marquee_select_button.setIcon(_make_tool_icon("Rectangle", QtGui.QColor("#72B7F2")))
        self.marquee_select_button.setToolTip("Drag a box over Pencil lines. Aminate keeps the enclosed sections, then shows a viewport move-and-scale box.")
        self.camera_notes_button = QtWidgets.QToolButton()
        self.camera_notes_button.setObjectName("animatorsPencilCameraNotesMenuButton")
        self.camera_notes_button.setText("Camera Notes")
        self.camera_notes_button.setIcon(_make_tool_icon("Camera", QtGui.QColor("#F6C85F")))
        self.camera_notes_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.camera_notes_button.setPopupMode(_tool_button_popup_mode("InstantPopup"))
        self.camera_notes_button.setToolTip("Create or use a Camera Notes camera. Each pencil mark can key this camera to the exact current view.")
        self.camera_notes_menu = QtWidgets.QMenu(self.camera_notes_button)
        self.camera_notes_menu.setObjectName("animatorsPencilCameraNotesMenu")
        self.camera_notes_menu.addAction(_make_tool_icon("Camera", QtGui.QColor("#F6C85F")), "Create / Use Camera Notes Camera", self._create_camera_notes_camera)
        self.camera_notes_menu.addAction(_make_tool_icon("Camera", QtGui.QColor("#72B7F2")), "Key Camera To Current View", self._key_camera_notes_camera)
        self.camera_notes_menu.addAction(_make_tool_icon("Camera", QtGui.QColor("#7BD88F")), "Look Through Camera Notes", self._switch_to_camera_notes)
        self.camera_notes_button.setMenu(self.camera_notes_menu)
        self.camera_note_box = QtWidgets.QCheckBox("Key camera when drawing")
        self.camera_note_box.setObjectName("animatorsPencilCameraNoteCheckBox")
        self.camera_note_box.setChecked(True)
        self.camera_note_box.setToolTip("When on, every new pencil mark keys the Camera Notes camera to the current viewport camera on this frame.")
        self.camera_snap_box = QtWidgets.QCheckBox("Snap camera cuts")
        self.camera_snap_box.setObjectName("animatorsPencilCameraSnapCheckBox")
        self.camera_snap_box.setChecked(True)
        self.camera_snap_box.setToolTip("When on, Camera Notes keys use stepped tangents so the camera snaps to each keyed note view.")
        self.single_frame_box = QtWidgets.QCheckBox("Current frame only")
        self.single_frame_box.setObjectName("animatorsPencilCurrentFrameOnlyCheckBox")
        self.single_frame_box.setChecked(DEFAULT_ONE_FRAME_ONLY)
        self.single_frame_box.setToolTip("On by default: the mark hides on the next frame. Turn this off when a drawing should hold.")
        tool_layout.addWidget(self.draw_button, 0, 0)
        tool_layout.addWidget(self.shape_library_button, 0, 1)
        tool_layout.addWidget(self.marquee_select_button, 1, 0, 1, 2)
        tool_layout.addWidget(QtWidgets.QLabel("Text"), 2, 0)
        tool_layout.addWidget(self.text_field, 2, 1)
        tool_layout.addWidget(self.camera_notes_button, 3, 0, 1, 2)
        tool_layout.addWidget(self.camera_note_box, 4, 0)
        tool_layout.addWidget(self.camera_snap_box, 4, 1)
        tool_layout.addWidget(self.single_frame_box, 5, 0)
        tool_layout.addWidget(self.brush_shortcut_label, 5, 1)
        self.active_tool_layout.addWidget(self.drawing_settings, 2, 0, 1, 4)

        # Mark editing and history are deliberately separate from Layer
        # Controls.  These actions operate on selected scene-native marks or
        # the edit history, not on the selected layer itself.
        mark_group = QtWidgets.QGroupBox("Selected Mark Editing")
        mark_group.setObjectName("animatorsPencilSelectedMarkEditingGroup")
        mark_group.setAccessibleName("Animator Pencil selected mark editing")
        mark_group.setToolTip(
            "These actions affect the selected Pencil marks. They do not move, rename, or change the active layer."
        )
        mark_group_layout = QtWidgets.QVBoxLayout(mark_group)
        mark_group_layout.setContentsMargins(6, 8, 6, 6)
        mark_group_layout.setSpacing(5)
        mark_help = QtWidgets.QLabel(
            "Select marks in the viewport, then copy, cut, paste, erase, or change their display state."
        )
        mark_help.setObjectName("animatorsPencilSelectedMarkEditingHelp")
        mark_help.setWordWrap(True)
        mark_help.setToolTip(mark_group.toolTip())
        mark_group_layout.addWidget(mark_help)

        edit_buttons = QtWidgets.QGridLayout()
        edit_buttons.setHorizontalSpacing(5)
        edit_buttons.setVerticalSpacing(5)
        self.copy_button = QtWidgets.QPushButton("Copy Selected Marks")
        self.copy_button.setAccessibleName("Copy selected Pencil marks")
        self.copy_button.setToolTip("Copy the selected Pencil marks to the clipboard without changing the current layer.")
        self.cut_button = QtWidgets.QPushButton("Cut Selected Marks")
        self.cut_button.setAccessibleName("Cut selected Pencil marks")
        self.cut_button.setToolTip("Copy and remove the selected Pencil marks from their current layer.")
        self.paste_button = QtWidgets.QPushButton("Paste Marks")
        self.paste_button.setAccessibleName("Paste Pencil marks")
        self.paste_button.setToolTip("Paste copied Pencil marks into the active layer at the current frame.")
        self.delete_marks_button = QtWidgets.QPushButton("Erase Selected Marks")
        self.delete_marks_button.setAccessibleName("Erase selected Pencil marks")
        self.delete_marks_button.setToolTip("Erase the selected Pencil marks. The layer itself is left unchanged.")
        self.translucent_button = QtWidgets.QPushButton("Toggle Mark Translucency")
        self.translucent_button.setObjectName("animatorsPencilTranslucentToggleButton")
        self.translucent_button.setAccessibleName("Toggle selected Pencil mark translucency")
        self.translucent_button.setToolTip("Toggle Maya's translucent/template display for the selected Pencil marks.")
        for index, button in enumerate((self.copy_button, self.cut_button, self.paste_button, self.delete_marks_button, self.translucent_button)):
            edit_buttons.addWidget(button, index // 2, index % 2)
        mark_group_layout.addLayout(edit_buttons)
        mark_group.setMinimumSize(0, 0)
        layout.addWidget(mark_group)
        self.selected_mark_editing_group = mark_group
        self.mark_edit_buttons_layout = edit_buttons

        history_group = QtWidgets.QGroupBox("Pencil History")
        history_group.setObjectName("animatorsPencilHistoryGroup")
        history_group.setAccessibleName("Animator Pencil edit history")
        history_group.setToolTip("Undo or redo recent Animator's Pencil edits.")
        history_layout = QtWidgets.QVBoxLayout(history_group)
        history_layout.setContentsMargins(6, 8, 6, 6)
        history_layout.setSpacing(5)
        history_help = QtWidgets.QLabel("Step backward or forward through recent Pencil edits.")
        history_help.setObjectName("animatorsPencilHistoryHelp")
        history_help.setWordWrap(True)
        history_help.setToolTip(history_group.toolTip())
        history_layout.addWidget(history_help)
        history_buttons = QtWidgets.QGridLayout()
        history_buttons.setHorizontalSpacing(5)
        history_buttons.setVerticalSpacing(5)
        self.undo_button = QtWidgets.QPushButton("Undo Pencil Edit")
        self.undo_button.setAccessibleName("Undo last Animator Pencil edit")
        self.undo_button.setToolTip("Undo the most recent Animator's Pencil edit.")
        self.redo_button = QtWidgets.QPushButton("Redo Pencil Edit")
        self.redo_button.setAccessibleName("Redo last Animator Pencil edit")
        self.redo_button.setToolTip("Redo the most recently undone Animator's Pencil edit.")
        history_buttons.addWidget(self.undo_button, 0, 0)
        history_buttons.addWidget(self.redo_button, 0, 1)
        history_layout.addLayout(history_buttons)
        history_group.setMinimumSize(0, 0)
        layout.addWidget(history_group)
        self.history_group = history_group
        self.history_buttons_layout = history_buttons

        onion = QtWidgets.QGroupBox("Onion Skin")
        onion_layout = QtWidgets.QGridLayout(onion)
        self.onion_toggle = QtWidgets.QCheckBox("Live Onion Skin")
        self.onion_toggle.setToolTip("Refresh ghosts automatically as the Maya timeline changes.")
        self.onion_before_spin = QtWidgets.QSpinBox()
        self.onion_before_spin.setRange(0, 12)
        self.onion_before_spin.setValue(1)
        self.onion_before_spin.setPrefix("Before ")
        self.onion_after_spin = QtWidgets.QSpinBox()
        self.onion_after_spin.setRange(0, 12)
        self.onion_after_spin.setValue(1)
        self.onion_after_spin.setPrefix("After ")
        self.onion_opacity_spin = QtWidgets.QDoubleSpinBox()
        self.onion_opacity_spin.setRange(0.05, 1.0)
        self.onion_opacity_spin.setSingleStep(0.05)
        self.onion_opacity_spin.setValue(0.35)
        self.onion_opacity_spin.setPrefix("Opacity ")
        self.onion_before_color_button = QtWidgets.QPushButton("Previous Color")
        self.onion_after_color_button = QtWidgets.QPushButton("Next Color")
        self.camera_scope_box = QtWidgets.QCheckBox("Current camera layer only")
        self.camera_scope_box.setChecked(True)
        self.camera_scope_box.setToolTip("Show annotations assigned to the active viewport camera.")
        onion_layout.addWidget(self.onion_toggle, 0, 0)
        onion_layout.addWidget(self.onion_opacity_spin, 0, 1)
        onion_layout.addWidget(self.onion_before_spin, 1, 0)
        onion_layout.addWidget(self.onion_after_spin, 1, 1)
        onion_layout.addWidget(self.onion_before_color_button, 2, 0)
        onion_layout.addWidget(self.onion_after_color_button, 2, 1)
        onion_layout.addWidget(self.camera_scope_box, 3, 0, 1, 2)
        layout.addWidget(onion)

        transform = QtWidgets.QGroupBox("Transform")
        transform_layout = QtWidgets.QGridLayout(transform)
        self.move_left_button = QtWidgets.QPushButton("Left")
        self.move_right_button = QtWidgets.QPushButton("Right")
        self.move_up_button = QtWidgets.QPushButton("Up")
        self.move_down_button = QtWidgets.QPushButton("Down")
        self.rotate_left_button = QtWidgets.QPushButton("Rotate -5")
        self.rotate_right_button = QtWidgets.QPushButton("Rotate +5")
        self.scale_down_button = QtWidgets.QPushButton("Scale 90%")
        self.scale_up_button = QtWidgets.QPushButton("Scale 110%")
        self.viewport_move_button = QtWidgets.QPushButton("Move Gizmo")
        self.viewport_move_button.setObjectName("animatorsPencilViewportMoveButton")
        self.viewport_move_button.setToolTip("Select pencil marks and switch Maya to the viewport move manipulator.")
        self.viewport_rotate_button = QtWidgets.QPushButton("Rotate Gizmo")
        self.viewport_rotate_button.setObjectName("animatorsPencilViewportRotateButton")
        self.viewport_rotate_button.setToolTip("Select pencil marks and switch Maya to the viewport rotate manipulator.")
        self.viewport_scale_button = QtWidgets.QPushButton("Scale Gizmo")
        self.viewport_scale_button.setObjectName("animatorsPencilViewportScaleButton")
        self.viewport_scale_button.setToolTip("Select pencil marks and switch Maya to the viewport scale manipulator.")
        self.transform_layer_button = QtWidgets.QPushButton("Apply To Full Layer")
        for i, button in enumerate((self.move_left_button, self.move_right_button, self.move_up_button, self.move_down_button, self.rotate_left_button, self.rotate_right_button, self.scale_down_button, self.scale_up_button)):
            transform_layout.addWidget(button, i // 2, i % 2)
        transform_layout.addWidget(self.viewport_move_button, 4, 0)
        transform_layout.addWidget(self.viewport_rotate_button, 4, 1)
        transform_layout.addWidget(self.viewport_scale_button, 5, 0)
        transform_layout.addWidget(self.transform_layer_button, 5, 1)
        layout.addWidget(transform)

        anim = QtWidgets.QGroupBox("Animation")
        anim_layout = QtWidgets.QGridLayout(anim)
        self.add_key_button = QtWidgets.QPushButton("Add Key")
        self.remove_key_button = QtWidgets.QPushButton("Remove Key")
        self.duplicate_key_button = QtWidgets.QPushButton("Duplicate Previous Key")
        self.marker_button = QtWidgets.QPushButton("Add Frame Marker")
        self.retime_back_button = QtWidgets.QPushButton("Retime -1")
        self.retime_forward_button = QtWidgets.QPushButton("Retime +1")
        self.ghost_button = QtWidgets.QPushButton("Build Ghosts")
        self.clear_ghosts_button = QtWidgets.QPushButton("Clear Ghosts")
        for i, button in enumerate((self.add_key_button, self.remove_key_button, self.duplicate_key_button, self.marker_button, self.retime_back_button, self.retime_forward_button, self.ghost_button, self.clear_ghosts_button)):
            anim_layout.addWidget(button, i // 2, i % 2)
        layout.addWidget(anim)

        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._camera_scope_timer = QtCore.QTimer(self)
        self._camera_scope_timer.setInterval(500)
        self._camera_scope_timer.timeout.connect(self._refresh_camera_scope_and_drawing_layer)
        self._camera_scope_timer.start()
        self._drawing_state_timer = QtCore.QTimer(self)
        self._drawing_state_timer.setInterval(250)
        self._drawing_state_timer.timeout.connect(self._refresh_drawing_state)
        self._drawing_state_timer.start()

        self.add_layer_button.clicked.connect(self._add_layer)
        self.rename_layer_button.clicked.connect(self._edit_selected_layer_name)
        self.delete_layer_button.clicked.connect(self._delete_layer)
        self.hide_all_layers_button.clicked.connect(lambda: self._set_all_layers_visibility(False))
        self.show_all_layers_button.clicked.connect(lambda: self._set_all_layers_visibility(True))
        self.layer_table.itemSelectionChanged.connect(self._layer_selection_changed)
        self.layer_table.itemChanged.connect(self._layer_item_changed)
        self.layer_table.customContextMenuRequested.connect(self._show_layer_menu)
        self.state_combo.currentTextChanged.connect(self._set_layer_state)
        self.layer_up_button.clicked.connect(lambda: self._move_layer(-1))
        self.layer_down_button.clicked.connect(lambda: self._move_layer(1))
        self.move_camera_button.clicked.connect(self._move_layer_to_camera)
        self.save_drawing_view_button.clicked.connect(self._save_current_drawing_view)
        self.switch_drawing_view_button.clicked.connect(self._switch_saved_drawing_view)
        self.rename_drawing_view_button.clicked.connect(self._begin_rename_drawing_view)
        self.drawing_view_name_edit.editingFinished.connect(self._finish_rename_drawing_view)
        self.drawing_view_combo.activated.connect(lambda _index: self._switch_saved_drawing_view())
        self.attach_video_button.clicked.connect(self._attach_video_draw_over)
        self.video_display_combo.currentIndexChanged.connect(self._video_display_changed)
        self.video_placement_combo.currentIndexChanged.connect(self._video_placement_changed)
        self.video_scale_spin.valueChanged.connect(self._video_scale_changed)
        self.video_start_frame_spin.valueChanged.connect(self._video_start_frame_changed)
        self.video_opacity_spin.valueChanged.connect(self._video_opacity_changed)
        self.video_line_opacity_spin.valueChanged.connect(self._video_line_opacity_changed)
        self.video_include_audio_box.toggled.connect(self._video_include_audio_changed)
        self.video_keep_strokes_on_top_box.toggled.connect(self._video_overlay_options_changed)
        self.show_pencil_view_button.clicked.connect(self._show_video_pencil_view)
        self.package_annotated_scene_button.clicked.connect(self._package_annotated_scene)
        self.clear_video_status_button.clicked.connect(lambda: self.video_source_status.setText("No video attached."))
        self.shape_library_button.clicked.connect(self._open_shape_library)
        self.pick_color_button.clicked.connect(self._open_color_swatch_window)
        self.size_spin.valueChanged.connect(self._drawing_options_changed)
        self.opacity_spin.valueChanged.connect(self._drawing_options_changed)
        self.text_field.textChanged.connect(self._drawing_options_changed)
        self.eraser_mode_combo.currentTextChanged.connect(self._drawing_options_changed)
        self.onion_toggle.toggled.connect(self._toggle_onion_skin)
        self.onion_before_spin.valueChanged.connect(self._refresh_onion_skin)
        self.onion_after_spin.valueChanged.connect(self._refresh_onion_skin)
        self.onion_opacity_spin.valueChanged.connect(self._refresh_onion_skin)
        self.onion_before_color_button.clicked.connect(lambda: self._pick_onion_color(True))
        self.onion_after_color_button.clicked.connect(lambda: self._pick_onion_color(False))
        self.camera_scope_box.toggled.connect(self._set_camera_scope)
        self.layer_opacity_spin.valueChanged.connect(self._layer_opacity_changed)
        self.camera_note_box.toggled.connect(self._drawing_options_changed)
        self.camera_snap_box.toggled.connect(self._drawing_options_changed)
        self.single_frame_box.toggled.connect(self._drawing_options_changed)
        self.draw_button.clicked.connect(self._create_mark)
        self.start_drawing_button.clicked.connect(self._toggle_drawing)
        self.marquee_select_button.clicked.connect(self._activate_marquee_select)
        self.tool_combo.currentTextChanged.connect(self._tool_changed)
        self.undo_button.clicked.connect(self.controller.undo)
        self.redo_button.clicked.connect(self.controller.redo)
        self.copy_button.clicked.connect(lambda: self.controller.copy_selected_marks(False))
        self.cut_button.clicked.connect(lambda: self.controller.copy_selected_marks(True))
        self.paste_button.clicked.connect(lambda: self._after_action(self.controller.paste_marks(self.current_layer)))
        self.delete_marks_button.clicked.connect(lambda: self._after_action(self.controller.delete_selected_marks()))
        self.translucent_button.clicked.connect(lambda: self._after_action(self.controller.toggle_marks_translucent(self.current_layer)))
        self.move_left_button.clicked.connect(lambda: self.controller.transform_selected(tx=-0.1))
        self.move_right_button.clicked.connect(lambda: self.controller.transform_selected(tx=0.1))
        self.move_up_button.clicked.connect(lambda: self.controller.transform_selected(ty=0.1))
        self.move_down_button.clicked.connect(lambda: self.controller.transform_selected(ty=-0.1))
        self.rotate_left_button.clicked.connect(lambda: self.controller.transform_selected(rotate=-5.0))
        self.rotate_right_button.clicked.connect(lambda: self.controller.transform_selected(rotate=5.0))
        self.scale_down_button.clicked.connect(lambda: self.controller.transform_selected(scale=0.9))
        self.scale_up_button.clicked.connect(lambda: self.controller.transform_selected(scale=1.1))
        self.viewport_move_button.clicked.connect(lambda: self.controller.activate_viewport_transform("move"))
        self.viewport_rotate_button.clicked.connect(lambda: self.controller.activate_viewport_transform("rotate"))
        self.viewport_scale_button.clicked.connect(lambda: self.controller.activate_viewport_transform("scale"))
        self.transform_layer_button.clicked.connect(lambda: self.controller.transform_layer(self.current_layer, scale=1.05))
        self.add_key_button.clicked.connect(self.controller.add_key)
        self.remove_key_button.clicked.connect(self.controller.remove_key)
        self.duplicate_key_button.clicked.connect(lambda: self._after_action(self.controller.duplicate_previous_key(self.current_layer)))
        self.marker_button.clicked.connect(lambda: self._after_action(self.controller.create_frame_marker(self._current_color())))
        self.retime_back_button.clicked.connect(lambda: self.controller.retime_selected(-1))
        self.retime_forward_button.clicked.connect(lambda: self.controller.retime_selected(1))
        self.ghost_button.clicked.connect(lambda: self.controller.make_ghosts(self.current_layer))
        self.clear_ghosts_button.clicked.connect(self.controller.clear_ghosts)

    def resizeEvent(self, event):
        try:
            super(AnimatorsPencilPanel, self).resizeEvent(event)
        except Exception:
            pass
        self._reflow_active_tool_strip()
        self._reflow_action_groups()

    @staticmethod
    def _clear_grid_layout(grid_layout):
        """Remove grid items without deleting their widgets."""
        while grid_layout.count():
            grid_layout.takeAt(0)

    def _reflow_action_groups(self, width=None):
        """Keep the action groups readable in narrow and wide Pencil docks."""
        layer_buttons = getattr(self, "layer_buttons_layout", None)
        mark_buttons = getattr(self, "mark_edit_buttons_layout", None)
        history_buttons = getattr(self, "history_buttons_layout", None)
        if not layer_buttons or not mark_buttons or not history_buttons:
            return
        compact = (self.width() if width is None else int(width)) <= 520
        if getattr(self, "_action_groups_compact", None) == compact:
            return
        self._action_groups_compact = compact

        self._clear_grid_layout(layer_buttons)
        top = getattr(self, "layer_top_layout", None)
        if top is not None:
            self._clear_grid_layout(top)
            if compact:
                top.addWidget(self.layer_name_label, 0, 0)
                top.addWidget(self.layer_name, 0, 1)
                top.addWidget(self.add_layer_button, 1, 0)
                top.addWidget(self.rename_layer_button, 1, 1)
                top.addWidget(self.delete_layer_button, 2, 0)
                top.addWidget(self.hide_all_layers_button, 2, 1)
                top.addWidget(self.show_all_layers_button, 3, 0, 1, 2)
            else:
                top.addWidget(self.layer_name_label, 0, 0)
                top.addWidget(self.layer_name, 0, 1, 1, 3)
                top.addWidget(self.add_layer_button, 1, 1)
                top.addWidget(self.rename_layer_button, 1, 2)
                top.addWidget(self.delete_layer_button, 1, 3)
                top.addWidget(self.hide_all_layers_button, 2, 1)
                top.addWidget(self.show_all_layers_button, 2, 2, 1, 2)
        if compact:
            layer_buttons.addWidget(self.layer_state_label, 0, 0)
            layer_buttons.addWidget(self.state_combo, 0, 1)
            self.layer_opacity_label.setText("Layer opacity")
            layer_buttons.addWidget(self.layer_opacity_label, 1, 0)
            layer_buttons.addWidget(self.layer_opacity_spin, 1, 1)
            layer_buttons.addWidget(self.layer_up_button, 2, 0)
            layer_buttons.addWidget(self.layer_down_button, 2, 1)
            layer_buttons.addWidget(self.move_camera_button, 3, 0, 1, 2)
        else:
            self.layer_opacity_label.setText("Opacity")
            layer_buttons.addWidget(self.layer_state_label, 0, 0)
            layer_buttons.addWidget(self.state_combo, 0, 1)
            layer_buttons.addWidget(self.layer_opacity_spin, 0, 3)
            layer_buttons.addWidget(self.layer_opacity_label, 0, 2)
            layer_buttons.addWidget(self.layer_up_button, 1, 0)
            layer_buttons.addWidget(self.layer_down_button, 1, 1)
            layer_buttons.addWidget(self.move_camera_button, 2, 0, 1, 4)

        self._clear_grid_layout(mark_buttons)
        mark_widgets = (self.copy_button, self.cut_button, self.paste_button, self.delete_marks_button, self.translucent_button)
        if compact:
            for row, button in enumerate(mark_widgets):
                mark_buttons.addWidget(button, row, 0)
        else:
            for index, button in enumerate(mark_widgets):
                mark_buttons.addWidget(button, index // 2, index % 2)

        self._clear_grid_layout(history_buttons)
        if compact:
            history_buttons.addWidget(self.undo_button, 0, 0)
            history_buttons.addWidget(self.redo_button, 1, 0)
        else:
            history_buttons.addWidget(self.undo_button, 0, 0)
            history_buttons.addWidget(self.redo_button, 0, 1)
        # Nested layouts can recompute a QGroupBox minimum from long button
        # labels.  The surrounding Pencil scroll area owns the width, so keep
        # these sections shrinkable and let the compact branch stack actions.
        for group in (self.layer_controls_group, self.selected_mark_editing_group, self.history_group):
            group.setMinimumSize(0, 0)
            policy = group.sizePolicy()
            policy.setHorizontalPolicy(_size_policy_value("Ignored") or policy.horizontalPolicy())
            group.setSizePolicy(policy)

    def _reflow_active_tool_strip(self):
        if not getattr(self, "active_tool_layout", None):
            return
        compact = self.width() < 520
        if getattr(self, "_active_tool_compact", None) == compact:
            return
        self._active_tool_compact = compact
        widgets = (
            self.start_drawing_button,
            self.tool_combo,
            self.pick_color_button,
            self.quick_swatches_widget,
            self.size_spin,
            self.opacity_spin,
            self.eraser_mode_combo,
            self.drawing_settings,
        )
        for widget in widgets:
            self.active_tool_layout.removeWidget(widget)
        if compact:
            placements = (
                (self.start_drawing_button, 0, 0, 1, 2),
                (self.tool_combo, 1, 0, 1, 2),
                (self.pick_color_button, 2, 0, 1, 2),
                (self.quick_swatches_widget, 3, 0, 1, 2),
                (self.size_spin, 4, 0, 1, 2),
                (self.opacity_spin, 5, 0, 1, 2),
                (self.eraser_mode_combo, 6, 0, 1, 2),
                (self.drawing_settings, 7, 0, 1, 2),
            )
        else:
            placements = (
                (self.start_drawing_button, 0, 0, 1, 1),
                (self.tool_combo, 0, 1, 1, 2),
                (self.pick_color_button, 0, 3, 1, 1),
                (self.quick_swatches_widget, 1, 0, 1, 2),
                (self.size_spin, 1, 2, 1, 1),
                (self.opacity_spin, 1, 3, 1, 1),
                (self.eraser_mode_combo, 2, 0, 1, 1),
                (self.drawing_settings, 2, 1, 1, 3),
            )
        # A narrow dock gives the active strip eight stacked rows. Explicit
        # row minimums stop Qt from compressing the swatch row into the Size
        # field when the surrounding Pencil panel is shorter than its content.
        for row in range(8):
            self.active_tool_layout.setRowMinimumHeight(row, 30 if compact else 0)
        # Keep the stacked compact rows in the scrollable Pencil surface. A
        # fixed-height host must not squeeze them into overlapping one-pixel
        # cells before the outer tab scroll area can take over.
        self.active_tool_strip.setMinimumHeight(320 if compact else 150)
        for widget, row, column, row_span, column_span in placements:
            self.active_tool_layout.addWidget(widget, row, column, row_span, column_span)

    def _open_shape_library(self):
        if self._shape_library_window is None:
            self._shape_library_window = AnimatorsPencilShapeLibraryWindow(self.controller, self._create_shape_preset, self)
        self._shape_library_window.show()
        self._shape_library_window.raise_()
        self._shape_library_window.activateWindow()

    def _create_shape_preset(self, name):
        self._ensure_drawing_view_for_current_action()
        mark = self.controller.create_shape_preset(
            name,
            layer_node=self.current_layer,
            color=self._current_color(),
            size=self.size_spin.value(),
            opacity=self._current_opacity(),
            camera_note=self.camera_note_box.isChecked(),
            camera_snap=self.camera_snap_box.isChecked(),
            one_frame=self.single_frame_box.isChecked(),
        )
        self._after_action(mark)
        self._set_status("Created {0} preset.".format(name))

    def _set_color_button(self, button, color, active=False):
        red, green, blue = [max(0, min(255, int(float(value) * 255))) for value in color]
        luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
        text_color = "#111827" if luminance >= 145 else "#F8FAFC"
        border_color = "#FFFFFF" if active else "#708090"
        border_width = 2 if active else 1
        compact = bool(button.property("aminateCompactSwatch"))
        compact_rules = " padding: 0px; min-height: 0px; max-height: 22px;" if compact else ""
        button.setStyleSheet(
            "QPushButton {{ background-color: rgb({0}, {1}, {2}); color: {3}; border: {4}px solid {5};{6} }}".format(
                red, green, blue, text_color, border_width, border_color, compact_rules
            )
        )
        if compact:
            # Maya's global QPushButton style can inflate fixed-size colour
            # chips to 40px+ despite setFixedSize(24, 22). Keep this rule
            # scoped to quick swatches; picker and onion colour buttons retain
            # their normal, readable action-button sizing.
            button.setMinimumHeight(0)
            button.setMaximumHeight(22)
            button.setFixedSize(24, 22)

    def _apply_selected_color(self, color, update_window=True):
        normalized = tuple(max(0.0, min(1.0, float(value))) for value in tuple(color)[:3])
        if len(normalized) != 3:
            return
        self._selected_color = normalized
        self._set_color_button(self.pick_color_button, normalized, active=True)
        self._update_quick_swatch_selection()
        if update_window and _qt_object_valid(self._color_swatch_window):
            self._color_swatch_window.set_current_color(normalized)
        self._drawing_options_changed()

    def _pick_color(self):
        self._open_color_swatch_window()

    def _open_color_swatch_window(self):
        if not _qt_object_valid(self._color_swatch_window):
            self._color_swatch_window = AnimatorsPencilColorSwatchWindow(
                self,
                parent=_maya_main_qt_window() or self,
            )
        self._color_swatch_window.show_for_color(self._selected_color)
        self._set_status("RGB colour and saved swatches opened.")
        return self._color_swatch_window

    def _refresh_swatches(self):
        values = [tuple(value) for value in self.controller.swatches()]
        while len(self.swatch_buttons) < len(values):
            button = QtWidgets.QPushButton()
            button.setObjectName("animatorsPencilQuickSwatchButton{0}".format(len(self.swatch_buttons) + 1))
            button.setProperty("aminateCompactSwatch", True)
            button.setFixedSize(24, 22)
            button.setProperty("aminateSwatchIndex", len(self.swatch_buttons))
            button.clicked.connect(lambda _checked=False, widget=button: self._quick_swatch_clicked(widget))
            index = len(self.swatch_buttons)
            self.quick_swatches_layout.addWidget(button, index // 6, index % 6)
            self.swatch_buttons.append(button)
        self._quick_swatch_values = values
        for index, button in enumerate(self.swatch_buttons):
            if index >= len(values):
                button.hide()
                continue
            color = values[index]
            button.setProperty("aminateSwatchIndex", index)
            button.setAccessibleName("Use quick pencil colour swatch {0}".format(index + 1))
            button.setToolTip("Use quick pencil colour swatch {0}".format(index + 1))
            self._set_color_button(button, color, active=self._colors_match(color, self._selected_color))
            button.show()
        if _qt_object_valid(self._color_swatch_window):
            self._color_swatch_window.refresh_swatches()

    @staticmethod
    def _colors_match(first, second):
        return len(tuple(first or ())) >= 3 and len(tuple(second or ())) >= 3 and all(
            abs(float(first[index]) - float(second[index])) < 1.0e-5 for index in range(3)
        )

    def _update_quick_swatch_selection(self):
        values = getattr(self, "_quick_swatch_values", [])
        for index, button in enumerate(getattr(self, "swatch_buttons", [])):
            if index < len(values):
                self._set_color_button(button, values[index], active=self._colors_match(values[index], self._selected_color))

    def _quick_swatch_clicked(self, button):
        raw_index = button.property("aminateSwatchIndex")
        index = int(raw_index) if raw_index is not None else -1
        values = getattr(self, "_quick_swatch_values", [])
        if 0 <= index < len(values):
            self._use_swatch(values[index])

    def _use_swatch(self, color):
        self._apply_selected_color(color)

    def _save_swatch(self):
        self.controller.save_swatch(self._selected_color)
        self._refresh_swatches()

    def _pick_onion_color(self, previous):
        current_value = self._onion_before_color if previous else self._onion_after_color
        chosen = QtWidgets.QColorDialog.getColor(QtGui.QColor.fromRgbF(*current_value), self, "Pick Onion Skin Color")
        if chosen.isValid():
            value = (chosen.redF(), chosen.greenF(), chosen.blueF())
            if previous:
                self._onion_before_color = value
                self._set_color_button(self.onion_before_color_button, value)
            else:
                self._onion_after_color = value
                self._set_color_button(self.onion_after_color_button, value)
            self._refresh_onion_skin()

    def _toggle_onion_skin(self, enabled):
        if enabled:
            self.controller.enable_onion_skin(
                self.current_layer,
                self.onion_before_spin.value(),
                self.onion_after_spin.value(),
                self.onion_opacity_spin.value(),
                self._onion_before_color,
                self._onion_after_color,
            )
        else:
            self.controller.disable_onion_skin()

    def _refresh_onion_skin(self):
        if self.onion_toggle.isChecked():
            self._toggle_onion_skin(True)

    def _is_text_input_focused(self):
        widget = QtWidgets.QApplication.focusWidget()
        while widget is not None:
            if isinstance(
                widget,
                (
                    QtWidgets.QLineEdit,
                    QtWidgets.QPlainTextEdit,
                    QtWidgets.QTextEdit,
                    QtWidgets.QAbstractSpinBox,
                    QtWidgets.QComboBox,
                ),
            ):
                return True
            widget = widget.parentWidget()
        return False

    def _run_panel_shortcut(self, callback):
        if self._is_text_input_focused():
            return
        callback()

    def _install_shortcuts(self):
        shortcut_type = _shortcut_class()
        if shortcut_type is None:
            return
        bindings = self.controller.default_shortcut_bindings()
        shortcut_specs = (
            ("drag_draw", self._activate_drag_draw, "animatorsPencilShortcutDragDraw"),
            ("marquee_select", self._activate_marquee_select, "animatorsPencilShortcutMarquee"),
            ("eraser_tool", self._activate_eraser, "animatorsPencilShortcutEraser"),
            ("erase_selected", lambda: self._after_action(self.controller.delete_selected_marks()), "animatorsPencilShortcutErase"),
            ("toggle_translucent", lambda: self._after_action(self.controller.toggle_marks_translucent(self.current_layer)), "animatorsPencilShortcutTranslucent"),
        )
        for action_name, callback, object_name in shortcut_specs:
            key_text = bindings.get(action_name)
            if not key_text:
                continue
            try:
                shortcut = shortcut_type(QtGui.QKeySequence(key_text), self)
                shortcut.setObjectName(object_name)
                shortcut_context = _qt_flag(
                    "ShortcutContext",
                    "WindowShortcut" if action_name == "eraser_tool" else "WidgetWithChildrenShortcut",
                )
                if shortcut_context is not None:
                    shortcut.setContext(shortcut_context)
                shortcut.setAutoRepeat(False)
                shortcut.activated.connect(lambda _callback=callback: self._run_panel_shortcut(_callback))
                self._shortcuts[action_name] = shortcut
            except Exception:
                continue

    def showEvent(self, event):
        super(AnimatorsPencilPanel, self).showEvent(event)
        drawing_view_name_edit = getattr(self, "drawing_view_name_edit", None)
        if _qt_object_valid(drawing_view_name_edit):
            drawing_view_name_edit.removeEventFilter(self)
            drawing_view_name_edit.installEventFilter(self)
        if not self._drawing_enabled:
            self._set_start_button_state(False)
        QtCore.QTimer.singleShot(0, self._activate_runtime_input)

    def hideEvent(self, event):
        self._deactivate_runtime_input()
        drawing_view_name_edit = getattr(self, "drawing_view_name_edit", None)
        if _qt_object_valid(drawing_view_name_edit):
            drawing_view_name_edit.removeEventFilter(self)
        super(AnimatorsPencilPanel, self).hideEvent(event)

    def _activate_runtime_input(self):
        if self._runtime_input_active or not self.isVisible():
            return
        self._runtime_input_active = True
        self._viewport_navigation_filter.refresh()
        self._install_marking_menus()
        self._install_brush_shortcuts()
        self._apply_brush_cursor()

    def _deactivate_runtime_input(self):
        # Leaving the panel or switching tools must never strand the yellow
        # marquee curve. Bake the selected marks back to their layer first;
        # the controller's scoped SelectionChanged watcher is removed as part
        # of that commit.
        self.controller._commit_marquee_transform_box()
        if not self._runtime_input_active:
            self._viewport_navigation_filter.clear()
            self._viewport_input_mode = ""
            self._set_start_button_state(False)
            return
        self._runtime_input_active = False
        self._viewport_input_mode = ""
        self._viewport_navigation_filter.clear()
        self._set_drawing_enabled(False, restore_tool=True, update_status=False)
        if _qt_object_valid(self._color_swatch_window):
            self._color_swatch_window.hide()
        self._set_marking_menus_enabled(False)
        self._set_brush_shortcuts_enabled(False)
        self._clear_brush_cursor()

    def _install_marking_menus(self):
        self._marking_menu_conflicts = []
        self._marking_menu_errors = []
        if not MAYA_AVAILABLE:
            return
        live_menus = []
        for menu_name in list(self._marking_menus):
            try:
                if cmds.popupMenu(menu_name, exists=True):
                    self._set_popup_menu_items_enabled(menu_name, True)
                    live_menus.append(menu_name)
            except Exception as exc:
                self._marking_menu_errors.append("{0}: {1}".format(menu_name, exc))
                continue
        self._marking_menus = live_menus
        radial_positions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        panel_controls = []
        for panel_name in cmds.getPanel(type="modelPanel") or []:
            try:
                control_name = cmds.modelPanel(panel_name, query=True, control=True)
            except Exception:
                control_name = ""
            if control_name:
                panel_controls.append((panel_name, control_name))

        chosen_trigger = None
        for trigger_label, trigger_flags in MARKING_MENU_TRIGGERS:
            conflicts = []
            for _panel_name, control_name in panel_controls:
                for menu_name in cmds.control(control_name, query=True, popupMenuArray=True) or []:
                    if menu_name.startswith(MARKING_MENU_PREFIX):
                        continue
                    try:
                        same_trigger = bool(
                            int(cmds.popupMenu(menu_name, query=True, button=True)) == 3
                            and all(bool(cmds.popupMenu(menu_name, query=True, **{flag: True})) == bool(value) for flag, value in trigger_flags.items())
                        )
                    except Exception:
                        same_trigger = False
                    if same_trigger:
                        conflicts.append(menu_name)
            if not conflicts:
                chosen_trigger = (trigger_label, trigger_flags)
                break
            self._marking_menu_conflicts.extend(conflicts)

        if not chosen_trigger:
            self.brush_shortcut_label.setToolTip("Animator Pencil left existing viewport marking menus untouched.")
            return
        trigger_label, trigger_flags = chosen_trigger
        self._marking_menu_trigger = trigger_label
        for panel_name, control_name in panel_controls:
            menu_name = "{0}_{1}".format(MARKING_MENU_PREFIX, _safe_name(panel_name))
            try:
                if cmds.popupMenu(menu_name, exists=True):
                    self._set_popup_menu_items_enabled(menu_name, True)
                    if menu_name not in self._marking_menus:
                        self._marking_menus.append(menu_name)
                    continue
                menu_name = cmds.popupMenu(
                    menu_name,
                    parent=control_name,
                    markingMenu=True,
                    button=3,
                    allowOptionBoxes=False,
                    **trigger_flags
                )
                for index, tool_name in enumerate(TOOL_NAMES):
                    menu_item_options = {
                        "parent": menu_name,
                        "label": tool_name,
                        "command": lambda *_args, _tool=tool_name: self._select_tool(_tool),
                    }
                    # Maya exposes only eight radial slots.  Keep the
                    # original tools in those slots and add the new Circle,
                    # Oval, and Star drag tools as ordinary menu items rather
                    # than silently dropping them from the marking menu.
                    if index < len(radial_positions):
                        menu_item_options["radialPosition"] = radial_positions[index]
                    cmds.menuItem(**menu_item_options)
                cmds.menuItem(parent=menu_name, divider=True)
                cmds.menuItem(
                    parent=menu_name,
                    label=RGB_SWATCH_MARKING_MENU_LABEL,
                    command=lambda *_args: self._open_color_swatch_window(),
                )
                self._marking_menus.append(menu_name)
            except Exception as exc:
                self._marking_menu_errors.append("{0}/{1}: {2}".format(panel_name, control_name, exc))
                continue
        if self._marking_menus:
            self.brush_shortcut_label.setToolTip(
                "{0} in a viewport opens every Pencil tool plus RGB colour and saved swatches.".format(trigger_label)
            )

    def _set_popup_menu_items_enabled(self, menu_name, enabled):
        if not MAYA_AVAILABLE or not menu_name or not cmds.popupMenu(menu_name, exists=True):
            return False
        changed = False
        for item_name in cmds.popupMenu(menu_name, query=True, itemArray=True) or []:
            try:
                cmds.menuItem(item_name, edit=True, enable=bool(enabled))
                changed = True
            except Exception:
                continue
        return changed

    def _set_marking_menus_enabled(self, enabled):
        if not MAYA_AVAILABLE:
            return
        for menu_name in list(self._marking_menus):
            try:
                if cmds.popupMenu(menu_name, exists=True):
                    self._set_popup_menu_items_enabled(menu_name, enabled)
            except Exception:
                continue

    def _remove_marking_menus(self):
        # Maya-owned popup teardown during Qt hide/reopen can crash Qt6Core.
        # Keep owned menus disabled for safe reuse. Process exit clears them.
        self._set_marking_menus_enabled(False)

    def _install_brush_shortcuts(self):
        live_shortcuts = {}
        for action_name, shortcut in list(self._runtime_shortcuts.items()):
            if _qt_object_valid(shortcut):
                try:
                    shortcut.setEnabled(True)
                    live_shortcuts[action_name] = shortcut
                except Exception:
                    continue
        self._runtime_shortcuts = live_shortcuts
        if len(self._runtime_shortcuts) == 2 and self._brush_shortcut_pair:
            self.brush_shortcut_label.setText("Keys {0} {1}".format(*self._brush_shortcut_pair))
            return
        shortcut_type = _shortcut_class()
        root_widget = _maya_main_qt_window()
        if shortcut_type is None or not _qt_object_valid(root_widget):
            self.brush_shortcut_label.setText("Size keys unavailable")
            return
        chosen_pair = ()
        for pair in BRUSH_SHORTCUT_PAIRS:
            if any(_maya_hotkey_name(sequence) or _qt_shortcut_in_use(sequence, root_widget) for sequence in pair):
                continue
            chosen_pair = pair
            break
        if not chosen_pair:
            self.brush_shortcut_label.setText("Size keys in use")
            self.brush_shortcut_label.setToolTip("Every safe brush-size key pair is already assigned. Aminate left all existing shortcuts untouched.")
            return
        context = _qt_flag("ShortcutContext", "ApplicationShortcut", None)
        for action_name, sequence, amount in (
            ("brush_smaller", chosen_pair[0], -1.0),
            ("brush_larger", chosen_pair[1], 1.0),
        ):
            shortcut = shortcut_type(QtGui.QKeySequence(sequence), root_widget)
            shortcut.setObjectName("animatorsPencilRuntime{0}".format(action_name.title().replace("_", "")))
            if context is not None:
                shortcut.setContext(context)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(lambda _amount=amount: self._adjust_brush_size(_amount))
            self._runtime_shortcuts[action_name] = shortcut
        self._runtime_shortcut_root = root_widget
        self._brush_shortcut_pair = chosen_pair
        self.brush_shortcut_label.setText("Keys {0} {1}".format(*chosen_pair))

    def _set_brush_shortcuts_enabled(self, enabled):
        for shortcut in list(self._runtime_shortcuts.values()):
            try:
                shortcut.setEnabled(bool(enabled))
            except Exception:
                pass

    def _remove_brush_shortcuts(self):
        # QShortcuts are parented to Maya's main window. Reuse them instead of
        # posting DeferredDelete events while Aminate is hiding or reopening.
        self._set_brush_shortcuts_enabled(False)

    def _adjust_brush_size(self, amount):
        if not self.isVisible() or self._is_text_input_focused():
            return
        self.size_spin.setValue(self.size_spin.value() + float(amount))
        self._set_status("Brush size {0:g}.".format(self.size_spin.value()))

    def _make_brush_cursor(self):
        tool_name = self.tool_combo.currentText()
        radius = int(round(self.size_spin.value() * (2.5 if tool_name == "Eraser" else 1.5)))
        radius = max(5, min(64, radius))
        diameter = (radius * 2) + 5
        pixmap = QtGui.QPixmap(diameter, diameter)
        pixmap.fill(_qt_flag("GlobalColor", "transparent", QtCore.Qt.transparent))
        painter = QtGui.QPainter(pixmap)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            center = diameter // 2
            painter.setBrush(_qt_flag("BrushStyle", "NoBrush", QtCore.Qt.NoBrush))
            painter.setPen(QtGui.QPen(QtGui.QColor("#0D1B2A"), 3))
            painter.drawEllipse(QtCore.QPoint(center, center), radius, radius)
            painter.setPen(QtGui.QPen(QtGui.QColor("#F7F9FB"), 1))
            painter.drawEllipse(QtCore.QPoint(center, center), radius, radius)
            painter.drawLine(center - 3, center, center + 3, center)
            painter.drawLine(center, center - 3, center, center + 3)
        finally:
            painter.end()
        self._brush_cursor_radius = radius
        return QtGui.QCursor(pixmap, diameter // 2, diameter // 2)

    def _apply_brush_cursor(self):
        self._clear_brush_cursor()
        if not self._drawing_enabled or not MAYA_AVAILABLE or self.tool_combo.currentText() not in ("Pencil", "Brush", "Eraser"):
            return
        cursor = self._make_brush_cursor()
        for panel_name in cmds.getPanel(type="modelPanel") or []:
            widget = _model_panel_qt_widget(panel_name)
            if not _qt_object_valid(widget):
                continue
            try:
                widget.setCursor(cursor)
                self._cursor_widgets.append(widget)
            except Exception:
                continue

    def _clear_brush_cursor(self):
        for widget in list(self._cursor_widgets):
            if not _qt_object_valid(widget):
                continue
            try:
                widget.unsetCursor()
            except Exception:
                pass
        self._cursor_widgets = []
        self._brush_cursor_radius = 0

    def _build_tool_menu(self, tool_names):
        menu = QtWidgets.QMenu(self)
        for tool_name in tool_names:
            action = menu.addAction(_make_tool_icon(tool_name), "{0} Tool".format(tool_name))
            action.setData(tool_name)
            action.triggered.connect(lambda _checked=False, name=tool_name: self._select_tool(name))
        return menu

    def _select_tool(self, tool_name):
        index = self.tool_combo.findText(tool_name)
        if index >= 0:
            if index == self.tool_combo.currentIndex():
                self._tool_changed(tool_name)
            else:
                self.tool_combo.setCurrentIndex(index)

    def _tool_changed(self, tool_name):
        icon = _make_tool_icon(tool_name)
        eraser_visible = tool_name == "Eraser"
        self.eraser_mode_combo.setVisible(eraser_visible)
        self.draw_button.setIcon(icon)
        self.start_drawing_button.setIcon(icon)
        self.draw_button.setToolTip("Stamp a default {0} mark on the active pencil layer.".format(tool_name))
        if tool_name in ("Pencil", "Brush"):
            self.start_drawing_button.setToolTip("Draw persistent freehand {0} strokes in the active viewport. Click again to stop.".format(tool_name))
        elif tool_name == "Eraser":
            self.start_drawing_button.setToolTip("Erase touched sections from strokes on the active layer. Click again to stop.")
        else:
            self.start_drawing_button.setToolTip("Drag in the active viewport to create persistent {0} marks. Click again to stop.".format(tool_name))
        if self._drawing_enabled:
            # A Qt combo edit can leave Maya on its select context. Re-edit
            # the existing dragger context so the next viewport gesture still
            # reaches Animator's Pencil.
            self._activate_drag_draw(force=True)
        else:
            self._set_drawing_enabled(True)

    def _activate_eraser(self):
        self._select_tool("Eraser")
        if not self._drawing_enabled:
            self._set_drawing_enabled(True)

    def _create_camera_notes_camera(self):
        camera = self.controller.camera_notes_camera(create=True)
        self._set_status("Camera Notes camera ready: {0}".format(camera or "not created"))

    def _key_camera_notes_camera(self):
        camera = self.controller.key_camera_notes_to_current_view(snap=self.camera_snap_box.isChecked(), switch_to_camera=False)
        self._set_status("Camera Notes keyed: {0}".format(camera or "not keyed"))

    def _switch_to_camera_notes(self):
        camera = self.controller.switch_to_camera_notes()
        self._set_status("Looking through Camera Notes: {0}".format(camera or "not available"))

    def refresh_drawing_views(self):
        views = self.controller.drawing_views() if MAYA_AVAILABLE else []
        current_camera = _current_camera() if MAYA_AVAILABLE else ""
        current_identity = _long_name(current_camera) if current_camera and cmds.objExists(current_camera) else current_camera
        self.drawing_view_combo.blockSignals(True)
        try:
            self.drawing_view_combo.clear()
            if not views:
                self.drawing_view_combo.addItem("No saved Pencil Views", "")
                return
            selected_index = 0
            for index, view in enumerate(views):
                camera = view.get("node") or ""
                self.drawing_view_combo.addItem(view.get("label") or view.get("name") or "Pencil View", camera)
                if camera == current_identity:
                    selected_index = index
            self.drawing_view_combo.setCurrentIndex(selected_index)
        finally:
            self.drawing_view_combo.blockSignals(False)

    def _begin_rename_drawing_view(self):
        if not self.drawing_view_combo.currentData():
            self._set_status("Choose a saved Pencil View before renaming it.")
            return False
        self.drawing_view_name_edit.setReadOnly(False)
        self.drawing_view_name_edit.selectAll()
        self.drawing_view_name_edit.setFocus()
        return True

    def _finish_rename_drawing_view(self):
        if self.drawing_view_name_edit.isReadOnly():
            return False
        camera = self.drawing_view_combo.currentData()
        requested = self.drawing_view_name_edit.text()
        self.drawing_view_name_edit.setReadOnly(True)
        ok, message = self.controller.rename_drawing_view(camera, requested)
        if not ok:
            current = self.controller.drawing_view_data(camera).get("label", "") if camera else ""
            self.drawing_view_combo.blockSignals(True)
            self.drawing_view_name_edit.setText(current)
            self.drawing_view_combo.blockSignals(False)
            self._set_status(message)
            return False
        self.refresh_drawing_views()
        self._set_status("Renamed saved drawing view: {0}.".format(message))
        return True

    def eventFilter(self, watched, event):
        if watched is getattr(self, "drawing_view_name_edit", None) and event.type() == _qt_event_type("MouseButtonDblClick"):
            self._begin_rename_drawing_view()
            return True
        return super(AnimatorsPencilPanel, self).eventFilter(watched, event)

    def _save_current_drawing_view(self):
        camera = self.controller.create_drawing_view_from_current_view(switch=True)
        if not camera:
            self._set_status("Could not save the current Pencil View.")
            return ""
        self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=camera)
        self.refresh_drawing_views()
        self.refresh_layers()
        self._drawing_options_changed()
        return camera

    def _switch_saved_drawing_view(self):
        index = self.drawing_view_combo.currentIndex()
        camera = self.drawing_view_combo.itemData(index) if index >= 0 else ""
        if not camera:
            return ""
        camera = self.controller.switch_to_drawing_view(camera)
        if not camera:
            return ""
        self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=camera)
        self.refresh_drawing_views()
        self.refresh_layers()
        self._drawing_options_changed()
        return camera

    def _sync_video_mode_button(self):
        """Keep the one viewer action truthful after camera/window changes."""
        if not getattr(self, "show_pencil_view_button", None):
            return
        display_mode = str(getattr(self, "_video_display_mode", "pinned") or "pinned")
        if display_mode == "main_view":
            if self._video_in_draw_over_mode:
                self.show_pencil_view_button.setText("Switch to Normal Viewport Drawing")
                self.show_pencil_view_button.setToolTip("Leave the video Pencil View and return to the normal viewport drawing camera.")
            else:
                self.show_pencil_view_button.setText("Switch to Draw Over Video")
                self.show_pencil_view_button.setToolTip("Temporarily switch the main viewport to the attached video's Pencil View.")
        else:
            if self._video_camera_handoff_active:
                self.show_pencil_view_button.setText("Switch to Normal Viewport Drawing")
                self.show_pencil_view_button.setToolTip(
                    "Return the main viewport to the camera that was active before attaching this video. Keep the Reference Viewer visible."
                )
                return
            visible = bool(_reference_viewer().is_visible()) if MAYA_AVAILABLE else False
            self._video_viewer_visible = visible
            self.show_pencil_view_button.setText("Hide Reference Viewer" if visible else "Show Reference Viewer")
            self.show_pencil_view_button.setToolTip(
                "Hide the retained Reference Viewer without deleting it." if visible
                else "Show the complete video-and-annotations Reference Viewer without changing the perspective camera."
            )

    def _persist_video_viewer_state(self, visible=None):
        transform = self._video_overlay_transform
        if not MAYA_AVAILABLE or not transform or not cmds.objExists(transform):
            return False
        mode = str(self.video_display_combo.currentData() or "pinned")
        placement = str(self.video_placement_combo.currentData() or "top_right")
        scale = max(0.10, min(2.0, float(self.video_scale_spin.value()) / 100.0))
        _set_string_attr(transform, VIDEO_VIEWER_MODE_ATTR, mode)
        _set_string_attr(transform, VIDEO_VIEWER_PLACEMENT_ATTR, placement)
        _ensure_attr(transform, VIDEO_VIEWER_SCALE_ATTR, "double", scale)
        cmds.setAttr(transform + "." + VIDEO_VIEWER_SCALE_ATTR, scale)
        _ensure_attr(transform, VIDEO_VIEWER_VISIBLE_ATTR, "bool", bool(self._video_viewer_visible if visible is None else visible))
        cmds.setAttr(transform + "." + VIDEO_VIEWER_VISIBLE_ATTR, bool(self._video_viewer_visible if visible is None else visible))
        viewer = _reference_viewer()
        geometry = viewer.floating_geometry()
        if geometry is not None:
            _set_string_attr(
                transform,
                VIDEO_VIEWER_FREEFORM_GEOMETRY_ATTR,
                json.dumps(
                    {
                        "height": int(geometry.height()),
                        "width": int(geometry.width()),
                        "x": int(geometry.x()),
                        "y": int(geometry.y()),
                    },
                    sort_keys=True,
                ),
            )
        return True

    def _stored_reference_viewer_geometry(self):
        """Return a scene-stored freeform rectangle, if it is well formed."""
        transform = self._video_overlay_transform
        if not MAYA_AVAILABLE or not transform or not cmds.objExists(transform):
            return None
        raw_value = _get_string_attr(transform, VIDEO_VIEWER_FREEFORM_GEOMETRY_ATTR, "")
        if not raw_value:
            return None
        try:
            value = json.loads(raw_value)
            geometry = QtCore.QRect(
                int(value["x"]),
                int(value["y"]),
                int(value["width"]),
                int(value["height"]),
            )
        except Exception:
            return None
        return geometry if geometry.width() >= 280 and geometry.height() >= 158 else None

    def _sync_reference_viewer_freeform_state(self, viewer):
        """Reflect a direct title-bar move in the compact Video Draw-Over controls."""
        if viewer.mode != "floating":
            return False
        transitioned = viewer.consume_freeform_transition()
        geometry_changed = viewer.consume_freeform_geometry_dirty()
        if not (transitioned or geometry_changed):
            return False
        freeform_index = self.video_display_combo.findData("floating")
        if freeform_index >= 0 and self.video_display_combo.currentIndex() != freeform_index:
            self.video_display_combo.blockSignals(True)
            self.video_display_combo.setCurrentIndex(freeform_index)
            self.video_display_combo.blockSignals(False)
        self._video_display_mode = "floating"
        self._video_viewer_visible = bool(viewer.is_visible())
        self._persist_video_viewer_state(visible=self._video_viewer_visible)
        if transitioned:
            self._set_status("Reference Viewer detached. Move or resize it anywhere, including another display.")
        return True

    def _reference_viewer_hidden_nodes(self, camera):
        """Return long DAG nodes that belong only to the viewer camera.

        Camera scope deliberately keeps the viewer-camera layer visible at the
        scene level so the retained Reference Viewer can draw it.  Main Maya
        panels receive a separate scene list instead, with this camera, its
        camera-space layer, and every mark descendant removed from that list.
        """
        if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
            return set()
        hidden = set()

        def add_node_and_descendants(node_name):
            if not node_name or not cmds.objExists(node_name):
                return
            node_name = _long_name(node_name)
            hidden.add(node_name)
            try:
                hidden.update(cmds.listRelatives(node_name, allDescendents=True, fullPath=True) or [])
            except Exception:
                pass

        add_node_and_descendants(camera)
        try:
            for shape in cmds.listRelatives(camera, shapes=True, fullPath=True) or []:
                add_node_and_descendants(shape)
                # Image planes are often parented under a separate placement
                # transform, so they are not guaranteed to be descendants of
                # the camera.  Keep their viewport icon/transform out of the
                # ordinary panels as well; the retained Reference Viewer
                # still owns the camera and its image-plane display.
                for image_plane in cmds.listConnections(shape, type="imagePlane") or []:
                    add_node_and_descendants(image_plane)
        except Exception:
            pass
        camera_short = _short_name(camera)
        root_name = _long_name(self.controller.root()) if self.controller.root() and cmds.objExists(self.controller.root()) else ""
        for layer in self.controller.layers(include_count=False):
            layer_camera = _short_name(layer.get("camera") or "")
            if layer_camera == camera_short:
                layer_node = _long_name(layer.get("node") or "")
                add_node_and_descendants(layer_node)
                # A camera-space layer is parented under an anchor transform.
                # Listing that anchor in the panel connection would make Maya
                # draw every descendant again, even when the mark itself was
                # removed from the temporary list.  Hide only the viewer
                # camera's ancestor chain, including the shared Pencil root as
                # a single excluded entry, so selecting that root cannot
                # re-show the viewer descendants. Other-camera layers remain
                # available because they are listed individually.
                parent = (cmds.listRelatives(layer_node, parent=True, fullPath=True) or [""])[0]
                while parent:
                    if parent == root_name:
                        hidden.add(parent)
                        break
                    add_node_and_descendants(parent)
                    parent = (cmds.listRelatives(parent, parent=True, fullPath=True) or [""])[0]
        return hidden

    @staticmethod
    def _reference_viewer_connection_exists(connection_name):
        if not MAYA_AVAILABLE or not connection_name:
            return False
        try:
            return bool(cmds.selectionConnection(connection_name, query=True, exists=True))
        except Exception:
            return False

    def _delete_reference_viewer_connection(self, connection_name):
        """Clear a temporary list without deleting Maya-owned UI objects.

        Maya's ``selectionConnection`` is a UI object.  The reliable-change
        guard (and Maya's retained workspace lifecycle) require us to reuse
        and clear it rather than call ``deleteUI`` during normal viewer hide.
        """
        if not connection_name:
            return
        try:
            if self._reference_viewer_connection_exists(connection_name):
                cmds.selectionConnection(connection_name, edit=True, clear=True)
        except Exception:
            pass

    def _build_reference_viewer_connection(self, panel_name, hidden_nodes):
        """Build a panel-local all-DAG list without viewer-camera nodes."""
        connection = self._reference_viewer_panel_connections.get(panel_name, "")
        if not self._reference_viewer_connection_exists(connection):
            connection = cmds.selectionConnection()
            self._reference_viewer_panel_connections[panel_name] = connection
        else:
            try:
                cmds.selectionConnection(connection, edit=True, clear=True)
            except Exception:
                pass
        try:
            dag_nodes = cmds.ls(dag=True, long=True) or []
        except Exception:
            dag_nodes = []
        visible_nodes = []
        for node_name in dag_nodes:
            try:
                node_name = _long_name(node_name)
            except Exception:
                continue
            if node_name in hidden_nodes:
                continue
            visible_nodes.append(node_name)
        try:
            # Maya accepts a node list for one edit call on current releases;
            # this avoids one command-port round-trip per DAG node on large
            # animation scenes.  Keep the per-node fallback for older builds.
            if visible_nodes:
                cmds.selectionConnection(connection, edit=True, select=visible_nodes)
                return connection
        except Exception:
            pass
        for node_name in visible_nodes:
            try:
                cmds.selectionConnection(connection, edit=True, select=node_name)
            except Exception:
                continue
        return connection

    def _sync_reference_viewer_main_panel_scope(self, camera, force=False):
        """Hide only viewer-camera nodes from the ordinary model panels.

        ``viewSelected`` is intentionally scoped to each main panel's own
        temporary selectionConnection.  The retained Reference Viewer panel
        is never included in ``_main_model_panels()``, so it keeps the complete
        viewer-camera layer and image plane.
        """
        if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
            self._restore_reference_viewer_main_panel_scope()
            return False
        panels = _main_model_panels()
        hidden_nodes = self._reference_viewer_hidden_nodes(camera)
        handoff_active = bool(getattr(self, "_video_camera_handoff_active", False))
        panel_cameras = {}
        for panel_name in panels:
            try:
                panel_cameras[panel_name] = _panel_camera_transform(panel_name)
            except Exception:
                panel_cameras[panel_name] = ""
        signature = (
            tuple(panels),
            _short_name(camera),
            tuple(sorted(hidden_nodes)),
            handoff_active,
            tuple(_long_name(panel_cameras.get(panel_name) or "") for panel_name in panels),
        )
        if not force and signature == self._reference_viewer_scope_signature:
            return False
        for panel_name in panels:
            if panel_name not in self._reference_viewer_panel_states:
                try:
                    self._reference_viewer_panel_states[panel_name] = {
                        "main": cmds.modelEditor(panel_name, query=True, mainListConnection=True),
                        "filter": cmds.modelEditor(panel_name, query=True, filter=True),
                        "view_selected": bool(cmds.modelEditor(panel_name, query=True, viewSelected=True)),
                        "view_objects": cmds.modelEditor(panel_name, query=True, filteredObjectList=True) or [],
                    }
                except Exception:
                    self._reference_viewer_panel_states[panel_name] = {
                        "main": "",
                        "filter": "",
                        "view_selected": False,
                        "view_objects": [],
                    }
            panel_camera = panel_cameras.get(panel_name) or ""
            video_camera_panel = bool(
                handoff_active
                and panel_camera
                and _long_name(panel_camera) == _long_name(camera)
            )
            try:
                if video_camera_panel:
                    # This is the one ordinary panel deliberately showing the
                    # attached video camera.  Leave the retained viewer's
                    # other panels isolated, but let this panel display the
                    # image plane and its camera-space Pencil marks.
                    original_filter = self._reference_viewer_panel_states[panel_name].get("filter") or ""
                    cmds.modelEditor(panel_name, edit=True, viewSelected=False, filter=original_filter)
                    continue
                connection = self._build_reference_viewer_connection(panel_name, hidden_nodes)
                original_filter = self._reference_viewer_panel_states[panel_name].get("filter") or ""
                cmds.modelEditor(
                    panel_name,
                    edit=True,
                    mainListConnection=connection,
                    viewSelected=True,
                    filter=original_filter,
                )
            except Exception:
                continue
        self._reference_viewer_scope_signature = signature
        return bool(panels)

    def _restore_reference_viewer_main_panel_scope(self):
        """Return main panels to normal scene display and clear temp lists."""
        if not MAYA_AVAILABLE:
            self._reference_viewer_panel_states = {}
            self._reference_viewer_panel_connections = {}
            self._reference_viewer_scope_signature = None
            return False
        for panel_name, state in list(self._reference_viewer_panel_states.items()):
            try:
                if not cmds.modelPanel(panel_name, exists=True):
                    continue
                original_filter = state.get("filter") or ""
                # Clearing viewSelected returns the panel to Maya's normal
                # all-scene display.  Maya's built-in lockedList connection
                # is internal and cannot be reassigned by name after a custom
                # list, so do not leave the temporary isolate state active.
                cmds.modelEditor(panel_name, edit=True, viewSelected=False, filter=original_filter)
            except Exception:
                continue
        for connection in list(self._reference_viewer_panel_connections.values()):
            self._delete_reference_viewer_connection(connection)
        self._reference_viewer_panel_states = {}
        self._reference_viewer_panel_connections = {}
        self._reference_viewer_scope_signature = None
        return True

    def _show_reference_viewer(self):
        camera = self._video_overlay_camera or self.video_reference_controller.camera_name
        if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
            self._set_status("Attach a video first so Aminate knows which Pencil View to show.")
            return False
        mode = str(self.video_display_combo.currentData() or "pinned")
        if mode == "main_view":
            return self._show_video_pencil_view()
        viewer = _reference_viewer()
        if mode == "floating":
            viewer.set_floating_geometry(self._stored_reference_viewer_geometry())
        success, message = viewer.show(
            camera,
            mode=mode,
            placement=str(self.video_placement_combo.currentData() or "top_right"),
            scale_percent=float(self.video_scale_spin.value()),
            anchor_panel=self._video_anchor_panel,
        )
        self._video_viewer_visible = bool(success)
        self._video_in_draw_over_mode = False
        # The Reference Viewer owns a second real modelPanel. Its camera must
        # stay in the scope allow-list while the main viewport changes, or the
        # next main-camera refresh hides its own draw-over layer globally.
        # Camera-space layers still sit on their assigned camera plane, so the
        # animator's perspective viewport remains an animation workspace.
        self.controller.set_additional_visible_cameras([viewer.camera] if success and viewer.camera else [])
        if success and viewer.camera:
            self._sync_reference_viewer_main_panel_scope(viewer.camera, force=True)
        else:
            self._restore_reference_viewer_main_panel_scope()
        self._persist_video_viewer_state(visible=success)
        self._sync_video_mode_button()
        self._set_status(message)
        return bool(success)

    def _switch_visible_view_to_camera(self, camera):
        """Switch the actual visible model panel and verify Maya accepted it."""
        if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
            return False
        camera = _long_name(camera)
        if not self.controller.switch_to_drawing_view(camera):
            return False
        panels = []
        try:
            active = _active_model_panel()
            if active:
                panels.append(active)
        except Exception:
            pass
        try:
            panels.extend(panel for panel in _main_model_panels() if panel not in panels)
        except Exception:
            pass
        for panel in panels:
            try:
                cmds.modelPanel(panel, edit=True, camera=camera)
                assigned = cmds.modelEditor(panel, query=True, camera=True)
                if assigned == camera or _long_name(assigned) == camera:
                    return True
            except Exception:
                continue
        return False

    def _normal_camera_for_video(self, overlay_camera, current_camera=""):
        """Resolve the camera to return to when leaving Video Draw-Over."""
        if overlay_camera and self.controller.is_drawing_view(overlay_camera):
            try:
                source = self.controller.drawing_view_data(overlay_camera).get("source", "")
                if source and cmds.objExists(source) and _long_name(source) != _long_name(overlay_camera):
                    return _long_name(source)
            except Exception:
                pass
        if current_camera and cmds.objExists(current_camera) and _long_name(current_camera) != _long_name(overlay_camera):
            try:
                if not self.controller.is_drawing_view(current_camera):
                    return _long_name(current_camera)
            except Exception:
                return _long_name(current_camera)
        if MAYA_AVAILABLE and cmds.objExists("persp"):
            return _long_name("persp")
        return ""

    def _restore_video_draw_over_state(self):
        """Read one existing scene overlay without importing or changing Maya time."""
        info = self.video_reference_controller.discover_camera_overlay()
        if not info:
            self.show_pencil_view_button.setEnabled(False)
            return False
        self._video_overlay_transform = info.get("transform") or ""
        self._video_overlay_camera = info.get("camera") or ""
        self._video_normal_camera = self._normal_camera_for_video(self._video_overlay_camera, _current_camera() if MAYA_AVAILABLE else "")
        placement = _get_string_attr(self._video_overlay_transform, VIDEO_VIEWER_PLACEMENT_ATTR, "") or info.get("placement") or "top_right"
        display_mode = _get_string_attr(self._video_overlay_transform, VIDEO_VIEWER_MODE_ATTR, "") or "pinned"
        if display_mode not in ("pinned", "floating", "main_view"):
            display_mode = "pinned"
        stored_viewer_scale = None
        try:
            if cmds.objExists(self._video_overlay_transform + "." + VIDEO_VIEWER_SCALE_ATTR):
                stored_viewer_scale = float(cmds.getAttr(self._video_overlay_transform + "." + VIDEO_VIEWER_SCALE_ATTR))
        except Exception:
            stored_viewer_scale = None
        try:
            viewer_visible = bool(cmds.getAttr(self._video_overlay_transform + "." + VIDEO_VIEWER_VISIBLE_ATTR)) if cmds.objExists(self._video_overlay_transform + "." + VIDEO_VIEWER_VISIBLE_ATTR) else False
        except Exception:
            viewer_visible = False
        display_index = self.video_display_combo.findData(display_mode)
        placement_index = self.video_placement_combo.findData(placement)
        self.video_display_combo.blockSignals(True)
        self.video_placement_combo.blockSignals(True)
        self.video_start_frame_spin.blockSignals(True)
        self.video_scale_spin.blockSignals(True)
        self.video_opacity_spin.blockSignals(True)
        self.video_line_opacity_spin.blockSignals(True)
        self.video_keep_strokes_on_top_box.blockSignals(True)
        try:
            if display_index >= 0:
                self.video_display_combo.setCurrentIndex(display_index)
            self._video_display_mode = display_mode
            if placement_index >= 0:
                self.video_placement_combo.setCurrentIndex(placement_index)
            self._video_last_placement = placement
            self.video_start_frame_spin.setValue(int(info.get("start_frame") or 1))
            self.video_scale_spin.setValue(float((stored_viewer_scale * 100.0) if stored_viewer_scale is not None else info.get("scale_percent", 100 if placement == "full_view" else 38)))
            self.video_opacity_spin.setValue(float(info.get("opacity", 0.8)) * 100.0)
            self.video_include_audio_box.setChecked(bool(info.get("audio_enabled", info.get("sound"))))
            active_layer_data = self.controller.layer_data(self.current_layer, include_count=False) if self.current_layer else {}
            self.video_line_opacity_spin.setValue(float(active_layer_data.get("opacity", 1.0)) * 100.0)
            self.video_keep_strokes_on_top_box.setChecked(bool(info.get("keep_strokes_on_top")))
        finally:
            self.video_display_combo.blockSignals(False)
            self.video_placement_combo.blockSignals(False)
            self.video_start_frame_spin.blockSignals(False)
            self.video_scale_spin.blockSignals(False)
            self.video_opacity_spin.blockSignals(False)
            self.video_line_opacity_spin.blockSignals(False)
            self.video_keep_strokes_on_top_box.blockSignals(False)

        camera = self._video_overlay_camera
        camera_is_drawing_view = bool(camera and cmds.objExists(camera) and self.controller.is_drawing_view(camera))
        current_camera = _current_camera() if MAYA_AVAILABLE else ""
        in_video_camera = bool(camera_is_drawing_view and current_camera and _long_name(current_camera) == _long_name(camera))
        self._video_in_draw_over_mode = bool(display_mode == "main_view" and in_video_camera)
        self._video_camera_handoff_active = bool(display_mode != "main_view" and viewer_visible and in_video_camera)
        self.show_pencil_view_button.setEnabled(camera_is_drawing_view)
        if camera_is_drawing_view:
            self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=camera)
        if camera_is_drawing_view and viewer_visible and display_mode != "main_view":
            # Reopening a saved PIP scene already has a full-view image-plane
            # composition stored on the camera. Rewriting every image-plane
            # placement plug (and the updated-at stamp) here makes Maya defer a
            # costly media redraw into the first post-open camera switch.
            stored_overlay_scale = float(info.get("scale", 1.0) or 1.0)
            baseline_metadata_ready = all(
                cmds.objExists(self._video_overlay_transform + "." + attr_name)
                for attr_name in (
                    "amirVideoOverlayBaselineWidth",
                    "amirVideoOverlayBaselineHeight",
                    "amirVideoOverlayBaselineSizeX",
                    "amirVideoOverlayBaselineSizeY",
                    "amirVideoOverlayBaselineOffsetX",
                    "amirVideoOverlayBaselineOffsetY",
                    "amirVideoOverlayBaselineDepth",
                )
            )
            overlay_needs_restore = bool(
                not baseline_metadata_ready
                or
                str(info.get("placement") or "full_view").lower() != "full_view"
                or abs(stored_overlay_scale - 1.0) > 0.0001
                or bool(info.get("keep_strokes_on_top")) != bool(self.video_keep_strokes_on_top_box.isChecked())
            )
            if overlay_needs_restore:
                self.video_reference_controller.apply_camera_overlay_placement(
                    "full_view",
                    bool(self.video_keep_strokes_on_top_box.isChecked()),
                    transform_name=self._video_overlay_transform,
                    scale_percent=100.0,
                )
            self._show_reference_viewer()
        self._sync_video_mode_button()
        source_path = info.get("source_path") or ""
        source_label = os.path.basename(source_path) if source_path else "scene video source"
        if camera_is_drawing_view:
            status = "Restored: {0} | {1}.".format(source_label, placement.replace("_", " "))
        else:
            status = "Restored: {0} | {1}. Pencil View camera unavailable.".format(source_label, placement.replace("_", " "))
        self.video_source_status.setText(status)
        self._video_scale_user_edited = False
        self._set_status(status)
        return True

    def _ensure_video_pencil_view(self, switch=False):
        if not MAYA_AVAILABLE:
            return ""
        current_camera = _current_camera()
        if current_camera and self.controller.is_drawing_view(current_camera):
            self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=current_camera)
            self.refresh_drawing_views()
            self.refresh_layers()
            return _long_name(current_camera)
        views = self.controller.drawing_views()
        if views:
            index = self.drawing_view_combo.currentIndex()
            camera = self.drawing_view_combo.itemData(index) if index >= 0 else ""
            camera = camera or views[0].get("node")
            camera = self.controller.switch_to_drawing_view(camera) if switch else camera
            if camera:
                self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=camera)
                self.refresh_drawing_views()
                self.refresh_layers()
            return camera or ""
        source_camera = current_camera or _current_camera()
        camera = self.controller.create_drawing_view_from_current_view(switch=bool(switch), source_camera=source_camera)
        if camera:
            self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=camera)
            self.refresh_drawing_views()
            self.refresh_layers()
        return camera or ""

    def _attach_video_draw_over(self):
        if not MAYA_AVAILABLE:
            self._set_status("Video Draw-Over needs Maya.")
            return False
        media_path, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Attach Video Draw-Over",
            "",
            "Video or image sequence (*.mp4 *.mov *.m4v *.avi *.mkv *.webm *.png *.jpg *.jpeg *.tif *.tiff);;All Files (*)",
        )
        if not media_path:
            return False
        previous_panel = _active_model_panel() if MAYA_AVAILABLE else ""
        previous_camera = _panel_camera_transform(previous_panel) if previous_panel else (_current_camera() if MAYA_AVAILABLE else "")
        self._video_anchor_panel = previous_panel if previous_panel != REFERENCE_VIEWER_PANEL_NAME else ""
        camera = self._ensure_video_pencil_view(switch=False)
        if not camera:
            self._set_status("Could not create or switch to a fixed Pencil View.")
            return False
        self._video_normal_camera = self._normal_camera_for_video(camera, previous_camera)
        old_overlays = self.video_reference_controller.camera_overlay_transforms(camera)
        controller = self.video_reference_controller
        controller.camera_name = camera
        controller.media_path = str(media_path)
        controller.start_frame = int(self.video_start_frame_spin.value())
        controller.opacity = max(0.0, min(1.0, float(self.video_opacity_spin.value()) / 100.0))
        controller.import_audio = bool(self.video_include_audio_box.isChecked())
        controller.placement_mode = "camera_overlay"
        self._video_display_mode = str(self.video_display_combo.currentData() or "pinned")
        viewer_placement = str(self.video_placement_combo.currentData() or "top_right")
        controller.camera_overlay_placement = viewer_placement if self._video_display_mode == "main_view" else "full_view"
        controller.camera_overlay_scale = float(self.video_scale_spin.value()) / 100.0 if self._video_display_mode == "main_view" else 1.0
        controller.keep_strokes_on_top = bool(self.video_keep_strokes_on_top_box.isChecked())
        success, message = controller.import_reference()
        if not success:
            self._video_in_draw_over_mode = False
            self._video_camera_handoff_active = False
            self._sync_video_mode_button()
            self.video_source_status.setText(str(message))
            self._set_status(str(message))
            return False
        self._video_overlay_camera = camera
        self._video_overlay_transform = controller.last_transform
        if self._video_display_mode == "main_view":
            self._video_camera_handoff_active = False
            switched = self._switch_visible_view_to_camera(camera)
            self._video_in_draw_over_mode = bool(switched)
            self._video_viewer_visible = False
        else:
            self._video_in_draw_over_mode = False
            self._video_camera_handoff_active = False
            viewer_shown = self._show_reference_viewer()
            # Pinned and freeform viewers remain independent windows, while
            # the active main Maya modelPanel follows the same Pencil View so
            # the animator can draw over the video at full size.
            switched = bool(viewer_shown and self._switch_visible_view_to_camera(camera))
            self._video_camera_handoff_active = bool(switched)
            if switched:
                self._sync_reference_viewer_main_panel_scope(camera, force=True)
        self.show_pencil_view_button.setEnabled(bool(camera and self.controller.is_drawing_view(camera)))
        self._sync_video_mode_button()
        placement_success, placement_message = controller.apply_camera_overlay_placement(
            controller.camera_overlay_placement,
            controller.keep_strokes_on_top,
            transform_name=controller.last_transform,
            scale_percent=self.video_scale_spin.value() if self._video_display_mode == "main_view" else 100.0,
        )
        if not placement_success:
            self.video_source_status.setText(str(placement_message))
            self._set_status(str(placement_message))
            return False
        if old_overlays:
            controller.remove_camera_overlays(camera_name=camera, transforms=old_overlays)
        self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=camera)
        self.refresh_layers()
        self.video_opacity_spin.blockSignals(True)
        self.video_opacity_spin.setValue(float(controller.opacity) * 100.0)
        self.video_opacity_spin.blockSignals(False)
        self.video_scale_spin.blockSignals(True)
        if self._video_display_mode == "main_view":
            self.video_scale_spin.setValue(float(controller.camera_overlay_scale or (100.0 if controller.camera_overlay_placement == "full_view" else 38.0)) * 100.0)
        self.video_scale_spin.blockSignals(False)
        self._video_scale_user_edited = False
        self._video_last_placement = viewer_placement
        self._persist_video_viewer_state(visible=self._video_viewer_visible)
        self.video_source_status.setText("Attached: {0} | {1}".format(os.path.basename(media_path), placement_message))
        self._set_status(
            "Video Draw-Over ready. The Reference Viewer and main viewport are on the video Pencil View; "
            "use Switch to Normal Viewport Drawing to return to the previous camera."
        )
        return True

    def _video_display_changed(self, _index=None):
        self._video_display_mode = str(self.video_display_combo.currentData() or "pinned")
        if self._video_display_mode == "main_view":
            self._video_camera_handoff_active = False
            _reference_viewer().hide()
            self._video_viewer_visible = False
            self.controller.set_additional_visible_cameras([])
            self._restore_reference_viewer_main_panel_scope()
            if self._video_overlay_camera and cmds.objExists(self._video_overlay_camera):
                current_camera = _current_camera()
                self._video_in_draw_over_mode = bool(
                    current_camera and _long_name(current_camera) == _long_name(self._video_overlay_camera)
                )
            self._persist_video_viewer_state(visible=False)
            self._sync_video_mode_button()
            return self._video_overlay_options_changed() if self._video_overlay_transform else True
        if self._video_overlay_camera and cmds.objExists(self._video_overlay_camera):
            self._video_overlay_options_changed()
            shown = self._show_reference_viewer()
            current_camera = _current_camera()
            self._video_camera_handoff_active = bool(
                shown
                and current_camera
                and _long_name(current_camera) == _long_name(self._video_overlay_camera)
            )
            if self._video_camera_handoff_active:
                self._sync_reference_viewer_main_panel_scope(self._video_overlay_camera, force=True)
            self._sync_video_mode_button()
            return shown
        self._sync_video_mode_button()
        return True

    def _video_placement_changed(self, _index=None):
        placement = str(self.video_placement_combo.currentData() or "full_view")
        old_placement = self._video_last_placement
        crossed_category = (old_placement == "full_view") != (placement == "full_view")
        if crossed_category:
            self.video_scale_spin.blockSignals(True)
            self.video_scale_spin.setValue(100.0 if placement == "full_view" else 38.0)
            self.video_scale_spin.blockSignals(False)
            self._video_scale_user_edited = False
        elif not self._video_overlay_transform and not self._video_scale_user_edited:
            self.video_scale_spin.blockSignals(True)
            self.video_scale_spin.setValue(100.0 if placement == "full_view" else 38.0)
            self.video_scale_spin.blockSignals(False)
        self._video_last_placement = placement
        return self._video_overlay_options_changed()

    def _video_scale_changed(self, _value=None):
        self._video_scale_user_edited = True
        return self._video_overlay_options_changed()

    def _video_overlay_options_changed(self, _value=None):
        controller = self.video_reference_controller
        if not MAYA_AVAILABLE or not self._video_overlay_transform or not cmds.objExists(self._video_overlay_transform):
            return False
        display_mode = str(self.video_display_combo.currentData() or "pinned")
        viewer_placement = str(self.video_placement_combo.currentData() or "top_right")
        controller.camera_overlay_placement = viewer_placement if display_mode == "main_view" else "full_view"
        controller.keep_strokes_on_top = bool(self.video_keep_strokes_on_top_box.isChecked())
        success, message = controller.apply_camera_overlay_placement(
            controller.camera_overlay_placement,
            controller.keep_strokes_on_top,
            transform_name=self._video_overlay_transform,
            scale_percent=self.video_scale_spin.value() if display_mode == "main_view" else 100.0,
        )
        if success:
            if display_mode != "main_view" and _reference_viewer().is_visible():
                _reference_viewer().show(
                    self._video_overlay_camera,
                    mode=display_mode,
                    placement=viewer_placement,
                    scale_percent=float(self.video_scale_spin.value()),
                    anchor_panel=self._video_anchor_panel,
                )
                self._video_viewer_visible = True
            self._persist_video_viewer_state(visible=self._video_viewer_visible)
            self.video_source_status.setText("Attached: {0}".format(message))
        else:
            self._set_status(str(message))
        return success

    def _video_opacity_changed(self, value):
        """Apply the Video Draw-Over percentage without waiting for re-import."""
        controller = self.video_reference_controller
        controller.opacity = max(0.0, min(1.0, float(value) / 100.0))
        if not MAYA_AVAILABLE or not self._video_overlay_transform or not cmds.objExists(self._video_overlay_transform):
            return False
        success, message = controller.set_video_opacity(controller.opacity, self._video_overlay_transform)
        if success:
            self.video_source_status.setText("Attached video | {0}% opacity".format(int(round(controller.opacity * 100.0))))
        else:
            self._set_status(str(message))
        return success

    def _video_line_opacity_changed(self, value):
        """Apply the Video Draw-Over Pencil-lines percentage to the active layer."""
        layer = self._selected_layer_from_table()
        if not layer:
            return False
        success = self.controller.set_layer_opacity(layer, float(value) / 100.0)
        if success:
            self.refresh_layers()
            self._preserve_active_viewport_input()
            self._set_status("Pencil line opacity: {0}%".format(int(round(float(value)))))
        return success

    def _video_start_frame_changed(self, value):
        controller = self.video_reference_controller
        controller.start_frame = int(value)
        if MAYA_AVAILABLE and self._video_overlay_transform and cmds.objExists(self._video_overlay_transform):
            success, message = controller.update_current_reference_timing()
            if success:
                self.video_source_status.setText("Attached video starts at frame {0}.".format(int(value)))
            else:
                self._set_status(str(message))

    def _video_include_audio_changed(self, checked):
        controller = self.video_reference_controller
        controller.import_audio = bool(checked)
        if not MAYA_AVAILABLE or not self._video_overlay_transform or not cmds.objExists(self._video_overlay_transform):
            return True
        success, message = controller.set_audio_enabled(bool(checked), self._video_overlay_transform)
        self.video_source_status.setText("Attached video | {0}".format(message))
        if not success:
            self._set_status(str(message))
        return success

    def _show_video_pencil_view(self):
        display_mode = str(self.video_display_combo.currentData() or "pinned")
        if display_mode != "main_view":
            if self._video_camera_handoff_active:
                normal_camera = self._video_normal_camera
                if normal_camera and cmds.objExists(normal_camera):
                    switched = False
                    try:
                        switched = bool(_set_camera_for_model_panels(normal_camera))
                    except Exception:
                        switched = False
                    if switched:
                        self._video_camera_handoff_active = False
                        self._video_in_draw_over_mode = False
                        viewer = _reference_viewer()
                        if viewer.is_visible() and viewer.camera and cmds.objExists(viewer.camera):
                            self.controller.set_additional_visible_cameras([viewer.camera])
                            self._sync_reference_viewer_main_panel_scope(viewer.camera, force=True)
                        self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=normal_camera)
                        self.refresh_drawing_views()
                        self.refresh_layers()
                        self._drawing_options_changed()
                        self._sync_video_mode_button()
                        self._set_status("Normal viewport drawing is active. The Reference Viewer remains visible.")
                        return True
                self._set_status("The camera that was active before attaching this video is no longer available.")
                return False
            viewer = _reference_viewer()
            if viewer.is_visible():
                viewer.hide()
                self._video_viewer_visible = False
                self.controller.set_additional_visible_cameras([])
                self._restore_reference_viewer_main_panel_scope()
                self._persist_video_viewer_state(visible=False)
                self._sync_video_mode_button()
                self._set_status("Reference Viewer hidden. Perspective remains active.")
                return True
            return self._show_reference_viewer()
        camera = self._video_overlay_camera or self.video_reference_controller.camera_name
        if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
            self._set_status("Attach a video first so Aminate knows which Pencil View to show.")
            return False
        if self._video_in_draw_over_mode:
            normal_camera = self._video_normal_camera
            if normal_camera and cmds.objExists(normal_camera):
                switched = False
                try:
                    switched = bool(_set_camera_for_model_panels(normal_camera))
                except Exception:
                    switched = False
                if switched:
                    self._video_in_draw_over_mode = False
                    self._sync_video_mode_button()
                    self._set_status("Normal viewport drawing is active.")
                    return True
            self._set_status("The normal viewport camera is no longer available.")
            return False
        if not self._switch_visible_view_to_camera(camera):
            self._set_status("Could not switch the visible viewport to the Video Draw-Over Pencil View.")
            return False
        self._video_overlay_camera = camera
        self._video_in_draw_over_mode = True
        self.current_layer = self.controller.active_layer_for_camera(self.current_layer, camera=camera)
        self.refresh_drawing_views()
        self.refresh_layers()
        self._drawing_options_changed()
        self._sync_video_mode_button()
        self._set_status("Draw over video is active on the fixed Pencil View.")
        return True

    def _save_scene_for_package(self):
        if not MAYA_AVAILABLE:
            return False
        original_scene = cmds.file(query=True, sceneName=True) or ""
        original_modified = bool(cmds.file(query=True, modified=True))
        original_ext = os.path.splitext(original_scene)[1].lower()
        if original_ext not in (".ma", ".mb"):
            original_ext = ".ma"
        if original_scene:
            original_root, _unused_ext = os.path.splitext(original_scene)
            suggested_copy = original_root + "_annotated_package_copy" + original_ext
        else:
            suggested_copy = "annotated_scene_package_copy.ma"
        package_scene, _selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Annotated Copy For Packaging",
            suggested_copy,
            "Maya ASCII (*.ma);;Maya Binary (*.mb)",
        )
        if not package_scene:
            self._set_status("Packaging cancelled: choose a new copy path.")
            return False
        if not os.path.splitext(package_scene)[1]:
            package_scene += original_ext
        package_scene = os.path.abspath(package_scene)
        package_ext = os.path.splitext(package_scene)[1].lower()
        if package_ext not in (".ma", ".mb"):
            self._set_status("Packaging cancelled: the annotated copy must be .ma or .mb.")
            return False
        normalized_copy = os.path.normcase(os.path.realpath(package_scene))
        normalized_source = os.path.normcase(os.path.realpath(original_scene)) if original_scene else ""
        if normalized_source and normalized_copy == normalized_source:
            self._set_status("Packaging refused: choose a copy path, not the open source scene.")
            return False
        if os.path.exists(package_scene):
            self._set_status("Packaging refused: the annotated copy path already exists.")
            return False
        parent_dir = os.path.dirname(package_scene) or os.getcwd()
        if not os.path.isdir(parent_dir):
            self._set_status("Packaging cancelled: the copy folder does not exist.")
            return False

        file_type = "mayaBinary" if package_ext == ".mb" else "mayaAscii"
        self._pending_package_scene_state = None
        try:
            cmds.file(rename=package_scene)
            cmds.file(save=True, type=file_type, force=False)
            if not os.path.isfile(package_scene) or os.path.getsize(package_scene) <= 0:
                raise RuntimeError("Maya did not write the annotated scene copy.")
            self._pending_package_scene_state = {
                "package_scene": package_scene,
                "original_scene": original_scene,
                "original_modified": original_modified,
                "restore_required": bool(original_scene),
            }
            return True
        except Exception as exc:
            if original_scene:
                try:
                    cmds.file(rename=original_scene)
                    cmds.file(modified=original_modified)
                except Exception:
                    pass
            self._set_status("Could not save a safe annotated copy: {0}".format(exc))
            return False

    def _restore_scene_after_package(self):
        state = self._pending_package_scene_state or {}
        self._pending_package_scene_state = None
        if not state.get("restore_required"):
            return True
        original_scene = state.get("original_scene") or ""
        if not original_scene:
            return True
        try:
            cmds.file(rename=original_scene)
            cmds.file(modified=bool(state.get("original_modified")))
            return True
        except Exception as exc:
            self._set_status("Package was made, but Maya could not restore the original scene name: {0}".format(exc))
            return False

    def _package_annotated_scene(self):
        if not self._save_scene_for_package():
            return False
        result = {}
        error = ""
        try:
            result = self.reference_package_controller.package_current_scene(
                include_references=True,
                include_external=True,
                save_scene=False,
                retarget_package_scene=True,
            )
        except Exception as exc:
            error = "Could not package annotated scene: {0}".format(exc)
        restored = self._restore_scene_after_package()
        if error:
            self._set_status(error)
            return False
        if not restored:
            return False
        zip_path = result.get("zip_path") or ""
        self._set_status("Annotated scene ZIP ready: {0}".format(zip_path))
        if zip_path and os.path.exists(zip_path):
            try:
                os.startfile(os.path.dirname(zip_path))
            except Exception:
                pass
        return True

    def _set_status(self, message):
        self.status_label.setText(message)

    def _prepare_viewport_navigation(self, viewport_widget):
        if not MAYA_AVAILABLE:
            return False
        panel_name = _model_panel_for_viewport_widget(viewport_widget) if _qt_object_valid(viewport_widget) else ""
        if not panel_name:
            panel_name = _active_model_panel()
        if not panel_name or panel_name == REFERENCE_VIEWER_PANEL_NAME:
            return False
        current_camera = _panel_camera_transform(panel_name)
        if not _is_drawing_view_camera(current_camera):
            return False
        perspective_camera = "persp" if cmds.objExists("persp") else ""
        if not perspective_camera:
            return False
        drawing_was_enabled = bool(self._drawing_enabled)
        if drawing_was_enabled:
            self._set_drawing_enabled(False, restore_tool=True, update_status=False)
        switched = _set_camera_for_viewport_widget(viewport_widget, perspective_camera)
        if not switched:
            # The panel itself remains valid even when its Qt viewport wrapper
            # was deleted during a Maya layout/camera rebuild.  Switch through
            # the named modelPanel as the final, deterministic fallback.
            try:
                cmds.modelPanel(panel_name, edit=True, camera=perspective_camera)
                switched = (
                    _panel_camera_transform(panel_name) == perspective_camera
                    or _short_name(_panel_camera_transform(panel_name)) == _short_name(perspective_camera)
                )
            except Exception:
                switched = False
        if switched:
            self.refresh_drawing_views()
            self.refresh_layers()
            self._set_status("Pencil View kept fixed; drawing paused and viewport navigation is now in perspective.")
        elif drawing_was_enabled:
            self._set_drawing_enabled(True, restore_tool=False, update_status=False)
        return switched

    def _after_action(self, _result=None):
        self.refresh_layers()

    def _current_color(self):
        return tuple(self._selected_color)

    def _current_opacity(self):
        return max(0.05, min(1.0, float(self.opacity_spin.value()) / 100.0))

    def _current_eraser_mode(self):
        return str(self.eraser_mode_combo.currentData() or "partial")

    def _preserve_active_viewport_input(self):
        """Keep drawing or marquee input armed after a settings edit."""
        if not MAYA_AVAILABLE:
            return False
        mode = str(getattr(self, "_viewport_input_mode", "") or "")
        if mode == "marquee":
            global GLOBAL_DRAG_CONTEXT_CONTROLLER
            GLOBAL_DRAG_CONTEXT_CONTROLLER = self.controller
            try:
                if not cmds.draggerContext(MARQUEE_CONTEXT_NAME, exists=True):
                    return bool(self.controller.activate_marquee_select_context(layer_node=self.current_layer, add=False))
                if cmds.currentCtx() != MARQUEE_CONTEXT_NAME:
                    cmds.setToolTo(MARQUEE_CONTEXT_NAME)
                return True
            except Exception:
                return False
        if mode == "draw" or self._drawing_enabled:
            self._drawing_enabled = True
            return bool(self._activate_drag_draw(force=True))
        return False

    def _ensure_drawing_view_for_current_action(self):
        if not MAYA_AVAILABLE:
            return ""
        previous_layer = self.current_layer
        display_mode = str(getattr(self, "_video_display_mode", "pinned") or "pinned")
        viewer_camera = getattr(self, "_video_overlay_camera", "")
        if display_mode != "main_view" and viewer_camera and cmds.objExists(viewer_camera):
            self.current_layer = self.controller.active_layer_for_camera(previous_layer, camera=viewer_camera)
            if self.current_layer != previous_layer:
                self.refresh_layers()
            return self.current_layer
        drawing_view = self.controller.ensure_drawing_view_for_drawing(previous_layer)
        self.current_layer = drawing_view.get("layer") or previous_layer
        if drawing_view.get("created") or self.current_layer != previous_layer:
            self.refresh_drawing_views()
            self.refresh_layers()
        return self.current_layer

    def _drawing_options_changed(self, _value=None):
        self._preserve_active_viewport_input()

    def _sync_drag_draw_options(self):
        if not MAYA_AVAILABLE:
            return False
        self._ensure_drawing_view_for_current_action()
        self.controller.update_drag_draw_options(
            tool=self.tool_combo.currentText(),
            layer_node=self.current_layer,
            color=self._current_color(),
            size=self.size_spin.value(),
            opacity=self._current_opacity(),
            text=self.text_field.text(),
            camera_note=self.camera_note_box.isChecked(),
            camera_snap=self.camera_snap_box.isChecked(),
            one_frame=self.single_frame_box.isChecked(),
            eraser_mode=self._current_eraser_mode(),
        )
        if self._runtime_input_active:
            self._apply_brush_cursor()
        return True

    def _set_start_button_state(self, active):
        active = bool(active)
        self.start_drawing_button.blockSignals(True)
        try:
            self.start_drawing_button.setChecked(active)
            self.start_drawing_button.setProperty("aminateDrawingActive", active)
            self.start_drawing_button.setText("Drawing Active" if active else "Start Drawing")
            self.start_drawing_button.setAccessibleName(
                "Animator Pencil drawing active. Click to stop drawing."
                if active else "Start or stop Animator Pencil drawing"
            )
            self.start_drawing_button.setToolTip(
                "Drawing is active in the Maya viewport. Click to stop."
                if active else "Start persistent drawing in the active Maya viewport. Click again to stop."
            )
            style = self.start_drawing_button.style()
            if _qt_object_valid(style):
                try:
                    style.unpolish(self.start_drawing_button)
                    style.polish(self.start_drawing_button)
                except (RuntimeError, AttributeError):
                    # Maya can tear down a QProxyStyle during a panel/window
                    # rebuild.  The dynamic property and checked state above
                    # are still authoritative; skip only the optional
                    # repolish instead of aborting a drawing activation.
                    pass
            self.start_drawing_button.update()
        finally:
            self.start_drawing_button.blockSignals(False)

    def _toggle_drawing(self, _checked=False):
        return self._set_drawing_enabled(not bool(self._drawing_enabled))

    def _set_drawing_enabled(self, enabled, restore_tool=True, update_status=True):
        enabled = bool(enabled)
        if enabled:
            if MAYA_AVAILABLE and not self._drawing_enabled:
                try:
                    current_context = cmds.currentCtx() or ""
                except Exception:
                    current_context = ""
                if current_context != DRAW_CONTEXT_NAME:
                    self._previous_tool_context = current_context
            self._drawing_enabled = True
            self._set_start_button_state(True)
            return self._activate_drag_draw(force=True)

        was_enabled = self._drawing_enabled
        self._drawing_enabled = False
        self._viewport_input_mode = ""
        self._set_start_button_state(False)
        self.controller._discard_drag_preview()
        self.controller._end_drag_preview_session()
        self._clear_brush_cursor()
        if MAYA_AVAILABLE and restore_tool:
            try:
                if cmds.currentCtx() == DRAW_CONTEXT_NAME:
                    target_context = self._previous_tool_context or "selectSuperContext"
                    try:
                        cmds.setToolTo(target_context)
                    except Exception:
                        cmds.setToolTo("selectSuperContext")
            except Exception:
                pass
        if was_enabled and update_status:
            self._set_status("Drawing stopped. Press Start Drawing or choose a pencil tool to resume.")
        return True

    def refresh_layers(self):
        layers = self.controller.layers() if MAYA_AVAILABLE else []
        self.layer_table.blockSignals(True)
        self.layer_table.setRowCount(len(layers))
        for row, layer in enumerate(layers):
            effective = layer.get("effective_visible", layer.get("visible", True))
            camera_filtered = layer.get("camera_filtered", False)
            effective_text = "Shown" if effective else ("Camera hidden" if camera_filtered else "Hidden")
            values = (
                layer.get("name"),
                "",
                effective_text,
                layer.get("camera"),
                layer.get("state"),
                "Yes" if layer.get("locked") else "No",
                str(layer.get("count", 0)),
            )
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value or "")
                item.setData(_qt_flag("ItemDataRole", "UserRole", QtCore.Qt.UserRole), layer.get("node"))
                if col == 1:
                    checkable = _qt_flag("ItemFlag", "ItemIsUserCheckable", QtCore.Qt.ItemIsUserCheckable)
                    item.setFlags((item.flags() | checkable) & ~_qt_flag("ItemFlag", "ItemIsEditable", QtCore.Qt.ItemIsEditable))
                    item.setCheckState(
                        _qt_flag("CheckState", "Checked", QtCore.Qt.Checked)
                        if layer.get("visible", True)
                        else _qt_flag("CheckState", "Unchecked", QtCore.Qt.Unchecked)
                    )
                    item.setToolTip("Saved user visibility intent. Current camera filtering never changes this checkbox.")
                elif col == 2:
                    item.setToolTip("Effective viewport state after Current camera layer only filtering.")
                if col != 0:
                    editable = _qt_flag("ItemFlag", "ItemIsEditable", QtCore.Qt.ItemIsEditable)
                    item.setFlags(item.flags() & ~editable)
                self.layer_table.setItem(row, col, item)
        self.layer_table.blockSignals(False)
        if layers:
            active = self.controller.active_layer()
            row = next((i for i, layer in enumerate(layers) if layer["node"] == active), 0)
            self.layer_table.selectRow(row)
            self.current_layer = layers[row]["node"]
            self.state_combo.blockSignals(True)
            self.state_combo.setCurrentText(layers[row].get("state", "Animation"))
            self.state_combo.blockSignals(False)
            self.layer_opacity_spin.blockSignals(True)
            self.layer_opacity_spin.setValue(float(layers[row].get("opacity", 1.0)) * 100.0)
            self.layer_opacity_spin.blockSignals(False)
            self.video_line_opacity_spin.blockSignals(True)
            self.video_line_opacity_spin.setValue(float(layers[row].get("opacity", 1.0)) * 100.0)
            self.video_line_opacity_spin.blockSignals(False)
        else:
            self.current_layer = ""
            self.layer_opacity_spin.blockSignals(True)
            self.layer_opacity_spin.setValue(100.0)
            self.layer_opacity_spin.blockSignals(False)
            self.video_line_opacity_spin.blockSignals(True)
            self.video_line_opacity_spin.setValue(100.0)
            self.video_line_opacity_spin.blockSignals(False)

    def _selected_layer_from_table(self):
        rows = self.layer_table.selectionModel().selectedRows() if self.layer_table.selectionModel() else []
        if not rows:
            return self.current_layer
        item = self.layer_table.item(rows[0].row(), 0)
        return item.data(_qt_flag("ItemDataRole", "UserRole", QtCore.Qt.UserRole)) if item else self.current_layer

    def _layer_selection_changed(self):
        layer = self._selected_layer_from_table()
        if layer:
            self.current_layer = layer
            self.controller.set_active_layer(layer)
            data = self.controller.layer_data(layer)
            self.state_combo.blockSignals(True)
            self.state_combo.setCurrentText(data.get("state", "Animation"))
            self.state_combo.blockSignals(False)
            self.layer_opacity_spin.blockSignals(True)
            self.layer_opacity_spin.setValue(float(data.get("opacity", 1.0)) * 100.0)
            self.layer_opacity_spin.blockSignals(False)
            self.video_line_opacity_spin.blockSignals(True)
            self.video_line_opacity_spin.setValue(float(data.get("opacity", 1.0)) * 100.0)
            self.video_line_opacity_spin.blockSignals(False)
            self._drawing_options_changed()

    def _add_layer(self):
        self.current_layer = self.controller.create_layer(self.layer_name.text() or "Pencil Layer")
        self.refresh_layers()
        self._drawing_options_changed()

    def _edit_selected_layer_name(self):
        rows = self.layer_table.selectionModel().selectedRows() if self.layer_table.selectionModel() else []
        if rows:
            self.layer_table.editItem(self.layer_table.item(rows[0].row(), 0))

    def _layer_item_changed(self, item):
        if not item:
            return
        layer = item.data(_qt_flag("ItemDataRole", "UserRole", QtCore.Qt.UserRole))
        if item.column() == 1:
            visible = item.checkState() == _qt_flag("CheckState", "Checked", QtCore.Qt.Checked)
            if not self.controller.set_layer_visibility(layer, visible):
                self.refresh_layers()
            else:
                self.refresh_layers()
            return
        if item.column() == 0 and not self.controller.rename_layer(layer, item.text()):
            self.refresh_layers()

    def _set_selected_layer_visibility(self, visible):
        layer = self._selected_layer_from_table()
        if layer and self.controller.set_layer_visibility(layer, visible):
            self.refresh_layers()

    def _layer_opacity_changed(self, value):
        layer = self._selected_layer_from_table()
        if layer and self.controller.set_layer_opacity(layer, float(value) / 100.0):
            self.refresh_layers()
            self._preserve_active_viewport_input()

    def _set_camera_scope(self, enabled):
        self.controller.set_camera_scope(enabled)
        self.refresh_layers()

    def _set_all_layers_visibility(self, visible):
        self.controller.set_all_layers_visibility(visible)
        self.refresh_layers()

    def _delete_layer(self):
        layer = self._selected_layer_from_table()
        if not layer:
            return
        result = QtWidgets.QMessageBox.question(self, "Delete Layer", "Delete this pencil layer and all marks inside it?")
        if result == QtWidgets.QMessageBox.Yes:
            self.controller.delete_layer(layer)
            self.refresh_layers()
            self._drawing_options_changed()

    def _set_layer_state(self, state):
        layer = self._selected_layer_from_table()
        if layer:
            self.controller.set_layer_state(layer, state)
            self.refresh_layers()

    def _move_layer(self, delta):
        layer = self._selected_layer_from_table()
        if layer:
            self.controller.move_layer_order(layer, delta)
            self.refresh_layers()

    def _move_layer_to_camera(self):
        layer = self._selected_layer_from_table()
        if layer:
            self.controller.move_layer_to_camera(layer)
            self.refresh_layers()

    def _create_mark(self):
        self._ensure_drawing_view_for_current_action()
        mark = self.controller.create_mark(
            tool=self.tool_combo.currentText(),
            layer_node=self.current_layer,
            color=self._current_color(),
            size=self.size_spin.value(),
            opacity=self._current_opacity(),
            text=self.text_field.text(),
            camera_note=self.camera_note_box.isChecked(),
            camera_snap=self.camera_snap_box.isChecked(),
            one_frame=self.single_frame_box.isChecked(),
        )
        self._after_action(mark)

    def _activate_drag_draw(self, force=False):
        if not MAYA_AVAILABLE or (not self._drawing_enabled and not force):
            return False
        self._ensure_drawing_view_for_current_action()
        activated = self.controller.activate_drag_draw_context(
            tool=self.tool_combo.currentText(),
            layer_node=self.current_layer,
            color=self._current_color(),
            size=self.size_spin.value(),
            opacity=self._current_opacity(),
            text=self.text_field.text(),
            camera_note=self.camera_note_box.isChecked(),
            camera_snap=self.camera_snap_box.isChecked(),
            one_frame=self.single_frame_box.isChecked(),
            eraser_mode=self._current_eraser_mode(),
        )
        self._drawing_enabled = bool(activated)
        self._viewport_input_mode = "draw" if self._drawing_enabled else ""
        self._set_start_button_state(self._drawing_enabled)
        if self._runtime_input_active:
            self._apply_brush_cursor()
        return bool(activated)

    def _refresh_camera_scope_and_drawing_layer(self):
        if self._runtime_input_active:
            self._viewport_navigation_filter.refresh()
        if getattr(self, "_video_overlay_camera", "") and MAYA_AVAILABLE:
            display_mode = str(getattr(self, "_video_display_mode", "pinned") or "pinned")
            if display_mode == "main_view":
                current_camera = _current_camera()
                in_video_view = bool(current_camera and _long_name(current_camera) == _long_name(self._video_overlay_camera))
                if in_video_view != bool(self._video_in_draw_over_mode):
                    self._video_in_draw_over_mode = in_video_view
                    self._sync_video_mode_button()
            else:
                viewer = _reference_viewer()
                self._sync_reference_viewer_freeform_state(viewer)
                viewer.sync_pinned_geometry()
                visible = viewer.is_visible()
                if visible != bool(self._video_viewer_visible):
                    self._video_viewer_visible = visible
                    self._persist_video_viewer_state(visible=visible)
                    self._sync_video_mode_button()
                current_camera = _current_camera()
                in_video_view = bool(
                    visible
                    and current_camera
                    and _long_name(current_camera) == _long_name(self._video_overlay_camera)
                )
                handoff_changed = in_video_view != bool(self._video_camera_handoff_active)
                if handoff_changed:
                    self._video_camera_handoff_active = in_video_view
                    self._sync_video_mode_button()
                # The main viewport may have changed cameras between timer
                # ticks. Reassert the retained viewer camera before the shared
                # scope refresh so its own modelPanel never loses draw-overs.
                self.controller.set_additional_visible_cameras(
                    [viewer.camera] if visible and viewer.camera and cmds.objExists(viewer.camera) else []
                )
                if visible and viewer.camera and cmds.objExists(viewer.camera):
                    self._sync_reference_viewer_main_panel_scope(viewer.camera, force=handoff_changed)
                else:
                    self._restore_reference_viewer_main_panel_scope()
        scope_changed = self.controller.refresh_camera_scope()
        if not scope_changed:
            return
        self.refresh_layers()
        self.refresh_drawing_views()
        if not self._drawing_enabled or not MAYA_AVAILABLE:
            return
        previous_layer = self.current_layer
        layer = self._ensure_drawing_view_for_current_action()
        self._sync_drag_draw_options()
        if layer != previous_layer:
            self._set_status("Drawing layer switched to the active camera. Saved Pencil View ready.")

    def _refresh_drawing_state(self):
        if not self._drawing_enabled or not MAYA_AVAILABLE or not self.isVisible():
            return
        try:
            context_active = cmds.currentCtx() == DRAW_CONTEXT_NAME
        except Exception:
            context_active = False
        if context_active:
            self._viewport_input_mode = "draw"
            return
        self._drawing_enabled = False
        self._viewport_input_mode = ""
        self._set_start_button_state(False)
        self._clear_brush_cursor()
        self._set_status("Drawing paused after another Maya tool was selected.")

    def _activate_marquee_select(self):
        self._set_drawing_enabled(False, restore_tool=False, update_status=False)
        activated = self.controller.activate_marquee_select_context(layer_node=self.current_layer, add=False)
        self._viewport_input_mode = "marquee" if activated else ""
        return bool(activated)

    def _show_layer_menu(self, position):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Set Active Layer", self._layer_selection_changed)
        menu.addAction("Add Layer", self._add_layer)
        menu.addAction("Rename Layer", self._edit_selected_layer_name)
        menu.addAction("Delete Layer", self._delete_layer)
        menu.addAction("Show Selected Layer", lambda: self._set_selected_layer_visibility(True))
        menu.addAction("Hide Selected Layer", lambda: self._set_selected_layer_visibility(False))
        menu.addAction("Show All Layers", lambda: self._set_all_layers_visibility(True))
        menu.addAction("Hide All Layers", lambda: self._set_all_layers_visibility(False))
        menu.addSeparator()
        menu.addAction("Layer Up", lambda: self._move_layer(-1))
        menu.addAction("Layer Down", lambda: self._move_layer(1))
        menu.addAction("Move Layer To Current Camera", self._move_layer_to_camera)
        menu.exec_(self.layer_table.mapToGlobal(position))


def ensure_video_opacity_controls(panel):
    """Idempotently add the Video Draw-Over percentage controls to an existing panel.

    This compatibility bridge is safe for a retained Maya session whose panel was
    created by an older Aminate module: it adds child widgets only and never
    reloads or tears down the panel.
    """
    if not QtWidgets or panel is None:
        return False
    group = getattr(panel, "video_draw_over_group", None)
    if group is None or group.layout() is None:
        return False
    layout = group.layout()
    video_spin = getattr(panel, "video_opacity_spin", None) or group.findChild(
        QtWidgets.QDoubleSpinBox, "animatorsPencilVideoOpacityPercentSpin"
    )
    line_spin = getattr(panel, "video_line_opacity_spin", None) or group.findChild(
        QtWidgets.QDoubleSpinBox, "animatorsPencilVideoLineOpacityPercentSpin"
    )
    reused_controls = video_spin is not None and line_spin is not None
    row = int(layout.rowCount())
    if video_spin is None:
        video_spin = QtWidgets.QDoubleSpinBox(group)
        video_spin.setObjectName("animatorsPencilVideoOpacityPercentSpin")
        video_spin.setAccessibleName("Video draw-over opacity percentage")
        video_spin.setRange(0.0, 100.0)
        video_spin.setSingleStep(5.0)
        video_spin.setDecimals(0)
        video_spin.setPrefix("Video Opacity ")
        video_spin.setSuffix("%")
        video_spin.setValue(80.0)
        video_spin.setToolTip("Opacity of the attached video image plane. Changes apply immediately and persist in the scene.")
        layout.addWidget(video_spin, row, 0)
    if line_spin is None:
        line_spin = QtWidgets.QDoubleSpinBox(group)
        line_spin.setObjectName("animatorsPencilVideoLineOpacityPercentSpin")
        line_spin.setAccessibleName("Pencil line opacity percentage")
        line_spin.setRange(0.0, 100.0)
        line_spin.setSingleStep(5.0)
        line_spin.setDecimals(0)
        line_spin.setPrefix("Lines Opacity ")
        line_spin.setSuffix("%")
        line_spin.setValue(100.0)
        line_spin.setToolTip("Opacity of marks on the active Pencil layer. Existing and future marks update immediately.")
        layout.addWidget(line_spin, row, 1)
    panel.video_opacity_spin = video_spin
    panel.video_line_opacity_spin = line_spin

    def _fallback_video_opacity(value):
        controller = getattr(panel, "video_reference_controller", None)
        transform = getattr(panel, "_video_overlay_transform", "")
        if not transform and controller is not None:
            transform = getattr(controller, "last_transform", "")
        if not transform and controller is not None and hasattr(controller, "discover_camera_overlay"):
            try:
                info = controller.discover_camera_overlay() or {}
                transform = info.get("transform", "")
                if transform:
                    panel._video_overlay_transform = transform
            except Exception:
                pass
        normalized = max(0.0, min(1.0, float(value) / 100.0))
        if controller is not None:
            controller.opacity = normalized
            setter = getattr(controller, "set_video_opacity", None)
            if setter is not None:
                setter(normalized, transform)
                return
        if not MAYA_AVAILABLE or not transform or not cmds.objExists(transform):
            return
        shapes = cmds.listRelatives(transform, shapes=True, fullPath=True, type="imagePlane") or []
        if not shapes:
            return
        shape = shapes[0]
        if cmds.objExists(shape + ".alphaGain"):
            cmds.setAttr(shape + ".alphaGain", normalized)
        if not cmds.attributeQuery("amirVideoOpacity", node=transform, exists=True):
            cmds.addAttr(transform, longName="amirVideoOpacity", attributeType="double")
        cmds.setAttr(transform + ".amirVideoOpacity", normalized)

    def _fallback_line_opacity(value):
        layer = panel._selected_layer_from_table() if hasattr(panel, "_selected_layer_from_table") else getattr(panel, "current_layer", "")
        controller = getattr(panel, "controller", None)
        if layer and controller is not None and hasattr(controller, "set_layer_opacity"):
            controller.set_layer_opacity(layer, float(value) / 100.0)
            if hasattr(panel, "refresh_layers"):
                panel.refresh_layers()

    video_handler = getattr(panel, "_video_opacity_changed", None) or _fallback_video_opacity
    line_handler = getattr(panel, "_video_line_opacity_changed", None) or _fallback_line_opacity
    if not reused_controls:
        video_spin.valueChanged.connect(video_handler)
        line_spin.valueChanged.connect(line_handler)
        panel._aminate_video_opacity_value_bridge = True
        panel._aminate_video_line_opacity_value_bridge = True
    # Older retained panels attach the video first and have no new scene-tag
    # logic. Queue one idempotent reapply after their Attach Video slot returns,
    # so the current percentage also writes the persistent transform attribute.
    attach_button = getattr(panel, "attach_video_button", None)
    if attach_button is not None and not getattr(panel, "_aminate_video_opacity_attach_bridge", False):
        panel._aminate_video_opacity_attach_bridge = True

        def _reapply_after_attach(_checked=False):
            def _apply_current_value():
                try:
                    _fallback_video_opacity(video_spin.value())
                except Exception:
                    pass

            QtCore.QTimer.singleShot(0, _apply_current_value)

        attach_button.clicked.connect(_reapply_after_attach)
    try:
        controller = getattr(panel, "video_reference_controller", None)
        info = controller.discover_camera_overlay() if controller is not None else None
        if info:
            transform = getattr(panel, "_video_overlay_transform", "") or info.get("transform", "")
            if transform:
                panel._video_overlay_transform = transform
            persisted_opacity = None
            if MAYA_AVAILABLE and transform and cmds.objExists(transform):
                try:
                    if cmds.attributeQuery("amirVideoOpacity", node=transform, exists=True):
                        persisted_opacity = float(cmds.getAttr(transform + ".amirVideoOpacity"))
                except Exception:
                    persisted_opacity = None
                if persisted_opacity is None:
                    try:
                        shapes = cmds.listRelatives(transform, shapes=True, fullPath=True, type="imagePlane") or []
                        if shapes and cmds.objExists(shapes[0] + ".alphaGain"):
                            persisted_opacity = float(cmds.getAttr(shapes[0] + ".alphaGain"))
                    except Exception:
                        persisted_opacity = None
            opacity_value = persisted_opacity if persisted_opacity is not None else info.get("opacity", 0.8)
            video_spin.blockSignals(True)
            video_spin.setValue(max(0.0, min(100.0, float(opacity_value) * 100.0)))
            video_spin.blockSignals(False)
    except Exception:
        pass
    return True


class AnimatorsPencilWindow(QtWidgets.QDialog):
    def __init__(self, controller=None, parent=None):
        super(AnimatorsPencilWindow, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Animators Pencil")
        self.controller = controller or AnimatorsPencilController()
        layout = QtWidgets.QVBoxLayout(self)
        self.panel = AnimatorsPencilPanel(controller=self.controller, parent=self)
        layout.addWidget(self.panel)
        self.resize(760, 760)

    def closeEvent(self, event):
        self.hide()
        event.ignore()


GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


def launch_animators_pencil():
    global GLOBAL_CONTROLLER, GLOBAL_WINDOW
    if GLOBAL_WINDOW:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
    GLOBAL_CONTROLLER = AnimatorsPencilController()
    GLOBAL_WINDOW = AnimatorsPencilWindow(GLOBAL_CONTROLLER)
    GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


def run_smoke_scene():
    if not MAYA_AVAILABLE:
        return {"available": False}
    for layer_info in AnimatorsPencilController().layers():
        if layer_info.get("name") in ("Smoke Layer", "Smoke Eraser Scope", "Smoke Locked", "Smoke Rename", "Renamed Smoke Layer", "Smoke Camera Layer", "Smoke Marquee Whole", "Smoke Marquee Partial", "Smoke Legacy Stamp Angle", "Smoke Direct Legacy Stamp Angle") and cmds.objExists(layer_info.get("node")):
            cmds.delete(layer_info.get("node"))
    if cmds.objExists("amirAnimatorsPencilGhosts_GRP"):
        cmds.delete("amirAnimatorsPencilGhosts_GRP")
    smoke_camera = "amirPencilSmokeView_CAM"
    if cmds.objExists(smoke_camera):
        cmds.delete(smoke_camera)
    if cmds.objExists("amirPencilSmokeSecondView_CAM"):
        cmds.delete("amirPencilSmokeSecondView_CAM")
    smoke_camera, _smoke_shape = cmds.camera(name=smoke_camera)
    cmds.xform(smoke_camera, worldSpace=True, translation=(3.0, 4.0, 12.0), rotation=(-5.0, 20.0, 0.0))
    _set_camera_for_model_panels(smoke_camera)
    controller = AnimatorsPencilController()
    layer = controller.create_layer("Smoke Layer", camera=smoke_camera, state="Animation")
    layer_parent = (cmds.listRelatives(layer, parent=True, fullPath=True) or [""])[0]
    camera_space_anchor_ok = bool(
        layer_parent
        and layer_parent != _long_name(smoke_camera)
        and _get_string_attr(layer_parent, CAMERA_SPACE_ANCHOR_ATTR, "") == "camera_space_anchor"
        and bool(cmds.getAttr(layer_parent + ".visibility"))
    )
    cmds.currentTime(10)
    line = controller.create_mark("Line", layer, DEFAULT_COLORS["Blue"], 4.0, 0.9, camera_note=True, camera_snap=True)
    cmds.currentTime(12)
    cmds.xform(smoke_camera, worldSpace=True, translation=(4.0, 5.0, 13.0), rotation=(-8.0, 25.0, 0.0))
    rect = controller.create_mark("Rectangle", layer, DEFAULT_COLORS["Yellow"], 3.0, 1.0, camera_note=True, camera_snap=True)
    dragged_rect = controller.create_mark_from_drag(
        "Rectangle",
        layer,
        DEFAULT_COLORS["Green"],
        3.0,
        1.0,
        start_point=(-1.2, 0.8, 0.0),
        end_point=(-0.2, -0.15, 0.0),
    )
    dragged_ellipse = controller.create_mark_from_drag(
        "Ellipse",
        layer,
        DEFAULT_COLORS["Blue"],
        3.0,
        0.8,
        start_point=(0.25, 0.65, 0.0),
        end_point=(1.1, -0.25, 0.0),
    )
    freehand = controller.create_freehand_mark(
        "Pencil",
        layer,
        DEFAULT_COLORS["Red"],
        2.0,
        1.0,
        points=[(-1.1, -0.55, 0.0), (-0.75, -0.25, 0.0), (-0.35, -0.5, 0.0), (0.15, -0.2, 0.0), (0.55, -0.45, 0.0)],
    )
    expected_freehand_points = [(-1.1, -0.55, 0.0), (-0.75, -0.25, 0.0), (-0.35, -0.5, 0.0), (0.15, -0.2, 0.0), (0.55, -0.45, 0.0)]
    freehand_shapes = cmds.listRelatives(freehand, shapes=True, noIntermediate=True, fullPath=True) or []
    freehand_local_points = [
        cmds.pointPosition(cv, local=True)
        for shape in freehand_shapes
        for cv in (cmds.ls(shape + ".cv[*]", flatten=True) or [])
    ]
    freehand_local_points_match = bool(
        len(freehand_local_points) == len(expected_freehand_points)
        and all(
            all(abs(float(actual[index]) - float(expected[index])) <= 1.0e-6 for index in range(3))
            for actual, expected in zip(freehand_local_points, expected_freehand_points)
        )
    )
    erase_target = controller.create_freehand_mark(
        "Brush",
        layer,
        DEFAULT_COLORS["Black"],
        2.0,
        1.0,
        points=[(1.2, 1.0, 0.0), (1.4, 1.0, 0.0), (1.6, 1.0, 0.0), (1.8, 1.0, 0.0), (2.0, 1.0, 0.0)],
    )
    scope_layer = controller.create_layer("Smoke Eraser Scope", camera=smoke_camera, state="Animation")
    scope_mark = controller.create_freehand_mark(
        "Brush",
        scope_layer,
        DEFAULT_COLORS["Blue"],
        2.0,
        1.0,
        points=[(1.2, 1.0, 0.0), (1.4, 1.0, 0.0), (1.6, 1.0, 0.0), (1.8, 1.0, 0.0), (2.0, 1.0, 0.0)],
    )
    controller.set_active_layer(layer)
    erased_count = controller.erase_marks_with_stroke(layer, [(1.6, 1.0, 0.0)], radius=0.08)
    erase_target_removed = bool(erase_target and not cmds.objExists(erase_target))
    partial_fragments = [
        mark for mark in controller.marks(layer)
        if (_get_json_attr(mark, "animatorsPencilMarkData", {}) or {}).get("partialErased")
    ]
    partial_fragment_points = [
        point
        for mark in partial_fragments
        for point in ((_get_json_attr(mark, "animatorsPencilMarkData", {}) or {}).get("points") or [])
    ]
    eraser_partial_gap = bool(
        len(partial_fragments) >= 2
        and partial_fragment_points
        and all(math.sqrt(((float(point[0]) - 1.6) ** 2.0) + ((float(point[1]) - 1.0) ** 2.0)) > 0.075 for point in partial_fragment_points)
    )
    eraser_kept_other_layer = bool(scope_mark and cmds.objExists(scope_mark))
    eraser_original_frame = float(cmds.currentTime(query=True))
    multi_frame_eraser_layer = controller.create_layer("Smoke Multi Frame Eraser", camera=smoke_camera, state="Animation")
    multi_frame_eraser_marks = []
    for frame, y in ((1, -0.4), (2, 0.0), (3, 0.4)):
        cmds.currentTime(frame)
        multi_frame_eraser_marks.append(
            controller.create_freehand_mark(
                "Pencil",
                multi_frame_eraser_layer,
                DEFAULT_COLORS["Green"],
                2.0,
                1.0,
                points=[(-0.8, y, 0.0), (0.8, y, 0.0)],
                one_frame=True,
            )
        )
    cmds.currentTime(3)
    controller.update_drag_draw_options(
        tool="Eraser",
        layer_node=multi_frame_eraser_layer,
        color=DEFAULT_COLORS["Red"],
        size=3.0,
        opacity=1.0,
        eraser_mode="partial",
    )
    multi_frame_preview_ok = bool(
        controller._update_eraser_preview(
            [(0.0, -0.6, 0.0), (0.0, 0.6, 0.0)],
            force=True,
        )
        and len(controller._eraser_preview_marks) == len(multi_frame_eraser_marks)
    )
    controller._discard_eraser_preview()
    multi_frame_affected = controller.erase_marks_with_stroke(
        multi_frame_eraser_layer,
        [(0.0, -0.6, 0.0), (0.0, 0.6, 0.0)],
        radius=0.08,
        whole_stroke=False,
    )
    multi_frame_fragments = [
        mark for mark in controller.marks(multi_frame_eraser_layer)
        if (_get_json_attr(mark, "animatorsPencilMarkData", {}) or {}).get("partialErased")
    ]
    multi_frame_eraser_all_marks = bool(
        multi_frame_affected == len(multi_frame_eraser_marks)
        and len(multi_frame_fragments) == len(multi_frame_eraser_marks) * 2
    )
    controller.delete_layer(multi_frame_eraser_layer)
    cmds.currentTime(eraser_original_frame)
    controller.delete_layer(scope_layer)
    whole_target = controller.create_freehand_mark(
        "Brush",
        layer,
        DEFAULT_COLORS["Yellow"],
        2.0,
        1.0,
        points=[(-2.0, 1.2, 0.0), (-1.7, 1.2, 0.0), (-1.4, 1.2, 0.0)],
    )
    whole_erased_count = controller.erase_marks_with_stroke(layer, [(-1.7, 1.2, 0.0)], radius=0.08, whole_stroke=True)
    whole_erase_removed = bool(whole_target and not cmds.objExists(whole_target))
    locked_layer = controller.create_layer("Smoke Locked", camera=smoke_camera, state="Animation")
    locked_mark = controller.create_freehand_mark(
        "Brush",
        locked_layer,
        DEFAULT_COLORS["Red"],
        2.0,
        1.0,
        points=[(-2.0, -1.2, 0.0), (-1.7, -1.2, 0.0), (-1.4, -1.2, 0.0)],
    )
    controller.set_layer_state(locked_layer, "Locked")
    locked_erase_count = controller.erase_marks_with_stroke(locked_layer, [(-1.7, -1.2, 0.0)], radius=0.08, whole_stroke=True)
    locked_erase_guarded = bool(locked_erase_count == 0 and locked_mark and cmds.objExists(locked_mark))
    controller.delete_layer(locked_layer)
    rename_layer = controller.create_layer("Smoke Rename", camera=smoke_camera, state="Animation")
    rename_layer_ok = controller.rename_layer(rename_layer, "Renamed Smoke Layer")
    renamed_layer_name = controller.layer_data(rename_layer).get("name")
    controller.delete_layer(rename_layer)
    controller.set_active_layer(layer)
    cmds.select(dragged_rect, replace=True)
    preset_saved, _preset_save_message = controller.save_shape_preset("Smoke User Shape")
    custom_shape_present = "Smoke User Shape" in controller.shape_library()
    custom_preset_shape = controller.create_shape_preset("Smoke User Shape", layer, DEFAULT_COLORS["Yellow"], 2.0, 0.8)
    preset_deleted, _preset_delete_message = controller.delete_shape_preset("Smoke User Shape")
    camera_matrix = cmds.xform(smoke_camera, query=True, matrix=True, worldSpace=True)
    def _rotation_basis(matrix):
        basis = []
        for axis in ((0, 1, 2), (4, 5, 6), (8, 9, 10)):
            length = math.sqrt(sum(float(matrix[index]) ** 2.0 for index in axis)) or 1.0
            basis.extend(float(matrix[index]) / length for index in axis)
        return basis

    camera_basis = _rotation_basis(camera_matrix)
    # Recreate the old absolute-parent bug, then let the normal layer scan
    # migrate it.  The marker must make that migration one-shot so later user
    # transforms are not silently reset on every refresh.
    smoke_anchor = controller._camera_space_anchor(smoke_camera)
    legacy_layer = cmds.createNode("transform", name="amirPencilSmokeLegacyStampAngle_LYR")
    legacy_layer = cmds.parent(legacy_layer, smoke_anchor)[0]
    legacy_layer = _long_name(legacy_layer)
    legacy_translate_z = -10.75
    cmds.setAttr(legacy_layer + ".translate", 0.0, 0.0, legacy_translate_z, type="double3")
    _set_string_attr(legacy_layer, LAYER_MARKER_ATTR, "layer")
    _set_string_attr(legacy_layer, "animatorsPencilCamera", _long_name(smoke_camera))
    _set_string_attr(legacy_layer, "animatorsPencilLayerState", "Animation")
    _set_json_attr(legacy_layer, "animatorsPencilLayerData", {"version": 1, "name": "Smoke Legacy Stamp Angle", "camera": _long_name(smoke_camera), "state": "Animation", "order": 99, "locked": False, "opacity": 1.0})
    legacy_parent = (cmds.listRelatives(legacy_layer, parent=True, fullPath=True) or [""])[0]
    legacy_locked_channels = ("rotateX", "rotateY", "rotateZ", "scaleX", "scaleY", "scaleZ")
    for attr_name in legacy_locked_channels:
        cmds.setAttr(legacy_layer + "." + attr_name, lock=True)

    # Older scenes can also have layers parented directly below a hidden
    # camera.  That route must move to the visible anchor without losing the
    # camera-space depth, layer order, or child drawing geometry.
    direct_legacy_layer = cmds.createNode("transform", name="amirPencilSmokeDirectLegacyStampAngle_LYR")
    direct_legacy_layer = cmds.parent(direct_legacy_layer, smoke_camera)[0]
    direct_legacy_layer = _long_name(direct_legacy_layer)
    direct_legacy_translate_z = -11.25
    cmds.setAttr(direct_legacy_layer + ".translate", 0.0, 0.0, direct_legacy_translate_z, type="double3")
    _set_string_attr(direct_legacy_layer, LAYER_MARKER_ATTR, "layer")
    _set_string_attr(direct_legacy_layer, "animatorsPencilCamera", _long_name(smoke_camera))
    _set_string_attr(direct_legacy_layer, "animatorsPencilLayerState", "Animation")
    _set_json_attr(direct_legacy_layer, "animatorsPencilLayerData", {"version": 1, "name": "Smoke Direct Legacy Stamp Angle", "camera": _long_name(smoke_camera), "state": "Animation", "order": 98, "locked": False, "opacity": 1.0})
    direct_legacy_child = _curve_node(
        "amirPencilSmokeDirectLegacyChild_MARK",
        [(-0.5, 0.0, 0.0), (0.5, 0.0, 0.0)],
        direct_legacy_layer,
        DEFAULT_COLORS["Red"],
        1.0,
        2.0,
    )
    direct_legacy_layer_name = _short_name(direct_legacy_layer)
    direct_legacy_child_name = _short_name(direct_legacy_child)
    controller.layers(include_count=False)
    direct_legacy_layer = _long_name(direct_legacy_layer_name)
    direct_legacy_child = _long_name(direct_legacy_child_name)
    legacy_post_migration_world = cmds.xform(legacy_layer, query=True, matrix=True, worldSpace=True)
    legacy_local_rotate = cmds.getAttr(legacy_layer + ".rotate")[0]
    legacy_local_scale = cmds.getAttr(legacy_layer + ".scale")[0]
    legacy_locks_restored = all(bool(cmds.getAttr(legacy_layer + "." + attr_name, lock=True)) for attr_name in legacy_locked_channels)
    legacy_migration_ok = bool(
        legacy_parent
        and abs(float(legacy_translate_z) - float(cmds.getAttr(legacy_layer + ".translateZ"))) <= 1.0e-6
        and all(abs(float(value)) <= 1.0e-6 for value in legacy_local_rotate)
        and all(abs(float(value) - 1.0) <= 1.0e-6 for value in legacy_local_scale)
        and legacy_locks_restored
        and all(abs(float(value) - float(expected)) <= 1.0e-5 for value, expected in zip(_rotation_basis(legacy_post_migration_world), camera_basis))
    )
    direct_legacy_parent = (cmds.listRelatives(direct_legacy_layer, parent=True, fullPath=True) or [""])[0]
    direct_legacy_world = cmds.xform(direct_legacy_layer, query=True, matrix=True, worldSpace=True)
    legacy_direct_camera_migration_ok = bool(
        direct_legacy_parent == _long_name(smoke_anchor)
        and abs(float(direct_legacy_translate_z) - float(cmds.getAttr(direct_legacy_layer + ".translateZ"))) <= 1.0e-6
        and int((_get_json_attr(direct_legacy_layer, "animatorsPencilLayerData", {}) or {}).get("order", -1)) == 98
        and direct_legacy_child
        and cmds.objExists(direct_legacy_child)
        and all(abs(float(value) - float(expected)) <= 1.0e-5 for value, expected in zip(_rotation_basis(direct_legacy_world), camera_basis))
    )
    for attr_name in legacy_locked_channels:
        cmds.setAttr(legacy_layer + "." + attr_name, lock=False)
    cmds.setAttr(legacy_layer + ".rotate", 3.0, 4.0, 5.0, type="double3")
    cmds.setAttr(legacy_layer + ".scale", 1.1, 1.0, 0.9, type="double3")
    controller.layers(include_count=False)
    legacy_migration_idempotent = bool(
        all(abs(float(value) - expected) <= 1.0e-6 for value, expected in zip(cmds.getAttr(legacy_layer + ".rotate")[0], (3.0, 4.0, 5.0)))
        and all(abs(float(value) - expected) <= 1.0e-6 for value, expected in zip(cmds.getAttr(legacy_layer + ".scale")[0], (1.1, 1.0, 0.9)))
    )
    # Stamp Current Tool and Shape Library bypass the drag projection path,
    # so exercise every scene-native stamp route and verify that each mark's
    # world rotation follows the active camera instead of the world grid.
    stamp_marks = {
        tool: controller.create_mark(tool, layer, DEFAULT_COLORS["White"], 2.0, 1.0, text="Stamp Smoke")
        for tool in ("Pencil", "Brush", "Line", "Arrow", "Rectangle", "Ellipse", "Text")
    }
    stamp_marks["Preset"] = controller.create_shape_preset("Star", layer, DEFAULT_COLORS["Yellow"], 2.0, 1.0)
    stamp_marks["UserPreset"] = custom_preset_shape
    stamp_angle_ok = bool(
        all(
            mark
            and cmds.objExists(mark)
            and len(cmds.xform(mark, query=True, matrix=True, worldSpace=True)) >= 11
            and all(
                abs(float(value) - float(expected)) <= 1.0e-5
                for value, expected in zip(_rotation_basis(cmds.xform(mark, query=True, matrix=True, worldSpace=True)), camera_basis)
            )
            for mark in stamp_marks.values()
        )
    )
    marquee_whole_layer = controller.create_layer("Smoke Marquee Whole", camera=smoke_camera, state="Animation")
    marquee_whole_mark = controller.create_freehand_mark(
        "Pencil",
        marquee_whole_layer,
        DEFAULT_COLORS["Green"],
        2.0,
        1.0,
        points=[(-1.0, -0.5, 0.0), (-0.25, 0.9, 0.0), (0.75, -0.35, 0.0)],
    )
    marquee_selected = controller.select_marks_in_box(marquee_whole_layer, (-1.25, -0.75, 0.0), (1.0, 1.0, 0.0))
    marquee_transform_box = controller._show_marquee_transform_box(marquee_whole_layer, marquee_selected)
    marquee_transform_box_active = bool(
        marquee_transform_box
        and cmds.objExists(marquee_transform_box)
        and _get_string_attr(marquee_transform_box, MARQUEE_TRANSFORM_BOX_ATTR, "") == "active"
        and controller.selected_marks()
    )
    marquee_transform_box_committed = bool(controller._commit_marquee_transform_box())
    controller.delete_layer(marquee_whole_layer)
    # Regression coverage for a moved mark: its metadata stays local while
    # the visible curve has an object-space translation. A layer-space box
    # must still split and move only the enclosed section.
    marquee_partial_layer = controller.create_layer("Smoke Marquee Partial", camera=smoke_camera, state="Animation")
    marquee_partial_source = controller.create_freehand_mark(
        "Pencil",
        marquee_partial_layer,
        DEFAULT_COLORS["Red"],
        2.0,
        1.0,
        points=[(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
    )
    cmds.xform(marquee_partial_source, objectSpace=True, translation=(3.0, 0.0, 0.0))
    marquee_partial_picked = controller.select_marks_in_box(
        marquee_partial_layer,
        (2.5, -0.5, 0.0),
        (3.5, 0.5, 0.0),
    )
    marquee_partial_fragments = [
        mark for mark in controller.marks(marquee_partial_layer)
        if (_get_json_attr(mark, "animatorsPencilMarkData", {}) or {}).get("partialMarquee")
    ]
    marquee_partial_inside = [
        mark for mark in marquee_partial_picked
        if mark and cmds.objExists(mark)
    ]
    marquee_partial_local_points = [
        point
        for mark in marquee_partial_inside
        for point in ((_get_json_attr(mark, "animatorsPencilMarkData", {}) or {}).get("points") or [])
    ]
    marquee_partial_split_ok = bool(
        marquee_partial_source
        and not cmds.objExists(marquee_partial_source)
        and len(marquee_partial_fragments) >= 3
        and marquee_partial_inside
        and marquee_partial_local_points
        and min(float(point[0]) for point in marquee_partial_local_points) >= -0.500001
        and max(float(point[0]) for point in marquee_partial_local_points) <= 0.500001
    )
    marquee_partial_box = controller._show_marquee_transform_box(marquee_partial_layer, marquee_partial_picked)
    # Parenting into the helper box changes full DAG paths. Refresh the
    # selected fragment paths before measuring the move and final cleanup.
    marquee_partial_inside = controller.selected_marks()
    marquee_partial_inside_names = set(_short_name(mark) for mark in marquee_partial_inside)
    marquee_partial_before = [
        tuple(cmds.xform(mark, query=True, worldSpace=True, translation=True))
        for mark in marquee_partial_inside
        if cmds.objExists(mark)
    ]
    if marquee_partial_box and cmds.objExists(marquee_partial_box):
        cmds.move(0.5, 0.0, 0.0, marquee_partial_box, relative=True, objectSpace=True)
    cmds.select(clear=True)
    # Batch mayapy has no live scriptJob event loop; the same callback is
    # invoked explicitly here while GUI Maya receives it from SelectionChanged.
    controller._marquee_selection_changed()
    marquee_partial_after_marks = [
        mark for mark in controller.marks(marquee_partial_layer)
        if _short_name(mark) in marquee_partial_inside_names
    ]
    marquee_partial_after = [
        tuple(cmds.xform(mark, query=True, worldSpace=True, translation=True))
        for mark in marquee_partial_after_marks
        if cmds.objExists(mark)
    ]
    marquee_partial_move_ok = bool(
        marquee_partial_box
        and marquee_partial_before
        and len(marquee_partial_before) == len(marquee_partial_after)
        and any(
            math.sqrt(sum((float(after[index]) - float(before[index])) ** 2.0 for index in range(3))) > 0.01
            for before, after in zip(marquee_partial_before, marquee_partial_after)
        )
    )
    marquee_partial_box_clean = bool(
        not marquee_partial_box
        or not cmds.objExists(marquee_partial_box)
    ) and not controller._marquee_transform_box_candidates()
    controller.delete_layer(marquee_partial_layer)
    viewport_target = controller.create_mark("Line", layer, DEFAULT_COLORS["Blue"], 2.0, 1.0, camera_note=True)
    line = viewport_target
    cmds.select(viewport_target, replace=True)
    viewport_move_ok = controller.activate_viewport_transform("move")
    viewport_move_context = cmds.currentCtx()
    viewport_rotate_ok = controller.activate_viewport_transform("rotate")
    viewport_rotate_context = cmds.currentCtx()
    viewport_scale_ok = controller.activate_viewport_transform("scale")
    viewport_scale_context = cmds.currentCtx()
    viewport_transform_selection_count = len(controller.selected_marks())
    translucent_on = controller.toggle_marks_translucent(layer)
    translucent_display_types = [
        int(cmds.getAttr(shape + ".overrideDisplayType"))
        for shape in _mark_shapes(viewport_target)
        if cmds.objExists(shape + ".overrideDisplayType")
    ]
    translucent_off = controller.toggle_marks_translucent(layer)
    opaque_display_types = [
        int(cmds.getAttr(shape + ".overrideDisplayType"))
        for shape in _mark_shapes(viewport_target)
        if cmds.objExists(shape + ".overrideDisplayType")
    ]
    preset_shape = controller.create_shape_preset("Star", layer, DEFAULT_COLORS["White"], 2.0, 0.8)
    one_frame_frame = int(round(float(cmds.currentTime(query=True))))
    one_frame_mark = controller.create_mark("Line", layer, DEFAULT_COLORS["Blue"], 2.0, 1.0, one_frame=True)
    one_frame_keys = sorted({int(round(float(value))) for value in (cmds.keyframe(one_frame_mark, attribute="visibility", query=True, timeChange=True) or [])}) if one_frame_mark and cmds.objExists(one_frame_mark) else []
    one_frame_visible_now = bool(cmds.getAttr(one_frame_mark + ".visibility")) if one_frame_mark and cmds.objExists(one_frame_mark) else False
    one_frame_visibility_values = {
        "before": bool(cmds.getAttr(one_frame_mark + ".visibility", time=one_frame_frame - 1)),
        "on": bool(cmds.getAttr(one_frame_mark + ".visibility", time=one_frame_frame)),
        "after": bool(cmds.getAttr(one_frame_mark + ".visibility", time=one_frame_frame + 1)),
    } if one_frame_mark and cmds.objExists(one_frame_mark) else {}
    opacity_existing_mark = controller.create_mark("Line", layer, DEFAULT_COLORS["Green"], 2.0, 0.8)
    layer_opacity_set = controller.set_layer_opacity(layer, 0.35)
    existing_shape_alphas = [
        float(cmds.getAttr(shape + ".overrideColorA"))
        for shape in _mark_shapes(opacity_existing_mark)
        if cmds.objExists(shape + ".overrideColorA")
    ]
    opacity_future_mark = controller.create_mark("Ellipse", layer, DEFAULT_COLORS["Yellow"], 2.0, 0.8)
    future_shape_alphas = [
        float(cmds.getAttr(shape + ".overrideColorA"))
        for shape in _mark_shapes(opacity_future_mark)
        if cmds.objExists(shape + ".overrideColorA")
    ]
    layer_opacity_35_effective = bool(
        layer_opacity_set
        and existing_shape_alphas
        and future_shape_alphas
        and all(abs(alpha - 0.28) <= 1.0e-6 for alpha in existing_shape_alphas + future_shape_alphas)
    )
    saved_swatches = controller.save_swatch((0.25, 0.5, 0.9))
    controller.refresh_camera_scope()
    text = controller.create_mark("Text", layer, DEFAULT_COLORS["White"], 2.0, 1.0, text="Animators Pencil")
    delete_target = controller.create_mark("Line", layer, DEFAULT_COLORS["Black"], 2.0, 1.0)
    cmds.select(delete_target, replace=True)
    controller.delete_selected_marks()
    controller.add_key()
    dupes = controller.duplicate_previous_key(layer)
    ghosts = controller.make_ghosts(layer, before=3, after=3)
    ghost_exists = cmds.objExists(ghosts)
    onion_job = controller.enable_onion_skin(layer, before=2, after=2, opacity=0.25)
    cmds.currentTime(11)
    onion_refresh_exists = cmds.objExists("amirAnimatorsPencilGhosts_GRP")
    controller.disable_onion_skin()
    onion_cleared = not cmds.objExists("amirAnimatorsPencilGhosts_GRP")
    notes_camera = controller.camera_notes_camera(create=False)
    camera_note_keys = sorted({int(round(float(value))) for value in (cmds.keyframe(notes_camera, query=True, timeChange=True) or [])}) if notes_camera and cmds.objExists(notes_camera) else []
    second_camera, _second_camera_shape = cmds.camera(name="amirPencilSmokeSecondView_CAM")
    _set_camera_for_model_panels(second_camera)
    second_camera_layer = controller.active_layer_for_camera(layer, camera=second_camera)
    controller.rename_layer(second_camera_layer, "Smoke Camera Layer")
    second_camera_layer_data = controller.layer_data(second_camera_layer)
    camera_layer_switch_ok = bool(
        second_camera_layer != layer
        and _short_name(second_camera_layer_data.get("camera")) == _short_name(second_camera)
    )

    smoke_camera_shape = _camera_shape(smoke_camera)
    source_camera_settings = {
        "panZoomEnabled": True,
        "horizontalPan": 0.37,
        "verticalPan": -0.21,
        "zoom": 1.45,
        "cameraScale": 1.25,
    }
    for attr_name, value in source_camera_settings.items():
        cmds.setAttr(smoke_camera_shape + "." + attr_name, value)
    first_source_matrix = cmds.xform(smoke_camera, query=True, matrix=True, worldSpace=True)
    first_source_focal = float(cmds.getAttr(_camera_shape(smoke_camera) + ".focalLength"))
    first_drawing_view = controller.create_drawing_view_from_current_view(name="Pencil View 1", switch=False, source_camera=smoke_camera)
    first_drawing_view_data = controller.drawing_view_data(first_drawing_view)
    first_drawing_layer = controller.active_layer_for_camera(camera=first_drawing_view)
    first_view_matrix = cmds.xform(first_drawing_view, query=True, matrix=True, worldSpace=True)
    first_view_focal = float(cmds.getAttr(_camera_shape(first_drawing_view) + ".focalLength"))
    saved_camera_settings = {
        attr_name: cmds.getAttr(_camera_shape(first_drawing_view) + "." + attr_name)
        for attr_name in source_camera_settings
    }
    drawing_view_copy_ok = bool(
        first_drawing_view
        and first_drawing_view_data.get("label") == "Pencil View 1"
        and len(first_source_matrix) == len(first_view_matrix)
        and all(abs(float(source) - float(saved)) <= 1.0e-6 for source, saved in zip(first_source_matrix, first_view_matrix))
        and abs(first_source_focal - first_view_focal) <= 1.0e-6
        and all(abs(float(source_camera_settings[name]) - float(saved_camera_settings[name])) <= 1.0e-6 for name in source_camera_settings)
    )

    cmds.xform(smoke_camera, worldSpace=True, translation=(9.0, 6.0, 15.0), rotation=(-12.0, 42.0, 0.0))
    first_view_matrix_after_source_move = cmds.xform(first_drawing_view, query=True, matrix=True, worldSpace=True)
    saved_drawing_view_stays_fixed = bool(
        len(first_view_matrix) == len(first_view_matrix_after_source_move)
        and all(abs(float(before) - float(after)) <= 1.0e-6 for before, after in zip(first_view_matrix, first_view_matrix_after_source_move))
    )
    second_drawing_view = controller.create_drawing_view_from_current_view(name="Pencil View 2", switch=False, source_camera=smoke_camera)
    second_drawing_layer = controller.active_layer_for_camera(camera=second_drawing_view)
    saved_drawing_views = controller.drawing_views()
    separate_drawing_view_layers = bool(
        first_drawing_view != second_drawing_view
        and first_drawing_layer != second_drawing_layer
        and _short_name(controller.layer_data(first_drawing_layer).get("camera")) == _short_name(first_drawing_view)
        and _short_name(controller.layer_data(second_drawing_layer).get("camera")) == _short_name(second_drawing_view)
    )
    drawing_frame = 24
    cmds.currentTime(drawing_frame)
    first_view_mark = controller.create_mark("Line", first_drawing_layer, DEFAULT_COLORS["Red"], 2.0, 1.0, one_frame=True)
    second_view_mark = controller.create_mark("Line", second_drawing_layer, DEFAULT_COLORS["Blue"], 2.0, 1.0, one_frame=True)
    saved_view_marks_are_camera_and_frame_specific = bool(
        _get_json_attr(first_view_mark, "animatorsPencilMarkData", {}).get("layer") == _long_name(first_drawing_layer)
        and _get_json_attr(second_view_mark, "animatorsPencilMarkData", {}).get("layer") == _long_name(second_drawing_layer)
        and controller.layer_data(first_drawing_layer, include_count=False).get("camera") != controller.layer_data(second_drawing_layer, include_count=False).get("camera")
        and bool(cmds.getAttr(first_view_mark + ".visibility", time=drawing_frame))
        and not bool(cmds.getAttr(first_view_mark + ".visibility", time=drawing_frame + 1))
        and bool(cmds.getAttr(second_view_mark + ".visibility", time=drawing_frame))
        and not bool(cmds.getAttr(second_view_mark + ".visibility", time=drawing_frame + 1))
    )
    real_set_camera_for_model_panels = globals()["_set_camera_for_model_panels"]
    try:
        globals()["_set_camera_for_model_panels"] = lambda _camera: True
        switched_drawing_view = controller.switch_to_drawing_view(first_drawing_view)
    finally:
        globals()["_set_camera_for_model_panels"] = real_set_camera_for_model_panels
    drawing_view_switch_ok = bool(
        _long_name(switched_drawing_view) == _long_name(first_drawing_view)
        and controller.active_layer() == _long_name(first_drawing_layer)
    )
    _set_camera_for_model_panels(first_drawing_view)
    navigation_panel = _active_model_panel()
    navigation_widget = _model_panel_viewport_widget(navigation_panel)
    fixed_camera_matrix_before_navigation = cmds.xform(first_drawing_view, query=True, matrix=True, worldSpace=True)
    navigation_switched_to_perspective = bool(
        _set_camera_for_viewport_widget(navigation_widget, "persp")
        and _short_name(_panel_camera_transform(navigation_panel)) == "persp"
    ) if navigation_widget else False
    fixed_camera_matrix_after_navigation = cmds.xform(first_drawing_view, query=True, matrix=True, worldSpace=True)
    fixed_camera_unchanged_after_navigation = bool(
        len(fixed_camera_matrix_before_navigation) == len(fixed_camera_matrix_after_navigation)
        and all(
            abs(float(before) - float(after)) <= 1.0e-6
            for before, after in zip(fixed_camera_matrix_before_navigation, fixed_camera_matrix_after_navigation)
        )
    )
    if navigation_widget:
        _set_camera_for_viewport_widget(navigation_widget, first_drawing_view)
    controller.refresh_camera_scope(force=True)
    original_layers_method = controller.layers
    idle_layer_scan_calls = [0]

    def counted_layers():
        idle_layer_scan_calls[0] += 1
        return original_layers_method()

    controller.layers = counted_layers
    try:
        unchanged_camera_refresh = controller.refresh_camera_scope()
    finally:
        controller.layers = original_layers_method
    idle_refresh_skips_layer_scan = bool(not unchanged_camera_refresh and idle_layer_scan_calls[0] == 0)
    real_dragger_context = cmds.draggerContext
    option_update_context_calls = []

    def counted_dragger_context(*args, **kwargs):
        option_update_context_calls.append((args, kwargs))
        return real_dragger_context(*args, **kwargs)

    cmds.draggerContext = counted_dragger_context
    try:
        controller.update_drag_draw_options(
            tool="Brush",
            layer_node=first_drawing_layer,
            color=DEFAULT_COLORS["Green"],
            size=7.0,
            opacity=0.65,
            one_frame=True,
        )
    finally:
        cmds.draggerContext = real_dragger_context
    context_option_update_reuses_existing = bool(
        not option_update_context_calls
        and controller._drag_options.get("tool") == "Brush"
        and controller._drag_options.get("size") == 7.0
    )
    ordinary_view_count_before = len(controller.drawing_views())
    ordinary_camera_change = controller.ensure_drawing_view_for_drawing(first_drawing_layer, camera=second_camera)
    ordinary_camera_saved_view = ordinary_camera_change.get("camera") or ""
    ordinary_camera_saved_layer = ordinary_camera_change.get("layer") or ""
    ordinary_camera_change_creates_saved_view = bool(
        ordinary_camera_change.get("created")
        and controller.is_drawing_view(ordinary_camera_saved_view)
        and _long_name(ordinary_camera_saved_view) != _long_name(second_camera)
        and _short_name(controller.layer_data(ordinary_camera_saved_layer, include_count=False).get("camera")) == _short_name(ordinary_camera_saved_view)
        and len(controller.drawing_views()) == ordinary_view_count_before + 1
    )

    _set_camera_for_model_panels(smoke_camera)
    controller.refresh_camera_scope()
    opacity_after_camera_refresh = bool(
        opacity_existing_mark
        and all(abs(float(cmds.getAttr(shape + ".overrideColorA")) - 0.28) <= 1.0e-6 for shape in _mark_shapes(opacity_existing_mark) if cmds.objExists(shape + ".overrideColorA"))
        and abs(float(cmds.getAttr(layer + "." + LAYER_OPACITY_ATTR)) - 0.35) <= 1.0e-6
    )
    layer_hidden_ok = controller.set_layer_visibility(layer, False) and not controller.layer_data(layer).get("visible", True)
    controller.refresh_camera_scope()
    layer_hidden_persists_after_camera_scope = not controller.layer_data(layer).get("visible", True)
    show_all_count = controller.set_all_layers_visibility(True)
    all_layers_visible = bool(show_all_count and all(item.get("visible", False) for item in controller.layers()))
    screen_rectangle_points = controller._tool_screen_points_from_drag("Rectangle", (110, 80, 0), (420, 260, 0))
    screen_rectangle_axis_aligned = bool(
        len(screen_rectangle_points) == 5
        and screen_rectangle_points[0][1] == screen_rectangle_points[1][1]
        and screen_rectangle_points[1][0] == screen_rectangle_points[2][0]
        and screen_rectangle_points[2][1] == screen_rectangle_points[3][1]
        and screen_rectangle_points[3][0] == screen_rectangle_points[4][0]
    )
    controller.update_drag_draw_options(
        tool="Pencil",
        layer_node=layer,
        color=DEFAULT_COLORS["Green"],
        size=3.0,
        opacity=1.0,
    )
    preview_node = controller._update_drag_preview([(-0.8, -0.8, 0.0), (-0.2, -0.3, 0.0)])
    preview_first_visible = bool(preview_node and cmds.objExists(preview_node))
    preview_node_after_update = controller._update_drag_preview(
        [(-0.8, -0.8, 0.0), (-0.2, -0.3, 0.0), (0.4, -0.55, 0.0)],
        force=True,
    )
    preview_shapes = cmds.listRelatives(preview_node_after_update, shapes=True, noIntermediate=True, fullPath=True) or []
    preview_cv_count = sum(len(cmds.ls(shape + ".cv[*]", flatten=True) or []) for shape in preview_shapes)
    controller._discard_drag_preview()
    live_preview_updates_and_cleans = bool(
        preview_first_visible
        and preview_node_after_update
        and preview_cv_count == 3
        and not cmds.objExists(preview_node_after_update)
    )
    rename_original_label = controller.drawing_view_data(first_drawing_view).get("label", "")
    rename_ok, _rename_message = controller.rename_drawing_view(first_drawing_view, "Smoke Renamed View")
    rename_duplicate_guarded = not controller.rename_drawing_view(second_drawing_view, "Smoke Renamed View")[0]
    rename_empty_guarded = not controller.rename_drawing_view(first_drawing_view, "   ")[0]
    rename_scene_path = os.path.join(cmds.internalVar(userTmpDir=True), "aminate_pencil_saved_view_rename_smoke.ma")
    rename_persisted_after_reopen = False
    try:
        cmds.file(rename=rename_scene_path)
        cmds.file(save=True, type="mayaAscii")
        cmds.file(rename_scene_path, open=True, force=True)
        rename_persisted_after_reopen = controller.drawing_view_data(first_drawing_view).get("label", "") == "Smoke Renamed View"
    except Exception:
        rename_persisted_after_reopen = False
    opacity_save_reopen_ok = False
    opacity_smoke_scene_path = os.path.join(cmds.internalVar(userTmpDir=True), "aminate_pencil_layer_opacity_smoke.ma")
    try:
        cmds.file(rename=opacity_smoke_scene_path)
        cmds.file(save=True, type="mayaAscii")
        cmds.file(opacity_smoke_scene_path, open=True, force=True)
        opacity_save_reopen_ok = bool(
            cmds.objExists(layer + "." + LAYER_OPACITY_ATTR)
            and abs(float(cmds.getAttr(layer + "." + LAYER_OPACITY_ATTR)) - 0.35) <= 1.0e-6
            and opacity_existing_mark
            and all(abs(float(cmds.getAttr(shape + ".overrideColorA")) - 0.28) <= 1.0e-6 for shape in _mark_shapes(opacity_existing_mark) if cmds.objExists(shape + ".overrideColorA"))
        )
    except Exception:
        opacity_save_reopen_ok = False
    controller.set_active_layer(layer)
    data = {
        "root_exists": cmds.objExists(ROOT_GROUP_NAME),
        "layer": layer,
        "camera_space_anchor_ok": camera_space_anchor_ok,
        "line": line,
        "rect": rect,
        "dragged_rect": dragged_rect,
        "dragged_ellipse": dragged_ellipse,
        "freehand": freehand,
        "freehand_point_count": _get_json_attr(freehand, "animatorsPencilMarkData", {}).get("freehandPointCount") if freehand and cmds.objExists(freehand) else 0,
        "freehand_local_points_match": freehand_local_points_match,
        "erased_count": erased_count,
        "erase_target_removed": erase_target_removed,
        "eraser_partial_fragment_count": len(partial_fragments),
        "eraser_partial_gap": eraser_partial_gap,
        "eraser_kept_other_layer": eraser_kept_other_layer,
        "multi_frame_preview_ok": multi_frame_preview_ok,
        "multi_frame_eraser_all_marks": multi_frame_eraser_all_marks,
        "whole_erased_count": whole_erased_count,
        "whole_erase_removed": whole_erase_removed,
        "locked_erase_count": locked_erase_count,
        "locked_erase_guarded": locked_erase_guarded,
        "camera_layer_switch_ok": camera_layer_switch_ok,
        "drawing_view_copy_ok": drawing_view_copy_ok,
        "drawing_view_camera_settings": saved_camera_settings,
        "saved_drawing_view_stays_fixed": saved_drawing_view_stays_fixed,
        "drawing_view_count": len(saved_drawing_views),
        "drawing_view_switch_ok": drawing_view_switch_ok,
        "navigation_widget_available": bool(navigation_widget),
        "navigation_switched_to_perspective": navigation_switched_to_perspective,
        "fixed_camera_unchanged_after_navigation": fixed_camera_unchanged_after_navigation,
        "separate_drawing_view_layers": separate_drawing_view_layers,
        "saved_view_marks_are_camera_and_frame_specific": saved_view_marks_are_camera_and_frame_specific,
        "idle_refresh_skips_layer_scan": idle_refresh_skips_layer_scan,
        "context_option_update_reuses_existing": context_option_update_reuses_existing,
        "ordinary_camera_change_creates_saved_view": ordinary_camera_change_creates_saved_view,
        "default_one_frame_only": DEFAULT_ONE_FRAME_ONLY,
        "first_drawing_view": first_drawing_view,
        "second_drawing_view": second_drawing_view,
        "first_drawing_layer": first_drawing_layer,
        "second_drawing_layer": second_drawing_layer,
        "layer_hidden_ok": layer_hidden_ok,
        "layer_hidden_persists_after_camera_scope": layer_hidden_persists_after_camera_scope,
        "layer_opacity_35_effective": layer_opacity_35_effective,
        "opacity_after_camera_refresh": opacity_after_camera_refresh,
        "opacity_save_reopen_ok": opacity_save_reopen_ok,
        "layer_opacity": float(cmds.getAttr(layer + "." + LAYER_OPACITY_ATTR)) if cmds.objExists(layer + "." + LAYER_OPACITY_ATTR) else 1.0,
        "layer_effective_visible": controller.layer_data(layer).get("effective_visible", True),
        "show_all_count": show_all_count,
        "all_layers_visible": all_layers_visible,
        "screen_rectangle_axis_aligned": screen_rectangle_axis_aligned,
        "live_preview_updates_and_cleans": live_preview_updates_and_cleans,
        "saved_view_rename_ok": bool(rename_ok and rename_original_label and rename_duplicate_guarded and rename_empty_guarded),
        "saved_view_rename_persisted_after_reopen": rename_persisted_after_reopen,
        "second_camera_layer": second_camera_layer,
        "rename_layer_ok": rename_layer_ok,
        "renamed_layer_name": renamed_layer_name,
        "preset_saved": preset_saved,
        "custom_shape_present": custom_shape_present,
        "custom_preset_shape": custom_preset_shape,
        "preset_deleted": preset_deleted,
        "marquee_select_count": len(marquee_selected),
        "marquee_transform_box_active": marquee_transform_box_active,
        "marquee_transform_box_committed": marquee_transform_box_committed,
        "marquee_partial_split_ok": marquee_partial_split_ok,
        "marquee_partial_move_ok": marquee_partial_move_ok,
        "marquee_partial_box_clean": marquee_partial_box_clean,
        "viewport_move_ok": viewport_move_ok,
        "viewport_move_context": viewport_move_context,
        "viewport_rotate_ok": viewport_rotate_ok,
        "viewport_rotate_context": viewport_rotate_context,
        "viewport_scale_ok": viewport_scale_ok,
        "viewport_scale_context": viewport_scale_context,
        "viewport_transform_selection_count": viewport_transform_selection_count,
        "translucent_on": translucent_on,
        "translucent_display_types": translucent_display_types,
        "translucent_off": translucent_off,
        "opaque_display_types": opaque_display_types,
        "default_shortcuts": controller.default_shortcut_bindings(),
        "delete_selected_removed_mark": bool(delete_target and not cmds.objExists(delete_target)),
        "drag_shape_bounds": _get_json_attr(dragged_rect, "animatorsPencilMarkData", {}).get("dragBounds") if dragged_rect and cmds.objExists(dragged_rect) else [],
        "text": text,
        "preset_shape": preset_shape,
        "stamp_angle_ok": stamp_angle_ok,
        "stamp_tools_tested": sorted(stamp_marks.keys()),
        "legacy_migration_ok": legacy_migration_ok,
        "legacy_direct_camera_migration_ok": legacy_direct_camera_migration_ok,
        "legacy_migration_idempotent": legacy_migration_idempotent,
        "one_frame_mark": one_frame_mark,
        "one_frame_visibility_keys": one_frame_keys,
        "one_frame_visible_now": one_frame_visible_now,
        "one_frame_visibility_values": one_frame_visibility_values,
        "shape_library_names": sorted(controller.shape_library().keys()),
        "saved_swatch_count": len(saved_swatches),
        "dupe_count": len(dupes),
        "ghost_exists": ghost_exists,
        "onion_job": onion_job,
        "onion_refresh_exists": onion_refresh_exists,
        "onion_cleared": onion_cleared,
        "mark_count": len(controller.marks(layer)),
        "scene_native_mark_shapes": len(cmds.listRelatives(layer, allDescendents=True, type="nurbsCurve") or []),
        "scene_native_mark_shapes_visible": sum(
            1
            for shape in (cmds.listRelatives(layer, allDescendents=True, type="nurbsCurve", fullPath=True) or [])
            if bool(cmds.getAttr(shape + ".visibility"))
        ),
        "layer_data": controller.layer_data(layer),
        "shape_tool_names": list(SHAPE_TOOL_NAMES),
        "stroke_path_tools": list(STROKE_PATH_TOOLS),
        "camera_notes_exists": bool(notes_camera and cmds.objExists(notes_camera)),
        "camera_notes_key_frames": camera_note_keys,
        "camera_notes_line_link": _get_string_attr(line, "animatorsPencilCameraNotesCamera", "") if line and cmds.objExists(line) else "",
    }
    return data


if __name__ == "__main__":
    launch_animators_pencil()
