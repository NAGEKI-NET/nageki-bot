"""Rating 图片绘制逻辑，支持真实数据和图片。"""
import os
import io
import asyncio
import logging
import math
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageColor
except ImportError:
    Image = ImageDraw = ImageFont = ImageColor = None

from .rating_calculator import RatingCalculator


async def generate_rating_canvas_image(
    output_path: str,
    profile: Dict[str, Any],
    categories: List[Dict[str, Any]],
    api_client=None
) -> str:
    """
    使用 Pillow 绘制与前端 Rating 页布局相近的图片，并保存到 output_path。
    """
    if Image is None:
        raise RuntimeError("Pillow 未安装，无法绘制图片，请安装 pillow 再试。")
    
    # 基础配置
    width = 1400 
    margin_x = 32
    margin_y = 32
    
    # Tailwind Colors (Dark Mode)
    bg_color = (17, 24, 39)      # gray-900
    card_bg_color = (55, 65, 81) # gray-700
    card_border_color = (75, 85, 99) # gray-600
    
    text_white = (243, 244, 246) # gray-100
    text_gray = (156, 163, 175)  # gray-400
    text_blue = (96, 165, 250)   # blue-400
    text_green = (74, 222, 128)  # green-400
    text_purple = (192, 132, 252) # purple-400
    text_yellow = (234, 179, 8)   # yellow-500
    text_teal = (45, 212, 191)    # teal-400 (用于New 10)
    
    def mix_color(c1, c2, alpha=0.5):
        return tuple(int(c1[i] * (1-alpha) + c2[i] * alpha) for i in range(3))

    diff_styles = {
        0: {"bg": mix_color(card_bg_color, (19, 78, 74), 0.5), "text": (153, 246, 228)},   # Basic
        1: {"bg": mix_color(card_bg_color, (124, 45, 18), 0.5), "text": (254, 215, 170)},  # Advanced
        2: {"bg": mix_color(card_bg_color, (127, 29, 29), 0.5), "text": (254, 202, 202)},  # Expert
        3: {"bg": mix_color(card_bg_color, (88, 28, 135), 0.5), "text": (233, 213, 255)},  # Master
        10: {"bg": (31, 41, 55), "text": (220, 38, 38), "border": (220, 38, 38)}           # Lunatic
    }

    # 尺寸配置
    header_height = 90 # 稍微调小一点
    item_height = 112
    item_gap = 16
    items_per_row = 5
    
    # 计算总高度
    total_height = margin_y
    for category in categories:
        items_count = len(category["items"])
        if items_count > 0:
            rows = (items_count + items_per_row - 1) // items_per_row
            cat_height = header_height + rows * item_height + (rows - 1) * item_gap + 24
            total_height += cat_height + 24
    
    # 增加底部额外高度，防止内容被截断
    height = total_height + margin_y + 60
    
    # 0. 预下载所有封面图 (Pre-fetch)
    # 将所有分类的下载任务合并，一次性并发下载，提高速度并减少由于分批下载导致的卡顿
    all_music_ids = set()
    for category in categories:
        for item in category["items"]:
            mid = item.get("musicId")
            if mid:
                all_music_ids.add(mid)
    
    downloaded_jackets = {}
    if api_client and all_music_ids:
        logger.info(f"[绘图] 准备并发下载 {len(all_music_ids)} 张封面图...")
        music_id_list = list(all_music_ids)
        # 此时 get_jacket_image 已经支持内部 timeout (默认10s)
        tasks = [api_client.get_jacket_image(mid, size="S", cache=True) for mid in music_id_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        for i, res in enumerate(results):
            if isinstance(res, bytes):
                downloaded_jackets[music_id_list[i]] = res
                success_count += 1
            else:
                 logger.warning(f"[绘图] 图片下载失败 ID={music_id_list[i]}: {res}")
        
        logger.info(f"[绘图] 下载完成，成功: {success_count}/{len(all_music_ids)}")
    
    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # 加载字体
    def load_font(size: int, bold=False):
        font_paths = []
        if bold:
            font_paths.extend([
                "msyhbd.ttc", "msyhbd.ttf", "simheibd.ttf", "arialbd.ttf",
                "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/arialbd.ttf"
            ])
        font_paths.extend([
            "msyh.ttc", "msyh.ttf", "simhei.ttf", "arial.ttf",
            "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
        ])
        for path in font_paths:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()
    
    title_font = load_font(24, bold=True) # text-2xl
    subtitle_font = load_font(16)
    card_title_font = load_font(15, bold=True)
    label_font = load_font(14)            # text-sm (用于Header右侧Label)
    artist_font = load_font(11)
    rating_font = load_font(13, bold=True)
    score_font = load_font(15, bold=True)
    badge_font = load_font(11, bold=True)
    rank_font = load_font(48, bold=True)
    star_font = load_font(12) # 用于星星
    
    # 辅助绘图函数
    def draw_round_rect(x1, y1, x2, y2, radius, fill, outline=None, width=1):
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)
    
    def truncate_text(text, max_width, font):
        if not text: return ""
        if draw.textlength(text, font=font) <= max_width:
            return text
        while len(text) > 0 and draw.textlength(text + "...", font=font) > max_width:
            text = text[:-1]
        return text + "..."
    
    def create_left_rounded_mask(size: int, radius: int) -> Image.Image:
        """创建左侧圆角、右侧直角的蒙版"""
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        # 绘制完整的圆角矩形
        mask_draw.rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
        # 覆盖右侧区域，使其成为直角（确保与卡片边界对齐）
        # 使用更大的覆盖区域，确保完全覆盖圆角
        mask_draw.rectangle([size - radius - 1, 0, size, size], fill=255)
        return mask

    # 绘制五角星
    def draw_star(cx, cy, r, fill):
        points = []
        for i in range(10):
            angle = math.pi/2 + i * math.pi/5
            dist = r if i % 2 == 0 else r * 0.4
            points.append((cx + math.cos(angle) * dist, cy - math.sin(angle) * dist))
        draw.polygon(points, fill=fill)
        
    # 绘制菱形
    def draw_diamond(cx, cy, r, fill):
        draw.polygon([(cx, cy-r), (cx+r, cy), (cx, cy+r), (cx-r, cy)], fill=fill)

    # 绘制 Icon 背景
    def draw_icon_bg(cx, cy, size, icon_type):
        if icon_type == 'star': # Blue Star
            draw_star(cx, cy, size/2, fill=(59, 130, 246)) # blue-500
        elif icon_type == 'new': # Teal Badge
             # 类似锯齿圆形，这里简化为圆形
            draw.ellipse([cx-size/2, cy-size/2, cx+size/2, cy+size/2], fill=(45, 212, 191)) # teal-400
            # 内部感叹号
            draw.text((cx-3, cy-10), "!", fill=(17, 24, 39), font=load_font(18, bold=True)) # gray-900 text
        elif icon_type == 'diamond': # Purple Diamond
             draw_diamond(cx, cy, size/2, fill=(168, 85, 247)) # purple-500
             
    y = margin_y
    
    # 遍历分类绘制
    for category in categories:
        items = category["items"]
        if not items:
            continue
            
        cat_title = category.get("title", "")
        # 根据标题判断样式
        style_type = 'blue'
        icon_type = 'star'
        header_title = cat_title
        header_subtitle = "BEST " + (cat_title.replace("Best ", "") if "Best" in cat_title else "DATA")
        
        stat_label = "平均单曲Rating"
        stat_value = RatingCalculator.format_rating(category.get('averageRating', 0))
        stat_color = text_white
        
        cat_title_lower = cat_title.lower()
        
        if "new" in cat_title_lower or "recent" in cat_title_lower:
            style_type = 'new'
            icon_type = 'new'
            header_subtitle = "NEW 10"
            stat_color = text_teal # 使用青色
        elif "pscore" in cat_title_lower:
            style_type = 'purple'
            icon_type = 'diamond'
            header_subtitle = "PLATINUM SCORE " + str(len(items))
            stat_label = "Rating 贡献"
            # 计算总 Rating 贡献
            total_rating = RatingCalculator.calculate_total_rating(items)
            stat_value = f"+{total_rating:.2f}"
            stat_color = text_purple

        # 1. 计算板块高度和布局
        container_padding_x = 20
        container_padding_top = 20
        container_padding_bottom = 24
        
        rows = (len(items) + items_per_row - 1) // items_per_row
        grid_height = rows * item_height + (rows - 1) * item_gap
        container_height = header_height + container_padding_top + grid_height + container_padding_bottom
        
        # 计算 Header 背景色
        base_header_bg = (31, 41, 55)
        if style_type == 'new':
            header_bg = mix_color(base_header_bg, (45, 212, 191), 0.15)
        elif style_type == 'purple':
            header_bg = mix_color(base_header_bg, (168, 85, 247), 0.15)
        else: # blue
            header_bg = mix_color(base_header_bg, (59, 130, 246), 0.15)
        
        # 2. 绘制大板块容器 (gray-800)
        container_bg = (31, 41, 55)
        container_x1 = margin_x
        container_y1 = y
        container_x2 = width - margin_x
        container_y2 = y + container_height
        
        draw_round_rect(container_x1, container_y1, container_x2, container_y2, 12, container_bg)
        
        # 3. 绘制 Header 背景 (带颜色, Top Rounded, Bottom Square)
        # 先画圆角矩形，再填补下方直角
        draw_round_rect(container_x1, container_y1, container_x2, container_y1 + header_height, 12, header_bg)
        draw.rectangle([container_x1, container_y1 + header_height - 12, container_x2, container_y1 + header_height], fill=header_bg)
        
        # 绘制 Header 内容 (Icon, Text)
        # Icon
        icon_cx = container_x1 + 40
        icon_cy = container_y1 + header_height // 2
        draw_icon_bg(icon_cx, icon_cy, 32, icon_type)
        
        # Titles
        title_x = container_x1 + 80
        draw.text((title_x, container_y1 + 20), header_title, fill=text_white, font=title_font)
        draw.text((title_x, container_y1 + 58), header_subtitle, fill=(156, 163, 175), font=subtitle_font) # gray-400
        
        # Right Stats
        # 垂直居中计算
        stat_y_start = container_y1 + 23
        
        label_w = draw.textlength(stat_label, font=label_font)
        right_margin = container_x2 - 32
        draw.text((right_margin - label_w, stat_y_start), stat_label, fill=(156, 163, 175), font=label_font)
        
        stat_val_w = draw.textlength(stat_value, font=title_font)
        draw.text((right_margin - stat_val_w, stat_y_start + 24), stat_value, fill=stat_color, font=title_font)

        # 绘制 Grid Items
        # 增加 Top Padding
        grid_start_y = container_y1 + header_height + container_padding_top
        
        # 重新计算 item_width (减去容器内边距)
        # 容器宽度 = width - 2*margin_x
        # 内部宽度 = 容器宽度 - 2*container_padding_x
        inner_width = (width - 2 * margin_x) - 2 * container_padding_x
        item_width = (inner_width - (items_per_row - 1) * item_gap) // items_per_row
        
        # (旧的并发下载逻辑已移除，改用预下载)
                    
        # 绘制 Grid Items
        for idx, item in enumerate(items):
            row = idx // items_per_row
            col = idx % items_per_row
            
            # 计算 Item 坐标 (相对于 Container)
            ix = container_x1 + container_padding_x + col * (item_width + item_gap)
            iy = grid_start_y + row * (item_height + item_gap)
            
            # 卡片背景
            draw_round_rect(ix, iy, ix + item_width, iy + item_height, 12, card_bg_color, outline=card_border_color)
            
            # 封面图
            jacket_size = item_height
            card_radius = 12  # 与卡片圆角半径一致
            
            # 绘制占位背景（带圆角）
            placeholder_mask = create_left_rounded_mask(jacket_size, card_radius)
            placeholder = Image.new("RGB", (jacket_size, jacket_size), (75, 85, 99))
            img.paste(placeholder, (ix, iy), placeholder_mask)
            
            jacket_data = downloaded_jackets.get(item.get("musicId"))
            if jacket_data:
                try:
                    jacket_img = Image.open(io.BytesIO(jacket_data))
                    jacket_img = jacket_img.resize((jacket_size, jacket_size), Image.LANCZOS)
                    
                    # 使用精确的左侧圆角蒙版
                    mask = create_left_rounded_mask(jacket_size, card_radius)
                    
                    # 使用蒙版粘贴图片，确保圆角精确对齐，不会溢出
                    img.paste(jacket_img, (ix, iy), mask)
                except Exception as e:
                    logger.warning(f"[绘图] 封面图片处理失败: {e}")
            
            # 信息区域
            info_padding = 12
            info_x = ix + jacket_size + info_padding
            info_y = iy + info_padding
            info_w = item_width - jacket_size - (info_padding * 2)
            
            # 水印
            rank_num = str(idx + 1)
            rw = draw.textlength(rank_num, font=rank_font)
            watermark_x = ix + item_width - rw + 4
            watermark_y = iy + item_height - 48
            
            txt_layer = Image.new("RGBA", (width, height), (0,0,0,0))
            txt_draw = ImageDraw.Draw(txt_layer)
            txt_draw.text((watermark_x, watermark_y), rank_num, fill=(107, 114, 128, 50), font=rank_font)
            img.alpha_composite(txt_layer)
            
            # Title & Artist
            music_info = item.get("musicInfo") or item.get("fullMusicInfo", {}).get("music")
            music_name = music_info.get("name", f"ID: {item['musicId']}") if music_info else f"ID: {item['musicId']}"
            artist = music_info.get("artistName", "") if music_info else ""
            
            draw.text((info_x, info_y), truncate_text(music_name, info_w, card_title_font), fill=text_white, font=card_title_font)
            draw.text((info_x, info_y + 20), truncate_text(artist, info_w, artist_font), fill=text_gray, font=artist_font)
            
            # 底部信息
            bottom_y = iy + item_height - info_padding
            
            # 难度 Badge
            level = item.get("level", 0)
            chart_const = item.get("chartConstant", 0.0)
            level_text = f"{chart_const:.1f}"
            
            style = diff_styles.get(level, {"bg": (75, 85, 99), "text": (255, 255, 255)})
            badge_bg = style["bg"]
            badge_fg = style["text"]
            badge_border = style.get("border")
            
            tw = draw.textlength(level_text, font=badge_font)
            badge_w = max(32, tw + 12)
            badge_h = 16
            badge_x1 = info_x
            badge_y1 = bottom_y - badge_h
            
            draw_round_rect(badge_x1, badge_y1, badge_x1 + badge_w, badge_y1 + badge_h, 4, badge_bg, outline=badge_border)
            draw.text((badge_x1 + (badge_w - tw) / 2, badge_y1 + 1), level_text, fill=badge_fg, font=badge_font)
            
            # 右侧数值 (区分 PScore 和 普通模式)
            is_pscore = category.get('title', '').startswith("PSCORE") or item.get('isPScore')
            right_x = ix + item_width - info_padding
            
            if is_pscore:
                # PScore 模式
                # 下行: 白金分 + 星星
                # 上行: Rating 贡献 (紫色)
                
                # 下行: 分数 (紫色)
                score_val = item.get("platinumScoreMax", 0)
                score_str = f"{score_val:,}"
                sw = draw.textlength(score_str, font=score_font)
                # 移除重复绘制的数值
                # score_y = bottom_y - 16
                # draw.text((right_x - sw, score_y), score_str, fill=text_purple, font=score_font)
                
                # 星星 (在分数左边？或者下面？看图星星在右下角，分数在星星上面？)
                # 再看图3: 
                # 右下角是星星 (3实2空)
                # 星星上面是分数 1691 (紫色)
                # 分数上面是 Rating贡献 (紫色)
                
                # 好像不对。图3:
                # 底部一行: 左边 Badge (11.90), 右边 星星 (★★★☆☆)
                # 倒数第二行: 右边 分数 1691 (紫色)
                # 倒数第三行: 右边 Rating +0.011 (紫色小字)
                
                # 让我们重新排布 PScore
                # 星星在最底部右侧
                star_count = item.get("platinumScoreStar", 0)
                star_str = "★" * star_count + "☆" * (5 - star_count)
                star_w = draw.textlength(star_str, font=star_font)
                draw.text((right_x - star_w, bottom_y - 12), "★" * star_count, fill=text_yellow, font=star_font)
                # 补画空心星
                filled_w = draw.textlength("★" * star_count, font=star_font)
                draw.text((right_x - star_w + filled_w, bottom_y - 12), "☆" * (5 - star_count), fill=text_gray, font=star_font)
                
                # 上方是分数
                score_y = bottom_y - 28
                draw.text((right_x - sw, score_y), score_str, fill=text_purple, font=card_title_font)
                
                # 再上方是 Rating
                rating_val = item.get("rating", 0)
                rating_str = f"+{rating_val:.3f}"
                # 使用稍大一点的字体避免看起来扁平
                rw = draw.textlength(rating_str, font=rating_font)
                draw.text((right_x - rw, score_y - 16), rating_str, fill=text_purple, font=rating_font)
                
            else:
                # 普通模式
                # 下行: Score (绿色)
                score_val = item.get("value", 0)
                score_str = f"{score_val:,}"
                sw = draw.textlength(score_str, font=score_font)
                score_y = bottom_y - 16
                draw.text((right_x - sw, score_y), score_str, fill=text_green, font=score_font)
                
                # 上行: Rating (蓝色) + Bonus
                rating_val = item.get("rating", 0)
                rating_str = f"{rating_val:.2f}"
                bonus = item.get("ratingBonus", 0)
                
                rw = draw.textlength(rating_str, font=rating_font)
                current_rx = right_x
                rating_y = score_y - 14
                
                if bonus > 0:
                    bonus_str = f"+{bonus:.2f}"
                    bw = draw.textlength(bonus_str, font=artist_font)
                    draw.text((current_rx - bw, rating_y), bonus_str, fill=text_gray, font=artist_font)
                    current_rx -= (bw + 4)
                
                draw.text((current_rx - rw, rating_y - 1), rating_str, fill=text_blue, font=rating_font)
            
            
        # 更新 y 坐标 (增加板块间距)
        y += container_height + 40
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.convert("RGB").save(output_path) # 转回 RGB 保存
    
    # 检查文件大小并压缩
    try:
        file_size = os.path.getsize(output_path)
        logger.info(f"[绘图] 原始图片大小: {file_size / 1024 / 1024:.2f} MB")
        
        if file_size > 3 * 1024 * 1024:
            logger.info("[绘图] 图片超过 3MB，正在进行压缩...")
            # 转换为 JPEG
            new_path = os.path.splitext(output_path)[0] + ".jpg"
            img.convert("RGB").save(new_path, "JPEG", quality=85)
            
            new_size = os.path.getsize(new_path)
            logger.info(f"[绘图] 压缩后图片大小: {new_size / 1024 / 1024:.2f} MB")
            
            # 删除旧文件
            if os.path.exists(output_path) and new_path != output_path:
                os.remove(output_path)
            
            return new_path
    except Exception as e:
        logger.warning(f"[绘图] 图片压缩失败: {e}")
            
    return output_path
