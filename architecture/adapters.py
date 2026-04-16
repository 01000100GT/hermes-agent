"""
Mac Native CLI Adapter and Default Harness Monitor.
Provides concrete implementations for the architecture contracts.
"""

import sys
import time
from typing import Optional

from .contracts import (
    IHarnessMonitor,
    IHumanIntervention,
    IRequirementElicitor,
    IEvaluator,
    MctsNode,
    HumanDecision,
    GoalContract,
)


class SubagentEvaluatorAdapter(IEvaluator):
    """
    Concrete Evaluator that uses LLM subagents to provide process-based scoring.
    Implements Single Responsibility Principle by decoupling evaluation from tree generation.
    """

    def __init__(self, parent_agent=None):
        if parent_agent is None:
            from run_agent import AIAgent

            self.parent_agent = AIAgent(
                quiet_mode=True, skip_context_files=True, skip_memory=True
            )
        else:
            self.parent_agent = parent_agent

    def evaluate_step(self, node: MctsNode, goal: GoalContract) -> float:
        import json
        import re
        from tools.delegate_tool import _build_child_agent, _run_single_child

        # What did this branch actually do?
        action_desc = "No tools called. " + node.history[-1].get("content", "")
        outcome_desc = ""

        if node.proposed_tool_calls:
            action_desc = (
                f"Called tools: {[c['name'] for c in node.proposed_tool_calls]}"
            )
            outcome_desc = (
                f"Tool result: {node.history[-1].get('content', '')[:500]}..."
            )

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
                max_iterations=1,
                parent_agent=self.parent_agent,
            )
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
                raw_response = result_dict.get("summary", "") or result_dict.get(
                    "result", "{}"
                )

            raw_response = re.sub(r"<think>[\s\S]*?</think>", "", raw_response).strip()

            json_match = re.search(r"\{[\s\S]*\}", raw_response)
            if json_match:
                parsed = json.loads(json_match.group(0))
                return float(parsed.get("score", 0.5))
            else:
                score_match = re.search(
                    r"(?i)score\s*[:=]\s*([0-9]*\.?[0-9]+)", raw_response
                )
                if score_match:
                    val = float(score_match.group(1))
                    return min(1.0, max(0.0, val / 10.0 if val > 1.0 else val))
                return 0.5
        except Exception as e:
            return 0.5

    def check_acceptance(self, node: MctsNode, goal: GoalContract) -> bool:
        # Simplistic implementation for now; could also call LLM to verify
        return node.status == MctsNode.COMPLETED


try:
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class DefaultHarnessMonitor(IHarnessMonitor):
    """
    Simple guardrail implementation.
    Triggers intervention if the AI attempts a dangerous command,
    or if the tree depth/score looks suspicious.
    """

    def __init__(self):
        self._last_reason = ""

    def check_thresholds(self, node: MctsNode) -> bool:
        # Example 1: Detect dangerous system commands
        for call in node.proposed_tool_calls:
            if call.get("name") == "terminal":
                cmd = call.get("args", {}).get("command", "")
                if "rm -rf" in cmd or "sudo" in cmd:
                    self._last_reason = f"Dangerous command detected: {cmd}"
                    return True

        # Example 2: Detect if AI is stuck (low score)
        if node.score < 0.3:
            self._last_reason = f"AI confidence score too low ({node.score:.2f})."
            return True

        return False

    def get_suspend_reason(self) -> str:
        return self._last_reason


class MacCliElicitorAdapter(IRequirementElicitor):
    """
    Mac-native terminal interface for Requirement Elicitation.
    Instead of hardcoding, it calls the LLM to analyze the request
    and generate 2 targeted clarification questions.
    """

    def clarify_goal(self, initial_request: str) -> GoalContract:
        sys.stdout.write("\a")  # Bell
        sys.stdout.flush()

        if HAS_RICH:
            console.print(
                "\n[bold magenta]🎯  Requirement Elicitation Phase[/bold magenta]"
            )
            console.print(f"[cyan]Original Request:[/cyan] {initial_request}")
            console.print(
                "\n[dim]Analyzing request to generate clarification questions...[/dim]"
            )

        # 1. Use Hermes auxiliary client to generate dynamic questions
        from agent.auxiliary_client import call_llm
        import json
        import re

        prompt = (
            "You are a Requirements Analyst. The user has made the following request:\n"
            f'"{initial_request}"\n\n'
            "Analyze this request and identify 2 critical ambiguities or missing constraints.\n"
            "IMPORTANT: If the user EXPLICITLY requests an action (like writing a file, creating a directory, or executing a command), "
            "your default_boundary_1 and default_criteria_1 MUST INCLUDE and SUPPORT that action. "
            "DO NOT assume you cannot perform the action. DO NOT output 'I cannot write files' or 'only output text' if the user asked you to write a file.\n\n"
            "Output ONLY a valid JSON object with the following structure:\n"
            "{\n"
            '  "q1": "Your first clarification question?",\n'
            '  "q2": "Your second clarification question?",\n'
            '  "default_boundary_1": "A safe boundary that INCLUDES the user\'s explicit requests (e.g., \'Must write to the specified path\').",\n'
            '  "default_criteria_1": "A measurable acceptance criteria that proves the explicit request was fulfilled."\n'
            "}"
        )

        try:
            response = call_llm(
                task="elicit_requirements",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            raw_content = response.choices[0].message.content or ""
            # Strip markdown / <think> tags
            raw_content = re.sub(r"<think>[\s\S]*?</think>", "", raw_content).strip()
            json_match = re.search(r"\{[\s\S]*\}", raw_content)
            if json_match:
                parsed = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found")

            q1 = parsed.get("q1", "Are there any specific formatting requirements?")
            q2 = parsed.get(
                "q2", "Are there any constraints on the tools I should use?"
            )
            b1 = parsed.get(
                "default_boundary_1", "Strictly follow the user's constraints."
            )
            c1 = parsed.get(
                "default_criteria_1", "Output meets all explicitly stated requirements."
            )

        except Exception as e:
            # Fallback if LLM fails
            q1 = "Could you clarify any specific constraints or boundaries for this task?"
            q2 = "How should I verify that this task is successfully completed?"
            b1 = "Only operate within the scope of the request."
            c1 = "Task completes without errors."

        if HAS_RICH:
            # 2. Ask the dynamic questions
            ans1 = Prompt.ask(f"[yellow]Q1: {q1}[/yellow]")
            ans2 = Prompt.ask(f"[yellow]Q2: {q2}[/yellow]")

            while True:
                console.print("\n[bold green]📝  Draft Goal Contract[/bold green]")

                boundaries = [b1, f"User clarification: {ans1}"]
                criteria = [c1, f"User clarification: {ans2}"]

                console.print("Boundaries:")
                for b in boundaries:
                    console.print(f"  - {b}")

                console.print("Acceptance Criteria:")
                for c in criteria:
                    console.print(f"  - {c}")

                approve = Prompt.ask(
                    "\n[bold]Do you approve this Goal Contract?[/bold] (y/n/edit)",
                    choices=["y", "n", "edit"],
                    default="y",
                )

                if approve.lower() == "y":
                    return GoalContract(
                        original_request=initial_request,
                        clarified_boundaries=boundaries,
                        acceptance_criteria=criteria,
                        is_approved=True,
                    )
                elif approve.lower() == "edit":
                    b1 = Prompt.ask("[cyan]Edit default boundary[/cyan]", default=b1)
                    c1 = Prompt.ask("[cyan]Edit default criteria[/cyan]", default=c1)
                    continue
                else:
                    return GoalContract(
                        original_request=initial_request,
                        clarified_boundaries=[],
                        acceptance_criteria=[],
                        is_approved=False,
                    )
        else:
            print("\n🎯  Requirement Elicitation Phase")
            print(f"Original Request: {initial_request}")

            ans1 = input(f"Q1: {q1}\nYour answer: ")
            ans2 = input(f"Q2: {q2}\nYour answer: ")

            print("\n📝  Draft Goal Contract")

            boundaries = [b1, f"User clarification: {ans1}"]
            criteria = [c1, f"User clarification: {ans2}"]

            print("Boundaries:")
            for b in boundaries:
                print(f"  - {b}")

            print("Acceptance Criteria:")
            for c in criteria:
                print(f"  - {c}")

            approve = input("\nDo you approve this Goal Contract? (y/n) [y]: ") or "y"

            return GoalContract(
                original_request=initial_request,
                clarified_boundaries=boundaries,
                acceptance_criteria=criteria,
                is_approved=(approve.lower() == "y"),
            )


class MacCliHitlAdapter(IHumanIntervention):
    """
    Mac-native terminal interface for Human-In-The-Loop.
    Uses Rich for beautiful prompts and formatting.
    """

    def __init__(self):
        self._last_feedback = None

    def request_decision(self, node: MctsNode, reason: str) -> HumanDecision:
        self._last_feedback = None

        # Ring terminal bell (Mac native behavior)
        sys.stdout.write("\a")
        sys.stdout.flush()

        if HAS_RICH:
            console.print("\n[bold red]⚠️  系统拦截执行[/bold red]")
            console.print(f"[yellow]原因：[/yellow] {reason}")

            if node.proposed_tool_calls:
                console.print("\n[cyan]拟执行操作：[/cyan]")
                for call in node.proposed_tool_calls:
                    console.print(f"  - {call.get('name')}({call.get('args')})")

            console.print("\n[bold]选择操作：[/bold]")
            console.print("  [green]1. 批准（继续）[/green]")
            console.print("  [yellow]2. 修剪并重定向（给 AI 提示）[/yellow]")
            console.print("  [blue]3. 覆盖（提供确切答案）[/blue]")
            console.print("  [red]4. 中止（停止任务）[/red]")

            choice = Prompt.ask(
                "Select option", choices=["1", "2", "3", "4"], default="1"
            )

            if choice == "1":
                return HumanDecision.APPROVE
            elif choice == "2":
                self._last_feedback = Prompt.ask(
                    "[yellow]Enter your hint for the AI[/yellow]"
                )
                return HumanDecision.PRUNE
            elif choice == "3":
                self._last_feedback = Prompt.ask(
                    "[blue]Enter the exact result/answer[/blue]"
                )
                return HumanDecision.OVERRIDE
            else:
                return HumanDecision.ABORT
        else:
            print(f"\n⚠️  Harness Intercepted Execution")
            print(f"Reason: {reason}")

            if node.proposed_tool_calls:
                print("\nProposed Actions:")
                for call in node.proposed_tool_calls:
                    print(f"  - {call.get('name')}({call.get('args')})")

            print("\n选择操作:")
            print("  1. 批准 (继续)")
            print("  2. 修剪并重定向 (给 AI 提示)")
            print("  3. 覆盖 (提供确切答案)")
            print("  4. 中止 (停止任务)")

            choice = input("Select option [1/2/3/4] (default 1): ").strip() or "1"

            if choice == "1":
                return HumanDecision.APPROVE
            elif choice == "2":
                self._last_feedback = input("Enter your hint for the AI: ")
                return HumanDecision.PRUNE
            elif choice == "3":
                self._last_feedback = input("Enter the exact result/answer: ")
                return HumanDecision.OVERRIDE
            else:
                return HumanDecision.ABORT

    def get_human_feedback(self) -> Optional[str]:
        return self._last_feedback
