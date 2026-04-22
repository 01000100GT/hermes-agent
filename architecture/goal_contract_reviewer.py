"""
GoalContractReviewer: analyzes goal strings and produces GoalContracts
with mechanically-verifiable acceptance_criteria.
Replaces the old MacCliElicitorAdapter with a stricter, D9-compliant reviewer.
"""

import sys
import json
import re
import logging
from typing import Optional

from .contracts import IRequirementElicitor, GoalContract
from .cli_utils import read_multiline_input

try:
    from rich.console import Console
    from rich.prompt import Prompt
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

logger = logging.getLogger(__name__)


class GoalContractReviewer(IRequirementElicitor):
    """
    D9 implementation: goal contract review gate.
    Produces boundaries + mechanically-verifiable acceptance_criteria,
    presents to user via HITL for Approve/Edit/Reject.
    """

    def __init__(self, parent_agent=None):
        self.parent_agent = parent_agent

    def review_goal(self, goal: str) -> GoalContract:
        """
        Analyze goal, draft verifiable criteria, present to user.
        Returns GoalContract (is_approved=False if user rejects).
        """
        sys.stdout.write("\a")
        sys.stdout.flush()

        if HAS_RICH:
            console.print("\n[bold magenta]🎯  Goal Contract Review[/bold magenta]")
            console.print(f"[cyan]Goal:[/cyan] {goal}")
            console.print("\n[dim]Analyzing goal to draft verifiable contract...[/dim]")
        else:
            print(f"\n🎯  Goal Contract Review")
            print(f"Goal: {goal}")
            print("\nAnalyzing goal to draft verifiable contract...")

        drafted = self._draft_contract(goal)
        return self._present_and_confirm(drafted)

    def clarify_goal(self, initial_request: str) -> GoalContract:
        """Legacy entry point — delegates to review_goal."""
        return self.review_goal(initial_request)

    def _draft_contract(self, goal: str) -> GoalContract:
        """Call LLM to produce a draft contract with verifiable criteria."""
        from agent.auxiliary_client import call_llm

        prompt = (
            "You are a Requirements Quality Analyst. Given this goal:\n"
            f'"{goal}"\n\n'
            "Produce a GoalContract as JSON with:\n"
            "1. \"boundaries\": list of 2-3 operational constraints (what the agent must stay within)\n"
            "2. \"criteria\": list of 2-3 MECHANICALLY VERIFIABLE acceptance criteria.\n"
            "   Each criterion MUST be checkable by one of:\n"
            "   - File existence: \"file://<path> exists and is non-empty\"\n"
            "   - Command exit code: \"exit_code(<command>) == 0\"\n"
            "   - String presence: \"<file> contains substring '<text>'\"\n"
            "   - Value threshold: \"word_count(<file>) >= N\"\n"
            "   - Tool success: \"web_search returned >= N results\"\n"
            "DO NOT use vague criteria like 'task completes successfully'.\n"
            "DO NOT refuse or hedge — assume the agent CAN perform the requested actions.\n\n"
            "Output ONLY the JSON object, no markdown fences:\n"
            '{"boundaries": [...], "criteria": [...]}'
        )

        try:
            response = call_llm(
                task="goal_contract_review",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            raw_content = response.choices[0].message.content or ""
            raw_content = re.sub(r'<think[\s\S]*?/think>', '', raw_content).strip()
            # Strip markdown code fences if present
            raw_content = re.sub(r'^```json\s*', '', raw_content)
            raw_content = re.sub(r'\s*```$', '', raw_content)

            json_match = re.search(r'\{[\s\S]*\}', raw_content)
            if json_match:
                parsed = json.loads(json_match.group(0))
                boundaries = parsed.get("boundaries", [
                    "Operate within the scope of the original goal."
                ])
                criteria = parsed.get("criteria", [
                    "Task completed without critical errors."
                ])
            else:
                raise ValueError("No JSON found in LLM response")

        except Exception as e:
            logger.warning(f"Contract drafting failed, using defaults: {e}")
            boundaries = ["Operate within the scope of the original goal."]
            criteria = ["Task completed without critical errors."]

        return GoalContract(
            original_request=goal,
            clarified_boundaries=boundaries,
            acceptance_criteria=criteria,
            is_approved=False,
        )

    def _present_and_confirm(self, draft: GoalContract) -> GoalContract:
        """Present draft contract to user for Approve/Edit/Reject."""
        if HAS_RICH:
            return self._present_rich(draft)
        else:
            return self._present_plain(draft)

    def _present_rich(self, draft: GoalContract) -> GoalContract:
        while True:
            console.print("\n[bold green]📝  Draft Goal Contract[/bold green]")
            console.print("[cyan]Boundaries:[/cyan]")
            for b in draft.clarified_boundaries:
                console.print(f"  - {b}")

            console.print("[cyan]Acceptance Criteria (mechanically verifiable):[/cyan]")
            for c in draft.acceptance_criteria:
                console.print(f"  - {c}")

            console.print(
                "\n[bold]Approve this Goal Contract?[/bold] "
                "(y = approve, n = reject, edit = modify)"
            )
            choice = Prompt.ask(
                "Select", choices=["y", "n", "edit"], default="y"
            )

            if choice == "y":
                draft.is_approved = True
                return draft
            elif choice == "n":
                console.print("[red]Goal Contract rejected. Task aborted.[/red]")
                return draft  # is_approved stays False
            elif choice == "edit":
                new_b = read_multiline_input("[cyan]Edit boundaries (one per line):[/cyan]")
                new_c = read_multiline_input("[cyan]Edit criteria (one per line):[/cyan]")
                if new_b.strip():
                    draft.clarified_boundaries = [
                        line.strip() for line in new_b.strip().split("\n") if line.strip()
                    ]
                if new_c.strip():
                    draft.acceptance_criteria = [
                        line.strip() for line in new_c.strip().split("\n") if line.strip()
                    ]
                continue

    def _present_plain(self, draft: GoalContract) -> GoalContract:
        while True:
            print("\n📝  Draft Goal Contract")
            print("Boundaries:")
            for b in draft.clarified_boundaries:
                print(f"  - {b}")
            print("Acceptance Criteria (mechanically verifiable):")
            for c in draft.acceptance_criteria:
                print(f"  - {c}")

            choice = input("\nApprove? (y/n/edit) [y]: ").strip().lower() or "y"

            if choice == "y":
                draft.is_approved = True
                return draft
            elif choice == "n":
                print("Goal Contract rejected. Task aborted.")
                return draft
            elif choice == "edit":
                new_b = input("Edit boundaries (one per line, blank to keep): ")
                new_c = input("Edit criteria (one per line, blank to keep): ")
                if new_b.strip():
                    draft.clarified_boundaries = [
                        l.strip() for l in new_b.strip().split("\n") if l.strip()
                    ]
                if new_c.strip():
                    draft.acceptance_criteria = [
                        l.strip() for l in new_c.strip().split("\n") if l.strip()
                    ]
                continue
            else:
                draft.is_approved = True
                return draft
