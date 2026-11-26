# 成片、字幕与交付 Ref

本地工具执行机制以 `local-runtime.md` 为准：使用同步 `tools/media.py` 和宿主文件交付能力，不要求远端异步 task、Canvas 或 `present_files`。本地无 ASR 时按实际音轨试听对齐字幕，不伪造 ASR 或工具结果；其余成片与字幕质量要求仍适用。

> 本文件统一负责成片拼接、最终音轨、字幕文本、ASR 对齐、SRT、字幕烧录、基础可交付检查和正式交付。工具名、参数、异步生命周期与结果字段以调用时宿主实际暴露的 mediakit 能力与 schema 为准。

## 第一部分：成片拼接、最终音轨与交付

本部分负责成片拼接策略、最终音轨策略、基础可交付检查和交付；字幕文本、ASR、SRT、烧录参数与字幕处理读取本文件第二部分。实际拼接、裁剪、混音、mux、字幕烧录等会产出或修改媒体文件的工具调用必须按 `delegation.md` 委派执行，主 Agent 负责按 Skill 锁定执行包、收口、基础可交付检查和交付。

### 权威引用

- accepted SEG、FRM、verified seam 和剪切点：`video.md`。
- ASR、SRT、基础可交付检查命令、字幕参数和烧录处理：本文件第二部分。
- mediakit 工具名、参数、异步任务和结果字段：调用前读取宿主实际能力与 schema，不依赖本 Skill 中不存在的静态工具说明。
- 成片路径、命名和 `delivery_manifest_ep_N.json` schema：`manifests.md`。
- 重试预算、缺陷编号和返回层级：`troubleshooting.md`。
- 跨阶段确认、版本失效和交付原则：`control-contracts.md`。
- 进入成片拼接的状态迁移、选项和授权边界：`control-contracts.md`。

### 目标与边界

把全部已确认片段按绝对时间轴和 best available cut 拼成无字幕母版，保留可用原生人声，完成最终混音、适用的字幕链路、基础可交付检查和正式交付。每集只交付一个最终视频版本：字幕关闭时交付无字幕成片；用户明确开启字幕时，以无字幕母版为内部烧录源，只交付字幕版。若片段或成片画面存在字幕、随机文字、水印或平台 UI 残留，先用宿主非视频生成类字幕/文字擦除能力处理并完成基础可交付检查。

本阶段不得改写剧情、替换镜头、重生角色、修改台词或改变画幅。内容、审美、口型、连续性或接缝问题只记录为用户主动修改时的线索，不作为最终交付前质检硬门；拼接、混音、字幕、编码和平台导出这类客观交付问题留在本阶段处理。

完整模式以已批准 VOICE 音色资产为声音身份标准：不传音频时使用该资产的固定 `voice_anchor`，支持音频输入时传入批准音频。轻量模式没有独立音色资产阶段，可以只用已确认的 `voice_anchor`；只有实际存在且已确认可用的既有/用户音频时才传入，不追加音色生成。已生成视频中的原生人声默认保留，不因最终阶段观察到静音、漏句、错人、声线漂移、类型或口型职责错误而自动返回视频阶段；这些问题只记录为用户主动修改时的线索。

### 输入门禁

必须具备：

- 已确认的片段顺序、绝对时间轴、视频文件和 `video_manifest_ep_N.json`。
- 完整模式每个采用 SEG 已真实生成、保存、登记并完成用户可见交付；轻量模式只要求唯一生成视频已保存并登记，不先执行片段交付。
- 完整模式下，主 Agent 已按 `control-contracts.md` 取得 `option_id=proceed_assembly`；视频生成确认或普通聊天肯定不能替代。轻量模式只有一条最终视频，不执行拼接，因此不要求该确认。
- 完整模式需要 `continuity_ep_N.json` 和相邻片段的可用 seam、切出点、切入点、切法及声音桥；缺失时使用 best available cut 并记录原因，不阻断最终交付。轻量模式只有一个最终视频，不要求连续性文件或接缝记录。
- 完整模式需要当前项目数据卡、共享资产登记和跨集一致性结论；轻量模式不要求这些完整模式上游文件。
- 已确认 `drama_plan.delivery_settings` 中的字幕开关、片头片尾、BGM、`audio_policy` 和交付范围；任一项缺失时返回规划阶段补齐，不得在成片阶段临时决定。只有 `audio_policy` 已明确给出目标响度时才按该值锁定；未给出时保留可用原生响度，只处理片段间明显响度突变，不在成片阶段临时发明 LUFS 数值。

字幕开启时，SRT、实际采用路径的 ASR 原始信封或人工试听对齐证据、烧录参数和字幕版必须在最终音轨锁定后按本文件第二部分生成，不得作为进入本阶段的前置产物；字幕关闭时跳过这些字幕专属产物。

缺片段、错序、未确认版本、损坏文件或时间轴重叠时不得进入成片。未验证接缝、计划人声偏差、口型或连续性问题不阻断成片，只记录为用户主动修改时的线索。

### 拼接与最终音轨

1. 按片段编号和绝对时间顺序拼接，不得调序、遗漏或重复。
2. 优先使用 `video.md` 已记录的有效切出/切入点；缺少记录时使用 best available cut 并记录原因。
3. 各片段媒体参数不一致时，先统一分辨率、画幅、帧率、编码和色彩空间。
4. 保留已生成的原生人声；环境声、拟音和 BGM 分轨处理，人声保持前景，避免片段间响度突变。
5. 声音桥按 verified seam 执行，不得用声音掩盖身份、动作、构图或光位错误。
6. 只处理响度、混音、mux 等客观交付问题；人声类型、主体、文本、顺序、口型职责等内容问题只内部记录。
7. 完成全部声音处理后锁定“最终音轨 vNN”；任何后续音频修改都会使 ASR、SRT 和字幕烧录产物失效。

只有用户明确提出修改并重新确认，才允许使用已批准 VOICE 音频做局部缺失人声修复；不得在最终阶段自动整段替换原生人声。

### 成片执行顺序

以下编号流程用于完整模式。轻量模式直接把唯一生成视频作为无字幕成片：字幕关闭时只做基础可交付检查并交付；字幕开启时把它作为内部烧录源，完成字幕链后只检查并交付字幕版。轻量模式不执行片段拼接、接缝读取或拼接确认。

1. 回读采用片段、verified seam、状态和版本。
2. 主 Agent 把已取得的拼接确认按 `manifests.md` 写入 `delivery_manifest_ep_N.json.assembly_confirmation`，再锁定片段顺序、有效切出/切入点、声音桥、已确认 `audio_policy`、字幕开关、输出版本和允许调用的当前媒体链能力；仅当 `audio_policy` 明确给出目标响度时才把该数值写入执行包。随后按 `delegation.md` 下发 `final_media_execution` 执行包。
3. subagent 使用宿主实际暴露的 mediakit 编辑能力（本地为 `local-runtime.md` 映射的 `tools/media.py`）拼接无字幕母版；存在独立音轨时使用当前媒体链实际支持的混音与音视频封装能力，不能把视频拼接冒充混音。subagent 只写白名单输出并返回真实工具结果，不决定剪辑策略、不交付用户、不写画布。
4. 主 Agent 收回后使用当前媒体链探测母版，确认有效视频流、音轨和媒体参数：原平台使用 `byted-mediakit-video`，本地使用 `python tools/media.py probe <mp4> [--json]` 并保存同步结果。
5. 锁定最终音轨后，执行本文件第二部分：
   - 字幕关闭：只做无字幕母版基础可交付检查。
   - 字幕开启：按宿主能力取得 ASR 或人工试听对齐证据，再执行对齐、SRT、无字幕母版基础可交付检查、烧录和字幕版基础可交付检查。
6. 若本文件第二部分需要字幕烧录或其他媒体变更工具，主 Agent 继续用锁定执行包委派 subagent 执行实际媒体变更，回收后只做基础可交付检查。
7. 不做阻断式最终内容质检；如需内部记录，可快速记录文件可播放、总时长、画幅和明显客观导出异常。
8. 更新 `delivery_manifest_ep_N.json`，运行 `drama_lint.py --stage final`。
9. 由主 Agent 通过宿主实际交付工具只展示一个最终视频：字幕关闭时展示无字幕成片，字幕开启时展示字幕版。只有原平台非 Mobile 分支把该最终交付版本按 `cli/README.md` 写入 Canvas 并回读，本地分支按 `local-runtime.md` 提供真实文件入口或内联预览；随后等待用户确认。内部无字幕母版不得作为第二个版本展示或上画布。

调用前必须确认宿主实际暴露的 mediakit 能力和参数 schema；本地按 `local-runtime.md` 核对 `tools/media.py` 的实际能力。当前媒体链所需能力不存在时停止，报告缺失能力与已落盘产物，不得伪造调用或宣布成片成功。

所有 mediakit 编辑、探测、ASR 和字幕任务均为异步调用。提交成功只表示已受理；必须保存真实 `task_id`，通过 `byted-mediakit-shared / query-task` 查询到 `status=completed` 后，才消费结果并及时下载临时 URL。单次轮询达到 9 分钟后仍为 `running|queued` 时，用同一 `task_id` 继续查询；不得重复提交。本地 `tools/media.py` 是同步命令，以退出码、真实输出文件和探测结果确认完成，不套用上述异步任务字段。

### 基础可交付检查

基础可交付状态只允许 `deliverable|blocked`：

| 检查 | 字幕关闭 | 字幕开启 | 通过条件 |
|---|---|---|---|
| 无字幕母版 basic | 必须 | 必须 | 文件存在、可解码、可播放、有视频流 |
| ASR 对齐 | 不适用 | 字幕开启时必须 | 仅用于生成字幕文件，不评价剧情或口型 |
| SRT 与烧录参数 | 不适用 | 字幕开启时必须 | 字幕文件存在，烧录任务完成 |
| 字幕版 basic | 不适用 | 字幕开启时必须 | 文件存在、可解码、可播放、有视频流 |

不执行三级人工质检，也不因剧情、节奏、身份、状态、声音、口型、接缝或审美判断阻断当前已选择版本的交付；这些观察如已发现，只能静默记录为用户主动修改时的返修线索。字幕关闭时，无字幕成片通过基础可交付检查即可交付。字幕开启时，字幕版必须通过本文件第二部分的 ASR 对齐、文本一致性、SRT 与烧录客观硬门；失败时阻断字幕版并修复字幕链，不得把内部无字幕母版改成交付替代品，也不得同时交付两个版本。

成片客观交付硬门：

- 文件可解码并可从头播放到结束。
- 总时长与采用片段数量大体相符；明显 0 秒、空文件或只含音频/只含封面图时阻断。
- 画幅、方向和编码可被宿主交付工具识别。
- 字幕开启时，SRT 文件和字幕版视频文件真实存在且可播放。

若客观交付硬门失败，只修复导出、下载、mux、字幕烧录或文件损坏等媒体交付问题；不得因此自动调用视频生成/编辑工具。

### 平台适配

平台规格、审核规则、推荐时长和 UI 安全区会变化。需要平台版本时查询当前官方或可靠来源，记录日期和链接，再建立 `platform_delivery_profile`：

```json
{
  "platform": "",
  "verified_at": "YYYY-MM-DD",
  "sources": [],
  "aspect_ratio": "",
  "duration_limit": "",
  "safe_area": {},
  "subtitle_policy": "",
  "cover_spec": "",
  "title_and_tags": "",
  "content_constraints": [],
  "output_version": ""
}
```

同一母版产生不同平台版本时分别导出和验收，不直接拉伸或裁掉关键人物、道具及字幕。

### 最终状态

- `可交付成片`：最终版本已生成，文件存在、可解码、可播放，并具备当前环境交付所需字段。
- `候选成片`：可播放但仍缺少非阻断记录，或存在已记录的内容/审美/连续性风险等待用户判断。
- `未完成/待验证`：缺生成、拼接、下载、可播放文件或任一客观交付硬门证据。

对应机器状态固定为：`可交付成片 = deliverable`、`候选成片 = candidate`、`未完成/待验证 = blocked`。运行最终交付检查时，每集 `delivery_manifest` 必须为 `deliverable|candidate`，不得要求内容质检通过后才交付。

内部可交付不等于用户确认；最终渲染文件不可播放时禁止标记为 `可交付成片`。

### 存储与交付

路径、命名、比例编码、版本后缀、报告文件和 `delivery_manifest_ep_N.json` schema 只读取 `manifests.md`。每集 `outputs` 必须且只能包含一个最终视频：字幕关闭时为无字幕成片，字幕开启时为字幕版。SRT、字幕 JSON、烧录参数、检查报告和字幕开启时的无字幕母版均为内部制作与追溯文件，不作为额外交付物，不进入 `outputs`、`present_files` 或 Canvas。重导出建立新 `_vNN`，不得覆盖已确认成片。

交付前更新成片清单、基础可交付记录和 delivery manifest，将成片阶段及 `current_episode` 状态写为 `awaiting_confirmation`，运行当前集最终结构检查，并确保内部记录与真实文件一致。通过后立即展示当前集字幕策略对应的唯一最终视频；只有原平台非 Mobile 分支把该版本写入 Canvas 并回读，本地分支按 `local-runtime.md` 真实展示。收到修改意见时返回当前集最早受影响阶段处理并重新展示；只有用户明确确认后才完成当前集交付。多集项目在当前集确认后，才把下一集设为 `current_episode` 并进入其详细剧本阶段；最后一集确认后才完成整个项目。

---

## 第二部分：字幕生成与烧录

MediaKit 工具名、参数、异步生命周期与结果字段统一以调用时宿主实际暴露的能力与 schema 为准；本文件中的业务流程不得覆盖当前工具 schema。

本部分是字幕文本、ASR、SRT、烧录参数和字幕处理的唯一权威；成片触发条件、最终音轨和交付状态由本文件第一部分规定。

### 权威引用

- 最终音轨、成片触发条件和交付状态：本文件第一部分。
- 文件路径、命名及 `delivery_manifest_ep_N.json`：`manifests.md`。
- 媒体与文本基础可交付检查：mediakit 探测结果、真实文件与人工核对记录；最终结构门禁：`scripts/drama_lint.py`。

> **引用关系**：正确台词来自 `scriptwriter.md` 和分集 `script_contract`；成片入口与交付状态见本文件第一部分；文件路径、基础可交付记录引用和字段见 `manifests.md`；媒体与文本基础检查基于真实 mediakit 结果和人工核对记录，失败升级见 `troubleshooting.md`。

### 默认策略

- 字幕默认关闭。只有用户明确要求字幕、双语字幕、逐句字幕、caption 或字幕版成片时才开启字幕链路。
- 所有视频生成工具调用固定 `video_generation_subtitles: false`，禁止模型直接生成逐句字幕或自动转写文字。
- 成片阶段先锁定已采用片段与最终原声音轨，再生成字幕。
- 默认逐集只交付无字幕成片；若视频生成结果里出现字幕、随机文字、水印或平台 UI 残留，先用宿主非视频生成类字幕/文字擦除能力处理并验证后再交付，无残留则直接交付。用户明确要求字幕时，生成内部 SRT、字幕 JSON 和烧录记录，但只交付字幕烧录版；内部无字幕母版和字幕辅助文件都不作为第二份用户交付。字幕烧录按 `local-runtime.md` 选择当前宿主真实媒体链：原平台使用 mediakit `add-subtitle-to-video`，本地使用 `tools/media.py burn`；同一版本只走一条路径，不把本地实现伪称远端任务。
- 字幕时间优先来自 mediakit ASR；本地确实无 ASR 时，以实际音轨逐句试听形成人工对齐记录。两条路径只执行一条，正确文本都来自已确认剧本和 `speech_lines`，ASR 文本或人工听写都不能覆盖已确认台词。

### 全交付链工具职责（按当前 MediaKit 0.2.1 合同）

下表覆盖本文件两个部分。有效区间裁剪和视频拼接只在第一部分执行一次；第二部分直接消费已锁定的无字幕母版。

| 环节 | 默认工具 | 职责 |
|---|---|---|
| 有效区间裁剪 | mediakit `trim-video` | 按 verified cut 生成各 SEG 的有效区间文件 |
| 视频拼接 | mediakit `concat-video` | 按已确认顺序硬切拼接有效区间并保留原声音轨 |
| 媒体探测 | 原平台 mediakit `probe-video-metadata`；本地 `tools/media.py probe` | 原平台为无字幕母版和字幕烧录版生成带真实 task ID 的元数据调用信封；本地保存同步退出码、实际输出文件与 ffprobe 事实，不伪造 task ID |
| 字幕对齐 | mediakit `asr-subtitles`；无 ASR 时主 Agent 实际试听 | 获取或人工确认逐句起止时间和说话人，只保存实际采用路径的证据 |
| 对齐差异检测 | 主 Agent 对照 `script_contract` 与 ASR 结果或试听记录 | 按顺序映射 `spoken_text`，定位疑似错字、漏句、重复和截断；只用于字幕文件整理，字幕开启时失败则修复字幕链，不改交付版本 |
| 基础可交付检查 | mediakit 探测 + 真实播放 | 检查媒体参数、文件完整性、音轨及适用的 SRT 结构、时码和无标点规则 |
| 文本整理 | 已确认 `spoken_text` + 定向人工复核 | 用剧本正确文本修正 ASR 错字，不用 ASR 覆盖剧本 |
| 字幕烧录 | 原平台 mediakit `add-subtitle-to-video`；本地 `tools/media.py burn` | 按比例使用固定位置、36px 思源黑体和白色字幕；两条路径分别保存真实参数与结果 |
| 基础检查 | 当前媒体链探测 + 实际播放/抽帧 | 原平台以 `probe-video-metadata` 的真实任务结果检查文件是否可交付；本地以同步 ffprobe、全量解码和实际播放/抽帧结果检查，不伪造异步任务 |

核心分工：主 Agent 根据宿主实际能力执行媒体探测和字幕对齐，并按 `delegation.md` 委派裁剪、拼接、混音和字幕烧录等媒体变更。使用 mediakit 时，探测和 ASR 都保存真实任务标识、终态原始响应和输入文件哈希；本地无 ASR 时不伪造调用信封，改存 `asr_alignment_report`，其中写明 `method: manual_listening`、实际音轨文件与 SHA-256、逐句 `spoken_text`、试听确认的起止时间、说话人和复核结果。该字段是两条路径共用的对齐报告位置，不表示人工路径曾调用 ASR。

mediakit 路径的调用信封固定为：

```json
{
  "skill": "byted-mediakit-video",
  "operation": "probe-video-metadata|asr-subtitles",
  "task_id": "异步提交返回的真实task_id",
  "request_id": "响应存在时原样保存",
  "status": "completed",
  "raw_response": {"status": "completed", "result": {}},
  "normalized": {}
}
```

所有 mediakit 能力均按异步任务处理：提交后保存真实 `task_id`，使用 `mediakit-cli shared query-task --task-id <task_id> --poll-complete` 查询；单次轮询结束但 `status` 仍为 `running|queued` 时，用同一 `task_id` 继续查询，不得重复提交。只有 `status=completed` 才能消费结果；`failed|canceled|cancelled` 阻断。结果中的临时 HTTPS 下载地址有效期为 24 小时，必须及时下载到项目正式路径。

`raw_response` 保留 `completed` 终态查询的未经改写响应；探测信封的 `normalized` 至少包含 `duration_s/width/height/fps/video_stream_count/audio_stream_count`。ASR 信封至少能从 `raw_response.result.subtitles[]` 解析 `start_time/end_time/subtitle_text`；启用说话人识别后还必须能解析 `speaker`。

本地同步探测与人工试听证据按 `local-runtime.md` 保存，不套用这些异步字段。

### 台词与字幕文本合同

从剧本第一次写出台词时就保存三层文本：用户原文 `source_text` 逐字保留；带规范标点的 `display_text` 用于剧本正文和人工阅读；`spoken_text` 用于视频 Prompt、语音校验和字幕正文。`display_text` 与 `spoken_text` 只能调整标点、引号和空格，字词与顺序不得改写。`spoken_text` 按以下规则规范化：

| 原符号 | 处理 |
|---|---|
| `。？！…….!?` | 删除 |
| `，、；：,;:` | 替换为一个半角空格 |
| `——` | 替换为一个半角空格 |
| 中文/英文引号、书名号、圆括号 | 删除 |
| 句首、句尾空格 | 删除 |
| 连续多个空格 | 合并为一个半角空格 |

问句、感叹和语义停顿在 `display_text` 中保留正常标点；模型执行另写入 `delivery_intent`、`pause_plan`、`emotion` 和 `emphasis_words`，避免只依赖标点控制表演。

```json
{
  "speaker": "林远",
  "type": "on_screen_dialogue",
  "source_text": "顾长渊，本宫今日来，不是跟你拜堂的。",
  "display_text": "顾长渊，本宫今日来，不是跟你拜堂的。",
  "spoken_text": "顾长渊 本宫今日来 不是跟你拜堂的",
  "delivery_intent": "冷静拒绝",
  "pause_plan": ["顾长渊 后短停", "今日来 后短停"],
  "emphasis_words": ["不是", "拜堂"],
  "subtitle_text": "顾长渊 本宫今日来 不是跟你拜堂的"
}
```

### 七步流程

#### 1. 消费已锁定的无字幕母版

本部分不再次裁剪或拼接 SEG。直接使用第一部分按 verified cut 生成、完成混音并锁定最终音轨的无字幕母版；任何片段顺序、剪切点或音轨变化都会使后续 ASR、SRT 和字幕烧录产物失效。裁剪精度、拼接参数、异步任务和下载规则以调用时宿主实际 schema 为准。

#### 2. 按宿主能力取得对齐证据

仅原平台在实际提供 mediakit ASR 时执行以下命令；本地没有 ASR 时跳过该命令，不伪造任务或原始信封，改按 `local-runtime.md` 对最终音轨逐句试听，并把真实音轨 SHA-256、`spoken_text`、起止时间、说话人和复核结果写入同一份 `asr_alignment_report`，标记 `method: manual_listening`。

```bash
mediakit-cli video asr-subtitles \
  --video-url "拼接后_原音轨.mp4" \
  --language "cmn-Hans-CN" \
  --content-type "speech" \
  --enable-speaker-info

mediakit-cli shared query-task \
  --task-id <asr_task_id> \
  --poll-complete
```

保存调用信封 JSON，包含 `skill: byted-mediakit-video`、`operation: asr-subtitles`、以 `amk-tool-asr-subtitles-` 开头的真实 `task_id`、`status: completed` 和未经改写的终态 `raw_response`；原始分段至少能从 `result.subtitles[]` 解析 `start_time`、`end_time`、`speaker` 和 `subtitle_text`。ASR 时间戳作为默认时间依据；文本可能有错，不能直接进入成片。

#### 3. 对齐证据与剧本顺序对齐

主 Agent 读取本集 `script_contract_ep_N.json` 和实际采用路径的 ASR 调用信封或人工试听记录，按说话人、句序和时间范围把对齐条目映射到已确认 `spoken_text`。允许一句被拆成多条或相邻短句被合并；把输入文件、媒体文件、所选路径的真实证据、映射结果和阻断原因保存到 `质检_ASR对齐_vNN_ep_N.json`。

- 整句没有任何匹配、相似度低于阻断阈值、时间范围无效或顺序结构异常：`blocked`。
- 单字、同音字、专名差异由创作者定向试听判断，不进入自动报告门禁。
- 无论 ASR 识别或人工听写为何，字幕正文都来自已批准 `spoken_text`。

#### 4. 回填正确文本并规范化

1. 按说话人、句序和语义把实际采用路径的对齐条目映射到已确认 `speech_lines`。
2. 字幕正文只取 `spoken_text`，不改变 ASR 或人工试听已核验的起止时间。
3. 相邻同说话人短句时间间隔小于 `0.5` 秒时可以合并；开始时间取第一句，结束时间取最后一句。
4. 单句超过 `18-20` 个汉字时优先在语义停顿处换成两行，保持同一时间区间；只有 ASR 提供可靠词级时间时才拆成两个独立字幕事件。
5. 每条字幕建议持续 `1.5-5` 秒。超出范围时先重新核对 ASR 分句或人工试听记录；不得凭感觉平移时间戳。
6. 对齐失败时按原路径重新 ASR 或重新试听；确认音轨本身缺句时只记录可选返修范围，不自动调用视频工具。禁止猜测整体偏移量。

默认输出：

```text
episodes/ep_N/05_成片/字幕_时间轴_vNN_ep_N.srt
```

```srt
1
00:00:00,240 --> 00:00:03,160
顾长渊 本宫今日来 不是跟你拜堂的

2
00:00:03,160 --> 00:00:05,480
这只杯子 你认得吧 五天前
```

#### 5. 基础可交付检查

先对无字幕母版执行当前媒体链的媒体探测并实际播放。原平台把文件路径、输入哈希、真实任务标识、终态响应、期望值、实测值和结论保存到 `质检_基础_无字幕_vNN_ep_N.json`；本地在同一报告保存同步命令、退出码、stdout/stderr 或探测 JSON 证据、实际输出文件及哈希、期望值、实测值和结论，不伪造远端 task ID 或终态响应。检查文件存在性、时长、比例、帧率、视频流和音轨；字幕开启时还检查 SRT 结构、时码、无标点规则及其与 `spoken_text` 的逐字一致性，并在烧录后对字幕版重复探测与播放。期望时长取 `delivery_manifest_ep_N.json.duration_s`，期望画幅取已确认 `scale_plan.aspect_ratio`，期望帧率取已确认 `delivery_settings.output_fps`，不得由执行者临时填写或从待验媒体反推。时长、比例和帧率容差分别不得超过 `0.5` 秒、`0.01` 相对误差和 `0.1` fps，且必须为有限非负数。确定性错误阻断，字幕持续时间、单行长度和阅读速度异常进入人工复核。

每份报告至少保存以下公共字段；原平台或本地路径各自的真实探测、播放与解码证据继续按上一段附加，不用这些公共字段代替原始证据：

```json
{
  "status": "deliverable",
  "media_file": "episodes/ep_1/05_成片/[项目名]_成片_[比例]_无字幕_v01_ep_1.mp4",
  "media_sha256": "当前验收媒体实际字节的64位小写SHA-256",
  "expected": {"duration_s": 12, "aspect_ratio": "9:16", "fps": 30},
  "observed": {"duration_s": 12.08, "aspect_ratio": "9:16", "fps": 30}
}
```

`media_file` 必须精确等于本报告对应的当前 `clean_master` 或 `subtitle_master`，不能只写同目录中的旧版本；`media_sha256` 必须匹配该文件当前实际字节。`expected.duration_s` 必须逐值取 `delivery_manifest.duration_s`，`observed.duration_s` 必须来自本次真实媒体探测且为有限正数，两者差值不得超过 `0.5` 秒。字幕关闭时只接受无字幕母版的一份报告；字幕开启时按 `basic_qc_reports` 顺序分别接受无字幕母版、字幕版各一份。任一媒体在报告生成后发生变化，必须重新探测、播放并更新报告，不得沿用旧哈希或旧实测值。

#### 6. 固定字幕参数并烧录

默认使用 mediakit `add-subtitle-to-video`。参数字段名以调用时实际 schema 为准，视觉结果固定为：

| 成片比例 | 位置预设 | 位置参数 | 字号 | 字体 | 颜色 |
|---|---|---:|---:|---|---|
| `9:16` | `lower_third` | `pos_y=70%` | `36px` | 思源黑体（`sy_black`） | 白色 |
| `16:9` | `bottom_center` | 底部居中 | `36px` | 思源黑体（`sy_black`） | 白色 |

其他比例默认使用 `bottom_center / 36px / sy_black / 白色`，并通过代表帧检查安全区。用户明确要求其他样式时必须重新确认；未确认不得动态改变字体、字号、颜色或位置。

本地执行映射为 `python tools/media.py burn <mp4> <srt> <out> --size 36 --pos lower_third`（底部居中使用 `--pos bottom`），读取 `local-runtime.md`。`--size` 为实际像素字号，ASS PlayRes 与真实视频尺寸一致，lower_third 将文字中心定位在高度 70%；先烧录代表帧或短样本查看实际字号与位置，再按原阶段流程处理，不把固定虚拟分辨率下的字号当作像素。

本地 SRT 不能直接传给 `--subtitle-url`，该字段只接受公网 HTTP/HTTPS URL。默认把已验收 SRT 转成等价的字幕对象数组，并通过 `--subtitles` 传入；对象字段固定为 `start_time/end_time/subtitle_text`，时间单位为秒。SRT 仍作为内部字幕文本事实源，不进入正式 `outputs` 或默认展示。

```bash
mediakit-cli editing add-subtitle-to-video \
  --video-url "拼接后_原音轨.mp4" \
  --subtitles '[{"start_time":0.24,"end_time":3.16,"subtitle_text":"顾长渊 本宫今日来 不是跟你拜堂的"}]' \
  --subtitle-font-size 36 \
  --subtitle-font-type sy_black \
  --subtitle-font-color '#FFFFFFFF' \
  --subtitle-pos-preset lower_third

mediakit-cli shared query-task \
  --task-id <subtitle_task_id> \
  --poll-complete
```

横屏把 `--subtitle-pos-preset` 改为 `bottom_center`。终态必须为 `completed`，再从 `result.video_url` 下载字幕版；不得使用不存在的本地输出参数。

#### 7. 烧录处理

1. 从无字幕母版抽取包含人物、关键道具和平台 UI 风险的代表帧。
2. 用最长字幕、生僻字、数字和英文生成短样片，确认思源黑体字符覆盖。
3. 抽取每条字幕的首帧、中间帧和尾帧，检查越界、遮脸、遮嘴、遮关键道具、平台 UI 冲突和换行。
4. 任一字幕不合格时，优先调整当前已选媒体链支持的预设或断句并重新烧录；原平台不得绕过 mediakit，本地继续使用 `tools/media.py burn`，不得把两条路径混写为同一次调用。

### 字幕文件与记录

正式路径和命名只读取 `manifests.md`。本链路必须产生或更新：实际路径的媒体探测证据、ASR 原始信封或人工试听记录、对齐报告、SRT、烧录参数、无字幕母版基础报告、字幕版基础报告和适用的字幕烧录版。拼接过程文件属于中间产物，不在 `delivery_manifest_ep_N.json` 登记为正式输出。

`字幕_烧录参数_vNN_ep_N.json` 至少记录实际采用路径。原平台 mediakit 示例：

```json
{
  "source_video": "",
  "asr_source": "",
  "language": "cmn-Hans-CN",
  "text_policy": "no_punctuation_commas_to_spaces",
  "subtitle_source": "srt",
  "execution_path": "mediakit",
  "mediakit_input_mode": "subtitles_json_from_srt",
  "burn_tool": "mediakit_add_subtitle_to_video",
  "task_id": "本次真实任务 ID",
  "font_id": "sy_black",
  "font_name": "思源黑体",
  "font_source": "mediakit_builtin",
  "font_size": 36,
  "font_color": "white",
  "alignment": "lower_third",
  "position_mode": "mediakit_preset",
  "pos_y_percent": 70,
  "video_width": 720,
  "video_height": 1280,
  "ratio": "9:16",
  "platform": "",
  "safe_area_basis": "",
  "burned_video": ""
}
```

本地同步 `tools/media.py burn` 示例：

```json
{
  "source_video": "",
  "asr_source": "实际 ASR 原始信封或人工试听对齐报告路径",
  "language": "cmn-Hans-CN",
  "text_policy": "no_punctuation_commas_to_spaces",
  "subtitle_source": "srt",
  "execution_path": "local_sync",
  "local_input_mode": "srt_file",
  "burn_tool": "python tools/media.py burn",
  "command": "python tools/media.py burn <mp4> <srt> <out> --size 36 --pos lower_third",
  "exit_code": 0,
  "sync_result": {"ok": true, "command": "burn", "output_file": "实际输出路径"},
  "font_family": "Source Han Sans SC",
  "font_name": "思源黑体",
  "font_source": "system_font_via_libass",
  "font_size": 36,
  "font_color": "white",
  "alignment": "lower_third",
  "position_mode": "ass_explicit_pixel_anchor",
  "pos_y_percent": 70,
  "play_res_x": 720,
  "play_res_y": 1280,
  "video_width": 720,
  "video_height": 1280,
  "ratio": "9:16",
  "platform": "",
  "safe_area_basis": "",
  "burned_video": ""
}
```

实际记录只采用当前路径的真实字段和值；本地不得补造 `task_id`、异步 `raw_response` 或 `mediakit_builtin`，原平台也不得把本地同步命令写成远端任务。底部居中时分别使用原平台 `bottom_center` 或本地 `--pos bottom`，并保存对应真实参数。

### 硬门

- 实际采用路径的对齐证据、规范化 SRT、烧录参数和字幕烧录成片均已落盘并可追溯：mediakit 路径保存 ASR 原始 JSON，人工路径保存带真实音轨哈希和逐句试听时间的 `asr_alignment_report`，不得互相冒充。
- 无字幕母版与字幕烧录版均有真实媒体探测证据和基础可交付检查报告；mediakit 路径的 `task_id` 非空、终态为 `completed` 且操作名匹配，本地路径按 `local-runtime.md` 保存同步探测事实。
- 对齐报告不得为 `blocked`。
- 字幕固定使用当前宿主已选媒体链、思源黑体、36px、白色；9:16 使用 `lower_third / pos_y=70%`，16:9 使用 `bottom_center`。
- 字幕文本与已确认 `spoken_text` 逐字一致，没有 ASR 或人工听写错字。
- 字幕文本不含标点；逗号、顿号、分号和冒号已替换为单个空格，其余指定标点已删除。
- 起止时间必须来自实际 ASR 结果或逐句试听记录，不得猜测或整体平移；合并只使用首句开始和末句结束。
- 相邻同说话人短句只有在间隔小于 `0.5` 秒时合并。
- 每条建议 `1.5-5` 秒，单行建议不超过 `18-20` 个汉字；超长优先换行。
- 字幕底部、描边和阴影全部位于实测安全区内，不遮脸、嘴、关键道具、线索文字或平台 UI。
- 最终烧录成片保留无字幕母版的音轨，不因字幕烧录发生音画漂移。
- 用户明确选择无字幕时，记录该选择并跳过 ASR、SRT 和烧录步骤。
