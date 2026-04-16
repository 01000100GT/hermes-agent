"""
A mock MCTS engine to demonstrate the workflow.
Simulates an AI generating actions and getting stuck until human intervention.
"""

from typing import List
from .contracts import IMctsEngine, MctsNode, NodeStatus

class MockMctsEngine(IMctsEngine):
    def __init__(self):
        self._turn_count = 0
        self._has_human_hint = False

    def step(self, current_node: MctsNode) -> List[MctsNode]:
        self._turn_count += 1
        
        # Turn 1: Try something harmless
        if self._turn_count == 1:
            return [
                MctsNode(
                    id="node_2",
                    parent_id=current_node.id,
                    history=current_node.history + [{"role": "assistant", "content": "I will check the directory."}],
                    proposed_tool_calls=[{"name": "terminal", "args": {"command": "ls -la"}}],
                    score=0.8,
                    status=NodeStatus.PENDING
                )
            ]
            
        # Turn 2: Simulate AI trying a dangerous command without human hint
        if self._turn_count == 2 and not self._has_human_hint:
            return [
                MctsNode(
                    id="node_3_dangerous",
                    parent_id=current_node.id,
                    history=current_node.history + [{"role": "assistant", "content": "I will clean up the temp files."}],
                    proposed_tool_calls=[{"name": "terminal", "args": {"command": "rm -rf /Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/tmp/hermes_*"}}],
                    score=0.6,
                    status=NodeStatus.PENDING
                )
            ]
            
        # Turn 2 or later (after human hint): Generate safe path
        return [
            MctsNode(
                id=f"node_safe_{self._turn_count}",
                parent_id=current_node.id,
                history=current_node.history + [{"role": "assistant", "content": "I have completed the task safely."}],
                proposed_tool_calls=[],
                score=0.95,
                status=NodeStatus.COMPLETED
            )
        ]

    def prune_and_redirect(self, node: MctsNode, feedback: str) -> None:
        # Simulate absorbing human knowledge to avoid the dangerous path next turn
        self._has_human_hint = True
        node.history.append({"role": "user", "content": f"Hint: {feedback}"})
        node.status = NodeStatus.PRUNED

    def apply_override(self, node: MctsNode, feedback: str) -> None:
        self._has_human_hint = True
        node.history.append({"role": "user", "content": f"Exact Answer: {feedback}"})
        node.status = NodeStatus.PENDING

    def diagnose_trajectory(self, node: MctsNode) -> str:
        return "Mock Engine: 达到了最大步数限制，建议人类提供进一步的指示。"
