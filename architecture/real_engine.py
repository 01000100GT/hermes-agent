"""
Real MCTS engine implementation that calls the actual LLM API.
Follows the Dependency Inversion Principle and SRP.
"""

import math
import json
import logging
import concurrent.futures
from typing import List, Dict, Any, Optional

from .contracts import IMctsEngine, MctsNode, NodeStatus, GoalContract, IEvaluator, ILlmProvider, IToolExecutor

logger = logging.getLogger(__name__)

class RealMctsEngine(IMctsEngine):
    def __init__(
        self,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        evaluator: IEvaluator,
        llm_provider: ILlmProvider,
        tool_executor: IToolExecutor,
        temperature: float = 0.7,
        branching_factor: int = 2,
        exploration_constant: float = 1.414
    ):
        self.system_prompt = system_prompt
        self.tools = tools
        self.evaluator = evaluator
        self.llm_provider = llm_provider
        self.tool_executor = tool_executor
        self.temperature = temperature
        self.branching_factor = branching_factor
        self.exploration_constant = exploration_constant
        self.total_simulations = 0

    def _generate_branch(self, i: int, history: List[Dict[str, Any]]) -> Optional[Any]:
        try:
            logger.info(f"MCTS Engine: requesting LLM (branch {i+1}/{self.branching_factor})...")
            temperature = self.temperature if i == 0 else min(1.0, self.temperature + 0.2)
            msg = self.llm_provider.generate(
                messages=history,
                tools=self.tools,
                temperature=temperature
            )
            return msg
        except Exception as e:
            logger.error(f"Branch {i+1} generation failed: {e}", exc_info=True)
            return None

    def step(self, current_node: MctsNode, goal: GoalContract) -> List[MctsNode]:
        """
        Expands the current node by calling the LLM multiple times (branching).
        Generates PENDING actions but does NOT execute tools.
        """
        logger.info(f"MCTS Engine expanding node {current_node.id} with b={self.branching_factor}...")

        base_messages = [{"role": "system", "content": self.system_prompt}]
        history = base_messages + current_node.history

        candidates = []
        # Phase 1: Expansion using ThreadPool for concurrency (addresses Full-Stack expert comment)
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.branching_factor) as executor:
            futures = [executor.submit(self._generate_branch, i, history) for i in range(self.branching_factor)]
            for future in concurrent.futures.as_completed(futures):
                msg = future.result()
                if msg:
                    candidates.append(msg)

        if not candidates:
            return []

        # Phase 2: Create Child Nodes (Proposed Actions only)
        child_nodes = []
        for idx, message in enumerate(candidates):
            content = message.content or ""
            proposed_tool_calls = []

            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    args = {}
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        pass
                    proposed_tool_calls.append(
                        {"name": tc.function.name, "args": args, "id": tc.id}
                    )
                    
            new_history = list(current_node.history)
            assistant_msg = {"role": "assistant"}
            if content:
                assistant_msg["content"] = content
            if hasattr(message, "tool_calls") and message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            
            if not assistant_msg.get("content") and not assistant_msg.get("tool_calls"):
                assistant_msg["content"] = "(AI failed to generate a response, please try another path)"
            
            new_history.append(assistant_msg)

            # Determine status
            if proposed_tool_calls:
                status = NodeStatus.PENDING
            elif not content.strip():
                status = NodeStatus.PENDING  
            else:
                status = NodeStatus.COMPLETED

            node = MctsNode(
                id=f"{current_node.id}_child_{idx+1}",
                parent_id=current_node.id,
                history=new_history,
                proposed_tool_calls=proposed_tool_calls,
                score=0.0,
                status=status,
                parent=current_node
            )
            current_node.children.append(node)
            child_nodes.append(node)

        # Phase 3: Initial Evaluation of Proposed Actions
        logger.info(f"Evaluating {len(child_nodes)} proposed branches...")
        for node in child_nodes:
            score, reason = self.evaluator.evaluate_step(node, goal)
            node.score = score
            node.critic_reason = reason
            logger.debug(f"Node {node.id} initial score: {score:.2f}, reason: {reason}")
            
            self.backpropagate(node, score)

        return child_nodes

    def execute_node(self, node: MctsNode, goal: GoalContract) -> None:
        """
        Executes the tools in a PENDING node, commits the results,
        evaluates the execution outcome, and updates the score.
        """
        if node.status != NodeStatus.PENDING or not node.proposed_tool_calls:
            logger.warning(f"execute_node called on node {node.id} with status {node.status}, no tools to run.")
            return

        for call in node.proposed_tool_calls:
            tool_name = call.get("name", "")
            tool_args = call.get("args", {})
            logger.info(f"Executing tool {tool_name} for node {node.id}...")
            
            try:
                final_result = self.tool_executor.execute(tool_name, tool_args)
            except Exception as e:
                # Add proper execution error status for Evaluator to penalize
                logger.error(f"Tool {tool_name} failed: {e}")
                final_result = json.dumps({"status": "ExecutionError", "message": str(e)})

            node.history.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": tool_name,
                "content": final_result,
            })
            
        # Update node status and re-evaluate with actual tool results
        node.status = NodeStatus.EXECUTED
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
            curr = curr.parent
        self.total_simulations += 1

    def select_next_node(self, root: MctsNode) -> MctsNode:
        """Selects the most promising leaf node using UCB1."""
        curr = root
        while curr.children:
            best_score = -1.0
            best_child = None
            
            for child in curr.children:
                if child.visit_count == 0:
                    best_child = child
                    break
                
                exploitation = child.avg_value
                exploration = self.exploration_constant * math.sqrt(
                    math.log(self.total_simulations) / child.visit_count
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
            "content": f"SYSTEM/HUMAN INTERVENTION: 您之前的意图操作已被阻止或剪枝。Feedback/Hint:{feedback}。请重新评估并尝试不同的方法。",
        })
        node.status = NodeStatus.PRUNED

    def apply_override(self, node: MctsNode, feedback: str) -> None:
        node.history.append({
            "role": "user",
            "content": f"SYSTEM/HUMAN INTERVENTION: 人类直接为您提供了当前步骤的确切结果或答案：\n{feedback}\n\n请直接基于此结果继续执行下一步操作。",
        })
        # Wait, if override is provided, we simulate an execution success. 
        # So it's EXECUTED, not PENDING.
        node.status = NodeStatus.EXECUTED

    def diagnose_trajectory(self, node: MctsNode) -> str:
        logger.info("Diagnosing stuck trajectory...")
        try:
            recent_history = node.history[-6:]
            history_text = json.dumps(recent_history, ensure_ascii=False, indent=2)
            
            prompt = (
                "你是一个高级AI诊断专家。当前主智能体在执行任务时达到了最大步数限制，可能陷入了死循环或网络困境。\n"
                "请分析以下最近的执行历史，并用中文简要总结：\n"
                "1. 它目前卡在了哪里（例如：反复遇到同一个报错、被反爬虫拦截、一直在搜索无用信息等）？\n"
                "2. 给人类操作员提供 1-2 条具体的下一步建议（例如：让它换个搜索工具、建议人类直接提供上下文、或者让它换个思路）。\n"
                "请保持回答简明扼要，直接输出诊断和建议即可，不要有任何多余的寒暄。\n\n"
                f"【最近执行历史】\n{history_text}"
            )
            
            response_msg = self.llm_provider.generate(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                temperature=0.3
            )
            
            import re
            raw_content = response_msg.content or ""
            raw_content = re.sub(r'<think>[\s\S]*?</think>', '', raw_content).strip()
            return f"【诊断报告】\n{raw_content}"
            
        except Exception as e:
            logger.error(f"Diagnostics failed: {e}")
            return f"AI 达到了最大探索步数限制，且诊断服务调用失败: {e}"
