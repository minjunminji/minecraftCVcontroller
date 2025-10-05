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
        self.pinch_threshold = 0.06  # Distance threshold for pinch detection (in normalized coords) - SMALLER = more sensitive
        self.pinch_release_threshold = 0.06  # Distance to release pinch (add hysteresis)
        self.freeze_threshold = 0.10  # Distance to freeze cursor movement (preparing for click)
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
            'cursor_frozen': False,  # True when cursor movement is frozen for clicking
            'frozen_cursor_x': None,  # Frozen cursor position
            'frozen_cursor_y': None,
        }
    
    def _get_screen_width(self):
        """Get screen width based on platform."""
        if sys.platform.startswith("win"):
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            # Ensure DPI awareness so metrics return physical pixels
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
            width = user32.GetSystemMetrics(0)
            if width <= 0:
                # Fallback: use desktop window rect
                try:
                    rect = wintypes.RECT()
                    hwnd = user32.GetDesktopWindow()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    width = rect.right - rect.left
                except Exception:
                    width = 1920  # sensible default
            return int(width) if width and width > 0 else 1920
        elif sys.platform == "darwin":
            from AppKit import NSScreen
            return int(NSScreen.mainScreen().frame().size.width)
        else:
            return 1920  # Default fallback
    
    def _get_screen_height(self):
        """Get screen height based on platform."""
        if sys.platform.startswith("win"):
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            # Ensure DPI awareness so metrics return physical pixels
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
            height = user32.GetSystemMetrics(1)
            if height <= 0:
                # Fallback: use desktop window rect
                try:
                    rect = wintypes.RECT()
                    hwnd = user32.GetDesktopWindow()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    height = rect.bottom - rect.top
                except Exception:
                    height = 1080  # sensible default
            return int(height) if height and height > 0 else 1080
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
        Map finger position to absolute screen coordinates using a 16:9 control
        rectangle centered on the right shoulder. The rectangle's total width is
        (2.5 × shoulder distance) in normalized space; height is set to keep 16:9.

        Args:
            hand_pos: (x, y, z) tuple for the controlling point (index fingertip preferred)
            center_pos: (x, y) tuple for the right shoulder position
            shoulder_width: Float distance between shoulders in normalized coords

        Returns:
            (screen_x, screen_y) tuple, or None if invalid
        """
        if hand_pos is None or center_pos is None or shoulder_width is None or shoulder_width <= 0:
            return None

        # Define control rectangle dimensions in normalized coordinates
        control_width_norm = shoulder_width * 2.5 * self.sensitivity_multiplier
        control_height_norm = control_width_norm * 9.0 / 16.0

        if control_width_norm <= 1e-6 or control_height_norm <= 1e-6:
            return None

        half_w = control_width_norm / 2.0
        half_h = control_height_norm / 2.0

        # Relative movement from right shoulder center
        # Flip X for natural control; Y positive is down in image/screen space
        dx = center_pos[0] - hand_pos[0]
        dy = hand_pos[1] - center_pos[1]

        # Clamp within the control rectangle
        if dx < -half_w:
            dx = -half_w
        elif dx > half_w:
            dx = half_w

        if dy < -half_h:
            dy = -half_h
        elif dy > half_h:
            dy = half_h

        # Normalize to [-1, 1] within the rectangle
        rel_x = dx / half_w
        rel_y = dy / half_h

        # Map to full screen dimensions (rectangle maps to whole screen)
        screen_x = int(self.screen_width / 2 + rel_x * (self.screen_width / 2))
        screen_y = int(self.screen_height / 2 + rel_y * (self.screen_height / 2))

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
        if not in_menu:
            self._state['last_cursor_x'] = None
            self._state['last_cursor_y'] = None
            return None
        
        # In menu mode, cursor control is active
        
        # Get right hand landmarks (MediaPipe hand tracking)
        # MediaPipe hand landmark names:
        # - Wrist: right_wrist (from pose) or can use hand landmark 0
        # - Thumb tip: right_thumb_tip (landmark 4)
        # - Index finger tip: right_index_finger_tip (landmark 8)
        right_thumb_tip = state_manager.get_landmark_position('right_thumb_tip', frame_offset=0)
        right_index_tip = state_manager.get_landmark_position('right_index_finger_tip', frame_offset=0)
        
        # Require both thumb tip and index tip for control
        if right_thumb_tip is None or right_index_tip is None:
            self._state['last_cursor_x'] = None
            self._state['last_cursor_y'] = None
            return None
        
        # Get shoulder width for scaling
        shoulder_width = self._get_shoulder_width(state_manager)
        if shoulder_width is None:
            return None
        
        # Ensure screen dimensions are valid (guard against 0/None)
        if not isinstance(self.screen_width, int) or self.screen_width <= 1:
            self.screen_width = self._get_screen_width()
        if not isinstance(self.screen_height, int) or self.screen_height <= 1:
            self.screen_height = self._get_screen_height()

        # Cache shoulder width
        self._state['shoulder_width'] = shoulder_width
        
        # Get right shoulder position to serve as dynamic center
        right_shoulder = state_manager.get_landmark_position('right_shoulder', frame_offset=0)
        if right_shoulder is None:
            return None
        center_pos = (float(right_shoulder[0]), float(right_shoulder[1]))
        if self._state['center_pos'] is None:
            self._state['center_pos'] = center_pos
        else:
            # Continuously update center to follow shoulder motion
            self._state['center_pos'] = center_pos
        
        # Cursor controlled by midpoint between thumb tip and index tip
        thumb_pos = tuple(right_thumb_tip)
        index_pos = tuple(right_index_tip)
        controlling_pos = (
            (thumb_pos[0] + index_pos[0]) / 2.0,
            (thumb_pos[1] + index_pos[1]) / 2.0,
            (thumb_pos[2] + index_pos[2]) / 2.0,
        )

        # Before mapping, ensure the wrist is inside the control rectangle
        control_width_norm = shoulder_width * 2.5 * self.sensitivity_multiplier
        control_height_norm = control_width_norm * 9.0 / 16.0
        half_w = control_width_norm / 2.0
        half_h = control_height_norm / 2.0

        dx = self._state['center_pos'][0] - controlling_pos[0]
        dy = controlling_pos[1] - self._state['center_pos'][1]
        if abs(dx) > half_w or abs(dy) > half_h:
            # Outside control area: fully disable cursor control this frame
            self._state['last_cursor_x'] = None
            self._state['last_cursor_y'] = None
            return None

        # Map wrist position within 16:9 rectangle (centered at shoulder) to full screen
        screen_pos = self._map_hand_to_screen(controlling_pos, self._state['center_pos'], shoulder_width)
        
        if screen_pos is None:
            return None
        
        # Check for pinch gesture (thumb + index finger) and freeze logic
        pinch_detected = False
        pinch_distance = None
        
        # Decrement click cooldown
        if self._state['click_cooldown'] > 0:
            self._state['click_cooldown'] -= 1
        
        if right_thumb_tip is not None and right_index_tip is not None:
            thumb_pos = tuple(right_thumb_tip)
            index_pos = tuple(right_index_tip)
            pinch_distance = self._calculate_distance(thumb_pos, index_pos)
        
        # Determine if cursor should be frozen
        cursor_should_freeze = False
        if pinch_distance is not None and pinch_distance <= self.freeze_threshold:
            cursor_should_freeze = True
        
        # Handle cursor freeze/unfreeze transitions
        if cursor_should_freeze and not self._state['cursor_frozen']:
            # Entering freeze state - save current cursor position
            self._state['cursor_frozen'] = True
            self._state['frozen_cursor_x'] = self._state['last_cursor_x']
            self._state['frozen_cursor_y'] = self._state['last_cursor_y']
        elif not cursor_should_freeze and self._state['cursor_frozen']:
            # Exiting freeze state - resume normal cursor tracking
            self._state['cursor_frozen'] = False
            self._state['frozen_cursor_x'] = None
            self._state['frozen_cursor_y'] = None
        
        # Determine final cursor position
        if self._state['cursor_frozen']:
            # Use frozen position
            final_x = self._state['frozen_cursor_x']
            final_y = self._state['frozen_cursor_y']
        else:
            # Apply smoothing and update cursor position normally
            last_pos = None
            if self._state['last_cursor_x'] is not None and self._state['last_cursor_y'] is not None:
                last_pos = (self._state['last_cursor_x'], self._state['last_cursor_y'])
            
            smooth_pos = self._smooth_position(screen_pos, last_pos)
            self._state['last_cursor_x'] = smooth_pos[0]
            self._state['last_cursor_y'] = smooth_pos[1]
            final_x = smooth_pos[0]
            final_y = smooth_pos[1]
        
        # Check for pinch click
        if pinch_distance is not None:
            if not self._state['is_pinching']:
                # Not currently pinching - check if we should start
                if pinch_distance <= self.pinch_threshold:
                    if self._state['click_cooldown'] == 0:
                        # Trigger click!
                        self._state['is_pinching'] = True
                        self._state['pinch_start_distance'] = pinch_distance
                        pinch_detected = True
                        self._state['click_cooldown'] = self.click_cooldown_frames
                        # Unfreeze after click
                        self._state['cursor_frozen'] = False
                        self._state['frozen_cursor_x'] = None
                        self._state['frozen_cursor_y'] = None
            else:
                # Currently pinching - check if we should release
                if pinch_distance > self.pinch_release_threshold:
                    self._state['is_pinching'] = False
                    self._state['pinch_start_distance'] = None
        
        # Return cursor control action
        result = {
            'action': 'cursor_move',
            'x': final_x,
            'y': final_y,
            'pinch_distance': pinch_distance,
            'cursor_frozen': self._state['cursor_frozen'],
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
            'cursor_frozen': False,
            'frozen_cursor_x': None,
            'frozen_cursor_y': None,
        }
