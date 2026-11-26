# 单段视频生成参数与五列分镜确认

本文件定义完整模式视频生成前以及轻量模式返修/重生时的展示格式。确认调用结构与选项只以 `interaction-ask-video-clarification-ref.md` 为准；轻量模式首次生成不重复展示本文件两张表。

## 每个新 SEG 单独编译与确认

完整模式每次只完成**当前一个新 SEG** 的导演底稿、H3 成稿、真实素材、槽位、参数、输出路径和固定 `串行执行.json`，再展示并确认这一段。上一段已经生成、看图、登记并交付后，才能根据其真实尾态编译下一段；不得预编译或预确认整集后续 SEG。

已真实存在且通过哈希复用的 SEG 不计入新生成数量。原任务的轮询恢复、结果下载和技术性补抽真实尾帧沿用原任务与原确认，不新增生成授权，也不得借机改变请求。新增、返修、重生或任何已展示生成参数变化，都重新展示当前段并确认。

### 确认前的硬门

当前 SEG 必须已有完整中文五段式导演底稿、一次真实的宿主 `Skill(skill="h3-prompt-writing", args=<完整交接包>)` 调用、保存后的 H3 英文成稿，以及通过源/成稿哈希和结构检查的 `h3_conversion`。未真实调用、只手写同格式 Prompt、哈希失配或固定输入未齐时，不得展示确认表。

`continuous` 段还必须满足真实尾态门：

- 上一段输出、真实 tail FRM、来源视频/tail 哈希和看图观察均已完成并登记，当前段 `reference_inputs` 指向该真实帧；不得只写 `planned_reference_inputs`、预定路径或“运行时自动生成”。
- 主 Agent 已把真实尾值写入当前段继承表和中文底稿，并在 H3 成稿中核对等价承接；小偏差明确调整承接，大冲突返回最早责任上游，不伪写一致。
- 固定资产和既有复用视频同样真实存在并通过预检。每次实际 POST 前，runner 再核验输入与来源哈希；任一未闭合就停止，不伪造占位图、改写 Prompt 或自动重生。

首段及 `elliptical` 段按其真实新起点与必要输入执行，不虚构上一段 tail。

## 强制展示顺序

除轻量模式首次生成外，每次建立一个新生成任务前，主 Agent 必须在同一条普通文本消息中按顺序展示：

1. 一张且仅一张当前 SEG 参数确认表。
2. 一张且仅一张当前 SEG 五列分镜表。
3. 立即按 `interaction-ask-video-clarification-ref.md` 调用一次标准视频生成确认。

两张表缺一不可。禁止使用散文、旧规划表、内部 Prompt 文件或上一段的表格代替。确认前不得调用任何视频生成或编辑工具。

## 单段范围边界

- `batch_start_segment_index == batch_end_segment_index`，数量固定为 `1`；`planned_video_count`、`segment_durations` 项数和五列表行数也都为 `1`。
- 两张表只包含本次新生成 SEG。复用或恢复段单独在“视觉与连续性”说明，不伪计入新数量。
- 分段时长和总时长都等于当前 SEG 的真实时长。
- 固定 `串行执行.json` 必须绑定确认：`execution_mode: serial_real_tail_chain`、`run_plan_file` 和 `run_plan_sha256`。完整 queue 字段按 `delegation.md` 填写；其中 provider 绑定相关字段只显式填写 `video_provider` 与 cloud config 路径，预检自动绑定协议、适配器版本/SHA-256 和 cloud config SHA-256。缺少 provider 或无法形成这些绑定时直接停止。当前新 SEG 的 Prompt、固定素材、槽位、模型、provider、时长、输出或 JSON 字节变化都需要重新预检和确认；纯恢复不得改变原请求。
- 当前段运行退出后，主 Agent 按 `delegation.md` 看图、对账、登记和交付。下一段是新的生成任务，必须重新展示两张表并确认。

## 参数确认表

固定为两列 Markdown 表格 `参数｜本批次确认值`，至少逐行包含：

| 参数 | 本批次确认值 |
|---|---|
| 任务类型 | 完整模式统一写“长视频生成任务”；轻量返修或重生写“短视频生成任务”或“视频编辑任务” |
| 交付格式 | 当前 SEG 的文件格式；运行退出后核对、登记并交付 |
| 数量 | `1` |
| 分段时长 | `SEGxxx：N秒` |
| 总时长 | 等于当前 SEG 时长 |
| 画幅与分辨率 | 当前 SEG 真实参数 |
| 视频模型 | H3 |
| 视频生成后端 | 已选注册 provider 的自然名称；当前注册项为 AutoDL。有多个兼容后端时展示已确认选择，不由执行器替换 |
| 视觉与连续性 | 当前 SEG 共同视觉方向、角色或产品锁定特征、群众/场景/道具事实及与上一真实尾态的连续关系 |
| 声音与字幕 | 当前 SEG 配音、完整台词或旁白范围、音乐、音效和字幕策略 |
| 参考素材 | 当前 SEG 实际使用的首尾帧、关键帧、角色、群众、场景、道具、音频或待编辑视频；`continuous` 另明确上一段真实 tail FRM，首段或 elliptical 按实际新起点说明 |
| 工具限制与消耗 | 模型/工具限制、本次一个视频和高消耗提示 |

“数量”必须等于五列分镜表行数、`planned_video_count`、`segment_durations` 项数及确认覆盖的 SEG 数，即固定为 `1`。模型、视频生成后端、画幅、分辨率、素材、台词、字幕和声音必须来自当前锁定串行执行配置。

## 当前 SEG 五列分镜表

固定列顺序如下，恰好一行：

| 片段与时长 | 画面内容 | 主体动作 | 声音与完整台词 | 运镜与素材 |
|---|---|---|---|---|
| `SEGxxx｜N秒` | 本段起始局势、关键推进和可见结果 | 主体策略、对手或环境反馈、动作落点与尾态 | 本段全部对白、旁白、画外音、内心独白及必要声响；没有则明确“无” | 主要镜头推进与切换、前后承接方式及本段真实输入素材 |

逐行要求：

- SEG ID 和时长必须匹配 `storyboard_ep_N.json`、`segment_durations` 和实际请求。
- 本行是一个视频片段的简洁完整分镜，不是只有主题词的摘要。画面内容至少交代起点、推进和结果；主体动作至少交代行动、反馈和段尾状态。只能压缩当前 SEG 已确认的详细分镜及上一段真实尾态，不得另写、借用其他段剧情或漏掉本段结果。
- 声音与完整台词必须列全该 SEG 的 `speech_lines[].spoken_text` 并标明声音类型；禁止只写“有对白”“同剧本”或摘要。
- 运镜与素材必须说明主要观察方式、镜头切换或连续运动、片段承接方式，以及当前 SEG 实际使用的图片、视频、音频职责；禁止把待生成、未批准或其他段素材写成已使用输入。`continuous` 明确所采用的上一段真实 tail FRM，不得写成未来依赖。

## 记录与校验

实际展示原文完整保存到 `generation_confirmations[].final_parameters_text`。结构化同步保存：

- `confirmation_id`、`attempt`、`supersedes_confirmation_ids`
- 相同的 `batch_start_segment_index`、`batch_end_segment_index`
- `planned_video_count: 1`、仅一项的 `segment_durations`
- `video_provider`、`video_provider_adapter_version`、`video_provider_adapter_sha256`、`cloud_config_sha256`
- `displayed_parameter_table`、仅一行的 `displayed_storyboard_rows`
- 串行运行另存 `execution_mode: serial_real_tail_chain`、项目相对 `run_plan_file` 和 `run_plan_sha256`

字段结构读取 `manifests.md`。首次确认写 `attempt: 1` 和空的 `supersedes_confirmation_ids`；返修/重生保留历史记录，递增 attempt 并列出同一 SEG 的旧确认 ID。

确认后的单次执行、退出看图、登记和交付统一按 `delegation.md` 执行。

调用前运行视频阶段检查。范围不是同一 SEG、数量不为一、逐段时长错误、五列表不是一行、台词缺失、continuous 真实 tail 未登记、provider 未注册或与串行执行配置不一致、适配器/cloud config 绑定缺失或失配、串行确认未绑定队列/哈希、返修未建立替代链时必须阻断。所有确认和执行记录都必须符合当前字段合同，缺失时停止，不自动补写。
