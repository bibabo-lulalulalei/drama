# drama 本地工具说明

CLI 输出通道、人类可读/原始探测例外和退出码统一见 `references/local-runtime.md`；调用方同时采集 stdout、stderr 和退出码。凭证只从环境变量或 `.env` 读取，不硬编码、不回显。视频后端选择与适配器见 `references/video-provider.md`，平台专属命令只见对应 provider 文档。

## .env 查找顺序

真实环境变量优先；文件按序合并，先存在者先入：

1. `--env-file` 显式指定
2. 环境变量 `DRAMA_ENV_FILE`
3. `tools/.env`
4. skill 根 `.env`

## 工具清单

| CLI / 模块 | 用途 | 依赖 |
|---|---|---|
| `video_run.py` | 固定读取每集 `串行执行.json`，预检并启动一次受管运行（最多一个新 SEG，可含恢复/复用） | 标准库 + 下列视频工具 |
| `video_run.example.json` | 主 Agent 填写的唯一串行输入模板 | JSON |
| `workflow_series.py` | 后端中立的 SEG 串行执行、任务恢复、真实尾帧和 run-state | 标准库 + ffmpeg/ffprobe；`h3.json` |
| `workflow_video.py` | 当前 `autodl` provider 的 Zealman/ComfyUI 适配器与直接 CLI | 标准库 + ffmpeg/ffprobe |
| `autodl_instance.py` | AutoDL 实例查询、开关机和受管任务 | 标准库 |
| `lib/video_providers.py` | provider 注册、精确选择、适配器版本/哈希绑定 | 标准库 |
| `video.py` | H3 请求、媒体槽位、HTTP 与下载校验共享模块 | 标准库 + ffmpeg/ffprobe；`h3.json` |
| `image.py` | 图片生成与参考修图 | 标准库；`image.json` |
| `media.py` | 抽帧、探测、裁剪、拼接、字幕、比例适配 | ffmpeg/ffprobe；burn 需 libass |
| `tts.py` | Qwen3-TTS 音色样片 | paramiko + ffmpeg；云主机 |
| `search.py` | 联网文本检索 | 标准库 |
| `upload.py` | S3 兼容对象存储上传 | boto3 |

## 视频固定用法

把 `video_run.example.json` 复制并填写为：

```text
episodes/ep_N/04_视频片段/串行执行.json
```

然后只调用固定入口：

```bash
python -I tools/video_run.py --project-root <项目目录> --episode ep_N
python -I tools/video_run.py --project-root <项目目录> --episode ep_N --execute
```

第一条只离线预检，并返回当前 queue 相对路径/SHA-256 及 provider、适配器版本/SHA-256、cloud config SHA-256，供主 Agent 原样写入当前 SEG 确认；此时不要求确认已经存在。第二条启用执行前确认门，核验当前 queue 实际字节和最新逐 SEG 确认后，把同一 JSON 的电源、轮询、逐段操作和确认 ID 直接填入：

```text
autodl_instance.py run-managed -> workflow_series.py run
```

不再有额外的规划、构建、执行包或启动包装步骤。固定日志为 `串行运行.log`，采用追加写入。每轮最多一个新 `generate`；进程退出后由主 Agent 看图、登记并交付当前段，再更新同一 JSON 编译和确认下一段。JSON 字段、恢复例外和段间边界见 `references/delegation.md`。

## 其他常用命令

```bash
python tools/image.py --prompt-file p.md --ratio 16:9 --out a.png
python tools/image.py --prompt-file p.md --ref anchor.png --out b.png

python tools/media.py probe a.mp4
python tools/media.py frame a.mp4 tail.png --tail
python tools/media.py concat final.mp4 seg1.mp4 seg2.mp4
python tools/media.py burn final.mp4 subs.srt final_sub.mp4 --pos lower_third
python tools/media.py fit-image a.png a_16x9.png --ratio 16:9 --mode pad

python tools/search.py "关键词" -n 8
python tools/upload.py a.png --prefix shots/
```

## 边界

- `workflow_series.py` 只通过 `lib/video_providers.py` 选择适配器。provider 身份和协议必须明确；适配器/cloud 哈希由工具计算并绑定 run-state，不要求重复手填。
- provider 适配器负责提交、恢复、下载和客观媒体校验；串行器负责授权范围、真实尾帧、来源哈希、执行锁和 checkpoint。任务恢复不新增生成 POST，内容问题不自动重生。
- 实际提交只读 h3-prompt-writing 产出的 H3 英文成稿，中文导演底稿不直接提交。普通身份、场景、高光与群众参考使用 Ref2VA。
- 视频与 TTS 的云端执行按各自后端合同包住当次 queue、单角色或整个 roles-file；同一受管进程内不按条目重复开关机。下一新 SEG 的新进程与电源授权按 provider 合同重新闭合。
- `media.py` 是 mediakit 的本地等价实现，操作日志工具名仍登记 `mediakit`。TTS 只产音色样片，视频人声默认由视频模型原生生成。
