from __future__ import absolute_import, division, print_function

import json
import os
import time

import maya_contact_hold as hold_utils

try:
    import maya.cmds as cmds
except Exception:
    cmds = None

try:
    import maya.utils as maya_utils
except Exception:
    maya_utils = None

try:
    from PySide2 import QtCore, QtWidgets
except Exception:
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:
        QtCore = QtWidgets = None


STATE_FILE_NAME = "maya_crash_recovery_state.json"
STATE_VERSION = 1
STATE_STALE_SECONDS = 7 * 24 * 60 * 60
USER_SETUP_BEGIN = "# >>> AmirAminate crash recovery >>>"
USER_SETUP_END = "# <<< AmirAminate crash recovery <<<"

_BOOTSTRAPPED = False
_SCRIPT_JOB_IDS = []
_ACTIVE_RECOVERY_DIALOG = None


def _module_root():
    return os.path.dirname(os.path.abspath(__file__))


def state_file_path():
    return os.path.join(_module_root(), STATE_FILE_NAME)


def _normalize_path(path_value):
    if not path_value:
        return ""
    return os.path.normpath(path_value).replace("\\", "/")


def _scene_path():
    if not cmds:
        return ""
    try:
        return _normalize_path(cmds.file(query=True, sceneName=True) or "")
    except Exception:
        return ""


def _workspace_root():
    if not cmds:
        return ""
    try:
        return _normalize_path(cmds.workspace(query=True, rootDirectory=True) or "")
    except Exception:
        return ""


def _autosave_directory():
    if not cmds:
        return ""
    try:
        path_value = cmds.autoSave(query=True, destinationFolder=True) or ""
        if path_value:
            return _normalize_path(path_value)
    except Exception:
        pass
    workspace_root = _workspace_root()
    if workspace_root:
        try:
            auto_save_rule = cmds.workspace(fileRuleEntry="autoSave") or ""
        except Exception:
            auto_save_rule = ""
        if auto_save_rule:
            if os.path.isabs(auto_save_rule):
                return _normalize_path(auto_save_rule)
            return _normalize_path(os.path.join(workspace_root, auto_save_rule))
        return _normalize_path(os.path.join(workspace_root, "autosave"))
    scene_path = _scene_path()
    if scene_path:
        return _normalize_path(os.path.join(os.path.dirname(scene_path), "autosave"))
    return ""


def _read_state():
    state_path = state_file_path()
    if not os.path.exists(state_path):
        return {"dirty": False, "version": STATE_VERSION}
    try:
        with open(state_path, "r") as handle:
            state = json.load(handle)
    except Exception:
        return {"dirty": False, "version": STATE_VERSION}
    if not isinstance(state, dict):
        return {"dirty": False, "version": STATE_VERSION}
    state.setdefault("dirty", False)
    state.setdefault("version", STATE_VERSION)
    return state


def _write_state(state):
    state_path = state_file_path()
    folder = os.path.dirname(state_path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    tmp_path = state_path + ".tmp"
    with open(tmp_path, "w") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
    os.replace(tmp_path, state_path)


def _candidate_autosave_paths(scene_path="", autosave_directory=""):
    scene_path = _normalize_path(scene_path or _scene_path())
    autosave_directory = _normalize_path(autosave_directory or _autosave_directory())
    search_dirs = []
    for directory in (autosave_directory,):
        if directory and os.path.isdir(directory) and directory not in search_dirs:
            search_dirs.append(directory)
    candidates = []
    scene_stem = os.path.splitext(os.path.basename(scene_path))[0].lower() if scene_path else ""
    for directory in search_dirs:
        try:
            for file_name in os.listdir(directory):
                full_path = _normalize_path(os.path.join(directory, file_name))
                if not os.path.isfile(full_path):
                    continue
                if not full_path.lower().endswith((".ma", ".mb")):
                    continue
                file_stem = os.path.splitext(os.path.basename(full_path))[0].lower()
                if scene_stem:
                    if file_stem == scene_stem or file_stem.startswith(scene_stem) or scene_stem in file_stem:
                        candidates.append(full_path)
                else:
                    candidates.append(full_path)
        except Exception:
            continue
    candidates = sorted(set(candidates), key=lambda path_value: os.path.getmtime(path_value), reverse=True)
    return candidates


def find_latest_autosave(scene_path="", autosave_directory=""):
    candidates = _candidate_autosave_paths(scene_path=scene_path, autosave_directory=autosave_directory)
    return candidates[0] if candidates else ""


def _capture_state(reason):
    scene_path = _scene_path()
    autosave_directory = _autosave_directory()
    latest_autosave = find_latest_autosave(scene_path=scene_path, autosave_directory=autosave_directory)
    return {
        "autosave_directory": autosave_directory,
        "dirty": True,
        "last_autosave_path": latest_autosave,
        "last_scene_label": os.path.basename(scene_path) if scene_path else "Untitled Scene",
        "pid": os.getpid(),
        "reason": reason,
        "scene_path": scene_path,
        "updated_at": time.time(),
        "version": STATE_VERSION,
    }


def mark_session_dirty(reason="session"):
    if not cmds:
        return False
    state = _read_state()
    state.update(_capture_state(reason))
    state["dirty"] = True
    _write_state(state)
    return True


def mark_session_clean(reason="quit"):
    if not cmds:
        return False
    state = _read_state()
    state.update(_capture_state(reason))
    state["dirty"] = False
    _write_state(state)
    return True


def recovery_candidate(previous_state=None, force=False, prefer_current_scene=False):
    state = dict(previous_state or _read_state())
    state_scene_path = _normalize_path(state.get("scene_path") or "")
    current_scene_path = _scene_path()
    scene_path = current_scene_path if prefer_current_scene and current_scene_path else state_scene_path or current_scene_path
    autosave_directory = _normalize_path(state.get("autosave_directory") or _autosave_directory())
    state_autosave_path = _normalize_path(state.get("last_autosave_path") or "")
    lookup_scene_path = scene_path or state_scene_path
    latest_autosave = find_latest_autosave(scene_path=lookup_scene_path, autosave_directory=autosave_directory)
    if not latest_autosave and state_autosave_path and os.path.exists(state_autosave_path):
        latest_autosave = state_autosave_path
    signature = "{0}|{1}".format(scene_path, latest_autosave)
    details = {
        "autosave_directory": autosave_directory,
        "autosave_path": latest_autosave,
        "scene_path": scene_path,
        "signature": signature,
        "state": state,
    }
    if not latest_autosave:
        return False, "Could not find a matching autosave file.", details
    if force:
        return True, "Latest autosave is ready.", details
    if not state.get("dirty"):
        return False, "No crash recovery is waiting right now.", details
    updated_at = float(state.get("updated_at") or 0.0)
    if updated_at and (time.time() - updated_at) > STATE_STALE_SECONDS:
        return False, "The old crash recovery state is too stale to trust.", details
    if _normalize_path(state.get("dismissed_signature") or "") == signature:
        return False, "Crash recovery was already dismissed for this autosave.", details
    return True, "Crash recovery is ready.", details


def open_autosave(path_value):
    if not cmds or not path_value or not os.path.exists(path_value):
        return False, "Autosave file not found."
    try:
        cmds.file(path_value, open=True, force=True, prompt=False)
        mark_session_dirty("recovered_autosave")
        state = _read_state()
        state["dismissed_signature"] = ""
        _write_state(state)
        return True, "Opened autosave: {0}".format(os.path.basename(path_value))
    except Exception as exc:
        return False, "Could not open autosave: {0}".format(exc)


def _execute_message_box(dialog):
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def _show_recovery_dialog(scene_path, autosave_path, auto_dismiss_response=None, auto_dismiss_delay_ms=0):
    global _ACTIVE_RECOVERY_DIALOG
    dialog = QtWidgets.QMessageBox(hold_utils._maya_main_window())
    dialog.setObjectName("mayaCrashRecoveryDialog")
    dialog.setWindowTitle("Recover Last Autosave?")
    dialog.setIcon(QtWidgets.QMessageBox.Question)
    dialog.setText(
        "Maya looks like it may have closed unexpectedly.\n\n"
        "Open the latest autosave now?\n\n"
        "Scene: {0}\n"
        "Autosave: {1}".format(os.path.basename(scene_path) or "Untitled Scene", autosave_path)
    )
    dialog.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
    dialog.setDefaultButton(QtWidgets.QMessageBox.Yes)
    dialog.setEscapeButton(QtWidgets.QMessageBox.No)
    dialog.setModal(True)
    if auto_dismiss_response and QtCore:
        response_value = QtWidgets.QMessageBox.Yes if str(auto_dismiss_response).lower().startswith("y") else QtWidgets.QMessageBox.No
        QtCore.QTimer.singleShot(max(int(auto_dismiss_delay_ms or 0), 1), lambda: dialog.done(response_value))
    _ACTIVE_RECOVERY_DIALOG = dialog
    try:
        return _execute_message_box(dialog)
    finally:
        _ACTIVE_RECOVERY_DIALOG = None


def recover_last_autosave(
    prompt=True,
    force=False,
    prefer_current_scene=False,
    previous_state=None,
    auto_dismiss_response=None,
    auto_dismiss_delay_ms=0,
):
    ready, message, details = recovery_candidate(
        previous_state=previous_state,
        force=force,
        prefer_current_scene=prefer_current_scene,
    )
    if not ready:
        return False, message, details
    autosave_path = details.get("autosave_path") or ""
    scene_path = details.get("scene_path") or ""
    if prompt and QtWidgets:
        response = _show_recovery_dialog(
            scene_path,
            autosave_path,
            auto_dismiss_response=auto_dismiss_response,
            auto_dismiss_delay_ms=auto_dismiss_delay_ms,
        )
        if response != QtWidgets.QMessageBox.Yes:
            state = _read_state()
            state["dismissed_signature"] = details.get("signature") or ""
            _write_state(state)
            return False, "Recovery cancelled.", details
    success, open_message = open_autosave(autosave_path)
    return success, open_message, details


def prompt_recover_after_crash(previous_state=None):
    return recover_last_autosave(prompt=True, force=False, prefer_current_scene=False, previous_state=previous_state)


def _register_script_job(event_name, callback):
    if not cmds:
        return
    try:
        job_id = cmds.scriptJob(event=[event_name, callback], protected=True)
    except Exception:
        return
    _SCRIPT_JOB_IDS.append(job_id)


def bootstrap_crash_recovery(startup_prompt=True):
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED or not cmds:
        return False, "Crash recovery is already active."
    previous_state = _read_state()
    mark_session_dirty("startup")
    _register_script_job("quitApplication", lambda: mark_session_clean("quit"))
    _register_script_job("SceneOpened", lambda: mark_session_dirty("scene_opened"))
    _register_script_job("SceneSaved", lambda: mark_session_dirty("scene_saved"))
    _register_script_job("NewSceneOpened", lambda: mark_session_dirty("new_scene"))
    _register_script_job("PostSceneRead", lambda: mark_session_dirty("post_scene_read"))
    _BOOTSTRAPPED = True
    if startup_prompt:
        if maya_utils:
            maya_utils.executeDeferred(lambda: prompt_recover_after_crash(previous_state))
        else:
            prompt_recover_after_crash(previous_state)
    return True, "Crash recovery is active."
