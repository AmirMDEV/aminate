from __future__ import absolute_import, division, print_function

import json
import math

try:
    import maya.cmds as cmds
    import maya.OpenMayaUI as omui
    import maya.api.OpenMaya as om

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    omui = None
    om = None
    MAYA_AVAILABLE = False

try:
    from PySide2 import QtCore, QtWidgets
    import shiboken2 as shiboken
except Exception:
    try:
        from PySide6 import QtCore, QtWidgets
        import shiboken6 as shiboken
    except Exception:
        QtCore = None
        QtWidgets = None
        shiboken = None


_QtObjectBase = QtCore.QObject if QtCore else object
_QtFrameBase = QtWidgets.QFrame if QtWidgets else object
_QtWidgetBase = QtWidgets.QWidget if QtWidgets else object


WINDOW_OBJECT_NAME = "mayaAnimationAssistantWindow"
ASSISTANT_ENABLED_OPTION = "AminateAnimationAssistantBalanceEnabled"
ASSISTANT_FLOOR_OPTION = "AminateAnimationAssistantFloorNode"
ASSISTANT_COG_OPTION = "AminateAnimationAssistantCogNode"
ASSISTANT_CONTACTS_OPTION = "AminateAnimationAssistantContactNodes"
ASSISTANT_THRESHOLD_OPTION = "AminateAnimationAssistantContactThreshold"

DEFAULT_ENABLED = False
DEFAULT_CONTACT_THRESHOLD = 0.5
MIN_CONTACT_THRESHOLD = 0.001
MAX_CONTACT_THRESHOLD = 1000.0

BALANCE_HELPER_ROOT = "aminateAnimationAssistant_GRP"
BALANCE_SUPPORT_CURVE = "aminateBalanceSupport_CRV"
BALANCE_SUPPORT_FILL = "aminateBalanceSupport_FACET"
BALANCE_COG_LINE = "aminateBalanceCogLine_CRV"
BALANCE_SHADER = "aminateBalanceSupport_MAT"
BALANCE_SHADING_GROUP = "aminateBalanceSupport_SG"

BALANCED_COLOR = (0.28, 0.85, 0.49)
UNBALANCED_COLOR = (0.94, 0.28, 0.28)
BADGE_OBJECT_NAME = "aminatePoseBalanceBadge"
REFRESH_INTERVAL_MS = 33


def _qt_object_valid(widget):
    if widget is None:
        return False
    if shiboken is not None and hasattr(shiboken, "isValid"):
        try:
            return bool(shiboken.isValid(widget))
        except Exception:
            return False
    try:
        widget.objectName()
        return True
    except Exception:
        return False


def _option_var_bool(option_name, default):
    if not cmds or not cmds.optionVar(exists=option_name):
        return bool(default)
    try:
        return bool(cmds.optionVar(query=option_name))
    except Exception:
        return bool(default)


def _option_var_float(option_name, default):
    if not cmds or not cmds.optionVar(exists=option_name):
        return float(default)
    try:
        return float(cmds.optionVar(query=option_name))
    except Exception:
        return float(default)


def _option_var_string(option_name, default=""):
    if not cmds or not cmds.optionVar(exists=option_name):
        return str(default or "")
    try:
        return str(cmds.optionVar(query=option_name) or "")
    except Exception:
        return str(default or "")


def _save_option_var_bool(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(intValue=(option_name, int(bool(value))))
    except Exception:
        pass


def _save_option_var_float(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(floatValue=(option_name, float(value)))
    except Exception:
        pass


def _save_option_var_string(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(stringValue=(option_name, str(value or "")))
    except Exception:
        pass


def _option_var_json_list(option_name):
    raw_value = _option_var_string(option_name, "[]")
    try:
        value = json.loads(raw_value)
    except Exception:
        value = []
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not item:
            continue
        result.append(str(item))
    return result


def _save_option_var_json_list(option_name, values):
    _save_option_var_string(option_name, json.dumps([str(item) for item in (values or []) if item]))


def _clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def _short_name(node_name):
    return (node_name or "").split("|")[-1]


def _dedupe(items):
    result = []
    seen = set()
    for item in items or []:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _node_exists(node_name):
    return bool(cmds and node_name and cmds.objExists(node_name))


def _existing_nodes(node_names):
    return [node_name for node_name in _dedupe(node_names or []) if _node_exists(node_name)]


def _model_panel_names():
    if not cmds:
        return []
    try:
        return cmds.getPanel(type="modelPanel") or []
    except Exception:
        return []


def _panel_widget(panel_name):
    if not (QtWidgets and omui and shiboken and cmds and panel_name):
        return None
    try:
        if cmds.getPanel(typeOf=panel_name) != "modelPanel":
            return None
    except Exception:
        return None
    pointer = None
    for finder in (omui.MQtUtil.findControl, omui.MQtUtil.findLayout):
        try:
            pointer = finder(panel_name)
        except Exception:
            pointer = None
        if pointer:
            break
    if not pointer:
        return None
    try:
        return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)
    except Exception:
        return None


def _overlay_host_widget(panel_name):
    root_widget = _panel_widget(panel_name)
    if root_widget is None or not QtWidgets:
        return None
    best_widget = root_widget
    best_score = -1
    candidates = [root_widget] + list(root_widget.findChildren(QtWidgets.QWidget))
    for widget in candidates:
        if widget is None:
            continue
        try:
            if widget.objectName() == BADGE_OBJECT_NAME:
                continue
            if not widget.isVisible():
                continue
            width = int(widget.width())
            height = int(widget.height())
            if width < 40 or height < 40:
                continue
            area = width * height
            class_name = widget.metaObject().className().lower()
            object_name = (widget.objectName() or "").lower()
            score = area
            if "model" in class_name or "viewport" in class_name or "gl" in class_name:
                score += 5000000
            if "model" in object_name or "viewport" in object_name or "view" in object_name:
                score += 2500000
            if widget is root_widget:
                score -= 10000000
            if score > best_score:
                best_score = score
                best_widget = widget
        except Exception:
            continue
    return best_widget


def _qt_object_id(widget):
    if widget is None:
        return None
    try:
        if shiboken:
            pointer_data = shiboken.getCppPointer(widget)
            if pointer_data:
                return int(pointer_data[0])
    except Exception:
        pass
    try:
        return int(id(widget))
    except Exception:
        return None


def _purge_badge_widgets(widget, keep_badge=None):
    if widget is None or not QtWidgets:
        return
    keep_id = _qt_object_id(keep_badge)
    seen = set()
    for badge in widget.findChildren(QtWidgets.QWidget, BADGE_OBJECT_NAME):
        badge_id = _qt_object_id(badge)
        if badge_id in seen:
            continue
        seen.add(badge_id)
        if keep_id is not None and badge_id == keep_id:
            continue
        try:
            badge.hide()
            badge.deleteLater()
        except Exception:
            pass


def _vector_add(a_value, b_value):
    return [float(a_value[0]) + float(b_value[0]), float(a_value[1]) + float(b_value[1]), float(a_value[2]) + float(b_value[2])]


def _vector_sub(a_value, b_value):
    return [float(a_value[0]) - float(b_value[0]), float(a_value[1]) - float(b_value[1]), float(a_value[2]) - float(b_value[2])]


def _vector_dot(a_value, b_value):
    return (float(a_value[0]) * float(b_value[0])) + (float(a_value[1]) * float(b_value[1])) + (float(a_value[2]) * float(b_value[2]))


def _vector_cross(a_value, b_value):
    return [
        (float(a_value[1]) * float(b_value[2])) - (float(a_value[2]) * float(b_value[1])),
        (float(a_value[2]) * float(b_value[0])) - (float(a_value[0]) * float(b_value[2])),
        (float(a_value[0]) * float(b_value[1])) - (float(a_value[1]) * float(b_value[0])),
    ]


def _vector_length(value):
    return math.sqrt(max(0.0, _vector_dot(value, value)))


def _vector_normalize(value, fallback=None):
    fallback = fallback or [0.0, 1.0, 0.0]
    length = _vector_length(value)
    if length <= 1.0e-8:
        return [float(fallback[0]), float(fallback[1]), float(fallback[2])]
    return [float(value[0]) / length, float(value[1]) / length, float(value[2]) / length]


def _plane_signed_distance(point, plane_point, plane_normal):
    return _vector_dot(_vector_sub(point, plane_point), plane_normal)


def _project_point_to_plane(point, plane_point, plane_normal):
    distance = _plane_signed_distance(point, plane_point, plane_normal)
    return _vector_sub(point, [plane_normal[0] * distance, plane_normal[1] * distance, plane_normal[2] * distance])


def _plane_basis(plane_normal):
    normal = _vector_normalize(plane_normal, fallback=[0.0, 1.0, 0.0])
    reference = [0.0, 1.0, 0.0] if abs(_vector_dot(normal, [0.0, 1.0, 0.0])) < 0.98 else [1.0, 0.0, 0.0]
    axis_u = _vector_normalize(_vector_cross(reference, normal), fallback=[1.0, 0.0, 0.0])
    axis_v = _vector_normalize(_vector_cross(normal, axis_u), fallback=[0.0, 0.0, 1.0])
    return axis_u, axis_v


def _plane_to_2d(point, plane_point, axis_u, axis_v):
    offset = _vector_sub(point, plane_point)
    return [_vector_dot(offset, axis_u), _vector_dot(offset, axis_v)]


def _line_plane_intersection(point, direction, plane_point, plane_normal):
    denominator = _vector_dot(plane_normal, direction)
    if abs(denominator) <= 1.0e-8:
        return _project_point_to_plane(point, plane_point, plane_normal)
    distance = _vector_dot(plane_normal, _vector_sub(plane_point, point)) / denominator
    return _vector_add(point, [direction[0] * distance, direction[1] * distance, direction[2] * distance])


def _distance_point_to_segment_2d(point, start_point, end_point):
    segment = [end_point[0] - start_point[0], end_point[1] - start_point[1]]
    segment_length_sq = (segment[0] * segment[0]) + (segment[1] * segment[1])
    if segment_length_sq <= 1.0e-8:
        return math.hypot(point[0] - start_point[0], point[1] - start_point[1])
    ratio = ((point[0] - start_point[0]) * segment[0] + (point[1] - start_point[1]) * segment[1]) / segment_length_sq
    ratio = max(0.0, min(1.0, ratio))
    projected = [start_point[0] + (segment[0] * ratio), start_point[1] + (segment[1] * ratio)]
    return math.hypot(point[0] - projected[0], point[1] - projected[1])


def _point_on_polygon_edge_2d(point, polygon_points, tolerance=1.0e-3):
    count = len(polygon_points)
    if count < 2:
        return False
    for index in range(count):
        start_point = polygon_points[index]
        end_point = polygon_points[(index + 1) % count]
        if _distance_point_to_segment_2d(point, start_point, end_point) <= float(tolerance):
            return True
    return False


def _point_in_polygon_2d(point, polygon_points):
    if len(polygon_points) < 3:
        return False
    inside = False
    x_value = float(point[0])
    y_value = float(point[1])
    count = len(polygon_points)
    for index in range(count):
        x1, y1 = polygon_points[index]
        x2, y2 = polygon_points[(index + 1) % count]
        intersects = ((y1 > y_value) != (y2 > y_value))
        if not intersects:
            continue
        denominator = (y2 - y1) if abs(y2 - y1) > 1.0e-8 else 1.0e-8
        cross_x = ((x2 - x1) * (y_value - y1) / denominator) + x1
        if x_value <= cross_x:
            inside = not inside
    return inside


def _convex_hull_2d(points_2d):
    cleaned = []
    seen = set()
    for item in points_2d:
        key = (round(float(item[0]), 6), round(float(item[1]), 6))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append([float(item[0]), float(item[1])])
    cleaned.sort(key=lambda value: (value[0], value[1]))
    if len(cleaned) <= 1:
        return cleaned

    def _cross(origin, point_a, point_b):
        return ((point_a[0] - origin[0]) * (point_b[1] - origin[1])) - ((point_a[1] - origin[1]) * (point_b[0] - origin[0]))

    lower = []
    for point in cleaned:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(cleaned):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _world_position(node_name):
    if not _node_exists(node_name):
        return None
    try:
        position = cmds.xform(node_name, query=True, worldSpace=True, rotatePivot=True)
    except Exception:
        try:
            position = cmds.xform(node_name, query=True, worldSpace=True, translation=True)
        except Exception:
            position = None
    if not position or len(position) < 3:
        return None
    return [float(position[0]), float(position[1]), float(position[2])]


def _mesh_shape(node_name):
    if not _node_exists(node_name):
        return ""
    if cmds.nodeType(node_name) == "mesh":
        return node_name
    shapes = cmds.listRelatives(node_name, shapes=True, noIntermediate=True, fullPath=True) or []
    for shape_name in shapes:
        try:
            if cmds.nodeType(shape_name) == "mesh":
                return shape_name
        except Exception:
            pass
    return ""


def _floor_plane_data(node_name):
    if not _node_exists(node_name):
        return None
    mesh_shape = _mesh_shape(node_name)
    if mesh_shape:
        try:
            vertices = cmds.polyInfo(mesh_shape + ".f[0]", faceToVertex=True) or []
        except Exception:
            vertices = []
        if vertices:
            tokens = vertices[0].replace(":", " ").split()
            vertex_ids = []
            for token in tokens:
                try:
                    vertex_ids.append(int(token))
                except Exception:
                    continue
            if len(vertex_ids) >= 3:
                point_a = cmds.pointPosition("{0}.vtx[{1}]".format(mesh_shape, vertex_ids[0]), world=True)
                point_b = cmds.pointPosition("{0}.vtx[{1}]".format(mesh_shape, vertex_ids[1]), world=True)
                point_c = cmds.pointPosition("{0}.vtx[{1}]".format(mesh_shape, vertex_ids[2]), world=True)
                plane_point = [float(point_a[0]), float(point_a[1]), float(point_a[2])]
                normal = _vector_cross(_vector_sub(point_b, point_a), _vector_sub(point_c, point_a))
                normal = _vector_normalize(normal, fallback=[0.0, 1.0, 0.0])
                return {"point": plane_point, "normal": normal}
    position = _world_position(node_name)
    if position is None:
        return None
    return {"point": position, "normal": [0.0, 1.0, 0.0]}


def _ensure_helper_root():
    if not cmds:
        return ""
    if cmds.objExists(BALANCE_HELPER_ROOT):
        return BALANCE_HELPER_ROOT
    root = cmds.group(empty=True, name=BALANCE_HELPER_ROOT)
    for attr_name, value in (("inheritsTransform", False), ("hiddenInOutliner", True)):
        try:
            cmds.setAttr(root + "." + attr_name, value)
        except Exception:
            pass
    return root


def _delete_helper_node(node_name):
    if cmds and node_name and cmds.objExists(node_name):
        try:
            cmds.delete(node_name)
        except Exception:
            pass


def _ensure_support_shader():
    if not cmds:
        return "", ""
    shader_name = BALANCE_SHADER
    shading_group = BALANCE_SHADING_GROUP
    if not cmds.objExists(shader_name):
        shader_name = cmds.shadingNode("lambert", asShader=True, name=BALANCE_SHADER)
        try:
            cmds.setAttr(shader_name + ".ambientColor", 0.08, 0.08, 0.08, type="double3")
        except Exception:
            pass
    if not cmds.objExists(shading_group):
        shading_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=BALANCE_SHADING_GROUP)
        try:
            cmds.connectAttr(shader_name + ".outColor", shading_group + ".surfaceShader", force=True)
        except Exception:
            pass
    return shader_name, shading_group


def _apply_curve_color(node_name, color):
    if not (cmds and node_name and cmds.objExists(node_name)):
        return
    shapes = cmds.listRelatives(node_name, shapes=True, noIntermediate=True, fullPath=True) or []
    for shape_name in shapes:
        try:
            cmds.setAttr(shape_name + ".overrideEnabled", 1)
            cmds.setAttr(shape_name + ".overrideRGBColors", 1)
            cmds.setAttr(shape_name + ".overrideColorRGB", float(color[0]), float(color[1]), float(color[2]))
            cmds.setAttr(shape_name + ".lineWidth", 2.0)
        except Exception:
            pass


def _apply_fill_color(node_name, color):
    if not (cmds and node_name and cmds.objExists(node_name)):
        return
    shader_name, shading_group = _ensure_support_shader()
    if not shader_name or not shading_group:
        return
    try:
        cmds.setAttr(shader_name + ".color", float(color[0]), float(color[1]), float(color[2]), type="double3")
        cmds.setAttr(shader_name + ".transparency", 0.78, 0.78, 0.78, type="double3")
    except Exception:
        pass
    try:
        cmds.sets(node_name, edit=True, forceElement=shading_group)
    except Exception:
        pass
    shapes = cmds.listRelatives(node_name, shapes=True, noIntermediate=True, fullPath=True) or []
    for shape_name in shapes:
        try:
            cmds.setAttr(shape_name + ".overrideEnabled", 1)
            cmds.setAttr(shape_name + ".overrideShading", 1)
            cmds.setAttr(shape_name + ".castsShadows", 0)
            cmds.setAttr(shape_name + ".receiveShadows", 0)
            cmds.setAttr(shape_name + ".motionBlur", 0)
        except Exception:
            pass


def _create_linear_curve(name, points, closed=False):
    if not cmds:
        return ""
    points = points or []
    if closed and len(points) >= 3:
        points = list(points) + [points[0]]
    if len(points) < 2:
        return ""
    if cmds.objExists(name):
        try:
            cmds.delete(name)
        except Exception:
            pass
    curve_name = cmds.curve(name=name, degree=1, point=points)
    try:
        cmds.parent(curve_name, _ensure_helper_root())
    except Exception:
        pass
    return curve_name


def _create_fill_mesh(name, points):
    if not cmds or len(points or []) < 3:
        return ""
    if cmds.objExists(name):
        try:
            cmds.delete(name)
        except Exception:
            pass
    mesh_name = cmds.polyCreateFacet(point=points, name=name)[0]
    try:
        cmds.parent(mesh_name, _ensure_helper_root())
    except Exception:
        pass
    try:
        cmds.setAttr(mesh_name + ".inheritsTransform", 0)
    except Exception:
        pass
    return mesh_name


class PoseBalanceViewportBadge(_QtFrameBase):
    def __init__(self, parent=None):
        super(PoseBalanceViewportBadge, self).__init__(parent)
        self.setObjectName(BADGE_OBJECT_NAME)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(
            """
            QFrame#aminatePoseBalanceBadge {
                background-color: transparent;
                border: none;
            }
            QLabel {
                color: #F2F2F2;
                font-size: 9px;
                font-weight: 700;
                background-color: transparent;
            }
            QLabel#aminatePoseBalanceDot {
                border-radius: 5px;
                min-width: 10px;
                max-width: 10px;
                min-height: 10px;
                max-height: 10px;
            }
            """
        )
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.dot_label = QtWidgets.QLabel("")
        self.dot_label.setObjectName("aminatePoseBalanceDot")
        self.text_label = QtWidgets.QLabel("Unbalanced")
        layout.addWidget(self.dot_label)
        layout.addWidget(self.text_label)
        self.set_balance_state(False, "Unbalanced")

    def set_balance_state(self, balanced, label_text):
        color_hex = "#48D97A" if balanced else "#FF5A5A"
        self.dot_label.setStyleSheet(
            "QLabel#aminatePoseBalanceDot {{ background-color: {0}; border: 1px solid rgba(255,255,255,65); border-radius: 5px; }}".format(color_hex)
        )
        self.text_label.setText(label_text or ("Balanced" if balanced else "Unbalanced"))
        self.text_label.adjustSize()
        self.adjustSize()


class ViewportBadgeManager(_QtObjectBase):
    def __init__(self, parent=None):
        super(ViewportBadgeManager, self).__init__(parent)
        self._badges = {}

    def _release_payload(self, payload):
        widget = payload.get("widget")
        host = payload.get("host")
        badge = payload.get("badge")
        for watched in (widget, host):
            try:
                if watched is not None:
                    watched.removeEventFilter(self)
            except Exception:
                pass
        try:
            if badge is not None:
                badge.hide()
                badge.deleteLater()
        except Exception:
            pass

    def clear(self):
        for panel_name, payload in list(self._badges.items()):
            self._release_payload(payload)
        self._badges = {}

    def _ensure_badge(self, panel_name):
        widget = _panel_widget(panel_name)
        host = _overlay_host_widget(panel_name)
        if widget is None or host is None:
            return None
        payload = self._badges.get(panel_name)
        widget_id = _qt_object_id(widget)
        host_id = _qt_object_id(host)
        if payload:
            payload_widget_id = payload.get("widget_id")
            payload_host_id = payload.get("host_id")
            payload_badge = payload.get("badge")
            if payload_widget_id == widget_id and payload_host_id == host_id and payload_badge is not None:
                _purge_badge_widgets(widget, keep_badge=payload_badge)
                if host is not widget:
                    _purge_badge_widgets(host, keep_badge=payload_badge)
                return payload_badge
        if payload:
            self._release_payload(payload)
        _purge_badge_widgets(widget)
        if host is not widget:
            _purge_badge_widgets(host)
        badge = PoseBalanceViewportBadge(host)
        badge.hide()
        for watched in (widget, host):
            try:
                watched.installEventFilter(self)
            except Exception:
                pass
        self._badges[panel_name] = {
            "widget": widget,
            "host": host,
            "badge": badge,
            "widget_id": widget_id,
            "host_id": host_id,
        }
        return badge

    def _position_badge(self, panel_name):
        payload = self._badges.get(panel_name) or {}
        widget = payload.get("host") or payload.get("widget")
        badge = payload.get("badge")
        if not _qt_object_valid(widget) or not _qt_object_valid(badge):
            payload = self._badges.pop(panel_name, None)
            if payload:
                self._release_payload(payload)
            return
        try:
            x_pos = max(8, widget.width() - badge.width() - 12)
            y_pos = max(8, widget.height() - badge.height() - 12)
            badge.move(int(x_pos), int(y_pos))
        except RuntimeError:
            payload = self._badges.pop(panel_name, None)
            if payload:
                self._release_payload(payload)

    def update_state(self, visible, balanced, label_text):
        active_panels = set(_model_panel_names())
        for panel_name in list(self._badges.keys()):
            if panel_name not in active_panels:
                payload = self._badges.pop(panel_name, {})
                self._release_payload(payload)
        for panel_name in sorted(active_panels):
            badge = self._ensure_badge(panel_name)
            if badge is None:
                continue
            payload = self._badges.get(panel_name) or {}
            host = payload.get("host") or payload.get("widget")
            if not _qt_object_valid(host) or not _qt_object_valid(badge):
                payload = self._badges.pop(panel_name, None)
                if payload:
                    self._release_payload(payload)
                continue
            badge.set_balance_state(bool(balanced), label_text)
            self._position_badge(panel_name)
            if visible and host is not None and host.isVisible():
                badge.show()
                try:
                    badge.raise_()
                except Exception:
                    pass
            else:
                badge.hide()

    def eventFilter(self, watched, event):
        try:
            if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show, QtCore.QEvent.Move):
                for panel_name, payload in self._badges.items():
                    watched_id = _qt_object_id(watched)
                    if watched_id in (payload.get("widget_id"), payload.get("host_id")):
                        self._position_badge(panel_name)
                        break
        except Exception:
            pass
        return super(ViewportBadgeManager, self).eventFilter(watched, event)


class AnimationAssistantController(object):
    def __init__(self):
        self.enabled = _option_var_bool(ASSISTANT_ENABLED_OPTION, DEFAULT_ENABLED)
        self.floor_node = _option_var_string(ASSISTANT_FLOOR_OPTION, "")
        self.cog_node = _option_var_string(ASSISTANT_COG_OPTION, "")
        self.contact_nodes = _existing_nodes(_option_var_json_list(ASSISTANT_CONTACTS_OPTION))
        self.contact_threshold = _clamp(_option_var_float(ASSISTANT_THRESHOLD_OPTION, DEFAULT_CONTACT_THRESHOLD), MIN_CONTACT_THRESHOLD, MAX_CONTACT_THRESHOLD)
        self.status_callback = None
        self._overlay_manager = ViewportBadgeManager() if QtCore and QtWidgets else None
        self._time_job_id = None
        self._watch_callback_ids = []
        self._last_signature = None
        self._refresh_timer = None
        self._pending_force_refresh = False
        if QtCore:
            self._refresh_timer = QtCore.QTimer()
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.setInterval(REFRESH_INTERVAL_MS)
            self._refresh_timer.timeout.connect(self._flush_scheduled_refresh)
        if self.enabled:
            self.start_monitoring()

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _emit_status(self, message, success=True):
        if self.status_callback:
            self.status_callback(message, success)

    def shutdown(self):
        self.stop_monitoring()

    def start_monitoring(self):
        if not MAYA_AVAILABLE or not cmds:
            return
        if self._time_job_id is None:
            try:
                self._time_job_id = cmds.scriptJob(event=["timeChanged", self._on_time_changed], protected=True)
            except Exception:
                self._time_job_id = None
        self._rebuild_watch_jobs()
        self.refresh_visuals(force=True)

    def stop_monitoring(self):
        self._kill_job(self._time_job_id)
        self._time_job_id = None
        self._clear_watch_callbacks()
        if self._refresh_timer:
            self._refresh_timer.stop()
        self._pending_force_refresh = False
        self._last_signature = None
        self._clear_visuals()

    def _kill_job(self, job_id):
        if job_id is None or not cmds:
            return
        try:
            if cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        except Exception:
            pass

    def _clear_watch_callbacks(self):
        if not om:
            self._watch_callback_ids = []
            return
        for callback_id in self._watch_callback_ids:
            try:
                om.MMessage.removeCallback(callback_id)
            except Exception:
                pass
        self._watch_callback_ids = []

    def _watch_targets(self):
        targets = []
        for node_name in [self.floor_node, self.cog_node] + list(self.contact_nodes):
            if not _node_exists(node_name):
                continue
            transform_node = node_name
            try:
                if cmds.nodeType(transform_node) != "transform":
                    parents = cmds.listRelatives(transform_node, parent=True, fullPath=True) or []
                    if parents:
                        transform_node = parents[0]
            except Exception:
                pass
            if _node_exists(transform_node):
                targets.append(transform_node)
        return _dedupe(targets)

    def _mobject_for_node(self, node_name):
        if not om or not node_name or not _node_exists(node_name):
            return None
        try:
            selection = om.MSelectionList()
            selection.add(node_name)
            return selection.getDependNode(0)
        except Exception:
            return None

    def _rebuild_watch_jobs(self):
        self._clear_watch_callbacks()
        if not self.enabled or not cmds or not om:
            return
        for node_name in self._watch_targets():
            mobject = self._mobject_for_node(node_name)
            if mobject is None:
                continue
            try:
                callback_id = om.MNodeMessage.addNodeDirtyPlugCallback(mobject, self._on_node_dirty)
                self._watch_callback_ids.append(callback_id)
            except Exception:
                continue

    def _schedule_refresh(self, force=False):
        if force:
            self._pending_force_refresh = True
        if self._refresh_timer:
            self._refresh_timer.start(REFRESH_INTERVAL_MS)
        else:
            self.refresh_visuals(force=force)

    def _flush_scheduled_refresh(self):
        force = bool(self._pending_force_refresh)
        self._pending_force_refresh = False
        self.refresh_visuals(force=force)

    def _on_time_changed(self):
        self._schedule_refresh()

    def _on_transform_changed(self):
        self._schedule_refresh()

    def _on_node_dirty(self, *args):
        self._schedule_refresh()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        _save_option_var_bool(ASSISTANT_ENABLED_OPTION, self.enabled)
        if self.enabled:
            self.start_monitoring()
            message = "Pose balance overlay is on."
        else:
            self.stop_monitoring()
            message = "Pose balance overlay is off."
        self._emit_status(message, True)
        return True, message

    def set_floor_from_selection(self):
        selection = cmds.ls(selection=True, long=True) or []
        if not selection:
            return False, "Select the floor plane first."
        self.floor_node = selection[0]
        _save_option_var_string(ASSISTANT_FLOOR_OPTION, self.floor_node)
        self._rebuild_watch_jobs()
        self.refresh_visuals(force=True)
        message = "Floor plane set to {0}.".format(_short_name(self.floor_node))
        self._emit_status(message, True)
        return True, message

    def set_cog_from_selection(self):
        selection = cmds.ls(selection=True, long=True) or []
        if not selection:
            return False, "Select the center of gravity control first."
        self.cog_node = selection[0]
        _save_option_var_string(ASSISTANT_COG_OPTION, self.cog_node)
        self._rebuild_watch_jobs()
        self.refresh_visuals(force=True)
        message = "Center of gravity set to {0}.".format(_short_name(self.cog_node))
        self._emit_status(message, True)
        return True, message

    def add_selected_contact_points(self):
        selection = cmds.ls(selection=True, long=True) or []
        if not selection:
            return False, "Select one or more contact points first."
        self.contact_nodes = _existing_nodes(self.contact_nodes + selection)
        _save_option_var_json_list(ASSISTANT_CONTACTS_OPTION, self.contact_nodes)
        self._rebuild_watch_jobs()
        self.refresh_visuals(force=True)
        message = "Added {0} contact point(s).".format(len(selection))
        self._emit_status(message, True)
        return True, message

    def remove_contact_points(self, node_names):
        node_names = set(_existing_nodes(node_names or []))
        if not node_names:
            return False, "Pick contact points from the list first."
        self.contact_nodes = [node_name for node_name in self.contact_nodes if node_name not in node_names]
        _save_option_var_json_list(ASSISTANT_CONTACTS_OPTION, self.contact_nodes)
        self._rebuild_watch_jobs()
        self.refresh_visuals(force=True)
        message = "Removed {0} contact point(s).".format(len(node_names))
        self._emit_status(message, True)
        return True, message

    def clear_contact_points(self):
        self.contact_nodes = []
        _save_option_var_json_list(ASSISTANT_CONTACTS_OPTION, self.contact_nodes)
        self._rebuild_watch_jobs()
        self.refresh_visuals(force=True)
        message = "Cleared all contact points."
        self._emit_status(message, True)
        return True, message

    def set_contact_threshold(self, value):
        self.contact_threshold = _clamp(value, MIN_CONTACT_THRESHOLD, MAX_CONTACT_THRESHOLD)
        _save_option_var_float(ASSISTANT_THRESHOLD_OPTION, self.contact_threshold)
        self.refresh_visuals(force=True)
        message = "Contact threshold set to {0:.3f}.".format(self.contact_threshold)
        self._emit_status(message, True)
        return True, message

    def current_configuration(self):
        return {
            "enabled": bool(self.enabled),
            "floor_node": self.floor_node if _node_exists(self.floor_node) else "",
            "cog_node": self.cog_node if _node_exists(self.cog_node) else "",
            "contact_nodes": _existing_nodes(self.contact_nodes),
            "contact_threshold": float(self.contact_threshold),
        }

    def evaluate_balance(self):
        floor_node = self.floor_node if _node_exists(self.floor_node) else ""
        cog_node = self.cog_node if _node_exists(self.cog_node) else ""
        contact_nodes = _existing_nodes(self.contact_nodes)
        if not floor_node:
            return {"ready": False, "message": "Pick a floor plane.", "balanced": False, "active_contacts": [], "all_contacts": contact_nodes}
        if not cog_node:
            return {"ready": False, "message": "Pick a center of gravity control.", "balanced": False, "active_contacts": [], "all_contacts": contact_nodes}
        if not contact_nodes:
            return {"ready": False, "message": "Add at least one contact point.", "balanced": False, "active_contacts": [], "all_contacts": []}
        floor_data = _floor_plane_data(floor_node)
        cog_position = _world_position(cog_node)
        if not floor_data or cog_position is None:
            return {"ready": False, "message": "Could not read the floor plane or center of gravity.", "balanced": False, "active_contacts": [], "all_contacts": contact_nodes}
        plane_point = floor_data["point"]
        plane_normal = _vector_normalize(floor_data["normal"], fallback=[0.0, 1.0, 0.0])
        axis_u, axis_v = _plane_basis(plane_normal)
        active_contacts = []
        all_contact_points = []
        for node_name in contact_nodes:
            position = _world_position(node_name)
            if position is None:
                continue
            projected = _project_point_to_plane(position, plane_point, plane_normal)
            distance = abs(_plane_signed_distance(position, plane_point, plane_normal))
            contact_data = {
                "node": node_name,
                "position": position,
                "projected": projected,
                "distance": float(distance),
            }
            all_contact_points.append(contact_data)
            if distance <= float(self.contact_threshold):
                active_contacts.append(contact_data)
        cog_projection = _line_plane_intersection(cog_position, [0.0, -1.0, 0.0], plane_point, plane_normal)
        active_points_3d = [item["projected"] for item in active_contacts]
        active_points_2d = [_plane_to_2d(point, plane_point, axis_u, axis_v) for point in active_points_3d]
        cog_projection_2d = _plane_to_2d(cog_projection, plane_point, axis_u, axis_v)
        hull_2d = _convex_hull_2d(active_points_2d)
        hull_3d = []
        for point_2d in hull_2d:
            hull_3d.append(
                _vector_add(
                    plane_point,
                    [
                        (axis_u[0] * point_2d[0]) + (axis_v[0] * point_2d[1]),
                        (axis_u[1] * point_2d[0]) + (axis_v[1] * point_2d[1]),
                        (axis_u[2] * point_2d[0]) + (axis_v[2] * point_2d[1]),
                    ],
                )
            )
        balanced = False
        if len(hull_2d) == 1:
            balanced = math.hypot(cog_projection_2d[0] - hull_2d[0][0], cog_projection_2d[1] - hull_2d[0][1]) <= max(0.001, float(self.contact_threshold))
        elif len(hull_2d) == 2:
            balanced = _distance_point_to_segment_2d(cog_projection_2d, hull_2d[0], hull_2d[1]) <= max(0.001, float(self.contact_threshold))
        elif len(hull_2d) >= 3:
            balanced = _point_on_polygon_edge_2d(cog_projection_2d, hull_2d, tolerance=max(0.001, float(self.contact_threshold))) or _point_in_polygon_2d(cog_projection_2d, hull_2d)
        label_text = "Balanced" if balanced else "Unbalanced"
        message = "{0}  |  {1} active contact(s)".format(label_text, len(active_contacts))
        return {
            "ready": True,
            "message": message,
            "balanced": bool(balanced),
            "label": label_text,
            "plane_point": plane_point,
            "plane_normal": plane_normal,
            "cog_position": cog_position,
            "cog_projection": cog_projection,
            "cog_projection_2d": cog_projection_2d,
            "all_contacts": all_contact_points,
            "active_contacts": active_contacts,
            "support_points_3d": hull_3d,
            "support_points_2d": hull_2d,
        }

    def _clear_visuals(self):
        if self._overlay_manager:
            self._overlay_manager.update_state(False, False, "")
        for node_name in (BALANCE_SUPPORT_CURVE, BALANCE_SUPPORT_FILL, BALANCE_COG_LINE):
            _delete_helper_node(node_name)

    def _signature_from_result(self, result):
        if not result.get("ready"):
            return ("not_ready", result.get("message", ""))
        return (
            bool(result.get("balanced")),
            tuple((round(point[0], 4), round(point[1], 4), round(point[2], 4)) for point in (result.get("support_points_3d") or [])),
            tuple((round(item["projected"][0], 4), round(item["projected"][1], 4), round(item["projected"][2], 4)) for item in (result.get("active_contacts") or [])),
            tuple(round(value, 4) for value in (result.get("cog_position") or [0.0, 0.0, 0.0])),
            tuple(round(value, 4) for value in (result.get("cog_projection") or [0.0, 0.0, 0.0])),
            round(float(self.contact_threshold), 4),
        )

    def _rebuild_helper_geometry(self, result):
        if not result.get("ready"):
            for node_name in (BALANCE_SUPPORT_CURVE, BALANCE_SUPPORT_FILL, BALANCE_COG_LINE):
                _delete_helper_node(node_name)
            return
        color = BALANCED_COLOR if result.get("balanced") else UNBALANCED_COLOR
        support_points = result.get("support_points_3d") or []
        if len(support_points) >= 2:
            curve_name = _create_linear_curve(BALANCE_SUPPORT_CURVE, support_points, closed=(len(support_points) >= 3))
            _apply_curve_color(curve_name, color)
        else:
            _delete_helper_node(BALANCE_SUPPORT_CURVE)
        if len(support_points) >= 3:
            mesh_name = _create_fill_mesh(BALANCE_SUPPORT_FILL, support_points)
            _apply_fill_color(mesh_name, color)
        else:
            _delete_helper_node(BALANCE_SUPPORT_FILL)
        cog_position = result.get("cog_position")
        cog_projection = result.get("cog_projection")
        if cog_position and cog_projection:
            curve_name = _create_linear_curve(BALANCE_COG_LINE, [cog_position, cog_projection], closed=False)
            _apply_curve_color(curve_name, color)
        else:
            _delete_helper_node(BALANCE_COG_LINE)

    def refresh_visuals(self, *args, **kwargs):
        force = bool(kwargs.get("force"))
        if not self.enabled:
            self._clear_visuals()
            return False, "Pose balance overlay is off."
        result = self.evaluate_balance()
        signature = self._signature_from_result(result)
        if force or signature != self._last_signature:
            self._last_signature = signature
            self._rebuild_helper_geometry(result)
        if self._overlay_manager:
            self._overlay_manager.update_state(bool(result.get("ready")), bool(result.get("balanced")), result.get("label") or result.get("message") or "Unbalanced")
        return bool(result.get("ready")), result.get("message") or "Pose balance updated."


class AnimationAssistantPanel(_QtWidgetBase):
    def __init__(self, controller=None, parent=None, status_callback=None):
        super(AnimationAssistantPanel, self).__init__(parent)
        self.controller = controller or AnimationAssistantController()
        self.status_callback = status_callback
        self.controller.set_status_callback(self._set_status)
        self._build_ui()
        self._sync_from_controller()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        setup_group = QtWidgets.QGroupBox("Pose Balance Assistant")
        setup_layout = QtWidgets.QGridLayout(setup_group)
        setup_layout.setHorizontalSpacing(8)
        setup_layout.setVerticalSpacing(6)

        self.enabled_check = QtWidgets.QCheckBox("Show viewport overlay")
        self.enabled_check.setToolTip("Shows a tiny bottom-right red or green balance indicator in every Maya model viewport and draws the support area in the scene.")
        setup_layout.addWidget(self.enabled_check, 0, 0, 1, 3)

        setup_layout.addWidget(QtWidgets.QLabel("Floor Plane"), 1, 0, 1, 2)
        self.floor_line = QtWidgets.QLineEdit()
        self.floor_line.setReadOnly(True)
        self.floor_line.setMinimumWidth(0)
        self.floor_line.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.floor_line.setPlaceholderText("Pick a floor plane mesh or transform.")
        setup_layout.addWidget(self.floor_line, 2, 0)
        self.floor_button = QtWidgets.QPushButton("Use Selected")
        setup_layout.addWidget(self.floor_button, 2, 1)

        setup_layout.addWidget(QtWidgets.QLabel("Center Of Gravity"), 3, 0, 1, 2)
        self.cog_line = QtWidgets.QLineEdit()
        self.cog_line.setReadOnly(True)
        self.cog_line.setMinimumWidth(0)
        self.cog_line.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.cog_line.setPlaceholderText("Pick the center of gravity control.")
        setup_layout.addWidget(self.cog_line, 4, 0)
        self.cog_button = QtWidgets.QPushButton("Use Selected")
        setup_layout.addWidget(self.cog_button, 4, 1)

        setup_layout.addWidget(QtWidgets.QLabel("Contact Threshold"), 5, 0, 1, 2)
        self.threshold_spin = QtWidgets.QDoubleSpinBox()
        self.threshold_spin.setRange(MIN_CONTACT_THRESHOLD, MAX_CONTACT_THRESHOLD)
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setSuffix(" units")
        self.threshold_spin.setToolTip("How close a contact point must be to the floor plane before Aminate counts it as touching.")
        setup_layout.addWidget(self.threshold_spin, 6, 0)
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.setToolTip("Force a pose balance refresh now.")
        setup_layout.addWidget(self.refresh_button, 6, 1)
        self.readiness_label = QtWidgets.QLabel()
        self.readiness_label.setWordWrap(True)
        self.readiness_label.setObjectName("aminateAnimationAssistantReadiness")
        setup_layout.addWidget(self.readiness_label, 7, 0, 1, 2)
        setup_layout.setColumnStretch(0, 1)

        layout.addWidget(setup_group)

        contacts_group = QtWidgets.QGroupBox("Contact Points")
        contacts_layout = QtWidgets.QVBoxLayout(contacts_group)
        self.contacts_list = QtWidgets.QListWidget()
        self.contacts_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.contacts_list.setToolTip("Pick the rig controls that can actually touch the floor plane such as feet or hands.")
        contacts_layout.addWidget(self.contacts_list, 1)
        contact_buttons = QtWidgets.QHBoxLayout()
        self.add_contacts_button = QtWidgets.QPushButton("Add Selected")
        self.remove_contacts_button = QtWidgets.QPushButton("Remove Selected")
        self.clear_contacts_button = QtWidgets.QPushButton("Clear")
        contact_buttons.addWidget(self.add_contacts_button)
        contact_buttons.addWidget(self.remove_contacts_button)
        contact_buttons.addWidget(self.clear_contacts_button)
        contacts_layout.addLayout(contact_buttons)
        layout.addWidget(contacts_group, 1)

        self.help_box = QtWidgets.QPlainTextEdit()
        self.help_box.setReadOnly(True)
        self.help_box.setMinimumHeight(90)
        self.help_box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.help_box.setPlainText(
            "How it works:\n"
            "1. Pick the floor plane.\n"
            "2. Pick the center of gravity control.\n"
            "3. Add every control that can touch the floor, like feet or hands.\n"
            "4. Aminate checks which contact points are touching the floor plane.\n"
            "5. Aminate draws the support line or polygon between active contact points.\n"
            "6. Aminate drops the center of gravity straight down onto the floor plane.\n"
            "7. If that projection lands on the support line or inside the support area, the pose is balanced."
        )
        layout.addWidget(self.help_box)

        self.status_label = QtWidgets.QLabel("Pick a floor plane, a center of gravity control, and contact points.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.enabled_check.toggled.connect(self._toggle_enabled)
        self.floor_button.clicked.connect(self._set_floor)
        self.cog_button.clicked.connect(self._set_cog)
        self.threshold_spin.valueChanged.connect(self._set_threshold)
        self.refresh_button.clicked.connect(self._refresh)
        self.add_contacts_button.clicked.connect(self._add_contacts)
        self.remove_contacts_button.clicked.connect(self._remove_contacts)
        self.clear_contacts_button.clicked.connect(self._clear_contacts)

    def _sync_from_controller(self):
        config = self.controller.current_configuration()
        self.enabled_check.blockSignals(True)
        self.enabled_check.setChecked(bool(config.get("enabled")))
        self.enabled_check.blockSignals(False)
        self.floor_line.setText(_short_name(config.get("floor_node") or ""))
        self.floor_line.setToolTip(config.get("floor_node") or "")
        self.cog_line.setText(_short_name(config.get("cog_node") or ""))
        self.cog_line.setToolTip(config.get("cog_node") or "")
        self.threshold_spin.blockSignals(True)
        self.threshold_spin.setValue(float(config.get("contact_threshold") or DEFAULT_CONTACT_THRESHOLD))
        self.threshold_spin.blockSignals(False)
        self.contacts_list.clear()
        for node_name in config.get("contact_nodes") or []:
            item = QtWidgets.QListWidgetItem(_short_name(node_name))
            item.setData(QtCore.Qt.UserRole, node_name)
            item.setToolTip(node_name)
            self.contacts_list.addItem(item)
        missing = []
        if not config.get("floor_node"):
            missing.append("floor plane")
        if not config.get("cog_node"):
            missing.append("center of gravity")
        if not config.get("contact_nodes"):
            missing.append("contact control(s)")
        if missing:
            self.readiness_label.setText("Setup needed: {0}. Use the selected-object buttons above, then add contact controls.".format(", ".join(missing)))
            self.readiness_label.setStyleSheet("color: #FFD166;")
            self.refresh_button.setEnabled(False)
        else:
            self.readiness_label.setText("Ready: floor, center of gravity, and contact controls are configured.")
            self.readiness_label.setStyleSheet("color: #59D987;")
            self.refresh_button.setEnabled(True)

    def _set_status(self, message, success=True):
        self.status_label.setText(message)
        if self.status_callback:
            self.status_callback(message, success)

    def _toggle_enabled(self, enabled):
        success, message = self.controller.set_enabled(enabled)
        self._set_status(message, success)

    def _set_floor(self):
        success, message = self.controller.set_floor_from_selection()
        self._sync_from_controller()
        self._set_status(message, success)

    def _set_cog(self):
        success, message = self.controller.set_cog_from_selection()
        self._sync_from_controller()
        self._set_status(message, success)

    def _set_threshold(self, value):
        success, message = self.controller.set_contact_threshold(value)
        self._set_status(message, success)

    def _refresh(self):
        success, message = self.controller.refresh_visuals(force=True)
        self._set_status(message, success)

    def _add_contacts(self):
        success, message = self.controller.add_selected_contact_points()
        self._sync_from_controller()
        self._set_status(message, success)

    def _remove_contacts(self):
        selected_nodes = []
        for item in self.contacts_list.selectedItems():
            selected_nodes.append(item.data(QtCore.Qt.UserRole))
        success, message = self.controller.remove_contact_points(selected_nodes)
        self._sync_from_controller()
        self._set_status(message, success)

    def _clear_contacts(self):
        success, message = self.controller.clear_contact_points()
        self._sync_from_controller()
        self._set_status(message, success)


__all__ = [
    "AnimationAssistantController",
    "AnimationAssistantPanel",
]
