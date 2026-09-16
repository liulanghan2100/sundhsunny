"""等效女娲 quality_check：主题 skill 六项质量标准自检"""
import sys, re
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8-sig")
checks = []
# 1. 心智模型数量 3-7
models = re.findall(r"^### F\d", text, re.M)
checks.append(("心智模型数量 3-7", 3 <= len(models) <= 7, f"{len(models)}个"))
# 2. 每个模型有失效条件
fails = text.count("失效条件")
checks.append(("每个框架有失效条件", fails >= len(models), f"{fails}处/{len(models)}框架"))
# 3. 反模式黑名单独立成章
checks.append(("反模式黑名单", "反模式黑名单" in text, ""))
# 4. 诚实边界 ≥3 条
m = re.search(r"## 诚实边界(.*?)(##|$)", text, re.S)
boundary = len(re.findall(r"^\d+\.", m.group(1), re.M)) if m else 0
checks.append(("诚实边界 ≥3 条", boundary >= 3, f"{boundary}条"))
# 5. 流派分歧/内在张力 ≥2 对（主题变体）
schools = len(re.findall(r"原典派|日系培训派|实战应用派", text))
checks.append(("流派分歧 ≥2 派", schools >= 2, f"{schools}派"))
# 6. 来源标注一手/二手
checks.append(("来源一手/二手分列", ("一手" in text and "二手" in text), ""))
# 附加：软化措辞红线（N15 规范第5条）
soft = len(re.findall(r"建议|可以考虑|根据情况|灵活把握|视情况而定", text))
checks.append(("禁软化措辞（=0）", soft == 0, f"{soft}处"))
# 附加：runtime 中立红线
rt = len(re.findall(r"\.claude|Claude Code|~/.kimi", text))
checks.append(("runtime 中立（=0）", rt == 0, f"{rt}处"))

ok = True
for name, passed, detail in checks:
    print(f"{'PASS' if passed else 'FAIL'}  {name}  {detail}")
    ok = ok and passed
print("总结:", "全部通过" if ok else "存在不通过项")
sys.exit(0 if ok else 1)
