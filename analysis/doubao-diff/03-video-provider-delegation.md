# 视频、生成确认、委派、Provider 与故障恢复对比

## 1. 对比范围、口径与结论

### 1.1 范围

- **原版（下文简称“原”）**：`<doubao-root>`
- **当前版（下文简称“现”）**：`<drama-root>`
- 主对比文件：
  1. `references/video.md`
  2. `references/video-batch-confirmation.md`
  3. `references/delegation.md`
  4. `references/troubleshooting.md`
  5. 当前新增 `references/video-provider.md`
  6. 当前新增 `references/video-providers/autodl.md`
- 为验证搬迁，另完整读取两侧 `SKILL.md`、`references/interaction-ask-video-clarification-ref.md`、`references/storyboard.md`，并读取当前 `references/local-runtime.md`、`tools/README.md`、`tools/h3.json`、`tools/video_run.example.json`。原版没有同名 `tools/README.md`。
- 行号均按本次读取的工作区快照。引用写作“原 `video.md:84-86`”“现 `video-provider.md:76-86`”，未特别注明时文件均位于各自 Skill 根目录下。
- 本报告是**文档合同对比**，不把文档声明等同于云端实测；未执行生成、开关机、联网恢复或云端下载。

### 1.2 总结论

当前版不是对原版 Seedance 流程的简单改名，而是把系统拆成四层：

1. **创作层**：仍由主 Agent 负责剧本、分镜、资产、真实输入和 SEAM/FRM 连续性。
2. **模型编译层**：由“单层、直接提交的五段式 Prompt”改为“中文五段式导演底稿 + 真实调用 h3-prompt-writing 得到的英文 H3 成稿”，实际提交只能是后者。
3. **串行执行层**：由“每次 1–2 个 SEG、必须异步 subagent”改为“每次最多一个新 SEG、每集一份固定 `串行执行.json`、固定 runner、段间主 Agent 看图反馈”。
4. **Provider 层**：新增模型/provider/协议分离、适配器与配置哈希锁定，以及 AutoDL 的独立电源授权、健康门、任务恢复、持久化资产找回、原子下载和退出清理。

保留的核心创作原则包括：真实素材必须真实传入；`continuous` 必须消费上一段真实 tail；`elliptical` 不强制 tail 但必须有新起点、转场锚点、不变量和允许变化；台词必须完整进入生成文本；默认不生成字幕；每段真实交付；内容问题不自动触发生成或返修；用户抱怨、纠正和原因追问本身不等于生成授权。

最重要的实际变化是：**当前 AutoDL 串行 queue 只支持图片和音频，明确禁止视频参考**。因此，通用 `video.md` 中依赖视频输入的 `media_to_video` 路径，以及把源视频作为 `<Video N>` 的 `video_edit -> Ref2VA` 路径，不能据此认定在当前固定串行入口可执行（现 `video-providers/autodl.md:171-177`）。

---

## 2. 六份主文件逐文件总表

| 文件 | 原版职责 | 当前版职责 | 判定与行为影响 |
|---|---|---|---|
| `references/video.md` | Seedance 视频生成、单层五段式 Prompt、1–2 SEG 批次、subagent 执行、mediakit 抽帧与交付后连续性记录（原 `video.md:43-56,74,258-272,404-421`） | H3 模型与 provider 分离；中文底稿到英文成稿；单 SEG 编译/确认/运行；固定 runner；本地媒体映射；段间真实反馈（现 `video.md:24-54,72,82-88,464-500`） | **大改**。保留导演与连续性内核，替换模型、提交文本、执行入口和反馈时点。 |
| `references/video-batch-confirmation.md` | 一次确认覆盖连续 1–2 个 SEG；两表共用；每 SEG 一行（原 `video-batch-confirmation.md:7-21,45-57`） | 一次确认只覆盖一个新 SEG；五列表恰好一行；新增 provider 和固定运行哈希绑定（现 `video-batch-confirmation.md:25-39,64-92`） | **语义改变 + 新增锁定**。确认从“小批次授权”变成“单段、不可复用的精确请求授权”。 |
| `references/delegation.md` | 视频生成/编辑必须异步委派 subagent；主 Agent 不得直调；结构化交接包和五个 `allow_*: false`（原 `delegation.md:7-12,50-90`） | 每集固定 `串行执行.json`；固定 `video_run.py`；`generate/recover/reuse`；无 subagent 时主 Agent 可启动并等待同一脚本（现 `delegation.md:3,7-54`） | **执行架构替换**。从“ Agent 权限隔离”转向“固定输入、进程、文件和状态证据隔离”。 |
| `references/troubleshooting.md` | 最早责任层级、V/A/F/S/N、部分成功、非视频一次定向重试、视频内容问题不自动返修（原 `troubleshooting.md:7-32`） | 保留上述原则，新增原任务只读恢复、提交不明防重、provider 证据归属和 H3 双层 Prompt 诊断（现 `troubleshooting.md:7-25,34,139-150`） | **同名规则延续 + 恢复语义大幅增强**。技术恢复不再被误算成新生成。 |
| `references/video-provider.md` | 无同名文件 | 模型/provider/协议三维；注册与确认；适配器接口、版本/哈希、通用恢复、可选电源（现 `video-provider.md:5-23,48-97`） | **当前新增**。provider 成为显式授权和运行事实，不再是隐含工具实现。 |
| `references/video-providers/autodl.md` | 无同名文件 | AutoDL 配置、凭证、电源、健康、提交、轮询、恢复、下载、清理和离线测试（现 `video-providers/autodl.md:20-189`） | **当前新增**。形成完整的云端生命周期合同，但当前 queue 有明确输入能力缺口。 |

---

## 3. `video.md`：逐项详细对比

### 3.1 模型、时长、工具与 Provider

| 主题 | 原版 | 当前版 | 分类及影响 |
|---|---|---|---|
| 默认/可用视频模型 | 默认 `seedance 2.0 fast`；只有明确确认 `seedance 2.5（会员模型并且消耗最多的额度）` 才可使用 2.5（原 `video.md:82-86`）。分镜另允许用户明确指定 `seedance 2.0 mini|seedance 2.0`（原 `storyboard.md:210-212`）。 | 当前唯一模型为 H3，模型与 provider 分开（现 `video.md:24,67,80-84`；现 `local-runtime.md:55-60`）。 | **语义改变**。不能再以“换模型”解决失败或时长问题；H3 不可用时只能停止、等待或调整合法分段。 |
| 单 SEG 时长 | 2.0 默认 10–15 秒、不得超过 15 秒；2.5 优先 25–30 秒、不得超过 30 秒（原 `storyboard.md:210-222`；原 `video.md:84-86`）。 | 默认 10–15 秒，硬区间 4–15 **整数秒**；不足 4 秒的尾数须重划相邻 SEG（现 `storyboard.md:183-186`；现 `video.md:82`）。 | **语义改变**。当前新增最短 4 秒与整数约束；原版 30 秒长段路径不再存在。 |
| 工具路由 | 零媒体 `text_to_video`；只有图片 `image_to_video`；存在视频/音频 `media_to_video`；已有视频定点返修 `video_edit`（原 `video.md:24-35`；原 `SKILL.md:269-273`）。 | 四个逻辑工具枚举保留，并新增到 H3 模式的映射；实际统一由固定 runner 和选中 provider 执行（现 `video.md:28-39,214-219,284-300`；现 `local-runtime.md:11-18`）。 | **同名同义 + 执行搬迁**。创作层路由语义基本不变，但不再表示主 Agent 直接调用原平台工具。 |
| 音色工具 | `Seed Audio 1.0` / `text_to_audio_plus` 生成 VOICE（原 `video.md:32,274-286`；原 `SKILL.md:268`）。 | `text_to_audio_plus` 映射到 Qwen3-TTS；轻量模式不新增独立音色资产阶段（现 `video.md:36,353-364`；现 `local-runtime.md:18,60`）。 | **后端替换，VOICE 合同保留**。Qwen3-TTS 可复用 AutoDL 电源，但不是另一个视频 provider（现 `video-providers/autodl.md:16`）。 |
| 模型与执行位置 | 未建立独立 provider 字段；实际视频工具隐含承载执行位置。 | H3、`autodl`、`comfy_workflow_v1` 分属模型、provider、协议三个维度（现 `video-provider.md:5-15`）。 | **当前新增**。更换 provider 不得连带改 Prompt、剧情、SEG、时长或画幅。 |
| 画幅/分辨率 | 画幅只进工具参数，不写 Prompt；按已确认规划与工具 schema 复核（原 `video.md:84-86,272`）。 | 仍不写 Prompt；实际请求参数由 provider 配置和适配器承载，目标交付比例不等于 provider 已支持请求参数，须核验真实输出（现 `video.md:84,345`；现 `tools/h3.json:55-56`）。 | **同名原则保留 + provider 化**。不能只凭目标比例宣称生成请求已经支持该比例。 |

### 3.2 输入类型、数量和时长上限

原版在 `video.md` 强调真实图片、视频、音频输入和实际 schema；具体 Seedance 数量/时长集中在原 `SKILL.md` 工具表。当前版把 H3 上限直接写入 `video.md` 并由 `tools/h3.json` 机器化。

| 输入/模式 | 原版 | 当前版 | 影响 |
|---|---|---|---|
| 无媒体 | `text_to_video`，三类媒体为空；非首段只允许无必要媒体锚点的 `elliptical`（原 `video.md:28,35,193`）。 | `T2VA`，零媒体，规则相同（现 `video.md:86,216,292`）。 | **同名同义并明确 H3 模式**。 |
| 普通图片参考 | `image_to_video`，图片必须真实传入；图片总数不得超过当时工具上限，超限拆 SEG 或返回可用工具方案（原 `video.md:201-205`）。 | 普通身份、场景、高光、群众及额外参考统一走 `Ref2VA`，不强制任一图片成为首/尾帧（现 `video.md:214-218,290-298`）。 | **语义细化**。避免把所有参考图误写成硬帧约束。 |
| 真实首帧/尾帧 | 主要通过 `previous_tail_as_start_frame` 等职责描述，没有当前这套 I2VA/FL2VA/L2VA 精确模式表（原 `video.md:203-205`）。 | `I2VA` 仅 1 张真实首帧；`L2VA` 仅 1 张真实尾帧；`FL2VA` 恰好 2 张真实首尾帧并填写 `frame_position`（现 `video.md:86,231,294-296`）。 | **新增精确槽位语义**。当前 `tools/h3.json:15-35` 的机器上限与 `video.md:86` 的更严格职责约束须一起遵守。 |
| Ref2VA 图片 | 原版无此模式名和固定 9 张上限；按实际 schema。 | 图片最多 9；Ref2VA 图片、视频、音频总文件最多 12（现 `video.md:86`；现 `tools/h3.json:36-52`）。 | **新增明确数量硬门**。 |
| 视频参考 | `media_to_video` 最多 3 个视频参考；默认参考视频总时长 ≤14 秒，2.5 ≤28 秒；单个参考 ≥2 秒（原 `SKILL.md:271`）。 | H3 Ref2VA 最多 3 个视频；每个 2–15 秒；视频合计 ≤15 秒（现 `video.md:86`）。**但 AutoDL 当前串行 queue 禁止视频参考**（现 `video-providers/autodl.md:176`）。 | **模型能力与当前执行能力必须分开**。AutoDL 固定入口不能承诺视频参考可用。 |
| 音频参考 | Seedance 2.0 最多 3 个音频；单个 ≥2 秒；默认合计 ≤15 秒，2.5 合计 ≤30 秒（原 `SKILL.md:271`）。 | Ref2VA 最多 3 个音频；每个 2–15 秒；合计 ≤15 秒；有音频时必须同时有图片或视频（现 `video.md:86`）。 | **语义改变并新增依赖约束**。AutoDL queue 支持音频，但仍须满足视觉输入条件。 |
| 超长音色派生 | 可为上传上限制作参考副本，不覆盖 accepted 原片或原音，不改变已确认 SEG/FRM 事实（原 `SKILL.md:187`）。 | 可从已核验静音区间用 `media.py cut-audio` 派生新 WAV；禁止覆盖原音、删语音、去必需音色或改说话人槽位；登记双侧哈希、删除区间、实测时长和全量解码；queue 字节变化后重新预检和确认（现 `video.md:88`）。 | **规则保留并具体化**。当前把“参考副本”升级为可审计的请求专用派生资产。 |

真实输入硬门没有弱化：两版都要求人物身份/状态、场景、道具/状态、高光 KF、返修图、连续 tail 等命中即真实传入，不能只写资产 ID 或 planned path；缺必需输入、超上限或后端不支持时停止，不得删掉关键参考继续生成（原 `video.md:201-205`；现 `video.md:227-231`）。

当前另增群众参考职责 `crowd_reference`，以及真实 dry-run/task slots 对上传文件的核验，防止只登记 `passed_to_tool` 而未上传（现 `video.md:231,347-351`；现 `storyboard.md:418-442,767-778`）。

### 3.3 从单层五段式到“两层 Prompt”

#### 原版：实际提交文本就是五段式

原版要求每个 SEG 独立保存 `提示词_SEGxxx_vNN_ep_N.md`，该文件就是最终提交给模型的文本；由五个空行分隔的自然段组成，顺序固定（原 `video.md:43-50,258-270`）：

1. 输入资产定位与 0 秒基准。
2. 参考主体绑定与生成目标。
3. 逐时间段动作、声音与脚本。
4. 转场与尾态收束。
5. 全片一致性与禁区。

重要短引：

> “五段式是一份视频生成 Prompt 的五层信息合同，不是五个镜头，也不是五个时间段。”（原 `video.md:258-262`）

五段中的第三段承担逐镜时间轴，不是把整段机械切成五截；每个已确认镜头必须恰好编译一次。画幅不写进 Prompt（原 `video.md:262-272`）。

#### 当前版：五段式只约束中文导演底稿

当前每次只编译当前一个新 SEG：

- 中文底稿：`编译底稿_SEGxxx_vNN_ep_N.md`，字段 `director_draft_file`。
- 英文 H3 成稿：`提示词_SEGxxx_vNN_ep_N.md`，字段 `compiled_prompt_file`。
- 主 Agent 必须真实执行 `Skill(skill="h3-prompt-writing", args=<完整交接包>)`；不得只手写同格式文本冒充 Skill 结果（现 `video.md:45-50,302-327`）。
- 实际提交只读英文成稿；中文底稿不直接提交（现 `video.md:49,335`；现 `tools/README.md:74`）。
- 登记 `h3_conversion`：Skill 名、宿主调用通道、`invoked=true`、带时区时间、底稿 SHA-256、成稿 SHA-256；任一层字节变化即失效并重新调用（现 `video.md:50,221`）。
- 底稿先做一次集中客观预检；成稿再做结构、槽位、台词、时长校验；最后还要由主 Agent 对照底稿人工回读成稿，检查动作桥、运镜、表演、声音、色彩、尾态和否定指令是否被反转或弱化。lint 与人工语义复核互不替代（现 `video.md:48-50,329-345`）。

**结构不再一一对应**：五段式仍完整保留在中文导演源，但 H3 成稿由 h3-prompt-writing 的指南决定。T2VA/I2VA/FL2VA/L2VA 使用三段核心字段，帧模式另有首行对齐指令；Ref2VA 使用六段结构（现 `video.md:315-327,329-343`）。因此不能把“英文成稿没有五个中文自然段”误判为缺少五段式。

Ref2VA 中文底稿还允许严格结构化形式：一个非空输入与连续性前置段，加固定顺序的 `integrated_multimodal_description`、`overall_soundscape`、`non_diegetic_music`、`dialogue_refs` 四个二级标题，合计五个顶层信息段；台词从花括号改为 `dialogue_refs.spoken_text` 表。该形式仍只是中文导演源，不是实际提交成稿（现 `video.md:331-335`）。

交接包必须包含：模式、整数秒时长、语言/字幕合同、完整中文底稿、本 SEG 全部镜头与运镜、真实媒体槽位及职责、完整 `speech_lines`、数据卡/轻量真实事实、continuous 真实 tail 或 elliptical 新起点、质量目标、可观察状态变化和声音设计（现 `video.md:302-313`）。这把原版“执行包保存 Prompt”前移并扩展为“转换输入也可追溯”。

### 3.4 台词 `<d>`、说话人、媒体标记与文字符号

| 项目 | 原版 | 当前版 | 行为影响 |
|---|---|---|---|
| 中文可听文本 | `说话人：{spoken_text}`；每条 `spoken_text` 必须逐字进入实际 Prompt（原 `video.md:266,280-283,309-328`）。 | 自然段底稿继续用 `{spoken_text}`；结构化 Ref2VA 底稿用 `dialogue_refs.spoken_text`；H3 成稿统一为 `<d>[语言] 原文</d>`（现 `video.md:317-325,353-360`）。 | **新增第二层硬门**，中文底稿存在台词不再足以证明台词已提交。 |
| 成稿台词保真 | 无 H3 `<d>` 层。 | 每条台词恰好一个 `<d>`；块数等于条数；只允许规范标点/空白，不翻译、不增删字词、不调词序、不换说话人、不拆并句（现 `video.md:50,320,358-360`）。 | **显著增强可校验性**。漏句、串人、拆句均可在提交前阻断。 |
| 说话人 | 角色名/VOICE ID 和 voice_anchor 写入中文 Prompt。 | H3 使用稳定 `(Sx)`，按实际发声事件顺序分配并跨镜复用；传 VOICE 时 `<Audio N>` 定义复用同一说话人编号（现 `video.md:320,360-361`）。 | **新增跨镜说话人槽位**。 |
| 音色锚点 | 没有音频输入不代表静音；在台词附近逐字复用 `voice_anchor`；有真实 VOICE 时走 `media_to_video`（原 `video.md:272-286`）。 | 原则保留；中文 voice_anchor 在英文成稿中只翻译为年龄/性别表达、音高、音色、语速、口音等识别短语，不得新增身份（现 `video.md:321,345,353-364`）。 | **同名原则保留 + 英译边界新增**。 |
| 中文媒体标签 | `<图片N>/<视频N>/<音频N>`，编号匹配真实上传顺序（原 `video.md:264,272`）。 | 中文自然段底稿沿用中文标签；成稿转为 `<Picture N>/<Video N>/<Audio N>`；结构化 Ref2VA 底稿可直接使用英文槽位标签；编号始终匹配真实 order（现 `video.md:47,317-320,333`）。 | **标签发生语言/结构迁移，不是媒体顺序可重排**。 |
| 字幕源 | `【】` 只作后期字幕源，不得进入视频生成画面（原 `video.md:266,283-284,318-328`）。 | `【】` 只允许出现在中文底稿，禁止进入 H3 成稿（现 `video.md:324,360`）。 | **同名策略保留，成稿禁则加强**。 |
| BGM/环境声/画面文字 | BGM `()`；环境声/拟音 `<>`；标题等画面文字 `“…”`（原 `video.md:318-328`）。 | BGM 归入 `non_diegetic_music`；环境声进 `overall_soundscape`，同步画内声进 `detailed_description`；画面文字改英文双引号但内容保留原语言（现 `video.md:322-327`）。 | **格式转换，叙事职责保留**。 |

四类人声 `on_screen_dialogue / narration / voiceover / inner_monologue` 仍均由视频模型原生生成；出镜对白驱动指定角色开口，其余三类明确画面人物不开口。生成后静音、漏句、串人、类型或口型问题仍只记录为用户主动返修线索，不自动重生（原 `video.md:274-286`；现 `video.md:353-364`）。

### 3.5 SEAM / FRM 与真实尾态

两版共享以下基础合同：

- **planned SEAM** 是分镜阶段的生成合同，**FRM** 是视频生成后的真实帧事实，不能在分镜阶段伪造实际 FRM（原 `storyboard.md:700-723`；现 `storyboard.md:685-707`）。
- `continuous` 非首段必须有上一段真实 tail；`elliptical` 不强制 tail，但必须有明确新起点、不变量、允许变化和转场锚点（原 `video.md:98-117`；现 `video.md:100-117`）。
- KF 仍是生成前的集级剧情高光，不承担普通首尾帧职责；FRM 不会被 KF 替代（原 `video.md:18-20,390-411`；现 `video.md:20-22,464-490`）。
- 每段至少有 start、scene、tail；相邻段另取上一段末 12 帧和下一段首 12 帧；tail 不一定是编码末帧，应避开黑帧、转场和污染帧（原 `video.md:404-421`；现 `video.md:483-500`）。
- 观察 SEAM 时先查 `required_invariants`，再查变化是否只属于 `permitted_deltas`；声音桥不能掩盖未允许的身份、动作相位或光位错误（原 `video.md:448-465`；现 `video.md:527-544`）。

关键语义修正：

- 原版统一把 continuous tail 写成 `previous_tail_as_start_frame`（原 `video.md:105,205`；原 `storyboard.md:436-456`）。
- 当前区分：**Ref2VA 中 tail 通常只是 `previous_tail_reference`，省略 `frame_position`，只继承 0 秒事实，不声称 API 强制首帧；只有“仅 1 张真实 tail 作实际开场”的 I2VA 才能使用 `previous_tail_as_start_frame` 和 `frame_position: first`**（现 `video.md:104-117,231`；现 `storyboard.md:436-440`）。
- 这不是放松 continuous，而是纠正参考图与硬首帧的混称；缺 tail、来源哈希或主 Agent 看图观察仍会阻断当前段编译、确认和提交（现 `video-batch-confirmation.md:13-21`）。

反馈时点明显前移：

- 原版通常在当前 SEG 交付后补 FRM/SEAM 内部记录，observed SEAM 在两段都生成并交付后记录，问题不阻断交付（原 `video.md:50-52,448-450,481-500`；原 `delegation.md:46`）。
- 当前 runner 可先抽取接力 tail，主 Agent 在每次进程退出后、当前段交付前实际看 start/scene/tail，并在后段交付前查看双侧 SEAM 窗口、登记 observed SEAM；下一段只能在当前段看图、登记和交付后编译（现 `video.md:442,468,494-500,527-529,560-578`；现 `delegation.md:58-69,88-94`）。
- **观察前移不等于主观质量门恢复**：当前仍明确 `rework` 不阻断 best available 当前段交付，不自动重生；阻断的是缺真实证据、媒体不可解码、哈希不符等技术/真实性问题（现 `video.md:452-460,558,573,577-620`；现 `delegation.md:84-94`）。

### 3.6 `video_edit` 的能力语义弱化

原版把 `video_edit` 定义为对已有视频的定点编辑：只传一个真实源视频，不传图片/音频；保持原比例、时长、人声、音色和口型关系；复杂剧情/镜头变化返回分镜或重生（原 `video.md:31,347-354`；原 `SKILL.md:272`）。

当前明确承认 **H3 没有原生视频编辑能力**：`video_edit` 只是将源视频作为 `<Video N>` 的 Ref2VA 参考重生成，编辑意图进入 `detailed_description`，语义弱于原生定点编辑；必须向用户说明限制并重新确认，且仍走两层 Prompt（现 `video.md:427-434`）。

因此这是明确的**能力弱化/语义改变**，不能继续把当前 `video_edit` 描述为等价的局部原位编辑。更现实的是，AutoDL 当前串行 queue 又禁止视频参考，所以该路径在固定入口还受到额外可执行性阻断（现 `video-providers/autodl.md:176`）。

### 3.7 生成后看图、登记、原始资源与交付

原版：

- subagent 返回真实输出路径、工具原始可渲染资源字段、URL/短链和工具结果；主 Agent 保存、登记、检查并交付（原 `video.md:48-51`；原 `delegation.md:12,92-100`）。
- 未做媒体处理时，原始资源就是最终交付版本；做了字幕擦除/烧录等处理时，处理后资源是唯一正式交付版本，原始资源只用于追溯（原 `SKILL.md:175`）。
- 完整模式每个 SEG 即时交付；非 Mobile 还须 `present_files`、Canvas 写入和 CLI get 回读后才继续下一段（原 `video.md:51,74`）。

当前：

- runner 负责 submit/resume、poll、download、客观媒体检查、tail 和电源收尾；主 Agent 在退出后亲自看图、对账 task/run-state/输出/哈希，登记并交付（现 `delegation.md:58-69,88-94`）。
- 证据由“subagent 回传字段”迁移为“任务文件保存 `result_url` + 真实输出 + run-state + 来源/tail 哈希”。这不是简单删除原始资源证据，而是换了责任主体和存储位置。
- 本地通过宿主实际提供的文件链接或内联预览逐项交付，不把未展示路径当成已交付；原始文件保持原位置，未经授权不为展示上传外部服务（现 `local-runtime.md:72-77`）。
- 本地没有 Canvas/Workspace 时不伪造远端 Item；这只替换宿主交付路由，不扩大生成授权（现 `SKILL.md:39-45`）。
- 当前段交付后才编译下一段；整集未齐保持 `in_progress`，整集齐全后才做阶段准出与拼接确认（现 `video.md:51-54,448-460`）。

### 3.8 字幕与 mediakit / 本地 `media.py` / ffmpeg

字幕创作策略基本未变：

1. 视频模型阶段固定不生成逐句字幕；默认最终 `subtitle_enabled: false`。
2. 只有用户明确要求字幕，才在最终音轨锁定后的成片阶段生成、对齐并烧录。
3. 逐段预览不另补正式字幕；模型意外字幕、随机文字、水印或平台 UI 按非视频生成类清理策略处理。
4. 最终只交付一个字幕策略版本：默认无字幕版，或用户明确要求的字幕版，不双发（原 `video.md:274-285`；原 `SKILL.md:181,188-189`；现 `video.md:347-364,452-460`）。

媒体实现发生明确迁移：

- 原版要求裁剪、拼接、抽帧、探测、ASR、字幕擦除/烧录都用 mediakit 或宿主等价能力，禁止 ffmpeg、本地封装或自行脚本冒充；mediakit 抽帧是异步任务，要保存 task ID、轮询并下载限时 URL（原 `video.md:24-35,413-421`；原 `SKILL.md:188,273`）。
- 当前按 `local-runtime.md` 选择原平台 mediakit 或本地已批准的 `tools/media.py`。本地实现可以调用 ffmpeg/ffprobe，操作日志仍登记 `mediakit`；它是同步命令，以退出码、真实输出和探测结果确认，不伪造远端 task ID（现 `video.md:37,492-500`；现 `local-runtime.md:19-33,69`；现 `tools/README.md:60-76`）。
- 当前本地**没有 ASR**：SRT 从锁定剧本台词整理，按实际音轨试听对齐，不能把估计时间冒称 ASR 结果（现 `local-runtime.md:27,69-70`）。这属于真实的本地能力缩减，而非只是工具改名。

---

## 4. `video-batch-confirmation.md`：1–2 段批次到单 SEG

### 4.1 逐文件对照

| 项目 | 原版 | 当前版 | 影响 |
|---|---|---|---|
| 范围 | 当前集接下来连续 1–2 个 SEG；两段可共用一次确认（原 `video-batch-confirmation.md:15-21`）。 | `batch_start_segment_index == batch_end_segment_index`，数量固定 1（现 `video-batch-confirmation.md:33-39`）。 | **授权粒度收紧**。两段不能再共享新生成确认。 |
| 编译时点 | 批次内各 SEG 独立 Prompt，前段保存、登记、交付并上画布后才执行下一段（原 `video.md:43-56,74`）。 | 当前段完整两层编译和真实输入闭合后才确认；不得预编译/预确认后续 SEG（现 `video-batch-confirmation.md:5-21`）。 | **真实反馈进入编译前置**，而不是只在同批串行执行时使用。 |
| 展示顺序 | 同一条普通文本：一张参数表、一张五列表、一次 `interaction.ask`（原 `video-batch-confirmation.md:5-13`）。 | 顺序相同，但两张表都只包含当前 SEG（现 `video-batch-confirmation.md:23-31`）。 | **同名同义保留**。 |
| 参数表 | 数量 1 或 2；逐段时长和批次总时长；模型含会员提示；参考素材等（原 `video-batch-confirmation.md:23-41`）。 | 数量固定 1；总时长等于当前 SEG；模型固定 H3；新增“视频生成后端”；素材必须真实存在，continuous tail 不得写成未来依赖（现 `video-batch-confirmation.md:41-60`）。 | **模型/provider 分开确认**，参数更贴近真实执行字节。 |
| 五列表 | 每 SEG 一行；两段各自独立行；声音列列全台词（原 `video-batch-confirmation.md:43-57`）。 | 固定五列不变，但恰好一行；仍须列全 `speech_lines[].spoken_text`（现 `video-batch-confirmation.md:62-75`）。 | **用户可见内容结构保留，行数改变**。 |
| 记录 | confirmation ID、attempt、supersession、数量、逐段时长、展示原文和两张表（原 `video-batch-confirmation.md:59-71`）。 | 另存 provider、适配器版本/SHA-256、cloud config SHA-256、`execution_mode: serial_real_tail_chain`、run plan 路径/SHA-256（现 `video-batch-confirmation.md:77-92`）。 | **确认与运行代码/配置绑定**，防止确认后换执行环境。 |
| 恢复/复用 | 原版没有统一 operation 语义；部分成功只补失败项。 | 真实哈希复用、原任务轮询恢复、结果下载和同源 tail 补抽不增加新生成数量，也不重复确认；新增、返修、重生或展示参数变化必须重新确认（现 `video-batch-confirmation.md:7-9`）。 | **新增恢复授权边界**，避免“恢复”被滥用为重生成。 |

当前确认前的硬门不只是“两张表填齐”：还必须已有完整中文底稿、真实 Skill 调用、保存后的英文成稿、通过双哈希/结构检查的 `h3_conversion`；continuous 还需真实 tail、来源视频/tail 哈希和主 Agent 看图观察。缺任一项不得展示确认表（现 `video-batch-confirmation.md:11-21`）。

### 4.2 用户意图与确认方式：核心未变

两侧 `interaction-ask-video-clarification-ref.md` 均保留：

- 默认直接给完整方案，不做内容问卷；只有商业任务无相关素材时才触发唯一素材询问例外（原 `interaction-ask-video-clarification-ref.md:7-23`；现同名文件 `:9-23`）。
- 正式生成确认是一道封闭式单选题，只有“按要求生成 / 暂不生成”，`multi_select: false`，并提示高消耗（原 `:43-83`；现 `:43-83`）。
- 普通聊天肯定、沉默、模糊答复、历史确认都不能替代实际生成确认；参数变化要完整重展示、重确认（原 `:86-92`；现 `:86-92`）。
- 用户抱怨、纠正、表达情绪或追问原因并不自动产生生成/返修授权；原版在主入口和故障表中明确这一点，当前继续保留（原 `SKILL.md:178-180`；原 `troubleshooting.md:120-121`；现 `SKILL.md:163-170`；现 `troubleshooting.md:113-114`）。

当前新增/明确：

- 每个新 SEG 单独确认；原 provider 的原任务恢复、下载和 tail 补抽不重复确认（现 `interaction-ask-video-clarification-ref.md:29,90-92`）。
- 展示模型与 provider 自然名称；模型或 provider 改变都使旧确认失效（现 `:41,90`）。
- 本地没有原平台 `interaction.ask` 时，按 `local-runtime.md` 使用宿主真实确认工具或两项文本确认并保存真实记录，不能因工具缺失跳过确认（现 `:3`；现 `local-runtime.md:62-69`）。现 `interaction` 第 27 行的固定工具禁则应结合第 3 行的本地作用域理解，不是要求伪造原平台调用。

---

## 5. `delegation.md`：受控 subagent 到固定串行 runner

### 5.1 原版：必须异步 subagent

原版关键约束（原 `delegation.md:7-12,16-46`）：

- 所有实际视频生成/编辑必须异步委派 subagent；主 Agent 不得直调。异步能力不可用时暂停，不能退回主 Agent 直调。
- “异步”只表示不阻塞主对话，不改变同批 SEG 串行依赖。
- 主 Agent 负责确认、Prompt/请求快照、交付、Canvas；subagent 不得改上游、模型、Prompt、分镜，不得再委派、确认、写 Canvas 或直接交付。
- 前段返回、保存、登记、交付、非 Mobile 上画布并抽取下段所需 FRM 后，才下发下一段。
- 交接包含 `skill_name=doubao-creative-drama`、references、上游 revision、Prompt/请求快照、允许输出路径、硬约束、验收标准和五个 `allow_*: false`（原 `delegation.md:50-90`）。
- 主 Agent 收回后核对越权、播放/探测、登记和交付；内容问题不自动返修（原 `:92-101`）。

### 5.2 当前：一个固定 JSON、一个固定入口、每轮最多一个新 POST 授权

当前每集只有：

`episodes/ep_N/04_视频片段/串行执行.json`

它同时是当次 queue 和固定脚本的启动参数来源；不再另建 plan、build queue、执行包或启动包装 JSON。每轮只填当前已确认的新 SEG，以及确需同次恢复/复用的既有段；启动后不得修改，确认记录绑定该文件 SHA-256（现 `delegation.md:5-35`）。

固定命令：

```bash
python -I tools/video_run.py --project-root <项目目录> --episode ep_N
python -I tools/video_run.py --project-root <项目目录> --episode ep_N --execute
```

第一条只做离线预检；第二条再次预检并固定进入：

```text
autodl_instance.py run-managed -> workflow_series.py run
```

不得临时改写 Python/Bash 包装命令。真实执行前须完成上游、唯一新 SEG 确认、JSON、离线预检、凭证和精确实例电源授权；不得先开机再补参数（现 `delegation.md:37-54`；现 `tools/README.md:31-52`）。

三种 operation：

| operation | 当前语义 | 是否新增生成授权 |
|---|---|---|
| `generate` | 一次新生成；同一 JSON 最多一项；绑定当前确认 ID | 是，但仅限当前唯一 SEG |
| `recover` | 按已有任务文件和原确认 ID 恢复原任务，不重复 POST | 否 |
| `reuse` | 复用真实存在、校验相符的输出和 tail | 否 |

见现 `delegation.md:29-35`。需要恢复上一段时，本轮只能先恢复；退出看图复核后才能建立下一新 SEG，不能拿未来 tail 先确认新段（现 `:35`）。

当前完整段间链路：

```text
当前新 SEG 的真实输入、两层 Prompt、预检与确认
-> submit|resume -> poll -> download -> media check
-> 保存真实 tail
-> 完成或不可恢复停止 -> 电源收尾
-> 主 Agent 看图、对账、登记并交付
-> 根据真实尾态重新编译、预检并确认下一新 SEG
```

（现 `delegation.md:56-69`）

### 5.3 主体边界是“变化”，不是简单削弱

当前 `local-runtime.md:68` 明确：本地有 subagent 时由 subagent 启动并等待固定 `video_run.py`；没有时由主 Agent 启动并等待同一进程。内层始终是同一受管链。

因此：

- **原版独有的强制角色隔离被放宽**：主 Agent 可以启动固定进程。
- **当前用更强的机器合同补偿**：固定 JSON、固定命令、单 `generate`、执行锁、任务防重、run-state、输出白名单、哈希绑定、禁止执行器修改 Prompt/素材/确认/拼接。
- 创作、用户确认、看图语义判断和交付仍只属于主 Agent；runner 技术成功不能证明内容承接正确（现 `delegation.md:67-69,88-94`）。

---

## 6. 当前新增 `video-provider.md`：通用 Provider 合同

### 6.1 三维分离与禁止静默切换

- H3 决定时长、模态、槽位、Prompt 结构；`autodl` 决定实际执行位置；`comfy_workflow_v1` 决定请求/查询格式（现 `video-provider.md:5-13`）。
- 当前注册表只有 `autodl`，可离线查询公开 ID、名称、协议、文档路径，不读取凭证（现 `:15`）。不能写成“当前已有多个可自由选择的后端”。
- 规划时分别登记 `model_plan.video` 和 `model_plan.video_provider`；完整确认表也分别展示“视频模型 / 视频生成后端”（现 `:17-23`）。
- 执行器不得因连接失败、排障、超时、额度、速度或偏好自动切换 provider；用户要求切换时更新固定 JSON、重新预检，若会有新 POST 则重新生成确认。旧任务只读恢复仍走原 provider（现 `:21-23`）。

重要短引：

> “更换 provider 不等于更换模型，也不授权改写剧本、分镜、Prompt、SEG、时长或画幅。”（现 `video-provider.md:13`）

### 6.2 配置、代码和确认的锁定链

固定 JSON 显式写 `video_provider` 和 `cloud_config`；cloud config 显式写受支持的 `protocol`。缺少 provider/protocol、二者冲突或不受支持都直接停止，不从目录、任务文件或其他字段猜测（现 `video-provider.md:25-37`）。

`workflow_series.py preflight` 从真实安装代码计算并返回：

- `video_provider_adapter_version`
- `video_provider_adapter_sha256`
- `cloud_config_sha256`

run-state 必须完整保存这些绑定并与固定 JSON、配置和安装代码一致；缺字段或失配拒绝续跑，不自动补写。确认记录使用同次 preflight 的返回值，固定 JSON 不重复手填这些哈希（现 `:39-46`）。

结合单段确认合同，实际锁定链为：

```text
当前 SEG 的模型 / Prompt / 素材 / 槽位 / 时长 / 输出 / 授权
+ 固定 串行执行.json 及其 SHA-256
+ provider 注册 ID 与协议
+ 适配器版本与 SHA-256
+ cloud config SHA-256
+ run-state / 任务文件 / 确认记录相互一致
```

任何新生成请求字节或展示参数变化都需重新预检和确认；纯恢复不得改变原请求（现 `video-batch-confirmation.md:38,79-92`）。

### 6.3 统一适配器接口与职责边界

注册表只能导入 Skill 内置且审核过的模块，不能由项目 JSON 指定任意 Python 路径。provider 至少实现（现 `video-provider.md:48-74`）：

- `load_config`：校验配置并拒绝文件内凭证。
- `prompt_markers`：核对成稿媒体标记与真实记录。
- `verify_task_inputs`：恢复前核对 Prompt、真实输入和哈希，防止套错任务。
- `submit_segment`：只提交一个已授权片段；一个任务文件最多一次真实提交。
- `poll_segment`：原任务恢复、查询、下载和客观媒体校验；`resumed=True` 明确跨进程恢复。

两个执行结果统一提供 `task_id`；串行器不依赖 provider 私有的 `prompt_id`、实例 UUID 或云状态名。通用串行器继续拥有授权映射、执行锁、连续范围、真实 tail/source 哈希、输出白名单、tail 抽取、run-state 和退出对账，且不包含 provider 专用 endpoint、凭证、电源或恢复协议。

### 6.4 通用恢复底线

所有 provider 共同遵守（现 `video-provider.md:76-86`）：

1. 原任务只读恢复、结果下载、媒体校验和同源 tail 补抽不新增生成授权。
2. 恢复不得产生新 POST；旧 ID 查询为空、接口异常或超时都不能成为重提理由。
3. 优先使用原任务保存的结果证据和可精确绑定身份的持久化记录。
4. mtime、时长相近、目录只有一个视频、文件名相似或“看起来像”均不能独立证明归属。
5. 无法唯一归属就保留现场并停止，不能标成可盲重试的新任务。
6. 先保存结果 URL，再下载、检查音轨/全量解码并原子落盘；本地失败不抹掉 URL 证据。
7. 明确后端失败与“旧任务暂不可查询”分开，后者不能伪报成功或失败。

### 6.5 可选电源与扩展边界

- 并非所有 provider 都有电源接口；不支持者不得伪造 `run-managed` 或 `stopped`（现 `video-provider.md:88-97`）。
- 视频生成确认不自动包含计费开机授权；必须另有本次精确实例/资源与电源范围确认。
- 一个受管监督进程拥有 queue、开机、健康门、任务、关机和最终状态对账；异常也要收尾；同一受管进程内不重复开关机。
- 新 provider 只能新增适配器、注册项、专属文档和离线测试，不得改创作、Prompt、连续性或交付规则；不支持模型/模态时预检停止，不删素材适配后端（现 `:99-108`）。

---

## 7. 当前新增 `video-providers/autodl.md`：详细生命周期总结

### 7.1 实现组件与配置

| 项目 | 当前值 |
|---|---|
| provider ID | `autodl` |
| 串行适配器 | `tools/workflow_video.py` |
| 协议 | `comfy_workflow_v1` |
| 模型 | H3，独立于 provider |
| 实例/电源 | `tools/autodl_instance.py` |
| H3 共享媒体 | `tools/video.py`，仅供适配器内部调用 |
| TTS | Qwen3-TTS 可复用同一实例电源，但不是另一种视频 provider |

见现 `video-providers/autodl.md:5-18`。

无凭证 cloud config 包含 `video_provider`、`protocol`、`base_url`、`workflow_id`、`aspect_ratio`、`megapixels`、`view_path`；不得保存 `token/api_key/authorization/password`。`base_url` 必须为 HTTP(S)，`view_path` 为根路径，比例只能是适配器支持的完整枚举，megapixels 为有限正数。这里的比例和像素是 AutoDL workflow 请求字段，不是 H3 通用能力承诺（现 `:20-46`）。

凭证环境变量（现 `:48-57`）：

- AutoDL 实例：`AUTODL_APP_API_TOKEN`，鉴权头原文发送，不添加 Bearer。
- Zealman workflow：可选 `H3_WORKFLOW_API_KEY`。
- 可覆盖：`H3_WORKFLOW_ID / H3_WORKFLOW_BASE_URL / H3_WORKFLOW_ASPECT_RATIO / H3_WORKFLOW_MEGAPIXELS`。
- TTS SSH：`AUTODL_SSH_HOST / PORT / USER / PASSWORD`。

秘密只在执行时从环境变量或批准的 `.env` 读取，不进入项目、queue、manifest、任务、Prompt、日志或回复；跨源和 HTTPS 降级重定向被拒绝；HTTP 错误正文、Token、SSH 密码和敏感实例字段不回显。

### 7.2 独立电源授权

- `list/status` 是只读联网请求；`power-on/power-off/run-managed` 默认 dry-run，不联网、不读 Token、不启动子进程（现 `video-providers/autodl.md:59-65`）。
- 真实开机是按小时计费的独立基础设施操作。剧本、图片、音色或视频生成确认均不含电源授权。
- 真实执行必须同时有 `--execute` 和与精确实例 UUID 完全一致的确认值；一次授权只覆盖当次实例和生命周期，已结束的 run-managed 不能作为下一次开机凭证。
- 正常制作必须先完成固定 JSON、任务参数和预检，再启动一次 `run-managed` 包住电源和完整当次 queue；不得先真实 `power-on` 再补任务。独立电源命令只用于另行授权的排障。
- `--` 后是无 shell 子进程命令；监督进程不得自行新增任务、改 Prompt 或扩大范围（现 `:63-85`）。

### 7.3 电源协议、状态与重发

- 列表、状态、开机、关机的 API 和载荷在现 `video-providers/autodl.md:87-97` 明确固定；API 不支持无卡开机，工具不伪造该能力。
- 真实 POST 前先查状态：`running` 是关机安全起点，`stopped` 是开机安全起点；过渡/未知状态只对账，不重复 POST。
- POST 结果不明先查状态；只有重新确认原起点，并满足受控退避与连续状态观察条件，才允许重发。不能把响应丢失当作未提交。
- 明确认证/参数错误停止；瞬时查询失败、限流、服务端错误按受控退避，不做重试轰炸。
- `power_on_accepted/power_off_accepted` 只表示请求被接受，最终必须读到真实 `running/stopped`。

### 7.4 健康门

| 场景 | 健康标准 |
|---|---|
| 独立 `power-on --health-url` | 默认 HTTP <500；可指定精确 HTTP 状态或 JSON 标量条件 |
| `run-managed` 配置健康地址 | 默认精确 HTTP 200；404 不就绪；健康请求不发送 AutoDL Token |
| 固定视频入口 | `/api/comfy/status` 且 `running=true` |
| Comfy 检查节奏 | 每 10 秒；独立健康上限 300 秒；不改电源 `--power-timeout` |

HTTP 200 只证明传输成功，不等于 Comfy 业务就绪；`/api/workflow/list` 200 只说明面板可访问，不能替代 Comfy 健康门；`running=false、starting=true` 继续等待，不提交视频（现 `video-providers/autodl.md:99-104`）。

### 7.5 自动关机、对账与退出码

- run-managed 先只读记录初始电源状态。子进程成功、非零、启动失败或被终止时都执行关机，并对账到真实 `stopped`（现 `video-providers/autodl.md:105-109`）。
- 本次从 stopped 启动但开机/就绪失败，也先对账再尝试关机，避免已生效 POST 留下计费实例。
- 若实例原本 running/starting 且子进程从未启动，就绪失败不会误关既有实例。
- 一旦已成功进入子命令，无论初始状态如何，都按本次 `--confirm-power` 授权在退出后关机。
- 子进程日志写 stderr，stdout 保留最终生命周期 JSON；保存真实 `child_exit_code`、规范化 `process_exit_code`、开机和关机结果。
- 子进程通常的非零码原样传播；关机失败自身也返回失败，不能把 `power_off_accepted` 当作 stopped。

### 7.6 提交与防重

协议包括 `POST /api/workflow/generate`，随后通过 result、history、concurrent assets、images 和 output URL 查询/下载（现 `video-providers/autodl.md:111-130`）。

- 本地图片、视频、音频按模型槽位转 data URI；HTTP(S) URL 原样透传；上传前核验 H3 模态、数量、时长和 Prompt 标记。
- 每任务文件最多一次 POST；任务文件已存在或正式输出已存在时拒绝重复提交。
- 任务先以 `submission_pending` 落盘再 POST。
- 响应缺 `prompt_id` 或请求结果不明时进入 `submission_unknown`，保存现场并停止；不得因没有 ID 再 POST。
- 成功取得真实 ID 后才进入 `submitted` 并记录真实 `http_post_count`。
- `poll` 是恢复原任务，不是再次生成；`submit --dry-run` 不联网、不创建任务文件。

### 7.7 排队、轮询与 prompt_id 失效

- `prompt_id` 只在当前 ComfyUI 进程内存 history 中；重启、隔日开机或崩溃后旧 ID 可失效，但这不等于 `/output` 文件被删除，也不等于获得重新生成授权（现 `video-providers/autodl.md:132-138`）。
- 恢复已有任务时先只读找回持久化结果，再与新提交任务共用同一轮询循环；默认每 10 秒，单段上限 900 秒；跨进程恢复传 `resumed=True`。
- result 遇到 HTTP `404|405|501|500` 回退 history。
- `pending=true、results=[]` 是正常排队/生成，继续查 result，不能因 history 尚未出现就判丢。
- result 明确完成/失败才采用其结果；history 只作兼容与故障回退，不覆盖正常 pending。
- history 暂空也继续在同一 900 秒预算内查询，没有恢复任务 0 秒或 120 秒提前判丢。
- result/history 都 500 时可尝试持久化资产找回，并继续在剩余时限查询；到上限仍无结果或唯一证据就停止，不无限等待、不自动重生成（现 `:140-146`）。

### 7.8 持久化资产证据优先级

现 `video-providers/autodl.md:148-158` 固定为：

1. 当前任务文件已保存的 `result_url`。
2. `/api/concurrent/assets` 中同时精确匹配 `promptId + workflowId` 的唯一视频。
3. result/history 仍能唯一证明的当前任务结果。

持久化 URL 必须与任务 `base_url` 同源、位于 `/output/`、有视频扩展名，并拒绝反斜杠与父目录跳转。`/api/images` 只提供路径、大小、mtime 等目录辅助证据；目录只有一个视频、时间接近、时长相近、文件名相似均不能独立认领，多个精确资产或多个候选同样停止。

无法唯一恢复时：

- 保留 `phase=submitted` 和原任务文件。
- 记录 `backend_status=STALE_OR_UNAVAILABLE`。
- 不自动改写为已失败、已完成或可重新生成。
- 只有后端明确返回失败才进入失败状态。

### 7.9 下载、原子落盘与恢复授权

取得视频 URL 后立即保存 `result_url` 到任务文件，再下载；检查媒体流、所需音轨和全量解码，通过后才原子改为正式输出。下载或本地校验失败仍保留 URL，下次恢复直接使用，不依赖已失效 history（现 `video-providers/autodl.md:160-169`）。

**恢复只发送 GET。**任何需要新 POST 的修复都属于新的生成/返修范围，不能由恢复自动触发。

### 7.10 当前能力限制与测试边界

- `seconds` 只接受 H3 4–15 整数秒；Prompt 只能是已保存且通过血缘校验的 H3 成稿（现 `video-providers/autodl.md:171-177`）。
- 当前串行 queue 只使用图片与音频，禁止视频参考；这是当前 queue 合同，不是所有未来 provider 的通用限制。
- dry-run slots 只用于核对真实文件、顺序和 SHA-256，不得伪造 prompt/task ID。
- 离线测试覆盖 provider 选择、版本/哈希锁定、无 POST 恢复、result/history 回退、900 秒/10 秒轮询、精确资产恢复、模糊目录拒绝、URL 保存恢复、健康门和固定入口（现 `:179-189`）。
- **离线测试通过不证明云端可用、不授权开机、不证明真实旧任务已找回。**

---

## 8. `troubleshooting.md`：异常分类与恢复语义

### 8.1 同名同义保留

两版均要求：

- 先读实际文件、状态和日志，不凭聊天记忆。
- 区分工具失败、结构错误、内容错误、实际媒体质量错误。
- 返回最早责任层级；保留最后已确认版本，只新建版本。
- 部分成功先保存真实成功项，只处理失败项。
- 非视频同一缺陷最多自动定向重试一次；视频已返回可播放/可渲染结果后，内容、审美、身份、口型、连续性问题不自动返修。
- 缺陷编号保留 `V` 视觉、`A` 音频、`F` 衔接、`S` 镜头执行、`N` 叙事；确认/并发问题继续使用特殊的 `C-*` 表项（原 `troubleshooting.md:7-32,112-129`；现 `troubleshooting.md:5-25,105-122`）。
- 排障结束仍要求根因、稳定 ID、修复版本、结构检查、媒体可查看/可播放、缺陷证据和受影响下游处理（原 `:160-170`；现 `:152-162`）。

### 8.2 当前新增或改变

| 异常 | 当前处理 | 与原版差异 |
|---|---|---|
| 同一任务瞬时查询失败 | 按原任务 ID 轮询、下载、校验、同源 tail 补抽，不视为新视频调用（现 `troubleshooting.md:12`） | 原版只有一般“先查 ID/状态，不立即重复调用”；当前明确区分技术恢复与新授权。 |
| 提交结果不明且无任务 ID | `submission_unknown` 先按原 provider 唯一对账服务端；无法唯一匹配就停止，禁止盲 POST（现 `delegation.md:82-86`；现 `troubleshooting.md:147-148`） | **新增专门状态与防重证据链**。 |
| 旧任务 ID 查询空/异常/超时 | 查持久化资产和原 URL；不能唯一归属就保留现场，不无限等待、不切换后端、不自动重生成 | **新增**。原版没有持久化证据优先级。 |
| 模型漂移 | 只能在 H3 4–15 秒内拆段或声明能力限制，不得切不存在模型（现 `troubleshooting.md:25,53,146`） | 原版可在已确认兼容模型间处理，并有 Seedance 会员路径；当前没有替代视频模型。 |
| 视频无声 | 先查中文底稿 `{spoken_text}`，再查 H3 成稿每条 `<d>`、字词/词序/说话人/句数和 `(Sx)`；两层完整才检查原生音轨（现 `troubleshooting.md:34`） | **双层诊断**替代单层 `compiled_prompt_file` 花括号检查。 |
| 上段未闭合又准备下一段 | 同一 runner 不并行提交；上一段输出、tail、看图登记和交付未闭合不得编译/提交下一段（现 `troubleshooting.md:114`） | 原版侧重“上一任务仍在生成不得提交未授权新任务”；当前增加真实尾态与反馈门。 |
| Ref2VA tail 角色 | 只有单图 I2VA 才查 `previous_tail_as_start_frame`，Ref2VA 查 `previous_tail_reference`（现 `troubleshooting.md:110`） | **排障字段随新槽位语义更新**。 |
| 本地 `video_edit` | 明确是 Ref2VA 参考重生成；输出时长/比例变化仍判失败（现 `troubleshooting.md:143-144`） | 原版按原生定点编辑理解；当前能力弱化且受 AutoDL 视频参考禁令影响。 |

当前“只补失败项”不再能解释为“对不明提交直接重试”：恢复必须先证明任务身份和输出归属，新增 POST 只能属于当前已确认唯一 SEG（现 `troubleshooting.md:147-148`）。

---

## 9. 规则迁移分类汇总

### 9.1 同名同义保留

1. 真实输入决定 `text_to_video/image_to_video/media_to_video/video_edit` 路由，不得为偏好工具伪造或丢弃素材。
2. 五段式的五项导演职责仍完整存在，但当前只约束中文底稿；因此“职责同名同义、承载层改变”。
3. 每个 SEG 独立编译，逐镜恰好一次，时间轴连续，台词完整，不能临时发明剧情。
4. planned SEAM、observed SEAM、FRM、start/scene/tail、双侧 12 帧、verified/best available cut 体系保留。
5. continuous 真实 tail 与 elliptical 新起点/不变量/允许变化合同保留。
6. KF 是生成前高光目标，FRM 是生成后事实，二者不互替。
7. 完整台词确认、封闭式生成确认、参数变化重确认、用户意图硬门保留。
8. 原生人声、VOICE 稳定复用、无音频输入不等于静音、默认无字幕、最终只交付一个字幕策略版本保留。
9. 每段保存、登记、真实交付后才推进；内容问题不自动重生。
10. 最早责任层级、保留已确认版本、部分成功、V/A/F/S/N 与 C 类问题保留。

### 9.2 规则搬迁

| 规则 | 原位置/形态 | 当前位置/形态 |
|---|---|---|
| 实际视频工具调用 | 主 Agent 建执行包，subagent 调工具 | 固定 `串行执行.json` + `video_run.py` + provider 适配器 |
| 原始可渲染资源证据 | subagent 回传资源字段、URL/短链 | task file 的 `result_url`、真实输出、run-state、来源哈希；主 Agent 收口 |
| 抽帧/探测/拼接/字幕 | 远端 mediakit-only | `local-runtime.md` 选择原 mediakit 或本地 `media.py`；后者可用 ffmpeg/ffprobe |
| 用户交付 | 原平台 `present_files`、Canvas/Workspace 硬门 | 本地宿主真实文件链接/内联预览；有原平台能力时才走远端路由 |
| 视频后端能力 | 隐含在实际工具 schema | `video-provider.md` + 选中 provider 专属文档 |
| 旧任务恢复 | 散见“查任务状态、不要重复提交” | 通用 provider 恢复底线 + AutoDL result/history/assets/result_url 证据链 |
| 分镜参考角色 | `previous_tail_as_start_frame` 等 | 当前 storyboard 增加 `previous_tail_reference/first_frame/last_frame/crowd_reference` 和 `frame_position`（现 `storyboard.md:418-442`） |

### 9.3 语义改变

1. Seedance 多模型与会员例外 → 当前唯一 H3。
2. 单段 ≤15/30 秒 → 4–15 整数秒，并有尾数不足 4 秒的重划规则。
3. 单层实际提交五段式 → 中文导演底稿 + 英文 H3 实际成稿。
4. 每次 1–2 SEG → 每次唯一一个新 SEG，恢复/复用不占新数量。
5. 必须异步 subagent → 固定 runner；无 subagent 时主 Agent 可启动同一进程。
6. continuous tail 一律称硬首帧 → Ref2VA 通常仅参考，单图 I2VA 才是硬首帧。
7. 原生 `video_edit` → Ref2VA 参考重生成，能力语义弱化。
8. FRM/SEAM 主要在交付后补记 → 当前段交付前完成必要看图与登记，问题仍不自动返修。
9. 工具失败主要按任务状态处理 → 新增提交不明、旧 ID 失效、持久化归属和只读恢复状态机。
10. 原平台 ASR → 当前本地无 ASR，字幕从锁定台词稿整理并人工对轨。

### 9.4 当前新增

- 真实 h3-prompt-writing Skill 调用、`h3_conversion`、双文件双哈希和两层语义复核。
- H3 模式、媒体槽位、精确数量/时长、音频必须有视觉输入。
- `<d>` 台词、稳定 `(Sx)`、媒体标签映射、成稿禁 `【】`。
- 固定 queue、`generate/recover/reuse`、执行锁、run-state 和固定日志。
- provider 注册、协议、适配器版本/SHA-256、cloud config SHA-256 和确认绑定。
- AutoDL 独立电源授权、精确实例 UUID、业务健康门、自动关机/stopped 对账。
- `submission_pending/submission_unknown/submitted/STALE_OR_UNAVAILABLE` 等恢复事实。
- 持久化资产精确归属、URL 先存、全量解码、原子落盘、恢复只发 GET。
- 离线测试与“不证明云端可用/不授权电源/不证明找回”的边界。

### 9.5 原版独有或当前弱化

1. **原版独有**：Seedance 2.5 的 25–30 秒长段、2.0/2.5 不同参考总时长和会员额度提示。当前不适用，不应误写成创作质量规则被删。
2. **当前能力弱化**：`video_edit` 不再是原生定点编辑，而是参考重生成；当前 AutoDL queue 还禁止源视频参考。
3. **当前角色隔离放宽**：不再绝对要求 subagent，主 Agent 可启动固定 runner；由机器防重和哈希合同补偿，而非原有 Agent 权限模型原样保留。
4. **当前本地能力缩减**：无本地 ASR，也无本地 Canvas/Workspace 等价物；必须如实报告能力，不可伪造。
5. **当前模型选择收窄**：没有第二个视频模型或第二个已注册 provider；文档的“可扩展”不代表现有多选。
6. **当前 AutoDL 可执行模态收窄**：模型层 Ref2VA 可接受视频，但固定串行 queue 只接受图片和音频。

---

## 10. 风险、矛盾与缺失

### 10.1 高优先级：通用视频输入合同与 AutoDL queue 不一致

- 现 `video.md:34-35,218-219,297-298` 允许存在视频输入时走 `media_to_video -> Ref2VA`，并把 `video_edit` 的源视频作为 `<Video N>`。
- 现 `video-providers/autodl.md:126` 描述适配器可处理本地视频槽位，但 `:176` 又明确“串行 queue 当前只使用图片与音频，禁止视频参考”。
- 固定 `串行执行.json` 的逐段字段也只有有序 `images`、`audio`，没有 `videos`（现 `delegation.md:22-27`；现 `tools/video_run.example.json:14-35`）。

**行为影响**：模型层支持视频参考不等于当前 AutoDL 固定入口可执行。依赖上一段完整视频、外部视频参考或源视频编辑的任务应在预检停止并说明限制，不能删掉源视频伪装成普通 Ref2VA，也不能声称已经完成原生编辑。建议主文档把该限制前移到 `video.md` 的工具路由和 `video_edit` 小节，避免执行者到 provider 层才发现断层。

### 10.2 高优先级：当前故障文档仍残留 ASR 指令

- 现 `local-runtime.md:27,69` 明确本地无 ASR，SRT 从锁定台词稿整理并试听对齐。
- 但现 `troubleshooting.md:41,133-135` 仍写“重新 ASR”“查看 alignment 的 ASR 字段”“对最终音轨重新 ASR 对齐”。

**行为影响**：本地执行者可能尝试调用不存在的 ASR，或把估计时间写成 ASR 证据。应把这些残留改为“按锁定台词稿重新人工对轨/使用宿主真实提供的 ASR（若存在）”，并明确无 ASR 时不得伪造 alignment。

### 10.3 中优先级：电源“不按 SEG 重复开关机”措辞需限定作用域

- 单段合同要求每次 run 最多一个新 `generate`，段退出后必须看图、登记、交付，再重新编译和确认下一段（现 `delegation.md:3,56-69`）。
- 通用 provider 又写明“下一新 SEG 的新进程与电源授权……重新闭合”（现 `video-provider.md:94`）。
- 但现 `video-providers/autodl.md:85` 写“视频正常 SEG 间不重复开关机”，现 `tools/README.md:75` 也写“不按 SEG……重复开关机”；与此同时 run-managed 结束要自动关机（现 `delegation.md:54`）。

**行为影响**：若把“不按 SEG 重复开关机”理解为跨多次单 SEG 运行也不关机，会与“每次退出关机”和“下一新 SEG 重新电源授权”冲突。较一致的理解应是“同一受管进程/同一 queue 内不按条目重复开关机”；建议明确写出这一作用域，避免长视频每段到底是否重新开机产生歧义。

### 10.4 中低优先级：确认 Ref 仍有“派发 subagent”残留

现 `interaction-ask-video-clarification-ref.md:88` 仍写“才能派发 subagent 开始视频生成／编辑”，而现 `delegation.md:3` 和 `local-runtime.md:68` 允许没有 subagent 时由主 Agent 启动并等待同一固定脚本。

**行为影响**：授权本身没有冲突，但执行主体表述未完全同步。建议改为“才能启动受控固定执行器（有 subagent 时由其启动）”。

### 10.5 低优先级：`video.md` 步骤编号残留

现 `video.md:466` 写“第一部分步骤 10 的抽帧与连续性流程对轻量模式不适用”，但当前第一部分步骤 10 已是整集准出/轻量交付，旧版“交付后进入第二部分”的编号已不存在于同一位置（现 `video.md:45-54`）。

**行为影响**：属于交叉引用陈旧，可能误导读者寻找错误步骤；不影响第二部分本身“轻量不创建 FRM/SEAM”的明确规则。

### 10.6 需要持续区分的非矛盾点

1. **观察提前不等于自动返修**：当前在交付前看图、登记 SEAM，但主观缺陷仍不阻断 best available 交付；技术真实性和可解码问题才阻断。
2. **五段式未消失**：它从实际提交层搬到中文导演源；英文 H3 成稿采用另一套结构是指定设计。
3. **本地允许 ffmpeg 不是回退到任意脚本**：只有批准的 `tools/media.py` 等价链路可以调用 ffmpeg/ffprobe；不得冒称远端异步任务。
4. **provider 可扩展不代表已有多个后端**：当前只有 AutoDL。
5. **prompt_id 失效不等于输出丢失**：持久化资产可能仍在；也不等于获得重新生成授权。
6. **离线测试不是云端验收**：电源、云端健康、真实任务恢复仍须现场证据和独立授权。

---

## 11. 可直接用于主文档的关键短引

> 原：“五段式是一份视频生成 Prompt 的五层信息合同，不是五个镜头，也不是五个时间段。”（原 `video.md:258-262`）

> 现：“五段式……约束第一层导演编译底稿，不直接约束 H3 成稿结构。”（现 `video.md:329-335`）

> 现：“更换 provider 不等于更换模型，也不授权改写剧本、分镜、Prompt、SEG、时长或画幅。”（现 `video-provider.md:13`）

> 现：“恢复不得产生新的生成 POST；不能因为旧 ID 查询为空、接口异常或超时就重提。”（现 `video-provider.md:80-86`）

> 现：“重启、隔日开机或崩溃恢复后，旧 ID 可以失效；这不等于 `/output` 中仍存在的文件被删除，也不等于可以重新生成。”（现 `video-providers/autodl.md:134-138`）

> 现：“串行 queue 当前只使用图片与音频，禁止视频参考；这是当前队列合同，不是所有未来 provider 的通用限制。”（现 `video-providers/autodl.md:171-177`）

> 现：“离线测试通过不证明云端服务可用，不授权开机，也不证明任何真实旧任务已找回。”（现 `video-providers/autodl.md:189`）

---

## 12. 最终判断

当前版在**提交前血缘、单段授权、真实尾态反馈、执行环境锁定、云端防重恢复和计费电源清理**方面显著强于原版；原版的优势主要是 Seedance 2.5 长段、原生视频编辑语义、原平台 mediakit/ASR/Canvas 一体化和强制 subagent 角色隔离。

当前最需要优先澄清的不是创作规则，而是三处执行合同：

1. AutoDL 固定 queue 禁止视频参考，与通用 `media_to_video`/`video_edit` 描述之间的可执行边界。
2. 本地无 ASR 与 troubleshooting 残留 ASR 指令之间的冲突。
3. 单 SEG 受管运行、每次退出关机与“不按 SEG 重复开关机”措辞之间的作用域。

除这些残留外，主体迁移关系清晰：**导演事实和连续性规则保留，模型编译改为两层，执行改为固定 runner，云端差异下沉到 provider，故障恢复从“不要重复调用”升级为可审计的原任务证据链。**
