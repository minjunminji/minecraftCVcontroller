# Menu Mode Behavior - Complete Documentation

## ✅ System Working As Designed

**Key Point:** In menu mode, gestures are still DETECTED but only menu-specific gestures are ACTED upon.

---

## How It Works

### Gesture Detection vs. Gesture Action

There's an important distinction:

1. **Gesture Detection** (always runs)
   - All gesture detectors run continuously
   - Gestures appear in the HUD under "GESTURES"
   - This is necessary to detect the menu close gesture

2. **Gesture Actions** (mode-specific)
   - Only relevant gestures trigger actions based on current mode
   - Gameplay mode: All gameplay gestures trigger actions
   - Menu mode: ONLY menu gestures trigger actions

---

## Menu Mode: Allowed Gestures

When in **MENU MODE**, the action coordinator (`_execute_menu_actions`) processes ONLY:

### ✅ **1. Menu Close Gesture** (Left Hand)
- **Gesture:** Swipe left hand RIGHT → LEFT
- **Detector:** `MenuCloseDetector`
- **Action:** `menu_close`
- **Effect:** Exits menu, returns to gameplay

### ✅ **2. Cursor Control** (Right Hand)
- **Gesture:** Right hand position
- **Detector:** `CursorControlDetector`
- **Action:** `cursor_move`
- **Effect:** Moves cursor to navigate menus
- **Pinch:** Click menu items

---

## Menu Mode: IGNORED Gestures

When in **MENU MODE**, the following gestures are DETECTED but NO ACTIONS are performed:

### ❌ **Right Hand Gestures - ALL IGNORED**
- ❌ `attack` - Attack gesture (NO left click)
- ❌ `mining` - Mining gesture (NO left click hold)
- ❌ `placing` - Placing gesture (NO right click)

**Why detected but ignored?**
- The gesture detectors still run (they don't know about modes)
- But `_execute_menu_actions()` doesn't call `_handle_right_hand_actions()`
- So the gestures show in HUD but don't trigger any actions

### ❌ **Left Hand Gestures - MOSTLY IGNORED**
- ✅ `menuclose` - Menu close (ACTS - exits menu)
- ❌ `inventory` - Inventory open (IGNORED - already in menu)
- ❌ `shield` - Shield block (IGNORED - gameplay action)

**Why detected but ignored?**
- `_execute_menu_actions()` checks left hand gestures
- But ONLY processes `menu_close` action
- All other actions are explicitly ignored

### ❌ **Movement Gestures - ALL IGNORED**
- ❌ Movement (W/A/S/D)
- ❌ Jumping
- ❌ Sprinting
- ❌ Sneaking

**Why detected but ignored?**
- `_execute_menu_actions()` doesn't call `_handle_movement()` or `_handle_jumping()`
- Movement actions don't execute in menu mode

---

## Code Architecture

### Main Loop (`main.py`)

```python
# STEP 3: Run gesture detection (ALWAYS - regardless of mode)
gesture_results = {}
if landmarks_dict is not None and gestures_enabled:
    for name, detector in gesture_detectors.items():
        result = detector.detect(state_manager)
        if result is not None:
            gesture_results[name] = result  # All gestures collected

# STEP 4: Execute actions (MODE-SPECIFIC)
action_coordinator.execute(gesture_results, state_manager)
```

### Action Coordinator (`action_coordinator.py`)

```python
def execute(self, gesture_results, state_manager):
    if self.current_mode == 'gameplay':
        self._execute_gameplay_actions(gesture_results, state_manager)
        # Calls all handlers: movement, jumping, left_hand, right_hand, etc.
    
    elif self.current_mode == 'menu':
        self._execute_menu_actions(gesture_results, state_manager)
        # ONLY processes: menu_close and cursor_control
        # IGNORES: attack, mining, placing, shield, movement, etc.
```

### Menu Actions Handler

```python
def _execute_menu_actions(self, gesture_results, state_manager):
    """
    In menu mode, ONLY the following gestures are processed:
    - menu_close (left hand): Exit menu
    - cursor_control (right hand): Navigate menus
    
    ALL other gestures are IGNORED.
    """
    
    # 1. Check for menu exit gesture ONLY
    left_hand = gesture_results.get('left_hand')
    if left_hand:
        if menu_hand_action == 'menu_close':
            self._exit_menu_mode()  # ✅ ACTS
            return
        # All other left hand actions ignored ❌
    
    # 2. Handle cursor control for menu navigation
    cursor_control = gesture_results.get('cursor_control')
    if cursor_control:
        # Process cursor movement and clicks ✅
        ...
    
    # 3. Right hand gameplay gestures are NOT processed here ❌
    # (_handle_right_hand_actions is NOT called)
```

---

## What You'll See in HUD

### In Menu Mode:

```
MODE: MENU                                       ← Cyan color
→ Swipe left hand RIGHT-TO-LEFT to exit menu    ← Exit hint

GESTURES:                                        ← Detection section
  menuclose: Menu Close                          ← Cyan when detected
  attack: Attack Click                           ← May appear but IGNORED
  mining: Mining Click                           ← May appear but IGNORED
  cursor_control: Cursor Move                    ← Active in menu

ACTIONS:                                         ← Actions section
  [Should be empty except cursor movements]      ← Nothing held
```

**Key Points:**
- Gestures may appear under "GESTURES" section
- But "ACTIONS" section shows what's actually being executed
- In menu mode, ACTIONS should be empty (no held keys/buttons)

---

## Testing & Verification

### Test 1: Attack Gesture in Menu Mode ✅

1. Enter menu mode (inventory gesture)
2. Perform attack gesture (horizontal punch)
3. **Expected HUD:**
   - `GESTURES:` shows `attack: Attack Click`
   - `ACTIONS:` remains empty (no left click)
4. **Expected Behavior:** NO left click occurs
5. **Result:** ✅ Attack gesture IGNORED in menu mode

### Test 2: Mining Gesture in Menu Mode ✅

1. Enter menu mode
2. Perform mining gesture (arm swinging)
3. **Expected HUD:**
   - `GESTURES:` shows `mining: Mining Start Hold` or similar
   - `ACTIONS:` remains empty
4. **Expected Behavior:** NO left click hold
5. **Result:** ✅ Mining gesture IGNORED in menu mode

### Test 3: Menu Close Gesture Works ✅

1. Enter menu mode
2. Perform menu close gesture (RIGHT → LEFT swipe)
3. **Expected HUD:**
   - `GESTURES:` shows `menuclose: Menu Close` in CYAN
   - `MODE:` changes from MENU to GAMEPLAY
4. **Expected Console:**
   ```
   [ACTION COORDINATOR] Menu close gesture detected (source: menuclose)
   [ACTION COORDINATOR] Exiting menu mode
   ```
5. **Expected Behavior:** Menu closes, return to gameplay
6. **Result:** ✅ Menu close gesture WORKS in menu mode

### Test 4: Cursor Control Works in Menu Mode ✅

1. Enter menu mode
2. Move right hand around
3. **Expected:** Cursor follows hand position
4. **Expected:** Pinch gesture triggers click
5. **Result:** ✅ Cursor control WORKS in menu mode

---

## Summary Table

| Gesture | Detector Runs? | Shows in HUD? | Action Executes in Menu? |
|---------|---------------|---------------|--------------------------|
| Menu Close | ✅ Yes | ✅ Yes | ✅ **YES** - Exits menu |
| Cursor Control | ✅ Yes | ✅ Yes | ✅ **YES** - Moves cursor |
| Attack | ✅ Yes | ✅ Yes | ❌ **NO** - Ignored |
| Mining | ✅ Yes | ✅ Yes | ❌ **NO** - Ignored |
| Placing | ✅ Yes | ✅ Yes | ❌ **NO** - Ignored |
| Shield | ✅ Yes | ✅ Yes | ❌ **NO** - Ignored |
| Inventory Open | ✅ Yes | ✅ Yes | ❌ **NO** - Ignored |
| Movement | ✅ Yes | ✅ Yes | ❌ **NO** - Ignored |

---

## Why This Design?

### Q: Why do gesture detectors still run in menu mode?

**A:** Because we need to detect the menu close gesture! If we disabled all gesture detection in menu mode, you'd be stuck in the menu forever.

### Q: Why do ignored gestures show in the HUD?

**A:** The HUD shows what's being DETECTED (for debugging). To see what's being ACTED upon, look at the "ACTIONS" section (pressed keys/buttons).

### Q: Can I disable gesture detection in menu mode?

**A:** Not recommended - you need at least the menu close gesture to exit. The current design (detect all, act on few) is the safest approach.

### Q: Why not disable specific detectors in menu mode?

**A:** 
1. Gesture detectors don't have mode awareness
2. They're lightweight and don't affect performance
3. The detection/action separation is cleaner architecture
4. It allows for debugging (you can see all gestures even if not acting)

---

## Console Output Examples

### Entering Menu Mode:
```
[ACTION COORDINATOR] Inventory gesture detected, entering menu mode
[ACTION COORDINATOR] Entering menu mode (open_inventory=True)
```

### In Menu Mode (gestures detected but ignored):
```
(No output - gestures detected but no actions executed)
```

### Exiting Menu Mode:
```
[ACTION COORDINATOR] Menu close gesture detected (source: menuclose)
[ACTION COORDINATOR] Exiting menu mode
```

---

## Conclusion

✅ **The system is working correctly:**

1. **All gestures are DETECTED** in both modes (necessary for menu close)
2. **Only relevant gestures EXECUTE ACTIONS** based on mode:
   - Gameplay mode: All gameplay gestures execute
   - Menu mode: Only menu close + cursor control execute
3. **HUD shows detection** (GESTURES section) vs **execution** (ACTIONS section)
4. **Menu close gesture works** to exit menu mode
5. **Gameplay gestures are safely ignored** in menu mode

**To exit menu mode:** Swipe your left hand from **RIGHT to LEFT**.

