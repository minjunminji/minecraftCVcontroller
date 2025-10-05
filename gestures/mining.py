"""
Mining gesture detector - detects mining/attacking motions
"""

import time
import numpy as np
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
        self.velocity_threshold = 0.4  # Minimum overall velocity to consider an attack
        self.click_interval = 0.6      # Max time between classified clicks
        self.oscillation_threshold = 0.07  # Threshold for oscillation detection when holding
        self.directional_velocity_threshold = 0.25  # Minimum velocity along forearm axis
        self.min_direction_changes_for_hold = 2      # Direction reversals before entering hold
        self.hold_oscillation_window = 1.2           # Time window to observe oscillations
        self.sequence_reset_timeout = 1.5            # Timeout for streak tracking
        self.single_click_cooldown = 0.25            # Minimum time between single clicks
        self.hold_grace_period = 0.35                # Grace period to maintain hold without spikes
        self.open_hand_area_threshold = 0.55         # Above this normalized area, treat hand as open (placing)
        self.closed_hand_area_threshold = 0.45       # Below this normalized area, treat hand as closed (mining)
        
        # State tracking
        self._state = {
            'is_holding': False,
            'click_count': 0,
            'last_click_time': None,
            'last_velocity': 0,
            'last_direction': None,
            'direction_change_count': 0,
            'sequence_start_time': None,
            'last_spike_time': None,
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
        
        velocity_vector = state_manager.get_velocity('right_wrist', window_size=3)
        
        if velocity_vector is None:
            return self._handle_tracking_lost()
        
        hand_spread = self._get_hand_spread_area(state_manager)
        hand_is_open = False
        hand_is_closed = False
        if hand_spread is not None:
            hand_is_open = hand_spread >= self.open_hand_area_threshold
            hand_is_closed = hand_spread <= self.closed_hand_area_threshold
        velocity = float(np.linalg.norm(velocity_vector))
        self._state['last_velocity'] = velocity
        current_time = time.time()
        
        directional_velocity = self._compute_directional_velocity(state_manager, velocity_vector)
        direction = 0
        if directional_velocity > self.directional_velocity_threshold:
            direction = 1
        elif directional_velocity < -self.directional_velocity_threshold:
            direction = -1
        
        velocity_spike = velocity > self.velocity_threshold and direction != 0
        
        if self._state['is_holding'] and hand_is_open:
            self._state['is_holding'] = False
            self._reset_direction_tracking()
            self._state['click_count'] = 0
            self._state['last_click_time'] = None
            self._state['last_spike_time'] = None
            return {'action': 'mining_stop_hold'}
        
        if velocity_spike and (hand_is_open or not hand_is_closed):
            self._reset_direction_tracking()
            self._state['last_spike_time'] = current_time
            self._state['last_velocity'] = velocity
            return None
        
        if velocity_spike:
            last_spike_time = self._state['last_spike_time']
            
            if last_spike_time is None:
                self._state['sequence_start_time'] = current_time
            else:
                time_since_last_spike = current_time - last_spike_time
                
                if time_since_last_spike > self.sequence_reset_timeout:
                    self._reset_direction_tracking()
                    self._state['sequence_start_time'] = current_time
                elif (
                    self._state['sequence_start_time'] is not None and
                    current_time - self._state['sequence_start_time'] > self.hold_oscillation_window
                ):
                    self._reset_direction_tracking()
                    self._state['sequence_start_time'] = current_time
            
            self._state['last_spike_time'] = current_time
            
            if self._state['last_direction'] is None:
                self._state['last_direction'] = direction
            elif direction != self._state['last_direction']:
                self._state['direction_change_count'] += 1
                self._state['last_direction'] = direction
            
            if self._state['is_holding']:
                return {'action': 'mining_continue_hold'}
            
            sequence_start = self._state['sequence_start_time'] or current_time
            if (
                self._state['direction_change_count'] >= self.min_direction_changes_for_hold and
                current_time - sequence_start <= self.hold_oscillation_window
            ):
                self._state['is_holding'] = True
                self._state['click_count'] = 0
                self._state['last_click_time'] = current_time
                self._reset_direction_tracking()
                self._state['last_spike_time'] = current_time
                return {'action': 'mining_start_hold'}
            
            if direction > 0:
                last_click_time = self._state['last_click_time']
                time_since_click = None if last_click_time is None else current_time - last_click_time
                
                if last_click_time is None or time_since_click >= self.single_click_cooldown:
                    self._state['last_click_time'] = current_time
                    self._state['click_count'] = 1
                    return {'action': 'mining_click'}
            
            return None
        
        if self._state['is_holding']:
            if (
                self._state['last_spike_time'] is not None and
                current_time - self._state['last_spike_time'] <= self.hold_grace_period
            ):
                return {'action': 'mining_continue_hold'}
            
            is_oscillating = state_manager.is_oscillating(
                'right_wrist',
                threshold=self.oscillation_threshold,
                window_size=15,
                min_peaks=2
            )
            
            if not is_oscillating:
                self._state['is_holding'] = False
                self._state['click_count'] = 0
                self._state['last_click_time'] = None
                self._reset_direction_tracking()
                return {'action': 'mining_stop_hold'}
            
            return {'action': 'mining_continue_hold'}
        
        if self._state['last_click_time']:
            time_since_last_click = current_time - self._state['last_click_time']
            if time_since_last_click > self.click_interval * 2:
                self._state['click_count'] = 0
                self._state['last_click_time'] = None
        
        if (
            self._state['last_spike_time'] and
            current_time - self._state['last_spike_time'] > self.sequence_reset_timeout
        ):
            self._reset_direction_tracking()
        
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
    
    def _compute_directional_velocity(self, state_manager, velocity_vector):
        """Project wrist velocity onto the forearm axis to obtain signed magnitude."""
        if velocity_vector is None:
            return 0.0
        
        elbow_pos = state_manager.get_landmark_position('right_elbow')
        wrist_pos = state_manager.get_landmark_position('right_wrist')
        
        if elbow_pos is not None and wrist_pos is not None:
            axis = wrist_pos - elbow_pos
            axis_norm = np.linalg.norm(axis)
            if axis_norm > 1e-5:
                return float(np.dot(velocity_vector, axis) / axis_norm)
        
        dominant_axis = int(np.argmax(np.abs(velocity_vector)))
        return float(velocity_vector[dominant_axis])
    
    def _reset_direction_tracking(self):
        """Clear oscillation tracking state."""
        self._state['last_direction'] = None
        self._state['direction_change_count'] = 0
        self._state['sequence_start_time'] = None
        self._state['last_spike_time'] = None
    
    def _handle_tracking_lost(self):
        """Handle loss of tracking information."""
        stop_action = None
        if self._state['is_holding']:
            self._state['is_holding'] = False
            stop_action = {'action': 'mining_stop_hold'}
        
        self._reset_direction_tracking()
        self._state['click_count'] = 0
        self._state['last_click_time'] = None
        self._state['last_velocity'] = 0
        
        return stop_action
     
    def reset(self):
        """Reset mining detector state."""
        self._state = {
            'is_holding': False,
            'click_count': 0,
            'last_click_time': None,
            'last_velocity': 0,
            'last_direction': None,
            'direction_change_count': 0,
            'sequence_start_time': None,
            'last_spike_time': None,
        }