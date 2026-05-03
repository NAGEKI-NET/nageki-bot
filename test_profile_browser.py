"""
独立测试脚本：渲染 Profile 浏览器截图并保存预览图。

运行前需要安装：
    pip install playwright pillow
    python -m playwright install chromium

并启动 NAGEKI-NET-NEXT 前端服务，默认地址：
    http://localhost:4200/render/ongeki-profile
"""

import asyncio
import base64
import os
from pathlib import Path

from profile_browser import generate_profile_browser_image


class MockApiClient:
    cdn_base_url = "https://cdn-nageki-next.sys-all.com.cn"
    profile_render_url = "http://localhost:4200/render/ongeki-profile"
    profile_render_theme = os.getenv("NAGEKI_PROFILE_RENDER_THEME", "dark")
    profile_render_language = os.getenv("NAGEKI_PROFILE_RENDER_LANGUAGE", "zh")


def build_mock_profile():
    return {
        "userName": "NagekiTester",
        "profileContent": "Playwright screenshot render test.",
        "cardId": 101010,
        "level": 72,
        "exp": 62000,
        "newPlayerRating": 15234,
        "newHighestRating": 15888,
        "playerRating": 1523,
        "highestRating": 1588,
        "playCount": 1234,
        "userRanking": 56,
        "playedMusicCountBasic": 120,
        "playedMusicCountAdvanced": 118,
        "playedMusicCountExpert": 112,
        "playedMusicCountMaster": 96,
        "playedMusicCountLunatic": 18,
        "playedMusicCountTotal": 464,
        "sumTechBasicHighScore": 120 * 1005000,
        "sumTechAdvancedHighScore": 118 * 1001200,
        "sumTechExpertHighScore": 112 * 998800,
        "sumTechMasterHighScore": 96 * 995400,
        "sumTechLunaticHighScore": 18 * 990000,
        "sumTechHighScore": (
            120 * 1005000
            + 118 * 1001200
            + 112 * 998800
            + 96 * 995400
            + 18 * 990000
        ),
    }


async def main():
    image_url = await generate_profile_browser_image(
        "",
        build_mock_profile(),
        api_client=MockApiClient(),
    )

    if not image_url.startswith("base64://"):
        raise RuntimeError(f"截图返回格式异常: {image_url[:40]}")

    image_bytes = base64.b64decode(image_url.removeprefix("base64://"))
    output_path = Path(__file__).parent / "assets" / "profile_browser_test.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)

    print(f"截图成功: {output_path}")
    print(f"图片大小: {len(image_bytes):,} bytes")

    try:
        from PIL import Image

        with Image.open(output_path) as image:
            print(f"图片尺寸: {image.width}x{image.height}")
    except ImportError:
        print("未安装 pillow，跳过尺寸检查。")


if __name__ == "__main__":
    asyncio.run(main())
