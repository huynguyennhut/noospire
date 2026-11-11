# Runbook vận hành pilot Noospire

Tài liệu này thay bản cũ. Bản cũ từng chứa mật khẩu tài khoản và tunnel token; cả hai đã bị lộ trong lịch sử git công khai và **phải được thay mới** (xem mục 0).

## 0. Việc bắt buộc trước khi chạy pilot

1. Đổi mật khẩu tài khoản Cloudflare của owner, bật 2FA, đăng xuất các phiên khác.
2. Trong Zero Trust → Networks → Tunnels: xóa (hoặc rotate token) tunnel cũ có token từng nằm trong `docker-compose.yml`, `auto_host.cmd`, `install_service.cmd`, `setup_cloudflare_tunnel.ps1`. Tạo Named Tunnel mới.
3. Mọi mật khẩu từng xuất hiện trong test, ghi chú `.agents/` hoặc chat đều coi là đã lộ. Không dùng lại ở đâu.
4. Lịch sử git công khai vẫn còn các giá trị cũ. Rotate là biện pháp chính. Viết lại lịch sử (`git filter-repo`) chỉ là bước phụ và cần owner quyết định vì phải force-push.

## 1. Kiến trúc được hỗ trợ

```
Trình duyệt ──HTTPS──> Cloudflare Access ──> Named Tunnel (cloudflared)
                                                  │ mạng Docker nội bộ
                                                  ▼
                                    gateway :8080 (static out/ + proxy /api, /healthz)
                                                  │ origin cố định NOOSPIRE_API_ORIGIN
                                                  ▼
                                    api :8000 ── worker ── scheduler ── SQLite (/data)
```

| Launcher | Vai trò | Trạng thái |
|---|---|---|
| `deploy/docker-compose.yml` | api, worker, scheduler, gateway; `--profile tunnel` thêm cloudflared | Đường pilot chính. Đọc mã, chưa chạy ở máy dev (không có Docker). |
| `run.ps1` / `run.cmd` / `run.sh` | API + gateway trên loopback cho máy local | Gateway đã đo bằng test tự động. |
| `frontend/public/_worker.js` | Chỉ khi host console trên Cloudflare Pages: static + proxy tới `API_ORIGIN` cố định | Tùy chọn. Đọc mã, chưa chạy. |

Gateway không giữ dữ liệu, không phát danh tính. FastAPI là nguồn duy nhất cho danh tính, quyền, số liệu, job và report.

## 2. Khởi động sạch

```bash
cp deploy/.env.example deploy/.env      # điền từ secret store; file này bị git-ignore
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api \
  python -m backend.app.cli bootstrap-owner --username <tên-owner>
```

Lệnh bootstrap đọc mật khẩu từ prompt, chỉ chạy được một lần và gắn owner với `SENTINEL_SOLE_OWNER_ACCOUNT_ID`. HTTP `/api/v1/auth/bootstrap` trả 404 trừ khi đặt `SENTINEL_BOOTSTRAP_TOKEN` tạm thời. DB mới luôn rỗng: không tự tạo user, asset, finding hay lịch.

Local không Docker:

```powershell
python -m venv .venv; .venv\Scripts\pip install -r backend\requirements.txt
.\run.ps1 -BuildConsole        # cần Node 20 để build frontend/out
```

## 3. Health và log

| Endpoint | Ý nghĩa |
|---|---|
| `/gateway/live` | Process gateway sống, có cấu hình origin, có file static |
| `/healthz/live` | Process API sống (không kiểm DB) |
| `/healthz/ready` | API kết nối được DB và có schema; trả 503 nếu không |

Mọi response có `X-Request-ID`. Lỗi gateway có dạng `{"code": "UPSTREAM_UNREACHABLE" | "UPSTREAM_TIMEOUT" | "MISROUTED", "request_id": ...}`. Dùng `request_id` để tìm dòng log tương ứng ở gateway và API.

## 4. Cloudflare Named Tunnel và Access

1. Tạo Named Tunnel, published route `https://<hostname-quản-trị-của-Empire>` → `http://gateway:8080`.
2. Tạo Access application (self-hosted) cho đúng hostname, policy chỉ cho các email được duyệt. Bật validate JWT ở origin hoặc dùng "Protect with Access".
3. Đặt `TUNNEL_TOKEN` và `CLOUDFLARED_VERSION` (bản cụ thể, không dùng `latest`) trong `deploy/.env`, rồi `--profile tunnel up -d`.
4. App vẫn kiểm user, vai trò và asset grant sau lớp Access.
5. Quick Tunnel chỉ dùng cho demo ngắn: giới hạn 200 request đang xử lý, không hỗ trợ SSE. Giao diện phải dùng polling theo cursor.

## 5. Đổi token và secret

- `SENTINEL_SECRET_KEY`: đổi trong secret store rồi restart api/worker/scheduler. Mọi phiên cũ mất hiệu lực.
- Tunnel token: rotate trong dashboard, cập nhật `TUNNEL_TOKEN`, `up -d cloudflared`.
- Thu quyền một người: owner disable tài khoản (`PATCH /api/v1/auth/users/{id}/status`) để hủy mọi phiên ngay, rồi gỡ người đó khỏi Access policy.

## 6. Backup và restore

```bash
docker compose ... exec api python -m backend.app.cli backup --out /data/backups/noospire-$(date -u +%Y%m%dT%H%M%SZ).db
docker compose ... exec api python -m backend.app.cli restore-check --backup /data/backups/<file>.db
```

`backup` dùng SQLite online backup API nên snapshot nhất quán kể cả khi có WAL. `restore-check` khôi phục vào DB tạm, chạy `integrity_check` và in số dòng từng bảng.

## 7. Dừng khẩn cấp và rollback

- Dừng mọi job: owner gọi `POST /api/v1/scans/stop-all`. Hoặc `docker compose stop worker scheduler`.
- Cắt truy cập từ ngoài: `docker compose stop cloudflared`, hoặc tắt Access application.
- Rollback app: `NOOSPIRE_BUILD_ID=<bản-trước> docker compose up -d`. Nếu bản mới đã đổi schema, restore backup chụp trước lúc nâng cấp.

## 8. Còn thiếu để nghiệm thu Vòng B

- Hostname quản trị do Empire sở hữu và quyền cấu hình Access/Tunnel.
- Máy có Docker để build image và ghi digest.
- Node 20 để build `frontend/out` sạch.
