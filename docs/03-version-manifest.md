# 未纳入版本管理的大文件清单

生成时间：2026-09-16 20:09

## 为什么有这份清单

下面这些文件体积大或每次运行都变，不适合放进 git。
但它们随包分发，是包能独立运行的关键。
记录指纹是为了：换机器或日后核对时，能确认它们有没有被改动。

## 清单

| 文件 | 大小(字节) | SHA256 前16位 | 说明 |
|---|---|---|---|
| `tools/codebase-memory-mcp/bin/codebase-memory-mcp.exe` | 273,333,760 | `9a205fa5ae759fbc` | 图谱引擎（260MB，不可再生） |
| `tools/codebase-memory-mcp/cache/MCPCreate20260719.db` | 61,538,304 | `2fd1abcc0d82e602` | 主库图谱索引 |
| `tools/codebase-memory-mcp/cache/OpenNiss.TiaExport.V21.db` | 5,111,808 | `febf145e03e52ce0` | TIA 项目图谱索引 |
| `tools/codebase-memory-mcp/cache/C-Users-sundh-Documents-KIMI_MODE-createMCP-MCPCreate20260719-AutoRobot.db` | 3,407,872 | `6a77c0d3fc424494` | AutoRobot 图谱索引 |
| `data/memory/memory.jsonl` | 3,203,017 | `cbfcbf69a3e67f66` | 经验记忆正文（累计数据，不可再生） |
| `data/memory/memory_index.sqlite` | 11,550,720 | `8aca297a23a32b3c` | 记忆关键词索引（可重建） |
| `data/memory/memory_vector.sqlite` | 4,308,992 | `977c56ffbb3fdab1` | 记忆向量索引（可重建） |

## 换机器时怎么处理

1. **引擎**（`tools/`）：直接从包里复制过去，无需安装。
   它只依赖 Windows 自带组件，任何 Win10/Win11 都能跑。
2. **图谱索引**（`cache/*.db`）：可以直接复制。
   索引里存的是相对路径，换机器后检索照常；
   只是 `list_projects` 显示的原始路径还是旧的。
   若要重建，用 `hub.py graph index <工程路径>`。
3. **记忆数据**（`data/memory/`）：`memory.jsonl` 是正文，必须带走。
   两个 `.sqlite` 是索引，丢了可以用下面命令重建：
   ```
   python -c "import sys; sys.path.insert(0, 'engine/memory'); \
     from experience_memory_mcp import common as C; \
     print(C._rebuild_index()); print(C._rebuild_vector_index())"
   ```

## 校验方法

```powershell
Get-FileHash tools/codebase-memory-mcp/bin/codebase-memory-mcp.exe -Algorithm SHA256
```
把结果和上表核对即可。
