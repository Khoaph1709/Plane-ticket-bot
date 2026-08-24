import time
import re
import json 
import os
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# ================= CẤU HÌNH CHUNG =================
CHROME_PATH = "/usr/bin/google-chrome" 

# CẤU HÌNH 2 CHIỀU BAY
TRIPS = [
    {
        "key": "outbound", # Khóa để lưu vào JSON
        "name": "CHIỀU ĐI (HAN -> DAD)",
        "route": "HAN.DAD",
        "start": "2026-02-02",
        "end": "2026-02-02" # Cập nhật theo ý bạn
    },
    {
        "key": "inbound",
        "name": "CHIỀU VỀ (DAD -> HAN)",
        "route": "DAD.HAN",
        "start": "2026-03-02",
        "end": "2026-03-02"
    }
]

SKIP_COUNT = 3 
TAKE_COUNT = 5 

AIRLINE_MAP = {
    "VJ": "Vietjet Air", "VN": "Vietnam Airlines", 
    "QH": "Bamboo Airways", "VU": "Vietravel Airlines", "JQ": "Jetstar Pacific"
}

# ... (GIỮ NGUYÊN HÀM init_driver và parse_ticket_text) ...
def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.page_load_strategy = 'eager' 
    if CHROME_PATH:
        chrome_options.binary_location = CHROME_PATH
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def parse_ticket_text(raw_text):
    info = {"airline": "Unknown", "code": "Unknown", "time": "Unknown", "price": 0}
    code_match = re.search(r'([A-Z]{2}\d{3,4})', raw_text)
    if code_match:
        info["code"] = code_match.group(1)
        info["airline"] = AIRLINE_MAP.get(info["code"][:2], "Hãng khác")
    time_matches = re.findall(r'(\d{2}:\d{2})', raw_text)
    if time_matches:
        info["time"] = time_matches[0]
    price_match = re.search(r'([\d\.]+)[₫d]', raw_text)
    if price_match:
        try:
            info["price"] = int(price_match.group(1).replace(".", ""))
        except: pass
    return info

# ================= HÀM TẠO URL (ĐÃ CẬP NHẬT THAM SỐ ROUTE) =================
def generate_atadi_url(route, date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    dep_date = date_obj.strftime("%Y%m%d")
    ret_date = (date_obj + timedelta(days=3)).strftime("%Y%m%d")
    # Sử dụng biến route truyền vào thay vì biến toàn cục
    url = f"https://atadi.vn/tim-ve-may-bay?ap={route}&dt={dep_date}.{ret_date}&ps=1.0.0&leg=0"
    return url

# ================= HÀM CÀO 1 NGÀY (ĐÃ CẬP NHẬT THAM SỐ ROUTE) =================
def scrape_single_day(driver, route, date_str):
    url = generate_atadi_url(route, date_str)
    driver.set_page_load_timeout(30)
    
    print(f"\n   -> Quét ngày: {date_str} ({route})")
    
    try:
        driver.get(url)
    except TimeoutException:
        driver.execute_script("window.stop();")

    wait = WebDriverWait(driver, 20)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".flightTicket")))
        time.sleep(5)
    except:
        print(f"   ❌ Không tìm thấy vé.")
        return []

    results = []
    tickets = driver.find_elements(By.CSS_SELECTOR, ".flightTicket")
    total = len(tickets)
    
    if total <= SKIP_COUNT:
        return []

    for i in range(SKIP_COUNT, min(SKIP_COUNT + TAKE_COUNT, total)):
        try:
            ticket = tickets[i]
            raw_text = ticket.text or ticket.get_attribute("innerText")
            data = parse_ticket_text(raw_text)
            data["date"] = date_str 
            
            if data["price"] > 0:
                results.append(data)
        except Exception:
            pass
    
    print(f"      Lấy được {len(results)} vé.")
    return results

def get_date_range(start, end):
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    delta = end_dt - start_dt
    dates = []
    for i in range(delta.days + 1):
        day = start_dt + timedelta(days=i)
        dates.append(day.strftime("%Y-%m-%d"))
    return dates

if __name__ == "__main__":
    # 1. XOAY VÒNG FILE CŨ
    if os.path.exists("dulieu_ve.json"):
        if os.path.exists("dulieu_ve_cu.json"):
            os.remove("dulieu_ve_cu.json")
        os.rename("dulieu_ve.json", "dulieu_ve_cu.json")
        print("🗂️ Đã sao lưu dữ liệu cũ.")

    driver = init_driver()
    
    # Biến chứa toàn bộ dữ liệu 2 chiều
    master_data = {} 

    try:
        # 2. CHẠY VÒNG LẶP QUA CÁC CHUYẾN ĐI (Outbound -> Inbound)
        for trip in TRIPS:
            trip_key = trip["key"]
            trip_name = trip["name"]
            route = trip["route"]
            
            print(f"\n🚀 BẮT ĐẦU QUÉT: {trip_name}")
            
            dates = get_date_range(trip["start"], trip["end"])
            trip_results = {}
            
            for d in dates:
                # Gọi hàm cào với route cụ thể
                data = scrape_single_day(driver, route, d)
                trip_results[d] = data
                time.sleep(2) # Nghỉ giữa các ngày
            
            # Lưu vào cục dữ liệu tổng
            master_data[trip_key] = {
                "info": trip, # Lưu thông tin hành trình để report dùng
                "data": trip_results
            }

        # 3. LƯU FILE
        with open("dulieu_ve.json", "w", encoding="utf-8") as f:
            json.dump(master_data, f, ensure_ascii=False, indent=4)
        print("\n✅ Đã hoàn tất và lưu file dữ liệu mới.")

    finally:
        driver.quit()