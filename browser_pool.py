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
import time
from collections import defaultdict
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

try:
    from astrbot.api import logger
except ImportError:
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


_LOCALE_MAP = {"zh": "zh-CN", "en": "en-US", "ja": "ja-JP"}


def _browser_locale() -> str:
    """根据 NAGEKI_PROFILE_RENDER_LANGUAGE 推断 Chromium locale。

    控制 navigator.language + Accept-Language header，让前端默认走对应语言。
    """
    raw = os.getenv("NAGEKI_BROWSER_LOCALE", "").strip()
    if raw:
        return raw
    lang = os.getenv("NAGEKI_PROFILE_RENDER_LANGUAGE", "zh").strip().lower()
    return _LOCALE_MAP.get(lang, lang or "zh-CN")


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
            locale = _browser_locale()
            _context = await _playwright_ctx.chromium.launch_persistent_context(
                user_data_dir=str(_user_data_dir()),
                args=list(_LEAN_CHROMIUM_ARGS),
                chromium_sandbox=False,
                timeout=get_browser_timeout_ms(),
                locale=locale,
                extra_http_headers={
                    "Accept-Language": f"{locale},{locale.split('-')[0]};q=0.9",
                },
            )
        except Exception:
            try:
                if _playwright_ctx is not None:
                    await _playwright_ctx.stop()
            except Exception:
                pass
            _playwright_ctx = None
            raise

        logger.info(
            "[浏览器截图] 共享 Chromium 已就绪（profile=%s, locale=%s）。",
            _user_data_dir(),
            locale,
        )
        return _context


def _debug_requests_enabled() -> bool:
    value = os.getenv("NAGEKI_BROWSER_DEBUG_REQUESTS", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _attach_request_logging(page) -> None:
    """打开后会把页面所有网络请求按 host 聚合输出，方便定位是哪类资源拖慢。

    通过 NAGEKI_BROWSER_DEBUG_REQUESTS=1 启用。
    """
    if not _debug_requests_enabled():
        return

    host_count: Dict[str, int] = defaultdict(int)
    host_time: Dict[str, float] = defaultdict(float)
    pending: Dict[str, float] = {}
    started = time.monotonic()

    def on_request(request):
        pending[request.url] = time.monotonic()

    def on_request_finished(request):
        url = request.url
        start = pending.pop(url, None)
        if start is None:
            return
        dur = time.monotonic() - start
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc or "<unknown>"
        except Exception:
            host = "<unknown>"
        host_count[host] += 1
        host_time[host] += dur

    def on_close(_):
        total = time.monotonic() - started
        if not host_count:
            return
        lines = [f"  {h}: {host_count[h]} reqs, {host_time[h]*1000:.0f} ms total" for h in sorted(host_count)]
        logger.info(
            "[浏览器截图] 网络统计(总 %.2fs):\n%s",
            total,
            "\n".join(lines),
        )

    page.on("request", on_request)
    page.on("requestfinished", on_request_finished)
    page.on("close", on_close)


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
            _attach_request_logging(page)
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
