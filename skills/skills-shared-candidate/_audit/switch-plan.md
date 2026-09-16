---
status: planned
type: switch-rehearsal
risk: high
owner_required: true
created: 2026-08-01
---

# skills-shared 切换演练方案

## 当前结论

本文件只记录任务 1B 的挂账演练方案，不执行切换。

本轮已完成的是离线候选并集：

- 候选目录：`04_技能包/skills-shared-candidate/`
- Kimi 来源目录：`C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills/`
- Codex 来源目录：`C:/Users/sundh/.codex/skills/`
- 合并策略：复制，不移动，不删除，不建 junction。

## 触发条件

以下条件缺一不可：

1. Kimi 已确认进入停机窗口。
2. owner 单独给出红线口令，明确允许执行 runtime skills 目录切换。
3. Kimi 与 Codex 两个现役 skills 目录均已完成时间戳快照。
4. `04_技能包/skills-shared-candidate/_audit/01_full_inventory.csv` 显示候选技能数为 45。
5. 切换前 git 工作区状态已记录，且不会混入其他在途文件。

## 切换步骤

1. 记录切换前目录计数：

   ```powershell
   Get-ChildItem -Directory "C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills" | Measure-Object
   Get-ChildItem -Directory "C:/Users/sundh/.codex/skills" | Where-Object Name -ne ".system" | Measure-Object
   Get-ChildItem -Directory "04_技能包/skills-shared-candidate" | Where-Object Name -ne "_audit" | Measure-Object
   ```

2. 生成快照备份：

   ```powershell
   Copy-Item -Recurse "C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills" "C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills.bak.<timestamp>"
   Copy-Item -Recurse "C:/Users/sundh/.codex/skills" "C:/Users/sundh/.codex/skills.bak.<timestamp>"
   ```

3. 重命名原现役目录：

   ```powershell
   Rename-Item "C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills" "skills.runtime-bak.<timestamp>"
   Rename-Item "C:/Users/sundh/.codex/skills" "skills.runtime-bak.<timestamp>"
   ```

4. 创建 junction：

   ```powershell
   cmd /c mklink /J "C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills" "C:/Users/sundh/Documents/KIMI_MODE/createMCP/MCPCreate20260719/04_技能包/skills-shared-candidate"
   cmd /c mklink /J "C:/Users/sundh/.codex/skills" "C:/Users/sundh/Documents/KIMI_MODE/createMCP/MCPCreate20260719/04_技能包/skills-shared-candidate"
   ```

5. 切换后验收：

   ```powershell
   Get-ChildItem -Directory "C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills" | Where-Object Name -ne "_audit" | Measure-Object
   Get-ChildItem -Directory "C:/Users/sundh/.codex/skills" | Where-Object Name -ne "_audit" | Measure-Object
   ```

   期望：两边均可看到 45 个技能目录。

## 回滚步骤

1. 停止 Kimi 和 Codex 对 skills 目录的读取。
2. 删除 junction：

   ```powershell
   Remove-Item "C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills"
   Remove-Item "C:/Users/sundh/.codex/skills"
   ```

3. 恢复原 runtime 目录：

   ```powershell
   Rename-Item "C:/Users/sundh/AppData/Roaming/kimi-desktop/daimon-share/daimon/skills.runtime-bak.<timestamp>" "skills"
   Rename-Item "C:/Users/sundh/.codex/skills.runtime-bak.<timestamp>" "skills"
   ```

4. 复核两边目录计数与切换前一致。

## 风险点

1. Codex 的部分技能可能包含 `agents/` 等子目录，Kimi runtime 是否完全忽略这些目录需要切换前验证。
2. Codex `.system` 技能目录本轮被排除；未来若要纳入共享，必须另行评审。
3. junction 会改变两个 runtime 的实际读入口，必须在停机窗口执行。
4. 该方案不能在 Kimi 在线工作期间执行。

