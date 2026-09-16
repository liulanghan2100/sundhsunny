---
status: reviewed
type: codex-overlay-review
risk: medium
created: 2026-08-01
---

# Codex 侧 overlay 复核记录

## 复核对象

- Kimi 执行记录：`04_技能包/skills-shared-candidate/_audit/codex-overlay-finish-20260801-230128.md`
- Codex runtime：`C:/Users/sundh/.codex/skills`
- 共享候选库：`04_技能包/skills-shared-candidate`

## 初始复核结果

```text
user_dirs: 45
junctions: 45
runtime_bak_dirs: 9
system_exists: true
```

结论：Kimi 的 overlay 收尾已把 45 个业务技能全部切为 junction，`.system` 保留正常。

风险：9 个 `.runtime-bak.20260801-230128` 目录仍在 `C:/Users/sundh/.codex/skills` 下，内部有有效 `SKILL.md`，已被本次技能索引识别成重复技能来源。

## 清理动作

将 9 个 runtime-bak 目录移出 Codex 技能扫描根目录，目标：

`09_投研/codex_skills_overlay_backup_20260801-230128/runtime-bak-from-codex-skills/`

移动对象：

1. `code-review.runtime-bak.20260801-230128`
2. `grill-me.runtime-bak.20260801-230128`
3. `math-model-selector.runtime-bak.20260801-230128`
4. `research.runtime-bak.20260801-230128`
5. `shortdrama-video-generation.runtime-bak.20260801-230128`
6. `speech.runtime-bak.20260801-230128`
7. `to-spec.runtime-bak.20260801-230128`
8. `to-tickets.runtime-bak.20260801-230128`
9. `transcribe.runtime-bak.20260801-230128`

## 清理后验证

```text
moved: 9
remaining_runtime_bak: 0
codex_user_skill_count: 45
codex_junction_count: 45
system_exists: true
```

## 当前状态

Codex 侧已经达到：

1. `.system` 保留。
2. 45 个业务技能均为 junction。
3. 不再存在会被扫描成重复技能的 `.runtime-bak` 目录。
4. 回滚备份仍保留在 `09_投研/codex_skills_overlay_backup_20260801-230128/`。

