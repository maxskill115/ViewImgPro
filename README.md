# ViewImgPro

Công cụ xem nhanh, chọn lọc và cắt **ảnh / video** (kể cả khung hình tách từ video), viết bằng Python + Tkinter, thiết kế cho Windows.

Quy trình điển hình: tách video thành ảnh (hoặc xem thẳng video) → lướt xem từng file với mức zoom được giữ nguyên → tick chọn file ưng ý → copy file gốc hoặc cắt sẵn theo khung đang xem.

> File gốc **không bao giờ bị di chuyển, sửa hay xóa**. Mọi kết quả đều là file mới trong thư mục `Đã lọc hình`.

---

## Tính năng chính

- **Xem ảnh mượt:** zoom có animation, bám theo con trỏ chuột; kéo để di chuyển ảnh; ảnh lớn (hàng chục MP) vẫn zoom và kéo không giật.
- **Xem cả video:** video hiện trong cùng danh sách (có biểu tượng 🎬), xem trước, tua và phát được (không có tiếng). Cần FFmpeg.
- **Giữ nguyên chế độ xem khi chuyển file:** zoom 150% ở file 1 thì sang file 2, 3, 4… vẫn xem 150% ở cùng vị trí tương đối. Rất tiện để so sánh cùng một vùng giữa các khung hình.
- **Bất đồng bộ di chuyển:** tùy chọn để zoom dùng chung nhưng mỗi file nhớ vị trí kéo riêng.
- **Tick chọn nhanh:** phím `Space` hoặc `Enter` để chọn/bỏ chọn file đang xem; `←` `→` để chuyển file.
- **Quét thư mục đệ quy:** chọn thư mục gốc, app tự tìm mọi thư mục có ảnh/video.
- **Copy file đã chọn:** copy nguyên file gốc sang `Đã lọc hình`.
- **Copy cắt theo khung zoom:** cắt từng file đã chọn (ảnh lẫn video) đúng vùng đang xem rồi lưu thành file mới.
- **Video → IMG:** tách video thành ảnh bằng FFmpeg ngay trong app.
- **Bố cục cố định:** mở lên là cửa sổ phóng to (maximize), cột danh sách bên trái luôn giữ độ rộng ổn định (365px), có thể kéo vách ngăn để đổi.

### Định dạng hỗ trợ

| Loại | Đuôi file |
|---|---|
| Ảnh | `.jpg` `.jpeg` `.jpe` `.jfif` `.png` `.apng` `.webp` `.bmp` `.dib` `.gif` `.tif` `.tiff` `.ico` `.tga` `.ppm` `.pgm` `.pbm` `.pnm` `.jp2` `.j2k` `.jpx` `.avif` |
| Ảnh (cần cài thêm `pillow-heif`) | `.heic` `.heif` |
| Video | `.mp4` `.m4v` `.mov` `.avi` `.mkv` `.wmv` `.webm` `.mpeg` `.mpg` `.mpe` `.3gp` `.3g2` `.mts` `.m2ts` `.flv` `.f4v` `.vob` `.ogv` `.asf` |

`.ts` được cố ý bỏ qua vì thường là file mã nguồn TypeScript.

---

## Yêu cầu

| Thành phần | Ghi chú |
|---|---|
| Windows | Giao diện thiết kế cho Windows (font Segoe UI, theme `vista`) |
| Python 3.9 trở lên | Tkinter đi kèm bản Python cài từ python.org |
| Pillow 9.1 trở lên | Bắt buộc |
| FFmpeg | Cần khi xem/phát/cắt video và khi dùng nút **Video → IMG**. Chỉ làm việc với ảnh thì không cần |
| pillow-heif | Tùy chọn, để mở ảnh `.heic` / `.heif` |

## Cài đặt và chạy

```bat
py -m pip install Pillow
py -m pip install pillow-heif
py ViewImgPro2.py
```

(`pillow-heif` chỉ cần nếu bạn có ảnh HEIC/HEIF.)

Nếu thiếu Pillow, app sẽ báo: *"Chưa cài Pillow. Mở CMD và chạy: py -m pip install Pillow"*.

---

## Cách dùng

### 1. Mở ảnh / video
Bấm **📂 Chọn thư mục gốc** (hoặc `Ctrl+O`). Có thể chọn thư mục cha chứa nhiều thư mục, hoặc chọn thẳng một thư mục. Danh sách thư mục hiện bên trái; bấm vào một thư mục để xem danh sách file của nó.

Các thư mục tên `Đã lọc hình` (kể cả `Đã lọc hình_zoom` của phiên bản cũ) được bỏ qua khi quét, nên kết quả không bị lẫn vào danh sách nguồn. Bấm **⟳ Tải lại** để quét lại sau khi thêm file.

Cột bên trái rộng 365px khi mở. Kéo vách ngăn giữa danh sách và khung xem để đổi độ rộng (tối thiểu 320px); sau khi bạn kéo, app không tự đặt lại nữa. Muốn đổi mặc định, sửa `LEFT_PANE_WIDTH` trong code.

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
| File trước / sau | `←` / `→`, hoặc bấm trong danh sách |

Mức zoom giới hạn từ 5% đến 800%. Ở chế độ **Vừa khung**, ảnh nhỏ hơn khung xem không bị phóng to.

**Bất đồng bộ di chuyển** (ô tick phía trên khung xem):

| Trạng thái | Hành vi khi chuyển file |
|---|---|
| Tắt (mặc định) | Zoom và vị trí giữ nguyên giữa các file |
| Bật | Zoom dùng chung, mỗi file nhớ vị trí kéo riêng; file mới mở ở vị trí gốc (vị trí lúc bạn bật tùy chọn) |

Nút **↺ Về vị trí gốc** đưa file đang xem về vị trí gốc, chỉ có tác dụng khi bật chế độ bất đồng bộ.

### 3. Xem video

Khi chọn một video, thanh điều khiển hiện dưới khung xem: nút **▶ Phát**, thanh tua và đồng hồ thời gian.

| Thao tác | Cách làm |
|---|---|
| Phát / dừng | Nút **▶ Phát**, hoặc phím `P` |
| Tua 5 giây | `Shift` + `←` / `→` |
| Tua tự do | Kéo thanh tua |

Lưu ý: đây là bản xem trước, **không có tiếng**. Khung hình phát được thu nhỏ để cạnh dài tối đa 1280px và tối đa 30 khung/giây cho mượt. Zoom, kéo và xoay hoạt động như với ảnh. `←` / `→` (không có `Shift`) vẫn là chuyển file.

### 4. Chọn file
- Tick ô vuông ở danh sách bên trái, hoặc nhấn `Space` / `Enter` khi đang xem file.
- **✓ Chọn tất cả**, **Bỏ chọn tất cả**, **Bỏ chọn file đang xem** nằm ngay dưới danh sách.
- Bộ đếm "x file | y chọn" và "Tổng file đã chọn" cập nhật liên tục. Lựa chọn được giữ khi bạn chuyển qua lại giữa các thư mục.

### 5. Copy

**Copy file đã chọn:** copy nguyên file gốc vào thư mục con `Đã lọc hình` của từng thư mục chứa nó. File đã tồn tại thì được bỏ qua.

**✂ Copy cắt theo khung zoom:** với mỗi file đã chọn, cắt đúng vùng bạn đang xem (cùng mức zoom, cùng vị trí tương đối) và lưu thành `ten_file_crop.ext` trong `Đã lọc hình`. Nếu bật bất đồng bộ di chuyển, mỗi file được cắt theo vị trí riêng của nó.

Với **ảnh**, hộp thoại cho chọn 1 trong 2 kiểu lưu:

| | Giữ độ phân giải gốc (mặc định) | Đúng kích thước hiển thị |
|---|---|---|
| Cách làm | Lấy thẳng pixel gốc, không phóng hay thu | Phóng/thu vùng cắt theo mức zoom hiện tại |
| Zoom > 100% | Ảnh ra nhỏ hơn khung xem, sắc nét nhất, file nhẹ | Ảnh ra cỡ khung xem, chỉ phóng bằng nội suy nên hơi mềm, file nặng hơn |
| Zoom < 100% | Ảnh ra lớn hơn khung xem, giữ trọn chi tiết | Ảnh ra cỡ khung xem, nhẹ hơn nhưng mất bớt chi tiết |
| Đúng 100% | Hai kiểu giống hệt nhau | |

Với **video**, file được cắt bằng FFmpeg và lưu thành `ten_video_crop.mp4` (mã hóa lại H.264, giữ nguyên âm thanh). Cần có FFmpeg; nếu thiếu app sẽ báo trước khi chạy.

Lưu ý:
- Màu sắc không khác nhau giữa hai kiểu lưu ảnh (giữ nguyên màu và hồ sơ màu ICC nếu có). Dung lượng chủ yếu phụ thuộc số pixel của ảnh ra.
- Ảnh JPEG lưu chất lượng 95; các định dạng ảnh khác giữ nguyên đuôi gốc.
- Ở chế độ **Vừa khung**, mỗi file được copy nguyên khung hình.
- File khác kích thước vẫn cắt được, dựa theo vị trí tương đối của khung xem.
- File `_crop` cũ cùng tên sẽ bị **ghi đè** (vì thường bạn cắt lại với khung mới).
- Việc cắt chạy nền, có thanh tiến trình nên app không bị đơ khi chọn nhiều file lớn.

### 6. Video → IMG
Bấm **Video → IMG**, chọn thư mục chứa video và số ảnh mỗi giây (FPS, mặc định 1; `2` = 2 ảnh/giây; `0.5` = 1 ảnh mỗi 2 giây).

- Mỗi video tạo một thư mục cùng tên, ảnh đánh số `frame_0001.jpg`, `frame_0002.jpg`, …
- Video đã tách xong ở cùng FPS sẽ được bỏ qua (đánh dấu bằng file `_DONE.txt`).
- Hộp thoại có phần **Kiểm tra FFmpeg**: app tìm `ffmpeg` trong PATH trước; nếu không có, bạn chọn thủ công file `ffmpeg.exe`. Đường dẫn được lưu vào `ffmpeg_path.txt` cạnh file `.py` để lần sau khỏi chọn lại. Cùng FFmpeg này được dùng cho xem/phát/cắt video.

---

## Phím tắt

| Phím | Tác dụng |
|---|---|
| `Ctrl+O` | Chọn thư mục gốc |
| `←` / `→` | File trước / sau |
| `Space` / `Enter` | Chọn / bỏ chọn file đang xem |
| `Ctrl` + lăn chuột | Zoom theo con trỏ |
| `Ctrl` + `+` / `Ctrl` + `-` | Zoom vào / ra |
| `P` | Phát / dừng video |
| `Shift+←` / `Shift+→` | Tua video lùi / tới 5 giây |

---

## Cấu trúc thư mục đầu ra

```text
F:\Downloads\img\IMG\
├── IMG_4759\
│   ├── frame_0001.jpg
│   ├── frame_0002.jpg
│   └── Đã lọc hình\
│       ├── frame_0001.jpg          ← từ "Copy file đã chọn"
│       └── frame_0002_crop.jpg     ← từ "Copy cắt theo khung zoom"
└── IMG_4760\
    └── ...
```

Với video, kết quả cũng nằm trong `Đã lọc hình` cạnh file video gốc (bản cắt có dạng `ten_video_crop.mp4`).

---

## Xử lý sự cố

| Vấn đề | Cách xử lý |
|---|---|
| App không mở hoặc báo lỗi giao diện | Xem file `viewimgpro_error.log` nằm cạnh file `.py` |
| Báo thiếu Pillow | `py -m pip install Pillow` |
| Video không xem được / báo thiếu FFmpeg | Thêm thư mục `bin` của FFmpeg vào PATH, hoặc chọn `ffmpeg.exe` trong hộp thoại **Video → IMG** |
| Không lưu được `ffmpeg_path.txt` | Thư mục chứa script đang chỉ đọc; app vẫn chạy bình thường trong phiên đó |
| File không hiện trong danh sách | Kiểm tra đuôi file có nằm trong bảng định dạng hỗ trợ, rồi bấm **⟳ Tải lại**. Ảnh HEIC/HEIF cần cài `pillow-heif` |
| Mở lên không thấy danh sách bên trái | Kéo vách ngăn giữa danh sách và khung xem sang phải; bản hiện tại đã tự giữ cột trái ở 365px khi khởi động |

---

## Ghi chú kỹ thuật

Để zoom và kéo ảnh mượt, canvas luôn chỉ vẽ **một khung bằng đúng kích thước vùng xem**, nên tốc độ không phụ thuộc kích thước ảnh. Khi mở ảnh, app tạo sẵn các bản thu nhỏ 1/2, 1/4, 1/8 để zoom ra xa không phải xử lý ảnh gốc. Lúc đang zoom hoặc kéo dùng nội suy nhanh, khoảng 140 ms sau khi dừng thì vẽ lại ở chất lượng cao.

Ảnh được đọc theo hướng EXIF (tự xoay đúng chiều) và chuyển sang RGB trước khi hiển thị hoặc cắt.

Vì cửa sổ tự phóng to ngay khi mở, vị trí vách ngăn được đặt lại cho đến khi Tk layout xong (và mỗi khi cửa sổ đổi kích thước), trừ khi bạn đã tự kéo vách ngăn.
