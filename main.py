# 补全所有依赖导入（关键！之前漏了CORSMiddleware）
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # 新增这行
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import uvicorn
import json
import os

# FastAPI 实例
app = FastAPI(title="基金估值盈亏接口（全功能）", version="1.0")

# 跨域配置（小程序必加）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据模型
class FundAddRequest(BaseModel):
    code: str
    name: str
    cost: float
    share: float

class FundDeleteRequest(BaseModel):
    code: str

# 全局变量+数据持久化
HOLD_FUNDS = []
FUND_DATA_FILE = "hold_funds.json"

# 启动时加载本地持仓
@app.on_event("startup")
async def load_hold_funds():
    global HOLD_FUNDS
    if os.path.exists(FUND_DATA_FILE):
        try:
            with open(FUND_DATA_FILE, "r", encoding="utf-8") as f:
                HOLD_FUNDS = json.load(f)
        except:
            HOLD_FUNDS = []
    else:
        HOLD_FUNDS = []

# 工具函数：保存持仓到本地
def save_hold_funds():
    with open(FUND_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(HOLD_FUNDS, f, ensure_ascii=False, indent=2)

# 工具函数1：获取基金实时数据（天天基金爬虫）
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
        
        # 提取实时估值
        estimate_area = soup.find("div", class_="dataItem02")
        if estimate_area:
            gz_gsz = estimate_area.find("span", id="gz_gsz")
            gz_gszzl = estimate_area.find("span", id="gz_gszzl")
            if gz_gsz and gz_gszzl and gz_gsz.text.strip():
                res_data["value"] = gz_gsz.text.strip()
                res_data["rate"] = gz_gszzl.text.strip()
                res_data["type"] = "实时估值"
                return res_data
        
        # 提取最新净值
        net_area = soup.find("div", class_="dataItem01")
        if net_area:
            nav_ele = net_area.find("span", class_="ui-font-large ui-font-bold")
            nav_rate_ele = net_area.find("span", class_=lambda x: x and ("ui-font-red" in x or "ui-font-green" in x))
            if nav_ele:
                res_data["value"] = nav_ele.text.strip()
            if nav_rate_ele:
                res_data["rate"] = nav_rate_ele.text.strip()
        return res_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"基金数据获取失败：{str(e)[:30]}")

# 工具函数2：计算盈亏
def calculate_profit(fund_hold, real_data):
    try:
        current_val = float(real_data["value"]) if real_data["value"] != "无数据" else 0
        cost_val = float(fund_hold["cost"])
        share = float(fund_hold["share"])
        float_profit = round((current_val - cost_val) * share, 2)
        total_cost = round(cost_val * share, 2)
        profit_rate = round((float_profit / total_cost) * 100, 2) if total_cost > 0 else 0.0
        return float_profit, total_cost, profit_rate
    except Exception as e:
        return 0.0, 0.0, 0.0

# 接口1：获取持仓+盈亏（必含cost/share）
@app.get("/api/fund/profit")
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
                "cost": fund["cost"],  # 前端要的成本
                "share": fund["share"],# 前端要的份额
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

# 接口2：基金搜索
@app.get("/api/fund/search")
async def search_fund(keyword: str):
    if not keyword or len(keyword) < 2:
        raise HTTPException(status_code=400, detail="请输入至少2位字符")
    search_url = f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key={keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://fund.eastmoney.com/"
    }
    try:
        search_res = requests.get(search_url, headers=headers, timeout=10)
        search_data = search_res.json()
        if not search_data.get("Datas"):
            return {"code": 200, "msg": "未找到匹配基金", "data": []}
        result = []
        for fund in search_data["Datas"][:10]:
            fund_code = fund["CODE"]
            fund_name = fund["NAME"]
            real_data = get_fund_real_data(fund_code)
            result.append({
                "code": fund_code,
                "name": fund_name,
                "current_value": real_data["value"],
                "change_rate": real_data["rate"],
                "data_type": real_data["type"]
            })
        return {"code": 200, "msg": f"找到{len(result)}条结果", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败：{str(e)[:30]}")

# 接口3：添加基金
@app.post("/api/fund/add")
async def add_fund(request: FundAddRequest):
    required_keys = ["code", "name", "cost", "share"]
    if not all(key in request.dict() for key in required_keys):
        raise HTTPException(status_code=400, detail="参数缺失")
    try:
        fund = {
            "code": request.code,
            "name": request.name,
            "cost": round(float(request.cost), 4),
            "share": round(float(request.share), 2)
        }
        if fund["cost"] <= 0 or fund["share"] <= 0:
            raise ValueError("成本/份额必须>0")
        if any(f["code"] == fund["code"] for f in HOLD_FUNDS):
            return {"code": 200, "msg": "该基金已在持仓中", "data": HOLD_FUNDS}
        HOLD_FUNDS.append(fund)
        save_hold_funds()
        return {"code": 200, "msg": "添加成功", "data": HOLD_FUNDS}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"参数错误：{str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加失败：{str(e)[:30]}")

# 接口4：删除基金
@app.post("/api/fund/delete")
async def delete_fund(request: FundDeleteRequest):
    if not request.code:
        raise HTTPException(status_code=400, detail="缺失基金代码")
    fund_code = request.code
    global HOLD_FUNDS
    fund_index = -1
    for i, f in enumerate(HOLD_FUNDS):
        if f["code"] == fund_code:
            fund_index = i
            break
    if fund_index == -1:
        raise HTTPException(status_code=404, detail="该基金未在持仓中")
    del HOLD_FUNDS[fund_index]
    save_hold_funds()
    return {"code": 200, "msg": "删除成功", "data": HOLD_FUNDS}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
