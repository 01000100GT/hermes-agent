from typing import Dict, Any
import json
from .contracts import IToolExecutor

class HermesToolExecutor(IToolExecutor):
    """
    Concrete implementation of IToolExecutor using the Hermes Agent's tool registry.
    """
    def execute(self, name: str, args: Dict[str, Any]) -> str:
        from model_tools import handle_function_call
        try:
            raw_result = handle_function_call(
                function_name=name,
                function_args=args,
                task_id="mcts_branch_exec",
                session_id="mcts_session",
            )
            return raw_result
        except Exception as tool_e:
            return json.dumps({"status": "error", "message": str(tool_e)})
