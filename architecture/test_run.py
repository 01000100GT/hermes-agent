"""
Run a simple end-to-end simulation of the MCTS + Harness + HITL workflow.
"""

import sys
import os

# Add parent to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from architecture.contracts import MctsNode, NodeStatus
from architecture.workflow import HermesMctsWorkflow
from architecture.adapters import DefaultHarnessMonitor, MacCliHitlAdapter
from architecture.real_engine import RealMctsEngine

try:
    from rich.console import Console

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def print_header(msg):
    if HAS_RICH:
        console.print(f"\n[bold green]{msg}[/bold green]\n")
    else:
        print(f"\n--- {msg} ---\n")


def print_status(msg, color="yellow"):
    if HAS_RICH:
        console.print(f"Task finished with status: [{color}]{msg}[/{color}]")
    else:
        print(f"Task finished with status: {msg}")


def print_msg(role, content):
    if HAS_RICH:
        console.print(f"  [cyan]{role}[/cyan]: {content}")
    else:
        print(f"  {role}: {content}")


def print_error(msg):
    if HAS_RICH:
        console.print(f"[red]{msg}[/red]")
    else:
        print(f"ERROR: {msg}")


def run_simulation():
    # Load environment so LLM API keys are available
    try:
        from hermes_cli.config import get_env_path, load_config
        from dotenv import load_dotenv
        import json

        _env_path = get_env_path()
        if _env_path.exists():
            load_dotenv(_env_path)
            print_header("Loaded Environment (.env)")
            print_msg("Path", str(_env_path))

        print_header("Loaded Config (config.yaml)")
        config = load_config()
        # Print model config specifically as it's most relevant
        model_cfg = config.get("model", {})
        custom_providers = config.get("custom_providers", [])

        if HAS_RICH:
            console.print(
                f"  [cyan]Main Model[/cyan]: {json.dumps(model_cfg, indent=2)}"
            )
            if custom_providers:
                console.print(
                    f"  [cyan]Custom Providers[/cyan]: {json.dumps(custom_providers, indent=2)}"
                )
        else:
            print(f"  Main Model: {json.dumps(model_cfg, indent=2)}")
            if custom_providers:
                print(f"  Custom Providers: {json.dumps(custom_providers, indent=2)}")

    except ImportError as e:
        print_error(f"Failed to load config/env: {e}")

    print_header("Starting MCTS + HITL Simulation")

    # 1. Initialize Dependency Injection
    # We set branching_factor=2 to generate two different thoughts and let the Critic evaluate them
    engine = RealMctsEngine(branching_factor=2)
    harness = DefaultHarnessMonitor()
    hitl = MacCliHitlAdapter()

    workflow = HermesMctsWorkflow(engine, harness, hitl)

    # 2. Create the root thought node
    root_node = MctsNode(
        id="root_0",
        parent_id=None,
        # history=[
        #     {
        #         "role": "user",
        #         "content": "思考如何写一个很好的缠中说禅理论的代码实现, 文章写入/Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/tmp/缠中说禅理论.md。",
        #     }
        # ],
        history=[
            {
                "role": "user",
                "content": "告诉我vue3是谁开发的.",
            }
        ],
        proposed_tool_calls=[],
        score=1.0,
        status=NodeStatus.PENDING,
    )

    # 3. Start execution loop
    final_node = workflow.run_task(root_node)

    print_header("Simulation Complete")
    if final_node:
        print_status(final_node.status.name)
        if HAS_RICH:
            console.print("Final History:")
        else:
            print("Final History:")
        for msg in final_node.history:
            print_msg(msg["role"], msg.get("content", str(msg.get("tool_calls", ""))))
    else:
        print_error("Task was aborted.")


if __name__ == "__main__":
    run_simulation()
