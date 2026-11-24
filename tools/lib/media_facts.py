from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import subprocess

from .env import sha256_file


def _run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, timeout=timeout)


def _number(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (ValueError, TypeError):
        return default


def media_duration(path: str) -> float:

    result = _run(["ffprobe", "-v", "error", "-show_entries",
                   "format=duration", "-of",
                   "default=noprint_wrappers=1:nokey=1", str(path)])
    if result.returncode:
        raise ValueError(f"ffprobe 无法读取时长: {path}")
    duration = _number(result.stdout.decode("utf-8", "replace").strip())
    if duration is None or duration <= 0:
        raise ValueError(f"媒体时长无效: {path}")
    return duration


@dataclass(frozen=True)
class StreamTimeline:
    start_s: float
    duration_s: float

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


@dataclass(frozen=True)
class DecodedFrames:
    rows: list[dict]

    @classmethod
    def load(cls, path: str) -> "DecodedFrames":
        result = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                       "-show_frames", "-show_entries",
                       "frame=best_effort_timestamp_time,duration_time,pkt_duration_time",
                       "-of", "json", str(path)])
        if result.returncode:
            raise ValueError(f"无法解码视频帧：{path}")
        frames = json.loads(result.stdout).get("frames", [])
        if not frames or any(_number(row.get("best_effort_timestamp_time")) is None
                             for row in frames):
            raise ValueError(f"视频无可确定时间的解码帧：{path}")
        return cls(frames)

    @property
    def first_timestamp_s(self) -> float:
        return _number(self.rows[0]["best_effort_timestamp_time"])

    @property
    def last_timestamp_s(self) -> float:
        return _number(self.rows[-1]["best_effort_timestamp_time"])

    def last_frame_facts(self) -> dict:
        return {"frame_index": len(self.rows) - 1,
                "timestamp_s": self.last_timestamp_s,
                "relative_timestamp_s": self.last_timestamp_s - self.first_timestamp_s}

    def video_timeline(self, path: str) -> StreamTimeline:
        start = self.first_timestamp_s
        last = self.rows[-1]
        tick = _number(last.get("duration_time") or last.get("pkt_duration_time"))
        if not tick and len(self.rows) > 1:
            tick = self.last_timestamp_s - _number(self.rows[-2]["best_effort_timestamp_time"])
        if not tick or tick <= 0:
            raise ValueError(f"无法确定视频流实际结束时间：{path}")
        return StreamTimeline(start, self.last_timestamp_s + tick - start)


def video_frames(path: str) -> list[dict]:

    return DecodedFrames.load(path).rows


def last_video_frame(path: str) -> dict:
    return DecodedFrames(video_frames(path)).last_frame_facts()


@dataclass(frozen=True)
class MediaTimeline:
    container_duration_s: float | None
    video: StreamTimeline
    audio: StreamTimeline | None
    width: int
    height: int
    codec: str

    @property
    def start_s(self) -> float:
        return min(self.video.start_s, self.audio.start_s) if self.audio else self.video.start_s

    @property
    def end_s(self) -> float:
        return max(self.video.end_s, self.audio.end_s) if self.audio else self.video.end_s

    def as_dict(self, path: str) -> dict:
        duration = self.end_s - self.start_s
        if not math.isfinite(duration) or duration <= 0 or self.video.duration_s <= 0:
            raise ValueError(f"媒体时长无效：{path}")
        return {"duration_s": duration, "container_duration_s": self.container_duration_s,
                "timeline_start_s": self.start_s, "video_start_s": self.video.start_s,
                "video_duration_s": self.video.duration_s, "video_end_s": self.video.end_s,
                "audio_start_s": self.audio.start_s if self.audio else None,
                "audio_duration_s": self.audio.duration_s if self.audio else None,
                "audio_end_s": self.audio.end_s if self.audio else None,
                "width": self.width, "height": self.height, "codec": self.codec,
                "has_audio": self.audio is not None}


def audio_timeline_from_packets(path: str, start_s: float) -> StreamTimeline:
    packets = _run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                    "-show_packets", "-show_entries",
                    "packet=pts_time,duration_time", "-of", "json", str(path)])
    if packets.returncode:
        raise ValueError(f"无法确定音频流实际结束时间：{path}")
    ends = [_number(row.get("pts_time"), 0) + _number(row.get("duration_time"), 0)
            for row in json.loads(packets.stdout).get("packets", [])]
    if not ends or max(ends) <= start_s:
        raise ValueError(f"音频流时长无效：{path}")
    return StreamTimeline(start_s, max(ends) - start_s)


def probe_media(path: str) -> dict:

    result = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                   "-of", "json", str(path)])
    if result.returncode:
        raise ValueError(f"ffprobe 未识别有效媒体：{path}")
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    video = next((row for row in streams if row.get("codec_type") == "video"
                  and row.get("codec_name") and int(row.get("width", 0)) > 0
                  and int(row.get("height", 0)) > 0), None)
    if not video:
        raise ValueError(f"不含有效视频流：{path}")
    audio = next((row for row in streams if row.get("codec_type") == "audio"), None)
    container = _number(info.get("format", {}).get("duration"))
    video_start = _number(video.get("start_time"), 0.0)
    video_duration = _number(video.get("duration"))
    if video_duration is None or video_duration <= 0:
        video_timeline = DecodedFrames(video_frames(path)).video_timeline(path)
    else:
        video_timeline = StreamTimeline(video_start, video_duration)
    audio_timeline = None
    if audio:
        audio_start = _number(audio.get("start_time"), 0.0)
        audio_duration = _number(audio.get("duration"))
        if audio_duration is None or audio_duration <= 0:
            audio_timeline = audio_timeline_from_packets(path, audio_start)
        else:
            audio_timeline = StreamTimeline(audio_start, audio_duration)
    timeline = MediaTimeline(
        container_duration_s=container, video=video_timeline, audio=audio_timeline,
        width=int(video["width"]), height=int(video["height"]), codec=video["codec_name"],
    )
    return timeline.as_dict(path)
