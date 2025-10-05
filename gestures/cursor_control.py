"""
Cursor control gesture detector - controls mouse cursor in menu mode
"""

# moves by pixels gotta change later

import sys
import numpy as np
from gestures.base_detector import BaseGestureDetector


def is_in_menu_mode():
    """
    Returns True if the mouse cursor is visible and not captured,
    indicating that a game or app is likely in menu mode.

    Works on both Windows and macOS.
    """

    # --- WINDOWS IMPLEMENTATION ---
    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes

        CURSOR_SHOWING = 0x00000001

        class CURSORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("hCursor", wintypes.HANDLE),  # Use HANDLE instead of HCURSOR
                ("ptScreenPos", wintypes.POINT),
            ]

        # Check cursor visibility
        ci = CURSORINFO()
        ci.cbSize = ctypes.sizeof(CURSORINFO)
        ctypes.windll.user32.GetCursorInfo(ctypes.byref(ci))
        cursor_visible = (ci.flags & CURSOR_SHOWING) != 0

        # Check if cursor is clipped (locked)
        rect = wintypes.RECT()
        user32 = ctypes.windll.user32
        user32.GetClipCursor(ctypes.byref(rect))
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)

        cursor_unclipped = (
            rect.left == 0
            and rect.top == 0
            and rect.right == screen_w
            and rect.bottom == screen_h
        )

        return cursor_visible and cursor_unclipped

    # --- MACOS IMPLEMENTATION ---
    elif sys.platform == "darwin":
        from Quartz import CGCursorIsVisible
        # macOS games typically hide the cursor when locked,
        # so visible cursor = menu mode
        return CGCursorIsVisible()

    # --- UNSUPPORTED PLATFORMS ---
    else:
        # For Linux or others, fallback assumption
        return True  # assume visible/free by default


class CursorControlDetector(BaseGestureDetector):
    """
    Detects cursor control gestures for menu navigation.
    
    Logic:
    - Only active when cursor is visible and not captured (menu mode)
    - Tracks cursor position using right hand palm/wrist position
    - Detects pinch gesture (thumb tip + index finger tip) for left click
    - Uses MediaPipe hand landmark indices:
      * 4: Thumb tip
      * 8: Index finger tip
      * 0: Wrist
    """
    
    def __init__(self):
        super().__init__("cursor_control")
        
        # Configuration
        self.pinch_threshold = 0.015  # Distance threshold for pinch detection (in normalized coords) - SMALLER = more sensitive
        self.pinch_release_threshold = 0.06  # Distance to release pinch (add hysteresis)
        self.smoothing_factor = 0.7  # Smoothing for cursor movement (0=no smooth, 1=full smooth) - HIGHER = more responsive
        self.sensitivity_multiplier = 1.0  # Movement sensitivity (shoulder width = full screen when 1.0)
        self.click_cooldown_frames = 15  # Minimum frames between clicks (prevents double-click at 30fps)
        
        # Screen dimensions (will be set dynamically)
        self.screen_width = self._get_screen_width()
        self.screen_height = self._get_screen_height()
        
        # State tracking
        self._state = {
            'is_pinching': False,
            'last_cursor_x': None,
            'last_cursor_y': None,
            'last_wrist_pos': None,
            'center_pos': None,  # Center position for relative movement
            'shoulder_width': None,  # Cached shoulder width
            'click_cooldown': 0,  # Frames since last click
            'pinch_start_distance': None,  # Distance when pinch started
        }
    
    def _get_screen_width(self):
        """Get screen width based on platform."""
        if sys.platform.startswith("win"):
            import ctypes
            return ctypes.windll.user32.GetSystemMetrics(0)
        elif sys.platform == "darwin":
            from AppKit import NSScreen
            return int(NSScreen.mainScreen().frame().size.width)
        else:
            return 1920  # Default fallback
    
    def _get_screen_height(self):
        """Get screen height based on platform."""
        if sys.platform.startswith("win"):
            import ctypes
            return ctypes.windll.user32.GetSystemMetrics(1)
        elif sys.platform == "darwin":
            from AppKit import NSScreen
            return int(NSScreen.mainScreen().frame().size.height)
        else:
            return 1080  # Default fallback
    
    def _calculate_distance(self, pos1, pos2):
        """
        Calculate Euclidean distance between two 3D points.
        
        Args:
            pos1: (x, y, z) tuple for first position
            pos2: (x, y, z) tuple for second position
        
        Returns:
            Float: Distance between points, or None if positions are invalid
        """
        if pos1 is None or pos2 is None:
            return None
        
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        dz = pos1[2] - pos2[2]
        
        return np.sqrt(dx**2 + dy**2 + dz**2)
    
    def _get_shoulder_width(self, state_manager):
        """
        Calculate shoulder width for scaling.
        
        Returns:
            Float: Distance between shoulders, or None
        """
        left_shoulder = state_manager.get_landmark_position('left_shoulder', frame_offset=0)
        right_shoulder = state_manager.get_landmark_position('right_shoulder', frame_offset=0)
        
        if left_shoulder is None or right_shoulder is None:
            return None
        
        dx = right_shoulder[0] - left_shoulder[0]
        dy = right_shoulder[1] - left_shoulder[1]
        shoulder_width = np.sqrt(dx**2 + dy**2)
        
        return shoulder_width
    
    def _map_hand_to_screen(self, hand_pos, center_pos, shoulder_width):
        """
        Map hand position to screen coordinates using shoulder-width-based scaling.
        
        Args:
            hand_pos: (x, y, z) tuple with normalized coordinates
            center_pos: (x, y) tuple for center/neutral position
            shoulder_width: Float, distance between shoulders
        
        Returns:
            (screen_x, screen_y) tuple, or None if invalid
        """
        if hand_pos is None or center_pos is None or shoulder_width is None or shoulder_width == 0:
            return None
        
        # Calculate relative movement from center
        # Positive dx = hand moved right, negative = left
        dx = center_pos[0] - hand_pos[0]  # Flip for natural control
        dy = hand_pos[1] - center_pos[1]
        
        # Scale by sensitivity: shoulder_width movement = full screen width
        # So dx of shoulder_width should move cursor screen_width pixels
        scale_x = self.screen_width / shoulder_width * self.sensitivity_multiplier
        scale_y = self.screen_height / shoulder_width * self.sensitivity_multiplier
        
        # Calculate screen position (center of screen + scaled offset)
        screen_x = int(self.screen_width / 2 + dx * scale_x)
        screen_y = int(self.screen_height / 2 + dy * scale_y)
        
        # Clamp to screen bounds
        screen_x = max(0, min(screen_x, self.screen_width - 1))
        screen_y = max(0, min(screen_y, self.screen_height - 1))
        
        return (screen_x, screen_y)
    
    def _smooth_position(self, new_pos, last_pos):
        """
        Apply smoothing to cursor position for stability.
        
        Args:
            new_pos: (x, y) tuple for new position
            last_pos: (x, y) tuple for last position (or None)
        
        Returns:
            Smoothed (x, y) tuple
        """
        if last_pos is None:
            return new_pos
        
        # Exponential moving average
        smooth_x = int(last_pos[0] * (1 - self.smoothing_factor) + new_pos[0] * self.smoothing_factor)
        smooth_y = int(last_pos[1] * (1 - self.smoothing_factor) + new_pos[1] * self.smoothing_factor)
        
        return (smooth_x, smooth_y)
    
    def detect(self, state_manager):
        """
        Detect cursor control gestures from right hand.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Dictionary with action type or None:
            - {'action': 'cursor_move', 'x': screen_x, 'y': screen_y} - Move cursor
            - {'action': 'cursor_click'} - Left click
            - None - No cursor control needed or not in menu mode
        """
        if not self.enabled:
            return None
        
        # Only operate in menu mode
        in_menu = is_in_menu_mode()
        print(f"🔍 [CURSOR] is_in_menu_mode() = {in_menu}")
        if not in_menu:
            self._state['last_cursor_x'] = None
            self._state['last_cursor_y'] = None
            return None
        
        # Debug: Print that we're in menu mode
        print(f"🎮 [CURSOR] In menu mode, cursor control active")
        
        # Get right hand landmarks (MediaPipe hand tracking)
        # MediaPipe hand landmark names:
        # - Wrist: right_wrist (from pose) or can use hand landmark 0
        # - Thumb tip: right_thumb_tip (landmark 4)
        # - Index finger tip: right_index_finger_tip (landmark 8)
        right_wrist = state_manager.get_landmark_position('right_wrist', frame_offset=0)
        right_thumb_tip = state_manager.get_landmark_position('right_thumb_tip', frame_offset=0)
        right_index_tip = state_manager.get_landmark_position('right_index_finger_tip', frame_offset=0)
        
        if right_wrist is None:
            # No hand detected
            self._state['last_cursor_x'] = None
            self._state['last_cursor_y'] = None
            return None
        
        # Convert numpy arrays to tuples
        wrist_pos = tuple(right_wrist)
        
        # Get shoulder width for scaling
        shoulder_width = self._get_shoulder_width(state_manager)
        if shoulder_width is None:
            print(f"⚠️  [CURSOR] Cannot detect shoulder width")
            return None
        
        # Cache shoulder width
        self._state['shoulder_width'] = shoulder_width
        
        # Set or update center position (neutral position)
        if self._state['center_pos'] is None:
            # First time - set current wrist position as center
            self._state['center_pos'] = (wrist_pos[0], wrist_pos[1])
            print(f"📍 [CURSOR] Center position set to {self._state['center_pos']}")
        
        # Map wrist position to screen coordinates using shoulder-width scaling
        screen_pos = self._map_hand_to_screen(wrist_pos, self._state['center_pos'], shoulder_width)
        
        if screen_pos is None:
            return None
        
        # Apply smoothing
        last_pos = None
        if self._state['last_cursor_x'] is not None and self._state['last_cursor_y'] is not None:
            last_pos = (self._state['last_cursor_x'], self._state['last_cursor_y'])
        
        smooth_pos = self._smooth_position(screen_pos, last_pos)
        self._state['last_cursor_x'] = smooth_pos[0]
        self._state['last_cursor_y'] = smooth_pos[1]
        
        # Debug: Print cursor position
        print(f"🖱️  [CURSOR] Moving to ({smooth_pos[0]}, {smooth_pos[1]})")
        
        # Check for pinch gesture (thumb + index finger)
        pinch_detected = False
        
        # Decrement click cooldown
        if self._state['click_cooldown'] > 0:
            self._state['click_cooldown'] -= 1
        
        if right_thumb_tip is not None and right_index_tip is not None:
            thumb_pos = tuple(right_thumb_tip)
            index_pos = tuple(right_index_tip)
            
            pinch_distance = self._calculate_distance(thumb_pos, index_pos)
            
            if pinch_distance is not None:
                # State machine for pinch detection with hysteresis
                current_state = "PINCHING" if self._state['is_pinching'] else "READY"
                
                if not self._state['is_pinching']:
                    # Not currently pinching - check if we should start
                    if pinch_distance <= self.pinch_threshold:
                        if self._state['click_cooldown'] == 0:
                            # Trigger click!
                            self._state['is_pinching'] = True
                            self._state['pinch_start_distance'] = pinch_distance
                            pinch_detected = True
                            self._state['click_cooldown'] = self.click_cooldown_frames
                            print(f"✅ [CURSOR] CLICK TRIGGERED! distance: {pinch_distance:.4f} (threshold: {self.pinch_threshold:.4f})")
                        else:
                            print(f"⏳ [CURSOR] Pinch detected but in cooldown ({self._state['click_cooldown']} frames left)")
                    else:
                        # Print distance when not pinching (less verbose)
                        if pinch_distance < self.pinch_threshold * 2:  # Only print when getting close
                            print(f"� [CURSOR] {current_state} | distance: {pinch_distance:.4f} (need: ≤{self.pinch_threshold:.4f})")
                else:
                    # Currently pinching - check if we should release
                    print(f"🤏 [CURSOR] {current_state} | distance: {pinch_distance:.4f} (release: >{self.pinch_release_threshold:.4f})")
                    if pinch_distance > self.pinch_release_threshold:
                        self._state['is_pinching'] = False
                        self._state['pinch_start_distance'] = None
                        print(f"👋 [CURSOR] Pinch RELEASED. Ready for next click.")
        else:
            print(f"⚠️  [CURSOR] Missing finger landmarks (thumb: {right_thumb_tip is not None}, index: {right_index_tip is not None})")
        
        # Return cursor control action
        result = {
            'action': 'cursor_move',
            'x': smooth_pos[0],
            'y': smooth_pos[1],
        }
        
        # Add click action if pinch just occurred
        if pinch_detected:
            result['click'] = True
        
        return result
    
    def reset(self):
        """Reset cursor control detector state."""
        self._state = {
            'is_pinching': False,
            'last_cursor_x': None,
            'last_cursor_y': None,
            'last_wrist_pos': None,
            'center_pos': None,  # Reset center position
            'shoulder_width': None,
            'click_cooldown': 0,
            'pinch_start_distance': None,
        }
