"""
Hand scroll gesture detector - controls scrolling based on LEFT hand rotation

This detector uses MediaPipe LEFT hand landmarks to perform continuous scrolling
based on hand rotation (ratio_a) - only when the LEFT hand is OPEN and the left arm
is held vertically (horizontal displacement below threshold).

Requirements:
1. Left arm vertical: |dx|/eye_width < threshold (where dx = wrist_x - elbow_x)
2. LEFT hand must be open (all fingers extended and spread)
3. LEFT hand must be rotated beyond threshold

The function detects forward/backward hand rotation using a signed ratio (ratio_a).
When the hand stays rotated beyond a threshold and remains open with arm vertical,
it continuously scrolls up or down every frame until the rotation returns near baseline.
"""

import numpy as np
from collections import deque
from gestures.base_detector import BaseGestureDetector


# Constants for scroll detection
SCROLL_FRAMES = 5               # Rolling window size for frame history
# Threshold for |ratio_a| where ratio_a = (y5 - y17) / eye_width.
# ratio_a is already normalized by eye width, so this is dimensionless.
SCROLL_THRESHOLD_MULT = 0.20    # Higher value = less sensitive
SCROLL_SPEED = 1                # Reserved for future tuning
INNER_DEAD_ZONE = 0.1           # Dead zone as a fraction of threshold (prevents micro drift)
VERTICAL_ARM_THRESHOLD_MULT = 2  # Horizontal displacement threshold: |dx|/eye_width must be < this value


class HandScrollDetector(BaseGestureDetector):
    """
    Detects LEFT hand rotation for continuous scrolling using MediaPipe hand landmarks.
    
    Requirements:
    1. Left arm vertical: |dx|/eye_width < 0.5 (horizontal displacement must be small - more lenient)
    2. LEFT hand must be OPEN (fingertips above joints, wide palm)
    3. LEFT hand rotation (ratio_a) must exceed threshold
    
    Logic:
    - Computes ratio_a = (y(landmark_5) - y(landmark_17)) / eye_width
    - Signed ratio indicates rotation direction (positive/negative)
    - Maintains rolling window of ratio history for stability
    - Continuously scrolls when ratio stays beyond threshold
    """
    
    def __init__(self):
        super().__init__("hand_scroll")
        
        # Configuration
        self.scroll_frames = SCROLL_FRAMES
        self.scroll_threshold_mult = SCROLL_THRESHOLD_MULT
        self.scroll_speed = SCROLL_SPEED
        self.inner_dead_zone = INNER_DEAD_ZONE
        
        # State tracking
        self._state = {
            'ratio_history': deque(maxlen=SCROLL_FRAMES),  # Rolling window of ratio_a values
            'last_scroll_action': 'none',  # 'up', 'down', or 'none'
        }
    
    def _is_left_arm_vertical(self, state_manager, eye_width):
        """
        Check if the left arm (elbow to wrist) is close to vertical.
        
        Uses pose landmarks:
        - LEFT_ELBOW: landmark 13
        - LEFT_WRIST: landmark 15
        
        Checks if horizontal displacement (|dx|) normalized by eye_width is below threshold.
        
        Args:
            state_manager: GestureStateManager instance
            eye_width: Eye width for scale normalization
        
        Returns:
            bool: True if arm is vertical (|dx|/eye_width < threshold)
        """
        # Get left elbow and wrist positions from pose landmarks
        left_elbow = state_manager.get_landmark_position('left_elbow', frame_offset=0)
        left_wrist = state_manager.get_landmark_position('left_wrist', frame_offset=0)
        
        if left_elbow is None or left_wrist is None:
            print("[ARM VERTICAL DEBUG] ❌ Left elbow or wrist not detected")
            return False
        
        if eye_width is None or eye_width < 1e-6:
            print("[ARM VERTICAL DEBUG] ❌ Eye width invalid")
            return False
        
        # Calculate horizontal displacement (dx)
        dx = left_wrist[0] - left_elbow[0]
        dy = left_wrist[1] - left_elbow[1]  # Y increases downward in image coordinates
        
        # Normalize horizontal displacement by eye_width
        dx_normalized = abs(dx) / eye_width
        
        # Calculate threshold
        threshold = VERTICAL_ARM_THRESHOLD_MULT
        
        print(f"[ARM VERTICAL DEBUG] Elbow: ({left_elbow[0]:.3f}, {left_elbow[1]:.3f}), Wrist: ({left_wrist[0]:.3f}, {left_wrist[1]:.3f})")
        print(f"[ARM VERTICAL DEBUG] dx={dx:.3f}, dy={dy:.3f}, |dx|/eye_width={dx_normalized:.3f} (threshold: {threshold:.3f})")
        
        # Check if horizontal displacement is small enough (arm is vertical)
        is_vertical = dx_normalized < threshold
        
        print(f"[ARM VERTICAL DEBUG] Is vertical? {is_vertical}")
        
        return is_vertical
    
    def _get_hand_landmark(self, landmarks_dict, hand_type, index):
        """
        Get a specific hand landmark by index.
        
        Args:
            landmarks_dict: Landmark dictionary from state manager
            hand_type: 'left_hand' or 'right_hand'
            index: Hand landmark index (0-20)
        
        Returns:
            numpy array [x, y, z] or None if not available
        """
        if landmarks_dict is None:
            return None
        
        hand_landmarks = landmarks_dict.get(hand_type)
        if hand_landmarks is None or len(hand_landmarks) <= index:
            return None
        
        landmark = hand_landmarks[index]
        return np.array([landmark['x'], landmark['y'], landmark['z']])
    
    def _calculate_eye_width(self, state_manager):
        """
        Calculate eye width using facial landmarks for scale normalization.
        
        Uses the distance between left and right eye outer canthi (corners):
        - Left eye outer canthus: landmark 33
        - Right eye outer canthus: landmark 263
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Float representing eye width, or None if landmarks unavailable
        """
        if len(state_manager.landmark_history) == 0:
            return None
        
        current_landmarks = state_manager.landmark_history[-1]
        face_landmarks = current_landmarks.get('face')
        
        if face_landmarks is None or len(face_landmarks) < 264:
            return None
        
        # Get left and right eye outer canthus positions
        left_eye_outer = face_landmarks[33]
        right_eye_outer = face_landmarks[263]
        
        left_pos = np.array([left_eye_outer['x'], left_eye_outer['y'], left_eye_outer['z']])
        right_pos = np.array([right_eye_outer['x'], right_eye_outer['y'], right_eye_outer['z']])
        
        # Calculate Euclidean distance in XY plane
        eye_width = np.linalg.norm(left_pos[:2] - right_pos[:2])
        
        return eye_width if eye_width > 1e-6 else None
    
    def _is_hand_open(self, hand_landmarks_dict, hand_type='right_hand'):
        """
        Check if the hand is OPEN.
        
        A hand is considered open when:
        1. Each fingertip is above its middle joint (for upright palm):
           - Index finger: 8.y < 6.y
           - Middle finger: 12.y < 10.y
           - Ring finger: 16.y < 14.y
           - Pinky: 20.y < 18.y
        2. Wide palm: distance(8, 20) > 0.25 * distance(5, 17)
        
        Args:
            hand_landmarks_dict: Landmark dictionary from state manager
            hand_type: 'left_hand' or 'right_hand'
        
        Returns:
            bool: True if hand is open, False otherwise
        """
        if hand_landmarks_dict is None:
            return False
        
        hand_landmarks = hand_landmarks_dict.get(hand_type)
        if hand_landmarks is None or len(hand_landmarks) < 21:
            return False
        
        # Check if each fingertip is above its middle joint
        # Landmark indices: tip, middle_joint
        finger_checks = [
            (8, 6),   # Index finger
            (12, 10), # Middle finger
            (16, 14), # Ring finger
            (20, 18), # Pinky
        ]
        
        for tip_idx, joint_idx in finger_checks:
            tip = hand_landmarks[tip_idx]
            joint = hand_landmarks[joint_idx]
            
            # In image coordinates, Y increases downward
            # So fingertip above joint means tip.y < joint.y
            if tip['y'] >= joint['y']:
                return False  # Finger not extended
        
        # Check palm width (distance between index tip and pinky tip)
        index_tip = hand_landmarks[8]
        pinky_tip = hand_landmarks[20]
        index_pos = np.array([index_tip['x'], index_tip['y']])
        pinky_pos = np.array([pinky_tip['x'], pinky_tip['y']])
        palm_width = np.linalg.norm(index_pos - pinky_pos)
        
        # Check reference distance (wrist to middle finger base)
        wrist = hand_landmarks[0]
        middle_base = hand_landmarks[9]
        wrist_pos = np.array([wrist['x'], wrist['y']])
        middle_base_pos = np.array([middle_base['x'], middle_base['y']])
        reference_distance = np.linalg.norm(wrist_pos - middle_base_pos)
        
        # Palm should be wide (fingers spread)
        # Reduced threshold from 0.25 to 0.15 for easier hand open detection
        if reference_distance > 1e-6:
            if palm_width < 0.005 * reference_distance:
                return False  # Palm not wide enough
        
        return True
    
    def _compute_ratio_a(self, hand_landmarks_dict, eye_width, hand_type='right_hand'):
        """
        Compute ratio_a for hand rotation detection.
        
        ratio_a = (y(landmark_5) - y(landmark_17)) / eye_width
        
        - Landmark 5: Index finger base (MCP joint)
        - Landmark 17: Pinky base (MCP joint)
        - Signed ratio: positive/negative indicates rotation direction
        
        Args:
            hand_landmarks_dict: Landmark dictionary from state manager
            eye_width: Eye width for normalization
            hand_type: 'left_hand' or 'right_hand'
        
        Returns:
            Float representing ratio_a, or None if computation fails
        """
        if hand_landmarks_dict is None or eye_width is None or eye_width < 1e-6:
            return None
        
        # Get landmarks 5 and 17
        landmark_5 = self._get_hand_landmark(hand_landmarks_dict, hand_type, 5)
        landmark_17 = self._get_hand_landmark(hand_landmarks_dict, hand_type, 17)
        
        if landmark_5 is None or landmark_17 is None:
            return None
        
        # Compute signed ratio_a
        # In image coordinates, Y increases downward
        y_diff = landmark_5[1] - landmark_17[1]
        ratio_a = y_diff / eye_width
        
        return ratio_a
    
    def detect(self, state_manager):
        """
        Detect hand rotation and perform continuous scrolling.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Dictionary with scroll info:
            {
                'action': 'hand_scroll',
                'ratio_a': current_ratio_a,
                'threshold': threshold,
                'hand_open': bool,
                'scrolling': 'up' / 'down' / 'none'
            }
            or None if gesture not detected
        """
        if not self.enabled:
            print("[HAND_SCROLL DEBUG] ⚠️  Detector disabled")
            return None
        
        # Check if we have landmark history
        if len(state_manager.landmark_history) == 0:
            print("[HAND_SCROLL DEBUG] ⚠️  No landmark history")
            return None
        
        current_landmarks = state_manager.landmark_history[-1]
        print(f"[HAND_SCROLL DEBUG] 🔍 Processing frame, landmarks available")
        
        # Calculate eye width for scale normalization
        eye_width = self._calculate_eye_width(state_manager)
        if eye_width is None:
            return None
        
        # Define threshold (ratio_a is already normalized by eye_width)
        threshold = self.scroll_threshold_mult
        inner_dead_zone = threshold * self.inner_dead_zone
        
        # Compute ratio_a for left hand
        hand_type = 'left_hand'
        ratio_a = self._compute_ratio_a(current_landmarks, eye_width, hand_type)
        
        if ratio_a is None:
            print("[HAND_SCROLL DEBUG] ❌ ratio_a is None (hand not detected)")
            return None
        
        print(f"[HAND_SCROLL DEBUG] ✓ ratio_a={ratio_a:.4f}, threshold=±{threshold:.4f}, eye_width={eye_width:.4f}")
        
        # Check if left arm (elbow to wrist) is vertical
        arm_is_vertical = self._is_left_arm_vertical(state_manager, eye_width)
        
        print(f"[HAND_SCROLL DEBUG] Arm vertical check: {arm_is_vertical}")
        
        # Check if hand is open
        hand_open = self._is_hand_open(current_landmarks, hand_type)
        
        # Add ratio_a to rolling window
        self._state['ratio_history'].append(ratio_a)
        
        # Initialize scroll action
        scrolling = 'none'
        
        print(f"[HAND_SCROLL DEBUG] Hand open: {hand_open}, Arm vertical: {arm_is_vertical}")
        
        # Only process scroll logic if hand is OPEN AND arm is VERTICAL
        if hand_open and arm_is_vertical:
            # Check if we have enough history for stable detection
            if len(self._state['ratio_history']) >= self.scroll_frames:
                # Compute average ratio over window for stability
                avg_ratio = sum(self._state['ratio_history']) / len(self._state['ratio_history'])
                
                # Check if all frames in window consistently exceed threshold
                # This prevents jittery/inconsistent scrolling
                all_above_positive = all(r > threshold for r in self._state['ratio_history'])
                all_below_negative = all(r < -threshold for r in self._state['ratio_history'])
                
                print(f"[SCROLL LOGIC DEBUG] avg_ratio={avg_ratio:.4f}, all_below_neg={all_below_negative}, all_above_pos={all_above_positive}")
                
                # Apply inner dead zone to prevent micro drift
                if abs(avg_ratio) < inner_dead_zone:
                    # Inside inner dead zone - no scroll
                    scrolling = 'none'
                    print("[SCROLL LOGIC DEBUG] ⏸️  In dead zone")
                elif all_below_negative:
                    # Consistently rotated forward (negative) - scroll UP
                    # ratio_a < -threshold → scroll UP
                    scrolling = 'up'
                    print("[SCROLL LOGIC DEBUG] ⬆️  SCROLLING UP (signal)!")
                elif all_above_positive:
                    # Consistently rotated backward (positive) - scroll DOWN
                    # ratio_a > +threshold → scroll DOWN
                    scrolling = 'down'
                    print("[SCROLL LOGIC DEBUG] ⬇️  SCROLLING DOWN (signal)!")
                else:
                    print("[SCROLL LOGIC DEBUG] ⏸️  Not all frames consistent")
            else:
                print(f"[SCROLL LOGIC DEBUG] ⏳ Building history: {len(self._state['ratio_history'])}/{self.scroll_frames}")
        else:
            if not hand_open:
                print("[SCROLL LOGIC DEBUG] ❌ Hand not open")
            if not arm_is_vertical:
                print("[SCROLL LOGIC DEBUG] ❌ Arm not vertical")
        
        # Update last scroll action
        self._state['last_scroll_action'] = scrolling
        
        # Return debug information
        return {
            'action': 'hand_scroll',
            'ratio_a': ratio_a,
            'threshold': threshold,
            'hand_open': hand_open,
            'arm_is_vertical': arm_is_vertical,
            'scrolling': scrolling,
            'eye_width': eye_width,
            'inner_dead_zone': inner_dead_zone,
            'history_size': len(self._state['ratio_history']),
        }
    
    def reset(self):
        """Reset detector state."""
        self._state = {
            'ratio_history': deque(maxlen=SCROLL_FRAMES),
            'last_scroll_action': 'none',
        }
