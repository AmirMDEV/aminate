# Aminate Wiki

This is the tracked Aminate feature wiki. It ships with the repo and the separate offline tutorial asset, so the private repo and public repo can point to the same feature map.

## Start Here

- Install: download the latest `Aminate_v0.3.7.zip`, unzip it, and drag `Aminate_v0_3_7_drag_this_file_into_Maya.py` into the Maya viewport.
- Main UI: Aminate opens as a stable floating Maya window. Maya 2026.2 dock requests use the floating fallback to avoid the reproduced native `Qt6Core.dll` crash.
- Safety rule: use the Maya GUI for final proof. Automated checks use command ports and Qt inspection, not physical mouse or keyboard takeover.
- Offline tutorial: download `Aminate_v0.3.7_offline_tutorial.zip` from the same release and open its `tutorial.html` for searchable screenshots, GIFs, videos, and button help.

## Feature Map

### Quick Start

Use this as the first page for students. It explains which tab to open and keeps the workflow inside the Aminate window.

### Toolkit Bar

Fixed non-movable controls at Maya's bottom edge for repeated animation jobs: key nudging, inbetween keys, Tween Machine, cut current-frame keys, zero pose, bake on twos, select animated controls, clean static curves, package zip, 1080p full-scale AVI Playblast to Documents, History Timeline strip, animation-layer controls, workflow navigation icons, and Game Animation Mode. Narrow windows scroll the layer and tool rows horizontally.

### Scene Helpers

Scene prep and review helpers: Auto Key, snap selected keys to frames, texture reload, game animation mode, render environment setup, camera presets, animation-layer tint, non-destructive layer duplication and consolidation, layer solo controls, floating Channel Box, floating Graph Editor, scene text notes, teacher-demo duplication, and toolbar-extra visibility behavior when Aminate hides.

### Reference Manager

Packages the current Maya scene plus references, textures, image planes, audio, Alembic/GPU caches, and a manifest into one zip. It can scan unknown Maya data and keeps the live scene safer by using copy-only packaging unless saving is explicitly selected.

### Dynamic Parenting

Switches props or controls between parents without visible pops. Core flow: add driven object, pick parent, snap if needed, switch to selected parent or world, fix jumps, delete picked switches, or delete all switches.

### Hand / Foot Hold

Locks planted hands or feet over a frame range on chosen world axes. The current robust flow saves named holds, toggles hold/original motion, updates ranges, deletes picked holds, and deletes all holds under a crash-health harness.

### Surface Contact

Keeps selected controls on a mesh surface, optionally following the surface normal. It supports loading selected controls and surfaces, setup checks, contact creation/update, refresh, keying state, turn on/off, delete selected, and delete all.

### Dynamic Pivot

Creates one bright temporary pivot marker so selected props and controls can rotate around a chosen contact point without changing Maya's real pivot. Use Create & Move Pivot, Move Pivot, Turn From Pivot, and Clear Pivot. Highlight a Time Slider range to bake the turn on every whole frame in that range. With no highlight, only the current frame is baked. Aminate adds unchanged guard keys one frame before and after the range so sparse animation curves stay put outside it. Move the same marker and apply again for a later range; earlier disjoint baked frames stay unchanged. The tutorial includes a real Amanda-rig GIF showing the baseline, Range A, the moved Range B pivot, and the reopened saved result.

### Universal IK/FK

Finds limb controls, saves switch profiles, and matches FK to IK or IK to FK at the current frame without a visible pop. Saved profiles are reused for repeat shots.

### Controls Retargeter (Face and Body)

Pairs source and target controls for body or face retargeting. It supports loading selections, pair-by-order, flexible auto-map by name, direct channel-value transfer by default, explicit maintain-offset behavior, baking, and reduction back to source keyframes.

### Control Picker

Scans almost any character or animal rig, groups controls from their hierarchy, names, body area and side, nests FK and IK below limbs and tails, and keeps Maya selection synchronized. Parent rows select every child; Ctrl/Shift combines groups; custom sets can mix controls or whole groups; manual reassignment fixes unusual naming; and the Front/Side visual map uses the rig's real control positions rather than a fixed humanoid template.

### Animators Pencil

Creates scene-native drawing marks, arrows, rectangles, ellipses, text, frame markers, camera notes, layers, keys, ghosts, cut/copy/paste/delete, and retime. `Start Drawing` from a normal viewport saves that angle as a fixed tagged `Pencil View` camera and creates its camera-specific layer. The compact `Saved Drawing Views` list switches the viewport and active layer back to any saved angle. Starting again from another normal view creates a second fixed camera and separate layer. New marks default to `Current frame only`; turn it off to hold a drawing. Pencil, Brush, Line, Arrow, Rectangle, and Ellipse show a live preview while dragging, and viewport-space shape construction keeps rectangles aligned to the box drawn on screen. Tool, RGB/swatches, size, percentage opacity, shape, and Eraser changes update the active viewport context without recreating it. Press `E` for partial or whole-stroke Eraser. Locked layers stay protected. All drawing controls, including Shape Library and Camera Notes, stay visible in one `Active Drawing` group instead of being repeated or hidden under Advanced Tools.

### Animation Assistant

Pose-balance tools for floor plane, centre-of-gravity control, feet, hands, and contact points. It draws support lines or filled support polygons and colors balance feedback based on whether the projected centre of gravity is inside the support area.

### Animation Styling

Spider-Verse-style animation helpers: held keys, stepped curves, selected-key holds, overlap warnings, auto-hold toggles, and cleanup for generated timeline warnings.

### History Timeline

ZBrush-style scene snapshots beside each Maya file. It supports manual Save Step, Save Milestone, branch tracking, protected milestones, custom auto-save rules, restore safety, per-scene history folders, a configurable 90-backup default cap, and security-prompt-safe restore flows. Turning on Game Animation Mode asks whether Auto History should run.

### Onion Skin

Shows past and future poses as translucent 3D ghosts. Use larger frame steps on heavy rigs for viewport speed.

### Rotation Doctor

Diagnoses and repairs rotation flips, gimbal-like curve issues, Euler jumps, sorted report rows, Use Best Fix, Fix Flips, Flip Current Key, and clear-preview behavior.

### Character Skinning

Cleans skinned mesh transforms and copies exact skinning for same-topology meshes. It supports one-source-to-many-targets and many-source-to-many-targets workflows, preserving influences and weights.

### Rig Scale

Creates export-safe scaled copies for game engines while leaving the original rig and skinning untouched. Use selected character, selected skeleton, scale multiplier, setup check, export copy, and cleanup.

### Video Reference

Places video or image reference in the scene for timing, tracing, and review. Current crash-health evidence covers the narrowed PNG tracing-card lane. MP4 proxying, audio import, drawing manager launch, and draw-tool activation should stay on isolated proof lanes before being counted as full action proof.

### Timeline Notes

Adds title/body notes to frames or ranges, draws colored note ranges on Maya's timeline, shows formatted translucent hover bubbles, reads notes at the current frame, and supports export/import/customization lanes.

### Smear Frames

Creates interactive smear-frame geometry from selected meshes. It supports static mesh output, Unreal morph targets, Unreal morph sequence/VAT style output, selected-vertex smear masks, selecting the last smear, viewport editing, visibility keys, and cleanup.

Step-by-step Amanda test:

1. Run `run_aminate_smear_frames_amanda_step_test.ps1`.
2. The test opens a sacrificial Maya GUI session with Amanda.
3. Step `bootstrap` opens Aminate to Smear Frames and duplicates Amanda `body_geo` as a disposable animated source.
4. Step `static_smear` creates a selected-vertex static smear mesh and checks matching topology, stored vertex metadata, component edit selection, and visibility keys.
5. Step `morph_smear` creates an Unreal morph-target smear and checks the edit target is unlocked, visible, and selected by component for viewport manipulation.
6. Step `vat_smear_cleanup` creates an Unreal morph-sequence/VAT smear, checks frame targets `1, 2, 3`, selects frame 3 vertices for editing, hides the non-active targets, then deletes the temporary verifier group.
7. The harness checks Maya process health and Windows crash events after the run.

### Customization

Central place for Aminate colors and presentation settings, including timeline highlight color, tooltip preview icon size, opacity, and wording mode.

## Release Evidence

The current completion gate is `aminate_goal_completion_gate.py`. It checks real Maya GUI reports, heavy-rig/performance reports, hotkeys, history restore, Amanda/Magpie rig preflights, and crash-health action harness reports.

For open/close crash regressions, use `aminate_open_close_cycle_verify.py`. It repeats close, direct reopen, and shelf reopen cycles in fresh Maya 2026, checks the installed module path, captures the Scene Helpers UI, exercises the animation-layer buttons, and rejects fresh crash events or a crash reporter.
