# 红尘仙 / Hongchenxian

[English](README.en.md) · [仓库入口](../../README.md)

**设计原则更新：** [原文记忆、Agent 切片与局部注意力](../../docs/MEMORY_LOGIC_FSM_PRINCIPLES.md)。底层窗口与索引能力已经存在；目标原文与相关上下索引简介的完整组合策略仍需接通并验证。

**名词解释：** [完整中英文词典](../../docs/GLOSSARY.md)分别说明 Agent 工作事件链、经验主义 AST 与发生记录。

本目录研究黑盒 Agent 的工作协作，包含一条可离线复现的工程链：原生记忆工具调用、最终生命周期决定、逐步用量账本、来源核验与中断后的保守恢复。它不实现深渊的完整经验主义学习架构。

当前是研究候选，不是可部署产品。不包含真实成员数据、模型凭据或服务器入口。

## 快速开始

在仓库根目录运行：

```sh
node --version
npm test
```

已验证环境为 Linux、Node.js **24.22.1**。只使用 Node 内置模块，包括 `node:sqlite`，不需要安装 npm 依赖、Python、官方 SDK 或 API key。其他版本和操作系统未验证。

默认测试先加载网络防误调用保护，再使用本地 synthetic fixtures。临时目录中会创建合成 SQLite 数据和会话文件。该保护不是恶意代码沙箱，不要把真实数据路径或凭据交给这些模块。

## 实现范围

- Body、成员私有记忆与索引、预览、选取原文。
- 固定轮次共享快照、受保护记录职责及简短意见接收。
- 多步工具调用后的一次最终生命周期决定，以及逐步请求/结算账本。
- 同一票据的来源核验恢复；未知或冲突结果保持挂起，不盲目重发。
- SDK/provider doubles，normal、reopen、中断与故障注入用例。

session persistence double 使用内存结构模拟 flush/reopen。SQLite 数据库是真实本地数据库，但这些测试不证明断电耐久性、生产权限隔离或密码学身份认证。十个合成身份不证明十成员并行，一条意见也不证明完整大会。

## 版本与证据

代码来自封存 central-step v04 的32个模块。30个文件原样保留，2处预览修改移除了官方 SDK 加载路径，并用禁止加载 SDK 的测试替换一个部署静态检查。源码在 v02 仅迁入本项目分区；来源与字节变化见仓库根目录 `evidence/SOURCE_MANIFEST.json`。

[证据说明](docs/EVIDENCE.md) 区分本地 double、官方 synthetic 和真实实验。完整原身份恢复与至少72小时连续实验尚未证明。不要用理论相近、日志完整或模型自述代替验收。

## 阅读

- [架构与边界](docs/ARCHITECTURE.md)
- [依赖和复现环境](docs/DEPENDENCIES.md)
- [实验和未执行范围](docs/EVIDENCE.md)
- [深渊理论入口](../the-abyss/README.md)

项目许可证与贡献归属待所有者决定。仓库根目录的上游 MIT 文本只保留第三方声明，不为本项目选择 MIT。
