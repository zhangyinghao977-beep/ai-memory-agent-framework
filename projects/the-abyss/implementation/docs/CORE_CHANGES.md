# Core release-copy changes / 核心发布副本变更

This note covers `project/` only. Changes were made in the isolated release candidate; the original research workspace was not modified or executed.

本文仅记录 `project/` 的整理。修改仅发生在独立发布副本，未修改或执行原研究工作区。

## Changes / 变更

- Replaced private conversation quotations and personal nicknames in comments and docstrings with technical descriptions. Retained design versions, experiment limitations, and historical source identifiers, including the reproduced v19 partition function. Synthetic dialogue used as test data remains synthetic test data.
- 将注释与文档字符串中的私人对话引用、昵称改成技术说明；保留设计版本、实验限制及历史来源标识，包括复刻的 v19 划分函数。测试中的合成对话样本仍保留。
- Updated the package description and the default-world display description. No learning algorithm, task distribution, model structure, or research hyperparameter was changed.
- 更新包说明及默认世界的显示描述；未修改学习算法、题目分布、模型结构或研究超参数。
- Marked the T4 crash-recovery subprocess test as `process_integration`. It resolves `experiments/t4_survival_20261103/live_t4.py` relative to the release root and explicitly skips only this integration test if the runner is absent. The marker is registered in `project/conftest.py`.
- 将 T4 子进程恢复测试标为 `process_integration`，按发布根目录相对定位运行器；缺少运行器时只明确跳过这项集成测试，其他基础测试不因此跳过。
- T4 test subprocesses use one thread and at most one CPU from the current process's allowed affinity set. Unsupported affinity returns an empty request. They run in their own temporary output directory and clear inherited crash-injection variables before applying a requested test fault. The runner CLI is unchanged.
- T4 测试子进程默认一个线程，并最多选择当前允许集合中的一个 CPU；不支持亲和设置时发送空请求。子进程使用自己的临时输出目录，并清理继承的故障注入变量。运行器 CLI 不变。线程与亲和设置不等于严格的 CPU 利用率上限。

## Static validation / 静态验证

- Parsed all 92 included Python files with the standard-library AST parser: 65 core files, 25 test files, `tests/_helpers.py`, and `conftest.py`.
- 已用标准库 AST 解析全部 92 个 Python 文件：65 个核心文件、25 个测试文件及两个测试辅助文件。
- Compared executable ASTs with the source snapshot after excluding docstrings. Differences are limited to T4 test portability, marker registration, and the human-readable SQL world description. Other edits are comments/docstrings. The final project scan found no original-workspace absolute paths or removed personal-attribution markers.
- 排除文档字符串后对照可执行 AST，差异仅为 T4 测试可移植性、标记登记和 SQL 中的世界显示描述；其余修改均为注释或文档字符串。最终扫描未发现原工作区绝对路径或待移除的私人归属标记。

## Not verified / 尚未验证

No project module or PyTorch was imported. No pytest collection, test execution, training, checkpoint loading, subprocess launch, process termination, or network operation was performed for this check. Static parsing does not establish runtime compatibility or test success.

本轮没有导入项目模块或 PyTorch，没有收集或执行 pytest、训练、加载权重、启动子进程、终止进程或联网。静态解析不能证明运行兼容性或测试通过。

The process-integration marker does not classify every training or resource-intensive test: several other tests perform short neural training or create temporary databases and checkpoints. The T4 runner's platform handling is maintained separately in `experiments/`. Run and verify the assembled release copy before claiming reproducibility. Modified release bytes do not match historical frozen-source hashes.

进程集成标记并未涵盖所有训练或较重计算测试；其他测试仍可能进行短训练、创建临时数据库和权重。T4 运行器的平台适配由 `experiments/` 单独维护。完整副本经过实际验证前，不应宣称已可复现；发布副本修改后的字节也不再等于历史冻结源码哈希。
