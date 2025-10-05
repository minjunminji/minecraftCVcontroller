"""
Walking and sprinting gesture detector using refined locomotion algorithm.

This module implements gesture-based movement detection for Minecraft controls
using MediaPipe pose landmarks. The algorithm prioritizes stability, uses
reliable landmarks with fallback strategies, and implements proper state
management with hysteresis to prevent false positives.

Key features:
- Ankle-based walking detection with knee/hip fallbacks
- Simple torso lean detection for strafing
- State machine with IDLE ↔ WALKING transitions
- Scale normalization by body dimensions
- Visibility checks for landmark reliability
- Temporal smoothing to reduce jitter
"""

from collections import deque
import numpy as np
from gestures.base_detector import BaseGestureDetector


# Detection thresholds (tuned for stability over speed)
WALK_ENTER_THRESHOLD = 0.15   # Enter WALKING state
WALK_EXIT_THRESHOLD = 0.08    # Exit to IDLE (hysteresis gap)
VISIBILITY_THRESHOLD = 0.6     # MediaPipe visibility confidence minimum
MIN_STABLE_FRAMES = 5          # Frames required for stable state transition
LEAN_SIMPLE_THRESHOLD = 0.03   # Normalized X-displacement for torso lean


class MovementState:
    """
    State machine for IDLE ↔ WALKING transitions with hysteresis.
    
    Prevents rapid state oscillation by requiring stability for MIN_STABLE_FRAMES
    before transitioning and using different thresholds for entry vs exit.
    """
    
    def __init__(self):
        self.current_state = 'IDLE'
        self.state_timer = 0
        self.last_leg_motion_score = 0.0
        self.stable_frame_count = 0
    
    def update(self, leg_motion_score):
        """
        Update state machine with new leg motion score.
        
        Args:
            leg_motion_score: float (0.0 = no motion, 0.15+ = clear walking)
        
        Returns:
            bool: True if currently in WALKING state, False if IDLE
        """
        self.state_timer += 1
        
        # Check if score is stable (small change from previous frame)
        score_delta = abs(leg_motion_score - self.last_leg_motion_score)
        if score_delta < 0.05:  # Stability threshold
            self.stable_frame_count += 1
        else:
            self.stable_frame_count = 0
        
        self.last_leg_motion_score = leg_motion_score
        
        # State transitions with hysteresis
        if self.current_state == 'IDLE':
            # Transition to WALKING: requires higher threshold and stability
            if (leg_motion_score > WALK_ENTER_THRESHOLD and 
                self.stable_frame_count >= MIN_STABLE_FRAMES):
                self.current_state = 'WALKING'
                self.state_timer = 0
                return True
            return False
        
        elif self.current_state == 'WALKING':
            # Transition to IDLE: requires lower threshold (hysteresis) and stability
            if (leg_motion_score < WALK_EXIT_THRESHOLD and 
                self.stable_frame_count >= MIN_STABLE_FRAMES):
                self.current_state = 'IDLE'
                self.state_timer = 0
                return False
            return True
        
        return False


class MovementDetector(BaseGestureDetector):
    """
    Detects walking, sprinting, and strafing based on body movement.
    
    Uses ankle oscillation for walking detection with fallback to knees/hips
    when ankles are occluded. Implements state machine with hysteresis to
    prevent false positives and ensure stable detection.
    
    Torso lean detection uses simple X-coordinate displacement for strafing,
    which is more robust to camera angles than 3D vector approaches.
    """
    
    def __init__(self):
        super().__init__("movement")
        
        # State machine for IDLE ↔ WALKING transitions
        self.movement_state = MovementState()
        
        # Smoothing buffers for temporal filtering
        self.leg_motion_history = deque(maxlen=3)
        self.lean_history = deque(maxlen=3)
        
        # Calibration data
        self.scale_factor = None  # Torso height for normalization
        self.baseline_ankle_y = None
    
    def detect(self, state_manager):
        """
        Detect movement gestures each frame.
        
        Args:
            state_manager: GestureStateManager instance with landmark history
        
        Returns:
            Dictionary with movement info or None:
            {
                'action': 'move',
                'is_walking': bool,
                'left_thumb_back': bool,  # TODO: Not implemented
                'torso_lean': 'left'|'right'|None
            }
        """
        if not self.enabled:
            return None
        
        # Check if we have enough landmark history (need 5+ frames for velocity)
        if len(state_manager.landmark_history) < 5:
            return None
        
        # Calculate scale factor for normalization (if not already set)
        if self.scale_factor is None:
            self.scale_factor = self._compute_scale_factor(state_manager)
            if self.scale_factor is None:
                return None  # Can't normalize without scale
        
        # Detect leg motion (walking-in-place)
        leg_motion_score = self._detect_leg_motion(state_manager)
        
        # Update state machine with hysteresis
        is_walking = self.movement_state.update(leg_motion_score)
        
        # Detect torso lean for strafing (independent of walking state)
        torso_lean = self._detect_torso_lean_simple(state_manager)
        
        # Return result if any movement detected
        if is_walking or torso_lean is not None:
            return {
                'action': 'move',
                'is_walking': is_walking,
                'left_thumb_back': False,  # TODO: Implement backward movement
                'torso_lean': torso_lean
            }
        
        return None  # No movement detected
    
    def _compute_scale_factor(self, state_manager):
        """
        Calculate torso height for scale normalization.
        
        Normalizes all distance/velocity measurements by user's torso height
        to ensure algorithm works regardless of distance from camera.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            float: Torso height in normalized coordinates (typically ~0.3-0.5)
                   or None if landmarks unavailable
        """
        nose = state_manager.get_landmark_position('nose')
        left_hip = state_manager.get_landmark_position('left_hip')
        right_hip = state_manager.get_landmark_position('right_hip')
        
        if nose is None or left_hip is None or right_hip is None:
            return None
        
        # Calculate mid-hip position
        mid_hip = (np.array(left_hip) + np.array(right_hip)) / 2.0
        
        # Torso height = distance from nose to mid-hip
        torso_height = np.linalg.norm(np.array(nose) - mid_hip)
        
        # Sanity check: torso height should be reasonable
        if torso_height < 0.1:  # Too small, likely tracking error
            return None
        
        return torso_height
    
    def _detect_leg_motion(self, state_manager):
        """
        Detect walking-in-place motion via ankle/knee oscillation.
        
        Uses vertical velocity and range of motion to determine if user is
        performing walking-in-place gesture. Includes fallback strategy:
        ankles → knees → hips if landmarks are occluded.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            float: Leg motion score (0.0 = no motion, 0.15+ = clear walking)
        """
        # Get best available landmarks with fallback strategy
        left_name, right_name, use_knees = self._get_best_leg_landmarks(
            state_manager
        )
        
        if left_name is None:
            return 0.0  # No valid landmarks available
        
        # Calculate vertical velocities (Y-axis in normalized coordinates)
        window_size = 5  # ~0.17 seconds at 30fps
        left_vel = state_manager.get_velocity(left_name, window_size)
        right_vel = state_manager.get_velocity(right_name, window_size)
        
        if left_vel is None or right_vel is None:
            return 0.0
        
        # Extract Y-component (vertical motion in image coordinates)
        # Note: Y increases downward in image coords, so we use absolute value
        left_vy = abs(left_vel[1])
        right_vy = abs(right_vel[1])
        avg_vertical_speed = (left_vy + right_vy) / 2.0
        
        # Calculate range of motion (Y-coordinate variation over window)
        left_range = self._calculate_y_range(state_manager, left_name, 15)
        right_range = self._calculate_y_range(state_manager, right_name, 15)
        avg_range = (left_range + right_range) / 2.0
        
        # Normalize by scale factor (body dimensions)
        normalized_speed = avg_vertical_speed / self.scale_factor
        normalized_range = avg_range / self.scale_factor
        
        # Combined score: velocity + range indicates walking
        # Scale factors chosen to bring scores into ~0-1 range
        velocity_component = normalized_speed * 10.0
        range_component = normalized_range * 5.0
        leg_motion_score = (velocity_component + range_component) / 2.0
        
        # Apply temporal smoothing to reduce jitter
        self.leg_motion_history.append(leg_motion_score)
        if len(self.leg_motion_history) > 0:
            smoothed_score = sum(self.leg_motion_history) / len(self.leg_motion_history)
            return smoothed_score
        
        return leg_motion_score
    
    def _calculate_y_range(self, state_manager, landmark_name, window_frames):
        """
        Calculate range of Y-coordinate variation over time window.
        
        This measures how much the landmark moves vertically, which indicates
        leg lifting motion during walking-in-place.
        
        Args:
            state_manager: GestureStateManager instance
            landmark_name: Name of landmark to track
            window_frames: Number of frames to analyze
        
        Returns:
            float: Range of Y-coordinates (max - min)
        """
        y_positions = []
        history_len = len(state_manager.landmark_history)
        
        for i in range(min(window_frames, history_len)):
            pos = state_manager.get_landmark_position(landmark_name, i)
            if pos is not None:
                y_positions.append(pos[1])
        
        # Need at least half the window to compute meaningful range
        if len(y_positions) < window_frames // 2:
            return 0.0
        
        return max(y_positions) - min(y_positions)
    
    def _get_best_leg_landmarks(self, state_manager):
        """
        Get best available leg landmarks with fallback strategy.
        
        Tries ankles first (most sensitive), then knees, then hips.
        This ensures detection continues even when lower landmarks are occluded.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            tuple: (left_landmark_name, right_landmark_name, use_knees_flag)
                   or (None, None, False) if no valid landmarks
        """
        # Try ankles first (most sensitive to leg motion)
        if self._check_visibility(state_manager, ['left_ankle', 'right_ankle']):
            return ('left_ankle', 'right_ankle', False)
        
        # Fallback to knees (more reliable, less occluded)
        if self._check_visibility(state_manager, ['left_knee', 'right_knee']):
            return ('left_knee', 'right_knee', True)
        
        # Fallback to hips (very conservative detection)
        if self._check_visibility(state_manager, ['left_hip', 'right_hip']):
            return ('left_hip', 'right_hip', True)
        
        # No valid landmarks available
        return (None, None, False)
    
    def _check_visibility(self, state_manager, landmark_names):
        """
        Check if landmarks are visible with sufficient confidence.
        
        Args:
            state_manager: GestureStateManager instance
            landmark_names: List of landmark names to check
        
        Returns:
            bool: True if all landmarks meet visibility threshold
        """
        if not state_manager.landmark_history:
            return False
        
        landmarks_dict = state_manager.landmark_history[-1]
        
        for name in landmark_names:
            visibility = self._get_landmark_visibility(landmarks_dict, name)
            if visibility < VISIBILITY_THRESHOLD:
                return False
        
        return True
    
    def _get_landmark_visibility(self, landmarks_dict, landmark_name):
        """
        Extract visibility score for specific landmark.
        
        Args:
            landmarks_dict: Dictionary from pose_tracking with landmark data
            landmark_name: Name of landmark to get visibility for
        
        Returns:
            float: Visibility score (0.0-1.0) or 0.0 if not found
        """
        if landmarks_dict.get('pose'):
            for lm in landmarks_dict['pose']:
                if lm.get('name') == landmark_name:
                    return lm.get('visibility', 0.0)
        return 0.0
    
    def _detect_torso_lean_simple(self, state_manager):
        """
        Simple torso lean detection using X-coordinate displacement.
        
        Measures horizontal displacement between nose and shoulder midpoint.
        This approach is more robust to camera angles than 3D vector methods.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            str: 'left', 'right', or None
        """
        left_shoulder = state_manager.get_landmark_position('left_shoulder')
        right_shoulder = state_manager.get_landmark_position('right_shoulder')
        nose = state_manager.get_landmark_position('nose')
        
        if left_shoulder is None or right_shoulder is None or nose is None:
            return None
        
        # Check visibility of required landmarks
        if not self._check_visibility(state_manager, 
                                      ['left_shoulder', 'right_shoulder', 'nose']):
            return None
        
        # Calculate shoulder midpoint X-coordinate
        shoulder_mid_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
        nose_x = nose[0]
        
        # Horizontal displacement (normalized by scale)
        displacement = (nose_x - shoulder_mid_x) / self.scale_factor
        
        # Apply thresholds to determine lean direction
        if displacement > LEAN_SIMPLE_THRESHOLD:
            lean = 'right'
        elif displacement < -LEAN_SIMPLE_THRESHOLD:
            lean = 'left'
        else:
            lean = None
        
        # Apply temporal smoothing: require consistent lean for 2/3 frames
        self.lean_history.append(lean)
        
        if len(self.lean_history) >= 2:
            # Return lean only if last 2 frames agree
            if self.lean_history[-1] == self.lean_history[-2]:
                return self.lean_history[-1]
        
        return None
    
    def reset(self):
        """Reset detector state to initial conditions."""
        super().reset()
        self.movement_state = MovementState()
        self.leg_motion_history.clear()
        self.lean_history.clear()
        self.scale_factor = None
        self.baseline_ankle_y = None