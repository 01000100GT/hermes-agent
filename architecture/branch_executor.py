"""
BranchExecutor: bridges MctsNode history to hermes AIAgent execution.
Reuses delegate_tool's _build_child_agent / _run_single_child to avoid
duplicating the heavy AIAgent construction logic.
"""

import logging
from typing import Optional

from .contracts import MctsNode, NodeStatus, GoalContract

logger = logging.getLogger(__name__)


class BranchExecutor:
    """
    Holds a reference to parent_agent and can advance any MctsNode
    by constructing a temporary child AIAgent, injecting node.history,
    running it, and writing the results back.
    """

    def __init__(self, parent_agent):
        self.parent_agent = parent_agent

    def advance(self, node: MctsNode, goal: GoalContract, max_steps: int = 15) -> MctsNode:
        """
        Rehydrate node.history into a child AIAgent, run it, write results back.
        Returns the same node (mutated in-place).
        """
        from tools.delegate_tool import _build_child_agent, _run_single_child

        # Build a goal message that incorporates the full context
        goal_message = (
            f"Task: {goal.original_request}\n\n"
            f"Boundaries: {'; '.join(goal.clarified_boundaries)}\n"
            f"Acceptance Criteria: {'; '.join(goal.acceptance_criteria)}\n\n"
            "Continue from the current conversation state. Use tools as needed."
        )

        # Extract conversation context from node history for the child agent
        context_parts = []
        for msg in node.history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "assistant" and content:
                context_parts.append(content[:200])
        context_str = "\n".join(context_parts[-3:]) if context_parts else None

        try:
            child = _build_child_agent(
                task_index=0,
                goal=goal_message,
                context=context_str,
                toolsets=None,  # inherit parent toolset
                model=None,
                max_iterations=max_steps,
                parent_agent=self.parent_agent,
            )

            result = _run_single_child(
                task_index=0,
                goal=goal_message,
                child=child,
                parent_agent=self.parent_agent,
            )

            # Writeback: collect child agent's conversation messages
            messages = result.get("messages", [])
            for msg in messages:
                if msg not in node.history:
                    node.history.append(msg)

            # Extract summary
            summary = result.get("summary", "")
            if summary and not any(
                m.get("role") == "assistant" and m.get("content") == summary
                for m in node.history
            ):
                node.history.append({"role": "assistant", "content": summary})

            # Update cost from child agent if available
            child_tokens = result.get("tokens", {})
            if child_tokens:
                from agent.usage_pricing import estimate_usage_cost
                try:
                    cost_result = estimate_usage_cost(
                        model_name=getattr(child, "model", ""),
                        usage={
                            "prompt_tokens": child_tokens.get("input", 0),
                            "completion_tokens": child_tokens.get("output", 0),
                        },
                        provider=getattr(child, "provider", ""),
                    )
                    node.cost_usd = getattr(cost_result, "amount_usd", 0.0)
                except Exception:
                    pass

            node.status = NodeStatus.COMPLETED
            logger.info(f"BranchExecutor: node {node.id} advanced successfully.")

        except Exception as e:
            logger.error(f"BranchExecutor failed for node {node.id}: {e}", exc_info=True)
            node.history.append({
                "role": "assistant",
                "content": f"(Branch execution error: {e})",
            })
            node.status = NodeStatus.EXECUTED
            node.score = 0.0

        return node
