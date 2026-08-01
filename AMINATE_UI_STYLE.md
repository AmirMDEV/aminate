# Aminate UI style contract

Aminate is a compact animation workbench inside Maya. It must not look like
the Aminate tutorial website, a marketing landing page, or a generic card
dashboard. This contract is scoped to Aminate and never changes Maya's global
palette.

## Visual thesis: graphite workbench

- Match Maya's dense, neutral, professional chrome.
- Let the scene and the animator's actions stay visually louder than the tool.
- Use shallow surface changes, spacing, alignment, type weight, and disclosure
  to build hierarchy.
- Use colour only for selection, status, danger, and the one primary action in
  a functional region.
- Never use a coloured border, rail, underline, glow, or perimeter as identity.
- Never colour-code whole tools. Manifest accent colours remain available for
  icon artwork, not panel chrome.

## Navigation

The searchable Tool combo is Aminate's one navigation surface. The internal
`QTabWidget` is only a page stack; its 23-tab strip stays hidden at every
width. This avoids a website-like tab row and preserves working space in a
narrow dock.

## Tool header and help

Each tool starts with:

1. a plain title,
2. a small Help disclosure,
3. the working controls.

Help is collapsed by default. When opened, its explanation, three-step flow,
and tutorial link sit in one neutral tonal well. Do not nest another bordered
card inside it. The working controls must begin near the top of the dock even
for a first-time user.

## Themes

The Customization tab exposes two stable, root-scoped choices:

- `Maya Graphite` is the default and sits close to Maya's native dark chrome.
- `Studio Contrast` deepens surface separation for bright or high-glare
  displays.

Both are neutral. Neither uses per-tool colours or accent borders. Old saved
`Material Dark` and `Toolkit Spectrum` optionVar values migrate to the
corresponding new theme automatically.

## Semantic tokens and control hierarchy

`AMINATE_UI_TOKENS` is the source of truth.

- `background`, `surface`, `surface_alt`, and `surface_raised` form a shallow
  graphite elevation scale.
- `primary_container`, `primary_hover`, and `primary_pressed` are restrained
  slate fills for the single primary action.
- `success`, `warning`, and `error` are status-only semantic colours.
- ordinary buttons are neutral and compact;
- destructive actions remain separated and use the error container;
- focus, hover, pressed, checked, selected, and disabled states stay visible
  without a bright accent outline.

The fixed bottom bar uses the same graphite surfaces, neutral edges, rounded
corners, and slate selected fill as the main workbench. Individual icon colours
remain inside the artwork. They never become tile underlines, borders, glows,
or hover-card frames.

Text and interactive states must meet the relevant WCAG contrast target. A
disabled control may use reduced contrast because it is unavailable.

## Creator and donation identity

Aminate is free. Keep `Made by Amir · followamir.com ↗` and the canonical
yellow `Donate` action directly visible in the footer. Do not hide them in a
submenu. The URL must read as a link through clear text, underline, pointing
cursor, keyboard access, and an external-link cue. Keep the yellow action
compact and secondary to the animation workflow; never expand it into the old
full-width marketing banner.

## Responsive rules

- Prove 360, 520, 900, 1180, and 1600 px widths.
- The Tool picker, current tool title, working controls, status, creator link,
  version, and Donate action must survive resizing.
- Layouts may reflow and scroll vertically. They must not create horizontal
  scroll, clip button text, overlap controls, or shrink the global font.
- Full-width actions are allowed only when the action genuinely needs the
  width. Prefer compact rows and content-sized secondary actions.
- Help remains collapsed by default at every width.

## Forbidden regressions

- No website-style tab strip, hero block, feature card, or marketing footer.
- No cyan-accent clone of the tutorial site.
- No per-tool rainbow palette.
- No accent borders, rails, underlines, or full-perimeter identity frames.
- No giant help card before the working controls.
- No hidden creator or donation link.
- No removal or renaming of existing callbacks or user behavior as a styling
  shortcut.
- Source and release-package runtime mirrors must remain byte-identical.
