"""
独立测试脚本：只生成 Rating 样式图并打开查看，不依赖 AstrBot。
需要先安装 Pillow: pip install pillow
"""
import os
import sys
import asyncio

# 确保当前目录在 path 中，便于导入 rating_canvas
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rating_canvas import generate_rating_canvas_image


def _generate_mock_data():
    """生成示例数据用于测试样式"""
    profile = {
        "userRanking": 1234,
        "newPlayerRating": 19032,  # 19.032
        "newHighestRating": 19500,  # 19.500
        "playCount": 1234
    }
    
    # 示例 B50 数据
    b50_items = [
        {
            "musicId": 1,
            "level": 2,
            "value": 1008265,
            "rating": 19.32,
            "chartConstant": 17.0,
            "ratingBonus": 2.32,
            "musicInfo": {
                "id": 1,
                "name": "B50 Sample Song 1",
                "artistName": "Artist A",
                "level0": "7.0",
                "level1": "10.0",
                "level2": "14.7",
                "level3": "15.5",
                "level4": ""
            }
        },
        {
            "musicId": 2,
            "level": 3,
            "value": 1004000,
            "rating": 19.05,
            "chartConstant": 16.5,
            "ratingBonus": 2.55,
            "musicInfo": {
                "id": 2,
                "name": "B50 Sample Song 2",
                "artistName": "Artist B",
                "level0": "7.5",
                "level1": "11.0",
                "level2": "14.4",
                "level3": "15.8",
                "level4": ""
            }
        },
        {
            "musicId": 3,
            "level": 2,
            "value": 998000,
            "rating": 18.50,
            "chartConstant": 16.0,
            "ratingBonus": 2.50,
            "musicInfo": {
                "id": 3,
                "name": "B50 Sample Song 3",
                "artistName": "Artist C",
                "level0": "6.5",
                "level1": "9.5",
                "level2": "13.8",
                "level3": "15.0",
                "level4": ""
            }
        }
    ]
    
    # 示例 NEW10 数据
    new10_items = [
        {
            "musicId": 4,
            "level": 1,
            "value": 997000,
            "rating": 18.10,
            "chartConstant": 15.5,
            "ratingBonus": 2.60,
            "musicInfo": {
                "id": 4,
                "name": "NEW10 Sample Song 1",
                "artistName": "Artist D",
                "level0": "6.0",
                "level1": "9.0",
                "level2": "12.5",
                "level3": "14.0",
                "level4": ""
            }
        }
    ]
    
    # 示例 PSCORE 数据
    pscore_items = [
        {
            "musicId": 5,
            "level": 3,
            "value": 1000000,
            "rating": 0.135,
            "chartConstant": 14.9,
            "ratingBonus": -1.5,
            "isPScore": True,
            "platinumScoreMax": 100000,
            "platinumScoreStar": 4,
            "musicInfo": {
                "id": 5,
                "name": "PSCORE Sample Song 1",
                "artistName": "Artist E",
                "level0": "7.0",
                "level1": "10.5",
                "level2": "13.5",
                "level3": "14.9",
                "level4": ""
            }
        }
    ]
    
    categories = [
        {
            "title": "B50",
            "description": "BEST 50",
            "items": b50_items,
            "totalRating": sum(item["rating"] for item in b50_items),
            "averageRating": sum(item["rating"] for item in b50_items) / len(b50_items) if b50_items else 0
        },
        {
            "title": "NEW10",
            "description": "NEW 10",
            "items": new10_items,
            "totalRating": sum(item["rating"] for item in new10_items),
            "averageRating": sum(item["rating"] for item in new10_items) / len(new10_items) if new10_items else 0
        },
        {
            "title": "PSCORE 50",
            "description": "PLATINUM SCORE 50",
            "items": pscore_items,
            "totalRating": sum(item["rating"] for item in pscore_items),
            "averageRating": sum(item["rating"] for item in pscore_items) / len(pscore_items) if pscore_items else 0
        }
    ]
    
    return profile, categories


async def async_main():
    """异步主函数"""
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(plugin_dir, "assets", "nageki_rating.png")
    
    try:
        # 生成示例数据
        profile, categories = _generate_mock_data()
        
        # 生成图片（不传 api_client，所以不会下载真实图片）
        await generate_rating_canvas_image(
            output_path,
            profile,
            categories,
            api_client=None
        )
        
        print(f"已生成: {output_path}")
        
        # 用系统默认程序打开图片
        if sys.platform == "win32":
            os.startfile(output_path)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", output_path], check=False)
        else:
            import subprocess
            subprocess.run(["xdg-open", output_path], check=False)
            
    except RuntimeError as e:
        if "Pillow" in str(e):
            print(e)
            print("请先安装: pip install pillow")
        else:
            raise
        sys.exit(1)
    except Exception as e:
        print(f"生成图片时出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """主函数入口"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
