"""
maya_rotation_doctor.py

Rotation cleanup and diagnosis tool for Maya 2022-2026.
"""

from __future__ import absolute_import, division, print_function

import math
import os
import traceback

import maya_shelf_utils

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    import maya.mel as mel
    import maya.OpenMayaUI as omui
    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    mel = None
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


WINDOW_OBJECT_NAME = "mayaRotationDoctorWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
DEFAULT_SHELF_NAME = maya_shelf_utils.DEFAULT_SHELF_NAME
DEFAULT_SHELF_BUTTON_LABEL = "Rotation Doctor"
SHELF_BUTTON_DOC_TAG = "mayaRotationDoctorShelfButton"
ROTATE_ATTRS = ("rotateX", "rotateY", "rotateZ")
ROTATE_ORDER_NAMES = {0: "xyz", 1: "yzx", 2: "zxy", 3: "xzy", 4: "yxz", 5: "zyx"}
RECIPE_LABELS = {
    "clean_euler_discontinuity": "Fix Flips",
    "flip_current_key_euler": "Flip Current Key",
    "preserve_spin_and_unroll": "Keep Big Spins",
    "switch_interp_to_synchronized_euler": "Smooth Euler",
    "switch_interp_to_quaternion": "Quaternion Mode",
    "custom_continuity_pass": "Extra Cleanup",
}
SUPPORTED_TRANSFORM_TYPES = ("transform", "joint")
LONG_SPIN_THRESHOLD = 270.0
DISCONTINUITY_DELTA_REDUCTION = 90.0
GIMBAL_RISK_THRESHOLD = 12.0
LONG_SPIN_COLLAPSE_TOLERANCE = 45.0
VALUE_EPSILON = 1.0e-4

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


def _debug(message):
    if MAYA_AVAILABLE:
        om.MGlobal.displayInfo("[Maya Rotation Doctor] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE:
        om.MGlobal.displayWarning("[Maya Rotation Doctor] {0}".format(message))


def _error(message):
    if MAYA_AVAILABLE:
        om.MGlobal.displayError("[Maya Rotation Doctor] {0}".format(message))


def _dedupe_preserve_order(items):
    deduped = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _short_name(node_name):
    return node_name.split("|")[-1].split(":")[-1]


def _normalized_angle(value):
    return ((float(value) + 180.0) % 360.0) - 180.0


def _qt_flag(scope_name, member_name, fallback=None):
    if not QtCore:
        return fallback
    if hasattr(QtCore.Qt, member_name):
        return getattr(QtCore.Qt, member_name)
    scoped_enum = getattr(QtCore.Qt, scope_name, None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return fallback


def _style_donate_button(button):
    if not button or not QtWidgets:
        return
    button.setMinimumWidth(92)
    button.setStyleSheet(
        """
        QPushButton {
            background-color: #FFC439;
            color: #111111;
            border: 1px solid #D9A000;
            border-radius: 5px;
            font-weight: 600;
            padding: 4px 12px;
        }
        QPushButton:hover {
            background-color: #FFD55C;
            border-color: #C89200;
        }
        QPushButton:pressed {
            background-color: #E6B12E;
            border-color: #AD7A00;
        }
        QPushButton:disabled {
            background-color: #D9D9D9;
            color: #666666;
            border-color: #BBBBBB;
        }
        """
    )


def _open_external_url(url):
    if not url:
        return False
    if QtGui and QtCore:
        try:
            if QtGui.QDesktopServices.openUrl(QtCore.QUrl(url)):
                return True
        except Exception:
            pass
    if MAYA_AVAILABLE and cmds:
        try:
            cmds.launch(web=url)
            return True
        except Exception:
            pass
    return False


def _shelf_button_command(repo_path):
    return (
        "import importlib\n"
        "import sys\n"
        "repo_path = r\"{0}\"\n"
        "if repo_path not in sys.path:\n"
        "    sys.path.insert(0, repo_path)\n"
        "import maya_rotation_doctor\n"
        "importlib.reload(maya_rotation_doctor)\n"
        "maya_rotation_doctor.launch_maya_rotation_doctor()\n"
    ).format(repo_path.replace("\\", "\\\\"))


def install_maya_rotation_doctor_shelf_button(
    shelf_name=DEFAULT_SHELF_NAME,
    button_label=DEFAULT_SHELF_BUTTON_LABEL,
    repo_path=None,
):
    if not MAYA_AVAILABLE:
        raise RuntimeError("install_maya_rotation_doctor_shelf_button() must run inside Autodesk Maya.")

    repo_path = repo_path or os.path.dirname(os.path.abspath(__file__))
    metadata = maya_shelf_utils.install_shelf_button(
        command_text=_shelf_button_command(repo_path),
        doc_tag=SHELF_BUTTON_DOC_TAG,
        annotation="Launch Maya Rotation Doctor",
        button_label=button_label,
        image_overlay_label="RD",
        shelf_name=shelf_name,
    )
    return metadata["button"]


def _maya_main_window():
    if not (MAYA_AVAILABLE and QtWidgets and shiboken and omui):
        return None
    main_window = omui.MQtUtil.mainWindow()
    if not main_window:
        return None
    return shiboken.wrapInstance(int(main_window), QtWidgets.QWidget)


def _close_existing_window():
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW

    if GLOBAL_CONTROLLER:
        try:
            GLOBAL_CONTROLLER.shutdown()
        except Exception:
            pass
        GLOBAL_CONTROLLER = None

    if MAYA_AVAILABLE and cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True):
        try:
            cmds.deleteUI(WORKSPACE_CONTROL_NAME, control=True)
        except Exception:
            pass

    if QtWidgets:
        application = QtWidgets.QApplication.instance()
        if application and hasattr(application, "topLevelWidgets"):
            for widget in application.topLevelWidgets():
                if widget.objectName() == WINDOW_OBJECT_NAME:
                    widget.close()
                    widget.deleteLater()

    GLOBAL_WINDOW = None


def _selected_transform_targets():
    if not MAYA_AVAILABLE:
        return []
    selection = cmds.ls(selection=True, long=True) or []
    targets = []
    for item in selection:
        if not cmds.objExists(item):
            continue
        node_type = cmds.nodeType(item)
        if node_type in SUPPORTED_TRANSFORM_TYPES:
            targets.append(item)
            continue
        parents = cmds.listRelatives(item, parent=True, fullPath=True) or []
        for parent in parents:
            if cmds.nodeType(parent) in SUPPORTED_TRANSFORM_TYPES:
                targets.append(parent)
    return _dedupe_preserve_order(targets)


def _rotate_order_name(node_name):
    if not MAYA_AVAILABLE or not cmds.objExists(node_name):
        return "xyz"
    try:
        return ROTATE_ORDER_NAMES.get(int(cmds.getAttr(node_name + ".rotateOrder")), "xyz")
    except Exception:
        return "xyz"


def _middle_axis_for_order(order_name):
    order = (order_name or "xyz").lower()
    if len(order) != 3:
        return "rotateY"
    return "rotate" + order[1].upper()


def _curve_names_for_attr(node_name, attr_name):
    curve_names = cmds.keyframe(node_name, attribute=attr_name, query=True, name=True) or []
    return _dedupe_preserve_order(curve_names)


def _channel_state(node_name, attr_name):
    curve_names = _curve_names_for_attr(node_name, attr_name)
    times = cmds.keyframe(node_name, attribute=attr_name, query=True, timeChange=True) or []
    values = cmds.keyframe(node_name, attribute=attr_name, query=True, valueChange=True) or []
    key_count = min(len(times), len(values))
    if key_count <= 0:
        return None

    return {
        "attribute": attr_name,
        "curve_names": curve_names,
        "curve_name": curve_names[0] if curve_names else None,
        "times": [float(times[index]) for index in range(key_count)],
        "values": [float(values[index]) for index in range(key_count)],
        "supported": len(curve_names) == 1,
        "unsupported_reason": None
        if len(curve_names) == 1
        else "Multiple animation curves or layers drive {0}; V1 only edits one rotate curve per channel.".format(attr_name),
    }


def _equivalent_candidates(value):
    return [float(value) + (360.0 * step) for step in range(-8, 9)]


def _nearest_equivalent(value, reference):
    return min(_equivalent_candidates(value), key=lambda candidate: abs(candidate - reference))


def _nearest_equivalent_to_context(value, previous_value=None, next_value=None):
    references = []
    if previous_value is not None:
        references.append(float(previous_value))
    if next_value is not None:
        references.append(float(next_value))
    if not references:
        return _normalized_angle(value)
    reference = sum(references) / float(len(references))
    return _nearest_equivalent(value, reference)


def _output_plug_for_curve(curve_name):
    if not MAYA_AVAILABLE or not curve_name or not cmds.objExists(curve_name):
        return ""
    plugs = cmds.listConnections(curve_name + ".output", source=False, destination=True, plugs=True) or []
    for plug_name in plugs:
        attr_name = plug_name.split(".")[-1]
        if attr_name in ROTATE_ATTRS:
            return plug_name
    return plugs[0] if plugs else ""


def _is_rotate_curve(curve_name):
    if not MAYA_AVAILABLE or not curve_name or not cmds.objExists(curve_name):
        return False
    if cmds.nodeType(curve_name) != "animCurveTA":
        return False
    plug_name = _output_plug_for_curve(curve_name)
    return plug_name.split(".")[-1] in ROTATE_ATTRS


def _curve_key_data(curve_name):
    times = cmds.keyframe(curve_name, query=True, timeChange=True) or []
    values = cmds.keyframe(curve_name, query=True, valueChange=True) or []
    key_count = min(len(times), len(values))
    return [(float(times[index]), float(values[index])) for index in range(key_count)]


def _neighbor_values_for_time(curve_name, time_value):
    key_data = _curve_key_data(curve_name)
    previous_values = [value for key_time, value in key_data if key_time < (float(time_value) - VALUE_EPSILON)]
    next_values = [value for key_time, value in key_data if key_time > (float(time_value) + VALUE_EPSILON)]
    previous_value = previous_values[-1] if previous_values else None
    next_value = next_values[0] if next_values else None
    return previous_value, next_value


def _selected_rotate_curve_keys():
    if not MAYA_AVAILABLE:
        return []
    curve_names = cmds.keyframe(query=True, selected=True, name=True) or []
    selected = []
    seen = set()
    for curve_name in _dedupe_preserve_order(curve_names):
        if not _is_rotate_curve(curve_name):
            continue
        times = cmds.keyframe(curve_name, query=True, selected=True, timeChange=True) or []
        values = cmds.keyframe(curve_name, query=True, selected=True, valueChange=True) or []
        for index in range(min(len(times), len(values))):
            key = (curve_name, float(times[index]))
            if key in seen:
                continue
            seen.add(key)
            selected.append(
                {
                    "curve": curve_name,
                    "time": float(times[index]),
                    "value": float(values[index]),
                    "plug": _output_plug_for_curve(curve_name),
                }
            )
    return selected


def _current_frame_rotate_keys_for_selection():
    if not MAYA_AVAILABLE:
        return []
    current_time = float(cmds.currentTime(query=True))
    keys = []
    seen = set()
    for node_name in _selected_transform_targets():
        for attr_name in ROTATE_ATTRS:
            for curve_name in _curve_names_for_attr(node_name, attr_name):
                if not _is_rotate_curve(curve_name):
                    continue
                values = cmds.keyframe(curve_name, query=True, time=(current_time, current_time), valueChange=True) or []
                if not values:
                    continue
                key = (curve_name, current_time)
                if key in seen:
                    continue
                seen.add(key)
                keys.append(
                    {
                        "curve": curve_name,
                        "time": current_time,
                        "value": float(values[0]),
                        "plug": "{0}.{1}".format(node_name, attr_name),
                    }
                )
    return keys


def _fix_euler_keys(keys):
    changed = []
    for key_info in keys:
        curve_name = key_info["curve"]
        time_value = key_info["time"]
        old_value = key_info["value"]
        previous_value, next_value = _neighbor_values_for_time(curve_name, time_value)
        new_value = _nearest_equivalent_to_context(old_value, previous_value, next_value)
        if abs(new_value - old_value) <= VALUE_EPSILON:
            continue
        cmds.keyframe(curve_name, edit=True, time=(time_value, time_value), valueChange=float(new_value))
        changed.append(
            {
                "curve": curve_name,
                "plug": key_info.get("plug") or _output_plug_for_curve(curve_name),
                "time": time_value,
                "old_value": old_value,
                "new_value": new_value,
            }
        )
    return changed


def _best_spin_preserving_candidate(value, previous_solved):
    candidates = _equivalent_candidates(value)
    target_delta = float(value) - float(previous_solved)
    if abs(target_delta) <= VALUE_EPSILON:
        return _nearest_equivalent(value, previous_solved)

    desired_sign = 1.0 if target_delta >= 0.0 else -1.0
    same_direction = []
    for candidate in candidates:
        candidate_delta = candidate - previous_solved
        if abs(candidate_delta) <= VALUE_EPSILON:
            continue
        if math.copysign(1.0, candidate_delta) == desired_sign:
            same_direction.append(candidate)
    search_pool = same_direction or candidates
    return min(search_pool, key=lambda candidate: abs((candidate - previous_solved) - target_delta))


def _is_likely_discontinuity(raw_delta, nearest_delta):
    raw_delta = abs(float(raw_delta))
    nearest_delta = abs(float(nearest_delta))
    return raw_delta > 180.0 and (raw_delta - nearest_delta) > DISCONTINUITY_DELTA_REDUCTION


def _is_likely_intentional_long_spin(previous_raw, current_raw, previous_solved):
    raw_delta = float(current_raw) - float(previous_raw)
    nearest = _nearest_equivalent(current_raw, previous_solved)
    nearest_delta = nearest - previous_solved
    if abs(raw_delta) < LONG_SPIN_THRESHOLD:
        return False
    if abs(current_raw) > 360.0 or abs(previous_raw) > 360.0:
        return True
    if abs(raw_delta) >= 300.0 and abs(nearest_delta) <= LONG_SPIN_COLLAPSE_TOLERANCE:
        return False
    if abs(raw_delta) >= 360.0 and abs(nearest_delta) > 60.0:
        return True
    return abs(raw_delta) >= LONG_SPIN_THRESHOLD and abs(nearest_delta) > 75.0


def _solve_continuity_values(values, preserve_long_spins):
    if not values:
        return []

    solved = [float(values[0])]
    for index in range(1, len(values)):
        previous_raw = float(values[index - 1])
        current_raw = float(values[index])
        previous_solved = solved[-1]
        nearest = _nearest_equivalent(current_raw, previous_solved)
        if preserve_long_spins and _is_likely_intentional_long_spin(previous_raw, current_raw, previous_solved):
            solved.append(_best_spin_preserving_candidate(current_raw, previous_solved))
        else:
            solved.append(nearest)
    return solved


def _analyze_channel(channel_state):
    values = channel_state["values"]
    times = channel_state["times"]
    discontinuity_count = 0
    long_spin_count = 0
    discontinuity_notes = []
    spin_notes = []
    solved_preview = [values[0]]

    for index in range(1, len(values)):
        raw_delta = values[index] - values[index - 1]
        nearest = _nearest_equivalent(values[index], solved_preview[-1])
        nearest_delta = nearest - solved_preview[-1]

        if _is_likely_discontinuity(raw_delta, nearest_delta):
            discontinuity_count += 1
            discontinuity_notes.append(
                "{0:g}->{1:g} can be rewritten as a shorter {2:.2f} degree move around frame {3:g}.".format(
                    values[index - 1],
                    values[index],
                    nearest_delta,
                    times[index],
                )
            )

        if _is_likely_intentional_long_spin(values[index - 1], values[index], solved_preview[-1]):
            long_spin_count += 1
            spin_notes.append(
                "Large {0:.2f} degree move around frame {1:g} looks intentional and should be preserved.".format(
                    raw_delta,
                    times[index],
                )
            )

        solved_preview.append(nearest)

    raw_deltas = [values[index] - values[index - 1] for index in range(1, len(values))]
    equivalent_deltas = [solved_preview[index] - solved_preview[index - 1] for index in range(1, len(solved_preview))]

    return {
        "attribute": channel_state["attribute"],
        "curve_name": channel_state["curve_name"],
        "curve_names": channel_state["curve_names"],
        "times": times,
        "values": values,
        "supported": channel_state["supported"],
        "unsupported_reason": channel_state["unsupported_reason"],
        "discontinuity_count": discontinuity_count,
        "long_spin_count": long_spin_count,
        "raw_deltas": raw_deltas,
        "equivalent_deltas": equivalent_deltas,
        "max_raw_delta": max([abs(delta) for delta in raw_deltas] or [0.0]),
        "max_equivalent_delta": max([abs(delta) for delta in equivalent_deltas] or [0.0]),
        "discontinuity_notes": discontinuity_notes,
        "spin_notes": spin_notes,
    }


def _detect_gimbal_risk(report):
    keyed_channels = report["keyed_channels"]
    if len(keyed_channels) < 2:
        return False, None

    middle_attr = _middle_axis_for_order(report["rotate_order"])
    middle_channel = report["channels"].get(middle_attr)
    if not middle_channel:
        return False, None

    risky_samples = []
    for time_value, raw_value in zip(middle_channel["times"], middle_channel["values"]):
        normalized = _normalized_angle(raw_value)
        distance = min(abs(normalized - 90.0), abs(normalized + 90.0))
        if distance <= GIMBAL_RISK_THRESHOLD:
            risky_samples.append((time_value, raw_value))

    if not risky_samples:
        return False, None

    first_time, first_value = risky_samples[0]
    note = (
        "{0} is the middle axis for rotate order {1}; it comes near +/-90 degrees around frame {2:g} ({3:.2f})."
    ).format(middle_attr, report["rotate_order"].upper(), first_time, first_value)
    return True, note


def _issue_type_for_report(report):
    if not report["supported"]:
        return "Unsupported layered rotation setup"
    if report["has_long_spin"] and report["has_discontinuity"]:
        return "Intentional long spin plus discontinuity risk"
    if report["has_long_spin"]:
        return "Intentional long spin detected"
    if report["has_discontinuity"]:
        return "Euler discontinuity"
    if report["has_gimbal_risk"]:
        return "Likely gimbal-prone Euler pose"
    if report["has_multi_axis_rotation"]:
        return "Multi-axis rotation"
    return "No obvious issue"


def _recommended_recipe_for_report(report):
    if not report["supported"]:
        return None
    if report["has_long_spin"]:
        return "preserve_spin_and_unroll"
    if report["has_discontinuity"]:
        return "clean_euler_discontinuity"
    if report["has_gimbal_risk"]:
        return "switch_interp_to_quaternion"
    if report.get("has_full_rotation_set"):
        return "switch_interp_to_synchronized_euler"
    if report["has_multi_axis_rotation"]:
        return "switch_interp_to_quaternion"
    return None


def _build_report(node_name):
    channels = {}
    keyed_channels = []
    supported = True
    notes = []
    warnings = []

    for attr_name in ROTATE_ATTRS:
        state = _channel_state(node_name, attr_name)
        if not state:
            continue
        analysis = _analyze_channel(state)
        channels[attr_name] = analysis
        keyed_channels.append(attr_name)
        if not analysis["supported"]:
            supported = False
            warnings.append(analysis["unsupported_reason"])
        warnings.extend(analysis["spin_notes"])
        notes.extend(analysis["discontinuity_notes"])

    if not keyed_channels:
        return None

    report = {
        "transform": node_name,
        "display_name": _short_name(node_name),
        "rotate_order": _rotate_order_name(node_name),
        "keyed_channels": keyed_channels,
        "channels": channels,
        "supported": supported,
        "notes": notes,
        "warnings": warnings,
        "has_discontinuity": any(ch["discontinuity_count"] > 0 for ch in channels.values()),
        "has_long_spin": any(ch["long_spin_count"] > 0 for ch in channels.values()),
        "has_multi_axis_rotation": len(keyed_channels) >= 2,
        "has_full_rotation_set": len(keyed_channels) == 3,
        "interpolation_state": "Heuristic / native curve set",
    }

    report["has_gimbal_risk"], gimbal_note = _detect_gimbal_risk(report)
    if gimbal_note:
        report["warnings"].append(gimbal_note)
    if report["has_multi_axis_rotation"]:
        report["notes"].append(
            "Interpolation recommendations are heuristic in V1; Maya does not expose a clean current interpolation readout here."
        )

    report["issue_type"] = _issue_type_for_report(report)
    report["recommended_recipe"] = _recommended_recipe_for_report(report)
    return report


def _report_detail_text(report):
    lines = [
        "Control: {0}".format(report["display_name"]),
        "Rotation Order: {0}".format(report["rotate_order"].upper()),
        "Moved Axes: {0}".format(", ".join(report["keyed_channels"])),
        "Problem: {0}".format(report["issue_type"]),
        "Best Fix: {0}".format(RECIPE_LABELS.get(report["recommended_recipe"], "No change needed")),
        "How The Rotation Moves: {0}".format(report["interpolation_state"]),
    ]

    for attr_name in report["keyed_channels"]:
        channel = report["channels"][attr_name]
        lines.append(
            "{0}: {1} keys, max raw jump {2:.2f}, discontinuities {3}, long spins {4}".format(
                attr_name,
                len(channel["times"]),
                channel["max_raw_delta"],
                channel["discontinuity_count"],
                channel["long_spin_count"],
            )
        )

    if report["warnings"]:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(["- {0}".format(text) for text in report["warnings"]])

    if report["notes"]:
        lines.append("")
        lines.append("Notes:")
        lines.extend(["- {0}".format(text) for text in report["notes"]])
    return "\n".join(lines)


class MayaRotationDoctorController(object):
    def __init__(self):
        self.reports = []
        self.last_targets = []

    def shutdown(self):
        self.clear_reports()

    def clear_reports(self):
        self.reports = []
        self.last_targets = []

    def analysis_summary(self):
        if not self.reports:
            return "Pick one or more animated controls, then click Analyze Selected."
        issue_count = sum(1 for report in self.reports if report["recommended_recipe"])
        return "Checked {0} control(s); {1} probably need a fix.".format(len(self.reports), issue_count)

    def analyze_selection(self):
        targets = _selected_transform_targets()
        if not targets:
            self.clear_reports()
            return False, "Pick one or more animated controls first."
        return self.analyze_targets(targets)

    def analyze_targets(self, targets):
        reports = []
        for target in _dedupe_preserve_order(targets):
            if not cmds.objExists(target):
                continue
            if cmds.nodeType(target) not in SUPPORTED_TRANSFORM_TYPES:
                continue
            report = _build_report(target)
            if report:
                reports.append(report)

        self.reports = reports
        self.last_targets = [report["transform"] for report in reports]
        if not reports:
            return False, "No rotation keys were found on what you picked."
        return True, self.analysis_summary()

    def reports_for_indices(self, indices=None):
        if not self.reports:
            return []
        if not indices:
            return list(self.reports)
        valid = []
        for index in indices:
            if 0 <= index < len(self.reports):
                valid.append(self.reports[index])
        return valid

    def apply_recommended(self, reports=None):
        target_reports = reports or list(self.reports)
        actionable = [report for report in target_reports if report.get("recommended_recipe")]
        if not actionable:
            return False, "There is no fix to use from the current list."

        applied = []
        for report in actionable:
            success, _message = self._apply_recipe_to_reports(report["recommended_recipe"], [report])
            if success:
                applied.append(report["display_name"])
        if not applied:
            return False, "No fixes were applied."

        self._reanalyze_last_targets()
        return True, "Used the best fix on {0}.".format(", ".join(applied))

    def apply_recipe(self, recipe_name, reports=None):
        target_reports = reports or list(self.reports)
        return self._apply_recipe_to_reports(recipe_name, target_reports)

    def flip_current_key(self):
        keys = _selected_rotate_curve_keys()
        source = "selected Graph Editor key(s)"
        if not keys:
            keys = _current_frame_rotate_keys_for_selection()
            source = "current-frame rotation key(s)"
        if not keys:
            return False, "Select a rotate key in the Graph Editor, or select an animated control on a keyed frame."

        cmds.undoInfo(openChunk=True, chunkName="MayaRotationDoctor_flip_current_key_euler")
        try:
            changed = _fix_euler_keys(keys)
        except Exception as exc:
            _warning("Current key Euler flip failed: {0}".format(exc))
            _warning(traceback.format_exc())
            return False, "Current key flip failed: {0}".format(exc)
        finally:
            cmds.undoInfo(closeChunk=True)

        if not changed:
            return False, "The {0} already use the nearest safe Euler value.".format(source)

        self._reanalyze_last_targets()
        return True, "Flipped {0} Euler key(s) to the nearest safe value.".format(len(changed))

    def _apply_recipe_to_reports(self, recipe_name, reports):
        if recipe_name == "flip_current_key_euler":
            return self.flip_current_key()
        if not reports:
            return False, "Analyze some controls first."
        if recipe_name not in RECIPE_LABELS:
            return False, "Unknown recipe: {0}".format(recipe_name)

        supported_reports = [report for report in reports if report["supported"]]
        if not supported_reports:
            return False, "These controls use a curve setup this first version cannot edit yet."

        cmds.undoInfo(openChunk=True, chunkName="MayaRotationDoctor_{0}".format(recipe_name))
        try:
            if recipe_name == "clean_euler_discontinuity":
                self._apply_euler_cleanup(supported_reports)
            elif recipe_name == "preserve_spin_and_unroll":
                self._apply_preserve_spins(supported_reports)
            elif recipe_name == "switch_interp_to_synchronized_euler":
                self._apply_rotation_interpolation(supported_reports, "euler")
            elif recipe_name == "switch_interp_to_quaternion":
                self._apply_rotation_interpolation(supported_reports, "quaternion")
            elif recipe_name == "custom_continuity_pass":
                self._apply_custom_continuity(supported_reports, preserve_long_spins=False)
            else:
                raise RuntimeError("Unhandled recipe: {0}".format(recipe_name))
        except Exception as exc:
            _warning("Rotation Doctor recipe failed: {0}".format(exc))
            _warning(traceback.format_exc())
            return False, "Recipe failed: {0}".format(exc)
        finally:
            cmds.undoInfo(closeChunk=True)

        self._reanalyze_last_targets()
        return True, "Used {0} on {1} control(s).".format(RECIPE_LABELS[recipe_name], len(supported_reports))

    def _reanalyze_last_targets(self):
        if self.last_targets:
            self.analyze_targets(self.last_targets)

    def _report_curve_names(self, report):
        curve_names = []
        for attr_name in report["keyed_channels"]:
            curve_name = report["channels"][attr_name]["curve_name"]
            if curve_name:
                curve_names.append(curve_name)
        return _dedupe_preserve_order(curve_names)

    def _apply_euler_cleanup(self, reports):
        curve_names = []
        for report in reports:
            curve_names.extend(self._report_curve_names(report))
        curve_names = _dedupe_preserve_order(curve_names)
        if not curve_names:
            raise RuntimeError("No rotate curves were available for Euler cleanup.")
        cmds.filterCurve(curve_names, filter="euler")

    def _apply_preserve_spins(self, reports):
        self._apply_custom_continuity(reports, preserve_long_spins=True)

    def _apply_rotation_interpolation(self, reports, interpolation_name):
        if interpolation_name == "euler":
            invalid = [report["display_name"] for report in reports if not report.get("has_full_rotation_set")]
            if invalid:
                raise RuntimeError(
                    "This fix needs keys on all 3 rotation axes. Add the missing keys, then try again on: {0}".format(
                        ", ".join(invalid)
                    )
                )
        curve_names = []
        for report in reports:
            curve_names.extend(self._report_curve_names(report))
        curve_names = _dedupe_preserve_order(curve_names)
        if not curve_names:
            raise RuntimeError("No rotate curves were available for interpolation conversion.")
        cmds.rotationInterpolation(curve_names, convert=interpolation_name)

    def _apply_custom_continuity(self, reports, preserve_long_spins):
        for report in reports:
            for attr_name in report["keyed_channels"]:
                state = _channel_state(report["transform"], attr_name)
                if not state or not state["supported"]:
                    continue
                solved = _solve_continuity_values(state["values"], preserve_long_spins)
                if len(solved) != len(state["values"]):
                    continue
                for index, solved_value in enumerate(solved):
                    if abs(solved_value - state["values"][index]) <= VALUE_EPSILON:
                        continue
                    cmds.setKeyframe(
                        report["transform"],
                        attribute=attr_name,
                        time=(state["times"][index], state["times"][index]),
                        value=float(solved_value),
                    )


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

        if MQtUtil.mainWindow() is not None:
            _WindowBase = type("MayaRotationDoctorBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
        else:
            _WindowBase = type("MayaRotationDoctorBase", (QtWidgets.QDialog,), {})
    except Exception:
        _WindowBase = type("MayaRotationDoctorBase", (QtWidgets.QDialog,), {})


    class MayaRotationDoctorWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaRotationDoctorWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller

            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Rotation Doctor")
            self.setMinimumWidth(960)
            self.setMinimumHeight(620)
            self._build_ui()
            self._refresh_preview()

        def _build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.setContentsMargins(12, 12, 12, 12)
            main_layout.setSpacing(10)

            description = QtWidgets.QLabel(
                "This checks your rotation keys for flips, jumps, and twist problems before anything is changed."
            )
            description.setWordWrap(True)
            main_layout.addWidget(description)

            note = QtWidgets.QLabel(
                "Nothing changes until you press a fix button. The tool tries to keep big planned spins unless they look broken."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #B8D7FF;")
            main_layout.addWidget(note)

            button_grid = QtWidgets.QGridLayout()
            button_grid.setHorizontalSpacing(8)
            button_grid.setVerticalSpacing(8)

            self.analyze_button = QtWidgets.QPushButton("Analyze Selected")
            self.analyze_button.setToolTip("Check the selected controls and look for likely rotation problems.")
            self.apply_recommended_button = QtWidgets.QPushButton("Use Best Fix")
            self.apply_recommended_button.setToolTip("Apply the safest fix the tool recommends for the selected controls.")
            self.euler_cleanup_button = QtWidgets.QPushButton("Fix Flips")
            self.euler_cleanup_button.setToolTip("Fix the most common rotation flips and jumps.")
            self.flip_current_key_button = QtWidgets.QPushButton("Flip Current Key")
            self.flip_current_key_button.setToolTip(
                "Blender-style Euler flip for the selected Graph Editor rotate key, or the current keyed frame on selected controls."
            )
            self.preserve_spins_button = QtWidgets.QPushButton("Keep Big Spins")
            self.preserve_spins_button.setToolTip("Keep big planned spins while still cleaning obvious jumps.")
            self.sync_euler_button = QtWidgets.QPushButton("Smooth Euler")
            self.sync_euler_button.setToolTip("Keep using Euler, but make the rotation curves work together more smoothly.")
            self.quaternion_button = QtWidgets.QPushButton("Quaternion Mode")
            self.quaternion_button.setToolTip("Switch to safer rotation math that can avoid some flip problems.")
            self.custom_pass_button = QtWidgets.QPushButton("Extra Cleanup")
            self.custom_pass_button.setToolTip("Run the tool's extra cleanup pass for hard cases.")
            self.clear_button = QtWidgets.QPushButton("Clear List")
            self.clear_button.setToolTip("Clear the current analysis list.")

            button_grid.addWidget(self.analyze_button, 0, 0)
            button_grid.addWidget(self.apply_recommended_button, 0, 1)
            button_grid.addWidget(self.euler_cleanup_button, 0, 2)
            button_grid.addWidget(self.flip_current_key_button, 0, 3)
            button_grid.addWidget(self.preserve_spins_button, 0, 4)
            button_grid.addWidget(self.sync_euler_button, 1, 0)
            button_grid.addWidget(self.quaternion_button, 1, 1)
            button_grid.addWidget(self.custom_pass_button, 1, 2)
            button_grid.addWidget(self.clear_button, 1, 3)
            main_layout.addLayout(button_grid)

            split_layout = QtWidgets.QHBoxLayout()
            split_layout.setSpacing(10)

            self.report_tree = QtWidgets.QTreeWidget()
            self.report_tree.setRootIsDecorated(False)
            self.report_tree.setAlternatingRowColors(True)
            self.report_tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.report_tree.setColumnCount(5)
            self.report_tree.setHeaderLabels(
                ["Control", "Moved Axes", "Problem", "Best Fix", "Heads-Up"]
            )
            self.report_tree.header().setStretchLastSection(False)
            self.report_tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            self.report_tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            self.report_tree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            self.report_tree.header().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
            self.report_tree.header().setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
            split_layout.addWidget(self.report_tree, 3)

            self.detail_text = QtWidgets.QPlainTextEdit()
            self.detail_text.setReadOnly(True)
            split_layout.addWidget(self.detail_text, 2)
            main_layout.addLayout(split_layout, 1)

            self.status_label = QtWidgets.QLabel("Pick one or more animated controls, then click Analyze Selected.")
            self.status_label.setWordWrap(True)
            selectable_flag = _qt_flag("TextInteractionFlag", "TextSelectableByMouse", 0)
            self.status_label.setTextInteractionFlags(selectable_flag)
            main_layout.addWidget(self.status_label)

            footer_layout = QtWidgets.QHBoxLayout()
            footer_layout.setSpacing(8)

            self.brand_label = QtWidgets.QLabel(
                'Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL)
            )
            self.brand_label.setWordWrap(True)
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            footer_layout.addWidget(self.brand_label, 1)

            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.setToolTip(
                "Open Amir's PayPal donate link. Set AMIR_PAYPAL_DONATE_URL or AMIR_DONATE_URL to customize it."
            )
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

            self.analyze_button.clicked.connect(self._analyze_selection)
            self.apply_recommended_button.clicked.connect(self._apply_recommended)
            self.euler_cleanup_button.clicked.connect(lambda: self._apply_recipe("clean_euler_discontinuity"))
            self.flip_current_key_button.clicked.connect(lambda: self._apply_recipe("flip_current_key_euler"))
            self.preserve_spins_button.clicked.connect(lambda: self._apply_recipe("preserve_spin_and_unroll"))
            self.sync_euler_button.clicked.connect(lambda: self._apply_recipe("switch_interp_to_synchronized_euler"))
            self.quaternion_button.clicked.connect(lambda: self._apply_recipe("switch_interp_to_quaternion"))
            self.custom_pass_button.clicked.connect(lambda: self._apply_recipe("custom_continuity_pass"))
            self.clear_button.clicked.connect(self._clear_preview)
            self.report_tree.itemSelectionChanged.connect(self._update_detail_from_selection)
            self.donate_button.clicked.connect(self._open_donate_url)

        def _selected_report_indices(self):
            items = self.report_tree.selectedItems()
            if not items:
                return []
            user_role = _qt_flag("ItemDataRole", "UserRole", 0x0100)
            indices = []
            for item in items:
                try:
                    stored_index = item.data(0, user_role)
                except Exception:
                    stored_index = None
                if stored_index is None:
                    stored_index = self.report_tree.indexOfTopLevelItem(item)
                try:
                    stored_index = int(stored_index)
                except Exception:
                    continue
                if stored_index >= 0:
                    indices.append(stored_index)
            return sorted(set(indices))

        def _refresh_preview(self):
            self.report_tree.clear()
            user_role = _qt_flag("ItemDataRole", "UserRole", 0x0100)
            for report_index, report in enumerate(self.controller.reports):
                warning_text = "; ".join(report["warnings"][:2])
                item = QtWidgets.QTreeWidgetItem(
                    [
                        report["display_name"],
                        ", ".join(report["keyed_channels"]),
                        report["issue_type"],
                        RECIPE_LABELS.get(report["recommended_recipe"], "No change"),
                        warning_text,
                    ]
                )
                item.setData(0, user_role, int(report_index))
                item.setToolTip(4, warning_text)
                self.report_tree.addTopLevelItem(item)
            self.report_tree.sortItems(0, _qt_flag("SortOrder", "AscendingOrder", 0))
            self._update_detail_from_selection()

        def _set_status(self, message, success):
            self.status_label.setText(message)
            if success:
                _debug(message)
            else:
                _warning(message)

        def _update_detail_from_selection(self):
            indices = self._selected_report_indices()
            if not indices and self.controller.reports:
                self.report_tree.setCurrentItem(self.report_tree.topLevelItem(0))
                indices = self._selected_report_indices()
            if not indices:
                self.detail_text.setPlainText(
                    "Preview details will appear here after you analyze animated controls."
                )
                return
            report = self.controller.reports[indices[0]]
            self.detail_text.setPlainText(_report_detail_text(report))

        def _analyze_selection(self):
            success, message = self.controller.analyze_selection()
            self._refresh_preview()
            self._set_status(message, success)

        def _reports_for_apply(self):
            indices = self._selected_report_indices()
            reports = self.controller.reports_for_indices(indices)
            if reports:
                return reports
            return list(self.controller.reports)

        def _apply_recommended(self):
            success, message = self.controller.apply_recommended(self._reports_for_apply())
            self._refresh_preview()
            self._set_status(message, success)

        def _apply_recipe(self, recipe_name):
            success, message = self.controller.apply_recipe(recipe_name, self._reports_for_apply())
            self._refresh_preview()
            self._set_status(message, success)

        def _clear_preview(self):
            self.controller.clear_reports()
            self._refresh_preview()
            self._set_status("Cleared the current preview.", True)

        def _open_follow_url(self, url=None):
            target_url = url or FOLLOW_AMIR_URL
            if _open_external_url(target_url):
                self._set_status("Opened followamir.com.", True)
            else:
                self._set_status("Could not open followamir.com from this Maya session.", False)

        def _open_donate_url(self):
            if not DONATE_URL:
                self._set_status(
                    "Donate button is ready, but the PayPal link still needs to be configured via AMIR_PAYPAL_DONATE_URL.",
                    False,
                )
                return
            if _open_external_url(DONATE_URL):
                self._set_status("Opened Amir's donate link.", True)
            else:
                self._set_status("Could not open the donate link from this Maya session.", False)

        def closeEvent(self, event):
            global GLOBAL_CONTROLLER
            global GLOBAL_WINDOW

            try:
                self.controller.shutdown()
            finally:
                GLOBAL_CONTROLLER = None
                GLOBAL_WINDOW = None
            try:
                super(MayaRotationDoctorWindow, self).closeEvent(event)
            except TypeError:
                QtWidgets.QDialog.closeEvent(self, event)


def launch_maya_rotation_doctor(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW

    if not MAYA_AVAILABLE:
        raise RuntimeError("maya_rotation_doctor.launch_maya_rotation_doctor() must run inside Autodesk Maya.")
    if not QtWidgets:
        raise RuntimeError("PySide is not available in this Maya session.")

    _close_existing_window()

    GLOBAL_CONTROLLER = MayaRotationDoctorController()
    GLOBAL_WINDOW = MayaRotationDoctorWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())

    if dock:
        try:
            GLOBAL_WINDOW.show(dockable=True, floating=True, area="right")
        except Exception:
            GLOBAL_WINDOW.show()
    else:
        GLOBAL_WINDOW.show()

    GLOBAL_WINDOW.raise_()
    GLOBAL_WINDOW.activateWindow()
    return GLOBAL_WINDOW


def flip_current_euler_key():
    """Public command for shelves or Maya hotkeys."""
    if not MAYA_AVAILABLE:
        raise RuntimeError("maya_rotation_doctor.flip_current_euler_key() must run inside Autodesk Maya.")
    controller = MayaRotationDoctorController()
    success, message = controller.flip_current_key()
    if success:
        _debug(message)
    else:
        _warning(message)
    return success, message


__all__ = [
    "launch_maya_rotation_doctor",
    "flip_current_euler_key",
    "install_maya_rotation_doctor_shelf_button",
    "MayaRotationDoctorController",
]
