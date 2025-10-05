"""
Attack gesture detector - detects horizontal punching motions for single left clicks
"""

import time
import numpy as np
from gestures.base_detector import BaseGestureDetector


class AttackDetector(BaseGestureDetector):
    """
    Detects attack gestures based on horizontal right wrist velocity.
    
    Logic:
    - Triggered by spike in x-axis velocity on right wrist
    - Y-axis velocity must remain low (horizontal movement only)
    - Velocity normalized to shoulder width for scale-invariance
    - Single left click with cooldown to prevent spam
    """
    
    def __init__(self):
        super().__init__("attack")
        
        # ==================== ADJUSTABLE CONFIGURATION ====================
        # All velocity values are normalized to shoulder width for scale-invariance
        
        # X-axis velocity threshold: Higher = requires faster horizontal punch
        # Default: 1.5 (increase to 2.0-2.5 for more aggressive punches only)
        self.x_velocity_threshold = 1.8
        
        # Y-axis velocity threshold: Lower = requires more strictly horizontal movement
        # Default: 0.8 (decrease to 0.5-0.6 to avoid false triggers from vertical movement)
        self.y_velocity_threshold = 0.8
        
        # Velocity averaging window: Number of frames to calculate average velocity
        # Default: 3 frames (increase to 5-7 for smoother, less sensitive detection)
        self.velocity_window_frames = 6
        
        # Click cooldown: Minimum time between consecutive attacks
        # Default: 0.4 seconds (decrease to 0.2-0.3 for faster clicking)
        self.click_cooldown = 0.3
        # ==================================================================
        
        # State tracking
        self._state = {
            'last_click_time': None,  # Time of last attack click
        }
    
    def detect(self, state_manager):
        """
        Detect attack gesture from right wrist horizontal velocity.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Dictionary with action type or None:
            - {'action': 'attack_click'} - Single left click attack
            - None - No attack detected
        """
        if not self.enabled:
            return None
        
        # Get velocity of right wrist
        velocity_vector = state_manager.get_velocity(
            'right_wrist', 
            window_size=self.velocity_window_frames
        )
        
        if velocity_vector is None:
            return None
        
        # Get shoulder distance for normalization
        shoulder_distance = self._get_shoulder_distance(state_manager)
        
        if shoulder_distance is None or shoulder_distance < 1e-5:
            return None
        
        # Normalize velocity by shoulder distance for scale-invariance
        normalized_velocity = velocity_vector / shoulder_distance
        
        # Extract x and y components
        x_velocity = abs(normalized_velocity[0])  # Absolute x-axis speed
        y_velocity = abs(normalized_velocity[1])  # Absolute y-axis speed
        
        # Check if movement is primarily horizontal and fast enough
        is_horizontal_punch = (
            x_velocity > self.x_velocity_threshold and 
            y_velocity < self.y_velocity_threshold
        )
        
        if not is_horizontal_punch:
            return None
        
        # Check cooldown
        current_time = time.time()
        last_click_time = self._state['last_click_time']
        
        if last_click_time is not None:
            time_since_last_click = current_time - last_click_time
            if time_since_last_click < self.click_cooldown:
                # Still in cooldown period
                return None
        
        # Trigger attack click
        self._state['last_click_time'] = current_time
        return {'action': 'attack_click'}
    
    def _get_shoulder_distance(self, state_manager):
        """
        Calculate the distance between the two shoulders (landmarks 11 and 12).
        This is used to normalize velocities for scale-invariance.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            float: Distance between shoulders, or None if landmarks not available
        """
        # Pose landmarks 11 = left shoulder, 12 = right shoulder
        left_shoulder = state_manager.get_landmark_position('left_shoulder')
        right_shoulder = state_manager.get_landmark_position('right_shoulder')
        
        if left_shoulder is None or right_shoulder is None:
            return None
        
        return float(np.linalg.norm(right_shoulder - left_shoulder))
    
    def reset(self):
        """Reset attack detector state."""
        self._state = {
            'last_click_time': None,
        }

