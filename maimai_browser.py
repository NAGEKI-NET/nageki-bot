import base64
import json
import logging
import os
from typing import Any, Dict

try:
    from .browser_fonts import inject_browser_fonts
    from .playwright_runtime import get_browser_timeout_ms, launch_playwright_chromium
except ImportError:
    from browser_fonts import inject_browser_fonts
    from playwright_runtime import get_browser_timeout_ms, launch_playwright_chromium

logger = logging.getLogger(__name__)


def _get_maimai_profile_page_url() -> str:
    return os.getenv("NAGEKI_MAIMAI_PROFILE_PAGE_URL", "https://next.nageki-net.com/net/maimai2/profile")


def _get_maimai_rating_page_url() -> str:
    return os.getenv("NAGEKI_MAIMAI_RATING_PAGE_URL", "https://next.nageki-net.com/net/maimai2/rating")


def _build_current_user(current_user: Dict[str, Any] | None, profile: Dict[str, Any]) -> Dict[str, Any]:
    base = current_user.copy() if isinstance(current_user, dict) else {}
    base.setdefault("id", "bot-render")
    base.setdefault("username", profile.get("userName") or "bot-render")
    base.setdefault("name", profile.get("userName") or "bot-render")
    base.setdefault("email", "")
    base.setdefault("bio", profile.get("profileContent") or "")
    base.setdefault("joinDate", "")
    return base


async def _screenshot_page(
    page_url: str,
    token: str,
    profile: Dict[str, Any],
    api_client,
    current_user: Dict[str, Any] | None,
    root_selector: str,
    ready_selector: str,
    viewport_height: int,
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
            logger.info("[Maimai截图] 启动浏览器，目标页面: %s", page_url)
            browser = await launch_playwright_chromium(playwright)
            page = await browser.new_page(
                viewport={"width": 1600, "height": viewport_height},
                device_scale_factor=1,
            )
            page.set_default_timeout(browser_timeout_ms)
            page.set_default_navigation_timeout(browser_timeout_ms)

            init_payload = json.dumps(
                {
                    "token": token,
                    "currentUser": _build_current_user(current_user, profile),
                    "apiHost": api_client.api_base_url,
                    "cdnHost": api_client.cdn_base_url,
                    "theme": getattr(api_client, "profile_render_theme", "dark"),
                    "language": getattr(api_client, "profile_render_language", "zh"),
                },
                ensure_ascii=False,
            )
            await page.add_init_script(
                """
                (() => {
                  const payload = __NAGEKI_INIT_PAYLOAD__;
                  localStorage.setItem('authToken', payload.token);
                  sessionStorage.setItem('authToken', payload.token);
                  localStorage.setItem('currentUser', JSON.stringify(payload.currentUser));
                  localStorage.setItem('apiHost', payload.apiHost);
                  localStorage.setItem('cdnHost', payload.cdnHost);
                  localStorage.setItem('theme-auto-mode', 'false');
                  localStorage.setItem('theme-preference', payload.theme);
                  localStorage.setItem('selectedLanguage', payload.language);
                })();
                """.replace("__NAGEKI_INIT_PAYLOAD__", init_payload)
            )

            logger.info("[Maimai截图] 打开页面: %s", page_url)
            await page.goto(page_url, wait_until="domcontentloaded", timeout=browser_timeout_ms)
            logger.info("[Maimai截图] 页面已打开，开始注入字体")
            await inject_browser_fonts(page)
            logger.info("[Maimai截图] 等待根节点: %s", root_selector)
            await page.wait_for_selector(root_selector, state="visible", timeout=browser_timeout_ms)
            logger.info("[Maimai截图] 等待内容节点: %s", ready_selector)
            await page.wait_for_selector(ready_selector, state="visible", timeout=browser_timeout_ms)
            logger.info("[Maimai截图] 页面节点已出现，等待短暂稳定")
            await page.wait_for_timeout(1500)
            root = page.locator(root_selector).first
            box = await root.bounding_box()
            if not box:
                raise RuntimeError(f"页面截图区域不可用: {root_selector}")
            logger.info("[Maimai截图] 开始截图，区域: %s", box)
            return await page.screenshot(
                type="png",
                timeout=browser_timeout_ms,
                clip={
                    "x": box["x"],
                    "y": box["y"],
                    "width": box["width"],
                    "height": box["height"],
                },
            )
    except Exception as exc:
        logger.exception("[Maimai截图] 截图失败: %s", exc)
        raise
    finally:
        if browser:
            await browser.close()


async def generate_maimai_profile_browser_image(
    output_path: str,
    profile: Dict[str, Any],
    api_client,
    token: str,
    current_user: Dict[str, Any] | None = None,
) -> str:
    image_bytes = await _screenshot_page(
        _get_maimai_profile_page_url(),
        token,
        profile,
        api_client,
        current_user,
        ".maimai2-profile-container",
        ".maimai2-profile-container mat-card",
        1600,
    )
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"


async def generate_maimai_rating_browser_image(
    output_path: str,
    profile: Dict[str, Any],
    api_client,
    token: str,
    current_user: Dict[str, Any] | None = None,
) -> str:
    image_bytes = await _screenshot_page(
        _get_maimai_rating_page_url(),
        token,
        profile,
        api_client,
        current_user,
        ".rating-container",
        ".rating-container .bg-white",
        2600,
    )
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"base64://{encoded}"
