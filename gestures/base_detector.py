"""
Base class for gesture detectors
"""

from abc import ABC, abstractmethod


class BaseGestureDetector(ABC):
    """
    Abstract base class for all gesture detectors.
    All gesture detectors should inherit from this class.
    """
    
    def __init__(self, name):
        """
        Initialize the gesture detector.
        
        Args:
            name: Name of the gesture detector
        """
        self.name = name
        self.enabled = True
        
        # Internal state for pattern tracking
        self._state = {}
    
    @abstractmethod
    def detect(self, state_manager):
        """
        Detect gesture from current state.
        
        Args:
            state_manager: GestureStateManager instance with landmark history
        
        Returns:
            Dictionary with detection results, or None if gesture not detected.
            Format: {'action': 'action_type', 'confidence': 0.0-1.0, ...}
        """
        pass
    
    def reset(self):
        """Reset internal state."""
        self._state = {}
    
    def enable(self):
        """Enable this detector."""
        self.enabled = True
    
    def disable(self):
        """Disable this detector."""
        self.enabled = False
    
    def is_enabled(self):
        """Check if detector is enabled."""
        return self.enabled