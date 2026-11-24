from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.lib import env

API_BASE = "https://www.autodl.art"
API_PREFIX = "/api/v1/adl_dev/dev/instance/pro"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
UUID_RE = re.compile(r"^pro-[A-Za-z0-9][A-Za-z0-9-]{2,63}$")
STOPPED_STATES = {"stopped", "shutdown", "shutoff", "off"}
STARTING_STATES = {"starting", "provisioning", "initializing", "booting", "creating"}
STOPPING_STATES = {"stopping", "shutting_down"}
RETRYABLE_HTTP_STATUSES = {408, 409, 425, 429}
TERMINAL_HTTP_STATUSES = {400, 401, 403, 404, 422}
UNCERTAIN_RETRY_STABLE_READS = 2
UNCERTAIN_RETRY_MIN_DELAY_S = 30


class AutoDLError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False,
                 outcome_unknown: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):


    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        old_origin = (old.scheme, old.hostname,
                      old.port or (443 if old.scheme == "https" else 80))
        new_origin = (new.scheme, new.hostname,
                      new.port or (443 if new.scheme == "https" else 80))
        if new.scheme != "https" or old_origin != new_origin:
            raise AutoDLError("AutoDL 返回跨源或降级重定向，已停止以防鉴权转发")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _uuid(value: str) -> str:
    if not isinstance(value, str) or not UUID_RE.fullmatch(value):
        raise ValueError("instance_uuid 必须是文档所示 pro-... 应用实例 ID")
    return value


def _token() -> str:
    token = env.get("AUTODL_APP_API_TOKEN")
    if not token:
        raise env.ConfigError(
            "缺凭证：请设置 AUTODL_APP_API_TOKEN，也可用 --env-file 指定 .env。"
        )
    token = token.strip()
    if token.lower().startswith("bearer "):
        raise ValueError("AutoDL Authorization 应填写 Token 原文，不加 Bearer")
    return token


def _api(method: str, path: str, payload: dict | None, token: str, timeout: int = 30) -> dict:
    if urlsplit(API_BASE).scheme != "https" and not API_BASE.startswith("http://127.0.0.1"):
        raise AutoDLError("AutoDL API 只允许 HTTPS；本地回环地址仅供离线测试")
    uncertain = method == "POST" and path.endswith(("/power_on", "/power_off"))
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.build_opener(_SameOriginRedirect()).open(
                request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise AutoDLError(
            f"AutoDL HTTP {exc.code}（响应体已抑制）",
            retryable=exc.code in RETRYABLE_HTTP_STATUSES or exc.code >= 500,
            outcome_unknown=uncertain and exc.code not in TERMINAL_HTTP_STATUSES,
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise AutoDLError(
            f"AutoDL 连接失败: {reason}", retryable=True, outcome_unknown=uncertain,
        ) from None

    try:
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response too large")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON root is not an object")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise AutoDLError(
            "AutoDL 返回无效或超限 JSON（正文已抑制）",
            retryable=True, outcome_unknown=uncertain,
        ) from None
    if value.get("code") != "Success":
        message = str(value.get("msg") or "").replace(token, "<redacted>")[:300]
        terminal_auth = re.search(
            r"authorizefailed|unauthorized|forbidden|invalid.?token|authentication|"
            r"鉴权|认证|无权限|令牌", message, flags=re.I)
        raise AutoDLError(json.dumps({
            "api_code": value.get("code"), "msg": message,
            "request_id": value.get("request_id"),
        }, ensure_ascii=False), retryable=not terminal_auth)
    return value


def _status(instance_uuid: str, token: str, request_timeout: int) -> tuple[str, str | None]:



    query = urlencode({"instance_uuid": instance_uuid})
    try:
        value = _api("GET", f"{API_PREFIX}/status?{query}", None,
                     token, request_timeout)
    except AutoDLError as exc:
        if "RequestParameterIsWrong" not in str(exc):
            raise
        value = _api("GET", f"{API_PREFIX}/status", {"instance_uuid": instance_uuid},
                     token, request_timeout)
    status = value.get("data")
    if not isinstance(status, str) or not status.strip():
        raise AutoDLError("AutoDL 状态响应缺少非空 data 字符串", retryable=True)
    return status.strip().lower(), value.get("request_id")


def _deadline(timeout: int | None) -> float | None:
    return None if timeout is None else time.monotonic() + timeout


def _pause(deadline: float | None, delay: float) -> None:
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AutoDLError("等待真实目标状态超时；下次执行会先通过 status 对账")
        delay = min(delay, remaining)
    time.sleep(max(0.0, delay))


def _health_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("--health-url 必须是完整的 HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("--health-url 不得内嵌用户名或密码")
    return value


def _health_json_requirement(value: str | None) -> tuple[str, object] | None:
    if value is None:
        return None
    path, separator, raw_expected = value.partition("=")
    keys = path.split(".")
    if not separator or not all(keys):
        raise ValueError("--health-json 必须形如 running=true 或 data.ready=true")
    try:
        expected = json.loads(raw_expected)
    except json.JSONDecodeError:
        raise ValueError("--health-json 的期望值必须是 JSON 标量") from None
    if isinstance(expected, (dict, list)):
        raise ValueError("--health-json 只接受布尔、数值、字符串或 null 期望值")
    return path, expected


def _health_config(url_value: str | None, json_value: str | None):
    url = _health_url(url_value)
    requirement = _health_json_requirement(json_value)
    if requirement and not url:
        raise ValueError("--health-json 必须与 --health-url 一起使用")
    return url, requirement


def _health_once(url: str, request_timeout: int,
                 required_status: int | None = None,
                 required_json: tuple[str, object] | None = None) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "drama-healthcheck/1"})
    try:
        with urllib.request.urlopen(request, timeout=request_timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1) if required_json else response.read(1)
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise AutoDLError(f"工作流端点尚未就绪: {reason}", retryable=True) from None
    ready = status == required_status if required_status is not None else status < 500
    if not ready:
        expected = f"HTTP {required_status}" if required_status is not None else "HTTP < 500"
        raise AutoDLError(
            f"工作流端点返回 HTTP {status}，等待 {expected}", retryable=True)
    result = {"reachable": True, "http_status": status, "url": url,
              "required_http_status": required_status}
    if required_json:
        path, expected = required_json
        try:
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("response too large")
            value = json.loads(body.decode("utf-8"))
            for key in path.split("."):
                if not isinstance(value, dict):
                    raise KeyError(key)
                value = value[key]
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, KeyError):
            raise AutoDLError(
                f"工作流端点缺少可核验的 JSON 健康字段 {path}", retryable=True) from None
        if value != expected or type(value) is not type(expected):
            raise AutoDLError(
                f"工作流端点 JSON 字段 {path} 尚未达到期望值", retryable=True)
        result["required_json"] = {"path": path, "equals": expected}
        result["observed_json"] = {"path": path, "value": value}
    return result


def _wait_health(url: str, deadline: float | None, interval: int,
                 request_timeout: int, required_status: int | None = None,
                 required_json: tuple[str, object] | None = None) -> dict:
    while True:
        try:
            return _health_once(url, request_timeout, required_status, required_json)
        except AutoDLError as exc:
            if not exc.retryable:
                raise
            _pause(deadline, interval)


def cmd_list(args) -> dict:
    value = _api("POST", f"{API_PREFIX}/list", {
        "page_index": args.page_index, "page_size": args.page_size,
    }, _token(), args.request_timeout)
    data = value.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise AutoDLError("AutoDL 列表响应缺少 data.list")
    fields = ("uuid", "name", "status", "sub_status", "region_sign", "region_name",
              "gpu_spec_uuid", "req_gpu_amount", "charge_type", "start_mode")
    rows = []
    for item in data["list"]:
        if not isinstance(item, dict):
            continue
        row = {key: item.get(key) for key in fields}
        app = item.get("cg_application_info")
        if isinstance(app, dict):
            row.update(application_name=app.get("application_name"),
                       application_uuid=app.get("application_uuid"))
        rows.append(row)
    return {
        "ok": True, "action": "list", "network": True, "read_only": True,
        "instances": rows,
        "page_index": data.get("page_index", args.page_index),
        "page_size": data.get("page_size", args.page_size),
        "max_page": data.get("max_page"), "result_total": data.get("result_total"),
        "request_id": value.get("request_id"), "sensitive_response_fields_suppressed": True,
    }


def cmd_status(args) -> dict:
    instance_uuid = _uuid(args.instance_uuid)
    status, request_id = _status(instance_uuid, _token(), args.request_timeout)
    return {"ok": True, "action": "status", "network": True, "read_only": True,
            "instance_uuid": instance_uuid, "status": status, "request_id": request_id}


@dataclass(frozen=True)
class PowerSpec:
    action: str
    label: str
    target: str
    wait_target: str
    sources: frozenset
    targets: frozenset
    transitions: frozenset
    reconciled_phase: str
    transition_phase: str
    confirmation: str
    payload: dict = field(default_factory=dict)
    success_key: str | None = None
    billing: str | None = None
    health: bool = False

    @property
    def cli(self) -> str:
        return self.action.replace("_", "-")


POWER_ON = PowerSpec(
    action="power_on", label="开机", target="running",
    wait_target="until_running_and_ready",
    sources=frozenset(STOPPED_STATES), targets=frozenset({"running"}),
    transitions=frozenset(STARTING_STATES),
    reconciled_phase="stopped_reconciled", transition_phase="already_starting",
    confirmation="confirm_power_on", payload={"payload": "gpu"},
    billing="真实有卡开机会产生云主机费用。", health=True,
)
POWER_OFF = PowerSpec(
    action="power_off", label="关机", target="stopped", wait_target="until_stopped",
    sources=frozenset({"running"}), targets=frozenset(STOPPED_STATES),
    transitions=frozenset(STOPPING_STATES),
    reconciled_phase="running_reconciled", transition_phase="already_stopping",
    confirmation="confirm_power_off", success_key="stopped",
)
POWER_SPECS = (POWER_ON, POWER_OFF)


class _PowerRun:


    def __init__(self, args, spec: PowerSpec, instance_uuid: str,
                 payload: dict, health_url: str | None,
                 health_json: tuple[str, object] | None):
        self.args, self.spec = args, spec
        self.instance_uuid, self.payload, self.health_url = instance_uuid, payload, health_url
        self.health_json = health_json
        self.token = _token()
        self.deadline = _deadline(args.timeout) if args.wait else None
        self.failures = self.stable_reads = 0
        self.uncertain_post = False
        self.retry_not_before = 0.0
        policy = "single_reconciled_attempt"
        if args.wait:
            policy = spec.wait_target if args.timeout is None else "bounded_reconciled_wait"
        self.result = {
            "ok": True, "action": spec.action, "dry_run": False, "network": True,
            "instance_uuid": instance_uuid, f"{spec.action}_posted": False,
            f"{spec.action}_post_count": 0, "automatic_retry": bool(args.wait),
            "wait_policy": policy, "transient_error_count": 0, "status_reads": 0,
        }

    def sleep(self, exponent: int = 0) -> None:
        delay = min(self.args.interval * (2 ** min(exponent, 4)), 60)
        _pause(self.deadline, delay)

    def read_status(self) -> str | None:
        try:
            status, request_id = _status(
                self.instance_uuid, self.token, self.args.request_timeout)
        except AutoDLError as exc:
            if not self.args.wait or not exc.retryable:
                raise
            self.result["transient_error_count"] += 1
            self.failures += 1
            self.sleep(self.failures - 1)
            return None
        self.result.update(status=status, request_id=request_id)
        self.result["status_reads"] += 1
        self.result.setdefault("status_before", status)
        self.failures = 0
        return status

    def finish(self) -> dict:
        if self.health_url:
            health_deadline = self.deadline
            if self.args.health_timeout is not None:
                candidate = _deadline(self.args.health_timeout)
                health_deadline = (candidate if health_deadline is None
                                   else min(health_deadline, candidate))
            self.result["readiness"] = _wait_health(
                self.health_url, health_deadline, self.args.health_interval,
                self.args.request_timeout, self.args.health_http_status, self.health_json)
            self.result["ready"] = True
        if self.spec.success_key:
            self.result[self.spec.success_key] = True
        untouched = (self.result[f"{self.spec.action}_post_count"] == 0
                     and self.result["status_before"] in self.spec.targets)
        self.result["phase"] = (
            f"already_{self.spec.target}" if untouched else self.spec.target)
        return self.result

    def accepted(self, response: dict) -> None:
        self.result.update({
            "phase": f"{self.spec.action}_accepted",
            f"{self.spec.action}_posted": True,
            f"{self.spec.action}_accepted": True,
            f"last_{self.spec.action}_outcome": "accepted_not_completion",
            "request_id": response.get("request_id"),
        })
        if self.spec.billing:
            self.result["billing_notice"] = self.spec.billing
        self.uncertain_post = False
        self.stable_reads = self.failures = 0

    def post(self) -> None:
        action = self.spec.action
        self.result[f"{action}_post_count"] += 1
        self.result[f"{action}_posted"] = True
        try:
            response = _api("POST", f"{API_PREFIX}/{action}", self.payload,
                            self.token, self.args.request_timeout)
        except AutoDLError as exc:
            if not exc.retryable:
                raise
            self.result["transient_error_count"] += 1
            self.failures += 1
            self.uncertain_post = exc.outcome_unknown
            self.stable_reads = 0
            self.retry_not_before = time.monotonic() + max(
                UNCERTAIN_RETRY_MIN_DELAY_S if self.uncertain_post else 0,
                min(self.args.interval * (2 ** min(self.failures, 4)), 60),
            )
            self.result[f"last_{action}_outcome"] = (
                "unknown_reconcile_before_retry" if self.uncertain_post else "not_accepted")
        else:
            self.accepted(response)
        self.sleep()

    def can_post(self) -> bool:
        if time.monotonic() < self.retry_not_before:
            return False
        if not self.uncertain_post:
            return True
        self.stable_reads += 1
        return self.stable_reads >= UNCERTAIN_RETRY_STABLE_READS

    def single_attempt(self, status: str) -> dict:
        if status in self.spec.transitions:
            self.result["phase"] = self.spec.transition_phase
            return self.result
        if status not in self.spec.sources:
            raise AutoDLError(
                f"实例状态 {status!r} 不在可安全{self.spec.label}集合；未 POST。"
                "请稍后仅用 status 复核。"
            )
        response = _api("POST", f"{API_PREFIX}/{self.spec.action}", self.payload,
                        self.token, self.args.request_timeout)
        self.result[f"{self.spec.action}_post_count"] = 1
        self.accepted(response)
        return self.result

    def run(self) -> dict:
        while True:
            status = self.read_status()
            if status is None:
                continue
            if status in self.spec.targets:
                return self.finish()
            if not self.args.wait:
                return self.single_attempt(status)
            if status not in self.spec.sources:
                self.stable_reads = 0
                self.result["phase"] = "waiting_for_safe_state"
                self.sleep()
                continue
            self.result["phase"] = self.spec.reconciled_phase
            if self.can_post():
                self.post()
            else:
                self.sleep()


def _power(args, spec: PowerSpec) -> dict:
    instance_uuid = _uuid(args.instance_uuid)
    payload = {"instance_uuid": instance_uuid, **spec.payload}
    health_url, health_json = _health_config(
        getattr(args, "health_url", None), getattr(args, "health_json", None)
    ) if spec.health else (None, None)
    if not args.execute:
        result = {
            "ok": True, "action": spec.action, "dry_run": True, "network": False,
            f"{spec.action}_posted": False, "instance_uuid": instance_uuid,
            "request": {"method": "POST", "path": f"{API_PREFIX}/{spec.action}",
                        "payload": payload},
            "required_for_execution":
                f"--execute --{spec.confirmation.replace('_', '-')} {instance_uuid}",
        }
        if spec.billing:
            result["billing_notice"] = spec.billing + "当前未发送请求。"
        return result
    if getattr(args, spec.confirmation) != instance_uuid:
        raise ValueError(
            f"真实{spec.label}必须同时提供 --execute 和与 --instance-uuid 完全一致的 "
            f"--{spec.confirmation.replace('_', '-')}；未发送请求。"
        )
    return _PowerRun(args, spec, instance_uuid, payload, health_url, health_json).run()


def _power_from_args(args) -> dict:
    return _power(args, args.power_spec)


def cmd_power_on(args) -> dict:
    return _power(args, POWER_ON)


def cmd_power_off(args) -> dict:
    return _power(args, POWER_OFF)


def _power_namespace(args, spec: PowerSpec) -> argparse.Namespace:
    values = {
        "instance_uuid": args.instance_uuid, "execute": True, "wait": True,
        "timeout": args.power_timeout, "interval": args.interval,
        "request_timeout": args.request_timeout, spec.confirmation: args.instance_uuid,
    }
    if spec.health:
        values.update(health_url=args.health_url,
                      health_http_status=args.health_http_status,
                      health_json=getattr(args, "health_json", None),
                      health_interval=args.health_interval,
                      health_timeout=args.health_timeout)
    return argparse.Namespace(**values)


def _capture(errors: dict, key: str, function, *args):

    try:
        return function(*args)
    except BaseException as exc:
        errors[key] = str(exc)
        return None


def _terminate(process) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_child(command: list[str]) -> tuple[int | None, str | None]:
    process = None
    try:
        process = subprocess.Popen(
            command, stdout=sys.stderr, stderr=sys.stderr, shell=False)
        return process.wait(), None
    except BaseException as exc:
        error = str(exc)
        try:
            _terminate(process)
        except BaseException as termination_error:
            error += f"; termination failed: {termination_error}"
        return None, error


def cmd_run_managed(args) -> dict:

    instance_uuid = _uuid(args.instance_uuid)
    _health_config(args.health_url, getattr(args, "health_json", None))
    command = list(args.command_argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("run-managed 需要在 -- 后提供一个非空子命令")
    if not args.execute:
        return {
            "ok": True, "action": "managed_run", "dry_run": True, "network": False,
            "instance_uuid": instance_uuid, "command": command,
            "automatic_power_off_after_child_exit": True,
            "required_for_execution": "--execute --confirm-power " + instance_uuid,
        }
    if args.confirm_power != instance_uuid:
        raise ValueError(
            "受管运行必须同时提供 --execute 和与 --instance-uuid 完全一致的 "
            "--confirm-power；该值同时约束本次开机和关机。"
        )

    initial_status, initial_request_id = _status(
        instance_uuid, _token(), args.request_timeout)
    errors = {}
    power_off = None
    child_exit_code = None
    power_on = _capture(
        errors, "power_on_error", cmd_power_on, _power_namespace(args, POWER_ON))
    if "power_on_error" not in errors:
        child_exit_code, child_error = _run_child(command)
        if child_error:
            errors["child_error"] = child_error
        power_off = _capture(
            errors, "power_off_error", cmd_power_off, _power_namespace(args, POWER_OFF))
    elif initial_status in STOPPED_STATES:

        power_off = _capture(
            errors, "power_off_error", cmd_power_off, _power_namespace(args, POWER_OFF))

    off_attempted = power_off is not None or "power_off_error" in errors
    if errors:
        raise AutoDLError(json.dumps({
            "managed_run_failed": True,
            "phase": "power_on" if "power_on_error" in errors else "child_or_power_off",
            "instance_uuid": instance_uuid, "initial_status": initial_status,
            "power_on_error": errors.get("power_on_error"),
            "child_error": errors.get("child_error"), "child_exit_code": child_exit_code,
            "power_off_attempted": off_attempted,
            "power_off_error": errors.get("power_off_error"),
            "power_off_completed": bool(power_off and power_off.get("stopped")),
            "power_off_skipped_reason": (
                None if off_attempted else "instance_was_already_active_and_child_never_started"),
        }, ensure_ascii=False))
    process_exit_code = 0 if not child_exit_code else (
        child_exit_code if 1 <= child_exit_code <= 255 else 1)
    return {
        "ok": child_exit_code == 0 and bool(power_off.get("stopped")),
        "action": "managed_run", "dry_run": False, "network": True,
        "instance_uuid": instance_uuid, "initial_status": initial_status,
        "initial_status_request_id": initial_request_id, "command": command,
        "child_exit_code": child_exit_code, "process_exit_code": process_exit_code,
        "child_output_stream": "stderr", "power_on": power_on, "power_off": power_off,
        "automatic_power_off_after_child_exit": True,
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def _http_status(value: str) -> int:
    parsed = _positive_int(value)
    if not 100 <= parsed <= 599:
        raise argparse.ArgumentTypeError("HTTP 状态必须为 100-599")
    return parsed


def _add_health_arguments(parser: argparse.ArgumentParser,
                          default_status: int | None) -> None:
    parser.add_argument("--health-url", help="running 后继续等待该服务健康地址")
    parser.add_argument("--health-http-status", type=_http_status, default=default_status,
                        help="可选精确健康 HTTP 状态")
    parser.add_argument("--health-json",
                        help="可选 JSON 健康条件，如 running=true；必须与健康地址一起使用")
    parser.add_argument("--health-interval", type=_positive_int, default=5,
                        help="健康检查固定间隔秒数")
    parser.add_argument("--health-timeout", type=_positive_int, default=None,
                        help="健康等待独立上限秒数；仍受电源等待上限约束")


def _add_power_arguments(parser: argparse.ArgumentParser, spec: PowerSpec) -> None:
    parser.add_argument("--instance-uuid", required=True)
    parser.add_argument("--execute", action="store_true", help="允许真实 POST")
    parser.add_argument(f"--{spec.confirmation.replace('_', '-')}",
                        help=f"再次填写同一实例 ID 以确认{spec.label}")
    parser.add_argument("--wait", action="store_true", help=f"对账到真实 {spec.target}")
    parser.add_argument("--timeout", type=_positive_int, default=None, help="可选等待上限秒数")
    parser.add_argument("--interval", type=_positive_int, default=5, help="轮询基础间隔秒数")
    parser.add_argument("--request-timeout", type=_positive_int, default=30)
    if spec.health:
        _add_health_arguments(parser, None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoDL 应用实例与受管电源生命周期")
    parser.add_argument("--env-file")
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="只读列出应用实例")
    listing.add_argument("--page-index", type=_positive_int, default=1)
    listing.add_argument("--page-size", type=_positive_int, default=20)
    listing.add_argument("--request-timeout", type=_positive_int, default=30)
    listing.set_defaults(func=cmd_list)

    status = sub.add_parser("status", help="只读查询实例状态")
    status.add_argument("--instance-uuid", required=True)
    status.add_argument("--request-timeout", type=_positive_int, default=30)
    status.set_defaults(func=cmd_status)

    for spec in POWER_SPECS:
        power = sub.add_parser(spec.cli, help=f"安全{spec.label}；默认 dry-run")
        _add_power_arguments(power, spec)
        power.set_defaults(func=_power_from_args, power_spec=spec)

    managed = sub.add_parser("run-managed", help="自动开机、运行子命令并自动关机")
    managed.add_argument("--instance-uuid", required=True)
    managed.add_argument("--execute", action="store_true")
    managed.add_argument("--confirm-power", help="同一实例 ID，同时确认本次开机和关机")
    managed.add_argument("--power-timeout", type=_positive_int, default=None,
                         help="开机和关机各自的可选等待上限秒数")
    managed.add_argument("--interval", type=_positive_int, default=5)
    managed.add_argument("--request-timeout", type=_positive_int, default=30)
    _add_health_arguments(managed, 200)
    managed.add_argument("command_argv", nargs=argparse.REMAINDER,
                         metavar="-- <command> [args ...]")
    managed.set_defaults(func=cmd_run_managed)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "list" and not 1 <= args.page_size <= 100:
        parser.error("--page-size 必须为 1-100")
    env.set_env_file(args.env_file)
    result = args.func(args)
    env.emit(result)
    if args.command == "run-managed" and result.get("process_exit_code"):
        raise SystemExit(result["process_exit_code"])


if __name__ == "__main__":
    env.run_cli(main)
