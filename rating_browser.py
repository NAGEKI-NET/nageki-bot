import base64
import copy
import json
import math
import os
import logging
import time
from typing import Any, Dict, List

try:
    from .browser_fonts import (
        auto_fit_viewport,
        compute_content_bounding_box,
        register_browser_fonts,
        tighten_render_layout,
        wait_for_browser_fonts,
    )
    from .browser_pool import shared_browser_page
    from .image_optimizer import compress_screenshot_bytes
    from .playwright_runtime import get_browser_timeout_ms
except ImportError:
    from browser_fonts import (
        auto_fit_viewport,
        compute_content_bounding_box,
        register_browser_fonts,
        tighten_render_layout,
        wait_for_browser_fonts,
    )
    from browser_pool import shared_browser_page
    from image_optimizer import compress_screenshot_bytes
    from playwright_runtime import get_browser_timeout_ms

logger = logging.getLogger(__name__)


def _get_frontend_render_url() -> str:
    return os.getenv("NAGEKI_RATING_RENDER_URL", "https://next.nageki-net.com/render/ongeki-rating")


def _get_category_render_meta(title: str, index: int) -> Dict[str, str]:
    normalized = (title or "").upper()
    if "PSCORE" in normalized:
        return {"icon": "diamond", "color": "purple"}
    if "NEW" in normalized:
        return {"icon": "new_releases", "color": "green"}
    if "B50" in normalized or index == 0:
        return {"icon": "star", "color": "blue"}
    fallback = [
        {"icon": "star", "color": "blue"},
        {"icon": "new_releases", "color": "green"},
        {"icon": "diamond", "color": "purple"},
    ]
    return fallback[index] if index < len(fallback) else {"icon": "star", "color": "blue"}


def _prepare_categories_for_frontend(categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    frontend_categories = copy.deepcopy(categories)

    for index, category in enumerate(frontend_categories):
        default_title = ["B50", "NEW10", "PSCORE 50"][index] if index < 3 else f"RATING {index + 1}"
        title = category.get("title") or default_title
        category["title"] = title
        category.setdefault("description", title)

        meta = _get_category_render_meta(title, index)
        category.setdefault("icon", meta["icon"])
        category.setdefault("color", meta["color"])

        for item in category.get("items", []):
            if "isAllBreak" in item:
                item["allBreak"] = item.pop("isAllBreak")
            if "isFullBell" in item:
                item["fullBell"] = item.pop("isFullBell")

    return frontend_categories


async def generate_rating_browser_image(
    output_path: str,
    profile: Dict[str, Any],
    categories: List[Dict[str, Any]],
    api_client,
) -> str:
    # output_path is kept for API compatibility; browser rendering returns base64 directly.
    image_bytes = await generate_rating_browser_image_bytes(profile, categories, api_client)
    image_bytes = compress_screenshot_bytes(image_bytes)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"


async def generate_rating_browser_image_bytes(
    profile: Dict[str, Any],
    categories: List[Dict[str, Any]],
    api_client,
) -> bytes:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "当前环境未安装 playwright，无法使用浏览器截图。"
            "请运行: pip install playwright && python -m playwright install chromium"
        ) from exc

    browser_timeout_ms = get_browser_timeout_ms()
    try:
        async with shared_browser_page(viewport={"width": 1600, "height": 2400}) as page:
            init_payload = json.dumps(
                {
                    "profile": profile,
                    "categories": _prepare_categories_for_frontend(categories),
                    "cdnBaseUrl": api_client.cdn_base_url,
                    "theme": getattr(api_client, "profile_render_theme", "dark"),
                    "language": getattr(api_client, "profile_render_language", "zh"),
                },
                ensure_ascii=False,
            )
            await register_browser_fonts(page)
            await page.add_init_script(
                """
                (() => {
                  const payload = __NAGEKI_INIT_PAYLOAD__;
                  const profile = payload.profile;
                  const categories = payload.categories;
                  window.__NAGEKI_PROFILE__ = profile;
                  window.__NAGEKI_RATING_CATEGORIES__ = categories;
                  window.__NAGEKI_CURRENT_USER__ = {
                    id: 'bot-render',
                    username: profile.userName || 'bot-render',
                    name: profile.userName || 'bot-render',
                    email: '',
                    bio: profile.profileContent || '',
                    joinDate: new Date().toISOString()
                  };
                  localStorage.setItem('cdnHost', payload.cdnBaseUrl);
                  localStorage.setItem('theme-auto-mode', 'false');
                  localStorage.setItem('theme-preference', payload.theme);
                  localStorage.setItem('selectedLanguage', payload.language);
                  window.__NAGEKI_RENDER_THEME__ = payload.theme;
                  window.__NAGEKI_RENDER_LANGUAGE__ = payload.language;
                  window.__NAGEKI_RENDER_TRANSPARENT__ = true;
                })();
                """.replace("__NAGEKI_INIT_PAYLOAD__", init_payload)
            )
            render_url = getattr(api_client, "rating_render_url", None) or _get_frontend_render_url()

            phases = []
            def _mark(name, t0):
                dt = time.monotonic() - t0
                phases.append((name, dt))
                return time.monotonic()

            t0 = time.monotonic()
            await page.goto(render_url, wait_until="domcontentloaded", timeout=browser_timeout_ms)
            t0 = _mark("goto(domcontentloaded)", t0)
            await wait_for_browser_fonts(page)
            t0 = _mark("fonts.ready", t0)
            await page.wait_for_function("window.__NAGEKI_RENDER_READY__ === true", timeout=browser_timeout_ms)
            t0 = _mark("__NAGEKI_RENDER_READY__", t0)
            render_selector = (
                ".ongeki-rating-render, .rating-render, "
                "[data-nageki-render='ongeki-rating'], [data-render='ongeki-rating']"
            )
            render_root = page.locator(render_selector).first
            await render_root.wait_for(state="visible", timeout=browser_timeout_ms)
            t0 = _mark("render_root.visible", t0)
            await tighten_render_layout(page)
            box = await auto_fit_viewport(page, render_selector)
            if not box:
                box = await compute_content_bounding_box(page, render_selector)
            if not box:
                box = await render_root.bounding_box()
            if not box:
                raise RuntimeError("前端 Rating 页截图区域不可用。")
            t0 = _mark("tighten+fit", t0)
            clip = {
                "x": math.floor(box["x"]),
                "y": math.floor(box["y"]),
                "width": math.ceil(box["width"]),
                "height": math.ceil(box["height"]),
            }
            png_bytes = await page.screenshot(
                type="png",
                omit_background=True,
                timeout=browser_timeout_ms,
                clip=clip,
            )
            t0 = _mark("screenshot", t0)
            logger.info(
                "[Rating 截图耗时] %s",
                ", ".join(f"{n}={d*1000:.0f}ms" for n, d in phases),
            )
            return png_bytes
    except Exception as exc:
        raise RuntimeError(
            "前端 Rating 页截图失败，请确认 Playwright Chromium 已安装，"
            "并且 NAGEKI_RATING_RENDER_URL 指向可访问的前端 /render/ongeki-rating 页面。"
        ) from exc
