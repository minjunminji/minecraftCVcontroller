"""
Action Coordinator - Coordinates gesture detection results with game controls
"""

from controls.keyboard_mouse import MinecraftController


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
        self.left_hand_action = None   # 'mining', 'shield', None
        self.right_hand_action = None  # 'placing', 'using', None
        
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
        """Execute actions during gameplay mode."""
        
        # 1. Handle movement actions
        self._handle_movement(gesture_results)
        
        # 2. Handle jumping
        self._handle_jumping(gesture_results)
        
        # 3. Handle left hand actions (mining, attacking, shield)
        self._handle_left_hand_actions(gesture_results)
        
        # 4. Handle right hand actions (placing, using items)
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
        
        # Apply movement rules from diagram
        action = movement.get('action')
        is_walking = movement.get('is_walking', False)
        left_thumb_back = movement.get('left_thumb_back', False)
        torso_lean = movement.get('torso_lean')
        
        new_movement = None
        
        # Determine movement direction
        if is_walking and not left_thumb_back:
            new_movement = 'w'  # Forward
        elif left_thumb_back:
            new_movement = 's'  # Backward
        elif torso_lean == 'left':
            new_movement = 'a'  # Strafe left
        elif torso_lean == 'right':
            new_movement = 'd'  # Strafe right
        
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
        Handle left hand actions: mining, attacking, shield.
        Mining: Sends L click, if multiple in period then hold L click
        Shield: Holds R click
        """
        left_hand = gesture_results.get('left_hand')
        
        if left_hand is None:
            # Release any active left hand actions
            if self.left_hand_action == 'mining':
                self.controller.stop_mining()
            elif self.left_hand_action == 'shield':
                self.controller.stop_using_item()
            self.left_hand_action = None
            return
        
        action_type = left_hand.get('action')
        
        # Mining gesture
        if action_type == 'mining_click':
            # Single click
            self.controller.attack()
            self.left_hand_action = 'attack'
            
        elif action_type == 'mining_start_hold':
            # Start holding for continuous mining
            if self.left_hand_action != 'mining':
                self.controller.start_mining()
                self.left_hand_action = 'mining'
                
        elif action_type == 'mining_stop_hold':
            # Stop mining
            if self.left_hand_action == 'mining':
                self.controller.stop_mining()
                self.left_hand_action = None
        
        # Shield gesture
        elif action_type == 'shield_start':
            if self.left_hand_action != 'shield':
                # Release any mining action first
                if self.left_hand_action == 'mining':
                    self.controller.stop_mining()
                self.controller.start_using_item()
                self.left_hand_action = 'shield'
        
        elif action_type == 'shield_hold':
            # Continue holding shield (maintain current state)
            if self.left_hand_action != 'shield':
                # Ensure shield is active
                if self.left_hand_action == 'mining':
                    self.controller.stop_mining()
                self.controller.start_using_item()
                self.left_hand_action = 'shield'
                
        elif action_type == 'shield_stop':
            if self.left_hand_action == 'shield':
                self.controller.stop_using_item()
                self.left_hand_action = None
    
    def _handle_right_hand_actions(self, gesture_results):
        """
        Handle right hand actions: placing blocks, using items.
        Placing gesture: Sends R click
        """
        right_hand = gesture_results.get('right_hand')
        
        if right_hand is None:
            self.right_hand_action = None
            return
        
        action_type = right_hand.get('action')
        
        # Placing gesture
        if action_type == 'place':
            self.controller.use_item()
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
            sensitivity = 5.0  # Adjust as needed
            if abs(dx) > 0.01 or abs(dy) > 0.01:  # Dead zone
                self.controller.move_mouse(
                    int(dx * sensitivity),
                    int(dy * sensitivity)
                )
    
    def _handle_mode_switches(self, gesture_results):
        """Handle switching between gameplay and menu modes."""
        mode_switch = gesture_results.get('mode_switch')
        
        if mode_switch == 'enter_menu':
            self._enter_menu_mode()
        elif mode_switch == 'exit_menu':
            self._exit_menu_mode()
    
    def _execute_menu_actions(self, gesture_results, state_manager):
        """Execute actions during menu mode."""
        menu_action = gesture_results.get('menu_action')
        
        if menu_action == 'select':
            self.controller.click_mouse('left')
        elif menu_action == 'back':
            self.controller.tap_key('e')  # Exit inventory
    
    def _enter_menu_mode(self):
        """Switch to menu mode."""
        if self.current_mode != 'menu':
            # Release all gameplay inputs
            self.controller.stop_moving()
            self.controller.stop_mining()
            self.controller.stop_using_item()
            
            # Open inventory
            self.controller.open_inventory()
            
            self.current_mode = 'menu'
            self.active_movement = None
            self.left_hand_action = None
            self.right_hand_action = None
    
    def _exit_menu_mode(self):
        """Switch back to gameplay mode."""
        if self.current_mode == 'menu':
            # Close inventory if open
            self.controller.tap_key('e')
            self.current_mode = 'gameplay'
    
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
    
    def cleanup(self):
        """Clean up resources and release all inputs."""
        self.reset()
    
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
        }