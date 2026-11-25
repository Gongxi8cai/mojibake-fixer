# -*- coding: utf-8 -*-
"""CLI 的测试：用 subprocess 真的跑一次 `python -m mojibake_fixer`。

为什么不用「直接调用 main()」：那样测的是函数，不是命令行。
这里关心的是终端用户实际会遇到的两种事——能出 JSON、出错给退出码。
"""

import conftest  # noqa: F401  （把 src 加进 sys.path，见 conftest.py）
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")


def _run_cli(args, stdin_bytes=None):
    """起一个子进程跑 CLI，返回 (退出码, stdout 文本, stderr 文本)。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-m", "mojibake_fixer"] + list(args),
        input=stdin_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    return (
        completed.returncode,
        completed.stdout.decode("utf-8", "replace"),
        completed.stderr.decode("utf-8", "replace"),
    )


class CliTest(unittest.TestCase):
    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "nihao.txt"
            sample.write_bytes("你好".encode("utf-8"))

            code, stdout, stderr = _run_cli([str(sample), "--json"])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)  # 断言 stdout 是纯 JSON
            self.assertIn("candidates", payload)
            self.assertGreaterEqual(len(payload["candidates"]), 1)
            self.assertEqual(payload["candidates"][0]["encoding"], "utf-8")
            self.assertEqual(payload["size"], len("你好".encode("utf-8")))

    def test_json_with_fix(self):
        """--fix --json 时，fix 字段要带上可读的修复结论。"""
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "mojibake.txt"
            # 文件里存的是「浣犲ソ」这段乱码文本本身（用 UTF-8 存盘）
            broken_text = "你好".encode("utf-8").decode("gbk")
            sample.write_bytes(broken_text.encode("utf-8"))

            code, stdout, stderr = _run_cli([str(sample), "--json", "--fix"])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["candidates"][0]["encoding"], "utf-8")
            self.assertIsNotNone(payload["fix"])
            self.assertTrue(payload["fix"]["changed"])
            self.assertEqual(payload["fix"]["after"], "你好")

    def test_missing_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "not-here.txt"
            code, stdout, stderr = _run_cli([str(missing)])
            self.assertEqual(code, 2)
            self.assertIn("文件不存在", stderr)
            self.assertEqual(stdout, "")

    def test_directory_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = _run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("目录", stderr)

    def test_stdin_bytes(self):
        """`-` 表示从标准输入读字节。"""
        data = "你好".encode("utf-8")
        code, stdout, stderr = _run_cli(["-", "--json"], stdin_bytes=data)
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["file"], "<stdin>")
        self.assertEqual(payload["candidates"][0].get("text"), "你好")

    def test_human_output_has_no_emoji(self):
        """人读的输出只用 [OK]/[?]/[X]，不用 emoji（老控制台画不出来）。"""
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "plain.txt"
            sample.write_bytes(b"hello")
            code, stdout, stderr = _run_cli([str(sample)])
            self.assertEqual(code, 0, stderr)
            self.assertIn("[OK]", stdout)
            emoji = [ch for ch in stdout if 0x1F300 <= ord(ch) <= 0x1FAFF]
            self.assertEqual(emoji, [])


if __name__ == "__main__":
    unittest.main()
