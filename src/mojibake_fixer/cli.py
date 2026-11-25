# -*- coding: utf-8 -*-
"""命令行入口。

用法：

    python -m mojibake_fixer <文件> [--json] [--fix] [--top N]
    python -m mojibake_fixer -              # 从 stdin 读字节

设计上的两个小决定：

1. 启动时把 stdout/stderr 切成 UTF-8 + errors="replace"。
   Windows 控制台默认是 GBK 代码页，直接打印会导致 `UnicodeEncodeError`；
   宁可把个别打不出的字换成 `?`，也不要让整个程序崩在一个 print 上。
2. 输出里不用 emoji，只用 [OK] / [?] / [X]。老式控制台字体画不出 emoji，
   显示成方块比不显示还糟。
"""

import argparse
import json
import os
import sys

from . import __version__
from .detect import detect
from .fix import FixResult, fix

EXIT_OK = 0
EXIT_USAGE = 2  # 参数/文件问题：和 grep 等工具的习惯保持一致

PREVIEW_LIMIT = 80  # 终端里一行最多展示多少字符
JSON_TEXT_LIMIT = 200  # --json 里内嵌文本最多带多少字符


def _setup_stdio():
    """把 stdout/stderr 设成 UTF-8，避免 Windows 控制台报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            # 被重定向成不支持 reconfigure 的对象时（比如某些测试替身）就算了
            pass


def _preview(text, limit=PREVIEW_LIMIT):
    """把文本压成一行，方便在终端里看。"""
    if not text:
        return ""
    flat = text.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    if len(flat) > limit:
        flat = flat[:limit] + "...(共 %d 字符)" % len(text)
    return flat


def _clip(text, limit=JSON_TEXT_LIMIT):
    """截断但保持原样（保留换行），给 --json 用。"""
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="mojibake-fixer",
        description="猜一段字节的编码，并尝试修复被误解出来的乱码文本。",
    )
    parser.add_argument(
        "path",
        help="要分析的文件路径；传 - 表示从标准输入读字节",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="输出 JSON（stdout 只有 JSON，方便接管道）",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        dest="do_fix",
        help="对最佳候选解码出的文本调用 fix()，打印修复前后对照",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        metavar="N",
        help="展示前 N 个候选编码（默认 3）",
    )
    return parser


def _read_source(path):
    """读入原始字节，返回 (bytes, 显示用的名字)。"""
    if path == "-":
        return sys.stdin.buffer.read(), "<stdin>"

    if os.path.isdir(path):
        raise IsADirectoryError(path)
    with open(path, "rb") as handle:
        return handle.read(), path


def _candidates_payload(candidates):
    payload = []
    for candidate in candidates:
        text, truncated = _clip(candidate.text)
        payload.append(
            {
                "encoding": candidate.encoding,
                "score": candidate.score,
                "reason": candidate.reason,
                "text": text,
                "truncated": truncated,
            }
        )
    return payload


def _print_json(name, data, candidates, best, result):
    payload = {
        "file": name,
        "size": len(data),
        "candidates": _candidates_payload(candidates),
        "fix": None,
    }

    if result is not None:
        before, before_truncated = _clip(best.text) if best is not None else ("", False)
        after, after_truncated = _clip(result.text)
        payload["fix"] = {
            "changed": result.changed,
            "method": result.method,
            "message": result.message,
            "best_encoding": best.encoding if best is not None else None,
            "before": before,
            "before_truncated": before_truncated,
            "after": after,
            "after_truncated": after_truncated,
        }

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_human(name, data, candidates, best, result):
    print("mojibake-fixer %s" % __version__)
    print("文件: %s" % name)
    print("大小: %d 字节" % len(data))
    print("")

    if not candidates:
        print("[X] 这段字节没有任何候选编码能严格解码，可能不是文本")
        return

    print("[OK] 猜测编码（共 %d 个候选，按可信度排序）:" % len(candidates))
    for index, candidate in enumerate(candidates, 1):
        print("  %d) %-11s 分数 %5.1f" % (index, candidate.encoding, candidate.score))
        print("     理由: %s" % candidate.reason)
    print("")

    if result is None:
        print("[?] 加 --fix 可以继续尝试修复最佳候选解码出的文本")
        return

    print("[?] 修复（对最佳候选 %s 解码出的文本）" % best.encoding)
    if result.changed:
        print("[OK] 已修复，method=%s" % result.method)
        print("  修复前: %s" % _preview(best.text))
        print("  修复后: %s" % _preview(result.text))
        print("  说明: %s" % result.message)
    else:
        print("[X] 未修复: %s" % result.message)
        print("  文本保持原样: %s" % _preview(best.text))


def main(argv=None):
    """命令行主函数。返回退出码，方便被 `__main__.py` 和测试直接调用。"""
    _setup_stdio()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.top < 1:
        sys.stderr.write("[X] --top 必须是大于 0 的整数\n")
        return EXIT_USAGE

    try:
        data, name = _read_source(args.path)
    except FileNotFoundError:
        sys.stderr.write("[X] 文件不存在: %s\n" % args.path)
        return EXIT_USAGE
    except IsADirectoryError:
        sys.stderr.write("[X] 这是一个目录，不是文件: %s\n" % args.path)
        return EXIT_USAGE
    except PermissionError:
        sys.stderr.write("[X] 没有权限读取: %s\n" % args.path)
        return EXIT_USAGE
    except OSError as error:
        sys.stderr.write("[X] 读取失败: %s (%s)\n" % (args.path, error))
        return EXIT_USAGE

    candidates = detect(data, top=args.top)
    best = candidates[0] if candidates else None

    result = None
    if args.do_fix:
        if best is None:
            result = FixResult(
                text="",
                changed=False,
                method=None,
                message="没有任何编码能严格解码这段字节，无法修复",
            )
        else:
            result = fix(best.text)

    if args.as_json:
        _print_json(name, data, candidates, best, result)
    else:
        _print_human(name, data, candidates, best, result)

    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - 只为方便 `python -m`
    sys.exit(main())
