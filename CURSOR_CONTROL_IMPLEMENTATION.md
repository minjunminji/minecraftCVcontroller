# Cursor Control Implementation Summary

## Overview
Added cursor control functionality for menu navigation using right-hand gestures. The system only activates when the game cursor is visible and not captured (menu mode).

## Files Created/Modified

### 1. **gestures/cursor_control.py** (NEW)
Created a new gesture detector for cursor control with the following features:

#### Key Components:
- **`is_in_menu_mode()`**: Cross-platform function that detects if the cursor is visible and unlocked
  - Windows: Checks cursor visibility and clip rect
  - macOS: Uses `CGCursorIsVisible()`
  - Returns `True` when in menu mode

- **`CursorControlDetector`**: Main gesture detector class
  - Tracks right hand wrist position to control cursor
  - Detects pinch gesture (thumb tip + index finger tip) for left click
  - Uses MediaPipe hand landmarks:
    - Index 0: Wrist (for cursor position)
    - Index 4: Thumb tip
    - Index 8: Index finger tip

#### Configuration:
```python
self.pinch_threshold = 0.015         # Distance to trigger pinch (SMALLER = fingers must be closer)
self.pinch_release_threshold = 0.06  # Distance to release pinch (hysteresis)
self.smoothing_factor = 0.7          # Cursor movement smoothing (HIGHER = more responsive to current hand position)
self.sensitivity_multiplier = 1.0    # Movement sensitivity (shoulder width = full screen when 1.0)
self.click_cooldown_frames = 15      # Minimum frames between clicks (prevents double-click at 30fps)
```

#### Detection Logic:
1. **Only activates** when `is_in_menu_mode()` returns `True`
2. **Cursor Movement**: 
   - Uses **shoulder-width-based scaling** for sensitivity
   - Maps hand position relative to a center point (set when menu mode starts)
   - Moving hand by shoulder_width distance = cursor moves across full screen
   - Sensitivity can be adjusted via `sensitivity_multiplier`
3. **Smoothing**: 
   - Applies exponential moving average for stable cursor
   - `smoothing_factor = 0.7` means 70% current position, 30% previous position
   - Higher values = more responsive, lower values = smoother but slower
4. **Pinch Detection**: 
   - Calculates 3D Euclidean distance between thumb tip and index finger tip
   - Uses hysteresis to prevent flickering
   - Triggers left click when fingers come together (distance ≤ 0.015)
   - Includes click cooldown (15 frames) to prevent accidental double-clicks
   - Must release (distance > 0.06) before next click is allowed

#### Returns:
```python
{
    'action': 'cursor_move',
    'x': screen_x,
    'y': screen_y,
    'click': True/False  # True when pinch detected
}
```

### 2. **controls/keyboard_mouse.py** (MODIFIED)
Added two new methods to `MinecraftController` class:

```python
def set_cursor_position(self, x, y):
    """Set absolute cursor position for menu navigation."""
    self.mouse.position = (x, y)

def get_cursor_position(self):
    """Get current cursor position."""
    return self.mouse.position
```

### 3. **utils/action_coordinator.py** (MODIFIED)
Added cursor control handling in `_execute_menu_actions()`:

```python
# Handle cursor control for menu navigation
cursor_control = gesture_results.get('cursor_control')
if cursor_control:
    action = cursor_control.get('action')
    
    if action == 'cursor_move':
        # Move cursor to absolute position
        x = cursor_control.get('x')
        y = cursor_control.get('y')
        if x is not None and y is not None:
            self.controller.set_cursor_position(x, y)
        
        # Handle click if pinch detected
        if cursor_control.get('click'):
            self.controller.click_mouse('left')
```

### 4. **main.py** (MODIFIED)
- Added import: `from gestures.cursor_control import CursorControlDetector`
- Added to gesture_detectors dictionary:
  ```python
  'cursor_control': CursorControlDetector(),  # Right hand: menu cursor control
  ```

## How It Works

### User Interaction Flow:
1. **Open Inventory**: Perform left-hand crossing gesture (existing inventory gesture)
2. **Menu Mode Activated**: System detects cursor is visible and unlocked
3. **Cursor Control Active**: 
   - Move right hand to control cursor position
   - Cursor maps to screen coordinates (mirrored for natural feeling)
   - Movement is smoothed for stability
4. **Click Items**:
   - Pinch thumb and index finger together
   - System detects distance < threshold
   - Left click is triggered
5. **Exit Menu**: ESC gesture or inventory gesture again

### Platform Support:
- ✅ **Windows**: Uses ctypes to check cursor state
- ✅ **macOS**: Uses Quartz framework (CGCursorIsVisible)
- ⚠️ **Linux**: Fallback to always-on (needs platform-specific implementation)

## Technical Details

### Coordinate Mapping:
```python
# Shoulder-width-based scaling (relative to center position)
# Center position: Where your hand is when menu mode first activates

# Calculate relative movement from center
dx = center_x - hand_x  # Flipped for natural control
dy = hand_y - center_y

# Scale by sensitivity: shoulder_width movement = full screen
scale_x = screen_width / shoulder_width * sensitivity_multiplier
scale_y = screen_height / shoulder_width * sensitivity_multiplier

# Map to screen coordinates (center of screen + scaled offset)
screen_x = screen_width/2 + dx * scale_x
screen_y = screen_height/2 + dy * scale_y
```

**Example:**
```
Shoulder width = 0.2 (normalized)
Screen = 1920x1080
sensitivity_multiplier = 1.0

scale_x = 1920 / 0.2 * 1.0 = 9600

Moving hand 0.1 units right (half shoulder width):
  dx = -0.1 (flipped)
  screen_x = 960 + (-0.1 * 9600) = 960 - 960 = 0 (left edge)

Moving hand 0.1 units left (half shoulder width):
  dx = 0.1
  screen_x = 960 + (0.1 * 9600) = 960 + 960 = 1920 (right edge)
```

### Smoothing Algorithm:
Exponential Moving Average (EMA):
```python
smooth_x = last_x * (1 - α) + new_x * α
where α = smoothing_factor (0.7)

# This means:
smooth_x = last_x * 0.3 + new_x * 0.7
# 30% previous position + 70% current position = RESPONSIVE!
```

**Effect:**
- Higher α (0.7-1.0): More responsive, cursor follows hand directly
- Lower α (0.1-0.3): Smoother, cursor "glides" but lags behind hand
- Current setting (0.7): Good balance - responsive but not jittery

### Pinch Detection with Hysteresis:
```
Pinch Threshold:         0.015  ← Fingers come together (trigger click)
                         ↕ 0.045 hysteresis zone
Release Threshold:       0.060  ← Fingers separate (ready for next click)

Click Cooldown:          15 frames (0.5 seconds at 30fps)
```

**State Machine:**
```
READY → (distance ≤ 0.015) → CLICK! → PINCHING
PINCHING → (distance > 0.060) → READY
PINCHING → (try to click again) → Cooldown active, no click

After click:
- 15 frames must pass before next click allowed
- Must release pinch (distance > 0.06) 
- Then can click again
```

## Debug Output
The cursor control detector prints comprehensive debug information:
- `� [CURSOR] is_in_menu_mode() = True` - Menu mode detection status
- `🎮 [CURSOR] In menu mode, cursor control active` - Confirms activation
- `📍 [CURSOR] Center position set to (0.5, 0.6)` - Initial calibration point
- `🖱️  [CURSOR] Moving to (960, 540)` - Cursor coordinates being sent
- `👌 [CURSOR] READY | distance: 0.0350 (need: ≤0.0150)` - Distance when approaching
- `✅ [CURSOR] CLICK TRIGGERED! distance: 0.0140` - When click happens
- `🤏 [CURSOR] PINCHING | distance: 0.0145 (release: >0.0600)` - While holding pinch
- `👋 [CURSOR] Pinch RELEASED. Ready for next click.` - When released
- `⏳ [CURSOR] Pinch detected but in cooldown (12 frames left)` - Cooldown active
- `🖱️  [CONTROLLER] Cursor move: (800, 600) → (960, 540)` - Actual cursor movement
- `👆 [ACTION_COORD] Triggering left click!` - Click confirmation

## Usage Example

```python
# In menu mode (inventory open):
1. Open inventory (left-hand crossing gesture or press E)
2. System detects menu mode and sets center position
3. Position your right hand comfortably - this becomes your neutral position
4. Move hand left/right/up/down relative to this center
   - Moving by shoulder_width distance = cursor travels full screen
5. Bring thumb and index finger together → left click
6. Separate fingers → ready for next click
7. Wait for cooldown (15 frames) before clicking again
```

**Tips:**
- Keep hand at comfortable distance from body
- Small movements = precise cursor control
- Larger movements = quick cursor travel
- Touch fingers gently for reliable clicks
- Don't try to double-click rapidly - cooldown prevents it

## Benefits
- **Natural Interaction**: Hand position directly controls cursor
- **Precise Clicks**: Pinch gesture is intuitive and reliable with click cooldown
- **Cross-Platform**: Works on Windows and macOS
- **Responsive Movement**: High smoothing factor (0.7) provides direct control
- **Shoulder-Width Scaling**: Control sensitivity based on your body proportions
- **Mode-Aware**: Only activates in menu mode (no interference with gameplay)
- **Hysteresis**: Prevents accidental double-clicks with cooldown system
- **Center-Relative**: Cursor starts at screen center, natural hand positioning
- **Robust Detection**: Comprehensive debug output for troubleshooting

## Future Enhancements
- [ ] Add right-click support (different finger combination)
- [ ] Add scroll gesture (two-finger vertical movement)
- [ ] Make sensitivity adjustable via keyboard shortcut
- [ ] Add visual feedback overlay showing pinch state and cooldown
- [ ] Implement for Linux platforms
- [ ] Add dead zones for stability at center position
- [ ] Allow recalibration of center position with gesture
- [ ] Add drag-and-drop support (hold pinch while moving)
