"""Reversible root-motion authoring for editable Maya transform hierarchies.

Scene-backed sessions keep original channel curves untouched until Bake. World
space caches break descendant-follow cycles; offsetParentMatrix helpers preserve
the body without reparenting joints or changing skinCluster bind data.
"""
from __future__ import absolute_import, division, print_function

import contextlib
import json
import math

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
except ImportError:
    cmds = om = None
try:
    from PySide6 import QtWidgets
except ImportError:
    try:
        from PySide2 import QtWidgets
    except ImportError:
        QtWidgets = None

ATTRS = tuple(group + axis for group in ("translate", "rotate", "scale") for axis in "XYZ")
SHEAR = ("shearXY", "shearXZ", "shearYZ")
SESSION_ATTR = "aminateRootMotionSession"
IDENTITY = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]


def sample_times(start, end, keys=(), every_frame=True):
    """Keep exact fractional keys; dense samples include both range boundaries."""
    start, end = float(start), float(end)
    if not math.isfinite(start) or not math.isfinite(end) or end < start:
        raise ValueError("Choose a finite frame range with End at or after Start.")
    result = {float(t) for t in keys if math.isfinite(float(t)) and start <= float(t) <= end}
    if every_frame:
        result.update((start, end))
        result.update(float(t) for t in range(int(math.ceil(start)), int(math.floor(end)) + 1))
    return sorted(result)


@contextlib.contextmanager
def _transaction(name):
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Enable Maya Undo before creating or baking root motion.")
    time = cmds.currentTime(query=True)
    selection = cmds.ls(selection=True, long=True) or []
    autokey = cmds.autoKeyframe(query=True, state=True)
    cmds.undoInfo(openChunk=True, chunkName=name)
    failed = False
    try:
        cmds.autoKeyframe(state=False)
        yield
    except Exception:
        failed = True
        raise
    finally:
        cmds.currentTime(time, edit=True)
        cmds.autoKeyframe(state=autokey)
        existing = [n for n in selection if cmds.objExists(n)]
        cmds.select(existing, replace=True) if existing else cmds.select(clear=True)
        cmds.undoInfo(closeChunk=True)
        if failed and cmds.undoInfo(query=True, undoName=True) == name:
            cmds.undo()


def _node(value):
    matches = cmds.ls(value, long=True) or []
    if len(matches) != 1 or cmds.nodeType(matches[0]) not in ("joint", "transform"):
        raise ValueError("Pick one unambiguous joint or transform: " + str(value))
    if len(cmds.ls(matches[0], long=True, allPaths=True) or []) != 1:
        raise ValueError("Instanced transforms are not supported: " + matches[0])
    return matches[0]


def _uuid(node):
    return cmds.ls(node, uuid=True)[0]


def _resolve(uuid):
    matches = cmds.ls(uuid, long=True) or []
    if len(matches) != 1:
        raise RuntimeError("A root-motion session object is missing. Undo its deletion before continuing.")
    return matches[0]


def _matrix(plug):
    value = cmds.getAttr(plug)
    if len(value) == 1 and isinstance(value[0], (tuple, list)):
        value = value[0]
    return list(value)


def _world(node):
    return list(cmds.xform(node, query=True, worldSpace=True, matrix=True))


def _invert(matrix):
    m = om.MMatrix(matrix)
    if abs(m.det4x4()) < 1.e-10:
        raise ValueError("Zero or near-zero scale cannot be compensated. Remove it before continuing.")
    return m.inverse()


def _close(a, b, tolerance=1.e-5):
    return all(abs(x - y) <= tolerance * max(1., abs(x), abs(y)) for x, y in zip(a, b))


def local_for_world(world, parent_world, offset_parent):
    """Solve Maya's row-vector hierarchy without assuming identity offsets."""
    return list(om.MMatrix(world) * _invert(parent_world) * _invert(offset_parent))


def _keys(nodes):
    # Include upstream constraint drivers and animated ancestors, not only
    # keys directly on the picked COG or joint.
    upstream = set(nodes)
    for node in nodes:
        upstream.update(cmds.listHistory(node, pruneDagObjects=False) or [])
        parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        while parent:
            upstream.add(parent[0])
            upstream.update(cmds.listHistory(parent[0], pruneDagObjects=False) or [])
            parent = cmds.listRelatives(parent[0], parent=True, fullPath=True) or []
    return sorted(set(cmds.keyframe(list(upstream), query=True, timeChange=True) or []))


def _editable(node):
    if not cmds.attributeQuery("offsetParentMatrix", node=node, exists=True):
        raise ValueError("This tool requires Maya 2020 or newer.")
    if cmds.getAttr(node + ".offsetParentMatrix", lock=True):
        raise ValueError("Unlock offsetParentMatrix before setup: " + node)
    if not cmds.getAttr(node + ".inheritsTransform"):
        raise ValueError("Enable Inherits Transform before setup: " + node)
    for attr in ATTRS + SHEAR:
        plug = node + "." + attr
        if cmds.getAttr(plug, lock=True):
            raise ValueError("Baking needs unlocked transform channels: " + plug)
        inputs = cmds.listConnections(plug, source=True, destination=False) or []
        if any(not cmds.nodeType(n).startswith("animCurveT") for n in inputs):
            raise ValueError("Bake needs directly editable channels. Use an editable controller or export skeleton; driven/layered channel: " + plug)


def _remember(node):
    plug = node + ".offsetParentMatrix"
    source = cmds.connectionInfo(plug, sourceFromDestination=True)
    return {"uuid": _uuid(node), "parent": [_uuid(p) for p in (cmds.listRelatives(node, parent=True, fullPath=True) or [])],
            "matrix": _matrix(plug), "source": ({"uuid": _uuid(source.split(".")[0]), "attr": source.split(".", 1)[1]} if source else None)}


def _restore(record):
    node = _resolve(record["uuid"])
    plug = node + ".offsetParentMatrix"
    current = cmds.connectionInfo(plug, sourceFromDestination=True)
    if current:
        cmds.disconnectAttr(current, plug)
    if record["source"]:
        src = record["source"]
        cmds.connectAttr(_resolve(src["uuid"]) + "." + src["attr"], plug)
    else:
        cmds.setAttr(plug, *record["matrix"], type="matrix")


def _cache(name, samples, owned):
    node = cmds.createNode("transform", name=name)
    owned.append(node)
    for time, matrix in samples:
        cmds.currentTime(time, edit=True)
        cmds.xform(node, objectSpace=True, matrix=matrix)
        cmds.setKeyframe(node, attribute=ATTRS + SHEAR, time=time)
    cmds.keyTangent(node, edit=True, inTangentType="linear", outTangentType="linear")
    cmds.filterCurve(node + ".rotateX", node + ".rotateY", node + ".rotateZ")
    cmds.setAttr(node + ".visibility", False)
    return node


def _drive_world(node, driver, owned):
    # Maya uses row-vector order: world = local * offsetParent * parentWorld.
    multiply = cmds.createNode("multMatrix", name="aminateRootWorldCompensation#")
    owned.append(multiply)
    # Every editable transform already exposes its local inverse. The separate
    # inverseMatrix node belongs to an optional plug-in and may be unavailable.
    cmds.connectAttr(node + ".inverseMatrix", multiply + ".matrixIn[0]")
    cmds.connectAttr(driver + ".worldMatrix[0]", multiply + ".matrixIn[1]")
    parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
    if parent:
        # parentInverseMatrix includes offsetParentMatrix in Maya; using the
        # actual parent's world inverse avoids a dependency cycle here.
        cmds.connectAttr(parent[0] + ".worldInverseMatrix[0]", multiply + ".matrixIn[2]")
    cmds.connectAttr(multiply + ".matrixSum", node + ".offsetParentMatrix", force=True)
    return multiply


class RootMotionController(object):
    def _owned_nodes(self, data):
        result = []
        for uuid in data["owned"]:
            result.extend(cmds.ls(uuid, long=True) or [])
        return result

    def sessions(self):
        return [n for n in (cmds.ls(type="network") or []) if cmds.attributeQuery(SESSION_ATTR, node=n, exists=True)]

    def _data(self, session):
        if session not in self.sessions():
            raise ValueError("Choose an existing root-motion session.")
        return json.loads(cmds.getAttr(session + "." + SESSION_ATTR))

    def prepare(self, root, start, end, source=None, translation=True, rotation=False,
                scale=False, maintain_offset=True):
        root = _node(root)
        source = _node(source) if source else None
        children = cmds.listRelatives(root, children=True, fullPath=True) or []
        children = [_node(n) for n in children if cmds.nodeType(n) in ("joint", "transform")]
        if not children:
            raise ValueError("The root needs a child hierarchy to preserve.")
        if source and not any((translation, rotation, scale)):
            raise ValueError("Choose Translation, Rotation, or Scale to follow.")
        targets = [root] + children
        for session in self.sessions():
            data = self._data(session)
            other = [_resolve(r["uuid"]) for r in data["targets"]]
            if any(a == b or a.startswith(b + "|") or b.startswith(a + "|") for a in targets for b in other):
                raise ValueError("Finish or cancel the overlapping root-motion session first.")
        for node in targets:
            _editable(node)
        key_times = _keys(targets + ([source] if source else []))
        times = sample_times(start, end, key_times)
        reference = float(cmds.currentTime(query=True))
        if not float(start) <= reference <= float(end):
            raise ValueError("Move to the offset reference frame inside the selected range before setup.")
        times = sorted(set(times + [reference]))
        with _transaction("Aminate Prepare Root Motion"):
            captured = {node: [] for node in set(targets + ([source] if source else []))}
            for time in times:
                cmds.currentTime(time, edit=True)
                for node in captured:
                    matrix = _world(node)
                    _invert(matrix)
                    captured[node].append((time, matrix))
            records = [_remember(n) for n in targets]
            owned = []
            body_drivers = [_cache("aminateBodyTrajectory#", captured[n], owned) for n in children]
            follow = _cache("aminateFollowTrajectory#", captured[source], owned) if source else None
            cmds.currentTime(reference, edit=True)
            root_matrix = dict(captured[root])[reference]
            edit = cmds.spaceLocator(name="aminateRoot_EDIT#")[0]
            owned.append(edit)
            cmds.xform(edit, worldSpace=True, matrix=root_matrix)
            # Seed only the original authored root/ancestor times, not dense
            # cache samples. New animator keys remain sparse and meaningful.
            seed_times = sample_times(start, end, _keys([root]), every_frame=False)
            seed_times = sorted(set(seed_times + [reference]))
            followed = set()
            if source:
                for enabled, group in ((translation, "translate"), (rotation, "rotate"), (scale, "scale")):
                    if enabled:
                        followed.update(group + axis for axis in "XYZ")
            seed_attrs = tuple(a for a in ATTRS + SHEAR if a not in followed)
            for time in seed_times:
                cmds.currentTime(time, edit=True)
                cmds.xform(edit, worldSpace=True, matrix=dict(captured[root])[time])
                cmds.setKeyframe(edit, attribute=seed_attrs, time=time)
            cmds.currentTime(reference, edit=True)
            # The reference is always captured; restore the exact offset pose.
            cmds.xform(edit, worldSpace=True, matrix=root_matrix)
            if follow:
                for enabled, command in ((translation, cmds.pointConstraint), (rotation, cmds.orientConstraint), (scale, cmds.scaleConstraint)):
                    if enabled:
                        owned.extend(command(follow, edit, maintainOffset=maintain_offset))
            for record, node, driver in zip(records, targets, [edit] + body_drivers):
                record["compensator"] = _uuid(_drive_world(node, driver, owned))
            curves = set()
            for helper in owned:
                curves.update(cmds.listConnections(helper, source=True, destination=False, type="animCurve") or [])
            owned.extend(sorted(curves))
            session = cmds.createNode("network", name="aminateRootMotion#")
            data = {"version": 1, "targets": records, "owned": [_uuid(n) for n in owned],
                    "edit": _uuid(edit), "start": float(start), "end": float(end),
                    "keys": key_times, "reference": reference, "source": _uuid(source) if source else None}
            cmds.addAttr(session, longName=SESSION_ATTR, dataType="string")
            cmds.setAttr(session + "." + SESSION_ATTR, json.dumps(data), type="string")
            # Check the body at setup before handing over the control.
            for node in children:
                if not _close(_world(node), dict(captured[node])[reference]):
                    raise RuntimeError("Body compensation did not preserve " + node + ". Setup was rolled back.")
        cmds.select(edit, replace=True)
        return session

    def select_control(self, session):
        edit = _resolve(self._data(session)["edit"])
        cmds.select(edit, replace=True)
        return edit

    def _validate_session(self, data):
        owned = set(data["owned"])
        for uuid in owned:
            matches = cmds.ls(uuid, long=True) or []
            if not matches:
                continue  # Deleting an animator's helper key curve is valid.
            helper = matches[0]
            if cmds.nodeType(helper) not in ("transform", "joint"):
                continue
            for child in cmds.listRelatives(helper, children=True, fullPath=True) or []:
                if cmds.nodeType(child) in ("transform", "joint") and _uuid(child) not in owned:
                    raise RuntimeError("Move user-created children out of the temporary helpers before finishing.")
        for record in data["targets"]:
            node = _resolve(record["uuid"])
            parents = [_uuid(p) for p in (cmds.listRelatives(node, parent=True, fullPath=True) or [])]
            if parents != record["parent"]:
                raise RuntimeError("The hierarchy changed during preview. Restore its original parenting before finishing.")
            expected = _resolve(record["compensator"]) + ".matrixSum"
            actual = cmds.connectionInfo(node + ".offsetParentMatrix", sourceFromDestination=True)
            if not actual or _uuid(actual.split(".")[0]) != _uuid(expected.split(".")[0]):
                raise RuntimeError("A compensation connection changed. Restore it before finishing to avoid overwriting edits.")

    def cancel(self, session):
        data = self._data(session)
        self._validate_session(data)
        with _transaction("Aminate Cancel Root Motion"):
            for record in data["targets"]:
                _restore(record)
            cmds.delete(self._owned_nodes(data) + [session])

    def bake(self, session, every_frame=False):
        data = self._data(session)
        self._validate_session(data)
        nodes = [_resolve(r["uuid"]) for r in data["targets"]]
        for node in nodes:
            _editable(node)
        keys = set(data["keys"]) | set(cmds.keyframe(_resolve(data["edit"]), query=True, timeChange=True) or [])
        times = sample_times(data["start"], data["end"], keys, every_frame)
        if not times:
            raise ValueError("Set at least one key in the range, or choose Every frame.")
        with _transaction("Aminate Bake Root Motion"):
            poses = []
            for time in times:
                cmds.currentTime(time, edit=True)
                poses.append([_world(node) for node in nodes])
            for record in data["targets"]:
                _restore(record)
            # Remove interior keys only on channels being replaced. Outside
            # keyed values survive; the range-edge interpolation can change.
            for node in nodes:
                cmds.cutKey(node, attribute=ATTRS + SHEAR, time=(data["start"], data["end"]), clear=True)
            for time, worlds in zip(times, poses):
                cmds.currentTime(time, edit=True)
                for node, world in zip(nodes, worlds):
                    parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
                    local = local_for_world(world, _world(parent[0]) if parent else IDENTITY,
                                            _matrix(node + ".offsetParentMatrix"))
                    cmds.xform(node, objectSpace=True, matrix=local)
                    cmds.setKeyframe(node, attribute=ATTRS + SHEAR, time=time)
                    if not _close(_world(node), world):
                        raise RuntimeError("This joint/controller cannot represent the compensated transform: " + node + ". Bake was rolled back.")
            for node in nodes:
                cmds.keyTangent(node, attribute=ATTRS + SHEAR, time=(data["start"], data["end"]), edit=True,
                                inTangentType="linear", outTangentType="linear")
            for time, worlds in zip(times, poses):
                cmds.currentTime(time, edit=True)
                if any(not _close(_world(n), w) for n, w in zip(nodes, worlds)):
                    raise RuntimeError("Baked motion failed world-space verification. Bake was rolled back.")
            cmds.delete(self._owned_nodes(data) + [session])
        return {"frames": len(times), "times": times, "targets": nodes}


if QtWidgets is not None:
    class RootMotionPanel(QtWidgets.QWidget):
        def __init__(self, parent=None):
            super(RootMotionPanel, self).__init__(parent)
            self.controller = RootMotionController()
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.root = self._picker(layout, "Root bone / control")
            self.source = self._picker(layout, "Follow source (optional)")
            self.source.setPlaceholderText("Leave empty for freeform root keys")
            range_row = QtWidgets.QHBoxLayout()
            self.start, self.end = QtWidgets.QDoubleSpinBox(), QtWidgets.QDoubleSpinBox()
            for label, spin, flag in (("Start", self.start, "minTime"), ("End", self.end, "maxTime")):
                spin.setRange(-1000000, 1000000)
                spin.setDecimals(3)
                spin.setValue(cmds.playbackOptions(query=True, **{flag: True}))
                range_row.addWidget(QtWidgets.QLabel(label))
                range_row.addWidget(spin)
            layout.addLayout(range_row)
            row = QtWidgets.QHBoxLayout()
            self.translation = QtWidgets.QCheckBox("Translation")
            self.rotation = QtWidgets.QCheckBox("Rotation")
            self.scale = QtWidgets.QCheckBox("Scale")
            self.translation.setChecked(True)
            for checkbox in (self.translation, self.rotation, self.scale):
                row.addWidget(checkbox)
            layout.addLayout(row)
            self.offset = QtWidgets.QCheckBox("Maintain offset at current frame")
            self.offset.setChecked(True)
            layout.addWidget(self.offset)
            self._button(layout, "Prepare independent root", self._prepare)
            self.session = QtWidgets.QComboBox()
            self.session.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.session.setMinimumContentsLength(10)
            layout.addWidget(self.session)
            self._button(layout, "Refresh sessions", self.refresh)
            self._button(layout, "Select root animation control", lambda: self.controller.select_control(self._selected()))
            self.bake_mode = QtWidgets.QComboBox()
            self.bake_mode.addItems(["Authored keyframes only", "Every frame"])
            layout.addWidget(self.bake_mode)
            note = QtWidgets.QLabel("All direct child branches are preserved. Preview caches the existing motion; edit the temporary root control. Keyframes-only baking can change motion between keys.")
            note.setWordWrap(True)
            layout.addWidget(note)
            self._button(layout, "Bake and finish", self._bake)
            self._button(layout, "Cancel and restore original", self._cancel)
            self.status = QtWidgets.QLabel("")
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            layout.addStretch(1)
            self.refresh()

        def _picker(self, layout, title):
            layout.addWidget(QtWidgets.QLabel(title))
            row = QtWidgets.QHBoxLayout()
            field = QtWidgets.QLineEdit()
            field.setMinimumWidth(0)
            row.addWidget(field, 1)
            button = QtWidgets.QPushButton("Pick")
            button.clicked.connect(lambda: self._run(lambda: field.setText(_node((cmds.ls(selection=True, long=True) or [""])[0]))))
            row.addWidget(button)
            layout.addLayout(row)
            return field

        def _button(self, layout, title, action):
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(lambda: self._run(action))
            layout.addWidget(button)

        def _run(self, action):
            try:
                action()
            except Exception as error:
                self.status.setText(str(error))
                cmds.warning(str(error))

        def refresh(self):
            current = self.session.currentText()
            self.session.clear()
            self.session.addItems(self.controller.sessions())
            index = self.session.findText(current)
            if index >= 0:
                self.session.setCurrentIndex(index)

        def _selected(self):
            return self.session.currentText()

        def _prepare(self):
            session = self.controller.prepare(self.root.text().strip(), self.start.value(), self.end.value(),
                source=self.source.text().strip() or None, translation=self.translation.isChecked(),
                rotation=self.rotation.isChecked(), scale=self.scale.isChecked(), maintain_offset=self.offset.isChecked())
            self.refresh()
            self.session.setCurrentText(session)
            self.status.setText("Preview ready. Animate the selected root helper, then Bake and finish.")

        def _bake(self):
            result = self.controller.bake(self._selected(), every_frame=self.bake_mode.currentIndex() == 1)
            self.refresh()
            self.status.setText("Baked and verified {0} sample times. Temporary helpers removed.".format(result["frames"]))

        def _cancel(self):
            self.controller.cancel(self._selected())
            self.refresh()
            self.status.setText("Original hierarchy transforms and animation restored.")
