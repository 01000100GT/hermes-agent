"""
mcts_delegate tool: registers MCTS+HITL as a hermes tool.
Parent AIAgent calls this via tool_call when it wants to delegate
a complex, multi-path task to the MCTS engine.

This tool is in _AGENT_LOOP_TOOLS because it needs parent_agent
(reference to the calling AIAgent instance).
"""

import json
import logging

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

MCTS_DELEGATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "mcts_delegate",
        "description": (
            "Delegate a complex task to the MCTS tree-search engine with "
            "human-in-the-loop checkpoints. Use for tasks that benefit from "
            "exploring multiple approaches in parallel (research, writing, "
            "stock analysis, code generation). Returns a summary + cost."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The high-level task goal to accomplish.",
                },
                "task_type": {
                    "type": "string",
                    "enum": ["auto", "stock", "code", "doc", "research"],
                    "description": "Task type hint for engine selection.",
                    "default": "auto",
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Maximum MCTS loop iterations.",
                    "default": 10,
                },
                "branching_factor": {
                    "type": "integer",
                    "description": "Number of parallel branches per expansion.",
                    "default": 2,
                },
                "budget_usd": {
                    "type": "number",
                    "description": "Maximum cost in USD.",
                    "default": 1.0,
                },
            },
            "required": ["goal"],
        },
    },
}


def mcts_delegate(
    goal: str,
    task_type: str = "auto",
    max_iterations: int = 10,
    branching_factor: int = 2,
    budget_usd: float = 1.0,
    parent_agent=None,
) -> str:
    """
    Main entry point for the MCTS delegate tool.
    Called from AIAgent._invoke_tool with parent_agent injected.
    """
    if parent_agent is None:
        return tool_error("mcts_delegate requires parent_agent context (agent-loop only).")

    logger.info(f"mcts_delegate invoked: goal={goal[:80]}...")

    try:
        from architecture.goal_contract_reviewer import GoalContractReviewer
        from architecture.harness_monitor import DefaultHarnessMonitor
        from architecture.cli_hitl_adapter import MacCliHitlAdapter
        from architecture.workflow import HermesMctsWorkflow

        reviewer = GoalContractReviewer(parent_agent=parent_agent)
        harness = DefaultHarnessMonitor()
        hitl = MacCliHitlAdapter()

        workflow = HermesMctsWorkflow(
            reviewer=reviewer,
            harness=harness,
            hitl=hitl,
        )

        final_node, total_cost = workflow.run_task(
            initial_request=goal,
            parent_agent=parent_agent,
            branching_factor=branching_factor,
            max_iterations=max_iterations,
            budget_usd=budget_usd,
        )

        if final_node is None:
            return tool_result({
                "status": "ABORTED",
                "summary": "Task was aborted (user rejected contract or hit abort).",
                "cost_usd": total_cost,
            })

        # Extract summary from final node history
        summary = ""
        for msg in reversed(final_node.history):
            if msg.get("role") == "assistant" and msg.get("content"):
                summary = msg["content"][:2000]
                break

        return tool_result({
            "status": final_node.status.value,
            "summary": summary,
            "cost_usd": round(total_cost, 4),
            "iterations": getattr(workflow, "_total_iterations", 0),
            "node_id": final_node.id,
        })

    except Exception as e:
        logger.error(f"mcts_delegate failed: {e}", exc_info=True)
        return tool_error(f"MCTS delegate error: {e}")


# --- Register with hermes tool registry ---
registry.register(
    name="mcts_delegate",
    toolset="delegation",
    schema=MCTS_DELEGATE_SCHEMA,
    handler=lambda args, **kw: mcts_delegate(
        goal=args.get("goal", ""),
        task_type=args.get("task_type", "auto"),
        max_iterations=args.get("max_iterations", 10),
        branching_factor=args.get("branching_factor", 2),
        budget_usd=args.get("budget_usd", 1.0),
        parent_agent=kw.get("parent_agent"),
    ),
    check_fn=lambda: True,
    emoji="🌳",
)
