# Flight Monitor đa người dùng với Trip.com

Đây là phiên bản crawler Selenium theo dõi giá vé trên Trip.com. Mỗi người dùng có thể có nhiều route riêng, mỗi route có ngày bay hoặc khoảng ngày, ngưỡng giá, mức giảm tối thiểu và trạng thái bật/tắt. Mỗi lần chạy sẽ tìm chuyến **một chiều**, so sánh với snapshot trước và gửi Telegram cho đúng người nhận khi có thay đổi đáng chú ý.

## Các nâng cấp chính

| Nhóm | Chức năng |
| --- | --- |
| Nguồn dữ liệu | Trip.com, locale `vi-VN`, tiền tệ `VND` |
| Kiểu hành trình | Mỗi route là một tìm kiếm một chiều, dùng `triptype=ow`; không gửi `rdate` |
| Cấu hình | Route và ngày được khai báo trong `config/users.json` |
| Người dùng | Nhiều người, mỗi người có chat ID Telegram riêng |
| Chuyến bay | Không giới hạn số route cấu hình |
| Cảnh báo | Giá thấp nhất, ngưỡng giá tối đa, mức giảm tối thiểu |
| So sánh | Theo hãng + mã chuyến + giờ khởi hành, lấy giá thấp nhất nếu trùng |
| DOM động | Chờ `.result-item.J_FlightItem` và lưu HTML/screenshot chẩn đoán khi không có card |
| State | Ghi snapshot bằng atomic write, không làm hỏng file khi tiến trình bị dừng |
| Bảo mật | Token/chat ID chỉ lấy từ biến môi trường hoặc GitHub Secrets |
| Kiểm thử | Có unit test parser, giá VND, fallback và logic cảnh báo |

## Chạy cục bộ

Tạo môi trường Python và cài dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/users.example.json config/users.json
```

Trên Linux nếu dùng Chromium:

```bash
export CHROME_BIN=/usr/bin/chromium
```

Chạy thử crawler mà **không gửi Telegram**:

```bash
python run_once.py \
  --config config/users.json \
  --state state/latest.json \
  --dry-run
```

`--dry-run` vẫn mở Trip.com và ghi state mới, nhưng chỉ in báo cáo ra terminal. Vì vậy đây là lệnh nên chạy trước để kiểm tra crawler.

Muốn gửi thật sau khi crawler đã trả dữ liệu:

```bash
export TELEGRAM_BOT_TOKEN="TOKEN_MOI_CUA_BAN"
export TELEGRAM_CHAT_ID_KHOAFUNG="CHAT_ID_CUA_BAN"
python run_once.py --config config/users.json --state state/latest.json
```

## Cấu hình Trip.com một chiều

Mỗi phần tử trong `users` là một người dùng. `chat_id_env` là tên biến môi trường chứa chat ID, còn `telegram_token_env` là tên biến môi trường chứa token bot. Thông thường nhiều người có thể dùng chung một bot và chỉ khác chat ID.

Ví dụ cho hai chặng open-jaw:

```json
{
  "defaults": {
    "top_n": 5,
    "skip_count": 0,
    "wait_seconds": 40
  },
  "users": [
    {
      "id": "owner",
      "name": "Người dùng chính",
      "chat_id_env": "TELEGRAM_CHAT_ID_KHOAFUNG",
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
          "nonstop_only": false,
          "enabled": true
        },
        {
          "id": "kansai-danang-20261122",
          "label": "Osaka Kansai → Đà Nẵng",
          "origin": "KIX",
          "destination": "DAD",
          "depart_date": "2026-11-22",
          "depart_end": "2026-11-22",
          "return_date": null,
          "max_price": 3500000,
          "min_drop": 100000,
          "nonstop_only": false,
          "enabled": true
        }
      ]
    }
  ]
}
```

Crawler sẽ tự tạo URL một chiều dạng:

```text
https://vn.trip.com/flights/showfarefirst?dcity=dad&acity=tyo&ddate=2026-11-14&dairport=dad&aairport=nrt&triptype=ow&class=y&locale=vi-VN&curr=VND
```

Với KIX → DAD, crawler dùng `dcity=kix`, `acity=dad`, `dairport=kix`, `aairport=dad`, `triptype=ow` và ngày `2026-11-22`. `return_date` được giữ trong schema để tương thích về sau nhưng hiện không được dùng khi route là một chiều.

`depart_end` cho phép theo dõi một khoảng ngày. Nếu chỉ theo dõi một ngày, đặt `depart_end` bằng `depart_date`. `max_price` và `min_drop` đều tính bằng **VND**; đặt `max_price` là `null` nếu không cần cảnh báo theo ngưỡng.

## Parser Trip.com

Trip.com tải kết quả bằng JavaScript. Crawler chờ các card `.result-item.J_FlightItem`, sau đó đọc hãng, mã chuyến nếu Trip.com render trong card, giờ đi/đến, sân bay, thời gian bay, điểm dừng và giá. Một số card đầu tiên không render mã chuyến trong DOM; khi đó trường `code` được ghi là `N/A` thay vì suy đoán. Giá dạng `14.296.000₫` được chuẩn hóa thành số nguyên `14296000` và lưu với trường `currency: "VND"`.

Crawler không dùng `skip_count` để bỏ qua các card Trip.com. Giá trị này chỉ còn trong schema để tương thích cấu hình cũ; mọi card kết quả Trip.com đều được xem xét rồi sắp xếp theo giá. Nếu không tìm thấy card sau thời gian chờ, crawler lưu HTML và screenshot trong `debug_artifacts/` để xem nguyên nhân.

## GitHub Actions

Workflow tại `.github/workflows/crawl.yml` chạy thủ công hoặc bốn lần mỗi ngày. GitHub Actions dùng UTC; lịch mẫu `17 0,6,12,18 * * *` tương đương khoảng 01:17, 07:17, 13:17 và 19:17 theo giờ Việt Nam.

Tạo các Secrets trong **Settings → Secrets and variables → Actions**:

| Secret | Nội dung |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Token mới của bot Telegram |
| `TELEGRAM_CHAT_ID_KHOAFUNG` | Chat ID của người dùng chính |
| `TELEGRAM_CHAT_ID_LAM` | Chat ID của Mợ Lam |
| `TELEGRAM_CHAT_ID_OWNER` | Tên cũ, chỉ giữ để tương thích cấu hình cũ |
| `TELEGRAM_CHAT_ID_FRIEND_1` | Tên cũ, chỉ giữ để tương thích cấu hình cũ |
| `USERS_JSON_B64` | Tùy chọn; nội dung `users.json` đã mã hóa Base64 |

Nếu `users.json` chỉ chứa route và tên biến môi trường, bạn có thể commit file này. Nếu muốn giữ cấu hình người dùng ngoài repository, chạy:

```bash
base64 -w 0 config/users.json
```

Sau đó lưu kết quả vào Secret `USERS_JSON_B64`. Workflow sẽ giải mã secret thành `config/users.json` trước khi chạy.

## Kiểm thử

Chạy unit test không mở browser:

```bash
python -m unittest discover -s tests -v
```

Chạy crawler thật nhưng không gửi Telegram:

```bash
CHROME_BIN=/usr/bin/chromium python run_once.py \
  --config config/users.json \
  --state state/latest.json \
  --dry-run
```

Không đặt token Telegram khi chạy dry-run. Khi chạy thật, nếu thiếu biến môi trường, chương trình sẽ báo rõ tên biến đang thiếu thay vì im lặng.

## Lưu ý vận hành

Trip.com có thể thay đổi class DOM hoặc cơ chế tải dữ liệu. Không nên xem state rỗng là bằng chứng chắc chắn không có chuyến bay; hãy kiểm tra log và thư mục `debug_artifacts/`. Không commit thư mục chẩn đoán, token, `.env` hoặc file `config/users.json` chứa thông tin cá nhân.

Giá và số lượng chuyến bay trong kết quả là dữ liệu động tại thời điểm crawl. Crawler có nhiệm vụ theo dõi và thông báo, không đảm bảo giá còn tồn tại khi bạn mở trang đặt vé.
