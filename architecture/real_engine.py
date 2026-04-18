"""
Real MCTS engine implementation that calls the actual LLM API.
Uses Hermes Agent's auxiliary_client and tool registry.
"""

import json
import logging
import concurrent.futures
from typing import List, Dict, Any

from .contracts import IMctsEngine, MctsNode, NodeStatus, GoalContract, IEvaluator

# Import Hermes agent's real LLM client and tool definitions
from agent.auxiliary_client import call_llm
from model_tools import get_tool_definitions, handle_function_call

logger = logging.getLogger(__name__)

class RealMctsEngine(IMctsEngine):
    def __init__(self, agent, evaluator=None, temperature: float = 0.7, branching_factor: int = 2):
        self.agent = agent
        self.evaluator = evaluator or (agent.evaluator if hasattr(agent, 'evaluator') else None)
        self.temperature = temperature
        self.branching_factor = branching_factor
        self.tools = agent.tools

    def step(self, current_node: MctsNode, goal: GoalContract) -> List[MctsNode]:
        """
        Expands the current node by calling the LLM multiple times (branching).
        Then uses the injected Evaluator to score each branch.
        """
        logger.info(
            f"MCTS Engine expanding node {current_node.id} with b={self.branching_factor}..."
        )

        # Build the full system prompt from the agent's core logic
        # (includes Identity, Memory blocks, Skill manifests, and Guidance prompts)
        system_prompt = self.agent._build_system_prompt()
        base_messages = [{"role": "system", "content": system_prompt}]
        full_history = base_messages + current_node.history

        candidates = []
        # Phase 1: Expansion (Generate N candidate actions)
        for i in range(self.branching_factor):
            try:
                print(
                    f"\n[AI 思考中] 正在向 LLM 发送请求 (生成分支 {i+1}/{self.branching_factor})..."
                )
                response = call_llm(
                    task="mcts_step",
                    messages=full_history,
                    tools=self.tools,
                    # We use a higher temperature for branches after the first one to encourage diversity
                    temperature=(
                        self.temperature if i == 0 else min(1.0, self.temperature + 0.2)
                    ),
                )
                
                msg = response.choices[0].message
                print(f"\n[AI 回复] 分支 {i+1} 返回结果:\n  - 文本内容: {msg.content}")
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    print(f"  - 工具调用: {[tc.function.name for tc in msg.tool_calls]}")
                    
                candidates.append(msg)
            except Exception as e:
                import traceback
                print(f"\n[错误] 分支 {i+1} 生成失败: {e}")
                traceback.print_exc()
                logger.error(f"Branch generation failed: {e}")

        if not candidates:
            return []

        # Phase 2: Execution & Node Creation
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
            # 消息合规性校验：确保 assistant 消息不为空 (协议要求必须有 content 或 tool_calls)
            if not assistant_msg.get("content") and not assistant_msg.get("tool_calls"):
                assistant_msg["content"] = "(AI failed to generate a response, please try another path)"
            
            new_history.append(assistant_msg)

            # Execute tools to see the real outcome for this branch
            if proposed_tool_calls:
                for call in proposed_tool_calls:
                    tool_name = call.get("name", "")
                    tool_args = call.get("args", {})
                    print(
                        f"[分支 {idx+1} 执行工具] {tool_name}({json.dumps(tool_args)})"
                    )
                    try:
                        raw_result = handle_function_call(
                            function_name=tool_name,
                            function_args=tool_args,
                            task_id=f"mcts_branch_{idx}",
                            session_id="mcts_session",
                        )
                        final_result = raw_result
                    except Exception as tool_e:
                        final_result = json.dumps(
                            {"status": "error", "message": str(tool_e)}
                        )

                    new_history.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "name": tool_name,
                            "content": final_result,
                        }
                    )

            # 状态判定优化：
            # 1. 如果有拟执行的工具，状态必为 PENDING
            # 2. 如果没有工具调用且内容为空，说明 AI “卡壳”了，设为 PENDING (后续会被低分拦截)
            # 3. 只有当没有工具调用且内容不为空时，才初步认为可能 COMPLETED (后续由 Evaluator 确证)
            if proposed_tool_calls:
                status = NodeStatus.PENDING
            elif not content.strip():
                status = NodeStatus.PENDING  # 空回复不代表完成
            else:
                status = NodeStatus.COMPLETED

            node = MctsNode(
                id=f"{current_node.id}_child_{idx+1}",
                parent_id=current_node.id,
                history=new_history,
                proposed_tool_calls=proposed_tool_calls,
                score=0.0,  # Will be scored by Critic next
                status=status,
            )
            child_nodes.append(node)

        # Phase 3: Evaluation (Critic) using injected Evaluator
        # For each child node, we use the evaluator to score its outcome against the GoalContract.
        print(f"\n[验证器] 正在对 {len(child_nodes)} 个探索分支进行过程打分...")
        for node in child_nodes:
            score = self.evaluator.evaluate_step(node, goal)
            node.score = score
            print(f"  [Validator] Node {node.id} score: {score:.2f}")

        return child_nodes

    def prune_and_redirect(self, node: MctsNode, feedback: str) -> None:
        """
        Injects the human's feedback into the node's history to steer the LLM
        away from the pruned path in the next generation attempt.
        """
        node.history.append(
            {
                "role": "user",
                "content": f"SYSTEM/HUMAN INTERVENTION: 您之前的意图操作已被阻止或剪枝。Feedback/Hint:{feedback}。请重新评估并尝试不同的方法。",
            }
        )
        node.status = NodeStatus.PRUNED

    def apply_override(self, node: MctsNode, feedback: str) -> None:
        """
        Injects the human's exact answer into the node's history so the LLM
        can skip the stuck step and proceed directly.
        """
        node.history.append(
            {
                "role": "user",
                "content": f"SYSTEM/HUMAN INTERVENTION: 人类直接为您提供了当前步骤的确切结果或答案：\n{feedback}\n\n请直接基于此结果继续执行下一步操作。",
            }
        )
        node.status = NodeStatus.PENDING

    def diagnose_trajectory(self, node: MctsNode) -> str:
        """
        Uses the LLM to diagnose the current stuck trajectory and provide actionable advice for the human.
        """
        print("\n[系统诊断] 正在分析 AI 陷入困境的原因并生成建议...")
        try:
            import json
            # Extract recent history to avoid token bloat
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
            
            response = call_llm(
                task="diagnose_trajectory",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            import re
            raw_content = response.choices[0].message.content or ""
            raw_content = re.sub(r'<think>[\s\S]*?</think>', '', raw_content).strip()
            
            return f"【诊断报告】\n{raw_content}"
        except Exception as e:
            return f"AI 达到了最大探索步数限制，且诊断服务调用失败: {e}"
