"""
Mac-native terminal interface for Human-In-The-Loop.
Uses Rich for beautiful prompts and formatting, and native Mac OS notifications.
"""

import sys
import os
from typing import List, Optional
from .contracts import IHumanIntervention, MctsNode, HumanDecision

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

        # Mac Native Notification
        os.system(f"osascript -e 'display notification \"{reason}\" with title \"Hermes Agent HITL\" subtitle \"需要您的干预\" sound name \"Glass\"'")

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
                self._last_feedback = Prompt.ask("[yellow]Enter your hint for the AI[/yellow]")
                return HumanDecision.PRUNE
            elif choice == "3":
                self._last_feedback = Prompt.ask("[blue]Enter the exact result/answer[/blue]")
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
