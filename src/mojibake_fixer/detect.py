# -*- coding: utf-8 -*-
"""猜编码：给一段字节，按「人看得懂的理由」排出最可能的几种编码。

为什么这么设计（给初学者）：

1. 只用标准库。`chardet` 之所以准，是因为它统计了每种编码里字节的分布；
   我们这里只写几条人能用一句中文解释清楚的规则，所以每个分数从哪来都能说明白。
2. 严格解码。`bytes.decode(enc)` 默认就是 `errors="strict"`，解不开会抛
   `UnicodeDecodeError`——这正是「这种编码不可能」的最强证据，直接排除。
3. 只排序，不拍板。乱码问题天生没有唯一答案（同一段字节可以同时是合法的
   GBK 和合法的 Shift-JIS），工具的任务是给出候选和理由，最后决定的是人。
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Candidate:
    """一种「可能的解码结果」。"""

    encoding: str
    text: str
    score: float
    reason: str  # 为什么给它这个分，中文短句


# 候选编码的固定顺序：既决定遍历顺序，也决定「同分时谁排前面」。
# 依据是中文互联网上的出现频率：UTF-8 最常见，GB18030 次之，UTF-16 少见，
# CP1252 / Latin-1 基本只当兜底（Latin-1 永远能解开任何字节，没有信息量）。
ENCODINGS = (
    "utf-8",
    "utf-8-sig",
    "gb18030",
    "big5",
    "shift_jis",
    "euc-kr",
    "utf-16-le",
    "utf-16-be",
    "cp1252",
    "latin-1",
)

# 同分时的排序权重，数字越小越靠前。
PRIORITY = dict((name, index) for index, name in enumerate(ENCODINGS))

DISPLAY_NAME = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8（带 BOM）",
    "gb18030": "GB18030",
    "big5": "Big5",
    "shift_jis": "Shift-JIS",
    "euc-kr": "EUC-KR",
    "utf-16-le": "UTF-16 LE",
    "utf-16-be": "UTF-16 BE",
    "cp1252": "CP1252",
    "latin-1": "Latin-1",
}

# CJK 统一汉字所在的码位区间（基本区 + 扩展 A + 兼容区）。
# 中文文本解对了，这些区间里的字符就会大量出现，所以它们是「解对了」的信号。
HAN_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0xF900, 0xFAFF),
)

# 常用中文标点：中文文本里几乎必然出现，也是「解对了」的信号。
CJK_PUNCTUATION = "，。、；：？！“”‘’（）《》〈〉【】…—～·「」『』"

# 典型的乱码片段。它们出现基本只有一个解释：解码器用错了。
# 「锟斤拷」是 UTF-8 被 GBK 解过、再被 UTF-8 解一次留下的残骸（不可逆）。
MOJIBAKE_FRAGMENTS = ("锟斤拷", "Ã", "â€", "ï¿½", "\ufffd")

# 「锟斤拷」三个字的 UTF-8 字节。如果这串字节出现在文件里，那就说明
# 文件本身就是 UTF-8——否则这三个字不会以这种字节形式存在（见 _score_one 的特例）。
IRREVERSIBLE_UTF8 = "锟斤拷".encode("utf-8")


def _count_han(text):
    """统计文本里的 CJK 统一汉字个数。"""
    count = 0
    for char in text:
        code = ord(char)
        for low, high in HAN_RANGES:
            if low <= code <= high:
                count += 1
                break
    return count


def _count_punctuation(text):
    """统计常用中文标点个数。"""
    return sum(1 for char in text if char in CJK_PUNCTUATION)


def _is_control(char):
    """是不是「不该出现在正常文本里」的控制字符。

    `\\t`、`\\n`、`\\r` 是文本里合法的空白，不扣分；
    其余 C0 控制符、DEL 和 C1 控制符出现，说明解错了。
    """
    code = ord(char)
    if char in "\t\n\r":
        return False
    if code < 0x20:
        return True
    return 0x7F <= code <= 0x9F


def _count_utf8_sequences(data):
    """数一数字节里有多少个「合法的 UTF-8 多字节序列」。

    这是本工具唯一用到概率的地方：一个随机字节流刚好凑成合法 UTF-8 多字节
    序列的概率很低（首字节和后续字节的取值范围被严格限制），所以「能解成
    UTF-8」本身就是证据。反过来说，GBK 文本几乎不可能同时是合法 UTF-8。

    只有文本已经严格解码成功时才会调用本函数，所以这里不用再校验续字节。
    """
    count = 0
    index = 0
    length = len(data)
    while index < length:
        byte = data[index]
        if byte < 0x80:
            index += 1
        elif byte < 0xE0:
            count += 1
            index += 2
        elif byte < 0xF0:
            count += 1
            index += 3
        else:
            count += 1
            index += 4
    return count


def _looks_like_latin1_mojibake(text):
    """UTF-8 解出的文本是不是「全是西欧单字节字符」？

    为什么要单独看这个：UTF-8 里的汉字是 3 字节一组，文本长度常是 3 的倍数，
    GBK 两两配对时经常剩下一个字节解不开；但 Latin-1 乱码（`ä½ å¥½`）每个
    字符只占 2 个 UTF-8 字节，长度总是偶数，GBK 恰好能完整配对成罕见汉字。
    所以「解出来全是 U+0080–U+00FF」是个很强的指纹：字节其实是 UTF-8，
    内容才是被 Latin-1 误读过的文本。
    """
    non_ascii = [char for char in text if ord(char) > 0x7F]
    if len(non_ascii) < 2:
        return False
    return all(0x80 <= ord(char) <= 0xFF for char in non_ascii)


def _score_one(text, encoding, data):
    """给一种「解码成功」的结果打分，返回 (分数, 理由片段列表)。

    分数只是相对排序用的，不必纠结绝对数值；重要的是每条规则都能讲清为什么。
    """
    score = 0.0
    notes = []

    # 规则 1：解出汉字/中文标点，说明解码器很可能选对了。
    han = _count_han(text)
    punctuation = _count_punctuation(text)
    if han or punctuation:
        gain = 2 * (han + punctuation)
        score += gain
        notes.append("汉字 %d 个、中文标点 %d 个 %+d" % (han, punctuation, gain))

    # 规则 2：可打印 ASCII 占比高，说明这段文本不像二进制被硬解成文字。
    printable_ascii = sum(1 for char in text if " " <= char <= "~")
    if text and printable_ascii / len(text) >= 0.8:
        score += 1
        notes.append("可打印 ASCII 占 %d%% +1" % int(100 * printable_ascii / len(text)))

    # 规则 3：控制字符是「解码错位」的典型症状。
    controls = sum(1 for char in text if _is_control(char))
    if controls:
        score -= 6 * controls
        notes.append("疑似控制字符 %d 个 %+d" % (controls, -6 * controls))

    # 规则 4：出现乱码片段，几乎可以确定这是误读的结果。
    for fragment in MOJIBAKE_FRAGMENTS:
        hits = text.count(fragment)
        if hits:
            score -= 15 * hits
            notes.append("出现乱码片段「%s」%d 次 %+d" % (fragment, hits, -15 * hits))

    # 规则 5：私用区字符（U+E000–U+F8FF）在正常文本里几乎不出现。
    private = sum(1 for char in text if 0xE000 <= ord(char) <= 0xF8FF)
    if private:
        score -= 5 * private
        notes.append("私用区字符 %d 个 %+d" % (private, -5 * private))

    # 规则 6：Latin-1 能解开一切字节。纯 ASCII 时它和 UTF-8 结果一样，
    # 却什么信息都没提供，所以扣分让它排到后面。
    if encoding == "latin-1" and text.isascii():
        score -= 3
        notes.append("Latin-1 谁都能解、又没有非 ASCII，无信息量 -3")

    # 规则 7：字节里大量 0x00——这是 UTF-16 的指纹（ASCII 字符高位补 0），
    # 对单字节编码和 UTF-8 来说则是「这不是文本」的信号。
    total = len(data)
    if total:
        nul_ratio = data.count(0) / float(total)
        if nul_ratio >= 0.2:
            if encoding in ("utf-16-le", "utf-16-be"):
                score += 3
                notes.append("0x00 占 %d%%，像 UTF-16 +3" % int(100 * nul_ratio))
            else:
                score -= 3
                notes.append("0x00 占 %d%%，不像单字节/UTF-8 文本 -3" % int(100 * nul_ratio))

    # 规则 8：合法的 UTF-8 多字节序列是结构证据。随机字节很难凑成合法 UTF-8，
    # 所以每出现一个就加分；但最多加 5 分，避免这一条压倒所有其他规则。
    if encoding in ("utf-8", "utf-8-sig"):
        sequences = _count_utf8_sequences(data)
        if sequences:
            bonus = min(5, sequences)
            score += bonus
            notes.append("合法的 UTF-8 多字节序列 %d 个 %+d" % (sequences, bonus))

    # 规则 9：带 BOM 的 UTF-8 该用 utf-8-sig 读，否则 BOM 会变成正文里的
    # 一个零宽字符（U+FEFF），用户看不见但会让字符串比较失败。
    if data.startswith(b"\xef\xbb\xbf"):
        if encoding == "utf-8-sig":
            score += 2
            notes.append("字节以 UTF-8 BOM 开头 +2")
        elif encoding == "utf-8":
            score -= 2
            notes.append("BOM 会被当成正文里的零宽字符 -2")

    # 规则 10（特例）：字节里出现「锟斤拷」的 UTF-8 形式（e9 94 9f e6 96 a4
    # e6 8b b7），说明这段字节本身就是 UTF-8——除了用 UTF-8 写下这三个字，
    # 很难有别的解释。此时规则 4 的扣分是「内容警告」而不是「误读证据」，
    # 所以加回 20 分（抵消 -15 后还有 5 分余量）。
    if encoding in ("utf-8", "utf-8-sig") and IRREVERSIBLE_UTF8 in data:
        score += 20
        notes.append("字节里有「锟斤拷」的 UTF-8 形式 +20：这段字节就是 UTF-8，但内容已不可逆")

    # 规则 11：UTF-8 解出来全是西欧单字节字符（U+0080–U+00FF），很像
    # 「UTF-8 被 Latin-1 误读」的文本。这种字节能被 GBK 两两配对成罕见汉字，
    # 所以不特殊处理的话会被双字节编码抢走第一名，见 _looks_like_latin1_mojibake。
    if encoding in ("utf-8", "utf-8-sig") and _looks_like_latin1_mojibake(text):
        score += 10
        notes.append("解出全是西欧单字节字符 +10：像是 UTF-8 被 Latin-1 误读，字节其实是 UTF-8")

    return score, notes


def _build_reason(encoding, notes):
    """把编码名和理由片段拼成一句中文。"""
    name = DISPLAY_NAME.get(encoding, encoding)
    if not notes:
        return name + " 严格解码通过，但没有可计分的特征"
    return name + " 严格解码通过，" + "；".join(notes)


def detect(data, top=3):
    """猜编码。

    :param data: 原始字节（bytes / bytearray 均可）
    :param top: 最多返回几个候选；小于 0 当作 0
    :return: 按可信度降序排列的 Candidate 列表
    """
    raw = bytes(data)
    limit = max(0, int(top))

    candidates = []
    for encoding in ENCODINGS:
        try:
            text = raw.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            # 严格解码失败 = 这段字节不可能是这种编码，直接排除。
            continue

        score, notes = _score_one(text, encoding, raw)
        score = round(score, 1)
        if score == 0:
            score = 0.0  # 避免出现 -0.0 这种让人困惑的显示
        candidates.append(
            Candidate(
                encoding=encoding,
                text=text,
                score=score,
                reason=_build_reason(encoding, notes),
            )
        )

    # 分数高的在前；同分时用 PRIORITY（更常见的编码）决定先后。
    candidates.sort(key=lambda item: (-item.score, PRIORITY.get(item.encoding, 99)))
    return candidates[:limit]
