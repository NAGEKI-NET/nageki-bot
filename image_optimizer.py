"""把 Playwright 截到的 PNG 字节压成更小的图，缩短 QQ 上传时间。

策略：
- 默认转 WebP（lossy quality=88，method=6 高压缩），保留透明通道。
  对纯前端 UI 截图来说肉眼无损，体积通常是原 PNG 的 1/3~1/2。
- 可通过环境变量 NAGEKI_IMAGE_FORMAT 切换：
    - ``webp`` (默认)
    - ``png``  仅 Pillow 重新优化压缩（小幅减小，无损）
    - ``jpeg`` 强制 JPEG（无透明，最小但需要页面本身有底色）
    - ``raw`` / ``none`` 跳过优化，直接返回原 PNG
- Pillow 不可用时退化为原 PNG（不会报错）。

WebP 是 QQ 客户端原生支持的格式，OneBot/NapCat 等适配器拿到 base64 字节后会自动嗅探 MIME。
"""

import io
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _format() -> str:
    value = os.getenv("NAGEKI_IMAGE_FORMAT", "webp").strip().lower()
    if value in {"", "auto"}:
        return "webp"
    return value


def _webp_quality() -> int:
    try:
        return max(50, min(100, int(os.getenv("NAGEKI_IMAGE_WEBP_QUALITY", "88"))))
    except ValueError:
        return 88


def _jpeg_quality() -> int:
    try:
        return max(50, min(100, int(os.getenv("NAGEKI_IMAGE_JPEG_QUALITY", "85"))))
    except ValueError:
        return 85


def _try_pillow():
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def compress_screenshot_bytes(png_bytes: bytes, format_override: Optional[str] = None) -> bytes:
    """对截图字节做后处理压缩，失败时返回原 PNG 字节。"""
    fmt = (format_override or _format()).lower()
    if fmt in {"raw", "none", "png-raw"}:
        return png_bytes

    if not _try_pillow():
        logger.debug("[图像压缩] 未安装 Pillow，跳过转码。")
        return png_bytes

    from PIL import Image

    try:
        with Image.open(io.BytesIO(png_bytes)) as img:
            img.load()
            if fmt == "webp":
                buf = io.BytesIO()
                save_kwargs = {
                    "format": "WEBP",
                    "quality": _webp_quality(),
                    "method": 6,
                }
                # 保留透明通道
                if img.mode not in ("RGBA", "RGB", "LA", "L"):
                    img = img.convert("RGBA")
                img.save(buf, **save_kwargs)
                return _smaller(png_bytes, buf.getvalue())

            if fmt == "jpeg":
                if img.mode != "RGB":
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(
                    buf,
                    format="JPEG",
                    quality=_jpeg_quality(),
                    optimize=True,
                    progressive=True,
                )
                return _smaller(png_bytes, buf.getvalue())

            # fmt == "png" — 仅重压缩
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True, compress_level=9)
            return _smaller(png_bytes, buf.getvalue())
    except Exception as exc:
        logger.warning("[图像压缩] 转码失败，回退原 PNG: %s", exc)
        return png_bytes


def _smaller(a: bytes, b: bytes) -> bytes:
    """选两者中较小的一份，避免反而变大。"""
    return b if len(b) < len(a) else a
