# Relay

Relay 是本地优先、离线可用的跨 harness 协作 CLI。Python 3.11+、SQLite、argparse，运行时只使用标准库。

当前里程碑：S1 基础存储、初始化、任务/事件与上下文已实现，后续按 [spec](docs/SPEC.md) 推进。

## 边界

只保存项目协作状态，不控制 Agent、不调用模型、不执行记录中的命令、不提供常驻服务或多机实时同步。
数据库领取不锁业务文件；用户验收是显式记录而非身份认证。禁止多机通过网络盘共写 SQLite。

## 开发流程

先读 [需求追踪](docs/REQUIREMENTS.md)、[设计](DESIGN.md)、[验收计划](docs/SPEC.md)。
每阶段实现后，在临时项目运行相关测试，审查暂存文件和隐私，提交推送并核验远端 commit。
不会公开原始附件、真实对话、凭据、运行数据库、日志或本地配置。只提交源码、中文文档和合成示例。
不添加许可证，不发布软件包。

计划入口：`python tools/relay --help`。计划测试：`python -m unittest discover -s tests -v`。
