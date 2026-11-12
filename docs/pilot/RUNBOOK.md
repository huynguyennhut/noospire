# Runbook vận hành · Noospire pilot cho Empire

Áp dụng cho bộ compose trong `deploy/`. Mọi lệnh chạy trong thư mục `deploy/` trên host pilot. Giờ lưu UTC, giao diện hiện ICT.
Secret (signing key, tunnel token, Access AUD) lấy từ secret store và đặt vào `deploy/.env`. Không commit, không gửi qua chat.

## 1. Kiến trúc mạng

```
Internet ── Cloudflare Access ── Named Tunnel ── cloudflared ──(mạng connector, internal)── gateway:8080
                                                                                              │ (mạng internal)
                                                                    api:8000 ── worker ── scheduler ── /data (SQLite + storage)
host loopback 127.0.0.1:8080 ── gateway   (chỉ dùng cho owner trên host và smoke test)
```

- `cloudflared` chỉ thấy được `gateway`. API, DB, worker và cổng debug nằm trong mạng nội bộ.
- Worker có mạng egress riêng (`worker-egress`), tách khỏi egress của tunnel (`tunnel-egress`).
- Gateway kiểm JWT Cloudflare Access (chữ ký, audience, issuer, hạn) cho mọi request, kể cả SSE. Sau đó app vẫn tự kiểm phiên, vai trò và grant theo asset.

## 2. Khởi động sạch

1. Tạo `deploy/.env` từ `deploy/.env.example`.
   - Bắt buộc có: `SENTINEL_SECRET_KEY` (≥32 ký tự, sinh mới), `SENTINEL_SOLE_OWNER_EMAIL`, `SENTINEL_SOLE_OWNER_ACCOUNT_ID`.
   - Có tunnel thì thêm: `TUNNEL_TOKEN`, `NOOSPIRE_ACCESS_TEAM_DOMAIN`, `NOOSPIRE_ACCESS_AUD`.
2. Build và chạy (chưa bật tunnel):
   ```bash
   docker compose build
   ```
   ```bash
   docker compose up -d api worker scheduler gateway
   ```
   Chạy loopback, chưa có tunnel: đặt `NOOSPIRE_ACCESS_REQUIRED=false`. Có tunnel thì giữ `true`; thiếu team/AUD thì gateway trả 503 cho mọi request (fail closed).
3. Tạo owner. Mật khẩu nhập qua stdin, không để trong lịch sử shell:
   ```bash
   docker compose exec -T api python -m backend.app.cli bootstrap-owner --username owner --password-stdin
   ```
4. Smoke test (chỉ đọc, không tạo job):
   ```bash
   python deploy/smoke.py http://127.0.0.1:8080
   ```
   Muốn kiểm cả phiên đăng nhập và SSE: đặt thêm `NOOSPIRE_SMOKE_USER` và `NOOSPIRE_SMOKE_PASSWORD` trong môi trường.
5. Bật tunnel:
   ```bash
   docker compose --profile tunnel up -d cloudflared
   ```

## 3. Cloudflare: Named Tunnel và Access

- **Tunnel**: tạo Named Tunnel trong Zero Trust → Networks → Tunnels. Published application route: `<hostname quản trị của Empire>` → `http://gateway:8080`. Token đặt vào `TUNNEL_TOKEN`.
- **Access**: tạo Self-hosted application cho cùng hostname.
  - Policy chỉ cho các email/nhóm được duyệt.
  - Lấy **Application Audience (AUD) tag** đặt vào `NOOSPIRE_ACCESS_AUD`, team domain (`<team>.cloudflareaccess.com`) đặt vào `NOOSPIRE_ACCESS_TEAM_DOMAIN`.
- **Firewall host**: chỉ mở egress cho `cloudflared` tới `region1.v2.argotunnel.com` và `region2.v2.argotunnel.com` qua cổng 7844 (UDP cho QUIC, TCP cho HTTP/2 dự phòng), cùng HTTPS 443 tới `api.cloudflare.com` và `update.argotunnel.com`.
  - Không mở cổng inbound nào.
  - Đối chiếu lại với tài liệu chính thức của Cloudflare trước khi áp dụng.
- **Quick Tunnel (`*.trycloudflare.com`)**: chỉ dùng cho demo ngắn. Console tự chuyển sang polling theo cursor vì Quick Tunnel không hỗ trợ SSE và giới hạn số request đang xử lý. **Không** dùng link Quick Tunnel trong biên bản nghiệm thu.
- Kiểm qua tunnel: lấy một service token của Access, đặt vào `NOOSPIRE_SMOKE_ACCESS_JWT`, rồi chạy:
  ```bash
  python deploy/smoke.py https://<hostname>
  ```

## 4. Health và log

| Kiểm tra | Ý nghĩa |
|---|---|
| `GET /gateway/live` | Process gateway sống. Không kiểm Access, dùng cho connector và Docker |
| `GET /healthz/live` | Process API sống |
| `GET /healthz/ready` | API sẵn sàng: DB truy cập được và đã có schema. Không phụ thuộc worker |
| `GET /api/v1/engines/workers`, `/api/v1/operations/overview` | Worker heartbeat (kèm lý do tạm dừng do tải), hàng đợi, job quá hạn, dead letter, độ mới dữ liệu |
| `GET /api/v1/engines/health` | Contract health duy nhất của engine, chỉ báo theo trạng thái đo được |

- Mọi response có `X-Request-ID`. Lỗi JSON có `request_id`.
- Job chạy tay dùng request ID làm `correlation_id`; lượt chạy theo lịch dùng `slot-…`. Mã này đi qua batch, execution, event, report.
- Truy vết một sự cố theo mã:
  ```bash
  docker compose logs api worker scheduler gateway | grep <request_id hoặc correlation_id>
  ```

## 5. Đổi token và secret

| Secret | Cách đổi | Hệ quả |
|---|---|---|
| Tunnel token | Zero Trust → tunnel → Refresh token. Cập nhật `TUNNEL_TOKEN`, rồi `docker compose --profile tunnel up -d cloudflared` | Token cũ hết hiệu lực |
| `SENTINEL_SECRET_KEY` | Sinh khóa mới, cập nhật `.env`, rồi `docker compose up -d api worker scheduler` | Mọi phiên đăng nhập bị vô hiệu |
| Mật khẩu người dùng | Owner tạm khóa tài khoản ở `/users/`, người dùng đặt lại | — |

**Bắt buộc trước khi go-live:** tunnel token và mật khẩu Cloudflare cũ từng bị commit vào lịch sử git công khai, nên phải đổi cả hai.

## 6. Backup và restore

- **Backup** bằng SQLite online backup, an toàn khi app đang chạy:
  ```bash
  docker compose exec -T api python -m backend.app.cli backup --out /data/backups/noospire-$(date -u +%Y%m%dT%H%M%SZ).db
  ```
  Sao chép thêm `/data/storage` (artifact, output execution, report snapshot).
- **Kiểm bản backup**:
  ```bash
  docker compose exec -T api python -m backend.app.cli restore-check --backup /data/backups/<file>.db
  ```
- **Restore**:
  1. `docker compose stop api worker scheduler`
  2. Thay `/data/noospire.db` bằng bản backup; xóa `-wal` và `-shm` cũ.
  3. Khôi phục `/data/storage` cùng thời điểm.
  4. `docker compose up -d`, rồi chạy smoke test.

## 7. Dừng khẩn cấp

| Mức | Lệnh | Tác dụng |
|---|---|---|
| Cắt truy cập từ ngoài | `docker compose stop cloudflared` (hoặc tắt route/Access application trên Cloudflare) | Console nội bộ vẫn chạy |
| Dừng mọi job | `docker compose stop worker scheduler` | Job đang chạy mất lease; reaper xếp hàng lại khi worker chạy lại |
| Tắt một lịch | Owner bấm tạm dừng lịch ở `/schedules/` | Bật lại không chạy bù các slot đã lỡ |

## 8. Rollback

- **Ứng dụng**: image được đánh tag theo `NOOSPIRE_BUILD_ID`. Đặt lại `NOOSPIRE_BUILD_ID` về bản trước rồi `docker compose up -d`.
- **Schema**: pilot dùng `create_all` (chỉ thêm bảng, không sửa cột). Muốn rollback schema thì restore bản backup lấy **trước** khi nâng cấp (mục 6). Luôn backup trước mỗi lần nâng cấp.

## 9. Thu hồi quyền

| Lớp | Thao tác |
|---|---|
| Cloudflare Access | Gỡ người dùng khỏi policy hoặc revoke session trong Zero Trust → Users. Gateway từ chối ngay khi token hết hạn hoặc không còn hợp lệ |
| Ứng dụng | Owner vô hiệu hóa tài khoản hoặc thu hồi grant ở `/users/`. Vô hiệu hóa sẽ hủy mọi phiên của người đó ngay |
| Tunnel | Xóa connector hoặc refresh token |
