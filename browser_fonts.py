import base64
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def _bundled_fonts_enabled() -> bool:
    """是否往页面注入插件自带字体（约 26MB base64）。

    默认 false：依赖宿主机/容器内系统字体（fc-list 能看到的）。
    若部署环境确实没有 CJK 字体，把 NAGEKI_USE_BUNDLED_FONTS=true 打开。
    """
    value = os.getenv("NAGEKI_USE_BUNDLED_FONTS", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


_FONT_STACK = (
    "'Nageki Segoe UI', 'Nageki CJK', 'Nageki MS Gothic', "
    "'Segoe UI', 'BIZ UDGothic', 'MS Gothic', sans-serif"
)


def _font_data_url(path: Path) -> Optional[str]:
    if not path.exists():
        logger.warning("[浏览器截图] 字体文件不存在: %s", path)
        return None

    mime = "font/ttc" if path.suffix.lower() == ".ttc" else "font/ttf"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _font_face(family: str, filename: str, weight: int) -> Optional[str]:
    font_path = Path(__file__).resolve().parent / "assets" / "fonts" / filename
    src = _font_data_url(font_path)
    if not src:
        return None

    font_format = "truetype-collection" if font_path.suffix.lower() == ".ttc" else "truetype"
    return (
        "@font-face {"
        f"font-family: '{family}';"
        f"src: url('{src}') format('{font_format}');"
        f"font-weight: {weight};"
        "font-style: normal;"
        "font-display: block;"
        "}"
    )


@lru_cache(maxsize=1)
def get_browser_font_css() -> str:
    faces: List[str] = []
    for family, filename, weight in (
        ("Nageki Segoe UI", "segoeui.ttf", 400),
        ("Nageki Segoe UI", "segoeuib.ttf", 700),
        ("Nageki CJK", "BIZ-UDGOTHICR.TTC", 400),
        ("Nageki CJK", "BIZ-UDGothicB.ttc", 700),
        ("Nageki MS Gothic", "msgothic.ttc", 400),
    ):
        face = _font_face(family, filename, weight)
        if face:
            faces.append(face)

    if not faces:
        return ""

    return "\n".join(
        [
            *faces,
            f"""
:root,
html,
body,
button,
input,
textarea,
select,
.ongeki-profile-render,
.ongeki-profile-render :not(.material-icons):not(.material-symbols-outlined):not(.mat-icon),
.ongeki-rating-render,
.ongeki-rating-render :not(.material-icons):not(.material-symbols-outlined):not(.mat-icon),
.rating-render,
.rating-render :not(.material-icons):not(.material-symbols-outlined):not(.mat-icon) {{
  font-family: {_FONT_STACK} !important;
}}
""",
        ]
    )


async def register_browser_fonts(page) -> None:
    """在导航前通过 init script 注入 @font-face，让首屏渲染就能用上内置字体。

    默认跳过，依赖系统字体；通过 NAGEKI_USE_BUNDLED_FONTS=true 启用注入。
    """
    if not _bundled_fonts_enabled():
        return
    css = get_browser_font_css()
    if not css:
        logger.warning("[浏览器截图] 未加载到内置字体，继续使用系统字体。")
        return

    script = (
        "(() => {"
        f"  const css = {json.dumps(css)};"
        "  const apply = () => {"
        "    if (document.querySelector('style[data-nageki-fonts]')) return;"
        "    const style = document.createElement('style');"
        "    style.setAttribute('data-nageki-fonts', '1');"
        "    style.textContent = css;"
        "    (document.head || document.documentElement).appendChild(style);"
        "  };"
        "  if (document.documentElement) {"
        "    apply();"
        "  } else {"
        "    new MutationObserver((_, obs) => {"
        "      if (document.documentElement) { apply(); obs.disconnect(); }"
        "    }).observe(document, { childList: true, subtree: true });"
        "  }"
        "})();"
    )
    await page.add_init_script(script)


async def wait_for_browser_fonts(page) -> None:
    """导航后等待 @font-face 全部加载完成，避免文字以回退字体测量/绘制。"""
    try:
        await page.evaluate(
            """
            async () => {
              if (document.fonts && document.fonts.ready) {
                await document.fonts.ready;
              }
            }
            """
        )
    except Exception as exc:
        logger.debug("[浏览器截图] 等待字体就绪失败，忽略: %s", exc)


async def inject_browser_fonts(page) -> None:
    """向后兼容：等价于 register + wait，但用于已经 goto 完成的场景。"""
    if not _bundled_fonts_enabled():
        return
    css = get_browser_font_css()
    if not css:
        logger.warning("[浏览器截图] 未加载到内置字体，继续使用系统字体。")
        return

    await page.add_style_tag(content=css)
    await wait_for_browser_fonts(page)


_LAYOUT_RESET_CSS = """
html, body {
  margin: 0 !important;
  padding: 0 !important;
  background: transparent !important;
  min-height: 0 !important;
  height: auto !important;
}
.ongeki-profile-render,
.ongeki-rating-render,
.rating-render,
.maimai2-profile-render,
.maimai2-rating-render,
[data-nageki-render],
[data-render] {
  min-height: 0 !important;
  height: auto !important;
  max-height: none !important;
  margin: 0 !important;
  padding: 0 !important;
  background: transparent !important;
}
"""


async def tighten_render_layout(page) -> None:
    """收紧渲染容器尺寸，使 bounding_box 等于实际内容，而非 viewport。

    需要在 wait_for_function(__NAGEKI_RENDER_READY__) 之后、bounding_box 之前调用。
    """
    try:
        await page.add_style_tag(content=_LAYOUT_RESET_CSS)
        # 触发一次 reflow，确保下一次 bounding_box 拿到新尺寸
        await page.evaluate("() => void document.body.offsetHeight")
    except Exception as exc:
        logger.debug("[浏览器截图] 收紧渲染容器尺寸失败，忽略: %s", exc)


async def auto_fit_viewport(page, selector: str, padding: int = 8):
    """根据真实内容尺寸把 viewport 拉大（不缩小），避免内容超出 viewport 被截掉。

    返回最终用于 clip 的 bounding box；调用方在 tighten_render_layout 之后调用。
    """
    box = await compute_content_bounding_box(page, selector)
    if not box:
        return None
    current = page.viewport_size
    if not current:
        return box
    target_w = max(int(box["x"] + box["width"]) + padding, current["width"])
    target_h = max(int(box["y"] + box["height"]) + padding, current["height"])
    if target_w == current["width"] and target_h == current["height"]:
        return box
    try:
        await page.set_viewport_size({"width": target_w, "height": target_h})
        await page.evaluate("() => void document.body.offsetHeight")
    except Exception as exc:
        logger.debug("[浏览器截图] 调整 viewport 失败，忽略: %s", exc)
        return box
    return await compute_content_bounding_box(page, selector) or box


async def compute_content_bounding_box(page, selector: str):
    """以 selector 命中的元素为根，扫描其全部可见子节点的外接矩形作为最终裁剪框。

    用于 selector 自身被设了 min-height 或 padding，导致 bounding_box 包含大片空白时。
    """
    return await page.evaluate(
        """
        (selector) => {
          const root = document.querySelector(selector);
          if (!root) return null;
          let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
          const nodes = [root, ...root.querySelectorAll('*')];
          for (const el of nodes) {
            const cs = getComputedStyle(el);
            if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue;
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            if (r.left < minX) minX = r.left;
            if (r.top < minY) minY = r.top;
            if (r.right > maxX) maxX = r.right;
            if (r.bottom > maxY) maxY = r.bottom;
          }
          if (!isFinite(minX)) return null;
          return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
        }
        """,
        selector,
    )
