from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
from pathlib import Path
from types import ModuleType


class ProviderSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    module: str
    protocols: frozenset[str]
    display_name: str
    reference: str


_REGISTRY = {
    "autodl": ProviderSpec(
        provider_id="autodl",
        module="tools.workflow_video",
        protocols=frozenset({"comfy_workflow_v1"}),
        display_name="AutoDL",
        reference="references/video-providers/autodl.md",
    ),
}

_REQUIRED_ADAPTER_METHODS = (
    "load_config", "prompt_markers", "verify_task_inputs",
    "submit_segment", "poll_segment",
)


def registered_providers() -> list[dict]:

    return [{
        "id": spec.provider_id,
        "display_name": spec.display_name,
        "protocols": sorted(spec.protocols),
        "reference": spec.reference,
    } for spec in _REGISTRY.values()]


def _selected_id(queue: dict, config: dict) -> str:
    queue_value = queue.get("video_provider")
    config_value = config.get("video_provider")
    if not isinstance(queue_value, str) or not queue_value:
        raise ProviderSelectionError("queue 必须显式设置非空字符串 video_provider")
    if config_value is not None and not isinstance(config_value, str):
        raise ProviderSelectionError("cloud config 的 video_provider 必须是字符串 ID")
    if config_value and config_value != queue_value:
        raise ProviderSelectionError("queue 与 cloud config 选择了不同的 video_provider")
    return queue_value


def select_adapter(queue: dict, config: dict) -> ModuleType:
    provider_id = _selected_id(queue, config)
    spec = _REGISTRY.get(provider_id)
    if spec is None:
        raise ProviderSelectionError(
            f"未注册的视频 provider: {provider_id!r}；不会回退到其他后端")
    protocol = config.get("protocol")
    if not isinstance(protocol, str) or protocol not in spec.protocols:
        raise ProviderSelectionError(
            f"provider={provider_id} 要求受支持的显式 protocol；实际为 {protocol!r}")
    adapter = importlib.import_module(spec.module)
    if getattr(adapter, "PROVIDER_ID", None) != provider_id:
        raise ProviderSelectionError(f"provider={provider_id} 的适配器身份不一致")
    missing = [name for name in _REQUIRED_ADAPTER_METHODS
               if not callable(getattr(adapter, name, None))]
    if missing:
        raise ProviderSelectionError(
            f"provider={provider_id} 适配器缺少统一接口: {', '.join(missing)}")
    return adapter


def adapter_binding(adapter: ModuleType) -> dict:

    source = Path(adapter.__file__).resolve()
    return {
        "video_provider": adapter.PROVIDER_ID,
        "video_provider_adapter_version": str(adapter.ADAPTER_VERSION),
        "video_provider_adapter_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
