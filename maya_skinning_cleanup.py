"""
maya_skinning_cleanup.py

Non-destructive skinned-mesh transform cleanup for Maya 2022-2026.
"""

from __future__ import absolute_import, division, print_function

import math
import os
import traceback

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaAnim as oma
    import maya.mel as mel
    import maya.OpenMayaUI as omui

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    oma = None
    mel = None
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


WINDOW_OBJECT_NAME = "mayaSkinningCleanupWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL
PREVIEW_SUFFIX = "_skinCleanPreview"
BACKUP_SUFFIX = "_skinBackup"
CHARACTER_COPY_SUFFIX = "_characterSkinCopy"
CHARACTER_SCALE_COMP_SUFFIX = "_scaleComp_GRP"
VALUE_EPSILON = 1.0e-5
# Maya mesh points are stored as single-precision values through a fresh
# skinCluster evaluation.  A 0.0002 scene-unit ceiling is sub-micron at the
# default centimetre scale while still rejecting any visible pose change.
DEFORMATION_EPSILON = 2.0e-4
NORMAL_EPSILON = 1.0e-4

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


class UnsupportedCharacterCase(RuntimeError):
    """A character cannot be copied without weakening the Track A contract."""

    def __init__(self, reasons):
        self.reasons = [str(reason) for reason in (reasons or [])]
        super(UnsupportedCharacterCase, self).__init__("; ".join(self.reasons))


def _debug(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayInfo("[Maya Skinning Cleanup] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayWarning("[Maya Skinning Cleanup] {0}".format(message))


def _qt_flag(scope_name, member_name, fallback=None):
    if not QtCore:
        return fallback
    if hasattr(QtCore.Qt, member_name):
        return getattr(QtCore.Qt, member_name)
    scoped_enum = getattr(QtCore.Qt, scope_name, None)
    if scoped_enum and hasattr(scoped_enum, member_name):
        return getattr(scoped_enum, member_name)
    return fallback


def _style_donate_button(button):
    if not button or not QtWidgets:
        return
    button.setCursor(_qt_flag("CursorShape", "PointingHandCursor", None))
    button.setMinimumHeight(28)
    button.setStyleSheet(
        """
        QPushButton {
            background-color: #FFC439;
            color: #111111;
            border: 1px solid #D9A000;
            border-radius: 6px;
            padding: 4px 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #FFCD57;
        }
        QPushButton:pressed {
            background-color: #F0B932;
        }
        """
    )


def _open_external_url(url):
    if not QtGui:
        return False
    qurl = QtCore.QUrl(url)
    return QtGui.QDesktopServices.openUrl(qurl)


def _maya_main_window():
    if not (MAYA_AVAILABLE and omui and shiboken and QtWidgets):
        return None
    pointer = omui.MQtUtil.mainWindow()
    if pointer is None:
        return None
    return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)


def _dedupe_preserve_order(items):
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _short_name(node_name):
    return node_name.split("|")[-1].split(":")[-1]


def _uuid_for_node(node_name):
    values = cmds.ls(node_name, uuid=True) or []
    return values[0] if values else ""


def _node_long_name(node_name):
    values = cmds.ls(node_name, long=True) or []
    return values[0] if values else node_name


def _unique_name(base_name):
    if not cmds.objExists(base_name):
        return base_name
    index = 1
    while True:
        candidate = "{0}{1}".format(base_name, index)
        if not cmds.objExists(candidate):
            return candidate
        index += 1


def _split_component_member(member):
    base, dot, suffix = member.partition(".")
    long_base = _node_long_name(base)
    return long_base, suffix if dot else ""


def _dag_path(node_name):
    selection = om.MSelectionList()
    selection.add(node_name)
    return selection.getDagPath(0)


def _depend_node(node_name):
    selection = om.MSelectionList()
    selection.add(node_name)
    return selection.getDependNode(0)


def _mesh_fn(node_name):
    return om.MFnMesh(_dag_path(node_name))


def _all_vertex_component(vertex_count):
    component = om.MFnSingleIndexedComponent().create(om.MFn.kMeshVertComponent)
    component_fn = om.MFnSingleIndexedComponent(component)
    component_fn.addElements(list(range(vertex_count)))
    return component


def _vector_tuple(vector):
    return (float(vector.x), float(vector.y), float(vector.z))


def _distance_between_points(point_a, point_b):
    return math.sqrt(
        ((point_a.x - point_b.x) ** 2)
        + ((point_a.y - point_b.y) ** 2)
        + ((point_a.z - point_b.z) ** 2)
    )


def _selected_mesh_target():
    selected = cmds.ls(selection=True, long=True) or []
    if len(selected) != 1:
        return None, "Pick just one skinned mesh for now."

    selected_node = selected[0]
    node_type = cmds.nodeType(selected_node)
    if node_type == "mesh":
        if cmds.getAttr(selected_node + ".intermediateObject"):
            return None, "Pick the visible mesh, not the hidden original shape."
        parent = cmds.listRelatives(selected_node, parent=True, fullPath=True) or []
        if not parent:
            return None, "Could not find the mesh transform."
        return {"transform": parent[0], "shape": selected_node}, ""

    if node_type != "transform":
        return None, "Pick one mesh object."

    shapes = cmds.listRelatives(selected_node, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
    if not shapes:
        return None, "The selected object is not a polygon mesh."
    return {"transform": selected_node, "shape": shapes[0]}, ""


def _find_skin_cluster(source_node):
    if mel:
        try:
            skin_cluster = mel.eval('findRelatedSkinCluster "{0}"'.format(source_node))
            if skin_cluster and cmds.objExists(skin_cluster):
                return skin_cluster
        except Exception:
            pass
    history = cmds.listHistory(source_node, pruneDagObjects=True) or []
    for node_name in history:
        if cmds.nodeType(node_name) == "skinCluster":
            return node_name
    return ""


def _find_base_shape(source_transform, source_shape, skin_cluster):
    shapes = cmds.listRelatives(source_transform, shapes=True, fullPath=True, type="mesh") or []
    for shape in shapes:
        if shape == source_shape:
            continue
        try:
            if not cmds.getAttr(shape + ".intermediateObject"):
                continue
        except Exception:
            continue
        connections = cmds.listConnections(shape + ".outMesh", source=False, destination=True, plugs=True) or []
        for destination in connections:
            if destination.startswith(skin_cluster + ".input[") and destination.endswith(".inputGeometry"):
                return shape
        connections = cmds.listConnections(shape + ".worldMesh[0]", source=False, destination=True, plugs=True) or []
        for destination in connections:
            if destination.startswith(skin_cluster + ".input[") and destination.endswith(".inputGeometry"):
                return shape
        # Imported/older rigs often route the original shape through
        # groupParts/groupId nodes before the skinCluster.  Follow the future
        # history instead of requiring a direct connection.
        try:
            future_history = cmds.listHistory(
                shape,
                future=True,
                allFuture=True,
                pruneDagObjects=True,
            ) or []
        except Exception:
            future_history = []
        if skin_cluster in future_history:
            return shape
    return ""


def _duplicate_visible_mesh_snapshot(source_transform, preview_name):
    clean_transform = cmds.duplicate(source_transform, name=preview_name, rr=True)[0]
    clean_transform = _node_long_name(clean_transform)
    for child in cmds.listRelatives(clean_transform, children=True, fullPath=True) or []:
        if cmds.nodeType(child) == "mesh":
            continue
        try:
            cmds.delete(child)
        except Exception:
            pass
    try:
        cmds.delete(clean_transform, constructionHistory=True)
    except Exception:
        pass
    return _node_long_name(clean_transform)


def _copy_mesh_shape_data(source_shape, target_transform, target_name):
    """Copy the exact mesh data object below ``target_transform``.

    Maya's ``cmds.duplicate(intermediateShape)`` evaluates the visible sibling
    on some imported rigs, which silently bakes the already-deformed pose.
    MFnMesh.copy works on the requested shape data object itself.
    """
    source_object = _dag_path(source_shape).node()
    target_object = _dag_path(target_transform).node()
    new_object = om.MFnMesh().copy(source_object, target_object)
    new_path = om.MDagPath.getAPathTo(new_object).fullPathName()
    try:
        new_path = cmds.rename(new_path, _unique_name(target_name))
    except Exception:
        pass
    return _node_long_name(new_path)


def _replace_duplicate_mesh_with_snapshot(
    source_transform,
    source_shape,
    duplicate_transform,
    base_shape="",
):
    """Replace a shared skinned duplicate shape with an independent snapshot.

    An input-connections-enabled duplicate is useful for preserving animation
    and rig-driver inputs, but Maya may connect both source and duplicate mesh
    shapes to the *same* skinCluster.  Deleting that shared history node would
    destroy the source.  Instead, make a clean evaluated snapshot, replace only
    the duplicate's mesh shape, and bind that independent shape below.
    """
    shading_assignments = _capture_shading_assignments(source_transform, source_shape)
    for duplicate_shape in cmds.listRelatives(
        duplicate_transform,
        shapes=True,
        fullPath=True,
        type="mesh",
    ) or []:
        cmds.delete(duplicate_shape)

    geometry_source = base_shape if base_shape and cmds.objExists(base_shape) else source_shape
    snapshot_shape = _copy_mesh_shape_data(
        geometry_source,
        duplicate_transform,
        _short_name(duplicate_transform) + "_skinSnapshotShape",
    )
    _apply_shading_assignments(duplicate_transform, snapshot_shape, shading_assignments)
    return _node_long_name(snapshot_shape)


def _unsupported_history_nodes(source_shape, skin_cluster):
    unsupported = []
    history = cmds.listHistory(source_shape, pruneDagObjects=True) or []
    ignore_types = {
        "groupId",
        "groupParts",
        "tweak",
        "polyTweak",
        "polyTweakUV",
        "objectSet",
        "dagPose",
    }
    for node_name in history:
        if not cmds.objExists(node_name):
            continue
        node_type = cmds.nodeType(node_name)
        if node_name == skin_cluster:
            continue
        if node_type in ignore_types or node_type.startswith("poly"):
            continue
        inherited = cmds.nodeType(node_name, inherited=True) or []
        if "geometryFilter" in inherited:
            unsupported.append((node_name, node_type))
    return unsupported


def _capture_shading_assignments(source_transform, source_shape):
    shading_engines = _dedupe_preserve_order(cmds.listConnections(source_shape, type="shadingEngine") or [])
    assignments = []
    for shading_engine in shading_engines:
        members = cmds.sets(shading_engine, query=True) or []
        relative_members = []
        for member in members:
            base, suffix = _split_component_member(member)
            if base == source_transform:
                relative_members.append({"target": "transform", "suffix": suffix})
            elif base == source_shape:
                relative_members.append({"target": "shape", "suffix": suffix})
        if relative_members:
            assignments.append({"shading_engine": shading_engine, "members": relative_members})
    return assignments


def _normalized_shading_assignments(assignments):
    normalized = []
    for assignment in assignments:
        members = []
        for member in assignment.get("members", []):
            members.append("{0}:{1}".format(member.get("target", "shape"), member.get("suffix", "")))
        normalized.append((assignment.get("shading_engine", ""), tuple(sorted(members))))
    return sorted(normalized)


def _apply_shading_assignments(target_transform, target_shape, assignments):
    for assignment in assignments:
        shading_engine = assignment.get("shading_engine")
        if not shading_engine or not cmds.objExists(shading_engine):
            continue
        members = []
        for member in assignment.get("members", []):
            base = target_shape if member.get("target") == "shape" else target_transform
            suffix = member.get("suffix", "")
            members.append(base if not suffix else "{0}.{1}".format(base, suffix))
        if members:
            try:
                cmds.sets(members, edit=True, forceElement=shading_engine)
            except Exception:
                pass


def _capture_uv_summary(shape):
    uv_sets = cmds.polyUVSet(shape, query=True, allUVSets=True) or []
    current = cmds.polyUVSet(shape, query=True, currentUVSet=True) or []
    return {
        "names": list(uv_sets),
        "current": current[0] if current else "",
    }


def _capture_color_summary(shape):
    color_sets = cmds.polyColorSet(shape, query=True, allColorSets=True) or []
    current = cmds.polyColorSet(shape, query=True, currentColorSet=True) or []
    return {
        "names": list(color_sets),
        "current": current[0] if current else "",
    }


def _capture_edge_smoothing(shape):
    mesh_fn = _mesh_fn(shape)
    return [bool(mesh_fn.isEdgeSmooth(index)) for index in range(mesh_fn.numEdges)]


def _capture_world_normals(shape):
    dag_path = _dag_path(shape)
    iterator = om.MItMeshFaceVertex(dag_path)
    normals = []
    while not iterator.isDone():
        normal = iterator.getNormal(om.MSpace.kWorld)
        normals.append((iterator.faceId(), iterator.vertexId(), _vector_tuple(normal)))
        iterator.next()
    return normals


def _capture_topology_signature(shape):
    mesh_fn = _mesh_fn(shape)
    counts, indices = mesh_fn.getVertices()
    return {
        "vertex_count": int(mesh_fn.numVertices),
        "face_count": int(mesh_fn.numPolygons),
        "counts": list(counts),
        "indices": list(indices),
    }


def _capture_world_points(shape):
    return _mesh_fn(shape).getPoints(om.MSpace.kWorld)


def _capture_skin_data(source_shape, skin_cluster):
    shape_dag = _dag_path(source_shape)
    mesh_fn = om.MFnMesh(shape_dag)
    component = _all_vertex_component(mesh_fn.numVertices)
    skin_fn = oma.MFnSkinCluster(_depend_node(skin_cluster))

    influence_objects = list(skin_fn.influenceObjects())
    flat_weights, influence_count = skin_fn.getWeights(shape_dag, component)
    influence_count = int(influence_count)
    vertex_count = int(mesh_fn.numVertices)
    if influence_count <= 0:
        raise RuntimeError("Skin cluster {0} has no influences to capture.".format(skin_cluster))
    if influence_count != len(influence_objects):
        raise RuntimeError(
            "Skin influence count mismatch for {0}: influenceObjects returned {1}, "
            "bulk weights returned {2}.".format(
                skin_cluster,
                len(influence_objects),
                influence_count,
            )
        )
    flat_weights = list(flat_weights)
    expected_weight_count = vertex_count * influence_count
    if len(flat_weights) != expected_weight_count:
        raise RuntimeError(
            "Bulk skin weight count mismatch for {0}: expected {1}, got {2}.".format(
                skin_cluster,
                expected_weight_count,
                len(flat_weights),
            )
        )

    influences = []
    for physical_position, influence_dag in enumerate(influence_objects):
        full_path = influence_dag.fullPathName()
        physical_index = int(skin_fn.indexForInfluenceObject(influence_dag))
        # Bulk getWeights returns vertex-major values in the same influence
        # order as influenceObjects().  Splitting that one buffer avoids one
        # full-vertex Maya API call per influence on production characters.
        weights = flat_weights[physical_position::influence_count]
        try:
            raw_bind_pre_matrix = cmds.getAttr("{0}.bindPreMatrix[{1}]".format(skin_cluster, physical_index)) or ()
            if raw_bind_pre_matrix and isinstance(raw_bind_pre_matrix[0], (tuple, list)):
                raw_bind_pre_matrix = raw_bind_pre_matrix[0]
            bind_pre_matrix = tuple(float(value) for value in raw_bind_pre_matrix)
        except Exception:
            bind_pre_matrix = ()
        influences.append(
            {
                "path": full_path,
                "uuid": _uuid_for_node(full_path),
                "physical_index": physical_index,
                "weights": weights,
                "bind_pre_matrix": bind_pre_matrix,
            }
        )
    influences.sort(key=lambda item: item["physical_index"])

    blend_weights = list(skin_fn.getBlendWeights(shape_dag, component))
    settings = {}
    for attribute in (
        "skinningMethod",
        "normalizeWeights",
        "maintainMaxInfluences",
        "maxInfluences",
        "weightDistribution",
        "bindMethod",
        "useComponents",
        "deformUserNormals",
    ):
        if cmds.attributeQuery(attribute, node=skin_cluster, exists=True):
            settings[attribute] = cmds.getAttr("{0}.{1}".format(skin_cluster, attribute))

    return {
        "skin_cluster": skin_cluster,
        "vertex_count": vertex_count,
        "influences": influences,
        "blend_weights": blend_weights,
        "settings": settings,
    }


def _resolve_influences(influence_entries):
    resolved = []
    missing = []
    for entry in influence_entries:
        resolved_name = ""
        uuid_value = entry.get("uuid", "")
        if uuid_value:
            values = cmds.ls(uuid_value, long=True) or []
            if values:
                resolved_name = values[0]
        if not resolved_name and entry.get("path") and cmds.objExists(entry["path"]):
            resolved_name = _node_long_name(entry["path"])
        if not resolved_name:
            missing.append(entry.get("path", "") or uuid_value)
            continue
        resolved.append(
            {
                "path": resolved_name,
                "uuid": _uuid_for_node(resolved_name),
                "weights": list(entry.get("weights", [])),
            }
        )
    return resolved, missing


def _copy_local_transform(source_transform, target_transform):
    world_matrix = cmds.xform(source_transform, query=True, worldSpace=True, matrix=True)
    cmds.xform(target_transform, worldSpace=True, matrix=world_matrix)
    if cmds.attributeQuery("rotateOrder", node=source_transform, exists=True):
        cmds.setAttr(target_transform + ".rotateOrder", cmds.getAttr(source_transform + ".rotateOrder"))
    if cmds.attributeQuery("inheritsTransform", node=source_transform, exists=True):
        cmds.setAttr(target_transform + ".inheritsTransform", cmds.getAttr(source_transform + ".inheritsTransform"))
    for attribute in ("visibility", "template"):
        if cmds.attributeQuery(attribute, node=source_transform, exists=True):
            try:
                cmds.setAttr(target_transform + "." + attribute, cmds.getAttr(source_transform + "." + attribute))
            except Exception:
                pass


def _unlock_transform_channels(transform_name):
    for attribute in ("translate", "rotate", "scale"):
        for axis in ("X", "Y", "Z"):
            plug = "{0}.{1}{2}".format(transform_name, attribute, axis)
            if not cmds.objExists(plug):
                continue
            try:
                cmds.setAttr(plug, lock=False, keyable=True, channelBox=True)
            except Exception:
                pass


def _build_clean_mesh_snapshot(report):
    source_transform = report["source_transform"]
    base_shape = report["base_shape"]
    short_name = _short_name(source_transform)
    preview_name = _unique_name(short_name + PREVIEW_SUFFIX)
    if base_shape and cmds.objExists(base_shape):
        clean_transform = cmds.duplicate(base_shape, name=preview_name, rr=True)[0]
    else:
        clean_transform = _duplicate_visible_mesh_snapshot(source_transform, preview_name)
    parent = cmds.listRelatives(source_transform, parent=True, fullPath=True) or []
    current_parent = cmds.listRelatives(clean_transform, parent=True, fullPath=True) or []
    if parent and current_parent != parent:
        clean_transform = cmds.parent(clean_transform, parent[0])[0]
    clean_transform = _node_long_name(clean_transform)
    _copy_local_transform(source_transform, clean_transform)
    clean_shapes = cmds.listRelatives(clean_transform, shapes=True, fullPath=True, type="mesh") or []
    clean_shape = ""
    for shape in clean_shapes:
        try:
            if cmds.getAttr(shape + ".intermediateObject"):
                continue
        except Exception:
            pass
        clean_shape = shape
        break
    if not clean_shape:
        raise RuntimeError("Could not build a visible clean mesh shape from the original mesh.")
    _unlock_transform_channels(clean_transform)
    cmds.makeIdentity(clean_transform, apply=True, translate=True, rotate=True, scale=True, normal=0)
    if report["uv_summary"].get("current"):
        try:
            cmds.polyUVSet(clean_shape, currentUVSet=True, uvSet=report["uv_summary"]["current"])
        except Exception:
            pass
    _apply_shading_assignments(clean_transform, clean_shape, report["shading_assignments"])
    return clean_transform, clean_shape


def _bind_clean_mesh(clean_transform, clean_shape, report):
    skin_data = report["skin_data"]
    resolved_influences, missing = _resolve_influences(skin_data["influences"])
    if missing:
        raise RuntimeError("Missing influences: {0}".format(", ".join(missing)))
    influence_paths = [entry["path"] for entry in resolved_influences]
    settings = skin_data["settings"]
    cluster_name = _unique_name(_short_name(report["skin_cluster"]) + "_clean")
    new_skin_cluster = cmds.skinCluster(
        influence_paths,
        clean_transform,
        name=cluster_name,
        toSelectedBones=True,
        bindMethod=int(settings.get("bindMethod", 0)),
        skinMethod=int(settings.get("skinningMethod", 0)),
        normalizeWeights=int(settings.get("normalizeWeights", 1)),
        maximumInfluences=int(settings.get("maxInfluences", 5)),
        obeyMaxInfluences=bool(settings.get("maintainMaxInfluences", False)),
        weightDistribution=int(settings.get("weightDistribution", 0)),
        removeUnusedInfluence=False,
    )[0]

    for attribute in ("maintainMaxInfluences", "useComponents", "deformUserNormals"):
        if attribute in settings and cmds.attributeQuery(attribute, node=new_skin_cluster, exists=True):
            try:
                cmds.setAttr("{0}.{1}".format(new_skin_cluster, attribute), settings[attribute])
            except Exception:
                pass

    skin_fn = oma.MFnSkinCluster(_depend_node(new_skin_cluster))
    shape_dag = _dag_path(clean_shape)
    component = _all_vertex_component(report["skin_data"]["vertex_count"])

    influence_order = []
    for influence_dag in skin_fn.influenceObjects():
        physical_index = int(skin_fn.indexForInfluenceObject(influence_dag))
        full_path = influence_dag.fullPathName()
        influence_order.append(
            {
                "path": full_path,
                "uuid": _uuid_for_node(full_path),
                "physical_index": physical_index,
            }
        )
    influence_order.sort(key=lambda item: item["physical_index"])

    source_weight_map = {}
    for entry in resolved_influences:
        key = entry["uuid"] or entry["path"]
        source_weight_map[key] = list(entry["weights"])

    indices = om.MIntArray()
    weights = om.MDoubleArray()
    for entry in influence_order:
        indices.append(entry["physical_index"])
    vertex_count = report["skin_data"]["vertex_count"]
    for vertex_index in range(vertex_count):
        for entry in influence_order:
            key = entry["uuid"] or entry["path"]
            weights.append(float(source_weight_map[key][vertex_index]))

    # Maya prunes weights as they are written when maintainMaxInfluences is
    # enabled.  Real production rigs can have more non-zero influences than
    # the cluster's display maximum (for example, 9 source influences with a
    # maxInfluences value of 5), and their captured sums may intentionally be
    # slightly off 1.0.  Temporarily disable both pruning and normalization
    # while restoring the captured arrays, then restore the source settings
    # after the exact values have landed.
    restore_gates = {}
    for attribute, disabled_value in (("maintainMaxInfluences", False), ("normalizeWeights", 0)):
        if not cmds.attributeQuery(attribute, node=new_skin_cluster, exists=True):
            continue
        try:
            original_value = cmds.getAttr(new_skin_cluster + "." + attribute)
            restore_gates[attribute] = original_value
            if original_value != disabled_value:
                cmds.setAttr(new_skin_cluster + "." + attribute, disabled_value)
        except Exception:
            pass
    try:
        skin_fn.setWeights(shape_dag, component, indices, weights, normalize=False)
        skin_fn.setBlendWeights(shape_dag, component, om.MDoubleArray(report["skin_data"]["blend_weights"]))
    finally:
        for attribute, original_value in restore_gates.items():
            try:
                cmds.setAttr(new_skin_cluster + "." + attribute, original_value)
            except Exception:
                pass
    return new_skin_cluster


def _capture_vector_attribute(node_name, attribute):
    """Read a Maya vector attribute as a flat tuple for stable comparisons."""
    try:
        values = cmds.getAttr("{0}.{1}".format(node_name, attribute))
        if values and isinstance(values[0], (tuple, list)):
            values = values[0]
        return tuple(float(value) for value in (values or ()))
    except Exception:
        return ()


def _capture_bool_attribute(node_name, attribute, default=None):
    try:
        value = cmds.getAttr("{0}.{1}".format(node_name, attribute))
        return bool(value)
    except Exception:
        return default


def _capture_node_state(node_name):
    """Capture only source-owned state that Track A promises not to change."""
    state = {
        "path": _node_long_name(node_name),
        "uuid": _uuid_for_node(node_name),
        "type": cmds.nodeType(node_name),
    }
    try:
        state["world_matrix"] = tuple(float(value) for value in cmds.xform(node_name, query=True, worldSpace=True, matrix=True))
    except Exception:
        state["world_matrix"] = ()
    for attribute in ("translate", "rotate", "scale", "rotatePivot", "scalePivot"):
        try:
            values = cmds.xform(node_name, query=True, objectSpace=True, **{attribute: True})
            state[attribute] = tuple(float(value) for value in values)
        except Exception:
            state[attribute] = _capture_vector_attribute(node_name, attribute)
    if state["type"] == "joint":
        # jointOrient is source-owned state.  It must be compared before and
        # after Track A even when the duplicate uses a compensation group.
        state["jointOrient"] = _capture_vector_attribute(node_name, "jointOrient")
        state["segmentScaleCompensate"] = _capture_bool_attribute(
            node_name,
            "segmentScaleCompensate",
            default=None,
        )
    return state


def _capture_source_integrity(nodes):
    return {
        _uuid_for_node(node_name) or _node_long_name(node_name): _capture_node_state(node_name)
        for node_name in nodes
        if cmds.objExists(node_name)
    }


def _source_integrity_diff(snapshot):
    differences = []
    for key, expected in (snapshot or {}).items():
        candidates = cmds.ls(expected.get("uuid", ""), long=True) or [] if expected.get("uuid") else []
        if not candidates and expected.get("path") and cmds.objExists(expected["path"]):
            candidates = [_node_long_name(expected["path"])]
        if not candidates:
            differences.append("missing source node {0}".format(expected.get("path") or key))
            continue
        actual = _capture_node_state(candidates[0])
        for field in (
            "type",
            "world_matrix",
            "translate",
            "rotate",
            "scale",
            "rotatePivot",
            "scalePivot",
            "jointOrient",
            "segmentScaleCompensate",
        ):
            expected_values = expected.get(field, ())
            actual_values = actual.get(field, ())
            if field == "type":
                if expected_values != actual_values:
                    differences.append("source type changed on {0}".format(expected.get("path") or key))
                continue
            if field == "segmentScaleCompensate":
                if expected_values is not None and actual_values is not None and bool(expected_values) != bool(actual_values):
                    differences.append("source segmentScaleCompensate changed on {0}".format(expected.get("path") or key))
                continue
            if len(expected_values) != len(actual_values) or any(
                abs(float(before) - float(after)) > VALUE_EPSILON for before, after in zip(expected_values, actual_values)
            ):
                differences.append("source {0} changed on {1}".format(field, expected.get("path") or key))
                break
    return differences


def _capture_animation_inputs(node_name, attributes):
    """Return incoming animation/non-animation connections for explicit guards."""
    result = {}
    for attribute in attributes:
        plug = "{0}.{1}".format(node_name, attribute)
        source_plugs = cmds.listConnections(plug, source=True, destination=False, plugs=True) or []
        result[attribute] = list(source_plugs)
    return result


def _animation_sample_times(nodes):
    """Return only the source-authored key times for an animation bake.

    Track A is an export-style correction, not a current-frame snapshot.  The
    source rig may evaluate constraints, utility nodes, or IK handles rather
    than direct animation curves on the joints themselves, so sampling only
    ``keyframe(joint)`` is not sufficient.  The supplied hierarchy/dependency
    nodes are queried together, but no playback endpoints or whole-frame
    samples are invented.  Fractional keys are kept exactly as authored.
    """
    if not MAYA_AVAILABLE or not cmds:
        return []
    try:
        playback_min = float(cmds.playbackOptions(query=True, min=True))
        playback_max = float(cmds.playbackOptions(query=True, max=True))
    except Exception:
        playback_min = playback_max = None
    if playback_min is not None and playback_max is not None and playback_max < playback_min:
        playback_min, playback_max = playback_max, playback_min
    valid_nodes = [node for node in _dedupe_preserve_order(nodes or []) if node and cmds.objExists(node)]
    samples = set()
    if valid_nodes:
        try:
            keyed_times = cmds.keyframe(valid_nodes, query=True, timeChange=True) or []
        except Exception:
            keyed_times = []
        for value in keyed_times:
            try:
                time_value = float(value)
            except (TypeError, ValueError):
                continue
            if playback_min is not None and playback_max is not None and not (playback_min <= time_value <= playback_max):
                continue
            samples.add(time_value)
    return sorted(samples)


def _matrix_to_list(matrix):
    return [float(matrix[index]) for index in range(16)]


def _matrix_max_delta(first, second):
    return max([abs(float(a) - float(b)) for a, b in zip(first or (), second or ())] or [float("inf")])


def _set_keyed_transform(node_name, time_value, attributes):
    for attribute in attributes:
        try:
            cmds.setKeyframe(node_name, attribute=attribute, time=time_value)
        except Exception as exc:
            raise UnsupportedCharacterCase(
                ["Could not key baked transform {0}.{1} at {2}: {3}".format(node_name, attribute, time_value, exc)]
            )


def _bake_joint_animation(source_joints, mapping, compensation, sample_times):
    """Bake evaluated world matrices onto the independent copied skeleton.

    Direct joint drivers (constraints, IK handles, utility nodes, and similar
    rig machinery) are intentionally not copied.  At each sample we read the
    evaluated source world matrix and write a local transform on the copy.  A
    joint that required scale correction is hosted below a plain compensation
    transform; its static jointOrient remains on the joint while the group
    receives the evaluated matrix.  This keeps every copied joint at 1/1/1 and
    avoids replacing a jointOrient-driven pose with raw Euler keys.
    """
    if not sample_times:
        return {"sample_times": [], "sample_count": 0, "keys": 0}
    compensation_by_source = {
        _node_long_name(item.get("source_joint")): item
        for item in (compensation or [])
        if item.get("source_joint")
    }
    ordered_joints = sorted(source_joints or [], key=lambda item: item.count("|"))
    direct_attributes = (
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ",
    )
    group_attributes = direct_attributes + ("shearXY", "shearXZ", "shearYZ")
    # Remove any duplicate-side curves before writing the baked curves.  This
    # also makes a copied source scene deterministic when Maya duplicated a
    # curve despite inputConnections=False.
    for source_joint in ordered_joints:
        duplicate_joint = mapping.get(_node_long_name(source_joint))
        if not duplicate_joint or not cmds.objExists(duplicate_joint):
            raise UnsupportedCharacterCase(["Could not map joint {0} for animation baking.".format(_short_name(source_joint))])
        target = compensation_by_source.get(_node_long_name(source_joint), {}).get("group") or duplicate_joint
        for attribute in group_attributes if target != duplicate_joint else direct_attributes:
            try:
                cmds.cutKey(target, attribute=attribute, clear=True)
            except Exception:
                pass
    original_time = float(cmds.currentTime(query=True))
    key_count = 0
    try:
        for sample_time in sample_times:
            cmds.currentTime(sample_time, edit=True, update=True)
            for source_joint in ordered_joints:
                source_path = _node_long_name(source_joint)
                duplicate_joint = mapping.get(source_path)
                source_world = tuple(float(value) for value in cmds.xform(source_path, query=True, worldSpace=True, matrix=True))
                entry = compensation_by_source.get(source_path)
                if entry:
                    group = entry.get("group") or ""
                    base_matrix = entry.get("joint_local_base_matrix") or ()
                    if not group or len(base_matrix) != 16 or not cmds.objExists(group):
                        raise UnsupportedCharacterCase(["Compensation group for {0} is missing its baked matrix state.".format(_short_name(source_path))])
                    source_matrix = om.MMatrix(source_world)
                    base = om.MMatrix(base_matrix)
                    candidates = (
                        base.inverse() * source_matrix,
                        source_matrix * base.inverse(),
                    )
                    best = None
                    best_delta = float("inf")
                    for candidate in candidates:
                        candidate_values = _matrix_to_list(candidate)
                        cmds.xform(group, worldSpace=True, matrix=candidate_values)
                        actual_joint = cmds.xform(duplicate_joint, query=True, worldSpace=True, matrix=True)
                        delta = _matrix_max_delta(source_world, actual_joint)
                        if delta < best_delta:
                            best_delta = delta
                            best = candidate_values
                    if best is None or best_delta > VALUE_EPSILON:
                        raise UnsupportedCharacterCase(
                            ["Could not preserve evaluated world matrix for compensated joint {0} at {1} (delta {2:.8f}).".format(
                                _short_name(source_path), sample_time, best_delta
                            )]
                        )
                    cmds.xform(group, worldSpace=True, matrix=best)
                    _set_keyed_transform(group, sample_time, group_attributes)
                    entry["keys"] = int(entry.get("keys", 0)) + len(group_attributes)
                    entry["sample_count"] = int(entry.get("sample_count", 0)) + 1
                else:
                    cmds.xform(duplicate_joint, worldSpace=True, matrix=list(source_world))
                    current_scale = tuple(float(value) for value in (cmds.getAttr(duplicate_joint + ".scale") or [(0.0, 0.0, 0.0)])[0])
                    if any(abs(value - 1.0) > VALUE_EPSILON for value in current_scale):
                        raise UnsupportedCharacterCase(
                            ["Joint {0} evaluates with non-unit scale at frame {1}; it was not placed in a compensation group.".format(
                                _short_name(source_path), sample_time
                            )]
                        )
                    _set_keyed_transform(duplicate_joint, sample_time, direct_attributes)
                    key_count += len(direct_attributes)
    finally:
        cmds.currentTime(original_time, edit=True, update=True)
    return {
        "sample_times": [float(value) for value in sample_times],
        "sample_count": len(sample_times),
        "keys": int(key_count + sum(int(item.get("keys", 0)) for item in compensation_by_source.values())),
    }


def _clear_incoming_connections(node_name, attributes):
    for attribute in attributes:
        plug = "{0}.{1}".format(node_name, attribute)
        for source_plug in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
            try:
                cmds.disconnectAttr(source_plug, plug)
            except Exception:
                pass


def _detach_duplicate_joint_trs_drivers(source_joints, mapping):
    """Disconnect copied-joint TRS inputs before evaluated animation baking.

    Maya can retain source constraint outputs on duplicated joints even when
    ``inputConnections=False``.  Track A deliberately creates an independent,
    export-ready baked skeleton, so every copied joint TRS input must be
    detached before any matrix is written.  Failure is fatal rather than
    silently leaving a source-driven copy.
    """
    attributes = (
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ",
    )
    detached = []
    for source_joint in source_joints or []:
        source_path = _node_long_name(source_joint)
        duplicate_joint = mapping.get(source_path)
        if not duplicate_joint or not cmds.objExists(duplicate_joint):
            raise UnsupportedCharacterCase(
                ["Could not map joint {0} before detaching copied rig drivers.".format(_short_name(source_path))]
            )
        for attribute in attributes:
            destination_plug = "{0}.{1}".format(duplicate_joint, attribute)
            incoming = cmds.listConnections(
                destination_plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            for source_plug in incoming:
                try:
                    cmds.disconnectAttr(source_plug, destination_plug)
                except Exception as exc:
                    raise UnsupportedCharacterCase(
                        [
                            "Could not detach copied joint driver {0} -> {1}: {2}".format(
                                source_plug,
                                destination_plug,
                                exc,
                            )
                        ]
                    )
                remaining = cmds.listConnections(
                    destination_plug,
                    source=True,
                    destination=False,
                    plugs=True,
                ) or []
                if source_plug in remaining:
                    raise UnsupportedCharacterCase(
                        ["Copied joint driver remained connected after detach: {0} -> {1}".format(source_plug, destination_plug)]
                    )
                detached.append(
                    {
                        "source_joint": source_path,
                        "duplicate_joint": _node_long_name(duplicate_joint),
                        "source_plug": str(source_plug),
                        "destination_plug": str(destination_plug),
                    }
                )
    return detached


def _incoming_connection_pairs(node_name):
    """Return ``(source_plug, destination_plug)`` pairs for one node."""
    try:
        raw = cmds.listConnections(
            node_name,
            source=True,
            destination=False,
            plugs=True,
            connections=True,
        ) or []
        paired = True
    except TypeError:
        # A small compatibility fallback for older Maya command wrappers.
        raw = cmds.listConnections(
            node_name,
            source=True,
            destination=False,
            plugs=True,
        ) or []
        paired = False
    pairs = []
    if paired:
        for index in range(0, len(raw) - 1, 2):
            first = str(raw[index])
            second = str(raw[index + 1])
            node_path = _node_long_name(node_name)
            first_node = first.split(".", 1)[0]
            if first_node and cmds.objExists(first_node) and _node_long_name(first_node) == node_path:
                destination_plug, source_plug = first, second
            else:
                source_plug, destination_plug = first, second
            pairs.append((source_plug, destination_plug))
    else:
        pairs.extend((str(source_plug), _node_long_name(node_name)) for source_plug in raw)
    return pairs


def _source_dependency_couplings(source_nodes, duplicate_nodes):
    """Recursively report incoming source/dependency couplings into the copy.

    The scan starts at every copied DAG node and follows incoming copied DG
    nodes as well.  A coupling is reported with both source and destination
    plugs rather than silently disconnected: severing a live source driver
    would be just as unsafe as leaving the dependency in place.
    """
    source_paths = {
        _node_long_name(node_name)
        for node_name in (source_nodes or [])
        if node_name and cmds.objExists(node_name)
    }
    duplicate_paths = {
        _node_long_name(node_name)
        for node_name in (duplicate_nodes or [])
        if node_name and cmds.objExists(node_name)
    }
    pending = list(duplicate_paths)
    visited = set()
    couplings = []
    seen_couplings = set()
    while pending:
        duplicate_node = pending.pop(0)
        if not duplicate_node or not cmds.objExists(duplicate_node):
            continue
        duplicate_path = _node_long_name(duplicate_node)
        if duplicate_path in visited:
            continue
        visited.add(duplicate_path)
        for source_plug, destination_plug in _incoming_connection_pairs(duplicate_node):
            source_node = str(source_plug).split(".", 1)[0]
            if not source_node or not cmds.objExists(source_node):
                continue
            # Maya shading sets legitimately share this display-only colour
            # output with every member shape.  It cannot drive transforms,
            # deformation, skin weights, or animation, so it is not a source
            # rig coupling and must not block an otherwise independent copy.
            if (
                cmds.nodeType(source_node) == "shadingEngine"
                and str(source_plug).split(".", 1)[-1] == "memberWireframeColor"
            ):
                continue
            source_path = _node_long_name(source_node)
            if source_path in source_paths:
                key = (duplicate_path, str(source_plug), str(destination_plug))
                if key not in seen_couplings:
                    seen_couplings.add(key)
                    couplings.append(
                        {
                            "copy_node": duplicate_path,
                            "source_plug": str(source_plug),
                            "destination_plug": str(destination_plug),
                        }
                    )
            # Follow only copied nodes.  Do not walk arbitrary external source
            # networks: those are legitimate inputs used while sampling the
            # source, not evidence that the corrected copy retained a coupling.
            if source_path in duplicate_paths and source_path not in visited:
                pending.append(source_node)
    return couplings


def _character_source_dependency_nodes(nodes, skin_reports):
    """Collect source hierarchy, deformer history, and driver node identities."""
    dependencies = {
        _node_long_name(node_name)
        for node_name in (nodes or [])
        if node_name and cmds.objExists(node_name)
    }
    for report in skin_reports or []:
        for candidate in (
            report.get("source_shape"),
            report.get("skin_cluster"),
            report.get("base_shape"),
        ):
            if candidate and cmds.objExists(candidate):
                dependencies.add(_node_long_name(candidate))
        shape = report.get("source_shape")
        if shape and cmds.objExists(shape):
            try:
                dependencies.update(
                    _node_long_name(node_name)
                    for node_name in (cmds.listHistory(shape, pruneDagObjects=True) or [])
                    if node_name and cmds.objExists(node_name)
                )
            except Exception:
                pass
    # Include incoming driver/history nodes recursively so an
    # input-connections-enabled duplicate cannot sneak an animCurve/utility
    # dependency through a copied DG node.
    pending = list(dependencies)
    visited = set()
    while pending:
        node_name = pending.pop(0)
        node_path = _node_long_name(node_name) if node_name and cmds.objExists(node_name) else ""
        if not node_path or node_path in visited:
            continue
        visited.add(node_path)
        try:
            incoming = cmds.listConnections(
                node_name,
                source=True,
                destination=False,
                plugs=False,
            ) or []
        except Exception:
            incoming = []
        for source_node in incoming:
            if not source_node or not cmds.objExists(source_node):
                continue
            # Maya's shared time node drives every copied animation curve; it
            # is scene context, not a source-owned dependency coupling.
            if cmds.nodeType(source_node) == "time":
                continue
            source_path = _node_long_name(source_node)
            if source_path not in dependencies:
                dependencies.add(source_path)
                pending.append(source_path)
    return dependencies


def _character_nodes(root_transform):
    if not root_transform or not cmds.objExists(root_transform):
        return []
    descendants = cmds.listRelatives(root_transform, allDescendents=True, fullPath=True) or []
    return [_node_long_name(root_transform)] + list(reversed(descendants))


def _character_mesh_shapes(nodes):
    meshes = []
    seen_shapes = set()
    for node_name in nodes or []:
        if cmds.nodeType(node_name) != "transform":
            continue
        for shape in cmds.listRelatives(node_name, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []:
            shape = _node_long_name(shape)
            if shape in seen_shapes:
                continue
            seen_shapes.add(shape)
            meshes.append({"transform": _node_long_name(node_name), "shape": shape})
    return meshes


def _character_joints(nodes):
    return [_node_long_name(node_name) for node_name in nodes or [] if cmds.nodeType(node_name) == "joint"]


def _joint_requires_scale_compensation(joint_name, sample_times=None):
    """Return True only when Track A actually needs to rewrite this joint.

    Production rigs commonly contain driven IK/export helper joints whose
    channels must remain connected.  A joint that is already at 1/1/1 needs no
    rewrite, so leaving it alone preserves those connections and keeps Track A
    focused on the bad-scale problem it is designed to solve.
    """
    times = [float(value) for value in (sample_times or [cmds.currentTime(query=True)])]
    original_time = float(cmds.currentTime(query=True))
    try:
        for sample_time in times:
            cmds.currentTime(sample_time, edit=True, update=True)
            try:
                scale = cmds.getAttr(joint_name + ".scale")[0]
            except Exception:
                return True
            if any(abs(float(value) - 1.0) > VALUE_EPSILON for value in scale):
                return True
    finally:
        cmds.currentTime(original_time, edit=True, update=True)
    return False


def _duplicate_node_mapping(source_root, duplicate_root):
    source_nodes = _character_nodes(source_root)
    duplicate_nodes = _character_nodes(duplicate_root)
    if len(source_nodes) != len(duplicate_nodes):
        raise UnsupportedCharacterCase(
            [
                "The duplicate hierarchy has {0} nodes, but the source has {1}; instanced or unsupported DAG content was found.".format(
                    len(duplicate_nodes), len(source_nodes)
                )
            ]
        )
    mapping = {}
    for source_node, duplicate_node in zip(source_nodes, duplicate_nodes):
        if cmds.nodeType(source_node) != cmds.nodeType(duplicate_node):
            raise UnsupportedCharacterCase(
                [
                    "The duplicate hierarchy changed node type for {0} ({1} -> {2}).".format(
                        _short_name(source_node), cmds.nodeType(source_node), cmds.nodeType(duplicate_node)
                    )
                ]
            )
        mapping[_node_long_name(source_node)] = _node_long_name(duplicate_node)
    return mapping


def _bind_skin_data_to_mapped_mesh(target_transform, target_shape, skin_data, influence_map, name_suffix="_character"):
    """Bind copied mesh weights to duplicate influences by UUID/path mapping."""
    target_influences = []
    source_entries = list(skin_data.get("influences", []))
    missing = []
    for entry in source_entries:
        source_key = entry.get("uuid") or entry.get("path")
        target_path = influence_map.get(source_key) or influence_map.get(entry.get("path"))
        if not target_path or not cmds.objExists(target_path):
            missing.append(entry.get("path") or source_key)
            continue
        target_influences.append((source_key, _node_long_name(target_path)))
    if missing:
        raise UnsupportedCharacterCase(
            ["Could not map source influences for {0}: {1}".format(_short_name(target_transform), ", ".join(missing))]
        )
    settings = skin_data.get("settings", {})
    skin_cluster = cmds.skinCluster(
        [target_path for _, target_path in target_influences],
        target_transform,
        name=_unique_name(_short_name(target_transform) + name_suffix + "_SKIN"),
        toSelectedBones=True,
        bindMethod=int(settings.get("bindMethod", 0)),
        skinMethod=int(settings.get("skinningMethod", 0)),
        normalizeWeights=int(settings.get("normalizeWeights", 1)),
        maximumInfluences=int(settings.get("maxInfluences", 5)),
        obeyMaxInfluences=bool(settings.get("maintainMaxInfluences", False)),
        weightDistribution=int(settings.get("weightDistribution", 0)),
        removeUnusedInfluence=False,
    )[0]
    for attribute in ("maintainMaxInfluences", "useComponents", "deformUserNormals"):
        if attribute in settings and cmds.attributeQuery(attribute, node=skin_cluster, exists=True):
            try:
                cmds.setAttr("{0}.{1}".format(skin_cluster, attribute), settings[attribute])
            except Exception:
                pass

    skin_fn = oma.MFnSkinCluster(_depend_node(skin_cluster))
    shape_dag = _dag_path(target_shape)
    vertex_count = int(skin_data.get("vertex_count", 0))
    component = _all_vertex_component(vertex_count)
    target_order = []
    target_entry_by_source_key = {source_key: entry for source_key, entry in zip(
        [key for key, _ in target_influences], source_entries
    )}
    for influence_dag in skin_fn.influenceObjects():
        target_path = influence_dag.fullPathName()
        target_uuid = _uuid_for_node(target_path)
        source_key = None
        for candidate_key, mapped_path in target_influences:
            if mapped_path == target_path or _uuid_for_node(mapped_path) == target_uuid:
                source_key = candidate_key
                break
        if source_key is not None:
            physical_index = int(skin_fn.indexForInfluenceObject(influence_dag))
            target_order.append((physical_index, source_key))
            bind_pre_matrix = target_entry_by_source_key.get(source_key, {}).get("bind_pre_matrix") or ()
            if len(bind_pre_matrix) == 16:
                try:
                    cmds.setAttr(
                        "{0}.bindPreMatrix[{1}]".format(skin_cluster, physical_index),
                        *bind_pre_matrix,
                        type="matrix",
                    )
                except Exception:
                    pass
    target_order.sort(key=lambda item: item[0])
    source_weight_map = {
        entry.get("uuid") or entry.get("path"): list(entry.get("weights", [])) for entry in source_entries
    }
    indices = om.MIntArray()
    weights = om.MDoubleArray()
    for physical_index, _ in target_order:
        indices.append(physical_index)
    for vertex_index in range(vertex_count):
        for _, source_key in target_order:
            weights.append(float(source_weight_map[source_key][vertex_index]))
    skin_fn.setWeights(shape_dag, component, indices, weights, normalize=False)
    blend_weights = list(skin_data.get("blend_weights", []))
    if blend_weights:
        skin_fn.setBlendWeights(shape_dag, component, om.MDoubleArray(blend_weights))
    return skin_cluster


def _character_root_from_selection():
    selected = cmds.ls(selection=True, long=True) or []
    if len(selected) != 1:
        raise UnsupportedCharacterCase(["Select exactly one character root transform for the separate corrected copy."])
    selected_node = selected[0]
    if cmds.nodeType(selected_node) == "mesh":
        parents = cmds.listRelatives(selected_node, parent=True, fullPath=True) or []
        selected_node = parents[0] if parents else ""
    if not selected_node or cmds.nodeType(selected_node) not in ("transform", "joint"):
        raise UnsupportedCharacterCase(["The selected character root must be a transform or joint hierarchy."])
    return _node_long_name(selected_node)


def _character_skin_reports(root_transform):
    nodes = _character_nodes(root_transform)
    meshes = _character_mesh_shapes(nodes)
    reports = []
    for mesh in meshes:
        skin_cluster = _find_skin_cluster(mesh["shape"])
        skin_data = _capture_skin_data(mesh["shape"], skin_cluster) if skin_cluster else None
        reports.append(
            {
                "source_transform": mesh["transform"],
                "source_shape": mesh["shape"],
                "skin_cluster": skin_cluster,
                "base_shape": _find_base_shape(mesh["transform"], mesh["shape"], skin_cluster) if skin_cluster else "",
                "skin_data": skin_data,
                "world_points": _capture_world_points(mesh["shape"]),
                "world_matrix": tuple(float(value) for value in cmds.xform(mesh["transform"], query=True, worldSpace=True, matrix=True)),
                "world_pivot": tuple(float(value) for value in (cmds.xform(mesh["transform"], query=True, worldSpace=True, rotatePivot=True) or ())),
            }
        )
    return nodes, meshes, reports


def _validate_character_copy_source(root_transform, nodes, mesh_reports, sample_times=None):
    reasons = []
    joints = _character_joints(nodes)
    skinned_meshes = [report for report in mesh_reports if report.get("skin_cluster")]
    if not joints:
        reasons.append("No joints were found below the selected character root.")
    if not skinned_meshes:
        reasons.append("No skinned meshes were found below the selected character root.")
    if _referenced_warning(root_transform):
        reasons.append("Referenced character roots are not supported; duplicate the character into an editable scene first.")
    for report in skinned_meshes:
        unsupported = _unsupported_history_nodes(report["source_shape"], report["skin_cluster"])
        if unsupported:
            names = ", ".join("{0} ({1})".format(_short_name(node), node_type) for node, node_type in unsupported)
            reasons.append("Mesh {0} has unsupported live deformation history: {1}.".format(_short_name(report["source_transform"]), names))
        for influence in report["skin_data"].get("influences", []):
            if not influence.get("path") or not cmds.objExists(influence["path"]):
                reasons.append("Mesh {0} has a missing influence {1}.".format(_short_name(report["source_transform"]), influence.get("path") or influence.get("uuid")))
    transform_attributes = (
        "translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ", "jointOrientX", "jointOrientY", "jointOrientZ",
        "segmentScaleCompensate",
    )
    joints_to_compensate = [
        joint for joint in joints
        if _joint_requires_scale_compensation(joint, sample_times=sample_times)
    ]
    for joint in joints:
        incoming = _capture_animation_inputs(joint, transform_attributes)
        for attribute, plugs in incoming.items():
            for source_plug in plugs:
                source_node = source_plug.split(".", 1)[0]
                node_type = cmds.nodeType(source_node) if cmds.objExists(source_node) else "unknown"
                if attribute.startswith("jointOrient"):
                    # jointOrient is part of the static joint basis.  A live
                    # driver would require baking a changing basis rather than
                    # merely baking evaluated TRS, so reject it explicitly.
                    reasons.append(
                        "Joint {0} has animated {1} or another driver; Track A cannot preserve jointOrient animation while normalizing scale.".format(
                            _short_name(joint), attribute
                        )
                    )
                elif attribute == "segmentScaleCompensate":
                    # SSC is a bool policy switch, not a numeric TRS channel.
                    # Do not silently bake only one branch of a changing policy.
                    reasons.append(
                        "Joint {0} has animated or driven segmentScaleCompensate; Track A rejects changing SSC semantics.".format(
                            _short_name(joint)
                        )
                    )
                elif node_type.startswith("animCurve"):
                    # Direct animation and rig-driver curves are sampled from
                    # the evaluated source.  They are intentionally not copied
                    # as source connections to the corrected character.
                    continue
                else:
                    # Constraints, IK handles, utility nodes, and other TRS
                    # drivers are supported by evaluated matrix baking.  Keep
                    # the dependency out of the copy; only non-TRS policies
                    # above remain honest unsupported cases.
                    continue
    if reasons:
        raise UnsupportedCharacterCase(reasons)


def _apply_joint_scale_compensation(source_joints, mapping, created_groups=None):
    compensation = []
    # Reparent deepest joints first so a parent path change never invalidates
    # a child path that is still waiting to be processed.
    source_joints = sorted(source_joints or [], key=lambda item: item.count("|"), reverse=True)
    for source_joint in source_joints:
        duplicate_joint = mapping.get(_node_long_name(source_joint))
        if not duplicate_joint or not cmds.objExists(duplicate_joint):
            raise UnsupportedCharacterCase(["Could not map joint {0} into the copied character.".format(_short_name(source_joint))])
        source_joint_orient = _capture_vector_attribute(source_joint, "jointOrient")
        source_segment_scale_compensate = _capture_bool_attribute(
            source_joint,
            "segmentScaleCompensate",
            default=None,
        )
        source_world_matrix = tuple(
            float(value) for value in cmds.xform(source_joint, query=True, worldSpace=True, matrix=True)
        )
        source_world_rotation = tuple(float(value) for value in (cmds.xform(source_joint, query=True, worldSpace=True, rotation=True) or ()))
        parent = cmds.listRelatives(duplicate_joint, parent=True, fullPath=True) or []
        compensation_name = _unique_name(_short_name(duplicate_joint) + CHARACTER_SCALE_COMP_SUFFIX)
        compensation_group = cmds.createNode("transform", name=compensation_name)
        if parent:
            compensation_group = cmds.parent(compensation_group, parent[0])[0]
        if created_groups is not None:
            created_groups.append(compensation_group)
        try:
            cmds.setAttr(compensation_group + ".rotateOrder", cmds.getAttr(source_joint + ".rotateOrder"))
        except Exception:
            pass

        # Parent while preserving the current duplicate world pose, then clear
        # the duplicate's transform channels.  Keep the source jointOrient on
        # the copied joint; the group absorbs the evaluated transform and the
        # later matrix bake updates that group every sample.
        duplicate_joint = cmds.parent(duplicate_joint, compensation_group, relative=True)[0]
        duplicate_joint = _node_long_name(duplicate_joint)
        mapping[_node_long_name(source_joint)] = duplicate_joint
        _clear_incoming_connections(
            duplicate_joint,
            (
                "translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ",
                "scaleX", "scaleY", "scaleZ",
            ),
        )
        _unlock_transform_channels(duplicate_joint)
        try:
            cmds.setAttr(duplicate_joint + ".translate", 0.0, 0.0, 0.0, type="double3")
            cmds.setAttr(duplicate_joint + ".rotate", 0.0, 0.0, 0.0, type="double3")
            cmds.setAttr(duplicate_joint + ".scale", 1.0, 1.0, 1.0, type="double3")
            if source_segment_scale_compensate is not None and cmds.attributeQuery(
                "segmentScaleCompensate",
                node=duplicate_joint,
                exists=True,
            ):
                # Preserve the source's segment-scale policy explicitly.  A
                # duplicate that silently flips this bool can evaluate the
                # same pose at one frame and drift under parent scaling.
                cmds.setAttr(
                    duplicate_joint + ".segmentScaleCompensate",
                    int(source_segment_scale_compensate),
                )
        except Exception as exc:
            raise UnsupportedCharacterCase(["Could not normalize local scale on joint {0}: {1}".format(_short_name(source_joint), exc)])
        # Capture the exact local basis left by the source jointOrient and
        # rotate/scale pivots.  The bake solves for the group's world matrix as
        # ``inverse(local_basis) * source_world`` (Maya's row-vector order),
        # preserving the static jointOrient instead of replacing it with raw
        # Euler keys on a plain transform.
        joint_local_base_matrix = tuple(
            float(value) for value in cmds.xform(duplicate_joint, query=True, objectSpace=True, matrix=True)
        )
        if len(joint_local_base_matrix) != 16:
            raise UnsupportedCharacterCase(["Could not capture the local jointOrient basis for {0}.".format(_short_name(source_joint))])
        base_matrix = om.MMatrix(joint_local_base_matrix)
        source_matrix = om.MMatrix(source_world_matrix)
        candidates = (
            base_matrix.inverse() * source_matrix,
            source_matrix * base_matrix.inverse(),
        )
        best_group_matrix = None
        best_delta = float("inf")
        for candidate in candidates:
            candidate_values = _matrix_to_list(candidate)
            cmds.xform(compensation_group, worldSpace=True, matrix=candidate_values)
            actual_joint = cmds.xform(duplicate_joint, query=True, worldSpace=True, matrix=True)
            delta = _matrix_max_delta(source_world_matrix, actual_joint)
            if delta < best_delta:
                best_delta = delta
                best_group_matrix = candidate_values
        if best_group_matrix is None or best_delta > VALUE_EPSILON:
            raise UnsupportedCharacterCase(
                ["Could not preserve the initial evaluated world matrix for compensated joint {0} (delta {1:.8f}).".format(
                    _short_name(source_joint), best_delta
                )]
            )
        cmds.xform(compensation_group, worldSpace=True, matrix=best_group_matrix)
        duplicate_joint_orient = _capture_vector_attribute(duplicate_joint, "jointOrient")
        duplicate_segment_scale_compensate = _capture_bool_attribute(
            duplicate_joint,
            "segmentScaleCompensate",
            default=None,
        )
        compensation_group_world_matrix = tuple(
            float(value) for value in cmds.xform(compensation_group, query=True, worldSpace=True, matrix=True)
        )
        compensation_group_world_rotation = tuple(
            float(value)
            for value in (cmds.xform(compensation_group, query=True, worldSpace=True, rotation=True) or ())
        )
        compensation_group_world_matrix_delta = max(
            [
                abs(before - after)
                for before, after in zip(best_group_matrix, compensation_group_world_matrix)
            ]
            or [float("inf")]
        )
        compensation.append(
            {
                "source_joint": source_joint,
                "duplicate_joint": duplicate_joint,
                "group": compensation_group,
                "keys": 0,
                "sample_count": 0,
                "source_joint_orient": source_joint_orient,
                "duplicate_joint_orient": duplicate_joint_orient,
                "duplicate_joint_orient_expected": source_joint_orient,
                "joint_orient_normalized": max(
                    [abs(float(before) - float(after)) for before, after in zip(source_joint_orient, duplicate_joint_orient)]
                    or [float("inf")]
                ) <= VALUE_EPSILON,
                "source_segment_scale_compensate": source_segment_scale_compensate,
                "duplicate_segment_scale_compensate": duplicate_segment_scale_compensate,
                "segment_scale_compensate_ok": (
                    source_segment_scale_compensate is not None
                    and duplicate_segment_scale_compensate is not None
                    and duplicate_segment_scale_compensate == source_segment_scale_compensate
                ),
                "source_world_matrix": source_world_matrix,
                "source_world_rotation": source_world_rotation,
                "compensation_group_world_matrix": compensation_group_world_matrix,
                "compensation_group_world_rotation": compensation_group_world_rotation,
                "joint_local_base_matrix": joint_local_base_matrix,
                "compensation_group_expected_matrix": tuple(float(value) for value in best_group_matrix),
                "compensation_group_world_matrix_delta": compensation_group_world_matrix_delta,
                "compensation_group_pose_preserved": compensation_group_world_matrix_delta <= VALUE_EPSILON,
            }
        )
    return compensation


def _character_copy_result(
    root_transform,
    duplicate_root,
    mapping,
    source_snapshot,
    skin_reports,
    compensation,
    source_couplings=None,
    animation_bake=None,
):
    source_joints = [item for item in mapping if cmds.nodeType(item) == "joint"]
    compensation_by_source = {
        _node_long_name(item.get("source_joint")): item
        for item in (compensation or [])
        if item.get("source_joint")
    }
    joint_checks = []
    for source_joint in source_joints:
        duplicate_joint = mapping[source_joint]
        source_state = source_snapshot.get(_uuid_for_node(source_joint) or source_joint, {})
        source_world = source_state.get("world_matrix", ())
        duplicate_world = tuple(float(value) for value in cmds.xform(duplicate_joint, query=True, worldSpace=True, matrix=True))
        world_delta = max(
            [abs(float(before) - float(after)) for before, after in zip(source_world, duplicate_world)] or [0.0]
        )
        source_translation = tuple(float(value) for value in (cmds.xform(source_joint, query=True, worldSpace=True, translation=True) or ()))
        duplicate_translation = tuple(float(value) for value in (cmds.xform(duplicate_joint, query=True, worldSpace=True, translation=True) or ()))
        source_rotation = tuple(float(value) for value in (cmds.xform(source_joint, query=True, worldSpace=True, rotation=True) or ()))
        duplicate_rotation = tuple(float(value) for value in (cmds.xform(duplicate_joint, query=True, worldSpace=True, rotation=True) or ()))
        translation_delta = max([abs(a - b) for a, b in zip(source_translation, duplicate_translation)] or [0.0])
        rotation_delta = max([abs(a - b) for a, b in zip(source_rotation, duplicate_rotation)] or [0.0])
        scale = tuple(float(value) for value in (cmds.getAttr(duplicate_joint + ".scale") or [(0.0, 0.0, 0.0)])[0])
        source_joint_orient_before = tuple(float(value) for value in (source_state.get("jointOrient") or ()))
        source_joint_orient_after = _capture_vector_attribute(source_joint, "jointOrient")
        duplicate_joint_orient = _capture_vector_attribute(duplicate_joint, "jointOrient")
        source_joint_orient_delta = max(
            [abs(before - after) for before, after in zip(source_joint_orient_before, source_joint_orient_after)]
            or [float("inf") if source_joint_orient_before != source_joint_orient_after else 0.0]
        )
        source_joint_orient_unchanged = (
            bool(source_joint_orient_before)
            and len(source_joint_orient_before) == len(source_joint_orient_after)
            and source_joint_orient_delta <= VALUE_EPSILON
        )
        compensation_entry = compensation_by_source.get(_node_long_name(source_joint))
        compensated = bool(compensation_entry)
        expected_duplicate_joint_orient = (
            tuple(compensation_entry.get("duplicate_joint_orient_expected") or source_joint_orient_before)
            if compensated
            else source_joint_orient_before
        )
        duplicate_joint_orient_delta = max(
            [abs(expected - actual) for expected, actual in zip(expected_duplicate_joint_orient, duplicate_joint_orient)]
            or [float("inf") if expected_duplicate_joint_orient != duplicate_joint_orient else 0.0]
        )
        joint_orient_ok = (
            len(expected_duplicate_joint_orient) == len(duplicate_joint_orient)
            and duplicate_joint_orient_delta <= VALUE_EPSILON
        )
        source_segment_scale_compensate = source_state.get("segmentScaleCompensate")
        duplicate_segment_scale_compensate = _capture_bool_attribute(
            duplicate_joint,
            "segmentScaleCompensate",
            default=None,
        )
        segment_scale_compensate_ok = (
            source_segment_scale_compensate is not None
            and duplicate_segment_scale_compensate is not None
            and duplicate_segment_scale_compensate == bool(source_segment_scale_compensate)
        )
        source_rotate_pivot = tuple(float(value) for value in (source_state.get("rotatePivot") or ()))
        source_scale_pivot = tuple(float(value) for value in (source_state.get("scalePivot") or ()))
        duplicate_rotate_pivot = tuple(
            float(value) for value in (cmds.xform(duplicate_joint, query=True, objectSpace=True, rotatePivot=True) or ())
        )
        duplicate_scale_pivot = tuple(
            float(value) for value in (cmds.xform(duplicate_joint, query=True, objectSpace=True, scalePivot=True) or ())
        )
        rotate_pivot_delta = max(
            [abs(before - after) for before, after in zip(source_rotate_pivot, duplicate_rotate_pivot)]
            or [float("inf") if source_rotate_pivot != duplicate_rotate_pivot else 0.0]
        )
        scale_pivot_delta = max(
            [abs(before - after) for before, after in zip(source_scale_pivot, duplicate_scale_pivot)]
            or [float("inf") if source_scale_pivot != duplicate_scale_pivot else 0.0]
        )
        pivots_ok = (
            len(source_rotate_pivot) == len(duplicate_rotate_pivot)
            and len(source_scale_pivot) == len(duplicate_scale_pivot)
            and rotate_pivot_delta <= VALUE_EPSILON
            and scale_pivot_delta <= VALUE_EPSILON
        )
        compensation_group_pose_preserved = True
        compensation_group_world_matrix_delta = 0.0
        compensation_group_world_rotation_delta = 0.0
        compensation_group = ""
        if compensated:
            compensation_group = compensation_entry.get("group") or ""
            if compensation_group and cmds.objExists(compensation_group):
                group_world_matrix = tuple(
                    float(value) for value in cmds.xform(compensation_group, query=True, worldSpace=True, matrix=True)
                )
                source_group_matrix = tuple(
                    float(value)
                    for value in (compensation_entry.get("compensation_group_expected_matrix") or source_world)
                )
                compensation_group_world_matrix_delta = max(
                    [abs(before - after) for before, after in zip(source_group_matrix, group_world_matrix)]
                    or [float("inf")]
                )
                group_world_rotation = tuple(
                    float(value)
                    for value in (cmds.xform(compensation_group, query=True, worldSpace=True, rotation=True) or ())
                )
                compensation_group_world_rotation_delta = max(
                    [abs(before - after) for before, after in zip(source_rotation, group_world_rotation)]
                    or [float("inf")]
                )
                compensation_group_pose_preserved = compensation_group_world_matrix_delta <= VALUE_EPSILON
            else:
                compensation_group_pose_preserved = False
                compensation_group_world_matrix_delta = float("inf")
            compensation_entry.update(
                {
                    "duplicate_joint": duplicate_joint,
                    "duplicate_joint_orient": duplicate_joint_orient,
                    "joint_orient_normalized": joint_orient_ok,
                    "duplicate_segment_scale_compensate": duplicate_segment_scale_compensate,
                    "segment_scale_compensate_ok": segment_scale_compensate_ok,
                    "compensation_group_world_matrix_delta": compensation_group_world_matrix_delta,
                    "compensation_group_world_rotation_delta": compensation_group_world_rotation_delta,
                    "compensation_group_pose_preserved": compensation_group_pose_preserved,
                }
            )
        joint_checks.append(
            {
                "source": source_joint,
                "copy": duplicate_joint,
                "compensated": compensated,
                "local_scale": scale,
                "scale_ok": all(abs(value - 1.0) <= VALUE_EPSILON for value in scale),
                "source_joint_orient_before": source_joint_orient_before,
                "source_joint_orient_after": source_joint_orient_after,
                "source_joint_orient_delta": source_joint_orient_delta,
                "source_joint_orient_unchanged": source_joint_orient_unchanged,
                "duplicate_joint_orient": duplicate_joint_orient,
                "duplicate_joint_orient_expected": expected_duplicate_joint_orient,
                "duplicate_joint_orient_delta": duplicate_joint_orient_delta,
                "joint_orient_ok": joint_orient_ok,
                "source_segment_scale_compensate": source_segment_scale_compensate,
                "duplicate_segment_scale_compensate": duplicate_segment_scale_compensate,
                "segment_scale_compensate_ok": segment_scale_compensate_ok,
                "source_rotate_pivot": source_rotate_pivot,
                "duplicate_rotate_pivot": duplicate_rotate_pivot,
                "rotate_pivot_delta": rotate_pivot_delta,
                "source_scale_pivot": source_scale_pivot,
                "duplicate_scale_pivot": duplicate_scale_pivot,
                "scale_pivot_delta": scale_pivot_delta,
                "pivots_ok": pivots_ok,
                "compensation_group": compensation_group,
                "compensation_group_world_matrix_delta": compensation_group_world_matrix_delta,
                "compensation_group_world_rotation_delta": compensation_group_world_rotation_delta,
                "compensation_group_pose_preserved": compensation_group_pose_preserved,
                "world_matrix_delta": world_delta,
                "world_translation_delta": translation_delta,
                "world_rotation_delta": rotation_delta,
                # Euler angles can differ by 180/360 degrees while describing
                # the same pose.  The evaluated world matrix is the exact
                # representation needed by skinning and export.
                "world_tr_ok": world_delta <= VALUE_EPSILON,
            }
        )
    mesh_checks = []
    for report in skin_reports:
        duplicate_transform = mapping.get(report["source_transform"])
        duplicate_shapes = cmds.listRelatives(duplicate_transform, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
        duplicate_shape = duplicate_shapes[0] if duplicate_shapes else ""
        source_matrix = report.get("world_matrix", ())
        duplicate_matrix = tuple(float(value) for value in cmds.xform(duplicate_transform, query=True, worldSpace=True, matrix=True)) if duplicate_transform else ()
        matrix_delta = max([abs(a - b) for a, b in zip(source_matrix, duplicate_matrix)] or [float("inf")])
        source_pivot = report.get("world_pivot", ())
        duplicate_pivot = tuple(float(value) for value in (cmds.xform(duplicate_transform, query=True, worldSpace=True, rotatePivot=True) or ())) if duplicate_transform else ()
        pivot_delta = max([abs(a - b) for a, b in zip(source_pivot, duplicate_pivot)] or [float("inf")])
        duplicate_skin = _find_skin_cluster(duplicate_shape) if duplicate_shape else ""
        deformation_delta = float("inf")
        max_weight_delta = 0.0
        weights_ok = not report.get("skin_cluster")
        if duplicate_shape and report.get("skin_cluster") and duplicate_skin:
            deformation_delta = _max_point_delta(report.get("world_points") or (), _capture_world_points(duplicate_shape))
            try:
                source_weights = {
                    entry.get("uuid") or entry.get("path"): entry.get("weights", [])
                    for entry in (report.get("skin_data") or {}).get("influences", [])
                }
                source_to_copy = {
                    entry.get("uuid") or entry.get("path"): mapping.get(entry.get("path"))
                    for entry in (report.get("skin_data") or {}).get("influences", [])
                }
                target_weights = {
                    entry.get("uuid") or entry.get("path"): entry.get("weights", [])
                    for entry in _capture_skin_data(duplicate_shape, duplicate_skin).get("influences", [])
                }
                target_aliases = {
                    entry.get("path"): entry.get("uuid") or entry.get("path")
                    for entry in _capture_skin_data(duplicate_shape, duplicate_skin).get("influences", [])
                }
                missing_weights = False
                for source_key, weights in source_weights.items():
                    target_key = target_aliases.get(source_to_copy.get(source_key), source_to_copy.get(source_key))
                    if target_key not in target_weights:
                        missing_weights = True
                        continue
                    if len(weights) != len(target_weights[target_key]):
                        missing_weights = True
                    for source_value, target_value in zip(weights, target_weights.get(target_key, [])):
                        max_weight_delta = max(max_weight_delta, abs(float(source_value) - float(target_value)))
                weights_ok = not missing_weights and max_weight_delta <= VALUE_EPSILON
            except Exception:
                weights_ok = False
        mesh_checks.append(
            {
                "source": report["source_transform"],
                "copy": duplicate_transform,
                "shape": duplicate_shape,
                "world_matrix_delta": matrix_delta,
                "pivot_delta": pivot_delta,
                "placement_ok": matrix_delta <= VALUE_EPSILON and pivot_delta <= VALUE_EPSILON,
                "skin_cluster": duplicate_skin,
                "deformation_delta": deformation_delta,
                "deformation_ok": deformation_delta <= DEFORMATION_EPSILON if report.get("skin_cluster") else True,
                "max_weight_delta": max_weight_delta,
                "weights_ok": weights_ok,
                "skin_ok": bool(duplicate_skin) and weights_ok if report.get("skin_cluster") else not duplicate_skin,
            }
        )
    source_differences = _source_integrity_diff(source_snapshot)
    source_mesh_differences = []
    for report in skin_reports:
        if not cmds.objExists(report["source_shape"]):
            source_mesh_differences.append("missing source mesh {0}".format(_short_name(report["source_transform"])))
            continue
        source_point_delta = _max_point_delta(report.get("world_points") or (), _capture_world_points(report["source_shape"]))
        if source_point_delta > VALUE_EPSILON:
            source_mesh_differences.append(
                "source mesh {0} world points changed (delta {1:.8f})".format(_short_name(report["source_transform"]), source_point_delta)
            )
        if report.get("skin_cluster"):
            current_skin = _find_skin_cluster(report["source_shape"])
            if not current_skin:
                source_mesh_differences.append("source mesh {0} lost its skinCluster".format(_short_name(report["source_transform"])))
            else:
                original_weights = {
                    entry.get("uuid") or entry.get("path"): entry.get("weights", [])
                    for entry in (report.get("skin_data") or {}).get("influences", [])
                }
                current_weights = {
                    entry.get("uuid") or entry.get("path"): entry.get("weights", [])
                    for entry in _capture_skin_data(report["source_shape"], current_skin).get("influences", [])
                }
                for source_key, original_values in original_weights.items():
                    current_values = current_weights.get(source_key)
                    if current_values is None or len(current_values) != len(original_values):
                        source_mesh_differences.append("source mesh {0} skin weights changed".format(_short_name(report["source_transform"])))
                        break
                    if any(abs(float(before) - float(after)) > VALUE_EPSILON for before, after in zip(original_values, current_values)):
                        source_mesh_differences.append("source mesh {0} skin weights changed".format(_short_name(report["source_transform"])))
                        break
    source_differences.extend(source_mesh_differences)
    animation_keys_copied = int(
        (animation_bake or {}).get("keys", sum(int(item.get("keys", 0)) for item in compensation))
    )
    source_couplings = list(source_couplings or [])
    source_joint_orient_unchanged = bool(joint_checks) and all(
        item.get("source_joint_orient_unchanged") for item in joint_checks
    )
    segment_scale_compensate_validated = bool(joint_checks) and all(
        item.get("segment_scale_compensate_ok") for item in joint_checks
    )
    joint_pivots_preserved = bool(joint_checks) and all(item.get("pivots_ok") for item in joint_checks)
    compensation_pose_preserved = bool(joint_checks) and all(
        item.get("compensation_group_pose_preserved") for item in joint_checks
    )
    return {
        "root": root_transform,
        "copy_root": duplicate_root,
        "mapping": mapping,
        "source_untouched": not source_differences,
        "source_differences": source_differences,
        "source_joint_orient_unchanged": source_joint_orient_unchanged,
        "segment_scale_compensate_validated": segment_scale_compensate_validated,
        "joint_pivots_preserved": joint_pivots_preserved,
        "compensation_pose_preserved": compensation_pose_preserved,
        "source_couplings": source_couplings,
        "joint_checks": joint_checks,
        "mesh_checks": mesh_checks,
        "compensation_groups": compensation,
        "animation_keys_copied": animation_keys_copied,
        "animation_bake": dict(animation_bake or {}),
        "animation_sample_times": list((animation_bake or {}).get("sample_times") or []),
        "animation_preserved": bool(
            not source_couplings
            and all(item.get("keys", 0) >= 0 for item in compensation)
        ),
        "verified": bool(
            not source_differences
            and not source_couplings
            and bool(all(item.get("keys", 0) >= 0 for item in compensation))
            and joint_checks
            and source_joint_orient_unchanged
            and segment_scale_compensate_validated
            and joint_pivots_preserved
            and compensation_pose_preserved
            and all(
                item["scale_ok"]
                and item["world_tr_ok"]
                and item["joint_orient_ok"]
                and item["segment_scale_compensate_ok"]
                and item["pivots_ok"]
                and item["compensation_group_pose_preserved"]
                for item in joint_checks
            )
            and mesh_checks
            and all(
                item.get("copy")
                and item["placement_ok"]
                and item["skin_ok"]
                and item["deformation_ok"]
                and item["weights_ok"]
                for item in mesh_checks
            )
        ),
    }


def _character_copy_failure_reasons(result):
    reasons = list(result.get("source_differences") or [])
    if result.get("source_couplings"):
        reasons.append(
            "Copied character has incoming source dependencies: {0}.".format(
                ", ".join(
                    "{0} {1} <- {2}".format(
                        _short_name(item.get("copy_node")),
                        item.get("destination_plug", ""),
                        item.get("source_plug", ""),
                    )
                    for item in result.get("source_couplings")[:12]
                )
            )
        )
    for check in result.get("joint_checks") or []:
        if not check.get("scale_ok"):
            reasons.append(
                "Copied joint {0} scale is {1}, not 1/1/1.".format(
                    _short_name(check.get("copy")),
                    tuple(round(float(value), 8) for value in (check.get("local_scale") or ())),
                )
            )
        if not check.get("world_tr_ok"):
            reasons.append(
                "Copied joint {0} moved (world-matrix delta {1:.8f}, translation delta {2:.8f}, Euler delta {3:.8f}).".format(
                    _short_name(check.get("copy")),
                    float(check.get("world_matrix_delta", float("inf"))),
                    float(check.get("world_translation_delta", float("inf"))),
                    float(check.get("world_rotation_delta", float("inf"))),
                )
            )
        if not check.get("source_joint_orient_unchanged"):
            reasons.append(
                "Source joint {0} jointOrient changed (delta {1:.8f}).".format(
                    _short_name(check.get("source")),
                    float(check.get("source_joint_orient_delta", float("inf"))),
                )
            )
        if not check.get("joint_orient_ok"):
            reasons.append(
                "Copied joint {0} jointOrient is {1}, expected {2}.".format(
                    _short_name(check.get("copy")),
                    tuple(round(float(value), 8) for value in (check.get("duplicate_joint_orient") or ())),
                    tuple(round(float(value), 8) for value in (check.get("duplicate_joint_orient_expected") or ())),
                )
            )
        if not check.get("segment_scale_compensate_ok"):
            reasons.append(
                "Copied joint {0} segmentScaleCompensate differs from source ({1} -> {2}).".format(
                    _short_name(check.get("copy")),
                    check.get("source_segment_scale_compensate"),
                    check.get("duplicate_segment_scale_compensate"),
                )
            )
        if not check.get("pivots_ok"):
            reasons.append(
                "Copied joint {0} rotate/scale pivots changed (rotate delta {1:.8f}, scale delta {2:.8f}).".format(
                    _short_name(check.get("copy")),
                    float(check.get("rotate_pivot_delta", float("inf"))),
                    float(check.get("scale_pivot_delta", float("inf"))),
                )
            )
        if not check.get("compensation_group_pose_preserved"):
            reasons.append(
                "Compensation group {0} does not preserve source world pose (matrix delta {1:.8f}).".format(
                    _short_name(check.get("compensation_group")),
                    float(check.get("compensation_group_world_matrix_delta", float("inf"))),
                )
            )
    for check in result.get("mesh_checks") or []:
        if not check.get("placement_ok"):
            reasons.append(
                "Copied mesh {0} placement changed (matrix delta {1:.8f}, pivot delta {2:.8f}).".format(
                    _short_name(check.get("copy")),
                    float(check.get("world_matrix_delta", float("inf"))),
                    float(check.get("pivot_delta", float("inf"))),
                )
            )
        if not check.get("skin_ok"):
            reasons.append(
                "Copied mesh {0} skin verification failed (cluster={1}, weights_ok={2}).".format(
                    _short_name(check.get("copy")),
                    check.get("skin_cluster") or "missing",
                    bool(check.get("weights_ok")),
                )
            )
        if not check.get("deformation_ok"):
            reasons.append(
                "Copied mesh {0} deformation changed (point delta {1:.8f}).".format(
                    _short_name(check.get("copy")),
                    float(check.get("deformation_delta", float("inf"))),
                )
            )
    return reasons or [
        "The copied character failed the world-transform, joint-scale, placement, or skin verification checks."
    ]


def create_whole_character_copy(root_transform=None):
    """Create a separate corrected character copy (Track A).

    The source hierarchy is never renamed, frozen, rebound, or deleted. Any
    failure removes the duplicate hierarchy and returns an explicit report.
    """
    if not MAYA_AVAILABLE:
        return False, "Track A requires a live Maya scene.", {"unsupported": ["Maya is not available."]}
    duplicate_root = ""
    compensation = []
    created_groups = []
    opened_chunk = False
    try:
        root_transform = _node_long_name(root_transform or _character_root_from_selection())
        nodes, meshes, skin_reports = _character_skin_reports(root_transform)
        source_dependency_nodes = _character_source_dependency_nodes(nodes, skin_reports)
        animation_sample_times = _animation_sample_times(list(nodes) + list(source_dependency_nodes))
        _validate_character_copy_source(root_transform, nodes, skin_reports, sample_times=animation_sample_times)
        source_snapshot = _capture_source_integrity(nodes)
        source_joints = _character_joints(nodes)
        source_joints_to_compensate = [
            joint for joint in source_joints
            if _joint_requires_scale_compensation(joint, sample_times=animation_sample_times)
        ]
        cmds.undoInfo(openChunk=True, chunkName="AminateCreateWholeCharacterSkinCopy")
        opened_chunk = True
        # Keep the copied hierarchy independent.  In particular, do not ask
        # Maya to preserve external input connections: that can wire duplicate
        # joints/shapes back to source animation/deformer nodes and make a
        # "safe" copy lie.
        duplicate_root = cmds.duplicate(
            root_transform,
            rr=True,
            rc=True,
            inputConnections=False,
            name=_unique_name(_short_name(root_transform) + CHARACTER_COPY_SUFFIX),
        )[0]
        duplicate_root = _node_long_name(duplicate_root)
        mapping = _duplicate_node_mapping(root_transform, duplicate_root)
        detached_joint_drivers = _detach_duplicate_joint_trs_drivers(
            source_joints,
            mapping,
        )
        source_couplings = _source_dependency_couplings(
            source_dependency_nodes,
            _character_nodes(duplicate_root),
        )
        if source_couplings:
            raise UnsupportedCharacterCase(
                [
                    "The copied character has incoming connections from its source hierarchy: {0}.".format(
                        ", ".join(
                            "{0} <- {1}".format(
                                _short_name(item.get("copy_node")),
                                item.get("source_plug", ""),
                            )
                            for item in source_couplings[:12]
                        )
                    )
                ]
            )
        mapping_uuids = {source_node: _uuid_for_node(duplicate_node) for source_node, duplicate_node in mapping.items()}
        compensation = _apply_joint_scale_compensation(
            source_joints_to_compensate,
            mapping,
            created_groups=created_groups,
        )
        for source_node, duplicate_uuid in mapping_uuids.items():
            duplicate_candidates = cmds.ls(duplicate_uuid, long=True) if duplicate_uuid else []
            if duplicate_candidates:
                mapping[source_node] = _node_long_name(duplicate_candidates[0])
        animation_bake = _bake_joint_animation(
            source_joints,
            mapping,
            compensation,
            animation_sample_times,
        )
        animation_bake["detached_driver_count"] = len(detached_joint_drivers)
        animation_bake["detached_driver_sample"] = detached_joint_drivers[:50]
        animation_bake["detached_driver_sample_truncated"] = len(detached_joint_drivers) > 50

        source_to_copy_influence = {}
        for source_joint in source_joints:
            duplicate_joint = mapping.get(source_joint)
            if duplicate_joint:
                source_to_copy_influence[source_joint] = duplicate_joint
                source_to_copy_influence[_uuid_for_node(source_joint)] = duplicate_joint
                source_to_copy_influence[_short_name(source_joint)] = duplicate_joint
        for report in skin_reports:
            duplicate_transform = mapping.get(report["source_transform"])
            if report.get("skin_cluster"):
                duplicate_shape = _replace_duplicate_mesh_with_snapshot(
                    report["source_transform"],
                    report["source_shape"],
                    duplicate_transform,
                    report.get("base_shape") or "",
                )
                _bind_skin_data_to_mapped_mesh(
                    duplicate_transform,
                    duplicate_shape,
                    report["skin_data"],
                    source_to_copy_influence,
                    name_suffix="_character",
                )
            else:
                duplicate_shapes = cmds.listRelatives(
                    duplicate_transform,
                    shapes=True,
                    noIntermediate=True,
                    fullPath=True,
                    type="mesh",
                ) or []
                if not duplicate_shapes:
                    raise UnsupportedCharacterCase(
                        ["The copied mesh for {0} has no visible shape.".format(_short_name(report["source_transform"]))]
                    )

        copy_root = duplicate_root
        root_compensation = next(
            (
                item for item in compensation
                if _node_long_name(item.get("source_joint") or "") == _node_long_name(root_transform)
            ),
            None,
        )
        if root_compensation and root_compensation.get("group") and cmds.objExists(root_compensation["group"]):
            # The old duplicate-root path becomes stale when a selected root
            # joint is reparented under its compensation group.
            copy_root = _node_long_name(root_compensation["group"])
            duplicate_root = copy_root
        else:
            copy_parents = cmds.listRelatives(duplicate_root, parent=True, fullPath=True) or []
            if copy_parents and _node_long_name(copy_parents[0]) in {_node_long_name(group) for group in created_groups}:
                copy_root = _node_long_name(copy_parents[0])
        source_couplings = _source_dependency_couplings(
            source_dependency_nodes,
            _character_nodes(copy_root),
        )
        result = _character_copy_result(
            root_transform,
            copy_root,
            mapping,
            source_snapshot,
            skin_reports,
            compensation,
            source_couplings=source_couplings,
            animation_bake=animation_bake,
        )
        if not result["verified"]:
            raise UnsupportedCharacterCase(_character_copy_failure_reasons(result))
        cmds.undoInfo(closeChunk=True)
        opened_chunk = False
        return True, "Created a separate corrected whole-character copy with normalized joint scales.", result
    except UnsupportedCharacterCase as exc:
        for item in reversed(compensation + [{"group": group} for group in created_groups if group not in [entry.get("group") for entry in compensation]]):
            group = item.get("group") if isinstance(item, dict) else item
            if group and cmds.objExists(group):
                try:
                    cmds.delete(group)
                except Exception:
                    pass
        if duplicate_root and cmds.objExists(duplicate_root):
            try:
                cmds.delete(duplicate_root)
            except Exception:
                pass
        if opened_chunk:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        report = {"verified": False, "copy_root": "", "unsupported": list(exc.reasons), "rolled_back": True}
        return False, "Track A is unsupported for this character: {0}".format("; ".join(exc.reasons)), report
    except Exception as exc:
        for item in reversed(compensation + [{"group": group} for group in created_groups if group not in [entry.get("group") for entry in compensation]]):
            group = item.get("group") if isinstance(item, dict) else item
            if group and cmds.objExists(group):
                try:
                    cmds.delete(group)
                except Exception:
                    pass
        if duplicate_root and cmds.objExists(duplicate_root):
            try:
                cmds.delete(duplicate_root)
            except Exception:
                pass
        if opened_chunk:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass
        _warning(traceback.format_exc())
        return False, "Track A rolled back because the copied character failed: {0}".format(exc), {"verified": False, "rolled_back": True, "unsupported": [str(exc)]}


# Friendly aliases keep the Track A action discoverable for integrations that
# call it "character copy" rather than "whole character copy".
create_character_copy = create_whole_character_copy


def _max_point_delta(source_points, target_points):
    max_delta = 0.0
    if len(source_points) != len(target_points):
        return float("inf")
    for index in range(len(source_points)):
        max_delta = max(max_delta, _distance_between_points(source_points[index], target_points[index]))
    return max_delta


def _max_normal_delta(source_normals, target_normals):
    if len(source_normals) != len(target_normals):
        return float("inf")
    max_delta = 0.0
    for source_item, target_item in zip(source_normals, target_normals):
        if source_item[0] != target_item[0] or source_item[1] != target_item[1]:
            return float("inf")
        source_vector = source_item[2]
        target_vector = target_item[2]
        max_delta = max(
            max_delta,
            math.sqrt(
                ((source_vector[0] - target_vector[0]) ** 2)
                + ((source_vector[1] - target_vector[1]) ** 2)
                + ((source_vector[2] - target_vector[2]) ** 2)
            ),
        )
    return max_delta


def _verify_cleanup(report, clean_transform, clean_shape, new_skin_cluster):
    checks = []

    def add_check(label, passed, details):
        checks.append({"label": label, "passed": bool(passed), "details": details})

    clean_signature = _capture_topology_signature(clean_shape)
    source_signature = report["topology_signature"]
    topology_ok = (
        clean_signature["vertex_count"] == source_signature["vertex_count"]
        and clean_signature["face_count"] == source_signature["face_count"]
        and clean_signature["counts"] == source_signature["counts"]
        and clean_signature["indices"] == source_signature["indices"]
    )
    add_check("Topology + vertex order", topology_ok, "{0} verts, {1} faces".format(clean_signature["vertex_count"], clean_signature["face_count"]))

    translate = cmds.getAttr(clean_transform + ".translate")[0]
    translate_ok = all(abs(value) <= VALUE_EPSILON for value in translate)
    add_check(
        "Translate is 0,0,0",
        translate_ok,
        "translate = {0:.6f}, {1:.6f}, {2:.6f}".format(translate[0], translate[1], translate[2]),
    )

    rotate = cmds.getAttr(clean_transform + ".rotate")[0]
    rotate_ok = all(abs(value) <= VALUE_EPSILON for value in rotate)
    add_check(
        "Rotate is 0,0,0",
        rotate_ok,
        "rotate = {0:.6f}, {1:.6f}, {2:.6f}".format(rotate[0], rotate[1], rotate[2]),
    )

    scale = cmds.getAttr(clean_transform + ".scale")[0]
    scale_ok = all(abs(value - 1.0) <= VALUE_EPSILON for value in scale)
    add_check(
        "Scale is 1,1,1",
        scale_ok,
        "scale = {0:.6f}, {1:.6f}, {2:.6f}".format(scale[0], scale[1], scale[2]),
    )

    source_points = _capture_world_points(report["source_shape"])
    clean_points = _capture_world_points(clean_shape)
    point_delta = _max_point_delta(source_points, clean_points)
    add_check("Viewport shape match", point_delta <= VALUE_EPSILON, "max point delta = {0:.8f}".format(point_delta))

    clean_skin_data = _capture_skin_data(clean_shape, new_skin_cluster)
    source_weight_map = {}
    for entry in report["skin_data"]["influences"]:
        key = entry["uuid"] or entry["path"]
        source_weight_map[key] = entry["weights"]
    max_weight_delta = 0.0
    influence_mismatch = []
    for entry in clean_skin_data["influences"]:
        key = entry["uuid"] or entry["path"]
        if key not in source_weight_map:
            influence_mismatch.append(entry["path"])
            continue
        source_weights = source_weight_map[key]
        for source_value, clean_value in zip(source_weights, entry["weights"]):
            max_weight_delta = max(max_weight_delta, abs(source_value - clean_value))
    weights_ok = not influence_mismatch and max_weight_delta <= VALUE_EPSILON
    add_check("Skin weights match by vertex", weights_ok, "max weight delta = {0:.8f}".format(max_weight_delta))

    source_blend = report["skin_data"]["blend_weights"]
    clean_blend = clean_skin_data["blend_weights"]
    max_blend_delta = 0.0
    for source_value, clean_value in zip(source_blend, clean_blend):
        max_blend_delta = max(max_blend_delta, abs(source_value - clean_value))
    add_check("Skin blend weights match", max_blend_delta <= VALUE_EPSILON, "max blend delta = {0:.8f}".format(max_blend_delta))

    source_shading = _normalized_shading_assignments(report["shading_assignments"])
    clean_shading = _normalized_shading_assignments(_capture_shading_assignments(clean_transform, clean_shape))
    add_check("Materials + face assignments", source_shading == clean_shading, "{0} shading groups".format(len(clean_shading)))

    clean_uv_summary = _capture_uv_summary(clean_shape)
    uv_ok = (
        clean_uv_summary["names"] == report["uv_summary"]["names"]
        and clean_uv_summary["current"] == report["uv_summary"]["current"]
    )
    add_check("UV sets", uv_ok, "sets = {0}".format(", ".join(clean_uv_summary["names"]) or "none"))

    clean_color_summary = _capture_color_summary(clean_shape)
    color_ok = (
        clean_color_summary["names"] == report["color_summary"]["names"]
        and clean_color_summary["current"] == report["color_summary"]["current"]
    )
    add_check("Color sets", color_ok, "sets = {0}".format(", ".join(clean_color_summary["names"]) or "none"))

    source_edges = report["edge_smoothing"]
    clean_edges = _capture_edge_smoothing(clean_shape)
    add_check("Hard/soft edges", source_edges == clean_edges, "{0} edges checked".format(len(clean_edges)))

    source_normals = report["world_normals"]
    clean_normals = _capture_world_normals(clean_shape)
    normal_delta = _max_normal_delta(source_normals, clean_normals)
    add_check("Viewport normals", normal_delta <= NORMAL_EPSILON, "max normal delta = {0:.8f}".format(normal_delta))

    passed = all(item["passed"] for item in checks)
    return {"passed": passed, "checks": checks}


def _format_report(report):
    if not report:
        return "Pick one skinned mesh, then click Replace Mesh With Frozen Transform Mesh."

    lines = [
        "Mesh: {0}".format(_short_name(report["source_transform"])),
        "Skin Cluster: {0}".format(_short_name(report["skin_cluster"]) if report["skin_cluster"] else "None"),
        "Base Shape: {0}".format(_short_name(report["base_shape"]) if report["base_shape"] else "Visible mesh fallback"),
        "Influences: {0}".format(len(report["skin_data"]["influences"]) if report.get("skin_data") else 0),
        "",
        "Checks:",
    ]

    if report["errors"]:
        for item in report["errors"]:
            lines.append("RED - {0}".format(item))
    if report["warnings"]:
        for item in report["warnings"]:
            lines.append("YELLOW - {0}".format(item))
    if not report["errors"] and not report["warnings"]:
        lines.append("GREEN - This mesh is ready for a clean copy.")

    if report.get("result"):
        lines.append("")
        lines.append("Frozen Copy:")
        lines.append("Preview: {0}".format(_short_name(report["result"]["clean_transform"])))
        for check in report["result"]["verification"]["checks"]:
            prefix = "GREEN" if check["passed"] else "RED"
            lines.append("{0} - {1}: {2}".format(prefix, check["label"], check["details"]))

    return "\n".join(lines)


def _referenced_warning(node_name):
    try:
        if cmds.referenceQuery(node_name, isNodeReferenced=True):
            return True
    except Exception:
        return False
    return False


class MayaSkinningCleanupController(object):
    def __init__(self):
        self.report = None
        self.result = None
        self.character_result = None
        self.status_callback = None

    def shutdown(self):
        pass

    def _set_status(self, message, success):
        if self.status_callback:
            self.status_callback(message, success)
        if success:
            _debug(message)
        else:
            _warning(message)

    def report_text(self):
        text = _format_report(self.report)
        if self.character_result:
            text += "\n\nTrack A whole-character copy:\n"
            text += "GREEN - verified separate copy: {0}\n".format(
                _short_name(self.character_result.get("copy_root", "")) if self.character_result.get("verified") else "not verified"
            )
            text += "GREEN - source untouched: {0}\n".format("yes" if self.character_result.get("source_untouched") else "no")
            text += "Joints checked: {0}\n".format(len(self.character_result.get("joint_checks", [])))
            text += "Meshes checked: {0}\n".format(len(self.character_result.get("mesh_checks", [])))
            text += "Animation keys copied to compensation groups: {0}\n".format(self.character_result.get("animation_keys_copied", 0))
            for mesh_check in self.character_result.get("mesh_checks", []):
                text += "Mesh {0}: deformation delta {1:.8f}, weight delta {2:.8f}\n".format(
                    _short_name(mesh_check.get("copy", "")),
                    float(mesh_check.get("deformation_delta", 0.0)),
                    float(mesh_check.get("max_weight_delta", 0.0)),
                )
            for reason in self.character_result.get("unsupported", []):
                text += "RED - Unsupported: {0}\n".format(reason)
        return text

    def create_whole_character_copy(self, root_transform=None):
        success, message, result = create_whole_character_copy(root_transform=root_transform)
        self.character_result = result
        self._set_status(message, success)
        return success, message

    def create_character_copy(self, root_transform=None):
        return self.create_whole_character_copy(root_transform=root_transform)

    def analyze_selection(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."

        target, message = _selected_mesh_target()
        if not target:
            self.report = None
            return False, message

        source_transform = target["transform"]
        source_shape = target["shape"]
        errors = []
        warnings = []

        scale = cmds.getAttr(source_transform + ".scale")[0]
        if any(abs(value) <= VALUE_EPSILON for value in scale):
            errors.append("The mesh has a scale of zero on one axis, so this tool cannot rebuild it safely.")

        skin_cluster = _find_skin_cluster(source_shape)
        if not skin_cluster:
            errors.append("This mesh is not skinned.")

        base_shape = _find_base_shape(source_transform, source_shape, skin_cluster) if skin_cluster else ""
        if skin_cluster and not base_shape:
            warnings.append("Could not find a hidden original mesh shape, so the tool will use a baked visible-mesh fallback.")

        unsupported_history = _unsupported_history_nodes(source_shape, skin_cluster) if skin_cluster else []
        if unsupported_history:
            names = ", ".join("{0} ({1})".format(_short_name(node_name), node_type) for node_name, node_type in unsupported_history)
            warnings.append("Extra deformation history will be baked into the clean mesh copy: {0}".format(names))

        if ":" in source_transform:
            warnings.append("This mesh uses names with extra tags. The tool can still work, but it will check names carefully.")
        if _referenced_warning(source_transform):
            warnings.append("This mesh comes from a reference. Making a clean copy is okay, but replacing the original may not be allowed.")

        shading_assignments = _capture_shading_assignments(source_transform, source_shape)
        if len(shading_assignments) > 1:
            warnings.append("This mesh uses more than one material assignment. The tool will keep the face-based material split.")

        world_normals = _capture_world_normals(source_shape)
        if world_normals:
            try:
                locked = cmds.polyNormalPerVertex(source_shape + ".vtxFace[*][*]", query=True, freezeNormal=True) or []
            except Exception:
                locked = []
            if any(bool(value) for value in locked):
                warnings.append("This mesh has locked normals. The tool will keep checking them after cleanup.")

        skin_data = _capture_skin_data(source_shape, skin_cluster) if skin_cluster and not errors else {"influences": [], "blend_weights": [], "settings": {}, "vertex_count": 0}
        report = {
            "source_transform": source_transform,
            "source_shape": source_shape,
            "skin_cluster": skin_cluster,
            "base_shape": base_shape,
            "errors": errors,
            "warnings": warnings,
            "skin_data": skin_data,
            "shading_assignments": shading_assignments,
            "uv_summary": _capture_uv_summary(source_shape),
            "color_summary": _capture_color_summary(source_shape),
            "edge_smoothing": _capture_edge_smoothing(source_shape),
            "world_normals": world_normals,
            "topology_signature": _capture_topology_signature(source_shape),
            "result": None,
        }
        self.report = report
        self.result = None
        if errors:
            return False, "The selected mesh is not ready. Read the red notes below."
        if warnings:
            return True, "The mesh can be frozen, but read the yellow notes first."
        return True, "The mesh looks ready for a clean frozen copy."

    def delete_clean_copy(self):
        if not self.result or not self.result.get("clean_transform"):
            return False, "There is no clean copy to delete."
        clean_transform = self.result["clean_transform"]
        if cmds.objExists(clean_transform):
            cmds.delete(clean_transform)
        if self.report:
            self.report["result"] = None
        self.result = None
        return True, "Deleted the clean copy."

    def create_clean_copy(self):
        if not self.report or self.report["errors"]:
            success, message = self.analyze_selection()
            if not success:
                return False, message

        if self.result and self.result.get("clean_transform") and cmds.objExists(self.result["clean_transform"]):
            try:
                cmds.delete(self.result["clean_transform"])
            except Exception:
                pass

        try:
            clean_transform, clean_shape = _build_clean_mesh_snapshot(self.report)
            new_skin_cluster = _bind_clean_mesh(clean_transform, clean_shape, self.report)
            _apply_shading_assignments(clean_transform, clean_shape, self.report["shading_assignments"])
            verification = _verify_cleanup(self.report, clean_transform, clean_shape, new_skin_cluster)
        except Exception as exc:
            _warning(traceback.format_exc())
            return False, "Could not make the clean copy: {0}".format(exc)

        self.result = {
            "clean_transform": clean_transform,
            "clean_shape": clean_shape,
            "skin_cluster": new_skin_cluster,
            "verification": verification,
            "verified": verification["passed"],
        }
        self.report["result"] = self.result
        if verification["passed"]:
            return True, "Clean frozen copy made and checked. You can replace the original when you are happy."
        return False, "A clean frozen copy was made, but one or more checks failed. The original mesh is still untouched."

    def replace_original(self):
        if not self.report or not self.result:
            return False, "Make and check a clean frozen copy first."
        if not self.result.get("verified"):
            return False, "The clean copy did not pass all checks, so replace is blocked."

        source_transform = self.report["source_transform"]
        clean_transform = self.result["clean_transform"]
        if _referenced_warning(source_transform):
            return False, "This mesh comes from a reference, so automatic replace is blocked. Keep the clean copy and swap it by hand if needed."
        if not cmds.objExists(source_transform) or not cmds.objExists(clean_transform):
            return False, "The original mesh or the clean copy could not be found."

        source_short = _short_name(source_transform)
        backup_name = _unique_name(source_short + BACKUP_SUFFIX)
        try:
            backup_transform = cmds.rename(source_transform, backup_name)
            if cmds.attributeQuery("visibility", node=backup_transform, exists=True):
                cmds.setAttr(backup_transform + ".visibility", 0)
            final_transform = cmds.rename(clean_transform, source_short)
            shapes = cmds.listRelatives(final_transform, shapes=True, fullPath=True, type="mesh") or []
            if shapes:
                target_shape_name = source_short + "Shape"
                try:
                    cmds.rename(shapes[0], target_shape_name)
                except Exception:
                    pass
        except Exception as exc:
            _warning(traceback.format_exc())
            return False, "Could not replace the original mesh: {0}".format(exc)

        self.result["backup_transform"] = backup_transform
        self.result["clean_transform"] = final_transform
        return True, "Replaced the original mesh. The old one is still in the scene as a hidden backup."

    def replace_with_frozen_transform_mesh(self):
        if not MAYA_AVAILABLE:
            return False, "This tool only works inside Maya."
        try:
            cmds.undoInfo(openChunk=True, chunkName="AminateReplaceWithFrozenTransformMesh")
            success, message = self.analyze_selection()
            if not success:
                return False, message
            success, message = self.create_clean_copy()
            if not success:
                return False, message
            success, message = self.replace_original()
            if not success:
                return False, message
            return True, "Replaced selected skinned mesh with a clean frozen-transform mesh. Skin weights, influences, materials, UVs, and normals were preserved."
        finally:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass


class _WindowBase(QtWidgets.QDialog if QtWidgets else object):
    pass


if QtWidgets:
    try:
        from maya.OpenMayaUI import MQtUtil
        from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

        if MQtUtil.mainWindow() is not None:
            _WindowBase = type("MayaSkinningCleanupBase", (MayaQWidgetDockableMixin, QtWidgets.QDialog), {})
        else:
            _WindowBase = type("MayaSkinningCleanupBase", (QtWidgets.QDialog,), {})
    except Exception:
        _WindowBase = type("MayaSkinningCleanupBase", (QtWidgets.QDialog,), {})


if QtWidgets:
    class MayaSkinningCleanupWindow(_WindowBase):
        def __init__(self, controller, parent=None):
            super(MayaSkinningCleanupWindow, self).__init__(parent or _maya_main_window())
            self.controller = controller
            self.controller.status_callback = self._set_status
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Maya Character Skinning")
            self.setMinimumWidth(760)
            self.setMinimumHeight(620)
            self._build_ui()
            self._refresh_report()

        def _build_ui(self):
            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.setContentsMargins(12, 12, 12, 12)
            main_layout.setSpacing(10)

            description = QtWidgets.QLabel(
                "Track A: select one character root to make a separate corrected copy with joint scales set to 1,1,1. Track B: use the adjacent Skin Transfer action for body-to-clothing or different-topology weights."
            )
            description.setWordWrap(True)
            main_layout.addWidget(description)

            note = QtWidgets.QLabel(
                "Track A never edits the source. It preserves world joint transforms, mesh placement and pivots, skin data, and animation where supported. Unsupported drivers are reported and rolled back."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #B8D7FF;")
            main_layout.addWidget(note)

            self.analyze_button = QtWidgets.QPushButton("Check Selected Mesh")
            self.analyze_button.setToolTip("Check the selected skinned mesh and show red, yellow, or green notes.")
            self.create_button = QtWidgets.QPushButton("Replace Mesh With Frozen Transform Mesh")
            self.create_button.setMinimumHeight(42)
            self.create_button.setMinimumWidth(0)
            self.create_button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.create_button.setToolTip("One-click fix: make a verified frozen copy, replace the selected mesh, and keep the old mesh hidden as a backup.")
            self.character_copy_button = QtWidgets.QPushButton("Track A: Copy Whole Character (Safe)")
            self.character_copy_button.setMinimumHeight(42)
            self.character_copy_button.setMinimumWidth(0)
            self.character_copy_button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            self.character_copy_button.setToolTip(
                "Select one character root. Creates a separate corrected copy, normalizes every copied joint scale to 1,1,1, and rolls back on unsupported cases."
            )
            self.replace_button = QtWidgets.QPushButton("Replace Original")
            self.replace_button.setToolTip("Only works after all checks pass. The old mesh is kept as a hidden backup.")
            self.delete_button = QtWidgets.QPushButton("Delete Frozen Copy")
            self.delete_button.setToolTip("Remove the frozen copy if you do not want to keep it.")
            main_layout.addWidget(self.create_button)
            main_layout.addWidget(self.character_copy_button)

            self.advanced_toggle = QtWidgets.QToolButton()
            self.advanced_toggle.setText("Advanced / Recovery")
            self.advanced_toggle.setCheckable(True)
            self.advanced_toggle.setChecked(False)
            self.advanced_toggle.setToolTip("Show preview, replace, and frozen-copy recovery actions.")
            self.advanced_body = QtWidgets.QWidget()
            advanced_layout = QtWidgets.QGridLayout(self.advanced_body)
            advanced_layout.setContentsMargins(0, 0, 0, 0)
            advanced_layout.setHorizontalSpacing(6)
            advanced_layout.setVerticalSpacing(6)
            for action_button in (self.analyze_button, self.replace_button, self.delete_button):
                action_button.setMinimumWidth(0)
                action_button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            advanced_layout.addWidget(self.analyze_button, 0, 0)
            advanced_layout.addWidget(self.replace_button, 0, 1)
            advanced_layout.addWidget(self.delete_button, 1, 0, 1, 2)
            advanced_layout.setColumnStretch(0, 1)
            advanced_layout.setColumnStretch(1, 1)
            self.advanced_body.setVisible(False)
            self.advanced_toggle.toggled.connect(self.advanced_body.setVisible)
            main_layout.addWidget(self.advanced_toggle)
            main_layout.addWidget(self.advanced_body)

            self.report_text = QtWidgets.QPlainTextEdit()
            self.report_text.setReadOnly(True)
            self.report_text.setMinimumHeight(0)
            self.report_text.setToolTip("Red means stop. Yellow means check carefully. Green means ready.")
            main_layout.addWidget(self.report_text, 1)

            self.status_label = QtWidgets.QLabel("Pick one character root for Track A, or one skinned mesh for the legacy single-mesh cleanup.")
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
            self.donate_button.clicked.connect(self._open_donate_url)
            footer_layout.addWidget(self.donate_button)
            main_layout.addLayout(footer_layout)

            self.analyze_button.clicked.connect(self._analyze)
            self.create_button.clicked.connect(self._replace_with_frozen_transform_mesh)
            self.character_copy_button.clicked.connect(self._create_whole_character_copy)
            self.replace_button.clicked.connect(self._replace_original)
            self.delete_button.clicked.connect(self._delete_clean_copy)

        def _refresh_report(self):
            self.report_text.setPlainText(self.controller.report_text())

        def _set_status(self, message, success):
            self.status_label.setText(message)

        def _analyze(self):
            success, message = self.controller.analyze_selection()
            self._refresh_report()
            self._set_status(message, success)

        def _create_clean_copy(self):
            success, message = self.controller.create_clean_copy()
            self._refresh_report()
            self._set_status(message, success)

        def _replace_with_frozen_transform_mesh(self):
            success, message = self.controller.replace_with_frozen_transform_mesh()
            self._refresh_report()
            self._set_status(message, success)

        def _create_whole_character_copy(self):
            success, message = self.controller.create_whole_character_copy()
            self._refresh_report()
            self._set_status(message, success)

        def _replace_original(self):
            success, message = self.controller.replace_original()
            self._refresh_report()
            self._set_status(message, success)

        def _delete_clean_copy(self):
            success, message = self.controller.delete_clean_copy()
            self._refresh_report()
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
                self._set_status("Opened the donate page.", True)
            else:
                self._set_status("Could not open the donate page from this Maya session.", False)

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


def launch_maya_skinning_cleanup(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not MAYA_AVAILABLE:
        raise RuntimeError("maya_skinning_cleanup.launch_maya_skinning_cleanup() must run inside Autodesk Maya.")
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
    _close_existing_window()
    GLOBAL_CONTROLLER = MayaSkinningCleanupController()
    GLOBAL_WINDOW = MayaSkinningCleanupWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    GLOBAL_WINDOW.show()
    GLOBAL_WINDOW.raise_()
    GLOBAL_WINDOW.activateWindow()
    return GLOBAL_WINDOW


__all__ = [
    "launch_maya_skinning_cleanup",
    "create_whole_character_copy",
    "create_character_copy",
    "UnsupportedCharacterCase",
    "MayaSkinningCleanupController",
]
