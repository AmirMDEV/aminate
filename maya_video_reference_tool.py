"""
maya_video_reference_tool.py

Import a video or image sequence as an image plane, optionally line up audio,
and jump into Maya's native drawing tools for frame-by-frame notes.
"""

from __future__ import absolute_import, division, print_function

import hashlib
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

import maya_skinning_cleanup as skin_cleanup

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    import maya.mel as mel

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    mel = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtCore, QtGui, QtWidgets

    QT_BINDING = "PySide6"
except Exception:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets

        QT_BINDING = "PySide2"
    except Exception:
        QtCore = None
        QtGui = None
        QtWidgets = None
        QT_BINDING = None


WINDOW_OBJECT_NAME = "mayaVideoReferenceWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
MEDIA_FILTER = "Media Files (*.mov *.mp4 *.avi *.m4v *.mkv *.png *.jpg *.jpeg *.tif *.tiff *.exr *.iff *.bmp *.gif)"
AUDIO_FILTER = "Audio Files (*.wav *.aiff *.aif *.mp3)"
REFERENCE_GROUP_NAME = "amirVideoReference_GRP"
ANNOTATION_GROUP_NAME = "amirVideoAnnotations_GRP"
ANNOTATION_SURFACE_MATERIAL = "amirVideoAnnotationSurface_MAT"
ANNOTATION_WINDOW_OBJECT_NAME = "mayaVideoAnnotationManagerWindow"
VIDEO_OPACITY_ATTR = "amirVideoOpacity"
VIDEO_AUDIO_ENABLED_ATTR = "amirVideoAudioEnabled"
PROXY_CACHE_DIR_NAME = "amir_maya_video_reference"
VIDEO_EXTENSIONS = {".mov", ".mp4", ".avi", ".m4v", ".mkv", ".mpg", ".mpeg", ".wmv", ".webm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".iff", ".bmp", ".gif"}
QIMAGE_REQUIRED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"}
MAX_PROXY_FRAME_COUNT = 1800
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 60
SEQUENCE_PATTERN = re.compile(r"(.*?)(\d+)(\.[^.]+)$")
PLACEMENT_MODE_ITEMS = [
    ("tracing_card", "Behind Picked Object"),
    ("follow_target", "Follow Picked Object"),
    ("camera_overlay", "Camera Overlay"),
]
PLACEMENT_MODE_LABELS = dict(PLACEMENT_MODE_ITEMS)

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None
GLOBAL_ANNOTATION_WINDOW = None

_style_donate_button = skin_cleanup._style_donate_button
_open_external_url = skin_cleanup._open_external_url
_maya_main_window = skin_cleanup._maya_main_window
_short_name = skin_cleanup._short_name


def _debug(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayInfo("[Maya Video Reference] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayWarning("[Maya Video Reference] {0}".format(message))


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
        if cmds.modelEditor(panel, query=True, exists=True):
            return panel
    return ""


def _active_camera(require_focus=False):
    panel = _active_model_panel(require_focus=require_focus)
    if not panel:
        return ""
    camera_name = cmds.modelEditor(panel, query=True, camera=True)
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


def _isolate_camera_overlay_to_assigned_view(shape_name):
    """Make a camera-attached overlay invisible from every other viewport.

    Maya image planes default to appearing in other model panels even when
    they are connected to a camera.  Animator's Pencil uses a retained model
    panel for reference, so its overlay must be visible only while that exact
    Pencil View camera is current.
    """
    if not shape_name or not cmds.objExists(shape_name):
        return False, "Camera overlay image plane is missing."
    attribute = shape_name + ".displayOnlyIfCurrent"
    if not cmds.objExists(attribute):
        return False, "This image plane cannot be limited to its assigned camera."
    try:
        cmds.setAttr(attribute, True)
        if not bool(cmds.getAttr(attribute)):
            return False, "Maya did not keep the camera-only overlay setting."
    except Exception as exc:
        return False, "Could not limit the camera overlay to its Pencil View: {0}".format(exc)
    return True, "Camera overlay is visible only in its assigned view."


def _ensure_reference_group():
    if cmds.objExists(REFERENCE_GROUP_NAME):
        return REFERENCE_GROUP_NAME
    group_name = cmds.createNode("transform", name=REFERENCE_GROUP_NAME)
    try:
        cmds.setAttr(group_name + ".visibility", 0)
        cmds.setAttr(group_name + ".visibility", 1)
    except Exception:
        pass
    return group_name


def _ensure_annotation_group():
    if cmds.objExists(ANNOTATION_GROUP_NAME):
        return ANNOTATION_GROUP_NAME
    return cmds.createNode("transform", name=ANNOTATION_GROUP_NAME)


def _playback_slider():
    try:
        if cmds.about(batch=True):
            return ""
    except Exception:
        pass
    try:
        slider = mel.eval("$tmpVar=$gPlayBackSlider")
    except Exception:
        return ""
    try:
        if slider and cmds.control(slider, exists=True):
            return slider
    except Exception:
        pass
    return ""


def _camera_transform_from_image_plane(shape_name):
    if not MAYA_AVAILABLE or not shape_name or not cmds.objExists(shape_name):
        return ""
    connections = []
    for attr_name in ("camera", "lookThroughCamera"):
        try:
            if cmds.attributeQuery(attr_name, node=shape_name, exists=True):
                connections.extend(cmds.listConnections(shape_name + "." + attr_name, source=True, destination=False) or [])
        except Exception:
            continue
    try:
        connections.extend(cmds.listConnections(shape_name, type="camera") or [])
    except Exception:
        pass
    for connection in connections:
        if not connection or not cmds.objExists(connection):
            continue
        if cmds.nodeType(connection) == "camera":
            parents = cmds.listRelatives(connection, parent=True, fullPath=True) or []
            return _long_name(parents[0] if parents else connection)
        if cmds.nodeType(connection) == "transform":
            return _long_name(connection)
    return ""


def _ensure_string_attr(node_name, attr_name):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, dataType="string")


def _ensure_long_attr(node_name, attr_name):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="long")


def _ensure_double_attr(node_name, attr_name):
    if not node_name or not cmds.objExists(node_name):
        return
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        cmds.addAttr(node_name, longName=attr_name, attributeType="double")


def _clamp_opacity(value, default=0.8):
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return float(default)


def _get_string_attr(node_name, attr_name, default_value=""):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return default_value
    try:
        return cmds.getAttr(node_name + "." + attr_name) or default_value
    except Exception:
        return default_value


def _get_long_attr(node_name, attr_name, default_value=0):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        return default_value
    try:
        return int(round(float(cmds.getAttr(node_name + "." + attr_name))))
    except Exception:
        return default_value


def _get_double_attr(node_name, attr_name, default_value=0.0):
    if not node_name or not cmds.objExists(node_name):
        return None if default_value is None else float(default_value)
    try:
        if cmds.attributeQuery(attr_name, node=node_name, exists=True):
            return float(cmds.getAttr(node_name + "." + attr_name))
    except Exception:
        pass
    return None if default_value is None else float(default_value)


def _set_string_attr(node_name, attr_name, value):
    _ensure_string_attr(node_name, attr_name)
    cmds.setAttr(node_name + "." + attr_name, value or "", type="string")


def _set_long_attr(node_name, attr_name, value):
    _ensure_long_attr(node_name, attr_name)
    cmds.setAttr(node_name + "." + attr_name, int(value))


def _long_name(node_name):
    matches = cmds.ls(node_name, long=True) or []
    return matches[0] if matches else node_name


def _selected_transform():
    selection = cmds.ls(selection=True, long=True) or []
    for item in selection:
        if cmds.nodeType(item) == "transform":
            return item
        parents = cmds.listRelatives(item, parent=True, fullPath=True) or []
        if parents and cmds.nodeType(parents[0]) == "transform":
            return parents[0]
    return ""


def _scene_fps():
    if not MAYA_AVAILABLE:
        return 24.0
    unit_name = cmds.currentUnit(query=True, time=True) or "film"
    mapping = {
        "game": 15.0,
        "film": 24.0,
        "pal": 25.0,
        "ntsc": 30.0,
        "show": 48.0,
        "palf": 50.0,
        "ntscf": 60.0,
    }
    if unit_name in mapping:
        return mapping[unit_name]
    if unit_name.endswith("fps"):
        try:
            return float(unit_name[:-3])
        except Exception:
            pass
    return 24.0


def _safe_make_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _proxy_cache_root():
    return _safe_make_dir(os.path.join(tempfile.gettempdir(), PROXY_CACHE_DIR_NAME))


def _proxy_frame_count(start_frame):
    if not MAYA_AVAILABLE:
        return 120
    playback_end = int(round(float(cmds.playbackOptions(query=True, maxTime=True))))
    return max(1, playback_end - int(start_frame) + 1)


def _hash_media_path(media_path, fps_value, frame_count):
    try:
        stat_info = os.stat(media_path)
        payload = {
            "path": os.path.abspath(media_path).lower(),
            "mtime_ns": int(getattr(stat_info, "st_mtime_ns", int(stat_info.st_mtime * 1000000000))),
            "size": int(stat_info.st_size),
            "fps": float(fps_value),
            "frame_count": int(frame_count),
        }
    except Exception:
        payload = {"path": os.path.abspath(media_path).lower(), "fps": float(fps_value), "frame_count": int(frame_count)}
    payload_json = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha1(payload_json).hexdigest()[:16]


def _run_process(command):
    kwargs = {
        "check": False,
        "capture_output": True,
        "text": True,
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run(command, timeout=PROCESS_TIMEOUT_SECONDS, **kwargs)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timed out preparing video media after {0} seconds.".format(PROCESS_TIMEOUT_SECONDS))
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Command failed.").strip())
    return completed


def _validate_image_plane_media(image_path):
    if not image_path or not os.path.exists(image_path):
        return False, "Maya could not find the prepared media frame."
    extension = os.path.splitext(image_path)[1].lower()
    if extension not in IMAGE_EXTENSIONS:
        return False, "Maya image planes only accept prepared image files, not {0}.".format(extension or "unknown media")
    try:
        first_stat = os.stat(image_path)
        if int(first_stat.st_size) <= 0:
            return False, "The prepared media frame is empty."
        time.sleep(0.05)
        second_stat = os.stat(image_path)
        if int(first_stat.st_size) != int(second_stat.st_size):
            return False, "The prepared media frame is still being written."
    except Exception as exc:
        return False, "Could not read the prepared media frame: {0}".format(exc)
    if QtGui and extension in QIMAGE_REQUIRED_EXTENSIONS:
        try:
            reader = QtGui.QImageReader(image_path)
            if not reader.canRead():
                return False, "Maya could not read the prepared media frame."
            image_size = reader.size()
            if not image_size.isValid() or image_size.width() <= 0 or image_size.height() <= 0:
                return False, "The prepared media frame has no readable size."
        except Exception as exc:
            return False, "Could not validate the prepared media frame: {0}".format(exc)
    return True, ""


def _delete_created_node(node_name):
    if node_name and cmds and cmds.objExists(node_name):
        try:
            cmds.delete(node_name)
        except Exception:
            pass


def _image_aspect_ratio(image_path):
    if QtGui:
        try:
            reader = QtGui.QImageReader(image_path)
            image_size = reader.size()
            if image_size.isValid() and image_size.height() > 0:
                return float(image_size.width()) / float(image_size.height())
        except Exception:
            pass
    try:
        from PIL import Image  # pylint: disable=import-outside-toplevel

        with Image.open(image_path) as image:
            width, height = image.size
            if height:
                return float(width) / float(height)
    except Exception:
        pass
    return 16.0 / 9.0


def _sequence_start_frame(path):
    match = SEQUENCE_PATTERN.match(os.path.basename(path))
    if not match:
        return 1
    try:
        return int(match.group(2))
    except Exception:
        return 1


def _camera_world_position(camera_transform):
    matrix = om.MMatrix(cmds.xform(camera_transform, query=True, worldSpace=True, matrix=True))
    transform = om.MTransformationMatrix(matrix)
    return om.MVector(transform.translation(om.MSpace.kWorld))


def _camera_forward_vector(camera_transform):
    matrix = om.MMatrix(cmds.xform(camera_transform, query=True, worldSpace=True, matrix=True))
    transform = om.MTransformationMatrix(matrix)
    rotation = transform.rotation(asQuaternion=True)
    vector = om.MVector(0.0, 0.0, -1.0)
    return vector.rotateBy(rotation).normal()


def _world_position(node_name):
    values = cmds.xform(node_name, query=True, worldSpace=True, translation=True)
    return om.MVector(values[0], values[1], values[2])


def _world_rotation(node_name):
    return cmds.xform(node_name, query=True, worldSpace=True, rotation=True)


def _ensure_annotation_surface_shader():
    if cmds.objExists(ANNOTATION_SURFACE_MATERIAL):
        shading_group = cmds.listConnections(ANNOTATION_SURFACE_MATERIAL + ".outColor", type="shadingEngine") or []
        if shading_group:
            return ANNOTATION_SURFACE_MATERIAL, shading_group[0]
    material = cmds.shadingNode("lambert", asShader=True, name=ANNOTATION_SURFACE_MATERIAL)
    shading_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=ANNOTATION_SURFACE_MATERIAL + "SG")
    cmds.connectAttr(material + ".outColor", shading_group + ".surfaceShader", force=True)
    cmds.setAttr(material + ".color", 1.0, 0.92, 0.4, type="double3")
    cmds.setAttr(material + ".transparency", 0.92, 0.92, 0.92, type="double3")
    cmds.setAttr(material + ".ambientColor", 0.1, 0.1, 0.1, type="double3")
    return material, shading_group


def _apply_frame_settings(shape_name, start_frame, sequence_start_frame, opacity):
    cmds.setAttr(shape_name + ".useFrameExtension", 1)
    cmds.setAttr(shape_name + ".frameOffset", int(sequence_start_frame) - int(start_frame))
    # Do not reset Maya's camera-only flag here.  This helper is also used by
    # opacity and start-frame edits, so clearing it would leak the reference
    # image plane into every other model panel after an otherwise harmless UI
    # change.  Creation/placement paths assert the flag explicitly, and the
    # update paths below re-assert it for legacy overlays as well.
    try:
        cmds.setAttr(shape_name + ".alphaGain", float(opacity))
    except Exception:
        pass


def _create_proxy_from_video(media_path, extract_audio, start_frame):
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg was not found on this machine, so Maya cannot proxy this video yet.")
    try:
        if os.path.getsize(media_path) > MAX_MEDIA_BYTES:
            raise RuntimeError("The video is too large for the Maya UI importer. Use a shorter clip under 1 GB.")
    except OSError:
        pass

    fps_value = _scene_fps()
    required_frame_count = _proxy_frame_count(start_frame)
    if required_frame_count > MAX_PROXY_FRAME_COUNT:
        raise RuntimeError("The playback range is too long for safe UI import. Use {0} frames or fewer.".format(MAX_PROXY_FRAME_COUNT))
    cache_dir = _safe_make_dir(os.path.join(_proxy_cache_root(), _hash_media_path(media_path, fps_value, required_frame_count)))
    manifest_path = os.path.join(cache_dir, "proxy_manifest.json")
    first_frame = os.path.join(cache_dir, "frame_000001.png")
    last_frame = os.path.join(cache_dir, "frame_{0:06d}.png".format(int(required_frame_count)))
    audio_path = os.path.join(cache_dir, "audio.wav")

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as handle:
                manifest = json.load(handle)
            manifest_ok = (
                manifest.get("media_path") == os.path.abspath(media_path)
                and abs(float(manifest.get("fps", 0.0)) - float(fps_value)) < 0.001
                and int(manifest.get("frame_count", 0)) >= int(required_frame_count)
                and os.path.exists(first_frame)
                and os.path.exists(last_frame)
                and (not extract_audio or not manifest.get("audio_path") or os.path.exists(manifest.get("audio_path")))
            )
            if manifest_ok:
                return manifest
        except Exception:
            pass

    frame_pattern = os.path.join(cache_dir, "frame_%06d.png")
    _run_process(
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            media_path,
            "-vf",
            "fps={0}".format(fps_value),
            "-frames:v",
            str(int(required_frame_count)),
            frame_pattern,
        ]
    )

    audio_result_path = ""
    audio_error = ""
    if extract_audio:
        try:
            _run_process(
                [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    media_path,
                    "-vn",
                    "-acodec",
                    "pcm_s16le",
                    audio_path,
                ]
            )
            if os.path.exists(audio_path):
                audio_result_path = audio_path
        except Exception as exc:
            audio_error = str(exc)

    generated_frames = sorted(glob.glob(os.path.join(cache_dir, "frame_*.png")))
    actual_frame_count = len(generated_frames)
    actual_last_frame = generated_frames[-1] if generated_frames else ""
    if not os.path.exists(first_frame) or not actual_last_frame or not os.path.exists(actual_last_frame):
        raise RuntimeError("The proxy frames were not created from the video.")
    media_ok, media_error = _validate_image_plane_media(first_frame)
    if not media_ok:
        raise RuntimeError(media_error)

    manifest = {
        "media_path": os.path.abspath(media_path),
        "resolved_media_path": first_frame,
        "audio_path": audio_result_path,
        "audio_error": audio_error,
        "fps": fps_value,
        # A source clip may be shorter than Maya's playback range. ffmpeg then
        # correctly stops at the source's last frame, so record the frames that
        # really exist instead of rejecting a valid short video.
        "frame_count": int(actual_frame_count),
        "sequence_start_frame": 1,
        "aspect_ratio": _image_aspect_ratio(first_frame),
        "is_proxy": True,
    }
    with open(manifest_path, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
    return manifest


def _resolve_media_path(media_path, extract_audio, start_frame):
    extension = os.path.splitext(media_path)[1].lower()
    if extension in VIDEO_EXTENSIONS:
        return _create_proxy_from_video(media_path, extract_audio, start_frame=start_frame)
    return {
        "media_path": os.path.abspath(media_path),
        "resolved_media_path": media_path,
        "audio_path": "",
        "audio_error": "",
        "fps": _scene_fps(),
        "sequence_start_frame": _sequence_start_frame(media_path),
        "aspect_ratio": _image_aspect_ratio(media_path),
        "is_proxy": False,
    }


class MayaVideoReferenceController(object):
    def __init__(self):
        self.camera_name = _active_camera(require_focus=False) if MAYA_AVAILABLE else ""
        self.media_path = ""
        self.audio_path = ""
        self.start_frame = int(round(float(cmds.currentTime(query=True)))) if MAYA_AVAILABLE else 1
        self.import_audio = False
        self.placement_mode = "tracing_card"
        self.target_node = ""
        self.follow_x = True
        self.follow_y = True
        self.follow_z = False
        self.card_width = 8.0
        self.depth_offset = 8.0
        self.opacity = 0.8
        self.last_image_plane = ""
        self.last_transform = ""
        self.last_sound = ""
        self.last_follow_group = ""
        self.last_annotation_surface = ""
        self.last_media_info = {}
        self.camera_overlay_placement = "full_view"
        # Fraction of the full-view camera image-plane footprint.  PIP uses
        # 0.38 by default, but the Animator's Pencil UI can override this and
        # the value is persisted on the overlay transform for scene reopen.
        self.camera_overlay_scale = None
        self.keep_strokes_on_top = False
        self.status_callback = None

    def shutdown(self):
        pass

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _set_status(self, message, success=True):
        if self.status_callback:
            self.status_callback(message, success)
        if success:
            _debug(message)
        else:
            _warning(message)

    def use_active_camera(self):
        camera_name = _active_camera(require_focus=False)
        if not camera_name:
            return False, "Click a Maya viewport first so I know which view to use."
        self.camera_name = camera_name
        return True, "Using view {0}.".format(_short_name(camera_name))

    def set_target_from_selection(self):
        target_name = _selected_transform()
        if not target_name:
            return False, "Pick the object you want the tracing card to line up behind or follow."
        self.target_node = target_name
        return True, "Using {0} as the object to line up with.".format(_short_name(target_name))

    def _audio_path_for_import(self, media_info):
        if self.audio_path and os.path.exists(self.audio_path):
            return self.audio_path
        return media_info.get("audio_path") or ""

    def _reference_shape(self, transform_name):
        if not transform_name or not cmds.objExists(transform_name):
            return ""
        shapes = cmds.listRelatives(transform_name, shapes=True, fullPath=True, type="imagePlane") or []
        return shapes[0] if shapes else ""

    def _current_reference_transform(self):
        selection = cmds.ls(selection=True, long=True) or []
        for item in selection:
            node_type = cmds.nodeType(item)
            if node_type == "imagePlane":
                parents = cmds.listRelatives(item, parent=True, fullPath=True) or []
                if parents:
                    return parents[0]
            if node_type == "transform" and self._reference_shape(item):
                return item
        if self.last_transform and cmds.objExists(self.last_transform):
            return self.last_transform
        return ""

    def _tag_reference_transform(self, transform_name, media_info, sound_name):
        if not transform_name or not cmds.objExists(transform_name):
            return
        _set_long_attr(transform_name, "amirVideoSequenceStartFrame", int(media_info.get("sequence_start_frame", 1)))
        _set_long_attr(transform_name, "amirVideoStartFrame", int(self.start_frame))
        _set_string_attr(transform_name, "amirVideoSourcePath", media_info.get("media_path", ""))
        _set_string_attr(transform_name, "amirVideoResolvedPath", media_info.get("resolved_media_path", ""))
        _set_string_attr(transform_name, "amirVideoSoundNode", sound_name or "")
        _ensure_double_attr(transform_name, VIDEO_OPACITY_ATTR)
        cmds.setAttr(transform_name + "." + VIDEO_OPACITY_ATTR, _clamp_opacity(self.opacity))
        _ensure_long_attr(transform_name, VIDEO_AUDIO_ENABLED_ATTR)
        cmds.setAttr(transform_name + "." + VIDEO_AUDIO_ENABLED_ATTR, int(bool(sound_name)))

    def camera_overlay_transforms(self, camera_name=None):
        """Return tagged camera overlays for one Pencil View camera.

        This is deliberately scene-native and read-only.  The Pencil panel uses
        it before a new attach so repeated Attach Video clicks cannot leave
        several visible image planes on the same saved view.
        """
        if not MAYA_AVAILABLE:
            return []
        wanted = _long_name(camera_name) if camera_name and cmds.objExists(camera_name) else ""
        matches = []
        for node_name in cmds.ls(type="transform", long=True) or []:
            try:
                if not cmds.attributeQuery("amirVideoOverlayPlacement", node=node_name, exists=True):
                    continue
                shape_name = self._reference_shape(node_name)
                if not shape_name:
                    continue
                tagged_camera = _get_string_attr(node_name, "amirVideoOverlayCamera", "")
                if wanted and tagged_camera:
                    tagged_camera = _long_name(tagged_camera) if cmds.objExists(tagged_camera) else tagged_camera
                    if tagged_camera != wanted:
                        continue
                elif wanted:
                    connected = _camera_transform_from_image_plane(shape_name)
                    if _long_name(connected) != wanted:
                        continue
                matches.append(_long_name(node_name))
            except Exception:
                continue
        return matches

    def remove_camera_overlays(self, camera_name=None, transforms=None):
        """Remove old overlays (and their attached audio) for one Pencil View."""
        if not MAYA_AVAILABLE:
            return 0
        targets = list(transforms or self.camera_overlay_transforms(camera_name))
        removed = 0
        for transform_name in targets:
            if not transform_name or not cmds.objExists(transform_name):
                continue
            sound_name = _get_string_attr(transform_name, "amirVideoSoundNode", "")
            try:
                slider = _playback_slider()
                if slider and sound_name and cmds.control(slider, exists=True):
                    current_sound = cmds.timeControl(slider, query=True, sound=True) or ""
                    if current_sound == sound_name:
                        cmds.timeControl(slider, edit=True, sound="", displaySound=False)
            except Exception:
                pass
            try:
                if sound_name and cmds.objExists(sound_name):
                    cmds.delete(sound_name)
            except Exception:
                pass
            try:
                cmds.delete(transform_name)
                removed += 1
            except Exception:
                continue
        return removed

    def set_video_opacity(self, opacity, transform_name=None):
        """Apply percentage-style video opacity to the live image plane and scene state."""
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        value = _clamp_opacity(opacity)
        transform_name = transform_name or self.last_transform or self._current_reference_transform()
        shape_name = self._reference_shape(transform_name)
        if not shape_name:
            return False, "Attach a video first so its opacity can be changed."
        sequence_start_frame = _get_long_attr(
            transform_name,
            "amirVideoSequenceStartFrame",
            self.last_media_info.get("sequence_start_frame", 1),
        )
        self.opacity = value
        _apply_frame_settings(shape_name, self.start_frame, sequence_start_frame, value)
        isolated, isolation_message = _isolate_camera_overlay_to_assigned_view(shape_name)
        if not isolated:
            return False, isolation_message
        _ensure_double_attr(transform_name, VIDEO_OPACITY_ATTR)
        cmds.setAttr(transform_name + "." + VIDEO_OPACITY_ATTR, value)
        self.last_transform = _long_name(transform_name)
        self.last_image_plane = _long_name(shape_name)
        return True, "Video opacity: {0}%".format(int(round(value * 100.0)))

    def set_audio_enabled(self, enabled, transform_name=None):
        """Toggle the attached video's scene sound without re-importing video."""
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        enabled = bool(enabled)
        transform_name = transform_name or self.last_transform or self._current_reference_transform()
        shape_name = self._reference_shape(transform_name)
        if not shape_name:
            self.import_audio = enabled
            return False, "Attach a video first so its audio can be changed."
        sound_name = _get_string_attr(transform_name, "amirVideoSoundNode", self.last_sound)
        if enabled:
            if not sound_name or not cmds.objExists(sound_name):
                source_path = _get_string_attr(transform_name, "amirVideoSourcePath", "") or self.media_path
                audio_path = self.audio_path if self.audio_path and os.path.exists(self.audio_path) else ""
                media_info = self.last_media_info or {}
                if not audio_path and source_path and os.path.exists(source_path):
                    try:
                        media_info = _resolve_media_path(source_path, extract_audio=True, start_frame=int(self.start_frame))
                        self.last_media_info = media_info
                    except Exception as exc:
                        return False, "Could not prepare video audio: {0}".format(exc)
                    audio_path = media_info.get("audio_path") or ""
                if not audio_path or not os.path.exists(audio_path):
                    return False, "This video does not contain audio that Maya can attach."
                try:
                    sound_name = cmds.sound(file=audio_path, offset=int(self.start_frame))
                except Exception as exc:
                    return False, "Could not attach video audio: {0}".format(exc)
            slider = _playback_slider()
            if slider:
                try:
                    cmds.timeControl(slider, edit=True, sound=sound_name, displaySound=True)
                except Exception:
                    pass
            self.last_sound = sound_name
            self.import_audio = True
        else:
            slider = _playback_slider()
            if slider and sound_name:
                try:
                    current_sound = cmds.timeControl(slider, query=True, sound=True) or ""
                    if current_sound == sound_name:
                        cmds.timeControl(slider, edit=True, sound="", displaySound=False)
                except Exception:
                    pass
            if sound_name and cmds.objExists(sound_name):
                try:
                    cmds.delete(sound_name)
                except Exception:
                    pass
            self.last_sound = ""
            self.import_audio = False
        _set_string_attr(transform_name, "amirVideoSoundNode", self.last_sound)
        _ensure_long_attr(transform_name, VIDEO_AUDIO_ENABLED_ATTR)
        cmds.setAttr(transform_name + "." + VIDEO_AUDIO_ENABLED_ATTR, int(enabled and bool(self.last_sound)))
        self.last_transform = _long_name(transform_name)
        self.last_image_plane = _long_name(shape_name)
        return True, "Video audio: {0}.".format("On" if enabled and self.last_sound else "Off")

    def apply_camera_overlay_placement(self, placement=None, keep_strokes_on_top=None, transform_name=None, scale_percent=None):
        """Place and resize a camera-attached video in full view or a PIP corner."""
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        transform_name = transform_name or self.last_transform or self._current_reference_transform()
        shape_name = self._reference_shape(transform_name)
        if not shape_name:
            return False, "Attach or select a camera video overlay first."
        isolated, isolation_message = _isolate_camera_overlay_to_assigned_view(shape_name)
        if not isolated:
            return False, isolation_message

        placement = str(placement or self.camera_overlay_placement or "full_view").lower()
        if placement not in ("full_view", "top_right", "top_left", "bottom_right", "bottom_left"):
            placement = "full_view"
        if keep_strokes_on_top is None:
            keep_strokes_on_top = self.keep_strokes_on_top
        keep_strokes_on_top = bool(keep_strokes_on_top)

        if scale_percent is None:
            stored_scale = _get_double_attr(transform_name, "amirVideoOverlayScale", None)
            previous_placement = str(self.camera_overlay_placement or "full_view").lower()
            crossed_category = (previous_placement == "full_view") != (placement == "full_view")
            if crossed_category:
                scale = 1.0 if placement == "full_view" else 0.38
            elif stored_scale is not None:
                scale = float(stored_scale)
            elif getattr(self, "camera_overlay_scale", None):
                scale = float(self.camera_overlay_scale)
            else:
                scale = 1.0 if placement == "full_view" else 0.38
        else:
            try:
                scale = float(scale_percent) / 100.0
            except Exception:
                scale = 1.0 if placement == "full_view" else 0.38
        scale = max(0.10, min(2.00, scale))

        baseline_width = _get_double_attr(transform_name, "amirVideoOverlayBaselineWidth", None)
        baseline_height = _get_double_attr(transform_name, "amirVideoOverlayBaselineHeight", None)
        baseline_size_x = _get_double_attr(transform_name, "amirVideoOverlayBaselineSizeX", None)
        baseline_size_y = _get_double_attr(transform_name, "amirVideoOverlayBaselineSizeY", None)
        baseline_offset_x = _get_double_attr(transform_name, "amirVideoOverlayBaselineOffsetX", None)
        baseline_offset_y = _get_double_attr(transform_name, "amirVideoOverlayBaselineOffsetY", None)
        baseline_depth = _get_double_attr(transform_name, "amirVideoOverlayBaselineDepth", None)

        def _fallback(value, attr_name, default_value):
            if value is not None:
                return float(value)
            try:
                return float(cmds.getAttr(shape_name + "." + attr_name))
            except Exception:
                return float(default_value)

        baseline_width = _fallback(baseline_width, "width", 1.0)
        baseline_height = _fallback(baseline_height, "height", 1.0)
        baseline_size_x = _fallback(baseline_size_x, "sizeX", 1.0)
        baseline_size_y = _fallback(baseline_size_y, "sizeY", 1.0)
        baseline_offset_x = _fallback(baseline_offset_x, "offsetX", 0.0)
        baseline_offset_y = _fallback(baseline_offset_y, "offsetY", 0.0)
        baseline_depth = max(0.001, _fallback(baseline_depth, "depth", 1.0))

        for attr_name, value in (
            ("amirVideoOverlayBaselineWidth", baseline_width),
            ("amirVideoOverlayBaselineHeight", baseline_height),
            ("amirVideoOverlayBaselineSizeX", baseline_size_x),
            ("amirVideoOverlayBaselineSizeY", baseline_size_y),
            ("amirVideoOverlayBaselineOffsetX", baseline_offset_x),
            ("amirVideoOverlayBaselineOffsetY", baseline_offset_y),
            ("amirVideoOverlayBaselineDepth", baseline_depth),
        ):
            _ensure_double_attr(transform_name, attr_name)
            cmds.setAttr(transform_name + "." + attr_name, float(value))
        _ensure_string_attr(transform_name, "amirVideoOverlayPlacement")
        _ensure_double_attr(transform_name, "amirVideoOverlayScale")
        _ensure_long_attr(transform_name, "amirVideoOverlayKeepStrokesOnTop")
        camera_name = self.camera_name if self.camera_name and cmds.objExists(self.camera_name) else _camera_transform_from_image_plane(shape_name)
        if camera_name and cmds.nodeType(camera_name) == "camera":
            parents = cmds.listRelatives(camera_name, parent=True, fullPath=True) or []
            camera_name = parents[0] if parents else camera_name
        if camera_name and cmds.objExists(camera_name):
            camera_name = _long_name(camera_name)
            _set_string_attr(transform_name, "amirVideoOverlayCamera", camera_name)

        corner_x = 1.0 if placement in ("top_right", "bottom_right") else -1.0 if placement in ("top_left", "bottom_left") else 0.0
        corner_y = 1.0 if placement in ("top_right", "top_left") else -1.0 if placement in ("bottom_right", "bottom_left") else 0.0
        target_depth = max(baseline_depth, 20.0) if keep_strokes_on_top else baseline_depth
        target_size_x = baseline_size_x * scale
        target_size_y = baseline_size_y * scale
        target_offset_x = baseline_offset_x + corner_x * baseline_size_x * (1.0 - scale) * 0.5
        target_offset_y = baseline_offset_y + corner_y * baseline_size_y * (1.0 - scale) * 0.5
        if placement == "full_view":
            target_offset_x = baseline_offset_x
            target_offset_y = baseline_offset_y
        try:
            # Camera-attached image planes use sizeX/sizeY for their screen
            # footprint. width/height describe the image geometry and pushed
            # PIP offsets off-screen when used as film-aperture coordinates.
            cmds.setAttr(shape_name + ".width", float(baseline_width))
            cmds.setAttr(shape_name + ".height", float(baseline_height))
            cmds.setAttr(shape_name + ".sizeX", float(target_size_x))
            cmds.setAttr(shape_name + ".sizeY", float(target_size_y))
            cmds.setAttr(shape_name + ".offsetX", float(target_offset_x))
            cmds.setAttr(shape_name + ".offsetY", float(target_offset_y))
            cmds.setAttr(shape_name + ".depth", float(target_depth))
        except Exception as exc:
            return False, "Could not place the camera overlay: {0}".format(exc)

        _set_string_attr(transform_name, "amirVideoOverlayPlacement", placement)
        cmds.setAttr(transform_name + ".amirVideoOverlayScale", float(scale))
        cmds.setAttr(transform_name + ".amirVideoOverlayKeepStrokesOnTop", int(keep_strokes_on_top))
        _ensure_double_attr(transform_name, "amirVideoOverlayUpdatedAt")
        cmds.setAttr(transform_name + ".amirVideoOverlayUpdatedAt", float(time.time()))
        self.camera_overlay_placement = placement
        self.camera_overlay_scale = scale
        self.keep_strokes_on_top = keep_strokes_on_top
        self.last_transform = _long_name(transform_name)
        self.last_image_plane = _long_name(shape_name)
        return True, "Camera overlay placed in {0}.".format(placement.replace("_", " "))

    def discover_camera_overlay(self):
        """Restore the latest tagged camera overlay from scene-native nodes."""
        if not MAYA_AVAILABLE:
            return False
        candidates = []
        for node_name in cmds.ls(type="transform", long=True) or []:
            try:
                if not cmds.attributeQuery("amirVideoOverlayPlacement", node=node_name, exists=True):
                    continue
                placement = _get_string_attr(node_name, "amirVideoOverlayPlacement", "").lower()
                if placement not in ("full_view", "top_right", "top_left", "bottom_right", "bottom_left"):
                    continue
                shape_name = self._reference_shape(node_name)
                if not shape_name:
                    continue
                updated_at = _get_double_attr(node_name, "amirVideoOverlayUpdatedAt", 0.0)
                candidates.append((float(updated_at or 0.0), node_name, shape_name, placement))
            except Exception:
                continue
        if not candidates:
            return False
        candidates.sort(key=lambda item: item[0])
        _updated_at, transform_name, shape_name, placement = candidates[-1]
        source_path = _get_string_attr(transform_name, "amirVideoSourcePath", "")
        resolved_path = _get_string_attr(transform_name, "amirVideoResolvedPath", "")
        sequence_start_frame = _get_long_attr(transform_name, "amirVideoSequenceStartFrame", 1)
        stored_start_frame = _get_long_attr(transform_name, "amirVideoStartFrame", 0)
        if stored_start_frame:
            start_frame = stored_start_frame
        else:
            frame_offset = _get_long_attr(shape_name, "frameOffset", 0)
            start_frame = int(sequence_start_frame) - int(frame_offset)
        camera_name = _get_string_attr(transform_name, "amirVideoOverlayCamera", "")
        if camera_name and not cmds.objExists(camera_name):
            camera_name = ""
        if not camera_name:
            camera_name = _camera_transform_from_image_plane(shape_name)
        if camera_name and cmds.nodeType(camera_name) == "camera":
            parents = cmds.listRelatives(camera_name, parent=True, fullPath=True) or []
            camera_name = parents[0] if parents else camera_name
        if camera_name and cmds.objExists(camera_name):
            camera_name = _long_name(camera_name)
        keep_strokes_on_top = bool(_get_long_attr(transform_name, "amirVideoOverlayKeepStrokesOnTop", 0))
        opacity_value = _get_double_attr(transform_name, VIDEO_OPACITY_ATTR, None)
        if opacity_value is None:
            try:
                opacity_value = cmds.getAttr(shape_name + ".alphaGain") if cmds.objExists(shape_name + ".alphaGain") else self.opacity
            except Exception:
                opacity_value = self.opacity
        self.last_transform = _long_name(transform_name)
        self.last_image_plane = _long_name(shape_name)
        self.media_path = source_path
        self.start_frame = int(start_frame)
        self.camera_overlay_placement = placement
        stored_scale = _get_double_attr(transform_name, "amirVideoOverlayScale", None)
        if stored_scale is None:
            stored_scale = 1.0 if placement == "full_view" else 0.38
        self.camera_overlay_scale = max(0.10, min(2.00, float(stored_scale)))
        self.keep_strokes_on_top = keep_strokes_on_top
        self.opacity = _clamp_opacity(opacity_value)
        self.camera_name = camera_name
        self.last_sound = _get_string_attr(transform_name, "amirVideoSoundNode", "")
        audio_enabled = bool(_get_long_attr(transform_name, VIDEO_AUDIO_ENABLED_ATTR, 1 if self.last_sound else 0))
        self.last_media_info = {
            "media_path": source_path,
            "resolved_media_path": resolved_path,
            "sequence_start_frame": int(sequence_start_frame),
            "is_proxy": bool(resolved_path and resolved_path != source_path),
        }
        return {
            "transform": self.last_transform,
            "image_plane": self.last_image_plane,
            "source_path": source_path,
            "resolved_path": resolved_path,
            "start_frame": int(start_frame),
            "sequence_start_frame": int(sequence_start_frame),
            "placement": placement,
            "scale": self.camera_overlay_scale,
            "scale_percent": int(round(self.camera_overlay_scale * 100.0)),
            "keep_strokes_on_top": keep_strokes_on_top,
            "opacity": self.opacity,
            "opacity_percent": int(round(self.opacity * 100.0)),
            "camera": camera_name,
            "sound": self.last_sound,
            "audio_enabled": audio_enabled,
        }

    def update_current_reference_timing(self, warn_if_missing=True):
        transform_name = self._current_reference_transform()
        if not transform_name:
            if warn_if_missing:
                return False, "Make or select a tracing card first."
            return True, ""

        shape_name = self._reference_shape(transform_name)
        if not shape_name:
            if warn_if_missing:
                return False, "The selected object is not a video tracing card."
            return True, ""

        sequence_start_frame = _get_long_attr(transform_name, "amirVideoSequenceStartFrame", self.last_media_info.get("sequence_start_frame", 1))
        opacity_value = float(cmds.getAttr(shape_name + ".alphaGain")) if cmds.objExists(shape_name + ".alphaGain") else float(self.opacity)
        _apply_frame_settings(shape_name, self.start_frame, sequence_start_frame, opacity_value)
        isolated, isolation_message = _isolate_camera_overlay_to_assigned_view(shape_name)
        if not isolated:
            return False, isolation_message

        sound_name = _get_string_attr(transform_name, "amirVideoSoundNode", self.last_sound)
        if sound_name and cmds.objExists(sound_name):
            try:
                cmds.setAttr(sound_name + ".offset", int(self.start_frame))
                self.last_sound = sound_name
            except Exception:
                pass

        self.last_transform = transform_name
        self.last_image_plane = shape_name
        return True, "Moved {0} so the video starts at frame {1}.".format(_short_name(transform_name), int(self.start_frame))

    def prepare_annotation_surface(self):
        reference_transform = self._current_reference_transform()
        if not reference_transform:
            return False, "Make or select a tracing card first."

        reference_shape = self._reference_shape(reference_transform)
        if not reference_shape:
            return False, "The selected object is not a tracing card."

        annotation_group = _ensure_annotation_group()
        if self.last_annotation_surface and cmds.objExists(self.last_annotation_surface):
            try:
                cmds.delete(self.last_annotation_surface)
            except Exception:
                pass

        surface_name = "{0}_drawSurface".format(_short_name(reference_transform))
        surface_transform, _history = cmds.polyPlane(
            name=surface_name,
            width=float(cmds.getAttr(reference_shape + ".width")),
            height=float(cmds.getAttr(reference_shape + ".height")),
            subdivisionsX=1,
            subdivisionsY=1,
            axis=(0.0, 0.0, 1.0),
        )
        surface_transform = _long_name(cmds.parent(surface_transform, annotation_group)[0])
        surface_shape = (cmds.listRelatives(surface_transform, shapes=True, fullPath=True, type="mesh") or [""])[0]
        cmds.xform(surface_transform, worldSpace=True, matrix=cmds.xform(reference_transform, query=True, worldSpace=True, matrix=True))
        cmds.xform(surface_transform, objectSpace=True, translation=(0.0, 0.0, 0.01))
        if surface_shape:
            cmds.setAttr(surface_shape + ".castsShadows", 0)
            cmds.setAttr(surface_shape + ".receiveShadows", 0)
            cmds.setAttr(surface_shape + ".motionBlur", 0)
        _material, shading_group = _ensure_annotation_surface_shader()
        cmds.sets(surface_transform, edit=True, forceElement=shading_group)
        self.last_annotation_surface = surface_transform
        return True, surface_transform

    def start_simple_draw(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        success, result = self.prepare_annotation_surface()
        if not success:
            return False, result
        surface_transform = result
        try:
            cmds.makeLive(surface_transform)
        except Exception:
            pass
        try:
            cmds.select(clear=True)
        except Exception:
            pass
        try:
            cmds.EPCurveTool()
        except Exception:
            try:
                mel.eval("EPCurveTool;")
            except Exception as exc:
                return False, "I could not start the simple curve draw tool: {0}".format(exc)
        return True, "Curve draw mode is ready. Click on the card to place points, press Enter to finish the line, then use the drawing manager to set how long it stays visible."

    def apply_hold_to_selected_annotations(self, start_frame, end_frame):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        start_frame = int(start_frame)
        end_frame = int(end_frame)
        if end_frame < start_frame:
            return False, "The end frame needs to be the same as or after the start frame."

        selection = cmds.ls(selection=True, long=True) or []
        curve_transforms = []
        for item in selection:
            node_type = cmds.nodeType(item)
            if node_type == "transform":
                shapes = cmds.listRelatives(item, shapes=True, fullPath=True, type="nurbsCurve") or []
                if shapes:
                    curve_transforms.append(item)
            elif node_type == "nurbsCurve":
                parents = cmds.listRelatives(item, parent=True, fullPath=True) or []
                if parents:
                    curve_transforms.append(parents[0])
        curve_transforms = sorted(set(curve_transforms))
        if not curve_transforms:
            return False, "Pick the line or lines you want to hold first."

        annotation_group = _ensure_annotation_group()
        for curve_transform in curve_transforms:
            parent_path = cmds.listRelatives(curve_transform, parent=True, fullPath=True) or []
            if not parent_path or parent_path[0] != annotation_group:
                try:
                    curve_transform = _long_name(cmds.parent(curve_transform, annotation_group)[0])
                except Exception:
                    curve_transform = _long_name(curve_transform)
            _set_long_attr(curve_transform, "amirNoteStartFrame", start_frame)
            _set_long_attr(curve_transform, "amirNoteEndFrame", end_frame)
            shapes = cmds.listRelatives(curve_transform, shapes=True, fullPath=True, type="nurbsCurve") or []
            for shape_name in shapes:
                try:
                    cmds.setAttr(shape_name + ".overrideEnabled", 1)
                    cmds.setAttr(shape_name + ".overrideColor", 17)
                except Exception:
                    pass
            try:
                cmds.cutKey(curve_transform, attribute="visibility", option="keys")
            except Exception:
                pass
            cmds.setKeyframe(curve_transform, attribute="visibility", time=(start_frame - 1,), value=0)
            cmds.setKeyframe(curve_transform, attribute="visibility", time=(start_frame,), value=1)
            cmds.setKeyframe(curve_transform, attribute="visibility", time=(end_frame,), value=1)
            cmds.setKeyframe(curve_transform, attribute="visibility", time=(end_frame + 1,), value=0)
            try:
                cmds.keyTangent(curve_transform, attribute="visibility", inTangentType="stepnext", outTangentType="step")
            except Exception:
                pass
        return True, "The selected note lines now show from frame {0} to frame {1}.".format(start_frame, end_frame)

    def clear_annotation_surface(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        try:
            cmds.makeLive(none=True)
        except Exception:
            pass
        if self.last_annotation_surface and cmds.objExists(self.last_annotation_surface):
            try:
                cmds.delete(self.last_annotation_surface)
            except Exception:
                pass
        self.last_annotation_surface = ""
        try:
            cmds.setToolTo("selectSuperContext")
        except Exception:
            pass
        return True, "Cleared the live drawing surface."

    def delete_selected_annotations(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        selection = cmds.ls(selection=True, long=True) or []
        targets = []
        for item in selection:
            node_type = cmds.nodeType(item)
            if node_type == "transform":
                shapes = cmds.listRelatives(item, shapes=True, fullPath=True, type="nurbsCurve") or []
                if shapes:
                    targets.append(item)
            elif node_type == "nurbsCurve":
                parents = cmds.listRelatives(item, parent=True, fullPath=True) or []
                targets.extend(parents)
        targets = sorted(set(targets))
        if not targets:
            return False, "Pick the note lines you want to delete first."
        cmds.delete(targets)
        return True, "Deleted the selected note lines."

    def _create_camera_overlay(self, resolved_media_path, sequence_start_frame):
        camera_shape = _camera_shape(self.camera_name or _active_camera(require_focus=False))
        if not camera_shape:
            return False, "Click the viewport you want first, then click Use Active View."
        transform_name = ""
        try:
            image_plane = cmds.imagePlane(camera=camera_shape, fileName=resolved_media_path)
            transform_name = _long_name(image_plane[0])
            shape_name = _long_name(image_plane[1])
            _apply_frame_settings(shape_name, self.start_frame, sequence_start_frame, self.opacity)
            isolated, isolation_message = _isolate_camera_overlay_to_assigned_view(shape_name)
            if not isolated:
                raise RuntimeError(isolation_message)
        except Exception as exc:
            _delete_created_node(transform_name)
            return False, "Could not make the camera overlay: {0}".format(exc)
        self.last_transform = transform_name
        self.last_image_plane = shape_name
        success, placement_message = self.apply_camera_overlay_placement(
            self.camera_overlay_placement,
            self.keep_strokes_on_top,
            transform_name=transform_name,
        )
        if not success:
            _delete_created_node(transform_name)
            return False, placement_message
        return True, "Made a camera overlay on {0}.".format(_short_name(camera_shape))

    def _place_tracing_card(self, transform_name, shape_name, camera_name, target_name, sequence_start_frame):
        reference_group = _ensure_reference_group()
        camera_name = camera_name or _active_camera(require_focus=False)
        if not camera_name or not cmds.objExists(camera_name):
            return False, "Click the viewport you want first so I know where to place the tracing card."

        aspect_ratio = self.last_media_info.get("aspect_ratio") or (16.0 / 9.0)
        card_height = float(self.card_width) / float(aspect_ratio if aspect_ratio else (16.0 / 9.0))
        cmds.setAttr(shape_name + ".width", float(self.card_width))
        cmds.setAttr(shape_name + ".height", float(card_height))
        _apply_frame_settings(shape_name, self.start_frame, sequence_start_frame, self.opacity)

        target_vector = _world_position(target_name) if target_name else None
        camera_position = _camera_world_position(camera_name)
        camera_rotation = _world_rotation(camera_name)
        camera_forward = _camera_forward_vector(camera_name)
        if target_vector is None:
            target_vector = camera_position + (camera_forward * 10.0)

        view_direction = target_vector - camera_position
        if view_direction.length() < 0.001:
            view_direction = camera_forward
        view_direction.normalize()
        card_position = target_vector + (view_direction * float(self.depth_offset))

        follow_group = ""
        if self.placement_mode == "follow_target":
            if not target_name or not cmds.objExists(target_name):
                return False, "Pick the object you want the card to follow first."
            follow_group = cmds.createNode("transform", name="{0}_videoFollow".format(_short_name(target_name)))
            follow_group = _long_name(cmds.parent(follow_group, reference_group)[0])
            cmds.xform(
                follow_group,
                worldSpace=True,
                translation=[target_vector.x, target_vector.y, target_vector.z],
            )
            skip_axes = []
            if not self.follow_x:
                skip_axes.append("x")
            if not self.follow_y:
                skip_axes.append("y")
            if not self.follow_z:
                skip_axes.append("z")
            constraint_kwargs = {"maintainOffset": False}
            if skip_axes:
                constraint_kwargs["skip"] = skip_axes
            cmds.pointConstraint(target_name, follow_group, **constraint_kwargs)
            transform_name = _long_name(cmds.parent(transform_name, follow_group)[0])
            cmds.xform(
                transform_name,
                worldSpace=True,
                translation=[card_position.x, card_position.y, card_position.z],
            )
            cmds.xform(transform_name, worldSpace=True, rotation=camera_rotation)
            shape_name = _long_name((cmds.listRelatives(transform_name, shapes=True, fullPath=True, type="imagePlane") or [shape_name])[0])
            self.last_transform = transform_name
            self.last_image_plane = shape_name
            self.last_follow_group = follow_group
            return True, "Made a tracing card that follows {0}.".format(_short_name(target_name))

        transform_name = _long_name(cmds.parent(transform_name, reference_group)[0])
        cmds.xform(
            transform_name,
            worldSpace=True,
            translation=[card_position.x, card_position.y, card_position.z],
        )
        cmds.xform(transform_name, worldSpace=True, rotation=camera_rotation)
        shape_name = _long_name((cmds.listRelatives(transform_name, shapes=True, fullPath=True, type="imagePlane") or [shape_name])[0])
        self.last_transform = transform_name
        self.last_image_plane = shape_name
        self.last_follow_group = ""
        if target_name:
            return True, "Made a tracing card behind {0}.".format(_short_name(target_name))
        return True, "Made a tracing card in the active view."

    def import_reference(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if not self.media_path or not os.path.exists(self.media_path):
            return False, "Pick a video or image sequence file first."
        camera_name = self.camera_name or _active_camera(require_focus=False)
        if not camera_name:
            return False, "Click the viewport you want first so I know where to place the reference."

        target_name = self.target_node if (self.target_node and cmds.objExists(self.target_node)) else ""
        if not target_name and self.placement_mode in ("tracing_card", "follow_target"):
            target_name = _selected_transform()
            if target_name:
                self.target_node = target_name

        media_info = _resolve_media_path(
            self.media_path,
            extract_audio=bool(self.import_audio and not self.audio_path),
            start_frame=int(self.start_frame),
        )
        self.last_media_info = media_info
        resolved_media_path = media_info.get("resolved_media_path") or self.media_path
        if not resolved_media_path or not os.path.exists(resolved_media_path):
            return False, "I could not prepare a Maya-friendly image sequence from that video."
        media_ok, media_error = _validate_image_plane_media(resolved_media_path)
        if not media_ok:
            return False, media_error

        original_selection = cmds.ls(selection=True, long=True) or []
        created_transform = ""
        created_follow_group = ""
        cmds.undoInfo(openChunk=True, chunkName="MayaVideoReference")
        try:
            self.last_sound = ""
            self.last_follow_group = ""
            if self.placement_mode == "camera_overlay":
                success, placement_message = self._create_camera_overlay(
                    resolved_media_path,
                    media_info.get("sequence_start_frame", 1),
                )
                if not success:
                    return False, placement_message
            else:
                image_plane = cmds.imagePlane(fileName=resolved_media_path)
                transform_name = _long_name(image_plane[0])
                shape_name = _long_name(image_plane[1])
                created_transform = transform_name
                self.last_transform = transform_name
                self.last_image_plane = shape_name
                success, placement_message = self._place_tracing_card(
                    transform_name,
                    shape_name,
                    camera_name,
                    target_name,
                    media_info.get("sequence_start_frame", 1),
                )
                if not success:
                    _delete_created_node(created_transform)
                    return False, placement_message
                created_follow_group = self.last_follow_group

            audio_path = self._audio_path_for_import(media_info)
            audio_error = media_info.get("audio_error") or ""
            if self.import_audio and audio_path and os.path.exists(audio_path):
                sound_name = cmds.sound(file=audio_path, offset=int(self.start_frame))
                slider = _playback_slider()
                if slider:
                    cmds.timeControl(slider, edit=True, sound=sound_name, displaySound=True)
                self.last_sound = sound_name
            elif self.import_audio and audio_error:
                placement_message += " I could not pull audio from the video: {0}".format(audio_error)
            self._tag_reference_transform(self.last_transform, media_info, self.last_sound)
        except Exception as exc:
            _delete_created_node(created_transform)
            _delete_created_node(created_follow_group)
            return False, "Could not make the video reference: {0}".format(exc)
        finally:
            try:
                if original_selection:
                    cmds.select(original_selection, replace=True)
                else:
                    cmds.select(clear=True)
            except Exception:
                pass
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass

        message = "{0} It starts at frame {1}.".format(placement_message, int(self.start_frame))
        if media_info.get("is_proxy"):
            message += " The video was turned into a Maya-friendly image sequence for the current playback range so scrubbing works."
        if self.last_sound:
            message += " Audio was lined up too."
        return True, message

    def open_drawing_manager(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if hasattr(cmds, "bluePencilUtil"):
            cmds.bluePencilUtil(layerManager=True)
            return True, "Opened Blue Pencil's layer manager."
        if QtWidgets:
            launch_video_annotation_manager(self)
            return True, "Opened the simple note manager for this Maya version."
        return False, "This Maya version does not have Blue Pencil, and the fallback note manager needs the Qt UI."

    def activate_draw_tool(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if hasattr(cmds, "bluePencilUtil"):
            cmds.bluePencilUtil(draw=True)
            return True, "Blue Pencil draw mode is ready. Draw over the image plane frame by frame."
        return self.start_simple_draw()


class _WindowBase(QtWidgets.QDialog if QtWidgets else object):
    pass


if QtWidgets:
    class MayaVideoAnnotationManagerWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaVideoAnnotationManagerWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.setObjectName(ANNOTATION_WINDOW_OBJECT_NAME)
            self.setWindowTitle("Video Notes")
            self.setMinimumSize(360, 320)
            self.resize(520, 460)
            self._build_ui()
            self._sync_reference_label()

        def _build_ui(self):
            outer_layout = QtWidgets.QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName("videoAnnotationContentScroll")
            scroll.setWidgetResizable(True)
            scroll.setMinimumWidth(0)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            content = QtWidgets.QWidget()
            content.setMinimumWidth(0)
            main_layout = QtWidgets.QVBoxLayout(content)
            intro = QtWidgets.QLabel(
                "Draw quick note lines on top of the tracing card, then choose how long they stay visible."
            )
            intro.setWordWrap(True)
            main_layout.addWidget(intro)

            reference_row = QtWidgets.QHBoxLayout()
            reference_row.addWidget(QtWidgets.QLabel("Current Card"))
            self.reference_line = QtWidgets.QLineEdit()
            self.reference_line.setReadOnly(True)
            reference_row.addWidget(self.reference_line, 1)
            main_layout.addLayout(reference_row)

            range_row = QtWidgets.QHBoxLayout()
            self.start_spin = QtWidgets.QSpinBox()
            self.start_spin.setRange(-100000, 100000)
            self.end_spin = QtWidgets.QSpinBox()
            self.end_spin.setRange(-100000, 100000)
            range_row.addWidget(QtWidgets.QLabel("Show From"))
            range_row.addWidget(self.start_spin)
            self.use_current_start_button = QtWidgets.QPushButton("Use Current For Start")
            range_row.addWidget(self.use_current_start_button)
            range_row.addSpacing(8)
            range_row.addWidget(QtWidgets.QLabel("Show Until"))
            range_row.addWidget(self.end_spin)
            self.use_current_end_button = QtWidgets.QPushButton("Use Current For End")
            range_row.addWidget(self.use_current_end_button)
            main_layout.addLayout(range_row)

            button_grid = QtWidgets.QGridLayout()
            self.start_draw_button = QtWidgets.QPushButton("Start Curve Draw")
            self.apply_hold_button = QtWidgets.QPushButton("Hold Selected Notes")
            self.clear_surface_button = QtWidgets.QPushButton("Clear Live Surface")
            self.delete_notes_button = QtWidgets.QPushButton("Delete Selected Notes")
            button_grid.addWidget(self.start_draw_button, 0, 0)
            button_grid.addWidget(self.apply_hold_button, 0, 1)
            button_grid.addWidget(self.clear_surface_button, 1, 0)
            button_grid.addWidget(self.delete_notes_button, 1, 1)
            main_layout.addLayout(button_grid)

            help_box = QtWidgets.QPlainTextEdit()
            help_box.setReadOnly(True)
            help_box.setVisible(False)
            help_box.setPlainText(
                "1. Make or select a tracing card.\n"
                "2. Click Start Curve Draw.\n"
                "3. Click on the card to place curve points and press Enter to finish the line.\n"
                "4. Pick the new line.\n"
                "5. Set Show From and Show Until.\n"
                "6. Click Hold Selected Notes so the line appears only on those frames."
            )
            help_toggle = QtWidgets.QToolButton()
            help_toggle.setText("How to use")
            help_toggle.setCheckable(True)
            help_toggle.setToolTip("Show or hide Video Notes quick help.")
            help_toggle.toggled.connect(help_box.setVisible)
            main_layout.addWidget(help_toggle)
            main_layout.addWidget(help_box, 1)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            main_layout.addWidget(self.status_label)

            footer_layout = QtWidgets.QHBoxLayout()
            self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            footer_layout.addWidget(self.brand_label, 1)
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)
            scroll.setWidget(content)
            outer_layout.addWidget(scroll)

            current_frame = int(round(float(cmds.currentTime(query=True)))) if MAYA_AVAILABLE else 1
            self.start_spin.setValue(current_frame)
            self.end_spin.setValue(current_frame)

            self.use_current_start_button.clicked.connect(self._use_current_start)
            self.use_current_end_button.clicked.connect(self._use_current_end)
            self.start_draw_button.clicked.connect(self._start_draw)
            self.apply_hold_button.clicked.connect(self._apply_hold)
            self.clear_surface_button.clicked.connect(self._clear_surface)
            self.delete_notes_button.clicked.connect(self._delete_notes)

        def _sync_reference_label(self):
            reference_name = self.controller._current_reference_transform()
            self.reference_line.setText(_short_name(reference_name) if reference_name else "")

        def _use_current_start(self):
            if MAYA_AVAILABLE:
                self.start_spin.setValue(int(round(float(cmds.currentTime(query=True)))))

        def _use_current_end(self):
            if MAYA_AVAILABLE:
                self.end_spin.setValue(int(round(float(cmds.currentTime(query=True)))))

        def _start_draw(self):
            success, message = self.controller.start_simple_draw()
            self._sync_reference_label()
            self._set_status(message, success)

        def _apply_hold(self):
            success, message = self.controller.apply_hold_to_selected_annotations(self.start_spin.value(), self.end_spin.value())
            self._set_status(message, success)

        def _clear_surface(self):
            success, message = self.controller.clear_annotation_surface()
            self._set_status(message, success)

        def _delete_notes(self):
            success, message = self.controller.delete_selected_annotations()
            self._set_status(message, success)

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)

        def _open_follow_url(self, *_args):
            _open_external_url(FOLLOW_AMIR_URL)

        def _open_donate_url(self):
            _open_external_url(DONATE_URL)

        def closeEvent(self, event):
            self.hide()
            event.ignore()


def launch_video_annotation_manager(controller):
    global GLOBAL_ANNOTATION_WINDOW
    if not QtWidgets:
        raise RuntimeError("Video Notes needs PySide inside Maya.")
    if GLOBAL_ANNOTATION_WINDOW is not None:
        try:
            GLOBAL_ANNOTATION_WINDOW.show()
            GLOBAL_ANNOTATION_WINDOW.raise_()
            GLOBAL_ANNOTATION_WINDOW.activateWindow()
            GLOBAL_ANNOTATION_WINDOW._sync_reference_label()
            return GLOBAL_ANNOTATION_WINDOW
        except Exception:
            GLOBAL_ANNOTATION_WINDOW = None
    GLOBAL_ANNOTATION_WINDOW = MayaVideoAnnotationManagerWindow(controller, parent=_maya_main_window())
    GLOBAL_ANNOTATION_WINDOW.show()
    return GLOBAL_ANNOTATION_WINDOW


if QtWidgets:
    class MayaVideoReferenceWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaVideoReferenceWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.set_status_callback(self._set_status)
            self._block_start_frame_sync = False
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Video Reference")
            self.setMinimumSize(360, 420)
            self.resize(760, 680)
            self._build_ui()
            self._sync_from_controller()
            self._auto_use_safe_current_state()

        def _build_ui(self):
            outer_layout = QtWidgets.QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName("videoReferenceContentScroll")
            scroll.setWidgetResizable(True)
            scroll.setMinimumWidth(0)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            content = QtWidgets.QWidget()
            content.setMinimumWidth(0)
            main_layout = QtWidgets.QVBoxLayout(content)
            intro = QtWidgets.QLabel(
                "Turn a video into a tracing card Maya can scrub cleanly. You can place it behind the character, make it follow a picked object, or use a full-screen camera overlay if you really want that."
            )
            intro.setWordWrap(True)
            main_layout.addWidget(intro)

            source_group = QtWidgets.QGroupBox("Source")
            source_layout = QtWidgets.QVBoxLayout(source_group)
            source_layout.setContentsMargins(8, 8, 8, 8)
            source_layout.setSpacing(6)
            camera_row = QtWidgets.QHBoxLayout()
            self.camera_line = QtWidgets.QLineEdit()
            self.camera_line.setReadOnly(True)
            self.use_camera_button = QtWidgets.QPushButton("Use Active View")
            camera_row.addWidget(QtWidgets.QLabel("View"))
            camera_row.addWidget(self.camera_line, 1)
            camera_row.addWidget(self.use_camera_button)
            source_layout.addLayout(camera_row)

            media_row = QtWidgets.QHBoxLayout()
            self.media_line = QtWidgets.QLineEdit()
            self.pick_media_button = QtWidgets.QPushButton("Pick Video / Images")
            media_row.addWidget(QtWidgets.QLabel("Video File"))
            media_row.addWidget(self.media_line, 1)
            media_row.addWidget(self.pick_media_button)
            source_layout.addLayout(media_row)

            audio_row = QtWidgets.QHBoxLayout()
            self.audio_line = QtWidgets.QLineEdit()
            self.pick_audio_button = QtWidgets.QPushButton("Pick Audio")
            audio_row.addWidget(QtWidgets.QLabel("Audio File"))
            audio_row.addWidget(self.audio_line, 1)
            audio_row.addWidget(self.pick_audio_button)
            source_layout.addLayout(audio_row)

            target_row = QtWidgets.QHBoxLayout()
            self.target_line = QtWidgets.QLineEdit()
            self.target_line.setReadOnly(True)
            self.use_target_button = QtWidgets.QPushButton("Use Selected Object")
            target_row.addWidget(QtWidgets.QLabel("Object To Follow"))
            target_row.addWidget(self.target_line, 1)
            target_row.addWidget(self.use_target_button)
            source_layout.addLayout(target_row)
            main_layout.addWidget(source_group)

            placement_group = QtWidgets.QGroupBox("Placement")
            placement_layout = QtWidgets.QVBoxLayout(placement_group)
            placement_layout.setContentsMargins(8, 8, 8, 8)
            placement_layout.setSpacing(6)
            placement_row = QtWidgets.QHBoxLayout()
            self.placement_combo = QtWidgets.QComboBox()
            for mode_key, mode_label in PLACEMENT_MODE_ITEMS:
                self.placement_combo.addItem(mode_label, mode_key)
            placement_row.addWidget(QtWidgets.QLabel("Placement"))
            placement_row.addWidget(self.placement_combo, 1)
            placement_row.addSpacing(8)
            placement_row.addWidget(QtWidgets.QLabel("Card Width"))
            self.card_width_spin = QtWidgets.QDoubleSpinBox()
            self.card_width_spin.setRange(0.1, 10000.0)
            self.card_width_spin.setDecimals(2)
            self.card_width_spin.setSingleStep(0.25)
            placement_row.addWidget(self.card_width_spin)
            placement_row.addWidget(QtWidgets.QLabel("Back Distance"))
            self.depth_offset_spin = QtWidgets.QDoubleSpinBox()
            self.depth_offset_spin.setRange(0.0, 10000.0)
            self.depth_offset_spin.setDecimals(2)
            self.depth_offset_spin.setSingleStep(0.25)
            placement_row.addWidget(self.depth_offset_spin)
            placement_row.addWidget(QtWidgets.QLabel("Opacity"))
            self.opacity_spin = QtWidgets.QDoubleSpinBox()
            self.opacity_spin.setRange(0.05, 1.0)
            self.opacity_spin.setDecimals(2)
            self.opacity_spin.setSingleStep(0.05)
            placement_row.addWidget(self.opacity_spin)
            placement_layout.addLayout(placement_row)

            axis_row = QtWidgets.QHBoxLayout()
            axis_row.addWidget(QtWidgets.QLabel("Follow Axes"))
            self.follow_x_check = QtWidgets.QCheckBox("X")
            self.follow_y_check = QtWidgets.QCheckBox("Y")
            self.follow_z_check = QtWidgets.QCheckBox("Z")
            axis_row.addWidget(self.follow_x_check)
            axis_row.addWidget(self.follow_y_check)
            axis_row.addWidget(self.follow_z_check)
            axis_row.addStretch(1)
            placement_layout.addLayout(axis_row)

            options_row = QtWidgets.QHBoxLayout()
            self.start_spin = QtWidgets.QSpinBox()
            self.start_spin.setRange(-100000, 100000)
            self.import_audio_check = QtWidgets.QCheckBox("Import Audio Too")
            options_row.addWidget(QtWidgets.QLabel("Start Frame"))
            options_row.addWidget(self.start_spin)
            self.update_timing_button = QtWidgets.QPushButton("Update Current Card")
            options_row.addWidget(self.update_timing_button)
            options_row.addWidget(self.import_audio_check)
            options_row.addStretch(1)
            placement_layout.addLayout(options_row)
            main_layout.addWidget(placement_group)

            draw_group = QtWidgets.QGroupBox("Draw")
            draw_layout = QtWidgets.QHBoxLayout(draw_group)
            button_row = QtWidgets.QHBoxLayout()
            self.import_button = QtWidgets.QPushButton("Make Tracing Card")
            self.open_layers_button = QtWidgets.QPushButton("Open Drawing Manager")
            self.draw_button = QtWidgets.QPushButton("Start Drawing")
            button_row.addWidget(self.import_button)
            button_row.addWidget(self.open_layers_button)
            button_row.addWidget(self.draw_button)
            draw_layout.addLayout(button_row)
            main_layout.addWidget(draw_group)

            help_box = QtWidgets.QPlainTextEdit()
            help_box.setReadOnly(True)
            help_box.setVisible(False)
            help_box.setPlainText(
                "1. Click the viewport you want to trace in, then click Use Active View.\n"
                "2. Pick the video or the first frame of an image sequence.\n"
                "3. If you want the card behind the character, pick the control or object and click Use Selected Object.\n"
                "4. Choose Behind Picked Object, Follow Picked Object, or Camera Overlay.\n"
                "5. Set the Start Frame. If a card is already in the scene, changing this box updates that card straight away.\n"
                "6. If you want sound, turn on Import Audio Too. You can also pick a separate audio file.\n"
                "7. Click Make Tracing Card.\n"
                "8. Click Start Drawing to sketch quick note lines on the card, or Open Drawing Manager to set how long those notes stay visible."
            )
            help_toggle = QtWidgets.QToolButton()
            help_toggle.setText("How to use")
            help_toggle.setCheckable(True)
            help_toggle.setToolTip("Show or hide Video Reference quick help.")
            help_toggle.toggled.connect(help_box.setVisible)
            main_layout.addWidget(help_toggle)
            main_layout.addWidget(help_box, 1)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            main_layout.addWidget(self.status_label)

            footer_layout = QtWidgets.QHBoxLayout()
            self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
            self.brand_label.setOpenExternalLinks(False)
            self.brand_label.linkActivated.connect(self._open_follow_url)
            footer_layout.addWidget(self.brand_label, 1)
            self.donate_button = QtWidgets.QPushButton("Donate")
            _style_donate_button(self.donate_button)
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)
            scroll.setWidget(content)
            outer_layout.addWidget(scroll)

            self.use_camera_button.clicked.connect(self._use_camera)
            self.pick_media_button.clicked.connect(self._pick_media)
            self.pick_audio_button.clicked.connect(self._pick_audio)
            self.use_target_button.clicked.connect(self._use_target)
            self.import_button.clicked.connect(self._import_reference)
            self.open_layers_button.clicked.connect(self._open_layers)
            self.draw_button.clicked.connect(self._draw)
            self.placement_combo.currentIndexChanged.connect(self._update_mode_ui)
            self.update_timing_button.clicked.connect(self._update_current_reference_timing)
            self.start_spin.valueChanged.connect(self._start_frame_changed)

        def _auto_use_safe_current_state(self):
            if MAYA_AVAILABLE and not self.controller.camera_name:
                try:
                    self.controller.use_active_camera()
                    self._sync_from_controller()
                except Exception:
                    pass

        def _sync_from_controller(self):
            self.camera_line.setText(_short_name(self.controller.camera_name) if self.controller.camera_name else "")
            self.media_line.setText(self.controller.media_path or "")
            self.audio_line.setText(self.controller.audio_path or "")
            self.target_line.setText(_short_name(self.controller.target_node) if self.controller.target_node else "")
            self._block_start_frame_sync = True
            self.start_spin.setValue(int(self.controller.start_frame))
            self._block_start_frame_sync = False
            self.import_audio_check.setChecked(bool(self.controller.import_audio))
            self.card_width_spin.setValue(float(self.controller.card_width))
            self.depth_offset_spin.setValue(float(self.controller.depth_offset))
            self.opacity_spin.setValue(float(self.controller.opacity))
            self.follow_x_check.setChecked(bool(self.controller.follow_x))
            self.follow_y_check.setChecked(bool(self.controller.follow_y))
            self.follow_z_check.setChecked(bool(self.controller.follow_z))
            mode_index = self.placement_combo.findData(self.controller.placement_mode)
            if mode_index >= 0:
                self.placement_combo.setCurrentIndex(mode_index)
            self._update_mode_ui()

        def _sync_to_controller(self):
            self.controller.start_frame = int(self.start_spin.value())
            self.controller.import_audio = bool(self.import_audio_check.isChecked())
            self.controller.placement_mode = self.placement_combo.currentData()
            self.controller.card_width = float(self.card_width_spin.value())
            self.controller.depth_offset = float(self.depth_offset_spin.value())
            self.controller.opacity = float(self.opacity_spin.value())
            self.controller.follow_x = bool(self.follow_x_check.isChecked())
            self.controller.follow_y = bool(self.follow_y_check.isChecked())
            self.controller.follow_z = bool(self.follow_z_check.isChecked())

        def _use_camera(self):
            success, message = self.controller.use_active_camera()
            self._sync_from_controller()
            self._set_status(message, success)

        def _pick_media(self):
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Pick Video Or Image Sequence", "", MEDIA_FILTER)
            if not file_path:
                return
            self.controller.media_path = file_path
            self._sync_from_controller()
            self._set_status("Picked media file.", True)

        def _pick_audio(self):
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Pick Audio", "", AUDIO_FILTER)
            if not file_path:
                return
            self.controller.audio_path = file_path
            self._sync_from_controller()
            self._set_status("Picked audio file.", True)

        def _use_target(self):
            success, message = self.controller.set_target_from_selection()
            self._sync_from_controller()
            self._set_status(message, success)

        def _import_reference(self):
            self._sync_to_controller()
            if not self.controller.camera_name:
                self._set_status("Choose a viewport with Use Active View first.", False)
                return
            if not self.controller.media_path:
                self._set_status("Pick a video or image sequence first.", False)
                return
            success, message = self.controller.import_reference()
            self._sync_from_controller()
            self._set_status(message, success)

        def _update_current_reference_timing(self):
            self._sync_to_controller()
            success, message = self.controller.update_current_reference_timing(warn_if_missing=True)
            if message:
                self._set_status(message, success)

        def _start_frame_changed(self, _value):
            if self._block_start_frame_sync:
                return
            self._sync_to_controller()
            success, message = self.controller.update_current_reference_timing(warn_if_missing=False)
            if message:
                self._set_status(message, success)

        def _open_layers(self):
            success, message = self.controller.open_drawing_manager()
            self._set_status(message, success)

        def _draw(self):
            success, message = self.controller.activate_draw_tool()
            self._set_status(message, success)

        def _update_mode_ui(self):
            mode_key = self.placement_combo.currentData()
            follow_enabled = mode_key == "follow_target"
            target_enabled = mode_key in ("tracing_card", "follow_target")
            self.follow_x_check.setEnabled(follow_enabled)
            self.follow_y_check.setEnabled(follow_enabled)
            self.follow_z_check.setEnabled(follow_enabled)
            self.target_line.setEnabled(target_enabled)
            self.use_target_button.setEnabled(target_enabled)
            self.card_width_spin.setEnabled(mode_key != "camera_overlay")
            self.depth_offset_spin.setEnabled(mode_key != "camera_overlay")
            self.import_button.setText("Make Camera Overlay" if mode_key == "camera_overlay" else "Make Tracing Card")
            ready = bool(self.controller.camera_name and self.controller.media_path)
            self.import_button.setEnabled(ready)
            self.import_button.setToolTip(
                "Ready to create the reference card."
                if ready
                else "Choose a viewport and media file before creating the reference card."
            )

        def closeEvent(self, event):
            self.hide()
            event.ignore()

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            palette = self.status_label.palette()
            role = self.status_label.foregroundRole()
            palette.setColor(role, QtGui.QColor("#24A148" if success else "#DA1E28"))
            self.status_label.setPalette(palette)

        def _open_follow_url(self, *_args):
            _open_external_url(FOLLOW_AMIR_URL)

        def _open_donate_url(self):
            _open_external_url(DONATE_URL)


def launch_maya_video_reference(dock=False):
    global GLOBAL_CONTROLLER, GLOBAL_WINDOW
    if not (MAYA_AVAILABLE and QtWidgets):
        raise RuntimeError("Maya Video Reference must be launched inside Maya with PySide available.")

    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
            GLOBAL_CONTROLLER = None

    GLOBAL_CONTROLLER = MayaVideoReferenceController()
    GLOBAL_WINDOW = MayaVideoReferenceWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    if dock:
        try:
            GLOBAL_WINDOW.show(dockable=True, floating=False, area="right")
        except Exception:
            GLOBAL_WINDOW.show()
    else:
        GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "DONATE_URL",
    "FOLLOW_AMIR_URL",
    "MayaVideoReferenceController",
    "MayaVideoReferenceWindow",
    "launch_maya_video_reference",
]
