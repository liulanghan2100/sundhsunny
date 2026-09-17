# TIA Template Compiler MCP

面向 TIA Portal V21 的模板差异编译规划 MCP。

## 定位

```text
项目文档
-> ProjectSpec
-> TemplateCatalog
-> ChangeSpec
-> 变更预览
-> OpennessTask 执行包
-> Windows V21 Runner
-> 编译与回读证据
-> PASS / FAIL
```

本 MCP 不直接调用 Siemens Openness，也不允许模型执行任意 TIA 命令。真实修改由现有的 Windows V21 Runner 执行。

## 工具

| 工具 | 作用 | 时机 |
|---|---|---|
| `tia_template_compiler_brief` | 查看边界和流程 | 每次新任务开始 |
| `scan_template` | 扫描 `.ap21`、GSDML、工程文档并建立文件基线 | 使用模板前 |
| `validate_project_spec` | 校验文档解析后的项目规格 | 生成计划前 |
| `build_change_spec` | 计算业务组件级差异 | 任何写入前 |
| `preview_change` | 查看将要修改的对象和风险 | Owner 审批前 |
| `stage_runner_bundle` | 输出离线 V21 Runner 执行包 | 审批后、执行前 |
| `dispatch_runner_bundle` | 预览或受控调用现有 V21 Runner | 执行包验收后 |
| `verify_staged_bundle` | 验证执行包契约 | Runner 启动前 |
| `verify_change` | 用编译和回读证据判定结果 | Runner 完成后 |

## 运行

```powershell
python .\run_tia_template_compiler.py
```

MCP 客户端使用 stdio 启动，工作目录建议设置为本目录。

## 当前边界

- `scan_template` 是静态文件扫描；完整的 PLC/HMI/硬件语义目录必须由 V21 Runner 回读。
- `stage_runner_bundle` 只写执行包，不修改 TIA 工程。
- `dispatch_runner_bundle` 默认只做 dry-run；真实执行必须同时满足：
  - 任务存在明确的 V21 Runner 路由
  - 执行包指定了 disposable project copy
  - `OPENNISS_RUNNER_ALLOW_EXECUTION=1`
  - Runner 接收 `--project` 和可选的 `--output`
- 适配层只分发已存在的 Runner 命令，不替换现有 Openness Applier。
- 没有真实编译和回读证据，`verify_change` 不会返回 PASS。
- 不支持在线连接、下载、上传或原始模板工程修改。

## Runner Adapter

`ChangeSpec` 中的业务组件需要显式声明执行路由。示例：

```json
{
  "kind": "cylinder",
  "target": {
    "name": "Z13",
    "execution_profile": "st10_pair_next"
  }
}
```

当前已绑定的专用路径：

- `cylinder + st10_pair_next` -> `--apply-st10-cylinder-pair-next`
- `servo + component_servo` -> `--apply-component-servo-plan`，同时需要 `plan_path` 和 `template_path`
- 通用 `compile-plc`、`apply-template-only`、`apply-hmi-tags-only` 路由可显式指定

未绑定路由的任务会返回 `blocked`，不会猜测或调用 TIA 命令。
