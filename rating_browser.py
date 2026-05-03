import base64
import copy
import json
import math
import os
import logging
from typing import Any, Dict, List

try:
    from .browser_fonts import inject_browser_fonts
except ImportError:
    from browser_fonts import inject_browser_fonts

logger = logging.getLogger(__name__)


def _get_frontend_render_url() -> str:
    return os.getenv("NAGEKI_RATING_RENDER_URL", "http://localhost:4200/render/ongeki-rating")


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
    # output_path is kept for API compatibility with the Pillow fallback path.
    image_bytes = await generate_rating_browser_image_bytes(profile, categories, api_client)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"


async def generate_rating_browser_image_bytes(
    profile: Dict[str, Any],
    categories: List[Dict[str, Any]],
    api_client,
) -> bytes:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "当前环境未安装 playwright，无法使用浏览器截图。"
            "请运行: pip install playwright && python -m playwright install chromium"
        ) from exc

    browser = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page(
                viewport={"width": 1600, "height": 2400},
                device_scale_factor=1,
            )
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
            await page.goto(render_url, wait_until="networkidle")
            await inject_browser_fonts(page)
            await page.wait_for_function("window.__NAGEKI_RENDER_READY__ === true")
            render_root = page.locator(
                ".ongeki-rating-render, .rating-render, "
                "[data-nageki-render='ongeki-rating'], [data-render='ongeki-rating']"
            ).first
            await render_root.wait_for(state="visible")
            box = await render_root.bounding_box()
            if not box:
                raise RuntimeError("前端 Rating 页截图区域不可用。")
            clip = {
                "x": math.floor(box["x"]),
                "y": math.floor(box["y"]),
                "width": math.ceil(box["width"]),
                "height": math.ceil(box["height"]),
            }
            return await page.screenshot(
                type="png",
                omit_background=True,
                clip=clip,
            )
    except Exception as exc:
        raise RuntimeError(
            "前端 Rating 页截图失败，请确认 Playwright Chromium 已安装，"
            "并且 NAGEKI_RATING_RENDER_URL 指向可访问的前端 /render/ongeki-rating 页面。"
        ) from exc
    finally:
        if browser:
            await browser.close()
