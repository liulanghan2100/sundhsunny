# Skill 分类总览

> 生成时间：2026-08-09 22:52 ｜ 调度器：`09_投研/skill_os_mvp/scripts/dispatch.py`
> 分类数据：`09_投研/skill_os_mvp/skill_categories.json` ｜ 启用集：`04_技能包/active_skills.json` ｜ 带 * 为根目录正式技能（未进 registry）

## 状态总览

| 状态 | 数量 | 说明 |
|---|---|---|
| 启用 | 34 | 可被调度器推荐（`dispatch.py` 只从启用集挑选） |
| 待审 | 5 | 未在启用集：candidate 待审核，或正式技能(* )未注册进 registry |
| 归档 | 22 | quarantine/override 禁用，需要时 `curate_skills.py --enable` 取回 |

---

## 分类清单

### 1. 蒸馏产线（知识/思维/经验 → Skill）

> 把方法论、决策思维、执行轨迹蒸馏成可复用技能，并做受控进化

| 技能 | 状态 | 用途 |
|---|---|---|
| nuwa-runbook | 启用 | 方法论蒸馏成 SKILL.md（强制走 27 节点门禁） |
| cangjie-thinking-distiller | 启用 | 决策思维样本蒸馏成思维协议 |
| metaskill-creator | 启用 | 执行轨迹/回放日志蒸馏成工作流技能 |
| skill-creator | 启用 | SKILL.md 编写指南（Kimi 官方第一方） |
| darwin-runbook | 启用 | 技能受控进化（评估-变异-选择，仅 owner 触发） |

### 2. 知识库与调研（输入侧）

> 外部调研、业务/流程文档化、仓库与技能准入盘点、问题转工单

| 技能 | 状态 | 用途 |
|---|---|---|
| knowledge-base* | 待审 | 知识库维护（正式技能） |
| research | 启用 | 外部调研（高可信一手信源） |
| process-doc | 启用 | 流程文档化：流程图/RACI/SOP |
| repo-intake-and-plan | 启用 | 仓库/技能包准入盘点 |
| intake-control-plane | 启用 | 第三方技能/仓库/缺陷统一准入 |
| bug-intake | 启用 | 扫描发现/评审失败 → 结构化工单 |
| to-spec | 启用 | 对话 → 规格文档 |
| to-tickets | 启用 | 规格 → 带阻塞边界的工单 |

### 3. 门禁与项目节奏（manual-gates 体系）

> 27 节点门禁、结构化思维、对抗评审、代码评审、技能治理基建

| 技能 | 状态 | 用途 |
|---|---|---|
| manual-gates | 启用 | 27 节点门禁驱动开发节奏（体系核心） |
| mckinsey-structured-thinking | 启用 | 麦肯锡结构化思维（MECE/金字塔/议题树） |
| grill-me | 启用 | 对抗式拷问，评审方案的漏洞 |
| debate-protocol | 启用 | 对抗式立场辩论协议——把决策议题拆成强制对立的支持/反对两方，经证据化陈述、交叉 |
| code-review | 启用 | 双轴代码评审（标准 + 规格） |
| skill-register | 启用 | 技能元数据注册（registry 账本） |
| skill-router | 启用 | 任务 → 技能路由 |
| skill-publisher | 启用 | 技能打包发布（GitHub/市场） |
| skill-pipeline-orchestrator | 启用 | 多技能编排执行流水线 |

### 4. 工业与专业领域

> 工业软件/视觉专家开发、数学模型选型、科研问题选择

| 技能 | 状态 | 用途 |
|---|---|---|
| industrial-expert-dev* | 待审 | 工业专家开发（正式技能） |
| math-model-selector | 启用 | 工程/运筹/控制建模选型 |
| scientific-problem-selection | 启用 | 科研问题选择与项目评估 |

### 5. A股投研（输出侧）

> 调研→估值分析→市场反应预演→Excel/图表→日报→PDF 报告

| 技能 | 状态 | 用途 |
|---|---|---|
| decision-review-loop | 启用 | 决策记忆与事后复盘闭环——决策登记（含失效条件）→到期对照→四象限归因（判断对/ |
| trading-decision-workflow | 启用 | 交易决策全流程工作流——事实包→基本面分析→多空辩论→风控检查→决策综合→复盘登 |
| graham-dodd-security-analysis | 启用 | 格雷厄姆-多德价值投资分析 |
| market-rehearsal | 启用 | Use when predicting how a market/opinion |
| xlsx | 启用 | Excel 建模/分析/图表/报告 |
| seaborn-visualization | 归档 | 中文图表绘制（seaborn/matplotlib） |
| daily-report | 归档 | 每日情报简报 PDF（全球宏观/产业） |
| pdf | 归档 | PDF 创建/文本表格提取/页面操作 |
| md-to-pdf | 启用 | Markdown → PDF 转换 |

### 6. 内容生产与办公

> 营销文案、SaaS 策略、文档/演示、音视频、网页应用

| 技能 | 状态 | 用途 |
|---|---|---|
| copywriting | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | 营销文案写作 |
| copy-editing | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | 营销文案润色 |
| content-research-writer | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | 带引用调研的内容写作 |
| humanizer-zh | 启用 | AI 味中文改写成自然中文 |
| ad-creative | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | 广告创意批量生成 |
| campaign-plan | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | 营销战役策划（目标/受众/日历） |
| pricing-strategy | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | SaaS 定价设计 |
| saas-metrics-coach | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | SaaS 财务健康顾问 |
| churn-prevention | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | 客户流失挽留流程设计 |
| seo-audit | 归档 override: 营销/SaaS类与正业零交集，归档留底(2026-08-09) | SEO 技术审计 |
| docx | 归档 | Word 文档创建/编辑/修复 |
| kimi-slides | 启用 | PPTX 演示文稿（Kimi 官方第一方） |
| kimi-design-skill | 启用 | Kimi 风格 UI 设计 |
| webapp-building | 启用 | React/TS/Tailwind 网页应用 |
| speech | 待审 | TTS 配音（需 OPENAI_API_KEY） |
| transcribe | 待审 | 音频转文字 + 说话人标注 |
| shortdrama-video-generation | 归档 | 短剧视频拍摄计划（分镜/选模型） |

### 7. 平台组件（Daimon/Kimi Widget 系）

> Widget/Canvas/Automation/Binding 等平台原语，仅供平台开发使用

| 技能 | 状态 | 用途 |
|---|---|---|
| widget | 归档 | Daimon Blueprint Widget 开发 |
| widgetdesign | 归档 | Daimon/Kimi Widget 设计规范 |
| canvas | 归档 | Daimon Canvas 画布操作 |
| automation | 归档 | Daimon 自动化创建/调度 |
| binding | 归档 | Daimon 绑定（Automation↔Widget） |
| blueprint | 归档 | Daimon Blueprint 域路由 |
| daimon-widget-cards | 归档 | Daimon 结果卡片渲染 |
| memory-widget | 归档 | 记忆可视化 widget（dashboard/关系图） |
| kimi-webbridge | 启用 | 控制真实浏览器（本地 daemon） |

### 8. 系统维护

> 离线升级等系统级操作

| 技能 | 状态 | 用途 |
|---|---|---|
| offline-upgrade* | 待审 | 离线升级（正式技能） |

---

## 常用命令

```powershell
# 看技能分类/状态
python 09_投研/skill_os_mvp/scripts/curate_skills.py --list
# 任务 → 自动挑技能链
python 09_投研/skill_os_mvp/scripts/dispatch.py "<任务描述>" --plain
# 排查某技能为何不被推荐
python 09_投研/skill_os_mvp/scripts/dispatch.py "<任务描述>" --debug <skill>
# 启用/禁用技能（owner 决策留痕）
python 09_投研/skill_os_mvp/scripts/curate_skills.py --enable <skill> --reason <理由>
python 09_投研/skill_os_mvp/scripts/curate_skills.py --disable <skill> --reason <理由>
# 使用后回写度量
python 09_投研/skill_os_mvp/scripts/record_usage.py <skill> <项目名>
# 重新生成本文档
python 09_投研/skill_os_mvp/scripts/build_categories_md.py
```
