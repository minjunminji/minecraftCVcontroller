"""
Main control loop for webcam input and landmark detection with gesture recognition
"""

import cv2
import sys
import time
from cv.pose_tracking import get_landmarks, draw_landmarks, cleanup

# Import the new architecture components
from utils.state_manager import GestureStateManager
from utils.action_coordinator import ActionCoordinator
from controls.keyboard_mouse import MinecraftController

# Import gesture detectors
from gestures.shield import ShieldDetector
from gestures.mining import MiningDetector
from gestures.placing import PlacingDetector
from gestures.movement import MovementDetector
from gestures.inventory import InventoryDetector
from gestures.menuclose import MenuCloseDetector
from gestures.cursor_control import CursorControlDetector, is_in_menu_mode
from gestures.attack import AttackDetector
from gestures.looking import LookingDetector
from gestures.hand_scroll import HandScrollDetector


def main():
    """
    Main gameplay loop with gesture detection and action coordination.
    
    Architecture:
    1. Capture webcam frame
    2. Extract MediaPipe landmarks
    3. Update state manager with landmark history
    4. Run all gesture detectors
    5. Coordinate and execute game actions
    6. Display debug visualization
    """
    
    print("=" * 60)
    print("MineMotion - Gesture-Controlled Minecraft")
    print("=" * 60)
    print("\nInitializing components...")
    
    # Initialize webcam
    # webcam 0 = iphone continuity camera
    # webcam 1 = mac camera
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        sys.exit(1)
    
    # Set camera resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    # Initialize state manager for temporal tracking
    state_manager = GestureStateManager(history_size=30, fps=30)
    print("✓ State Manager initialized")
    
    # Initialize game controller
    try:
        game_controller = MinecraftController()
        print("✓ Game Controller initialized")
    except ImportError as e:
        print(f"✗ Error initializing controller: {e}")
        print("  Please install required packages: pip install pynput")
        cap.release()
        sys.exit(1)
    
    # Initialize action coordinator
    action_coordinator = ActionCoordinator(game_controller)
    print("✓ Action Coordinator initialized")
    
    # Initialize gesture detectors
    gesture_detectors = {
        'shield': ShieldDetector(),         # Left hand: shield block
        'inventory': InventoryDetector(),   # Left hand: inventory open
        'menuclose': MenuCloseDetector(),   # Left hand: menu close (opposite of inventory)
        'cursor_control': CursorControlDetector(),  # Right hand: menu cursor control
        'attack': AttackDetector(),         # Right hand: single left clicks (attacking)
        'mining': MiningDetector(),         # Right hand: mining / continuous attacking
        'placing': PlacingDetector(),       # Right hand: placing / using items
        'movement': MovementDetector(),     # Locomotion
        'looking': LookingDetector(),       # Head rotation: mouse control (looking around)
        'hand_scroll': HandScrollDetector(), # Left hand rotation: scroll wheel
    }
    enabled_count = sum(1 for detector in gesture_detectors.values() if detector.is_enabled())
    print(f"✓ {enabled_count} gesture detector(s) enabled / {len(gesture_detectors)} total initialized")
    
    print("\n" + "=" * 60)
    print("System ready! Starting main loop...")
    print("=" * 60)
    print("\nControls:")
    print("  'q' - Quit application")
    print("  'r' - Toggle gestures ON/OFF")
    print("  'd' - Toggle debug display")
    # Menu mode is auto-detected (cursor free/locked) or via left-hand swipe
    print("  'c' - Calibrate neutral pose")
    print("\nWaiting for person detection...")
    
    # Main loop state
    debug_display = True
    calibrated = False # TODO: implement calibration
    frame_count = 0
    fps_start_time = time.time()
    current_fps = 0
    
    # Track OS cursor free/locked to trigger menu entry automatically
    cursor_free_prev = None
    
    # Global gesture enable/disable toggle
    gestures_enabled = False  # Toggle with 'r' key
    
    # Error tracking
    last_error_time = None
    error_message = None
    
    # Create window and configure for always-on-top display
    window_name = 'MineMotion - Gesture Control'
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)
    cv2.moveWindow(window_name, 0, 0)  # Position at top-left corner
    
    try:
        while True:
            # Capture frame from webcam
            ret, frame = cap.read()
            
            if not ret:
                print("Error: Failed to capture frame.")
                break
            
            # === STEP 1: Get landmarks from MediaPipe ===
            landmarks_dict = get_landmarks(frame)
            
            # === STEP 2: Update state manager with new landmark data ===
            state_manager.update(landmarks_dict)
            
            # === STEP 3: Run gesture detection ===
            gesture_results = {}
            if landmarks_dict is not None and gestures_enabled:
                # Detect OS cursor free/locked and inject mode switch to enter menu
                try:
                    cursor_free = is_in_menu_mode()
                except Exception:
                    cursor_free = None
                if cursor_free is not None and cursor_free_prev is not None:
                    if (not cursor_free_prev) and cursor_free:
                        # Cursor just became free: enter menu without pressing E
                        gesture_results['mode_switch'] = 'cursor_released'
                cursor_free_prev = cursor_free if cursor_free is not None else cursor_free_prev
                # Run all enabled gesture detectors
                for name, detector in gesture_detectors.items():
                    # Pass menu mode flag to cursor_control detector
                    if name == 'cursor_control':
                        # Auto-detect based on OS cursor state inside detector
                        result = detector.detect(state_manager, force_menu_mode=None)
                    else:
                        result = detector.detect(state_manager)
                    if result is not None:
                        gesture_results[name] = result
                
                # Map left hand gestures (priority order)
                left_hand_priority = ['menuclose', 'inventory', 'shield']
                for gesture_name in left_hand_priority:
                    if gesture_name in gesture_results:
                        gesture_payload = gesture_results[gesture_name]
                        if isinstance(gesture_payload, dict):
                            gesture_results['left_hand'] = {**gesture_payload, 'source': gesture_name}
                        else:
                            gesture_results['left_hand'] = {'action': gesture_payload, 'source': gesture_name}
                        break
                
                # Map right hand gestures (priority order)
                right_hand_priority = ['placing', 'attack', 'mining']
                for gesture_name in right_hand_priority:
                    if gesture_name in gesture_results:
                        gesture_payload = gesture_results[gesture_name]
                        if isinstance(gesture_payload, dict):
                            gesture_results['right_hand'] = {**gesture_payload, 'source': gesture_name}
                        else:
                            gesture_results['right_hand'] = {'action': gesture_payload, 'source': gesture_name}
                        break
                
                # Map looking gesture to head_look for action coordinator
                if 'looking' in gesture_results:
                    gesture_results['head_look'] = gesture_results['looking']
                
                # === STEP 4: Execute actions via coordinator ===
                try:
                    action_coordinator.execute(gesture_results, state_manager)
                    # Clear error if action succeeded
                    if error_message is not None and (last_error_time is None or time.time() - last_error_time > 3):
                        error_message = None
                except Exception as e:
                    current_time = time.time()
                    error_message = f"Controller Error: {str(e)[:50]}"
                    last_error_time = current_time
                    print(f"\n⚠ ERROR in action execution: {e}")
                    import traceback
                    traceback.print_exc()
                    # Try to recover by resetting
                    try:
                        action_coordinator.reset()
                        print("✓ Action coordinator reset after error")
                    except:
                        pass
            
            # === STEP 5: Prepare frame for display ===
            frame_display = frame.copy()
            overlay_texts = []
            
            if debug_display:
                if landmarks_dict is not None:
                    frame_display = draw_landmarks(frame_display, landmarks_dict)
                    
                    # Get action coordinator status
                    action_status = action_coordinator.get_status()
                    
                    # Prepare textual overlays
                    left_x = 10
                    y_pos = 30
                    
                    # Show current mode prominently
                    mode_display = action_status.get('mode', 'unknown').upper()
                    mode_display_color = (0, 255, 255) if mode_display == 'MENU' else (255, 255, 255)
                    overlay_texts.append({
                        'text': f"MODE: {mode_display}",
                        'position': (left_x, y_pos),
                        'scale': 0.6,
                        'color': mode_display_color,
                        'thickness': 2,
                        'background': (0, 0, 0),
                        'background_padding': 5
                    })
                    y_pos += 35
                    
                    # Show exit hint when in menu mode
                    if mode_display == 'MENU':
                        overlay_texts.append({
                            'text': "→ Swipe left hand RIGHT-TO-LEFT to exit menu",
                            'position': (left_x, y_pos),
                            'scale': 0.45,
                            'color': (0, 255, 255),
                            'thickness': 1
                        })
                        y_pos += 25
                    
                    overlay_texts.append({
                        'text': "GESTURES:",
                        'position': (left_x, y_pos),
                        'scale': 0.6,
                        'color': (255, 255, 255),
                        'thickness': 2
                    })
                    y_pos += 30

                    # Show cursor coordinates from cursor_control (if available)
                    cursor_result = gesture_results.get('cursor_control')
                    if isinstance(cursor_result, dict):
                        cx = cursor_result.get('x')
                        cy = cursor_result.get('y')
                        cursor_frozen = cursor_result.get('cursor_frozen', False)
                        
                        if cx is not None and cy is not None:
                            # Color code cursor position based on freeze state
                            cursor_color = (255, 128, 0) if cursor_frozen else (0, 255, 255)
                            cursor_text = f"Cursor: ({int(cx)}, {int(cy)})"
                            if cursor_frozen:
                                cursor_text += " [FROZEN]"
                            overlay_texts.append({
                                'text': cursor_text,
                                'position': (left_x, y_pos),
                                'scale': 0.5,
                                'color': cursor_color,
                                'thickness': 1
                            })
                            y_pos += 25
                        
                        # Show pinch distance
                        pinch_dist = cursor_result.get('pinch_distance')
                        if pinch_dist is not None:
                            # Color code based on thresholds (0.06 = pinch trigger, 0.10 = freeze)
                            if pinch_dist <= 0.06:
                                dist_color = (0, 255, 0)  # Green = click zone
                            elif pinch_dist <= 0.10:
                                dist_color = (255, 128, 0)  # Orange = freeze zone
                            else:
                                dist_color = (255, 255, 255)  # White = normal
                            
                            overlay_texts.append({
                                'text': f"Pinch: {pinch_dist:.4f} (click: 0.06, freeze: 0.10)",
                                'position': (left_x, y_pos),
                                'scale': 0.5,
                                'color': dist_color,
                                'thickness': 1
                            })
                            y_pos += 25
                    
                    # Show looking gesture debug info (if available)
                    looking_result = gesture_results.get('looking')
                    if isinstance(looking_result, dict):
                        left_x_dist = looking_result.get('left_x_distance')
                        right_x_dist = looking_result.get('right_x_distance')
                        left_y_dist = looking_result.get('left_y_distance')
                        right_y_dist = looking_result.get('right_y_distance')
                        avg_y_dist = looking_result.get('avg_y_distance')
                        x_ratio = looking_result.get('x_ratio')
                        
                        # Get detector settings for display
                        looking_detector = gesture_detectors.get('looking')
                        if looking_detector:
                            tilt_mult = looking_detector.tilt_multiplier
                            deadzone = looking_detector.deadzone
                            y_thresh = looking_detector.y_threshold
                            y_deadzone = looking_detector.y_deadzone
                            
                            # Color code based on whether tilting is active
                            dx = looking_result.get('dx', 0)
                            dy = looking_result.get('dy', 0)
                            if dx != 0 or dy != 0:
                                looking_color = (0, 255, 0)  # Green when active
                            else:
                                looking_color = (200, 200, 200)  # Gray when neutral
                            
                            # Show horizontal (left/right) info
                            overlay_texts.append({
                                'text': f"Looking L/R: X_L={left_x_dist:.4f} X_R={right_x_dist:.4f}",
                                'position': (left_x, y_pos),
                                'scale': 0.5,
                                'color': looking_color,
                                'thickness': 1
                            })
                            y_pos += 25
                            
                            overlay_texts.append({
                                'text': f"  X Ratio: {x_ratio:.3f} (threshold: {tilt_mult:.2f}, deadzone: {deadzone:.2f})",
                                'position': (left_x, y_pos),
                                'scale': 0.5,
                                'color': looking_color,
                                'thickness': 1
                            })
                            y_pos += 25
                            
                            # Show vertical (up/down) info
                            overlay_texts.append({
                                'text': f"Looking U/D: Avg_Y={avg_y_dist:.4f} (- = up, + = down)",
                                'position': (left_x, y_pos),
                                'scale': 0.5,
                                'color': looking_color,
                                'thickness': 1
                            })
                            y_pos += 25
                            
                            overlay_texts.append({
                                'text': f"  Up: Y < -{y_thresh:.3f}, Down: Y > 0, Deadzone={y_deadzone:.3f}",
                                'position': (left_x, y_pos),
                                'scale': 0.5,
                                'color': looking_color,
                                'thickness': 1
                            })
                            y_pos += 25
                    
                    if gesture_results:
                        for gesture_name, gesture_data in gesture_results.items():
                            # Skip the mapped results (left_hand, right_hand, looking, head_look)
                            # looking is displayed separately above with detailed debug info
                            if gesture_name in ['left_hand', 'right_hand', 'looking', 'head_look']:
                                continue
                            
                            # Extract action info
                            if isinstance(gesture_data, dict):
                                action = gesture_data.get('action', 'detected')
                                action_display = action.replace('_', ' ').title()
                                
                                text = f"{gesture_name}: {action_display}"
                                # Highlight menu close gesture in cyan when in menu mode
                                if gesture_name == 'menuclose' and action_status.get('mode') == 'menu':
                                    color = (0, 255, 255)  # Cyan - stands out
                                elif 'shield' in gesture_name:
                                    color = (128, 128, 255)
                                else:
                                    color = (255, 255, 255)
                                
                                overlay_texts.append({
                                    'text': text,
                                    'position': (left_x, y_pos),
                                    'scale': 0.5,
                                    'color': color,
                                    'thickness': 1
                                })
                                y_pos += 25
                    else:
                        overlay_texts.append({
                            'text': "None",
                            'position': (left_x, y_pos),
                            'scale': 0.5,
                            'color': (150, 150, 150),
                            'thickness': 1
                        })
                        y_pos += 25
                    
                    y_pos += 10
                    
                    overlay_texts.append({
                        'text': "ACTIONS:",
                        'position': (left_x, y_pos),
                        'scale': 0.6,
                        'color': (255, 255, 255),
                        'thickness': 2
                    })
                    y_pos += 30
                    
                    # Show what's actually being pressed (held)
                    pressed_keys = action_status.get('pressed_keys', [])
                    pressed_buttons = action_status.get('pressed_buttons', [])
                    recent_actions = action_status.get('recent_actions', [])

                    if pressed_keys:
                        keys_text = f"Held Keys: {', '.join([str(k).upper() for k in pressed_keys])}"
                        overlay_texts.append({
                            'text': keys_text,
                            'position': (left_x, y_pos),
                            'scale': 0.5,
                            'color': (0, 255, 0),
                            'thickness': 1
                        })
                        y_pos += 25

                    if pressed_buttons:
                        buttons_text = f"Held Mouse: {', '.join([b.upper() for b in pressed_buttons])}"
                        overlay_texts.append({
                            'text': buttons_text,
                            'position': (left_x, y_pos),
                            'scale': 0.5,
                            'color': (0, 255, 255),
                            'thickness': 1
                        })
                        y_pos += 25

                    # Show recent one-time actions (clicks, taps, scrolls)
                    if recent_actions:
                        for action_type, action_name in recent_actions:
                            action_text = f"{action_type.capitalize()}: {action_name}"
                            # Different colors for different action types
                            if action_type == 'click':
                                color = (255, 128, 0)  # Orange for clicks
                            elif action_type == 'tap':
                                color = (128, 255, 128)  # Light green for taps
                            elif action_type == 'scroll':
                                color = (255, 255, 128)  # Yellow for scrolls
                            else:
                                color = (200, 200, 200)  # Gray for others
                            
                            overlay_texts.append({
                                'text': action_text,
                                'position': (left_x, y_pos),
                                'scale': 0.5,
                                'color': color,
                                'thickness': 1
                            })
                            y_pos += 25

                    if not pressed_keys and not pressed_buttons and not recent_actions:
                        overlay_texts.append({
                            'text': "None",
                            'position': (left_x, y_pos),
                            'scale': 0.5,
                            'color': (150, 150, 150),
                            'thickness': 1
                        })
                        y_pos += 25
                else:
                    # No person detected
                    overlay_texts.append({
                        'text': "No person detected",
                        'position': (10, 30),
                        'scale': 0.7,
                        'color': (0, 0, 255),
                        'thickness': 2
                    })
                
                # Calculate FPS
                frame_count += 1
                if frame_count >= 10:
                    elapsed = time.time() - fps_start_time
                    current_fps = frame_count / elapsed
                    frame_count = 0
                    fps_start_time = time.time()
                
                frame_height = frame_display.shape[0]
                
                # Show error message if present
                if error_message is not None:
                    overlay_texts.append({
                        'text': f"⚠ {error_message}",
                        'position': (10, frame_height - 130),
                        'scale': 0.6,
                        'color': (0, 165, 255),  # Orange
                        'thickness': 2,
                        'background': (0, 0, 0),
                        'background_padding': 8
                    })
                
                # Show gesture status (large, prominent indicator)
                gesture_text = f"GESTURES: {'ENABLED' if gestures_enabled else 'DISABLED'}"
                gesture_color = (0, 255, 0) if gestures_enabled else (0, 0, 255)
                overlay_texts.append({
                    'text': gesture_text,
                    'position': (10, frame_height - 100),
                    'scale': 0.6,
                    'color': gesture_color,
                    'thickness': 2,
                    'background': (0, 0, 0),
                    'background_padding': 8
                })
                
                # Show OS cursor detection (free vs locked)
                try:
                    cursor_free = is_in_menu_mode()
                except Exception:
                    cursor_free = None
                if cursor_free is not None:
                    cursor_text = f"Cursor: {'FREE' if cursor_free else 'LOCKED'}"
                    cursor_color = (0, 255, 0) if cursor_free else (128, 128, 128)
                    overlay_texts.append({
                        'text': cursor_text,
                        'position': (10, frame_height - 70),
                        'scale': 0.5,
                        'color': cursor_color,
                        'thickness': 2
                    })
                
                overlay_texts.append({
                    'text': f"FPS: {current_fps:.1f}",
                    'position': (10, frame_height - 40),
                    'scale': 0.5,
                    'color': (255, 255, 255),
                    'thickness': 1
                })
                
                overlay_texts.append({
                    'text': "MineMotion - Press 'q' to quit, 'd' for debug, 'r' to toggle gestures",
                    'position': (10, frame_height - 10),
                    'scale': 0.4,
                    'color': (255, 255, 255),
                    'thickness': 1
                })
            
            # Mirror the frame for preview only
            frame_display = cv2.flip(frame_display, 1)
            frame_height, frame_width = frame_display.shape[:2]
            
            # Draw textual overlays on mirrored frame
            font_face = cv2.FONT_HERSHEY_SIMPLEX
            for overlay in overlay_texts:
                text = overlay['text']
                position = overlay['position']
                font_scale = overlay['scale']
                color = overlay['color']
                thickness = overlay['thickness']
                background_color = overlay.get('background', (0, 0, 0))
                padding = overlay.get('background_padding', 6)
                
                if background_color is not None:
                    text_size, baseline = cv2.getTextSize(
                        text,
                        font_face,
                        font_scale,
                        thickness
                    )
                    text_width, text_height = text_size
                    x, y = position
                    top_left_x = max(x - padding, 0)
                    top_left_y = max(y - text_height - padding, 0)
                    bottom_right_x = min(x + text_width + padding, frame_width)
                    bottom_right_y = min(y + baseline + padding, frame_height)
                    cv2.rectangle(
                        frame_display,
                        (top_left_x, top_left_y),
                        (bottom_right_x, bottom_right_y),
                        background_color,
                        -1
                    )
                
                cv2.putText(
                    frame_display,
                    text,
                    position,
                    font_face,
                    font_scale,
                    color,
                    thickness
                )
            
            # Show the frame
            cv2.imshow(window_name, frame_display)
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("\nQuitting...")
                break
            elif key == ord('r'):
                gestures_enabled = not gestures_enabled
                if not gestures_enabled:
                    # Release all active controls when disabling gestures
                    action_coordinator.reset()
                    # Clear error state
                    error_message = None
                    last_error_time = None
                print(f"\nGestures: {'ENABLED' if gestures_enabled else 'DISABLED'}")
            elif key == ord('d'):
                debug_display = not debug_display
                print(f"\nDebug display: {'ON' if debug_display else 'OFF'}")
            elif key == ord('c'):
                if landmarks_dict is not None:
                    state_manager.set_calibration_baseline(landmarks_dict)
                    calibrated = True
                    print("\n✓ Calibration complete! Neutral pose captured.")
                else:
                    print("\n✗ Cannot calibrate - no person detected")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    
    except Exception as e:
        print(f"\n\nError in main loop: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # === Cleanup ===
        print("\nCleaning up...")
        
        # Release all game controls
        action_coordinator.reset()
        print("✓ Released all game controls")
        
        # Release webcam
        cap.release()
        cv2.destroyAllWindows()
        print("✓ Released webcam")
        
        # Cleanup MediaPipe
        cleanup()
        print("✓ MediaPipe cleanup complete")
        
        print("\n" + "=" * 60)
        print("MineMotion shutdown complete. Goodbye!")
        print("=" * 60)


if __name__ == "__main__":
    main()
