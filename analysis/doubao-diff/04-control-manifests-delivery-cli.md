# 专题 04：控制、交互、清单、交付、本地宿主与 CLI

> 对比原版 `<doubao-root>` 与当前版 `<drama-root>`。按 2026-11-25 磁盘内容静态分析。

## 一、总体结论

1. **完整/轻量模式、逐集串行、阶段确认、revision 与真实依赖失效、数据卡和资产事实源、FRM/SEAM、每集唯一成片及字幕策略均保留。**
2. **真正改变执行语义的是 H3 单 SEG 串行链**：每 SEG 4–15 整数秒；一次确认/runner 最多一个新 SEG；中文五段式导演底稿必须真实调用 `h3-prompt-writing` 转为英文 H3 成稿；provider、适配器及配置被冻结。
3. **当前新增 `references/local-runtime.md`，用本地同步 CLI、宿主确认和真实文件交付替代远端异步工具、Canvas 与 `present_files`。** 这是工具映射，不扩大授权、不取消阶段确认。
4. **规划时长改为预估区间，真实执行时长与最终实测时长分层保存。** 不再把规划预估值强制等于分镜或成片时长。
5. **十份 CLI 文档中六份完全相同；CLI 目录仍描述原平台远端画布，并非当前本地 CLI。**
6. **真实向后兼容断点：当前 `drama_lint.py` 删除了 `--fix`、`--changed-file`。** 旧调用会由 argparse 判为未知参数，通常退出码 2，而不是继续忽略参数。
7. 当前仍存在少量未完全清理的旧绝对措辞：`interaction.ask`、Canvas/present_files、mediakit ASR、禁止 FFmpeg 等，与本地覆盖规则并存，需要按 `SKILL.md` 和 `local-runtime.md` 的权威优先级解释。

分类口径：完全相同；仅措辞/搬迁；语义改变；新增；原版独有/当前删除或弱化。

## 二、逐文件总表

| 文件 | 分类 | 核心结论 |
|---|---|---|
| `references/control-contracts.md` | 主体保留 + 语义改变 + 新增 | 三种独立授权、七态阶段事务、真实意图确认、revision/下游失效均保留；视频改为 H3、单 SEG、双层 Prompt、真实尾态串行 |
| `references/interaction-ask-video-clarification-ref.md` | 主体保留 + 本地新增 | 标准 `interaction.ask` JSON 完全相同；新增本地确认映射；确认范围从连续 1–2 SEG 改为当前一个 SEG |
| `references/manifests.md` | 大量新增 + schema 语义改变 | 新 provider/adapter、群众、双层 Prompt、串行 run-state；时长预估/实测分层；七种状态值未变 |
| `references/delivery.md` | 主体保留 + 本地执行改变 | 唯一最终视频与字幕策略不变；新增同步 media、人工试听和本地 burn；远端轮询细节弱化 |
| `references/local-runtime.md` | 当前新增 | 定义 Claude Code/Codex/baocode 的本地工具、凭证、确认、provider、执行和真实交付合同 |
| `references/cli/README.md` | 仅措辞/搬迁 + 原状态说明删除 | 初始化、XML、Item/Frame、path、source_ids、原子性均保留；删除“已上线、不再 mock”等部署状态 |
| `references/cli/ls.md` | 完全相同 | 双版 1–65 |
| `references/cli/tree.md` | 完全相同 | 双版 1–65 |
| `references/cli/get.md` | 完全相同 | 双版 1–101 |
| `references/cli/create.md` | 仅措辞/搬迁 | 示例资源和预览宿主调整；原平台 `present_files` 卡片交付规则保留 |
| `references/cli/create-batch.md` | 完全相同 | 双版 1–160 |
| `references/cli/update.md` | 完全相同 | 双版 1–104 |
| `references/cli/update-batch.md` | 完全相同 | 双版 1–116 |
| `references/cli/workspace-create.md` | 措辞修正 | 创建、原始 ID、非幂等、present_files 前置不变；删除错误的“唯一零 workspace ID 命令” |
| `references/cli/get-workspace.md` | 措辞修正 + 弱化旧错误动线 | 消除“每轮先查询/重复创建幂等”与默认直接创建规则的冲突 |
| `scripts/drama_lint.py` | 实际兼容参数删除 | 原版 3104–3111 有兼容参数；当前 1528–1533 仅剩 `skill_root`、`--project-root`、`--stage` |

## 三、控制、确认、revision 与失效

### 3.1 三种独立授权

`control-contracts.md` 原版 40–53、当前 32–45：

- **项目执行确认**：仍为 `project_execution_confirmation`，选项 `proceed_project|revise_project`，只授权项目制作，不授权媒体生成。
- **视频生成确认**：独立取得；当前每个新 SEG 都单独确认。
- **成片拼接确认**：仍为 `final_assembly_confirmation`、`proceed_assembly|revise_assembly`。

当前拼接门有所加强：原版 49 要求全部 SEG 逐个交付，当前 41 明写它们必须“已真实生成并逐段交付”，且单段生成确认不能替代拼接确认。

实际影响：项目确认、当前 SEG 的 generate、最终拼接三者不可互相推导。尤其目标为 `video` 时不能把普通视频阶段确认伪写成成片拼接授权。

### 3.2 完整/轻量模式

- 完整模式逐集串行、目标阶段限制、KF 硬门：原版 `control-contracts.md` 82–92，当前 74–84。
- 轻量仍只有规划页 `generate` 和最终普通确认，中间阶段为 `merged`；不创建数据卡、分镜 JSON 等完整配套文件。
- 内部十五列分镜不能缩水为五列预览。

语义变化：
- 原版 `SKILL.md` 82–88：Seedance 2.0 ≤15 秒，2.5 ≤30 秒。
- 当前 `SKILL.md` 85–91：唯一 H3，每 SEG 4–15 整数秒。
- 当前 `control-contracts.md` 86 把连续性风险扩展到人物、群众和场景。

当前轻量也必须保存“导演底稿 + H3 成稿”两层 Prompt，见当前 `manifests.md` 215、`SKILL.md` 258。

### 3.3 阶段事务与真实意图

- 状态枚举仍为 `pending|in_progress|awaiting_confirmation|confirmed|merged|invalidated|blocked`。
- 七步阶段事务：原版 `control-contracts.md` 100–108，当前 92–100。
- 普通阶段确认仍必须结合最新交付、当前询问和用户整句判断真实意图，不使用封闭关键词白名单：原版 107，当前 99；当前 `SKILL.md` 195 再次明确。
- “好的”“继续”“OK”等只是可能成立的非穷举示例，不是自动关键词；已读、沉默、模糊、条件式、带修改意见、否定和系统生成内容均不算确认。
- 视频生成仍需标准 `generate`，普通聊天肯定在原平台不能替代工具确认；本地无专用工具时则按 `local-runtime.md` 的明确聊天确认合同处理。

当前 `control-contracts.md` 98 将统一“生成一个就交付/上画布”细化为：资产/KF 逐项交付；视频每个 runner 退出后由主 Agent 看图、对账、登记、交付，然后才能编译下一段。

### 3.4 revision、确认记录与下游失效

主体规则保留：

- 每次确认追加真实 `用户确认记录.jsonl`，含阶段、revision、purpose、result、user_message、带时区时间、full/incremental 和影响范围。
- revision 变化后旧确认不能自动覆盖新范围。
- `supersedes_confirmation_ids` 用于明确替代关系。
- 已确认版本不覆盖，新版本递增 `_vNN`。
- 下游仅按真实依赖失效，未受影响产物继续复用。
- 回滚仍使用 `scripts/drama_rollback.py`；分集需 `--episode ep_N`，跨后续集需显式 `--cascade-later-episodes`。

当前新增/调整：

- 当前 `manifests.md` 217–234 示例加入 `confirmation_transport:"host_tool"`；普通确认也要求记录真实确认调用 ID。
- 本地聊天确认以唯一 `local:` ID 填 `interaction_ask_call_id`，同时标记 `confirmation_transport:user_message`，不得伪称工具调用。
- 当前 `control-contracts.md` 131–134 新增增量确认例外：仅细调非锁定的规划预估区间，本身不使剧本、分镜、视频或成片失效。
- 用户锁定的精确时长、核心事件、集数或交付边界变化，仍按真实影响失效。
- 视觉替换触发失效的资产范围由原版 126 的 CHR/SCN/PROP/STYLE 扩为当前 121 的 CHR/CRD/SCN/PROP/STYLE。

### 3.5 版本与资产事实源

原版 `manifests.md` 155–162、当前 150–157 基本一致：

- `project_data_card.json` 是身份、关系、状态、音色和资产归属事实源。
- `asset_registry.json` 是共享资产版本事实源。
- `asset_usage_ep_N.json` 是分集采用快照。
- 下游只采用 approved 版本。
- `项目设定卡.md` 只是数据卡的用户可读投影，不是第二事实源。

## 四、交互文档差异

### 4.1 保留内容

原版与当前 `interaction-ask-video-clarification-ref.md`：

- mainagent/subagent 权限边界不变。
- 默认直接给完整方案，不询问视频内容。
- 商业宣传片/广告/带货且无相关素材，仍是唯一素材询问例外。
- 禁止 `interaction.request_action`。
- 标准 JSON 双版 61–84 完全相同：`question_id:"video_confirm"`；`display_option` 仅 `generate|cancel`；`multi_select:false`；生成说明包含“高消耗生成”。
- 完整参数先普通文本展示，再单独确认。
- 用户主动修改后重新展示完整参数，不只确认变化字段。

### 4.2 语义改变与新增

- 当前 3 新增本地映射：固定工具名和结构只适用于原平台；本地仍须展示完整参数、获得明确选择并保存真实确认。
- 原版“每次实际提交生成前”改为当前 29 的每个新生成 SEG；一次只覆盖当前一个 SEG。
- 原任务轮询、下载、补抽 tail 不新增确认。
- 当前 41 要求同时展示视频模型和视频生成后端的自然名称，但不展示内部适配器/路由字段。
- 当前 90 将“subagent 回传后由 mainagent 完成 present_files/CLI”改为：当前 SEG 参数绑定；provider、协议、适配器冻结；运行退出后看图、登记、交付；本地展示和 Canvas/CLI 按 `local-runtime.md`。
- 失效条件增加模型/provider；原版单列的“数量”不再必要，因为当前固定一次一个 SEG。
- 当前 92 明确下一新 SEG、返修、重生均需新确认；拼接独立；恢复不能借名新发生成。

### 4.3 删除/弱化与风险

- 原版 13 关于“旧版逐项追问/不限题数等规则废止”的历史警告被当前删除，但当前 9–13 仍保留主规则，不能解读为恢复内容问卷。
- 当前 27、88、96 仍有“必须 `interaction.ask`、不得普通聊天”的绝对措辞，与当前 3 和 `local-runtime.md` 62–67 的本地聊天确认并存。
- 应按权威覆盖理解为：**原平台禁止普通聊天；本地没有确认工具时允许符合合同的明确聊天确认。** 但文档最好进一步清理，避免执行者误判。

## 五、manifest、目录、schema 与状态

### 5.1 基本不变

`manifests.md` 原版 12–24、当前 14–26：

- 统一项目根路径。
- 项目级/分集 JSON 分工。
- 数据卡事实源。
- KF 与真实生成后的 FRM 不混用。
- 相对路径。
- `_ep_N`、`_vNN`。
- `project_manifest` 与轻量空路径规则：原版 141–167，当前 149–175。
- 状态 schema 和七种状态值：原版 169–207，当前 177–215。
- 共享资产 approved 复用规则。
- 有视觉输入时选择 `image_edit`，无有效参考才用 `image_gen`。
- `episode_seams` 的 continuous/elliptical、真实尾帧、verified 语义。
- 轻量不创建完整接缝层。
- storyboard、asset_usage、keyframe_manifest 的主体结构。
- KF/FRM 不回写覆盖：原版 880–884，当前 900–904。
- continuity 的 FRM/SEAM schema：原版 1047–1090，当前 1135–1178。
- delivery manifest 的 assembly/subtitle/outputs/status 主体。

### 5.2 新增目录和命名

当前新增：

- 共享群众与命名：`manifests.md` 64–66。
- 分集群众状态：102–103。
- `编译底稿_SEGxxx_vNN_ep_N.md`：115。
- storyboard segment 的 `crowds:[]`：792。
- 数据卡 `crowds:[]` 与 CRD 批准门：489、513、517。
- asset registry 的 CRD/crowd：535–536。

最终成片目录、字幕 SRT、ASR/烧录/媒体探测报告、无字幕版/字幕烧录版命名，双侧基本相同：原版 116–129，当前 124–137。

### 5.3 规划预估、执行总和与最终实测

这是跨多个 schema 的系统性语义改变：

- 原版 `project_script_manifest` 294–305：`total_duration_s`、每集 `duration_s`。
- 当前 300–307：`estimated_total_duration_range_s/display`、每集 `estimated_duration_range_s/display`。
- 当前 326 明确不与详细剧本、分镜、成片实际时长相等校验。
- 数据卡原版 363–365 的 `episode_durations_s`，当前 371–379 改为预估区间和显示数组。
- episode manifest 原版 588–590，当前 606–608 同样改预估值。
- `script_contract` 原版 616–618，当前 634–636 改预估区间，且不作字数或下游时长门。
- 当前 732：storyboard `duration_s` 是真实执行总和；只有 `user_locked` 才与锁定执行时长相等。
- 当前 1182：delivery 的 `duration_s/display` 必须来自最终真实媒体，而非规划预估。

实际影响：迁移旧项目或编写 lint 时，不能继续把所有 `duration_s` 当同一种语义。

### 5.4 旧状态镜像兼容说明删除

- 原版 171：旧项目镜像状态可保留但不参与判断；当前 179 删除。
- 原版 1144：episode manifest 旧镜像兼容说明；当前 1232 删除。

七种状态枚举和唯一状态源未变，但旧项目兼容说明有所弱化。

### 5.5 数据卡 lint 增强

- 原版 497：只检查数据卡是否存在，不解析内容。
- 当前 515：检查可确定结构、引用与群众声明合同。

仍不评价关系、声音、视觉事实或英文转译的主观质量。

### 5.6 FRM/SEAM 与 manifest 引用

主体保持：

- KF 是生成前高光目标；FRM 是生成后事实。
- 第一段不伪造历史 tail。
- 非首段 `continuous` 必须消费上一段真实 tail FRM。
- `elliptical` 明确时间/空间/认知跳跃，不强制传 tail。
- planned SEAM、observed seam、verified cut/best available cut 分层。
- 视频进入成片必须覆盖全部 Storyboard SEG。
- EPSEAM 及连续性交接规则保留。

变化集中在 Prompt 引用：原版一层 Prompt 检查，当前 190 等改为导演底稿、H3 成稿及二者血缘检查。

## 六、H3、provider、单 SEG 与 run-state

### 6.1 视频执行链

原版 `control-contracts.md` 110–122 是一层五段式 Prompt、一次预检/终检和 Seedance 批次执行。

当前 102–117 改为：

1. 当前 SEG 中文五段式导演底稿；
2. 主 Agent 真实调用 `h3-prompt-writing`；
3. 保存 H3 英文成稿；
4. 检查 H3 结构、人工语义回读；
5. 展示当前 SEG 两张确认表；
6. 一次 generate；
7. 受管 runner 运行；
8. 真实尾态落盘、看图、登记、交付；
9. 再编译下一段。

当前 117 新增说话人与 `(Sx)` 映射人工核验；H3 固定字段、槽位、`<d>` 台词语法进入客观校验。

### 6.2 批次授权

- 原版 `control-contracts.md` 143：一次可覆盖连续 1–2 个 SEG。
- 当前 138：一次确认/运行最多一个新 SEG。
- 新增、返修、重生均重新确认。
- 原任务恢复、轮询、下载、补抽 tail 不重新确认。
- 完整阶段确认门仍保留。

### 6.3 `video_manifest` 新合同

当前 908 起：

- 固定 `串行执行.json`。
- 未生成段不得伪造 tool/output/tail/candidate。
- 示例 925–971 新增：`video_provider`；adapter version/SHA；cloud config SHA；`execution_mode:serial_real_tail_chain`；`run_plan_file/sha256`；`confirmation_source/transport`。
- segment 新增 `crowds`、`request_snapshot_file`、`h3_mode`、provider、`director_draft_file`、`h3_conversion`、`h3_structure_verified`、真实 task_id。
- 参考输入增加 adopt/exclude 事实。
- 当前 1067–1075 定义双层 Prompt、真实 Skill 血缘、哈希、首尾帧/真实 tail 角色、群众 dry-run slots、派生音频及两层 preflight。
- 原版 1021–1028 的 1–2 SEG 和重叠范围 supersede，当前 1077–1085 改为 `start=end`、数量 1，只 supersede 同 SEG 旧确认。
- 当前 1081 要求确认绑定冻结 queue 字节；参数、素材、provider、Prompt 等变化重新预检确认。
- 当前 1087–1114 新增 run-state，含输出/tail 哈希、tail 来源视频哈希、confirmation ID、`manifest_modified:false`。
- 当前 1116–1118 区分确认来源与通道。
- 当前 1120：`video_edit` 是 H3 无原生编辑时按 Ref2VA 参考重生成，不再等同原版直接定点编辑语义。

原版 937 的 `membership_notice` 从当前示例删除。

原版 1015 的 candidate 定义含“完成即时交付”，当前 1061 改为“媒体检查通过”。这不代表逐段交付门取消，因为当前 control 138 和 `SKILL.md` 192 仍明确要求逐段交付。

## 七、delivery、字幕与真实文件交付

### 7.1 保持不变

原版 `delivery.md` 19–25、当前 21–27：

- 每集只交付一个最终视频。
- 内容/审美/口型/连续性问题不阻断客观交付，也不自动重生。
- 拼接不授权重生。
- 完整模式只拼接 confirmed/accepted 片段。
- 进入拼接需 `proceed_assembly`。
- 最终音轨变化会使字幕产物失效。
- 字幕默认关闭。
- 模型禁止直接生成画面字幕。
- 字幕关闭交无字幕版；字幕开启只交字幕烧录版。
- SRT、JSON、内部母版、报告不进入正式 outputs。
- 内部裁剪片、拼接中间件、字幕测试样片不正式展示。

### 7.2 当前新增本地路径

当前 3 的总覆盖：使用同步 `tools/media.py` 和宿主文件交付；不要求远端 task、Canvas、present_files；无 ASR 时人工试听；其余质量要求继续适用。

当前 158、169–176、192、355–366：

- 无 ASR 时人工试听。
- 报告须 `method:manual_listening`。
- 保存真实音轨 SHA、逐句文本、时间、说话人和复核证据。
- 不得冒充 ASR。

当前 293 新增：

```bash
python tools/media.py burn <mp4> <srt> <out> --size 36 --pos lower_third
```

横屏可用 `--pos bottom`；字号为像素，ASS PlayRes 等于实际视频尺寸，lower_third 的文字中心位于高度 70%。

当前 280 修正循环时长依据：期望来自实际采用 SEG、裁剪切点和时间线；delivery duration 保存最终实测。0.5 秒、0.01 比例、0.1 fps 容差保留。

### 7.3 声音语义

- 原版 25：Seed Audio 始终承担声音身份。
- 当前 27：完整模式使用 approved VOICE；轻量可只使用 voice_anchor；不新增音色生成。
- 局部修复同样从原版 52 的 Seed Audio 改为当前 54 的 VOICE。

### 7.4 删除/弱化

- 原版 72 的 9 分钟轮询继续规则在当前 74 删除。
- 原版 190 的临时 URL 24 小时、精确 normalized 字段、failed/canceled 细节，当前 192 泛化为同一 task_id 查询终态、不伪造。
- 属于原远端平台细节弱化，不是本地媒体检查门取消。

### 7.5 当前内部措辞冲突

1. 当前 157 仍写“不使用 FFmpeg 手动烧录”，318 仍写“不得切换 FFmpeg”，但 `local-runtime.md` 24 明确定义 ffmpeg/libass，delivery 293 又提供本地命令。
2. 当前 229–260 七步流程仍大量按 mediakit ASR 单路径书写，本地分支依赖顶部、176、192、355 的覆盖。
3. 当前 322 仍笼统称必须 ASR 原始信封，与人工试听路径不完全一致。
4. 当前 70、132、134 仍保留非 Mobile Canvas/present_files 文案。
5. 当前 `manifests.md` 1224 仍写 basic QC 由“真实 mediakit 探测”生成，未完全宿主中立。

实际执行应按 `SKILL.md` 41–43 和 local-runtime 的优先级处理，但这些残留是明确文档维护风险。

## 八、当前新增 `local-runtime.md` 详细总结

### 8.1 权威与 CLI 合同（1–7）

- 本地范围：Claude Code、Codex、baocode。
- 本文件是本地工具执行、秘密处理和交付权威。
- 方法论中的原工具枚举仍保留，供 `drama_lint.py` 校验。
- 所有本地 CLI stdout 为单行 JSON。
- 退出码：0 成功，1 运行/业务失败，2 参数错误。
- 凭证只从环境变量或批准的 `.env` 读取。
- 不写入项目、manifest、快照、Prompt，不回显真实值。

### 8.2 工具映射（11–31）

| 原枚举/操作 | 本地实现 |
|---|---|
| `image_gen` / `image_edit` | `tools/image.py`，知脑中转 gpt-image；有 `--ref` 自动 edits |
| 所有视频模式 | `tools/video_run.py` 读取固定 `串行执行.json` |
| 中文底稿转 H3 | 真实 `Skill(skill="h3-prompt-writing", ...)`，禁止自行仿写 |
| TTS | Qwen3-TTS，受管任务 |
| frame/probe/trim/concat/burn | `tools/media.py` |
| cut-audio/fit-image/erase | `tools/media.py` 对应子命令 |
| ASR | 无本地 ASR；从锁定台词整理 SRT 并按实际音轨对齐 |
| 上传 | `tools/upload.py`；OSS 未配置时明确报错并先本地交付 |
| design-cli/Canvas/Workspace | 无本地等价物；`references/cli/` 只描述原平台 |
| `present_files` / `file_presents` | 宿主真实文件链接或内联预览 |
| `interaction.ask` | 当前宿主真实确认方式 |

第 33 行特别规定：JSON 的 `tool/tool_mode` 仍写原枚举；操作日志中的媒体工具写 `mediakit`；lint 禁用词为 `ffmpeg`、`text_to_image`。因此“实现使用 ffmpeg”和“manifest 工具枚举写 mediakit”是有意分层，不应擅自改枚举。

### 8.3 凭证与电源（35–45）

`.env` 查找顺序：`--env-file` > `$DRAMA_ENV_FILE` > `tools/.env` > skill 根 `.env`。环境变量优先。图片、搜索、OSS 变量集中列出；视频/TTS 专属凭证只读 provider 部署文档。

需要计费电源的 provider 必须另行明确授权；视频或 TTS 生成确认不自动包含开机。

### 8.4 模型/provider 分离（47–60）

- 模型与执行 provider 分开确认、记录。
- queue 显式保存 `video_provider`。
- 适配器版本/SHA 由真实安装代码预检计算并绑定 run-state。
- runner 后端中立，不包含云平台 endpoint、凭证或电源逻辑。
- 错误、超时、额度或偏好不得导致静默切换模型/provider。
- 用户可见生图模型为 gpt-image；视频统一 H3。
- 每 SEG 4–15 整数秒。
- AutoDL 是 provider，不是模型名。
- TTS 只产约 5 秒音色样片；视频人声默认由 H3 原生生成。

### 8.5 本地确认与执行（62–70）

- 优先使用宿主真实确认工具，如 Claude Code 原生确认、Codex `request_user_input_async`。
- 无专用工具时展示“按要求生成（高消耗）/暂不生成”，等待明确回复。
- 沉默、模糊、预选、历史确认无效。
- 项目执行、视频、拼接仍保留各自选项和授权范围。
- `confirmation_source=batch_preview|planning_preview` 表示工作流来源。
- `confirmation_transport=host_tool|user_message` 表示通道。
- 聊天确认生成唯一 `local:` ID 写入 `interaction_ask_call_id`，不冒充工具调用。
- 同次规划/视频/拼接引用同一确认记录 ID。
- 有 subagent 时其启动并等待 runner；无 subagent 时主 Agent 启动同一进程。
- 内层仍是受管 runner。
- media 为同步命令，以退出码、实际文件和 probe 为证据，不伪造远端 task ID。
- 无 ASR 时人工试听；未实现的混音等能力须如实说明。

### 8.6 本地真实交付（72–78）

- 图片/视频必须存在、非零、可解码。
- 视频另需可渲染流和全量解码。
- 资产/KF 即时交付。
- 视频每段退出、看图登记后交付。
- 正式交付必须通过宿主真实文件链接或内联预览逐项展示，并核对展示结果。
- 未展示路径不算已交付。
- 客观失败不得宣布交付。
- 内容/审美/口型/连续性问题不阻断 best available，也不触发自动重生。
- 原文件不因展示复制或改写。
- 未经用户授权不上传外部服务。
- 远端 workspace/canvas 字段留空，不能用本地路径或文件 ID 填充。
- 默认只展示应交付图片、音色样片和视频；文档按用户要求提供。
- 内部 Prompt、JSON、日志、快照、中间视频不自动展示。

## 九、Workspace、Canvas、Mobile 与 present_files

### 9.1 原版合同

原版 `SKILL.md` 47–52：

- 非 Mobile：规划确认后按目标初始化 Workspace；图片/视频生成一个就 Design CLI 写入、真实 ID `+get` 回读，并由主 Agent `present_files`。
- 两条分支都成功才算非 Mobile 画布交付完成。
- Mobile：仅 `present_files`，禁止访问 Workspace/Canvas。
- 音频、文档、JSON、Prompt、报告不上画布。
- 成片只对一个最终版本执行双通道。
- Markdown、裸 URL、路径和工具自带预览不能替代原平台交付工具。

### 9.2 当前迁移

当前 `SKILL.md` 41–43：

- 本地路由优先于其他 Ref 的远端工具硬门。
- 本地无需 Canvas/Workspace 或 present_files 前置。
- 原版远端画布只有在实际具备客户端、平台授权和展示工具时才启用。
- 本地工具替换不扩大授权，也不改变阶段合同。

当前 53–56 保留：Mobile 判定；只有图片/视频上 Canvas；展示不等于 approved/accepted/confirmed；没有真实资源或正式交付工具时保持未交付。

当前 182 仍有“present_files/file_presents、禁止纯 Markdown 链接/纯路径”等原平台措辞，但 41 和 local-runtime 72–78 明确允许本地真实文件链接/内联预览。应理解为不同宿主分支，而不是当前本地也禁止文件链接。

### 9.3 风险

当前 `control-contracts.md` 224 仍保留原版 229 的非 Mobile Canvas/CLI 硬门。与 local-runtime 同时阅读时，必须遵循当前 SKILL 的本地优先级；否则可能把合法的本地文件交付误判为违规，或反向虚构远端 Item/Workspace。

## 十、Design CLI 十文档详审

### 10.1 六份完全相同

| 文件 | 行号 | 保留合同 |
|---|---:|---|
| `cli/ls.md` | 1–65 | 直属目录、Item/Frame 摘要；path 默认 `/`；根级 brief；空容器 |
| `cli/tree.md` | 1–65 | 整棵树，不含对象；tree 片段需自行补 `/` 拼完整路径 |
| `cli/get.md` | 1–101 | item/frame IDs 至少一个、合计最多 10；Frame 全成员回读；update 不改内容；读回 source_ids 不可原样用于 create |
| `cli/create-batch.md` | 1–160 | HTML 顶层；逐项 get/present；共享 source_ids 落位；最多 50、1MB、全成或全败 |
| `cli/update.md` | 1–104 | 只 patch 顶层 brief/path；brief 修改前先 get 证实被动编辑；其他字段无效；内容变化重建 |
| `cli/update-batch.md` | 1–116 | 同 ID 一次，后项静默覆盖前项；50/1MB/原子性 |

这些是**完全相同**，不能报告为“当前本地新增命令”。

### 10.2 `cli/README.md`

双版均 198 行。

删除/弱化：
- 原版 3 的“CLI 与服务端均已实现、七接口上线、不再 mock”在当前 3 删除。
- 原版 125、162 对 `../items/README.md` 的引用在当前删除或改指现有命令页/schema。
- 原版 160 关于 `canvas_xml_define` 文档可能领先线上 SDK 的来源说明，当前 160 简化为运行失败即停止，不得伪造、静默删除 source_ids 或用 update 补血缘。

保留：初始化、公共参数、环境变量；HTTP/退出码；XML、Item/Frame、Directory；path、source_ids、资产短链；50 项、1MB、批量原子性；`tree→ls→get` 渐进披露。

双版 35–41 初始化关键规则相同：

- 当前对话没有唯一 Workspace ID 时直接 `+workspace-create`。
- `+get-workspace` 只用于显式恢复或排障。
- 创建后使用原始 Workspace ID 单独 `present_files`。
- 画布卡片成功前不得生成/编辑媒体或写 Item/Frame。

### 10.3 `workspace-create.md`

原版 61 行，当前 59 行。

保留：创建请求；从环境读取 conversation_id；返回 Workspace ID/version；无幂等保证；创建后以原始 ID 执行 present_files 门禁。

当前删除原版 11 的错误重复句“唯一不带 canvas-workspace-id 的命令”。双版 9 已正确说明 workspace-create 和 get-workspace 都不带。

次要措辞问题：当前 45 的“后续所有命令都要用它”是泛化表述；严格说两个初始化命令不需要该 ID。

### 10.4 `get-workspace.md`

原版 64 行，当前 62 行。

原版内部存在冲突：12 已说不是默认初始化；14 又写“每轮第一条命令、无 ID 先查、重复建同一张”。

当前删除 14，消除与 SKILL/README 默认直接创建的冲突。当前 51–59 把“典型动线”改为“显式恢复动线”，只演 exists=true 后复用 ID，不再演示 exists=false 后建画布。

保留：exists=false 仍是成功响应；不能只按进程退出码判断是否存在；会话信息从环境读取。

### 10.5 `create.md`

原版 165 行，当前 163 行。

- 当前 36 删除已不存在的 items 文档链接。
- HTML 示例从原版 88–94 的 `example/create-HTML.xml` 改为当前 88–94 的临时 `item.xml`。
- 当前 98 将原版固定 CDN+Markdown 截图协议改为当前宿主真实预览/文件入口和 local-runtime。
- Canvas Item 回读后 `present_files(<workspace>?item_id=<id>)` 的原平台规则保留。
- 原版 165 关于 Workspace 初始化卡片与 HTML Item 卡片不可混用的独立总结被当前删除，但核心仍见当前 README 39、workspace-create 49、create 98，属于去重，不是授权弱化。

### 10.6 CLI 在本地的定位

`local-runtime.md` 29 已明确：`references/cli/` 只描述原平台远端画布。本地没有 design-cli 等价物，不应伪造 Workspace、Item 或 Frame。

## 十一、lint 命令与实际兼容断点

双版主命令保持：

```bash
python3 <skill-dir>/scripts/drama_lint.py \
  --project-root "<项目目录>" \
  --stage planning|script|assets|storyboard|keyframes|video|final
```

- `--stage skill` 检查 Skill。
- 最终发布或专项审计使用 `--stage all`。
- `summary.error_count > 0` 或 `release_ready == false` 禁止交付。
- 当前只报告，不自动预填确认、创作内容、工具结果或媒体文件。
- 当前新增导演底稿五段、H3 固定字段、两层媒体标记/真实槽位、`<d>` 台词字词/词序/说话人/句数等客观检查。

实际脚本：

- 原版 `scripts/drama_lint.py` 3104–3111：`--fix` 为兼容参数，不自动修复；`--changed-file` 可重复，兼容参数，仍跑相同 focused checks。
- 当前 `scripts/drama_lint.py` 1528–1533：仅 `skill_root`、`--project-root`、`--stage`。

当前 `manifests.md` 283–286 与 `SKILL.md` 220 同步删除兼容参数说明。

**实际影响：高优先级迁移断点。** 旧自动化继续传 `--fix` 或 `--changed-file` 会失败，不能按原版“兼容但不执行额外动作”的假设运行。

## 十二、缺失、矛盾与迁移风险优先级

### P0：会直接破坏旧自动化或授权真实性

1. **lint 参数不兼容**：`--fix`、`--changed-file` 已真实删除。
2. **视频确认粒度变化**：旧的 1–2 SEG 批次调用不符合当前一次一个 SEG。
3. **不得伪造本地确认/交付**：本地聊天必须明确，且使用 `local:` 记录；文件链接必须真实展示；不能用本地路径填充远端 Canvas 字段。
4. **不得伪造 H3 转换**：必须真实调用 h3-prompt-writing，不能自行仿写英文成稿。

### P1：会导致 manifest/schema 或执行错误

1. 规划预估区间、storyboard 执行时长、delivery 实测时长不可混用。
2. `video_manifest` 新 provider/adapter/run-state/双层 Prompt 字段不是旧 Seedance 记录可自然兼容的可选装饰。
3. H3 `video_edit` 的 Ref2VA 重生成语义不同于原版直接编辑。
4. 当前删除旧状态镜像兼容说明，旧项目迁移需额外核验唯一状态源。
5. CRD/群众引用、批准门和下游失效是新依赖，不可沿用旧 CHR/SCN/PROP/STYLE 集合。

### P2：文档内部一致性风险

1. `interaction.ask` 绝对措辞与本地聊天确认并存。
2. `control-contracts.md` 224、`delivery.md` 70/132/134、`SKILL.md` 182 仍有远端 Canvas/present_files 绝对措辞。
3. delivery 的禁止 FFmpeg 与本地 burn 命令并存。
4. mediakit ASR 单路径、人工试听和“必须 ASR 原始信封”措辞并存。
5. `manifests.md` 1224 的“真实 mediakit 探测”未完全本地中立。
6. workspace-create 45 的“后续所有命令都要用它”与两个零 ID 初始化命令存在轻微泛化冲突。

### 不应误报为功能删除的内容

- control 顶部摘要从原版 5–15 压缩为当前 5–7，不代表正文合同全部消失。
- get-workspace 旧动线删除是冲突修复。
- workspace-create 错误“唯一零 ID”删除是纠错。
- create.md 的卡片总结删除主要是去重。
- candidate 定义不再含“即时交付”，不等于逐段交付门取消。
- CLI 六份文件完全相同。
- `references/cli/` 保留不代表本地必须调用远端 Canvas。
