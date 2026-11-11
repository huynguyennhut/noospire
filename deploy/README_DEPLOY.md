# HƯỚNG DẪN TRIỂN KHAI PRIVATE HOST & KẾT NỐI CLOUDFLARE ZERO TRUST
## NOOSFORGE Security Intelligence — Continuous Enterprise Security Platform

---

## 1. CẢI TIẾN THƯƠNG HIỆU: LOGO CHÌM, SÂU LẮNG & ĐẲNG CẤP LIQUID GLASS
Đệ đã tối ưu toàn bộ tài sản logo (`logo.png`/`logo.jpg`) từ dạng nền trắng thô sơ thành **bộ nhận diện thương hiệu chìm (debossed/watermark) chuẩn mực Cyber Command Center**:
- **Huy hiệu Logo Kính Lồi (Debossed Frosted Jewel)**: Tạo khung kính gradient đa tầng với hiệu ứng viền sáng phản quang (`border-white/15`), bóng đổ âm thành lòng (`shadow-[inset_0_1px_2px_rgba(255,255,255,0.2)]`), đặt logo nét trắng bạc (`logo-white-emblem.png`) với drop-shadow nổi khối 3D trên thanh Sidebar, Mobile Header và Dashboard Hero.
- **Hình Chìm Nền Ambient Lớn (Ambient Debossed Watermark)**: Tích hợp hình chìm lớn toàn màn hình (`logo-white.png`) ở góc dưới nền Canvas với độ mờ tinh tế (`opacity-[0.035]`), mặt nạ mờ dần dạng elip xuyên tâm (`mask-image: radial-gradient(ellipse, ...)`), tạo chiều sâu quang học sang trọng, chìm sâu vào nền đen Obsidian `#09090B` mà không che khuất bảng biểu hay biểu đồ.

---

## 2. KIẾN TRÚC TRIỂN KHAI PRIVATE HOST (TỰ HOST 100%)

Nền tảng NOOSFORGE được thiết kế theo mô hình **Đơn Cửa Khẩu (Single-Origin Reverse Proxy Architecture)**:
- **Frontend (Next.js 14 App Router)**: Lắng nghe tại cổng `3000`.
- **Backend (FastAPI & Engine Tác Chiến)**: Lắng nghe tại cổng `8000`.
- **Reverse Proxy Nội Bộ**: Next.js tự động chuyển tiếp toàn bộ yêu cầu `/api/v1/*`, `/api/*`, `/docs`, `/openapi.json` sang cổng `8000`. 
=> Do đó, Private Host hoặc Cloudflare Tunnel chỉ cần trỏ duy nhất vào **`http://localhost:3000`** là toàn bộ hệ thống (UI + API) hoạt động trơn tru 100%!

---

## 3. CÁC PHƯƠNG THỨC KHỞI CHẠY PRIVATE HOST

### Phương thức 1: Khởi chạy Trực Tiếp trên Máy Chủ Windows (Khuyên Dùng)
Chạy kịch bản tự động hóa điều phối toàn bộ dịch vụ:
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\run_private_host.ps1
```

### Phương thức 2: Khởi chạy qua Docker Compose (Mọi Hệ Điều Hành VPS Linux/Windows)
```bash
cd deploy
docker compose up -d
```

### Phương thức 3: Khởi chạy trên Linux VPS (Ubuntu / Debian / RHEL)
```bash
chmod +x deploy/run_private_host.sh
./deploy/run_private_host.sh
```

---

## 4. KẾT NỐI CLOUDFLARE ZERO TRUST QUA CLOUDFLARED (KHÔNG CẦN MỞ PORT ROUTER)

Để đưa nền tảng từ Private Host lên mạng Internet thông qua Cloudflare với tài khoản của Đại Ca (`dangnhutnguyen0910@gmail.com`):

### Cách 1: Sử dụng Cloudflare Zero Trust Tunnel Token (Chuẩn Sản Phẩm Doanh Nghiệp Tối Thượng)
1. Đại Ca truy cập [dash.cloudflare.com](https://dash.cloudflare.com/) và đăng nhập bằng:
   - Email: `dangnhutnguyen0910@gmail.com`
   - Mật khẩu: `Hahanguyen09@`
2. Vào mục **Zero Trust** (thanh bên trái) -> **Networks** -> **Tunnels**.
3. Bấm **Create a Tunnel** (hoặc **Add a Tunnel**):
   - Đặt tên tunnel: `noosforge-private-host`
   - Chọn môi trường: **Windows** hoặc **Docker**.
   - Cloudflare sẽ hiển thị một chuỗi **Tunnel Token** dài (bắt đầu bằng `eyJ...`).
4. Tại tab **Public Hostname**:
   - Subdomain: `sec` (hoặc `noosforge`, `soc`)
   - Domain: Chọn tên miền của Đại Ca có sẵn trên Cloudflare
   - Type: `HTTP`
   - URL: `localhost:3000`
5. Kích hoạt Tunnel trên máy chủ của Đại Ca:
   - **Chạy trực tiếp dòng lệnh**:
     ```powershell
     powershell -ExecutionPolicy Bypass -File .\deploy\setup_cloudflare_tunnel.ps1 -TunnelToken "<DÁN_TUNNEL_TOKEN_VÀO_ĐÂY>"
     ```
   - **Hoặc cài làm Windows Service vĩnh viễn (Tự khởi động cùng Windows)**:
     ```powershell
     powershell -ExecutionPolicy Bypass -File .\deploy\setup_cloudflare_tunnel.ps1 -TunnelToken "<DÁN_TUNNEL_TOKEN_VÀO_ĐÂY>" -InstallService
     ```

### Cách 2: Quick Tunnel Miễn Phí (Không Cần Cấu Hình Domain)
Nếu Đại Ca muốn mở nhanh một đường hầm thử nghiệm bảo mật HTTPS có chứng chỉ SSL chính hãng của Cloudflare ngay lập tức:
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\setup_cloudflare_tunnel.ps1 -QuickTunnel
```
Lệnh này sẽ tự động sinh một liên kết bảo mật công khai dạng `https://xxxx.trycloudflare.com` định tuyến thẳng vào Dashboard NOOSFORGE của Đại Ca!
