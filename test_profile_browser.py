"""
独立测试脚本：渲染 Profile 浏览器截图并校验 base64 图片。

运行前需要安装：
    pip install playwright
    python -m playwright install chromium

默认使用线上 NAGEKI-NET-NEXT 前端：
    https://next.nageki-net.com/render/ongeki-profile
"""

import asyncio
import base64
import os

from profile_browser import generate_profile_browser_image


class MockApiClient:
    cdn_base_url = "https://cdn-nageki-next.sys-all.com.cn"
    profile_render_url = os.getenv("NAGEKI_PROFILE_RENDER_URL", "https://next.nageki-net.com/render/ongeki-profile")
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
    print("截图成功")
    print(f"图片大小: {len(image_bytes):,} bytes")


if __name__ == "__main__":
    asyncio.run(main())
