"""Read-only IK/FK graph discovery and driven-pose matching for Maya limbs."""

import math

try:
    from maya import cmds
    from maya.api import OpenMaya as om
except ImportError:
    cmds = om = None


_AXES = "XYZ"
_CONSTRAINTS = {"parentConstraint", "pointConstraint", "orientConstraint"}


def _node(plug):
    matches = cmds.ls(plug.split(".", 1)[0], long=True) or []
    return matches[0] if len(matches) == 1 else ""


def _plug(plug):
    return _node(plug) + "." + plug.split(".", 1)[1]


def _incoming(plug):
    source = cmds.connectionInfo(plug, sourceFromDestination=True)
    return _plug(source) if source and _node(source) else ""


def _outputs(plug):
    return cmds.listConnections(plug, source=False, destination=True, plugs=True) or []


def _constraint_targets(node):
    command = getattr(cmds, cmds.nodeType(node))
    targets = command(node, query=True, targetList=True) or []
    return [_node(target) for target in targets]


def _control_like(node):
    if not node or cmds.nodeType(node) != "transform":
        return False
    return any(cmds.nodeType(shape) in {"nurbsCurve", "nurbsSurface", "locator", "mesh"}
               for shape in cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or [])


def _parents(node):
    return cmds.listRelatives(node, parent=True, fullPath=True) or []


def _driving_control(node, channel, depth=0):
    if depth > 5 or not node:
        return ""
    if _control_like(node):
        return node
    sources = [_incoming(node + "." + channel + axis) for axis in _AXES]
    driven = [(axis, source) for axis, source in zip(_AXES, sources) if source]
    if driven:
        controls = set()
        for axis, source in driven:
            driver, attr = source.split(".", 1)
            kind = cmds.nodeType(driver)
            if kind in _CONSTRAINTS and attr == "constraint" + channel.capitalize() + axis:
                targets = _constraint_targets(driver)
                if len(targets) == 1:
                    controls.add(_driving_control(targets[0], channel, depth + 1))
                else:
                    return ""
            elif kind in {"transform", "joint"} and attr in {channel, channel + axis}:
                controls.add(_driving_control(driver, channel, depth + 1))
            elif kind == "decomposeMatrix" and attr in {"output" + channel.capitalize(), "output" + channel.capitalize() + axis}:
                controls.add(_matrix_control(driver, channel, depth))
            elif kind == "pairBlend" and channel == "translate" and attr in {"outTranslate", "outTranslate" + axis}:
                controls.add(_translation_pair_control(driver, depth))
            else:
                return ""
        return next(iter(controls)) if len(controls) == 1 else ""
    parent = _parents(node)
    return _driving_control(parent[0], channel, depth + 1) if parent else ""


def _matrix_control(driver, channel, depth):
    source = _incoming(driver + ".inputMatrix")
    if not source:
        return ""
    source_node, attribute = source.split(".", 1)
    if cmds.nodeType(source_node) == "multMatrix" and attribute == "matrixSum":
        indices = cmds.getAttr(source_node + ".matrixIn", multiIndices=True) or []
        inverse = _incoming(source_node + ".matrixIn[1]") if indices == [0, 1] else ""
        if not inverse or inverse.split(".", 1)[1] not in {"worldInverseMatrix[0]", "parentInverseMatrix[0]"}:
            return ""
        source = _incoming(source_node + ".matrixIn[0]")
    if source and source.split(".", 1)[1] == "worldMatrix[0]":
        node = _node(source)
        shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or []
        if shapes and all(cmds.nodeType(shape) == "locator" for shape in shapes):
            parent = _parents(node)
            if parent and _control_like(parent[0]):
                node = parent[0]
        return _driving_control(node, channel, depth + 1)
    return ""


def _translation_pair_control(driver, depth):
    if not math.isclose(cmds.getAttr(driver + ".weight"), 0.0, abs_tol=1e-8):
        return ""
    inputs = [_incoming(driver + ".inTranslate" + axis + "1") for axis in _AXES]
    nodes = {_node(source) for source in inputs if source}
    if len(nodes) != 1 or not all(inputs):
        return ""
    source = next(iter(nodes))
    if cmds.nodeType(source) == "decomposeMatrix":
        return _matrix_control(source, "translate", depth + 1)
    return ""


def _affine_utility(node, kind, attr):
    if kind == "multiplyDivide" and attr in {"outputX", "outputY", "outputZ"}:
        operation = cmds.getAttr(node + ".operation")
        first, second = "input1" + attr[-1], "input2" + attr[-1]
        if _incoming(node + "." + first) and not _incoming(node + "." + second):
            constant = cmds.getAttr(node + "." + second)
            if operation == 1:
                return first, constant, 0.0
            if operation == 2 and abs(constant) > 1e-10:
                return first, 1 / constant, 0.0
    if kind == "plusMinusAverage" and attr in {"output2Dx", "output2Dy"}:
        operation = cmds.getAttr(node + ".operation")
        indices = cmds.getAttr(node + ".input2D", multiIndices=True) or []
        inputs = ["input2D[{}].input2D{}".format(index, attr[-1]) for index in indices]
        driven = [name for name in inputs if _incoming(node + "." + name)]
        if operation not in (1, 2, 3) or len(driven) != 1:
            return None
        weights = [(-1.0 if operation == 2 and index else 1.0) / (len(inputs) if operation == 3 else 1)
                   for index in range(len(inputs))]
        bias = sum(gain * cmds.getAttr(node + "." + name) for name, gain in zip(inputs, weights) if name != driven[0])
        return driven[0], weights[inputs.index(driven[0])], bias
    return None


def _linear(plug, depth=0):
    """Return source, gain, bias for explicitly supported weight routing."""
    if depth > 8:
        return None
    source = _incoming(plug)
    if not source:
        if "." in plug and cmds.nodeType(_node(plug)) in {"transform", "joint"}:
            if cmds.getAttr(plug, settable=True) and cmds.getAttr(plug, keyable=True):
                return plug, 1.0, 0.0
        return None
    node, attr = source.split(".", 1)
    kind = cmds.nodeType(node)
    if kind in {"transform", "joint"} and cmds.getAttr(source, settable=True) and cmds.getAttr(source, keyable=True):
        return source, 1.0, 0.0
    if kind == "reverse" and attr.startswith("output"):
        incoming, gain, bias = ("input" + attr[-1], -1.0, 1.0)
    elif kind == "unitConversion":
        incoming, gain, bias = "input", cmds.getAttr(node + ".conversionFactor"), 0.0
    elif kind in {"multDoubleLinear", "addDoubleLinear"}:
        inputs = ["input1", "input2"]
        driven = [name for name in inputs if _incoming(node + "." + name)]
        if len(driven) != 1:
            return None
        incoming = driven[0]
        constant = cmds.getAttr(node + "." + next(name for name in inputs if name != incoming))
        gain, bias = (constant, 0.0) if kind == "multDoubleLinear" else (1.0, constant)
    else:
        affine = _affine_utility(node, kind, attr)
        if not affine:
            return None
        incoming, gain, bias = affine
    path = _linear(node + "." + incoming, depth + 1)
    return (path[0], gain * path[1], gain * path[2] + bias) if path else None


def _endpoints(weight, first, second):
    path = _linear(weight)
    if not path or abs(path[1]) < 1e-10:
        return None
    plug, gain, bias = path
    values = [(weight_value - bias) / gain for weight_value in (first, second)]
    node, attr = plug.split(".", 1)
    if cmds.attributeQuery(attr, node=node, minExists=True):
        if min(values) < cmds.attributeQuery(attr, node=node, minimum=True)[0] - 1e-6:
            return None
    if cmds.attributeQuery(attr, node=node, maxExists=True):
        if max(values) > cmds.attributeQuery(attr, node=node, maximum=True)[0] + 1e-6:
            return None
    return (plug, *values)


def _branch_source(plug, channel, axis):
    source = _incoming(plug)
    node = _node(source) if source else ""
    if node and cmds.nodeType(node) == "unitConversion":
        source = _incoming(node + ".input")
        node = _node(source) if source else ""
    if node and cmds.nodeType(node) in _CONSTRAINTS:
        if source.split(".", 1)[1] != "constraint" + channel.capitalize() + axis:
            return ""
        targets = _constraint_targets(node)
        return targets[0] if len(targets) == 1 else ""
    if node and source.split(".", 1)[1] in {channel, channel + axis}:
        return node
    return ""


def _pair_routes(ik_joint, blend):
    if cmds.getAttr(blend + ".rotateMode") != 0:
        return []
    branches = [[_branch_source(blend + ".inRotate" + axis + str(index), "rotate", axis) for axis in _AXES]
                for index in (1, 2)]
    if any(not branch[0] or len(set(branch)) != 1 for branch in branches):
        return []
    if [branch[0] for branch in branches].count(ik_joint) != 1:
        return []
    ik_index = [branch[0] for branch in branches].index(ik_joint)
    fk_driver = branches[1 - ik_index][0]
    switch = _endpoints(blend + ".weight", 1 - ik_index, ik_index)
    if not switch:
        return []
    return [(node, fk_driver, switch, blend) for node in _rotation_outputs(blend, "outRotate")]


def _color_routes(ik_joint, blend):
    branches = [[_branch_source(blend + ".color" + str(index) + color, "rotate", axis)
                 for color, axis in zip("RGB", _AXES)]
                for index in (1, 2)]
    if any(not branch[0] or len(set(branch)) != 1 for branch in branches):
        return []
    if [branch[0] for branch in branches].count(ik_joint) != 1:
        return []
    ik_index = [branch[0] for branch in branches].index(ik_joint)
    switch = _endpoints(blend + ".blender", ik_index, 1 - ik_index)
    if not switch:
        return []
    return [(node, branches[1 - ik_index][0], switch, blend)
            for node in _rotation_outputs(blend, "output", "RGB")]


def _through_conversion(plug):
    outputs = _outputs(plug)
    return [out for item in outputs for out in (
        _outputs(_node(item) + ".output") if _node(item) and cmds.nodeType(_node(item)) == "unitConversion" else [item]
    )]


def _rotation_outputs(node, attr, components=_AXES):
    compounds = {_node(plug) for plug in _through_conversion(node + "." + attr)
                 if plug.endswith(".rotate") and _node(plug) and cmds.nodeType(_node(plug)) == "joint"}
    outputs = [{_node(plug) for plug in _through_conversion(node + "." + attr + component)
                if plug.endswith(".rotate" + axis) and _node(plug) and cmds.nodeType(_node(plug)) == "joint"}
               for axis, component in zip(_AXES, components)]
    return compounds | set.intersection(*outputs)


def _constraint_routes(ik_joint, constraint):
    targets = _constraint_targets(constraint)
    if len(targets) != 2 or targets.count(ik_joint) != 1 or not all(targets):
        return []
    weights = getattr(cmds, cmds.nodeType(constraint))(constraint, query=True, weightAliasList=True) or []
    if len(weights) != 2:
        return []
    ik_index = targets.index(ik_joint)
    ik_switch = _endpoints(constraint + "." + weights[ik_index], 0, 1)
    fk_switch = _endpoints(constraint + "." + weights[1 - ik_index], 1, 0)
    if not _same_switch(ik_switch, fk_switch):
        return []
    return [(node, targets[1 - ik_index], ik_switch, constraint)
            for node in _rotation_outputs(constraint, "constraintRotate")]


def _same_switch(first, second):
    return bool(first and second and first[0] == second[0]
                and all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(first[1:], second[1:])))


def _result_routes(ik_joint):
    downstream = cmds.listConnections(ik_joint, source=False, destination=True, skipConversionNodes=True) or []
    pairs = set()
    routes = []
    for item in set(downstream):
        node = _node(item)
        if not node:
            continue
        kind = cmds.nodeType(node)
        if kind == "pairBlend":
            pairs.add(node)
        elif kind == "blendColors":
            routes.extend(_color_routes(ik_joint, node))
        elif kind in _CONSTRAINTS:
            if kind != "pointConstraint":
                routes.extend(_constraint_routes(ik_joint, node))
            pairs.update(_node(blend) for blend in cmds.listConnections(node, source=False, destination=True,
                                                                       type="pairBlend") or [])
    for blend in sorted(pairs - {""}):
        routes.extend(_pair_routes(ik_joint, blend))
    return routes


def _ik_chain(handle):
    solvers = cmds.listConnections(handle + ".ikSolver", source=True, destination=False) or []
    if len(solvers) != 1 or cmds.nodeType(solvers[0]) != "ikRPsolver":
        return []
    joints = cmds.ikHandle(handle, query=True, jointList=True) or []
    effector = cmds.ikHandle(handle, query=True, endEffector=True)
    end = _branch_source(_node(effector) + ".translateX", "translate", "X") if effector else ""
    if len(joints) != 2 or not end or cmds.nodeType(end) != "joint":
        return []
    chain = [_node(joint) for joint in joints] + [end]
    return chain if all(_parents(child) == [parent] for parent, child in zip(chain, chain[1:])) else []


def _ik_end_control(handle, terminal):
    end = _driving_control(handle, "translate")
    orientation = _driving_control(terminal, "rotate")
    if orientation and end and (end == orientation or end.startswith(orientation + "|")):
        return orientation
    if end:
        return end
    parent = _parents(handle)
    while parent and cmds.getAttr(parent[0] + ".inheritsTransform"):
        node = parent[0]
        rotation = _incoming(node + ".rotateX")
        aim = _node(rotation) if rotation else ""
        if aim and cmds.nodeType(aim) == "aimConstraint":
            up = _incoming(aim + ".worldUpMatrix")
            target = _node(up) if up else ""
            if _control_like(target) and node.startswith(target + "|"):
                return target
        if _control_like(node):
            return node
        parent = _parents(node)
    return end


def _pole_control(handle):
    drivers = {_node(source) for source in (_incoming(handle + ".poleVector" + axis) for axis in _AXES) if source}
    if len(drivers) != 1:
        return ""
    driver = next(iter(drivers))
    if cmds.nodeType(driver) == "poleVectorConstraint":
        targets = _constraint_targets(driver)
        return targets[0] if len(targets) == 1 else ""
    if cmds.nodeType(driver) == "plusMinusAverage" and cmds.getAttr(driver + ".operation") == 2:
        first, second = [_incoming(driver + ".input3D[{}]".format(index))
                         or _incoming(driver + ".input3D[{}].input3Dx".format(index)) for index in (0, 1)]
        if first and second and all(cmds.nodeType(_node(plug)) == "decomposeMatrix" for plug in (first, second)):
            return _matrix_control(_node(first), "translate", 0)
    return ""


def _enum_endpoints(plug):
    """Read a two-state SDK's keyed values without changing the enum."""
    source = _incoming(plug)
    if source and source != plug and _node(source) == _node(plug):
        source = _incoming(source)
    curve = _node(source) if source else ""
    if not curve or cmds.nodeType(curve) != "animCurveUU" or source.split(".", 1)[1] != "output":
        return None
    driver = _incoming(curve + ".input")
    if not driver or cmds.getAttr(driver, type=True) != "enum" or not cmds.getAttr(driver, keyable=True):
        return None
    indices = cmds.keyframe(curve, query=True, floatChange=True) or []
    values = cmds.keyframe(curve, query=True, valueChange=True) or []
    if len(indices) == len(values) == 2 and all(index == int(index) for index in indices):
        return driver, dict(zip(indices, values))
    return None


def _same_chain_routes(handle, chain, end):
    route = _enum_endpoints(handle + ".ikBlend")
    if not route or set(route[1].values()) != {0, 1}:
        return None
    setting, values = route
    fk_value = next(key for key, value in values.items() if value == 0)
    ik_value = next(key for key, value in values.items() if value == 1)
    drivers = []
    constraints = []
    for index, joint in enumerate(chain):
        inputs = [_incoming(joint + ".rotate" + axis) for axis in _AXES]
        nodes = {_node(plug) for plug in inputs if plug}
        if len(nodes) != 1 or not all(inputs):
            return None
        constraint = next(iter(nodes))
        if cmds.nodeType(constraint) != "orientConstraint" or joint not in _rotation_outputs(constraint, "constraintRotate"):
            return None
        targets = _constraint_targets(constraint)
        if index < 2 and len(targets) == 1:
            drivers.append(targets[0])
        elif index == 2 and len(targets) == 2 and end in targets:
            fk_index = 1 - targets.index(end)
            indices = cmds.getAttr(constraint + ".target", multiIndices=True) or []
            if len(indices) != len(targets):
                return None
            weights = _enum_endpoints(constraint + ".target[{}].targetWeight".format(indices[fk_index]))
            if not weights or weights[0] != setting or weights[1].get(ik_value) != 0 or weights[1].get(fk_value, 0) <= 0:
                return None
            drivers.append(targets[fk_index])
        else:
            return None
        constraints.append(constraint)
    return chain, drivers, [(setting, fk_value, ik_value)] * 3, constraints


def _same_setting_ancestor(control, switch, root):
    parent = _parents(control)
    while parent and parent[0] != root and not _control_like(parent[0]):
        node = parent[0]
        source = _incoming(node + ".rotateX")
        constraint = _node(source) if source else ""
        if constraint and cmds.nodeType(constraint) in {"orientConstraint", "parentConstraint"}:
            aliases = getattr(cmds, cmds.nodeType(constraint))(constraint, query=True, weightAliasList=True) or []
            weights = [_endpoints(constraint + "." + alias, 0, 1) for alias in aliases]
            reverse = (switch[0], switch[2], switch[1])
            if (len(weights) == 2 and any(_same_switch(weight, switch) for weight in weights)
                    and any(_same_switch(weight, reverse) for weight in weights)):
                return True
        parent = _parents(node)
    return False


def _auxiliary_links(terminal, ik_terminal, end, switch, root, primary_controls):
    """Find directly constrained terminal children affected by the same switch."""
    links = []
    for joint in cmds.listRelatives(terminal, children=True, fullPath=True, type="joint") or []:
        source = _incoming(joint + ".rotateX")
        constraint = _node(source) if source else ""
        if not constraint or cmds.nodeType(constraint) not in {"orientConstraint", "parentConstraint"}:
            continue
        if joint not in _rotation_outputs(constraint, "constraintRotate"):
            continue
        targets = _constraint_targets(constraint)
        if len(targets) == 1:
            control = _driving_control(targets[0], "rotate")
            if (control and control not in primary_controls and control.startswith(root + "|")
                    and _same_setting_ancestor(control, switch, root)):
                links.append((joint, control, control))
            continue
        ik_targets = [target for target in targets if target.startswith(ik_terminal + "|")]
        if len(ik_targets) != 1:
            continue
        for result, fk_driver, endpoints, _ in _constraint_routes(ik_targets[0], constraint):
            if result != joint or not _same_switch(endpoints, switch):
                continue
            fk_control = _driving_control(fk_driver, "rotate")
            ik_control = _driving_control(ik_targets[0], "rotate")
            if not fk_control or fk_control in primary_controls or not fk_control.startswith(root + "|"):
                continue
            if not ik_control.startswith(end + "|") or ik_control in primary_controls:
                ik_control = ""
            links.append((joint, fk_control, ik_control))
    return links


def _handle_profile(handle, root):
    chain = _ik_chain(handle)
    if len(chain) != 3 or not all(chain):
        return None
    end = _ik_end_control(handle, chain[-1])
    pole = _pole_control(handle)
    if not end or not _control_like(pole) or end == pole:
        return None
    routes = [_result_routes(joint) for joint in chain]
    if all(len(link) == 1 for link in routes):
        result, fk_drivers, switches, blends = zip(*(link[0] for link in routes))
    else:
        same_chain = _same_chain_routes(handle, chain, end)
        if not same_chain:
            return None
        result, fk_drivers, switches, blends = same_chain
    if not all(_parents(child) == [parent] for parent, child in zip(result, result[1:])):
        return None
    if not all(_same_switch(switches[0], switch) for switch in switches[1:]):
        return None
    fk = [_driving_control(node, "rotate") for node in fk_drivers]
    if len(set(fk + [end, pole])) != 5 or not all(fk):
        return None
    plug, fk_value, ik_value = switches[0]
    settings = _node(plug)
    if not all(node.startswith(root + "|") or node == root for node in (*result, *fk, end, pole, settings)):
        return None
    aux = _auxiliary_links(result[-1], chain[-1], end, switches[0], root, set(fk + [end, pole]))
    identity_nodes = [root, handle, settings, *result, *fk, *fk_drivers, *chain, *blends, end, pole,
                      *(node for link in aux for node in link if node)]
    return {
        "profile_name": end.rsplit("|", 1)[-1], "rig_root": root, "chain_mode": "limb",
        "fk_controls": fk, "ik_controls": [end, pole], "ik_control": end, "pole_vector_control": pole,
        "switch_attr": plug, "fk_value": fk_value, "ik_value": ik_value, "match_nodes": list(result),
        "result_nodes": list(result) + [joint for joint, _, _ in aux], "ik_match_node": result[-1], "detection_kind": "graph",
        "detection_evidence": {"handle": handle, "branches": list(blends), "settings": settings,
                               "driver_nodes": list(fk_drivers) + chain,
                               "fk_auxiliary_controls": list(dict.fromkeys(fk_node for _, fk_node, _ in aux)),
                               "ik_auxiliary_controls": list(dict.fromkeys(ik_node for _, _, ik_node in aux if ik_node)),
                               "node_ids": {node: cmds.ls(node, uuid=True)[0] for node in identity_nodes}},
    }


def detect(selected, root):
    """Return complete graph matches for the exact selection; perform no writes."""
    candidates = []
    all_profiles = []
    selected = set(selected)
    handles = cmds.listRelatives(root, allDescendents=True, fullPath=True, type="ikHandle") or []
    for handle in handles:
        try:
            profile = _handle_profile(handle, root)
        except (RuntimeError, ValueError, TypeError):
            continue
        if not profile:
            continue
        all_profiles.append(profile)
        evidence = profile["detection_evidence"]
        limb = set(profile["result_nodes"] + profile["fk_controls"] + profile["ik_controls"]
                   + evidence["driver_nodes"] + [handle])
        controls = profile["fk_controls"] + profile["ik_controls"]
        wrappers = {node for node in selected if _control_like(node)
                    and sum(control.startswith(node + "|") for control in controls) == 1}
        if selected & (limb | wrappers) and selected <= limb | wrappers | {evidence["settings"]}:
            candidates.append((True, profile))
        elif selected == {evidence["settings"]}:
            candidates.append((False, profile))
    direct = [profile for exact, profile in candidates if exact]
    selected_profiles = direct or [profile for _, profile in candidates]
    selected_plugs = {profile["switch_attr"] for profile in selected_profiles}
    return [profile for profile in all_profiles if profile["switch_attr"] in selected_plugs]


def _switch_outputs(node, kind, attribute):
    if kind in {"reverse", "multiplyDivide"} and attribute[-1:] in _AXES:
        return ["output" + attribute[-1]]
    if kind == "setRange" and attribute[-1:] in _AXES:
        return ["outValue" + attribute[-1]]
    if kind == "plusMinusAverage":
        if attribute.startswith("input2D["):
            return ["output2D" + attribute[-1]] if attribute[-1:] in "xy" else ["output2D", "output2Dx", "output2Dy"]
        if attribute.startswith("input1D["):
            return ["output1D"]
        if attribute.startswith("input3D["):
            return ["output3D", "output3Dx", "output3Dy", "output3Dz"]
    if kind in {"unitConversion", "multDoubleLinear", "addDoubleLinear", "animCurveUU", "blendTwoAttr", "choice"}:
        return ["output"]
    if kind in {"blendColors", "clamp"}:
        return ["output", "outputR", "outputG", "outputB"]
    if kind == "condition":
        return ["outColor", "outColorR", "outColorG", "outColorB"]
    if kind == "pairBlend":
        groups = ["outRotate", "outTranslate"]
        return groups + [group + axis for group in groups for axis in _AXES]
    if kind in _CONSTRAINTS | {"aimConstraint", "scaleConstraint", "poleVectorConstraint"}:
        return [attr for group in ("constraintRotate", "constraintTranslate", "constraintScale")
                for attr in [group] + [group + axis for axis in _AXES] if cmds.objExists(node + "." + attr)]
    return None


def _is_related(node, nodes):
    return any(node == member or node.startswith(member + "|") or member.startswith(node + "|") for member in nodes)


def _related_constraint_relay(node, source, related, results):
    """Recognize a sibling control space attached to the verified limb result."""
    if cmds.nodeType(_node(source)) != "parentConstraint":
        return False
    targets = _constraint_targets(_node(source))
    if not targets or not all(target and _is_related(target, related) for target in targets):
        return False
    parent = _parents(node)
    for _ in range(3):
        if not parent:
            break
        attachment = _incoming(parent[0] + ".translateX")
        attachment_node = _node(attachment) if attachment else ""
        if attachment_node and cmds.nodeType(attachment_node) == "parentConstraint":
            owners = _constraint_targets(attachment_node)
            if len(owners) == 1 and owners[0] in results:
                return True
        parent = _parents(parent[0])
    return False


def _related_aim_relay(node, source, profile):
    """Prove a switched aim space that drives an ancestor of the result chain."""
    orient = _node(source)
    if cmds.nodeType(orient) != "orientConstraint":
        return False
    targets = _constraint_targets(orient)
    parents = _parents(node)
    if len(targets) != 2 or not all(targets) or not parents:
        return False
    target_parent = _parents(targets[0])
    if target_parent != _parents(targets[1]) or target_parent not in (parents, _parents(parents[0])):
        return False
    end = profile["ik_control"]
    for aimed, rest in (targets, targets[::-1]):
        aim_source = _incoming(aimed + ".rotateX")
        aim = _node(aim_source) if aim_source else ""
        if not aim or cmds.nodeType(aim) != "aimConstraint":
            continue
        aim_targets = _constraint_targets(aim)
        if len(aim_targets) != 1 or not aim_targets[0] or not (end == aim_targets[0] or end.startswith(aim_targets[0] + "|")):
            continue
        if _incoming(aim + ".worldUpMatrix") == rest + ".worldMatrix[0]":
            break
    else:
        return False
    drivers = cmds.listRelatives(node, allDescendents=True, fullPath=True, type="joint") or []
    if not drivers or len(drivers) > 64:
        return False
    constraints = cmds.listConnections(drivers, source=False, destination=True, type="constraint") or []
    for candidate in set(constraints):
        constraint = _node(candidate)
        if not constraint or cmds.nodeType(constraint) not in {"parentConstraint", "orientConstraint"}:
            continue
        owners = _constraint_targets(constraint)
        if len(owners) != 1 or owners[0] not in drivers:
            continue
        for ancestor in _rotation_outputs(constraint, "constraintRotate"):
            if any(result.startswith(ancestor + "|") for result in profile["result_nodes"]):
                return True
    return False


def unsafe_switch_output(profile):
    """Check known switch dependencies before any key can change the scene."""
    root = profile["rig_root"]
    evidence = profile.get("detection_evidence", {})
    handle = evidence.get("handle", "")
    related = set(profile["result_nodes"] + evidence.get("driver_nodes", [])
                  + profile["fk_controls"] + profile["ik_controls"]
                  + evidence.get("fk_auxiliary_controls", []) + evidence.get("ik_auxiliary_controls", []))
    pending = [profile["switch_attr"]]
    seen = set()
    while pending and len(seen) < 256:
        source = pending.pop()
        if source in seen:
            continue
        seen.add(source)
        for destination in _outputs(source):
            node = _node(destination)
            if not node:
                return destination
            attribute = destination.split(".", 1)[1]
            kind = cmds.nodeType(node)
            if kind in {"joint", "transform", "ikHandle", "mesh", "nurbsCurve", "nurbsSurface", "locator"}:
                if not node.startswith(root + "|") and node != root:
                    return destination
                if attribute in {"visibility", "overrideVisibility"}:
                    continue
                if kind == "ikHandle" and node != handle and not node.startswith(profile["ik_control"] + "|"):
                    return destination
                if kind != "ikHandle" and not _is_related(node, related):
                    if kind != "transform" or not (
                        _related_constraint_relay(node, source, related, profile["result_nodes"])
                        or _related_aim_relay(node, source, profile)
                    ):
                        return destination
                if kind in {"transform", "joint"}:
                    pending.append(node + "." + attribute)
                continue
            outputs = _switch_outputs(node, kind, attribute)
            if outputs is None:
                return destination
            pending.extend(node + "." + attr for attr in outputs)
    return "dependency traversal limit" if pending else ""


def snapshot(nodes):
    return [cmds.xform(node, query=True, worldSpace=True, matrix=True) for node in nodes]


def _numpy():
    try:
        import numpy
    except ImportError as error:
        raise RuntimeError("Connected matching requires NumPy in Maya's Python environment.") from error
    return numpy


def _mesh_points(shape):
    selection = om.MSelectionList()
    selection.add(shape)
    mesh = om.MFnMesh(selection.getDagPath(0))
    points = mesh.getPoints(om.MSpace.kWorld)
    return _numpy().fromiter((coordinate for point in points for coordinate in (point.x, point.y, point.z)),
                             dtype=float, count=len(points) * 3).reshape((-1, 3))


def mesh_snapshot(root, controls=()):
    """Capture evaluated mesh vertices in Maya's internal centimetres."""
    shapes = cmds.ls(root, dag=True, allPaths=True, noIntermediate=True, long=True, type="mesh") or []
    controls = set(controls)
    return {shape: _mesh_points(shape) for shape in shapes if shape.rsplit("|", 1)[0] not in controls}


def layered_channels(channels):
    layers = cmds.ls(type="animLayer") or []
    if len(layers) <= 1:
        return []
    base = cmds.animLayer(query=True, root=True)
    members = {_node(plug) for layer in layers if layer != base
               for plug in (cmds.animLayer(layer, query=True, attribute=True) or [])}
    return sorted(plug for plug in set(channels) if _node(plug) in members)


def validate_meshes(before):
    np = _numpy() if before else None
    for shape, expected in before.items():
        current = _mesh_points(shape)
        if current.shape != expected.shape:
            raise RuntimeError("The switch changed the topology of {0}.".format(shape.rsplit("|", 1)[-1]))
        if not len(current):
            continue
        delta = np.max(np.linalg.norm(current - expected, axis=1))
        if not delta <= 0.001:
            raise RuntimeError("Mesh {0} moved by {1:.5g} cm. This pose needs additional rig controls to match.".format(
                shape.rsplit("|", 1)[-1], delta))


def _position(matrix):
    return matrix[12:15]


def _distance(first, second):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _pose_errors(actual, desired):
    position = _distance(_position(actual), _position(desired))
    basis = max(abs(actual[index] - desired[index]) for index in (0, 1, 2, 4, 5, 6, 8, 9, 10))
    return position, basis


def validate_pose(nodes, desired):
    if len(nodes) != len(desired) or (nodes and not all(nodes)):
        raise RuntimeError("The driven joint mapping is incomplete. Detect the selected limb again.")
    for node, current, target in zip(nodes, snapshot(nodes), desired):
        position, basis = _pose_errors(current, target)
        rotation, target_rotation = [om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)
                                     for matrix in (current, target)]
        dot = abs(sum(getattr(rotation, axis) * getattr(target_rotation, axis) for axis in "xyzw"))
        angle = math.degrees(2 * math.acos(min(1.0, dot)))
        if not position <= 0.001 or not basis <= 0.0001 or not angle <= 0.01:
            raise RuntimeError("Driven joint {0} moved (position {1:.5g}, rotation {2:.5g} degrees, basis {3:.5g}). "
                               "Check the rig's reachable pose and unlocked match channels.".format(
                                   node.rsplit("|", 1)[-1], position, angle, basis))


def channel_groups(profile, direction):
    mode = "fk" if direction == "ik_to_fk" else "ik"
    auxiliary = [(node, ("rotate",))
                 for node in profile["detection_evidence"].get(mode + "_auxiliary_controls", [])]
    if direction == "ik_to_fk":
        return [(node, ("rotate",)) for node in profile["fk_controls"]] + auxiliary
    return [(profile["ik_control"], ("translate", "rotate")),
            (profile["pole_vector_control"], ("translate",))] + auxiliary


def _write(plug, value, frame):
    cmds.setAttr(plug, float(value))
    if not cmds.setKeyframe(plug, time=frame, value=float(value), insertBlend=False):
        raise RuntimeError("Could not key {0}.".format(plug))


def _rotation(matrix):
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def _rotation_vector(current, target):
    difference = current * target.inverse()
    sign = -1.0 if difference.w < 0 else 1.0
    vector = [difference.x * sign, difference.y * sign, difference.z * sign]
    length = math.sqrt(sum(value * value for value in vector))
    if length < 1e-12:
        return vector
    scale = 2 * math.atan2(length, abs(difference.w)) / length
    return [value * scale for value in vector]


def _seed_ik(profile, desired, writable, frame, pole_position):
    end = profile["ik_control"]
    pole = profile["pole_vector_control"]
    nodes = profile["result_nodes"]
    current_matrix = snapshot(nodes[2:3])[0]
    rotations = [end + ".rotate" + axis for axis in _AXES]
    if all(plug in writable for plug in rotations):
        control_rotation = _rotation(snapshot([end])[0]).asMatrix()
        delta = _rotation(current_matrix).asMatrix().inverse() * _rotation(desired[2]).asMatrix()
        euler = om.MTransformationMatrix(control_rotation * delta).rotation()
        euler.reorderIt(cmds.getAttr(end + ".rotateOrder"))
        cmds.xform(end, worldSpace=True, rotation=[math.degrees(value) for value in (euler.x, euler.y, euler.z)])
        for plug in rotations:
            _write(plug, cmds.getAttr(plug), frame)
    current_tip = _position(snapshot(nodes[2:3])[0])
    end_position, pole_current = [_position(matrix) for matrix in snapshot([end, pole])]
    end_target = [start + goal - tip for start, goal, tip in zip(end_position, _position(desired[2]), current_tip)]
    proposed_pole = pole_position(*[_position(matrix) for matrix in desired[:3]])
    # Preserve the guide's existing reach when possible to avoid large local key jumps.
    middle = _position(desired[1])
    distance = _distance(middle, pole_current)
    span = _distance(middle, proposed_pole)
    if span > 1e-6 and distance > 1e-6:
        proposed_pole = [mid + (value - mid) * distance / span for mid, value in zip(middle, proposed_pole)]
    for node, target in ((end, end_target), (pole, proposed_pole)):
        plugs = [node + ".translate" + axis for axis in _AXES]
        if all(plug in writable for plug in plugs):
            cmds.xform(node, worldSpace=True, translation=target)
            for plug in plugs:
                _write(plug, cmds.getAttr(plug), frame)


def match(profile, direction, desired, writable, frame, pole_position):
    """Fit the active animator channels to the sampled driven joints in the open undo chunk."""
    np = _numpy()

    nodes = profile["result_nodes"]
    plugs = [node + "." + prefix + axis for node, prefixes in channel_groups(profile, direction)
             for prefix in prefixes for axis in _AXES if node + "." + prefix + axis in writable]
    if direction == "fk_to_ik":
        _seed_ik(profile, desired, writable, frame, pole_position)
    length = max(0.01, sum(_distance(_position(a), _position(b)) for a, b in zip(desired, desired[1:])))
    target_rotations = [_rotation(matrix) for matrix in desired]

    def residual():
        actual = snapshot(nodes)
        error = np.asarray([
            _rotation_vector(_rotation(current), target_rotation)
            + [(current[index] - target[index]) / length for index in (12, 13, 14)]
            for current, target, target_rotation in zip(actual, desired, target_rotations)
        ])
        errors = [_pose_errors(current, target) for current, target in zip(actual, desired)]
        return error.ravel(), all(p <= 0.00005 and r <= 0.000005 for p, r in errors)

    # Finite differences use Maya's evaluated target branch. This respects jointOrient,
    # control offsets, constraints and parent spaces without calibrating inactive poses.
    for _ in range(28):
        error, matched = residual()
        if matched or not plugs:
            break
        values = [cmds.getAttr(plug) for plug in plugs]
        near = np.linalg.norm(error) < 0.01
        steps = [0.02 if ".rotate" in plug else max(0.0001, length * 0.00015) for plug in plugs]
        derivatives = []
        for plug, value, step in zip(plugs, values, steps):
            _write(plug, value + step, frame)
            moved, _ = residual()
            if near:
                _write(plug, value - step, frame)
                opposite, _ = residual()
                derivatives.append((moved - opposite) / (2 * step))
            else:
                derivatives.append((moved - error) / step)
            _write(plug, value, frame)
        jacobian = np.asarray(derivatives).T
        limits = np.asarray([35.0 if ".rotate" in plug else length * 0.4 for plug in plugs])
        scaled = jacobian * limits
        # Mild damping keeps redundant channels, including pole distance, close to their current values.
        damping = 0.00002 if near else 0.0002
        delta = np.linalg.lstsq(np.vstack((scaled, np.eye(len(plugs)) * damping)),
                                np.concatenate((-error, np.zeros(len(plugs)))), rcond=None)[0] * limits
        delta /= max(1.0, np.max(np.abs(delta / limits)))
        for factor in (1.0, 0.5, 0.25, 0.1):
            for plug, value, adjustment in zip(plugs, values, delta):
                _write(plug, value + adjustment * factor, frame)
            moved, _ = residual()
            if np.linalg.norm(moved) < np.linalg.norm(error):
                break
        else:
            for plug, value in zip(plugs, values):
                _write(plug, value, frame)
            break
    validate_pose(nodes, desired)
