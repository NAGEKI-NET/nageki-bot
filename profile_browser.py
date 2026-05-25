import base64
import json
import os
import logging
from typing import Any, Dict

try:
    from .browser_fonts import (
        auto_fit_viewport,
        compute_content_bounding_box,
        register_browser_fonts,
        tighten_render_layout,
        wait_for_browser_fonts,
        wait_for_render_images,
    )
    from .browser_pool import shared_browser_page
    from .image_optimizer import compress_screenshot_bytes_async
    from .playwright_runtime import get_browser_timeout_ms
except ImportError:
    from browser_fonts import (
        auto_fit_viewport,
        compute_content_bounding_box,
        register_browser_fonts,
        tighten_render_layout,
        wait_for_browser_fonts,
        wait_for_render_images,
    )
    from browser_pool import shared_browser_page
    from image_optimizer import compress_screenshot_bytes_async
    from playwright_runtime import get_browser_timeout_ms

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)


def _get_frontend_render_url() -> str:
    return os.getenv("NAGEKI_PROFILE_RENDER_URL", "https://next.nageki-net.com/render/ongeki-profile")


async def generate_profile_browser_image(
    output_path: str,
    profile: Dict[str, Any],
    api_client,
) -> str:
    # output_path is kept for API compatibility; browser rendering returns base64 directly.
    image_bytes = await generate_profile_browser_image_bytes(profile, api_client)
    image_bytes = await compress_screenshot_bytes_async(image_bytes)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"


async def generate_profile_browser_image_bytes(
    profile: Dict[str, Any],
    api_client,
) -> bytes:
    try:
        import playwright.async_api  # noqa: F401  仅用于确认依赖存在
    except ImportError as exc:
        raise RuntimeError(
            "当前环境未安装 playwright，无法使用浏览器截图。"
            "请运行: pip install playwright && python -m playwright install chromium"
        ) from exc

    browser_timeout_ms = get_browser_timeout_ms()
    try:
        async with shared_browser_page(viewport={"width": 1600, "height": 1280}) as page:
            init_payload = json.dumps(
                {
                    "profile": profile,
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
                  window.__NAGEKI_PROFILE__ = profile;
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
            render_url = getattr(api_client, "profile_render_url", None) or _get_frontend_render_url()
            await page.goto(render_url, wait_until="domcontentloaded", timeout=browser_timeout_ms)
            await wait_for_browser_fonts(page)
            await page.wait_for_function("window.__NAGEKI_RENDER_READY__ === true", timeout=browser_timeout_ms)
            render_root = page.locator(".ongeki-profile-render")
            await render_root.wait_for(state="visible", timeout=browser_timeout_ms)
            await wait_for_render_images(page, ".ongeki-profile-render")
            await tighten_render_layout(page)
            box = await auto_fit_viewport(page, ".ongeki-profile-render")
            if not box:
                box = await compute_content_bounding_box(page, ".ongeki-profile-render")
            if not box:
                box = await render_root.bounding_box()
            if not box:
                raise RuntimeError("前端资料页截图区域不可用。")
            return await page.screenshot(
                type="png",
                omit_background=True,
                timeout=browser_timeout_ms,
                clip={
                    "x": box["x"],
                    "y": box["y"],
                    "width": box["width"],
                    "height": box["height"],
                },
            )
    except Exception as exc:
        raise RuntimeError(
            "前端资料页截图失败，请确认 Playwright Chromium 已安装，"
            "并且 NAGEKI_PROFILE_RENDER_URL 指向可访问的前端 /render/ongeki-profile 页面。"
        ) from exc
