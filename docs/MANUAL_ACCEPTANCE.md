# 真实集成人工验收

以下步骤未执行时必须保持“待验证”，不能用 unittest 或双 subprocess 替代。
只使用明确选定的合成测试项目，不读取真实会话存储、不接入新账号、不更改全局配置。

## 两个真实 harness

1. 生成全新合成项目，记录工具版本、项目 ID 和根目录。
2. 将 generic/codex/claude render 片段合并进该项目对应入口，保留已有内容。
3. 在 harness A 的真实新会话中要求读取协议、运行 context、session start、task create/claim。
4. A 通过 progress 记录可辨识合成结果，回读事件，再 release 并输出 handoff。
5. 在 harness B 的真实新会话中粘贴 handoff。B 必须自己运行 context、创建不同会话、领取原任务。
6. B 通过 progress 提交结果和证据、进入 awaiting_review，记录原 task_id 未变。
7. 用户明确确认后记录 task accept；保留命令/结果证据及版本。公开报告只写合成信息。

存在某 harness 可执行文件不算已完成验证。不得为了验收擅自接入外部账号或持久凭据。

## 新会话自动加载

与手工粘贴交接分开验证：在两个目标 harness 的全新会话中，只给合成业务任务，
观察是否自动读取项目入口并先查询 Relay。保存实际观察。integration check=true 只能证明文件与 CLI 可用。

## 跨电脑与其他平台

原电脑释放领取、停止工作，导出完整包并记录 SHA256；传输到另一台明确授权电脑。
新电脑使用 Python 3.11+，先验证包摘要，恢复到新目录，local set 映射资源，doctor/context。
比对项目/任务 ID 相同、instance_id 不同、旧会话不能写入；新会话继续任务并回读。
原副本不再写入。Linux/macOS 也可运行同一 unittest 和 demo；只报告实际测试的平台与 commit。

## 已知边界

- 无身份认证，用户确认由调用方遵守协议；工具不判断真假。
- 领取与 SQLite 锁不锁业务文件；不自动判死、不自动抢占。
- WAL/SQLite 仅用于同机本地磁盘，不支持多机共享盘。
- 完整包的一致性依赖停工与变化检查，不提供跨文件系统事务。
- local.json 本机配置短锁中断后可能留下 local.lock；确认无 local set 正在运行后才手工移除该锁文件。
- 源码版本升级/数据库分叉合并不属于本版；不兼容 schema 拒绝恢复。
