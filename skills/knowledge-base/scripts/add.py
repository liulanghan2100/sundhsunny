# -*- coding: utf-8 -*-
import argparse
import shutil
from pathlib import Path

from kb_common import ROOT, add_common_args, append_meta, ensure_dirs, make_entry_id, normalize_type, rebuild_index, target_dir, now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Add an item to the local Agent knowledge base.")
    add_common_args(parser)
    args = parser.parse_args()

    if not args.source_url and not args.source_path:
        raise SystemExit("source-url or source-path is required.")
    if not args.content and not args.file:
        raise SystemExit("content or file is required.")

    ensure_dirs()
    entry_type = normalize_type(args.type)
    entry_id = make_entry_id(args.title)
    out_dir = target_dir(entry_type, args.status)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{entry_id}.md"

    if args.file:
        source_file = Path(args.file)
        if not source_file.exists():
            raise SystemExit(f"Input file not found: {source_file}")
        if source_file.suffix.lower() == ".md":
            shutil.copyfile(source_file, out_path)
        else:
            body = source_file.read_text(encoding="utf-8", errors="replace")
            out_path.write_text(body, encoding="utf-8")
    else:
        out_path.write_text(args.content, encoding="utf-8")

    tags = [x.strip() for x in args.tags.split(",") if x.strip()]
    row = {
        "id": entry_id,
        "title": args.title,
        "type": entry_type,
        "status": args.status,
        "trust_level": "unreviewed" if args.status == "quarantine" else "reviewed",
        "source_url": args.source_url,
        "source_path": args.source_path,
        "tags": tags,
        "summary": args.summary,
        "path": str(out_path.relative_to(ROOT)),
        "collected_at": now_iso(),
        "reviewed_at": "" if args.status == "quarantine" else now_iso(),
    }
    append_meta(row)
    rebuild_index()
    print(entry_id)
    print(out_path)


if __name__ == "__main__":
    main()

