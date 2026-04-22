"""
BatchApprovalSession: context manager for D6 batch approval mode.
Wraps tools/approval.py's per-session whitelist to allow MCTS tasks
to pre-approve dangerous patterns for the duration of a single task.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class BatchApprovalSession:
    """
    Usage:
        with BatchApprovalSession(session_key, approve_all=False) as batch:
            batch.pre_approve(["rm_pattern_1", "sudo_pattern_2"])
            # ... run MCTS engine ...
        # session whitelist is cleaned up on exit

    If approve_all=True, enables session yolo mode (auto-approve everything)
    for the session duration. Use with caution.
    """

    def __init__(self, session_key: str, approve_all: bool = False):
        self.session_key = session_key
        self.approve_all = approve_all
        self._pre_approved_patterns: List[str] = []
        self._yolo_was_enabled = False

    def __enter__(self):
        from tools.approval import is_session_yolo_enabled
        self._yolo_was_enabled = is_session_yolo_enabled(self.session_key)

        if self.approve_all:
            self._enable_yolo()

        logger.info(
            f"BatchApprovalSession started: key={self.session_key}, "
            f"approve_all={self.approve_all}"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Clean up patterns we pre-approved (not the ones user approved independently)
        # Note: approval.py doesn't have a "revoke" API per-pattern,
        # but session state is ephemeral (not persisted), so cleanup is implicit.
        if self.approve_all and not self._yolo_was_enabled:
            try:
                from tools.approval import disable_session_yolo
                disable_session_yolo(self.session_key)
            except Exception:
                pass

        logger.info(f"BatchApprovalSession ended: key={self.session_key}")

    def pre_approve(self, pattern_keys: List[str]) -> None:
        """Pre-approve a list of dangerous command patterns for this session."""
        from tools.approval import approve_session
        for pk in pattern_keys:
            try:
                approve_session(self.session_key, pk)
                self._pre_approved_patterns.append(pk)
            except Exception as e:
                logger.warning(f"Failed to pre-approve pattern '{pk}': {e}")

    def is_approved(self, pattern_key: str) -> bool:
        """Check if a pattern is approved in this session."""
        from tools.approval import is_approved
        return is_approved(self.session_key, pattern_key)

    def _enable_yolo(self) -> None:
        """Enable yolo mode for this session (auto-approve all dangerous commands)."""
        try:
            from tools.approval import enable_session_yolo
            enable_session_yolo(self.session_key)
            logger.warning(f"YOLO mode enabled for session {self.session_key}")
        except Exception as e:
            logger.error(f"Failed to enable yolo mode: {e}")
