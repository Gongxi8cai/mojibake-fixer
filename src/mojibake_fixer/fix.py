# -*- coding: utf-8 -*-
"""修乱码：拿一段「已经乱了的文本」，尝试倒回原始字符。

关键认识：乱码是「解码时用错了编码器」，不是文件坏了。只要字节本身没丢，
就可以反着走一遍：

    text.encode(错误编码)  ->  原始字节  ->  .decode("utf-8")  ->  原字符

比如 `你好` 的 UTF-8 字节是 `E4 BD A0 E5 A5 BD`，被 GBK 读成「浣犲ソ」；
把「浣犲ソ」按 GBK 编回字节，再按 UTF-8 解，就回到「你好」。

但这条路有个前提：读错的过程中没有丢东西。如果中间有人把字节替换成了
`U+FFFD`（替换符），原始字节就永久丢了——「锟斤拷」就是这种情况。
"""

from dataclasses import dataclass
from typing import Optional

# 典型的乱码片段，出现即说明解码器用错了。
# 「锟斤拷」是 UTF-8 被 GBK 解过、再被 UTF-8 解一次后留下的残骸。
MOJIBAKE_FRAGMENTS = ("锟斤拷", "Ã", "â€", "Â", "ï¿½", "\ufffd")

# CJK 统一汉字区间（基本区 + 扩展 A + 兼容区），与 detect.py 保持一致。
HAN_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0xF900, 0xFAFF),
)


@dataclass
class FixResult:
    """一次修复尝试的结果。`changed=False` 时 `text` 就是原文。"""

    text: str
    changed: bool
    method: Optional[str]  # 例如 "utf8<-gbk"、"utf8<-latin1"
    message: str  # 中文说明（不可恢复时也要说清楚）


def _is_han(char):
    code = ord(char)
    for low, high in HAN_RANGES:
        if low <= code <= high:
            return True
    return False


def count_han(text):
    """统计文本里的 CJK 统一汉字个数。"""
    return sum(1 for char in text if _is_han(char))


def count_kana_or_hangul(text):
    """统计假名（0x3040–0x30FF）与谚文（0xAC00–0xD7AF）的个数。"""
    count = 0
    for char in text:
        code = ord(char)
        if 0x3040 <= code <= 0x30FF or 0xAC00 <= code <= 0xD7AF:
            count += 1
    return count


def mojibake_signals(text):
    """数一数这段文本里有多少「乱码特征」，越大越像乱码。

    这是 `fix()` 判断「修完是不是更好了」的尺子之一。包含：

    - 经典乱码片段（`锟斤拷`、`Ã`、`â€`…）出现的次数
    - 私用区字符（U+E000–U+F8FF，正常文本几乎不会有）
    - 不该出现的控制字符（`\\t\\n\\r` 除外）
    - 中文里混进的假名/谚文：GBK 字节被误解时经常解出这种混合文本，
      比如「浣犲ソ」里的「ソ」就是日文片假名。
    """
    signals = 0
    for fragment in MOJIBAKE_FRAGMENTS:
        signals += text.count(fragment)

    for char in text:
        code = ord(char)
        if code == 0xFFFD:
            continue  # 已经在上面的乱码片段里数过一次，不重复计
        if 0xE000 <= code <= 0xF8FF:
            signals += 1
        elif char not in "\t\n\r" and code < 0x20:
            signals += 1
        elif 0x7F <= code <= 0x9F:
            signals += 1

    if count_han(text):
        signals += count_kana_or_hangul(text)

    return signals


def is_improvement(before, after):
    """修完的文本是不是真的更好了？

    只看两个指标，避免「越修越坏」：

    1. 乱码特征变少了；
    2. 或者汉字变多了（Latin-1 乱码里一个汉字都没有，修好就出现了）。

    正常中文文本重新编码再解码，汉字数不会变多、乱码特征也不会变少，
    所以会被这条判据拦下来。
    """
    if after == before:
        return False
    if mojibake_signals(after) < mojibake_signals(before):
        return True
    return count_han(after) > count_han(before)


def _has_readable_content(text):
    """结果里至少要有汉字或可打印的非空白字符，不能是一堆空白/控制符。"""
    for char in text:
        if _is_han(char):
            return True
        if char.isprintable() and not char.isspace():
            return True
    return False


def _try_utf8_from(text, codec):
    """通用套路：按 `codec`（当初用错的编码）编回字节，再按 UTF-8 解。

    三个条件全满足才算成功：严格编码/解码通过、结果可读、确实有改善。
    """
    try:
        raw = text.encode(codec, errors="strict")
        fixed = raw.decode("utf-8", errors="strict")
    except (UnicodeError, LookupError):
        return None

    if not _has_readable_content(fixed):
        return None
    if not is_improvement(text, fixed):
        return None
    return fixed


def fix(text):
    """尝试把一段乱码文本还原。返回第一个「有改善」的结果，没有就原样返回。"""
    if not isinstance(text, str):
        raise TypeError("fix() 需要已解码的 str，收到 %r" % type(text).__name__)

    if text == "":
        return FixResult(text="", changed=False, method=None, message="输入是空文本，没有可修复的内容")

    # 案例 1：锟斤拷。替换符已经把原始字节吃掉了，任何尝试都是猜。
    if "锟斤拷" in text:
        return FixResult(
            text=text,
            changed=False,
            method=None,
            message="经典不可逆乱码（UTF-8 被 GBK 解过再被 UTF-8 解），原始字节已丢失",
        )

    # 案例 2：UTF-8 字节被 GBK/GB18030 当成双字节汉字读了。
    # 只有当文本里确实有汉字时才值得试——纯 ASCII 编回字节后解 UTF-8 还是它自己。
    if count_han(text) >= 2:
        fixed = _try_utf8_from(text, "gb18030")
        if fixed is not None:
            return FixResult(
                text=fixed,
                changed=True,
                method="utf8<-gbk",
                message="文本像是 UTF-8 字节被 GBK 误解；按 GB18030 编回字节后可以用 UTF-8 严格解开",
            )

    # 案例 3：UTF-8 字节被 Latin-1 / CP1252 一个字节一个字节地读了。
    # 这类乱码里没有汉字（Ã、â€、ä½ 这些全是西欧字符），所以前提是「不含汉字」。
    if count_han(text) == 0:
        fixed = _try_utf8_from(text, "latin-1")
        if fixed is not None:
            return FixResult(
                text=fixed,
                changed=True,
                method="utf8<-latin1",
                message="文本像是 UTF-8 字节被 Latin-1 误解；按 Latin-1 编回字节后可以用 UTF-8 严格解开",
            )

        # CP1252 是 Latin-1 的「超集改良版」（补了 € 、’ 等 0x80–0x9F 位置的字符），
        # Latin-1 编不回去的文本再试它一次。
        fixed = _try_utf8_from(text, "cp1252")
        if fixed is not None:
            return FixResult(
                text=fixed,
                changed=True,
                method="utf8<-cp1252",
                message="文本像是 UTF-8 字节被 CP1252 误解；按 CP1252 编回字节后可以用 UTF-8 严格解开",
            )

    return FixResult(text=text, changed=False, method=None, message="没有识别出可逆的乱码模式")
