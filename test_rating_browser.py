"""
独立测试脚本：渲染 Rating 浏览器截图并保存预览图。

运行前需要安装：
    pip install playwright pillow
    python -m playwright install chromium

并启动 NAGEKI-NET-NEXT 前端服务，默认地址：
    http://localhost:4200/render/ongeki-rating
"""

import asyncio
import base64
import os
from pathlib import Path

from rating_browser import generate_rating_browser_image


class MockApiClient:
    cdn_base_url = "https://cdn-nageki-next.sys-all.com.cn"
    rating_render_url = "http://localhost:4200/render/ongeki-rating"
    profile_render_theme = os.getenv("NAGEKI_PROFILE_RENDER_THEME", "dark")
    profile_render_language = os.getenv("NAGEKI_PROFILE_RENDER_LANGUAGE", "zh")


def build_mock_profile():
    return {
        "userName": "NagekiTester",
        "profileContent": "Playwright rating render test.",
        "newPlayerRating": 19032,
        "newHighestRating": 19500,
        "playerRating": 1903,
        "highestRating": 1950,
        "playCount": 1234,
        "userRanking": 56,
    }


def build_mock_music(music_id, name, artist, levels):
    return {
        "id": music_id,
        "name": name,
        "artistName": artist,
        "level0": levels[0],
        "level1": levels[1],
        "level2": levels[2],
        "level3": levels[3],
        "level4": levels[4],
    }


def build_mock_categories():
    b50_items = [
        {
            "musicId": 1,
            "level": 2,
            "value": 1008265,
            "rating": 19.32,
            "chartConstant": 17.0,
            "ratingBonus": 2.32,
            "isAllBreak": True,
            "isFullBell": True,
            "musicInfo": build_mock_music(1, "B50 Sample Song 1", "Artist A", ["7.0", "10.0", "14.7", "15.5", ""]),
        },
        {
            "musicId": 2,
            "level": 3,
            "value": 1004000,
            "rating": 19.05,
            "chartConstant": 16.5,
            "ratingBonus": 2.55,
            "isAllBreak": False,
            "isFullBell": True,
            "musicInfo": build_mock_music(2, "B50 Sample Song 2", "Artist B", ["7.5", "11.0", "14.4", "15.8", ""]),
        },
    ]

    new10_items = [
        {
            "musicId": 3,
            "level": 1,
            "value": 997000,
            "rating": 18.10,
            "chartConstant": 15.5,
            "ratingBonus": 2.60,
            "isAllBreak": False,
            "isFullBell": False,
            "musicInfo": build_mock_music(3, "NEW10 Sample Song 1", "Artist C", ["6.0", "9.0", "12.5", "14.0", ""]),
        }
    ]

    pscore_items = [
        {
            "musicId": 4,
            "level": 3,
            "value": 1000000,
            "rating": 0.135,
            "chartConstant": 14.9,
            "ratingBonus": -1.5,
            "isPScore": True,
            "platinumScoreMax": 100000,
            "platinumScoreStar": 4,
            "musicInfo": build_mock_music(4, "PSCORE Sample Song 1", "Artist D", ["7.0", "10.5", "13.5", "14.9", ""]),
        }
    ]

    return [
        {
            "title": "B50",
            "description": "BEST 50",
            "items": b50_items,
            "totalRating": sum(item["rating"] for item in b50_items),
            "averageRating": sum(item["rating"] for item in b50_items) / len(b50_items),
        },
        {
            "title": "NEW10",
            "description": "NEW 10",
            "items": new10_items,
            "totalRating": sum(item["rating"] for item in new10_items),
            "averageRating": sum(item["rating"] for item in new10_items) / len(new10_items),
        },
        {
            "title": "PSCORE 50",
            "description": "PLATINUM SCORE 50",
            "items": pscore_items,
            "totalRating": sum(item["rating"] for item in pscore_items),
            "averageRating": sum(item["rating"] for item in pscore_items) / len(pscore_items),
        },
    ]


async def main():
    image_url = await generate_rating_browser_image(
        "",
        build_mock_profile(),
        build_mock_categories(),
        api_client=MockApiClient(),
    )

    if not image_url.startswith("base64://"):
        raise RuntimeError(f"截图返回格式异常: {image_url[:40]}")

    image_bytes = base64.b64decode(image_url.removeprefix("base64://"))
    output_path = Path(__file__).parent / "assets" / "rating_browser_test.png"
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
