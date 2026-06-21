# Aminate Branding Style Guide

## Brand Feeling

Aminate should feel like a friendly animation companion inside Maya: fast, helpful, playful enough to be memorable, and still professional enough for production work.

## Core Icon

Primary icon:

- `branding/icons/aminate/aminate-pet-icon-source.png`
- App/shelf runtime icon: `maya_anim_workflow_tools_icon.png`
- Export sizes: `branding/icons/aminate/aminate-pet-icon-1024.png`, `512`, `256`, `128`, `64`, and `32`

The mascot is a keyframe-diamond animation pet. It should stay centered on a dark rounded tile, with cyan and amber glow accents and a visible timeline/keyframe motif.

Current official icon:

- `branding/icons/aminate/options/2026-05-08-lower-glow/aminate-icon-option-05-curve-companion-official-source.png`

This calmer option is the official Aminate shelf/app mark. It uses a simpler rounded companion shape, lower glow, and curve-handle animation language.

## Runtime Icon Archive

All current shipped runtime icons are mirrored under:

- `branding/icons/runtime/`

The generated toolbar source sheet is archived under:

- `branding/icons/generated-sheets/toolkit-toolbar-icon-sheet-2026-05-08.png`
- `branding/icons/generated-sheets/toolkit-toolbar-icon-sheet-app-style-readable-2026-05-08.png`

The current readable app-style toolbar crops and their size variants are under:

- `branding/icons/toolbar/2026-05-08-app-style-readable/`

The previous toolbar runtime icon set is preserved under:

- `branding/icons/toolbar/previous-toolbar-icons-before-app-style-readable/`

The previous Aminate shelf icon is preserved under:

- `branding/icons/aminate/maya_anim_workflow_tools_icon-previous.png`

## Visual Rules

- Use dark charcoal rounded square tiles.
- Use cyan as the primary glow and amber as the action/keyframe accent.
- Keep silhouettes readable at 32 px.
- Prefer simple animation language: keyframes, arcs, timelines, handles, curves, pivots.
- Avoid text inside icons.
- Avoid realistic animals, clutter, heavy shadows, stock-style imagery, or one-off color palettes.
- Icons should read clearly without relying on labels.

## Palette

- Background charcoal: `#0B1114`
- Panel charcoal: `#121A1F`
- Cyan glow: `#55E6FF`
- Amber glow: `#FFC44D`
- Soft white highlight: `#F4FBFF`
- Muted line gray: `#66727C`

## Icon Production Notes

- Generate master art large, then downscale to 512, 256, 128, 64, and 32 px.
- Keep the 256 px PNG as the Maya shelf/app runtime icon unless Maya needs a smaller asset.
- Keep the shelf/app icon text-free. Do not use Maya `imageOverlayLabel` text on the Aminate shelf button.
- Keep the shelf/app icon outer background transparent. Do not ship the white frame/corner fill around the rounded tile.
- For Toolbar icons, archive generated sheets and crop final runtime icons into standalone PNGs.
- Toolbar icons must stay readable at 24 px. Prefer large silhouettes, simple teal/amber forms, transparent outer corners, and no tiny text.
- Do not overwrite previous major brand assets without keeping a dated or clearly named archive copy in `branding/icons/aminate/`.
- When evaluating options, save the full option sheet plus cropped per-option PNGs before replacing the runtime icon.

## Current ImageGen Prompt

```text
Create a friendly animation pet-like icon for Aminate, matching the existing dark neon toolbar icon style: rounded dark charcoal square tile, cyan and warm amber glow line art, polished glossy UI icon, very obvious it represents animation and helpful assistant energy.

Subject: a cute small animation companion pet, like a soft rounded mascot made of a bouncing keyframe diamond body with tiny friendly eyes, small ears or antennae, a wagging tail shaped like a motion arc, and a tiny timeline/keyframe motif.

Style: high-end 3D/2D hybrid app icon, clean vector-like line art rendered as bitmap, neon cyan and amber accents, dark rounded tile, same style family as the combine meshes and toolbar icons.

Constraints: no text, no letters, no watermark, readable at 32 px and 64 px, no realistic animal, no clutter.
```
