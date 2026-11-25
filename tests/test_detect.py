# -*- coding: utf-8 -*-
"""detect() 的测试：只验证「排序」和「不崩」，不锁死具体分数。

分数是人为定的启发式，会随规则微调；锁死它只会让测试变成负担。
"""

import conftest  # noqa: F401  （把 src 加进 sys.path，见 conftest.py）
import unittest

from mojibake_fixer import detect


class DetectTest(unittest.TestCase):
    def test_utf8_chinese_ranks_first(self):
        """UTF-8 的「你好」应该被认成 UTF-8。"""
        candidates = detect("你好".encode("utf-8"))
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].encoding, "utf-8")
        self.assertEqual(candidates[0].text, "你好")
        self.assertTrue(candidates[0].reason)

    def test_gb18030_chinese_ranks_first(self):
        """GB18030 的「你好」（C4 E3 BA C3）不是合法 UTF-8，应该认成 GB18030。

        Big5 也能把这段字节解成两个汉字（「斕疑」），所以这条测试实际在检验
        「同分时更常见的编码优先」这条规则。
        """
        candidates = detect("你好".encode("gb18030"))
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].encoding, "gb18030")
        self.assertEqual(candidates[0].text, "你好")

    def test_pure_ascii(self):
        """纯 ASCII 在所有候选里都解得出，排第一的应该是 UTF-8。"""
        candidates = detect(b"hello world")
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].text, "hello world")
        self.assertIn(candidates[0].encoding, ("utf-8", "latin-1", "ascii"))

    def test_empty_bytes(self):
        """空字节串不能崩，也不该抛异常。"""
        candidates = detect(b"")
        self.assertIsInstance(candidates, list)
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].text, "")
        self.assertEqual(detect(b"", top=1)[0].text, "")

    def test_top_limits_result(self):
        candidates = detect("你好".encode("utf-8"), top=2)
        self.assertLessEqual(len(candidates), 2)

    def test_utf8_bom(self):
        """带 BOM 的 UTF-8 应该优先认出 utf-8-sig，否则 BOM 会混进正文。"""
        data = b"\xef\xbb\xbf" + "你好".encode("utf-8")
        candidates = detect(data)
        self.assertEqual(candidates[0].encoding, "utf-8-sig")
        self.assertEqual(candidates[0].text, "你好")

    def test_compressed_noise_does_not_crash(self):
        """随便一段二进制也不能让打分崩掉。"""
        candidates = detect(bytes(range(256)))
        self.assertIsInstance(candidates, list)


if __name__ == "__main__":
    unittest.main()
