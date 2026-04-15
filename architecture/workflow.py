"""
Application Service Layer for the Hermes MCTS+HITL architecture.
Simplicity First: This workflow orchestrates the domain contracts
without knowing ANY implementation details.
"""

import logging
from typing import Optional

from .contracts import (
    IMctsEngine,
    IHarnessMonitor,
    IHumanIntervention,
    MctsNode,
    NodeStatus,
    HumanDecision,
)

logger = logging.getLogger(__name__)


class HermesMctsWorkflow:
    """
    The orchestrator that wires together the MCTS Engine (AI),
    Harness Monitor (Guardrails), and Human Intervention (CLI/UI).
    Strictly follows Dependency Inversion Principle (DIP).
    """

    def __init__(
        self,
        engine: IMctsEngine,
        harness: IHarnessMonitor,
        hitl: IHumanIntervention,
    ):
        self._engine = engine
        self._harness = harness
        self._hitl = hitl

    def run_task(self, root_node: MctsNode) -> Optional[MctsNode]:
        """
        The main state machine loop for a single MCTS-driven task.
        Returns the final completed node, or None if aborted.
        """
        current_node = root_node

        while current_node.status not in (NodeStatus.COMPLETED, NodeStatus.PRUNED):
            # 1. Guardrail Check (Harness Monitor)
            if self._harness.check_thresholds(current_node):
                reason = self._harness.get_suspend_reason()
                logger.warning(f"Harness triggered: {reason}. Suspending for HITL.")

                # 2. Human-In-The-Loop Intervention
                decision = self._hitl.request_decision(current_node, reason)

                if decision == HumanDecision.ABORT:
                    logger.error("Task aborted by human.")
                    return None

                elif decision in (HumanDecision.PRUNE, HumanDecision.OVERRIDE):
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.prune_and_redirect(current_node, feedback)
                    logger.info("Human provided steering feedback. Re-evaluating...")
                    # In MCTS, after pruning/steering, we let the engine select the next best node
                    continue 

                elif decision == HumanDecision.APPROVE:
                    logger.info("Human approved execution. Proceeding.")

            # 3. AI Execution (MCTS Step)
            # The engine expands the current node by proposing/executing the next actions.
            child_nodes = self._engine.step(current_node)

            if not child_nodes:
                logger.info("No further steps generated. Marking as completed.")
                current_node.status = NodeStatus.COMPLETED
                break

            # 4. Selection
            # For this draft, we simply pick the child with the highest score to continue.
            best_child = max(child_nodes, key=lambda n: n.score)
            current_node = best_child

        return current_node
