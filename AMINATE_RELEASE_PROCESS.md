# Aminate Release Process

Follow this checklist for every Aminate release. Do not publish a release package until the drag-and-drop update path passes.

## Required Reliability Gate

Run the guarded gate before any package or Maya install work:

```powershell
py tools\aminate_reliable_change_gate.py --mode source
py tools\aminate_reliable_change_gate.py --mode package
```

Run the install mode only after the feature branch is merged into clean canonical `main`:

```powershell
py tools\aminate_reliable_change_gate.py --mode install
```

Install ordering is fixed: build package, prove tracked post-build cleanliness, check package-only parity, sync Maya 2026, then require installed-root parity. The installed root may legitimately be stale before sync. The package builder may change tracked files only under `release_package/aminate/`; any other tracked mutation fails the gate.

Use `--mode live-preflight` before GUI actions. The helper never launches, closes, reloads, or terminates Maya. It exists to stop stale packages, unsafe lifecycle edits, duplicate Maya instances, and false-positive static proof before release work begins.

Every source, package, and install gate executes `tools/aminate_reliable_change_gate_test.py`. Lifecycle review allows owned widget event filters only with exact removal cleanup, allows stored script jobs only with owned kill cleanup, and blocks native retained-dock `workspaceControl(..., visible=False)` or `close=True` calls.

## Non-Negotiable Install Rule

- A user updates Aminate by unzipping the release, opening the `aminate` folder, and dragging the versioned installer into the Maya viewport.
- The recommended installer must be versioned from `RELEASE_TAG`, for example `Aminate_v0_3_5_drag_this_file_into_Maya.py`.
- Keep the legacy installer `Aminate drag and drop this onto Maya viewport.py` in the package as a fallback.
- The installer must self-evict its dropped-file module from `sys.modules` after running, so Maya cannot reuse an older installer with the same filename.
- The parity gate must import every packaged installer and call `_load_manifest()` before upload, so undefined installer globals such as `MANIFEST_FILE_NAME` fail the release locally.
- The release package must include `manifest.json` at both locations:
  - `aminate/manifest.json`
  - `aminate/aminate_package/manifest.json`
- Both manifests must match `aminate_package_manifest.py` for `version`, `release_tag`, `installer_files`, `runtime_files`, and `static_dirs`.

## Build Gate

Run these from `C:\Users\Amir Mansaray\Documents\Github\maya-animation-tools` before any tag or GitHub Release change:

```powershell
py -m py_compile .\aminate_dragdrop_installer.py .\build_aminate_release_package.py .\aminate_package_manifest.py .\aminate_runtime_package_parity_static_test.py .\aminate_runtime_package_parity_unit_test.py
py .\aminate_runtime_package_parity_unit_test.py
py .\build_aminate_release_package.py
py .\aminate_runtime_package_parity_static_test.py --installed-root "C:\Users\Amir Mansaray\Documents\maya\2026\scripts\Aminate" --legacy-root "C:\Users\Amir Mansaray\Documents\maya\2026\scripts\AmirAminate"
py .\aminate_static_release_audit.py --max-age-days 60 --release-candidate v0.3.6 --installed-root "C:\Users\Amir Mansaray\Documents\maya\2026\scripts\Aminate" --legacy-root "C:\Users\Amir Mansaray\Documents\maya\2026\scripts\AmirAminate"
```

Update the `--release-candidate` value for the release being shipped.

## Maya GUI Gate

- Use one settled Maya GUI session where possible.
- Do not take over the user's physical mouse or keyboard.
- Prefer Maya command port, live bridge, shelf install helpers, Qt introspection, UI Automation reads, and screenshots.
- If a true manual drag is required, ask the user to drag the versioned installer while Codex monitors Maya state.
- Prove same-session update behavior: install or update from an older release, then drag the new versioned installer into the same Maya session and confirm the new runtime opens.
- Confirm Maya stays responsive after install, Aminate opens, and the Toolkit Bar docks to the bottom layout when enabled.

## Package Inspection Gate

Inspect the generated ZIP before upload:

- ZIP name matches `Aminate_<RELEASE_TAG>.zip`.
- ZIP root folder is `aminate`.
- `aminate/manifest.json` exists.
- `aminate/aminate_package/manifest.json` exists.
- Both installer files exist in `aminate/`.
- Runtime files match `RUNTIME_FILES`.
- Static folders from `STATIC_DIRS` are copied into the payload.
- `README.txt` tells users to drag the versioned installer, not the legacy one.
- The separate `Aminate_<RELEASE_TAG>_offline_tutorial.zip` contains `tutorial.html` and `docs/`; neither is included in the Maya installer ZIP.

The parity unit test and static parity test must catch any misplaced or stale manifest before release.

## Publish Gate

- Commit private repo changes.
- Push private repo.
- Sync public release-facing files and package payload.
- Commit public repo changes.
- Push public repo.
- Create or move private and public `vX.Y.Z` tags to the exact release commits.
- Upload or replace the GitHub Release asset with `gh release upload --clobber`.
- For a stable public release, edit the public GitHub Release so `isPrerelease` is false and the title does not contain `Beta`.
- Verify the uploaded asset digest against local `Get-FileHash`.
- Download the release asset into a clean temp folder and inspect the same manifest and installer layout again.

## Release Copy Gate

Public release notes must say:

- Aminate is the current public release.
- Install or update by unzipping the release and dragging the versioned installer into the Maya viewport.
- The legacy installer remains a fallback, but the versioned installer is the recommended path.
- Internal test harness detail stays out of public-facing copy unless it helps users install or understand current release limits.
- If the release includes new Pencil or reference-video workflows, say plainly that those features are in beta testing without labelling the release/version as beta.
