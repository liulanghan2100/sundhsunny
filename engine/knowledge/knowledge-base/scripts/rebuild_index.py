# -*- coding: utf-8 -*-
from kb_common import rebuild_index


if __name__ == "__main__":
    count = rebuild_index()
    print(f"indexed={count}")

