# Toolbar hotfix audit

Base: public `main` commit `45aeb4d73040aabe1d1a3d556651fb13b9c58a69` (v0.3.7).
Status: source candidate, not a verified Maya release.

## Findings fixed

- The one-click ZIP action constructed a new ReferencePackageController on each click. Reference Manager therefore could not see its last_result. Aminate now supplies the same controller to the timing tool and Reference Manager. Standalone timing controllers retain their own package controller between clicks.
- ZIP archives are created alongside the unpacked package directory. Both folder-opening paths now prefer the directory containing the ZIP.
- Reference Manager overwrote its ZIP completion message with dependency-refresh status. Completion now remains visible, including missing-file and package warnings. Opening a nonexistent output folder now reports an actionable message.
- Failed Bake on Twos closed the undo chunk in both except and finally. It now closes once.

These findings do not establish that every reported unresponsive button is fixed. No live Maya session, failing-scene reproduction, or Qt click test was available.

## Routing audit

| Controls | Expected behaviour | Evidence / remaining check |
| --- | --- | --- |
| -1 / +1 | Move selected Graph Editor keys, otherwise keys on selected controls | Both command routes tested; Maya key edits still require live QA |
| In / Cut | Insert an unkeyed current-frame key / remove current-frame keys | Routes checked; Maya evaluation still requires live QA |
| Tween | Open percentage popup | All three toolbar _run implementations tested with popup stub |
| Zero | Reset settable translate/rotate to 0, scale to 1 | Route checked; locked-channel and Auto Key behaviour needs Maya |
| 2s | Bake playback range every two frames | Route and failed-bake undo regression tested |
| Anim / Clean | Select animated transforms / clean static curves on selected controls | Routes checked; layer-connected curves need live QA |
| Combine / Freeze / Pivot | Combine meshes, freeze and enter pivot edit mode | Route checked; mesh operations need Maya |
| ZIP | Save and package scene plus dependencies, open ZIP directory | Shared-controller routing tested; real archive built with mocked Maya access |
| Playblast | Save full-scale 1080p AVI | Route checked; viewport and codec availability require Maya |
| Selected Animation FBX | Open export options | All three toolbar _run implementations tested with exporter stub |
| 23 workflow icons | Open the corresponding tab | Every manifest alias resolves to a real tab; actual show/dock lifecycle needs Maya |
| Game Animation Mode | Toggle configured scene defaults and sync button state | Signal and handler inspected; actual scene changes need Maya |
| Layer controls | Create/delete, add/remove selection, mute/solo/lock/weight | Signals and controller targets inspected; interactive operations need Maya |
| History strip | Snapshot, restore and branch actions | Separate history subsystem; not runtime-tested by this hotfix |

All three action-button builders bind command values as lambda defaults; workflow buttons similarly bind their tab values. The ZIP action and Reference Manager navigation icon are distinct: ZIP packages immediately, while Reference Manager opens options. Existing documented behaviour is retained.

## Verification

Run `python -m unittest discover -s tests -v` (eight tests), Python compilation and `git diff --check`.
Headless tests establish routing and the listed regressions only; they do not establish live Maya correctness.

## Required before release

Follow AMINATE_RELEASE_PROCESS.md. Its reliability/build/install tools are absent from the public repository; this environment also has no Maya GUI or installed runtime. No version bump, release tag or release archive is represented as verified here.

In Maya, test both the embedded and bottom bars on a saved scene with references, textures, audio and at least one missing dependency. Package from each bar, then open Reference Manager and its package folder; verify the same ZIP appears and missing-file warnings persist. Test unsaved-scene rejection, unwritable output, all workflow icons, timing actions, layer controls, History, Tween, FBX options and playblast. Finally complete the versioned drag-and-drop update and payload-parity gates before publishing the hotfix.
