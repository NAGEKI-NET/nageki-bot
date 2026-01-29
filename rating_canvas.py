"""Rating 图片绘制逻辑，支持真实数据和图片。"""
import os
import io
import asyncio
import logging
import math
from typing import Dict, Any, List, Optional, Tuple
import re

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
    
    # 加载字体组 (Latin, CJK_Main, CJK_Fallback)
    def load_font_group(size: int, bold=False):
        plugin_dir = os.path.dirname(__file__)
        fonts_dir = os.path.join(plugin_dir, "assets", "fonts")
        
        def _load(paths):
            for path in paths:
                try:
                    if os.path.exists(path):
                        return ImageFont.truetype(path, size)
                except Exception:
                    continue
            return None

        # 1. Segoe UI (Latin)
        segoe_paths = [os.path.join(fonts_dir, "segoeuib.ttf"), os.path.join(fonts_dir, "SegoeUI-Bold.ttf")] if bold else [os.path.join(fonts_dir, "segoeui.ttf"), os.path.join(fonts_dir, "SegoeUI.ttf")]
        
        # 2. BIZ UD Gothic (CJK Main)
        # 固定使用 Bold 版本，或者根据 bold 参数？用户之前说“无论是否粗体都用BIZ-UDGothicB”
        # 这里遵循用户“无论是否粗体都用BIZ-UDGothicB.ttc”的要求作为 CJK 主字体
        biz_paths = [os.path.join(fonts_dir, "BIZ-UDGothicB.ttc")]
        
        # 3. MS Gothic (CJK Fallback)
        ms_paths = [os.path.join(fonts_dir, "msgothic.ttc"), os.path.join(fonts_dir, "msgothic.ttf")]
             
        font_latin = _load(segoe_paths)
        font_cjk_main = _load(biz_paths)
        font_cjk_fallback = _load(ms_paths)
        
        # 互相作为 Fallback 以防完全缺失
        if not font_cjk_fallback: font_cjk_fallback = font_cjk_main
        if not font_cjk_main: font_cjk_main = font_cjk_fallback
        
        # 如果连 Latin 都没有，用 CJK
        if not font_latin: font_latin = font_cjk_main
        
        # 最后的保底
        if not font_latin:
             logger.error("严重: 未找到任何字体")
             fallback = ImageFont.load_default()
             return (fallback, fallback, fallback)
             
        return (font_latin, font_cjk_main, font_cjk_fallback)
        
    # 字体检测缓存
    _GLYPH_CACHE = {}
    _TOFU_CACHE = {}

    def has_glyph(font, char):
        # 常见空白字符认为存在
        if char in [' ', '\t', '\n', '\r', '\u3000']:
            return True
            
        font_id = id(font)
        if font_id not in _TOFU_CACHE:
            # 获取一个极大概率不存在的字符的 mask 作为 tofu 参考
            # 使用 Private Use Area 字符
            try:
                _TOFU_CACHE[font_id] = font.getmask('\uE000').tobytes()
            except Exception:
                _TOFU_CACHE[font_id] = None
        
        cache_key = (font_id, char)
        if cache_key in _GLYPH_CACHE:
            return _GLYPH_CACHE[cache_key]
            
        try:
            mask = font.getmask(char)
            # 如果 mask 大小或内容与 Tofu 不同，则认为支持
            # 注意：某些字体 Tofu 可能是空的，某些可能是方框
            # 这里简单比对 bytes
            has = (mask.tobytes() != _TOFU_CACHE[font_id])
            _GLYPH_CACHE[cache_key] = has
            return has
        except Exception:
            return False

    def get_char_font(char, font_group):
        latin, cjk_main, cjk_fallback = font_group
        
        # 1. 如果是 Basic Latin (ASCII)，优先 Segoe
        # 但 Segoe 可能也缺字符? 通常不会。
        if '\u0000' <= char <= '\u007F':
            if has_glyph(latin, char): return latin
            
        # 2. 否则判断是否 CJK
        is_cjk = re.search(r'[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\uff00-\uffef]', char)
        
        if is_cjk:
            # 优先 BIZ
            if has_glyph(cjk_main, char): return cjk_main
            # 其次 MS Gothic
            if has_glyph(cjk_fallback, char): return cjk_fallback
            # 如果都没有，回退到 Latin (可能显示方框)
            return latin
        else:
            # 非 CJK 字符 (如特殊符号)，优先 Segoe，然后 BIZ，然后 MS
            if has_glyph(latin, char): return latin
            if has_glyph(cjk_main, char): return cjk_main
            if has_glyph(cjk_fallback, char): return cjk_fallback
            
        return cjk_main # 默认还是给 Main

    def draw_text_fallback(xy, text, fill, font_group, anchor=None):
        if not text: return
        x, y = xy
        
        # 目前只支持简单的单行左对齐绘制，不支持 anchor (除了默认 lt)
        # 如果 text 包含不支持的字符，逐字绘制
        
        # 优化：如果整段文本都能用首选字体，则一次性绘制
        # 这对于纯英文或纯日文会快很多
        
        # 简单起见，且为了完美 Fallback，这里逐字绘制 (Visual 效果最好)
        # 但要注意性能。如果性能必须优化，可以分段。
        # 这里的 text 通常很短。
        
        current_x = x
        for char in text:
            f = get_char_font(char, font_group)
            draw.text((current_x, y), char, fill=fill, font=f)
            current_x += f.getlength(char)
            
    def get_text_width_fallback(text, font_group):
        if not text: return 0
        w = 0
        for char in text:
            f = get_char_font(char, font_group)
            w += f.getlength(char)
        return w

    title_font = load_font_group(24, bold=True)
    subtitle_font = load_font_group(16)
    card_title_font = load_font_group(15, bold=True)
    label_font = load_font_group(14)
    artist_font = load_font_group(11)
    rating_font = load_font_group(13, bold=True)
    score_font = load_font_group(15, bold=True)
    badge_font = load_font_group(11, bold=True)
    rank_font = load_font_group(48, bold=True)
    star_font = load_font_group(12) 
    exclam_font = load_font_group(18, bold=True)
    
    # 辅助绘图函数
    def draw_round_rect(x1, y1, x2, y2, radius, fill, outline=None, width=1):
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)
    
    def truncate_text(text, max_width, font_group):
        if not text: return ""
        # 逐字逼近
        current_w = 0
        res = ""
        
        # 预计算 ... 的宽度
        ellipsis = "..."
        # 假设 ... 用 Latin 或 Main 绘制
        e_font = get_char_font('.', font_group)
        e_width = e_font.getlength('.') * 3
        
        # 如果总宽度小于 max，直接返回
        total_w = get_text_width_fallback(text, font_group)
        if total_w <= max_width:
             return text
             
        for char in text:
            cw = get_char_font(char, font_group).getlength(char)
            if current_w + cw + e_width > max_width:
                return res + ellipsis
            res += char
            current_w += cw
            
        return res
    
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
            draw_text_fallback((cx-3, cy-10), "!", fill=(17, 24, 39), font_group=exclam_font) # gray-900 text
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
        draw_text_fallback((title_x, container_y1 + 20), header_title, fill=text_white, font_group=title_font)
        draw_text_fallback((title_x, container_y1 + 58), header_subtitle, fill=(156, 163, 175), font_group=subtitle_font) # gray-400
        
        # Right Stats
        # 垂直居中计算
        stat_y_start = container_y1 + 23
        
        label_w = get_text_width_fallback(stat_label, font_group=label_font)
        right_margin = container_x2 - 32
        draw_text_fallback((right_margin - label_w, stat_y_start), stat_label, fill=(156, 163, 175), font_group=label_font)
        
        stat_val_w = get_text_width_fallback(stat_value, font_group=title_font)
        draw_text_fallback((right_margin - stat_val_w, stat_y_start + 24), stat_value, fill=stat_color, font_group=title_font)

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
            rw = get_text_width_fallback(rank_num, font_group=rank_font)
            watermark_x = ix + item_width - rw + 4
            watermark_y = iy + item_height - 48
            
            txt_layer = Image.new("RGBA", (width, height), (0,0,0,0))
            txt_draw = ImageDraw.Draw(txt_layer)
            # txt_draw 需要手动调用，这里我们用自己的函数，但 target 是 txt_draw
            # 为了复用 draw_text_fallback，修改 draw_text_fallback 支持传入 draw 对象？
            # 暂时临时修改 draw_text_fallback 定义不好，直接内联或者修改函数签名
            # 让我们把 draw_text_fallback 的 draw 作为参数？
            # 由于 draw_text_fallback 使用了闭包的 draw (line 106)，我们可以临时修改它，或者复制一份逻辑
            # 最简单：增加 draw_obj 参数
            
            # 修正：上面定义的 draw_text_fallback 依赖外部 draw。
            # 为了支持这里的 txt_draw，我们需要更新 draw_text_fallback 的定义。
            # 下一次工具调用将更新定义，这里先假设它支持，或者我们手动实现
            
            # 手动实现水印绘制（简单，因为Rank是数字，肯定是 Segoe）
            # 但是为了统一，还是重构 draw_text_fallback 吧
            
            # 这里先不改 draw_text_fallback 签名，直接用旧方法？不行，我们把 measure改了
            # rank_num 只有数字，可以用 font_group[0] (Latin)
            txt_draw.text((watermark_x, watermark_y), rank_num, fill=(107, 114, 128, 50), font=rank_font[0]) 
            img.alpha_composite(txt_layer)
            
            # Title & Artist
            music_info = item.get("musicInfo") or item.get("fullMusicInfo", {}).get("music")
            music_name = music_info.get("name", f"ID: {item['musicId']}") if music_info else f"ID: {item['musicId']}"
            artist = music_info.get("artistName", "") if music_info else ""
            
            disp_title = truncate_text(music_name, info_w, card_title_font)
            draw_text_fallback((info_x, info_y), disp_title, fill=text_white, font_group=card_title_font)
            disp_artist = truncate_text(artist, info_w, artist_font)
            draw_text_fallback((info_x, info_y + 20), disp_artist, fill=text_gray, font_group=artist_font)
            
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
            
            tw = get_text_width_fallback(level_text, font_group=badge_font)
            badge_w = max(32, tw + 12)
            badge_h = 16
            badge_x1 = info_x
            badge_y1 = bottom_y - badge_h
            
            draw_round_rect(badge_x1, badge_y1, badge_x1 + badge_w, badge_y1 + badge_h, 4, badge_bg, outline=badge_border)
            draw_text_fallback((badge_x1 + (badge_w - tw) / 2, badge_y1 + 1), level_text, fill=badge_fg, font_group=badge_font)
            
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
                sw = get_text_width_fallback(score_str, font_group=score_font)
                
                # 星星在最底部右侧
                star_count = item.get("platinumScoreStar", 0)
                star_str = "★" * star_count + "☆" * (5 - star_count)
                star_w = get_text_width_fallback(star_str, font_group=star_font)
                draw_text_fallback((right_x - star_w, bottom_y - 12), "★" * star_count, fill=text_yellow, font_group=star_font)
                # 补画空心星
                filled_w = get_text_width_fallback("★" * star_count, font_group=star_font)
                draw_text_fallback((right_x - star_w + filled_w, bottom_y - 12), "☆" * (5 - star_count), fill=text_gray, font_group=star_font)
                
                # 上方是分数
                score_y = bottom_y - 28
                draw_text_fallback((right_x - sw, score_y), score_str, fill=text_purple, font_group=card_title_font)
                
                # 再上方是 Rating
                rating_val = item.get("rating", 0)
                rating_str = f"+{rating_val:.3f}"
                # 使用稍大一点的字体避免看起来扁平
                rw = get_text_width_fallback(rating_str, font_group=rating_font)
                draw_text_fallback((right_x - rw, score_y - 16), rating_str, fill=text_purple, font_group=rating_font)
                
            else:
                # 普通模式
                # 下行: Score (绿色)
                score_val = item.get("value", 0)
                score_str = f"{score_val:,}"
                sw = get_text_width_fallback(score_str, font_group=score_font)
                score_y = bottom_y - 16
                draw_text_fallback((right_x - sw, score_y), score_str, fill=text_green, font_group=score_font)
                
                # 上行: Rating (蓝色) + Bonus
                rating_val = item.get("rating", 0)
                rating_str = f"{rating_val:.2f}"
                bonus = item.get("ratingBonus", 0)
                
                rw = get_text_width_fallback(rating_str, font_group=rating_font)
                current_rx = right_x
                rating_y = score_y - 14
                
                if bonus > 0:
                    bonus_str = f"+{bonus:.2f}"
                    bw = get_text_width_fallback(bonus_str, font_group=artist_font)
                    draw_text_fallback((current_rx - bw, rating_y), bonus_str, fill=text_gray, font_group=artist_font)
                    current_rx -= (bw + 4)
                
                draw_text_fallback((current_rx - rw, rating_y - 1), rating_str, fill=text_blue, font_group=rating_font)
            
            
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
