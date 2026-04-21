# Hermes Agent × MCTS+HITL 融合规格（实施合同）

> **状态：** 已冻结 · 本文档是实施阶段的合同性依据，任何偏离必须在本文件登记修订后再执行。
>
> **关联文档：** [mcts_hitl_architecture_design.md](./mcts_hitl_architecture_design.md)（愿景与专家评审）

---

## 1. 背景与目标范围

### 1.1 愿景
让 `hermes-agent` 成为 Agent-as-a-Platform：除了已有的 ReAct 能力，还能胜任
（A）**股票研判**——并行假设+证据聚合；
（B）**嵌套代码 Agent**——安全调用 Claude Code / OpenCode；
（C）**文档/PPT 生成**——多风格分支+择优合并。

### 1.2 本次融合不做的事
- **不替换**父 `AIAgent` 的主 system prompt
- **不替代**其 ReAct 主循环、IterationBudget、ContextCompressor、provider fallback 链
- **不平行重建** hermes 已有的 `approval.py` / `tirith_security` / `process_registry` / `checkpoint_manager` / `delegate_tool` / `skills_hub` / `usage_pricing`

### 1.3 本次融合要做的事
- MCTS+HITL 以一个**新工具** `mcts_delegate` 的形式加入 hermes 工具注册表，由父 AIAgent 按需调用
- 复用上述基础设施，通过薄适配器接入 `architecture/contracts.py` 契约
- 提供 git worktree 级别的分支隔离，支持真并行
- 提供分层 HITL：L1 操作级（approval.py）/ L2 节点级 / L3 任务级
- 落地预算感知 UCB，以 `usage_pricing` 驱动的 cost 惩罚项

---

## 2. 核心架构决策（冻结）

| # | 决策 | 理由 |
|---|---|---|
| D1 | MCTS 以 `mcts_delegate` 工具形态嵌入 hermes，而非平行引擎 | 心智一致、UX 统一、父 AIAgent 天然作为顶层控制面 |
| D2 | 分支隔离采用 **git worktree**，存放于 `~/.hermes/worktrees/{sha256(cwd)[:16]}/mcts_{root}_{branch}` | 支持并行 execute；轻量；天然 diff；不污染工作目录 |
| D3 | 非 git 工作目录：自动 `git init`，同时写 `.hermes_auto_git` 标记用于清理识别 | 保证隔离可用；边界可追溯 |
| D4 | WINNER 分支合并采用 **HITL diff 预览 → 用户确认 → apply_patch** | 安全优先；避免自动合并带来的 silent 覆盖 |
| D5 | **需求澄清**（任务进行中的单点问答）由父 AIAgent + `clarify_tool` 负责；**目标契约评审**（任务开始前的结构化闸门）由 `mcts_delegate` 入口负责（见 D9） | 区分两种职责：clarify_tool 是进行时问答，契约评审是开工前锁定可测验收标准 |
| D6 | 审批采用**批量模式**：`mcts_delegate` 入口把"接下来一批操作属于本 MCTS 任务"登记给 `approval.py`，用户可选 "approve all for this MCTS task"，任务结束自动失效 | 避免审批轰炸 |
| D7 | `budget_usd` 为任务硬上限，超出强制熔断返回 | 成本可控，父 AIAgent 可决策续费 |
| D8 | `mcts_delegate` 是独立的 delegate 类别，**不占用** `delegate_task` 的 `MAX_DEPTH=2` 配额 | MCTS 内仍可嵌套 `nested_coding_agent` |
| D9 | `mcts_delegate` 入口保留 **GoalContractReviewer** 阶段（opt-in，参数 `review_goal=True`）：LLM 分析 goal → 起草 `GoalContract`（含可机械验证的 acceptance_criteria）→ HITL 展示草案 → 用户 Approve / Edit / Reject；拒绝即 abort | 恢复 MVP 的目标契约闸门；让 Evaluator 的 `check_acceptance` 有机械判定锚点；批量审批 UI 前置到这一步，用户一次性通过契约 + 审批策略 |

---

## 3. 目录结构与文件清单

### 3.1 `architecture/` 变更总览

| 文件 | 动作 | 说明 |
|---|---|---|
| `contracts.py` | **改** | 见 §4.1 |
| `workflow.py` | **改** | 变为 `mcts_delegate` 内部入口，修终止条件 |
| `real_engine.py` | **大改** | 去除自调 LLM；通过 `BranchExecutor` 驱动；修 UCB/并发/PENDING bug |
| `evaluator_adapter.py` | **改** | 修 `MctsNode.COMPLETED` 拼写、子 Agent 隔离、并发锁、评估时机 |
| `harness_monitor.py` | **大改** | L1 改调 `approval.py` + `tirith_security`；L2 保留节点级判断 |
| `cli_hitl_adapter.py` | **改** | `os.system` → `subprocess.run([...])`；新增 diff 预览模式 |
| `mock_engine.py` | **保留** | 单元测试继续使用 |
| `test_run.py` | **保留/扩展** | 回归测试 |
| `llm_provider_adapter.py` | **删** | 走父 AIAgent 主路径 |
| `tool_executor_adapter.py` | **删** | 同上 |
| `cli_elicitor_adapter.py` | **改 + 重命名 → `goal_contract_reviewer.py`** | 职责收窄为"目标契约评审"（D9）；不再承担对话式澄清；改为单次 LLM 起草契约 + HITL 审查 + 产出可测 `acceptance_criteria` |

### 3.2 新增文件

| 路径 | 职责 |
|---|---|
| `architecture/branch_executor.py` | 持有/复用 `AIAgent` 实例；`rehydrate(node) → advance_one_step() → writeback(node)` |
| `architecture/worktree_manager.py` | worktree 生命周期；patch 生成；安全清理 |
| `architecture/parallel_hypothesis_engine.py` | 单层 b=N 并行假设 + 聚合打分（管线 A） |
| `architecture/mcts_rollback_engine.py` | 带 worktree 回滚的深度 MCTS（管线 B/C） |
| `architecture/task_type_router.py` | 按 `task_type` 选引擎 |
| `architecture/budget_hook.py` | hook AIAgent API 完成点，累加 `cost_usd` 至当前活跃 node |
| `architecture/approval_batch.py` | 批量审批上下文管理器，封装 `approval.py` |
| `tools/mcts_delegate_tool.py` | 工具注册入口；参数校验；父 AIAgent 引用注入 |
| `tools/nested_coding_agent_tool.py` | 通过 `process_registry` PTY 跑 Claude Code / OpenCode（阶段 3 落地） |
| `tools/stock_cli_tool.py` | 股票 CLI 包装（阶段 1.4，待用户交付 CLI） |

---

## 4. 接口契约

### 4.1 `contracts.py` 修订

```python
class TaskType(Enum):
    AUTO = "auto"
    STOCK = "stock"           # ParallelHypothesisEngine, isolation=none
    CODE = "code"             # MctsRollbackEngine, isolation=worktree
    DOC = "doc"               # MctsRollbackEngine, isolation=worktree
    RESEARCH = "research"     # ParallelHypothesisEngine, isolation=none（通用研究型）

class Isolation(Enum):
    NONE = "none"
    WORKTREE = "worktree"
    DOCKER = "docker"         # 预留，本期不实现

@dataclass
class MctsNode:
    # 既有字段保持
    id: str
    parent_id: Optional[str]
    history: List[Dict[str, Any]]
    proposed_tool_calls: List[Dict[str, Any]]
    score: float
    status: NodeStatus
    critic_reason: Optional[str] = None
    visit_count: int = 0
    value: float = 0.0
    children: List["MctsNode"] = field(default_factory=list)
    parent: Optional["MctsNode"] = None
    # 新增
    branch_id: str = ""                          # 贯穿 task_id/worktree 命名
    worktree_path: Optional[str] = None          # None 表示 isolation=none
    cost_usd: float = 0.0                        # 本节点消耗
    cumulative_cost_usd: float = 0.0             # 含所有子孙
    merge_patch: Optional[str] = None            # WINNER 节点携带的 diff
```

- 删 `ILlmProvider`、`IToolExecutor`
- **保留并改造** `IRequirementElicitor` → 方法签名修订为：
  ```python
  class IRequirementElicitor(Protocol):
      def review_goal(self, goal: str, task_type: TaskType) -> GoalContract:
          """
          接收父 AIAgent 传入的 goal 字符串，调用 LLM 起草 boundaries 与
          **可机械验证的** acceptance_criteria；通过 IHumanIntervention
          展示契约草案并等待 Approve / Edit / Reject。
          Reject 时返回 GoalContract(is_approved=False)。
          """
  ```
  - `acceptance_criteria` 要求为**可机械判定**的断言（文件存在、命令退出码、数值阈值等），非自由文本
  - 唯一实现放在 `architecture/goal_contract_reviewer.py`（由 `cli_elicitor_adapter.py` 改造而来）
- 保留 `IMctsEngine`、`IEvaluator`、`IHarnessMonitor`、`IHumanIntervention`
- 新增 `IBranchExecutor`（见 §4.2）

### 4.2 `IBranchExecutor` 协议

```python
class IBranchExecutor(Protocol):
    def advance(self, node: MctsNode, goal: str, max_steps: int) -> None:
        """基于 node.history rehydrate 一个 AIAgent，推进至多 max_steps 步
        ReAct，把新 messages / tool_calls / cost 写回 node。"""

    def execute_pending(self, node: MctsNode) -> None:
        """对 PENDING 节点执行其 proposed_tool_calls；在 worktree 内运行。"""
```

### 4.3 `mcts_delegate` 工具 Schema

```python
{
    "name": "mcts_delegate",
    "description": "Run a tree-search + HITL task with parallel hypothesis branches.",
    "parameters": {
        "goal": "string",                        # required
        "task_type": "auto|stock|code|doc|research",
        "budget_usd": "number (default 1.0)",
        "max_branches": "integer (default 3)",
        "max_depth": "integer (default 5)",
        "max_iterations": "integer (default 20)",
        "isolation": "none|worktree|auto",
        "approve_all_dangerous": "boolean (default false)",  # 对应 D6 的批量审批
        "review_goal": "boolean (default true)",             # 对应 D9 的目标契约评审闸门
    }
}
```

返回值结构（JSON 字符串）：

```json
{
  "status": "COMPLETED | PRUNED | ABORTED | BUDGET_EXCEEDED",
  "summary": "人类可读总结",
  "artifacts": [{"path": "...", "description": "..."}],
  "cost_usd": 0.47,
  "merged": true,
  "merge_patch_preview": "...",
  "diagnostics": "若 stuck 则附诊断"
}
```

---

## 5. 调用链时序

### 5.1 父 AIAgent 调用 `mcts_delegate` 的完整流程

```
用户 → 父 AIAgent (ReAct 主循环)
  │
  ├─ [可选] clarify_tool 澄清模糊需求
  │
  ├─ tool_call: mcts_delegate(goal, task_type, budget_usd, approve_all_dangerous, review_goal)
  │    │
  │    ├─ [若 review_goal=true] GoalContractReviewer.review_goal(goal, task_type):
  │    │    ├─ LLM 起草 boundaries + 可测 acceptance_criteria
  │    │    ├─ cli_hitl_adapter.preview_contract_and_confirm(draft):
  │    │    │    ├─ 同屏展示"Approve all dangerous for this task"复选（合并 D6 UI）
  │    │    │    └─ 用户 Approve / Edit / Reject
  │    │    └─ Reject → 立即返回 status=ABORTED，不进入 MCTS
  │    ├─ [若 review_goal=false] GoalContract 直接从 tool args 构造（无 criteria）
  │    │
  │    ├─ approval.py: 注册 batch 会话（使用契约评审阶段收集的 approve_all_dangerous 意愿）
  │    ├─ WorktreeManager.init_root()  # 准备根 worktree（或 isolation=none 时 skip）
  │    ├─ TaskTypeRouter.pick_engine(task_type) → Engine
  │    │
  │    ├─ Engine.run(goal, budget):
  │    │    ├─ Selection (UCB with cost penalty)
  │    │    ├─ Expansion (ThreadPool LLM 并发，纯推理)
  │    │    ├─ Execution (per-branch AIAgent in worktree; 并行)
  │    │    │    ├─ BranchExecutor.advance(node) → 产生 tool_calls/history
  │    │    │    ├─ HarnessMonitor.check_thresholds(node):
  │    │    │    │    ├─ L1: approval.py (若 batch=on 则复用白名单)
  │    │    │    │    ├─ L1: tirith_security.check_command_security
  │    │    │    │    └─ L2: 节点级 score/depth/cost 判定
  │    │    │    └─ 触发 → cli_hitl_adapter.request_decision (APPROVE/PRUNE/OVERRIDE/ABORT)
  │    │    ├─ Evaluation (critic subagent, 只读最小工具集)
  │    │    ├─ Backpropagation (value + cost)
  │    │    └─ budget_hook: 累计 cost_usd，超 budget_usd 触发 L3 HITL
  │    │
  │    ├─ WINNER 选出 → WorktreeManager.generate_patch(winner.worktree_path)
  │    ├─ cli_hitl_adapter.preview_diff_and_confirm(patch)
  │    │    └─ 用户 y → apply_patch 到 main CWD；n → 丢弃
  │    ├─ WorktreeManager.cleanup(all_branches)  # 包括 LOSER
  │    ├─ approval.py: 销毁 batch 会话
  │    └─ return JSON 结果
  │
  └─ 父 AIAgent 继续 ReAct 或结束
```

### 5.2 管线 A（isolation=none）的简化流程

无 worktree 相关步骤；Execution 阶段每分支仍起独立 AIAgent，但 CWD 共享 main；工具集只允许只读操作（`web_search`, `read_file`, `stock_cli`）；不产生 patch，`merged=false` 直接返回 summary。

---

## 6. 隔离与回滚（Worktree 细节）

### 6.1 路径约定

- **根路径：** `~/.hermes/worktrees/{sha256(abs(cwd))[:16]}/`
- **分支路径：** 上述根路径下 `mcts_{root_id}_{branch_id}/`
- **分支命名：** `mcts-{root_id}-{branch_id}` 作为 git 分支名
- **根元数据：** 根路径下 `meta.json` 记录 main CWD、创建时间、任务 ID、非 git 自动 init 标记

### 6.2 生命周期

| 阶段 | 动作 |
|---|---|
| 入口 | 检测 CWD 是否 git；非 git 则 `git init` + `touch .hermes_auto_git` + 首次 `git add -A && git commit -m "hermes auto-init"` |
| 分支创建 | `git worktree add -b mcts-{root}-{branch} ~/.hermes/worktrees/.../mcts_{root}_{branch} HEAD` |
| 分支执行 | 所有工具调用 CWD 强制指向分支 worktree 路径；`task_id=f"mcts_{root}_{branch}"` |
| 分支结束（LOSER） | `git worktree remove --force <path>` + `git branch -D mcts-{root}-{branch}` |
| 分支结束（WINNER） | `git -C <path> add -A && git diff --cached HEAD > patch` → 交由 HITL 预览 |
| 合并确认 | 用户 y → `git apply --3way patch` 到 main CWD；然后同 LOSER 清理 |
| 合并拒绝 | 同 LOSER 清理；返回 `merged=false` 含 `merge_patch_preview` 供父 AIAgent 决策 |
| 异常退出 | `atexit` 注册清理；`~/.hermes/worktrees/` 定期扫孤儿目录（>24h 且无对应 task）|

### 6.3 并发安全

- 多分支同时 execute：每分支独立 worktree，物理无共享 → 无 FS 竞争
- process_registry 的 task_id 已按分支区分 → 进程不串
- `_last_resolved_tool_names` 全局变量（delegate_tool）竞态：`BranchExecutor` 构造子 AIAgent 时加 `threading.Lock`
- 同 main CWD 多 MCTS 任务并发：root_id 不同，路径不撞

### 6.4 非 git 降级

- 检测：`git rev-parse --is-inside-work-tree` 退出码非 0
- 行为：`git init` + 写 `.hermes_auto_git`（内容含时间戳和 hermes 版本）+ 首次全量 commit
- 清理提示：任务结束时若检测到 `.hermes_auto_git`，向用户提示"此目录由 hermes 自动转为 git 仓库，如不需要可删除 `.git/` 和 `.hermes_auto_git`"
- **不自动删** `.git`：用户可能后续受益

---

## 7. HITL / 审批分层

### 7.1 三层架构

| 层 | 触发点 | 实现 | UI |
|---|---|---|---|
| **L1 操作级** | 单次工具调用（危险命令、可疑路径、SSRF URL） | `approval.py` + `tirith_security` + `path_security` + `url_safety`（既有） | hermes 原生审批 CLI |
| **L2 节点级** | 单个 MctsNode：分数低 / 深度超阈 / 本节点 cost 异常 | `DefaultHarnessMonitor` 重写 | `cli_hitl_adapter.request_decision` 四选一 |
| **L3 任务级** | 整棵树：迷路 / 超预算 / 人类主动介入 | workflow 状态机；`diagnose_trajectory` | `cli_hitl_adapter.request_decision` + 诊断报告 |

### 7.2 批量审批模式（D6 + D9 协同）

**UI 前置到契约评审阶段：** 按 D9，批量审批选项**不再**等到首次危险命令触发时再弹出，而是**直接嵌入 GoalContractReviewer 的契约确认页**。用户一次性对两件事拍板：

```
┌─ Goal Contract Review ─────────────────────────────────┐
│ Original: <goal>                                       │
│ Boundaries:                                            │
│   - <b1>                                               │
│   - <b2>                                               │
│ Acceptance Criteria (mechanically verifiable):         │
│   - file://<path> exists and non-empty                 │
│   - exit_code(pytest tests/xxx) == 0                   │
│                                                        │
│ [ ] Approve all dangerous commands for this MCTS task  │ ← D6 复选
│                                                        │
│ [Approve]  [Edit]  [Reject]                            │
└────────────────────────────────────────────────────────┘
```

**入口注册：**
```python
# 在 mcts_delegate_tool.py 入口
from architecture.approval_batch import BatchApprovalSession

# approve_all_dangerous 优先取自契约评审页的复选；若 review_goal=false 则取 tool args
final_approve_all = (
    contract.approve_all_dangerous
    if review_goal else tool_args.get("approve_all_dangerous", False)
)

with BatchApprovalSession(
    task_label=f"MCTS: {goal[:60]}",
    approve_all_dangerous=final_approve_all,
) as batch:
    result = engine.run(...)
```

**实现要点：**
- `BatchApprovalSession.__enter__`：向 `approval.py` 的 per-session 白名单**注入一个 scope 标签**，设置 `auto_approve_within_scope=True`（当 `approve_all_dangerous=True` 时）
- 契约评审阶段用户未勾选时，首次遇到危险命令仍可在 L1 弹窗中选"Approve for this MCTS task"（作为后备通路），将其 hash 加入 scope 白名单
- `__exit__`：销毁 scope，白名单不持久化到 hermes 全局
- 若 `review_goal=false` 且 `approve_all_dangerous=False`：退化为标准行为，每次危险操作单独确认（hermes 现有 UX）

**L1 审批弹窗（后备通路）UI 增强：** 当契约评审未勾选批量审批、而任务进行中遇到首个危险命令时：
```
1. Approve once
2. Approve for this MCTS task    ← 新增（后备入口）
3. Approve permanently
4. Reject
5. Abort MCTS
```

---

## 8. 预算与成本核算

### 8.1 Hook 点

在 `BranchExecutor` 构造的子 AIAgent 的每次 API 完成回调处插入：
```python
# budget_hook.py
def on_api_complete(node: MctsNode, usage, model, provider, base_url):
    cost = estimate_usage_cost(model, usage, provider, base_url)
    node.cost_usd += cost.amount_usd
    # backpropagate 时同步 cumulative_cost_usd
```

### 8.2 UCB 公式

```
UCB(child) = exploitation + exploration - λ * cumulative_cost_ratio

exploitation = child.avg_value
exploration  = c * sqrt(log(parent.visit_count) / child.visit_count)   # 修正：parent 而非 global
cumulative_cost_ratio = child.cumulative_cost_usd / budget_usd
λ = 0.3 (初始值，可配置)
```

### 8.3 熔断

- `cumulative_cost_usd >= 0.8 * budget_usd`：触发 L3 HITL，提示"预算即将耗尽"，给用户 APPROVE（继续）/ PRUNE（返回当前最优）/ ABORT
- `cumulative_cost_usd >= budget_usd`：强制返回 status=BUDGET_EXCEEDED，携带当前最优节点

---

## 9. 三管线差异化配置

| 管线 | task_type | 引擎 | isolation | 工具集（分支内 AIAgent） | Evaluator |
|---|---|---|---|---|---|
| A 股票 | `stock` | ParallelHypothesisEngine（b=3, depth=1） | none | `stock_cli`, `web_search`, `read_file`, `memory` | TechnicalEvaluator（指标一致性 + 证据覆盖度） |
| A' 通用研究 | `research` | 同上 | none | `web_search`, `read_file`, `memory` | GenericCriticEvaluator（现有 subagent critic 修正版） |
| C 文档/PPT | `doc` | MctsRollbackEngine（b=2, depth=3） | worktree | 全部 + `skills/productivity/powerpoint/*` | DocStructureEvaluator（章节完整性 + 引用可达） |
| B 嵌套代码 | `code` | MctsRollbackEngine（b=2, depth=4） | worktree | 全部 + `nested_coding_agent` | CodeEvaluator（lint pass + 测试通过率，阶段 3 落地） |

`task_type="auto"`：由 `TaskTypeRouter` 按 goal 关键词启发式判别，默认回退 `research`。

---

## 10. 实施阶段与里程碑

### 阶段 1.0：P0 修复（与后续工作解耦，优先做）

| # | 文件:行 | 修复 |
|---|---|---|
| P0-1 | `evaluator_adapter.py:120` | `MctsNode.COMPLETED` → `NodeStatus.COMPLETED` |
| P0-2 | `cli_hitl_adapter.py:32` | `os.system(f"osascript ... {reason}")` → `subprocess.run([...])` |
| P0-3 | `workflow.py:67` + `real_engine.py:59` | 统一 system prompt 来源，去重 |
| P0-4 | `tool_executor_adapter.py:13-15` | 硬编码 task_id 改为接受参数（即便本文件最终要删，过渡期先修） |

**验收：** 现有 `test_run.py` 全绿 + 手跑 1 次 MVP 流程不出 AttributeError。

### 阶段 1.1：MCTS-as-Tool 骨架

**交付物：**
- `contracts.py` 按 §4.1 修订（含 `IRequirementElicitor.review_goal` 新签名）
- `architecture/branch_executor.py` 完成 `advance` / `execute_pending`
- `architecture/approval_batch.py` 完成 `BatchApprovalSession`
- `architecture/goal_contract_reviewer.py` 完成 `review_goal`（由 `cli_elicitor_adapter.py` 改造重命名而来，含可测 criteria 生成逻辑）
- `cli_hitl_adapter.py` 新增 `preview_contract_and_confirm`（含 D6 批量审批复选）
- `tools/mcts_delegate_tool.py` 注册至 hermes registry（含 `review_goal` 参数）
- `workflow.py` 改为工具内部入口；调用顺序：reviewer → BatchApprovalSession → engine
- 删除 `llm_provider_adapter.py` / `tool_executor_adapter.py`

**验收：** 父 AIAgent 在 CLI 会话中能通过 `mcts_delegate` 工具发起一个 dummy MCTS 任务，进入契约评审页，Approve 后返回 JSON；Reject 后返回 status=ABORTED。

### 阶段 1.2：ParallelHypothesisEngine + 通用研究 Demo

**交付物：**
- `architecture/parallel_hypothesis_engine.py`
- `architecture/task_type_router.py`（基础启发式）
- `architecture/evaluator_adapter.py` 修订后的 Generic 版
- `architecture/harness_monitor.py` 接入 `tirith_security` + `approval.py`
- `architecture/budget_hook.py` 基本 cost 累计

**验收：** `task_type="research"` 跑"A 方案 vs B 方案调研"demo，3 条并行假设，<60 秒返回，cost_usd 可核算。

### 阶段 1.3：Worktree + Diff 合并 HITL

**交付物：**
- `architecture/worktree_manager.py` 完整生命周期
- `architecture/mcts_rollback_engine.py`
- `cli_hitl_adapter.py` 新增 diff 预览模式
- 非 git 自动 init 与清理提示

**验收：** `task_type="doc"` 跑"写一份 PPT 草稿"demo，2 分支并行，用户预览 diff 后合并成功。

### 阶段 1.4：股票 CLI 接入（依赖用户交付）

**前置：** 用户提供 stock CLI 可执行路径 + `--help` 输出

**交付物：**
- `tools/stock_cli_tool.py`
- `TechnicalEvaluator`
- `task_type="stock"` 路由完成

**验收：** 对某只股票发起研判，输出看多/看空/中性三假设及聚合结论。

### 阶段 2.0：文档管线优化

- 挂载 `skills/productivity/powerpoint/` 与 `ocr-and-documents/`
- `DocStructureEvaluator`
- `search_and_load_skill` 元工具（若届时 hermes 仍无）

### 阶段 3.0：嵌套代码 Agent

- `tools/nested_coding_agent_tool.py`（Claude Code / OpenCode via PTY）
- `CodeEvaluator`（lint + test）
- 预算感知二次加固（嵌套 Agent 成本高）

---

## 11. 风险登记与未决问题

### 11.1 技术风险

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | `_last_resolved_tool_names` 全局变量在并发构造子 AIAgent 时竞态 | 分支工具集错配 | `BranchExecutor` 构造阶段加锁；长期建议向 hermes 提 PR 改为 threading.local |
| R2 | `ContextCompressor` 不感知 MCTS 分支：同一子 AIAgent 被多节点 rehydrate 时压缩状态错乱 | history 截断不一致 | 每分支用独立 AIAgent 实例；压缩触发时与 node.history 同步 |
| R3 | Worktree 残留累积占用磁盘 | 长期运行后几 GB | `atexit` + 定期扫描 `~/.hermes/worktrees/` 超 24h 孤儿目录 |
| R4 | 非 git 用户目录被静默 init | 用户意外多了 `.git` | `.hermes_auto_git` 标记 + 任务结束提示 |
| R5 | Claude Code / OpenCode CLI 行为变化 | 嵌套 Agent 失效 | 阶段 3 前做兼容性嗅探；失败时降级为 `delegate_task` |
| R6 | 审批批量模式误放行 | 安全风险 | scope 限于单个 `mcts_delegate` 调用周期；scope 结束白名单销毁；始终拦截 tirith 硬红线 |

### 11.2 未决问题（需后续讨论）

- **U1：** MCTS 任务失败后的产物保留策略——是否保留失败分支的 worktree 供用户手动检查？默认全清，提供 `--keep-on-failure` 开关？
- **U2：** WINNER 合并失败（`git apply` 冲突）时的回退：自动降级为 patch 文件写到用户目录，还是直接丢弃？
- **U3：** 父 AIAgent 多次连续调用 `mcts_delegate`：worktree root 是否复用 / 是否共享 cost 账本？
- **U4：** 股票 CLI 的并发上限——多假设同时打交易所 API 是否触发限流？

---

## 12. 修订记录

| 日期 | 修改 | 作者 |
|---|---|---|
| 2026-04-21 | 初版冻结 | hermes-agent 融合评审 |
| 2026-04-21 | 新增 D9（目标契约评审闸门）；恢复并改造 `IRequirementElicitor.review_goal`；`cli_elicitor_adapter.py` 改为重命名至 `goal_contract_reviewer.py`；`mcts_delegate` schema 加 `review_goal` 参数；§5.1 时序插入契约评审环节；§7.2 批量审批 UI 前置到契约评审页（L1 弹窗选项降级为后备通路）；阶段 1.1 交付物更新 | 设计 gap 补齐（clarify_tool vs elicitor 职责区分）|

---

## 附录 A：关键既有基础设施参考索引

| 模块 | 路径 | 关键 API |
|---|---|---|
| 主 Agent 循环 | `run_agent.py:526` `AIAgent` | `run_conversation`, `_interruptible_api_call`, `_invoke_tool`, `_execute_tool_calls` |
| 工具注册 | `tools/registry.py:49` + `model_tools.py:132` | `register`, `dispatch`, `handle_function_call`, `get_tool_definitions` |
| 子 Agent | `tools/delegate_tool.py:238` | `_build_child_agent`, `_run_single_child` |
| Checkpoint | `tools/checkpoint_manager.py:262` | `ensure_checkpoint`, `restore`, `list_checkpoints`, `diff` |
| 进程 | `tools/process_registry.py:286` | `spawn_local(use_pty=True)`, `kill_process` (PGID), `poll`, `wait` |
| 安全 | `tools/tirith_security.py:600` | `check_command_security` → `{action, findings, summary}` |
| 审批 | `tools/approval.py` | per-session 白名单 + aux LLM 自动审批 |
| 澄清 | `tools/clarify_tool.py` | 结构化多选 / 开放问题，平台 callback |
| 成本 | `agent/usage_pricing.py:481` | `estimate_usage_cost` → `CostResult.amount_usd` |
| 错误分类 | `agent/error_classifier.py:233` | `classify_api_error` → 14 类 + `retryable/should_compress/should_fallback` |
| 模型路由 | `agent/smart_model_routing.py:110` | `resolve_turn_route` |

## 附录 B：术语

- **MCTS 分支（Branch）**：MCTS 树上一条从根到叶的路径对应的状态切片，物理上映射为一个 git worktree 和一个 `task_id`
- **Rehydrate**：从 `MctsNode.history` 构造一个 AIAgent 实例的 messages，使其能继续 ReAct
- **L1/L2/L3 HITL**：见 §7
- **Batch Approval Scope**：`approval.py` 的作用域级白名单，随 `mcts_delegate` 生命周期建立与销毁
- **Goal Contract**：任务开工前由 `GoalContractReviewer` 起草、用户 HITL 审批通过的结构化契约，含 `original_request` / `clarified_boundaries` / `acceptance_criteria`（可机械验证）/ `is_approved`；作为 `IEvaluator.check_acceptance` 的判定锚点
- **契约评审 vs 澄清对话**：契约评审是**任务入口**的一次性结构化闸门（D9）；澄清对话是**任务进行中**的单点问答（hermes `clarify_tool` 负责）——两者不替代彼此
