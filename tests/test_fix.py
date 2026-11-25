# -*- coding: utf-8 -*-
"""fix() 的测试：能修的要修对，不能修的要老实说不能修。

注意每个「乱码」都是现场造出来的（encode 再 decode），
这样测试不依赖任何外部样例文件。
"""

import conftest  # noqa: F401  （把 src 加进 sys.path，见 conftest.py）
import unittest

from mojibake_fixer import fix


class FixTest(unittest.TestCase):
    def test_gbk_mojibake(self):
        """UTF-8 字节被 GBK 读成「浣犲ソ」，应该改回「你好」。"""
        broken = "你好".encode("utf-8").decode("gbk")
        self.assertNotEqual(broken, "你好")  # 先确认前提：它确实是乱码

        result = fix(broken)
        self.assertTrue(result.changed)
        self.assertEqual(result.text, "你好")
        self.assertIsNotNone(result.method)
        self.assertIn("gbk", result.method)
        self.assertTrue(result.message)

    def test_latin1_mojibake(self):
        """UTF-8 字节被 Latin-1 一个字节一个字节读，应该改回「你好」。"""
        broken = "你好".encode("utf-8").decode("latin-1")
        self.assertNotEqual(broken, "你好")

        result = fix(broken)
        self.assertTrue(result.changed)
        self.assertEqual(result.text, "你好")
        self.assertIsNotNone(result.method)
        self.assertIn("latin1", result.method)

    def test_kun_jin_kao_is_irreversible(self):
        """「锟斤拷」是替换符残骸，只能拒绝修复并说明原因。"""
        result = fix("锟斤拷")
        self.assertFalse(result.changed)
        self.assertEqual(result.text, "锟斤拷")
        self.assertIsNone(result.method)
        self.assertIn("不可逆", result.message)

    def test_normal_chinese_stays_untouched(self):
        """正常中文不能被「修」坏——这是最重要的一条。"""
        text = "这是一段正常的中文"
        result = fix(text)
        self.assertFalse(result.changed)
        self.assertEqual(result.text, text)

    def test_plain_ascii_stays_untouched(self):
        text = "hello world"
        result = fix(text)
        self.assertFalse(result.changed)
        self.assertEqual(result.text, text)

    def test_empty_text(self):
        result = fix("")
        self.assertFalse(result.changed)
        self.assertEqual(result.text, "")
        self.assertTrue(result.message)


if __name__ == "__main__":
    unittest.main()
