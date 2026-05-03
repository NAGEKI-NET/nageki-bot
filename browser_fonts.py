import base64
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


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


async def inject_browser_fonts(page) -> None:
    css = get_browser_font_css()
    if not css:
        logger.warning("[浏览器截图] 未加载到内置字体，继续使用系统字体。")
        return

    await page.add_style_tag(content=css)
    await page.evaluate(
        """
        async () => {
          if (document.fonts && document.fonts.ready) {
            await document.fonts.ready;
          }
        }
        """
    )
