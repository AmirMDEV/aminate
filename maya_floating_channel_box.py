from __future__ import absolute_import, division, print_function

import functools
import re
import time

try:
    import maya.cmds as cmds
    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    MAYA_AVAILABLE = False

try:
    import maya.mel as mel
except Exception:
    mel = None

try:
    import maya.OpenMayaUI as omui
except Exception:
    omui = None

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    import shiboken6 as shiboken
except Exception:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
        import shiboken2 as shiboken
    except Exception:
        QtCore = QtGui = QtWidgets = None
        shiboken = None


HOTKEY_OPTION = "AmirMayaAnimWorkflowFloatingChannelBoxHotkey"
CHANNEL_OPACITY_OPTION = "AmirMayaAnimWorkflowFloatingChannelBoxOpacity"
GRAPH_EDITOR_HOTKEY_OPTION = "AmirMayaAnimWorkflowFloatingGraphEditorHotkey"
GRAPH_EDITOR_OPACITY_OPTION = "AmirMayaAnimWorkflowFloatingGraphEditorOpacity"
DEFAULT_HOTKEY = "#"
DEFAULT_CHANNEL_OPACITY = 0.84
LEGACY_DEFAULT_GRAPH_EDITOR_HOTKEYS = ("Ctrl+Alt+G", "Apostrophe", "Semicolon", "Ctrl+Backslash")
DEFAULT_GRAPH_EDITOR_HOTKEY = "Ctrl+Semicolon"
DEFAULT_GRAPH_EDITOR_OPACITY = 0.88
DEFAULT_OPACITY = DEFAULT_CHANNEL_OPACITY
CURSOR_OPEN_OFFSET = 18
SCREEN_EDGE_MARGIN = 10
DEFAULT_GRAPH_EDITOR_WIDTH = 1180
DEFAULT_GRAPH_EDITOR_HEIGHT = 640
DEFAULT_GRAPH_EDITOR_OUTLINER_WIDTH = 320
GRAPH_EDITOR_HEADER_HEIGHT = 34
GRAPH_EDITOR_MIN_BODY_HEIGHT = 320
NUMERIC_EDIT_FLUSH_INTERVAL_MS = 33
FLOATING_OBJECT_NAME = "aminateFloatingChannelBoxWindow"
GRAPH_EDITOR_WINDOW_NAME = "aminateFloatingGraphEditorWindow"
GRAPH_EDITOR_WORKSPACE_CONTROL_NAME = GRAPH_EDITOR_WINDOW_NAME + "WorkspaceControl"
GRAPH_EDITOR_CONTAINER_NAME = "aminateFloatingGraphEditorContainer"
GRAPH_EDITOR_HEADER_NAME = "aminateFloatingGraphEditorHeader"
GRAPH_EDITOR_PANEL_NAME = "aminateFloatingGraphEditorPanel"
GRAPH_EDITOR_OUTLINER_PANEL_NAME = "aminateFloatingGraphEditorOutlinerPanel"
GRAPH_EDITOR_PANE_NAME = "aminateFloatingGraphEditorPane"
_GLOBAL_MANAGER = None
_GRAPH_EDITOR_RESIZE_FILTER = None


if QtCore:
    class _GraphEditorResizeFilter(QtCore.QObject):
        def eventFilter(self, watched, event):
            try:
                resize_event = getattr(QtCore.QEvent, "Resize", None)
                if resize_event is not None and event.type() == resize_event:
                    _schedule_graph_editor_resize()
            except Exception:
                pass
            return False


def _short_name(node_name):
    return (node_name or "").split("|")[-1]


def _option_var_string(option_name, default_value):
    if not cmds or not cmds.optionVar(exists=option_name):
        return default_value
    try:
        value = cmds.optionVar(query=option_name)
        return value if value else default_value
    except Exception:
        return default_value


def _save_option_var_string(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(stringValue=(option_name, value or ""))
    except Exception:
        pass


def _clamp(value, min_value, max_value):
    return max(float(min_value), min(float(max_value), float(value)))


def _option_var_float(option_name, default_value):
    if not cmds or not cmds.optionVar(exists=option_name):
        return float(default_value)
    try:
        return float(cmds.optionVar(query=option_name))
    except Exception:
        return float(default_value)


def _save_option_var_float(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(floatValue=(option_name, float(value)))
    except Exception:
        pass


def get_hotkey():
    return _option_var_string(HOTKEY_OPTION, DEFAULT_HOTKEY)


def get_channel_opacity():
    return _clamp(_option_var_float(CHANNEL_OPACITY_OPTION, DEFAULT_CHANNEL_OPACITY), 0.2, 1.0)


def set_channel_opacity(opacity):
    opacity = _clamp(opacity, 0.2, 1.0)
    _save_option_var_float(CHANNEL_OPACITY_OPTION, opacity)
    manager = install_global_hotkey()
    if manager:
        manager.set_channel_opacity(opacity)
    return opacity


def get_graph_editor_hotkey():
    value = _option_var_string(GRAPH_EDITOR_HOTKEY_OPTION, DEFAULT_GRAPH_EDITOR_HOTKEY)
    if normalize_hotkey(value, default_value=DEFAULT_GRAPH_EDITOR_HOTKEY) in LEGACY_DEFAULT_GRAPH_EDITOR_HOTKEYS:
        _save_option_var_string(GRAPH_EDITOR_HOTKEY_OPTION, DEFAULT_GRAPH_EDITOR_HOTKEY)
        return DEFAULT_GRAPH_EDITOR_HOTKEY
    return value


def set_graph_editor_hotkey(hotkey_text):
    hotkey_text = normalize_hotkey(hotkey_text, default_value=DEFAULT_GRAPH_EDITOR_HOTKEY)
    _save_option_var_string(GRAPH_EDITOR_HOTKEY_OPTION, hotkey_text)
    manager = install_global_hotkey()
    if manager:
        manager.set_graph_hotkey(hotkey_text)
    return hotkey_text


def get_graph_editor_opacity():
    return _clamp(_option_var_float(GRAPH_EDITOR_OPACITY_OPTION, DEFAULT_GRAPH_EDITOR_OPACITY), 0.2, 1.0)


def set_graph_editor_opacity(opacity):
    opacity = _clamp(opacity, 0.2, 1.0)
    _save_option_var_float(GRAPH_EDITOR_OPACITY_OPTION, opacity)
    _apply_graph_editor_opacity(opacity)
    return opacity


def set_hotkey(hotkey_text):
    hotkey_text = normalize_hotkey(hotkey_text)
    _save_option_var_string(HOTKEY_OPTION, hotkey_text)
    manager = install_global_hotkey(hotkey_text)
    if manager:
        manager.set_channel_hotkey(hotkey_text)
    return hotkey_text


def normalize_hotkey(hotkey_text, default_value=DEFAULT_HOTKEY):
    text = (hotkey_text or "").strip()
    if not text:
        return default_value
    text = re.sub(r"\s*\+\s*", "+", text)
    text = re.sub(r"\s*-\s*", "+", text)
    text = re.sub(r"\s+", "+", text)
    if text == "#":
        return "#"
    if text in (";", ":", "'", "`"):
        return {
            ";": "Semicolon",
            ":": "Semicolon",
            "'": "Apostrophe",
            "`": "Backquote",
        }.get(text, text)
    if text == "\\":
        return "Backslash"
    lowered = text.lower().replace(" ", "").replace("+", "")
    if lowered in ("semicolon", "semi", "semicolonkey"):
        return "Semicolon"
    if lowered in ("apostrophe", "quote", "singlequote"):
        return "Apostrophe"
    if lowered in ("backquote", "backtick", "grave", "graveaccent"):
        return "Backquote"
    if lowered in ("backslash", "slashback", "\\"):
        return "Backslash"
    if lowered in ("alt", "leftalt", "lalt"):
        return "Left Alt"
    if lowered in ("rightalt", "ralt", "altgr"):
        return "Right Alt"
    parts = []
    modifier_order = {"Ctrl": 0, "Shift": 1, "Alt": 2, "Meta": 3}
    seen_modifiers = set()
    key_part = ""
    for part in text.split("+"):
        part = part.strip()
        if not part:
            continue
        low = part.lower()
        if low in ("ctrl", "control"):
            seen_modifiers.add("Ctrl")
        elif low == "shift":
            seen_modifiers.add("Shift")
        elif low in ("alt", "left alt", "leftalt", "lalt"):
            seen_modifiers.add("Alt")
        elif low in ("cmd", "meta", "win", "windows"):
            seen_modifiers.add("Meta")
        else:
            key_part = part.upper() if len(part) == 1 else {
                ";": "Semicolon",
                ":": "Semicolon",
                "'": "Apostrophe",
                "`": "Backquote",
                "\\": "Backslash",
                "semi": "Semicolon",
                "semicolon": "Semicolon",
                "semicolonkey": "Semicolon",
                "quote": "Apostrophe",
                "singlequote": "Apostrophe",
                "apostrophe": "Apostrophe",
                "backtick": "Backquote",
                "backquote": "Backquote",
                "grave": "Backquote",
                "graveaccent": "Backquote",
                "backslash": "Backslash",
            }.get(low, part)
    for modifier in sorted(seen_modifiers, key=lambda value: modifier_order[value]):
        parts.append(modifier)
    if key_part:
        parts.append(key_part)
    return "+".join(parts) if parts else default_value


def _qt_modifier_value(name):
    if not QtCore:
        return 0
    def _as_int(value):
        try:
            return int(value)
        except TypeError:
            return int(getattr(value, "value", 0))
    value = getattr(QtCore.Qt, name, None)
    if value is not None:
        return _as_int(value)
    enum = getattr(QtCore.Qt, "KeyboardModifier", None)
    if enum and hasattr(enum, name):
        return _as_int(getattr(enum, name))
    return 0


def _qt_shortcut_context_value(name):
    if not QtCore:
        return None
    value = getattr(QtCore.Qt, name, None)
    if value is not None:
        return value
    enum = getattr(QtCore.Qt, "ShortcutContext", None)
    if enum and hasattr(enum, name):
        return getattr(enum, name)
    return None


def _qt_key_value(name):
    if not QtCore:
        return None
    def _as_int(value):
        try:
            return int(value)
        except TypeError:
            return int(getattr(value, "value", 0))
    value = getattr(QtCore.Qt, name, None)
    if value is not None:
        return _as_int(value)
    enum = getattr(QtCore.Qt, "Key", None)
    if enum and hasattr(enum, name):
        return _as_int(getattr(enum, name))
    return None


def _modifier_mask():
    return (
        _qt_modifier_value("ControlModifier")
        | _qt_modifier_value("ShiftModifier")
        | _qt_modifier_value("AltModifier")
        | _qt_modifier_value("MetaModifier")
    )


def _key_name_to_qt(key_name):
    if not QtCore:
        return None
    name = (key_name or "").strip()
    if not name:
        return None
    aliases = {
        "ESC": "Escape",
        "RETURN": "Return",
        "ENTER": "Enter",
        "SPACE": "Space",
        "TAB": "Tab",
        "#": "NumberSign",
        "HASH": "NumberSign",
        "NUMBERSIGN": "NumberSign",
        ";": "Semicolon",
        ":": "Semicolon",
        "SEMICOLON": "Semicolon",
        "SEMI": "Semicolon",
        "'": "Apostrophe",
        "QUOTE": "Apostrophe",
        "SINGLEQUOTE": "Apostrophe",
        "APOSTROPHE": "Apostrophe",
        "`": "QuoteLeft",
        "BACKQUOTE": "QuoteLeft",
        "BACKTICK": "QuoteLeft",
        "GRAVE": "QuoteLeft",
        "\\": "Backslash",
        "BACKSLASH": "Backslash",
        "LEFT ALT": "Alt",
        "RIGHT ALT": "Alt",
        "ALT": "Alt",
    }
    if name == "#":
        value = _qt_key_value("Key_NumberSign")
        return value if value is not None else ord("#")
    lookup = aliases.get(name.upper(), name)
    qt_name = "Key_" + lookup.replace(" ", "")
    value = _qt_key_value(qt_name)
    if value is not None:
        return value
    if len(name) == 1:
        return _qt_key_value("Key_" + name.upper())
    return None


def _qt_mouse_button_value(name):
    if not QtCore:
        return 0
    value = getattr(QtCore.Qt, name, None)
    if value is not None:
        try:
            return int(value)
        except TypeError:
            return int(getattr(value, "value", 0))
    enum = getattr(QtCore.Qt, "MouseButton", None)
    if enum and hasattr(enum, name):
        value = getattr(enum, name)
        try:
            return int(value)
        except TypeError:
            return int(getattr(value, "value", 0))
    return 0


def _enum_int(value, default=0):
    try:
        return int(value)
    except Exception:
        try:
            return int(getattr(value, "value", default))
        except Exception:
            return int(default)


def _qt_shortcut_text(hotkey_text, default_value=DEFAULT_GRAPH_EDITOR_HOTKEY):
    normalized = normalize_hotkey(hotkey_text, default_value=default_value)
    sequence_parts = []
    for part in normalized.split("+"):
        label = part.strip()
        replacement = {
            "Semicolon": ";",
            "Apostrophe": "'",
            "Backquote": "`",
            "Backslash": "\\",
        }.get(label, label)
        sequence_parts.append(replacement)
    return "+".join(sequence_parts)


def _event_global_pos(event):
    try:
        return event.globalPosition().toPoint()
    except Exception:
        try:
            return event.globalPos()
        except Exception:
            return QtGui.QCursor.pos() if QtGui else None


def _screen_available_geometry(point=None):
    if not QtWidgets or not QtGui:
        return None
    app = QtWidgets.QApplication.instance()
    screen = None
    point = point or QtGui.QCursor.pos()
    try:
        screen = QtGui.QGuiApplication.screenAt(point)
    except Exception:
        screen = None
    if screen is None and app:
        try:
            screen = app.primaryScreen()
        except Exception:
            screen = None
    if screen:
        try:
            return screen.availableGeometry()
        except Exception:
            pass
    if app:
        try:
            return app.desktop().availableGeometry(point)
        except Exception:
            pass
    return None


def _clamped_top_left_near_cursor(width, height, cursor_pos=None):
    if not QtCore or not QtGui:
        return None
    cursor_pos = cursor_pos or QtGui.QCursor.pos()
    geometry = _screen_available_geometry(cursor_pos)
    if geometry is None:
        return cursor_pos + QtCore.QPoint(CURSOR_OPEN_OFFSET, CURSOR_OPEN_OFFSET)
    width = max(80, int(width or 320))
    height = max(80, int(height or 240))
    x_pos = cursor_pos.x() + CURSOR_OPEN_OFFSET
    y_pos = cursor_pos.y() + CURSOR_OPEN_OFFSET
    if x_pos + width + SCREEN_EDGE_MARGIN > geometry.right():
        x_pos = cursor_pos.x() - width - CURSOR_OPEN_OFFSET
    if y_pos + height + SCREEN_EDGE_MARGIN > geometry.bottom():
        y_pos = cursor_pos.y() - height - CURSOR_OPEN_OFFSET
    x_pos = max(geometry.left() + SCREEN_EDGE_MARGIN, min(x_pos, geometry.right() - width - SCREEN_EDGE_MARGIN))
    y_pos = max(geometry.top() + SCREEN_EDGE_MARGIN, min(y_pos, geometry.bottom() - height - SCREEN_EDGE_MARGIN))
    return QtCore.QPoint(int(x_pos), int(y_pos))


def _move_widget_near_cursor(widget, width=None, height=None):
    if not widget or not QtCore:
        return False
    try:
        if width and height:
            widget.resize(int(width), int(height))
        size = widget.frameGeometry().size() if widget.isVisible() else widget.sizeHint()
        width = width or size.width() or widget.width()
        height = height or size.height() or widget.height()
        point = _clamped_top_left_near_cursor(width, height)
        if point is not None:
            widget.move(point)
            return True
    except Exception:
        pass
    return False


def _move_widget_within_screen(widget, top_left):
    if not widget or top_left is None or not QtCore:
        return False
    try:
        geometry = _screen_available_geometry(top_left)
        width = widget.frameGeometry().width() or widget.width()
        height = widget.frameGeometry().height() or widget.height()
        if geometry is None:
            widget.move(top_left)
            return True
        x_pos = max(geometry.left() + SCREEN_EDGE_MARGIN, min(top_left.x(), geometry.right() - width - SCREEN_EDGE_MARGIN))
        y_pos = max(geometry.top() + SCREEN_EDGE_MARGIN, min(top_left.y(), geometry.bottom() - height - SCREEN_EDGE_MARGIN))
        widget.move(int(x_pos), int(y_pos))
        return True
    except Exception:
        pass
    return False


def hotkey_to_parts(hotkey_text):
    text = normalize_hotkey(hotkey_text)
    lowered = text.lower()
    if lowered in ("left alt", "right alt"):
        return {"key": _key_name_to_qt("Alt"), "modifiers": 0, "side": lowered.split(" ", 1)[0]}
    if text == "#":
        return {"key": _key_name_to_qt("#"), "modifiers": 0, "side": "", "text": "#"}
    modifiers = 0
    key_name = ""
    for part in text.split("+"):
        low = part.strip().lower()
        if low == "ctrl":
            modifiers |= _qt_modifier_value("ControlModifier")
        elif low == "shift":
            modifiers |= _qt_modifier_value("ShiftModifier")
        elif low == "alt":
            modifiers |= _qt_modifier_value("AltModifier")
        elif low == "meta":
            modifiers |= _qt_modifier_value("MetaModifier")
        else:
            key_name = part.strip()
    return {"key": _key_name_to_qt(key_name), "modifiers": modifiers, "side": ""}


def graph_hotkey_to_parts(hotkey_text):
    return hotkey_to_parts(normalize_hotkey(hotkey_text, default_value=DEFAULT_GRAPH_EDITOR_HOTKEY))


def _is_text_entry_widget(widget):
    if not QtWidgets or widget is None:
        return False
    text_widgets = (
        QtWidgets.QLineEdit,
        QtWidgets.QPlainTextEdit,
        QtWidgets.QTextEdit,
        QtWidgets.QSpinBox,
        QtWidgets.QDoubleSpinBox,
        QtWidgets.QComboBox,
    )
    return isinstance(widget, text_widgets)


def _selected_nodes():
    if not MAYA_AVAILABLE or not cmds:
        return []
    selected = cmds.ls(selection=True, long=True) or []
    nodes = []
    for node_name in selected:
        try:
            node_type = cmds.nodeType(node_name)
        except Exception:
            continue
        if node_type not in ("transform", "joint"):
            parents = cmds.listRelatives(node_name, parent=True, fullPath=True) or []
            if parents:
                node_name = parents[0]
        if node_name not in nodes:
            nodes.append(node_name)
    return nodes


def _attr_names_for_node(node_name):
    attrs = []
    for query_kwargs in ({"keyable": True}, {"channelBox": True}):
        try:
            for attr_name in cmds.listAttr(node_name, **query_kwargs) or []:
                if attr_name not in attrs:
                    attrs.append(attr_name)
        except Exception:
            pass
    result = []
    for attr_name in attrs:
        plug = "{0}.{1}".format(node_name, attr_name)
        if not cmds.objExists(plug):
            continue
        try:
            if cmds.getAttr(plug, size=True) not in (None, 1):
                continue
        except Exception:
            pass
        try:
            attr_type = cmds.getAttr(plug, type=True)
        except Exception:
            attr_type = ""
        if attr_type in ("double3", "float3", "long3", "short3", "matrix", "compound"):
            continue
        result.append(attr_name)
    return result


def channel_records_for_selection():
    nodes = _selected_nodes()
    if not nodes:
        return []
    primary = nodes[0]
    records = []
    for attr_name in _attr_names_for_node(primary):
        plug = "{0}.{1}".format(primary, attr_name)
        try:
            attr_type = cmds.getAttr(plug, type=True)
            value = cmds.getAttr(plug)
            locked = bool(cmds.getAttr(plug, lock=True))
        except Exception:
            continue
        enum_names = []
        if attr_type == "enum":
            try:
                enum_payload = cmds.attributeQuery(attr_name, node=primary, listEnum=True) or []
                enum_names = enum_payload[0].split(":") if enum_payload else []
            except Exception:
                enum_names = []
        records.append(
            {
                "node": primary,
                "attr": attr_name,
                "type": attr_type,
                "value": value,
                "locked": locked,
                "enum_names": enum_names,
            }
        )
    return records


def _set_attr_on_selection(attr_name, value):
    return _set_attr_on_nodes(_selected_nodes(), attr_name, value)


def _qt_window_from_maya_window(window_name):
    if not omui or not shiboken or not QtWidgets:
        return None
    ptr = None
    for finder in ("findWindow", "findControl"):
        try:
            ptr = getattr(omui.MQtUtil, finder)(window_name)
        except Exception:
            ptr = None
        if ptr:
            break
    if not ptr:
        return None
    try:
        return shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        return None


def _graph_editor_root_name():
    if cmds and cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, exists=True):
        return GRAPH_EDITOR_WORKSPACE_CONTROL_NAME
    return GRAPH_EDITOR_WINDOW_NAME


def _graph_editor_root_widget():
    return _qt_window_from_maya_window(_graph_editor_root_name())


def _graph_editor_root_exists():
    if not cmds:
        return False
    try:
        if cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, exists=True):
            return True
    except Exception:
        pass
    try:
        return bool(cmds.window(GRAPH_EDITOR_WINDOW_NAME, exists=True))
    except Exception:
        return False


def _graph_editor_root_visible():
    widget = _graph_editor_root_widget()
    if widget is not None:
        try:
            return bool(widget.isVisible())
        except Exception:
            pass
    if not cmds:
        return False
    try:
        if cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, exists=True):
            return bool(cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, query=True, visible=True))
    except Exception:
        pass
    try:
        return bool(cmds.window(GRAPH_EDITOR_WINDOW_NAME, exists=True) and cmds.window(GRAPH_EDITOR_WINDOW_NAME, query=True, visible=True))
    except Exception:
        return False


def _set_graph_editor_root_visible(visible):
    if not cmds:
        return False
    try:
        if cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, exists=True):
            if visible:
                cmds.workspaceControl(
                    GRAPH_EDITOR_WORKSPACE_CONTROL_NAME,
                    edit=True,
                    restore=True,
                    visible=True,
                )
            else:
                try:
                    cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, edit=True, close=True)
                except Exception:
                    pass
                try:
                    cmds.deleteUI(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, control=True)
                except Exception:
                    pass
            return True
    except Exception:
        pass
    try:
        if cmds.window(GRAPH_EDITOR_WINDOW_NAME, exists=True):
            if visible:
                cmds.window(GRAPH_EDITOR_WINDOW_NAME, edit=True, visible=True)
            else:
                cmds.deleteUI(GRAPH_EDITOR_WINDOW_NAME, window=True)
            return True
    except Exception:
        pass
    return False


def _graph_editor_is_floating():
    if not cmds:
        return True
    try:
        if cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, exists=True):
            return bool(cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, query=True, floating=True))
    except Exception:
        pass
    return True


def _maya_main_window():
    if not omui or not shiboken or not QtWidgets:
        return None
    try:
        ptr = omui.MQtUtil.mainWindow()
    except Exception:
        ptr = None
    if not ptr:
        return None
    try:
        return shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        return None


def _set_attr_on_nodes(nodes, attr_name, value, open_undo_chunk=True):
    nodes = [node_name for node_name in (nodes or []) if node_name and cmds.objExists(node_name)]
    if not nodes:
        return False, "Select an object first."
    changed = 0
    if open_undo_chunk:
        try:
            cmds.undoInfo(openChunk=True, chunkName="AminateFloatingChannelBoxEdit")
        except Exception:
            pass
    try:
        for node_name in nodes:
            plug = "{0}.{1}".format(node_name, attr_name)
            if not cmds.objExists(plug):
                continue
            try:
                if cmds.getAttr(plug, lock=True):
                    continue
            except Exception:
                continue
            try:
                attr_type = cmds.getAttr(plug, type=True)
                if attr_type == "string":
                    cmds.setAttr(plug, value or "", type="string")
                else:
                    cmds.setAttr(plug, value)
                changed += 1
            except Exception:
                pass
    finally:
        if open_undo_chunk:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
    if not changed:
        return False, "No editable matching channel found."
    return True, "Edited {0} on {1} selected object(s).".format(attr_name, changed)


def _apply_graph_editor_opacity(opacity=None):
    widget = _graph_editor_root_widget()
    if widget:
        try:
            widget.setWindowOpacity(_clamp(opacity if opacity is not None else get_graph_editor_opacity(), 0.2, 1.0))
        except Exception:
            pass
    return widget


def _apply_graph_editor_style():
    global _GRAPH_EDITOR_RESIZE_FILTER
    widget = _graph_editor_root_widget()
    if not widget:
        return None
    try:
        widget.setObjectName(GRAPH_EDITOR_WINDOW_NAME)
        widget.setMinimumSize(760, 420)
        try:
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        except Exception:
            pass
        widget.setStyleSheet(
            """
            QWidget#aminateFloatingGraphEditorWindow {
                background-color: #202020;
                color: #F2F2F2;
            }
            QWidget {
                background-color: #202020;
                color: #F2F2F2;
                selection-background-color: #335C67;
                selection-color: #FFFFFF;
            }
            QLabel {
                color: #F2F2F2;
            }
            QPushButton {
                background: #2B2B2B;
                background-color: #2B2B2B;
                color: #F2F2F2;
                border: 1px solid #4A4A4A;
                border-radius: 0px;
                padding: 4px 10px;
                min-height: 20px;
            }
            QPushButton:hover {
                background: #343434;
                background-color: #343434;
                border-color: #4CC9F0;
            }
            QPushButton:pressed {
                background: #244E55;
                background-color: #244E55;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #111111;
                color: #FFFFFF;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 3px;
            }
            QMenuBar, QMenu {
                background-color: #242424;
                color: #F2F2F2;
            }
            QToolBar {
                background-color: #242424;
                border: 0px;
                spacing: 3px;
            }
            QSplitter::handle {
                background-color: #333333;
            }
            QTreeView, QTableView {
                background-color: #171717;
                color: #F2F2F2;
                alternate-background-color: #1F1F1F;
                border: 1px solid #343434;
            }
            """
        )
        for button in widget.findChildren(QtWidgets.QPushButton):
            try:
                button.setFlat(True)
                button.setAutoDefault(False)
                button.setDefault(False)
            except Exception:
                pass
        for child in widget.findChildren(QtWidgets.QWidget):
            if child.objectName() in (GRAPH_EDITOR_CONTAINER_NAME, GRAPH_EDITOR_PANE_NAME):
                try:
                    child.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
                    child.setMinimumSize(1, 1)
                except Exception:
                    pass
        if QtCore and _GRAPH_EDITOR_RESIZE_FILTER is None:
            _GRAPH_EDITOR_RESIZE_FILTER = _GraphEditorResizeFilter(widget)
            widget.installEventFilter(_GRAPH_EDITOR_RESIZE_FILTER)
    except Exception:
        pass
    return widget


def _fit_graph_editor_curves():
    if not cmds:
        return False
    editor_names = []
    try:
        panel_control = cmds.scriptedPanel(GRAPH_EDITOR_PANEL_NAME, query=True, control=True)
        if panel_control:
            editor_names.extend([panel_control, panel_control + "GraphEd"])
    except Exception:
        pass
    editor_names.extend([GRAPH_EDITOR_PANEL_NAME + "GraphEd", "graphEditor1GraphEd"])
    try:
        for editor_name in cmds.lsUI(editors=True) or []:
            if "GraphEd" in editor_name or "graphEditor" in editor_name:
                editor_names.append(editor_name)
    except Exception:
        pass
    did_fit = False
    for editor_name in dict.fromkeys(editor_names):
        try:
            if cmds.animCurveEditor(editor_name, exists=True):
                cmds.animCurveEditor(editor_name, edit=True, lookAt="all")
                try:
                    cmds.animCurveEditor(editor_name, edit=True, displayInfinities="on")
                except Exception:
                    pass
                did_fit = True
        except Exception:
            pass
    return did_fit


def _graph_editor_curve_names():
    if not cmds:
        return []
    curves = []
    editor_names = []
    try:
        panel_control = cmds.scriptedPanel(GRAPH_EDITOR_PANEL_NAME, query=True, control=True)
        if panel_control:
            editor_names.extend([panel_control, panel_control + "GraphEd"])
    except Exception:
        pass
    editor_names.extend([GRAPH_EDITOR_PANEL_NAME + "GraphEd", "graphEditor1GraphEd"])
    try:
        for editor_name in cmds.lsUI(editors=True) or []:
            if "GraphEd" in editor_name or "graphEditor" in editor_name:
                editor_names.append(editor_name)
    except Exception:
        pass
    for editor_name in dict.fromkeys(editor_names):
        try:
            if cmds.animCurveEditor(editor_name, exists=True):
                curves.extend(cmds.animCurveEditor(editor_name, query=True, curvesShown=True) or [])
        except Exception:
            pass
    try:
        curves.extend(cmds.keyframe(query=True, selected=True, name=True) or [])
    except Exception:
        pass
    for node_name in cmds.ls(selection=True, long=True) or []:
        try:
            curves.extend(cmds.listConnections(node_name, source=True, destination=False, type="animCurve") or [])
        except Exception:
            pass
    if not curves:
        try:
            curves.extend(cmds.ls(type="animCurve") or [])
        except Exception:
            pass
    return [curve for curve in dict.fromkeys(curves) if curve and cmds.objExists(curve)]


def _set_graph_editor_infinity_view(enabled=True):
    if not cmds:
        return False
    editor_names = [GRAPH_EDITOR_PANEL_NAME + "GraphEd", "graphEditor1GraphEd"]
    try:
        panel_control = cmds.scriptedPanel(GRAPH_EDITOR_PANEL_NAME, query=True, control=True)
        if panel_control:
            editor_names.extend([panel_control, panel_control + "GraphEd"])
    except Exception:
        pass
    try:
        for editor_name in cmds.lsUI(editors=True) or []:
            if "GraphEd" in editor_name or "graphEditor" in editor_name:
                editor_names.append(editor_name)
    except Exception:
        pass
    did_update = False
    for editor_name in dict.fromkeys(editor_names):
        try:
            if cmds.animCurveEditor(editor_name, exists=True):
                cmds.animCurveEditor(editor_name, edit=True, displayInfinities="on" if enabled else "off")
                did_update = True
        except Exception:
            pass
    return did_update


def _graph_editor_window_size():
    width = DEFAULT_GRAPH_EDITOR_WIDTH
    height = DEFAULT_GRAPH_EDITOR_HEIGHT
    widget = _graph_editor_root_widget()
    if widget:
        try:
            widget_width = int(widget.width())
            widget_height = int(widget.height())
            if widget_width > 100 and widget_height > 100:
                width = widget_width
                height = widget_height
        except Exception:
            pass
    try:
        if cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, exists=True):
            cmd_width = int(cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, query=True, width=True) or width)
            cmd_height = int(cmds.workspaceControl(GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, query=True, height=True) or height)
            if cmd_width > 100 and cmd_height > 100:
                width = cmd_width
                height = cmd_height
        else:
            width_height = cmds.window(GRAPH_EDITOR_WINDOW_NAME, query=True, widthHeight=True) or []
            if len(width_height) >= 2:
                cmd_width = int(width_height[0])
                cmd_height = int(width_height[1])
                if cmd_width > 100 and cmd_height > 100:
                    width = cmd_width
                    height = cmd_height
    except Exception:
        pass
    return width, height


def _graph_editor_panel_controls():
    controls = []
    for panel_name, query_fn in (
        (GRAPH_EDITOR_OUTLINER_PANEL_NAME, cmds.outlinerPanel),
        (GRAPH_EDITOR_PANEL_NAME, cmds.scriptedPanel),
    ):
        try:
            control_name = query_fn(panel_name, query=True, control=True)
            if control_name:
                controls.append(control_name)
        except Exception:
            pass
    controls.extend([GRAPH_EDITOR_CONTAINER_NAME, GRAPH_EDITOR_PANE_NAME])
    return [control_name for control_name in dict.fromkeys(controls) if control_name]


def _set_maya_control_size(control_name, width, height):
    for command in (cmds.control, cmds.formLayout, cmds.paneLayout, cmds.rowLayout):
        try:
            if command(control_name, exists=True):
                command(control_name, edit=True, width=int(width), height=int(height))
                return True
        except Exception:
            pass
    return False


def _schedule_graph_editor_resize():
    if not QtCore:
        _resize_graph_editor_split()
        return
    for delay in (0, 40, 120, 280):
        try:
            QtCore.QTimer.singleShot(delay, _resize_graph_editor_split)
        except Exception:
            pass


def apply_cycle_infinity_to_graph_editor():
    if not MAYA_AVAILABLE or not cmds:
        return False, "Maya is not available."
    curves = _graph_editor_curve_names()
    if not curves:
        return False, "No animation curves found for cycle infinity."
    selected_nodes = cmds.ls(selection=True, long=True) or []
    try:
        selected_keys = cmds.keyframe(query=True, selected=True, name=True) or []
    except Exception:
        selected_keys = []
    changed = 0
    try:
        cmds.selectKey(clear=True)
    except Exception:
        pass
    for curve_name in curves:
        try:
            cmds.selectKey(curve_name, add=True)
            changed += 1
        except Exception:
            try:
                cmds.setAttr(curve_name + ".preInfinity", 3)
                cmds.setAttr(curve_name + ".postInfinity", 3)
                changed += 1
            except Exception:
                pass
    try:
        cmds.setInfinity(preInfinite="cycle", postInfinite="cycle")
    except Exception:
        for curve_name in curves:
            try:
                cmds.setAttr(curve_name + ".preInfinity", 3)
                cmds.setAttr(curve_name + ".postInfinity", 3)
            except Exception:
                pass
    try:
        cmds.selectKey(clear=True)
        for curve_name in selected_keys:
            if curve_name and cmds.objExists(curve_name):
                cmds.selectKey(curve_name, add=True)
    except Exception:
        pass
    try:
        if selected_nodes:
            cmds.select(selected_nodes, replace=True)
    except Exception:
        pass
    _set_graph_editor_infinity_view(True)
    _fit_graph_editor_curves()
    return True, "Cycle infinity enabled on {0} curve(s).".format(changed)


def apply_euler_flip_to_graph_editor():
    if not MAYA_AVAILABLE:
        return False, "Maya is not available."
    try:
        import maya_rotation_doctor
        success, message = maya_rotation_doctor.flip_current_euler_key()
    except Exception as exc:
        return False, "Euler flip failed: {0}".format(exc)
    _fit_graph_editor_curves()
    return success, message


def _resize_graph_editor_split():
    if not cmds:
        return False
    try:
        if not cmds.window(GRAPH_EDITOR_WINDOW_NAME, exists=True) or not cmds.paneLayout(GRAPH_EDITOR_PANE_NAME, exists=True):
            return False
        width, window_height = _graph_editor_window_size()
        width = max(760, int(width))
        header_height = GRAPH_EDITOR_HEADER_HEIGHT
        try:
            header_height = max(GRAPH_EDITOR_HEADER_HEIGHT, int(cmds.rowLayout(GRAPH_EDITOR_HEADER_NAME, query=True, height=True) or GRAPH_EDITOR_HEADER_HEIGHT))
        except Exception:
            pass
        height = max(GRAPH_EDITOR_MIN_BODY_HEIGHT, int(window_height) - header_height - 4)
        outliner_width = int(min(380, max(220, width * 0.26)))
        graph_width = max(420, width - outliner_width - 8)
        outliner_percent = int(min(45, max(18, round((float(outliner_width) / float(width)) * 100.0))))
        graph_percent = max(10, 100 - outliner_percent)
        try:
            _set_maya_control_size(GRAPH_EDITOR_CONTAINER_NAME, width, max(height + header_height, window_height))
            cmds.paneLayout(GRAPH_EDITOR_PANE_NAME, edit=True, width=width, height=height)
        except Exception:
            pass
        try:
            cmds.paneLayout(GRAPH_EDITOR_PANE_NAME, edit=True, paneSize=(1, outliner_percent, 100))
            cmds.paneLayout(GRAPH_EDITOR_PANE_NAME, edit=True, paneSize=(2, graph_percent, 100))
        except Exception:
            pass
        graph_control = ""
        try:
            graph_control = cmds.scriptedPanel(GRAPH_EDITOR_PANEL_NAME, query=True, control=True)
        except Exception:
            pass
        for control_name in _graph_editor_panel_controls():
            if control_name == GRAPH_EDITOR_CONTAINER_NAME:
                _set_maya_control_size(control_name, width, max(height + header_height, window_height))
            elif control_name == GRAPH_EDITOR_PANE_NAME:
                _set_maya_control_size(control_name, width, height)
            elif control_name == graph_control:
                _set_maya_control_size(control_name, graph_width, height)
            else:
                _set_maya_control_size(control_name, outliner_width, height)
        return True
    except Exception:
        return False


def _graph_editor_outliner_panel_exists():
    if not cmds:
        return False
    try:
        return bool(cmds.outlinerPanel(GRAPH_EDITOR_OUTLINER_PANEL_NAME, exists=True))
    except Exception:
        pass
    try:
        return bool(cmds.scriptedPanel(GRAPH_EDITOR_OUTLINER_PANEL_NAME, exists=True))
    except Exception:
        return False


def _configure_graph_editor_outliner_panel(panel_name=None):
    if not cmds:
        return ""
    panel_name = panel_name or GRAPH_EDITOR_OUTLINER_PANEL_NAME
    try:
        editor_name = cmds.outlinerPanel(panel_name, query=True, outlinerEditor=True)
    except Exception:
        editor_name = ""
    if not editor_name:
        return ""
    # Start clean for animators: DAG hierarchy visible, dependency/plugin internals hidden.
    editor_settings = {
        "mainListConnection": "worldList",
        "selectionConnection": "modelList",
        "showDagOnly": True,
        "showShapes": True,
        "showReferenceNodes": True,
        "showSetMembers": True,
        "displayMode": "DAG",
        "ignoreDagHierarchy": False,
        "autoExpand": False,
    }
    for attr_name, attr_value in editor_settings.items():
        try:
            cmds.outlinerEditor(editor_name, edit=True, **{attr_name: attr_value})
        except Exception:
            pass
    return editor_name


def _place_graph_editor_near_cursor():
    if not cmds:
        return False
    if not _graph_editor_is_floating():
        return False
    widget = _graph_editor_root_widget()
    if widget:
        try:
            widget.setMinimumSize(520, 320)
            widget.resize(DEFAULT_GRAPH_EDITOR_WIDTH, DEFAULT_GRAPH_EDITOR_HEIGHT)
        except Exception:
            pass
        return _move_widget_near_cursor(widget, DEFAULT_GRAPH_EDITOR_WIDTH, DEFAULT_GRAPH_EDITOR_HEIGHT)
    return False


def _delete_graph_editor_ui():
    if not cmds:
        return
    root_widget = _graph_editor_root_widget()
    if root_widget is not None:
        try:
            root_widget.hide()
        except Exception:
            pass
        try:
            root_widget.close()
        except Exception:
            pass
    for ui_name, kwargs in (
        (GRAPH_EDITOR_WORKSPACE_CONTROL_NAME, {"control": True}),
        (GRAPH_EDITOR_OUTLINER_PANEL_NAME, {"panel": True}),
        (GRAPH_EDITOR_PANEL_NAME, {"panel": True}),
        (GRAPH_EDITOR_WINDOW_NAME, {"window": True}),
    ):
        if ui_name == GRAPH_EDITOR_WORKSPACE_CONTROL_NAME:
            try:
                if cmds.workspaceControl(ui_name, exists=True):
                    try:
                        cmds.workspaceControl(ui_name, edit=True, close=True)
                    except Exception:
                        pass
                    cmds.deleteUI(ui_name, control=True)
                    continue
            except Exception:
                pass
        if ui_name == GRAPH_EDITOR_OUTLINER_PANEL_NAME:
            try:
                if cmds.outlinerPanel(ui_name, exists=True):
                    cmds.deleteUI(ui_name, panel=True)
                    continue
            except Exception:
                pass
        try:
            if cmds.scriptedPanel(ui_name, exists=True):
                cmds.deleteUI(ui_name, panel=True)
                continue
        except Exception:
            pass
        try:
            if cmds.window(ui_name, exists=True):
                cmds.deleteUI(ui_name, window=True)
                continue
        except Exception:
            pass
        try:
            cmds.deleteUI(ui_name, **kwargs)
        except Exception:
            pass
    if root_widget is not None:
        try:
            root_widget.setParent(None)
        except Exception:
            pass
        try:
            root_widget.deleteLater()
        except Exception:
            pass
    if QtWidgets and QtWidgets.QApplication.instance():
        try:
            QtWidgets.QApplication.instance().processEvents()
        except Exception:
            pass


def _ensure_graph_editor_window():
    if not MAYA_AVAILABLE or not cmds:
        return False, "Maya is not available."
    if _graph_editor_root_exists():
        try:
            if (
                not cmds.formLayout(GRAPH_EDITOR_CONTAINER_NAME, exists=True)
                or not cmds.paneLayout(GRAPH_EDITOR_PANE_NAME, exists=True)
                or not cmds.scriptedPanel(GRAPH_EDITOR_PANEL_NAME, exists=True)
                or not _graph_editor_outliner_panel_exists()
            ):
                _delete_graph_editor_ui()
            else:
                _configure_graph_editor_outliner_panel()
                _apply_graph_editor_style()
                _apply_graph_editor_opacity()
                _schedule_graph_editor_resize()
                return True, "Floating Graph Editor is ready."
        except Exception:
            _delete_graph_editor_ui()
    if _graph_editor_root_exists():
        return True, "Floating Graph Editor is ready."
    try:
        if cmds.scriptedPanel(GRAPH_EDITOR_PANEL_NAME, exists=True):
            cmds.deleteUI(GRAPH_EDITOR_PANEL_NAME, panel=True)
    except Exception:
        pass
    try:
        if cmds.outlinerPanel(GRAPH_EDITOR_OUTLINER_PANEL_NAME, exists=True):
            cmds.deleteUI(GRAPH_EDITOR_OUTLINER_PANEL_NAME, panel=True)
    except Exception:
        pass
    try:
        cmds.workspaceControl(
            GRAPH_EDITOR_WORKSPACE_CONTROL_NAME,
            label="Aminate Floating Graph Editor",
            retain=False,
            floating=True,
            initialWidth=DEFAULT_GRAPH_EDITOR_WIDTH,
            initialHeight=DEFAULT_GRAPH_EDITOR_HEIGHT,
        )
        cmds.formLayout(
            GRAPH_EDITOR_CONTAINER_NAME,
            parent=GRAPH_EDITOR_WORKSPACE_CONTROL_NAME,
            backgroundColor=(0.125, 0.125, 0.125),
        )
        cmds.rowLayout(
            GRAPH_EDITOR_HEADER_NAME,
            numberOfColumns=7,
            adjustableColumn=2,
            columnAttach=[(1, "both", 8), (2, "both", 8), (3, "both", 4), (4, "both", 4), (5, "both", 4), (6, "both", 4), (7, "both", 8)],
            columnAlign=[(1, "left"), (2, "left"), (3, "right"), (4, "right"), (5, "right"), (6, "right"), (7, "right")],
            height=34,
            parent=GRAPH_EDITOR_CONTAINER_NAME,
            backgroundColor=(0.188, 0.188, 0.188),
        )
        cmds.text(label="Aminate Graph Editor", align="left", font="boldLabelFont", backgroundColor=(0.188, 0.188, 0.188))
        cmds.text(label="Outliner + native curves  translucent split mode", align="left", backgroundColor=(0.188, 0.188, 0.188))
        cmds.text(
            label="Hotkey {0}".format(get_graph_editor_hotkey()),
            align="right",
            backgroundColor=(0.188, 0.188, 0.188),
        )
        cmds.button(
            label="Cycle Inf",
            annotation="Set selected or visible animation curves to pre-cycle and post-cycle, then show infinities in the Graph Editor View.",
            height=24,
            backgroundColor=(0.17, 0.17, 0.17),
            command=lambda *_args: apply_cycle_infinity_to_graph_editor(),
        )
        cmds.button(
            label="Euler Flip",
            annotation="Blender-style fix for selected rotation keys: rewrites the current key to the nearest safe Euler equivalent.",
            height=24,
            backgroundColor=(0.17, 0.17, 0.17),
            command=lambda *_args: apply_euler_flip_to_graph_editor(),
        )
        cmds.button(
            label="Refresh",
            height=24,
            backgroundColor=(0.17, 0.17, 0.17),
            command=lambda *_args: (_configure_graph_editor_outliner_panel(), _resize_graph_editor_split(), _apply_graph_editor_style(), _fit_graph_editor_curves()),
        )
        cmds.button(
            label="Close",
            height=24,
            backgroundColor=(0.13, 0.13, 0.13),
            command=lambda *_args: _set_graph_editor_root_visible(False),
        )
        cmds.setParent(GRAPH_EDITOR_CONTAINER_NAME)
        cmds.paneLayout(GRAPH_EDITOR_PANE_NAME, configuration="vertical2", separatorThickness=7, parent=GRAPH_EDITOR_CONTAINER_NAME)
        cmds.formLayout(
            GRAPH_EDITOR_CONTAINER_NAME,
            edit=True,
            attachForm=[
                (GRAPH_EDITOR_HEADER_NAME, "top", 0),
                (GRAPH_EDITOR_HEADER_NAME, "left", 0),
                (GRAPH_EDITOR_HEADER_NAME, "right", 0),
                (GRAPH_EDITOR_PANE_NAME, "left", 0),
                (GRAPH_EDITOR_PANE_NAME, "right", 0),
                (GRAPH_EDITOR_PANE_NAME, "bottom", 0),
            ],
            attachControl=[(GRAPH_EDITOR_PANE_NAME, "top", 0, GRAPH_EDITOR_HEADER_NAME)],
        )
        try:
            outliner_panel = cmds.outlinerPanel(
                GRAPH_EDITOR_OUTLINER_PANEL_NAME,
                label="Aminate Floating Outliner",
                parent=GRAPH_EDITOR_PANE_NAME,
            )
        except Exception:
            outliner_panel = cmds.outlinerPanel(label="Aminate Floating Outliner")
            cmds.outlinerPanel(outliner_panel, edit=True, parent=GRAPH_EDITOR_PANE_NAME)
        try:
            cmds.outlinerPanel(outliner_panel, edit=True, parent=GRAPH_EDITOR_PANE_NAME)
        except Exception:
            pass
        _configure_graph_editor_outliner_panel(outliner_panel)
        try:
            panel = cmds.scriptedPanel(GRAPH_EDITOR_PANEL_NAME, type="graphEditor", label="Aminate Floating Graph Editor", parent=GRAPH_EDITOR_PANE_NAME)
        except Exception:
            panel = cmds.scriptedPanel(type="graphEditor", label="Aminate Floating Graph Editor")
            cmds.scriptedPanel(panel, edit=True, parent=GRAPH_EDITOR_PANE_NAME)
        try:
            cmds.scriptedPanel(panel, edit=True, parent=GRAPH_EDITOR_PANE_NAME)
        except Exception:
            pass
        try:
            _resize_graph_editor_split()
            _schedule_graph_editor_resize()
        except Exception:
            pass
        _apply_graph_editor_style()
        _apply_graph_editor_opacity()
        _fit_graph_editor_curves()
        return True, "Floating Graph Editor is ready."
    except Exception as exc:
        _delete_graph_editor_ui()
        if mel:
            try:
                mel.eval("GraphEditor;")
                return False, "Opened Maya Graph Editor fallback: {0}".format(exc)
            except Exception:
                pass
        return False, "Could not create Floating Graph Editor: {0}".format(exc)


def show_floating_graph_editor():
    if not MAYA_AVAILABLE or not cmds:
        return False, "Maya is not available."
    try:
        if _graph_editor_root_visible():
            _apply_graph_editor_opacity()
            _schedule_graph_editor_resize()
            return True, "Floating Graph Editor already open."
    except Exception:
        pass
    success, message = _ensure_graph_editor_window()
    if not success and not _graph_editor_root_exists():
        return success, message
    try:
        _set_graph_editor_root_visible(True)
        _place_graph_editor_near_cursor()
        _resize_graph_editor_split()
        _schedule_graph_editor_resize()
        _apply_graph_editor_opacity()
        _fit_graph_editor_curves()
        return True, "Floating Graph Editor shown."
    except Exception as exc:
        return False, "Could not show Floating Graph Editor: {0}".format(exc)


def toggle_floating_graph_editor():
    if not MAYA_AVAILABLE or not cmds:
        return False, "Maya is not available."
    try:
        if _graph_editor_root_visible():
            _delete_graph_editor_ui()
            if QtWidgets and QtWidgets.QApplication.instance():
                try:
                    QtWidgets.QApplication.instance().processEvents()
                except Exception:
                    pass
            return True, "Floating Graph Editor hidden."
    except Exception:
        pass
    return show_floating_graph_editor()


if QtWidgets:
    class FloatingChannelBoxDialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super(FloatingChannelBoxDialog, self).__init__(parent or _maya_main_window())
            self.setObjectName(FLOATING_OBJECT_NAME)
            self.setWindowTitle("Aminate Floating Channel Box")
            self._drag_offset = None
            self._target_nodes = []
            self._numeric_pending = {}
            self._numeric_last_status = ""
            self._numeric_timer = QtCore.QTimer(self)
            self._numeric_timer.setSingleShot(True)
            self._numeric_timer.setInterval(NUMERIC_EDIT_FLUSH_INTERVAL_MS)
            self._numeric_timer.timeout.connect(self._flush_numeric_edits)
            flags = QtCore.Qt.Tool
            self.setWindowFlags(flags)
            self.setWindowOpacity(get_channel_opacity())
            self.setMinimumWidth(260)
            self.setStyleSheet(
                """
                QDialog#aminateFloatingChannelBoxWindow {
                    background-color: #202020;
                    color: #F2F2F2;
                    border: 0px;
                    border-radius: 8px;
                }
                QLabel { color: #F2F2F2; }
                QLabel#floatingChannelBoxTitle { font-weight: 700; color: #FFFFFF; }
                QFrame#floatingChannelBoxHeader { background-color: #303030; border-radius: 6px; }
                QDoubleSpinBox, QLineEdit, QComboBox {
                    background-color: #111111;
                    color: #FFFFFF;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 3px;
                }
                QCheckBox { color: #F2F2F2; }
                QPushButton {
                    background-color: #333333;
                    color: #F2F2F2;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 3px 6px;
                }
                """
            )
            self._build_ui()

        def _build_ui(self):
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)
            header = QtWidgets.QFrame()
            self.header = header
            header.setObjectName("floatingChannelBoxHeader")
            header.setCursor(QtCore.Qt.SizeAllCursor)
            header.installEventFilter(self)
            header_layout = QtWidgets.QHBoxLayout(header)
            header_layout.setContentsMargins(6, 4, 6, 4)
            self.title_label = QtWidgets.QLabel("Floating Channel Box")
            self.title_label.setObjectName("floatingChannelBoxTitle")
            self.title_label.setCursor(QtCore.Qt.SizeAllCursor)
            self.title_label.installEventFilter(self)
            header_layout.addWidget(self.title_label, 1)
            refresh_button = QtWidgets.QPushButton("Refresh")
            refresh_button.clicked.connect(self.refresh)
            header_layout.addWidget(refresh_button)
            close_button = QtWidgets.QPushButton("X")
            close_button.setFixedWidth(26)
            close_button.clicked.connect(self.hide)
            header_layout.addWidget(close_button)
            layout.addWidget(header)
            self.selection_label = QtWidgets.QLabel("Select an object.")
            self.selection_label.setWordWrap(True)
            layout.addWidget(self.selection_label)
            self.scroll = QtWidgets.QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            self.rows_widget = QtWidgets.QWidget()
            self.rows_layout = QtWidgets.QFormLayout(self.rows_widget)
            self.rows_layout.setContentsMargins(0, 0, 0, 0)
            self.rows_layout.setSpacing(4)
            self.scroll.setWidget(self.rows_widget)
            layout.addWidget(self.scroll, 1)
            self.status_label = QtWidgets.QLabel("")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)

        def show_for_selection(self):
            self.refresh()
            try:
                self.adjustSize()
                _move_widget_near_cursor(self)
            except Exception:
                pass
            self.show()
            self.raise_()

        def eventFilter(self, obj, event):
            if obj in (getattr(self, "header", None), getattr(self, "title_label", None)):
                try:
                    event_type = event.type()
                    left_button = _qt_mouse_button_value("LeftButton")
                    if event_type == QtCore.QEvent.MouseButtonPress and int(event.button()) == left_button:
                        return self._begin_drag(event)
                    if event_type == QtCore.QEvent.MouseMove and self._drag_offset is not None:
                        return self._continue_drag(event)
                    if event_type == QtCore.QEvent.MouseButtonRelease:
                        self._drag_offset = None
                except Exception:
                    self._drag_offset = None
            return super(FloatingChannelBoxDialog, self).eventFilter(obj, event)

        def mousePressEvent(self, event):
            try:
                left_button = _qt_mouse_button_value("LeftButton")
                if int(event.button()) == left_button and not _is_text_entry_widget(self.childAt(event.pos())):
                    if self._begin_drag(event):
                        return
            except Exception:
                pass
            super(FloatingChannelBoxDialog, self).mousePressEvent(event)

        def mouseMoveEvent(self, event):
            try:
                if self._drag_offset is not None and self._continue_drag(event):
                    return
            except Exception:
                pass
            super(FloatingChannelBoxDialog, self).mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            self._drag_offset = None
            super(FloatingChannelBoxDialog, self).mouseReleaseEvent(event)

        def _begin_drag(self, event):
            global_pos = _event_global_pos(event)
            if global_pos is None:
                return False
            self._drag_offset = global_pos - self.frameGeometry().topLeft()
            return True

        def _continue_drag(self, event):
            global_pos = _event_global_pos(event)
            if global_pos is None:
                return False
            _move_widget_within_screen(self, global_pos - self._drag_offset)
            return True

        def refresh(self):
            while self.rows_layout.rowCount():
                self.rows_layout.removeRow(0)
            nodes = _selected_nodes()
            self._target_nodes = list(nodes)
            if not nodes:
                self.selection_label.setText("Select an object to edit channels.")
                self.status_label.setText("")
                return
            primary = nodes[0]
            suffix = " Editing {0} selected objects.".format(len(nodes)) if len(nodes) > 1 else ""
            self.selection_label.setText("{0}.{1}".format(_short_name(primary), suffix))
            records = channel_records_for_selection()
            if not records:
                self.status_label.setText("No keyable or channel-box attrs found.")
                return
            for record in records:
                widget = self._make_editor(record)
                if widget:
                    self.rows_layout.addRow(record["attr"], widget)
            self.status_label.setText("Hotkey: {0}".format(get_hotkey()))

        def _make_editor(self, record):
            attr_name = record["attr"]
            attr_type = record["type"]
            value = record["value"]
            locked = bool(record["locked"])
            if attr_type in ("double", "float", "doubleLinear", "doubleAngle", "long", "short", "byte", "time"):
                editor = QtWidgets.QDoubleSpinBox()
                editor.setRange(-1000000.0, 1000000.0)
                editor.setDecimals(4)
                editor.setSingleStep(0.1)
                try:
                    editor.setValue(float(value))
                except Exception:
                    editor.setValue(0.0)
                editor.setEnabled(not locked)
                try:
                    editor.setKeyboardTracking(False)
                except Exception:
                    pass
                editor.valueChanged.connect(functools.partial(self._queue_numeric, attr_name))
                editor.editingFinished.connect(self._flush_numeric_edits)
                return editor
            if attr_type == "bool":
                editor = QtWidgets.QCheckBox()
                editor.setChecked(bool(value))
                editor.setEnabled(not locked)
                editor.toggled.connect(functools.partial(self._set_bool, attr_name))
                return editor
            if attr_type == "enum":
                editor = QtWidgets.QComboBox()
                names = record.get("enum_names") or []
                for index, name in enumerate(names):
                    editor.addItem(name, index)
                try:
                    editor.setCurrentIndex(int(value))
                except Exception:
                    pass
                editor.setEnabled(not locked)
                editor.currentIndexChanged.connect(functools.partial(self._set_enum, attr_name))
                return editor
            if attr_type == "string":
                editor = QtWidgets.QLineEdit(str(value or ""))
                editor.setEnabled(not locked)
                editor.editingFinished.connect(functools.partial(self._set_string, attr_name, editor))
                return editor
            editor = QtWidgets.QLineEdit(str(value))
            editor.setReadOnly(True)
            editor.setEnabled(False)
            return editor

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            if MAYA_AVAILABLE and cmds:
                try:
                    if success:
                        cmds.inViewMessage(amg=message, pos="midCenterTop", fade=True)
                    else:
                        cmds.warning(message)
                except Exception:
                    pass

        def _set_numeric(self, attr_name, value):
            success, message = _set_attr_on_nodes(self._target_nodes, attr_name, float(value))
            self._set_status(message, success)

        def _queue_numeric(self, attr_name, value):
            self._numeric_pending[attr_name] = float(value)
            if not self._numeric_timer.isActive():
                self._numeric_timer.start()

        def _flush_numeric_edits(self):
            if not getattr(self, "_numeric_pending", None):
                return
            pending = dict(self._numeric_pending)
            self._numeric_pending.clear()
            if not self._target_nodes:
                self._set_status("Select an object first.", False)
                return
            changed_attrs = []
            last_message = ""
            success_any = False
            try:
                cmds.undoInfo(openChunk=True, chunkName="AminateFloatingChannelBoxNumericEdit")
            except Exception:
                pass
            try:
                for attr_name, value in pending.items():
                    success, message = _set_attr_on_nodes(
                        self._target_nodes,
                        attr_name,
                        float(value),
                        open_undo_chunk=False,
                    )
                    last_message = message
                    if success:
                        success_any = True
                        changed_attrs.append(attr_name)
            finally:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass
            if changed_attrs:
                message = "Edited {0} on {1} selected object(s).".format(
                    ", ".join(sorted(changed_attrs)),
                    len(self._target_nodes),
                )
            else:
                message = last_message or "No editable matching channel found."
            if message != self._numeric_last_status:
                self._numeric_last_status = message
                self._set_status(message, success_any)
            else:
                self.status_label.setText(message)
            if self._numeric_pending and not self._numeric_timer.isActive():
                self._numeric_timer.start()

        def _set_bool(self, attr_name, value):
            success, message = _set_attr_on_nodes(self._target_nodes, attr_name, bool(value))
            self._set_status(message, success)

        def _set_enum(self, attr_name, index):
            success, message = _set_attr_on_nodes(self._target_nodes, attr_name, int(index))
            self._set_status(message, success)

        def _set_string(self, attr_name, editor):
            success, message = _set_attr_on_nodes(self._target_nodes, attr_name, editor.text())
            self._set_status(message, success)


    class FloatingChannelBoxHotkeyManager(QtCore.QObject):
        def __init__(self, hotkey_text=None, graph_hotkey_text=None, parent=None):
            super(FloatingChannelBoxHotkeyManager, self).__init__(parent)
            self.hotkey_text = normalize_hotkey(hotkey_text or get_hotkey())
            self.hotkey_parts = hotkey_to_parts(self.hotkey_text)
            self.graph_hotkey_text = normalize_hotkey(graph_hotkey_text or get_graph_editor_hotkey(), default_value=DEFAULT_GRAPH_EDITOR_HOTKEY)
            # Graph editor hotkey uses the same raw app-wide event filter path as the channel box.
            self.graph_hotkey_parts = graph_hotkey_to_parts(self.graph_hotkey_text)
            self.dialog = None
            self.graph_shortcut = None
            self._last_trigger_time = 0.0
            app = QtWidgets.QApplication.instance()
            if app:
                app.installEventFilter(self)
            self._install_graph_shortcut()

        def set_hotkey(self, hotkey_text):
            self.set_channel_hotkey(hotkey_text)

        def set_channel_hotkey(self, hotkey_text):
            self.hotkey_text = normalize_hotkey(hotkey_text)
            self.hotkey_parts = hotkey_to_parts(self.hotkey_text)

        def set_graph_hotkey(self, hotkey_text):
            self.graph_hotkey_text = normalize_hotkey(hotkey_text, default_value=DEFAULT_GRAPH_EDITOR_HOTKEY)
            self.graph_hotkey_parts = graph_hotkey_to_parts(self.graph_hotkey_text)
            self._install_graph_shortcut()

        def _graph_shortcut_parent(self):
            parent_widget = _maya_main_window()
            if parent_widget:
                return parent_widget
            return QtWidgets.QApplication.instance()

        def _install_graph_shortcut(self):
            if not QtWidgets or not QtGui:
                return
            shortcut_class = getattr(QtWidgets, "QShortcut", None) or getattr(QtGui, "QShortcut", None)
            if shortcut_class is None:
                return
            parent_widget = self._graph_shortcut_parent()
            if not parent_widget:
                return
            if self.graph_shortcut is None or self.graph_shortcut.parent() is not parent_widget:
                if self.graph_shortcut is not None:
                    try:
                        self.graph_shortcut.activated.disconnect(self.toggle_graph)
                    except Exception:
                        pass
                    try:
                        self.graph_shortcut.deleteLater()
                    except Exception:
                        pass
                self.graph_shortcut = shortcut_class(parent_widget)
                try:
                    self.graph_shortcut.setContext(_qt_shortcut_context_value("ApplicationShortcut"))
                except Exception:
                    pass
                try:
                    self.graph_shortcut.setAutoRepeat(False)
                except Exception:
                    pass
                self.graph_shortcut.activated.connect(self.toggle_graph)
            try:
                self.graph_shortcut.setKey(QtGui.QKeySequence(_qt_shortcut_text(self.graph_hotkey_text)))
            except Exception:
                pass

        def set_channel_opacity(self, opacity):
            if self.dialog:
                try:
                    self.dialog.setWindowOpacity(_clamp(opacity, 0.2, 1.0))
                except Exception:
                    pass

        def shutdown(self):
            app = QtWidgets.QApplication.instance()
            if app:
                try:
                    app.removeEventFilter(self)
                except Exception:
                    pass
            if self.graph_shortcut is not None:
                try:
                    self.graph_shortcut.activated.disconnect(self.toggle_graph)
                except Exception:
                    pass
                try:
                    self.graph_shortcut.deleteLater()
                except Exception:
                    pass
            self.graph_shortcut = None
            if self.dialog:
                try:
                    self.dialog.close()
                except Exception:
                    pass
            self.dialog = None

        def toggle(self):
            self.toggle_channel()

        def toggle_channel(self):
            if self.dialog and self.dialog.isVisible():
                self.dialog.hide()
                return
            if self.dialog is None:
                self.dialog = FloatingChannelBoxDialog(parent=_maya_main_window())
            self.dialog.setWindowOpacity(get_channel_opacity())
            self.dialog.show_for_selection()

        def toggle_graph(self):
            toggle_floating_graph_editor()

        def _event_matches(self, event, parts):
            if event.type() != QtCore.QEvent.KeyPress:
                return False
            if hasattr(event, "isAutoRepeat") and event.isAutoRepeat():
                return False
            expected_text = parts.get("text") or ""
            if expected_text:
                try:
                    if event.text() == expected_text:
                        return True
                except Exception:
                    pass
            key_value = parts.get("key")
            if key_value is None or _enum_int(event.key()) != _enum_int(key_value):
                return False
            side = parts.get("side") or ""
            if side:
                scan_code = _enum_int(event.nativeScanCode()) if hasattr(event, "nativeScanCode") else 0
                if side == "left" and scan_code not in (0, 56):
                    return False
                if side == "right" and scan_code not in (0, 541, 312, 3640):
                    return False
                return True
            modifiers = _enum_int(event.modifiers()) & _modifier_mask()
            required_modifiers = _enum_int(parts.get("modifiers") or 0)
            if required_modifiers:
                return (modifiers & required_modifiers) == required_modifiers
            return modifiers == 0

        def eventFilter(self, obj, event):
            try:
                matched_channel = self._event_matches(event, self.hotkey_parts)
                if matched_channel:
                    if _is_text_entry_widget(QtWidgets.QApplication.focusWidget()):
                        return False
                    now = time.time()
                    if now - self._last_trigger_time < 0.2:
                        return True
                    self._last_trigger_time = now
                    self.toggle_channel()
                    return True
                matched_graph = self._event_matches(event, self.graph_hotkey_parts)
                if matched_graph:
                    if _is_text_entry_widget(QtWidgets.QApplication.focusWidget()):
                        return False
                    now = time.time()
                    if now - self._last_trigger_time < 0.2:
                        return True
                    self._last_trigger_time = now
                    self.toggle_graph()
                    return True
            except Exception:
                pass
            return False


def install_global_hotkey(hotkey_text=None, graph_hotkey_text=None):
    global _GLOBAL_MANAGER
    if not QtWidgets or not QtCore:
        return None
    app = QtWidgets.QApplication.instance()
    if not app:
        return None
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = FloatingChannelBoxHotkeyManager(hotkey_text or get_hotkey(), graph_hotkey_text or get_graph_editor_hotkey())
    else:
        _GLOBAL_MANAGER.set_channel_hotkey(hotkey_text or get_hotkey())
        _GLOBAL_MANAGER.set_graph_hotkey(graph_hotkey_text or get_graph_editor_hotkey())
    return _GLOBAL_MANAGER


def shutdown_global_hotkey():
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER:
        _GLOBAL_MANAGER.shutdown()
    _GLOBAL_MANAGER = None


def hide_floating_channel_box_and_graph_editor():
    hidden = 0
    manager = _GLOBAL_MANAGER
    if manager is not None and getattr(manager, "dialog", None) is not None:
        try:
            if manager.dialog.isVisible():
                hidden += 1
        except Exception:
            pass
        try:
            manager.dialog.close()
        except Exception:
            pass
        manager.dialog = None
    try:
        if _graph_editor_root_exists():
            if _graph_editor_root_visible():
                hidden += 1
            _delete_graph_editor_ui()
    except Exception:
        pass
    if QtWidgets and QtWidgets.QApplication.instance():
        try:
            QtWidgets.QApplication.instance().processEvents()
        except Exception:
            pass
    return hidden


def show_floating_channel_box():
    manager = install_global_hotkey()
    if manager:
        manager.toggle()
        return True, "Floating Channel Box toggled."
    return False, "Qt is not available, so Floating Channel Box could not open."


__all__ = [
    "CHANNEL_OPACITY_OPTION",
    "DEFAULT_CHANNEL_OPACITY",
    "DEFAULT_GRAPH_EDITOR_HOTKEY",
    "DEFAULT_GRAPH_EDITOR_OPACITY",
    "DEFAULT_HOTKEY",
    "GRAPH_EDITOR_HOTKEY_OPTION",
    "GRAPH_EDITOR_OPACITY_OPTION",
    "HOTKEY_OPTION",
    "channel_records_for_selection",
    "get_channel_opacity",
    "get_graph_editor_hotkey",
    "get_graph_editor_opacity",
    "get_hotkey",
    "graph_hotkey_to_parts",
    "hotkey_to_parts",
    "hide_floating_channel_box_and_graph_editor",
    "install_global_hotkey",
    "normalize_hotkey",
    "set_channel_opacity",
    "set_graph_editor_hotkey",
    "set_graph_editor_opacity",
    "set_hotkey",
    "show_floating_channel_box",
    "show_floating_graph_editor",
    "shutdown_global_hotkey",
    "toggle_floating_graph_editor",
]
