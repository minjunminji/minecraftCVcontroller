"""
Menu Close gesture detector - detects menu close gesture
"""

import numpy as np
from gestures.base_detector import BaseGestureDetector


class MenuCloseDetector(BaseGestureDetector):
    """
    Detects menu close gesture based on left hand crossing motion.
    This is the OPPOSITE of the inventory open gesture.
    
    Logic:
    - Triggers when left hand begins from right of shoulder and crosses to the left side
    - This is the reverse motion of inventory open
    - Only active when in menu mode (cursor control active)
    - Monitors the x-axis position of the left wrist relative to the left shoulder
    - Detects the crossing motion when wrist moves from right to left of shoulder
    """
    
    def __init__(self):
        super().__init__("menuclose")
        
        # Configuration (as ratios of shoulder width)
        self.start_threshold_ratio = 0.1  # Wrist must be this ratio of shoulder width to the right
        self.end_threshold_ratio = 0.1    # Wrist must cross this ratio of shoulder width to the left
        self.cooldown_frames = 30          # Frames to wait before allowing another gesture (1 second at 30fps)
        
        # State tracking
        self._state = {
            'gesture_started': False,     # True when wrist is on right side of shoulder
            'gesture_completed': False,   # True when crossing gesture completes
            'cooldown_counter': 0,        # Frames since last gesture completion
        }
    
    def _get_shoulder_width(self, state_manager):
        """
        Calculate the distance between left and right shoulders.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Float: Distance between shoulders, or None if positions unavailable
        """
        left_shoulder = state_manager.get_landmark_position('left_shoulder', frame_offset=0)
        right_shoulder = state_manager.get_landmark_position('right_shoulder', frame_offset=0)
        
        if left_shoulder is None or right_shoulder is None:
            return None
        
        # Calculate Euclidean distance in x-y plane (ignore z for shoulder width)
        dx = right_shoulder[0] - left_shoulder[0]
        dy = right_shoulder[1] - left_shoulder[1]
        shoulder_width = np.sqrt(dx**2 + dy**2)
        
        return shoulder_width
    
    def _get_relative_x_position(self, shoulder_pos, wrist_pos):
        """
        Calculate the relative x-position of wrist to shoulder.
        
        Args:
            shoulder_pos: (x, y, z) tuple for shoulder position
            wrist_pos: (x, y, z) tuple for wrist position
        
        Returns:
            Float: x-difference (positive = wrist is to the right of shoulder)
                   None if positions are invalid
        """
        if shoulder_pos is None or wrist_pos is None:
            return None
        
        # In MediaPipe, x increases from left to right (from camera's perspective)
        # Since frame is mirrored in the preview, the actual gesture is:
        # - negative x_diff means wrist is to the left of shoulder
        # - positive x_diff means wrist is to the right of shoulder
        x_diff = wrist_pos[0] - shoulder_pos[0]
        
        return x_diff
    
    def detect(self, state_manager):
        """
        Detect menu close gesture from left hand crossing motion.
        This is the OPPOSITE of inventory open - starts right, crosses to left.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Dictionary with action type or None:
            - {'action': 'menu_close'} - Menu should be closed (ESC pressed)
            - None - No menu close gesture detected
        """
        if not self.enabled:
            return None
        
        # Update cooldown counter
        if self._state['cooldown_counter'] > 0:
            self._state['cooldown_counter'] -= 1
            return None
        
        # Get shoulder width for relative thresholds
        shoulder_width = self._get_shoulder_width(state_manager)
        if shoulder_width is None:
            self._state['gesture_started'] = False
            return None
        
        # Calculate absolute thresholds based on shoulder width
        # OPPOSITE of inventory open:
        # - start_threshold should be negative (wrist to the LEFT of shoulder in MediaPipe coords)
        # - end_threshold should be positive (wrist crosses to the RIGHT in MediaPipe coords)
        # This appears as right-to-left motion to the user viewing the mirrored display
        start_threshold = -self.start_threshold_ratio * shoulder_width
        end_threshold = self.end_threshold_ratio * shoulder_width
        
        # Get left shoulder and wrist positions from state manager
        left_shoulder = state_manager.get_landmark_position('left_shoulder', frame_offset=0)
        left_wrist = state_manager.get_landmark_position('left_wrist', frame_offset=0)
        
        if left_shoulder is None or left_wrist is None:
            # Can't detect without landmarks, reset gesture state
            self._state['gesture_started'] = False
            return None
        
        # Convert numpy arrays to tuples for consistency
        shoulder_pos = tuple(left_shoulder)
        wrist_pos = tuple(left_wrist)
        
        # Get relative x position
        x_diff = self._get_relative_x_position(shoulder_pos, wrist_pos)
        
        if x_diff is None:
            self._state['gesture_started'] = False
            return None
        
        # State machine for gesture detection (OPPOSITE of inventory open)
        # Step 1: Check if wrist is on the left side (gesture start - in MediaPipe coords)
        if not self._state['gesture_started']:
            if x_diff <= start_threshold:
                # Wrist is on the left side of shoulder (in MediaPipe) - gesture started
                self._state['gesture_started'] = True
                return None
        
        # Step 2: Check if wrist has crossed to the right side (gesture complete - in MediaPipe coords)
        else:
            if x_diff >= end_threshold:
                # Wrist has crossed to the right side (in MediaPipe) - gesture complete!
                self._state['gesture_started'] = False
                self._state['gesture_completed'] = True
                self._state['cooldown_counter'] = self.cooldown_frames
                
                return {
                    'action': 'menu_close',
                    'x_diff': x_diff,
                    'shoulder_width': shoulder_width,
                    'start_threshold': start_threshold,
                    'end_threshold': end_threshold
                }
            elif x_diff <= start_threshold:
                # Wrist is still on the left side, keep waiting
                return None
            else:
                # Wrist is in the middle zone, continue tracking
                return None
        
        return None
    
    def reset(self):
        """Reset menu close detector state."""
        self._state = {
            'gesture_started': False,
            'gesture_completed': False,
            'cooldown_counter': 0,
        }
