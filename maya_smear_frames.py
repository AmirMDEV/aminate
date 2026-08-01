from __future__ import absolute_import, division, print_function

import json
import os
import re
import time
import uuid

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    MAYA_AVAILABLE = False

try:
    from PySide2 import QtCore, QtWidgets
except Exception:
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:
        QtCore = None
        QtWidgets = None

import maya_skinning_cleanup as skin_cleanup
import maya_selected_animation_fbx_export as selected_fbx_export


WINDOW_OBJECT_NAME = "aminateSmearFramesWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL

GENERATED_ATTR = "aminateSmearFrame"
SOURCE_ATTR = "aminateSmearSource"
FRAMES_ATTR = "aminateSmearSampleFrames"
MODE_ATTR = "aminateSmearMode"
STRENGTH_ATTR = "aminateSmearStrength"
MORPH_TARGET_ATTR = "aminateSmearMorphTarget"
BLENDSHAPE_ATTR = "aminateSmearBlendShape"
VAT_MANIFEST_ATTR = "aminateSmearVatManifest"
VERTEX_INDICES_ATTR = "aminateSmearVertexIndices"
SMEAR_ID_ATTR = "aminateSmearId"
SMEAR_NAME_ATTR = "aminateSmearName"
RANGE_START_ATTR = "aminateSmearRangeStart"
RANGE_END_ATTR = "aminateSmearRangeEnd"
CREATED_TIME_ATTR = "aminateSmearCreatedTime"
ROOT_JOINT_ATTR = "aminateSmearRootJoint"
SKIN_CLUSTER_ATTR = "aminateSmearSkinCluster"
UNREAL_CARRIER_ATTR = "aminateSmearUnrealCarrier"
CARRIER_VISIBLE_SCALE_X_ATTR = "aminateSmearVisibleScaleX"
CARRIER_VISIBLE_SCALE_Y_ATTR = "aminateSmearVisibleScaleY"
CARRIER_VISIBLE_SCALE_Z_ATTR = "aminateSmearVisibleScaleZ"
UNREAL_SCHEMA_VERSION = 1
HIDDEN_BASE_SCALE = 1.0e-4
MODE_STATIC = "static_unreal_mesh"
MODE_MORPH = "unreal_morph_target"
MODE_VAT = "unreal_morph_target_sequence"

_capture_shading_assignments = skin_cleanup._capture_shading_assignments
_apply_shading_assignments = skin_cleanup._apply_shading_assignments
_style_donate_button = skin_cleanup._style_donate_button
_open_external_url = skin_cleanup._open_external_url
_maya_main_window = skin_cleanup._maya_main_window

GLOBAL_WINDOW = None


def _short_name(node_name):
    return (node_name or "").split("|")[-1].split(":")[-1]


def _dag_path(node_name):
    selection = om.MSelectionList()
    selection.add(node_name)
    return selection.getDagPath(0)


def _mesh_shape(transform_or_shape):
    if not cmds or not transform_or_shape:
        return ""
    if cmds.nodeType(transform_or_shape) == "mesh":
        return transform_or_shape
    shapes = cmds.listRelatives(transform_or_shape, shapes=True, noIntermediate=True, fullPath=True) or []
    for shape in shapes:
        if cmds.nodeType(shape) == "mesh":
            return shape
    return ""


def _mesh_transform(transform_or_shape):
    if not cmds or not transform_or_shape:
        return ""
    if cmds.nodeType(transform_or_shape) == "mesh":
        parents = cmds.listRelatives(transform_or_shape, parent=True, fullPath=True) or []
        return parents[0] if parents else ""
    return transform_or_shape


def _parse_vertex_index(component_name):
    match = re.search(r"\.vtx\[(\d+)\]$", component_name or "")
    return int(match.group(1)) if match else None


def _selected_mesh_with_vertices():
    if not cmds:
        return "", "", []
    selection = cmds.ls(selection=True, long=True, flatten=True) or []
    vertex_components = cmds.filterExpand(selection, selectionMask=31, fullPath=True, expand=True) or []
    if vertex_components:
        mesh_node = vertex_components[0].split(".")[0]
        shape = _mesh_shape(mesh_node)
        transform = _mesh_transform(mesh_node)
        indices = sorted(
            set(
                index
                for index in (_parse_vertex_index(component) for component in vertex_components)
                if index is not None
            )
        )
        if shape and transform:
            return transform, shape, indices
    for node_name in selection:
        node_name = node_name.split(".")[0]
        shape = _mesh_shape(node_name)
        transform = _mesh_transform(node_name)
        if shape and transform:
            return transform, shape, []
    return "", "", []


def _sample_mesh_points(shape_name, frame):
    shape_path = _dag_path(shape_name)
    shape_dep = om.MFnDependencyNode(shape_path.node())
    out_mesh_plug = shape_dep.findPlug("outMesh", False)
    sample_time = om.MTime(float(frame), om.MTime.uiUnit())
    mesh_data = out_mesh_plug.asMObject(om.MDGContext(sample_time))
    if mesh_data.isNull():
        return om.MFnMesh(shape_path).getPoints(om.MSpace.kObject)
    return om.MFnMesh(mesh_data).getPoints(om.MSpace.kObject)


def _point_count(points):
    try:
        return len(points)
    except Exception:
        return points.length()


def _smear_points(previous_points, current_points, next_points, strength):
    count = _point_count(current_points)
    if _point_count(previous_points) != count or _point_count(next_points) != count:
        raise RuntimeError("Sampled frames do not share topology.")
    strength = float(strength)
    result = om.MPointArray()
    for index in range(count):
        current = current_points[index]
        motion = next_points[index] - previous_points[index]
        result.append(om.MPoint(current.x + motion.x * strength, current.y + motion.y * strength, current.z + motion.z * strength))
    return result


def _smear_selected_vertices(current_points, smear_points, vertex_indices):
    if not vertex_indices:
        return smear_points
    count = _point_count(current_points)
    if _point_count(smear_points) != count:
        raise RuntimeError("Smear points do not share topology.")
    selected = set(int(index) for index in vertex_indices if 0 <= int(index) < count)
    result = om.MPointArray()
    for index in range(count):
        result.append(smear_points[index] if index in selected else current_points[index])
    return result


def _vertex_indices_payload(vertex_indices):
    return json.dumps(sorted(set(int(index) for index in (vertex_indices or []))), separators=(",", ":"))


def _read_vertex_indices(node_name):
    if not cmds or not node_name or not cmds.objExists(node_name):
        return []
    try:
        if not cmds.attributeQuery(VERTEX_INDICES_ATTR, node=node_name, exists=True):
            return []
        value = cmds.getAttr(node_name + "." + VERTEX_INDICES_ATTR) or "[]"
        indices = json.loads(value)
        return sorted(set(int(index) for index in indices))
    except Exception:
        return []


def _ensure_attr(node_name, attr_name, attr_type="string", default=None):
    if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
        if attr_type == "bool":
            cmds.addAttr(node_name, longName=attr_name, attributeType="bool")
        elif attr_type == "double":
            cmds.addAttr(node_name, longName=attr_name, attributeType="double")
        else:
            cmds.addAttr(node_name, longName=attr_name, dataType="string")
    plug = "{0}.{1}".format(node_name, attr_name)
    if default is not None:
        if attr_type == "string":
            cmds.setAttr(plug, str(default), type="string")
        else:
            cmds.setAttr(plug, default)


def _normalize_range(start_frame, end_frame):
    start_frame = float(start_frame)
    end_frame = float(end_frame)
    if start_frame > end_frame:
        start_frame, end_frame = end_frame, start_frame
    return start_frame, end_frame


def _range_keys(start_frame, end_frame):
    start_frame, end_frame = _normalize_range(start_frame, end_frame)
    keys = [(start_frame - 1.0, 0.0), (start_frame, 1.0)]
    if end_frame > start_frame:
        keys.append((end_frame, 1.0))
    keys.append((end_frame + 1.0, 0.0))
    return keys


def _set_stepped_keys(plug_name, key_values):
    current_frame = float(cmds.currentTime(query=True))
    try:
        cmds.cutKey(plug_name, clear=True)
    except Exception:
        pass
    seen = set()
    for sample_frame, value in key_values:
        sample_frame = float(sample_frame)
        if sample_frame in seen:
            continue
        seen.add(sample_frame)
        cmds.setKeyframe(plug_name, time=sample_frame, value=float(value))
    for sample_frame in sorted(seen):
        try:
            cmds.keyTangent(
                plug_name,
                time=(sample_frame, sample_frame),
                outTangentType="step",
            )
        except Exception:
            pass
    try:
        cmds.currentTime(current_frame, edit=True, update=True)
    except Exception:
        pass


def _key_visibility_range(transform, start_frame, end_frame):
    _set_stepped_keys(transform + ".visibility", _range_keys(start_frame, end_frame))


def _first_blendshape_weight_attr(blendshape_node):
    aliases = cmds.aliasAttr(blendshape_node, query=True) or []
    for index in range(0, len(aliases), 2):
        if index + 1 >= len(aliases):
            continue
        alias_name = aliases[index]
        plug_name = aliases[index + 1]
        if plug_name.startswith("weight["):
            return "{0}.{1}".format(blendshape_node, alias_name)
    return "{0}.weight[0]".format(blendshape_node)


def _key_morph_weight(blendshape_node, frame, end_frame=None):
    weight_attr = _first_blendshape_weight_attr(blendshape_node)
    _set_stepped_keys(weight_attr, _range_keys(frame, frame if end_frame is None else end_frame))
    return weight_attr


def _blendshape_weight_attr_for_target(blendshape_node, target_name, fallback_index=0):
    target_short = _short_name(target_name)
    aliases = cmds.aliasAttr(blendshape_node, query=True) or []
    for index in range(0, len(aliases), 2):
        if index + 1 >= len(aliases):
            continue
        alias_name = aliases[index]
        plug_name = aliases[index + 1]
        if not plug_name.startswith("weight["):
            continue
        if alias_name == target_short or alias_name.endswith(target_short):
            return "{0}.{1}".format(blendshape_node, alias_name)
    return "{0}.weight[{1}]".format(blendshape_node, int(fallback_index))


def _set_mesh_points(transform, points):
    shape = _mesh_shape(transform)
    if not shape:
        raise RuntimeError("{0} does not contain a mesh shape.".format(_short_name(transform)))
    mesh_fn = om.MFnMesh(_dag_path(shape))
    mesh_fn.setPoints(points, om.MSpace.kObject)
    return shape


def _key_unreal_carrier_scale(root_joint, range_start, range_end):
    """Hide the overlay outside its range without damaging mesh normals."""
    range_start, range_end = _normalize_range(range_start, range_end)
    scale_attrs = (
        ("X", CARRIER_VISIBLE_SCALE_X_ATTR),
        ("Y", CARRIER_VISIBLE_SCALE_Y_ATTR),
        ("Z", CARRIER_VISIBLE_SCALE_Z_ATTR),
    )
    for axis, visible_attr in scale_attrs:
        visible_scale = float(_read_attr(root_joint, visible_attr, 1.0) or 1.0)
        key_values = [
            (range_start - 1.0, visible_scale * HIDDEN_BASE_SCALE),
            (range_start, visible_scale),
            (range_end, visible_scale),
            (range_end + 1.0, visible_scale * HIDDEN_BASE_SCALE),
        ]
        _set_stepped_keys("{0}.scale{1}".format(root_joint, axis), key_values)


def _sanitize_file_stem(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return value.strip("._-") or "Aminate_Smear"


def _read_attr(node_name, attr_name, default=None):
    if not cmds or not node_name or not cmds.objExists(node_name):
        return default
    try:
        if not cmds.attributeQuery(attr_name, node=node_name, exists=True):
            return default
        value = cmds.getAttr(node_name + "." + attr_name)
        return default if value is None else value
    except Exception:
        return default


def _write_smear_metadata(
    output_node,
    source_transform,
    mode,
    strength,
    sample_frames,
    range_start,
    range_end,
    vertex_indices,
    display_name=None,
):
    range_start, range_end = _normalize_range(range_start, range_end)
    display_name = display_name or _short_name(output_node)
    _ensure_attr(output_node, GENERATED_ATTR, "bool", 1)
    _ensure_attr(output_node, SOURCE_ATTR, "string", source_transform)
    _ensure_attr(output_node, FRAMES_ATTR, "string", ",".join("{0:g}".format(float(value)) for value in sample_frames))
    _ensure_attr(output_node, MODE_ATTR, "string", mode)
    _ensure_attr(output_node, STRENGTH_ATTR, "double", float(strength))
    _ensure_attr(output_node, VERTEX_INDICES_ATTR, "string", _vertex_indices_payload(vertex_indices))
    _ensure_attr(output_node, SMEAR_ID_ATTR, "string", uuid.uuid4().hex)
    _ensure_attr(output_node, SMEAR_NAME_ATTR, "string", display_name)
    _ensure_attr(output_node, RANGE_START_ATTR, "double", range_start)
    _ensure_attr(output_node, RANGE_END_ATTR, "double", range_end)
    _ensure_attr(output_node, CREATED_TIME_ATTR, "double", time.time())


def _create_unreal_carrier_skin(base, range_start, range_end):
    """Give a morph overlay the minimal skeleton Unreal requires."""
    selection_before = cmds.ls(selection=True, long=True) or []
    root_joint = ""
    skin_cluster = ""
    try:
        cmds.select(clear=True)
        root_joint = cmds.joint(name="{0}_ROOT".format(_short_name(base)))
        try:
            matrix = cmds.xform(base, query=True, worldSpace=True, matrix=True)
            cmds.xform(root_joint, worldSpace=True, matrix=matrix)
        except Exception:
            pass
        for axis, visible_attr in (
            ("X", CARRIER_VISIBLE_SCALE_X_ATTR),
            ("Y", CARRIER_VISIBLE_SCALE_Y_ATTR),
            ("Z", CARRIER_VISIBLE_SCALE_Z_ATTR),
        ):
            visible_scale = float(cmds.getAttr("{0}.scale{1}".format(root_joint, axis)))
            _ensure_attr(root_joint, visible_attr, "double", visible_scale)
        skin_cluster = cmds.skinCluster(
            root_joint,
            base,
            toSelectedBones=True,
            bindMethod=0,
            skinMethod=0,
            normalizeWeights=1,
            maximumInfluences=1,
            obeyMaxInfluences=True,
            name="{0}_SKIN".format(_short_name(base)),
        )[0]
        _key_unreal_carrier_scale(root_joint, range_start, range_end)
        _ensure_attr(base, ROOT_JOINT_ATTR, "string", root_joint)
        _ensure_attr(base, SKIN_CLUSTER_ATTR, "string", skin_cluster)
        _ensure_attr(base, UNREAL_CARRIER_ATTR, "bool", 1)
        return root_joint, skin_cluster
    finally:
        try:
            cmds.select(selection_before, replace=True)
        except Exception:
            pass


def _unreal_import_script():
    return '''"""Run this file inside Unreal Editor's Python console.

It imports every FBX beside aminate_smears.json as a Skeletal Mesh with
animations and morph targets enabled. Change DESTINATION if needed.
"""
import json
import os
import unreal

DESTINATION = "/Game/Aminate/SmearFrames"
ROOT = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(ROOT, "aminate_smears.json")

with open(MANIFEST, "r", encoding="utf-8") as handle:
    data = json.load(handle)

tasks = []
for smear in data.get("smears", []):
    filename = os.path.join(ROOT, smear["fbx"])
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", DESTINATION)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", False)

    options = unreal.FbxImportUI()
    options.set_editor_property("import_mesh", True)
    options.set_editor_property("import_animations", True)
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    options.skeletal_mesh_import_data.set_editor_property("import_morph_targets", True)
    task.set_editor_property("options", options)
    tasks.append(task)

unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
for task in tasks:
    unreal.log("Aminate imported: {0}".format(task.get_editor_property("imported_object_paths")))
'''


def _unreal_import_readme():
    return """AMINATE SMEAR FRAMES -> UNREAL ENGINE

What is in this folder
1. One FBX for each saved smear overlay.
2. aminate_smears.json: the exact Maya frame ranges, FPS, units and names.
3. import_aminate_smears.py: an Unreal Editor Python helper.

Easy import
1. In Unreal, enable the Python Editor Script Plugin.
2. Open Output Log and choose Python.
3. Run: exec(open(r"FULL_PATH_TO_THIS_FOLDER/import_aminate_smears.py").read())
4. Open the imported Skeletal Mesh and check Morph Target Previewer.
5. Open the imported Animation Sequence. The morph curve is 1 inside the saved
   smear range and 0 outside it.
6. Play this overlay animation at the same time as the character animation.

Manual import
1. Import an FBX as Skeletal Mesh.
2. Turn on Import Animations and Import Morph Targets.
3. Keep the animation frame rate from aminate_smears.json.

Why it is a separate overlay
The mesh keeps healthy full-size geometry and the one-joint carrier scales
almost to zero outside the chosen frames. During the range, the joint returns
to its rest scale and the morph curve shows the sculpted smear. This avoids
relying on FBX visibility keys, which are not a dependable Unreal handoff.
"""


def _unlock_for_viewport_edit(transform):
    for attr_name in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v"):
        plug = "{0}.{1}".format(transform, attr_name)
        if not cmds.objExists(plug):
            continue
        try:
            cmds.setAttr(plug, lock=False)
        except Exception:
            pass
        try:
            cmds.setAttr(plug, keyable=True, channelBox=True)
        except Exception:
            pass
    for attr_name, value in (("template", 0), ("overrideEnabled", 0), ("overrideDisplayType", 0)):
        plug = "{0}.{1}".format(transform, attr_name)
        if cmds.objExists(plug):
            try:
                cmds.setAttr(plug, lock=False)
                cmds.setAttr(plug, value)
            except Exception:
                pass


def _select_vertex_indices(transform, vertex_indices):
    if not vertex_indices:
        cmds.select(transform, replace=True)
        return
    components = ["{0}.vtx[{1}]".format(transform, index) for index in vertex_indices]
    cmds.select(components, replace=True)
    try:
        cmds.selectMode(component=True)
        cmds.selectType(polymeshVertex=True)
    except Exception:
        pass


class SmearFrameController(object):
    def __init__(self):
        self.last_created = ""
        self.saved_smears = []
        self.refresh_saved_smears()

    def refresh_saved_smears(self):
        self.saved_smears = []
        if not cmds:
            return []
        for node_name in cmds.ls(type="transform", long=True) or []:
            if not _read_attr(node_name, GENERATED_ATTR, False):
                continue
            if not cmds.attributeQuery(FRAMES_ATTR, node=node_name, exists=True):
                continue
            self.saved_smears.append(self.smear_info(node_name))
        self.saved_smears.sort(
            key=lambda item: (float(item.get("created_time") or 0.0), item.get("name") or ""),
            reverse=True,
        )
        if not self.last_created or not cmds.objExists(self.last_created):
            self.last_created = self.saved_smears[0]["node"] if self.saved_smears else ""
        return list(self.saved_smears)

    def smear_info(self, output_node):
        range_start = float(_read_attr(output_node, RANGE_START_ATTR, 0.0) or 0.0)
        range_end = float(_read_attr(output_node, RANGE_END_ATTR, range_start) or range_start)
        return {
            "node": output_node,
            "id": _read_attr(output_node, SMEAR_ID_ATTR, "") or "",
            "name": _read_attr(output_node, SMEAR_NAME_ATTR, _short_name(output_node)) or _short_name(output_node),
            "mode": _read_attr(output_node, MODE_ATTR, MODE_STATIC) or MODE_STATIC,
            "source": _read_attr(output_node, SOURCE_ATTR, "") or "",
            "range_start": range_start,
            "range_end": range_end,
            "created_time": float(_read_attr(output_node, CREATED_TIME_ATTR, 0.0) or 0.0),
            "morph_target": _read_attr(output_node, MORPH_TARGET_ATTR, "") or "",
            "blendshape": _read_attr(output_node, BLENDSHAPE_ATTR, "") or "",
            "root_joint": _read_attr(output_node, ROOT_JOINT_ATTR, "") or "",
        }

    def selected_mesh_label(self):
        transform, _shape, vertex_indices = _selected_mesh_with_vertices()
        if not transform:
            return "No mesh selected"
        if vertex_indices:
            return "{0} ({1} selected vertices)".format(_short_name(transform), len(vertex_indices))
        return _short_name(transform)

    def create_from_selection(
        self,
        frame=None,
        previous_offset=1.0,
        next_offset=1.0,
        strength=0.5,
        key_visibility=True,
        mode=MODE_STATIC,
        range_start=None,
        range_end=None,
        display_name=None,
    ):
        if not MAYA_AVAILABLE or not cmds:
            return False, "Smear Frames must run inside Maya.", ""
        source_transform, source_shape, vertex_indices = _selected_mesh_with_vertices()
        if not source_transform or not source_shape:
            return False, "Select one animated mesh first.", ""
        mode = mode or MODE_STATIC
        if mode not in (MODE_STATIC, MODE_MORPH, MODE_VAT):
            return False, "Unknown smear output mode: {0}".format(mode), ""
        frame = float(cmds.currentTime(query=True) if frame is None else frame)
        previous_frame = frame - abs(float(previous_offset or 1.0))
        next_frame = frame + abs(float(next_offset or 1.0))
        range_is_default = range_start is None and range_end is None
        if mode == MODE_VAT and range_is_default:
            range_start = previous_frame
            range_end = next_frame
        else:
            range_start = frame if range_start is None else float(range_start)
            range_end = frame if range_end is None else float(range_end)
        range_start, range_end = _normalize_range(range_start, range_end)
        shading = _capture_shading_assignments(source_transform, source_shape)
        if mode == MODE_VAT:
            return self._create_vat_morph_sequence_handoff(
                source_transform,
                source_shape,
                frame,
                previous_frame,
                next_frame,
                previous_offset,
                next_offset,
                strength,
                shading,
                key_visibility,
                vertex_indices,
                range_start,
                range_end,
                display_name,
            )
        previous_points = _sample_mesh_points(source_shape, previous_frame)
        current_points = _sample_mesh_points(source_shape, frame)
        next_points = _sample_mesh_points(source_shape, next_frame)
        smear_points = _smear_points(previous_points, current_points, next_points, strength)
        smear_points = _smear_selected_vertices(current_points, smear_points, vertex_indices)
        if mode == MODE_MORPH:
            return self._create_morph_target_handoff(
                source_transform,
                source_shape,
                frame,
                previous_frame,
                next_frame,
                strength,
                smear_points,
                shading,
                key_visibility,
                vertex_indices,
                range_start,
                range_end,
                display_name,
            )
        return self._create_static_mesh_handoff(
            source_transform,
            source_shape,
            frame,
            previous_frame,
            next_frame,
            strength,
            smear_points,
            shading,
            key_visibility,
            vertex_indices,
            range_start,
            range_end,
            display_name,
        )

    def _create_static_mesh_handoff(
        self,
        source_transform,
        source_shape,
        frame,
        previous_frame,
        next_frame,
        strength,
        smear_points,
        shading,
        key_visibility,
        vertex_indices=None,
        range_start=None,
        range_end=None,
        display_name=None,
    ):
        duplicate = (cmds.duplicate(source_transform, name="{0}_AminateSmear_{1}".format(_short_name(source_transform), int(round(frame))), returnRootsOnly=True) or [""])[0]
        if not duplicate:
            return False, "Could not duplicate the selected mesh.", ""
        try:
            cmds.delete(duplicate, constructionHistory=True)
        except Exception:
            pass
        duplicate_shape = _mesh_shape(duplicate)
        if not duplicate_shape:
            try:
                cmds.delete(duplicate)
            except Exception:
                pass
            return False, "Duplicate did not contain a mesh shape.", ""
        _set_mesh_points(duplicate, smear_points)
        try:
            cmds.delete(duplicate, constructionHistory=True)
        except Exception:
            pass
        _apply_shading_assignments(duplicate, duplicate_shape, shading)
        range_start, range_end = _normalize_range(
            frame if range_start is None else range_start,
            frame if range_end is None else range_end,
        )
        _write_smear_metadata(
            duplicate,
            source_transform,
            MODE_STATIC,
            strength,
            (previous_frame, frame, next_frame),
            range_start,
            range_end,
            vertex_indices,
            display_name,
        )
        if key_visibility:
            _key_visibility_range(duplicate, range_start, range_end)
        self.last_created = duplicate
        self.refresh_saved_smears()
        return True, "Created static smear mesh: {0}.".format(_short_name(duplicate)), duplicate

    def _create_morph_target_handoff(
        self,
        source_transform,
        source_shape,
        frame,
        previous_frame,
        next_frame,
        strength,
        smear_points,
        shading,
        key_visibility,
        vertex_indices=None,
        range_start=None,
        range_end=None,
        display_name=None,
    ):
        base = (cmds.duplicate(source_transform, name="{0}_AminateMorphBase_{1}".format(_short_name(source_transform), int(round(frame))), returnRootsOnly=True) or [""])[0]
        if not base:
            return False, "Could not duplicate the selected mesh.", ""
        target = ""
        try:
            cmds.delete(base, constructionHistory=True)
            base_shape = _mesh_shape(base)
            if not base_shape:
                return False, "Morph base did not contain a mesh shape.", ""
            target = (cmds.duplicate(base, name="{0}_SmearTarget_{1}".format(_short_name(source_transform), int(round(frame))), returnRootsOnly=True) or [""])[0]
            if not target:
                return False, "Could not create the smear morph target.", ""
            cmds.delete(target, constructionHistory=True)
            target_shape = _set_mesh_points(target, smear_points)
            blendshape = cmds.blendShape(target, base, name="{0}_SmearMorph_BS".format(_short_name(base)), origin="local")[0]
            range_start, range_end = _normalize_range(
                frame if range_start is None else range_start,
                frame if range_end is None else range_end,
            )
            weight_attr = _key_morph_weight(blendshape, range_start, range_end)
            root_joint, skin_cluster = _create_unreal_carrier_skin(base, range_start, range_end)
            try:
                cmds.hide(target)
            except Exception:
                pass
            _apply_shading_assignments(base, base_shape, shading)
            _apply_shading_assignments(target, target_shape, shading)
            _write_smear_metadata(
                base,
                source_transform,
                MODE_MORPH,
                strength,
                (previous_frame, frame, next_frame),
                range_start,
                range_end,
                vertex_indices,
                display_name,
            )
            _ensure_attr(base, MORPH_TARGET_ATTR, "string", target)
            _ensure_attr(base, BLENDSHAPE_ATTR, "string", blendshape)
            _ensure_attr(base, ROOT_JOINT_ATTR, "string", root_joint)
            _ensure_attr(base, SKIN_CLUSTER_ATTR, "string", skin_cluster)
            _ensure_attr(target, GENERATED_ATTR, "bool", 1)
            _ensure_attr(target, MODE_ATTR, "string", MODE_MORPH)
            _ensure_attr(target, SOURCE_ATTR, "string", source_transform)
            _ensure_attr(target, VERTEX_INDICES_ATTR, "string", _vertex_indices_payload(vertex_indices))
            if key_visibility:
                _key_visibility_range(base, range_start, range_end)
            self.last_created = base
            self.refresh_saved_smears()
            return True, "Created Unreal morph overlay: {0} ({1}).".format(_short_name(base), weight_attr), base
        except Exception:
            for node_name in (base, target):
                if node_name and cmds.objExists(node_name):
                    try:
                        cmds.delete(node_name)
                    except Exception:
                        pass
            raise

    def _create_vat_morph_sequence_handoff(
        self,
        source_transform,
        source_shape,
        frame,
        previous_frame,
        next_frame,
        previous_offset,
        next_offset,
        strength,
        shading,
        key_visibility,
        vertex_indices=None,
        range_start=None,
        range_end=None,
        display_name=None,
    ):
        sample_frames = sorted(set([previous_frame, frame, next_frame]))
        base = (cmds.duplicate(source_transform, name="{0}_AminateVatBase_{1}".format(_short_name(source_transform), int(round(frame))), returnRootsOnly=True) or [""])[0]
        targets = []
        if not base:
            return False, "Could not duplicate the selected mesh.", ""
        try:
            cmds.delete(base, constructionHistory=True)
            base_shape = _mesh_shape(base)
            if not base_shape:
                return False, "VAT base did not contain a mesh shape.", ""
            for sample_frame in sample_frames:
                previous_points = _sample_mesh_points(source_shape, sample_frame - abs(float(previous_offset or 1.0)))
                current_points = _sample_mesh_points(source_shape, sample_frame)
                next_points = _sample_mesh_points(source_shape, sample_frame + abs(float(next_offset or 1.0)))
                smear_points = _smear_points(previous_points, current_points, next_points, strength)
                smear_points = _smear_selected_vertices(current_points, smear_points, vertex_indices)
                target = (cmds.duplicate(base, name="{0}_VatTarget_{1}".format(_short_name(source_transform), int(round(sample_frame))), returnRootsOnly=True) or [""])[0]
                if not target:
                    return False, "Could not create VAT morph target for frame {0:g}.".format(sample_frame)
                cmds.delete(target, constructionHistory=True)
                target_shape = _set_mesh_points(target, smear_points)
                _apply_shading_assignments(target, target_shape, shading)
                _ensure_attr(target, GENERATED_ATTR, "bool", 1)
                _ensure_attr(target, MODE_ATTR, "string", MODE_VAT)
                _ensure_attr(target, SOURCE_ATTR, "string", source_transform)
                _ensure_attr(target, VERTEX_INDICES_ATTR, "string", _vertex_indices_payload(vertex_indices))
                targets.append((sample_frame, target))
            blendshape = cmds.blendShape(*([target for _sample_frame, target in targets] + [base]), name="{0}_VatMorphSequence_BS".format(_short_name(base)), origin="local")[0]
            range_start, range_end = _normalize_range(
                previous_frame if range_start is None else range_start,
                next_frame if range_end is None else range_end,
            )
            display_frames = []
            if len(targets) <= 1 or abs(range_end - range_start) <= 1.0e-4:
                display_frames = [range_start for _item in targets]
            else:
                step = (range_end - range_start) / float(len(targets) - 1)
                display_frames = [range_start + (index * step) for index in range(len(targets))]
            for target_index, (sample_frame, target) in enumerate(targets):
                weight_attr = _blendshape_weight_attr_for_target(blendshape, target, target_index)
                key_values = [(range_start - 1.0, 0.0), (range_end + 1.0, 0.0)]
                for display_index, display_frame in enumerate(display_frames):
                    key_values.append((display_frame, 1.0 if display_index == target_index else 0.0))
                _set_stepped_keys(weight_attr, key_values)
                try:
                    cmds.hide(target)
                except Exception:
                    pass
            root_joint, skin_cluster = _create_unreal_carrier_skin(base, range_start, range_end)
            _apply_shading_assignments(base, base_shape, shading)
            manifest = {
                "mode": MODE_VAT,
                "source": source_transform,
                "base": base,
                "blendShape": blendshape,
                "frames": [float(value) for value in sample_frames],
                "displayFrames": [float(value) for value in display_frames],
                "range": [float(range_start), float(range_end)],
                "targets": [{"frame": float(sample_frame), "node": target} for sample_frame, target in targets],
                "strength": float(strength),
                "vertexIndices": json.loads(_vertex_indices_payload(vertex_indices)),
            }
            _write_smear_metadata(
                base,
                source_transform,
                MODE_VAT,
                strength,
                sample_frames,
                range_start,
                range_end,
                vertex_indices,
                display_name,
            )
            _ensure_attr(base, BLENDSHAPE_ATTR, "string", blendshape)
            _ensure_attr(base, VAT_MANIFEST_ATTR, "string", json.dumps(manifest, sort_keys=True))
            _ensure_attr(base, ROOT_JOINT_ATTR, "string", root_joint)
            _ensure_attr(base, SKIN_CLUSTER_ATTR, "string", skin_cluster)
            if key_visibility:
                _key_visibility_range(base, range_start, range_end)
            self.last_created = base
            self.refresh_saved_smears()
            return True, "Created Unreal morph overlay sequence: {0} ({1} target frame(s)).".format(_short_name(base), len(targets)), base
        except Exception:
            for _sample_frame, target in targets:
                if target and cmds.objExists(target):
                    try:
                        cmds.delete(target)
                    except Exception:
                        pass
            if base and cmds.objExists(base):
                try:
                    cmds.delete(base)
                except Exception:
                    pass
            raise

    def select_last_created(self):
        self.refresh_saved_smears()
        if self.last_created and cmds and cmds.objExists(self.last_created):
            cmds.select(self.last_created, replace=True)
            return True, "Selected {0}.".format(_short_name(self.last_created))
        return False, "No saved smear frame exists in this scene."

    def select_smear(self, output_node):
        if not output_node or not cmds or not cmds.objExists(output_node):
            return False, "Choose a saved smear first."
        self.last_created = output_node
        cmds.select(output_node, replace=True)
        return True, "Selected {0}.".format(self.smear_info(output_node)["name"])

    def edit_last_created_in_viewport(self):
        self.refresh_saved_smears()
        if not self.last_created or not cmds or not cmds.objExists(self.last_created):
            return False, "No saved smear output exists in this scene.", ""
        edit_target = self._editable_target_for_output(self.last_created)
        if not edit_target or not cmds.objExists(edit_target):
            return False, "No editable smear target was found for {0}.".format(_short_name(self.last_created)), ""
        self._hide_non_active_targets_for_edit(self.last_created, edit_target)
        _unlock_for_viewport_edit(edit_target)
        try:
            cmds.showHidden(edit_target)
        except Exception:
            try:
                cmds.setAttr(edit_target + ".visibility", 1)
            except Exception:
                pass
        vertex_indices = _read_vertex_indices(edit_target) or _read_vertex_indices(self.last_created)
        _select_vertex_indices(edit_target, vertex_indices)
        try:
            cmds.setToolTo("moveSuperContext")
        except Exception:
            pass
        if vertex_indices:
            return True, "Selected {0} editable vertices on {1}.".format(len(vertex_indices), _short_name(edit_target)), edit_target
        return True, "Selected editable smear target: {0}. Use Maya's move/rotate/scale tools to adjust it.".format(_short_name(edit_target)), edit_target

    def edit_smear_in_viewport(self, output_node):
        if output_node and cmds and cmds.objExists(output_node):
            self.last_created = output_node
        return self.edit_last_created_in_viewport()

    def finish_editing(self, output_node=None):
        output_node = output_node or self.last_created
        if not output_node or not cmds or not cmds.objExists(output_node):
            return False, "Choose a saved smear first."
        info = self.smear_info(output_node)
        targets = []
        if info["mode"] == MODE_VAT:
            targets = self._vat_targets_for_output(output_node)
        elif info["mode"] == MODE_MORPH and info["morph_target"]:
            targets = [info["morph_target"]]
        for target in targets:
            if target and cmds.objExists(target):
                try:
                    cmds.setAttr(target + ".visibility", 0)
                except Exception:
                    pass
        current_frame = float(cmds.currentTime(query=True))
        visible_now = info["range_start"] <= current_frame <= info["range_end"]
        try:
            cmds.setAttr(output_node + ".visibility", 1 if visible_now else 0)
        except Exception:
            pass
        cmds.select(output_node, replace=True)
        self.last_created = output_node
        return True, "Finished editing {0}. The saved range is {1:g} to {2:g}.".format(
            info["name"],
            info["range_start"],
            info["range_end"],
        )

    def update_smear_range(self, output_node, start_frame, end_frame, key_visibility=True):
        if not output_node or not cmds or not cmds.objExists(output_node):
            return False, "Choose a saved smear first."
        start_frame, end_frame = _normalize_range(start_frame, end_frame)
        info = self.smear_info(output_node)
        _ensure_attr(output_node, RANGE_START_ATTR, "double", start_frame)
        _ensure_attr(output_node, RANGE_END_ATTR, "double", end_frame)
        if key_visibility:
            _key_visibility_range(output_node, start_frame, end_frame)
        root_joint = info.get("root_joint") or ""
        if root_joint and cmds.objExists(root_joint):
            _key_unreal_carrier_scale(root_joint, start_frame, end_frame)
        blendshape = info.get("blendshape") or ""
        if blendshape and cmds.objExists(blendshape):
            if info["mode"] == MODE_MORPH:
                _key_morph_weight(blendshape, start_frame, end_frame)
            elif info["mode"] == MODE_VAT:
                manifest = {}
                try:
                    manifest = json.loads(_read_attr(output_node, VAT_MANIFEST_ATTR, "{}") or "{}")
                except Exception:
                    manifest = {}
                targets = manifest.get("targets") or []
                if targets:
                    display_frames = (
                        [start_frame for _item in targets]
                        if len(targets) <= 1 or abs(end_frame - start_frame) <= 1.0e-4
                        else [
                            start_frame + ((end_frame - start_frame) * index / float(len(targets) - 1))
                            for index in range(len(targets))
                        ]
                    )
                    for target_index, target_data in enumerate(targets):
                        target_name = target_data.get("node") or ""
                        weight_attr = _blendshape_weight_attr_for_target(blendshape, target_name, target_index)
                        key_values = [(start_frame - 1.0, 0.0), (end_frame + 1.0, 0.0)]
                        for display_index, display_frame in enumerate(display_frames):
                            key_values.append((display_frame, 1.0 if display_index == target_index else 0.0))
                        _set_stepped_keys(weight_attr, key_values)
                    manifest["displayFrames"] = [float(value) for value in display_frames]
                    manifest["range"] = [float(start_frame), float(end_frame)]
                    _ensure_attr(output_node, VAT_MANIFEST_ATTR, "string", json.dumps(manifest, sort_keys=True))
        self.last_created = output_node
        self.refresh_saved_smears()
        return True, "Updated {0} to show from frame {1:g} through {2:g}.".format(
            info["name"],
            start_frame,
            end_frame,
        )

    def rename_smear(self, output_node, display_name):
        if not output_node or not cmds or not cmds.objExists(output_node):
            return False, "Choose a saved smear first."
        display_name = str(display_name or "").strip()
        if not display_name:
            return False, "Type a name for this smear."
        _ensure_attr(output_node, SMEAR_NAME_ATTR, "string", display_name)
        self.last_created = output_node
        self.refresh_saved_smears()
        return True, "Renamed saved smear to {0}.".format(display_name)

    def delete_smear(self, output_node):
        if not output_node or not cmds or not cmds.objExists(output_node):
            return False, "Choose a saved smear first."
        info = self.smear_info(output_node)
        nodes = []
        if info["mode"] == MODE_VAT:
            nodes.extend(self._vat_targets_for_output(output_node))
        elif info["morph_target"]:
            nodes.append(info["morph_target"])
        nodes.extend([info.get("root_joint") or "", output_node])
        deleted = 0
        for node_name in nodes:
            if node_name and cmds.objExists(node_name):
                try:
                    cmds.delete(node_name)
                    deleted += 1
                except Exception:
                    pass
        self.last_created = ""
        self.refresh_saved_smears()
        return True, "Deleted generated smear {0} ({1} Maya node(s)).".format(info["name"], deleted)

    def _frames_per_second(self):
        time_unit = str(cmds.currentUnit(query=True, time=True) or "film")
        known = {
            "game": 15.0,
            "film": 24.0,
            "pal": 25.0,
            "ntsc": 30.0,
            "show": 48.0,
            "palf": 50.0,
            "ntscf": 60.0,
        }
        if time_unit in known:
            return known[time_unit], time_unit
        match = re.match(r"([0-9.]+)fps$", time_unit)
        return (float(match.group(1)) if match else 24.0), time_unit

    def export_unreal_bundle(self, output_directory, output_nodes=None, up_axis="Y", overwrite=False):
        if not MAYA_AVAILABLE or not cmds:
            return False, "Unreal smear export must run inside Maya.", {}
        output_directory = os.path.abspath(str(output_directory or "").strip())
        if not output_directory:
            return False, "Choose an output folder.", {}
        if not os.path.isdir(output_directory):
            try:
                os.makedirs(output_directory)
            except Exception as exc:
                return False, "Could not create the export folder: {0}".format(exc), {}
        self.refresh_saved_smears()
        output_nodes = list(output_nodes or [item["node"] for item in self.saved_smears])
        output_nodes = [node for node in output_nodes if node and cmds.objExists(node)]
        if not output_nodes:
            return False, "No saved smear frames are available to export.", {}
        selection_before = cmds.ls(selection=True, long=True) or []
        exported = []
        errors = []
        fps, time_unit = self._frames_per_second()
        timeline_start = float(cmds.playbackOptions(query=True, minTime=True))
        timeline_end = float(cmds.playbackOptions(query=True, maxTime=True))
        try:
            for output_node in output_nodes:
                info = self.smear_info(output_node)
                if info["mode"] not in (MODE_MORPH, MODE_VAT):
                    errors.append("{0}: choose Unreal Morph Overlay or Unreal Morph Sequence.".format(info["name"]))
                    continue
                root_joint = info.get("root_joint") or ""
                if not root_joint or not cmds.objExists(root_joint):
                    errors.append("{0}: Unreal carrier root is missing.".format(info["name"]))
                    continue
                smear_id = str(info.get("id") or uuid.uuid4().hex)
                stem = "{0}_{1}".format(_sanitize_file_stem(info["name"]), smear_id[:8])
                fbx_path = os.path.join(output_directory, stem + ".fbx")
                opts = selected_fbx_export.SelectedAnimationFbxOptions(
                    # The carrier already contains authored animation keys;
                    # do not ask FBX to invent whole-frame samples by default.
                    bake_animation=False,
                    include_geometry=True,
                    include_skinning=True,
                    include_blend_shapes=True,
                    include_tangents_binormals=True,
                    include_materials_textures=True,
                    embed_media=True,
                    include_cameras=False,
                    include_lights=False,
                    up_axis=str(up_axis or "Y").upper(),
                    scale_label=selected_fbx_export.UNREAL_SCALE_LABEL,
                    overwrite=bool(overwrite),
                    output_path=fbx_path,
                )
                cmds.select([root_joint, output_node], replace=True)
                result = selected_fbx_export._perform_export(
                    fbx_path,
                    options=opts,
                    cmds_api=cmds,
                    mel_api=selected_fbx_export.mel,
                )
                if not result.get("success"):
                    errors.append("{0}: {1}".format(info["name"], result.get("message") or "FBX export failed."))
                    continue
                exported.append(
                    {
                        "id": info["id"],
                        "name": info["name"],
                        "fbx": os.path.basename(fbx_path),
                        "mode": info["mode"],
                        "source": info["source"],
                        "range": [info["range_start"], info["range_end"]],
                        "blendShape": info["blendshape"],
                        "morphTarget": info["morph_target"],
                        "morphTargets": (
                            self._vat_targets_for_output(output_node)
                            if info["mode"] == MODE_VAT
                            else [info["morph_target"]]
                        ),
                        "rootJoint": _short_name(root_joint),
                    }
                )
        finally:
            try:
                cmds.select(selection_before, replace=True)
            except Exception:
                pass
        manifest = {
            "schema": "aminate.unreal-smear-bundle",
            "version": UNREAL_SCHEMA_VERSION,
            "fps": fps,
            "mayaTimeUnit": time_unit,
            "mayaLinearUnit": str(cmds.currentUnit(query=True, linear=True) or "cm"),
            "unrealUnit": "centimetres",
            "upAxis": str(up_axis or "Y").upper(),
            "timeline": [timeline_start, timeline_end],
            "smears": exported,
        }
        manifest_path = os.path.join(output_directory, "aminate_smears.json")
        script_path = os.path.join(output_directory, "import_aminate_smears.py")
        readme_path = os.path.join(output_directory, "README_IMPORT_TO_UNREAL.txt")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(_unreal_import_script())
        with open(readme_path, "w", encoding="utf-8") as handle:
            handle.write(_unreal_import_readme())
        report = {
            "manifest": manifest_path,
            "import_script": script_path,
            "readme": readme_path,
            "exported": exported,
            "errors": errors,
        }
        if not exported:
            return False, "No Unreal-ready smear FBX files were exported. {0}".format(" ".join(errors)), report
        message = "Exported {0} Unreal smear FBX file(s) plus manifest and import helper.".format(len(exported))
        if errors:
            message += " Skipped: {0}".format(" ".join(errors))
        return True, message, report

    def _vat_targets_for_output(self, output_node):
        try:
            manifest = json.loads(cmds.getAttr(output_node + "." + VAT_MANIFEST_ATTR) or "{}")
        except Exception:
            manifest = {}
        return [item.get("node") or "" for item in (manifest.get("targets") or [])]

    def _hide_non_active_targets_for_edit(self, output_node, edit_target):
        mode = ""
        try:
            if cmds.attributeQuery(MODE_ATTR, node=output_node, exists=True):
                mode = cmds.getAttr(output_node + "." + MODE_ATTR) or ""
        except Exception:
            mode = ""
        targets = []
        if mode == MODE_VAT:
            targets = self._vat_targets_for_output(output_node)
        elif mode == MODE_MORPH:
            try:
                targets = [cmds.getAttr(output_node + "." + MORPH_TARGET_ATTR) or ""]
            except Exception:
                targets = []
        if mode in (MODE_MORPH, MODE_VAT) and output_node != edit_target and cmds.objExists(output_node):
            try:
                cmds.setAttr(output_node + ".visibility", 0)
            except Exception:
                pass
        for target in targets:
            if not target or not cmds.objExists(target):
                continue
            try:
                cmds.setAttr(target + ".visibility", 1 if target == edit_target else 0)
            except Exception:
                pass

    def _editable_target_for_output(self, output_node):
        mode = ""
        try:
            if cmds.attributeQuery(MODE_ATTR, node=output_node, exists=True):
                mode = cmds.getAttr(output_node + "." + MODE_ATTR) or ""
        except Exception:
            mode = ""
        if mode == MODE_MORPH:
            try:
                return cmds.getAttr(output_node + "." + MORPH_TARGET_ATTR) or ""
            except Exception:
                return ""
        if mode == MODE_VAT:
            try:
                manifest = json.loads(cmds.getAttr(output_node + "." + VAT_MANIFEST_ATTR) or "{}")
            except Exception:
                manifest = {}
            targets = manifest.get("targets") or []
            current_frame = float(cmds.currentTime(query=True))
            best = None
            for item in targets:
                node_name = item.get("node") or ""
                if not node_name or not cmds.objExists(node_name):
                    continue
                distance = abs(float(item.get("frame", current_frame)) - current_frame)
                if best is None or distance < best[0]:
                    best = (distance, node_name)
            return best[1] if best else ""
        return output_node

    def shutdown(self):
        pass


if QtWidgets is not None:
    class SmearFrameWindow(QtWidgets.QWidget):
        def __init__(self, controller=None, parent=None, show_footer=True):
            super(SmearFrameWindow, self).__init__(parent)
            self.controller = controller or SmearFrameController()
            self.show_footer = bool(show_footer)
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Aminate Smear Frames")
            self._build_ui()

        def _build_ui(self):
            root_layout = QtWidgets.QVBoxLayout(self)
            root_layout.setContentsMargins(0, 0, 0, 0)
            scroll_area = QtWidgets.QScrollArea(self)
            scroll_area.setObjectName("aminateSmearFramesScroll")
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
            content_widget = QtWidgets.QWidget()
            content_widget.setObjectName("aminateSmearFramesContent")
            content_widget.setMinimumWidth(0)
            content_widget.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
            layout = QtWidgets.QVBoxLayout(content_widget)
            layout.setContentsMargins(10, 10, 10, 10)
            help_label = QtWidgets.QLabel(
                "Make a smear from the selected animated mesh on any frame. "
                "You can move its vertices, save several smears in the Maya scene, "
                "choose exactly when each one appears, and export Unreal morph overlays."
            )
            help_label.setWordWrap(True)
            layout.addWidget(help_label)
            self.selected_label = QtWidgets.QLabel(self.controller.selected_mesh_label())
            self.selected_label.setObjectName("aminateSmearSelectedLabel")
            self.selected_label.setWordWrap(True)
            layout.addWidget(self.selected_label)
            form = QtWidgets.QFormLayout()
            self.name_edit = QtWidgets.QLineEdit()
            self.name_edit.setObjectName("aminateSmearNameEdit")
            self.name_edit.setPlaceholderText("Example: Sword swing smear")
            self.prev_spin = QtWidgets.QDoubleSpinBox()
            self.prev_spin.setObjectName("aminateSmearPreviousOffsetSpin")
            self.prev_spin.setRange(0.1, 24.0)
            self.prev_spin.setValue(1.0)
            self.next_spin = QtWidgets.QDoubleSpinBox()
            self.next_spin.setObjectName("aminateSmearNextOffsetSpin")
            self.next_spin.setRange(0.1, 24.0)
            self.next_spin.setValue(1.0)
            self.strength_spin = QtWidgets.QDoubleSpinBox()
            self.strength_spin.setObjectName("aminateSmearStrengthSpin")
            self.strength_spin.setRange(-3.0, 3.0)
            self.strength_spin.setSingleStep(0.1)
            self.strength_spin.setValue(0.5)
            current_frame = float(cmds.currentTime(query=True)) if cmds else 1.0
            self.range_start_spin = QtWidgets.QDoubleSpinBox()
            self.range_start_spin.setObjectName("aminateSmearRangeStartSpin")
            self.range_start_spin.setRange(-100000.0, 100000.0)
            self.range_start_spin.setDecimals(2)
            self.range_start_spin.setValue(current_frame)
            self.range_end_spin = QtWidgets.QDoubleSpinBox()
            self.range_end_spin.setObjectName("aminateSmearRangeEndSpin")
            self.range_end_spin.setRange(-100000.0, 100000.0)
            self.range_end_spin.setDecimals(2)
            self.range_end_spin.setValue(current_frame)
            self.visibility_check = QtWidgets.QCheckBox("Also key Maya visibility to this range")
            self.visibility_check.setObjectName("aminateSmearVisibilityCheck")
            self.visibility_check.setChecked(True)
            self.mode_combo = QtWidgets.QComboBox()
            self.mode_combo.setObjectName("aminateSmearModeCombo")
            self.mode_combo.addItem("Unreal Morph Overlay (recommended)", MODE_MORPH)
            self.mode_combo.addItem("Unreal Morph Sequence (3 samples)", MODE_VAT)
            self.mode_combo.addItem("Maya Static Mesh", MODE_STATIC)
            form.addRow("Smear Name", self.name_edit)
            form.addRow("Previous Frame Offset", self.prev_spin)
            form.addRow("Next Frame Offset", self.next_spin)
            form.addRow("Smear Strength", self.strength_spin)
            form.addRow("Visible From Frame", self.range_start_spin)
            form.addRow("Visible Through Frame", self.range_end_spin)
            form.addRow("Output", self.mode_combo)
            form.addRow("", self.visibility_check)
            layout.addLayout(form)

            saved_label = QtWidgets.QLabel("Saved Smear Frames")
            saved_label.setObjectName("aminateSmearSavedHeading")
            layout.addWidget(saved_label)
            self.saved_list = QtWidgets.QListWidget()
            self.saved_list.setObjectName("aminateSmearSavedList")
            self.saved_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.saved_list.setMinimumHeight(110)
            self.saved_list.setToolTip("These smears are stored in the Maya scene and return after save and reopen.")
            layout.addWidget(self.saved_list)

            row = QtWidgets.QVBoxLayout()
            self.refresh_button = QtWidgets.QPushButton("Refresh Mesh And Saved Smears")
            self.refresh_button.setObjectName("aminateSmearRefreshSelectionButton")
            self.create_button = QtWidgets.QPushButton("Create And Save Smear")
            self.create_button.setObjectName("aminateSmearCreateButton")
            self.select_button = QtWidgets.QPushButton("Select Saved Smear")
            self.select_button.setObjectName("aminateSmearSelectLastButton")
            self.edit_button = QtWidgets.QPushButton("Sculpt / Edit Vertices In Viewport")
            self.edit_button.setObjectName("aminateSmearEditTargetButton")
            self.finish_edit_button = QtWidgets.QPushButton("Finish Editing")
            self.finish_edit_button.setObjectName("aminateSmearFinishEditButton")
            self.apply_range_button = QtWidgets.QPushButton("Save Name And Frame Range")
            self.apply_range_button.setObjectName("aminateSmearApplyRangeButton")
            self.export_button = QtWidgets.QPushButton("Export All Unreal Smears")
            self.export_button.setObjectName("aminateSmearExportUnrealButton")
            self.delete_button = QtWidgets.QPushButton("Delete Selected Generated Smear")
            self.delete_button.setObjectName("aminateSmearDeleteButton")
            row.addWidget(self.refresh_button)
            row.addWidget(self.create_button)
            row.addWidget(self.select_button)
            row.addWidget(self.edit_button)
            row.addWidget(self.finish_edit_button)
            row.addWidget(self.apply_range_button)
            row.addWidget(self.export_button)
            row.addWidget(self.delete_button)
            layout.addLayout(row)
            self.status_label = QtWidgets.QLabel("")
            self.status_label.setObjectName("aminateSmearStatusLabel")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)
            if self.show_footer:
                footer = QtWidgets.QVBoxLayout()
                self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
                self.brand_label.setOpenExternalLinks(False)
                self.brand_label.linkActivated.connect(lambda _url: _open_external_url(FOLLOW_AMIR_URL))
                footer.addWidget(self.brand_label, 1)
                self.donate_button = QtWidgets.QPushButton("Donate")
                _style_donate_button(self.donate_button)
                self.donate_button.clicked.connect(lambda: _open_external_url(DONATE_URL))
                footer.addWidget(self.donate_button)
                layout.addLayout(footer)
            self.refresh_button.clicked.connect(self._refresh_selection)
            self.create_button.clicked.connect(self._create)
            self.select_button.clicked.connect(self._select_last)
            self.edit_button.clicked.connect(self._edit_last)
            self.finish_edit_button.clicked.connect(self._finish_editing)
            self.apply_range_button.clicked.connect(self._apply_name_and_range)
            self.export_button.clicked.connect(self._export_unreal)
            self.delete_button.clicked.connect(self._delete_selected)
            self.saved_list.currentItemChanged.connect(self._saved_item_changed)
            scroll_area.setWidget(content_widget)
            root_layout.addWidget(scroll_area)
            self._refresh_saved_list()

        def _refresh_selection(self):
            self.selected_label.setText(self.controller.selected_mesh_label())
            self._refresh_saved_list()

        def _selected_output(self):
            item = self.saved_list.currentItem()
            if item is not None:
                return item.data(QtCore.Qt.UserRole) or ""
            return self.controller.last_created or ""

        def _refresh_saved_list(self, preferred_node=None):
            selected_node = preferred_node or (
                self._selected_output() if self.saved_list.count() else self.controller.last_created
            )
            saved = self.controller.refresh_saved_smears()
            self.saved_list.blockSignals(True)
            self.saved_list.clear()
            selected_row = -1
            for row_index, info in enumerate(saved):
                label = "{0}  |  {1:g}-{2:g}  |  {3}".format(
                    info["name"],
                    info["range_start"],
                    info["range_end"],
                    "Unreal" if info["mode"] in (MODE_MORPH, MODE_VAT) else "Maya",
                )
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.UserRole, info["node"])
                self.saved_list.addItem(item)
                if info["node"] == selected_node:
                    selected_row = row_index
            if self.saved_list.count():
                self.saved_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
            self.saved_list.blockSignals(False)
            if self.saved_list.currentItem() is not None:
                self._saved_item_changed(self.saved_list.currentItem(), None)

        def _saved_item_changed(self, current, _previous):
            if current is None:
                return
            output_node = current.data(QtCore.Qt.UserRole) or ""
            if not output_node or not cmds or not cmds.objExists(output_node):
                return
            info = self.controller.smear_info(output_node)
            self.controller.last_created = output_node
            self.name_edit.setText(info["name"])
            self.range_start_spin.setValue(info["range_start"])
            self.range_end_spin.setValue(info["range_end"])

        def _create(self):
            # Read the current Maya selection without rebuilding the saved list.
            # Rebuilding it here can overwrite a newly typed name/range with the
            # previously selected smear before Create reads the fields.
            self.selected_label.setText(self.controller.selected_mesh_label())
            success, message, created_node = self.controller.create_from_selection(
                previous_offset=self.prev_spin.value(),
                next_offset=self.next_spin.value(),
                strength=self.strength_spin.value(),
                key_visibility=self.visibility_check.isChecked(),
                mode=self.mode_combo.currentData() or MODE_STATIC,
                range_start=self.range_start_spin.value(),
                range_end=self.range_end_spin.value(),
                display_name=self.name_edit.text().strip() or None,
            )
            self.status_label.setText(message)
            self.selected_label.setText(self.controller.selected_mesh_label())
            self._refresh_saved_list(preferred_node=created_node if success else None)
            return success

        def _select_last(self):
            output_node = self._selected_output()
            success, message = self.controller.select_smear(output_node)
            self.status_label.setText(message)
            return success

        def _edit_last(self):
            success, message, _target = self.controller.edit_smear_in_viewport(self._selected_output())
            self.status_label.setText(message)
            return success

        def _finish_editing(self):
            success, message = self.controller.finish_editing(self._selected_output())
            self.status_label.setText(message)
            return success

        def _apply_name_and_range(self):
            output_node = self._selected_output()
            success, message = self.controller.rename_smear(output_node, self.name_edit.text())
            if success:
                success, message = self.controller.update_smear_range(
                    output_node,
                    self.range_start_spin.value(),
                    self.range_end_spin.value(),
                    key_visibility=self.visibility_check.isChecked(),
                )
            self.status_label.setText(message)
            self._refresh_saved_list()
            return success

        def _export_unreal(self):
            output_directory = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Export Aminate Smears For Unreal",
                os.path.dirname(cmds.file(query=True, sceneName=True) or os.getcwd()) if cmds else os.getcwd(),
            )
            if not output_directory:
                self.status_label.setText("Unreal smear export cancelled.")
                return False
            success, message, _report = self.controller.export_unreal_bundle(
                output_directory,
                up_axis="Y",
                overwrite=False,
            )
            self.status_label.setText(message)
            return success

        def _delete_selected(self):
            output_node = self._selected_output()
            if not output_node:
                self.status_label.setText("Choose a saved smear first.")
                return False
            info = self.controller.smear_info(output_node)
            answer = QtWidgets.QMessageBox.question(
                self,
                "Delete Generated Smear?",
                "Delete the generated smear '{0}'? The original character mesh is not touched.".format(info["name"]),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return False
            success, message = self.controller.delete_smear(output_node)
            self.status_label.setText(message)
            self._refresh_saved_list()
            return success

        def closeEvent(self, event):
            # Reuse the wrapper on the next shelf click; avoid repeated Qt
            # construction while Maya is processing callbacks.
            self.hide()
            event.accept()
else:
    SmearFrameWindow = None


def show_smear_frames():
    global GLOBAL_WINDOW
    if QtWidgets is None:
        raise RuntimeError("Smear Frames needs PySide.")
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            GLOBAL_WINDOW._refresh_selection()
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
    GLOBAL_WINDOW = SmearFrameWindow(parent=_maya_main_window())
    GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW
