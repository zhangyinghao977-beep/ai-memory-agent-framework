# 依赖与可复现环境

[English](DEPENDENCIES.en.md)

- 已验证：Linux，Node.js 24.22.1。`.nvmrc`、`.node-version`、`engines.node` 固定该版本。
- 运行/测试依赖仅为 Node 内置模块。使用 `node:sqlite`、Web Response/Headers、AbortSignal、测试运行器等能力。
- npm dependency 与 devDependency 均为空。锁文件没有下载条目、registry 地址或认证配置。不需要 `npm install`。
- 本预览不安装或捆绑 DeepSeek Harness、Cordis、模型 SDK、Python、数据库二进制或 Node 分发包。
- 默认 `npm test` 先加载本地网络防误调用保护，再运行研究测试。公共 provider URL 仅保留作序列化契约的比较常量；注入 forward 返回合成 Response。
- 只验证上述确切环境。没有宣称其他 Node 24 小版本、Windows 或 macOS 已兼容。
- 若以后加入真实 SDK、CI action 或 npm 包，须固定版本/提交并重新审查许可、依赖闭包、网络与秘密暴露面。
