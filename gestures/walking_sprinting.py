"""
Walking and sprinting gesture detector
"""

from gestures.base_detector import BaseGestureDetector


class MovementDetector(BaseGestureDetector):
    """
    Detects walking, sprinting, and strafing based on body movement.
    
    TODO: Implement detection logic based on:
    - Leg movement patterns for walking
    - Left thumb position for backward movement
    - Torso lean for strafing
    """
    
    def __init__(self):
        super().__init__("movement")
    
    def detect(self, state_manager):
        """
        Detect movement gestures.
        
        Returns:
            Dictionary with movement info or None:
            {
                'action': 'move',
                'is_walking': bool,
                'left_thumb_back': bool,
                'torso_lean': 'left'|'right'|None
            }
        """
        if not self.enabled:
            return None
        
        # For now, return None (no movement detected)
        return None