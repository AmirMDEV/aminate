from __future__ import absolute_import, division, print_function

import json
import os
import re

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    om = None
    MAYA_AVAILABLE = False

try:
    from PySide2 import QtWidgets
except Exception:
    try:
        from PySide6 import QtWidgets
    except Exception:
        QtWidgets = None

import maya_skinning_cleanup as skin_cleanup


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
MODE_STATIC = "static_unreal_mesh"
MODE_MORPH = "unreal_morph_target"
MODE_VAT = "unreal_morph_target_sequence"

_capture_shading_assignments = skin_cleanup._capture_shading_assignments
_apply_shading_assignments = skin_cleanup._apply_shading_assignments
_style_donate_button = skin_cleanup._style_donate_button
_open_external_url = skin_cleanup._open_external_url
_maya_main_window = skin_cleanup._maya_main_window


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


def _selected_mesh():
    transform, shape, _indices = _selected_mesh_with_vertices()
    return transform, shape


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


def _copy_visibility_keys(transform, frame):
    for sample_frame, visible in ((frame - 1.0, 0), (frame, 1), (frame + 1.0, 0)):
        cmds.setKeyframe(transform, attribute="visibility", time=sample_frame, value=visible)


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


def _key_morph_weight(blendshape_node, frame):
    weight_attr = _first_blendshape_weight_attr(blendshape_node)
    for sample_frame, value in ((frame - 1.0, 0.0), (frame, 1.0), (frame + 1.0, 0.0)):
        cmds.setKeyframe(weight_attr, time=sample_frame, value=value)
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

    def selected_mesh_label(self):
        transform, _shape, vertex_indices = _selected_mesh_with_vertices()
        if not transform:
            return "No mesh selected"
        if vertex_indices:
            return "{0} ({1} selected vertices)".format(_short_name(transform), len(vertex_indices))
        return _short_name(transform)

    def create_from_selection(self, frame=None, previous_offset=1.0, next_offset=1.0, strength=0.5, key_visibility=True, mode=MODE_STATIC):
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
        shading = _capture_shading_assignments(source_transform, source_shape)
        if mode == MODE_VAT:
            return self._create_vat_morph_sequence_handoff(source_transform, source_shape, frame, previous_frame, next_frame, previous_offset, next_offset, strength, shading, key_visibility, vertex_indices)
        previous_points = _sample_mesh_points(source_shape, previous_frame)
        current_points = _sample_mesh_points(source_shape, frame)
        next_points = _sample_mesh_points(source_shape, next_frame)
        smear_points = _smear_points(previous_points, current_points, next_points, strength)
        smear_points = _smear_selected_vertices(current_points, smear_points, vertex_indices)
        if mode == MODE_MORPH:
            return self._create_morph_target_handoff(source_transform, source_shape, frame, previous_frame, next_frame, strength, smear_points, shading, key_visibility, vertex_indices)
        return self._create_static_mesh_handoff(source_transform, source_shape, frame, previous_frame, next_frame, strength, smear_points, shading, key_visibility, vertex_indices)

    def _create_static_mesh_handoff(self, source_transform, source_shape, frame, previous_frame, next_frame, strength, smear_points, shading, key_visibility, vertex_indices=None):
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
        _ensure_attr(duplicate, GENERATED_ATTR, "bool", 1)
        _ensure_attr(duplicate, SOURCE_ATTR, "string", source_transform)
        _ensure_attr(duplicate, FRAMES_ATTR, "string", "{0:g},{1:g},{2:g}".format(previous_frame, frame, next_frame))
        _ensure_attr(duplicate, MODE_ATTR, "string", MODE_STATIC)
        _ensure_attr(duplicate, STRENGTH_ATTR, "double", float(strength))
        _ensure_attr(duplicate, VERTEX_INDICES_ATTR, "string", _vertex_indices_payload(vertex_indices))
        if key_visibility:
            _copy_visibility_keys(duplicate, frame)
        self.last_created = duplicate
        return True, "Created Unreal-safe static smear mesh: {0}.".format(_short_name(duplicate)), duplicate

    def _create_morph_target_handoff(self, source_transform, source_shape, frame, previous_frame, next_frame, strength, smear_points, shading, key_visibility, vertex_indices=None):
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
            weight_attr = _key_morph_weight(blendshape, frame)
            try:
                cmds.hide(target)
            except Exception:
                pass
            _apply_shading_assignments(base, base_shape, shading)
            _apply_shading_assignments(target, target_shape, shading)
            _ensure_attr(base, GENERATED_ATTR, "bool", 1)
            _ensure_attr(base, SOURCE_ATTR, "string", source_transform)
            _ensure_attr(base, FRAMES_ATTR, "string", "{0:g},{1:g},{2:g}".format(previous_frame, frame, next_frame))
            _ensure_attr(base, MODE_ATTR, "string", MODE_MORPH)
            _ensure_attr(base, STRENGTH_ATTR, "double", float(strength))
            _ensure_attr(base, MORPH_TARGET_ATTR, "string", target)
            _ensure_attr(base, BLENDSHAPE_ATTR, "string", blendshape)
            _ensure_attr(base, VERTEX_INDICES_ATTR, "string", _vertex_indices_payload(vertex_indices))
            _ensure_attr(target, GENERATED_ATTR, "bool", 1)
            _ensure_attr(target, MODE_ATTR, "string", MODE_MORPH)
            _ensure_attr(target, SOURCE_ATTR, "string", source_transform)
            _ensure_attr(target, VERTEX_INDICES_ATTR, "string", _vertex_indices_payload(vertex_indices))
            if key_visibility:
                _copy_visibility_keys(base, frame)
            self.last_created = base
            return True, "Created Unreal morph-target smear: {0} ({1}).".format(_short_name(base), weight_attr), base
        except Exception:
            for node_name in (base, target):
                if node_name and cmds.objExists(node_name):
                    try:
                        cmds.delete(node_name)
                    except Exception:
                        pass
            raise

    def _create_vat_morph_sequence_handoff(self, source_transform, source_shape, frame, previous_frame, next_frame, previous_offset, next_offset, strength, shading, key_visibility, vertex_indices=None):
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
            for target_index, (sample_frame, target) in enumerate(targets):
                weight_attr = _blendshape_weight_attr_for_target(blendshape, target, target_index)
                for key_frame in sample_frames:
                    cmds.setKeyframe(weight_attr, time=key_frame, value=1.0 if abs(key_frame - sample_frame) <= 1.0e-4 else 0.0)
                try:
                    cmds.hide(target)
                except Exception:
                    pass
            _apply_shading_assignments(base, base_shape, shading)
            manifest = {
                "mode": MODE_VAT,
                "source": source_transform,
                "base": base,
                "blendShape": blendshape,
                "frames": [float(value) for value in sample_frames],
                "targets": [{"frame": float(sample_frame), "node": target} for sample_frame, target in targets],
                "strength": float(strength),
                "vertexIndices": json.loads(_vertex_indices_payload(vertex_indices)),
            }
            _ensure_attr(base, GENERATED_ATTR, "bool", 1)
            _ensure_attr(base, SOURCE_ATTR, "string", source_transform)
            _ensure_attr(base, FRAMES_ATTR, "string", ",".join("{0:g}".format(value) for value in sample_frames))
            _ensure_attr(base, MODE_ATTR, "string", MODE_VAT)
            _ensure_attr(base, STRENGTH_ATTR, "double", float(strength))
            _ensure_attr(base, BLENDSHAPE_ATTR, "string", blendshape)
            _ensure_attr(base, VAT_MANIFEST_ATTR, "string", json.dumps(manifest, sort_keys=True))
            _ensure_attr(base, VERTEX_INDICES_ATTR, "string", _vertex_indices_payload(vertex_indices))
            if key_visibility:
                _copy_visibility_keys(base, frame)
            self.last_created = base
            return True, "Created Unreal morph-target sequence: {0} ({1} target frame(s)).".format(_short_name(base), len(targets)), base
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
        if self.last_created and cmds and cmds.objExists(self.last_created):
            cmds.select(self.last_created, replace=True)
            return True, "Selected {0}.".format(_short_name(self.last_created))
        return False, "No smear mesh has been created in this session."

    def edit_last_created_in_viewport(self):
        if not self.last_created or not cmds or not cmds.objExists(self.last_created):
            return False, "No smear output has been created in this session.", ""
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
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            help_label = QtWidgets.QLabel("Create a clean static mesh smear from the selected animated mesh. The output has no rig or deformer history, keeps material assignments, and is keyed visible only on the current frame.")
            help_label.setWordWrap(True)
            layout.addWidget(help_label)
            self.selected_label = QtWidgets.QLabel(self.controller.selected_mesh_label())
            self.selected_label.setObjectName("aminateSmearSelectedLabel")
            layout.addWidget(self.selected_label)
            form = QtWidgets.QFormLayout()
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
            self.visibility_check = QtWidgets.QCheckBox("Only show on current frame")
            self.visibility_check.setObjectName("aminateSmearVisibilityCheck")
            self.visibility_check.setChecked(True)
            self.mode_combo = QtWidgets.QComboBox()
            self.mode_combo.setObjectName("aminateSmearModeCombo")
            self.mode_combo.addItem("Static Mesh", MODE_STATIC)
            self.mode_combo.addItem("Unreal Morph Target", MODE_MORPH)
            self.mode_combo.addItem("Unreal Morph Sequence", MODE_VAT)
            form.addRow("Previous Frame Offset", self.prev_spin)
            form.addRow("Next Frame Offset", self.next_spin)
            form.addRow("Smear Strength", self.strength_spin)
            form.addRow("Output", self.mode_combo)
            form.addRow("", self.visibility_check)
            layout.addLayout(form)
            row = QtWidgets.QHBoxLayout()
            self.refresh_button = QtWidgets.QPushButton("Refresh Selection")
            self.refresh_button.setObjectName("aminateSmearRefreshSelectionButton")
            self.create_button = QtWidgets.QPushButton("Create Smear Frame")
            self.create_button.setObjectName("aminateSmearCreateButton")
            self.select_button = QtWidgets.QPushButton("Select Last Smear")
            self.select_button.setObjectName("aminateSmearSelectLastButton")
            self.edit_button = QtWidgets.QPushButton("Edit Target In Viewport")
            self.edit_button.setObjectName("aminateSmearEditTargetButton")
            row.addWidget(self.refresh_button)
            row.addWidget(self.create_button)
            row.addWidget(self.select_button)
            row.addWidget(self.edit_button)
            layout.addLayout(row)
            self.status_label = QtWidgets.QLabel("")
            self.status_label.setObjectName("aminateSmearStatusLabel")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)
            if self.show_footer:
                footer = QtWidgets.QHBoxLayout()
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

        def _refresh_selection(self):
            self.selected_label.setText(self.controller.selected_mesh_label())

        def _create(self):
            success, message, _node = self.controller.create_from_selection(
                previous_offset=self.prev_spin.value(),
                next_offset=self.next_spin.value(),
                strength=self.strength_spin.value(),
                key_visibility=self.visibility_check.isChecked(),
                mode=self.mode_combo.currentData() or MODE_STATIC,
            )
            self.status_label.setText(message)
            self._refresh_selection()
            return success

        def _select_last(self):
            success, message = self.controller.select_last_created()
            self.status_label.setText(message)
            return success

        def _edit_last(self):
            success, message, _target = self.controller.edit_last_created_in_viewport()
            self.status_label.setText(message)
            return success
else:
    SmearFrameWindow = None


def show_smear_frames():
    if QtWidgets is None:
        raise RuntimeError("Smear Frames needs PySide.")
    window = SmearFrameWindow(parent=_maya_main_window())
    window.show()
    return window
