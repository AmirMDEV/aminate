"""Calibrated, one-owner-per-control mocap composition on generated rigs.

All source samples are cached before target edits. Output is an independent
native override animation layer; imported FBX nodes are never connected to it.
"""
from __future__ import absolute_import, division, print_function
import json
import math
import uuid
import aminate_skeleton_map as mapping
import maya_control_rig_builder as rigging

cmds = rigging.cmds
om = rigging.om
META = "aminateMocapData"


def fps():
    return om.MTime(1, om.MTime.kSeconds).asUnits(om.MTime.uiUnit())


def rotation(matrix):
    value=om.MMatrix(matrix)
    if value.det4x4()<=1e-10:raise ValueError("Retargeting requires non-mirrored, non-zero transform scale.")
    transform=om.MTransformationMatrix(value)
    if any(abs(x)>1e-5 for x in transform.shear(om.MSpace.kTransform)):
        raise ValueError("Remove shear from the source and target transform spaces before retargeting.")
    return transform.rotation(asQuaternion=True).asMatrix()


def relative(child, parent):
    return rigging.multiply(child, rigging.inverse(parent))


def calibrated_rotation(source_reference, source_current, target_reference):
    """Row-vector local matrices; calibration frame reproduces target rest."""
    return rotation(target_reference) * rotation(source_reference).inverse() * rotation(source_current)


def parent_world(n):
    parent = cmds.listRelatives(n, parent=True, fullPath=True) or []
    return rigging.world(parent[0]) if parent else rigging.IDENTITY


def make_route(rig, module_id, source_joints, source_reference, source_start,
               target_start, source_end, speed=1., offset_seconds=0., translate=False,
               translation_scale=1., label="Performer"):
    data = rigging.rig_data(rig)
    module = next((m for m in data["modules"] if m["id"] == module_id), None)
    if not module and module_id.startswith("joint:") and module_id[6:] in data["controls"]:
        module={"joints":[module_id[6:]]}
    if not module:
        raise ValueError("Choose a target limb group or body joint.")
    if len(source_joints) != len(module["joints"]):
        raise ValueError("Select the same number of source joints as the chosen target group.")
    sources = [rigging.uid(rigging.node(n)) for n in source_joints]
    route = {"version":1, "id":uuid.uuid4().hex, "label":label, "module":module_id,
             "sources":sources, "targets":list(module["joints"]),
             "source_reference":float(source_reference), "source_start":float(source_start),
             "source_end":float(source_end), "target_start":float(target_start),
             "speed":float(speed), "offset_seconds":float(offset_seconds),
             "translate":bool(translate), "translation_scale":float(translation_scale)}
    mapping.validate_routes([route])
    return route


def validate(rig, routes, start, end, dense=True, key_times=None):
    data = rigging.rig_data(rig)
    mapping.validate_routes(routes)
    times = rigging.frames(start,end,key_times,dense)
    if not times:
        raise ValueError("No requested key times in the bake range.")
    target_ids = set(data["controls"])
    owned = set(data["owned"]) | target_ids
    for route in routes:
        if not set(route["targets"]) <= target_ids:
            raise ValueError("Route targets must belong to the selected generated rig.")
        if set(route["sources"]) & owned:
            raise ValueError("Use an independent performer skeleton as the source.")
        if float(route.get("weight",1.)) != 1.:
            raise ValueError("This compositor uses exclusive limb ownership; use animation layers to blend takes.")
        for n in route["sources"]:
            if cmds.nodeType(rigging.node(n)) != "joint":raise ValueError("Mocap sources must be joints.")
        if not math.isfinite(float(route.get("translation_scale",1.))) or float(route.get("translation_scale",1.)) <= 0:
            raise ValueError("Translation scale must be finite and positive.")
        first, last = mapping.route_time(times[0],route,fps()),mapping.route_time(times[-1],route,fps())
        if first < float(route["source_start"])-1e-6 or last > float(route["source_end"])+1e-6:
            raise ValueError(route.get("label","Performer")+": requested timing extends outside the source clip.")
        if not math.isfinite(float(route["source_reference"])):
            raise ValueError("Choose a finite reference frame.")
        for source,following in zip(route["sources"],route["sources"][1:]):
            a,b=rigging.node(source),rigging.node(following)
            if not b.startswith(a+"|"):raise ValueError("Source joints must form an ordered chain.")
        for target in route["targets"]:
            control=rigging.node(data["controls"][target]["control"])
            attrs=("rotateX","rotateY","rotateZ")+(("translateX","translateY","translateZ") if route.get("translate") else ())
            for attr in attrs:
                if cmds.getAttr(control+"."+attr,lock=True):raise ValueError("Unlock target channel: "+control+"."+attr)
    return data,times


def bake(rig, routes, start, end, dense=True, key_times=None, preview=False):
    data,times=validate(rig,routes,start,end,dense,key_times)
    cache={}
    route_for={target:route for route in routes for target in route["targets"]}
    ordered=sorted(route_for,key=lambda n:data["controls"][n]["depth"])
    owner=rigging.Builder()
    with rigging.transaction("Aminate Compose Performer Mocap"):
        # Local anatomical motion excludes source parent/root locomotion. Each
        # selected bone is measured relative to its immediate skeleton parent.
        for route in routes:
            cmds.currentTime(route["source_reference"])
            refs={s:relative(rigging.world(rigging.node(s)),parent_world(rigging.node(s))) for s in route["sources"]}
            for t in times:
                cmds.currentTime(mapping.route_time(t,route,fps()))
                for source,target in zip(route["sources"],route["targets"]):
                    src=rigging.node(source)
                    cache[t,target]=(refs[source],relative(rigging.world(src),parent_world(src)))
        layer=owner.own(cmds.animLayer("Aminate_Mocap_"+uuid.uuid4().hex[:8],override=True,passthrough=True))
        for target in ordered:
            ctrl=rigging.node(data["controls"][target]["control"])
            attrs=["rotate"+a for a in "XYZ"]+(["translate"+a for a in "XYZ"] if route_for[target].get("translate") else [])
            for attr in attrs:owner.layer_attribute(layer,ctrl+"."+attr)
        switches=[]
        for module in data["modules"]:
            if module.get("ik") and set(module["joints"]) & set(ordered):
                if not set(module["joints"]) <= set(ordered):
                    raise ValueError("Route all three primary joints of an IK limb together.")
                plug=rigging.node(module["settings"])+".ikFk"
                owner.layer_attribute(layer,plug);switches.append(plug)
        # The layer contributes only within the requested range.
        for t,value in ((times[0]-.001,0),(times[0],1),(times[-1],1),(times[-1]+.001,0)):
            owner.keyframe(layer+".weight",time=t,value=value,outTangentType="step")
        previous={}
        for t in times:
            cmds.currentTime(t)
            for plug in switches:owner.keyframe(plug,time=t,value=0,animLayer=layer,noResolve=True,outTangentType="step")
            cmds.currentTime(t,update=True)
            for target in ordered:
                rec=data["controls"][target];desc=data["description"]["nodes"]
                parent_id=rec["parent"]
                target_ref_parent=desc[parent_id]["world"] if parent_id in desc else data.get("external_parents",{}).get(parent_id,rigging.IDENTITY)
                target_ref=relative(rec["rest"],target_ref_parent)
                sref,scur=cache[t,target]
                desired=om.MTransformationMatrix(calibrated_rotation(sref,scur,target_ref))
                position=target_ref[12:15]
                route=route_for[target]
                if route.get("translate"):
                    position=[p+(b-a)*route.get("translation_scale",1.) for p,a,b in zip(position,sref[12:15],scur[12:15])]
                desired.setTranslation(om.MVector(*position),om.MSpace.kTransform)
                parent_current=parent_world(rigging.node(target))
                wanted=rigging.multiply(desired.asMatrix(),parent_current)
                local=om.MTransformationMatrix(om.MMatrix(relative(wanted,rigging.world(rigging.node(rec["zero"])))))
                rotation_value=local.rotation(asQuaternion=False)
                ctrl=rigging.node(rec["control"])
                rotation_value.reorderIt(cmds.getAttr(ctrl+".rotateOrder"))
                if target in previous:rotation_value=rotation_value.closestSolution(previous[target])
                previous[target]=rotation_value
                values={"rotate"+a:math.degrees(v) for a,v in zip("XYZ",rotation_value)}
                if route.get("translate"):values.update({"translate"+a:v for a,v in zip("XYZ",local.translation(om.MSpace.kTransform))})
                for attr,value in values.items():
                    owner.keyframe(ctrl+"."+attr,time=t,value=value,animLayer=layer,noResolve=True,inTangentType="linear",outTangentType="linear")
                cmds.currentTime(t,update=True)
        payload={"version":1,"rig":rigging.uid(rig),"routes":routes,"times":times,"preview":bool(preview),
                 "sampling":"every frame" if dense else "requested keys", "scene_fps":fps()}
        rigging.string_attr(layer,META,json.dumps(payload))
        data["owned"]=list(set(data["owned"]+owner.owned))
        data.setdefault("mocap_layers",[]).append(rigging.uid(layer))
        rigging.string_attr(rig,rigging.META,json.dumps(data))
    return layer


def finish_preview(layer):
    if not cmds.attributeQuery(META,node=layer,exists=True):raise ValueError("Select an Aminate mocap preview layer.")
    with rigging.transaction("Aminate Keep Mocap Preview"):
        data=json.loads(cmds.getAttr(layer+"."+META));data["preview"]=False
        rigging.string_attr(layer,META,json.dumps(data))
    return layer


def discard_preview(layer):
    if not cmds.objExists(layer) or not cmds.attributeQuery(META,node=layer,exists=True):raise ValueError("No preview to discard.")
    if not json.loads(cmds.getAttr(layer+"."+META)).get("preview"):raise ValueError("Only an uncommitted preview can be discarded here.")
    with rigging.transaction("Aminate Discard Mocap Preview"):cmds.delete(layer)


def save_routes(rig,routes):
    if routes:mapping.validate_routes(routes)
    with rigging.transaction("Aminate Save Performer Routes"):
        rigging.string_attr(rig,"aminatePerformerRoutes",json.dumps({"version":1,"routes":routes}))


def load_routes(rig):
    if not cmds.attributeQuery("aminatePerformerRoutes",node=rig,exists=True):return []
    data=json.loads(cmds.getAttr(rig+".aminatePerformerRoutes"))
    if data.get("version")!=1:raise ValueError("Unsupported route version.")
    if data["routes"]:mapping.validate_routes(data["routes"])
    return data["routes"]
