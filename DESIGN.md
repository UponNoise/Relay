# Relay 设计

## 数据权威与模块

SQLite 是唯一业务权威；project.json 只存 project_id、schema_version。
local.json 保存 instance_id、环境名及外部资源映射，永不迁移。
PROTOCOL.md 是公共协作协议。上下文、handoff、HTML 都是只读派生快照。

模块：cli 解析与输出，store schema/事务/发现，service 业务写入，views 上下文与报告，
packages 迁移，resources 路径及证据，integration 模板，common 校验/错误/版本。
工具安装到目标项目 tools/relay；已有入口或 .relay 一律不覆盖。

## 身份与事务

UUID 标识项目、任务、事件、决策、证据、会话、实例。
任务领取独立 claim 表：task_id、session_id、generation、最近活动时间。
SQLite foreign_keys=ON；journal_mode=WAL（仅本地磁盘）；busy_timeout=250ms，
最多 4 次有界重试。每个变更用 BEGIN IMMEDIATE，防重检查、业务写入、项目 revision
递增和结果缓存同一事务。无外部命令，无长文件处理在事务中。
导出通过 SQLite backup API 取得一致快照，不能复制活动 DB/WAL 文件。

修改命令统一 --input-file JSON（- 表示 stdin）。业务变更要求 request_id；
请求规范化为排序 JSON（去除 request_id），命令名参与摘要；同 ID 同输入返回原结果，
异输入返回 duplicate_request_mismatch。init/local/export/import 使用可回读的操作结果；
业务防重以数据库为准，文件操作另记可验证操作标识。

任务摘要/公共字段修改要求 expected_revision 以及当前 session_id/generation；
非负责人仅可追加事件。成功返回对象 ID、revision、request_id。
recover 必须给原因，递增 generation，旧持有者写入失效；不按时间自动释放。
session 只在本地实例有效，迁移清除有效领取及会话，历史来源仍保留。

## 状态转换与验收

创建为 todo；领取不自动改变业务状态。
负责人可在 todo / in_progress / blocked / awaiting_review / cancelled 中显式转换。
done 只能由 task accept 从 awaiting_review 进入，必须 confirmation_source 和 note；
同时追加 acceptance 事件。done/cancelled 为终态，不提供隐式重新打开。
协议要求先获得用户明确确认。工具不验证调用者是真人。
release 不改变状态。recover 不隐式重写摘要。

## 读取、路径与资源

从 cwd 向上发现 .relay；遇到多个候选报 project_mismatch，显式 --project 精确选根。
每次读取核对 project.json 和 DB 身份、版本。JSON stdout 只有一份 JSON；
错误结构 {ok:false,error:{code,message,details}}；退出 2 为输入/业务错误，3 为忙，4 为完整性。
文本默认简洁。context 的 tasks/decisions/events/evidence 各自有 limit，显示 truncated 与继续查询说明；
支持 task/since/limit/offset，不调用模型。

project_file 只允许项目根内相对普通文件，拒绝越界与符号链接。
external_file 使用 resource:name/relative，由 local.json 映射；url 不下载。
digest 使用 SHA256；verified_fact 必须带验证方法或证据。
所有 HTML 记录转义；URL 作为文本显示，不执行。

## 迁移安全与一致性

协作包含工具源码、协议、身份、DB backup、证据索引、manifest、恢复说明。
完整包另加显式 include 文件，支持 exclude；拒绝私有路径、凭据常见命名、缓存、
虚拟环境、旧包、DB 附属文件、符号链接。默认单文件上限 50 MiB。
清单可 --dry-run 查看，不能保证识别所有秘密。
完整包要求 --quiesced 且无活动领取；读取前后及封包前比对文件摘要/元数据。
不能锁住外部写入者，用户须暂停业务工作。

manifest 含 export_id/project_id/source_instance_id/tool_version/schema_version/created_at/
snapshot_revision、文件路径/大小/SHA256、外部缺失清单。manifest 本身不自校验，不声称签名认证。
恢复先验证所有 ZIP 路径、重名、大小、符号链接、manifest 完整对应及 hashes，
在同一父目录临时目录校验 DB integrity_check/foreign_key_check，再原子安装到新建或空目录。
保留实体 ID，生成新 instance_id，移除旧会话有效性并记录迁移事件与被释放领取。
不合并分叉，不自动停旧副本。只接受当前 schema 1。

## 接入与验证边界

Codex 的项目级 AGENTS.md、Claude Code 的项目级 CLAUDE.md 仅放最小接入片段；
不自动编辑入口，更不修改全局配置。integration check 只查文件、路径、CLI 可用性。
官方机制参考（核对日期 2026-10-26）：
- https://developers.openai.com/codex/guides/agents-md
- https://code.claude.com/docs/en/memory

模板存在不代表新会话加载成功。独立 CLI 进程与真实 harness 分层报告。
