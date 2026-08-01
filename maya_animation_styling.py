from __future__ import absolute_import, division, print_function

import os
import time

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om2
    import maya.api.OpenMayaAnim as oma2

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om2 = None
    oma2 = None
    MAYA_AVAILABLE = False

try:
    from PySide2 import QtWidgets
except Exception:
    try:
        from PySide6 import QtWidgets
    except Exception:
        QtWidgets = None

try:
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
except Exception:
    MayaQWidgetDockableMixin = None

import maya_skinning_cleanup as skin_cleanup


WINDOW_OBJECT_NAME = "mayaAnimationStylingWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
SHELF_BUTTON_DOC_TAG = "amir.maya.animationStyling"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL

ENABLED_OPTION = "AminateAnimationStylingHoldEnabled"
HOLD_FRAMES_OPTION = "AminateAnimationStylingHoldFrames"
STEP_CURVES_OPTION = "AminateAnimationStylingStepAllCurves"
DEFAULT_ENABLED = False
DEFAULT_HOLD_FRAMES = 2
DEFAULT_STEP_CURVES = False
MIN_HOLD_FRAMES = 1
MAX_HOLD_FRAMES = 24
BLOCKED_MARKER_ATTR = "aminateAnimationStylingBlockedHold"
BLOCKED_MARKER_COLOR = (0.95, 0.22, 0.18)

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None
_ACTIVE_CONTROLLERS = []

_qt_flag = skin_cleanup._qt_flag
_style_donate_button = skin_cleanup._style_donate_button
_open_external_url = skin_cleanup._open_external_url
_maya_main_window = skin_cleanup._maya_main_window


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


def _option_var_int(option_name, default):
    if not cmds or not cmds.optionVar(exists=option_name):
        return int(default)
    try:
        return int(cmds.optionVar(query=option_name))
    except Exception:
        return int(default)


def _save_option_var_int(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(intValue=(option_name, int(value)))
    except Exception:
        pass


def _clamp_hold_frames(value):
    return max(MIN_HOLD_FRAMES, min(MAX_HOLD_FRAMES, int(round(float(value or DEFAULT_HOLD_FRAMES)))))


def _short_name(node_name):
    return (node_name or "").split("|")[-1]


def _dedupe(values):
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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


def _anim_curve_name_from_object(mobject):
    if not om2:
        return ""
    try:
        return om2.MFnDependencyNode(mobject).name()
    except Exception:
        return ""


def _scene_anim_curves():
    if not cmds:
        return []
    curves = []
    for node_type in ("animCurveTA", "animCurveTL", "animCurveTT", "animCurveTU", "animCurveUA", "animCurveUL", "animCurveUT", "animCurveUU"):
        try:
            curves.extend(cmds.ls(type=node_type) or [])
        except Exception:
            pass
    return _dedupe(curves)


def _selected_anim_curves():
    if not cmds:
        return []
    curves = []
    selected_nodes = cmds.ls(selection=True, long=True) or []
    for node_name in selected_nodes:
        try:
            curves.extend(cmds.listConnections(node_name, source=True, destination=False, type="animCurve") or [])
        except Exception:
            pass
    return _dedupe(curves)


def _key_times(curve_name):
    try:
        return [float(value) for value in (cmds.keyframe(curve_name, query=True, timeChange=True) or [])]
    except Exception:
        return []


def _has_key_at(curve_name, frame):
    return any(abs(value - float(frame)) <= 1.0e-4 for value in _key_times(curve_name))


def _first_key_between(curve_name, start_frame, end_frame):
    start_frame = float(start_frame)
    end_frame = float(end_frame)
    for frame in sorted(_key_times(curve_name)):
        if frame > start_frame + 1.0e-4 and frame <= end_frame + 1.0e-4:
            return frame
    return None


def _value_at_key(curve_name, frame):
    values = cmds.keyframe(curve_name, query=True, time=(float(frame), float(frame)), valueChange=True) or []
    if values:
        return float(values[0])
    return float(cmds.keyframe(curve_name, query=True, eval=True, time=(float(frame), float(frame)))[0])


def _set_curves_to_stepped(curves):
    if not cmds:
        return 0
    changed = 0
    for curve_name in _dedupe(curves or []):
        if not curve_name or not cmds.objExists(curve_name):
            continue
        try:
            cmds.keyTangent(curve_name, edit=True, outTangentType="step")
            changed += 1
        except Exception:
            pass
    return changed


def _set_string_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, dataType="string")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), value or "", type="string")


def _set_bool_attr(node_name, attr_name, value):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="bool")
    cmds.setAttr("{0}.{1}".format(node_name, attr_name), bool(value))


def _ensure_bookmark_plugin():
    if not cmds:
        return False
    try:
        if not cmds.pluginInfo("timeSliderBookmark", query=True, loaded=True):
            cmds.loadPlugin("timeSliderBookmark", quiet=True)
        return True
    except Exception:
        return False


def _blocked_bookmarks():
    if not cmds:
        return []
    nodes = cmds.ls(type="timeSliderBookmark") or []
    result = []
    for node_name in nodes:
        try:
            if cmds.attributeQuery(BLOCKED_MARKER_ATTR, node=node_name, exists=True) and cmds.getAttr(node_name + "." + BLOCKED_MARKER_ATTR):
                result.append(node_name)
        except Exception:
            pass
    return result


def clear_blocked_markers():
    if not cmds:
        return 0
    deleted = 0
    for node_name in _blocked_bookmarks():
        try:
            cmds.delete(node_name)
            deleted += 1
        except Exception:
            pass
    return deleted


def _animation_styling_key_callback(curve_objects, client_data=None):
    for controller in list(_ACTIVE_CONTROLLERS):
        try:
            controller._on_keyframes_edited(curve_objects, client_data)
        except Exception as exc:
            try:
                controller.last_callback_error = str(exc)
            except Exception:
                pass


def _create_blocked_marker(curve_name, source_frame, blocked_frame, target_frame):
    if not _ensure_bookmark_plugin():
        return ""
    title = "Hold blocked {0} f{1:g}".format(_short_name(curve_name), source_frame)
    try:
        node_name = cmds.createNode("timeSliderBookmark", name="aminateStyleHoldBlocked_BKM")
        cmds.setAttr(node_name + ".timeRangeStart", float(source_frame))
        cmds.setAttr(node_name + ".timeRangeStop", float(target_frame))
        cmds.setAttr(node_name + ".name", title, type="string")
        cmds.setAttr(node_name + ".color", *BLOCKED_MARKER_COLOR)
        cmds.setAttr(node_name + ".priority", 999)
        _set_bool_attr(node_name, BLOCKED_MARKER_ATTR, True)
        _set_string_attr(node_name, "blockedCurve", curve_name)
        _set_string_attr(node_name, "blockedReason", "Key exists at frame {0:g}; hold target was frame {1:g}.".format(blocked_frame, target_frame))
        return node_name
    except Exception:
        return ""


class AnimationStylingController(object):
    def __init__(self):
        self.enabled = _option_var_bool(ENABLED_OPTION, DEFAULT_ENABLED)
        self.hold_frames = _clamp_hold_frames(_option_var_int(HOLD_FRAMES_OPTION, DEFAULT_HOLD_FRAMES))
        self.step_all_curves = _option_var_bool(STEP_CURVES_OPTION, DEFAULT_STEP_CURVES)
        self.status_callback = None
        self._callback_id = None
        self._idle_job_id = None
        self._processing = False
        self.last_callback_error = ""
        self._last_idle_check = 0.0
        self._processed_signatures = set()
        if self.enabled:
            self.install_key_callback()

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _emit_status(self, message, success=True):
        if self.status_callback:
            self.status_callback(message, success)
        elif MAYA_AVAILABLE and om2:
            if success:
                om2.MGlobal.displayInfo("[Animation Styling] {0}".format(message))
            else:
                om2.MGlobal.displayWarning("[Animation Styling] {0}".format(message))

    def install_key_callback(self):
        if not MAYA_AVAILABLE:
            return
        if oma2 and self._callback_id is None:
            if self not in _ACTIVE_CONTROLLERS:
                _ACTIVE_CONTROLLERS.append(self)
            self._callback_id = oma2.MAnimMessage.addAnimKeyframeEditedCallback(_animation_styling_key_callback)
        if cmds and self._idle_job_id is None:
            try:
                _kill_script_jobs_with_marker("AnimationStylingController._on_idle")
                self._idle_job_id = cmds.scriptJob(event=["idle", self._on_idle], protected=True)
            except Exception:
                self._idle_job_id = None

    def shutdown(self):
        if self._callback_id is not None:
            try:
                om2.MMessage.removeCallback(self._callback_id)
            except Exception:
                try:
                    oma2.MAnimMessage.removeCallback(self._callback_id)
                except Exception:
                    pass
        self._callback_id = None
        if self._idle_job_id is not None and cmds:
            try:
                if cmds.scriptJob(exists=self._idle_job_id):
                    cmds.scriptJob(kill=self._idle_job_id, force=True)
            except Exception:
                pass
        self._idle_job_id = None
        try:
            while self in _ACTIVE_CONTROLLERS:
                _ACTIVE_CONTROLLERS.remove(self)
        except Exception:
            pass

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        _save_option_var_bool(ENABLED_OPTION, self.enabled)
        if self.enabled:
            self.install_key_callback()
            message = "Animation Styling hold keys is on."
        else:
            self.shutdown()
            message = "Animation Styling hold keys is off."
        self._emit_status(message, True)
        return True, message

    def set_hold_frames(self, hold_frames):
        self.hold_frames = _clamp_hold_frames(hold_frames)
        _save_option_var_int(HOLD_FRAMES_OPTION, self.hold_frames)
        message = "Hold length set to {0} frame(s).".format(self.hold_frames)
        self._emit_status(message, True)
        return True, message

    def set_step_all_curves(self, enabled):
        self.step_all_curves = bool(enabled)
        _save_option_var_bool(STEP_CURVES_OPTION, self.step_all_curves)
        if self.step_all_curves:
            changed = _set_curves_to_stepped(_scene_anim_curves())
            message = "Stepped curves is on. Set {0} curve(s) to stepped tangents.".format(changed)
        else:
            message = "Stepped curves is off."
        self._emit_status(message, True)
        return True, message

    def activate_spider_verse_preset(self, apply_current_key=True):
        self.hold_frames = 2
        self.step_all_curves = True
        self.enabled = True
        _save_option_var_int(HOLD_FRAMES_OPTION, self.hold_frames)
        _save_option_var_bool(STEP_CURVES_OPTION, self.step_all_curves)
        _save_option_var_bool(ENABLED_OPTION, self.enabled)
        self.install_key_callback()
        stepped = _set_curves_to_stepped(_scene_anim_curves())
        applied = {"created": 0, "blocked": 0}
        if apply_current_key:
            curves = _selected_anim_curves()
            current_frame = float(cmds.currentTime(query=True)) if cmds else 0.0
            keyed_curves = [curve_name for curve_name in curves if _has_key_at(curve_name, current_frame)]
            if keyed_curves:
                _success, _message, applied = self.apply_hold_to_curves(keyed_curves, frames=[current_frame], quiet=True)
        message = "Spider-Verse style is on: twos, stepped curves, and auto-hold are ready."
        if applied.get("created", 0) or applied.get("blocked", 0):
            message += " Created {0} held key(s), blocked {1} overlap(s).".format(applied.get("created", 0), applied.get("blocked", 0))
        self._emit_status(message, True)
        return True, message, {"hold_frames": self.hold_frames, "stepped": stepped, "created": applied.get("created", 0), "blocked": applied.get("blocked", 0)}

    def _on_keyframes_edited(self, curve_objects, _client_data=None):
        if not self.enabled or self._processing:
            return
        curve_names = []
        try:
            for item in curve_objects:
                curve_name = _anim_curve_name_from_object(item)
                if curve_name:
                    curve_names.append(curve_name)
        except Exception:
            curve_names = []
        if not curve_names:
            return
        current_frame = float(cmds.currentTime(query=True))
        self.apply_hold_to_curves(_dedupe(curve_names), frames=[current_frame], quiet=True)

    def _on_idle(self):
        if not self.enabled or self._processing or not cmds:
            return
        now = time.time()
        if now - self._last_idle_check < 0.15:
            return
        self._last_idle_check = now
        current_frame = float(cmds.currentTime(query=True))
        curves = _selected_anim_curves()
        pending_curves = []
        for curve_name in curves:
            if not _has_key_at(curve_name, current_frame):
                continue
            try:
                value = _value_at_key(curve_name, current_frame)
            except Exception:
                continue
            signature = (curve_name, round(current_frame, 4), round(value, 6), int(self.hold_frames))
            if signature in self._processed_signatures:
                continue
            self._processed_signatures.add(signature)
            pending_curves.append(curve_name)
        if pending_curves:
            self.apply_hold_to_curves(_dedupe(pending_curves), frames=[current_frame], quiet=True)

    def apply_hold_to_current_key(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}
        curves = _selected_anim_curves()
        if not curves:
            return False, "Select animated controls first.", {}
        success, message, detail = self.apply_hold_to_curves(curves, frames=[float(cmds.currentTime(query=True))])
        self._emit_status(message, success)
        return success, message, detail

    def apply_hold_to_selected_existing_keys(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}
        curves = _selected_anim_curves()
        if not curves:
            return False, "Select animated controls first.", {}
        frame_set = set()
        for curve_name in curves:
            frame_set.update(_key_times(curve_name))
        success, message, detail = self.apply_hold_to_curves(curves, frames=sorted(frame_set))
        self._emit_status(message, success)
        return success, message, detail

    def apply_hold_to_curves(self, curves, frames=None, quiet=False):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya.", {}
        frames = sorted(set(float(value) for value in (frames or [])))
        curves = _dedupe(curves or [])
        if not curves or not frames:
            return False, "No animated keyframes found.", {}
        created = 0
        blocked = []
        self._processing = True
        try:
            cmds.undoInfo(openChunk=True, chunkName="AminateAnimationStylingHoldKeys")
        except Exception:
            pass
        try:
            for curve_name in curves:
                if not curve_name or not cmds.objExists(curve_name):
                    continue
                for source_frame in frames:
                    if not _has_key_at(curve_name, source_frame):
                        continue
                    target_frame = source_frame + float(self.hold_frames)
                    blocked_frame = _first_key_between(curve_name, source_frame, target_frame)
                    if blocked_frame is not None:
                        blocked.append((curve_name, source_frame, blocked_frame, target_frame))
                        continue
                    value = _value_at_key(curve_name, source_frame)
                    try:
                        cmds.setKeyframe(curve_name, time=target_frame, value=value)
                        created += 1
                    except Exception:
                        continue
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
            self._processing = False
        if blocked:
            self.refresh_blocked_markers(blocked)
        stepped = 0
        if self.step_all_curves:
            stepped = _set_curves_to_stepped(_scene_anim_curves())
        detail = {"created": created, "blocked": len(blocked), "hold_frames": self.hold_frames, "stepped": stepped}
        message = "Created {0} held key(s), blocked {1} overlap(s).".format(created, len(blocked))
        if self.step_all_curves:
            message += " Set {0} curve(s) to stepped tangents.".format(stepped)
        if not quiet:
            self._emit_status(message, True)
        return True, message, detail

    def refresh_blocked_markers(self, blocked=None):
        clear_blocked_markers()
        blocked = blocked if blocked is not None else self.find_blocked_overlaps()[2].get("blocked_items", [])
        created = 0
        for item in blocked:
            if isinstance(item, dict):
                curve_name = item.get("curve")
                source_frame = item.get("source")
                blocked_frame = item.get("blocked")
                target_frame = item.get("target")
            else:
                curve_name, source_frame, blocked_frame, target_frame = item
            if _create_blocked_marker(curve_name, source_frame, blocked_frame, target_frame):
                created += 1
        message = "Highlighted {0} blocked hold range(s) on the timeline.".format(created)
        self._emit_status(message, True)
        return True, message, {"markers": created}

    def find_blocked_overlaps(self, curves=None):
        curves = _dedupe(curves or _selected_anim_curves() or _scene_anim_curves())
        blocked = []
        for curve_name in curves:
            frames = sorted(_key_times(curve_name))
            for source_frame in frames:
                target_frame = source_frame + float(self.hold_frames)
                blocked_frame = _first_key_between(curve_name, source_frame, target_frame)
                if blocked_frame is not None:
                    blocked.append(
                        {
                            "curve": curve_name,
                            "source": source_frame,
                            "blocked": blocked_frame,
                            "target": target_frame,
                        }
                    )
        message = "Found {0} blocked hold overlap(s).".format(len(blocked))
        return True, message, {"blocked_items": blocked}

    def clear_blocked_timeline_markers(self):
        deleted = clear_blocked_markers()
        message = "Cleared {0} Animation Styling timeline warning(s).".format(deleted)
        self._emit_status(message, True)
        return True, message, {"deleted": deleted}


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        _HAS_MAYA_MAIN_WINDOW = MQtUtil.mainWindow() is not None
    except Exception:
        _HAS_MAYA_MAIN_WINDOW = False
    _WindowBase = type("AnimationStylingWindowBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {}) if MayaQWidgetDockableMixin and _HAS_MAYA_MAIN_WINDOW else type("AnimationStylingWindowBase", (QtWidgets.QDialog,), {})


    class AnimationStylingPanel(QtWidgets.QWidget):
        def __init__(self, controller=None, parent=None, status_callback=None):
            super(AnimationStylingPanel, self).__init__(parent)
            self.controller = controller or AnimationStylingController()
            self.status_callback = status_callback
            self.controller.set_status_callback(self._set_status)
            self._build_ui()
            self._sync_from_controller()

        def _build_ui(self):
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            header = QtWidgets.QGroupBox("Spider-Verse Style Holds")
            header_layout = QtWidgets.QGridLayout(header)
            self.spider_verse_button = QtWidgets.QPushButton("Spider-Verse")
            self.spider_verse_button.setObjectName("aminateSpiderVersePresetButton")
            self.spider_verse_button.setToolTip("Turn on the Spider-Verse preset: twos, stepped curves, auto-hold, and current-key hold when a keyed control is selected.")
            header_layout.addWidget(self.spider_verse_button, 0, 0, 1, 2)
            self.enabled_check = QtWidgets.QCheckBox("Auto duplicate new keys")
            self.enabled_check.setObjectName("aminateAnimationStylingAutoHoldCheck")
            self.enabled_check.setToolTip("When on, every new current-frame key gets copied forward by the hold length unless another key blocks it.")
            header_layout.addWidget(self.enabled_check, 1, 0, 1, 2)
            header_layout.addWidget(QtWidgets.QLabel("Hold Length"), 2, 0)
            self.hold_spin = QtWidgets.QSpinBox()
            self.hold_spin.setObjectName("aminateAnimationStylingHoldSpin")
            self.hold_spin.setRange(MIN_HOLD_FRAMES, MAX_HOLD_FRAMES)
            self.hold_spin.setSuffix(" frame(s)")
            self.hold_spin.setToolTip("Example: 2 means a key on frame 0 also gets copied to frame 2.")
            header_layout.addWidget(self.hold_spin, 2, 1)
            self.step_curves_check = QtWidgets.QCheckBox("Set all curves to stepped curves")
            self.step_curves_check.setObjectName("aminateAnimationStylingStepCheck")
            self.step_curves_check.setToolTip("When on, Aminate converts scene animation curves to stepped tangents so held poses stay locked until the next key.")
            header_layout.addWidget(self.step_curves_check, 3, 0, 1, 2)
            layout.addWidget(header)

            action_group = QtWidgets.QGroupBox("Apply / Check")
            action_layout = QtWidgets.QGridLayout(action_group)
            self.apply_current_button = QtWidgets.QPushButton("Hold Current Key")
            self.apply_current_button.setObjectName("aminateAnimationStylingHoldCurrentButton")
            self.apply_current_button.setToolTip("Copy selected controls' current-frame key forward by the hold length.")
            self.apply_selected_button = QtWidgets.QPushButton("Hold Selected Existing Keys")
            self.apply_selected_button.setObjectName("aminateAnimationStylingHoldSelectedButton")
            self.apply_selected_button.setToolTip("Copy every existing selected-control key forward where it does not overlap another key.")
            self.scan_button = QtWidgets.QPushButton("Scan Overlaps")
            self.scan_button.setObjectName("aminateAnimationStylingScanButton")
            self.scan_button.setToolTip("Color blocked ranges on the timeline where a hold key would overlap a nearby key.")
            self.clear_button = QtWidgets.QPushButton("Clear Timeline Warnings")
            self.clear_button.setObjectName("aminateAnimationStylingClearWarningsButton")
            self.clear_button.setToolTip("Remove Animation Styling blocked-range timeline markers.")
            for action_button in (
                self.spider_verse_button,
                self.apply_current_button,
                self.apply_selected_button,
                self.scan_button,
                self.clear_button,
            ):
                action_button.setMinimumWidth(0)
                action_button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            action_layout.addWidget(self.apply_current_button, 0, 0, 1, 2)
            action_layout.addWidget(self.apply_selected_button, 1, 0, 1, 2)
            action_layout.addWidget(self.scan_button, 2, 0, 1, 2)
            action_layout.addWidget(self.clear_button, 3, 0, 1, 2)
            layout.addWidget(action_group)

            self.help_box = QtWidgets.QPlainTextEdit()
            self.help_box.setObjectName("aminateAnimationStylingGuideBox")
            self.help_box.setReadOnly(True)
            self.help_box.setMinimumHeight(90)
            self.help_box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            self.help_box.setPlainText(
                "How it works:\n"
                "1. Press Spider-Verse.\n"
                "2. Animate on twos with stepped curves.\n"
                "3. When a keyed control is selected, Aminate can copy the current pose forward by two frames.\n"
                "4. If another key blocks the hold, Aminate skips it and marks that blocked range red on the timeline."
            )
            layout.addWidget(self.help_box)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)
            layout.addStretch(1)

            self.enabled_check.toggled.connect(self._toggle_enabled)
            self.spider_verse_button.clicked.connect(self._activate_spider_verse)
            self.hold_spin.valueChanged.connect(self._set_hold_frames)
            self.step_curves_check.toggled.connect(self._toggle_step_curves)
            self.apply_current_button.clicked.connect(self._apply_current)
            self.apply_selected_button.clicked.connect(self._apply_selected)
            self.scan_button.clicked.connect(self._scan_overlaps)
            self.clear_button.clicked.connect(self._clear_markers)

        def _sync_from_controller(self):
            self.enabled_check.blockSignals(True)
            self.enabled_check.setChecked(bool(self.controller.enabled))
            self.enabled_check.blockSignals(False)
            self.hold_spin.blockSignals(True)
            self.hold_spin.setValue(int(self.controller.hold_frames))
            self.hold_spin.blockSignals(False)
            self.step_curves_check.blockSignals(True)
            self.step_curves_check.setChecked(bool(self.controller.step_all_curves))
            self.step_curves_check.blockSignals(False)

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            if self.status_callback:
                self.status_callback(message, success)

        def _toggle_enabled(self, enabled):
            success, message = self.controller.set_enabled(enabled)
            if not success:
                self._sync_from_controller()
            self._set_status(message, success)

        def _set_hold_frames(self, value):
            success, message = self.controller.set_hold_frames(value)
            self._set_status(message, success)

        def _toggle_step_curves(self, enabled):
            success, message = self.controller.set_step_all_curves(enabled)
            self._set_status(message, success)

        def _activate_spider_verse(self):
            success, message, _detail = self.controller.activate_spider_verse_preset(apply_current_key=True)
            self._sync_from_controller()
            self._set_status(message, success)

        def _apply_current(self):
            success, message, _detail = self.controller.apply_hold_to_current_key()
            self._set_status(message, success)

        def _apply_selected(self):
            success, message, _detail = self.controller.apply_hold_to_selected_existing_keys()
            self._set_status(message, success)

        def _scan_overlaps(self):
            success, message, detail = self.controller.find_blocked_overlaps()
            if success:
                self.controller.refresh_blocked_markers(detail.get("blocked_items", []))
            self._set_status(message, success)

        def _clear_markers(self):
            success, message, _detail = self.controller.clear_blocked_timeline_markers()
            self._set_status(message, success)


    class AnimationStylingWindow(_WindowBase):
        def __init__(self, controller=None, parent=None):
            super(AnimationStylingWindow, self).__init__(parent or _maya_main_window())
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Animation Styling")
            self.controller = controller or AnimationStylingController()
            layout = QtWidgets.QVBoxLayout(self)
            self.panel = AnimationStylingPanel(self.controller, parent=self)
            layout.addWidget(self.panel)
            footer = QtWidgets.QHBoxLayout()
            self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(lambda _url: _open_external_url(FOLLOW_AMIR_URL))
            footer.addWidget(self.brand_label, 1)
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.clicked.connect(lambda: _open_external_url(DONATE_URL))
            footer.addWidget(self.donate_button)
            layout.addLayout(footer)

        def closeEvent(self, event):
            # Maya owns the dockable Qt wrapper.  Native destruction during a
            # close can invalidate Maya's workspace-control pointer and crash
            # the host.  Keep the controller and window alive for reuse.
            self.hide()
            event.ignore()


def launch_maya_animation_styling(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not MAYA_AVAILABLE:
        raise RuntimeError("Animation Styling must run inside Maya.")
    if not QtWidgets:
        raise RuntimeError("PySide is not available in this Maya session.")
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            return GLOBAL_WINDOW
        except Exception:
            # A genuinely stale wrapper can be discarded without invoking Qt
            # close or deleteLater on Maya-owned UI.
            GLOBAL_WINDOW = None
            GLOBAL_CONTROLLER = None
    GLOBAL_CONTROLLER = AnimationStylingController()
    GLOBAL_WINDOW = AnimationStylingWindow(GLOBAL_CONTROLLER)
    try:
        GLOBAL_WINDOW.show(dockable=bool(dock), floating=not bool(dock), area="right")
    except TypeError:
        GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "AnimationStylingController",
    "AnimationStylingPanel",
    "AnimationStylingWindow",
    "launch_maya_animation_styling",
]
