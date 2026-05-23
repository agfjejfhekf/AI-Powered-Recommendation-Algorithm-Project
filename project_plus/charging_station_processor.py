import pandas as pd
import numpy as np
import os
import re
import json
import requests
from geopy.distance import geodesic
from dotenv import load_dotenv

load_dotenv()

class ChargingStationProcessor:
    def __init__(self, data_path=None, top_n=4, max_distance=20):
        self.data_path = data_path
        self.top_n = top_n
        self.max_distance = max_distance
        self.df = pd.DataFrame()
        self._load_config()
        self.api_key = os.getenv("DOUBAO_API_KEY")
        self.endpoint_id = os.getenv("DOUBAO_ENDPOINT_ID")
        self.api_url = "高德地图api网址"
        self.ai_available = all([self.api_key, self.endpoint_id])

        if self.data_path and os.path.exists(self.data_path):
            try:
                self.df = self._load_and_preprocess_data()
                self._validate_data()
                print(f"充电站数据加载完成：共{len(self.df)}个充电站")
            except Exception as e:
                print(f"数据加载失败: {str(e)}")

    def _load_config(self):
        self.score_weights = {
            "距离":0.4,"评分":0.25,"价格性价比":0.15,"充电速度":0.1,"设施完整性":0.05,"环境卫生":0.05
        }

    def _load_and_preprocess_data(self):
        try:
            try:
                df = pd.read_csv(self.data_path, encoding='gbk')
            except:
                df = pd.read_csv(self.data_path, encoding='utf-8')

            key_columns = [
                '唯一充电站ID','充电站名称','行政区','具体地址','经度','纬度',
                '充电桩类型','联系电话','站平均评分','站有效评论数',
                '充电速度（0-5分）','价格性价比（0-5分）',
                '设施完整性（0-5分）','环境卫生（0-5分）','位置便利性（0-5分）'
            ]
            df = df[key_columns].copy()

            for col in ['经度','纬度']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df[(df['经度'].between(116,119)) & (df['纬度'].between(30,33))]
            return df.dropna(subset=['经度','纬度']).reset_index(drop=True)
        except:
            return pd.DataFrame()

    def _validate_data(self):
        self.df = self.df.dropna(subset=['经度','纬度'])

    def calculate_distance(self, user_lat, user_lng, station_lat, station_lng):
        try:
            return round(geodesic((user_lat,user_lng),(station_lat,station_lng)).kilometers,1)
        except:
            return 99.9

    # ====================== AI 解析偏好 ======================
    def ai_parse_station_preference(self, user_input):
        if not self.ai_available:
            return self._rule_based_preference_analysis(user_input)

        prompt = """你是充电站意图解析器，只返回JSON。
提取：priority(distance/price/speed/environment)，distance_limit(数字)，
need_fast_charge(bool)，price_sensitive(bool)，station_name(字符串)，
need_more_info(bool)，msg(字符串)。输入：""" + user_input

        try:
            resp = requests.post(
                self.api_url,
                headers={"Authorization":f"Bearer {self.api_key}"},
                json={"model":self.endpoint_id,"messages":[{"role":"user","content":prompt}],"temperature":0.1},
                timeout=5
            )
            data = json.loads(resp.json()["choices"][0]["message"]["content"])
            rule = self._rule_based_preference_analysis(user_input)
            return {
                "priority": data.get("priority", rule["priority"]),
                "distance_limit": min(int(data.get("distance_limit", rule["distance_limit"])), self.max_distance),
                "need_fast_charge": data.get("need_fast_charge", rule["need_fast_charge"]),
                "price_sensitive": data.get("price_sensitive", rule["price_sensitive"]),
                "station_name": data.get("station_name", ""),
                "need_more_info": data.get("need_more_info", False),
                "msg": data.get("msg", "请告诉我你的需求，比如就近、便宜、快充")
            }
        except:
            return self._rule_based_preference_analysis(user_input)

    # ====================== 规则解析 ======================
    def _is_valid_charging_request(self, user_input):
        return re.search(r'充电|快充|慢充|桩|充电站|补能|电费|便宜|速度|停车|附近', user_input) is not None

    def _rule_based_preference_analysis(self, user_input):
        preferences = {
            "priority": "distance", "distance_limit":3,
            "need_fast_charge":False, "price_sensitive":False,
            "station_name": "", "need_more_info":False, "msg":"请描述充电需求"
        }
        s = user_input.lower()
        if re.search(r'便宜|性价比|省钱',s): preferences["priority"]="price"
        elif re.search(r'快|快充|速度',s): preferences["priority"]="speed"
        elif re.search(r'环境|干净',s): preferences["priority"]="environment"
        dist = re.search(r'(\d+)(公里|km)',s)
        if dist: preferences["distance_limit"]=min(int(dist.group(1)), self.max_distance)
        
        # ====================== 扩充充电站品牌（全覆盖） ======================
        station_brands = [
            "星星充电", "特来电", "国家电网", "云快充", "小桔充电",
            "蔚来", "小鹏", "理想", "壳牌", "中国石化", "中国石油",
            "昆仑网电", "皖小能", "卫莱电", "中充服", "来点电",
            "优充星", "开迈斯", "极氪", "特斯拉", "广汽能源",
            "易佳电", "白猿", "新电途", "行星充电", "鸿电e充"
        ]
        for brand in station_brands:
            if brand in user_input:
                preferences["station_name"] = brand
                break

        if len(user_input.strip())<6: preferences["need_more_info"]=True
        return preferences

    # ====================== 过滤暂停营业的充电站 ======================
    def is_station_closed(self, station):
        name = str(station['充电站名称']).strip()
        address = str(station['具体地址']).strip()
        closed_keywords = ["暂停营业", "停业", "关闭", "停用", "拆除", "维修", "搬迁"]
        for kw in closed_keywords:
            if kw in name or kw in address:
                return True
        return False

    # ====================== 评分与过滤 ======================
    def score_station(self, station, user_location, preferences):
        if self.is_station_closed(station):
            return {"filtered": True}

        distance = self.calculate_distance(user_location['lat'],user_location['lng'],station['纬度'],station['经度'])
        if distance > preferences['distance_limit']:
            return {"filtered":True}

        name = str(station['充电站名称'])
        if preferences.get("station_name") and preferences["station_name"] not in name:
            return {"filtered":True}

        if preferences['need_fast_charge'] and "快充" not in str(station['充电桩类型']):
            return {"filtered":True}

        distance_score = 5 if distance<=1 else 4 if distance<=2 else 3 if distance<=3 else 1
        base = {
            "距离":distance_score,
            "评分":float(station['站平均评分']),
            "价格性价比":float(station['价格性价比（0-5分）']),
            "充电速度":float(station['充电速度（0-5分）']),
            "设施完整性":float(station['设施完整性（0-5分）']),
            "环境卫生":float(station['环境卫生（0-5分）'])
        }
        weights = self.score_weights.copy()
        if preferences["priority"]=="distance": weights = {"距离":0.6,"评分":0.15,"价格性价比":0.1,"充电速度":0.1,"设施完整性":0.025,"环境卫生":0.025}
        elif preferences["priority"]=="price": weights = {"价格性价比":0.5,"距离":0.2,"评分":0.15,"充电速度":0.1,"设施完整性":0.025,"环境卫生":0.025}
        elif preferences["priority"]=="speed": weights = {"充电速度":0.5,"距离":0.2,"评分":0.15,"价格性价比":0.1,"设施完整性":0.025,"环境卫生":0.025}
        total = sum(base[k]*weights[k] for k in weights)
        return {"station_info":self._format_station_info(station,distance),"score":round(total,2),"filtered":False}

    def _format_station_info(self, station, distance):
        charge_type = str(station['充电桩类型']).split(';')[-1] if ';' in str(station['充电桩类型']) else str(station['充电桩类型'])
        return {
            "id":str(station['唯一充电站ID']),"name":str(station['充电站名称']),
            "address":f"{station['行政区']}{station['具体地址']}",
            "distance":distance,"score":round(float(station['站平均评分']),1),
            "price_score":round(float(station['价格性价比（0-5分）']),1),
            "speed_score":round(float(station['充电速度（0-5分）']),1),
            "charge_type":charge_type,"phone":str(station['联系电话']) if pd.notna(station['联系电话']) else "未提供",
            "lng":float(station['经度']),"lat":float(station['纬度'])
        }

    # ====================== 主推荐逻辑（品牌严格匹配 + 近似最多5个） ======================
    def recommend_stations(self, user_input, user_location):
        if not self._is_valid_charging_request(user_input):
            return {"success":False,"pref":{},"stations":[],"other_stations":[],"msg":"请描述充电站相关需求"}
        if self.df.empty:
            return {"success":False,"pref":{},"stations":[],"msg":"暂无充电站数据"}

        pref = self.ai_parse_station_preference(user_input)
        if pref["need_more_info"]:
            return {"success":False,"pref":pref,"stations":[],"msg":pref["msg"]}

        candidates = []
        for _, st in self.df.iterrows():
            res = self.score_station(st, user_location, pref)
            if not res["filtered"]:
                candidates.append(res)

        # 无匹配时兜底
        if not candidates:
            for _, st in self.df.iterrows():
                d = self.calculate_distance(user_location['lat'],user_location['lng'],st['纬度'],st['经度'])
                candidates.append({"station_info":self._format_station_info(st,d),"score":10-d})

        candidates.sort(key=lambda x:x["score"],reverse=True)
        all_rec = [x["station_info"] for x in candidates]

        # 1. 精选推荐
        best = all_rec[:1]

        # 2. 近似匹配 = 剩余所有符合品牌要求的站点
        target_brand = pref.get("station_name", "").strip()
        if target_brand:
            # 只保留包含指定品牌的站点
            others_filtered = [
                s for s in all_rec[1:]
                if target_brand in s["name"]
            ]
        else:
            # 无品牌要求 → 正常取剩余
            others_filtered = all_rec[1:]

        # 3. 近似匹配最多 5 个
        others = others_filtered[:5]

        return {
            "success": True,
            "pref": pref,
            "stations": best,
            "other_stations": others,
            "all_recommend_stations": best + others,  # 地图只显示精准+近似，不乱跳
            "msg": "推荐成功"
        }

    def recommend_for_map(self, user_input, user_location):
        return self.recommend_stations(user_input, user_location)