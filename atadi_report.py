import json
import requests
import os
import time
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================= CẤU HÌNH =================
TELEGRAM_TOKEN = "7741373193:AAEv3Yyo6ismT5px86glSC4FvcJilDWeLRU"
TELEGRAM_CHAT_ID = "6081012780"

FILE_NEW = "dulieu_ve.json"
FILE_OLD = "dulieu_ve_cu.json"

# --- HÀM GỬI TIN NHẮN MẠNH MẼ HƠN (SỬA LỖI SSL/MẠNG) ---
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Cấu hình chiến thuật thử lại (Retry Strategy)
    # total=5: Thử lại tối đa 5 lần
    # backoff_factor=1: Lần 1 chờ 1s, lần 2 chờ 2s, lần 3 chờ 4s... (để mạng ổn định lại)
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    try:
        if len(message) > 4000:
            parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for part in parts:
                data = {"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": "Markdown"}
                session.post(url, data=data, timeout=30) # Timeout 30s để không bị treo
                time.sleep(1)
        else:
            data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
            session.post(url, data=data, timeout=30)
            
    except Exception as e:
        print(f"⚠️ Lỗi khi gửi Telegram: {e}")
        # Không crash chương trình, chỉ in lỗi để log lại

def get_flight_history(flight_list):
    history = {}
    for f in flight_list:
        code = f['code']
        price = f['price']
        if code not in history:
            history[code] = []
        history[code].append(price)
    return history

def generate_route_report(trip_key, new_data_full, old_data_full):
    if trip_key not in new_data_full:
        return None

    trip_info = new_data_full[trip_key]["info"]
    flights_new_dict = new_data_full[trip_key]["data"]
    
    flights_old_dict = {}
    if trip_key in old_data_full:
        flights_old_dict = old_data_full[trip_key]["data"]

    trip_name = trip_info["name"]
    now = datetime.now().strftime("%H:%M %d/%m")
    
    msg = f"✈️ **{trip_name}**\n🕒 Cập nhật: {now}\n"
    has_data = False

    for date_str, flights_new in flights_new_dict.items():
        if not flights_new: continue
        has_data = True

        flights_old = flights_old_dict.get(date_str, [])
        history_old = get_flight_history(flights_old)
        
        pretty_date = date_str.split("-")[2] + "/" + date_str.split("-")[1]
        msg += f"\n📅 **{pretty_date}:**\n"
        
        min_price_today = min(f['price'] for f in flights_new)
        
        for f in flights_new:
            code = f['code']
            price_now = f['price']
            old_prices_list = history_old.get(code, [])
            
            change_icon = ""
            diff_text = ""
            
            if not old_prices_list:
                change_icon = "🆕"
            elif price_now in old_prices_list:
                change_icon = "➖"
                old_prices_list.remove(price_now)
            else:
                # Nếu list cũ rỗng (có thể do lỗi logic trước đó), coi như min là giá hiện tại
                if old_prices_list:
                    min_old = min(old_prices_list)
                else:
                    min_old = price_now
                    
                diff = price_now - min_old
                if diff > 0:
                    change_icon = "🔺"
                    diff_text = f"(+{diff/1000:,.0f}k)"
                elif diff < 0:
                    change_icon = "🔻🔥"
                    diff_text = f"({diff/1000:,.0f}k)"
                else:
                    change_icon = "➖"

            airline_icon = "🔴" if "Vietjet" in f['airline'] else "🔷" if "Vietnam" in f['airline'] else "🎋"
            price_str = "{:,.0f}".format(price_now).replace(",", ".")
            
            line = f"   {airline_icon} {price_str} {change_icon} {diff_text} | {f['time']}\n"
            if price_now == min_price_today:
                line = f"   {airline_icon} *{price_str}* {change_icon} {diff_text} | {f['time']}\n"
                
            msg += line

    if has_data:
        return msg
    else:
        return f"✈️ **{trip_name}**\n⚠️ Không tìm thấy vé nào."

def create_comparison_report():
    if not os.path.exists(FILE_NEW):
        print("Chưa có dữ liệu mới.")
        return
    
    with open(FILE_NEW, "r", encoding="utf-8") as f:
        data_new = json.load(f)

    data_old = {}
    if os.path.exists(FILE_OLD):
        try:
            with open(FILE_OLD, "r", encoding="utf-8") as f:
                data_old = json.load(f)
        except: pass

    print("Đang tạo báo cáo chiều đi...")
    msg_out = generate_route_report("outbound", data_new, data_old)
    if msg_out:
        send_telegram_message(msg_out)
        time.sleep(2) # Nghỉ 2s trước khi gửi tin tiếp theo
    
    print("Đang tạo báo cáo chiều về...")
    msg_in = generate_route_report("inbound", data_new, data_old)
    if msg_in:
        send_telegram_message(msg_in)

    print("✅ Đã gửi xong báo cáo (hoặc đã xử lý lỗi mạng)!")

if __name__ == "__main__":
    create_comparison_report()