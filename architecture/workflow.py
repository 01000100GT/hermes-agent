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

        max_iterations = 1
        iteration = 0

        while current_node.status not in (NodeStatus.COMPLETED, NodeStatus.PRUNED):
            if iteration >= max_iterations:
                logger.warning("Max iterations reached. Triggering diagnostic...")
                reason = self._engine.diagnose_trajectory(current_node)
                
                # 当达到最大次数时，通过 HITL (Human-In-The-Loop) 询问人下一步的工作
                decision = self._hitl.request_decision(current_node, reason)

                if decision == HumanDecision.ABORT:
                    logger.error("Task aborted by human due to max iterations.")
                    return None
                elif decision == HumanDecision.PRUNE:
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.prune_and_redirect(current_node, feedback)
                    logger.info("Human provided steering feedback at max iterations. Resetting counter.")
                    # 关键修改：Prune 会将节点状态改为 PRUNED。
                    # 为了让 while 循环继续（因为我们要给 AI 新的机会），我们需要把状态改回 PENDING
                    current_node.status = NodeStatus.PENDING
                    # 关键修复：重置分数为 1.0，防止再次被低分护栏拦截！
                    current_node.score = 1.0
                    # 重置迭代计数器
                    iteration = 0 
                    continue
                elif decision == HumanDecision.OVERRIDE:
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.apply_override(current_node, feedback)
                    logger.info("Human provided override result at max iterations. Resetting counter.")
                    # apply_override 本身已经把状态设为了 PENDING
                    # 关键修复：重置分数为 1.0
                    current_node.score = 1.0
                    iteration = 0
                    continue
                elif decision == HumanDecision.APPROVE:
                    logger.info("Human approved execution to continue. Extending max_iterations.")
                    # 如果人类觉得没问题，再给 20 次机会
                    # max_iterations += 20
                    max_iterations += 1  # 测试期先多给1次机会 sss
                    # 关键修复：既然人类批准了“超出步数限制”的继续，也意味着认可当前节点，重置分数防二次拦截
                    current_node.score = 1.0
                    continue
                else:
                    break

            iteration += 1
            # 1. Guardrail Check (Harness Monitor)
            if self._harness.check_thresholds(current_node):
                reason = self._harness.get_suspend_reason()
                logger.warning(f"Harness triggered: {reason}. Suspending for HITL.")

                # 2. Human-In-The-Loop Intervention
                decision = self._hitl.request_decision(current_node, reason)

                if decision == HumanDecision.ABORT:
                    logger.error("Task aborted by human.")
                    return None

                elif decision == HumanDecision.PRUNE:
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.prune_and_redirect(current_node, feedback)
                    logger.info("Human provided steering feedback. Re-evaluating...")
                    # 关键修改：重置节点状态为 PENDING，防止外层 while 循环直接退出
                    current_node.status = NodeStatus.PENDING
                    # 关键修复：重置分数为 1.0，防止再次被低分护栏拦截！
                    current_node.score = 1.0
                    # In MCTS, after pruning/steering, we let the engine select the next best node
                    continue

                elif decision == HumanDecision.OVERRIDE:
                    feedback = self._hitl.get_human_feedback() or ""
                    self._engine.apply_override(current_node, feedback)
                    logger.info("Human provided override result. Proceeding...")
                    # In MCTS, after overriding, the node state is kept PENDING internally by apply_override
                    current_node.status = NodeStatus.PENDING
                    # 关键修复：重置分数为 1.0
                    current_node.score = 1.0
                    continue

                elif decision == HumanDecision.APPROVE:
                    logger.info("Human approved execution. Proceeding.")
                    # 关键修复：人类批准后，必须重置分数，否则下一次循环可能依然被分数拦截
                    current_node.score = 1.0

            # 3. AI Execution (MCTS Step)
            # The engine expands the current node by proposing/executing the next actions.
            # We pass the confirmed goal_contract down so the engine (and its evaluator)
            # evaluate actions strictly against this "North Star".
            child_nodes = self._engine.step(current_node, goal_contract)

            if not child_nodes:
                logger.info("No further steps generated. Marking as completed.")
                current_node.status = NodeStatus.COMPLETED
                break

            # 4. Selection
            # For this draft, we simply pick the child with the highest score to continue.
            best_child = max(child_nodes, key=lambda n: n.score)
            current_node = best_child

        return current_node
