Mango — gesture-controlled Minecraft using your webcam (no VR headset required)

Built in 12 hours at HelloHacks and awarded 1st place. Our goal: lower the barrier to “VR-like” experiences using only commodity hardware and open tools — no proprietary games or equipment. MineMotion uses computer vision to turn your whole body into a controller for vanilla Minecraft.

## Highlights

- No proprietary hardware: just a webcam and your PC
- Works with vanilla Minecraft (OS-level keyboard/mouse inputs)
- Full-body + hand gestures for gameplay and menus
- Built fast but thoughtfully: modular detectors, central coordinator, debug HUD

## Demo

https://youtu.be/pdja2_o8bpY

## How It Works

- Pose tracking: `cv/pose_tracking.py` wraps MediaPipe Holistic and returns normalized landmarks for pose, hands, and face, plus draw helpers for the debug HUD.
- Temporal state: `utils/state_manager.py` keeps a rolling history (≈30 frames) and exposes helpers for positions, velocity, acceleration, and relative measurements.
- Gesture detectors: each file in `gestures/` detects one gesture and returns an action payload. Examples: `shield.py`, `mining.py`, `placing.py`, `movement.py`, `inventory.py`, `menuclose.py`, `cursor_control.py`, `attack.py`, `looking.py`, `hand_scroll.py`.
- Action coordination: `utils/action_coordinator.py` resolves conflicts and translates gesture events to concrete inputs via `controls/keyboard_mouse.py` (pynput).
- Main loop: `main.py` ties it together, shows a HUD, and handles hotkeys.

## Supported Gestures

Gameplay
- Movement: walk-in-place to move; lean torso left/right to strafe. Backward is not yet implemented.
- Looking: head tilt/rotation moves the camera (mouse look).
- Attack: right-hand horizontal “punch” = left click.
- Mining: right-hand vertical “stab” transitions into hold left click.
- Place/Use: quick right-hand open sequence = right click.
- Shield: left forearm horizontal, forward at chest height = hold right click.
- Hotbar scroll: rotate open left hand to scroll up/down.

Menus
- Open inventory: left hand swipe left-to-right (as seen by you) enters menu mode and opens inventory.
- Close menu: left hand swipe right-to-left sends ESC and returns to gameplay.
- Cursor control: in menu mode, move the cursor with your right hand; pinch (thumb+index) to click.

Menu mode details and rationale: see `MENU_MODE_BEHAVIOR.md`.

## Install

Prereqs
- Python 3.11 (tested on 3.11.9)
- A webcam with decent lighting

Setup
```bash
pip install -r requirements.txt
```

OS permissions for input control
- macOS: System Settings → Privacy & Security → Accessibility and Input Monitoring. Add your terminal/IDE and allow control.
- Windows: Run the script “as Administrator”. Some overlays or anti‑cheat can block simulated input.

## Run

```bash
python main.py
```

Tips
- Camera selection: edit `main.py` if needed (`cv2.VideoCapture(0)` → try `1` if you have multiple cameras). The HUD notes 0 = iPhone Continuity Camera, 1 = Mac camera.
- Focus: ensure Minecraft has focus to receive OS input. The debug HUD is always-on-top for visibility.

Hotkeys (in the MineMotion window)
- `r` — toggle gestures on/off (quick reset releases all inputs)
- `d` — toggle debug HUD overlays
- `c` — capture neutral calibration pose (optional)
- `q` — quit

## Architecture & Files

- `main.py` — capture loop, detector orchestration, HUD, hotkeys
- `cv/pose_tracking.py` — MediaPipe Holistic wrapper and drawing
- `utils/state_manager.py` — temporal history and kinematics helpers
- `utils/action_coordinator.py` — maps gesture events to actions; manages gameplay vs menu modes
- `controls/keyboard_mouse.py` — OS input via `pynput` with safety and state tracking
- `gestures/` — one detector per gesture (see files listed above)

Additional docs
- `MENU_MODE_BEHAVIOR.md` — what runs in menu mode and why
- `LOOKING_GESTURE_INFO.md` — head-look details and tuning
- `INVENTORY_FIX.md` — fixes and safety around menu transitions
- `TROUBLESHOOTING.md` — common issues and quick recovery

## Adding New Gestures

1) Create detector in `gestures/`
- Inherit `BaseGestureDetector`
- Use `GestureStateManager` for positions/velocity; keep internal debounce state in `self._state`
- Return a small action dict, e.g. `{'action': 'my_action', 'confidence': 0.8}`

2) Register in `main.py`
- Instantiate and add to `gesture_detectors`
- If it competes with others on the same hand, add it to the left/right priority lists

3) Handle in `ActionCoordinator`
- Consume your action in the appropriate handler, release conflicting actions as needed

## Troubleshooting

- Press `r` to quickly reset (releases all inputs and clears errors)
- Watch the HUD for the orange error banner and check the console stack trace
- See `TROUBLESHOOTING.md` for OS-specific tips (e.g., macOS Accessibility, Windows Admin)

## Why We Built This

We wanted VR‑like immersion without the cost and lock‑in. MineMotion turns any webcam into a controller for a game you already own, keeping the experience open, accessible, and fun.

## Acknowledgements

- MediaPipe Holistic (pose, hands, face) and OpenCV
- HelloHacks — built in 12 hours; awarded 1st place

## Notes & Limitations

- Designed for desktop Minecraft; other titles may work but aren’t tested
- Lighting and camera placement affect tracking quality
- Avoid online servers with anti‑cheat; MineMotion simulates inputs like a keyboard/mouse, but be respectful of game/server rules

