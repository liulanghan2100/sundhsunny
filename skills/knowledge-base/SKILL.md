---
name: knowledge-base
description: Manage and query the user's local personal Agent knowledge base. Use when collecting useful Agent skills, playbooks, cases, official references, or web research into a local repository; when searching prior stored knowledge before a project; when adding items to quarantine; when promoting reviewed items; or when rebuilding/reporting the local SQLite FTS index.
---

# Knowledge Base

Use this skill to keep external knowledge useful without polluting the Agent's trusted memory.

Core rules:
- Search the knowledge base before broad web research when the task matches stored topics.
- Add new internet findings to quarantine by default.
- Require source URL or local source path for every entry.
- Promote only after review or explicit user approval.
- Never rewrite the AI execution manual directly from web findings; create a rule candidate instead.

Repository paths:
- Knowledge base: `10_知识储备库/`
- Skill scripts: `04_技能包/knowledge-base/scripts/`

Common commands:

```powershell
python "04_技能包/knowledge-base/scripts/query.py" "agent memory"
python "04_技能包/knowledge-base/scripts/add.py" --title "Title" --type playbook --source-url "https://example.com" --tags "agent,memory" --summary "Short summary" --content "Markdown body"
python "04_技能包/knowledge-base/scripts/promote.py" <entry-id>
python "04_技能包/knowledge-base/scripts/rebuild_index.py"
python "04_技能包/knowledge-base/scripts/report.py"
```

Result handling:
- Cite `source_url` when using stored knowledge.
- Prefer `trusted` entries over `quarantine` entries.
- If only quarantine entries match, say they are unreviewed before using them.

