import requests
import json

# ======================================================
# DÁN TOKEN BẠN VỪA LẤY TỪ BOTFATHER VÀO ĐÂY
TOKEN = "7741373193:AAEv3Yyo6ismT5px86glSC4FvcJilDWeLRU" 
# Ví dụ: "123456:ABC-DEF..."
# ======================================================

def get_chat_id():
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data["ok"] == True:
            if len(data["result"]) > 0:
                # Lấy tin nhắn mới nhất
                last_msg = data["result"][-1]
                chat_id = last_msg["message"]["chat"]["id"]
                user_name = last_msg["message"]["chat"].get("first_name", "User")
                
                print("\n" + "="*40)
                print(f"✅ TÌM THẤY RỒI!")
                print(f"👤 Người nhắn: {user_name}")
                print(f"🆔 CHAT ID CỦA BẠN LÀ: {chat_id}")
                print("="*40 + "\n")
                print("👉 Hãy copy số này dán vào biến TELEGRAM_CHAT_ID trong code vé máy bay.")
            else:
                print("⚠️ Bot hoạt động tốt, nhưng chưa thấy tin nhắn nào.")
                print("👉 Hãy mở Telegram, tìm con bot của bạn và nhắn 'hello' cho nó rồi chạy lại code này.")
        else:
            print("❌ Token sai hoặc lỗi kết nối.")
            print("Lỗi:", data)
            
    except Exception as e:
        print("❌ Có lỗi xảy ra:", e)

if __name__ == "__main__":
    get_chat_id()