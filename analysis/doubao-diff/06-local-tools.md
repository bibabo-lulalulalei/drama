# 当前版 drama 本地 tools 与原版工具路由深入对照

## 0. 范围、口径与结论边界

本报告只做静态源码与文档分析，没有执行任何工具源码、测试、外部 API、SSH、媒体生成、上传、下载、开机、关机或实机任务，也没有修改被审计的 Skill 文件。以下关于网络请求、远端模型、ComfyUI、AutoDL 电源、ffmpeg 编解码和恢复成功的描述，均为代码路径分析，不代表已经实机验证。

路径缩写：

- `D` = `<drama-root>`
- `O` = `<doubao-root>`
- 引用格式 `D/tools/image.py:184-196` 表示当前版根目录下对应文件的行号。

审计清单按**当前 `tools/` 下全部 20 个文本源码、配置、example 和 README 文件**统计：14 个顶层文件，加 `tools/lib/` 下 6 个文件；不计 `__pycache__` 二进制缓存。缓存中虽存在 `managed_execution`、`workflow_series_plan` 的 `.pyc`，但当前没有同名 `.py` 源码。缓存只能说明某个 Python 环境曾产生过这些字节码，**不能据此认定当前 Skill 仍具有对应模块或功能**；本报告未反编译、读取或执行这些缓存。

### 核心结论

1. 当前版不是把原版的 `image_gen`、`text_to_video` 等抽象工具简单改名，而是拆成四层：**创作层工具枚举与 lint 取值、H3 模型模式、provider adapter、AutoDL 实例/电源生命周期**。原版枚举仍保留在文档和 lint 合同中，正常视频执行却统一进入 `video_run.py`，见 `D/references/local-runtime.md:3-17`。
2. 图片仍是最接近原版的一对一映射：无参考走 `image_gen`，有参考走 `image_edit`，但后端改为知脑中转型的 gpt-image 配置，比例只映射到三种标准尺寸，精确比例需要另行 `fit-image`，见 `D/tools/image.py:25-56,110-147`、`D/tools/image.json:2-9`。
3. 视频模型已从原版 Seedance 路由改为 H3；直接 adapter CLI 能表达 T2VA/I2VA/FL2VA/L2VA/Ref2VA，但固定串行 queue 额外要求每段至少一张图片、禁止视频输入并强制音轨，因而**固定入口的实际能力小于 H3 模型和直接 CLI 的声明能力**，见 `D/tools/h3.json:4-53`、`D/tools/workflow_series.py:165-274,344-377`。
4. 原版 `video_edit` 是原生定点修改；当前方法论将 `video_edit` 解释为 Ref2VA 参考重生成，不是原位编辑，而固定 queue 又禁止视频参考。因此这条概念路由不能由当前固定 runner 完整兑现，见 `O/SKILL.md:260-276`、`D/references/video.md:284-300,427-434`。
5. `media.py` 是当前版明确批准的本地同步 ffmpeg/ffprobe 等价链路，不再服从原版“禁止 ffmpeg”的远端约束；但它没有 ASR、混音、mux 等完整能力，且不同子命令的覆盖保护并不一致，见 `O/SKILL.md:188`、`D/references/local-runtime.md:19-29,69`、`D/tools/media.py:59-535`。
6. 当前版最显著的工程收益是生成 POST 防重、`submission_unknown` 现场保护、原任务 GET 恢复、queue/provider/adapter 哈希绑定、真实尾帧哈希链、视频下载验证和受管电源对账；主要风险则是 queue 更新与 run-state 哈希锁定的续跑冲突、stale lock、adapter 哈希未覆盖共享库、TTS 自动信任 SSH host key，以及若干 URL/输出覆盖边界。

---

## 1. 20 个文件逐文件总表

| # | 文件 | 职责与主要输入/输出 | 外部依赖、凭证和副作用 | 状态、安全与关键限制 |
|---:|---|---|---|---|
| 1 | `tools/README.md` | 工具索引、`.env` 顺序、固定视频调用链和示例命令，`:16-68` | 文档本身无副作用 | 声明统一 stdout JSON、0/1/2 和凭证不回显，`:3-12`；实际有 `search --pretty`、原始 probe JSON、错误走 stderr 等例外，见第 10 节 |
| 2 | `tools/image.json` | gpt-image 根地址、model、默认尺寸、质量、超时、最多 10 张参考图及 extra，`:2-9` | 指向 `https://api.zhinaoapi.ai/v1`；说明 `XAI_API_KEY` 和 `GROK_MODELS_BASE_URL` | 仅三种标准尺寸；有参考必须 edits；note 是说明文字，真正校验仍在 `image.py` |
| 3 | `tools/h3.json` | H3 能力配置：4–15 整数秒、五种模式、各模态数量与时长上限，`:2-53` | 配置本身无网络；被共享域策略和 adapter 读取 | 目标交付比例列表不等于 provider 请求能力，`:55-56`；I2VA/L2VA 配置上限均为 2，与更严格文档不同 |
| 4 | `tools/video_run.example.json` | 固定 queue 模板：provider、cloud config、run-state、电源、poll 和 SEG 示例，`:1-37` | 模板不执行；填入真实值后会成为高消耗生成与电源流程输入 | 占位符不是可执行配置；只示例 generate，未展示 recover/reuse 所需全部事实字段 |
| 5 | `tools/image.py` | 单一 CLI 按是否有 `--ref` 分流 generations/edits；写一张输出图，`:29-56,110-170,184-229` | 标准库 HTTP；`XAI_API_KEY`；真实生成 POST，URL 返回时再 GET 下载 | 无 dry-run、任务状态、锁、自动重试和输出防覆盖；HTTP 错误可带响应正文 |
| 6 | `tools/video.py` | H3 共享模块：HTTP、配置、模式/时长、媒体槽位、Prompt 标记、task 默认路径、下载验证，`:28-162` | 标准库 + ffprobe/ffmpeg；由 `workflow_video.py` 调用 | **不是独立 CLI**；跨源重定向只移除 Authorization；下载有 `.part`、probe、全量解码和原子替换，`:135-162` |
| 7 | `tools/tts.py` | 单角色或 roles-file 批次音色样片；远端 ComfyUI Qwen3-TTS，下载后规范化 WAV，`:18-39,117-130,195-247` | paramiko、SSH、远端 Python/ComfyUI/模型、本地 ffmpeg；AutoDL SSH 环境变量 | 每项都有远端生成副作用；无 task 持久化恢复/POST 防重；`AutoAddPolicy` 自动接受未知 host key，`:91-107` |
| 8 | `tools/search.py` | Smart Search GET，抽取 `webPages.value`，`:15-54` | `SEARCH_ENGINE_HOST`、`SEARCH_ENGINE_SUBSCRIPTION_KEY`；60 秒联网 GET | 无分页、重试和正文抓取；`--pretty` 是多行文本；count 缺正数/上限校验，`:33-39` |
| 9 | `tools/upload.py` | 本地文件或 HTTP(S) URL 上传到 S3 兼容存储，返回 CDN URL，`:38-84,95-140` | boto3/botocore；5 个 OSS 环境变量；外部 GET 和真实上传 | 内容 MD5 决定 key；全量内存读取；无 dry-run、大小/SSRF 限制、上传回读或本地恢复记录 |
| 10 | `tools/media.py` | 9 个同步本地媒体子命令：frame/strip/probe/trim/cut-audio/concat/burn/erase/fit-image，`:476-535` | 本机 ffmpeg/ffprobe；burn 另需 libass 和思源黑体 | 不联网、不伪造远端 task；cut-audio/fit-image 有较强防覆盖和哈希，其他命令多为可覆盖输出 |
| 11 | `tools/autodl_instance.py` | AutoDL list/status、电源和 run-managed 子进程监督，`:18-28,554-694` | `AUTODL_APP_API_TOKEN`；固定 AutoDL HTTPS API；真实执行可计费开/关机和启动命令 | 电源默认 dry-run，真实执行需 `--execute` + 精确 UUID 确认；不确定 POST 有状态对账，但无独立持久化电源状态 |
| 12 | `tools/workflow_video.py` | AutoDL adapter + Zealman/ComfyUI 直接 CLI；prepare/submit/poll/run/status 与恢复，`:33-35,70-200,356-595,611-716` | H3 workflow endpoint；可选 `H3_WORKFLOW_API_KEY`；提交 POST、轮询/恢复 GET、视频 GET | task 先落盘再 POST，最多一次生成 POST；恢复强调身份证据；adapter 哈希只覆盖本文件，不含共享库 |
| 13 | `tools/workflow_series.py` | provider 中立的 queue preflight/run、授权范围、段间接力、reuse/recover、run-state 和锁，`:74-97,165-313,344-496` | 通过固定注册表加载 adapter；本地 ffprobe/ffmpeg；实际运行产生网络与文件副作用 | 项目路径限制、独立确认、独占锁、queue/provider 哈希绑定；直接 run 不限制最多一个 generate，stale lock 无自动恢复 |
| 14 | `tools/video_run.py` | 正常视频制作固定入口；读取每集 `串行执行.json`，组合 AutoDL manager + series runner，`:22-99` | dry-run 只本地预检；`--execute` 启动真实受管进程并追加日志，`:102-130` | 每次最多一个 generate，generate 不得消费同次未来 tail；但硬编码 AutoDL 生命周期，未向子进程传 `--env-file` |
| 15 | `tools/lib/__init__.py` | 空包标记 | 无 | 无运行逻辑，不能把包名当作额外能力 |
| 16 | `tools/lib/env.py` | dotenv、凭证读取、JSON emit/fail、URL/MIME、SHA-256、data URI、统一异常出口，`:39-151` | 读取环境变量和 `.env`；编码时读取整个本地文件 | 真实环境优先；简单 dotenv 解析；错误 JSON 到 stderr；大文件 base64 有内存放大的开销，`:57-80,99-151` |
| 17 | `tools/lib/h3_domain.py` | H3 模式、task phase、TaskRecord、媒体物化和模式策略，`:11-55,64-215` | 本地媒体读文件并转 data URI；时长由调用方注入 reader | 本地文件有 SHA-256，URL 只有字符串身份；URL 不进入本地时长检查；I2VA/L2VA 按配置可允许 2 图，`:74-91,118-147,188-205` |
| 18 | `tools/lib/json_state.py` | 状态 JSON 添加 UTC `updated_at`，写固定 `.tmp` 后 `os.replace`，`:9-14` | 本地文件写入 | 原子替换不等于事务；无 fsync、文件锁和唯一临时名，同路径并写可能冲突 |
| 19 | `tools/lib/media_facts.py` | ffprobe 时长、帧/包时间轴、末帧事实、媒体 probe；复用 SHA-256，`:24-175` | 本机 ffprobe，大量帧/包输出 | 缺 stream duration 时逐帧/逐包推算；完整列表可能耗时耗内存；`probe_media` 必须存在有效视频流，`:142-175` |
| 20 | `tools/lib/video_providers.py` | provider 注册、协议检查、统一接口检查、adapter 源码绑定，`:23-89` | 只从内置 `tools.workflow_video` 导入当前唯一 AutoDL | 项目 JSON 不能指定任意模块；禁止静默回退；SHA-256 只算 adapter 文件，不覆盖其依赖，`:61-89` |

---

## 2. 原版抽象工具到当前实现的映射

原版总路由要求按真实媒体输入选 `image_gen/image_edit/text_to_audio_plus/text_to_video/image_to_video/media_to_video/video_edit/mediakit`，见 `O/SKILL.md:260-276`；原版视频文档还给出模型、输入合同和原生编辑边界，见 `O/references/video.md:16-35,82-205,347-354`。当前版保留这些名字作为创作与 lint 枚举，但实际命令映射由 `D/references/local-runtime.md:9-33` 决定。

| 原版枚举/能力 | 当前实际入口 | 保留的语义 | 关键语义变化与缺口 |
|---|---|---|---|
| `image_gen` | `image.py`，无 `--ref`，POST `/images/generations` | 文本生成图片 | 后端改为配置中的 gpt-image；ratio 不是精确生成比例；只保存 `data[0]`；无任务恢复，见 `D/tools/image.py:29-42,110-170` |
| `image_edit` | 同一 `image.py`，至少一个 `--ref`，multipart POST `/images/edits` | 有真实视觉参考就必须走 edits | 顺序由重复 `--ref` 保留，最多 10 张；本地图只按扩展名/MIME 读取，未先真实解码，见 `D/tools/image.py:29-42,125-147` |
| `text_to_audio_plus` | `tts.py`，经 SSH 在 AutoDL ComfyUI 调 Qwen3-TTS VoiceDesign | 生成短 VOICE 音色样片，锁定 voice_anchor | 不再是原版平台 Seed Audio 工具调用；需要用户自建云环境；只产约 5 秒样片，不是正片完整配音，见 `O/references/assets.md:380-413`、`D/references/assets.md:369-405`、`D/tools/tts.py:27-39,195-247` |
| `text_to_video` | 创作枚举；正常执行 `video_run.py`；直接 CLI 可用 H3 T2VA | 零媒体文本生视频的概念仍在 | 固定 queue 每段至少一图，因此固定 runner 实际不能提交纯 T2VA；模型/时长也从原 Seedance 改为 H3 4–15 整数秒 |
| `image_to_video` | 正常执行 `video_run.py`；直接 CLI 可映射 I2VA/FL2VA/L2VA/Ref2VA | 图片驱动视频 | 原版“只有图片”的单一工具名被拆成多种 H3 模式；固定 queue 非首段第一图强制前段 tail，不等同于任意图片自由路由 |
| `media_to_video` | 直接 `workflow_video.py` 可提交 Ref2VA 图片/视频/音频；固定 queue 仅图片/音频子集 | 多模态参考生视频 | 固定 runner 禁止视频输入；URL 参考没有本地时长校验；不能将 H3 Ref2VA 与原平台工具字段一一套用 |
| `video_edit` | 文档概念映射为 Ref2VA 参考重生成 | 仍表示“基于已有视频做修改”的创作意图 | 不是原版原生定点编辑，必须重新确认；固定 queue 又禁止视频，故当前固定链路不兑现该能力，见 `D/references/video.md:427-434` |
| mediakit `extract-frames` | `media.py frame/strip` | 抽首帧、末帧、指定时间帧和帧条 | 本地同步，无远端 task ID；`tail` 是最后可定时编码帧，不自动等于“稳定无转场尾帧” |
| mediakit `probe-video-metadata` | `media.py probe`，视频深度事实另由 `media_facts.py` | 媒体探测 | 无真实远端 task 信封；`--json` 是 ffprobe 原始 JSON；全量播放/解码仍需按流程另做 |
| mediakit `trim-video` / `concat-video` | `media.py trim/concat` | 裁剪、规格统一、顺序拼接 | 本地重编码；concat 不自行完成最终交付的全部时长/播放硬门 |
| mediakit `add-subtitle-to-video` | `media.py burn` | SRT 烧录、36px、bottom/lower_third | 改为 ffmpeg libass；依赖本机字体；没有原平台 mediakit task/query 生命周期 |
| mediakit `erase-watermark` | `media.py erase` | 固定区域擦除 | 是 delogo，不是通用智能擦除；区域可为多个，但坐标合法性检查有限 |
| mediakit `asr-subtitles` | 无本地等价实现 | 当前文档承认能力缺口 | 只能按真实音轨人工试听对齐，不得伪造 ASR，见 `D/references/local-runtime.md:27,69` |
| `FileBatchUpload` | `upload.py` | 把本地/远程内容变成可访问 URL | 需要自有 S3/CDN 和凭证；不是交付动作；缺配置应失败并保留本地交付 |
| `search` 对应基础设施 | `search.py` | 当前版新增文本搜索 CLI | 不属于原版八大媒体工具；只返回搜索摘要，不抓取网页正文 |
| 无原版对应 | `autodl_instance.py` | 当前版新增实例、电源、健康门和进程收尾 | 是云资源控制面，不是生成模型；授权必须与生成确认分开 |
| 无原版对应 | `workflow_series.py` / `video_run.py` | 当前版新增串行状态机、逐段确认与恢复 | 将原版“连续 1–2 SEG 批次”收紧为固定入口每次最多一个新 SEG，见 `D/references/delegation.md:13-35,56-69` |
| `design-cli` / Canvas / Workspace | 无本地等价 | 原版远端画布不作为本地硬前置 | 当前只使用宿主真实文件链接/内联预览；不能伪造远端 Item 或 Workspace，见 `D/references/local-runtime.md:29-31,72-77` |

###  Prompt 与模型合同的额外变化

原版主要直接把中文五段式导演 Prompt 交给视频工具，见 `O/references/video.md:258-272`。当前版要求先形成中文五段式导演编译底稿，再真实调用 `h3-prompt-writing` Skill 得到英文 H3 成稿，不能由主 Agent 自行仿写，见 `D/references/video.md:41-54`、`D/references/local-runtime.md:17`。因此“工具同名”并不代表请求 payload、Prompt 语言、槽位标记或确认记录可以复用。

---

## 3. 公共运行时：环境、输出、路径和数据物化

### 3.1 `.env` 与凭证优先级

`env.py` 的候选顺序是显式 `--env-file`、`DRAMA_ENV_FILE`、`tools/.env`、Skill 根 `.env`，见 `D/tools/lib/env.py:39-54`。实现会依次读取所有存在的候选文件，并用 `os.environ.setdefault` 填值，所以：

- 已存在的真实环境变量优先；
- 多个文件含同一个 key 时，先读到的文件优先；
- 不是完整 dotenv 解析器，只处理空行、注释、可选 `export ` 和简单首尾引号；
- 文件读取 `OSError` 被忽略，可能把“文件不可读”表现为后续“缺凭证”，见 `D/tools/lib/env.py:57-96`。

`video_run.py` 没有把自己的 `--env-file` 参数传给 manager/series 子进程；它依赖继承的真实环境或子进程默认查找。因此固定入口与直接 CLI 在“显式指定非标准 env 文件”方面不完全等价，见 `D/tools/video_run.py:80-99,133-142`。

### 3.2 JSON、退出码和错误通道

`env.emit` 输出紧凑单行 JSON；`env.fail` 把 `{"ok":false,...}` 打到 **stderr** 并退出；`run_cli` 捕获 ConfigError/OSError/ValueError/RuntimeError，argparse 自身错误通常为退出码 2，见 `D/tools/lib/env.py:99-107,139-151`。因此自动化调用方应同时采集 stdout、stderr 和退出码，不能只读 stdout。

`search.py --pretty` 明确输出人类可读多行文本，`media.py probe --json` 可输出 ffprobe 原始结构，均不保证统一的 `ok:true` 信封；`video_run.py` 在子进程失败时仍先输出最终摘要，再传播非零退出码，见 `D/tools/video_run.py:118-142`。

### 3.3 本地媒体物化

`env.encode_data_uri` 一次性读完整文件，计算 SHA-256 并 base64；`h3_domain.MediaReference` 对本地文件按扩展名/MIME 校验并记录 `identity=local_bytes`，对 HTTP(S) URL 则原样透传、记录 `identity=url_string_only` 和 `sha256=None`，见 `D/tools/lib/env.py:110-136`、`D/tools/lib/h3_domain.py:64-91`。这带来三条边界：

1. 大图片/视频/音频会同时占用原始 bytes 和 base64 字符串内存；
2. MIME 检查不是实际媒体解码；
3. URL 输入的本地哈希与音视频时长均未被证明，不能和本地 bytes 的溯源强度等同。

---

## 4. 图片、搜索、上传与 TTS 详细分析

### 4.1 `image.py` + `image.json`

**CLI 与输入输出**

- `--env-file`、`--config`；
- 互斥且必填的 `--prompt-file` / `--prompt`；
- 可重复 `--ref`；
- `--ratio`、`--size`；
- 必填 `--out`，见 `D/tools/image.py:184-196`。

无 ref 时工具名为 `image_gen`，走 generations；有 ref 时工具名为 `image_edit`，走 edits，见 `D/tools/image.py:29-42,110-113`。ratio 就近选择 `1024x1024`、`1536x1024`、`1024x1536`，也可显式 `--size` 覆盖已加载配置，但不会回写 JSON，见 `D/tools/image.py:25-26,44-56`。这与当前资产文档“ratio 只选就近尺寸，精确比例另用 fit-image”一致，见 `D/references/assets.md:17-20`。

**外部请求与模型**

配置默认 model 为 `gpt-image-2.5-sunburst`、quality 为 high、timeout 为 300 秒，见 `D/tools/image.json:2-9`。请求由 model、prompt、size、quality 和 extra 合并；edits 将本地参考图读入内存形成 multipart，generations 使用 JSON，见 `D/tools/image.py:125-147`。鉴权为 `XAI_API_KEY` Bearer，根地址可由 `GROK_MODELS_BASE_URL` 覆盖，见 `D/tools/image.py:173-181`。返回只消费 `data[0].b64_json` 或 `data[0].url`；前者解码写文件，后者再发 GET 下载，见 `D/tools/image.py:150-170`。

**状态、恢复与安全边界**

- 调用即产生生成 POST，无 dry-run；无任务 ID、状态文件、锁、重试或断点恢复。
- 输出直接 `write_bytes`，可覆盖已有文件，且不先检查父目录/版本策略，见 `D/tools/image.py:216-229`。这与资产“新版本不覆盖”的方法论需要由调用方约束，工具本身不兜底，见 `D/references/assets.md:469-480`。
- 只取 `data[0]`，即使服务返回多图也不会完整保存全部结果。
- 未用图片解码器验证返回内容；非图片 bytes 也可能写入 `.png` 路径。当前本地交付文档要求保存后检查可解码，因此还需外层检查，见 `D/references/local-runtime.md:72-75`。
- `_post` 会把 HTTP 错误响应正文最多约 600 字放入异常，见 `D/tools/image.py:88-92`。工具不主动打印 API key，不等于服务端错误正文永远不含敏感数据；日志仍应按不可信外部文本处理。

### 4.2 `tts.py`

**职责与模型**

该工具不在本机跑神经网络。它经 SSH/SFTP 把临时 Python runner 和 job JSON 上传到远端 `/tmp`，远端 runner 调 `127.0.0.1:6006` 的 ComfyUI。模型固定为 `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`，配置 bf16、CUDA、flash_attention_2，见 `D/tools/tts.py:27-39,42-80`。远端 Python 固定 `/root/miniconda3/bin/python`，ComfyUI 输出根固定 `/root/ComfyUI/output`，见 `D/tools/tts.py:87-88`，可移植性依赖特定镜像布局。

**CLI 与批次**

- 单角色：`--role --instruct --text --out`；
- 批次：`--roles-file`；
- 另有 `--language`、`--ffmpeg`、`--env-file`，见 `D/tools/tts.py:237-247`。

roles-file 必须是非空数组，每项含非空 role/instruct/text/out；role 只允许 `[A-Za-z0-9_-]+`，见 `D/tools/tts.py:117-130`。语言只接受代码声明列表，见 `D/tools/tts.py:18-19`。批次串行处理，某项失败后仍继续后续角色，最后汇总 `ok=false` 并非零退出。

**凭证、网络与实机副作用**

必需 `AUTODL_SSH_HOST`、`AUTODL_SSH_PASSWORD`；可选 `AUTODL_SSH_PORT`（默认 22）、`AUTODL_SSH_USER`（默认 root），见 `D/tools/tts.py:91-107`。paramiko 使用 `AutoAddPolicy()`，会自动接受未知 SSH host key，缺少已知主机指纹校验，存在中间人信任风险。

每个 job 都向远端 ComfyUI 发 `POST /prompt`，再轮询 `/history/<prompt_id>`，最多 180 次、间隔 5 秒，见 `D/tools/tts.py:42-80`。它没有本地 task 文件、http_post_count、未知提交状态或自动恢复；网络结果不明时直接重跑可能造成新 POST。工具自身不开机/关机，文档要求由 `autodl_instance.py run-managed` 包住单角色或整个批次，见 `D/references/video-providers/autodl.md:59-85`。

**媒体与文件**

下载音频后通过 ffmpeg 转为 44.1 kHz、单声道、PCM s16le WAV，见 `D/tools/tts.py:111-114,195-221`。ffmpeg 使用 `-y`，输出可覆盖，且没有输入/输出 SHA 事实或 approved 资产防覆盖。清理只针对上传的 runner/job 临时文件，不删除 ComfyUI 已生成音频。业务语义仅是音色样片，不应冒充整集配音，见 `D/references/local-runtime.md:60`。

### 4.3 `search.py`

CLI 为位置参数 `query`、`-n/--count`（默认 8）、`--pretty`、`--env-file`，见 `D/tools/search.py:33-39`。必需 `SEARCH_ENGINE_HOST` 和 `SEARCH_ENGINE_SUBSCRIPTION_KEY`，以 Bearer 调 `<host>?q=...&count=...`，60 秒超时，只提取 `webPages.value`，见 `D/tools/search.py:15-30`。

它是真实联网 GET，但不下载结果网页；无分页、重试、缓存或状态文件。`count` 未做正数/上限校验，0、负数或极大值会交服务端处理。HTTP 错误可带最多约 300 字响应正文。`--pretty` 破坏统一单行 JSON 约定，只适合人工阅读，不宜供严格 JSON parser 消费。

### 4.4 `upload.py`

**CLI 与凭证**

接受一个或多个本地路径/HTTP(S) URL，另有 `--prefix`、`--env-file`，见 `D/tools/upload.py:116-121`。必需：

- `OSS_ENDPOINT_URL`
- `OSS_BUCKET_NAME`
- `OSS_ACCESS_KEY_ID`
- `OSS_SECRET_KEY_SECRET`
- `OSS_ANTI_THEFT_CHAIN`

见 `D/tools/upload.py:16-17`。依赖 boto3/botocore，使用 S3v4、virtual addressing 和 `upload_fileobj`，见 `D/tools/upload.py:95-113`。

**行为与限制**

远程 URL 先 GET 并把整个响应读入内存，120 秒超时；本地文件也一次性读入内存，见 `D/tools/upload.py:38-45`。对象 key 为 `prefix + 内容MD5 + 扩展名`，见 `D/tools/upload.py:70-84`。相同内容可得到相同 key，具有一定命名幂等性，但 MD5 只应视为内容寻址/去重标签，不是安全身份或抗碰撞证明。

没有 dry-run；执行即有外部读取和上传副作用。远程 GET 不限制内网地址、重定向目标或响应大小，存在 SSRF/内存耗尽边界；endpoint 和 CDN 也没有强制 HTTPS。批次逐项继续，部分失败最后非零退出。boto3 可能内部重试，但本工具没有自定义恢复记录、ETag/SHA 返回或上传后回读验证。它只解决“获得 URL”，不代表已经向用户交付；未经授权不应为本地交付而上传素材，见 `D/references/local-runtime.md:72-77`。

---

## 5. `media.py` 与媒体事实库

### 5.1 子命令、参数和实际保证

所有操作同步执行，本机调用 ffmpeg/ffprobe，不产生云端 task ID，见 `D/references/local-runtime.md:69`。

| 子命令 | CLI 摘要 | 输出与验证 | 边界 |
|---|---|---|---|
| `frame` | `video out [--first|--tail|--at S]`，`:59-82,476-483` | 抽一帧图片 | `tail` 是最后可确定时间的编码视频帧，不自动判断转场/稳定；`--at` 未显式拒绝负数或越界 |
| `strip` | `video out [--interval 0.5] [--cols 10]`，`:94-108,485-490` | 生成帧条 | 是联系表，不等于人工接缝审核 |
| `probe` | `video [--json]`，`:111-121,492-495` | 媒体元数据 | `--json` 可为 ffprobe 原始 JSON，不保证统一 `ok` 字段 |
| `trim` | `video out [--start S] [--end S]`，`:124-142,497-502` | H.264/AAC 重编码片段 | start 非负等验证有限；输出可覆盖 |
| `cut-audio` | `audio out --remove START:END`，可重复，`:145-215,504-508` | 新 PCM s16le WAV；源/输出 SHA、时长、全量解码事实 | 区间须有序、不重叠、在源时长内；输出须新 `.wav`；时长误差核对约 0.002 秒 |
| `concat` | `out seg1 [seg2...]`，`:225-294,510-513` | 按首段尺寸统一偶数宽高、letterbox、24fps、H.264/AAC，并处理头尾帧/静音 | 使用 `-y` 可覆盖；不在本函数完成全量解码和 expected/actual duration 硬门 |
| `burn` | `video srt out [--size 36] [--pos bottom|lower_third]`，`:301-373,515-521` | 临时 ASS + libass 烧录，PlayRes 跟实际视频尺寸 | 需 libass 和 Source Han Sans SC；只禁止覆盖源文件，不禁止覆盖其他已有输出 |
| `erase` | `video out --region x,y,w,h`，可重复，`:446-469,523-527` | 固定区域 delogo | 不是智能水印理解；只验证宽高为正，x/y 非负及画面内约束不足；不会自动分配 `_vNN` |
| `fit-image` | `image out.png --ratio W:H [--mode pad|crop]`，`:376-443,529-535` | pad 完整补边或 crop 中心裁切；校验尺寸并返回源/输出 SHA | 输出必须是不存在的新 PNG；不会修改原图 |

`_exclusive_output` 给 cut-audio/fit-image 提供独占创建保护，但 frame/trim/concat/burn/erase 等命令大多沿用 ffmpeg `-y` 或直接写入。文件命名中的版本递增、approved 资产不覆盖和正式成片唯一版本，主要仍是上层流程责任，不能仅凭工具名推定。

### 5.2 `media_facts.py` 的深度与成本

`probe_media` 先读取 stream/format；视频缺有效 stream duration 时，用所有解码帧的 best-effort timestamp 和末帧 duration 推算结束时间；音频缺 duration 时，用全部 packet 的 PTS/duration 推算，见 `D/tools/lib/media_facts.py:51-95,129-175`。这比只读 container duration 更严格，也给真实 tail 提供 frame_index/timestamp/relative_timestamp，见 `D/tools/lib/media_facts.py:65-86`。

代价是 `DecodedFrames.rows` 和音频 packet ends 都可能在内存中保存长媒体的完整列表；ffprobe 子进程默认 120 秒超时，长视频可能慢或超时，见 `D/tools/lib/media_facts.py:12-13,51-63,129-139`。`probe_media` 强制存在有效视频流，因此它是视频事实函数，不是通用纯音频 probe；纯音频时长走 `media_duration`，见 `D/tools/lib/media_facts.py:24-34,142-155`。

### 5.3 尚未由 media.py 完整兑现的交付能力

原版 mediakit 覆盖异步 trim/concat/probe/ASR/subtitle 等，见 `O/references/delivery.md:158-192`。当前 `media.py` 没有 ASR、独立分轨混音、通用 mux、精确双侧 12 帧接缝窗口或 0.25x 慢放命令。当前视频文档要求接缝双侧窗口和慢放审核，见 `D/references/video.md:527-536`；这意味着需要主 Agent 组合其他真实宿主能力或明确记录缺口，不能把一次 `strip` 等同于完成全部接缝验收。当前本地运行时已经承认无 ASR 和混音缺口，见 `D/references/local-runtime.md:27,69`。

---

## 6. H3 模型、共享域策略与 AutoDL workflow adapter

### 6.1 模型、provider、协议必须分开

- **模型**：MiniMax H3，项目用户可见名写 H3；
- **provider**：当前注册表只有 `autodl`；
- **协议**：`comfy_workflow_v1`；
- **adapter**：`tools.workflow_video`，版本 `1.0`。

见 `D/tools/h3.json:2-14`、`D/tools/lib/video_providers.py:23-36`、`D/tools/workflow_video.py:33-35`。当前文档也要求三维分开选择、记录和确认，见 `D/references/video-provider.md:5-46`。

H3 配置能力：

| 模式 | 共享域实际输入规则 |
|---|---|
| T2VA | 禁止所有媒体输入，见 `D/tools/lib/h3_domain.py:104-108` |
| I2VA | 至少 1 图，最多取配置 `images_max=2`；禁止视频/音频，`:118-127` 与 `D/tools/h3.json:21-25` |
| FL2VA | 恰好 2 图，禁止视频/音频，见 `D/tools/lib/h3_domain.py:111-115` |
| L2VA | 与 I2VA 共用 ImageClipPolicy，按当前配置可 1–2 图，`:118-127,150-155` |
| Ref2VA | 至少一个真实参考；最多 9 图、3 视频、3 音频，总数最多 12；音频需视觉输入；本地音视频逐项 2–15 秒且各自总计最多 15 秒，见 `D/tools/h3.json:36-52`、`D/tools/lib/h3_domain.py:130-147,188-205` |

槽位按每类从 0 开始，如 `ref_image_0`、`ref_audio_0`；Prompt 业务标记从 1 开始，由共享标记检查对齐实际输入类型，见 `D/tools/lib/h3_domain.py:64-73,168-175`、`D/tools/video.py:101-116`。

### 6.2 `video.py` 共享模块

它没有 argparse/main，不是应直接调用的第五个视频 CLI。主要职责：

- `_http` 支持 JSON/raw、HTTP 错误正文抑制、跨源重定向移除 Authorization，见 `D/tools/video.py:28-64`；
- 校验模式和整数秒，`:67-80`；
- data URI 脱敏、媒体槽位和 Prompt 标记，`:91-116`；
- 默认 task 路径为 `<out>.h3task.json`，`:119-124`；
- 下载后 probe、可选音轨要求、ffmpeg 全量解码（300 秒超时），`:135-146`；
- 先写 `<out>.h3-download.part`，状态依次 downloaded/validated/complete，最后 `os.replace` 为正式输出，`:149-162`。

安全差异是：跨源重定向只移除鉴权头，并不像 AutoDL 控制面那样直接拒绝跨源或 HTTPS 降级；正常结果下载 URL 也没有全部套用持久化 concurrent asset 的同源 `/output/` 规则。`.part` 是固定名称，可覆盖旧临时文件，不是每次独立临时文件。

### 6.3 `workflow_video.py` 直接 CLI 与统一 adapter 接口

**配置优先级与秘密**

aspect ratio、megapixels、workflow、base URL 按 CLI > 环境变量 > cloud config 读取；环境变量为 `H3_WORKFLOW_ASPECT_RATIO`、`H3_WORKFLOW_MEGAPIXELS`、`H3_WORKFLOW_ID`、`H3_WORKFLOW_BASE_URL`，可选认证为 `H3_WORKFLOW_API_KEY`，见 `D/tools/workflow_video.py:70-99,133-135`。cloud config 禁止 `token/api_key/authorization/password` 字段，`:54-63`。

adapter 接受 8 种完整画幅字符串：Square、2:3、3:2、3:4、4:3、9:16、16:9、21:9，见 `D/tools/workflow_video.py:24-28,76-89`。这与 `h3.json` 的“目标交付比例”不是同一枚举，后者明确不是 provider 参数承诺，见 `D/tools/h3.json:55-56`。

**直接 CLI**

- `submit`：Prompt 文件/文本、mode、seconds、可重复 image/video/audio、aspect/megapixels、workflow/base/config、task/out、dry-run；
- `run`：提交参数加必填 out、timeout/interval、require-audio；
- `poll`：task-file、out、timeout/interval、require-audio、poll-style；
- `status`：task-file、poll-style。

见 `D/tools/workflow_video.py:663-716`。`submit --dry-run` 不联网、不创建 task，但仍会读取并 materialize 本地素材、计算哈希，`:153-161`。`run` 是 submit 后 poll；已有任务应通过 poll 恢复，不是再 submit。timeout/interval 在直接 CLI 中缺少统一正数校验。

**统一 provider 接口**

`load_config`、`prompt_markers`、`verify_task_inputs`、`submit_segment`、`poll_segment` 是注册表要求的五个方法，见 `D/tools/lib/video_providers.py:33-36,61-79`。`verify_task_inputs` 核对 Prompt SHA、输入数量、路径及本地输入 SHA；URL 的 sha 为 None，因此 URL 只能核对字符串身份，不能证明远端内容未变，见 `D/tools/workflow_video.py:611-660`、`D/tools/lib/h3_domain.py:74-91`。

---

## 7. 提交、防重、恢复、状态、哈希与锁

### 7.1 生成 POST 的状态机

`workflow_video.py` 向 `POST {base}/api/workflow/generate` 提交，请求包含 workflow_id 和 input_values，见 `D/references/video-providers/autodl.md:111-126`。核心保护为：

1. task 已存在或正式输出已存在时拒绝新 POST；
2. POST 前先写 `submission_pending`；
3. 响应无 prompt_id 或请求异常/结果不明时写 `submission_unknown`，不立即重发；
4. 成功拿到 ID 后写 `submitted`，记录 `http_post_count=1`。

见 `D/tools/workflow_video.py:149-200`。TaskPhase 还定义 downloaded/validated/complete/failed，见 `D/tools/lib/h3_domain.py:25-55`。

这是一套很强的**本地防重证据**，但不是服务端 idempotency key：保护依赖同一个 task_file 和输出路径持续存在。删除、改名或更换 task 路径后，工具无法知道另一个路径曾经提交过同一请求，因此不能宣称跨目录、跨副本的全局 exactly-once。

### 7.2 轮询与明确失败

result 优先；HTTP 404/405/501/500 可回退 history。默认单段等待 900 秒、间隔 10 秒；只有后端明确失败才进入 failed。无活动记录或无法唯一找回时为 `STALE_OR_UNAVAILABLE`，保留现场，不自动重生，见 `D/tools/workflow_video.py:356-378,503-595`。这与 provider 文档“pending 不等于丢失、恢复不得自动 POST”一致，见 `D/references/video-providers/autodl.md:132-169`。

### 7.3 持久化恢复证据

代码可尝试：

- `/api/concurrent/assets` 中精确匹配 `promptId + workflowId` 的唯一资产；
- 与任务 base 同源、位于 `/output/`、视频扩展名合法且拒绝父目录跳转的 URL；
- task 已保存的 result_url；
- `/api/images` 只作目录辅助，不按单文件、mtime、名称或时长猜测归属。

见 `D/tools/workflow_video.py:396-468`。恢复正常路径只发送 GET；取得 URL 后先保存 result_url，再无 token GET 下载、验证并原子落盘，`:490-500`。

需要区分两种严格度：**持久化恢复路径强调唯一身份；正常成功响应中的 `_video_url` 发现较启发式**，会递归搜索并按候选评分选择，不一定像 concurrent asset 那样天然绑定 prompt_id。不能将“恢复严格”扩展成“所有正常响应 URL 都有同等唯一性证明”。

### 7.4 状态原子写入与锁

`json_state.save_state` 每次更新 UTC `updated_at`，写固定 `<name>.tmp` 后 `os.replace`，见 `D/tools/lib/json_state.py:9-14`。这可避免读者看到半截 JSON，但没有 fsync、唯一临时名和状态文件锁；若同一路径被并发写，固定 `.tmp` 仍可能互相干扰。

串行队列另有 `<run-state>.lock`，使用 `O_CREAT|O_EXCL` 创建并写 PID，正常/异常退出由 finally 删除，见 `D/tools/workflow_series.py:427-440`。进程被强杀或主机崩溃可能留下 stale lock；代码没有自动识别 PID 是否仍存活或提供安全清理命令，恢复前需人工对账，不能简单反复启动。

### 7.5 run-state 绑定内容

run-state 精确绑定 queue SHA-256 和 provider binding；binding 包含 provider ID、adapter version、adapter 源文件 SHA-256，见 `D/tools/workflow_series.py:443-453`、`D/tools/lib/video_providers.py:82-89`。adapter 哈希只覆盖 `workflow_video.py` 本身，不包括 `video.py`、`env.py`、`h3_domain.py`、`media_facts.py` 或注册表源码；共享库改变不会必然使既有 run-state 的 adapter SHA 失效，这是供应链绑定缺口。

输入侧则组合 Prompt SHA、params SHA、本地输入 SHA、queue/cloud 配置绑定、输出/任务路径与 tail 事实。其价值是让“同一个确认”尽量指向同一份真实请求和素材，而不是仅比较 SEG 编号。

---

## 8. 固定串行 queue、真实尾帧与正常入口

### 8.1 `workflow_series.py` 的 queue 合同

直接 CLI 为：

- `preflight --queue ... [--project-root ...] [--require-ready]`；
- `run --queue ... [--project-root ...] --authorized-segment SEG ... --confirmation SEG=ID ... [--timeout 900] [--interval 10]`；
- 另有全局 `--env-file`，见 `D/tools/workflow_series.py:499-519`。

queue 必须 `schema_version=1.0` 且 segments 非空，provider 和 protocol 必须显式且匹配，见 `D/tools/workflow_series.py:90-97`、`D/tools/lib/video_providers.py:49-79`。所有项目路径经 `_inside` 限制在 project root 内，拒绝绝对路径和 `..` 越界，见 `D/tools/workflow_series.py:74-83`。

preflight 的关键约束，见 `D/tools/workflow_series.py:165-274`：

- 4–15 整数秒；
- 每段至少一张图片；
- 非首段第一图必须且只能引用前一个 SEG 的 tail；
- 禁止视频参考；
- 本地音频逐项 2–15 秒，总计不超过 15 秒；
- 输入存在，可核对 input_sha256；
- 校验输出、task、tail 路径和 Prompt 标记；
- 已有输出必须按接管/reuse 事实核对，不能随意覆盖。

因此固定 queue 实际是一条**图片/音频 Ref2VA 串行链**，不是 H3 五模式的通用调度器。它也不接受真正源视频，所以不能直接兑现原生或参考式 `video_edit`。

### 8.2 generate / recover / reuse 的真实分支

- task 不存在时才允许新 submit；
- task 已存在即视为 resumed，先核对 Prompt/输入，再 poll；
- `recover` 无 task 直接失败；
- 固定 queue 的 poll 永远 `require_audio=True`；
- `reuse` 消费已有输出和 tail，可核对 existing output/media/tail 等事实。

见 `D/tools/workflow_series.py:282-313,344-377`。所以 `operation=generate` 表达的是“本段被授权进入生成/恢复范围”，不是无条件保证新 POST；如果 task 已存在，它仍走恢复。固定 `video_run.py` 另要求 recover 必须已有 task，见 `D/tools/video_run.py:38-52`。

强制音轨意味着无声 H3 片段即使符合模型能力，也不能经当前固定 queue 正常 complete；直接 CLI 虽可不设 `--require-audio`，但那不是文档指定的正常串行入口。

### 8.3 尾帧事实与人工审核边界

tail 文件已存在时 runner 拒绝覆盖。前段依赖会检查 tail 文件、源视频、run-state 中 tail SHA、源视频 SHA 和输出 SHA，形成段间哈希闭合，见 `D/tools/workflow_series.py:35-64,282-313`。没有 run-state 同源记录时，只有 reuse 路径可依据当前文件构造事实，不能随意为 generate 伪造历史 tail。

技术上 runner 使用最后可定时的视频帧；但创作文档要求主 Agent 实际看图，且“稳定无转场尾帧”可能需要人工另选，见 `D/references/video.md:492-500`、`O/references/video.md:413-421`。因此自动 tail 是连续性技术证据，不是自动审美/接缝验收。

### 8.4 授权范围与“一次一个新 SEG”

`workflow_series.py` 自身要求至少一个 authorized segment、每段独立 confirmation，前序未授权项只能 reuse，见 `D/tools/workflow_series.py:407-424`。但它**没有自行限制最多一个 generate**；直接调用可以授权多个段。

真正的单段上限在 `video_run.py`：operation 只允许 generate/recover/reuse、最多一个 generate，且 generate 不得引用同次运行中尚未产生的未来 tail；其前段必须是 reuse 且 tail 已存在，见 `D/tools/video_run.py:29-69`。这也是“不要把直接 workflow_series run 当作正常入口”的实质原因。

### 8.5 queue 更新与 run-state SHA 的续跑疑点

这是当前实现最重要的流程风险之一：

- 文档要求每轮更新同一份 `串行执行.json`，启动后不得修改，并将确认绑定到该文件 SHA，见 `D/references/delegation.md:13-35`；
- 代码在已有 run-state 时要求 `state.queue_sha256 == sha256_file(当前queue)`，任何字节变化都会拒绝续跑，见 `D/tools/workflow_series.py:443-453`；
- 固定 `video_run.py` 每轮仍读取同一个 queue 和 JSON 中同一个 run_state_file，没有自动轮换/归档 run-state 的逻辑，见 `D/tools/video_run.py:29-32,70-99`。

所以按当前静态代码，如果第一轮后按文档向同一 queue 添加/修改下一段，并沿用同一 run-state，下一轮会因 queue SHA 不同而停止。要连续多轮，必须更换 run-state、显式归档/重新初始化，或改变绑定设计；这些步骤未在固定入口中实现。该结论不需要联网即可由代码确定，但实际项目是否另有未纳入本工具的外部编排，需流程实机验证，不能假设它会自动解决。

### 8.6 `video_run.py` 的受管调用链

固定读取：

- `episodes/<episode>/04_视频片段/串行执行.json`；
- 日志 `串行运行.log`。

episode 只允许 `ep_[A-Za-z0-9_-]+`，见 `D/tools/video_run.py:14-26`。执行命令为：

```text
video_run.py
  -> autodl_instance.py run-managed
       -> workflow_series.py run
```

健康门固定为 `<base_url>/api/comfy/status`、HTTP 200、JSON `running=true`，健康间隔 10 秒、上限 300 秒；power/poll timeout 来自 queue，见 `D/tools/video_run.py:70-99`。

不带 `--execute` 时先 series preflight，不启动 manager、不联网、不创建 task，但会读取本地媒体并可能执行 ffprobe，见 `D/tools/video_run.py:102-117`。带 `--execute` 时把 manager stdout/stderr 都追加到 `串行运行.log`，当前进程只返回最终摘要 JSON并传播子进程退出码，`:118-142`。

虽然 `workflow_series.py` 被设计为 provider 中立，`video_run.py` 却硬编码 AutoDL manager 和健康接口。未来 provider 若不共享同一电源/健康门，需要扩展固定入口，不能只新增 adapter 就获得完整正常流程；这与 `D/references/video-provider.md:99-108` 的“新 provider 只增加 adapter、注册项和文档”存在可扩展性落差。

---

## 9. AutoDL 实例、电源与受管执行

### 9.1 API、凭证与网络安全

固定 API 为 `https://www.autodl.art/api/v1/adl_dev/dev/instance/pro`，实例 UUID 必须匹配 `pro-...`，见 `D/tools/autodl_instance.py:18-21,53-56`。凭证为 `AUTODL_APP_API_TOKEN`，必须传原文，不应自行添加 Bearer 前缀，`:59-68`。

控制面网络保护比普通 HTTP 工具严格：

- AutoDL API 仅 HTTPS，本地回环例外用于离线测试；
- 跨源或 HTTPS 降级重定向直接拒绝；
- 响应限制约 2 MiB；
- HTTP 错误正文抑制；
- 实例列表字段白名单。

状态查询优先 GET query，只有明确 `RequestParameterIsWrong` 才回退 GET JSON body，见 `D/tools/autodl_instance.py:124-140`。

### 9.2 子命令和副作用

- `list [--page-index] [--page-size] [--request-timeout]`：真实只读联网；
- `status --instance-uuid ...`：真实只读联网；
- `power-on` / `power-off`：默认 dry-run，不联网；
- `run-managed ... -- <command>`：默认只给计划，真实执行才启动电源和子进程。

见 `D/tools/autodl_instance.py:661-694`。真实电源需要 `--execute` 和与 UUID 完全一致的 `--confirm-power-on`、`--confirm-power-off` 或 `--confirm-power`；开机 payload 包含 `gpu` 并有计费提示，`:302-317`。还支持 wait、timeout、轮询间隔和请求超时。

健康门支持 `--health-url`、期望 HTTP 状态、`--health-json running=true`、健康间隔和超时，见 `D/tools/autodl_instance.py:156-241,635-645`。真实执行的健康 URL 是外部 GET 目标，调用方仍需审查其来源。

### 9.3 不确定电源 POST 与收尾

对于结果不确定的电源 POST，代码先反复读取实例状态对账；至少等待约 30 秒后才考虑重发，并要求两次稳定原起点读取，指数退避最高 60 秒，见 `D/tools/autodl_instance.py:25-28,398-428`。这里的重试逻辑属于 AutoDL 电源控制，不应误认为图片、TTS 或 workflow 生成也有相同能力。

run-managed 记录初始实例状态，执行开机和健康门，以无 shell 参数数组启动子进程，子进程输出到 stderr；结束后尝试关机并对账 stopped。若从 stopped 启动且开机/健康失败，也尝试收尾；若实例原本 running/starting 且子进程未启动，不就绪失败不会误关既有实例，见 `D/tools/autodl_instance.py:554-618`。

限制：

- 没有独立持久化电源状态文件；进程被强杀时 finally 式关机不能保证执行；
- 子进程启动错误或关机错误可能以异常退出，stdout 不一定仍含完整生命周期 JSON；
- 子进程普通非零退出码会传播；
- dry-run 只展示计划，不验证 `--` 后命令是否安全；
- 监督器允许任意子命令，并非只允许 drama 工具。授权者必须把完整命令也纳入审查，不能只看实例 UUID。

---

## 10. 文档、配置与脚本可能不一致之处

以下区分“可由源码直接确定”与“需要实机/外部流程进一步验证”，避免把静态疑点写成已发生故障。

| 项目 | 静态事实与引用 | 判断 |
|---|---|---|
| 固定 queue 连续续跑 | 文档每轮更新同一 JSON；run-state 要求 queue SHA 完全不变，见 `D/references/delegation.md:13-35`、`D/tools/workflow_series.py:443-453` | **确定的约束冲突**；同 run-state 下修改 queue 必被拒绝。实际项目是否另有外部归档流程待验证 |
| 固定 runner 与 H3 全模式 | H3 声明五模式；series 至少一图、禁视频、强制音轨，见 `D/tools/h3.json:8-53`、`D/tools/workflow_series.py:165-274,344-377` | **确定的能力覆盖差异**；直接 adapter 能力不能冒充固定 queue 能力 |
| `video_edit` | 当前文档定义为 Ref2VA 参考重生成；固定 queue 禁视频，见 `D/references/video.md:427-434` | **确定的正常链路缺口**；不是原生定点编辑 |
| I2VA/L2VA 图片数 | `h3.json` 和 ImageClipPolicy 允许 1–2 图；video.md 要求各仅 1 张，见 `D/tools/h3.json:21-35`、`D/tools/lib/h3_domain.py:118-127`、`D/references/video.md:86` | **确定的规则层级差异**；业务可主动更严格，但底层并未强制文档的 1 张 |
| 持久化证据优先级 | 文档列 saved result_url 第一；代码先尝试 concurrent assets，得到唯一候选即可返回，没有再先读 saved URL，见 `D/references/video-providers/autodl.md:148-156`、`D/tools/workflow_video.py:419-455` | **确定的顺序不一致**；二者都严格时不一定改变结果，但异常/多候选时可能影响恢复路径 |
| provider 可扩展性 | video-provider 文档称新增 provider 只增 adapter/注册/文档；video_run 固定 AutoDL manager，见 `D/references/video-provider.md:99-108`、`D/tools/video_run.py:80-99` | **确定的固定入口耦合**；series 中立不等于整个入口中立 |
| 统一 stdout 单行 JSON | README/local-runtime 作统一声明；错误实际走 stderr，search pretty 多行，probe 可输出原始 JSON，见 `D/tools/README.md:3`、`D/tools/lib/env.py:99-107`、`D/tools/search.py:33-39` | **确定的文档过度概括**；调用方应按具体子命令解析 |
| 图片/搜索“本机即可运行” | local-runtime 同句列出图片、搜索和 media，见 `D/references/local-runtime.md:45`；前两者代码明确调用外部 API | 措辞易误读；合理解释是“不需要云主机/电源”，不是完全离线 |
| 交付文档残留 mediakit 硬门 | 当前 delivery 前部仍有“按实际 mediakit schema/不存在则停止”，字幕段还写“不使用 FFmpeg”；后文又给本地 burn 映射，见 `D/references/delivery.md:3-15,72-74,152-158,282-311` | local-runtime 声明优先级可解决规范冲突，但文本本身仍可能误导执行者 |
| 输出 `_vNN` 不覆盖 | 方法论文档要求版本不覆盖；image/TTS/多数 media 命令可覆盖，erase 也不自动生成版本号 | 工具未统一兜底，需调用方命名与独占检查；不是每个命令都满足同一安全级别 |
| example 对 recover/reuse 的覆盖 | 模板只展示 generate 基础字段，`:14-35`；series reuse 还可消费 existing_media、tail frame index/timestamp 等 | 模板不是完整状态手册；手工复用必须读代码/preflight 结果，不能只填示例字段 |
| adapter 源码绑定 | 文档强调 adapter SHA；实现只算 workflow_video.py，见 `D/tools/lib/video_providers.py:82-89` | 哈希真实存在，但不是整个执行依赖树的完整性证明 |
| 缓存中的额外模块 | 存在 `managed_execution`、`workflow_series_plan` pyc，无对应源码 | 不能写入当前能力清单，也不能据此推定调用链；需源码或干净环境验证 |
| 真实模型/API 可用性 | 配置文件写有模型、endpoint、模式，未进行任何实机请求 | **未验证**；模型上架、账号权限、远端节点、字段兼容、配额与恢复效果均不能由静态源码保证 |

---

## 11. 实际工程收益

1. **生成防重优先于盲目重试**：`submission_pending/submission_unknown` 在 POST 前后保留现场，避免“没收到 ID 就再生成一次”，见 `D/tools/workflow_video.py:149-200`。
2. **恢复原任务而非另起任务**：poll/recover 走 GET，失效 history 不等于输出丢失，持久化资产必须唯一身份匹配，见 `D/references/video-providers/autodl.md:132-169`。
3. **哈希绑定较完整**：queue、cloud/provider binding、Prompt、params、本地输入、输出和 tail 形成可追溯链，减少确认后参数被静默替换的空间。
4. **段间接力有真实文件事实**：前段 tail 与源视频 SHA 闭合，且 generate 不能消费同次未来 tail，见 `D/tools/video_run.py:54-67`。
5. **媒体成功标准更严格**：下载后 probe、音轨检查和全量解码通过才原子落盘，避免把 HTTP 200 或一个 URL 当作成片完成，见 `D/tools/video.py:135-162`。
6. **电源授权与生成确认分离**：真实电源需要 execute 和精确 UUID；manager 有健康门、状态对账和关机收尾，见 `D/tools/autodl_instance.py:302-317,398-428,554-618`。
7. **provider 选择不可由项目 JSON 注入任意模块**：注册表固定模块并检查协议和接口，见 `D/tools/lib/video_providers.py:23-79`。
8. **项目路径越界保护**：固定 queue 的输入、task、输出和 tail 受 project root 限制，见 `D/tools/workflow_series.py:74-83`。
9. **本地可审计性较强**：大量功能仅用标准库，状态 JSON、task、run-state 和日志均可直接检查；媒体处理不再依赖不可见的远端异步黑盒。
10. **部分派生资产有强防覆盖**：cut-audio/fit-image 使用新文件和哈希事实，适合构造可复现的请求专用派生物。

---

## 12. 安全、可移植性与运维注意事项

### 12.1 凭证与日志

- 不要把凭证写入项目 JSON、Prompt、manifest 或报告；cloud config 对常见秘密字段有显式拒绝，见 `D/tools/workflow_video.py:54-63`。
- “工具不回显真实 key”不等于“所有异常正文都可安全公开”。image/search 可携带服务端错误正文；外部响应和日志应视为不可信文本。
- `video_run.py` 将 manager stdout/stderr 合并追加到日志，便于审计，但调用方仍需避免子进程打印敏感环境。
- TTS 应改为预置并校验 SSH host key；当前 `AutoAddPolicy` 不适合作为高信任生产默认。

### 12.2 URL、SSRF 与重定向

不同模块安全级别不同：AutoDL 控制面拒绝跨源/降级，共享 workflow HTTP 只移除 Authorization，upload 对远程 URL 没有内网/大小限制。不能把某一个模块的严格策略推断为全局网络安全沙箱。

特别是 `upload.py` 的远程 source、workflow 的 base/result URL、run-managed 的 health URL，均可能使本机或远端环境访问调用方指定的地址。真实使用前应限定可信域名、HTTPS、重定向、响应大小和内网访问策略。

### 12.3 文件覆盖和路径边界

固定 series 的项目路径保护不覆盖 image/TTS/upload/media 的所有自由参数。直接 CLI 可写调用方指定的本机路径，且多个工具允许覆盖；在 approved 资产、已确认成片或多版本目录中，应由上层先分配新 `_vNN` 并验证目标不存在。

原子 `os.replace` 只保证替换语义，不自动提供版本保留、崩溃一致性、备份或跨进程事务。stale lock、固定 `.tmp`、固定 `.part` 都需要运维对账。

### 12.4 外部依赖与平台差异

- 通用 Python 代码大多跨平台，但 ffmpeg/ffprobe 必须真实安装并可从 PATH 调用。
- `burn` 需要 ffmpeg libass 和实际可解析的 Source Han Sans SC 字体；仅安装同名文件不一定保证所有平台 fontconfig 能找到。
- TTS 强依赖远端 Linux 路径、指定 Conda Python、ComfyUI 自定义节点、CUDA、bf16、flash_attention_2 和已下载模型；不是“装 paramiko 即可”。
- upload 需要 boto3/botocore；image/search/workflow 网络层主要用标准库，但模型和 API 仍需真实服务。
- 大文件 data URI、上传全量读取、完整帧/包 JSON 都可能造成明显内存开销；长视频应预留时间和磁盘。
- 原版命令示例和当前文档含 POSIX 风格写法，在 Windows/PowerShell 下应按真实 shell 调整，不要把文档多行命令原样当作跨平台保证。

### 12.5 重试与恢复不能泛化

| 工具 | 当前恢复/重试能力 |
|---|---|
| image | 无任务恢复，无自动重试；重跑就是新请求 |
| search | 无重试/缓存/分页恢复 |
| upload | 无自定义恢复记录；boto3 内部重试不等于业务幂等证明 |
| TTS | 有远端 history 轮询，但无本地 task 恢复和未知提交保护 |
| media | 同步命令；失败后由调用方决定是否重跑，无远端 task |
| workflow_video | 有生成防重、GET poll/recover、持久化证据和下载现场 |
| workflow_series | 有 task/run-state/lock/tail 事实，但 stale lock 和 queue 更新需人工处理 |
| autodl_instance | 有电源不确定结果对账和有限重发；不保证强杀后的自动关机 |
| video_run | 只组合上述能力，不增加独立的跨崩溃事务管理器 |

---

## 13. 建议的优先核对顺序（不在本次执行）

1. **先用纯本地、临时测试项目验证多轮 queue 生命周期**：第一轮 generate 完成后，按文档更新同一 queue 追加下一段，观察既有 run-state 的 SHA 拒绝；在不产生真实 POST 的测试替身中确认应当轮换 run-state 还是修改绑定设计。
2. **明确固定入口的支持矩阵**：把 T2VA、单图 I2VA、FL2VA、L2VA、含视频 Ref2VA、无声段、video_edit 分别标为“固定 queue 支持/仅直接 CLI/当前不支持”，避免创作文档承诺超过 runner。
3. **统一恢复证据优先级**：选择文档的 saved result_url 优先或代码的 concurrent unique asset 优先，并补充多候选、跨源和旧 URL 的离线测试。
4. **扩大完整性绑定**：评估将共享 H3/HTTP/media 库及注册表纳入 adapter 执行依赖哈希，否则共享代码变化可能绕开既有 run-state 适配器绑定。
5. **统一输出安全策略**：至少对 approved 资产和正式成片默认拒绝覆盖；明确哪些中间文件允许 `-y`，哪些必须新 `_vNN`。
6. **收紧高边界网络与 SSH**：为 TTS 固定 host key，为 upload 限制 URL/大小/HTTPS，为 workflow 正常下载明确同源策略。
7. **补齐或显式降级媒体能力**：ASR、混音/mux、完整接缝窗口和慢放没有本地实现时，应返回明确能力缺口，不能用 probe/strip 结果冒充。
8. **最后再做实机验收**：静态审查不能证明模型可用、字段兼容、远端节点安装、生成质量、计时/计费或跨重启恢复；实机测试必须另获生成与电源授权。

---

## 14. 总结

当前版 tools 的真正价值，不是“脱离平台后仍能叫出原来的工具名”，而是把高消耗视频生成改造成可审计的本地状态机：真实素材决定 H3 槽位，固定 queue 绑定确认与哈希，每个 task 防重，恢复只读原任务，尾帧串联有文件事实，电源由独立受管生命周期包围。图片、搜索、上传和本地媒体则仍是相对轻量的独立 CLI，安全与恢复能力明显弱于视频主链。

与原版相比，可获得更强的本地透明度和防重证据，但失去了原平台工具的统一 schema、原生视频定点编辑、完整 mediakit/ASR 能力和托管 Canvas 交付。当前最需优先处理的是固定 queue 的续跑哈希冲突、固定 runner 的能力覆盖差异，以及不同 CLI 在覆盖、SSH/URL 和输出 JSON 上的非一致性。所有模型与云端行为仍须在未来的独立授权实机测试中验证。
