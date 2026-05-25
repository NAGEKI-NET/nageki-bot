import base64
import copy
import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

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

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)


def _get_maimai_profile_render_url() -> str:
    return os.getenv("NAGEKI_MAIMAI_PROFILE_RENDER_URL", "https://next.nageki-net.com/render/maimai2-profile")


def _get_maimai_rating_render_url() -> str:
    return os.getenv("NAGEKI_MAIMAI_RATING_RENDER_URL", "https://next.nageki-net.com/render/maimai2-rating")


_LANG_VARIANT_MAP = {
    "zh": ("zh", "zh-CN", "zh-Hans", "zh_CN"),
    "en": ("en", "en-US"),
    "ja": ("ja", "ja-JP"),
}


def _append_lang_query(url: str, lang: str) -> str:
    """在 URL 末尾追加 lang 查询参数（保留已有参数，已有同名则覆盖）。"""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["lang"] = lang
    return urlunparse(parsed._replace(query=urlencode(query)))


def _build_i18n_init_snippet(lang: str) -> str:
    """生成在导航前注入的 i18n 设置代码，覆盖多种常见前端读取方式。"""
    variants = _LANG_VARIANT_MAP.get(lang, (lang,))
    primary = variants[0]
    payload = {
        "primary": primary,
        "variants": list(variants),
    }
    return (
        "(() => {"
        f"  const payload = {json.dumps(payload)};"
        "  const primary = payload.primary;"
        "  const variants = payload.variants;"
        "  const keys = ['selectedLanguage','language','lang','locale',"
        "                'i18nextLng','vue-i18n-lang','userLanguage',"
        "                'maimai-language','maimai-locale','app-language'];"
        "  try { for (const k of keys) localStorage.setItem(k, primary); } catch (e) {}"
        "  try { document.cookie = 'lang=' + primary + '; path=/'; "
        "        document.cookie = 'locale=' + primary + '; path=/'; } catch (e) {}"
        "  window.__NAGEKI_LANG__ = primary;"
        "  window.__NAGEKI_LANG_VARIANTS__ = variants;"
        "  try { Object.defineProperty(navigator, 'language',"
        "    { configurable: true, get: () => primary }); } catch (e) {}"
        "  try { Object.defineProperty(navigator, 'languages',"
        "    { configurable: true, get: () => variants }); } catch (e) {}"
        "})();"
    )


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
    image_bytes = compress_screenshot_bytes(image_bytes)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"


async def _generate_maimai_profile_browser_image_bytes(
    profile: Dict[str, Any],
    api_client,
    current_user: Optional[Dict[str, Any]] = None,
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
        async with shared_browser_page(viewport={"width": 1600, "height": 1280}) as page:
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
            lang = getattr(api_client, "profile_render_language", "zh")
            await register_browser_fonts(page)
            await page.add_init_script(_build_i18n_init_snippet(lang))
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
            render_url = _append_lang_query(render_url, lang)
            await page.goto(render_url, wait_until="domcontentloaded", timeout=browser_timeout_ms)
            await wait_for_browser_fonts(page)
            await page.wait_for_function("window.__NAGEKI_RENDER_READY__ === true", timeout=browser_timeout_ms)
            render_root = page.locator(".maimai2-profile-render")
            await render_root.wait_for(state="visible", timeout=browser_timeout_ms)
            await tighten_render_layout(page)
            box = await auto_fit_viewport(page, ".maimai2-profile-render")
            if not box:
                box = await compute_content_bounding_box(page, ".maimai2-profile-render")
            if not box:
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


async def generate_maimai_rating_browser_image(
    output_path: str,
    profile: Dict[str, Any],
    categories: List[Dict[str, Any]],
    api_client,
    current_user: Optional[Dict[str, Any]] = None,
) -> str:
    image_bytes = await _generate_maimai_rating_browser_image_bytes(profile, categories, api_client, current_user)
    image_bytes = compress_screenshot_bytes(image_bytes)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"


async def _generate_maimai_rating_browser_image_bytes(
    profile: Dict[str, Any],
    categories: List[Dict[str, Any]],
    api_client,
    current_user: Optional[Dict[str, Any]] = None,
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
        async with shared_browser_page(viewport={"width": 1600, "height": 2600}) as page:
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
            lang = getattr(api_client, "profile_render_language", "zh")
            await register_browser_fonts(page)
            await page.add_init_script(_build_i18n_init_snippet(lang))
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
            render_url = _append_lang_query(render_url, lang)
            await page.goto(render_url, wait_until="domcontentloaded", timeout=browser_timeout_ms)
            await wait_for_browser_fonts(page)
            await page.wait_for_function("window.__NAGEKI_RENDER_READY__ === true", timeout=browser_timeout_ms)
            render_root = page.locator(".maimai2-rating-render")
            await render_root.wait_for(state="visible", timeout=browser_timeout_ms)
            await tighten_render_layout(page)
            box = await auto_fit_viewport(page, ".maimai2-rating-render")
            if not box:
                box = await compute_content_bounding_box(page, ".maimai2-rating-render")
            if not box:
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
