# Hermes Agent-as-a-Platform: MCTS+HITL 架构融合与系统设计指南

## 1. 愿景与背景

本项目旨在将纯粹的、基于六边形架构的 MCTS (Monte Carlo Tree Search) + HITL (Human-In-The-Loop) 引擎融合到 `hermes-agent` 主项目中。目标是构建一个极具野心的 **Agent-as-a-Platform（智能体即平台）**，使其不仅能执行基础的文件操作，还能胜任股票研判、文档写作，甚至通过调用 Claude Code/OpenCode 等外部自治 Agent 来编写复杂代码。

经过两轮由 7 名世界级专家组成的评审委员会的深度拷问，我们确立了在非纯函数物理世界中落地 MCTS 树搜索算法的核心挑战与解决蓝图。

## 2. 核心挑战与专家评审意见

在将单一 LLM 脚本升级为高并发、高风险、多模态自治系统的过程中，专家们指出了以下致命问题：

1.  **系统架构师（状态污染与代理嵌套）：** 
    *   **问题：** 外部代理（如 Claude Code）执行后会修改文件系统或网络状态，当 MCTS 回溯到其他分支时，这些残留的物理状态会污染后续探索。
    *   **对策：** 必须在架构层面实现状态隔离与环境回滚机制。
2.  **安全与合规专家（沙箱与提权）：**
    *   **问题：** 简单的静态正则拦截（如检查 `rm -rf`）无法防住被幻觉驱使或混淆的恶意脚本。
    *   **对策：** 引入操作系统级别的沙箱（Docker/Modal）或强大的安全策略引擎。
3.  **AI 开发专家（反馈稀疏与评估失效）：**
    *   **问题：** 通用 LLM 评估器对代码执行的打分不够精确，且容易产生阿谀奉承现象，导致 MCTS 蜕变为随机搜索。
    *   **对策：** 设计细粒度的过程奖励（Dense Reward Shaping）和领域特定评估器。
4.  **全栈/DevOps 工程师（阻塞与僵尸进程）：**
    *   **问题：** 交互式 CLI（含 ANSI 和输入提示）会导致 `subprocess` 死锁；中断任务时会遗留大量孤儿进程消耗资源。
    *   **对策：** 采用异步 PTY 管理和严格的进程组（PGID）生命周期控制。
5.  **产品经理（意图路由过早绑定）：**
    *   **问题：** 静态分类任务意图并限制工具集，会扼杀 Agent 解决复合问题的能力。
    *   **对策：** 支持延迟加载工具（Lazy Tool Fetching），允许 Agent 按需搜索和挂载新技能。
6.  **数据与监控专家（预算爆炸）：**
    *   **问题：** 嵌套 Agent 调用会导致 Token 消耗呈指数级增长。
    *   **对策：** 引入预算感知型搜索（Budget-Aware Search），将成本作为 MCTS 价值函数的惩罚项。
7.  **QA 专家（竞态条件与测试）：**
    *   **问题：** MCTS 的高并发特性会导致 Mock 环境或真实沙箱产生严重的竞态条件。
    *   **对策：** 适配器层必须是绝对线程安全的，并具备类似事务的回滚能力。

## 3. 架构融合最终蓝图

幸运的是，`hermes-agent` 本身已经是一个极其庞大且成熟的系统，拥有数百个 Skills、丰富的 Plugins 以及健壮的底层工具库（如 `process_registry.py`, `checkpoint_manager.py`, `tirith_security.py` 等）。

我们的实施策略是：**坚守六边形架构的边界，通过适配器模式 (Adapter Pattern) 将现有基础设施接入 `contracts.py` 中定义的契约，而不污染核心的 MCTS 业务逻辑。**

### 3.1 攻克“状态污染”：基于 Checkpoint 的沙箱回滚

MCTS 并发探索时，分支间的物理副作用必须被隔离。

*   **复用组件：** `tools/checkpoint_manager.py` (Shadow Git Repo 机制)。
*   **适配设计 (State Rollback Adapter)：**
    *   **预执行快照：** `RealMctsEngine` 在执行 `PENDING` 节点前，调用 `checkpoint_manager` 对工作目录创建快照，记录 Hash。
    *   **回溯恢复：** 若分支被剪枝 (Pruned)，引擎在回退前强制调用 `checkpoint_manager.restore()` 恢复物理状态。
    *   **沙箱隔离：** 对于不可回滚的严重副作用（如启动服务），强制将 `terminal_env` 切换至 Docker 或 Modal，实现分支级别的容器隔离。

### 3.2 攻克“僵尸进程与阻塞”：异步 PTY 与进程组管理

安全调用 Claude Code 等交互式 CLI 是 Agent 嵌套的基础。

*   **复用组件：** `tools/process_registry.py` (进程注册表), `tools/interrupt.py`。
*   **适配设计 (Async PTY Process Manager)：**
    *   **非阻塞执行：** `InteractiveCliAdapter` 摒弃同步阻塞调用，将任务以 `background=True` 提交给 `process_registry`。
    *   **进程组斩首：** 接收到中断或 `ABORT` 指令时，通过 `process_registry.kill()` 发送 `SIGKILL` 至整个进程组 (`-PGID`)，彻底杜绝僵尸进程。
    *   **流式交互检测：** 在输出日志监控 (`_check_watch_patterns`) 中注入检测逻辑，遇 `[Y/n]` 等交互提示时暂停节点并抛给 HITL。

### 3.3 领域特定评估器 (Composite Evaluator)

解决 MCTS 奖励稀疏问题。

*   **复用组件：** `environments/benchmarks/`, `agent/error_classifier.py`。
*   **适配设计：** 在 `evaluator_adapter.py` 中实现路由分发：
    *   **代码任务：** 挂载测试环境，依据 linter/pytest 的通过率或错误类型演进（Dense Reward）进行打分。
    *   **文档任务：** 使用轻量级 LLM 检查格式规范。
    *   **数据任务：** 调用特定的数据一致性校验逻辑。

### 3.4 动态意图路由与延迟加载 (Lazy Tool Fetching)

赋予 Agent 按需扩展能力，打破静态路由限制。

*   **复用组件：** `tools/skills_hub.py`, `agent/smart_model_routing.py`。
*   **适配设计：**
    *   在 MCTS 引擎中配置常驻元工具 `search_and_load_skill`。
    *   当 Agent 在探索中发现现有工具不足时，主动调用该工具从 Hub 动态拉取并挂载新技能（如临时加载股票 API）。

### 3.5 预算感知型搜索与强力护栏

保障系统在财务和系统层面的绝对安全。

*   **复用组件：** `agent/usage_pricing.py`, `tools/path_security.py`, `tools/tirith_security.py`。
*   **适配设计：**
    *   **预算感知 MCTS：** 修改 `select_next_node` 的 UCB1 公式，引入 Token 成本惩罚项 ($-\lambda \times Cost$)，引导引擎探索高性价比分支；超出硬预算阈值则强制熔断触发 HITL。
    *   **强化护栏：** `DefaultHarnessMonitor` 直接接入 `tirith_security` 策略引擎，摒弃脆弱的正则匹配，对违规操作实施“一票否决”。

## 4. 实施原则

1.  **契约优先 (Interface-First)：** 所有新功能必须先在 `contracts.py` 定义 Protocol，再于外部基础设施层实现。
2.  **单一职责 (SRP)：** 每个 Adapter 仅专注一件事（如 PTY 处理、安全拦截、回滚）。
3.  **不造轮子：** 最大限度复用 `hermes-agent` 已有的高质量模块，通过组合实现涌现能力。
