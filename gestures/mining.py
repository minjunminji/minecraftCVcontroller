"""
Mining gesture detector - detects mining/attacking motions
"""

import time
from gestures.base_detector import BaseGestureDetector


class MiningDetector(BaseGestureDetector):
    """
    Detects mining/attacking gestures based on right arm velocity.
    
    Logic:
    - Detected by spike in velocity of the right arm
    - Sends one left click
    - If movement is oscillatory / keeps happening (like a continuous mining motion)
    - Switches to holding down left-click until oscillating stops
    """
    
    def __init__(self):
        super().__init__("mining")
        
        # Configuration
        self.velocity_threshold = 1  # Minimum velocity to trigger attack
        self.click_interval = 0.5      # Max time between clicks to count as mining
        self.oscillation_threshold = 1  # Threshold for oscillation detection
        self.min_clicks_for_hold = 2   # Number of clicks before holding
        
        # State tracking
        self._state = {
            'is_holding': False,
            'click_count': 0,
            'last_click_time': None,
            'last_velocity': 0,
        }
    
    def detect(self, state_manager):
        """
        Detect mining gesture from right arm velocity patterns.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Dictionary with action type or None:
            - {'action': 'mining_click'} - Single attack click
            - {'action': 'mining_start_hold'} - Start continuous mining
            - {'action': 'mining_continue_hold'} - Continue holding
            - {'action': 'mining_stop_hold'} - Stop mining
            - None - No mining detected
        """
        if not self.enabled:
            return None
        
        # Get right wrist velocity (for mining motion)
        velocity = state_manager.get_speed('right_wrist', window_size=3)
        
        if velocity is None:
            # No tracking, stop any active mining
            if self._state['is_holding']:
                self._state['is_holding'] = False
                self._state['click_count'] = 0
                return {'action': 'mining_stop_hold'}
            return None
        
        current_time = time.time()
        
        # Detect velocity spike (attack motion)
        velocity_spike = velocity > self.velocity_threshold
        
        if velocity_spike:
            last_click_time = self._state['last_click_time']
            
            # First click or isolated click
            if last_click_time is None:
                self._state['last_click_time'] = current_time
                self._state['click_count'] = 1
                self._state['last_velocity'] = velocity
                return {'action': 'mining_click'}
            
            # Check time since last click
            time_since_last = current_time - last_click_time
            
            # Multiple clicks in short period = mining pattern
            if time_since_last < self.click_interval:
                self._state['click_count'] += 1
                self._state['last_click_time'] = current_time
                self._state['last_velocity'] = velocity
                
                # Start continuous mining if enough clicks
                if self._state['click_count'] >= self.min_clicks_for_hold:
                    if not self._state['is_holding']:
                        self._state['is_holding'] = True
                        return {'action': 'mining_start_hold'}
                    else:
                        return {'action': 'mining_continue_hold'}
                else:
                    # Still individual clicks
                    return {'action': 'mining_click'}
            else:
                # Too much time passed, reset and count as new click
                self._state['click_count'] = 1
                self._state['last_click_time'] = current_time
                self._state['last_velocity'] = velocity
                
                # If was holding, stop it
                if self._state['is_holding']:
                    self._state['is_holding'] = False
                    return {'action': 'mining_stop_hold'}
                
                return {'action': 'mining_click'}
        
        # No velocity spike, check if we should continue or stop holding
        if self._state['is_holding']:
            # Check if oscillation has stopped
            is_oscillating = state_manager.is_oscillating(
                'right_wrist',
                threshold=self.oscillation_threshold,
                window_size=15,
                min_peaks=2
            )
            
            if not is_oscillating:
                # Mining motion stopped
                self._state['is_holding'] = False
                self._state['click_count'] = 0
                self._state['last_click_time'] = None
                return {'action': 'mining_stop_hold'}
            else:
                # Continue holding
                return {'action': 'mining_continue_hold'}
        
        # Check if click sequence timed out
        if self._state['last_click_time']:
            time_since_last = current_time - self._state['last_click_time']
            if time_since_last > self.click_interval * 2:
                # Reset state
                self._state['click_count'] = 0
                self._state['last_click_time'] = None
        
        return None
    
    def reset(self):
        """Reset mining detector state."""
        self._state = {
            'is_holding': False,
            'click_count': 0,
            'last_click_time': None,
            'last_velocity': 0,
        }