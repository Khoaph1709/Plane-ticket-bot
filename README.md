# Flight Monitor đa người dùng

Đây là phiên bản nâng cấp từ crawler Selenium hiện tại. Mỗi người dùng có thể có nhiều route riêng, mỗi route có ngày bay hoặc khoảng ngày, ngưỡng giá, mức giảm tối thiểu và trạng thái bật/tắt. Một lần chạy sẽ crawl tất cả route đang bật, so sánh với snapshot trước và gửi Telegram cho đúng người nhận.

## Các nâng cấp chính

| Nhóm | Phiên bản cũ | Phiên bản mới |
| --- | --- | --- |
| Cấu hình | Route và Telegram hard-code trong Python | Cấu hình trong `config/users.json` |
| Người dùng | Một người nhận | Nhiều người, mỗi người có chat ID riêng |
| Chuyến bay | Hai route cố định | Không giới hạn số route cấu hình |
| Ngày bay | Một ngày và tự cộng 3 ngày | Một ngày hoặc khoảng ngày; return date là tùy chọn |
| Cảnh báo | Gửi lại cả khi không đổi | Cảnh báo khi có thay đổi, giá đạt ngưỡng hoặc lần chạy đầu |
| So sánh | Ghép chủ yếu theo mã chuyến bay | Ghép theo hãng + mã chuyến + giờ bay, lấy giá thấp nhất |
| Độ an toàn state | Đổi tên file trực tiếp | Ghi JSON tạm rồi đổi tên nguyên tử |
| Bí mật | Token nằm trong mã nguồn cũ | Token và chat ID lấy từ biến môi trường/Secrets |
| Vận hành | Chạy từng file thủ công | Một entrypoint `run_once.py`, sẵn sàng cho cron/GitHub Actions |

## Chạy cục bộ

Tạo môi trường Python và cài dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/users.example.json config/users.json
```

Đặt biến môi trường Telegram:

```bash
export TELEGRAM_BOT_TOKEN="TOKEN_MOI_CUA_BAN"
export TELEGRAM_CHAT_ID_OWNER="CHAT_ID_CUA_BAN"
```

Chạy thử không gửi tin:

```bash
python run_once.py --config config/users.json --state state/latest.json --dry-run
```

Muốn gửi thật, bỏ `--dry-run`:

```bash
python run_once.py --config config/users.json --state state/latest.json
```

Máy phải có Google Chrome/Chromium tương thích. Selenium 4 sử dụng Selenium Manager để tìm driver; nếu cần chỉ định browser, đặt `CHROME_BIN`.

## Cấu hình người dùng

Mỗi phần tử trong `users` là một người dùng. `chat_id_env` là tên biến môi trường chứa chat ID, còn `telegram_token_env` là tên biến chứa token bot. Thông thường mọi người có thể dùng chung một bot và chỉ khác chat ID.

```json
{
  "id": "owner",
  "name": "Người dùng chính",
  "chat_id_env": "TELEGRAM_CHAT_ID_OWNER",
  "telegram_token_env": "TELEGRAM_BOT_TOKEN",
  "enabled": true,
  "routes": [
    {
      "id": "danang-narita-20261114",
      "label": "Đà Nẵng → Narita",
      "origin": "DAD",
      "destination": "NRT",
      "depart_date": "2026-11-14",
      "depart_end": "2026-11-14",
      "return_date": null,
      "max_price": 3500000,
      "min_drop": 100000,
      "enabled": true
    }
  ]
}
```

`depart_end` cho phép theo dõi một khoảng ngày. Nếu chỉ theo dõi một ngày, đặt `depart_end` bằng `depart_date`. `max_price` là ngưỡng cảnh báo; đặt `null` nếu không cần. `min_drop` là mức giảm tối thiểu tính bằng đồng Việt Nam; đặt `0` để mọi mức giảm đều có thể tạo cảnh báo.

Không đặt token thật trong `users.json`. File này đã được thêm vào `.gitignore`; chỉ commit `users.example.json`.

## GitHub Actions

Workflow tại `.github/workflows/crawl.yml` chạy thủ công hoặc bốn lần mỗi ngày. GitHub Actions sử dụng UTC; lịch mẫu `17 0,6,12,18 * * *` tương đương khoảng 01:17, 07:17, 13:17 và 19:17 theo giờ Việt Nam.

Trong GitHub repository, tạo các Secrets sau:

| Secret | Nội dung |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Token mới của bot Telegram |
| `TELEGRAM_CHAT_ID_OWNER` | Chat ID của người dùng chính |
| `TELEGRAM_CHAT_ID_FRIEND_1` | Chat ID của người dùng thứ hai nếu bật người đó |
| `USERS_JSON_B64` | Tùy chọn; nội dung `users.json` đã mã hóa Base64 nếu không muốn commit cấu hình người dùng |

Cách dùng `USERS_JSON_B64`:

```bash
base64 -w 0 config/users.json
```

Copy kết quả vào Secret `USERS_JSON_B64`. Nếu không tạo Secret này, workflow sẽ dùng `config/users.json` đã commit; file đó không nên chứa token, nhưng có thể chứa route và tên biến môi trường.

Sau khi push code, vào **Actions → Flight price monitor → Run workflow** để chạy thử. Kiểm tra log trước khi chờ lịch tự động. State mới được ghi vào `state/latest.json` và commit trở lại repository; không đưa `state/latest.json` vào public repository nếu không muốn lộ lịch sử giá cá nhân.

## Lưu ý về Atadi và route một chiều

Crawler tách hai chặng thành hai route độc lập, ví dụ `DAD.NRT` và `KIX.DAD`. URL Atadi hiện có tham số chứa hai ngày; với route không có `return_date`, code dùng cùng ngày cho hai phần ngày và giữ `leg=0` theo hợp đồng của crawler cũ. Cần chạy `--dry-run` hoặc workflow thủ công để xác nhận kết quả thực tế sau khi Atadi thay đổi giao diện. Nếu giao diện thay đổi, phần cần sửa chủ yếu là selector `.flightTicket` và hàm `parse_ticket_text()` trong `atadi_crawler.py`.

## Kiểm thử

Chạy bộ test thuần Python, không cần mở Chrome:

```bash
python -m unittest discover -s tests -v
```

Bộ test kiểm tra cấu hình đa người dùng, khoảng ngày, xử lý nhiều mức giá trùng chuyến, ngưỡng cảnh báo và ghi state an toàn.

## Lộ trình nâng cấp tiếp theo

Phiên bản này phù hợp cho một repository do bạn quản lý, trong đó người dùng được thêm bằng cách chỉnh `users.json`. Nếu bạn muốn người dùng tự đăng nhập vào một website rồi tự tạo route mà không sửa file, bước tiếp theo nên là xây dựng dashboard có xác thực, database và job scheduler riêng. Khi đó GitHub Actions không còn là lựa chọn lý tưởng cho từng người dùng độc lập, vì Secrets của repository thuộc về chủ repository; nên chuyển phần cấu hình và lịch chạy sang một backend có database.
