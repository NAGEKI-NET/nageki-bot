import base64
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# 用网页 CSS 里常见的 font-family 名称去注册我们打包的字体文件，
# 这样网页自己的 font-family 声明就能命中这些字体，不需要强制覆盖。
# 一份 ttf/ttc 同时挂在多个常见别名下，覆盖中/日/英三种命名习惯。
_LATIN_FAMILIES = ("Segoe UI", "Helvetica Neue", "Arial", "Inter")
_CJK_FAMILIES = (
    "BIZ UDGothic",
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "微软雅黑",
    "PingFang SC",
    "PingFang TC",
    "Hiragino Sans GB",
    "Hiragino Sans",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Noto Sans SC",
    "Noto Sans JP",
    "Source Han Sans SC",
    "Source Han Sans",
    "Yu Gothic",
    "Yu Gothic UI",
    "Meiryo",
    "SimHei",
    "黑体",
    "SimSun",
    "宋体",
)
_MS_GOTHIC_FAMILIES = ("MS Gothic", "MS PGothic", "ＭＳ ゴシック")


def _font_data_url(path: Path) -> Optional[str]:
    if not path.exists():
        logger.warning("[浏览器截图] 字体文件不存在: %s", path)
        return None

    mime = "font/ttc" if path.suffix.lower() == ".ttc" else "font/ttf"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _font_face(family: str, src: str, font_format: str, weight: int) -> str:
    return (
        "@font-face {"
        f"font-family: '{family}';"
        f"src: url('{src}') format('{font_format}');"
        f"font-weight: {weight};"
        "font-style: normal;"
        "font-display: block;"
        "}"
    )


def _build_faces(filename: str, weight: int, families) -> List[str]:
    font_path = Path(__file__).resolve().parent / "assets" / "fonts" / filename
    src = _font_data_url(font_path)
    if not src:
        return []
    font_format = "truetype-collection" if font_path.suffix.lower() == ".ttc" else "truetype"
    return [_font_face(family, src, font_format, weight) for family in families]


@lru_cache(maxsize=1)
def get_browser_font_css() -> str:
    faces: List[str] = []
    # Latin 字体（细 / 粗）
    faces += _build_faces("segoeui.ttf", 400, _LATIN_FAMILIES)
    faces += _build_faces("segoeuib.ttf", 700, _LATIN_FAMILIES)
    # CJK 字体（细 / 粗）
    faces += _build_faces("BIZ-UDGOTHICR.TTC", 400, _CJK_FAMILIES)
    faces += _build_faces("BIZ-UDGothicB.ttc", 700, _CJK_FAMILIES)
    # MS Gothic 别名（仅常规字重）
    faces += _build_faces("msgothic.ttc", 400, _MS_GOTHIC_FAMILIES)

    return "\n".join(faces)


async def register_browser_fonts(page) -> None:
    """在导航前通过 init script 注入 @font-face，让首屏渲染就能用上内置字体。"""
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
    css = get_browser_font_css()
    if not css:
        logger.warning("[浏览器截图] 未加载到内置字体，继续使用系统字体。")
        return

    await page.add_style_tag(content=css)
    await wait_for_browser_fonts(page)
