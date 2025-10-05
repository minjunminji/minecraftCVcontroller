# Troubleshooting Guide

## Issue: Actions Stop Working During Testing

### Problem Description
Gestures are being detected correctly, but actions (keyboard/mouse inputs) stop working midway through testing. The HUD shows gestures being recognized, but Minecraft doesn't respond to the controls.

### Root Causes
1. **Silent exceptions in controller**: The pynput library can throw exceptions on Windows when:
   - The target application loses focus
   - Administrator privileges are required
   - Anti-cheat software interferes
   - Windows security settings block input simulation

2. **State corruption**: If a key press succeeds but the release fails, the controller thinks the key is still pressed and won't press it again.

3. **Missing error visibility**: Errors were being caught silently without user notification.

### Fixes Implemented

#### 1. Enhanced Error Handling in Controller (`controls/keyboard_mouse.py`)
- Added comprehensive error logging with stack traces
- Improved state management to prevent stuck keys/buttons
- If a release operation fails, the key/button is still removed from the internal state to prevent permanent "stuck" state

#### 2. Action Coordinator Error Recovery (`main.py`)
- Wrapped `action_coordinator.execute()` in try-except block
- Automatic reset of coordinator when errors occur
- Error messages are displayed in the console with full stack traces

#### 3. Visual Error Feedback (HUD)
- Orange error banner appears at the bottom of the HUD when controller errors occur
- Shows error message in real-time
- Auto-clears after 3 seconds if no new errors

#### 4. Recovery Mechanism
- Press **'R'** to toggle gestures OFF and back ON to reset the system
- Automatically releases all active controls when disabling gestures
- Clears error state when toggling gestures

### How to Use

1. **Monitor Console Output**: Watch for `⚠ Error` messages with stack traces
2. **Check HUD**: Look for orange error banner at bottom of screen
3. **Quick Recovery**: Press 'R' twice (OFF then ON) to reset the system
4. **If Persists**: Check these common issues:

### Common Issues & Solutions

#### Issue: "Permission Denied" errors on Windows
**Solution**: Run the application as Administrator
```bash
# Run PowerShell as Admin, then:
cd "C:\Users\ryank\Documents\Code\hellohacks"
python main.py
```

#### Issue: Actions work initially but stop after Minecraft window is focused
**Solution**: This is a Windows security feature. Either:
- Run script as Administrator
- Or keep the camera window visible and click on it periodically to maintain focus

#### Issue: Keys get "stuck" (character keeps moving)
**Solution**: 
1. Press 'R' to disable gestures (releases all keys)
2. Press 'R' again to re-enable

#### Issue: pynput errors about X11 display (Linux)
**Solution**: Ensure you're running in a graphical environment, not SSH/headless

### Diagnostic Mode

When testing, watch the console for these patterns:

**Normal Operation:**
```
✓ Action coordinator reset after error
```

**Controller Errors:**
```
⚠ Error pressing key w: <error message>
[Full stack trace]
```

**Action Execution Errors:**
```
⚠ ERROR in action execution: <error message>
[Full stack trace]
✓ Action coordinator reset after error
```

### Prevention Tips

1. **Keep Camera Window Visible**: The always-on-top window helps maintain focus
2. **Run as Administrator**: Especially on Windows with UAC enabled
3. **Close Conflicting Software**: Disable macro recorders, anti-cheat overlays temporarily
4. **Use 'R' Key Liberally**: Don't hesitate to toggle gestures OFF/ON to reset state
5. **Monitor HUD**: Watch for error messages and respond quickly

### Still Having Issues?

If actions continue to stop working:

1. Check console output for specific error messages
2. Try running as Administrator
3. Verify pynput is installed correctly: `pip install --upgrade pynput`
4. On Windows, check if UAC or Windows Defender is blocking input simulation
5. Test with a simple application (Notepad) before Minecraft to verify controller works

### Advanced: Force Reset Everything

If all else fails, press 'R' to disable gestures, then restart the application:
```python
# The finally block in main.py ensures clean shutdown:
# - Releases all game controls
# - Releases webcam
# - Cleans up MediaPipe
```

