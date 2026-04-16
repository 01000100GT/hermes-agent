"""
Real MCTS engine implementation that calls the actual LLM API.
Uses Hermes Agent's auxiliary_client and tool registry.
"""

import json
import logging
import concurrent.futures
from typing import List, Dict, Any

from .contracts import IMctsEngine, MctsNode, NodeStatus

# Import Hermes agent's real LLM client and tool definitions
from agent.auxiliary_client import call_llm
from model_tools import get_tool_definitions, handle_function_call

# Import Subagent architecture to act as our Critic/Verifier
from tools.delegate_tool import _build_child_agent, _run_single_child

logger = logging.getLogger(__name__)


class RealMctsEngine(IMctsEngine):
    def __init__(self, temperature: float = 0.7, branching_factor: int = 2):
        self.temperature = temperature
        self.branching_factor = branching_factor
        self.tools = get_tool_definitions(quiet_mode=True)
        # We need a parent agent context to spawn subagents.
        # For this MVP, we create a lightweight dummy or use the config directly.
        from run_agent import AIAgent

        self.parent_agent = AIAgent(
            quiet_mode=True, skip_context_files=True, skip_memory=True
        )

    def step(self, current_node: MctsNode) -> List[MctsNode]:
        """
        Expands the current node by calling the LLM multiple times (branching).
        Then uses Hermes subagents as a Critic to score each branch.
        """
        logger.info(
            f"MCTS Engine expanding node {current_node.id} with b={self.branching_factor}..."
        )

        candidates = []
        # Phase 1: Expansion (Generate N candidate actions)
        # In a real high-perf system, this should be async/parallel.
        for i in range(self.branching_factor):
            try:
                print(
                    f"\n[AI 思考中] 正在向 LLM 发送请求 (生成分支 {i+1}/{self.branching_factor})..."
                )
                response = call_llm(
                    task="mcts_step",
                    messages=current_node.history,
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

            status = NodeStatus.PENDING if proposed_tool_calls else NodeStatus.COMPLETED

            node = MctsNode(
                id=f"{current_node.id}_child_{idx+1}",
                parent_id=current_node.id,
                history=new_history,
                proposed_tool_calls=proposed_tool_calls,
                score=0.0,  # Will be scored by Critic next
                status=status,
            )
            child_nodes.append(node)

        # Phase 3: Evaluation (Critic) using Hermes Subagents
        # For each child node, we spawn a restricted subagent to evaluate its outcome.
        self._evaluate_nodes_with_subagents(child_nodes, current_node.history)

        return child_nodes

    def _evaluate_nodes_with_subagents(
        self, nodes: List[MctsNode], original_history: List[Dict[str, Any]]
    ):
        """
        Uses Hermes's native delegate_task logic to spawn parallel critic agents.
        Each critic looks at the action taken by a branch and scores it 0.0 - 1.0.
        """
        print(
            f"\n[验证器] 正在拉起 {len(nodes)} 个子智能体 (Subagents) 对探索分支进行打分..."
        )

        # Extract the original goal from the very first message
        goal_msg = next(
            (m["content"] for m in original_history if m["role"] == "user"),
            "Unknown goal",
        )

        def evaluate_single_node(idx, node):
            # What did this branch actually do?
            action_desc = "No tools called. " + node.history[-1].get("content", "")
            outcome_desc = ""

            if node.proposed_tool_calls:
                action_desc = (
                    f"Called tools: {[c['name'] for c in node.proposed_tool_calls]}"
                )
                # The last message in history is the tool result
                outcome_desc = (
                    f"Tool result: {node.history[-1].get('content', '')[:500]}..."
                )

            critic_goal = (
                "您是一位严格的评估者/批评者。您的职责是针对用户原始目标，对 AI 提出的行动进行评分。\n"
                "【格式要求】您必须，且只能输出一个合法的 JSON 对象，不要输出任何额外的解释或 Markdown 格式（不要使用 ```json 包裹）。\n"
                "JSON 对象必须恰好包含两个键：\n"
                "- 'score': 一个浮点数，范围从 0.0 到 1.0之间。\n"
                "- 'reason': 一个简单的句子，解释为什么给定的评分是这样的。\n"
                "示例输出:\n"
                '{"score": 0.8, "reason": "行动直接且准确地回答了用户关于Vue3作者的问题。"}\n\n'
                f"User's Goal: {goal_msg}\n"
                f"AI's Action: {action_desc}\n"
                f"Action Outcome: {outcome_desc}\n"
            )

            # Build a subagent with NO tools (pure reasoning critic)
            child = _build_child_agent(
                task_index=idx,
                goal=critic_goal,
                context=None,
                toolsets=[],  # Restricted: Critic cannot execute tools
                model=None,
                max_iterations=1,
                parent_agent=self.parent_agent,
            )

            result_dict = _run_single_child(
                task_index=idx,
                goal=critic_goal,
                child=child,
                parent_agent=self.parent_agent,
            )

            # Parse the critic's JSON response
            # Note: _run_single_child returns a dict with 'messages' containing the conversation
            messages = result_dict.get("messages", [])
            raw_response = ""
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    raw_response = msg.get("content", "")
                    break

            if not raw_response:
                raw_response = result_dict.get("summary", "")
            if not raw_response:
                raw_response = result_dict.get("result", "{}")

            score = 0.5  # Default fallback
            reason = "No reason provided"
            
            # If the API returned a 400 error or similar (e.g. rate limit, bad request due to context format)
            # Or if we genuinely failed to get any response text
            if not raw_response or "error" in str(result_dict).lower() and not raw_response:
                print(f"  └─ 分支 {idx+1} 验证器子智能体 API 调用失败或无返回。")
                print(f"     [调试信息] result_dict: {result_dict}")
                node.score = score
                return node

            try:
                import re

                # Extract JSON using regex in case the LLM ignored our "no markdown" instruction
                json_match = re.search(r"\{[\s\S]*\}", raw_response)
                if json_match:
                    json_str = json_match.group(0)
                    parsed = json.loads(json_str)
                    score = float(parsed.get("score", 0.5))
                    reason = parsed.get("reason", "No reason provided")
                    print(f"  └─ 分支 {idx+1} 得分: {score} (理由: {reason})")
                else:
                    # Fallback: Try to parse score from text like "Score: 3/10" or "score: 0.8"
                    score_match = re.search(r"(?i)score\s*[:=]\s*([0-9]*\.?[0-9]+)(?:\s*/\s*10)?", raw_response)
                    if score_match:
                        val = float(score_match.group(1))
                        # If the LLM returned out of 10 instead of 0.0-1.0
                        if val > 1.0:
                            val = val / 10.0
                        score = min(1.0, max(0.0, val))
                        reason = "Score extracted via fallback regex from natural language."
                        print(f"  └─ 分支 {idx+1} 得分: {score} (后备解析: {reason})")
                    else:
                        raise ValueError("No JSON object found in response and fallback regex failed")
            except Exception as e:
                print(
                    f"  └─ 分支 {idx+1} 打分解析失败，默认给 0.5 分。原始回复: {raw_response[:100].replace(chr(10), ' ')}"
                )

            node.score = score
            return node

        # Run critics in parallel using Hermes's built-in subagent threading approach
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(nodes)) as executor:
            futures = [
                executor.submit(evaluate_single_node, i, node)
                for i, node in enumerate(nodes)
            ]
            concurrent.futures.wait(futures)

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
