from flask import Flask, render_template, request, jsonify
from car_recommendation import CarRecommendation
from charging_station_processor import ChargingStationProcessor
import os
import pandas as pd
from dotenv import load_dotenv
import warnings
import qrcode
import uuid

warnings.filterwarnings('ignore', category=UserWarning, module='requests')
load_dotenv()

app = Flask(__name__)
app.secret_key = "charging_station_2025_secret_key"

APP_PORT = int(os.getenv("APP_PORT", 5000))
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
DEFAULT_LAT = float(os.getenv("DEFAULT_LATITUDE", 31.86))
DEFAULT_LNG = float(os.getenv("DEFAULT_LONGITUDE", 117.28))

PUBLIC_URL = "公网穿透网址"
QR_CODE_PATH = "static/qrcode.png"

def generate_qrcode(url):
    try:
        os.makedirs("static", exist_ok=True)
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(QR_CODE_PATH)
        print(f"二维码已生成：{QR_CODE_PATH}")
    except Exception as e:
        print(f"二维码生成失败：{str(e)}")

generate_qrcode(PUBLIC_URL)

def validate_config():
    required_vars = ["DOUBAO_API_KEY", "DOUBAO_ENDPOINT_ID"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print("缺少必要配置: " + ", ".join(missing_vars))
    else:
        print("配置验证通过")

station_data_path = os.path.join(os.path.dirname(__file__), "data", "全量充电站特征分数_补全版.csv")
if not os.path.exists(os.path.dirname(station_data_path)):
    os.makedirs(os.path.dirname(station_data_path))

car_recommender = None    
station_processor = None
app.map_storage = {}

try:
    car_recommender = CarRecommendation()
    print("汽车推荐模块初始化成功")
    
    if os.path.exists(station_data_path):
        station_processor = ChargingStationProcessor(data_path=station_data_path)
        print("充电站推荐模块初始化成功（本地数据）")
    else:
        station_processor = ChargingStationProcessor(data_path=None)
        print("使用AI模式推荐充电站")
        
except Exception as e:
    print("模块初始化警告: " + str(e))

with app.app_context():
    validate_config()

@app.route('/')
def index():
    qr_exists = os.path.exists(QR_CODE_PATH)
    return render_template('index.html', public_url=PUBLIC_URL, qr_exists=qr_exists)

@app.route('/api/recommend-car', methods=['POST'])
def recommend_car():
    try:
        if not car_recommender:
            return jsonify({'success': False,'message': '汽车推荐模块未初始化'})
        data = request.json
        user_input = data.get('user_input', '').strip()
        if not user_input:
            return jsonify({'success': False,'message': '请输入购车需求'})
        recommendation = car_recommender.generate_recommendation(user_input)
        return jsonify({'success': True,'recommendation': recommendation})
    except Exception as e:
        return jsonify({'success': False,'message': '服务异常，请稍后重试'})

@app.route('/api/recommend-station', methods=['POST'])
def recommend_station():
    try:
        if not station_processor:
            return jsonify({'success': False,'message': '充电站模块未初始化'})
        data = request.json
        user_input = data.get('user_input', '').strip()
        user_lat = float(data.get('latitude', DEFAULT_LAT))
        user_lng = float(data.get('longitude', DEFAULT_LNG))
        if not user_input:
            return jsonify({'success': False,'message': '请输入充电需求'})
        recommendation = station_processor.recommend_stations(user_input, {'lat': user_lat, 'lng': user_lng})
        return jsonify({'success': True,'recommendation': recommendation})
    except Exception as e:
        return jsonify({'success': False,'message': '错误：' + str(e)[:100]})

@app.route('/api/get-location', methods=['GET'])
def get_location():
    return jsonify({"latitude": DEFAULT_LAT,"longitude": DEFAULT_LNG,"city": "合肥市"})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "running",
        "modules": {"car": "ok" if car_recommender else "no","station": "ok" if station_processor else "no"}
    })
    
@app.route('/api/recommend-station-map', methods=['POST'])
def recommend_station_map():
    try:
        if not station_processor:
            return jsonify(success=False, message='充电站模块未初始化')
        data = request.json
        user_input = data.get('user_input', '').strip()
        user_lat = float(data.get('latitude', DEFAULT_LAT))
        user_lng = float(data.get('longitude', DEFAULT_LNG))
        
        if not user_input:
            return jsonify(success=False, message='请输入充电需求')
        
        result = station_processor.recommend_for_map(user_input, {'lat': user_lat, 'lng': user_lng})
        return jsonify(result)
    except Exception as e:
        return jsonify(success=False, message=str(e)[:100])

@app.route("/api/save-map-data", methods=["POST"])
def save_map_data():
    data = request.json
    sid = str(uuid.uuid4())
    app.map_storage[sid] = data
    return jsonify({"sid": sid})

@app.route("/api/get-map-data/<sid>")
def get_map_data(sid):
    return jsonify(app.map_storage.get(sid, {}))

@app.route('/map')
def show_map():
    return render_template('map.html')

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    print("\n新能源汽车AI助手 启动成功")
    print(f"本地访问：http://127.0.0.1:{APP_PORT}")
    print(f"公网访问：{PUBLIC_URL}")
    print(f"二维码路径：{os.path.abspath(QR_CODE_PATH)}\n")
    
    app.run(debug=False, threaded=True, host='0.0.0.0', port=5000)