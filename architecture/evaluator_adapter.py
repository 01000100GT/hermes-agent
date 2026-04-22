"""
Concrete Evaluator that uses LLM subagents to provide process-based scoring.
Implements Single Responsibility Principle by decoupling evaluation from tree generation.
"""

from typing import Tuple
from .contracts import IEvaluator, MctsNode, GoalContract, NodeStatus

class SubagentEvaluatorAdapter(IEvaluator):
    def __init__(self, parent_agent=None):
        if parent_agent is None:
            from run_agent import AIAgent
            self.parent_agent = AIAgent(
                quiet_mode=True, skip_context_files=True, skip_memory=False
            )
        else:
            self.parent_agent = parent_agent

    def evaluate_step(self, node: MctsNode, goal: GoalContract) -> Tuple[float, str]:
        import json
        import re
        from tools.delegate_tool import _build_child_agent, _run_single_child

        action_desc = "No tools called. " + node.history[-1].get("content", "")
        outcome_desc = ""

        if node.proposed_tool_calls:
            action_desc = f"Called tools: {[c['name'] for c in node.proposed_tool_calls]}"
            outcome_desc = f"Tool result: {node.history[-1].get('content', '')[:500]}..."

        goal_msg = (
            f"Original Request: {goal.original_request}\n"
            f"Boundaries: {', '.join(goal.clarified_boundaries)}\n"
            f"Acceptance Criteria: {', '.join(goal.acceptance_criteria)}"
        )

        critic_goal = (
            "您是一位严格的过程评估者。请评估 AI 的中间步骤进展，而非苛求一次性完成全部目标。\n"
            "如果该操作对最终目标有【建设性进展】（例如：正确收集了信息、验证了环境、修复了子错误），请给出较高的过程分 (0.6-0.9)。\n"
            "如果该操作毫无进展或产生灾难性错误，给出低分 (0.0-0.3)。\n"
            "【格式要求】仅输出一个 JSON 对象，包含两个键：\n"
            "- 'score': 浮点数 (0.0 - 1.0)\n"
            "- 'reason': 简短的评分理由\n\n"
            f"用户总体目标: {goal_msg}\n"
            f"AI 当前行动: {action_desc}\n"
            f"行动结果/状态: {outcome_desc}\n"
        )

        try:
            child = _build_child_agent(
                task_index=0,
                goal=critic_goal,
                context=None,
                toolsets=[],
                model=None,
                max_iterations=2,
                parent_agent=self.parent_agent,
            )
            print(f"  [Critic] Evaluating node {node.id}...")
            result_dict = _run_single_child(
                task_index=0,
                goal=critic_goal,
                child=child,
                parent_agent=self.parent_agent,
            )

            messages = result_dict.get("messages", [])
            raw_response = ""
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    raw_response = msg.get("content", "")
                    break

            if not raw_response:
                raw_response = result_dict.get("summary", "") or result_dict.get("result", "{}")

            raw_response = re.sub(r"<think>[\s\S]*?</think>", "", raw_response).strip()

            json_match = re.search(r"\{[\s\S]*\}", raw_response)
            if json_match:
                parsed = json.loads(json_match.group(0))
                llm_score = float(parsed.get("score", 0.5))
                reason = parsed.get("reason", "No reason provided")
                
                det_score, det_reason = self._run_deterministic_checks(node, goal)
                if det_reason:
                    score = (llm_score * 0.4) + (det_score * 0.6)
                    reason = f"{reason} | {det_reason}"
                else:
                    score = llm_score
                    
                return score, reason
            else:
                score_match = re.search(r"(?i)score\s*[:=]\s*([0-9]*\.?[0-9]+)", raw_response)
                if score_match:
                    val = float(score_match.group(1))
                    score = min(1.0, max(0.0, val / 10.0 if val > 1.0 else val))
                    return score, "Score extracted from raw response (no detail)"
                return 0.5, "Could not parse score or reason from response"
        except Exception as e:
            return 0.5, f"Evaluation error: {str(e)}"

    def _run_deterministic_checks(self, node: MctsNode, goal: GoalContract) -> Tuple[float, str]:
        import os
        path_hint = None
        for boundary in goal.clarified_boundaries:
            if "/" in boundary or ".md" in boundary or ".txt" in boundary:
                import re
                match = re.search(r'(/[a-zA-Z0-9._/-]+)', boundary)
                if match:
                    path_hint = match.group(1)
                    break
        
        if path_hint and os.path.exists(path_hint):
            return 1.0, f"DETERMINISTIC: Verified file exists at {path_hint}"
            
        return 0.0, ""

    def check_acceptance(self, node: MctsNode, goal: GoalContract) -> bool:
        return node.status == NodeStatus.COMPLETED
