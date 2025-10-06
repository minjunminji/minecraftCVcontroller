Mango maps full-body gestures to Minecraft inputs

## component details

### Pose Tracking (`cv/pose_tracking.py`)

- Wraps MediaPipe Holistic
- Returns dictionaries keyed by `"pose"`, `"left_hand"`, `"right_hand"`, `"face"`
- Each landmark entry includes `name`, `x`, `y`, `z`, and `visibility` (for pose)
- Stores raw MediaPipe results for drawing overlays
- `draw_landmarks` renders annotations when debugging is enabled
- Mirrors the preview only after detection to keep gesture math in camera space

### Gesture State Manager (`utils/state_manager.py`)

**`utils/state_manager.py`:** The [`GestureStateManager`](minecraftCVcontroller/utils/state_manager.py:10) maintains the application's state over time.
  *   It keeps a history of landmark positions, which is essential for detecting movements, velocities, and patterns.
      *   Maintains last _N_ frames of landmark dictionaries (default 30 frames ≈ 1 s @30 FPS)
  *   It provides helper functions that gesture detectors use to analyze the data.
      - Provides positional queries (`get_landmark_position`, `get_relative_position`)
      - Computes kinematics (`get_velocity`, `get_speed`, `get_acceleration`)
      - Detect oscillation patterns for repeated motions
  *   By centralizing state, it ensures that all detectors are working with the same consistent data.


### Gesture Detectors (`gestures/`)

Each file in this directory, like [`shield.py`](minecraftCVcontroller/gestures/shield.py:1), is responsible for detecting a **single, specific gesture**.
  *   Each detector inherits from [`BaseGestureDetector`](minecraftCVcontroller/gestures/base_detector.py) and implements a `detect()` method.
*   It uses the [`GestureStateManager`](minecraftCVcontroller/utils/state_manager.py:10) to access current and past landmark positions to determine if its specific gesture is being performed.
*   It returns a dictionary describing the action (e.g., `{'action': 'shield_start'}`) or `None` if the gesture is not detected.

#### Shield Gesture Logic

1. Pulls left shoulder/elbow/wrist positions
2. Checks:
   - Forearm angle within 35° of horizontal
   - Wrist at least 0.10 units in front of shoulder (negative Z direction)
   - Wrist within 0.15 units vertical of shoulder height
3. Emits:
   - `shield_start` when entering pose
   - `shield_hold` each frame while held
   - `shield_stop` when pose breaks or tracking lost

#### Mining Gesture Logic

1. Monitors right wrist velocity using a 3-frame window for responsive detection
2. Detects velocity spikes above `velocity_threshold` (1.0) to trigger individual attack clicks
3. Tracks click frequency within `click_interval` (0.5s) and counts consecutive clicks
4. Transitions to continuous mining mode after `min_clicks_for_hold` (2) rapid clicks
5. While in hold mode, monitors wrist oscillation patterns to maintain continuous mining
6. Stops hold mode when oscillation ceases or tracking is lost
7. Includes timeout logic to reset click sequences after `click_interval * 2` (1.0s) of inactivity
8. Emits:
   - `mining_click` for individual attack motions
   - `mining_start_hold` when transitioning to continuous mining
   - `mining_continue_hold` while maintaining continuous mining
   - `mining_stop_hold` when stopping continuous mining or losing tracking

### Action Coordinator (`utils/action_coordinator.py`)

**`utils/action_coordinator.py`:** The [`ActionCoordinator`](minecraftCVcontroller/utils/action_coordinator.py:8) receives the raw detection results from all gesture detectors and decides which actions to execute.
 *   It prevents conflicting actions. For example, it ensures you cannot mine and use a shield at the same time.
 *   It manages state transitions, such as starting to sprint or stopping movement.
 *   It translates abstract gesture events (like `shield_start`) into concrete keyboard and mouse commands via the `MinecraftController`.

### Minecraft Controller (`controls/keyboard_mouse.py`)

- Thin wrapper around `pynput` providing Minecraft-specific helpers (move, jump, mining, shield, hotbar)
- Tracks pressed keys/buttons to avoid duplicate presses and for debug inspection
- Throws informative error when `pynput` is missing
- `release_all()` cleans up on shutdown

### Main Loop (`main.py`)

**`main.py`:** This is responsible for the main loop. In each cycle, it:
 *   Captures a frame from the webcam.
 *   Calls [`cv.pose_tracking.get_landmarks()`](minecraftCVcontroller/cv/pose_tracking.py) to get raw landmark data from MediaPipe.
 *   Updates the [`GestureStateManager`](minecraftCVcontroller/utils/state_manager.py:10) with the new landmarks.
 *   Iterates through all registered gesture detectors (`gestures/*.py`).
 *   Passes the aggregated gesture results to the [`ActionCoordinator`](minecraftCVcontroller/utils/action_coordinator.py:8).
 *   Displays a debug visualization.
- Handles hotkeys:
  - `q`: quit
  - `r`: reset coordinator, detectors, and state history
  - `d`: toggle HUD
  - `c`: capture neutral calibration pose (when landmarks available)
- Performs cleanup (stop inputs, release webcam, destroy windows, close MediaPipe)

## adding new gestures

1. **Create Detector**
   - Add new class in `gestures/`
   - Inherit `BaseGestureDetector`
   - Use `state_manager` queries for posture/motion
   - Return structured dict with `action` plus any debug metadata
   - Maintain internal state in `self._state` to debounce transitions

2. **Register in `main.py`**
   - Instantiate detector in `gesture_detectors`
   - Add to left/right hand mapping priority lists if relevant

3. **Handle Output in `ActionCoordinator`**
   - Update `_handle_left_hand_actions`, `_handle_right_hand_actions`, or movement/jumping handlers to consume new action types
   - Ensure conflicting actions release prior state (e.g., shield vs mining)

4. **Update Documentation**
   - Record detector behavior and expected outputs for future collaborators
   - Mention tunable thresholds and calibration needs

## requirements:

- Tested on Python 3.11.9
- `pip install -r requirements.txt` (includes `mediapipe` & `opencv-python`)
- `pynput` for keyboard/mouse control (install via requirements)
