# -*- coding: utf-8 -*-
"""mojibake-fixer：猜编码（detect）与修乱码（fix）的教学用玩具版。

三个学习项目里的第三个：
- `file-detective`：看魔数，认文件类型
- `byte-xray`：把字节摊开给人看
- `mojibake-fixer`（本项目）：字节已经是文本了，但被用错编码读了一遍

对外只暴露四个名字，其余都是实现细节：

    from mojibake_fixer import Candidate, detect, FixResult, fix

    >>> detect("你好".encode("utf-8"))[0].encoding
    'utf-8'
    >>> fix("浣犲ソ").text
    '你好'
"""

from .detect import Candidate, detect
from .fix import FixResult, fix

__version__ = "0.1.0"

__all__ = ["Candidate", "detect", "FixResult", "fix", "__version__"]
