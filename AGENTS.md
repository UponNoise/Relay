# Relay 开发约定

开始工作先读 README.md、DESIGN.md、docs/SPEC.md。运行测试前读 README.md 的测试说明。
只改本仓库。Python 3.11+，运行时仅标准库，不改系统 Python、PATH 或全局 harness 配置。
测试使用 tempfile 独立项目。公开文件仅源码、中文文档、合成样例。
不得提交真实输入、凭据、数据库、日志、机器配置。先查看 git diff --cached，再提交。
禁止把双进程测试称为真实双 harness，或把本机恢复称为跨电脑验收。
