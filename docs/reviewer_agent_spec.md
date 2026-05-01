# Hermes Reviewer Agent & MCTS Engine - Technical Specification

## 1. 背景与动力 (Background & Motivation)
在 Hermes Agent 的演进中，我们面临着从“工具调用者”向“自主解决者”跨越的挑战。目前的单向执行逻辑在处理长程、复杂任务时暴露出以下核心痛点：
- **目标漂移 (Goal Drift)**：Agent 容易陷入工具输出的局部细节，忽视了用户的最终需求（如在修 Bug 时无意中破坏了无关功能）。
- **验证困境 (Validation Gap)**：模型自评存在“幸存者偏差”，无法客观评估操作是否真正达成预期。
- **回溯成本 (Backtracking Cost)**：在物理环境下（非模拟器），撤销一个错误的 shell 命令或文件修改极其困难，缺乏原子性保障。

为了解决这些问题，本项目引入了 **Critic-Driven MCTS (评论家驱动的蒙特卡洛树搜索)** 架构。

---

## 2. 讨论过程中的关键决策与技术细节 (Key Decisions & Technical Subtleties)

### 2.1 破解“自举困境”：异构模型评审
- **讨论焦点**：能否通过 Prompt 优化让主模型自检？
- **决策**：专家组认为自评本质上是同一概率分布的二次采样，无法纠正系统性幻觉。
- **细节**：
    - **异构化**：Actor 使用 GPT-4o，Critic 强制使用 Claude 3.5 Sonnet 或 Gemini 1.5 Pro。
    - **分级策略**：
        - **L1 快速自检**：主模型执行，检查格式和基本逻辑（低延迟）。
        - **L2 深度评审**：异构模型执行，仅在任务里程碑或高风险操作（`rm`, `sudo`, `deploy`）时触发。

### 2.2 事务性回溯：从“快照”到“补偿事务”
- **讨论焦点**：文件系统快照是否足以应对所有场景？
- **决策**：单纯的文件快照无法恢复进程状态（如运行中的服务器）和环境变量。
- **细节**：
    - **TransactionManager**：不仅记录文件变更，还记录启动的 **PID 树**、修改的 **Env Vars**。
    - **补偿操作 (Undo Log)**：每个操作映射一个逆向操作（如 `mkdir` $\leftrightarrow$ `rmdir`）。
    - **I/O 优化**：针对大型代码库，弃用全量快照，改用 **Copy-on-Write (CoW)** 机制，仅对受影响的文件进行物理备份。

### 2.3 安全加固：防御性通信与沙箱
- **讨论焦点**：评审过程本身是否引入新风险？
- **决策**：评审智能体被授予运行测试的权限，这可能成为攻击载体。
- **细节**：
    - **隔离执行**：所有由 Critic 触发的验证命令（`pytest` 等）必须在 **Docker/Modal 隔离容器**中运行。
    - **防止报告注入**：Critic 的反馈必须是 **结构化 JSON**。任何自然语言描述在反馈给主模型前都要经过转义处理，防止 Critic 的输出被误认为系统指令。

### 2.4 UX 透明度：评审看板
- **讨论焦点**：用户如何理解 Agent 的中途转向？
- **决策**：不可黑盒评审。
- **细节**：
    - **语义对齐分**：在 TUI 侧边栏展示当前步骤与用户原始意图的相似度。
    - **审计日志**：记录每一条 Critic 的驳回建议（Rejection Reason），用户可回溯查看“为什么 Agent 放弃了路径 A”。

---

## 3. 数学评估模型 (Mathematical Deep Dive)

### 3.1 语义偏离度 (Semantic Drift)
$$SemanticDrift = 0.6 \cdot (1 - \text{ConstraintSat}) + 0.4 \cdot \text{IntentShift}$$
- **ConstraintSat (约束满足度)**：通过 `ConstraintExtractor` 提取的硬约束清单（如“不得修改 `tests/` 目录”）。
- **IntentShift (意图偏移)**：使用 `all-MiniLM-L6-v2` 向量模型计算用户原始 Goal 与当前路径摘要的余弦相似度。

### 3.2 动态评分公式 (Dynamic Scoring)
$$Score = \alpha \cdot \text{EnvFeedback} + \beta \cdot \text{CriticScore} + \gamma \cdot \text{LLMConfidence}$$

| 阶段 | $\alpha$ (环境) | $\beta$ (异构) | $\gamma$ (自置信) | 理由 |
| :--- | :--- | :--- | :--- | :--- |
| **初期 (探索)** | 0.2 | 0.5 | 0.3 | 此时环境反馈较少，依赖异构模型直觉。 |
| **中期 (执行)** | 0.4 | 0.4 | 0.2 | 命令行退出码和初步文件变更开始生效。 |
| **后期 (收敛)** | **0.7** | 0.2 | 0.1 | **最终验证（如测试通过）是唯一标准。** |

### 3.3 自适应 UCB1 (Adaptive UCB1)
$$UCB = avg\_score + C_{base} \cdot (1 - avg\_score) \cdot \sqrt{\frac{\ln(N_{parent})}{N_{child}}}$$
- **创新点**：将探索系数 $C$ 与路径质量挂钩。路径越好，探索欲望越低，从而快速收敛。

---

## 4. 核心组件规格

### 4.1 `TransactionManager` (事务管理器)
- **职责**：维护全局事务栈。
- **数据结构**：`Stack<TransactionNode>`，每个节点包含 `(action, undo_payload, evidence)`。

### 4.2 `ReviewerAgent` (评审器)
- **职责**：执行只读审计。
- **接口**：`review(transcript) -> ReviewReport{alignment, risks, suggestion}`。

### 4.3 `ConstraintExtractor` (约束抽取器)
- **职责**：任务冷启动预处理。
- **技术**：基于正则和关键词触发的 NER 抽取。

---

## 5. 风险与对策 (Risks & Mitigations)
- **延迟爆炸**：通过分级评审（L1/L2）和评审结果缓存来缓解。
- **并发冲突**：在 MCTS 分支并行执行时，为每个分支分配独立的 `task_id` 和隔离的工作目录快照。
- **Token 消耗**：对历史轨迹进行摘要压缩，仅向 Critic 提供关键决策路径。

---

## 6. 实施路线图 (Implementation Roadmap)

### Phase 1: Foundation & Security (并行)
- [ ] 创建 `agent/transaction_manager.py` (事务日志与沙箱执行封装)。
- [ ] 开发 `agent/reviewer_agent.py` (异构模型连接与只读限制)。

### Phase 2: Transactional Backtracking
- [ ] 实现 `agent/backtrack_engine.py` (CoW 回滚与进程清理)。
- [ ] 改造 `tools/file_tools.py` 埋点记录事务。

### Phase 3: Scoring & MCTS Logic
- [ ] 创建 `agent/constraint_extractor.py` (硬约束自动生成)。
- [ ] 实现 `agent/scoring_engine.py` (动态权重与 UCB1 算法)。

### Phase 4: UI/UX
- [ ] 开发 `/review` 指令。
- [ ] 实现 TUI 评审看板。
