"""Run manually with PySide6: Qt-only construction and five-width screenshot audit.
Maya scene queries are mocked. This does not replace the live release gate.
Screenshots are written to /tmp/aminate-ui-previews.
"""
import os,sys,inspect,importlib,traceback
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from PySide6 import QtWidgets,QtCore
from unittest.mock import Mock
app=QtWidgets.QApplication([]); windows=[]; failures=[]
mods=['maya_contact_hold','maya_surface_contact','maya_dynamic_parenting_tool','maya_face_retarget','maya_rotation_doctor','maya_rig_scale_export','maya_animation_assistant','maya_animation_styling','maya_control_picker','maya_animators_pencil','maya_history_timeline','maya_video_reference_tool','maya_skinning_cleanup','maya_skin_transfer','maya_selected_animation_fbx_export','maya_onion_skin','maya_smear_frames','maya_timeline_notes','maya_reference_manager','maya_aminate_customization','maya_timing_tools','maya_floating_channel_box']
for name in mods:
 m=importlib.import_module(name)
 # A non-Maya Qt run: satisfy read-only queries needed during initial population.
 if getattr(m,'cmds',False) is None:
  m.cmds=Mock();m.cmds.objExists.return_value=False;m.cmds.ls.return_value=[];m.cmds.listRelatives.return_value=[];m.cmds.currentTime.return_value=1.;m.cmds.playbackOptions.return_value=24.;m.cmds.file.return_value='';m.cmds.optionVar.return_value=False;m.cmds.filterExpand.return_value=[];m.cmds.listConnections.return_value=[]
 for n,c in list(vars(m).items()):
  if not (inspect.isclass(c) and c.__module__==name and hasattr(c,'_build_ui') and 'maya_aminate_ui' in c._build_ui.__code__.co_names):continue
  try:
   kw={};sig=inspect.signature(c)
   if 'controller' in sig.parameters:
    factories=[v for k,v in vars(m).items() if inspect.isclass(v) and k.endswith('Controller') and v.__module__==name]
    kw['controller']=factories[0]() if factories else Mock()
   w=c(**kw);windows.append((name,w));w.resize(360,850);w.show();app.processEvents()
   print(name,n,'OK',w.width(),w.minimumSizeHint().width())
   for timer in w.findChildren(QtCore.QTimer):timer.stop()
   if name in ['maya_animators_pencil','maya_aminate_customization','maya_timing_tools','maya_reference_manager','maya_contact_hold']:
    os.makedirs('/tmp/aminate-ui-previews',exist_ok=True);w.grab().save('/tmp/aminate-ui-previews/'+name+'.png')
   w.hide()
  except Exception as e:failures.append((name,n,str(e)));print('FAIL',name,n,str(e));traceback.print_exc(limit=4)
assert not failures, failures

import maya_dynamic_parent_pivot as main
try:
 main.cmds=importlib.import_module('maya_contact_hold').cmds
 controller=main.AminateController()
 for attr in vars(controller):
  if attr.endswith('_controller') and getattr(controller,attr) is None:
   for name,panel in windows:
    candidate=getattr(panel,'controller',None)
    if candidate and attr.replace('_controller','') in name:
     setattr(controller,attr,candidate);break
 controller.timing_controller=importlib.import_module('maya_timing_tools').MayaTimingToolsController()
 controller.dynamic_parenting_controller=importlib.import_module('maya_dynamic_parenting_tool').MayaDynamicParentingController()
 controller.skinning_controller=importlib.import_module('maya_skinning_cleanup').MayaSkinningCleanupController()
 controller.surface_contact_controller=importlib.import_module('maya_surface_contact').MayaSurfaceContactController()
 w=main.AminateWindow(controller);windows.append(('main',w))
 for i in range(w.tab_widget.count()):
  ok=w._ensure_tab_content(i)
  assert ok, w._last_tab_error
  print('TAB', i, w.tab_widget.tabText(i), 'OK')
 w.resize(360,850);w.show();app.processEvents();w.grab().save('/tmp/aminate-ui-previews/main.png')
except Exception:
 traceback.print_exc()
 raise

from pathlib import Path
out=Path('/tmp/aminate-ui-previews/all');out.mkdir(exist_ok=True)
for width in (360,520,900,1180,1600):
 for i in range(w.tab_widget.count()):
  w.tab_widget.setCurrentIndex(i);w.resize(width,850);app.processEvents();app.processEvents()
  w.grab().save(str(out/('w%d-tab%02d.png'%(width,i))))
print('RENDERED',115)
