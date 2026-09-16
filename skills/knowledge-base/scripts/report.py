# -*- coding: utf-8 -*-
from collections import Counter

from kb_common import read_meta


def main() -> None:
    rows = read_meta()
    print(f"total={len(rows)}")
    print("by_status=" + str(dict(Counter(row.get("status", "") for row in rows))))
    print("by_type=" + str(dict(Counter(row.get("type", "") for row in rows))))
    print("unreviewed:")
    for row in rows:
        if row.get("status") == "quarantine":
            print(f"- {row.get('id')} | {row.get('type')} | {row.get('title')}")


if __name__ == "__main__":
    main()

