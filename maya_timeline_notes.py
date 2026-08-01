"""
maya_timeline_notes.py

Colored timeline notes built on Maya's native time slider bookmark plugin,
with Amir-specific note text, export/import, and custom hover tooltips.
"""

from __future__ import absolute_import, division, print_function

import json
import os

import maya_skinning_cleanup as skin_cleanup

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    import maya.OpenMayaUI as omui
    import maya.mel as mel

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    omui = None
    mel = None
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


WINDOW_OBJECT_NAME = "mayaTimelineNotesWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
EXPORT_FILE_FILTER = "Timeline Notes (*.json)"
NOTE_MARKER_ATTR = "amirTimelineNote"
NOTE_TEXT_ATTR = "amirTimelineNoteText"
NOTE_OPACITY_ATTR = "amirTimelineNoteOpacity"
NOTE_EXPORT_ID_ATTR = "amirTimelineNoteId"
NOTE_RGB_ATTR = "amirTimelineNoteRgb"
NOTE_TITLE_ATTR = "amirTimelineNoteTitle"
DEFAULT_NOTE_COLOR = (0.278, 0.584, 0.800)
DEFAULT_NOTE_OPACITY = 0.8
DEFAULT_TOOLTIP_BACKGROUND = (0.18, 0.18, 0.18)
MAX_TOOLTIP_WIDTH = 420
TIMELINE_OVERLAY_OBJECT_NAME = "aminateTimelineNotesOverlay"
TIMELINE_TOOLTIP_OBJECT_NAME = "aminateTimelineNotesTooltip"
TIMELINE_NOTES_OVERLAY_ENABLED_OPTION = "aminateTimelineNotesOverlayEnabled"
TIMELINE_NOTES_BAR_HEIGHT_OPTION = "aminateTimelineNotesBarHeight"
TIMELINE_NOTES_TOOLTIP_OPACITY_OPTION = "aminateTimelineNotesTooltipOpacity"
TIMELINE_NOTES_DEFAULT_COLOR_OPTION = "aminateTimelineNotesDefaultColor"
DEFAULT_TIMELINE_BAR_HEIGHT = 7
DEFAULT_TIMELINE_TOOLTIP_OPACITY = 0.88

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None

_qt_flag = skin_cleanup._qt_flag
_style_donate_button = skin_cleanup._style_donate_button
_open_external_url = skin_cleanup._open_external_url
_maya_main_window = skin_cleanup._maya_main_window
_short_name = skin_cleanup._short_name


def _debug(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayInfo("[Maya Timeline Notes] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayWarning("[Maya Timeline Notes] {0}".format(message))


def _blend_channel(channel, background, alpha):
    return max(0.0, min(1.0, background + ((channel - background) * alpha)))


def _blend_color(color, opacity):
    return tuple(_blend_channel(float(color[index]), float(DEFAULT_TOOLTIP_BACKGROUND[index]), float(opacity)) for index in range(3))


def _clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def _clean_color(color, fallback=DEFAULT_NOTE_COLOR):
    values = list(color or fallback)
    while len(values) < 3:
        values.append(fallback[len(values)])
    return tuple(_clamp(values[index], 0.0, 1.0) for index in range(3))


def _option_var_exists(name):
    if not MAYA_AVAILABLE or not cmds:
        return False
    try:
        return bool(cmds.optionVar(exists=name))
    except Exception:
        return False


def _option_var_int(name, default):
    if not _option_var_exists(name):
        return int(default)
    try:
        return int(cmds.optionVar(query=name))
    except Exception:
        return int(default)


def _option_var_float(name, default):
    if not _option_var_exists(name):
        return float(default)
    try:
        return float(cmds.optionVar(query=name))
    except Exception:
        return float(default)


def _option_var_color(name, default):
    if not _option_var_exists(name):
        return _clean_color(default)
    try:
        return _clean_color(json.loads(cmds.optionVar(query=name)), default)
    except Exception:
        return _clean_color(default)


def _set_option_var_int(name, value):
    if MAYA_AVAILABLE and cmds:
        cmds.optionVar(intValue=(name, int(value)))


def _set_option_var_float(name, value):
    if MAYA_AVAILABLE and cmds:
        cmds.optionVar(floatValue=(name, float(value)))


def _set_option_var_color(name, color):
    if MAYA_AVAILABLE and cmds:
        cmds.optionVar(stringValue=(name, json.dumps([float(value) for value in _clean_color(color)])))


def _timeline_customization_defaults():
    return {
        "overlay_enabled": True,
        "bar_height": int(DEFAULT_TIMELINE_BAR_HEIGHT),
        "tooltip_opacity": float(DEFAULT_TIMELINE_TOOLTIP_OPACITY),
        "default_color": tuple(DEFAULT_NOTE_COLOR),
    }


def _timeline_customization_settings():
    defaults = _timeline_customization_defaults()
    return {
        "overlay_enabled": bool(_option_var_int(TIMELINE_NOTES_OVERLAY_ENABLED_OPTION, int(defaults["overlay_enabled"]))),
        "bar_height": int(_clamp(_option_var_int(TIMELINE_NOTES_BAR_HEIGHT_OPTION, defaults["bar_height"]), 3, 24)),
        "tooltip_opacity": float(_clamp(_option_var_float(TIMELINE_NOTES_TOOLTIP_OPACITY_OPTION, defaults["tooltip_opacity"]), 0.25, 1.0)),
        "default_color": _option_var_color(TIMELINE_NOTES_DEFAULT_COLOR_OPTION, defaults["default_color"]),
    }


def _escape_html(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _preferred_note_text(note):
    text = (note.get("text") or "").strip()
    if text:
        return text
    return (note.get("title") or "No extra note text yet.").strip() or "No extra note text yet."


def _set_string_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), value or "", type="string")


def _set_bool_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="bool")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), bool(value))


def _set_double_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="double")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), float(value))


def _get_string_attr(node_name, attr_name, default=""):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return default
    value = cmds.getAttr("{0}.{1}".format(node_name, attr_name))
    return value if value is not None else default


def _get_double_attr(node_name, attr_name, default=0.0):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return float(default)
    return float(cmds.getAttr("{0}.{1}".format(node_name, attr_name)))


def _get_bool_attr(node_name, attr_name, default=False):
    if not cmds.objExists(node_name) or not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return bool(default)
    return bool(cmds.getAttr("{0}.{1}".format(node_name, attr_name)))


def _playback_range():
    start = int(round(float(cmds.playbackOptions(query=True, minTime=True))))
    end = int(round(float(cmds.playbackOptions(query=True, maxTime=True))))
    if end < start:
        start, end = end, start
    return start, end


def _playback_slider_name():
    if not MAYA_AVAILABLE or not mel:
        return ""
    try:
        if cmds.about(batch=True):
            return ""
    except Exception:
        pass
    try:
        slider = mel.eval("$tmpVar=$gPlayBackSlider")
    except Exception:
        return ""
    try:
        if slider and cmds.control(slider, exists=True):
            return slider
    except Exception:
        pass
    return ""


def _selected_time_range():
    if not MAYA_AVAILABLE or not mel:
        return None
    slider = _playback_slider_name()
    if not slider:
        return None
    try:
        values = cmds.timeControl(slider, query=True, rangeArray=True) or []
        if len(values) >= 2:
            start = int(round(float(values[0])))
            end = int(round(float(values[1])))
            if end < start:
                start, end = end, start
            return start, end
    except Exception:
        pass
    return None


def _has_playback_slider():
    return bool(_playback_slider_name())


def _current_frame():
    if not MAYA_AVAILABLE or not cmds:
        return None
    try:
        return int(round(float(cmds.currentTime(query=True))))
    except Exception:
        return None


def _direct_create_bookmark(bookmark_api, title, start_frame, end_frame, color):
    cmds.pluginInfo("timeSliderBookmark", edit=True, writeRequires=True)
    bookmark = cmds.createNode("timeSliderBookmark")
    cmds.setAttr(bookmark + ".timeRangeStart", float(start_frame))
    cmds.setAttr(bookmark + ".timeRangeStop", float(end_frame))
    cmds.setAttr(bookmark + ".name", title, type="string")
    cmds.setAttr(bookmark + ".color", *color)
    priority = 1
    if bookmark_api and hasattr(bookmark_api, "getNextPriority"):
        try:
            priority = int(bookmark_api.getNextPriority())
        except Exception:
            priority = 1
    cmds.setAttr(bookmark + ".priority", priority)
    return bookmark


def _time_slider_widget():
    if not (MAYA_AVAILABLE and QtWidgets and omui and mel and shiboken):
        return None
    slider = _playback_slider_name()
    if not slider:
        return None
    try:
        pointer = omui.MQtUtil.findControl(slider)
        if not pointer:
            return None
        return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)
    except Exception:
        return None


def _ensure_bookmark_api():
    if not MAYA_AVAILABLE:
        return None
    try:
        if not cmds.pluginInfo("timeSliderBookmark", query=True, loaded=True):
            cmds.loadPlugin("timeSliderBookmark", quiet=True)
    except Exception:
        return None
    try:
        from maya.plugin.timeSliderBookmark import timeSliderBookmark as bookmark_api  # noqa: WPS433

        return bookmark_api
    except Exception:
        return None


def _bookmark_nodes(bookmark_api):
    bookmark_nodes = []
    try:
        bookmark_nodes = bookmark_api.getAllBookmarks() or []
    except Exception:
        bookmark_nodes = cmds.ls(type="timeSliderBookmark") or []
    result = []
    for node_name in bookmark_nodes:
        if cmds.objExists(node_name) and _get_bool_attr(node_name, NOTE_MARKER_ATTR, False):
            result.append(node_name)
    return result


def _note_payload(node_name):
    rgb_data = _get_string_attr(node_name, NOTE_RGB_ATTR, "")
    try:
        rgb = tuple(json.loads(rgb_data)) if rgb_data else DEFAULT_NOTE_COLOR
    except Exception:
        rgb = DEFAULT_NOTE_COLOR
    title = _get_string_attr(node_name, NOTE_TITLE_ATTR, "") or _short_name(node_name)
    return {
        "node": node_name,
        "title": title,
        "start_frame": int(round(float(cmds.getAttr(node_name + ".timeRangeStart")))),
        "end_frame": int(round(float(cmds.getAttr(node_name + ".timeRangeStop")))),
        "opacity": _get_double_attr(node_name, NOTE_OPACITY_ATTR, DEFAULT_NOTE_OPACITY),
        "color": tuple(float(value) for value in rgb),
        "text": _get_string_attr(node_name, NOTE_TEXT_ATTR, ""),
        "export_id": _get_string_attr(node_name, NOTE_EXPORT_ID_ATTR, node_name),
    }


class _TimelineTooltipFilter(QtCore.QObject if QtCore else object):
    def __init__(self, controller, widget):
        super(_TimelineTooltipFilter, self).__init__(widget)
        self.controller = controller
        self.widget = widget

    def eventFilter(self, watched, event):
        if watched is not self.widget or not QtCore:
            return False
        event_type = event.type()
        if event_type == _qt_flag("QEvent", "ToolTip", fallback=QtCore.QEvent.ToolTip):
            note = self.controller.note_at_widget_x(event.pos().x(), self.widget.width())
            if note:
                self.controller.show_tooltip(note, event.globalPos())
                return True
            self.controller.hide_tooltip()
            return True
        if event_type == _qt_flag("QEvent", "Leave", fallback=QtCore.QEvent.Leave):
            self.controller.hide_tooltip()
        return False


class _TimelineNoteTooltipBubble(QtWidgets.QFrame if QtWidgets else object):
    def __init__(self, controller, parent=None):
        flags = _qt_flag("WindowType", "ToolTip", getattr(QtCore.Qt, "ToolTip", 0)) if QtCore else 0
        super(_TimelineNoteTooltipBubble, self).__init__(parent, flags)
        self.controller = controller
        self.setObjectName(TIMELINE_TOOLTIP_OBJECT_NAME)
        self.setAttribute(_qt_flag("WidgetAttribute", "WA_ShowWithoutActivating", getattr(QtCore.Qt, "WA_ShowWithoutActivating", None)), True)
        self.setAttribute(_qt_flag("WidgetAttribute", "WA_TranslucentBackground", getattr(QtCore.Qt, "WA_TranslucentBackground", None)), True)
        self.setWindowOpacity(float(self.controller.timeline_customization()["tooltip_opacity"]))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self.label = QtWidgets.QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(_qt_flag("TextFormat", "RichText", getattr(QtCore.Qt, "RichText", None)))
        self.label.setMaximumWidth(MAX_TOOLTIP_WIDTH)
        layout.addWidget(self.label)
        self._effect = None
        self._animation = None
        try:
            self._effect = QtWidgets.QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._effect)
            self._animation = QtCore.QPropertyAnimation(self._effect, b"opacity", self)
            self._animation.setDuration(180)
        except Exception:
            self._effect = None
            self._animation = None

    def show_note(self, note, global_pos):
        settings = self.controller.timeline_customization()
        self.setWindowOpacity(float(settings["tooltip_opacity"]))
        self.setStyleSheet(
            "#{0} {{ background: rgba(31, 31, 31, 232); color: #F2F2F2; border: 1px solid rgba(0, 161, 224, 180); border-radius: 6px; }}"
            "QLabel {{ color: #F2F2F2; }}".format(TIMELINE_TOOLTIP_OBJECT_NAME)
        )
        self.label.setText(self.controller.tooltip_html(note))
        self.adjustSize()
        self.move(global_pos + QtCore.QPoint(14, 18))
        if self._animation and self._effect:
            self._animation.stop()
            self._effect.setOpacity(0.0)
            self.show()
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.start()
        else:
            self.show()


class _TimelineNotesOverlay(QtWidgets.QWidget if QtWidgets else object):
    def __init__(self, controller, parent_widget):
        super(_TimelineNotesOverlay, self).__init__(parent_widget)
        self.controller = controller
        self.parent_widget = parent_widget
        self.setObjectName(TIMELINE_OVERLAY_OBJECT_NAME)
        self.setAttribute(_qt_flag("WidgetAttribute", "WA_TransparentForMouseEvents", getattr(QtCore.Qt, "WA_TransparentForMouseEvents", None)), True)
        self.setAttribute(_qt_flag("WidgetAttribute", "WA_TranslucentBackground", getattr(QtCore.Qt, "WA_TranslucentBackground", None)), True)
        self.setAttribute(_qt_flag("WidgetAttribute", "WA_NoSystemBackground", getattr(QtCore.Qt, "WA_NoSystemBackground", None)), True)
        self.sync_geometry()
        self.show()
        self.raise_()
        try:
            parent_widget.installEventFilter(self)
        except Exception:
            pass

    def sync_geometry(self):
        if self.parent_widget:
            self.setGeometry(self.parent_widget.rect())

    def refresh_notes(self):
        self.sync_geometry()
        self.update()

    def eventFilter(self, watched, event):
        if watched is self.parent_widget and QtCore:
            event_type = event.type()
            if event_type in (
                _qt_flag("QEvent", "Resize", fallback=QtCore.QEvent.Resize),
                _qt_flag("QEvent", "Show", fallback=QtCore.QEvent.Show),
                _qt_flag("QEvent", "Paint", fallback=QtCore.QEvent.Paint),
            ):
                self.sync_geometry()
                self.raise_()
        return False

    def paintEvent(self, event):
        if not QtGui:
            return
        settings = self.controller.timeline_customization()
        if not settings["overlay_enabled"]:
            return
        rects = self.controller.timeline_note_rects(self.width(), height=self.height())
        if not rects:
            return
        painter = QtGui.QPainter(self)
        antialiasing = getattr(QtGui.QPainter, "Antialiasing", None)
        if antialiasing is None and hasattr(QtGui.QPainter, "RenderHint"):
            antialiasing = getattr(QtGui.QPainter.RenderHint, "Antialiasing", None)
        if antialiasing is not None:
            painter.setRenderHint(antialiasing, True)
        for item in rects:
            note = item["note"]
            color = QtGui.QColor.fromRgbF(*_clean_color(note.get("color")))
            color.setAlphaF(_clamp(float(note.get("opacity", DEFAULT_NOTE_OPACITY)), 0.15, 1.0))
            border = QtGui.QColor(color)
            border.setAlphaF(min(1.0, color.alphaF() + 0.2))
            painter.setPen(QtGui.QPen(border, 1.0))
            painter.setBrush(QtGui.QBrush(color))
            painter.drawRoundedRect(
                QtCore.QRectF(float(item["x"]), float(item["y"]), float(item["width"]), float(item["height"])),
                3.0,
                3.0,
            )
        painter.end()


class MayaTimelineNotesController(object):
    def __init__(self):
        self.bookmark_api = _ensure_bookmark_api() if MAYA_AVAILABLE else None
        self.status_callback = None
        self.tooltip_filter = None
        self.tooltip_widget = None
        self.tooltip_bubble = None
        self.overlay_widget = None
        self.install_timeline_ui_hooks()

    def shutdown(self):
        if self.tooltip_filter and self.tooltip_widget:
            try:
                self.tooltip_widget.removeEventFilter(self.tooltip_filter)
            except Exception:
                pass
        self.tooltip_filter = None
        self.tooltip_widget = None
        if self.tooltip_bubble:
            try:
                self.tooltip_bubble.close()
                self.tooltip_bubble.deleteLater()
            except Exception:
                pass
        self.tooltip_bubble = None
        if self.overlay_widget:
            parent_widget = getattr(self.overlay_widget, "parent_widget", None)
            if parent_widget:
                try:
                    parent_widget.removeEventFilter(self.overlay_widget)
                except Exception:
                    pass
            try:
                self.overlay_widget.close()
                self.overlay_widget.deleteLater()
            except Exception:
                pass
        self.overlay_widget = None

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _set_status(self, message, success=True):
        if self.status_callback:
            self.status_callback(message, success)
        if success:
            _debug(message)
        else:
            _warning(message)

    def _install_tooltip_filter(self):
        if not QtWidgets:
            return
        widget = _time_slider_widget()
        if not widget:
            return
        if self.tooltip_filter:
            try:
                widget.removeEventFilter(self.tooltip_filter)
            except Exception:
                pass
        self.tooltip_widget = widget
        self.tooltip_filter = _TimelineTooltipFilter(self, widget)
        widget.installEventFilter(self.tooltip_filter)
        widget.setMouseTracking(True)

    def _install_overlay(self):
        if not QtWidgets:
            return
        widget = _time_slider_widget()
        if not widget:
            return
        if self.overlay_widget:
            try:
                self.overlay_widget.close()
                self.overlay_widget.deleteLater()
            except Exception:
                pass
            self.overlay_widget = None
        if not self.timeline_customization()["overlay_enabled"]:
            return
        self.overlay_widget = _TimelineNotesOverlay(self, widget)
        self.overlay_widget.refresh_notes()

    def install_timeline_ui_hooks(self):
        self._install_tooltip_filter()
        self._install_overlay()

    def refresh_timeline_overlay(self):
        if self.overlay_widget:
            try:
                self.overlay_widget.refresh_notes()
            except Exception:
                pass

    def hide_tooltip(self):
        if self.tooltip_bubble:
            try:
                self.tooltip_bubble.hide()
            except Exception:
                pass

    def show_tooltip(self, note, global_pos):
        if not QtWidgets:
            return
        if self.tooltip_bubble is None:
            self.tooltip_bubble = _TimelineNoteTooltipBubble(self)
        self.tooltip_bubble.show_note(note, global_pos)

    def timeline_customization(self):
        return _timeline_customization_settings()

    def set_timeline_customization(self, overlay_enabled=None, bar_height=None, tooltip_opacity=None, default_color=None):
        current = self.timeline_customization()
        if overlay_enabled is not None:
            current["overlay_enabled"] = bool(overlay_enabled)
            _set_option_var_int(TIMELINE_NOTES_OVERLAY_ENABLED_OPTION, int(current["overlay_enabled"]))
        if bar_height is not None:
            current["bar_height"] = int(_clamp(bar_height, 3, 24))
            _set_option_var_int(TIMELINE_NOTES_BAR_HEIGHT_OPTION, current["bar_height"])
        if tooltip_opacity is not None:
            current["tooltip_opacity"] = float(_clamp(tooltip_opacity, 0.25, 1.0))
            _set_option_var_float(TIMELINE_NOTES_TOOLTIP_OPACITY_OPTION, current["tooltip_opacity"])
        if default_color is not None:
            current["default_color"] = _clean_color(default_color)
            _set_option_var_color(TIMELINE_NOTES_DEFAULT_COLOR_OPTION, current["default_color"])
        self.install_timeline_ui_hooks()
        if self.tooltip_bubble:
            self.tooltip_bubble.setWindowOpacity(float(current["tooltip_opacity"]))
        return current

    def notes(self):
        if not MAYA_AVAILABLE:
            return []
        self.bookmark_api = self.bookmark_api or _ensure_bookmark_api()
        if not self.bookmark_api:
            return []
        return [_note_payload(node_name) for node_name in _bookmark_nodes(self.bookmark_api)]

    def notes_at_frame(self, frame_value):
        frame_value = int(frame_value)
        note_list = [
            item
            for item in self.notes()
            if int(item["start_frame"]) <= frame_value <= int(item["end_frame"])
        ]
        note_list.sort(key=lambda item: (int(item["start_frame"]), int(item["end_frame"]) - int(item["start_frame"]), item["title"].lower()))
        return note_list

    def note_at_widget_x(self, x_value, width):
        note_list = self.notes()
        if not note_list or width <= 0:
            return None
        playback_start, playback_end = _playback_range()
        if playback_end <= playback_start:
            return None
        ratio = max(0.0, min(1.0, float(x_value) / float(width)))
        frame_value = playback_start + ((playback_end - playback_start) * ratio)
        hits = [item for item in note_list if item["start_frame"] <= frame_value <= item["end_frame"]]
        if not hits:
            return None
        hits.sort(key=lambda item: (item["end_frame"] - item["start_frame"], item["start_frame"]))
        return hits[0]

    def timeline_note_rects(self, width, height=24, playback_start=None, playback_end=None):
        width = max(1, int(width))
        height = max(1, int(height))
        if playback_start is None or playback_end is None:
            playback_start, playback_end = _playback_range()
        playback_start = float(playback_start)
        playback_end = float(playback_end)
        if playback_end <= playback_start:
            return []
        settings = self.timeline_customization()
        bar_height = int(settings["bar_height"])
        y_value = max(0, height - bar_height - 2)
        rects = []
        for note in self.notes():
            start_frame = max(playback_start, float(note["start_frame"]))
            end_frame = min(playback_end, float(note["end_frame"]))
            if end_frame < playback_start or start_frame > playback_end:
                continue
            start_ratio = (start_frame - playback_start) / (playback_end - playback_start)
            end_ratio = (end_frame - playback_start) / (playback_end - playback_start)
            x_value = int(round(start_ratio * width))
            x_stop = int(round(end_ratio * width))
            rects.append(
                {
                    "note": note,
                    "x": max(0, min(width - 1, x_value)),
                    "y": y_value,
                    "width": max(3, min(width, x_stop) - max(0, min(width - 1, x_value))),
                    "height": bar_height,
                    "start_frame": int(note["start_frame"]),
                    "end_frame": int(note["end_frame"]),
                    "title": note["title"],
                }
            )
        return rects

    def tooltip_html(self, note):
        title = (note.get("title") or "").strip()
        preferred_text = _preferred_note_text(note)
        html_parts = [
            "<div style='font-weight:600; margin-bottom:6px;'>{0}</div>".format(
                _escape_html(preferred_text).replace("\n", "<br>")
            )
        ]
        if title and title != preferred_text:
            html_parts.append(
                "<div style='color:#BEBEBE; margin-bottom:4px;'>Title: {0}</div>".format(_escape_html(title))
            )
        html_parts.append(
            "<div style='color:#D0D0D0;'>{0}-{1}</div>".format(
                int(note["start_frame"]),
                int(note["end_frame"]),
            )
        )
        html = "".join(html_parts)
        return "<div style='max-width:{0}px'>{1}</div>".format(int(MAX_TOOLTIP_WIDTH), html)

    def create_note(self, title, start_frame, end_frame, color, opacity, text):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        self.bookmark_api = self.bookmark_api or _ensure_bookmark_api()
        if not self.bookmark_api:
            return False, "Maya's time slider bookmark plugin is not available."
        if int(end_frame) < int(start_frame):
            return False, "End Frame must be the same as or after Start Frame."
        title = (title or "").strip() or "Timeline Note"
        baked_color = _blend_color(color, opacity)
        if _has_playback_slider():
            bookmark = self.bookmark_api.createBookmark(name=title, start=int(start_frame), stop=int(end_frame), color=baked_color)
        else:
            bookmark = _direct_create_bookmark(self.bookmark_api, title, int(start_frame), int(end_frame), baked_color)
        _set_bool_attr(bookmark, NOTE_MARKER_ATTR, True)
        _set_string_attr(bookmark, NOTE_TITLE_ATTR, title)
        _set_string_attr(bookmark, NOTE_TEXT_ATTR, text)
        _set_string_attr(bookmark, NOTE_RGB_ATTR, json.dumps([float(value) for value in color]))
        _set_string_attr(bookmark, NOTE_EXPORT_ID_ATTR, bookmark)
        _set_double_attr(bookmark, NOTE_OPACITY_ATTR, opacity)
        self.refresh_timeline_overlay()
        return True, "Added timeline note from frame {0} to {1}.".format(int(start_frame), int(end_frame))

    def update_note(self, node_name, title, start_frame, end_frame, color, opacity, text):
        if not cmds.objExists(node_name):
            return False, "That note no longer exists in the scene."
        self.bookmark_api = self.bookmark_api or _ensure_bookmark_api()
        if not self.bookmark_api:
            return False, "Maya's time slider bookmark plugin is not available."
        if _has_playback_slider():
            self.bookmark_api.updateBookmark(node_name, start=int(start_frame), stop=int(end_frame))
        else:
            cmds.setAttr(node_name + ".timeRangeStart", float(start_frame))
            cmds.setAttr(node_name + ".timeRangeStop", float(end_frame))
        cmds.setAttr(node_name + ".name", title or "Timeline Note", type="string")
        cmds.setAttr(node_name + ".color", *_blend_color(color, opacity))
        _set_string_attr(node_name, NOTE_TITLE_ATTR, title or "Timeline Note")
        _set_string_attr(node_name, NOTE_TEXT_ATTR, text)
        _set_string_attr(node_name, NOTE_RGB_ATTR, json.dumps([float(value) for value in color]))
        _set_double_attr(node_name, NOTE_OPACITY_ATTR, opacity)
        self.refresh_timeline_overlay()
        return True, "Updated timeline note."

    def delete_note(self, node_name):
        if not MAYA_AVAILABLE or not cmds.objExists(node_name):
            return False, "That note is already gone."
        cmds.delete(node_name)
        self.refresh_timeline_overlay()
        return True, "Deleted the selected timeline note."

    def export_notes(self, file_path):
        note_list = self.notes()
        payload = {
            "version": 1,
            "notes": [
                {
                    "title": item["title"],
                    "start_frame": int(item["start_frame"]),
                    "end_frame": int(item["end_frame"]),
                    "color": [float(value) for value in item["color"]],
                    "opacity": float(item["opacity"]),
                    "text": item["text"],
                    "export_id": item["export_id"],
                }
                for item in note_list
            ],
        }
        with open(file_path, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return True, "Exported {0} timeline note(s).".format(len(payload["notes"]))

    def import_notes(self, file_path):
        with open(file_path, "r") as handle:
            payload = json.load(handle)
        notes = payload.get("notes") or []
        existing = {item["export_id"]: item for item in self.notes()}
        created = 0
        updated = 0
        for item in notes:
            export_id = item.get("export_id", "")
            color = tuple(item.get("color") or DEFAULT_NOTE_COLOR)
            opacity = float(item.get("opacity", DEFAULT_NOTE_OPACITY))
            if export_id and export_id in existing and cmds.objExists(existing[export_id]["node"]):
                success, _message = self.update_note(
                    existing[export_id]["node"],
                    item.get("title", "Timeline Note"),
                    item.get("start_frame", 1),
                    item.get("end_frame", 1),
                    color,
                    opacity,
                    item.get("text", ""),
                )
                if success:
                    updated += 1
            else:
                success, _message = self.create_note(
                    item.get("title", "Timeline Note"),
                    item.get("start_frame", 1),
                    item.get("end_frame", 1),
                    color,
                    opacity,
                    item.get("text", ""),
                )
                if success:
                    created += 1
        self.refresh_timeline_overlay()
        return True, "Imported {0} new note(s) and updated {1} existing note(s).".format(created, updated)


class _WindowBase(QtWidgets.QDialog if QtWidgets else object):
    pass


if QtWidgets:
    class MayaTimelineNotesWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaTimelineNotesWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.set_status_callback(self._set_status)
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Timeline Notes")
            self.setMinimumSize(360, 420)
            self.resize(760, 700)
            self._loading_note_fields = False
            self._last_highlighted_range = None
            self._last_current_frame_notes_state = None
            self._build_ui()
            self._refresh_notes()
            self._sync_highlighted_range_if_needed(force=True)
            self._refresh_current_frame_notes(force=True)

        def closeEvent(self, event):
            try:
                if hasattr(self, "range_sync_timer") and self.range_sync_timer:
                    self.range_sync_timer.stop()
            except Exception:
                pass
            try:
                if hasattr(self, "note_auto_update_timer") and self.note_auto_update_timer:
                    self.note_auto_update_timer.stop()
            except Exception:
                pass
            if os.environ.get("AMINATE_LEGACY_NATIVE_CLEANUP") == "1":
                # Explicit recovery-only teardown. Normal close hides/reuses.
                self.controller.shutdown()
            # Keep the time-slider overlay/controller alive for safe reuse.
            # Native destruction while Maya owns the Qt wrapper is unsafe.
            self.hide()
            event.ignore()

        def showEvent(self, event):
            try:
                if hasattr(self, "range_sync_timer") and self.range_sync_timer:
                    self.range_sync_timer.start()
            except Exception:
                pass
            try:
                if hasattr(self, "note_auto_update_timer") and self.note_auto_update_timer:
                    # Single-shot timer remains idle until a field changes.
                    self.note_auto_update_timer.stop()
            except Exception:
                pass
            try:
                super(MayaTimelineNotesWindow, self).showEvent(event)
            except Exception:
                pass

        def hideEvent(self, event):
            try:
                if hasattr(self, "range_sync_timer") and self.range_sync_timer:
                    self.range_sync_timer.stop()
            except Exception:
                pass
            try:
                if hasattr(self, "note_auto_update_timer") and self.note_auto_update_timer:
                    self.note_auto_update_timer.stop()
            except Exception:
                pass
            try:
                super(MayaTimelineNotesWindow, self).hideEvent(event)
            except Exception:
                pass

        def _build_ui(self):
            outer_layout = QtWidgets.QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName("timelineNotesContentScroll")
            scroll.setWidgetResizable(True)
            scroll.setMinimumWidth(0)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            content = QtWidgets.QWidget()
            content.setMinimumWidth(0)
            main_layout = QtWidgets.QVBoxLayout(content)
            intro = QtWidgets.QLabel(
                "Make colored timeline ranges with titles, note text, export/import, and hover help on the Maya time slider."
            )
            intro.setWordWrap(True)
            main_layout.addWidget(intro)

            self.tab_widget = QtWidgets.QTabWidget()
            self.tab_widget.setObjectName("timelineNotesTabWidget")
            self.notes_tab = QtWidgets.QWidget()
            self.notes_tab.setObjectName("timelineNotesNotesTab")
            notes_layout = QtWidgets.QVBoxLayout(self.notes_tab)
            self.customize_tab = QtWidgets.QWidget()
            self.customize_tab.setObjectName("timelineNotesCustomizeTab")

            form = QtWidgets.QGridLayout()
            self.title_line = QtWidgets.QLineEdit()
            self.title_line.setPlaceholderText("Run start, Contact pose, Camera beat")
            self.start_spin = QtWidgets.QSpinBox()
            self.start_spin.setRange(-100000, 100000)
            self.end_spin = QtWidgets.QSpinBox()
            self.end_spin.setRange(-100000, 100000)
            playback_start, playback_end = _playback_range() if MAYA_AVAILABLE else (1, 24)
            self.start_spin.setValue(int(playback_start))
            self.end_spin.setValue(int(playback_end))
            self.opacity_spin = QtWidgets.QDoubleSpinBox()
            self.opacity_spin.setDecimals(2)
            self.opacity_spin.setRange(0.1, 1.0)
            self.opacity_spin.setSingleStep(0.05)
            self.opacity_spin.setValue(DEFAULT_NOTE_OPACITY)
            self.color_button = QtWidgets.QPushButton("Pick Color")
            self.color_preview = QtWidgets.QLabel("      ")
            self.color_preview.setFrameShape(QtWidgets.QFrame.Box)
            self.note_text = QtWidgets.QPlainTextEdit()
            self.note_text.setPlaceholderText("Write the full formatted note here. New lines are kept in the hover tooltip.")
            form.addWidget(QtWidgets.QLabel("Title"), 0, 0)
            form.addWidget(self.title_line, 0, 1, 1, 3)
            form.addWidget(QtWidgets.QLabel("Start"), 1, 0)
            form.addWidget(self.start_spin, 1, 1)
            form.addWidget(QtWidgets.QLabel("End"), 1, 2)
            form.addWidget(self.end_spin, 1, 3)
            form.addWidget(QtWidgets.QLabel("Opacity"), 2, 0)
            form.addWidget(self.opacity_spin, 2, 1)
            form.addWidget(QtWidgets.QLabel("Color"), 2, 2)
            color_row = QtWidgets.QHBoxLayout()
            color_row.addWidget(self.color_button)
            color_row.addWidget(self.color_preview)
            color_holder = QtWidgets.QWidget()
            color_holder.setLayout(color_row)
            form.addWidget(color_holder, 2, 3)
            notes_layout.addLayout(form)
            notes_layout.addWidget(self.note_text, 1)

            range_row = QtWidgets.QHBoxLayout()
            self.auto_highlight_range_check = QtWidgets.QCheckBox("Auto Use Highlighted Range")
            self.auto_highlight_range_check.setChecked(True)
            self.auto_highlight_range_check.setToolTip("When this is on, the Start and End boxes follow the highlighted range on Maya's time slider.")
            self.auto_update_note_check = QtWidgets.QCheckBox("Auto Update Picked Note")
            self.auto_update_note_check.setChecked(True)
            self.auto_update_note_check.setToolTip("When this is on, changes you make to the picked note are saved straight back to the scene.")
            self.use_playback_range_button = QtWidgets.QPushButton("Use Playback Range")
            self.marking_menu_button = QtWidgets.QToolButton()
            self.marking_menu_button.setText("Marking Menu")
            self.marking_menu_button.setToolTip("Open the quick note-action menu. You can also right-click the Scene Notes list.")
            self.add_button = QtWidgets.QPushButton("Add Note")
            self.update_button = QtWidgets.QPushButton("Update Picked Note")
            self.delete_button = QtWidgets.QPushButton("Delete Picked Note")
            range_row.addWidget(self.auto_highlight_range_check)
            range_row.addWidget(self.auto_update_note_check)
            range_row.addWidget(self.use_playback_range_button)
            range_row.addWidget(self.marking_menu_button)
            range_row.addStretch(1)
            range_row.addWidget(self.add_button)
            range_row.addWidget(self.update_button)
            range_row.addWidget(self.delete_button)
            notes_layout.addLayout(range_row)

            notes_label = QtWidgets.QLabel("Scene Notes")
            notes_layout.addWidget(notes_label)
            self.notes_list = QtWidgets.QTreeWidget()
            self.notes_list.setHeaderLabels(["Title", "Range", "Opacity"])
            self.notes_list.setAlternatingRowColors(True)
            notes_layout.addWidget(self.notes_list, 1)

            self.current_frame_notes_label = QtWidgets.QLabel("Notes At Current Frame")
            notes_layout.addWidget(self.current_frame_notes_label)
            self.current_frame_notes_box = QtWidgets.QPlainTextEdit()
            self.current_frame_notes_box.setReadOnly(True)
            self.current_frame_notes_box.setPlaceholderText("Move the time slider into a note range to read the full note here.")
            self.current_frame_notes_box.setMaximumHeight(170)
            notes_layout.addWidget(self.current_frame_notes_box)

            file_row = QtWidgets.QHBoxLayout()
            self.export_button = QtWidgets.QPushButton("Export Notes")
            self.import_button = QtWidgets.QPushButton("Import Notes")
            file_row.addWidget(self.export_button)
            file_row.addWidget(self.import_button)
            file_row.addStretch(1)
            notes_layout.addLayout(file_row)

            help_box = QtWidgets.QPlainTextEdit()
            help_box.setReadOnly(True)
            help_box.setObjectName("timelineNotesHelpBox")
            help_box.setVisible(False)
            help_box.setPlainText(
                "1. Type a short title and the full note text.\n"
                "2. Leave Auto Use Highlighted Range on to follow the highlighted time-slider range, or turn it off and set Start and End yourself.\n"
                "3. Leave Auto Update Picked Note on if you want edits to save right away after you pick a note.\n"
                "4. Pick a color and opacity.\n"
                "5. Click Add Note.\n"
                "6. Hover over the colored range on the time slider to read the full note.\n"
                "7. Export Notes if you want to move them to another scene later."
            )
            help_toggle = QtWidgets.QToolButton()
            help_toggle.setText("How to use")
            help_toggle.setCheckable(True)
            help_toggle.setChecked(False)
            help_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            help_toggle.setToolTip("Show or hide the Timeline Notes quick guide.")
            help_toggle.toggled.connect(help_box.setVisible)
            notes_layout.addWidget(help_toggle)
            notes_layout.addWidget(help_box)

            self._build_customization_tab()
            self.tab_widget.addTab(self.notes_tab, "Notes")
            self.tab_widget.addTab(self.customize_tab, "Customize")
            main_layout.addWidget(self.tab_widget, 1)

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
            scroll.setWidget(content)
            outer_layout.addWidget(scroll)

            self.current_color = tuple(getattr(self, "default_note_color", DEFAULT_NOTE_COLOR))
            self._refresh_color_preview()
            self._build_marking_menu()
            self.range_sync_timer = QtCore.QTimer(self)
            self.range_sync_timer.setInterval(250)
            self.range_sync_timer.timeout.connect(self._poll_live_timeline_state)
            self.range_sync_timer.start()
            self.note_auto_update_timer = QtCore.QTimer(self)
            self.note_auto_update_timer.setSingleShot(True)
            self.note_auto_update_timer.setInterval(250)
            self.note_auto_update_timer.timeout.connect(self._auto_update_selected_note_if_needed)

            self.color_button.clicked.connect(self._pick_color)
            self.auto_highlight_range_check.toggled.connect(self._toggle_auto_highlight_range)
            self.auto_update_note_check.toggled.connect(self._toggle_auto_update_note)
            self.use_playback_range_button.clicked.connect(self._use_playback_range)
            self.add_button.clicked.connect(self._add_note)
            self.update_button.clicked.connect(self._update_note)
            self.delete_button.clicked.connect(self._delete_note)
            self.export_button.clicked.connect(self._export_notes)
            self.import_button.clicked.connect(self._import_notes)
            self.notes_list.itemSelectionChanged.connect(self._load_selected_note)
            self.notes_list.setContextMenuPolicy(_qt_flag("ContextMenuPolicy", "CustomContextMenu", QtCore.Qt.CustomContextMenu))
            self.notes_list.customContextMenuRequested.connect(self._show_notes_marking_menu_from_list)
            self.title_line.textChanged.connect(self._schedule_auto_update_note)
            self.start_spin.valueChanged.connect(self._schedule_auto_update_note)
            self.end_spin.valueChanged.connect(self._schedule_auto_update_note)
            self.opacity_spin.valueChanged.connect(self._handle_opacity_changed)
            self.note_text.textChanged.connect(self._schedule_auto_update_note)

        def _build_customization_tab(self):
            settings = self.controller.timeline_customization()
            self.default_note_color = tuple(settings["default_color"])
            layout = QtWidgets.QVBoxLayout(self.customize_tab)

            overlay_box = QtWidgets.QGroupBox("Timeline Display")
            overlay_layout = QtWidgets.QGridLayout(overlay_box)
            self.overlay_enabled_check = QtWidgets.QCheckBox("Show colored note ranges on Maya's timeline")
            self.overlay_enabled_check.setObjectName("timelineNotesOverlayEnabledCheck")
            self.overlay_enabled_check.setChecked(bool(settings["overlay_enabled"]))
            self.overlay_enabled_check.setToolTip("Draws Aminate note ranges on top of Maya's time slider so the notes are visible even when Maya's bookmark display changes.")
            self.bar_height_spin = QtWidgets.QSpinBox()
            self.bar_height_spin.setObjectName("timelineNotesBarHeightSpin")
            self.bar_height_spin.setRange(3, 24)
            self.bar_height_spin.setValue(int(settings["bar_height"]))
            self.bar_height_spin.setSuffix(" px")
            self.tooltip_opacity_spin = QtWidgets.QDoubleSpinBox()
            self.tooltip_opacity_spin.setObjectName("timelineNotesTooltipOpacitySpin")
            self.tooltip_opacity_spin.setDecimals(2)
            self.tooltip_opacity_spin.setRange(0.25, 1.0)
            self.tooltip_opacity_spin.setSingleStep(0.05)
            self.tooltip_opacity_spin.setValue(float(settings["tooltip_opacity"]))
            overlay_layout.addWidget(self.overlay_enabled_check, 0, 0, 1, 2)
            overlay_layout.addWidget(QtWidgets.QLabel("Range Bar Height"), 1, 0)
            overlay_layout.addWidget(self.bar_height_spin, 1, 1)
            overlay_layout.addWidget(QtWidgets.QLabel("Hover Bubble Opacity"), 2, 0)
            overlay_layout.addWidget(self.tooltip_opacity_spin, 2, 1)
            layout.addWidget(overlay_box)

            color_box = QtWidgets.QGroupBox("New Note Defaults")
            color_layout = QtWidgets.QHBoxLayout(color_box)
            self.default_color_button = QtWidgets.QPushButton("Default Note Color")
            self.default_color_button.setObjectName("timelineNotesDefaultColorButton")
            self.default_color_preview = QtWidgets.QLabel("      ")
            self.default_color_preview.setFrameShape(QtWidgets.QFrame.Box)
            color_layout.addWidget(self.default_color_button)
            color_layout.addWidget(self.default_color_preview)
            color_layout.addStretch(1)
            layout.addWidget(color_box)

            button_row = QtWidgets.QHBoxLayout()
            self.apply_customization_button = QtWidgets.QPushButton("Apply")
            self.reset_customization_button = QtWidgets.QPushButton("Reset Defaults")
            button_row.addWidget(self.apply_customization_button)
            button_row.addWidget(self.reset_customization_button)
            button_row.addStretch(1)
            layout.addLayout(button_row)
            layout.addStretch(1)

            self._refresh_default_color_preview()
            self.default_color_button.clicked.connect(self._pick_default_color)
            self.apply_customization_button.clicked.connect(self._apply_customization)
            self.reset_customization_button.clicked.connect(self._reset_customization)
            self.overlay_enabled_check.toggled.connect(self._apply_customization)
            self.bar_height_spin.valueChanged.connect(self._apply_customization)
            self.tooltip_opacity_spin.valueChanged.connect(self._apply_customization)

        def _build_marking_menu(self):
            self.marking_menu = QtWidgets.QMenu(self)
            self.marking_menu.aboutToShow.connect(self._sync_marking_menu_state)

            self.marking_menu_add_action = self.marking_menu.addAction("Add Note")
            self.marking_menu_update_action = self.marking_menu.addAction("Update Picked Note")
            self.marking_menu_delete_action = self.marking_menu.addAction("Delete Picked Note")
            self.marking_menu.addSeparator()
            self.marking_menu_playback_action = self.marking_menu.addAction("Use Playback Range")
            self.marking_menu_pick_color_action = self.marking_menu.addAction("Pick Color")
            self.marking_menu.addSeparator()
            self.marking_menu_auto_range_action = self.marking_menu.addAction("Auto Use Highlighted Range")
            self.marking_menu_auto_range_action.setCheckable(True)
            self.marking_menu_auto_update_action = self.marking_menu.addAction("Auto Update Picked Note")
            self.marking_menu_auto_update_action.setCheckable(True)
            self.marking_menu.addSeparator()
            self.marking_menu_export_action = self.marking_menu.addAction("Export Notes")
            self.marking_menu_import_action = self.marking_menu.addAction("Import Notes")

            self.marking_menu_add_action.triggered.connect(self._add_note)
            self.marking_menu_update_action.triggered.connect(self._update_note)
            self.marking_menu_delete_action.triggered.connect(self._delete_note)
            self.marking_menu_playback_action.triggered.connect(self._use_playback_range)
            self.marking_menu_pick_color_action.triggered.connect(self._pick_color)
            self.marking_menu_auto_range_action.toggled.connect(self.auto_highlight_range_check.setChecked)
            self.marking_menu_auto_update_action.toggled.connect(self.auto_update_note_check.setChecked)
            self.marking_menu_export_action.triggered.connect(self._export_notes)
            self.marking_menu_import_action.triggered.connect(self._import_notes)

            self.marking_menu_button.setMenu(self.marking_menu)
            popup_mode = getattr(QtWidgets.QToolButton, "InstantPopup", None)
            if popup_mode is None and hasattr(QtWidgets.QToolButton, "ToolButtonPopupMode"):
                popup_mode = QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
            if popup_mode is not None:
                self.marking_menu_button.setPopupMode(popup_mode)

        def _sync_marking_menu_state(self):
            has_selection = bool(self._selected_node())
            self.marking_menu_update_action.setEnabled(has_selection)
            self.marking_menu_delete_action.setEnabled(has_selection)
            self.marking_menu_auto_range_action.blockSignals(True)
            self.marking_menu_auto_range_action.setChecked(self.auto_highlight_range_check.isChecked())
            self.marking_menu_auto_range_action.blockSignals(False)
            self.marking_menu_auto_update_action.blockSignals(True)
            self.marking_menu_auto_update_action.setChecked(self.auto_update_note_check.isChecked())
            self.marking_menu_auto_update_action.blockSignals(False)

        def _show_marking_menu(self, global_pos):
            self._sync_marking_menu_state()
            try:
                self.marking_menu.exec(global_pos)
            except Exception:
                self.marking_menu.exec_(global_pos)

        def _show_notes_marking_menu_from_list(self, position):
            self._show_marking_menu(self.notes_list.viewport().mapToGlobal(position))

        def _refresh_color_preview(self):
            color = QtGui.QColor.fromRgbF(*_blend_color(self.current_color, self.opacity_spin.value()))
            self.color_preview.setStyleSheet("background-color: {0};".format(color.name()))

        def _refresh_default_color_preview(self):
            color = QtGui.QColor.fromRgbF(*_clean_color(self.default_note_color))
            self.default_color_preview.setStyleSheet("background-color: {0};".format(color.name()))

        def _pick_default_color(self):
            current = QtGui.QColor.fromRgbF(*_clean_color(self.default_note_color))
            chosen = QtWidgets.QColorDialog.getColor(current, self, "Pick Default Timeline Note Color")
            if not chosen.isValid():
                return
            self.default_note_color = (chosen.redF(), chosen.greenF(), chosen.blueF())
            self._refresh_default_color_preview()
            self._apply_customization()

        def _apply_customization(self, *_args):
            if not hasattr(self, "overlay_enabled_check"):
                return
            settings = self.controller.set_timeline_customization(
                overlay_enabled=self.overlay_enabled_check.isChecked(),
                bar_height=self.bar_height_spin.value(),
                tooltip_opacity=self.tooltip_opacity_spin.value(),
                default_color=self.default_note_color,
            )
            self.default_note_color = tuple(settings["default_color"])
            if not self._selected_node():
                self.current_color = tuple(self.default_note_color)
                self._refresh_color_preview()
            self._refresh_default_color_preview()
            self._set_status("Timeline note display settings updated.", True)

        def _reset_customization(self):
            defaults = _timeline_customization_defaults()
            self.overlay_enabled_check.blockSignals(True)
            self.bar_height_spin.blockSignals(True)
            self.tooltip_opacity_spin.blockSignals(True)
            self.overlay_enabled_check.setChecked(bool(defaults["overlay_enabled"]))
            self.bar_height_spin.setValue(int(defaults["bar_height"]))
            self.tooltip_opacity_spin.setValue(float(defaults["tooltip_opacity"]))
            self.overlay_enabled_check.blockSignals(False)
            self.bar_height_spin.blockSignals(False)
            self.tooltip_opacity_spin.blockSignals(False)
            self.default_note_color = tuple(defaults["default_color"])
            self._apply_customization()

        def _refresh_notes(self, selected_node=""):
            self.notes_list.clear()
            node_to_select = selected_node or ""
            selected_item = None
            for note in self.controller.notes():
                item = QtWidgets.QTreeWidgetItem(
                    [
                        note["title"],
                        "{0}-{1}".format(int(note["start_frame"]), int(note["end_frame"])),
                        "{0:.2f}".format(float(note["opacity"])),
                    ]
                )
                item.setData(0, QtCore.Qt.UserRole, note["node"])
                tooltip_text = _preferred_note_text(note)
                for column in range(3):
                    item.setToolTip(column, tooltip_text)
                color = QtGui.QColor.fromRgbF(*_blend_color(note["color"], note["opacity"]))
                for column in range(3):
                    item.setBackground(column, QtGui.QBrush(color))
                self.notes_list.addTopLevelItem(item)
                if node_to_select and note["node"] == node_to_select:
                    selected_item = item
            if selected_item is not None:
                self.notes_list.setCurrentItem(selected_item)
                selected_item.setSelected(True)
            self._refresh_current_frame_notes(force=True)

        def _load_selected_note(self):
            items = self.notes_list.selectedItems()
            if not items:
                return
            node_name = items[0].data(0, QtCore.Qt.UserRole)
            note = next((item for item in self.controller.notes() if item["node"] == node_name), None)
            if not note:
                return
            self._loading_note_fields = True
            try:
                self.title_line.setText(note["title"])
                self.start_spin.setValue(int(note["start_frame"]))
                self.end_spin.setValue(int(note["end_frame"]))
                self.opacity_spin.setValue(float(note["opacity"]))
                self.current_color = tuple(note["color"])
                self.note_text.setPlainText(note["text"])
                self._refresh_color_preview()
            finally:
                self._loading_note_fields = False

        def _selected_node(self):
            items = self.notes_list.selectedItems()
            if not items:
                return ""
            return items[0].data(0, QtCore.Qt.UserRole) or ""

        def _selected_note_payload(self):
            node_name = self._selected_node()
            if not node_name:
                return None
            return next((item for item in self.controller.notes() if item["node"] == node_name), None)

        def _pick_color(self):
            current = QtGui.QColor.fromRgbF(*self.current_color)
            chosen = QtWidgets.QColorDialog.getColor(current, self, "Pick Timeline Note Color")
            if chosen.isValid():
                self.current_color = (chosen.redF(), chosen.greenF(), chosen.blueF())
                self._refresh_color_preview()
                self._schedule_auto_update_note()

        def _handle_opacity_changed(self, *_args):
            self._refresh_color_preview()
            self._schedule_auto_update_note()

        def _poll_live_timeline_state(self):
            if not self.isVisible():
                return
            self._sync_highlighted_range_if_needed()
            self._refresh_current_frame_notes()

        def _current_frame_notes_text(self, frame_value, note_list):
            if not note_list:
                return "Frame {0}\n\nNo note at this frame yet.".format(int(frame_value))
            chunks = ["Frame {0}".format(int(frame_value))]
            for note in note_list:
                chunks.append(
                    "{0} ({1}-{2})\n{3}".format(
                        note["title"],
                        int(note["start_frame"]),
                        int(note["end_frame"]),
                        note["text"] or "No extra note text yet.",
                    )
                )
            return "\n\n".join(chunks)

        def _refresh_current_frame_notes(self, force=False):
            frame_value = _current_frame()
            if frame_value is None:
                if force:
                    self.current_frame_notes_box.setPlainText("Current frame is not available right now.")
                return
            note_list = self.controller.notes_at_frame(frame_value)
            state = (
                int(frame_value),
                tuple(
                    (
                        note["node"],
                        note["title"],
                        int(note["start_frame"]),
                        int(note["end_frame"]),
                        float(note["opacity"]),
                        note["text"] or "",
                    )
                    for note in note_list
                ),
            )
            if not force and state == self._last_current_frame_notes_state:
                return
            self.current_frame_notes_box.setPlainText(self._current_frame_notes_text(frame_value, note_list))
            self._last_current_frame_notes_state = state

        def _apply_range_values(self, start_frame, end_frame):
            self.start_spin.blockSignals(True)
            self.end_spin.blockSignals(True)
            self.start_spin.setValue(int(start_frame))
            self.end_spin.setValue(int(end_frame))
            self.start_spin.blockSignals(False)
            self.end_spin.blockSignals(False)

        def _sync_highlighted_range_if_needed(self, force=False, announce=False):
            if not self.auto_highlight_range_check.isChecked():
                self._last_highlighted_range = None
                return
            current_range = _selected_time_range()
            if not current_range:
                if force and announce:
                    self._set_status("Highlight a range on the time slider to auto-fill Start and End.", False)
                return
            current_range = (int(current_range[0]), int(current_range[1]))
            existing_range = (int(self.start_spin.value()), int(self.end_spin.value()))
            if not force and current_range == self._last_highlighted_range and current_range == existing_range:
                return
            self._apply_range_values(*current_range)
            self._last_highlighted_range = current_range
            self._schedule_auto_update_note()
            if announce:
                self._set_status("Start and End now follow the highlighted time-slider range.", True)

        def _toggle_auto_highlight_range(self, checked):
            if checked:
                self._sync_highlighted_range_if_needed(force=True, announce=True)
            else:
                self._last_highlighted_range = None
                self._set_status("Auto highlighted-range sync turned off.", True)

        def _toggle_auto_update_note(self, checked):
            if not checked:
                self.note_auto_update_timer.stop()
                self._set_status("Auto update for the picked note turned off.", True)
                return
            self._set_status("Picked note changes will now save automatically.", True)
            self._schedule_auto_update_note()

        def _use_playback_range(self):
            if self.auto_highlight_range_check.isChecked():
                self.auto_highlight_range_check.setChecked(False)
            playback_start, playback_end = _playback_range()
            self._apply_range_values(int(playback_start), int(playback_end))
            self._schedule_auto_update_note()
            self._set_status("Copied the playback range.", True)

        def _current_note_values(self):
            return {
                "title": self.title_line.text() or "Timeline Note",
                "start_frame": int(self.start_spin.value()),
                "end_frame": int(self.end_spin.value()),
                "color": tuple(float(value) for value in self.current_color),
                "opacity": float(self.opacity_spin.value()),
                "text": self.note_text.toPlainText(),
            }

        def _schedule_auto_update_note(self, *_args):
            if self._loading_note_fields:
                return
            if not self.auto_update_note_check.isChecked():
                return
            if not self._selected_node():
                return
            self.note_auto_update_timer.start()

        def _auto_update_selected_note_if_needed(self):
            if self._loading_note_fields:
                return
            if not self.auto_update_note_check.isChecked():
                return
            note = self._selected_note_payload()
            if not note:
                return
            current = self._current_note_values()
            if (
                note["title"] == current["title"]
                and int(note["start_frame"]) == current["start_frame"]
                and int(note["end_frame"]) == current["end_frame"]
                and abs(float(note["opacity"]) - current["opacity"]) < 0.0001
                and tuple(float(value) for value in note["color"]) == current["color"]
                and (note["text"] or "") == current["text"]
            ):
                return
            success, message = self.controller.update_note(
                note["node"],
                current["title"],
                current["start_frame"],
                current["end_frame"],
                current["color"],
                current["opacity"],
                current["text"],
            )
            self._refresh_notes(selected_node=note["node"])
            if success:
                self._set_status("Picked note updated automatically.", True)
            else:
                self._set_status(message, False)

        def _add_note(self):
            success, message = self.controller.create_note(
                self.title_line.text(),
                self.start_spin.value(),
                self.end_spin.value(),
                self.current_color,
                self.opacity_spin.value(),
                self.note_text.toPlainText(),
            )
            self._refresh_notes()
            self._set_status(message, success)

        def _update_note(self):
            node_name = self._selected_node()
            if not node_name:
                self._set_status("Pick a note from the list first.", False)
                return
            success, message = self.controller.update_note(
                node_name,
                self.title_line.text(),
                self.start_spin.value(),
                self.end_spin.value(),
                self.current_color,
                self.opacity_spin.value(),
                self.note_text.toPlainText(),
            )
            self._refresh_notes(selected_node=node_name)
            self._set_status(message, success)

        def _delete_note(self):
            node_name = self._selected_node()
            if not node_name:
                self._set_status("Pick a note from the list first.", False)
                return
            success, message = self.controller.delete_note(node_name)
            self._refresh_notes()
            self._set_status(message, success)

        def _export_notes(self):
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Timeline Notes", "", EXPORT_FILE_FILTER)
            if not file_path:
                return
            success, message = self.controller.export_notes(file_path)
            self._set_status(message, success)

        def _import_notes(self):
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import Timeline Notes", "", EXPORT_FILE_FILTER)
            if not file_path:
                return
            success, message = self.controller.import_notes(file_path)
            self._refresh_notes()
            self._set_status(message, success)

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)

        def _open_follow_url(self, *_args):
            _open_external_url(FOLLOW_AMIR_URL)

        def _open_donate_url(self):
            _open_external_url(DONATE_URL)


def launch_maya_timeline_notes(dock=False):
    global GLOBAL_CONTROLLER, GLOBAL_WINDOW
    if not (MAYA_AVAILABLE and QtWidgets):
        raise RuntimeError("Maya Timeline Notes must be launched inside Maya with PySide available.")

    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
            GLOBAL_CONTROLLER = None

    GLOBAL_CONTROLLER = MayaTimelineNotesController()
    GLOBAL_WINDOW = MayaTimelineNotesWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "DONATE_URL",
    "FOLLOW_AMIR_URL",
    "MayaTimelineNotesController",
    "MayaTimelineNotesWindow",
    "launch_maya_timeline_notes",
]
