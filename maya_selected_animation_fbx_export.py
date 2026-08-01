"""Selected-animation FBX export for the Aminate Toolkit Bar.

The exporter is deliberately small and Maya-free at import time.  All FBX
settings are applied through a deterministic MEL command list, and a complete
snapshot is restored in a ``finally`` block so a failed export cannot leave
Maya's global FBX preferences changed.
"""

from __future__ import absolute_import, division, print_function

import os
import re
import time


try:
    import maya.cmds as cmds
    import maya.mel as mel

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    mel = None
    MAYA_AVAILABLE = False


try:
    from PySide6 import QtWidgets
except Exception:
    try:
        from PySide2 import QtWidgets
    except Exception:
        QtWidgets = None


EXPORT_COMMAND = "export_selected_animation_fbx"
DISPLAY_NAME = "Export Selected Animation FBX"
UNREAL_SCALE_LABEL = "Unreal Engine — centimetres"
SCENE_SCALE_LABEL = "Maya scene units"
SCALE_CHOICES = (
    (UNREAL_SCALE_LABEL, "cm"),
    (SCENE_SCALE_LABEL, "scene"),
)
DEFAULT_UP_AXIS = "Y"
UP_AXIS_CHOICES = ("Y", "Z")
DEFAULT_OUTPUT_NAME = "selected_animation.fbx"
FBX_PLUGIN_NAME = "fbxmaya"

# Maya 2026's FBX plug-in does not register an ``FBXExportMaterials`` MEL
# command.  Materials and file textures are included through
# ``FBXExportInputConnections``; embedded media is a separate setting and is
# enabled only when those input connections are included.
#
# Keep this list complete for every setting the exporter actually changes.
# A partial snapshot cannot prove that restoration happened, so export fails
# closed when any supported FBX query is unavailable.
_FBX_RESTORABLE_SETTINGS = (
    "FBXExportInAscii",
    "FBXExportSmoothingGroups",
    "FBXExportHardEdges",
    "FBXExportTangents",
    "FBXExportSmoothMesh",
    "FBXExportSkins",
    "FBXExportShapes",
    "FBXExportEmbeddedTextures",
    "FBXExportConstraints",
    "FBXExportCameras",
    "FBXExportLights",
    "FBXExportInputConnections",
    "FBXExportUpAxis",
    "FBXExportConvertUnitString",
    "FBXExportFileVersion",
    "FBXExportBakeComplexAnimation",
    "FBXExportBakeComplexStart",
    "FBXExportBakeComplexEnd",
    "FBXExportBakeComplexStep",
    "FBXExportApplyConstantKeyReducer",
)


class SelectedAnimationFbxOptions(object):
    """Safe defaults for a selected-object animation export."""

    def __init__(self, **values):
        self.selection_only = True
        # Selected animation already carries its authored keys.  Dense FBX
        # resampling is an explicit opt-in for interchange cases that need it.
        self.bake_animation = False
        self.include_geometry = True
        self.include_skinning = True
        self.include_blend_shapes = True
        self.include_tangents_binormals = True
        self.include_materials_textures = True
        self.embed_media = True
        self.include_cameras = False
        self.include_lights = False
        self.up_axis = DEFAULT_UP_AXIS
        self.scale_label = UNREAL_SCALE_LABEL
        self.overwrite = False
        self.output_path = ""
        for key, value in (values or {}).items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.selection_only = True
        self.up_axis = str(self.up_axis or DEFAULT_UP_AXIS).upper()
        if self.up_axis not in UP_AXIS_CHOICES:
            self.up_axis = DEFAULT_UP_AXIS
        if self.scale_label not in dict(SCALE_CHOICES):
            self.scale_label = UNREAL_SCALE_LABEL

    def to_dict(self):
        return {
            "selection_only": True,
            "bake_animation": bool(self.bake_animation),
            "include_geometry": bool(self.include_geometry),
            "include_skinning": bool(self.include_skinning),
            "include_blend_shapes": bool(self.include_blend_shapes),
            "include_tangents_binormals": bool(self.include_tangents_binormals),
            "include_materials_textures": bool(self.include_materials_textures),
            "embed_media": bool(self.embed_media),
            "include_cameras": bool(self.include_cameras),
            "include_lights": bool(self.include_lights),
            "up_axis": self.up_axis,
            "scale_label": self.scale_label,
            "overwrite": bool(self.overwrite),
            "output_path": self.output_path,
        }


def normalize_options(options=None):
    if isinstance(options, SelectedAnimationFbxOptions):
        return SelectedAnimationFbxOptions(**options.to_dict())
    if isinstance(options, dict):
        return SelectedAnimationFbxOptions(**options)
    return SelectedAnimationFbxOptions()


def current_visible_playback_range(cmds_api=None):
    """Return Maya's currently visible Time Slider min/max, not animation range."""
    api = cmds_api or cmds
    if api is None:
        return 0.0, 1.0
    values = api.playbackOptions(query=True, minTime=True, maxTime=True)
    if isinstance(values, (list, tuple)):
        if len(values) >= 2:
            return float(values[0]), float(values[1])
    # Some Maya wrappers return one value per query flag.  Keep the fallback
    # explicit so tests and older command wrappers still use min/maxTime.
    return (
        float(api.playbackOptions(query=True, minTime=True)),
        float(api.playbackOptions(query=True, maxTime=True)),
    )


def _valid_fbx_path(path):
    if isinstance(path, os.PathLike):
        path = os.fspath(path)
    if not isinstance(path, str) or not path.strip():
        return "", "Choose an explicit .fbx output path."
    normalized = os.path.abspath(path.strip())
    if os.path.splitext(normalized)[1].lower() != ".fbx":
        return "", "The selected-animation export path must end in .fbx."
    parent = os.path.dirname(normalized)
    if not parent or not os.path.isdir(parent):
        return "", "The FBX export folder does not exist: {0}".format(parent or "(empty)")
    return normalized, ""


def _selected_objects(cmds_api=None):
    api = cmds_api or cmds
    if api is None:
        return []
    try:
        return list(api.ls(selection=True, long=True) or [])
    except TypeError:
        return list(api.ls(selection=True) or [])


def _quote_path(path):
    return str(path).replace("\\", "/").replace('"', '\\"')


def _scale_unit(options, cmds_api=None):
    if options.scale_label == UNREAL_SCALE_LABEL:
        return "cm"
    api = cmds_api or cmds
    if api is not None:
        try:
            return str(api.currentUnit(query=True, linear=True) or "cm")
        except Exception:
            pass
    return "cm"


def _fbx_mel_commands(path, options=None, visible_range=None, cmds_api=None):
    """Build the exact deterministic FBX setting/export command sequence."""
    opts = normalize_options(options)
    if visible_range is None:
        visible_range = current_visible_playback_range(cmds_api=cmds_api)
    start, end = float(visible_range[0]), float(visible_range[1])
    axis = opts.up_axis if opts.up_axis in UP_AXIS_CHOICES else DEFAULT_UP_AXIS
    unit = _scale_unit(opts, cmds_api=cmds_api)
    path_text = _quote_path(path)
    commands = [
        "FBXExportInAscii -v false",
        "FBXExportSmoothingGroups -v true",
        "FBXExportHardEdges -v false",
        "FBXExportTangents -v {0}".format("true" if opts.include_tangents_binormals else "false"),
        "FBXExportSmoothMesh -v {0}".format("true" if opts.include_geometry else "false"),
        "FBXExportSkins -v {0}".format("true" if opts.include_skinning else "false"),
        "FBXExportShapes -v {0}".format("true" if opts.include_blend_shapes else "false"),
        "FBXExportEmbeddedTextures -v {0}".format(
            "true" if opts.include_materials_textures and opts.embed_media else "false"
        ),
        "FBXExportConstraints -v false",
        "FBXExportCameras -v {0}".format("true" if opts.include_cameras else "false"),
        "FBXExportLights -v {0}".format("true" if opts.include_lights else "false"),
        # In Maya 2026 this is the supported material/texture export switch.
        "FBXExportInputConnections -v {0}".format(
            "true" if opts.include_materials_textures else "false"
        ),
        "FBXExportUpAxis {0}".format(axis.lower()),
        'FBXExportConvertUnitString -v "{0}"'.format(unit),
        "FBXExportFileVersion -v FBX202000",
        "FBXExportApplyConstantKeyReducer -v false",
    ]
    if opts.bake_animation:
        commands.extend(
            [
                "FBXExportBakeComplexAnimation -v true",
                "FBXExportBakeComplexStart -v {0}".format(start),
                "FBXExportBakeComplexEnd -v {0}".format(end),
                "FBXExportBakeComplexStep -v 1",
            ]
        )
    else:
        commands.append("FBXExportBakeComplexAnimation -v false")
    # ``-s`` is the important selection-only guard.  Never silently export
    # the whole scene even when the plug-in has IncludeGrp enabled globally.
    commands.append('FBXExport -f "{0}" -s'.format(path_text))
    return commands


def _capture_fbx_settings(mel_api=None):
    api = mel_api or mel
    if api is None:
        return None
    captured = {}
    for command_name in _FBX_RESTORABLE_SETTINGS:
        try:
            captured[command_name] = api.eval("{0} -q".format(command_name))
        except Exception:
            return None
    if set(captured) != set(_FBX_RESTORABLE_SETTINGS):
        return None
    return captured


def _mel_literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if str(value).strip().lower() in ("true", "false"):
        return str(value).strip().lower()
    return '"{0}"'.format(str(value).replace('"', '\\"'))


def _restore_fbx_settings(captured, mel_api=None):
    api = mel_api or mel
    if api is None or not isinstance(captured, dict):
        return
    for command_name in _FBX_RESTORABLE_SETTINGS:
        if command_name not in captured:
            continue
        value = captured[command_name]
        try:
            if command_name == "FBXExportUpAxis":
                api.eval("{0} {1}".format(command_name, str(value).strip().lower()))
            else:
                api.eval("{0} -v {1}".format(command_name, _mel_literal(value)))
        except Exception:
            # Restoration is best effort, while the caller reports whether a
            # complete post-export snapshot matched the original snapshot.
            pass


def _fbx_settings_match(before, after):
    expected = set(_FBX_RESTORABLE_SETTINGS)
    return (
        isinstance(before, dict)
        and isinstance(after, dict)
        and set(before) == expected
        and set(after) == expected
        and all(after.get(key) == before.get(key) for key in expected)
    )


def _ensure_fbx_plugin(cmds_api):
    try:
        if bool(cmds_api.pluginInfo(FBX_PLUGIN_NAME, query=True, loaded=True)):
            return True, ""
    except Exception:
        pass
    try:
        cmds_api.loadPlugin(FBX_PLUGIN_NAME, quiet=True)
    except Exception as exc:
        return False, "The fbxmaya plug-in could not be loaded: {0}".format(exc)
    try:
        if not bool(cmds_api.pluginInfo(FBX_PLUGIN_NAME, query=True, loaded=True)):
            return False, "The fbxmaya plug-in is not loaded; no FBX was written."
    except Exception as exc:
        return False, "Could not verify the fbxmaya plug-in: {0}".format(exc)
    return True, ""


def _perform_export(path, options=None, cmds_api=None, mel_api=None):
    """Return a detailed, testable export result dictionary."""
    opts = normalize_options(options)
    api = cmds_api or cmds
    mel_module = mel_api or mel
    normalized, error = _valid_fbx_path(path)
    result = {
        "success": False,
        "message": "",
        "path": normalized,
        "selection_only": True,
        "selection": [],
        "visible_range": None,
        "settings_restored": False,
        "settings_before": None,
        "settings_after": None,
        "commands": [],
        "fresh_output": False,
    }
    if error:
        result["message"] = error
        return result
    if os.path.exists(normalized) and not bool(opts.overwrite):
        result["message"] = "The FBX path already exists. Choose a new filename or explicitly allow overwrite."
        return result
    if api is None or mel_module is None:
        result["message"] = "Selected-animation FBX export only works inside Maya with the FBX plug-in."
        return result
    selected = _selected_objects(api)
    result["selection"] = list(selected)
    if not selected:
        result["message"] = "Select at least one object before exporting selected animation FBX."
        return result
    plugin_ok, plugin_error = _ensure_fbx_plugin(api)
    if not plugin_ok:
        result["message"] = plugin_error
        return result
    settings_before = _capture_fbx_settings(mel_api=mel_module)
    if settings_before is None:
        result["message"] = "Could not capture every FBX setting; export was not started."
        return result
    result["settings_before"] = dict(settings_before)
    visible_range = current_visible_playback_range(cmds_api=api)
    result["visible_range"] = tuple(visible_range)
    commands = _fbx_mel_commands(normalized, opts, visible_range=visible_range, cmds_api=api)
    result["commands"] = list(commands)
    selection_before = list(selected)
    export_started = time.time()
    export_error = ""
    try:
        api.select(selection_before, replace=True)
        for command in commands:
            mel_module.eval(command)
    except Exception as exc:
        export_error = str(exc)
    finally:
        _restore_fbx_settings(settings_before, mel_api=mel_module)
        try:
            api.select(selection_before, replace=True)
        except Exception:
            pass
    settings_after = _capture_fbx_settings(mel_api=mel_module)
    result["settings_after"] = dict(settings_after or {})
    result["settings_restored"] = _fbx_settings_match(settings_before, settings_after)
    file_exists = os.path.isfile(normalized)
    result["fresh_output"] = bool(
        file_exists
        and os.path.getsize(normalized) > 0
        and os.path.getmtime(normalized) >= (export_started - 2.0)
    )
    if export_error:
        result["message"] = "Selected-animation FBX export failed: {0}".format(export_error)
    elif not result["fresh_output"]:
        result["message"] = "Maya reported export, but no non-empty fresh FBX file was created."
    elif not result["settings_restored"]:
        result["message"] = "FBX export finished, but the previous FBX settings were not restored."
    else:
        result["success"] = True
        result["message"] = "Selected animation FBX exported: {0}".format(normalized)
    return result


def export_selected_animation_fbx(path, options=None, cmds_api=None, mel_api=None):
    """Export selected objects and return ``(success, message)``."""
    result = _perform_export(path, options=options, cmds_api=cmds_api, mel_api=mel_api)
    return bool(result.get("success")), str(result.get("message") or "")


def _maya_scene_default_path(cmds_api=None):
    api = cmds_api or cmds
    if api is None:
        return ""
    try:
        scene_name = api.file(query=True, sceneName=True) or "untitled"
    except Exception:
        scene_name = "untitled"
    stem = os.path.splitext(os.path.basename(str(scene_name)))[0] or "untitled"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
    return os.path.join(os.path.dirname(str(scene_name)) if os.path.dirname(str(scene_name)) else os.getcwd(), stem + "_selected_animation.fbx")


if QtWidgets:

    class SelectedAnimationFbxOptionsDialog(QtWidgets.QDialog):
        """Small, safe options panel used by the Toolkit Bar button."""

        def __init__(self, parent=None, cmds_api=None):
            super(SelectedAnimationFbxOptionsDialog, self).__init__(parent)
            self.cmds_api = cmds_api or cmds
            self.options = SelectedAnimationFbxOptions()
            self._build_ui()
            self._refresh_visible_range()

        def _build_ui(self):
            self.setObjectName("selectedAnimationFbxOptionsDialog")
            self.setWindowTitle(DISPLAY_NAME)
            self.setMinimumWidth(440)
            root = QtWidgets.QVBoxLayout(self)
            root.setContentsMargins(12, 12, 12, 12)
            root.setSpacing(8)

            intro = QtWidgets.QLabel("Export selected objects only. The visible Time Slider range is baked.")
            intro.setWordWrap(True)
            root.addWidget(intro)

            output_row = QtWidgets.QHBoxLayout()
            output_row.addWidget(QtWidgets.QLabel("Output FBX"))
            self.output_edit = QtWidgets.QLineEdit()
            self.output_edit.setPlaceholderText("Choose a new .fbx file")
            self.output_edit.setText(_maya_scene_default_path(self.cmds_api))
            output_row.addWidget(self.output_edit, 1)
            self.browse_button = QtWidgets.QPushButton("Browse…")
            self.browse_button.clicked.connect(self._browse_output)
            output_row.addWidget(self.browse_button)
            root.addLayout(output_row)

            self.range_label = QtWidgets.QLabel("Visible range: reading Maya…")
            self.range_label.setObjectName("selectedAnimationFbxVisibleRange")
            root.addWidget(self.range_label)

            settings = QtWidgets.QGroupBox("Export options")
            settings_layout = QtWidgets.QGridLayout(settings)
            self.bake_checkbox = QtWidgets.QCheckBox("Resample visible playback range (every frame)")
            self.bake_checkbox.setChecked(False)
            self.bake_checkbox.setToolTip(
                "Off by default: keep the original source keyframe times. Turn this on only when a dense whole-frame FBX bake is required."
            )
            settings_layout.addWidget(self.bake_checkbox, 0, 0, 1, 2)
            self.geometry_checkbox = QtWidgets.QCheckBox("Geometry")
            self.geometry_checkbox.setChecked(True)
            self.skinning_checkbox = QtWidgets.QCheckBox("Skinning")
            self.skinning_checkbox.setChecked(True)
            self.shapes_checkbox = QtWidgets.QCheckBox("Blend shapes")
            self.shapes_checkbox.setChecked(True)
            self.tangents_checkbox = QtWidgets.QCheckBox("Tangents / binormals")
            self.tangents_checkbox.setChecked(True)
            self.materials_checkbox = QtWidgets.QCheckBox("Materials / textures")
            self.materials_checkbox.setChecked(True)
            self.embed_checkbox = QtWidgets.QCheckBox("Embed media")
            self.embed_checkbox.setChecked(True)
            self.cameras_checkbox = QtWidgets.QCheckBox("Cameras")
            self.cameras_checkbox.setChecked(False)
            self.lights_checkbox = QtWidgets.QCheckBox("Lights")
            self.lights_checkbox.setChecked(False)
            controls = (
                self.geometry_checkbox,
                self.skinning_checkbox,
                self.shapes_checkbox,
                self.tangents_checkbox,
                self.materials_checkbox,
                self.embed_checkbox,
                self.cameras_checkbox,
                self.lights_checkbox,
            )
            for index, control in enumerate(controls):
                settings_layout.addWidget(control, 1 + index // 2, index % 2)
            root.addWidget(settings)

            axis_row = QtWidgets.QHBoxLayout()
            axis_row.addWidget(QtWidgets.QLabel("Up axis"))
            self.up_axis_combo = QtWidgets.QComboBox()
            self.up_axis_combo.addItems(["Y", "Z"])
            self.up_axis_combo.setCurrentText(DEFAULT_UP_AXIS)
            axis_row.addWidget(self.up_axis_combo)
            axis_row.addWidget(QtWidgets.QLabel("Scale"))
            self.scale_combo = QtWidgets.QComboBox()
            self.scale_combo.addItems([label for label, _unit in SCALE_CHOICES])
            self.scale_combo.setCurrentText(UNREAL_SCALE_LABEL)
            axis_row.addWidget(self.scale_combo, 1)
            root.addLayout(axis_row)

            self.overwrite_checkbox = QtWidgets.QCheckBox("Allow overwrite (explicit choice)")
            self.overwrite_checkbox.setChecked(False)
            self.overwrite_checkbox.setToolTip("Existing files are never replaced unless this is checked explicitly.")
            root.addWidget(self.overwrite_checkbox)

            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
            buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Export FBX")
            buttons.accepted.connect(self._accept_export)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

        def _refresh_visible_range(self):
            start, end = current_visible_playback_range(cmds_api=self.cmds_api)
            self.visible_range = (start, end)
            self.range_label.setText("Visible range: {0:g} – {1:g}".format(start, end))

        def _browse_output(self):
            path, _filter = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Export selected animation FBX",
                self.output_edit.text() or DEFAULT_OUTPUT_NAME,
                "FBX files (*.fbx)",
            )
            if path:
                self.output_edit.setText(path)

        def _options_from_ui(self):
            return SelectedAnimationFbxOptions(
                bake_animation=self.bake_checkbox.isChecked(),
                include_geometry=self.geometry_checkbox.isChecked(),
                include_skinning=self.skinning_checkbox.isChecked(),
                include_blend_shapes=self.shapes_checkbox.isChecked(),
                include_tangents_binormals=self.tangents_checkbox.isChecked(),
                include_materials_textures=self.materials_checkbox.isChecked(),
                embed_media=self.embed_checkbox.isChecked(),
                include_cameras=self.cameras_checkbox.isChecked(),
                include_lights=self.lights_checkbox.isChecked(),
                up_axis=self.up_axis_combo.currentText(),
                scale_label=self.scale_combo.currentText(),
                overwrite=self.overwrite_checkbox.isChecked(),
                output_path=self.output_edit.text().strip(),
            )

        def _accept_export(self):
            opts = self._options_from_ui()
            normalized, error = _valid_fbx_path(opts.output_path)
            if error:
                QtWidgets.QMessageBox.warning(self, "Export selected animation FBX", error)
                return
            if os.path.exists(normalized) and not opts.overwrite:
                answer = QtWidgets.QMessageBox.question(
                    self,
                    "Replace existing FBX?",
                    "The selected file already exists. Replace it? This is an explicit overwrite choice.",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No,
                )
                if answer != QtWidgets.QMessageBox.Yes:
                    return
                opts.overwrite = True
            self.options = opts
            success, message = export_selected_animation_fbx(
                normalized,
                options=opts,
                cmds_api=self.cmds_api,
                mel_api=mel,
            )
            if success:
                self.accept()
            else:
                QtWidgets.QMessageBox.warning(self, "Export selected animation FBX", message)


else:
    SelectedAnimationFbxOptionsDialog = None


def show_selected_animation_fbx_options(parent=None, status_callback=None, controller=None):
    """Open the Toolkit Bar options panel and return ``(success, message)``."""
    if not MAYA_AVAILABLE or not QtWidgets:
        message = "Selected-animation FBX export needs Maya's Qt UI."
        if status_callback:
            status_callback(message, False)
        return False, message
    dialog = SelectedAnimationFbxOptionsDialog(parent=parent)
    result = dialog.exec_() if hasattr(dialog, "exec_") else dialog.exec()
    if not result:
        message = "Selected-animation FBX export cancelled."
        if status_callback:
            status_callback(message, False)
        return False, message
    # The dialog performs the export before accepting.  Its options retain the
    # output path for a useful status message and for controller tests.
    message = "Selected animation FBX exported: {0}".format(dialog.options.output_path)
    if status_callback:
        status_callback(message, True)
    return True, message


# Friendly aliases for callers/tests that use the shorter name.
SelectedAnimationFbxExportOptions = SelectedAnimationFbxOptions
build_fbx_mel_commands = _fbx_mel_commands
capture_fbx_settings = _capture_fbx_settings
restore_fbx_settings = _restore_fbx_settings
