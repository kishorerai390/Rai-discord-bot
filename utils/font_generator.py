"""
Discord Font Generator Utility.
Converts standard text into stylized Unicode Discord fonts compatible with desktop and mobile clients.
Matches styling categories from LingoJam Discord Fonts.
"""

from __future__ import annotations
from typing import Dict, List, Tuple

# Base alphanumeric ranges
LOWER_ASCII = "abcdefghijklmnopqrstuvwxyz"
UPPER_ASCII = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS_ASCII = "0123456789"

# Character transformation maps
# 1. Gothic / Fraktur (Normal)
GOTHIC_LOWER = "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷"
GOTHIC_UPPER = "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ"

# 2. Bold Gothic / Fraktur
BOLD_GOTHIC_LOWER = "𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟"
BOLD_GOTHIC_UPPER = "𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅"

# 3. Cursive / Script
SCRIPT_LOWER = "𝒶𝒷𝒸𝒹𝑒𝒻𝑔𝒽𝒾𝒿𝓀𝓁𝓂𝓃𝑜𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"
SCRIPT_UPPER = "𝒜𝐵𝒞𝒟𝐸𝐹𝒢𝐻𝐼𝒥𝒦𝐿𝑀𝒩𝒪𝒫𝒬𝑅𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵"

# 4. Bold Cursive
BOLD_SCRIPT_LOWER = "𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃"
BOLD_SCRIPT_UPPER = "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩"

# 5. Double-Struck / Blackboard
DOUBLE_STRUCK_LOWER = "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"
DOUBLE_STRUCK_UPPER = "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ"
DOUBLE_STRUCK_DIGITS = "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"

# 6. Small Caps
SMALL_CAPS_MAP = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ғ", "g": "ɢ", "h": "ʜ",
    "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ",
    "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
    "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ғ", "G": "ɢ", "H": "ʜ",
    "I": "ɪ", "J": "ᴊ", "K": "ᴋ", "L": "ʟ", "M": "ᴍ", "N": "ɴ", "O": "ᴏ", "P": "ᴘ",
    "Q": "ǫ", "R": "ʀ", "S": "s", "T": "ᴛ", "U": "ᴜ", "V": "ᴠ", "W": "ᴡ", "X": "x",
    "Y": "ʏ", "Z": "ᴢ",
}

# 7. Bubbles / Circled (White)
CIRCLED_LOWER = "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ"
CIRCLED_UPPER = "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"
CIRCLED_DIGITS = "⓪①②③④⑤⑥⑦⑧⑨"

# 8. Bubbles (Filled / Black)
FILLED_CIRCLED_UPPER = "🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩"
FILLED_CIRCLED_LOWER = "🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩"
FILLED_CIRCLED_DIGITS = "⓿➊➋➌➍➎➏➐➑➒"

# 9. Squared (Negative)
SQUARED_MAP = {
    "A": "🅰", "B": "🅱", "C": "🅲", "D": "🅳", "E": "🅴", "F": "🅵", "G": "🅶",
    "H": "🅷", "I": "🅸", "J": "🅹", "K": "🅺", "L": "🅻", "M": "🅼", "N": "🅽",
    "O": "🅾", "P": "🅿", "Q": "🆀", "R": "🆁", "S": "🆂", "T": "🆃", "U": "🆄",
    "V": "🆅", "W": "🆆", "X": "🆇", "Y": "🆈", "Z": "🆉",
    "a": "🅰", "b": "🅱", "c": "🅲", "d": "🅳", "e": "🅴", "f": "🅵", "g": "🅶",
    "h": "🅷", "i": "🅸", "j": "🅹", "k": "🅺", "l": "🅻", "m": "🅼", "n": "🅽",
    "o": "🅾", "p": "🅿", "q": "🆀", "r": "🆁", "s": "🆂", "t": "🆃", "u": "🆄",
    "v": "🆅", "w": "🆆", "x": "🆇", "y": "🆈", "z": "🆉",
}

# 10. Wide / Fullwidth (Vaporwave)
WIDE_LOWER = "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
WIDE_UPPER = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
WIDE_DIGITS = "０１２３４５６７８９"

# 11. Sans-Serif Bold
SANS_BOLD_LOWER = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"
SANS_BOLD_UPPER = "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭"
SANS_BOLD_DIGITS = "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"

# 12. Sans-Serif Italic
SANS_ITALIC_LOWER = "𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻"
SANS_ITALIC_UPPER = "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡"

# 13. Bold Italic (Serif)
BOLD_ITALIC_LOWER = "𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛"
BOLD_ITALIC_UPPER = "𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁"

# 14. Monospace
MONO_LOWER = "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"
MONO_UPPER = "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉"
MONO_DIGITS = "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"

# 15. Aesthetic / Asian Symbols
ASIAN_MAP = {
    "a": "卂", "b": "乃", "c": "匚", "d": "ᗪ", "e": "乇", "f": "千", "g": "Ꮆ",
    "h": "卄", "i": "丨", "j": "ﾌ", "k": "Ҝ", "l": "ㄥ", "m": "爪", "n": "几",
    "o": "ㄖ", "p": "卩", "q": "Ɋ", "r": "尺", "s": "丂", "t": "ㄒ", "u": "ㄩ",
    "v": "ᐯ", "w": "山", "x": "乂", "y": "ㄚ", "z": "乙",
    "A": "卂", "B": "乃", "C": "匚", "D": "ᗪ", "E": "乇", "F": "千", "G": "Ꮆ",
    "H": "卄", "I": "丨", "J": "ﾌ", "K": "Ҝ", "L": "ㄥ", "M": "爪", "N": "几",
    "O": "ㄖ", "P": "卩", "Q": "Ɋ", "R": "尺", "S": "丂", "T": "ㄒ", "U": "ㄩ",
    "V": "ᐯ", "W": "山", "X": "乂", "Y": "ㄚ", "Z": "乙",
}

# Helper to build translation table
def _build_trans(lower: str, upper: str, digits: str = "") -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    for src, dst in zip(LOWER_ASCII, lower):
        mapping[ord(src)] = dst
    for src, dst in zip(UPPER_ASCII, upper):
        mapping[ord(src)] = dst
    if digits:
        for src, dst in zip(DIGITS_ASCII, digits):
            mapping[ord(src)] = dst
    return mapping

TRANS_GOTHIC = _build_trans(GOTHIC_LOWER, GOTHIC_UPPER)
TRANS_BOLD_GOTHIC = _build_trans(BOLD_GOTHIC_LOWER, BOLD_GOTHIC_UPPER)
TRANS_SCRIPT = _build_trans(SCRIPT_LOWER, SCRIPT_UPPER)
TRANS_BOLD_SCRIPT = _build_trans(BOLD_SCRIPT_LOWER, BOLD_SCRIPT_UPPER)
TRANS_DOUBLE_STRUCK = _build_trans(DOUBLE_STRUCK_LOWER, DOUBLE_STRUCK_UPPER, DOUBLE_STRUCK_DIGITS)
TRANS_CIRCLED = _build_trans(CIRCLED_LOWER, CIRCLED_UPPER, CIRCLED_DIGITS)
TRANS_FILLED_CIRCLED = _build_trans(FILLED_CIRCLED_LOWER, FILLED_CIRCLED_UPPER, FILLED_CIRCLED_DIGITS)
TRANS_WIDE = _build_trans(WIDE_LOWER, WIDE_UPPER, WIDE_DIGITS)
TRANS_SANS_BOLD = _build_trans(SANS_BOLD_LOWER, SANS_BOLD_UPPER, SANS_BOLD_DIGITS)
TRANS_SANS_ITALIC = _build_trans(SANS_ITALIC_LOWER, SANS_ITALIC_UPPER)
TRANS_BOLD_ITALIC = _build_trans(BOLD_ITALIC_LOWER, BOLD_ITALIC_UPPER)
TRANS_MONO = _build_trans(MONO_LOWER, MONO_UPPER, MONO_DIGITS)


def transform_text(text: str, style_key: str) -> str:
    """Transforms raw text into the requested font style."""
    key = style_key.lower().strip()
    
    if key in ("gothic", "old_english"):
        return text.translate(TRANS_GOTHIC)
    elif key in ("bold_gothic", "fraktur"):
        return text.translate(TRANS_BOLD_GOTHIC)
    elif key in ("cursive", "script"):
        return text.translate(TRANS_SCRIPT)
    elif key in ("bold_cursive", "bold_script"):
        return text.translate(TRANS_BOLD_SCRIPT)
    elif key in ("double_struck", "blackboard"):
        return text.translate(TRANS_DOUBLE_STRUCK)
    elif key in ("small_caps", "smallcaps"):
        return "".join(SMALL_CAPS_MAP.get(c, c) for c in text)
    elif key in ("bubbles", "circled"):
        return text.translate(TRANS_CIRCLED)
    elif key in ("bubbles_black", "filled_circled"):
        return text.translate(TRANS_FILLED_CIRCLED)
    elif key in ("squared", "negative_box"):
        return "".join(SQUARED_MAP.get(c, c) for c in text)
    elif key in ("vaporwave", "wide"):
        # Replace normal space with fullwidth ideographic space
        res = text.translate(TRANS_WIDE)
        return res.replace(" ", "　")
    elif key in ("sans_bold", "bold"):
        return text.translate(TRANS_SANS_BOLD)
    elif key in ("sans_italic", "italic"):
        return text.translate(TRANS_SANS_ITALIC)
    elif key in ("bold_italic",):
        return text.translate(TRANS_BOLD_ITALIC)
    elif key in ("mono", "monospace", "code"):
        return text.translate(TRANS_MONO)
    elif key in ("aesthetic", "asian"):
        return "".join(ASIAN_MAP.get(c, c) for c in text)
    elif key in ("strikethrough", "strike"):
        return "".join(f"{c}\u0336" for c in text)
    elif key in ("underline", "wave"):
        return "".join(f"{c}\u0332" for c in text)
    else:
        # Default fallback
        return text


# Catalog of available styles for UI Select Menu / Autocomplete
AVAILABLE_STYLES: List[Tuple[str, str, str]] = [
    ("small_caps", "Small Caps", "Clean & aesthetic (Great for roles/channels)"),
    ("bold_gothic", "Bold Fraktur / Gothic", "Royal & medieval look"),
    ("bold_cursive", "Bold Cursive", "Elegant handwritten script"),
    ("double_struck", "Double-Struck / Blackboard", "Math/blackboard outlined style"),
    ("sans_bold", "Sans Bold", "Crisp modern bold"),
    ("bubbles", "Bubbles (Circled)", "Light circled letters"),
    ("bubbles_black", "Bubbles (Filled)", "Dark solid circled letters"),
    ("squared", "Squared Neon", "Blocky uppercase negative badges"),
    ("vaporwave", "Vaporwave / Wide", "A E S T H E T I C fullwidth spacing"),
    ("gothic", "Gothic (Normal)", "Classic Old English font"),
    ("cursive", "Cursive (Script)", "Light elegant script"),
    ("sans_italic", "Sans Italic", "Slanted modern text"),
    ("bold_italic", "Bold Italic", "Heavy slanted serif style"),
    ("mono", "Monospace", "Clean typewriter/code style"),
    ("aesthetic", "Asian Aesthetic", "Kanji/pseudo-symbol styled letters"),
    ("underline", "Underlined", "Underline decorated text"),
    ("strikethrough", "Strikethrough", "Crossed-out decorated text"),
]

# Build Reverse Unicode Font Translation Map
REVERSE_FONT_MAP: Dict[str, str] = {}
for _s, _d in zip(LOWER_ASCII, GOTHIC_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, GOTHIC_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, BOLD_GOTHIC_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, BOLD_GOTHIC_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, SCRIPT_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, SCRIPT_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, BOLD_SCRIPT_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, BOLD_SCRIPT_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, DOUBLE_STRUCK_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, DOUBLE_STRUCK_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, WIDE_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, WIDE_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, SANS_BOLD_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, SANS_BOLD_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, SANS_ITALIC_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, SANS_ITALIC_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, BOLD_ITALIC_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, BOLD_ITALIC_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in zip(LOWER_ASCII, MONO_LOWER): REVERSE_FONT_MAP[_d] = _s
for _s, _d in zip(UPPER_ASCII, MONO_UPPER): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in SMALL_CAPS_MAP.items(): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in SQUARED_MAP.items(): REVERSE_FONT_MAP[_d] = _s.lower()
for _s, _d in ASIAN_MAP.items(): REVERSE_FONT_MAP[_d] = _s.lower()


def normalize_to_ascii(text: str) -> str:
    """Normalizes stylized Unicode Discord fonts, small caps, and symbols into standard lowercase ASCII."""
    if not text:
        return ""
    converted = "".join(REVERSE_FONT_MAP.get(c, c) for c in text.lower())
    import re
    return re.sub(r"[^a-z0-9\-_]", "", converted)

