# -------------------------- 新增：基金搜索接口（支持代码/名称搜索） --------------------------
@app.get("/api/fund/search", summary="基金搜索：输入代码/名称，返回匹配的基金实时数据")
async def search_fund(keyword: str):
    """
    keyword：搜索关键词（6位基金代码/基金名称关键词，如「000311」「沪深300」）
    返回：匹配的基金实时估值/最新净值数据
    """
    if not keyword:
        raise HTTPException(status_code=400, detail="请输入基金代码或名称")
    
    # 构造天天基金网搜索接口（适配代码/名称搜索，官方接口，稳定可靠）
    search_url = f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key={keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://fund.eastmoney.com/"
    }
    
    try:
        # 调用天天基金搜索接口，获取匹配的基金基础信息
        search_res = requests.get(search_url, headers=headers, timeout=10)
        search_data = search_res.json()
        if not search_data.get("Datas"):
            return {"code": 200, "msg": "未找到匹配基金", "data": []}
        
        # 遍历匹配结果，获取每只基金的实时估值/净值（复用原有get_fund_real_data逻辑）
        result = []
        for fund in search_data["Datas"][:10]:  # 最多返回10条匹配结果，避免数据过多
            fund_code = fund["CODE"]
            fund_name = fund["NAME"]
            # 复用原有逻辑，获取该基金的实时估值/最新净值
            real_data = get_fund_real_data(fund_code)
            result.append({
                "code": fund_code,
                "name": fund_name,
                "current_value": real_data["value"],
                "change_rate": real_data["rate"],
                "data_type": real_data["type"]
            })
        return {"code": 200, "msg": "搜索成功", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败：{str(e)[:20]}")

# -------------------------- 新增：手动添加持仓接口（一人添加，双人共用） --------------------------
@app.post("/api/fund/add", summary="添加基金到持仓，一人添加，小程序双人共用")
async def add_fund(fund: dict):
    """
    接收参数：{"code":基金代码, "name":基金名称, "cost":持仓成本, "share":持有份额}
    功能：添加基金到HOLD_FUNDS，同时更新本地持仓（简易文件存储，无需数据库，双人共用）
    """
    # 校验参数是否完整
    required_keys = ["code", "name", "cost", "share"]
    if not all(key in fund for key in required_keys):
        raise HTTPException(status_code=400, detail="参数不完整，需包含code/name/cost/share")
    try:
        # 转换数据类型（成本/份额为浮点数）
        fund["cost"] = float(fund["cost"])
        fund["share"] = float(fund["share"])
        # 检查是否已在持仓中，避免重复添加
        global HOLD_FUNDS  # 声明全局变量，修改原有持仓列表
        if any(f["code"] == fund["code"] for f in HOLD_FUNDS):
            return {"code": 200, "msg": "该基金已在持仓中，无需重复添加", "data": HOLD_FUNDS}
        # 添加到持仓列表
        HOLD_FUNDS.append(fund)
        # 简易文件存储（把持仓数据保存到本地文件，重启服务不丢失，双人共用）
        with open("hold_funds.json", "w", encoding="utf-8") as f:
            import json
            json.dump(HOLD_FUNDS, f, ensure_ascii=False, indent=2)
        return {"code": 200, "msg": "添加持仓成功", "data": HOLD_FUNDS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加持仓失败：{str(e)[:20]}")

# -------------------------- 新增：启动时加载本地持仓（避免重启服务丢失数据） --------------------------
# 程序启动时，若有本地持仓文件，自动加载到HOLD_FUNDS
try:
    with open("hold_funds.json", "r", encoding="utf-8") as f:
        import json
        HOLD_FUNDS = json.load(f)
    print("✅ 成功加载本地持仓数据")
except FileNotFoundError:
    print("ℹ️  未找到本地持仓文件，使用默认配置")
except Exception as e:
    print(f"⚠️  加载本地持仓失败，使用默认配置：{e}")