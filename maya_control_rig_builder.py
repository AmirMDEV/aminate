"""Scene-backed FK/IK control rig generation for imported joint hierarchies.

Uses Maya-native nodes. Original animation inputs are retained for restoration;
generated rigs use owned controls, never destructive joint reorientation.
"""
from __future__ import absolute_import, division, print_function
import contextlib
import json
import math
import os
import uuid
import aminate_skeleton_map as mapping

try:
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
except ImportError:
    cmds = om = None

TRS = tuple(a + b for a in ("translate", "rotate", "scale") for b in "XYZ")
IDENTITY = [1.,0,0,0,0,1.,0,0,0,0,1.,0,0,0,0,1.]
META = "aminateControlRigData"


def uid(node):
    return cmds.ls(node, uuid=True)[0]


def node(identity):
    values = cmds.ls(identity, long=True) or []
    if len(values) != 1:
        raise ValueError("Missing or ambiguous scene object: " + str(identity))
    return values[0]


def world(n):
    return list(cmds.xform(n, query=True, worldSpace=True, matrix=True))


def inverse(value):
    m = om.MMatrix(value)
    if abs(m.det4x4()) < 1e-10:
        raise ValueError("Zero or near-zero scale cannot be solved.")
    return m.inverse()


def multiply(*values):
    result = om.MMatrix()
    for value in values:
        result *= om.MMatrix(value)
    return list(result)


def close(a, b, tolerance=1e-5):
    return all(abs(x-y) <= tolerance*max(1,abs(x),abs(y)) for x,y in zip(a,b))


def frames(start, end, keys=None, dense=True):
    start, end = float(start), float(end)
    if not all(math.isfinite(x) for x in (start,end)) or end < start:
        raise ValueError("Choose a finite ordered frame range.")
    result = {float(t) for t in keys or [] if math.isfinite(float(t)) and start <= float(t) <= end}
    if dense:
        result.update((start,end))
        result.update(range(int(math.ceil(start)), int(math.floor(end))+1))
    return sorted(result)


@contextlib.contextmanager
def transaction(label):
    if not cmds.undoInfo(query=True,state=True):
        raise RuntimeError("Enable Maya Undo before editing a rig.")
    original_time = cmds.currentTime(query=True)
    selection = cmds.ls(selection=True,long=True) or []
    auto = cmds.autoKeyframe(query=True,state=True)
    cmds.undoInfo(openChunk=True,chunkName=label)
    failed = False
    try:
        cmds.autoKeyframe(state=False)
        yield
    except Exception:
        failed = True
        raise
    finally:
        try:
            cmds.currentTime(original_time)
            cmds.autoKeyframe(state=auto)
            existing = [n for n in selection if cmds.objExists(n)]
            cmds.select(existing,replace=True) if existing else cmds.select(clear=True)
        finally:
            cmds.undoInfo(closeChunk=True)
        if failed and cmds.undoInfo(query=True,undoName=True) == label:
            cmds.undo()


def string_attr(n, attr, value):
    if not cmds.attributeQuery(attr,node=n,exists=True):
        cmds.addAttr(n,longName=attr,dataType="string")
    cmds.setAttr(n+"."+attr,value,type="string")


def scan(root, left_axis=None):
    root = node(root)
    joints = ([root] if cmds.nodeType(root)=="joint" else []) + (cmds.listRelatives(root,allDescendents=True,fullPath=True,type="joint") or [])
    joints = sorted(set(joints),key=lambda n:(n.count("|"),n))
    records = {}
    for n in joints:
        if len(cmds.ls(n,long=True,allPaths=True) or []) != 1:
            raise ValueError("Instanced skeletons are not supported.")
        parent = cmds.listRelatives(n,parent=True,fullPath=True) or []
        matrix = world(n)
        inverse(matrix)
        relative_path = n[len(root):].strip("|") if n!=root else n.rsplit("|",1)[-1]
        relative_path = "|".join(part.rsplit(":",1)[-1] for part in relative_path.split("|"))
        records[uid(n)] = {"name":n.rsplit("|",1)[-1],"path":relative_path,
                          "parent":uid(parent[0]) if parent else None,"position":matrix[12:15],
                          "world":matrix,"rotate_order":cmds.getAttr(n+".rotateOrder"),
                          "joint_orient":list(cmds.getAttr(n+".jointOrient")[0]),"depth":n.count("|")}
    result = {"version":1,"root":uid(root),"nodes":records,"reference_frame":float(cmds.currentTime(query=True)),
              "left_axis":left_axis,"origin":world(root)[12:15],"units":cmds.currentUnit(query=True,linear=True)}
    mapping.validate_description(result)
    return result


def rigs():
    return [n for n in cmds.ls(type="network") or [] if cmds.attributeQuery(META,node=n,exists=True)]


def rig_data(rig):
    if rig not in rigs():
        raise ValueError("Select a generated Aminate rig.")
    data=json.loads(cmds.getAttr(rig+"."+META))
    if data.get("version")!=1:raise ValueError("Unsupported control rig version; use the Aminate version that created it.")
    return data


class Builder(object):
    def __init__(self):
        self.owned = []
        self._node_types = None

    def own(self, n):
        self.owned.append(uid(n))
        return n

    def create(self, kind, name, **kwargs):
        if self._node_types is None:self._node_types=set(cmds.allNodeTypes() or [])
        if kind not in self._node_types:
            raise ValueError("Required Maya node type is unavailable: "+kind)
        return self.own(cmds.createNode(kind,name=name,**kwargs))

    def _identities(self, nodes):
        return {uid(n) for n in nodes or []}

    def _own_new(self, before, nodes):
        # Callers supply only nodes returned by an exact command/target query.
        # A scene-wide difference would also claim unrelated callback output.
        for n in nodes or []:
            if uid(n) not in before:self.own(n)

    def connect(self, source, destination, **kwargs):
        before=self._identities(cmds.listConnections(source,source=False,destination=True) or [])
        result=cmds.connectAttr(source,destination,**kwargs)
        connected=cmds.connectionInfo(destination,sourceFromDestination=True)
        if connected:
            converter=connected.split(".",1)[0]
            if cmds.nodeType(converter) in ("unitConversion","unitToTimeConversion","timeToUnitConversion"):
                self._own_new(before,[converter])
        return result

    def _animation_curves(self, plug):
        # An explicit plug avoids keyframe's active-key/selection query mode.
        return cmds.listConnections(plug,source=True,destination=False,
                                    type="animCurve",skipConversionNodes=True) or []

    def keyframe(self, target, **kwargs):
        attributes=kwargs.get("attribute")
        if isinstance(attributes,str):attributes=[attributes]
        plugs=[target] if "." in target else [target+"."+attr for attr in
                (attributes if attributes is not None else (cmds.listAttr(target,keyable=True) or []))]
        def curves():
            result=[]
            if kwargs.get("animLayer"):
                for plug in plugs:
                    curve=cmds.animLayer(kwargs["animLayer"],query=True,findCurveForPlug=plug)
                    result.extend([curve] if isinstance(curve,str) else (curve or []))
            else:
                for plug in plugs:result.extend(self._animation_curves(plug))
            return result
        before=self._identities(curves())
        result=cmds.setKeyframe(target,**kwargs)
        self._own_new(before,curves())
        return result

    def layer_attribute(self, layer, plug):
        def related():
            result=[]
            for flag in ("blendNodes","animCurves","baseAnimCurves"):
                result.extend(cmds.animLayer(layer,query=True,**{flag:True}) or [])
            return result
        before=self._identities(related()+self._animation_curves(plug))
        cmds.animLayer(layer,edit=True,attribute=plug)
        self._own_new(before,related())

    def cluster(self, curve, component, name):
        def geometry_nodes():
            allowed=("nurbsCurve","cluster","groupParts","groupId","tweak")
            return [n for n in cmds.listHistory(curve) or [] if cmds.nodeType(n) in allowed]
        before=self._identities(geometry_nodes())
        deformer,handle=cmds.cluster(component,relative=True,name=name)
        self.own(deformer);self.own(handle)
        self._own_new(before,geometry_nodes())
        for shape in cmds.listRelatives(handle,shapes=True,fullPath=True) or []:self.own(shape)
        # The newly returned deformer has its own membership set. Never walk
        # arbitrary sets or the scene's shared solver/animation infrastructure.
        for group in cmds.listConnections(deformer+".message",source=False,destination=True,type="objectSet") or []:
            self.own(group)
        return deformer,handle

    def control(self, name, matrix, radius, parent, color=17):
        zero = self.create("transform",name+"_ZERO",parent=parent)
        cmds.xform(zero,worldSpace=True,matrix=matrix)
        ctrl = self.own(cmds.circle(name=name+"_CTRL",normal=(1,0,0),radius=radius,constructionHistory=False)[0])
        ctrl = cmds.parent(ctrl,zero,relative=True)[0]
        for shape in cmds.listRelatives(ctrl,shapes=True,fullPath=True) or []:
            self.own(shape)
            cmds.setAttr(shape+".overrideEnabled",True)
            cmds.setAttr(shape+".overrideColor",color)
        return ctrl,zero

    def follow(self, source, target):
        for n in cmds.parentConstraint(source,target,maintainOffset=True):self.own(n)
        for n in cmds.scaleConstraint(source,target,maintainOffset=True):self.own(n)

    def _snapshot_inputs(self, target):
        result = {"target":uid(target),"attrs":{}}
        if cmds.referenceQuery(target,isNodeReferenced=True):
            raise ValueError("Build on a local imported skeleton; referenced skeletons need an editable export copy.")
        for attr in ("offsetParentMatrix","jointOrient","rotateAxis","rotateOrder","shear"):
            if cmds.listConnections(target+"."+attr,source=True,destination=False):
                raise ValueError("Animated or driven structural joint attributes are not supported: "+target+"."+attr)
        for attr in TRS:
            plug = target+"."+attr
            if cmds.getAttr(plug,lock=True):raise ValueError("Unlock target channel: "+plug)
            src = cmds.connectionInfo(plug,sourceFromDestination=True)
            if src and not cmds.nodeType(src.split(".")[0]).startswith("animCurveT"):
                raise ValueError("Existing rig drivers are not replaced: "+plug)
            result["attrs"][attr] = {"value":cmds.getAttr(plug),"input":({"node":uid(src.split(".")[0]),"attr":src.split(".",1)[1]} if src else None)}
        return result

    def build(self, description, roles, modules, preserve_animation=False, start=None, end=None):
        records = mapping.validate_description(description)
        mapping.validate_modules(modules,records)
        if abs(cmds.currentTime(query=True)-description["reference_frame"])>1e-6:
            raise ValueError("Return to the scanned reference frame, or scan again before building.")
        ordered = sorted(records,key=lambda n:records[n]["depth"])
        for rig in rigs():
            if set(rig_data(rig)["controls"]) & set(records):raise ValueError("This skeleton already belongs to an Aminate rig.")
        originals = [self._snapshot_inputs(node(n)) for n in ordered]
        has_animation = any(v["input"] for r in originals for v in r["attrs"].values())
        if has_animation and not preserve_animation:
            raise ValueError("Skeleton has animation. Enable Preserve animation and choose its range.")
        for n in ordered:
            if not close(world(node(n)),records[n]["world"]):raise ValueError("Skeleton changed after scan; scan again.")
        # An RP solver needs the two primary segments, without intermediary
        # deform/twist joints. Ineligible chains retain full FK controls.
        warnings = []
        modules = [dict(m) for m in modules]
        for m in modules:
            chain=m["joints"]
            if m.get("ik") and any(records[b]["parent"]!=a for a,b in zip(chain,chain[1:])):
                m["ik"]=False;warnings.append(m["id"]+": intermediary joints; generated FK only. Dedicated twist IK is pending.")
        self.owned=[]
        captured=[]
        with transaction("Aminate Build Control Rig"):
            if preserve_animation:
                times=frames(start,end,cmds.keyframe([node(n) for n in ordered],query=True,timeChange=True),True)
                for t in times:
                    cmds.currentTime(t);captured.append((t,{n:world(node(n)) for n in ordered}))
                cmds.currentTime(description["reference_frame"])
            for rec in originals:
                target=node(rec["target"])
                for attr,value in rec["attrs"].items():
                    if value["input"]:
                        src=value["input"];cmds.disconnectAttr(node(src["node"])+"."+src["attr"],target+"."+attr)
            prefix="AminateRig_"+uuid.uuid4().hex[:8]
            group=self.create("transform",prefix)
            global_ctrl,zero=self.control(prefix+"_Global",IDENTITY,10,group)
            controls={}
            for n in ordered:
                rec=records[n];target=node(n)
                parent=cmds.listRelatives(target,parent=True,fullPath=True) or []
                lengths=[math.dist(rec["position"],r["position"]) for r in records.values() if r["parent"]==n]
                radius=max(.2,min(max(lengths or [2])*.2,10))
                evidence=mapping.name_evidence(rec["name"])
                ctrl,offset=self.control(prefix+"_"+re_safe(rec["name"]),rec["world"],radius,global_ctrl,6 if evidence["side"]=="left" else 13 if evidence["side"]=="right" else 17)
                if parent and uid(parent[0]) in records:self.follow(parent[0],offset)
                elif parent:
                    # External animated parents must not become implicit sources.
                    ancestor=parent[0]
                    while ancestor:
                        if any(cmds.listConnections(ancestor+"."+a,source=True,destination=False) for a in TRS+("offsetParentMatrix",)):
                            raise ValueError("Choose a skeleton root below static external ancestors.")
                        ancestors=cmds.listRelatives(ancestor,parent=True,fullPath=True) or []
                        ancestor=ancestors[0] if ancestors else None
                constraint=self.own(cmds.parentConstraint(ctrl,target,maintainOffset=True)[0])
                scale_constraint=self.own(cmds.scaleConstraint(ctrl,target,maintainOffset=True)[0])
                controls[n]={"control":uid(ctrl),"zero":uid(offset),"constraint":uid(constraint),"scale_constraint":uid(scale_constraint),"rest":rec["world"],"parent":rec["parent"],"depth":rec["depth"]}
            for m in modules:
                if m.get("ik"):self._limb(m,records,controls,global_ctrl,prefix)
            for n in ordered:
                if not close(world(node(n)),records[n]["world"]):raise RuntimeError("Build altered the reference pose of "+node(n)+". Rolled back.")
            for t,poses in captured:
                cmds.currentTime(t)
                for n in ordered:
                    ctrl=node(controls[n]["control"])
                    cmds.xform(ctrl,worldSpace=True,matrix=poses[n]);self.keyframe(ctrl,attribute=TRS,time=t)
                if any(not close(world(node(n)),poses[n]) for n in ordered):raise RuntimeError("Existing animation transfer failed; build rolled back.")
            meta=self.create("network",prefix+"_Metadata")
            data={"version":1,"id":prefix,"group":uid(group),"global":uid(global_ctrl),"controls":controls,"roles":roles,"modules":modules,
                  "external_parents":{records[n]["parent"]:world(node(records[n]["parent"])) for n in ordered if records[n]["parent"] and records[n]["parent"] not in records},
                  "originals":originals,"reference_frame":description["reference_frame"],"description":description,"warnings":warnings}
            data["owned"]=list(set(self.owned))
            string_attr(meta,META,json.dumps(data))
        return meta

    def _limb(self, module, records, controls, global_ctrl, prefix):
        ids=module["joints"];name=prefix+"_"+module["id"]
        setup=self.create("transform",name+"_IK",parent=global_ctrl)
        parent=records[ids[0]]["parent"]
        if parent in records:self.follow(node(parent),setup)
        chain=[]
        for index,n in enumerate(ids):
            j=self.create("joint",name+"_solve"+str(index),parent=chain[-1] if chain else setup)
            cmds.xform(j,worldSpace=True,translation=records[n]["position"]);chain.append(j)
        # Orient generated solver joints only. The imported bind joints retain
        # their original jointOrient, scale and hierarchy.
        cmds.joint(chain[0],edit=True,orientJoint="xyz",secondaryAxisOrient="yup",children=True,zeroScaleOrient=True)
        end,zero=self.control(name+"_IKTarget",records[ids[2]]["world"],2,global_ctrl)
        pv,pvzero=self.control(name+"_Pole",IDENTITY,1,global_ctrl)
        position=pole_position(*[records[n]["position"] for n in ids])
        cmds.xform(pvzero,worldSpace=True,translation=position)
        handle,effector=cmds.ikHandle(name=name+"_Handle",startJoint=chain[0],endEffector=chain[-1],solver="ikRPsolver")
        self.own(handle);self.own(effector)
        cmds.parent(handle,end)
        for c in cmds.poleVectorConstraint(pv,handle):self.own(c)
        for c in cmds.orientConstraint(end,chain[-1],maintainOffset=True):self.own(c)
        settings,settingszero=self.control(name+"_Settings",records[ids[2]]["world"],.6,global_ctrl)
        cmds.addAttr(settings,longName="ikFk",attributeType="double",minValue=0,maxValue=1,defaultValue=0,keyable=True)
        reverse=self.create("reverse",name+"_FKWeight")
        self.connect(settings+".ikFk",reverse+".inputX")
        for source,n in zip(chain,ids):
            constraint=node(controls[n]["constraint"])
            cmds.parentConstraint(source,node(n),maintainOffset=True,weight=0)
            aliases=cmds.parentConstraint(constraint,query=True,weightAliasList=True)
            self.connect(reverse+".outputX",constraint+"."+aliases[0])
            self.connect(settings+".ikFk",constraint+"."+aliases[1])
        module.update({"settings":uid(settings),"ik_control":uid(end),"ik_zero":uid(zero),"pole":uid(pv),"pole_zero":uid(pvzero),"solver":[uid(n) for n in chain],
                       "ik_offset":multiply(world(end),inverse(world(node(ids[2])))),"preferred_pole":position})
        cmds.setAttr(setup+".visibility",False)


def re_safe(name):
    import re
    return re.sub(r"[^A-Za-z0-9_]","_",name.rsplit(":",1)[-1])


def pole_position(start,middle,end,preferred=None):
    a,b,c=(om.MVector(*p) for p in (start,middle,end))
    line=c-a
    if line.length()<1e-8:raise ValueError("Limb start and end overlap.")
    projection=a+line*((b-a)*line/(line*line))
    bend=b-projection
    if bend.length()<1e-6:
        bend=om.MVector(*(preferred or [0,0,1]))
        bend-=line.normal()*(bend*line.normal())
        if bend.length()<1e-6:bend=line^om.MVector(0,1,0)
        if bend.length()<1e-6:bend=line^om.MVector(1,0,0)
    return list(b+bend.normal()*max((b-a).length()+(c-b).length(),.01))


def match_limb(rig,module_id,to_ik,key=True):
    data=rig_data(rig)
    owner=Builder()
    module=next(m for m in data["modules"] if m["id"]==module_id)
    if not module.get("ik"):raise ValueError("This limb was built with FK controls only.")
    if module.get("kind")=="spine":
        import maya_control_rig_modules
        return maya_control_rig_modules.match_spine(rig,module_id,to_ik)
    targets=[node(n) for n in module["joints"]]
    before=[world(n) for n in targets]
    with transaction("Aminate Match FK IK"):
        changed=[]
        if to_ik:
            settings=node(module["settings"])
            if module.get("soft_ik"):cmds.setAttr(settings+".softness",0)
            if module.get("stretch"):
                lengths=[math.dist(a[12:15],b[12:15]) for a,b in zip(before,before[1:])]
                parent=cmds.listRelatives(node(module["solver"][0]),parent=True,fullPath=True)[0]
                scale=om.MTransformationMatrix(om.MMatrix(world(parent))).scale(om.MSpace.kTransform)
                if max(scale)-min(scale)>1e-5:raise ValueError("IK matching requires uniform solver-parent scale.")
                for attr,value,rest in zip(("upperLength","lowerLength"),lengths,module["stretch"]["rest_lengths"]):cmds.setAttr(settings+"."+attr,value/(abs(rest)*abs(scale[0])))
                cmds.setAttr(settings+".stretch",0)
            if module.get("foot_roll"):
                for attr in ("heelRoll","bankOut","bankIn","toeRoll","ballRoll"):cmds.setAttr(node(module["ik_control"])+"."+attr,0)
            changed.append(settings)
            ctrl=node(module["ik_control"])
            cmds.xform(ctrl,worldSpace=True,matrix=multiply(module["ik_offset"],before[-1]));changed.append(ctrl)
            pv=node(module["pole"])
            old=world(pv)[12:15]
            preferred=[x-y for x,y in zip(old,before[1][12:15])]
            cmds.xform(pv,worldSpace=True,translation=pole_position(*[m[12:15] for m in before],preferred=preferred));changed.append(pv)
        else:
            for ident,pose in zip(module["joints"],before):
                ctrl=node(data["controls"][ident]["control"])
                cmds.xform(ctrl,worldSpace=True,matrix=pose);changed.append(ctrl)
        switch=node(module["settings"])+".ikFk"
        cmds.setAttr(switch,1 if to_ik else 0)
        if key:
            for ctrl in changed:owner.keyframe(ctrl,attribute=list(TRS)+(cmds.listAttr(ctrl,userDefined=True,keyable=True) or []))
            owner.keyframe(switch);cmds.keyTangent(switch,edit=True,time=(cmds.currentTime(query=True),cmds.currentTime(query=True)),outTangentType="step")
        if any(not close(world(n),m) for n,m in zip(targets,before)):
            raise RuntimeError("FK/IK destination cannot represent this pose within tolerance. Switch rolled back.")
        data["owned"]=list(set(data["owned"]+owner.owned))
        string_attr(rig,META,json.dumps(data))


def reset_controls(rig,selected_only=False):
    data=rig_data(rig)
    controls=[node(r["control"]) for r in data["controls"].values()]
    if selected_only:
        selection=set(cmds.ls(selection=True,long=True) or []);controls=[c for c in controls if c in selection]
    with transaction("Aminate Reset Controls"):
        for ctrl in controls:
            for attr in TRS:cmds.setAttr(ctrl+"."+attr,1 if attr.startswith("scale") else 0)


def pose_controls(data):
    result={"fk:"+data["description"]["nodes"][n]["path"]:r["control"] for n,r in data["controls"].items()}
    result["global"]=data["global"]
    for module in data["modules"]:
        for key in ("ik_control","pole","settings"):
            if module.get(key):result[module["id"]+":"+key]=module[key]
        for index,ident in enumerate(module.get("spine_controls",[])):result[module["id"]+":spine:"+str(index)]=ident
    for index,module in enumerate(data.get("aim_modules",[])):result["aim:"+data["description"]["nodes"][module["joint"]]["path"]]=module["control"]
    for index,module in enumerate(data.get("face_modules",[])):result["face:"+str(index)]=module["control"]
    return result


def save_pose(rig,path):
    data=rig_data(rig);pose={}
    for label,ident in pose_controls(data).items():
        ctrl=node(ident);values={}
        for attr in list(TRS)+(cmds.listAttr(ctrl,userDefined=True,keyable=True) or []):
            value=cmds.getAttr(ctrl+"."+attr)
            if isinstance(value,(int,float)) and math.isfinite(value):values[attr]=value
        pose[label]=values
    with open(path,"w") as stream:json.dump({"version":2,"pose":pose},stream,indent=2)


def load_pose(rig,path,key=True):
    data=rig_data(rig)
    owner=Builder()
    with open(path) as stream:pose=json.load(stream)
    if pose.get("version")!=2:raise ValueError("Unsupported pose version.")
    lookup=pose_controls(data)
    if set(pose["pose"])-set(lookup):raise ValueError("Pose contains controls missing from this rig.")
    with transaction("Aminate Load Pose"):
        for label,values in pose["pose"].items():
            ctrl=node(lookup[label])
            allowed=set(TRS)|set(cmds.listAttr(ctrl,userDefined=True,keyable=True) or [])
            for attr,value in values.items():
                if attr not in allowed or not math.isfinite(float(value)):raise ValueError("Invalid pose channel.")
                cmds.setAttr(ctrl+"."+attr,value)
                if key:owner.keyframe(ctrl+"."+attr)
        data["owned"]=list(set(data["owned"]+owner.owned))
        string_attr(rig,META,json.dumps(data))


def remove(rig):
    data=rig_data(rig)
    owned=set(data["owned"])
    existing=[node(u) for u in owned if cmds.ls(u)]
    for layer_id in data.get("mocap_layers",[]):
        if not cmds.ls(layer_id):continue
        layer=node(layer_id)
        for plug in cmds.animLayer(layer,query=True,attribute=True) or []:
            if uid(plug.split(".")[0]) not in owned:raise ValueError("A mocap layer contains animation for another object; separate that animation before removing this rig.")
    for n in existing:
        if cmds.nodeType(n) in ("transform","joint"):
            for child in cmds.listRelatives(n,children=True,fullPath=True) or []:
                if uid(child) not in owned:raise ValueError("Move non-Aminate children out of the generated rig before removal.")
    for rec in data["originals"]:
        target=node(rec["target"])
        for attr in TRS:
            src=cmds.connectionInfo(target+"."+attr,sourceFromDestination=True)
            if src and uid(src.split(".")[0]) not in owned:
                raise ValueError("An output connection changed; removal would overwrite an external edit.")
    for module in data.get("face_modules",[]):
        for rec in module["weights"]:
            plug=node(rec["node"])+"."+rec["attr"]
            src=cmds.connectionInfo(plug,sourceFromDestination=True)
            if src and uid(src.split(".")[0]) not in owned:raise ValueError("A face weight driver changed; removal would overwrite an external edit.")
    with transaction("Aminate Remove Control Rig"):
        for module in data.get("face_modules",[]):
            for rec in module["weights"]:
                plug=node(rec["node"])+"."+rec["attr"]
                src=cmds.connectionInfo(plug,sourceFromDestination=True)
                if src:cmds.disconnectAttr(src,plug)
                cmds.setAttr(plug,rec["value"])
        for rec in data["originals"]:
            target=node(rec["target"])
            for attr,saved in rec["attrs"].items():
                plug=target+"."+attr;src=cmds.connectionInfo(plug,sourceFromDestination=True)
                if src:cmds.disconnectAttr(src,plug)
                if saved["input"]:
                    origin=saved["input"];cmds.connectAttr(node(origin["node"])+"."+origin["attr"],plug)
                else:cmds.setAttr(plug,saved["value"])
        cmds.delete(existing)


def import_fbx(path):
    if not os.path.isfile(path) or os.path.splitext(path)[1].lower()!=".fbx":raise ValueError("Choose an FBX file.")
    if not cmds.pluginInfo("fbxmaya",query=True,loaded=True):cmds.loadPlugin("fbxmaya")
    namespace="Performer_"+uuid.uuid4().hex[:8]
    unit=cmds.currentUnit(query=True,time=True)
    playback={k:cmds.playbackOptions(query=True,**{k:True}) for k in ("minTime","maxTime","animationStartTime","animationEndTime")}
    with transaction("Aminate Import Performer FBX"):
        try:
            created=cmds.file(path,i=True,type="FBX",namespace=namespace,mergeNamespacesOnClash=False,returnNewNodes=True)
        finally:
            if cmds.currentUnit(query=True,time=True)!=unit:cmds.currentUnit(time=unit,updateAnimation=True)
            cmds.playbackOptions(**playback)
    joints=[n for n in created if cmds.objExists(n) and cmds.nodeType(n)=="joint"]
    return {"namespace":namespace,"joints":joints}
