# 脚本、校验器、回退与测试对比

## 结论摘要

本次对比以磁盘上的实际文件为准，完整阅读了原版 `scripts/drama_lint.py`、`scripts/drama_rollback.py`，以及当前版 `scripts/` 下全部 11 个 Python 文件和 `tests/` 下全部 11 个测试文件。

当前版不是简单把原版单体脚本拆开，而是把原来的 Seedance 2.0/2.5 工作流改造为 **H3 唯一模型、五种 H3 模式、真实 Skill 转换血缘、逐 SEG 串行确认** 的工作流，并新增了群众资产、结构化导演底稿、H3 `<d></d>` 台词、阅读稿和逐镜删除复审等约束。状态机、资产版本、复用、关键帧、成片连续性等大量原有规则仍然保留，但分散到了多个模块中；不能用类或代码行数多少判断功能强弱。

需要优先注意的行为差异有：

1. 当前 lint CLI 删除了原版的兼容参数 `--fix` 和 `--changed-file`，旧调用方可能直接得到 argparse 参数错误。
2. 轻量模式的非 planning 回退不再回到请求的阶段，而是统一修复为 `current_stage=final`、`current_episode=ep_1`；输出新增 `requested_to_stage` 正是为了区分请求和实际结果。
3. 视频生成确认由原版允许连续 1–2 个 SEG，收紧为每次只能确认并生成一个 SEG。
4. 视频阶段缺少 storyboard SEG 的记录由 error 改为 warning，但进入 final/all 验收时仍是 error。
5. `video_edit` 不再豁免 Prompt preflight 和提示词结构校验，统一进入导演底稿、H3 成稿、preflight 和转换血缘管线。
6. 当前 `release_ready` 仍只取决于 error 数；warning 不会阻断，也不代表真实生成、上传、Provider 或媒体内容已经通过外部验证。

实际执行的本地测试结果为 **76 项全部通过**，当前 Skill 包自检为 **0 error、0 warning、release_ready=true**。测试通过不等于所有新旧规则都有回归覆盖：回退、完整状态机、群众、H3 台词与转换血缘、完整生成确认链路等仍缺专项测试。

---

## 1. 范围、基线与安全边界

### 1.1 路径约定

下文使用两个缩写：

- **原版 O**：`<doubao-root>`
- **当前版 C**：`<drama-root>`

行号均指本次读取时磁盘文件的实际行号。报告中的“保留”表示找到了对应校验职责，不表示所有错误文案、内部数据结构或边界条件逐字相同。

### 1.2 未提交状态

当前仓库的 Git 状态包含：

```text
 M references/storyboard.md
 M scripts/drama_lint_storyboards.py
 M tests/test_storyboard_reading_lint.py
?? DOUBAO_CREATIVE_DRAMA_DIFF.md
?? tests/test_storyboard_deletion_review_lint.py
```

因此，本报告特别以磁盘内容纳入了：

- 未提交的分镜脚本修改，主要是导演逐镜删除复审和阅读稿内切检查，见 C `scripts/drama_lint_storyboards.py:413-503,518-623`；
- 已跟踪但未提交的阅读稿测试修改，见 C `tests/test_storyboard_reading_lint.py:65-89`；
- 完全未跟踪的新测试 C `tests/test_storyboard_deletion_review_lint.py:1-105`。

原版目录不是 Git 仓库，执行 Git 状态检查返回 `not a git repository`，所以只能描述其磁盘实现，不能声称原版“没有未提交修改”。

### 1.3 执行边界

本次没有修改任何源码或测试，没有执行真实视频、生图、上传或网络请求。仅运行了本地无副作用测试和 Skill 自检；测试使用临时目录、fake HTTP、mock 子进程/时钟/媒体验证。真实命令和结果见第 7 节。

---

## 2. 从原版单体到当前 11 个脚本的功能映射

### 2.1 总体映射

| 原版职责与位置 | 当前承接位置 | 结论 |
|---|---|---|
| 阶段、状态、媒体常量、issue/JSON/路径/哈希等基础能力，O `scripts/drama_lint.py:1-213` | C `scripts/drama_lint_domain.py:1-325` | 基础能力独立成域模块；模型与媒体常量改为 H3，参考角色明显扩充 |
| manifest、轻量计划，O `scripts/drama_lint.py:226-382` | C `scripts/drama_lint.py:247-361`、`drama_lint_domain.py:251-307` | 保留并改变轻量时长约束 |
| 用户确认记录，O `scripts/drama_lint.py:385-523` | C `scripts/drama_lint_confirmations.py:1-237` | full/incremental 等保留，新增 confirmation transport |
| 制作状态、分集顺序、聚合状态，O `scripts/drama_lint.py:526-743` | C `scripts/drama_lint_state.py:1-477` | 主体状态机保留，新增强制轻量 merged/final 形态 |
| 阶段产物、故事文档，O `scripts/drama_lint.py:759-895` | C `scripts/drama_lint.py:389-524` | 文件门和故事包职责基本保留 |
| 创意计划、节奏、逐集精确时长，O `scripts/drama_lint.py:897-1026` | C `scripts/drama_lint.py:527-697` | 新增 planning_estimate 与 user_locked 分流 |
| storyboard index、镜头/关键帧计划，O `scripts/drama_lint.py:1029-1167` | C `scripts/drama_lint_storyboards.py:50-416` | 拆为独立分镜模块 |
| 亮点、反应、跨集余震，O `scripts/drama_lint.py:1170-1446` | C `scripts/drama_lint_highlights.py:1-244`，并由 `drama_lint_storyboards.py:668-669` 接入 | 主要是迁移保留，不应以类数量视为功能增强 |
| 参考输入计划，O `scripts/drama_lint.py:1449-1481` | C `scripts/drama_lint_storyboards.py` 中 reference plan 校验 | 保留并服务后续实际输入核对 |
| 资产注册表、版本、状态、复用和生成请求，O `scripts/drama_lint.py:1484-1821` | C `scripts/drama_lint_assets.py:1-703` | 保留主体系，新增 crowd/CRD 和分集资产前缀检查 |
| 实际媒体输入、五段 Prompt、字幕与台词，O `scripts/drama_lint.py:1824-2038` | C `scripts/drama_lint_video.py:101-227`、`drama_lint_prompts.py:1-374` | 从单份 Prompt 改为导演底稿 + H3 成稿两层 |
| 视频生成参数确认与批次，O `scripts/drama_lint.py:2052-2389` | C `scripts/drama_lint_video_confirmations.py:1-599` | 独立成完整确认子系统，串行范围收紧 |
| 语音输入与 voice anchor，O `scripts/drama_lint.py:2392-2457` | C `scripts/drama_lint_video.py:253-318` | 基本迁移保留 |
| Prompt preflight，O `scripts/drama_lint.py:2460-2479` | C `scripts/drama_lint_prompts.py:297-318` | 保留并新增 H3 结构确认 |
| 关键帧 manifest，O `scripts/drama_lint.py:2482-2579` | C `scripts/drama_lint.py:997-1094` | 基本保留 |
| 视频路由、状态、Prompt、输出，O `scripts/drama_lint.py:2581-2769` | C `scripts/drama_lint_video.py:321-681` | H3 路由与来源核对显著收紧 |
| 成片、连续性、字幕、QC，O `scripts/drama_lint.py:2772-3024` | C `scripts/drama_lint.py:1096-1350` | 主体保留，精确时长只在有锁定值时比较 |
| Skill 包和 Markdown 链接，O `scripts/drama_lint.py:3039-3101` | C `scripts/drama_lint.py:1364-1525` | 新增 H3 能力档、运行文件、Python 源码与视频示例检查 |
| 单体回退，O `scripts/drama_rollback.py:1-215` | C `scripts/drama_rollback.py:1-308` | 完整模式主逻辑保留，新增轻量修复、输入校验和深复制 |

### 2.2 当前 11 个脚本各自的实际职责

1. **C `scripts/drama_lint.py`**：兼容包内/脚本两种导入方式并再导出公共函数；负责阶段文件、计划时长、群众、关键帧、成片、本地 H3 能力档、Skill 包、CLI 和总调度。群众新增逻辑集中在 `700-995`，主调度在 `1536-1607`。
2. **C `scripts/drama_rollback.py`**：唯一回退写入脚本，负责状态转换、原子 JSON 写入、操作日志、dry-run 和失败恢复。
3. **C `scripts/drama_lint_domain.py`**：公共枚举、常量、输入角色、H3 模型/时长、marker、计划对象和通用 helper。导入时读取 `tools/h3.json`，见 `55-58`；H3 规则见 `200-232`。
4. **C `scripts/drama_lint_confirmations.py`**：通用用户确认 JSONL 的读取、full/incremental、revision、planning interaction 和 transport。
5. **C `scripts/drama_lint_highlights.py`**：剧本亮点、分镜绑定、reaction/payoff/aftereffect 顺序以及跨集 deferred/inherited aftereffect。
6. **C `scripts/drama_lint_assets.py`**：共享/分集资产、版本和状态、文件存在性、复用、生成路由、STYLE001 moodboard，以及群众资产索引。
7. **C `scripts/drama_lint_state.py`**：项目/分集状态、前集/当前集/未来集、确认要求和项目聚合状态。
8. **C `scripts/drama_lint_prompts.py`**：结构化或五自然段导演底稿、H3 最终 Prompt、媒体标记、`<d>` 台词、preflight、真实 Skill 调用与 SHA-256 血缘。
9. **C `scripts/drama_lint_storyboards.py`**：分镜 JSON、segment/shot、密度、镜头和尾态计划、参考计划、audience execution、导演删除复审、阅读稿。
10. **C `scripts/drama_lint_video.py`**：实际输入、H3 模式媒体限制、voice、路由策略、逐段 Prompt 管线、视频 manifest 与真实来源。
11. **C `scripts/drama_lint_video_confirmations.py`**：生成段索引、确认 ledger/envelope、单 SEG 范围、supersession、授权、参数展示、五列分镜、调用 ID 与时间。

---

## 3. CLI、输出 schema、错误与 release_ready

### 3.1 lint CLI

原版 O `scripts/drama_lint.py:3104-3111` 与当前 C `scripts/drama_lint.py:1528-1533` 都支持：

- 可选位置参数 `skill_root`，默认 `.`；
- `--project-root`；
- `--stage`，取值为 `skill`、七个制作阶段或 `all`，默认 `skill`。

**当前遗漏/移除的旧接口**：

```text
--fix
--changed-file
```

原版这两个参数只用于兼容：`--fix` 不实际修复，`--changed-file` 也仍运行相同 focused checks。当前版将其完全删除，因此不是校验能力退化，但属于 **CLI 向后兼容破坏**。旧自动化若仍传参，会在进入校验前失败。

### 3.2 输出 schema 和退出码

两版 lint 的主输出结构保持一致，见 O `scripts/drama_lint.py:3114-3183` 与 C `scripts/drama_lint.py:1536-1607`：

```json
{
  "summary": {
    "error_count": 0,
    "warning_count": 0,
    "scope": "skill"
  },
  "release_ready": true,
  "issues": []
}
```

单个 issue 仍包含 `level`、`code`、`message`、`hint`，有路径时包含 `path`，见 C `scripts/drama_lint_domain.py:102-106`。两版都会按 level/code/message/path 去重；当前实现见 C `scripts/drama_lint.py:1352-1361`。

判定逻辑没有改变：

- `release_ready = (error_count == 0)`；
- 有 error 返回进程码 1，否则返回 0；
- warning 只计数，不阻断；
- `scope` 是请求的检查阶段，不是对所有阶段的隐式认证。

因此，`--stage video` 的 `release_ready=true` 不能解释为成片可交付；当前视频阶段甚至允许用 warning 表示尚未覆盖全部分镜 SEG。

### 3.3 主调度新增关系

当前 C `scripts/drama_lint.py:1574-1593` 在原有 assets/storyboards/keyframes/video/delivery 之外加入 `check_project_crowds`。其调用范围根据阶段决定要不要读取 storyboard 和 video 关系，避免把群众检查误认为仅在 assets 阶段执行。

---

## 4. 校验规则的保留、新增、改变与退役

### 4.1 阶段、集数和状态

两版阶段序列保持：

```text
planning → script → assets → storyboard → keyframes → video → final
```

状态集合仍覆盖 `pending`、`in_progress`、`awaiting_confirmation`、`confirmed`、`merged`、`invalidated`、`blocked`。原版状态机的以下职责在 C `scripts/drama_lint_state.py` 中均有对应实现：

- planning/script 项目级范围与逐集范围的区分，`55-87`；
- planning 前、全局 script 确认前的分集限制，`138-153`；
- 前集必须完成到 target、未来集不得提前开始，`156-173`；
- 当前集前后阶段顺序及当前活动状态，`176-197`；
- 项目 phases 与所有 episodes 的聚合对齐，`280-313`；
- confirmed 阶段必须存在相应用户确认，`378-388,442-448`。

**轻量模式新增硬约束**：planning 确认后，必须始终保持 `current_stage=final`、`current_episode=ep_1`，项目中间阶段必须 merged，见 `323-333`；ep_1 的中间阶段也必须 merged，见 `361-366`。这不再是“中间阶段可以选择 confirmed 或 merged”的宽松状态，而是固定的工作流形态。

另有一个底层语义变化：C `scripts/drama_lint_domain.py:153-162` 的 `has_meaningful_value` 将非 bool 数字（包括 0）视为有意义值，原版不把数字作为同类有意义内容。它会影响复用该 helper 的非空说明类校验，属于需要边界测试的细微差异，不能默认所有调用点都完全等价。

### 4.2 计划与时长

原版 O `scripts/drama_lint.py:897-1026` 要求精确逐集时长，并围绕总时长、显示文本、节奏、策略和字幕进行校验。当前 C `scripts/drama_lint.py:527-697` 将时长语义拆成两类：

- `duration_semantics=planning_estimate`：完整模式规划阶段允许只登记估算范围、估算显示文本和总范围，不建立精确跨阶段时长门；
- `duration_semantics=user_locked`：建立逐集精确时长门，storyboard 和 delivery 必须匹配；
- lightweight 即使使用规划估算，也仍需有唯一可执行时长，并建立精确门。

对应返回值的语义也从“每集必有整数时长”变成 `dict[episode_id, int | None]`。分镜和成片只有在 expected duration 非 None 时才比较精确值，见 C `scripts/drama_lint_storyboards.py:638-640` 与 `drama_lint.py:1096-1350` 的 delivery 校验。

**轻量时长规则改变**：原版按 Seedance 型号分支允许总时长不超过 15 或 30 秒；当前 C `scripts/drama_lint_domain.py:251-307` 改为单集、单视频、满足 H3 的 **4–15 整数秒**。状态错误文案也同步改为该约束，见 C `scripts/drama_lint_state.py:323-326`。

### 4.3 通用用户确认

原版 full/incremental 确认体系基本保留在 C `scripts/drama_lint_confirmations.py`：

- full 记录同 scope 的 revision，`72-77`；
- incremental 必须有整数 base_revision，且指向同阶段已有 full revision，并有 changed_artifacts 和 impact_scope，`80-92`；
- stage、episode_id、decision、mode、revision、user_message、带时区 confirmed_at 的校验，`170-188`；
- 最新 planning revision 必须带要求的 purpose/result/call ID，`190-205`。

**新增 transport 门**：`30-36` 要求 `confirmation_transport` 只能是 `user_message` 或 `host_tool`。用户消息必须使用唯一 `local:` 记录 ID；host_tool 必须保存真实、非 local 的宿主调用 ID。它把“确认来自聊天还是宿主工具”从原来的 confirmation_source 中分离出来，旧确认记录如果没有新字段会失败。

### 4.4 故事、亮点、分镜、阅读稿和删除复审

#### 保留部分

- 阶段故事文档和完整模式故事包要求仍由 C `scripts/drama_lint.py:389-524` 负责，对应 O `scripts/drama_lint.py:759-895`。
- 分镜文件、shot/segment 结构、时长和覆盖关系由 C `scripts/drama_lint_storyboards.py:349-416,626-670` 负责。
- 密度、shot mode、tail mode、关键帧请求计划和 reference plan 位于 `50-235`。
- audience execution 位于 `236-275`。
- 原版的亮点绑定、反应/payoff、跨集余震没有因单体拆分而消失，而是集中到 C `scripts/drama_lint_highlights.py:1-244`，由分镜总入口调用。

#### 新增阅读稿校验

当前完整模式在阅读稿文件存在时执行 C `scripts/drama_lint_storyboards.py:521-623`，检查：

- 固定标题、全片摘要、唯一“本集故事提要”、章节和片段标题；
- 禁止 Markdown 表格和 SEG 式片段标题；
- 每章叙事功能、至少一个片段；
- 每镜固定 bullet、四项摄影信息、声音/人声/切入/切出字段；
- 片段声明镜头数、镜头连续编号、全片章节/片段/镜头总数。

未提交新增的内切检查在 `518,599-609`：画面动作已经建立后，再出现“切至”“镜头/画面切到”等明确编辑语言，会报 `storyboard_reading_internal_cut`；开头切入、连续运镜、焦点转移和物理切纸动作不在目标范围内。

**边界**：该校验主要验证阅读稿自身结构，没有完整交叉核对阅读稿与 storyboard JSON 的 SHOT ID、时间区间和逐镜时长；自然语言内切识别也是限定正则，不等于覆盖所有切镜表达。

#### 新增导演逐镜删除复审

未提交逻辑位于 C `scripts/drama_lint_storyboards.py:413-503`：

- 标签接受“镜头职责与删除损失”或“镜头职责与删除测试”；
- 支持 Markdown 表格和带 SEG heading 的写法；
- 以 SEG 分组，要求每段有记录；
- 只有含“删”的分句中的 SHOT 引用才计入覆盖；
- 缺整段记录报 `director_segment_deletion_review_missing`；
- 缺具体镜头报 `director_shot_deletion_review_missing`。

完整模式且 director card 路径有效、文件存在时调用，见 `647-649`。这能防止用全集概括或其他镜头的删除分句充数，但它验证的是 **逐镜删除记录的存在与归属**，不证明所写删除损失在艺术上正确或充分。

### 4.5 资产、群众与关键帧

C `scripts/drama_lint_assets.py` 保留原版资产版本、approved 状态、真实文件、跨集复用、image_gen/image_edit 和 STYLE001 moodboard 等主规则。复用仍要求更早分集、相同版本/状态/文件，见 `594-649`。

新增或收紧包括：

- 新增 `crowd` 资产类别、CRD 前缀和 `files_by_ref` 索引，供后续核对 approved 资产实际文件；
- 分集资产也检查 category 对应 ID 前缀，见 `652-687`；
- 复用资产生成请求继续使用统一 GenerationRequest 校验，但共享资产和分集资产的历史分支不能仅凭函数名认定所有细节完全一致，尤其是 image_gen 的 style_anchor_refs 处理。

群众体系是当前主入口最大的新增块，C `scripts/drama_lint.py:700-995`：

1. `check_request_snapshot` 核对真实 CLI dry-run/task 快照的 slots、图片槽位、项目文件路径和字节 SHA-256，`704-747`。
2. `check_crowd_reference` 要求 recurring 群众绑定真实 CRD/SRC 来源、crowd_reference 输入和真实图片；SRC 还要与 source_manifest 的唯一记录、stored_path、哈希一致，CRD 要与 approved 文件集合一致，`750-809`。
3. `check_crowd_list` 检查 CRD ID、状态、人数/密度、位置、动作、允许变化、continuity_scope、visibility、群体外观和成员登记，并约束跨段外观与 character 映射稳定，`812-995`。
4. storyboard shot 绑定和 video 段输入由 project crowds 总入口跨文件核对，而不是只检查单个 JSON 字段。

关键帧 manifest 的原版职责仍在 C `scripts/drama_lint.py:997-1094`，并由视频模块读取真实 keyframe ID 做来源核对，见 C `scripts/drama_lint_video.py:146-152,668-669`。

### 4.6 视频模型、媒体槽位和路由

#### 从 Seedance 多模型转为 H3 能力档

原版在 O `scripts/drama_lint.py:1-80,1081-1105,1993-2038` 按 Seedance 2.0/2.5 和媒体类型执行不同限制。当前只接受 H3，并由本地 `tools/h3.json` 提供能力：

- 时长为 4–15 整数秒，C `scripts/drama_lint_domain.py:200-223`；
- 五种模式为 T2VA、I2VA、FL2VA、L2VA、Ref2VA；
- Skill 自检会重新核验能力档本身，禁止通过修改能力档虚增能力，并禁止把 deployment/provider/凭证配置混入其中，C `scripts/drama_lint.py:1364-1398`。

能力档硬门包括五种模式完整唯一、参考数量上限、Ref2VA 总文件数 12、音频必须有视觉输入、视频/音频每条 2–15 秒且累计不超过 15 秒等。

#### 实际输入与槽位

C `scripts/drama_lint_video.py:101-143` 保留并强化实际输入检查：

- `reference_inputs`、`video_inputs`、`audio_inputs` 必须是数组；
- order 必须为从 1 开始的连续整数；
- role 必须属于对应角色集合；
- 文件必须是存在的项目相对路径，图片输入还检查后缀；
- 图片与媒体输入分别要求 source_id/resource_id、file、adopt、exclude 等字段。

**禁止未来尾帧**：只要出现 `planned_reference_inputs` 就报错，即使数组为空；实际 reference_inputs 中也不得用 `previous_tail_of` 动态偷带未来 tail，见 `101-107`。连续段必须传入已存在、可定位的真实 frame。

#### H3 模式媒体约束

C `scripts/drama_lint_video.py:163-227` 新增完整的模式输入检查：

- 按模式限制图片、视频、音频数量及总文件数；
- FL2VA 必须恰好两张图，I2VA/L2VA 必须恰好一张图；
- 首尾帧的 role、frame_position、order 和实际 frame 来源必须匹配；
- Ref2VA 必须至少有一个真实参考，普通参考不能冒用首尾帧职责；
- 音频参考必须伴随视觉输入；
- 视频/音频每条 2–15 秒、累计不超过 15 秒；
- **每个视频/音频参考都必须登记实际时长**，缺失直接报 `h3_*_input_duration_missing`。

最后一项相对原版是收紧：原版媒体时长检查主要处理已经提供时长的条目，缺少时长本身不必然形成同类硬错误。

状态参考也更灵活但更明确：C `scripts/drama_lint_video.py:230-250,651-669` 允许用 approved 基准资产或 approved state_refs 锁定状态；上一段尾帧的两类角色都必须 `source_type=frame`，asset/keyframe 来源仍会回查真实索引。

#### 路由映射

当前 C `scripts/drama_lint_video.py:84-98,321-438` 将工作流 tool_mode 与 H3 mode 显式绑定：

```text
text_to_video  → T2VA
image_to_video → I2VA / FL2VA / L2VA / Ref2VA
media_to_video → Ref2VA
video_edit     → Ref2VA
```

轻量模式仍只能有一个视频，见 `565-566`。所有有效路由最终都会执行 SegmentPromptPipeline，见 `641-649`，不再保留原版 video_edit 的 Prompt 豁免。

#### 缺段严重级别变化

原版 O `scripts/drama_lint.py:2619-2623` 对 video manifest 未覆盖 storyboard SEG 始终报 error。当前 C `scripts/drama_lint_video.py:581-588` 改为：

- 普通 video 阶段：warning，允许逐段建立真实执行记录；
- final/all 且非 lightweight：error，进入成片前必须补齐。

这与 `release_ready` 只受 error 影响共同构成有意的阶段语义变化。

### 4.7 Prompt、H3 与 `<d>` 台词

原版 O `scripts/drama_lint.py:1824-1990,2460-2479,2720-2739` 主要围绕一份五段式 Prompt、媒体标记、台词和 preflight。当前 C `scripts/drama_lint_prompts.py` 将流程拆成两层：

#### 第一层：导演编译底稿

- 固定结构化标题为 `integrated_multimodal_description`、`overall_soundscape`、`non_diegetic_music`、`dialogue_refs`，见 `125-162`；
- 同时兼容传统五自然段底稿，见 `165-230`；
- 结构化模式从 dialogue_refs 表核对当前 SEG 的 speech_lines，五自然段模式保留花括号台词检查；
- 媒体槽位标记、字幕方括号、主体标签等检查转移到底稿层，见 `106-123,185-199`，不是简单消失。

#### 第二层：H3 最终成稿

C `scripts/drama_lint_prompts.py:233-294` 要求：

- 普通模式具有 `integrated_multimodal_description:`、`overall_soundscape:`、`non_diegetic_music:`；
- Ref2VA 另用 `subject_definitions:`、`summary:`、`retention_analysis:`、`detailed_description:` 等固定字段；
- I2VA/FL2VA/L2VA 必须带对应 opening instruction；
- 只能使用 `<Picture N>`、`<Video N>`、`<Audio N>`，禁止中文 `<图片N>` 等标记；
- 成稿中的媒体 order 必须与实际输入数组完全一致；
- 未启用字幕时不得出现 `【】` 字幕源标识。

`<d></d>` 是新增硬合同：

- 开闭标签必须完整配对，不能嵌套；
- 每条 speech_line 恰好一个 `<d>` 块；
- 每块必须以 `[语言]` 标签开头；
- 移除允许的 `<scenetrans>`/`<cutoff>` 后，按规范化台词逐条、按顺序比较；
- 没有 speech_lines 时不得额外出现 `<d>` 块。

#### preflight 与真实 Skill 血缘

preflight 保留“一次集中审阅、最多一次修订、一次最终客观校验、每镜恰好编译一次”等要求，并新增 `h3_structure_verified is True`，见 `297-318`。

C `scripts/drama_lint_prompts.py:321-373` 进一步要求：

- 主 Agent 通过 `host_skill_tool` 真实调用 `h3-prompt-writing`，`invoked=true`；
- converted_at 为带时区时间；
- source_draft_sha256 与 compiled_prompt_sha256 为 64 位小写 SHA-256；
- 两个 hash 必须分别匹配当前源底稿和 H3 成稿；
- compiled_prompt_sha256 还必须与实际提交的 prompt_sha256 一致。

因此，当前不是“手写一个长得像 H3 的 Prompt 即可通过”。但也应明确：lint 检查的是登记字段、文件哈希和合同一致性，它本身不会向宿主证明一次历史工具调用的外部真实性。

### 4.8 视频生成确认

原版 O `scripts/drama_lint.py:2052-2389` 的生成确认、批次参数表、五列分镜、返修替代和调用时间逻辑，迁移到 C `scripts/drama_lint_video_confirmations.py`。

主要保留与增强：

- segment index 必须唯一、为正整数并覆盖 1..N 连续序列，`38-84`；
- confirmation ID、attempt、范围、ledger 和重叠范围管理，`88-242`；
- serial_real_tail_chain 必须绑定项目相对 run_plan_file 及其 SHA-256，`206-214`；
- 返修必须显式 supersedes 所有重叠旧确认，时间更晚且 attempt 递增，`217-242`；
- 必填参数、planned_video_count、轻量规划范围和逐段授权，`245-303`；
- 轻量/普通批次的参数展示与 final_parameters_text 回查，`328-426`；
- 五列分镜和台词规范化比较，`427-486`；
- confirmed_at、interaction_ask_result=generate、cost notice、H3 模型、tool_call_id、带时区调用时间以及确认早于调用，`487-551`。

**单 SEG 收紧**：当前 `186-188` 明确 `end != start` 即报 `video_generation_confirmation_too_large`。原版允许连续 1–2 个 SEG；当前要求上一段真实尾态复核、登记并交付后，才确认下一段。

**新增生成前 H3 转换门**：`SegmentAuthorizationRule._validate_segment` 会检查 h3_conversion；continuous 段还必须在确认前已有真实 tail FRM、文件和 source relation，见 `280-303` 及后续实现。

**有意退役的规则**：原版 Seedance 2.5 生成确认要求非空 `membership_notice`，见 O `scripts/drama_lint.py:2353-2357`。当前 H3 唯一模型下不再存在 `video_generation_membership_notice_missing`，这是模型切换导致的合同删除，不应误判为漏迁移。

### 4.9 成片与 Skill 包

成片侧仍检查输出、accepted/candidate 状态要求、source segment、连续性、字幕和 basic QC，主体位于 C `scripts/drama_lint.py:1096-1350`。变化主要是精确时长服从 planning_estimate/user_locked 门；不能据局部时长测试推断整个成片校验都已覆盖。

Skill 包自检除原有 frontmatter、SKILL.md 引用和 Markdown 相对链接外，还新增：

- 本地 H3 能力档完整校验，`1364-1398`；
- Markdown 中视频 manifest JSON 示例的生成确认、H3 时长/媒体/模型和输入字段校验，`1401-1429`；
- 本地运行文件和参考文件必须存在，`1432` 起；
- 对 Python 文件做 AST/tokenize 检查，并执行当前源码风格约束（包括禁止注释和 docstring），见 `1432-1525`。

这些新增检查解释了为什么 Skill 自检比原版更依赖当前包内文件完整性，但它仍只是静态和示例合同检查。

---

## 5. 回退脚本专项对比

### 5.1 保留的完整模式行为

原版 O `scripts/drama_rollback.py:25-107` 与当前 C `scripts/drama_rollback.py:88-192` 都保留：

- 七阶段校验；
- assets 到 final 的项目级回退必须提供 episode；
- episode 回退只允许 script 到 final；
- 不得回退尚未成为 current 的未来集；
- 不得回退尚未开始的目标阶段；
- 后续集已经推进时，必须显式 `--cascade-later-episodes`；
- revision 加一，目标阶段进入 awaiting_confirmation 或 in_progress，下游 invalidated；
- 不删除或重写实际艺术产物，只改制作状态和操作日志。

当前将状态更新改为 `deepcopy`，见 C `scripts/drama_rollback.py:74,173`，避免嵌套 phases/episodes 与输入对象共享引用；这是对原版浅复制风险的实质修正。

### 5.2 新增输入校验

C `scripts/drama_rollback.py:37-58` 新增：

- state 必须是对象；
- `--episode` 必须是正整数 ep_N；
- phases 必须是对象；
- episodes 中所有 key 都必须是合法 ep_N，避免后续按 `_` 分割和转整数时发生非预期异常；
- 通过 workflow_mode 或 merged 状态识别轻量回退。

CLI 参数名和基本用途保持：`--project-root`、`--to-stage`、`--episode`、`--cascade-later-episodes`、`--reason`、`--dry-run`，见 `270-278`。

### 5.3 轻量模式语义发生根本变化

当前在 C `scripts/drama_rollback.py:232-242` 额外读取 `00_制作控制/drama_plan.json` 的 `objective.workflow_mode`；原版只根据状态和 CLI 参数工作，不读取计划判断模式。

轻量且目标不是 planning 时，C `scripts/drama_rollback.py:161-170` 不执行普通逐阶段回退，而进入 `_lightweight_repair`，其规则为 `61-85`：

- planning 必须 confirmed，否则要求先回 planning；
- 必须恰好只有 ep_1，且请求的 episode 只能为空或 ep_1；
- 无论请求的是 script/assets/storyboard/keyframes/video/final 中哪个非 planning 阶段，实际都设置：
  - `current_stage=final`；
  - `current_episode=ep_1`；
  - script 到 video 的项目和 ep_1 阶段均为 merged；
  - final 为 in_progress。

这与 lint 的轻量固定状态形态一致，但意味着 **“回退到某阶段”在轻量模式中实际是“回到 final 做内部返修”**。调用方不能只看请求参数推断结果。

### 5.4 日志和输出差异

原子写入仍是临时文件加 `os.replace`，见 O `scripts/drama_rollback.py:18-22` 与 C `scripts/drama_rollback.py:19-23`。日志字段结构大体保留。

当前提交日志时使用 **更新后的** `current_stage/current_episode`，见 C `scripts/drama_rollback.py:245-256`；原版直接记录 args.to_stage/args.episode，见 O `scripts/drama_rollback.py:167-178`。轻量修复时，当前日志因此记录实际 final，而不是请求的 script/video 等阶段；requested 值仍可在 CLI 输出中看到，但日志 params_summary 同样以实际值为主。

成功输出新增 `requested_to_stage`，且 `to_stage`、`episode_id` 取更新后的状态，见 C `scripts/drama_rollback.py:295-302`。原版输出只回显请求参数，见 O `scripts/drama_rollback.py:197-208`。

失败结构保持：

- 请求、读取或 JSON 错误：`rollback_failed`，退出 2；
- 状态已写但日志失败且成功恢复：`rollback_log_failed`，退出 2；
- 日志失败且原状态恢复也失败：`rollback_partial_commit`，退出 3。

### 5.5 回退风险

当前 11 个测试文件中没有 `drama_rollback.py` 专项测试。因此，轻量 final 修复、后续集级联、dry-run 不写文件、日志失败恢复、退出 3 等关键行为都没有在本仓库测试中得到直接回归保护。这是本次对比中最明确的测试空白之一。

---

## 6. 当前 11 个测试文件逐项覆盖

测试数量合计 76。下表的“通过”只表示该测试实际断言通过，不表示被测模块的全部功能通过。

| 测试文件 | 数量 | 实际覆盖与隔离方式 | 主要边界 |
|---|---:|---|---|
| C `tests/test_structured_director_draft_lint.py` | 5 | 直接测试 `check_director_draft_prompt`：结构化固定标题和 dialogue table 合法、五自然段兼容、标题乱序拒绝、台词漏/增拒绝，见 `12-76` | 不覆盖 H3 成稿 `<d>`、preflight 或 Skill hash 血缘 |
| C `tests/test_media_audio.py` | 3 | ffmpeg/ffprobe 可用时在 TemporaryDirectory 生成两秒 WAV；覆盖显式暂停裁剪、源文件和 hash 保留、时长接近、禁止覆盖、重叠区间拒绝，见 `18-65` | 本次未跳过；只处理本地 WAV，没有真实视频或上传 |
| C `tests/test_workflow_audio_preflight.py` | 3 | mock `media_duration`，覆盖参考合计恰好 15 秒、超过 15 秒、单音频不足 2 秒，见 `23-47` | 不是五种 H3 模式的完整媒体参数矩阵 |
| C `tests/test_autodl_health.py` | 6 | FakeResponse/mock urlopen、等待和时钟；覆盖 JSON requirement parser、HTTP 200 不等于 ready、精确 JSON boolean、错误 body 不回显、固定等待间隔、健康期限受电源 deadline 限制，见 `15-101` | 没有真实网络，也不证明实际 AutoDL 服务可用 |
| C `tests/test_workflow_recovery.py` | 21 | 11 项 WorkflowRecovery：500、空 history、pending 超过 120 秒、精确资产恢复、saved result URL、多候选/唯一目录歧义、completed/running history、900 秒超时等；4 项 SeriesRecovery；5 项 ProviderSelection；1 项 HTTP envelope，见 `21-463` | FakeBackend 对非 GET 直接 AssertionError；输出 mp4 是临时占位字节，媒体验证被 mock，没有真实生成 |
| C `tests/test_video_run.py` | 8 | 临时 run plan；managed command 固定路径/JSON 字段、默认 offline preflight、单个子进程调用、recover 无原 task、第二个新 generate、未来尾帧/复用尾帧、非法 operation/缺确认在进程前拒绝，见 `16-141` | subprocess.run 被 mock；名为 append log 的用例实际断言原日志不变。未启动真实进程 |
| C `tests/test_video_confirmations.py` | 4 | 单 SEG 确认通过、多 SEG 拒绝、continuous 缺真实尾帧拒绝、真实尾帧满足局部 gate，见 `17-88` | 直接调用 envelope 和 `_validate_segment`，不覆盖完整参数表、supersession、时长和调用时序 |
| C `tests/test_duration_locks.py` | 5 | planning estimate 不建立精确跨阶段门；user_locked 的 storyboard/delivery 不匹配拒绝；lightweight delivery 不匹配拒绝；user_locked 匹配通过目标时长门，见 `25-147` | 多数断言只检查目标错误码或不包含目标错误码；fixture 可能产生其他 issue，不能声称整个 storyboard/delivery 校验通过 |
| C `tests/test_video_plan_lint.py` | 6 | 真实尾帧和固定输入顺序；未来尾帧、空 planned 字段、向实际输入偷带未来尾帧、缺真实尾帧、缺固定输入，见 `12-99` | 直接测 `video_reference_inputs` 与 `ordered_inputs`，不覆盖完整 H3 路由 |
| C `tests/test_storyboard_deletion_review_lint.py`（未跟踪） | 6 | 表格/heading 删除复审、全集概括不能替代分段、镜头不能借用其他镜头删除分句；另有非高密度动态镜头数和 high density 15 秒最少镜头回归，见 `15-101` | 只覆盖所给文本形态；不验证删除损失内容质量，也未做全项目集成 |
| C `tests/test_storyboard_reading_lint.py`（已修改） | 9 | 合法章节/片段/bullet、表格和 SEG heading 拒绝、摘要数量、每镜声音和切入切出；新增明确内切拒绝、连续转场不误报、开头切入不误报、物理切纸不误报，见 `12-89` | 不覆盖阅读稿与 JSON 的完整交叉一致性、所有时间轴边界或更多切镜语言变体 |

### 6.1 测试结构的总体特点

- 多数是局部函数/类单元测试，而不是从真实项目目录运行 lint CLI 的端到端 fixture。
- 网络、子进程、时钟、媒体时长和验证均有 fake 或 mock，安全隔离做得明确。
- 当前新增的分镜阅读稿和删除复审有直接测试，但对应源码/测试仍处于未提交状态。
- 没有发现专门验证 lint 顶层 JSON schema、warning 不阻断、退出码或 release_ready 的测试。

---

## 7. 真实执行命令与结果

### 7.1 全部本地测试

实际命令：

```powershell
python -I -B -m unittest discover -s "<drama-root>\tests" -p "test*.py" -v
```

真实结果摘要：

```text
Ran 76 tests in 1.051s

OK
```

- 退出成功，76 项全部通过，无 failure、无 error；输出未显示 skip。
- `-I` 隔离 Python 环境，`-B` 禁止写字节码。
- 临时文件位于测试自己的 TemporaryDirectory；WAV 由本地媒体工具生成。
- fake HTTP 和 mock 子进程确保没有真实网络、视频生成、上传或外部服务调用。

### 7.2 当前 Skill 包自检

实际命令：

```powershell
python -I -B "<drama-root>\scripts\drama_lint.py" "<drama-root>" --stage skill
```

真实输出：

```json
{
  "summary": {
    "error_count": 0,
    "warning_count": 0,
    "scope": "skill"
  },
  "release_ready": true,
  "issues": []
}
```

该结果只证明当前磁盘上的 Skill 包静态自检通过，不等于 planning/script/assets/storyboard/keyframes/video/final 全阶段项目 fixture 全部通过，也不证明外部 Provider 或真实媒体已经验证。

---

## 8. 覆盖空白与风险优先级

### P0：兼容与状态写入风险

1. **轻量回退语义容易被误用。** 请求 `--to-stage script` 等非 planning 阶段，实际会到 final；需要专项测试覆盖请求值、实际值、日志值和 dry-run，并确保调用方理解“修复”而非逐阶段回退。相关代码：C `scripts/drama_rollback.py:61-85,161-170,232-302`。
2. **回退完全无专项测试。** 完整模式未来集保护、未开始阶段保护、后续集级联、revision、原子写入和失败恢复都应建立临时目录回归测试。
3. **lint CLI 兼容参数被移除。** 应明确是故意 breaking change 还是疏漏；若需兼容旧自动化，可恢复为原版那样的 no-op 参数，否则应同步迁移所有调用方。相关代码：O `scripts/drama_lint.py:3104-3111`、C `scripts/drama_lint.py:1528-1533`。

### P1：新增核心合同缺端到端保护

4. **H3 Prompt 测试不完整。** 缺 `<d>` 配对、语言标签、块数量、顺序、scenetrans/cutoff、无计划台词、中文媒体标记，以及双文件 SHA-256 和 prompt_sha256 的专项测试。
5. **H3 媒体模式缺完整参数化测试。** 应覆盖 T2VA/I2VA/FL2VA/L2VA/Ref2VA 的输入数、首尾帧角色和位置、Ref2VA 总文件数、音频视觉依赖、每条与累计时长、缺时长等边界。
6. **生成确认只测了局部。** 需要完整覆盖 serial run plan/hash、参数展示与 final_parameters_text、五列分镜、规范化台词、supersedes、attempt、确认和调用时序，以及轻量 planning/首次生成 call ID 复用。
7. **群众没有专项测试。** 请求快照槽位/hash、SRC 来源、CRD approved 文件、成员和外观跨段稳定、storyboard/video 绑定均是高复杂度新增规则，当前 76 项通过不能为这些行为背书。
8. **状态机没有专项测试。** 前集/当前集/未来集、聚合状态、轻量 merged/final 固定形态和 confirmation transport 都应补直接测试。

### P1：原有能力迁移后的回归保护不足

9. 资产完整生成路由、共享/分集复用、STYLE001、关键帧、亮点和跨集余震没有独立测试；拆分后应防止导入或调用条件变化造成“代码存在但未执行”。
10. 成片连续性、QC、字幕开关缺专项测试。duration lock 测试只验证目标时长错误码，不能替代完整 delivery 合同测试。
11. 缺顶层 CLI 测试：stderr/stdout、退出 0/1、issue 去重、warning 下 release_ready=true、各 stage 调度范围都应固定为合同。

### P2：未提交文本规则与静态校验的解释边界

12. 阅读稿和删除复审相关源码、测试未提交，需要与当前参考文档和真实项目样例联合验证，不能只凭单元测试认定模板生态已同步。
13. 阅读稿未完整交叉核对 storyboard JSON 的镜头 ID、时间区间和逐镜时长；若这些一致性属于交付合同，应另增校验和测试。
14. 删除复审只验证逐镜“删除记录”的存在与归属，不判断删除损失是否真实、具体或艺术上合理；内切正则也只是限定语言识别，存在其他表达未覆盖的可能。
15. `release_ready` 是静态校验术语，不是外部运行健康证明。特别是 video 阶段缺段 warning 不阻断、AutoDL 测试全为 fake、视频运行测试不启动进程，发布说明必须保留这一边界。

---

## 9. 最终判断

从代码职责看，当前版没有发现状态、亮点、资产、关键帧、语音、视频或成片等原版大功能区被整块无声删除；主要职责均能找到承接模块。真正需要按“遗漏/变化”管理的是：

- 明确删除的 lint 兼容 CLI 参数；
- Seedance 专属型号、媒体与 membership notice 合同被 H3 合同替代；
- 五段式单 Prompt 转为导演底稿 + H3 成稿双门；
- video_edit 豁免消失；
- 生成确认从 1–2 SEG 改为单 SEG；
- 视频缺段的阶段性 warning/error 分流；
- 轻量时长、状态和回退语义整体改变；
- planning_estimate 不再承担精确锁定时长的含义。

当前测试通过说明已有局部合同和离线运行/恢复逻辑稳定，但覆盖并不与源码规则数量对称。最应优先补齐的是回退、状态机、H3 Prompt/媒体/确认全链路、群众以及 lint CLI 顶层合同；同时应把未提交的阅读稿和删除复审逻辑与参考文档、真实项目样例一起验收。
