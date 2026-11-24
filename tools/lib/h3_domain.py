from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from . import env


class VideoMode(str, Enum):
    TEXT_TO_VIDEO = "T2VA"
    IMAGE_TO_VIDEO = "I2VA"
    FIRST_LAST_TO_VIDEO = "FL2VA"
    LAST_FRAME_TO_VIDEO = "L2VA"
    REFERENCE_TO_VIDEO = "Ref2VA"


class MediaKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class TaskPhase(str, Enum):
    SUBMISSION_PENDING = "submission_pending"
    SUBMISSION_UNKNOWN = "submission_unknown"
    SUBMITTED = "submitted"
    DOWNLOADED = "downloaded"
    VALIDATED = "validated"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class TaskRecord:


    state: dict

    @property
    def phase(self) -> str | None:
        return self.state.get("phase")

    @property
    def task_id(self):
        return self.state.get("task_id")

    def transition(self, phase: TaskPhase, **fields) -> None:
        self.state.update(fields)
        self.state["phase"] = phase.value

    def fail(self, backend_status: str | None = None) -> None:
        fields = {"backend_status": backend_status} if backend_status is not None else {}
        self.transition(TaskPhase.FAILED, **fields)


@dataclass(frozen=True)
class MaterializedSlot:
    value: str
    record: dict


@dataclass(frozen=True)
class MediaReference:
    kind: MediaKind
    source: str
    index: int

    @property
    def slot(self) -> str:
        return f"ref_{self.kind.value}_{self.index}"

    def materialize(self) -> MaterializedSlot:
        kind = self.kind.value
        if env.is_url(self.source):
            return MaterializedSlot(self.source, {
                "slot": self.slot, "kind": kind, "identity": "url_string_only",
                "ref": self.source, "sha256": None,
            })
        path = Path(self.source)
        if not path.is_file():
            raise FileNotFoundError(f"{kind} 参考文件不存在: {self.source}")
        mime = env.mime_of(str(path))
        if not mime.startswith(kind + "/"):
            raise ValueError(f"{self.source} 的 MIME {mime or '未知'} 与 {kind} 槽位不符")
        uri, mime, digest = env.encode_data_uri(str(path))
        return MaterializedSlot(uri, {
            "slot": self.slot, "kind": kind, "identity": "local_bytes",
            "ref": str(path.resolve()), "mime": mime, "sha256": digest,
        })


class VideoModePolicy(Protocol):
    def validate(self, request: "MediaSlotRequest") -> None:
        ...


def _reject_non_images(request: "MediaSlotRequest", mode: str) -> None:
    if request.count(MediaKind.VIDEO) or request.count(MediaKind.AUDIO):
        raise ValueError(f"{mode} 只接受图片输入；视频/音频参考请用 Ref2VA")


class TextToVideoPolicy:
    def validate(self, request: "MediaSlotRequest") -> None:
        if request.total:
            raise ValueError("T2VA 不接受任何媒体输入；有输入请按真实类型选 I2VA/FL2VA/L2VA/Ref2VA")
        _reject_non_images(request, VideoMode.TEXT_TO_VIDEO.value)


class FirstLastFramePolicy:
    def validate(self, request: "MediaSlotRequest") -> None:
        if request.count(MediaKind.IMAGE) != 2:
            raise ValueError("FL2VA（首尾帧）必须且只能给 2 张图片")
        _reject_non_images(request, VideoMode.FIRST_LAST_TO_VIDEO.value)


class ImageClipPolicy:
    def __init__(self, mode: VideoMode):
        self.mode = mode

    def validate(self, request: "MediaSlotRequest") -> None:
        count = request.count(MediaKind.IMAGE)
        maximum = request.limits["images_max"]
        if not 1 <= count <= maximum:
            raise ValueError(f"{self.mode.value} 需要 1-{maximum} 张图片")
        _reject_non_images(request, self.mode.value)


class ReferenceVideoPolicy:
    def validate(self, request: "MediaSlotRequest") -> None:
        if not request.total:
            raise ValueError("Ref2VA 必须有真实参考输入")
        if request.limits.get("audio_requires_visual_input") \
                and request.count(MediaKind.AUDIO) and not request.has_visual_input:
            raise ValueError("音频参考必须同时有视觉输入")
        if request.total > request.limits.get("total_files_max", 10 ** 9):
            raise ValueError(
                f"参考文件总数 {request.total} 超上限 {request.limits['total_files_max']}")
        for kind, plural in ((MediaKind.IMAGE, "images"),
                             (MediaKind.VIDEO, "videos"),
                             (MediaKind.AUDIO, "audios")):
            count = request.count(kind)
            if count > request.limits.get(plural + "_max", 0):
                raise ValueError(
                    f"{kind.value} 参考 {count} 个超上限 {request.limits[plural + '_max']}")
        request.validate_local_durations()


VIDEO_MODE_POLICIES: dict[str, VideoModePolicy] = {
    VideoMode.TEXT_TO_VIDEO.value: TextToVideoPolicy(),
    VideoMode.IMAGE_TO_VIDEO.value: ImageClipPolicy(VideoMode.IMAGE_TO_VIDEO),
    VideoMode.FIRST_LAST_TO_VIDEO.value: FirstLastFramePolicy(),
    VideoMode.LAST_FRAME_TO_VIDEO.value: ImageClipPolicy(VideoMode.LAST_FRAME_TO_VIDEO),
    VideoMode.REFERENCE_TO_VIDEO.value: ReferenceVideoPolicy(),
}


@dataclass
class MediaSlotRequest:
    images: list[str] | None
    videos: list[str] | None
    audios: list[str] | None
    mode: str
    limits: dict
    duration_reader: Callable[[str], float]

    @property
    def references(self) -> list[MediaReference]:
        groups = ((MediaKind.IMAGE, self.images or []),
                  (MediaKind.VIDEO, self.videos or []),
                  (MediaKind.AUDIO, self.audios or []))
        return [MediaReference(kind, source, index)
                for kind, sources in groups
                for index, source in enumerate(sources)]

    def count(self, kind: MediaKind) -> int:
        return sum(reference.kind is kind for reference in self.references)

    @property
    def total(self) -> int:
        return len(self.references)

    @property
    def has_visual_input(self) -> bool:
        return bool(self.count(MediaKind.IMAGE) or self.count(MediaKind.VIDEO))

    def validate_local_durations(self) -> None:
        totals = {MediaKind.VIDEO: 0.0, MediaKind.AUDIO: 0.0}
        for record in self._records:
            kind_value = record["kind"]
            if kind_value not in {kind.value for kind in totals} \
                    or record["identity"] != "local_bytes":
                continue
            kind = MediaKind(kind_value)
            duration = self.duration_reader(record["ref"])
            low, high = self.limits[kind_value + "_per_clip_s"]
            if not low <= duration <= high:
                raise ValueError(
                    f"{record['ref']} 时长 {duration:.2f}s 超出 {low}-{high}s 能力范围")
            totals[kind] += duration
        for kind, total in totals.items():
            cap = self.limits.get(kind.value + "_total_s")
            if cap and total > cap:
                raise ValueError(f"{kind.value} 参考累计 {total:.2f}s 超上限 {cap}s")

    def build(self) -> tuple[dict, list[dict]]:
        materialized = [reference.materialize() for reference in self.references]
        self._slots = {reference.slot: item.value
                       for reference, item in zip(self.references, materialized)}
        self._records = [item.record for item in materialized]
        policy = VIDEO_MODE_POLICIES.get(self.mode)
        if policy is not None:
            policy.validate(self)
        return self._slots, self._records

    _slots: dict = None
    _records: list[dict] = None
