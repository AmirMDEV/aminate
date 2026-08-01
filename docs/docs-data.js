window.AMINATE_DOCS = {
  "sections": [
    {
      "id": "quick-start",
      "icon": "QS",
      "short": "Quick Start",
      "title": "Quick Start",
      "media": "assets/quick_start.png",
      "purpose": "The learner map for Aminate. Use it to decide which tab or button fits the animation problem in front of you.",
      "when": "A student has opened Aminate and needs the fastest route to the right tool.",
      "steps": [
        "Open the Quick Start tab in Aminate.",
        "Look at the animation problem you have right now: timing, a sliding foot, a missing file, or a note for your teacher.",
        "Pick the matching lesson in this guide and do one small test before changing a whole shot."
      ],
      "buttons": [
        "Open Tutorials + FAQ",
        "Tab arrows",
        "Donate"
      ],
      "tips": [
        "Keep this page open beside Maya during lessons so students can self-correct before asking for help."
      ],
      "before": "Have Maya open with Aminate visible. If this is your first time, start here before clicking lots of buttons.",
      "see": "You should know which tab to open next. You should also see the Aminate window stay open while you move between lessons.",
      "help": "If you feel lost, return here and choose only one problem. Do not press every button to see what happens.",
      "number": "01",
      "tabTitle": "Quick Start",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/quick_start.png",
          "title": "Quick Start screenshot"
        }
      ]
    },
    {
      "id": "toolkit-bar",
      "icon": "TB",
      "short": "Toolkit",
      "title": "Toolkit Bar",
      "media": "assets/toolkit_bar.png",
      "purpose": "A fixed row of quick animation controls at the bottom of Maya. It keeps your most-used keys, layers, exports, and Aminate tabs one click away.",
      "when": "You want to work quickly without hunting through Maya menus or opening another floating window.",
      "steps": [
        "Look at the little groups from left to right: History, Animation Layer, quick action icons, Aminate tab icons, then Game Animation Mode.",
        "Hover a button if you forget it. Aminate shows its name and a short explanation.",
        "Select the control or mesh that the button should work on.",
        "Try the button on one pose or a short frame range first.",
        "If Maya is narrow, scroll the Toolkit Bar sideways. The buttons stay large enough to click."
      ],
      "buttons": [
        "History Auto",
        "History Timeline",
        "Animation Layer menu",
        "+ Layer",
        "Delete Layer",
        "+ Selection",
        "- Selection",
        "Mute",
        "Solo",
        "Lock",
        "Layer Weight",
        "Nudge Left",
        "Nudge Right",
        "Insert Inbetween",
        "Tween Machine",
        "Cut Current Key",
        "Reset Pose",
        "Bake On Twos",
        "Select Animated",
        "Clean Static Keys",
        "Combine Freeze Pivot",
        "Package Scene",
        "Playblast 1080p AVI",
        "Export Selected Animation FBX",
        "23 Aminate tab buttons",
        "Game Animation Mode"
      ],
      "tips": [
        "The blue selected icon tells you which Aminate tab is open. That is a state cue, not a coloured border around the whole button."
      ],
      "before": "Save the scene. Put the Time Slider on the frame you want and select only the controls or meshes you mean to change.",
      "see": "The button gives a short status message, the correct pose or file changes, and the Toolkit Bar stays fixed at Maya's bottom edge.",
      "help": "If nothing happens, check the selection and frame. If the bar looks cut off, scroll it sideways instead of shrinking Maya's buttons.",
      "subsections": [
        {
          "title": "History and animation layers",
          "intro": "These controls protect versions and organise animation without changing the character rig.",
          "items": [
            ["History Auto", "When this is on, Aminate can make History Timeline checkpoints while you work. Turn it on only when you want automatic snapshots."],
            ["History Timeline", "Open the list of saved checkpoints so you can compare or restore an earlier scene state."],
            ["Animation Layer menu", "Choose which Maya animation layer you are editing."],
            ["+ Layer / Delete", "Make a new animation layer, or delete the chosen layer. Delete affects the layer, so check its name first."],
            ["+ Selection / - Selection", "Add selected controls to the layer, or remove them from it."],
            ["Mute / Solo / Lock", "Mute hides a layer's effect. Solo shows only that layer. Lock stops accidental changes."],
            ["Layer Weight", "Choose how strongly the layer changes the final pose. 0 means no effect; 1 means full effect."]
          ]
        },
        {
          "title": "Quick action icons",
          "intro": "These buttons change keys, poses, meshes, packages, or exports.",
          "items": [
            ["Nudge Left / Nudge Right", "Move selected keys exactly one frame earlier or later."],
            ["Insert Inbetween", "Add a new key on the frame where the Time Slider is standing."],
            ["Tween Machine", "Blend between the key before and the key after. 0% copies the first; 100% copies the next; 50% is halfway."],
            ["Cut Current Key", "Remove keys only on the current frame for the selected controls."],
            ["Reset Pose", "Set selected controls to translate 0, rotate 0, and scale 1. If Auto Key is on, the reset is keyed."],
            ["Bake On Twos", "Bake selected controls over the visible playback range with a key every two frames."],
            ["Select Animated", "Find and select transforms in the scene that already have animation curves."],
            ["Clean Static Keys", "Remove animation curves whose keyed value never changes."],
            ["Combine Freeze Pivot", "Join selected meshes, freeze transforms, and enter Maya's Edit Pivot mode."],
            ["Package Scene", "Save the scene and collect references, textures, image planes, audio, and caches into a zip."],
            ["Playblast 1080p AVI", "Make a 1920x1080 AVI of the visible playback range in your Documents folder."],
            ["Export Selected Animation FBX", "Export only what you selected. It keeps the original source keyframe times by default, with an explicit optional whole-frame resampling checkbox, and leaves cameras and lights off by default."]
          ]
        },
        {
          "title": "Aminate tab buttons and Game Mode",
          "intro": "The small workflow icons jump to every Aminate tab. The separate Game button changes useful Maya scene settings for game animation.",
          "items": [
            ["23 workflow icons", "Quick Start, Toolkit Bar, Scene Helpers, Reference Manager, Dynamic Parenting, Hand / Foot Hold, Surface Contact, Dynamic Pivot, Universal IK/FK, Controls Retargeter, Control Picker, Animators Pencil, History Timeline, Onion Skin, Rotation Doctor, Character Skinning, Rig Scale, Video Reference, Timeline Notes, Smear Frames, Customization, and the other current Aminate workflow tabs."],
            ["Game Animation Mode", "Turns on the game setup choices selected in Scene Helpers. Read the Game Animation Mode subsection below before using it."]
          ]
        }
      ],
      "number": "02",
      "tabTitle": "Toolkit Bar",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/toolkit_bar.png",
          "title": "Toolkit Bar screenshot"
        },
        {
          "type": "image",
          "src": "assets/tween_machine.gif",
          "title": "Tween Machine GIF"
        }
      ]
    },
    {
      "id": "scene-helpers",
      "icon": "SH",
      "short": "Scene",
      "title": "Scene Helpers",
      "media": "assets/scene_feedback_text.gif",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/scene_feedback_text.gif",
          "title": "Feedback text GIF"
        },
        {
          "type": "video",
          "src": "assets/render_environment.mp4",
          "title": "Render environment tutorial",
          "poster": "assets/scene_helpers.png"
        },
        {
          "type": "image",
          "src": "assets/render_environment.gif",
          "title": "Render environment GIF"
        },
        {
          "type": "video",
          "src": "assets/game_animation_mode.mp4",
          "title": "Game Animation Mode tutorial",
          "poster": "assets/student_timeline_bar.png"
        },
        {
          "type": "image",
          "src": "assets/game_animation_mode.gif",
          "title": "Game Animation Mode GIF"
        }
      ],
      "purpose": "A set of small helpers for blocking, timing, game setup, render cameras, recovery, animation layers, floating editors, and notes that live inside the Maya scene.",
      "when": "The scene needs safer setup, cleaner timing, a quick game-preview configuration, or feedback that should travel with the Maya file.",
      "steps": [
        "Choose one subsection: Blocking & Timing, Scene Setup, Scene Notes, or Help.",
        "Read the tick box beside a tool. A tick means that choice will be included when the main button runs.",
        "Select the controls or rig if that helper needs a selection.",
        "Run one helper, then look at Maya's status message and the visible result.",
        "Undo or use the matching remove button when the result is not what you wanted."
      ],
      "buttons": [
        "Auto Key",
        "Auto Snap To Frames",
        "Game Animation Mode",
        "7 Game Mode tick boxes",
        "Snap Selected Keys To Frames",
        "Key Full Blocking Poses",
        "Translation",
        "Rotation",
        "Other keyable attributes",
        "Retime Every N Frames",
        "Animation Layer Tint",
        "Keep Toolbar Extras On Aminate Hide",
        "Load Textures",
        "Open Last Autosave",
        "Disable Maya Security Popups",
        "Set Up Render Environment",
        "Delete Render Environment",
        "Teacher Demo tools",
        "Camera Preset and offsets",
        "Tween Machine hotkey and opacity",
        "Floating Channel Box",
        "Floating Graph Editor",
        "Create Text Note",
        "Auto Wrap",
        "Key On",
        "Key Off",
        "Move To Selected",
        "Apply Style",
        "Delete Note"
      ],
      "tips": [
        "A tick box is a promise: when it is ticked, that setting is included; when it is empty, Aminate leaves that setting alone."
      ],
      "before": "Save the scene. Select the control or object that your note or helper belongs to.",
      "see": "You get one clear result: keys snap, a camera setup appears, Game Mode turns on, a floating editor opens, or a text note appears beside the character.",
      "help": "If the wrong thing changes, undo once and check the selection and tick boxes. Empty tick boxes tell Aminate to leave that part alone.",
      "subsections": [
        {
          "title": "Game Animation Mode",
          "intro": "This is a setup button, not an animation style. It applies only the choices that are ticked.",
          "items": [
            ["30 fps", "Changes Maya's time unit to 30 frames per second, which is common for games."],
            ["Realtime", "Makes Maya try to play the animation at its real speed instead of racing through every frame."],
            ["Update All Views", "Makes Maya refresh every viewport while the animation plays."],
            ["Autosave", "Turns on Maya autosave and keeps five backup files."],
            ["Activate Focused Viewport", "Makes the viewport you are working in the active viewport."],
            ["Load Textures", "Refreshes and repaths texture files that already exist on the computer."],
            ["Weighted Tangents", "Converts animation curves to weighted tangents so handles can have different lengths."],
            ["Important: turning Game Mode off", "The button stops showing as active, but it does not undo the Maya settings it already changed. Change those settings manually if you want the old setup back."]
          ]
        },
        {
          "title": "Blocking and timing tick boxes",
          "intro": "These choices decide which animation channels the blocking helper keys.",
          "items": [
            ["Translation", "Tick this to key move X, Y, and Z on every shared blocking frame."],
            ["Rotation", "Tick this to key rotate X, Y, and Z on every shared blocking frame."],
            ["Other keyable attributes", "Tick this only when you also want scale, visibility, and unlocked custom controls keyed."],
            ["Auto Key", "When on, Maya adds keys when you change an already animated value."],
            ["Auto Snap To Frames", "When on, Aminate keeps timing changes on whole-number frames."],
            ["Animation Layer Tint", "Shows the active animation layer with a tint above Maya's Time Slider."],
            ["Keep Toolbar Extras On Aminate Hide", "Keeps the Toolkit Bar, Tween Machine, Floating Channel Box, and Floating Graph Editor visible when Aminate is hidden. Leave it empty if hiding Aminate should clear those helpers."]
          ]
        },
        {
          "title": "Blocking and editor buttons",
          "intro": "Use these after selecting the controls that should change.",
          "items": [
            ["Snap Selected Keys To Frames", "Moves selected keys from decimal times such as 12.4 to whole frames such as 12."],
            ["Key Full Blocking Poses", "Adds keys on the shared blocking frames using the Translation, Rotation, and Other tick boxes above."],
            ["Retime Every N Frames", "Spreads selected timing so each pose is the chosen number of frames apart."],
            ["Duplicate / Consolidate / Solo layers", "Copy the current layer, combine other layers into a safe muted copy, solo the current layer, or clear all solos."],
            ["Tween Machine", "Set its hotkey and transparency, then open the small inbetween slider near the cursor."],
            ["Floating Channel Box", "Set its hotkey and transparency, then open a small floating channel editor for the selected control."],
            ["Floating Graph Editor", "Set its hotkey and transparency, then open a floating Maya Graph Editor that avoids duplicates."]
          ]
        },
        {
          "title": "Scene setup and cameras",
          "intro": "These buttons build or remove scene helpers. They do not change the original character mesh.",
          "items": [
            ["Load Textures", "Ask Maya to refresh and repath texture files that are already available."],
            ["Open Last Autosave", "Open the newest Maya autosave after a crash or mistake."],
            ["Disable Maya Security Popups", "Turn off Maya's repeated script-security questions for trusted local work. Use this only when you understand the scene source."],
            ["Set Up / Delete Render Environment", "Build or remove Aminate's cyclorama, cameras, sky light, and bookmarks."],
            ["Duplicate / Delete Teacher Demo", "Make a separate demonstration copy of a rig, or remove every teacher-demo copy and its display layer."],
            ["Teacher Demo Edit Log", "See which teacher-demo edits were recorded."],
            ["Camera Preset / Switch View", "Choose Front, Side, or Three Quarter and look through that helper camera."],
            ["Height, Dolly, and Rig Copy offsets", "Move all helper cameras up/down, closer/farther, or offset the demo rig copy together."]
          ]
        },
        {
          "title": "Scene Notes and Auto Wrap",
          "intro": "Scene notes are real Maya text curves, so they save with the scene.",
          "items": [
            ["Text, colour, and size", "Type the note, choose a readable colour, and set how large it should appear."],
            ["Auto Wrap", "Tick this to split long text into several lines inside the width and height box."],
            ["Box W / Box H / Apply Box", "Choose the note's world-space box size and apply it."],
            ["Resize In Viewport", "Select the note's resize box so you can scale it directly in Maya."],
            ["Create Text Note", "Make the note beside the currently selected control or body part."],
            ["Key On / Key Off", "Make the note appear or disappear on the current frame."],
            ["Move To Selected", "Move an existing note beside a newly selected control."],
            ["Apply Style / Delete / Refresh", "Update the selected note's look, remove it, or rebuild the list of notes in the scene."]
          ]
        }
      ],
      "number": "03",
      "tabTitle": "Scene Helpers"
    },
    {
      "id": "reference-manager",
      "icon": "PK",
      "short": "Package",
      "title": "Reference Manager",
      "media": "assets/reference_manager.png",
      "mediaItems": [
        {
          "type": "video",
          "src": "assets/auto_package_zip.mp4",
          "title": "Auto package in zip tutorial",
          "poster": "assets/reference_manager.png"
        },
        {
          "type": "image",
          "src": "assets/auto_package_zip.gif",
          "title": "Auto package in zip GIF"
        },
        {
          "type": "image",
          "src": "assets/reference_manager.png",
          "title": "Reference Manager screenshot"
        }
      ],
      "purpose": "Collect a scene and every referenced file into one zip for hand-in, review, or transfer.",
      "when": "A shot relies on references, textures, image planes, audio, or caches that must travel with the scene.",
      "steps": [
        "Open Reference Manager and click Refresh Needed Files.",
        "Read the list. A green or complete row means Aminate found that file; a missing row needs fixing first.",
        "Leave the file groups you need checked, such as references, textures, audio, or caches.",
        "Click Package Scene To Zip and wait for the small manifest to finish.",
        "Open the zip in a temporary folder and check that the scene and its files travel together."
      ],
      "buttons": [
        "Refresh Needed Files",
        "Package Scene To Zip"
      ],
      "tips": [
        "The manifest inside the zip tells you what was copied and what Maya could not find."
      ],
      "before": "Save the Maya scene once. Make sure you know where the new zip file may be written.",
      "see": "A new zip appears with the scene, copied files, and a manifest that tells you what was found or missing.",
      "help": "If the zip is tiny or a file is missing, refresh again and fix the path before packaging. Packaging copies files; it does not repair a broken scene path.",
      "number": "04",
      "tabTitle": "Reference Manager"
    },
    {
      "id": "dynamic-parenting",
      "icon": "DP",
      "short": "Parent",
      "title": "Dynamic Parenting",
      "media": "assets/dynamic_parenting.png",
      "mediaItems": [
        {
          "type": "video",
          "src": "assets/dynamic_parenting.mp4",
          "title": "Dynamic Parent tutorial",
          "poster": "assets/dynamic_parenting.png"
        },
        {
          "type": "image",
          "src": "assets/dynamic_parenting.gif",
          "title": "Dynamic Parent GIF"
        },
        {
          "type": "image",
          "src": "assets/dynamic_parenting.png",
          "title": "Dynamic Parenting screenshot"
        }
      ],
      "purpose": "Switch props or controls between parents without visible pops.",
      "when": "A magazine, sword, phone, hand, or prop needs to follow different controls during a shot.",
      "steps": [
        "Click Add Object and choose the prop.",
        "Choose a hand, world, or other control, then click Pick Parent.",
        "Use Snap To Parent only if you want the prop to line up to that parent.",
        "Turn on Maintain Current Offset when the prop must not jump at the switch frame.",
        "At the right frame, click Switch to this Parent. Use World when the prop should let go."
      ],
      "buttons": [
        "Add Object",
        "Pick Parent",
        "Snap To Parent",
        "Switch to this Parent",
        "World",
        "Fix Jumps",
        "Delete Picked Switch"
      ],
      "tips": [
        "Leave Maintain Current Offset on when you want the object to keep its visible pose at the switch frame.",
        "Bake to Rig uses the original source keyframe times by default; choose Bake Frames only when dense whole-frame sampling is intentional."
      ],
      "before": "Pick the prop that changes hands, such as a phone, sword, or magazine. Have the possible parent controls ready.",
      "see": "The prop follows the new parent without a sudden jump. The switch is saved on the timeline so it plays the same way again.",
      "help": "A jump usually means the wrong parent or offset was saved. Undo, keep the current offset, and try the switch on a clean test frame.",
      "number": "05",
      "tabTitle": "Dynamic Parenting"
    },
    {
      "id": "hand-foot-hold",
      "icon": "HF",
      "short": "Hold",
      "title": "Hand / Foot Hold",
      "media": "assets/hand_foot_hold.png",
      "mediaItems": [
        {
          "type": "video",
          "src": "assets/foot_hold.mp4",
          "title": "Foot Hold tutorial",
          "poster": "assets/hand_foot_hold.png"
        },
        {
          "type": "image",
          "src": "assets/foot_hold.gif",
          "title": "Foot Hold GIF"
        },
        {
          "type": "image",
          "src": "assets/hand_foot_hold.png",
          "title": "Hand / Foot Hold screenshot"
        }
      ],
      "purpose": "Keep planted hands or feet locked on chosen world axes while the body keeps moving.",
      "when": "Foot sliding, hand contact, or one-axis travel needs a quick non-destructive hold.",
      "steps": [
        "Click Suggest Range, or enter the contact and lift frames yourself.",
        "Choose only the world axes that should stay still.",
        "Click Create / Update Hold and read the row that appears.",
        "Scrub through the hold. Use Use Hold to test it and Use Original Motion to compare.",
        "Update or delete the hold when the contact range changes."
      ],
      "buttons": [
        "Suggest Range",
        "Use Current For Contact Start",
        "Use Current For Lift End",
        "Create / Update Hold",
        "Use Hold",
        "Use Original Motion",
        "Delete Hold"
      ],
      "tips": [
        "Use fewer locked axes when the contact should still rotate or slide naturally in one direction."
      ],
      "before": "Pick the hand or foot control and find the first touch frame and the lift-off frame.",
      "see": "The foot or hand stays planted while the rest of the body moves. The hold row shows exactly which frames and axes are locked.",
      "help": "If the contact looks stiff, unlock an axis so it can slide or rotate naturally. A hold is a helper, not a promise that every footstep should be frozen.",
      "number": "06",
      "tabTitle": "Hand / Foot Hold"
    },
    {
      "id": "surface-contact",
      "icon": "SC",
      "short": "Surface",
      "title": "Surface Contact",
      "media": "assets/surface_contact.png",
      "purpose": "Clamp a selected control to a mesh surface and optionally follow the surface normal.",
      "when": "A hand, foot, wheel, or prop should stay on a moving or uneven surface.",
      "steps": [
        "Click Check Setup and read the short message before creating anything.",
        "Choose the closest-point or surface-normal options that fit the contact.",
        "Click Create / Update Contact.",
        "Turn the contact on or off at the frames where the hand, foot, or wheel touches.",
        "Click Key State to save the on/off change, then use Refresh Now only when you mean to solve the current frame again."
      ],
      "buttons": [
        "Check Setup",
        "Create / Update Contact",
        "Turn On Selected",
        "Turn Off Selected",
        "Key State",
        "Refresh Now"
      ],
      "tips": [
        "Use Refresh Now only when you intentionally want the current frame solved again."
      ],
      "before": "Pick the control that should touch something, then pick the mesh surface underneath it.",
      "see": "The selected control sits on the mesh instead of floating above or sinking through it. A keyed state lets contact start and stop.",
      "help": "If the control snaps to a strange place, check that you selected the mesh, not a group or locator. Fix the selection and run Check Setup again.",
      "number": "07",
      "tabTitle": "Surface Contact",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/surface_contact.png",
          "title": "Surface Contact screenshot"
        }
      ]
    },
    {
      "id": "dynamic-pivot",
      "icon": "PV",
      "short": "Pivot",
      "title": "Dynamic Pivot",
      "media": "assets/dynamic_pivot.png",
      "purpose": "Turn objects around a temporary pivot without changing the real Maya pivot.",
      "when": "A prop needs to rotate from a hinge, edge, hand point, or temporary contact point.",
      "steps": [
        "Click Create & Move Pivot to make one temporary marker for the selected controls.",
        "Click Move Pivot and place the marker on the hinge, edge, or hand point.",
        "Rotate the marker to choose the turn direction.",
        "Highlight a Time Slider range to turn every whole frame in it; with no highlight, only the current frame is used.",
        "Click Turn From Pivot, then move the same marker and apply again for a later range.",
        "Click Clear Pivot when the temporary turn is finished."
      ],
      "buttons": [
        "Create & Move Pivot",
        "Move Pivot",
        "Turn From Pivot",
        "Clear Pivot"
      ],
      "tips": [
        "Aminate adds unchanged guard keys one frame before and after the range so the rest of the animation stays put.",
        "Earlier baked ranges stay unchanged when a later disjoint range uses a moved marker. Clear the pivot after the move so later animation does not inherit stale helper objects."
      ],
      "before": "Pick the controls you want to turn. Save a History Timeline step before changing a long range.",
      "see": "Every whole frame in the highlighted range turns around the helper point. Frames outside that range and the real Maya pivot stay unchanged.",
      "help": "If the turn is backwards, undo, rotate or move the marker, and try again. To use a new pivot later, move the same marker, highlight the later frames, and click Turn From Pivot again.",
      "number": "08",
      "tabTitle": "Dynamic Pivot",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/dynamic_pivot.png",
          "title": "Real Amanda rig: bright temporary pivot at Range A"
        },
        {
          "type": "image",
          "src": "assets/dynamic_pivot_ranges.gif",
          "title": "Real Amanda rig: baseline, Range A, moved Range B, and reopened result"
        },
        {
          "type": "image",
          "src": "assets/dynamic_pivot_range_b.png",
          "title": "Real Amanda rig: the same pivot moved for Range B"
        }
      ]
    },
    {
      "id": "universal-ikfk",
      "icon": "IK",
      "short": "IK/FK",
      "title": "Universal IK/FK",
      "media": "assets/universal_ikfk.png",
      "purpose": "Find and save limb controls, then switch IK to FK or FK to IK without a pop.",
      "when": "An arm or leg changes mode mid-shot and needs clean keys around the switch.",
      "steps": [
        "Click Find From What You Picked and check the boxes Aminate fills in.",
        "Fix any FK or IK control that is wrong, then click Save Switch.",
        "Move to the frame where the animation should change mode.",
        "Click Switch FK -> IK or Switch IK -> FK.",
        "Scrub over the switch and compare the pose before and after it."
      ],
      "buttons": [
        "Find From What You Picked",
        "Save Switch",
        "Switch FK -> IK",
        "Switch IK -> FK"
      ],
      "tips": [
        "If auto-find guesses wrong, fix the boxes by hand once and save the switch profile."
      ],
      "before": "Pick the arm or leg controls and save a History Timeline step before a large switch.",
      "see": "The limb keeps almost the same pose while the keys change from one control system to the other.",
      "help": "If the pose pops, the saved control pair is incomplete. Pick the missing controls, save the switch again, and repeat on a test frame.",
      "number": "09",
      "tabTitle": "Universal IK/FK",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/universal_ikfk.png",
          "title": "Universal IK/FK screenshot"
        }
      ]
    },
    {
      "id": "retargeter",
      "icon": "RT",
      "short": "Retarget",
      "title": "Controls Retargeter (Face and Body)",
      "media": "assets/face_retarget.png",
      "purpose": "Copy source control animation onto target controls while matching the source's real first pose and keeping only the animator's original key times.",
      "when": "Two rigs use different control names but the motion should transfer by order or loose names.",
      "steps": [
        "Load Selected Source for the controls that already move.",
        "Load Selected Target for the controls that should receive the motion.",
        "Click Pair By Order for matching lists, or Auto Map By Name when names are clear.",
        "Read a few pair rows and fix any left/right mix-up before copying.",
        "Check that Match Source Starting Pose and Source Keyframes Only are shown.",
        "Retarget Selected Controls or Retarget All Controls, then scrub the target rig.",
        "At the first source key, check that a target which began in a T-pose now matches the source's ready pose.",
        "Open the Time Slider or Graph Editor and check that the target has keys only where the source had keys."
      ],
      "buttons": [
        "Load Selected Source",
        "Load Selected Target",
        "Pair By Order",
        "Auto Map By Name",
        "Retarget Selected Controls",
        "Retarget All Controls"
      ],
      "tips": [
        "Keep source and target lists in the same order for the most predictable transfer.",
        "The target's old T-pose is not used as the animation starting point.",
        "Aminate does not bake a key on every frame, so the transferred animation stays easy to edit."
      ],
      "before": "Have a source rig and a target rig in the scene. Select controls in a simple, known order.",
      "see": "The target matches the source pose on the first animated key, follows the source motion, and has no extra keys between the source keys. A pair list shows exactly which source drives each target.",
      "help": "If the target begins in its old T-pose, undo and make sure you used the repaired Match Source Starting Pose workflow. If it bends the wrong way, fix the pair row; Aminate cannot guess a missing or incorrectly paired control.",
      "number": "10",
      "tabTitle": "Controls Retargeter (Face and Body)",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/face_retarget.png",
          "title": "Controls Retargeter paired-control screenshot"
        },
        {
          "type": "image",
          "src": "assets/controls_retargeter_real_rigs.png",
          "title": "Real Magpie source and target rigs used for the retarget proof"
        },
        {
          "type": "image",
          "src": "assets/controls_retargeter.gif",
          "title": "Real copied-rig retarget motion at the three exact source key times"
        }
      ]
    },
    {
      "id": "control-picker",
      "icon": "CP",
      "short": "Picker",
      "title": "Control Picker",
      "media": "assets/control_picker.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/control_picker.gif",
          "title": "Real Dude rig scan, custom set, and Front and Side live maps"
        },
        {
          "type": "image",
          "src": "assets/control_picker_visual.png",
          "title": "Live visual picker built from the Dude rig's real control positions"
        },
        {
          "type": "video",
          "src": "assets/auto_selection_sets.mp4",
          "title": "Auto selection sets tutorial",
          "poster": "assets/control_picker.png"
        },
        {
          "type": "image",
          "src": "assets/auto_selection_sets.gif",
          "title": "Auto selection sets GIF"
        },
        {
          "type": "image",
          "src": "assets/control_picker.png",
          "title": "Nested FK and IK groups with clear multi-selection feedback"
        }
      ],
      "purpose": "Automatically turn almost any character or animal rig into clear selection groups.",
      "when": "You need to select a whole tail, one arm, only its FK controls, only its IK controls, or your own saved mixture without hunting through the viewport.",
      "steps": [
        "In Maya, click the highest group of the rig you want to use. This is normally the character's main control group.",
        "Click Scan Selected Rig. Aminate finds curve controls below that group and sorts them by hierarchy, body area, left or right side, and FK or IK mode.",
        "Open a group such as Body, Left Arm, or Tail. Click its name to select everything inside it. Hold Ctrl or Shift and click another group to add that group too.",
        "Open the FK or IK subgroup when a limb has both systems. Pick only the mode you are animating. Aminate stops Key All Attrs if one limb contains both FK and IK controls.",
        "Watch the selection summary. It tells you how many controls are selected, which groups were used, and whether FK and IK are mixed.",
        "To make your own set, select controls or whole groups, type a name such as Tail + Left Arm FK, then click Create / Update From Selection.",
        "To fix an unusual rig, select several controls, choose a destination in the group menu, and click Move Selected To Group.",
        "Open Visual and click Refresh Live Rig Map. Front uses the rig's real X/Y positions; Side uses Z/Y, so animals and unusual proportions are not forced onto a fixed human picture.",
        "Click or marquee the live-map buttons. Blue buttons with a white outline are selected, and Maya shows the same selection."
      ],
      "buttons": [
        "Scan Selected Rig",
        "Scan All",
        "Add Selected",
        "Remove Selected",
        "Move Selected To Group",
        "Create / Update From Selection",
        "Delete Custom Set",
        "Refresh Live Rig Map",
        "Key Selected Attrs",
        "Key All Attrs"
      ],
      "tips": [
        "Use the top group when you want every child, and the FK or IK subgroup when you only want one animation system.",
        "Ctrl or Shift adds another group without losing the first one.",
        "If an unusual control lands in the wrong place, move it manually once and save the layout.",
        "The live map uses real control positions instead of assuming every rig is a human."
      ],
      "before": "Save a copy of the scene, then select the rig's highest control group. You do not need to build every picker button by hand.",
      "see": "A nested picker appears. Arms, legs, tail, wings, face, and core are grouped; FK and IK sit below their limb; selected groups remain visibly highlighted; and the live map follows the rig's real shape.",
      "help": "If Aminate misses a control, select that control in Maya and click Add Selected. If it is in the wrong group, select it, choose the right group, and click Move Selected To Group. If a saved set points at deleted controls, rescan and update that custom set.",
      "number": "11",
      "tabTitle": "Control Picker"
    },
    {
      "id": "animators-pencil",
      "icon": "PN",
      "short": "Pencil",
      "title": "Animators Pencil",
      "media": "assets/animators_pencil.png",
      "purpose": "Draw arcs, contact notes, frame markers, and planning marks as scene objects.",
      "when": "You need visible animation notes that survive without the script installed.",
      "steps": [
        "Choose Pencil, Brush, Line, Arrow, Rectangle, or Ellipse, then click Start Drawing once.",
        "Draw a small mark and watch the radius cursor so you know the brush size.",
        "Use RGB + Swatches to choose a colour. Keep Current frame only on for a one-frame mark.",
        "Rename the layer and lock it when the notes should not be erased by accident.",
        "Use E for Partial Stroke or Whole Stroke erasing, then save the view when the angle is useful.",
        "Move to another camera angle and start again; Saved Drawing Views lets you return to either angle."
      ],
      "buttons": [
        "Start Drawing",
        "Saved Drawing Views",
        "Save Current View",
        "Switch",
        "RGB + Swatches",
        "Drawing Tools",
        "Shape Tools",
        "Rename"
      ],
      "tips": [
        "Each Pencil View has a separate camera layer. Current-frame drawing is the default. Locked layers cannot be erased. Camera Notes remains available for the older keyed review-camera workflow."
      ],
      "before": "Save the scene. Pick a normal camera angle and make one Pencil View before drawing a long note.",
      "see": "Your marks are scene objects in a camera-specific layer. They remain visible when you scrub and can be opened on another computer with the scene.",
      "help": "If a mark is missing, switch back to its Saved Drawing View and layer. A locked layer cannot be erased until you unlock it.",
      "number": "12",
      "tabTitle": "Animators Pencil",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/animators_pencil.png",
          "title": "Animators Pencil screenshot"
        }
      ]
    },
    {
      "id": "animation-assistant",
      "icon": "AA",
      "short": "Assist",
      "title": "Animation Assistant",
      "media": "assets/animation_assistant.png",
      "purpose": "Pose balance helpers for centre of gravity, floor plane, and contact points.",
      "when": "A pose feels unstable and needs a fast visual balance check.",
      "steps": [
        "Use Selected for the floor or centre-of-gravity control.",
        "Click Add Selected for each foot, hand, or other contact point.",
        "Click Refresh and watch the support area and balance badge.",
        "Move the pose a little and refresh again to compare.",
        "Clear the points when you start a different pose."
      ],
      "buttons": [
        "Use Selected",
        "Refresh",
        "Add Selected",
        "Remove Selected",
        "Clear"
      ],
      "tips": [
        "The badge is a guide, not a replacement for silhouette and acting decisions."
      ],
      "before": "Pick the floor or ground control and the controls that touch it. This is a balance hint, not a final acting decision.",
      "see": "The viewport shows a support area and a simple balanced or unbalanced badge.",
      "help": "If the badge says unbalanced, check the silhouette and acting too. The helper only measures the points you gave it.",
      "number": "13",
      "tabTitle": "Animation Assistant",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/animation_assistant.png",
          "title": "Animation Assistant screenshot"
        }
      ]
    },
    {
      "id": "animation-styling",
      "icon": "ST",
      "short": "Style",
      "title": "Animation Styling",
      "media": "assets/animation_styling.png",
      "purpose": "Apply held-key or stepped animation styling quickly.",
      "when": "A shot needs Spider-Verse-style stepped timing or clean held poses.",
      "steps": [
        "Choose how many frames a key should hold.",
        "Preview the warning list for overlaps before changing curves.",
        "Click Apply Hold to copy the values forward.",
        "Use Set all curves to stepped curves only when the whole shot wants stepped timing.",
        "Scrub the result and undo if the hold hides an important breakdown."
      ],
      "buttons": [
        "Apply Hold",
        "Set all curves to stepped curves"
      ],
      "tips": [
        "Check overlap warnings before applying holds across dense animation."
      ],
      "before": "Save a History Timeline step and select a small range of keys to test.",
      "see": "Keys hold for the chosen number of frames and the warning area points out collisions before they surprise you.",
      "help": "A hold can cover a key you meant to keep. Start with a small range and use the warning list as your map.",
      "number": "14",
      "tabTitle": "Animation Styling",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/animation_styling.png",
          "title": "Animation Styling screenshot"
        }
      ]
    },
    {
      "id": "history-timeline",
      "icon": "HT",
      "short": "History",
      "title": "History Timeline",
      "media": "assets/history_timeline.png",
      "purpose": "Scene restore points that are safer than relying on a long Maya undo chain.",
      "when": "Students need a return point before risky edits or a milestone before feedback changes.",
      "steps": [
        "Click Save Step for a quick checkpoint or Save Milestone for an important pose.",
        "Give the row a plain name such as blocking pass or before polish.",
        "Select the row or coloured history block you want to visit.",
        "Click Restore and read the safety message before confirming.",
        "Keep working; if you branch from an older step, the new work gets its own branch."
      ],
      "buttons": [
        "Save Step",
        "Save Milestone",
        "Restore"
      ],
      "tips": [
        "Restoring creates a safety snapshot first so the current state is not lost immediately."
      ],
      "before": "Save the scene. Use a new step before risky edits, not after the mistake.",
      "see": "A coloured history row appears and Restore returns the scene to that saved moment without deleting your current work first.",
      "help": "If a restore looks wrong, use the safety snapshot that Aminate made just before restoring. History is a safety net, not a replacement for saving the Maya file.",
      "number": "15",
      "tabTitle": "History Timeline",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/history_timeline.png",
          "title": "History Timeline screenshot"
        }
      ]
    },
    {
      "id": "onion-skin",
      "icon": "OS",
      "short": "Onion",
      "title": "Onion Skin",
      "media": "assets/onion_skin.png",
      "purpose": "Show past and future poses as see-through ghosts.",
      "when": "Arcs, spacing, contacts, and rhythm are hard to judge from the current frame alone.",
      "steps": [
        "Open Onion Skin and choose how many past and future poses to show.",
        "Keep the mode on 3D Ghost for the dependable Maya path.",
        "Click Attach Selected, then scrub the timeline.",
        "Change Frame Step if the ghosts are too busy or the rig feels slow.",
        "Click Clear when you no longer need the ghosts."
      ],
      "buttons": [
        "Attach Selected",
        "Frame Step",
        "Clear"
      ],
      "tips": [
        "Use larger frame steps on heavy rigs to keep the viewport responsive."
      ],
      "before": "Pick the rig or object you want to watch and save the scene if the rig is heavy.",
      "see": "See-through copies of past and future poses sit around the current pose, making spacing and arcs easier to compare.",
      "help": "Too many ghosts can slow a heavy rig. Use fewer ghosts or a larger frame step before doing more work.",
      "number": "16",
      "tabTitle": "Onion Skin",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/onion_skin.png",
          "title": "Onion Skin screenshot"
        },
        {
          "type": "image",
          "src": "assets/maya_onion_skin_demo.gif",
          "title": "Onion Skin GIF"
        }
      ]
    },
    {
      "id": "rotation-doctor",
      "icon": "RD",
      "short": "Rotate",
      "title": "Rotation Doctor",
      "media": "assets/rotation_doctor.png",
      "purpose": "Analyze and repair rotation flips, gimbal problems, and Euler key issues.",
      "when": "Rotations jump, spin the long way, or become hard to edit cleanly.",
      "steps": [
        "Click Analyze Selected and read each warning.",
        "Choose Use Best Fix for a safe broad repair, or choose Flip Current Key for one key.",
        "Scrub the repaired range and check the Graph Editor if the motion still looks odd.",
        "Undo and try a smaller selection when the report names a different control."
      ],
      "buttons": [
        "Analyze Selected",
        "Use Best Fix",
        "Flip Current Key"
      ],
      "tips": [
        "Save a History Timeline step before large curve repairs."
      ],
      "before": "Select only the animated controls with the rotation problem. Save a history step first.",
      "see": "The rotation curve no longer makes a surprise flip, and the report tells you what was checked.",
      "help": "Rotation fixes change keys. A History Timeline step makes it easy to go back if the artistic result is not right.",
      "number": "17",
      "tabTitle": "Rotation Doctor",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/rotation_doctor.png",
          "title": "Rotation Doctor screenshot"
        }
      ]
    },
    {
      "id": "character-skinning",
      "icon": "SK",
      "short": "Skin",
      "title": "Character Skinning",
      "media": "assets/character_skinning.png",
      "purpose": "Clean skinned mesh transforms and copy exact skinning for matching topology.",
      "when": "A skinned mesh has bad transform values or a duplicate mesh needs the same weights.",
      "steps": [
        "Click Check Selected Mesh and read the weights, influences, UVs, materials, and normals.",
        "Click Make Frozen Copy to create a clean backup candidate.",
        "Inspect the copy in the viewport and read its report.",
        "Click Replace Original only after the checks pass.",
        "Keep the hidden backup until you are sure the animation and materials still look right."
      ],
      "buttons": [
        "Check Selected Mesh",
        "Make Frozen Copy",
        "Replace Original",
        "Delete Frozen Copy",
        "Copy Selected Pair Now"
      ],
      "tips": [
        "The original mesh stays hidden as a backup after replacement, so students can recover if they picked the wrong mesh.",
        "Animated copies use the source's exact keyframe times, including fractional frames, rather than adding keys on every whole frame."
      ],
      "before": "Pick one skinned mesh. Do not replace the original until the green checks are clear.",
      "see": "The mesh keeps its skin and animation but has clean transform values. A hidden backup gives you a safe way back.",
      "help": "If a check is red, stop and fix that problem first. Replace Original is the one action in this lesson that should never be rushed.",
      "number": "18",
      "tabTitle": "Character Skinning",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/character_skinning.png",
          "title": "Character Skinning screenshot"
        },
        {
          "type": "image",
          "src": "assets/character_skinning_rig_scale_fix.gif",
          "title": "Character Skinning frozen-transform GIF"
        }
      ]
    },
    {
      "id": "rig-scale",
      "icon": "RS",
      "short": "Scale",
      "title": "Rig Scale",
      "media": "assets/rig_scale.png",
      "purpose": "Make an export-safe scaled copy for Unreal or another game engine.",
      "when": "The original rig must stay untouched but the exported copy needs a different scale.",
      "steps": [
        "Click Use Selected Character and confirm the character name.",
        "Click Use Selected Skeleton and confirm the joint root.",
        "Enter the size multiplier your game engine needs.",
        "Click Check Setup and fix any missing selection.",
        "Click Make Export Copy, then export the new group instead of the original."
      ],
      "buttons": [
        "Use Selected Character",
        "Use Selected Skeleton",
        "Check Setup",
        "Make Export Copy"
      ],
      "tips": [
        "Export the copied group, not the original rig.",
        "When the source has animation, the copy keeps only the unique original keyframe times, including fractional frames; it does not add a key on every frame."
      ],
      "before": "Choose the character and skeleton you want to export. Keep the original rig untouched.",
      "see": "A separate scaled group appears in the scene and the source rig stays as it was.",
      "help": "If the copy is the wrong size, delete the copy and make it again with a corrected multiplier. Never scale the original just to test an export.",
      "number": "19",
      "tabTitle": "Rig Scale",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/rig_scale.png",
          "title": "Rig Scale screenshot"
        }
      ]
    },
    {
      "id": "video-reference",
      "icon": "VR",
      "short": "Video",
      "title": "Video Reference",
      "media": "assets/video_reference.png",
      "purpose": "Place video or image-sequence reference in the scene for timing, tracing, or review.",
      "when": "A shot needs visual reference aligned with the Maya timeline.",
      "steps": [
        "Click Use Active View so the card opens in the camera you are looking through.",
        "Choose the video or image sequence and set the start frame.",
        "Choose whether the card should use an audio track.",
        "Click Make Tracing Card and scrub the timeline.",
        "Use Open Drawing Manager or Start Drawing when you want to draw over the reference."
      ],
      "buttons": [
        "Use Active View",
        "Use Selected Object",
        "Make Tracing Card",
        "Open Drawing Manager",
        "Start Drawing"
      ],
      "tips": [
        "Changing Start Frame after creation retimes the existing card."
      ],
      "before": "Have a video or image sequence and know the frame where it should start.",
      "see": "The reference lines up with the Maya timeline, and the tracing card stays in the chosen view while you animate.",
      "help": "If the timing is off, change Start Frame on the existing card instead of making a second card.",
      "number": "20",
      "tabTitle": "Video Reference",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/video_reference.png",
          "title": "Video Reference screenshot"
        }
      ]
    },
    {
      "id": "timeline-notes",
      "icon": "TN",
      "short": "Notes",
      "title": "Timeline Notes",
      "media": "assets/timeline_notes.png",
      "purpose": "Attach readable notes to frame ranges and see them while scrubbing.",
      "when": "Feedback, planning notes, or shot tasks need to live on the timeline.",
      "steps": [
        "Select the range in Maya's time slider.",
        "Type a short title and the full feedback note.",
        "Pick a colour that is easy to read.",
        "Click Add Note, then scrub through the range.",
        "Read or export the notes when you review the shot."
      ],
      "buttons": [
        "Add Note",
        "Export Notes"
      ],
      "tips": [
        "Use short titles so notes stay readable on the timeline strip."
      ],
      "before": "Highlight the frame range that the note belongs to and write the note in plain words.",
      "see": "A coloured range appears over the timeline and the note reader shows it at the matching frame.",
      "help": "Use a short title so the strip stays readable. The full note is still available when you hover or open the reader.",
      "number": "21",
      "tabTitle": "Timeline Notes",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/timeline_notes.png",
          "title": "Timeline Notes screenshot"
        }
      ]
    },
    {
      "id": "smear-frames",
      "icon": "SM",
      "short": "Smear",
      "title": "Smear Frames",
      "media": "assets/smear_frames.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/smear_frames.png",
          "title": "Smear Frames tab screenshot"
        },
        {
          "type": "image",
          "src": "assets/smear_frames_sculpt_closeup.png",
          "title": "Amanda's arm stretched by moving the smear mesh vertices"
        },
        {
          "type": "image",
          "src": "assets/smear_frames_sculpt_and_range.gif",
          "title": "The normal rig, the sculpted smear, then the normal rig again"
        }
      ],
      "purpose": "Take a snapshot of a moving mesh, stretch it into a smear, sculpt the exact vertices you want, save several smears in the Maya scene, choose when each appears, and export Unreal morph overlays.",
      "when": "A sword swing, fast punch, spinning limb, or other quick move needs a readable stretched drawing for one frame or a short frame range.",
      "buttons": [
        "Refresh Mesh And Saved Smears",
        "Create And Save Smear",
        "Saved Smear Frames",
        "Select Saved Smear",
        "Sculpt / Edit Vertices In Viewport",
        "Finish Editing",
        "Save Name And Frame Range",
        "Export All Unreal Smears",
        "Delete Selected Generated Smear"
      ],
      "tips": [
        "Use Unreal Morph Overlay for most smears. Maya Static Mesh is useful inside Maya, but it does not carry dependable on/off animation into Unreal."
      ],
      "steps": [
        "Move to the frame where the fast action needs a smear.",
        "Select the whole animated mesh, or select only the vertices you want to stretch.",
        "Type a clear Smear Name, such as Sword Swing Smear.",
        "Set Previous and Next Frame Offset to tell Aminate how far around the current frame it should look for motion.",
        "Start with a small Smear Strength such as 0.5.",
        "Set Visible From Frame and Visible Through Frame. Use the same number for a one-frame smear.",
        "Choose Unreal Morph Overlay and click Create And Save Smear.",
        "Choose the new item in Saved Smear Frames, then click Sculpt / Edit Vertices In Viewport.",
        "Move the selected vertices until the silhouette looks right from the game camera. Do not add or delete vertices because Unreal morph targets need the same topology.",
        "Click Finish Editing, then scrub before, inside, and after the saved range.",
        "Use Save Name And Frame Range whenever you rename the smear or change its timing.",
        "Click Export All Unreal Smears and choose a new folder. Aminate writes one FBX per smear, aminate_smears.json, an Unreal Python import helper, and simple import instructions."
      ],
      "before": "Save the scene and select one animated mesh. Do not change the mesh's vertex count while sculpting. The original rig and original mesh are never replaced.",
      "see": "The saved smear list remembers the name and frame range after saving and reopening Maya. The overlay shrinks too small to see when its morph weight is 0 and shows the sculpted smear when the curve becomes 1.",
      "help": "If the smear is too wild, undo and use smaller offsets or strength. If Unreal shows no morph, import the FBX as Skeletal Mesh with Import Animations and Import Morph Targets turned on.",
      "subsections": [
        {
          "title": "What Aminate saves",
          "intro": "Each saved item keeps enough information to return after the Maya scene is reopened.",
          "items": [
            ["Name and unique ID", "A human name for the list plus an internal ID so two smears can have similar names safely."],
            ["Source and sample frames", "The mesh Aminate sampled and the previous/current/next frames used to calculate motion."],
            ["Visible range", "The first and last frame where the smear should be on."],
            ["Editable target", "A topology-matching mesh whose vertices you can move with Maya's normal modelling tools."],
            ["Unreal carrier", "A one-joint skeletal overlay with blend shapes. Aminate remembers the source rig's scale, so a vertex you move by 3.5 cm stays a 3.5 cm edit. The joint shrinks the overlay almost to zero outside your chosen frames, then returns to the captured scale during the smear."]
          ]
        },
        {
          "title": "Why the Unreal export works",
          "intro": "FBX visibility animation is not a dependable way to turn a mesh on and off in Unreal, so Aminate uses morph curves instead.",
          "items": [
            ["Before the range", "Morph weight is 0, so the overlay shrinks too small for the player to see."],
            ["Inside the range", "Morph weight is 1, so the sculpted smear appears."],
            ["After the range", "Morph weight returns to 0 and the overlay disappears again."],
            ["FBX bundle", "The FBX contains geometry, one root joint, skinning, blend shapes, and baked animation. The JSON records FPS, units, axis, names, and ranges."],
            ["Unreal import", "Import as Skeletal Mesh with animations and morph targets. Play the smear overlay animation at the same time as the character animation."]
          ]
        }
      ],
      "number": "22",
      "tabTitle": "Smear Frames"
    },
    {
      "id": "customization",
      "icon": "CU",
      "short": "Custom",
      "title": "Customization",
      "media": "assets/customization.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/customization.png",
          "title": "Customization tab screenshot"
        }
      ],
      "purpose": "Tune Aminate's colours, labels, and small interface choices so the tool feels comfortable to use.",
      "when": "The tools work but the interface needs clearer contrast or a calmer personal setup.",
      "buttons": [
        "Apply Style",
        "Reset"
      ],
      "tips": [
        "Change one setting at a time and keep the most readable result."
      ],
      "steps": [
        "Choose Material Dark for the familiar blue hierarchy or Toolkit Spectrum for tool-coloured accents.",
        "Change one animation colour, icon size, opacity, or tooltip wording at a time.",
        "Click Apply Colors or Apply Tooltip Style.",
        "Open two or three Aminate tabs and check that the text, focus, and main action are still easy to see.",
        "Click Reset when the change makes the interface harder to read."
      ],
      "before": "Take a screenshot of the current look or remember the Reset button. Do not change every colour at once.",
      "see": "The selected Aminate accents update while neutral panels stay dark and readable. Reset returns the default choices.",
      "help": "If a colour hides text or makes a normal button look dangerous, reset it and choose a calmer colour with more contrast.",
      "number": "23",
      "tabTitle": "Customization"
    }
  ],
  "buttons": [
    {
      "label": "History Auto",
      "group": "Toolkit Bar — History",
      "tooltip": "Turn automatic History Timeline checkpoints on or off."
    },
    {
      "label": "History Timeline",
      "group": "Toolkit Bar — History",
      "tooltip": "Open saved scene checkpoints so you can compare or restore them."
    },
    {
      "label": "Animation Layer menu",
      "group": "Toolkit Bar — Layers",
      "tooltip": "Choose the Maya animation layer you are editing."
    },
    {
      "label": "+ Layer",
      "group": "Toolkit Bar — Layers",
      "tooltip": "Create a new Maya animation layer."
    },
    {
      "label": "Delete Layer",
      "group": "Toolkit Bar — Layers",
      "tooltip": "Delete the chosen animation layer after checking its name."
    },
    {
      "label": "+ Selection / - Selection",
      "group": "Toolkit Bar — Layers",
      "tooltip": "Add selected controls to the layer or remove them from it."
    },
    {
      "label": "Mute / Solo / Lock",
      "group": "Toolkit Bar — Layers",
      "tooltip": "Hide a layer's effect, show only that layer, or protect it from edits."
    },
    {
      "label": "Layer Weight",
      "group": "Toolkit Bar — Layers",
      "tooltip": "Set how strongly the chosen animation layer affects the final pose."
    },
    {
      "label": "-1",
      "group": "Toolkit Bar",
      "tooltip": "Move selected keys one frame earlier."
    },
    {
      "label": "+1",
      "group": "Toolkit Bar",
      "tooltip": "Move selected keys one frame later."
    },
    {
      "label": "In",
      "group": "Toolkit Bar",
      "tooltip": "Create an inbetween key on the current frame."
    },
    {
      "label": "Tween",
      "group": "Toolkit Bar",
      "tooltip": "Toggle the cursor-side Tween Machine percentage bar. The header shows the current percent while you drag."
    },
    {
      "label": "Cut",
      "group": "Toolkit Bar",
      "tooltip": "Remove keys on the current frame."
    },
    {
      "label": "Zero",
      "group": "Toolkit Bar",
      "tooltip": "Reset selected controls."
    },
    {
      "label": "2s",
      "group": "Toolkit Bar",
      "tooltip": "Bake selected controls every two frames."
    },
    {
      "label": "Anim",
      "group": "Toolkit Bar",
      "tooltip": "Select animated controls."
    },
    {
      "label": "Clean",
      "group": "Toolkit Bar",
      "tooltip": "Remove static curves."
    },
    {
      "label": "CFP",
      "group": "Toolkit Bar",
      "tooltip": "Combine selected meshes, freeze transforms, and enter Edit Pivot mode."
    },
    {
      "label": "Zip",
      "group": "Toolkit Bar",
      "tooltip": "Save and package the scene, references, textures, media, audio, and caches into a zip."
    },
    {
      "label": "PB",
      "group": "Toolkit Bar",
      "tooltip": "Make a 1920x1080 AVI playblast of the visible playback range in Documents."
    },
    {
      "label": "FBX",
      "group": "Toolkit Bar",
      "tooltip": "Export only the selected animation over the visible timeline with Unreal centimetres or Maya scene units."
    },
    {
      "label": "Game",
      "group": "Toolkit Bar",
      "tooltip": "Apply the Game Animation Mode choices ticked in Scene Helpers. Turning it off does not undo those Maya settings."
    },
    {
      "label": "QS",
      "group": "Workflow",
      "tooltip": "Open Quick Start."
    },
    {
      "label": "SH",
      "group": "Workflow",
      "tooltip": "Open Scene Helpers."
    },
    {
      "label": "PK",
      "group": "Workflow",
      "tooltip": "Open Reference Manager."
    },
    {
      "label": "DP",
      "group": "Workflow",
      "tooltip": "Open Dynamic Parenting."
    },
    {
      "label": "HF",
      "group": "Workflow",
      "tooltip": "Open Hand / Foot Hold."
    },
    {
      "label": "SC",
      "group": "Workflow",
      "tooltip": "Open Surface Contact."
    },
    {
      "label": "PV",
      "group": "Workflow",
      "tooltip": "Open Dynamic Pivot."
    },
    {
      "label": "IK",
      "group": "Workflow",
      "tooltip": "Open Universal IK/FK."
    },
    {
      "label": "RT",
      "group": "Workflow",
      "tooltip": "Open Controls Retargeter."
    },
    {
      "label": "CP",
      "group": "Workflow",
      "tooltip": "Open Control Picker."
    },
    {
      "label": "PN",
      "group": "Workflow",
      "tooltip": "Open Animators Pencil."
    },
    {
      "label": "HT",
      "group": "Workflow",
      "tooltip": "Open History Timeline."
    },
    {
      "label": "OS",
      "group": "Workflow",
      "tooltip": "Open Onion Skin."
    },
    {
      "label": "RD",
      "group": "Workflow",
      "tooltip": "Open Rotation Doctor."
    },
    {
      "label": "SK",
      "group": "Workflow",
      "tooltip": "Open Character Skinning."
    },
    {
      "label": "RS",
      "group": "Workflow",
      "tooltip": "Open Rig Scale."
    },
    {
      "label": "VR",
      "group": "Workflow",
      "tooltip": "Open Video Reference."
    },
    {
      "label": "TN",
      "group": "Workflow",
      "tooltip": "Open Timeline Notes."
    },
    {
      "label": "Open Tutorials + FAQ",
      "group": "Quick Start",
      "tooltip": "Open this local documentation page."
    },
    {
      "label": "Donate",
      "group": "Footer",
      "tooltip": "Open Amir's configurable donation link."
    }
  ],
  "faq": [
    {
      "q": "Where do I open the tutorials?",
      "a": "Click Open Tutorials + FAQ in Aminate's Quick Start tab, or open tutorial.html beside the release installer. The installed route remains Aminate/docs/index.html."
    },
    {
      "q": "Will this guide work without internet?",
      "a": "Yes. The tutorial page, styles, JavaScript, screenshots, GIFs, and videos are local files. Links such as followamir.com are optional extras."
    },
    {
      "q": "Why can I not find Smear Frames or Customization?",
      "a": "They are the last two main tabs in the current 23-tab Aminate window. Scroll the tab strip or use the search box in this guide."
    },
    {
      "q": "Does turning Game Animation Mode off undo its settings?",
      "a": "No. Off only changes the button state. The 30 fps, realtime, viewport, autosave, textures, and weighted-tangent settings already applied stay in Maya until you change them again."
    },
    {
      "q": "How do Smear Frames reach Unreal Engine?",
      "a": "Use Unreal Morph Overlay, sculpt without adding or deleting vertices, save the range, then click Export All Unreal Smears. Import the FBX as a Skeletal Mesh with Import Animations and Import Morph Targets turned on. The bundle also includes a JSON manifest, an Unreal Python helper, and a plain-text guide."
    },
    {
      "q": "What should I do before a risky button?",
      "a": "Save the Maya scene and make a History Timeline step. That gives you a clear way back if the result is not what you wanted."
    },
    {
      "q": "A button did nothing. What now?",
      "a": "Read the before-you-start box, check the selection, then run the small setup or refresh button shown in that lesson. Most tools need the right object selected first."
    },
    {
      "q": "Can I use the GIFs in class?",
      "a": "Yes. They are local teaching examples. Pause a GIF or use the controls on a video to watch one small action at a time."
    },
    {
      "q": "Why is a screenshot labelled narrow?",
      "a": "It is a real narrow-window capture. It shows how the tab reflows on a small laptop or phone-sized view; it is not a promise that every Maya window is that exact width."
    },
    {
      "q": "How do I return to the normal installed docs?",
      "a": "Open Aminate/docs/index.html. The release-root tutorial.html is a handoff shortcut to the same payload docs, not a second installed docs route."
    }
  ],
  "intro": {
    "eyebrow": "Offline field guide",
    "title": "Make the next pose clearer",
    "summary": "A calm, picture-first coach for the 23 Aminate tabs. Find the animation problem in front of you, do one small test, and check the result before you keep working.",
    "version": "Aminate 0.3.6"
  },
  "featured": [
    {
      "label": "Try this first",
      "title": "A foot that slides",
      "text": "Open Hand / Foot Hold, choose the contact range, and look for a planted foot in the GIF.",
      "target": "hand-foot-hold"
    },
    {
      "label": "See the shape",
      "title": "Draw an animation note",
      "text": "Animators Pencil turns a quick arc or contact mark into a scene object that survives with the file.",
      "target": "animators-pencil"
    },
    {
      "label": "Package safely",
      "title": "Send a shot to a friend",
      "text": "Reference Manager finds the files your scene needs and puts them beside the Maya file in one zip.",
      "target": "reference-manager"
    },
    {
      "label": "Make speed readable",
      "title": "Sculpt a smear and send it to Unreal",
      "text": "Smear Frames saves the edited shape and its frame range, then exports a morph overlay bundle for Unreal.",
      "target": "smear-frames"
    }
  ]
};
