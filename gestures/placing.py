"""
Placing/using items gesture detector
"""

from gestures.base_detector import BaseGestureDetector


class PlacingDetector(BaseGestureDetector):
    """
    Detects placing blocks or using items gesture.
    
    TODO: Implement detection logic for right hand gestures
    """
    
    def __init__(self):
        super().__init__("placing")
    
    def detect(self, state_manager):
        """
        Detect placing gesture.
        
        Returns:
            Dictionary with action info or None:
            {'action': 'place'} - Place block/use item
            {'action': 'scroll_up'} - Scroll hotbar up
            {'action': 'scroll_down'} - Scroll hotbar down
        """
        if not self.enabled:
            return None
        
        return None