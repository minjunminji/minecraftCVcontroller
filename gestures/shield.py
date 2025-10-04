"""
Shield gesture detector - detects shield blocking gesture
"""

import numpy as np
from gestures.base_detector import BaseGestureDetector


class ShieldDetector(BaseGestureDetector):
    """
    Detects shield blocking gesture based on left forearm position.
    
    Logic:
    - Triggers when left forearm is held horizontally in front of chest (like holding a sword)
    - Should hold right click for as long as forearm stays in position
    - Forearm is considered in "blocking" position when:
      * Roughly horizontal (parallel to floor)
      * Wrist is forward from shoulder (in front of body)
      * At approximately chest/shoulder height
    """
    
    def __init__(self):
        super().__init__("shield")
        
        # Configuration
        self.horizontal_angle_tolerance = 35  # Degrees from horizontal (0° or 180°)
        self.min_forward_distance = 0.10  # Minimum distance wrist should be forward from shoulder
        self.max_height_diff = 0.15  # Maximum vertical difference from shoulder height
        
        # State tracking
        self._state = {
            'is_blocking': False,
        }
    
    def _calculate_forearm_angle(self, elbow_pos, wrist_pos):
        """
        Calculate the angle of the forearm from horizontal.
        
        Args:
            elbow_pos: (x, y, z) tuple for elbow position
            wrist_pos: (x, y, z) tuple for wrist position
        
        Returns:
            Angle in degrees from horizontal (0-180)
            Returns None if positions are invalid
        """
        if elbow_pos is None or wrist_pos is None:
            return None
        
        # Calculate vector from elbow to wrist
        dx = wrist_pos[0] - elbow_pos[0]
        dy = wrist_pos[1] - elbow_pos[1]  # Note: In image coordinates, y increases downward
        
        # Calculate angle from horizontal
        # For horizontal forearm, dy should be close to 0
        angle_rad = np.arctan2(-dy, abs(dx))  # Negative dy to flip y-axis
        angle_deg = abs(np.degrees(angle_rad))
        
        # Return absolute angle from horizontal
        # 0° = horizontal, 90° = vertical
        return angle_deg
    
    def _is_forearm_horizontal(self, elbow_pos, wrist_pos):
        """
        Check if forearm is roughly horizontal (parallel to floor).
        
        Returns:
            bool: True if forearm is horizontal within tolerance
        """
        angle = self._calculate_forearm_angle(elbow_pos, wrist_pos)
        if angle is None:
            return False
        
        # Check if angle is close to horizontal (near 0°)
        return angle <= self.horizontal_angle_tolerance
    
    def _is_wrist_forward(self, shoulder_pos, wrist_pos):
        """
        Check if wrist is forward from shoulder (in front of body).
        
        Args:
            shoulder_pos: (x, y, z) tuple for shoulder position
            wrist_pos: (x, y, z) tuple for wrist position
        
        Returns:
            bool: True if wrist is sufficiently forward
        """
        if shoulder_pos is None or wrist_pos is None:
            return False
        
        # In MediaPipe, z-axis points toward camera (negative z = closer to camera)
        # Wrist should be closer to camera than shoulder
        forward_distance = shoulder_pos[2] - wrist_pos[2]
        
        return forward_distance >= self.min_forward_distance
    
    def _is_at_chest_height(self, shoulder_pos, wrist_pos):
        """
        Check if wrist is at roughly shoulder/chest height.
        
        Returns:
            bool: True if wrist is near shoulder height
        """
        if shoulder_pos is None or wrist_pos is None:
            return False
        
        # Check vertical difference
        height_diff = abs(shoulder_pos[1] - wrist_pos[1])
        
        return height_diff <= self.max_height_diff
    
    def detect(self, state_manager):
        """
        Detect shield blocking gesture from left forearm angle.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Dictionary with action type or None:
            - {'action': 'shield_start'} - Start blocking
            - {'action': 'shield_hold'} - Continue blocking
            - {'action': 'shield_stop'} - Stop blocking
            - None - No shield gesture detected
        """
        if not self.enabled:
            return None
        
        # Get left arm and shoulder positions from state manager
        left_shoulder = state_manager.get_landmark_position('left_shoulder', frame_offset=0)
        left_elbow = state_manager.get_landmark_position('left_elbow', frame_offset=0)
        left_wrist = state_manager.get_landmark_position('left_wrist', frame_offset=0)
        
        if left_shoulder is None or left_elbow is None or left_wrist is None:
            # Can't detect without all landmarks, stop blocking if active
            if self._state['is_blocking']:
                self._state['is_blocking'] = False
                return {'action': 'shield_stop'}
            return None
        
        # Convert numpy arrays to tuples for consistency
        shoulder_pos = tuple(left_shoulder)
        elbow_pos = tuple(left_elbow)
        wrist_pos = tuple(left_wrist)
        
        # Check all three conditions for sword/shield blocking position:
        # 1. Forearm is roughly horizontal (parallel to floor)
        is_horizontal = self._is_forearm_horizontal(elbow_pos, wrist_pos)
        
        # 2. Wrist is forward from shoulder (in front of body)
        is_forward = self._is_wrist_forward(shoulder_pos, wrist_pos)
        
        # 3. Wrist is at approximately chest/shoulder height
        is_chest_height = self._is_at_chest_height(shoulder_pos, wrist_pos)
        
        # All three conditions must be met
        is_blocking_position = is_horizontal and is_forward and is_chest_height
        
        # Update state and return action
        if is_blocking_position:
            if not self._state['is_blocking']:
                # Start blocking
                self._state['is_blocking'] = True
                angle = self._calculate_forearm_angle(elbow_pos, wrist_pos)
                return {
                    'action': 'shield_start',
                    'horizontal': is_horizontal,
                    'forward': is_forward,
                    'chest_height': is_chest_height,
                    'angle': angle
                }
            else:
                # Continue blocking
                angle = self._calculate_forearm_angle(elbow_pos, wrist_pos)
                return {
                    'action': 'shield_hold',
                    'horizontal': is_horizontal,
                    'forward': is_forward,
                    'chest_height': is_chest_height,
                    'angle': angle
                }
        else:
            if self._state['is_blocking']:
                # Stop blocking
                self._state['is_blocking'] = False
                return {'action': 'shield_stop'}
            return None
    
    def reset(self):
        """Reset shield detector state."""
        self._state = {
            'is_blocking': False,
        }