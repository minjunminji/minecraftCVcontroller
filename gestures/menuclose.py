"""
Menu Close gesture detector - detects menu close gesture
"""

import numpy as np
from gestures.base_detector import BaseGestureDetector


class MenuCloseDetector(BaseGestureDetector):
    """
    Detects menu close gesture based on left hand velocity.
    This is the OPPOSITE direction of the inventory open gesture.
    
    Logic:
    - Triggers when left wrist velocity exceeds a threshold
    - Direction must be right-to-left (positive x velocity in MediaPipe coords)
    - Velocity is normalized to shoulder width for consistency
    - Only active when in menu mode (cursor control active)
    """
    
    def __init__(self):
        super().__init__("menuclose")
        
        # Configuration (velocity threshold as ratio of shoulder width per frame)
        self.velocity_threshold_ratio = 0.15  # Velocity must exceed this ratio of shoulder width per frame
        self.velocity_window_size = 3          # Frames to use for velocity calculation
        
        # Displacement requirements (minimum distance to be considered a swipe)
        self.min_displacement_ratio = 0.9      # Minimum displacement in x direction (as ratio of shoulder width)
        self.displacement_window_size = 5      # Frames to measure displacement over
        
        self.cooldown_frames = 30              # Frames to wait before allowing another gesture (1 second at 30fps)
        
        # State tracking
        self._state = {
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
    
    def _get_normalized_velocity(self, state_manager):
        """
        Calculate the velocity of the left wrist normalized by shoulder width.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Tuple of (velocity_x, velocity_magnitude) normalized by shoulder width, or (None, None)
        """
        # Get shoulder width for normalization
        shoulder_width = self._get_shoulder_width(state_manager)
        if shoulder_width is None:
            return None, None
        
        # Get velocity of left wrist
        velocity = state_manager.get_velocity('left_wrist', window_size=self.velocity_window_size)
        if velocity is None:
            return None, None
        
        # Normalize by shoulder width
        velocity_normalized = velocity / shoulder_width
        velocity_x = velocity_normalized[0]
        velocity_magnitude = np.linalg.norm(velocity_normalized)
        
        return velocity_x, velocity_magnitude
    
    def _get_x_displacement(self, state_manager):
        """
        Calculate the displacement in x direction over the displacement window,
        normalized by shoulder width.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Float: x displacement normalized by shoulder width, or None
        """
        # Check if we have enough history
        if len(state_manager.landmark_history) < self.displacement_window_size:
            return None
        
        # Get shoulder width for normalization
        shoulder_width = self._get_shoulder_width(state_manager)
        if shoulder_width is None:
            return None
        
        # Get current and past positions
        current_pos = state_manager.get_landmark_position('left_wrist', frame_offset=0)
        past_pos = state_manager.get_landmark_position('left_wrist', frame_offset=self.displacement_window_size - 1)
        
        if current_pos is None or past_pos is None:
            return None
        
        # Calculate x displacement (normalized by shoulder width)
        x_displacement = (current_pos[0] - past_pos[0]) / shoulder_width
        
        return x_displacement
    
    def detect(self, state_manager):
        """
        Detect menu close gesture from left hand velocity and displacement.
        This is the OPPOSITE direction of inventory open - right-to-left swipe.
        
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
        
        # Get normalized velocity
        velocity_x, velocity_magnitude = self._get_normalized_velocity(state_manager)
        
        if velocity_x is None or velocity_magnitude is None:
            return None
        
        # Check if velocity exceeds threshold
        if velocity_magnitude < self.velocity_threshold_ratio:
            return None
        
        # Check direction: right-to-left swipe (OPPOSITE of inventory open)
        # In MediaPipe coordinates (not mirrored), x increases from left to right
        # Since the display is mirrored, a right-to-left swipe (as seen by user) 
        # means moving from low x to high x in MediaPipe coordinates
        # So we need POSITIVE x velocity for right-to-left swipe (as seen by user)
        if velocity_x <= 0:
            # Negative velocity = moving right in MediaPipe coords = left-to-right as seen by user
            return None
        
        # Check displacement requirement
        x_displacement = self._get_x_displacement(state_manager)
        if x_displacement is None:
            return None
        
        # For right-to-left swipe (as seen by user), we need positive displacement in MediaPipe coords
        # The displacement must exceed the minimum threshold
        if x_displacement <= 0 or abs(x_displacement) < self.min_displacement_ratio:
            # Either wrong direction or insufficient displacement
            return None
        
        # Velocity and displacement are both sufficient and direction is correct!
        self._state['cooldown_counter'] = self.cooldown_frames
        
        shoulder_width = self._get_shoulder_width(state_manager)
        
        return {
            'action': 'menu_close',
            'velocity_x': velocity_x,
            'velocity_magnitude': velocity_magnitude,
            'x_displacement': x_displacement,
            'shoulder_width': shoulder_width,
            'velocity_threshold': self.velocity_threshold_ratio,
            'displacement_threshold': self.min_displacement_ratio
        }
    
    def reset(self):
        """Reset menu close detector state."""
        self._state = {
            'cooldown_counter': 0,
        }
