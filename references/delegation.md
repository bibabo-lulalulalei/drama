# 执行委派 Ref

本地宿主的可用执行主体以 `local-runtime.md` 为准。主 Agent 负责导演链路、运行前授权、每次进程退出后的看图对账、登记和交付。固定执行器每次运行最多处理一个新 `generate`，可以同时执行合法的 `recover|reuse`；没有 subagent 时，主 Agent 启动并等待同一个固定脚本。

## 本 Ref 关键要求

- 规划、剧本、资产体系、分镜、视频参数确认、继续下一新 SEG 生成确认、进入拼接确认、两层 Prompt 与请求快照定稿、所属环境画布写入/回读、用户交付和最终确认必须由主 Agent 按 Skill 完成；主 Agent 不得按自己的偏好或临时判断覆盖 Skill 策略。
- 凡实际调用视频生成/编辑工具，必须使用读取固定 `串行执行.json` 的同一受控执行器；本地有 subagent 时由其启动并等待固定入口，没有时主 Agent 启动并等待同一进程。每次运行最多处理一个新 `generate`，同一集、同一新 SEG 的串行依赖不变；不得绕过固定脚本直接提交视频请求。
- 凡成片阶段会产出或修改媒体文件的拼接、裁剪、混音、mux、字幕烧录等媒体变更工具调用，必须按 `delivery.md` 委派给 subagent 执行；主 Agent 保留剪辑策略、字幕策略、基础可交付检查、交付和确认责任，不设置最终内容质检硬门。
- 图片生成、修图和关键帧可由主 Agent 执行；若委派，也只能让 subagent 按锁定 Prompt 与白名单路径执行图片工具，不得让 subagent 做创作决策。
- subagent 和执行器不能改上游、换模型或 provider、改 Prompt、扩写分镜、再次委派、调用澄清/确认工具、写 Canvas/Workspace、调用交付工具或面向用户发问。
- 完整模式资产、关键帧和视频片段阶段的每个图片或视频产物生成后，主 Agent 必须按 `SKILL.md` 与 `local-runtime.md` 完成当前环境用户交付；只有原平台非 Mobile 分支再完成 `present_files`、Canvas 写入和 CLI get 回读。串行视频在 runner 退出并由主 Agent 看图、对账和登记后交付当前段。轻量模式字幕关闭时交付原始生成视频；字幕开启时原始无字幕视频只作为内部烧录源。成片阶段的裁剪片、拼接中间件、字幕测试样片和内部母版只保存登记；主 Agent 只交付字幕策略对应的唯一最终视频版本。

## 视频只有一个输入 JSON

每集只使用一份固定文件：

```text
episodes/ep_N/04_视频片段/串行执行.json
```

主 Agent 复制 `tools/video_run.example.json` 到该位置并填写。它是当次串行 queue，也是固定脚本的全部启动参数来源；不再另建 plan、build 用 queue、执行包或启动包装 JSON。每轮只填写已经编译并确认的当前新 SEG，以及确需同次恢复或复用的既有段；上一段看图、登记和交付前，不预编译或预确认下一段。每次运行前按当前确认更新这一份文件，启动后不得修改；确认记录仍以该文件的 SHA-256 绑定实际运行版本。

顶层只填：

- `video_provider`、`cloud_config`、`run_state_file`。
- `power.instance_uuid` 和可选电源超时。
- 可选轮询超时与间隔。
- 有序 `segments`。

每段只填执行链实际读取的字段：

- `segment_id`、`duration_s`、`operation`、`confirmation_id`。
- 实际提交的 H3 成稿 `prompt_file`。
- 有序 `images`、`audio`，以及 `output_file`、`task_file`、`tail_file`。
- 图片项只写 `file` 或 `previous_tail_of`；资产身份、导演底稿、转换血缘和 FRM 编号已在 manifest 登记，不在本 JSON 复制。

`operation` 固定为：

- `generate`：授权一次新生成，填写本段 `confirmation_id`；同一 JSON 最多一项。
- `recover`：已有任务文件只恢复，不重复 POST，仍填写原确认 ID。
- `reuse`：复用真实输出和尾帧，不进入新生成参数，也不需要第二个复用布尔字段。

新 `generate` 的固定图片、音频和 `continuous` 上一段真实 tail 必须在确认前已经存在并登记。不得用未来 tail、预定路径或尚未完成恢复的上段先编译并确认新 Prompt；需要先恢复上一段时，本轮只恢复，退出复核后再建立下一段新任务。适配器版本、适配器/cloud config 哈希、Prompt 哈希和媒体事实由现有工具计算并写入预检、任务或 run-state，不在 JSON 重复抄写。

同一 run-state 可以从上一份已冻结 queue 推进到本轮新 queue，但只允许向前续跑：历史 SEG 必须按原顺序构成新 queue 前缀，全部改为 `reuse`，保持原输出和 tail 路径，且逐段重新核验输出、tail 及来源视频 SHA-256；历史段尚未完成、路径或字节变化、被删除、调序或重新写成 `generate|recover` 时拒绝执行。核验通过后，run-state 把当前 `queue_sha256` 更新为本轮冻结值，并把旧值追加到 `superseded_queue_sha256`；历史段证据继续保留，新 SEG 的确认仍只绑定本轮 queue。不得通过手改 run-state、删除历史记录或另换状态文件绕过这些检查。

## 固定脚本直接读取并启动

```bash
python -I tools/video_run.py --project-root <项目目录> --episode ep_N
python -I tools/video_run.py --project-root <项目目录> --episode ep_N --execute
```

第一条只读固定 JSON 并做离线预检，返回 `run_plan_file/run_plan_sha256`、`video_provider`、`video_provider_adapter_version/video_provider_adapter_sha256` 和 `cloud_config_sha256`；主 Agent 必须把这些实际返回值写入当前 SEG 的展示与确认记录，不手工猜算。此阶段不要求确认记录预先存在，避免“先确认才能取得确认参数”的循环。第二条用执行前确认门再次预检：最新逐 SEG 确认必须匹配当前 queue 实际字节、完整 provider 绑定和当前 SEG，再把 JSON 字段填入现有两个底层工具。需要显式指定非默认凭证文件时，在同一固定入口追加 `--env-file <路径>`；该参数会传给受管监督层和串行 runner，不另建包装命令。调用链固定为：

```text
autodl_instance.py run-managed
  -> workflow_series.py run
     -> JSON 中 generate|recover 段的授权与确认参数
```

`run-managed`、脚本路径和参数顺序由 `video_run.py` 固定写入，执行者不得临时另写 Python/Bash 包装命令。固定日志为同目录 `串行运行.log`，追加保存；真实任务防重、执行锁和 run-state 仍由现有 runner 负责。

真实 `--execute` 前只需闭合正常制作条件：上游阶段和当前唯一新 SEG 已确认，JSON 已填全，离线预检通过，凭证可用，并已取得本次精确实例电源授权。不得先开机再补 JSON 或生成参数。电源和当次 queue 由同一次 `run-managed` 生命周期拥有，结束或失败后自动关机并对账；不拆成两个制作脚本，同一受管进程内不重复开关机。下一新 SEG 的新进程重新取得电源授权。

## 单次运行与段间反馈

```text
当前一个新 SEG 的真实输入、两层 Prompt、预检与确认
-> submit|resume -> poll -> download -> media check
-> 按预定 tail_file 抽取并保存真实尾帧
-> 完成或不可恢复停止 -> 电源收尾
-> 主 Agent 看图、对账、登记并交付当前段
-> 根据真实尾态编译、预检并确认下一个新 SEG
```

执行器启动后不得改 Prompt、素材、槽位、路径或 JSON，也不得自行加入下一项新生成。已有任务标识的轮询恢复、结果下载/校验和真实尾帧补抽不新增生成授权；下一个新 SEG 必须回到主 Agent 重新编译、展示和确认。

执行器只能写 JSON 指定的任务、视频、尾帧、run-state 以及固定日志，不得修改原始素材、Prompt、转换记录或确认记录，不得再委派、切换模型/provider、自动重生或拼接成片。

## 执行边界

| 阶段 | 主执行责任 | 委派规则 | 边界 |
|---|---|---|---|
| planning | main_agent | 禁止 | 方向、参数、模式、风险和项目级执行确认由主 Agent 决定 |
| script | main_agent | 禁止 | 项目级与分集剧情不得拆给不同 Agent 创作 |
| assets | main_agent | 图片工具可选委派 | 主 Agent 只建立当前集实际需要且项目内无 approved 可复用版本的人物、群众、场景、道具、音色、风格和状态资产；图片委派只执行锁定 Prompt 与指定输出 |
| storyboard | main_agent | 禁止 | 镜头语言、片段切分和连续性必须保持全局一致 |
| keyframes | main_agent | 图片工具可选委派且最多一个 subagent | 主 Agent 先完成 KF 清单、职责和 Prompt；subagent 只生成指定图片并保存到白名单路径 |
| video | main_agent_director + serial_executor | 必须使用固定视频入口；有 subagent 时委派启动，没有时主 Agent 启动同一进程 | 主 Agent 完成两层 Prompt、生成参数展示、确认和固定 `串行执行.json`；每次最多一个新 SEG，同一集不能并行多个队列 |
| final | main_agent_director + subagent_executor | 必须委派媒体变更工具调用 | 主 Agent 按 Skill 决定片段顺序、剪切点、声音/字幕策略和基础交付检查；subagent 只执行拼接、裁剪、混音、mux、字幕烧录等锁定媒体操作 |

完整制作必须由主 Agent 按 `current_episode` 逐集闭环，不得把不同集并行推进到不同 subagent。`assigned_episodes` 在生产执行包中只能包含当前集；它不授权 subagent 进入其他阶段，也不授权在当前集成片确认前处理下一集。

## 委派与固定执行前置条件

遇到以下执行动作时使用对应执行边界：

1. 实际提交视频生成或编辑时，必须读取固定 `串行执行.json` 并启动同一受控执行器；有 subagent 时委派其启动并等待，没有时主 Agent 启动并等待，不得绕过固定脚本直调。
2. 实际执行成片拼接、裁剪、混音、mux、字幕烧录或其他会产出/修改最终媒体文件的媒体工具时，必须委派 subagent。
3. 主 Agent 明确决定把图片生成、修图或关键帧工具调用外包给 subagent 时，按图片交接包执行；关键帧最多委派一个 subagent。

委派或固定执行前必须同时满足：

1. 上游阶段和本次所需参数已经由主 Agent 确认或锁定。
2. 视频执行已按 `interaction-ask-video-clarification-ref.md` 完成本次标准视频生成确认；轻量首次生成复用规划页 `generate`。完整模式的成片执行还必须由主 Agent 按 `control-contracts.md` 取得进入成片拼接确认，轻量模式不要求拼接确认。
3. 主 Agent 已保存本次最终 Prompt、请求快照、输入媒体清单、模型、provider、时长、比例、字幕策略和输出白名单；视频以固定 queue 及 manifest 中已登记的真实快照为准。
4. 每个执行者能读取完整项目上下文和自己范围内的全部上游文件。
5. 交接包逐文件列明允许新增或覆盖的输出；未列出的文件一律不得写入。固定视频 queue 已逐项指定任务、视频、尾帧和 run-state 路径；日志固定写同目录 `串行运行.log`，不在交接包中另造一组输出路径。

任一前置条件不满足时，必须回到对应上游由主 Agent 补齐或重新确认；不得绕过固定视频入口或成片委派边界。

所有用户可见图片与视频媒体均按 `current_episode` 和集内稳定顺序串行执行，不得同时启动多个媒体生成执行者。视频必须按 `episode_segment_index` 串行：前一个 SEG 返回、保存、登记、交付并抽取下一段所需真实 tail FRM 后，才能编译和下发下一个新 SEG；不得因判断“没有跨集依赖”而并行。observed SEAM 只能在相邻两段都生成后记录。后续集首段还必须先验收上一集真实尾帧、场景锚点帧、必要角色状态帧和必要道具状态帧，并把对应 `EPSEAMxxx` 更新为 `verified`。

## 交接包

每个实际委派的 subagent 必须收到一个结构化交接包，至少包含：

```json
{
  "subagent_id": "",
  "scope_stage": "image_execution|keyframes|video_execution|final_media_execution",
  "assigned_episodes": ["ep_1"],
  "skill_name": "drama",
  "reference_paths": [],
  "upstream_artifacts": [],
  "upstream_revisions": [
    {"path": "01_剧本/剧本_全剧完整剧本.md", "revision": 1}
  ],
  "prepared_request_snapshot_files": [],
  "prepared_prompt_files": [],
  "allowed_output_paths": [],
  "produced_outputs": [],
  "hard_constraints": [],
  "acceptance_criteria": [],
  "check_commands": [],
  "allow_redelegation": false,
  "allow_upstream_edits": false,
  "allow_user_delivery": false,
  "allow_canvas_or_workspace_write": false,
  "allow_confirmation_tools": false
}
```

固定视频只有当前集 `串行执行.json` 这一份执行参数。`video_execution` 交接包引用该 queue、已登记请求快照、H3 成稿和既有 run-state，不复制或另建第二份视频执行包、plan 或启动包装 JSON；主 Agent 直接启动固定进程的回退不虚构 subagent 交接包。

### 通用必备内容

- `skill_name` 必须写当前已加载 Skill 名称 `drama`；Reference 使用 Skill 内相对路径，不写机器绑定路径。
- `reference_paths` 图片或关键帧执行至少包含 `references/control-contracts.md`、`references/assets.md`、`references/keyframes.md`、`references/manifests.md`；视频执行至少包含 `references/control-contracts.md`、`references/video-batch-confirmation.md`、`references/interaction-ask-video-clarification-ref.md`、`references/video.md`、`references/storyboard.md`、`references/keyframes.md`、`references/assets.md`、`references/manifests.md`、`references/video-provider.md` 与所选 provider 文档；成片媒体执行至少包含 `references/control-contracts.md`、`references/delivery.md`、`references/manifests.md`、`references/local-runtime.md`。
- `upstream_artifacts` 使用项目内相对路径或宿主可访问的资源引用，必须包含本次执行真正依赖的全局剧本包、项目数据卡、共享资产注册表、分集创作说明、分集完整剧本、分镜、已确认 KF、已确认 SEG 或剪辑策略；轻量模式只列真实存在且被确认的上游，不伪造完整模式文件。
- `upstream_revisions` 记录关键上游资源的路径和当前 revision；每次下发前都必须重新核对当前锁定 revision。
- 视频执行必须包含本次确认覆盖的固定 queue、已登记请求快照文件和最终 H3 Prompt 文件。执行者不得自行创建、改写、扩写或压缩请求快照与 Prompt；纯 `recover|reuse` 沿用原任务和原确认。
- 成片媒体执行必须包含采用片段清单、片段顺序、有效切出/切入点、声音桥、字幕开关、输出版本和允许调用的媒体能力；subagent 不得决定剪辑策略或字幕文本，不得做最终内容质检判断。
- `allowed_output_paths` 必须在委派前逐项列出 subagent 可新增或覆盖的项目内相对路径或宿主资源引用，不得只给目录。`produced_outputs` 在收回时填写实际写入文件或资源，必须是 `allowed_output_paths` 的子集。
- `hard_constraints` 必须完整复制主 Skill 的执行约束，至少逐项包含：`只允许执行当前单一执行包`、`不得再次委派`、`不得修改已确认上游`、`不得切换模型或 provider`、`不得调用澄清或确认工具`、`不得写 Canvas/Workspace`、`不得直接向用户交付`、`不得重写 Prompt 或请求快照`、`必须读取完整上游文件`、`完成后返回真实输出路径、工具原始可渲染资源和工具结果`。
- `acceptance_criteria` 必须列出当前执行包产物、基础可打开/可播放要求和客观阻断项；不得把审美、口型、连续性、接缝或剧情判断写成阻断交付的最终质检门。
- `check_commands` 逐项列出收回后要执行的真实只读探测、媒体检查和阶段 lint 命令；不得在交接包中预写“已通过”，实际结果由主 Agent 收回后登记。
- 五个 `allow_*` 字段必须全部为 `false`。

任一执行者报告输入缺失、版本不一致、schema 不符或约束冲突时，当前批次停止并由主 Agent 修复交接包。不得同时启动多个媒体生成执行者。

## 主 Agent 收口

subagent 返回后，主 Agent 必须：

1. 对照交接包逐项检查实际输出路径、数量、版本和状态；任何未列入 `allowed_output_paths` 的新增或修改文件都视为越权。
2. 检查 subagent 未修改任何上游、Prompt、请求快照、确认记录、Workspace/Canvas 或用户交付记录。
3. 检查串行结果持续使用同一已确认项目事实、资产版本、模型与 provider 参数、字幕策略和输出命名。
4. 亲自完成可打开、可播放、必要媒体探测和阶段 lint；FRM/SEAM 或内容问题只作为内部记录，不阻断已生成视频或成片交付，也不授权自动重生。
5. 按 `SKILL.md` 的交付路由立即向用户展示产物；只有原平台非 Mobile 分支由主 Agent 使用当前最终交付版本完成 `present_files`、Canvas 写入和 CLI get 回读，本地分支按 `local-runtime.md` 交付真实文件。未发生媒体处理时，当前最终交付版本就是 subagent 返回的原始可渲染资源。
6. 继续生成或调整视频时，主 Agent 直接按 `interaction-ask-video-clarification-ref.md` 重新展示完整参数并调用标准视频生成确认；进入成片拼接时按 `control-contracts.md` 调用阶段迁移确认。两者不得互相替代。

固定视频进程退出后还须执行下文“每次进程退出后的主 Agent 对账”；该节是视频 queue、真实 tail 和 run-state 的专项补充，不替代上述通用收口。

## 异常边界

runner 可按原 provider 对锁定任务进行状态查询、轮询、下载和恢复，不得重写创作输入或切换后端。提交结果不明且没有可用任务标识时先对账服务端原任务；无法唯一匹配就停止，禁止盲目新 POST。缺真实尾帧、哈希不符、输入失效、媒体不可解码或不可恢复后端错误同样保留现场并停止。

只有主 Agent 能在进程退出后修复固定 JSON 或向用户报告。修复会新增、重发或改变生成请求时必须重新确认；只恢复既有任务时不得改变原请求，也不新增生成确认。失败或未闭合段不得作为下一段的真实尾态来源。

## 每次进程退出后的主 Agent 对账

1. 对照固定 JSON、run-state、任务文件和真实媒体检查退出状态、各段输出、任务 ID、尾帧及来源哈希。
2. 只对真实存在且媒体检查通过的输出登记 `video_manifest` 与 FRM/SEAM；失败和未开始段不补造事实。主 Agent 必须实际查看当前新 SEG 的 `start / scene / tail`，并将其 `start` 与上一段真实 `tail` 并排核对，不能只凭 runner 技术回执认定承接正确。
3. 按真实结果交付当前生成或恢复片段，汇总成功、复用、失败和未开始项；未通过客观交付检查的文件不得宣布交付。整集片段齐全后再执行 `video.md` 规定的阶段准出检查与确认。
4. 下一段只能在当前段看图、登记和交付后编译。真实尾值成为下一段 0 秒基准；小偏差在不改写已发生剧情和用户锁定项的前提下明确承接，身份、因果、轴线或关键道具等大冲突返回最早责任上游修订并履行变更确认。不得伪写一致或自动重生。
5. 内容问题只内部记录并用于下一段承接或用户主动返修定位，不自动重生；进入拼接或新返修仍走各自确认。
