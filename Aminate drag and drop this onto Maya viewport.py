from __future__ import absolute_import, division, print_function

import json
import os
import shutil
import sys
import traceback


PACKAGE_FOLDER_NAME = "Aminate"
PAYLOAD_DIR_NAME = "aminate_package"
DEFAULT_MANIFEST_FILE_NAME = "manifest.json"
DEFAULT_RUNTIME_FILES = [
    "aminate.py",
    "aminate_package_manifest.py",
    "maya_aminate_customization.py",
    "maya_aminate_theme.py",
    "maya_animation_assistant.py",
    "maya_animation_styling.py",
    "maya_aminate_icon_manifest.py",
    "maya_aminate_pencil_action_groups_bridge.py",
    "maya_aminate_pencil_view_video_bridge.py",
    "maya_animators_pencil.py",
    "maya_contact_hold.py",
    "maya_control_picker.py",
    "maya_crash_recovery.py",
    "maya_dynamic_parent_pivot.py",
    "maya_dynamic_parenting_tool.py",
    "maya_face_retarget.py",
    "maya_floating_channel_box.py",
    "maya_history_timeline.py",
    "maya_onion_skin.py",
    "maya_reference_manager.py",
    "maya_rig_scale_export.py",
    "maya_selected_animation_fbx_export.py",
    "maya_rotation_doctor.py",
    "maya_shelf_utils.py",
    "maya_skin_transfer.py",
    "maya_skinning_cleanup.py",
    "maya_smear_frames.py",
    "maya_surface_contact.py",
    "maya_timeline_notes.py",
    "maya_timing_tools.py",
    "maya_universal_ikfk_switcher.py",
    "maya_video_reference_tool.py",
    "combine_freeze_pivot_icon.png",
    "game_animation_mode_icon.png",
    "aminate_icon.png",
    "toolkit_bake_twos_icon.png",
    "toolkit_clean_static_icon.png",
    "toolkit_cut_key_icon.png",
    "toolkit_insert_inbetween_icon.png",
    "toolkit_nudge_left_icon.png",
    "toolkit_nudge_right_icon.png",
    "toolkit_package_zip_icon.png",
    "toolkit_reset_pose_icon.png",
    "toolkit_select_animated_icon.png",
    "toolkit_tween_machine_icon.png",
]
DEFAULT_STATIC_DIRS = [
    "branding",
]


def _managed_user_setup_block(destination_root):
    return "\n".join(
        [
            "try:",
            "    import sys",
            "    import os",
            "    import maya.cmds as _amir_maya_cmds",
            "    import maya.utils as _amir_maya_utils",
            "    _amir_workflow_root = r\"{0}\"".format(destination_root),
            "    def _amir_workflow_prepare_runtime():",
            "        try:",
            "            while _amir_workflow_root in sys.path:",
            "                sys.path.remove(_amir_workflow_root)",
            "            sys.path.insert(0, _amir_workflow_root)",
            "        except Exception:",
            "            pass",
            "    _amir_workflow_prepare_runtime()",
            "    def _amir_workflow_schedule(function, delay_ms=1000):",
            "        try:",
            "            from PySide6 import QtCore as _amir_qt_core",
            "        except Exception:",
            "            try:",
            "                from PySide2 import QtCore as _amir_qt_core",
            "            except Exception:",
            "                _amir_qt_core = None",
            "        if _amir_qt_core:",
            "            _amir_qt_core.QTimer.singleShot(int(delay_ms), function)",
            "        else:",
            "            _amir_maya_utils.executeDeferred(function)",
            "    def _amir_workflow_main_window_ready():",
            "        try:",
            "            import maya.OpenMayaUI as _amir_omui",
            "            if _amir_omui.MQtUtil.mainWindow() is None:",
            "                return False",
            "        except Exception:",
            "            return False",
            "        try:",
            "            return bool(_amir_maya_cmds.window('MayaWindow', exists=True))",
            "        except Exception:",
            "            return False",
            "    def _amir_workflow_bootstrap_startup():",
            "        if getattr(sys, '_aminate_startup_bootstrapped_root', '') == _amir_workflow_root:",
            "            return",
            "        sys._aminate_startup_bootstrapped = True",
            "        sys._aminate_startup_bootstrapped_root = _amir_workflow_root",
            "        _amir_workflow_prepare_runtime()",
            "        try:",
            "            import maya_crash_recovery as _amir_maya_crash_recovery",
            "            _amir_maya_crash_recovery.bootstrap_crash_recovery(startup_prompt=True)",
            "        except Exception:",
            "            pass",
            "        if os.environ.get('AMINATE_AUTO_OPEN_ON_MAYA_STARTUP') == '1':",
            "            try:",
            "                import aminate as _amir_aminate",
            "                _amir_aminate.launch_aminate(dock=True, initial_tab='quick_start')",
            "            except Exception:",
            "                pass",
            "    def _amir_workflow_wait_for_startup(attempt=0):",
            "        if int(attempt) >= 8 and _amir_workflow_main_window_ready():",
            "            _amir_workflow_bootstrap_startup()",
            "            return",
            "        if int(attempt) < 120:",
            "            _amir_workflow_schedule(lambda: _amir_workflow_wait_for_startup(int(attempt) + 1), 1000)",
            "    _amir_maya_utils.executeDeferred(lambda: _amir_workflow_wait_for_startup(0))",
            "except Exception:",
            "    pass",
        ]
    )


def _upsert_block(text_value, begin_marker, end_marker, block_body):
    managed_block = "{0}\n{1}\n{2}\n".format(begin_marker, block_body.rstrip(), end_marker)
    if begin_marker in text_value and end_marker in text_value:
        prefix, remainder = text_value.split(begin_marker, 1)
        _, suffix = remainder.split(end_marker, 1)
        updated = prefix.rstrip() + "\n\n" + managed_block + suffix.lstrip("\r\n")
        return updated
    if text_value and not text_value.endswith(("\n", "\r")):
        text_value += "\n"
    if text_value:
        text_value += "\n"
    return text_value + managed_block


def _ensure_user_setup_hook(cmds, destination_root):
    import maya_crash_recovery

    scripts_dir = cmds.internalVar(userScriptDir=True)
    user_setup_path = os.path.join(scripts_dir, "userSetup.py")
    existing_text = ""
    if os.path.exists(user_setup_path):
        with open(user_setup_path, "r") as handle:
            existing_text = handle.read()
    updated_text = _upsert_block(
        existing_text,
        maya_crash_recovery.USER_SETUP_BEGIN,
        maya_crash_recovery.USER_SETUP_END,
        _managed_user_setup_block(destination_root),
    )
    if updated_text != existing_text:
        with open(user_setup_path, "w") as handle:
            handle.write(updated_text)


def _maya_api():
    import maya.cmds as cmds  # type: ignore

    return cmds


def _source_root():
    here = os.path.dirname(os.path.abspath(__file__))
    packaged_root = os.path.join(here, PAYLOAD_DIR_NAME)
    if os.path.isdir(packaged_root):
        return packaged_root
    return here


def _load_manifest(source_root):
    manifest_path = os.path.join(source_root, DEFAULT_MANIFEST_FILE_NAME)
    if not os.path.exists(manifest_path):
        sibling_manifest = os.path.join(os.path.dirname(source_root), DEFAULT_MANIFEST_FILE_NAME)
        if os.path.exists(sibling_manifest):
            manifest_path = sibling_manifest
    if not os.path.exists(manifest_path):
        try:
            from aminate_package_manifest import (
                MANIFEST_FILE_NAME as package_manifest_file_name,
                RELEASE_VERSION_LABEL,
                RUNTIME_FILES,
                STATIC_DIRS,
            )
            return {
                "package_name": PACKAGE_FOLDER_NAME,
                "version": RELEASE_VERSION_LABEL,
                "runtime_files": list(RUNTIME_FILES),
                "static_dirs": list(STATIC_DIRS),
                "manifest_file_name": package_manifest_file_name,
            }
        except Exception:
            pass
        return {
            "package_name": PACKAGE_FOLDER_NAME,
            "version": "dev",
            "runtime_files": list(DEFAULT_RUNTIME_FILES),
            "static_dirs": list(DEFAULT_STATIC_DIRS),
        }
    with open(manifest_path, "r") as handle:
        return json.load(handle)


def _install_root(cmds):
    scripts_dir = cmds.internalVar(userScriptDir=True)
    return os.path.join(scripts_dir, PACKAGE_FOLDER_NAME)


def _same_path(left, right):
    """Return True when two paths resolve to the same file-system entry."""
    try:
        return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
            os.path.realpath(right)
        )
    except (OSError, TypeError):
        return False


def _copy_runtime_files(source_root, destination_root, runtime_files):
    if not os.path.isdir(destination_root):
        os.makedirs(destination_root)
    for file_name in runtime_files:
        source_path = os.path.join(source_root, file_name)
        if not os.path.exists(source_path):
            raise RuntimeError("Missing runtime file in installer payload: {0}".format(file_name))
        destination_path = os.path.join(destination_root, file_name)
        if not _same_path(source_path, destination_path):
            shutil.copy2(source_path, destination_path)
    manifest_path = os.path.join(source_root, DEFAULT_MANIFEST_FILE_NAME)
    if not os.path.exists(manifest_path):
        sibling_manifest = os.path.join(os.path.dirname(source_root), DEFAULT_MANIFEST_FILE_NAME)
        if os.path.exists(sibling_manifest):
            manifest_path = sibling_manifest
    if os.path.exists(manifest_path):
        destination_path = os.path.join(destination_root, DEFAULT_MANIFEST_FILE_NAME)
        if not _same_path(manifest_path, destination_path):
            shutil.copy2(manifest_path, destination_path)


def _copy_static_dirs(source_root, destination_root, static_dirs):
    if not os.path.isdir(destination_root):
        os.makedirs(destination_root)
    for dir_name in static_dirs:
        source_path = os.path.join(source_root, dir_name)
        if not os.path.isdir(source_path):
            raise RuntimeError("Missing static directory in installer payload: {0}".format(dir_name))
        destination_path = os.path.join(destination_root, dir_name)
        if _same_path(source_path, destination_path):
            continue
        if os.path.isdir(destination_path):
            shutil.rmtree(destination_path)
        shutil.copytree(source_path, destination_path)


def _copy_installer_files(source_root, destination_root, manifest):
    package_root = os.path.dirname(source_root) if os.path.basename(source_root) == PAYLOAD_DIR_NAME else source_root
    installer_files = list(manifest.get("installer_files") or [])
    current_path = os.path.abspath(__file__)
    current_name = os.path.basename(current_path)
    if current_name not in installer_files:
        installer_files.insert(0, current_name)
    for file_name in installer_files:
        source_path = os.path.join(package_root, file_name)
        if not os.path.exists(source_path) and file_name == current_name:
            source_path = current_path
        if not os.path.exists(source_path):
            continue
        destination_path = os.path.join(destination_root, file_name)
        if not _same_path(source_path, destination_path):
            shutil.copy2(source_path, destination_path)


def install_aminate_from_dragdrop():
    cmds = _maya_api()
    source_root = _source_root()
    manifest = _load_manifest(source_root)
    runtime_files = manifest.get("runtime_files") or list(DEFAULT_RUNTIME_FILES)
    static_dirs = manifest.get("static_dirs") or list(DEFAULT_STATIC_DIRS)
    destination_root = _install_root(cmds)
    _copy_runtime_files(source_root, destination_root, runtime_files)
    _copy_static_dirs(source_root, destination_root, static_dirs)
    _copy_installer_files(source_root, destination_root, manifest)

    while destination_root in sys.path:
        sys.path.remove(destination_root)
    sys.path.insert(0, destination_root)

    aminate = sys.modules.get("aminate")
    restart_required = aminate is not None
    if aminate is None:
        import aminate

    if os.environ.get("AMINATE_ENABLE_STARTUP_RECOVERY") == "1":
        import maya_crash_recovery
        _ensure_user_setup_hook(cmds, destination_root)
        maya_crash_recovery.bootstrap_crash_recovery(startup_prompt=False)
    button_name = aminate.install_aminate_shelf_button(repo_path=destination_root)
    window = None
    if not restart_required:
        window = aminate.launch_aminate(dock=True, initial_tab="quick_start")
    version = manifest.get("version") or "unknown"
    install_message = 'Installed <hl>Aminate</hl> {0}'.format(version)
    if restart_required:
        install_message += '. Restart Maya before reopening Aminate.'
    cmds.inViewMessage(
        amg=install_message,
        pos="midCenterTop",
        fade=True,
    )
    return {
        "button_name": button_name,
        "destination_root": destination_root,
        "version": version,
        "window_title": window.windowTitle() if window else "",
        "restart_required": restart_required,
    }


def _evict_this_drop_module():
    module_name = globals().get("__name__", "")
    if module_name and module_name != "__main__":
        sys.modules.pop(module_name, None)


def onMayaDroppedPythonFile(*_args):
    try:
        result = install_aminate_from_dragdrop()
        print("AMINATE_DRAGDROP_INSTALL: {0}".format(json.dumps(result, sort_keys=True)))
    except Exception:
        traceback.print_exc()
        raise
    finally:
        _evict_this_drop_module()


if __name__ == "__main__":
    try:
        result = install_aminate_from_dragdrop()
        print("AMINATE_DRAGDROP_INSTALL: {0}".format(json.dumps(result, sort_keys=True)))
    except Exception:
        traceback.print_exc()
        raise
