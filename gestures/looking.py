"""
Looking gesture detector - controls mouse by rotating head left/right
"""

import numpy as np
from gestures.base_detector import BaseGestureDetector


class LookingDetector(BaseGestureDetector):
    """
    Detects head rotation for mouse control using facial landmarks.
    
    Uses the distance between face edge and outer canthus (corner) of eyes:
    - Left distance: landmarks 127 (face edge) to 33 (left outer canthus)
    - Right distance: landmarks 356 (face edge) to 263 (right outer canthus)
    
    When the head rotates left, the left distance increases and right distance decreases.
    When the head rotates right, the right distance increases and left distance decreases.
    """
    
    def __init__(self):
        super().__init__("looking")
        
        # Configuration for horizontal (left/right) control
        self.tilt_multiplier = 8  # Ratio threshold to trigger movement (adjustable)
        self.deadzone = 0.4  # Minimum ratio difference to prevent drift (adjustable)
        
        # Configuration for vertical (up/down) control
        # Thresholds operate on shoulder-normalized distances (scale-invariant)
        self.y_threshold = 0.015  # If |avg Y distance|/shoulder_dist > this, tilt detected (adjustable)
        self.y_deadzone = 0.1  # Deadzone for vertical movement (adjustable)
        
        # Mouse movement speed
        self.mouse_speed = 7  # Base speed units per frame (scaled by HEAD_LOOK_SENSITIVITY in coordinator)
        
        # Facial landmark indices
        self.left_edge = 127  # Left face edge
        self.left_eye_outer = 33  # Left eye outer canthus
        self.right_edge = 356  # Right face edge
        self.right_eye_outer = 263  # Right eye outer canthus
        
        # State tracking
        self._state = {
            'last_dx': 0,  # Last mouse movement for smoothing
        }
    
    def _get_face_landmark(self, landmarks_dict, index):
        """
        Get a specific face landmark by index.
        
        Args:
            landmarks_dict: Landmark dictionary from state manager
            index: Face landmark index (0-467)
        
        Returns:
            numpy array [x, y, z] or None if not available
        """
        if landmarks_dict is None:
            return None
        
        face_landmarks = landmarks_dict.get('face')
        if face_landmarks is None or len(face_landmarks) <= index:
            return None
        
        landmark = face_landmarks[index]
        return np.array([landmark['x'], landmark['y'], landmark['z']])
    
    def _calculate_x_distance(self, pos1, pos2):
        """
        Calculate horizontal (X-axis) distance between two points.
        Head rotation primarily affects the horizontal spacing.
        
        Args:
            pos1: numpy array [x, y, z]
            pos2: numpy array [x, y, z]
        
        Returns:
            Float: Absolute X distance between points, or None if positions are invalid
        """
        if pos1 is None or pos2 is None:
            return None
        
        # Use only X coordinate (horizontal distance)
        return abs(pos1[0] - pos2[0])
    
    def _calculate_y_distance(self, pos1, pos2):
        """
        Calculate vertical (Y-axis) SIGNED distance between two points.
        Head tilt up/down primarily affects the vertical spacing.
        
        Args:
            pos1: numpy array [x, y, z] - face edge position
            pos2: numpy array [x, y, z] - eye canthus position
        
        Returns:
            Float: Signed Y distance (pos2 Y - pos1 Y)
            - Positive = canthus is BELOW face edge (head tilted down)
            - Negative = canthus is ABOVE face edge (head tilted up)
            Or None if positions are invalid
        """
        if pos1 is None or pos2 is None:
            return None
        
        # Use only Y coordinate (signed distance)
        # In image coordinates, Y increases downward
        return pos2[1] - pos1[1]
    
    def detect(self, state_manager):
        """
        Detect head rotation and return mouse movement.
        
        Args:
            state_manager: GestureStateManager instance
        
        Returns:
            Dictionary with mouse movement:
            {
                'action': 'head_look',
                'dx': horizontal_movement,  # Positive = right, negative = left
                'dy': 0  # No vertical movement for now
            }
            or None if no significant rotation detected
        """
        if not self.enabled:
            return None
        
        # Get current frame landmarks
        if len(state_manager.landmark_history) == 0:
            return None
        
        current_landmarks = state_manager.landmark_history[-1]
        
        # Get the four key facial landmarks
        left_edge_pos = self._get_face_landmark(current_landmarks, self.left_edge)
        left_eye_pos = self._get_face_landmark(current_landmarks, self.left_eye_outer)
        right_edge_pos = self._get_face_landmark(current_landmarks, self.right_edge)
        right_eye_pos = self._get_face_landmark(current_landmarks, self.right_eye_outer)
        
        # Check if all landmarks are available
        if any(pos is None for pos in [left_edge_pos, left_eye_pos, right_edge_pos, right_eye_pos]):
            return None
        
        # === HORIZONTAL CONTROL (Left/Right) ===
        # Calculate X distances on each side
        left_x_distance = self._calculate_x_distance(left_edge_pos, left_eye_pos)
        right_x_distance = self._calculate_x_distance(right_edge_pos, right_eye_pos)
        
        if left_x_distance is None or right_x_distance is None:
            return None
        
        # Avoid division by zero
        if left_x_distance < 1e-6 or right_x_distance < 1e-6:
            return None
        
        # Calculate the ratio of X distances
        left_to_right_ratio = left_x_distance / right_x_distance
        right_to_left_ratio = right_x_distance / left_x_distance
        
        # Determine horizontal mouse movement based on ratio
        dx = 0
        threshold_value = self.tilt_multiplier + self.deadzone
        
        # Head tilted right (left distance > right distance)
        # When you turn your head right, the left side of your face is more visible
        if left_to_right_ratio > threshold_value:
            # Move mouse left (inverted for natural feel)
            dx = -self.mouse_speed
        
        # Head tilted left (right distance > left distance)
        # When you turn your head left, the right side of your face is more visible
        elif right_to_left_ratio > threshold_value:
            # Move mouse right (inverted for natural feel)
            dx = self.mouse_speed
        
        # === VERTICAL CONTROL (Up/Down) ===
        # Calculate SIGNED Y distances on each side
        # Positive = canthus is BELOW face edge (head tilted down)
        # Negative = canthus is ABOVE face edge (head tilted up)
        left_y_distance = self._calculate_y_distance(left_edge_pos, left_eye_pos)
        right_y_distance = self._calculate_y_distance(right_edge_pos, right_eye_pos)
        
        # Average the Y distances from both sides for more stable detection
        avg_y_distance = (left_y_distance + right_y_distance) / 2.0
        
        # Determine vertical mouse movement based on shoulder-normalized average Y distance
        dy = 0

        # Compute shoulder distance for scale normalization (pose landmarks 11 and 12)
        # Use state_manager to fetch named pose landmarks ('left_shoulder', 'right_shoulder')
        left_shoulder = state_manager.get_landmark_position('left_shoulder')
        right_shoulder = state_manager.get_landmark_position('right_shoulder')

        shoulder_distance = None
        avg_y_normalized = None
        if left_shoulder is not None and right_shoulder is not None:
            # Euclidean distance in image-normalized XY space
            shoulder_vec = left_shoulder[:2] - right_shoulder[:2]
            shoulder_distance = float(np.linalg.norm(shoulder_vec))
            if shoulder_distance > 1e-6:
                avg_y_normalized = avg_y_distance / shoulder_distance

        # Fallback: if we cannot compute a reliable shoulder distance, use raw avg_y_distance
        value_for_threshold = avg_y_normalized if avg_y_normalized is not None else avg_y_distance
        y_threshold_value = self.y_threshold + self.y_deadzone

        # Head tilted UP: requires threshold (canthus significantly ABOVE face edge)
        if value_for_threshold < -y_threshold_value:
            # Negative = canthus ABOVE face edge = head tilted UP
            # Move mouse up (negative Y in screen coordinates)
            dy = -self.mouse_speed

        # Head tilted DOWN: any amount below triggers (canthus BELOW face edge)
        elif value_for_threshold > 0:
            # Positive = canthus BELOW face edge = head tilted DOWN
            # Move mouse down (positive Y in screen coordinates)
            dy = self.mouse_speed
        
        # Store for smoothing (optional future enhancement)
        self._state['last_dx'] = dx
        
        # Always return data for debug display (even when dx/dy is 0)
        # This allows the HUD to show distances and ratios for tuning
        # Show the maximum ratio for easier debugging
        max_x_ratio = max(left_to_right_ratio, right_to_left_ratio)
        
        return {
            'action': 'head_look',
            'dx': dx,
            'dy': dy,
            'left_x_distance': left_x_distance,
            'right_x_distance': right_x_distance,
            'left_y_distance': left_y_distance,
            'right_y_distance': right_y_distance,
            'avg_y_distance': avg_y_distance,
            'avg_y_distance_normalized': avg_y_normalized if avg_y_normalized is not None else avg_y_distance,
            'shoulder_distance': shoulder_distance if shoulder_distance is not None else 0.0,
            'x_ratio': max_x_ratio,
            'left_to_right_ratio': left_to_right_ratio,
            'right_to_left_ratio': right_to_left_ratio
        }
    
    def reset(self):
        """Reset detector state."""
        self._state = {
            'last_dx': 0,
        }

