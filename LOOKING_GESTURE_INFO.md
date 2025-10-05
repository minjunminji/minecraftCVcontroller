# Looking Gesture - Head Tilt Mouse Control

## Overview

The looking gesture allows you to control the mouse cursor by tilting your head in any direction, like using your head as a joystick. It supports both horizontal (left/right) and vertical (up/down) movement.

## How It Works

### Facial Landmarks Used
- **Left side**: Distance between face edge (landmark 127) and left eye outer corner (landmark 33)
- **Right side**: Distance between face edge (landmark 356) and right eye outer corner (landmark 263)

### Detection Logic

#### Horizontal Control (Left/Right)
- Uses **X-axis (horizontal) distance** between landmarks
- When you rotate your head **left**, the right side of your face becomes more visible (right X distance increases)
  - This triggers mouse movement to the **left**
- When you rotate your head **right**, the left side of your face becomes more visible (left X distance increases)
  - This triggers mouse movement to the **right**

#### Vertical Control (Up/Down)
- Uses **Y-axis (vertical) SIGNED distance** between landmarks
- Calculates average Y distance from both sides (positive or negative)
- **Tilt UP**: The eye canthus moves above the face edge
  - Average Y distance becomes **negative**
  - Requires threshold: If Y < -(y_threshold + y_deadzone) → Mouse moves **up**
- **Tilt DOWN**: The eye canthus moves below the face edge
  - Average Y distance becomes **positive**
  - **No threshold required**: If Y > 0 → Mouse moves **down** immediately

## Adjustable Parameters

All parameters can be adjusted in `gestures/looking.py` in the `__init__` method:

### Horizontal (Left/Right) Control

#### 1. `tilt_multiplier` (default: 1.15)
- **What it does**: Determines how much head rotation is needed to trigger movement
- **Higher value** = Need to rotate head more to trigger movement (less sensitive)
- **Lower value** = Less rotation needed (more sensitive)
- **Recommended range**: 1.10 to 1.30

#### 2. `deadzone` (default: 0.3)
- **What it does**: Creates a neutral zone where small head movements are ignored
- **Higher value** = Larger deadzone, more stable but less responsive
- **Lower value** = Smaller deadzone, more responsive but may drift
- **Recommended range**: 0.1 to 0.5

### Vertical (Up/Down) Control

#### 3. `y_threshold` (default: 0.02)
- **What it does**: Y distance threshold to trigger **upward** movement only
- **Note**: Downward movement triggers immediately when canthus is below face edge (no threshold)
- **Higher value** = Need to tilt head up more to trigger
- **Lower value** = More sensitive upward detection
- **Recommended range**: 0.01 to 0.05

#### 4. `y_deadzone` (default: 0.005)
- **What it does**: Creates a neutral zone for vertical movement
- **Higher value** = Larger deadzone, more stable
- **Lower value** = Smaller deadzone, more responsive
- **Recommended range**: 0.001 to 0.01

### Movement Speed

#### 5. `mouse_speed` (default: 2)
- **What it does**: Constant movement speed in units per frame
- **Higher value** = Faster mouse movement
- **Lower value** = Slower mouse movement
- **Note**: This is further multiplied by `HEAD_LOOK_SENSITIVITY` (5.0) in the action coordinator
- **Final speed** = `mouse_speed × HEAD_LOOK_SENSITIVITY` pixels per frame
- **Recommended range**: 1 to 5

## Global Sensitivity Adjustment

You can also adjust the overall sensitivity in `utils/action_coordinator.py`:

```python
HEAD_LOOK_SENSITIVITY = 5.0  # Global multiplier for all head movement
HEAD_LOOK_DEADZONE = 0.01    # Additional deadzone check (usually fine at default)
```

## Testing Tips

### General
1. **Start with defaults** and test how it feels
2. If movement is **too fast**: Reduce `mouse_speed` or `HEAD_LOOK_SENSITIVITY`
3. If movement is **too slow**: Increase `mouse_speed` or `HEAD_LOOK_SENSITIVITY`

### Horizontal Control (Left/Right)
4. If it's **triggering when you don't want**: Increase `tilt_multiplier` or `deadzone`
5. If it's **not triggering enough**: Decrease `tilt_multiplier` or `deadzone`

### Vertical Control (Up/Down)
6. Watch the **Avg_Y** value in the HUD (negative = up, positive = down)
7. **Downward** movement triggers immediately when Y > 0 (canthus below face edge)
8. If **upward** movement triggers too easily: Increase `y_threshold`
9. If **upward** movement is not sensitive enough: Decrease `y_threshold`
10. If you want a **larger neutral zone** for upward movement: Increase `y_deadzone`

## Usage

1. Enable gestures by pressing `r` in the application
2. Face the camera and tilt your head in any direction:
   - **Tilt left/right** → Mouse moves horizontally
   - **Tilt up/down** → Mouse moves vertically
   - **Diagonal tilts** → Mouse moves diagonally
3. The mouse will move continuously while your head is tilted
4. Return head to neutral position to stop movement

## Debug Information

When debug display is enabled (press `d`), you'll see the looking gesture info showing:

**Horizontal (L/R) Control:**
- X distances for left and right sides
- X ratio being used for detection
- Threshold and deadzone values

**Vertical (U/D) Control:**
- Average Y distance (signed: negative = up, positive = down)
- Threshold for upward movement (downward has no threshold)
- Shows "Up: Y < -threshold" and "Down: Y > 0"

**Color coding:**
- **Green text** = Mouse is actively moving
- **Gray text** = Head is in neutral position

## Implementation Files

- **Detector**: `gestures/looking.py` - The main detection logic
- **Integration**: `main.py` - Lines 24, 86, 176-177 - Import and registration
- **Action Handler**: `utils/action_coordinator.py` - Lines 249-262 - Mouse movement execution

