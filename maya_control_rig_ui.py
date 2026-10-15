"""Lazy Qt panels for Control Rig Builder and Multi-Performer Mocap."""
from __future__ import absolute_import, division, print_function
import aminate_skeleton_map as mapping
import maya_control_rig_builder as rigging
import maya_multi_performer_mocap as mocap
import maya_control_rig_modules as modules
try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

cmds=rigging.cmds


def button(layout,label,action):
    widget=QtWidgets.QPushButton(label);layout.addWidget(widget)
    def run():
        try:action()
        except Exception as exc:QtWidgets.QMessageBox.warning(widget,"Aminate",str(exc))
    widget.clicked.connect(run)
    return widget


def number(value,minimum=-1000000,maximum=1000000):
    widget=QtWidgets.QDoubleSpinBox();widget.setRange(minimum,maximum);widget.setDecimals(3);widget.setValue(value)
    return widget


def note(layout,text):
    label=QtWidgets.QLabel(text);label.setWordWrap(True);layout.addWidget(label)
    return label


def selected_joints():
    joints=cmds.ls(orderedSelection=True,long=True,type="joint") or []
    # Hierarchy order is deterministic even when Maya selection tracking is off.
    return sorted(joints,key=lambda n:n.count("|"))


class RigPanel(QtWidgets.QWidget):
    def __init__(self,parent=None):
        super(RigPanel,self).__init__(parent)
        self.description=None;self.modules=[];self.aliases={};self.suggestions={}
        layout=QtWidgets.QVBoxLayout(self)
        note(layout,"Pick the skeleton's top joint in its starting pose. Scan it, check the joint labels, then build controls.")
        self.left=QtWidgets.QComboBox();self.left.addItems(["Side from names only","Character left: +X","Character left: -X","Character left: +Z","Character left: -Z"]);layout.addWidget(self.left)
        button(layout,"Scan selected skeleton / Auto-map",self.scan)
        self.table=QtWidgets.QTableWidget(len(mapping.ROLE_ORDER),3);self.table.setHorizontalHeaderLabels(["Role","Joint","Evidence"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents);self.table.setMinimumHeight(260);layout.addWidget(self.table)
        for index, role in enumerate(mapping.ROLE_ORDER):
            self.table.setItem(index,0,QtWidgets.QTableWidgetItem(role))
        self.table.setToolTip("Scan a skeleton to fill the Joint and Evidence columns.")
        row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        button(row,"Assign selected joint to role",self.assign)
        button(layout,"Suggest remaining roles from assigned anchors",self.suggest_anchors)
        button(row,"Save map",self.save_map);button(row,"Load map",self.load_map)
        button(layout,"Remember selected role name as an alias",self.remember_alias)
        self.limbs=QtWidgets.QListWidget();self.limbs.setMinimumHeight(100);layout.addWidget(self.limbs)
        row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        button(row,"Use mapped arms and legs",self.standard_limbs)
        button(row,"Add selected three-joint limb",self.add_limb)
        button(row,"Remove limb",self.remove_limb)
        self.preserve=QtWidgets.QCheckBox("Preserve existing animation over range");layout.addWidget(self.preserve)
        form=QtWidgets.QFormLayout();layout.addLayout(form)
        self.start=number(cmds.playbackOptions(query=True,minTime=True));self.end=number(cmds.playbackOptions(query=True,maxTime=True))
        form.addRow("Start frame",self.start);form.addRow("End frame",self.end)
        button(layout,"Build control rig",self.build)
        note(layout,"Built rig")
        self.rig=QtWidgets.QComboBox();layout.addWidget(self.rig);button(layout,"Refresh scene rigs",self.refresh)
        self.match=QtWidgets.QComboBox();layout.addWidget(self.match);self.rig.currentIndexChanged.connect(self.refresh_limbs)
        row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        button(row,"Match and switch to IK",lambda:self.switch(True));button(row,"Match and switch to FK",lambda:self.switch(False))
        row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        button(row,"Save pose",self.save_pose);button(row,"Load and key pose",self.load_pose)
        self.extension=QtWidgets.QComboBox()
        self.extension.addItems(["Add stretch to chosen limb","Add soft IK to chosen limb","Add world / global / body spaces","Switch chosen limb to World","Switch chosen limb to Global","Switch chosen limb to Body","Add spine IK from selected joints","Add look control to selected head / eye","Add foot pivots from five selected guides","Add finger curl from selected chain","Mirror mapped FK pose","Bake independent export skeleton","Add face blend-shape sliders","Match chosen limb to IK over range","Match chosen limb to FK over range"])
        layout.addWidget(self.extension);button(layout,"Apply rig feature",self.apply_extension)
        note(layout,"Stretch → Soft IK → Foot pivots is the supported setup order. Foot guides: heel, ball, toe, inner bank, outer bank. Set Maya Track Selection Order before selecting guides. Finger curl uses local Z; look controls use local +Z forward and +Y up.")
        button(layout,"Remove rig / restore original animation",self.remove)
        self.status=note(layout,"Ready. Generated rigs and mapping metadata survive scene save and reopen.")
        layout.addStretch();self.refresh()

    def scan(self):
        selection=cmds.ls(selection=True,long=True) or []
        if len(selection)!=1:raise ValueError("Select one skeleton root or its parent group.")
        axis=[None,[1,0,0],[-1,0,0],[0,0,1],[0,0,-1]][self.left.currentIndex()]
        self.description=rigging.scan(selection[0],axis);self.modules=[]
        self.suggestions=mapping.suggest(self.description,aliases=self.aliases)
        self.populate();self.standard_limbs()
        self.status.setText("Scanned {} joints at frame {}. Review Check and Missing slots.".format(len(self.description["nodes"]),self.description["reference_frame"]))

    def populate(self):
        for index,role in enumerate(mapping.ROLE_ORDER):
            self.table.setItem(index,0,QtWidgets.QTableWidgetItem(role))
            combo=QtWidgets.QComboBox();combo.addItem("Unassigned",None)
            for ident,rec in sorted(self.description["nodes"].items(),key=lambda x:x[1]["path"]):combo.addItem(rec["path"],ident)
            suggestion=self.suggestions.get(role,{})
            combo.setCurrentIndex(max(0,combo.findData(suggestion.get("node"))))
            self.table.setCellWidget(index,1,combo)
            combo.currentIndexChanged.connect(lambda _value,row=index:self.table.setItem(row,2,QtWidgets.QTableWidgetItem("Confirmed: manual selection")))
            self.table.setItem(index,2,QtWidgets.QTableWidgetItem(suggestion.get("status","Missing")+": "+", ".join(suggestion.get("why",[]))))

    def roles(self):
        if not self.description:raise ValueError("Scan a skeleton first.")
        result={role:self.table.cellWidget(i,1).currentData() for i,role in enumerate(mapping.ROLE_ORDER) if self.table.cellWidget(i,1).currentData()}
        if len(set(result.values()))!=len(result):raise ValueError("A joint is assigned to more than one anatomical role.")
        return result

    def assign(self):
        row=self.table.currentRow();selection=selected_joints()
        if row<0 or len(selection)!=1:raise ValueError("Select one role row and one Maya joint.")
        ident=rigging.uid(selection[0]);combo=self.table.cellWidget(row,1);index=combo.findData(ident)
        if index<0:raise ValueError("Joint is outside the scanned skeleton.")
        combo.setCurrentIndex(index);self.table.setItem(row,2,QtWidgets.QTableWidgetItem("Confirmed: user assignment"))

    def remember_alias(self):
        row=self.table.currentRow()
        if row<0:raise ValueError("Choose a role row first.")
        ident=self.table.cellWidget(row,1).currentData()
        if not ident:raise ValueError("Assign a joint to that role first.")
        role=mapping.ROLE_ORDER[row].rsplit(".",1)[-1]
        parts=mapping.tokens(self.description["nodes"][ident]["name"])
        alias="".join(p for p in parts if p not in mapping.IGNORE and p not in mapping.SIDE and not p.isdigit())
        if not alias:raise ValueError("This name has no reusable anatomical word. Save the explicit mapping instead.")
        self.aliases.setdefault(role,[]).append(alias)
        self.status.setText("Remembered "+alias+" for "+role+". Save the map to reuse this alias.")

    def suggest_anchors(self):
        self.suggestions=mapping.suggest(self.description,locked=self.roles(),aliases=self.aliases)
        self.populate()

    def apply_extension(self):
        rig=self.rig.currentText();module=self.match.currentText();index=self.extension.currentIndex()
        if index==0:modules.add_stretch(rig,module)
        elif index==1:modules.add_soft_ik(rig,module)
        elif index==2:modules.add_spaces(rig,module)
        elif index in (3,4,5):modules.switch_space(rig,module,("World","Global","Body")[index-3])
        elif index==6:
            name,ok=QtWidgets.QInputDialog.getText(self,"Spine module","Unique spine name",text="spine")
            if ok:modules.add_spine_ik(rig,selected_joints(),name)
        elif index==7:
            selection=selected_joints()
            if len(selection)!=1:raise ValueError("Select one head or eye joint.")
            modules.add_aim(rig,selection[0])
        elif index==8:
            if not cmds.selectPref(query=True,trackSelectionOrder=True):raise ValueError("Enable Track Selection Order in Maya preferences, then reselect the five guides.")
            selection=cmds.ls(orderedSelection=True,long=True,type="transform") or []
            if len(selection)!=5:raise ValueError("Select heel, ball, toe, inner bank and outer bank guides in order.")
            modules.add_foot_roll(rig,module,*[rigging.world(n)[12:15] for n in selection])
        elif index==9:
            selection=selected_joints()
            if len(selection)<2:raise ValueError("Select the hand followed by a finger chain.")
            name,ok=QtWidgets.QInputDialog.getText(self,"Finger name","Name for the curl slider",text="index")
            if ok:modules.add_finger_pose_controls(rig,rigging.uid(selection[0]),{name:[rigging.uid(n) for n in selection[1:]]})
        elif index==10:modules.mirror_pose(rig)
        elif index==11:modules.bake_export_skeleton(rig,self.start.value(),self.end.value())
        elif index==12:
            selection=cmds.ls(selection=True) or []
            shapes=[n for n in selection if cmds.nodeType(n)=="blendShape"]
            if len(shapes)!=1:raise ValueError("Select one blendShape node in the Node Editor or Outliner.")
            aliases=cmds.aliasAttr(shapes[0],query=True) or []
            modules.add_face_sliders(rig,shapes[0],aliases[::2])
        elif index in (13,14):modules.match_range(rig,module,index==13,self.start.value(),self.end.value())
        self.refresh_limbs();self.status.setText("Rig feature applied. It can be reverted with Maya Undo.")

    def standard_limbs(self):
        self.modules=mapping.humanoid_modules(self.roles(),self.description);self.show_limbs()

    def show_limbs(self):
        self.limbs.clear()
        for m in self.modules:self.limbs.addItem(m["id"]+" — "+" → ".join(self.description["nodes"][n]["name"] for n in m["joints"]))

    def add_limb(self):
        if not self.description:raise ValueError("Scan a skeleton first.")
        selected=selected_joints()
        if len(selected)!=3:raise ValueError("Select the limb start, middle and end joints.")
        name,ok=QtWidgets.QInputDialog.getText(self,"Limb group","Unique group name (for example upper_left_arm)")
        if not ok:return
        item={"id":name.strip(),"kind":"limb","joints":[rigging.uid(n) for n in selected],"ik":True}
        mapping.validate_modules(self.modules+[item],self.description["nodes"])
        self.modules.append(item);self.show_limbs()

    def remove_limb(self):
        index=self.limbs.currentRow()
        if index>=0:self.modules.pop(index);self.show_limbs()

    def save_map(self):
        roles=self.roles();path,_=QtWidgets.QFileDialog.getSaveFileName(self,"Save map","","JSON (*.json)")
        if path:mapping.save_profile(path,self.description,roles,self.modules,self.aliases)

    def load_map(self):
        if not self.description:raise ValueError("Scan the destination skeleton first.")
        path,_=QtWidgets.QFileDialog.getOpenFileName(self,"Load map","","JSON (*.json)")
        if path:
            roles,self.modules,self.aliases=mapping.load_profile(path,self.description)
            self.suggestions=mapping.suggest(self.description,locked=roles,aliases=self.aliases);self.populate();self.show_limbs()

    def build(self):
        rig=rigging.Builder().build(self.description,self.roles(),self.modules,self.preserve.isChecked(),self.start.value(),self.end.value())
        self.refresh();self.rig.setCurrentText(rig)
        warnings=rigging.rig_data(rig)["warnings"]
        self.status.setText("Built "+rig+(". "+"; ".join(warnings) if warnings else ". FK/IK matching is available for the configured limbs."))

    def refresh(self):
        current=self.rig.currentText();self.rig.clear();self.rig.addItems(rigging.rigs());self.rig.setCurrentText(current);self.refresh_limbs()

    def refresh_limbs(self,*args):
        self.match.clear()
        if self.rig.currentText():self.match.addItems([m["id"] for m in rigging.rig_data(self.rig.currentText())["modules"] if m.get("ik")])

    def switch(self,to_ik):rigging.match_limb(self.rig.currentText(),self.match.currentText(),to_ik)

    def save_pose(self):
        path,_=QtWidgets.QFileDialog.getSaveFileName(self,"Save pose","","JSON (*.json)")
        if path:rigging.save_pose(self.rig.currentText(),path)

    def load_pose(self):
        path,_=QtWidgets.QFileDialog.getOpenFileName(self,"Load pose","","JSON (*.json)")
        if path:rigging.load_pose(self.rig.currentText(),path)

    def remove(self):
        rigging.remove(self.rig.currentText());self.refresh();self.status.setText("Original animation restored. Undo restores the generated rig.")


class MocapPanel(QtWidgets.QWidget):
    def __init__(self,parent=None):
        super(MocapPanel,self).__init__(parent)
        self.routes=[];self.preview=None
        layout=QtWidgets.QVBoxLayout(self)
        note(layout,"Import a performer. Pick their three arm joints, choose a target limb below, then add the route. Repeat for each limb.")
        button(layout,"Import performer FBX",self.import_fbx)
        note(layout,"Target rig — build one in Control Rig Builder first")
        self.rig=QtWidgets.QComboBox();layout.addWidget(self.rig);button(layout,"Refresh target rigs",self.refresh)
        note(layout,"Target limb or body part")
        self.module=QtWidgets.QComboBox();layout.addWidget(self.module);self.rig.currentIndexChanged.connect(self.rig_changed)
        form=QtWidgets.QFormLayout();layout.addLayout(form)
        self.label=QtWidgets.QLineEdit("Performer 1");form.addRow("Performer label",self.label)
        self.reference=number(cmds.currentTime(query=True));form.addRow("Source reference-pose frame",self.reference)
        self.source_start=number(1);self.source_end=number(120);self.target_start=number(1)
        form.addRow("Source clip start",self.source_start);form.addRow("Source clip end",self.source_end);form.addRow("Place at target frame",self.target_start)
        self.speed=number(1,.001,100);self.offset=number(0);form.addRow("Playback speed",self.speed);form.addRow("Timing offset (seconds)",self.offset)
        self.translation=QtWidgets.QCheckBox("Include source local translation (for root / body routes)");layout.addWidget(self.translation)
        self.translation_scale=number(1,.001,1000);form.addRow("Translation scale",self.translation_scale)
        button(layout,"Add selected source chain → target group",self.add_route)
        self.list=QtWidgets.QListWidget();self.list.setMinimumHeight(150);layout.addWidget(self.list)
        row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        button(row,"Remove route",self.remove_route);button(row,"Save routes in scene",self.save);button(row,"Load scene routes",self.load)
        form=QtWidgets.QFormLayout();layout.addLayout(form)
        self.start=number(cmds.playbackOptions(query=True,minTime=True));self.end=number(cmds.playbackOptions(query=True,maxTime=True))
        form.addRow("Bake start",self.start);form.addRow("Bake end",self.end)
        self.dense=QtWidgets.QCheckBox("Bake every frame");self.dense.setChecked(True);layout.addWidget(self.dense)
        note(layout,"With every-frame baking off, select target control keys in the Graph Editor. Sparse baking preserves those sample times; motion between them may differ.")
        row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        button(row,"Create baked preview",self.make_preview);button(row,"Keep preview",self.keep);button(row,"Discard preview",self.discard)
        button(layout,"Bake composed mocap",self.bake)
        self.status=note(layout,"Reference poses should describe the same anatomical stance. Inspect shoulder alignment and contacts before keeping the result.")
        layout.addStretch();self.refresh()

    def refresh(self):
        current=self.rig.currentText();self.rig.clear();self.rig.addItems(rigging.rigs());self.rig.setCurrentText(current);self.rig_changed()

    def rig_changed(self,*args):
        self.module.clear();self.routes=[]
        if self.rig.currentText():
            data=rigging.rig_data(self.rig.currentText())
            for m in data["modules"]:self.module.addItem(m["id"],m["id"])
            for role in ("pelvis","spine","chest","neck","head"):
                ident=data["roles"].get(role)
                if ident:self.module.addItem("Body: "+role,"joint:"+ident)
            root=min(data["controls"],key=lambda n:data["controls"][n]["depth"])
            self.module.addItem("Root","joint:"+root)
            self.routes=mocap.load_routes(self.rig.currentText())
        self.show_routes()

    def import_fbx(self):
        path,_=QtWidgets.QFileDialog.getOpenFileName(self,"Import performer","","FBX (*.fbx)")
        if path:
            result=rigging.import_fbx(path);self.status.setText("Imported "+result["namespace"]+". Select its source limb joints.")

    def add_route(self):
        route=mocap.make_route(self.rig.currentText(),self.module.currentData(),selected_joints(),self.reference.value(),self.source_start.value(),self.target_start.value(),self.source_end.value(),self.speed.value(),self.offset.value(),translate=self.translation.isChecked(),translation_scale=self.translation_scale.value(),label=self.label.text())
        mapping.validate_routes(self.routes+[route]);self.routes.append(route);self.save();self.show_routes()

    def show_routes(self):
        self.list.clear()
        for route in self.routes:self.list.addItem(route["label"]+" → "+route["module"]+" | "+str(route["speed"])+"×, "+str(route["offset_seconds"])+" s")

    def remove_route(self):
        row=self.list.currentRow()
        if row>=0:self.routes.pop(row);self.save();self.show_routes()

    def save(self):mocap.save_routes(self.rig.currentText(),self.routes)
    def load(self):self.routes=mocap.load_routes(self.rig.currentText());self.show_routes()

    def create(self,preview):
        if self.preview and cmds.objExists(self.preview):raise ValueError("Keep or discard the current preview first.")
        keys=cmds.keyframe(query=True,selected=True,timeChange=True) or []
        layer=mocap.bake(self.rig.currentText(),self.routes,self.start.value(),self.end.value(),self.dense.isChecked(),keys,preview)
        self.status.setText("Created "+layer+". The animation no longer depends on the performer skeletons.")
        return layer

    def make_preview(self):self.preview=self.create(True)
    def bake(self):self.create(False)
    def keep(self):mocap.finish_preview(self.preview);self.preview=None
    def discard(self):mocap.discard_preview(self.preview);self.preview=None
