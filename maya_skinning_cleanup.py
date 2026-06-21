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
VALUE_EPSILON = 1.0e-5
NORMAL_EPSILON = 1.0e-4

GLOBAL_CONTROLLER = None
GLOBAL_WINDOW = None


def _debug(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayInfo("[Maya Skinning Cleanup] {0}".format(message))


def _warning(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayWarning("[Maya Skinning Cleanup] {0}".format(message))


def _error(message):
    if MAYA_AVAILABLE and om:
        om.MGlobal.displayError("[Maya Skinning Cleanup] {0}".format(message))


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

    influences = []
    for influence_dag in skin_fn.influenceObjects():
        full_path = influence_dag.fullPathName()
        physical_index = int(skin_fn.indexForInfluenceObject(influence_dag))
        weights = list(skin_fn.getWeights(shape_dag, component, physical_index))
        influences.append(
            {
                "path": full_path,
                "uuid": _uuid_for_node(full_path),
                "physical_index": physical_index,
                "weights": weights,
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
        "vertex_count": int(mesh_fn.numVertices),
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

    skin_fn.setWeights(shape_dag, component, indices, weights, normalize=False)
    skin_fn.setBlendWeights(shape_dag, component, om.MDoubleArray(report["skin_data"]["blend_weights"]))
    return new_skin_cluster


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
        return _format_report(self.report)

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
                "Select an already skinned mesh with bad translate, rotate, or scale values, then press the button below. Aminate replaces it with a clean frozen-transform mesh while preserving skin weights."
            )
            description.setWordWrap(True)
            main_layout.addWidget(description)

            note = QtWidgets.QLabel(
                "The old mesh is kept as a hidden backup after the replacement. Reference meshes are blocked so they are not changed by mistake."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #B8D7FF;")
            main_layout.addWidget(note)

            self.analyze_button = QtWidgets.QPushButton("Check Selected Mesh")
            self.analyze_button.setToolTip("Check the selected skinned mesh and show red, yellow, or green notes.")
            self.create_button = QtWidgets.QPushButton("Replace Mesh With Frozen Transform Mesh")
            self.create_button.setMinimumHeight(42)
            self.create_button.setToolTip("One-click fix: make a verified frozen copy, replace the selected mesh, and keep the old mesh hidden as a backup.")
            self.replace_button = QtWidgets.QPushButton("Replace Original")
            self.replace_button.setToolTip("Only works after all checks pass. The old mesh is kept as a hidden backup.")
            self.delete_button = QtWidgets.QPushButton("Delete Frozen Copy")
            self.delete_button.setToolTip("Remove the frozen copy if you do not want to keep it.")
            self.analyze_button.hide()
            self.replace_button.hide()
            self.delete_button.hide()
            main_layout.addWidget(self.create_button)

            self.report_text = QtWidgets.QPlainTextEdit()
            self.report_text.setReadOnly(True)
            self.report_text.setToolTip("Red means stop. Yellow means check carefully. Green means ready.")
            main_layout.addWidget(self.report_text, 1)

            self.status_label = QtWidgets.QLabel("Pick one skinned mesh, then click Replace Mesh With Frozen Transform Mesh.")
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

    if QtWidgets:
        application = QtWidgets.QApplication.instance()
        if application and hasattr(application, "topLevelWidgets"):
            for widget in application.topLevelWidgets():
                try:
                    if widget.objectName() == WINDOW_OBJECT_NAME:
                        widget.close()
                        widget.deleteLater()
                except Exception:
                    pass

    GLOBAL_CONTROLLER = None
    GLOBAL_WINDOW = None


def launch_maya_skinning_cleanup(dock=False):
    global GLOBAL_CONTROLLER
    global GLOBAL_WINDOW
    if not MAYA_AVAILABLE:
        raise RuntimeError("maya_skinning_cleanup.launch_maya_skinning_cleanup() must run inside Autodesk Maya.")
    if not QtWidgets:
        raise RuntimeError("PySide is not available in this Maya session.")
    _close_existing_window()
    GLOBAL_CONTROLLER = MayaSkinningCleanupController()
    GLOBAL_WINDOW = MayaSkinningCleanupWindow(GLOBAL_CONTROLLER, parent=_maya_main_window())
    GLOBAL_WINDOW.show()
    GLOBAL_WINDOW.raise_()
    GLOBAL_WINDOW.activateWindow()
    return GLOBAL_WINDOW


__all__ = [
    "launch_maya_skinning_cleanup",
    "MayaSkinningCleanupController",
]
