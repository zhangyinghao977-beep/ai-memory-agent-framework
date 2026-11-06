# 第二次准备：资源采样修正，未改研究设置

第一次位于相邻目录 `granularity-pilot-20261107`。2026-11-06 16:52:04 UTC，在准备第一个种子后触发 INCOMPLETE_RESOURCE_STOP。没有 FROZEN、训练回执或训练结果，也没有开始训练；该目录和原始停止证据保留。

记录显示新进程仅耗费0.140625 CPU秒、约35.6MB RSS。三次暂停计算的初始测量中，CPU22分别为0%、15.4%、11.5%；生成数据后约0.185秒的非阻塞窗口显示75%，全机平均49.05%。此短窗口包含自身准备消耗，不能断言75%均来自其他实验。

本次只修正资源测量：每次负载采样都暂停自身计算0.4秒，与初始门禁一致。仍使用同一CPU、IDLE优先级、约10%单核软节流、30CPU秒/240墙钟秒预算及原停止阈值。未改变种子、题目、分组、模型、监督、训练预算或预注册指标。没有看过训练结果后改设计；若新测量仍触发门禁，继续停止。

This attempt fixes a resource-measurement window before any training. The first attempt and its stop record are retained. Sampling pauses this process, avoiding its own short preparation burst in the external-load observation. Research settings and safety thresholds are unchanged.
