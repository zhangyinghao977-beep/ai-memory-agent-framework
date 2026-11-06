# 证据等级与已知缺口

[English](EVIDENCE.en.md)

## 本发布副本

源基线为 `hcx-central-step-abi-20261106-v04`，封包 SHA256 为 `f8a1d1675f8b98d715a811d1e34e3f6defaad5677a1ac97d5721f01b53a2139a`。32 个代码文件纳入白名单；30 个逐字保留，2 个仅作预览隔离改动，见仓库根目录 `evidence/SOURCE_MANIFEST.json`。

最终复跑摘要见仓库根目录 `evidence/VALIDATION.json`。原版 70 项 Node 测试中保留 69 项，另 1 项改为禁止官方 SDK 加载检查。新增网络保护测试单独计数，不能说所有测试与原包逐字相同。原包 36 项 Python mock/static runner 测试未纳入本最小副本，也不计入本副本结果。

## 历史结果，仅摘要

- central-step v04：本地 SDK-double 70 Node、36 Python 通过；官方五案例/十 worker 矩阵未执行，安装版本 metadata 门未打开。
- policy a04 与 native index a03：留存官方 synthetic 通过记录，分别检验迁移、原生工具/读取契约，不证明真实成员恢复。
- rolling a03：首 worker 的 17 次 synthetic stream 完成，随后 runner 在 raw-prefix capture 失败；完整矩阵失败/不完整，reopen 及后续案例未执行。
- 真实池短测：7 次已消耗请求，5 个 accepted settlement，另 2 个缺 receipt，3 个成员未发请求；结果失败，原状态保留。真实连续 sleep/wake/stop、同一身份恢复与 72 小时目标尚未完成。

这些是已有审核记录的公开化摘要，本副本没有携带原始实验日志、服务器标识或真实内容，读者不能仅据摘要独立复核全部历史实验。未来公开原始证据需另行去标识与授权。

## 仍未证明

真实 SDK 的 serializer/SSE 行为、安装版本兼容性、可信主机源 custody/排他写入、密码学成员认证、原身份的 append-only 迁移、十成员真实协作、真实成本、生产耐久性和至少 72 小时连续运行。
