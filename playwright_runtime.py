import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_install_lock: Optional[asyncio.Lock] = None


def _auto_install_enabled() -> bool:
    value = os.getenv("NAGEKI_PLAYWRIGHT_AUTO_INSTALL", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _install_timeout() -> int:
    raw_value = os.getenv("NAGEKI_PLAYWRIGHT_INSTALL_TIMEOUT", "600")
    try:
        return max(30, int(raw_value))
    except ValueError:
        return 600


def _get_install_lock() -> asyncio.Lock:
    global _install_lock
    if _install_lock is None:
        _install_lock = asyncio.Lock()
    return _install_lock


def _chromium_binary_exists(playwright) -> bool:
    executable_path = getattr(playwright.chromium, "executable_path", "")
    return bool(executable_path and Path(executable_path).exists())


async def _install_chromium() -> None:
    command = [sys.executable, "-m", "playwright", "install", "chromium"]
    if os.getenv("NAGEKI_PLAYWRIGHT_INSTALL_WITH_DEPS", "").strip().lower() in {"1", "true", "yes", "on"}:
        command.insert(-1, "--with-deps")

    logger.warning("[浏览器截图] 未找到 Playwright Chromium，准备自动安装: %s", " ".join(command))
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=_install_timeout())
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise RuntimeError("自动安装 Playwright Chromium 超时，请手动运行 python -m playwright install chromium。") from exc

    if process.returncode != 0:
        output = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            "自动安装 Playwright Chromium 失败，请手动运行 python -m playwright install chromium。"
            f"安装输出: {output[-1200:]}"
        )

    logger.info("[浏览器截图] Playwright Chromium 自动安装完成。")


async def ensure_playwright_chromium(playwright) -> None:
    if _chromium_binary_exists(playwright):
        return

    if not _auto_install_enabled():
        raise RuntimeError(
            "当前环境未安装 Playwright Chromium。"
            "请运行 python -m playwright install chromium，或启用 NAGEKI_PLAYWRIGHT_AUTO_INSTALL。"
        )

    async with _get_install_lock():
        if _chromium_binary_exists(playwright):
            return
        await _install_chromium()


def _looks_like_missing_browser(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "executable doesn't exist" in message
        or "please run the following command" in message
        or "playwright install" in message
        or "browser has not been installed" in message
    )


async def launch_playwright_chromium(playwright, **kwargs):
    await ensure_playwright_chromium(playwright)

    try:
        return await playwright.chromium.launch(**kwargs)
    except Exception as exc:
        if not _auto_install_enabled() or not _looks_like_missing_browser(exc):
            raise

        async with _get_install_lock():
            await _install_chromium()
        return await playwright.chromium.launch(**kwargs)
