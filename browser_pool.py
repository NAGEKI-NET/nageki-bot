"""轻量化的共享 Playwright Chromium 浏览器池（面向低配机器）。

策略：
- 单例 Browser，懒加载，一旦起来就常驻；插件 terminate 时统一关闭。
- 全局信号量串行化截图，避免在 2 核机上并发触发 OOM/卡死。
- 启动 Chromium 时附带一组精简参数（关 GPU/扩展/沙箱/site-isolation 等），
  尽可能压低常驻内存与上下文切换开销。

可通过环境变量调节：
- ``NAGEKI_BROWSER_CONCURRENCY``：同时进行的截图数量上限，默认 1。
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Optional

try:
    from .playwright_runtime import get_browser_timeout_ms, launch_playwright_chromium
except ImportError:
    from playwright_runtime import get_browser_timeout_ms, launch_playwright_chromium

logger = logging.getLogger(__name__)


_lock = asyncio.Lock()
_playwright_ctx = None  # async_playwright() 实例
_browser = None  # 共享 Browser

_semaphore: Optional[asyncio.Semaphore] = None


def _concurrency_limit() -> int:
    try:
        return max(1, int(os.getenv("NAGEKI_BROWSER_CONCURRENCY", "1")))
    except ValueError:
        return 1


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_concurrency_limit())
    return _semaphore


# 精简启动参数，2 核机友好：少进程、少后台活动、关 GPU。
_LEAN_CHROMIUM_ARGS = (
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-features=IsolateOrigins,site-per-process,Translate,BackForwardCache,AcceptCHFrame",
    "--disable-blink-features=AutomationControlled",
    "--no-zygote",
    "--mute-audio",
    "--hide-scrollbars",
)


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
            _browser = await launch_playwright_chromium(
                _playwright_ctx,
                args=list(_LEAN_CHROMIUM_ARGS),
                chromium_sandbox=False,
            )
        except Exception:
            try:
                if _playwright_ctx is not None:
                    await _playwright_ctx.stop()
            except Exception:
                pass
            _playwright_ctx = None
            raise

        logger.info("[浏览器截图] 共享 Chromium 已就绪（精简模式，常驻）。")
        return _browser


@asynccontextmanager
async def shared_browser_page(viewport: Dict[str, int], device_scale_factor: int = 1):
    """从共享 Browser 取一个新 Page；并发由信号量串行，Browser 常驻不关。

    使用方法：

        async with shared_browser_page(viewport={"width": 1600, "height": 1280}) as page:
            ...
    """
    semaphore = _get_semaphore()
    async with semaphore:
        page = None
        try:
            browser = await _ensure_browser()
            page = await browser.new_page(
                viewport=viewport,
                device_scale_factor=device_scale_factor,
            )
            timeout_ms = get_browser_timeout_ms()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
            yield page
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception as exc:
                    logger.debug("[浏览器截图] 关闭 page 失败，忽略: %s", exc)


async def shutdown() -> None:
    """关闭共享 Browser + Playwright 子进程；仅在插件 terminate 时调用。"""
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
        logger.info("[浏览器截图] 共享 Chromium 已释放。")
