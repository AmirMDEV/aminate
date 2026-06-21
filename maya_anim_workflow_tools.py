"""
maya_anim_workflow_tools.py

Canonical entrypoint for the combined Aminate UI.
"""

from __future__ import absolute_import, division, print_function

import importlib
import os
import sys

import maya_dynamic_parent_pivot as _impl  # noqa: F401
import maya_dynamic_parenting_tool as _parenting  # noqa: F401
import maya_contact_hold as _contact_hold  # noqa: F401
import maya_crash_recovery as _crash_recovery  # noqa: F401
import maya_animators_pencil as _animators_pencil  # noqa: F401
import maya_animation_assistant as _animation_assistant  # noqa: F401
import maya_animation_styling as _animation_styling  # noqa: F401
import maya_control_picker as _control_picker  # noqa: F401
import maya_face_retarget as _face_retarget  # noqa: F401
import maya_floating_channel_box as _floating_channel_box  # noqa: F401
import maya_history_timeline as _history_timeline  # noqa: F401
import maya_reference_manager as _reference_manager  # noqa: F401
import maya_surface_contact as _surface_contact  # noqa: F401
import maya_timing_tools as _timing_tools  # noqa: F401
import maya_onion_skin as _onion  # noqa: F401
import maya_rotation_doctor as _rotation  # noqa: F401
import maya_skin_transfer as _skin_transfer  # noqa: F401
import maya_skinning_cleanup as _skin  # noqa: F401
import maya_rig_scale_export as _rig_scale  # noqa: F401
import maya_video_reference_tool as _video_reference  # noqa: F401
import maya_timeline_notes as _timeline_notes  # noqa: F401
import maya_aminate_customization as _customization  # noqa: F401
import maya_smear_frames as _smear_frames  # noqa: F401


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


def _close_loaded_workflow_ui():
    for module_name in ("maya_dynamic_parent_pivot", "maya_anim_workflow_tools"):
        module = sys.modules.get(module_name)
        if not module:
            continue
        impl = getattr(module, "_impl", module)
        close_fn = getattr(impl, "_close_existing_window", None)
        if close_fn:
            try:
                close_fn()
            except Exception:
                pass


def _force_own_root_first():
    while _MODULE_ROOT in sys.path:
        sys.path.remove(_MODULE_ROOT)
    sys.path.insert(0, _MODULE_ROOT)
    importlib.invalidate_caches()


def _dev_reload_enabled():
    return os.environ.get("AMINATE_DEV_RELOAD_MODULES") == "1"


def _refresh_modules(force=False):
    global _parenting, _contact_hold, _animators_pencil, _animation_assistant, _animation_styling, _control_picker, _face_retarget, _floating_channel_box, _history_timeline, _reference_manager, _surface_contact
    global _timing_tools, _onion, _rotation, _skin_transfer, _skin, _rig_scale, _video_reference, _timeline_notes, _customization, _smear_frames
    global _crash_recovery, _impl
    _force_own_root_first()
    if not (force or _dev_reload_enabled()):
        return _impl
    _close_loaded_workflow_ui()
    for module_name in _WORKFLOW_MODULE_NAMES:
        sys.modules.pop(module_name, None)
    _parenting = importlib.import_module("maya_dynamic_parenting_tool")
    _contact_hold = importlib.import_module("maya_contact_hold")
    _crash_recovery = importlib.import_module("maya_crash_recovery")
    _animators_pencil = importlib.import_module("maya_animators_pencil")
    _animation_assistant = importlib.import_module("maya_animation_assistant")
    _animation_styling = importlib.import_module("maya_animation_styling")
    _control_picker = importlib.import_module("maya_control_picker")
    _face_retarget = importlib.import_module("maya_face_retarget")
    _floating_channel_box = importlib.import_module("maya_floating_channel_box")
    _history_timeline = importlib.import_module("maya_history_timeline")
    _reference_manager = importlib.import_module("maya_reference_manager")
    _surface_contact = importlib.import_module("maya_surface_contact")
    _timing_tools = importlib.import_module("maya_timing_tools")
    _onion = importlib.import_module("maya_onion_skin")
    _rotation = importlib.import_module("maya_rotation_doctor")
    _skin_transfer = importlib.import_module("maya_skin_transfer")
    _skin = importlib.import_module("maya_skinning_cleanup")
    _rig_scale = importlib.import_module("maya_rig_scale_export")
    _video_reference = importlib.import_module("maya_video_reference_tool")
    _timeline_notes = importlib.import_module("maya_timeline_notes")
    _customization = importlib.import_module("maya_aminate_customization")
    _smear_frames = importlib.import_module("maya_smear_frames")
    _impl = importlib.import_module("maya_dynamic_parent_pivot")
    global DEFAULT_SHELF_BUTTON_LABEL, DEFAULT_SHELF_NAME, DONATE_URL, FOLLOW_AMIR_URL
    global MayaAnimWorkflowController, MayaAnimWorkflowWindow, SHELF_BUTTON_DOC_TAG
    DEFAULT_SHELF_BUTTON_LABEL = _impl.DEFAULT_SHELF_BUTTON_LABEL
    DEFAULT_SHELF_NAME = _impl.DEFAULT_SHELF_NAME
    DONATE_URL = _impl.DONATE_URL
    FOLLOW_AMIR_URL = _impl.FOLLOW_AMIR_URL
    MayaAnimWorkflowController = _impl.MayaAnimWorkflowController
    MayaAnimWorkflowWindow = _impl.MayaAnimWorkflowWindow
    SHELF_BUTTON_DOC_TAG = _impl.SHELF_BUTTON_DOC_TAG
    return _impl


def _reloaded_impl():
    return _refresh_modules()


DEFAULT_SHELF_BUTTON_LABEL = _impl.DEFAULT_SHELF_BUTTON_LABEL
DEFAULT_SHELF_NAME = _impl.DEFAULT_SHELF_NAME
DONATE_URL = _impl.DONATE_URL
FOLLOW_AMIR_URL = _impl.FOLLOW_AMIR_URL
MayaAnimWorkflowController = _impl.MayaAnimWorkflowController
MayaAnimWorkflowWindow = _impl.MayaAnimWorkflowWindow
SHELF_BUTTON_DOC_TAG = _impl.SHELF_BUTTON_DOC_TAG


def launch_maya_anim_workflow_tools(dock=True, initial_tab="quick_start"):
    impl = _reloaded_impl()
    try:
        _crash_recovery.bootstrap_crash_recovery(startup_prompt=False)
    except Exception:
        pass
    return impl.launch_maya_dynamic_parent_pivot(dock=dock, initial_tab=initial_tab)


def install_maya_anim_workflow_tools_shelf_button(
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
    "MayaAnimWorkflowController",
    "MayaAnimWorkflowWindow",
    "SHELF_BUTTON_DOC_TAG",
    "install_maya_anim_workflow_tools_shelf_button",
    "launch_maya_anim_workflow_tools",
]
