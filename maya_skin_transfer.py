"""
maya_skin_transfer.py

Transactional adaptive skin transfer for exact and different-topology meshes.
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

TARGET_POLICY_REJECT = "reject"
TARGET_POLICY_REPLACE = "replace"
TARGET_POLICY_PRESERVE = "preserve"
SUPPORTED_TARGET_POLICIES = (TARGET_POLICY_REJECT, TARGET_POLICY_REPLACE, TARGET_POLICY_PRESERVE)


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


def _status_payload(state, text):
    return {"state": state, "text": text}


class AlreadySkinnedTargetError(RuntimeError):
    """Raised when an already-skinned target needs an explicit policy."""


def _normalized_influence_name(node_name):
    name = skin_utils._short_name(node_name or "").lower()
    return re.sub(r"[^a-z0-9]+", "", name.replace("joint", ""))


def _influence_label(node_name):
    values = []
    for attribute in ("side", "type"):
        try:
            if cmds.attributeQuery(attribute, node=node_name, exists=True):
                values.append(str(cmds.getAttr("{0}.{1}".format(node_name, attribute))))
        except Exception:
            pass
    return "|".join(values)


def _target_influence_entries(target_shape, target_skin):
    if not target_skin:
        return []
    data = skin_utils._capture_skin_data(target_shape, target_skin)
    return list(data.get("influences", []))


def _map_influences(source_entries, target_shape, target_skin, auto_add_missing=True):
    """Map source joints to an existing/new target cluster without guessing silently."""
    target_entries = _target_influence_entries(target_shape, target_skin)
    by_uuid = {entry.get("uuid"): entry["path"] for entry in target_entries if entry.get("uuid")}
    by_name = {}
    by_label = {}
    for entry in target_entries:
        by_name.setdefault(_normalized_influence_name(entry.get("path")), entry["path"])
        label = _influence_label(entry.get("path"))
        if label:
            by_label.setdefault(label, entry["path"])

    mapping = {}
    missing = []
    for source_entry in source_entries:
        source_path = source_entry.get("path", "")
        source_uuid = source_entry.get("uuid", "")
        resolved = by_uuid.get(source_uuid)
        if not resolved and source_path and cmds.objExists(source_path):
            source_long = skin_utils._node_long_name(source_path)
            resolved = by_name.get(_normalized_influence_name(source_long))
            if not resolved:
                resolved = by_label.get(_influence_label(source_long))
            if not resolved and target_skin and _normalized_influence_name(source_long):
                # A namespace can differ between body and clothing rigs.  A
                # unique normalized basename is a safe, deterministic match.
                candidates = [
                    entry["path"]
                    for entry in target_entries
                    if _normalized_influence_name(entry.get("path")) == _normalized_influence_name(source_long)
                ]
                if len(candidates) == 1:
                    resolved = candidates[0]
        if not resolved and auto_add_missing and source_path and cmds.objExists(source_path):
            if cmds.nodeType(source_path) not in ("joint", "transform"):
                missing.append("{0} (not a joint/transform)".format(source_path))
                continue
            try:
                cmds.skinCluster(target_skin, edit=True, addInfluence=source_path, lockWeights=False, weight=0.0)
                resolved = skin_utils._node_long_name(source_path)
                target_entries.append({"path": resolved, "uuid": skin_utils._uuid_for_node(resolved)})
                by_uuid[skin_utils._uuid_for_node(resolved)] = resolved
            except Exception as exc:
                missing.append("{0} ({1})".format(source_path, exc))
        if resolved:
            key = source_uuid or source_path
            mapping[key] = resolved
            mapping[source_path] = resolved
    if missing:
        raise RuntimeError("Missing or unsafe influences: {0}".format(", ".join(missing)))
    return mapping


def _skin_settings(skin_data):
    settings = skin_data.get("settings", {})
    return {
        "bindMethod": int(settings.get("bindMethod", 0)),
        "skinMethod": int(settings.get("skinningMethod", 0)),
        "normalizeWeights": int(settings.get("normalizeWeights", 1)),
        "maximumInfluences": int(settings.get("maxInfluences", 5)),
        "obeyMaxInfluences": bool(settings.get("maintainMaxInfluences", False)),
        "weightDistribution": int(settings.get("weightDistribution", 0)),
    }


def _create_target_skin(target_target, source_data):
    influence_paths = [entry["path"] for entry in source_data.get("influences", []) if entry.get("path") and cmds.objExists(entry["path"])]
    if not influence_paths:
        raise RuntimeError("The source has no resolvable influences.")
    settings = _skin_settings(source_data)
    return cmds.skinCluster(
        influence_paths,
        target_target["transform"],
        name=skin_utils._unique_name(skin_utils._short_name(target_target["transform"]) + "_transfer_SKIN"),
        toSelectedBones=True,
        removeUnusedInfluence=False,
        **settings
    )[0]


def _copy_closest_point_skin(source_target, target_target, source_skin, target_skin, source_data):
    mapping = _map_influences(source_data.get("influences", []), target_target["shape"], target_skin, auto_add_missing=True)
    cmds.copySkinWeights(
        sourceSkin=source_skin,
        destinationSkin=target_skin,
        noMirror=True,
        surfaceAssociation="closestPoint",
        influenceAssociation=["name", "label", "closestJoint"],
        normalize=True,
    )
    return mapping


def _capture_transfer_metrics(source_shape, target_shape, source_skin, target_skin, mapping, mode):
    source_data = skin_utils._capture_skin_data(source_shape, source_skin)
    target_data = skin_utils._capture_skin_data(target_shape, target_skin)
    source_keys = [entry.get("uuid") or entry.get("path") for entry in source_data.get("influences", [])]
    mapped_keys = [key for key in source_keys if key in (mapping or {})]
    target_weights_by_key = {
        entry.get("uuid") or entry.get("path"): entry.get("weights", []) for entry in target_data.get("influences", [])
    }
    target_aliases = {
        entry.get("path"): entry.get("uuid") or entry.get("path") for entry in target_data.get("influences", [])
    }
    nonzero_vertices = 0
    sum_error_max = 0.0
    target_vertex_count = int(target_data.get("vertex_count", 0))
    for vertex_index in range(target_vertex_count):
        total = sum(float(weights[vertex_index]) for weights in target_weights_by_key.values() if vertex_index < len(weights))
        if total > skin_utils.VALUE_EPSILON:
            nonzero_vertices += 1
        sum_error_max = max(sum_error_max, abs(total - 1.0))
    max_weight_delta = None
    if int(source_data.get("vertex_count", 0)) == target_vertex_count:
        source_weights = {
            entry.get("uuid") or entry.get("path"): entry.get("weights", []) for entry in source_data.get("influences", [])
        }
        max_weight_delta = 0.0
        for source_key, target_key in (mapping or {}).items():
            target_data_key = target_aliases.get(target_key, target_key)
            if source_key not in source_weights or target_data_key not in target_weights_by_key:
                continue
            for source_value, target_value in zip(source_weights[source_key], target_weights_by_key[target_data_key]):
                max_weight_delta = max(max_weight_delta, abs(float(source_value) - float(target_value)))
    source_count = len(source_keys)
    coverage = float(len(set(mapped_keys))) / float(max(1, source_count))
    vertex_coverage = float(nonzero_vertices) / float(max(1, target_vertex_count))
    return {
        "mode": mode,
        "source_vertex_count": int(source_data.get("vertex_count", 0)),
        "target_vertex_count": target_vertex_count,
        "source_influence_count": source_count,
        "mapped_influence_count": len(set(mapped_keys)),
        "influence_coverage": coverage,
        "target_nonzero_vertex_coverage": vertex_coverage,
        "target_weight_sum_error_max": sum_error_max,
        "max_weight_delta": max_weight_delta,
        "quality_score": max(0.0, min(1.0, coverage * vertex_coverage)),
    }


def _copy_skin_adaptive(source_target, target_target, already_skinned_policy=TARGET_POLICY_REJECT):
    source_shape = source_target["shape"]
    target_shape = target_target["shape"]
    source_skin = skin_utils._find_skin_cluster(source_shape)
    if not source_skin:
        raise RuntimeError("{0} is not skinned.".format(skin_utils._short_name(source_target["transform"])))
    if already_skinned_policy not in SUPPORTED_TARGET_POLICIES:
        raise ValueError("Unknown already-skinned target policy: {0}".format(already_skinned_policy))
    target_skin = skin_utils._find_skin_cluster(target_shape)
    if target_skin and already_skinned_policy == TARGET_POLICY_REJECT:
        raise AlreadySkinnedTargetError(
            "Target {0} is already skinned. Choose an explicit target policy: replace or preserve.".format(
                skin_utils._short_name(target_target["transform"])
            )
        )
    if target_skin and already_skinned_policy == TARGET_POLICY_PRESERVE:
        return target_skin, {"mode": "preserve", "quality_score": 0.0, "already_skinned": True}

    source_data = skin_utils._capture_skin_data(source_shape, source_skin)
    if target_skin and already_skinned_policy == TARGET_POLICY_REPLACE:
        cmds.delete(target_skin)
        target_skin = ""
    matches, source_topology, target_topology = _topology_matches(source_shape, target_shape)
    if matches:
        report = {"skin_cluster": source_skin, "skin_data": source_data}
        target_skin = skin_utils._bind_clean_mesh(target_target["transform"], target_shape, report)
        mapping = {entry.get("uuid") or entry.get("path"): entry.get("path") for entry in source_data.get("influences", [])}
        metrics = _capture_transfer_metrics(source_shape, target_shape, source_skin, target_skin, mapping, "exact")
        return target_skin, metrics

    target_skin = _create_target_skin(target_target, source_data)
    mapping = _copy_closest_point_skin(source_target, target_target, source_skin, target_skin, source_data)
    metrics = _capture_transfer_metrics(source_shape, target_shape, source_skin, target_skin, mapping, "closestPoint")
    metrics["topology_note"] = "Source {0} vertices -> target {1} vertices; closest-point transfer used.".format(
        source_topology.get("vertex_count"), target_topology.get("vertex_count")
    )
    return target_skin, metrics


class MayaSkinTransferController(object):
    def __init__(self):
        self.sources = []
        self.targets = []
        self.status_callback = None
        self.last_report = ""
        self.last_transfer_report = {"pairs": [], "rolled_back": False}
        self.already_skinned_policy = TARGET_POLICY_REJECT

    def shutdown(self):
        pass

    def set_status_callback(self, callback):
        self.status_callback = callback

    def set_already_skinned_policy(self, policy):
        policy = str(policy or "").lower()
        if policy not in SUPPORTED_TARGET_POLICIES:
            raise ValueError("Choose one of: {0}.".format(", ".join(SUPPORTED_TARGET_POLICIES)))
        self.already_skinned_policy = policy
        return policy

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

    def copy_loaded(self, already_skinned_policy=None, replace_existing=None):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        if already_skinned_policy is None and replace_existing is not None:
            already_skinned_policy = TARGET_POLICY_REPLACE if replace_existing else TARGET_POLICY_REJECT
        policy = already_skinned_policy or self.already_skinned_policy
        if policy not in SUPPORTED_TARGET_POLICIES:
            message = "Unknown already-skinned target policy: {0}.".format(policy)
            self._set_status(message, False)
            return False, message
        self.last_transfer_report = {"pairs": [], "rolled_back": False, "already_skinned_policy": policy}
        opened_chunk = False
        mutated = False
        attempted_transfer = False
        try:
            validation = self.validation_summary()
            if validation["source"]["state"] == "bad":
                raise RuntimeError(validation["source"]["text"])
            if validation["target"]["state"] == "bad" and "Topology mismatch" not in validation["target"]["text"]:
                raise RuntimeError(validation["target"]["text"])
            pairs = self._paired_targets()
            results = []
            cmds.undoInfo(openChunk=True, chunkName="AminateAdaptiveSkinTransfer")
            opened_chunk = True
            for source_target, target_target in pairs:
                attempted_transfer = True
                new_skin, metrics = _copy_skin_adaptive(
                    source_target,
                    target_target,
                    already_skinned_policy=policy,
                )
                mutated = mutated or metrics.get("mode") != "preserve"
                self.last_transfer_report["pairs"].append(
                    {
                        "source": source_target["transform"],
                        "target": target_target["transform"],
                        "skin_cluster": new_skin,
                        "metrics": metrics,
                    }
                )
                results.append(
                    "{0} -> {1} ({2}; quality {3:.2f}; {4:.0%} influence coverage)".format(
                        skin_utils._short_name(source_target["transform"]),
                        skin_utils._short_name(target_target["transform"]),
                        skin_utils._short_name(new_skin) if new_skin else "preserved",
                        float(metrics.get("quality_score", 0.0)),
                        float(metrics.get("influence_coverage", 0.0)),
                    )
                )
            cmds.undoInfo(closeChunk=True)
            opened_chunk = False
            message = "Transferred skinning for {0} pair(s): {1}".format(len(results), "; ".join(results))
            self._set_status(message, True)
            return True, message
        except AlreadySkinnedTargetError as exc:
            if opened_chunk:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass
                opened_chunk = False
            if attempted_transfer and mutated:
                try:
                    cmds.undo()
                    self.last_transfer_report["rolled_back"] = True
                except Exception:
                    self.last_transfer_report["rollback_error"] = "Maya could not undo the transfer chunk."
            message = "Skin transfer stopped: {0}".format(exc)
            self._set_status(message, False)
            return False, message
        except Exception as exc:
            if opened_chunk:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass
                opened_chunk = False
            if attempted_transfer:
                try:
                    cmds.undo()
                    self.last_transfer_report["rolled_back"] = True
                except Exception:
                    self.last_transfer_report["rollback_error"] = "Maya could not undo the transfer chunk."
            message = "Could not copy skinning: {0}".format(exc)
            self._set_status(message, False)
            return False, message
        finally:
            if opened_chunk:
                try:
                    cmds.undoInfo(closeChunk=True)
                except Exception:
                    pass

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
                "target": _status_payload(
                    "warn",
                    "Topology mismatch; closest-point transfer is available: {0}".format("; ".join(bad_targets)),
                ),
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
                "Load one or more skinned source meshes, then one or more target meshes. Transfer Skin uses exact vertex order when possible and closest-point transfer for body-to-clothing or different topology."
            )
            help_text.setWordWrap(True)
            main_layout.addWidget(help_text)

            self.copy_selected_button = QtWidgets.QPushButton("Transfer Skin From Selection")
            self.copy_selected_button.setMinimumHeight(38)
            self.copy_selected_button.setMinimumWidth(0)
            self.copy_selected_button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.copy_selected_button.setToolTip("First selected mesh is the source; every later mesh is a target. Different topology uses closest-point transfer.")
            main_layout.addWidget(self.copy_selected_button)

            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            self.source_line = QtWidgets.QLineEdit()
            self.source_line.setReadOnly(True)
            self.source_line.setMinimumWidth(0)
            self.source_line.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.target_line = QtWidgets.QLineEdit()
            self.target_line.setReadOnly(True)
            self.target_line.setMinimumWidth(0)
            self.target_line.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.source_badge = QtWidgets.QLabel("Source: pick skinned source mesh(es) first.")
            self.target_badge = QtWidgets.QLabel("Target: pick one or more target mesh(es) next.")
            self.load_source_button = QtWidgets.QPushButton("Use Selection As Sources")
            self.load_target_button = QtWidgets.QPushButton("Use Selection As Targets")
            self.copy_loaded_button = QtWidgets.QPushButton("Transfer Skin (Auto)")
            self.copy_loaded_button.setMinimumHeight(34)
            for action_button in (self.load_source_button, self.load_target_button, self.copy_loaded_button):
                action_button.setMinimumWidth(0)
                action_button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            grid.addWidget(QtWidgets.QLabel("Source"), 0, 0)
            grid.addWidget(self.source_line, 0, 1)
            grid.addWidget(self.load_source_button, 0, 2)
            grid.addWidget(self.source_badge, 1, 1, 1, 2)
            grid.addWidget(QtWidgets.QLabel("Target"), 2, 0)
            grid.addWidget(self.target_line, 2, 1)
            grid.addWidget(self.load_target_button, 2, 2)
            grid.addWidget(self.target_badge, 3, 1, 1, 2)
            grid.addWidget(self.copy_loaded_button, 4, 0, 1, 3)
            grid.setColumnStretch(1, 1)
            main_layout.addLayout(grid)

            policy_row = QtWidgets.QHBoxLayout()
            policy_row.addWidget(QtWidgets.QLabel("Already-skinned target policy"))
            self.policy_combo = QtWidgets.QComboBox()
            self.policy_combo.addItems([TARGET_POLICY_REJECT, TARGET_POLICY_REPLACE, TARGET_POLICY_PRESERVE])
            self.policy_combo.setToolTip("Reject is safest. Replace is explicit and transactional. Preserve leaves an existing target unchanged.")
            policy_row.addWidget(self.policy_combo, 1)
            main_layout.addLayout(policy_row)

            note = QtWidgets.QLabel(
                "Supported workflows: one source -> many targets, matching source/target counts, or name-matched sets. Exact topology is copied directly; different topology uses closest-point transfer with influence remapping and coverage metrics."
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
            self.policy_combo.currentTextChanged.connect(self.controller.set_already_skinned_policy)

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
            success, message = self.controller.copy_loaded(already_skinned_policy=self.policy_combo.currentText())
            self._sync_lists()
            self._set_status(message, success)

        def _copy_selected_pair_now(self):
            self.controller.set_already_skinned_policy(self.policy_combo.currentText())
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

        def closeEvent(self, event):
            # Maya owns dockable Qt wrappers.  Hide for reuse instead of
            # destroying the wrapper during a native close.
            self.hide()
            event.ignore()


def _close_existing_window():
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.hide()
        except Exception:
            pass


def launch_maya_skin_transfer(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not MAYA_AVAILABLE or not QtWidgets:
        raise RuntimeError("maya_skin_transfer.launch_maya_skin_transfer() must run inside Autodesk Maya.")
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
            GLOBAL_CONTROLLER = None
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
    "TARGET_POLICY_REJECT",
    "TARGET_POLICY_REPLACE",
    "TARGET_POLICY_PRESERVE",
    "AlreadySkinnedTargetError",
    "MayaSkinTransferController",
    "MayaSkinTransferWindow",
    "launch_maya_skin_transfer",
]
