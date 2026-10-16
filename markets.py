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
            # 下面这些是拿真实直播录音（tmp\cap.wav）对照补的：
            # 术语表里有的词全听对了，不在表里的被听歪 ——
            #   sextavados  -> "sexta, vados"
            #   philips e fenda -> "filhos de fenda"
            # （提示词就是由本表拼出来的，所以补到这里等于同时喂给识别模型）
            "sextavado": "内六角", "chave philips": "十字螺丝刀",
            "philips": "十字", "fenda": "一字螺丝刀",
            "martelete": "电锤", "ponteira": "批头", "adaptador": "转接头",
            "parafuso": "螺丝", "porca": "螺母", "arruela": "垫圈",
            "chave inglesa": "活动扳手", "nível": "水平尺", "estilete": "美工刀",
            "lixadeira": "砂光机", "serra tico-tico": "曲线锯",
            "bivolt": "双电压", "voltagem": "电压",
            "espelho": "镜子", "quadro": "画框", "móveis": "家具",
            "montar": "组装", "desmontar": "拆卸",
            # 巴西直播口语（2026-10 拿真实直播回放补的）：
            # 这些词以前被音译成"博拉/加莱拉"或者根本不翻，译文读不懂。
            # 补进术语表有两个作用：1) 拼进识别提示词，模型更容易听对；
            # 2) 触发 TERM_FIXES 修掉在线接口的错译。
            "bora": "来吧", "galera": "大家", "pessoal": "各位",
            "oferta": "优惠", "promoção": "促销", "desconto": "折扣",
            "aproveita": "抓紧", "oportunidade": "机会",
            "últimas unidades": "最后几件", "unidades disponíveis": "现货",
            "finaliza a compra": "下单", "leva o kit para casa": "把套装带回家",
            "preço de barbada": "白菜价", "carrinho amarelo": "黄色购物车",
            "frete": "运费",
            # 注：cupom 归 LIVE_GLOSSARY（市场层）。这里别再登记 ——
            # get_glossary() 是「市场层先、品类层后 update」，品类层同名会覆盖市场层，
            # 重复登记会让市场层的译法悄悄失效（实测踩过）。
            # 注：TERM_FIXES 的键必须同时出现在术语表里才会触发修正，
            # 所以下面这几个"动作词"也要登记（现场被译成"将刺/会刺"）。
            "furar": "钻孔", "furando": "在钻孔",
            "parafusar": "拧螺丝", "montar": "组装", "desmontar": "拆卸",
            "três oitavos": "3/8 英寸",
            # 2026-10 第二场真实直播（medium 模型）回放补的：这些口语词
            # 模型已经听得对了，但在线接口逐字直译，中文读着别扭。
            "top demais": "太棒了", "luz": "灯",
            "aproveita e leva": "抓紧下单带走",
        },
        "es": {
            "taladro": "电钻", "destornillador": "螺丝刀",
            "llave inglesa": "活动扳手", "juego de dados": "套筒套装",
            "dado": "套筒", "alicate": "钳子", "pinza": "钳子",
            "martillo": "锤子", "cinta métrica": "卷尺", "broca": "钻头",
            "mecha": "钻头", "amoladora": "角磨机", "esmeriladora": "角磨机",
            "sierra circular": "圆锯", "caja de herramientas": "工具箱",
            "batería": "电池", "cargador": "充电器",
            # 与葡语表对齐补齐（同一批品类的常见说法）
            "llave de dado": "套筒扳手", "desarmador": "螺丝刀",
            "destornillador de estrella": "十字螺丝刀", "phillips": "十字",
            "plana": "一字", "rotomartillo": "电锤", "punta": "批头",
            "adaptador": "转接头", "tornillo": "螺丝", "tuerca": "螺母",
            "rondana": "垫圈", "nivel": "水平尺", "cúter": "美工刀",
            "lijadora": "砂光机", "caladora": "曲线锯",
            "bivolt": "双电压", "voltaje": "电压",
            "espejo": "镜子", "cuadro": "画框", "muebles": "家具",
            "armar": "组装", "desarmar": "拆卸",
        },
        "en": {
            "power drill": "电钻", "drill": "电钻", "screwdriver": "螺丝刀",
            "wrench set": "扳手套装", "socket set": "套筒套装", "socket": "套筒",
            "pliers": "钳子", "hammer": "锤子", "tape measure": "卷尺",
            "drill bit": "钻头", "angle grinder": "角磨机", "circular saw": "圆锯",
            "tool box": "工具箱", "toolbox": "工具箱", "battery": "电池",
            "charger": "充电器",
            # 与葡语/西语表对齐补齐
            "hex socket": "内六角套筒", "phillips": "十字",
            "flathead": "一字", "hammer drill": "电锤", "bit": "批头",
            "adapter": "转接头", "screw": "螺丝", "nut": "螺母",
            "washer": "垫圈", "level": "水平尺", "utility knife": "美工刀",
            "sander": "砂光机", "jigsaw": "曲线锯",
            "voltage": "电压", "mirror": "镜子", "picture frame": "画框",
            "furniture": "家具", "assemble": "组装", "disassemble": "拆卸",
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


# ============================================================
# 市场/平台通用术语（不分品类）
# ============================================================
# 2026-10 补：原来只有品类词（五金工具），缺"支付 / 物流清关 / 营销逼单 / 评论区情绪"
# 这一层，而巴西直播间天天说这些，传统机翻基本全错（Pix→像素、Taxado→税、
# Remessa Conforme 翻不出来）。词表来源：外部建议（已逐条核对译法，纠正了
# "Calote→杀猪盘"、"Decepcionado→拔草"这类错译）+ 我们两场真实直播字幕的频次统计。
LIVE_GLOSSARY = {
    "pt": {
        # —— 支付（Pix / Boleto 是巴西特有，机翻必错）——
        "pix": "Pix 秒付", "boleto": "线下现金支付单",
        "parcelado": "分期付款", "parcelas": "分期", "sem juros": "免息",
        "reembolso": "退款", "cartão de crédito": "信用卡支付", "à vista": "全款",
        # —— 物流与清关（巴西跨境最痛的点）——
        "frete grátis": "包邮", "taxado": "被海关税了", "taxa": "税费",
        "remessa conforme": "巴西合规计划", "rastreio": "物流单号",
        "código de rastreio": "追踪码", "esgotado": "售罄",
        "despachado": "已发货", "retido na alfândega": "卡在海关",
        "correios": "巴西邮政", "devolução": "退货",
        "pronta entrega": "现货秒发", "sob encomenda": "预售",
        "últimas unidades": "最后几件", "unidades disponíveis": "现货",
        # —— 营销与逼单（译法按"带货味"走：中文直播间的说法，不是书面语）——
        "queima de estoque": "清仓大甩卖", "cupom": "优惠券/羊毛券",
        "metade do preço": "半价", "só hoje": "仅限今天/破价一天",
        "brindes": "赠品", "mimos": "宠粉福利", "oferta relâmpago": "限时秒杀",
        "golpe": "骗局/割韭菜", "garantia": "保修", "não perca": "别错过",
        "tchau": "再见", "vale a pena": "值得买/绝对值/性价比高",
        # —— 评论区情绪（用来判断弹幕风向）——
        # ⚠️ 这里用中文网络热语，**多选项用"/"分隔是故意的**，因为：
        #   · LLM 通道（System Prompt）会按上下文挑一个合适的 —— 多选项是优点；
        #   · 但 replace 式术语修正会把整串**原样插进字幕**（"杀猪盘/骗子店/老赖"），
        #     所以这几条**不要**再加 TERM_FIXES 规则，除非改成单一译法。
        "falso": "假货/一眼假", "réplica": "仿品",
        "calote": "杀猪盘/骗子店/老赖", "caloteiro": "骗子店/老赖",
        "reclame aqui": "投诉维权网（等同 315 曝光）",
        "decepcionado": "踩雷了/拔草了/避坑", "decepção": "踩雷/翻车",
        "perfeito": "太神了/闭眼入/绝绝子", "maravilhoso": "太神了/闭眼入/绝绝子",
        # —— 流量与互动 ——
        "for you": "推荐页", "para você": "推荐页", "flopou": "没流量",
        "viralizou": "爆了", "seguidor": "粉丝", "seguidores": "粉丝",
        "compartilha": "分享", "tap tap na tela": "点赞",
        # —— 规格与配件（真实字幕里的高频词）——
        "bits": "批头", "torque": "扭矩", "potência": "功率",
        "watts": "瓦", "volts": "伏", "acessórios": "配件",
        "extensor": "延长杆", "sockets": "套筒", "tela": "屏幕",
        "mandril": "夹头", "uso prolongado": "长时间使用",
    },
    "es": {
        "envío gratis": "包邮", "cupón": "优惠券", "descuento": "折扣",
        "promoción": "促销", "precio exclusivo": "专属价",
        "transmisión en vivo": "直播", "carrito amarillo": "小黄车",
        "enlace en la bio": "主页链接", "agotado": "售罄",
        "reembolso": "退款", "sin intereses": "免息",
        "meses sin intereses": "免息分期", "parcelas": "分期",
        "garantía": "保修", "envío": "运费", "seguidores": "粉丝",
        "me gusta": "点赞", "regalo": "赠品", "torque": "扭矩",
        "potencia": "功率", "vatios": "瓦", "accesorios": "配件",
    },
}


def get_glossary(category: str, whisper_lang: str) -> dict:
    """取某品类在某语种下的术语表 {原文: 中文}。

    两层合并：市场通用词（LIVE_GLOSSARY）+ 品类词（CATEGORIES，同名时覆盖）。
    """
    out = dict(LIVE_GLOSSARY.get(whisper_lang, {}))
    cat = CATEGORIES.get(category) or {}
    out.update(cat.get(whisper_lang, {}))
    return out


# ============================================================
# 识别提示词（Whisper initial_prompt）—— 有硬预算，单独控制
# ============================================================
# Whisper 的 initial_prompt 上限是 223 token（faster-whisper: max_length//2 - 1），
# 而且**超长时保留结尾、丢掉开头**：
#     prompt.extend(previous_tokens[-(self.max_length // 2 - 1):])   # get_prompt()
#
# 2026-10 实测踩坑：术语从 38 条加到 61 条后，提示词涨到 298 token，
# 开头那批最重要的工具词（furadeira / maleta / broca / sextavado）**被静默丢掉** ——
# 而真实直播里它们恰好被听错：furadeira→fideira/fuzadeira、maleta→malzinha、
# broca→blocas、sextavado→estavado。后加的（在尾部）bora/galera/oferta 反而全对。
#
# 结论：**重要的词必须放最后**；并且按预算裁剪（从最不重要的开始丢）。
# 普通词不要放进来 —— 模型自己听得出来，别浪费预算。
ASR_PROMPT_CHAR_BUDGET = 500      # ≈180 token（实测 843 字符 = 298 token，约 2.83 字符/token）

# 按重要性**从低到高**排列（越靠后越重要，因为截断保尾）。
ASR_PROMPT_PRIORITY = {
    "pt": [
        # —— 最不重要（预算不够时先丢这些）——
        "curtidas", "seguidores", "presente", "compartilha", "seguidor",
        "link na bio", "cupom", "desconto", "promoção", "oferta",
        "oportunidade", "aproveita", "bora", "galera", "pessoal",
        "garantia", "não perca", "finaliza a compra", "leva o kit para casa",
        "carrinho amarelo", "preço de barbada", "top demais", "transmissão ao vivo",
        # —— 规格与配件 ——
        "bivolt", "voltagem", "potência", "torque", "bits", "acessórios",
        "extensor", "adaptador", "ponteira", "nível", "trena",
        # —— 最容易听错的工具词（必须保住，放最后）——
        "serra circular", "esmerilhadeira", "parafusadeira", "furadeira",
        "sextavado", "mandril", "martelete", "chave philips", "philips",
        "chave de fenda", "fenda", "soquete", "alicate", "bateria",
        "carregador", "maleta", "kit de ferramentas", "broca",
    ],
    "es": [
        "me gusta", "seguidores", "regalo", "enlace en la bio", "cupón",
        "descuento", "promoción", "envío gratis", "precio exclusivo",
        "transmisión en vivo", "taladro", "destornillador", "amoladora",
        "llave inglesa", "juego de dados", "martillo", "cinta métrica",
        "broca", "mecha", "batería", "cargador", "caja de herramientas",
    ],
}


def _asr_prompt_terms(category: str, whisper_lang: str) -> tuple[list, list]:
    """按优先级挑词并裁到预算内；返回 (保留的词, 被丢的词)。"""
    prio = list(ASR_PROMPT_PRIORITY.get(whisper_lang, []))
    if not prio:                       # 没配置的语言退回旧行为
        return [t for t in get_glossary(category, whisper_lang) if t], []
    gl = get_glossary(category, whisper_lang)
    terms = [t for t in prio if t in gl]
    dropped = []
    while len(", ".join(terms)) > ASR_PROMPT_CHAR_BUDGET and terms:
        dropped.append(terms.pop(0))   # 从列表头丢 = 丢最不重要的
    return terms, dropped


def asr_prompt_stats(category: str, whisper_lang: str) -> dict:
    """给测试/自检用：提示词多长、几条、丢了哪些。"""
    used, dropped = _asr_prompt_terms(category, whisper_lang)
    text = ", ".join(used)
    return {"chars": len(text), "terms": len(used), "dropped": dropped,
            "budget": ASR_PROMPT_CHAR_BUDGET, "text": text}


def get_asr_prompt(category: str, whisper_lang: str) -> str:
    """拼识别提示词（塞进 Whisper 的 initial_prompt）。

    预算与排序的原因见 ASR_PROMPT_CHAR_BUDGET 上方的注释。
    历史教训：以前是"把整张术语表全塞进去"，词表一大就把重要词挤掉。
    """
    used, _ = _asr_prompt_terms(category, whisper_lang)
    return ", ".join(used)


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
