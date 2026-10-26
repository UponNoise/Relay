# Relay

Relay 是本地优先、离线可用的跨 harness 协作 CLI。用 Python 3.11+ 标准库、SQLite 和 argparse，保存项目、任务、进展、决策、证据与交接上下文。每次调用是短进程，不需要全局安装、模型账号、Docker、Node 或常驻服务。

第一版功能已实现，验收层级及未验证项见 [TEST_REPORT.md](TEST_REPORT.md)。[设计](DESIGN.md)、[需求追踪](docs/REQUIREMENTS.md)、[分阶段 spec](docs/SPEC.md)、[公共协议](tools/relay/PROTOCOL.md) 随源码交付。

## 启动与快速体验

在源码目录运行：

```text
python tools/relay --help
python tools/relay --version
python scripts/demo.py --output exports/demo
```

示例目录必须尚不存在。该脚本通过真实 CLI 进程完成 A 领取、记录、释放、B 续接、待验收、合成验收，再生成 HTML、完整包并恢复自检。它使用合成数据，两个 CLI 会话不代表两个真实 harness。

查看生成的 `exports/demo/project/artifacts/report.html`、`handoff.md` 与 `exports/demo/full.zip`。
仓库中的 [示例报告](examples/report.html) 和 [交接示例](examples/handoff.md) 只含合成内容。

## 首次初始化

把下面内容保存为 UTF-8 的 `init.json`；请求 ID 自己选择唯一值：

```json
{"request_id":"example-init-001","name":"示例项目","goal":"完成一个明确成果","scope":"本地工作","working_agreements":"先读后写，记录证据","acceptance_policy":"用户明确确认","environment":"home-codex"}
```

```text
python tools/relay --project "你的项目根目录" init --input-file init.json --json
python tools/relay --project "你的项目根目录" doctor --json
```

不会覆盖已有 `.relay` 或其他已有 `tools/relay`。初始化安装项目内 CLI、协议和本机配置，不改全局 PATH/Agent 设置。
已有业务文件保留。将 `.relay/`、日志、导出包、本机配置加入业务仓库忽略规则，勿把运行状态公开提交。

## 接入已有项目

在项目根目录先读 `.relay/PROTOCOL.md`，运行 `python tools/relay context`。
子目录也可通过 CLI 的绝对路径运行，会向上发现根目录；嵌套项目必须用 `--project` 明确选择。

```text
python tools/relay integration render --harness codex
python tools/relay integration render --harness claude
python tools/relay integration check --harness codex --json
```

将片段手工合并至项目级 AGENTS.md 或 CLAUDE.md，保留原内容；通用模板使用 `--harness generic`。
命令只输出片段，不自动编辑入口。check 仅检查文件、路径、CLI；新会话是否自动加载必须另测。
入口机制已依据 [Codex 官方文档](https://developers.openai.com/codex/guides/agents-md) 与 [Claude Code 官方文档](https://code.claude.com/docs/en/memory) 核对。

## 日常协作

修改统一使用 `--input-file FILE`，或 `--input-file -` 从标准输入读 JSON。
可以保存包含中文和多行内容的 JSON 文件，避免 shell 转义。每次新操作使用新的 `request_id`；
网络/终端中断后的同操作重试必须沿用原 ID 和输入。成功结果包含对象 ID、revision 和 request_id，用查询命令回读。

下面表格给出每个修改的 JSON 字段；所有行另须 request_id。ID 使用实际返回值，勿照抄占位符。

| 命令 | 必要/常用字段 |
|---|---|
| session start | environment（可选；默认本机环境名） |
| task create | title, objective, acceptance_criteria |
| claim | task_id, session_id |
| task update | task_id, session_id, generation, expected_revision；要修改的 title/objective/acceptance_criteria/current_summary/next_step/blocker/status |
| progress | session_id, content；可选 task_id, event_type, evidence_refs；若同时改任务字段，还需 generation, expected_revision |
| release | task_id, session_id, generation |
| recover | task_id, session_id, reason |
| task accept | task_id, session_id, expected_revision, confirmation_source, note |
| project update | expected_revision；name/goal/scope/working_agreements/acceptance_policy |
| decision add | statement, rationale, provenance；可选 task_id, supersedes, confirmation_reference, verification_method, evidence_refs |
| evidence add | kind, locator, description；可选 digest, verification_method, verified_at |
| local set | environment 或 resources（完整映射对象） |
| export / import / report | 只需 request_id；路径和包选项放在命令行 |

领取不自动改变业务状态。状态为 todo、in_progress、blocked、awaiting_review、done、cancelled；
普通更新不能写 done，必须从 awaiting_review 执行 task accept。终态不可重新打开。
协议要求只有用户明确确认后才记录完成；本地工具不认证“人类”，不能提供不可绕过的审批。

非负责人可以追加结果/建议/阻塞，不能覆盖当前摘要。progress 的事件与摘要更新是同一事务。
过期 revision 返回 revision_conflict；接管后的旧代次返回 stale_claim。
recover 不判断旧进程已死，必须显式给原因；status 显示持有者和最后活动时间。
领取只保护 Relay 业务状态，不锁真实业务文件。

查询命令：

```text
python tools/relay status
python tools/relay task list --json
python tools/relay task show --task TASK_ID --json
python tools/relay session show --id SESSION_ID --json
python tools/relay event show --id EVENT_ID --json
python tools/relay decision list --id DECISION_ID --json
python tools/relay evidence check --id EVIDENCE_ID --json
python tools/relay project show --json
python tools/relay local show --json
python tools/relay context --task TASK_ID --limit 20 --offset 0 --json
python tools/relay handoff --task TASK_ID
```

context 支持带时区的 `--since 2026-01-01T00:00:00+00:00`、limit、offset；
明确标记截断并给下一页。指定任务包含项目级与该任务的有效决定/事件。
handoff 是生成时快照，接收者必须重新读取协议和最新 context，不重复 init 或创建原任务。

决策 provenance 为 user_confirmed、agent_proposed、verified_fact、unverified。
user_confirmed 要求确认引用；verified_fact 要求验证方法或证据，但工具不证明自然语言结论。
错误历史追加 correction；新决策用 supersedes 替代旧决策，不改历史。

## 证据与本机路径

project_file 使用正斜杠相对文件路径，例如 artifacts/result.txt。
external_file 使用 `resource:assets/path/file.txt`；local set 的输入例如：

```json
{"request_id":"local-map-001","environment":"new-computer","resources":{"assets":"D:/Assets"}}
```

POSIX 下填写该机绝对路径。resources 是整体替换；本机配置和本机请求收据只存在 local.json，
不进入迁移包。url 只存 http/https 引用，不自动访问；note 直接保存文字。digest 是小写 SHA256。
evidence check 和 doctor 的 `data.ok` / 单项 `ok` 表示检查是否通过；运行诊断成功不意味着资源齐全。

## 导出、恢复与自检

先停止业务工作，查看清单。把 `{"request_id":"export-preview-001"}` 保存为请求 JSON：

```text
python tools/relay export --kind collaboration --output exports/relay.zip --dry-run --input-file request.json --json
python tools/relay export --kind collaboration --output exports/relay.zip --input-file request.json --json
```

协作包含工具源码、协议、身份、SQLite backup 快照、证据索引、manifest 和恢复说明。
不会复制 local.json。完整包另加明确选择的文件：

```text
python tools/relay export --kind full --quiesced --include artifacts/result.txt --exclude "*.tmp" --output exports/full.zip --dry-run --input-file request.json --json
```

检查后去掉 --dry-run 执行。完整包无活动领取才允许；include 可重复且只接受单个文件，不递归整个目录。
默认排除私有配置、常见凭据、虚拟环境、缓存、日志、数据库临时文件和旧包；单个选择文件上限 50 MiB、包总量 500 MiB。
排除规则不能识别所有秘密，发布/分享前必须检查清单。文件在打包期间变化会失败。
数据库快照与业务文件并不受同一事务保护，工具不能阻止外部进程改文件。

恢复使用一个新的请求 ID，目标必须新建或空目录：

```text
python tools/relay import --archive exports/full.zip --destination "恢复目录" --input-file import-request.json --json
python tools/relay --project "恢复目录" local set --input-file local-map.json --json
python tools/relay --project "恢复目录" doctor --json
python tools/relay --project "恢复目录" context
```

恢复验证路径、manifest、SHA256、DB integrity/外键、身份/schema 后安装。
项目/任务 ID 保留，新实例 ID 重新生成，旧会话失效，领取释放并记录迁移事件。再次工作先创建新会话。
缺失外部资源会出现在 manifest 和 doctor 中；协作包未包含的项目证据文件也会被 doctor 检出。
只有 schema 1 可恢复。manifest 是校验清单，不是签名；只恢复可信来源的包，包内含可执行 CLI 源码。
快照不会停止旧副本；迁移后不要继续写旧副本。分叉不能自动合并，不支持多机从共享盘共写 SQLite。

## 离线报告

```text
python tools/relay report --output artifacts/status.html --input-file request.json --json
```

输出单文件、转义所有记录文本的只读 HTML。含生成时间和快照 revision，无 CDN、脚本、外部字体或服务。
既有输出不覆盖；同 request_id 的相同文件操作可回读原收据。新报告使用新路径和新 ID。

## JSON 与退出码

成功为 `{"ok":true,"data":...}`；失败为 `{"ok":false,"error":{"code":"...","message":"...","details":{}}}`。
--json 的 stdout 只含 JSON，文本错误写 stderr。退出码：0 请求完成；2 输入/业务错误；3 忙超时；4 完整性/IO 错误。
doctor、evidence check、integration check 还需检查返回的诊断字段，不能仅看退出码。

错误 code 包括 not_found、invalid_input、project_mismatch、claim_conflict、revision_conflict、
stale_claim、duplicate_request_mismatch、database_busy、missing_resource、incompatible_version、integrity_error。
业务请求 ID 在项目数据库内唯一；本机配置为实例作用域；报告为目标文件作用域。读操作无需 request_id。

## 测试与源码交付

运行测试前请阅读本节。测试只在 tempfile 创建合成项目，包含真实 subprocess 并发与失败路径：

```text
python -m unittest discover -s tests -v
python scripts/package_source.py --output dist/relay-source-0.1.0.zip
```

源码打包从经审查的 Git index 取文件，附 .sha256 校验文件，不打包 venv、测试数据库或日志。
打包本身需要 Git；解压后的 CLI 与测试只需 Python。请在提交/暂存完整源码后打包。
没有许可证声明或软件包发布。公开仓库仅含源码、中文文档、合成样例。

真实第二 harness、新会话自动加载与跨电脑运行按 [人工验收步骤](docs/MANUAL_ACCEPTANCE.md) 单独验证。
不控制其他 Agent、不执行记录中的命令、不调用模型、不接公司服务、不进行分布式同步。
