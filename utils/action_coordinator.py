"""
Action Coordinator - Coordinates gesture detection results with game controls
"""

from controls.keyboard_mouse import MinecraftController

# Configuration constants
HEAD_LOOK_SENSITIVITY = 5.0  # Adjust as needed
HEAD_LOOK_DEADZONE = 0.01    # Minimum movement threshold

class ActionCoordinator:
    """
    Coordinates gesture detection results and executes appropriate game actions.
    Manages state transitions and prevents conflicting actions.
    """
    
    def __init__(self, controller=None):
        """
        Initialize the action coordinator.
        
        Args:
            controller: MinecraftController instance (creates new one if None)
        """
        self.controller = controller or MinecraftController()
        
        # Track current action states
        self.active_movement = None  # Current movement direction (w/a/s/d)
        self.is_jumping = False
        self.is_sprinting = False
        self.is_sneaking = False
        
        # Hand action states
        self.left_hand_action = None   # 'shield', 'menu', None
        self.right_hand_action = None  # 'mining', 'placing', 'using', 'attack', None
        
        # Mode tracking
        self.current_mode = 'gameplay'  # 'gameplay', 'menu', 'inventory'
        
        # Action history for debouncing
        self.last_action_time = {}
    
    def execute(self, gesture_results, state_manager):
        """
        Execute actions based on gesture detection results.
        
        Args:
            gesture_results: Dictionary of gesture detection results
            state_manager: GestureStateManager instance
        """
        # Mode-specific execution
        if self.current_mode == 'gameplay':
            self._execute_gameplay_actions(gesture_results, state_manager)
        elif self.current_mode == 'menu':
            self._execute_menu_actions(gesture_results, state_manager)
    
    def _execute_gameplay_actions(self, gesture_results, state_manager):
        """
        Execute actions during gameplay mode.
        
        Note: This should only be called when in gameplay mode.
        """
        
        # 1. Handle movement actions
        self._handle_movement(gesture_results)
        
        # 2. Handle jumping
        self._handle_jumping(gesture_results)
        
        # 3. Handle left hand actions (mining, attacking, shield, inventory)
        self._handle_left_hand_actions(gesture_results)
        
        # 4. Handle right hand actions (placing, using items, attacking)
        self._handle_right_hand_actions(gesture_results)
        
        # 5. Handle head look (mouse movement)
        self._handle_head_look(gesture_results)
        
        # 6. Handle mode switches
        self._handle_mode_switches(gesture_results)
    
    def _handle_movement(self, gesture_results):
        """
        Handle movement actions (W/A/S/D).
        Follows the movement rules from the diagram.
        """
        movement = gesture_results.get('movement')
        
        if movement is None:
            # Stop all movement
            if self.active_movement:
                self.controller.stop_moving()
                self.active_movement = None
            return
        
        is_walking = movement.get('is_walking', False)
        left_thumb_back = movement.get('left_thumb_back', False)
        torso_lean = movement.get('torso_lean')
        
        new_movement = None
        
        # Determine movement direction
        if torso_lean == 'left':
            new_movement = 'a'  # Strafe left
        elif torso_lean == 'right':
            new_movement = 'd'  # Strafe right
        elif left_thumb_back:
            new_movement = 's'  # Backward
        else:
            new_movement = 'w'  # Forward
        
        # Update movement if changed
        if new_movement != self.active_movement:
            self.controller.stop_moving()
            if new_movement == 'w':
                self.controller.move_forward()
            elif new_movement == 's':
                self.controller.move_backward()
            elif new_movement == 'a':
                self.controller.move_left()
            elif new_movement == 'd':
                self.controller.move_right()
            self.active_movement = new_movement
    
    def _handle_jumping(self, gesture_results):
        """Handle jumping action."""
        jump_result = gesture_results.get('jumping')
        
        if jump_result == 'jump' and not self.is_jumping:
            self.controller.jump()
            self.is_jumping = True
        elif jump_result != 'jump':
            self.is_jumping = False
    
    def _handle_left_hand_actions(self, gesture_results):
        """
        Handle left hand actions: shield, inventory, swipe in and out
        
        Note: This is only called during gameplay mode, not menu mode
        """
        left_hand = gesture_results.get('left_hand')
        
        if left_hand is None:
            # Release any active left hand actions
            if self.left_hand_action == 'shield':
                self.controller.release_right_click()
            self.left_hand_action = None
            return
        
        action_type = left_hand.get('action')
        
        # Inventory gesture - switch to menu mode
        if action_type == 'inventory_open':
            if self.current_mode != 'menu':
                print(f"[ACTION COORDINATOR] Inventory gesture detected, entering menu mode")
                self._enter_menu_mode(open_inventory=True)
            return
        
        # Menu close gesture - only works if we're somehow stuck in menu mode
        # (Normal menu exit is handled in _execute_menu_actions)
        if action_type == 'menu_close':
            if self.current_mode == 'menu':
                print(f"[ACTION COORDINATOR] Menu close detected in gameplay handler")
                self._exit_menu_mode()
            return
        
        # Menu navigation gestures
        if action_type == 'menu_swipe_right':
            if self.current_mode != 'menu':
                self._enter_menu_mode(open_inventory=True)
            return
        
        if action_type == 'menu_swipe_left':
            self._exit_menu_mode()
            return
        
        # Shield gesture
        if action_type == 'shield_start':
            if self.left_hand_action != 'shield':
                self.controller.hold_right_click()
                self.left_hand_action = 'shield'
        
        elif action_type == 'shield_hold':
            # Continue holding shield (maintain current state)
            if self.left_hand_action != 'shield':
                self.controller.hold_right_click()
                self.left_hand_action = 'shield'
                
        elif action_type == 'shield_stop':
            if self.left_hand_action == 'shield':
                self.controller.release_right_click()
                self.left_hand_action = None
    
    def _handle_right_hand_actions(self, gesture_results):
        """
        Handle right hand actions: mining, attacking, placing
        """
        right_hand = gesture_results.get('right_hand')
        
        if right_hand is None:
            if self.right_hand_action == 'mining':
                self.controller.release_left_click()
            elif self.right_hand_action == 'placing':
                self.controller.release_right_click()
            self.right_hand_action = None
            return
        
        action_type = right_hand.get('action')
        
        # Attack gesture (single left click)
        if action_type == 'attack_click':
            self.controller.single_left_click()
            self.right_hand_action = 'attack'
        
        # Mining gestures
        elif action_type == 'mining_click':
            self.controller.single_left_click()
            self.right_hand_action = 'attack'
        
        elif action_type == 'mining_start_hold':
            if self.right_hand_action != 'mining':
                self.controller.hold_left_click()
            self.right_hand_action = 'mining'
        
        elif action_type == 'mining_continue_hold':
            if self.right_hand_action != 'mining':
                self.controller.hold_left_click()
            self.right_hand_action = 'mining'
        
        elif action_type == 'mining_stop_hold':
            if self.right_hand_action == 'mining':
                self.controller.release_left_click()
            self.right_hand_action = None
        
        # Placing gesture
        elif action_type == 'place':
            if self.right_hand_action == 'mining':
                self.controller.release_left_click()
            self.controller.single_right_click()
            self.right_hand_action = 'placing'
        
        # Turning knob gesture (hotbar scroll)
        elif action_type == 'scroll_up':
            self.controller.scroll_hotbar(1)
        elif action_type == 'scroll_down':
            self.controller.scroll_hotbar(-1)
    
    def _handle_head_look(self, gesture_results):
        """Handle head tilt for mouse movement (camera control)."""
        head_look = gesture_results.get('head_look')
        
        if head_look:
            dx = head_look.get('dx', 0)
            dy = head_look.get('dy', 0)
            
            # Apply sensitivity scaling
            if abs(dx) > HEAD_LOOK_DEADZONE or abs(dy) > HEAD_LOOK_DEADZONE:
                self.controller.move_mouse(
                    int(dx * HEAD_LOOK_SENSITIVITY),
                    int(dy * HEAD_LOOK_SENSITIVITY)
                )
    
    def _handle_mode_switches(self, gesture_results):
        """Handle switching between gameplay and menu modes."""
        mode_switch = gesture_results.get('mode_switch')
        
        if mode_switch == 'enter_menu':
            self._enter_menu_mode(open_inventory=True)
        elif mode_switch == 'cursor_released':
            self._enter_menu_mode(open_inventory=False)
        elif mode_switch == 'cursor_locked':
            self._exit_menu_mode()
        elif mode_switch == 'exit_menu':
            self._exit_menu_mode()
    
    def _execute_menu_actions(self, gesture_results, state_manager):
        """
        Execute actions during menu mode.
        
        In menu mode, ONLY the following gestures are processed:
        - menu_close (left hand): Exit menu and return to gameplay
        - cursor_control (right hand): Navigate menus with hand position
        
        ALL other gestures (attack, mining, shield, placing, etc.) are IGNORED.
        """
        _ = state_manager  # Placeholder for future expansions
        
        # Safety check: Release any stuck actions from gameplay mode
        # This prevents left/right click from staying held when entering menu
        if self.right_hand_action in ['mining', 'attack', 'placing']:
            self.controller.release_left_click()
            self.controller.release_right_click()
            self.right_hand_action = None
        
        if self.left_hand_action == 'shield':
            self.controller.release_right_click()
            self.left_hand_action = None
        
        # ========== ONLY PROCESS MENU-SPECIFIC GESTURES ==========
        
        # 1. Check for menu exit gesture (highest priority)
        left_hand = gesture_results.get('left_hand')
        if left_hand:
            menu_hand_action = left_hand.get('action')
            menu_hand_source = left_hand.get('source', 'unknown')
            
            # ONLY process menu_close action in menu mode
            if menu_hand_action == 'menu_close':
                print(f"[ACTION COORDINATOR] Menu close gesture detected (source: {menu_hand_source})")
                self._exit_menu_mode()
                return
            
            # Legacy support for menu swipe (if it exists)
            if menu_hand_action == 'menu_swipe_left':
                print(f"[ACTION COORDINATOR] Menu swipe left detected, exiting menu")
                self._exit_menu_mode()
                return
            
            # All other left hand gestures are IGNORED in menu mode
            # (shield, inventory_open, etc. should not trigger)
        
        # 2. Handle cursor control for menu navigation (right hand)
        cursor_control = gesture_results.get('cursor_control')
        if cursor_control:
            action = cursor_control.get('action')
            
            if action == 'cursor_move':
                # Move cursor to absolute position
                x = cursor_control.get('x')
                y = cursor_control.get('y')
                if x is not None and y is not None:
                    self.controller.set_cursor_position(x, y)
                
                # Handle click if pinch detected
                if cursor_control.get('click'):
                    self.controller.click_mouse('left')
        
        # 3. Handle generic menu actions (if any)
        menu_action = gesture_results.get('menu_action')
        if menu_action == 'select':
            self.controller.click_mouse('left')
        elif menu_action == 'back':
            self._exit_menu_mode()
        
        # NOTE: All right hand gameplay gestures (attack, mining, placing)
        # are intentionally IGNORED in menu mode
    
    def _enter_menu_mode(self, open_inventory=True):
        """Switch to menu mode."""
        if self.current_mode == 'menu':
            return
        
        print(f"[ACTION COORDINATOR] Entering menu mode (open_inventory={open_inventory})")
        
        # Release ALL inputs before entering menu mode
        self.controller.release_all()
        
        if open_inventory:
            self.controller.open_inventory()
        
        self.current_mode = 'menu'
        self.active_movement = None
        self.left_hand_action = None
        self.right_hand_action = None
        self.is_jumping = False
        self.is_sprinting = False
        self.is_sneaking = False
    
    def _exit_menu_mode(self):
        """Send ESC to exit menus and return to gameplay mode."""
        was_in_menu = self.current_mode == 'menu'
        
        print("[ACTION COORDINATOR] Exiting menu mode")
        
        # Release all inputs before sending ESC (in case anything is stuck)
        self.controller.release_all()
        
        # Always send ESC to close any open UI
        self.controller.tap_key('esc')
        
        if was_in_menu:
            self.current_mode = 'gameplay'
            self.active_movement = None
            self.left_hand_action = None
            self.right_hand_action = None
            self.is_jumping = False
            self.is_sprinting = False
            self.is_sneaking = False
    
    def reset(self):
        """Reset all actions and release all inputs."""
        self.controller.release_all()
        self.active_movement = None
        self.is_jumping = False
        self.is_sprinting = False
        self.is_sneaking = False
        self.left_hand_action = None
        self.right_hand_action = None
        self.current_mode = 'gameplay'
    
    def get_status(self):
        """Get current action status (for debugging/display)."""
        return {
            'mode': self.current_mode,
            'movement': self.active_movement,
            'jumping': self.is_jumping,
            'sprinting': self.is_sprinting,
            'sneaking': self.is_sneaking,
            'left_hand': self.left_hand_action,
            'right_hand': self.right_hand_action,
            'pressed_keys': self.controller.get_pressed_keys(),
            'pressed_buttons': self.controller.get_pressed_buttons(),
            'recent_actions': self.controller.get_recent_actions(),
        }