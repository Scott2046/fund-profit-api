from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import json

# 全局变量：模拟持仓基金数据（存储用户添加的基金+成本+份额）
HOLD_FUNDS = []

# FastAPI 实例
app = FastAPI(title="基金盈亏计算接口", version="1.0")

# 数据模型：添加基金的请求体
class FundAddRequest(BaseModel):
    code: str  # 基金代码
    name: str  # 基金名称
    cost: float  # 持仓成本（单价）
    share: float  # 持有份额

# 数据模型：删除基金的请求体
class FundDeleteRequest(BaseModel):
    code: str  # 基金代码

# 工具函数1：获取基金实时数据（模拟接口，实际可替换为真实数据源）
def get_fund_real_data(fund_code: str) -> dict:
    """
    获取基金实时净值/涨幅
    :param fund_code: 基金代码
    :return: {"value": 实时净值, "rate": 涨跌幅, "type": 数据类型}
    """
    # 模拟数据（实际项目中替换为真实爬虫/API调用）
    mock_data = {
        "000001": {"value": 1.2345, "rate": "+0.89%", "type": "股票型"},
        "000002": {"value": 2.3456, "rate": "-0.23%", "type": "债券型"},
        "000003": {"value": 0.9876, "rate": "+1.56%", "type": "混合型"},
    }
    # 兜底：如果无匹配代码，返回默认值
    return mock_data.get(fund_code, {"value": 1.0000, "rate": "0.00%", "type": "未知类型"})

# 工具函数2：计算单只基金的盈亏
def calculate_profit(fund: dict, real_data: dict) -> tuple:
    """
    计算盈亏：浮动盈亏、总成本、收益率
    :param fund: 持仓基金（含code/name/cost/share）
    :param real_data: 实时数据（含value/rate/type）
    :return: (浮动盈亏, 总成本, 收益率)
    """
    total_cost = fund["cost"] * fund["share"]  # 总成本 = 成本单价 * 份额
    current_value = float(real_data["value"]) * fund["share"]  # 当前市值 = 实时净值 * 份额
    float_profit = current_value - total_cost  # 浮动盈亏
    profit_rate = (float_profit / total_cost) * 100 if total_cost > 0 else 0.0  # 收益率
    return round(float_profit, 2), round(total_cost, 2), round(profit_rate, 2)

# 接口1：获取所有持仓基金的实时盈亏（核心修复：强制返回cost/share字段）
@app.get("/api/fund/profit", summary="获取所有持仓基金的实时盈亏数据")
async def get_fund_profit():
    result = []
    total_float_profit = 0.0  # 总浮动盈亏
    total_total_cost = 0.0    # 总成本
    try:
        for fund in HOLD_FUNDS:
            # 获取实时数据
            real_data = get_fund_real_data(fund["code"])
            # 计算盈亏
            float_profit, total_cost, profit_rate = calculate_profit(fund, real_data)
            # 累加总盈亏/总成本
            total_float_profit += float_profit
            total_total_cost += total_cost
            # 组装返回数据（必含cost/share）
            result.append({
                "code": fund["code"],
                "name": fund["name"],
                "cost": fund["cost"],          # 前端要渲染的成本单价
                "share": fund["share"],        # 前端要渲染的持有份额
                "current_value": real_data["value"],  # 实时净值
                "change_rate": real_data["rate"],     # 涨跌幅
                "data_type": real_data["type"],       # 基金类型
                "total_cost": total_cost,      # 持仓总成本
                "float_profit": float_profit,  # 浮动盈亏
                "profit_rate": profit_rate     # 收益率
            })
        # 计算总收益率
        total_profit_rate = round((total_float_profit / total_total_cost) * 100, 2) if total_total_cost > 0 else 0.0
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "funds": result,
                "total": {
                    "total_cost": round(total_total_cost, 2),
                    "total_float_profit": round(total_float_profit, 2),
                    "total_profit_rate": total_profit_rate
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"盈亏计算失败：{str(e)[:50]}")

# 接口2：添加基金到持仓
@app.post("/api/fund/add", summary="添加基金到持仓列表")
async def add_fund(request: FundAddRequest):
    try:
        # 校验参数
        if not request.code or len(request.code) != 6:
            raise HTTPException(status_code=400, detail="基金代码必须为6位数字")
        if request.cost <= 0 or request.share <= 0:
            raise HTTPException(status_code=400, detail="成本和份额必须大于0")
        # 检查是否已添加
        for fund in HOLD_FUNDS:
            if fund["code"] == request.code:
                raise HTTPException(status_code=400, detail="该基金已在持仓列表中")
        # 添加到持仓
        HOLD_FUNDS.append({
            "code": request.code,
            "name": request.name,
            "cost": request.cost,
            "share": request.share
        })
        return {
            "code": 200,
            "msg": "添加成功",
            "data": {"fund_count": len(HOLD_FUNDS)}
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加基金失败：{str(e)[:50]}")

# 接口3：从持仓删除基金
@app.post("/api/fund/delete", summary="从持仓列表删除基金")
async def delete_fund(request: FundDeleteRequest):
    try:
        # 校验参数
        if not request.code or len(request.code) != 6:
            raise HTTPException(status_code=400, detail="基金代码必须为6位数字")
        # 查找并删除
        for index, fund in enumerate(HOLD_FUNDS):
            if fund["code"] == request.code:
                HOLD_FUNDS.pop(index)
                return {
                    "code": 200,
                    "msg": "删除成功",
                    "data": {"fund_count": len(HOLD_FUNDS)}
                }
        # 未找到基金
        raise HTTPException(status_code=404, detail="该基金不在持仓列表中")
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除基金失败：{str(e)[:50]}")

# 接口4：清空持仓列表
@app.post("/api/fund/clear", summary="清空所有持仓基金")
async def clear_fund():
    try:
        HOLD_FUNDS.clear()
        return {
            "code": 200,
            "msg": "清空成功",
            "data": {"fund_count": 0}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空持仓失败：{str(e)[:50]}")

# 启动入口（本地测试用，Render部署时无需）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
