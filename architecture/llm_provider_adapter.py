from typing import List, Dict, Any
from .contracts import ILlmProvider

class HermesLlmProvider(ILlmProvider):
    """
    Concrete implementation of ILlmProvider using the Hermes Agent's call_llm.
    """
    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], temperature: float) -> Any:
        from agent.auxiliary_client import call_llm
        
        response = call_llm(
            task="mcts_step",
            messages=messages,
            tools=tools,
            temperature=temperature,
        )
        return response.choices[0].message
