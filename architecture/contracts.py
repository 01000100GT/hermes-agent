"""
Core domain contracts for the Hermes MCTS+HITL architecture.
Designed with Simplicity First and Single Responsibility Principle.
These protocols define the boundaries for the new MCTS engine,
Harness (guardrails), and Human-In-The-Loop (HITL) interventions.
"""

from typing import Any, Dict, List, Optional, Protocol, Tuple
from enum import Enum
from dataclasses import dataclass, field


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


class TaskType(Enum):
    """Determines which engine strategy and isolation mode to use."""
    STOCK = "stock"
    CODE = "code"
    DOC = "doc"
    RESEARCH = "research"
    AUTO = "auto"


class Isolation(Enum):
    """Branch filesystem isolation strategy."""
    NONE = "none"
    WORKTREE = "worktree"


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
    critic_reason: Optional[str] = None
    
    # --- MCTS specific fields ---
    visit_count: int = 0
    value: float = 0.0  # Cumulative value for backprop
    children: List["MctsNode"] = field(default_factory=list)
    parent: Optional["MctsNode"] = None

    # --- Phase 1.1 fields (worktree/cost filled by later phases) ---
    branch_id: str = ""
    worktree_path: Optional[str] = None
    cost_usd: float = 0.0
    cumulative_cost_usd: float = 0.0
    merge_patch: Optional[str] = None

    @property
    def avg_value(self) -> float:
        return self.value / self.visit_count if self.visit_count > 0 else 0.0


class IRequirementElicitor(Protocol):
    """
    Contract for the goal contract review phase.
    Produces a GoalContract with mechanically-verifiable acceptance_criteria.
    """
    def review_goal(self, goal: str) -> GoalContract:
        """
        Analyze goal string, draft boundaries + verifiable criteria,
        present to user via HITL for Approve/Edit/Reject.
        Returns finalized GoalContract (is_approved=False if rejected).
        """
        ...

    def clarify_goal(self, initial_request: str) -> GoalContract:
        """Legacy entry point for backward compatibility. Delegates to review_goal."""
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
    def evaluate_step(self, node: MctsNode, goal: GoalContract) -> Tuple[float, str]:
        """Evaluate an intermediate step, returning a tuple of (score, reason)."""
        ...
        
    def check_acceptance(self, node: MctsNode, goal: GoalContract) -> bool:
        """Check if the final acceptance criteria are fully met."""
        ...


class IHumanIntervention(Protocol):
    """
    Contract for Human-In-The-Loop interaction.
    Single Responsibility: Request and receive decisions from the human operator.
    """
    def request_decision(self, node: MctsNode, reason: str, candidates: Optional[List[MctsNode]] = None) -> HumanDecision:
        """Ask the human what to do with the suspended node, optionally comparing with candidates."""
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

    def execute_node(self, node: MctsNode, goal: GoalContract) -> None:
        """
        Execute the proposed tool calls of a PENDING node.
        This must be called after harness checks. Updates node status and backpropagates the evaluation.
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

class ILlmProvider(Protocol):
    """
    Contract for LLM communication.
    Single Responsibility: Send prompts to an LLM and receive parsed responses (text + tool calls).
    """
    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], temperature: float) -> Any:
        """
        Generate a response from the LLM. 
        Returns an object containing content and tool_calls.
        """
        ...

class IToolExecutor(Protocol):
    """
    Contract for tool execution.
    Single Responsibility: Execute a tool by name with arguments and return the result string.
    """
    def execute(self, name: str, args: Dict[str, Any]) -> str:
        """Execute the requested tool and return the output."""
        ...

