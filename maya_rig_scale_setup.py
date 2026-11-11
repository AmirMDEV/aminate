"""Guarded, in-place uniform Rig Scale setup for Maya rigs."""

import json
import math
import re
import uuid

try:
    import maya.api.OpenMaya as om
    import maya.cmds as cmds
except ImportError:
    om = cmds = None


_SCALE = "rigScale"
_MIN_SCALE = 0.001
_OWNER = "aminateRigScaleVersion"
_MASTER = "aminateRigScaleMaster"
_UTILITIES = "aminateRigScaleUtilities"
_ATTACHMENTS = "aminateRigScaleAttachments"
_ATTACHMENT_COUNT = "aminateRigScaleAttachmentCount"
_VERSION = "1"
_BRANCH_VERSION = "2"
_SIGNAL_VERSION = "3"
_BRANCH_SIGNAL_VERSION = "4"
_MESH_ATTACHMENT_VERSIONS = {"5": "1", "6": "2", "7": "3", "8": "4"}
_MESH_ATTACHMENTS = "aminateRigScaleMeshAttachments"
_MESH_ATTACHMENT_COUNT = "aminateRigScaleMeshAttachmentCount"
_SKIN_BRANCHES = "aminateRigScaleSkinBranches"
_SKIN_BRANCH_COUNT = "aminateRigScaleSkinBranchCount"
_SCALE_SIGNALS = "aminateRigScaleSignals"
_SCALE_SIGNAL_SCOPE = "aminateRigScaleSignalScope"
_COORDINATE_VERSION = "9"
_COORDINATE_PLAN = "aminateRigScaleCoordinatePlan"
_SPLINE_VERSION = "10"
_SPLINE_PLAN = "aminateRigScaleSplinePlan"
_STATIC_SURFACE_VERSION = "12"
_STATIC_SURFACE_PLAN = "aminateRigScaleStaticSurfacePlan"
_STATIC_SURFACE_FRAME_NOTE = "Position this rig with its master control and keep the outer scene frame unchanged."
_AXES = "XYZ"
_BRANCH_GRAPH_LIMIT = 2048
_SCALE_SIGNAL_GRAPH_LIMIT = 8192
_SCALE_SIGNAL_PROCESSORS = {
    "addDoubleLinear", "animCurveUA", "animCurveUL", "animCurveUU",
    "blendColors", "blendTwoAttr", "clamp", "condition", "curveInfo", "dagPose",
    "distanceBetween", "distanceBetweenDL", "groupParts", "multDoubleLinear",
    "multiplyDivide", "plusMinusAverage", "pointOnCurveInfo", "reverse",
    "setRange", "skinCluster", "unitConversion",
}
_SCALE_SIGNAL_DAG_TYPES = {
    "aimConstraint", "annotationShape", "distanceDimShape", "ikEffector",
    "ikHandle", "joint", "locator", "mesh", "nurbsCurve", "orientConstraint",
    "parentConstraint", "pointConstraint", "poleVectorConstraint",
    "scaleConstraint", "tangentConstraint", "transform",
}


class _Unsupported(Exception):
    """The current rig cannot safely use the supported setup."""


class _RollbackFailure(RuntimeError):
    """Maya could not restore the previous scale edit safely."""


class _VerificationFailure(_Unsupported):
    def __init__(self, reason, obj, typ, factor, error):
        super().__init__(reason)
        self.node = {
            "uuid": om.MFnDependencyNode(obj).uuid().asString(),
            "path": om.MDagPath.getAPathTo(obj).fullPathName(),
            "type": typ,
            "scale": factor,
            "error": error,
        }


def _inside(path, parent):
    return path == parent or path.startswith(parent + "|")


def _path(node):
    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDagPath(0)


def _resolve_transform(node, label):
    matches = cmds.ls(node, long=True, allPaths=True, objectsOnly=True) if node else []
    if len(matches) != 1 or cmds.nodeType(matches[0]) != "transform":
        raise _Unsupported("Choose one unambiguous transform for the {}.".format(label))
    if _path(matches[0]).isInstanced():
        raise _Unsupported("The {} is instanced.".format(label))
    return matches[0]


def _parent(node):
    return (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]


def _local_node(node):
    if cmds.referenceQuery(node, isNodeReferenced=True):
        raise _Unsupported("Edit the source scene for the referenced node {}.".format(node))
    if cmds.lockNode(node, query=True, lock=True)[0]:
        raise _Unsupported("The node {} is locked.".format(node))


def _input(plug):
    return cmds.connectionInfo(plug, sourceFromDestination=True) or ""


def _incoming(plug):
    return bool(cmds.listConnections(plug, source=True, destination=False, plugs=True))


def _source_node(plug):
    source = _input(plug)
    if not source:
        return None
    nodes = cmds.ls(source.split(".", 1)[0], long=True, allPaths=True) or []
    return nodes[0] if len(nodes) == 1 else None


def _attached_source(follicle, master, scope):
    surfaces = [_source_node(follicle + "." + attr) for attr in ("inputSurface", "inputMesh")]
    surfaces = [s for s in surfaces if s]
    if len(surfaces) != 1 or not _inside(surfaces[0], scope):
        return None
    surface = surfaces[0]
    if _source_node(follicle + ".inputWorldMatrix") != surface:
        return None
    return _skin_source_branch(surface, master)


def _skin_source_branch(surface, master, require_uninstanced=False):
    skins = cmds.ls(cmds.listHistory(surface, pruneDagObjects=True) or [], type="skinCluster") or []
    if len(skins) != 1:
        return None
    names = cmds.skinCluster(skins[0], query=True, influence=True) or []
    if not names:
        return None
    branches = set()
    for name in names:
        matches = cmds.ls(name, long=True, allPaths=True) or []
        if len(matches) != 1 or not _inside(matches[0], master):
            return None
        if require_uninstanced and _path(matches[0]).isInstanced():
            return None
        branch = matches[0][len(master):].strip("|").split("|", 1)[0]
        branches.add(master + "|" + branch if branch else master)
    # Use a common top branch of the skin drivers, avoiding limb-specific scale.
    return next(iter(branches)) if len(branches) == 1 else master


def _visible(path, scope):
    while path and _inside(path, scope):
        if not cmds.getAttr(path + ".visibility"):
            return False
        path = _parent(path)
    return True


def _curve_control_evidence(curve, scope):
    # Detached hidden deformation curves must not be scaled. Keep hidden
    # controls when an animator display override or a visibility driver exists.
    parent = _parent(curve)
    for node in (curve, parent):
        if cmds.getAttr(node + ".overrideEnabled") or _incoming(node + ".visibility"):
            return True
    return _visible(curve, scope)


def _mesh_attachment_source(follicle, node, master, scope, skin_sources, owned_link=None):
    # A non-inheriting follicle can place a mesh at the correct position
    # without inheriting its size. Require the exact object-space surface
    # and corresponding matrix, and keep its scaled outputs in this rig.
    if (cmds.nodeType(node) != "transform" or _inside(master, node)
            or cmds.getAttr(node + ".inheritsTransform")
            or _incoming(node + ".inheritsTransform") or _incoming(follicle + ".inputSurface")
            or not cmds.isConnected(follicle + ".outTranslate", node + ".translate")
            or not cmds.isConnected(follicle + ".outRotate", node + ".rotate")):
        return None
    surface = _source_node(follicle + ".inputMesh")
    if (not surface or not _inside(surface, scope) or _inside(surface, node)
            or cmds.nodeType(surface) != "mesh"
            or not cmds.isConnected(surface + ".outMesh", follicle + ".inputMesh")):
        return None
    matrix = _parent(surface)
    if not matrix or not cmds.isConnected(matrix + ".worldMatrix[0]", follicle + ".inputWorldMatrix"):
        return None
    if (surface, matrix) not in skin_sources:
        skin_sources[surface, matrix] = (None if _path(surface).isInstanced() or _path(matrix).isInstanced()
                                         else _skin_source_branch(surface, master, require_uninstanced=True))
    source = skin_sources[surface, matrix]
    if not source or not _branch_scope_isolated(node, scope, set(), owned_link):
        return None
    return source, surface


def _attachment_plan(follicles, curves, meshes, master, scope):
    plans = []
    skin_sources = {}
    for shape in follicles:
        node = _parent(shape)
        if _inside(node, master):
            continue
        source = None
        mesh_source = None
        if any(_inside(curve, node) for curve in curves):
            source = _attached_source(shape, master, scope)
            if source and (_source_node(node + ".translate") != shape or _source_node(node + ".rotate") != shape):
                source = None
        if not source and any(_inside(mesh, node) for mesh in meshes):
            mesh_source = _mesh_attachment_source(shape, node, master, scope, skin_sources)
            if mesh_source:
                source, surface = mesh_source
        if not source:
            # It may already inherit scale through an existing rig mechanism.
            # Include its geometry in verification without modifying it.
            continue
        _local_node(node)
        if _path(node).isInstanced():
            raise _Unsupported("Attachment {} is instanced.".format(node))
        if _incoming(node + ".scale") or any(_incoming(node + ".scale" + axis) for axis in _AXES):
            # Leave established scale drivers alone and let the proof decide.
            continue
        parent = _parent(node) if cmds.getAttr(node + ".inheritsTransform") else None
        matrix = _path(source).inclusiveMatrix()
        if parent:
            matrix *= _path(parent).inclusiveMatrixInverse()
        source_scale = om.MTransformationMatrix(matrix).scale(om.MSpace.kTransform)
        original = cmds.getAttr(node + ".scale")[0]
        if any(not math.isfinite(v) or abs(v) < 1e-9 for v in (*source_scale, *original)):
            raise _Unsupported("Attachment {} has a singular scale.".format(node))
        plans.append({
            "transform": node, "source": source, "parent": parent,
            "ratios": [a / b for a, b in zip(original, source_scale)],
        })
        if mesh_source:
            plans[-1]["mesh_identity"] = [cmds.ls(path, uuid=True)[0]
                                          for path in (node, shape, surface, source)]
    return plans


def _root_follows_master(joint, master):
    # Require one position constraint with all three outputs and with every
    # target's local translation and parent matrix sourced from the master DAG.
    constraint = _source_node(joint + ".translateX")
    if not constraint or cmds.nodeType(constraint) not in ("pointConstraint", "parentConstraint"):
        return False
    if not all(cmds.isConnected(constraint + ".constraintTranslate" + axis,
                                joint + ".translate" + axis) for axis in _AXES):
        return False
    if not cmds.isConnected(joint + ".parentInverseMatrix[0]", constraint + ".constraintParentInverseMatrix"):
        return False
    indices = cmds.getAttr(constraint + ".target", multiIndices=True) or []
    for index in indices:
        target = "{}.target[{}]".format(constraint, index)
        driver = _source_node(target + ".targetTranslate")
        if not driver or not _inside(driver, master) or _source_node(target + ".targetParentMatrix") != driver:
            return False
    return bool(indices)


def _branch_scope_isolated(branch, scope, skins, owned_link=None):
    # Follow inherited transforms as well as explicit outputs. Accept only the
    # built-in processors used by this skeleton pattern, and fail closed when
    # their downstream graph reaches another rig or cannot be bounded.
    pending = [branch]
    seen = set()
    destinations = {}
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        if len(seen) > _BRANCH_GRAPH_LIMIT:
            return False
        if node.startswith("|"):
            if not _inside(node, scope) or _path(node).isInstanced():
                return False
            pending.extend(cmds.listRelatives(node, children=True, fullPath=True) or [])
        else:
            kind = cmds.nodeType(node)
            if kind == "skinCluster":
                if node not in skins:
                    return False
                for geometry in cmds.skinCluster(node, query=True, geometry=True) or []:
                    matches = cmds.ls(geometry, long=True, allPaths=True) or []
                    if len(matches) != 1 or not _inside(matches[0], scope):
                        return False
            elif kind not in ("dagPose", "HIKCharacterNode", "HIKSolverNode", "HIKState2SK"):
                return False

        connections = cmds.listConnections(node, source=False, destination=True,
                                           plugs=True, connections=True) or []
        for source, target in zip(connections[::2], connections[1::2]):
            name, target_attr = target.split(".", 1)
            if name not in destinations:
                matches = cmds.ls(name, long=True, allPaths=True) or []
                if len(matches) != 1:
                    return False
                destinations[name] = (matches[0], cmds.nodeType(matches[0]))
            path, kind = destinations[name]
            source_attr = source.split(".", 2)[1].split("[", 1)[0]
            if source_attr == "message" and owned_link == (path, target_attr):
                continue
            # Shading and deformer sets can be shared across rigs. Their
            # membership inputs carry no evaluated transform or geometry.
            if (kind in ("objectSet", "shadingEngine")
                    and source_attr == "instObjGroups" and target_attr.startswith("dagSetMembers[")):
                continue
            if kind == "objectSet" and source_attr == "message" and target_attr.startswith("usedBy["):
                continue
            pending.append(path)
    return True


def _skin_branch_plan(meshes, master, parent, scope):
    # A detached bind skeleton may follow the controls through translation and
    # rotation constraints while its bones and IK chain keep their old lengths.
    # Only move an entire, dedicated sibling skeleton in the same parent space.
    if not parent or not _inside(parent, scope):
        return []
    skins = set()
    for mesh in meshes:
        history = cmds.listHistory(mesh, pruneDagObjects=True) or []
        skins.update(cmds.ls(history, type="skinCluster") or [])
    candidates = set()
    for skin in skins:
        for name in cmds.skinCluster(skin, query=True, influence=True) or []:
            matches = cmds.ls(name, long=True, allPaths=True) or []
            if len(matches) != 1 or not _inside(matches[0], parent) or _inside(matches[0], master):
                continue
            branch_name = matches[0][len(parent) + 1:].split("|", 1)[0]
            if branch_name:
                candidates.add(parent + "|" + branch_name)

    plans = []
    for branch in sorted(candidates):
        if cmds.nodeType(branch) != "transform" or _path(branch).isInstanced():
            continue
        if not cmds.getAttr(branch + ".inheritsTransform") or _incoming(branch + ".inheritsTransform"):
            continue
        if (_incoming(branch + ".offsetParentMatrix")
                or any(_incoming(branch + "." + attr + axis)
                       for attr in ("translate", "rotate", "scale") for axis in ("", *_AXES))):
            # An existing driver may already propagate the master's scale.
            continue
        roots = cmds.listRelatives(branch, children=True, fullPath=True, type="joint") or []
        if not roots or not all(_root_follows_master(root, master) for root in roots):
            continue
        children = cmds.listRelatives(branch, children=True, fullPath=True) or []
        if any(child not in roots and cmds.nodeType(child) != "locator" for child in children):
            continue
        if cmds.listRelatives(branch, allDescendents=True, type=("mesh", "nurbsSurface", "nurbsCurve")):
            continue
        if not _branch_scope_isolated(branch, scope, skins):
            continue
        _local_node(branch)
        plans.append(branch)
    return plans


def _outgoing(plug):
    return cmds.listConnections(plug, source=False, destination=True, plugs=True) or []


def _scale_signal_scope(destinations, master, scope, extensions=None, owned=()):
    # Walk existing evaluation outputs before changing any native scale input.
    # A data connection into an unbounded, unknown or external graph is not
    # proof that the destination belongs only to this character.
    pending = [plug.split(".", 1)[0] for plug in destinations]
    resolved = {}
    seen = set()
    found_dag = False
    while pending:
        node = pending.pop()
        if node not in resolved:
            resolved[node] = cmds.ls(node, long=True, allPaths=True) or []
        paths = resolved[node]
        if len(paths) != 1:
            return False
        path = paths[0]
        if path in seen:
            continue
        seen.add(path)
        if len(seen) > _SCALE_SIGNAL_GRAPH_LIMIT:
            return False
        kind = cmds.nodeType(path)
        allowed = extensions is not None and path in extensions
        if path.startswith("|"):
            if (path == master or _path(path).isInstanced()
                    or (not allowed and (kind not in _SCALE_SIGNAL_DAG_TYPES or not _inside(path, scope)))):
                return False
            found_dag = True
            pending.extend(cmds.listRelatives(path, children=True, fullPath=True) or [])
        elif kind not in _SCALE_SIGNAL_PROCESSORS and not allowed:
            return False
        for source, target in _data_edges(path, owned=owned):
            if allowed and kind == "blendShape" and _shape_editor_edge(source, target):
                continue
            pending.append(target.split(".", 1)[0])
    return found_dag


def _shape_editor_edge(source, target):
    node, attr = target.split(".", 1)
    return (source.endswith(".midLayerParent") and not _incoming(source)
            and cmds.nodeType(node) == "shapeEditorManager"
            and re.fullmatch(r"(?:blendShapeParent|bspr)\[\d+\]", attr) is not None)


def _data_edges(node, incoming=False, owned=()):
    pairs = cmds.listConnections(node, source=incoming, destination=not incoming,
                                 plugs=True, connections=True) or []
    if incoming:
        pairs = [p for pair in zip(pairs[1::2], pairs[::2]) for p in pair]
    edges = []
    for source, target in zip(pairs[::2], pairs[1::2]):
        source_attr = source.split(".", 2)[1].split("[", 1)[0]
        target_node, target_attr = target.split(".", 1)
        # Repeat validation separately checks the owned utility wires.
        if source_attr == "message" or target_node in owned:
            continue
        if (source_attr in ("instObjGroups", "objectGroups")
                and target_attr.startswith("dagSetMembers[")
                and cmds.nodeType(target_node) in ("objectSet", "shadingEngine")):
            continue
        edges.append((source, target))
    return edges


def _plug_node(plug):
    if not plug:
        return None
    matches = cmds.ls(plug.split(".", 1)[0], long=True, allPaths=True) or []
    return matches[0] if len(matches) == 1 else None


def _is_local_dag(node):
    return (node and node.startswith("|") and not _path(node).isInstanced()
            and not cmds.referenceQuery(node, isNodeReferenced=True))


def _identity_matrix(plug):
    return om.MMatrix(cmds.getAttr(plug)) == om.MMatrix.kIdentity


def _fixed_attr(plug, value):
    return not _incoming(plug) and cmds.getAttr(plug) == value


def _coordinate_source(destination, originals):
    entry = originals.get(_coordinate_identity(destination))
    return entry[1] if entry else _input(destination)


def _exact_connections(node, expected, owned=()):
    # Compare actual authored plug pairs, including the original edge when
    # its verified owned relay is already in the scene.
    return len(_data_edges(node, owned=owned)) == len(expected) and all(
        _exact_input(source, target) for source, target in expected)


def _exact_input(source, target):
    return (cmds.connectionInfo(target, isExactDestination=True)
            and cmds.isConnected(source, target))


def _coordinate_follicles(master, scope, originals, owned):
    candidates = {}
    bad_islands = set()
    skin_sources = {}
    for constraint in cmds.ls(type="parentConstraint", long=True) or []:
        rigid = _parent(constraint)
        if not rigid or not _inside(rigid, scope):
            continue
        if cmds.getAttr(constraint + ".target", multiIndices=True) != [0]:
            continue
        target = constraint + ".target[0]"
        destination = target + ".targetScale"
        source = _coordinate_source(destination, originals)
        leaf = _plug_node(source)
        if not leaf or not leaf.startswith("|") or _inside(leaf, scope):
            continue
        island = _parent(leaf)
        if not island or _parent(island):
            continue
        shapes = cmds.listRelatives(leaf, children=True, fullPath=True) or []
        if len(shapes) != 1 or cmds.nodeType(shapes[0]) != "follicle":
            continue
        follicle = shapes[0]
        body = _source_node(follicle + ".inputMesh")
        pairs = [(leaf + "." + attr, target + "." + dest) for attr, dest in (
            ("translate", "targetTranslate"), ("rotate", "targetRotate"),
            ("rotatePivot", "targetRotatePivot"), ("rotatePivotTranslate", "targetRotateTranslate"),
            ("rotateOrder", "targetRotateOrder"), ("parentMatrix[0]", "targetParentMatrix"),
            ("scale", "targetScale"),
        )]
        connected = pairs[:-1] if _coordinate_identity(destination) in originals else pairs
        rigid_shapes = cmds.listRelatives(rigid, shapes=True, fullPath=True) or []
        scale_constraint = _source_node(rigid + ".scaleX")
        if (not all(_is_local_dag(node) for node in (leaf, follicle, island, rigid, constraint))
                or cmds.nodeType(leaf) != "transform" or cmds.nodeType(rigid) != "transform"
                or cmds.listAttr(leaf, userDefined=True) or cmds.listAttr(follicle, userDefined=True)
                or not _is_local_dag(body) or not _is_local_dag(_parent(body))
                or not _inside(body, scope) or cmds.nodeType(body) != "mesh"
                or cmds.getAttr(body + ".intermediateObject")
                or _coordinate_identity(source) != _coordinate_identity(leaf + ".scale")
                or not _fixed_attr(leaf + ".inheritsTransform", False)
                or not _fixed_attr(leaf + ".scale", [(1.0, 1.0, 1.0)])
                or _incoming(leaf + ".offsetParentMatrix") or not _identity_matrix(leaf + ".offsetParentMatrix")
                or len(_data_edges(leaf, incoming=True)) != 2
                or len(_data_edges(follicle, incoming=True)) != 2
                or not _exact_connections(follicle, [(follicle + ".outTranslate", leaf + ".translate"),
                                                     (follicle + ".outRotate", leaf + ".rotate")])
                or not _exact_connections(leaf, connected, owned)
                or not cmds.isConnected(body + ".outMesh", follicle + ".inputMesh")
                or not cmds.isConnected(_parent(body) + ".worldMatrix[0]", follicle + ".inputWorldMatrix")
                or not rigid_shapes or any(not _is_local_dag(s) or cmds.nodeType(s) != "mesh"
                                           or _incoming(s + ".inMesh")
                                           for s in rigid_shapes)
                or not scale_constraint or cmds.nodeType(scale_constraint) != "scaleConstraint"
                or _parent(scale_constraint) != rigid
                or cmds.getAttr(scale_constraint + ".target", multiIndices=True) != [0]
                or not _exact_input(master + ".scale", scale_constraint + ".target[0].targetScale")
                or not cmds.isConnected(master + ".parentMatrix[0]",
                                        scale_constraint + ".target[0].targetParentMatrix")
                or not all(cmds.isConnected(scale_constraint + ".constraintScale" + axis,
                                             rigid + ".scale" + axis) for axis in _AXES)
                or not _exact_connections(constraint, [
                    (constraint + ".constraint" + name + axis, rigid + "." + name.lower() + axis)
                    for name in ("Translate", "Rotate") for axis in _AXES
                ] + [(source_plug, target_plug) for source_plug, target_plug in _data_edges(constraint)
                     if _plug_node(target_plug) == constraint and target_plug.endswith(".targetWeight")])):
            bad_islands.add(island)
            continue
        if body not in skin_sources:
            skin_sources[body] = _skin_source_branch(body, master, require_uninstanced=True)
        if not skin_sources[body]:
            bad_islands.add(island)
            continue
        candidates.setdefault(island, []).append((leaf, follicle, source, destination, body))
    result = []
    for island, leaves in candidates.items():
        if (island not in bad_islands and cmds.nodeType(island) == "transform"
                and not cmds.listAttr(island, userDefined=True)
                and not _data_edges(island) and not _data_edges(island, incoming=True)
                and set(cmds.listRelatives(island, children=True, fullPath=True) or [])
                == {row[0] for row in leaves}):
            result.extend(leaves)
    return result


def _scale_divisor(plug):
    node, attr = plug.split(".", 1)
    return (cmds.nodeType(node) == "multiplyDivide"
            and attr in ("input2X", "input2Y", "input2Z")
            and cmds.getAttr(node + ".operation") == 2
            and not _incoming(node + ".operation"))


def _scale_signal_plan(master, scope):
    # A parent scale preserves editable/animated XYZ channels, but it does
    # not update authored local-scale multipliers used by some IK solvers.
    # Only relay divisor inputs with an isolated downstream graph.
    plan = {}
    for axis in _AXES:
        for plug in _outgoing(master + ".scale" + axis):
            node = plug.split(".", 1)[0]
            if not (_scale_divisor(plug)
                    and _input(plug) and cmds.isConnected(master + ".scale" + axis, plug)
                    and not cmds.getAttr(plug, lock=True)
                    and not cmds.referenceQuery(node, isNodeReferenced=True)
                    and not cmds.lockNode(node, query=True, lock=True)[0]):
                continue
            plan.setdefault(axis, []).append(plug)
    destinations = [plug for plugs in plan.values() for plug in plugs]
    return plan if destinations and _scale_signal_scope(destinations, master, scope) else {}


def _plug_identity(plug):
    node, attr = plug.split(".", 1)
    return cmds.ls(node, uuid=True)[0] + "." + attr


def _coordinate_identity(name):
    plug = om.MSelectionList().add(name).getPlug(0)
    attr = plug.partialName(includeNonMandatoryIndices=True, includeInstancedIndices=True,
                            useFullAttributePath=True, useLongNames=True)
    return om.MFnDependencyNode(plug.node()).uuid().asString() + "." + attr


def _coordinate_surface(attachment, master, scope, skin_sources):
    parent = _parent(attachment)
    point = _source_node(attachment + ".translate")
    if (not _is_local_dag(attachment) or not _inside(attachment, master) or not parent
            or not _fixed_attr(parent + ".inheritsTransform", False)
            or not cmds.getAttr(parent + ".inheritsTransform", lock=True)
            or not point or cmds.nodeType(point) != "pointOnCurveInfo"
            or not cmds.isConnected(point + ".position", attachment + ".translate")):
        return None
    curve = _source_node(point + ".inputCurve")
    if (not _is_local_dag(curve) or not _inside(curve, parent) or cmds.nodeType(curve) != "nurbsCurve"
            or not cmds.isConnected(curve + ".worldSpace[0]", point + ".inputCurve")):
        return None
    edge = _source_node(curve + ".create")
    if (not edge or cmds.nodeType(edge) != "curveFromMeshEdge"
            or not _exact_connections(edge, [(edge + ".outputCurve", curve + ".create")])):
        return None
    mesh = _source_node(edge + ".inputMesh")
    if (not _is_local_dag(mesh) or not _inside(mesh, scope) or cmds.nodeType(mesh) != "mesh"
            or not cmds.isConnected(mesh + ".worldMesh[0]", edge + ".inputMesh")):
        return None
    if mesh not in skin_sources:
        skin_sources[mesh] = _skin_source_branch(mesh, master, require_uninstanced=True)
    surfaces = cmds.listRelatives(attachment, allDescendents=True, fullPath=True, type="nurbsSurface") or []
    if not skin_sources[mesh] or not surfaces or not all(map(_is_local_dag, surfaces)):
        return None
    return {edge, *surfaces}


def _coordinate_targets(master, scope, originals, owned):
    targets = []
    for blend in cmds.ls(type="blendShape") or []:
        if not _fixed_attr(blend + ".origin", 1):
            continue
        geometry = cmds.blendShape(blend, query=True, geometry=True) or []
        if not geometry or any(not _is_local_dag(path) or not _inside(path, scope)
                               for path in map(_plug_node, geometry)):
            continue
        for source, dest in _data_edges(blend, incoming=True):
            if not dest.endswith(".inputGeomTarget"):
                continue
            shape = _plug_node(source)
            if (not _is_local_dag(shape) or not _inside(shape, scope) or _inside(shape, master)
                    or cmds.nodeType(shape) != "mesh" or cmds.getAttr(shape + ".intermediateObject")
                    or _incoming(shape + ".inMesh") or not cmds.isConnected(shape + ".worldMesh[0]", dest)
                    or not _exact_connections(shape, [(source, dest)])):
                continue
            target = _parent(shape)
            frame = _parent(target)
            offset = target + ".offsetParentMatrix"
            siblings = [child for child in cmds.listRelatives(target, children=True, fullPath=True) or []
                        if child != shape]
            if (not _is_local_dag(target) or not _is_local_dag(frame) or not _inside(frame, scope)
                    or not _fixed_attr(target + ".inheritsTransform", True)
                    or any(not _is_local_dag(sibling) or cmds.nodeType(sibling) != "mesh"
                           or not _fixed_attr(sibling + ".intermediateObject", True)
                           or _data_edges(sibling) or _data_edges(sibling, incoming=True) for sibling in siblings)
                    or _data_edges(target, owned=owned)
                    or (_coordinate_identity(offset) not in originals
                        and (not cmds.getAttr(offset, settable=True) or not _identity_matrix(offset)))):
                continue
            targets.append((offset, frame, shape + ".worldMesh[0]", dest, blend))
    return targets


def _coordinate_graph_nodes(scope, targets):
    # Extend the walk only through specific deformer and spline nodes whose
    # local connections are recognized. Every output is still walked.
    allowed = {entry[-1] for entry in targets}
    for cluster in cmds.ls(type="cluster") or []:
        matrix = _source_node(cluster + ".matrix")
        geometry = cmds.cluster(cluster, query=True, geometry=True) or []
        handle = _source_node(cluster + ".clusterXforms")
        if (not _is_local_dag(matrix) or not _inside(matrix, scope)
                or not _is_local_dag(handle) or _parent(handle) != matrix
                or cmds.nodeType(handle) != "clusterHandle"
                or not cmds.isConnected(matrix + ".worldMatrix[0]", cluster + ".matrix")
                or not geometry or any(not _is_local_dag(path) or not _inside(path, scope)
                                       for path in map(_plug_node, geometry))):
            continue
        allowed.update((cluster, handle))
    for ramp in cmds.ls(type="ramp") or []:
        edges = _data_edges(ramp)
        if edges and all(source == ramp + ".outColor"
                         and dest.endswith(".dTwistRamp")
                         and cmds.nodeType(_plug_node(dest)) == "ikHandle"
                         and _inside(_plug_node(dest), scope)
                         for source, dest in edges):
            allowed.add(ramp)
    return allowed


def _coordinate_plan(master, scope, group, originals=None, owned=()):
    parent = _parent(group)
    if not parent or not _inside(parent, scope):
        return None
    originals = originals or {}
    scale = master + ".scale"
    destinations = {target for target in _outgoing(scale) if target.split(".", 1)[0] not in owned}
    destinations.update(target for target, source in originals.values()
                        if source and _coordinate_identity(source) == _coordinate_identity(scale))
    signals = []
    starts = []
    extensions = set()
    skin_sources = {}
    for target in sorted(destinations):
        target_node = _plug_node(target)
        if not target_node or (_coordinate_identity(target) not in originals
                               and not _exact_input(scale, target)):
            continue
        if target.endswith(".input1") and cmds.nodeType(target_node) == "multiplyDivide":
            outputs = _data_edges(target_node)
            if (outputs and _fixed_attr(target_node + ".operation", 1)
                    and _fixed_attr(target_node + ".input2", [(1.0, 1.0, 1.0)])
                    and all(source in (target_node + ".output" + axis for axis in _AXES)
                            and _scale_divisor(dest) for source, dest in outputs)):
                signals.append(("divisor", scale, target))
                starts.append(target)
        elif target.endswith(".scale") and cmds.nodeType(target_node) == "transform":
            route = _coordinate_surface(target_node, master, scope, skin_sources)
            if route:
                signals.append(("surface", scale, target))
                starts.append(target)
                extensions.update(route)
    for leaf, follicle, source, dest, _ in _coordinate_follicles(master, scope, originals, owned):
        signals.append(("constraint", source, dest))
        starts.append(dest)
        extensions.update((leaf, follicle))
    targets = _coordinate_targets(master, scope, originals, owned)
    extensions.update(_coordinate_graph_nodes(scope, targets))
    if not signals and not targets:
        return None
    if not _scale_signal_scope(starts + [entry[3] for entry in targets], master, scope, extensions, owned):
        return None
    for _, _, target in signals:
        _local_node(_plug_node(target))
        if cmds.getAttr(target, lock=True):
            return None
    for target, *_ in targets:
        _local_node(_plug_node(target))
    return signals, targets


def _coordinate_matrix_inputs(group, target_frame):
    # Maya uses row vectors. Convert the wrapper's world delta to the
    # target-parent frame, preserving the target's editable local channels.
    return (target_frame + ".worldMatrix[0]", _parent(group) + ".worldInverseMatrix[0]",
            group + ".worldMatrix[0]", target_frame + ".worldInverseMatrix[0]")


def _coordinate_manifest(scope, plan, utilities):
    signals, targets = plan
    return {
        "scope": cmds.ls(scope, uuid=True)[0],
        "signals": sorted([route, _coordinate_identity(source), _coordinate_identity(target)]
                          for route, source, target in signals),
        "targets": sorted([_coordinate_identity(offset), cmds.ls(frame, uuid=True)[0],
                           _coordinate_identity(source), _coordinate_identity(dest)]
                          for offset, frame, source, dest, _ in targets),
        "utilities": [cmds.ls(node, uuid=True)[0] for node in utilities],
    }


def _create_coordinates(plan, driver, group, scope, prefix, create):
    signals, targets = plan
    utilities = []
    relays = {}
    for _, source, target in signals:
        identity = _coordinate_identity(source)
        if identity not in relays:
            relay = create("multiplyDivide", prefix + "_coordinateScale#")
            cmds.connectAttr(source, relay + ".input1")
            for axis in _AXES:
                cmds.connectAttr(driver, relay + ".input2" + axis)
            relays[identity] = relay
            utilities.append(relay)
        cmds.disconnectAttr(source, target)
        cmds.connectAttr(relays[identity] + ".output", target)
    for target, frame, *_ in targets:
        relay = create("multMatrix", prefix + "_coordinateFrame#")
        for index, source in enumerate(_coordinate_matrix_inputs(group, frame)):
            cmds.connectAttr(source, "{}.matrixIn[{}]".format(relay, index))
        cmds.connectAttr(relay + ".matrixSum", target)
        utilities.append(relay)
    cmds.addAttr(group, longName=_COORDINATE_PLAN, dataType="string")
    cmds.setAttr(group + "." + _COORDINATE_PLAN,
                 json.dumps(_coordinate_manifest(scope, plan, utilities)), type="string", lock=True)
    return utilities


def _identity_node(identity):
    nodes = cmds.ls(identity, long=True, allPaths=True) or []
    if len(nodes) != 1:
        raise ValueError("Ambiguous Rig Scale ownership node.")
    return nodes[0]


def _identity_plug(identity):
    node, attr = identity.split(".", 1)
    return _identity_node(node) + "." + attr


def _owned_coordinates(group, driver, master, explicit_scope):
    plug = group + "." + _COORDINATE_PLAN
    try:
        if not cmds.getAttr(plug, lock=True) or _incoming(plug):
            return None
        manifest = json.loads(cmds.getAttr(plug))
        scope = _identity_node(manifest["scope"])
        if (not _is_local_dag(scope) or not _inside(master, scope)
                or (explicit_scope and explicit_scope != scope)
                or cmds.getAttr(group + "." + _ATTACHMENT_COUNT) != 0
                or cmds.getAttr(group + "." + _ATTACHMENTS, multiIndices=True)
                or any(cmds.objExists(group + "." + attr) for attr in
                       (_SCALE_SIGNALS, _SKIN_BRANCHES, _SKIN_BRANCH_COUNT))):
            return None
        utilities = [_identity_node(identity) for identity in manifest["utilities"]]
        utility_plug = group + "." + _UTILITIES
        if (not utilities or len(utilities) != len(set(utilities))
                or cmds.getAttr(utility_plug, multiIndices=True) != list(range(len(utilities)))
                or not all(cmds.isConnected(node + ".message", "{}[{}]".format(utility_plug, index))
                           for index, node in enumerate(utilities))):
            return None
        originals = {}
        relay_outputs = {}
        for _, original, destination in manifest["signals"]:
            source = _identity_plug(original)
            target = _identity_plug(destination)
            if destination in originals:
                return None
            originals[destination] = (target, source)
            relay = _source_node(target)
            if relay not in utilities or cmds.nodeType(relay) != "multiplyDivide":
                return None
            expected = [(source, relay + ".input1")] + [
                (driver, relay + ".input2" + axis) for axis in _AXES]
            if (not _fixed_attr(relay + ".operation", 1)
                    or len(_data_edges(relay, incoming=True)) != len(expected)
                    or not all(_exact_input(a, b) for a, b in expected)):
                return None
            relay_outputs.setdefault(relay, []).append((relay + ".output", target))
        for offset, frame, _, _ in manifest["targets"]:
            target = _identity_plug(offset)
            if offset in originals:
                return None
            originals[offset] = (target, None)
            relay = _source_node(target)
            if relay not in utilities or relay in relay_outputs or cmds.nodeType(relay) != "multMatrix":
                return None
            if (cmds.getAttr(relay + ".matrixIn", multiIndices=True) != [0, 1, 2, 3]
                    or len(_data_edges(relay, incoming=True)) != 4
                    or not all(cmds.isConnected(source, "{}.matrixIn[{}]".format(relay, index))
                               for index, source in enumerate(
                                   _coordinate_matrix_inputs(group, _identity_node(frame))))):
                return None
            relay_outputs[relay] = [(relay + ".matrixSum", target)]
        if set(relay_outputs) != set(utilities) or not all(
                _exact_connections(node, outputs) for node, outputs in relay_outputs.items()):
            return None
        scale_outputs = [group + ".scale" + axis for axis in _AXES]
        world_outputs = []
        for relay in utilities:
            if cmds.nodeType(relay) == "multiplyDivide":
                scale_outputs.extend(relay + ".input2" + axis for axis in _AXES)
            else:
                world_outputs.append((group + ".worldMatrix[0]", relay + ".matrixIn[2]"))
        neutral = ("translate", "rotate", "shear", "rotatePivot", "rotatePivotTranslate",
                   "scalePivot", "scalePivotTranslate", "rotateAxis")
        if (not _is_local_dag(group) or not _parent(group)
                or (cmds.listRelatives(group, children=True, fullPath=True) or []) != [master]
                or not _fixed_attr(group + ".inheritsTransform", True)
                or not all(_fixed_attr(group + "." + attr, [(0.0, 0.0, 0.0)]) for attr in neutral)
                or _incoming(group + ".offsetParentMatrix") or not _identity_matrix(group + ".offsetParentMatrix")
                or not _exact_connections(group, world_outputs)
                or len(_outgoing(driver)) != len(scale_outputs)
                or not all(_exact_input(driver, target) for target in scale_outputs)):
            return None
        plan = _coordinate_plan(master, scope, group, originals, set(utilities))
        if not plan or _coordinate_manifest(scope, plan, utilities) != manifest:
            return None
        return [group] + utilities, [], len(plan[0]), 0, scope
    except (_Unsupported, AttributeError, IndexError, KeyError, RuntimeError, TypeError, ValueError):
        return None


_SPLINE_DAG_TYPES = _SCALE_SIGNAL_DAG_TYPES | {
    "baseLattice", "clusterHandle", "deformBend", "lattice",
}
_SPLINE_PROCESSORS = _SCALE_SIGNAL_PROCESSORS | {
    "blendShape", "blendWeighted", "cluster", "createColorSet", "ffd",
    "nonLinear", "polyMapDel", "polySeparate", "tweak",
}
_SPLINE_UTILITIES = ("multiplyDivide", "multMatrix", "multMatrix", "transformGeometry",
                     "transformGeometry", "decomposeMatrix", "plusMinusAverage", "multiplyDivide")


def _spline_container(branch, master):
    if (cmds.nodeType(branch) != "transform" or not _is_local_dag(branch)
            or not _fixed_attr(branch + ".inheritsTransform", True)
            or _incoming(branch + ".offsetParentMatrix") or not _identity_matrix(branch + ".offsetParentMatrix")
            or not _fixed_attr(branch + ".scale", [(1.0, 1.0, 1.0)])
            or any(_incoming(branch + ".scale" + axis) for axis in _AXES)):
        return False
    roots = cmds.listRelatives(branch, children=True, fullPath=True, type="joint") or []
    if len(roots) != 1 or any(_incoming(roots[0] + "." + attr + axis)
                             for attr in ("translate", "rotate", "scale") for axis in ("", *_AXES)):
        return False
    return _spline_constraint_target(branch, master) is not None


def _spline_constraint_target(driven, master):
    constraint = _source_node(driven + ".translateX")
    if (not constraint or cmds.nodeType(constraint) != "parentConstraint"
            or _parent(constraint) != driven or _path(constraint).isInstanced()
            or cmds.getAttr(constraint + ".target", multiIndices=True) != [0]
            or not _exact_input(driven + ".parentInverseMatrix[0]", constraint + ".constraintParentInverseMatrix")
            or not all(_exact_input(constraint + ".constraint" + attr.title() + axis, driven + "." + attr + axis)
                       for attr in ("translate", "rotate") for axis in _AXES)):
        return None
    prefix = constraint + ".target[0].target"
    target = _source_node(prefix + "Translate")
    target_channels = (("translate", "Translate"), ("rotate", "Rotate"), ("scale", "Scale"),
                       ("rotateOrder", "RotateOrder"), ("rotatePivot", "RotatePivot"),
                       ("rotatePivotTranslate", "RotateTranslate"))
    expected = [(target + "." + name, prefix + destination)
                for name, destination in target_channels] if target else []
    weight = _input(prefix + "Weight")
    if (not target or not _inside(target, master) or _path(target).isInstanced()
            or _plug_node(weight) != constraint or not _fixed_attr(weight, 1.0)
            or not _exact_input(target + ".parentMatrix[0]", prefix + "ParentMatrix")
            or not all(_exact_input(a, b) for a, b in expected)):
        return None
    return target


def _spline_volume(quotient, joints):
    visited = set()
    found = set()
    pending = [(quotient, 0)]
    while pending:
        node, depth = pending.pop()
        if node in visited or depth > 3:
            return False
        visited.add(node)
        for source, target in _data_edges(node):
            if not source.endswith(".outputX"):
                return False
            other = _plug_node(target)
            attr = target.split(".", 1)[1]
            if other in joints and attr in (("scaleX",) if depth == 0 else ("scaleY", "scaleZ")):
                found.add((other, attr))
                continue
            # The bounded volume path transforms only this ratio. Any
            # authored additional input must be a static scalar.
            allowed = ((3, "input1X"), (2, "input2X"), (1, "input1X"))
            if depth >= len(allowed) or not other or cmds.nodeType(other) != "multiplyDivide":
                return False
            operation, destination = allowed[depth]
            if (attr != destination or not _fixed_attr(other + ".operation", operation)
                    or len(_data_edges(other, incoming=True)) != 1):
                return False
            constant = other + (".input2X" if destination == "input1X" else ".input1X")
            if _incoming(constant) or not math.isfinite(cmds.getAttr(constant)):
                return False
            pending.append((other, depth + 1))
    return (all((joint, "scaleX") in found for joint in joints)
            and (len(visited) == 1 or all((joint, "scale" + axis) in found for joint in joints for axis in "YZ")))


def _spline_divisor(branch, master, original_rest=None):
    plans = []
    handles = cmds.listRelatives(branch, allDescendents=True, fullPath=True, type="ikHandle") or []
    for handle in handles:
        if cmds.ikHandle(handle, query=True, solver=True) != "ikSplineSolver":
            continue
        curve_plug = _input(handle + ".inCurve")
        curve = _plug_node(curve_plug)
        if (not curve or not _inside(curve, branch) or cmds.nodeType(curve) != "nurbsCurve"
                or not curve_plug.endswith(".worldSpace[0]") or _path(curve).isInstanced()):
            return None
        cursor = _parent(curve)
        while cursor != branch and _fixed_attr(cursor + ".inheritsTransform", True):
            cursor = _parent(cursor)
        if cursor == branch or not _fixed_attr(cursor + ".inheritsTransform", False):
            return None
        source = _input(curve + ".create")
        skin = _plug_node(source)
        if not skin or cmds.nodeType(skin) != "skinCluster" or not source.endswith(".outputGeometry[0]"):
            return None
        influences = _spline_influences(skin)
        if (not influences or not all(_inside(joint, master) or (
                _inside(joint, branch) and _spline_constraint_target(joint, master))
                for joint in influences)):
            return None
        uses = _outgoing(curve_plug)
        infos = [p for p in uses if p.endswith(".inputCurve") and cmds.nodeType(_plug_node(p)) == "curveInfo"]
        if len(uses) != 2 or len(infos) != 1 or not _exact_input(curve_plug, handle + ".inCurve"):
            return None
        quotients = _outgoing(_plug_node(infos[0]) + ".arcLength")
        if len(quotients) != 1 or not quotients[0].endswith(".input1X"):
            return None
        quotient = _plug_node(quotients[0])
        if cmds.nodeType(quotient) != "multiplyDivide" or not _fixed_attr(quotient + ".operation", 2):
            return None
        joints = {_plug_node(name + ".message") for name in cmds.ikHandle(handle, query=True, jointList=True) or []}
        if (not joints or not all(node and _inside(node, branch) for node in joints)
                or joints.intersection(influences) or not _spline_volume(quotient, joints)):
            return None
        divisor = quotient + ".input2X"
        if original_rest:
            if _coordinate_identity(divisor) != original_rest[0]:
                return None
            rest = original_rest[1]
        else:
            if _incoming(divisor) or cmds.getAttr(divisor, lock=True):
                return None
            rest = cmds.getAttr(divisor)
        if not math.isfinite(rest) or rest <= 0:
            return None
        plans.append((divisor, rest))
    return plans[0] if len(plans) == 1 else None


def _spline_scope(starts, scope, owned):
    pending = list(starts)
    seen = set()
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        if len(seen) > _SCALE_SIGNAL_GRAPH_LIMIT:
            return False
        kind = cmds.nodeType(node)
        if node.startswith("|"):
            if not _inside(node, scope) or _path(node).isInstanced() or kind not in _SPLINE_DAG_TYPES:
                return False
            pending.extend(cmds.listRelatives(node, children=True, fullPath=True) or [])
        elif kind not in _SPLINE_PROCESSORS:
            return False
        for source, target in _data_edges(node, owned=owned):
            if kind == "blendShape" and _shape_editor_edge(source, target):
                continue
            downstream = _plug_node(target)
            if not downstream:
                return False
            pending.append(downstream)
    return True


def _spline_driven_channel(node, attr):
    children = cmds.attributeQuery(attr, node=node, listChildren=True) or []
    return any(_incoming(node + "." + channel) for channel in (attr, *children))


def _spline_static_frame(node, scope, driven_translate=None):
    frame = om.MMatrix()
    while node != scope:
        if (not _is_local_dag(node) or cmds.nodeType(node) != "transform"
                or not _fixed_attr(node + ".inheritsTransform", True)
                or _incoming(node + ".offsetParentMatrix") or not _identity_matrix(node + ".offsetParentMatrix")
                or any(_spline_driven_channel(node, attr)
                       for attr in ("translate", "rotate", "scale", "shear", "rotateAxis", "rotateOrder",
                                    "rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate")
                       if node != driven_translate or attr != "translate")):
            return None
        local = om.MMatrix(cmds.getAttr(node + ".matrix"))
        if node == driven_translate:
            local = om.MMatrix([value if index not in (12, 13, 14) else 0.0
                                for index, value in enumerate(local)])
        frame = frame * local
        node = _parent(node)
        if not node:
            return None
    return frame


def _spline_bind(skin, scope, branch, output, owned_output, shape=None):
    if not shape:
        geometry = cmds.skinCluster(skin, query=True, geometry=True) or []
        shape = _plug_node(geometry[0] + ".message") if len(geometry) == 1 else None
    if (not shape or not _inside(shape, output) or cmds.nodeType(shape) != "mesh"
            or not all(_fixed_attr(skin + "." + attr, value)
                       for attr, value in (("envelope", 1.0), ("normalizeWeights", 1), ("skinningMethod", 0)))
            or _incoming(skin + ".geomMatrix")):
        return None
    frame = _spline_static_frame(_parent(shape), scope, owned_output)
    if frame is None or not frame.isEquivalent(om.MMatrix(cmds.getAttr(skin + ".geomMatrix")), 1e-7):
        return None
    joints = _spline_influences(skin)
    return shape if joints and all(_inside(joint, branch) for joint in joints) else None


def _spline_post_skin(shape):
    destination = shape + ".inMesh"
    visited = set()
    while len(visited) < 16:
        source = _input(destination)
        node = _plug_node(source)
        if not node or node in visited or not _exact_input(source, destination):
            return None
        visited.add(node)
        kind = cmds.nodeType(node)
        attr = source.split(".", 1)[1]
        if kind == "groupParts" and attr == "outputGeometry":
            destination = node + ".inputGeometry"
        elif kind in ("ffd", "tweak", "skinCluster"):
            output = re.fullmatch(r"outputGeometry\[(\d+)\]", attr)
            if not output:
                return None
            if kind == "skinCluster":
                return node
            if kind == "tweak" and (not _fixed_attr(node + ".relativeTweak", True)
                    or any(cmds.getAttr(node + "." + attr, multiIndices=True) or _incoming(node + "." + attr)
                           for attr in ("vlist", "plist"))):
                return None
            destination = "{}.input[{}].inputGeometry".format(node, output[1])
        else:
            return None
    return None


def _spline_influences(skin):
    indices = set(cmds.getAttr(skin + ".matrix", multiIndices=True) or [])
    bind_indices = set(cmds.getAttr(skin + ".bindPreMatrix", multiIndices=True) or [])
    if (not indices or not indices <= bind_indices
            or any(_incoming("{}.bindPreMatrix[{}]".format(skin, i)) for i in bind_indices)):
        return None
    if bind_indices != indices:
        # Maya can leave static bind matrices behind after removing influences.
        # They are harmless only if no vertex retains a weight at an inactive index.
        selection = om.MSelectionList().add(skin)
        weights = om.MFnDependencyNode(selection.getDependNode(0)).findPlug("weightList", False)
        for vertex in weights.getExistingArrayAttributeIndices():
            row = weights.elementByLogicalIndex(vertex).child(0)
            inactive = set(row.getExistingArrayAttributeIndices()) - indices
            if any(row.elementByLogicalIndex(i).asDouble() != 0.0 for i in inactive):
                return None
    joints = set()
    for index in indices:
        plug = "{}.matrix[{}]".format(skin, index)
        joint = _source_node(plug)
        if (not _is_local_dag(joint) or cmds.nodeType(joint) != "joint"
                or not _exact_input(joint + ".worldMatrix[0]", plug)):
            return None
        joints.add(joint)
    return joints if len(joints) == len(indices) else None


def _spline_target(mesh, master, branch, scope, owned, original_target):
    if original_target:
        skin_source, mesh_input, world, target = map(_identity_plug, original_target)
        if _plug_node(world) != mesh:
            return None
    else:
        world = mesh + ".worldMesh[0]"
        targets = _outgoing(world)
        if len(targets) != 1:
            return None
        target = targets[0]
        mesh_input = mesh + ".inMesh"
        skin_source = _input(mesh_input)
    blend = _plug_node(target)
    skin = _plug_node(skin_source)
    if (not skin or cmds.nodeType(skin) != "skinCluster" or not skin_source.endswith(".outputGeometry[0]")
            or not blend or cmds.nodeType(blend) != "blendShape" or not _fixed_attr(blend + ".origin", 1)
            or not re.fullmatch(r"inputTarget\[\d+\]\.inputTargetGroup\[\d+\]\.inputTargetItem\[6000\]\.inputGeomTarget",
                                target.split(".", 1)[1])
            or not _is_local_dag(mesh) or _inside(mesh, master) or _inside(mesh, branch)
            or _spline_static_frame(_parent(mesh), scope) is None):
        return None
    joints = _spline_influences(skin)
    if (not joints or _incoming(skin + ".geomMatrix")
            or not all(_inside(joint, scope) and not _inside(joint, master) and not _inside(joint, branch)
                       for joint in joints)
            or (not original_target and (not _exact_input(skin_source, mesh_input) or not _exact_input(world, target)))
            or any(source.split(".", 1)[1].split("[", 1)[0] in ("outMesh", "worldMesh")
                   and not _exact_input(world, destination)
                   for source, destination in _data_edges(mesh, owned=owned))):
        return None
    _local_node(mesh)
    _local_node(blend)
    return skin_source, mesh_input, world, target


def _spline_plan(master, parent, scope, meshes, group=None, originals=None, owned=()):
    if not parent or parent != scope:
        return None
    siblings = cmds.listRelatives(group or parent, children=True, fullPath=True, type="transform") or []
    branches = [node for node in siblings if node != master and _spline_container(node, master)]
    if len(branches) != 1:
        return None
    branch = branches[0]
    divisor = _spline_divisor(branch, master, originals["rest"] if originals else None)
    if not divisor:
        return None
    target_mesh = _plug_node(_identity_plug(originals["target"][2])) if originals else None
    candidates = [(mesh, _spline_target(mesh, master, branch, scope, owned, originals["target"] if originals else None))
                  for mesh in meshes
                  if not originals or mesh == target_mesh]
    targets = [(mesh, pair) for mesh, pair in candidates if pair]
    if len(targets) != 1:
        return None
    mouth, pair = targets[0]
    outputs = [mesh for mesh in meshes if mesh != mouth]
    if not outputs:
        return None
    output = _parent(outputs[0])
    while output != parent and not all(_inside(mesh, output) for mesh in outputs):
        output = _parent(output)
    if (output == parent or _inside(master, output) or _inside(branch, output) or _inside(mouth, output)
            or _spline_static_frame(output, parent, output if originals else None) != om.MMatrix.kIdentity
            or _spline_static_frame(_parent(output), parent) != om.MMatrix.kIdentity
            or (not originals and not _fixed_attr(output + ".translate", [(0.0, 0.0, 0.0)]))):
        return None
    _local_node(output)
    bindings = {}
    covered = set()
    blends = {}
    for mesh in outputs:
        history = cmds.listHistory(mesh, pruneDagObjects=True) or []
        for skin in cmds.ls(history, type="skinCluster") or []:
            if skin not in bindings:
                bindings[skin] = _spline_bind(skin, scope, branch, output, output if originals else None)
            if bindings[skin] == mesh:
                covered.add(mesh)
        if mesh not in covered:
            skin = _spline_post_skin(mesh)
            if skin and _spline_bind(skin, scope, branch, output, output if originals else None, shape=mesh):
                covered.add(mesh)
        if mesh not in covered:
            source = _input(mesh + ".inMesh")
            blend = _plug_node(source)
            if not blend or cmds.nodeType(blend) != "blendShape" or not source.endswith(".outputGeometry[0]"):
                return None
            targets = [(a, b) for a, b in _data_edges(blend, incoming=True) if b.endswith(".inputGeomTarget")]
            inputs = []
            for source_plug, target_plug in targets:
                node = _plug_node(source_plug)
                if (not node or not _inside(node, output) or _path(node).isInstanced()
                        or not target_plug.split(".", 1)[1].startswith("inputTarget[0].")
                        or not _exact_input(node + ".worldMesh[0]", target_plug)):
                    return None
                inputs.append(node)
            if not inputs:
                return None
            blends[mesh] = inputs
    if any(not set(inputs) <= covered for inputs in blends.values()) or not _spline_scope(
            (master, branch, output, mouth, _plug_node(divisor[0]), _plug_node(pair[0]), _plug_node(pair[3])),
            scope, owned):
        return None
    _local_node(_plug_node(divisor[0]))
    return {"branch": branch, "output": output, "rest": divisor, "target": pair}


def _spline_manifest(scope, plan, utilities):
    divisor, rest = plan["rest"]
    return {"scope": cmds.ls(scope, uuid=True)[0], "branch": cmds.ls(plan["branch"], uuid=True)[0],
            "output": cmds.ls(plan["output"], uuid=True)[0], "rest": [_coordinate_identity(divisor), rest],
            "target": [_coordinate_identity(plug) for plug in plan["target"]],
            "utilities": [cmds.ls(node, uuid=True)[0] for node in utilities]}


def _spline_wires(plan, group, driver, utilities):
    rest, forward, inverse, display, blend, decomposition, delta, translation = utilities
    divisor, length = plan["rest"]
    skin, mesh, world, target = plan["target"]
    parent = _parent(group)
    frame = _parent(_plug_node(world))
    common = (frame + ".worldMatrix[0]", frame + ".worldInverseMatrix[0]")
    matrices = (
        (forward, (common[0], parent + ".worldInverseMatrix[0]", group + ".worldMatrix[0]", common[1])),
        (inverse, (common[0], group + ".worldInverseMatrix[0]", parent + ".worldMatrix[0]", common[1])),
    )
    links = [(source, "{}.matrixIn[{}]".format(node, index))
             for node, sources in matrices for index, source in enumerate(sources)]
    # A world translation present in skin matrices also appears in the
    # inherited output frame. The bind-frame proof above makes (s-1)*t
    # the common local correction, including when the parent rotates.
    links.extend(((driver, rest + ".input2X"), (rest + ".outputX", divisor),
                  (skin, display + ".inputGeometry"), (forward + ".matrixSum", display + ".transform"),
                  (display + ".outputGeometry", mesh), (world, blend + ".inputGeometry"),
                  (inverse + ".matrixSum", blend + ".transform"), (blend + ".outputGeometry", target),
                  (parent + ".worldMatrix[0]", decomposition + ".inputMatrix"),
                  (driver, delta + ".input1D[0]"), (decomposition + ".outputTranslate", translation + ".input1"),
                  (translation + ".output", plan["output"] + ".translate")))
    links.extend((delta + ".output1D", translation + ".input2" + axis) for axis in _AXES)
    constants = {rest + ".operation": 1, rest + ".input1X": length, delta + ".operation": 2,
                 delta + ".input1D[1]": 1.0, translation + ".operation": 1,
                 display + ".invertTransform": False, blend + ".invertTransform": False}
    return links, constants


def _create_spline(plan, driver, group, scope, prefix, create):
    utilities = [create(kind, prefix + "_spline" + kind + "#") for kind in _SPLINE_UTILITIES]
    links, constants = _spline_wires(plan, group, driver, utilities)
    skin, mesh, world, target = plan["target"]
    cmds.disconnectAttr(skin, mesh)
    cmds.disconnectAttr(world, target)
    for plug, value in constants.items():
        cmds.setAttr(plug, value)
    for source, destination in links:
        cmds.connectAttr(source, destination)
    cmds.addAttr(group, longName=_SPLINE_PLAN, dataType="string")
    cmds.setAttr(group + "." + _SPLINE_PLAN, json.dumps(_spline_manifest(scope, plan, utilities)),
                 type="string", lock=True)
    return utilities


def _owned_spline(group, driver, master, explicit_scope):
    try:
        manifest_plug = group + "." + _SPLINE_PLAN
        if not cmds.getAttr(manifest_plug, lock=True) or _incoming(manifest_plug):
            return None
        manifest = json.loads(cmds.getAttr(manifest_plug))
        scope, branch, output = (_identity_node(manifest[key]) for key in ("scope", "branch", "output"))
        utilities = [_identity_node(identity) for identity in manifest["utilities"]]
        if (scope != _parent(group) or (explicit_scope and explicit_scope != scope)
                or not _is_local_dag(group) or not _fixed_attr(group + ".inheritsTransform", True)
                or set(cmds.listRelatives(group, children=True, fullPath=True) or []) != {master, branch}
                or len(set(utilities)) != len(_SPLINE_UTILITIES)
                or tuple(map(cmds.nodeType, utilities)) != _SPLINE_UTILITIES
                or not _fixed_attr(group + "." + _ATTACHMENT_COUNT, 0)
                or cmds.getAttr(group + "." + _ATTACHMENTS, multiIndices=True)
                or not _fixed_attr(group + "." + _SKIN_BRANCH_COUNT, 1)
                or cmds.getAttr(group + "." + _SKIN_BRANCHES, multiIndices=True) != [0]
                or not _exact_input(branch + ".message", group + "." + _SKIN_BRANCHES + "[0]")
                or cmds.getAttr(group + "." + _UTILITIES, multiIndices=True) != list(range(len(utilities)))
                or not all(_exact_input(node + ".message", "{}.{}[{}]".format(group, _UTILITIES, index))
                           for index, node in enumerate(utilities))):
            return None
        neutral = ("translate", "rotate", "shear", "rotatePivot", "rotatePivotTranslate",
                   "scalePivot", "scalePivotTranslate", "rotateAxis")
        if (not all(_fixed_attr(group + "." + attr, [(0.0, 0.0, 0.0)]) for attr in neutral)
                or _incoming(group + ".offsetParentMatrix") or not _identity_matrix(group + ".offsetParentMatrix")):
            return None
        expected = {"branch": branch, "output": output,
                    "rest": (_identity_plug(manifest["rest"][0]), manifest["rest"][1]),
                    "target": tuple(map(_identity_plug, manifest["target"]))}
        links, constants = _spline_wires(expected, group, driver, utilities)
        scale_links = [(driver, group + ".scale" + axis) for axis in _AXES]
        if (not all(_fixed_attr(plug, value) for plug, value in constants.items())
                or not all(_exact_input(source, target) for source, target in links + scale_links)
                or len(_outgoing(driver)) != sum(source == driver for source, _ in links + scale_links)
                or not _exact_connections(group, [(a, b) for a, b in links if _plug_node(a) == group])
                or any(len(_data_edges(node, incoming=True)) != sum(_plug_node(b) == node for _, b in links)
                       or not _exact_connections(node, [(a, b) for a, b in links if _plug_node(a) == node])
                       for node in utilities)):
            return None
        meshes = [shape for shape in cmds.listRelatives(scope, allDescendents=True, fullPath=True, type="mesh") or []
                  if not cmds.getAttr(shape + ".intermediateObject")]
        plan = _spline_plan(master, scope, scope, meshes, group, manifest, set(utilities))
        if not plan or _spline_manifest(scope, plan, utilities) != manifest:
            return None
        return [group] + utilities, [branch], 1, 0, scope
    except (_Unsupported, AttributeError, IndexError, KeyError, RuntimeError, TypeError, ValueError):
        return None


def _owned_scale_signals(parent, driver, master, utility_index):
    if not cmds.attributeQuery(_SCALE_SIGNALS, node=parent, exists=True):
        return None
    try:
        scope = _source_node(parent + "." + _SCALE_SIGNAL_SCOPE)
        if not scope or not _inside(master, scope):
            return None
        manifest = json.loads(cmds.getAttr(parent + "." + _SCALE_SIGNALS))
        if not isinstance(manifest, dict) or not manifest or set(manifest) - set(_AXES):
            return None
        relay = _input("{}.{}[{}]".format(parent, _UTILITIES, utility_index)).split(".", 1)[0]
        if not relay or cmds.nodeType(relay) != "multiplyDivide":
            return None
        if (cmds.getAttr(relay + ".operation") != 1 or _incoming(relay + ".operation")
                or cmds.connectionInfo(relay + ".output", isExactSource=True)):
            return None
        destinations = []
        for axis, targets in manifest.items():
            if not cmds.isConnected(master + ".scale" + axis, relay + ".input1" + axis):
                return None
            if not cmds.isConnected(driver, relay + ".input2" + axis):
                return None
            output = _outgoing(relay + ".output" + axis)
            if (not output or not all(_scale_divisor(plug) for plug in output)
                    or sorted(_plug_identity(plug) for plug in output) != targets):
                return None
            destinations.extend(output)
        if any(_outgoing(relay + ".output" + axis) for axis in _AXES if axis not in manifest):
            return None
        if not _scale_signal_scope(destinations, master, scope):
            return None
    except (IndexError, RuntimeError, TypeError, ValueError):
        return None
    return relay, len(destinations)


def _owned_mesh_manifest(group, master, count):
    plug = group + "." + _MESH_ATTACHMENTS
    size = group + "." + _MESH_ATTACHMENT_COUNT
    if any(not cmds.objExists(attr) or not cmds.getAttr(attr, lock=True) or _incoming(attr)
           for attr in (plug, size)):
        return None
    try:
        manifest = json.loads(cmds.getAttr(plug))
        scope, = cmds.ls(manifest["scope"], long=True, allPaths=True)
        targets = manifest["targets"]
        if (not _inside(master, scope) or _path(scope).isInstanced()
                or not targets or len(targets) != cmds.getAttr(size)
                or targets.keys() - {str(index) for index in range(count)}
                or any(not isinstance(entry, list) or len(entry) != 5 for entry in targets.values())):
            return None
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        return None
    return scope, targets


def _owned_mesh_attachment(entry, destination, utilities, master, scope, skin_sources, owned_link):
    matrix, decomposition, ratio = utilities
    try:
        paths = [cmds.ls(identity, long=True, allPaths=True) or [] for identity in entry[:4]]
        if any(len(matches) != 1 for matches in paths):
            return False
        target, follicle, surface, source = (matches[0] for matches in paths)
        if (target != destination or not follicle or not surface or not source
                or cmds.nodeType(follicle) != "follicle" or _parent(follicle) != target
                or not any(not cmds.getAttr(mesh + ".intermediateObject")
                           for mesh in cmds.listRelatives(target, allDescendents=True,
                                                          fullPath=True, type="mesh") or [])):
            return False
        if _mesh_attachment_source(follicle, target, master, scope, skin_sources, owned_link) != (source, surface):
            return False
        if (cmds.nodeType(matrix) != "multMatrix" or cmds.nodeType(decomposition) != "decomposeMatrix"
                or cmds.nodeType(ratio) != "multiplyDivide"
                or cmds.getAttr(ratio + ".operation") != 1 or _incoming(ratio + ".operation")
                or _incoming(ratio + ".input2")
                or list(cmds.getAttr(ratio + ".input2")[0]) != entry[4]
                or cmds.getAttr(matrix + ".matrixIn", multiIndices=True) != [0]
                or not cmds.isConnected(source + ".worldMatrix[0]", matrix + ".matrixIn[0]")):
            return False
        # Each utility has its owned message edge and exactly the data edges
        # verified by the caller. Refuse new consumers of its scaled values.
        return all(len(_outgoing(node)) == edges
                   for node, edges in zip(utilities, (2, 4, 4)))
    except (RuntimeError, TypeError, ValueError):
        return False


def _static_surface_scope(scope, group):
    # Only the selected master provides global position for this route. An
    # animated outer frame can also feed native world-space deformers.
    return (_parent(group) == scope and _is_local_dag(scope) and not _parent(scope)
            and _fixed_attr(scope + ".inheritsTransform", True)
            and _identity_matrix(scope + ".matrix")
            and _identity_matrix(scope + ".offsetParentMatrix")
            and not any(_spline_driven_channel(scope, attr) for attr in (
                "translate", "rotate", "scale", "shear", "rotateOrder", "rotateAxis",
                "rotatePivot", "rotatePivotTranslate", "scalePivot", "scalePivotTranslate", "offsetParentMatrix")))


def _static_surface_leaf_scope(leaf, scope):
    # DAG inheritance can carry the scaled frame past a direct follicle
    # connection. Every reached processor must lead back to this character.
    processors = _SCALE_SIGNAL_PROCESSORS | {
        "addDL", "multDL", "decomposeMatrix", "fourByFourMatrix", "multMatrix",
    }
    dag_types = _SCALE_SIGNAL_DAG_TYPES | {"follicle"}
    pending, seen, dag, upstream = [leaf], set(), set(), {}
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        if len(seen) > _SCALE_SIGNAL_GRAPH_LIMIT:
            return False
        kind = cmds.nodeType(node)
        if node.startswith("|"):
            if not _inside(node, scope) or not _is_local_dag(node) or kind not in dag_types:
                return False
            dag.add(node)
            pending.extend(cmds.listRelatives(node, children=True, fullPath=True) or [])
        elif kind not in processors or cmds.referenceQuery(node, isNodeReferenced=True):
            return False
        for source, plug in _data_edges(node):
            target = _plug_node(plug)
            if not target:
                return False
            # A joint's stored bind pose is independent of its evaluated matrix.
            if (kind == "joint" and cmds.nodeType(target) == "dagPose"
                    and _coordinate_identity(source).endswith(".bindPose") and not _incoming(source)
                    and re.fullmatch(r"worldMatrix\[\d+\]", _coordinate_identity(plug).split(".", 1)[1])):
                continue
            upstream.setdefault(target, set()).add(node)
            pending.append(target)
    pending = list(dag)
    while pending:
        for node in upstream.get(pending.pop(), ()):
            if node not in dag:
                dag.add(node)
                pending.append(node)
    return seen == dag


def _static_surface_plan(shape, master, scope, relays=()):
    transform = _parent(shape)
    frame = _parent(transform) if transform else None
    if (not all(map(_is_local_dag, (shape, transform, frame)))
            or cmds.nodeType(shape) != "nurbsSurface" or cmds.nodeType(transform) != "transform"
            or not _inside(transform, scope) or _inside(transform, master)
            or (cmds.listRelatives(transform, children=True, fullPath=True) or []) != [shape]
            or not _fixed_attr(transform + ".inheritsTransform", True)
            or not _fixed_attr(shape + ".intermediateObject", False)
            or _data_edges(shape, incoming=True)
            or _spline_static_frame(frame, scope) is None):
        return None
    offset = transform + ".offsetParentMatrix"
    matrix = shape + ".worldMatrix[0]"
    input_links = []
    output_links = []
    if relays:
        forward, original = relays
        input_links = [(forward + ".matrixSum", offset)]
        output_links = [(transform + ".matrix", original + ".matrixIn[0]")]
    elif not cmds.getAttr(offset, settable=True) or not _identity_matrix(offset):
        return None
    if (not _exact_connections(transform, output_links)
            or len(_data_edges(transform, incoming=True)) != len(input_links)
            or not all(_exact_input(a, b) for a, b in input_links)):
        return None
    edges = _data_edges(shape)
    targets = [target for source, target in edges
               if source.split(".", 1)[1] == "local" and target.endswith(".inputSurface")]
    if len(targets) != 1:
        return None
    follicle = _plug_node(targets[0])
    leaf = _parent(follicle) if follicle else None
    if (not all(map(_is_local_dag, (follicle, leaf))) or cmds.nodeType(follicle) != "follicle"
            or cmds.nodeType(leaf) != "transform" or not _inside(leaf, master)
            or not _fixed_attr(leaf + ".inheritsTransform", True)
            or _incoming(follicle + ".inputMesh")
            or not _exact_connections(follicle, [(follicle + ".outTranslate", leaf + ".translate"),
                                                  (follicle + ".outRotate", leaf + ".rotate")])
            or not _static_surface_leaf_scope(leaf, scope)):
        return None
    destination = follicle + ".inputWorldMatrix"
    expected = [(shape + ".local", follicle + ".inputSurface")]
    if not relays:
        expected.append((matrix, destination))
        _local_node(transform)
        _local_node(follicle)
        if cmds.getAttr(destination, lock=True):
            return None
    return (shape, transform, frame, follicle) if _exact_connections(shape, expected) else None


def _static_surface_wires(plan, group, relays):
    _, transform, frame, follicle = plan
    forward, original = relays
    links = [(source, "{}.matrixIn[{}]".format(forward, index)) for index, source in enumerate(
        _coordinate_matrix_inputs(group, frame))]
    links.extend(((transform + ".matrix", original + ".matrixIn[0]"),
                  (frame + ".worldMatrix[0]", original + ".matrixIn[1]"),
                  (forward + ".matrixSum", transform + ".offsetParentMatrix"),
                  (original + ".matrixSum", follicle + ".inputWorldMatrix")))
    return links


def _create_static_surface(plan, group, scope, attachments, utilities, prefix, create):
    relays = [create("multMatrix", prefix + suffix + "#")
              for suffix in ("_surfaceDisplayFrame", "_surfaceOriginalFrame")]
    shape, _, _, follicle = plan
    cmds.disconnectAttr(shape + ".worldMatrix[0]", follicle + ".inputWorldMatrix")
    for source, destination in _static_surface_wires(plan, group, relays):
        cmds.connectAttr(source, destination)
    manifest = {key: cmds.ls(node, uuid=True)[0] for key, node in (
        ("scope", scope), ("shape", shape), ("follicle", follicle))}
    manifest["relays"] = [cmds.ls(node, uuid=True)[0] for node in relays]
    manifest["attachments"] = [
        {"destination": cmds.ls(attachment["transform"], uuid=True)[0],
         "nodes": [cmds.ls(node, uuid=True)[0] for node in utilities[index * 3:index * 3 + 3]],
         "source": _coordinate_identity(_input(utilities[index * 3] + ".matrixIn[0]")),
         "ratios": list(cmds.getAttr(utilities[index * 3 + 2] + ".input2")[0])}
        for index, attachment in enumerate(attachments)
    ]
    cmds.addAttr(group, longName=_STATIC_SURFACE_PLAN, dataType="string")
    cmds.setAttr(group + "." + _STATIC_SURFACE_PLAN, json.dumps(manifest), type="string", lock=True)
    return relays


def _owned_static_surface_attachments(group, master, scope, entries, utilities):
    for index, entry in enumerate(entries):
        destination = _identity_node(entry["destination"])
        matrix, decomposition, ratio = map(_identity_node, entry["nodes"])
        source = _identity_plug(entry["source"])
        constants = entry["ratios"]
        parent = _parent(destination) if cmds.getAttr(destination + ".inheritsTransform") else None
        if ([matrix, decomposition, ratio] != utilities[index * 3:index * 3 + 3]
                or tuple(map(cmds.nodeType, (matrix, decomposition, ratio))) != (
                    "multMatrix", "decomposeMatrix", "multiplyDivide")
                or any(cmds.referenceQuery(node, isNodeReferenced=True) for node in (matrix, decomposition, ratio))
                or not _is_local_dag(destination) or not _inside(destination, scope)
                or _inside(destination, master) or not _inside(_plug_node(source), master)
                or _coordinate_identity(_plug_node(source) + ".worldMatrix[0]") != entry["source"]
                or _incoming(destination + ".inheritsTransform")
                or not _exact_input(destination + ".message", "{}.{}[{}]".format(group, _ATTACHMENTS, index))
                or len(constants) != 3 or not all(math.isfinite(value) and value != 0 for value in constants)
                or not _fixed_attr(ratio + ".operation", 1)
                or not _fixed_attr(ratio + ".input2", [tuple(constants)])
                or not _fixed_attr(decomposition + ".inputRotateOrder", 0)):
            return False
        matrix_inputs = [(source, matrix + ".matrixIn[0]")]
        if parent:
            matrix_inputs.append((parent + ".worldInverseMatrix[0]", matrix + ".matrixIn[1]"))
        decomposition_input = (matrix + ".matrixSum", decomposition + ".inputMatrix")
        ratio_inputs = [(decomposition + ".outputScale" + axis, ratio + ".input1" + axis) for axis in _AXES]
        outputs = [(ratio + ".output" + axis, destination + ".scale" + axis) for axis in _AXES]
        if (cmds.getAttr(matrix + ".matrixIn", multiIndices=True) != list(range(len(matrix_inputs)))
                or not all(_exact_input(a, b) for a, b in matrix_inputs)
                or not _exact_connections(matrix, [decomposition_input])
                or not _exact_connections(decomposition, ratio_inputs)
                or not _exact_connections(ratio, outputs)
                or [len(_data_edges(node, incoming=True)) for node in (matrix, decomposition, ratio)]
                   != [len(matrix_inputs), 1, 3]):
            return False
    return True


def _owned_static_surface(group, driver, master, explicit_scope, attachments, utilities):
    manifest_plug = group + "." + _STATIC_SURFACE_PLAN
    if not cmds.getAttr(manifest_plug, lock=True) or _incoming(manifest_plug):
        return None
    keys = ("scope", "shape", "follicle")
    try:
        manifest = json.loads(cmds.getAttr(manifest_plug))
        if not isinstance(manifest, dict) or set(manifest) != {*keys, "relays", "attachments"}:
            return None
        relay_ids = manifest["relays"]
        if not isinstance(relay_ids, list) or len(relay_ids) != 2:
            return None
        node_ids = [manifest[key] for key in keys] + relay_ids
        if any(not isinstance(value, str) or str(uuid.UUID(value)) != value.lower() for value in node_ids):
            return None
        scope, shape, follicle, *owned_relays = map(_identity_node, node_ids)
    except (RuntimeError, TypeError, ValueError):
        return None
    if ((explicit_scope and explicit_scope != scope) or not _static_surface_scope(scope, group)
            or not _is_local_dag(group) or not _fixed_attr(group + ".inheritsTransform", True)
            or not _fixed_attr(group + "." + _OWNER, _STATIC_SURFACE_VERSION)
            or not cmds.getAttr(group + "." + _OWNER, lock=True)
            or not _exact_input(master + ".message", group + "." + _MASTER)
            or (cmds.listRelatives(group, children=True, fullPath=True) or []) != [master]
            or (cmds.getAttr(group + "." + _ATTACHMENTS, multiIndices=True) or []) != list(range(attachments))):
        return None
    utility = group + "." + _UTILITIES
    if cmds.getAttr(utility, multiIndices=True) != list(range(len(utilities) + 2)):
        return None
    relays = [_input("{}[{}]".format(utility, index)).split(".", 1)[0]
              for index in range(len(utilities), len(utilities) + 2)]
    if (not all(relays) or len(set(utilities + relays)) != len(utilities) + 2
            or owned_relays != relays
            or any(cmds.nodeType(node) != "multMatrix" or cmds.referenceQuery(node, isNodeReferenced=True)
                   for node in relays)
            or not all(_exact_input(node + ".message", "{}[{}]".format(utility, index))
                       for index, node in enumerate(utilities + relays))):
        return None
    entries = manifest["attachments"]
    if (not isinstance(entries, list) or len(entries) != attachments
            or not _owned_static_surface_attachments(group, master, scope, entries, utilities)):
        return None
    plan = _static_surface_plan(shape, master, scope, relays)
    if not plan or plan[-1] != follicle:
        return None
    links = _static_surface_wires(plan, group, relays)
    scales = [(driver, group + ".scale" + axis) for axis in _AXES]
    neutral = ("translate", "rotate", "shear", "rotatePivot", "rotatePivotTranslate",
               "scalePivot", "scalePivotTranslate", "rotateAxis")
    if (not all(_fixed_attr(group + "." + attr, [(0.0, 0.0, 0.0)]) for attr in neutral)
            or not _fixed_attr(group + ".rotateOrder", 0)
            or _incoming(group + ".offsetParentMatrix") or not _identity_matrix(group + ".offsetParentMatrix")
            or not all(_exact_input(source, dest) for source, dest in links + scales)
            or not _exact_connections(group, [(source, dest) for source, dest in links if _plug_node(source) == group])
            or len(_outgoing(driver)) != len(scales)):
        return None
    for node, count in zip(relays, (4, 2)):
        if (cmds.getAttr(node + ".matrixIn", multiIndices=True) != list(range(count))
                or len(_data_edges(node, incoming=True)) != count
                or not _exact_connections(node, [(a, b) for a, b in links if _plug_node(a) == node])):
            return None
    return scope, relays


def _owned_setup(master, parent, explicit_scope):
    if not parent or not all(
        cmds.attributeQuery(attr, node=parent, exists=True)
        for attr in (_OWNER, _MASTER, _UTILITIES, _ATTACHMENTS, _ATTACHMENT_COUNT)
    ):
        return None
    version = cmds.getAttr(parent + "." + _OWNER)
    driver = master + "." + _SCALE
    surface_version = version == _STATIC_SURFACE_VERSION
    if cmds.objExists(parent + "." + _STATIC_SURFACE_PLAN) != surface_version:
        return None
    if version == _SPLINE_VERSION:
        if (not _exact_input(master + ".message", parent + "." + _MASTER)
                or any(cmds.objExists(parent + "." + attr)
                       for attr in (_COORDINATE_PLAN, _MESH_ATTACHMENTS, _MESH_ATTACHMENT_COUNT,
                                    _SCALE_SIGNALS, _SCALE_SIGNAL_SCOPE))):
            return None
        return _owned_spline(parent, driver, master, explicit_scope)
    if cmds.objExists(parent + "." + _SPLINE_PLAN):
        return None
    if version == _COORDINATE_VERSION:
        if (not _exact_input(master + ".message", parent + "." + _MASTER)
                or not all(cmds.isConnected(driver, parent + ".scale" + axis) for axis in _AXES)
                or any(cmds.objExists(parent + "." + attr)
                       for attr in (_MESH_ATTACHMENTS, _MESH_ATTACHMENT_COUNT))):
            return None
        return _owned_coordinates(parent, driver, master, explicit_scope)
    if cmds.objExists(parent + "." + _COORDINATE_PLAN):
        return None
    mesh_version = version in _MESH_ATTACHMENT_VERSIONS
    if not mesh_version and any(cmds.objExists(parent + "." + attr)
                                for attr in (_MESH_ATTACHMENTS, _MESH_ATTACHMENT_COUNT)):
        return None
    version = _MESH_ATTACHMENT_VERSIONS.get(version, version)
    if surface_version:
        if any(cmds.objExists(parent + "." + attr) for attr in (
                _SKIN_BRANCHES, _SKIN_BRANCH_COUNT, _SCALE_SIGNALS, _SCALE_SIGNAL_SCOPE)):
            return None
        version = _VERSION
    if (version not in (_VERSION, _BRANCH_VERSION, _SIGNAL_VERSION, _BRANCH_SIGNAL_VERSION)
            or _source_node(parent + "." + _MASTER) != master):
        return None
    branches = []
    if version in (_BRANCH_VERSION, _BRANCH_SIGNAL_VERSION):
        if not all(cmds.attributeQuery(attr, node=parent, exists=True)
                   for attr in (_SKIN_BRANCHES, _SKIN_BRANCH_COUNT)):
            return None
        branch_count = cmds.getAttr(parent + "." + _SKIN_BRANCH_COUNT)
        branches = [_source_node("{}.{}[{}]".format(parent, _SKIN_BRANCHES, index))
                    for index in range(branch_count)]
        if (not branch_count or len(set(branches)) != branch_count
                or any(not branch or branch == master or _parent(branch) != parent
                       or not cmds.getAttr(branch + ".inheritsTransform")
                       or _incoming(branch + ".inheritsTransform") for branch in branches)):
            return None
    if not all(cmds.isConnected(driver, parent + ".scale" + axis) for axis in _AXES):
        return None
    def message_source(attr, index):
        return _input("{}.{}[{}]".format(parent, attr, index)).split(".", 1)[0]

    count = cmds.getAttr(parent + "." + _ATTACHMENT_COUNT)
    mesh_targets = {}
    if mesh_version:
        mesh_manifest = _owned_mesh_manifest(parent, master, count)
        if not mesh_manifest:
            return None
        scope, mesh_targets = mesh_manifest
        if explicit_scope and explicit_scope != scope:
            return None
    skin_sources = {}
    utilities = []
    signal_count = 0
    for index in range(count):
        destination = _source_node("{}.{}[{}]".format(parent, _ATTACHMENTS, index))
        matrix, decomposition, ratio = [
            message_source(_UTILITIES, index * 3 + offset) for offset in range(3)
        ]
        if not destination or not all((matrix, decomposition, ratio)):
            return None
        if not _input(matrix + ".matrixIn[0]"):
            return None
        if not cmds.isConnected(matrix + ".matrixSum", decomposition + ".inputMatrix"):
            return None
        if not all(
            cmds.isConnected(decomposition + ".outputScale" + axis, ratio + ".input1" + axis)
            and cmds.isConnected(ratio + ".output" + axis, destination + ".scale" + axis)
            for axis in _AXES
        ):
            return None
        if str(index) in mesh_targets and not _owned_mesh_attachment(
            mesh_targets[str(index)], destination, (matrix, decomposition, ratio),
            master, scope, skin_sources, (parent, "{}[{}]".format(_ATTACHMENTS, index)),
        ):
            return None
        utilities.extend((matrix, decomposition, ratio))
    if surface_version:
        try:
            surface = _owned_static_surface(parent, driver, master, explicit_scope, count, utilities)
        except (AttributeError, IndexError, KeyError, TypeError):
            return None
        if not surface:
            return None
        scope, relays = surface
        utilities.extend(relays)
    if version in (_SIGNAL_VERSION, _BRANCH_SIGNAL_VERSION):
        signals = _owned_scale_signals(parent, driver, master, len(utilities))
        if not signals:
            return None
        relay, signal_count = signals
        utilities.append(relay)
    return [parent] + utilities, branches, signal_count, len(mesh_targets), scope if mesh_version or surface_version else None


_NATIVE_VERSION = "11"
_NATIVE_PLAN = "aminateRigScaleNativePlan"
_NATIVE_FRAME_NOTE = "Keep the outer scene frame at scale 1. Resize with Rig Scale."
_NATIVE_ADDERS = {"addDL", "addDoubleLinear"}
_NATIVE_MULTIPLIERS = {"multDL", "multDoubleLinear"}


def _native_require(condition, detail):
    if not condition:
        raise _Unsupported("Native coordinate setup: " + detail)


def _native_node(plug):
    if not plug:
        return None
    nodes = cmds.ls(plug.split(".", 1)[0], long=True, objectsOnly=True) or []
    _native_require(len(nodes) == 1, "ambiguous input " + plug)
    return nodes[0]


def _native_attr(plug):
    return plug.split(".", 1)[1] if plug else None


def _native_kind(node):
    return cmds.nodeType(node) if node else None


def _native_one(items, detail):
    unique = set(items)
    _native_require(len(unique) == 1, detail)
    return next(iter(unique))


def _native_ancestors(node, scope):
    while node and _inside(node, scope):
        yield node
        if node == scope:
            break
        node = _parent(node)


def _native_local_dag(node, scope):
    _native_require(node and _inside(node, scope) and not _path(node).isInstanced(),
                    "a DAG input is outside the character or instanced")
    _local_node(node)
    return node


def _native_curve(world, scope, allow_static=False):
    shape = _native_node(world)
    _native_require(_native_kind(shape) == "nurbsCurve" and _native_attr(world) == "worldSpace[0]",
                    "missing an uninstanced curve world output")
    _native_local_dag(shape, scope)
    previous = _input(shape + ".create")
    if not previous and allow_static:
        return (shape, shape + ".local", ())
    stages = []
    visited = set()
    while _native_kind(_native_node(previous)) == "cluster":
        cluster = _native_node(previous)
        match = re.fullmatch(r"outputGeometry\[(\d+)\]", _native_attr(previous))
        _native_require(match and cluster not in visited and len(visited) < _BRANCH_GRAPH_LIMIT,
                        "unsupported curve cluster lane")
        visited.add(cluster)
        lane = ".input[{}].inputGeometry".format(match[1])
        geometry = _input(cluster + lane)
        parts = _native_node(geometry)
        handle = _input(cluster + ".matrix")
        _native_require(_native_kind(parts) == "groupParts" and _native_attr(geometry) == "outputGeometry"
                        and _native_attr(handle) == "worldMatrix[0]", "incomplete curve cluster history")
        _native_local_dag(_native_node(handle), scope)
        _local_node(cluster)
        _local_node(parts)
        stages.append((cluster, lane, previous, parts, handle))
        previous = _input(parts + ".inputGeometry")
    _native_require(stages and _native_kind(_native_node(previous)) == "tweak"
                    and _native_attr(previous) == "outputGeometry[0]", "unsupported curve history source")
    return (shape, previous, tuple(reversed(stages)))


def _native_pather(node):
    outputs = [_input(node + ".translate" + axis) for axis in _AXES]
    adders = [_native_node(source) for source in outputs]
    if not all(_native_kind(adder) in _NATIVE_ADDERS and _native_attr(source) == "output"
               for adder, source in zip(adders, outputs)):
        return None
    positions = [_input(adder + ".input2") for adder in adders]
    motion = _native_one(map(_native_node, positions), "mixed motion path inputs")
    _native_require(_native_kind(motion) == "motionPath"
                    and [_native_attr(plug) for plug in positions] == ["xCoordinate", "yCoordinate", "zCoordinate"],
                    "unsupported motion path position lane")
    parent = _parent(node)
    _native_require(parent and not cmds.getAttr(parent + ".inheritsTransform")
                    and not _incoming(parent + ".inheritsTransform"), "pather parent is not detached")
    return motion, adders, positions, _input(motion + ".geometryPath")


def _native_aims(scope):
    aims = {}
    pathers = {}
    for aim in cmds.ls(type="aimConstraint", long=True) or []:
        if not _inside(aim, scope):
            continue
        if cmds.getAttr(aim + ".worldUpType", asString=True).casefold() != "object up":
            continue
        targets = cmds.getAttr(aim + ".target", multiIndices=True) or []
        if len(targets) != 1:
            continue
        target = ".target[{}].targetParentMatrix".format(targets[0])
        attrs = (".constraintParentInverseMatrix", target, ".worldUpMatrix")
        sources = [_input(aim + attr) for attr in attrs]
        if list(map(_native_attr, sources)) != ["parentInverseMatrix[0]", "parentMatrix[0]", "worldMatrix[0]"]:
            continue
        frames = list(map(_native_node, sources))
        if frames[0] != _parent(aim):
            continue
        if not all(_exact_input(aim + ".constraintRotate" + axis, frames[0] + ".rotate" + axis)
                   for axis in _AXES):
            continue
        # The pather-driven aims farther along a curve use an earlier aim as up.
        # The head of the family uses the original control or joint as object-up.
        if any(_native_kind(_source_node(frames[2] + ".rotate" + axis)) == "aimConstraint" for axis in _AXES):
            continue
        pather_nodes = [_parent(node) for node in frames[:2]]
        if not all(pather_nodes) or len(set(pather_nodes)) != 2:
            continue
        chains = [_native_pather(node) for node in pather_nodes]
        if not all(chains):
            continue
        _native_require(chains[0][-1] == chains[1][-1], "aim frames use different curves")
        # The terminal backwards aim has an external up object as well.
        # Keep the root aim that follows increasing curve parameter.
        if cmds.getAttr(chains[0][0] + ".uValue") >= cmds.getAttr(chains[1][0] + ".uValue"):
            continue
        for node in [aim, *frames, *pather_nodes]:
            _native_local_dag(node, scope)
        pathers.update(zip(pather_nodes, chains))
        aims.update((aim + attr, source) for attr, source in zip(attrs, sources))
    _native_require(aims and pathers, "no complete native aim families")
    return aims, pathers


def _native_point_candidates(curve, scope):
    found = set()
    for _, _, _, _, handle in curve[2]:
        for node in _native_ancestors(_native_node(handle), scope):
            if _native_kind(node) != "joint":
                continue
            outputs = [_input(node + ".translate" + axis) for axis in _AXES]
            sources = {_native_node(plug) for plug in outputs}
            if len(sources) != 1:
                continue
            point = next(iter(sources))
            if _native_kind(point) == "pointConstraint":
                _native_require([_native_attr(plug) for plug in outputs] ==
                                ["constraintTranslate" + axis for axis in _AXES],
                                "point constraint axes are cross-wired")
                found.add((node, point))
    return found


def _native_point_and_spline(found, scope):
    point_joint, point = _native_one(found, "multiple point-constraint islands")
    _native_require(_identity_matrix(point_joint + ".offsetParentMatrix")
                    and not _incoming(point_joint + ".offsetParentMatrix")
                    and _exact_input(point_joint + ".parentInverseMatrix[0]", point + ".constraintParentInverseMatrix"),
                    "point constraint frame is not stable")
    targets = cmds.getAttr(point + ".target", multiIndices=True) or []
    _native_require(len(targets) == 1, "point constraint does not have one target")
    tip_source = _input(point + ".target[{}].targetParentMatrix".format(targets[0]))
    tip = _native_local_dag(_native_node(tip_source), scope)
    _native_require(_native_attr(tip_source) == "parentMatrix[0]", "point constraint target frame is unsupported")
    joints = []
    for node in _native_ancestors(tip, scope):
        if _native_kind(node) != "joint":
            break
        joints.append(node)
    joints.reverse()
    _native_require(len(joints) > 2, "the point target has no spline joint chain")
    handles = []
    for handle in cmds.ls(type="ikHandle", long=True) or []:
        if not _inside(handle, scope) or _native_node(_input(handle + ".hsj")) != joints[0]:
            continue
        solver = _input(handle + ".hsv")
        effector = _native_node(_input(handle + ".hee"))
        if _native_kind(_native_node(solver)) == "ikSplineSolver" and effector and _parent(effector) == joints[-2]:
            handles.append((handle, effector, solver))
    handle, effector, solver = _native_one(handles, "no unique native spline solver owns the point target")
    _native_require(cmds.getAttr(handle + ".ikBlend") == 1 and not _incoming(handle + ".ikBlend"),
                    "spline IK/FK blend is animated or fractional")
    _native_require([_native_node(name) for name in cmds.ikHandle(handle, query=True, jointList=True)] == joints[:-1],
                    "the spline joint list differs from its DAG chain")
    active = _input(handle + ".ic")
    up = [_input(handle + "." + attr) for attr in ("dwum", "dwue")]
    for source in up:
        _native_require(_native_attr(source) == "worldMatrix[0]", "unsupported spline up frame")
        _native_local_dag(_native_node(source), scope)
    ratio = _native_one((_input(joint + ".scaleX") for joint in joints[:-1]), "mixed spline stretch sources")
    return dict(point_joint=point_joint, point=point, point_target=targets[0], joints=joints,
                handle=handle, effector=effector, solver=solver, active=active, up=up, ratio=ratio)


def _native_ratio(source, active, scope):
    stages = {}
    curves = set()
    walking = set()

    def walk(plug):
        node, attr = _native_node(plug), _native_attr(plug)
        kind = _native_kind(node)
        if kind not in {"curveInfo", "multiplyDivide", "plusMinusAverage"}:
            return
        _native_require(plug not in walking and len(stages) + len(walking) < _BRANCH_GRAPH_LIMIT,
                        "invalid spline stretch graph")
        if plug in stages:
            return
        walking.add(plug)
        if kind == "curveInfo":
            _native_require(attr == "arcLength", "unsupported spline length output")
            inputs = ("inputCurve",)
            curve = _input(node + ".inputCurve")
            _native_curve(curve, scope, allow_static=True)
            curves.add(curve)
        elif kind == "multiplyDivide":
            _native_require(attr == "outputX", "unsupported spline multiply lane")
            inputs = ("input1X", "input2X")
        else:
            _native_require(attr == "output1D", "unsupported spline sum lane")
            inputs = tuple("input1D[{}]".format(index)
                           for index in (cmds.getAttr(node + ".input1D", multiIndices=True) or []))
        for input_attr in inputs:
            walk(_input(node + "." + input_attr))
        walking.remove(plug)
        stages[plug] = (node, inputs)

    walk(source)
    _native_require(source in stages and active in curves and len(curves) == 2, "incomplete spline stretch lanes")
    measure = next(iter(curves - {active}))
    _native_require(not _incoming(_native_node(measure) + ".create"), "spline measurement curve is deformed")
    return stages, measure


def _native_coordinate_plan(master, scope):
    _native_require(master != scope, "the master must have a character container")
    container = [node for node in _native_ancestors(master, scope) if _parent(node) == scope][0]
    aims, pathers = _native_aims(container)
    curves = {world: _native_curve(world, container) for _, _, _, world in pathers.values()}
    candidates = {world: _native_point_candidates(curve, container) for world, curve in curves.items()}
    curves = {world: curve for world, curve in curves.items() if candidates[world]}
    pathers = {node: chain for node, chain in pathers.items() if chain[-1] in curves}
    aims = {target: source for target, source in aims.items() if _parent(_parent(_native_node(target))) in pathers}
    _native_require(curves and pathers and aims, "no point-driven native aim island")
    spline = _native_point_and_spline(set().union(*(candidates[world] for world in curves)), container)
    spline["ratio_stages"], spline["measure"] = _native_ratio(spline["ratio"], spline["active"], container)
    curves[spline["active"]] = _native_curve(spline["active"], container)
    curves[spline["measure"]] = _native_curve(spline["measure"], container, allow_static=True)
    pather_scale = _native_one((_input(node + ".scale" + axis) for node in pathers for axis in _AXES),
                               "mixed pather scale sources")
    ratio = _native_node(pather_scale)
    distance_source = _input(ratio + ".input1X") if _native_kind(ratio) == "multiplyDivide" else None
    distance = _native_node(distance_source)
    _native_require(_native_attr(pather_scale) == "outputX" and _native_kind(distance) == "distanceDimShape"
                    and _native_attr(distance_source) == "distance", "unsupported pather scale source")
    locators = {}
    for attr in ("startPoint", "endPoint"):
        source = _input(distance + "." + attr)
        locator = _native_node(source)
        _native_require(_native_kind(locator) == "locator" and _native_attr(source) == "worldPosition[0]",
                        "unsupported pather distance input")
        locators[attr] = _native_local_dag(locator, container)
    _native_local_dag(distance, container)
    return dict(container=container, aims=aims, pathers=pathers, curves=curves, spline=spline,
                pather_scale=pather_scale, distance=distance, locators=locators)


_NATIVE_TRANSFORM_CHANNELS = (
    "translate", "rotate", "scale", "shear", "rotateOrder", "rotateAxis", "rotatePivot", "rotatePivotTranslate",
    "scalePivot", "scalePivotTranslate", "offsetParentMatrix", "inheritsTransform",
)
_NATIVE_JOINT_CHANNELS = (
    "jointOrient", "inverseScale", "segmentScaleCompensate", "preferredAngle",
    "minRotLimit", "maxRotLimit", "minRotLimitEnable", "maxRotLimitEnable", "stiffness",
)
_NATIVE_IK_CHANNELS = (
    "priority", "weight", "poWeight", "stickiness", "snapEnable", "rootOnCurve", "rootTwistMode",
    "twist", "roll", "offset", "dTwistControlEnable", "dWorldUpType", "dWorldUpAxis", "dForwardAxis",
    "dWorldUpVector", "dWorldUpVectorEnd", "dTwistValueType", "dTwistStart", "dTwistEnd", "dTwistRampMult",
)


def _native_objects():
    result = {}
    iterator = om.MItDependencyNodes()
    while not iterator.isDone():
        obj = iterator.thisNode()
        node = om.MFnDependencyNode(obj)
        identity = node.uuid().asString()
        result.setdefault(identity, []).append(obj)
        iterator.next()
    return result


def _native_object_path(obj):
    if obj.hasFn(om.MFn.kDagNode):
        return om.MDagPath.getAPathTo(obj).fullPathName()
    return om.MFnDependencyNode(obj).name()


def _native_links(node):
    links = cmds.listConnections(node, source=True, destination=True, connections=True, plugs=True) or []
    return sorted(zip(links[::2], links[1::2]))


def _native_default_membership(source, target):
    return (_native_attr(source) == "message"
            and _native_kind(_native_node(target)) == "defaultRenderUtilityList"
            and bool(re.fullmatch(r"utilities\[\d+\]", _native_attr(target))))


class _NativeCoordinates:
    def __init__(self, scope, wrapper, plan, prefix, create, created):
        self.scope = scope
        self.wrapper = wrapper
        self.plan = plan
        self.prefix = prefix
        self.create = create
        self.created = created
        self.frames = {}
        self.parent_frames = {}
        self.curves = {}
        self.static = {}
        self.building = set()
        self.registered_types = set(cmds.allNodeTypes())

    def node(self, kind, label, parent=None):
        node = self.create(kind, self.prefix + "_" + label + "#", **({"parent": parent} if parent else {}))
        return _native_node(node)

    def matrix(self, *sources):
        node = self.node("multMatrix", "matrix")
        for index, source in enumerate(sources):
            cmds.connectAttr(source, "{}.matrixIn[{}]".format(node, index))
        return node + ".matrixSum"

    def output_scale_matrix(self, driver, detached):
        # Detached display meshes need world scaling about the scope origin.
        # Inherited world-deformed meshes get scale from their inputs and need
        # only the opposite translation in their local output frame.
        multiplier = _native_one(self.registered_types & _NATIVE_MULTIPLIERS, "double-linear multiply unavailable")
        adder = _native_one(self.registered_types & _NATIVE_ADDERS, "double-linear add unavailable")
        difference = self.node(adder, "scaleDifference")
        origin = self.node("decomposeMatrix", "scaleOrigin")
        correction = self.node("composeMatrix", "outputScale")
        signed_driver = driver
        if detached:
            negate = self.node(multiplier, "scaleNegate")
            cmds.connectAttr(driver, negate + ".input1")
            cmds.setAttr(negate + ".input2", -1)
            self.static[_coordinate_identity(negate + ".input2")] = -1
            signed_driver = negate + ".output"
        offset = 1 if detached else -1
        cmds.connectAttr(signed_driver, difference + ".input1")
        cmds.setAttr(difference + ".input2", offset)
        self.static[_coordinate_identity(difference + ".input2")] = offset
        cmds.connectAttr(self.scope + ".worldMatrix[0]", origin + ".inputMatrix")
        for axis in _AXES:
            translate = self.node(multiplier, "detachedTranslate")
            cmds.connectAttr(difference + ".output", translate + ".input1")
            cmds.connectAttr(origin + ".outputTranslate" + axis, translate + ".input2")
            cmds.connectAttr(translate + ".output", correction + ".inputTranslate" + axis)
            if detached:
                cmds.connectAttr(driver, correction + ".inputScale" + axis)
        fixed = ["inputRotateOrder", "useEulerRotation"]
        fixed.extend(attr + axis for attr in ("inputRotate", "inputShear") for axis in _AXES)
        if not detached:
            fixed.extend("inputScale" + axis for axis in _AXES)
        for attr in fixed:
            plug = correction + "." + attr
            self.static[_coordinate_identity(plug)] = cmds.getAttr(plug)
        return correction + ".outputMatrix"

    def duplicate(self, source, support=False):
        before = _native_objects()
        links = _native_links(source)
        cmds.duplicate(source, inputConnections=True, name=self.prefix + "_clone#")
        after = _native_objects()
        new = sorted(after.keys() - before.keys())
        self.created.extend(new)
        _native_require(all(len(after.get(identity, ())) == len(nodes) for identity, nodes in before.items())
                        and _native_links(source) == links,
                        "native duplication changed existing graph edges")
        matches = []
        for identity in new:
            _native_require(len(after[identity]) == 1, "duplicate native node identity")
            node = _native_object_path(after[identity][0])
            kind = _native_kind(node)
            if kind == _native_kind(source):
                matches.append(node)
            else:
                _native_require(support and kind in {"objectSet", "transform", "clusterHandle", "pointConstraint"},
                                "unexpected native duplication support node " + kind)
                if kind in {"clusterHandle", "pointConstraint"}:
                    _native_require(_native_uuid(_parent(node)) in new, "native support shape or constraint escaped")
                if kind == "transform":
                    cmds.setAttr(node + ".visibility", False)
            flat = cmds.listConnections(node, source=False, destination=True, connections=True, plugs=True) or []
            for output, target in zip(flat[::2], flat[1::2]):
                _native_require(cmds.ls(_native_node(target), uuid=True)[0] in new
                                or _native_default_membership(output, target),
                                "native duplication changed a foreign destination")
        return _native_one(matches, "could not identify the native duplicate")

    def relay(self, source, destination, attr, remap=None, live=False):
        original = source + "." + attr
        target = destination + "." + attr
        source_input = _input(original) if cmds.connectionInfo(original, isExactDestination=True) else None
        if source_input:
            node = _native_node(source_input)
            replacement = (remap or {}).get(node)
            if replacement:
                source_input = replacement + "." + _native_attr(source_input)
            elif live:
                source_input = original
            if not _exact_input(source_input, target):
                cmds.connectAttr(source_input, target, force=True)
            return
        children = cmds.attributeQuery(attr, node=source, listChildren=True) or []
        if children:
            for child in children:
                self.relay(source, destination, child, remap, live=live)
            return
        value = cmds.getAttr(original)
        if live:
            cmds.connectAttr(original, target, force=True)
        elif cmds.getAttr(original, type=True) == "matrix":
            cmds.setAttr(target, *value, type="matrix")
        elif value != cmds.getAttr(target):
            cmds.setAttr(target, value)

    def transform(self, node):
        if node == self.wrapper:
            return self.scope
        if not _inside(node, self.wrapper):
            _native_require(node == self.scope or _inside(node, self.scope), "shadow frame escapes the scope")
            return node
        if node not in self.frames:
            _native_require(node not in self.building, "cyclic canonical transform")
            self.building.add(node)
            parent = self.transform(_parent(node))
            shadow = self.node("transform", "frame", parent)
            cmds.setAttr(shadow + ".visibility", False)
            self.relay(node, shadow, "inheritsTransform", live=True)
            cmds.connectAttr(node + ".dagLocalMatrix", shadow + ".offsetParentMatrix")
            self.frames[node] = shadow
            if node == self.plan["spline"]["point_joint"]:
                self.point_shadow(node, shadow)
            self.building.remove(node)
        return self.frames[node]

    def input_matrix(self, source):
        node, attr = _native_node(source), _native_attr(source)
        if attr == "worldMatrix[0]":
            return self.transform(node) + "." + attr
        _native_require(attr in {"parentMatrix[0]", "parentInverseMatrix[0]"}, "unsupported canonical frame plug")
        if node not in self.parent_frames:
            parent = self.transform(_parent(node))
            shadow = self.node("transform", "parentFrame", parent)
            cmds.setAttr(shadow + ".visibility", False)
            for channel in ("offsetParentMatrix", "inheritsTransform"):
                self.relay(node, shadow, channel, live=True)
            self.parent_frames[node] = shadow
        return self.parent_frames[node] + "." + attr

    def point_shadow(self, joint, shadow):
        spline = self.plan["spline"]
        point = spline["point"]
        duplicate = self.duplicate(point)
        target = ".target[{}]".format(spline["point_target"])
        for attr in (".constraintParentInverseMatrix", target + ".targetParentMatrix"):
            cmds.connectAttr(self.input_matrix(_input(point + attr)), duplicate + attr, force=True)
        cmds.connectAttr(point + target + ".targetWeight", duplicate + target + ".targetWeight", force=True)
        for attr in ("offset", "restTranslate", "enableRestPosition", "constraintOffsetPolarity"):
            if cmds.attributeQuery(attr, node=point, exists=True):
                cmds.connectAttr(point + "." + attr, duplicate + "." + attr, force=True)
        translate = self.node("composeMatrix", "pointDelta")
        multiplier = _native_one(self.registered_types & _NATIVE_MULTIPLIERS, "double-linear multiply unavailable")
        adder = _native_one(self.registered_types & _NATIVE_ADDERS, "double-linear add unavailable")
        for axis in _AXES:
            minus = self.node(multiplier, "pointNegate")
            add = self.node(adder, "pointAdd")
            cmds.connectAttr(joint + ".translate" + axis, minus + ".input1")
            cmds.setAttr(minus + ".input2", -1)
            self.static[_coordinate_identity(minus + ".input2")] = -1
            cmds.connectAttr(minus + ".output", add + ".input1")
            cmds.connectAttr(duplicate + ".constraintTranslate" + axis, add + ".input2")
            cmds.connectAttr(add + ".output", translate + ".inputTranslate" + axis)
        corrected = self.matrix(joint + ".dagLocalMatrix", translate + ".outputMatrix")
        cmds.connectAttr(corrected, shadow + ".offsetParentMatrix", force=True)

    def curve(self, world):
        if world not in self.curves:
            shape, geometry, stages = self.plan["curves"][world]
            for cluster, lane, output, parts, handle in stages:
                canonical_handle = self.input_matrix(handle)
                parts_copy = self.duplicate(parts)
                cmds.connectAttr(geometry, parts_copy + ".inputGeometry", force=True)
                cluster_copy = self.duplicate(cluster, support=True)
                cmds.connectAttr(canonical_handle, cluster_copy + ".matrix", force=True)
                xforms = _input(cluster + ".clusterXforms")
                if xforms and not _exact_input(xforms, cluster_copy + ".clusterXforms"):
                    cmds.connectAttr(xforms, cluster_copy + ".clusterXforms", force=True)
                cmds.connectAttr(cluster + ".envelope", cluster_copy + ".envelope", force=True)
                cmds.connectAttr(parts_copy + ".outputGeometry", cluster_copy + lane, force=True)
                geometry = cluster_copy + "." + _native_attr(output)
            parent = self.transform(_parent(shape))
            duplicate = self.node("nurbsCurve", "geometry", parent)
            cmds.connectAttr(geometry, duplicate + ".create")
            self.curves[world] = duplicate + ".worldSpace[0]"
        return self.curves[world]

    def spline(self):
        spline = self.plan["spline"]
        active = self.curve(spline["active"])
        replacements = {spline["active"]: active, spline["measure"]: self.curve(spline["measure"])}
        for output, (node, inputs) in spline["ratio_stages"].items():
            clone = self.duplicate(node)
            for attr in inputs:
                original = node + "." + attr
                upstream = _input(original)
                if upstream:
                    source = replacements.get(upstream, upstream)
                    if not _exact_input(source, clone + "." + attr):
                        cmds.connectAttr(source, clone + "." + attr, force=True)
                else:
                    value = cmds.getAttr(original)
                    _native_require(_fixed_attr(clone + "." + attr, value), "native ratio default was not retained")
                    self.static[_coordinate_identity(original)] = value
                    self.static[_coordinate_identity(clone + "." + attr)] = value
            if cmds.objExists(node + ".operation"):
                cmds.connectAttr(node + ".operation", clone + ".operation", force=True)
            replacements[output] = clone + "." + _native_attr(output)
        joints = spline["joints"]
        mapped = {}
        parent = self.transform(_parent(joints[0]))
        for joint in joints:
            _native_require(_identity_matrix(joint + ".offsetParentMatrix"), "nonidentity spline joint offset")
            shadow = self.node("joint", "splineJoint", parent)
            for attr in _NATIVE_TRANSFORM_CHANNELS + _NATIVE_JOINT_CHANNELS:
                if attr == "scale" and joint != joints[-1]:
                    cmds.connectAttr(replacements[spline["ratio"]], shadow + ".scaleX")
                    for axis in "YZ":
                        self.relay(joint, shadow, "scale" + axis, mapped, live=True)
                else:
                    self.relay(joint, shadow, attr, mapped, live=attr not in {"translate", "rotate", "inverseScale"})
            if cmds.getAttr(shadow + ".dofMask") != cmds.getAttr(joint + ".dofMask"):
                cmds.joint(shadow, edit=True, degreeOfFreedom=cmds.joint(joint, query=True, degreeOfFreedom=True))
            _native_require(cmds.getAttr(shadow + ".dofMask") == cmds.getAttr(joint + ".dofMask"),
                            "spline joint degree of freedom could not be reproduced")
            for axis in _AXES:
                attr = ".rotate" + axis
                cmds.setAttr(shadow + attr, lock=cmds.getAttr(joint + attr, lock=True))
            mapped[joint] = shadow
            parent = shadow
        effector = self.node("ikEffector", "splineEffector", mapped[joints[-2]])
        for attr in _NATIVE_TRANSFORM_CHANNELS:
            self.relay(spline["effector"], effector, attr, mapped)
        original_handle = spline["handle"]
        self.static[_coordinate_identity(original_handle + ".ikBlend")] = 1
        handle = self.node("ikHandle", "splineHandle", self.transform(_parent(original_handle)))
        cmds.setAttr(handle + ".visibility", False)
        cmds.setAttr(handle + ".ikBlend", 0)
        for attr in _NATIVE_TRANSFORM_CHANNELS + _NATIVE_IK_CHANNELS:
            if cmds.objExists(original_handle + "." + attr):
                self.relay(original_handle, handle, attr, mapped, live=True)
        connections = {
            ".hsj": mapped[joints[0]] + ".message", ".hee": effector + ".hp", ".hsv": spline["solver"],
            ".ic": active, ".dwum": self.input_matrix(spline["up"][0]), ".dwue": self.input_matrix(spline["up"][1]),
            ".ikBlend": original_handle + ".ikBlend",
        }
        for attr, source in connections.items():
            cmds.connectAttr(source, handle + attr)
        original_chain = cmds.ikHandle(original_handle, query=True, jointList=True)
        actual_chain = cmds.ikHandle(handle, query=True, jointList=True)
        _native_require(list(map(_native_node, actual_chain)) == [mapped[_native_node(node)] for node in original_chain],
                        "native spline shadow has a different IK joint list")
        self.frames.update(mapped)

    def pather_scale(self):
        distance = self.plan["distance"]
        clone = self.node("distanceDimShape", "distance", self.transform(_parent(distance)))
        cmds.setAttr(clone + ".visibility", False)
        for attr, locator in self.plan["locators"].items():
            shadow = self.node("locator", "distancePoint", self.transform(_parent(locator)))
            cmds.setAttr(shadow + ".visibility", False)
            self.relay(locator, shadow, "localPosition", live=True)
            cmds.connectAttr(shadow + ".worldPosition[0]", clone + "." + attr)
        ratio = _native_node(self.plan["pather_scale"])
        duplicate = self.duplicate(ratio)
        cmds.connectAttr(clone + ".distance", duplicate + ".input1X", force=True)
        for attr in ("input2X", "operation"):
            cmds.connectAttr(ratio + "." + attr, duplicate + "." + attr, force=True)
        return duplicate + ".outputX"

    def aim_inputs(self):
        self.spline()
        scale_source = self.pather_scale()
        for pather, (motion, adders, positions, world) in self.plan["pathers"].items():
            shadow = self.node("transform", "pather", self.transform(_parent(pather)))
            cmds.setAttr(shadow + ".visibility", False)
            _native_require(pather not in self.frames, "a pather was already used as an ordinary frame")
            self.frames[pather] = shadow
            for attr in _NATIVE_TRANSFORM_CHANNELS:
                if attr not in {"translate", "scale"}:
                    self.relay(pather, shadow, attr, live=True)
            duplicate = self.duplicate(motion)
            cmds.connectAttr(self.curve(world), duplicate + ".geometryPath", force=True)
            cmds.connectAttr(motion + ".uValue", duplicate + ".uValue", force=True)
            for axis, adder, position in zip(_AXES, adders, positions):
                addition = self.duplicate(adder)
                cmds.connectAttr(adder + ".input1", addition + ".input1", force=True)
                cmds.connectAttr(duplicate + "." + _native_attr(position), addition + ".input2", force=True)
                cmds.connectAttr(addition + ".output", shadow + ".translate" + axis)
                cmds.connectAttr(scale_source, shadow + ".scale" + axis)
        return {destination: self.input_matrix(source) for destination, source in self.plan["aims"].items()}


def _native_affected_closure(sources, destinations):
    iterator_type = om.MItDependencyGraph
    blocked = {_coordinate_identity(plug) for plug in destinations}
    blocked_aims = {_native_node(plug) for plug in destinations}
    visited = set()
    pending = list(sources)
    while pending:
        name = pending.pop()
        plug = om.MSelectionList().add(name).getPlug(0)
        if plug.name() in visited:
            continue
        iterator = iterator_type(plug, om.MFn.kInvalid, iterator_type.kUpstream,
                                 iterator_type.kDepthFirst, iterator_type.kPlugLevel)
        iterator.traversingOverWorldSpaceDependents = True
        while not iterator.isDone():
            current = iterator.currentPlug()
            current_name = current.name()
            if current_name not in visited:
                visited.add(current_name)
                _native_require(len(visited) < _SCALE_SIGNAL_GRAPH_LIMIT, "canonical dependency graph is too large")
                node = _native_object_path(current.node())
                attr = current.partialName(includeNonMandatoryIndices=True, includeInstancedIndices=True,
                                           useFullAttributePath=True, useLongNames=True)
                identity = om.MFnDependencyNode(current.node()).uuid().asString() + "." + attr
                _native_require(identity not in blocked and not (
                    node in blocked_aims and attr.startswith("constraintRotate")), "canonical graph reads a replaced aim")
                if attr in {"worldMatrix[0]", "worldInverseMatrix[0]", "parentMatrix[0]", "parentInverseMatrix[0]"}:
                    parent = _parent(node)
                    if parent and cmds.getAttr(node + ".inheritsTransform"):
                        pending.append(parent + ".worldMatrix[0]")
            iterator.next()


def _native_mesh_consumers(branch, scope, inherited=False):
    _native_spatial_exits(branch)
    meshes = cmds.listRelatives(branch, allDescendents=True, fullPath=True, type="mesh") or []
    pending = [mesh + attr for mesh in meshes for attr in (".outMesh", ".worldMesh[0]")]
    seen = set()
    edges = set()
    sinks = set()
    while pending:
        source = pending.pop()
        identity = _coordinate_identity(source)
        if identity in seen:
            continue
        _native_require(len(seen) < _BRANCH_GRAPH_LIMIT, "detached geometry graph is too large")
        seen.add(identity)
        for target in cmds.listConnections(source, source=False, destination=True, plugs=True) or []:
            node, attr = _native_node(target), _native_attr(target)
            kind = _native_kind(node)
            edges.add((identity, _coordinate_identity(target)))
            if kind == "mesh" and attr == "inMesh":
                _native_local_dag(node, branch if inherited else scope)
                sinks.add(node)
                pending.extend((node + ".outMesh", node + ".worldMesh[0]"))
            elif kind == "groupParts" and attr == "inputGeometry":
                pending.append(node + ".outputGeometry")
            elif kind in {"createColorSet", "deleteColorSet"} and _exact_input(source, node + ".ig"):
                pending.append(node + ".og")
            elif kind == "polyTweakUV" and _exact_input(source, node + ".ip"):
                pending.append(node + ".out")
            elif kind in {"tweak", "skinCluster", "blendShape"} and (
                lane := re.fullmatch(r"input\[(\d+)\]\.inputGeometry", attr)
            ):
                if kind == "blendShape":
                    _native_require(cmds.getAttr(node + ".origin", asString=True).casefold() == "local",
                                    "detached geometry enters a world-origin blend")
                elif kind == "skinCluster":
                    influences = _spline_influences(node)
                    _native_require(_fixed_attr(node + ".skinningMethod", 0)
                                    and not _incoming(node + ".geomMatrix")
                                    and influences and all(_inside(joint, scope) for joint in influences),
                                    "detached geometry enters an unsupported skin mode")
                else:
                    _native_require(_fixed_attr(node + ".relativeTweak", True),
                                    "detached geometry enters an absolute tweak")
                pending.append(node + ".outputGeometry[{}]".format(lane[1]))
            elif kind == "blendShape" and (
                lane := re.fullmatch(r"inputTarget\[(\d+)\]\..*\.inputGeomTarget", attr)
            ):
                output = node + ".outputGeometry[{}]".format(lane[1])
                _native_require(cmds.getAttr(node + ".origin", asString=True).casefold() == "local",
                                "geometry enters a world-origin blend target")
                if inherited:
                    pending.append(output)
                else:
                    _native_require(not cmds.listConnections(output, source=False, destination=True),
                                    "detached geometry enters an active blend target")
            else:
                raise _Unsupported("Unknown output mesh consumer: " + target)
    return sorted(edges), sinks


def _native_sample_status(samples, origin, factor):
    _force_evaluation()
    result = {}
    for obj, kind, original in samples:
        current = _points(obj, kind)
        stationary = len(current) == len(original) and all(a == b for a, b in zip(original, current))
        follows = len(current) == len(original) and all(
            math.sqrt(sum((b[i] - (origin[i] + (a[i] - origin[i]) * factor)) ** 2 for i in range(3)))
            <= 1e-4 + max(abs(a[i] - origin[i]) for i in range(3)) * 2e-5
            for a, b in zip(original, current))
        result[_native_object_path(obj)] = (kind, stationary, follows)
    return result


def _native_exact_points(samples):
    _force_evaluation()
    for obj, kind, original in samples:
        current = _points(obj, kind)
        _native_require(len(current) == len(original) and all(a == b for a, b in zip(original, current)),
                        "scale 1 changes original points on " + _native_object_path(obj))


def _native_skin_scope(shape, container):
    history = cmds.listHistory(shape, pruneDagObjects=True) or []
    skins = cmds.ls(history, type="skinCluster") or []
    return bool(skins) and all(influences and all(_inside(node, container) for node in influences)
                              for influences in map(_spline_influences, skins))


def _native_rigid_output(shape, container):
    node = _parent(shape)
    if _incoming(shape + ".inMesh") or not node or not _root_follows_master(node, container):
        return False
    constraint = _source_node(node + ".translateX")
    return (cmds.nodeType(constraint) == "parentConstraint"
            and all(_exact_input(constraint + ".constraintRotate" + axis, node + ".rotate" + axis) for axis in _AXES))


def _native_rendered_output(branch, scope, container, shapes):
    if not all(kind == "mesh" and _incoming(shape + ".inMesh") for shape, kind, _ in shapes):
        return None
    skin_paths = [_native_skin_scope(shape, container) for shape, _, _ in shapes]
    if not any(skin_paths):
        return None
    _native_require(all(skin_paths), "mixed rendered output drivers on " + branch)
    return _native_rendered_frame(branch, scope)


def _native_rendered_frame(branch, scope):
    _native_local_dag(branch, scope)
    _native_require(_parent(branch) == scope, "rendered output branch moved")
    transforms = cmds.listRelatives(branch, allDescendents=True, fullPath=True, type="transform") or []
    for node in (branch, *transforms):
        _native_require(_native_kind(node) == "transform" and _identity_matrix(node + ".matrix")
                        and _fixed_attr(node + ".inheritsTransform", True)
                        and not any(_incoming(node + "." + attr) for attr in _NATIVE_TRANSFORM_CHANNELS
                                    if attr != "offsetParentMatrix")
                        and (node == branch or (not _incoming(node + ".offsetParentMatrix")
                                                and _identity_matrix(node + ".offsetParentMatrix"))),
                        "rendered output has a nonidentity local frame " + node)
    parent = scope
    while parent:
        _native_require(_native_kind(parent) == "transform" and _fixed_attr(parent + ".scale", [(1.0, 1.0, 1.0)])
                        and _fixed_attr(parent + ".shear", [(0.0, 0.0, 0.0)])
                        and not _incoming(parent + ".offsetParentMatrix") and _identity_matrix(parent + ".offsetParentMatrix"),
                        "rendered outputs require an unscaled outer frame")
        parent = _parent(parent)
    edges, _ = _native_mesh_consumers(branch, scope, inherited=True)
    return edges


def _native_spatial_exits(branch):
    transforms = [branch] + (cmds.listRelatives(branch, allDescendents=True, fullPath=True, type="transform") or [])
    for node in transforms:
        for attr in ("worldMatrix[0]", "worldInverseMatrix[0]", "parentMatrix[0]", "parentInverseMatrix[0]"):
            for target in cmds.listConnections(node + "." + attr, source=False, destination=True, plugs=True) or []:
                constraint = _native_node(target)
                if (attr == "parentInverseMatrix[0]" and _native_attr(target) == "constraintParentInverseMatrix"
                        and _native_kind(constraint) == "parentConstraint"
                        and all(_exact_input(constraint + ".constraintTranslate" + axis, node + ".translate" + axis)
                                for axis in _AXES)):
                    continue
                _native_require(_inside(_native_node(target), branch), "foreign spatial consumer " + target)


def _native_scope_consumers(branches, scope):
    # The wrapper moves inherited descendants as well as explicit DG lanes.
    # Follow original and owned data edges to catch exports through utilities.
    pending = list(branches)
    visited = set()
    while pending:
        node = pending.pop()
        if node in visited:
            continue
        visited.add(node)
        _native_require(len(visited) < _SCALE_SIGNAL_GRAPH_LIMIT, "native output graph is too large")
        if node.startswith("|"):
            _native_require(_inside(node, scope) and not _path(node).isInstanced(),
                            "native output reaches a foreign or instanced DAG node " + node)
            pending.extend(cmds.listRelatives(node, children=True, fullPath=True) or [])
        for source, target in _data_edges(node):
            if _shape_editor_edge(source, target):
                continue
            destination = _plug_node(target)
            _native_require(destination, "ambiguous native output destination " + target)
            pending.append(destination)


def _native_placement(samples, scope, container, origin):
    status = _native_sample_status(samples, origin, 0.5)
    branch_states = {}
    detached = set()
    for shape, (kind, stationary, follows) in status.items():
        ancestors = list(_native_ancestors(shape, scope))
        if len(ancestors) < 2:
            _native_require(follows, "scope has unsupported geometry on its own transform")
            continue
        branch = ancestors[-2]
        if _inside(shape, container):
            if follows:
                continue
            _native_require(kind == "mesh" and stationary and not _incoming(shape + ".inMesh"),
                            "a rig output does not follow canonical scale")
            cuts = [node for node in ancestors[1:] if node != scope and
                    not cmds.getAttr(node + ".inheritsTransform") and not _incoming(node + ".inheritsTransform")]
            _native_require(cuts, "stationary output has no stable inheritance cut")
            detached.add(cuts[-1])
        else:
            branch_states.setdefault(branch, []).append((shape, kind, follows))
    siblings = []
    rendered = {}
    for branch, shapes in branch_states.items():
        edges = _native_rendered_output(branch, scope, container, shapes)
        if edges is not None:
            _native_require(not _incoming(branch + ".offsetParentMatrix") and _identity_matrix(branch + ".offsetParentMatrix"),
                            "rendered output already has a matrix driver")
            rendered[branch] = edges
            continue
        if all(follows for _, _, follows in shapes):
            continue
        _native_local_dag(branch, scope)
        _native_require(_parent(branch) == scope and _native_kind(branch) == "transform"
                        and _fixed_attr(branch + ".inheritsTransform", True)
                        and all(not follows and kind == "mesh" and (
                            _native_rigid_output(shape, container) or _native_skin_scope(shape, container)
                        ) for shape, kind, follows in shapes), "unclassified sibling output branch " + branch)
        _native_mesh_consumers(branch, scope)
        siblings.append(branch)
    lane_edges = {}
    for branch in detached:
        offset = branch + ".offsetParentMatrix"
        _native_local_dag(branch, scope)
        _native_require(not _incoming(offset) and _identity_matrix(offset), "detached branch already has a matrix driver")
        edges, sinks = _native_mesh_consumers(branch, scope)
        _native_require(sinks <= set(status), "unmeasured downstream detached mesh")
        lane_edges[branch] = edges
    return siblings, lane_edges, rendered


def _native_uuid(node):
    identities = cmds.ls(node, uuid=True) or []
    _native_require(len(identities) == 1, "ambiguous node identity")
    return identities[0]


def _native_plug_key(plug):
    attr = plug.partialName(includeNonMandatoryIndices=True, includeInstancedIndices=True,
                           useFullAttributePath=True, useLongNames=True)
    return om.MFnDependencyNode(plug.node()).uuid().asString() + "." + attr


def _native_graph_edges(objects, owned=None):
    result = set()
    for identity, nodes in objects.items():
        if owned is not None and identity not in owned:
            continue
        if len(nodes) != 1:
            _native_require(owned is None, "ambiguous owned node identity")
            continue
        fn = om.MFnDependencyNode(nodes[0])
        for plug in fn.getConnections():
            for source in plug.connectedTo(True, False):
                if owned is not None:
                    result.add((_native_plug_key(source), _native_plug_key(plug)))
            for target in plug.connectedTo(False, True):
                if owned is not None or om.MFnDependencyNode(target.node()).uuid().asString() in objects:
                    result.add((_native_plug_key(plug), _native_plug_key(target)))
    return sorted(result)


def _native_nodes_state(nodes):
    result = []
    for node in nodes:
        identity = _native_uuid(node)
        kind = cmds.nodeType(node)
        is_dag = bool(cmds.ls(node, dagObjects=True, objectsOnly=True, long=True))
        parent = _parent(node) if is_dag else None
        result.append((identity, kind, _native_uuid(parent) if parent else None))
    return sorted(result)


_NATIVE_WRAPPER_CONSTANTS = {
    "translate": (0, 0, 0), "rotate": (0, 0, 0), "shear": (0, 0, 0), "rotateAxis": (0, 0, 0),
    "rotatePivot": (0, 0, 0), "scalePivot": (0, 0, 0), "rotatePivotTranslate": (0, 0, 0),
    "scalePivotTranslate": (0, 0, 0), "inheritsTransform": True,
}


def _native_wrapper_frame(group):
    for attr, value in _NATIVE_WRAPPER_CONSTANTS.items():
        plug = group + "." + attr
        _native_require(_fixed_attr(plug, [value] if isinstance(value, tuple) else value)
                        and cmds.getAttr(plug, lock=True), "wrapper frame has been altered")
    offset = group + ".offsetParentMatrix"
    _native_require(_identity_matrix(offset) and not _incoming(offset) and cmds.getAttr(offset, lock=True),
                    "wrapper offset has been altered")


def _native_owner_candidates(master):
    driver = master + "." + _SCALE
    destinations = set()
    for source in (driver, master + ".message"):
        for plug in cmds.listConnections(source, source=False, destination=True, plugs=True) or []:
            node = _native_node(plug)
            if (cmds.objExists(node + "." + _NATIVE_PLAN)
                    or (cmds.objExists(node + "." + _OWNER) and cmds.getAttr(node + "." + _OWNER) == _NATIVE_VERSION)):
                destinations.add(node)
    return destinations


def _owned_native(group, master, explicit_scope):
    try:
        driver = master + "." + _SCALE
        wrapper_plugs = {group + ".scale" + axis for axis in _AXES}
        _native_require(_native_kind(group) == "transform"
                        and _fixed_attr(group + "." + _OWNER, _NATIVE_VERSION)
                        and cmds.getAttr(group + "." + _OWNER, lock=True)
                        and _exact_input(master + ".message", group + "." + _MASTER)
                        and all(_exact_input(driver, plug) for plug in wrapper_plugs)
                        and {_coordinate_identity(plug) for plug in (
                            cmds.listConnections(driver, source=False, destination=True, plugs=True) or []
                        )} == {_coordinate_identity(plug) for plug in wrapper_plugs}, "invalid wrapper ownership")
        manifest_plug = group + "." + _NATIVE_PLAN
        _native_require(cmds.getAttr(manifest_plug, lock=True) and not _incoming(manifest_plug),
                        "native owner manifest is editable")
        manifest = json.loads(cmds.getAttr(manifest_plug))
        scope = _identity_node(manifest["scope"])
        branches = list(map(_identity_node, manifest["branches"]))
        _native_require(scope == _parent(group) and (not explicit_scope or explicit_scope == scope)
                        and _inside(master, branches[0]) and _parent(branches[0]) == group
                        and set(branches) == set(cmds.listRelatives(group, children=True, fullPath=True) or []),
                        "wrapper branch containment changed")
        _native_wrapper_frame(group)
        identities = [item[0] for item in manifest["nodes"]]
        _native_require(len(set(identities)) == len(identities) and _native_uuid(group) in identities,
                        "duplicate or absent owned node")
        nodes = list(map(_identity_node, identities))
        _native_require([list(item) for item in _native_nodes_state(nodes)] == manifest["nodes"],
                        "owned native node type or parent changed")
        inputs = cmds.getAttr(group + "." + _UTILITIES, multiIndices=True) or []
        members = [_native_node(_input("{}.{}[{}]".format(group, _UTILITIES, index))) for index in inputs]
        _native_require(len(members) == len(nodes) - 1 and set(members) == set(nodes) - {group},
                        "native utility ownership changed")
        objects = _native_objects()
        _native_require([list(edge) for edge in _native_graph_edges(objects, set(identities))] == manifest["edges"],
                        "native graph connection changed")
        for source, target in manifest["constants"]:
            _native_require(_fixed_attr(_identity_plug(source), target), "native authored setting changed")
        for target, inherit_lock, offset_lock, edges in manifest["detached"]:
            branch = _identity_node(target)
            current, _ = _native_mesh_consumers(branch, scope)
            _native_require([list(edge) for edge in current] == edges
                            and _fixed_attr(branch + ".inheritsTransform", False)
                            and cmds.getAttr(branch + ".inheritsTransform", lock=True) == inherit_lock
                            and cmds.getAttr(branch + ".offsetParentMatrix", lock=True) == offset_lock,
                            "detached geometry path changed")
        for identity, edges in manifest["sibling_consumers"]:
            branch = _identity_node(identity)
            current, _ = _native_mesh_consumers(branch, scope)
            _native_require([list(edge) for edge in current] == edges, "sibling geometry path changed")
        rendered_branches = []
        for identity, offset_lock, edges in manifest["rendered"]:
            branch = _identity_node(identity)
            current = _native_rendered_frame(branch, scope)
            _native_require([list(edge) for edge in current] == edges
                            and cmds.getAttr(branch + ".offsetParentMatrix", lock=True) == offset_lock,
                            "rendered geometry path changed")
            rendered_branches.append(branch)
        _native_scope_consumers(branches + rendered_branches, scope)
        for original, destination, replacement in manifest["replaced"]:
            _native_require(cmds.objExists(_identity_plug(original))
                            and _exact_input(_identity_plug(replacement), _identity_plug(destination)),
                            "original aim replacement changed")
        return [group] + [node for node in nodes if node != group], branches, 1, len(manifest["detached"]), scope
    except (_Unsupported, RuntimeError, TypeError, ValueError, KeyError, IndexError):
        return None


def _add_native_coordinates(report, checked, plan, multiplier):
    scope = report["character_root"]
    original_master = report["master_control"]
    master_id = _native_uuid(original_master)
    container_id = _native_uuid(plan["container"])
    origin = om.MPoint.kOrigin * _path(scope).inclusiveMatrix()
    samples = _point_samples(checked)
    selected = om.MGlobal.getActiveSelectionList()
    modified = cmds.file(query=True, modified=True)
    autokey = cmds.autoKeyframe(query=True, state=True)
    prefix = ":" + original_master.rsplit("|", 1)[-1] + "_aminateRigScale"
    original_objects = _native_objects()
    original_edges = _native_graph_edges(original_objects)
    original_branches = {_native_uuid(node): node for node in (cmds.listRelatives(
        scope, children=True, fullPath=True, type="transform") or [])}
    original_aims = [(_coordinate_identity(source), _coordinate_identity(destination))
                     for destination, source in plan["aims"].items()]
    created = []
    chunk = "Aminate Add Rig Scale " + uuid.uuid4().hex

    def create(kind, name, **kwargs):
        node = cmds.createNode(kind, name=name, skipSelect=True, **kwargs)
        created.append(_native_uuid(node))
        return node

    try:
        cmds.undoInfo(openChunk=True, chunkName=chunk)
        try:
            group = _native_node(create("transform", prefix + "#", parent=scope))
            _native_local_dag(plan["container"], scope)
            _native_require(_fixed_attr(plan["container"] + ".inheritsTransform", True),
                            "the rig container does not inherit the character frame")
            cmds.parent(plan["container"], group, relative=True)
            master = _identity_node(master_id)
            container = _identity_node(container_id)
            plan = _native_coordinate_plan(master, group)
            native = _NativeCoordinates(scope, group, plan, prefix, create, created)
            replacements = native.aim_inputs()
            _native_affected_closure(replacements.values(), replacements)
            replaced = []
            for destination, source in replacements.items():
                _native_require(not cmds.getAttr(destination, lock=True), "locked native aim destination")
                original = plan["aims"][destination]
                _native_require(_exact_input(original, destination), "native aim changed during setup")
                replaced.append(tuple(map(_coordinate_identity, (original, destination, source))))
                cmds.connectAttr(source, destination, force=True)

            _add_scale_driver(master, multiplier)
            driver = master + "." + _SCALE
            for axis in _AXES:
                cmds.connectAttr(driver, group + ".scale" + axis)
            for attr in (*_NATIVE_WRAPPER_CONSTANTS, "offsetParentMatrix"):
                cmds.setAttr(group + "." + attr, lock=True)
            _native_wrapper_frame(group)
            if autokey:
                cmds.autoKeyframe(state=False)
            try:
                _native_exact_points(samples)
                cmds.setAttr(driver, 0.5)
                siblings, detached, rendered = _native_placement(samples, scope, container, origin)
                cmds.setAttr(driver, 1.0)
                branches = [container]
                sibling_records = []
                for sibling in siblings:
                    identity = _native_uuid(sibling)
                    cmds.parent(sibling, group, relative=True)
                    sibling = _identity_node(identity)
                    branches.append(sibling)
                    edges, _ = _native_mesh_consumers(sibling, scope)
                    sibling_records.append((identity, edges))
                _native_scope_consumers([*branches, *rendered], scope)
                detached_records = []
                correction = native.output_scale_matrix(group + ".scaleX", detached=True) if detached else None
                for branch, edges in detached.items():
                    target = branch + ".offsetParentMatrix"
                    inherit_lock = cmds.getAttr(branch + ".inheritsTransform", lock=True)
                    offset_lock = cmds.getAttr(target, lock=True)
                    cmds.setAttr(target, lock=False)
                    cmds.connectAttr(correction, target)
                    cmds.setAttr(target, lock=offset_lock)
                    detached_records.append((_native_uuid(branch), inherit_lock, offset_lock, edges))
                rendered_records = []
                correction = native.output_scale_matrix(group + ".scaleX", detached=False) if rendered else None
                for branch, edges in rendered.items():
                    target = branch + ".offsetParentMatrix"
                    offset_lock = cmds.getAttr(target, lock=True)
                    cmds.setAttr(target, lock=False)
                    cmds.connectAttr(correction, target)
                    cmds.setAttr(target, lock=offset_lock)
                    rendered_records.append((_native_uuid(branch), offset_lock, edges))
                factors = (1.0, 0.1, 0.25, 0.5, 2.0, 5.0, 1.0)
                _native_exact_points(samples)
                worst = 0.0
                for factor in factors[1:]:
                    cmds.setAttr(driver, factor)
                    worst = max(worst, _verify(samples, origin, factor))
                _native_exact_points(samples)
                if multiplier is not None:
                    worst = max(worst, _set_verified_scale(driver, multiplier, samples, origin, multiplier))
                    factors += (multiplier,)
            finally:
                if autokey:
                    cmds.autoKeyframe(state=True)

            current_objects = _native_objects()
            old_after = {identity: current_objects[identity] for identity in original_objects}
            _native_require(all(len(old_after[identity]) == len(nodes) for identity, nodes in original_objects.items())
                            and set(_native_graph_edges(old_after)) == set(original_edges) - set(original_aims),
                            "setup changed an unplanned original graph edge")
            owned = set(current_objects) - set(original_objects)
            _native_require(owned and set(created) <= owned, "native setup node identity changed")
            created[:] = sorted(owned)
            owned_nodes = list(map(_identity_node, created))
            cmds.addAttr(group, longName=_OWNER, dataType="string")
            cmds.setAttr(group + "." + _OWNER, _NATIVE_VERSION, type="string", lock=True)
            cmds.addAttr(group, longName=_MASTER, attributeType="message")
            cmds.connectAttr(master + ".message", group + "." + _MASTER)
            cmds.addAttr(group, longName=_UTILITIES, attributeType="message", multi=True)
            for index, node in enumerate(node for node in owned_nodes if node != group):
                cmds.connectAttr(node + ".message", "{}.{}[{}]".format(group, _UTILITIES, index))
            manifest = dict(scope=_native_uuid(scope), branches=list(map(_native_uuid, branches)),
                            nodes=_native_nodes_state(owned_nodes), edges=_native_graph_edges(current_objects, owned),
                            constants=list(native.static.items()), detached=detached_records, replaced=replaced,
                            sibling_consumers=sibling_records, rendered=rendered_records)
            cmds.addAttr(group, longName=_NATIVE_PLAN, dataType="string")
            cmds.setAttr(group + "." + _NATIVE_PLAN, json.dumps(manifest), type="string", lock=True)
            _native_require(_owned_native(group, master, scope), "native ownership readback failed")
        finally:
            cmds.undoInfo(closeChunk=True)
        report.update(status="added", master_control=master, rig_scale_plug=driver, rig_scale_visible=multiplier is None,
                      skin_branches=branches, scale_signal_count=1, mesh_attachment_count=len(detached),
                      owned_nodes=[group] + [node for node in owned_nodes if node != group],
                      verification={"scales": list(factors), "max_world_error": worst,
                                    "point_count": sum(len(points) for _, _, points in samples)},
                      usage_note=_NATIVE_FRAME_NOTE,
                      reason="Rig Scale added and verified. Adjust Rig Scale on the master control.")
        if multiplier is not None:
            _report_scaled(report, multiplier, 1.0, multiplier)
    except Exception as exc:
        if created:
            failed_objects = _native_objects()
            new_identities = set(failed_objects) - set(original_objects)
            if cmds.undoInfo(query=True, undoName=True) != chunk:
                raise RuntimeError("Cannot safely undo the unfinished native Rig Scale setup.") from exc
            cmds.undo()
            cmds.select(clear=True)
            restored_objects = _native_objects()
            if (not cmds.undoInfo(query=True, redoQueueEmpty=True)
                    or new_identities & set(restored_objects)
                    or set(restored_objects) != set(original_objects)
                    or any(len(restored_objects[identity]) != len(nodes) for identity, nodes in original_objects.items())
                    or _native_graph_edges(restored_objects) != original_edges
                    or cmds.objExists(original_master + "." + _SCALE)
                    or any(_identity_node(identity) != path for identity, path in original_branches.items())):
                raise RuntimeError("Maya did not restore the pre-setup native Rig Scale graph.") from exc
            _native_exact_points(samples)
            if not modified:
                cmds.file(modified=False)
        if isinstance(exc, _VerificationFailure):
            failure = exc.node
            path = _identity_node(failure["uuid"])
            report["failed_nodes"].append({**failure, "path": path})
        report.update(status="unsupported", supported=False, reason=str(exc))
    finally:
        if om.MGlobal.getActiveSelectionList().getSelectionStrings() != selected.getSelectionStrings():
            om.MGlobal.setActiveSelectionList(selected)
    return report


def _checked_geometry(master, scope):
    descendants = cmds.listRelatives(scope, allDescendents=True, fullPath=True,
                                    type=("mesh", "nurbsCurve", "nurbsSurface", "follicle")) or []
    shapes = {"mesh": [], "nurbsCurve": [], "nurbsSurface": [], "follicle": []}
    for node in descendants:
        if not cmds.getAttr(node + ".intermediateObject"):
            shapes[cmds.nodeType(node)].append(node)
    # Retain hidden controllers inside the master or an attached follicle,
    # even when their current IK/FK display mode has hidden them.
    follicle_parents = {_parent(f) for f in shapes["follicle"]}
    curves = [
        curve for curve in shapes["nurbsCurve"]
        if _inside(curve, master)
        or any(_inside(curve, parent) for parent in follicle_parents)
        or _curve_control_evidence(curve, scope)
    ]
    meshes = shapes["mesh"]
    if not meshes:
        raise _Unsupported("The character root contains no output meshes.")
    if not any(_parent(curve) == master for curve in curves):
        raise _Unsupported("Choose the rig's master control with a NURBS curve shape.")
    # Temporarily hidden surfaces must satisfy the same whole-character check.
    surfaces = shapes["nurbsSurface"]
    checked = [(node, typ) for typ, nodes in (("mesh", meshes), ("nurbsCurve", curves),
                                             ("nurbsSurface", surfaces)) for node in nodes]
    if any(_path(node).isInstanced() for node, _ in checked):
        raise _Unsupported("The character contains instanced meshes, curves or surfaces.")
    return shapes["follicle"], meshes, curves, surfaces, checked


def _inspect(master_control, character_root):
    report = {
        "status": "unsupported", "supported": False, "reason": "",
        "master_control": None, "character_root": None,
        "mesh_count": 0, "control_curve_count": 0, "surface_count": 0, "attachments": [], "skin_branches": [],
        "failed_nodes": [], "scale_signal_count": 0, "mesh_attachment_count": 0,
    }
    if cmds is None or om is None:
        report["reason"] = "Live Rig Scale setup requires Maya."
        return report, [], None
    try:
        master = _resolve_transform(master_control, "master control")
        scope = (_resolve_transform(character_root, "character root") if character_root
                 else "|" + master.split("|")[1])
        report.update(master_control=master, character_root=scope)
        if not _inside(master, scope):
            raise _Unsupported("The character root must contain the master control.")
        parent = _parent(master)
        if cmds.attributeQuery(_SCALE, node=master, exists=True):
            native = _native_owner_candidates(master)
            if native:
                owned = _owned_native(next(iter(native)), master, scope if character_root else None) if len(native) == 1 else None
            else:
                owned = _owned_setup(master, parent, scope if character_root else None)
            if not owned:
                raise _Unsupported("The master already has a rigScale attribute outside a verified Aminate setup.")
            owned_nodes, branches, signal_count, mesh_count, mesh_scope = owned
            plug = master + "." + _SCALE
            report.update(status="already_added", supported=True, owned_nodes=owned_nodes, skin_branches=branches,
                          scale_signal_count=signal_count, mesh_attachment_count=mesh_count,
                          character_root=mesh_scope or scope,
                          rig_scale_plug=plug,
                          rig_scale_visible=cmds.getAttr(plug, keyable=True) or cmds.getAttr(plug, channelBox=True),
                          reason="Aminate Rig Scale is already installed on this master.")
            if native:
                report["usage_note"] = _NATIVE_FRAME_NOTE
            elif parent and cmds.objExists(parent + "." + _STATIC_SURFACE_PLAN):
                report["usage_note"] = _STATIC_SURFACE_FRAME_NOTE
            return report, [], None
        _local_node(master)
        if parent:
            _local_node(parent)
        if not cmds.getAttr(master + ".inheritsTransform") or _incoming(master + ".inheritsTransform"):
            raise _Unsupported("The master control does not reliably inherit its parent transform.")
        follicles, meshes, curves, surfaces, checked = _checked_geometry(master, scope)
        attachments = _attachment_plan(follicles, curves, meshes, master, scope)
        report.update(
            status="ready", supported=True, mesh_count=len(meshes), control_curve_count=len(curves),
            surface_count=len(surfaces),
            attachments=attachments, skin_branches=_skin_branch_plan(meshes, master, parent, scope),
            reason="Ready to verify uniform scale on this character's meshes, controls and surfaces.",
        )
        return report, checked, parent
    except (_Unsupported, RuntimeError, ValueError) as exc:
        report["reason"] = str(exc)
        return report, [], None


def analyze(master_control, character_root=None):
    """Inspect a selected master and return a JSON-safe report without editing."""
    return _inspect(master_control, character_root)[0]


def _point_samples(checked):
    _force_evaluation()
    samples = []
    for node, typ in checked:
        obj = _path(node).node()
        points = _points(obj, typ)
        samples.append((obj, typ, points))
    if not any(len(points) for _, _, points in samples):
        raise _Unsupported("The character has no measurable geometry.")
    return samples


def _points(obj, typ):
    path = om.MDagPath.getAPathTo(obj)
    if typ == "mesh":
        return om.MFnMesh(path).getPoints(om.MSpace.kWorld)
    if typ == "nurbsSurface":
        return om.MFnNurbsSurface(path).cvPositions(om.MSpace.kWorld)
    return om.MFnNurbsCurve(path).cvPositions(om.MSpace.kWorld)


def _verify(samples, origin, factor):
    _force_evaluation()
    worst = 0.0
    for obj, typ, before in samples:
        after = _points(obj, typ)
        if len(after) != len(before):
            path = om.MDagPath.getAPathTo(obj).fullPathName()
            raise _VerificationFailure("Scaling changes the point count on {}.".format(path),
                                       obj, typ, factor, None)
        for a, b in zip(before, after):
            # A scalar group at the original parent's origin has the same
            # world-space effect even if that parent is rotated or scaled.
            delta = tuple(b[i] - (origin[i] + (a[i] - origin[i]) * factor) for i in range(3))
            error = math.sqrt(sum(v * v for v in delta))
            extent = max(abs(a[i] - origin[i]) for i in range(3))
            if not math.isfinite(error) or error > 1e-4 + extent * 2e-5:
                raise _VerificationFailure(
                    "Scale {} could not be verified on {} (world-space error {:.5g})."
                    .format(factor, om.MDagPath.getAPathTo(obj).fullPathName(), error),
                    obj, typ, factor, error if math.isfinite(error) else None,
                )
            worst = max(worst, error)
    return worst


def _force_evaluation():
    # Cached parallel outputs can survive a graph edit until Maya evaluates
    # again. In GUI Maya settle the viewport as well before sampling.
    cmds.dgdirty(allPlugs=True)
    if not cmds.about(batch=True):
        cmds.refresh(force=True)


def _create_attachment(plan, name, create):
    relative = create("multMatrix", name + "_relativeMatrix")
    decomposed = create("decomposeMatrix", name + "_decompose")
    cmds.connectAttr(plan["source"] + ".worldMatrix[0]", relative + ".matrixIn[0]")
    if plan["parent"]:
        cmds.connectAttr(plan["parent"] + ".worldInverseMatrix[0]", relative + ".matrixIn[1]")
    cmds.connectAttr(relative + ".matrixSum", decomposed + ".inputMatrix")
    ratio = create("multiplyDivide", name + "_preserveScale")
    for axis, value in zip(_AXES, plan["ratios"]):
        plug = plan["transform"] + ".scale" + axis
        locked = cmds.getAttr(plug, lock=True)
        if locked:
            cmds.setAttr(plug, lock=False)
        cmds.setAttr(ratio + ".input2" + axis, value)
        cmds.connectAttr(decomposed + ".outputScale" + axis, ratio + ".input1" + axis)
        cmds.connectAttr(ratio + ".output" + axis, plug)
        if locked:
            cmds.setAttr(plug, lock=True)
    return [relative, decomposed, ratio]


def _create_scale_signals(plan, master, driver, group, scope, name, create):
    relay = create("multiplyDivide", name)
    manifest = {}
    for axis, targets in plan.items():
        source = master + ".scale" + axis
        cmds.connectAttr(source, relay + ".input1" + axis)
        cmds.connectAttr(driver, relay + ".input2" + axis)
        for target in targets:
            cmds.disconnectAttr(source, target)
            cmds.connectAttr(relay + ".output" + axis, target)
        manifest[axis] = sorted(_plug_identity(target) for target in targets)
    cmds.addAttr(group, longName=_SCALE_SIGNALS, dataType="string")
    cmds.setAttr(group + "." + _SCALE_SIGNALS, json.dumps(manifest), type="string", lock=True)
    cmds.addAttr(group, longName=_SCALE_SIGNAL_SCOPE, attributeType="message")
    cmds.connectAttr(scope + ".message", group + "." + _SCALE_SIGNAL_SCOPE)
    cmds.setAttr(group + "." + _SCALE_SIGNAL_SCOPE, lock=True)
    return relay


def _add_scale_driver(master, multiplier):
    cmds.addAttr(master, longName=_SCALE, niceName="Rig Scale", attributeType="double",
                 minValue=_MIN_SCALE, defaultValue=1.0, keyable=multiplier is None)


def _set_verified_scale(plug, value, samples, origin, factor):
    cmds.setAttr(plug, value)
    if cmds.getAttr(plug) != value:
        raise _Unsupported("Maya did not retain the requested Rig Scale value.")
    return _verify(samples, origin, factor)


def _report_scaled(report, multiplier, previous, result):
    report.update(status="scaled", multiplier=multiplier, previous_scale=previous, resulting_scale=result,
                  reason="Character size multiplied by {:.8g} and verified.".format(multiplier))
    if report.get("usage_note") == _NATIVE_FRAME_NOTE and not report["rig_scale_visible"]:
        report["usage_note"] = "Keep the outer scene frame at scale 1."


def _require_scale_undo():
    if not cmds.undoInfo(query=True, state=True):
        raise _Unsupported("Enable Maya Undo before changing Rig Scale.")
    if not cmds.undoInfo(query=True, redoQueueEmpty=True):
        raise _Unsupported("Finish or clear the pending Maya Redo before changing Rig Scale.")


def _require_owned_scale_edit(report):
    master = report["master_control"]
    group, *utilities = report["owned_nodes"]
    _local_node(master)
    _local_node(group)
    version = cmds.getAttr(group + "." + _OWNER)
    if version in (_NATIVE_VERSION, _SPLINE_VERSION, _COORDINATE_VERSION, _STATIC_SURFACE_VERSION):
        return
    # Earlier setups only check necessary wires on discovery. Refuse new
    # consumers and altered wrapper frames before changing their scale.
    driver = report["rig_scale_plug"]
    expected = [group + ".scale" + axis for axis in _AXES]
    if cmds.objExists(group + "." + _SCALE_SIGNALS):
        relay = utilities.pop()
        signals = json.loads(cmds.getAttr(group + "." + _SCALE_SIGNALS))
        expected.extend(relay + ".input2" + axis for axis in signals)
        if len(_data_edges(relay)) != report["scale_signal_count"]:
            raise _Unsupported("The Aminate scale relay has additional connections.")
    if (len(_outgoing(driver)) != len(expected) or not all(_exact_input(driver, plug) for plug in expected)
            or _data_edges(group)
            or set(cmds.listRelatives(group, children=True, fullPath=True) or [])
            != {master, *report["skin_branches"]}
            or not all(_fixed_attr(group + "." + attr, [value] if isinstance(value, tuple) else value)
                       for attr, value in _NATIVE_WRAPPER_CONSTANTS.items())
            or _incoming(group + ".offsetParentMatrix") or not _identity_matrix(group + ".offsetParentMatrix")):
        raise _Unsupported("The Aminate scale wrapper has been altered.")
    if any(len(_data_edges(node)) != (1, 3, 3)[index % 3] for index, node in enumerate(utilities)):
        raise _Unsupported("An Aminate attachment relay has additional connections.")


def _multiply_owned(report, multiplier):
    plug = report["rig_scale_plug"]
    _require_owned_scale_edit(report)
    if _incoming(plug) or cmds.getAttr(plug, lock=True) or not cmds.getAttr(plug, settable=True):
        raise _Unsupported("The existing Rig Scale is locked, connected or animated.")
    previous = cmds.getAttr(plug)
    result = previous * multiplier
    master = report["master_control"]
    minimum = cmds.attributeQuery(_SCALE, node=master, minimum=True)[0]
    maximum = math.inf
    if cmds.attributeQuery(_SCALE, node=master, maxExists=True):
        maximum = cmds.attributeQuery(_SCALE, node=master, maximum=True)[0]
    if (not math.isfinite(previous) or previous <= 0 or not math.isfinite(result)
            or not max(minimum, _MIN_SCALE) <= result <= maximum):
        raise _Unsupported("The resulting size is outside the supported Rig Scale range.")
    _, meshes, curves, surfaces, checked = _checked_geometry(master, report["character_root"])
    samples = _point_samples(checked)
    frame = _parent(report["owned_nodes"][0])
    origin = om.MPoint.kOrigin * _path(frame).inclusiveMatrix() if frame else om.MPoint.kOrigin
    selected = om.MGlobal.getActiveSelectionList()
    modified = cmds.file(query=True, modified=True)
    autokey = cmds.autoKeyframe(query=True, state=True)
    chunk = "Aminate Multiply Character Scale " + uuid.uuid4().hex
    try:
        cmds.undoInfo(openChunk=True, chunkName=chunk)
        try:
            if autokey:
                cmds.autoKeyframe(state=False)
            # Relative checks amplify the solver's low-scale numeric residual.
            # Use the same scale-1 frame and unchanged tolerances as setup.
            cmds.setAttr(plug, 1.0)
            baseline = _point_samples(checked)
            worst = _set_verified_scale(plug, previous, baseline, origin, previous)
            worst = max(worst, _set_verified_scale(plug, result, baseline, origin, result))
        finally:
            if autokey:
                cmds.autoKeyframe(state=True)
            cmds.undoInfo(closeChunk=True)
    except Exception as exc:
        if cmds.undoInfo(query=True, undoName=True) == chunk:
            try:
                cmds.undo()
                cmds.select(clear=True)
                if not cmds.undoInfo(query=True, redoQueueEmpty=True) or cmds.getAttr(plug) != previous:
                    raise RuntimeError("Maya did not restore the previous Rig Scale value.")
                _native_exact_points(samples)
                if not modified:
                    cmds.file(modified=False)
            except Exception as rollback_error:
                raise _RollbackFailure("Maya did not restore the previous character scale.") from rollback_error
        elif cmds.getAttr(plug) != previous:
            raise _RollbackFailure("Cannot safely undo the unfinished Rig Scale change.") from exc
        if isinstance(exc, _VerificationFailure):
            report["failed_nodes"].append(exc.node)
        raise
    finally:
        if om.MGlobal.getActiveSelectionList().getSelectionStrings() != selected.getSelectionStrings():
            om.MGlobal.setActiveSelectionList(selected)
    report.update(mesh_count=len(meshes), control_curve_count=len(curves), surface_count=len(surfaces),
                  verification={"scales": [1.0, previous, result], "reference_scale": 1.0,
                                "max_world_error": worst,
                                "point_count": sum(len(points) for _, _, points in samples)})
    _report_scaled(report, multiplier, previous, result)


def add_rig_scale(master_control, character_root=None):
    """Add or expose the undoable Rig Scale control on the selected master."""
    return _rig_scale(master_control, character_root)


def scale_character(master_control="", multiplier=1.5, character_root=""):
    """Multiply the current evaluated character size in one undoable edit."""
    try:
        multiplier = float(multiplier)
        if not math.isfinite(multiplier) or multiplier <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return {"status": "unsupported", "supported": False, "master_control": None,
                "reason": "Enter a positive, finite scale multiplier.", "failed_nodes": []}
    return _rig_scale(master_control, character_root, multiplier)


def _rig_scale(master_control, character_root, multiplier=None):
    report, checked, parent = _inspect(master_control, character_root)
    status = report["status"]
    if status not in ("ready", "already_added") or (
            status == "already_added" and multiplier is None and report["rig_scale_visible"]):
        return report
    try:
        _require_scale_undo()
        if status == "already_added":
            if multiplier is None:
                _require_owned_scale_edit(report)
                cmds.setAttr(report["rig_scale_plug"], keyable=True)
                report.update(status="added", rig_scale_visible=True,
                              reason="Rig Scale exposed on the master at its current value.")
            else:
                _multiply_owned(report, multiplier)
            return report
        if multiplier is not None and multiplier < _MIN_SCALE:
            raise _Unsupported("The resulting size is below the minimum Rig Scale value.")
    except _RollbackFailure:
        raise
    except (_Unsupported, RuntimeError, ValueError) as exc:
        report.update(status="unsupported", supported=False, reason=str(exc))
        return report
    original_master = master = report["master_control"]

    if not report["skin_branches"] and not report["attachments"] and report["character_root"] != master:
        try:
            native = _native_coordinate_plan(master, report["character_root"])
        except (_Unsupported, RuntimeError, TypeError, ValueError):
            native = None
        if native:
            return _add_native_coordinates(report, checked, native, multiplier)

    try:
        samples = _point_samples(checked)
        origin = om.MPoint.kOrigin * _path(parent).inclusiveMatrix() if parent else om.MPoint.kOrigin
    except (_Unsupported, RuntimeError, ValueError) as exc:
        report.update(status="unsupported", supported=False, reason=str(exc))
        return report

    selected = om.MGlobal.getActiveSelectionList()
    was_modified = cmds.file(query=True, modified=True)
    autokey = cmds.autoKeyframe(query=True, state=True)
    # A unique chunk name lets us prove this operation owns the next undo.
    chunk = "Aminate Add Rig Scale " + uuid.uuid4().hex
    prefix = ":" + master.rsplit("|", 1)[-1] + "_aminateRigScale"
    created = []
    signal_plan = {}
    coordinate_manifest = None
    original_surface_edge = None
    spline = None
    spline_manifest = None
    branches = report["skin_branches"]
    if not branches and not report["attachments"]:
        try:
            spline = _spline_plan(master, parent, report["character_root"],
                                  [node for node, kind in checked if kind == "mesh"])
        except (_Unsupported, RuntimeError, TypeError, ValueError):
            pass
        if spline:
            branches = [spline["branch"]]
            spline_manifest = _spline_manifest(report["character_root"], spline, [])
    original_branches = {branch: cmds.ls(branch, uuid=True)[0] for branch in branches}
    mesh_targets = {str(index): plan["mesh_identity"] for index, plan in enumerate(report["attachments"])
                    if "mesh_identity" in plan}

    def create(kind, name, **kwargs):
        node = cmds.createNode(kind, name=name, skipSelect=True, **kwargs)
        created.append(cmds.ls(node, uuid=True)[0])
        return node

    try:
        cmds.undoInfo(openChunk=True, chunkName=chunk)
        try:
            group = create("transform", prefix, **({"parent": parent} if parent else {}))
            group = _path(group).fullPathName()
            utilities = []
            # The source paths in the attachment plans still refer to the
            # original DAG, so wire these before the master changes path.
            for index, plan in enumerate(report["attachments"], 1):
                utilities.extend(_create_attachment(plan, prefix + "_attachment" + str(index), create))
            leaf = master.rsplit("|", 1)[-1]
            cmds.parent([master] + branches, group, relative=True)
            master = group + "|" + leaf
            moved_branches = [group + "|" + branch.rsplit("|", 1)[-1] for branch in branches]
            _add_scale_driver(master, multiplier)
            plug = master + "." + _SCALE
            for axis in _AXES:
                cmds.connectAttr(plug, group + ".scale" + axis)
            version = _BRANCH_VERSION if branches else _VERSION
            if spline:
                spline["branch"] = moved_branches[0]
                utilities.extend(_create_spline(spline, plug, group, report["character_root"], prefix, create))
                version = _SPLINE_VERSION
            if autokey:
                cmds.autoKeyframe(state=False)
            try:
                worst = _verify(samples, origin, 1.0)
                probe_scales = (0.5, 2.0, 0.1, 0.25, 5.0, 1.0)
                try:
                    for scale in probe_scales:
                        cmds.setAttr(plug, scale)
                        worst = max(worst, _verify(samples, origin, scale))
                except _VerificationFailure as first_failure:
                    if spline or first_failure.node["scale"] == 1.0 or first_failure.node["error"] is None:
                        raise
                    signal_scope = report["character_root"]
                    if signal_scope == original_master:
                        signal_scope = master
                    signal_plan = _scale_signal_plan(master, signal_scope)
                    cmds.setAttr(plug, 1.0)
                    static_surface = None
                    if (not signal_plan and not branches and not mesh_targets
                            and first_failure.node["type"] == "nurbsSurface"):
                        static_surface = _static_surface_plan(first_failure.node["path"], master, signal_scope)
                    if signal_plan:
                        utilities.append(_create_scale_signals(
                            signal_plan, master, plug, group, signal_scope, prefix + "_effectiveScale", create))
                        version = _BRANCH_SIGNAL_VERSION if branches else _SIGNAL_VERSION
                    elif static_surface:
                        if not _static_surface_scope(signal_scope, group):
                            raise _Unsupported("This surface attachment requires an identity, unanimated outer "
                                               "frame. Position the character using its master control.") from first_failure
                        shape, surface_transform, _, follicle = static_surface
                        original_surface_edge = tuple(map(_coordinate_identity, (
                            shape + ".worldMatrix[0]", follicle + ".inputWorldMatrix",
                            surface_transform + ".offsetParentMatrix")))
                        utilities.extend(_create_static_surface(
                            static_surface, group, signal_scope, report["attachments"], utilities, prefix, create))
                        version = _STATIC_SURFACE_VERSION
                    elif not branches and not report["attachments"]:
                        coordinates = _coordinate_plan(master, signal_scope, group)
                        if not coordinates:
                            raise
                        coordinate_manifest = _coordinate_manifest(signal_scope, coordinates, [])
                        utilities.extend(_create_coordinates(coordinates, plug, group, signal_scope, prefix, create))
                        version = _COORDINATE_VERSION
                    else:
                        raise
                    worst = _verify(samples, origin, 1.0)
                    probe_scales = (0.1, 0.25, 0.5, 2.0, 5.0, 1.0)
                    for scale in probe_scales:
                        cmds.setAttr(plug, scale)
                        worst = max(worst, _verify(samples, origin, scale))
                if multiplier is not None:
                    worst = max(worst, _set_verified_scale(plug, multiplier, samples, origin, multiplier))
                    probe_scales += (multiplier,)
            finally:
                if autokey:
                    cmds.autoKeyframe(state=True)
            if mesh_targets:
                version = next(key for key, base in _MESH_ATTACHMENT_VERSIONS.items() if base == version)
                for index, identity in mesh_targets.items():
                    ratio = utilities[int(index) * 3 + 2]
                    mesh_targets[index] = identity + list(cmds.getAttr(ratio + ".input2"))
                mesh_manifest = {"scope": cmds.ls(report["character_root"], uuid=True)[0],
                                 "targets": mesh_targets}
                cmds.addAttr(group, longName=_MESH_ATTACHMENTS, dataType="string")
                cmds.setAttr(group + "." + _MESH_ATTACHMENTS, json.dumps(mesh_manifest), type="string", lock=True)
                cmds.addAttr(group, longName=_MESH_ATTACHMENT_COUNT, attributeType="long", minValue=1)
                cmds.setAttr(group + "." + _MESH_ATTACHMENT_COUNT, len(mesh_targets), lock=True)
            cmds.addAttr(group, longName=_OWNER, dataType="string")
            cmds.setAttr(group + "." + _OWNER, version, type="string", lock=True)
            cmds.addAttr(group, longName=_MASTER, attributeType="message")
            cmds.connectAttr(master + ".message", group + "." + _MASTER)
            cmds.addAttr(group, longName=_UTILITIES, attributeType="message", multi=True)
            for index, node in enumerate(utilities):
                cmds.connectAttr(node + ".message", "{}.{}[{}]".format(group, _UTILITIES, index))
            cmds.addAttr(group, longName=_ATTACHMENTS, attributeType="message", multi=True)
            cmds.addAttr(group, longName=_ATTACHMENT_COUNT, attributeType="long", minValue=0)
            cmds.setAttr(group + "." + _ATTACHMENT_COUNT, len(report["attachments"]), lock=True)
            for index, plan in enumerate(report["attachments"]):
                cmds.connectAttr(plan["transform"] + ".message",
                                 "{}.{}[{}]".format(group, _ATTACHMENTS, index))
            if moved_branches:
                cmds.addAttr(group, longName=_SKIN_BRANCHES, attributeType="message", multi=True)
                cmds.addAttr(group, longName=_SKIN_BRANCH_COUNT, attributeType="long", minValue=1)
                cmds.setAttr(group + "." + _SKIN_BRANCH_COUNT, len(moved_branches), lock=True)
                for index, branch in enumerate(moved_branches):
                    cmds.connectAttr(branch + ".message", "{}.{}[{}]".format(group, _SKIN_BRANCHES, index))
            if multiplier is not None and not _owned_setup(master, group, None):
                raise _Unsupported("The Aminate Rig Scale ownership readback failed.")
        finally:
            cmds.undoInfo(closeChunk=True)
        report.update(status="added", master_control=master, rig_scale_plug=plug, rig_scale_visible=multiplier is None,
                      skin_branches=moved_branches,
                      scale_signal_count=(1 if spline else len(coordinate_manifest["signals"]) if coordinate_manifest
                                          else sum(map(len, signal_plan.values()))),
                      mesh_attachment_count=len(mesh_targets),
                      owned_nodes=[group] + utilities,
                      verification={"scales": list(probe_scales), "max_world_error": worst,
                                    "point_count": sum(len(a) for _, _, a in samples)},
                      reason="Rig Scale added and verified. Adjust Rig Scale on the master control.")
        if version == _STATIC_SURFACE_VERSION:
            report["usage_note"] = _STATIC_SURFACE_FRAME_NOTE
        if report["character_root"] == original_master:
            report["character_root"] = group if not parent and not character_root else master
        for plan in report["attachments"]:
            plan["source"] = master + plan["source"][len(original_master):]
        if multiplier is not None:
            _report_scaled(report, multiplier, 1.0, multiplier)
    except Exception as exc:
        if created:
            if cmds.undoInfo(query=True, undoName=True) != chunk:
                raise RuntimeError("Cannot safely undo the unfinished Rig Scale setup.") from exc
            cmds.undo()
            # A failed probe must never be offered as a Maya Redo. A
            # selection-only undo entry discards it without a scene edit.
            cmds.select(clear=True)
            if not cmds.undoInfo(query=True, redoQueueEmpty=True):
                raise RuntimeError("Cannot clear the unfinished Rig Scale redo.") from exc
            if (cmds.objExists(original_master + "." + _SCALE)
                    or any(cmds.ls(node_id, long=True) for node_id in created)
                    or any(cmds.ls(node_id, long=True) != [branch]
                           for branch, node_id in original_branches.items())
                    or any(not cmds.isConnected(original_master + ".scale" + axis, target)
                           for axis, targets in signal_plan.items() for target in targets)):
                raise RuntimeError("Maya did not remove the unfinished Rig Scale setup.") from exc
            if spline_manifest:
                original_divisor, original_length = spline_manifest["rest"]
                original_skin, original_mesh, original_world, original_target = map(_identity_plug, spline_manifest["target"])
                original_output = _identity_node(spline_manifest["output"])
                if (not _fixed_attr(_identity_plug(original_divisor), original_length)
                        or not _fixed_attr(original_output + ".translate", [(0.0, 0.0, 0.0)])
                        or not _exact_input(original_skin, original_mesh)
                        or not _exact_input(original_world, original_target)):
                    raise RuntimeError("Maya did not restore the original Rig Scale spline connections.") from exc
            if coordinate_manifest and (
                    any(not cmds.isConnected(_identity_plug(source), _identity_plug(target))
                        for _, source, target in coordinate_manifest["signals"])
                    or any(_incoming(_identity_plug(offset)) or not _identity_matrix(_identity_plug(offset))
                           or not cmds.isConnected(_identity_plug(source), _identity_plug(target))
                           for offset, _, source, target in coordinate_manifest["targets"])):
                raise RuntimeError("Maya did not restore the original Rig Scale coordinate connections.") from exc
            if original_surface_edge:
                source, destination, offset = map(_identity_plug, original_surface_edge)
                if not _exact_input(source, destination) or _incoming(offset) or not _identity_matrix(offset):
                    raise RuntimeError("Maya did not restore the original Rig Scale surface connections.") from exc
            try:
                _verify(samples, origin, 1.0)
            except Exception as verification_error:
                raise RuntimeError("Maya did not restore the pre-setup geometry.") from verification_error
            if not was_modified:
                cmds.file(modified=False)
        reason = str(exc)
        if isinstance(exc, _VerificationFailure):
            failure = exc.node
            restored = cmds.ls(failure["uuid"], long=True) or []
            if len(restored) == 1:
                reason = reason.replace(failure["path"], restored[0])
                failure["path"] = restored[0]
            report["failed_nodes"].append(failure)
        report.update(status="unsupported", supported=False, reason=reason)
    finally:
        if om.MGlobal.getActiveSelectionList().getSelectionStrings() != selected.getSelectionStrings():
            om.MGlobal.setActiveSelectionList(selected)
    return report
