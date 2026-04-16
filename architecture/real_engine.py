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
    def __init__(self, evaluator: IEvaluator, temperature: float = 0.7, branching_factor: int = 2):
        self.evaluator = evaluator
        self.temperature = temperature
        self.branching_factor = branching_factor
        self.tools = get_tool_definitions(quiet_mode=True)

    def step(self, current_node: MctsNode, goal: GoalContract) -> List[MctsNode]:
        """
        Expands the current node by calling the LLM multiple times (branching).
        Then uses the injected Evaluator to score each branch.
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

        # Phase 3: Evaluation (Critic) using injected Evaluator
        # For each child node, we use the evaluator to score its outcome against the GoalContract.
        print(f"\n[验证器] 正在对 {len(child_nodes)} 个探索分支进行过程打分...")
        for node in child_nodes:
            score = self.evaluator.evaluate_step(node, goal)
            node.score = score
            print(f"  └─ 分支 {node.id} 得分: {score}")

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
