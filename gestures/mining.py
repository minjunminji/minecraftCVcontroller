"""
Mining gesture detector - detects vertical stabbing motions for continuous mining
"""

import time
import numpy as np
from gestures.base_detector import BaseGestureDetector


class MiningDetector(BaseGestureDetector):
    """
    Detects mining gestures based on vertical right wrist velocity.
    
    Logic:
    - Triggered by spike in y-axis velocity on right wrist (vertical stabbing)
    - X-axis velocity must remain low (vertical movement only)
    - Velocity normalized to shoulder width for scale-invariance
    - Holds down left click while vertical motion continues
    - Uses hand spread detection to distinguish mining (closed fist) from placing (open hand)
    - Gated: right wrist must be above right shoulder for any mining detection/hold
    """
    
    def __init__(self):
        super().__init__("mining")
        
        # ==================== ADJUSTABLE CONFIGURATION ====================
        # All velocity values are normalized to shoulder width for scale-invariance
        
        # Y-axis velocity threshold: Higher = requires faster vertical stabbing
        # Default: 1.3 (increase to 1.8 for more aggressive stabs only)
        self.y_velocity_threshold = 1.3
        
        # X-axis velocity threshold: Lower = requires more strictly vertical movement
        # Default: 0.8 (decrease to 0.5-0.6 to avoid false triggers from horizontal movement)
        self.x_velocity_threshold = 0.8
        
        # Velocity averaging window: Number of frames to calculate average velocity
        # Default: 6 frames (increase to 7-10 for smoother, less sensitive detection)
        self.velocity_window_frames = 6
        
        # Grace period: Time to maintain hold without vertical motion
        # Default: 0.26 seconds (increase to 0.6 for more forgiving detection)
        self.hold_grace_period = 0.5
        
        # Hand spread thresholds for distinguishing mining vs placing
        self.open_hand_area_threshold = 0.55    # Above this = open hand (placing)
        self.closed_hand_area_threshold = 0.45  # Below this = closed fist (mining)
        # ==================================================================
        
        # State tracking
        self._state = {
            'is_holding': False,           # Whether currently holding left click
            'last_motion_time': None,      # Time of last detected vertical motion
        }
    
    def detect(self, state_manager):
        """
        Detect mining gesture from right wrist vertical velocity.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Dictionary with action type or None:
            - {'action': 'mining_start_hold'} - Start continuous mining
            - {'action': 'mining_continue_hold'} - Continue holding
            - {'action': 'mining_stop_hold'} - Stop mining
            - None - No mining detected
        """
        if not self.enabled:
            return None

        # Gate: require right wrist above right shoulder to listen for mining
        right_wrist_pos = state_manager.get_landmark_position('right_wrist')
        right_shoulder_pos = state_manager.get_landmark_position('right_shoulder')

        if right_wrist_pos is None or right_shoulder_pos is None:
            return self._handle_tracking_lost()

        wrist_above_shoulder = float(right_wrist_pos[1]) < float(right_shoulder_pos[1])

        if not wrist_above_shoulder:
            # If we were holding, stop immediately; otherwise, ignore gesture
            if self._state['is_holding']:
                self._state['is_holding'] = False
                self._state['last_motion_time'] = None
                return {'action': 'mining_stop_hold'}
            return None

        # Get velocity of right wrist
        velocity_vector = state_manager.get_velocity(
            'right_wrist',
            window_size=self.velocity_window_frames
        )
        
        if velocity_vector is None:
            return self._handle_tracking_lost()
        
        # Check hand spread to distinguish mining (closed fist) from placing (open hand)
        hand_spread = self._get_hand_spread_area(state_manager)
        hand_is_open = False
        if hand_spread is not None:
            hand_is_open = hand_spread >= self.open_hand_area_threshold
        
        # If hand is open and we're holding, stop mining
        if self._state['is_holding'] and hand_is_open:
            self._state['is_holding'] = False
            self._state['last_motion_time'] = None
            return {'action': 'mining_stop_hold'}
        
        # Ignore if hand is open (this is placing gesture, not mining)
        if hand_is_open:
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
        
        # Check if movement is primarily vertical and fast enough
        is_vertical_stab = (
            y_velocity > self.y_velocity_threshold and
            x_velocity < self.x_velocity_threshold
        )
        
        current_time = time.time()
        
        if is_vertical_stab:
            # Vertical stabbing motion detected
            self._state['last_motion_time'] = current_time
            
            if not self._state['is_holding']:
                # Start holding
                self._state['is_holding'] = True
                return {'action': 'mining_start_hold'}
            else:
                # Continue holding
                return {'action': 'mining_continue_hold'}
        
        # No vertical motion detected
        if self._state['is_holding']:
            # Check if we should stop holding (grace period expired)
            last_motion_time = self._state['last_motion_time']
            
            if last_motion_time is not None:
                time_since_motion = current_time - last_motion_time
                
                if time_since_motion <= self.hold_grace_period:
                    # Still within grace period, continue holding
                    return {'action': 'mining_continue_hold'}
            
            # Grace period expired, stop holding
            self._state['is_holding'] = False
            self._state['last_motion_time'] = None
            return {'action': 'mining_stop_hold'}
        
        return None
    
    def _get_hand_spread_area(self, state_manager):
        """
        Estimate normalized fingertip spread area for right hand.

        Returns:
            float or None: Normalized area (size-invariant), None if landmarks missing.
        """
        fingertip_names = [
            'right_thumb_tip',
            'right_index_finger_tip',
            'right_middle_finger_tip',
            'right_ring_finger_tip',
            'right_pinky_tip',
        ]
        
        points = []
        for name in fingertip_names:
            pos = state_manager.get_landmark_position(name)
            if pos is None:
                return None
            points.append((float(pos[0]), float(pos[1])))
        
        raw_area = self._polygon_area(points)
        hand_scale = self._get_hand_scale(state_manager)
        if hand_scale is None:
            return None
        
        return float(raw_area / max(hand_scale ** 2, 1e-6))
    
    @staticmethod
    def _polygon_area(points):
        """Compute area via shoelace formula."""
        area = 0.0
        count = len(points)
        for i in range(count):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % count]
            area += x1 * y2 - x2 * y1
        return abs(area) * 0.5
    
    def _get_hand_scale(self, state_manager):
        """Estimate characteristic hand size for normalization."""
        distance_pairs = [
            ('right_wrist', 'right_index_finger_mcp'),
            ('right_wrist', 'right_middle_finger_mcp'),
            ('right_wrist', 'right_ring_finger_mcp'),
            ('right_wrist', 'right_pinky_mcp'),
            ('right_index_finger_mcp', 'right_pinky_mcp'),
        ]
        
        distances = []
        for start, end in distance_pairs:
            dist = state_manager.get_landmark_distance(start, end)
            if dist is not None and dist > 1e-5:
                distances.append(dist)
        
        if not distances:
            return None
        
        return float(np.median(distances))
    
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
    
    def _handle_tracking_lost(self):
        """Handle loss of tracking information."""
        if self._state['is_holding']:
            self._state['is_holding'] = False
            self._state['last_motion_time'] = None
            return {'action': 'mining_stop_hold'}
        
        return None
     
    def reset(self):
        """Reset mining detector state."""
        self._state = {
            'is_holding': False,
            'last_motion_time': None,
        }
