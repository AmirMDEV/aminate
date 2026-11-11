"""Scene-native, keyed attachment changes for Maya transform controls."""

import json
import math
from colorsys import hls_to_rgb
from contextlib import contextmanager

from maya import cmds
from maya.api import OpenMaya as om


CHANNELS = ("translate", "rotate", "scale")
AXES = "XYZ"
TOLERANCE = 1.0e-5
FOLLOW_KEY_COLOR = (0.27, 0.62, 1.0)
FOLLOW_COLORS = (
    ("#7DBAFF", "#225C9E"), ("#FFBA72", "#94440D"), ("#71D6BB", "#166653"),
    ("#D3A7F5", "#743B92"), ("#F29DB8", "#982F57"), ("#D7CD7A", "#716415"),
)
SETUP_TAG = "aminateParentManagerEvents"
POINT_TAG = "aminateAttachmentPoint"
POINT_LABEL_TAG = "aminatePointNameLabel"
FOLLOW_TARGETS_TAG = "aminateFollowTargets"
FREE_COLOR = "#A5ABB5"
FIXED_TRANSFORM_ATTRS = (
    "rotateOrder", "rotateAxis", "rotatePivot", "rotatePivotTranslate",
    "scalePivot", "scalePivotTranslate", "shear",
)


def _transform(name):
    matches = cmds.ls(name, long=True, type="transform") if name else []
    if len(matches) != 1 or cmds.nodeType(matches[0]) != "transform":
        raise ValueError("Choose one unambiguous Maya transform control.")
    node = matches[0]
    if len(cmds.ls(node, long=True, allPaths=True) or []) != 1:
        raise ValueError("Choose a non-instanced transform control.")
    return node


def _uuid(node):
    return (cmds.ls(node, uuid=True) or [""])[0] if node else ""


def _resolve(identifier):
    return (cmds.ls(identifier, long=True) or [None])[0] if identifier else None


def _matrix(plug):
    return om.MMatrix(cmds.getAttr(plug))


def _world(node):
    return _matrix(node + ".worldMatrix[0]") if node else om.MMatrix()


def _set_matrix(plug, value):
    cmds.setAttr(plug, *tuple(value), type="matrix")


def _near(left, right):
    return all(abs(a - b) <= TOLERANCE for a, b in zip(left, right))


def _inverse(value):
    if value.isSingular():
        raise ValueError("A transform has zero scale. Aminate cannot preserve this pose.")
    return value.inverse()


def _text_attr(node, name, value):
    if not cmds.attributeQuery(name, node=node, exists=True):
        cmds.addAttr(node, longName=name, dataType="string")
    cmds.setAttr(node + "." + name, value, type="string")


@contextmanager
def _edit(label, end_time=None):
    if not cmds.undoInfo(query=True, state=True):
        raise ValueError("Enable Maya Undo before changing an attachment.")
    time = cmds.currentTime(query=True)
    chunk = "Aminate Parent Manager: " + label
    cmds.undoInfo(openChunk=True, chunkName=chunk)
    try:
        try:
            yield
            if end_time is not None:
                time = end_time
        finally:
            if cmds.currentTime(query=True) != time:
                cmds.currentTime(time, edit=True)
            cmds.undoInfo(closeChunk=True)
    except Exception:
        if cmds.undoInfo(query=True, undoName=True) == chunk:
            cmds.undo()
        raise


def _point_color(shape, color):
    if len(color) != 3 or any(not 0.0 <= value <= 1.0 for value in color):
        raise ValueError("Choose an RGB colour.")
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideRGBColors", True)
    cmds.setAttr(shape + ".overrideColorRGB", *color, type="double3")


def _point_shape(point):
    point = _transform(point)
    if not cmds.attributeQuery(POINT_TAG, node=point, exists=True):
        raise ValueError("Select an Aminate attachment point.")
    shapes = cmds.listRelatives(point, shapes=True, fullPath=True, type="locator") or []
    if len(shapes) != 1:
        raise ValueError("This attachment point is missing its viewport marker.")
    return point, shapes[0]


def _point_label(point):
    labels = cmds.listRelatives(point, shapes=True, fullPath=True, type="annotationShape") or []
    return next((label for label in labels if cmds.attributeQuery(POINT_LABEL_TAG, node=label, exists=True)), None)


def _create_point_label(point, name, color):
    label = cmds.createNode("annotationShape", name="aminatePointName#", parent=point, skipSelect=True)
    cmds.addAttr(label, longName=POINT_LABEL_TAG, attributeType="bool", defaultValue=True, hidden=True)
    cmds.setAttr(label + ".displayArrow", False)
    cmds.setAttr(label + ".text", name, type="string")
    _point_color(label, color)


def set_point_labels(target, visible):
    """Show or hide the saved names belonging to one follow target."""
    points = list_points(target)
    if not points:
        return
    with _edit("Show point names" if visible else "Hide point names"):
        for point in points:
            label = _point_label(point["node"])
            if label:
                cmds.setAttr(label + ".visibility", visible)
            elif visible:
                _create_point_label(point["node"], point["name"], point["color"])


def create_point(target, source, name, color):
    """Create a movable, reusable marker in the target's local space."""
    target, source = _transform(target), _transform(source)
    name = name.strip()
    if not name:
        raise ValueError("Enter a name for the attachment point.")
    show_label = any(point["label_visible"] for point in list_points(target))
    relative_pose = _world(source) * _inverse(_world(target))
    with _edit("Add point"):
        point = cmds.createNode("transform", name="aminateAttachmentPoint#", parent=target, skipSelect=True)
        shape = cmds.createNode("locator", name="aminateAttachmentPointShape#", parent=point, skipSelect=True)
        cmds.xform(point, objectSpace=True, matrix=tuple(relative_pose))
        _text_attr(point, POINT_TAG, name)
        _point_color(shape, color)
        if show_label:
            _create_point_label(point, name, color)
    return _transform(point)


def update_point(point, name, color):
    point, shape = _point_shape(point)
    name = name.strip()
    if not name:
        raise ValueError("Enter a name for the attachment point.")
    with _edit("Edit point"):
        _text_attr(point, POINT_TAG, name)
        _point_color(shape, color)
        label = _point_label(point)
        if label:
            cmds.setAttr(label + ".text", name, type="string")
            _point_color(label, color)


def list_points(target):
    if not target:
        return []
    target = _transform(target)
    results = []
    for child in cmds.listRelatives(target, children=True, fullPath=True, type="transform") or []:
        if cmds.attributeQuery(POINT_TAG, node=child, exists=True):
            point, shape = _point_shape(child)
            label = _point_label(point)
            results.append({
                "node": point,
                "name": cmds.getAttr(point + "." + POINT_TAG),
                "color": cmds.getAttr(shape + ".overrideColorRGB")[0],
                "label_visible": bool(label and cmds.getAttr(label + ".visibility")),
            })
    return results


def _setup(driven):
    for node in cmds.listConnections(driven + ".message", source=False, destination=True, type="network") or []:
        if cmds.attributeQuery(SETUP_TAG, node=node, exists=True):
            return node
    return None


def _linked(setup, attr):
    plug = setup + "." + attr
    return cmds.connectionInfo(plug, sourceFromDestination=True).split(".", 1)[0]


def _parent(driven):
    if cmds.connectionInfo(driven + ".inheritsTransform", isDestination=True):
        raise ValueError("Animated Inherits Transform is unsupported for this control.")
    parents = cmds.listRelatives(driven, parent=True, fullPath=True) or []
    return parents[0] if parents and cmds.getAttr(driven + ".inheritsTransform") else None


def _new_node(node_type, role):
    return cmds.createNode(node_type, name="aminateParent" + role + "#", skipSelect=True)


def _link(setup, name, node):
    cmds.addAttr(setup, longName=name, attributeType="message")
    cmds.connectAttr(node + ".message", setup + "." + name)


def _create_setup(driven):
    destination = driven + ".offsetParentMatrix"
    if cmds.getAttr(destination, lock=True):
        raise ValueError("This rig locks the control's Offset Parent Matrix.")
    source = cmds.connectionInfo(destination, sourceFromDestination=True)
    original = _matrix(destination)
    parent = _parent(driven)
    setup = _new_node("network", "Setup")
    baseline = _new_node("multMatrix", "OriginalWorld")
    choice = _new_node("choice", "State")
    result = _new_node("multMatrix", "Output")
    _text_attr(setup, SETUP_TAG, "[]")
    _link(setup, "aminateDriven", driven)
    _link(setup, "aminateBaseline", baseline)
    _link(setup, "aminateChoice", choice)
    _link(setup, "aminateOutput", result)
    if parent:
        _link(setup, "aminateHierarchyParent", parent)
        cmds.connectAttr(parent + ".worldMatrix[0]", baseline + ".matrixIn[2]")
        cmds.connectAttr(parent + ".worldInverseMatrix[0]", result + ".matrixIn[2]")
    cmds.connectAttr(driven + ".matrix", baseline + ".matrixIn[0]")
    if source:
        cmds.disconnectAttr(source, destination)
        cmds.connectAttr(source, baseline + ".matrixIn[1]")
    else:
        _set_matrix(baseline + ".matrixIn[1]", original)
    cmds.connectAttr(baseline + ".matrixSum", choice + ".input[0]")
    cmds.connectAttr(driven + ".inverseMatrix", result + ".matrixIn[0]")
    cmds.connectAttr(choice + ".output", result + ".matrixIn[1]")
    cmds.connectAttr(result + ".matrixSum", destination)
    return setup


def _read_events(setup):
    return json.loads(cmds.getAttr(setup + "." + SETUP_TAG)) if setup else []


def _active(events, time):
    return next((event for event in reversed(events) if event["start"] <= time), None)


def _describe(event):
    return {
        "frame": event["frame"],
        "start": event["start"],
        "action": event["action"],
        "target_id": event["target"],
        "target": _resolve(event["target"]),
        "point": _resolve(event["point"]),
        "name": event["name"],
        "channels": tuple(event["channels"]),
    }


def state(driven):
    if not driven or not cmds.objExists(driven):
        return None
    setup = _setup(_transform(driven))
    event = _active(_read_events(setup), cmds.currentTime(query=True))
    if not event or not event["index"]:
        return None
    active = _describe(event)
    point = active["point"]
    if point and cmds.attributeQuery(POINT_TAG, node=point, exists=True):
        active["name"] = cmds.getAttr(point + "." + POINT_TAG)
    return active


def history(driven):
    if not driven or not cmds.objExists(driven):
        return []
    driven = _transform(driven)
    setup = _setup(driven)
    events = _read_events(setup)
    colors = _follow_colors(setup, events)
    rows = []
    previous = None
    for event in events:
        row = _describe(event)
        row["color_index"] = colors.get(event["target"]) if event["index"] else None
        row["protected_release"] = _protected_release(driven, event, previous)
        rows.append(row)
        previous = event
    return rows


def _follow_colors(setup, events):
    plug = setup + "." + FOLLOW_TARGETS_TAG if setup else ""
    targets = json.loads(cmds.getAttr(plug)) if plug and cmds.objExists(plug) else []
    targets = dict.fromkeys(targets + [event["target"] for event in events if event["index"]])
    return {target: index for index, target in enumerate(targets)}


def follow_color(index, light_background=False):
    if index is None:
        return "#505965" if light_background else FREE_COLOR
    if index < len(FOLLOW_COLORS):
        return FOLLOW_COLORS[index][light_background]
    hue = ((index - len(FOLLOW_COLORS) + 0.4) * 0.61803398875) % 1.0
    rgb = hls_to_rgb(hue, 0.30 if light_background else 0.70, 0.75)
    return "#" + "".join(f"{round(value * 255):02X}" for value in rgb)


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def _bookmark_node(identifier):
    node = _resolve(identifier)
    return node if node and cmds.nodeType(node) == "timeSliderBookmark" else None


def _bookmark_specs(driven, events, colors):
    previous_name = None
    name = driven.rsplit("|", 1)[-1]
    for index, event in enumerate(events):
        specs = []
        if index == 0:
            specs.append((event["start"] - 1, f"{name} is free before its first follow", FREE_COLOR))
        target = _resolve(event["target"])
        if target:
            target_name = target.rsplit("|", 1)[-1]
        else:
            target_name = "Missing parent" if event["target"] else "World"
        if event["index"]:
            color = follow_color(colors[event["target"]])
            point = _resolve(event["point"])
            spot = cmds.getAttr(point + "." + POINT_TAG) if point else ""
            destination = f"{target_name} at {spot}" if spot else target_name
            message = f"{name} starts following {destination}"
            if event["start"] < event["frame"]:
                location = f"{spot} on {target_name}" if spot else target_name
                movement = f"starts moving to {location}"
                if previous_name:
                    movement = f"stops following {previous_name} and {movement}"
                specs.append((event["start"], f"{name} {movement}", color))
                message = f"{name} reaches {location} and follows {target_name}"
            elif previous_name == target_name:
                message = f"{name} continues following {destination}"
            elif previous_name:
                message = f"{name} stops following {previous_name} and starts following {destination}"
            specs.append((event["frame"], message, color))
            previous_name = target_name
        else:
            release = f"stops following {previous_name}" if previous_name else "is free"
            specs.append((event["frame"], f"{name} {release} and keeps its pose", FREE_COLOR))
            previous_name = None
        yield [(frame, f"Frame {frame:.12g} · {label}", color) for frame, label, color in specs]


def follow_timeline_marks():
    """Read follow changes in the scene without requiring selected objects or bookmark nodes."""
    marks = []
    setups = cmds.ls("*." + SETUP_TAG, recursive=True, objectsOnly=True, type="network") or []
    for setup in setups:
        driven = _linked(setup, "aminateDriven")
        if driven:
            events = _read_events(setup)
            for specs in _bookmark_specs(driven, events, _follow_colors(setup, events)):
                marks.extend(specs)
    return sorted(marks)


def _sync_bookmarks(driven, events, colors):
    if not cmds.pluginInfo("timeSliderBookmark", query=True, loaded=True):
        cmds.loadPlugin("timeSliderBookmark", quiet=True)
    cmds.pluginInfo("timeSliderBookmark", edit=True, writeRequires=True)
    from maya.plugin.timeSliderBookmark.timeSliderBookmark import getNextPriority

    for event, specs in zip(events, _bookmark_specs(driven, events, colors)):
        saved = event.get("bookmarks", [])
        bookmarks = []
        for index, (frame, label, color) in enumerate(specs):
            node = _bookmark_node(saved[index]) if index < len(saved) else None
            if not node:
                priority = getNextPriority()
                node = _new_node("timeSliderBookmark", "Bookmark")
                cmds.setAttr(node + ".priority", priority)
            cmds.setAttr(node + ".name", label, type="string")
            cmds.setAttr(node + ".color", *_rgb(color))
            cmds.setAttr(node + ".timeRangeStart", frame)
            cmds.setAttr(node + ".timeRangeStop", frame + 1)
            bookmarks.append(_uuid(node))
        event["bookmarks"] = bookmarks


def missing_bookmarks(driven):
    setup = _setup(_transform(driven))
    events = _read_events(setup)
    for event, specs in zip(events, _bookmark_specs(driven, events, _follow_colors(setup, events))):
        identifiers = event.get("bookmarks", [])
        if len(identifiers) != len(specs):
            return True
        for identifier, (frame, label, color) in zip(identifiers, specs):
            node = _bookmark_node(identifier)
            if (not node or cmds.getAttr(node + ".name") != label
                    or cmds.getAttr(node + ".timeRangeStart") != frame
                    or cmds.getAttr(node + ".timeRangeStop") != frame + 1
                    or not _near(cmds.getAttr(node + ".color")[0], _rgb(color))):
                return True
    return False


def add_bookmarks(driven):
    """Add or restore the native bookmarks for an existing follow setup."""
    driven = _transform(driven)
    setup = _setup(driven)
    events = _read_events(setup)
    if events:
        with _edit("Add timeline bookmarks"):
            _save_events(driven, setup, events)


def _save_events(driven, setup, events):
    colors = _follow_colors(setup, events)
    _text_attr(setup, FOLLOW_TARGETS_TAG, json.dumps(list(colors)))
    if events:
        _sync_bookmarks(driven, events, colors)
    _label_selector(_linked(setup, "aminateChoice"))
    _sync_follow_display(setup, events, colors)
    _text_attr(setup, SETUP_TAG, json.dumps(events))


def _follow_display_specs(setup, events, colors):
    if not events:
        return {}
    specs = {setup + ".followFree": ([events[0]["start"] - 1], "Free", FREE_COLOR)}
    for event in events:
        if not event["index"]:
            specs[setup + ".followFree"][0].append(event["frame"])
            continue
        index = colors[event["target"]]
        attr = "objectToFollow" if index == 0 else f"followParent{index}"
        name = _resolve(event["target"])
        label = "Object to Follow" if index == 0 else (name.rsplit("|", 1)[-1] if name else event["name"])
        frames, _, _ = specs.setdefault(setup + "." + attr, ([], label, follow_color(index)))
        frames.append(event["start"])
        if event["start"] < event["frame"]:
            frames.append(event["frame"])
    return specs


def _sync_follow_display(setup, events, colors):
    # The display channels are separate from the rig's driving curves. Selecting
    # the setup shows one curve per colour without overlapping the selector ticks.
    specs = _follow_display_specs(setup, events, colors)
    for attr in cmds.listAttr(setup, userDefined=True, keyable=True) or []:
        plug = setup + "." + attr
        if plug not in specs and (attr in ("objectToFollow", "followFree") or attr.startswith("followParent")):
            cmds.deleteAttr(plug)
    for plug, (frames, label, color) in specs.items():
        if not cmds.objExists(plug):
            cmds.addAttr(setup, longName=plug.split(".", 1)[1], niceName=label, attributeType="bool", keyable=True)
        curve = _direct_curve(plug)
        times = cmds.keyframe(curve, query=True, timeChange=True) if curve else []
        for time in sorted(set(times or []) - set(frames)):
            cmds.cutKey(plug, time=(time, time), clear=True)
        for frame in sorted(set(frames) - set(times or [])):
            if cmds.setKeyframe(plug, time=frame, value=1, outTangentType="step") != 1:
                raise RuntimeError("Maya could not draw the coloured follow key.")
        _style_follow_curve(plug, _rgb(color))


def _label_selector(choice):
    label = choice + ".objectToFollow"
    if not cmds.objExists(label):
        cmds.addAttr(choice, longName="objectToFollow", niceName="Object to Follow", attributeType="long")
        cmds.connectAttr(choice + ".selector", label)
        cmds.setAttr(label, channelBox=True)
        cmds.setAttr(choice + ".selector", keyable=False, channelBox=False)


def prepare_follow_display(driven):
    """Repair missing or stale display keys without changing the rig animation."""
    driven = _transform(driven)
    setup = _setup(driven)
    events = _read_events(setup)
    colors = _follow_colors(setup, events)
    specs = _follow_display_specs(setup, events, colors)
    stale = False
    for plug, (frames, _, color) in specs.items():
        curve = _direct_curve(plug) if cmds.objExists(plug) else None
        if (not curve or cmds.keyframe(curve, query=True, timeChange=True) != frames
                or not cmds.getAttr(curve + ".useCurveColor")
                or not _near(cmds.getAttr(curve + ".curveColor")[0], _rgb(color))):
            stale = True
            break
    if events and (stale or not cmds.objExists(_linked(setup, "aminateChoice") + ".objectToFollow")
                   or missing_bookmarks(driven)):
        with _edit("Update coloured follow keys"):
            _save_events(driven, setup, events)
    return list(specs)


def follow_key_plug(driven):
    """Return the native Maya channel that keys this object's follow link."""
    if not driven or not cmds.objExists(driven):
        return None
    setup = _setup(_transform(driven))
    if not setup:
        return None
    choice = _linked(setup, "aminateChoice")
    plug = choice + ".selector"
    return plug if choice and cmds.objExists(plug) else None


def follow_key_plugs(driven):
    """Include both the switch curve and the saved-spot transition curves."""
    selector = follow_key_plug(driven)
    if not selector:
        return []
    choice = selector.rsplit(".", 1)[0]
    plugs = [selector]
    for event in _read_events(_setup(_transform(driven))):
        if event["start"] < event["frame"]:
            transition = cmds.connectionInfo(
                f"{choice}.input[{event['index']}]", sourceFromDestination=True
            ).split(".", 1)[0]
            if transition:
                plugs.append(transition + ".target[0].weight")
    return plugs


def _check_cycle(driven, target):
    if not target:
        return
    if target == driven or target.startswith(driven + "|"):
        raise ValueError("This parent already depends on the object you want to attach.")
    nodes = om.MSelectionList()
    nodes.add(driven)
    nodes.add(target + ".worldMatrix[0]")
    source = nodes.getDependNode(0)
    graph = om.MItDependencyGraph(
        nodes.getPlug(1), om.MFn.kInvalid, om.MItDependencyGraph.kUpstream,
        om.MItDependencyGraph.kDepthFirst, om.MItDependencyGraph.kPlugLevel,
    )
    while not graph.isDone():
        if graph.currentNode() == source:
            raise ValueError("This parent already depends on the object you want to attach.")
        graph.next()


def _check_setup(setup, driven):
    if not setup:
        return
    hierarchy_plug = setup + ".aminateHierarchyParent"
    hierarchy = (cmds.listConnections(hierarchy_plug, source=True, destination=False) or []) if cmds.objExists(hierarchy_plug) else []
    parent = _parent(driven)
    original_parent = (cmds.ls(hierarchy[0], long=True) or [None])[0] if hierarchy else None
    if parent != original_parent:
        raise ValueError("The Maya hierarchy changed after setup. Restore the original hierarchy before switching.")
    output = _linked(setup, "aminateOutput")
    if cmds.connectionInfo(driven + ".offsetParentMatrix", sourceFromDestination=True) != output + ".matrixSum":
        raise ValueError("The rig's attachment connection changed. Restore the original Aminate connection first.")


def _frame_for_edit(events, start):
    if events and start <= events[-1]["frame"]:
        raise ValueError("Choose a frame after the last attachment change. Earlier switches are protected.")


def _key_state(choice, frame, index):
    count = cmds.setKeyframe(choice, attribute="selector", time=frame, value=index, outTangentType="step")
    if count != 1:
        raise RuntimeError("Maya could not key the attachment state.")


def _style_follow_curve(plug, rgb=None):
    curve = _direct_curve(plug)
    if curve:
        color = curve + ".curveColor"
        use_color = curve + ".useCurveColor"
        if ((rgb is not None or not cmds.getAttr(use_color))
                and cmds.getAttr(color, settable=True) and cmds.getAttr(use_color, settable=True)):
            cmds.setAttr(color, *(rgb or FOLLOW_KEY_COLOR), type="float3")
            cmds.setAttr(use_color, True)


def _write_event(driven, setup, events, event):
    choice = _linked(setup, "aminateChoice")
    time = cmds.currentTime(query=True)
    if not events:
        _key_state(choice, event["start"] - 1.0, 0)
    if time != event["start"]:
        cmds.currentTime(event["start"], edit=True)
    try:
        _key_state(choice, event["start"], event["index"])
    finally:
        # setKeyframe(value=...) can leave the current evaluation cached.
        # Advance the time input without drawing another frame, then evaluate.
        cmds.currentTime(time - 0.5, edit=True, update=False)
        cmds.currentTime(time, edit=True)
    if cmds.getAttr(choice + ".selector") != event["index"]:
        raise RuntimeError("Maya did not evaluate the keyed attachment state.")
    _style_follow_curve(choice + ".selector")
    _save_events(driven, setup, events + [event])


def _set_probe_attr(probe, attr, value):
    if isinstance(value, list):
        cmds.setAttr(probe + "." + attr, *value[0], type="double3")
    else:
        cmds.setAttr(probe + "." + attr, value)


def _release_values(driven, setup, pose, channels):
    baseline = _linked(setup, "aminateBaseline")
    parent_inverse = _inverse(_world(_parent(driven)))
    original_inverse = _inverse(_matrix(baseline + ".matrixIn[1]"))
    desired_local = pose * parent_inverse * original_inverse
    probe = _new_node("transform", "ReleaseProbe")
    fixed = {attr: cmds.getAttr(driven + "." + attr) for attr in FIXED_TRANSFORM_ATTRS}
    for attr, value in fixed.items():
        _set_probe_attr(probe, attr, value)
    for attr in CHANNELS:
        _set_probe_attr(probe, attr, cmds.getAttr(driven + "." + attr))
    cmds.xform(probe, objectSpace=True, matrix=tuple(desired_local))
    values = {
        attr + axis: cmds.getAttr(probe + "." + attr + axis)
        for attr in channels
        for axis in AXES
    }
    cmds.delete(probe)
    return values


def _key_release_channel(node, channel, frame, value):
    count = cmds.setKeyframe(node, attribute=channel, time=frame, value=value, noResolve=True)
    if count != 1:
        raise RuntimeError("Maya could not key " + channel + " on release.")


def _key_release(driven, setup, pose, channels, frame, guard):
    keys = {}
    if not channels:
        return keys
    values = _release_values(driven, setup, pose, channels)
    for channel, value in values.items():
        plug = driven + "." + channel
        current = cmds.getAttr(plug)
        incoming = cmds.connectionInfo(plug, sourceFromDestination=True)
        curve = incoming.split(".", 1)[0]
        animated = bool(curve and cmds.nodeType(curve).startswith("animCurve"))
        writable = not cmds.getAttr(plug, lock=True) and (not incoming or animated)
        if not writable:
            if abs(current - value) > TOLERANCE:
                raise ValueError("The rig drives or locks " + channel + ". Aminate cannot preserve this pose.")
            continue
        if guard < frame:
            if animated:
                if not cmds.keyframe(curve, time=(guard, guard), query=True, keyframeCount=True):
                    if not cmds.setKeyframe(curve, time=guard, insert=True):
                        raise RuntimeError("Maya could not preserve the existing " + channel + " curve.")
            else:
                _key_release_channel(driven, channel, guard, cmds.getAttr(plug, time=guard))
        replaced = animated and _has_key(curve, frame)
        _key_release_channel(driven, channel, frame, value)
        keys[channel] = {"value": value, "replaced": replaced}
    return keys


def _has_key(curve, frame):
    return bool(cmds.keyframe(curve, time=(frame, frame), query=True, keyframeCount=True))


def _new_attachment_output(setup, target, relative_pose, channels):
    baseline = _linked(setup, "aminateBaseline")
    world = _new_node("multMatrix", "TargetWorld")
    _set_matrix(world + ".matrixIn[0]", relative_pose)
    if target:
        cmds.connectAttr(target + ".worldMatrix[0]", world + ".matrixIn[1]")
    blend = _new_node("blendMatrix", "Channels")
    cmds.connectAttr(baseline + ".matrixSum", blend + ".inputMatrix")
    cmds.connectAttr(world + ".matrixSum", blend + ".target[0].targetMatrix")
    for channel in CHANNELS + ("shear",):
        cmds.setAttr(blend + ".target[0]." + channel + "Weight", float(channel in channels))
    return blend + ".outputMatrix"


def _blend_transition(choice, previous_index, output, start, frame):
    blend = _new_node("blendMatrix", "Transition")
    previous = cmds.connectionInfo(choice + ".input[{}]".format(previous_index), sourceFromDestination=True)
    cmds.connectAttr(previous, blend + ".inputMatrix")
    cmds.connectAttr(output, blend + ".target[0].targetMatrix")
    weight = blend + ".target[0].weight"
    for time, value in ((start, 0.0), (frame, 1.0)):
        if cmds.setKeyframe(weight, time=time, value=value, inTangentType="linear", outTangentType="linear") != 1:
            raise RuntimeError("Maya could not key the Match Point transition.")
    _style_follow_curve(weight)
    return blend + ".outputMatrix"


def _verify_pose(driven, expected):
    if not _near(_world(driven), expected):
        raise ValueError("Aminate could not preserve the requested pose with these channels and this rig.")


def attach(driven, target, point=None, channels=("translate", "rotate"), match_start=None, *, end_frame=None):
    """Key a new follow, using the current frame when no arrival frame is supplied."""
    driven = _transform(driven)
    target = _transform(target) if target else None
    if not channels or set(channels).difference(CHANNELS):
        raise ValueError("Choose Translate, Rotate, Scale, or any combination.")
    channels = tuple(channel for channel in CHANNELS if channel in channels)
    point, _shape = _point_shape(point) if point else (None, None)
    if point and (cmds.listRelatives(point, parent=True, fullPath=True) or [None])[0] != target:
        raise ValueError("Choose a point that belongs to the selected parent.")
    _check_cycle(driven, target)
    frame = float(cmds.currentTime(query=True) if end_frame is None else end_frame)
    start = frame if match_start is None else float(match_start)
    if not (math.isfinite(start) and math.isfinite(frame)):
        raise ValueError("Enter valid movement frames.")
    if start > frame:
        raise ValueError("Start moving on or before the arrival frame.")
    setup = _setup(driven)
    _check_setup(setup, driven)
    events = _read_events(setup)
    _frame_for_edit(events, start)
    previous = _active(events, start)
    previous_index = previous["index"] if previous else 0
    name = cmds.getAttr(point + "." + POINT_TAG) if point else (target.rsplit("|", 1)[-1] if target else "World")
    action = "switch" if previous_index else "attach"
    with _edit(action.title(), end_time=frame if end_frame is not None else None):
        if cmds.currentTime(query=True) != frame:
            cmds.currentTime(frame, edit=True)
        before = _world(driven)
        inverse_target = _inverse(_world(target))
        reference = before if match_start is None else _world(point or target)
        relative_pose = reference * inverse_target
        if not setup:
            setup = _create_setup(driven)
            _verify_pose(driven, before)
        choice = _linked(setup, "aminateChoice")
        index = max([event["index"] for event in events] + [0]) + 1
        output = _new_attachment_output(setup, target, relative_pose, channels)
        expected = _matrix(output) if match_start is not None else before
        if end_frame is None and match_start is not None and start == frame and not _near(expected, before):
            raise ValueError("The object is away from this point. Set an earlier transition start frame.")
        release = {}
        if previous_index and match_start is None:
            released = set(previous["channels"]).difference(channels)
            guard = previous["start"]
            release = _key_release(driven, setup, before, sorted(released), frame, guard)
        if start < frame:
            output = _blend_transition(choice, previous_index, output, start, frame)
        cmds.connectAttr(output, choice + ".input[{}]".format(index))
        _write_event(driven, setup, events, {
            "frame": frame, "start": start, "action": action, "index": index,
            "target": _uuid(target), "point": _uuid(point), "name": name, "channels": channels,
            "match": match_start is not None, "release": release,
        })
        cmds.dgdirty(driven)
        _verify_pose(driven, expected)


def detach(driven):
    """Key attachment off on this frame and key the evaluated release pose."""
    driven = _transform(driven)
    setup = _setup(driven)
    _check_setup(setup, driven)
    events = _read_events(setup)
    frame = float(cmds.currentTime(query=True))
    current = _active(events, frame)
    if not current or not current["index"]:
        raise ValueError("This object has no active attachment on this frame.")
    _frame_for_edit(events, frame)
    pose = _world(driven)
    channels = CHANNELS if "scale" in current["channels"] else CHANNELS[:2]
    detached_at = next(
        (event["start"] for event in reversed(events) if not event["index"]), float("-inf")
    )
    first_attached = next(event["start"] for event in events if event["start"] > detached_at)
    with _edit("Detach"):
        release = _key_release(driven, setup, pose, channels, frame, first_attached)
        _write_event(driven, setup, events, {
            "frame": frame, "start": frame, "action": "detach", "index": 0,
            "target": "", "point": "", "name": "", "channels": (),
            "release": release,
        })
        cmds.dgdirty(driven)
        _verify_pose(driven, pose)


def _direct_curve(plug):
    node = cmds.connectionInfo(plug, sourceFromDestination=True).split(".", 1)[0]
    return node if node and cmds.nodeType(node).startswith("animCurve") else None


def _require_keys(curve, times, values):
    if (not curve or cmds.keyframe(curve, query=True, timeChange=True) != times
            or cmds.keyframe(curve, query=True, valueChange=True) != values):
        raise ValueError("The follow keys changed outside Parent Manager. Restore them before editing this change.")


def _move_keys(curve, start, end, offset):
    cmds.keyframe(curve, edit=True, time=(start, end), relative=True, timeChange=offset, option="over")


def _release_channels(event, previous):
    if not previous or not previous["index"]:
        return ()
    if not event["index"]:
        return CHANNELS if "scale" in previous["channels"] else CHANNELS[:2]
    if event.get("match", event["start"] < event["frame"]):
        return ()
    return tuple(channel for channel in previous["channels"] if channel not in event["channels"])


def _protected_release(driven, event, previous):
    keys = event.get("release", {})
    for group in _release_channels(event, previous):
        for axis in AXES:
            channel = group + axis
            plug = driven + "." + channel
            curve = _direct_curve(plug)
            key = keys.get(channel)
            current = cmds.keyframe(curve, time=(event["frame"], event["frame"]),
                                    query=True, valueChange=True) if curve else None
            if ((current or key) and (not key or key["replaced"] or not current
                                      or abs(current[0] - key["value"]) > TOLERANCE)
                    or cmds.getAttr(plug, lock=True)):
                return True
    return False


def _retime_release(driven, setup, event, channels, pose, old_frame):
    frame = event["frame"]
    keys = event.get("release", {})
    values = _release_values(driven, setup, pose, channels)
    for channel, value in values.items():
        plug = driven + "." + channel
        if old_frame == frame and abs(cmds.getAttr(plug) - value) <= TOLERANCE:
            continue
        key = keys.get(channel)
        curve = _direct_curve(plug)
        if not curve and not key and abs(cmds.getAttr(plug) - value) <= TOLERANCE:
            continue
        current = cmds.keyframe(curve, time=(old_frame, old_frame), query=True, valueChange=True) if curve else None
        if (not key or key["replaced"] or not current or abs(current[0] - key["value"]) > TOLERANCE
                or cmds.getAttr(plug, lock=True)):
            raise ValueError("A release pose uses older or edited keys. Its animation has been protected.")
        if frame != old_frame:
            if _has_key(curve, frame):
                raise ValueError("The new frame already has a key on " + channel + ". Choose another frame.")
            _move_keys(curve, old_frame, old_frame, frame - old_frame)
            if _has_key(curve, old_frame) or not _has_key(curve, frame):
                raise RuntimeError("Maya could not move the release pose key.")
        _key_release_channel(driven, channel, frame, value)
        key["value"] = value


def _input_source(plug):
    source = cmds.connectionInfo(plug, sourceFromDestination=True).split(".", 1)[0]
    if not source:
        raise ValueError("A follow connection is missing. Restore it before moving this change.")
    return source


def _rebase_events(driven, setup, choice, events, index, old_frame=None):
    previous = events[index - 1] if index else None
    for position, event in enumerate(events[index:], start=index):
        previous_index = previous["index"] if previous else 0
        prior_output = f"{choice}.input[{previous_index}]"
        frame = event["frame"]
        cmds.currentTime(frame, edit=True)
        pose = _matrix(prior_output)
        channels = _release_channels(event, previous)
        if channels:
            source_frame = old_frame if position == index and old_frame is not None else frame
            _retime_release(driven, setup, event, channels, pose, source_frame)
        if event["index"] and event.get("match", event["start"] < frame):
            cmds.currentTime(event["start"], edit=True)
            _verify_pose(driven, _matrix(prior_output))
        else:
            if event["index"]:
                target = _resolve(event["target"])
                if event["target"] and not target:
                    raise ValueError("A parent is missing. Restore it before moving this change.")
                output = _input_source(f"{choice}.input[{event['index']}]")
                world = _input_source(output + ".target[0].targetMatrix")
                _set_matrix(world + ".matrixIn[0]", pose * _inverse(_world(target)))
            cmds.dgdirty(driven)
            _verify_pose(driven, pose)
        previous = event


def move_follow_change(driven, frame, new_frame, jump=False):
    """Move one history row, its Maya keys, and its bookmarks as a single undo."""
    driven = _transform(driven)
    setup = _setup(driven)
    _check_setup(setup, driven)
    events = _read_events(setup)
    index = next((i for i, event in enumerate(events) if event["frame"] == frame), None)
    if index is None or not math.isfinite(new_frame):
        raise ValueError("Choose a change in Follow history and a valid frame.")
    offset = new_frame - frame
    if not offset:
        return
    event = events[index]
    start = event["start"]
    new_start = start + offset
    if ((index and new_start <= events[index - 1]["frame"])
            or (index + 1 < len(events) and new_frame >= events[index + 1]["start"])):
        raise ValueError("There is another follow change in the way. Move that one first.")
    choice = _linked(setup, "aminateChoice")
    selector = _direct_curve(choice + ".selector")
    key_start = events[0]["start"] - 1
    times = [key_start] + [entry["start"] for entry in events]
    indices = [0] + [entry["index"] for entry in events]
    _require_keys(selector, times, indices)
    with _edit("Move follow change", end_time=new_frame if jump else None):
        _move_keys(selector, start if index else key_start, start, offset)
        times[index + 1] = new_start
        if not index:
            times[0] += offset
        _require_keys(selector, times, indices)
        if start < frame:
            transition = _input_source(f"{choice}.input[{event['index']}]")
            weight = _direct_curve(transition + ".target[0].weight")
            _require_keys(weight, [start, frame], [0, 1])
            _move_keys(weight, start, frame, offset)
            _require_keys(weight, [new_start, new_frame], [0, 1])
        event["start"] = new_start
        event["frame"] = new_frame
        _rebase_events(driven, setup, choice, events, index, frame)
        _save_events(driven, setup, events)


def remove_follow_change(driven, frame):
    """Remove a switch and its markers, preserving the object's transform keys."""
    driven = _transform(driven)
    setup = _setup(driven)
    _check_setup(setup, driven)
    events = _read_events(setup)
    index = next((i for i, event in enumerate(events) if event["frame"] == frame), None)
    if index is None:
        raise ValueError("Choose a row in Follow history.")
    choice = _linked(setup, "aminateChoice")
    selector = _direct_curve(choice + ".selector")
    guard = events[0]["start"] - 1
    _require_keys(selector, [guard] + [event["start"] for event in events],
                  [0] + [event["index"] for event in events])
    removed = events.pop(index)
    with _edit("Remove follow change"):
        cmds.cutKey(selector, time=(removed["start"], removed["start"]), clear=True)
        if not events:
            cmds.cutKey(selector, time=(guard, guard), clear=True)
            if not _direct_curve(choice + ".selector"):
                cmds.setAttr(choice + ".selector", 0)
        else:
            new_guard = events[0]["start"] - 1
            if guard != new_guard:
                _move_keys(selector, guard, guard, new_guard - guard)
            _require_keys(selector, [new_guard] + [event["start"] for event in events],
                          [0] + [event["index"] for event in events])
            if index < len(events):
                previous = events[index - 1]["index"] if index else 0
                successor = events[index]
                if successor["index"]:
                    successor["action"] = "switch" if previous else "attach"
                if successor["start"] < successor["frame"]:
                    transition = _input_source(f"{choice}.input[{successor['index']}]")
                    source = cmds.connectionInfo(f"{choice}.input[{previous}]", sourceFromDestination=True)
                    cmds.connectAttr(source, transition + ".inputMatrix", force=True)
                _rebase_events(driven, setup, choice, events, index)
        if removed["index"]:
            plug = f"{choice}.input[{removed['index']}]"
            output = cmds.connectionInfo(plug, sourceFromDestination=True)
            cmds.removeMultiInstance(plug, b=True)
            _retire_attachment_output(output)
        for identifier in removed.get("bookmarks", []):
            bookmark = _bookmark_node(identifier)
            if bookmark:
                cmds.delete(bookmark)
        _save_events(driven, setup, events)


def _retire_attachment_output(output):
    # A later ramp or a custom rig connection can still consume an old branch.
    # Delete only the now-unused nodes created by this setup.
    while output and cmds.objExists(output) and not cmds.connectionInfo(output, isSource=True):
        node = output.split(".", 1)[0]
        name = node.rsplit(":", 1)[-1]
        if not name.startswith(("aminateParentTransition", "aminateParentChannels", "aminateParentTargetWorld")):
            return
        if cmds.listConnections(node, source=False, destination=True):
            return
        target = node + ".target[0].targetMatrix"
        upstream = cmds.connectionInfo(target, sourceFromDestination=True) if cmds.objExists(target) else ""
        weight = node + ".target[0].weight"
        curve = _direct_curve(weight) if name.startswith("aminateParentTransition") else None
        cmds.delete(node)
        if curve and cmds.objExists(curve) and not cmds.connectionInfo(curve + ".output", isSource=True):
            cmds.delete(curve)
        output = upstream
