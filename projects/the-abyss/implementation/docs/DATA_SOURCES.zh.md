# 材料来源与复现边界

本预览不附带语料、分词器、预训练权重、数据库、token 分片或原始运行回执。T1–T10 是由代码生成数据的受控合成实验，不需要 119M 底座或下列外部材料。历史结果的说明见 [RESULTS.zh.md](../historical/RESULTS.zh.md)。

下列材料属于另一个可选的自然语言材料接入流程。来源可公开查找，不代表整条历史流程已能从公开输入复现。本次整理没有下载材料、加载权重或重新运行实验。

## 核验口径

- **本轮官方核验**：本轮项目审阅通过官方页面核对了 TinyStories 的 CDLA-Sharing-1.0、固定 Wikipedia 数据卡的 CC BY-SA 3.0/GFDL 与当前 Wikimedia 条款的 4.0/GFDL 差异、EmpatheticDialogues 的 CC BY-NC 4.0，以及 NRC EmoLex 的禁止再分发条款。
- **本地记录**：其余许可、下载字节、SHA256 和历史处理过程来自已有来源清单。没有在本轮逐项重新核验官方页面或重新下载文件。哈希用来识别当时字节，不保证当前链接仍可提供它们。
- 数据、模型权重、分词器和程序各自有来源及许可。项目代码许可证不自动覆盖这些外部材料。

## 中文与英文 Wikipedia

来源：[Wikimedia Wikipedia 数据集](https://huggingface.co/datasets/wikimedia/wikipedia)。历史选用 `20231101` 数据，而非网站当前内容。

| 语种 | 固定仓库提交 | 选择 |
|---|---|---|
| 中文 `20231101.zh` | `5428a5d9ebb8d68732fc1227ebc5e8d5cec28592` | 6 片全部获取 |
| 英文 `20231101.en` | `ad5752b5e625abfcdeefe5ae0ad2c3721c4b2619` | 41 片中的 00000、00020、00040；非随机或主题均衡抽样 |

按以下 URL 模式获取所需文件，将 `{revision}`、`{config}` 和 `{filename}` 替换为表中固定值：

```text
https://huggingface.co/datasets/wikimedia/wikipedia/resolve/{revision}/{config}/{filename}
```

下载后先核对 SHA256；不匹配时停止并记录版本差异。不要直接使用数据集最新分支替换历史版本。

| 配置与文件名 | 历史 SHA256 |
|---|---|
| zh / `train-00000-of-00006.parquet` | `853ddf4a138c792ad7386d6de831788f96326c03e1e3349f7a315498392e8b56` |
| zh / `train-00001-of-00006.parquet` | `038b08e5aae38b5a1671794cee3fa0d4952c0d00fa0890a903d2de3f3fe5f703` |
| zh / `train-00002-of-00006.parquet` | `ec8f6c0dd1418b8fcd454278fb4f2bc7cd0ce8312f29c80b672533942601338f` |
| zh / `train-00003-of-00006.parquet` | `4884e4933fa91f46dc9bf711db8be07f368da59b8cfc2e00e895a65a3284cbb1` |
| zh / `train-00004-of-00006.parquet` | `415a5cd235a359a009c6bd6d488c3d9ee81ed3220b9f33fd04214558bc5150cd` |
| zh / `train-00005-of-00006.parquet` | `803ae27118b1daf9be4403b57b679b8ce065fbffdfdea0c33c517255c17478df` |
| en / `train-00000-of-00041.parquet` | `382e7f6f09e488b24793a7f7cfc659879d5a22da2cf2efec6491665f0c019677` |
| en / `train-00020-of-00041.parquet` | `79ee06627f4ba2fec056fcd23c077a29238bbcbacc3187e8d1a0b47e663e9c7a` |
| en / `train-00040-of-00041.parquet` | `fed6addb1da9364fcf42c6953539eecc21bbc2cf3cd33743684e6872ce6c468a` |

固定数据卡说明为 CC BY-SA 3.0/GFDL，部分文本仅 CC；[当前 Wikimedia 使用条款](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use)使用 CC BY-SA 4.0/GFDL。保留这个版本区别、文章 URL、标题和署名来源，不把历史数据统一改标为当前版本，也不以清洗代码许可证替代文本许可。

历史整理按 NFC 规范化、连续空白合并及首尾去空白后的正文哈希分组，以固定盐 `empiricist-expansion-v1` 划分约 98%/1%/1% 的训练/验证/测试集，同组只保留固定文件/行序的第一篇。记录的去重后总量为 1,847,940 篇；该量不是全面质量或隐私审核结果。未做完整的近重复、语义改写、跨语言对应及既有训练集污染检查。

**尚未补齐的复现环节**：大语料 `prepare_scale.py` 依赖已经存在的 `corpus_index.sqlite`，本轮没有找到从下载 Parquet 从零重建该索引的完整程序。已有 `读取示例.py` 只是读取现成索引，不能生成它。获取原始文件和核对哈希可以独立完成；不能据此宣称 1B token 计划、历史划分或完整材料流水线已经可复现。上游文件名中的 `train` 不代表所有行都能用于本项目训练；历史本地验证/测试隔离应被重建并核对。

## 16,384 词表分词器

材料接口使用历史文件名 `tokenizer_fixed_16384.json`。原准备记录描述的是：ByteLevel BPE，词表 16,384，`min_frequency=2`，特殊 token 为 pad/eos/unk，从下列两个语料的训练部分各取 20M 字符。以下是输入身份，不是分词器文件下载地址。

| 输入 | 获取方式与固定范围 | 历史 SHA256 |
|---|---|---|
| TinyStories | [固定提交的 TinyStories-train.txt](https://huggingface.co/datasets/roneneldan/TinyStories/resolve/f54c09fd23315a6f9c86f9dc80f725de7d8f9c64/TinyStories-train.txt)，只保留字节区间 `[0,536870312]`，共 536,870,313 字节 | `ffb42c44e03703622327e89577e32ffdb4c398ca6acd5d63d55ffdc78aeb3554`；这是前缀哈希，不能拿完整文件比较 |
| Simple English Wikipedia | 历史来源记录为 [2026-10-01 dump 目录](https://dumps.wikimedia.org/simplewiki/20261001/)，文件名 `simplewiki-20261001-pages-articles.xml.bz2`，358,258,425 字节 | `2db94ff149adbbaf88efecb8f510a549eaa2a82d59df6278a4af88e13c1b99bd` |

TinyStories 数据卡列 CDLA-Sharing-1.0；见[官方数据卡](https://huggingface.co/datasets/roneneldan/TinyStories)。SimpleWiki 的历史文件是否仍可从该目录获得尚待验证，本说明没有猜造直接下载链接。Wikipedia 文本的许可、出处和署名要求仍需跟随所选 dump 核对。

目标分词器 SHA256 为 `3cc4001a8a9418e1f1a97c47b809fbd85860ccb0c44b6d6dc4a0326e791ac7fe`。原工作区的 `scripts/prepare_data.py` 与 `src/data.py` 含准备逻辑，但没有在本预览中完成隔离重建验证。字符抽样顺序、清洗/划分、特殊 token 的确切字符串及顺序、依赖版本都要与原记录对齐；上表和 BPE 参数本身不足以保证逐字节相同。未匹配目标哈希时，不应把重建产物称为原分词器。

## 可选 119M 底座

材料代码的历史说明指向另一研究分支的 `hardened_empiricist_model_119m_billion_seek_common_final.pt`，称其由 `run_streaming_billion_scale_seek_common_reserve_diff.py` 于 2026-10-21 保存。`backbone.py` 明示依据 `hardened_empiricist_kernel.py` 重写底座路径；它是有来源的重实现，不应笼统宣传为完全独立原创。

本轮没有找到该权重的公开获取 URL、公开模型卡、可发布许可证或完整公开重训流程。源内核的精确版本、许可与权重身份还需补齐。输出一致性测试在缺少原内核时会跳过；这不是已通过对照测试。即使从随机权重运行同形状网络，也不等于复现该预训练检查点。T1–T10 合成实验不依赖这一材料分支。

## 其他可选研究材料

这些是更早学习材料包中的可选内容，不是 T1–T10 的输入。可以按来源自行获取；本预览不转发原件或派生正文。

| 类别 | 来源与获取方式 | 许可记录、固定身份与限制 |
|---|---|---|
| GoEmotions | [Google Research 官方目录](https://github.com/google-research/google-research/tree/master/goemotions)；原始 CSV 由该页链接到 Google Storage，官方 train/dev/test TSV 与标签表在 `data/` | 本地记录 Apache-2.0；部分 URL 指向 `master`，未固定提交。保留官方划分；逐标注者记录不是独立评论。历史 `train.tsv` SHA256：`1c254a142be5c00e80d819b9ae1bbd36d94b2eeb8f4b1271846508d57e57d9c5`。 |
| EmpatheticDialogues | [官方仓库](https://github.com/facebookresearch/EmpatheticDialogues)与[官方 tar.gz](https://dl.fbaipublicfiles.com/parlai/empatheticdialogues/empatheticdialogues.tar.gz) | 本轮官方核验 CC BY-NC 4.0，仅非商业；压缩包 SHA256：`56f234d77b7dd1f005fd365bb17769cfe346c3c84295b69bc069c8ccb83be03d`。按上游每物理行一记录/直接逗号分列格式读取；通用带引号 CSV 解析会改变记录数。保留会话划分，不把候选回答列计为新训练样本。 |
| NRC EmoLex 中文辅助词表 | [作者页面](https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm)，由读者阅读条件后自行获取 | 本轮官方核验非商业研究/教学用途及禁止再分发；不附带 ZIP、中文词表或词表派生副本。历史 ZIP SHA256：`4edcbd00b1d38ace19ecebca17a50ce08719785b9476cd12d31532eff0fc34e6`。中文是机器翻译的词关联，不是原生句级情绪标注。 |
| 五张物体图片 | [scikit-image v0.25.2 数据目录](https://github.com/scikit-image/scikit-image/tree/v0.25.2/skimage/data)，取 coffee.png、clock_motion.png、camera.png、chelsea.png、rocket.jpg | 本地记录逐图为 CC0 或来源声明公有领域；按该固定版本 `_fetchers.py` 的逐图说明与 `_registry.py` 的哈希核验，不能仅用库代码许可证推断图片许可。 |
| IPA 图表 | [IPA 官方图表页面](https://www.internationalphoneticassociation.org/content/ipa-chart)，Kiel PDF 与 300ppi PNG | 本地记录 CC BY-SA 4.0；PDF SHA256：`c8203013c676b243959072234526d60b874851d0509a00fd7528f4e56c706787`，PNG：`c9ebf272d46f3bcfc3484c12c9a4eae0db94c277ca80884abbacb091b17a174d`。不含发音音频。 |
| 汉字字典与六字字形 | [Make Me a Hanzi](https://github.com/skishore/makemeahanzi)，`dictionary.txt` 与木/林/人/心/水/休的 SVG | 本地记录字典 LGPL-3.0-or-later、字形 Arphic Public License；原下载指向 `master`，版本未完全固定。字典 SHA256：`744bb05d5b0742e9ee35c37791f94d56a173349b3367569e7ca11e510364d203`。字形结构不等于词义或历史字源。 |
| Unicode 部首表 | [Unicode 17.0.0 CJKRadicals.txt](https://www.unicode.org/Public/17.0.0/ucd/CJKRadicals.txt) | 本地记录 Unicode License v3；SHA256：`826f83be25cd18fb8a5015a514704504e1982e840ea14d058bf583e1cc620c83`。 |
| 英文构词资料 | [A 字头希腊/拉丁词根固定版本](https://en.wikipedia.org/w/index.php?title=List_of_Greek_and_Latin_roots_in_English/A&oldid=1377897064)、[前缀固定版本](https://en.wiktionary.org/w/index.php?title=Appendix:English_prefixes&oldid=91404073)、[后缀固定版本](https://en.wiktionary.org/w/index.php?title=Appendix:English_suffixes&oldid=77921209) | 本地记录 CC BY-SA 4.0；保留页面版本与署名。A 字头子集、前缀/后缀索引不能代替完整现代构词规则。 |

GoEmotions、IPA、Make Me a Hanzi 等只列出的部分哈希不足以恢复整个旧材料包；如需精确重建每个可选文件，还需补齐完整的逐文件清单与转换脚本。没有必要为了运行合成实验去取得这些材料。

## 来源记录

本说明综合的原工作区相对记录为 `project/DESIGN_v0.2.md`、`project/empirical_core/materials/{backbone,corpus}.py`、`project/tests/test_materials.py`，以及材料集合 `empiricist_learning_materials_20261019/{README_中文.md,来源清单.md,sources.json}` 和其 `expansion_v1/` 对应文件。分词器线索另来自原 `data/processed_v1/manifest.json`。这些是来源定位说明，不代表原件全部随本仓库发布。
