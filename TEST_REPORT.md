# 验收记录

S0：完整需求读取完成；24 项追踪覆盖原输入 15 章节，状态机、事务和迁移边界已确定。
本阶段无可执行代码，功能测试未运行。目录预先不存在，未覆盖既有项目。
S1：Windows / Python 3.12.0，运行 `python -m unittest discover -s tests -v`：7 项通过。
覆盖初始化重试/防覆盖、中文多行、子目录与显式发现、嵌套拒绝、身份冲突、JSON 错误、项目 revision、任务/事件/context。
首次发现任务 INSERT 占位符数量错误，修正后全部通过。所有数据均为临时目录内的合成数据。
S2：同一测试命令共 12 项通过；独立进程竞争恰一成功、领取不改业务状态、原请求重试、异输入拒绝、progress 回滚、旧代次失效、release/accept、有限锁等待均通过。
S3：同一测试命令共 16 项通过；覆盖决策来源与替代、证据 hash/缺失/越界、本地资源配置防重、交接截断、模板生成不改已有入口、接入静态检查。
S4：同一测试命令共 22 项通过；两类包、显式文件选择/排除、完整包活动领取拒绝、恢复 ID/新实例/旧会话失效、hash/穿越/schema/非空目标拒绝、doctor 缺失资源、HTML 转义与报告重试通过。
父线程在 S3 commit 474ab71 的独立 Linux 环境复验 16 项通过，并发现任务上下文遗漏项目级决定；已在 S4 修复，新增项目/任务决定和项目级事件回归通过。此 Linux 证据仅覆盖 S3，不代表当前版本或真实第二 harness。
S5：完整回归 30 项通过；随后补充 manifest 缺 export_id 用例，失败矩阵 9 项全部通过（共 31 项用例）。覆盖独立进程、锁超时、原请求重试、原子回滚、打包期间文件变化、原始 ZIP 路径/别名/符号链接、DB 身份与外键损坏、输入文件及时间过滤。
Windows ZIP 名称规范化曾使非法路径落入错误类别，已改为先校验 orig_filename；父线程发现缺少 manifest 身份字段出现 KeyError，已显式校验并补回归。
父线程另在 S4 commit 986d6f0 上独立 Linux 复验 22/22 通过。
S6：Windows / Python 3.12.0 完整运行 `python -m unittest discover -s tests -v`，31/31 通过。
父线程在 S5 commit 35e3ba20f296dcc250ab0b1a4e47a0000b64c116 的独立 Linux / Python 3.12.14 环境运行同一套测试，31/31 通过。此证据不等于真实第二 harness 或跨电脑恢复。

## 实际 CLI 演示

`python scripts/demo.py --output exports/demo-final` 通过真实短进程完成：A 创建会话/领取/记录/释放，B 读取/创建会话/领取/结果/待验收，合成显式验收、生成交接和 HTML、完整包清单/导出、新目录恢复及使用恢复后 CLI 执行 doctor。
初次演示在 Windows 发现示例文本 CRLF 与内存 LF 的摘要差异，改为计算实际文件字节后通过；这是示例修复，迁移校验正确识别了差异。
当前 Codex 会话直接执行过 `python tools/relay --help`、合成项目 status、恢复项目 doctor --json 和 integration check --harness codex --json。
源码包从审查后的 Git index 构建；输出到 dist，附 SHA256 文件。解压后复验命令为 `python tools/relay --help` 与 `python -m unittest discover -s tests -v`。

## 验收分层

| 层级 | 结果与证据 |
|---|---|
| 自动化行为测试 | Windows 当前版本 31 项通过；Linux S5 31 项由父线程独立通过 |
| 两个独立 CLI 进程 | 竞争测试恰一成功；合成 A/B 接力演示通过 |
| 当前 Codex harness 调用 | 本会话直接运行 help/status/doctor/integration check 通过 |
| 第二真实 harness | 未运行；已提供 Claude/Codex/通用模板和人工步骤 |
| 新会话自动加载 | 未验证；integration check 明确返回 automatic_loading_verified=false |
| 跨电脑恢复 | 未运行；同机新目录恢复通过，不冒充换机验收 |

当前无已知阻断基础功能的问题。无 CI 配置，远端通过阶段 SHA 核验；没有发布软件包。
公开样例仅合成内容，交接根路径替换为占位符。真实运行 DB、日志、本机路径配置和原始附件不提交。
