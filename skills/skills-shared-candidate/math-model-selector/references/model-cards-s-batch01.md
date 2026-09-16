# S 层模型详卡 Batch 01

> 状态：quarantine。用途：先把可直接迁移到 Agent OS 的模型补成选型依据。  
> 注意：本文件是工程选型卡，不是完整数学教材。

## 1. 贝叶斯模型

| 字段 | 内容 |
|---|---|
| model_id | bayesian-inference |
| 中文名 | 贝叶斯推断 |
| 英文名 | Bayesian Inference |
| 类型 | 概率推断 |
| 问题类型 | 证据更新、风险判断、置信度估计 |
| 核心公式 | `P(H|D) = P(D|H)P(H) / P(D)` |
| 最小推导 | 后验概率等于“先验可信度 × 证据在该假设下出现的可能性”，再除以所有可能证据概率做归一化。 |
| 输入 | 先验 `P(H)`、似然 `P(D|H)`、观测数据 `D` |
| 输出 | 后验概率 `P(H|D)` |
| 核心假设 | 先验可定义；似然模型合理；观测数据与建模变量一致 |
| 适用场景 | Agent 证据累积；质量异常诊断；模型置信度更新 |
| 不适用场景 | 先验完全乱填；似然不可估计；数据采样严重偏置 |
| 失效模式 | 先验支配结论；似然函数错误；证据非独立却按独立处理 |
| 验证方法 | 与频率统计结果对照；后验预测检查；敏感性分析 |
| 工程降级方案 | 无法建似然时退到规则评分或专家评审 |
| Agent 迁移 | 每次测试、用户反馈、日志异常都应更新任务置信度 |
| 信源 | 概率论教材、NIST 统计手册 |
| source_url | https://www.itl.nist.gov/div898/handbook/apr/section1/apr1a.htm |
| source_locator | NIST/SEMATECH e-Handbook of Statistical Methods, 8.1.10 Bayesian methodology, “Bayes Formula, Prior and Posterior Distribution Models, and Conjugate Priors”。 |
| 信源等级 | A |
| 审核状态 | quarantine |

## 2. Kalman Filter

| 字段 | 内容 |
|---|---|
| model_id | kalman-filter |
| 中文名 | 卡尔曼滤波 |
| 英文名 | Kalman Filter |
| 类型 | 状态估计、控制 |
| 问题类型 | 动态状态估计、传感器融合 |
| 核心公式 | 预测：`x̂_k^- = F_k x̂_{k-1} + B_k u_k`；更新：`x̂_k = x̂_k^- + K_k(z_k - H_k x̂_k^-)` |
| 最小推导 | 先用系统模型预测当前状态，再用观测残差修正预测，卡尔曼增益决定相信模型还是观测。 |
| 输入 | 状态转移矩阵、控制输入、观测矩阵、过程噪声、观测噪声 |
| 输出 | 当前状态估计和协方差 |
| 核心假设 | 系统近似线性；噪声近似高斯；过程和观测噪声参数可估 |
| 适用场景 | 视觉目标跟踪；设备状态估计；Agent 项目状态融合 |
| 不适用场景 | 强非线性且未扩展；噪声重尾；状态转移机制未知 |
| 失效模式 | 噪声协方差设错；旧观测污染；模型漂移未重估 |
| 验证方法 | 残差白噪声检查；真实轨迹对比；异常观测注入测试 |
| 工程降级方案 | 非线性场景退到 EKF/UKF/Particle Filter |
| Agent 迁移 | 把“计划状态、测试结果、用户反馈”融合成当前项目真实状态 |
| 信源 | 控制理论教材、状态估计教材 |
| source_url | https://asmedigitalcollection.asme.org/fluidsengineering/article/82/1/35/397706/A-New-Approach-to-Linear-Filtering-and-Prediction |
| source_locator | R. E. Kalman, “A New Approach to Linear Filtering and Prediction Problems”, Journal of Basic Engineering, Vol. 82, Issue 1, 1960, pp. 35-45；ASME 原始发表页。 |
| 信源等级 | A |
| 审核状态 | quarantine |

## 3. 队列模型

| 字段 | 内容 |
|---|---|
| model_id | queueing-mm1 |
| 中文名 | M/M/1 队列 |
| 英文名 | M/M/1 Queue |
| 类型 | 运筹、排队论 |
| 问题类型 | 吞吐、等待、资源瓶颈 |
| 核心公式 | 利用率 `ρ = λ / μ`；平均系统内数量 `L = ρ / (1-ρ)`；平均等待时间 `W = 1 / (μ-λ)` |
| 最小推导 | 当到达率接近服务率时，分母 `μ-λ` 趋近 0，等待时间快速爆炸。 |
| 输入 | 到达率 `λ`、服务率 `μ`、队列规则 |
| 输出 | 等待时间、队列长度、利用率 |
| 核心假设 | 到达服从泊松过程；服务时间指数分布；单服务台；稳定条件 `λ < μ` |
| 适用场景 | Agent 任务队列；扫码缓存；PLC 请求节拍 |
| 不适用场景 | 批处理；优先级队列复杂；服务时间强确定性 |
| 失效模式 | 忽略峰值到达；服务率估计过高；队列无限导致内存风险 |
| 验证方法 | 压测到达率；统计 P95/P99 等待；断线积压恢复测试 |
| 工程降级方案 | 限流、批处理、增加 worker、优先级队列 |
| Agent 迁移 | 长任务必须有队列状态、积压阈值和熔断条件 |
| 信源 | 排队论教材、运筹学教材 |
| source_url | https://www.stats.ox.ac.uk/~winkel/bs3a07l13-14.pdf |
| source_locator | Oxford Applied Probability lecture notes, Lecture 13/14；M/M/1 queues, traffic intensity `ρ=λ/μ`，等待时间与稳定性条件相关段落。 |
| 信源等级 | A |
| 审核状态 | quarantine |

## 4. MDP/POMDP

| 字段 | 内容 |
|---|---|
| model_id | mdp-pomdp |
| 中文名 | 马尔可夫决策过程 / 部分可观测马尔可夫决策过程 |
| 英文名 | MDP / POMDP |
| 类型 | 序贯决策、强化学习 |
| 问题类型 | 条件自主、策略选择 |
| 核心公式 | MDP 五元组 `(S,A,P,R,γ)`；价值函数 `Vπ(s)=Eπ[Σ γ^t R_t | S_0=s]` |
| 最小推导 | 决策质量由当前状态、动作、转移概率和长期奖励决定；POMDP 进一步承认状态不可完全观测，需要维护 belief。 |
| 输入 | 状态、动作、转移概率、奖励、折扣因子、观测 |
| 输出 | 策略、价值函数、动作选择 |
| 核心假设 | 状态表示足够；转移近似马尔可夫；奖励函数能表达目标 |
| 适用场景 | Agent 自主等级；审批降级；任务调度 |
| 不适用场景 | 奖励不可定义；状态不可观测且无 belief；高风险直接实操 |
| 失效模式 | 奖励黑客；状态遗漏；探索动作造成真实损害 |
| 验证方法 | 离线仿真；策略回放；安全约束单元测试 |
| 工程降级方案 | 规则状态机 + 人工审批 |
| Agent 迁移 | 证据不足时按 POMDP 降自主，不允许装作全知 |
| 信源 | Sutton & Barto, Reinforcement Learning: An Introduction |
| source_url | https://incompleteideas.net/book/the-book-2nd.html; https://www.pomdp.org/tutorial/index.html |
| source_locator | Sutton & Barto, Reinforcement Learning: An Introduction, 2nd ed., Chapter 3 “Finite Markov Decision Processes”；Cassandra, POMDPs for Dummies, tutorial index and “Background on POMDPs”。 |
| 信源等级 | S/A |
| 审核状态 | quarantine |

## 5. 动态规划

| 字段 | 内容 |
|---|---|
| model_id | dynamic-programming |
| 中文名 | 动态规划 |
| 英文名 | Dynamic Programming |
| 类型 | 优化、算法 |
| 问题类型 | 多阶段最优决策 |
| 核心公式 | Bellman 形式：`V(s)=min_a { c(s,a)+γ V(s') }` 或 `V(s)=max_a { r(s,a)+γ V(s') }` |
| 最小推导 | 如果问题满足最优子结构，整体最优可以由当前决策和子问题最优组合得到。 |
| 输入 | 状态、动作、转移、成本/收益 |
| 输出 | 最优值函数、最优策略 |
| 核心假设 | 最优子结构；重叠子问题；状态空间可枚举或可近似 |
| 适用场景 | 项目阶段规划；路径选择；排产；背包类资源分配 |
| 不适用场景 | 状态爆炸无法压缩；未来依赖不可表示；目标频繁变化 |
| 失效模式 | 状态定义不完整；递推边界错；局部阶段目标替代全局目标 |
| 验证方法 | 小规模穷举对照；边界条件测试；复杂度评估 |
| 工程降级方案 | 贪心、启发式、MIP 求解器 |
| Agent 迁移 | 大项目按阶段定义状态和完成标准，避免只看眼前一步 |
| 信源 | 算法教材、强化学习教材 |
| source_url | https://incompleteideas.net/book/the-book-2nd.html; https://onlinelibrary.wiley.com/doi/book/10.1002/9780470316887 |
| source_locator | Sutton & Barto, Reinforcement Learning: An Introduction, 2nd ed., Chapter 4 “Dynamic Programming”；Puterman, Markov Decision Processes: Discrete Stochastic Dynamic Programming, Wiley book record。 |
| 信源等级 | A |
| 审核状态 | quarantine |

## 6. PageRank / 图排序

| 字段 | 内容 |
|---|---|
| model_id | pagerank |
| 中文名 | PageRank |
| 英文名 | PageRank |
| 类型 | 图论、网络排序 |
| 问题类型 | 节点重要性、知识排序 |
| 核心公式 | `PR(u) = (1-d)/N + d Σ_{v∈B(u)} PR(v)/L(v)` |
| 最小推导 | 一个节点越多被重要节点指向，它越重要；阻尼项避免无出边或孤岛导致概率陷阱。 |
| 输入 | 有向图、边关系、阻尼系数 |
| 输出 | 节点重要性分数 |
| 核心假设 | 链接代表推荐或依赖；图结构可信；阻尼系数合理 |
| 适用场景 | 知识库条目排序；代码依赖重要性；文档引用网络 |
| 不适用场景 | 边关系被刷；链接不代表质量；冷启动无图 |
| 失效模式 | 垃圾链接操纵；孤立高价值节点被低估；时间新鲜度缺失 |
| 验证方法 | 人工 top-k 评审；与引用频率对比；抗刷边测试 |
| 工程降级方案 | 混合 BM25、人工权重、时间衰减 |
| Agent 迁移 | trusted 知识排序不能只靠文本相似度，也要看复用和引用 |
| 信源 | PageRank 原始论文、图论教材 |
| source_url | http://ilpubs.stanford.edu:8090/422/1/1999-66.pdf |
| source_locator | Page, Brin, Motwani & Winograd, “The PageRank Citation Ranking: Bringing Order to the Web”, Stanford Digital Library Technologies Project Technical Report 1999-66；PageRank 算法与 damping/random-surfer 公式。 |
| 信源等级 | S |
| 审核状态 | quarantine |

## 7. Stackelberg / Nash 博弈

| 字段 | 内容 |
|---|---|
| model_id | game-theory-nash-stackelberg |
| 中文名 | Nash 均衡 / Stackelberg 博弈 |
| 英文名 | Nash Equilibrium / Stackelberg Game |
| 类型 | 博弈论、多主体决策 |
| 问题类型 | 多 Agent 协作、冲突约束 |
| 核心公式 | Nash：`u_i(s_i*,s_-i*) ≥ u_i(s_i,s_-i*)`；Stackelberg：领导者先选策略，跟随者最优响应 |
| 最小推导 | Nash 表示没有参与者能单方面改变策略获益；Stackelberg 表示调度器先定规则，执行器在规则内响应。 |
| 输入 | 参与者、策略集、收益函数、行动顺序 |
| 输出 | 稳定策略组合或主从策略 |
| 核心假设 | 参与者目标可表达；策略空间明确；收益函数近似真实 |
| 适用场景 | 多 Agent 分工；文件锁；合并仲裁；资源竞价 |
| 不适用场景 | 目标不清；参与者不服从规则；收益函数不可度量 |
| 失效模式 | 激励错配；局部最优伤害全局；规则外行为无法约束 |
| 验证方法 | 冲突任务演练；越权 diff 检查；合并仲裁回放 |
| 工程降级方案 | 中央调度器强制派单 |
| Agent 迁移 | Kimi/Codex 并行时，任务卡和 allowed_paths 是规则，不是建议 |
| 信源 | 博弈论教材 |
| source_url | https://www.cs.vu.nl/~eliens/download/paper-Nash51.pdf; https://web.stanford.edu/~rjohari/teaching/notes/246_lecture7_2007.pdf |
| source_locator | Nash, “Non-Cooperative Games”, Annals of Mathematics, Vol. 54, No. 2, 1951, pp. 286-295；Stanford MS&E 246 Lecture 7 “Stackelberg games”，leader/follower sequential-move definition。 |
| 信源等级 | A |
| 审核状态 | quarantine |

## 8. 凸优化 / KKT

| 字段 | 内容 |
|---|---|
| model_id | convex-optimization-kkt |
| 中文名 | 凸优化 / KKT 条件 |
| 英文名 | Convex Optimization / KKT Conditions |
| 类型 | 优化 |
| 问题类型 | 约束最优化 |
| 核心公式 | `min f0(x)` s.t. `fi(x)≤0, hi(x)=0`；KKT 含原始可行、对偶可行、互补松弛、驻点条件 |
| 最小推导 | 在凸问题中，满足可行性和拉格朗日驻点等条件时，可得到全局最优或强最优性证据。 |
| 输入 | 目标函数、约束、变量域 |
| 输出 | 最优解、对偶变量、约束活跃性 |
| 核心假设 | 目标/约束满足凸性；可行域非空；约束资格条件成立 |
| 适用场景 | 资源分配；风险约束；多目标权衡；门禁规则 |
| 不适用场景 | 非凸强、多峰；目标函数随意拼凑；约束不可度量 |
| 失效模式 | 把非凸误当凸；忽略硬约束；目标函数权重拍脑袋 |
| 验证方法 | 凸性检查；约束可行性检查；与数值求解器结果对照 |
| 工程降级方案 | MIP/启发式/人工规则 |
| Agent 迁移 | 自主执行的目标函数必须被权限、门禁、验收约束包住 |
| 信源 | Boyd & Vandenberghe, Convex Optimization |
| source_url | https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf |
| source_locator | Boyd & Vandenberghe, Convex Optimization, Chapter 4 “Convex Optimization Problems” and Chapter 5 “Duality”, especially 5.5 “Optimality conditions” / KKT。 |
| 信源等级 | S/A |
| 审核状态 | quarantine |

## 9. 多臂老虎机

| 字段 | 内容 |
|---|---|
| model_id | multi-armed-bandit |
| 中文名 | 多臂老虎机 |
| 英文名 | Multi-Armed Bandit |
| 类型 | 在线学习、强化学习 |
| 问题类型 | 探索-利用权衡 |
| 核心公式 | 累积遗憾 `R_T = Tμ* - Σ E[r_t]`；UCB 常见形式 `argmax_i x̄_i + sqrt(2 ln t / n_i)` |
| 最小推导 | 既要利用当前看起来最好的策略，又要探索不确定但可能更好的策略；目标是降低长期遗憾。 |
| 输入 | 候选策略、奖励观测、探索规则 |
| 输出 | 下一步选择的策略 |
| 核心假设 | 奖励可观测；策略相对稳定；探索成本可承受 |
| 适用场景 | Agent 工作流灰度；提示词策略实验；非生产推荐 |
| 不适用场景 | 金融实盘大额探索；工业安全动作探索；奖励延迟严重 |
| 失效模式 | 短期噪声误导；探索伤害生产；奖励设计偏离真实目标 |
| 验证方法 | 离线回放；小流量 A/B；遗憾曲线分析 |
| 工程降级方案 | 固定策略 + 人工评审 |
| Agent 迁移 | 新规则先 shadow/small batch，不直接全量替换 |
| 信源 | 强化学习教材 |
| source_url | https://tor-lattimore.com/downloads/book/book.pdf; https://www.cambridge.org/core/books/bandit-algorithms/8E39FD004E6CE036680F90DD0C6F09FC |
| source_locator | Lattimore & Szepesvári, Bandit Algorithms, free online edition and Cambridge University Press record；Chapter 1/early chapters define bandit setting and regret。 |
| 信源等级 | A |
| 审核状态 | quarantine |

## 10. Agent-Based Model

| 字段 | 内容 |
|---|---|
| model_id | agent-based-model |
| 中文名 | 多主体仿真模型 |
| 英文名 | Agent-Based Model |
| 类型 | 仿真、复杂系统 |
| 问题类型 | 多主体交互、涌现行为 |
| 核心公式 | 无统一公式，通常定义主体集合 `A`、状态 `s_i`、行为规则 `π_i`、环境 `E`、交互函数 `I` |
| 最小推导 | 不是从全局方程开始，而是定义局部主体规则，通过仿真观察全局结果。 |
| 输入 | 主体、规则、环境、交互网络、时间步 |
| 输出 | 系统演化轨迹、统计指标、涌现模式 |
| 核心假设 | 局部规则能代表真实行为；仿真环境足够接近；参数校准合理 |
| 适用场景 | 多 Agent 协作演练；产线仿真；市场参与者行为 |
| 不适用场景 | 规则无法验证；参数全靠拍脑袋；需要严格闭式证明 |
| 失效模式 | 规则过拟合；仿真结果不可复现；局部规则遗漏关键约束 |
| 验证方法 | 固定随机种子；历史场景回放；敏感性分析 |
| 工程降级方案 | 离散事件仿真或规则状态机 |
| Agent 迁移 | 在真实多 Agent 并行前，先用任务卡、文件锁、合并仲裁做仿真演练 |
| 信源 | 复杂系统/仿真教材 |
| source_url | https://www.railsback-grimm-abm-book.com/; https://pup-assets.imgix.net/onix/images/9780691190822/9780691190839.pdf?fm=pdf |
| source_locator | Railsback & Grimm, Agent-Based and Individual-Based Modeling: A Practical Introduction, Princeton University Press；book site and PUP sample PDF, model design/implementation/analysis orientation。 |
| 信源等级 | A |
| 审核状态 | quarantine |
