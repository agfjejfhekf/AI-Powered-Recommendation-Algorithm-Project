import json
import re
import os
import requests
from dotenv import load_dotenv

load_dotenv()

class CarRecommendation:
    def __init__(self):
        self.load_config()
        self.load_car_database()

    def load_config(self):
        self.base_weights = {
            "price": 0.2, "scene": 0.4, "body": 0.2, "energy": 0.2
        }
        self.api_key = os.getenv("DOUBAO_API_KEY")
        self.endpoint_id = os.getenv("DOUBAO_ENDPOINT_ID")
        self.api_url = "高德地图api网址"
        self.ai_available = all([self.api_key, self.endpoint_id])

    def load_car_database(self):
        try:
            with open("car_database.json", "r", encoding="utf-8") as f:
                self.car_db = json.load(f)
            self.all_cars = []
            for cat in ["low_price", "mid_price", "high_price"]:
                self.all_cars.extend(self.car_db.get(cat, []))
        except:
            self.all_cars = []

    # ====================== 大模型解析用户意图 ======================
    def ai_parse_preference(self, user_input):
        if not self.ai_available:
            return self.parse_preference(user_input)
#撰写提示词
        prompt = f"""
你是汽车推荐意图解析器，只返回JSON，不要其他文字。
从用户输入提取：
- budget_min, budget_max（数字，单位万）
- priority：family/price/speed/luxury/normal
- brand：品牌名，没有则为空字符串
- need_more_info：true/false（信息是否太少）
- reason：文字说明（用于前端提示）

用户输入：{user_input}
""".strip()

        try:
            resp = requests.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.endpoint_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                },
                timeout=5
            )
            res = resp.json()
            content = res["choices"][0]["message"]["content"]
            data = json.loads(content)

            rule_pref = self.parse_preference(user_input)
            merged = {
                "priority": data.get("priority", rule_pref["priority"]),
                "budget_min": int(data.get("budget_min", rule_pref["budget_min"])),
                "budget_max": int(data.get("budget_max", rule_pref["budget_max"])),
                "brand": data.get("brand", "").strip(),
                "need_more_info": data.get("need_more_info", False),
                "reason": data.get("reason", "")
            }
            return merged
        except:
            return self.parse_preference(user_input)

    def extract_budget(self, user_input):
        user = user_input.lower()
        range_match = re.search(r'(\d+)\s*[-到至]\s*(\d+)\s*万', user)
        budget_match = re.search(r'预算\s*(\d+)\s*万', user)
        around_match = re.search(r'(\d+)\s*万(左右|上下|约)', user)
        if range_match:
            return int(range_match.group(1)), int(range_match.group(2))
        if budget_match:
            n = int(budget_match.group(1))
            return n, n
        if around_match:
            n = int(around_match.group(1))
            return max(n-5, 0), n+5
        return 15, 30

    def parse_preference(self, user_input):
        user = user_input.lower()
        pref = {"priority": "normal", "budget_min": 0, "budget_max": 0,
                "brand": "", "need_more_info": False, "reason": ""}
        pref["budget_min"], pref["budget_max"] = self.extract_budget(user_input)

        if re.search(r'便宜|性价比|省钱|经济', user):
            pref["priority"] = "price"
        elif re.search(r'家用|空间|舒适|安全|三口|四口', user):
            pref["priority"] = "family"
        elif re.search(r'商务|豪华|面子|品牌', user):
            pref["priority"] = "luxury"
        elif re.search(r'快|动力|加速|性能', user):
            pref["priority"] = "speed"

        brands = [
            "比亚迪", "特斯拉", "蔚来", "小鹏", "理想", "广汽埃安", "AION",
            "哪吒", "五菱", "长安", "吉利", "几何", "零跑", "创维", "捷途",
            "东风", "奔腾", "红旗", "本田", "丰田", "大众", "沃尔沃", "保时捷",
            "宝马", "奔驰", "奥迪", "高合", "极氪", "问界", "小米", "深蓝",
            "宝骏", "大运", "中兴", "开瑞", "江淮", "江铃", "赛力斯", "传祺"
        ]
        for b in brands:
            if b in user_input:
                pref["brand"] = b

        # 规则判断信息过少
        if len(user_input.strip()) < 6:
            pref["need_more_info"] = True
            pref["reason"] = "请告诉我你的预算、用途或品牌哦"
        return pref

    def hard_filter(self, cars, pref):
        res = []
        for car in cars:
            try:
                price = float(re.findall(r'[\d.]+', car["price"])[0])
                if not (pref["budget_min"] <= price <= pref["budget_max"]):
                    continue
                if pref.get("brand") and pref["brand"] not in car["name"]:
                    continue
            except:
                continue
            res.append(car)
        res = res
        return res

    def score_and_sort(self, cars, pref):
        scored = []
        for car in cars:
            score = 0
            if pref["priority"] == "price":
                scene_p, price_p = 0.2, 0.6
            elif pref["priority"] == "family":
                scene_p, price_p = 0.7, 0.1
            elif pref["priority"] in ["luxury", "speed"]:
                scene_p, price_p = 0.3, 0.2
            else:
                scene_p, price_p = 0.4, 0.2

            scenes = car.get("usage_scene", [])
            scene_score = 10 if ("家用" in scenes and pref["priority"] == "family") else 8 if "家用" in scenes else 5
            mid = (pref["budget_min"] + pref["budget_max"]) / 2
            price_score = 10 - abs((float(re.findall(r'[\d.]+', car["price"])[0]) - mid) / 5)
            score = scene_score * scene_p + price_score * price_p
            scored.append((car, round(score, 2)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in scored[:3]]

    def build_result(self, title, cars):
        text = f"{title}\n\n"
        for i, car in enumerate(cars, 1):
            text += f"{i}. {car['name']}\n价格：{car['price']}\n"
            text += f"车型：{car.get('body_type', '')} | {car.get('energy_type', '')}\n"
            text += f"续航：{car.get('range', 0)}km\n"
            text += f"优势：{'、'.join(car.get('advantage_tags', []))}\n\n"
        return text

    def generate_recommendation(self, user_input):
        if not user_input.strip():
            return "请告诉我您的购车需求，我会为您推荐合适的车型。"

        pref = self.ai_parse_preference(user_input)
        if pref["need_more_info"]:
            return pref["reason"]

        o_min, o_max = pref["budget_min"], pref["budget_max"]
        matched = self.hard_filter(self.all_cars, pref)
        ranked = self.score_and_sort(matched, pref)

        if ranked:
            title = f"为您推荐{o_min}至{o_max}万的车型（推荐可能没有完全匹配您的需求，请谅解）"
            if pref.get("brand"):
                title += f"（品牌：{pref['brand']}）"
            return self.build_result(title, ranked)

        # 安全兜底：只有用户没指定预算，才放宽
        has_budget = o_min != 15 or o_max != 30
        if pref.get("brand") and not has_budget:
            brand_cars = [car for car in self.all_cars if pref["brand"] in car["name"]]
            if brand_cars:
                prices = [float(re.findall(r'[\d.]+', car["price"])[0]) for car in brand_cars]
                brand_min = min(prices)
                brand_max = max(prices)
                fallback_pref = pref.copy()
                fallback_pref["budget_min"] = max(brand_min - 5, 0)
                fallback_pref["budget_max"] = brand_max + 5
                fallback_ranked = self.score_and_sort(brand_cars, fallback_pref)
                if fallback_ranked:
                    return f"为您推荐{pref['brand']}品牌车型（推荐可能没有完全匹配您的需求，请谅解）：\n\n" + self.build_result("", fallback_ranked)

        # 普通兜底
        fallback_pref = pref.copy()
        fallback_pref["budget_min"] = max(o_min - 10, 0)
        fallback_pref["budget_max"] = o_max + 10
        fallback_cars = self.hard_filter(self.all_cars, fallback_pref)
        fallback_ranked = self.score_and_sort(fallback_cars, pref)

        if fallback_ranked:
            return "暂时没有完全匹配的车型，为您推荐相近款式：\n" + self.build_result("", fallback_ranked)

        return "暂时没有符合您需求的车型"