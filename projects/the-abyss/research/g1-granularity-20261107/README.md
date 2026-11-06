# G1：固定任务粒度小试

这是独立的本地实验目录。方案和边界见 [PREREG.md](PREREG.md)，配置见 [PLAN.json](PLAN.json)。复用的 `vendor/t1_task.py` 来自此前整理的深渊研究源码；不修改原项目，不为其选择许可证。

本实验使用 Python 标准库，以及仅用于自身资源约束的 psutil。准备环境为 Windows、Python 3.13.9、psutil 5.9.0；没有安装新依赖。代码不导入 torch、不使用 GPU、不联网。

在独立新目录中保留本目录的源文件（不要复制已有 data/、receipts/、FROZEN.json 或结果文件），从该目录执行：

```powershell
python -B pilot.py prepare
python -B pilot.py run
python -B report.py
```

`prepare` 冻结数据、分组、训练顺序和源码；`run` 才训练新增的小型比较器。已有证据会触发拒绝覆盖；程序不会自动恢复、追加或重跑。资源门禁不满足时保留 INCOMPLETE 状态，报告仅汇总完整平衡种子。

默认 CPU 22 必须在当前允许集合内；它只是本机避开已知其他实验亲和范围的选择，不是通用建议。换机器时应在首次冻结前调整配置，并把该运行作为独立复现。10% duty 是软节流，不是操作系统硬上限。

结果文件包括 REPORT.md、SUMMARY.json、VERIFICATION.json、FROZEN.json、DATA_AUDIT.json、逐臂 receipts/ 和冻结 data/。报告中的 SD 是种子间标准差，不是置信区间。两世界复用同一无序对象对，不构成独立重复。

## English

An isolated local pilot using the reviewed T1 generator and a new shared-score logistic learner. Prepare once, run once, then summarize. Existing evidence is not overwritten. Resource controls affect only the newly launched process. No original experiment, GPU, corpus, model checkpoint or network is used. See the preregistration for supplied structural priors, capacity changes, repeated measurements and the limits of conclusions.
