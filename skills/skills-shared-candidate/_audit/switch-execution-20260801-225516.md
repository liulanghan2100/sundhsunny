---
status: executed
type: switch-execution
risk: high
owner_window: kimi-stopped
created: 2026-08-01
timestamp: 20260801-225516
---

# skills-shared 切换执行记录

## 执行结论

本次没有执行“两个 runtime 根目录都直接 junction 到 `skills-shared-candidate`”的原始方案。

原因：Codex 当前进程占用 `C:/Users/sundh/.codex/skills`，Windows 拒绝重命名；并且直接替换 Codex 根目录会丢失 `.system` 系统技能入口。为避免破坏 Codex，实际执行了更保守的 overlay 方案：

1. Kimi runtime 根目录保留为普通目录，目录内 45 个业务技能全部改为 junction，目标均指向 `04_技能包/skills-shared-candidate/<skill>`。
2. Codex runtime 根目录保留为普通目录，`.system` 原样保留。
3. Codex 已有 9 个用户技能目录原样保留。
4. Codex 缺失的 36 个 Kimi 技能以 junction 方式补入，目标均指向 `04_技能包/skills-shared-candidate/<skill>`。

## 验证结果

```text
Kimi user skill count: 45
Kimi junction count: 45
Kimi root linktype: null

Codex user skill count: 45
Codex system exists: true
Codex added junctions: 36
Codex existing user dirs kept: 9
Codex total junctions: 36
```

## 备份

切换前快照：

- `09_投研/skills_shared_switch_backup_20260801-225516/kimi-skills.before`
- `09_投研/skills_shared_switch_backup_20260801-225516/codex-skills.before`

Kimi runtime 原目录备份：

- `C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills.runtime-bak.20260801-225516`

Codex runtime 根目录未重命名成功，因此不存在 `skills.runtime-bak.20260801-225516`。

## 偏离原方案说明

原方案风险：

1. Codex 根目录 root junction 会隐藏 `.system`。
2. 候选目录中的 `_audit` 会暴露给 runtime。
3. 当前 Codex 进程占用 `.codex/skills`，重命名失败。

实际方案收益：

1. 两边都能看到 45 个业务技能。
2. Kimi 的 45 个业务技能已统一指向候选库。
3. Codex 不丢 `.system`。
4. Codex 侧不强行替换当前会话正在使用的 9 个技能。

实际方案限制：

1. Codex 原有 9 个用户技能仍是原目录，不是 junction；它们与候选库目前是同内容副本，不是严格单一真源。
2. 若未来要把 Codex 原有 9 个也切到候选库，需要在 Codex 停机窗口执行第二阶段。

## 回滚步骤

### 回滚 Kimi

1. 确认 Kimi 停止。
2. 删除当前 Kimi `skills` 目录中的 45 个 junction。
3. 删除空的 `skills` 目录。
4. 将 `skills.runtime-bak.20260801-225516` 改名回 `skills`。

### 回滚 Codex

1. 删除 Codex `skills` 目录中本次新增的 36 个 junction。
2. 保留 `.system` 和原有 9 个 Codex 用户技能目录。
3. 如需完整还原，可用 `09_投研/skills_shared_switch_backup_20260801-225516/codex-skills.before` 做人工比对。

