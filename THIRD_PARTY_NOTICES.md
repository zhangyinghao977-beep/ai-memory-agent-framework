# 第三方来源与许可范围

[English](THIRD_PARTY_NOTICES.en.md)

## DeepSeek Harness

- 项目：https://github.com/deepseek-ai/deepseek-harness
- 已核许可证：https://github.com/deepseek-ai/deepseek-harness/blob/master/LICENSE
- 已核第三方说明：https://github.com/deepseek-ai/deepseek-harness/blob/master/THIRD_PARTY_NOTICES.md
- 核查日期：2026-11-06。公开 master 根许可为 MIT，版权行为 `Copyright (c) 2026 DeepSeek`。
- 页面未给出此次可核对的固定 commit。此处只证明当前公开页面显示的条款，不证明早期版本、所有子依赖或安装 rc.5 与 master 相同。

本项目的一些边界检查与 doubles 根据其公开接口/数据格式编写，特别是 `catalog-policy.mjs`、`protected-wire.mjs`、`provider-double.mjs` 和 `sdk-runtime-double.mjs`。本预览不包含上游源码摘录、官方 SDK 包、上游 vendor 或其第三方依赖。为保留来源与任何适用的上游声明，`third_party/DeepSeek-Harness-MIT.txt` 单独记录已核对的 MIT 文本；这不是红尘仙项目的许可证选择。

上游的第三方说明还列有各自独立条款的依赖，不能因为根仓库 MIT 就假设全部依赖同许可。未来若捆绑上游运行包，必须按确切包版本重新检查完整依赖与 notices。

## 本项目内的 vendor

`projects/hongchenxian/research/central-step/vendor/` 是红尘仙先前模块的源码快照，不是 npm 安装目录。当前字节及其封存包来源由 `evidence/SOURCE_MANIFEST.json` 记录。能够追溯文件来源不等于已经确定所有作者权利；本项目许可证与贡献归属仍待所有者确认。

## Node.js / SQLite

本预览使用用户单独安装的 Node.js 内置 API，包括 SQLite 绑定，不重新分发 Node 或 SQLite 二进制/源码。SQLite WAL 格式检查模块实现项目需要的有限格式验证；没有纳入 SQLite 源码。Node/SQLite 本身的许可由其原分发提供，不能当作本项目许可。

## 深渊技术参考

深渊文档保留 Transformer 论文及候选分词工具的公开参考链接。理论摘编没有复制论文正文、第三方代码、词典、模型或权重。候选依赖不等于已经采用或完成许可核验；后续本地源码接入须另行审查。
