"""
Keyboard and Mouse controller for game input
"""

import platform
import time

# Try to import pynput for cross-platform support
try:
    from pynput.keyboard import Controller as KeyboardController, Key
    from pynput.mouse import Controller as MouseController, Button
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("Warning: pynput not installed. Install with: pip install pynput")


class GameController:
    """
    Handles keyboard and mouse input for game control.
    Uses pynput for cross-platform compatibility.
    """
    
    def __init__(self):
        """Initialize keyboard and mouse controllers."""
        if not PYNPUT_AVAILABLE:
            raise ImportError("pynput is required. Install with: pip install pynput")
        
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        
        # Track currently pressed keys and buttons
        self.pressed_keys = set()
        self.pressed_buttons = set()
        
        # Key mapping (Minecraft standard controls)
        self.key_map = {
            'w': 'w',
            'a': 'a',
            's': 's',
            'd': 'd',
            'space': Key.space,
            'shift': Key.shift,
            'ctrl': Key.ctrl,
            'esc': Key.esc,  # Menu/back
            'e': 'e',  # Inventory
            'q': 'q',  # Drop item
            '1': '1', '2': '2', '3': '3', '4': '4', '5': '5',
            '6': '6', '7': '7', '8': '8', '9': '9',
        }
        
        # Mouse button mapping
        self.button_map = {
            'left': Button.left,
            'right': Button.right,
            'middle': Button.middle,
        }
    
    def press_key(self, key_name):
        """
        Press and hold a key.
        
        Args:
            key_name: Name of the key (e.g., 'w', 'space', 'shift')
        """
        if key_name in self.pressed_keys:
            return  # Already pressed
        
        key = self.key_map.get(key_name, key_name)
        try:
            self.keyboard.press(key)
            self.pressed_keys.add(key_name)
        except Exception as e:
            print(f"Error pressing key {key_name}: {e}")
    
    def release_key(self, key_name):
        """
        Release a key.
        
        Args:
            key_name: Name of the key to release
        """
        if key_name not in self.pressed_keys:
            return  # Not currently pressed
        
        key = self.key_map.get(key_name, key_name)
        try:
            self.keyboard.release(key)
            self.pressed_keys.discard(key_name)
        except Exception as e:
            print(f"Error releasing key {key_name}: {e}")
    
    def tap_key(self, key_name, duration=0.05):
        """
        Tap a key (press and release quickly).
        
        Args:
            key_name: Name of the key
            duration: How long to hold the key (seconds)
        """
        self.press_key(key_name)
        time.sleep(duration)
        self.release_key(key_name)
    
    def press_mouse(self, button_name='left'):
        """
        Press and hold a mouse button.
        
        Args:
            button_name: 'left', 'right', or 'middle'
        """
        if button_name in self.pressed_buttons:
            return  # Already pressed
        
        button = self.button_map.get(button_name, Button.left)
        try:
            self.mouse.press(button)
            self.pressed_buttons.add(button_name)
        except Exception as e:
            print(f"Error pressing mouse button {button_name}: {e}")
    
    def release_mouse(self, button_name='left'):
        """
        Release a mouse button.
        
        Args:
            button_name: 'left', 'right', or 'middle'
        """
        if button_name not in self.pressed_buttons:
            return  # Not currently pressed
        
        button = self.button_map.get(button_name, Button.left)
        try:
            self.mouse.release(button)
            self.pressed_buttons.discard(button_name)
        except Exception as e:
            print(f"Error releasing mouse button {button_name}: {e}")
    
    def click_mouse(self, button_name='left', count=1):
        """
        Click a mouse button.
        
        Args:
            button_name: 'left', 'right', or 'middle'
            count: Number of clicks
        """
        button = self.button_map.get(button_name, Button.left)
        try:
            self.mouse.click(button, count)
        except Exception as e:
            print(f"Error clicking mouse button {button_name}: {e}")
    
    def move_mouse(self, dx, dy):
        """
        Move mouse relative to current position.
        
        Args:
            dx: Horizontal movement (positive = right)
            dy: Vertical movement (positive = down)
        """
        try:
            self.mouse.move(dx, dy)
        except Exception as e:
            print(f"Error moving mouse: {e}")
    
    def scroll_mouse(self, dx=0, dy=0):
        """
        Scroll the mouse wheel.
        
        Args:
            dx: Horizontal scroll
            dy: Vertical scroll (positive = up, negative = down)
        """
        try:
            self.mouse.scroll(dx, dy)
        except Exception as e:
            print(f"Error scrolling mouse: {e}")
    
    def release_all(self):
        """Release all currently pressed keys and mouse buttons."""
        # Release all keys
        for key_name in list(self.pressed_keys):
            self.release_key(key_name)
        
        # Release all mouse buttons
        for button_name in list(self.pressed_buttons):
            self.release_mouse(button_name)
    
    def is_key_pressed(self, key_name):
        """Check if a key is currently pressed."""
        return key_name in self.pressed_keys
    
    def is_mouse_pressed(self, button_name='left'):
        """Check if a mouse button is currently pressed."""
        return button_name in self.pressed_buttons
    
    def get_pressed_keys(self):
        """Get list of currently pressed keys."""
        return list(self.pressed_keys)
    
    def get_pressed_buttons(self):
        """Get list of currently pressed mouse buttons."""
        return list(self.pressed_buttons)


class MinecraftController(GameController):
    """
    Specialized controller for Minecraft with common action helpers.
    """
    
    def __init__(self):
        super().__init__()
    
    def move_forward(self):
        """Move forward (W key)."""
        self.press_key('w')
    
    def move_backward(self):
        """Move backward (S key)."""
        self.press_key('s')
    
    def move_left(self):
        """Move left (A key)."""
        self.press_key('a')
    
    def move_right(self):
        """Move right (D key)."""
        self.press_key('d')
    
    def stop_moving(self):
        """Stop all movement."""
        self.release_key('w')
        self.release_key('a')
        self.release_key('s')
        self.release_key('d')
    
    def jump(self):
        """Jump (Space key)."""
        self.tap_key('space')
    
    def start_sprint(self):
        """Start sprinting (hold W and double-tap or hold Ctrl)."""
        self.press_key('ctrl')
    
    def stop_sprint(self):
        """Stop sprinting."""
        self.release_key('ctrl')
    
    def start_sneak(self):
        """Start sneaking (hold Shift)."""
        self.press_key('shift')
    
    def stop_sneak(self):
        """Stop sneaking."""
        self.release_key('shift')
    
    def attack(self):
        """Single attack (left click)."""
        self.click_mouse('left')
    
    def start_mining(self):
        """Start mining/breaking (hold left click)."""
        self.press_mouse('left')
    
    def stop_mining(self):
        """Stop mining/breaking (release left click)."""
        self.release_mouse('left')
    
    def use_item(self):
        """Use item (right click)."""
        self.click_mouse('right')
    
    def start_using_item(self):
        """Start using item continuously (hold right click)."""
        self.press_mouse('right')
    
    def stop_using_item(self):
        """Stop using item (release right click)."""
        self.release_mouse('right')
    
    def open_inventory(self):
        """Open inventory (E key)."""
        self.tap_key('e')
    
    def drop_item(self):
        """Drop current item (Q key)."""
        self.tap_key('q')
    
    def select_hotbar_slot(self, slot):
        """
        Select a hotbar slot (1-9).
        
        Args:
            slot: Slot number (1-9)
        """
        if 1 <= slot <= 9:
            self.tap_key(str(slot))
    
    def scroll_hotbar(self, direction):
        """
        Scroll through hotbar.
        
        Args:
            direction: 1 for forward, -1 for backward
        """
        self.scroll_mouse(dy=direction)