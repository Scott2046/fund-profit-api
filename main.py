# 导入所有依赖库（前置）
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import uvicorn
import json
import os

# 第一步：先创建 FastAPI 核心实例（所有路由前必须定义，解决 NameError 问题）
app = FastAPI(title="基金估值盈亏接口（支持搜索）", version="1.0")

# 跨域配置（必须加，小程序跨域调用必备）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 允许所有域名访问（适配小程序本地调试/真机）
    allow_credentials=True,
    allow_methods=["*"],        # 允许GET/POST等所有请求方法
    allow_headers=["*"],        # 允许所有请求头
)

# -------------------------- 【可选修改】初始默认持仓（可留空，后续小程序搜索添加） --------------------------
# 格式：code(6位数字)、name(基金名称)、cost(持仓成本)、share(持有份额)，留空则写 DEFAULT_HOLD_FUNDS = []
DEFAULT_HOLD_FUNDS = [
    {"code": "000311", "name": "景顺长城沪深300指数A", "cost": 1.2345, "share": 1000.00},
    {"code": "012769", "name": "华夏恒生ETF联接A", "cost": 1.0890, "share": 500.00},
]
# ------------------------------------------------------------------------------------------------------------------

# 全局持仓变量 + 数据持久化配置
HOLD_FUNDS = []
FUND_DATA_FILE = "hold_funds.json"  # 持仓数据存储文件，重启服务不丢失

# 程序启动时加载本地持仓（优先加载本地文件，无则用默认）
@app.on_event("startup")
async def load_hold_funds():
    global HOLD_FUNDS
    if os.path.exists(FUND_DATA_FILE):
        try:
            with open(FUND_DATA_FILE, "r", encoding="utf-8") as f:
                HOLD_FUNDS = json.load(f)
            print(f"✅ 成功加载本地持仓：{len(HOLD_FUNDS)}只基金")
        except Exception as e:
            HOLD_FUNDS = DEFAULT_HOLD_FUNDS
            print(f"⚠️  本地持仓文件损坏，使用默认持仓：{e}")
    else:
        HOLD_FUNDS = DEFAULT_HOLD_FUNDS
        print(f"ℹ️  无本地持仓文件，使用默认持仓")

# 工具函数1：获取基金实时估值/最新净值（交易时间返估值，非交易时间返净值）
def get_fund_real_data(fund_code):
    url = f"https://fund.eastmoney.com/{fund_code}.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://fund.eastmoney.com/"
    }
    res_data = {"value": "无数据", "rate": "无数据", "type": "最新净值"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 提取实时估值（交易时间有效）
        estimate_area = soup.find("div", class_="dataItem02")
        if estimate_area:
            gz_gsz = estimate_area.find("span", id="gz_gsz")  # 估值净值
            gz_gszzl = estimate_area.find("span", id="gz_gszzl")  # 估值涨幅
            if gz_gsz and gz_gszzl and gz_gsz.text.strip():
                res_data["value"] = gz_gsz.text.strip()
                res_data["rate"] = gz_gszzl.text.strip()
                res_data["type"] = "实时估值"
                return res_data
        
        # 提取最新净值（非交易时间有效）
        net_area = soup.find("div", class_="dataItem01")
        if net_area:
            nav_ele = net_area.find("span", class_="ui-font-large ui-font-bold")  # 最新净值
            nav_rate_ele = net_area.find("span", class_=lambda x: x and ("ui-font-red" in x or "ui-font-green" in x))  # 净值涨幅
            nav_date_ele = net_area.find("p", class_="ui-font-normal")  # 更新时间
            if nav_ele:
                res_data["value"] = nav_ele.text.strip()
            if nav_rate_ele:
                res_data["rate"] = nav_rate_ele.text.strip()
            if nav_date_ele:
                res_data["type"] = f"最新净值({nav_date_ele.text.strip().replace('更新时间：', '')})"
        return res_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"基金数据获取失败：{str(e)[:30]}")

# 工具函数2：计算基金盈亏（成本、份额 → 浮动盈亏、总成本、收益率）
def calculate_profit(fund_hold, real_data):
    try:
        current_val = float(real_data["value"])
        cost_val = float(fund_hold["cost"])
        share = float(fund_hold["share"])
        float_profit = round((current_val - cost_val) * share, 2)  # 浮动盈亏
        total_cost = round(cost_val * share, 2)                    # 持仓总成本
        profit_rate = round((float_profit / total_cost) * 100, 2) if total_cost > 0 else 0.0  # 收益率
        return float_profit, total_cost, profit_rate
    except Exception as e:
        return 0.0, 0.0, 0.0

# -------------------------- 接口1：获取持仓基金+实时盈亏（小程序核心） --------------------------
@app.get("/api/fund/profit", summary="获取所有持仓基金的实时盈亏数据")
async def get_fund_profit():
    result = []
    total_float_profit = 0.0
    total_total_cost = 0.0
    try:
        for fund in HOLD_FUNDS:
            real_data = get_fund_real_data(fund["code"])
            float_profit, total_cost, profit_rate = calculate_profit(fund, real_data)
            total_float_profit += float_profit
            total_total_cost += total_cost
            result.append({
                "code": fund["code"],
                "name": fund["name"],
                "cost": fund["cost"],
                "share": fund["share"],
                "current_value": real_data["value"],
                "change_rate": real_data["rate"],
                "data_type": real_data["type"],
                "total_cost": total_cost,
                "float_profit": float_profit,
                "profit_rate": profit_rate
            })
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "funds": result,
                "total": {
                    "total_cost": round(total_total_cost, 2),
                    "total_float_profit": round(total_float_profit, 2),
                    "total_profit_rate": round((total_float_profit / total_total_cost) * 100, 2) if total_total_cost > 0 else 0.0
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"盈亏计算失败：{str(e)[:30]}")

# -------------------------- 接口2：基金搜索（核心搜索功能，支持代码/名称） --------------------------
@app.get("/api/fund/search", summary="基金搜索：6位代码精准搜/名称模糊搜，返回实时数据")
async def search_fund(keyword: str):
    # 校验搜索关键词
    if not keyword or len(keyword) < 2:
        raise HTTPException(status_code=400, detail="请输入至少2位字符（基金代码/名称）")
    # 调用天天基金官方搜索接口（稳定可靠，适配模糊搜索）
    search_url = f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key={keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://fund.eastmoney.com/"
    }
    try:
        search_res = requests.get(search_url, headers=headers, timeout=10)
        search_data = search_res.json()
        # 无匹配结果
        if not search_data.get("Datas"):
            return {"code": 200, "msg": "未找到匹配基金", "data": []}
        # 处理搜索结果，最多返回10条，避免数据过多
        result = []
        for fund in search_data["Datas"][:10]:
            fund_code = fund["CODE"]
            fund_name = fund["NAME"]
            real_data = get_fund_real_data(fund_code)  # 为搜索结果绑定实时估值/净值
            result.append({
                "code": fund_code,
                "name": fund_name,
                "current_value": real_data["value"],
                "change_rate": real_data["rate"],
                "data_type": real_data["type"]
            })
        return {"code": 200, "msg": f"找到{len(result)}条匹配结果", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败：{str(e)[:30]}")

# -------------------------- 接口3：添加基金到持仓（搜索后一键添加，双人共用） --------------------------
@app.post("/api/fund/add", summary="将搜索到的基金添加到持仓，自动保存，重启不丢失")
async def add_fund(fund: dict):
    # 校验必传参数
    required_keys = ["code", "name", "cost", "share"]
    if not all(key in fund for key in required_keys):
        raise HTTPException(status_code=400, detail="参数缺失：需包含code/name/cost/share")
    # 校验参数合法性
    try:
        fund["cost"] = round(float(fund["cost"]), 4)    # 成本保留4位小数，贴合基金平台
        fund["share"] = round(float(fund["share"]), 2)  # 份额保留2位小数
        if fund["cost"] <= 0 or fund["share"] <= 0:
            raise ValueError("成本和份额必须大于0")
        if len(fund["code"]) != 6 or not fund["code"].isdigit():
            raise ValueError("基金代码必须是6位纯数字")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"参数错误：{str(e)}")
    # 避免重复添加
    global HOLD_FUNDS
    if any(f["code"] == fund["code"] for f in HOLD_FUNDS):
        return {"code": 200, "msg": "该基金已在持仓中，无需重复添加", "data": HOLD_FUNDS}
    # 添加持仓并持久化到本地文件
    HOLD_FUNDS.append(fund)
    with open(FUND_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(HOLD_FUNDS, f, ensure_ascii=False, indent=2)
    print(f"✅ 新增持仓：{fund['name']}({fund['code']})")
    return {"code": 200, "msg": "添加持仓成功", "data": HOLD_FUNDS}

# 本地运行入口（仅本地测试用，Render部署时自动忽略）
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")