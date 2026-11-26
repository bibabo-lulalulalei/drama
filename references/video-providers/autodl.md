# AutoDL 视频 Provider

本文件集中维护 `video_provider: autodl` 的实例、电源、凭证、Zealman/ComfyUI workflow、旧任务恢复和持久化资产找回。通用选择规则读取 `../video-provider.md`；H3 模型能力、导演 Prompt 和真实尾帧连续性仍分别读取 `../video.md`、`tools/h3.json` 与 h3-prompt-writing Skill。其他 Reference 不复制本文件的接口细节。

## 当前实现与边界

| 项目 | 当前值 |
|---|---|
| provider ID | `autodl` |
| 串行适配器 | `tools/workflow_video.py` |
| 适配器接口版本 | 代码中的 `ADAPTER_VERSION` |
| 串行协议 | `comfy_workflow_v1` |
| 当前模型 | H3；模型与 provider 是两个独立字段 |
| 实例与电源 | `tools/autodl_instance.py` |
| H3 共享媒体工具 | `tools/video.py`，仅供适配器内部调用 |
| TTS | Qwen3-TTS 可复用同一实例电源生命周期，但不是另一种视频 provider |

`workflow_series.py` 不直接导入本适配器，而是通过 `tools/lib/video_providers.py` 精确选择。当前注册表只有 AutoDL 并不意味着可以省略新项目的 provider 确认；未来新增后端不得修改本文件来冒充其能力。

## 无凭证配置与锁定

cloud config 示例：

```json
{
  "schema_version": "1.0",
  "video_provider": "autodl",
  "protocol": "comfy_workflow_v1",
  "base_url": "https://instance.example",
  "workflow_id": "workflow-id",
  "aspect_ratio": "16:9 (Widescreen)",
  "megapixels": 0.4,
  "view_path": "/api/comfy/proxy/view"
}
```

配置不得保存 `token`、`api_key`、`authorization` 或 `password`。`base_url` 必须是 HTTP(S)，`view_path` 必须是以 `/` 开头的路径。实际 `aspect_ratio` 只能是适配器支持的完整枚举；`megapixels` 是有限正数。二者是 AutoDL workflow 的请求字段，不冒充 H3 的通用模型合同。

固定 `串行执行.json` 顶层必须显式写 `video_provider: autodl`，cloud config 必须显式写 `protocol: comfy_workflow_v1`。离线 `preflight` 自动取得适配器版本、SHA-256 和 cloud config SHA-256 并绑定 run-state；缺少 provider 或 protocol 时直接停止，不根据任务文件或目录内容猜测。

```bash
python -I tools/video_run.py --project-root <项目目录> --episode ep_N
python -I tools/video_run.py --project-root <项目目录> --episode ep_N --execute
```

第一条只做离线预检，不联网、不创建任务文件、不修改 manifest。第二条由固定入口把 JSON 中的连续 SEG、operation 和 confirmation ID 填给底层 runner；视频制作不手工拼接 `workflow_series.py` 或 `run-managed` 命令。

## 凭证与本地秘密

环境变量优先；`.env` 查找顺序遵循 `tools/lib/env.py`。凭证只在执行时读取，不写入项目、queue、manifest、任务快照、Prompt、日志或回复，不回显真实值。

- AutoDL 应用实例：`AUTODL_APP_API_TOKEN`，控制台开发者 Token。鉴权头原文发送，不添加 Bearer。
- Zealman workflow 可选鉴权：`H3_WORKFLOW_API_KEY`；未配置时按部署实际无鉴权发送。
- workflow 可选覆盖：`H3_WORKFLOW_ID`、`H3_WORKFLOW_BASE_URL`、`H3_WORKFLOW_ASPECT_RATIO`、`H3_WORKFLOW_MEGAPIXELS`。
- TTS SSH：`AUTODL_SSH_HOST` / `AUTODL_SSH_PORT` / `AUTODL_SSH_USER` / `AUTODL_SSH_PASSWORD`。

跨源或 HTTPS 降级重定向被拒绝，HTTP 错误正文和 Token 不回显。实例列表只输出 UUID、名称、状态、地区、规格等白名单字段，不输出 SSH 密码、Jupyter Token 或快照敏感字段。

## AutoDL 实例与独立电源授权

接口以 [AutoDL 应用实例 API 文档](https://www.autodl.art/docs/app_api/) 为准，固定 HOST 为 `https://www.autodl.art`。`list` 与 `status` 是只读联网请求；`power-on`、`power-off` 和 `run-managed` 默认 dry-run，不联网、不读取 Token、不启动子进程。

真实开机是按小时计费的独立基础设施操作。剧本、图片、音色或视频生成确认均不包含电源授权；真实执行必须同时给出 `--execute` 和与精确实例 UUID 完全一致的确认值。一次授权只覆盖当次实例与生命周期，已结束的 run-managed 不能作为下一次开机凭证。

视频或 TTS 制作只在 `../delegation.md` 的全部准备硬门通过后启动一次 `run-managed`，由它包住电源和完整任务批次。不得先执行真实 `power-on` 再准备固定 JSON 或任务命令；独立电源命令只用于另行授权的排障，不属于正常制作启动链。

```bash
python tools/autodl_instance.py list
python tools/autodl_instance.py status --instance-uuid pro-xxx

python tools/autodl_instance.py power-on --instance-uuid pro-xxx
python tools/autodl_instance.py power-off --instance-uuid pro-xxx

python tools/autodl_instance.py power-on --instance-uuid pro-xxx \
  --execute --confirm-power-on pro-xxx --wait
python tools/autodl_instance.py power-off --instance-uuid pro-xxx \
  --execute --confirm-power-off pro-xxx --wait

python tools/autodl_instance.py run-managed --instance-uuid pro-xxx \
  --execute --confirm-power pro-xxx \
  --health-url https://instance.example/health --health-http-status 200 \
  -- python tools/tts.py --roles-file roles.json
```

`--` 后是无 shell 的子进程命令，监督进程不自行新增任务、重写 Prompt 或扩大范围。同一受管进程内不按 SEG 或 TTS 角色重复开关机；下一新 SEG 的新进程与电源授权按通用 provider 合同重新闭合。`--env-file` 是全局参数，放在子命令之前。

### 电源协议与状态对账

- 列表：`POST /api/v1/adl_dev/dev/instance/pro/list`。
- 状态：优先 query 参数请求 `GET /api/v1/adl_dev/dev/instance/pro/status`；只有服务端明确返回指定参数错误时才按文档回退 JSON Body，不对所有错误盲目换请求形式。
- 开机：`POST .../power_on`，载荷包含 `instance_uuid` 与 `payload=gpu`。文档不支持 API 无卡开机，本工具不伪造该能力。
- 关机：`POST .../power_off`，载荷为 `instance_uuid`。
- 真实 POST 前先查状态：`running`/`stopped` 才是对应动作的安全起点。过渡或未知状态只对账，不重复 POST。
- POST 结果不明时先查状态；只有重新确认原起点，并满足工具退避和连续状态观察条件后才允许重发，不能把丢失响应当成未提交。
- 独立 `--wait` 默认持续到真实 `running` 或 `stopped`；可用 `--timeout <正整数秒>` 设置排障上限。受管运行以 `--power-timeout` 限制开关机排障。
- 明确认证/参数错误停止；瞬时查询失败、限流和服务端错误按受控退避恢复，不做重试轰炸。
- `power_on_accepted` / `power_off_accepted` 都不是完成，最终必须读取真实目标状态。

### 健康门、收尾与退出码

- `power-on --health-url` 默认只要求 HTTP 状态低于 `500`，也可显式传 `--health-http-status`。可用 `--health-json running=true` 或点分路径条件核验响应中的 JSON 标量；HTTP 200 只证明传输成功，不等于业务服务已经就绪。
- `run-managed` 配置健康地址时默认精确要求 HTTP `200`；网关 `404` 不算业务服务就绪。健康请求不发送 AutoDL Token。`--health-interval` 设置固定检查间隔，`--health-timeout` 设置进入健康门后的独立等待上限；若既有电源等待截止更早，仍按较早截止停止。
- 固定视频入口使用 `/api/comfy/status` 并同时要求 `running=true`，直到 Comfy 真正 running 才启动串行子进程。Comfy 健康检查固定每 `10` 秒一次，独立等待上限为 `300` 秒（5 分钟）；实例开关机的 `--power-timeout` 保持原值，不改成 300 秒。`/api/workflow/list` 返回 200 只代表面板可访问，不能替代 Comfy 就绪门；`running=false、starting=true` 时继续等待，不提交视频。
- 实例 `running` 但没有健康检查，只证明实例状态，不冒充 workflow 已就绪。
- run-managed 先只读记录初始电源状态，再进入开机与就绪门。子进程成功、非零、启动失败或被终止时都执行关机并对账到真实 `stopped`。
- 本次从 stopped 启动、但开机或就绪失败时，也先对账再尝试关机，避免已生效 POST 留下计费实例；实例原本 running/starting 且子进程从未启动时，就绪失败不会误关既有实例。
- 已成功进入子命令的受管运行，无论初始状态如何，均按本次 `--confirm-power` 授权在退出后关机。
- 子进程日志写到 stderr，stdout 保留最终生命周期 JSON。结果保存真实 `child_exit_code`、规范化 `process_exit_code`、开机结果和关机结果。
- 子进程通常的非零退出码原样传播；关机失败返回失败，不能把任务退出或 `power_off_accepted` 冒充 stopped。

## Zealman / ComfyUI workflow 提交

协议：

```text
POST {base}/api/workflow/generate
  {workflow_id, input_values:{ref_image_N, ref_video_N, ref_audio_N,
   prompt, seconds, aspect_ratio, megapixels}} -> prompt_id
GET  {base}/api/workflow/result?prompt_id=...
GET  {base}/api/comfy/proxy/history?prompt_id=...
GET  {base}/api/concurrent/assets
GET  {base}/api/images
GET  {base}/output/{subfolder}/{filename}
```

本地图片、视频、音频按模型槽位转为 data URI；HTTP(S) URL 原样透传。实际上传前仍按 `tools/h3.json` 和 Prompt 标记核验模态、数量与时长。`submit`/`run` 每个任务文件最多 POST 一次；任务文件已存在或正式输出已存在时拒绝重复提交。

直接 CLI 保留 `submit`、`poll`、`run`、`status`。`submit --dry-run` 不联网、不创建任务文件；`poll` 是恢复原任务，不是再次生成。

任务文件先以 `submission_pending` 落盘，再执行 POST。响应缺少 `prompt_id` 或请求结果不明时进入 `submission_unknown`，保存现场并停止；不得因没有 ID 就再次 POST。成功响应返回 ID 后才进入 `submitted` 并记录真实 `http_post_count`。

## 原任务恢复与持久化资产找回

### prompt_id 的有效范围

Zealman 的 `prompt_id` 只存在于当前 ComfyUI 进程内存 history。重启、隔日开机或崩溃恢复后，旧 ID 可以失效；这不等于 `/output` 中仍存在的文件被删除，也不等于可以重新生成。

恢复已有任务文件时，`poll` 默认先只读找回持久化结果；随后与新提交任务共用同一个结果轮询循环，默认每 10 秒查询一次，单段等待上限 900 秒。跨进程串行恢复通过统一接口传 `resumed=True`，不另建恢复专用等待循环。

### result 与 history

- result 遇到 HTTP `404|405|501|500` 时回退 history。
- result 返回 `pending=true、results=[]` 是正常的排队或生成状态，继续按间隔查询 result；不得因为 history 尚未出现而判丢。
- result 明确完成/失败时采用其结果；history 只作为兼容与故障回退，不覆盖正常 pending。
- 回退 history 后记录暂时为空时仍在同一个 900 秒上限内继续查询，不再使用 120 秒或恢复任务 0 秒的提前判丢宽限。
- result 与 history 都发生 HTTP 500 时可尝试持久化资产找回，并在剩余轮询时限内继续查询；到达上限仍无结果或唯一持久化证据时停止，不无限等待，也不自动重新生成。

### 持久化证据优先级

1. 当前任务文件已经保存的 `result_url`。
2. `/api/concurrent/assets` 中同时精确匹配 `promptId + workflowId` 的唯一视频。
3. result/history 仍能唯一证明的当前任务结果。

concurrent asset 可使用 `localFile`、`sourceHost`、`sourceHostId`、`originalFile`、`promptId`、`timestamp`、`workflowId`、`url` 等字段，但只有任务身份精确匹配与唯一视频 URL 能授权下载。持久化 URL 必须与任务 `base_url` 同源、位于 `/output/`、具有视频扩展名，拒绝反斜杠和父目录跳转。

`/api/images` 只提供路径、大小、修改时间等目录辅助证据。它可能直接返回顶层数组，HTTP 解析只有显式 `allow_list=True` 才接受该形态。目录中“只有一个视频”、修改时间接近、时长相近或文件名相似都不能独立认领；多个精确资产或多个候选同样停止。

无法唯一恢复时抛出恢复类错误，保留 `phase=submitted` 和原任务文件，记录 `backend_status=STALE_OR_UNAVAILABLE`，不自动改写为已失败、已完成或可重新生成。只有后端明确返回失败才进入失败状态。

### 下载与原子落盘

取得视频 URL 后立即把 `result_url` 保存到任务文件，再下载。下载后检查媒体流、所需音轨与全量解码，通过后才原子改为正式输出。下载或本地校验失败时保留 URL，下一次恢复可直接使用，不依赖已经失效的 history。

```bash
python tools/workflow_video.py poll --task-file seg.task.json --out seg.mp4 \
  --timeout 900 --interval 10 --require-audio
```

恢复只发送 GET。任何需要新 POST 的修复都属于新的生成/返修范围，不能由本恢复流程自动触发。

## H3 workflow 请求补充

- `seconds` 为 H3 允许的 4–15 整数秒；模式、参考数量和时长限制以 `tools/h3.json` 为准。
- `input_values` 由真实 `ref_image_N` / `ref_video_N` / `ref_audio_N`、`prompt`、`seconds`、`aspect_ratio`、`megapixels` 构成。
- Prompt 只能是已保存且通过血缘校验的 H3 成稿；媒体标记必须和真实槽位一致。
- 串行 queue 当前只使用图片与音频，禁止视频参考；这是当前队列合同，不是所有未来 provider 的通用限制。
- dry-run 快照中的 slots 用于核对真实文件、顺序和 SHA-256，不得伪造 `prompt_id` 或 task ID。

## 离线验证

`tests/test_workflow_recovery.py` 使用路由假后端，所有非 GET 请求都会使测试失败。覆盖 provider 选择、执行依赖哈希锁定、历史段原序 `reuse` 的多轮 queue 续跑、历史路径/授权篡改拒绝、串行器解耦、result/history 回退、pending 超过 120 秒继续到成功、10 秒间隔、900 秒上限、保存 URL 优先恢复、精确资产恢复、模糊目录拒绝和下载校验。`tests/test_autodl_health.py` 覆盖 HTTP 200 但 Comfy 尚未 running 时继续等待、JSON 健康条件、固定检查间隔、独立健康时限与敏感正文抑制；`tests/test_video_run.py` 覆盖固定入口的结果轮询 900 秒/10 秒、健康门 10 秒/300 秒及原电源超时。运行：

```bash
python -I tests/test_workflow_recovery.py -v
python -I tests/test_autodl_health.py -v
python -I tests/test_video_run.py -v
```

离线测试通过不证明云端服务可用，不授权开机，也不证明任何真实旧任务已找回。真实恢复仍需在对应电源授权内按本文件执行，并以实际结果证据对账。
