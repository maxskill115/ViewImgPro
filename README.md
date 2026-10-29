# ViewImgPro

Công cụ xem nhanh, chọn lọc và cắt ảnh khung hình (frame) từ video, viết bằng Python + Tkinter, thiết kế cho Windows.

Quy trình điển hình: tách video thành ảnh → lướt xem từng ảnh với mức zoom được giữ nguyên → tick chọn ảnh ưng ý → copy ảnh gốc hoặc cắt sẵn theo khung đang xem.

> Ảnh gốc **không bao giờ bị di chuyển, sửa hay xóa**. Mọi kết quả đều là file mới trong thư mục `Đã lọc hình`.

---

## Tính năng chính

- **Xem ảnh mượt:** zoom có animation, bám theo con trỏ chuột; kéo để di chuyển ảnh; ảnh lớn (hàng chục MP) vẫn zoom và kéo không giật.
- **Giữ nguyên chế độ xem khi chuyển ảnh:** zoom 150% ở ảnh 1 thì sang ảnh 2, 3, 4… vẫn xem 150% ở cùng vị trí tương đối. Rất tiện để so sánh cùng một vùng giữa các khung hình.
- **Tick chọn nhanh:** phím `Space` hoặc `Enter` để chọn/bỏ chọn ảnh đang xem; `←` `→` để chuyển ảnh.
- **Quét thư mục đệ quy:** chọn thư mục gốc, app tự tìm mọi thư mục có ảnh.
- **Copy ảnh đã chọn:** copy nguyên file gốc sang `Đã lọc hình`.
- **Copy cắt theo khung zoom:** cắt từng ảnh đã chọn đúng vùng đang xem rồi lưu thành ảnh mới.
- **Video → IMG:** tách video thành ảnh bằng FFmpeg ngay trong app.
- Mở lên là cửa sổ phóng to (maximize).

Định dạng ảnh hỗ trợ: `.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tif` `.tiff`.

---

## Yêu cầu

| Thành phần | Ghi chú |
|---|---|
| Windows | Giao diện thiết kế cho Windows (font Segoe UI, theme `vista`) |
| Python 3.9 trở lên | Tkinter đi kèm bản Python cài từ python.org |
| Pillow 9.1 trở lên | Bắt buộc |
| FFmpeg | Chỉ cần khi dùng nút **Video → IMG** |

## Cài đặt và chạy

```bat
py -m pip install Pillow
py viewimgpro.py
```

Nếu thiếu Pillow, app sẽ báo: *"Chưa cài Pillow. Mở CMD và chạy: py -m pip install Pillow"*.

---

## Cách dùng

### 1. Mở ảnh
Bấm **📂 Chọn thư mục gốc** (hoặc `Ctrl+O`). Có thể chọn thư mục cha chứa nhiều thư mục ảnh, hoặc chọn thẳng một thư mục ảnh. Danh sách thư mục hiện bên trái; bấm vào một thư mục để xem danh sách ảnh của nó.

Các thư mục tên `Đã lọc hình` (kể cả `Đã lọc hình_zoom` của phiên bản cũ) được bỏ qua khi quét, nên kết quả không bị lẫn vào danh sách nguồn. Bấm **⟳ Tải lại** để quét lại sau khi thêm ảnh.

### 2. Xem và zoom

| Thao tác | Cách làm |
|---|---|
| Zoom theo con trỏ | `Ctrl` + lăn chuột |
| Zoom vào / ra | Nút **+** / **−**, hoặc `Ctrl` + `+` / `Ctrl` + `-` |
| Vừa khung | Nút **Vừa khung** |
| Xem 1:1 (100%) | Nút **Ảnh thật 1:1** |
| Di chuyển ảnh | Kéo chuột trái, thanh cuộn, hoặc lăn chuột |
| Cuộn ngang | `Shift` + lăn chuột |
| Xoay 90° | Nút **Xoay trái** / **Xoay phải** (chỉ áp dụng khi xem, không ghi đè file) |
| Ảnh trước / sau | `←` / `→`, hoặc bấm trong danh sách |

Mức zoom giới hạn từ 5% đến 800%. Ở chế độ **Vừa khung**, ảnh nhỏ hơn khung xem không bị phóng to.

### 3. Chọn ảnh
- Tick ô vuông ở danh sách bên trái, hoặc nhấn `Space` / `Enter` khi đang xem ảnh.
- **✓ Chọn tất cả**, **Bỏ chọn tất cả**, **Bỏ chọn ảnh đang xem** nằm ngay dưới danh sách.
- Bộ đếm "x ảnh | y chọn" và "Tổng ảnh đã chọn" cập nhật liên tục. Lựa chọn được giữ khi bạn chuyển qua lại giữa các thư mục.

### 4. Copy

**Copy ảnh đã chọn:** copy nguyên file gốc vào thư mục con `Đã lọc hình` của từng thư mục ảnh. File đã tồn tại thì được bỏ qua.

**✂ Copy cắt theo khung zoom:** với mỗi ảnh đã chọn, cắt đúng vùng bạn đang xem (cùng mức zoom, cùng vị trí tương đối) và lưu thành `ten_anh_crop.ext` trong `Đã lọc hình`. Hộp thoại cho chọn 1 trong 2 kiểu lưu:

| | Giữ độ phân giải gốc (mặc định) | Đúng kích thước hiển thị |
|---|---|---|
| Cách làm | Lấy thẳng pixel gốc, không phóng hay thu | Phóng/thu vùng cắt theo mức zoom hiện tại |
| Zoom > 100% | Ảnh ra nhỏ hơn khung xem, sắc nét nhất, file nhẹ | Ảnh ra cỡ khung xem, chỉ phóng bằng nội suy nên hơi mềm, file nặng hơn |
| Zoom < 100% | Ảnh ra lớn hơn khung xem, giữ trọn chi tiết | Ảnh ra cỡ khung xem, nhẹ hơn nhưng mất bớt chi tiết |
| Đúng 100% | Hai kiểu giống hệt nhau | |

Lưu ý:
- Màu sắc không khác nhau giữa hai kiểu (giữ nguyên màu và hồ sơ màu ICC nếu có). Dung lượng chủ yếu phụ thuộc số pixel của ảnh ra.
- JPEG lưu chất lượng 95; các định dạng khác giữ nguyên đuôi gốc.
- Ở chế độ **Vừa khung**, mỗi ảnh được copy nguyên khung hình.
- Ảnh khác kích thước vẫn cắt được, dựa theo vị trí tương đối của khung xem.
- File `_crop` cũ cùng tên sẽ bị **ghi đè** (vì thường bạn cắt lại với khung mới).
- Việc cắt chạy nền, có thanh tiến trình nên app không bị đơ khi chọn nhiều ảnh lớn.

### 5. Video → IMG
Bấm **Video → IMG**, chọn thư mục chứa video và số ảnh mỗi giây (FPS, mặc định 1; `2` = 2 ảnh/giây; `0.5` = 1 ảnh mỗi 2 giây).

- Mỗi video tạo một thư mục cùng tên, ảnh đánh số `frame_0001.jpg`, `frame_0002.jpg`, …
- Video đã tách xong ở cùng FPS sẽ được bỏ qua (đánh dấu bằng file `_DONE.txt`).
- Hỗ trợ: `.mp4` `.mov` `.avi` `.mkv` `.wmv` `.m4v` `.webm` `.mpeg` `.mpg` `.3gp` `.mts` `.m2ts`.
- Hộp thoại có phần **Kiểm tra FFmpeg**: app tìm `ffmpeg` trong PATH trước; nếu không có, bạn chọn thủ công file `ffmpeg.exe`. Đường dẫn được lưu vào `ffmpeg_path.txt` cạnh file `.py` để lần sau khỏi chọn lại.

---

## Cấu trúc thư mục đầu ra

```text
F:\Downloads\img\IMG\
├── IMG_4759\
│   ├── frame_0001.jpg
│   ├── frame_0002.jpg
│   └── Đã lọc hình\
│       ├── frame_0001.jpg          ← từ "Copy ảnh đã chọn"
│       └── frame_0002_crop.jpg     ← từ "Copy cắt theo khung zoom"
└── IMG_4760\
    └── ...
```

---

## Xử lý sự cố

| Vấn đề | Cách xử lý |
|---|---|
| App không mở hoặc báo lỗi giao diện | Xem file `viewimgpro_error.log` nằm cạnh file `.py` |
| Báo thiếu Pillow | `py -m pip install Pillow` |
| Video → IMG báo không tìm thấy FFmpeg | Thêm thư mục `bin` của FFmpeg vào PATH, hoặc chọn `ffmpeg.exe` trong hộp thoại |
| Không lưu được `ffmpeg_path.txt` | Thư mục chứa script đang chỉ đọc; app vẫn chạy bình thường trong phiên đó |
| Ảnh không hiện trong danh sách | Kiểm tra đuôi file có nằm trong danh sách định dạng hỗ trợ, rồi bấm **⟳ Tải lại** |

---

## Ghi chú kỹ thuật

Để zoom và kéo ảnh mượt, canvas luôn chỉ vẽ **một khung bằng đúng kích thước vùng xem**, nên tốc độ không phụ thuộc kích thước ảnh. Khi mở ảnh, app tạo sẵn các bản thu nhỏ 1/2, 1/4, 1/8 để zoom ra xa không phải xử lý ảnh gốc. Lúc đang zoom hoặc kéo dùng nội suy nhanh, khoảng 140 ms sau khi dừng thì vẽ lại ở chất lượng cao.

Ảnh được đọc theo hướng EXIF (tự xoay đúng chiều) và chuyển sang RGB trước khi hiển thị hoặc cắt.
