"""
Application Service Layer for the Hermes MCTS+HITL architecture.
Now operates as an internal entry point called by tools/mcts_delegate_tool.py.
Orchestrates: GoalContractReviewer → BatchApproval → Engine → HITL.
"""

import logging
from typing import Optional, Tuple

from .contracts import (
    IHarnessMonitor,
    IHumanIntervention,
    IRequirementElicitor,
    MctsNode,
    NodeStatus,
    HumanDecision,
    GoalContract,
)

logger = logging.getLogger(__name__)


class HermesMctsWorkflow:
    """
    Orchestrator for MCTS + HITL. Called by mcts_delegate_tool.

    Call flow:
        run_task(goal, parent_agent, ...)
            → reviewer.review_goal(goal)           [D9: contract gate]
            → hitl.preview_contract_and_confirm()   [D6: batch approval]
            → BatchApprovalSession                  [D6: scope]
            → RealMctsEngine(parent_agent, ...)     [engine]
            → MCTS loop (select → expand → execute → evaluate)
            → return best node
    """

    def __init__(
        self,
        reviewer: IRequirementElicitor,
        harness: IHarnessMonitor,
        hitl: IHumanIntervention,
    ):
        self._reviewer = reviewer
        self._harness = harness
        self._hitl = hitl

    def run_task(
        self,
        initial_request: str,
        parent_agent,
        branching_factor: int = 2,
        max_iterations: int = 10,
        budget_usd: float = 1.0,
    ) -> Tuple[Optional[MctsNode], float]:
        """
        Main entry point. Returns (best_node, total_cost_usd).

        Parameters:
            initial_request: goal string from mcts_delegate tool args
            parent_agent: hermes AIAgent instance
            branching_factor: number of branches per expansion
            max_iterations: MCTS loop iteration limit
            budget_usd: cost cap
        """
        from .real_engine import RealMctsEngine
        from .evaluator_adapter import SubagentEvaluatorAdapter
        from .approval_batch import BatchApprovalSession

        # --- PHASE 1: Goal Contract Review (D9) ---
        logger.info("Starting Goal Contract Review Phase...")
        draft_contract = self._reviewer.review_goal(initial_request)

        # D6: present contract + batch approval checkbox
        from .cli_hitl_adapter import MacCliHitlAdapter
        if isinstance(self._hitl, MacCliHitlAdapter):
            goal_contract, approve_all = self._hitl.preview_contract_and_confirm(draft_contract)
        else:
            goal_contract = draft_contract
            approve_all = False

        if not goal_contract.is_approved:
            logger.error("User rejected the goal contract. Aborting.")
            return None, 0.0

        logger.info(f"Goal locked: {goal_contract.original_request}")

        # --- PHASE 2: Build Engine + Batch Approval Session ---
        evaluator = SubagentEvaluatorAdapter(parent_agent=parent_agent)
        engine = RealMctsEngine(
            parent_agent=parent_agent,
            evaluator=evaluator,
            branching_factor=branching_factor,
        )

        import uuid
        session_key = f"mcts_{uuid.uuid4().hex[:8]}"

        with BatchApprovalSession(session_key, approve_all=approve_all):
            return self._run_mcts_loop(
                engine, goal_contract, max_iterations, budget_usd
            )

    def _run_mcts_loop(
        self,
        engine,
        goal_contract: GoalContract,
        max_iterations: int,
        budget_usd: float,
    ) -> Tuple[Optional[MctsNode], float]:
        """The MCTS execution loop."""

        # Initialize root node
        import platform
        import os
        import datetime

        env_prompt = (
            f"Operating System: {platform.system()}\n"
            f"Working Directory: {os.getcwd()}\n"
            f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}"
        )

        system_prompt = (
            "You are Hermes Agent, an intelligent AI assistant. "
            "You have access to various tools (e.g. web_search, terminal, write_file).\n"
            "=== SYSTEM ENVIRONMENT ===\n"
            f"{env_prompt}\n"
            "==========================\n\n"
            "You are operating under the following confirmed Goal Contract:\n"
            f"Original Request: {goal_contract.original_request}\n"
            f"Boundaries: {', '.join(goal_contract.clarified_boundaries)}\n"
            f"Acceptance Criteria: {', '.join(goal_contract.acceptance_criteria)}\n\n"
            "IMPORTANT INSTRUCTIONS:\n"
            "1. You MUST USE TOOLS to accomplish this task.\n"
            "2. If a tool call fails, try a different approach.\n"
            "3. Only output a final answer once the Acceptance Criteria are met."
        )

        root_node = MctsNode(
            id="root_0",
            parent_id=None,
            history=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        "Please begin executing the task according to the Goal Contract. "
                        "Use tools as needed."
                    ),
                },
            ],
            proposed_tool_calls=[],
            score=1.0,
            status=NodeStatus.PENDING,
        )
        best_overall_node = root_node
        iteration = 0

        while best_overall_node.status not in (NodeStatus.COMPLETED, NodeStatus.PRUNED):
            # Selection
            current_node = engine.select_next_node(root_node)

            # Budget check (L3)
            if root_node.cumulative_cost_usd >= budget_usd:
                logger.warning("Budget exhausted. Returning best node.")
                break

            if iteration >= max_iterations:
                logger.warning("Max iterations reached. Triggering diagnostic...")
                reason = engine.diagnose_trajectory(current_node)
                candidates = current_node.parent.children if current_node.parent else []
                decision = self._hitl.request_decision(
                    current_node, reason, candidates=candidates
                )

                if decision == HumanDecision.ABORT:
                    return None, root_node.cumulative_cost_usd
                elif decision == HumanDecision.PRUNE:
                    feedback = self._hitl.get_human_feedback() or ""
                    engine.prune_and_redirect(current_node, feedback)
                    engine.backpropagate(current_node, 0.0)
                    iteration = 0
                    continue
                elif decision == HumanDecision.OVERRIDE:
                    feedback = self._hitl.get_human_feedback() or ""
                    engine.apply_override(current_node, feedback)
                    engine.backpropagate(current_node, 1.0)
                    iteration = 0
                    continue
                elif decision == HumanDecision.APPROVE:
                    max_iterations += 20
                    engine.backpropagate(current_node, 1.0)
                    continue
                else:
                    break

            iteration += 1

            # Harness check (L2) for PENDING nodes with proposed tool calls
            if current_node.status == NodeStatus.PENDING and current_node.proposed_tool_calls:
                if self._harness.check_thresholds(current_node):
                    reason = self._harness.get_suspend_reason()
                    logger.warning(f"Harness triggered: {reason}")

                    candidates = current_node.parent.children if current_node.parent else []
                    decision = self._hitl.request_decision(
                        current_node, reason, candidates=candidates
                    )

                    if decision == HumanDecision.ABORT:
                        return None, root_node.cumulative_cost_usd
                    elif decision == HumanDecision.PRUNE:
                        feedback = self._hitl.get_human_feedback() or ""
                        engine.prune_and_redirect(current_node, feedback)
                        engine.backpropagate(current_node, 0.0)
                        best_overall_node = engine.select_next_node(root_node)
                        continue
                    elif decision == HumanDecision.OVERRIDE:
                        feedback = self._hitl.get_human_feedback() or ""
                        engine.apply_override(current_node, feedback)
                        engine.backpropagate(current_node, 1.0)
                        best_overall_node = engine.select_next_node(root_node)
                        continue
                    elif decision == HumanDecision.APPROVE:
                        logger.info("Human approved. Proceeding.")

                # Execute pending node
                logger.info(f"Executing node {current_node.id}...")
                engine.execute_node(current_node, goal_contract)
                best_overall_node = engine.select_next_node(root_node)
                continue

            # Expansion
            logger.info(f"Expanding node {current_node.id}...")
            child_nodes = engine.step(current_node, goal_contract)

            if not child_nodes:
                logger.info("No children generated. Marking as completed.")
                current_node.status = NodeStatus.COMPLETED
                best_overall_node = current_node
                break

            best_overall_node = engine.select_next_node(root_node)

        # Track total cost
        total_cost = root_node.cumulative_cost_usd
        return best_overall_node, total_cost
