# 复现说明

[返回深渊](../README.md) · [English](REPRODUCIBILITY.en.md)

本说明描述候选副本的检查与复现边界，**不记录一次已经完成的新复现**。发布准备只做文件整理和静态检查，没有执行 pytest、导入项目、启动训练或加载历史权重。历史结果与新运行应各自保留独立身份。

本说明中的“根目录”均指本实现子目录 `projects/the-abyss/implementation`，不是整个 GitHub 仓库的根目录。若从整个仓库开始，先执行以下命令，再执行本文其余命令：

```sh
cd projects/the-abyss/implementation
```

## 环境与依赖

基础存储与契约代码使用 Python 标准库，包括 sqlite3、json、hashlib 等；测试运行器是第三方包 pytest。神经实验需要第三方包 torch，T4 的资源与子进程路径还需要 psutil。`subprocess`、`pathlib`、`dataclasses`、`pickle` 等是标准库，不是需要单独安装的依赖。

使用 Python 3.11 或以上版本和独立虚拟环境。在本实现根目录安装基础测试依赖：

```sh
python -m pip install -e '.[test]'
```

需要神经实验与完整测试依赖时：

```sh
python -m pip install -e '.[experiments,test]'
```

第二组包括 torch、numpy、psutil 和 pytest，安装版本由 `pyproject.toml` 的依赖组指定。根目录的 `requirements-observed.txt` 仅以注释记录观察到的环境信息，**不是可执行的依赖锁文件，也不是历史实验环境记录**。CPU 与 GPU、线程数、软件版本及随机种子都应写入新运行记录；历史运行使用过某个环境，不等于任意环境都能逐位复现。上述安装命令是供复现者选择执行的步骤，本次发布准备未安装依赖。

不执行项目代码的检查入口是：

```sh
python -B tools/check_static.py --report STATIC_CHECKS.json
```

它只做 AST、JSON、TOML、哈希和路径扫描，并写自己的报告；不能代替导入检查、pytest 或实验运行。报告结果以实际生成的文件为准。

此副本不包含旧 `materials` 与 `toy` 模块或对应测试，不依赖外部语料、分词器和 119M 检查点。原工作区的材料测试曾有“文件缺失就跳过”的行为；本预览不把那些跳过算成接口验证。

## 先选择测试范围

以下 **12 个基础契约文件**是第一批轻量候选，另可加入 `test_t1.py` 检查合成出题与规则基线。它们不读取外部数据，不执行神经训练，但多数通过 `project/conftest.py` 在 pytest 临时目录创建 SQLite 数据库；评测与完整性测试还会写临时计划和备份。**本次没有运行这个候选集合，不能把它写成已经通过。**

| 文件，均在 project/tests 下 | 主要检查 |
|---|---|
| test_calls.py | 调用输入、候选、反馈与修正记录 |
| test_decisive_gate.py | 决定因素重合与简单捷径门禁 |
| test_evaluation.py | 计划冻结、数据重合、基线和报告结论 |
| test_event_ast.py | AST、对象绑定、条件证据与流转 |
| test_experience.py | 来源、核实、发生记录与只读访问 |
| test_formation.py | 成包、局部推广与概念关系 |
| test_learning_integrity.py | 学习收据、逻辑遗忘、备份与引用完整性 |
| test_memory.py | 形成、想象、修订与回忆 |
| test_registry.py | 知识包、版本及局部修正契约 |
| test_relation_eval.py | 尺子、方向、未知值与评价转换 |
| test_v017.py | 记忆范围、稳定引用和调用时可见性 |
| test_valve.py | 世界边界、前提范围和撤销 |
| test_t1.py（可选） | 合成任务、数据划分与规则基线 |

从本实现根目录逐名选择这 13 个文件的命令如下。它是供选择执行的候选检查，**本次没有执行**：

```sh
python -B -m pytest -q -p no:cacheprovider project/tests/test_calls.py project/tests/test_decisive_gate.py project/tests/test_evaluation.py project/tests/test_event_ast.py project/tests/test_experience.py project/tests/test_formation.py project/tests/test_learning_integrity.py project/tests/test_memory.py project/tests/test_registry.py project/tests/test_relation_eval.py project/tests/test_v017.py project/tests/test_valve.py project/tests/test_t1.py
```

保留 `project/conftest.py`、`project/tests/_helpers.py` 和 `project/empirical_core` 的目录关系。测试中的 `_helpers` 是本仓库的辅助模块，不是 PyPI 依赖。直接改变布局或导入模式后，需要重新检查模块是否可导入。

## 其他测试会做什么

| 测试组 | 实际行为 |
|---|---|
| test_t1_models.py、test_t1_scale.py | 前向、梯度连通和规模检查；包含约千万参数模型和较大合成任务，不能当作零资源检查 |
| test_t1_train.py、test_t2.py、test_t3.py | 有短训练、局部修复和临时权重版本读写；测试名称含“只读”也不保证整个测试不训练 |
| test_t4.py | 写临时日志、SQLite 和权重；部分测试实际学习；故障恢复测试启动自身子进程并让其硬退出，然后重新启动验证恢复 |
| test_t5.py–test_t10.py | 合成数据上的训练和一致性检查；T5 的一个检查运行 400 个优化步骤，其余也有真实参数更新 |

T4 的硬退出针对测试自己创建的子进程，不是终止已有实验。它还依赖 `experiments/t4_survival_20261103/live_t4.py`，因此不能只拿走 `project/` 就期待完整测试能运行。发布副本为该测试增加了 `process_integration` 标记；运行器缺失时只跳过这项集成检查。其子进程默认一个线程，并最多选择当前允许集合中的一个 CPU，而非使用固定的本机 CPU 编号。线程数与亲和设置不是严格的 CPU 利用率上限；这些静态适配尚未经过实际运行验证。具体改动见 [核心副本变更](CORE_CHANGES.md)。

部分测试在收集阶段就生成数据并设置 torch 线程数，因此 `--collect-only` 也不是纯文件清单。旧套件没有统一的 slow/integration 分类；不要用不加选择的整套 pytest 命令替代轻量检查。

## 新运行与历史摘要分开

新运行使用全新的输出目录，保留计划、源码版本或哈希、环境、种子、资源预算、数据划分、门禁、运行回执和失败记录。遇到失败应保留失败记录；事后修改计划、指标或分析时，应另记变更和新身份，不能覆盖为“原计划通过”。

`historical/` 中的证据描述原来的运行。历史回执、摘要或源码哈希不证明本副本已复现。修改可移植入口后的代码也不再与原始冻结文件逐字节相同，需用新的源码身份记录。

`historical/SOURCE_SNAPSHOT.json` 记录复制来源文件的相对路径和只读 SHA-256。它用于溯源，不是测试通过凭证，也不代表适配后的代码与历史运行源码相同。

T10 的历史状态是 50/50 个任务完成；S2 未通过，新包泛化仍有问题。任务数、工程契约通过数、预测是否成立和模型成绩是四种不同信息，不相加，也不相互替代。T8/T9/T10 所用的规则生成公式、比较器和窗口仍有人工结构；这些受控结果不证明完整的自主知识形成或通用持续学习。

经验主义事件链用于表达对象、关系、条件和流转；红尘仙工作事件链用于工作执行与回执。T4 的人工 FSM 仅借用后者的存活和恢复思路，不能把它的运行称为红尘仙系统已经实现。

## 实验入口与前序运行

以下是适配后的接口说明，**所有运行命令均未在本次整理中执行**。从本实现根目录运行，路径以本实现根目录为基准。每个实验目录有自己的 `PLAN.json`；默认的新输出目录名是 `run_reproduction`，不能把历史输出冒充新运行。

| 阶段 | experiments 下的目录 | 入口 | PLAN 中声明的前序运行 |
|---|---|---|---|
| T1 | t1_run_20261101 | run_t1.py | 无 |
| T1 扩展 | t1_run2_20261102 | run_t1.py | 无 |
| T2 | t2_repair_20261102 | run_t2.py | 无 |
| T3 | t3_mutual_stability_20261103 | run_t3.py | 无 |
| T4 | t4_survival_20261103 | run_t4.py | T3 |
| T5 | t5_content_choice_20261105 | run_t5.py | 无 |
| T6 | t6_lattice_parts_20261105 | run_t6.py | T5 |
| T7 | t7_noisy_lattice_20261106 | run_t7.py | T6 |
| T8 | t8_grown_lattice_20261106 | run_t8.py | T6，供事后比较 |
| T9 | t9_grown_rule_20261106 | run_t9.py | T8 |
| T10 | t10_relation_size_20261106 | run_t10.py | T8、T9 |

前序路径由计划中的 `dependency_runs` 指定，默认指向对应实验的 `run_reproduction`。`dependency_run` 会检查本副本的新运行标记、相对计划路径与阶段、冻结计划 SHA256，以及早期阶段的完成状态，或后期阶段的门禁与完整数量的 JSON 回执。目录存在本身不够，不能用空目录替代前序实验。这些检查支持产物身份和完成记录的一致性，不证明回执内容正确、权重完整或科学上的可比性；所需权重和结果仍须由相应读取入口核验。

可移植性改动面向本副本的新运行入口。已经生成的运行目录或检查点迁移到另一位置后能否直接续跑，尚未验证；不得将入口路径相对化等同于旧产物可任意搬迁。

T1、T1 扩展、T2、T3、T4 使用两个位置参数：计划路径、输出路径。一次调用会启动计划中的真实运行，包括训练；T4 还包含故障注入子进程。以 T1 为例：

```sh
python -B experiments/t1_run_20261101/run_t1.py experiments/t1_run_20261101/PLAN.json experiments/t1_run_20261101/run_reproduction
```

其他阶段按表替换目录及脚本。T4 的起点依赖 T3 运行，不能省略前序回执与单元版本。T1–T4 的报告脚本接收一个输出目录参数，例如：

```sh
python -B experiments/t1_run_20261101/report_t1.py experiments/t1_run_20261101/run_reproduction
```

T3 的 `analyze_t3.py` 必须接收且仅接收一个运行目录参数。T4 的 `live_t4.py` 保留“配置文件、输出目录”两个参数供集成测试调用，不替代主运行器的计划与前序检查。更多适配细节见 [T1–T4 入口变更](EXPERIMENT_CHANGES_T1_T4.md)。

T5–T10 分为 `gate` 与 `worker`。以下示例只选一个 worker，索引为 0、总数为 1；worker 会进行训练并写回执和模型文件：

```sh
python -B experiments/t5_content_choice_20261105/run_t5.py experiments/t5_content_choice_20261105/run_reproduction gate
python -B experiments/t5_content_choice_20261105/run_t5.py experiments/t5_content_choice_20261105/run_reproduction worker 0 1
python -B experiments/t5_content_choice_20261105/report_t5.py experiments/t5_content_choice_20261105/run_reproduction
```

T6–T9 使用同样的参数形式并替换目录和编号。T5–T9 的 gate 不训练也不加载旧权重，但会生成题目、计算基线；T8/T9 还构造经验向量或规则表，包含 SVD 等计算，因此也不是轻量静态检查。

**T10 的 gate 本身会训练。** 它对 2 种题型 × 2 种模型分别运行 3000 步，并与 T9 已有曲线点比较；必须显式传入 `--allow-training`，不是总共只运行 3000 步：

```sh
python -B experiments/t10_relation_size_20261106/run_t10.py experiments/t10_relation_size_20261106/run_reproduction gate --allow-training
python -B experiments/t10_relation_size_20261106/run_t10.py experiments/t10_relation_size_20261106/run_reproduction worker 0 1
python -B experiments/t10_relation_size_20261106/report_t10.py experiments/t10_relation_size_20261106/run_reproduction
```

T5–T10 的报告使用该运行冻结的计划身份，拒绝把已改动的当前 PLAN 或历史绝对路径冻结文件混入新运行。报告需要对应回执；缺回执不能靠报告脚本补成已完成。

事后分析另记输出目录。T5、T6、T9、T10 的 `posthoc_tN.py` 接收两个位置参数：运行目录、事后输出目录；T7、T8 的第二参数可省略，默认位于运行目录的父目录下 `posthoc_reproduction`。例如：

```sh
python -B experiments/t9_grown_rule_20261106/posthoc_t9.py experiments/t9_grown_rule_20261106/run_reproduction experiments/t9_grown_rule_20261106/posthoc_reproduction
```

事后分析可能加载该新运行的模型并进行计算，不属于静态检查；分析结论应标明是事后提出的。

适配入口默认 `ABYSS_THREADS=1`。需要指定 CPU 亲和时，可通过 `ABYSS_CPU_AFFINITY` 传入逗号分隔的 CPU 编号，但必须属于当前进程允许的集合。入口限制研究输出及依赖路径在候选根内；T4 单元测试自己的临时目录另行使用。线程和亲和设置不保证严格利用率上限；设备、训练预算及其他资源参数仍需按计划和实际环境检查。
