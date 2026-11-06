# 深渊与红尘仙 / The Abyss and Hongchenxian

[English](README.en.md) · 简体中文

**完整名词解释：** [中英文术语与事件链边界](docs/GLOSSARY.md)，收录最新三轮修正、实现对应和未定问题。

**新证据：** [2026-11-07 研究记录更新](projects/the-abyss/evidence/2026-11-07/README.md)整理 v18.1、T11、后续阶段状态与 G1 粒度小试。G1 仅完成 2/10 个种子后因资源门禁停止；此前深渊实现副本的静态验证范围保持不变。

同一个仓库，两个分开的研究项目。这是一套面向**记忆、学习与智能体协作的半成品人工智能方案**：补充基础 LLM 本身不提供的持久记录、知识组织和工作接续机制，并研究局部学习。**当前是双语研究预览，整体方案没有完整实现或验证。项目许可证尚未选定；公开可读不等于已按开源许可证授权使用。**

## 两个入口

### [深渊 / The Abyss](projects/the-abyss/README.md)

1. **逻辑是知识的可达路径。**
   Logic is the path that makes knowledge reachable.

这是本项目的理论主张，不是已由实验证明的结论。该项目讨论经验如何形成可复用知识、知识如何组合和展开、以及如何依据新经验修订。入口提供中英文设计、来源和证据说明。

本次整合保留已有理论文档，并在 [implementation](projects/the-abyss/implementation/README.md) 纳入选取的原研究代码及发布适配：65 个核心 Python 文件、25 个 `test_*.py` 文件、31 个实验 Python 文件（含共用辅助文件）和 11 份计划。它们包括记忆与来源记录、知识包、事件链 AST 和 T1–T10 受控合成实验；不是完整本地工作区的发行。

代码存在、历史运行完成和当前副本验证是不同状态。本轮深渊接入只做静态检查，未安装依赖、导入项目、执行 pytest、训练或独立复现历史成绩。T10 历史回执为 50/50，**S2 未达预期，新包泛化仍未解决**；回执齐全不能写成“50/50 实验成功”。详见[证据边界](projects/the-abyss/EVIDENCE.md)和[历史摘要](projects/the-abyss/implementation/historical/RESULTS.zh.md)。

### [红尘仙 / Hongchenxian](projects/hongchenxian/README.md)

黑盒 Agent 的工作协作研究：持续身份、段落索引记忆、固定共享快照、逐步调用账本、生命周期决定及来源核验恢复。已有离线 synthetic 工程链使用 Node 内置依赖，本次保留其源码与成果。

红尘仙的工作事件链承接工作记录、调用、依赖、挂起和接续。深渊的经验主义事件链用于对象、关系、条件和流转的学习表示。二者不等同。深渊 T4 的人工 FSM 只借用了存活与恢复思路，不能把它或协作账本当作完整知识学习、九算子或自主编程系统已经实现。

## 运行与证据

以下命令仅运行红尘仙离线测试，不训练深渊模型：

```sh
node --version  # 此前验证环境：Node.js 24.22.1
npm test
```

这组 Node 测试无需 npm install、Python、官方模型 SDK 或 API key。测试在临时目录创建合成数据，默认防误调用保护拒绝常见 Node 网络入口；它不是恶意代码沙箱。不要传入真实数据路径或凭据。

深渊使用单独的 Python 安装与实验入口，见[复现说明](projects/the-abyss/implementation/docs/REPRODUCIBILITY.zh.md)。其中逐名列出 12 个基础契约文件和可选 `test_t1.py`；本次没有运行。其他测试可能真正训练模型，T4 还会启动自身子进程并注入硬退出。新运行入口的静态适配不保证既有运行目录或权重可以直接迁移。

| 记录 | 对应范围 |
|---|---|
| [此前 VALIDATION](evidence/VALIDATION.json) | 此前检查点的红尘仙离线测试 72/72；不是深渊测试通过数。文件中的“深渊尚未并入”描述保留为历史状态 |
| [此次整合记录](evidence/ABYSS_INTEGRATION.json) | 深渊源码接入与本轮检查范围；与此前记录分开 |
| [深渊静态报告](projects/the-abyss/implementation/STATIC_CHECKS.json) | 解析、结构、链接与哈希等静态检查；不证明运行或学习结果 |
| [来源快照](projects/the-abyss/implementation/historical/SOURCE_SNAPSHOT.json) | 选入来源文件的相对路径与哈希；发布适配后的字节可能不同 |

此前的 `SCAN_REPORT.json`、`SOURCE_MANIFEST.json` 也保留其原检查点范围，不能直接解释为新增深渊文件已经通过同一轮检查。全仓完整性以当前 `SHA256SUMS` 及此次整合记录为准。

## 仓库分区

- `projects/the-abyss/`：中英理论、来源、证据边界，以及 `implementation/` 中的选取研究源码、计划和历史摘要。
- `projects/hongchenxian/`：红尘仙源码、synthetic tests 与中英双语说明。
- `scripts/`：离线防误调用、候选扫描、完整性验证。
- `evidence/`：按检查阶段分开的来源与验证记录。
- `docs/`：两项目共享的排除范围与发布清单。
- `third_party/`：独立的上游许可文本；不替本项目选择许可证。

理论、源码、历史摘要和本次静态检查分开记载。没有完成真实十成员恢复、72小时连续运行、一般学习能力、复杂度突破或意识的声明。

## 发布前

查看 [排除范围](docs/EXCLUSIONS.md)、[发布清单](docs/RELEASE_CHECKLIST.md) 与 [第三方说明](THIRD_PARTY_NOTICES.md)。不得整包上传原始工作目录。真实会话、私人聊天、账号、凭据、原始训练数据和未经审查的运维记录不进入本候选。

[材料来源说明](projects/the-abyss/implementation/docs/DATA_SOURCES.zh.md)仍记录可选 119M 底座来源与许可未齐、`corpus_index.sqlite` 从零生成流程缺失等问题；这些不能写成完整材料流水线已可复现。语料、分词器和预训练权重未打包，T1–T10 合成实验不依赖该材料分支。
