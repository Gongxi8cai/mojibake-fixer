# -*- coding: utf-8 -*-
"""让测试在「没 pip install」的情况下也能 import mojibake_fixer。

pytest 会自动加载 conftest.py；标准库 unittest 不会，所以三个测试文件
开头都显式 `import conftest`，借这一行把 src 放进 sys.path。

这样两条命令都能跑：

    python -m unittest discover -s tests -v
    pytest
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
