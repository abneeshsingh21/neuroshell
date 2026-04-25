# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
Plan Mode
State controller that strictly governs whether AI is allowed to execute commands
or if it must remain in a safe brainstorm/architecting state.
"""

import threading

class PlanModeController:
    def __init__(self):
        self._is_planning = False
        self._plan_buffer = []
        self._lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._is_planning

    def enter_plan_mode(self):
        """Locks the AI into brainstorm mode. Destructive actions will be blocked."""
        with self._lock:
            self._is_planning = True
            self._plan_buffer.clear()

    def exit_plan_mode(self):
        """Unlocks execution mode."""
        with self._lock:
            self._is_planning = False

    def add_to_plan(self, thought: str):
        """Allows AI to stream thoughts into a pending task-tree."""
        with self._lock:
            if self._is_planning:
                self._plan_buffer.append(thought)

    def get_current_plan(self) -> str:
        with self._lock:
            return "\n".join(self._plan_buffer)
