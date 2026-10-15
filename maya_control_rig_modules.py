"""Optional native-node modules for Aminate generated rigs.

Extensions use the same ownership manifest and undo transaction as the builder.
No scripts run on time changes and no imported joint is reoriented.
"""
from __future__ import absolute_import, division, print_function
import json
import math
import maya_control_rig_builder as rigging
cmds=rigging.cmds
om=rigging.om


def commit(rig,data,builder):
    data["owned"]=list(set(data["owned"]+builder.owned))
    rigging.string_attr(rig,rigging.META,json.dumps(data))


def limb(data,ident):
    result=next((m for m in data["modules"] if m["id"]==ident),None)
    if not result or not result.get("ik"):raise ValueError("Choose a generated IK limb.")
    return result


def _number(n,name,default=0,minimum=None,maximum=None):
    options={"longName":name,"attributeType":"double","defaultValue":default,"keyable":True}
    if minimum is not None:options["minValue"]=minimum
    if maximum is not None:options["maxValue"]=maximum
    cmds.addAttr(n,**options)
    return n+"."+name


def add_stretch(rig,module_id):
    """Optional, scale-aware two-bone stretch with animatable limb lengths."""
    data=rigging.rig_data(rig);m=limb(data,module_id)
    if m.get("kind")=="spine":raise ValueError("This feature applies to two-segment limbs, not spline spines.")
    if m.get("stretch"):raise ValueError("Stretch is already installed on this limb.")
    if m.get("soft_ik"):raise ValueError("Add Stretch before Soft IK to combine both features.")
    b=rigging.Builder();prefix=data["id"]+"_"+module_id
    chain=[rigging.node(n) for n in m["solver"]]
    setup=cmds.listRelatives(chain[0],parent=True,fullPath=True)[0]
    control=rigging.node(m["ik_control"]);settings=rigging.node(m["settings"])
    with rigging.transaction("Aminate Add Limb Stretch"):
        stretch=_number(settings,"stretch",0,0,1)
        matrix=b.create("multMatrix",prefix+"_ReachMatrix")
        b.connect(control+".worldMatrix[0]",matrix+".matrixIn[0]")
        b.connect(setup+".worldInverseMatrix[0]",matrix+".matrixIn[1]")
        decompose=b.create("decomposeMatrix",prefix+"_ReachPosition");b.connect(matrix+".matrixSum",decompose+".inputMatrix")
        distance=b.create("distanceBetween",prefix+"_ReachDistance")
        b.connect(chain[0]+".translate",distance+".point1");b.connect(decompose+".outputTranslate",distance+".point2")
        lengths=[cmds.getAttr(n+".translateX") for n in chain[1:]]
        if any(abs(v)<1e-6 for v in lengths):raise ValueError("Stretch requires non-zero X-oriented generated segments.")
        sum_node=b.create("plusMinusAverage",prefix+"_RestLength")
        multipliers=[]
        for index,(joint,length) in enumerate(zip(chain[1:],lengths)):
            length_attr=_number(settings,("upperLength","lowerLength")[index],1,.001,100)
            rest=b.create("multiplyDivide",prefix+"_SegmentLength"+str(index))
            cmds.setAttr(rest+".input1X",abs(length));b.connect(length_attr,rest+".input2X")
            b.connect(rest+".outputX",sum_node+".input1D[{}]".format(index))
            multipliers.append((joint,length,length_attr))
        ratio=b.create("multiplyDivide",prefix+"_StretchRatio");cmds.setAttr(ratio+".operation",2)
        b.connect(distance+".distance",ratio+".input1X");b.connect(sum_node+".output1D",ratio+".input2X")
        condition=b.create("condition",prefix+"_OnlyStretch");cmds.setAttr(condition+".operation",2)
        b.connect(ratio+".outputX",condition+".firstTerm");cmds.setAttr(condition+".secondTerm",1)
        b.connect(ratio+".outputX",condition+".colorIfTrueR");cmds.setAttr(condition+".colorIfFalseR",1)
        blend=b.create("blendTwoAttr",prefix+"_StretchAmount");cmds.setAttr(blend+".input[0]",1)
        b.connect(condition+".outColorR",blend+".input[1]");b.connect(stretch,blend+".attributesBlender")
        for index,(joint,length,length_attr) in enumerate(multipliers):
            factor=b.create("multiplyDivide",prefix+"_LengthFactor"+str(index))
            b.connect(length_attr,factor+".input1X");b.connect(blend+".output",factor+".input2X")
            output=b.create("multiplyDivide",prefix+"_StretchedLength"+str(index));cmds.setAttr(output+".input1X",length)
            b.connect(factor+".outputX",output+".input2X");b.connect(output+".outputX",joint+".translateX")
        m["stretch"]={"rest_lengths":lengths,"length_node":rigging.uid(sum_node),"reach_matrix":rigging.uid(matrix)};commit(rig,data,b)


def add_spaces(rig,module_id):
    """World/global/body-parent spaces for an IK target and pole control."""
    data=rigging.rig_data(rig);m=limb(data,module_id)
    if m.get("kind")=="spine":raise ValueError("This feature applies to two-segment limbs, not spline spines.")
    if m.get("spaces"):raise ValueError("Spaces are already installed on this limb.")
    b=rigging.Builder();parent_id=data["description"]["nodes"][m["joints"][0]]["parent"]
    with rigging.transaction("Aminate Add Limb Spaces"):
        world=b.create("transform",data["id"]+"_"+module_id+"_WorldSpace",parent=rigging.node(data["group"]))
        choices=[("World",world),("Global",rigging.node(data["global"]))]
        if parent_id in data["controls"]:choices.append(("Body",rigging.node(parent_id)))
        records=[]
        for ctrl_id,zero_id in ((m["ik_control"],m["ik_zero"]),(m["pole"],m["pole_zero"])):
            ctrl,zero=rigging.node(ctrl_id),rigging.node(zero_id)
            cmds.addAttr(ctrl,longName="space",attributeType="enum",enumName=":".join(x[0] for x in choices),keyable=True,defaultValue=1)
            constraints=[]
            for command in (cmds.parentConstraint,cmds.scaleConstraint):
                constraint=b.own(command([n for _,n in choices],zero,maintainOffset=True)[0]);constraints.append(constraint)
                aliases=command(constraint,query=True,weightAliasList=True)
                for index,alias in enumerate(aliases):
                    condition=b.create("condition",data["id"]+"_SpaceWeight")
                    b.connect(ctrl+".space",condition+".firstTerm");cmds.setAttr(condition+".secondTerm",index)
                    cmds.setAttr(condition+".colorIfTrueR",1);cmds.setAttr(condition+".colorIfFalseR",0)
                    b.connect(condition+".outColorR",constraint+"."+alias)
            records.append({"control":ctrl_id,"choices":[n for n,_ in choices]})
        m["spaces"]=records;commit(rig,data,b)


def switch_space(rig,module_id,space):
    data=rigging.rig_data(rig);m=limb(data,module_id)
    if not m.get("spaces"):raise ValueError("Add limb spaces first.")
    b=rigging.Builder()
    with rigging.transaction("Aminate Match Space Switch"):
        poses={rec["control"]:rigging.world(rigging.node(rec["control"])) for rec in m["spaces"]}
        for rec in m["spaces"]:
            if space not in rec["choices"]:raise ValueError("This limb has no "+space+" space.")
            ctrl=rigging.node(rec["control"]);cmds.setAttr(ctrl+".space",rec["choices"].index(space))
            cmds.xform(ctrl,worldSpace=True,matrix=poses[rec["control"]]);b.keyframe(ctrl,attribute=rigging.TRS)
            b.keyframe(ctrl+".space",outTangentType="step")
            if not rigging.close(rigging.world(ctrl),poses[rec["control"]]):raise RuntimeError("Space switch changed the pose; rolled back.")
        commit(rig,data,b)


def add_foot_roll(rig,module_id,heel,ball,toe,bank_inner,bank_outer):
    """Explicit world-space guides avoid guessing shoe shape or character axes."""
    data=rigging.rig_data(rig);m=limb(data,module_id)
    if m.get("foot_roll"):raise ValueError("Foot roll is already installed.")
    guides=[heel,bank_outer,bank_inner,toe,ball]
    if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in guides):raise ValueError("Supply five finite world-space pivot positions.")
    b=rigging.Builder();ctrl=rigging.node(m["ik_control"])
    handles=cmds.listRelatives(ctrl,children=True,fullPath=True,type="ikHandle") or []
    if not m.get("soft_ik") and len(handles)!=1:raise ValueError("Expected one generated IK handle below this foot control.")
    with rigging.transaction("Aminate Add Foot Roll"):
        parent=ctrl;pivots=[]
        for name,point in zip(("heel","bankOuter","bankInner","toe","ball"),guides):
            pivot=b.create("transform",data["id"]+"_"+module_id+"_"+name,parent=parent)
            cmds.xform(pivot,worldSpace=True,matrix=rigging.world(ctrl));cmds.xform(pivot,worldSpace=True,translation=point)
            pivots.append(pivot);parent=pivot
        endpoint=b.create("transform",data["id"]+"_"+module_id+"_FootEndpoint",parent=parent)
        cmds.xform(endpoint,worldSpace=True,matrix=rigging.world(ctrl))
        if m.get("soft_ik"):
            matrix=rigging.node(m["soft_ik"]["reach_matrix"])
            b.connect(endpoint+".worldMatrix[0]",matrix+".matrixIn[0]",force=True)
        else:cmds.parent(handles[0],endpoint)
        if m.get("stretch"):b.connect(endpoint+".worldMatrix[0]",rigging.node(m["stretch"]["reach_matrix"])+".matrixIn[0]",force=True)
        solver_end=rigging.node(m["solver"][-1])
        constraints=cmds.listConnections(solver_end+".rotate",source=True,destination=False,type="orientConstraint") or []
        if any(rigging.uid(n) not in data["owned"] for n in constraints):raise ValueError("An external driver was added to the solver.")
        cmds.delete(constraints)
        b.own(cmds.orientConstraint(endpoint,solver_end,maintainOffset=True)[0])
        for index,name,axis in ((0,"heelRoll","X"),(1,"bankOut","Z"),(2,"bankIn","Z"),(3,"toeRoll","X"),(4,"ballRoll","X")):
            attr=_number(ctrl,name);b.connect(attr,pivots[index]+".rotate"+axis)
        # Individual signed pivot controls work for both sides and arbitrary
        # imported orientations; the animator decides the anatomical sign.
        m["foot_roll"]={"pivots":[rigging.uid(n) for n in pivots],"axes":"local X roll / local Z bank"};commit(rig,data,b)


def add_finger_pose_controls(rig,hand_id,fingers,axis="Z"):
    """Named curl sliders layered above existing finger FK controls."""
    data=rigging.rig_data(rig)
    if axis not in "XYZ" or hand_id not in data["controls"]:raise ValueError("Choose a mapped hand and a curl axis.")
    if any(j not in data["controls"] for chain in fingers.values() for j in chain):raise ValueError("Finger joints must belong to this rig.")
    primary=[j for chain in fingers.values() for j in chain]
    if len(primary)!=len(set(primary)):raise ValueError("A joint cannot belong to two fingers.")
    if not fingers:raise ValueError("Add at least one finger chain.")
    hand=rigging.node(data["controls"][hand_id]["control"]);b=rigging.Builder()
    with rigging.transaction("Aminate Add Finger Poses"):
        installed=data.setdefault("finger_modules",[])
        existing=next((m for m in installed if m["hand"]==hand_id),None)
        if existing and (set(existing["fingers"])&set(fingers) or set(j for chain in existing["fingers"].values() for j in chain)&set(primary)):
            raise ValueError("A finger name or joint is already configured for this hand.")
        for name,chain in fingers.items():
            if not name or rigging.re_safe(name)!=name:raise ValueError("Use simple unique finger names.")
            plug=_number(hand,name+"Curl")
            for ident in chain:
                ctrl=rigging.node(data["controls"][ident]["control"])
                if not rigging.node(ident).startswith(rigging.node(hand_id)+"|"):raise ValueError("Finger is not below the chosen hand.")
                parent=cmds.listRelatives(ctrl,parent=True,fullPath=True)[0]
                offset=b.create("transform",data["id"]+"_"+name+"_Curl",parent=parent)
                cmds.parent(ctrl,offset,relative=True);b.connect(plug,offset+".rotate"+axis)
                data["controls"][ident]["zero"]=rigging.uid(offset)
        if existing:existing["fingers"].update(fingers)
        else:installed.append({"hand":hand_id,"fingers":fingers,"axis":axis})
        commit(rig,data,b)


def mirror_pose(rig,axis="X",selected_only=False):
    """Reflect world poses through the rig-global plane with rest-axis offsets."""
    data=rigging.rig_data(rig)
    b=rigging.Builder()
    if axis not in "XYZ":raise ValueError("Mirror axis must be X, Y or Z.")
    pairs=[];roles=data["roles"]
    for role,ident in roles.items():
        if not role.startswith("left."):continue
        other=roles.get("right."+role[5:])
        if other:pairs.extend(((ident,other),(other,ident)))
    if selected_only:
        selected={rigging.uid(n) for n in cmds.ls(selection=True,long=True) or []}
        pairs=[p for p in pairs if data["controls"][p[0]]["control"] in selected]
    if not pairs:raise ValueError("Map matching left/right roles first.")
    mirror=list(rigging.IDENTITY);mirror["XYZ".index(axis)*5]=-1
    global_world=rigging.world(rigging.node(data["global"]));global_inverse=rigging.inverse(global_world)
    cached={}
    for source,target in pairs:
        current=rigging.multiply(rigging.world(rigging.node(source)),global_inverse)
        source_rest=data["controls"][source]["rest"];target_rest=data["controls"][target]["rest"]
        reflected=rigging.multiply(mirror,current,mirror)
        rest_reflected=rigging.multiply(mirror,source_rest,mirror)
        cached[target]=rigging.multiply(target_rest,rigging.inverse(rest_reflected),reflected,global_world)
    with rigging.transaction("Aminate Mirror Pose"):
        # FK destinations are required, otherwise hidden FK edits do not move
        # the skeleton. Match the complete limb before applying the mirror.
        for m in data["modules"]:
            if m.get("ik") and set(m["joints"])&set(cached):
                if cmds.getAttr(rigging.node(m["settings"])+".ikFk")!=0:raise ValueError("Switch mirrored limbs to FK first.")
        for ident in sorted(cached,key=lambda n:data["controls"][n]["depth"]):
            ctrl=rigging.node(data["controls"][ident]["control"])
            cmds.xform(ctrl,worldSpace=True,matrix=cached[ident]);b.keyframe(ctrl,attribute=rigging.TRS)
        commit(rig,data,b)


def set_display(rig,scale=1.,show_fk=True,show_ik=True):
    data=rigging.rig_data(rig)
    if not math.isfinite(scale) or scale<=0:raise ValueError("Control shape scale must be positive.")
    with rigging.transaction("Aminate Control Display"):
        for rec in data["controls"].values():
            ctrl=rigging.node(rec["control"]);cmds.setAttr(ctrl+".visibility",show_fk)
            if scale!=1:cmds.scale(scale,scale,scale,ctrl+".cv[*]",relative=True,objectSpace=True)
        for m in data["modules"]:
            if m.get("ik"):
                controls=m["spine_controls"] if m.get("kind")=="spine" else (m["ik_control"],m["pole"])
                for ident in controls:cmds.setAttr(rigging.node(ident)+".visibility",show_ik)


def bake_export_skeleton(rig,start,end,dense=True,key_times=None):
    """Independent skeleton copy; preserves original rig, skin and animation."""
    data=rigging.rig_data(rig);times=rigging.frames(start,end,key_times,dense)
    if not times:raise ValueError("No requested sample times in the export range.")
    ordered=sorted(data["controls"],key=lambda n:data["controls"][n]["depth"])
    with rigging.transaction("Aminate Bake Export Skeleton"):
        samples=[]
        for t in times:
            cmds.currentTime(t);samples.append((t,{n:rigging.world(rigging.node(n)) for n in ordered}))
        group=cmds.createNode("transform",name=data["id"]+"_Export")
        output={}
        for ident in ordered:
            source=rigging.node(ident);parent=data["controls"][ident]["parent"]
            joint=cmds.createNode("joint",name=rigging.re_safe(source.rsplit("|",1)[-1])+"_export",parent=output.get(parent,group))
            for attr in ("jointOrient","rotateAxis"):
                cmds.setAttr(joint+"."+attr,*cmds.getAttr(source+"."+attr)[0])
            for attr in ("rotateOrder","segmentScaleCompensate","radius"):
                cmds.setAttr(joint+"."+attr,cmds.getAttr(source+"."+attr))
            output[ident]=joint
        for t,poses in samples:
            cmds.currentTime(t)
            for ident in ordered:
                joint=output[ident];cmds.xform(joint,worldSpace=True,matrix=poses[ident])
                cmds.setKeyframe(joint,attribute=rigging.TRS,time=t,minimizeRotation=True,inTangentType="linear",outTangentType="linear")
                if not rigging.close(rigging.world(joint),poses[ident]):raise RuntimeError("Export cannot represent the source transform; rolled back.")
        rigging.string_attr(group,"aminateExportSource",json.dumps({"rig":rigging.uid(rig),"times":times,"joints":{k:rigging.uid(v) for k,v in output.items()}}))
    return group


def add_soft_ik(rig,module_id):
    """Exponential end-of-reach easing built entirely from Maya DG nodes."""
    data=rigging.rig_data(rig);m=limb(data,module_id)
    if m.get("kind")=="spine":raise ValueError("This feature applies to two-segment limbs, not spline spines.")
    if m.get("soft_ik"):raise ValueError("Soft IK is already installed.")
    if m.get("foot_roll"):raise ValueError("Add Soft IK before configuring foot pivots.")
    b=rigging.Builder();chain=[rigging.node(n) for n in m["solver"]]
    control=rigging.node(m["ik_control"]);settings=rigging.node(m["settings"])
    setup=cmds.listRelatives(chain[0],parent=True,fullPath=True)[0]
    handles=cmds.listRelatives(control,children=True,fullPath=True,type="ikHandle") or []
    if len(handles)!=1:raise ValueError("Expected a generated IK handle directly below the target.")
    total=sum(abs(cmds.getAttr(n+".translateX")) for n in chain[1:])
    prefix=data["id"]+"_"+module_id+"_Soft"
    with rigging.transaction("Aminate Add Soft IK"):
        softness=_number(settings,"softness",0,0,total*.9)
        def connect(value,plug):
            if isinstance(value,str):b.connect(value,plug)
            else:cmds.setAttr(plug,value)
        def scalar(kind,left,right,operation=None):
            n=b.create(kind,prefix+"Math")
            if kind=="multiplyDivide":
                if operation:cmds.setAttr(n+".operation",operation)
                connect(left,n+".input1X");connect(right,n+".input2X");return n+".outputX"
            if kind=="plusMinusAverage":
                if operation:cmds.setAttr(n+".operation",operation)
                connect(left,n+".input1D[0]");connect(right,n+".input1D[1]");return n+".output1D"
        matrix=b.create("multMatrix",prefix+"Matrix");b.connect(control+".worldMatrix[0]",matrix+".matrixIn[0]");b.connect(setup+".worldInverseMatrix[0]",matrix+".matrixIn[1]")
        decompose=b.create("decomposeMatrix",prefix+"Position");b.connect(matrix+".matrixSum",decompose+".inputMatrix")
        distance=b.create("distanceBetween",prefix+"Distance");b.connect(chain[0]+".translate",distance+".point1");b.connect(decompose+".outputTranslate",distance+".point2")
        safe=b.create("clamp",prefix+"SafeSoftness");cmds.setAttr(safe+".minR",.00001);cmds.setAttr(safe+".maxR",total);b.connect(softness,safe+".inputR")
        total_input=rigging.node(m["stretch"]["length_node"])+".output1D" if m.get("stretch") else total
        threshold=scalar("plusMinusAverage",total_input,safe+".outputR",2)
        excess=scalar("plusMinusAverage",threshold,distance+".distance",2)
        exponent=scalar("multiplyDivide",excess,safe+".outputR",2)
        # Clamp the unused negative-distance branch to prevent exp overflow.
        bounded=b.create("clamp",prefix+"Exponent");cmds.setAttr(bounded+".minR",-100);cmds.setAttr(bounded+".maxR",0);b.connect(exponent,bounded+".inputR")
        power=scalar("multiplyDivide",math.e,bounded+".outputR",3)
        ease=scalar("multiplyDivide",safe+".outputR",scalar("plusMinusAverage",1,power,2))
        eased_distance=scalar("plusMinusAverage",threshold,ease)
        condition=b.create("condition",prefix+"Threshold");cmds.setAttr(condition+".operation",2)
        b.connect(distance+".distance",condition+".firstTerm");b.connect(threshold,condition+".secondTerm")
        b.connect(eased_distance,condition+".colorIfTrueR");b.connect(distance+".distance",condition+".colorIfFalseR")
        enabled=b.create("condition",prefix+"Enabled");cmds.setAttr(enabled+".operation",2);b.connect(softness,enabled+".firstTerm");cmds.setAttr(enabled+".secondTerm",.000001)
        b.connect(condition+".outColorR",enabled+".colorIfTrueR");b.connect(distance+".distance",enabled+".colorIfFalseR")
        safe_distance=b.create("clamp",prefix+"SafeDistance");cmds.setAttr(safe_distance+".minR",.00001);cmds.setAttr(safe_distance+".maxR",1e12);b.connect(distance+".distance",safe_distance+".inputR")
        distance_output=enabled+".outColorR"
        if m.get("stretch"):
            stretch_blend=b.create("blendTwoAttr",prefix+"StretchBlend")
            b.connect(distance_output,stretch_blend+".input[0]");b.connect(distance+".distance",stretch_blend+".input[1]")
            b.connect(settings+".stretch",stretch_blend+".attributesBlender");distance_output=stretch_blend+".output"
        ratio=scalar("multiplyDivide",distance_output,safe_distance+".outputR",2)
        difference=b.create("plusMinusAverage",prefix+"Direction");cmds.setAttr(difference+".operation",2)
        b.connect(decompose+".outputTranslate",difference+".input3D[0]");b.connect(chain[0]+".translate",difference+".input3D[1]")
        vector=b.create("multiplyDivide",prefix+"Vector");b.connect(difference+".output3D",vector+".input1")
        for axis in "XYZ":b.connect(ratio,vector+".input2"+axis)
        position=b.create("plusMinusAverage",prefix+"Target");b.connect(chain[0]+".translate",position+".input3D[0]");b.connect(vector+".output",position+".input3D[1]")
        target=b.create("transform",prefix+"HandleTarget",parent=setup);b.connect(position+".output3D",target+".translate")
        moved_handle=cmds.parent(handles[0],target)[0];cmds.setAttr(moved_handle+".translate",0,0,0)
        m["soft_ik"]={"target":rigging.uid(target),"rest_length":total,"reach_matrix":rigging.uid(matrix)};commit(rig,data,b)


def add_spine_ik(rig,joints,module_id="spine"):
    """Variable-count spline spine with one editable curve control per joint."""
    data=rigging.rig_data(rig);ids=[rigging.uid(rigging.node(n)) for n in joints]
    if len(ids)<3 or len(set(ids))!=len(ids) or any(n not in data["controls"] for n in ids):raise ValueError("Select at least three distinct spine joints from this rig.")
    if not module_id or rigging.re_safe(module_id)!=module_id or any(m["id"]==module_id for m in data["modules"]):raise ValueError("Choose a unique spine module name.")
    records=data["description"]["nodes"]
    if any(records[c]["parent"]!=p for p,c in zip(ids,ids[1:])):raise ValueError("Select the complete contiguous spine chain in hierarchy order.")
    if any(set(m["joints"])&set(ids) for m in data["modules"]):raise ValueError("Spine joints already belong to another solver module.")
    if any(not rigging.close(rigging.world(rigging.node(n)),records[n]["world"]) for n in ids):raise ValueError("Return the spine to its scanned reference pose before adding IK.")
    b=rigging.Builder();prefix=data["id"]+"_"+module_id
    with rigging.transaction("Aminate Add Spine IK"):
        setup=b.create("transform",prefix+"_Solver",parent=rigging.node(data["global"]))
        parent=records[ids[0]]["parent"]
        if parent in data["controls"]:b.follow(rigging.node(parent),setup)
        chain=[]
        for index,n in enumerate(ids):
            j=b.create("joint",prefix+"_Solve"+str(index),parent=chain[-1] if chain else setup)
            cmds.xform(j,worldSpace=True,translation=records[n]["position"]);chain.append(j)
        cmds.joint(chain[0],edit=True,orientJoint="xyz",secondaryAxisOrient="yup",children=True,zeroScaleOrient=True)
        curve=b.own(cmds.curve(name=prefix+"_Curve",degree=1,point=[records[n]["position"] for n in ids]))
        curve=cmds.parent(curve,rigging.node(data["group"]))[0]
        for shape in cmds.listRelatives(curve,shapes=True,fullPath=True) or []:b.own(shape)
        controls=[]
        for index,n in enumerate(ids):
            ctrl,zero=b.control(prefix+"_IK"+str(index),records[n]["world"],1,rigging.node(data["global"]))
            cluster,handle=b.cluster(curve,curve+".cv[{}]".format(index),prefix+"_CV"+str(index))
            handle=cmds.parent(handle,ctrl)[0];cmds.setAttr(handle+".visibility",False)
            controls.append(rigging.uid(ctrl))
        handle,effector=cmds.ikHandle(name=prefix+"_Handle",startJoint=chain[0],endEffector=chain[-1],solver="ikSplineSolver",curve=curve,createCurve=False,parentCurve=False)
        b.own(handle);b.own(effector);handle=cmds.parent(handle,setup)[0]
        cmds.setAttr(handle+".dTwistControlEnable",True);cmds.setAttr(handle+".dWorldUpType",4)
        cmds.setAttr(handle+".dForwardAxis",0);cmds.setAttr(handle+".dWorldUpAxis",0)
        b.connect(rigging.node(controls[0])+".worldMatrix[0]",handle+".dWorldUpMatrix")
        b.connect(rigging.node(controls[-1])+".worldMatrix[0]",handle+".dWorldUpMatrixEnd")
        settings,zero=b.control(prefix+"_Settings",records[ids[-1]]["world"],.6,rigging.node(data["global"]))
        switch=_number(settings,"ikFk",0,0,1);reverse=b.create("reverse",prefix+"_FKWeight");b.connect(switch,reverse+".inputX")
        for solver,ident in zip(chain,ids):
            constraint=rigging.node(data["controls"][ident]["constraint"])
            cmds.parentConstraint(solver,rigging.node(ident),maintainOffset=True,weight=0)
            aliases=cmds.parentConstraint(constraint,query=True,weightAliasList=True)
            b.connect(reverse+".outputX",constraint+"."+aliases[0]);b.connect(switch,constraint+"."+aliases[1])
        cmds.setAttr(setup+".visibility",False);cmds.setAttr(curve+".visibility",False)
        data["modules"].append({"id":module_id,"kind":"spine","ik":True,"joints":ids,"settings":rigging.uid(settings),"spine_controls":controls,"solver":[rigging.uid(n) for n in chain]})
        commit(rig,data,b)


def match_spine(rig,module_id,to_ik):
    data=rigging.rig_data(rig);m=limb(data,module_id)
    b=rigging.Builder()
    if m.get("kind")!="spine":raise ValueError("Choose a spine module.")
    poses={n:rigging.world(rigging.node(n)) for n in m["joints"]}
    with rigging.transaction("Aminate Match Spine FK IK"):
        for ident,ctrl_id in zip(m["joints"],m["spine_controls"]):
            ctrl=rigging.node(ctrl_id if to_ik else data["controls"][ident]["control"])
            cmds.xform(ctrl,worldSpace=True,matrix=poses[ident]);b.keyframe(ctrl,attribute=rigging.TRS)
        settings=rigging.node(m["settings"]);cmds.setAttr(settings+".ikFk",1 if to_ik else 0);b.keyframe(settings+".ikFk",outTangentType="step")
        if any(not rigging.close(rigging.world(rigging.node(n)),pose) for n,pose in poses.items()):raise RuntimeError("This spine pose is outside the spline solver's representable poses. Matching was rolled back.")
        commit(rig,data,b)


def add_aim(rig,joint,forward_axis="Z",up_axis="Y",distance=20.):
    """Add a head/eye look target above its existing FK control."""
    data=rigging.rig_data(rig);ident=rigging.uid(rigging.node(joint))
    if ident not in data["controls"] or forward_axis not in "XYZ" or up_axis not in "XYZ" or forward_axis==up_axis:raise ValueError("Choose a rig joint and distinct forward/up axes.")
    if not math.isfinite(distance) or distance<=0:raise ValueError("Look distance must be positive.")
    b=rigging.Builder();rec=data["controls"][ident];ctrl=rigging.node(rec["control"])
    with rigging.transaction("Aminate Add Look Control"):
        if any(m["joint"]==ident for m in data.get("aim_modules",[])):raise ValueError("This joint already has a look control.")
        matrix=rigging.world(ctrl);forward=[0.,0.,0.];forward["XYZ".index(forward_axis)]=1
        up=[0.,0.,0.];up["XYZ".index(up_axis)]=1
        point=om.MPoint(*(v*distance for v in forward))*om.MMatrix(matrix)
        target_matrix=list(matrix);target_matrix[12:15]=list(point)[:3]
        look,zero=b.control(data["id"]+"_Look",target_matrix,1,rigging.node(data["global"]))
        parent=cmds.listRelatives(ctrl,parent=True,fullPath=True)[0]
        offset=b.create("transform",data["id"]+"_Aim",parent=parent);cmds.parent(ctrl,offset,relative=True)
        b.own(cmds.aimConstraint(look,offset,maintainOffset=True,aimVector=forward,upVector=up,worldUpType="objectrotation",worldUpVector=up,worldUpObject=rigging.node(data["global"]))[0])
        data["controls"][ident]["zero"]=rigging.uid(offset)
        data.setdefault("aim_modules",[]).append({"joint":ident,"control":rigging.uid(look),"forward":forward_axis,"up":up_axis})
        commit(rig,data,b)
    return look


def add_face_sliders(rig,blendshape,aliases):
    """Expose chosen, undriven blend-shape weights on an animator control."""
    data=rigging.rig_data(rig);blendshape=rigging.node(blendshape)
    if cmds.nodeType(blendshape)!="blendShape":raise ValueError("Choose a blendShape node.")
    if cmds.referenceQuery(blendshape,isNodeReferenced=True):raise ValueError("Use an editable local blendShape node.")
    if not aliases or len(aliases)!=len(set(aliases)):raise ValueError("Choose distinct blend-shape aliases.")
    pairs=cmds.aliasAttr(blendshape,query=True) or [];lookup=dict(zip(pairs[::2],pairs[1::2]))
    records=[]
    for alias in aliases:
        if alias not in lookup:raise ValueError("Missing blend-shape alias: "+alias)
        plug=blendshape+"."+lookup[alias]
        if cmds.connectionInfo(plug,sourceFromDestination=True) or cmds.getAttr(plug,lock=True):raise ValueError("This facial weight already has a driver or is locked: "+alias)
        records.append({"node":rigging.uid(blendshape),"attr":lookup[alias],"alias":alias,"value":cmds.getAttr(plug)})
    b=rigging.Builder()
    with rigging.transaction("Aminate Add Face Sliders"):
        head=data["roles"].get("head");matrix=data["controls"][head]["rest"] if head else rigging.IDENTITY
        ctrl,zero=b.control(data["id"]+"_Face",matrix,2,rigging.node(data["global"]))
        for index,record in enumerate(records):
            slider=_number(ctrl,"face_"+str(index)+"_"+rigging.re_safe(record["alias"]),record["value"],0,1)
            b.connect(slider,blendshape+"."+record["attr"])
        data.setdefault("face_modules",[]).append({"control":rigging.uid(ctrl),"weights":records});commit(rig,data,b)
    return ctrl


def match_range(rig,module_id,to_ik,start,end,dense=True,key_times=None):
    times=rigging.frames(start,end,key_times,dense)
    if not times:raise ValueError("Choose keys or an every-frame range to match.")
    b=rigging.Builder()
    with rigging.transaction("Aminate Match FK IK Range"):
        # Capture all source poses before any switch curve changes evaluation
        # of later samples. One-frame matching alone cannot guarantee this.
        data=rigging.rig_data(rig);m=limb(data,module_id)
        samples=[]
        for t in times:
            cmds.currentTime(t);samples.append((t,{n:rigging.world(rigging.node(n)) for n in m["joints"]}))
        for t,poses in samples:
            cmds.currentTime(t)
            settings=rigging.node(m["settings"])
            cmds.setAttr(settings+".ikFk",0)
            for ident in m["joints"]:
                ctrl=rigging.node(data["controls"][ident]["control"])
                cmds.xform(ctrl,worldSpace=True,matrix=poses[ident]);b.keyframe(ctrl,attribute=rigging.TRS,time=t)
            b.keyframe(settings+".ikFk",value=0,time=t,outTangentType="step")
            rigging.match_limb(rig,module_id,to_ik)
            if any(not rigging.close(rigging.world(rigging.node(n)),p) for n,p in poses.items()):raise RuntimeError("Range match failed at frame "+str(t)+"; rolled back.")
        commit(rig,rigging.rig_data(rig),b)
    return times
