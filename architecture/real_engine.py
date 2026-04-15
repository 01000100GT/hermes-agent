"""
Real MCTS engine implementation that calls the actual LLM API.
Uses Hermes Agent's auxiliary_client and tool registry.
"""

import json
import logging
from typing import List

from .contracts import IMctsEngine, MctsNode, NodeStatus

# Import Hermes agent's real LLM client and tool definitions
from agent.auxiliary_client import call_llm
from model_tools import get_tool_definitions, handle_function_call

logger = logging.getLogger(__name__)

class RealMctsEngine(IMctsEngine):
    def __init__(self, temperature: float = 0.7):
        self.temperature = temperature
        # Fetch all available tools from the Hermes registry
        # We use quiet_mode=True to avoid spamming the console during initialization
        self.tools = get_tool_definitions(quiet_mode=True)
        
    def step(self, current_node: MctsNode) -> List[MctsNode]:
        """
        Calls the LLM to generate the next step.
        In a full MCTS, this would branch multiple times (e.g., n=3).
        For simplicity and cost control in this MVP, we generate 1 branch.
        """
        logger.info(f"MCTS 引擎正在扩展节点 {current_node.id}...")
        
        try:
            print(f"\n[AI 思考中] 正在向 LLM 发送请求 (节点: {current_node.id})...")
            # Call the real LLM configured in Hermes (~/.hermes/config.yaml)
            response = call_llm(
                task="mcts_step",
                messages=current_node.history,
                tools=self.tools,
                temperature=self.temperature
            )
            print("[AI 思考中] 已收到 LLM 的回复！")
            
            message = response.choices[0].message
            content = message.content or ""
            
            # Parse proposed tool calls
            proposed_tool_calls = []
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    fn = tc.function
                    args = {}
                    try:
                        args = json.loads(fn.arguments)
                    except Exception:
                        pass
                    proposed_tool_calls.append({
                        "name": fn.name,
                        "args": args,
                        "id": tc.id
                    })
            
            # Create the new history including the assistant's response
            new_history = list(current_node.history)
            assistant_msg = {"role": "assistant"}
            if content:
                assistant_msg["content"] = content
            if hasattr(message, "tool_calls") and message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in message.tool_calls
                ]
            
            new_history.append(assistant_msg)
            
            # CRITICAL FIX: Real Tool Execution (Goal-Driven Execution)
            # Replace fake data with actual Hermes tool dispatcher
            if proposed_tool_calls:
                for call in proposed_tool_calls:
                    tool_name = call.get("name", "")
                    tool_args = call.get("args", {})
                    
                    print(f"[AI 执行工具] {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")
                    
                    try:
                        # Call the actual Hermes tool registry dispatcher
                        # This runs the real Python code for search_files, terminal, etc.
                        raw_result = handle_function_call(
                            function_name=tool_name,
                            function_args=tool_args,
                            task_id="mcts_test_run",
                            session_id="mcts_session"
                        )
                        # The dispatcher returns a JSON string, we parse it or keep it raw
                        try:
                            # Verify it's valid JSON
                            json.loads(raw_result)
                            final_result = raw_result
                        except:
                            final_result = json.dumps({"status": "success", "output": str(raw_result)}, ensure_ascii=False)
                            
                    except Exception as tool_e:
                        final_result = json.dumps({"status": "error", "message": f"工具执行失败: {str(tool_e)}"}, ensure_ascii=False)
                        
                    new_history.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": tool_name,
                        "content": final_result
                    })
            
            # If no tools were called AND the assistant returned some text, 
            # we consider the current branch "completed" (e.g. it asked a question or gave an answer)
            status = NodeStatus.PENDING if proposed_tool_calls else NodeStatus.COMPLETED
            
            # Simple heuristic score: penalize empty content, otherwise baseline 0.8
            score = 0.8 if content or proposed_tool_calls else 0.1
            
            child_node = MctsNode(
                id=f"{current_node.id}_child_1",
                parent_id=current_node.id,
                history=new_history,
                proposed_tool_calls=proposed_tool_calls,
                score=score,
                status=status
            )
            
            return [child_node]
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # Return a failed/pruned node so the workflow doesn't crash but stops this branch
            return [
                MctsNode(
                    id=f"{current_node.id}_error",
                    parent_id=current_node.id,
                    history=current_node.history + [{"role": "system", "content": f"Error: {str(e)}"}],
                    proposed_tool_calls=[],
                    score=0.0,
                    status=NodeStatus.PRUNED
                )
            ]

    def prune_and_redirect(self, node: MctsNode, feedback: str) -> None:
        """
        Injects the human's feedback into the node's history to steer the LLM
        away from the pruned path in the next generation attempt.
        """
        node.history.append({
            "role": "user", 
            "content": f"SYSTEM/HUMAN INTERVENTION: 您之前的意图操作已被阻止或剪枝。Feedback/Hint:{feedback}。请重新评估并尝试不同的方法。"
        })
        node.status = NodeStatus.PRUNED
