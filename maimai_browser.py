import base64
import copy
import json
import logging
import os
from typing import Any, Dict, List, Optional

try:
    from .browser_fonts import register_browser_fonts, wait_for_browser_fonts
    from .playwright_runtime import get_browser_timeout_ms, launch_playwright_chromium
except ImportError:
    from browser_fonts import register_browser_fonts, wait_for_browser_fonts
    from playwright_runtime import get_browser_timeout_ms, launch_playwright_chromium

logger = logging.getLogger(__name__)


def _get_maimai_profile_render_url() -> str:
    return os.getenv("NAGEKI_MAIMAI_PROFILE_RENDER_URL", "https://next.nageki-net.com/render/maimai2-profile")


def _get_maimai_rating_render_url() -> str:
    return os.getenv("NAGEKI_MAIMAI_RATING_RENDER_URL", "https://next.nageki-net.com/render/maimai2-rating")


def _build_current_user(current_user: Optional[Dict[str, Any]], profile: Dict[str, Any]) -> Dict[str, Any]:
    base = copy.deepcopy(current_user) if isinstance(current_user, dict) else {}
    base.setdefault("id", "bot-render")
    base.setdefault("username", profile.get("userName") or "bot-render")
    base.setdefault("name", profile.get("userName") or "bot-render")
    base.setdefault("email", "")
    base.setdefault("bio", profile.get("profileContent") or "")
    base.setdefault("joinDate", "")
    return base


async def generate_maimai_profile_browser_image(
    output_path: str,
    profile: Dict[str, Any],
    api_client,
    current_user: Optional[Dict[str, Any]] = None,
) -> str:
    image_bytes = await _generate_maimai_profile_browser_image_bytes(profile, api_client, current_user)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"


async def _generate_maimai_profile_browser_image_bytes(
    profile: Dict[str, Any],
    api_client,
    current_user: Optional[Dict[str, Any]] = None,
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
            browser_timeout_ms = get_browser_timeout_ms()
            browser = await launch_playwright_chromium(playwright)
            page = await browser.new_page(
                viewport={"width": 1600, "height": 1280},
                device_scale_factor=1,
            )
            page.set_default_timeout(browser_timeout_ms)
            page.set_default_navigation_timeout(browser_timeout_ms)
            init_payload = json.dumps(
                {
                    "profile": profile,
                    "currentUser": _build_current_user(current_user, profile),
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
                  window.__NAGEKI_PROFILE__ = payload.profile;
                  window.__NAGEKI_CURRENT_USER__ = payload.currentUser;
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
            render_url = getattr(api_client, "maimai_profile_render_url", None) or _get_maimai_profile_render_url()
            await page.goto(render_url, wait_until="networkidle", timeout=browser_timeout_ms)
            await wait_for_browser_fonts(page)
            await page.wait_for_function("window.__NAGEKI_RENDER_READY__ === true", timeout=browser_timeout_ms)
            render_root = page.locator(".maimai2-profile-render")
            await render_root.wait_for(state="visible", timeout=browser_timeout_ms)
            box = await render_root.bounding_box()
            if not box:
                raise RuntimeError("前端 Maimai Profile 截图区域不可用。")
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
            "前端 Maimai Profile 页截图失败，请确认 Playwright Chromium 已安装，"
            "并且 NAGEKI_MAIMAI_PROFILE_RENDER_URL 指向可访问的前端 /render/maimai2-profile 页面。"
        ) from exc
    finally:
        if browser:
            await browser.close()


async def generate_maimai_rating_browser_image(
    output_path: str,
    profile: Dict[str, Any],
    categories: List[Dict[str, Any]],
    api_client,
    current_user: Optional[Dict[str, Any]] = None,
) -> str:
    image_bytes = await _generate_maimai_rating_browser_image_bytes(profile, categories, api_client, current_user)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"


async def _generate_maimai_rating_browser_image_bytes(
    profile: Dict[str, Any],
    categories: List[Dict[str, Any]],
    api_client,
    current_user: Optional[Dict[str, Any]] = None,
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
            browser_timeout_ms = get_browser_timeout_ms()
            browser = await launch_playwright_chromium(playwright)
            page = await browser.new_page(
                viewport={"width": 1600, "height": 2600},
                device_scale_factor=1,
            )
            page.set_default_timeout(browser_timeout_ms)
            page.set_default_navigation_timeout(browser_timeout_ms)
            init_payload = json.dumps(
                {
                    "profile": profile,
                    "categories": categories,
                    "currentUser": _build_current_user(current_user, profile),
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
                  window.__NAGEKI_PROFILE__ = payload.profile;
                  window.__NAGEKI_RATING_CATEGORIES__ = payload.categories;
                  window.__NAGEKI_CURRENT_USER__ = payload.currentUser;
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
            render_url = getattr(api_client, "maimai_rating_render_url", None) or _get_maimai_rating_render_url()
            await page.goto(render_url, wait_until="networkidle", timeout=browser_timeout_ms)
            await wait_for_browser_fonts(page)
            await page.wait_for_function("window.__NAGEKI_RENDER_READY__ === true", timeout=browser_timeout_ms)
            render_root = page.locator(".maimai2-rating-render")
            await render_root.wait_for(state="visible", timeout=browser_timeout_ms)
            box = await render_root.bounding_box()
            if not box:
                raise RuntimeError("前端 Maimai Rating 截图区域不可用。")
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
            "前端 Maimai Rating 页截图失败，请确认 Playwright Chromium 已安装，"
            "并且 NAGEKI_MAIMAI_RATING_RENDER_URL 指向可访问的前端 /render/maimai2-rating 页面。"
        ) from exc
    finally:
        if browser:
            await browser.close()
