# Relay 项目接入

这是接入已有项目。先读 .relay/PROTOCOL.md，再运行 python tools/relay context --json。
不要重复 init 或重建已有任务。创建自己的 session，检查和领取分工后再修改业务文件。
重要结果用 progress 记录证据、摘要、下一步；按返回 ID 回读。重试沿用 request_id。
交付先 awaiting_review，只有用户明确确认后才能 task accept。
交接只是快照；重新查询最新状态。路径以当前项目实际根目录为准。
