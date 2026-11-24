from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.lib import env
from tools.lib.media_facts import last_video_frame, probe_media, sha256_file


def _run(cmd: list[str], *, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)


def _ensure_file(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")


def _ensure_parent(out: str) -> None:
    Path(out).resolve().parent.mkdir(parents=True, exist_ok=True)


def _run_checked(
    command: list[str],
    *,
    error: str,
    output: str | Path | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    result = _run(command, cwd=cwd)
    if result.returncode or (output is not None and not Path(output).exists()):
        raise RuntimeError(f"{error}: {result.stderr.strip()}")
    return result


@contextmanager
def _exclusive_output(output: Path):

    _ensure_parent(str(output))
    with output.open("xb"):
        pass
    try:
        yield
    except Exception:
        output.unlink(missing_ok=True)
        raise


def cmd_frame(args) -> dict:
    _ensure_file(args.video)
    _ensure_parent(args.out)
    mode = "tail" if args.tail else ("at" if args.at is not None else "first")
    if mode == "tail":
        frame = last_video_frame(args.video)
        cmd = ["ffmpeg", "-y", "-v", "error", "-xerror", "-i", args.video,
               "-map", "0:v:0", "-vf", f"select=eq(n\\,{frame['frame_index']})",
               "-vsync", "0", "-frames:v", "1", "-update", "1", args.out]
    elif mode == "at":
        cmd = ["ffmpeg", "-y", "-ss", str(args.at), "-i", args.video,
               "-frames:v", "1", args.out]
    else:
        cmd = ["ffmpeg", "-y", "-i", args.video, "-frames:v", "1", args.out]
    _run_checked(cmd, error="抽帧失败", output=args.out)
    facts = {"ok": True, "command": "frame", "mode": mode,
             "output_file": str(Path(args.out).resolve()),
             "source_file": str(Path(args.video).resolve()),
             "source_sha256": sha256_file(args.video)}
    if mode == "tail":
        facts.update(frame)
    elif mode == "at":
        facts["requested_timestamp_s"] = args.at
    return facts


def _duration_s(path: str) -> float:
    p = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=noprint_wrappers=1:nokey=1", path])
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise RuntimeError(f"无法读取视频时长: {p.stderr.strip() or p.stdout.strip()}")


def cmd_strip(args) -> dict:
    _ensure_file(args.video)
    if not math.isfinite(args.interval) or args.interval <= 0 or args.cols < 1:
        raise ValueError("--interval 须为有限正数，--cols 须为正整数")
    _ensure_parent(args.out)
    frames = max(1, int(_duration_s(args.video) / args.interval + 0.5))
    cols = max(1, min(args.cols, frames))
    rows = (frames + cols - 1) // cols
    vf = f"fps=1/{args.interval},scale=480:-1,tile={cols}x{rows}"
    _run_checked(
        ["ffmpeg", "-y", "-i", args.video, "-vf", vf, "-frames:v", "1", args.out],
        error="帧条生成失败", output=args.out,
    )
    return {"ok": True, "command": "strip", "frames": frames, "cols": cols,
            "rows": rows, "output_file": str(Path(args.out).resolve())}


def cmd_probe(args) -> dict:
    _ensure_file(args.video)
    if args.json:
        p = _run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                  "-of", "json", args.video])
        if p.returncode != 0:
            raise RuntimeError(f"探测失败: {p.stderr.strip()}")
        return json.loads(p.stdout)
    facts = probe_media(args.video)
    facts.update(ok=True, command="probe", source_file=str(Path(args.video).resolve()))
    return facts


def cmd_trim(args) -> dict:
    _ensure_file(args.video)
    if args.end is not None and args.start is not None and args.end <= args.start:
        raise ValueError(f"--end ({args.end}) 必须大于 --start ({args.start})")
    _ensure_parent(args.out)
    cmd = ["ffmpeg", "-y"]
    if args.start is not None:
        cmd += ["-ss", str(args.start)]
    cmd += ["-i", args.video]
    if args.end is not None:
        cmd += ["-t", str(args.end - (args.start or 0))]

    cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k", args.out]
    _run_checked(cmd, error="裁剪失败", output=args.out)
    return {"ok": True, "command": "trim",
            "output_file": str(Path(args.out).resolve()),
            "start_s": args.start, "end_s": args.end,
            "media": probe_media(args.out)}


def _parse_audio_removal(text: str) -> tuple[float, float]:
    try:
        start_text, end_text = text.split(":", 1)
        start, end = float(start_text), float(end_text)
    except ValueError:
        raise ValueError(f"--remove 格式应为 START:END 秒: {text}") from None
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError(f"--remove 必须满足 0 <= START < END: {text}")
    return start, end


def cmd_cut_audio(args) -> dict:
    _ensure_file(args.audio)
    source, output = Path(args.audio).resolve(), Path(args.out).resolve()
    if source == output or output.exists():
        raise ValueError("音频派生必须写入新的输出文件，不能覆盖原音或已有版本。")
    if output.suffix.lower() != ".wav":
        raise ValueError("cut-audio 输出使用 .wav，以 PCM 保存请求专用音频。")
    source_duration = _duration_s(str(source))
    removals = sorted(args.remove)
    cursor = 0.0
    for start, end in removals:
        if start < cursor or end > source_duration + 1e-6:
            raise ValueError("--remove 区间必须不重叠、按时间递增且位于源音频内。")
        cursor = end
    keeps = []
    cursor = 0.0
    for start, end in removals:
        if start > cursor:
            keeps.append((cursor, start))
        cursor = end
    if cursor < source_duration:
        keeps.append((cursor, source_duration))
    if not keeps:
        raise ValueError("删除区间后必须保留非空音频。")

    filters = []
    for index, (start, end) in enumerate(keeps):
        filters.append(
            f"[0:a]atrim=start={start:.9f}:end={end:.9f},"
            f"asetpts=PTS-STARTPTS[a{index}]"
        )
    inputs = "".join(f"[a{index}]" for index in range(len(keeps)))
    filters.append(f"{inputs}concat=n={len(keeps)}:v=0:a=1[a]")
    expected_duration = sum(end - start for start, end in keeps)
    with _exclusive_output(output):
        _run_checked(
            ["ffmpeg", "-y", "-v", "error", "-xerror", "-i", str(source),
             "-filter_complex", ";".join(filters), "-map", "[a]",
             "-c:a", "pcm_s16le", str(output)],
            error="音频区间删除失败", output=output,
        )
        actual_duration = _duration_s(str(output))
        if abs(actual_duration - expected_duration) > 0.002:
            raise RuntimeError(
                f"音频派生时长不闭合：预期 {expected_duration:.6f}，实际 {actual_duration:.6f}"
            )
        _run_checked(
            ["ffmpeg", "-v", "error", "-xerror", "-i", str(output),
             "-map", "0:a:0", "-f", "null", "-"],
            error="音频派生全量解码失败",
        )
    return {
        "ok": True, "command": "cut-audio",
        "source_file": str(source), "source_sha256": sha256_file(source),
        "source_duration_s": source_duration,
        "removed_ranges": [{"start_s": start, "end_s": end} for start, end in removals],
        "output_file": str(output), "output_sha256": sha256_file(output),
        "duration_s": actual_duration, "expected_duration_s": expected_duration,
        "full_decode_ok": True,
    }


def _info(path: str) -> dict:
    try:
        return probe_media(path)
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"无法读取片段规格 {path}: {exc}")


def _segment_graph(index: int, facts: dict, width: int, height: int) -> tuple[list[str], dict]:
    duration = math.ceil(facts["duration_s"] * 24 - 1e-7) / 24
    video_head = facts["video_start_s"] - facts["timeline_start_s"]
    video_tail = max(0, duration - video_head - facts["video_duration_s"])
    video = (
        f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        f"setpts=PTS-STARTPTS,tpad=start_mode=clone:start_duration={video_head}:"
        f"stop_mode=clone:stop_duration={video_tail},fps=24:round=up,"
        f"trim=duration={duration},format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
    )
    if facts["has_audio"]:
        audio_head = max(0, facts["audio_start_s"] - facts["timeline_start_s"])
        audio = (
            f"[{index}:a:0]aresample=48000,aformat=channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS,adelay={audio_head * 1000}:all=1,"
            f"apad=whole_dur={duration}[a{index}]"
        )
    else:
        audio = (
            f"anullsrc=r=48000:cl=stereo,atrim=duration={duration},"
            f"asetpts=PTS-STARTPTS[a{index}]"
        )
    details = {
        "source_duration_s": facts["duration_s"],
        "export_duration_s": duration,
        "video_clone_pad_s": video_head + video_tail,
        "audio_silence_pad_s": max(0, duration - (facts["audio_duration_s"] or 0)),
    }
    return [video, audio], details


def _concat_graph(segments: list[str], metadata: list[dict]) -> tuple[str, list[dict], float]:
    width = metadata[0]["width"] - metadata[0]["width"] % 2
    height = metadata[0]["height"] - metadata[0]["height"] % 2
    chain, timeline = [], []
    offset = 0.0
    for index, (source, facts) in enumerate(zip(segments, metadata)):
        filters, details = _segment_graph(index, facts, width, height)
        chain.extend(filters)
        timeline.append({
            "source_file": str(Path(source).resolve()), "start_s": offset, **details,
        })
        offset += details["export_duration_s"]
    inputs = "".join(f"[v{index}][a{index}]" for index in range(len(segments)))
    chain.append(f"{inputs}concat=n={len(segments)}:v=1:a=1[v][a]")
    return ";".join(chain), timeline, offset


def cmd_concat(args) -> dict:
    segments = list(args.segments)
    if not segments:
        raise ValueError("concat 需要至少 1 个片段")
    for segment in segments:
        _ensure_file(segment)
    _ensure_parent(args.out)
    graph, timeline, expected_duration = _concat_graph(segments, [_info(seg) for seg in segments])
    command = ["ffmpeg", "-y"]
    for segment in segments:
        command += ["-i", segment]
    command += [
        "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", args.out,
    ]
    _run_checked(command, error="拼接失败", output=args.out)
    return {"ok": True, "command": "concat",
            "output_file": str(Path(args.out).resolve()),
            "source_timeline": timeline, "expected_duration_s": expected_duration,
            "actual_media": probe_media(args.out)}


def _height(path: str) -> int:
    return _info(path)["height"]


def _subtitle_anchor(width: int, height: int, size: int, position: str) -> str:
    if position == "lower_third":
        return f"{{\\an5\\pos({width / 2:g},{height * 0.70:g})}}"
    baseline = height - max(size, round(height * 0.04))
    return f"{{\\an2\\pos({width / 2:g},{baseline:g})}}"


def _ass_events(lines: list[str], width: int, height: int, size: int, position: str) -> list[str]:
    anchor = _subtitle_anchor(width, height, size, position)
    events = []
    for line in lines:
        if not line.startswith("Dialogue:"):
            continue
        fields = line.split(",", 9)
        if len(fields) != 10:
            raise ValueError("字幕事件格式无效。")
        fields[3], fields[5], fields[6], fields[7] = "Default", "0", "0", "0"
        fields[9] = anchor + fields[9]
        events.append(",".join(fields))
    if not events:
        raise ValueError("SRT 没有可烧录的字幕事件。")
    return events


def _prepare_ass(srt: str, directory: str, width: int, height: int, size: int, position: str) -> Path:
    ass_file = Path(directory) / "captions.ass"
    _run_checked(
        ["ffmpeg", "-y", "-v", "error", "-i", str(Path(srt).resolve()),
         "-c:s", "ass", str(ass_file)],
        error="SRT 解析失败", output=ass_file,
    )
    lines = ass_file.read_text(encoding="utf-8-sig").splitlines()
    events = _ass_events(lines, width, height, size, position)

    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Source Han Sans SC,{size},&H00FFFFFF,&H00FFFFFF,&H80000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,0,2,16,16,0,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    ass_file.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_file


def cmd_burn(args) -> dict:
    _ensure_file(args.video)
    if not os.path.isfile(args.srt):
        raise FileNotFoundError(f"字幕文件不存在: {args.srt}")
    source, output = Path(args.video).resolve(), Path(args.out).resolve()
    if source == output:
        raise ValueError("字幕输出必须使用新文件，不能覆盖源视频。")
    if not isinstance(args.size, int) or isinstance(args.size, bool) or not 1 <= args.size <= 512:
        raise ValueError("--size 必须为 1-512 的像素字号。")
    width, height = _image_dimensions(str(source))
    _ensure_parent(str(output))
    with tempfile.TemporaryDirectory(prefix="drama-subtitles-") as directory:
        _prepare_ass(args.srt, directory, width, height, args.size, args.pos)

        _run_checked(
            ["ffmpeg", "-y", "-i", str(source), "-vf", "ass=filename=captions.ass",
             "-c:v", "libx264", "-crf", "18", "-preset", "fast",
             "-c:a", "copy", str(output)],
            error="字幕烧录失败（需 ffmpeg 带 libass）", output=output, cwd=directory,
        )
    return {"ok": True, "command": "burn",
            "output_file": str(output), "srt": str(Path(args.srt).resolve()),
            "subtitle_style": {"font_size_px": args.size, "position": args.pos,
                               "play_res_x": width, "play_res_y": height,
                               "center_y_ratio": 0.70 if args.pos == "lower_third" else None}}


def _image_dimensions(path: str) -> tuple[int, int]:


    result = _run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:v:0",
                   "-frames:v", "1", "-f", "framehash", "-"])
    if result.returncode:
        raise ValueError(f"图片无法读取：{path}")
    match = re.search(r"^#dimensions\s+0:\s*(\d+)x(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match or int(match[1]) < 1 or int(match[2]) < 1:
        raise ValueError(f"图片尺寸无效：{path}")
    return int(match[1]), int(match[2])


def _ratio_integers(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[:：]\s*(\d+)\s*", text)
    if not match:
        raise ValueError("--ratio 必须为正整数 W:H，例如 16:9。")
    width, height = int(match[1]), int(match[2])
    if width <= 0 or height <= 0 or width > 10000 or height > 10000:
        raise ValueError("--ratio 两项必须在 1-10000 之间。")
    divisor = math.gcd(width, height)
    return width // divisor, height // divisor


def _fit_geometry(source: Path, ratio: str, mode: str) -> tuple[int, int, int, int, str]:
    ratio_w, ratio_h = _ratio_integers(ratio)
    width, height = _image_dimensions(str(source))
    if mode == "pad":
        multiplier = max(math.ceil(width / ratio_w), math.ceil(height / ratio_h))
        operation = "pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black"
    else:
        multiplier = min(width // ratio_w, height // ratio_h)
        operation = "crop={target_w}:{target_h}:(iw-ow)/2:(ih-oh)/2:exact=1"
    target_w, target_h = ratio_w * multiplier, ratio_h * multiplier
    if multiplier < 1 or max(target_w, target_h) > 32768 or target_w * target_h > 100000000:
        raise ValueError("目标画幅尺寸过小或过大，请使用合理比例。")
    video_filter = "format=rgba," + operation.format(target_w=target_w, target_h=target_h) + ",setsar=1"
    return width, height, target_w, target_h, video_filter


def cmd_fit_image(args) -> dict:
    _ensure_file(args.image)
    source, output = Path(args.image).resolve(), Path(args.out).resolve()
    if not env.mime_of(str(source)).startswith("image/"):
        raise ValueError("fit-image 输入必须是图片文件。")
    if source == output or output.exists():
        raise ValueError("图片适配必须写入新的输出文件，不能覆盖原图或已有版本。")
    if output.suffix.lower() != ".png":
        raise ValueError("fit-image 输出使用 .png，以无损保存适配结果。")
    if args.mode not in {"pad", "crop"}:
        raise ValueError("--mode 必须为 pad 或 crop。")
    width, height, target_w, target_h, video_filter = _fit_geometry(source, args.ratio, args.mode)
    ratio_w, ratio_h = _ratio_integers(args.ratio)
    with _exclusive_output(output):
        _run_checked(
            ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vf", video_filter,
             "-frames:v", "1", "-pix_fmt", "rgba", "-update", "1", str(output)],
            error="图片适配失败", output=output,
        )
        actual_w, actual_h = _image_dimensions(str(output))
        if (actual_w, actual_h) != (target_w, target_h):
            raise RuntimeError("图片适配后的真实尺寸不符合目标画幅。")
        return {"ok": True, "command": "fit-image", "mode": args.mode,
                "source_file": str(source), "source_sha256": sha256_file(source),
                "output_file": str(output), "sha256": sha256_file(output),
                "source_width": width, "source_height": height,
                "width": actual_w, "height": actual_h,
                "aspect_ratio": f"{ratio_w}:{ratio_h}", "content_preserved": args.mode == "pad"}


def _parse_region(text: str) -> tuple[int, int, int, int]:
    try:
        x, y, w, h = (int(part) for part in text.split(","))
    except ValueError:
        raise ValueError(f"--region 格式应为 x,y,w,h: {text}") from None
    if w <= 0 or h <= 0:
        raise ValueError(f"--region 宽高必须为正: {text}")
    return x, y, w, h


def cmd_erase(args) -> dict:
    _ensure_file(args.video)
    if not args.region:
        raise ValueError("erase 至少需要一个 --region x,y,w,h")
    _ensure_parent(args.out)
    vf = ",".join(f"delogo=x={x}:y={y}:w={w}:h={h}" for x, y, w, h in args.region)
    _run_checked(
        ["ffmpeg", "-y", "-i", args.video, "-vf", vf,
         "-c:v", "libx264", "-crf", "18", "-preset", "fast",
         "-c:a", "copy", args.out],
        error="擦除失败", output=args.out,
    )
    return {"ok": True, "command": "erase", "regions": args.region,
            "output_file": str(Path(args.out).resolve())}


def main() -> None:
    ap = argparse.ArgumentParser(description="drama 本地 mediakit 等价能力（ffmpeg 封装）")
    sub = ap.add_subparsers(dest="command", required=True)

    p_frame = sub.add_parser("frame", help="抽帧（默认首帧；--tail 尾帧；--at 时间点）")
    p_frame.add_argument("video")
    p_frame.add_argument("out")
    where = p_frame.add_mutually_exclusive_group()
    where.add_argument("--at", type=float)
    where.add_argument("--tail", action="store_true")
    where.add_argument("--first", action="store_true")
    p_frame.set_defaults(func=cmd_frame)

    p_strip = sub.add_parser("strip", help="等距抽帧拼帧条（审片）")
    p_strip.add_argument("video")
    p_strip.add_argument("out")
    p_strip.add_argument("--interval", type=float, default=0.5)
    p_strip.add_argument("--cols", type=int, default=10)
    p_strip.set_defaults(func=cmd_strip)

    p_probe = sub.add_parser("probe", help="媒体事实 JSON（--json 输出 ffprobe 原文）")
    p_probe.add_argument("video")
    p_probe.add_argument("--json", action="store_true")
    p_probe.set_defaults(func=cmd_probe)

    p_trim = sub.add_parser("trim", help="区间裁剪（重编码，切点精确）")
    p_trim.add_argument("video")
    p_trim.add_argument("out")
    p_trim.add_argument("--start", type=float)
    p_trim.add_argument("--end", type=float)
    p_trim.set_defaults(func=cmd_trim)

    p_cut_audio = sub.add_parser("cut-audio", help="按明确时间码删除音频区间，输出新 PCM WAV")
    p_cut_audio.add_argument("audio")
    p_cut_audio.add_argument("out")
    p_cut_audio.add_argument("--remove", action="append", required=True, metavar="START:END")
    p_cut_audio.set_defaults(func=cmd_cut_audio)

    p_concat = sub.add_parser("concat", help="多片段统一规格拼接（24fps，短流自动补齐）")
    p_concat.add_argument("out")
    p_concat.add_argument("segments", nargs="+")
    p_concat.set_defaults(func=cmd_concat)

    p_burn = sub.add_parser("burn", help="SRT 字幕烧录（需 libass）")
    p_burn.add_argument("video")
    p_burn.add_argument("srt")
    p_burn.add_argument("out")
    p_burn.add_argument("--size", type=int, default=36, help="像素字号（显式 ASS PlayRes 与视频尺寸一致）")
    p_burn.add_argument("--pos", choices=["bottom", "lower_third"], default="bottom")
    p_burn.set_defaults(func=cmd_burn)

    p_erase = sub.add_parser("erase", help="固定区域 delogo 擦除（输出新版本，不覆盖原片）")
    p_erase.add_argument("video")
    p_erase.add_argument("out")
    p_erase.add_argument("--region", action="append", required=True, metavar="x,y,w,h")
    p_erase.set_defaults(func=cmd_erase)

    p_fit = sub.add_parser("fit-image", help="精确图片画幅；默认加黑边保护全部内容，输出新 PNG")
    p_fit.add_argument("image")
    p_fit.add_argument("out")
    p_fit.add_argument("--ratio", required=True, help="目标比例 W:H，正整数，例如 9:16")
    p_fit.add_argument("--mode", choices=["pad", "crop"], default="pad",
                       help="pad 保留全部内容；crop 经授权后居中裁切")
    p_fit.set_defaults(func=cmd_fit_image)

    args = ap.parse_args()
    if args.command == "erase":
        args.region = [_parse_region(text) for text in args.region]
    if args.command == "cut-audio":
        args.remove = [_parse_audio_removal(text) for text in args.remove]
    env.emit(args.func(args))


if __name__ == "__main__":
    env.run_cli(main)
