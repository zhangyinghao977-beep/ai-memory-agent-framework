# 第三方来源与许可范围

[English](THIRD_PARTY_NOTICES.en.md)

## DeepSeek Harness

- 项目：https://github.com/deepseek-ai/deepseek-harness
- 已核许可证：https://github.com/deepseek-ai/deepseek-harness/blob/master/LICENSE
- 已核第三方说明：https://github.com/deepseek-ai/deepseek-harness/blob/master/THIRD_PARTY_NOTICES.md
- 核查日期：2026-11-06。公开 master 根许可为 MIT，版权行为 `Copyright (c) 2026 DeepSeek`。
- 页面未给出此次可核对的固定 commit。此处只证明当前公开页面显示的条款，不证明早期版本、所有子依赖或安装 rc.5 与 master 相同。

本项目的一些边界检查与 doubles 根据其公开接口/数据格式编写，特别是 `catalog-policy.mjs`、`protected-wire.mjs`、`provider-double.mjs` 和 `sdk-runtime-double.mjs`。本预览不包含上游源码摘录、官方 SDK 包、上游 vendor 或其第三方依赖。为保留来源与任何适用的上游声明，[DeepSeek-Harness-MIT.txt](third_party/DeepSeek-Harness-MIT.txt) 单独记录已核对的 MIT 文本；这不是深渊或红尘仙项目的许可证选择。

上游的第三方说明还列有各自独立条款的依赖，不能因为根仓库 MIT 就假设全部依赖同许可。未来若捆绑上游运行包，必须按确切包版本重新检查完整依赖与 notices。

## 本项目内的 vendor

`projects/hongchenxian/research/central-step/vendor/` 是红尘仙先前模块的源码快照，不是 npm 安装目录。当前字节及其封存包来源由 `evidence/SOURCE_MANIFEST.json` 记录。能够追溯文件来源不等于已经确定所有作者权利；本项目许可证与贡献归属仍待所有者确认。

## Node.js / SQLite

本预览使用用户单独安装的 Node.js 内置 API，包括 SQLite 绑定，不重新分发 Node 或 SQLite 二进制/源码。SQLite WAL 格式检查模块实现项目需要的有限格式验证；没有纳入 SQLite 源码。Node/SQLite 本身的许可由其原分发提供，不能当作本项目许可。

## 深渊研究源码与技术参考

深渊已在 [implementation](projects/the-abyss/implementation/) 中选入本地研究工作树的部分源码：65 个核心 `.py`、25 个 `test_*.py`、31 个实验 `.py`（含辅助脚本），另有 11 份新运行计划配置。范围包括基础记忆层、评测工具及 T1–T10 受控合成实验；不再只是理论摘编。来源相对路径和读取时哈希由 [SOURCE_SNAPSHOT.json](projects/the-abyss/implementation/historical/SOURCE_SNAPSHOT.json) 记录。该清单不证明作者身份、权利归属或历史实验执行版本，候选修改和证据边界见 [NOTICES.md](projects/the-abyss/implementation/NOTICES.md)。

项目代码的公开许可证尚未确定，选入源码不等于授予开源许可或完成全部来源审查，见 [LICENSE-STATUS.md](projects/the-abyss/implementation/LICENSE-STATUS.md)。运行依赖由读者另行安装；本预览没有打包其实现或沿用其许可证作为项目许可证。

理论文档继续保留 Transformer 论文及候选分词工具的公开参考链接，没有复制论文正文、第三方代码、词典、模型或权重。外部材料适配模块和已停用的 toy 实验未选入；T1–T10 通过代码生成合成数据，不依赖可选的 119M 底座或历史语料包。

可选 119M 材料分支的历史代码说明曾依据另一研究分支的内核重实现底座路径。其源内核精确版本、许可、权重公开获取地址与完整公开重训流程仍未补齐；不能将该来源描述为已经核验的完全独立原创。历史大语料处理还依赖现成 `corpus_index.sqlite`，本轮未找到从下载 Parquet 从零重建它的完整程序。这些限制没有因本次选入合成实验源码而解决。

第三方语料、词表、分词器文件、权重、数据库及原始运行回执均未打包。可选资料的来源、获取方式、分别适用的许可记录与尚未核实的环节见[数据来源](projects/the-abyss/implementation/docs/DATA_SOURCES.zh.md)，其中 NRC EmoLex 禁止再分发的原件和派生词表也不包含在本预览中。材料来源可公开查找不代表完整历史流程已可复现；本次深渊源码整理没有安装依赖、运行测试或训练。
