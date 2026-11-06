# G1：固定任务上的粒度小试 / Fixed-task granularity pilot

本方案在查看本实验结果之前冻结。复用已审查的 T1 标准库出题器；这是新增诊断学习器，不是原 T1 神经模型、T11、v18 或完整理论的验证。

## 固定与改变

每个种子只生成一次 96 个原子、2048 个无序对象对及两个世界的题目。保留原事件、查询、原子赢家、原标签和划分。源包是生成器预设的参考家族，不是本实验学出的结构。源数值由包水平加成员偏差产生，因此结构分组含有相关性先验。

只改变原子到共享分数槽的映射：家族内嵌套的 1/2/4/8 粒度，以及同大小全局随机分组。禁止按隐藏数值或答案排序分组。两档预定训练稀疏度为 64/512 个不同对象对；每对取一个世界例，所有臂使用相同实例、顺序、初始化、步数与学习率。

学习器用两个候选的共享分数之差做二元逻辑回归，原子赢家始终不变。每臂分配相同 96 个标量槽，但聚合改变参数共享及有效自由度；不能声称等有效容量或等 FLOP。CPU 侧沿用 resolve 找到 A/B；世界的正负号由既有规则提供，不检验事件注意力、世界规则发现或世界迁移。两个世界是同一无序对的重复测量。

## 预先声明的观察方向，不是结果

- 稀疏监督时，带有生成器先验的共享可能帮助跨参考包比较；随机共享未必有同样收益。
- 共享槽会失去某些原子区别；同槽候选必须保留，平局按各半计分。这是结构检查，不包装成新发现。
- 较多监督时原子级分数可能更有利；若没有出现该模式，原样报告，不重新选种子、调学习率或噪声。

主要比较每个种子中各臂相对 atomic 的配对差值，并比较同粒度 family 与 random。报告全部 7 臂、2 档、10 种子；不根据结果挑选最优粒度。种子而非题目作为汇总重复单位；10 个合成世界仍不足以建立广泛结论。

## 指标与混杂记录

原子期望准确率对最高分平局均分；另记录使用固定种子、固定题序的独立伪随机破平局的实际准确率。错误按不变的源包归为包内或跨包，保留分母；另记录当前分组导致的候选同槽比例、碰撞/无碰撞准确率。知道正确组后随机破同槽平局的分数仅作本表示/评分规则的参照，不称任意模型的信息论上界。

同时记录训练原子覆盖、固定原子比较图的连通分量，以及测试两端是否同分量。共享先验可以桥接未见原子或断开的比较图；这不等于学会发现知识结构。原子标签、候选、训练顺序及划分使用哈希冻结，隐藏数值仅供数据审计，不交给学习器。

跨槽也可能丢失信息：按规范化无序组对统计要求相反赢家的冲突及覆盖题数。另计算每个组对各自选择多数赢家、同槽计0.5的事后查表参照；它使用测试标签，仅供诊断，绝不训练或选择实验臂，也比共享标量排序更宽松。训练覆盖只统计 A/B 端点，不统计历史干扰对象。64对是512对的前缀。超时后仅汇总完整平衡的种子，明确 INCOMPLETE。

仅评原生成器的 test 划分；dev 保留但本次完全不使用。训练图按4096次抽样实际呈现的不同对象对构造，同时记录选入对数和实际呈现对数，避免把未呈现样本记成见过。

## 执行边界

仅在独立目录执行；原工作树和实验只读。无 GPU、无 torch、无外部语料、无网络。只调整新进程自己的优先级和亲和性。限制为一颗 CPU 的约 10% 时间、每次进程最多 30 CPU 秒及 240 秒墙钟；负载或内存门禁不满足时停止并保留部分状态，不自动降格后补跑。

## English scope

This preregistered pilot reuses the reviewed standard-library T1 generator. Atomic identities, labels, tasks, candidates, splits, update order, learner, and budget remain fixed within each seed and evidence regime. Only the mapping to shared score slots changes. Reference families are supplied by the synthetic generator. Allocation is fixed but effective degrees of freedom change with sharing. World inversion and A/B resolution are supplied rules, not learned achievements.

All arms and seeds, ties, representational collisions, errors within/across fixed reference families, unseen atoms, and disconnected comparison graphs are reported. Results can support only a local statement about this scorer and task. They cannot establish optimal granularity for natural-language knowledge, a better attention architecture, autonomous formation, or full-system learning.
