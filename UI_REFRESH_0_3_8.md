# Aminate 0.3.8 UI refresh

This is the next-version source candidate, including the earlier toolbar hotfixes. No GitHub release asset has been published from this environment.

| Tool | Updated UI |
| --- | --- |
| Quick Start | Animate, Fix motion, Draw feedback and Prepare/export shortcuts above the searchable tool list. |
| Toolkit Bar | Keys, Review and Scene action groups; saved favourite module icons; More tools menu. Both package icons remain visible and create ZIPs. |
| Scene Helpers | Scene setup, Animation, Teaching and Floating windows groups. Window shortcut and opacity settings are centralised in Customization. |
| Reference Manager | Create Scene ZIP is primary; destination and dependency list visible; packaging options and cleanup separate. Save-first popup for unnamed scenes and paths missing on disk. |
| Dynamic Parenting | Object, Parent and switch, Previous switches, More options. One Save Current Offset action routes to the selected row or picked parent. Keep-position behaviour is explicit; World remains directly accessible. |
| Hand / Foot Hold | Control/range, create/update, saved holds. Selected rows expose Update Hold; New hold clears the selection. |
| Surface Contact | Controls/surfaces, Create/Update Contact, saved contacts; collision options collapsed. |
| Dynamic Pivot | Place/reposition pivot, then rotate around it; range status visible. |
| Universal IK/FK | Saved switch and the two switch actions first; rig setup and advanced matching collapsed. |
| Controls Retargeter | Pair mapping, auto map and one Retarget action with all/selected saved pair scope. |
| Control Picker | Visual map opens by default; layout editing and rig setup are secondary. |
| Animator's Pencil | Drawing controls and layers first; drawing options, views/video, mark editing and animation separated. |
| Animation Assistant | Pose Balance labelled Preview; character/ground, contact points and separate calibration. |
| Animation Styling | Existing-key actions distinguished from automatic future holds; scene-wide stepped setting explicitly labelled. |
| History Timeline | Save Step, Save Milestone and Restore first; snapshot management, branches, storage and automatic saves separate. |
| Onion Skin | Use Selection, past/future counts and preview enabled toggle; appearance/performance secondary. Re-enabling restores callbacks. |
| Rotation Doctor | Analyse, findings and recommended/current-key fixes; advanced cleanup collapsed. |
| Character Skinning | Copy Skin Weights and Fix Mesh Transforms are separate tasks. |
| Rig Scale | Rig/size, create export copy, export; copy management secondary. |
| Video Reference | Media source, placement and create/update; reference options and Pencil actions grouped separately. |
| Timeline Notes | Labelled range/text/colour, Add Note and Save Changes; auto-update wording explicit; import/export secondary. |
| Smear Frames | Mesh/range, create/edit/finish, editing state; saved smears and export/delete groups. |
| Customization | Appearance, toolbar favourites, window shortcuts/opacity and tooltips; previews and existing reset actions retained. |
| Tween Machine | Compact slider, presets and percentage retained; Settings opens Customization. |
| Floating Channel Box | Pin selection and local opacity controls; refresh continues reading pinned controls. |
| Floating Graph Editor | Optional Outliner using existing native panes; cycle and Euler-flip actions remain adjacent. |
| FBX export | Output/range and inclusion summary visible; detailed options collapsed. |

## Validation

- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`: 29 passing tests. Covers existing toolbar routing and safety fixes plus save-first guards, installer manifest loading, Hold actions, retarget scope, offset routing, Onion callback restoration and toolbar preferences.
- `QT_QPA_PLATFORM=offscreen python tests/qt_layout_smoke.py`: 23 standalone Qt constructors and all 23 main pages construct; 115 renders across widths 360, 520, 900, 1180 and 1600. Narrow screenshots were visually reviewed and clipping in the main workflows corrected.
- Qt uses PySide6 with mocked Maya scene queries. These checks do not exercise Maya constraints, native editor pane rendering, actual scene evaluation, callback lifetime in Maya, or drag-and-drop updates.
- Version metadata, runtime module inclusion and both installer manifest loaders were checked. This is source-level validation, not packaged/installed parity.

## Remaining release gate

`AMINATE_RELEASE_PROCESS.md` requires the canonical reliability/build/package/install checks and same-session Maya GUI update test before any tag or GitHub Release. The public checkout does not contain the canonical build/gate scripts and this environment has no Maya session. Complete those existing gates on the authorised canonical workstation before merging/publishing the v0.3.8 assets. Do not treat mocked Qt evidence as live Maya proof.
