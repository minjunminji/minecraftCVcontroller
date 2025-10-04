"""
MediaPipe Holistic pose tracking wrapper.
Handles landmark extraction from webcam frames.
"""

import cv2
import mediapipe as mp
import numpy as np

# Initialize MediaPipe Holistic once globally for efficiency
mp_holistic = mp.solutions.holistic
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands

# Global holistic instance
holistic = mp_holistic.Holistic(
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    model_complexity=1  # 0=lite, 1=full, 2=heavy
)


def get_landmarks(frame):
    """
    Extract body and hand landmarks from a frame using MediaPipe Holistic.
    
    Args:
        frame: BGR image from OpenCV (numpy array)
    
    Returns:
        dict: Dictionary containing normalized (x, y, z) coordinates for landmarks:
            - 'pose': list of 33 pose landmarks
            - 'left_hand': list of 21 left hand landmarks
            - 'right_hand': list of 21 right hand landmarks
            - 'face': list of 468 face landmarks
        Returns None if no person is detected.
    """
    # Convert BGR to RGB (MediaPipe expects RGB)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # Process the frame with MediaPipe Holistic
    results = holistic.process(frame_rgb)
    
    # Check if pose landmarks were detected
    if not results.pose_landmarks:
        return None
    
    # Extract landmarks into a structured dictionary
    landmarks_dict = {
        'pose': None,
        'left_hand': None,
        'right_hand': None,
        'face': None,
        'raw_results': results  # Store raw results for drawing
    }
    
    # Extract pose landmarks (33 landmarks)
    if results.pose_landmarks:
        pose_landmarks = []
        for idx, lm in enumerate(results.pose_landmarks.landmark):
            try:
                landmark_enum = mp_pose.PoseLandmark(idx)
                name = landmark_enum.name.lower()
            except ValueError:
                name = f"pose_{idx}"
            pose_landmarks.append({
                'name': name,
                'x': lm.x,
                'y': lm.y,
                'z': lm.z,
                'visibility': lm.visibility
            })
        landmarks_dict['pose'] = pose_landmarks
    
    # Extract left hand landmarks (21 landmarks)
    if results.left_hand_landmarks:
        left_hand_landmarks = []
        for idx, lm in enumerate(results.left_hand_landmarks.landmark):
            try:
                landmark_enum = mp_hands.HandLandmark(idx)
                name = landmark_enum.name.lower()
            except ValueError:
                name = f"hand_{idx}"
            left_hand_landmarks.append({
                'name': f"left_{name}",
                'x': lm.x,
                'y': lm.y,
                'z': lm.z
            })
        landmarks_dict['left_hand'] = left_hand_landmarks
    
    # Extract right hand landmarks (21 landmarks)
    if results.right_hand_landmarks:
        right_hand_landmarks = []
        for idx, lm in enumerate(results.right_hand_landmarks.landmark):
            try:
                landmark_enum = mp_hands.HandLandmark(idx)
                name = landmark_enum.name.lower()
            except ValueError:
                name = f"hand_{idx}"
            right_hand_landmarks.append({
                'name': f"right_{name}",
                'x': lm.x,
                'y': lm.y,
                'z': lm.z
            })
        landmarks_dict['right_hand'] = right_hand_landmarks
    
    # Extract face landmarks (468 landmarks)
    if results.face_landmarks:
        landmarks_dict['face'] = [
            {'x': lm.x, 'y': lm.y, 'z': lm.z}
            for lm in results.face_landmarks.landmark
        ]
    
    return landmarks_dict


def draw_landmarks(frame, landmarks_dict):
    """
    Draw landmarks on the frame for visual debugging.
    
    Args:
        frame: BGR image from OpenCV (numpy array)
        landmarks_dict: Dictionary returned by get_landmarks()
    
    Returns:
        frame: Annotated frame with landmarks drawn
    """
    if landmarks_dict is None or 'raw_results' not in landmarks_dict:
        return frame
    
    results = landmarks_dict['raw_results']
    
    # Draw pose landmarks
    if results.pose_landmarks:
        mp_drawing.draw_landmarks(
            frame,
            results.pose_landmarks,
            mp_holistic.POSE_CONNECTIONS,
            landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
        )
    
    # Draw left hand landmarks
    if results.left_hand_landmarks:
        mp_drawing.draw_landmarks(
            frame,
            results.left_hand_landmarks,
            mp_holistic.HAND_CONNECTIONS,
            landmark_drawing_spec=mp_drawing_styles.get_default_hand_landmarks_style()
        )
    
    # Draw right hand landmarks
    if results.right_hand_landmarks:
        mp_drawing.draw_landmarks(
            frame,
            results.right_hand_landmarks,
            mp_holistic.HAND_CONNECTIONS,
            landmark_drawing_spec=mp_drawing_styles.get_default_hand_landmarks_style()
        )
    
    # Draw face landmarks (optional - can be noisy)
    if results.face_landmarks:
        mp_drawing.draw_landmarks(
            frame,
            results.face_landmarks,
            mp_holistic.FACEMESH_CONTOURS,
            landmark_drawing_spec=None,
            connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_contours_style()
        )
    
    return frame


def cleanup():
    """
    Clean up MediaPipe resources.
    Call this when shutting down the application.
    """
    holistic.close()

