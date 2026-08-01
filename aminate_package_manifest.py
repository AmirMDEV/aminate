from __future__ import absolute_import, division, print_function


LICENSE_FILE_NAME = "LICENSE"
MANIFEST_FILE_NAME = "manifest.json"
TUTORIAL_FILE_NAME = "tutorial.html"
RELEASE_VERSION_LABEL = "Version 0.3.7"
RELEASE_TAG = "v0.3.7"
RELEASE_TAG_FILE_SAFE = RELEASE_TAG.replace(".", "_").replace("-", "_")
INSTALLER_RELEASE_NAME = "Aminate_{0}_drag_this_file_into_Maya.py".format(RELEASE_TAG_FILE_SAFE)
LEGACY_INSTALLER_RELEASE_NAME = "Aminate drag and drop this onto Maya viewport.py"
TUTORIAL_RELEASE_NAME = "Aminate_{0}_offline_tutorial.zip".format(RELEASE_TAG)
INSTALLER_RELEASE_NAMES = [
    INSTALLER_RELEASE_NAME,
    LEGACY_INSTALLER_RELEASE_NAME,
]
PUBLIC_REPO_URL = "https://github.com/AmirMDEV/aminate"
FOLLOW_AMIR_URL = "https://followamir.com"
DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"

RUNTIME_FILES = [
    "aminate.py",
    "aminate_package_manifest.py",
    "maya_animation_assistant.py",
    "maya_animation_styling.py",
    "maya_aminate_icon_manifest.py",
    "maya_animators_pencil.py",
    "maya_aminate_pencil_action_groups_bridge.py",
    "maya_aminate_pencil_view_video_bridge.py",
    "maya_aminate_customization.py",
    "maya_aminate_theme.py",
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

STATIC_DIRS = [
    "branding",
]
