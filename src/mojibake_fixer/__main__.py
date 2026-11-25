# -*- coding: utf-8 -*-
"""让 `python -m mojibake_fixer` 可以跑起来。

真正的工作在 cli.main() 里；这里只负责把它接进 `-m` 的入口点。
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
