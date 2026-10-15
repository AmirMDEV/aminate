window.AMINATE_DOCS = {
  "sections": [
    {
      "id": "quick-start",
      "icon": "QS",
      "short": "Quick Start",
      "title": "Quick Start",
      "media": "assets/panel-quick-start.png",
      "purpose": "Find a tool for the job you want to do.",
      "when": "A student has opened Aminate and needs the fastest route to the right tool.",
      "steps": [
        "Type a job, such as foot sliding or draw notes.",
        "Pick a tool and read what it does.",
        "Click Open Tool. Use Help inside any tool for its steps."
      ],
      "buttons": [
        "Open Tool",
        "How to use it",
        "Open Tutorials + FAQ"
      ],
      "tips": [
        "Keep this page open beside Maya during lessons so students can self-correct before asking for help."
      ],
      "before": "Open Maya and Aminate. Save your scene before testing tools.",
      "see": "The tool you chose opens in Aminate.",
      "help": "Clear the search and try one word, such as foot.",
      "number": "01",
      "tabTitle": "Quick Start",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-quick-start.png",
          "title": "Quick Start · built panel preview"
        }
      ],
      "searchTerms": "help learn beginner start"
    },
    {
      "id": "toolkit-bar",
      "icon": "TB",
      "short": "Toolkit",
      "title": "Toolkit Bar",
      "media": "assets/panel-toolkit-bar.png",
      "purpose": "Move keys, change timing, and open tools from Maya's bottom bar.",
      "when": "You want to work quickly without hunting through Maya menus or opening another floating window.",
      "steps": [
        "Select the animated controls or keys.",
        "Point at a button to see its name and steps.",
        "Check the timeline before moving on."
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
      "before": "Save your scene. Try changes on a short frame range first.",
      "see": "The button gives a short status message, the correct pose or file changes, and the Toolkit Bar stays fixed at Maya's bottom edge.",
      "help": "If nothing happens, check the selection and frame. If the bar looks cut off, scroll it sideways instead of shrinking Maya's buttons.",
      "subsections": [
        {
          "title": "History and animation layers",
          "intro": "These controls protect versions and organise animation without changing the character rig.",
          "items": [
            [
              "History Auto",
              "When this is on, Aminate can make History Timeline checkpoints while you work. Turn it on only when you want automatic snapshots."
            ],
            [
              "History Timeline",
              "Open the list of saved checkpoints so you can compare or restore an earlier scene state."
            ],
            [
              "Animation Layer menu",
              "Choose which Maya animation layer you are editing."
            ],
            [
              "+ Layer / Delete",
              "Make a new animation layer, or delete the chosen layer. Delete affects the layer, so check its name first."
            ],
            [
              "+ Selection / - Selection",
              "Add selected controls to the layer, or remove them from it."
            ],
            [
              "Mute / Solo / Lock",
              "Mute hides a layer's effect. Solo shows only that layer. Lock stops accidental changes."
            ],
            [
              "Layer Weight",
              "Choose how strongly the layer changes the final pose. 0 means no effect; 1 means full effect."
            ]
          ]
        },
        {
          "title": "Quick action icons",
          "intro": "These buttons change keys, poses, meshes, packages, or exports.",
          "items": [
            [
              "Nudge Left / Nudge Right",
              "Move selected keys exactly one frame earlier or later."
            ],
            [
              "Insert Inbetween",
              "Add a new key on the frame where the Time Slider is standing."
            ],
            [
              "Tween Machine",
              "Blend between the key before and the key after. 0% copies the first; 100% copies the next; 50% is halfway."
            ],
            [
              "Cut Current Key",
              "Remove keys only on the current frame for the selected controls."
            ],
            [
              "Reset Pose",
              "Set selected controls to translate 0, rotate 0, and scale 1. If Auto Key is on, the reset is keyed."
            ],
            [
              "Bake On Twos",
              "Bake selected controls over the visible playback range with a key every two frames."
            ],
            [
              "Select Animated",
              "Find and select transforms in the scene that already have animation curves."
            ],
            [
              "Clean Static Keys",
              "Remove animation curves whose keyed value never changes."
            ],
            [
              "Combine Freeze Pivot",
              "Join selected meshes, freeze transforms, and enter Maya's Edit Pivot mode."
            ],
            [
              "Package Scene",
              "Save the scene and collect references, textures, image planes, audio, and caches into a zip."
            ],
            [
              "Playblast 1080p AVI",
              "Make a 1920x1080 AVI of the visible playback range in your Documents folder."
            ],
            [
              "Export Selected Animation FBX",
              "Export only what you selected. It keeps the original source keyframe times by default, with an explicit optional whole-frame resampling checkbox, and leaves cameras and lights off by default."
            ]
          ]
        },
        {
          "title": "Aminate tab buttons and Game Mode",
          "intro": "The small workflow icons jump to every Aminate tab. The separate Game button changes useful Maya scene settings for game animation.",
          "items": [
            [
              "23 workflow icons",
              "Quick Start, Toolkit Bar, Scene Helpers, Reference Manager, Dynamic Parenting, Hand / Foot Hold, Surface Contact, Dynamic Pivot, Universal IK/FK, Controls Retargeter, Control Picker, Animators Pencil, History Timeline, Onion Skin, Rotation Doctor, Character Skinning, Rig Scale, Video Reference, Timeline Notes, Smear Frames, Customization, and the other current Aminate workflow tabs."
            ],
            [
              "Game Animation Mode",
              "Turns on the game setup choices selected in Scene Helpers. Read the Game Animation Mode subsection below before using it."
            ]
          ]
        }
      ],
      "number": "02",
      "tabTitle": "Toolkit Bar",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-toolkit-bar.png",
          "title": "Toolkit Bar · built panel preview"
        },
        {
          "type": "image",
          "src": "assets/tween_machine.gif",
          "title": "Tween Machine GIF"
        }
      ],
      "searchTerms": "toolbar keys timing tween inbetween nudge reset pose bake twos layers game animation mode history zip"
    },
    {
      "id": "scene-helpers",
      "icon": "SH",
      "short": "Scene",
      "title": "Scene Helpers",
      "media": "assets/panel-scene-helpers.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-scene-helpers.png",
          "title": "Scene Helpers · built panel preview"
        },
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
      "purpose": "Set up cameras, textures, key snapping, and other scene helpers.",
      "when": "The scene needs safer setup, cleaner timing, a quick game-preview configuration, or feedback that should travel with the Maya file.",
      "steps": [
        "Find the job: keys, camera, textures, or rendering.",
        "Select the objects or frames that job needs.",
        "Click the helper. Read the result at the bottom."
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
      "before": "Save your scene. Try changes on a short frame range first.",
      "see": "You get one clear result: keys snap, a camera setup appears, Game Mode turns on, a floating editor opens, or a text note appears beside the character.",
      "help": "If the wrong thing changes, undo once and check the selection and tick boxes. Empty tick boxes tell Aminate to leave that part alone.",
      "subsections": [
        {
          "title": "Game Animation Mode",
          "intro": "This is a setup button, not an animation style. It applies only the choices that are ticked.",
          "items": [
            [
              "30 fps",
              "Changes Maya's time unit to 30 frames per second, which is common for games."
            ],
            [
              "Realtime",
              "Makes Maya try to play the animation at its real speed instead of racing through every frame."
            ],
            [
              "Update All Views",
              "Makes Maya refresh every viewport while the animation plays."
            ],
            [
              "Autosave",
              "Turns on Maya autosave and keeps five backup files."
            ],
            [
              "Activate Focused Viewport",
              "Makes the viewport you are working in the active viewport."
            ],
            [
              "Load Textures",
              "Refreshes and repaths texture files that already exist on the computer."
            ],
            [
              "Weighted Tangents",
              "Converts animation curves to weighted tangents so handles can have different lengths."
            ],
            [
              "Important: turning Game Mode off",
              "The button stops showing as active, but it does not undo the Maya settings it already changed. Change those settings manually if you want the old setup back."
            ]
          ]
        },
        {
          "title": "Blocking and timing tick boxes",
          "intro": "These choices decide which animation channels the blocking helper keys.",
          "items": [
            [
              "Translation",
              "Tick this to key move X, Y, and Z on every shared blocking frame."
            ],
            [
              "Rotation",
              "Tick this to key rotate X, Y, and Z on every shared blocking frame."
            ],
            [
              "Other keyable attributes",
              "Tick this only when you also want scale, visibility, and unlocked custom controls keyed."
            ],
            [
              "Auto Key",
              "When on, Maya adds keys when you change an already animated value."
            ],
            [
              "Auto Snap To Frames",
              "When on, Aminate keeps timing changes on whole-number frames."
            ],
            [
              "Animation Layer Tint",
              "Shows the active animation layer with a tint above Maya's Time Slider."
            ],
            [
              "Keep Toolbar Extras On Aminate Hide",
              "Keeps the Toolkit Bar, Tween Machine, Floating Channel Box, and Floating Graph Editor visible when Aminate is hidden. Leave it empty if hiding Aminate should clear those helpers."
            ]
          ]
        },
        {
          "title": "Blocking and editor buttons",
          "intro": "Use these after selecting the controls that should change.",
          "items": [
            [
              "Snap Selected Keys To Frames",
              "Moves selected keys from decimal times such as 12.4 to whole frames such as 12."
            ],
            [
              "Key Full Blocking Poses",
              "Adds keys on the shared blocking frames using the Translation, Rotation, and Other tick boxes above."
            ],
            [
              "Retime Every N Frames",
              "Spreads selected timing so each pose is the chosen number of frames apart."
            ],
            [
              "Duplicate / Consolidate / Solo layers",
              "Copy the current layer, combine other layers into a safe muted copy, solo the current layer, or clear all solos."
            ],
            [
              "Tween Machine",
              "Set its hotkey and transparency, then open the small inbetween slider near the cursor."
            ],
            [
              "Floating Channel Box",
              "Set its hotkey and transparency, then open a small floating channel editor for the selected control."
            ],
            [
              "Floating Graph Editor",
              "Set its hotkey and transparency, then open a floating Maya Graph Editor that avoids duplicates."
            ]
          ]
        },
        {
          "title": "Scene setup and cameras",
          "intro": "These buttons build or remove scene helpers. They do not change the original character mesh.",
          "items": [
            [
              "Load Textures",
              "Ask Maya to refresh and repath texture files that are already available."
            ],
            [
              "Open Last Autosave",
              "Open the newest Maya autosave after a crash or mistake."
            ],
            [
              "Disable Maya Security Popups",
              "Turn off Maya's repeated script-security questions for trusted local work. Use this only when you understand the scene source."
            ],
            [
              "Set Up / Delete Render Environment",
              "Build or remove Aminate's cyclorama, cameras, sky light, and bookmarks."
            ],
            [
              "Duplicate / Delete Teacher Demo",
              "Make a separate demonstration copy of a rig, or remove every teacher-demo copy and its display layer."
            ],
            [
              "Teacher Demo Edit Log",
              "See which teacher-demo edits were recorded."
            ],
            [
              "Camera Preset / Switch View",
              "Choose Front, Side, or Three Quarter and look through that helper camera."
            ],
            [
              "Height, Dolly, and Rig Copy offsets",
              "Move all helper cameras up/down, closer/farther, or offset the demo rig copy together."
            ]
          ]
        },
        {
          "title": "Scene Notes and Auto Wrap",
          "intro": "Scene notes are real Maya text curves, so they save with the scene.",
          "items": [
            [
              "Text, colour, and size",
              "Type the note, choose a readable colour, and set how large it should appear."
            ],
            [
              "Auto Wrap",
              "Tick this to split long text into several lines inside the width and height box."
            ],
            [
              "Box W / Box H / Apply Box",
              "Choose the note's world-space box size and apply it."
            ],
            [
              "Resize In Viewport",
              "Select the note's resize box so you can scale it directly in Maya."
            ],
            [
              "Create Text Note",
              "Make the note beside the currently selected control or body part."
            ],
            [
              "Key On / Key Off",
              "Make the note appear or disappear on the current frame."
            ],
            [
              "Move To Selected",
              "Move an existing note beside a newly selected control."
            ],
            [
              "Apply Style / Delete / Refresh",
              "Update the selected note's look, remove it, or rebuild the list of notes in the scene."
            ]
          ]
        }
      ],
      "number": "03",
      "tabTitle": "Scene Helpers",
      "searchTerms": "auto key snap frames layer tint game animation mode load textures autosave render environment camera offset preset cleanup"
    },
    {
      "id": "reference-manager",
      "icon": "PK",
      "short": "Package",
      "title": "Reference Manager",
      "media": "assets/panel-reference-manager.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-reference-manager.png",
          "title": "Reference Manager · built panel preview"
        },
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
      "purpose": "Put your saved scene and its needed files in one zip.",
      "when": "A shot relies on references, textures, image planes, audio, or caches that must travel with the scene.",
      "steps": [
        "Save the Maya scene.",
        "Click Refresh Needed Files. Check for missing files.",
        "Choose a folder, then click Package Scene To Zip."
      ],
      "buttons": [
        "Refresh Needed Files",
        "Package Scene To Zip"
      ],
      "tips": [
        "The manifest inside the zip tells you what was copied and what Maya could not find."
      ],
      "before": "Save the Maya scene once.",
      "see": "A new zip appears with the scene, copied files, and a manifest that tells you what was found or missing.",
      "help": "If the zip is tiny or a file is missing, refresh again and fix the path before packaging. Packaging copies files; it does not repair a broken scene path.",
      "number": "04",
      "tabTitle": "Reference Manager",
      "searchTerms": "package zip collect share send missing files textures images audio caches references cleanup unknown data"
    },
    {
      "id": "dynamic-parenting",
      "icon": "DP",
      "short": "Parent",
      "title": "Dynamic Parenting",
      "media": "assets/panel-dynamic-parenting.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-dynamic-parenting.png",
          "title": "Dynamic Parenting · built panel preview"
        },
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
      "purpose": "Make an object follow a hand, then let go without a jump.",
      "when": "A magazine, sword, phone, hand, or prop needs to follow different controls during a shot.",
      "steps": [
        "Select the moving object. Click Add Object.",
        "Select the hand or other target. Click Pick Parent.",
        "Choose a frame and target. Click Switch to this Parent."
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
      "before": "Pick the prop that changes hands, such as a phone, sword, or magazine.",
      "see": "The prop follows the new parent without a sudden jump.",
      "help": "A jump usually means the wrong parent or offset was saved. Undo, keep the current offset, and try the switch on a clean test frame.",
      "number": "05",
      "tabTitle": "Dynamic Parenting",
      "searchTerms": "attach detach follow pickup pick up let go drop pass hand prop gun magazine world parent blend offset"
    },
    {
      "id": "hand-foot-hold",
      "icon": "HF",
      "short": "Hold",
      "title": "Hand / Foot Hold",
      "media": "assets/panel-hand-foot-hold.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-hand-foot-hold.png",
          "title": "Hand / Foot Hold · built panel preview"
        },
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
      "purpose": "Keep a hand or foot still while the character moves.",
      "when": "Foot sliding, hand contact, or one-axis travel needs a quick non-destructive hold.",
      "steps": [
        "Select a hand or foot. Click Use Selected Control.",
        "Set the first and last frames. Choose which directions stay still.",
        "Click Save New Hold. Play the range to check it."
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
      "see": "The foot or hand stays planted while the rest of the body moves.",
      "help": "If the contact looks stiff, unlock an axis so it can slide or rotate naturally. A hold is a helper, not a promise that every footstep should be frozen.",
      "number": "06",
      "tabTitle": "Hand / Foot Hold",
      "searchTerms": "foot feet hand sliding slide slipping plant planted pin lock still hold original motion"
    },
    {
      "id": "surface-contact",
      "icon": "SC",
      "short": "Surface",
      "title": "Surface Contact",
      "media": "assets/panel-surface-contact.png",
      "purpose": "Keep hands, feet, or objects from passing through a surface.",
      "when": "A hand, foot, wheel, or prop should stay on a moving or uneven surface.",
      "steps": [
        "Select the controls and floor meshes. Click Use Controls + Meshes.",
        "Set the frame range and gap above the surface.",
        "Click Check Setup, then Create / Update Collision."
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
      "see": "The selected control sits on the mesh instead of floating above or sinking through it.",
      "help": "If the control snaps to a strange place, check that you selected the mesh, not a group or locator. Fix the selection and run Check Setup again.",
      "number": "07",
      "tabTitle": "Surface Contact",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-surface-contact.png",
          "title": "Surface Contact · built panel preview"
        }
      ],
      "searchTerms": "collision floor ground feet foot hand slope steps surface contact penetrate through"
    },
    {
      "id": "dynamic-pivot",
      "icon": "PV",
      "short": "Pivot",
      "title": "Dynamic Pivot",
      "media": "assets/panel-dynamic-pivot.png",
      "purpose": "Turn controls around a temporary point, such as a heel.",
      "when": "A prop needs to rotate from a hinge, edge, hand point, or temporary contact point.",
      "steps": [
        "Pick controls. Create a pivot marker and move it to the turning point.",
        "Highlight frames to change. No highlight means only the current frame.",
        "Rotate the marker, then use the turn button. Check the movement."
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
      "before": "Pick the controls you want to turn.",
      "see": "Every whole frame in the highlighted range turns around the helper point.",
      "help": "If the turn is backwards, undo, rotate or move the marker, and try again. To use a new pivot later, move the same marker, highlight the later frames, and click Turn From Pivot again.",
      "number": "08",
      "tabTitle": "Dynamic Pivot",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-dynamic-pivot.png",
          "title": "Dynamic Pivot · built panel preview"
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
      ],
      "searchTerms": "rotate turn heel toe pivot point marker roll"
    },
    {
      "id": "universal-ikfk",
      "icon": "IK",
      "short": "IK/FK",
      "title": "Universal IK/FK",
      "media": "assets/panel-universal-ikfk.png",
      "purpose": "Switch an arm or leg between IK and FK without changing its pose.",
      "when": "An arm or leg changes mode mid-shot and needs clean keys around the switch.",
      "steps": [
        "Pick one arm or leg. Click Set Up From Selection.",
        "Check its controls: IK moves the end; FK turns each joint.",
        "Save the setup. Switch to IK or FK and check the pose."
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
          "src": "assets/panel-universal-ikfk.png",
          "title": "Universal IK/FK · built panel preview"
        }
      ],
      "searchTerms": "arm leg chain switch match ik fk inverse forward kinematics"
    },
    {
      "id": "control-rig-builder",
      "icon": "RB",
      "short": "Control Rig Builder",
      "title": "Control Rig Builder",
      "tabTitle": "Control Rig Builder",
      "purpose": "Turn an imported skeleton into an editable control rig while keeping its existing skin.",
      "when": "Use this when preparing an imported character or creature for editable animation in Maya.",
      "steps": [
        "Select the skeleton at its reference pose and click Scan selected skeleton / Auto-map.",
        "Review each role, assign uncertain joints, and add extra three-joint limb groups.",
        "Build the rig, then use Match and switch to IK or FK to animate. Add optional features after returning to the reference pose."
      ],
      "buttons": [
        "Scan selected skeleton / Auto-map",
        "Build control rig",
        "Match and switch to IK",
        "Apply rig feature",
        "Save pose"
      ],
      "tips": [
        "Use assigned endpoints to suggest unnamed joints between them. Geometry suggestions still need review.",
        "Stretch, Soft IK and foot pivots are optional modules. Add them in that order.",
        "Current imported rigs must have editable local joint channels. Existing constraint rigs and animation layers require an export skeleton first.",
        "Every joint receives FK controls. Primary limb IK requires a contiguous three-joint chain; intermediary twist chains remain FK."
      ],
      "before": "Save your scene and choose a clear reference pose before creating or transferring animation.",
      "see": "Editable controls or a baked animation layer appear on the chosen target rig.",
      "help": "Check role assignments, reference poses, frame ranges and the status message if the operation stops.",
      "media": "assets/control-rig-builder.svg",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/control-rig-builder.svg",
          "title": "Control Rig Builder workflow diagram"
        }
      ],
      "searchTerms": "skeleton rig builder mocap creature extra arms mapping fbx animation bake",
      "number": "10"
    },
    {
      "id": "multi-performer-mocap",
      "icon": "MC",
      "short": "Multi-Performer Mocap",
      "title": "Multi-Performer Mocap",
      "tabTitle": "Multi-Performer Mocap",
      "purpose": "Route several performers onto separate creature limbs and bake their combined movement onto one rig.",
      "when": "Use this when preparing an imported character or creature for editable animation in Maya.",
      "steps": [
        "Import each performer FBX and choose the generated creature rig.",
        "Select source joints and assign them to a target limb group. Set a matching reference-pose frame and clip timing for each route.",
        "Create a baked preview, inspect the movement, then keep or discard the layer."
      ],
      "buttons": [
        "Import performer FBX",
        "Add selected source chain → target group",
        "Create baked preview",
        "Keep preview",
        "Bake composed mocap"
      ],
      "tips": [
        "Four performers can each drive a separate pair of arms. Reuse a source on several groups if useful, but assign each target only once.",
        "Give the root and body their own route when you want locomotion. Arm routes use local rotation by default.",
        "Every-frame baking captures the requested samples. Sparse baking uses selected Graph Editor key times and can differ between those times.",
        "Match anatomical reference poses and inspect shoulders and contacts; composition does not automatically solve hand contact or collisions."
      ],
      "before": "Save your scene and choose a clear reference pose before creating or transferring animation.",
      "see": "Editable controls or a baked animation layer appear on the chosen target rig.",
      "help": "Check role assignments, reference poses, frame ranges and the status message if the operation stops.",
      "media": "assets/multi-performer-mocap.svg",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/multi-performer-mocap.svg",
          "title": "Multi-Performer Mocap workflow diagram"
        }
      ],
      "searchTerms": "skeleton rig builder mocap creature extra arms mapping fbx animation bake",
      "number": "11"
    },
    {
      "id": "retargeter",
      "icon": "RT",
      "short": "Retarget",
      "title": "Controls Retargeter (Face and Body)",
      "media": "assets/panel-retargeter.png",
      "purpose": "Copy movement from one character's controls to another character's controls.",
      "when": "Two rigs use different control names but the motion should transfer by order or loose names.",
      "steps": [
        "Load the controls to copy from on the left.",
        "Load the controls to copy to on the right. Check each pair.",
        "Click Check Setup, then Retarget All Controls. Play the result."
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
      "before": "Have a source rig and a target rig in the scene.",
      "see": "The target matches the source pose on the first animated key, follows the source motion, and has no extra keys between the source keys.",
      "help": "If the target begins in its old T-pose, undo and make sure you used the repaired Match Source Starting Pose workflow. If it bends the wrong way, fix the pair row; Aminate cannot guess a missing or incorrectly paired control.",
      "number": "12",
      "tabTitle": "Controls Retargeter (Face and Body)",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-retargeter.png",
          "title": "Controls Retargeter (Face and Body) · built panel preview"
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
      ],
      "searchTerms": "retarget copy animation movement motion face body source target pair map controls"
    },
    {
      "id": "control-picker",
      "icon": "CP",
      "short": "Picker",
      "title": "Control Picker",
      "media": "assets/panel-control-picker.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-control-picker.png",
          "title": "Control Picker · built panel preview"
        },
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
      "purpose": "Find and select a character's controls from a list or picture.",
      "when": "You need to select a whole tail, one arm, only its FK controls, only its IK controls, or your own saved mixture without hunting through the viewport.",
      "steps": [
        "Select the character's top group. Click Scan Selected Rig.",
        "Click a body part to select its controls.",
        "Hold Ctrl or Shift to add more groups to your selection."
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
      "before": "Save a copy of the scene, then select the rig's highest control group.",
      "see": "A nested picker appears.",
      "help": "If Aminate misses a control, select that control in Maya and click Add Selected. If it is in the wrong group, select it, choose the right group, and click Move Selected To Group. If a saved set points at deleted controls, rescan and update that custom set.",
      "number": "13",
      "tabTitle": "Control Picker",
      "searchTerms": "select selection character animal controls rig body hands fingers limbs tail map custom sets attributes"
    },
    {
      "id": "animators-pencil",
      "icon": "PN",
      "short": "Pencil",
      "title": "Animators Pencil",
      "media": "assets/panel-animators-pencil.png",
      "purpose": "Draw on the view to plan poses or leave notes.",
      "when": "You need visible animation notes that survive without the script installed.",
      "steps": [
        "Choose a drawing tool and colour.",
        "Click Start Drawing, then drag in the view.",
        "Use layers to separate drawings. Press E to erase on the current layer."
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
      "before": "Open the view you want to draw on. Choose a drawing layer.",
      "see": "Your marks are scene objects in a camera-specific layer.",
      "help": "If a mark is missing, switch back to its Saved Drawing View and layer. A locked layer cannot be erased until you unlock it.",
      "number": "14",
      "tabTitle": "Animators Pencil",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-animators-pencil.png",
          "title": "Animators Pencil · built panel preview"
        }
      ],
      "searchTerms": "draw drawing notes pencil blue pencil erase eraser strokes marks shapes camera video layers ghosts retime"
    },
    {
      "id": "animation-assistant",
      "icon": "AA",
      "short": "Assist",
      "title": "Animation Assistant",
      "media": "assets/panel-animation-assistant.png",
      "purpose": "Check whether a pose balances over the hands or feet touching the floor.",
      "when": "A pose feels unstable and needs a fast visual balance check.",
      "steps": [
        "Load the floor and the control at the character's centre of weight.",
        "Add the hands or feet that can touch the floor.",
        "Click Refresh. Adjust the pose and check the balance guide."
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
      "before": "Pick the floor or ground control and the controls that touch it.",
      "see": "The viewport shows a support area and a simple balanced or unbalanced badge.",
      "help": "If the badge says unbalanced, check the silhouette and acting too. The helper only measures the points you gave it.",
      "number": "15",
      "tabTitle": "Animation Assistant",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-animation-assistant.png",
          "title": "Animation Assistant · built panel preview"
        }
      ],
      "searchTerms": "balance weight gravity floor contact support pose"
    },
    {
      "id": "animation-styling",
      "icon": "ST",
      "short": "Style",
      "title": "Animation Styling",
      "media": "assets/panel-animation-styling.png",
      "purpose": "Hold poses for several frames to make stepped, stop-motion-style movement.",
      "when": "A shot needs Spider-Verse-style stepped timing or clean held poses.",
      "steps": [
        "Select controls and set how many frames each pose lasts.",
        "Click Scan Overlaps to check for keys that are too close.",
        "Click Hold Current Key or Hold Selected Existing Keys. Play the result."
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
      "number": "16",
      "tabTitle": "Animation Styling",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-animation-styling.png",
          "title": "Animation Styling · built panel preview"
        }
      ],
      "searchTerms": "spider verse stop motion stepped hold poses keys overlap"
    },
    {
      "id": "history-timeline",
      "icon": "HT",
      "short": "History",
      "title": "History Timeline",
      "media": "assets/panel-history-timeline.png",
      "purpose": "Save scene copies you can return to. Restoring replaces the whole open scene.",
      "when": "Students need a return point before risky edits or a milestone before feedback changes.",
      "steps": [
        "Save the scene first.",
        "Click Save Step. Use Save Milestone for a copy you want to keep.",
        "Save current work before restoring a snapshot; it replaces the whole scene."
      ],
      "buttons": [
        "Save Step",
        "Save Milestone",
        "Restore"
      ],
      "tips": [
        "Restoring creates a safety snapshot first so the current state is not lost immediately."
      ],
      "before": "Save your scene. Try changes on a short frame range first.",
      "see": "A coloured history row appears and Restore returns the scene to that saved moment without deleting your current work first.",
      "help": "If a restore looks wrong, use the safety snapshot that Aminate made just before restoring. History is a safety net, not a replacement for saving the Maya file.",
      "number": "17",
      "tabTitle": "History Timeline",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-history-timeline.png",
          "title": "History Timeline · built panel preview"
        }
      ],
      "searchTerms": "undo restore recover backup snapshot save milestone branch autosave history"
    },
    {
      "id": "onion-skin",
      "icon": "OS",
      "short": "Onion",
      "title": "Onion Skin",
      "media": "assets/panel-onion-skin.png",
      "purpose": "See faint copies of earlier and later poses beside the current pose.",
      "when": "Arcs, spacing, contacts, and rhythm are hard to judge from the current frame alone.",
      "steps": [
        "Select the animated mesh. Click Use Current Selection.",
        "Choose how far apart the earlier and later poses should be.",
        "Move through frames to compare poses. Clear the preview when finished."
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
      "number": "18",
      "tabTitle": "Onion Skin",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-onion-skin.png",
          "title": "Onion Skin · built panel preview"
        },
        {
          "type": "image",
          "src": "assets/maya_onion_skin_demo.gif",
          "title": "Onion Skin GIF"
        }
      ],
      "searchTerms": "ghost ghosts previous next past future poses spacing arc timing onion skin"
    },
    {
      "id": "rotation-doctor",
      "icon": "RD",
      "short": "Rotate",
      "title": "Rotation Doctor",
      "media": "assets/panel-rotation-doctor.png",
      "purpose": "Find and fix unwanted twists or flips in animated controls.",
      "when": "Rotations jump, spin the long way, or become hard to edit cleanly.",
      "steps": [
        "Select the controls that twist or flip.",
        "Click Analyze Selected. Read the suggested fix.",
        "Click Use Best Fix. Play the changed frames to check them."
      ],
      "buttons": [
        "Analyze Selected",
        "Use Best Fix",
        "Flip Current Key"
      ],
      "tips": [
        "Save a History Timeline step before large curve repairs."
      ],
      "before": "Select only the animated controls with the rotation problem.",
      "see": "The rotation curve no longer makes a surprise flip, and the report tells you what was checked.",
      "help": "Rotation fixes change keys. A History Timeline step makes it easy to go back if the artistic result is not right.",
      "number": "19",
      "tabTitle": "Rotation Doctor",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-rotation-doctor.png",
          "title": "Rotation Doctor · built panel preview"
        }
      ],
      "searchTerms": "rotation flip twist gimbal euler quaternion spins smooth cleanup"
    },
    {
      "id": "character-skinning",
      "icon": "SK",
      "short": "Skin",
      "title": "Character Skinning",
      "media": "assets/panel-character-skinning.png",
      "purpose": "Fix a character's transforms or copy how its skin follows the bones.",
      "when": "A skinned mesh has bad transform values or a duplicate mesh needs the same weights.",
      "steps": [
        "Choose Fix Skinning or Skin Transfer.",
        "For a whole rig, select its top group and click Copy Whole Character.",
        "For weight transfer, load source meshes and target meshes, then click Transfer Skin."
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
      "before": "Pick one skinned mesh.",
      "see": "The mesh keeps its skin and animation but has clean transform values.",
      "help": "If a check is red, stop and fix that problem first. Replace Original is the one action in this lesson that should never be rushed.",
      "number": "20",
      "tabTitle": "Character Skinning",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-character-skinning.png",
          "title": "Character Skinning · built panel preview"
        },
        {
          "type": "image",
          "src": "assets/character_skinning_rig_scale_fix.gif",
          "title": "Character Skinning frozen-transform GIF"
        }
      ],
      "searchTerms": "skinning skin weights bones joints mesh transforms freeze scale clothing topology transfer copy"
    },
    {
      "id": "root-motion",
      "icon": "RM",
      "short": "Root Motion",
      "title": "Root Motion",
      "tabTitle": "Root Motion",
      "media": "assets/root-motion-flow.svg",
      "purpose": "Add root motion after animating the body while keeping its world-space performance.",
      "when": "Your character moves away from a stationary root, or you want to replace the root path independently.",
      "before": "Use a saved scene with an editable root and editable direct child joints or transforms. Move to the offset reference frame inside the range.",
      "steps": [
        "Pick the root bone or control and set Start and End. All its direct child transform branches will be preserved.",
        "Leave Follow source empty for freeform editing, or pick a bone or COG and tick Translation, Rotation and/or Scale. Maintain offset uses the current frame.",
        "Click Prepare independent root. Animate the selected root helper, then choose Authored keyframes only or Every frame and click Bake and finish."
      ],
      "buttons": [
        "Prepare independent root",
        "Select root animation control",
        "Refresh sessions",
        "Bake and finish",
        "Cancel and restore original"
      ],
      "see": "The root helper changes the root path while the body follows its captured motion. Bake verifies the resulting world matrices at the selected sample times and removes its helpers.",
      "help": "Locked, constrained, driven-key or animation-layer channels on the root or direct children require an editable controller or baked export skeleton. Zero scale is rejected. If matrix verification fails, the bake is undone and the preview remains available.",
      "searchTerms": "root motion independent hips cog follow offset bake keyframes translate rotate scale",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/root-motion-flow.svg",
          "title": "Root-motion workflow diagram, not a Maya screenshot"
        }
      ],
      "tips": [
        "The follow source is captured at setup to avoid a cycle when it is a descendant. Cancel and prepare again to capture changed body/source animation or change follow settings.",
        "Preview is intended for the chosen frame range. Caches sample whole frames, exact source keys and the reference frame; subframe interpolation may differ.",
        "Authored keyframes only uses original target/source/ancestor keys plus helper keys, preserving fractional times. It can differ between keys. Dense mode also includes whole frames and range boundaries.",
        "Baking preserves outside-range key values; interpolation at the range edges can change. Undo Bake restores the active preview.",
        "Sessions survive scene save/reopen. Refresh sessions to resume. Do not reparent targets during preview."
      ],
      "subsections": [
        {
          "title": "Follow and offset",
          "items": [
            [
              "Translation",
              "Copy the captured source position. With Maintain offset, retain the position difference at the reference frame."
            ],
            [
              "Rotation",
              "Copy the captured source orientation, optionally retaining the reference orientation offset."
            ],
            [
              "Scale",
              "Copy source scale through a scale constraint, optionally retaining the reference scale ratio. Matrices must stay invertible."
            ],
            [
              "Freeform",
              "Leave Follow source empty and key the temporary root helper. The body cache remains independent."
            ]
          ]
        }
      ],
      "number": "21"
    },
    {
      "id": "rig-scale",
      "icon": "RS",
      "short": "Scale",
      "title": "Rig Scale",
      "media": "assets/panel-rig-scale.png",
      "purpose": "Make a bigger or smaller export copy. Keep the original rig unchanged.",
      "when": "The original rig must stay untouched but the exported copy needs a different scale.",
      "steps": [
        "Load the rig control and top skeleton joint.",
        "Set the size. 150% means one and a half times the original.",
        "Click Check Setup, then Make Copy. Export the copy when it looks right."
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
      "before": "Choose the character and skeleton you want to export.",
      "see": "A separate scaled group appears in the scene and the source rig stays as it was.",
      "help": "If the copy is the wrong size, delete the copy and make it again with a corrected multiplier. Never scale the original just to test an export.",
      "number": "22",
      "tabTitle": "Rig Scale",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-rig-scale.png",
          "title": "Rig Scale · built panel preview"
        }
      ],
      "searchTerms": "resize size bigger smaller scale character skeleton export unreal fbx"
    },
    {
      "id": "video-reference",
      "icon": "VR",
      "short": "Video",
      "title": "Video Reference",
      "media": "assets/panel-video-reference.png",
      "purpose": "Put a video or picture in the view to follow or trace.",
      "when": "A shot needs visual reference aligned with the Maya timeline.",
      "steps": [
        "Click Use Active View, then Pick Video / Images.",
        "Set where it goes, its size, and its first frame.",
        "Click Make Tracing Card. Move through frames to check the timing."
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
      "number": "23",
      "tabTitle": "Video Reference",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-video-reference.png",
          "title": "Video Reference · built panel preview"
        }
      ],
      "searchTerms": "video image picture reference trace tracing card audio follow overlay sequence"
    },
    {
      "id": "timeline-notes",
      "icon": "TN",
      "short": "Notes",
      "title": "Timeline Notes",
      "media": "assets/panel-timeline-notes.png",
      "purpose": "Add coloured notes to frames so you can find them later.",
      "when": "Feedback, planning notes, or shot tasks need to live on the timeline.",
      "steps": [
        "Set the first and last frames for the note.",
        "Write a short title and note. Choose a colour.",
        "Click Add Note. Move into those frames to see it."
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
      "number": "24",
      "tabTitle": "Timeline Notes",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-timeline-notes.png",
          "title": "Timeline Notes · built panel preview"
        }
      ],
      "searchTerms": "notes note comment reminder title colour color frames bookmarks timeline"
    },
    {
      "id": "smear-frames",
      "icon": "SM",
      "short": "Smear",
      "title": "Smear Frames",
      "media": "assets/panel-smear-frames.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-smear-frames.png",
          "title": "Smear Frames · built panel preview"
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
      "purpose": "Make a stretchy motion shape. Edit it and choose when it appears.",
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
        "Select the animated mesh on the frame you want to stretch.",
        "Set the stretch amount. Click Create Smear.",
        "Edit the shape and its visible frames. Click Save Name And Frames."
      ],
      "before": "Save the scene and select one animated mesh.",
      "see": "The saved smear list remembers the name and frame range after saving and reopening Maya.",
      "help": "If the smear is too wild, undo and use smaller offsets or strength. If Unreal shows no morph, import the FBX as Skeletal Mesh with Import Animations and Import Morph Targets turned on.",
      "subsections": [
        {
          "title": "What Aminate saves",
          "intro": "Each saved item keeps enough information to return after the Maya scene is reopened.",
          "items": [
            [
              "Name and unique ID",
              "A human name for the list plus an internal ID so two smears can have similar names safely."
            ],
            [
              "Source and sample frames",
              "The mesh Aminate sampled and the previous/current/next frames used to calculate motion."
            ],
            [
              "Visible range",
              "The first and last frame where the smear should be on."
            ],
            [
              "Editable target",
              "A topology-matching mesh whose vertices you can move with Maya's normal modelling tools."
            ],
            [
              "Unreal carrier",
              "A one-joint skeletal overlay with blend shapes. Aminate remembers the source rig's scale, so a vertex you move by 3.5 cm stays a 3.5 cm edit. The joint shrinks the overlay almost to zero outside your chosen frames, then returns to the captured scale during the smear."
            ],
            [
              "Visible From Frame",
              "The first frame where the saved smear shape appears."
            ],
            [
              "Visible Through Frame",
              "The last frame where the saved smear shape appears."
            ]
          ]
        },
        {
          "title": "Why the Unreal export works",
          "intro": "FBX visibility animation is not a dependable way to turn a mesh on and off in Unreal, so Aminate uses morph curves instead.",
          "items": [
            [
              "Before the range",
              "Morph weight is 0, so the overlay shrinks too small for the player to see."
            ],
            [
              "Inside the range",
              "Morph weight is 1, so the sculpted smear appears."
            ],
            [
              "After the range",
              "Morph weight returns to 0 and the overlay disappears again."
            ],
            [
              "FBX bundle",
              "The FBX contains geometry, one root joint, skinning, blend shapes, and baked animation. The JSON records FPS, units, axis, names, and ranges."
            ],
            [
              "Unreal import",
              "Import as Skeletal Mesh with animations and morph targets. Play the smear overlay animation at the same time as the character animation."
            ]
          ]
        }
      ],
      "number": "25",
      "tabTitle": "Smear Frames",
      "searchTerms": "smear stretch speed motion shape vertices sculpt frame unreal morph export"
    },
    {
      "id": "customization",
      "icon": "CU",
      "short": "Custom",
      "title": "Customization",
      "media": "assets/panel-customization.png",
      "mediaItems": [
        {
          "type": "image",
          "src": "assets/panel-customization.png",
          "title": "Customization · built panel preview"
        }
      ],
      "purpose": "Choose Aminate's theme, animation colours, and toolbar tooltip size.",
      "when": "The tools work but the interface needs clearer contrast or a calmer personal setup.",
      "buttons": [
        "Apply Style",
        "Reset"
      ],
      "tips": [
        "Change one setting at a time and keep the most readable result."
      ],
      "steps": [
        "Choose a theme to change Aminate's look.",
        "Pick animation colours, then click Apply Colors.",
        "Use Reset Colors to return to the default animation colours."
      ],
      "before": "Take a screenshot of the current look or remember the Reset button.",
      "see": "The selected Aminate accents update while neutral panels stay dark and readable.",
      "help": "If a colour hides text or makes a normal button look dangerous, reset it and choose a calmer colour with more contrast.",
      "number": "26",
      "tabTitle": "Customization",
      "searchTerms": "theme appearance graphite studio contrast toolkit spectrum colours colors tooltip text size"
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
