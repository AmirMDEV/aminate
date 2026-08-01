from __future__ import absolute_import, division, print_function

import json
import glob
import os
import re
import shutil
import time

try:
    import maya.cmds as cmds
    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtCore, QtWidgets
except Exception:
    try:
        from PySide2 import QtCore, QtWidgets
    except Exception:
        QtCore = QtWidgets = None

try:
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
except Exception:
    MayaQWidgetDockableMixin = None

WINDOW_OBJECT_NAME = "mayaReferenceManagerWindow"
PACKAGE_FOLDER_NAME = "reference_packages"
MANIFEST_FILE_NAME = "reference_package_manifest.json"
MAYA_ASCII_TYPE = "mayaAscii"
MAYA_BINARY_TYPE = "mayaBinary"
UNKNOWN_NODE_TYPES = ("unknown", "unknownDag", "unknownTransform")

REFERENCE_MANAGER_ATTR_SPECS = (
    ("file", "fileTextureName", "sourceimages", "Material Texture"),
    ("imagePlane", "imageName", "sourceimages", "Image Plane"),
    ("transform", "amirVideoSourcePath", "video", "Video Reference Source"),
    ("audio", "filename", "audio", "Audio"),
    ("AlembicNode", "abc_File", "cache", "Alembic Cache"),
    ("gpuCache", "cacheFileName", "cache", "GPU Cache"),
)

_NUMBERED_FRAME_NAME = re.compile(r"^(.*?)(\d+)(\.[^.]+)$")


def _numbered_sequence_paths(source_path):
    """Return matching numbered siblings for a camera image-plane sequence."""
    if not source_path or not os.path.isfile(source_path):
        return []
    folder_path = os.path.dirname(source_path)
    file_name = os.path.basename(source_path)
    match = _NUMBERED_FRAME_NAME.match(file_name)
    if not match:
        return []
    prefix, _digits, suffix = match.groups()
    pattern = os.path.join(folder_path, prefix + "*" + suffix)
    candidates = []
    for candidate in glob.glob(pattern):
        candidate_name = os.path.basename(candidate)
        candidate_match = _NUMBERED_FRAME_NAME.match(candidate_name)
        if not candidate_match or candidate_match.group(1) != prefix or candidate_match.group(3) != suffix:
            continue
        if os.path.isfile(candidate):
            candidates.append(candidate)
    return sorted(set(candidates), key=lambda path: (int(_NUMBERED_FRAME_NAME.match(os.path.basename(path)).group(2)), os.path.basename(path)))


def _maya_main_window():
    if not MAYA_AVAILABLE or not QtWidgets:
        return None
    try:
        import maya.OpenMayaUI as omui
        try:
            import shiboken6 as shiboken
        except Exception:
            import shiboken2 as shiboken
        ptr = omui.MQtUtil.mainWindow()
        if ptr is None:
            return None
        return shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        return None


def _normalize_path(path_value):
    if not path_value:
        return ""
    path_value = os.path.expandvars(str(path_value)).replace("/", os.sep)
    return os.path.normpath(path_value)


def _resolve_existing_path(path_value):
    normalized = _normalize_path(path_value)
    if not normalized:
        return ""
    if os.path.exists(normalized) or os.path.isabs(normalized):
        return normalized
    roots = [
        _scene_folder(),
        _workspace_root(),
        os.path.join(_workspace_root(), "sourceimages"),
        os.path.join(_workspace_root(), "textures"),
        os.path.join(_scene_folder(), "sourceimages"),
        os.path.join(_scene_folder(), "textures"),
    ]
    for root_path in roots:
        if not root_path:
            continue
        candidate = _normalize_path(os.path.join(root_path, normalized))
        if os.path.exists(candidate):
            return candidate
    return normalized


def _scene_path():
    if not cmds:
        return ""
    return _normalize_path(cmds.file(query=True, sceneName=True) or "")


def _workspace_root():
    if not cmds:
        return os.getcwd()
    try:
        return _normalize_path(cmds.workspace(query=True, rootDirectory=True) or "")
    except Exception:
        return os.getcwd()


def _scene_folder():
    scene_name = _scene_path()
    if scene_name:
        return os.path.dirname(scene_name)
    return _workspace_root() or os.getcwd()


def _scene_file_type(scene_path=None):
    scene_path = scene_path or _scene_path()
    ext = os.path.splitext(scene_path or "")[1].lower()
    if ext == ".mb":
        return MAYA_BINARY_TYPE, ".mb"
    return MAYA_ASCII_TYPE, ".ma"


def _safe_slug(value, fallback="scene"):
    value = os.path.splitext(os.path.basename(value or ""))[0] or fallback
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or fallback


def _unique_path(path_value):
    if not os.path.exists(path_value):
        return path_value
    root, ext = os.path.splitext(path_value)
    index = 1
    while os.path.exists("{0}_{1}{2}".format(root, index, ext)):
        index += 1
    return "{0}_{1}{2}".format(root, index, ext)


def _unique_dest_path(folder_path, file_name):
    safe_name = os.path.basename(file_name or "file")
    candidate = os.path.join(folder_path, safe_name)
    return _unique_path(candidate)


def _copy_file(source_path, destination_path):
    folder_path = os.path.dirname(destination_path)
    if folder_path and not os.path.isdir(folder_path):
        os.makedirs(folder_path)
    shutil.copy2(source_path, destination_path)


def _relative_to_scene(package_scene_path, copied_path):
    try:
        return os.path.relpath(copied_path, os.path.dirname(package_scene_path)).replace(os.sep, "/")
    except Exception:
        return copied_path.replace(os.sep, "/")


def _rewrite_packaged_scene_paths(package_scene_path, package_dir, copied_records):
    if not package_scene_path.lower().endswith(".ma") or not os.path.exists(package_scene_path):
        return False
    try:
        with open(package_scene_path, "r") as handle:
            scene_text = handle.read()
    except Exception:
        return False
    updated_text = scene_text
    for record in copied_records:
        absolute_path = _normalize_path(record.get("package_path", ""))
        source_path = _normalize_path(record.get("source", ""))
        raw_source = str(record.get("raw_source", "") or "")
        if not absolute_path:
            continue
        relative_path = _relative_to_scene(package_scene_path, absolute_path)
        path_variants = [
            source_path,
            source_path.replace(os.sep, "/"),
            source_path.replace("/", "\\"),
            source_path.replace("\\", "/"),
            source_path.replace("\\", "\\\\"),
            raw_source,
            raw_source.replace(os.sep, "/"),
            raw_source.replace("/", "\\"),
            raw_source.replace("\\", "/"),
            raw_source.replace("\\", "\\\\"),
            absolute_path,
            absolute_path.replace(os.sep, "/"),
            absolute_path.replace("/", "\\"),
            absolute_path.replace("\\", "/"),
            absolute_path.replace("\\", "\\\\"),
        ]
        for path_variant in path_variants:
            updated_text = updated_text.replace(path_variant, relative_path)
    if updated_text == scene_text:
        return False
    with open(package_scene_path, "w") as handle:
        handle.write(updated_text)
    return True


def _dedupe_records(records):
    deduped = []
    seen = set()
    for record in records:
        source = _normalize_path(record.get("source", ""))
        key = (record.get("kind", ""), source.lower(), record.get("node", ""), record.get("attr", ""))
        if key in seen:
            continue
        seen.add(key)
        record["source"] = source
        record["exists"] = bool(source and os.path.exists(source))
        deduped.append(record)
    return deduped


def _dependency_display_kind(record):
    return record.get("display_kind") or record.get("kind") or "File"


def _missing_dependency_summary(records):
    counts = {}
    for record in records:
        if record.get("exists"):
            continue
        display_kind = _dependency_display_kind(record)
        counts[display_kind] = counts.get(display_kind, 0) + 1
    if not counts:
        return ""
    parts = []
    for display_kind in sorted(counts):
        count = counts[display_kind]
        suffix = "" if count == 1 else "s"
        parts.append("{0} {1}{2}".format(count, display_kind, suffix))
    return ", ".join(parts)


def _reference_node_path(ref_node):
    try:
        return cmds.referenceQuery(ref_node, filename=True, withoutCopyNumber=True)
    except Exception:
        try:
            return cmds.referenceQuery(ref_node, filename=True)
        except Exception:
            return ""


def _collect_reference_records():
    if not cmds:
        return []
    records = []
    ref_nodes = cmds.ls(type="reference") or []
    for ref_node in ref_nodes:
        if ref_node == "sharedReferenceNode":
            continue
        source_path = _resolve_existing_path(_reference_node_path(ref_node))
        if not source_path:
            continue
        try:
            loaded = bool(cmds.referenceQuery(ref_node, isLoaded=True))
        except Exception:
            loaded = False
        records.append(
            {
                "kind": "reference",
                "display_kind": "Maya Reference",
                "node": ref_node,
                "attr": "",
                "raw_source": _reference_node_path(ref_node),
                "source": source_path,
                "folder": "references",
                "loaded": loaded,
            }
        )
    return _dedupe_records(records)


def _collect_external_records():
    if not cmds:
        return []
    records = []
    try:
        available_node_types = set(cmds.allNodeTypes() or [])
    except Exception:
        available_node_types = set()
    for node_type, attr_name, folder_name, display_kind in REFERENCE_MANAGER_ATTR_SPECS:
        if available_node_types and node_type not in available_node_types:
            continue
        try:
            nodes = cmds.ls(type=node_type) or []
        except Exception:
            nodes = []
        for node_name in nodes:
            raw_source = ""
            try:
                if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
                    continue
                raw_source = cmds.getAttr("{0}.{1}".format(node_name, attr_name)) or ""
            except Exception:
                raw_source = ""
            source_path = raw_source
            source_path = _resolve_existing_path(source_path)
            if not source_path:
                continue
            sequence_paths = []
            sequence_folder = folder_name
            if node_type == "imagePlane" and attr_name == "imageName":
                try:
                    uses_frame_extension = bool(cmds.getAttr(node_name + ".useFrameExtension"))
                except Exception:
                    uses_frame_extension = False
                if uses_frame_extension:
                    sequence_paths = _numbered_sequence_paths(source_path)
                    if len(sequence_paths) > 1:
                        sequence_folder = "video"
            records.append(
                {
                    "kind": "external",
                    "display_kind": display_kind,
                    "node_type": node_type,
                    "node": node_name,
                    "attr": attr_name,
                    "raw_source": raw_source,
                    "source": source_path,
                    "folder": sequence_folder,
                    "loaded": True,
                }
            )
            if sequence_paths:
                first_frame = sequence_paths[0]
                for frame_path in sequence_paths:
                    if _normalize_path(frame_path) == _normalize_path(source_path):
                        continue
                    records.append(
                        {
                            "kind": "external",
                            "display_kind": "Video Proxy Frame",
                            "node_type": node_type,
                            "node": node_name,
                            "attr": attr_name,
                            "raw_source": frame_path,
                            "source": frame_path,
                            "folder": "video",
                            "sequence_first_source": first_frame,
                            "loaded": True,
                        }
                    )
    return _dedupe_records(records)


def _unknown_nodes():
    if not cmds:
        return []
    nodes = []
    for node_type in UNKNOWN_NODE_TYPES:
        try:
            nodes.extend(cmds.ls(type=node_type, long=True) or [])
        except Exception:
            continue
    seen = set()
    result = []
    for node_name in nodes:
        if node_name in seen:
            continue
        seen.add(node_name)
        result.append(node_name)
    return result


def _unknown_plugins():
    if not cmds:
        return []
    try:
        return cmds.unknownPlugin(query=True, list=True) or []
    except Exception:
        return []


def _inspect_unknown_scene_data():
    nodes = _unknown_nodes()
    plugins = _unknown_plugins()
    node_records = []
    for node_name in nodes:
        node_type = ""
        plugin_name = ""
        try:
            node_type = cmds.nodeType(node_name)
        except Exception:
            pass
        try:
            plugin_name = cmds.unknownNode(node_name, query=True, plugin=True) or ""
        except Exception:
            plugin_name = ""
        node_records.append({"node": node_name, "type": node_type, "plugin": plugin_name})
    return {
        "nodes": node_records,
        "plugins": plugins,
        "node_count": len(node_records),
        "plugin_count": len(plugins),
    }


def _clean_unknown_scene_data(remove_nodes=True, remove_plugins=True):
    report = _inspect_unknown_scene_data()
    deleted_nodes = []
    removed_plugins = []
    failed = []
    if remove_nodes:
        for record in report["nodes"]:
            node_name = record.get("node")
            if not node_name or not cmds.objExists(node_name):
                continue
            try:
                cmds.lockNode(node_name, lock=False)
            except Exception:
                pass
            try:
                cmds.delete(node_name)
                deleted_nodes.append(node_name)
            except Exception as exc:
                failed.append("Could not delete {0}: {1}".format(node_name, exc))
    if remove_plugins:
        for plugin_name in report["plugins"]:
            try:
                cmds.unknownPlugin(plugin_name, remove=True)
                removed_plugins.append(plugin_name)
            except Exception as exc:
                failed.append("Could not remove unknown plugin {0}: {1}".format(plugin_name, exc))
    refreshed = _inspect_unknown_scene_data()
    return {
        "before": report,
        "after": refreshed,
        "deleted_nodes": deleted_nodes,
        "removed_plugins": removed_plugins,
        "failed": failed,
    }


class ReferencePackageController(object):
    def __init__(self, status_callback=None):
        self.status_callback = status_callback
        self.last_result = {}

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _emit_status(self, message, ok=True):
        if self.status_callback:
            self.status_callback(message, ok)

    def collect_dependencies(self, include_references=True, include_external=True):
        if not MAYA_AVAILABLE:
            raise RuntimeError("Reference Manager must run inside Maya.")
        records = []
        if include_references:
            records.extend(_collect_reference_records())
        if include_external:
            records.extend(_collect_external_records())
        return {
            "scene": _scene_path(),
            "records": _dedupe_records(records),
        }

    def inspect_unknown_scene_data(self):
        if not MAYA_AVAILABLE:
            raise RuntimeError("Reference Manager must run inside Maya.")
        return _inspect_unknown_scene_data()

    def clean_unknown_scene_data(self):
        if not MAYA_AVAILABLE:
            raise RuntimeError("Reference Manager must run inside Maya.")
        report = _clean_unknown_scene_data(remove_nodes=True, remove_plugins=True)
        deleted = len(report.get("deleted_nodes") or [])
        removed = len(report.get("removed_plugins") or [])
        failed = len(report.get("failed") or [])
        remaining = (report.get("after") or {}).get("node_count", 0) + (report.get("after") or {}).get("plugin_count", 0)
        ok = failed == 0 and remaining == 0
        message = "Cleaned {0} unknown node(s) and {1} unknown plugin record(s).".format(deleted, removed)
        if failed:
            message += " {0} cleanup item(s) failed.".format(failed)
        if remaining:
            message += " {0} unknown item(s) still remain.".format(remaining)
        self._emit_status(message, ok)
        return report

    def default_output_dir(self):
        return os.path.join(_scene_folder(), PACKAGE_FOLDER_NAME)

    def package_current_scene(
        self,
        output_dir=None,
        package_name=None,
        include_references=True,
        include_external=True,
        save_scene=False,
        retarget_package_scene=True,
    ):
        if not MAYA_AVAILABLE:
            raise RuntimeError("Reference Manager must run inside Maya.")
        original_scene = _scene_path()
        if not original_scene:
            raise RuntimeError("Save the scene once before packaging.")
        warnings = []
        if save_scene:
            cmds.file(save=True, force=True)
        elif cmds.file(query=True, modified=True):
            warnings.append(
                "Current scene has unsaved changes. Package used the last saved scene file because Save current scene first is off."
            )

        dependencies = self.collect_dependencies(include_references=include_references, include_external=include_external)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base_name = _safe_slug(package_name or original_scene)
        output_dir = _normalize_path(output_dir or self.default_output_dir())
        package_dir = _unique_path(os.path.join(output_dir, "{0}_{1}".format(base_name, timestamp)))
        scenes_dir = os.path.join(package_dir, "scenes")
        os.makedirs(scenes_dir)
        scene_type, scene_ext = _scene_file_type(original_scene)
        package_scene_path = os.path.join(scenes_dir, "{0}_packaged{1}".format(base_name, scene_ext))

        copied_records = []
        missing_records = []
        for record in dependencies["records"]:
            source_path = record["source"]
            if not source_path or not os.path.exists(source_path):
                missing_records.append(dict(record))
                continue
            destination_dir = os.path.join(package_dir, record.get("folder") or "external")
            destination_path = _unique_dest_path(destination_dir, os.path.basename(source_path))
            _copy_file(source_path, destination_path)
            packaged_record = dict(record)
            packaged_record["package_path"] = destination_path
            packaged_record["package_relpath"] = os.path.relpath(destination_path, package_dir).replace(os.sep, "/")
            copied_records.append(packaged_record)

        _copy_file(original_scene, package_scene_path)
        if retarget_package_scene:
            if package_scene_path.lower().endswith(".ma"):
                rewrote_paths = _rewrite_packaged_scene_paths(package_scene_path, package_dir, copied_records)
                if not rewrote_paths:
                    warnings.append("Packaged Maya ASCII scene was copied safely, but no dependency paths needed text retargeting.")
            else:
                warnings.append(
                    "Packaged Maya Binary scene was copied safely without opening the scene. "
                    "Dependencies are included in the zip, but binary scene paths are not rewritten."
                )

        manifest = {
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "original_scene": original_scene,
            "scene_file_type": scene_type,
            "packaged_scene": os.path.relpath(package_scene_path, package_dir).replace(os.sep, "/"),
            "copied_files": [
                {
                    "kind": record.get("kind"),
                    "display_kind": record.get("display_kind"),
                    "node_type": record.get("node_type"),
                    "node": record.get("node"),
                    "attr": record.get("attr"),
                    "raw_source": record.get("raw_source"),
                    "source": record.get("source"),
                    "package_relpath": record.get("package_relpath"),
                    "loaded": record.get("loaded"),
                }
                for record in copied_records
            ],
            "missing_files": missing_records,
            "warnings": warnings,
        }
        manifest_path = os.path.join(package_dir, MANIFEST_FILE_NAME)
        with open(manifest_path, "w") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)

        zip_path = shutil.make_archive(package_dir, "zip", output_dir, os.path.basename(package_dir))
        result = {
            "package_dir": package_dir,
            "zip_path": zip_path,
            "package_scene": package_scene_path,
            "copied_count": len(copied_records),
            "missing_count": len(missing_records),
            "warnings": warnings,
            "manifest_path": manifest_path,
        }
        self.last_result = result
        message = "Packaged scene zip with {0} file(s): {1}".format(len(copied_records), zip_path)
        if missing_records:
            missing_summary = _missing_dependency_summary(missing_records)
            message += " Missing {0}.".format(missing_summary or "{0} file(s)".format(len(missing_records)))
        self._emit_status(message, not bool(missing_records))
        return result


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        _HAS_MAYA_MAIN_WINDOW = MQtUtil.mainWindow() is not None
    except Exception:
        _HAS_MAYA_MAIN_WINDOW = False
    if MayaQWidgetDockableMixin is not None and _HAS_MAYA_MAIN_WINDOW:
        _WindowBase = type("MayaReferenceManagerWindowBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
    else:
        _WindowBase = type("MayaReferenceManagerWindowBase", (QtWidgets.QDialog,), {})

    class ReferenceManagerPanel(QtWidgets.QWidget):
        def __init__(self, controller=None, status_callback=None, parent=None):
            super(ReferenceManagerPanel, self).__init__(parent)
            self.controller = controller or ReferencePackageController()
            self.status_callback = status_callback
            self.controller.set_status_callback(self._set_status)
            self.setMinimumWidth(0)
            self._build_ui()
            self.refresh_files()

        def _build_ui(self):
            outer_layout = QtWidgets.QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName("referenceManagerContentScroll")
            scroll.setWidgetResizable(True)
            scroll.setMinimumWidth(0)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            content = QtWidgets.QWidget()
            content.setObjectName("referenceManagerContent")
            content.setMinimumWidth(0)
            layout = QtWidgets.QVBoxLayout(content)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            intro = QtWidgets.QLabel(
                "Package the current scene plus Maya references, textures, image planes, audio, caches, and a manifest into one zip."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

            package_group = QtWidgets.QGroupBox("Package Scene")
            package_layout = QtWidgets.QVBoxLayout(package_group)
            package_layout.setContentsMargins(8, 8, 8, 8)
            package_layout.setSpacing(6)

            output_row = QtWidgets.QHBoxLayout()
            output_row.addWidget(QtWidgets.QLabel("Output folder"))
            self.output_path = QtWidgets.QLineEdit(self.controller.default_output_dir() if MAYA_AVAILABLE else "")
            self.output_path.setToolTip("Folder where Reference Manager writes package folder plus zip.")
            output_row.addWidget(self.output_path, 1)
            self.browse_button = QtWidgets.QPushButton("Browse")
            self.browse_button.setToolTip("Choose folder for created package zip.")
            output_row.addWidget(self.browse_button)
            package_layout.addLayout(output_row)

            name_row = QtWidgets.QHBoxLayout()
            name_row.addWidget(QtWidgets.QLabel("Package name"))
            default_name = _safe_slug(_scene_path(), "maya_scene") if MAYA_AVAILABLE else "maya_scene"
            self.package_name = QtWidgets.QLineEdit(default_name)
            self.package_name.setToolTip("Base name used for package folder, packaged scene, zip file.")
            name_row.addWidget(self.package_name, 1)
            package_layout.addLayout(name_row)

            options_row = QtWidgets.QHBoxLayout()
            self.save_scene_box = QtWidgets.QCheckBox("Save current scene first")
            self.save_scene_box.setChecked(False)
            self.save_scene_box.setToolTip(
                "Off by default for safety. Leave off to package the last saved file without changing the open scene."
            )
            self.references_box = QtWidgets.QCheckBox("Include Maya references")
            self.references_box.setChecked(True)
            self.references_box.setToolTip("Copy referenced Maya scenes from reference nodes into package references folder.")
            self.external_box = QtWidgets.QCheckBox("Include textures, audio, caches")
            self.external_box.setChecked(True)
            self.external_box.setToolTip("Copy file textures, image planes, audio, Alembic caches, GPU caches into package folders.")
            self.relative_box = QtWidgets.QCheckBox("Make packaged scene use relative paths")
            self.relative_box.setChecked(True)
            self.relative_box.setToolTip("Write packaged scene paths so extracted package can move to another computer.")
            for widget in (self.save_scene_box, self.references_box, self.external_box, self.relative_box):
                options_row.addWidget(widget)
            options_row.addStretch(1)
            package_layout.addLayout(options_row)

            action_row = QtWidgets.QHBoxLayout()
            self.refresh_button = QtWidgets.QPushButton("Refresh Needed Files")
            self.refresh_button.setToolTip("Scan current Maya scene for references plus external files before packaging.")
            self.package_button = QtWidgets.QPushButton("Package Scene To Zip")
            self.package_button.setToolTip("Copy the saved scene and needed files, write a manifest, and create a final zip package.")
            self.open_folder_button = QtWidgets.QPushButton("Open Package Folder")
            self.open_folder_button.setToolTip("Open folder containing latest package zip in Windows Explorer.")
            action_row.addWidget(self.refresh_button)
            action_row.addWidget(self.package_button)
            action_row.addWidget(self.open_folder_button)
            action_row.addStretch(1)
            package_layout.addLayout(action_row)
            layout.addWidget(package_group)

            cleanup_group = QtWidgets.QGroupBox("Scene Cleanup")
            cleanup_layout = QtWidgets.QVBoxLayout(cleanup_group)
            cleanup_layout.setContentsMargins(8, 8, 8, 8)
            cleanup_layout.setSpacing(6)
            cleanup_row = QtWidgets.QHBoxLayout()
            self.scan_unknown_button = QtWidgets.QPushButton("Scan Unknown Data")
            self.scan_unknown_button.setToolTip(
                "Check for unknown Maya nodes or unknown plugin records that can block file format changes."
            )
            self.clean_unknown_button = QtWidgets.QPushButton("Clean Unknown Data")
            self.clean_unknown_button.setToolTip(
                "Delete unknown nodes and remove unknown plugin records after a confirmation prompt. Save a backup first."
            )
            cleanup_row.addWidget(self.scan_unknown_button)
            cleanup_row.addWidget(self.clean_unknown_button)
            cleanup_row.addStretch(1)
            cleanup_layout.addLayout(cleanup_row)
            cleanup_hint = QtWidgets.QLabel("Scan first. Cleanup removes unknown nodes or plugin records after confirmation.")
            cleanup_hint.setWordWrap(True)
            cleanup_layout.addWidget(cleanup_hint)
            layout.addWidget(cleanup_group)

            self.files_table = QtWidgets.QTableWidget(0, 4)
            self.files_table.setHorizontalHeaderLabels(["Type", "Node", "Source", "Status"])
            self.files_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.files_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.files_table.setToolTip("Shows each referenced scene, material texture, image plane, audio file, or cache path plus found or missing state.")
            self.files_table.horizontalHeader().setStretchLastSection(True)
            self.files_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
            layout.addWidget(self.files_table, 1)

            self.status_label = QtWidgets.QLabel("Ready.")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)

            scroll.setWidget(content)
            outer_layout.addWidget(scroll)

            self.refresh_button.clicked.connect(self.refresh_files)
            self.package_button.clicked.connect(self.package_scene)
            self.open_folder_button.clicked.connect(self.open_package_folder)
            self.browse_button.clicked.connect(self.pick_output_folder)
            self.scan_unknown_button.clicked.connect(self.scan_unknown_data)
            self.clean_unknown_button.clicked.connect(self.clean_unknown_data)
            for option in (self.references_box, self.external_box):
                option.stateChanged.connect(lambda _state: self.refresh_files())
            self.output_path.textChanged.connect(self._validate_package_inputs)
            self.package_name.textChanged.connect(self._validate_package_inputs)
            self._validate_package_inputs()

        def _validate_package_inputs(self, *_args):
            output_dir = self.output_path.text().strip()
            package_name = self.package_name.text().strip()
            valid = bool(output_dir and package_name)
            self.package_button.setEnabled(valid)
            if not valid:
                self._set_status("Enter an output folder and package name before packaging.", False)

        def _set_status(self, message, ok=True):
            self.status_label.setText(message)
            if self.status_callback:
                self.status_callback(message, ok)

        def pick_output_folder(self):
            start_dir = self.output_path.text() or self.controller.default_output_dir()
            folder_path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose package output folder", start_dir)
            if folder_path:
                self.output_path.setText(folder_path)

        def refresh_files(self):
            self.files_table.setRowCount(0)
            try:
                data = self.controller.collect_dependencies(
                    include_references=self.references_box.isChecked(),
                    include_external=self.external_box.isChecked(),
                )
            except Exception as exc:
                self._set_status(str(exc), False)
                return
            for record in data["records"]:
                row = self.files_table.rowCount()
                self.files_table.insertRow(row)
                values = [
                    _dependency_display_kind(record),
                    record.get("node", ""),
                    record.get("source", ""),
                    "Found" if record.get("exists") else "Missing {0}".format(_dependency_display_kind(record)),
                ]
                for column, value in enumerate(values):
                    self.files_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
            missing_summary = _missing_dependency_summary(data["records"])
            message = "Found {0} file(s) needed by this scene.".format(len(data["records"]))
            if missing_summary:
                message += " Missing {0}.".format(missing_summary)
            self._set_status(message, not bool(missing_summary))

        def package_scene(self):
            if not self.output_path.text().strip() or not self.package_name.text().strip():
                self._set_status("Enter an output folder and package name before packaging.", False)
                return
            try:
                result = self.controller.package_current_scene(
                    output_dir=self.output_path.text(),
                    package_name=self.package_name.text(),
                    include_references=self.references_box.isChecked(),
                    include_external=self.external_box.isChecked(),
                    save_scene=self.save_scene_box.isChecked(),
                    retarget_package_scene=self.relative_box.isChecked(),
                )
            except Exception as exc:
                self._set_status(str(exc), False)
                return
            self._set_status("Zip ready: {0}".format(result["zip_path"]), True)
            self.refresh_files()

        def scan_unknown_data(self):
            try:
                report = self.controller.inspect_unknown_scene_data()
            except Exception as exc:
                self._set_status(str(exc), False)
                return
            self._set_status(
                "Unknown data scan: {0} unknown node(s), {1} unknown plugin record(s).".format(
                    report.get("node_count", 0),
                    report.get("plugin_count", 0),
                ),
                report.get("node_count", 0) == 0 and report.get("plugin_count", 0) == 0,
            )

        def clean_unknown_data(self):
            try:
                report = self.controller.inspect_unknown_scene_data()
            except Exception as exc:
                self._set_status(str(exc), False)
                return
            total = int(report.get("node_count", 0)) + int(report.get("plugin_count", 0))
            if not total:
                self._set_status("No unknown data found.", True)
                return
            message = (
                "This deletes {0} unknown node(s) and removes {1} unknown plugin record(s).\n\n"
                "Save a backup first if this is an important scene.\n\nContinue?"
            ).format(report.get("node_count", 0), report.get("plugin_count", 0))
            result = QtWidgets.QMessageBox.question(self, "Clean Unknown Data", message)
            if result != QtWidgets.QMessageBox.Yes:
                self._set_status("Unknown data cleanup cancelled.", False)
                return
            try:
                cleanup = self.controller.clean_unknown_scene_data()
            except Exception as exc:
                self._set_status(str(exc), False)
                return
            after = cleanup.get("after") or {}
            self._set_status(
                "Unknown data cleanup done. Remaining: {0} node(s), {1} plugin record(s).".format(
                    after.get("node_count", 0),
                    after.get("plugin_count", 0),
                ),
                not cleanup.get("failed") and not after.get("node_count", 0) and not after.get("plugin_count", 0),
            )

        def open_package_folder(self):
            result = self.controller.last_result or {}
            folder_path = result.get("package_dir") or self.output_path.text()
            if folder_path and os.path.exists(folder_path):
                try:
                    os.startfile(folder_path)
                except Exception:
                    self._set_status("Package folder is {0}".format(folder_path), True)

    class MayaReferenceManagerWindow(_WindowBase):
        def __init__(self, controller=None, parent=None):
            super(MayaReferenceManagerWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller or ReferencePackageController()
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Reference Manager")
            self.setMinimumSize(360, 360)
            self.resize(720, 560)
            layout = QtWidgets.QVBoxLayout(self)
            self.panel = ReferenceManagerPanel(self.controller, parent=self)
            layout.addWidget(self.panel)

        def closeEvent(self, event):
            # Maya-owned Qt wrappers stay alive and are hidden for reuse. Native
            # workspace destruction is a known Maya 2026 crash path.
            self.hide()
            event.ignore()


GLOBAL_WINDOW = None
GLOBAL_CONTROLLER = None


def launch_maya_reference_manager(dock=False):
    global GLOBAL_WINDOW
    global GLOBAL_CONTROLLER
    if not MAYA_AVAILABLE:
        raise RuntimeError("launch_maya_reference_manager() must run inside Maya.")
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
    GLOBAL_CONTROLLER = ReferencePackageController()
    GLOBAL_WINDOW = MayaReferenceManagerWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    if dock:
        try:
            GLOBAL_WINDOW.show(dockable=True, floating=False, area="right")
        except Exception:
            GLOBAL_WINDOW.show()
    else:
        GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "ReferencePackageController",
    "ReferenceManagerPanel",
    "MayaReferenceManagerWindow",
    "launch_maya_reference_manager",
]
