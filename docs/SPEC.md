# 分阶段 spec 与验收门槛

## 工作流程

读取需求 → 需求追踪/状态机/CLI/验收 → S0 提交推送 → 按序实现 →
阶段测试 → staged diff 与隐私检查 → commit/push → 远端 SHA 核验。
每阶段失败先修复，不用后续功能掩盖失败。真实集成无法验证时明确列出。
不设 CI（当前计划），本机 Windows 记录实际测试环境；可提供跨平台复验命令。

| 阶段 | 实现 | 验收门槛 |
|---|---|---|
| S0 规划 | README、DESIGN、需求追踪、本 spec、忽略规则 | 24 个追踪条目覆盖全部原章节；明确错误/状态/事务/恢复规则；原文和私人数据不入库 |
| S1 基础 | schema、init、发现、CLI、任务、事件、context | 重复 init 拒绝；中文/空格/多行；显式与子目录；身份不匹配；JSON 错误；写入回读 |
| S2 一致性 | session/claim/release/recover/revision/防重/accept | 独立进程抢占恰一成功；旧版本/代次拒绝；相同重试一条事件；异输入失败；无半完成 |
| S3 协作 | 决策、证据、handoff、协议与模板、status | 来源校验、证据路径/摘要、有限上下文、模板 render/check、不覆盖入口 |
| S4 迁移查看 | 两种包、导入、doctor、HTML | backup 快照、清单/排除、hash/路径安全、新实例、旧领取失效、缺资源、HTML 转义 |
| S5 失败矩阵 | 补齐锁/并发/迁移/不兼容/变化测试 | unittest 全通过；有限忙等待；恶意包/非空目的地不落地；变化包不交付 |
| S6 交付 | 真实 CLI 接力、示例生成、文档、源码 zip/SHA256 | CLI A→B→待验收→显式验收；源码包解压可运行；实际层级报告；全部源码已推送 |

## 最终 CLI

全局选项：--project PATH、--json、--input-file PATH（- 为 stdin）；复杂修改字段通过 JSON。
init / doctor / status / context；project show/update；local show/set；
session start/show；task create/list/show/update/accept；
claim / release / recover；progress；event show；
decision add/list；evidence add/check；handoff / report；
export / import；integration render/check。
查询目标 --task / --id，context 支持 --since --limit --offset。
export 支持 --kind collaboration|full、--output、--include（重复）、--exclude（重复）、--dry-run、--quiesced。
import --archive --destination。report --output；模板 --harness generic|codex|claude。
JSON 输入拒绝未知字段，错误不静默忽略。

## 验收分层

1. 单元/行为测试：必须本机执行并报告数量。
2. 独立 CLI 进程：必须实测，不冒充 harness。
3. 当前 Codex harness：实际调用 CLI 留命令与结果。
4. 第二真实 harness：仅实际运行才标通过；否则给人工步骤。
5. 新会话自动加载：必须看到新会话读协议及查询，不能以模板存在代替。
6. 跨电脑：在另一台机器恢复并 doctor/context 才通过；同机恢复只算自动化迁移。
