"""
State Manager for temporal landmark tracking and gesture pattern detection
"""

from collections import deque
import numpy as np
import time


class GestureStateManager:
    """
    Manages temporal state for gesture detection including:
    - Landmark position history for velocity/acceleration calculation
    - Gesture pattern history
    - Active action tracking
    """
    
    def __init__(self, history_size=30, fps=30):
        """
        Initialize the state manager.
        
        Args:
            history_size: Number of frames to keep in history (default: 30 frames ~1 second at 30fps)
            fps: Expected frames per second for time calculations
        """
        self.history_size = history_size
        self.fps = fps
        self.dt = 1.0 / fps  # Time delta between frames
        
        # Landmark history: deque of landmark dictionaries
        self.landmark_history = deque(maxlen=history_size)
        
        # Gesture detection history
        self.gesture_history = deque(maxlen=history_size)
        
        # Current active actions (what keys/buttons are held)
        self.active_actions = set()
        
        # Calibration baseline (neutral pose)
        self.calibration_baseline = None
        
        # Frame timestamps
        self.timestamps = deque(maxlen=history_size)
        
        # Last update time
        self.last_update_time = None
    
    def update(self, landmarks_dict):
        """
        Update state with new landmark data.
        
        Args:
            landmarks_dict: Dictionary from `pose_tracking.get_landmarks()`.
                Should contain a 'pose' key with body landmarks.
                May also contain 'left_hand' and 'right_hand' keys for finger landmarks.
        """
        current_time = time.time()
        
        if landmarks_dict is not None:
            self.landmark_history.append(landmarks_dict)
            self.timestamps.append(current_time)
        
        self.last_update_time = current_time
    
    def set_calibration_baseline(self, landmarks_dict):
        """
        Set the neutral/calibration pose as baseline for relative measurements.
        
        Args:
            landmarks_dict: Landmark dictionary representing neutral pose
        """
        self.calibration_baseline = landmarks_dict
    
    def get_landmark_position(self, landmark_name, frame_offset=0):
        """
        Get the position of a specific landmark.
        
        Args:
            landmark_name: Name of the landmark (e.g., 'right_wrist', 'left_elbow')
            frame_offset: How many frames back to look (0 = current, 1 = previous, etc.)
        
        Returns:
            numpy array [x, y, z] or None if not available
        """
        if len(self.landmark_history) <= frame_offset:
            return None
        
        landmarks = self.landmark_history[-(frame_offset + 1)]
        
        # Try to get from pose landmarks first
        if landmarks.get('pose'):
            for landmark in landmarks['pose']:
                if landmark.get('name') == landmark_name:
                    return np.array([landmark['x'], landmark['y'], landmark['z']])
        
        # Check hand landmarks
        # Check hand landmarks if not found in pose
        for hand_type in ['left_hand', 'right_hand']:
            if hand_type.split('_')[0] in landmark_name.lower() and landmarks.get(hand_type):
                for landmark in landmarks[hand_type]:
                    if landmark.get('name') == landmark_name:
                        return np.array([landmark['x'], landmark['y'], landmark['z']])
        
        return None
    
    def get_velocity(self, landmark_name, window_size=3):
        """
        Calculate the velocity of a landmark over a time window.
        
        Args:
            landmark_name: Name of the landmark
            window_size: Number of frames to use for velocity calculation
        
        Returns:
            numpy array [vx, vy, vz] representing velocity, or None
        """
        if len(self.landmark_history) < window_size:
            return None
        
        # Get positions at different time points
        current_pos = self.get_landmark_position(landmark_name, 0)
        past_pos = self.get_landmark_position(landmark_name, window_size - 1)
        
        if current_pos is None or past_pos is None:
            return None
        
        # Calculate velocity (position change / time)
        time_delta = self.dt * (window_size - 1)
        velocity = (current_pos - past_pos) / time_delta
        
        return velocity
    
    def get_speed(self, landmark_name, window_size=3):
        """
        Calculate the speed (magnitude of velocity) of a landmark.
        
        Args:
            landmark_name: Name of the landmark
            window_size: Number of frames to use for calculation
        
        Returns:
            float representing speed, or None
        """
        velocity = self.get_velocity(landmark_name, window_size)
        if velocity is None:
            return None
        
        return np.linalg.norm(velocity)
    
    def get_acceleration(self, landmark_name, window_size=5):
        """
        Calculate the acceleration of a landmark.
        
        Args:
            landmark_name: Name of the landmark
            window_size: Number of frames to use
        
        Returns:
            numpy array [ax, ay, az] representing acceleration, or None
        """
        if len(self.landmark_history) < window_size:
            return None
        
        # Get velocities at two time points
        mid_point = window_size // 2
        velocity_now = self.get_velocity(landmark_name, mid_point)
        velocity_past = self.get_velocity(landmark_name, window_size - mid_point)
        
        if velocity_now is None or velocity_past is None:
            return None
        
        # Calculate acceleration (velocity change / time)
        time_delta = self.dt * mid_point
        acceleration = (velocity_now - velocity_past) / time_delta
        
        return acceleration
    
    def is_oscillating(self, landmark_name, threshold=0.05, window_size=15, min_peaks=2):
        """
        Detect if a landmark is oscillating (moving back and forth repeatedly).
        
        Args:
            landmark_name: Name of the landmark
            threshold: Minimum movement threshold to count as motion
            window_size: Number of frames to analyze
            min_peaks: Minimum number of direction changes to count as oscillation
        
        Returns:
            bool: True if oscillating, False otherwise
        """
        if len(self.landmark_history) < window_size:
            return False
        
        # Get position history
        positions = []
        for i in range(min(window_size, len(self.landmark_history))):
            pos = self.get_landmark_position(landmark_name, i)
            if pos is not None:
                positions.append(pos)
        
        if len(positions) < window_size // 2:
            return False
        
        # Analyze one dimension (typically y for up/down, x for left/right)
        # Using y-axis for most gestures
        y_positions = [pos[1] for pos in positions]
        
        # Find peaks and valleys (direction changes)
        direction_changes = 0
        for i in range(1, len(y_positions) - 1):
            if abs(y_positions[i] - y_positions[i-1]) > threshold:
                # Check if direction changed
                prev_direction = np.sign(y_positions[i] - y_positions[i-1])
                next_direction = np.sign(y_positions[i+1] - y_positions[i])
                
                if prev_direction != next_direction and prev_direction != 0:
                    direction_changes += 1
        
        return direction_changes >= min_peaks
    
    def get_relative_position(self, landmark_name, reference_landmark='nose'):
        """
        Get position of a landmark relative to a reference landmark.
        Useful for scale-invariant gesture detection.
        
        Args:
            landmark_name: Name of the landmark to measure
            reference_landmark: Name of the reference landmark (default: 'nose')
        
        Returns:
            numpy array [dx, dy, dz] or None
        """
        target_pos = self.get_landmark_position(landmark_name)
        reference_pos = self.get_landmark_position(reference_landmark)
        
        if target_pos is None or reference_pos is None:
            return None
        
        return target_pos - reference_pos
    
    def is_action_active(self, action_name):
        """Check if an action is currently active (being held)."""
        return action_name in self.active_actions
    
    def activate_action(self, action_name):
        """Mark an action as active."""
        self.active_actions.add(action_name)
    
    def deactivate_action(self, action_name):
        """Mark an action as inactive."""
        self.active_actions.discard(action_name)
    
    def get_landmark_distance(self, landmark1, landmark2):
        """
        Calculate distance between two landmarks.
        
        Args:
            landmark1: Name of first landmark
            landmark2: Name of second landmark
        
        Returns:
            float: Distance between landmarks, or None
        """
        pos1 = self.get_landmark_position(landmark1)
        pos2 = self.get_landmark_position(landmark2)
        
        if pos1 is None or pos2 is None:
            return None
        
        return np.linalg.norm(pos1 - pos2)
    
    def clear_history(self):
        """Clear all history (useful for reset/calibration)."""
        self.landmark_history.clear()
        self.gesture_history.clear()
        self.timestamps.clear()
        self.active_actions.clear()