"""
RealMctsEngine: drives MCTS tree search via BranchExecutor (which wraps hermes AIAgent).
No longer depends on ILlmProvider or IToolExecutor — all LLM/tool execution
goes through the AIAgent instance chain (parent_agent → _build_child_agent).
"""

import math
import json
import logging
from typing import List, Dict, Any, Optional

from .contracts import IMctsEngine, MctsNode, NodeStatus, GoalContract, IEvaluator
from .branch_executor import BranchExecutor

logger = logging.getLogger(__name__)


class RealMctsEngine(IMctsEngine):
    def __init__(
        self,
        parent_agent,
        evaluator: IEvaluator,
        branching_factor: int = 2,
        exploration_constant: float = 1.414,
    ):
        self.parent_agent = parent_agent
        self.evaluator = evaluator
        self.branching_factor = branching_factor
        self.exploration_constant = exploration_constant
        self.total_simulations = 0
        self._executor = BranchExecutor(parent_agent)

    def step(self, current_node: MctsNode, goal: GoalContract) -> List[MctsNode]:
        """
        Expands the current node by spawning branching_factor child agents.
        Each child is a full AIAgent run via BranchExecutor.
        """
        logger.info(
            f"MCTS Engine expanding node {current_node.id} "
            f"with b={self.branching_factor}..."
        )

        child_nodes = []
        for i in range(self.branching_factor):
            child_id = f"{current_node.id}_b{i}"
            child = MctsNode(
                id=child_id,
                parent_id=current_node.id,
                history=list(current_node.history),
                proposed_tool_calls=[],
                score=0.0,
                status=NodeStatus.PENDING,
                parent=current_node,
                branch_id=child_id,
            )
            current_node.children.append(child)
            child_nodes.append(child)

        # Execute each branch via BranchExecutor
        logger.info(f"Executing {len(child_nodes)} branches via BranchExecutor...")
        for node in child_nodes:
            try:
                self._executor.advance(node, goal)
            except Exception as e:
                logger.error(f"Branch {node.id} execution failed: {e}", exc_info=True)
                node.status = NodeStatus.EXECUTED
                node.critic_reason = f"Execution error: {e}"

        # Evaluate each branch
        logger.info(f"Evaluating {len(child_nodes)} branches...")
        for node in child_nodes:
            if node.status in (NodeStatus.COMPLETED, NodeStatus.EXECUTED):
                score, reason = self.evaluator.evaluate_step(node, goal)
                node.score = score
                node.critic_reason = reason
                logger.debug(
                    f"Node {node.id} score: {score:.2f}, reason: {reason}"
                )
                self.backpropagate(node, score)

        return child_nodes

    def execute_node(self, node: MctsNode, goal: GoalContract) -> None:
        """
        Re-execute / continue a node via BranchExecutor.
        Used when the workflow wants to explicitly advance a node.
        """
        if node.status == NodeStatus.COMPLETED:
            logger.warning(f"execute_node called on already COMPLETED node {node.id}")
            return

        logger.info(f"Executing node {node.id} via BranchExecutor...")
        self._executor.advance(node, goal)

        score, reason = self.evaluator.evaluate_step(node, goal)
        node.score = score
        node.critic_reason = reason
        logger.info(f"Node {node.id} post-execution score: {score:.2f}, reason: {reason}")
        self.backpropagate(node, score)

    def backpropagate(self, node: MctsNode, score: float) -> None:
        """Updates the path from leaf to root with the evaluation score."""
        curr = node
        while curr:
            curr.visit_count += 1
            curr.value += score
            # Propagate cost upward
            curr.cumulative_cost_usd = curr.cost_usd + sum(
                c.cumulative_cost_usd for c in curr.children
            )
            curr = curr.parent
        self.total_simulations += 1

    def select_next_node(self, root: MctsNode) -> MctsNode:
        """Selects the most promising leaf node using UCB1 (parent-visit corrected)."""
        curr = root
        while curr.children:
            best_score = -1.0
            best_child = None

            for child in curr.children:
                if child.visit_count == 0:
                    best_child = child
                    break

                exploitation = child.avg_value
                # Fixed: use parent.visit_count, not global total_simulations
                exploration = self.exploration_constant * math.sqrt(
                    math.log(curr.visit_count) / child.visit_count
                )
                ucb1 = exploitation + exploration

                if ucb1 > best_score:
                    best_score = ucb1
                    best_child = child

            if not best_child:
                break
            curr = best_child
        return curr

    def prune_and_redirect(self, node: MctsNode, feedback: str) -> None:
        node.history.append({
            "role": "user",
            "content": (
                f"SYSTEM/HUMAN INTERVENTION: 您之前的意图操作已被阻止或剪枝。"
                f"Feedback/Hint:{feedback}。请重新评估并尝试不同的方法。"
            ),
        })
        node.status = NodeStatus.PRUNED

    def apply_override(self, node: MctsNode, feedback: str) -> None:
        node.history.append({
            "role": "user",
            "content": (
                f"SYSTEM/HUMAN INTERVENTION: 人类直接为您提供了当前步骤的确切结果或答案：\n"
                f"{feedback}\n\n请直接基于此结果继续执行下一步操作。"
            ),
        })
        node.status = NodeStatus.EXECUTED

    def diagnose_trajectory(self, node: MctsNode) -> str:
        """Diagnose why the agent is stuck using auxiliary_client.call_llm."""
        logger.info("Diagnosing stuck trajectory...")
        try:
            from agent.auxiliary_client import call_llm
            import re

            recent_history = node.history[-6:]
            history_text = json.dumps(recent_history, ensure_ascii=False, indent=2)

            prompt = (
                "你是一个高级AI诊断专家。当前主智能体在执行任务时达到了最大步数限制，"
                "可能陷入了死循环或网络困境。\n"
                "请分析以下最近的执行历史，并用中文简要总结：\n"
                "1. 它目前卡在了哪里？\n"
                "2. 给人类操作员提供 1-2 条具体的下一步建议。\n"
                "请保持回答简明扼要，直接输出诊断和建议即可，不要有任何多余的寒暄。\n\n"
                f"【最近执行历史】\n{history_text}"
            )

            response = call_llm(
                task="diagnose_trajectory",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            raw_content = response.choices[0].message.content or ""
            raw_content = re.sub(r'<think[\s\S]*?/think>', '', raw_content).strip()
            return f"【诊断报告】\n{raw_content}"

        except Exception as e:
            logger.error(f"Diagnostics failed: {e}")
            return f"AI 达到了最大探索步数限制，且诊断服务调用失败: {e}"
