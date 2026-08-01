"""
aminate.py

Canonical entrypoint for the combined Aminate UI.
"""

from __future__ import absolute_import, division, print_function

import importlib
import os
import sys

import maya_dynamic_parent_pivot as _impl  # noqa: F401
import maya_crash_recovery as _crash_recovery  # noqa: F401


_WORKFLOW_MODULE_NAMES = (
    "maya_dynamic_parenting_tool",
    "maya_contact_hold",
    "maya_crash_recovery",
    "maya_animators_pencil",
    "maya_animation_assistant",
    "maya_animation_styling",
    "maya_control_picker",
    "maya_face_retarget",
    "maya_floating_channel_box",
    "maya_history_timeline",
    "maya_reference_manager",
    "maya_surface_contact",
    "maya_timing_tools",
    "maya_onion_skin",
    "maya_rotation_doctor",
    "maya_skin_transfer",
    "maya_skinning_cleanup",
    "maya_rig_scale_export",
    "maya_video_reference_tool",
    "maya_timeline_notes",
    "maya_aminate_customization",
    "maya_smear_frames",
    "maya_dynamic_parent_pivot",
)


_MODULE_ROOT = os.path.dirname(os.path.abspath(__file__))


def _force_own_root_first():
    while _MODULE_ROOT in sys.path:
        sys.path.remove(_MODULE_ROOT)
    sys.path.insert(0, _MODULE_ROOT)
    importlib.invalidate_caches()


def _dev_reload_enabled():
    return os.environ.get("AMINATE_DEV_RELOAD_MODULES") == "1"


def _refresh_modules(force=False):
    _force_own_root_first()
    if force or _dev_reload_enabled():
        raise RuntimeError("Aminate live module reload is disabled. Restart Maya to load changed runtime files safely.")
    return _impl


def _reloaded_impl():
    return _refresh_modules()


DEFAULT_SHELF_BUTTON_LABEL = _impl.DEFAULT_SHELF_BUTTON_LABEL
DEFAULT_SHELF_NAME = _impl.DEFAULT_SHELF_NAME
DONATE_URL = _impl.DONATE_URL
FOLLOW_AMIR_URL = _impl.FOLLOW_AMIR_URL
AminateController = _impl.AminateController
AminateWindow = _impl.AminateWindow
SHELF_BUTTON_DOC_TAG = _impl.SHELF_BUTTON_DOC_TAG


def launch_aminate(dock=True, initial_tab="quick_start"):
    impl = _reloaded_impl()
    try:
        _crash_recovery.bootstrap_crash_recovery(startup_prompt=False)
    except Exception:
        pass
    # ``dock`` remains in the public signature so old shelf buttons keep
    # working, but the main Aminate panel is permanently docked.  Forwarding
    # a literal True adds a second safety layer if the implementation changes.
    return impl.launch_maya_dynamic_parent_pivot(dock=True, initial_tab=initial_tab)


def install_aminate_shelf_button(
    shelf_name=DEFAULT_SHELF_NAME,
    button_label=DEFAULT_SHELF_BUTTON_LABEL,
    repo_path=None,
):
    impl = _reloaded_impl()
    return impl.install_maya_dynamic_parent_pivot_shelf_button(
        shelf_name=shelf_name,
        button_label=button_label,
        repo_path=repo_path,
    )


__all__ = [
    "DEFAULT_SHELF_BUTTON_LABEL",
    "DEFAULT_SHELF_NAME",
    "DONATE_URL",
    "FOLLOW_AMIR_URL",
    "AminateController",
    "AminateWindow",
    "SHELF_BUTTON_DOC_TAG",
    "install_aminate_shelf_button",
    "launch_aminate",
]
