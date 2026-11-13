# Luồng xe theo trạm ở Jersey City

Tháng 1/2025 · Python · SQLite · Jupyter

**Grove St PATH là trạm ưu tiên kiểm tra**, với 23 ngày trong tuần có ít nhất một giờ cao điểm mà lượt đi vượt lượt đến. Trong giờ 18:00–19:00, cộng riêng các ngày có chênh lệch dương, trạm ghi nhận 445 lượt đi và 120 lượt đến.

| Hạng | Trạm | Ngày có giờ cao điểm dương | Tổng chênh lệch dương | Giờ lặp lại nhiều nhất |
|---|---|---:|---:|---|
| 1 | Grove St PATH | 23 | 851 | 18:00–19:00 |
| 2 | Bergen Ave & Sip Ave | 23 | 324 | 18:00–19:00 |
| 3 | Brunswick St | 23 | 196 | 08:00–09:00 |
| 4 | McGinley Square | 23 | 171 | 08:00–09:00 |
| 5 | Brunswick & 6th | 23 | 154 | 07:00–08:00 |

[Bản đồ HTML](reports/map.html) · [Notebook đã chạy](notebooks/01_station_flow.ipynb) · [Báo cáo](reports/findings.md) · [Kiểm tra dữ liệu](reports/quality.json)

## Đọc kết quả

Một chuyến đi lúc 08:50 và đến lúc 09:10 đóng góp một lượt đi cho giờ 08:00 và một lượt đến cho giờ 09:00. Mã trạm là văn bản. Các đầu chuyến thiếu mã không được gán trạm. Với mỗi mã, chương trình dùng trung vị tọa độ quan sát để xác định trạm thuộc ranh giới thành phố. Các chuyến xuyên ranh giới vẫn đóng góp ở đầu thuộc Jersey City.

Chênh lệch bằng lượt đi trừ lượt đến. Ví dụ 12 lượt đi và 5 lượt đến cho +7. Xếp hạng dùng 23 ngày thứ Hai đến thứ Sáu, kể cả ngày lễ, và các giờ bắt đầu 07, 08, 09, 16, 17, 18. Số ngày dương là số ngày có ít nhất một giờ cao điểm dương. Tổng chênh lệch dương cộng riêng các ô ngày–giờ có net > 0. Khi hai trạm bằng số ngày, dùng tổng chênh lệch dương rồi mã trạm. Giờ ưu tiên là giờ dương nhiều ngày nhất, hòa thì lấy tổng net dương lớn hơn rồi giờ sớm hơn.

Thử lọc Grove St PATH theo một ngày và giờ 18 trong bảng chi tiết. Tính net, rồi kiểm tra giá trị đó trong tổng xếp hạng. Đọc bảng theo giờ để so sánh trung bình trên 23 ngày trong tuần và 8 ngày cuối tuần, kể cả ngày có 0 lượt. Các bảng chỉ ghi ô có sự kiện. Số lượt đi/đến cạnh giờ ưu tiên trên bản đồ chỉ cộng các ngày trong tuần mà giờ đó có net dương.

## Chạy lại

Python 3.10+. Tải hai ZIP chính thức [tháng 1](https://s3.amazonaws.com/tripdata/JC-202501-citibike-tripdata.csv.zip) và [tháng 12](https://s3.amazonaws.com/tripdata/JC-202412-citibike-tripdata.csv.zip) theo [trang dữ liệu Citi Bike](https://citibikenyc.com/system-data). Tệp tháng 12 giúp tính lượt đến của các chuyến bắt đầu trước 1/1 và kết thúc trong tháng 1. Chỉ các sự kiện thuộc tháng 1 được tính. Giờ trong CSV được đọc theo giờ địa phương.

```powershell
python run_all.py --input JC-202501.zip --previous JC-202412.zip
python -m unittest discover -s tests
python -m pip install jupyter
python -m notebook notebooks/01_station_flow.ipynb
```

Nếu chỉ có gói tháng 1, có thể bỏ `--previous`. Kết quả khi đó thiếu lượt đến trong tháng 1 từ các chuyến chỉ có trong gói tháng 12. Pipeline tạo SQLite cục bộ và xuất các bảng tổng hợp trong reports. Mở map.html trong trình duyệt để bấm các điểm trên bản đồ.

Nguồn ranh giới là Jersey City GEOID 3436000, lớp Incorporated Places của [U.S. Census TIGERweb ACS 2024](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/28). Phân tích và biểu đồ phục vụ portfolio theo [điều khoản dữ liệu Citi Bike](https://citibikenyc.com/data-sharing-policy).
