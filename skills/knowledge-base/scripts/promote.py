# -*- coding: utf-8 -*-
import argparse
import shutil

from kb_common import ROOT, read_meta, rebuild_index, target_dir, write_meta, now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote a quarantined knowledge item to trusted storage.")
    parser.add_argument("entry_id")
    args = parser.parse_args()

    rows = read_meta()
    changed = False
    for row in rows:
        if row.get("id") != args.entry_id:
            continue
        old_path = ROOT / row["path"]
        out_dir = target_dir(row["type"], "trusted")
        out_dir.mkdir(parents=True, exist_ok=True)
        new_path = out_dir / old_path.name
        if old_path.exists() and old_path.resolve() != new_path.resolve():
            shutil.move(str(old_path), str(new_path))
        row["path"] = str(new_path.relative_to(ROOT))
        row["status"] = "trusted"
        row["trust_level"] = "reviewed"
        row["reviewed_at"] = now_iso()
        changed = True
        print(new_path)
        break
    if not changed:
        raise SystemExit(f"Entry not found: {args.entry_id}")
    write_meta(rows)
    rebuild_index()


if __name__ == "__main__":
    main()

