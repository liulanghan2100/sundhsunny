# -*- coding: utf-8 -*-
import argparse
import sqlite3

from kb_common import INDEX_PATH, init_db, rebuild_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the local Agent knowledge base.")
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--status", default="")
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        rebuild_index()
    con = init_db()
    where = "entries MATCH ?"
    params = [args.query]
    if args.status:
        where += " AND status = ?"
        params.append(args.status)
    sql = (
        "SELECT id,title,type,status,summary,path,source_url,bm25(entries) AS score "
        f"FROM entries WHERE {where} ORDER BY score LIMIT ?"
    )
    params.append(args.limit)
    try:
        rows = con.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        rebuild_index()
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()

    for row in rows:
        print("---")
        print(f"id: {row[0]}")
        print(f"title: {row[1]}")
        print(f"type: {row[2]}")
        print(f"status: {row[3]}")
        print(f"summary: {row[4]}")
        print(f"path: {row[5]}")
        print(f"source: {row[6]}")


if __name__ == "__main__":
    main()

