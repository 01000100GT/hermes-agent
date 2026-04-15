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
    MctsNode,
    HumanDecision,
)

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
        sys.stdout.write('\a')
        sys.stdout.flush()
        
        if HAS_RICH:
            console.print("\n[bold red]⚠️  Harness Intercepted Execution[/bold red]")
            console.print(f"[yellow]Reason:[/yellow] {reason}")
            
            if node.proposed_tool_calls:
                console.print("\n[cyan]Proposed Actions:[/cyan]")
                for call in node.proposed_tool_calls:
                    console.print(f"  - {call.get('name')}({call.get('args')})")
            
            console.print("\n[bold]Choose action:[/bold]")
            console.print("  [green]1. Approve (Proceed)[/green]")
            console.print("  [yellow]2. Prune & Redirect (Give AI a hint)[/yellow]")
            console.print("  [blue]3. Override (Provide exact answer)[/blue]")
            console.print("  [red]4. Abort (Stop task)[/red]")
            
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
            
            print("\nChoose action:")
            print("  1. Approve (Proceed)")
            print("  2. Prune & Redirect (Give AI a hint)")
            print("  3. Override (Provide exact answer)")
            print("  4. Abort (Stop task)")
            
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
