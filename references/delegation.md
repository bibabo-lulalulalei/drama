# 执行委派 Ref

本地宿主的可用执行主体以 `local-runtime.md` 为准。主 Agent 负责导演链路、运行前授权、每次进程退出后的看图对账、登记和交付。固定执行器每次运行最多处理一个新 `generate`，可以同时执行合法的 `recover|reuse`；没有 subagent 时，主 Agent 启动并等待同一个固定脚本。

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

## 固定脚本直接读取并启动

```bash
python -I tools/video_run.py --project-root <项目目录> --episode ep_N
python -I tools/video_run.py --project-root <项目目录> --episode ep_N --execute
```

第一条只读固定 JSON 并做离线预检。第二条再次预检后，直接把 JSON 字段填入现有两个底层工具：

```text
autodl_instance.py run-managed
  -> workflow_series.py run
     -> JSON 中 generate|recover 段的授权与确认参数
```

`run-managed`、脚本路径和参数顺序由 `video_run.py` 固定写入，执行者不得临时另写 Python/Bash 包装命令。固定日志为同目录 `串行运行.log`，追加保存；真实任务防重、执行锁和 run-state 仍由现有 runner 负责。

真实 `--execute` 前只需闭合正常制作条件：上游阶段和当前唯一新 SEG 已确认，JSON 已填全，离线预检通过，凭证可用，并已取得本次精确实例电源授权。不得先开机再补 JSON 或生成参数。电源和当次 queue 由同一次 `run-managed` 生命周期拥有，结束或失败后自动关机并对账；不拆成两个制作脚本，不重复开关机。

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

## 其他阶段委派边界

| 阶段 | 主执行责任 | 委派规则 |
|---|---|---|
| planning / script / storyboard | main_agent | 禁止委派创作决策 |
| assets / keyframes | main_agent | 图片工具可按锁定 Prompt 与输出委派 |
| video | main_agent_director + serial_executor | 必须委派固定视频入口；每次最多一个新 SEG，同一集不能并行多个队列 |
| final | main_agent_director + subagent_executor | 实际拼接、裁剪、混音、mux、字幕烧录按 `delivery.md` 的锁定媒体操作委派 |

完整制作按 `current_episode` 逐集闭环，不授权执行器进入其他阶段或下一集。

## 异常边界

runner 可按原 provider 对锁定任务进行状态查询、轮询、下载和恢复，不得重写创作输入或切换后端。提交结果不明且没有可用任务标识时先对账服务端原任务；无法唯一匹配就停止，禁止盲目新 POST。缺真实尾帧、哈希不符、输入失效、媒体不可解码或不可恢复后端错误同样保留现场并停止。

只有主 Agent 能在进程退出后修复固定 JSON 或向用户报告。修复会新增、重发或改变生成请求时必须重新确认；只恢复既有任务时不得改变原请求，也不新增生成确认。失败或未闭合段不得作为下一段的真实尾态来源。

## 每次进程退出后的主 Agent 对账

1. 对照固定 JSON、run-state、任务文件和真实媒体检查退出状态、各段输出、任务 ID、尾帧及来源哈希。
2. 只对真实存在且媒体检查通过的输出登记 `video_manifest` 与 FRM/SEAM；失败和未开始段不补造事实。主 Agent 必须实际查看当前新 SEG 的 `start / scene / tail`，并将其 `start` 与上一段真实 `tail` 并排核对，不能只凭 runner 技术回执认定承接正确。
3. 按真实结果交付当前生成或恢复片段，汇总成功、复用、失败和未开始项；未通过客观交付检查的文件不得宣布交付。整集片段齐全后再执行 `video.md` 规定的阶段准出检查与确认。
4. 下一段只能在当前段看图、登记和交付后编译。真实尾值成为下一段 0 秒基准；小偏差在不改写已发生剧情和用户锁定项的前提下明确承接，身份、因果、轴线或关键道具等大冲突返回最早责任上游修订并履行变更确认。不得伪写一致或自动重生。
5. 内容问题只内部记录并用于下一段承接或用户主动返修定位，不自动重生；进入拼接或新返修仍走各自确认。
