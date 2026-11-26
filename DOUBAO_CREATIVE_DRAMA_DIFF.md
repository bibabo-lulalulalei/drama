# `drama` 与 `doubao-creative-drama` 全面差异分析

> 状态：已完成六个专题的内容级对比与主报告整合；结论以 2026-11-25 磁盘快照为准。
>
> 对比日期：2026-11-25。
>
> - 当前版：`<drama-root>`，以下简称 **当前版 / drama**。
> - 对照版：`<doubao-root>`，以下简称 **原版 / doubao**。
> - 比较对象是两侧**磁盘当前内容**，不是仅比较 Git 已提交版本。当前版基线提交为 `b6f10d5`，且 `references/storyboard.md`、`scripts/drama_lint_storyboards.py`、`tests/test_storyboard_reading_lint.py` 有未提交修改，`tests/test_storyboard_deletion_review_lint.py` 为未跟踪文件；原版目录不是 Git 仓库。
> - 本文只分析，不修改两套 Skill 的既有规则。差异分类为：**同名同义 / 表述压缩 / 规则增强 / 语义改变 / 当前版新增 / 原版独有或当前版移除**。

## 1. 执行摘要

当前版不是原版的简单改名或局部补丁，而是一次围绕以下方向的整体重构：

1. **视频模型与生成链替换**：原版围绕 `seedance 2.0 / 2.5`、通用 `text_to_video / image_to_video / media_to_video / video_edit` 和单层中文五段式 Prompt；当前版固定围绕 `H3`，增加“中文五段式导演底稿 → 主 Agent 真实调用 `h3-prompt-writing` → 英文 H3 成稿”的双层 Prompt 合同。
2. **运行环境增加本地分支**：当前版新增 `local-runtime.md`，明确支持 Claude Code、Codex、baocode 和 Python，本地媒体处理改用 `tools/media.py`，允许其调用 `ffmpeg/ffprobe`；原版要求所有媒体处理走 `mediakit` 且明确禁止 `ffmpeg`。
3. **视频执行从“小批量委派”收紧为“单 SEG 受管运行”**：原版一次确认可覆盖连续 `1–2` 个 SEG；当前版每次只编译、确认并运行一个新 SEG，runner 退出后由主 Agent 看图、对账、登记、交付，再编译下一段。
4. **执行后端可插拔但受锁定**：当前版新增 provider 总路由和 AutoDL 专属文档，并在 `串行执行.json` 中显式锁定 provider、适配器版本与哈希；原版没有这层 provider/电源/健康检查/恢复合同。
5. **工程化程度显著不同**：原版只有 `SKILL.md`、27 份 Reference 和两个脚本；当前版有 31 份 Reference、11 个脚本、20 个工具/配置文件及 11 个测试文件。当前版把校验器拆成多个领域模块，并增加真实本地执行工具。
6. **创作规则总体高保真保留**：四个创作参考库中三个字节完全一致，电影大师风格库只有三处 Prompt 语言适配；七轮改稿、12 维人工评估、五类分镜密度、8 镜特定门槛、黄金三秒、每集 3–4 张 KF、人物/场景/PROP/状态和连续性主干都仍在。真正明显删除的创作验收是按秒数计算最低字符数的公式，而不是删掉剧作方法。
7. **当前版不是无条件“更强”**：它增强授权、血缘、防重和恢复，但固定 AutoDL runner 实际只覆盖图片/音频串行子集，不能兑现纯 T2VA、视频参考、源视频 `video_edit` 和无声段；本地也没有完整 ASR/混音/Canvas 等价能力。另有同 queue 修改与同 run-state SHA 锁定之间的确定性续跑冲突。
8. **已有离线验证，但没有云端验收**：当前 11 个测试文件共 76 项实际全部通过，Skill 静态自检为 0 error、0 warning、`release_ready=true`；未真实调用 H3、AutoDL、上传、SSH 或电源，不能据此证明模型可用、画面质量或真实旧任务恢复。

### 1.1 核心行为速览

| 行为维度 | 原版 doubao | 当前版 drama |
|---|---|---|
| Skill 身份 | `doubao-creative-drama` | `drama` |
| 触发范围 | 角色驱动的剧情创作与影视制作 | 描述完全一致，未改变 |
| 默认完整模式 | 全局故事包 → 逐集剧本/资产/分镜/KF/视频/成片 | 核心顺序保留，视频段改为逐 SEG 编译、确认、运行和交付 |
| 轻量模式 | Seedance 2.0 ≤15 秒；2.5 ≤30 秒 | H3 仅 `4–15` 整数秒 |
| 视频 Prompt | 项目语言的固定五段式，一层 | 中文五段式导演底稿 + 英文 H3 成稿，两层 |
| 转换职责 | 主 Agent 编译五段式 Prompt | 主 Agent 还必须真实调用 `h3-prompt-writing`，且不得改变导演事实 |
| 单次生成确认 | 可覆盖接下来连续 `1–2` 个 SEG | 当前一个新 SEG |
| 实际执行 | 受控 subagent 调用通用视频工具 | 固定读取 `串行执行.json` 的一个受管执行器，每次最多一个新 SEG |
| 段间推进 | 前段返回、保存、登记、交付后可继续同批下一段 | runner 退出后必须看图、对账、登记和交付，再编译下一段 |
| 模型/后端 | Seedance 模型与通用视频工具绑定 | H3 模型与 provider 分离；provider、适配器版本和哈希显式锁定 |
| 本地宿主 | 无独立本地合同 | Claude Code / Codex / baocode + Python；有独立本地路由 |
| 媒体处理 | `mediakit`；禁止 `ffmpeg` | 本地 `tools/media.py`；允许其调用 `ffmpeg/ffprobe` |
| 画布 | 非 Mobile 的 Workspace/Canvas 是重要前置和交付通道 | 远端能力存在时沿用；本地无此能力时真实文件交付，不伪造远端 ID |
| 群众 | 无专门 Reference | 新增 `crowds.md`，并纳入完整模式升级和阶段读取路由 |
| 校验 | 单体 lint，围绕一层五段式 Prompt | 模块化 lint，新增 H3 两层 Prompt、真实槽位、台词块等检查 |
| 自动化保障 | 无随附测试 | 11 个测试文件，覆盖多个 lint/运行/恢复/健康门主题 |

### 1.2 同一请求下的行为差异示例

| 场景 | 原版行为 | 当前版行为 |
|---|---|---|
| 用户要做一条 20 秒轻量剧情片 | 若确认使用 Seedance 2.5，可落入其 30 秒轻量上限 | 当前 H3 轻量范围只有 4–15 整数秒，20 秒不能按当前轻量合同直接生成 |
| 当前集已准备好两个连续 SEG | 可用同一轮两张表确认连续 1–2 段，再串行生成 | 每次只编译、确认和运行一个新 SEG；第一段退出、看图、登记、交付后再处理第二段 |
| 已有完整中文五段式 Prompt | 可作为单层视频 Prompt 继续走客观预检 | 只能作为导演事实来源之一；仍需当前版底稿合同和真实 `h3-prompt-writing` 转换，最终提交英文 H3 成稿 |
| 本地有 Python、ffmpeg，没有远端 mediakit | 原版规则要求停止并说明媒体能力缺口 | 当前版本地可经 `tools/media.py` 使用 ffmpeg/ffprobe，仍须遵守该工具的输入和验收合同 |
| 本地没有 Canvas/Workspace | 原版非 Mobile 规则把画布写入/回读作为重要交付链 | 当前版按本地路由真实交付文件；不能把本地路径伪称远端 Item/Workspace |
| 剧情含背景群众且有连续性风险 | 原版依靠一般资产/分镜规则，没有专门群众文档 | 当前版须读取 `crowds.md`，群众连续性风险也会触发完整模式 |
| 生成后主观发现口型或审美问题 | 记录为内部线索，不授权自动重生 | 核心原则保留；当前版同样不因主观观察自动重生 |
| 后端执行中途结果不明 | 按原工具/任务事实排障，不能盲目重复生成 | 当前版还需遵守锁定 provider 的服务端核对、受管恢复与清理规则，不得静默换后端 |

这些例子说明差异会影响**能否进入轻量模式、需要几次确认、提交什么 Prompt、谁执行、失败如何恢复、在什么宿主算已交付**，而不仅是内部文件名不同。

## 2. 范围、方法与判定口径

### 2.1 覆盖范围

本次比较的可维护源码/文档集合为：原版 **30 个文件**（1 个主入口 + 27 个 Reference + 2 个脚本），当前版 **74 个文件**（1 个主入口 + 31 个 Reference + 11 个脚本 + 11 个测试 + 20 个 tools 源码/配置/说明）。原版 30 个文件在当前版均有同名映射；当前版另有 44 个新增文件。`.git/`、`__pycache__/`、`.pyc`、`.gitignore` 和本次新建的分析文档不纳入功能差异基数。真实 `.env`、凭证值和个人配置不属于对比对象；工具分析只记录所需变量名、用途和副作用。

- 主入口 `SKILL.md`：触发描述、流程、模式、确认、交付、状态、工具路由和完成条件。
- 所有同名 Reference：逐条比较正文，而不只比较标题或文件是否存在。
- 当前版新增 Reference：说明其建立的全新合同，以及对旧规则的分流或覆盖。
- CLI 文档：区分完全相同、仅本地路由调整、参数/行为改变。
- Python 脚本与测试：比较校验边界、模块结构、状态回退、提示词与媒体规则、实际测试覆盖。
- `tools/`：比较当前版新增的本地图片、视频、TTS、上传、搜索、媒体、AutoDL 与串行工作流能力；原版没有对应目录，不能把这些误判为文档措辞差异。

### 2.2 判定口径

- **同名同义**：措辞不同，但触发条件、责任主体、输入、输出、阈值和失败行为均相同。
- **表述压缩**：当前版将细节移到 Reference 或删除重复段落，但权威规则仍能在当前版其他文件找到。
- **规则增强**：新增前置条件、记录字段、校验、恢复或禁止行为，原核心目标仍保留。
- **语义改变**：模型、时长、确认范围、工具、责任主体、交付时点、状态机等实际执行结果发生变化。
- **原版独有或移除**：必须检查当前版全部相关文件后，才能判定为真正缺失；若只是迁移，应写明新位置。
- 本文中的“更好/更弱”只针对可观察的执行后果，不把文档更长、更严格自动等同于质量更高。

### 2.3 结论边界

- 这是**当前磁盘内容的静态源码/规则对比**，不是两个历史提交之间的版本演变考据；原版目录没有 Git 元数据，不能从本目录证明某条规则何时、为何改变。
- 不调用生图、视频、TTS、上传、AutoDL 电源或任何外部生成服务，不伪称做过成片质量 A/B。
- 若运行测试，只用于验证当前校验器/本地工作流的客观行为；测试结果不证明剧作、审美或模型画面质量。
- “原版独有”必须经相关当前版文件交叉搜索后才能成立；仅在原版主入口出现、但当前版 Reference 仍保留的，记为“下沉/迁移”，不记为缺失。
- 当前版未提交的分镜与 lint 变更也纳入结论；因此本文是该工作区快照，不应自动视作已发布稳定版说明。

## 3. 文件与结构清单

| 类别 | 原版 doubao | 当前版 drama | 初步结论 |
|---|---:|---:|---|
| 主入口 | 1 | 1 | `name` 不同；正文差异约 72 行新增、101 行删除（以 Git 行差异计，不代表语义条目数） |
| Reference 总数 | 27 | 31 | 当前版净增 4 份 |
| 同名根级 Reference | 17 | 17 | 其中 `assets / control-contracts / delegation / delivery / interaction / keyframes / manifests / planning / scriptwriter / storyboard / troubleshooting / video-batch-confirmation / video` 有变化 |
| 创作参考库 | 4 | 4 | `剧作方法与类型库.md`、`题材亮点与传播库.md`、`题材受众库.md` 内容完全一致；`电影大师风格库.md` 有少量变化 |
| CLI Reference | 10 | 10 | 6 份完全一致；`README.md`、`create.md`、`get-workspace.md`、`workspace-create.md` 有变化 |
| 当前版新增 Reference | 0 | 4 | `crowds.md`、`local-runtime.md`、`video-provider.md`、`video-providers/autodl.md` |
| 顶层脚本 | 2 | 11 | 原版为单体 lint + rollback；当前版为 lint 入口 + 9 个校验/领域模块 + rollback，详表见后文 |
| 测试 | 0 | 11 | 当前版新增分镜、时长、视频确认、运行、恢复、音频、AutoDL 健康门等测试 |
| `tools/` | 无 | 20 个文件 | 当前版新增本地可执行工具、模型配置、示例与说明 |
| `assets/` | 无 | 无 | 两侧均未发现 Skill 静态 assets |

### 3.1 当前版新增文件

- `references/crowds.md`
- `references/local-runtime.md`
- `references/video-provider.md`
- `references/video-providers/autodl.md`
- `scripts/drama_lint_assets.py`
- `scripts/drama_lint_confirmations.py`
- `scripts/drama_lint_domain.py`
- `scripts/drama_lint_highlights.py`
- `scripts/drama_lint_prompts.py`
- `scripts/drama_lint_state.py`
- `scripts/drama_lint_storyboards.py`
- `scripts/drama_lint_video.py`
- `scripts/drama_lint_video_confirmations.py`
- `tests/` 下 11 个测试文件
- `tools/` 下 20 个源码、配置、示例与说明文件：14 个顶层文件，另有 `tools/lib/` 下 `__init__.py`、`env.py`、`h3_domain.py`、`json_state.py`、`media_facts.py`、`video_providers.py` 六个模块。

`tools/` 和 `tests/` 中还存在 `__pycache__/*.pyc` 运行缓存；它们不是可维护源码，不计入上述文件数，也不把只有缓存、没有对应 `.py` 的模块当作当前功能。当前版有而原版没有的 `tools/lib/` 六个模块，已纳入工具链专题分析。

### 3.2 原版有而当前版没有的文件

截至当前清单核对，**没有发现原版单独存在、当前版完全缺失的同名文件**。当前版的文件变化以“新增 + 同名重写”为主，不是删除原版文档。

### 3.3 同名 Reference 的文本变化量

下表的“增/删”是 `git diff --no-index --numstat` 从原版指向当前版的行数，仅用于定位重写密度；一行往往是一整段规则，不能把行数直接当作规则条数或质量评分。

| 同名文件 | 增行 | 删行 | 初步判读 |
|---|---:|---:|---|
| `references/assets.md` | 19 | 30 | 有实质重写，重点核对参考图、状态、场景与本地生图路由 |
| `references/control-contracts.md` | 24 | 29 | 有实质重写，重点核对阶段、确认和版本失效 |
| `references/delegation.md` | 85 | 92 | 高度重写，受控 subagent 流程转为固定配置 runner/本地串行合同 |
| `references/delivery.md` | 19 | 17 | 有实质重写，重点核对本地媒体与最终交付 |
| `references/interaction-ask-video-clarification-ref.md` | 6 | 6 | 改动较少，但可能改变确认来源、选项或模型参数 |
| `references/keyframes.md` | 7 | 19 | 当前版明显压缩，需核验是否只是规则上收/迁移 |
| `references/manifests.md` | 130 | 42 | 变化量最大之一，H3 双层 Prompt、执行记录和 provider 字段显著扩展 |
| `references/planning.md` | 39 | 42 | 有实质重写，需区分创作规则与执行规则变化 |
| `references/scriptwriter.md` | 15 | 14 | 中等重写，需逐条核对剧本内容算法 |
| `references/storyboard.md` | 68 | 80 | 高度重写，且含未提交变更；需重点核对阅读稿和删除复审 |
| `references/troubleshooting.md` | 10 | 18 | 当前版压缩并重路由到本地/provider 恢复 |
| `references/video-batch-confirmation.md` | 64 | 43 | 高度重写，批次范围和 H3 参数合同发生变化 |
| `references/video.md` | 176 | 97 | 变化量最大之一，围绕 H3 双层 Prompt 和执行槽位重构 |
| `references/剧作方法与类型库.md` | 0 | 0 | 完全一致 |
| `references/题材亮点与传播库.md` | 0 | 0 | 完全一致 |
| `references/题材受众库.md` | 0 | 0 | 完全一致 |
| `references/电影大师风格库.md` | 3 | 3 | 仅三处 Prompt 语言/双层层级适配；大师风格机制未改 |

CLI 十份文档中，`create-batch.md`、`get.md`、`ls.md`、`tree.md`、`update-batch.md`、`update.md` 六份完全一致；其余四份变化量为：`README.md` 4/4、`create.md` 4/7、`get-workspace.md` 4/6、`workspace-create.md` 0/2。

### 3.4 内容规模（仅作结构量级参考）

以 `wc -l` 的换行计数为准；末行是否有换行会造成与阅读器行号约 1 行差异，且行数不代表质量。

| 范围 | 原版 | 当前版 | 说明 |
|---|---:|---:|---|
| `SKILL.md` + 全部 Reference | 8,270 | 8,827 | 当前版主入口更短，但新增/扩展 Reference 后文档总量更大 |
| `scripts/*.py` | 3,401 | 6,219 | 原版单体 lint 为 3,187 行；当前版入口缩短、领域模块合计扩大 |
| `tools/` 源码/配置/说明 | 0 | 4,336 | 含顶层 14 文件和 `tools/lib/` 6 模块，不含 pyc |
| `tests/*.py` | 0 | 1,461 | 11 个测试文件，不含 pyc |
| 上述范围合计 | 11,671 | 20,843 | 当前版新增的主要体量在可执行工具、校验模块和测试，不只是提示词变长 |

## 4. 主入口 `SKILL.md` 内容差异

### 4.1 身份与触发描述

- 原版 frontmatter 为 `name: doubao-creative-drama`，当前版为 `name: drama`。
- `description` 逐字一致：短剧、微电影、动画/动态漫、剧情视频、长篇剧本的适用范围，以及普通品牌宣传、UGC、广告、活动预告转交 `doubao-creative-video` 的边界均未改变。
- 因此两者的差异不在“触发哪类创意任务”，而在触发之后采用什么生产链、工具和执行合同。

### 4.2 导演流水线与 Prompt 层数

| 维度 | 原版 doubao | 当前版 drama | 性质与影响 |
|---|---|---|---|
| 主流水线 | 完整分镜后直接“五段式 Prompt 编译 → 集中客观预检 → 生成” | 每个新 SEG 先形成中文五段式导演底稿并预检，再由主 Agent 真实调用 `h3-prompt-writing` 生成英文 H3 成稿，复核后确认并运行 | **语义改变**：当前版多一层可追踪导演事实源和一次 Skill 转换，不是单纯把中文翻成英文 |
| Prompt 权威 | 单层五段式 Prompt 不得发明剧情 | 中文底稿是导演事实权威；H3 成稿只做语言、结构和标签转换，两层都不能发明剧情 | **规则增强 + 语义改变**：防止英文转换阶段改写创作事实 |
| 生成颗粒 | 原版主入口允许按连续 `1–2` 个 SEG 为一批确认并串行生成 | 每次只准备、确认和执行最多一个新 SEG；退出后看图、对账、登记、交付，再编译下一段 | **语义改变**：当前版取消两段共享一次生成确认的做法 |
| 预检对象 | 五段式 Prompt 的段数、镜头覆盖、时间、媒体标记、台词等 | 中文底稿五段 + H3 成稿固定字段、结构、哈希、媒体槽位和 `<d>` 台词块 | **规则增强**：校验对象从一层扩为两层 |

### 4.3 本地宿主、模型和 provider

- 当前版新增“本地宿主执行路由”，原版没有对应章节。
- 当前版明确本地支持 Claude Code、Codex、baocode，要求 Python；执行前先读 `local-runtime.md`，实际模型配置、确认来源、执行主体、媒体处理和文件展示以本地路由为准。
- 更重要的是，当前版明确让 `local-runtime.md` 的本地工具映射**优先于主入口下文及其他 Reference 的远端工具硬门**。因此，即便十份 CLI 文档中六份逐字未变，也不能据此推断两种 Skill 在本地宿主中的实际交付行为完全相同。
- 原版默认远端工具链与 Canvas/Workspace 前置约束更强；当前版在本地没有 Canvas/Workspace 或 `present_files` 时，只要求真实文件交付，并禁止把本地文件冒充远端 Item/Workspace。
- 原版轻量模式上限按模型分为 `seedance 2.0 <= 15 秒`、`seedance 2.5 <= 30 秒`；当前版只写当前唯一视频模型 `H3`，要求 `4–15` 的整数秒。
- 当前版把“视频模型”和“视频生成 provider”分开选择；执行前必须读取 provider 路由和所选 provider 文档，并锁定适配器版本/哈希。原版无独立 provider 层。
- 当前版对需要计费电源的 provider 增加本次电源授权、精确资源确认、单受管进程、健康门、恢复和失败清理；原版没有这些实机资源合同。

### 4.4 模式、阶段和确认范围

- 完整模式、逐集闭环、项目级全局故事包先于分集详细剧本、每集 `3–4` 张高光 KF、阶段确认、默认无字幕等核心框架在两侧均保留。
- 原版完整模式顺序在关键帧之后写“视频参数确认 → 视频片段”；当前版改成逐个 SEG 的“编译并确认当前段 → 单一受控执行器生成 → 退出后看图、登记并交付”。
- 原版每批视频确认可覆盖接下来连续 `1–2` 个 SEG，两个 SEG 共用一张参数表和一张五列表；当前版主入口改为“每个新 SEG 单独确认”，详细表结构及阈值需与 `video-batch-confirmation.md` 联合分析。
- 原版要求规划确认后，只要后续会生成图片/视频，非 Mobile 第一项执行动作立即初始化或复用 Workspace；当前版入口不再保留这项统一硬门，改由 `local-runtime.md` 与 CLI 路由按宿主能力处理。这是**执行前置条件改变**，不能简单视为文字删减。
- 原版完整模式强制条件包括“人物或场景连续性风险”；当前版扩为“人物、群众或场景连续性风险”，与新增 `crowds.md` 对应。
- 原版轻量模式围绕 Seedance 两层时长上限；当前版围绕 H3 `4–15` 秒，并要求两层 Prompt。轻量模式不创建导演总控卡、独立资产/KF 等简化边界基本保留。

### 4.5 Reference 路由差异

- 当前版新增“含背景群众的规划、剧本、资产、分镜、关键帧或视频必须读 `crowds.md`”；原版没有。
- 当前版在规划、视频阶段新增 `video-provider.md` 和所选 provider 文档；原版没有。
- 当前版串行视频交付边界必须读 `delegation.md`，本地宿主差异必须读 `local-runtime.md`；原版虽也有 `delegation.md`，但入口路由未以同样方式列出本地分支。
- 当前版最高优先级前置读取允许“为发现和读取这些 Ref 使用只读文件工具”，原版写成“读完前不得调用工具”。两者实际意图都是禁止在读取前推进任务，但当前版消除了“读取文件本身也是工具调用”的字面自相矛盾。
- 当前版 CLI/Mobile 入口明显压缩，原版关于 Workspace 初始化时机、每个候选/返修结果立即上画布、Media 双通道等长段规则被移到本地/CLI Reference 或被本地分支改写；最终章节需核验哪些仍保留。

### 4.6 全局合同与资产规则

- 两侧共有：素材文字不等于用户指令、主 Agent 受 Skill 约束、上传图片逐张查看与按维度登记、原始素材不删除不覆盖、项目语言静默锁定、真实上游先于下游、已确认版本不覆盖。
- 当前版把“主 Agent 负责导演链路与交付”的长段压缩为“主 Agent 负责导演与交付”，视频只能委派给读取固定 `串行执行.json` 的受控执行器；图片仍可主 Agent 生成。
- 当前版将原版“下游必须已经完成当前环境交付”改写为“已保存、登记、验收且当前可访问”；连续段的 tail 必须是真实生成、看图并登记的 tail。交叉核对 `control-contracts.md` 后确认：视频逐段交付门没有取消，当前段 runner 退出后仍须看图、对账、登记并交付，才能编译下一段；变化的是本地交付通道，不是取消交付。
- 当前版把原版长段资产细则（场景四宫格、PROP 升级、STYLE001 禁区、状态资产、各种工具输入上限）更多地下沉到 Reference，主入口只保留跨阶段硬门。
- 当前版新增群众作为完整模式升级风险与独立必读 Reference；原版无同等专门合同。

### 4.7 视频、声音、字幕和媒体处理

- 原版工具路由直接写 `text_to_video / image_to_video / media_to_video / video_edit`；当前版主入口不再以这些通用工具名为核心，改由 H3、provider 和受管 runner 路由。
- 原版默认 `seedance 2.0 fast` 不可用时停止并重新确认模型；当前版强调 provider 显式锁定、执行器不得静默切换，具体模型可用性和替换规则需看 provider 文档。
- 原版默认每个正常 SEG 为 `native_required`，至少一条 `speech_lines`，台词约占 SEG `55%` 以内、高潮不超过 `70%`，中文普通 `4` 字/秒、快节奏 `5` 字/秒；当前版入口不再重复这些数字，但 `storyboard.md` 正文完整保留，因此是**主入口下沉，不是规则删除**。
- 原版最终 Prompt 是项目语言的五段式；当前版固定先中文导演底稿，再英文 H3 成稿。当前版新增 `<d>` 台词块字词、词序、说话人和句数锁定，并允许规范标点/空白。
- 原版要求 `mediakit`，禁止任何阶段直接使用 `ffmpeg`；当前版本地媒体明确允许 `tools/media.py` 调用 `ffmpeg/ffprobe`。这是明确的**工具与失败策略改变**：本地版不再因没有 mediakit 而必然停止。
- 两侧均要求默认无字幕、逐段清理意外字幕/文字、用户明确要求时才在最终成片烧录字幕、每集只交付一个最终版本；实际工具和校验证据不同。

### 4.8 主入口中的具体数字与硬阈值

下表先比较**主入口本身**；“未重复”不等于全 Skill 已删除，后续 Reference 章节会给出最终去向。

| 数字/阈值 | 原版主入口 | 当前版主入口 | 入口层变化 |
|---|---|---|---|
| 轻量时长 | 2.0 系列 ≤15 秒；2.5 ≤30 秒 | H3 `4–15` 整数秒 | 模型和下限/步长均改变 |
| 高光关键帧 | 每集 `3–4` 张 | 每集 `3–4` 张 | 不变 |
| 规划预览 | 最多 `8` 行五列预览 | 最多 `8` 行五列预览 | 不变 |
| 单次视频确认数量 | 连续 `1–2` 个 SEG，禁止超过 `2` | 当前 `1` 个新 SEG | 从批量授权收紧为单段授权 |
| 台词时间占比 | 默认约 ≤55%；密集高潮约 ≤70% | 入口未重复 | **保留在 `storyboard.md`**；是下沉，不是删除 |
| 中文字符速度 | 普通 ≤4 汉字/秒；快节奏 ≤5 汉字/秒 | 入口未重复 | **保留在 `storyboard.md`**；是下沉，不是删除 |
| H3 媒体输入上限 | 原版入口按 Seedance 2.0 写视频参考 ≤14 秒、音频 ≤15 秒，各最多 3 个，单视频 ≥2 秒 | 当前入口不列旧值；Reference/H3 能力档改为各最多 3、单条 2–15 秒、音视频各自累计 ≤15 秒，Ref2VA 另限 9 图和总文件 12 | 模型合同替换；固定 queue 还禁视频参考 |
| 2.5 媒体输入上限 | 视频 ≤28 秒、音频 ≤30 秒 | 已删除旧值 | 随 Seedance 2.5 和 30 秒长段一起退役，不适用于 H3 |
| 多集风险提示 | 超过 `10` 集须在规划参数表说明漂移风险 | 入口未重复 | `scriptwriter.md` 仍保留 >10 集声明要求；两版都缺同名实际模板，属于共有风险 |
| Prompt 集中修订 | 发现客观问题最多集中修订 `1` 次，再最终校验 | 入口写集中预检，但未重复修订次数 | **保留在 Prompt preflight/lint**：一次集中审阅、最多一次修订、一次最终客观校验 |
| 最终成片数量 | 每集只交付 `1` 个字幕策略对应版本 | 每集只交付 `1` 个最终版本 | 不变 |

### 4.9 Prompt 文件、展示、状态和完成检查

- 原版每个视频只保存 `提示词_SEGxxx_vNN_ep_N.md`；当前版同时保存内部 `编译底稿_SEGxxx_vNN_ep_N.md` 与实际提交 `提示词_SEGxxx_vNN_ep_N.md`，分别登记为 `director_draft_file` 和 `compiled_prompt_file`。`h3_conversion` 同时记录源底稿与成稿 SHA-256，实际提交的 `prompt_sha256` 还须匹配成稿。
- 原版把生成阶段的候选、草稿、未采用版本、返修版本也明确纳入逐项 `present_files` 和非 Mobile 上画布；当前版主入口与本地路由改为“实际采用/应交付”的可见范围。**正式资产/KF 逐项交付和视频逐段交付仍保留，但“所有候选、草稿、未采用结果都必须展示”的绝对要求已弱化**，两者不能混为一谈。
- 当前版把原版按阶段长段展示规则压缩为表格，保留剧本、资产、分镜、关键帧、视频、成片的主要可见范围。
- 两侧均以 `制作状态.json` 为唯一阶段状态源，均使用 `用户确认记录.jsonl`、revision、下游失效和 `drama_rollback.py`；当前版不再保留原版“旧项目镜像字段可保留”的兼容说明。状态脚本仍实现同一七态、阶段顺序和唯一状态源，未发现七态或状态源被替换；消失的是旧镜像文档指引，不是状态机主体。
- 当前版 lint 明确增加导演底稿五段、H3 固定字段、两层媒体标记与真实槽位、`<d>` 台词块等检查；原版主要检查单层五段式 Prompt 与媒体标记。
- 原版 lint 仍说明 `--changed-file` 和 `--fix` 兼容参数；当前版主入口和 `manifests.md` 同步删除说明，且当前脚本 argparse 也已实际删除这两个参数。旧调用会真实报未知参数，属于明确的向后不兼容。
- 当前版完成检查新增“两层 Prompt”；其余逐集确认、真实 FRM、SEAM、主观问题不阻断交付、每集一个成片等核心收口条件基本一致。

### 4.10 主入口中仍然保留的创作骨架

以下内容不是当前版新发明，也不是本次重构的重点变化，两侧基本同义：

- 用户显式要求优先，创意补全只能发生在用户未锁定空间，不能以“效果更好”为由改写要求。
- 角色目标、失败代价、阻力、行动/语言策略、反馈与局势变化构成剧情任务边界。
- 动笔前回答“主角是谁、目标是什么、阻碍是什么、失败代价是什么、为什么必须现在行动”。
- 真实品牌、IP、人物、地点、历史、热点和平台规则需要可靠检索并区分事实与虚构；参考案例只吸收机制，不搬运剧情、台词、镜头或素材。
- 单阶段目标必须登记为交付终点，不能自动升级成完整视频生产；合格上游可以复用。
- 完整模式先锁全局故事圣经、全部分集推进总纲、人物弧、伏笔账本和最终结局，再逐集写详细剧本，不能一开始批量写死所有集。
- 每集按详细剧本、资产、分镜、3–4 张高光 KF、视频、成片的顺序闭环；阶段产物先展示再确认。
- 轻量模式合并中间阶段，但仍需内部十五列完整分镜，不能用最多 8 行五列预览直接代替。
- 项目语言、字幕默认策略、已确认版本不可覆盖、上游修改只使实际受影响下游失效等合同均保留。

因此，**当前版的主要变化不是剧作哲学换了一套，而是同一剧作骨架下的视频模型、执行颗粒、宿主工具、可追溯性和自动检查换了一套**。真正的创作内容删改将在后续 Reference 章节单列。

### 4.11 主入口章节行号定位

| 主题 | 原版 `SKILL.md` | 当前版 `SKILL.md` |
|---|---:|---:|
| 用户指令与创意边界 | L8–21 | L8–21 |
| 主流水线 | L23–35 | L23–37 |
| 本地宿主/provider | 无独立章节 | L39–45 |
| Ref 全量前置读取 | L37–39 | L47–49 |
| 交付与确认前置路由 | L41–53 | L51–56 |
| 适用边界 | L55–70 | L58–73 |
| 模式与阶段 | L72–102 | L75–105 |
| Reference 路由 | L104–125 | L107–130 |
| 全局执行合同 | L127–141 | L132–142 |
| 阶段内容硬门 | L143–151 | L144–154 |
| 资产与视觉参考 | L153–167 | L156–161 |
| 视频、声音与 Prompt | L169–189 | L163–170 |
| Prompt 文件与可见交付 | L191–216 | L172–195 |
| 状态、文件与自动校验 | L218–258 | L197–237 |
| 工具路由 | L260–276 | L239–247 |
| 返修与完成检查 | L278–293 | L249–264 |

## 5. 创作、规划与剧本 Reference

> 完整逐条报告：[01-creative-planning-script.md](analysis/doubao-diff/01-creative-planning-script.md)。

### 5.1 总体判断

当前版对这部分的处理是：**保留创作方法，替换执行环境，松绑代理估算对正文的机械控制，补强事实与授权链**。没有发现大规模删除人物、关系、场景、信息、台词、分集、结局和改稿算法的证据。

| 文件 | 结论 |
|---|---|
| `planning.md` | 创作机制算法主体保留；实质变化为时长双轨、H3/provider、双层 Prompt、单 SEG 确认和群众事实源 |
| `scriptwriter.md` | 主体质量合同保留；真正删除动态最低字符公式和评审排他句，2000–3000 字降为非门禁参考 |
| `剧作方法与类型库.md` | 字节完全相同 |
| `题材亮点与传播库.md` | 字节完全相同 |
| `题材受众库.md` | 字节完全相同 |
| `电影大师风格库.md` | 仅 3 行替换，均为中文底稿/H3 英文成稿的语言编译适配 |

### 5.2 `planning.md`：保留的创作算法

以下规则在当前版仍有明确正文承接，不是只剩主入口口号：

- 未锁定方向时内部恰好生成 **3 个本质不同主机制**，每个配置 1–3 个同源辅助机制；用户已锁定时不得另造三个故事方向。
- **反换皮测试**：抹去姓名、年代、地点、道具、滤镜和媒介标签后，仍比较“策略→反馈→局势变化→高潮证明”；只换职业或证据道具不算本质差异。
- **可持续测试**：至少推演一轮“目标→阻力→策略→反馈→新局势”；多集还检查建立、变奏、升级、回收；依赖巧合、反派无理由犯错或临时新增设定者淘汰。
- 分层筛选顺序仍是用户锁定/禁用项、核心证明、连续性、生成稳定性；不能为了生成方便覆盖创作匹配。
- 一句话故事核心仍须包含主角、外在欲望、最大阻力、时间压力、失败代价和反讽/刺激点。
- 类型、呈现形态、交叉策略、项目签名、至少两个不同维度亮点支柱及其跨集回收规则均保留。
- 可观察风格仍须拆成媒介、构图、光线、色彩、材质、镜头质感、字体/版式和剥离项，不能只写“电影感/高级感”。
- 六步节奏推导、不可移动节点、信息/动作负载、唯一主重拍、切镜选择和 `1–5` 强度序列均保留，仍禁止套固定秒段。
- 多集先锁全局故事圣经、全部分集推进总纲、人物弧、伏笔账本和最终结局，再逐集详细创作。
- `verified_facts / pending_facts / assumptions` 仍分开；真实人物、品牌、热点和平台规则须检索并记录日期。

### 5.3 `planning.md`：实质变化

| 主题 | 原版 | 当前版 | 实际影响 |
|---|---|---|---|
| 轻量规划中的台词 | 规划不写完整台词 | 轻量唯一一次确认前，五列预览必须列出本条实际使用的全部台词、旁白和画外音 | 因没有独立剧本确认门，把台词授权前置；完整模式并未因此省略正文 |
| 时长语义 | 以精确 `episode_durations_s/total_duration_s` 为主 | 新增 `duration_semantics` 和 `estimated_*`；区分 `planning_estimate` 与 `user_locked` | 代理估算只用于规模/预算；用户锁定和轻量唯一视频仍须精确闭合 |
| 五列预览时间 | 从 00:00 到精确总时长连续覆盖 | 仅轻量或用户锁定精确时长时强制；代理规划可用连续剧情顺序的预估节点区间 | 防止为凑总秒数增删剧情，不是取消开端/发展/高潮/结尾 |
| 创作量失配回退 | 缩小事件范围以适配确认时长，不删高潮证明 | 可调整事件范围或更新预估区间；不得删高潮证明、必要动作或反应 | 当前版对内容保护的措辞更完整 |
| 默认模型 | 生图 `seedream 5.0 flash`；视频 `seedance 2.0 fast` | 生图按真实本地配置默认 gpt-image；视频固定 H3；无法核实时 `pending` 并停在参数确认 | 执行模型迁移，不是剧作算法变化 |
| H3 输入阈值 | Seedance 2.0/2.5 的旧视频、音频和数量上限 | 每 SEG 4–15 整数秒；最多 9 图、3 视频、3 音频、总文件 12；单个音视频 2–15 秒，各自合计 ≤15 秒；有音频必须同时有图或视频 | 真实技术合同改变，旧阈值不可套用 |
| provider | 无独立选择 | `model_plan.video_provider` 只能取真实注册 provider；更换 provider 不授权改剧情/分镜/SEG/画幅 | 执行后端成为独立确认事实 |
| 生成确认 | 每批连续 1–2 SEG | 每次当前一个新 SEG；真实尾态后再编译下一段；恢复/下载/补 tail 不新增确认 | 授权收紧，同时避免只读恢复被误当新生成 |
| Prompt 语言 | `video_language` 同时控制人声和 Prompt 自然语言 | 新增 `director_draft_language` 与 `compiled_prompt_language`；中文底稿、英文 H3 成稿；`video_language` 收窄为人声/音色 | 对白、歌词、专名和画面原文仍保留原语言，不能随英文编译翻译 |
| 群众 | 无独立 `crowds[]` 预测合同 | 单镜/复现群众均预估可见外观；模糊群体可整体描述，可辨认成员逐人锚定；无台词也不能省略 | 新增视觉事实源，轻量继承事实但不建完整数据卡 |
| 重大修改 | 时长、模型等变化通常回退规划 | 非锁定预估区间细调不自动使下游失效；用户锁定精确时长、provider、核心方向等仍按真实影响失效 | 减少无意义全链回滚，不取消真实变更的失效 |
| 超 60 秒显示 | 必须同时写精确秒数与分钟换算 | 当前“可同时”写；预估区间明确标“预估/参考” | 展示强制性降低，用户锁定值仍需精确 |

### 5.4 `scriptwriter.md`：高质量保留项

当前版仍保留：

- AI 可拍性限制及应对：微表情不能独自承担反转；复杂动作拆为“起势→接触→受力→结果→反应”；多人互动明确主行动者、关系轴线和反馈；不得用暗调掩盖塑料感。
- 项目级全剧完整剧本与 `ep_N` 详细剧本的双层结构；二者不能互相替代。
- 每场“角色目标→现实阻力→采取策略→反馈→局势变化”；开尾不变且无新增信息的场景必须删除或重写。
- Markdown 是创作正文权威，`script_contract_ep_N.json` 是带来源哈希的派生合同，不能维护两套独立剧情。
- 台词证据链：“声明→事实来源/铺垫→可见画面/动作/道具/结果→揭示场次→局势后果”；角色所信不等于故事事实。
- 项目事实与假设文件、项目数据卡、每集固定创作产物和单集创作卡 13 字段均保留。
- 人物外壳/内核/执念、错误信念、动机、底线、越界选择、成长弧、行为签名；反派独立目标、资源和合理性；关系变化必须绑定事件。
- 商业对话型短剧每集传播句候选及非语言作品的视听母题例外；高潮/结局必须由前文规则与人物选择造成。
- 逐集亮点账本，包含铺垫、兑现动作、状态变化、题材职责、呈现表达和高潮余震。
- 专业分场、场景稳定 ID、`△` 客观动作、VO/OS 声音主体及职责。
- 用户台词三层 `source_text/display_text/spoken_text`；除标点规范外不得删改、拆合、调序或换词。
- **七轮改稿**（前提、结构、人物、关系、场景、台词、导演/可拍）和 **12 维人工质量评估**均保留，前一轮阻断问题未解决不能提前润色后一轮。
- 修改只使真实受影响阶段/稳定 ID 失效；改结局仍须回查伏笔、因果、人物弧、相关 SEG 和最终音轨。

### 5.5 `scriptwriter.md`：真正删除与语义调整

| 项目 | 原版 | 当前版 | 判定与影响 |
|---|---|---|---|
| 动态最低字符公式 | `max(120, min(800, 时长秒数 × 4.5))`，低于下限不得进分镜 | 明确不按任何时长公式设最低字数，不执行字符数下限校验 | **真正删除**。失去客观薄稿安全网，但避免自然主义/极短作品机械凑字 |
| 正文完整性门 | 字数达标仍需主线、目标、阻力、行动、反馈、变化、高潮和结果 | 每场目标/阻力/策略/反馈/状态变化；全集开端/推进/高潮/结果/必要反应；具体动作、对白、反应和结果作证据；薄稿和自评分不能通过 | **不是取消验收，而是改为正文事件证据门**；更依赖主 Agent 真读正文 |
| 项目级 2000–3000 字 | 写作建议 | 仅为常见篇幅参考，不是上下限或准出条件 | **字数导向弱化**，固定子章节和产物范围未删 |
| 剧情梗概字数估算 | 按实际语速、动作和反应动态估算 | 1–3 分钟、5–10 分钟等只帮助理解容量，不换算字数 | 删除时长到字数的推导，不取消事件完整性 |
| 角色音色 | 每个出镜、画外角色和叙述者都配置固定音色 | 只有实际承担可辨识人声者绑定 voice_id；无声角色/无台词群众不创建 VOICE | 资产职责收窄；有人声者仍须稳定音色 |
| 群众数据卡 | 无 `crowds[]` | 登记全部背景人物外观与状态，包括单镜无台词者；升级 CHR 时继承外观和成员映射 | 当前新增连续性事实 |
| 评审排他句 | “不再执行第二套单集检查或独立可拍性评分” | 删除排他句，仍保留统一 12 维阅读全文 | **流程排他性删除**，不是七轮改稿或可拍性评估删除 |
| 剧本头时长 | `单集时长：[X 分钟]` | 用户锁定写精确值；代理规划写“预估 X–Y 分钟（参考）” | 防止把代理估算伪装成用户承诺 |

### 5.6 四个创作库的具体内容差异

- **三个字节一致库**保留了结构模型、人物引擎、关系矩阵、信息差账本、场景策略、系列发动机、55 个题材发动机、12 个亮点维度、五类开场/反转、受众心理机制、情绪曲线和合规门。它们不是当前版新加，也没有当前版删减。
- `电影大师风格库.md` 只改三类句子：视频导演语言改为中文底稿；英文检索词先转中文自然底稿再由 H3 成稿等价转译；`video.md` 的权威范围扩为两层 Prompt。
- 该库其余“不强制选大师、风格拆为可观察机制、混搭不超过两位、禁止整段堆关键词、慢动作/定格不得用于填时长”等内容均保留。

### 5.7 两版共有的创作文档风险

这些不能算作当前版新增回退，但会影响执行：

1. 两侧 `scriptwriter.md` 都引用“长篇幻觉风险声明”模板，却未找到同名实际章节；超过 10 集时不同执行者可能自编不同声明。
2. `剧作方法与类型库.md` 指向 `剧本_分集创作说明_ep_N.md`，而正式关系矩阵文件在 `scriptwriter.md` 中是 `剧本_人物关系张力矩阵_ep_N.md`，存在文件名不一致。
3. 电影风格库个别“用构图/冷色掩盖 AI 缺陷”的示例，与同文件“不得掩盖结构/生成缺陷”存在措辞张力，两版共有。
4. “金句可选”与商业对话型“每集至少一句传播句候选”需按作用域共同理解，不是版本差异。
5. 创作库开头要求规划/剧本必读，末尾又写按需读取；两侧主入口的 Reference 表可解决主流程歧义，但文本本身不够一致。

## 6. 资产、群众、分镜与关键帧

> 完整逐条报告：[02-assets-storyboard-keyframes.md](analysis/doubao-diff/02-assets-storyboard-keyframes.md)。当前 `storyboard.md` 按磁盘未提交版本纳入比较。

### 6.1 总体判断与文件映射

| 文件 | 核心结论 |
|---|---|
| `assets.md` | CHR/SCN/PROP/VOICE/STYLE、版本、复用、真实传图、三视图/四宫格/状态板等主干保留；新增 CRD、精确比例适配和先复用 VOICE |
| `storyboard.md` | 五类密度、动作单元、8 镜特定门槛、黄金三秒、运镜家族、表演/声音/色彩、十五列、SEAM 主干保留；H3、双层 Prompt、阅读稿和 tail 角色改变 |
| `keyframes.md` | 每集 3–4 张、K0–K5、I2I、SCN 必传、300–500 字、逐张验收均保留；新增群众调度和 CRD 参考 |
| `crowds.md` | 当前新增 87 行独立合同，贯穿剧本、资产、分镜、KF、视频和 manifest；原版没有 |

三份旧 Reference 顶部的“本 Ref 关键要求”集中摘要均被移除，但对应规则大多仍在正文或其他文件；这属于**摘要去重/搬迁**，不能据此判为算法丢失。

### 6.2 `assets.md`：保持不变的资产创作主干

- 制作前仍先查 `asset_registry.json` 与历史 `asset_usage_ep_N.json`；approved 同身份/同状态直接复用，不重复生成，未来集只保留计划。
- 外部图仍按身份/状态、空间/道具、构图/姿态、媒介、画风、色彩、光影、材质/颗粒/纸感、文字拆分，并分别登记 `lock/weak/exclude`。
- 相同 basename 或相同本地路径不自动视为同一输入；URL、附件 ID、消息位置或顺序不同仍分别登记 `SRCxxx`、哈希并逐张查看。
- 没有有效视觉维度才 `image_gen`；命中必要维度必须 `image_edit` 并真实传图。只写 ID、planned path 或“参考某图”都不算执行。
- CHR 类型、真人/动漫/动物等 `representation_type`、16:9 中性角色设定板、左 1/3 头部特写、右 2/3 正/严格 90°侧/背三视图、七组描述和角色区分键均保留。
- SCN 建立条件、近景/远景/平视全景/远景俯拍四宫格、每场景 3–5 个具体锚点、灯光状态与结构版本的区分均保留。
- STYLE001 仍只锁主色、线条、光线、材质、构图、景深、颗粒等视觉语言，不得夹带剧情角色脸、具体服装或剧情道具。
- PROP 仍须同时满足复现前提与剧情职责条件；一次性被拿起/损坏的物件不会自动资产化。多状态可共用分区状态图，但下游必须指向具体分区。
- `generation.prompt_path` 与 KF `prompt_path` 均仍在 `manifests.md`；摘要中不再出现不等于字段删除。
- 版本状态 `draft/reviewed/approved/rejected/superseded`、换图递增 `_vNN`、只使真实下游失效等原则保持。

### 6.3 `assets.md`：真实语义变化

| 项目 | 原版 | 当前版 | 影响 |
|---|---|---|---|
| 群众 | 没有 CRD | 新增 `CRDxxx`，进入扫描、资产 ID、版本、展示、复用和依赖失效 | 复现群众获得与 CHR 同级的可追溯性，但不机械生成三视图 |
| 资产展示顺序 | 人物→场景→道具→音色→风格 | 人物→群众→场景→道具→音色→风格 | 群众需要独立可见交付，不能混在场景背景里 |
| 当前集三视图范围 | 每个当前集出场角色 | 每个需要稳定身份的独立角色 | 可辨认 CHR 仍需完整身份板；远景/单镜群众不再机械套 CHR 工作量 |
| 精确比例 | 原平台工具直接按参数处理 | `--ratio` 只就近选尺寸；精确比例另用 `fit-image`，默认 pad，crop 需明确授权 | 避免标称比例误导和静默裁切；适配文件与原图均须追溯 |
| VOICE 生成 | 每个计划人声主体生成一个专属音色 | 先复用 approved VOICE，缺可用版本才生成；无台词群众不建 VOICE | 减少重复生成，视觉资产与可辨识人声解耦 |
| 样音 | 约 5 秒、1–2 句短台词，只锁声线 | 保持；不代替正片完整配音 | 没有扩大 TTS 样片职责 |
| 图片 Prompt 语言 | 部分位置用 `video_language` | 改用 `output_language`；视频人声仍用 `video_language` | 分离普通文档/图片语言与视频人声/音色语言 |

### 6.4 `storyboard.md`：密度与镜头算法没有缩水

当前仍保留五种密度：`high_density_short / dialogue_emotional / suspense_build / micro_film / custom`。选择依据仍是“哪类内容最不能被压缩，压缩后最先损坏核心证明”，不是题材名或平台名。

- 事件单元仍须改变信息、行动、关系、危险、空间或道具状态；动作单元仍须含起点、过程、接触/反馈、可见结果。
- **8 镜下限仍只属于 `high_density_short + edited + 15 秒`**，不是所有 SEG 的通用硬指标；不得复制反应、数字裁切或拆断动作凑数。
- **黄金三秒**同样只用于上述组合，仍须形成“异常/承诺→主体行动→反馈并改变局势”的因果链。
- 一镜到底仍是唯一单镜例外，禁止硬切、隐藏切、遮挡伪切、匹配剪辑和时间跳跃；至少三个连续可观察节点。
- 当前进一步明确：不得先定镜数或统一单镜秒数，不得先排 SHOT 再反填动作单元；2–5 秒只是连续微动作组预算，不是 SHOT 默认时长。
- 同一 SHOT 建立画面后又明确“切至/切换至另一观看位置”必须另建 SHOT；连续拉远、变焦和焦点转移不因景别变化就误算切镜。
- 原版已有删除测试，当前强化为每镜写自己的具体删除损失，不能用“本段镜头均有职责”概括。
- 运镜十家族和阈值保留：4–5 镜默认至少 2 家族，6 镜及以上至少 3；单一家族默认不超过 50%，axial 推拉合计也不超过 50%，有理由例外仍可登记。
- 动作 30%–70% 相位切出、四类 tail mode、最终段 0.6–1.0 秒稳定结果帧、表演谱/AU、三层声音、BGM 退点、色彩因果均保留。
- 台词预算仍包含朗读、句前起势、停连、句后反应和必要动作；普通段人声约 ≤55%，高密度约 ≤70%，中文普通硬上限 4 字/秒、快节奏 5 字/秒。

### 6.5 时长、阅读稿和十五列的实际变化

**时长：**原版 Seedance 2.0 系不超过 15 秒、2.5 可到 25–30 秒；当前所有 SEG（含独立 bridge）固定为 H3 **4–15 整数秒**，默认 10–15 秒。不足 4 秒的尾数必须在自然切点重新分配相邻 SEG。`planning_estimate` 不与内部执行层机械相等，但 SHOT 总和仍须闭合到 storyboard，用户锁定和轻量唯一视频仍须精确匹配。

**用户阅读稿：**从较宽松示例改为严格结构：

```text
总览 → 本集故事提要 → 章节 → 片段 → 逐镜条目
```

- 总览写实际总秒数、画幅、画风、章/片段/镜头真实总数、字幕与画面文字策略。
- 禁止 Markdown 表格、JSON、哈希、字段名和校验结果。
- 片段标题使用可读“场景·片段名＋绝对起止时间＋实际镜头数”，不得以 `SEGxxx` 作为用户标题。
- 每镜固定 `[景别｜视角｜主运镜｜机位/角度]`，并写动作与反馈、`声音：`、`人声：`、`切入：`、`切出：`。

**不同层的台词格式不可混用：**

| 层 | 台词形式 |
|---|---|
| 用户阅读稿 | `说话人：“完整原文”` |
| 内部中文十五列 | `说话人：{完整台词}` |
| 中文五自然段导演底稿 | `{spoken_text}` |
| 中文结构化 Ref2VA 底稿 | `dialogue_refs.spoken_text` |
| H3 英文成稿 | `<d>[语言] 原文</d>` |

内部十五列的名称和顺序完全保留，群众通过 JSON 字段绑定，**没有增加第十六列**。轻量仍生成内部十五列，不创建完整模式配套文件。

### 6.6 `reference_input_plan` 与连续 tail 的关键语义修正

计划数组仍不是实际传图证据；每项仍需 `order/role/planned_source/opening_binding/adopt/exclude/required`。当前新增或扩展的角色包括 `previous_tail_reference`、`first_frame`、`last_frame`、`crowd_reference`，planned source 可指向 CRD。

| 连续情形 | 原版 | 当前版 |
|---|---|---|
| continuous 的上一段 tail | 统一写 `previous_tail_as_start_frame` | Ref2VA 通常写 `previous_tail_reference`，省略 `frame_position`，只继承 0 秒事实，不宣称硬首帧 |
| 单图 I2VA 实际开场 | 未精确区分 | 才使用 `previous_tail_as_start_frame + frame_position:first` |
| 真正首尾帧 | 未建立当前精确模式表 | `first_frame/last_frame` 与 `frame_position:first/last` 配套 |
| 其他参考 | 容易混称首帧 | 身份、场景、高光、群众等普通参考不得冒充首尾帧 |

这不是放松 continuous：真实 tail、来源、看图观察仍是硬门。它修正的是“普通参考图”和“API 强制首帧”的混称。

### 6.7 `keyframes.md`：核心保留与新增

- 完整模式仍每集固定 **3–4 张**，按整集重要性和漂移风险选点，不按 SEG 配额；多 SEG 项目单段通常 0–1 张，只有两个独立集级峰值且无法拆分时最多 2 张。
- 首段不生成首帧 KF，任何 SEG 不生成尾帧 KF；KF 是生成前高光目标，FRM 是生成后事实。
- 高光仍优先信息揭露、证据出现、动作接触、关系变化、危险逼近和不可逆选择；排除普通首尾、角色展示和纯氛围画面。
- 单帧不得写“先、再、随后、从 A 到 B”；不支持有序多关键帧时只作高光参考并写时间点目标。
- 画面创作十法、主体描述 **300–500 字**、K0–K5 六类参考、固定 `image_edit`、存在直接相关 approved 资产即真实传入、已登记 SCN 内必须传四宫格、逐张生成/展示/验收/用户确认均保留。
- 当前新增：关键角色与可辨认群众成员逐人写位置、距离、朝向、视线、手部和持物；模糊群体按区域、组成、外观、朝向、反应描述；recurring CRD 图必须真实传入 `image_edit`。
- 没有新增“K6”不代表群众未覆盖；CRD 由独立规则和 `crowd_reference` 承接。
- 原版 `seedream 5.0 pro` 与会员/额度标签被真实本地配置和可靠费用信息替代。

### 6.8 新增群众合同的实际内容

`crowds.md` 要求：

1. **所有背景群众都描述外观**，包括单镜、无台词、无独立剧情功能者。远处模糊群体写人数/密度、年龄体型分布、发型轮廓、服装配色、群体特征、画面区域、行动反应；不可辨认脸不逐人编造。
2. 可辨认成员逐人登记稳定 `member_id`、外观和位置锚点；有独立台词、重要特写或关键因果行动者升级 CHR，并保留 `member_id → character_id` 映射，不得换脸。
3. 数据容器为 `project_data_card.crowds[]`、`storyboard.segments[].crowds`、`shots[].crowd_ids`、视频 `segments[].crowds`；没有群众也必须写 `[]`。
4. 字段包含 `crowd_id/state_id/continuity_scope/visibility/count_or_density/appearance/members/screen_position/action/allowed_changes/reference_source_id`；外观六项均须非空。
5. `continuity_scope` 为 `shot|recurring`，`visibility` 为 `indistinct|identifiable`；可辨认者必须有 members。精确人数服从用户锁定，不得静默改近似。
6. 同一 `crowd_id + state_id` 下人数/密度、群体外观、成员外观稳定；位置、动作、视线可按镜头变化。变装、伤妆、成员变化或时间跳跃须新 state、原因、版本与必要参考。
7. recurring 必须绑定 approved CRD 或已验收 SRC；视频执行时真实传 `crowd_reference`，source、file、order、adopt/exclude 一致，并用 dry-run/task slots 和实际 bytes SHA 核验。
8. 多群体可共用一张成员可辨认的已验收图，不伪造槽位；群众图是普通参考，不得为凑模式标成 first/last frame。
9. 轻量仍描述全部群众外观，但不建独立资产审批包；若需新增参考、逐阶段审批或有连续性风险，必须返回规划并切完整模式。
10. lint 只检查结构、ID、稳定快照、文件/批准引用和槽位哈希；英文翻译准确性与实际换脸/复制/无因消失仍需人工看图。

### 6.9 当前版残留风险

- `assets.md` 的展示顺序已包含群众，但阶段交接总述和最终确认句仍只列人物、场景、道具、音色、风格，**确认范围文案未完全同步 CRD**。
- `storyboard.md` 一处仍有“用户指定模型例外”，与唯一 H3 冲突；实际应以后者及 `tools/h3.json` 为准。
- tail 的 Ref2VA 新语义已经明确，但后文仍有“0 秒首帧视觉基准”措辞，容易被误读成 I2VA 硬首帧；宜理解为“0 秒连续事实视觉基准”。

## 7. 视频、确认、委派、provider 与故障恢复

> 完整逐条报告：[03-video-provider-delegation.md](analysis/doubao-diff/03-video-provider-delegation.md)。该专题是文档合同对比，未执行云端生成、开关机、联网恢复或下载；代码实现边界另见第 10 节。

### 7.1 执行架构从两层变四层

原版主要是“主 Agent 创作与确认 → subagent 调原平台视频工具”；当前版变成：

1. **创作层**：主 Agent 负责剧本、分镜、资产、真实输入、SEAM/FRM、看图和交付。
2. **模型编译层**：中文五段式/结构化导演底稿，真实调用 `h3-prompt-writing`，得到英文 H3 成稿；只提交后者。
3. **串行执行层**：每集固定 `串行执行.json` 和 `video_run.py`，每次最多一个新 SEG，段间主 Agent 看图反馈。
4. **provider 层**：模型、provider、协议分离；适配器与 cloud config 哈希绑定；AutoDL 另有电源、健康、恢复、下载与关机生命周期。

| 文件 | 当前相对原版的主要变化 |
|---|---|
| `video.md` | Seedance/单层 Prompt/1–2 SEG/subagent/mediakit → H3/双层 Prompt/单 SEG/固定 runner/本地媒体 |
| `video-batch-confirmation.md` | 连续 1–2 SEG 共用一次确认 → 恰好一个 SEG，并绑定 provider、运行文件及代码/配置哈希 |
| `delegation.md` | 强制异步 subagent 与五个 `allow_*:false` → 固定 queue、operation、进程、锁和状态证据 |
| `troubleshooting.md` | 保留最早责任层级和部分成功；新增 `submission_unknown`、原任务 GET 恢复、持久化归属和双层 Prompt 诊断 |
| `video-provider.md` | 当前新增通用模型/provider/协议、注册、适配器接口、恢复和可选电源合同 |
| `video-providers/autodl.md` | 当前新增 AutoDL 配置、独立电源授权、健康、提交、防重、轮询、恢复、下载和清理 |

### 7.2 模型、时长、媒体输入的真实变化

| 项目 | 原版 | 当前模型层 | 当前固定 AutoDL queue 的实际边界 |
|---|---|---|---|
| 视频模型 | 默认 `seedance 2.0 fast`；可明确指定其他 2.0；2.5 需会员确认 | 唯一 H3 | 当前注册 provider 只有 `autodl` |
| 单 SEG | 2.0 默认 10–15 秒、≤15；2.5 优先 25–30、≤30 | 默认 10–15；硬区间 4–15 整数秒 | 同模型层；不足 4 秒尾数须重划 |
| 无媒体 | `text_to_video` | T2VA，零媒体 | **不能正常走**：固定 queue 每段至少一图 |
| 普通图片 | `image_to_video`，真实传图 | 普通身份/场景/KF/群众等通常 Ref2VA | 支持图片子集，但非首段第一图强制前段真实 tail |
| 真实首/尾帧 | 主要通过 tail 角色描述 | I2VA/L2VA 各仅一图；FL2VA 恰好两图并有 `frame_position` | 固定 queue 的串行 tail 规则优先，不是任意模式自由调度器 |
| 视频参考 | `media_to_video` 最多 3；单个 ≥2 秒；2.0 合计默认 ≤14，2.5 ≤28 | Ref2VA 最多 3；单个 2–15 秒；合计 ≤15 | **禁止视频参考** |
| 音频参考 | 最多 3；单个 ≥2 秒；2.0 合计 ≤15，2.5 ≤30 | 最多 3；单个 2–15 秒；合计 ≤15；有音频须同时有图或视频 | 支持本地音频，但固定 queue 强制输出音轨 |
| Ref2VA 总输入 | 无此模式名和当前统一上限 | 最多 9 图、3 视频、3 音频，总文件 ≤12 | 实际只覆盖图片/音频子集 |
| `video_edit` | 一个源视频的原生定点编辑，保持原比例/时长/人声/音色/口型关系 | H3 无原生编辑时按源视频 `<Video N>` 的 Ref2VA 参考重生成，须说明并重确认 | 因禁视频参考，**固定入口不能兑现该路径** |

两版共同的硬门仍是：必要人物/状态/SCN/PROP/KF/tail 命中即真实传入；缺输入、超上限或后端不支持时停止，不得删掉关键参考继续生成。

当前还新增请求专用音频派生：从已核验静音区间用 `cut-audio` 生成新 WAV，保留原音和双侧哈希、删除区间、实测时长及全量解码事实；queue 字节变化须重新预检和确认。

### 7.3 双层 Prompt 的精确职责

**原版：**`提示词_SEGxxx_vNN_ep_N.md` 就是实际提交文本，五个自然段依次承担：

1. 输入资产定位与 0 秒基准。
2. 参考主体绑定与生成目标。
3. 逐时间段动作、声音与脚本。
4. 转场与尾态收束。
5. 全片一致性与禁区。

“五段式”是五层信息合同，不是五个镜头或五个时间段；第三段含逐镜时间轴，每镜恰好编译一次，画幅不写 Prompt。

**当前版：**五段式只约束中文导演源，不直接约束英文成稿结构。

- 中文底稿：`编译底稿_SEGxxx_vNN_ep_N.md` / `director_draft_file`。
- 英文成稿：`提示词_SEGxxx_vNN_ep_N.md` / `compiled_prompt_file`。
- 主 Agent 必须真实执行 `Skill(skill="h3-prompt-writing", args=<完整交接包>)`；不得手写同格式文本冒充 Skill 调用。
- `h3_conversion` 保存 Skill 名、宿主通道、`invoked=true`、带时区时间、源底稿 SHA-256 与成稿 SHA-256；任一层字节变化即失效并重转。
- 底稿先集中预检，成稿再查结构、槽位、台词和时长；主 Agent 还要人工回读动作桥、运镜、表演、声音、色彩、尾态和否定指令，防止英译反转或弱化。
- 普通 H3 成稿使用 `integrated_multimodal_description / overall_soundscape / non_diegetic_music`；帧模式另有开场对齐指令；Ref2VA 使用 `subject_definitions / summary / retention_analysis / detailed_description` 等结构。
- Ref2VA 中文源也可用“前置段＋四个固定二级标题”的结构化形式；它仍不是实际提交成稿。

### 7.4 `<d>` 台词、说话人和标记迁移

| 项目 | 原版 | 当前版 |
|---|---|---|
| 中文可听文本 | `说话人：{spoken_text}`，逐字进最终 Prompt | 自然段底稿仍用 `{}`；结构化底稿用 `dialogue_refs.spoken_text`；成稿为 `<d>[语言] 原文</d>` |
| 成稿保真 | 无第二道 H3 台词合同 | 每条恰好一个 `<d>`，块数等于条数；只允许规范标点/空白，不翻译、不增删、不调序、不换人、不拆并句 |
| 说话人 | 角色名/VOICE ID 与 voice_anchor | H3 用稳定 `(Sx)`，按实际发声顺序分配并跨镜复用；VOICE 音频复用同一编号 |
| 音色锚点 | 无音频输入不等于静音；台词附近逐字复用 | 原则保留；英译只转换年龄/性别表达、音高、音色、语速、口音等识别短语，不新增身份 |
| 媒体标签 | `<图片N>/<视频N>/<音频N>` | 中文自然段沿用；成稿为 `<Picture N>/<Video N>/<Audio N>`；编号始终匹配真实 order |
| 字幕源 | `【】` 只作后期字幕源 | 只允许在中文底稿，禁止进入 H3 成稿 |
| BGM/环境声/画面文字 | `()`、`<>`、`“…”` | 分别归入 `non_diegetic_music`、`overall_soundscape`、画面描述；画面文字内容保留原语言 |

四类人声 `on_screen_dialogue / narration / voiceover / inner_monologue` 仍由视频模型原生生成；旁白、画外音和内心独白明确画面人物不开口。生成后静音、漏句、串人、口型或类型错误仍是用户主动返修线索，不自动重生。

### 7.5 SEAM/FRM 保留，反馈时点前移

两版共同保留：

- planned SEAM 是生成前计划，FRM 是生成后事实；不能在分镜阶段伪造实际 FRM。
- `continuous` 必须有上一段真实 tail；`elliptical` 不强制 tail，但须新起点、不变量、允许变化和转场锚点。
- KF 是生成前高光，不代替 start/tail FRM。
- 每段至少有 start、scene、tail；相邻段检查上一段末 12 帧与下一段首 12 帧；tail 应避开黑帧、转场和污染帧。
- observed SEAM 先查 `required_invariants`，再查变化是否只属于 `permitted_deltas`；声音桥不能掩盖身份、动作相位或光位错误。

当前关键变化：

1. Ref2VA tail 通常是 `previous_tail_reference`，只有单图 I2VA 才是 `previous_tail_as_start_frame + first`。
2. 原版通常在当前段交付后补 FRM/SEAM 记录；当前 runner 可先抽接力 tail，主 Agent 在当前段交付前看图、对账并登记，下一段只能在当前段看图、登记和交付后编译。
3. **观察前移不等于恢复自动质量返修**：内容/审美问题仍可 best available 交付，不阻断也不自动重生；缺真实证据、不可解码或哈希不符才属于技术阻断。

### 7.6 单 SEG 确认与委派替换

原版一次可确认接下来连续 1–2 个 SEG，每段一行；当前 `batch_start == batch_end`，数量固定 1，两张表都只含当前 SEG。

当前确认前必须已有：完整中文底稿、真实 Skill 调用、保存后的英文成稿、通过双哈希/结构检查的 `h3_conversion`；continuous 还须真实 tail、来源视频/tail 哈希和主 Agent 看图观察。

确认记录新增 provider、adapter version/SHA、cloud config SHA、`execution_mode:serial_real_tail_chain`、run plan 路径/SHA。真实哈希复用、原任务轮询恢复、结果下载和同源 tail 补抽不占新生成数量；新增、返修、重生或展示参数变化必须重确认。

用户意图硬门没有放宽：普通聊天肯定、沉默、模糊答复、历史确认、抱怨、纠正和原因追问都不自动成为生成授权。本地没有 `interaction.ask` 时可使用真实文本确认，但必须按 local-runtime 记录，不能伪造工具调用。

**委派语义变化：**原版实际视频生成/编辑必须异步 subagent，主 Agent 不得直调；当前有 subagent 时由其启动并等待固定 runner，没有时主 Agent 可启动同一进程。这是**强制角色隔离放宽**，由固定 JSON、固定命令、单 generate、执行锁、task 防重、run-state、输出白名单和哈希绑定补偿；不是原版 subagent 权限模型原样保留。

固定 operation：

| operation | 含义 | 是否新增生成授权 |
|---|---|---|
| `generate` | 当前唯一新 SEG；已有 task 时可进入原任务恢复而非盲目再 POST | 是，限当前段 |
| `recover` | 按已有 task 和原确认恢复原任务 | 否 |
| `reuse` | 复用真实存在且哈希相符的输出/tail | 否 |

### 7.7 Provider 与 AutoDL 生命周期

- H3 决定模型能力，`autodl` 决定执行位置，`comfy_workflow_v1` 决定协议；当前只有 AutoDL，不是已有多个可自由切换后端。
- 禁止因超时、连接、额度或偏好静默切换 provider；切换须更新固定 JSON、重新预检，有新 POST 时重新确认。旧任务恢复仍走原 provider。
- 注册表只能加载 Skill 内置审核模块，项目 JSON 不能注入任意 Python 路径。
- adapter 至少提供 `load_config / prompt_markers / verify_task_inputs / submit_segment / poll_segment`；串行器拥有授权、锁、tail/source 哈希、输出白名单和 run-state。
- 恢复不得新 POST；旧 ID 查询空、异常或超时不是重提理由。mtime、时长相近、目录只有一个视频、文件名相似或“看起来像”都不能独立证明归属。
- AutoDL 真实开机是独立计费授权，必须 `--execute` 加精确实例 UUID；剧本、图片、音色或视频生成确认都不包含电源授权。
- `run-managed` 负责初始电源状态、开机、业务健康门、子进程、退出关机和真实 stopped 对账；固定入口健康门为 `/api/comfy/status` 且 JSON `running=true`，不是 HTTP 200 即就绪。
- task 先写 `submission_pending` 再 POST；响应缺 ID 或结果不明进入 `submission_unknown`，不立即重发；取得真实 ID 才 `submitted`，记录 `http_post_count=1`。
- `prompt_id` 可能随 ComfyUI 重启失效，不等于 `/output` 文件被删，也不等于获得重生成授权。恢复通过 result/history/concurrent assets/result URL 找唯一身份；无法唯一归属时保留现场并标记 `STALE_OR_UNAVAILABLE`。
- 取得 URL 后先保存，再下载、probe、音轨检查、全量解码并原子落盘；本地失败保留 URL。恢复正常路径只发 GET。
- 离线测试通过不证明云端可用、不授权开机，也不证明真实旧任务已找回。

### 7.8 当前执行文档的主要矛盾与残留

1. **高优先级：通用视频路由与固定 queue 断层。** `video.md` 允许视频参考和 Ref2VA 式 `video_edit`，AutoDL queue 却禁视频且 schema 没有 `videos`；应在通用路由层就暴露限制，不能删掉源视频伪装执行。
2. **高优先级：本地无 ASR 与排障残留冲突。** `troubleshooting.md` 仍写“重新 ASR”“查看 ASR alignment”；本地应按锁定台词人工对轨，只有宿主真实提供 ASR 时才可使用，不得伪造。
3. **电源措辞作用域不清。** “不按 SEG 重复开关机”与“每次单 SEG 进程退出关机、下一段重新电源授权”并存；一致解释应是“同一受管进程/同一 queue 内不逐条重复”，跨多次单段运行仍需按实际生命周期执行。
4. 确认 Reference 仍有“派发 subagent”旧措辞，与无主 Agent 也可启动固定 runner 并存。
5. `video.md` 有“第一部分步骤 10 抽帧”旧编号引用；当前同位置步骤已改变。
6. 当前仍只有一个模型和一个 provider；可扩展架构不等于实际多模型、多后端选择。

## 8. 状态、清单、交付、控制合同与 CLI

> 完整逐条报告：[04-control-manifests-delivery-cli.md](analysis/doubao-diff/04-control-manifests-delivery-cli.md)。

### 8.1 保留的核心控制合同

- 三种授权仍严格分开：项目执行 `proceed_project`、当前视频生成 `generate`、成片拼接 `proceed_assembly`；任何一种都不能替代另外两种。
- 完整模式逐集闭环、目标阶段停止、轻量中间阶段 `merged`、KF 硬门和内部十五列分镜均保留。
- 阶段状态仍是 `pending | in_progress | awaiting_confirmation | confirmed | merged | invalidated | blocked`；七步阶段事务和真实意图判断不变。
- 普通确认不使用封闭关键词白名单；本地无专用确认工具时可以明确聊天确认，但必须记录唯一 `local:` ID 和 `confirmation_transport:user_message`，不能伪造工具调用。
- revision、`supersedes_confirmation_ids`、已确认版本不覆盖、按真实依赖失效下游、`drama_rollback.py` 和跨后续集显式级联均保留。
- `project_data_card.json` / `asset_registry.json` / `asset_usage_ep_N.json` 的事实源分工不变；`项目设定卡.md` 仍只是可读投影。
- KF 与 FRM、planned/observed SEAM、verified cut/best available cut 的层次不变；连续段仍必须消费真实 tail。
- 每集唯一最终视频、默认无字幕、只拼接 confirmed/accepted 片段、主观问题不阻断客观交付也不自动重生等规则不变。

### 8.2 schema 与执行语义的实质变化

| 主题 | 原版 | 当前版 | 影响 |
|---|---|---|---|
| 规划时长 | `total_duration_s`、每集 `duration_s` | `estimated_total_duration_range_s/display`、每集 `estimated_duration_range_s/display` | 规划改为非锁定预估区间，不再与下游实际时长机械相等 |
| 分镜时长 | 与规划时长关系较紧 | storyboard `duration_s` 是真实执行总和；只有 `user_locked` 才与锁定值相等 | 预估、执行、锁定三种语义分离 |
| 成片时长 | 使用交付时长字段 | delivery `duration_s/display` 必须来自最终真实媒体 | 不得把规划预估值当成片实测值 |
| 视频确认 | 可覆盖连续 1–2 SEG，允许批次范围 | `start=end`、数量 1，只 supersede 同 SEG 旧确认 | 旧批次授权记录不能直接迁入 |
| 冻结对象 | Prompt、模型和输入等 | 还冻结 queue 字节、provider、adapter version/SHA、cloud config SHA | 任一冻结值改变都需重新预检和确认 |
| 视频 segment | 一层 Prompt、通用工具结果 | 新增 `director_draft_file`、`h3_conversion`、`h3_structure_verified`、provider、request snapshot、真实 task_id 等 | 旧 manifest 缺的不只是描述字段，而是可验证血缘 |
| 运行状态 | 主要依靠 video manifest/工具记录 | 新增独立 run-state：输出/tail 哈希、来源视频哈希、confirmation ID、`manifest_modified:false` | 运行事实与人工 manifest 修改进一步隔离 |
| 群众 | 无 CRD 专属 schema | 数据卡、registry、storyboard segment 增加 crowds/CRD 和批准门 | 视觉替换失效范围从 CHR/SCN/PROP/STYLE 扩为含 CRD |
| 视频编辑 | 通用 `video_edit` 定点修改现有视频 | H3 无原生编辑时按 Ref2VA 参考重生成 | 名称相同不等于工具语义相同，不能按原版直接编辑理解 |
| 旧状态镜像 | 文档允许保留但不参与判断 | 两处旧镜像兼容说明删除 | 状态枚举没变，但旧项目迁移说明弱化 |

### 8.3 新增 `local-runtime.md` 的具体内容

- **宿主与输出协议**：Claude Code、Codex、baocode；本地 CLI stdout 为单行 JSON；退出码 0/1/2 分别表示成功、运行/业务失败、参数错误。
- **凭证边界**：只从环境变量或批准的 `.env` 读取；查找顺序为 `--env-file` > `DRAMA_ENV_FILE` > `tools/.env` > Skill 根 `.env`；凭证不写入项目/manifest/Prompt，不回显真实值。
- **工具映射**：`image.py` 对应 image_gen/image_edit；`video_run.py` 统一读取 `串行执行.json`；`media.py` 对应 frame/probe/trim/concat/burn 等；`upload.py` 处理 OSS 上传；中文到底稿的 H3 转换必须真实调用 `h3-prompt-writing`。
- **模型和电源**：用户可见生图模型为 gpt-image，视频为 H3；AutoDL 是 provider，不是模型；TTS 使用 Qwen3-TTS 产约 5 秒音色样片，视频人声默认由 H3 原生生成；计费电源必须另行授权。
- **确认适配**：优先宿主真实确认工具；无工具时明确聊天确认；来源 `batch_preview|planning_preview` 与通道 `host_tool|user_message` 分开记录。
- **执行适配**：有 subagent 时由其启动并等待 runner，无 subagent 时主 Agent 启动同一受管进程；media 是同步命令，以退出码、实际文件和 probe 为证据，不伪造远端 task ID。
- **交付适配**：图片/视频必须存在、非零、可解码；视频另需可渲染流和全量解码；通过宿主真实文件链接或内联预览逐项展示并核对结果；未展示路径不算交付。
- **外部服务边界**：未经用户授权不上传；远端 workspace/canvas 字段留空，不能用本地路径或文件 ID 填充。
- **有意的枚举分层**：JSON 的 `tool/tool_mode` 仍写原枚举，日志媒体工具仍写 `mediakit`，lint 禁用词仍写 `ffmpeg`、`text_to_image`；实现层使用 ffmpeg 与 manifest 兼容枚举不是同一层，不应擅自互换。

### 8.4 十份 CLI 文档的真实差异

- **六份完全一致**：`ls.md`、`tree.md`、`get.md`、`create-batch.md`、`update.md`、`update-batch.md`。其中的 50 项/1MB 原子批处理、Item/Frame 回读、source_ids、path patch 等不是当前本地新功能。
- `README.md`：删除“七接口已上线、不再 mock”等部署状态及失效文档引用；初始化、XML、Item/Frame、path、source_ids 和原子性保留。
- `workspace-create.md`：删除“唯一不带 workspace ID 的命令”这一错误句；创建非幂等、原始 ID、present_files 前置不变。
- `get-workspace.md`：删除“每轮先查、重复创建幂等”的旧动线，改成显式恢复/排障，消除了与默认直接创建的冲突。
- `create.md`：示例文件和预览宿主调整；删除的卡片总结主要属于去重，核心门禁仍在其他 CLI 文件。
- **重要解释**：当前 `local-runtime.md` 明确 `references/cli/` 只描述原平台远端画布；本地没有 design-cli 等价物，不能伪造 Workspace/Item/Frame。

### 8.5 当前版内部一致性问题

以下不是两版设计差异本身，而是当前版迁移后仍需清理的规则冲突：

1. `interaction-ask-video-clarification-ref.md` 仍有“必须 interaction.ask、不得普通聊天”的绝对句，与本地无工具时允许明确聊天确认并存。
2. 当前 `SKILL.md`、`control-contracts.md`、`delivery.md` 仍有 Canvas/present_files 的非 Mobile 绝对措辞，需要靠 local-runtime 优先级解释。
3. `delivery.md` 一部分段落仍禁止 FFmpeg，另一段却给出 `tools/media.py burn` 的本地命令。
4. ASR 七步流程仍偏 mediakit 单路径，与“无本地 ASR、人工试听并标记 `manual_listening`”并存；“必须 ASR 原始信封”的表述过宽。
5. `manifests.md` 仍把 basic QC 写成“真实 mediakit 探测”，宿主中立化不彻底。
6. `workspace-create.md` 的“后续所有命令都要用 ID”是泛化表述，严格说两个零 ID 初始化命令例外。

这些问题应优先按当前 `SKILL.md` 的本地覆盖条款解释，但从可维护性看，最好减少需要读者自行裁决的绝对句。

### 8.6 已确认的兼容断点

原版 `scripts/drama_lint.py` 的 `--fix` 和 `--changed-file` 是兼容参数；当前 argparse 只剩 `skill_root`、`--project-root`、`--stage`。旧自动化继续传这两个参数会真实报未知参数，通常退出码 2，而不是“兼容但忽略”。这是当前版明确删除的旧调用能力，详见第 9 节。

## 9. 校验器、回退脚本与测试

> 完整逐条报告：[05-scripts-lint-tests.md](analysis/doubao-diff/05-scripts-lint-tests.md)。该专题完整读取原版 2 个脚本、当前 11 个脚本和 11 个测试文件，并实际执行了离线测试与 Skill 自检。

### 9.1 从单体脚本到 11 个脚本的功能映射

当前不是把原版 `drama_lint.py` 机械拆开，而是把原有职责迁移到领域模块，并新增 H3、群众、双层 Prompt、单 SEG 和运行文件检查。

| 当前脚本 | 实际职责及原版来源 |
|---|---|
| `drama_lint.py` | 总调度、阶段文件、计划时长、群众、KF、成片、H3 能力档、Skill 包、CLI；承接原版主入口与多处总检查 |
| `drama_lint_domain.py` | 公共枚举、常量、输入角色、H3 模型/时长、marker、计划对象、helper；导入时读取 `tools/h3.json` |
| `drama_lint_confirmations.py` | 通用 full/incremental 确认、revision、planning interaction、transport；来自原版用户确认记录 |
| `drama_lint_highlights.py` | 亮点绑定、reaction/payoff/aftereffect 顺序、跨集 deferred/inherited aftereffect；主要是迁移保留 |
| `drama_lint_assets.py` | 共享/分集资产、版本、approved、真实文件、复用、生成路由、STYLE001、CRD 索引 |
| `drama_lint_state.py` | 项目/分集七态、前集/当前集/未来集、聚合状态、确认要求；新增强制轻量 merged/final 形态 |
| `drama_lint_prompts.py` | 中文结构化/五自然段底稿、H3 成稿、媒体标记、`<d>`、preflight、真实 Skill 调用与双 SHA 血缘 |
| `drama_lint_storyboards.py` | storyboard JSON、segment/shot、密度、镜头/尾态、reference plan、audience execution、逐镜删除复审、阅读稿 |
| `drama_lint_video.py` | 实际媒体输入、H3 模式限制、voice、路由、逐段 Prompt 管线、视频 manifest 与真实来源 |
| `drama_lint_video_confirmations.py` | 段索引、确认 ledger/envelope、单 SEG、supersession、参数展示、五列分镜、调用 ID/时间 |
| `drama_rollback.py` | 唯一回退写入脚本；完整模式主逻辑保留，新增轻量修复、输入校验和 deepcopy |

原版状态、亮点、资产、KF、语音、视频和成片大功能区均能找到承接模块；**没有发现整块无声删除**。类数量或行数变化不能直接当功能强弱结论。

### 9.2 CLI、输出 schema 与 `release_ready`

两版共同保留：位置参数 `skill_root`、`--project-root`、`--stage`（skill、七阶段或 all）。当前删除 `--fix` 与 `--changed-file`：

- 原版二者本就是兼容参数，`--fix` 不实际修复，`--changed-file` 仍运行相同 focused checks。
- 当前 argparse 不接受它们，旧自动化通常直接退出码 2。
- 因而不是“自动修复能力退化”，而是**真实 CLI 向后兼容破坏**。

主输出结构保持 `summary.error_count/warning_count/scope + release_ready + issues[]`，issue 仍有 level/code/message/hint/path 并去重。

- `release_ready = (error_count == 0)`；有 error 退出 1，否则 0；warning 不阻断。
- `scope` 只是请求检查范围，不代表所有阶段通过。
- 当前 video 阶段缺 storyboard SEG 记录可从 error 变 warning，所以 video 的 `release_ready=true` 更不能解释为成片可交付。

### 9.3 状态、时长和通用确认的校验变化

- 七阶段 `planning→script→assets→storyboard→keyframes→video→final` 和七态 `pending/in_progress/awaiting_confirmation/confirmed/merged/invalidated/blocked` 保留。
- 前集必须到 target、未来集不得提前、当前集阶段顺序、项目 phases 与 episodes 聚合、confirmed 必须有相应确认等均有实现。
- 轻量 planning 确认后必须固定 `current_stage=final`、`current_episode=ep_1`，项目和 ep_1 的 script 到 video 中间阶段均 merged；不再允许中间阶段自由选 confirmed/merged。
- `planning_estimate` 在完整模式规划阶段可只登记估算范围，不建立精确跨阶段时长门；`user_locked` 仍要求 storyboard/delivery 精确匹配。
- 轻量即使写 planning estimate，也仍须有唯一可执行视频时长；范围从原版按 Seedance 型号的 ≤15/30 秒改为 H3 单集单视频 4–15 整数秒。
- 通用 full/incremental、base_revision、changed_artifacts、impact_scope、带时区 confirmed_at 等保留。
- 新增 `confirmation_transport:user_message|host_tool`：用户消息须唯一 `local:` 记录 ID，host_tool 须真实非 local 调用 ID；旧确认记录缺新字段会失败。
- 底层 `has_meaningful_value` 对非 bool 数字（含 0）的处理与原版略有差异，属于需要边界测试的细微 helper 语义变化。

### 9.4 新增阅读稿、逐镜删除复审与群众校验

**阅读稿：**当前完整模式在阅读稿存在时检查固定标题、全片摘要、唯一本集提要、章节/片段、逐镜 bullet、四项摄影信息、声音/人声/切入/切出、镜头连续编号和真实总数；禁 Markdown 表格与 SEG 式片段标题。未提交源码另增明确内切检查：画面动作建立后又写“切至/画面切到”等报 `storyboard_reading_internal_cut`，开头切入、连续运镜、焦点转移和物理切纸不误报。

边界：主要验证阅读稿自身结构，未完整交叉核对 storyboard JSON 的 SHOT ID、时间区间和逐镜时长；自然语言正则不可能覆盖所有切镜表达。

**逐镜删除复审：**未提交源码按 SEG 分组，接受“镜头职责与删除损失/删除测试”标签和表格/heading；只有含“删”的分句里的 SHOT 引用计入覆盖。缺段报 `director_segment_deletion_review_missing`，缺镜报 `director_shot_deletion_review_missing`。它证明记录存在和归属，不证明艺术理由真实或充分。

**群众：**新增约 300 行主校验块，覆盖：

1. dry-run/task 请求快照的 slots、图片槽位、项目相对路径与实际 bytes SHA-256。
2. recurring 群众的 approved CRD/SRC 来源、crowd_reference 和真实图片；SRC 与 source_manifest 唯一记录、stored_path、哈希一致；CRD 与 approved 文件集合一致。
3. CRD ID、状态、人数/密度、位置、动作、allowed changes、continuity scope、visibility、群体外观、成员登记及跨段稳定。
4. storyboard shot 绑定与 video 段输入跨文件核对，而不是只查一个 JSON 字段是否存在。

资产模块还新增 crowd/CRD 前缀和 `files_by_ref`，分集资产也按 category 查 ID 前缀；KF manifest、资产复用和生成请求等旧职责仍在。

### 9.5 视频、Prompt 和生成确认校验变化

- 当前只接受 H3，并重新核验本地能力档，禁止通过改配置虚增能力，也禁止把 provider/deployment/凭证混入模型能力档。
- `reference_inputs/video_inputs/audio_inputs` 必须为数组，order 从 1 连续，role 合法，文件必须真实存在且为项目相对路径。
- 只要出现 `planned_reference_inputs` 就报错，即使为空；实际输入也不得用 `previous_tail_of` 偷带未来 tail。
- H3 按模式检查图片/视频/音频数量、总文件数、首尾帧 role/position/order、Ref2VA 真实参考、音频视觉依赖、每个音视频实际时长及总时长。
- 路由显式映射：`text_to_video→T2VA`；`image_to_video→I2VA/FL2VA/L2VA/Ref2VA`；`media_to_video→Ref2VA`；`video_edit→Ref2VA`。
- 所有有效路由包括 `video_edit` 都进入 SegmentPromptPipeline；原版 video_edit 的 Prompt 豁免消失。
- 中文导演底稿支持固定结构化标题或传统五自然段，台词、媒体槽位、字幕方括号和主体标签分别校验。
- H3 成稿按模式检查固定字段、opening instruction、英文媒体标记、真实 order 和字幕禁则。
- `<d>` 必须配对、不嵌套、每条 speech_line 恰好一个、以 `[语言]` 开头；移除允许的 `<scenetrans>/<cutoff>` 后按规范化台词逐条顺序比较；无台词不得额外出现。
- preflight 保留“一次集中审阅、最多一次修订、一次最终客观校验、每镜恰好一次”，新增 `h3_structure_verified=true`。
- `h3_conversion` 要真实登记 `host_skill_tool`、`invoked=true`、带时区时间和双 SHA；成稿 SHA 还须匹配实际提交的 `prompt_sha256`。lint 验证登记字段和当前文件哈希，本身不能向宿主证明历史工具调用的外部真实性。
- 生成确认保留段索引连续、ledger、返修 supersedes/attempt、参数展示、五列分镜、confirmed_at 与调用时序；当前 `end != start` 即报 `video_generation_confirmation_too_large`。
- `serial_real_tail_chain` 必须绑定项目相对 run plan 及 SHA；continuous 在确认前已有真实 tail FRM、文件和 source relation。
- 原版 Seedance 2.5 专属 `membership_notice` 消失是模型合同替换，不是漏迁移。
- video 缺段在普通 video 阶段改 warning，final/all 且非 lightweight 仍 error，以支持逐段建立真实记录。

### 9.6 成片与 Skill 包自检

成片仍检查输出、accepted/candidate、source segment、连续性、字幕和 basic QC；主要变化是精确时长服从 planning/user lock 双轨，不能据局部时长测试推断全部 delivery 已覆盖。

Skill 自检除 frontmatter、SKILL 引用和 Markdown 相对链接外，还新增：

- 本地 H3 能力档完整性；
- Markdown 中 video manifest JSON 示例的确认、H3 时长/媒体/模型/输入字段；
- 本地运行文件和 Reference 存在性；
- Python AST/tokenize 与当前源码风格约束（包括禁注释/docstring）。

这些仍是静态和示例合同检查，不是外部运行健康证明。

### 9.7 回退脚本：完整模式保留，轻量语义根本改变

完整模式仍保留七阶段校验、项目/episode 范围、未来集/未开始阶段保护、后续集显式 `--cascade-later-episodes`、revision+1、目标 awaiting/in_progress、下游 invalidated；不删除或重写艺术产物。当前用 deepcopy 修正原版浅复制风险，并新增 state/episode/phases 输入合法性检查。

**轻量非 planning 回退不再是回到请求阶段：**

- 读取 `drama_plan.json.objective.workflow_mode` 识别轻量。
- 无论请求 script/assets/storyboard/keyframes/video/final 哪个非 planning 阶段，实际统一修复为 `current_stage=final`、`current_episode=ep_1`。
- script 到 video 的项目和 ep_1 阶段均 merged，final 为 in_progress。
- 输出新增 `requested_to_stage` 区分请求和实际；操作日志也记录更新后的 final，而非请求的 script/video。

这与轻量固定状态机一致，但调用方不能只看 `--to-stage` 推断结果。回退失败仍有 `rollback_failed`、`rollback_log_failed`、`rollback_partial_commit` 及退出码 2/2/3。

### 9.8 真实测试与自检结果

专题实际执行：

```powershell
python -I -B -m unittest discover -s "<drama-root>\tests" -p "test*.py" -v
```

真实结果：

```text
Ran 76 tests in 1.051s

OK
```

当前 11 个测试文件合计 **76 项全部通过，无 failure、无 error，输出未显示 skip**。测试使用 TemporaryDirectory、fake HTTP、mock 子进程/时钟/媒体验证；WAV 由本地媒体工具生成，没有真实网络、生图、视频或上传。

另执行：

```powershell
python -I -B "<drama-root>\scripts\drama_lint.py" "<drama-root>" --stage skill
```

真实结果：**0 error、0 warning、`release_ready=true`、`issues=[]`**。主报告和六个专题全部整合完成后，主 Agent 再次执行同一 Skill 自检，结果仍为 **0 error、0 warning、`release_ready=true`**。

覆盖分布：结构化导演底稿 5、媒体音频 3、音频 preflight 3、AutoDL 健康 6、workflow 恢复/provider 21、固定 video_run 8、视频确认 4、时长锁 5、视频计划 6、逐镜删除复审 6、阅读稿 9。网络、子进程、时钟、媒体时长和验证均 fake/mock；测试通过不代表真实 Provider、AutoDL 或媒体质量已验证。

### 9.9 测试覆盖空白

1. **回退完全无专项测试**：轻量 final 修复、后续集级联、dry-run、日志失败恢复、退出码 3 都无直接回归。
2. **状态机无专项测试**：前集/未来集、聚合、轻量 merged/final 和 confirmation transport 需覆盖。
3. **群众无专项测试**：SRC/CRD、slots/hash、成员与外观跨段、storyboard/video 绑定不能由 76 项通过背书。
4. **H3 Prompt 不完整**：缺 `<d>` 配对/语言/数量/顺序、scenetrans/cutoff、无台词、中文媒体标记和双 SHA 专项。
5. **H3 媒体模式缺完整参数化矩阵**：五模式、首尾帧、Ref2VA 总数、音频视觉依赖、单条/累计/缺时长等需补齐。
6. **生成确认只测局部**：run plan/hash、参数表、五列分镜、规范化台词、supersedes、attempt、调用时序和 planning/首次 call ID 复用需端到端测试。
7. 资产完整路由、复用、STYLE001、KF、亮点/跨集余震、成片连续性/QC/字幕缺独立测试。
8. 缺顶层 lint CLI 测试：stdout/stderr、退出 0/1、issue 去重、warning 下 release_ready 和 stage 调度未固定为合同。
9. 阅读稿与 storyboard JSON 的完整交叉一致性、更多切镜语言变体未覆盖；删除复审也不判断内容质量。
10. 阅读稿和删除复审对应源码/测试含未提交变更，发布时需把当前磁盘状态与提交历史明确区分。

## 10. 本地工具链 `tools/`

> 完整逐文件报告：[06-local-tools.md](analysis/doubao-diff/06-local-tools.md)。该专题为纯静态源码分析，未执行工具、网络、SSH、生成、上传、下载或电源操作。当前共 20 个文本文件：14 个顶层文件和 `tools/lib/` 6 个模块，不计 `.pyc`。

### 10.1 20 个文件逐项职责

| 文件 | 职责、依赖与关键边界 |
|---|---|
| `tools/README.md` | 工具索引、env 顺序、固定视频链和示例；统一 stdout JSON 的说法存在实际例外 |
| `tools/image.json` | gpt-image 根地址、model、尺寸、质量、超时、最多 10 参考图；指向真实外部 API，不是离线配置 |
| `tools/h3.json` | H3 4–15 整数秒、五模式、模态数量/时长上限；目标交付比例列表不等于 provider 请求能力 |
| `tools/video_run.example.json` | provider/cloud config/run-state/电源/poll/SEG 模板；只示例 generate，不是完整 recover/reuse 手册 |
| `tools/image.py` | 无 ref 走 generations，有 ref 走 edits，写一张图；无 dry-run、任务恢复、锁或自动重试，输出可覆盖 |
| `tools/video.py` | H3 共享 HTTP、模式/时长、槽位、Prompt 标记、task 默认路径、下载验证；**不是独立 CLI** |
| `tools/tts.py` | SSH 到 AutoDL ComfyUI Qwen3-TTS，生成约 5 秒音色样片并规范化 WAV；不是正片完整配音 |
| `tools/search.py` | Smart Search GET，抽取 `webPages.value`；无分页/重试/正文抓取，`--pretty` 是多行文本 |
| `tools/upload.py` | 本地文件或 HTTP(S) URL 上传 S3 兼容存储并返回 CDN URL；需 boto3 与 OSS 凭证，全量内存读取 |
| `tools/media.py` | 9 个本地同步命令：frame/strip/probe/trim/cut-audio/concat/burn/erase/fit-image；依赖 ffmpeg/ffprobe |
| `tools/autodl_instance.py` | AutoDL list/status、电源和 run-managed；真实执行会计费并启动子进程，默认 dry-run |
| `tools/workflow_video.py` | H3 workflow adapter 与直接 CLI；prepare/submit/poll/run/status、task 防重、GET 恢复和下载 |
| `tools/workflow_series.py` | provider 中立的 queue preflight/run、授权、接力、reuse/recover、run-state 和锁 |
| `tools/video_run.py` | 正常视频固定入口；读取每集 `串行执行.json`，组合 AutoDL manager 与 series runner |
| `tools/lib/__init__.py` | 空包标记，无额外能力 |
| `tools/lib/env.py` | dotenv、凭证、JSON emit/fail、URL/MIME、SHA、data URI、统一异常出口 |
| `tools/lib/h3_domain.py` | H3 模式、task phase、TaskRecord、媒体物化和模式策略 |
| `tools/lib/json_state.py` | 状态 JSON 添加 UTC 时间，固定 `.tmp` 后 `os.replace`；原子替换不等于完整事务 |
| `tools/lib/media_facts.py` | ffprobe 时长、帧/包时间轴、末帧事实、媒体 probe 和 SHA |
| `tools/lib/video_providers.py` | provider 注册、协议/接口检查和 adapter 源文件 SHA；当前只导入内置 AutoDL |

缓存中虽有 `managed_execution`、`workflow_series_plan` 的 `.pyc` 而没有同名源码，但不能据此把缓存当当前功能；本次未反编译或执行缓存。

### 10.2 原版抽象工具到当前真实实现的映射

| 原版枚举/能力 | 当前实际入口 | 保留与变化 |
|---|---|---|
| `image_gen` | `image.py` 无 `--ref`，POST generations | 文本生图保留；后端为配置的 gpt-image；只保存 `data[0]` |
| `image_edit` | 同一 `image.py` 有 `--ref`，POST edits | 有真实视觉参考必须 edits；最多 10 图；本地图未先真实解码 |
| `text_to_audio_plus` | `tts.py`，SSH/ComfyUI Qwen3-TTS | VOICE 样片与 voice_anchor 语义保留；依赖用户自建云环境，只产约 5 秒样片 |
| `text_to_video` | 创作枚举；直接 adapter 可 T2VA；正常入口 `video_run.py` | 概念保留，但固定 queue 每段至少一图，正常入口不能纯 T2VA |
| `image_to_video` | `video_run.py`；直接 adapter 可 I2VA/FL2VA/L2VA/Ref2VA | 一个原工具名拆成多种 H3 模式；固定 queue 非首段强制 tail |
| `media_to_video` | 直接 adapter 可图片/视频/音频 Ref2VA；固定 queue 仅图片/音频 | 多模态概念保留，正常串行入口禁视频 |
| `video_edit` | 文档映射为 Ref2VA 参考重生成 | 不是原生定点编辑；固定 queue 又不能传源视频 |
| mediakit `extract-frames` | `media.py frame/strip` | 本地同步抽帧；tail 是最后可定时编码帧，不自动等于稳定无转场尾帧 |
| mediakit `probe-video-metadata` | `media.py probe` + `media_facts.py` | 本地探测，无远端 task 信封；深度事实可遍历帧/包 |
| mediakit `trim-video/concat-video` | `media.py trim/concat` | 本地重编码；concat 不自动完成最终全部 QC/时长硬门 |
| mediakit `add-subtitle-to-video` | `media.py burn` | ffmpeg libass 烧录；需本机字体和 libass |
| mediakit `erase-watermark` | `media.py erase` | 固定区域 delogo，不是通用智能擦除 |
| mediakit `asr-subtitles` | 无本地等价 | 只能按真实音轨人工试听对齐；不得伪造 ASR |
| `FileBatchUpload` | `upload.py` | 需自有 S3/CDN；只获得 URL，不等于用户交付 |
| `design-cli` / Canvas / Workspace | 无本地等价 | 用宿主真实文件链接/内联预览；不能伪造远端 Item/Workspace |
| 无原版对应 | `search.py` | 新增文本搜索 CLI，只返回摘要 |
| 无原版对应 | `autodl_instance.py` | 新增云资源控制面、健康门与电源生命周期 |
| 无原版对应 | `workflow_series.py` / `video_run.py` | 新增串行状态机、真实 tail、逐段授权和恢复 |

### 10.3 正常视频链与固定 runner 的支持矩阵

固定调用链：

```text
video_run.py
  -> autodl_instance.py run-managed
       -> workflow_series.py run
            -> workflow_video.py adapter
```

`workflow_series.py` 的 queue 实际要求：每段至少一图；非首段第一图必须且只能引用前段真实 tail；禁止视频参考；本地音频逐项 2–15 秒、合计 ≤15；所有项目路径限制在 project root；已有输出必须按接管/reuse 事实核对；固定 queue poll 永远 `require_audio=True`。

| 能力 | 直接 adapter / 模型层 | 固定正常入口 |
|---|---|---|
| 纯 T2VA | 可表达 | 不支持，因至少一图 |
| 图片驱动 Ref2VA | 支持 | 支持其串行子集 |
| 含视频参考的 Ref2VA | 可表达 | 不支持 |
| 无声段 | 模型/直接 CLI 可不要求音轨 | 不能正常 complete，因强制音轨 |
| 基于源视频的 `video_edit` | 概念可按 Ref2VA 重生成 | 不支持，因禁视频 |
| 多个新 SEG 一次运行 | `workflow_series.py` 本身可授权多个 | `video_run.py` 限制最多一个 generate |

所以“**H3 五模式能力**”“**直接 adapter 能表达**”“**固定制作入口可执行**”是三个不同集合，不能互相冒充。单 SEG 上限在 `video_run.py`，不是 `workflow_series.py` 本身。

### 10.4 queue 更新与 run-state SHA 的确定性续跑冲突

这是当前最重要的实现风险之一：

- `delegation.md` 要求每轮更新同一份 `串行执行.json`，启动后不得修改，并把确认绑定到该文件 SHA。
- 已有 run-state 时，`workflow_series.py` 要求 `state.queue_sha256 == sha256_file(当前 queue)`；任何字节变化都会拒绝续跑。
- `video_run.py` 每轮仍读取同一个 queue 和 JSON 中同一个 run-state，没有自动轮换、归档或重新初始化 run-state 的逻辑。

因此，按当前静态代码，如果第一轮后向同一 queue 添加/修改下一段并沿用同一 run-state，下一轮会**确定性因 SHA 不同而停止**。连续多轮必须更换 run-state、显式归档/重新初始化或改变绑定设计；固定入口没有实现这些步骤。实际项目是否另有未纳入工具的外部编排仍需实机验证，不能假设自动解决。

### 10.5 生成 POST 防重、恢复与哈希绑定的真实强度

`workflow_video.py` 的生成状态机：

1. task 已存在或正式输出已存在时拒绝新 POST。
2. POST 前先写 `submission_pending`。
3. 响应无 prompt_id 或请求异常/结果不明时写 `submission_unknown`，不立即重发。
4. 成功取得 ID 后写 `submitted`，记录 `http_post_count=1`。

这是强本地防重证据，但**不是服务端 idempotency key**：保护依赖同一 task_file/output 路径持续存在；删除、改名或更换路径后无法知道另一个路径曾提交，不是跨目录/跨副本的全局 exactly-once。

恢复侧：result 优先，特定 HTTP 错误可回退 history；默认单段 900 秒、间隔 10 秒；只有后端明确失败才 failed；无活动记录或无法唯一找回时 `STALE_OR_UNAVAILABLE`，保留现场不自动重生。持久化资产须精确匹配 promptId+workflowId、同源 `/output/`、合法视频扩展名并拒绝路径跳转。下载后 probe、音轨检查、全量解码，最后原子替换正式输出。

两个边界：

- 文档偏 saved `result_url` 优先，代码可先返回 concurrent assets 的唯一匹配；恢复证据顺序存在确定不一致。
- 持久化恢复强调唯一身份，但正常成功响应的 `_video_url` 发现较启发式，不能扩展为所有正常 URL 都有同等归属证明。

run-state 绑定 queue SHA、provider ID、adapter version、adapter SHA、cloud config、Prompt、params、本地输入、输出和 tail。**adapter SHA 只覆盖 `workflow_video.py` 本身**，不含 `video.py`、env、H3 域、media facts 或注册表；共享库变化不会必然使旧 run-state 的 adapter SHA 失效，不能称为整个依赖树完整性证明。

### 10.6 状态写入、锁、路径与电源边界

- `json_state.save_state` 使用固定 `.tmp` + `os.replace`，避免半截 JSON，但无 fsync、唯一临时名或同文件锁；同路径并写仍可能冲突。
- series lock 用 `O_CREAT|O_EXCL` 并写 PID，正常/异常退出 finally 删除；强杀或主机崩溃可留 stale lock，当前无 PID 存活识别或安全清理命令。
- queue 项目路径保护只覆盖固定 series；image/TTS/upload/media 的自由输出路径不自动继承。
- 固定 series 有真实 tail/source/output SHA 闭合，generate 不得消费同次未来 tail；但自动 tail 只是技术证据，不替代主 Agent 看图和稳定尾态审美判断。
- `video_run.py` 虽使用 provider 中立的 series，却硬编码 AutoDL manager 和 `/api/comfy/status`；未来 provider 不能只增 adapter 就自动获得完整正常入口。
- `video_run.py` 没有把自己的 `--env-file` 传给 manager/series 子进程，显式非标准 env 文件与直接 CLI 不完全等价。
- AutoDL 控制面仅 HTTPS、拒绝跨源/降级、限制响应并抑制错误正文；真实电源需 execute+精确 UUID，POST 不明先状态对账。
- run-managed 有健康门与关机收尾，但强杀时 finally 不保证执行；没有独立持久化电源状态。监督器允许任意子命令，授权审查必须覆盖完整命令，不只看实例 UUID。

### 10.7 图片、TTS、上传和本地媒体的边界

**图片：**比例只就近映射 `1024x1024 / 1536x1024 / 1024x1536`，精确比例另走 fit-image；无 dry-run/task 恢复/自动重试；输出可覆盖；只消费 `data[0]`；参考图和返回图未在工具内先真实解码；HTTP 错误可带服务端正文，日志不能默认可公开。

**TTS：**远端固定 Qwen3-TTS、ComfyUI、Conda Python 和 Linux 路径，强依赖特定镜像；paramiko `AutoAddPolicy` 自动信任未知 SSH host key；每个 job 都远端 POST 并轮询，没有本地 task 持久化、未知提交保护或恢复；ffmpeg 输出可覆盖。它只生成音色样片，不是正片配音。

**上传：**本地文件和远程响应均全量读入内存；远程 GET 没有内网、重定向、响应大小和 HTTPS 限制，存在 SSRF/资源消耗边界；MD5 key 只是内容寻址/去重标签，不是抗碰撞安全身份；没有 dry-run、上传后回读或本地恢复记录。

**媒体：**cut-audio/fit-image 有较强新文件与哈希保护；frame/trim/concat/burn/erase 多数可覆盖输出，版本递增和 approved 不覆盖主要仍靠上层。`frame tail` 不自动选择稳定尾帧；concat 不在函数内完成所有最终 QC；erase 是固定区域 delogo。

`media_facts.py` 在缺 stream duration 时可遍历全部帧/包推算，更严格但可能耗时、超时或占用大量内存；`probe_media` 强制有效视频流，不是通用纯音频 probe。

当前没有本地 ASR、独立分轨混音、通用 mux、精确双侧 12 帧接缝窗口或 0.25x 慢放专用命令。文档要求这些验收时，需组合真实宿主能力或明确记录缺口，不能把一次 strip/probe 当作全部接缝与 ASR 验收。

### 10.8 统一 CLI 文档的例外

- 正常 emit 是紧凑单行 JSON，但错误 JSON 实际写 **stderr**，调用方须同时采集 stdout、stderr 和退出码。
- `search --pretty` 是多行人类文本。
- `media probe --json` 可输出原始 ffprobe JSON，不保证统一 `ok` 信封。
- `video_run.py` 子进程失败时仍可先输出最终摘要再传播非零码。
- “本机即可运行”应理解为不需云主机/电源，不代表 image/search 完全离线；二者仍调用外部 API。

### 10.9 工具层的实际收益与代价

**收益：**生成防重优先于盲目重试；恢复原任务而非另起任务；queue/config/Prompt/params/输入/输出/tail 可审计；真实文件事实串联；下载后全量解码才落盘；电源授权与生成确认分离；项目 JSON 不能注入任意 provider 模块；固定 queue 有路径越界保护；本地状态和日志可直接检查。

**代价：**失去原平台统一 schema、原生定点编辑、完整 mediakit/ASR 和托管 Canvas；新增 queue 续跑、stale lock、依赖哈希范围、SSH host key、URL/输出覆盖和 CLI 输出非一致性问题。图片、搜索、上传和 media 的恢复/安全能力明显弱于视频主链，不能把主链保证泛化到全部工具。

## 11. 原版独有、当前版缺失或弱化的规则

本节只收录交叉核对全部相关文件后确认“不是简单搬迁”的项目，并区分有意适配、真实向后不兼容、监督/质量弱化和能力缺口。

### 11.1 已确认的真实删除、弱化或能力收窄

| 项目 | 原版 | 当前版 | 判定 |
|---|---|---|---|
| 动态最低字符公式 | `max(120, min(800, 时长秒数 × 4.5))`，低于下限不得进分镜 | 明确不按时长公式设最低字数，不执行字符数下限校验 | **真正删除的创作验收门**；避免机械凑字，但失去客观薄稿安全网，改靠事件证据与主 Agent 阅读全文 |
| 项目级 2000–3000 字 | 常见篇幅建议 | 仅为非门禁参考，不是上下限或准出条件 | **字数导向弱化**；固定子章节、产物范围和完整性门未删 |
| 评审排他句 | 不再执行第二套单集检查或独立可拍性评分 | 删除排他句，保留七轮改稿与统一 12 维评估 | **流程排他性删除**，不是评审能力删除；可能允许额外检查，也更依赖执行者避免重复流程 |
| 所有生成候选都即时展示 | 资产/KF/视频的正式、候选、草稿、未采用和返修结果都逐项展示，非 Mobile 还上画布 | 正式资产/KF 逐项、视频逐段交付保留；可见范围转向实际采用/应交付结果 | **监督范围弱化**：减少候选噪声，但用户不再必然看到每个未采用结果 |
| 规划与下游时长相等约束 | 规划和各层精确 `duration_s` 关系更紧 | 非锁定规划改为预估区间，不与详细剧本/分镜/成片实际时长相等校验 | **有意放宽**；提高规划弹性，但旧 lint/迁移脚本不能继续假定字段同义 |
| 超 60 秒双格式显示 | 必须同时写精确秒数和分钟换算 | 可同时写；预估区间标参考 | **展示强制弱化**；用户锁定值仍需精确 |
| 旧状态镜像兼容说明 | 明确旧镜像字段可保留但不参与推进 | 两处说明删除，唯一状态源和七态枚举未变 | **文档兼容指引弱化**；状态机主体未改 |
| lint `--fix` / `--changed-file` | 接受兼容参数；`--fix` 不自动修复，`--changed-file` 仍运行 focused checks | argparse 已删除，旧调用通常退出码 2 | **真实向后不兼容**；不是自动修复能力变弱，而是旧命令入口不再存在 |
| 强制异步 subagent 隔离 | 主 Agent 不得直调；异步不可用时暂停 | 无 subagent 时主 Agent 可启动并等待同一固定 runner | **角色隔离放宽**；由固定命令、授权、锁和哈希补偿，不是原权限模型原样保留 |
| 通用直接视频编辑 | `video_edit` 对已有视频做定点编辑 | H3 无原生编辑时按 Ref2VA 参考重生成 | **能力语义弱化**：不是像素级原位编辑；固定 queue 还禁源视频，正常入口实际不可执行 |
| 原平台完整媒体链 | mediakit 提供抽帧、探测、裁剪、拼接、字幕、ASR 等统一异步任务链 | 本地 `media.py` 只有九类同步命令；无本地 ASR、完整混音/mux 等 | **本地能力缩减**；人工试听是降级路径，不得伪称 ASR |
| 原平台画布/Workspace | 非 Mobile 的初始化、写入、回读和 present_files 是统一交付链 | 本地无等价物，使用真实文件链接/内联预览 | **宿主能力替换/缩减**；本地更方便，但不等于远端画布交付 |
| 固定入口模型模态覆盖 | 原平台抽象路由可表达零媒体、图片、音视频和源视频编辑 | 当前固定 queue 至少一图、禁视频、强制音轨 | **正常入口能力收窄**：不能纯 T2VA、视频参考、源视频 edit 或无声 complete |
| 视频模型/provider 选择 | 有 Seedance 2.0 多档和明确确认的 2.5 | 只有 H3，注册 provider 只有 AutoDL | **现有选择收窄**；可扩展架构不代表现有多选 |
| VOICE 生成表述 | 每个计划人声主体生成一个专属音色 | 先复用 approved，缺可用版本才生成；无台词群众不建 VOICE | **职责收窄且更合理复用**；不是取消可辨识人声的稳定 voice_anchor |
| 每个当前集出场角色都三视图 | 旧验收口径较机械 | 仅需要稳定身份的独立角色；群众按 shot/recurring 分层 | **资产验收范围改变**；不是取消 CHR 身份板，而是不再给所有远景群众机械套三视图 |

### 11.2 有意随模型/平台替换而退役，不应误判为创作质量回退

- Seedance 2.0 fast/mini/2.0/2.5 的型号路由、2.5 的 25–30 秒长段、会员/额度提示和旧媒体总时长阈值。
- Seedance 2.5 生成确认专属 `membership_notice`。
- `seedream 5.0 flash/pro` 的固定模型标签和会员话术；当前由真实本地图片配置承接。
- 原版 continuous tail 一律 `previous_tail_as_start_frame` 的旧语义；当前是在区分普通参考与硬首帧，并非删除真实 tail 门。
- 原平台轮询中的 9 分钟、临时 URL 24 小时、normalized/failed/canceled 等细节；当前本地同步工具不伪造远端 task，AutoDL 则另有自己的 900 秒/10 秒和恢复状态机。
- 宽松阅读稿示例被更严格结构替代，不属于变弱。
- `video_edit` 不再豁免 Prompt preflight 是当前收紧，不是功能删除；真正弱化的是原生编辑能力本身。

### 11.3 不应误报为缺失

- `get-workspace` 的“每轮先查询、重复创建幂等”被删是消除内部冲突，不是功能退化。
- `workspace-create` 的“唯一零 ID 命令”被删是纠正错误，因为 `get-workspace` 也不需要该 ID。
- `create.md` 的卡片总结被删主要是去重，初始化/回读门仍在其他 CLI 文档。
- `candidate` 定义不再包含“即时交付”不等于视频逐段交付门取消；当前控制合同仍明确要求。
- `references/cli/` 被保留不等于本地必须调用远端 Canvas；`local-runtime.md` 已明确其只描述原平台。
- 三份旧 Reference 顶部摘要、`generation.prompt_path`、KF `prompt_path`、轻量 KF `merged`、8 镜/黄金三秒、声音/VOICE/口型/字幕和 SEAM 主干都没有因文字压缩而消失。
- 五段式没有消失，只是从实际提交层搬到中文导演源；英文 H3 成稿采用另一套指定结构。
- 群众没有 K6 编号不代表缺参考；CRD 由独立字段、rules、slots 和哈希合同覆盖。

## 12. 当前版新增能力与实际收益/代价

| 当前版变化 | 经代码/文档复核的收益 | 新增代价或约束 |
|---|---|---|
| 中文导演底稿 + 英文 H3 成稿 | 导演事实与模型序列化分离；可分别审查剧情事实和 H3 标签结构；双哈希与调用记录可追溯 | 多一次真实 Skill 调用、结构校验和人工回读；转换失败是新阻塞点；旧单层 Prompt 不能直接提交 |
| `<d>`、`(Sx)` 和真实媒体槽位 | 可机器检查漏句、串人、句数、顺序、槽位和提交 Prompt SHA | 英文结构正确仍不等于语义翻译或实际声音正确；需人工复核和真实媒体验收 |
| 每次仅一个新 SEG | 下一段消费已生成、已看图、已登记的真实尾态；减少两段预编译后上游变化失配 | 用户确认、电源/进程和对账次数增加；旧两段共享授权不能直接映射 |
| 固定 queue/runner 与真实 tail 哈希链 | 固定输入、命令、输出和状态证据；防未来 tail、越界路径和静默覆盖 | 支持矩阵小于 H3 声明能力；queue 修改与 run-state SHA 存在续跑冲突 |
| provider 与模型分离 | 执行后端、协议、配置和产物可追溯；项目 JSON 不能注入任意模块 | 当前只有 AutoDL；固定入口仍硬编码其 manager/健康接口，不是完全 provider 中立 |
| task 防重与原任务 GET 恢复 | `submission_pending/unknown`、真实 POST 计数、唯一资产归属、URL 先存和全量解码显著降低盲重试风险 | 只是 task/output 路径级保护，不是全局 exactly-once；stale lock、强杀和证据优先级仍需运维处理 |
| adapter/config/run-state 哈希 | 确认尽量指向同一份代码、配置、Prompt 和素材，而非仅 SEG 编号 | adapter SHA 不覆盖共享库/注册表，不能视为完整依赖树证明 |
| AutoDL 电源/健康/清理 | 计费电源独立授权；业务健康门、状态对账和关机收尾责任明确 | 需额外授权；强杀不能保证 finally 关机；电源“不按 SEG”措辞仍有作用域歧义 |
| 本地宿主与 `tools/media.py` | 没有远端 mediakit/Canvas 时仍能完成多种真实本地处理和文件交付 | Python、ffmpeg、字体、路径和文件系统成为边界；ASR/混音/mux/画布能力不齐全 |
| 群众专属合同与 lint | 背景群众成为可登记、复用、真实传图、哈希核对和人工验收的连续性对象 | 含群众任务更易进入完整模式，增加字段、资产、读取和校验工作；当前无群众专项测试 |
| 阅读稿和逐镜删除复审 | 用户阅读稿更一致；防止用全集概括替代逐镜删除损失 | 自然语言正则和记录存在性不等于艺术质量；与 storyboard JSON 的完整交叉一致性未覆盖 |
| lint 模块化与 76 项测试 | 领域职责更清晰；关键局部合同、离线恢复、健康门和固定入口有回归保护 | 测试数量不与源码规则数量对称；回退、状态机、群众和完整 H3/确认链仍缺专项或端到端覆盖 |
| 时长双轨 | 代理规划不再为凑精确秒数机械增删剧情；用户锁定仍精确闭合 | 字段和 lint 语义改变，旧项目/自动化不能继续把 planning estimate 当 locked duration |

### 12.1 已验证事实与未验证事实

- **已验证**：76 项本地测试全部通过；当前 Skill 静态自检 0 error、0 warning、`release_ready=true`。
- **未验证**：真实 H3 模型/API 字段兼容与可用性、AutoDL 实例和电源、真实旧任务恢复、SSH TTS、外部上传、实际画面/声音质量、跨崩溃运维恢复。
- **不能泛化**：视频主链的防重、路径、哈希和恢复保证不能自动套到 image/TTS/upload/media；静态 lint 通过也不能证明艺术内容通过。

### 12.2 当前版需要优先处理的实现风险

1. **P0：queue/run-state 续跑设计冲突。** 先用不产生真实 POST 的测试替身验证多轮生命周期，明确轮换 run-state、归档还是调整哈希绑定。
2. **P0：固定入口支持矩阵与通用文档不一致。** 在视频路由和确认前暴露纯 T2VA、视频参考、video_edit、无声段限制，不能到 provider 层才发现。
3. **P1：回退与核心新合同缺测试。** 优先补 rollback、状态机、群众、H3 Prompt/媒体/完整确认和顶层 lint CLI。
4. **P1：旧文档绝对措辞残留。** 统一 interaction、Canvas、mediakit/FFmpeg、ASR、subagent、步骤编号、电源作用域和旧模型例外。
5. **P1：安全与覆盖策略不一致。** TTS 固定 SSH host key；upload 限制 URL/大小/HTTPS；approved 资产和正式成片默认拒绝覆盖；明确 stdout/stderr 合同。
6. **P2：扩大完整性绑定并统一恢复顺序。** 评估把共享库和注册表纳入执行依赖哈希；统一 saved result_url 与 concurrent unique asset 的优先级并补离线测试。


## 13. 综合结论与迁移建议

### 13.1 对五个核心问题的直接回答

**1. 当前版改变了哪些创作结果，而不只是工具名称？**

- 可执行片长改变：原版 2.5 可到 25–30 秒 SEG/30 秒轻量，当前任何 SEG 与轻量视频都只能 4–15 整数秒；长内容必须重划段。
- 用户确认次数改变：两个连续 SEG 不能再共用一次生成确认；每一段都要等上一段真实尾态和交付后再授权。
- 用户可见阅读稿改变：固定总览/提要/章节/片段/逐镜条目，禁表格和 SEG 式标题；内部十五列并未取消。
- 台词提交形式改变：中文 `{spoken_text}` 不再是最终提交；英文 H3 成稿用 `<d>` 和稳定 `(Sx)`，并受双哈希约束。
- 群众呈现改变：无台词、单镜背景人物也有外观事实；复现群众要 CRD/SRC、真实参考和请求哈希。
- 连续段输入语义改变：tail 不再一概称硬首帧，Ref2VA 普通参考和单图 I2VA 被分开。
- 候选可见性改变：正式产物仍逐项交付，但所有未采用/草稿/返修候选都展示的绝对要求弱化。
- 本地交付改变：无 Canvas/mediakit 时可走真实文件与 ffmpeg 工具链，但 ASR、混音和画布能力不能假装等价。
- 故障结果改变：提交不明、旧 ID 失效和结果 URL 有独立状态与证据链；不再只是“查询失败再试”。

**2. 哪些原版创作规则仍完整保留？**

用户显式要求优先；角色目标/阻力/策略/反馈/状态变化；三个本质不同方向与反换皮/可持续测试；全局故事圣经、分集总纲、人物弧、伏笔和结局先行；逐场因果；台词事实证据链；七轮改稿；12 维人工评估；55 个题材发动机、12 个亮点维度和受众机制；五类密度、动作单元、8 镜特定门、黄金三秒、运镜十家族、表演/声音/色彩；十五列；CHR/SCN/PROP/VOICE/STYLE、版本和复用；每集 3–4 张 KF、K0–K5、300–500 字；KF/FRM 与 planned/observed SEAM 分离；真实 tail；默认无字幕；每段交付；主观问题不自动重生；七态、revision、回退与跨集失效均保留。

**3. 哪些是本地/H3 适配所必需，哪些属于额外设计收紧？**

- **直接适配必需**：替换模型名称和时长/媒体能力；使用 H3 成稿结构；新增 provider/config/adapter 事实；本地媒体工具路由；无原平台工具时不得伪造远端 ID。
- **当前架构额外收紧**：真实调用独立 `h3-prompt-writing`、双文件双哈希、单 SEG 确认、固定 queue、强制真实 tail 后才编译下一段、独立电源 UUID 授权、只读恢复和受管关机。
- **当前特定实现选择，并非 H3 天然要求**：固定 queue 每段至少一图、禁视频、强制音轨；每次进程只一个新 SEG；这些应与模型通用能力分开说明。
- **当前创作新增而非模型必需**：CRD 群众合同、严格阅读稿和逐镜删除复审。
- **当前主动放宽**：规划估算时长、最低字符公式、所有候选即时展示、无 subagent 时主 Agent 可启动固定 runner。

**4. 是否存在规则冲突、文档与实现不一致和测试空白？**

存在，且已在第 6–12 节逐项列出。最重要的不是剧作算法消失，而是：

- 同一 queue 更新与同一 run-state SHA 不变的续跑冲突；
- 通用 H3 五模式/视频输入描述与固定 queue 能力收窄的断层；
- 本地无 ASR 与排障文档仍要求 ASR；
- 单 SEG 受管运行/退出关机与“不按 SEG 重复开关机”措辞作用域不清；
- Canvas、interaction.ask、mediakit/FFmpeg、subagent 和旧步骤编号残留；
- I2VA/L2VA 文档“一张图”与底层配置可 1–2 图的严格度层级差异；
- adapter SHA 不覆盖共享库、恢复证据优先级不一致；
- 回退、状态机、群众、完整 H3 Prompt/媒体/确认链和顶层 CLI 缺专项或端到端测试。

**5. 从原版迁移时哪些不能直接复用？**

旧模型字段、30 秒段、旧媒体阈值、单层 Prompt、1–2 SEG 确认、旧确认记录、tail 角色、旧 lint CLI、旧 provider/任务假设和轻量回退语义都不能原样复用。剧本正文和已验收原始媒体可作为事实/素材来源复用，但必须重新登记到当前合同，不能把旧 manifest 字段名当作已兼容。

### 13.2 迁移字段与产物对照

| 原版对象 | 当前版要求 | 迁移动作 |
|---|---|---|
| `skill_name=doubao-creative-drama` | `drama` | 更新入口和委派引用；frontmatter description 不变 |
| `seedance 2.0/2.5` | `H3` + 独立 `video_provider` | 不直接改字符串后执行；按真实 H3 能力重划 SEG 并选注册 provider |
| 精确规划时长 | `duration_semantics=planning_estimate|user_locked` | 明确哪些是代理估算、哪些是用户锁定；轻量仍须唯一可执行 4–15 秒 |
| `提示词_SEG...md` 单层文件 | `director_draft_file` + `compiled_prompt_file` + `h3_conversion` | 旧 Prompt 可作导演事实来源，须重建底稿、真实调用 Skill、保存英文成稿和双 SHA |
| 中文媒体标签/花括号台词 | H3 英文媒体标签、`<d>`、`(Sx)` | 保持真实 order、原语言台词/歌词/画面文字；不能只全局替换符号 |
| 一次确认 1–2 SEG | `start=end`、数量 1 | 拆成逐段确认；后续段等真实 tail、看图和交付 |
| 旧确认记录 | `confirmation_transport`、provider/run plan/hash 等 | 旧记录缺新字段会失败；不能伪造 host_tool ID，本地用户消息用唯一 `local:` |
| continuous tail 一律 start frame | Ref2VA `previous_tail_reference`；单图 I2VA 才 start+first | 按真实模式重标 role/frame_position，不改变真实 tail 硬门 |
| 无群众字段 | 数据卡/storyboard/video 的 crowds，CRD/SRC 和请求快照 | 没有群众也写 `[]`；有复现群众补外观、成员、来源和真实槽位 |
| 轻量中间阶段 confirmed/merged 的宽松理解 | planning 后固定 final/ep_1，中间 merged | 按当前 lint 重建状态；非 planning 回退实际统一到 final 修复 |
| lint `--fix/--changed-file` | 参数已删除 | 更新调用方，或明确决定恢复 no-op 兼容参数；不要继续旧命令 |
| mediakit/Canvas 记录 | 本地同步 media、真实文件链接/预览 | 不伪造远端 task/Item；缺 ASR/混音时明确人工或能力缺口 |
| 无固定 queue | 每集 `串行执行.json`、task/run-state/log | 先离线 preflight；处理 queue SHA 与 run-state 生命周期后才可逐段续跑 |
| 原任务失败即重试 | 原 provider 只读恢复、submission unknown、唯一归属 | 不删除 task 文件，不更换路径盲重发，不静默切 provider |
| 原成片字幕/ASR 证据 | 默认无字幕；用户要求时人工对轨或真实宿主 ASR | 不把估算时间写成 ASR；最终只交付一个字幕策略版本 |

### 13.3 推荐迁移顺序

1. **先冻结事实源**：保留原剧本、原始素材、approved 资产和已确认版本，不覆盖；把原 manifest 当历史证据，不当当前可直接执行文件。
2. **重确认模式与时长**：判断轻量是否仍满足 4–15 秒；完整模式区分 planning estimate 与 user lock，重划所有 SEG/bridge。
3. **迁移剧本与资产事实**：复用剧作正文和 approved 媒体；补当前数据卡、CRD、状态、真实路径和哈希，不重写无关创作。
4. **重编译分镜和阅读稿**：保留十五列主干，按新 tail role、H3 槽位和群众字段调整；生成当前严格阅读稿及逐镜删除记录。
5. **重建 Prompt 血缘**：每个当前 SEG 单独形成中文底稿，真实调用 h3-prompt-writing，保存英文成稿和双 SHA；人工回读语义后再确认。
6. **迁移确认与状态**：更新 transport、provider、run plan/hash；逐段拆授权；按当前七态和轻量 final 修复语义重建状态，不伪造历史宿主调用。
7. **先解决 runner 生命周期**：在无真实 POST 的测试替身里验证 queue/run-state 轮换、recover/reuse、锁和 tail 哈希；再考虑实机。
8. **更新 CLI 与交付自动化**：删除旧参数，按 stdout/stderr/退出码解析；准备 ffmpeg/ffprobe/字体，明确 ASR、混音和 Canvas 缺口。
9. **补测试**：优先 rollback、状态机、群众、H3 全模式、完整确认和 CLI 顶层合同，再跑全量离线测试与 lint。
10. **最后单独授权实机验收**：真实模型、账户、节点、计费和电源不属于文档迁移；必须在独立授权下验证，且不能用离线通过代替。

### 13.4 最终选型判断

- 若目标是**本地 Claude Code/Codex/baocode + H3 + AutoDL、可审计逐段生产和防重恢复**，当前版提供了原版没有的完整工具与合同，但应先修复 queue 续跑和能力声明问题。
- 若任务依赖**Seedance 2.5 长段、原生视频定点编辑、原平台 mediakit ASR、托管 Canvas 或一次确认两段**，原版语义更匹配；不能假定当前版已等价覆盖。
- 若只比较**剧本、人物、分镜、高光选点和连续性创作方法**，当前版总体高度继承，并增加群众和阅读稿约束；没有必要把当前版理解成另一套剧作体系。
- 不应把两版规则混用：尤其不能同时采用当前 H3 时长与旧 Seedance 阈值、当前单段授权与旧双层/单层 Prompt 假设、当前固定 runner 与旧原生 video_edit 语义。

## 14. 附录：逐文件结论索引

### 14.1 六个专题入口

| 专题 | 详细报告 |
|---|---|
| 创作、规划、剧本与四个创作库 | [01-creative-planning-script.md](analysis/doubao-diff/01-creative-planning-script.md) |
| 资产、群众、分镜与关键帧 | [02-assets-storyboard-keyframes.md](analysis/doubao-diff/02-assets-storyboard-keyframes.md) |
| 视频、确认、委派、provider 与恢复 | [03-video-provider-delegation.md](analysis/doubao-diff/03-video-provider-delegation.md) |
| 控制、清单、交付、本地宿主与 CLI | [04-control-manifests-delivery-cli.md](analysis/doubao-diff/04-control-manifests-delivery-cli.md) |
| lint、回退与测试 | [05-scripts-lint-tests.md](analysis/doubao-diff/05-scripts-lint-tests.md) |
| 20 个本地 tools 文件 | [06-local-tools.md](analysis/doubao-diff/06-local-tools.md) |

### 14.2 主入口与 Reference

| 文件 | 状态 | 结论位置与摘要 |
|---|---|---|
| `SKILL.md` | 已完整对照 | 第 4 节；H3 双层 Prompt、本地/provider、单 SEG、状态和交付 |
| `planning.md` | 已完整对照 | 第 5.2–5.3 节；创作算法保留，时长/provider/群众/语言改变 |
| `scriptwriter.md` | 已完整对照 | 第 5.4–5.5 节；七轮/12 维保留，最低字符公式删除 |
| `剧作方法与类型库.md` | 字节一致 | 第 5.6 节；55 个题材发动机等无版本差异 |
| `题材亮点与传播库.md` | 字节一致 | 第 5.6 节；12 个亮点维度等无版本差异 |
| `题材受众库.md` | 字节一致 | 第 5.6 节；受众心理与情绪机制无版本差异 |
| `电影大师风格库.md` | 仅 3 行替换 | 第 5.6 节；只适配中文底稿/H3 英文成稿 |
| `assets.md` | 已完整对照 | 第 6.2–6.3 节；资产主干保留，新增 CRD、fit-image、VOICE 复用 |
| `storyboard.md` | 已完整对照，含未提交版本 | 第 6.4–6.6 节；密度/十五列保留，H3/阅读稿/tail role 改变 |
| `keyframes.md` | 已完整对照 | 第 6.7 节；3–4 张、K0–K5、300–500 字保留，群众增强 |
| `crowds.md` | 当前新增 | 第 6.8 节；群众外观、成员、状态、CRD/SRC、slots/hash 全合同 |
| `video.md` | 已完整对照 | 第 7.2–7.5 节；模型、输入、双层 Prompt、台词、SEAM/FRM、字幕 |
| `video-batch-confirmation.md` | 已完整对照 | 第 7.6 节；1–2 SEG 改单 SEG，运行/provider 哈希绑定 |
| `delegation.md` | 已完整对照 | 第 7.6 节；强制 subagent 改固定 queue/runner 与 generate/recover/reuse |
| `video-provider.md` | 当前新增 | 第 7.7 节；模型/provider/协议、adapter 接口与通用恢复 |
| `video-providers/autodl.md` | 当前新增 | 第 7.7 节；AutoDL 配置、电源、健康、防重、恢复、下载、清理 |
| `troubleshooting.md` | 已完整对照 | 第 7.7–7.8 节；最早责任层级保留，新增恢复状态，ASR 残留 |
| `interaction-ask-video-clarification-ref.md` | 已完整对照 | 第 7.6、8.5 节；真实意图不变，本地确认与 subagent 旧措辞并存 |
| `control-contracts.md` | 已完整对照 | 第 8.1–8.2 节；七态、revision、失效和状态源保留，video schema 扩展 |
| `manifests.md` | 已完整对照 | 第 8.2 节；新增 provider/run plan/双层 Prompt/确认来源等字段 |
| `delivery.md` | 已完整对照 | 第 8.2–8.5 节；本地文件交付保留闭环，FFmpeg/mediakit/ASR 绝对措辞有冲突 |
| `local-runtime.md` | 当前新增 | 第 8.3 节；本地宿主、env、工具路由、文本确认和真实文件交付 |

### 14.3 十份 CLI 文档

| 文件 | 状态 | 摘要 |
|---|---|---|
| `cli/ls.md` | 字节一致 | 原版远端 CLI 文档保留，本地是否适用由 local-runtime 决定 |
| `cli/tree.md` | 字节一致 | 同上 |
| `cli/get.md` | 字节一致 | 同上 |
| `cli/create-batch.md` | 字节一致 | 同上 |
| `cli/update.md` | 字节一致 | 同上 |
| `cli/update-batch.md` | 字节一致 | 同上 |
| `cli/README.md` | 已对照 | 删除部署状态和失效引用，详见第 8.4 节 |
| `cli/workspace-create.md` | 已对照 | 删除错误的“唯一零 ID 命令”，详见第 8.4 节 |
| `cli/get-workspace.md` | 已对照 | 删除“每轮先查、重复创建幂等”的冲突动线 |
| `cli/create.md` | 已对照 | 只调整示例、预览宿主等；初始化/回读并未整体删除 |

### 14.4 脚本、测试与工具索引

- 当前 11 个脚本的逐文件职责和原版承接位置见第 9.1 节；逐校验规则、CLI、回退和退出码见第 9.2–9.7 节。
- 当前 11 个测试文件、各自测试数量、隔离方式、真实结果和覆盖空白见第 9.8–9.9 节；完整逐项表在专题 05。
- 当前 `tools/` 20 个文件（含 `tools/lib/` 六个模块）的逐文件职责见第 10.1 节；原版工具映射见第 10.2 节；实现风险见第 10.3–10.9 节；完整行号证据在专题 06。

至此，原版 30 个可维护文件均有同名映射结论，当前版新增 44 个功能文件也已按 Reference、脚本、测试和 tools 全部归类；没有把 `.pyc`、`.git`、`.gitignore` 或本报告文件计入功能差异。
