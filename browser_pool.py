"""进程级共享的 Playwright Chromium 浏览器池。

为避免每次截图都冷启动 Chromium（约 1~2 秒），在这里维护一个单例 Browser，
所有截图函数通过 `shared_browser_page(...)` 拿到独立 Page，结束后只关 Page，
Browser 继续驻留供下次使用。

插件 terminate 时调用 `shutdown()` 释放资源。
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

try:
    from .playwright_runtime import get_browser_timeout_ms, launch_playwright_chromium
except ImportError:
    from playwright_runtime import get_browser_timeout_ms, launch_playwright_chromium

logger = logging.getLogger(__name__)


_lock = asyncio.Lock()
_playwright_ctx = None  # async_playwright() 实例
_browser = None  # 共享的 Browser


def _browser_alive() -> bool:
    return _browser is not None and _browser.is_connected()


async def _ensure_browser():
    """懒加载共享 Browser；若已断开则重建。"""
    global _playwright_ctx, _browser
    if _browser_alive():
        return _browser

    async with _lock:
        if _browser_alive():
            return _browser

        from playwright.async_api import async_playwright

        if _playwright_ctx is None:
            _playwright_ctx = await async_playwright().start()
        try:
            _browser = await launch_playwright_chromium(_playwright_ctx)
        except Exception:
            # 启动失败时清理 playwright 句柄，避免下次拿到坏状态
            try:
                if _playwright_ctx is not None:
                    await _playwright_ctx.stop()
            except Exception:
                pass
            _playwright_ctx = None
            raise

        logger.info("[浏览器截图] 共享 Chromium 已就绪。")
        return _browser


@asynccontextmanager
async def shared_browser_page(viewport: Dict[str, int], device_scale_factor: int = 1):
    """从共享 Browser 取一个新 Page，退出 with 时只关 Page。

    使用方法：

        async with shared_browser_page(viewport={"width": 1600, "height": 1280}) as page:
            ...
    """
    browser = await _ensure_browser()
    page = await browser.new_page(
        viewport=viewport,
        device_scale_factor=device_scale_factor,
    )
    timeout_ms = get_browser_timeout_ms()
    page.set_default_timeout(timeout_ms)
    page.set_default_navigation_timeout(timeout_ms)
    try:
        yield page
    finally:
        try:
            await page.close()
        except Exception as exc:
            logger.debug("[浏览器截图] 关闭 page 失败，忽略: %s", exc)


async def shutdown() -> None:
    """关闭共享 Browser + Playwright 子进程；通常由插件 terminate 调用。"""
    global _browser, _playwright_ctx
    async with _lock:
        if _browser is not None:
            try:
                await _browser.close()
            except Exception as exc:
                logger.debug("[浏览器截图] 关闭 browser 失败，忽略: %s", exc)
            _browser = None
        if _playwright_ctx is not None:
            try:
                await _playwright_ctx.stop()
            except Exception as exc:
                logger.debug("[浏览器截图] 关闭 playwright 失败，忽略: %s", exc)
            _playwright_ctx = None
