HARNESS ENGINEERING CORE CONCEPTS: MCTS-BASED AGENT DELEGATION PATTERNS IN AI AGENT ARCHITECTURES

Technical Report -- Compiled April 2026


==============================================================================
SECTION 1: DEFINITION AND SCOPE OF HARNESS ENGINEERING AS A DISCIPLINE
==============================================================================

Harness Engineering is the systematic discipline of building reliable, observable, and controllable systems that govern the full lifecycle of AI agent operations. It encompasses prompt design, tool integration, safety guardrails, error recovery mechanisms, observability infrastructure, and multi-agent orchestration patterns. The discipline operates under a fundamental philosophy: infrastructure quality supersedes prompt engineering. Deterministic system controls are preferred over probabilistic behavioral guarantees for security, compliance, and operational reliability.

The scope of Harness Engineering extends across the entire task lifecycle rather than being confined to individual interaction turns. While traditional prompt engineering optimizes behavior within a single conversation turn, harness engineering ensures that every turn in an extended multi-step workflow operates within defined boundaries, maintains state consistency, and produces verifiable outcomes. Key responsibilities include:

  - Context Lifecycle Management: Bounded memory stores, adaptive compaction strategies,
    dual-memory architectures (persistent vs. session-scoped), and prefix-cache preservation.
  - Tool Integration Safety: Registry-based tool discovery, capability negotiation via MCP,
    permission hierarchies, and deterministic gates that prevent unauthorized operations.
  - Observability and Tracing: Structured logging, execution snapshots, cost tracking per turn,
    and audit trails for compliance verification.
  - Error Recovery and Retry Logic: Exponential backoff patterns, circuit breakers, graceful
    degradation when external services fail, and fallback strategies that preserve task state.
  - Multi-Agent Orchestration: Subagent spawning with isolated contexts, filtered tool access,
    consensus validation, and supervisor delegation patterns.


==============================================================================
SECTION 2: CORE ARCHITECTURAL LAYERS
==============================================================================

The harness architecture is organized into four distinct layers, each serving a specific responsibility within the agent control plane. This layered design enables separation of concerns and facilitates independent evolution of system capabilities.

Layer 1 -- Core (Main Conversation Context):
  The Core layer manages the finite conversation context that interfaces directly with the LLM. It handles message sequencing, token budgeting, and API call accounting. Since this context is both finite in capacity and costly per invocation, the harness must enforce strict attention to context efficiency. Every turn consumes tokens; therefore, the system tracks api_call_count, iteration budgets, and remaining context window to prevent resource exhaustion.

Layer 2 -- Instruction (Project Context and Operational Policy):
  The Instruction layer provides persistent project-level guidance through files such as CLAUDE.md, .claude/rules/, and MEMORY.md. These files establish operational policy, domain-specific conventions, and behavioral constraints that persist across sessions. Unlike the ephemeral Core context, Instruction-layer content is loaded once at session initialization and injected into the system prompt as a stable prefix, preserving cache efficiency throughout execution.

Layer 3 -- Extension (Domain Expertise and Deterministic Gates):
  The Extension layer implements domain-specific capabilities through skills, hooks, memory files, and custom agents. This layer provides deterministic gates that enforce safety constraints regardless of LLM behavior. Examples include file-locking mechanisms for concurrent memory writes, injection-scanning patterns that block prompt-injection payloads in memory entries, and capability negotiation protocols via MCP lazy discovery.

Layer 4 -- Orchestration (Multi-Agent Deliberation):
  The Orchestration layer manages agent teams, subagent spawning, consensus validation, and hierarchical delegation. It implements supervisor patterns where an orchestrator decides how to decompose requests among specialists, and coordination mechanisms such as Mixture-of-Agents aggregation where multiple models generate parallel responses that are synthesized by a stronger aggregator model.


==============================================================================
SECTION 3: SCAFFOLDING VS HARNESS DISTINCTION IN AGENT ARCHITECTURE
==============================================================================

A critical architectural distinction exists between scaffolding and harness, though both contribute to agent reliability. Understanding this boundary is essential for proper system design.

Scaffolding refers to the structural framework that enables an agent to operate within a defined environment. It includes:
  - The entry-point interface (CLI/TUI/Web) with standardized callback contracts
  - File-system scaffolding such as CLAUDE.md and project configuration files
  - Tool registry initialization and capability discovery protocols
  - Session setup procedures including memory loading, workspace resolution, and
    environment variable injection

The Scaffolding layer answers the question: "How does an agent begin operation?" It establishes the operational theater but does not govern runtime behavior.

Harness refers to the active control mechanisms that manage agent execution during its operational lifecycle. It includes:
  - Runtime context compaction strategies (adaptive token budget management)
  - Safety gates and permission hierarchies enforced at each tool invocation
  - Error recovery loops with exponential backoff and circuit breakers
  - Observability hooks for structured tracing and cost tracking
  - Human-in-the-loop interception points where execution is paused for user approval

The Harness layer answers the question: "How does an agent operate safely and reliably throughout its task lifecycle?" It governs behavior at every turn.

In architectural terms, scaffolding provides the stage; harness directs the performance upon it. Scaffolding is loaded once at initialization; harness operates continuously during execution.


==============================================================================
SECTION 4: THE REACT LOOP EVOLUTION AND EXTENDED REACT PATTERNS
==============================================================================

The ReAct (Reasoning-Acting) loop forms the foundational execution pattern for agentic systems. Its evolution from a simple iteration to sophisticated extended patterns reflects increasing demands placed on AI agents in production environments.

Basic ReAct Loop:
  The canonical ReAct loop follows a fixed iterative structure:
    while budget_remaining > 0:
        response = llm(messages, tools)
        if tool_calls present:
            for each call: result = execute(call.name, call.args)
                messages.append(tool_result(result))
            api_call_count += 1
        else:
            return response.content

This pattern implements a simple observe-think-act cycle where the LLM reasons about
the current state, selects tools to invoke, observes results, and iterates until no
further tool calls are required. The loop terminates when either the budget is exhausted
or the model produces a direct textual response (indicating task completion).

Extended ReAct Patterns:

  Extended Pattern A -- Adaptive Compaction within ReAct:
    As conversation history grows during extended multi-step tasks, context window pressure becomes critical. Adaptive compaction strategies intervene by summarizing older message segments while preserving critical state transitions. This maintains the agent's reasoning continuity without exceeding token limits. The compaction operates as a transparent middleware layer that rewrites historical messages into compressed representations before each new LLM call.

  Extended Pattern B -- Dual-Memory Augmentation:
    Standard ReAct loops rely entirely on conversation history for memory, which is both expensive and fragile. Extended patterns incorporate dual-memory architectures where persistent knowledge (learned facts, user preferences, tool behaviors) is stored in bounded file-backed stores separate from the conversation context. The MEMORY.md store maintains agent-learned observations up to a character budget (~2200 chars), while USER.md captures user-specific preferences (~1375 chars). Both are injected as frozen snapshots at session start and updated atomically via tool calls without disrupting the prefix cache.

  Extended Pattern C -- Contract-Guided ReAct:
    In this pattern, goal clarification precedes the first ReAct iteration. A GoalContract is drafted by an LLM subagent with mechanically verifiable acceptance criteria (file existence checks, command exit codes, string presence verification). The user reviews and approves or edits the contract before execution begins. During each ReAct cycle, a critic evaluator scores progress against these verifiable criteria rather than relying solely on the LLM's self-assessment.

  Extended Pattern D -- MCTS-Augmented ReAct:
    Rather than following a single linear reasoning path, MCTS-augmented agents explore multiple action branches simultaneously. At each decision point, the agent generates candidate tool calls, simulates outcomes via Monte Carlo rollouts, and selects the branch with highest expected value. This transforms the ReAct loop from a greedy sequential process into an exploratory search over a structured action space.


==============================================================================
SECTION 5: CONTEXT MANAGEMENT STRATEGIES
==============================================================================

Effective context management is the single most critical factor in sustaining long-running agent operations within finite token budgets and cost constraints. The following strategies are employed across modern harness architectures.

Strategy A -- Adaptive Compaction:
    As conversation history accumulates during multi-step task execution, the total message count approaches the model's context window limit. Adaptive compaction intervenes by identifying older, less critical message segments and replacing them with compressed summaries. The strategy preserves state-critical information (tool results that inform subsequent decisions, explicit user instructions) while discarding or summarizing intermediate reasoning traces. Compaction is triggered when remaining token budget falls below a configurable threshold, typically 20-30% of the total context window.

    Implementation considerations:
      - Summary quality directly affects downstream reasoning; poor compaction causes state loss.
      - The summary must maintain referential integrity (e.g., file paths, variable names) so that subsequent tool calls remain valid.
      - Compaction should be idempotent to prevent cumulative information degradation across multiple cycles.

Strategy B -- Dual-Memory Architecture:
    This architecture separates persistent knowledge from session-scoped conversation history. The MemoryStore class maintains two parallel stores with independent character budgets and separate file backings (MEMORY.md for agent observations, USER.md for user profile data). Both stores are loaded once at session initialization as frozen snapshots injected into the system prompt prefix. Mid-session updates write to disk atomically via temp-file-plus-rename patterns but do not modify the in-memory snapshot until next session start.

    Design principles:
      - Frozen snapshot pattern preserves the system prompt prefix cache for all turns.
      - Atomic file writes (temp + os.replace) prevent corruption from concurrent access.
      - Content scanning blocks injection/exfiltration payloads before entries are accepted.
      - Character-based limits (not token counts) ensure model-independent budgeting.

Strategy C -- Prefix Cache Optimization:
    The system prompt and instruction-layer files form a static prefix that the LLM cache can reuse across turns. By keeping this prefix unchanged throughout execution, each subsequent API call benefits from reduced latency and cost on cached prefix tokens. Only the conversation history (Core layer) grows per turn; the Instruction and Extension layers remain stable after initialization.


==============================================================================
SECTION 6: MCTS-BASED DELEGATION -- MONTE CARLO TREE SEARCH IN AGENT ARCHITECTURES
==============================================================================

Monte Carlo Tree Search (MCTS) represents a paradigm shift in how AI agents approach complex task decomposition and workflow optimization. Unlike simple ReAct loops that follow greedy sequential decision-making, MCTS-augmented harnesses explore structured action spaces with explicit evaluation of alternative branches.

6.1 Theoretical Foundation:
    MCTS is applied to agent architectures by treating the space of possible tool-call sequences as a search tree where:
      - Nodes represent states in the task execution (after a sequence of tool calls)
      - Edges represent individual tool invocations with their arguments
      - Leaf nodes are terminal states indicating either task completion or failure conditions

    The four phases of MCTS operate within each iteration cycle:
      Selection: Starting from the root node, traverse down the tree using an exploration/exploitation policy (typically UCB1) to identify a leaf node requiring expansion. The selection balances visiting high-value nodes (exploitation) against exploring under-visited branches (exploration).

      Expansion: Generate candidate tool calls at the selected leaf node by querying the LLM with the current state and available tools. Each candidate becomes a new child node in the search tree.

      Simulation (Rollout): Estimate the value of each newly created branch through lightweight evaluation rather than full execution. This is where efficiency gains are realized: instead of executing expensive tool calls, the harness uses fast approximations to score potential outcomes. In practice, this involves LLM-based process evaluators that assess whether a proposed action represents constructive progress toward acceptance criteria, combined with deterministic verification checks (e.g., confirming file existence).

      Backpropagation: Update node values up the tree from leaf to root, propagating evaluation scores so that parent nodes can make informed selection decisions in future iterations.

6.2 MCTS Node Structure:
    Each node in the search tree carries the following attributes:
      - id: Unique identifier for tree traversal and logging
      - state: Current conversation context up to this point
      - proposed_tool_calls: Candidate tool invocations at this decision point
      - score: Aggregated evaluation from simulation phase (0.0-1.0)
      - critic_reason: Natural language justification for the assigned score
      - visit_count: Number of times this node has been visited during selection
      - status: Node lifecycle state (OPEN, COMPLETED, FAILED, BLOCKED, SKIPPED)

6.3 Tool-Level MCTS Implementation:
    The mcts_delegate_tool implements MCTS as a callable tool that the main agent can invoke when facing complex multi-step problems. Key implementation characteristics include:
      - Budget enforcement via max_iterations parameter controls tree exploration depth.
      - Parallel branch execution using ThreadPoolExecutor for synchronous and asynchronous branches, enabling concurrent evaluation of independent sub-tasks.
      - A SubagentEvaluatorAdapter provides process-based scoring by spawning LLM critic agents that evaluate intermediate steps rather than requiring final outcomes. The evaluator uses a 40/60 weighted combination of LLM-provided scores (for nuanced progress assessment) and deterministic checks (for verifiable state changes).

6.4 Loop Topology Spectrum:
    Research classifies agent loop topologies along a spectrum from "Fixed pipeline" to "Full MCTS." The key distinction is that MCTS-based agents differ fundamentally from simple while-loop agents in cost, reliability, and failure modes. While fixed-pipeline agents execute predetermined sequences with minimal overhead but no adaptability, Full MCTS agents dynamically explore action spaces at the cost of increased API calls but with significantly higher robustness to unexpected conditions.

6.5 Integration with Delegation:
    Within multi-agent harness architectures, MCTS serves as the decision-making layer for delegation strategy selection. When a task is decomposed into sub-tasks, MCTS evaluates different assignment strategies (which subagent handles which subtask, in what order) and selects the configuration with highest expected value based on historical performance data and current resource constraints.


==============================================================================
SECTION 7: MULTI-AGENT HARNESS ARCHITECTURES AND SUBAGENT ORCHESTRATION PATTERNS
==============================================================================

Multi-agent harness architectures implement hierarchical delegation where a parent agent coordinates multiple specialized subagents, each operating within isolated contexts with restricted capabilities. This pattern is essential for managing complexity in long-running tasks that require diverse tool access patterns and domain expertise.

7.1 Subagent Orchestration Model:
    The delegate_tool module implements the primary subagent spawning mechanism. Each child agent receives:
      - A fresh conversation context (no parent history leakage)
      - An isolated task_id providing separate terminal sessions, file operation caches, and execution state
      - A restricted toolset with blocked tools always stripped from available capabilities
      - A focused system prompt constructed from the delegated goal and relevant workspace context

    The parent agent's context observes only the delegation call invocation and the final summary result. It never sees intermediate tool calls or reasoning traces produced by child agents, maintaining clean separation of concerns.

7.2 Safety Boundaries:
    Subagent capabilities are constrained through multiple mechanisms:
      - Blocked tools list (DELEGATE_BLOCKED_TOOLS) prevents recursive delegation (delegate_task), user interaction (clarify), shared memory writes (memory), cross-platform side effects (send_message), and arbitrary code execution (execute_code).
      - Maximum recursion depth is enforced at two levels (MAX_DEPTH = 2): parent (level 0) spawns children (level 1); grandchildren (level 2) are rejected.
      - Concurrent child limit defaults to three (_DEFAULT_MAX_CONCURRENT_CHILDREN), configurable via config.yaml or DELEGATION_MAX_CONCURRENT_CHILDREN environment variable, with a heartbeat mechanism that maintains parent activity during extended delegation periods.

7.3 Toolset Filtering:
    Subagents receive only non-composite toolsets (hermes-* prefixed and scenario-specific sets are excluded). The filtering logic excludes debugging, safe, delegation, MoA, and RL toolsets from subagent availability, ensuring children operate within a controlled capability envelope while retaining access to terminal, file, web search, code execution, and other domain-specific tools.

7.4 Mixture-of-Agents Integration:
    The mixture_of_agents_tool implements a two-layer aggregation architecture where multiple reference models (claude-opus-4.6, gemini-3-pro-preview, gpt-5.4-pro, deepseek-v3.2) generate parallel diverse responses at temperature 0.6, and an aggregator model synthesizes these into a single high-quality output at temperature 0.4. This pattern is particularly effective for complex mathematical proofs, advanced coding problems, multi-step analytical reasoning tasks, and scenarios requiring diverse domain expertise where single models show limitations.

7.5 Supervisor Pattern:
    The orchestrator acts as a supervisor that decides how to handle incoming requests by decomposing them into subtasks and assigning each to the most appropriate specialist agent. This pattern is evident in the workflow.py module's Plan Mode vs Normal Mode transition, where a Planner subagent determines task decomposition strategy before execution begins.


==============================================================================
SECTION 8: AGENT OPTIMIZATION HARNESSES -- THE VeRO FRAMEWORK
===============================================================================

The VeRO (Versioning, Execution, Reproducibility, Observation) framework represents a systematic approach to iterative agent improvement through structured edit-execute-evaluate cycles. This framework addresses the fundamental challenge of making agent behavior improvements measurable and reproducible rather than relying on anecdotal assessment.

8.1 Six Core Requirements:
    The VeRO framework mandates six structural requirements for any effective agent optimization harness:

      1. Versioning: Every configuration change, tool update, or prompt modification must be tracked as a distinct version. This enables rollback to known-good states and provides an audit trail linking behavioral changes to specific modifications.

      2. Budget Enforcement: Iteration limits are strictly enforced at the framework level, not left to individual agent self-regulation. The harness monitors api_call_count and remaining iteration budgets in real time, terminating execution when thresholds are exceeded regardless of agent state. This prevents runaway cost accumulation during optimization experiments.

      3. Permission Control: Tool access is governed by a permission hierarchy that can be adjusted per experiment version. Different optimization iterations may require different capability levels (e.g., read-only vs. full write access), and the harness enforces these constraints at invocation time rather than relying on prompt-level instructions.

      4. Reproducible Execution: Every test iteration must produce deterministic results given identical inputs. This requires capturing all environmental state variables, tool configurations, model parameters, and random seeds that influence execution outcomes. The harness serializes this state before each run to enable exact replication of failures for debugging purposes.

      5. Structured Tracing: All intermediate states during agent execution are captured in a structured format (JSON/JSONL) rather than unstructured logs. This enables post-hoc analysis, automated regression detection, and quantitative comparison between optimization iterations. Trace data includes message sequences, tool call arguments and results, timing information, and cost accumulation per turn.

      6. Standardized Observation Interface: The harness provides a uniform API for observing agent behavior across all execution modes (Plan mode, Normal mode, MCTS exploration). Observers receive the same event types regardless of which execution path is active, enabling consistent monitoring dashboards and automated alerting systems.


==============================================================================
SECTION 9: WORKFLOW OPTIMIZATION SURVEY FINDINGS -- ACG ABSTRACTION AND GDT/GPM TAXONOMY
===============================================================================

Recent research in agentic workflow optimization has converged on several unifying abstractions that provide a common vocabulary for comparing and improving agent architectures across different implementation approaches.

9.1 Agentic Computation Graph (ACG):
    The ACG serves as the primary unifying abstraction for representing agent workflows. In this model:
      - Nodes represent atomic actions (individual tool calls, LLM inference steps, or human intervention points)
      - Edges represent control and data dependencies between nodes
      - The graph structure captures both sequential execution order and parallelizable action groups

    This representation enables systematic optimization at multiple levels:
      Node-level optimization: Improving individual action efficiency (e.g., selecting cheaper tool variants, reducing LLM inference cost per node through prompt compression).
      Graph-level optimization: Restructuring the workflow topology to minimize critical path length, eliminate redundant computation paths, or introduce parallel execution opportunities.
      Joint optimization: Simultaneously optimizing both node implementations and graph structure using gradient-based methods or reinforcement learning approaches.

9.2 GDT/GPM Taxonomy:
    The General Decision Tree / Goal Planning Model taxonomy provides a classification framework for understanding how different agent architectures decompose complex tasks into executable sub-tasks. This taxonomy distinguishes between:
      - Greedy decomposition strategies that make locally optimal choices at each step (simple but fragile under distribution shift)
      - Lookahead strategies that evaluate multiple future states before committing to an action path (computationally expensive but more robust)
      - Hybrid approaches that combine fast greedy heuristics with periodic MCTS-based lookahead for critical decision points

9.3 MCTS Applications in Workflow Optimization:
    The survey identifies three distinct application patterns for MCTS within agent workflow optimization:
      Offline template search: Before execution begins, MCTS searches over possible workflow topologies to identify the most efficient action graph structure (as implemented in AFlow). This is computationally expensive but yields optimal templates that can be reused across similar tasks.
      Pre-execution generation: At task start, MCTS generates candidate sub-task decompositions and evaluates their expected success probability before committing to any execution path.
      In-execution editing: During active task execution, MCTS dynamically restructures the workflow graph when unexpected conditions arise (e.g., tool failures, contradictory results), enabling real-time adaptation without manual intervention.


==============================================================================
SECTION 10: PRACTICAL IMPLEMENTATION LESSONS FROM OPENDEV, CLAUDE CODE, AND SIMILAR SYSTEMS
===============================================================================

Drawing from analysis of OpenDev (arXiv 2603.05344), Claude Code architecture patterns, and the hermes-agent implementation, several practical lessons emerge for building production-grade agent harnesses.

Lesson 1 -- Configuration Hierarchy Matters:
    A four-tier configuration system (built-in defaults > environment variables > per-project config.yaml > global ~/.hermes/config.yaml) provides appropriate flexibility without overwhelming users with options. Lower tiers override higher tiers, enabling project-specific customization while maintaining sensible defaults for new projects.

Lesson 2 -- Shadow Git Snapshots Enable Safe Undo:
    The persistence layer implements shadow git snapshots that capture the complete file system state before each significant operation. This enables atomic rollback to any previous state without requiring explicit user intervention or risking partial writes that leave the workspace in an inconsistent state.

Lesson 3 -- Adaptive Compaction Requires State Preservation Guarantees:
    When implementing context compaction, preserving referential integrity of tool results is paramount. Summaries must retain file paths, variable names, and command outputs that subsequent tool calls depend on. Loss of this information causes cascading failures where the agent attempts to operate on files or variables that no longer exist in its understanding.

Lesson 4 -- Human-in-the-Loop Interception Requires Rich Presentation:
    The cli_hitl_adapter demonstrates that HITL interfaces must present sufficient context for meaningful human decisions. Simply asking "approve/deny" without showing proposed tool calls, their arguments, and the reasoning behind them leads to blind approvals or unnecessary rejections. Presenting top candidate branches with scores and critic reasons enables informed decision-making at a glance.

Lesson 5 -- Goal Contract Review Prevents Misalignment:
    The GoalContractReviewer pattern (arXiv 2603.05344, D9-compliant implementation) demonstrates that requiring mechanically verifiable acceptance criteria before execution begins dramatically reduces wasted computation on misaligned tasks. The LLM drafts a contract with specific file-existence checks and command-success verification; the user reviews and approves it before any agent work proceeds.

Lesson 6 -- Deterministic Gates Complement Probabilistic LLM Behavior:
    Security-sensitive operations should never rely solely on prompt-level instructions to prevent misuse. File-locking mechanisms, content scanning for injection patterns, blocked tool lists for subagents, and permission hierarchies provide deterministic enforcement that cannot be circumvented by adversarial prompts or model failures.

Lesson 7 -- Cost Awareness Must Be Built Into the Loop:
    Every ReAct iteration consumes API tokens. The harness must track api_call_count and iteration budgets at the framework level, not leave cost management to individual agent self-regulation which is unreliable under extended multi-step tasks where context pressure increases error rates.


==============================================================================
TECHNICAL DEBT
===============================================================================

The following technical debt items have been identified during this analysis of the harness engineering architecture:

TD-1 -- Mixed-Language UI Strings (cli_hitl_adapter.py, cli_elicitor_adapter.py):
    The HITL interface uses a mixture of Chinese and English strings throughout. This creates maintenance burden for non-Chinese-speaking developers and limits internationalization capability. All user-facing strings should be extracted to a localization layer with language selection at runtime.

TD-2 -- Hardcoded Model References (mixture_of_agents_tool.py):
    The reference model list and aggregator model are hardcoded as module-level constants rather than being configurable via the four-tier configuration hierarchy used elsewhere in the system. This creates inconsistency between how MoA behavior is controlled versus other harness components.

TD-3 -- Incomplete MCTS Rollout Implementation:
    The mcts_delegate_tool's SubagentEvaluatorAdapter uses lightweight LLM-based evaluation (2 max_iterations for critic agents) rather than true Monte Carlo rollouts with full tool execution. While this is a deliberate efficiency trade-off, the documentation does not clearly distinguish between approximate scoring and exact simulation, which could mislead users about the fidelity of MCTS branch selection.

TD-4 -- Memory Store Character Limit Without Token Awareness:
    The dual-memory architecture uses character-based limits (2200/1375 chars) for budgeting rather than token counts. While this provides model independence as a design goal, it creates unpredictable context window usage across different models with varying char-to-token ratios. For example, Chinese text typically has a much higher characters-per-token ratio than English text, meaning the effective memory capacity varies significantly by language.

TD-5 -- No Automated Regression Testing for Harness Behavior:
    The VeRO framework's requirement for reproducible execution is not paired with an automated regression test suite that validates harness behavior across configuration changes. Without such tests, modifications to context compaction, tool filtering, or delegation logic could silently degrade agent reliability without detection.

TD-6 -- Evaluator Adapter Dependency on delegate_tool Internal APIs:
    The SubagentEvaluatorAdapter imports _build_child_agent and _run_single_child from tools.delegate_tool, which are internal implementation details (prefixed with underscore). This creates a tight coupling between the architecture layer's evaluator and the tool layer's delegation internals. If the delegation API changes, both modules must be updated simultaneously, violating separation of concerns.

TD-7 -- Missing Circuit Breaker for External LLM Provider Failures:
    While retry logic with exponential backoff exists in mixture_of_agents_tool.py, there is no circuit breaker pattern that temporarily halts all external LLM calls when a provider consistently returns errors. During extended outages, this leads to continued budget consumption on failed retries rather than graceful degradation to cached or local processing.

TD-8 -- No Schema Validation for GoalContract Drafts:
    The GoalContractReviewer parses JSON from LLM responses using regex-based extraction (re.search(r'\{[\s\S]*\}', raw_content)) without validating the resulting structure against a schema. If an LLM produces malformed JSON that still contains a parseable object, invalid contract fields could silently propagate through the system with no error indication to the user.


==============================================================================
END OF REPORT
===============================================================================
