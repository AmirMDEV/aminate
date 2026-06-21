"""
maya_skin_transfer.py

Simple exact skin transfer for same-topology meshes.
"""

from __future__ import absolute_import, division, print_function

import difflib
import os
import re
import webbrowser

import maya_skinning_cleanup as skin_utils

try:
    import maya.cmds as cmds

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    MAYA_AVAILABLE = False

try:
    from PySide6 import QtWidgets
except Exception:
    try:
        from PySide2 import QtWidgets
    except Exception:
        QtWidgets = None


WINDOW_OBJECT_NAME = "mayaSkinTransferWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


def _debug(message):
    if MAYA_AVAILABLE:
        try:
            import maya.api.OpenMaya as om2

            om2.MGlobal.displayInfo("[Skin Transfer] {0}".format(message))
            return
        except Exception:
            pass
    print("[Skin Transfer] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE:
        try:
            import maya.api.OpenMaya as om2

            om2.MGlobal.displayWarning("[Skin Transfer] {0}".format(message))
            return
        except Exception:
            pass
    print("[Skin Transfer] {0}".format(message))


def _maya_main_window():
    try:
        return skin_utils._maya_main_window()
    except Exception:
        return None


def _style_donate_button(button):
    try:
        skin_utils._style_donate_button(button)
    except Exception:
        pass


def _open_external_url(url):
    try:
        return bool(skin_utils._open_external_url(url))
    except Exception:
        try:
            webbrowser.open(url)
            return True
        except Exception:
            return False


def _ordered_selection():
    ordered = cmds.ls(orderedSelection=True, long=True) or []
    if ordered:
        return ordered
    return cmds.ls(selection=True, long=True) or []


def _mesh_target_from_node(node_name):
    if not node_name or not cmds.objExists(node_name):
        return None
    if cmds.nodeType(node_name) == "mesh":
        shape = skin_utils._node_long_name(node_name)
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        if not parents:
            return None
        return {"transform": skin_utils._node_long_name(parents[0]), "shape": shape}
    transform = skin_utils._node_long_name(node_name)
    shapes = cmds.listRelatives(transform, shapes=True, fullPath=True, type="mesh") or []
    for shape in shapes:
        try:
            if cmds.getAttr(shape + ".intermediateObject"):
                continue
        except Exception:
            pass
        return {"transform": transform, "shape": skin_utils._node_long_name(shape)}
    return None


def _mesh_targets_from_selection():
    targets = []
    seen = set()
    for node_name in _ordered_selection():
        target = _mesh_target_from_node(node_name)
        if not target:
            continue
        key = target["shape"]
        if key in seen:
            continue
        seen.add(key)
        targets.append(target)
    return targets


def _short_list(targets):
    return ", ".join(skin_utils._short_name(item["transform"]) for item in targets) if targets else ""


def _counted_mesh_list(label, items):
    count = len(items)
    if count == 0:
        return "{0} (0)".format(label)
    if count == 1:
        return "{0} (1): {1}".format(label[:-1] if label.endswith("s") else label, _short_list(items))
    return "{0} ({1}): {2}".format(label, count, _short_list(items))


def _mesh_match_tokens(target):
    name = skin_utils._short_name((target or {}).get("transform", ""))
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    name = re.sub(r"[^a-zA-Z0-9]+", " ", name).lower()
    ignored = {
        "src",
        "source",
        "target",
        "tgt",
        "mesh",
        "geo",
        "geometry",
        "skin",
        "skinned",
        "copy",
        "new",
        "old",
    }
    return [token for token in name.split() if token and token not in ignored]


def _mesh_match_key(target):
    return "".join(_mesh_match_tokens(target))


def _mesh_match_score(source_target, target_target):
    source_key = _mesh_match_key(source_target)
    target_key = _mesh_match_key(target_target)
    if not source_key or not target_key:
        return 0.0
    if source_key == target_key:
        return 1.0
    source_tokens = set(_mesh_match_tokens(source_target))
    target_tokens = set(_mesh_match_tokens(target_target))
    overlap = float(len(source_tokens & target_tokens)) / float(max(1, len(source_tokens | target_tokens)))
    fuzzy = difflib.SequenceMatcher(None, source_key, target_key).ratio()
    return max(fuzzy, overlap)


def _name_map_mesh_pairs(sources, targets):
    remaining_targets = list(targets or [])
    pairs = []
    unmatched_sources = []
    for source_target in sources or []:
        best_target = None
        best_score = 0.0
        for target_target in remaining_targets:
            score = _mesh_match_score(source_target, target_target)
            if score > best_score:
                best_score = score
                best_target = target_target
        if best_target and best_score >= 0.45:
            pairs.append((source_target, best_target))
            remaining_targets.remove(best_target)
        else:
            unmatched_sources.append(source_target)
    return pairs, unmatched_sources, remaining_targets


def _topology_matches(source_shape, target_shape):
    source_topology = skin_utils._capture_topology_signature(source_shape)
    target_topology = skin_utils._capture_topology_signature(target_shape)
    return source_topology == target_topology, source_topology, target_topology


def _delete_existing_target_skin(target_shape):
    skin_cluster = skin_utils._find_skin_cluster(target_shape)
    if skin_cluster and cmds.objExists(skin_cluster):
        cmds.delete(skin_cluster)
    return skin_cluster


def _copy_exact_skin(source_target, target_target, replace_existing=True):
    source_shape = source_target["shape"]
    target_shape = target_target["shape"]
    source_skin = skin_utils._find_skin_cluster(source_shape)
    if not source_skin:
        raise RuntimeError("{0} is not skinned.".format(skin_utils._short_name(source_target["transform"])))

    matches, source_topology, target_topology = _topology_matches(source_shape, target_shape)
    if not matches:
        raise RuntimeError(
            "{0} and {1} do not have matching topology. Source vertices: {2}. Target vertices: {3}.".format(
                skin_utils._short_name(source_target["transform"]),
                skin_utils._short_name(target_target["transform"]),
                source_topology.get("vertex_count"),
                target_topology.get("vertex_count"),
            )
        )

    if replace_existing:
        _delete_existing_target_skin(target_shape)

    skin_data = skin_utils._capture_skin_data(source_shape, source_skin)
    report = {
        "skin_cluster": source_skin,
        "skin_data": skin_data,
    }
    new_skin = skin_utils._bind_clean_mesh(target_target["transform"], target_shape, report)
    return new_skin


def _status_payload(state, text):
    return {"state": state, "text": text}


class MayaSkinTransferController(object):
    def __init__(self):
        self.sources = []
        self.targets = []
        self.status_callback = None
        self.last_report = ""

    def shutdown(self):
        pass

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _set_status(self, message, success=True):
        self.last_report = message
        if self.status_callback:
            self.status_callback(message, success)
        if success:
            _debug(message)
        else:
            _warning(message)

    def load_sources_from_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        targets = _mesh_targets_from_selection()
        if not targets:
            self.sources = []
            return False, "Select the skinned source mesh or meshes first."
        self.sources = targets
        message = "Loaded {0}".format(_counted_mesh_list("Sources", self.sources))
        self._set_status(message, True)
        return True, message

    def load_targets_from_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        targets = _mesh_targets_from_selection()
        if not targets:
            self.targets = []
            return False, "Select the target mesh or meshes first."
        self.targets = targets
        message = "Loaded {0}".format(_counted_mesh_list("Targets", self.targets))
        self._set_status(message, True)
        return True, message

    def copy_selected_pair_now(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        targets = _mesh_targets_from_selection()
        if len(targets) < 2:
            return False, "Select the skinned source first, then one or more target meshes."
        self.sources = [targets[0]]
        self.targets = targets[1:]
        return self.copy_loaded()

    def _paired_targets(self):
        if not self.sources:
            raise RuntimeError("Load at least one source mesh first.")
        if not self.targets:
            raise RuntimeError("Load at least one target mesh first.")
        if len(self.sources) == 1:
            return [(self.sources[0], target) for target in self.targets]
        name_pairs, unmatched_sources, unmatched_targets = _name_map_mesh_pairs(self.sources, self.targets)
        if len(name_pairs) == len(self.sources):
            return name_pairs
        if len(self.sources) == len(self.targets):
            return list(zip(self.sources, self.targets))
        raise RuntimeError(
            "Use one source for many targets, matching source/target counts, or name-matched mesh sets. Unmatched sources: {0}. Unmatched targets: {1}.".format(
                _short_list(unmatched_sources) or "none",
                _short_list(unmatched_targets) or "none",
            )
        )

    def copy_loaded(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        try:
            validation = self.validation_summary()
            if validation["source"]["state"] == "bad":
                raise RuntimeError(validation["source"]["text"])
            if validation["target"]["state"] == "bad":
                raise RuntimeError(validation["target"]["text"])
            pairs = self._paired_targets()
            results = []
            cmds.undoInfo(openChunk=True, chunkName="AminateExactSkinTransfer")
            try:
                for source_target, target_target in pairs:
                    new_skin = _copy_exact_skin(source_target, target_target, replace_existing=True)
                    results.append(
                        "{0} -> {1} ({2})".format(
                            skin_utils._short_name(source_target["transform"]),
                            skin_utils._short_name(target_target["transform"]),
                            skin_utils._short_name(new_skin),
                        )
                    )
            finally:
                cmds.undoInfo(closeChunk=True)
            message = "Copied exact skinning for {0} pair(s): {1}".format(len(results), "; ".join(results))
            self._set_status(message, True)
            return True, message
        except Exception as exc:
            message = "Could not copy skinning: {0}".format(exc)
            self._set_status(message, False)
            return False, message

    def validation_summary(self):
        if not MAYA_AVAILABLE:
            return {
                "source": _status_payload("bad", "Maya required."),
                "target": _status_payload("bad", "Maya required."),
            }
        if not self.sources:
            return {
                "source": _status_payload("warn", "Source: pick one or more skinned source meshes."),
                "target": _status_payload("warn", "Target: pick matching target mesh(es)."),
            }
        if not self.targets:
            bad_sources = [
                skin_utils._short_name(source["transform"]) for source in self.sources if not skin_utils._find_skin_cluster(source["shape"])
            ]
            if bad_sources:
                return {
                    "source": _status_payload(
                        "bad",
                        "Source mesh(es) without skinCluster: {0}".format(", ".join(bad_sources)),
                    ),
                    "target": _status_payload("warn", "Target: select a valid skinned target set."),
                }
            source_state = "good"
            source_text = "Source: {0} skinned meshes loaded.".format(len(self.sources))
            return {
                "source": _status_payload(source_state, source_text),
                "target": _status_payload("warn", "Target: pick one or more target meshes."),
            }
        try:
            pairs = self._paired_targets()
        except Exception as exc:
            return {
                "source": _status_payload("bad", str(exc)),
                "target": _status_payload("bad", str(exc)),
            }
        bad_sources = []
        bad_targets = []
        for source_target, target_target in pairs:
            source_skin = skin_utils._find_skin_cluster(source_target["shape"])
            if not source_skin:
                bad_sources.append(skin_utils._short_name(source_target["transform"]))
                continue
            matches, source_topology, target_topology = _topology_matches(source_target["shape"], target_target["shape"])
            if not matches:
                bad_targets.append(
                    "{0} verts {1}, target {2} verts {3}".format(
                        skin_utils._short_name(source_target["transform"]),
                        source_topology.get("vertex_count"),
                        skin_utils._short_name(target_target["transform"]),
                        target_topology.get("vertex_count"),
                    )
                )
        if bad_sources:
            return {
                "source": _status_payload("bad", "Source not skinned: {0}".format(", ".join(bad_sources))),
                "target": _status_payload("warn", "Target: waiting for valid source."),
            }
        if bad_targets:
            return {
                "source": _status_payload("good", "Source: skinned."),
                "target": _status_payload("bad", "Topology mismatch: {0}".format("; ".join(bad_targets))),
            }
        return {
            "source": _status_payload("good", "Source: skinned."),
            "target": _status_payload("good", "Target: topology matches. Ready to copy."),
        }


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

        if MQtUtil.mainWindow() is not None:
            _WindowBase = type("MayaSkinTransferBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
        else:
            _WindowBase = type("MayaSkinTransferBase", (QtWidgets.QDialog,), {})
    except Exception:
        _WindowBase = type("MayaSkinTransferBase", (QtWidgets.QDialog,), {})


    class MayaSkinTransferWindow(_WindowBase):
        def __init__(self, controller, parent=None, show_footer=True):
            super(MayaSkinTransferWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.show_footer = bool(show_footer)
            self.controller.set_status_callback(self._set_status)
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Exact Skin Transfer")
            self.setMinimumSize(420, 240)
            self._build_ui()
            self._sync_lists()

        def _build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.setContentsMargins(12, 12, 12, 12)
            main_layout.setSpacing(10)

            title = QtWidgets.QLabel("Exact Skin Transfer")
            title.setStyleSheet("font-size: 16px; font-weight: 800; color: #F2F2F2;")
            main_layout.addWidget(title)

            help_text = QtWidgets.QLabel(
                "Load one or more skinned source meshes, then one or more target meshes, then click Copy from Loaded Sets."
            )
            help_text.setWordWrap(True)
            main_layout.addWidget(help_text)

            self.copy_selected_button = QtWidgets.QPushButton("Copy From Selection")
            self.copy_selected_button.setMinimumHeight(38)
            self.copy_selected_button.setToolTip("If multiple meshes are selected, first mesh acts as source and the rest as targets.")
            main_layout.addWidget(self.copy_selected_button)

            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            self.source_line = QtWidgets.QLineEdit()
            self.source_line.setReadOnly(True)
            self.target_line = QtWidgets.QLineEdit()
            self.target_line.setReadOnly(True)
            self.source_badge = QtWidgets.QLabel("Source: pick skinned source mesh(es) first.")
            self.target_badge = QtWidgets.QLabel("Target: pick one or more target mesh(es) next.")
            self.load_source_button = QtWidgets.QPushButton("Use Selection As Sources")
            self.load_target_button = QtWidgets.QPushButton("Use Selection As Targets")
            self.copy_loaded_button = QtWidgets.QPushButton("Copy Exact Skinning")
            self.copy_loaded_button.setMinimumHeight(34)
            grid.addWidget(QtWidgets.QLabel("Source"), 0, 0)
            grid.addWidget(self.source_line, 0, 1)
            grid.addWidget(self.load_source_button, 0, 2)
            grid.addWidget(self.source_badge, 1, 1, 1, 2)
            grid.addWidget(QtWidgets.QLabel("Target"), 2, 0)
            grid.addWidget(self.target_line, 2, 1)
            grid.addWidget(self.load_target_button, 2, 2)
            grid.addWidget(self.target_badge, 3, 1, 1, 2)
            grid.addWidget(self.copy_loaded_button, 4, 0, 1, 3)
            main_layout.addLayout(grid)

            note = QtWidgets.QLabel(
                "Topology must match. Supported workflows: 1 source -> many targets, or matching source/target counts in order."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #B8D7FF;")
            main_layout.addWidget(note)

            self.status_label = QtWidgets.QLabel(
                "Ready. Use Load Sources / Load Targets for many-to-many sets, or keep one source and many targets for one-to-many."
            )
            self.status_label.setWordWrap(True)
            main_layout.addWidget(self.status_label)

            if self.show_footer:
                footer = QtWidgets.QHBoxLayout()
                self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
                self.brand_label.setOpenExternalLinks(False)
                self.brand_label.linkActivated.connect(self._open_follow_url)
                self.brand_label.setWordWrap(True)
                footer.addWidget(self.brand_label, 1)
                self.donate_button = QtWidgets.QPushButton("Donate")
                _style_donate_button(self.donate_button)
                self.donate_button.clicked.connect(self._open_donate_url)
                footer.addWidget(self.donate_button)
                main_layout.addLayout(footer)

            self.copy_selected_button.clicked.connect(self._copy_selected_pair_now)
            self.load_source_button.clicked.connect(self._load_sources)
            self.load_target_button.clicked.connect(self._load_targets)
            self.copy_loaded_button.clicked.connect(self._copy_loaded)

        def _sync_lists(self):
            self.source_line.setText(_short_list(self.controller.sources))
            self.target_line.setText(_short_list(self.controller.targets))
            self._sync_badges()

        def _sync_badges(self):
            validation = self.controller.validation_summary()
            self._set_badge(self.source_badge, validation["source"])
            self._set_badge(self.target_badge, validation["target"])

        def _set_badge(self, label, payload):
            colors = {
                "good": ("#103C1D", "#59D987"),
                "bad": ("#4A1515", "#FF7A7A"),
                "warn": ("#463812", "#FFD166"),
            }
            background, foreground = colors.get(payload.get("state"), colors["warn"])
            label.setText(payload.get("text") or "")
            label.setWordWrap(True)
            label.setStyleSheet(
                "QLabel {{ background-color: {0}; color: {1}; border: 1px solid {1}; border-radius: 4px; padding: 4px 6px; font-weight: 700; }}".format(
                    background,
                    foreground,
                )
            )

        def _set_status(self, message, success=True):
            self.status_label.setText(message)
            self._sync_badges()

        def _load_sources(self):
            success, message = self.controller.load_sources_from_selection()
            self._sync_lists()
            self._set_status(message, success)

        def _load_targets(self):
            success, message = self.controller.load_targets_from_selection()
            self._sync_lists()
            self._set_status(message, success)

        def _copy_loaded(self):
            success, message = self.controller.copy_loaded()
            self._sync_lists()
            self._set_status(message, success)

        def _copy_selected_pair_now(self):
            success, message = self.controller.copy_selected_pair_now()
            self._sync_lists()
            self._set_status(message, success)

        def _open_follow_url(self, url=None):
            if _open_external_url(url or FOLLOW_AMIR_URL):
                self._set_status("Opened followamir.com.", True)
            else:
                self._set_status("Could not open followamir.com from this Maya session.", False)

        def _open_donate_url(self):
            if not DONATE_URL:
                self._set_status("Donate link is not set. Use AMIR_PAYPAL_DONATE_URL or AMIR_DONATE_URL.", False)
                return
            if _open_external_url(DONATE_URL):
                self._set_status("Opened donate page.", True)
            else:
                self._set_status("Could not open donate page from this Maya session.", False)


def _close_existing_window():
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.close()
            GLOBAL_WINDOW.deleteLater()
        except Exception:
            pass
    if MAYA_AVAILABLE and cmds and cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True):
        try:
            cmds.deleteUI(WORKSPACE_CONTROL_NAME, control=True)
        except Exception:
            pass
    GLOBAL_WINDOW = None
    GLOBAL_CONTROLLER = None


def launch_maya_skin_transfer(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not MAYA_AVAILABLE or not QtWidgets:
        raise RuntimeError("maya_skin_transfer.launch_maya_skin_transfer() must run inside Autodesk Maya.")
    _close_existing_window()
    GLOBAL_CONTROLLER = MayaSkinTransferController()
    GLOBAL_WINDOW = MayaSkinTransferWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    if dock and hasattr(GLOBAL_WINDOW, "show"):
        try:
            GLOBAL_WINDOW.show(dockable=True, area="right", floating=False)
        except TypeError:
            GLOBAL_WINDOW.show()
    else:
        GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW


__all__ = [
    "MayaSkinTransferController",
    "MayaSkinTransferWindow",
    "launch_maya_skin_transfer",
]
