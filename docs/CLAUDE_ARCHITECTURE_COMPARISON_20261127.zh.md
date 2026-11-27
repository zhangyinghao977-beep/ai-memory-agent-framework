# 红尘仙与 Claude：从记住进度到接着执行

[English](CLAUDE_ARCHITECTURE_COMPARISON_20261127.en.md) · [公开原型](https://github.com/zhangyinghao977-beep/hongchenxian-prototype)

本文对照截至 2026 年 11 月 27 日的公开文档，不推断 Claude 的内部实现，也不比较模型能力或产品成熟度。主对照是 Claude Managed Agents；Claude Code 的功能另行标注。红尘仙是独立 Agent 的研究原型，阶段 5 是另外的人工智能研究目标。

## 1. 两边如何分工

[Anthropic 的 Managed Agents 架构](https://www.anthropic.com/research/managed-agents)把会话事件记录、调用模型和工具的运行框架、实际执行环境分开。[动态工作流](https://platform.claude.com/docs/en/managed-agents/workflow-runs)还允许 Agent 编写程序，分阶段调用多个 Agent、汇合结果。双方的共同点是：运行和协调并不全靠模型一次生成。红尘仙的分工从三个问题出发：What 是已知事实及其来源，由记忆库提供；Why 是为何选择这条路，由逻辑判断；How 是怎样执行，由状态机（FSM）负责。事件链登记三者间的转换，也给各条正在执行的路径保留各自的进度。它既不是完整的聊天记录，也不只是事后画出来的流程图。

## 2. 记忆：什么可以读，什么可以改

[Claude Code 自动记忆](https://code.claude.com/docs/en/memory)会把纠正与经验写成可编辑笔记，下次作为上下文。[Managed Agents Dreams](https://platform.claude.com/docs/en/managed-agents/dreams)也能回看经历、产出可以审查的独立记忆副本，输入库不变。红尘仙同样把工作副本和可信来源分开，但明确把记忆原文、关键词索引和修订分开：短期工作库只重建所需部分，修改先留在隔离副本，经显式合并才作为补丁进入长期库。需要隔离访问时，调用者只看到获准发布的索引图，不直连可信源。这是公开原型分别演示的机制，不是对两边隔离能力的排名。

## 3. How：一段过程为什么值得成为反射

[Claude Code Skills](https://code.claude.com/docs/en/skills)可提供任务说明和配套脚本；[Hooks](https://code.claude.com/docs/en/hooks#pretooluse)能按事件运行代码或阻止工具调用。所以官方同样可以用程序约束执行，不能把 Skills 和 Hooks 都说成提示词。红尘仙所谓 guide / subguide，是把**已经能控制的过程**封装起来，供其他任务复用；封装不是可控性的来源。一个条件反射就是一种 How：条件已登记，状态机可直接调用现成工具，并依据结果决定是否完成，不必请模型每次重新想。反射也可能被另一个反射中断；事件链可以临时登记它的执行位置和未确认结果。

## 4. 续接：记住发出动作，不等于动作完成

Anthropic 的[长任务示例](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents)用进度文件、Git 和环境检查接班；Managed Agents [工具事件](https://platform.claude.com/docs/en/managed-agents/reference)本身也区分调用和工具结果。我们要比较的是在同一个中断下，**究竟保存了什么，以及恢复时使用哪条证据**，而不是断言官方不能恢复。

一次单独的离线小实验里，模拟表单发出提交后、结果返回前，被可跳过的提示打断。保存原提交状态的版本只发出一次请求，恢复后等待匹配的结果；刻意丢弃该状态并重启反射的对照发出了两次请求。这不是 Claude 对照，没使用真实网站、账号，也未验证进程崩溃恢复或多层并发。[DLC 03](https://github.com/zhangyinghao977-beep/hongchenxian-prototype/tree/main/dlc03)演示事件链和反射的基础机制；上述嵌套试验未随公共原型发布。

## 5. 阶段 5：从经验长出可执行的逻辑

[阶段 5 设计](../projects/hongchenxian/demo/STAGE5.zh.md)的问题是：系统能否从有来源的多次经验里，学出带适用条件的抽象映射，再把它绑定到当前对象与证据，得到可执行的具体逻辑？软件里的 DNA／蛋白质类比分别指这两种表示。单次执行结果不能直接改写抽象逻辑。这是尚未实现的研究目标，不是把自动笔记改个名字，也不是声称能完整拆出现有 Transformer 的逻辑。

**欢迎挑错：** 给双方相同的工具、权限和故障时间点。让工具先收到请求，故意延迟结果，再中断执行。请指出哪一层保存待确认的动作、恢复时用什么证据接回、何时必须停下来。若已有公开的 Skills、Hooks 或 Managed Agents 组合能完整覆盖这个案例，欢迎指出最小配置，我们就有了可以一起复跑的对照。
