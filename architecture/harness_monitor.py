"""
Simple guardrail implementation.
Triggers intervention if the AI attempts a dangerous command,
or if the tree depth/score looks suspicious.
"""

from .contracts import IHarnessMonitor, MctsNode

class DefaultHarnessMonitor(IHarnessMonitor):
    def __init__(self):
        self._last_reason = ""

    def check_thresholds(self, node: MctsNode) -> bool:
        for call in node.proposed_tool_calls:
            if call.get("name") == "terminal":
                cmd = call.get("args", {}).get("command", "")
                if "rm -rf" in cmd or "sudo" in cmd:
                    self._last_reason = f"Dangerous command detected: {cmd}"
                    return True

        if node.score < 0.3:
            self._last_reason = f"AI confidence score too low ({node.score:.2f})."
            return True

        return False

    def get_suspend_reason(self) -> str:
        return self._last_reason
