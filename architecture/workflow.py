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
    IRequirementElicitor,
    MctsNode,
    NodeStatus,
    HumanDecision,
    GoalContract,
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
        elicitor: IRequirementElicitor,
        engine: IMctsEngine,
        harness: IHarnessMonitor,
        hitl: IHumanIntervention,
    ):
        self._elicitor = elicitor
        self._engine = engine
        self._harness = harness
        self._hitl = hitl

    def run_task(self, initial_request: str) -> Optional[MctsNode]:
        """
        The main state machine loop for a single MCTS-driven task.
        Phase 1: Clarify and lock down the goal.
        Phase 2: MCTS execution loop.
        """
        # --- PHASE 1: Requirement Elicitation ---
        logger.info("Starting Requirement Elicitation Phase...")
        goal_contract = self._elicitor.clarify_goal(initial_request)
        if not goal_contract.is_approved:
            logger.error("User rejected the final goal contract. Aborting task.")
            return None

        logger.info(f"Goal locked: {goal_contract.original_request}")

        # --- PHASE 2: MCTS Execution Loop ---
        # Fetch the system environment information using Hermes's built-in prompt builder
        try:
            from agent.prompt_builder import build_environment_prompt

            env_prompt = build_environment_prompt()
        except Exception as e:
            logger.warning(f"Failed to load environment prompt: {e}")
            import platform
            import os
            import datetime

            env_prompt = f"Operating System: {platform.system()}\nWorking Directory: {os.getcwd()}\nDate: {datetime.datetime.now().strftime('%Y-%m-%d')}"

        # Initialize the root node with the confirmed goal boundaries
        system_prompt = (
            "You are Hermes Agent, an intelligent AI assistant. You have access to various tools (e.g. web_search, terminal, write_file).\n"
            "=== SYSTEM ENVIRONMENT ===\n"
            f"{env_prompt}\n"
            "==========================\n\n"
            "You are operating under the following confirmed Goal Contract:\n"
            f"Original Request: {goal_contract.original_request}\n"
            f"Boundaries: {', '.join(goal_contract.clarified_boundaries)}\n"
            f"Acceptance Criteria: {', '.join(goal_contract.acceptance_criteria)}\n\n"
            "IMPORTANT INSTRUCTIONS:\n"
            "1. You MUST USE TOOLS to accomplish this task. Do not just output the final text if tools are required.\n"
            "2. For example, if asked to search the web and write a file, you MUST call 'web_search' and then 'write_file'.\n"
            "3. If a tool call fails or returns an error, DO NOT repeat the exact same tool call. Try a different approach or tool.\n"
            "4. Only output a final conversational answer once you have successfully used the tools to meet the Acceptance Criteria."
        )

        current_node = MctsNode(
            id="root_0",
            parent_id=None,
            history=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Please begin executing the task according to the Goal Contract. REMEMBER: Use tools to search and write the file.",
                },
            ],
            proposed_tool_calls=[],
            score=1.0,
            status=NodeStatus.PENDING,
        )
        root_node = current_node
        best_overall_node = root_node
        max_iterations = 10
        iteration = 0
        
        while best_overall_node.status not in (NodeStatus.COMPLETED, NodeStatus.PRUNED):
            # 1. Selection: Find the most promising leaf node in the entire tree
            current_node = self._engine.select_next_node(root_node)
            
            if iteration >= max_iterations:
                logger.warning("Max iterations reached. Triggering diagnostic...")
                reason = self._engine.diagnose_trajectory(current_node)
                
                # Fetch sibling candidates for context
                candidates = current_node.parent.children if current_node.parent else []
                decision = self._hitl.request_decision(current_node, reason, candidates=candidates)

                if decision == HumanDecision.ABORT:
                    logger.error("Task aborted by human due to max iterations.")
                    return None
                elif decision == HumanDecision.PRUNE:
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.prune_and_redirect(current_node, feedback)
                    # Human steering counts as a "simulated failure" for this path
                    self._engine.backpropagate(current_node, 0.0)
                    iteration = 0 
                    continue
                elif decision == HumanDecision.OVERRIDE:
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.apply_override(current_node, feedback)
                    # Human override is a massive success signal
                    self._engine.backpropagate(current_node, 1.0)
                    iteration = 0
                    continue
                elif decision == HumanDecision.APPROVE:
                    logger.info("Human approved execution to continue. Extending max_iterations.")
                    max_iterations += 20
                    self._engine.backpropagate(current_node, 1.0)
                    continue
                else:
                    break

            iteration += 1
            # 2. Guardrail Check (Harness Monitor)
            if self._harness.check_thresholds(current_node):
                reason = self._harness.get_suspend_reason()
                logger.warning(f"Harness triggered: {reason}. Suspending for HITL.")

                # 3. Human-In-The-Loop Intervention
                candidates = current_node.parent.children if current_node.parent else []
                decision = self._hitl.request_decision(current_node, reason, candidates=candidates)

                if decision == HumanDecision.ABORT:
                    logger.error("Task aborted by human.")
                    return None

                elif decision == HumanDecision.PRUNE:
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.prune_and_redirect(current_node, feedback)
                    # Human steering counts as a "simulated failure" for this path
                    self._engine.backpropagate(current_node, 0.0)
                    continue

                elif decision == HumanDecision.OVERRIDE:
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.apply_override(current_node, feedback)
                    # Human override is a massive success signal
                    self._engine.backpropagate(current_node, 1.0)
                    continue

                elif decision == HumanDecision.APPROVE:
                    logger.info("Human approved execution. Proceeding.")
                    self._engine.backpropagate(current_node, 1.0)

            # 4. AI Execution (MCTS Step: Expansion & Simulation)
            child_nodes = self._engine.step(current_node, goal_contract)

            if not child_nodes:
                logger.info("No further steps generated. Marking as completed.")
                current_node.status = NodeStatus.COMPLETED
                best_overall_node = current_node
                break

            # In true MCTS, we don't just pick one child. We expand the tree and 
            # let the next loop iteration select the best leaf via UCB1.
            # For simplicity in this conversational flow, we define the "best_overall_node"
            # as the one the user would see if they stopped now.
            best_overall_node = self._engine.select_next_node(root_node)

        # --- POST-LOOP: Final Validation ---
        return best_overall_node
