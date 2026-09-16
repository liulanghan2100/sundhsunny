---
name: offline-upgrade
description: Run and manage the user's local offline Agent upgrade lane. Use when setting up autonomous offline upgrades, writing upgrade plans, enqueueing safe upgrade tasks, checking offline upgrade logs, or preparing user-space scheduled execution without administrator privileges.
---

# Offline Upgrade

Use this skill to let the local Agent OS keep doing low-risk maintenance while the user is away.

Rules:
- Never request administrator privileges.
- Never install a system service.
- Never push to a remote repository.
- Never auto-run high-risk code refactors.
- Write risky work to the approval queue.
- Run at most one small task per tick by default.

Commands:

```powershell
python "04_技能包/offline-upgrade/scripts/offline_upgrade.py" plan
python "04_技能包/offline-upgrade/scripts/offline_upgrade.py" enqueue
python "04_技能包/offline-upgrade/scripts/offline_upgrade.py" status
python "04_技能包/offline-upgrade/scripts/offline_upgrade.py" tick --max-tasks 1
python "04_技能包/offline-upgrade/scripts/offline_upgrade.py" loop --max-ticks 5 --interval-seconds 2
python "04_技能包/offline-upgrade/scripts/offline_upgrade.py" run-until --until 07:30 --interval-seconds 120 --max-tasks 1
```

Artifacts:
- `09_投研/offline_upgrade/upgrade_plan.json`
- `09_投研/offline_upgrade/offline_upgrade_log.jsonl`
- `09_投研/offline_upgrade/approval_queue.jsonl`
- `09_投研/task_queue/task_queue.sqlite`

Runtime note:
- The CLI auto-switches to the bundled Kimi Python runtime when the system Python lacks the `mcp` package.
