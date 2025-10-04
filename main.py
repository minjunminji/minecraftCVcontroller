"""
Main control loop for webcam input and landmark detection
"""

import cv2
import sys
from cv.pose_tracking import get_landmarks, draw_landmarks, cleanup


def main():
    """
    Main loop: capture webcam frames, extract landmarks, and display results.
    Press 'q' to quit
    """
    # Open webcam (0 = default camera)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        sys.exit(1)
    
    # Set camera resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    print("Webcam started")
    print("Press 'q' to quit")
    
    try:
        while True:
            # Capture frame from webcam
            ret, frame = cap.read()
            
            if not ret:
                print("Error: Failed to capture frame.")
                break
            
            # Flip frame horizontally for mirror effect
            frame = cv2.flip(frame, 1)
            
            # Get landmarks from the frame
            landmarks_dict = get_landmarks(frame)
            
            # Draw landmarks on the frame for debugging
            if landmarks_dict is not None:
                frame = draw_landmarks(frame, landmarks_dict)
                
                # Display landmark detection status
                status_text = "Tracking: "
                if landmarks_dict['pose']:
                    status_text += "Body "
                if landmarks_dict['left_hand']:
                    status_text += "L-Hand "
                if landmarks_dict['right_hand']:
                    status_text += "R-Hand "
                
                cv2.putText(
                    frame,
                    status_text,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )
            else:
                # No person detected
                cv2.putText(
                    frame,
                    "No person detected",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2
                )
            
            # Display FPS
            # Note: for accurate FPS we'd need to track time between frames
            cv2.putText(
                frame,
                "MineMotion - Press 'q' to quit",
                (10, frame.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1
            )
            
            # Show the frame
            cv2.imshow('MineMotion - Landmark Detection', frame)
            
            # Check for q key to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Quitting...")
                break
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        # Clean up resources
        cap.release()
        cv2.destroyAllWindows()
        cleanup()
        print("Cleaned up resources. Goodbye!")


if __name__ == "__main__":
    main()

