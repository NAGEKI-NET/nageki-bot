"""轻量化的共享 Playwright Chromium 浏览器池（面向低配机器）。

策略：
- 使用 ``launch_persistent_context`` + 本地用户数据目录，让 Chromium 的 HTTP 磁盘
  缓存跨重启保留：第二次起 JS/CSS/封面图直接从本地读，免去网络往返。
- 单例 Context，懒加载，一旦起来就常驻；插件 terminate 时统一关闭。
- 全局信号量串行化截图，避免在 2 核机上并发触发 OOM/卡死。
- 启动 Chromium 时附带一组精简参数（关 GPU/扩展/沙箱/site-isolation 等），
  尽可能压低常驻内存与上下文切换开销。

可通过环境变量调节：
- ``NAGEKI_BROWSER_CONCURRENCY``：同时进行的截图数量上限，默认 1。
- ``NAGEKI_BROWSER_USER_DATA_DIR``：自定义 Chromium 用户数据目录。
  默认放在 ``<插件目录>/cache/browser_profile``。
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional

try:
    from .playwright_runtime import (
        ensure_playwright_chromium,
        get_browser_timeout_ms,
    )
except ImportError:
    from playwright_runtime import (
        ensure_playwright_chromium,
        get_browser_timeout_ms,
    )

logger = logging.getLogger(__name__)


_lock = asyncio.Lock()
_playwright_ctx = None  # async_playwright() 实例
_context = None  # 共享 BrowserContext（来自 launch_persistent_context）

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


def _user_data_dir() -> Path:
    override = os.getenv("NAGEKI_BROWSER_USER_DATA_DIR", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
    else:
        path = Path(__file__).resolve().parent / "cache" / "browser_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def _context_alive() -> bool:
    if _context is None:
        return False
    browser = _context.browser
    return browser is not None and browser.is_connected()


async def _ensure_context():
    """懒加载共享 persistent BrowserContext；若已断开则重建。"""
    global _playwright_ctx, _context
    if _context_alive():
        return _context

    async with _lock:
        if _context_alive():
            return _context

        from playwright.async_api import async_playwright

        if _playwright_ctx is None:
            _playwright_ctx = await async_playwright().start()
        await ensure_playwright_chromium(_playwright_ctx)

        try:
            _context = await _playwright_ctx.chromium.launch_persistent_context(
                user_data_dir=str(_user_data_dir()),
                args=list(_LEAN_CHROMIUM_ARGS),
                chromium_sandbox=False,
                timeout=get_browser_timeout_ms(),
            )
        except Exception:
            try:
                if _playwright_ctx is not None:
                    await _playwright_ctx.stop()
            except Exception:
                pass
            _playwright_ctx = None
            raise

        # 让 jacket 封面不进 Chromium 磁盘缓存：拦截后强行 fetch + no-store。
        await _context.route("**/jacket/**", _no_cache_jacket_route)

        logger.info(
            "[浏览器截图] 共享 Chromium 已就绪（持久化 profile=%s）。",
            _user_data_dir(),
        )
        return _context


async def _no_cache_jacket_route(route):
    """拦截 jacket 请求，绕过磁盘缓存并强制响应 no-store。"""
    try:
        response = await route.fetch()
        body = await response.body()
        headers = dict(response.headers)
        headers["cache-control"] = "no-store, max-age=0"
        headers.pop("etag", None)
        headers.pop("last-modified", None)
        headers.pop("expires", None)
        await route.fulfill(
            status=response.status,
            headers=headers,
            body=body,
        )
    except Exception as exc:
        logger.debug("[浏览器截图] jacket 拦截失败回退原请求: %s", exc)
        try:
            await route.continue_()
        except Exception:
            pass


@asynccontextmanager
async def shared_browser_page(viewport: Dict[str, int], device_scale_factor: int = 1):
    """从共享 Context 取一个新 Page；并发由信号量串行，Context 常驻不关。

    使用方法：

        async with shared_browser_page(viewport={"width": 1600, "height": 1280}) as page:
            ...
    """
    semaphore = _get_semaphore()
    async with semaphore:
        page = None
        try:
            ctx = await _ensure_context()
            page = await ctx.new_page()
            await page.set_viewport_size(viewport)
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
    """关闭共享 Context + Playwright 子进程；仅在插件 terminate 时调用。"""
    global _context, _playwright_ctx
    async with _lock:
        if _context is not None:
            try:
                await _context.close()
            except Exception as exc:
                logger.debug("[浏览器截图] 关闭 context 失败，忽略: %s", exc)
            _context = None
        if _playwright_ctx is not None:
            try:
                await _playwright_ctx.stop()
            except Exception as exc:
                logger.debug("[浏览器截图] 关闭 playwright 失败，忽略: %s", exc)
            _playwright_ctx = None
        logger.info("[浏览器截图] 共享 Chromium 已释放。")
