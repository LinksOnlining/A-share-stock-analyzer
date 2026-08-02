# -*- coding: utf-8 -*-
"""
A股智能股票分析工具 v5.0 — 后端主程序
技术栈：FastAPI + httpx + python-dotenv
数据源：新浪财经（并发分页，全市场实时行情）
支持：单只深度分析 / 批量横向对比 / 潜力股量化筛选 / 全市场搜索
兼容：源码运行 + PyInstaller 打包 exe
"""

import os
import sys

# ==== 1. 全局禁用代理（直连国内行情接口） ====
for _k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(_k, None)
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

# ==== 2. 真实浏览器 UA（绕过反爬） ====
_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


# =====================================================================
# 打包兼容辅助函数
# =====================================================================
def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包后的 exe 中"""
    return getattr(sys, "frozen", False)


def get_app_dir() -> str:
    """可写文件目录：源码=项目根；exe=exe同级目录"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir() -> str:
    """只读资源目录（static）：exe模式下在_MEIPASS临时解压目录"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", get_app_dir())
    return get_app_dir()


# =====================================================================
# 主程序
# =====================================================================
import json
import time
import re
import hashlib
import logging
import threading
import urllib.request
import concurrent.futures
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import httpx
from dotenv import load_dotenv

# ==================== 环境配置 ====================
APP_DIR = Path(get_app_dir())
RESOURCE_DIR = Path(get_resource_dir())

# 打包exe：.env 和 cache 放在 exe 同级，避免每次启动丢失
if is_frozen():
    env_path = APP_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
else:
    load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "120"))
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_DIR = APP_DIR / os.getenv("CACHE_DIR", "cache")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="A股智能股票分析工具", version="5.0.0")

STATIC_DIR = RESOURCE_DIR / "static"
if not STATIC_DIR.exists() and is_frozen():
    STATIC_DIR = APP_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==================== 请求体模型 ====================
class AnalyzeRequest(BaseModel):
    stock_code: str = Field(..., min_length=2, max_length=50)


class BatchRequest(BaseModel):
    stock_list: List[str] = Field(..., min_items=1, max_items=10)


class ScreenRequest(BaseModel):
    pe_min: float = Field(0, ge=-100, le=5000)
    pe_max: float = Field(60, ge=-100, le=5000)
    mktcap_min: float = Field(50, ge=1, le=100000)
    mktcap_max: float = Field(3000, ge=1, le=100000)
    turnover_min: float = Field(1, ge=0, le=100)
    change_min: float = Field(-5, ge=-30, le=30)
    change_max: float = Field(10, ge=-30, le=30)
    exclude_st: bool = Field(True)
    top_n: int = Field(10, ge=3, le=30)
    sort_by: str = Field("score")


# ==================== 系统提示词 ====================
SYSTEM_PROMPT = """你是一名专业、客观、理性的资本市场多维度分析师，严格基于公开可查询信息进行推演，禁止凭空编造财务数据、小道消息、未公告传闻。

任务：针对指定上市公司股票进行全方位量化 + 定性综合分析。六大维度：

【维度1 基本面】主营业务、核心产品、商业模式、核心竞争力（壁垒）；近三年关键财务指标（营收、净利润、扣非净利润、毛利率、净利率、资产负债率、经营现金流）；管理层、股权结构、大股东质押、商誉减值隐患。

【维度2 估值水平】横向对比同行业PE(TTM)/PB/PEG；纵向对比历史5年估值分位；判断当前估值：高估/合理/低估。

【维度3 行业与宏观景气】行业周期（复苏/繁荣/下行/底部）；政策利好/利空；上下游供需格局；未来1-2年增长空间与催化事件。

【维度4 资金与市场情绪面】北向资金/机构持仓变化趋势；筹码集中度/成交量变化；市场主流机构一致预期。

【维度5 技术面客观解读】K线中长期趋势、支撑位、压力位、成交量配合情况。只描述形态，禁止预测涨跌。

【维度6 全面风险排查】业绩暴雷风险、政策监管风险、行业竞争加剧风险、原材料涨价风险、解禁减持风险、诉讼风险、流动性风险等。

规则：中立客观，优势隐患同等权重。杜绝绝对化词语（"一定大涨、绝对低估"），使用保守表述（"存在上涨潜力、具备配置价值、风险较高"）。区分【事实】和【主观推演】。固定结构：①标的基础概况 ②六大维度逐项分析 ③综合评分（总分100分：基本面30｜估值20｜行业景气20｜资金面15｜风险15）④综合结论 ⑤重点关注跟踪指标。严禁输出买卖指令。使用标准Markdown格式。"""

SCREEN_PROMPT = """你是一名专业、客观、理性的资本市场多维度分析师，严格基于公开可查询信息进行推演，禁止凭空编造财务数据、小道消息、未公告传闻。

任务：以下是一批通过量化指标初筛（综合得分排序）产生的A股关注候选清单。请对这批候选进行深入分析，输出一份《潜力候选分析报告》：

要求：
1. 对每只候选股票，给出简洁但有依据的简评，覆盖：估值水平、行业逻辑、资金面迹象、主要风险。每条不超过80字。
2. 明确说明这些候选是【量化初筛结果】，仅代表某些技术/估值特征，不代表基本面确认，需要进一步核实。
3. 对所有候选进行横向比较，指出各自相对优势与隐患，给出「关注优先级」排序（仅作研究参考）。
4. 客观列出整体风险：量化筛选的局限性、数据延迟、行业集中度风险等。
5. 严禁输出任何买卖指令，不得使用"买入、卖出、加仓、抄底、清仓"等词汇。
6. 使用保守表述（"存在关注价值、需要进一步验证"），杜绝绝对化词语。
7. 输出使用标准Markdown格式，结构清晰。

请记住：你的输出是【研究参考】，不是投资建议。"""


# ==================== 内容过滤 ====================
FORBIDDEN_KEYWORDS = [
    "买入", "卖出", "加仓", "减仓", "清仓", "抄底", "逃顶", "满仓",
    "建议买入", "建议卖出", "建议持有", "强烈推荐", "重仓", "轻仓",
    "全仓", "半仓", "建仓", "平仓", "做多", "做空", "追涨", "杀跌",
    "all in", "梭哈", "上车", "下车",
]


def filter_content(text: str) -> str:
    filtered = text
    for kw in FORBIDDEN_KEYWORDS:
        filtered = re.sub(re.escape(kw), "**[合规提示：该词汇已被系统屏蔽，请理性决策]**", filtered, flags=re.IGNORECASE)
    return filtered


# ==================== 缓存 ====================
def get_cache_key(raw: str, mode: str = "analyze") -> str:
    return hashlib.md5(f"{mode}:{raw}".encode()).hexdigest()


def read_cache(key: str) -> Optional[str]:
    if not CACHE_ENABLED:
        return None
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        f = CACHE_DIR / f"{key}.json"
        if not f.exists():
            return None
        data = json.loads(f.read_text("utf-8"))
        if time.time() - data.get("timestamp", 0) > 86400:
            f.unlink(missing_ok=True)
            return None
        return data.get("content")
    except Exception:
        return None


def write_cache(key: str, content: str) -> None:
    if not CACHE_ENABLED:
        return
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        (CACHE_DIR / f"{key}.json").write_text(
            json.dumps({"timestamp": time.time(), "content": content}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception:
        pass


# =====================================================================
# 全市场数据源 — 新浪财经（并发分页）
# =====================================================================
_SINA_URL = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"

_market_cache: Optional[List[dict]] = None
_market_time: float = 0.0
_MARKET_CACHE_TTL = 3600 * 6

_FALLBACK_STOCKS = [
    {"code": "600519", "name": "贵州茅台", "exchange": "SH", "price": 1350.0, "changepercent": 0.0, "per": 20.0, "pb": 7.0, "mktcap": 16900, "nmc": 16900, "turnoverratio": 0.2, "volume": 30000, "amount": 400000},
    {"code": "000858", "name": "五粮液", "exchange": "SZ", "price": 120.0, "changepercent": 0.0, "per": 18.0, "pb": 4.0, "mktcap": 4600, "nmc": 4600, "turnoverratio": 0.4, "volume": 150000, "amount": 180000},
    {"code": "300750", "name": "宁德时代", "exchange": "SZ", "price": 180.0, "changepercent": 0.0, "per": 25.0, "pb": 4.5, "mktcap": 7900, "nmc": 6900, "turnoverratio": 0.8, "volume": 200000, "amount": 360000},
    {"code": "600036", "name": "招商银行", "exchange": "SH", "price": 35.0, "changepercent": 0.0, "per": 6.0, "pb": 0.9, "mktcap": 8800, "nmc": 7200, "turnoverratio": 0.3, "volume": 120000, "amount": 420000},
    {"code": "601318", "name": "中国平安", "exchange": "SH", "price": 45.0, "changepercent": 0.0, "per": 8.0, "pb": 1.0, "mktcap": 8200, "nmc": 4800, "turnoverratio": 0.5, "volume": 180000, "amount": 800000},
    {"code": "600030", "name": "中信证券", "exchange": "SH", "price": 25.0, "changepercent": 0.0, "per": 15.0, "pb": 1.3, "mktcap": 3700, "nmc": 2900, "turnoverratio": 0.6, "volume": 250000, "amount": 620000},
    {"code": "002415", "name": "海康威视", "exchange": "SZ", "price": 30.0, "changepercent": 0.0, "per": 18.0, "pb": 3.0, "mktcap": 2800, "nmc": 2700, "turnoverratio": 0.4, "volume": 150000, "amount": 450000},
    {"code": "000333", "name": "美的集团", "exchange": "SZ", "price": 55.0, "changepercent": 0.0, "per": 12.0, "pb": 2.5, "mktcap": 3800, "nmc": 3700, "turnoverratio": 0.5, "volume": 100000, "amount": 550000},
    {"code": "600900", "name": "长江电力", "exchange": "SH", "price": 28.0, "changepercent": 0.0, "per": 20.0, "pb": 3.0, "mktcap": 6800, "nmc": 6400, "turnoverratio": 0.3, "volume": 80000, "amount": 220000},
    {"code": "688981", "name": "中芯国际", "exchange": "SH", "price": 50.0, "changepercent": 0.0, "per": 60.0, "pb": 3.5, "mktcap": 3900, "nmc": 2800, "turnoverratio": 1.0, "volume": 300000, "amount": 150000},
]


def _fetch_sina_page(page: int, num: int = 100) -> list:
    url = f"{_SINA_URL}?page={page}&num={num}&sort=symbol&asc=1&node=hs_a"
    req = urllib.request.Request(url, headers={
        "User-Agent": _BROWSER_UA,
        "Referer": "https://finance.sina.com.cn",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode("utf-8")
    data = json.loads(raw)
    return data if isinstance(data, list) else []


def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _load_market_snapshot() -> List[dict]:
    global _market_cache, _market_time
    if _market_cache is not None and (time.time() - _market_time) < _MARKET_CACHE_TTL:
        return _market_cache

    try:
        first = _fetch_sina_page(1, 100)
        if not first:
            raise RuntimeError("新浪接口返回空数据")

        total_pages = 60
        logger.info("正在通过新浪财经并发分页加载全市场A股快照...")
        stock_list, seen = [], set()

        def process_page(p):
            try:
                return _fetch_sina_page(p, 100)
            except Exception:
                return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            pages = list(ex.map(process_page, range(1, total_pages + 1)))

        for page_data in pages:
            for item in page_data:
                try:
                    symbol = str(item.get("symbol", ""))
                    code = str(item.get("code", ""))
                    name = str(item.get("name", ""))
                    if not symbol or not code or not name or code in seen:
                        continue
                    seen.add(code)
                    if symbol.startswith("sh"):
                        exchange = "SH"
                    elif symbol.startswith("sz"):
                        exchange = "SZ"
                    elif symbol.startswith("bj"):
                        exchange = "BJ"
                    else:
                        exchange = ""
                    mktcap_wan = _to_float(item.get("mktcap"))
                    nmc_wan = _to_float(item.get("nmc"))
                    stock_list.append({
                        "code": code, "name": name, "exchange": exchange,
                        "label": f"{code}.{exchange} {name}",
                        "price": _to_float(item.get("trade")),
                        "changepercent": _to_float(item.get("changepercent")),
                        "per": _to_float(item.get("per")),
                        "pb": _to_float(item.get("pb")),
                        "mktcap": round(mktcap_wan / 10000, 2),
                        "nmc": round(nmc_wan / 10000, 2),
                        "turnoverratio": _to_float(item.get("turnoverratio")),
                        "volume": _to_float(item.get("volume")),
                        "amount": _to_float(item.get("amount")),
                    })
                except Exception:
                    continue

        if not stock_list:
            raise RuntimeError("新浪数据解析为空")

        _market_cache = stock_list
        _market_time = time.time()
        logger.info(f"✅ 全市场快照加载完成：{len(stock_list)} 只（新浪财经）")
        return _market_cache

    except Exception as e:
        logger.error(f"新浪接口加载失败: {e}")
        if _market_cache is not None and _market_cache:
            logger.warning(f"使用过期缓存（{len(_market_cache)} 只）")
            return _market_cache
        logger.warning(f"降级为内置兜底列表（{len(_FALLBACK_STOCKS)} 只）")
        fallback = []
        for s in _FALLBACK_STOCKS:
            fallback.append({**s, "label": f"{s['code']}.{s['exchange']} {s['name']}"})
        _market_cache = fallback
        _market_time = time.time()
        return fallback


def _get_search_list() -> List[dict]:
    snapshot = _load_market_snapshot()
    return [{"code": s["code"], "name": s["name"], "exchange": s["exchange"], "label": s["label"]} for s in snapshot]


# ==================== 拼音首字母匹配 ====================
_PINYIN = {
    "中":"z","国":"g","平":"p","安":"a","人":"r","民":"m","银":"y","行":"h",
    "工":"g","农":"n","建":"j","交":"j","招":"z","商":"s","华":"h","夏":"x",
    "浦":"p","发":"f","兴":"x","业":"y","信":"x","用":"y","保":"b","险":"x",
    "证":"z","券":"q","基":"j","金":"j","科":"k","技":"j","电":"d","力":"l",
    "能":"n","源":"y","石":"s","油":"y","化":"h","学":"x","医":"y","药":"y",
    "生":"s","物":"w","制":"z","造":"z","机":"j","械":"x","汽":"q","车":"c",
    "房":"f","地":"d","产":"c","筑":"z","材":"c","食":"s","品":"p","饮":"y",
    "料":"l","白":"b","酒":"j","五":"w","粮":"l","液":"y","茅":"m","台":"t",
    "泸":"l","州":"z","老":"l","窖":"j","洋":"y","河":"h","汾":"f","古":"g",
    "井":"j","贡":"g","伊":"y","利":"l","蒙":"m","牛":"n","牧":"m","原":"y",
    "温":"w","氏":"s","海":"h","尔":"e","美":"m","的":"d","格":"g","三":"s",
    "一":"y","重":"c","万":"w","福":"f","耀":"y","玻":"b","璃":"l","宁":"n",
    "德":"d","时":"s","代":"d","比":"b","亚":"y","迪":"d","隆":"l","绿":"l",
    "阳":"y","光":"g","通":"t","威":"w","晶":"j","澳":"a","天":"t","合":"h",
    "亿":"y","纬":"w","锂":"l","友":"y","齐":"q","恒":"h","瑞":"r","迈":"m",
    "眼":"y","康":"k","明":"m","片":"p","仔":"z","癀":"h","云":"y","南":"n",
    "新":"x","和":"h","成":"c","智":"z","飞":"f","君":"j","实":"s","泰":"t",
    "芯":"x","北":"b","韦":"w","微":"w","兆":"z","易":"y","创":"c","澜":"l",
    "起":"q","紫":"z","卓":"z","胜":"s","东":"d","财":"c","同":"t","花":"h",
    "顺":"s","汇":"h","川":"c","大":"d","立":"l","讯":"x","精":"j","密":"m",
    "传":"c","音":"y","广":"g","联":"l","达":"d","山":"s","办":"b","公":"g",
    "腾":"t","阿":"a","里":"l","网":"w","京":"j","拼":"p","多":"d","团":"t",
    "快":"k","手":"s","小":"x","米":"m","为":"w","长":"c","江":"j","矿":"k",
    "水":"s","泥":"n","螺":"l","神":"s","宝":"b","钢":"g","铁":"t","科":"k",
}

def _pinyin_match(name: str, keyword: str) -> bool:
    return keyword in "".join([_PINYIN.get(ch, "?") for ch in name])


# ==================== 潜力股量化筛选 ====================
def _is_st(name: str) -> bool:
    return "ST" in name.upper()


def _score_candidates(candidates: List[dict]) -> List[dict]:
    n = len(candidates)
    if n == 0:
        return candidates

    def norm(vals, v, reverse=False):
        lo, hi = min(vals), max(vals)
        if hi == lo:
            return 50.0
        r = (v - lo) / (hi - lo) * 100
        return 100 - r if reverse else r

    changes = [c["changepercent"] for c in candidates]
    turnovers = [c["turnoverratio"] for c in candidates]
    pes = [c["per"] for c in candidates if c["per"] > 0]

    def value_score(c):
        if c["per"] <= 0:
            return 10
        if len(pes) < 2:
            return 50
        return norm(pes, c["per"], reverse=True)

    def mktcap_score(c):
        cap = c["mktcap"]
        if cap < 20: return 20
        if cap < 50: return 40
        if cap < 100: return 60
        if cap <= 2000: return 90
        if cap <= 5000: return 60
        return 30

    for c in candidates:
        momentum = norm(changes, c["changepercent"]) if n > 1 else 50
        liquidity = norm(turnovers, c["turnoverratio"]) if n > 1 else 50
        value = value_score(c)
        cap = mktcap_score(c)
        c["score"] = round(0.3 * momentum + 0.2 * liquidity + 0.3 * value + 0.2 * cap, 2)
        c["score_components"] = {
            "momentum": round(momentum, 1),
            "liquidity": round(liquidity, 1),
            "value": round(value, 1),
            "mktcap": round(cap, 1),
        }
    return candidates


def _screen_stocks(req: ScreenRequest) -> List[dict]:
    snapshot = _load_market_snapshot()
    filtered = []
    for s in snapshot:
        if req.exclude_st and _is_st(s["name"]):
            continue
        if s["per"] == 0:
            continue
        if s["per"] < req.pe_min or s["per"] > req.pe_max:
            continue
        if s["mktcap"] < req.mktcap_min or s["mktcap"] > req.mktcap_max:
            continue
        if s["turnoverratio"] < req.turnover_min:
            continue
        if s["changepercent"] < req.change_min or s["changepercent"] > req.change_max:
            continue
        filtered.append(s)

    if not filtered:
        return []

    filtered = _score_candidates(filtered)
    sort_key = {"score": "score", "change": "changepercent", "mktcap": "mktcap", "pe": "per"}.get(req.sort_by, "score")
    reverse = sort_key != "pe"
    filtered.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)
    return filtered[: req.top_n]


# ==================== DeepSeek API ====================
async def call_deepseek(messages: list, max_tokens: int = 8192) -> dict:
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY.startswith("your-"):
        return {"success": False, "error": "DeepSeek API Key 未配置"}

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(DEEPSEEK_BASE_URL, json=payload, headers=headers)
            if resp.status_code in (401, 403): return {"success": False, "error": f"API认证失败 HTTP {resp.status_code}"}
            if resp.status_code == 429: return {"success": False, "error": "API频率过高，请稍后重试"}
            if resp.status_code != 200: return {"success": False, "error": f"API错误 HTTP {resp.status_code}"}
            data = resp.json()
            choices = data.get("choices", [])
            if not choices: return {"success": False, "error": "API返回空结果"}
            content = choices[0].get("message", {}).get("content", "")
            if not content: return {"success": False, "error": "API返回空内容"}
            return {"success": True, "content": content}
    except httpx.TimeoutException:
        return {"success": False, "error": f"请求超时（{REQUEST_TIMEOUT}s）"}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接 DeepSeek API"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 路由 ====================
@app.get("/")
async def root():
    idx = STATIC_DIR / "index.html"
    return FileResponse(str(idx)) if idx.exists() else {"message": "API已启动", "docs": "/docs"}


@app.get("/api/stock/search")
async def search_stocks(q: str = Query(""), limit: int = Query(15, ge=1, le=50)):
    keyword = q.strip()
    try:
        stock_list = _get_search_list()
    except Exception as e:
        return {"success": False, "error": str(e), "results": [], "total": 0, "search_available": False}

    if not stock_list:
        return {"success": True, "results": [], "total": 0, "search_available": False,
                "hint": "股票数据加载失败，请手动输入，如：600519.SH 贵州茅台"}

    if not keyword:
        top = sorted(stock_list, key=lambda x: x["code"])[:limit]
        return {"success": True, "results": top, "total": len(stock_list), "search_available": True}

    kw = keyword.lower()
    matches = []
    for s in stock_list:
        score = 0
        cl = s["code"].lower(); nm = s["name"]
        if cl.startswith(kw): score = 100 + len(kw)
        elif kw in cl: score = 50 + len(kw)
        if keyword == nm: score += 200
        elif nm.startswith(keyword): score += 80
        elif keyword in nm: score += 40
        elif _pinyin_match(nm, kw): score += 30
        if score > 0: matches.append({**s, "_s": score})

    matches.sort(key=lambda x: x["_s"], reverse=True)
    results = matches[:limit]
    for r in results: r.pop("_s", None)
    return {"success": True, "results": results, "total": len(stock_list),
            "search_available": True, "matched": len(matches)}


@app.post("/api/stock/screen")
async def screen_stocks(req: ScreenRequest):
    logger.info(f"收到潜力股筛选请求: PE[{req.pe_min},{req.pe_max}] 市值[{req.mktcap_min},{req.mktcap_max}]亿 Top{req.top_n}")

    candidates = _screen_stocks(req)
    if not candidates:
        return {"success": True, "candidates": [], "analysis": "未找到符合筛选条件的股票，请放宽筛选条件后重试。",
                "filters": req.model_dump(), "from_cache": False}

    cache_key = get_cache_key(json.dumps(req.model_dump(), sort_keys=True, ensure_ascii=False), "screen")
    analysis = read_cache(cache_key)
    from_cache = False

    if not analysis:
        lines = ["| 排名 | 代码 | 名称 | 现价 | 涨跌幅% | PE | PB | 总市值(亿) | 换手% | 综合得分 |",
                 "|---|---|---|---|---|---|---|---|---|---|"]
        for i, c in enumerate(candidates, 1):
            lines.append(f"| {i} | {c['code']} | {c['name']} | {c['price']:.2f} | {c['changepercent']:.2f} | "
                         f"{c['per']:.1f} | {c['pb']:.2f} | {c['mktcap']:.0f} | {c['turnoverratio']:.2f} | {c['score']:.1f} |")

        user_msg = (f"以下是通过量化指标初筛得到的潜力股关注候选清单（共{len(candidates)}只，按综合得分排序）：\n\n"
                    + "\n".join(lines) +
                    "\n\n筛选条件：" + json.dumps(req.model_dump(), ensure_ascii=False) +
                    "\n\n请对这些候选进行深入分析，输出《潜力候选分析报告》。")

        r = await call_deepseek(messages=[
            {"role": "system", "content": SCREEN_PROMPT},
            {"role": "user", "content": user_msg},
        ], max_tokens=8192)
        if r["success"]:
            analysis = filter_content(r["content"])
            write_cache(cache_key, analysis)
        else:
            analysis = ("> ⚠️ AI深度分析暂不可用（" + r["error"] + "），以下为量化筛选结果，仅供参考。\n\n"
                        "## 量化候选清单（综合得分排序）\n\n"
                        "本结果仅基于行情指标筛选，不代表基本面确认。")

    slim_candidates = []
    for c in candidates:
        slim_candidates.append({
            "code": c["code"], "name": c["name"], "exchange": c["exchange"], "label": c["label"],
            "price": c["price"], "changepercent": c["changepercent"], "per": c["per"], "pb": c["pb"],
            "mktcap": c["mktcap"], "nmc": c["nmc"], "turnoverratio": c["turnoverratio"], "score": c["score"],
        })

    return {"success": True, "candidates": slim_candidates, "analysis": analysis,
            "filters": req.model_dump(), "from_cache": from_cache}


@app.post("/api/stock/analyze")
async def analyze_stock(req: AnalyzeRequest):
    sc = req.stock_code.strip()
    key = get_cache_key(sc)
    if c := read_cache(key):
        return {"success": True, "stock_code": sc, "analysis": c, "from_cache": True}
    r = await call_deepseek(messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请对以下A股上市公司进行全面深度分析：{sc}"},
    ], max_tokens=8192)
    if not r["success"]:
        raise HTTPException(502, r["error"])
    fc = filter_content(r["content"])
    write_cache(key, fc)
    return {"success": True, "stock_code": sc, "analysis": fc, "from_cache": False}


@app.post("/api/stock/batch")
async def batch_analyze(req: BatchRequest):
    sl = [s.strip() for s in req.stock_list if s.strip()]
    if not sl:
        raise HTTPException(400, "股票列表为空")
    key = get_cache_key(",".join(sorted(sl)), "batch")
    if c := read_cache(key):
        return {"success": True, "stock_list": sl, "analysis": c, "from_cache": True}

    stocks_text = "\n".join(f"- {c}" for c in sl)
    r = await call_deepseek(messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请对以下{len(sl)}只A股进行横向对比分析：\n\n{stocks_text}"},
    ], max_tokens=16384)
    if not r["success"]:
        raise HTTPException(502, r["error"])
    fc = filter_content(r["content"])
    write_cache(key, fc)
    return {"success": True, "stock_list": sl, "analysis": fc, "from_cache": False}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "deepseek_configured": bool(DEEPSEEK_API_KEY and not DEEPSEEK_API_KEY.startswith("your-")),
        "cache_enabled": CACHE_ENABLED,
        "model": DEEPSEEK_MODEL,
        "data_source": "sina_finance",
        "stocks_loaded": len(_market_cache) if _market_cache else 0,
    }


# ==================== 启动入口 ====================
def _open_browser(url: str) -> None:
    try:
        import webbrowser
        time.sleep(2.0)
        webbrowser.open(url)
    except Exception as e:
        logger.warning(f"自动打开浏览器失败: {e}")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))

    logger.info("=" * 60)
    logger.info("A股智能股票分析工具 v5.0")
    logger.info(f"数据源: 新浪财经(并发分页) | 代理: 全局禁用 | UA: Chrome 131")
    logger.info(f"DeepSeek: {'已配置' if DEEPSEEK_API_KEY and not DEEPSEEK_API_KEY.startswith('your-') else '未配置 (请在exe同目录.env中配置)'}")
    logger.info(f"缓存目录: {CACHE_DIR}")
    logger.info(f"服务地址: http://{host}:{port}")
    logger.info("按 Ctrl+C 停止服务")
    logger.info("=" * 60)

    threading.Thread(target=_open_browser, args=(f"http://{host}:{port}",), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
