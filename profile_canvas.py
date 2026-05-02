import io
import logging
import os
import re
from typing import Any, Dict, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

logger = logging.getLogger(__name__)


async def generate_profile_canvas_image(
    output_path: str,
    profile: Dict[str, Any],
    api_client=None,
) -> str:
    if Image is None:
        raise RuntimeError("Pillow 未安装，无法绘制图片，请安装 pillow 再试。")

    width = 1600
    height = 1280
    padding = 48

    bg = Image.new("RGBA", (width, height), (248, 250, 252, 255))
    draw = ImageDraw.Draw(bg)

    colors = {
        "bg": (248, 250, 252),
        "card": (255, 255, 255),
        "text": (17, 24, 39),
        "subtle": (107, 114, 128),
        "line": (229, 231, 235),
        "blue": (37, 99, 235),
        "green": (22, 163, 74),
        "orange": (234, 88, 12),
        "purple": (147, 51, 234),
        "red": (220, 38, 38),
        "cyan": (8, 145, 178),
    }

    plugin_dir = os.path.dirname(__file__)
    fonts_dir = os.path.join(plugin_dir, "assets", "fonts")

    def load_font_candidates(paths, size: int):
        for path in paths:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return None

    def load_font_pair(size: int, bold: bool = False):
        latin_paths = [os.path.join(fonts_dir, "segoeuib.ttf" if bold else "segoeui.ttf")]
        cjk_paths = [
            os.path.join(fonts_dir, "BIZ-UDGothicB.ttc" if bold else "BIZ-UDGOTHICR.TTC"),
            os.path.join(fonts_dir, "msgothic.ttc"),
        ]
        latin_font = load_font_candidates(latin_paths, size)
        cjk_font = load_font_candidates(cjk_paths, size)
        fallback = ImageFont.load_default()
        return (latin_font or cjk_font or fallback, cjk_font or latin_font or fallback)

    title_font = load_font_pair(42, bold=True)
    subtitle_font = load_font_pair(20)
    h1_font = load_font_pair(34, bold=True)
    h2_font = load_font_pair(22, bold=True)
    body_font = load_font_pair(18)
    small_font = load_font_pair(15)
    stat_value_font = load_font_pair(44, bold=True)
    rating_font = load_font_pair(52, bold=True)
    signature_font = load_font_pair(22)

    def round_rect(box, radius=18, fill=None, outline=None, width_=1):
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width_)

    def pick_font(font_pair, value: str):
        text_value = str(value)
        if re.search(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]", text_value):
            return font_pair[1]
        return font_pair[0]

    def text(xy, value, font_pair, fill, anchor="la"):
        draw.text(xy, str(value), font=pick_font(font_pair, value), fill=fill, anchor=anchor)

    def wrap_text(value: str, font_pair, max_width: int, max_lines: int = 2):
        words = []
        current = ""
        target_font = pick_font(font_pair, value)
        for ch in value:
            candidate = current + ch
            if draw.textlength(candidate, font=target_font) <= max_width:
                current = candidate
                continue
            if current:
                words.append(current)
            current = ch
            if len(words) >= max_lines:
                break
        if current and len(words) < max_lines:
            words.append(current)
        if len(words) == max_lines and "".join(words) != value:
            last = words[-1]
            while last and draw.textlength(last + "...", font=target_font) > max_width:
                last = last[:-1]
            words[-1] = last + "..."
        return words

    def format_rating() -> Tuple[str, str]:
        new_rating = profile.get("newPlayerRating")
        new_highest = profile.get("newHighestRating")
        current = f"{new_rating / 1000:.3f}" if new_rating else f"{profile.get('playerRating', 0) / 100:.2f}"
        highest = f"{new_highest / 1000:.3f}" if new_highest else f"{profile.get('highestRating', 0) / 100:.2f}"
        return current, highest

    def get_level_exp_requirement(level: int) -> int:
        if 0 <= level <= 9:
            return 200
        if 10 <= level <= 19:
            return 400
        if 20 <= level <= 29:
            return 600
        if 30 <= level <= 39:
            return 800
        if 40 <= level <= 49:
            return 1000
        if 50 <= level <= 59:
            return 1200
        if 60 <= level <= 69:
            return 1400
        if 70 <= level <= 79:
            return 1600
        if 80 <= level <= 89:
            return 1800
        return 2000

    def get_exp_progress() -> Tuple[int, int, float]:
        level = min(int(profile.get("level", 0) or 0), 99)
        total_exp = int(profile.get("exp", 0) or 0)
        used = 0
        for lv in range(level):
            used += get_level_exp_requirement(lv)
        current_exp = max(0, total_exp - used)
        required = get_level_exp_requirement(level)
        current_exp = min(current_exp, required)
        progress = current_exp / required if required else 0
        return current_exp, required, progress

    async def fetch_image(url: str, fallback_size: Tuple[int, int], contain: bool = False) -> Image.Image:
        try:
            if not api_client:
                raise RuntimeError("api_client unavailable")
            raw = await api_client.download_image(url, timeout=12)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            if contain:
                img.thumbnail(fallback_size, Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", fallback_size, (0, 0, 0, 0))
                x = (fallback_size[0] - img.width) // 2
                y = (fallback_size[1] - img.height) // 2
                canvas.paste(img, (x, y), img)
                return canvas
            return img.resize(fallback_size, Image.Resampling.LANCZOS)
        except Exception as exc:
            logger.warning("[Profile绘图] 下载图片失败 %s: %s", url, exc)
            placeholder = Image.new("RGBA", fallback_size, (229, 231, 235, 255))
            pd = ImageDraw.Draw(placeholder)
            pd.rounded_rectangle((0, 0, fallback_size[0] - 1, fallback_size[1] - 1), radius=18, outline=(209, 213, 219), width=2)
            pd.line((0, 0, fallback_size[0], fallback_size[1]), fill=(209, 213, 219), width=3)
            pd.line((fallback_size[0], 0, 0, fallback_size[1]), fill=(209, 213, 219), width=3)
            return placeholder

    card_id = int(profile.get("cardId", 0) or 0)
    padded_card_id = str(card_id).zfill(6)
    avatar_url = f"{api_client.cdn_base_url}/web/assets/ongeki/card/UI_Card_Icon_{padded_card_id}.webp" if api_client else ""
    chara_url = f"{api_client.cdn_base_url}/web/assets/ongeki/card/UI_Card_Chara_{padded_card_id}.webp" if api_client else ""

    avatar = await fetch_image(avatar_url, (96, 96))
    chara = await fetch_image(chara_url, (320, 520), contain=True)

    text((padding, 60), "个人资料", title_font, colors["text"])
    text((padding, 102), "查看您的游戏资料", subtitle_font, colors["subtle"])

    main_card = (padding, 140, width - padding, 700)
    round_rect(main_card, radius=28, fill=colors["card"], outline=(226, 232, 240), width_=2)

    chara_panel = (width - padding - 360, 160, width - padding - 28, 672)
    round_rect(chara_panel, radius=24, fill=(243, 244, 246), outline=(229, 231, 235))
    bg.paste(chara, (chara_panel[0] + (chara_panel[2] - chara_panel[0] - chara.width) // 2, chara_panel[1] + (chara_panel[3] - chara_panel[1] - chara.height) // 2), chara)

    header_x = padding + 36
    header_y = 190
    content_right = chara_panel[0] - 36
    text((header_x, header_y), profile.get("userName", "Unknown"), h1_font, colors["text"])

    avatar_x = header_x
    avatar_y = 254
    avatar_box = (avatar_x, avatar_y, avatar_x + 96, avatar_y + 96)
    round_rect(avatar_box, radius=18, outline=(209, 213, 219), width_=2)
    bg.paste(avatar, (avatar_x, avatar_y), avatar)

    exp_x = avatar_x + 124
    exp_y = avatar_y + 8
    current_exp, required_exp, progress = get_exp_progress()
    text((exp_x, exp_y), "经验值", body_font, colors["subtle"])
    text((content_right, exp_y), f"{current_exp}/{required_exp}", small_font, colors["subtle"], anchor="ra")
    bar_box = (exp_x, exp_y + 32, content_right, exp_y + 50)
    round_rect(bar_box, radius=8, fill=(229, 231, 235))
    fill_width = int((bar_box[2] - bar_box[0]) * progress)
    if fill_width > 0:
        draw.rounded_rectangle((bar_box[0], bar_box[1], bar_box[0] + fill_width, bar_box[3]), radius=8, fill=colors["blue"])

    current_rating, highest_rating = format_rating()
    section_top = 390
    section_gap = 18
    rating_box_w = 530
    rating_box = (header_x, section_top, header_x + rating_box_w, section_top + 138)
    round_rect(rating_box, radius=22, fill=(239, 242, 255))
    text((rating_box[0] + 28, rating_box[1] + 24), "当前评分", h2_font, colors["text"])
    text((rating_box[0] + 28, rating_box[1] + 92), current_rating, rating_font, colors["blue"])
    text((rating_box[0] + 295, rating_box[1] + 98), f"(最高: {highest_rating})", body_font, colors["subtle"])

    stat_top = section_top
    stats_x = rating_box[2] + section_gap
    stat_area_w = content_right - stats_x
    stat_gap = 14
    stat_w = (stat_area_w - stat_gap * 2) // 3
    stat_h = 138
    stats = [
        ("等级", profile.get("level", 0), (239, 246, 255), colors["blue"]),
        ("游玩次数", f"{int(profile.get('playCount', 0) or 0):,}", (240, 253, 244), colors["green"]),
        ("排名", f"#{profile.get('userRanking', 'N/A')}", (255, 247, 237), colors["orange"]),
    ]
    for idx, (label, value, fill, accent) in enumerate(stats):
        x1 = stats_x + idx * (stat_w + stat_gap)
        box = (x1, stat_top, x1 + stat_w, stat_top + stat_h)
        round_rect(box, radius=20, fill=fill)
        text((x1 + stat_w / 2, stat_top + 58), value, stat_value_font, accent, anchor="ma")
        text((x1 + stat_w / 2, stat_top + 110), label, body_font, colors["subtle"], anchor="ma")

    tech_card = (padding, 736, width - padding, 1030)
    round_rect(tech_card, radius=28, fill=colors["card"], outline=(226, 232, 240), width_=2)
    text((padding + 36, 778), "技术分统计", h2_font, colors["text"])

    def avg_score(sum_key: str, cnt_key: str) -> str:
        score = int(profile.get(sum_key, 0) or 0)
        count = int(profile.get(cnt_key, 0) or 0)
        if count <= 0:
            return "0"
        return f"{score // count:,}"

    tech_items = [
        ("Basic", avg_score("sumTechBasicHighScore", "playedMusicCountBasic"), int(profile.get("playedMusicCountBasic", 0) or 0), (240, 253, 244), colors["green"]),
        ("Advanced", avg_score("sumTechAdvancedHighScore", "playedMusicCountAdvanced"), int(profile.get("playedMusicCountAdvanced", 0) or 0), (255, 251, 235), (202, 138, 4)),
        ("Expert", avg_score("sumTechExpertHighScore", "playedMusicCountExpert"), int(profile.get("playedMusicCountExpert", 0) or 0), (253, 242, 248), colors["red"]),
        ("Master", avg_score("sumTechMasterHighScore", "playedMusicCountMaster"), int(profile.get("playedMusicCountMaster", 0) or 0), (250, 245, 255), colors["purple"]),
        ("Lunatic", avg_score("sumTechLunaticHighScore", "playedMusicCountLunatic"), int(profile.get("playedMusicCountLunatic", 0) or 0), (254, 242, 242), colors["red"]),
        ("Total", avg_score("sumTechHighScore", "playedMusicCountTotal"), int(profile.get("playedMusicCountTotal", 0) or 0), (236, 254, 255), colors["cyan"]),
    ]

    grid_x = padding + 36
    grid_y = 830
    grid_gap_x = 18
    grid_gap_y = 16
    cell_w = (width - padding * 2 - 72 - grid_gap_x * 2) // 3
    cell_h = 86
    for idx, (label, score, songs, fill, accent) in enumerate(tech_items):
        row = idx // 3
        col = idx % 3
        x1 = grid_x + col * (cell_w + grid_gap_x)
        y1 = grid_y + row * (cell_h + grid_gap_y)
        box = (x1, y1, x1 + cell_w, y1 + cell_h)
        round_rect(box, radius=18, fill=fill)
        text((x1 + cell_w / 2, y1 + 26), score, h2_font, accent, anchor="ma")
        text((x1 + cell_w / 2, y1 + 50), label, small_font, colors["subtle"], anchor="ma")
        text((x1 + cell_w / 2, y1 + 70), f"{songs} 首", small_font, colors["subtle"], anchor="ma")

    sign_card = (padding, 1066, width - padding, 1210)
    round_rect(sign_card, radius=28, fill=colors["card"], outline=(226, 232, 240), width_=2)
    text((padding + 36, 1108), "个性签名", h2_font, colors["text"])
    signature = (profile.get("profileContent") or "").strip() or "这个玩家还没有设置个性签名。"
    sig_box = (padding + 36, 1140, width - padding - 36, 1188)
    round_rect(sig_box, radius=16, fill=(249, 250, 251))
    wrapped_signature = wrap_text(signature, signature_font, sig_box[2] - sig_box[0] - 44, max_lines=2)
    for idx, line in enumerate(wrapped_signature):
        text((sig_box[0] + 22, sig_box[1] + 24 + idx * 26), line, signature_font, (55, 65, 81))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bg.convert("RGB").save(output_path, quality=95)
    return output_path
