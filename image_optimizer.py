"""把 Playwright 截到的 PNG 字节压成更小的图，缩短 QQ 上传时间。

策略：
- 默认转 WebP（lossy quality=88，method=2 快编码），保留透明通道。
  对纯前端 UI 截图来说肉眼无损，体积通常是原 PNG 的 1/3~1/2。
- 同步 Pillow 调用通过 asyncio.to_thread 跑在线程池，不阻塞事件循环。
- 可通过环境变量 NAGEKI_IMAGE_FORMAT 切换：
    - ``webp`` (默认)
    - ``png``  仅 Pillow 重新优化压缩（小幅减小，无损）
    - ``jpeg`` 强制 JPEG（无透明，最小但需要页面本身有底色）
    - ``raw`` / ``none`` 跳过优化，直接返回原 PNG
- WebP 编码 effort 通过 ``NAGEKI_IMAGE_WEBP_METHOD`` 调，0(最快) ~ 6(最压缩)。
- Pillow 不可用时退化为原 PNG（不会报错）。
"""

import asyncio
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


def _webp_method() -> int:
    """libwebp 编码 effort：0(最快) ~ 6(最压缩最慢)。默认 2，方便低配 CPU 快速出图。"""
    try:
        return max(0, min(6, int(os.getenv("NAGEKI_IMAGE_WEBP_METHOD", "2"))))
    except ValueError:
        return 2


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
    """对截图字节做后处理压缩（同步阻塞）；失败时返回原 PNG 字节。

    注意：是 CPU bound，请用 `await asyncio.to_thread(compress_screenshot_bytes, png_bytes)`
    或调用 `compress_screenshot_bytes_async` 包装，避免阻塞 asyncio 事件循环。
    """
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
                if img.mode not in ("RGBA", "RGB", "LA", "L"):
                    img = img.convert("RGBA")
                img.save(
                    buf,
                    format="WEBP",
                    quality=_webp_quality(),
                    method=_webp_method(),
                )
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
            img.save(buf, format="PNG", optimize=True, compress_level=6)
            return _smaller(png_bytes, buf.getvalue())
    except Exception as exc:
        logger.warning("[图像压缩] 转码失败，回退原 PNG: %s", exc)
        return png_bytes


async def compress_screenshot_bytes_async(
    png_bytes: bytes, format_override: Optional[str] = None
) -> bytes:
    """异步包装：把 CPU bound 的压缩搬到线程池，避免阻塞 event loop。"""
    return await asyncio.to_thread(compress_screenshot_bytes, png_bytes, format_override)


def _smaller(a: bytes, b: bytes) -> bytes:
    """选两者中较小的一份，避免反而变大。"""
    return b if len(b) < len(a) else a
