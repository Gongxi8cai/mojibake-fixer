# mojibake-fixer

一个只用标准库写的玩具版 `chardet` + `ftfy`：**给一段字节猜它是什么编码，给一段乱码文本试着把它救回来。**

它是「字节学习三件套」的第三件：

| 项目 | 类比 | 回答的问题 |
| --- | --- | --- |
| `file-detective`（已完成） | `file`、`binwalk` | 这堆字节是什么文件？ |
| `byte-xray`（已完成） | `xxd`、010 Editor 模板 | 这堆字节每个位置是什么意思？ |
| `mojibake-fixer`（本项目） | `chardet`、`ftfy`、`uchardet` | 这堆字节该用哪种编码读？读出来是乱码还能不能救？ |

前两个项目里，答案一旦对上就是唯一的；到这里不一样了——**「这段字节是什么编码」往往没有唯一答案**，
只能给几个候选、各自说明理由、排个序。这正是 `chardet` 这类库做的事。

---

## 一、乱码是怎么来的

乱码只有一个成因：**写的时候用编码 A 变成字节，读的时候用编码 B 还原。**

同一个汉字在不同编码里占的字节完全不同，比如「你」：

| 编码 | 字节 |
| --- | --- |
| UTF-8 | `E4 BD A0`（3 字节） |
| GBK / GB18030 | `C4 E3`（2 字节） |

一旦 A ≠ B，字节会被「按错的方式重新解释」，于是得到一串看着像文字的垃圾。

### 三种经典案例（本项目全部覆盖）

| # | 原始文本 | 用来读它的编码 | 看到的乱码 | 还能救吗 |
| --- | --- | --- | --- | --- |
| 1 | `你好` | 先 UTF-8 编码，再用 **GBK** 读 | `浣犲ソ` | ✅ 能。按 GB18030 编回字节，再用 UTF-8 解 |
| 2 | `你好` | 先 UTF-8 编码，再用 **Latin-1** 读 | `ä½ å¥½` | ✅ 能。按 Latin-1 编回字节，再用 UTF-8 解 |
| 3 | 任意中文 | 先 **GBK** 编码，再用 **UTF-8** 读 | `锟斤拷` | ❌ 不能。字节已经被替换成 `EF BF BD`，原始信息永久丢失 |

第 3 种要单独说一句：UTF-8 解码器遇到非法字节时会**丢弃并写入替换符** `U+FFFD`，
再存成 UTF-8 就是 `EF BF BD`。这种「替换」是不可逆的——原来的 `C4 E3` 已经不在了，
所以再聪明的工具也只能说「这里坏过」，变不回去。这就是网上「锟斤拷」段子的由来。

> 教学顺序提醒：本项目故意排在 `file-detective`、`byte-xray` 之后。
> 前两个项目教你「字节 → 字节」，这个项目要求你同时理解「字节层」和「文本层」，
> 还得接受「推理只能是概率性的」这件事。

---

## 二、安装

要求 Python **3.9+**，只用标准库，没有任何第三方依赖。

```bash
# 方式一：直接跑，不安装（把 src 加进 PYTHONPATH 即可）
set PYTHONPATH=src           # Windows cmd
export PYTHONPATH=src        # bash / zsh

# 方式二：可编辑安装，装完就有 mojibake-fixer 命令
pip install -e .
```

---

## 三、用法

```bash
python -m mojibake_fixer <文件>            # 猜编码
python -m mojibake_fixer <文件> --fix      # 猜编码 + 尝试修复
python -m mojibake_fixer <文件> --json     # 机器可读，stdout 只有 JSON
python -m mojibake_fixer <文件> --top 5    # 多看几个候选
python -m mojibake_fixer -                 # 从 stdin 读字节
```

仓库里的 [`samples/`](samples/) 有 4 个配套演示文件，clone 下来就能照着下面的例子跑：

| 文件 | 大小 | 内容 |
| --- | --- | --- |
| `samples/gbk.txt` | 10 字节 | 正常的 GBK 文本「你好，世界」 |
| `samples/broken-gbk.txt` | 9 字节 | UTF-8 字节被 GBK 误读后的「浣犲ソ」 |
| `samples/broken-latin1.txt` | 12 字节 | UTF-8 字节被 Latin-1 误读后的「ä½ å¥½」 |
| `samples/broken-kun.txt` | 9 字节 | 已经被替换符破坏、不可逆的「锟斤拷」 |

### 例 1：猜一个 GBK 文件

```
$ python -m mojibake_fixer samples/gbk.txt
mojibake-fixer 0.1.0
文件: samples\gbk.txt
大小: 10 字节

[OK] 猜测编码（共 3 个候选，按可信度排序）:
  1) gb18030     分数  10.0
     理由: GB18030 严格解码通过，汉字 4 个、中文标点 1 个 +10
  2) big5        分数   8.0
     理由: Big5 严格解码通过，汉字 4 个、中文标点 0 个 +8
  3) euc-kr      分数   4.0
     理由: EUC-KR 严格解码通过，汉字 1 个、中文标点 1 个 +4

[?] 加 --fix 可以继续尝试修复最佳候选解码出的文本
```

注意 `big5` 也「解成功了」——双字节编码几乎什么字节都能两两配对。所以「能解开」不等于「解对了」，
必须靠打分排序（见下一节）。

### 例 2：修复 UTF-8 被 GBK 读出来的文本

```
$ python -m mojibake_fixer samples/broken-gbk.txt --fix
mojibake-fixer 0.1.0
文件: samples\broken-gbk.txt
大小: 9 字节

[OK] 猜测编码（共 3 个候选，按可信度排序）:
  1) utf-8       分数   7.0
     理由: UTF-8 严格解码通过，汉字 2 个、中文标点 0 个 +4；合法的 UTF-8 多字节序列 3 个 +3
  2) utf-8-sig   分数   7.0
     理由: UTF-8（带 BOM） 严格解码通过，汉字 2 个、中文标点 0 个 +4；合法的 UTF-8 多字节序列 3 个 +3
  3) shift_jis   分数   6.0
     理由: Shift-JIS 严格解码通过，汉字 3 个、中文标点 0 个 +6

[?] 修复（对最佳候选 utf-8 解码出的文本）
[OK] 已修复，method=utf8<-gbk
  修复前: 浣犲ソ
  修复后: 你好
  说明: 文本像是 UTF-8 字节被 GBK 误解；按 GB18030 编回字节后可以用 UTF-8 严格解开
```

### 例 3：不可逆的「锟斤拷」

```
$ python -m mojibake_fixer samples/broken-kun.txt --fix
...
[?] 修复（对最佳候选 utf-8 解码出的文本）
[X] 未修复: 经典不可逆乱码（UTF-8 被 GBK 解过再被 UTF-8 解），原始字节已丢失
  文本保持原样: 锟斤拷
```

工具在这里的诚实很重要：**它会明确告诉你救不回来，而不是瞎猜一个结果。**

### 例 4：`--json` 给管道用

`--json` 时 **stdout 里只有 JSON**（没有标题、没有 emoji、没有彩色），错误仍然走 stderr。
不加 `--fix` 时 `"fix"` 是 `null`；长文本的 `text`/`before`/`after` 会被截到 200 字符，并用
`truncated` / `before_truncated` / `after_truncated` 标出来。

```json
{
  "file": "samples\\broken-latin1.txt",
  "size": 12,
  "candidates": [
    {
      "encoding": "utf-8",
      "score": 15.0,
      "reason": "UTF-8 严格解码通过，合法的 UTF-8 多字节序列 6 个 +5；解出全是西欧单字节字符 +10：像是 UTF-8 被 Latin-1 误读，字节其实是 UTF-8",
      "text": "ä½ å¥½",
      "truncated": false
    },
    {
      "encoding": "utf-8-sig",
      "score": 15.0,
      "reason": "UTF-8（带 BOM） 严格解码通过，合法的 UTF-8 多字节序列 6 个 +5；解出全是西欧单字节字符 +10：像是 UTF-8 被 Latin-1 误读，字节其实是 UTF-8",
      "text": "ä½ å¥½",
      "truncated": false
    }
  ],
  "fix": {
    "changed": true,
    "method": "utf8<-latin1",
    "message": "文本像是 UTF-8 字节被 Latin-1 误解；按 Latin-1 编回字节后可以用 UTF-8 严格解开",
    "best_encoding": "utf-8",
    "before": "ä½ å¥½",
    "before_truncated": false,
    "after": "你好",
    "after_truncated": false
  }
}
```

### 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 正常结束（包括「猜出来了但修不了」） |
| `2` | 输入有问题：文件不存在、传进来的是目录、没权限、`--top` 小于 1 |

### Python API

```python
from mojibake_fixer import detect, fix

for cand in detect(data, top=3):
    print(cand.encoding, cand.score, cand.reason)

result = fix("浣犲ソ")
print(result.text, result.changed, result.method)   # 你好 True utf8<-gbk
```

---

## 四、算法：为什么是这几分

全部代码都在 `src/mojibake_fixer/detect.py` 和 `fix.py` 里，没有黑箱，也没有「魔法权重」——
每一条都能用一句话解释。

### detect：先严格解码，再打分排序

候选编码固定为 10 个：`utf-8`、`utf-8-sig`、`gb18030`、`big5`、`shift_jis`、`euc-kr`、
`utf-16-le`、`utf-16-be`、`cp1252`、`latin-1`。

**第一步：严格解码。** 用 `errors="strict"` 试一遍，抛异常就排除。
这一步就能砍掉大半：一段 UTF-8 字节几乎不可能同时是合法 GBK。
唯一的例外是 `latin-1`——它把每个字节都映射成一个字符，**永远成功**，
所以它只作为「兜底」存在，并且默认扣分。

**第二步：给活下来的每一种编码打分。**

| # | 规则 | 分值 | 为什么 |
| --- | --- | --- | --- |
| 1 | 每出现一个 CJK 统一汉字 / 常用中文标点 | **+2 / 个** | 中文文本解对了，这些字符会大量出现 |
| 2 | 可打印 ASCII 占比 ≥ 80%（文本非空） | **+1** | 说明像正常文本，不是二进制被硬解成字符 |
| 3 | 控制字符（`\t\n\r` 除外，含 0x7F–0x9F） | **-6 / 个** | 解码错位的典型症状 |
| 4 | 典型乱码片段 `锟斤拷`、`Ã`、`â€`、`ï¿½`、`�` | **-15 / 次** | 出现它们几乎可以断定用错了编码 |
| 5 | 私用区字符 U+E000–U+F8FF | **-5 / 个** | 正常文本里几乎不出现，是错位的信号 |
| 6 | `latin-1` 且文本是纯 ASCII | **-3** | 谁都能解、又没提供任何信息，不该排前面 |
| 7 | 字节里 `0x00` 占比 ≥ 20% | utf-16 系 **+3**，其余 **-3** | ASCII 文本存成 UTF-16 时高位全是 0，这是 UTF-16 的指纹 |
| 8 | 合法的 UTF-8 多字节序列个数 | **+min(5, n)** | 随机字节很难凑成合法 UTF-8，这是结构证据 |
| 9 | 字节以 UTF-8 BOM `EF BB BF` 开头 | `utf-8-sig` **+2**，`utf-8` **-2** | BOM 该被去掉，否则会变成正文里的零宽字符 U+FEFF |
| 10 | 字节里出现「锟斤拷」的 UTF-8 形式 | utf-8 系 **+20** | 这段字节**就是** UTF-8（否则这三个字不会这么排列），规则 4 的扣分在这里是「内容警告」而非「误读证据」 |
| 11 | UTF-8 解出来全是西欧单字节字符（U+0080–U+00FF） | utf-8 系 **+10** | 典型是「UTF-8 被 Latin-1 误读」的文本；这类字节长度总是偶数，正好被 GBK 两两配成罕见汉字，不加这条会被双字节编码抢走第一名 |

规则 7–11 是在前 6 条之上补的，目的都只有一个：**让结构证据压过「能解出汉字」这种弱证据。**
其中 7、8、9 处理 UTF-16 指纹、UTF-8 结构证据和 BOM；10、11 是两个特例，理由如下。

规则 10 和 11 值得多解释一句，因为它们是「特例」，但它们都有硬理由：

- **规则 10**：`锟斤拷` 的 UTF-8 字节是 `E9 94 9F E6 96 A4 E6 8B B7`。这串字节出现在文件里，
  基本只能是「有人把这三个字用 UTF-8 存了下来」。既然字节本身就是 UTF-8，
  那规则 4 的 -15 惩罚就罚错了对象，于是加回 20 分抵消（净 +5，保证它排第一）。
- **规则 11**：Latin-1 乱码的每个字符只占 **2 个** UTF-8 字节，长度总是偶数；
  UTF-8 汉字是 **3 字节**一组，长度常为 3 的倍数。GBK 需要两两配对，
  所以它对 Latin-1 乱码几乎必然「解成功」（解出 `盲陆聽氓楼陆` 这种罕见字），
  对真正的 UTF-8 中文却经常在结尾多出一个字节解不开。
  「解出来全是 U+0080–U+00FF」正好相反地指向 UTF-8，所以给它 +10。

**第三步：排序。** 分数降序；**同分**时按「更常见」优先：

```
utf-8 > utf-8-sig > gb18030 > big5 > shift_jis > euc-kr > utf-16-le > utf-16-be > cp1252 > latin-1
```

这一条是必须的：`你好` 的 GB18030 字节 `C4 E3 BA C3` 用 Big5 恰好也解出两个汉字 `斕疑`，
两条规则 1 得分一样。没有同分优先级，「是不是中文」就分不出高下了。

### fix：按顺序试，第一个「有改善」的就返回

```
1. 文本里含「锟斤拷」           → 直接认输，changed=False
2. 汉字 ≥ 2：GB18030 编回字节 → 用 UTF-8 严格解 → method = utf8<-gbk
3. 汉字 == 0：Latin-1 编回字节 → 用 UTF-8 严格解 → method = utf8<-latin1
              不行再试 cp1252（Windows 上常见的 Latin-1 变体）→ method = utf8<-cp1252
4. 都不行                      → 原样返回，message = 没有识别出可逆的乱码模式
```

注意第 2 步用的是 `gb18030` 而不是 `gbk`：GB18030 是 GBK 的超集，
能多解一批生僻字，标成 `utf8<-gbk` 只是为了让 method 好认。

**「有改善」的判据**写在 `fix.is_improvement(before, after)` 里，两个条件满足其一才算：

1. 修复后文本必须**真的变了**（`after != before`）；否则不叫改善。
2. 乱码特征计数**下降**（`mojibake_signals`：乱码片段出现次数 + 私用区字符数 + 控制字符数，
   且文本含汉字时再加上片假名/谚文数量——它们是「GBK 解错了 CJK 字节」的典型残留），
   **或者** CJK 汉字数量上升。

这个判据是对着「别越修越坏」设计的：正常中文 `这是一段正常的中文` 走第 2 步时，
`encode("gb18030")` 得到的字节不是合法 UTF-8，严格解码直接失败，于是原样返回 `changed=False`。

---

## 五、已知限制

先把话说在前面：**这是一个教学用的启发式工具，不是 `chardet` 的替代品。**

- **短文本会误判。** 只有几个字节时，证据太少。`你好` 的 GBK 字节同时能被 Big5 解成两个汉字，
  我们的排序只是「按常见程度赌一把」，不是证明。
- **双字节编码之间很难区分。** `gb18030`、`big5`、`shift_jis`、`euc-kr` 都能解开大量偶数长度字节。
  我们没有字频表，只能用「码位是不是落在 CJK 区」判断，所以「解出罕见汉字」和
  「解出常用汉字」拿一样的分。真正的 `chardet` 会做统计模型。
- **Latin-1 乱码被存成 UTF-8 时只能缓解。** 规则 11 处理的是「解出来全是西欧字符」的情况；
  一旦乱码文本里混了较多 ASCII（比如 `ä½ å¥½, world` 里有一堆英文），
  GBK 仍可能靠汉字数量反超。此时请用 `--top` 看候选，或直接对文本调用 `fix()`。
- **`锟斤拷` 只能识别，不能恢复。** 这是信息论层面的事实，不是实现缺陷。
- **只认固定 10 种编码。** 不支持 `euc-jp`、`iso-2022-jp`、`utf-32`、`cp932` 的变体差异等。
- **`fix()` 只处理「单层误读」。** 多重误读（比如 GBK→Latin-1→UTF-8 叠了两次）救不回来。
- **`--fix` 只作用于最佳候选。** 如果第一名猜错了，修复自然不会成功——这符合「可解释」的取舍，
  换来的是「你能看清它为什么这么猜」。

---

## 六、路线图

- [ ] 用「常用字频率表」（可内置几百个高频字）替代纯码位判断，让 GBK 与 Big5 能真正分出高下
- [ ] 多重误读的递归修复，并给出 `utf8<-gbk<-latin1` 这种修复链
- [ ] 增加 `euc-jp`、`iso-2022-jp`、`utf-32`、`cp932` 候选
- [ ] `--fix -o <文件>` 直接写出修复后的 UTF-8 文件
- [ ] 与 `chardet` / `ftfy` 做对比实验：同一批样本，谁的 Top-1 更准
- [ ] 补 pytest 版测试（现在只依赖 `unittest`，为了零依赖）
- [ ] 把打分层抽成可插拔的 `Rule` 列表，方便教学时一条条打开/关闭

---

## 七、目录结构

```
mojibake-fixer/
  src/mojibake_fixer/
    __init__.py      公共 API（导出 Candidate / detect / FixResult / fix）
    detect.py        猜编码：候选、严格解码、打分、排序
    fix.py           修乱码：四步尝试 + is_improvement 判据
    cli.py           命令行：参数解析、人读/JSON 两种输出、退出码
    __main__.py      让 python -m mojibake_fixer 能用
  tests/
    conftest.py      把 src 塞进 sys.path，不安装也能跑测试
    test_detect.py   猜编码的用例
    test_fix.py      修复与「不可逆」的用例
    test_cli.py      用 subprocess 真跑命令行的用例
  samples/           4 个演示文件（见第三节）
```

## 八、测试

```bash
python -m unittest discover -s tests -v
```

也可以 `pytest`（装了的话），`tests/conftest.py` 对两边都友好。CI 在
`.github/workflows/ci.yml`，Ubuntu + Python 3.11 / 3.12 矩阵。

## 九、许可

MIT，见 [LICENSE](LICENSE)。Copyright (c) 2026 Gongxi8cai
