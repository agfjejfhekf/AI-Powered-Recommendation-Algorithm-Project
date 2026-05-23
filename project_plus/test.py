import json
from collections import defaultdict

def check_duplicate_car_ids(json_file_path):
    """
    检查汽车数据库JSON文件：重复ID + 统计总数量/唯一ID数量
    :param json_file_path: JSON文件路径
    """
    id_counter = defaultdict(int)
    duplicate_ids = []
    total_cars = 0  # 总车辆条数

    try:
        # 读取JSON文件
        with open(json_file_path, 'r', encoding='utf-8') as f:
            car_data = json.load(f)

        # 遍历所有分类统计
        price_categories = ['low_price', 'mid_price', 'high_price']
        for category in price_categories:
            car_list = car_data.get(category, [])
            for car in car_list:
                total_cars += 1
                car_id = car.get('id')
                if car_id:
                    id_counter[car_id] += 1

        # 筛选重复ID
        for car_id, count in id_counter.items():
            if count > 1:
                duplicate_ids.append((car_id, count))

        # 计算唯一ID数量
        unique_id_count = len(id_counter)

        # 输出结果
        print("=" * 60)
        print(f"汽车数据库统计结果")
        print(f"总车辆条目数：{total_cars} 条")
        print(f"唯一不重复ID总数：{unique_id_count} 个")
        print("=" * 60)

        if duplicate_ids:
            print(f"发现 {len(duplicate_ids)} 个重复ID：")
            for idx, (dup_id, count) in enumerate(duplicate_ids, 1):
                print(f"{idx}. ID: {dup_id} | 重复 {count} 次")
        else:
            print("未发现重复ID！所有ID均唯一合规！")
        
        # 数据一致性校验
        if total_cars == unique_id_count:
            print("数据完全合规：总条数 = 唯一ID数，无任何重复！")
        else:
            print(f"数据异常：总条数与唯一ID数不匹配，存在重复！")
        print("=" * 60)

    except FileNotFoundError:
        print(f"未找到文件 {json_file_path}")
    except json.JSONDecodeError:
        print(f"JSON文件格式错误！")
    except Exception as e:
        print(f"{str(e)}")

# ====================== 你的文件路径（无需修改） ======================
JSON_FILE = r"C:/Users/luhao/Desktop/test_AI/新能源AI助手_公网传统_充电站推荐升级_购车推荐升级/car_database.json"
# ====================================================================

if __name__ == '__main__':
    check_duplicate_car_ids(JSON_FILE)