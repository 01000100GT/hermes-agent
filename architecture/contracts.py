"""
Core domain contracts for the Hermes MCTS+HITL architecture.
Designed with Simplicity First and Single Responsibility Principle.
These protocols define the boundaries for the new MCTS engine,
Harness (guardrails), and Human-In-The-Loop (HITL) interventions.
"""

from typing import Any, Dict, List, Optional, Protocol
from enum import Enum
from dataclasses import dataclass


class NodeStatus(Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    PRUNED = "PRUNED"
    COMPLETED = "COMPLETED"


class HumanDecision(Enum):
    APPROVE = "APPROVE"
    PRUNE = "PRUNE"
    OVERRIDE = "OVERRIDE"
    ABORT = "ABORT"


@dataclass
class GoalContract:
    """
    The explicitly confirmed final goal.
    This acts as the 'North Star' for the entire MCTS process.
    """
    original_request: str
    clarified_boundaries: List[str]
    acceptance_criteria: List[str]
    is_approved: bool = False

@dataclass
class MctsNode:
    """Represents a single state/thought branch in the MCTS tree."""
    id: str
    parent_id: Optional[str]
    history: List[Dict[str, Any]]  # Chat history for this branch
    proposed_tool_calls: List[Dict[str, Any]]
    score: float
    status: NodeStatus


class IRequirementElicitor(Protocol):
    """
    Contract for the requirement elicitation phase.
    Single Responsibility: Clarify vague requests into a concrete GoalContract with the user.
    """
    def clarify_goal(self, initial_request: str) -> GoalContract:
        """
        Engage with the user (or LLM + Human in loop) to lock down the boundaries and criteria.
        Returns the finalized and approved GoalContract.
        """
        ...

class IHarnessMonitor(Protocol):
    """
    Contract for the system guardrail.
    Single Responsibility: Determine if the current node violates safety/cost thresholds.
    """
    def check_thresholds(self, node: MctsNode) -> bool:
        """Returns True if human intervention is required."""
        ...
        
    def get_suspend_reason(self) -> str:
        """Returns the reason for suspension (e.g., 'Depth > 3', 'rm -rf detected')."""
        ...

class IEvaluator(Protocol):
    """
    Contract for node evaluation.
    Single Responsibility: Evaluate the progress of a node toward the goal, providing a score and feedback.
    """
    def evaluate_step(self, node: MctsNode, goal: GoalContract) -> float:
        """Evaluate an intermediate step, returning a score between 0.0 and 1.0."""
        ...
        
    def check_acceptance(self, node: MctsNode, goal: GoalContract) -> bool:
        """Check if the final acceptance criteria are fully met."""
        ...


class IHumanIntervention(Protocol):
    """
    Contract for Human-In-The-Loop interaction.
    Single Responsibility: Request and receive decisions from the human operator.
    """
    def request_decision(self, node: MctsNode, reason: str) -> HumanDecision:
        """Ask the human what to do with the suspended node."""
        ...
        
    def get_human_feedback(self) -> Optional[str]:
        """Get optional text feedback if the decision was PRUNE or OVERRIDE."""
        ...


class IMctsEngine(Protocol):
    """
    Contract for the MCTS execution engine.
    Single Responsibility: Manage the tree search and execution state transitions.
    """
    def step(self, current_node: MctsNode, goal: GoalContract) -> List[MctsNode]:
        """
        Execute one step of the current node (e.g., call LLM, run tools).
        Returns new child nodes. The 'goal' acts as the evaluation anchor.
        """
        ...

    def prune_and_redirect(self, node: MctsNode, feedback: str) -> None:
        """Handle human intervention to prune a branch and steer the search."""
        ...

    def apply_override(self, node: MctsNode, feedback: str) -> None:
        """Handle human intervention to provide the exact answer/result."""
        ...

    def diagnose_trajectory(self, node: MctsNode) -> str:
        """Diagnose why the agent is stuck and provide a human-readable summary and advice."""
        ...
