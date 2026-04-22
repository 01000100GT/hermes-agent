"""
Mac-native terminal interface for Human-In-The-Loop.
Uses Rich for beautiful prompts and formatting, and native Mac OS notifications.
"""

import sys
import os
import subprocess
from typing import List, Optional, Tuple
from .contracts import IHumanIntervention, MctsNode, HumanDecision, GoalContract
from .cli_utils import read_multiline_input

try:
    from rich.console import Console
    from rich.prompt import Prompt
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

class MacCliHitlAdapter(IHumanIntervention):
    def __init__(self):
        self._last_feedback = None

    def request_decision(self, node: MctsNode, reason: str, candidates: Optional[List[MctsNode]] = None) -> HumanDecision:
        self._last_feedback = None

        # Ring terminal bell
        sys.stdout.write("\a")
        sys.stdout.flush()

        # Mac Native Notification (safe from shell injection via list args)
        try:
            subprocess.run(
                [
                    "osascript", "-e",
                    f'display notification "{reason}" with title "Hermes Agent HITL" subtitle "需要您的干预" sound name "Glass"'
                ],
                timeout=5,
                check=False,
            )
        except Exception:
            pass  # Notification is best-effort, never block the decision flow

        if HAS_RICH:
            console.print("\n[bold red]⚠️  系统拦截执行[/bold red]")
            console.print(f"[yellow]原因：[/yellow] {reason}")

            if candidates:
                from rich.table import Table
                table = Table(title="分支对比 (Top 3 Candidates)", show_header=True, header_style="bold magenta")
                table.add_column("ID", style="dim", width=12)
                table.add_column("得分", justify="center")
                table.add_column("操作预览", width=40)
                table.add_column("理由", width=30)

                sorted_candidates = sorted(candidates, key=lambda n: n.score, reverse=True)[:3]
                for c in sorted_candidates:
                    tool_desc = "None"
                    if c.proposed_tool_calls:
                        tool_desc = ", ".join([call.get("name", "") for call in c.proposed_tool_calls])
                    
                    table.add_row(
                        c.id,
                        f"{c.score:.2f}",
                        tool_desc,
                        c.critic_reason or "N/A"
                    )
                console.print(table)
            elif node.proposed_tool_calls:
                console.print("\n[cyan]拟执行操作：[/cyan]")
                for call in node.proposed_tool_calls:
                    console.print(f"  - {call.get('name')}({call.get('args')})")

            console.print("\n[bold]选择操作：[/bold]")
            console.print("  [green]1. 批准（继续）[/green]")
            console.print("  [yellow]2. 修剪并重定向（给 AI 提示）[/yellow]")
            console.print("  [blue]3. 覆盖（提供确切答案）[/blue]")
            console.print("  [red]4. 中止（停止任务）[/red]")

            choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="1")

            if choice == "1":
                return HumanDecision.APPROVE
            elif choice == "2":
                self._last_feedback = read_multiline_input("[yellow]Enter your hint for the AI[/yellow]")
                return HumanDecision.PRUNE
            elif choice == "3":
                self._last_feedback = read_multiline_input("[blue]Enter the exact result/answer[/blue]")
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
                self._last_feedback = read_multiline_input("Enter your hint for the AI: ")
                return HumanDecision.PRUNE
            elif choice == "3":
                self._last_feedback = read_multiline_input("Enter the exact result/answer: ")
                return HumanDecision.OVERRIDE
            else:
                return HumanDecision.ABORT

    def get_human_feedback(self) -> Optional[str]:
        return self._last_feedback

    # ------------------------------------------------------------------
    # D9: Contract preview with batch-approval checkbox (§7.2)
    # ------------------------------------------------------------------

    def preview_contract_and_confirm(
        self, contract: GoalContract
    ) -> Tuple[GoalContract, bool]:
        """
        Present GoalContract for user review.
        Returns (final_contract, approve_all_dangerous).
        approve_all_dangerous is the D6 batch-approval consent.
        """
        approve_all = False

        if HAS_RICH:
            from rich.panel import Panel
            from rich.text import Text

            boundary_text = "\n".join(f"  - {b}" for b in contract.clarified_boundaries)
            criteria_text = "\n".join(f"  - {c}" for c in contract.acceptance_criteria)

            panel_content = (
                f"[bold]Goal:[/bold] {contract.original_request}\n\n"
                f"[bold]Boundaries:[/bold]\n{boundary_text}\n\n"
                f"[bold]Acceptance Criteria (verifiable):[/bold]\n{criteria_text}\n\n"
                f"[dim]Batch-approve dangerous commands for this task?[/dim]"
            )
            console.print(Panel(panel_content, title="[bold]Goal Contract Review[/bold]", border_style="green"))

            # D6 batch approval checkbox
            batch_choice = Prompt.ask(
                "[bold]Approve all dangerous commands for this MCTS task?[/bold]",
                choices=["y", "n"],
                default="n",
            )
            approve_all = batch_choice == "y"

            main_choice = Prompt.ask(
                "\n[bold]Contract decision[/bold]",
                choices=["approve", "edit", "reject"],
                default="approve",
            )

            if main_choice == "approve":
                contract.is_approved = True
            elif main_choice == "edit":
                new_b = read_multiline_input("[cyan]Edit boundaries (one per line):[/cyan]")
                new_c = read_multiline_input("[cyan]Edit criteria (one per line):[/cyan]")
                if new_b.strip():
                    contract.clarified_boundaries = [
                        line.strip() for line in new_b.strip().split("\n") if line.strip()
                    ]
                if new_c.strip():
                    contract.acceptance_criteria = [
                        line.strip() for line in new_c.strip().split("\n") if line.strip()
                    ]
                contract.is_approved = True
            else:
                contract.is_approved = False
                console.print("[red]Goal Contract rejected. MCTS task aborted.[/red]")

        else:
            print("\n" + "=" * 60)
            print("GOAL CONTRACT REVIEW")
            print("=" * 60)
            print(f"Goal: {contract.original_request}")
            print("\nBoundaries:")
            for b in contract.clarified_boundaries:
                print(f"  - {b}")
            print("\nAcceptance Criteria (verifiable):")
            for c in contract.acceptance_criteria:
                print(f"  - {c}")

            batch = input("\nApprove all dangerous commands for this task? (y/n) [n]: ").strip().lower()
            approve_all = batch == "y"

            choice = input("\nContract decision (approve/edit/reject) [approve]: ").strip().lower() or "approve"
            if choice == "approve":
                contract.is_approved = True
            elif choice == "edit":
                new_b = input("Edit boundaries (one per line, blank to keep): ")
                new_c = input("Edit criteria (one per line, blank to keep): ")
                if new_b.strip():
                    contract.clarified_boundaries = [l.strip() for l in new_b.strip().split("\n") if l.strip()]
                if new_c.strip():
                    contract.acceptance_criteria = [l.strip() for l in new_c.strip().split("\n") if l.strip()]
                contract.is_approved = True
            else:
                contract.is_approved = False
                print("Goal Contract rejected. MCTS task aborted.")

        return contract, approve_all
