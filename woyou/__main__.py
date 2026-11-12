"""命令行入口：启动本地服务并尝试打开浏览器。

终端只输出一个简洁的启动面板；uvicorn / httpx 的常规日志被压到 WARNING，
避免刷屏。服务在主线程运行，Ctrl+C 由 uvicorn 自己处理，退出干净。
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import __version__

# 不输出 uvicorn 的 INFO 启动日志，也不让 httpx 每次请求打一行。
# 只保留 WARNING / ERROR，且不带 ANSI 颜色。
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(levelname)s: %(message)s"},
    },
    "handlers": {
        "plain": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["plain"], "level": "WARNING", "propagate": False},
        "uvicorn.error": {"handlers": ["plain"], "level": "WARNING", "propagate": False},
        "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
        "httpx": {"handlers": ["plain"], "level": "ERROR", "propagate": False},
        "httpcore": {"handlers": ["plain"], "level": "ERROR", "propagate": False},
    },
}


def _find_port(host: str, start: int, tries: int = 20) -> int:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    for port in range(start, start + tries):
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    return start


def _preflight_data_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".woyou-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        print(
            f"\n  无法写入数据目录：{path}\n  {exc}\n"
            "  请用 --data-dir 指定一个可写目录，例如：\n"
            "    woyou --data-dir ~/woyou-data\n",
            file=sys.stderr,
            flush=True,
        )
        return False
    return True


def _run_opener(command: list[str], url: str) -> bool:
    """运行 xdg-open / gio 这类会很快返回的启动器。"""
    if not shutil.which(command[0]):
        return False
    try:
        result = subprocess.run(
            [*command, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _default_browser_registered() -> bool:
    """确认桌面环境确实注册了 http 处理器，避免 xdg-open 退回文本浏览器。"""
    if shutil.which("xdg-settings"):
        try:
            result = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    if shutil.which("gio"):
        try:
            result = subprocess.run(
                ["gio", "mime", "x-scheme-handler/http"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if "Default application" in result.stdout:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    return False


def _open_wsl(url: str) -> bool:
    """WSL 下优先用 wslview，其次 PowerShell / cmd 调 Windows 默认浏览器。"""
    candidates: list[list[str]] = [
        ["wslview", url],
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Start-Process '{url}'",
        ],
        ["cmd.exe", "/c", "start", "", url],
    ]
    for command in candidates:
        if not shutil.which(command[0]):
            continue
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return True
    return False


def _open_browser(url: str) -> bool:
    """只尝试 GUI 浏览器；绝不退回 lynx/w3m 这类文本浏览器。"""
    if sys.platform == "darwin":
        try:
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            return False

    if os.name == "nt":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except OSError:
            return False

    if "microsoft" in platform.release().lower():
        if _open_wsl(url):
            return True

    if _default_browser_registered():
        if _run_opener(["xdg-open"], url):
            return True
        if _run_opener(["gio", "open"], url):
            return True

    gui_browsers = (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "microsoft-edge-stable",
        "brave-browser",
        "firefox",
        "firefox-esr",
        "epiphany",
        "falkon",
        "qutebrowser",
    )
    for name in gui_browsers:
        executable = shutil.which(name)
        if not executable:
            continue
        try:
            subprocess.Popen(
                [executable, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            continue
    return False


def _banner(url: str) -> None:
    unicode_ok = "utf" in (sys.stdout.encoding or "").lower()
    if unicode_ok:
        title = f"卧游 Woyou  v{__version__}"
        hint = "按 Ctrl+C 停止"
        manual = "若浏览器未自动打开，请按住 Ctrl 并点击上面的地址，或复制到浏览器。"
    else:
        title = f"Woyou v{__version__}"
        hint = "Press Ctrl+C to stop"
        manual = "If the browser did not open, Ctrl+click the URL above or copy it."

    lines = [
        "",
        "  " + "=" * 56,
        f"  {title}",
        f"  {url}",
        f"  {hint}",
        f"  {manual}",
        "  " + "=" * 56,
    ]
    print("\n".join(lines), flush=True)


def _announce_when_ready(server, url: str, no_browser: bool) -> None:
    for _ in range(1200):
        if server.started:
            break
        if server.should_exit:
            return
        time.sleep(0.05)
    if not server.started:
        return
    if not no_browser:
        _open_browser(url)
    _banner(url)


def _announce_reload(url: str, no_browser: bool) -> None:
    # reload 模式下拿不到 Server 对象，等端口起来再提示。
    for _ in range(120):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", int(url.rsplit(":", 1)[-1]))) == 0:
                break
        time.sleep(0.1)
    if not no_browser:
        _open_browser(url)
    _banner(url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="woyou",
        description="卧游 Woyou — 本地个人地理探索台",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765, help="起始端口（默认 8765）")
    parser.add_argument("--data-dir", default=None, help="数据目录（缓存与设置）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--reload", action="store_true", help="开发模式：代码变更自动重载")
    parser.add_argument("--version", action="version", version=f"卧游 Woyou {__version__}")
    args = parser.parse_args(argv)

    port = _find_port(args.host, args.port)
    os.environ["WOYOU_HOST"] = args.host
    os.environ["WOYOU_PORT"] = str(port)
    if args.data_dir:
        os.environ["WOYOU_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    if args.no_browser:
        os.environ["WOYOU_OPEN_BROWSER"] = "0"

    from .config import Settings

    settings = Settings()
    if not _preflight_data_dir(settings.data_dir):
        return 1

    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{display_host}:{port}"

    import uvicorn

    if args.reload:
        threading.Thread(
            target=_announce_reload, args=(url, args.no_browser), daemon=True
        ).start()
        uvicorn.run(
            "woyou.app:app",
            host=args.host,
            port=port,
            reload=True,
            log_level="warning",
            log_config=LOG_CONFIG,
            access_log=False,
        )
        print("\n  已停止。\n", flush=True)
        return 0

    from .app import create_app

    application = create_app(settings)
    config = uvicorn.Config(
        application,
        host=args.host,
        port=port,
        log_level="warning",
        log_config=LOG_CONFIG,
        access_log=False,
    )
    server = uvicorn.Server(config)
    threading.Thread(
        target=_announce_when_ready,
        args=(server, url, args.no_browser),
        daemon=True,
    ).start()

    try:
        # 主线程运行，uvicorn 才能正确接管 SIGINT，Ctrl+C 退出干净。
        server.run()
    except KeyboardInterrupt:
        server.should_exit = True

    if not server.started:
        print("\n  启动失败，请查看上面的错误信息。\n", file=sys.stderr, flush=True)
        return 1

    print("\n  已停止。\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
