# -*- coding: utf-8 -*-
"""市场与品类配置：语言、识别参数、术语表全部数据化，代码里不写死任何语言。

设计原则（B 方案）：
  · 市场(MARKET) 决定「说什么语言」——识别语言、翻译源语言
  · 品类(CATEGORY) 决定「用什么术语」——每个术语配多语言说法
  · 换市场只换语言，加品类只加一张表，互不干扰

加新市场：在 MARKETS 里加一条。
加新品类：在 CATEGORIES 里加一条（术语按 语种 -> {葡语词: 中文} 组织）。
"""

from __future__ import annotations

# ============================================================
# 一、市场档案
# ============================================================
# locale        给界面和翻译接口用的标准语言代码
# whisper       给 Whisper 识别用的语言代码
# nllb          给 NLLB 翻译用的 FLORES-200 代码
# asr_prompt    该语种的识别提示词（塞进 Whisper 的 initial_prompt，提升专有名词准确率）
MARKETS = {
    "巴西": {
        "locale": "pt-BR",
        "whisper": "pt",
        "nllb": "por_Latn",
        "asr_prompt": (
            "parafusadeira, furadeira, chave de fenda, jogo de chaves, soquete, alicate, martelo, "
            "serra, trena, broca, esmerilhadeira, kit de ferramentas, maleta, bateria, carregador, "
            "óleo lubrificante, pastilha de freio, capacete, moto, carro, pneu, "
            "academia, camping, pesca, bicicleta, suplemento, "
            "frete grátis, cupom, promoção, desconto, carrinho amarelo, link na bio, "
            "preço exclusivo, transmissão ao vivo, seguidores, curtidas, presente"
        ),
    },
    "墨西哥": {
        "locale": "es-MX",
        "whisper": "es",
        "nllb": "spa_Latn",
        "asr_prompt": (
            "taladro, destornillador, llave inglesa, juego de dados, alicate, martillo, sierra, "
            "cinta métrica, broca, esmeriladora, caja de herramientas, batería, cargador, "
            "aceite lubricante, balatas, casco, moto, carro, llanta, "
            "gimnasio, camping, pesca, bicicleta, suplemento, "
            "envío gratis, cupón, promoción, descuento, carrito amarillo, enlace en la bio, "
            "precio exclusivo, transmisión en vivo, seguidores, me gusta, regalo"
        ),
    },
    "阿根廷": {
        "locale": "es-AR",
        "whisper": "es",
        "nllb": "spa_Latn",
        "asr_prompt": (
            "taladro, destornillador, llave, juego de dados, pinza, martillo, sierra, cinta métrica, "
            "mecha, amoladora, caja de herramientas, batería, cargador, "
            "aceite, pastillas de freno, casco, moto, auto, cubierta, "
            "gimnasio, camping, pesca, bici, suplemento, "
            "envío gratis, cupón, promoción, descuento, carrito amarillo, link en la bio, "
            "precio exclusivo, transmisión en vivo, seguidores, me gusta, regalo"
        ),
    },
    "美区": {
        "locale": "en-US",
        "whisper": "en",
        "nllb": "eng_Latn",
        "asr_prompt": (
            "power drill, screwdriver, wrench set, socket set, pliers, hammer, saw, tape measure, "
            "drill bit, angle grinder, tool box, battery, charger, "
            "motor oil, brake pads, helmet, motorcycle, car, tire, "
            "gym, camping, fishing, bike, supplement, "
            "free shipping, coupon, discount, yellow cart, link in bio, "
            "exclusive price, live stream, followers, likes, gift"
        ),
    },
    "自定义": {
        "locale": "",
        "whisper": "",
        "nllb": "",
        "asr_prompt": "",
    },
}

# 界面下拉里可选的所有识别语言（Whisper 语言代码 -> 显示名）
WHISPER_LANGS = {
    "pt": "葡萄牙语",
    "es": "西班牙语",
    "en": "英语",
    "zh": "中文",
    "fr": "法语",
    "de": "德语",
    "it": "意大利语",
    "ja": "日语",
    "ko": "韩语",
    "ru": "俄语",
    "ar": "阿拉伯语",
    "hi": "印地语",
    "id": "印尼语",
    "th": "泰语",
    "vi": "越南语",
    "tr": "土耳其语",
    "nl": "荷兰语",
    "pl": "波兰语",
}

# 翻译目标语言（界面下拉）：显示名 -> 标准代码
TARGET_LANGS = {
    "中文": "zh-CN",
    "英文": "en",
    "西班牙语": "es",
    "葡萄牙语": "pt",
    "日语": "ja",
    "韩语": "ko",
}


# ============================================================
# 二、品类术语表
# ============================================================
# 结构：品类 -> { 语种: {该语种的说法: 标准中文} }
# 说明：识别提示词负责"让模型听对"，术语表负责"把译错的改对"。
CATEGORIES = {
    "五金工具": {
        "pt": {
            "parafusadeira": "电动螺丝刀", "furadeira": "电钻",
            "chave de fenda": "一字螺丝刀", "jogo de chaves": "扳手套装",
            "jogo de soquetes": "套筒套装", "soquete": "套筒", "alicate": "钳子",
            "martelo": "锤子", "trena": "卷尺", "broca": "钻头",
            "esmerilhadeira": "角磨机", "serra circular": "圆锯",
            "kit de ferramentas": "工具套装", "maleta": "工具箱",
            "bateria": "电池", "carregador": "充电器",
        },
        "es": {
            "taladro": "电钻", "destornillador": "螺丝刀",
            "llave inglesa": "活动扳手", "juego de dados": "套筒套装",
            "dado": "套筒", "alicate": "钳子", "pinza": "钳子",
            "martillo": "锤子", "cinta métrica": "卷尺", "broca": "钻头",
            "mecha": "钻头", "amoladora": "角磨机", "esmeriladora": "角磨机",
            "sierra circular": "圆锯", "caja de herramientas": "工具箱",
            "batería": "电池", "cargador": "充电器",
        },
        "en": {
            "power drill": "电钻", "drill": "电钻", "screwdriver": "螺丝刀",
            "wrench set": "扳手套装", "socket set": "套筒套装", "socket": "套筒",
            "pliers": "钳子", "hammer": "锤子", "tape measure": "卷尺",
            "drill bit": "钻头", "angle grinder": "角磨机", "circular saw": "圆锯",
            "tool box": "工具箱", "toolbox": "工具箱", "battery": "电池",
            "charger": "充电器",
        },
    },
    "汽车与摩托": {
        "pt": {
            "óleo lubrificante": "润滑油", "óleo de motor": "机油",
            "pastilha de freio": "刹车片", "filtro de óleo": "机油滤芯",
            "filtro de ar": "空气滤芯", "vela de ignição": "火花塞",
            "pneu": "轮胎", "corrente": "链条", "capacete": "头盔",
            "retrovisor": "后视镜", "farol": "车灯", "buzina": "喇叭",
            "bomba de ar": "充气泵", "suporte de celular": "手机支架",
            "capa de chuva": "雨衣", "luvas": "手套",
        },
        "es": {
            "aceite lubricante": "润滑油", "aceite de motor": "机油",
            "pastillas de freno": "刹车片", "balatas": "刹车片",
            "filtro de aceite": "机油滤芯", "filtro de aire": "空气滤芯",
            "bujía": "火花塞", "llanta": "轮胎", "neumático": "轮胎",
            "cadena": "链条", "casco": "头盔", "espejo retrovisor": "后视镜",
            "faro": "车灯", "bocina": "喇叭", "bomba de aire": "充气泵",
            "soporte para celular": "手机支架", "impermeable": "雨衣", "guantes": "手套",
        },
        "en": {
            "motor oil": "机油", "engine oil": "机油", "brake pads": "刹车片",
            "oil filter": "机油滤芯", "air filter": "空气滤芯",
            "spark plug": "火花塞", "tire": "轮胎", "tyre": "轮胎",
            "chain": "链条", "helmet": "头盔", "side mirror": "后视镜",
            "headlight": "车灯", "horn": "喇叭", "air pump": "充气泵",
            "phone mount": "手机支架", "raincoat": "雨衣", "gloves": "手套",
        },
    },
    "运动与户外": {
        "pt": {
            "academia": "健身房", "haltere": "哑铃", "barra": "杠铃",
            "faixa elástica": "弹力带", "tapete de yoga": "瑜伽垫",
            "bola": "球", "cordas de pular": "跳绳", "whey protein": "乳清蛋白",
            "suplemento": "保健品", "barraca": "帐篷", "saco de dormir": "睡袋",
            "lanterna": "手电筒", "vara de pesca": "鱼竿", "mochila": "背包",
            "bicicleta": "自行车", "capacete de bicicleta": "自行车头盔",
            "garrafa térmica": "保温杯",
        },
        "es": {
            "gimnasio": "健身房", "mancuerna": "哑铃", "barra": "杠铃",
            "banda elástica": "弹力带", "tapete de yoga": "瑜伽垫",
            "pelota": "球", "cuerda para saltar": "跳绳", "proteína whey": "乳清蛋白",
            "suplemento": "保健品", "carpa": "帐篷", "bolsa de dormir": "睡袋",
            "linterna": "手电筒", "caña de pescar": "鱼竿", "mochila": "背包",
            "bicicleta": "自行车", "casco de bicicleta": "自行车头盔",
            "termo": "保温杯",
        },
        "en": {
            "gym": "健身房", "dumbbell": "哑铃", "barbell": "杠铃",
            "resistance band": "弹力带", "yoga mat": "瑜伽垫",
            "ball": "球", "jump rope": "跳绳", "whey protein": "乳清蛋白",
            "supplement": "保健品", "tent": "帐篷", "sleeping bag": "睡袋",
            "flashlight": "手电筒", "fishing rod": "鱼竿", "backpack": "背包",
            "bicycle": "自行车", "bike helmet": "自行车头盔",
            "tumbler": "保温杯",
        },
    },
    "通用": {},   # 不加载任何术语表
}


# ============================================================
# 三、查询接口
# ============================================================
def get_market(name: str) -> dict:
    """取市场档案；未知市场返回自定义档。"""
    return MARKETS.get(name, MARKETS["自定义"])


def get_glossary(category: str, whisper_lang: str) -> dict:
    """取某品类在某语种下的术语表 {原文: 中文}。"""
    cat = CATEGORIES.get(category) or {}
    return dict(cat.get(whisper_lang, {}))


# 直播通用词：跟具体品类无关，主播天天说的那些。
# 以前这些词混在 MARKETS[..]["asr_prompt"] 里，等于任何品类都带着其它品类的词。
LIVE_PHRASES = {
    "pt": ("frete grátis, cupom, promoção, desconto, carrinho amarelo, link na bio, "
           "preço exclusivo, transmissão ao vivo, seguidores, curtidas, presente"),
    "es": ("envío gratis, cupón, promoción, descuento, carrito amarillo, enlace en la bio, "
           "precio exclusivo, transmisión en vivo, seguidores, me gusta, regalo"),
    "en": ("free shipping, coupon, promotion, discount, yellow cart, link in bio, "
           "exclusive price, live stream, followers, likes, gift"),
}


def get_asr_prompt(category: str, whisper_lang: str) -> str:
    """拼某品类在某语种下的识别提示词（塞进 Whisper 的 initial_prompt）。

    只用**当前品类**的术语 + 跟品类无关的直播通用词。

    以前直接用市场级的 asr_prompt，那是四个品类的词全混在一起（427 字符）：
    卖五金工具时提示词里却有 moto / carro / pneu / academia / camping / pesca。
    Whisper 的 initial_prompt 会强烈带偏解码，混进无关品类词容易识别出主播
    根本没说的词（实测直播字幕里出现过"山羊""大使馆""牛奶"这类凭空冒出来的词）。
    """
    terms = [t for t in get_glossary(category, whisper_lang) if t]
    generic = LIVE_PHRASES.get(whisper_lang, "")
    if generic:
        terms.append(generic)
    return ", ".join(terms)


# 反向翻译专用别名：有些中文说法在目标语言里没有独立单词，正向术语表因此没有它，
# 但做「中文 -> 外文」的回复时需要。只作用于回复助手方向，不影响正向识别与翻译。
#   es：西语里"电动螺丝刀"和"电钻"都叫 taladro（正向表把 taladro 记作"电钻"）
REVERSE_ALIAS = {
    "es": {"电动螺丝刀": "taladro"},
    "en": {"电动螺丝刀": "power drill"},
}


def get_reverse_glossary(category: str, whisper_lang: str) -> dict:
    """把术语表反过来：{标准中文: 该语种的说法}，供「中文 -> 外文」的回复翻译用。

    一个中文词可能对应多个外文说法（例如西语里 alicate 和 pinza 都是"钳子"），
    取术语表里先出现的那个；该语种没有独立说法的词由 REVERSE_ALIAS 补上。
    """
    out: dict[str, str] = {}
    cat = CATEGORIES.get(category) or {}
    for foreign, cn in (cat.get(whisper_lang) or {}).items():
        if cn and foreign:
            out.setdefault(cn, foreign)
    for cn, foreign in REVERSE_ALIAS.get(whisper_lang, {}).items():
        out.setdefault(cn, foreign)
    return out


def market_names() -> list[str]:
    return list(MARKETS.keys())


def category_names() -> list[str]:
    return list(CATEGORIES.keys())


if __name__ == "__main__":
    print("=== 市场 ===")
    for name, m in MARKETS.items():
        print(f"  {name:6s} locale={m['locale']:6s} whisper={m['whisper']:3s} nllb={m['nllb']}")
    print("\n=== 品类术语数量 ===")
    for cat, langs in CATEGORIES.items():
        detail = ", ".join(f"{k}:{len(v)}条" for k, v in langs.items()) or "（无）"
        print(f"  {cat:10s} {detail}")
    print("\n=== 抽样 ===")
    for cat in ("五金工具", "汽车与摩托", "运动与户外"):
        print(f"  [{cat}] 葡语 parafusadeira/taladro 类:")
        for lang in ("pt", "es", "en"):
            g = get_glossary(cat, lang)
            sample = list(g.items())[:3]
            print(f"    {lang}: {sample}")
