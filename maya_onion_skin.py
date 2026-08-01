"""
maya_onion_skin.py

Lightweight onion-skin previews for Maya 2022-2026.
"""

from __future__ import absolute_import, division, print_function

import json
import math
import os
import time
import traceback
import hashlib
import tempfile
import glob

import maya_shelf_utils

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    import maya.OpenMayaUI as omui
    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
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


WINDOW_OBJECT_NAME = "mayaOnionSkinWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
ROOT_GROUP_NAME = "mayaOnionSkinGhosts_GRP"
PREFIX = "mayaOnionSkin"
SILHOUETTE_PREFIX = "mayaOnionSilhouette"
MAX_FRAMES_PER_SIDE = 48
MAX_FRAME_STEP = 12
DEFAULT_PAST_FRAMES = 3
DEFAULT_FUTURE_FRAMES = 3
DEFAULT_FRAME_STEP = 1
DEFAULT_OPACITY = 0.55
DEFAULT_FALLOFF = 1.35
DEFAULT_FULL_FIDELITY_SCRUB = False
DEFAULT_PAST_COLOR = (0.25, 0.7, 1.0)
DEFAULT_FUTURE_COLOR = (1.0, 0.55, 0.2)
MODE_3D_GHOST = "3d_ghost"
MODE_FAST_SILHOUETTE = "fast_silhouette"
MODE_ITEMS = [
    ("3D Ghost", MODE_3D_GHOST),
    ("Fast Silhouette (Live + Refine)", MODE_FAST_SILHOUETTE),
]
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
AUTO_UPDATE_INTERVAL_MS = 33
SCRUB_SETTLE_DELAY_MS = 140
SCRUB_PREVIEW_MAX_OFFSETS = 8
SCRUB_PREVIEW_MAX_MESHES = 24
FAST_SILHOUETTE_LIVE_RESOLUTION = (640, 360)
FAST_SILHOUETTE_REFINE_RESOLUTION = (1280, 720)
FAST_SILHOUETTE_LIVE_CAPTURE_BUDGET = 3
CAMERA_POLL_INTERVAL_MS = 80
DEFORMER_NODE_TYPES = set(
    [
        "skinCluster",
        "blendShape",
        "cluster",
        "lattice",
        "wire",
        "sculpt",
        "nonLinear",
        "deltaMush",
        "wrap",
        "ffd",
        "jiggle",
        "shrinkWrap",
    ]
)
PROXY_NAME_TOKENS = ("proxy", "guide", "gizmo")
DEFAULT_SHELF_NAME = maya_shelf_utils.DEFAULT_SHELF_NAME
DEFAULT_SHELF_BUTTON_LABEL = "Onion Skin"
SHELF_BUTTON_DOC_TAG = "mayaOnionSkinShelfButton"

OPTION_KEYS = {
    "display_mode": "mayaOnionSkin_displayMode",
    "past_frames": "mayaOnionSkin_pastFrames",
    "future_frames": "mayaOnionSkin_futureFrames",
    "frame_step": "mayaOnionSkin_frameStep",
    "opacity": "mayaOnionSkin_opacity",
    "falloff": "mayaOnionSkin_falloff",
    "auto_update": "mayaOnionSkin_autoUpdate",
    "full_fidelity_scrub": "mayaOnionSkin_fullFidelityScrub",
    "past_color": "mayaOnionSkin_pastColor",
    "future_color": "mayaOnionSkin_futureColor",
}

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


def _debug(message):
    if MAYA_AVAILABLE:
        om.MGlobal.displayInfo("[Maya Onion Skin] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE:
        om.MGlobal.displayWarning("[Maya Onion Skin] {0}".format(message))


def _clamp(value, low, high):
    return max(low, min(high, value))


def _dedupe_preserve_order(items):
    deduped = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _lerp_color(start, end, alpha):
    return tuple((start[index] * (1.0 - alpha)) + (end[index] * alpha) for index in range(3))


def _safe_delete(node_name):
    if MAYA_AVAILABLE and node_name and cmds.objExists(node_name):
        cmds.delete(node_name)


def _unlock_and_disconnect_attr(attr_name):
    if not (MAYA_AVAILABLE and attr_name and cmds.objExists(attr_name)):
        return

    try:
        incoming = cmds.listConnections(attr_name, source=True, destination=False, plugs=True) or []
        for source_attr in incoming:
            try:
                cmds.disconnectAttr(source_attr, attr_name)
            except Exception:
                pass
    except Exception:
        pass

    try:
        cmds.setAttr(attr_name, lock=False)
    except Exception:
        pass


def _shape_color(button, color):
    if not button or not QtWidgets:
        return
    rgb_255 = [int(_clamp(channel, 0.0, 1.0) * 255.0) for channel in color]
    button.setStyleSheet(
        "QPushButton {{ background-color: rgb({0}, {1}, {2}); color: black; }}".format(*rgb_255)
    )
    button.setText("{0:.2f}, {1:.2f}, {2:.2f}".format(*color))


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


def _qt_flag(scope_name, member_name, fallback=None):
    if not QtCore:
        return fallback
    if hasattr(QtCore.Qt, member_name):
        return getattr(QtCore.Qt, member_name)
    scoped_enum = getattr(QtCore.Qt, scope_name, None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return fallback


def _serialize_color(color):
    return json.dumps([float(channel) for channel in color])


def _deserialize_color(value, default):
    if not value:
        return default
    try:
        loaded = json.loads(value)
        if isinstance(loaded, (list, tuple)) and len(loaded) == 3:
            return tuple(float(channel) for channel in loaded)
    except Exception:
        pass
    return default


def _load_option(key, default):
    if not MAYA_AVAILABLE:
        return default
    option_name = OPTION_KEYS[key]
    if not cmds.optionVar(exists=option_name):
        return default
    if isinstance(default, bool):
        return bool(cmds.optionVar(query=option_name))
    if isinstance(default, int):
        return int(cmds.optionVar(query=option_name))
    if isinstance(default, float):
        return float(cmds.optionVar(query=option_name))
    if isinstance(default, (tuple, list)):
        return _deserialize_color(cmds.optionVar(query=option_name), default)
    return cmds.optionVar(query=option_name)


def _save_option(key, value):
    if not MAYA_AVAILABLE:
        return
    option_name = OPTION_KEYS[key]
    if isinstance(value, bool):
        cmds.optionVar(intValue=(option_name, int(value)))
    elif isinstance(value, int):
        cmds.optionVar(intValue=(option_name, value))
    elif isinstance(value, float):
        cmds.optionVar(floatValue=(option_name, value))
    elif isinstance(value, (tuple, list)):
        cmds.optionVar(stringValue=(option_name, _serialize_color(value)))
    else:
        cmds.optionVar(stringValue=(option_name, value))


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
        "import sys\n"
        "repo_path = r\"{0}\"\n"
        "if repo_path not in sys.path:\n"
        "    sys.path.insert(0, repo_path)\n"
        "import maya_onion_skin\n"
        "maya_onion_skin.launch_maya_onion_skin()\n"
    ).format(repo_path.replace("\\", "\\\\"))


def install_maya_onion_skin_shelf_button(
    shelf_name=DEFAULT_SHELF_NAME,
    button_label=DEFAULT_SHELF_BUTTON_LABEL,
    repo_path=None,
):
    if not MAYA_AVAILABLE:
        raise RuntimeError("install_maya_onion_skin_shelf_button() must run inside Autodesk Maya.")

    repo_path = repo_path or os.path.dirname(os.path.abspath(__file__))
    metadata = maya_shelf_utils.install_shelf_button(
        command_text=_shelf_button_command(repo_path),
        doc_tag=SHELF_BUTTON_DOC_TAG,
        annotation="Launch Maya Onion Skin",
        button_label=button_label,
        image_overlay_label="OS",
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


def _dag_path(node_name):
    selection = om.MSelectionList()
    selection.add(node_name)
    return selection.getDagPath(0)


def _matrix_to_list(matrix):
    return [matrix[index] for index in range(16)]


def _active_model_panel(require_focus=False):
    try:
        panel = cmds.getPanel(withFocus=True)
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            return panel
    except Exception:
        pass
    if require_focus:
        return ""
    for panel in cmds.getPanel(type="modelPanel") or []:
        try:
            if cmds.modelEditor(panel, query=True, exists=True):
                return panel
        except Exception:
            continue
    return ""


def _active_camera(panel_name=""):
    panel_name = panel_name or _active_model_panel(require_focus=False)
    if not panel_name:
        return ""
    try:
        camera_name = cmds.modelEditor(panel_name, query=True, camera=True)
    except Exception:
        return ""
    if not camera_name:
        return ""
    if cmds.nodeType(camera_name) == "camera":
        parents = cmds.listRelatives(camera_name, parent=True, fullPath=True) or []
        return parents[0] if parents else camera_name
    return camera_name


def _camera_shape(camera_name):
    if not camera_name or not cmds.objExists(camera_name):
        return ""
    if cmds.nodeType(camera_name) == "camera":
        return camera_name
    shapes = cmds.listRelatives(camera_name, shapes=True, fullPath=True, type="camera") or []
    return shapes[0] if shapes else ""


def _silhouette_cache_dir():
    cache_dir = os.path.join(tempfile.gettempdir(), "maya_onion_skin_silhouette")
    if not os.path.isdir(cache_dir):
        try:
            os.makedirs(cache_dir)
        except OSError:
            pass
    return cache_dir


def _color_to_rgba_bytes(color, alpha_value):
    return (
        int(_clamp(color[0], 0.0, 1.0) * 255.0),
        int(_clamp(color[1], 0.0, 1.0) * 255.0),
        int(_clamp(color[2], 0.0, 1.0) * 255.0),
        int(_clamp(alpha_value, 0.0, 1.0) * 255.0),
    )


def _tint_silhouette_image(source_path, destination_path, color, alpha_value):
    if not (QtGui and os.path.exists(source_path)):
        return 0
    image = QtGui.QImage(source_path)
    if image.isNull():
        return 0
    output = QtGui.QImage(image.size(), QtGui.QImage.Format_ARGB32)
    output.fill(QtCore.Qt.transparent)
    fill_rgba = _color_to_rgba_bytes(color, alpha_value)
    threshold = 18
    filled_pixels = 0
    for y_pos in range(image.height()):
        for x_pos in range(image.width()):
            pixel = image.pixelColor(x_pos, y_pos)
            if pixel.red() <= threshold and pixel.green() <= threshold and pixel.blue() <= threshold:
                continue
            output.setPixelColor(x_pos, y_pos, QtGui.QColor(*fill_rgba))
            filled_pixels += 1
    if filled_pixels <= 0:
        return 0
    if not output.save(destination_path, "PNG"):
        return 0
    return filled_pixels


class MayaOnionSkinController(object):
    def __init__(self):
        self.display_mode = _load_option("display_mode", MODE_3D_GHOST)
        self.past_frames = _load_option("past_frames", DEFAULT_PAST_FRAMES)
        self.future_frames = _load_option("future_frames", DEFAULT_FUTURE_FRAMES)
        self.frame_step = _load_option("frame_step", DEFAULT_FRAME_STEP)
        self.opacity = _load_option("opacity", DEFAULT_OPACITY)
        self.falloff = _load_option("falloff", DEFAULT_FALLOFF)
        self.auto_update = _load_option("auto_update", True)
        self.full_fidelity_scrub = _load_option("full_fidelity_scrub", DEFAULT_FULL_FIDELITY_SCRUB)
        self.past_color = _load_option("past_color", DEFAULT_PAST_COLOR)
        self.future_color = _load_option("future_color", DEFAULT_FUTURE_COLOR)

        self.attached_root = None
        self.attached_roots = []
        self.source_meshes = []
        self.ghost_cache = {}
        self.material_cache = {}
        self.callback_ids = []
        self.script_job_id = None
        self._updating = False
        self._context_sampling_supported = True
        self._offset_layout_dirty = True
        self._appearance_dirty = True
        self._active_offset_signature = tuple()
        self._refresh_timer = None
        self._refresh_pending = False
        self._pending_rebuild = False
        self._pending_reason = "callback"
        self._refresh_request_serial = 0
        self._pending_request_serial = 0
        self._active_refresh_serial = 0
        self._stale_refresh_skip_count = 0
        self._completed_refresh_count = 0
        self._last_refresh_duration_ms = 0.0
        self._last_callback_request_at = 0.0
        self._cached_visible_mesh_entries = None
        self._visible_mesh_cache_dirty = True
        self.silhouette_cache = {}
        self.silhouette_image_planes = {}
        self._camera_signature = tuple()
        self._camera_poll_timer = None
        self._last_motion_at = 0.0
        self._silhouette_capture_active = False
        self._silhouette_live_cursor = 0
        self._last_silhouette_warning = ""
        self._last_silhouette_warning_at = 0.0

    def save_preferences(self):
        _save_option("display_mode", self.display_mode)
        _save_option("past_frames", int(self.past_frames))
        _save_option("future_frames", int(self.future_frames))
        _save_option("frame_step", int(self.frame_step))
        _save_option("opacity", float(self.opacity))
        _save_option("falloff", float(self.falloff))
        _save_option("auto_update", bool(self.auto_update))
        _save_option("full_fidelity_scrub", bool(self.full_fidelity_scrub))
        _save_option("past_color", self.past_color)
        _save_option("future_color", self.future_color)

    def set_settings(
        self,
        past_frames,
        future_frames,
        frame_step,
        opacity,
        falloff,
        auto_update,
        full_fidelity_scrub,
        past_color,
        future_color,
        display_mode=None,
    ):
        new_display_mode = display_mode or self.display_mode or MODE_3D_GHOST
        if new_display_mode not in (MODE_3D_GHOST, MODE_FAST_SILHOUETTE):
            new_display_mode = MODE_3D_GHOST
        new_past_frames = _clamp(int(past_frames), 0, MAX_FRAMES_PER_SIDE)
        new_future_frames = _clamp(int(future_frames), 0, MAX_FRAMES_PER_SIDE)
        new_frame_step = _clamp(int(frame_step), 1, MAX_FRAME_STEP)
        new_opacity = float(_clamp(opacity, 0.05, 1.0))
        new_falloff = float(_clamp(falloff, 0.1, 4.0))
        new_auto_update = bool(auto_update)
        new_full_fidelity_scrub = bool(full_fidelity_scrub)
        was_full_fidelity_scrub = self.full_fidelity_scrub
        new_past_color = tuple(_clamp(channel, 0.0, 1.0) for channel in past_color)
        new_future_color = tuple(_clamp(channel, 0.0, 1.0) for channel in future_color)

        if (
            new_display_mode != self.display_mode
            or (
            new_past_frames != self.past_frames
            or new_future_frames != self.future_frames
            or new_frame_step != self.frame_step
            )
        ):
            self._offset_layout_dirty = True
            self._appearance_dirty = True
        elif (
            new_opacity != self.opacity
            or new_falloff != self.falloff
            or new_past_color != self.past_color
            or new_future_color != self.future_color
        ):
            self._appearance_dirty = True

        self.display_mode = new_display_mode
        self.past_frames = new_past_frames
        self.future_frames = new_future_frames
        self.frame_step = new_frame_step
        self.opacity = new_opacity
        self.falloff = new_falloff
        self.auto_update = new_auto_update
        self.full_fidelity_scrub = new_full_fidelity_scrub
        self.past_color = new_past_color
        self.future_color = new_future_color
        if self.full_fidelity_scrub and not was_full_fidelity_scrub:
            self._cancel_scheduled_refresh()
        self._ensure_camera_polling()
        self.save_preferences()

    def _set_attached_roots(self, roots):
        normalized = []
        for root in roots or []:
            if not root or not cmds.objExists(root):
                continue
            long_name = (cmds.ls(root, long=True) or [root])[0]
            normalized.append(long_name)
        self.attached_roots = _dedupe_preserve_order(normalized)
        self.attached_root = self.attached_roots[0] if self.attached_roots else None

    def _selected_roots(self):
        selection = cmds.ls(selection=True, long=True) or []
        roots = []
        for node_name in selection:
            current = node_name
            try:
                if cmds.nodeType(current) == "mesh":
                    parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
                    if not parents:
                        continue
                    current = parents[0]
            except Exception:
                continue
            roots.append(current)
        return _dedupe_preserve_order(roots)

    def _valid_attached_roots(self):
        return [root for root in self.attached_roots if cmds.objExists(root)]

    def _reset_runtime_state(self, clear_scene_nodes=True):
        self._cancel_scheduled_refresh()
        if clear_scene_nodes:
            self._delete_ghost_group()
            self._delete_materials()
            self._delete_silhouette_planes()
        self.ghost_cache = {}
        self.material_cache = {}
        self.silhouette_cache = {}
        self.silhouette_image_planes = {}
        self._active_offset_signature = tuple()
        self._offset_layout_dirty = True
        self._appearance_dirty = True
        self._cached_visible_mesh_entries = None
        self._visible_mesh_cache_dirty = True
        self._camera_signature = tuple()
        self._last_motion_at = 0.0
        self._silhouette_live_cursor = 0

    def attachment_summary(self):
        if not self.attached_roots:
            return "Pick one or more characters, then click Attach Selected."
        if len(self.attached_roots) == 1:
            return "Attached to {0} with {1} mesh shapes.".format(self.attached_roots[0], len(self.source_meshes))
        return "Attached {0} roots with {1} mesh shapes.".format(len(self.attached_roots), len(self.source_meshes))

    def attach_selection(self, add=False):
        selected_roots = self._selected_roots()
        if not selected_roots:
            return False, "Select one or more character roots or main controls first."

        previous_roots = list(self.attached_roots)
        if add and previous_roots:
            selected_roots = _dedupe_preserve_order(previous_roots + selected_roots)

        discovered_meshes = self._discover_mesh_entries(selected_roots)
        if not discovered_meshes:
            return False, "No visible mesh shapes were found under the current selection."

        self._remove_callbacks()
        self._reset_runtime_state(clear_scene_nodes=True)
        self._set_attached_roots(selected_roots)
        self.source_meshes = discovered_meshes
        self._register_callbacks()

        success, message = self.refresh(rebuild=False, reason="attach")
        if not success:
            self.detach(clear_attachment=False)
            if previous_roots:
                previous_meshes = self._discover_mesh_entries(previous_roots)
                if previous_meshes:
                    self._set_attached_roots(previous_roots)
                    self.source_meshes = previous_meshes
                    self._register_callbacks()
                    self.refresh(rebuild=False, reason="restore")
                else:
                    self._set_attached_roots([])
                    self.source_meshes = []
            else:
                self._set_attached_roots([])
                self.source_meshes = []
            return False, message

        action = "Added" if add and previous_roots else "Attached"
        return True, "{0} {1} mesh shapes across {2} roots.".format(
            action,
            len(self.source_meshes),
            len(self.attached_roots),
        )

    def manual_refresh(self):
        valid_roots = self._valid_attached_roots()
        if not valid_roots:
            return False, "Nothing is attached. Use Attach Selected first."

        self._set_attached_roots(valid_roots)
        self.source_meshes = self._discover_mesh_entries(valid_roots)
        if not self.source_meshes:
            self.detach()
            return False, "Attached roots no longer have visible mesh shapes."

        self._reset_runtime_state(clear_scene_nodes=True)
        return self.refresh(rebuild=False, reason="manual")

    def detach(self, clear_attachment=True):
        self._remove_callbacks()
        self._reset_runtime_state(clear_scene_nodes=True)
        self.source_meshes = []
        if clear_attachment:
            self._set_attached_roots([])

    def shutdown(self):
        self.detach(clear_attachment=True)

    def refresh(self, rebuild=False, reason="callback", request_serial=None):
        if self._updating:
            return True, "Update already running."
        if not self.attached_roots:
            return False, "Nothing is attached."
        if reason != "callback":
            self._cancel_scheduled_refresh()
        valid_roots = self._valid_attached_roots()
        if not valid_roots:
            self.detach()
            return False, "Attached roots were deleted."
        if valid_roots != self.attached_roots:
            self._set_attached_roots(valid_roots)
            rebuild = True
        if rebuild:
            self.source_meshes = self._discover_mesh_entries(valid_roots)
            self._cached_visible_mesh_entries = None
            self._visible_mesh_cache_dirty = True
        if not self.source_meshes:
            self.detach()
            return False, "No visible mesh shapes are currently attached."

        desired_offsets = self._desired_offsets()
        if not desired_offsets:
            self._reset_runtime_state(clear_scene_nodes=True)
            return True, "Past and future frame counts are both zero."

        self._updating = True
        self._active_refresh_serial = int(request_serial or 0)
        refresh_started_at = time.perf_counter()
        current_time = cmds.currentTime(query=True)
        refresh_suspended = False
        requires_time_restore = False
        active_offsets = self._active_offsets_for_reason(reason, desired_offsets)

        try:
            if self.display_mode == MODE_FAST_SILHOUETTE:
                self._delete_ghost_group()
                self._delete_materials()
                self.ghost_cache = {}
                self.material_cache = {}
                self._refresh_fast_silhouette(active_offsets, current_time, refresh_serial=request_serial)
            else:
                self._delete_silhouette_planes()
                self._ensure_root_group()
                offset_signature = tuple(desired_offsets)
                if self._offset_layout_dirty or offset_signature != self._active_offset_signature:
                    self._sync_offset_slots(desired_offsets)
                    self._active_offset_signature = offset_signature
                    self._offset_layout_dirty = False
                    self._appearance_dirty = True

                if self._appearance_dirty:
                    self._sync_materials(desired_offsets)
                    self._appearance_dirty = False

                preview_mode = active_offsets != desired_offsets
                visible_mesh_entries = self._visible_mesh_entries(desired_offsets, allow_cached=preview_mode)
                active_mesh_entries = self._active_mesh_entries_for_reason(reason, visible_mesh_entries, preview_mode)
                self._set_group_visibility(bool(visible_mesh_entries))
                self._sync_offset_group_visibility(desired_offsets, active_offsets)

                try:
                    cmds.refresh(suspend=True)
                    refresh_suspended = True
                except Exception:
                    refresh_suspended = False

                if self._context_sampling_supported:
                    try:
                        self._refresh_with_context(active_offsets, current_time, active_mesh_entries)
                    except Exception:
                        self._context_sampling_supported = False
                        _warning(
                            "Context-based sampling failed once. Falling back to timeline stepping. Details: {0}".format(
                                traceback.format_exc().strip().splitlines()[-1]
                            )
                        )
                        requires_time_restore = True
                        self._refresh_with_timeline(active_offsets, current_time, active_mesh_entries)
                else:
                    requires_time_restore = True
                    self._refresh_with_timeline(active_offsets, current_time, active_mesh_entries)
        except Exception as exc:
            return False, "Onion skin refresh failed: {0}".format(exc)
        finally:
            if requires_time_restore:
                try:
                    cmds.currentTime(current_time, edit=True, update=True)
                except Exception:
                    pass
            if refresh_suspended:
                try:
                    cmds.refresh(suspend=False)
                    if reason != "callback":
                        cmds.refresh(force=True)
                except Exception:
                    pass
            self._last_refresh_duration_ms = (time.perf_counter() - refresh_started_at) * 1000.0
            self._updating = False
            self._active_refresh_serial = 0

        if self.display_mode == MODE_FAST_SILHOUETTE:
            self._camera_signature = self._current_view_signature(include_time=False)

        self._completed_refresh_count += 1
        return True, "Updated {0} ghost offsets across {1} roots around frame {2}.".format(
            len(active_offsets),
            len(self.attached_roots),
            int(round(current_time)),
        )

    def _on_time_changed(self, *args):
        if not self.auto_update or self._updating or self._silhouette_capture_active or not self.attached_roots:
            return
        self._queue_callback_refresh(rebuild=False, reason="callback")

    def _queue_callback_refresh(self, rebuild=False, reason="callback"):
        if self.display_mode == MODE_3D_GHOST and self.full_fidelity_scrub and reason == "callback":
            self._cancel_scheduled_refresh()
            self.refresh(rebuild=rebuild, reason=reason)
            return
        if not MAYA_AVAILABLE or cmds.about(batch=True) or not QtCore:
            self.refresh(rebuild=rebuild, reason=reason)
            return

        self._last_callback_request_at = time.perf_counter()
        self._refresh_request_serial += 1
        self._refresh_pending = True
        self._pending_rebuild = self._pending_rebuild or rebuild
        self._pending_reason = reason
        self._pending_request_serial = self._refresh_request_serial

        timer = self._ensure_refresh_timer()
        if timer:
            timer.start(AUTO_UPDATE_INTERVAL_MS)

    def _ensure_refresh_timer(self):
        if self._refresh_timer or not QtCore or not MAYA_AVAILABLE or cmds.about(batch=True):
            return self._refresh_timer

        self._refresh_timer = QtCore.QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._process_queued_refresh)
        return self._refresh_timer

    def _ensure_camera_polling(self):
        if not QtCore or not MAYA_AVAILABLE or cmds.about(batch=True):
            return None
        if self.display_mode != MODE_FAST_SILHOUETTE or not self.auto_update or not self.attached_roots:
            if self._camera_poll_timer and self._camera_poll_timer.isActive():
                self._camera_poll_timer.stop()
            return self._camera_poll_timer
        if self._camera_poll_timer is None:
            self._camera_poll_timer = QtCore.QTimer()
            self._camera_poll_timer.timeout.connect(self._on_camera_poll)
        if not self._camera_poll_timer.isActive():
            self._camera_poll_timer.start(CAMERA_POLL_INTERVAL_MS)
        return self._camera_poll_timer

    def _current_view_signature(self, include_time=True):
        panel_name = _active_model_panel(require_focus=False)
        camera_name = _active_camera(panel_name)
        if not camera_name or not cmds.objExists(camera_name):
            if include_time:
                return (panel_name, camera_name, round(float(cmds.currentTime(query=True)), 3))
            return (panel_name, camera_name)
        matrix_values = cmds.xform(camera_name, query=True, matrix=True, worldSpace=True) or [0.0] * 16
        rounded_matrix = tuple(round(float(value), 4) for value in matrix_values)
        if include_time:
            return (panel_name, camera_name, round(float(cmds.currentTime(query=True)), 3), rounded_matrix)
        return (panel_name, camera_name, rounded_matrix)

    def _on_camera_poll(self):
        if self.display_mode != MODE_FAST_SILHOUETTE or not self.auto_update or self._silhouette_capture_active or not self.attached_roots:
            return
        current_signature = self._current_view_signature(include_time=False)
        if current_signature != self._camera_signature:
            self._camera_signature = current_signature
            self._last_motion_at = time.perf_counter()
            self._queue_callback_refresh(rebuild=False, reason="view")

    def _process_queued_refresh(self):
        if not self._refresh_pending or not self.attached_roots:
            return
        if self._updating:
            timer = self._ensure_refresh_timer()
            if timer:
                timer.start(AUTO_UPDATE_INTERVAL_MS)
            return

        rebuild = self._pending_rebuild
        reason = self._pending_reason
        request_serial = self._pending_request_serial
        self._refresh_pending = False
        self._pending_rebuild = False
        self._pending_reason = "callback"
        self._pending_request_serial = 0

        if self.display_mode == MODE_3D_GHOST and self.full_fidelity_scrub and reason == "callback":
            self.refresh(rebuild=rebuild, reason=reason, request_serial=request_serial)
            return

        self.refresh(rebuild=rebuild, reason=reason, request_serial=request_serial)

        timer = self._ensure_refresh_timer()
        if not timer or timer.isActive():
            return

        if self._refresh_pending:
            timer.start(AUTO_UPDATE_INTERVAL_MS)
            return

        if reason in ("callback", "view"):
            elapsed_ms = (time.perf_counter() - self._last_callback_request_at) * 1000.0
            if elapsed_ms < SCRUB_SETTLE_DELAY_MS:
                self._refresh_pending = True
                self._pending_rebuild = False
                self._pending_reason = reason
                self._pending_request_serial = max(int(request_serial or 0), self._refresh_request_serial)
                remaining_ms = max(int(SCRUB_SETTLE_DELAY_MS - elapsed_ms), AUTO_UPDATE_INTERVAL_MS)
                timer.start(remaining_ms)

    def _cancel_scheduled_refresh(self):
        self._refresh_pending = False
        self._pending_rebuild = False
        self._pending_reason = "callback"
        self._pending_request_serial = 0
        if self._refresh_timer and self._refresh_timer.isActive():
            self._refresh_timer.stop()
        if self._camera_poll_timer and self._camera_poll_timer.isActive() and self.display_mode != MODE_FAST_SILHOUETTE:
            self._camera_poll_timer.stop()

    def _is_refresh_stale(self, refresh_serial):
        if not refresh_serial:
            return False
        return int(refresh_serial) < int(self._refresh_request_serial)

    def _register_callbacks(self):
        self._remove_callbacks()
        self._ensure_camera_polling()
        try:
            callback_id = om.MEventMessage.addEventCallback("timeChanged", self._on_time_changed)
            self.callback_ids.append(callback_id)
        except Exception:
            self.callback_ids = []
            try:
                self.script_job_id = cmds.scriptJob(event=["timeChanged", self._on_time_changed], protected=True)
            except Exception as exc:
                _warning("Could not install timeChanged callback: {0}".format(exc))

    def _remove_callbacks(self):
        for callback_id in self.callback_ids:
            try:
                om.MMessage.removeCallback(callback_id)
            except Exception:
                pass
        self.callback_ids = []

        if self.script_job_id:
            try:
                cmds.scriptJob(kill=self.script_job_id, force=True)
            except Exception:
                pass
        self.script_job_id = None
        if self._camera_poll_timer and self._camera_poll_timer.isActive():
            self._camera_poll_timer.stop()

    def _discover_mesh_entries(self, roots):
        if isinstance(roots, (str, bytes)):
            roots = [roots]

        mesh_entries = []
        seen_shapes = set()

        for root in roots or []:
            if not root or not cmds.objExists(root):
                continue

            candidates = []
            if cmds.nodeType(root) == "transform":
                direct_shapes = cmds.listRelatives(root, shapes=True, fullPath=True, type="mesh") or []
                candidates.extend(direct_shapes)

            descendants = cmds.listRelatives(root, allDescendents=True, fullPath=True, type="mesh") or []
            candidates.extend(descendants)

            for shape in candidates:
                if shape in seen_shapes or not cmds.objExists(shape):
                    continue
                seen_shapes.add(shape)
                if not self._is_shape_eligible(shape):
                    continue

                transform = cmds.listRelatives(shape, parent=True, fullPath=True) or []
                if not transform:
                    continue

                transform_name = transform[0]
                try:
                    shape_path = _dag_path(shape)
                    transform_path = _dag_path(transform_name)
                except Exception:
                    continue

                mesh_entries.append(
                    {
                        "root": root,
                        "shape": shape,
                        "transform": transform_name,
                        "shape_path": shape_path,
                        "transform_path": transform_path,
                        "is_deformed": self._is_shape_deformed(shape),
                    }
                )

        if any(entry["is_deformed"] for entry in mesh_entries):
            filtered_entries = [
                entry for entry in mesh_entries if entry["is_deformed"] or not self._is_proxy_like_entry(entry)
            ]
            if filtered_entries:
                mesh_entries = filtered_entries

        mesh_entries.sort(key=lambda entry: entry["shape"])
        return mesh_entries

    def _is_shape_deformed(self, shape):
        history = cmds.listHistory(shape, pruneDagObjects=True) or []
        if not history:
            return False
        try:
            history_types = set(cmds.nodeType(node) for node in history)
        except Exception:
            return True
        return bool(history_types.intersection(DEFORMER_NODE_TYPES))

    def _is_proxy_like_entry(self, mesh_entry):
        haystack = "{0} {1}".format(mesh_entry["shape"], mesh_entry["transform"]).lower()
        return any(token in haystack for token in PROXY_NAME_TOKENS)

    def _visible_mesh_entries(self, desired_offsets, allow_cached=False):
        if allow_cached and not self._visible_mesh_cache_dirty and self._cached_visible_mesh_entries is not None:
            return list(self._cached_visible_mesh_entries)

        visible_entries = []
        hidden_entries = []

        for mesh_entry in self.source_meshes:
            shape_name = mesh_entry["shape"]
            transform_name = mesh_entry["transform"]
            if not cmds.objExists(shape_name) or not cmds.objExists(transform_name):
                hidden_entries.append(mesh_entry)
                continue
            if self._is_visible_in_hierarchy(shape_name):
                visible_entries.append(mesh_entry)
            else:
                hidden_entries.append(mesh_entry)

        if hidden_entries:
            for mesh_entry in hidden_entries:
                for offset in desired_offsets:
                    self._hide_cached_ghost(offset, mesh_entry)

        self._cached_visible_mesh_entries = list(visible_entries)
        self._visible_mesh_cache_dirty = False
        return visible_entries

    def _active_mesh_entries_for_reason(self, reason, visible_mesh_entries, preview_mode):
        if reason != "callback" or not preview_mode or self.full_fidelity_scrub:
            return visible_mesh_entries
        mesh_limit = SCRUB_PREVIEW_MAX_MESHES
        if len(visible_mesh_entries) >= 80:
            mesh_limit = min(mesh_limit, 12)
        elif len(visible_mesh_entries) >= 40:
            mesh_limit = min(mesh_limit, 16)

        if len(visible_mesh_entries) <= mesh_limit:
            return visible_mesh_entries

        deformed_entries = [entry for entry in visible_mesh_entries if entry["is_deformed"]]
        rigid_entries = [entry for entry in visible_mesh_entries if not entry["is_deformed"]]
        if len(deformed_entries) >= mesh_limit:
            return self._sample_list_evenly(deformed_entries, mesh_limit)

        remaining = mesh_limit - len(deformed_entries)
        return deformed_entries + self._sample_list_evenly(rigid_entries, remaining)

    def _is_shape_eligible(self, shape):
        if cmds.getAttr("{0}.intermediateObject".format(shape)):
            return False
        return self._is_visible_in_hierarchy(shape)

    def _is_visible_in_hierarchy(self, node):
        current = node
        while current:
            for attribute in ("visibility", "lodVisibility"):
                if cmds.attributeQuery(attribute, node=current, exists=True):
                    try:
                        if not cmds.getAttr("{0}.{1}".format(current, attribute)):
                            return False
                    except Exception:
                        return False
            parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
            current = parents[0] if parents else None
        return True

    def _desired_offsets(self):
        offsets = []
        for sample_index in range(self.past_frames, 0, -1):
            offsets.append(-(sample_index * self.frame_step))
        for sample_index in range(1, self.future_frames + 1):
            offsets.append(sample_index * self.frame_step)
        return offsets

    def _ensure_root_group(self):
        if not cmds.objExists(ROOT_GROUP_NAME):
            cmds.createNode("transform", name=ROOT_GROUP_NAME)
            cmds.setAttr("{0}.overrideEnabled".format(ROOT_GROUP_NAME), 1)
            cmds.setAttr("{0}.overrideDisplayType".format(ROOT_GROUP_NAME), 2)

    def _set_group_visibility(self, visible):
        if cmds.objExists(ROOT_GROUP_NAME):
            attr_name = "{0}.visibility".format(ROOT_GROUP_NAME)
            desired_value = int(bool(visible))
            try:
                current_value = cmds.getAttr(attr_name)
            except Exception:
                current_value = None
            if current_value != desired_value:
                cmds.setAttr(attr_name, desired_value)

    def _delete_ghost_group(self):
        _safe_delete(ROOT_GROUP_NAME)

    def _delete_materials(self):
        shader_names = list(self.material_cache.values())
        self.material_cache = {}
        for shader_info in shader_names:
            _safe_delete(shader_info.get("shading_group"))
            _safe_delete(shader_info.get("shader"))

        for node_name in cmds.ls("{0}_*".format(PREFIX)) or []:
            if cmds.objExists(node_name) and cmds.nodeType(node_name) in ("lambert", "shadingEngine"):
                _safe_delete(node_name)

    def _sync_offset_slots(self, desired_offsets):
        desired_keys = set(desired_offsets)
        existing_keys = set(self.ghost_cache.keys())

        for offset in sorted(existing_keys - desired_keys):
            ghost_slot = self.ghost_cache.pop(offset, None)
            if ghost_slot:
                _safe_delete(ghost_slot.get("group"))

        for offset in desired_offsets:
            if offset not in self.ghost_cache:
                group_name = self._offset_group_name(offset)
                group = cmds.createNode("transform", name=group_name, parent=ROOT_GROUP_NAME)
                cmds.setAttr("{0}.overrideEnabled".format(group), 1)
                cmds.setAttr("{0}.overrideDisplayType".format(group), 2)
                self.ghost_cache[offset] = {"group": group, "entries": {}, "visible": True}

    def _sync_offset_group_visibility(self, desired_offsets, active_offsets):
        active_keys = set(active_offsets)
        for offset in desired_offsets:
            slot = self.ghost_cache.get(offset)
            if not slot:
                continue
            desired_visible = offset in active_keys
            if slot.get("visible") == desired_visible:
                continue
            cmds.setAttr("{0}.visibility".format(slot["group"]), int(desired_visible))
            slot["visible"] = desired_visible

    def _sync_materials(self, desired_offsets):
        desired_keys = set(desired_offsets)
        existing_keys = set(self.material_cache.keys())

        for offset in sorted(existing_keys - desired_keys):
            shader_info = self.material_cache.pop(offset, None)
            if shader_info:
                _safe_delete(shader_info.get("shading_group"))
                _safe_delete(shader_info.get("shader"))

        for offset in desired_offsets:
            alpha = self._offset_alpha(offset)
            color = self._offset_color(offset)
            shader_info = self.material_cache.get(offset)
            if not shader_info:
                shader_info = self._create_material(offset)
                self.material_cache[offset] = shader_info
            self._update_material(shader_info, color, alpha)

    def _create_material(self, offset):
        direction = "past" if offset < 0 else "future"
        suffix = "{0}_{1:02d}".format(direction, abs(offset))
        shader_name = "{0}_{1}_SHD".format(PREFIX, suffix)
        shading_group_name = "{0}_{1}_SG".format(PREFIX, suffix)
        _safe_delete(shading_group_name)
        _safe_delete(shader_name)
        shader = cmds.shadingNode("lambert", asShader=True, name=shader_name)
        shading_group = cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=shading_group_name,
        )
        cmds.connectAttr("{0}.outColor".format(shader), "{0}.surfaceShader".format(shading_group), force=True)
        return {"shader": shader, "shading_group": shading_group}

    def _update_material(self, shader_info, color, alpha):
        shader = shader_info["shader"]
        transparency = 1.0 - alpha
        cmds.setAttr("{0}.color".format(shader), color[0], color[1], color[2], type="double3")
        cmds.setAttr(
            "{0}.transparency".format(shader),
            transparency,
            transparency,
            transparency,
            type="double3",
        )
        cmds.setAttr(
            "{0}.ambientColor".format(shader),
            color[0] * 0.15,
            color[1] * 0.15,
            color[2] * 0.15,
            type="double3",
        )
        cmds.setAttr("{0}.diffuse".format(shader), 0.8)
        cmds.setAttr("{0}.translucence".format(shader), 0.0)

    def _offset_group_name(self, offset):
        direction = "past" if offset < 0 else "future"
        return "{0}_{1}_{2:02d}_GRP".format(PREFIX, direction, abs(offset))

    def _offset_color(self, offset):
        base = self.past_color if offset < 0 else self.future_color
        count = self.past_frames if offset < 0 else self.future_frames
        if count <= 1:
            return base
        sample_index = max(1.0, abs(offset) / float(max(self.frame_step, 1)))
        normalized = 1.0 - ((sample_index - 1.0) / float(max(count - 1, 1)))
        return _lerp_color((0.12, 0.12, 0.12), base, 0.45 + (normalized * 0.55))

    def _offset_alpha(self, offset):
        count = self.past_frames if offset < 0 else self.future_frames
        if count <= 1:
            return self.opacity
        sample_index = max(1.0, abs(offset) / float(max(self.frame_step, 1)))
        normalized = 1.0 - ((sample_index - 1.0) / float(max(count - 1, 1)))
        return _clamp(self.opacity * math.pow(max(normalized, 0.01), self.falloff), 0.02, 1.0)

    def _active_offsets_for_reason(self, reason, desired_offsets):
        if self.display_mode == MODE_FAST_SILHOUETTE:
            return desired_offsets
        if reason != "callback" or self.full_fidelity_scrub:
            return desired_offsets
        preview_limit = SCRUB_PREVIEW_MAX_OFFSETS
        source_count = len(self.source_meshes)
        if source_count >= 80:
            preview_limit = min(preview_limit, 2)
        elif source_count >= 40:
            preview_limit = min(preview_limit, 4)

        if len(desired_offsets) <= preview_limit:
            return desired_offsets
        elapsed_ms = (time.perf_counter() - self._last_callback_request_at) * 1000.0
        if elapsed_ms >= SCRUB_SETTLE_DELAY_MS:
            return desired_offsets

        max_per_side = max(1, preview_limit // 2)
        past_offsets = [offset for offset in desired_offsets if offset < 0]
        future_offsets = [offset for offset in desired_offsets if offset > 0]
        return self._preview_side_offsets(past_offsets, max_per_side, reverse=True) + self._preview_side_offsets(
            future_offsets,
            max_per_side,
            reverse=False,
        )

    def _preview_side_offsets(self, offsets, limit, reverse):
        if len(offsets) <= limit:
            return list(offsets)

        sorted_offsets = sorted(offsets, key=lambda value: abs(value))
        chosen = self._sample_list_evenly(sorted_offsets, limit)

        if reverse:
            return sorted(chosen)
        return sorted(chosen, key=lambda value: abs(value))

    def _sample_list_evenly(self, items, limit):
        if len(items) <= limit:
            return list(items)

        chosen = []
        count = len(items)
        for index in range(limit):
            sample_index = int(round((index / float(max(limit - 1, 1))) * float(count - 1)))
            candidate = items[sample_index]
            if candidate not in chosen:
                chosen.append(candidate)
        return chosen

    def _fast_silhouette_is_live_preview(self):
        if self.display_mode != MODE_FAST_SILHOUETTE:
            return False
        if not self._last_motion_at:
            return False
        return (time.perf_counter() - self._last_motion_at) * 1000.0 < SCRUB_SETTLE_DELAY_MS

    def _fast_silhouette_resolution(self):
        if self._fast_silhouette_is_live_preview():
            return FAST_SILHOUETTE_LIVE_RESOLUTION
        return FAST_SILHOUETTE_REFINE_RESOLUTION

    def _warn_silhouette_once(self, message):
        now = time.perf_counter()
        if message == self._last_silhouette_warning and ((now - self._last_silhouette_warning_at) * 1000.0) < 1000.0:
            return
        self._last_silhouette_warning = message
        self._last_silhouette_warning_at = now
        _warning(message)

    def _delete_silhouette_planes(self):
        for entry in list(self.silhouette_image_planes.values()):
            for node_name in (entry.get("transform"), entry.get("shape")):
                if node_name and cmds.objExists(node_name):
                    try:
                        cmds.delete(node_name)
                    except Exception:
                        pass
        self.silhouette_image_planes = {}

    def _ensure_silhouette_plane(self, offset, camera_shape):
        entry = self.silhouette_image_planes.get(offset)
        if entry and cmds.objExists(entry.get("shape", "")):
            if entry.get("camera") == camera_shape:
                return entry
            for node_name in (entry.get("transform"), entry.get("shape")):
                if node_name and cmds.objExists(node_name):
                    try:
                        cmds.delete(node_name)
                    except Exception:
                        pass
        plane_result = cmds.imagePlane(camera=camera_shape, name="{0}_{1:02d}".format(SILHOUETTE_PREFIX, abs(offset)))
        transform_name = plane_result[0]
        shape_name = plane_result[1] if len(plane_result) > 1 else (cmds.listRelatives(transform_name, shapes=True, fullPath=True) or [""])[0]
        try:
            cmds.setAttr(shape_name + ".displayOnlyIfCurrent", 1)
        except Exception:
            pass
        try:
            cmds.setAttr(shape_name + ".type", 0)
        except Exception:
            pass
        try:
            cmds.setAttr(shape_name + ".depth", 5.0 + (abs(offset) * 0.02))
        except Exception:
            pass
        entry = {"transform": transform_name, "shape": shape_name, "camera": camera_shape}
        self.silhouette_image_planes[offset] = entry
        return entry

    def _silhouette_cache_key(self, sample_frame, resolution, color, alpha_value, camera_signature):
        return (
            round(float(sample_frame), 3),
            int(resolution[0]),
            int(resolution[1]),
            tuple(round(float(channel), 4) for channel in color),
            round(float(alpha_value), 4),
            camera_signature,
        )

    def _reuse_silhouette_cache(self, offset, sample_frame, resolution, color, alpha_value, camera_shape, camera_signature):
        cache_key = self._silhouette_cache_key(sample_frame, resolution, color, alpha_value, camera_signature)
        cache_entry = self.silhouette_cache.get(offset) or {}
        image_path = cache_entry.get("image_path") or ""
        if cache_entry.get("cache_key") != cache_key or not image_path or not os.path.exists(image_path):
            return False
        plane_entry = self._ensure_silhouette_plane(offset, camera_shape)
        try:
            cmds.setAttr(plane_entry["shape"] + ".imageName", image_path, type="string")
            cmds.setAttr(plane_entry["shape"] + ".visibility", 1)
        except Exception:
            return False
        return True

    def _silhouette_capture_offsets(self, desired_offsets):
        offsets = list(desired_offsets)
        if not offsets:
            return []
        if not self._fast_silhouette_is_live_preview():
            self._silhouette_live_cursor = 0
            return offsets

        budget = max(1, min(FAST_SILHOUETTE_LIVE_CAPTURE_BUDGET, len(offsets)))
        missing = []
        for offset in offsets:
            plane_entry = self.silhouette_image_planes.get(offset) or {}
            if not cmds.objExists(plane_entry.get("shape", "")):
                missing.append(offset)
        if len(missing) >= budget:
            return missing[:budget]

        chosen = list(missing)
        remaining = [offset for offset in offsets if offset not in chosen]
        if not remaining:
            return chosen

        start_index = self._silhouette_live_cursor % len(remaining)
        rotated = remaining[start_index:] + remaining[:start_index]
        needed = max(0, budget - len(chosen))
        chosen.extend(rotated[:needed])
        if needed:
            self._silhouette_live_cursor = (start_index + needed) % len(remaining)
        return chosen

    def _silhouette_plane_visibility_state(self):
        state = {}
        for entry in list(self.silhouette_image_planes.values()):
            shape_name = entry.get("shape") or ""
            if not shape_name or not cmds.objExists(shape_name):
                continue
            try:
                state[shape_name] = bool(cmds.getAttr(shape_name + ".visibility"))
                cmds.setAttr(shape_name + ".visibility", 0)
            except Exception:
                pass
        return state

    def _restore_silhouette_plane_visibility(self, state):
        for shape_name, is_visible in (state or {}).items():
            if not cmds.objExists(shape_name):
                continue
            try:
                cmds.setAttr(shape_name + ".visibility", int(bool(is_visible)))
            except Exception:
                pass

    def _scene_mesh_visibility_state(self, allowed_mesh_transforms):
        state = {}
        allowed = set((cmds.ls(allowed_mesh_transforms or [], long=True) or []))
        for mesh_shape in cmds.ls(type="mesh", long=True) or []:
            parents = cmds.listRelatives(mesh_shape, parent=True, fullPath=True) or []
            if not parents:
                continue
            transform_name = parents[0]
            if transform_name in allowed or transform_name in state:
                continue
            try:
                state[transform_name] = bool(cmds.getAttr(transform_name + ".visibility"))
                cmds.setAttr(transform_name + ".visibility", 0)
            except Exception:
                state.pop(transform_name, None)
        return state

    def _restore_scene_mesh_visibility(self, state):
        for transform_name, is_visible in (state or {}).items():
            if not cmds.objExists(transform_name):
                continue
            try:
                cmds.setAttr(transform_name + ".visibility", int(bool(is_visible)))
            except Exception:
                pass

    def _capture_silhouette_image(self, offset, sample_frame, resolution, color, alpha_value, camera_signature=None, manage_scene_mesh_visibility=True, refresh_serial=None):
        panel_name = _active_model_panel(require_focus=False)
        camera_name = _active_camera(panel_name)
        camera_shape = _camera_shape(camera_name)
        if not panel_name or not camera_name or not camera_shape:
            raise RuntimeError("Pick an active viewport camera first.")
        if self._is_refresh_stale(refresh_serial):
            self._stale_refresh_skip_count += 1
            return False
        camera_signature = camera_signature or self._current_view_signature(include_time=False)
        if self._reuse_silhouette_cache(offset, sample_frame, resolution, color, alpha_value, camera_shape, camera_signature):
            return False

        cache_dir = _silhouette_cache_dir()
        suffix = "live" if resolution == FAST_SILHOUETTE_LIVE_RESOLUTION else "refine"
        base_name = "{0}_{1}_{2:02d}".format(suffix, "past" if offset < 0 else "future", abs(offset))
        raw_base = os.path.join(cache_dir, base_name + "_raw")
        raw_path = raw_base + ".png"
        tinted_path = os.path.join(cache_dir, base_name + ".png")

        current_time = float(cmds.currentTime(query=True))
        original_selection = cmds.ls(selection=True, long=True) or []
        editor_state = {}
        background_state = {}
        hidden_plane_state = {}
        hidden_mesh_state = {}
        cache_key = self._silhouette_cache_key(sample_frame, resolution, color, alpha_value, camera_signature)

        try:
            self._silhouette_capture_active = True
            for flag_name in ("displayAppearance", "displayLights", "useDefaultMaterial", "displayTextures", "nurbsCurves", "joints", "locators", "manipulators"):
                try:
                    editor_state[flag_name] = cmds.modelEditor(panel_name, query=True, **{flag_name: True})
                except Exception:
                    pass
            for color_name in ("background", "backgroundTop", "backgroundBottom"):
                try:
                    background_state[color_name] = cmds.displayRGBColor(color_name, query=True)
                except Exception:
                    pass

            hidden_plane_state = self._silhouette_plane_visibility_state()
            if manage_scene_mesh_visibility:
                hidden_mesh_state = self._scene_mesh_visibility_state([mesh_entry["transform"] for mesh_entry in self.source_meshes])
            if background_state:
                for color_name in background_state:
                    cmds.displayRGBColor(color_name, 0.0, 0.0, 0.0)
            try:
                cmds.modelEditor(
                    panel_name,
                    edit=True,
                    displayAppearance="smoothShaded",
                    displayLights="default",
                    useDefaultMaterial=True,
                    displayTextures=False,
                    nurbsCurves=False,
                    joints=False,
                    locators=False,
                    manipulators=False,
                )
            except Exception:
                pass

            cmds.currentTime(sample_frame, edit=True, update=True)
            returned_path = cmds.playblast(
                format="image",
                compression="png",
                viewer=False,
                showOrnaments=False,
                offScreen=True,
                forceOverwrite=True,
                clearCache=True,
                frame=[sample_frame],
                widthHeight=list(resolution),
                editorPanelName=panel_name,
                filename=raw_base,
                percent=100,
            )
            if returned_path and os.path.exists(returned_path):
                raw_path = returned_path
            elif os.path.exists(raw_base):
                raw_path = raw_base
            if not os.path.exists(raw_path):
                matches = sorted(glob.glob(raw_base + "*.png"))
                if matches:
                    raw_path = matches[-1]
            if not os.path.exists(raw_path):
                raise RuntimeError("Playblast did not create the silhouette image.")
            if self._is_refresh_stale(refresh_serial):
                self._stale_refresh_skip_count += 1
                return False
            filled_pixels = _tint_silhouette_image(raw_path, tinted_path, color, alpha_value)
            if filled_pixels <= 0:
                raise RuntimeError("Silhouette capture was empty.")
        finally:
            self._silhouette_capture_active = False
            try:
                cmds.currentTime(current_time, edit=True, update=True)
            except Exception:
                pass
            for flag_name, value in editor_state.items():
                try:
                    cmds.modelEditor(panel_name, edit=True, **{flag_name: value})
                except Exception:
                    pass
            for color_name, value in background_state.items():
                try:
                    cmds.displayRGBColor(color_name, value[0], value[1], value[2])
                except Exception:
                    pass
            self._restore_silhouette_plane_visibility(hidden_plane_state)
            if manage_scene_mesh_visibility:
                self._restore_scene_mesh_visibility(hidden_mesh_state)
            if original_selection:
                try:
                    cmds.select(original_selection, replace=True)
                except Exception:
                    pass
            else:
                try:
                    cmds.select(clear=True)
                except Exception:
                    pass

        if self._is_refresh_stale(refresh_serial):
            self._stale_refresh_skip_count += 1
            return False
        plane_entry = self._ensure_silhouette_plane(offset, camera_shape)
        cmds.setAttr(plane_entry["shape"] + ".imageName", tinted_path, type="string")
        cmds.setAttr(plane_entry["shape"] + ".visibility", 1)
        self.silhouette_cache[offset] = {
            "image_path": tinted_path,
            "resolution": resolution,
            "camera": camera_shape,
            "frame": float(sample_frame),
            "cache_key": cache_key,
        }
        return True

    def _refresh_fast_silhouette(self, desired_offsets, current_time, refresh_serial=None):
        panel_name = _active_model_panel(require_focus=False)
        camera_name = _active_camera(panel_name)
        camera_shape = _camera_shape(camera_name)
        if not panel_name or not camera_shape:
            raise RuntimeError("Click into a Maya viewport first so Fast Silhouette knows which camera to use.")
        resolution = self._fast_silhouette_resolution()
        camera_signature = self._current_view_signature(include_time=False)
        capture_offsets = self._silhouette_capture_offsets(desired_offsets)
        capture_failures = []
        any_visible = False
        stale_refresh = False
        hidden_mesh_state = self._scene_mesh_visibility_state([mesh_entry["transform"] for mesh_entry in self.source_meshes]) if capture_offsets else {}
        try:
            for offset in capture_offsets:
                if self._is_refresh_stale(refresh_serial):
                    stale_refresh = True
                    break
                sample_frame = float(current_time) + offset
                try:
                    self._capture_silhouette_image(
                        offset,
                        sample_frame,
                        resolution,
                        self._offset_color(offset),
                        self._offset_alpha(offset),
                        camera_signature=camera_signature,
                        manage_scene_mesh_visibility=False,
                        refresh_serial=refresh_serial,
                    )
                except Exception as exc:
                    capture_failures.append("{0}: {1}".format(offset, exc))
                if self._is_refresh_stale(refresh_serial):
                    stale_refresh = True
                    break
        finally:
            self._restore_scene_mesh_visibility(hidden_mesh_state)
        if stale_refresh:
            return
        active_keys = set(desired_offsets)
        for offset, entry in list(self.silhouette_image_planes.items()):
            if offset not in active_keys and cmds.objExists(entry.get("shape", "")):
                try:
                    cmds.setAttr(entry["shape"] + ".visibility", 0)
                except Exception:
                    pass
                continue
            if cmds.objExists(entry.get("shape", "")):
                any_visible = True

        if capture_failures:
            self._warn_silhouette_once(
                "Fast Silhouette kept the previous preview for some offsets while Maya updated: {0}".format(
                    capture_failures[0]
                )
            )
        if not any_visible and capture_failures:
            raise RuntimeError(capture_failures[0])

    def _refresh_with_context(self, desired_offsets, current_time, visible_mesh_entries):
        for offset in desired_offsets:
            sample_time = om.MTime(float(current_time) + offset, om.MTime.uiUnit())
            for mesh_entry in visible_mesh_entries:
                points, matrix = self._sample_mesh_state(mesh_entry, sample_time)
                ghost_entry = self._ensure_ghost_entry(offset, mesh_entry)
                self._apply_state_to_ghost(ghost_entry, points, matrix)
                self._set_ghost_visibility(ghost_entry, True)

    def _refresh_with_timeline(self, desired_offsets, current_time, visible_mesh_entries):
        for offset in desired_offsets:
            sample_frame = current_time + offset
            cmds.currentTime(sample_frame, edit=True, update=True)
            for mesh_entry in visible_mesh_entries:
                points, matrix = self._sample_live_mesh_state(mesh_entry)
                ghost_entry = self._ensure_ghost_entry(offset, mesh_entry)
                self._apply_state_to_ghost(ghost_entry, points, matrix)
                self._set_ghost_visibility(ghost_entry, True)

    def _ensure_source_paths(self, mesh_entry):
        shape_path = mesh_entry.get("shape_path")
        transform_path = mesh_entry.get("transform_path")
        try:
            if shape_path:
                shape_path.fullPathName()
            if transform_path:
                transform_path.fullPathName()
        except Exception:
            shape_path = None
            transform_path = None

        if shape_path is None:
            shape_path = _dag_path(mesh_entry["shape"])
            mesh_entry["shape_path"] = shape_path
        if transform_path is None:
            transform_path = _dag_path(mesh_entry["transform"])
            mesh_entry["transform_path"] = transform_path
        return shape_path, transform_path

    def _sample_mesh_state(self, mesh_entry, sample_time):
        shape_path, transform_path = self._ensure_source_paths(mesh_entry)

        transform_dep = om.MFnDependencyNode(transform_path.node())
        world_matrix_plug = transform_dep.findPlug("worldMatrix", False).elementByLogicalIndex(0)
        matrix_data = world_matrix_plug.asMObject(om.MDGContext(sample_time))
        if matrix_data.isNull():
            raise RuntimeError("Null worldMatrix sample for {0}".format(mesh_entry["transform"]))
        matrix = om.MFnMatrixData(matrix_data).matrix()

        if not mesh_entry["is_deformed"]:
            return None, matrix

        shape_dep = om.MFnDependencyNode(shape_path.node())
        out_mesh_plug = shape_dep.findPlug("outMesh", False)
        mesh_data = out_mesh_plug.asMObject(om.MDGContext(sample_time))
        if mesh_data.isNull():
            raise RuntimeError("Null outMesh sample for {0}".format(mesh_entry["shape"]))

        sampled_mesh = om.MFnMesh(mesh_data)
        points = sampled_mesh.getPoints(om.MSpace.kObject)
        return points, matrix

    def _sample_live_mesh_state(self, mesh_entry):
        shape_path, transform_path = self._ensure_source_paths(mesh_entry)
        matrix = transform_path.inclusiveMatrix()
        if not mesh_entry["is_deformed"]:
            return None, matrix
        points = om.MFnMesh(shape_path).getPoints(om.MSpace.kObject)
        return points, matrix

    def _ensure_ghost_entry(self, offset, mesh_entry):
        slot = self.ghost_cache[offset]
        ghost_entry = slot["entries"].get(mesh_entry["shape"])
        if ghost_entry and cmds.objExists(ghost_entry["transform"]) and cmds.objExists(ghost_entry["shape"]):
            return ghost_entry

        source_shape_path, _ = self._ensure_source_paths(mesh_entry)

        ghost_transform = cmds.createNode(
            "transform",
            name=self._ghost_name(offset, mesh_entry),
            parent=slot["group"],
        )
        self._prepare_ghost_transform(ghost_transform)

        ghost_transform_path = _dag_path(ghost_transform)
        ghost_mesh_object = om.MFnMesh().copy(source_shape_path.node(), ghost_transform_path.node())
        ghost_shape_name = om.MFnDagNode(ghost_mesh_object).fullPathName()
        self._assign_material(offset, ghost_transform)

        ghost_entry = {
            "transform": ghost_transform,
            "shape": ghost_shape_name,
            "shape_path": _dag_path(ghost_shape_name),
            "transform_path": ghost_transform_path,
            "visible": False,
        }
        slot["entries"][mesh_entry["shape"]] = ghost_entry
        return ghost_entry

    def _prepare_ghost_transform(self, transform):
        for attribute in ("visibility", "overrideEnabled", "overrideDisplayType"):
            _unlock_and_disconnect_attr("{0}.{1}".format(transform, attribute))

        cmds.setAttr("{0}.overrideEnabled".format(transform), 1)
        cmds.setAttr("{0}.overrideDisplayType".format(transform), 2)
        for attribute in ("translate", "rotate", "scale"):
            for axis in ("X", "Y", "Z"):
                attr_name = "{0}.{1}{2}".format(transform, attribute, axis)
                if cmds.objExists(attr_name):
                    try:
                        _unlock_and_disconnect_attr(attr_name)
                        cmds.setAttr(attr_name, lock=False, keyable=False, channelBox=False)
                    except Exception:
                        pass

    def _assign_material(self, offset, transform):
        shader_info = self.material_cache[offset]
        cmds.sets(transform, edit=True, forceElement=shader_info["shading_group"])

    def _apply_state_to_ghost(self, ghost_entry, points, matrix):
        ghost_shape_path = ghost_entry.get("shape_path")
        ghost_transform_path = ghost_entry.get("transform_path")
        try:
            if ghost_shape_path:
                ghost_shape_path.fullPathName()
            if ghost_transform_path:
                ghost_transform_path.fullPathName()
        except Exception:
            ghost_shape_path = None
            ghost_transform_path = None

        if ghost_shape_path is None:
            ghost_shape_path = _dag_path(ghost_entry["shape"])
            ghost_entry["shape_path"] = ghost_shape_path
        if ghost_transform_path is None:
            ghost_transform_path = _dag_path(ghost_entry["transform"])
            ghost_entry["transform_path"] = ghost_transform_path

        if points is not None:
            ghost_mesh = om.MFnMesh(ghost_shape_path)
            ghost_mesh.setPoints(points, om.MSpace.kObject)

        if isinstance(matrix, om.MMatrix):
            world_matrix = matrix
        else:
            world_matrix = om.MMatrix(matrix)

        try:
            om.MFnTransform(ghost_transform_path).setTransformation(om.MTransformationMatrix(world_matrix))
        except Exception:
            cmds.xform(
                ghost_entry["transform"],
                matrix=_matrix_to_list(world_matrix),
                worldSpace=True,
            )

    def _set_ghost_visibility(self, ghost_entry, visible):
        desired_state = bool(visible)
        if ghost_entry.get("visible") == desired_state:
            return
        cmds.setAttr("{0}.visibility".format(ghost_entry["transform"]), int(desired_state))
        ghost_entry["visible"] = desired_state

    def _hide_cached_ghost(self, offset, mesh_entry):
        slot = self.ghost_cache.get(offset)
        if not slot:
            return
        ghost_entry = slot["entries"].get(mesh_entry["shape"])
        if ghost_entry and cmds.objExists(ghost_entry["transform"]):
            self._set_ghost_visibility(ghost_entry, False)

    def _ghost_name(self, offset, mesh_entry):
        source_transform = mesh_entry["transform"]
        base_name = source_transform.split("|")[-1].replace(":", "_")
        direction = "past" if offset < 0 else "future"
        unique_suffix = hashlib.md5(mesh_entry["shape"].encode("utf-8")).hexdigest()[:8]
        return "{0}_{1}_{2:02d}_{3}_{4}".format(PREFIX, direction, abs(offset), base_name, unique_suffix)


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
        if MQtUtil.mainWindow() is not None:
            _WindowBase = type("MayaOnionSkinBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
        else:
            _WindowBase = type("MayaOnionSkinBase", (QtWidgets.QDialog,), {})
    except Exception:
        _WindowBase = type("MayaOnionSkinBase", (QtWidgets.QDialog,), {})


    class MayaOnionSkinWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaOnionSkinWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self._syncing_ui = False

            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Onion Skin")
            self.setMinimumSize(360, 360)
            self.resize(520, 560)
            self._build_ui()
            self._populate_from_controller()

        def _build_ui(self):
            outer_layout = QtWidgets.QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName("mayaOnionSkinContentScroll")
            scroll.setWidgetResizable(True)
            scroll.setMinimumWidth(0)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            content = QtWidgets.QWidget()
            content.setMinimumWidth(0)
            main_layout = QtWidgets.QVBoxLayout(content)
            main_layout.setContentsMargins(12, 12, 12, 12)
            main_layout.setSpacing(10)

            description = QtWidgets.QLabel(
                "Pick a character, then this tool draws see-through copies on earlier and later frames so you can see the motion path."
            )
            description.setWordWrap(True)
            main_layout.addWidget(description)

            form_layout = QtWidgets.QFormLayout()
            form_layout.setLabelAlignment(_qt_flag("AlignmentFlag", "AlignLeft", 0))
            form_layout.setFormAlignment(_qt_flag("AlignmentFlag", "AlignTop", 0))

            self.display_mode_combo = QtWidgets.QComboBox()
            for label, value in MODE_ITEMS:
                self.display_mode_combo.addItem(label, value)
            self.display_mode_combo.setToolTip("3D Ghost keeps real 3D meshes. Fast Silhouette uses a camera-based live preview that refreshes low-res while you move, then sharpens when you stop.")
            form_layout.addRow("Preview Mode", self.display_mode_combo)

            self.past_spin = QtWidgets.QSpinBox()
            self.past_spin.setRange(0, MAX_FRAMES_PER_SIDE)
            self.past_spin.setToolTip("How many frames behind the current frame to show.")
            form_layout.addRow("Past Frames", self.past_spin)

            self.future_spin = QtWidgets.QSpinBox()
            self.future_spin.setRange(0, MAX_FRAMES_PER_SIDE)
            self.future_spin.setToolTip("How many frames ahead of the current frame to show.")
            form_layout.addRow("Future Frames", self.future_spin)

            self.frame_step_spin = QtWidgets.QSpinBox()
            self.frame_step_spin.setRange(1, MAX_FRAME_STEP)
            self.frame_step_spin.setToolTip("Show every Nth frame. A value of 2 shows every other frame.")
            form_layout.addRow("Frame Step", self.frame_step_spin)

            self.opacity_spin = QtWidgets.QDoubleSpinBox()
            self.opacity_spin.setRange(0.05, 1.0)
            self.opacity_spin.setSingleStep(0.05)
            self.opacity_spin.setDecimals(2)
            self.opacity_spin.setToolTip("How see-through the ghost copies should be.")
            form_layout.addRow("Opacity", self.opacity_spin)

            self.falloff_spin = QtWidgets.QDoubleSpinBox()
            self.falloff_spin.setRange(0.1, 4.0)
            self.falloff_spin.setSingleStep(0.1)
            self.falloff_spin.setDecimals(2)
            self.falloff_spin.setToolTip("How fast the far-away ghost copies fade out.")
            form_layout.addRow("Falloff", self.falloff_spin)

            self.past_color_button = QtWidgets.QPushButton()
            self.past_color_button.setToolTip("Pick the color for the ghosts behind the current frame.")
            form_layout.addRow("Past Color", self.past_color_button)

            self.future_color_button = QtWidgets.QPushButton()
            self.future_color_button.setToolTip("Pick the color for the ghosts ahead of the current frame.")
            form_layout.addRow("Future Color", self.future_color_button)

            self.auto_update_check = QtWidgets.QCheckBox("Auto Update")
            self.auto_update_check.setToolTip("Update the ghost copies while you scrub the timeline.")
            form_layout.addRow("", self.auto_update_check)

            self.full_fidelity_scrub_check = QtWidgets.QCheckBox("Show Every Ghost While Scrubbing (Slower)")
            self.full_fidelity_scrub_check.setToolTip(
                "Show the full onion skin while scrubbing. This looks better but can be slower."
            )
            form_layout.addRow("", self.full_fidelity_scrub_check)

            main_layout.addLayout(form_layout)

            button_layout = QtWidgets.QHBoxLayout()
            self.attach_button = QtWidgets.QPushButton("Use Current Selection")
            self.attach_button.setToolTip("Use the selected character or rig root.")
            self.add_button = QtWidgets.QPushButton("Add Selected")
            self.add_button.setToolTip("Add another selected character or rig root to the onion skin list.")
            self.refresh_button = QtWidgets.QPushButton("Refresh")
            self.refresh_button.setToolTip("Rebuild the ghost copies right now.")
            self.clear_button = QtWidgets.QPushButton("Clear")
            self.clear_button.setToolTip("Remove all ghost copies and detach everything.")
            button_layout.addWidget(self.attach_button)
            button_layout.addWidget(self.add_button)
            button_layout.addWidget(self.refresh_button)
            button_layout.addWidget(self.clear_button)
            main_layout.addLayout(button_layout)

            self.status_label = QtWidgets.QLabel("Pick one or more characters, then click Attach Selected.")
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
            scroll.setWidget(content)
            outer_layout.addWidget(scroll)

            self.attach_button.clicked.connect(self._attach_selected)
            self.add_button.clicked.connect(self._add_selected)
            self.refresh_button.clicked.connect(self._refresh)
            self.clear_button.clicked.connect(self._clear)
            self.donate_button.clicked.connect(self._open_donate_url)
            self.display_mode_combo.currentIndexChanged.connect(self._settings_changed)
            self.auto_update_check.toggled.connect(self._settings_changed)
            self.full_fidelity_scrub_check.toggled.connect(self._settings_changed)
            self.past_spin.valueChanged.connect(self._settings_changed)
            self.future_spin.valueChanged.connect(self._settings_changed)
            self.frame_step_spin.valueChanged.connect(self._settings_changed)
            self.opacity_spin.valueChanged.connect(self._settings_changed)
            self.falloff_spin.valueChanged.connect(self._settings_changed)
            self.past_color_button.clicked.connect(lambda: self._pick_color("past"))
            self.future_color_button.clicked.connect(lambda: self._pick_color("future"))

        def _populate_from_controller(self):
            self._syncing_ui = True
            try:
                mode_index = self.display_mode_combo.findData(self.controller.display_mode)
                self.display_mode_combo.setCurrentIndex(0 if mode_index < 0 else mode_index)
                self.past_spin.setValue(self.controller.past_frames)
                self.future_spin.setValue(self.controller.future_frames)
                self.frame_step_spin.setValue(self.controller.frame_step)
                self.opacity_spin.setValue(self.controller.opacity)
                self.falloff_spin.setValue(self.controller.falloff)
                self.auto_update_check.setChecked(self.controller.auto_update)
                self.full_fidelity_scrub_check.setChecked(self.controller.full_fidelity_scrub)
                _shape_color(self.past_color_button, self.controller.past_color)
                _shape_color(self.future_color_button, self.controller.future_color)
                self.status_label.setText(self.controller.attachment_summary())
                self.full_fidelity_scrub_check.setEnabled(self.controller.display_mode == MODE_3D_GHOST)
            finally:
                self._syncing_ui = False

        def _current_settings(self):
            return {
                "display_mode": self.display_mode_combo.currentData(),
                "past_frames": self.past_spin.value(),
                "future_frames": self.future_spin.value(),
                "frame_step": self.frame_step_spin.value(),
                "opacity": self.opacity_spin.value(),
                "falloff": self.falloff_spin.value(),
                "auto_update": self.auto_update_check.isChecked(),
                "full_fidelity_scrub": self.full_fidelity_scrub_check.isChecked(),
                "past_color": self.controller.past_color,
                "future_color": self.controller.future_color,
            }

        def _apply_settings(self):
            if self._syncing_ui:
                return
            current = self._current_settings()
            self.controller.set_settings(
                current["past_frames"],
                current["future_frames"],
                current["frame_step"],
                current["opacity"],
                current["falloff"],
                current["auto_update"],
                current["full_fidelity_scrub"],
                current["past_color"],
                current["future_color"],
                current["display_mode"],
            )
            self.full_fidelity_scrub_check.setEnabled(self.controller.display_mode == MODE_3D_GHOST)

        def _settings_changed(self, *args):
            self._apply_settings()
            if self.controller.attached_roots:
                success, message = self.controller.refresh(rebuild=False, reason="ui")
                self._set_status(message, success)

        def _pick_color(self, direction):
            existing = self.controller.past_color if direction == "past" else self.controller.future_color
            dialog_color = QtGui.QColor.fromRgbF(existing[0], existing[1], existing[2], 1.0)
            selected = QtWidgets.QColorDialog.getColor(dialog_color, self, "Choose {0} color".format(direction))
            if not selected.isValid():
                return

            color = (selected.redF(), selected.greenF(), selected.blueF())
            if direction == "past":
                self.controller.past_color = color
                _shape_color(self.past_color_button, color)
            else:
                self.controller.future_color = color
                _shape_color(self.future_color_button, color)

            self._settings_changed()

        def _attach_selected(self):
            self._apply_settings()
            success, message = self.controller.attach_selection()
            self._populate_from_controller()
            self._set_status(message, success)

        def _add_selected(self):
            self._apply_settings()
            success, message = self.controller.attach_selection(add=True)
            self._populate_from_controller()
            self._set_status(message, success)

        def _refresh(self):
            self._apply_settings()
            success, message = self.controller.manual_refresh()
            self._populate_from_controller()
            self._set_status(message, success)

        def _clear(self):
            self.controller.detach(clear_attachment=True)
            self._populate_from_controller()
            self._set_status("Cleared ghosts and detached all rigs.", True)

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

        def _set_status(self, message, success):
            self.status_label.setText(message)
            if success:
                _debug(message)
            else:
                _warning(message)

        def closeEvent(self, event):
            # Keep the Qt wrapper alive. Native Maya workspace destruction can
            # invalidate callbacks and crash Maya 2026 during close.
            self.hide()
            event.ignore()


def launch_maya_onion_skin(dock=False):
    """
    Launch the Maya Onion Skin tool.

    Args:
        dock (bool): Try to use a dockable Maya window when available.
    """

    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW

    if not MAYA_AVAILABLE:
        raise RuntimeError("maya_onion_skin.launch_maya_onion_skin() must run inside Autodesk Maya.")
    if not QtWidgets:
        raise RuntimeError("PySide is not available in this Maya session.")

    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
            GLOBAL_CONTROLLER = None

    GLOBAL_CONTROLLER = MayaOnionSkinController()
    GLOBAL_WINDOW = MayaOnionSkinWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())

    if dock:
        try:
            GLOBAL_WINDOW.show(dockable=True, floating=False, area="right")
        except Exception:
            GLOBAL_WINDOW.show()
    else:
        GLOBAL_WINDOW.show()

    GLOBAL_WINDOW.raise_()
    GLOBAL_WINDOW.activateWindow()
    return GLOBAL_WINDOW


__all__ = ["launch_maya_onion_skin", "install_maya_onion_skin_shelf_button", "MayaOnionSkinController"]
