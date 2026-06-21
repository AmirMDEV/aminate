"""
maya_history_timeline.py

Scene-backed Aminate History Timeline.

Full Maya scene snapshots keep restores reliable. Snapshot metadata captures
changed scene facts so later partial restore and comparison tools can build on it.
"""

from __future__ import absolute_import, division, print_function

import datetime
import hashlib
import json
import os
import re
import time
import uuid

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om2

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om2 = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
    except Exception:
        QtCore = QtGui = QtWidgets = None


WINDOW_OBJECT_NAME = "mayaHistoryTimelineWindow"
META_NODE_NAME = "aminateHistory_META"
MANIFEST_FILE_NAME = "history_manifest.json"
SNAPSHOT_FOLDER_NAME = "snapshots"
MANIFEST_VERSION = 1
AMINATE_HISTORY_VERSION = "0.1"
AUTO_SNAPSHOT_SUPPRESS_UNTIL_OPTION = "AmirMayaHistoryAutoSnapshotSuppressUntil"
AUTO_SNAPSHOT_ENABLED_OPTION = "AmirMayaHistoryAutoSnapshotEnabled"
HISTORY_SECURITY_PROMPT_OPTION_VARS = (
    "SafeModeOption",
    "SafeModeImportOption",
    "SafeModeBuiltInCheck",
    "SafeModeUserSetupHashOption",
    "TrustCenterPathOption",
)
AUTO_SNAPSHOT_SETTLE_SECONDS = 1.5
DEFAULT_AUTO_SNAPSHOT_ENABLED = False
DEFAULT_STEP_COLOR = "#4CC9F0"
DEFAULT_MILESTONE_COLOR = "#F6C85F"
DEFAULT_AUTO_COLOR = "#8D99AE"
DEFAULT_SNAPSHOT_CAP = 50
MAX_HISTORY_STRIP_MARKERS = 120
MAX_HISTORY_TABLE_ROWS = 500
DEFAULT_AUTO_SNAPSHOT_MODE = "all"
AUTO_SNAPSHOT_MODE_ALL = "all"
AUTO_SNAPSHOT_MODE_CUSTOM = "custom"
AUTO_SNAPSHOT_TRIGGER_LABELS = (
    ("keyframes", "After setting or deleting keyframes, including Auto Key"),
    ("constraints", "After creating or keying constraints"),
    ("nodes", "After creating or deleting objects"),
    ("animation_layers", "After animation layer changes"),
    ("parenting", "After parenting changes"),
    ("references", "After reference or import changes"),
    ("transforms", "After transform changes"),
    ("materials", "After material changes"),
)
DEFAULT_AUTO_SNAPSHOT_TRIGGERS = {
    "keyframes": True,
    "constraints": True,
    "nodes": True,
    "animation_layers": True,
    "parenting": True,
    "references": True,
    "transforms": True,
    "materials": True,
}
BRANCH_COLOR_PALETTE = (
    "#4CC9F0",
    "#F76E6E",
    "#7BD88F",
    "#B86BFF",
    "#F4A261",
    "#2EC4B6",
    "#FF5D8F",
    "#9DDBAD",
)
HISTORY_UI_WIDGETS = []
HISTORY_SCENE_CHANGE_JOBS = {}
HISTORY_ACTION_TIMER_CONTROLLERS = []


def _now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _safe_name(value, fallback="snapshot"):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._")
    return cleaned[:48] or fallback


def _short_name(node_name):
    if not node_name:
        return ""
    return str(node_name).split("|")[-1].split(":")[-1]


def _scene_file_type(scene_path):
    ext = os.path.splitext(scene_path or "")[1].lower()
    if ext == ".mb":
        return "mayaBinary"
    return "mayaAscii"


def _display_info(message):
    if MAYA_AVAILABLE and om2:
        try:
            om2.MGlobal.displayInfo("[History Timeline] {0}".format(message))
            return
        except Exception:
            pass
    print("[History Timeline] {0}".format(message))


def _display_warning(message):
    if MAYA_AVAILABLE and om2:
        try:
            om2.MGlobal.displayWarning("[History Timeline] {0}".format(message))
            return
        except Exception:
            pass
    print("[History Timeline] WARNING: {0}".format(message))


def _ensure_string_attr(node_name, attr_name):
    if not cmds.objExists(node_name + "." + attr_name):
        cmds.addAttr(node_name, longName=attr_name, dataType="string")


def _ensure_meta_node():
    if not MAYA_AVAILABLE:
        return ""
    if cmds.objExists(META_NODE_NAME):
        node = META_NODE_NAME
    else:
        node = cmds.createNode("network", name=META_NODE_NAME)
    for attr_name in ("manifestPath", "historyRoot", "originalScenePath", "currentSnapshotId", "manifestJson"):
        _ensure_string_attr(node, attr_name)
    try:
        cmds.setAttr(node + ".hiddenInOutliner", True)
    except Exception:
        pass
    return node


def _read_meta_value(attr_name):
    if not MAYA_AVAILABLE or not cmds.objExists(META_NODE_NAME + "." + attr_name):
        return ""
    try:
        return cmds.getAttr(META_NODE_NAME + "." + attr_name) or ""
    except Exception:
        return ""


def _write_meta(context, manifest):
    if not MAYA_AVAILABLE:
        return
    node = _ensure_meta_node()
    if not node:
        return
    payload = json.dumps(
        {
            "version": MANIFEST_VERSION,
            "current_snapshot_id": manifest.get("current_snapshot_id", ""),
            "snapshot_count": len(manifest.get("snapshots") or []),
            "active_branch_id": manifest.get("active_branch_id", ""),
        },
        sort_keys=True,
    )
    values = {
        "manifestPath": context.get("manifest_path", ""),
        "historyRoot": context.get("history_root", ""),
        "originalScenePath": context.get("original_scene_path", ""),
        "currentSnapshotId": manifest.get("current_snapshot_id", ""),
        "manifestJson": payload,
    }
    for attr_name, value in values.items():
        try:
            cmds.setAttr(node + "." + attr_name, value or "", type="string")
        except Exception:
            pass


def _scene_uses_meta_original(scene_path, original_scene_path):
    if not scene_path or not original_scene_path:
        return False
    scene_path = os.path.abspath(scene_path)
    original_scene_path = os.path.abspath(original_scene_path)
    if scene_path == original_scene_path:
        return True
    original_dir = os.path.dirname(original_scene_path)
    original_base = os.path.splitext(os.path.basename(original_scene_path))[0]
    snapshot_dir = os.path.join(original_dir, "{0}_aminate_history".format(original_base), SNAPSHOT_FOLDER_NAME)
    try:
        return os.path.commonpath([scene_path, os.path.abspath(snapshot_dir)]) == os.path.abspath(snapshot_dir)
    except Exception:
        return False


def _infer_original_scene_from_snapshot_path(scene_path):
    if not scene_path:
        return ""
    scene_path = os.path.abspath(scene_path)
    snapshot_dir = os.path.dirname(scene_path)
    history_root = os.path.dirname(snapshot_dir)
    if os.path.basename(snapshot_dir) != SNAPSHOT_FOLDER_NAME:
        return ""
    if not os.path.basename(history_root).endswith("_aminate_history"):
        return ""
    manifest_path = os.path.join(history_root, MANIFEST_FILE_NAME)
    if not os.path.exists(manifest_path):
        return ""
    try:
        with open(manifest_path, "r") as handle:
            manifest = json.load(handle)
    except Exception:
        return ""
    original_scene_path = manifest.get("original_scene_path", "")
    if original_scene_path and _scene_uses_meta_original(scene_path, original_scene_path):
        return os.path.abspath(original_scene_path)
    return ""


def _is_unlinked_history_snapshot_path(scene_path):
    if not scene_path:
        return False
    scene_path = os.path.abspath(scene_path)
    snapshot_dir = os.path.dirname(scene_path)
    history_root = os.path.dirname(snapshot_dir)
    return os.path.basename(snapshot_dir) == SNAPSHOT_FOLDER_NAME and os.path.basename(history_root).endswith("_aminate_history")


def _branch_display_name(branch_id):
    if not branch_id or branch_id == "main":
        return "Main"
    if branch_id.startswith("branch_"):
        return "Branch " + branch_id.split("_", 1)[-1][:4].upper()
    return str(branch_id)


def _branch_color_from_id(branch_id, index=0):
    if branch_id == "main":
        return BRANCH_COLOR_PALETTE[0]
    seed = sum(ord(char) for char in str(branch_id or "main")) + int(index or 0)
    return BRANCH_COLOR_PALETTE[seed % len(BRANCH_COLOR_PALETTE)]


def _format_bytes(byte_count):
    try:
        value = float(byte_count or 0)
    except Exception:
        value = 0.0
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or suffix == "TB":
            if suffix == "B":
                return "{0} {1}".format(int(value), suffix)
            return "{0:.1f} {1}".format(value, suffix)
        value /= 1024.0
    return "{0:.1f} TB".format(value)


def _first_items(values, limit=5):
    clean = [str(value) for value in (values or []) if value]
    return clean[: int(limit or 5)]


def _join_preview(values, limit=5):
    items = _first_items(values, limit)
    if not items:
        return ""
    extra = max(0, len(values or []) - len(items))
    text = ", ".join(items)
    if extra:
        text += " +" + str(extra)
    return text


def _summary_dict(summary, key):
    value = (summary or {}).get(key) or {}
    return value if isinstance(value, dict) else {}


def _summary_list(summary, key):
    value = (summary or {}).get(key) or []
    return value if isinstance(value, list) else []


def _suppress_auto_snapshots_for(seconds=2.0):
    if not MAYA_AVAILABLE:
        return
    try:
        cmds.optionVar(floatValue=(AUTO_SNAPSHOT_SUPPRESS_UNTIL_OPTION, time.time() + float(seconds or 0.0)))
    except Exception:
        pass


def _auto_snapshots_are_suppressed():
    if not MAYA_AVAILABLE:
        return False
    try:
        if not cmds.optionVar(exists=AUTO_SNAPSHOT_SUPPRESS_UNTIL_OPTION):
            return False
        return time.time() < float(cmds.optionVar(query=AUTO_SNAPSHOT_SUPPRESS_UNTIL_OPTION) or 0.0)
    except Exception:
        return False


def _auto_snapshot_enabled():
    if not MAYA_AVAILABLE:
        return DEFAULT_AUTO_SNAPSHOT_ENABLED
    try:
        if not cmds.optionVar(exists=AUTO_SNAPSHOT_ENABLED_OPTION):
            return DEFAULT_AUTO_SNAPSHOT_ENABLED
        return bool(int(cmds.optionVar(query=AUTO_SNAPSHOT_ENABLED_OPTION)))
    except Exception:
        return DEFAULT_AUTO_SNAPSHOT_ENABLED


def _set_auto_snapshot_enabled_option(enabled):
    if not MAYA_AVAILABLE:
        return
    try:
        cmds.optionVar(intValue=(AUTO_SNAPSHOT_ENABLED_OPTION, 1 if enabled else 0))
    except Exception:
        pass


def _quiet_scene_file_prompts_for_history():
    if not MAYA_AVAILABLE or not cmds:
        return
    try:
        cmds.file(prompt=False)
    except Exception:
        pass
    for option_name in HISTORY_SECURITY_PROMPT_OPTION_VARS:
        try:
            if cmds.optionVar(exists=option_name):
                cmds.optionVar(intValue=(option_name, 0))
        except Exception:
            pass


def _show_auto_history_security_warning(parent=None):
    message = (
        "Auto History may not work well with rigs like Amanda that trigger many Maya security popups.\n\n"
        "Those popups can block snapshot loading and saving during restore. If this rig is trusted, use Scene Helpers > Disable Maya Security Popups first, or keep Auto History off and save manual steps."
    )
    if QtWidgets:
        try:
            QtWidgets.QMessageBox.warning(parent, "Auto History And Security Popups", message)
            return
        except Exception:
            pass
    if om:
        try:
            om.MGlobal.displayWarning(message.replace("\n\n", " "))
        except Exception:
            pass


def _scene_summary_changed(previous_summary, current_summary):
    previous_summary = previous_summary or {}
    current_summary = current_summary or {}
    if not previous_summary or not current_summary:
        return False
    meaningful_keys = (
        "node_count",
        "node_types",
        "interesting_nodes",
        "anim_curves",
        "anim_curve_digest",
        "constraints",
        "animation_layers",
        "materials",
        "transform_digest",
        "material_digest",
    )
    return any(previous_summary.get(key) != current_summary.get(key) for key in meaningful_keys)


def _normalize_undo_name(value):
    return " ".join(str(value or "").lower().strip().split())


def _is_camera_transform_node(node_name):
    if not MAYA_AVAILABLE or not node_name:
        return False
    try:
        if cmds.nodeType(node_name) != "transform":
            return False
    except Exception:
        return False
    try:
        shapes = cmds.listRelatives(node_name, shapes=True, fullPath=True) or []
    except Exception:
        shapes = []
    for shape_name in shapes:
        try:
            if cmds.nodeType(shape_name) == "camera":
                return True
        except Exception:
            pass
    return False


def _qt_flag(scope_name, member_name, fallback=None):
    if not QtCore:
        return fallback
    scope = getattr(QtCore.Qt, scope_name, None)
    if scope is not None and hasattr(scope, member_name):
        return getattr(scope, member_name)
    return getattr(QtCore.Qt, member_name, fallback)


def _snapshot_file_size(record):
    snapshot_path = record.get("snapshot_path", "") if record else ""
    if snapshot_path and os.path.exists(snapshot_path):
        try:
            return int(os.path.getsize(snapshot_path))
        except Exception:
            return int(record.get("snapshot_size_bytes") or 0)
    try:
        return int(record.get("snapshot_size_bytes") or 0)
    except Exception:
        return 0


def _stored_snapshot_size(record):
    try:
        return max(0, int((record or {}).get("snapshot_size_bytes") or 0))
    except Exception:
        return 0


def _manifest_storage_size(manifest):
    return sum(_stored_snapshot_size(record) for record in ((manifest or {}).get("snapshots") or []))


def _compact_snapshot_records(records, max_count, current_snapshot_id=""):
    records = list(records or [])
    try:
        max_count = int(max_count or 0)
    except Exception:
        max_count = 0
    if max_count <= 0 or len(records) <= max_count:
        return records
    tail = list(records[-max_count:])
    if not current_snapshot_id:
        return tail
    if any(record.get("id") == current_snapshot_id for record in tail):
        return tail
    current_record = None
    for record in records:
        if record.get("id") == current_snapshot_id:
            current_record = record
            break
    if not current_record:
        return tail
    return [current_record] + tail[-max(0, max_count - 1):]


def _register_history_widget(widget):
    if widget not in HISTORY_UI_WIDGETS:
        HISTORY_UI_WIDGETS.append(widget)
    _ensure_history_scene_change_jobs()


def _queue_history_widget_call(widget, method_name):
    if not QtCore:
        return
    flag_name = "_aminate_history_{0}_queued".format(method_name)
    try:
        if getattr(widget, flag_name, False):
            return
        setattr(widget, flag_name, True)

        def _run():
            try:
                setattr(widget, flag_name, False)
                method = getattr(widget, method_name, None)
                if method:
                    method()
            except Exception:
                try:
                    if widget in HISTORY_UI_WIDGETS:
                        HISTORY_UI_WIDGETS.remove(widget)
                except Exception:
                    pass

        QtCore.QTimer.singleShot(0, _run)
    except Exception:
        try:
            HISTORY_UI_WIDGETS.remove(widget)
        except Exception:
            pass


def _notify_history_ui_changed():
    if not QtCore:
        return
    for widget in list(HISTORY_UI_WIDGETS):
        try:
            if widget is None:
                HISTORY_UI_WIDGETS.remove(widget)
                continue
            _queue_history_widget_call(widget, "refresh")
        except Exception:
            try:
                HISTORY_UI_WIDGETS.remove(widget)
            except Exception:
                pass


def _history_scene_changed():
    _suppress_auto_snapshots_for(2.0)
    if not QtCore:
        return
    refreshed_controllers = set()
    for widget in list(HISTORY_UI_WIDGETS):
        try:
            if widget is None:
                HISTORY_UI_WIDGETS.remove(widget)
                continue
            controller = getattr(widget, "controller", None)
            if controller is not None and id(controller) not in refreshed_controllers:
                refreshed_controllers.add(id(controller))
                try:
                    controller._clear_pending_auto_snapshot()
                    controller._mark_action_baseline()
                except Exception:
                    pass
            if hasattr(widget, "_on_scene_context_changed"):
                _queue_history_widget_call(widget, "_on_scene_context_changed")
            else:
                _queue_history_widget_call(widget, "refresh")
        except Exception:
            try:
                HISTORY_UI_WIDGETS.remove(widget)
            except Exception:
                pass


def _ensure_history_scene_change_jobs():
    if not MAYA_AVAILABLE:
        return
    _kill_history_scene_change_jobs()
    for event_name in ("SceneOpened", "NewSceneOpened", "SceneSaved"):
        job_id = HISTORY_SCENE_CHANGE_JOBS.get(event_name)
        if job_id:
            try:
                if cmds.scriptJob(exists=job_id):
                    continue
            except Exception:
                pass
        try:
            HISTORY_SCENE_CHANGE_JOBS[event_name] = cmds.scriptJob(
                event=(event_name, _history_scene_changed),
                protected=True,
            )
        except Exception:
            pass


def _kill_history_scene_change_jobs():
    if not MAYA_AVAILABLE:
        return 0
    killed = 0
    try:
        jobs = cmds.scriptJob(listJobs=True) or []
    except Exception:
        jobs = []
    for job_text in jobs:
        text = str(job_text)
        if "_history_scene_changed" not in text:
            continue
        try:
            job_id = int(text.split(":", 1)[0].strip())
            cmds.scriptJob(kill=job_id, force=True)
            killed += 1
        except Exception:
            pass
    HISTORY_SCENE_CHANGE_JOBS.clear()
    return killed


class MayaHistoryTimelineController(object):
    def __init__(self, status_callback=None):
        self.status_callback = status_callback
        self._action_timer = None
        self._auto_snapshot_busy = False
        self._last_action_signature = None
        self._last_auto_snapshot_time = 0.0
        self._last_action_summary = None
        self._pending_action_signature = None
        self._pending_action_started_time = 0.0
        self._pending_action_changed_time = 0.0
        self._pending_action_undo_names = []
        self._pending_action_base_summary = None
        self._pending_action_current_summary = None
        self._restored_snapshot_summary = None
        self._restore_settle_until = 0.0
        self._last_context_warning_time = 0.0

    def set_status_callback(self, callback):
        self.status_callback = callback

    def shutdown(self):
        self.stop_default_action_snapshots()
        return

    def _stop_other_action_snapshot_timers(self):
        for controller in list(HISTORY_ACTION_TIMER_CONTROLLERS):
            if controller is self:
                continue
            try:
                controller.stop_default_action_snapshots()
            except Exception:
                pass
        HISTORY_ACTION_TIMER_CONTROLLERS[:] = []
        if QtCore and QtWidgets:
            app = QtWidgets.QApplication.instance()
            if app and hasattr(app, "allWidgets"):
                for widget in app.allWidgets():
                    for timer in widget.findChildren(QtCore.QTimer, "aminateHistoryDefaultActionSnapshotTimer"):
                        if timer is self._action_timer:
                            continue
                        try:
                            timer.stop()
                        except Exception:
                            pass
                        try:
                            timer.deleteLater()
                        except Exception:
                            pass

    def start_default_action_snapshots(self, parent=None, interval_ms=2000):
        """Default v1 behaviour: save a sidecar step after each new Maya action."""
        if not MAYA_AVAILABLE or not QtCore:
            return False, "Auto history needs Maya and Qt."
        if not _auto_snapshot_enabled():
            self.stop_default_action_snapshots()
            self._stop_other_action_snapshot_timers()
            return False, "Auto History is off."
        if self._action_timer is not None:
            return True, "Auto history is already watching Maya actions."
        self._stop_other_action_snapshot_timers()
        context = self._context()
        if not context.get("ok"):
            self._emit_status(context.get("message", "Save the Maya scene first."), False, display=False)
        self._last_action_signature = self._current_action_signature()
        self._last_action_summary = self._restored_snapshot_summary or self._scene_summary()
        self._clear_pending_auto_snapshot()
        self._action_timer = QtCore.QTimer(parent)
        self._action_timer.setObjectName("aminateHistoryDefaultActionSnapshotTimer")
        self._action_timer.setInterval(max(1000, int(interval_ms or 2000)))
        self._action_timer.timeout.connect(self._maybe_snapshot_after_action)
        self._action_timer.start()
        HISTORY_ACTION_TIMER_CONTROLLERS.append(self)
        return True, "Auto history now saves after Maya actions."

    def stop_default_action_snapshots(self):
        timer = self._action_timer
        self._action_timer = None
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            try:
                timer.deleteLater()
            except Exception:
                pass
        while self in HISTORY_ACTION_TIMER_CONTROLLERS:
            HISTORY_ACTION_TIMER_CONTROLLERS.remove(self)

    def auto_snapshot_enabled(self):
        return _auto_snapshot_enabled()

    def set_auto_snapshot_enabled(self, enabled, parent=None, interval_ms=2000):
        enabled = bool(enabled)
        _set_auto_snapshot_enabled_option(enabled)
        if enabled:
            success, message = self.start_default_action_snapshots(parent=parent, interval_ms=interval_ms)
            if success:
                message = "Auto History is on."
            self._emit_status(message, success, display=False)
            _notify_history_ui_changed()
            return success, message
        self.stop_default_action_snapshots()
        self._stop_other_action_snapshot_timers()
        self._clear_pending_auto_snapshot()
        message = "Auto History is off. Manual Save Step still works."
        self._emit_status(message, True, display=False)
        _notify_history_ui_changed()
        return True, message

    def _current_action_signature(self):
        if not MAYA_AVAILABLE:
            return ""
        scene_path = self._current_scene_path()
        undo_name = ""
        try:
            undo_name = _normalize_undo_name(cmds.undoInfo(query=True, undoName=True) or "")
        except Exception:
            undo_name = ""
        return "{0}|{1}".format(scene_path, undo_name)

    def _is_autokey_enabled(self):
        if not MAYA_AVAILABLE:
            return False
        try:
            return bool(cmds.autoKeyframe(query=True, state=True))
        except Exception:
            return False

    def _auto_snapshot_settings_from_manifest(self, manifest):
        mode = manifest.get("auto_snapshot_mode") or DEFAULT_AUTO_SNAPSHOT_MODE
        if mode not in (AUTO_SNAPSHOT_MODE_ALL, AUTO_SNAPSHOT_MODE_CUSTOM):
            mode = DEFAULT_AUTO_SNAPSHOT_MODE
        stored = manifest.get("auto_snapshot_triggers") or {}
        triggers = dict(DEFAULT_AUTO_SNAPSHOT_TRIGGERS)
        for key in triggers:
            if key in stored:
                triggers[key] = bool(stored[key])
        return {"mode": mode, "triggers": triggers}

    def auto_snapshot_settings(self):
        context = self._context()
        if not context.get("ok"):
            return {"mode": DEFAULT_AUTO_SNAPSHOT_MODE, "triggers": dict(DEFAULT_AUTO_SNAPSHOT_TRIGGERS)}
        manifest = self._load_manifest(context)
        return self._auto_snapshot_settings_from_manifest(manifest)

    def set_auto_snapshot_settings(self, mode=DEFAULT_AUTO_SNAPSHOT_MODE, triggers=None):
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not update Auto History settings.")
        mode = mode if mode in (AUTO_SNAPSHOT_MODE_ALL, AUTO_SNAPSHOT_MODE_CUSTOM) else DEFAULT_AUTO_SNAPSHOT_MODE
        manifest = self._load_manifest(context)
        current = self._auto_snapshot_settings_from_manifest(manifest)
        merged = dict(current["triggers"])
        for key in merged:
            if triggers and key in triggers:
                merged[key] = bool(triggers[key])
        manifest["auto_snapshot_mode"] = mode
        manifest["auto_snapshot_triggers"] = merged
        manifest.setdefault("events", []).append({"type": "auto_snapshot_settings", "timestamp": _now_iso(), "mode": mode})
        self._save_manifest(context, manifest)
        message = "Auto History saves after every Maya action." if mode == AUTO_SNAPSHOT_MODE_ALL else "Auto History uses the checked custom triggers."
        self._emit_status(message, True)
        return True, message

    def _classify_auto_snapshot_action(self, undo_name, previous_summary=None, current_summary=None):
        text = _normalize_undo_name(undo_name)
        if self._is_view_camera_navigation_action(text):
            return {"other"}
        triggers = set()
        if any(token in text for token in ("key", "setkeyframe", "cutkey", "pastekey", "animcurve", "breakdown", "autokey", "auto key", "auto-key")):
            triggers.add("keyframes")
        if "constraint" in text:
            triggers.add("constraints")
        if any(token in text for token in ("animlayer", "animation layer", "layer")):
            triggers.add("animation_layers")
        if any(token in text for token in ("parent", "unparent", "group", "hierarchy")):
            triggers.add("parenting")
        if any(token in text for token in ("reference", "import", "file")):
            triggers.add("references")
        if any(token in text for token in ("move", "rotate", "scale", "translate", "transform", "xform", "manipulator")):
            triggers.add("transforms")
        if any(token in text for token in ("material", "shader", "hypershade", "texture", "assign", "shading", "lambert", "blinn", "phong", "aistandardsurface")):
            triggers.add("materials")
        if any(token in text for token in ("create", "delete", "duplicate", "poly", "curve", "locator", "rename", "node")):
            triggers.add("nodes")
        previous_summary = previous_summary or {}
        current_summary = current_summary or {}
        if previous_summary and current_summary:
            if previous_summary.get("node_count") != current_summary.get("node_count") or previous_summary.get("node_types") != current_summary.get("node_types"):
                triggers.add("nodes")
            if previous_summary.get("constraints") != current_summary.get("constraints"):
                triggers.add("constraints")
            if previous_summary.get("anim_curves") != current_summary.get("anim_curves"):
                triggers.add("keyframes")
            if previous_summary.get("anim_curve_digest") != current_summary.get("anim_curve_digest"):
                triggers.add("keyframes")
                previous_curve_values = _summary_dict(previous_summary, "anim_curve_values")
                current_curve_values = _summary_dict(current_summary, "anim_curve_values")
                previous_targets = _summary_dict(previous_summary, "anim_curve_targets")
                current_targets = _summary_dict(current_summary, "anim_curve_targets")
                changed_curve_names = set(previous_curve_values.keys()).union(set(current_curve_values.keys()))
                for curve_name in changed_curve_names:
                    if previous_curve_values.get(curve_name) == current_curve_values.get(curve_name):
                        continue
                    target_text = " ".join([str(item) for item in (current_targets.get(curve_name) or previous_targets.get(curve_name) or [])]).lower()
                    if "constraint" in target_text:
                        triggers.add("constraints")
            if previous_summary.get("animation_layers") != current_summary.get("animation_layers"):
                triggers.add("animation_layers")
            if previous_summary.get("transform_digest") != current_summary.get("transform_digest"):
                triggers.add("transforms")
                if self._is_autokey_enabled():
                    triggers.add("keyframes")
            if previous_summary.get("material_digest") != current_summary.get("material_digest"):
                triggers.add("materials")
        if not triggers:
            triggers.add("other")
        return triggers

    def _is_timeline_scrub_action(self, undo_name, previous_summary=None, current_summary=None):
        text = _normalize_undo_name(undo_name)
        if any(token in text for token in ("currenttime", "current time", "setcurrenttime", "time changed", "timechange", "playback", "next frame", "previous frame", "goto frame", "go to frame", "scrub")):
            return True
        previous_summary = previous_summary or {}
        current_summary = current_summary or {}
        if not previous_summary or not current_summary:
            return False
        try:
            previous_time = float(previous_summary.get("current_time", 0.0))
            current_time = float(current_summary.get("current_time", 0.0))
        except Exception:
            previous_time = current_time = 0.0
        if abs(previous_time - current_time) <= 1.0e-4:
            return False
        stable_keys = (
            "node_count",
            "node_types",
            "interesting_nodes",
            "anim_curves",
            "anim_curve_digest",
            "constraints",
            "animation_layers",
            "materials",
            "material_digest",
        )
        for key in stable_keys:
            if previous_summary.get(key) != current_summary.get(key):
                return False
        return True

    def _is_view_camera_navigation_action(self, undo_name):
        text = _normalize_undo_name(undo_name)
        if not text:
            return False
        view_tokens = (
            "tumble",
            "tumble tool",
            "dolly",
            "dolly tool",
            "track",
            "track tool",
            "pan tool",
            "pan view",
            "zoom tool",
            "zoom view",
            "orbit",
            "orbit tool",
            "look through",
            "lookthrough",
            "frame selected",
            "fit view",
            "camera view",
            "view camera",
            "view tumble",
            "view dolly",
            "view track",
            "viewdolly",
            "viewdollytool",
            "viewtumble",
            "viewtumbletool",
            "viewtrack",
            "viewtracktool",
        )
        return any(token in text for token in view_tokens)

    def _should_auto_snapshot_for_action(self, manifest, undo_name, previous_summary=None, current_summary=None):
        settings = self._auto_snapshot_settings_from_manifest(manifest)
        if settings["mode"] == AUTO_SNAPSHOT_MODE_ALL:
            return True, "Maya action"
        classified = self._classify_auto_snapshot_action(undo_name, previous_summary, current_summary)
        enabled = {key for key, value in settings["triggers"].items() if value}
        matched = sorted(classified.intersection(enabled))
        if matched:
            return True, ", ".join(matched)
        return False, ", ".join(sorted(classified))

    def _maybe_snapshot_after_action(self):
        if not _auto_snapshot_enabled():
            self.stop_default_action_snapshots()
            self._clear_pending_auto_snapshot()
            return
        if self._auto_snapshot_busy:
            return
        context = self._context()
        if not context.get("ok"):
            now = time.time()
            if now - self._last_context_warning_time > 10.0:
                self._last_context_warning_time = now
                self._emit_status(context.get("message", "Save the Maya scene first."), False, display=False)
            self._clear_pending_auto_snapshot()
            return
        if _auto_snapshots_are_suppressed():
            self._mark_action_baseline()
            return
        signature = self._current_action_signature()
        now = time.time()
        if self._pending_action_signature and now - self._pending_action_changed_time >= AUTO_SNAPSHOT_SETTLE_SECONDS:
            self._auto_snapshot_busy = True
            try:
                manifest = self._load_manifest(context)
                self._flush_pending_auto_snapshot(context, manifest, now)
            finally:
                self._auto_snapshot_busy = False
            return
        if not signature:
            return
        if (
            signature == self._last_action_signature
            and not self._pending_action_signature
            and not self._restored_snapshot_summary
        ):
            return
        self._auto_snapshot_busy = True
        try:
            undo_name = "Maya action"
            try:
                undo_name = cmds.undoInfo(query=True, undoName=True) or "Maya action"
            except Exception:
                pass
            if self._is_view_camera_navigation_action(undo_name):
                self._last_action_signature = signature
                self._restored_snapshot_summary = None
                self._last_auto_snapshot_time = now
                self._clear_pending_auto_snapshot()
                return
            manifest = self._load_manifest(context)
            current_summary = self._scene_summary()
            if self._is_restore_settling(current_summary, now, undo_name, signature != self._last_action_signature):
                self._last_action_signature = signature
                self._last_action_summary = current_summary
                self._last_auto_snapshot_time = now
                self._clear_pending_auto_snapshot()
                return
            if self._is_timeline_scrub_action(undo_name, self._last_action_summary, current_summary):
                self._last_action_signature = signature
                self._last_action_summary = current_summary
                self._last_auto_snapshot_time = now
                self._clear_pending_auto_snapshot()
                return
            if not _scene_summary_changed(self._last_action_summary, current_summary):
                self._last_action_signature = signature
                self._last_action_summary = current_summary
                self._last_auto_snapshot_time = now
                self._clear_pending_auto_snapshot()
                return
            if self._pending_action_signature and not _scene_summary_changed(self._pending_action_current_summary, current_summary):
                return
            self._queue_pending_auto_snapshot(signature, undo_name, self._last_action_summary, current_summary, now)
        finally:
            self._auto_snapshot_busy = False

    def create_post_action_snapshot(self, reason):
        if not _auto_snapshot_enabled():
            return False, "Auto History is off.", None
        if self._auto_snapshot_busy:
            return False, "Auto history is already saving.", None
        self._auto_snapshot_busy = True
        try:
            context = self._context()
            if context.get("ok"):
                manifest = self._load_manifest(context)
                current_summary = self._scene_summary()
                if not _scene_summary_changed(self._last_action_summary, current_summary):
                    self._last_action_signature = self._current_action_signature()
                    self._last_action_summary = current_summary
                    return False, "Auto history skipped because the scene did not change.", None
                should_save, _matched = self._should_auto_snapshot_for_action(manifest, reason, self._last_action_summary, current_summary)
                if not should_save:
                    self._last_action_signature = self._current_action_signature()
                    self._last_action_summary = current_summary
                    return False, "Auto history skipped by custom trigger settings.", None
            label, note = self._action_label_and_note(self._last_action_summary, current_summary, reason or "Maya action")
            success, message, record = self.create_auto_snapshot(reason or "Maya action", label=label, note=note)
            self._last_action_signature = self._current_action_signature()
            self._last_action_summary = self._scene_summary()
            self._last_auto_snapshot_time = time.time()
            return success, message, record
        finally:
            self._auto_snapshot_busy = False

    def _mark_action_baseline(self, summary=None):
        self._last_action_signature = self._current_action_signature()
        self._last_action_summary = summary or self._scene_summary()
        self._last_auto_snapshot_time = time.time()
        self._clear_pending_auto_snapshot()

    def _mark_restore_baseline(self, summary=None, settle_seconds=6.0):
        self._restored_snapshot_summary = summary or self._scene_summary()
        self._restore_settle_until = time.time() + float(settle_seconds or 0.0)
        self._mark_action_baseline(self._restored_snapshot_summary)

    def _clear_restore_baseline(self):
        self._restored_snapshot_summary = None
        self._restore_settle_until = 0.0

    def _is_restore_settling(self, current_summary, now=None, undo_name="", action_changed=True):
        restored_summary = self._restored_snapshot_summary
        if not restored_summary:
            return False
        now = time.time() if now is None else now
        if not _scene_summary_changed(restored_summary, current_summary):
            self._restored_snapshot_summary = current_summary
            return True
        if not action_changed:
            self._restored_snapshot_summary = current_summary
            self._mark_action_baseline(current_summary)
            return True
        text = str(undo_name or "").lower()
        real_edit_tokens = (
            "setattr",
            "setkey",
            "keyframe",
            "cutkey",
            "pastekey",
            "delete",
            "move",
            "rotate",
            "scale",
            "xform",
            "constraint",
            "parent",
            "poly",
            "create",
            "duplicate",
        )
        non_edit_tokens = (
            "select",
            "hilite",
            "highlight",
            "graph",
            "outliner",
            "channel",
            "refresh",
            "frame",
            "time",
            "panel",
            "view",
            "show",
        )
        is_real_edit = any(token in text for token in real_edit_tokens)
        if any(token in text for token in non_edit_tokens):
            self._restored_snapshot_summary = current_summary
            self._mark_action_baseline(current_summary)
            return True
        if now <= self._restore_settle_until and not is_real_edit:
            self._restored_snapshot_summary = current_summary
            self._mark_action_baseline(current_summary)
            return True
        self._clear_restore_baseline()
        return False

    def _clear_pending_auto_snapshot(self):
        self._pending_action_signature = None
        self._pending_action_started_time = 0.0
        self._pending_action_changed_time = 0.0
        self._pending_action_undo_names = []
        self._pending_action_base_summary = None
        self._pending_action_current_summary = None

    def _queue_pending_auto_snapshot(self, signature, undo_name, base_summary, current_summary, now):
        if not self._pending_action_signature:
            self._pending_action_started_time = now
            self._pending_action_base_summary = base_summary or self._last_action_summary
            self._pending_action_undo_names = []
        self._pending_action_signature = signature
        self._pending_action_changed_time = now
        self._pending_action_current_summary = current_summary
        if undo_name and undo_name not in self._pending_action_undo_names:
            self._pending_action_undo_names.append(undo_name)

    def _pending_auto_snapshot_name(self):
        names = [name for name in self._pending_action_undo_names if name]
        if not names:
            return "Maya action"
        if len(names) == 1:
            return names[0]
        lowered = " ".join(names).lower()
        if any(token in lowered for token in ("key", "setkeyframe", "cutkey", "pastekey", "animcurve", "breakdown")):
            return "keyframe edit"
        if any(token in lowered for token in ("move", "rotate", "scale", "translate", "transform", "xform", "manipulator")):
            return "transform edit"
        return "Maya action batch"

    def _flush_pending_auto_snapshot(self, context, manifest, now):
        if not self._pending_action_signature:
            return False
        undo_name = self._pending_auto_snapshot_name()
        base_summary = self._pending_action_base_summary or self._last_action_summary
        current_summary = self._pending_action_current_summary or self._scene_summary()
        self._last_action_signature = self._pending_action_signature
        self._last_action_summary = current_summary
        if self._is_timeline_scrub_action(undo_name, base_summary, current_summary) or not _scene_summary_changed(base_summary, current_summary):
            self._last_auto_snapshot_time = now
            self._clear_pending_auto_snapshot()
            return False
        should_save, reason = self._should_auto_snapshot_for_action(manifest, undo_name, base_summary, current_summary)
        self._clear_pending_auto_snapshot()
        if not should_save:
            return False
        self._last_auto_snapshot_time = now
        label, note = self._action_label_and_note(base_summary, current_summary, undo_name)
        self.create_auto_snapshot(reason or _safe_name(undo_name) or "Maya action", label=label, note=note)
        return True

    def _emit_status(self, message, success=True, display=True):
        if self.status_callback:
            try:
                self.status_callback(message, success)
            except TypeError:
                self.status_callback(message)
        if not display:
            return
        if success:
            _display_info(message)
        else:
            _display_warning(message)

    def _current_scene_path(self):
        if not MAYA_AVAILABLE:
            return ""
        try:
            return cmds.file(query=True, sceneName=True) or ""
        except Exception:
            return ""

    def _context(self, prefer_meta=True):
        scene_path = self._current_scene_path()
        original_from_meta = _read_meta_value("originalScenePath") if prefer_meta else ""
        if (
            original_from_meta
            and os.path.exists(os.path.dirname(original_from_meta))
            and _scene_uses_meta_original(scene_path, original_from_meta)
        ):
            original_scene_path = original_from_meta
        else:
            original_from_snapshot_manifest = _infer_original_scene_from_snapshot_path(scene_path)
            if original_from_snapshot_manifest:
                original_scene_path = original_from_snapshot_manifest
            elif _is_unlinked_history_snapshot_path(scene_path):
                return {
                    "ok": False,
                    "message": "This is a History Timeline snapshot file. Open the original Maya scene so new snapshots stay beside the scene file.",
                }
            else:
                original_scene_path = scene_path
        if not original_scene_path:
            return {
                "ok": False,
                "message": "Save the Maya scene first. History Timeline starts after Maya has a real scene file path, so snapshots can be saved beside that scene file.",
            }
        scene_dir = os.path.dirname(os.path.abspath(original_scene_path))
        scene_base = os.path.splitext(os.path.basename(original_scene_path))[0]
        history_root = os.path.join(scene_dir, "{0}_aminate_history".format(scene_base))
        snapshot_dir = os.path.join(history_root, SNAPSHOT_FOLDER_NAME)
        manifest_path = os.path.join(history_root, MANIFEST_FILE_NAME)
        return {
            "ok": True,
            "scene_path": scene_path,
            "original_scene_path": os.path.abspath(original_scene_path),
            "history_root": history_root,
            "snapshot_dir": snapshot_dir,
            "manifest_path": manifest_path,
        }

    def _load_manifest(self, context):
        manifest_path = context.get("manifest_path", "")
        if manifest_path and os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as handle:
                    manifest = json.load(handle)
            except Exception:
                manifest = {}
        else:
            manifest = {}
        manifest.setdefault("version", MANIFEST_VERSION)
        manifest.setdefault("aminate_history_version", AMINATE_HISTORY_VERSION)
        manifest.setdefault("original_scene_path", context.get("original_scene_path", ""))
        manifest.setdefault("current_snapshot_id", "")
        manifest.setdefault("active_branch_id", "main")
        manifest.setdefault("snapshot_cap", DEFAULT_SNAPSHOT_CAP)
        manifest.setdefault("auto_snapshot_mode", DEFAULT_AUTO_SNAPSHOT_MODE)
        manifest.setdefault("auto_snapshot_triggers", dict(DEFAULT_AUTO_SNAPSHOT_TRIGGERS))
        manifest.setdefault("branches", {})
        manifest.setdefault("snapshots", [])
        manifest.setdefault("events", [])
        self._ensure_branch_records(manifest)
        return manifest

    def _ensure_branch_records(self, manifest):
        branches = manifest.setdefault("branches", {})
        if "main" not in branches:
            branches["main"] = {"id": "main", "label": "Main", "color": BRANCH_COLOR_PALETTE[0], "parent_id": "", "index": 0}
        branches["main"].setdefault("index", 0)
        next_index = 1
        for branch_id, record in sorted(branches.items()):
            if branch_id == "main":
                continue
            try:
                next_index = max(next_index, int(record.get("index") or 0) + 1)
            except Exception:
                pass
        for item in manifest.get("snapshots") or []:
            branch_id = item.get("branch_id") or "main"
            if branch_id not in branches:
                branches[branch_id] = {
                    "id": branch_id,
                    "label": "Branch {0}".format(next_index),
                    "color": item.get("branch_color") or _branch_color_from_id(branch_id, len(branches)),
                    "parent_id": item.get("branched_from_id", ""),
                    "index": next_index,
                }
                next_index += 1
            item.setdefault("branch_id", branch_id)
            item.setdefault("branch_color", branches[branch_id].get("color") or _branch_color_from_id(branch_id))
            item.setdefault("branch_label", branches[branch_id].get("label") or _branch_display_name(branch_id))
            if item.get("branched_from_id") and not item.get("branched_from_label"):
                parent = self._snapshot_for_id(manifest, item.get("branched_from_id"))
                item["branched_from_label"] = parent.get("label", item.get("branched_from_id")) if parent else item.get("branched_from_id")
        for branch_id, record in sorted(branches.items()):
            if branch_id == "main":
                continue
            if not record.get("index"):
                record["index"] = next_index
                if not record.get("label") or str(record.get("label")).startswith("Branch "):
                    record["label"] = "Branch {0}".format(next_index)
                next_index += 1

    def _branch_record(self, manifest, branch_id):
        self._ensure_branch_records(manifest)
        branches = manifest.setdefault("branches", {})
        branch_id = branch_id or "main"
        if branch_id not in branches:
            index = self._next_branch_index(manifest)
            branches[branch_id] = {
                "id": branch_id,
                "label": "Branch {0}".format(index),
                "color": _branch_color_from_id(branch_id, len(branches)),
                "parent_id": "",
                "index": index,
            }
        return branches[branch_id]

    def _next_branch_index(self, manifest):
        self._ensure_branch_records(manifest)
        highest = 0
        for record in (manifest.get("branches") or {}).values():
            try:
                highest = max(highest, int(record.get("index") or 0))
            except Exception:
                pass
        return highest + 1

    def _create_branch(self, manifest, parent_id):
        index = self._next_branch_index(manifest)
        branch_id = "branch_{0}_{1}".format(index, uuid.uuid4().hex[:4])
        color = _branch_color_from_id(branch_id, len(manifest.get("branches") or {}))
        label = "Branch {0}".format(index)
        manifest.setdefault("branches", {})[branch_id] = {"id": branch_id, "label": label, "color": color, "parent_id": parent_id or "", "index": index}
        manifest["active_branch_id"] = branch_id
        manifest.setdefault("events", []).append(
            {"type": "branch_create", "branch_id": branch_id, "parent_id": parent_id or "", "timestamp": _now_iso()}
        )
        return branch_id

    def _save_manifest(self, context, manifest):
        if not context.get("ok"):
            return
        if not os.path.isdir(context["history_root"]):
            os.makedirs(context["history_root"])
        if not os.path.isdir(context["snapshot_dir"]):
            os.makedirs(context["snapshot_dir"])
        manifest["original_scene_path"] = context.get("original_scene_path", "")
        manifest["snapshot_count"] = len(manifest.get("snapshots") or [])
        manifest["history_storage_size_bytes"] = _manifest_storage_size(manifest)
        manifest["updated_at"] = _now_iso()
        with open(context["manifest_path"], "w") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
        _write_meta(context, manifest)

    def _snapshot_for_id(self, manifest, snapshot_id):
        for item in manifest.get("snapshots") or []:
            if item.get("id") == snapshot_id:
                return item
        return None

    def _scene_summary(self):
        if not MAYA_AVAILABLE:
            return {}
        current_time = 0.0
        try:
            current_time = float(cmds.currentTime(query=True))
        except Exception:
            current_time = 0.0
        nodes = cmds.ls(long=True) or []
        node_types = {}
        interesting = []
        constraints = []
        anim_curves = []
        anim_curve_values = []
        anim_curve_value_map = {}
        anim_curve_targets = {}
        anim_layers = []
        materials = []
        material_values = []
        material_value_map = {}
        transform_values = []
        transform_value_map = {}
        material_types = {
            "lambert",
            "blinn",
            "phong",
            "phongE",
            "surfaceShader",
            "aiStandardSurface",
            "standardSurface",
            "file",
            "place2dTexture",
            "shadingEngine",
        }
        for node_name in nodes:
            try:
                node_type = cmds.nodeType(node_name)
            except Exception:
                node_type = "unknown"
            node_types[node_type] = node_types.get(node_type, 0) + 1
            short = _short_name(node_name).lower()
            if node_type.startswith("animCurve"):
                anim_curves.append(node_name)
                try:
                    times = cmds.keyframe(node_name, query=True, timeChange=True) or []
                    values = cmds.keyframe(node_name, query=True, valueChange=True) or []
                    pairs = []
                    for index, key_time in enumerate(times):
                        key_value = values[index] if index < len(values) else 0.0
                        pairs.append("{0:.5f}:{1:.5f}".format(float(key_time), float(key_value)))
                    curve_value = ",".join(pairs)
                    anim_curve_values.append("{0}:{1}".format(node_name, curve_value))
                    anim_curve_value_map[node_name] = curve_value
                except Exception:
                    anim_curve_values.append("{0}:x".format(node_name))
                    anim_curve_value_map[node_name] = "x"
                try:
                    outputs = cmds.listConnections(node_name + ".output", plugs=True, destination=True, source=False) or []
                    anim_curve_targets[node_name] = [_short_name(item.split(".", 1)[0]) for item in outputs]
                except Exception:
                    anim_curve_targets[node_name] = []
            if node_type.endswith("Constraint"):
                constraints.append(node_name)
            if node_type == "animLayer":
                anim_layers.append(node_name)
            if node_type in material_types or "shader" in node_type.lower() or "texture" in node_type.lower():
                materials.append("{0}|{1}".format(node_type, node_name))
                attr_values = []
                for attr_name in ("color", "baseColor", "transparency", "fileTextureName", "specularColor", "roughness", "metalness"):
                    try:
                        value = cmds.getAttr(node_name + "." + attr_name)
                        attr_values.append("{0}={1}".format(attr_name, value))
                    except Exception:
                        pass
                material_value = "{0}:{1}".format(node_name, ";".join(attr_values))
                material_values.append(material_value)
                material_value_map[node_name] = material_value
            if node_type == "transform" and not _is_camera_transform_node(node_name):
                values = []
                for attr_name in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ", "scaleX", "scaleY", "scaleZ"):
                    try:
                        values.append("{0:.5f}".format(float(cmds.getAttr(node_name + "." + attr_name))))
                    except Exception:
                        values.append("x")
                transform_value = "{0}:{1}".format(node_name, ",".join(values))
                transform_values.append(transform_value)
                transform_value_map[node_name] = transform_value
            if (
                node_type.endswith("Constraint")
                or node_type.startswith("animCurve")
                or "adp" in short
                or "amir" in short
                or "pencil" in short
                or node_type in ("animLayer", "network", "transform", "joint")
            ):
                interesting.append("{0}|{1}".format(node_type, node_name))
        return {
            "current_time": current_time,
            "node_count": len(nodes),
            "node_types": node_types,
            "interesting_nodes": sorted(interesting),
            "anim_curves": sorted(anim_curves),
            "anim_curve_targets": anim_curve_targets,
            "anim_curve_values": anim_curve_value_map,
            "anim_curve_digest": hashlib.sha1("|".join(sorted(anim_curve_values)).encode("utf-8")).hexdigest(),
            "constraints": sorted(constraints),
            "animation_layers": sorted(anim_layers),
            "materials": sorted(materials),
            "material_values": material_value_map,
            "transform_digest": hashlib.sha1("|".join(sorted(transform_values)).encode("utf-8")).hexdigest(),
            "transform_values": transform_value_map,
            "material_digest": hashlib.sha1("|".join(sorted(materials + material_values)).encode("utf-8")).hexdigest(),
        }

    def _delta_from_previous(self, manifest, summary):
        snapshots = manifest.get("snapshots") or []
        if not snapshots:
            return {
                "created_nodes": [],
                "deleted_nodes": [],
                "changed_counts": True,
            }
        previous = snapshots[-1].get("scene_summary") or {}
        previous_nodes = set(previous.get("interesting_nodes") or [])
        current_nodes = set(summary.get("interesting_nodes") or [])
        return {
            "created_nodes": sorted(current_nodes - previous_nodes),
            "deleted_nodes": sorted(previous_nodes - current_nodes),
            "changed_counts": previous.get("node_types") != summary.get("node_types"),
        }

    def _action_details_between_summaries(self, previous_summary, current_summary, undo_name="Maya action"):
        previous_summary = previous_summary or {}
        current_summary = current_summary or {}
        created_nodes = sorted(set(_summary_list(current_summary, "interesting_nodes")) - set(_summary_list(previous_summary, "interesting_nodes")))
        deleted_nodes = sorted(set(_summary_list(previous_summary, "interesting_nodes")) - set(_summary_list(current_summary, "interesting_nodes")))
        previous_transforms = _summary_dict(previous_summary, "transform_values")
        current_transforms = _summary_dict(current_summary, "transform_values")
        changed_transforms = sorted(
            _short_name(node_name)
            for node_name, value in current_transforms.items()
            if previous_transforms.get(node_name) != value
        )
        previous_curves = _summary_dict(previous_summary, "anim_curve_values")
        current_curves = _summary_dict(current_summary, "anim_curve_values")
        changed_curve_nodes = sorted(
            node_name for node_name, value in current_curves.items() if previous_curves.get(node_name) != value
        )
        targets_by_curve = _summary_dict(current_summary, "anim_curve_targets")
        changed_key_targets = []
        for curve_name in changed_curve_nodes:
            targets = targets_by_curve.get(curve_name) or []
            if targets:
                changed_key_targets.extend(targets)
            else:
                changed_key_targets.append(_short_name(curve_name))
        changed_key_targets = sorted(set(changed_key_targets))
        previous_materials = _summary_dict(previous_summary, "material_values")
        current_materials = _summary_dict(current_summary, "material_values")
        changed_materials = sorted(
            _short_name(node_name)
            for node_name, value in current_materials.items()
            if previous_materials.get(node_name) != value
        )
        action_types = sorted(self._classify_auto_snapshot_action(undo_name, previous_summary, current_summary))
        if not action_types:
            action_types = ["scene"]
        objects = []
        objects.extend(changed_key_targets)
        objects.extend(changed_transforms)
        objects.extend(_short_name(item.split("|", 1)[-1]) for item in created_nodes)
        objects.extend(_short_name(item.split("|", 1)[-1]) for item in deleted_nodes)
        objects.extend(changed_materials)
        objects = sorted(set(item for item in objects if item))
        return {
            "undo_name": str(undo_name or "Maya action"),
            "action_types": action_types,
            "objects": objects,
            "changed_transforms": changed_transforms,
            "changed_key_targets": changed_key_targets,
            "changed_curve_nodes": [_short_name(item) for item in changed_curve_nodes],
            "changed_materials": changed_materials,
            "created_nodes": [_short_name(item.split("|", 1)[-1]) for item in created_nodes],
            "deleted_nodes": [_short_name(item.split("|", 1)[-1]) for item in deleted_nodes],
        }

    def _action_label_and_note(self, previous_summary, current_summary, undo_name="Maya action"):
        details = self._action_details_between_summaries(previous_summary, current_summary, undo_name)
        action_types = details.get("action_types") or ["scene"]
        action_label = action_types[0].replace("_", " ").title()
        objects = details.get("objects") or []
        object_preview = _join_preview(objects, 3)
        label = "{0}".format(action_label)
        if object_preview:
            label = "{0}: {1}".format(action_label, object_preview)
        sections = [
            "Action summary: {0}.".format(label),
            "Maya undo item: {0}.".format(details.get("undo_name") or "Maya action"),
        ]
        if objects:
            sections.append("Objects: {0}.".format(_join_preview(objects, 12)))
        if details.get("changed_key_targets"):
            sections.append("Keyed controls or attributes: {0}.".format(_join_preview(details.get("changed_key_targets"), 12)))
        if details.get("changed_transforms"):
            sections.append("Changed transforms: {0}.".format(_join_preview(details.get("changed_transforms"), 12)))
        if details.get("created_nodes"):
            sections.append("Created nodes: {0}.".format(_join_preview(details.get("created_nodes"), 12)))
        if details.get("deleted_nodes"):
            sections.append("Deleted nodes: {0}.".format(_join_preview(details.get("deleted_nodes"), 12)))
        if details.get("changed_materials"):
            sections.append("Changed materials: {0}.".format(_join_preview(details.get("changed_materials"), 12)))
        if details.get("changed_curve_nodes"):
            sections.append("Changed animation curves: {0}.".format(_join_preview(details.get("changed_curve_nodes"), 12)))
        return label[:80], " ".join(sections)

    def create_snapshot(self, label="", color="", milestone=False, note="", auto=False, reason=""):
        if not MAYA_AVAILABLE:
            return False, "History Timeline only works inside Maya.", None
        _suppress_auto_snapshots_for(2.0)
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not create History Timeline snapshot."), None
        manifest = self._load_manifest(context)
        snapshot_id = "snap_{0}_{1}".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:8])
        label = (label or "").strip()
        if not label:
            if milestone:
                label = "Milestone"
            elif auto:
                label = "Auto - {0}".format(reason or "Safety")
            else:
                label = "Manual saved step"
        note = (note or "").strip()
        if not note and not auto:
            try:
                manual_frame = int(round(float(cmds.currentTime(query=True)))) if MAYA_AVAILABLE else 0
            except Exception:
                manual_frame = 0
            note = "Manual snapshot saved by user on frame {0}.".format(manual_frame)
        explicit_color = (color or "").strip()
        frame_value = 0.0
        try:
            frame_value = float(cmds.currentTime(query=True))
        except Exception:
            frame_value = 0.0
        parent_id = manifest.get("current_snapshot_id", "")
        active_branch = manifest.get("active_branch_id", "main") or "main"
        branched_from_id = ""
        branched_from_label = ""
        parent_record = self._snapshot_for_id(manifest, parent_id)
        parent_branch = (parent_record.get("branch_id") if parent_record else active_branch) or active_branch
        if parent_id and snapshots_has_future(manifest, parent_id, branch_id=parent_branch):
            active_branch = self._create_branch(manifest, parent_id)
            branched_from_id = parent_id
            branched_from_label = parent_record.get("label", parent_id) if parent_record else parent_id
        branch_info = self._branch_record(manifest, active_branch)
        branch_color = branch_info.get("color") or _branch_color_from_id(active_branch)
        color = explicit_color or branch_color
        summary = self._scene_summary()
        record = {
            "id": snapshot_id,
            "label": label,
            "color": color,
            "note": note,
            "frame": frame_value,
            "timestamp": _now_iso(),
            "milestone": bool(milestone),
            "locked": bool(milestone),
            "auto": bool(auto),
            "reason": reason or "",
            "parent_id": parent_id,
            "branch_id": active_branch,
            "branch_label": branch_info.get("label") or _branch_display_name(active_branch),
            "branch_color": branch_color,
            "branched_from_id": branched_from_id,
            "branched_from_label": branched_from_label,
            "original_scene_path": context.get("original_scene_path", ""),
            "snapshot_path": "",
            "snapshot_size_bytes": 0,
            "scene_summary": summary,
            "v2_delta": self._delta_from_previous(manifest, summary),
        }
        ext = os.path.splitext(context["original_scene_path"])[1] or ".ma"
        snapshot_name = "{0}_{1}{2}".format(snapshot_id, _safe_name(label), ext)
        record["snapshot_path"] = os.path.join(context["snapshot_dir"], snapshot_name)
        try:
            self._write_snapshot_file(context, record["snapshot_path"])
            record["snapshot_size_bytes"] = _snapshot_file_size(record)
        except Exception as exc:
            return False, "Could not write snapshot: {0}".format(exc), None
        manifest.setdefault("snapshots", []).append(record)
        manifest["current_snapshot_id"] = snapshot_id
        manifest.setdefault("events", []).append(
            {"type": "create", "snapshot_id": snapshot_id, "timestamp": record["timestamp"], "reason": reason or ""}
        )
        self._apply_snapshot_cap(context, manifest)
        self._mark_action_baseline(summary)
        _notify_history_ui_changed()
        message = "Saved {0} snapshot: {1}".format("milestone" if milestone else ("auto" if auto else "step"), label)
        self._emit_status(message, True, display=not auto)
        _suppress_auto_snapshots_for(2.0)
        return True, message, record

    def _apply_snapshot_cap(self, context, manifest):
        cap = int(manifest.get("snapshot_cap") or 0)
        snapshots = manifest.get("snapshots") or []
        if cap <= 0 or len(snapshots) <= cap:
            self._save_manifest(context, manifest)
            return
        keep_ids = set(item.get("id") for item in snapshots if item.get("milestone") or item.get("locked"))
        removable = [item for item in snapshots if item.get("id") not in keep_ids]
        while len(snapshots) > cap and removable:
            victim = removable.pop(0)
            snapshot_path = victim.get("snapshot_path", "")
            if snapshot_path and os.path.exists(snapshot_path):
                try:
                    os.remove(snapshot_path)
                except Exception:
                    pass
            snapshots = [item for item in snapshots if item.get("id") != victim.get("id")]
        manifest["snapshots"] = snapshots
        current_id = manifest.get("current_snapshot_id", "")
        if current_id and current_id not in [item.get("id") for item in snapshots]:
            manifest["current_snapshot_id"] = snapshots[-1]["id"] if snapshots else ""
        manifest.setdefault("events", []).append({"type": "cap_cleanup", "timestamp": _now_iso(), "cap": cap})
        self._save_manifest(context, manifest)

    def _write_snapshot_file(self, context, snapshot_path):
        if not os.path.isdir(os.path.dirname(snapshot_path)):
            os.makedirs(os.path.dirname(snapshot_path))
        file_type = _scene_file_type(context.get("original_scene_path", "") or self._current_scene_path())
        _quiet_scene_file_prompts_for_history()
        try:
            cmds.file(
                snapshot_path,
                force=True,
                options="v=0;",
                type=file_type,
                preserveReferences=True,
                exportAll=True,
                prompt=False,
            )
            return
        except Exception:
            pass
        original_scene_path = context.get("original_scene_path", "")
        current_scene_path = self._current_scene_path() or original_scene_path
        try:
            was_modified = bool(cmds.file(query=True, modified=True))
        except Exception:
            was_modified = False
        try:
            cmds.file(rename=snapshot_path)
            cmds.file(save=True, type=file_type, force=True, prompt=False)
        finally:
            if current_scene_path:
                try:
                    cmds.file(rename=current_scene_path)
                except Exception:
                    pass
            if was_modified:
                try:
                    cmds.file(modified=True)
                except Exception:
                    pass

    def create_auto_snapshot(self, reason, label=None, note=None):
        if not _auto_snapshot_enabled():
            return False, "Auto History is off.", None
        return self.create_snapshot(label=label or "Auto - {0}".format(reason or "Safety"), note=note or "", auto=True, reason=reason or "Safety")

    def restore_snapshot(self, snapshot_id, save_current_first=False):
        if not MAYA_AVAILABLE:
            return False, "History Timeline only works inside Maya."
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not restore History Timeline snapshot.")
        manifest = self._load_manifest(context)
        record = self._snapshot_for_id(manifest, snapshot_id)
        if not record:
            return False, "Pick a History Timeline snapshot to restore."
        snapshot_path = record.get("snapshot_path", "")
        if not snapshot_path or not os.path.exists(snapshot_path):
            return False, "Snapshot file is missing: {0}".format(snapshot_path)
        was_watching = self._action_timer is not None
        _suppress_auto_snapshots_for(6.0)
        self.stop_default_action_snapshots()
        self._auto_snapshot_busy = True
        try:
            _quiet_scene_file_prompts_for_history()
            cmds.file(snapshot_path, open=True, force=True, prompt=False)
            cmds.file(rename=record.get("original_scene_path") or context.get("original_scene_path"))
        except Exception as exc:
            self._auto_snapshot_busy = False
            if was_watching:
                self.start_default_action_snapshots()
            return False, "Could not restore snapshot: {0}".format(exc)
        self._auto_snapshot_busy = False
        context = self._context(prefer_meta=False)
        manifest = self._load_manifest(context)
        manifest["current_snapshot_id"] = snapshot_id
        manifest["active_branch_id"] = record.get("branch_id", manifest.get("active_branch_id", "main"))
        manifest.setdefault("events", []).append({"type": "restore", "snapshot_id": snapshot_id, "timestamp": _now_iso()})
        self._save_manifest(context, manifest)
        self._refresh_outliners_after_restore()
        self._mark_restore_baseline(record.get("scene_summary") or self._scene_summary(), settle_seconds=6.0)
        _suppress_auto_snapshots_for(6.0)
        _notify_history_ui_changed()
        if was_watching:
            self.start_default_action_snapshots()
        message = "Restored snapshot: {0}".format(record.get("label", snapshot_id))
        self._emit_status(message, True)
        return True, message

    def delete_all_snapshots(self, force=False):
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not delete History Timeline snapshots.")
        manifest = self._load_manifest(context)
        snapshots = list(manifest.get("snapshots") or [])
        if not force and any(item.get("locked") for item in snapshots):
            return False, "Some milestone snapshots are locked. Confirm delete all first."
        removed = 0
        for record in snapshots:
            snapshot_path = record.get("snapshot_path", "")
            if snapshot_path and os.path.exists(snapshot_path):
                try:
                    os.remove(snapshot_path)
                    removed += 1
                except Exception:
                    pass
        manifest["snapshots"] = []
        manifest["current_snapshot_id"] = ""
        manifest["active_branch_id"] = "main"
        manifest["branches"] = {"main": {"id": "main", "label": "Main", "color": BRANCH_COLOR_PALETTE[0], "parent_id": "", "index": 0}}
        manifest.setdefault("events", []).append({"type": "delete_all", "timestamp": _now_iso(), "count": len(snapshots)})
        self._save_manifest(context, manifest)
        self._mark_action_baseline()
        _notify_history_ui_changed()
        message = "Deleted all History Timeline snapshots: {0}.".format(removed)
        self._emit_status(message, True)
        return True, message

    def _refresh_outliners_after_restore(self):
        if not MAYA_AVAILABLE:
            return
        try:
            cmds.refresh(force=True)
        except Exception:
            pass
        try:
            outliner_panels = cmds.getPanel(type="outlinerPanel") or []
        except Exception:
            outliner_panels = []
        for panel_name in outliner_panels:
            try:
                editor = cmds.outlinerPanel(panel_name, query=True, outlinerEditor=True)
                if editor:
                    try:
                        cmds.outlinerEditor(editor, edit=True, refresh=True)
                    except Exception:
                        pass
                    try:
                        cmds.outlinerEditor(editor, edit=True, showDagOnly=True)
                    except Exception:
                        pass
            except Exception:
                pass

    def delete_snapshot(self, snapshot_id, force=False):
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not delete History Timeline snapshot.")
        manifest = self._load_manifest(context)
        record = self._snapshot_for_id(manifest, snapshot_id)
        if not record:
            return False, "Pick a History Timeline snapshot to delete."
        if record.get("locked") and not force:
            return False, "Milestone snapshots are locked. Unlock it before deleting."
        snapshot_path = record.get("snapshot_path", "")
        if snapshot_path and os.path.exists(snapshot_path):
            try:
                os.remove(snapshot_path)
            except Exception as exc:
                return False, "Could not delete snapshot file: {0}".format(exc)
        manifest["snapshots"] = [item for item in manifest.get("snapshots", []) if item.get("id") != snapshot_id]
        if manifest.get("current_snapshot_id") == snapshot_id:
            manifest["current_snapshot_id"] = manifest["snapshots"][-1]["id"] if manifest.get("snapshots") else ""
        manifest.setdefault("events", []).append({"type": "delete", "snapshot_id": snapshot_id, "timestamp": _now_iso()})
        self._save_manifest(context, manifest)
        self._mark_action_baseline()
        _notify_history_ui_changed()
        message = "Deleted snapshot: {0}".format(record.get("label", snapshot_id))
        self._emit_status(message, True)
        return True, message

    def rename_snapshot(self, snapshot_id, label):
        return self._edit_snapshot(snapshot_id, {"label": (label or "").strip() or "Snapshot"}, "Renamed snapshot.")

    def color_snapshot(self, snapshot_id, color):
        return self._edit_snapshot(snapshot_id, {"color": (color or "").strip() or DEFAULT_STEP_COLOR}, "Changed snapshot color.")

    def set_snapshot_milestone(self, snapshot_id, milestone=True):
        is_milestone = bool(milestone)
        changes = {"milestone": is_milestone, "locked": is_milestone}
        message = "Marked snapshot as milestone." if is_milestone else "Removed milestone mark."
        return self._edit_snapshot(snapshot_id, changes, message)

    def lock_snapshot(self, snapshot_id, locked=True):
        return self._edit_snapshot(snapshot_id, {"locked": bool(locked)}, "Updated milestone lock.")

    def update_note(self, snapshot_id, note):
        return self._edit_snapshot(snapshot_id, {"note": note or ""}, "Updated snapshot note.")

    def _edit_snapshot(self, snapshot_id, changes, message):
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not update History Timeline snapshot.")
        manifest = self._load_manifest(context)
        record = self._snapshot_for_id(manifest, snapshot_id)
        if not record:
            return False, "Pick a snapshot in the History list or click a History toolbar square first."
        record.update(changes)
        self._save_manifest(context, manifest)
        _notify_history_ui_changed()
        self._emit_status(message, True)
        return True, message

    def list_snapshots(self, branch_id=None):
        context = self._context()
        if not context.get("ok"):
            return []
        manifest = self._load_manifest(context)
        self._ensure_branch_records(manifest)
        snapshots = list(manifest.get("snapshots") or [])
        if branch_id and branch_id != "__all__":
            snapshots = [item for item in snapshots if (item.get("branch_id") or "main") == branch_id]
        enriched = []
        for item in snapshots:
            record = dict(item)
            branch = self._branch_record(manifest, record.get("branch_id") or "main")
            record["branch_label"] = branch.get("label") or _branch_display_name(record.get("branch_id") or "main")
            record["branch_color"] = branch.get("color") or record.get("branch_color") or _branch_color_from_id(record.get("branch_id") or "main")
            record["snapshot_size_bytes"] = _stored_snapshot_size(record)
            if record.get("branched_from_id") and not record.get("branched_from_label"):
                parent = self._snapshot_for_id(manifest, record.get("branched_from_id"))
                record["branched_from_label"] = parent.get("label", record.get("branched_from_id")) if parent else record.get("branched_from_id")
            enriched.append(record)
        return enriched

    def history_storage_size_bytes(self):
        context = self._context()
        if not context.get("ok"):
            return 0
        manifest = self._load_manifest(context)
        try:
            return int(manifest.get("history_storage_size_bytes"))
        except Exception:
            return _manifest_storage_size(manifest)

    def branch_choices(self):
        context = self._context()
        if not context.get("ok"):
            return [{"id": "main", "label": "Main", "color": BRANCH_COLOR_PALETTE[0], "active": True, "count": 0}]
        manifest = self._load_manifest(context)
        self._ensure_branch_records(manifest)
        active = manifest.get("active_branch_id", "main") or "main"
        snapshots = manifest.get("snapshots") or []
        branch_counts = {}
        for item in snapshots:
            branch_id = item.get("branch_id") or "main"
            branch_counts[branch_id] = branch_counts.get(branch_id, 0) + 1
        choices = []
        for branch_id, record in sorted((manifest.get("branches") or {}).items(), key=lambda item: (item[0] != "main", int(item[1].get("index") or 0), item[1].get("label", item[0]))):
            count = branch_counts.get(branch_id, 0)
            if branch_id != "main" and count == 0:
                continue
            choices.append(
                {
                    "id": branch_id,
                    "label": record.get("label") or _branch_display_name(branch_id),
                    "color": record.get("color") or _branch_color_from_id(branch_id),
                    "active": bool(branch_id == active),
                    "count": count,
                    "parent_id": record.get("parent_id", ""),
                }
            )
        return choices

    def active_branch_id(self):
        context = self._context()
        if not context.get("ok"):
            return "main"
        return self._load_manifest(context).get("active_branch_id", "main") or "main"

    def set_active_branch(self, branch_id):
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not switch History Timeline branch.")
        manifest = self._load_manifest(context)
        branch_id = branch_id or "main"
        if branch_id not in (manifest.get("branches") or {}):
            return False, "History branch not found: {0}".format(branch_id)
        manifest["active_branch_id"] = branch_id
        branch_snapshots = [item for item in manifest.get("snapshots", []) if (item.get("branch_id") or "main") == branch_id]
        if branch_snapshots:
            manifest["current_snapshot_id"] = branch_snapshots[-1].get("id", "")
        manifest.setdefault("events", []).append({"type": "branch_switch", "branch_id": branch_id, "timestamp": _now_iso()})
        self._save_manifest(context, manifest)
        _notify_history_ui_changed()
        return True, "Switched History Timeline branch to {0}.".format(self._branch_record(manifest, branch_id).get("label", branch_id))

    def rename_branch(self, branch_id, label):
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not rename History Timeline branch.")
        manifest = self._load_manifest(context)
        branch_id = branch_id or "main"
        branch = self._branch_record(manifest, branch_id)
        clean_label = (label or "").strip()
        if not clean_label:
            return False, "Type a branch name first."
        branch["label"] = clean_label
        for record in manifest.get("snapshots") or []:
            if (record.get("branch_id") or "main") == branch_id:
                record["branch_label"] = clean_label
        manifest.setdefault("events", []).append({"type": "branch_rename", "branch_id": branch_id, "timestamp": _now_iso()})
        self._save_manifest(context, manifest)
        _notify_history_ui_changed()
        message = "Renamed History Timeline branch to {0}.".format(clean_label)
        self._emit_status(message, True)
        return True, message

    def restore_latest_in_branch(self, branch_id):
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not restore History Timeline branch.")
        manifest = self._load_manifest(context)
        branch_id = branch_id or "main"
        branch_snapshots = [item for item in manifest.get("snapshots", []) if (item.get("branch_id") or "main") == branch_id]
        if not branch_snapshots:
            success, message = self.set_active_branch(branch_id)
            return success, message
        return self.restore_snapshot(branch_snapshots[-1].get("id"), save_current_first=False)

    def snapshot_cap(self):
        context = self._context()
        if not context.get("ok"):
            return DEFAULT_SNAPSHOT_CAP
        manifest = self._load_manifest(context)
        return int(manifest.get("snapshot_cap", DEFAULT_SNAPSHOT_CAP))

    def set_snapshot_cap(self, cap):
        context = self._context()
        if not context.get("ok"):
            return False, context.get("message", "Could not set History Timeline snapshot cap.")
        manifest = self._load_manifest(context)
        try:
            cap = int(cap)
        except Exception:
            cap = DEFAULT_SNAPSHOT_CAP
        manifest["snapshot_cap"] = max(0, cap)
        self._apply_snapshot_cap(context, manifest)
        _notify_history_ui_changed()
        message = "History Timeline snapshot cap set to {0}. Milestones are preserved.".format(manifest["snapshot_cap"])
        self._emit_status(message, True)
        return True, message

    def current_snapshot_id(self):
        context = self._context()
        if not context.get("ok"):
            return ""
        return self._load_manifest(context).get("current_snapshot_id", "")

    def history_folder(self):
        context = self._context()
        if not context.get("ok"):
            return ""
        return context.get("history_root", "")

    def open_history_folder(self):
        folder = self.history_folder()
        if not folder:
            return False, "Save the Maya scene first, then History Timeline can open its folder."
        if not os.path.isdir(folder):
            os.makedirs(folder)
        try:
            os.startfile(folder)
        except Exception as exc:
            return False, "Could not open history folder: {0}".format(exc)
        return True, "Opened History Timeline folder."


def snapshots_has_future(manifest, snapshot_id, branch_id=None):
    snapshots = manifest.get("snapshots") or []
    if not snapshot_id:
        return False
    if branch_id:
        snapshots = [item for item in snapshots if (item.get("branch_id") or "main") == branch_id]
    for index, item in enumerate(snapshots):
        if item.get("id") == snapshot_id:
            return index < len(snapshots) - 1
    return False


if QtWidgets:
    class HistoryTimelineStrip(QtWidgets.QFrame):
        def __init__(self, controller=None, status_callback=None, parent=None, max_markers=12, marker_click_callback=None):
            super(HistoryTimelineStrip, self).__init__(parent)
            self.controller = controller or MayaHistoryTimelineController(status_callback=status_callback)
            self.status_callback = status_callback
            self.marker_click_callback = marker_click_callback
            self.max_markers = min(MAX_HISTORY_STRIP_MARKERS, int(max_markers or 12))
            self.setObjectName("toolkitBarHistoryTimelineStrip")
            self.setMinimumHeight(18)
            self.setMaximumHeight(22)
            if hasattr(self, "setSizePolicy"):
                self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self._build_ui()
            _register_history_widget(self)
            self.refresh()

        def _build_ui(self):
            self.setStyleSheet(
                """
                QFrame#toolkitBarHistoryTimelineStrip {
                    background-color: #191919;
                    border: 1px solid #363636;
                    border-radius: 4px;
                }
                QToolButton#toolkitBarHistorySaveStep {
                    background-color: #252525;
                    color: #F2F2F2;
                    border: 1px solid #4CC9F0;
                    border-radius: 0px;
                    padding: 0px 4px;
                    font-weight: 700;
                    font-size: 9px;
                }
                QToolButton#toolkitBarHistoryAutoToggle {
                    background-color: #3A2525;
                    color: #FFD6D6;
                    border: 1px solid #F76E6E;
                    border-radius: 0px;
                    padding: 0px 4px;
                    font-weight: 700;
                    font-size: 9px;
                }
                QToolButton#toolkitBarHistoryAutoToggle:checked {
                    background-color: #1F3540;
                    color: #BDEBFF;
                    border: 1px solid #4CC9F0;
                }
                QLabel#toolkitBarHistoryStatusPill {
                    background-color: #26323A;
                    color: #BDEBFF;
                    border: 1px solid #4CC9F0;
                    border-radius: 0px;
                    padding: 1px 6px;
                    font-size: 8px;
                    font-weight: 700;
                }
                QToolButton#toolkitBarHistoryMarker {
                    border: 1px solid #2A2A2A;
                    border-radius: 2px;
                    min-width: 7px;
                    max-width: 9px;
                    min-height: 10px;
                    max-height: 12px;
                }
                """
            )
            self.layout = QtWidgets.QHBoxLayout(self)
            self.layout.setContentsMargins(4, 2, 4, 2)
            self.layout.setSpacing(2)
            self.auto_toggle = QtWidgets.QToolButton()
            self.auto_toggle.setObjectName("toolkitBarHistoryAutoToggle")
            self.auto_toggle.setText("Auto")
            self.auto_toggle.setCheckable(True)
            self.auto_toggle.setToolTip("Toggle automatic History snapshots. Off stops the background watcher completely; H+ still saves manually.")
            self.auto_toggle.setMinimumSize(34, 16)
            self.auto_toggle.setMaximumSize(42, 18)
            self.auto_toggle.clicked.connect(self._toggle_auto_history)
            self.layout.addWidget(self.auto_toggle)
            self.save_button = QtWidgets.QToolButton()
            self.save_button.setObjectName("toolkitBarHistorySaveStep")
            self.save_button.setText("H+")
            self.save_button.setToolTip("History Timeline: save a new step snapshot beside the Maya scene.")
            self.save_button.setMinimumSize(24, 16)
            self.save_button.setMaximumSize(30, 18)
            self.save_button.clicked.connect(self._save_step)
            self.layout.addWidget(self.save_button)
            self.status_pill = QtWidgets.QLabel()
            self.status_pill.setObjectName("toolkitBarHistoryStatusPill")
            self.status_pill.setText("History ready")
            self.status_pill.setToolTip("History Timeline is ready.")
            self.status_pill.setMinimumHeight(14)
            self.status_pill.setMaximumHeight(18)
            self.status_pill.setMinimumWidth(78)
            self.status_pill.setMaximumWidth(122)
            self.status_pill.setAlignment(QtCore.Qt.AlignCenter)
            self.layout.addWidget(self.status_pill)
            self.marker_layout = QtWidgets.QHBoxLayout()
            self.marker_layout.setContentsMargins(0, 0, 0, 0)
            self.marker_layout.setSpacing(1)
            self.layout.addLayout(self.marker_layout)

        def _set_status(self, message, success=True):
            if "save" in (message or "").lower() and "scene" in (message or "").lower():
                self._set_status_pill("Save scene required", "warning", message)
            elif "auto history is off" in (message or "").lower():
                self._set_status_pill("Auto off", "off", message)
            elif success:
                self._set_status_pill("History active", "active", message)
            elif message:
                self._set_status_pill("History warning", "warning", message)
            if self.status_callback:
                self.status_callback(message, success)

        def _set_status_pill(self, text, state="active", tooltip=""):
            if not getattr(self, "status_pill", None):
                return
            styles = {
                "warning": ("#3B2E1E", "#FFD88A", "#F6C85F"),
                "active": ("#26323A", "#BDEBFF", "#4CC9F0"),
                "ready": ("#243326", "#C8F7D0", "#7BD88F"),
                "off": ("#332326", "#FFD6D6", "#F76E6E"),
            }
            background, foreground, border = styles.get(state, styles["active"])
            self.status_pill.setText(text)
            self.status_pill.setToolTip(tooltip or text)
            self.status_pill.setStyleSheet(
                "QLabel#toolkitBarHistoryStatusPill {{ background-color: {0}; color: {1}; border: 1px solid {2}; border-radius: 0px; padding: 1px 6px; font-size: 8px; font-weight: 700; }}".format(
                    background,
                    foreground,
                    border,
                )
            )

        def _save_step(self):
            success, message, _record = self.controller.create_snapshot(label="Step")
            self._set_status(message, success)
            self.refresh()

        def _toggle_auto_history(self, checked):
            if checked:
                _show_auto_history_security_warning(self)
            success, message = self.controller.set_auto_snapshot_enabled(bool(checked), parent=self, interval_ms=2000)
            self._set_status(message, success)
            self.refresh()

        def _restore_marker(self, snapshot_id):
            if self.marker_click_callback:
                handled = self.marker_click_callback(snapshot_id)
                if handled is not False:
                    self.refresh()
                    return
            success, message = self.controller.restore_snapshot(snapshot_id, save_current_first=False)
            self._set_status(message, success)
            self.refresh()

        def _visible_snapshots(self, snapshots, current_id):
            if len(snapshots) <= self.max_markers or not current_id:
                return snapshots[-self.max_markers:]
            current_index = -1
            for index, record in enumerate(snapshots):
                if record.get("id") == current_id:
                    current_index = index
                    break
            if current_index < 0:
                return snapshots[-self.max_markers:]
            half = max(1, self.max_markers // 2)
            start = max(0, current_index - half)
            end = start + self.max_markers
            if end > len(snapshots):
                end = len(snapshots)
                start = max(0, end - self.max_markers)
            return snapshots[start:end]

        def refresh(self):
            while self.marker_layout.count():
                item = self.marker_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
            context = self.controller._context()
            auto_enabled = self.controller.auto_snapshot_enabled()
            if getattr(self, "auto_toggle", None):
                self.auto_toggle.blockSignals(True)
                self.auto_toggle.setChecked(bool(auto_enabled))
                self.auto_toggle.blockSignals(False)
            if not context.get("ok"):
                message = context.get("message", "Save the Maya scene first.")
                self._set_status_pill(
                    "Save scene required",
                    "warning",
                    "{0}\nHistory snapshots are stored beside the saved Maya scene.".format(message),
                )
                self.marker_layout.addStretch(1)
                return
            snapshots = self.controller.list_snapshots()
            current_id = self.controller.current_snapshot_id()
            if not auto_enabled:
                self._set_status_pill(
                    "Auto off",
                    "off",
                    "Auto History is off. H+ and Save Step still create manual snapshots.",
                )
            elif snapshots:
                self._set_status_pill(
                    "History active",
                    "active",
                    "History Timeline is saving snapshots beside this Maya scene.",
                )
            else:
                self._set_status_pill(
                    "History ready",
                    "ready",
                    "History Timeline is ready. Click H+ or make an enabled action to save a snapshot.",
                )
            for record in self._visible_snapshots(snapshots, current_id):
                color = record.get("color") or DEFAULT_STEP_COLOR
                button = QtWidgets.QToolButton()
                button.setObjectName("toolkitBarHistoryMarker")
                button.setText("")
                button.setToolTip(
                    "Label: {0}\nBranch: {1}\nFrame: {2}\nDate: {3}\nNote: {4}".format(
                        record.get("label", "Snapshot"),
                        record.get("branch_label") or _branch_display_name(record.get("branch_id") or "main"),
                        int(round(float(record.get("frame", 0.0)))),
                        record.get("timestamp", ""),
                        record.get("note", ""),
                    )
                )
                border = "#FFFFFF" if record.get("id") == current_id else "#2A2A2A"
                button.setStyleSheet(
                    "QToolButton#toolkitBarHistoryMarker {{ background-color: {0}; border: 2px solid {1}; border-radius: 2px; }}".format(
                        color,
                        border,
                    )
                )
                button.clicked.connect(lambda _checked=False, snapshot_id=record.get("id"): self._restore_marker(snapshot_id))
                self.marker_layout.addWidget(button)
            self.marker_layout.addStretch(1)


    class MayaHistoryTimelinePanel(QtWidgets.QFrame):
        def __init__(self, controller=None, status_callback=None, parent=None):
            super(MayaHistoryTimelinePanel, self).__init__(parent)
            self.controller = controller or MayaHistoryTimelineController(status_callback=status_callback)
            self.status_callback = status_callback
            self._selected_snapshot_id = ""
            self._refreshing_table = False
            self._last_context_scene_path = ""
            self._visible_snapshot_count = 0
            self._total_snapshot_count = 0
            self.setObjectName("mayaHistoryTimelinePanel")
            if hasattr(self, "setMinimumWidth"):
                self.setMinimumWidth(0)
            self._build_ui()
            _register_history_widget(self)
            self.refresh()

        def _build_ui(self):
            self.setStyleSheet(
                """
                QFrame#mayaHistoryTimelinePanel {
                    background-color: #2B2B2B;
                    color: #E8E8E8;
                }
                QTableWidget {
                    background-color: #202020;
                    color: #EFEFEF;
                    gridline-color: #3C3C3C;
                    selection-background-color: #335C67;
                }
                QPushButton {
                    background-color: #3A3A3A;
                    color: #F2F2F2;
                    border: 1px solid #555555;
                    border-radius: 5px;
                    padding: 5px 8px;
                }
                QPushButton:hover { background-color: #454545; }
                QLineEdit, QPlainTextEdit {
                    background-color: #1E1E1E;
                    color: #F2F2F2;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 4px;
                }
                QCheckBox {
                    color: #E8E8E8;
                    spacing: 5px;
                }
                """
            )
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)

            intro = QtWidgets.QLabel(
                "Save scene snapshots you can return to when Maya undo is not enough. Restore the whole scene, branch from older work, and keep snapshots under control with custom auto-save rules."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

            self.strip = HistoryTimelineStrip(
                self.controller,
                self._set_status,
                parent=self,
                max_markers=24,
                marker_click_callback=self._restore_from_marker,
            )
            layout.addWidget(self.strip)

            branch_row = QtWidgets.QGridLayout()
            self.branch_combo = QtWidgets.QComboBox()
            self.branch_combo.setObjectName("historyTimelineBranchCombo")
            self.branch_combo.setToolTip("Pick which History Timeline branch to inspect.")
            self.switch_branch_button = QtWidgets.QPushButton("Switch Branch")
            self.switch_branch_button.setObjectName("historyTimelineSwitchBranchButton")
            self.switch_branch_button.setToolTip("Open the latest snapshot from the chosen branch.")
            self.branch_name_field = QtWidgets.QLineEdit()
            self.branch_name_field.setObjectName("historyTimelineBranchNameField")
            self.branch_name_field.setPlaceholderText("Branch name")
            self.rename_branch_button = QtWidgets.QPushButton("Rename Branch")
            self.rename_branch_button.setObjectName("historyTimelineRenameBranchButton")
            self.branch_help_label = QtWidgets.QLabel("If you restore an older snapshot and keep working, Aminate creates a new colored branch.")
            self.branch_help_label.setWordWrap(True)
            branch_row.addWidget(QtWidgets.QLabel("Branch"), 0, 0)
            branch_row.addWidget(self.branch_combo, 0, 1)
            branch_row.addWidget(self.switch_branch_button, 0, 2)
            branch_row.addWidget(self.branch_name_field, 1, 1)
            branch_row.addWidget(self.rename_branch_button, 1, 2)
            branch_row.addWidget(self.branch_help_label, 2, 0, 1, 3)
            branch_row.setColumnStretch(1, 1)
            layout.addLayout(branch_row)

            form = QtWidgets.QGridLayout()
            self.label_field = QtWidgets.QLineEdit()
            self.label_field.setObjectName("historyTimelineSnapshotLabelField")
            self.label_field.setPlaceholderText("Snapshot label, e.g. good blocking")
            self.color_field = QtWidgets.QLineEdit()
            self.color_field.setObjectName("historyTimelineSnapshotColorField")
            self.color_field.setPlaceholderText("Optional color, blank = branch color")
            self.pick_color_button = QtWidgets.QPushButton("Pick Color")
            self.pick_color_button.setObjectName("historyTimelinePickSnapshotColorButton")
            self.pick_color_button.setToolTip("Open a color picker. If a snapshot is selected, the picked color is applied to that snapshot.")
            self.note_field = QtWidgets.QLineEdit()
            self.note_field.setObjectName("historyTimelineSnapshotNoteField")
            self.note_field.setPlaceholderText("Note, e.g. before polish")
            form.addWidget(QtWidgets.QLabel("Label"), 0, 0)
            form.addWidget(self.label_field, 0, 1)
            form.addWidget(QtWidgets.QLabel("Color"), 0, 2)
            form.addWidget(self.color_field, 0, 3)
            form.addWidget(self.pick_color_button, 0, 4)
            form.addWidget(QtWidgets.QLabel("Note"), 1, 0)
            form.addWidget(self.note_field, 1, 1, 1, 4)
            form.setColumnStretch(1, 2)
            form.setColumnStretch(3, 1)
            layout.addLayout(form)

            settings_row = QtWidgets.QGridLayout()
            self.snapshot_cap_spin = QtWidgets.QSpinBox()
            self.snapshot_cap_spin.setObjectName("historyTimelineSnapshotCapSpin")
            self.snapshot_cap_spin.setRange(0, 1000)
            self.snapshot_cap_spin.setToolTip("Maximum snapshots to keep for this Maya scene. 0 means no cap. Milestones are preserved.")
            self.snapshot_cap_spin.setValue(DEFAULT_SNAPSHOT_CAP)
            self.apply_cap_button = QtWidgets.QPushButton("Set Snapshot Cap")
            self.apply_cap_button.setObjectName("historyTimelineSetSnapshotCapButton")
            self.storage_size_label = QtWidgets.QLabel("History size 0 B")
            self.storage_size_label.setObjectName("historyTimelineStorageSizeLabel")
            self.storage_size_label.setToolTip("Total disk size of all saved History Timeline scene snapshots for this Maya scene.")
            self.warning_label = QtWidgets.QLabel(
                "Warning: every snapshot is a full Maya scene copy. Large scenes make large history folders. Set a cap to keep file size under control."
            )
            self.warning_label.setWordWrap(True)
            settings_row.addWidget(QtWidgets.QLabel("Max snapshots"), 0, 0)
            settings_row.addWidget(self.snapshot_cap_spin, 0, 1)
            settings_row.addWidget(self.apply_cap_button, 0, 2)
            settings_row.addWidget(self.storage_size_label, 0, 3)
            settings_row.addWidget(self.warning_label, 1, 0, 1, 4)
            settings_row.setColumnStretch(3, 1)
            layout.addLayout(settings_row)

            auto_box = QtWidgets.QGroupBox("Auto History Save Rules")
            auto_box.setObjectName("historyTimelineAutoRulesBox")
            auto_layout = QtWidgets.QVBoxLayout(auto_box)
            self.auto_enabled_checkbox = QtWidgets.QCheckBox("Enable automatic History snapshots")
            self.auto_enabled_checkbox.setObjectName("historyTimelineAutoEnabledCheckBox")
            self.auto_enabled_checkbox.setToolTip("Turn this off to stop the History background watcher completely. Manual Save Step and Save Milestone still work.")
            auto_layout.addWidget(self.auto_enabled_checkbox)
            self.auto_full_checkbox = QtWidgets.QCheckBox("Save snapshot after every Maya action")
            self.auto_full_checkbox.setObjectName("historyTimelineAutoAllCheckBox")
            self.auto_full_checkbox.setToolTip("Default mode. Aminate saves a full scene snapshot after each Maya action when the scene has been saved.")
            auto_layout.addWidget(self.auto_full_checkbox)
            self.auto_rules_help_label = QtWidgets.QLabel(
                "Turn this off for custom rules, then tick only the events that should create snapshots. Full snapshots can use a lot of disk space on large scenes."
            )
            self.auto_rules_help_label.setObjectName("historyTimelineAutoRulesHelpLabel")
            self.auto_rules_help_label.setWordWrap(True)
            auto_layout.addWidget(self.auto_rules_help_label)
            trigger_row = QtWidgets.QGridLayout()
            self.auto_trigger_checkboxes = {}
            trigger_object_names = {
                "keyframes": "historyTimelineTriggerKeyframesCheckBox",
                "constraints": "historyTimelineTriggerConstraintsCheckBox",
                "nodes": "historyTimelineTriggerNodesCheckBox",
                "animation_layers": "historyTimelineTriggerAnimationLayersCheckBox",
                "parenting": "historyTimelineTriggerParentingCheckBox",
                "references": "historyTimelineTriggerReferencesCheckBox",
                "transforms": "historyTimelineTriggerTransformsCheckBox",
                "materials": "historyTimelineTriggerMaterialsCheckBox",
            }
            for index, (trigger_id, trigger_label) in enumerate(AUTO_SNAPSHOT_TRIGGER_LABELS):
                checkbox = QtWidgets.QCheckBox(trigger_label)
                checkbox.setObjectName(trigger_object_names.get(trigger_id, "historyTimelineTriggerCheckBox"))
                checkbox.setToolTip("Custom Auto History trigger: {0}.".format(trigger_label))
                self.auto_trigger_checkboxes[trigger_id] = checkbox
                trigger_row.addWidget(checkbox, index // 2, index % 2)
            trigger_row.setColumnStretch(0, 1)
            trigger_row.setColumnStretch(1, 1)
            auto_layout.addLayout(trigger_row)
            auto_button_row = QtWidgets.QHBoxLayout()
            self.apply_auto_rules_button = QtWidgets.QPushButton("Save Auto Rules")
            self.apply_auto_rules_button.setObjectName("historyTimelineApplyAutoRulesButton")
            self.apply_auto_rules_button.setToolTip("Save the full-save or custom Auto History trigger settings into this Maya scene history manifest.")
            auto_button_row.addWidget(self.apply_auto_rules_button)
            auto_button_row.addStretch(1)
            auto_layout.addLayout(auto_button_row)
            layout.addWidget(auto_box)

            button_row = QtWidgets.QGridLayout()
            self.save_step_button = QtWidgets.QPushButton("Save Step")
            self.save_milestone_button = QtWidgets.QPushButton("Save Milestone")
            self.restore_button = QtWidgets.QPushButton("Jump to Selected Snapshot")
            self.rename_button = QtWidgets.QPushButton("Rename Selected")
            self.color_button = QtWidgets.QPushButton("Apply Color")
            self.toggle_milestone_button = QtWidgets.QPushButton("Mark Milestone")
            self.toggle_milestone_button.setObjectName("historyTimelineToggleMilestoneButton")
            self.toggle_milestone_button.setToolTip("Mark the selected snapshot as a protected milestone, or remove the milestone mark.")
            self.delete_button = QtWidgets.QPushButton("Delete Selected")
            self.delete_all_button = QtWidgets.QPushButton("Delete All Snapshots")
            self.delete_all_button.setObjectName("historyTimelineDeleteAllSnapshotsButton")
            self.open_folder_button = QtWidgets.QPushButton("Open History Folder")
            buttons = (
                self.save_step_button,
                self.save_milestone_button,
                self.restore_button,
                self.rename_button,
                self.color_button,
                self.toggle_milestone_button,
                self.delete_button,
                self.delete_all_button,
                self.open_folder_button,
            )
            for index, button in enumerate(buttons):
                button_row.addWidget(button, index // 5, index % 5)
                button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            layout.addLayout(button_row)

            self.table = QtWidgets.QTableWidget(0, 9)
            self.table.setObjectName("historyTimelineSnapshotTable")
            self.table.setHorizontalHeaderLabels(["Color", "Label", "Kind", "Frame", "Branch", "From", "Size", "Date", "Note"])
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            try:
                self.table.setHorizontalScrollBarPolicy(_qt_flag("ScrollBarPolicy", "ScrollBarAsNeeded", QtCore.Qt.ScrollBarAsNeeded))
                header = self.table.horizontalHeader()
                header.setSectionsMovable(False)
                header.setStretchLastSection(False)
                header.setMinimumSectionSize(36)
                header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
                for index, width in enumerate((64, 180, 88, 64, 130, 120, 82, 150, 260)):
                    self.table.setColumnWidth(index, width)
            except Exception:
                try:
                    self.table.horizontalHeader().setStretchLastSection(True)
                except Exception:
                    pass
            layout.addWidget(self.table, 1)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)

            self.save_step_button.clicked.connect(self._save_step)
            self.save_milestone_button.clicked.connect(self._save_milestone)
            self.restore_button.clicked.connect(self._restore)
            self.rename_button.clicked.connect(self._rename)
            self.color_button.clicked.connect(self._color)
            self.pick_color_button.clicked.connect(self._pick_color)
            self.toggle_milestone_button.clicked.connect(self._toggle_milestone)
            self.delete_button.clicked.connect(self._delete)
            self.delete_all_button.clicked.connect(self._delete_all)
            self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
            self.table.itemDoubleClicked.connect(lambda _item: self._restore())
            self.apply_cap_button.clicked.connect(self._apply_cap)
            self.open_folder_button.clicked.connect(self._open_folder)
            self.branch_combo.currentIndexChanged.connect(self._branch_filter_changed)
            self.switch_branch_button.clicked.connect(self._switch_branch)
            self.rename_branch_button.clicked.connect(self._rename_branch)
            self.auto_enabled_checkbox.toggled.connect(self._auto_enabled_toggled)
            self.auto_full_checkbox.toggled.connect(self._auto_full_toggled)
            self.apply_auto_rules_button.clicked.connect(self._apply_auto_snapshot_rules)

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            if self.status_callback:
                self.status_callback(message, success)

        def selected_snapshot_id(self):
            row = self.table.currentRow()
            if row < 0:
                return self._selected_snapshot_id or self.controller.current_snapshot_id()
            item = self.table.item(row, 1) or self.table.item(row, 0)
            if not item:
                return self._selected_snapshot_id or self.controller.current_snapshot_id()
            role = _qt_flag("ItemDataRole", "UserRole", 32)
            return item.data(role) or self._selected_snapshot_id or self.controller.current_snapshot_id()

        def _record_for_id(self, snapshot_id):
            if not snapshot_id:
                return None
            for record in self.controller.list_snapshots(branch_id="__all__"):
                if record.get("id") == snapshot_id:
                    return record
            return None

        def _select_snapshot_row(self, snapshot_id):
            if not snapshot_id:
                return False
            role = _qt_flag("ItemDataRole", "UserRole", 32)
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 1) or self.table.item(row, 0)
                if item and item.data(role) == snapshot_id:
                    self._refreshing_table = True
                    try:
                        self.table.selectRow(row)
                        self.table.setCurrentCell(row, 1)
                        self.table.scrollToItem(item)
                    finally:
                        self._refreshing_table = False
                    self._selected_snapshot_id = snapshot_id
                    self._update_selected_snapshot_fields(snapshot_id)
                    return True
            return False

        def _update_selected_snapshot_fields(self, snapshot_id):
            record = self._record_for_id(snapshot_id)
            if not record:
                self.toggle_milestone_button.setText("Mark Milestone")
                return
            self.label_field.setText(record.get("label", ""))
            self.color_field.setText(record.get("color", "") or "")
            self.note_field.setText(record.get("note", "") or "")
            if record.get("milestone"):
                self.toggle_milestone_button.setText("Remove Milestone")
            else:
                self.toggle_milestone_button.setText("Mark Milestone")

        def _on_table_selection_changed(self):
            if self._refreshing_table:
                return
            snapshot_id = self.selected_snapshot_id()
            if snapshot_id:
                self._selected_snapshot_id = snapshot_id
                self._update_selected_snapshot_fields(snapshot_id)
                self._set_status("Selected snapshot. Use Jump, Rename, Pick Color, or Mark Milestone.", True)

        def _on_scene_context_changed(self):
            self._selected_snapshot_id = ""
            self._last_context_scene_path = ""
            self.refresh()

        def refresh(self):
            context = self.controller._context()
            context_message = "" if context.get("ok") else context.get("message", "Save the Maya scene first.")
            context_scene_path = context.get("original_scene_path", "") if context.get("ok") else ""
            if context_scene_path != self._last_context_scene_path:
                self._selected_snapshot_id = ""
                self._last_context_scene_path = context_scene_path
            self._refresh_branch_combo()
            branch_id = self._selected_branch_filter()
            all_snapshots = self.controller.list_snapshots(branch_id=branch_id)
            current_id = self.controller.current_snapshot_id()
            previous_selected_id = self._selected_snapshot_id or current_id
            snapshots = _compact_snapshot_records(all_snapshots, MAX_HISTORY_TABLE_ROWS, previous_selected_id)
            self._visible_snapshot_count = len(snapshots)
            self._total_snapshot_count = len(all_snapshots)
            try:
                self.snapshot_cap_spin.blockSignals(True)
                self.snapshot_cap_spin.setValue(int(self.controller.snapshot_cap()))
                self.snapshot_cap_spin.blockSignals(False)
            except Exception:
                pass
            try:
                self.storage_size_label.setText("History size {0}".format(_format_bytes(self.controller.history_storage_size_bytes())))
            except Exception:
                pass
            if context_message:
                self.status_label.setText(context_message)
            elif self._total_snapshot_count > self._visible_snapshot_count:
                self.status_label.setText(
                    "Showing {0} of {1} snapshots. Latest snapshots stay visible; selected older snapshot stays pinned.".format(
                        self._visible_snapshot_count,
                        self._total_snapshot_count,
                    )
                )
            self._refresh_auto_snapshot_controls()
            self._refreshing_table = True
            self.table.setRowCount(len(snapshots))
            for row, record in enumerate(snapshots):
                kind = "Milestone" if record.get("milestone") else ("Auto" if record.get("auto") else "Step")
                values = [
                    record.get("color", ""),
                    record.get("label", ""),
                    kind,
                    str(int(round(float(record.get("frame", 0.0))))),
                    record.get("branch_label") or _branch_display_name(record.get("branch_id") or "main"),
                    record.get("branched_from_label") or record.get("branched_from_id") or "",
                    _format_bytes(record.get("snapshot_size_bytes", 0)),
                    record.get("timestamp", ""),
                    record.get("note", ""),
                ]
                role = _qt_flag("ItemDataRole", "UserRole", 32)
                tooltip = (
                    "Label: {0}\nKind: {1}\nFrame: {2}\nBranch: {3}\nFrom: {4}\nSize: {5}\nDate: {6}\nNote: {7}".format(
                        values[1],
                        values[2],
                        values[3],
                        values[4],
                        values[5],
                        values[6],
                        values[7],
                        values[8],
                    )
                )
                for col, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(value)
                    item.setData(role, record.get("id", ""))
                    item.setToolTip(tooltip)
                    if col == 0:
                        item.setBackground(QtGui.QColor(record.get("color") or DEFAULT_STEP_COLOR))
                    if col == 4:
                        item.setBackground(QtGui.QColor(record.get("branch_color") or _branch_color_from_id(record.get("branch_id") or "main")))
                    self.table.setItem(row, col, item)
            self._refreshing_table = False
            visible_ids = [record.get("id") for record in snapshots]
            target_id = previous_selected_id if previous_selected_id in visible_ids else (current_id if current_id in visible_ids else "")
            if target_id:
                self._select_snapshot_row(target_id)
            elif snapshots:
                self._select_snapshot_row(snapshots[-1].get("id", ""))
            else:
                self._selected_snapshot_id = ""
                self.table.clearSelection()
                self.toggle_milestone_button.setText("Mark Milestone")
            self.strip.refresh()

        def _refresh_auto_snapshot_controls(self):
            settings = self.controller.auto_snapshot_settings()
            enabled = self.controller.auto_snapshot_enabled()
            is_full = settings.get("mode") == AUTO_SNAPSHOT_MODE_ALL
            try:
                self.auto_enabled_checkbox.blockSignals(True)
                self.auto_enabled_checkbox.setChecked(bool(enabled))
                self.auto_enabled_checkbox.blockSignals(False)
                self.auto_full_checkbox.blockSignals(True)
                self.auto_full_checkbox.setChecked(is_full)
                self.auto_full_checkbox.setEnabled(bool(enabled))
                self.auto_full_checkbox.blockSignals(False)
            except Exception:
                pass
            triggers = settings.get("triggers") or {}
            for trigger_id, checkbox in self.auto_trigger_checkboxes.items():
                try:
                    checkbox.blockSignals(True)
                    checkbox.setChecked(bool(triggers.get(trigger_id, DEFAULT_AUTO_SNAPSHOT_TRIGGERS.get(trigger_id, True))))
                    checkbox.setEnabled(bool(enabled) and not is_full)
                    checkbox.blockSignals(False)
                except Exception:
                    pass
            try:
                self.apply_auto_rules_button.setEnabled(bool(enabled))
            except Exception:
                pass

        def _auto_full_toggled(self, checked):
            for checkbox in self.auto_trigger_checkboxes.values():
                checkbox.setEnabled(self.controller.auto_snapshot_enabled() and not checked)

        def _auto_enabled_toggled(self, checked):
            if checked:
                _show_auto_history_security_warning(self)
            success, message = self.controller.set_auto_snapshot_enabled(bool(checked), parent=self, interval_ms=2000)
            self._set_status(message, success)
            self._refresh_auto_snapshot_controls()
            try:
                self.strip.refresh()
            except Exception:
                pass

        def _apply_auto_snapshot_rules(self):
            mode = AUTO_SNAPSHOT_MODE_ALL if self.auto_full_checkbox.isChecked() else AUTO_SNAPSHOT_MODE_CUSTOM
            triggers = {trigger_id: checkbox.isChecked() for trigger_id, checkbox in self.auto_trigger_checkboxes.items()}
            success, message = self.controller.set_auto_snapshot_settings(mode=mode, triggers=triggers)
            self._set_status(message, success)
            self.refresh()

        def _refresh_branch_combo(self):
            if not getattr(self, "branch_combo", None):
                return
            current_data = self.branch_combo.currentData() if self.branch_combo.count() else None
            active_branch = self.controller.active_branch_id()
            target = current_data if current_data is not None else "__all__"
            self.branch_combo.blockSignals(True)
            try:
                self.branch_combo.clear()
                self.branch_combo.addItem("All Branches", "__all__")
                for branch in self.controller.branch_choices():
                    label = "{0} ({1})".format(branch.get("label") or branch.get("id"), branch.get("count", 0))
                    self.branch_combo.addItem(label, branch.get("id"))
                for index in range(self.branch_combo.count()):
                    if self.branch_combo.itemData(index) == target:
                        self.branch_combo.setCurrentIndex(index)
                        break
                else:
                    for index in range(self.branch_combo.count()):
                        if self.branch_combo.itemData(index) == active_branch:
                            self.branch_combo.setCurrentIndex(index)
                            break
            finally:
                self.branch_combo.blockSignals(False)
            self._refresh_branch_name_field()

        def _refresh_branch_name_field(self):
            branch_id = self._selected_branch_filter()
            if not getattr(self, "branch_name_field", None):
                return
            branch_label = ""
            if branch_id and branch_id != "__all__":
                for branch in self.controller.branch_choices():
                    if branch.get("id") == branch_id:
                        branch_label = branch.get("label", "")
                        break
            self.branch_name_field.setEnabled(bool(branch_id and branch_id != "__all__"))
            self.rename_branch_button.setEnabled(bool(branch_id and branch_id != "__all__"))
            self.branch_name_field.setText(branch_label)

        def _selected_branch_filter(self):
            if not getattr(self, "branch_combo", None) or self.branch_combo.currentIndex() < 0:
                return self.controller.active_branch_id()
            return self.branch_combo.currentData()

        def _branch_filter_changed(self, *_args):
            self._refresh_branch_name_field()
            self.refresh()

        def _switch_branch(self):
            branch_id = self._selected_branch_filter()
            if not branch_id or branch_id == "__all__":
                self._set_status("Pick a single branch before switching.", False)
                return
            success, message = self.controller.restore_latest_in_branch(branch_id)
            self._set_status(message, success)
            self.refresh()

        def _rename_branch(self):
            branch_id = self._selected_branch_filter()
            if not branch_id or branch_id == "__all__":
                self._set_status("Pick a single branch before renaming.", False)
                return
            success, message = self.controller.rename_branch(branch_id, self.branch_name_field.text())
            self._set_status(message, success)
            self.refresh()

        def _save_step(self):
            success, message, record = self.controller.create_snapshot(
                label=self.label_field.text(),
                color=self.color_field.text(),
                note=self.note_field.text(),
            )
            if success and record:
                self._selected_snapshot_id = record.get("id", "")
            self._set_status(message, success)
            self.refresh()

        def _save_milestone(self):
            success, message, record = self.controller.create_snapshot(
                label=self.label_field.text() or "Milestone",
                color=self.color_field.text() or DEFAULT_MILESTONE_COLOR,
                milestone=True,
                note=self.note_field.text(),
            )
            if success and record:
                self._selected_snapshot_id = record.get("id", "")
            self._set_status(message, success)
            self.refresh()

        def _restore_from_marker(self, snapshot_id):
            if snapshot_id:
                self._selected_snapshot_id = snapshot_id
            success, message = self.controller.restore_snapshot(snapshot_id, save_current_first=False)
            self._set_status(message, success)
            self.refresh()
            return True

        def _restore(self):
            snapshot_id = self.selected_snapshot_id()
            if not snapshot_id:
                self._set_status("Pick a snapshot in the History list or click a History toolbar square first.", False)
                return
            answer = QtWidgets.QMessageBox.question(
                self,
                "Restore History Snapshot",
                "Jump the whole Maya scene to the selected snapshot? This restores the saved state without creating a new snapshot.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
            success, message = self.controller.restore_snapshot(snapshot_id, save_current_first=False)
            self._set_status(message, success)
            self.refresh()

        def _rename(self):
            snapshot_id = self.selected_snapshot_id()
            if not snapshot_id:
                self._set_status("Pick a snapshot in the History list or click a History toolbar square first.", False)
                return
            current_label = self.label_field.text() or "Snapshot"
            new_label, accepted = QtWidgets.QInputDialog.getText(
                self,
                "Rename History Snapshot",
                "New snapshot label",
                QtWidgets.QLineEdit.Normal,
                current_label,
            )
            if not accepted:
                return
            self.label_field.setText(new_label)
            success, message = self.controller.rename_snapshot(snapshot_id, new_label)
            self._set_status(message, success)
            self.refresh()

        def _color(self):
            snapshot_id = self.selected_snapshot_id()
            if not snapshot_id:
                self._set_status("Pick a snapshot in the History list or click a History toolbar square first.", False)
                return
            success, message = self.controller.color_snapshot(snapshot_id, self.color_field.text())
            self._set_status(message, success)
            self.refresh()

        def _pick_color(self):
            snapshot_id = self.selected_snapshot_id()
            current_color = self.color_field.text().strip() or DEFAULT_STEP_COLOR
            chosen = QtWidgets.QColorDialog.getColor(QtGui.QColor(current_color), self, "Pick Snapshot Color")
            if not chosen.isValid():
                return
            color_name = chosen.name().upper()
            self.color_field.setText(color_name)
            if snapshot_id:
                success, message = self.controller.color_snapshot(snapshot_id, color_name)
                self._set_status(message, success)
                self.refresh()
            else:
                self._set_status("Color set for the next snapshot.", True)

        def _toggle_milestone(self):
            snapshot_id = self.selected_snapshot_id()
            if not snapshot_id:
                self._set_status("Pick a snapshot in the History list or click a History toolbar square first.", False)
                return
            record = self._record_for_id(snapshot_id) or {}
            make_milestone = not bool(record.get("milestone"))
            success, message = self.controller.set_snapshot_milestone(snapshot_id, make_milestone)
            self._set_status(message, success)
            self.refresh()

        def _delete(self):
            snapshot_id = self.selected_snapshot_id()
            if not snapshot_id:
                self._set_status("Pick a snapshot in the History list or click a History toolbar square first.", False)
                return
            answer = QtWidgets.QMessageBox.question(
                self,
                "Delete History Snapshot",
                "Delete this snapshot file and remove it from History Timeline?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
            success, message = self.controller.delete_snapshot(snapshot_id)
            self._set_status(message, success)
            self.refresh()

        def _delete_all(self):
            answer = QtWidgets.QMessageBox.question(
                self,
                "Delete All History Snapshots",
                "Delete every History Timeline snapshot file for this Maya scene? This includes milestones and cannot be undone.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
            success, message = self.controller.delete_all_snapshots(force=True)
            self._set_status(message, success)
            self.refresh()

        def _apply_cap(self):
            success, message = self.controller.set_snapshot_cap(self.snapshot_cap_spin.value())
            self._set_status(message, success)
            self.refresh()

        def _open_folder(self):
            success, message = self.controller.open_history_folder()
            self._set_status(message, success)


    class MayaHistoryTimelineWindow(QtWidgets.QDialog):
        def __init__(self, controller=None, parent=None):
            super(MayaHistoryTimelineWindow, self).__init__(parent)
            self.controller = controller or MayaHistoryTimelineController()
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("History Timeline")
            layout = QtWidgets.QVBoxLayout(self)
            self.panel = MayaHistoryTimelinePanel(self.controller, parent=self)
            layout.addWidget(self.panel)


GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


def launch_maya_history_timeline():
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not MAYA_AVAILABLE:
        raise RuntimeError("History Timeline must run inside Maya.")
    if not QtWidgets:
        raise RuntimeError("History Timeline needs PySide.")
    GLOBAL_CONTROLLER = MayaHistoryTimelineController()
    GLOBAL_WINDOW = MayaHistoryTimelineWindow(GLOBAL_CONTROLLER)
    GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "MayaHistoryTimelineController",
    "MayaHistoryTimelinePanel",
    "MayaHistoryTimelineWindow",
    "HistoryTimelineStrip",
    "launch_maya_history_timeline",
]
