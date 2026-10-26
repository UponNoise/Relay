接入已有项目；这是生成时快照，必须重新查询最新状态。
项目 ID：375a1781-85e1-484c-8cdb-292dd28fe6ed
本机根目录：<PROJECT_ROOT>
路径以目标电脑实际根目录为准。不要重复初始化或创建已有任务。
先读 .relay/PROTOCOL.md，运行 python tools/relay context --json。
写入用 --input-file FILE（UTF-8 JSON）或 --input-file -（stdin）；每次新操作用新 request_id，重试沿用原 ID 与输入。
会话示例：python tools/relay session start --input-file session.json --json；JSON: {"request_id":"NEW_UUID","environment":"YOUR_ENV"}。
领取示例：python tools/relay claim --input-file claim.json --json；JSON: {"request_id":"NEW_UUID","task_id":"EXISTING_TASK_ID","session_id":"RETURNED_SESSION_ID"}。
写结果用 python tools/relay progress --input-file progress.json --json；JSON 含 request_id、task_id、session_id、content、evidence_refs。
同时改摘要需 generation（领取返回值）、expected_revision（task show 返回值）、current_summary、next_step、blocker 和 status。
状态 todo/in_progress/blocked/awaiting_review；不要直接写 done。未持有任务只追加事件；claim_conflict 时先沟通，禁止绕过分工。
创建自己的 session start；读取 task show 后 claim，已有负责人则沟通或显式 recover 并说明原因。
先读后写，progress 记录结果/证据/下一步；按返回 ID 回读；交付 awaiting_review，用户明确确认后 accept。
{
  "project": {
    "project_id": "375a1781-85e1-484c-8cdb-292dd28fe6ed",
    "name": "合成接力示例",
    "goal": "由两个 CLI 会话接力生成示例成果",
    "scope": "仅合成数据，不代表真实 harness 集成验收",
    "working_agreements": "先读后写、领取、证据、回读、显式验收",
    "acceptance_policy": "用户明确确认",
    "schema_version": 1,
    "revision": 7,
    "created_at": "2026-10-26T09:08:52.457404+00:00",
    "updated_at": "2026-10-26T09:08:53.726573+00:00"
  },
  "generated_at": "2026-10-26T09:08:53.919357+00:00",
  "collections": {
    "tasks": [
      {
        "task_id": "72139a8f-ba6a-466e-8202-74ff1ba6bcb9",
        "project_id": "375a1781-85e1-484c-8cdb-292dd28fe6ed",
        "title": "制作示例成果",
        "objective": "完成一份可校验文本",
        "acceptance_criteria": "文本内容完整，SHA256 可核验，交接可续接",
        "status": "in_progress",
        "current_summary": "已确认合成输出格式",
        "next_step": "由 B 生成并验证成果",
        "blocker": "",
        "revision": 2,
        "created_at": "2026-10-26T09:08:52.775572+00:00",
        "updated_at": "2026-10-26T09:08:53.342757+00:00"
      }
    ],
    "decisions": [
      {
        "decision_id": "da76f991-9512-4a11-bdd4-fd0783bd3c1e",
        "project_id": "375a1781-85e1-484c-8cdb-292dd28fe6ed",
        "task_id": null,
        "statement": "示例只使用合成内容",
        "rationale": "避免真实信息进入示例",
        "provenance": "verified_fact",
        "confirmation_reference": "{\"confirmation_reference\":\"\",\"evidence_refs\":[],\"verification_method\":\"本脚本使用固定合成字符串\"}",
        "supersedes": null,
        "created_at": "2026-10-26T09:08:53.532884+00:00"
      }
    ],
    "events": [
      {
        "event_id": "705ae140-8f26-4c6e-a2d7-362924b9b854",
        "task_id": "72139a8f-ba6a-466e-8202-74ff1ba6bcb9",
        "event_type": "handoff",
        "content": "{\"generation\":2,\"operation\":\"release\",\"previous_claim\":{\"generation\":1,\"session_id\":\"8bc58b3d-970c-4d7f-986b-5543567dab71\",\"task_id\":\"72139a8f-ba6a-466e-8202-74ff1ba6bcb9\",\"updated_at\":\"2026-10-26T09:08:53.342757+00:00\"},\"reason\":\"\",\"session_id\":null}",
        "source_environment": "demo-cli-A",
        "session_id": "8bc58b3d-970c-4d7f-986b-5543567dab71",
        "recorded_at": "2026-10-26T09:08:53.725571+00:00",
        "evidence_refs": [],
        "request_id": "3ff08bee-068f-4344-a9ae-989192e0c989"
      },
      {
        "event_id": "68d2360f-6efe-4966-a1f5-8c5bcc3a3a68",
        "task_id": "72139a8f-ba6a-466e-8202-74ff1ba6bcb9",
        "event_type": "progress",
        "content": "A 完成第一部分",
        "source_environment": "demo-cli-A",
        "session_id": "8bc58b3d-970c-4d7f-986b-5543567dab71",
        "recorded_at": "2026-10-26T09:08:53.342757+00:00",
        "evidence_refs": [],
        "request_id": "829a27c3-195e-4d3c-b589-77daa5b0a790"
      },
      {
        "event_id": "95d139c9-c2a5-4804-b462-d8f28871b79a",
        "task_id": "72139a8f-ba6a-466e-8202-74ff1ba6bcb9",
        "event_type": "handoff",
        "content": "{\"generation\":1,\"operation\":\"claim\",\"previous_claim\":null,\"reason\":\"\",\"session_id\":\"8bc58b3d-970c-4d7f-986b-5543567dab71\"}",
        "source_environment": "demo-cli-A",
        "session_id": "8bc58b3d-970c-4d7f-986b-5543567dab71",
        "recorded_at": "2026-10-26T09:08:53.154580+00:00",
        "evidence_refs": [],
        "request_id": "99671434-a2a8-48dd-9ee8-9e634e948c6e"
      }
    ],
    "evidence": []
  },
  "truncated": {
    "tasks": false,
    "decisions": false,
    "events": false,
    "evidence": false,
    "claims": false
  },
  "claims": [],
  "continuation": {
    "next_offset": 20,
    "instruction": "Use --offset with --limit; task show includes terminal tasks."
  }
}
