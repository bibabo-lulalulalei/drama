# 视频生成 Provider：选择、适配与运行合同

本文件是视频生成后端选择与适配器接口的唯一权威。`video.md` 负责导演输入、Prompt、串行连续性和交付；具体云平台的电源、凭证、API、任务恢复与资产找回只写在 `video-providers/<provider>.md`，不得复制回本文件或其他通用 Reference。

## 三个不同维度

| 维度 | 示例 | 职责 |
|---|---|---|
| 视频模型 | `H3` | 时长、模态、参考槽位、Prompt 结构和生成能力 |
| 视频 provider | `autodl` | 实际在哪里、通过什么服务执行已锁定请求 |
| 传输协议 | `comfy_workflow_v1` | 某个 provider 适配器支持的请求与查询格式 |

更换 provider 不等于更换模型，也不授权改写剧本、分镜、Prompt、SEG、时长或画幅。同一模型可以由不同 provider 承载；同一 provider 也可以支持不同协议，但必须显式选择并校验兼容性。

当前注册表只有 `autodl`，详细说明读取 `video-providers/autodl.md`。注册表可离线查询：`tools/lib/video_providers.py` 的 `registered_providers()` 只返回公开 ID、名称、协议和文档路径，不读取凭证。

## 用户选择与确认

1. 规划时读取当前注册 provider，并把选择写入 `drama_plan.model_plan.video_provider`，与 `model_plan.video` 分开。只有一个可用 provider 时记录该真实选项，不虚构第二个后端；有两个及以上时，以用户可理解的名称展示选择，不暴露 Python 模块、接口路径或适配器内部字段。
2. 完整模式在实际视频生成确认表中单列“视频生成后端”，与“视频模型”分开；轻量首次生成也在规划参数中登记实际 provider。用户未明确要求更换时沿用已确认 provider。
3. 运行前把 `video_provider` 写入固定 `串行执行.json`。provider、协议、模型、Prompt、素材、时长、输出和授权范围一起冻结；适配器版本与哈希由工具读取当前安装代码并绑定，不重复手填。
4. 执行器不得因连接失败、排障、超时、额度、速度或偏好自动切换 provider。未知 ID、queue/config 冲突、协议不兼容、适配器版本或哈希失配都必须停止。
5. 用户要求更换 provider 时更新固定 `串行执行.json` 并重新预检；若还会有新 POST，按视频生成确认规则重新展示并确认。只读恢复旧任务仍按原任务所属 provider，不得拿到另一后端查询。

## 当前配置格式

固定 `串行执行.json` 顶层显式填写：

```json
{
  "video_provider": "autodl",
  "cloud_config": "00_制作控制/cloud.json",
  "segments": []
}
```

cloud config 必须显式登记受适配器支持的 `protocol`，也可以登记同一个 `video_provider`，但与固定 JSON 不一致时拒绝执行。固定 JSON 不重复填写适配器版本或 SHA-256；`workflow_series.py preflight` 根据真实安装代码自动计算。缺少显式 provider、cloud config 缺少 protocol 或二者不受支持时直接停止，不根据其他字段推断。

`preflight` 和运行结果包含：

- `video_provider`
- `video_provider_adapter_version`
- `video_provider_adapter_sha256`
- `cloud_config_sha256`

run-state 必须完整保存这些工具计算出的绑定，并与当次固定 JSON、配置及安装代码完全一致；缺字段或值不同都拒绝续跑，不自动补写。`video_provider_adapter_sha256` 是对适配器及其 `EXECUTION_DEPENDENCY_FILES` 声明的固定执行依赖按相对路径和实际字节共同计算的指纹，不是只哈希适配器入口文件。确认记录使用同次 preflight 的返回值，不在固定 JSON 中手工复制这些哈希。合法推进到下一版 queue 时仍需满足 `delegation.md` 的历史段 `reuse`、顺序和哈希闭合条件，不能用续跑名义更换 provider 或执行依赖。

## 统一适配器接口

注册表只允许导入 Skill 内置且已审核的模块，不能从项目 JSON 指定任意 Python 路径。一个 provider 至少实现：

```python
PROVIDER_ID = "<registered-id>"
ADAPTER_VERSION = "<adapter-version>"
EXECUTION_DEPENDENCY_FILES = ("relative/dependency.py", ...)

load_config(path) -> dict
prompt_markers(prompt, records) -> dict
verify_task_inputs(task_file, *, config, entry, images, audio,
                   prompt_file, output) -> None
submit_segment(*, config, entry, images, audio,
               prompt_file, task_file, output) -> dict
poll_segment(*, task_file, output, timeout, interval,
             require_audio, resumed) -> dict
```

职责边界：

- `EXECUTION_DEPENDENCY_FILES` 只声明该适配器正常固定执行链实际共享的 Skill 内相对源码路径；适配器入口文件自动纳入同一指纹，项目 JSON 不能增删这份清单。
- `load_config` 校验 provider 配置并拒绝文件内凭证。
- `prompt_markers` 核对已编译 Prompt 的媒体标记与实际记录；模型创作规则仍由通用流程拥有。
- `verify_task_inputs` 在已有任务恢复前用与提交共用的请求构造参数离线核对完整原请求：config/workflow、base URL/view path、H3 mode、秒数、画幅、分辨率、Prompt SHA-256、完整参数 SHA-256、输出路径，以及每个图片/音频槽位的顺序、真实路径和 SHA-256。只比较 Prompt 和媒体数组不足以证明同一请求；该核验不得产生新 POST。
- `submit_segment` 只提交传入的一个已授权片段；每个任务文件最多一次真实提交。
- `poll_segment` 恢复原任务、查询、下载和客观媒体校验。`resumed=True` 表示跨进程已有任务，不能当成刚提交任务处理。
- 两个执行结果统一提供 `task_id`；provider 自己的 ID 可留在其任务文件，串行器不依赖 `prompt_id`、实例 UUID 或云平台状态名。

通用串行器继续拥有：授权 SEG 与 confirmation 映射、执行锁、连续范围、固定输入和上一段真实 tail/source 哈希、输出白名单、媒体 tail 抽取、run-state 和进程退出对账。它不得包含 provider 专用 endpoint、凭证、电源命令或恢复协议。

## 原任务恢复的共同底线

具体证据和接口由所选 provider 文档定义，但所有 provider 都遵守：

1. 已有任务的只读恢复、原结果下载、媒体校验和同源 tail 补抽不新增生成授权。
2. 恢复不得产生新的生成 POST；不能因为旧 ID 查询为空、接口异常或超时就重提。
3. 优先使用原任务已保存的结果证据和能精确绑定任务身份的持久化记录。
4. 文件修改时间、时长相近、目录里只有一个视频、文件名相似或“看起来像”都不能独立证明任务归属。
5. 无法唯一归属时保留原任务和现场并停止，交给主 Agent；不得标记为可盲目重试的新任务。
6. 取得结果 URL 后先保存，再下载、检查音轨与全量解码、原子落盘；本地失败不抹掉已经取得的结果证据。
7. 明确的后端失败与“旧任务暂不可查询”分开记录，后者不伪报生成失败或成功。

## 可选电源生命周期

provider 可以支持本地、托管 API 或需要开关机的云主机，统一接口不强迫所有后端实现电源接口。需要计费电源时：

- 视频生成确认不自动包含开机授权；必须另有本次精确实例/资源和电源范围确认。
- 一个受管监督进程拥有当次 queue 与开机、健康门、任务、关机、最终状态对账；真实电源动作前必须已经通过 `delegation.md` 的“先全部准备，后一次启动”硬门。
- 同一受管进程内不重复开关机；异常退出也要执行该 provider 的收尾。下一新 SEG 的新进程与电源授权按本文件和选中 provider 文档重新闭合。
- 不支持电源生命周期的 provider 不伪造 `run-managed`、`stopped` 或实例状态。

AutoDL 的电源授权、健康门、退出码和 stopped 对账只在 `video-providers/autodl.md` 维护。

## 新增第二种 Provider

新增 provider 时，适配器层至少增加：

1. 一个实现上述接口的适配器模块。
2. 注册表中的一条固定 ID、支持协议和文档映射。
3. `references/video-providers/<provider>.md`，完整说明其配置、凭证、提交、恢复、错误分类及可选电源生命周期。
4. 离线测试：精确选择、未知 ID 拒绝、协议/版本/哈希失配拒绝、串行器仅经统一接口调用、恢复路径无生成 POST。

当前固定入口只实现了 AutoDL 的受管电源生命周期。新 provider 若采用本地、托管 API 或其他生命周期，还必须在固定入口和本地运行文档中实现并测试真实的按 provider 路由；不得把它送进 `autodl_instance.py run-managed`，也不得伪造 AutoDL 实例或 `stopped` 状态。

不得为接入新 provider 修改剧本、分镜、Prompt 编译、真实尾帧接力或交付规则。若新 provider 不支持当前模型或必需模态，必须在预检停止，不得删减输入或静默换模型来适配它。
