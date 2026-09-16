---
name: industrial-expert-dev
description: Industrial automation software expert workflow for PLC, HMI, barcode scanner, machine vision, marking/printing, MES traceability, device communication, SQLite/SQL logging, alarms, audit logs, recipes, reports, and Windows industrial desktop tools. Use when Codex is asked to design or develop industrial software, automation tooling, PLC-connected applications, HMI pages, production traceability systems, scanner/camera/printer integration, or when a project must follow an industrial engineering acceptance workflow.
---

# Industrial Expert Dev

Use this skill to prevent industrial software projects from becoming a thin demo. It adds a mandatory industrial checklist before implementation.

## Hard Gate

Before editing code or creating project files, output and freeze:

1. Global project outline
2. Research summary
3. Industrial module checklist
4. Communication matrix
5. Device interaction signal table
6. UI page list
7. Acceptance matrix

Do not start implementation until the outline and acceptance matrix exist in the project folder.

## Workflow

1. Research comparable systems and standards.
   - SCADA/HMI: alarms, historian, events, user security, trends, reports.
   - MES/traceability: barcode, station, process, result, audit, genealogy, export.
   - Industrial device apps: IP/port/serial config, online status, heartbeat, retries, timeouts.

2. Create the required cards from `templates/`:
   - `01_工业项目全局大纲.md`
   - `02_工业通讯矩阵.md`
   - `03_设备交互信号表.md`
   - `04_数据库追溯表.md`
   - `05_UI页面清单.md`
   - `06_工业验收矩阵.md`
   - `07_发布检查表.md`

3. Implement only after the cards are created.

4. Verify with at least:
   - Build passes with zero errors.
   - Smoke test covers the core workflow.
   - EXE or deployable artifact exists.
   - Backup exists.
   - Git baseline is created when appropriate.

5. At project end, write an experience card and update the knowledge references when a reusable lesson appears.

## Default Industrial Modules

Every industrial software project must explicitly include or reject these modules:

- Device communication configuration: IP, port, protocol, serial parameters.
- Communication status: online/offline/reconnecting, last packet time, latency, heartbeat.
- Device interaction: start, stop, reset, ready, busy, complete, OK, NG, error code, ACK.
- Data storage: production record, raw data, parsed data, result, timestamp, operator.
- Query: by time, barcode/serial, result, station, product, batch.
- Export: CSV minimum, Excel/reporting when required.
- User roles: operator, engineer, admin.
- Audit log: login, config change, export, reset, delete, maintenance.
- Alarm/event center: comm timeout, device offline, validation NG, database failure.
- Recipe/config management: save, load, import, export, backup.
- Runtime page: large status display for operators.
- Configuration page: admin-only settings.
- Maintenance page: logs, backup, database cleanup.
- Release evidence: build, smoke test, publish, backup, run instructions.

## Reference Routing

Read `references/工业软件标准能力清单.md` when designing a new industrial project.

Read `references/扫码枪项目经验回流.md` when working on barcode scanner, PLC validation, traceability, SQLite, or WPF industrial desktop software.

Read `references/打标机项目经验回流.md` when working on Zebra, ZPL, label designer, printer status, barcode/QR templates, or PLC-triggered printing.
