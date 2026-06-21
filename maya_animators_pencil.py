"""
maya_animators_pencil.py

Scene-native drawing layer tool for Maya animators.
"""

from __future__ import absolute_import, division, print_function

import json
import math
import os
import time

try:
    import maya.cmds as cmds
    import maya.mel as mel
    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    mel = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:
    from PySide2 import QtCore, QtGui, QtWidgets


WINDOW_OBJECT_NAME = "mayaAnimatorsPencilWindow"
ROOT_GROUP_NAME = "amirAnimatorsPencil_GRP"
ROOT_MARKER_ATTR = "amirAnimatorsPencilRoot"
ROOT_STATE_ATTR = "animatorsPencilState"
LAYER_MARKER_ATTR = "amirAnimatorsPencilLayer"
MARK_MARKER_ATTR = "amirAnimatorsPencilMark"
LAYER_VERSION = 1

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
TOOL_NAMES = ("Pencil", "Brush", "Eraser", "Text", "Line", "Arrow", "Rectangle", "Ellipse")
SHAPE_TOOL_NAMES = ("Line", "Arrow", "Rectangle", "Ellipse")
CAMERA_NOTES_NAME = "amirAnimatorsPencilNotes_CAM"
CAMERA_NOTES_SHAPE_NAME = CAMERA_NOTES_NAME + "Shape"
CAMERA_NOTES_ATTR = "animatorsPencilCameraNotes"
DRAW_CONTEXT_NAME = "aminateAnimatorsPencilDrawContext"
MARQUEE_CONTEXT_NAME = "aminateAnimatorsPencilMarqueeContext"
TRANSLUCENT_MARKS_ATTR = "animatorsPencilTranslucentMarks"
DEFAULT_SHORTCUTS = {
    "drag_draw": "D",
    "marquee_select": "M",
    "erase_selected": "Delete",
    "toggle_translucent": "T",
}
GLOBAL_DRAG_CONTEXT_CONTROLLER = None


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


def _shortcut_class():
    return getattr(QtWidgets, "QShortcut", None) or getattr(QtGui, "QShortcut", None)


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
        panel = cmds.getPanel(withFocus=True)
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
        panel = cmds.getPanel(withFocus=True)
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            cmds.modelPanel(panel, edit=True, camera=camera_transform)
            changed = True
    except Exception:
        pass
    if changed:
        return True
    for panel in cmds.getPanel(type="modelPanel") or []:
        try:
            cmds.modelPanel(panel, edit=True, camera=camera_transform)
            return True
        except Exception:
            continue
    return False


def _active_model_panel():
    if not MAYA_AVAILABLE:
        return ""
    try:
        panel = cmds.getPanel(withFocus=True)
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            return panel
    except Exception:
        pass
    panels = cmds.getPanel(type="modelPanel") or []
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


def _screen_to_layer_point(layer_node, screen_point):
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


def _curve_node(name, points, parent, color, opacity, size, degree=1):
    curve = cmds.curve(name=name, degree=degree, point=points)
    if parent:
        curve = cmds.parent(curve, parent)[0]
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
        elif tool == "ellipse":
            painter.drawEllipse(6, 8, 16, 12)
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
        self._drag_points = []
        self._marquee_options = {}
        self._marquee_anchor = None

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
        elif tool == "Ellipse":
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

    def layers(self):
        if not MAYA_AVAILABLE:
            return []
        root = self.root()
        result = []
        for node in cmds.ls(type="transform", long=True) or []:
            if _get_string_attr(node, LAYER_MARKER_ATTR, "") != "layer":
                continue
            data = self.layer_data(node)
            result.append(data)
        result.sort(key=lambda item: (item.get("order", 0), item.get("name", "")))
        return result

    def layer_data(self, layer_node):
        layer_node = _long_name(layer_node)
        data = _get_json_attr(layer_node, "animatorsPencilLayerData", {}) or {}
        data["node"] = layer_node
        data.setdefault("name", _short_name(layer_node))
        data.setdefault("camera", _get_string_attr(layer_node, "animatorsPencilCamera", ""))
        data.setdefault("state", _get_string_attr(layer_node, "animatorsPencilLayerState", "Animation"))
        data.setdefault("order", int(cmds.getAttr(layer_node + ".animatorsPencilLayerOrder")) if cmds.objExists(layer_node + ".animatorsPencilLayerOrder") else 0)
        data.setdefault("locked", bool(cmds.getAttr(layer_node + ".animatorsPencilLayerLocked")) if cmds.objExists(layer_node + ".animatorsPencilLayerLocked") else False)
        data["count"] = len(self.marks(layer_node))
        return data

    def active_layer(self):
        state = _get_json_attr(self.root(), ROOT_STATE_ATTR, {}) or {}
        layer = state.get("active_layer")
        if layer and cmds.objExists(layer):
            return _long_name(layer)
        layers = self.layers()
        if layers:
            return layers[0]["node"]
        return self.create_layer("Pencil Layer")

    def set_active_layer(self, layer_node):
        root = self.root()
        state = _get_json_attr(root, ROOT_STATE_ATTR, {}) or {}
        state["active_layer"] = _long_name(layer_node)
        _set_json_attr(root, ROOT_STATE_ATTR, state)

    def create_layer(self, name="Pencil Layer", camera=None, state="Animation"):
        if not MAYA_AVAILABLE:
            return ""
        camera = camera or _current_camera()
        order = len(self.layers())
        layer_name = "amirPencil_{0}_{1}_LYR".format(_safe_name(camera), _safe_name(name))
        layer = cmds.createNode("transform", name=layer_name)
        if camera and cmds.objExists(camera):
            try:
                layer = cmds.parent(layer, camera)[0]
            except Exception:
                pass
        layer = _long_name(layer)
        cmds.setAttr(layer + ".translate", 0, 0, -10.0 - (order * 0.03), type="double3")
        _set_string_attr(layer, LAYER_MARKER_ATTR, "layer")
        _set_string_attr(layer, "animatorsPencilCamera", camera or "")
        _set_string_attr(layer, "animatorsPencilLayerState", state)
        _ensure_attr(layer, "animatorsPencilLayerOrder", "long", order)
        _ensure_attr(layer, "animatorsPencilLayerLocked", "bool", False)
        data = {"version": LAYER_VERSION, "name": name, "camera": camera, "state": state, "order": order, "locked": False}
        _set_json_attr(layer, "animatorsPencilLayerData", data)
        self.set_active_layer(layer)
        self._status("Layer created: {0}".format(name))
        return layer

    def delete_layer(self, layer_node):
        if layer_node and cmds.objExists(layer_node):
            cmds.delete(layer_node)
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

    def move_layer_order(self, layer_node, delta):
        layers = self.layers()
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
        world_matrix = cmds.xform(layer_node, query=True, matrix=True, worldSpace=True)
        layer_node = cmds.parent(layer_node, camera)[0]
        layer_node = _long_name(layer_node)
        cmds.xform(layer_node, matrix=world_matrix, worldSpace=True)
        _set_string_attr(layer_node, "animatorsPencilCamera", camera)
        data = self.layer_data(layer_node)
        data["camera"] = camera
        _set_json_attr(layer_node, "animatorsPencilLayerData", data)
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
        children = cmds.listRelatives(layer_node, children=True, fullPath=True) or []
        return [child for child in children if _get_string_attr(child, MARK_MARKER_ATTR, "") == "mark"]

    def selected_marks(self):
        if not MAYA_AVAILABLE:
            return []
        selected = cmds.ls(selection=True, type="transform", long=True) or []
        return [node for node in selected if _get_string_attr(node, MARK_MARKER_ATTR, "") == "mark"]

    def _mark_node(self, node, layer_node, tool, color, opacity, size, frame=None):
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
        }
        _set_json_attr(node, "animatorsPencilMarkData", data)
        _ensure_attr(node, "animatorsPencilFrame", "long", frame)
        cmds.setAttr(node + ".animatorsPencilFrame", frame)
        self._key_mark_visibility(node, layer_node, frame)
        return node

    def _key_mark_visibility(self, node, layer_node, frame):
        layer_state = _get_string_attr(layer_node, "animatorsPencilLayerState", "Animation")
        if layer_state == "Static":
            cmds.setAttr(node + ".visibility", True)
            return
        cmds.setAttr(node + ".visibility", False)
        cmds.setKeyframe(node, attribute="visibility", time=max(frame - 1, 0), value=0)
        cmds.setAttr(node + ".visibility", True)
        cmds.setKeyframe(node, attribute="visibility", time=frame, value=1)

    def _tool_points(self, tool):
        if tool == "Brush":
            return [(-1.0, -0.15, 0.0), (-0.45, 0.25, 0.0), (0.1, -0.05, 0.0), (0.75, 0.28, 0.0)]
        if tool == "Line":
            return [(-0.8, 0.0, 0.0), (0.8, 0.0, 0.0)]
        if tool == "Arrow":
            return [(-0.9, 0.0, 0.0), (0.75, 0.0, 0.0), (0.45, 0.22, 0.0), (0.75, 0.0, 0.0), (0.45, -0.22, 0.0)]
        if tool == "Rectangle":
            return [(-0.7, -0.45, 0.0), (0.7, -0.45, 0.0), (0.7, 0.45, 0.0), (-0.7, 0.45, 0.0), (-0.7, -0.45, 0.0)]
        if tool == "Ellipse":
            points = []
            for i in range(33):
                angle = (math.pi * 2.0) * (float(i) / 32.0)
                points.append((math.cos(angle) * 0.72, math.sin(angle) * 0.45, 0.0))
            return points
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
        if tool == "Ellipse":
            points = []
            rx = max((max_x - min_x) * 0.5, 0.05)
            ry = max((max_y - min_y) * 0.5, 0.05)
            for i in range(49):
                angle = (math.pi * 2.0) * (float(i) / 48.0)
                points.append((cx + (math.cos(angle) * rx), cy + (math.sin(angle) * ry), 0.0))
            return points
        if tool == "Brush":
            return [(sx, sy, 0.0), ((sx + cx) * 0.5, cy + 0.15, 0.0), (cx, cy - 0.12, 0.0), ((ex + cx) * 0.5, cy + 0.18, 0.0), (ex, ey, 0.0)]
        return [(sx, sy, 0.0), ((sx + cx) * 0.5, cy + 0.1, 0.0), (cx, cy - 0.08, 0.0), ((ex + cx) * 0.5, cy + 0.12, 0.0), (ex, ey, 0.0)]

    def _bounds_from_points(self, points):
        xs = [float(point[0]) for point in points] or [0.0]
        ys = [float(point[1]) for point in points] or [0.0]
        return [min(xs), min(ys), max(xs), max(ys)]

    def _point_distance(self, point_a, point_b):
        return math.sqrt(((float(point_a[0]) - float(point_b[0])) ** 2.0) + ((float(point_a[1]) - float(point_b[1])) ** 2.0))

    def create_mark(self, tool="Pencil", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True, points=None):
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
                group = cmds.parent(group, layer_node)[0]
                group = _long_name(group)
                cmds.setAttr(group + ".translate", -0.55, 0.0, 0.0, type="double3")
                cmds.setAttr(group + ".scale", 0.025, 0.025, 0.025, type="double3")
                mark = group
                _set_display_color(mark, color, opacity=opacity, line_width=size)
            else:
                mark_points = points or self._tool_points(tool)
                mark = _curve_node("amirPencil{0}_MARK".format(tool), mark_points, layer_node, color, opacity, size)
            self._mark_node(mark, layer_node, tool, color, opacity, size)
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

    def create_mark_from_drag(self, tool="Rectangle", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True, start_point=(-0.5, 0.35, 0.0), end_point=(0.5, -0.35, 0.0)):
        points = self._tool_points_from_drag(tool, start_point, end_point)
        mark = self.create_mark(tool, layer_node, color, size, opacity, text, camera_note, camera_snap, points=points)
        if mark and cmds.objExists(mark):
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            data["dragStart"] = [float(start_point[0]), float(start_point[1])]
            data["dragEnd"] = [float(end_point[0]), float(end_point[1])]
            data["dragBounds"] = self._bounds_from_points(points)
            _set_json_attr(mark, "animatorsPencilMarkData", data)
        return mark

    def create_freehand_mark(self, tool="Pencil", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True, points=None):
        clean_points = [(float(point[0]), float(point[1]), 0.0) for point in (points or [])]
        if len(clean_points) < 2:
            return self.create_mark_from_drag(tool, layer_node, color, size, opacity, text, camera_note, camera_snap)
        mark = self.create_mark(tool, layer_node, color, size, opacity, text, camera_note, camera_snap, points=clean_points)
        if mark and cmds.objExists(mark):
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            data["freehandDrawn"] = True
            data["freehandPointCount"] = len(clean_points)
            data["dragStart"] = [clean_points[0][0], clean_points[0][1]]
            data["dragEnd"] = [clean_points[-1][0], clean_points[-1][1]]
            data["dragBounds"] = self._bounds_from_points(clean_points)
            _set_json_attr(mark, "animatorsPencilMarkData", data)
        return mark

    def select_marks_in_box(self, layer_node=None, start_point=(-1.0, -1.0, 0.0), end_point=(1.0, 1.0, 0.0), add=False):
        if not MAYA_AVAILABLE:
            return []
        layer_node = layer_node or self.active_layer()
        min_x, max_x = min(float(start_point[0]), float(end_point[0])), max(float(start_point[0]), float(end_point[0]))
        min_y, max_y = min(float(start_point[1]), float(end_point[1])), max(float(start_point[1]), float(end_point[1]))
        picked = []
        for mark in self.marks(layer_node):
            data = _get_json_attr(mark, "animatorsPencilMarkData", {}) or {}
            bounds = data.get("dragBounds")
            if not bounds:
                try:
                    bounds = list(cmds.xform(mark, query=True, boundingBox=True, objectSpace=True) or [])
                    if len(bounds) >= 6:
                        bounds = [bounds[0], bounds[1], bounds[3], bounds[4]]
                except Exception:
                    bounds = None
            if not bounds or len(bounds) < 4:
                continue
            bx1, by1, bx2, by2 = float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])
            if bx2 < min_x or bx1 > max_x or by2 < min_y or by1 > max_y:
                continue
            picked.append(mark)
        if picked:
            if add:
                cmds.select(picked, add=True)
            else:
                cmds.select(picked, replace=True)
        else:
            cmds.select(clear=True)
        self._status("Marquee selected {0} pencil mark(s).".format(len(picked)))
        return picked

    def activate_drag_draw_context(self, tool="Rectangle", layer_node=None, color=(1.0, 0.05, 0.05), size=2.0, opacity=1.0, text="Note", camera_note=False, camera_snap=True):
        if not MAYA_AVAILABLE:
            return False
        global GLOBAL_DRAG_CONTEXT_CONTROLLER
        GLOBAL_DRAG_CONTEXT_CONTROLLER = self
        self._drag_options = {
            "tool": tool,
            "layer_node": layer_node or self.active_layer(),
            "color": color,
            "size": size,
            "opacity": opacity,
            "text": text,
            "camera_note": camera_note,
            "camera_snap": camera_snap,
        }
        self._drag_anchor = None
        self._drag_points = []
        _delete_drag_context(DRAW_CONTEXT_NAME)
        cmds.draggerContext(
            DRAW_CONTEXT_NAME,
            pressCommand=_animators_pencil_draw_press,
            dragCommand=_animators_pencil_draw_drag,
            releaseCommand=_animators_pencil_draw_release,
            cursor="crossHair",
            undoMode="step",
        )
        cmds.setToolTo(DRAW_CONTEXT_NAME)
        self._status("Drag in viewport to draw {0}.".format(tool))
        return True

    def activate_marquee_select_context(self, layer_node=None, add=False):
        if not MAYA_AVAILABLE:
            return False
        global GLOBAL_DRAG_CONTEXT_CONTROLLER
        GLOBAL_DRAG_CONTEXT_CONTROLLER = self
        self._marquee_options = {"layer_node": layer_node or self.active_layer(), "add": bool(add)}
        self._marquee_anchor = None
        _delete_drag_context(MARQUEE_CONTEXT_NAME)
        cmds.draggerContext(
            MARQUEE_CONTEXT_NAME,
            pressCommand=_animators_pencil_marquee_press,
            releaseCommand=_animators_pencil_marquee_release,
            cursor="crossHair",
            undoMode="step",
        )
        cmds.setToolTo(MARQUEE_CONTEXT_NAME)
        self._status("Drag a box over pencil marks to select them.")
        return True

    def _draw_context_press(self):
        try:
            self._drag_anchor = cmds.draggerContext(DRAW_CONTEXT_NAME, query=True, anchorPoint=True)
        except Exception:
            self._drag_anchor = None
        options = dict(self._drag_options)
        layer = options.get("layer_node") or self.active_layer()
        self._drag_points = [_screen_to_layer_point(layer, self._drag_anchor or (640, 360, 0))]

    def _draw_context_drag(self):
        options = dict(self._drag_options)
        if options.get("tool") not in ("Pencil", "Brush"):
            return
        layer = options.get("layer_node") or self.active_layer()
        try:
            drag_point = cmds.draggerContext(DRAW_CONTEXT_NAME, query=True, dragPoint=True)
        except Exception:
            drag_point = None
        point = _screen_to_layer_point(layer, drag_point or self._drag_anchor or (640, 360, 0))
        if not self._drag_points or self._point_distance(point, self._drag_points[-1]) >= 0.025:
            self._drag_points.append(point)

    def _draw_context_release(self):
        try:
            drag_point = cmds.draggerContext(DRAW_CONTEXT_NAME, query=True, dragPoint=True)
        except Exception:
            drag_point = None
        options = dict(self._drag_options)
        layer = options.get("layer_node") or self.active_layer()
        start_point = _screen_to_layer_point(layer, self._drag_anchor or drag_point or (640, 360, 0))
        end_point = _screen_to_layer_point(layer, drag_point or self._drag_anchor or (720, 420, 0))
        if options.get("tool") in ("Pencil", "Brush"):
            if drag_point:
                release_point = _screen_to_layer_point(layer, drag_point)
                if not self._drag_points or self._point_distance(release_point, self._drag_points[-1]) >= 0.001:
                    self._drag_points.append(release_point)
            self.create_freehand_mark(points=self._drag_points, **options)
        else:
            self.create_mark_from_drag(start_point=start_point, end_point=end_point, **options)

    def _marquee_context_press(self):
        try:
            self._marquee_anchor = cmds.draggerContext(MARQUEE_CONTEXT_NAME, query=True, anchorPoint=True)
        except Exception:
            self._marquee_anchor = None

    def _marquee_context_release(self):
        try:
            drag_point = cmds.draggerContext(MARQUEE_CONTEXT_NAME, query=True, dragPoint=True)
        except Exception:
            drag_point = None
        options = dict(self._marquee_options)
        layer = options.get("layer_node") or self.active_layer()
        start_point = _screen_to_layer_point(layer, self._marquee_anchor or drag_point or (0, 0, 0))
        end_point = _screen_to_layer_point(layer, drag_point or self._marquee_anchor or (1280, 720, 0))
        self.select_marks_in_box(layer, start_point, end_point, add=options.get("add", False))

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
            cmds.setKeyframe(mark, attribute=("translate", "rotate", "scale", "visibility"), time=_current_frame())
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

    def make_ghosts(self, layer_node=None, before=1, after=1, before_color=(0.1, 0.6, 1.0), after_color=(1.0, 0.4, 0.1)):
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
            _set_display_color(dup, color, opacity=0.35, line_width=max(1.0, float(data.get("size", 2.0)) * 0.75))
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


def _animators_pencil_marquee_release():
    if GLOBAL_DRAG_CONTEXT_CONTROLLER:
        GLOBAL_DRAG_CONTEXT_CONTROLLER._marquee_context_release()


class AnimatorsPencilPanel(QtWidgets.QWidget):
    def __init__(self, controller=None, parent=None):
        super(AnimatorsPencilPanel, self).__init__(parent)
        self.controller = controller or AnimatorsPencilController()
        self.controller.set_status_callback(self._set_status)
        self.current_layer = ""
        self._shortcuts = {}
        self._build_ui()
        self._install_shortcuts()
        self.refresh_layers()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        intro = QtWidgets.QLabel(
            "Simple flow: pick a layer, pick a tool, then click Drag Draw In Viewport. "
            "Use Marquee Select Marks to drag a box over pencil marks, then move, copy, erase, retime, or key them."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        native = QtWidgets.QGroupBox("Native Maya Blue Pencil")
        native_layout = QtWidgets.QGridLayout(native)
        self.open_native_button = QtWidgets.QPushButton("Open Blue Pencil")
        self.native_tool_button = QtWidgets.QPushButton("Use Tool In Viewport")
        self.native_options_button = QtWidgets.QPushButton("Apply Color / Size / Opacity")
        self.native_insert_button = QtWidgets.QPushButton("Insert BP Frame")
        self.native_duplicate_button = QtWidgets.QPushButton("Duplicate BP Frame")
        self.native_delete_button = QtWidgets.QPushButton("Delete BP Frame")
        self.native_ghost_button = QtWidgets.QPushButton("Native Ghosting")
        native_buttons = (
            self.open_native_button,
            self.native_tool_button,
            self.native_options_button,
            self.native_insert_button,
            self.native_duplicate_button,
            self.native_delete_button,
            self.native_ghost_button,
        )
        for index, button in enumerate(native_buttons):
            native_layout.addWidget(button, index // 3, index % 3)
        layout.addWidget(native)

        top = QtWidgets.QHBoxLayout()
        self.layer_name = QtWidgets.QLineEdit("Pencil Layer")
        top.addWidget(QtWidgets.QLabel("Layer"))
        top.addWidget(self.layer_name, 1)
        self.add_layer_button = QtWidgets.QPushButton("Add Layer")
        self.delete_layer_button = QtWidgets.QPushButton("Delete Layer")
        top.addWidget(self.add_layer_button)
        top.addWidget(self.delete_layer_button)
        layout.addLayout(top)

        self.layer_table = QtWidgets.QTableWidget(0, 5)
        self.layer_table.setHorizontalHeaderLabels(["Layer", "Camera", "State", "Locked", "Marks"])
        self.layer_table.horizontalHeader().setStretchLastSection(True)
        self.layer_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.layer_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.layer_table.setContextMenuPolicy(_qt_flag("ContextMenuPolicy", "CustomContextMenu", QtCore.Qt.CustomContextMenu))
        layout.addWidget(self.layer_table, 1)

        layer_buttons = QtWidgets.QHBoxLayout()
        self.state_combo = QtWidgets.QComboBox()
        self.state_combo.addItems(LAYER_STATES)
        self.layer_up_button = QtWidgets.QPushButton("Layer Up")
        self.layer_down_button = QtWidgets.QPushButton("Layer Down")
        self.move_camera_button = QtWidgets.QPushButton("Move Layer To Current Camera")
        layer_buttons.addWidget(QtWidgets.QLabel("State"))
        layer_buttons.addWidget(self.state_combo)
        layer_buttons.addWidget(self.layer_up_button)
        layer_buttons.addWidget(self.layer_down_button)
        layer_buttons.addWidget(self.move_camera_button, 1)
        layout.addLayout(layer_buttons)

        toolbox = QtWidgets.QGroupBox("Toolbox")
        tool_layout = QtWidgets.QGridLayout(toolbox)
        self.tool_combo = QtWidgets.QComboBox()
        self.tool_combo.setObjectName("animatorsPencilToolCombo")
        for tool_name in TOOL_NAMES:
            self.tool_combo.addItem(_make_tool_icon(tool_name), tool_name)
        self.tool_popup_button = QtWidgets.QToolButton()
        self.tool_popup_button.setObjectName("animatorsPencilToolPopupButton")
        self.tool_popup_button.setText("Drawing Tools")
        self.tool_popup_button.setIcon(_make_tool_icon("Pencil"))
        self.tool_popup_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.tool_popup_button.setPopupMode(_tool_button_popup_mode("InstantPopup"))
        self.tool_popup_button.setMenu(self._build_tool_menu(TOOL_NAMES))
        self.tool_popup_button.setToolTip("Open a Photoshop-style quick menu for pencil, brush, eraser, text, and shape tools.")
        self.shape_popup_button = QtWidgets.QToolButton()
        self.shape_popup_button.setObjectName("animatorsPencilShapePopupButton")
        self.shape_popup_button.setText("Shape Tools")
        self.shape_popup_button.setIcon(_make_tool_icon("Rectangle"))
        self.shape_popup_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.shape_popup_button.setPopupMode(_tool_button_popup_mode("InstantPopup"))
        self.shape_popup_button.setMenu(self._build_tool_menu(SHAPE_TOOL_NAMES))
        self.shape_popup_button.setToolTip("Open line, arrow, rectangle, and ellipse tools with clear icons.")
        self.color_combo = QtWidgets.QComboBox()
        self.color_combo.addItems(list(DEFAULT_COLORS.keys()))
        self.size_spin = QtWidgets.QDoubleSpinBox()
        self.size_spin.setRange(1.0, 24.0)
        self.size_spin.setValue(3.0)
        self.opacity_spin = QtWidgets.QDoubleSpinBox()
        self.opacity_spin.setRange(0.05, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setValue(1.0)
        self.text_field = QtWidgets.QLineEdit("Note")
        self.draw_button = QtWidgets.QPushButton("Stamp Mark")
        self.draw_button.setObjectName("animatorsPencilCreateMarkButton")
        self.draw_button.setIcon(_make_tool_icon("Pencil"))
        self.drag_draw_button = QtWidgets.QPushButton("Drag Draw In Viewport")
        self.drag_draw_button.setObjectName("animatorsPencilDragDrawButton")
        self.drag_draw_button.setIcon(_make_tool_icon("Rectangle", QtGui.QColor("#7BD88F")))
        self.drag_draw_button.setToolTip("Pick a tool, click this, then drag in the Maya viewport. Pencil and Brush follow your stroke. Shapes use drag size.")
        self.marquee_select_button = QtWidgets.QPushButton("Marquee Select Marks")
        self.marquee_select_button.setObjectName("animatorsPencilMarqueeSelectButton")
        self.marquee_select_button.setIcon(_make_tool_icon("Rectangle", QtGui.QColor("#72B7F2")))
        self.marquee_select_button.setToolTip("Click this, then drag a box in the viewport to select pencil marks.")
        self.camera_notes_button = QtWidgets.QToolButton()
        self.camera_notes_button.setObjectName("animatorsPencilCameraNotesMenuButton")
        self.camera_notes_button.setText("Camera Notes")
        self.camera_notes_button.setIcon(_make_tool_icon("Camera", QtGui.QColor("#F6C85F")))
        self.camera_notes_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.camera_notes_button.setPopupMode(_tool_button_popup_mode("InstantPopup"))
        self.camera_notes_button.setToolTip("Create or use a Camera Notes camera. Each pencil mark can key this camera to the exact current view.")
        self.camera_notes_menu = QtWidgets.QMenu(self.camera_notes_button)
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
        tool_layout.addWidget(QtWidgets.QLabel("Tool"), 0, 0)
        tool_layout.addWidget(self.tool_combo, 0, 1)
        tool_layout.addWidget(QtWidgets.QLabel("Color"), 0, 2)
        tool_layout.addWidget(self.color_combo, 0, 3)
        tool_layout.addWidget(self.tool_popup_button, 1, 0, 1, 2)
        tool_layout.addWidget(self.shape_popup_button, 1, 2, 1, 2)
        tool_layout.addWidget(QtWidgets.QLabel("Size"), 2, 0)
        tool_layout.addWidget(self.size_spin, 2, 1)
        tool_layout.addWidget(QtWidgets.QLabel("Opacity"), 2, 2)
        tool_layout.addWidget(self.opacity_spin, 2, 3)
        tool_layout.addWidget(QtWidgets.QLabel("Text"), 3, 0)
        tool_layout.addWidget(self.text_field, 3, 1, 1, 2)
        tool_layout.addWidget(self.draw_button, 3, 3)
        tool_layout.addWidget(self.camera_notes_button, 4, 0, 1, 2)
        tool_layout.addWidget(self.camera_note_box, 4, 2)
        tool_layout.addWidget(self.camera_snap_box, 4, 3)
        tool_layout.addWidget(self.drag_draw_button, 5, 0, 1, 2)
        tool_layout.addWidget(self.marquee_select_button, 5, 2, 1, 2)
        layout.addWidget(toolbox)

        edit_buttons = QtWidgets.QHBoxLayout()
        self.undo_button = QtWidgets.QPushButton("Undo")
        self.redo_button = QtWidgets.QPushButton("Redo")
        self.copy_button = QtWidgets.QPushButton("Copy Selected")
        self.cut_button = QtWidgets.QPushButton("Cut Selected")
        self.paste_button = QtWidgets.QPushButton("Paste")
        self.delete_marks_button = QtWidgets.QPushButton("Erase Selected")
        self.translucent_button = QtWidgets.QPushButton("Toggle Translucent")
        self.translucent_button.setObjectName("animatorsPencilTranslucentToggleButton")
        self.translucent_button.setToolTip("Toggle selected pencil marks into Maya's translucent/template display for quick draw-over review.")
        for button in (self.undo_button, self.redo_button, self.copy_button, self.cut_button, self.paste_button, self.delete_marks_button):
            edit_buttons.addWidget(button)
        edit_buttons.addWidget(self.translucent_button)
        layout.addLayout(edit_buttons)

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
            transform_layout.addWidget(button, i // 4, i % 4)
        transform_layout.addWidget(self.viewport_move_button, 2, 0)
        transform_layout.addWidget(self.viewport_rotate_button, 2, 1)
        transform_layout.addWidget(self.viewport_scale_button, 2, 2)
        transform_layout.addWidget(self.transform_layer_button, 2, 3)
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
            anim_layout.addWidget(button, i // 4, i % 4)
        layout.addWidget(anim)

        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.add_layer_button.clicked.connect(self._add_layer)
        self.open_native_button.clicked.connect(self.controller.open_native_blue_pencil)
        self.native_tool_button.clicked.connect(lambda: self.controller.set_native_tool(self.tool_combo.currentText()))
        self.native_options_button.clicked.connect(lambda: self.controller.apply_native_options(self.tool_combo.currentText(), self._current_color(), self.size_spin.value(), self.opacity_spin.value()))
        self.native_insert_button.clicked.connect(lambda: self.controller.native_frame_command("insert"))
        self.native_duplicate_button.clicked.connect(lambda: self.controller.native_frame_command("duplicate"))
        self.native_delete_button.clicked.connect(lambda: self.controller.native_frame_command("delete"))
        self.native_ghost_button.clicked.connect(self.controller.configure_native_ghosting)
        self.delete_layer_button.clicked.connect(self._delete_layer)
        self.layer_table.itemSelectionChanged.connect(self._layer_selection_changed)
        self.layer_table.customContextMenuRequested.connect(self._show_layer_menu)
        self.state_combo.currentTextChanged.connect(self._set_layer_state)
        self.layer_up_button.clicked.connect(lambda: self._move_layer(-1))
        self.layer_down_button.clicked.connect(lambda: self._move_layer(1))
        self.move_camera_button.clicked.connect(self._move_layer_to_camera)
        self.draw_button.clicked.connect(self._create_mark)
        self.drag_draw_button.clicked.connect(self._activate_drag_draw)
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
                shortcut_context = _qt_flag("ShortcutContext", "WidgetWithChildrenShortcut")
                if shortcut_context is not None:
                    shortcut.setContext(shortcut_context)
                shortcut.setAutoRepeat(False)
                shortcut.activated.connect(lambda _callback=callback: self._run_panel_shortcut(_callback))
                self._shortcuts[action_name] = shortcut
            except Exception:
                continue

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
            self.tool_combo.setCurrentIndex(index)
        self._tool_changed(tool_name)

    def _tool_changed(self, tool_name):
        icon = _make_tool_icon(tool_name)
        self.draw_button.setIcon(icon)
        self.tool_popup_button.setIcon(icon)
        self.drag_draw_button.setIcon(icon)
        self.draw_button.setToolTip("Stamp a default {0} mark on the active pencil layer.".format(tool_name))
        if tool_name in ("Pencil", "Brush"):
            self.drag_draw_button.setToolTip("Drag in the viewport to draw a freehand {0} stroke.".format(tool_name))
        else:
            self.drag_draw_button.setToolTip("Drag in the viewport to draw a {0} mark at the size you want.".format(tool_name))

    def _create_camera_notes_camera(self):
        camera = self.controller.camera_notes_camera(create=True)
        self._set_status("Camera Notes camera ready: {0}".format(camera or "not created"))

    def _key_camera_notes_camera(self):
        camera = self.controller.key_camera_notes_to_current_view(snap=self.camera_snap_box.isChecked(), switch_to_camera=False)
        self._set_status("Camera Notes keyed: {0}".format(camera or "not keyed"))

    def _switch_to_camera_notes(self):
        camera = self.controller.switch_to_camera_notes()
        self._set_status("Looking through Camera Notes: {0}".format(camera or "not available"))

    def _set_status(self, message):
        self.status_label.setText(message)

    def _after_action(self, _result=None):
        self.refresh_layers()

    def _current_color(self):
        return DEFAULT_COLORS.get(self.color_combo.currentText(), DEFAULT_COLORS["Red"])

    def refresh_layers(self):
        layers = self.controller.layers() if MAYA_AVAILABLE else []
        self.layer_table.blockSignals(True)
        self.layer_table.setRowCount(len(layers))
        for row, layer in enumerate(layers):
            for col, value in enumerate((layer.get("name"), layer.get("camera"), layer.get("state"), "Yes" if layer.get("locked") else "No", str(layer.get("count", 0)))):
                item = QtWidgets.QTableWidgetItem(value or "")
                item.setData(_qt_flag("ItemDataRole", "UserRole", QtCore.Qt.UserRole), layer.get("node"))
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
        else:
            self.current_layer = ""

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

    def _add_layer(self):
        self.current_layer = self.controller.create_layer(self.layer_name.text() or "Pencil Layer")
        self.refresh_layers()

    def _delete_layer(self):
        layer = self._selected_layer_from_table()
        if not layer:
            return
        result = QtWidgets.QMessageBox.question(self, "Delete Layer", "Delete this pencil layer and all marks inside it?")
        if result == QtWidgets.QMessageBox.Yes:
            self.controller.delete_layer(layer)
            self.refresh_layers()

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
        mark = self.controller.create_mark(
            tool=self.tool_combo.currentText(),
            layer_node=self.current_layer,
            color=self._current_color(),
            size=self.size_spin.value(),
            opacity=self.opacity_spin.value(),
            text=self.text_field.text(),
            camera_note=self.camera_note_box.isChecked(),
            camera_snap=self.camera_snap_box.isChecked(),
        )
        self._after_action(mark)

    def _activate_drag_draw(self):
        self.controller.activate_drag_draw_context(
            tool=self.tool_combo.currentText(),
            layer_node=self.current_layer,
            color=self._current_color(),
            size=self.size_spin.value(),
            opacity=self.opacity_spin.value(),
            text=self.text_field.text(),
            camera_note=self.camera_note_box.isChecked(),
            camera_snap=self.camera_snap_box.isChecked(),
        )

    def _activate_marquee_select(self):
        self.controller.activate_marquee_select_context(layer_node=self.current_layer, add=False)

    def _show_layer_menu(self, position):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Set Active Layer", self._layer_selection_changed)
        menu.addAction("Add Layer", self._add_layer)
        menu.addAction("Delete Layer", self._delete_layer)
        menu.addSeparator()
        menu.addAction("Layer Up", lambda: self._move_layer(-1))
        menu.addAction("Layer Down", lambda: self._move_layer(1))
        menu.addAction("Move Layer To Current Camera", self._move_layer_to_camera)
        menu.exec_(self.layer_table.mapToGlobal(position))


class AnimatorsPencilWindow(QtWidgets.QDialog):
    def __init__(self, controller=None, parent=None):
        super(AnimatorsPencilWindow, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Animators Pencil")
        self.controller = controller or AnimatorsPencilController()
        layout = QtWidgets.QVBoxLayout(self)
        self.panel = AnimatorsPencilPanel(self.controller, self)
        layout.addWidget(self.panel)
        self.resize(760, 760)


GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


def launch_animators_pencil():
    global GLOBAL_CONTROLLER, GLOBAL_WINDOW
    if GLOBAL_WINDOW:
        try:
            GLOBAL_WINDOW.close()
        except Exception:
            pass
    GLOBAL_CONTROLLER = AnimatorsPencilController()
    GLOBAL_WINDOW = AnimatorsPencilWindow(GLOBAL_CONTROLLER)
    GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


def run_smoke_scene():
    if not MAYA_AVAILABLE:
        return {"available": False}
    for layer_info in AnimatorsPencilController().layers():
        if layer_info.get("name") == "Smoke Layer" and cmds.objExists(layer_info.get("node")):
            cmds.delete(layer_info.get("node"))
    if cmds.objExists("amirAnimatorsPencilGhosts_GRP"):
        cmds.delete("amirAnimatorsPencilGhosts_GRP")
    smoke_camera = "amirPencilSmokeView_CAM"
    if cmds.objExists(smoke_camera):
        cmds.delete(smoke_camera)
    smoke_camera, _smoke_shape = cmds.camera(name=smoke_camera)
    cmds.xform(smoke_camera, worldSpace=True, translation=(3.0, 4.0, 12.0), rotation=(-5.0, 20.0, 0.0))
    _set_camera_for_model_panels(smoke_camera)
    controller = AnimatorsPencilController()
    layer = controller.create_layer("Smoke Layer", camera=smoke_camera, state="Animation")
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
    marquee_selected = controller.select_marks_in_box(layer, (-1.35, -0.3, 0.0), (-0.05, 0.95, 0.0))
    cmds.select(line, replace=True)
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
        for shape in _mark_shapes(line)
        if cmds.objExists(shape + ".overrideDisplayType")
    ]
    translucent_off = controller.toggle_marks_translucent(layer)
    opaque_display_types = [
        int(cmds.getAttr(shape + ".overrideDisplayType"))
        for shape in _mark_shapes(line)
        if cmds.objExists(shape + ".overrideDisplayType")
    ]
    text = controller.create_mark("Text", layer, DEFAULT_COLORS["White"], 2.0, 1.0, text="Animators Pencil")
    delete_target = controller.create_mark("Line", layer, DEFAULT_COLORS["Black"], 2.0, 1.0)
    cmds.select(delete_target, replace=True)
    controller.delete_selected_marks()
    controller.add_key()
    dupes = controller.duplicate_previous_key(layer)
    ghosts = controller.make_ghosts(layer, before=3, after=3)
    notes_camera = controller.camera_notes_camera(create=False)
    camera_note_keys = sorted({int(round(float(value))) for value in (cmds.keyframe(notes_camera, query=True, timeChange=True) or [])}) if notes_camera and cmds.objExists(notes_camera) else []
    data = {
        "root_exists": cmds.objExists(ROOT_GROUP_NAME),
        "layer": layer,
        "line": line,
        "rect": rect,
        "dragged_rect": dragged_rect,
        "dragged_ellipse": dragged_ellipse,
        "freehand": freehand,
        "freehand_point_count": _get_json_attr(freehand, "animatorsPencilMarkData", {}).get("freehandPointCount") if freehand and cmds.objExists(freehand) else 0,
        "marquee_select_count": len(marquee_selected),
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
        "dupe_count": len(dupes),
        "ghost_exists": cmds.objExists(ghosts),
        "mark_count": len(controller.marks(layer)),
        "scene_native_mark_shapes": len(cmds.listRelatives(layer, allDescendents=True, type="nurbsCurve") or []),
        "layer_data": controller.layer_data(layer),
        "shape_tool_names": list(SHAPE_TOOL_NAMES),
        "camera_notes_exists": bool(notes_camera and cmds.objExists(notes_camera)),
        "camera_notes_key_frames": camera_note_keys,
        "camera_notes_line_link": _get_string_attr(line, "animatorsPencilCameraNotesCamera", "") if line and cmds.objExists(line) else "",
    }
    return data


if __name__ == "__main__":
    launch_animators_pencil()
