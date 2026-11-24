# 本地运行时合同（Claude Code / Codex / baocode）

本文件是 drama Skill 本地通用工具执行、秘密处理和交付的权威。视频生成后端的选择与适配器读取 `video-provider.md`；某个 provider 的实例、电源、专属凭证、接口和恢复只读取 `video-providers/<provider>.md`。方法论各 Reference 的工具枚举按下表映射到 `tools/` 下的独立 CLI；枚举原文（`image_gen`、`text_to_video` 等）仍是 `drama_lint.py` 的校验取值，不随本地命令改名。

H3 的模式、参考使用方式和成稿结构由 `tools/h3.json`、`video.md` 与 h3-prompt-writing Skill 决定；这些模型规则与执行 provider 分开。

所有 CLI 统一约定：stdout 单行 JSON（`{"ok": true, ...}`），退出码 `0` 成功 / `1` 运行或业务失败 / `2` 参数错误。凭证只在执行时从环境变量或批准的 `.env` 读取，不写入项目、manifest、快照或 Prompt，不回显真实值。

## 工具映射总表

| 工具枚举或操作 | 本地执行 | 调用方式 |
|---|---|---|
| `image_gen`（文生图，无参考） | 知脑中转 gpt-image | `python tools/image.py --prompt-file <md> --ratio 16:9 --out <png>` |
| `image_edit`（图生图/修图，必带真实参考） | 知脑中转 gpt-image | 同上加 `--ref <图>`，可重复，顺序即参考顺序；存在 `--ref` 自动走 `/images/edits` |
| `text_to_video` / `image_to_video` / `media_to_video` / `video_edit` | 由已确认的视频模型与 `video_provider` 共同执行 | 统一使用固定入口 `tools/video_run.py` 读取每集 `串行执行.json`；底层串行与 provider 细节分别由 `workflow_series.py` 和 provider 文档负责 |
| 视频 provider 实例、电源或受管任务 | 由选中 provider 的可选生命周期能力决定 | 通用授权与所有权读取 `video-provider.md`；AutoDL 实现读取 `video-providers/autodl.md`，其他 provider 不伪造相同接口 |
| 中文导演底稿转 H3 成稿 | 宿主真实 Skill 调用 | 主 Agent 执行 `Skill(skill="h3-prompt-writing", args=<完整 drama 交接包>)`，只保存该次 Skill 产出；禁止自行仿写 |
| `text_to_audio_plus`（TTS 音色样片） | Qwen3-TTS 声音设计 | 单角色或整个 roles-file 批次使用同一受管任务；当前 AutoDL 部署的凭证和电源入口见 `video-providers/autodl.md` |
| mediakit `extract-frames` | ffmpeg（mediakit 等价） | `python tools/media.py frame <mp4> <png> [--first\|--tail\|--at S]`；帧条 `strip` |
| mediakit `probe-video-metadata` | ffprobe | `python tools/media.py probe <mp4> [--json]` |
| mediakit `trim-video` | ffmpeg | `python tools/media.py trim <in> <out> --start S --end S` |
| 请求专用音频区间删除 | ffmpeg | `python tools/media.py cut-audio <in.wav> <out.wav> --remove START:END [--remove START:END ...]`；按源音频时间码同时删除明确区间，拒绝重叠、越界和覆盖，输出新 PCM WAV，并返回来源/输出哈希、实测时长和全量解码结果 |
| mediakit `concat-video` | ffmpeg | `python tools/media.py concat <out> <seg1> [seg2 ...]`（规格不一时 letterbox 统一、24fps） |
| mediakit `add-subtitle-to-video` | ffmpeg（libass） | `python tools/media.py burn <mp4> <srt> <out> [--size 36] [--pos bottom\|lower_third]` |
| 图片目标比例适配 | 本地图片补边/裁切 | `python tools/media.py fit-image <image> <out.png> --ratio W:H [--mode pad\|crop]`；默认 pad，拒绝覆盖已有文件，记录来源、尺寸与哈希 |
| mediakit `erase-watermark` | ffmpeg delogo | `python tools/media.py erase <in> <out> --region x,y,w,h`（可重复；固定区域，输出 `_vNN` 新版本不覆盖原片） |
| mediakit `asr-subtitles` | 无 ASR | 字幕从已锁定剧本台词稿整理 SRT，时间轴按成片口播对齐，不做语音识别 |
| `FileBatchUpload`（换可访问 URL） | S3 兼容对象存储 | `python tools/upload.py <文件...> --prefix shots/`；OSS 凭证未配置时工具明确报错，先落本地交付 |
| `design-cli`（画布 Workspace） | 无本地等价物 | 本地流程不调用远端 Canvas/Workspace，相关字段留空；`references/cli/` 只描述原平台远端画布 |
| `present_files` / `file_presents`（交付展示） | 宿主文件展示能力 | 通过当前宿主实际提供的文件链接或内联预览逐项交付真实文件；不得声称调用了宿主未提供的工具 |
| `interaction.ask`（确认/询问） | 当前宿主可用的确认方式 | 按下文“本地确认与执行”映射，展示同样的参数和选项，记录用户真实选择；不把超时或默认预选当确认 |

工具参数、依赖和配置入口见 `tools/README.md`。JSON 里 `tool`/`tool_mode` 字段取值仍是左列枚举原文；只有用户可见叙述使用自然工具名称。操作日志登记媒体处理动作时工具名写 `mediakit`（`drama_lint.py` 禁用词为 `ffmpeg`、`text_to_image`）。

## 凭证与 .env

环境变量优先；`.env` 按 `tools/lib/env.py` 的顺序查找：`--env-file` > `$DRAMA_ENV_FILE` > `tools/.env` > skill 根 `.env`。凭证不复制进项目目录。

本地通用服务当前使用的变量：

- 图片：`XAI_API_KEY`（知脑中转令牌；可选 `GROK_MODELS_BASE_URL` 覆盖根地址）。
- 搜索：`SEARCH_ENGINE_HOST` / `SEARCH_ENGINE_SUBSCRIPTION_KEY`。
- 上传：`OSS_ENDPOINT_URL` / `OSS_BUCKET_NAME` / `OSS_ACCESS_KEY_ID` / `OSS_SECRET_KEY_SECRET` / `OSS_ANTI_THEFT_CHAIN`（当前未配置）。

视频 provider 与云端 TTS 的专属凭证集中在实际部署文档，不在本文件另建第二份清单。当前 AutoDL 部署读取 `video-providers/autodl.md`。需要计费电源的 provider 必须另有本次明确电源授权；视频或 TTS 生成确认不自动包含开机。图片、搜索和 media 本机即可运行。

## 视频 Provider 路由

- 视频模型和 provider 分开确认、分开记录；当前模型为 H3，当前注册 provider 可通过 `tools/lib/video_providers.py` 查询。
- 固定 `串行执行.json` 必须显式保存 `video_provider`；适配器版本和 SHA-256 由预检从真实安装代码计算并绑定 run-state，不在 JSON 中重复手填。预检、配置、run-state 绑定和新增 provider 方法统一读取 `video-provider.md`。
- `tools/workflow_series.py` 是后端中立的预检与串行 runner，只通过注册适配器提交/恢复任务，不包含云平台 endpoint、凭证或电源逻辑。
- provider 专用单段 CLI、健康门、请求协议、旧任务恢复和资产找回只从该 provider 文档调用。AutoDL 当前实现读取 `video-providers/autodl.md`。
- 不得因错误、超时、额度或工具偏好静默更换模型或 provider。新 provider 不支持已确认模型或输入时停止，不删减素材或改 Prompt 迁就后端。

## 用户可见模型名

- 生图后端为知脑中转 gpt-image（配置 `tools/image.json`，当前 model_id `gpt-image-2.5-sunburst`）；内部通道名不主动暴露给用户，项目字段按方法论写 `gpt-image`。
- 当前唯一视频模型为 MiniMax H3，用户可见名称与项目模型字段统一写 `H3`；规划、分镜、确认、请求快照和校验均以 `tools/h3.json` 为能力权威，每个 SEG 为 4–15 整数秒。
- H3 的 provider 是可替换执行位置，不把“AutoDL 封装”写进模型名。服务不可用时停止并按选中 provider 文档排查，恢复后复核已确认参数。
- TTS 为 Qwen3-TTS 声音设计：只产 5 秒级音色样片（VOICE/voice_anchor），视频人声默认由视频模型原生生成。

## 本地确认与执行

- 本地使用范围为 Claude Code、Codex 和 baocode，三者使用同一套 CLI，产物通过当前宿主提供的文件链接或内联预览查看，不需要豆包账号或远端 Canvas。
- 优先使用宿主实际提供的确认工具，例如 Claude Code 的原生确认工具或 Codex 的 `request_user_input_async`；参数结构服从当前工具真实 schema，保留确认 Ref 的单选语义和授权范围，不传入另一平台的字段。
- 宿主没有专用确认工具时，主 Agent 在完整参数后展示“按要求生成（视频生成为高消耗生成）／暂不生成”两项并等待用户明确回复；项目执行与拼接同样保留各自的选项及范围。沉默、模糊回复、预选项和历史确认均无效，参数变化后重新确认。
- 确认记录继续保存真实用户原文、当前 revision、参数范围和带时区时间。`confirmation_source` 表示工作流依据：完整模式视频批次为 `batch_preview`，轻量首次生成为 `planning_preview`；`confirmation_transport` 表示实际通道，为 `host_tool|user_message`。存在真实工具调用时记录真实调用 ID；聊天确认时生成唯一的本地确认记录 ID，以 `local:` 前缀写入 `interaction_ask_call_id`，并写 `confirmation_transport: user_message`。该 ID 只标识已收到的本地确认，不能声称调用了不存在的工具；规划、视频和拼接中引用同次确认时使用同一记录 ID。
- 视频固定 JSON、正常段间与进程退出边界只读 `delegation.md`。本地有 subagent 时由其启动并等待固定 `video_run.py` 进程；没有时由主 Agent 启动并等待同一进程，内层始终是 `autodl_instance.py run-managed` 包住的 `workflow_series.py run`。计费电源只按选中 provider 文档另行授权。TTS 同样由一个受管进程包住单角色或整个 roles-file 批次。
- `tools/media.py` 为同步命令，以退出码、实际输出文件及探测结果确认完成，不伪造远端异步 task ID。本地没有 ASR：字幕从锁定台词稿建立 SRT，再按实际音轨试听对齐，不能把估计时间写成已通过 ASR 核验；工具未实现的混音等操作应如实说明能力缺口。
- 本地字幕 `burn --size` 使用像素字号，ASS 的 PlayRes 与实际视频尺寸一致；`--pos lower_third` 把文字中心定位在画面高度 70%，`bottom` 对应底部居中。不得用固定虚拟画布缩放字号或把 70% 解释为字幕基线。

## 本地交付语义

- 每个图片/视频产物保存后检查文件存在、大小非零、可被图片解码器/ffprobe 打开（视频另做可渲染流与全量解码检查）。资产和关键帧仍按阶段即时交付；串行视频在每段运行退出并看图登记后交付，时点按 `delegation.md`。
- 正式交付必须通过当前宿主实际提供的文件链接或内联预览逐项展示，并核对真实文件与展示结果，不把未展示路径当作已交付。技术检查失败时 runner 停止对应提交并保留现场，不伪造输出；进程退出后未通过客观交付检查的文件不得宣布交付。内容、审美、口型或连续性问题不阻断 best available 输出交付，也不触发自动重生。
- 原始文件保持原位置，不因展示而复制或改写；未经用户授权不因本地交付向外部服务上传素材。
- manifest 中远端 workspace/canvas 字段留空，不用本地路径或文件 ID 填充远端字段。默认只正式展示应交付的图片、音色样片和视频；用户要求查看的文档也可提供文件入口。内部 Prompt、JSON、日志、请求快照与未交付中间视频不自动展示。
