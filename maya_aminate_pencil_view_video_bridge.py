"""Retained-session bridge for Animator's Pencil saved-view/video controls.

This module is intentionally independent from ``maya_animators_pencil``.  It
can be imported into an already-open Maya process whose older Pencil classes
are cached, adding only child widgets and signal handlers.  It never reloads
modules, replaces a window, or creates a second Aminate instance.
"""

from __future__ import absolute_import, division, print_function

import time
import os
import types

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.OpenMayaUI as omui

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    mel = None
    omui = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtCore, QtWidgets
    import shiboken6 as shiboken
except Exception:
    try:
        from PySide2 import QtCore, QtWidgets
        import shiboken2 as shiboken
    except Exception:
        QtCore = None
        QtWidgets = None
        shiboken = None


REFERENCE_VIEWER_WINDOW_NAME = "aminatePencilReferenceViewerWindow"
REFERENCE_VIEWER_LAYOUT_NAME = "aminatePencilReferenceViewerLayout"
REFERENCE_VIEWER_PANEL_NAME = "aminatePencilReferenceViewerPanel"
REFERENCE_DISPLAY_MODES = (
    ("Over Main Viewport", "pinned"),
    ("Floating Window", "floating"),
    ("Main Viewport (Legacy)", "main_view"),
)


DRAWING_VIEW_ATTR = "animatorsPencilDrawingView"
DRAWING_VIEW_LABEL_ATTR = "animatorsPencilDrawingViewLabel"
DRAWING_VIEW_SOURCE_ATTR = "animatorsPencilDrawingViewSource"
OVERLAY_PLACEMENT_ATTR = "amirVideoOverlayPlacement"
OVERLAY_SCALE_ATTR = "amirVideoOverlayScale"
VIDEO_OPACITY_ATTR = "amirVideoOpacity"
VIDEO_AUDIO_ENABLED_ATTR = "amirVideoAudioEnabled"
REFERENCE_VIEWER_WINDOW_NAME = "aminatePencilReferenceViewerWindow"
REFERENCE_VIEWER_LAYOUT_NAME = "aminatePencilReferenceViewerLayout"
REFERENCE_VIEWER_PANEL_NAME = "aminatePencilReferenceViewerPanel"


def _qt_valid(widget):
    if widget is None:
        return False
    try:
        import shiboken6

        return bool(shiboken6.isValid(widget))
    except Exception:
        try:
            import shiboken2

            return bool(shiboken2.isValid(widget))
        except Exception:
            try:
                widget.objectName()
                return True
            except Exception:
                return False


def _find_child(parent, object_name, widget_type=None):
    if not _qt_valid(parent):
        return None
    try:
        matches = parent.findChildren(widget_type or QtWidgets.QWidget, object_name)
    except Exception:
        matches = []
    return matches[0] if matches and _qt_valid(matches[0]) else None


def _maya_ui_widget(ui_name):
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


def _model_panel_widget(panel):
    if not (MAYA_AVAILABLE and omui and shiboken and panel):
        return None
    pointer = None
    try:
        view = omui.M3dView()
        omui.M3dView.getM3dViewFromModelPanel(panel, view)
        pointer = view.widget()
    except Exception:
        pointer = None
    try:
        return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
    except Exception:
        return None


class _ReferenceViewerCloseFilter(QtCore.QObject if QtCore else object):
    def __init__(self, viewer, parent=None):
        if QtCore:
            super(_ReferenceViewerCloseFilter, self).__init__(parent)
        self.viewer = viewer

    def eventFilter(self, watched, event):
        close_type = None
        if QtCore:
            close_type = getattr(getattr(QtCore.QEvent, "Type", QtCore.QEvent), "Close", None)
        if close_type is not None and event.type() == close_type:
            try:
                if QtWidgets.QApplication.closingDown():
                    return False
            except Exception:
                pass
            watched.hide()
            event.ignore()
            self.viewer._visible = False
            return True
        return super(_ReferenceViewerCloseFilter, self).eventFilter(watched, event)


class RetainedReferenceViewer(object):
    """One hide-only modelPanel for PIP or floating annotated reference video."""

    def __init__(self):
        self._close_filter = None
        self._visible = False
        self.mode = "pinned"
        self.placement = "top_right"
        self.scale_percent = 38.0
        self.anchor_panel = ""
        self.camera = ""
        self._floating_geometry = None

    def _root(self):
        return _maya_ui_widget(REFERENCE_VIEWER_WINDOW_NAME)

    def exists(self):
        try:
            return bool(
                cmds.window(REFERENCE_VIEWER_WINDOW_NAME, exists=True)
                and cmds.modelPanel(REFERENCE_VIEWER_PANEL_NAME, exists=True)
            )
        except Exception:
            return False

    def ensure(self, camera):
        if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
            return False, "Attach a video first so Aminate knows the Pencil camera."
        window_exists = bool(cmds.window(REFERENCE_VIEWER_WINDOW_NAME, exists=True))
        panel_exists = bool(cmds.modelPanel(REFERENCE_VIEWER_PANEL_NAME, exists=True))
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
            return False, "Could not assign the Pencil camera: {0}".format(exc)
        root = self._root()
        if not _qt_valid(root):
            return False, "Maya created the Reference Viewer but its Qt window is not ready."
        delete_on_close = getattr(getattr(QtCore.Qt, "WidgetAttribute", QtCore.Qt), "WA_DeleteOnClose", None)
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
        self._close_filter = _ReferenceViewerCloseFilter(self, root)
        root.installEventFilter(self._close_filter)
        self.camera = _long_name(camera)
        return True, "Reference Viewer ready."

    def _anchor(self, preferred=""):
        names = []
        if preferred and preferred != REFERENCE_VIEWER_PANEL_NAME:
            names.append(preferred)
        try:
            focused = cmds.getPanel(withFocus=True)
            if focused and focused != REFERENCE_VIEWER_PANEL_NAME:
                names.append(focused)
        except Exception:
            pass
        try:
            names.extend(name for name in (cmds.getPanel(type="modelPanel") or []) if name not in names and name != REFERENCE_VIEWER_PANEL_NAME)
        except Exception:
            pass
        candidates = []
        for name in names:
            try:
                if cmds.getPanel(typeOf=name) != "modelPanel":
                    continue
            except Exception:
                continue
            widget = _model_panel_widget(name)
            if _qt_valid(widget) and widget.isVisible():
                candidates.append((name, widget))
        if preferred:
            for name, widget in candidates:
                if name == preferred:
                    return name, widget
        return max(candidates, key=lambda item: item[1].width() * item[1].height()) if candidates else ("", None)

    def pinned_geometry(self, placement, scale_percent, preferred=""):
        panel, widget = self._anchor(preferred)
        if not _qt_valid(widget):
            return panel, None
        origin = widget.mapToGlobal(QtCore.QPoint(0, 0))
        viewport = QtCore.QRect(origin.x(), origin.y(), max(widget.width(), 1), max(widget.height(), 1))
        placement = str(placement or "top_right")
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

    def show(self, camera, mode="pinned", placement="top_right", scale_percent=38.0, anchor_panel=""):
        success, message = self.ensure(camera)
        if not success:
            return False, message
        root = self._root()
        if self.mode == "floating" and mode != "floating":
            self._floating_geometry = QtCore.QRect(root.geometry())
        self.mode = "floating" if str(mode) == "floating" else "pinned"
        self.placement = str(placement or "top_right")
        self.scale_percent = float(scale_percent)
        panel, geometry = self.pinned_geometry(self.placement, self.scale_percent, anchor_panel)
        if self.mode == "pinned":
            if geometry is None:
                return False, "Could not find the main Maya viewport."
            self.anchor_panel = panel
            root.setGeometry(geometry)
        elif self._floating_geometry is not None:
            size = geometry.size() if geometry is not None else QtCore.QSize(640, 360)
            root.setGeometry(QtCore.QRect(self._floating_geometry.topLeft(), size))
        elif geometry is not None:
            root.resize(geometry.size())
        try:
            cmds.window(REFERENCE_VIEWER_WINDOW_NAME, edit=True, visible=True)
        except Exception:
            root.show()
        # Showing a retained Maya window can restore its previous size. Apply
        # the requested PIP geometry again so Full View never sticks when the
        # user returns to a corner placement.
        if self.mode == "pinned" and geometry is not None:
            root.move(geometry.topLeft())
            root.resize(geometry.size())
        root.raise_()
        self._visible = True
        return True, "Reference Viewer shown."

    def hide(self):
        root = self._root()
        if _qt_valid(root):
            if self.mode == "floating":
                self._floating_geometry = QtCore.QRect(root.geometry())
            root.hide()
        self._visible = False
        return True

    def is_visible(self):
        root = self._root()
        self._visible = bool(_qt_valid(root) and root.isVisible())
        return self._visible

    def sync(self):
        if self.mode != "pinned" or not self.is_visible():
            return False
        panel, geometry = self.pinned_geometry(self.placement, self.scale_percent, self.anchor_panel)
        root = self._root()
        if geometry is None or not _qt_valid(root):
            return False
        self.anchor_panel = panel
        if root.geometry() != geometry:
            root.move(geometry.topLeft())
            root.resize(geometry.size())
        return True


GLOBAL_REFERENCE_VIEWER = None


def _reference_viewer():
    global GLOBAL_REFERENCE_VIEWER
    if GLOBAL_REFERENCE_VIEWER is None:
        GLOBAL_REFERENCE_VIEWER = RetainedReferenceViewer()
    return GLOBAL_REFERENCE_VIEWER


def _set_status(panel, message):
    for name in ("status_label", "video_source_status"):
        label = getattr(panel, name, None)
        if _qt_valid(label):
            try:
                label.setText(str(message))
                return
            except Exception:
                continue


def _string_attr(node, attr, default=""):
    if not MAYA_AVAILABLE or not node or not cmds.objExists(node):
        return default
    try:
        if cmds.attributeQuery(attr, node=node, exists=True):
            return cmds.getAttr(node + "." + attr) or default
    except Exception:
        pass
    return default


def _ensure_string_attr(node, attr):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, dataType="string")


def _ensure_double_attr(node, attr):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, attributeType="double")


def _double_attr(node, attr, default=None):
    if not MAYA_AVAILABLE or not node or not cmds.objExists(node):
        return default
    try:
        if cmds.attributeQuery(attr, node=node, exists=True):
            return float(cmds.getAttr(node + "." + attr))
    except Exception:
        pass
    return default


def _long_name(node):
    if not MAYA_AVAILABLE or not node:
        return node or ""
    try:
        return (cmds.ls(node, long=True) or [node])[0]
    except Exception:
        return node


def _camera_overlay_transform():
    if not MAYA_AVAILABLE:
        return ""
    candidates = []
    for node in cmds.ls(type="transform", long=True) or []:
        if not cmds.attributeQuery(OVERLAY_PLACEMENT_ATTR, node=node, exists=True):
            continue
        placement = str(_string_attr(node, OVERLAY_PLACEMENT_ATTR, "")).lower()
        if placement not in ("full_view", "top_right", "top_left", "bottom_right", "bottom_left"):
            continue
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True, type="imagePlane") or []
        if not shapes:
            continue
        candidates.append((_double_attr(node, "amirVideoOverlayUpdatedAt", 0.0) or 0.0, _long_name(node)))
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1] if candidates else ""


def _overlay_shape(transform):
    if not MAYA_AVAILABLE or not transform or not cmds.objExists(transform):
        return ""
    return (cmds.listRelatives(transform, shapes=True, fullPath=True, type="imagePlane") or [""])[0]


def _current_model_camera():
    if not MAYA_AVAILABLE:
        return ""
    panels = []
    try:
        focused = cmds.getPanel(withFocus=True)
        if focused and cmds.getPanel(typeOf=focused) == "modelPanel":
            panels.append(focused)
    except Exception:
        pass
    try:
        panels.extend(panel for panel in (cmds.getPanel(type="modelPanel") or []) if panel not in panels)
    except Exception:
        pass
    for panel in panels:
        try:
            camera = cmds.modelEditor(panel, query=True, camera=True)
            if camera:
                return _long_name(camera)
        except Exception:
            continue
    return ""


def _visible_main_panel():
    candidates = []
    try:
        focused = cmds.getPanel(withFocus=True)
        if focused and focused != REFERENCE_VIEWER_PANEL_NAME and cmds.getPanel(typeOf=focused) == "modelPanel":
            candidates.append(focused)
    except Exception:
        pass
    try:
        candidates.extend(
            panel for panel in (cmds.getPanel(type="modelPanel") or [])
            if panel != REFERENCE_VIEWER_PANEL_NAME and panel not in candidates
        )
    except Exception:
        pass
    visible = []
    for panel in candidates:
        widget = _model_panel_widget(panel)
        if _qt_valid(widget) and widget.isVisible():
            visible.append((panel, widget.width() * widget.height()))
    return max(visible, key=lambda item: item[1])[0] if visible else (candidates[0] if candidates else "")


def _panel_camera(panel):
    if not panel:
        return ""
    try:
        return _long_name(cmds.modelEditor(panel, query=True, camera=True))
    except Exception:
        return ""


def _restore_main_panel_camera(panel, camera):
    if not panel or panel == REFERENCE_VIEWER_PANEL_NAME or not camera or not cmds.objExists(camera):
        return False
    try:
        cmds.modelPanel(panel, edit=True, camera=camera)
        return _panel_camera(panel) == _long_name(camera)
    except Exception:
        return False


def _switch_visible_model_camera(camera):
    if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
        return False
    camera = _long_name(camera)
    panels = []
    try:
        focused = cmds.getPanel(withFocus=True)
        if focused and cmds.getPanel(typeOf=focused) == "modelPanel":
            panels.append(focused)
    except Exception:
        pass
    try:
        panels.extend(panel for panel in (cmds.getPanel(type="modelPanel") or []) if panel not in panels)
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


def _set_overlay_full_view(transform):
    shape = _overlay_shape(transform)
    if not shape:
        return False
    try:
        current_size_x = float(cmds.getAttr(shape + ".sizeX"))
        current_size_y = float(cmds.getAttr(shape + ".sizeY"))
        current_offset_x = float(cmds.getAttr(shape + ".offsetX"))
        current_offset_y = float(cmds.getAttr(shape + ".offsetY"))
        stored_scale = _double_attr(transform, OVERLAY_SCALE_ATTR, 1.0) or 1.0
        baseline_size_x = _double_attr(transform, "amirVideoOverlayBaselineSizeX", None)
        baseline_size_y = _double_attr(transform, "amirVideoOverlayBaselineSizeY", None)
        baseline_offset_x = _double_attr(transform, "amirVideoOverlayBaselineOffsetX", None)
        baseline_offset_y = _double_attr(transform, "amirVideoOverlayBaselineOffsetY", None)
        placement = _string_attr(transform, OVERLAY_PLACEMENT_ATTR, "full_view")
        corner_x = 1.0 if placement in ("top_right", "bottom_right") else -1.0 if placement in ("top_left", "bottom_left") else 0.0
        corner_y = 1.0 if placement in ("top_right", "top_left") else -1.0 if placement in ("bottom_right", "bottom_left") else 0.0
        if baseline_size_x is None:
            baseline_size_x = current_size_x / max(stored_scale, 0.001)
        if baseline_size_y is None:
            baseline_size_y = current_size_y / max(stored_scale, 0.001)
        if baseline_offset_x is None:
            baseline_offset_x = current_offset_x - corner_x * baseline_size_x * (1.0 - stored_scale) * 0.5
        if baseline_offset_y is None:
            baseline_offset_y = current_offset_y - corner_y * baseline_size_y * (1.0 - stored_scale) * 0.5
        for attr, value in (
            ("amirVideoOverlayBaselineSizeX", baseline_size_x),
            ("amirVideoOverlayBaselineSizeY", baseline_size_y),
            ("amirVideoOverlayBaselineOffsetX", baseline_offset_x),
            ("amirVideoOverlayBaselineOffsetY", baseline_offset_y),
        ):
            _ensure_double_attr(transform, attr)
            cmds.setAttr(transform + "." + attr, float(value))
        cmds.setAttr(shape + ".sizeX", baseline_size_x)
        cmds.setAttr(shape + ".sizeY", baseline_size_y)
        cmds.setAttr(shape + ".offsetX", baseline_offset_x)
        cmds.setAttr(shape + ".offsetY", baseline_offset_y)
        _ensure_string_attr(transform, OVERLAY_PLACEMENT_ATTR)
        _ensure_double_attr(transform, OVERLAY_SCALE_ATTR)
        cmds.setAttr(transform + "." + OVERLAY_PLACEMENT_ATTR, "full_view", type="string")
        cmds.setAttr(transform + "." + OVERLAY_SCALE_ATTR, 1.0)
        return True
    except Exception:
        return False


def _reference_mode(panel):
    combo = getattr(panel, "video_display_combo", None)
    return str(combo.currentData() or "pinned") if _qt_valid(combo) else "pinned"


def _has_native_reference_viewer(panel):
    try:
        import maya_animators_pencil as pencil_module
    except Exception:
        pencil_module = None
    return bool(
        pencil_module is not None
        and hasattr(pencil_module, "AnimatorsPencilReferenceViewer")
        and callable(getattr(panel, "_video_display_changed", None))
        and callable(getattr(panel, "_show_reference_viewer", None))
    )


def _show_reference_for_panel(panel):
    transform = getattr(panel, "_aminate_bridge_overlay_transform", "") or _camera_overlay_transform()
    camera = getattr(panel, "_aminate_bridge_overlay_camera", "") or _overlay_camera(transform)
    if not transform or not camera:
        _set_status(panel, "Attach a video first so Aminate knows the reference camera.")
        return False
    mode = _reference_mode(panel)
    mode_button = getattr(panel, "show_pencil_view_button", None)
    if mode == "main_view":
        _reference_viewer().hide()
        switched = _switch_visible_model_camera(camera)
        if _qt_valid(mode_button):
            mode_button.setText("Switch to Normal Viewport Drawing")
        return switched
    _set_overlay_full_view(transform)
    normal_panel = getattr(panel, "_aminate_bridge_normal_panel", "") or _visible_main_panel()
    normal_camera = getattr(panel, "_aminate_bridge_normal_camera", "")
    if not normal_camera or _long_name(normal_camera) == _long_name(camera):
        normal_camera = _normal_camera_for_overlay(panel, camera, "")
    _restore_main_panel_camera(normal_panel, normal_camera)
    placement = str(panel.video_placement_combo.currentData() or "top_right")
    size = float(panel.video_scale_spin.value())
    success, message = _reference_viewer().show(camera, mode=mode, placement=placement, scale_percent=size, anchor_panel=normal_panel)
    if success:
        panel._aminate_bridge_in_video_mode = False
        panel._aminate_bridge_normal_panel = normal_panel
        panel._aminate_bridge_normal_camera = normal_camera
        _set_status(panel, message + " Perspective remains active.")
        if _qt_valid(mode_button):
            mode_button.setText("Hide Reference Viewer")
    else:
        _set_status(panel, message)
    return success


def _install_reference_drawing_route(panel):
    """Route retained-session drawing to the visible reference camera."""
    if _has_native_reference_viewer(panel):
        return True
    if getattr(panel, "_aminate_reference_drawing_route_installed", False):
        return True
    route_name = "_ensure_video_pencil_view_for_current_action"
    original = getattr(panel, route_name, None)
    if not callable(original):
        route_name = "_ensure_drawing_view_for_current_action"
        original = getattr(panel, route_name, None)
    controller = getattr(panel, "controller", None)
    if not callable(original) or controller is None:
        return False
    panel._aminate_reference_original_drawing_route = original

    def _route(instance):
        camera = getattr(instance, "_aminate_bridge_overlay_camera", "") or _overlay_camera(
            getattr(instance, "_aminate_bridge_overlay_transform", "")
        )
        if _reference_mode(instance) != "main_view" and _reference_viewer().is_visible() and camera:
            try:
                instance.current_layer = controller.active_layer_for_camera(
                    getattr(instance, "current_layer", None),
                    camera=camera,
                )
                refresh = getattr(instance, "refresh_layers", None)
                if callable(refresh):
                    refresh()
                return instance.current_layer
            except Exception as exc:
                _set_status(instance, "Could not route drawing to the Reference Viewer: {0}".format(exc))
        return original()

    setattr(panel, route_name, types.MethodType(_route, panel))
    panel._aminate_reference_drawing_route_name = route_name
    panel._aminate_reference_drawing_route_installed = True
    return True


def _install_reference_activation_guard(panel):
    """Keep the user's perspective modelPanel active when drawing starts."""
    if _has_native_reference_viewer(panel):
        return True
    if getattr(panel, "_aminate_reference_activation_guard_v2_installed", False):
        return True
    original = getattr(panel, "_activate_drag_draw", None)
    if not callable(original):
        return False
    panel._aminate_reference_original_activate_drag_draw = original

    def _activate(instance):
        if _reference_mode(instance) == "main_view":
            return original()
        main_panel = getattr(instance, "_aminate_bridge_normal_panel", "") or _visible_main_panel()
        normal_camera = getattr(instance, "_aminate_bridge_normal_camera", "")
        if not normal_camera or not cmds.objExists(normal_camera):
            normal_camera = _panel_camera(main_panel)
        result = original()
        _restore_main_panel_camera(main_panel, normal_camera)
        _show_reference_for_panel(instance)
        return result

    panel._activate_drag_draw = types.MethodType(_activate, panel)
    panel._aminate_reference_activation_guard_installed = True
    panel._aminate_reference_activation_guard_v2_installed = True
    return True


def _install_reference_geometry_timer(panel):
    """Keep pinned retained-session geometry synced after Maya UI restores."""
    if _has_native_reference_viewer(panel):
        return True
    timer = getattr(panel, "_aminate_reference_geometry_timer_v3", None)
    if _qt_valid(timer):
        return True
    timer = QtCore.QTimer(panel)
    timer.setInterval(250)
    def _sync_from_controls():
        viewer = _reference_viewer()
        viewer.mode = "floating" if _reference_mode(panel) == "floating" else "pinned"
        placement = getattr(panel, "video_placement_combo", None)
        scale = getattr(panel, "video_scale_spin", None)
        if _qt_valid(placement):
            viewer.placement = str(placement.currentData() or "top_right")
        if _qt_valid(scale):
            viewer.scale_percent = float(scale.value())
        viewer.sync()
    timer.timeout.connect(_sync_from_controls)
    panel._aminate_reference_geometry_timer_callback_v2 = _sync_from_controls
    timer.start()
    panel._aminate_reference_geometry_timer_v3 = timer
    return True


def _overlay_camera(transform):
    camera = _string_attr(transform, "amirVideoOverlayCamera", "")
    if camera and cmds.objExists(camera):
        return _long_name(camera)
    shape = _overlay_shape(transform)
    if shape:
        try:
            connected = cmds.listConnections(shape + ".camera", source=True, destination=False) or []
            if connected:
                return _long_name(connected[0])
        except Exception:
            pass
    return ""


def _normal_camera_for_overlay(panel, overlay_camera, current_camera=""):
    """Resolve the original viewport camera behind a saved Pencil View."""
    source_camera = ""
    controller = getattr(panel, "controller", None)
    data_getter = getattr(controller, "drawing_view_data", None)
    if overlay_camera and callable(data_getter):
        try:
            source_camera = data_getter(overlay_camera).get("source", "") or ""
        except Exception:
            source_camera = ""
    if not source_camera and overlay_camera:
        source_camera = _string_attr(overlay_camera, DRAWING_VIEW_SOURCE_ATTR, "")
    if source_camera and cmds.objExists(source_camera) and _long_name(source_camera) != _long_name(overlay_camera):
        return _long_name(source_camera)
    if current_camera and cmds.objExists(current_camera) and _long_name(current_camera) != _long_name(overlay_camera):
        if _string_attr(current_camera, DRAWING_VIEW_ATTR, "") != "drawing_view":
            return _long_name(current_camera)
    if cmds.objExists("persp"):
        return _long_name("persp")
    return ""


def _set_video_opacity(panel, value):
    transform = getattr(panel, "_aminate_bridge_overlay_transform", "") or _camera_overlay_transform()
    shape = _overlay_shape(transform)
    if not shape:
        return False
    normalized = max(0.0, min(1.0, float(value) / 100.0))
    try:
        cmds.setAttr(shape + ".alphaGain", normalized)
        _ensure_double_attr(transform, VIDEO_OPACITY_ATTR)
        cmds.setAttr(transform + "." + VIDEO_OPACITY_ATTR, normalized)
        panel._aminate_bridge_overlay_transform = transform
        _set_status(panel, "Video opacity: {0}%".format(int(round(normalized * 100.0))))
        return True
    except Exception:
        return False


def _playback_slider():
    if not MAYA_AVAILABLE or mel is None:
        return ""
    try:
        slider = mel.eval("$tmpVar=$gPlayBackSlider")
        return slider if slider and cmds.control(slider, exists=True) else ""
    except Exception:
        return ""


def _set_audio_enabled(panel, enabled):
    """Toggle sound for a retained panel without reloading its old controller."""
    transform = getattr(panel, "_aminate_bridge_overlay_transform", "") or _camera_overlay_transform()
    if not transform or not cmds.objExists(transform):
        _set_status(panel, "Attach a video first so its audio can be changed.")
        return False
    enabled = bool(enabled)
    sound_name = _string_attr(transform, "amirVideoSoundNode", "")
    if enabled and (not sound_name or not cmds.objExists(sound_name)):
        controller = getattr(panel, "video_reference_controller", None)
        setter = getattr(controller, "set_audio_enabled", None)
        if callable(setter):
            success, message = setter(True, transform)
            _set_status(panel, message)
            return bool(success)
        source_path = _string_attr(transform, "amirVideoSourcePath", "")
        audio_path = ""
        try:
            import maya_video_reference_tool as video_tool

            media_info = video_tool._resolve_media_path(source_path, extract_audio=True, start_frame=int(getattr(controller, "start_frame", 1))) if source_path else {}
            audio_path = media_info.get("audio_path", "") or ""
        except Exception:
            audio_path = ""
        if not audio_path or not os.path.exists(audio_path):
            _set_status(panel, "This video does not contain audio that Maya can attach.")
            return False
        try:
            sound_name = cmds.sound(file=audio_path, offset=int(getattr(controller, "start_frame", 1)))
        except Exception as exc:
            _set_status(panel, "Could not attach video audio: {0}".format(exc))
            return False
    slider = _playback_slider()
    if not enabled:
        if slider and sound_name:
            try:
                if cmds.timeControl(slider, query=True, sound=True) == sound_name:
                    cmds.timeControl(slider, edit=True, sound="", displaySound=False)
            except Exception:
                pass
        if sound_name and cmds.objExists(sound_name):
            try:
                cmds.delete(sound_name)
            except Exception:
                pass
        sound_name = ""
    elif slider and sound_name:
        try:
            cmds.timeControl(slider, edit=True, sound=sound_name, displaySound=True)
        except Exception:
            pass
    _ensure_string_attr(transform, "amirVideoSoundNode")
    cmds.setAttr(transform + ".amirVideoSoundNode", sound_name, type="string")
    if not cmds.attributeQuery(VIDEO_AUDIO_ENABLED_ATTR, node=transform, exists=True):
        cmds.addAttr(transform, longName=VIDEO_AUDIO_ENABLED_ATTR, attributeType="long")
    cmds.setAttr(transform + "." + VIDEO_AUDIO_ENABLED_ATTR, int(bool(enabled and sound_name)))
    _set_status(panel, "Video audio: {0}.".format("On" if enabled and sound_name else "Off"))
    return True


def _delete_overlay_with_audio(transform):
    """Delete one stale retained overlay and any sound node it owns."""
    if not MAYA_AVAILABLE or not transform or not cmds.objExists(transform):
        return False
    sound_name = _string_attr(transform, "amirVideoSoundNode", "")
    slider = _playback_slider()
    if slider and sound_name:
        try:
            if cmds.timeControl(slider, query=True, sound=True) == sound_name:
                cmds.timeControl(slider, edit=True, sound="", displaySound=False)
        except Exception:
            pass
    if sound_name and cmds.objExists(sound_name):
        try:
            cmds.delete(sound_name)
        except Exception:
            pass
    try:
        cmds.delete(transform)
        return True
    except Exception:
        return False


def _rename_scene_view(panel, camera, label):
    if not MAYA_AVAILABLE or not camera or not cmds.objExists(camera):
        return False, "Choose a saved Pencil View first."
    label = (label or "").strip()[:64]
    if not label:
        return False, "Enter a name for the saved Pencil View."
    if _string_attr(camera, DRAWING_VIEW_ATTR, "") != "drawing_view":
        return False, "Choose a saved Pencil View first."
    folded = label.casefold()
    combo_labels = {}
    combo = getattr(panel, "drawing_view_combo", None)
    if _qt_valid(combo):
        try:
            for index in range(combo.count()):
                combo_camera = str(combo.itemData(index) or "")
                if combo_camera:
                    combo_labels[_long_name(combo_camera)] = str(combo.itemText(index) or "")
        except Exception:
            combo_labels = {}
    for other in cmds.ls(type="transform", long=True) or []:
        if _long_name(other) == _long_name(camera):
            continue
        if _string_attr(other, DRAWING_VIEW_ATTR, "") != "drawing_view":
            continue
        other_label = _string_attr(other, DRAWING_VIEW_LABEL_ATTR, "").strip()
        if not other_label:
            other_label = combo_labels.get(_long_name(other), "")
        if not other_label:
            other_label = str(other).rsplit("|", 1)[-1]
        if other_label.casefold() == folded:
            return False, "That Pencil View name is already in use."
    _ensure_string_attr(camera, DRAWING_VIEW_LABEL_ATTR)
    cmds.setAttr(camera + "." + DRAWING_VIEW_LABEL_ATTR, label, type="string")
    return True, label


def _combo_data(combo):
    try:
        value = combo.itemData(combo.currentIndex())
        return str(value or "")
    except Exception:
        return ""


def _begin_rename(panel):
    combo = getattr(panel, "drawing_view_combo", None)
    edit = _bind_view_name_edit(panel, combo) if _qt_valid(combo) else None
    if not _qt_valid(combo) or not _qt_valid(edit) or not _combo_data(combo):
        _set_status(panel, "Choose a saved Pencil View before renaming it.")
        return False
    edit.setReadOnly(False)
    edit.selectAll()
    edit.setFocus()
    return True


def _finish_rename(panel):
    edit = getattr(panel, "_aminate_bridge_view_name_edit", None)
    combo = getattr(panel, "drawing_view_combo", None)
    if not _qt_valid(edit) or edit.isReadOnly() or not _qt_valid(combo):
        return False
    camera = _combo_data(combo)
    requested = edit.text()
    edit.setReadOnly(True)
    ok, message = _rename_scene_view(panel, camera, requested)
    if not ok:
        try:
            edit.setText(combo.currentText())
        except Exception:
            pass
        _set_status(panel, message)
        return False
    try:
        combo.setItemText(combo.currentIndex(), message)
    except Exception:
        pass
    _set_status(panel, "Renamed saved drawing view: {0}.".format(message))
    return True


class _RenameEventFilter(QtCore.QObject if QtCore else object):
    def __init__(self, panel, parent=None):
        if QtCore:
            super(_RenameEventFilter, self).__init__(parent)
        self.panel = panel

    def eventFilter(self, watched, event):
        if QtCore and event.type() == QtCore.QEvent.MouseButtonDblClick:
            _begin_rename(self.panel)
            return True
        return False


def _bind_view_name_edit(panel, combo):
    """Bind the combo's current editor after Maya/view-list refreshes replace it."""
    if not _qt_valid(combo):
        return None
    edit = combo.lineEdit()
    if not _qt_valid(edit):
        return None
    edit.setAccessibleName("Saved Pencil View name")
    edit.setToolTip("Double-click the view name or press Rename, then press Enter to save it.")
    panel._aminate_bridge_view_name_edit = edit

    event_filter = getattr(panel, "_aminate_bridge_view_filter", None)
    if not _qt_valid(event_filter) or event_filter.parent() is not edit:
        event_filter = _RenameEventFilter(panel, edit)
        panel._aminate_bridge_view_filter = event_filter
    else:
        edit.removeEventFilter(event_filter)
    edit.installEventFilter(event_filter)

    # This editor is dedicated to Saved Drawing View names.  Replace legacy
    # callbacks every time because QComboBox can destroy/recreate the editor
    # while the retained panel refreshes its item list after Attach Video.
    try:
        edit.editingFinished.disconnect()
    except Exception:
        pass
    try:
        edit.returnPressed.disconnect()
    except Exception:
        pass
    rename_handler = lambda: _finish_rename(panel)
    edit.editingFinished.connect(rename_handler)
    edit.returnPressed.connect(rename_handler)
    panel._aminate_bridge_rename_handler = rename_handler
    panel._aminate_bridge_rename_connected = True
    return edit


def _install_view_rename(panel):
    combo = getattr(panel, "drawing_view_combo", None)
    if not _qt_valid(combo) or QtWidgets is None:
        return False
    if not combo.isEditable():
        combo.setEditable(True)
    edit = _bind_view_name_edit(panel, combo)
    if not _qt_valid(edit):
        return False
    edit.setReadOnly(True)

    button = getattr(panel, "rename_drawing_view_button", None) or _find_child(panel, "animatorsPencilRenameDrawingViewButton")
    button_created = False
    if not _qt_valid(button) or not isinstance(button, QtWidgets.QPushButton):
        old_button = button if _qt_valid(button) else None
        button = QtWidgets.QPushButton(combo.parentWidget())
        button_created = True
        button.setObjectName("animatorsPencilRenameDrawingViewButton")
        button.setText("Rename")
        button.setAccessibleName("Rename selected Pencil View")
        button.setToolTip("Rename the selected Pencil View. Double-clicking its name works too.")
        group = combo.parentWidget()
        layout = group.layout() if _qt_valid(group) else None
        if layout is not None:
            try:
                if isinstance(layout, QtWidgets.QGridLayout):
                    old_index = layout.indexOf(old_button) if old_button is not None else -1
                    if old_index >= 0:
                        old_button.setObjectName("animatorsPencilRenameDrawingViewButtonLegacyHidden")
                        old_button.setVisible(False)
                        try:
                            row, column, row_span, column_span = layout.getItemPosition(old_index)
                        except Exception:
                            row, column, row_span, column_span = layout.rowCount(), 0, 1, 2
                        layout.removeWidget(old_button)
                        layout.addWidget(button, row, column, row_span or 1, column_span or 2)
                    else:
                        layout.addWidget(button, layout.rowCount(), 0, 1, 2)
                else:
                    layout.addWidget(button)
            except Exception:
                layout.addWidget(button)
        panel.rename_drawing_view_button = button
        button.setMinimumHeight(28)
    expanding_policy = getattr(QtWidgets.QSizePolicy, "Expanding", None)
    fixed_policy = getattr(QtWidgets.QSizePolicy, "Fixed", None)
    if expanding_policy is None and hasattr(QtWidgets.QSizePolicy, "Policy"):
        expanding_policy = QtWidgets.QSizePolicy.Policy.Expanding
        fixed_policy = QtWidgets.QSizePolicy.Policy.Fixed
    if expanding_policy is not None and fixed_policy is not None:
        button.setSizePolicy(expanding_policy, fixed_policy)
    # A retained older bridge may have left the connection flag on the panel
    # while this call replaces its QToolButton.  The new dedicated QPushButton
    # must own a real click handler regardless of that stale flag.
    if not button_created:
        try:
            button.clicked.disconnect()
        except Exception:
            pass
    rename_button_handler = lambda: _begin_rename(panel)
    button.clicked.connect(rename_button_handler)
    panel._aminate_bridge_rename_button_handler = rename_button_handler
    panel._aminate_bridge_rename_button_connected = True
    return True


def _apply_overlay_size(panel):
    combo = getattr(panel, "video_placement_combo", None)
    spin = getattr(panel, "video_scale_spin", None)
    if not _qt_valid(combo) or not _qt_valid(spin):
        return False
    placement = str(combo.currentData() or "full_view").lower()
    old_placement = getattr(panel, "_aminate_bridge_last_placement", "full_view")
    crossed = (old_placement == "full_view") != (placement == "full_view")
    if crossed:
        # Match the fresh Pencil panel: crossing Full View <-> PIP chooses a
        # useful default, while corner-to-corner keeps a custom size.
        spin.blockSignals(True)
        spin.setValue(100.0 if placement == "full_view" else 38.0)
        spin.blockSignals(False)
        panel._aminate_bridge_scale_user_edited = False
    if _reference_mode(panel) != "main_view":
        panel._aminate_bridge_last_placement = placement
        panel._aminate_bridge_scale_user_edited = True
        if getattr(panel, "_aminate_bridge_overlay_transform", ""):
            return _show_reference_for_panel(panel)
        return False
    if not getattr(panel, "_aminate_bridge_overlay_transform", ""):
        if not getattr(panel, "_aminate_bridge_scale_user_edited", False):
            spin.blockSignals(True)
            spin.setValue(100.0 if placement == "full_view" else 38.0)
            spin.blockSignals(False)
        panel._aminate_bridge_last_placement = placement
        return False
    transform = panel._aminate_bridge_overlay_transform
    shape = _overlay_shape(transform)
    if not shape:
        return False
    try:
        current_size_x = float(cmds.getAttr(shape + ".sizeX"))
        current_size_y = float(cmds.getAttr(shape + ".sizeY"))
        current_offset_x = float(cmds.getAttr(shape + ".offsetX"))
        current_offset_y = float(cmds.getAttr(shape + ".offsetY"))
        baseline_size_x = _double_attr(transform, "amirVideoOverlayBaselineSizeX", None)
        baseline_size_y = _double_attr(transform, "amirVideoOverlayBaselineSizeY", None)
        baseline_offset_x = _double_attr(transform, "amirVideoOverlayBaselineOffsetX", None)
        baseline_offset_y = _double_attr(transform, "amirVideoOverlayBaselineOffsetY", None)
        # Older retained overlays may predate the baseline attrs. Infer a
        # useful full-view basis from the known legacy PIP default, then save
        # it so future edits and scene reopen use stable coordinates.
        inferred_scale = 0.38 if placement != "full_view" else 1.0
        corner_x = 1.0 if placement in ("top_right", "bottom_right") else -1.0 if placement in ("top_left", "bottom_left") else 0.0
        corner_y = 1.0 if placement in ("top_right", "top_left") else -1.0 if placement in ("bottom_right", "bottom_left") else 0.0
        if baseline_size_x is None:
            baseline_size_x = current_size_x / inferred_scale
        if baseline_size_y is None:
            baseline_size_y = current_size_y / inferred_scale
        if baseline_offset_x is None:
            baseline_offset_x = current_offset_x - corner_x * baseline_size_x * (1.0 - inferred_scale) * 0.5
        if baseline_offset_y is None:
            baseline_offset_y = current_offset_y - corner_y * baseline_size_y * (1.0 - inferred_scale) * 0.5
        for attr, value in (("amirVideoOverlayBaselineSizeX", baseline_size_x), ("amirVideoOverlayBaselineSizeY", baseline_size_y), ("amirVideoOverlayBaselineOffsetX", baseline_offset_x), ("amirVideoOverlayBaselineOffsetY", baseline_offset_y)):
            _ensure_double_attr(transform, attr)
            cmds.setAttr(transform + "." + attr, float(value))
        scale = max(0.10, min(2.0, float(spin.value()) / 100.0))
        offset_x = baseline_offset_x + corner_x * baseline_size_x * (1.0 - scale) * 0.5
        offset_y = baseline_offset_y + corner_y * baseline_size_y * (1.0 - scale) * 0.5
        if placement == "full_view":
            offset_x, offset_y = baseline_offset_x, baseline_offset_y
        cmds.setAttr(shape + ".sizeX", baseline_size_x * scale)
        cmds.setAttr(shape + ".sizeY", baseline_size_y * scale)
        cmds.setAttr(shape + ".offsetX", offset_x)
        cmds.setAttr(shape + ".offsetY", offset_y)
        _ensure_string_attr(transform, OVERLAY_PLACEMENT_ATTR)
        _ensure_double_attr(transform, OVERLAY_SCALE_ATTR)
        cmds.setAttr(transform + "." + OVERLAY_PLACEMENT_ATTR, placement, type="string")
        cmds.setAttr(transform + "." + OVERLAY_SCALE_ATTR, scale)
        if cmds.attributeQuery("amirVideoOverlayUpdatedAt", node=transform, exists=True):
            cmds.setAttr(transform + ".amirVideoOverlayUpdatedAt", float(time.time()))
        panel._aminate_bridge_last_placement = placement
        panel._aminate_bridge_scale_user_edited = True
        return True
    except Exception as exc:
        _set_status(panel, "Could not resize the attached video: {0}".format(exc))
        return False


def _install_video_controls(panel):
    if QtWidgets is None or not _qt_valid(panel):
        return False
    native_reference_controls = _has_native_reference_viewer(panel)
    start_spin = _find_child(panel, "animatorsPencilVideoStartFrameSpin", QtWidgets.QSpinBox)
    if _qt_valid(start_spin):
        start_spin.setPrefix("Start frame ")
        start_spin.setAccessibleName("Video draw-over start frame")
        start_spin.setToolTip("Start frame: the Maya frame where the first video frame appears. A value such as 5 is a timeline frame, not a size.")
    placement = getattr(panel, "video_placement_combo", None) or _find_child(panel, "animatorsPencilVideoPlacementCombo", QtWidgets.QComboBox)
    if not _qt_valid(placement):
        return False
    panel.video_placement_combo = placement
    placement.setMinimumWidth(140)
    try:
        placement.setMinimumContentsLength(12)
        placement.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    except Exception:
        pass
    size_spin = getattr(panel, "video_scale_spin", None) or _find_child(panel, "animatorsPencilVideoScalePercentSpin", QtWidgets.QDoubleSpinBox)
    if not _qt_valid(size_spin):
        size_spin = QtWidgets.QDoubleSpinBox(placement.parentWidget())
        size_spin.setObjectName("animatorsPencilVideoScalePercentSpin")
        size_spin.setRange(10.0, 200.0)
        size_spin.setSingleStep(5.0)
        size_spin.setDecimals(0)
        size_spin.setValue(100.0)
        group = placement.parentWidget()
        layout = group.layout() if _qt_valid(group) else None
        if layout is not None:
            try:
                if isinstance(layout, QtWidgets.QGridLayout):
                    layout.addWidget(size_spin, layout.rowCount(), 0, 1, 2)
                else:
                    layout.addWidget(size_spin)
            except Exception:
                layout.addWidget(size_spin)
        panel.video_scale_spin = size_spin
    group = placement.parentWidget()
    layout = group.layout() if _qt_valid(group) else None
    if isinstance(layout, QtWidgets.QGridLayout):
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
    size_spin.setPrefix("Viewer Size ")
    size_spin.setSuffix("%")
    size_spin.setAccessibleName("Reference viewer size percentage")
    size_spin.setToolTip("Viewer size as a percentage of the main viewport. 100% fills it; 38% is the compact PIP default.")
    display_combo = getattr(panel, "video_display_combo", None) or _find_child(panel, "animatorsPencilVideoDisplayCombo", QtWidgets.QComboBox)
    if not _qt_valid(display_combo):
        display_combo = QtWidgets.QComboBox(placement.parentWidget())
        display_combo.setObjectName("animatorsPencilVideoDisplayCombo")
        display_combo.addItem("Over Main Viewport", "pinned")
        display_combo.addItem("Floating Window", "floating")
        display_combo.addItem("Main Viewport (Legacy)", "main_view")
        if isinstance(layout, QtWidgets.QGridLayout):
            layout.addWidget(display_combo, layout.rowCount(), 0, 1, 2)
        elif layout is not None:
            layout.addWidget(display_combo)
    panel.video_display_combo = display_combo
    display_combo.setAccessibleName("Video reference display mode")
    display_combo.setToolTip("Choose a picture-in-picture viewer, one movable floating viewer, or the legacy main-viewport camera switch.")
    display_combo.setMinimumWidth(150)
    if display_combo.findData("pinned") < 0:
        display_combo.addItem("Over Main Viewport", "pinned")
    if display_combo.findData("floating") < 0:
        display_combo.addItem("Floating Window", "floating")
    if display_combo.findData("main_view") < 0:
        display_combo.addItem("Main Viewport (Legacy)", "main_view")
    if not native_reference_controls and not getattr(panel, "_aminate_reference_display_initialized", False):
        display_combo.blockSignals(True)
        display_combo.setCurrentIndex(max(0, display_combo.findData("pinned")))
        display_combo.blockSignals(False)
        if placement.currentData() != "top_right":
            placement.blockSignals(True)
            placement.setCurrentIndex(max(0, placement.findData("top_right")))
            placement.blockSignals(False)
        size_spin.blockSignals(True)
        size_spin.setValue(38.0)
        size_spin.blockSignals(False)
        panel._aminate_bridge_last_placement = "top_right"
        panel._aminate_reference_display_initialized = True
    if not native_reference_controls and not getattr(panel, "_aminate_reference_display_v2_connected", False):
        display_combo.currentIndexChanged.connect(lambda _index: _show_reference_for_panel(panel))
        panel._aminate_reference_display_v2_connected = True
    panel._aminate_bridge_overlay_transform = getattr(panel, "_video_overlay_transform", "") or _camera_overlay_transform()
    if not native_reference_controls and not getattr(panel, "_aminate_reference_geometry_v2_connected", False):
        placement.currentIndexChanged.connect(lambda: _apply_overlay_size(panel))
        size_spin.valueChanged.connect(lambda: _apply_overlay_size(panel))
        panel._aminate_reference_geometry_v2_connected = True
    panel._aminate_bridge_last_placement = str(placement.currentData() or "full_view")
    if not native_reference_controls and panel._aminate_bridge_overlay_transform:
        stored_scale = _double_attr(panel._aminate_bridge_overlay_transform, OVERLAY_SCALE_ATTR, None)
        if stored_scale is not None:
            size_spin.blockSignals(True)
            size_spin.setValue(max(10.0, min(200.0, stored_scale * 100.0)))
            size_spin.blockSignals(False)
    opacity_spin = getattr(panel, "video_opacity_spin", None) or _find_child(panel, "animatorsPencilVideoOpacityPercentSpin", QtWidgets.QDoubleSpinBox)
    line_opacity_spin = getattr(panel, "video_line_opacity_spin", None) or _find_child(panel, "animatorsPencilVideoLineOpacityPercentSpin", QtWidgets.QDoubleSpinBox)
    if _qt_valid(opacity_spin):
        opacity_spin.setPrefix("Video Opacity ")
        opacity_spin.setSuffix("%")
        opacity_spin.setAccessibleName("Video draw-over opacity percentage")
        opacity_spin.setToolTip("Opacity of the attached video. Changes apply immediately and persist in the scene.")
        if not getattr(panel, "_aminate_bridge_video_opacity_connected", False):
            opacity_spin.valueChanged.connect(lambda value: _set_video_opacity(panel, value))
            panel._aminate_bridge_video_opacity_connected = True
    if _qt_valid(line_opacity_spin):
        line_opacity_spin.setPrefix("Lines Opacity ")
        line_opacity_spin.setSuffix("%")
        line_opacity_spin.setAccessibleName("Pencil line opacity percentage")
        line_opacity_spin.setToolTip("Opacity of Pencil lines on the active layer. Changes apply immediately.")
    audio_box = getattr(panel, "video_include_audio_box", None) or _find_child(panel, "animatorsPencilVideoIncludeAudioCheckBox", QtWidgets.QCheckBox)
    if _qt_valid(audio_box) and not getattr(panel, "_aminate_bridge_audio_connected", False):
        audio_box.toggled.connect(lambda checked: _set_audio_enabled(panel, checked))
        panel._aminate_bridge_audio_connected = True
    mode_button = getattr(panel, "show_pencil_view_button", None) or _find_child(panel, "animatorsPencilShowPencilViewButton", QtWidgets.QPushButton)
    if _qt_valid(mode_button) and not native_reference_controls:
        panel.show_pencil_view_button = mode_button
        normal_panel = getattr(panel, "_aminate_bridge_normal_panel", "") or _visible_main_panel()
        current_camera = _panel_camera(normal_panel) or _current_model_camera()
        panel._aminate_bridge_normal_panel = normal_panel
        panel._aminate_bridge_overlay_camera = _overlay_camera(panel._aminate_bridge_overlay_transform)
        normal_camera = getattr(panel, "_aminate_bridge_normal_camera", "")
        if not normal_camera or not cmds.objExists(normal_camera) or _long_name(normal_camera) == _long_name(panel._aminate_bridge_overlay_camera):
            normal_camera = _normal_camera_for_overlay(panel, panel._aminate_bridge_overlay_camera, current_camera)
        panel._aminate_bridge_normal_camera = normal_camera
        in_video = bool(panel._aminate_bridge_overlay_camera and current_camera == panel._aminate_bridge_overlay_camera)
        panel._aminate_bridge_in_video_mode = in_video
        mode_button.setText("Hide Reference Viewer" if _reference_viewer().is_visible() else "Show Reference Viewer")
        mode_button.setAccessibleName("Switch Video Draw-Over mode")
        mode_button.setToolTip("Show or hide the video-and-annotations viewer without changing the perspective camera.")
        if not getattr(panel, "_aminate_reference_mode_connected", False):
            def _toggle_video_mode(_checked=False):
                mode = _reference_mode(panel)
                desired_video = (
                    not _reference_viewer().is_visible()
                    if mode != "main_view"
                    else not bool(getattr(panel, "_aminate_bridge_in_video_mode", False))
                )

                def _apply_toggle():
                    _apply_video_mode(desired_video)

                def _apply_video_mode(want_video):
                    overlay_camera = getattr(panel, "_aminate_bridge_overlay_camera", "") or _overlay_camera(getattr(panel, "_aminate_bridge_overlay_transform", ""))
                    if not overlay_camera:
                        _set_status(panel, "Attach a video first so Aminate knows the draw-over camera.")
                        return
                    if _reference_mode(panel) != "main_view":
                        if not want_video:
                            _reference_viewer().hide()
                            mode_button.setText("Show Reference Viewer")
                            _set_status(panel, "Reference Viewer hidden. Perspective remains active.")
                            return
                        if _show_reference_for_panel(panel):
                            mode_button.setText("Hide Reference Viewer")
                        return
                    if not want_video:
                        normal_camera = getattr(panel, "_aminate_bridge_normal_camera", "")
                        if normal_camera and _switch_visible_model_camera(normal_camera):
                            panel._aminate_bridge_in_video_mode = False
                            mode_button.setText("Switch to Draw Over Video")
                            _set_status(panel, "Normal viewport drawing is active.")
                        return
                    if _switch_visible_model_camera(overlay_camera):
                        panel._aminate_bridge_in_video_mode = True
                        panel._aminate_bridge_overlay_camera = overlay_camera
                        mode_button.setText("Switch to Normal Viewport Drawing")
                        _set_status(panel, "Draw over video is active.")

                # Let the legacy retained callback return first, then force the
                # requested final camera/label state exactly once.
                QtCore.QTimer.singleShot(0, _apply_toggle)

            mode_button.clicked.connect(_toggle_video_mode)
            panel._aminate_reference_mode_connected = True
    attach_button = getattr(panel, "attach_video_button", None) or _find_child(panel, "animatorsPencilAttachVideoButton", QtWidgets.QPushButton)
    if _qt_valid(attach_button) and not native_reference_controls and not getattr(panel, "_aminate_reference_attach_connected", False):
        def _after_attach(_checked=False):
            def _apply():
                transform = _camera_overlay_transform()
                if not transform:
                    return
                panel._aminate_bridge_overlay_transform = transform
                overlay_camera = _overlay_camera(transform)
                panel._aminate_bridge_overlay_camera = overlay_camera
                if overlay_camera:
                    if _reference_mode(panel) == "main_view":
                        _switch_visible_model_camera(overlay_camera)
                        panel._aminate_bridge_in_video_mode = True
                        if _qt_valid(mode_button):
                            mode_button.setText("Switch to Normal Viewport Drawing")
                    else:
                        _show_reference_for_panel(panel)
                        if _qt_valid(mode_button):
                            mode_button.setText("Hide Reference Viewer")
                # Keep only the newest overlay for this Pencil View.
                if overlay_camera and MAYA_AVAILABLE:
                    matching = []
                    for node in cmds.ls(type="transform", long=True) or []:
                        if node == transform or _overlay_camera(node) != overlay_camera:
                            continue
                        if _overlay_shape(node):
                            matching.append(node)
                    for old in matching:
                        _delete_overlay_with_audio(old)
            QtCore.QTimer.singleShot(0, _apply)

        attach_button.clicked.connect(_after_attach)
        panel._aminate_reference_attach_connected = True
    return True


def _relabel_package_button(panel):
    button = getattr(panel, "package_annotated_scene_button", None) or _find_child(panel, "animatorsPencilPackageAnnotatedSceneButton", QtWidgets.QPushButton)
    if not _qt_valid(button):
        return False
    button.setText("Package Scene")
    button.setAccessibleName("Package scene with references and draw-overs")
    button.setToolTip("Save and package the Maya scene with references, original/proxy video, audio, and Pencil draw-overs using portable paths.")
    return True


def install_into_open_aminate(window=None):
    """Augment the existing Aminate window without reload or recreation."""
    if QtWidgets is None:
        return {"ok": False, "reason": "Qt is unavailable."}
    if window is None:
        try:
            import maya_dynamic_parent_pivot

            window = maya_dynamic_parent_pivot.GLOBAL_WINDOW
        except Exception:
            window = None
    panel = getattr(window, "animators_pencil_panel", None) if _qt_valid(window) else None
    if not _qt_valid(panel):
        return {"ok": False, "reason": "No retained Animator's Pencil panel was found."}
    result = {
        "ok": True,
        "window_reused": True,
        "panel_reused": True,
        "view_rename": _install_view_rename(panel),
        "video_controls": _install_video_controls(panel),
        "reference_drawing_route": _install_reference_drawing_route(panel),
        "reference_activation_guard": _install_reference_activation_guard(panel),
        "reference_geometry_timer": _install_reference_geometry_timer(panel),
        "package_button": _relabel_package_button(panel),
        "module_reload": False,
        "window_recreated": False,
    }
    panel._aminate_pencil_view_video_bridge_installed = True
    return result


__all__ = ["install_into_open_aminate"]
