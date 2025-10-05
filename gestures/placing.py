"""
Placing/using items gesture detector
"""

import time
import numpy as np

from gestures.base_detector import BaseGestureDetector


class PlacingDetector(BaseGestureDetector):
    """
    Detects placing blocks or using items gesture based on a fast right-hand opening
    sequence, independent of forearm position.
    """

    def __init__(self):
        super().__init__("placing")

        # Hand spread thresholds (normalized by shoulder distance for camera independence)
        # Note: Values depend on shoulder-based normalization, may need adjustment
        self.close_threshold = 0.015  # Closed hand threshold
        self.open_threshold = 0.045   # Open hand threshold
        self.min_area_delta = 0.030   # Minimum area increase
        self.area_growth_rate_threshold = 0.25  # Minimum growth rate
        
        # Alternative/fallback thresholds for robust detection
        self.fallback_open_threshold = 0.035  # Lower threshold for fallback
        self.fallback_area_delta = 0.040  # Higher delta for fallback
        
        # Timing thresholds (seconds)
        self.close_to_open_window = 0.6  # Even longer window for natural motion
        self.cooldown = 0.5
        
        # Debug mode
        self.debug = False  # Disable debug logging for production

        self.reset()

    def detect(self, state_manager):
        """
        Detect placing gesture.

        Returns:
            Dictionary with action info or None:
            {'action': 'place'} - Place block/use item
        """
        if not self.enabled:
            return None

        current_time = time.time()
        hand_metrics = self._get_hand_metrics(state_manager)
        if hand_metrics is None:
            self._handle_tracking_lost()
            return None

        raw_area = hand_metrics["normalized_area"]
        
        # Apply LIGHTER smoothing to reduce noise but remain responsive (alpha = 0.5)
        normalized_area = raw_area
        if self._state["last_area"] is not None:
            normalized_area = 0.5 * raw_area + 0.5 * self._state["last_area"]
        
        previous_area = self._state["last_area"]
        previous_time = self._state["last_area_time"]

        growth_rate = None
        if previous_area is not None and previous_time is not None:
            dt = current_time - previous_time
            if dt > 0:
                growth_rate = (normalized_area - previous_area) / dt

        recent_min_area = self._update_recent_min_area(normalized_area, current_time)

        base_area = previous_area if previous_area is not None else normalized_area
        if recent_min_area is not None:
            base_area = recent_min_area

        area_increase = normalized_area - base_area
        cooldown_active = current_time < self._state["cooldown_end"]
        
        time_since_close = None
        if self._state["last_close_time"] is not None:
            time_since_close = current_time - self._state["last_close_time"]
        
        # Primary detection path: Fast opening with growth rate
        primary_trigger = (
            not cooldown_active
            and time_since_close is not None
            and time_since_close <= self.close_to_open_window
            and normalized_area >= self.open_threshold
            and area_increase >= self.min_area_delta
            and growth_rate is not None
            and growth_rate >= self.area_growth_rate_threshold
        )
        
        # Fallback detection path: Strong area increase even if slower
        fallback_trigger = (
            not cooldown_active
            and time_since_close is not None
            and time_since_close <= self.close_to_open_window
            and normalized_area >= self.fallback_open_threshold
            and area_increase >= self.fallback_area_delta
            and growth_rate is not None
            and growth_rate >= self.area_growth_rate_threshold * 0.5  # 50% of primary threshold
        )
        
        # Rapid opening detection: Very fast growth regardless of absolute area
        rapid_trigger = (
            not cooldown_active
            and time_since_close is not None
            and time_since_close <= self.close_to_open_window
            and growth_rate is not None
            and growth_rate >= self.area_growth_rate_threshold * 1.2  # 20% faster than primary
            and area_increase >= self.min_area_delta * 0.6  # At least 60% of min delta
        )
        
        # Ultra-permissive trigger: Any significant opening from closed state
        permissive_trigger = (
            not cooldown_active
            and time_since_close is not None
            and time_since_close <= self.close_to_open_window
            and normalized_area >= 0.030  # Based on actual values
            and area_increase >= 0.025  # Based on actual deltas
            and growth_rate is not None
            and growth_rate >= 0.20  # Based on actual growth rates
        )

        detection = None
        should_trigger = primary_trigger or fallback_trigger or rapid_trigger or permissive_trigger
        
        if should_trigger:
            trigger_type = "primary" if primary_trigger else ("rapid" if rapid_trigger else ("fallback" if fallback_trigger else "permissive"))
            
            # Determine which path triggered for confidence calculation
            if primary_trigger:
                confidence = self._compute_confidence(area_increase, growth_rate)
            elif rapid_trigger:
                # Boost confidence for rapid openings
                confidence = min(1.0, self._compute_confidence(area_increase, growth_rate) * 1.1)
            elif fallback_trigger:
                # Slightly reduce confidence for fallback
                confidence = self._compute_confidence(area_increase, growth_rate) * 0.9
            else:  # permissive_trigger
                confidence = self._compute_confidence(area_increase, growth_rate) * 0.8
            
            self._state["cooldown_end"] = current_time + self.cooldown
            self._state["last_close_time"] = None
            self._state["recent_min_area"] = None

            detection = {
                "action": "place",
                "confidence": round(confidence, 3),
                "area": round(normalized_area, 4),
                "area_increase": round(area_increase, 4),
                "growth_rate": round(growth_rate, 4) if growth_rate else 0.0,
            }

        self._state["last_area"] = normalized_area
        self._state["last_area_time"] = current_time

        return detection

    def _get_hand_metrics(self, state_manager):
        """
        Calculate normalized spread area of right-hand fingertips.

        Returns:
            dict or None - {"normalized_area": float, "scale_type": str} when landmarks available.
        """
        fingertip_names = [
            "right_thumb_tip",
            "right_index_finger_tip",
            "right_middle_finger_tip",
            "right_ring_finger_tip",
            "right_pinky_tip",
        ]

        points = []
        for name in fingertip_names:
            pos = state_manager.get_landmark_position(name)
            if pos is None:
                return None
            points.append((float(pos[0]), float(pos[1])))

        raw_area = self._polygon_area(points)
        hand_scale, scale_type = self._get_hand_scale(state_manager)
        if hand_scale is None:
            return None

        normalized_area = raw_area / max(hand_scale ** 2, 1e-6)
        return {
            "normalized_area": float(normalized_area),
            "scale_type": scale_type,
            "raw_area": float(raw_area),
            "scale": float(hand_scale)
        }

    @staticmethod
    def _polygon_area(points):
        """Compute planar area via the shoelace formula."""
        area = 0.0
        count = len(points)
        for i in range(count):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % count]
            area += x1 * y2 - x2 * y1
        return abs(area) * 0.5

    def _get_hand_scale(self, state_manager):
        """Estimate a scale factor using shoulder distance for camera-distance independence.
        
        Returns:
            tuple: (scale_value, scale_type) or (None, None)
        """
        # Try shoulder distance first (most reliable for full-body tracking)
        shoulder_dist = state_manager.get_landmark_distance("left_shoulder", "right_shoulder")
        if shoulder_dist is not None and shoulder_dist > 1e-5:
            return float(shoulder_dist), "shoulder"
        
        # Fallback to torso width if shoulders not visible
        hip_dist = state_manager.get_landmark_distance("left_hip", "right_hip")
        if hip_dist is not None and hip_dist > 1e-5:
            return float(hip_dist), "hip"
        
        # Last resort: use hand-based measurements (original method)
        distance_pairs = [
            ("right_wrist", "right_index_finger_mcp"),
            ("right_wrist", "right_middle_finger_mcp"),
            ("right_wrist", "right_ring_finger_mcp"),
            ("right_wrist", "right_pinky_mcp"),
            ("right_index_finger_mcp", "right_pinky_mcp"),
        ]

        distances = []
        for start, end in distance_pairs:
            dist = state_manager.get_landmark_distance(start, end)
            if dist is not None and dist > 1e-5:
                distances.append(dist)

        if not distances:
            return None, None

        return float(np.median(distances)), "hand"

    def _update_recent_min_area(self, current_area, current_time):
        """Track minimum hand area observed during the closed phase with hysteresis."""
        last_close_time = self._state["last_close_time"]
        recent_min_area = self._state["recent_min_area"]
        
        # Use hysteresis: slightly lower threshold to enter closed state
        close_enter_threshold = self.close_threshold
        # Higher threshold to exit (prevents flickering)
        close_exit_threshold = self.close_threshold + 0.05

        # Check if hand is closing or already closed
        is_closing = current_area < close_enter_threshold
        was_closed = last_close_time is not None
        
        if is_closing:
            # Update close time on first detection or if we're getting even more closed
            if not was_closed or (recent_min_area is not None and current_area < recent_min_area):
                self._state["last_close_time"] = current_time
            
            # Track minimum area during closed phase
            if recent_min_area is None or current_area < recent_min_area:
                recent_min_area = current_area
            self._state["recent_min_area"] = recent_min_area
            return recent_min_area
        
        # If hand was closed but is now opening, use exit threshold for stability
        if was_closed and current_area >= close_exit_threshold:
            # Don't immediately clear - wait for window expiry
            if current_time - last_close_time > self.close_to_open_window:
                self._state["recent_min_area"] = None
                return None

        return self._state["recent_min_area"]

    def _compute_confidence(self, area_increase, growth_rate):
        """Compute confidence score based on area change dynamics with improved scaling."""
        # Area increase contribution (0.0 to 1.0, scaled beyond min threshold)
        area_ratio = min(1.0, max(0.0, area_increase) / (self.min_area_delta * 1.5))

        # Growth rate contribution (0.0 to 1.0, scaled beyond min threshold)
        growth_ratio = 0.0
        if self.area_growth_rate_threshold > 1e-6 and growth_rate is not None:
            growth_ratio = min(1.0, max(0.0,
                (growth_rate - self.area_growth_rate_threshold * 0.5)
                / (self.area_growth_rate_threshold * 1.5)
            ))

        # Weighted combination: area matters more, but fast growth boosts confidence
        base_confidence = 0.5 + 0.35 * area_ratio + 0.15 * growth_ratio
        
        # Bonus for strong signals in both metrics
        if area_ratio > 0.7 and growth_ratio > 0.7:
            base_confidence = min(1.0, base_confidence + 0.1)
        
        return round(min(1.0, max(0.3, base_confidence)), 3)

    def _handle_tracking_lost(self):
        """Clear transient state when landmarks become unavailable."""
        self._state["last_area"] = None
        self._state["last_area_time"] = None
        self._state["last_close_time"] = None
        self._state["recent_min_area"] = None

    def reset(self):
        """Reset placing detector state."""
        super().reset()
        self._state = {
            "last_area": None,
            "last_area_time": None,
            "last_close_time": None,
            "recent_min_area": None,
            "cooldown_end": 0.0,
        }