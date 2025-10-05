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
# Movement thresholds
WALK_ENTER_THRESHOLD = 0.28   # Enter WALKING state (higher to reduce false triggers)
WALK_EXIT_THRESHOLD = 0.12    # Exit to IDLE (hysteresis gap)
VISIBILITY_THRESHOLD = 0.7     # MediaPipe visibility confidence minimum (stricter)
MIN_STABLE_FRAMES = 3          # Frames required for stable state transition

# Leg motion signal shaping
LEG_MIN_SPEED = 0.04           # Minimum normalized vertical speed to consider
LEG_MIN_RANGE = 0.015          # Minimum normalized vertical range to consider
ANTI_PHASE_WINDOW = 5          # Frames to evaluate left/right anti-phase pattern
ANTI_PHASE_MIN_RATIO = 0.6     # Proportion of frames needing opposite vertical velocity signs

# Lean/strafe thresholds (with hysteresis)
LEAN_ENTER_THRESHOLD = 0.025   # Enter lean state (normalized by scale)
LEAN_EXIT_THRESHOLD = 0.012    # Exit lean state (hysteresis)
LEAN_DEADZONE = 0.010          # Minimum displacement to ignore (noise/small movements)
LEAN_COOLDOWN_FRAMES = 10      # Frames to wait after lean ends before allowing walking (0.5s at 30fps)


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
        if score_delta < 0.5:  # Stability threshold
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
    
    def __init__(self, 
                 lean_enter_threshold=LEAN_ENTER_THRESHOLD, 
                 lean_exit_threshold=LEAN_EXIT_THRESHOLD,
                 lean_deadzone=LEAN_DEADZONE):
        super().__init__("movement")
        
        # State machine for IDLE ↔ WALKING transitions
        self.movement_state = MovementState()
        
        # Smoothing buffers for temporal filtering
        self.leg_motion_history = deque(maxlen=5)
        self.lean_history = deque(maxlen=5)
        self.anti_phase_history = deque(maxlen=ANTI_PHASE_WINDOW)
        
        # Calibration data
        self.scale_factor = None  # Torso height for normalization
        self.baseline_ankle_y = None
        
        # Configurable lean detection thresholds
        self.lean_enter_threshold = lean_enter_threshold
        self.lean_exit_threshold = lean_exit_threshold
        self.lean_deadzone = lean_deadzone
        
        # Lean cooldown tracking for hysteresis
        self.lean_cooldown_timer = 0  # Frames remaining in cooldown
        self.last_lean_detected = None  # Track previous lean state
    
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
        
        # Detect torso lean for strafing first (to track state changes)
        torso_lean = self._detect_torso_lean_simple(state_manager)
        
        # Track lean state changes for cooldown management
        if self.last_lean_detected is not None and torso_lean is None:
            # Lean just ended, start cooldown
            self.lean_cooldown_timer = LEAN_COOLDOWN_FRAMES
        elif torso_lean is not None:
            # Lean is active, reset cooldown
            self.lean_cooldown_timer = 0
        elif self.lean_cooldown_timer > 0:
            # Decrement cooldown timer
            self.lean_cooldown_timer -= 1
        
        self.last_lean_detected = torso_lean
        
        # Detect leg motion (walking-in-place)
        leg_motion_score = self._detect_leg_motion(state_manager)
        
        # Apply cooldown: suppress walking detection if we're in cooldown period
        if self.lean_cooldown_timer > 0:
            # Suppress walking detection during cooldown after a lean ends
            leg_motion_score = 0.0
        
        # Update state machine with hysteresis
        is_walking = self.movement_state.update(leg_motion_score)
        
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
        # Normalize by scale so values are relative to body size
        left_vy_raw = left_vel[1] / self.scale_factor
        right_vy_raw = right_vel[1] / self.scale_factor
        left_vy = abs(left_vy_raw)
        right_vy = abs(right_vy_raw)
        avg_vertical_speed = (left_vy + right_vy) / 2.0
        
        # Calculate range of motion (Y-coordinate variation over window)
        left_range = self._calculate_y_range(state_manager, left_name, 15)
        right_range = self._calculate_y_range(state_manager, right_name, 15)
        avg_range = (left_range + right_range) / 2.0
        
        # Normalize by scale factor (body dimensions)
        normalized_speed = avg_vertical_speed
        normalized_range = avg_range / self.scale_factor

        # Apply basic deadzones to ignore tiny vibrations
        if normalized_speed < LEG_MIN_SPEED and normalized_range < LEG_MIN_RANGE:
            normalized_speed = 0.0
            normalized_range = 0.0
        
        # Combined score: velocity + range indicates walking
        # Scale factors chosen to bring scores into ~0-1 range
        velocity_component = normalized_speed * 8.0
        range_component = normalized_range * 4.0
        leg_motion_score = (velocity_component + range_component) / 2.0

        # Anti-phase gating: walking-in-place exhibits opposite vertical
        # velocities between left/right legs. Suppress score if not present
        # in a short temporal window to avoid false positives from body sway.
        opposite_sign = (
            left_vy_raw * right_vy_raw < 0 and
            left_vy >= LEG_MIN_SPEED and right_vy >= LEG_MIN_SPEED
        )
        self.anti_phase_history.append(1 if opposite_sign else 0)
        if len(self.anti_phase_history) >= max(3, ANTI_PHASE_WINDOW // 2):
            ratio = sum(self.anti_phase_history) / len(self.anti_phase_history)
            if ratio < ANTI_PHASE_MIN_RATIO:
                leg_motion_score = 0.0
        
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
        Simple torso lean detection using shoulder-to-hip X-coordinate displacement.
        
        Measures horizontal displacement between shoulder midpoint and hip midpoint.
        This measures actual torso posture and is independent of head movement,
        preventing interference with camera panning (which uses face/eye landmarks).
        This approach is more robust to camera angles than 3D vector methods.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            str: 'left', 'right', or None
        """
        left_shoulder = state_manager.get_landmark_position('left_shoulder')
        right_shoulder = state_manager.get_landmark_position('right_shoulder')
        left_hip = state_manager.get_landmark_position('left_hip')
        right_hip = state_manager.get_landmark_position('right_hip')
        
        if left_shoulder is None or right_shoulder is None or left_hip is None or right_hip is None:
            return None
        
        # Check visibility of required landmarks
        if not self._check_visibility(state_manager,
                                      ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip']):
            return None
        
        # Calculate shoulder midpoint X-coordinate
        shoulder_mid_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
        
        # Calculate hip midpoint X-coordinate
        hip_mid_x = (left_hip[0] + right_hip[0]) / 2.0
        
        # Horizontal displacement (normalized by scale)
        # Positive displacement = shoulders right of hips = leaning left
        displacement = (shoulder_mid_x - hip_mid_x) / self.scale_factor

        magnitude = abs(displacement)
        direction = 'left' if displacement > 0 else 'right'

        # Apply deadzone to filter out noise and small movements
        if magnitude < self.lean_deadzone:
            lean = None
        else:
            prev = self.last_lean_detected
            # Hysteresis: require larger magnitude to enter than to stay
            if prev is None:
                if magnitude >= self.lean_enter_threshold:
                    lean = direction
                else:
                    lean = None
            else:
                if direction == prev:
                    # Stay in current lean until it drops below exit threshold
                    lean = prev if magnitude >= self.lean_exit_threshold else None
                else:
                    # Switching sides requires meeting enter threshold
                    lean = direction if magnitude >= self.lean_enter_threshold else None
        
        # Apply temporal smoothing: require consistent lean for 2/3 frames
        self.lean_history.append(lean)

        # Temporal smoothing with hysteresis-aware consistency:
        # Require 3 consecutive matching frames to assert a lean,
        # which dramatically reduces flicker and false strafes.
        if len(self.lean_history) >= 3:
            if self.lean_history[-1] == self.lean_history[-2] == self.lean_history[-3]:
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
        self.lean_cooldown_timer = 0
        self.last_lean_detected = None
