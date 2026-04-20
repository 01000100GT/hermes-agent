"""
Mac-native terminal interface for Requirement Elicitation.
Instead of hardcoding, it calls the LLM to analyze the request
and generate targeted clarification questions.
"""

import sys
from .contracts import IRequirementElicitor, GoalContract

try:
    from rich.console import Console
    from rich.prompt import Prompt
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

class MacCliElicitorAdapter(IRequirementElicitor):
    def clarify_goal(self, initial_request: str) -> GoalContract:
        sys.stdout.write("\a")  # Bell
        sys.stdout.flush()

        if HAS_RICH:
            console.print("\n[bold magenta]🎯  Requirement Elicitation Phase[/bold magenta]")
            console.print(f"[cyan]Original Request:[/cyan] {initial_request}")
            console.print("\n[dim]Analyzing request to generate clarification questions...[/dim]")

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
            '  "default_boundary_1": "A safe boundary that INCLUDES the user\'s explicit requests.",\n'
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
            raw_content = re.sub(r"<think>[\s\S]*?</think>", "", raw_content).strip()
            json_match = re.search(r"\{[\s\S]*\}", raw_content)
            if json_match:
                parsed = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found")

            q1 = parsed.get("q1", "Are there any specific formatting requirements?")
            q2 = parsed.get("q2", "Are there any constraints on the tools I should use?")
            b1 = parsed.get("default_boundary_1", "Strictly follow the user's constraints.")
            c1 = parsed.get("default_criteria_1", "Output meets all explicitly stated requirements.")

        except Exception as e:
            q1 = "Could you clarify any specific constraints or boundaries for this task?"
            q2 = "How should I verify that this task is successfully completed?"
            b1 = "Only operate within the scope of the request."
            c1 = "Task completes without errors."

        if HAS_RICH:
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
