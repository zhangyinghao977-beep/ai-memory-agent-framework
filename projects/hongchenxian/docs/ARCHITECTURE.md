# 本副本的架构范围

[English](ARCHITECTURE.en.md)

**2026-11-07 补充：** [逻辑、记忆与 FSM 原则](../../../docs/MEMORY_LOGIC_FSM_PRINCIPLES.md)说明原文与关系、索引及简介的区别。现有底层 `summary-preferred` 窗口能力与原生 `readOriginal` 固定读取原文的链路应分开说明；二者不能合写为完整局部注意力策略已经实现。

## 数据与执行链

合成 claim 绑定成员、session、policy 和 ticket。记忆引用只携带固定 snapshot/pin；工具先查索引，再预览，最后读取选择的原文。原生工具的来源记录与结果必须匹配，工具返回不自动成为成员的最终意见或生命周期决定。

`runCentralPlugin` 在本地 double 注册 provider 与 stream hook。每步先准入，随后保护层核对实际序列化请求，先记录 spend 再交给注入的离线 forward。最终 completed source、Body acceptance、receipt、settlement 和意见 staging 是不同记录。

重开先核验保存的来源与账本。只有完整一致的已完成来源才补齐同一票据的缺失本地记录；未知、冲突、异源或缺少完成证明的状态保持挂起。不能把后来的决定倒写成旧请求的成功，也不凭异常就再次调用 provider。

## 重要边界

- `sdk-runtime-double.mjs` 是可控模型，不是已安装的官方 runtime。
- 测试包含十个合成身份，但实际执行链只覆盖一个成员，不证明十成员并行或集体会议。
- 来源哈希与 lineage 检查不等于密码学身份认证或主机写入者排他控制。
- 临时 SQLite 持久化与模拟 session reopen 不等于跨进程、断电或真实服务器恢复。
- 读取预算与窗口限制不能被表述为删除历史或自动遗忘的许可。
- 官方加载函数在本副本无条件拒绝；生产接线、原身份迁移与 72 小时运行均在范围外。

`syntheticOnly` 与 `officialRuntimeExecuted` 是当前固定离线组成的报告标签，不能认证任意调用方注入的 SDK/deps。直接复用模块时须另行约束依赖、权限和网络。
