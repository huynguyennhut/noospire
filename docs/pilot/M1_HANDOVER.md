# Bàn giao Mốc 1 · Một nguồn dữ liệu, một owner đã xác minh

Ngày: 2026-11-11 (UTC). Nguồn: working tree trên commit `a0bb68d` của `huynguyennhut/noospire`, chưa commit.
Nhãn: **đã đo** = chạy thật trong phiên này · **đọc mã** = sửa và review, chưa chạy · **chưa xác minh** = chưa làm.

## 1. Số liệu đo lại (đã đo)

| Hạng mục | Trước | Sau |
|---|---|---|
| Import app trên venv sạch từ `requirements.txt` | Lỗi: thiếu `greenlet`, `jinja2`, `reportlab`, `dnspython` | OK, dependency đã ghim phiên bản |
| `init_db` trên DB mới | Lỗi `index ix_scan_events_occurred_at already exists` | OK |
| Operation OpenAPI | 109 (gồm `/`, `/health`) | 110 (thêm `/healthz/live`, `/healthz/ready`, `/api/v1/version`; bỏ `/`; `/health` vẫn chạy nhưng ẩn khỏi schema) |
| Dữ liệu tạo khi boot DB rỗng | Seeder tạo asset VERIFIED + finding lịch sử mỗi lần boot | 0 user, 0 asset, 0 finding |
| Suite pilot `pytest` (mặc định = `tests_pilot`) | chưa có | 27 passed, exit 0 |
| Suite cũ `pytest tests` | 273 passed / 169 failed / 1 error, exit 1 | 218 passed / 225 failed, exit 1 |

Suite cũ dùng chung `noospire.db` ở gốc repo, gọi API không đăng nhập và giả định DB tự seed 379 dòng. Gần như mọi fail là 401, `KeyError: 'items'` (danh sách rỗng) hoặc token tự tạo với `sub=username`. Không có response 500. Suite này cần viết lại theo quyền mới và không dùng làm bằng chứng nghiệm thu.

## 2. Thay đổi

### Danh tính và phiên (đã đo)
- Phiên web: cookie `noospire_session` (HttpOnly, SameSite=Strict, Secure ngoài dev/test) và cookie `noospire_csrf`. Mọi mutation dùng cookie phải gửi `X-CSRF-Token` trùng cookie.
- Bearer chỉ nhận qua header `Authorization`. Token trên query string bị bỏ qua (trước đây có nhận, nên SSE và download làm lộ token trên URL).
- JWT `sub` = ID người dùng bất biến. Claim chỉ để tham khảo. Mỗi request đọc lại user và grant từ DB.
- Logout, disable và đổi phiên có hiệu lực trên server với độ chính xác mili giây (`iat_ms`). Áp dụng cho API, SSE và download.
- SSE kiểm lại phiên và grant ở mỗi heartbeat (10 giây). Khi mất quyền, stream gửi event `auth_revoked` rồi đóng.

### Owner (đã đo)
- Owner = ID bất biến `SENTINEL_SOLE_OWNER_ACCOUNT_ID` + email `SENTINEL_SOLE_OWNER_EMAIL` + vai trò OWNER. Có vai trò OWNER mà sai ID thì không phải owner.
- Bootstrap: `python -m backend.app.cli bootstrap-owner` trên host. HTTP `/auth/bootstrap` trả 404 nếu không có `SENTINEL_BOOTSTRAP_TOKEN`, 403 nếu token sai, 409 ở lần thứ hai. Khóa chính cố định bảo đảm tính nguyên tử.
- Không còn bypass ngầm cho `ADMIN`/`SUPER_ADMIN`/`is_superuser`. Lời mời chỉ cấp DEVELOPER, VIEWER, OPERATOR, SECURITY_LEAD.
- Chỉ owner: users, invite, enable/disable, grants, audit (lọc theo `user_id`, `action`), scan toàn estate, stop-all, cancel batch, tạo/sửa/xác minh inventory, lịch, baseline, settings, reset (chỉ dev/test).

### Phạm vi đối tượng (đã đo cho assets, findings, scans, reports; đọc mã cho batch và log)
- Người không phải owner chỉ thấy asset có grant. Quyền trong grant: `READ`, `SCAN`, `TRIAGE`, `REPORT`.
- Đối tượng ngoài phạm vi trả 404 (không lộ là có tồn tại). Thiếu hành động trả 403.
- Áp dụng cho: list, detail, search, count của assets/findings/scans/reports, batch list/detail, log, poll event, SSE, download report, triage, retest, tạo scan.
- Grant tạo/thu đều ghi audit với actor ID và resource ID. Thu grant có hiệu lực ở request kế tiếp.
- **Tạm thời**: metrics, empire-modules, alerts, logs, telemetry, fixture-379 chỉ cho owner, vì chưa tính tổng theo grant. Developer/viewer chưa có dashboard tổng hợp.

### Gateway và đường phát hành (gateway đã đo; Pages worker, Docker đọc mã)
- `deploy/gateway/gateway.py`: phục vụ `frontend/out`, chuyển `/api/*` và `/healthz/*` tới một origin cố định. Upstream ngắt trả 502 `UPSTREAM_UNREACHABLE`, timeout trả 503 `UPSTREAM_TIMEOUT`, HTML trên đường API trả 502 `MISROUTED`, tất cả có `request_id`. Mã 401/403/404/422/502/503/504 từ upstream đi qua nguyên vẹn. Header `x-backend-url` không có tác dụng. Không phục vụ `_worker.js`, `_routes.json`, `_redirects`.
- `frontend/public/_worker.js`: viết lại thành proxy tối thiểu tới `API_ORIGIN`. Đã bỏ kho dữ liệu trong bộ nhớ, login giả, upstream do client chọn và cơ chế nuốt lỗi.
- Đã xóa: `scan-engine.ts`, `fallback-data.*` (532 KB dữ liệu mô phỏng), `generate_full_worker.py`, `export_fallback_data.py`, `auto_host.cmd`, `install_service.cmd`, `setup_cloudflare_tunnel.ps1`, `run_private_host.*`, `Dockerfile.frontend` (`next start` không chạy được với `output: 'export'`), log và tsbuildinfo cũ.
- Compose mới: api / worker / scheduler / gateway / cloudflared (profile `tunnel`). Chỉ gateway publish ra `127.0.0.1:8080`. Secret bắt buộc lấy từ env, không có giá trị mặc định.
- API: `X-Request-ID`, lỗi JSON thống nhất `{detail, code, request_id}`, `Cache-Control: no-store` cho `/api` và `/healthz`. Download report kèm `private, no-store` và `X-Content-SHA256`.
- `SENTINEL_PROCESS_ROLE` tách api / worker / scheduler.

### Frontend (đọc mã; không build được vì máy dev không có Node)
- `api.ts`: `credentials: 'same-origin'`, header CSRF, `ApiError.kind` (unauthenticated, forbidden, upstream_unreachable, upstream_timeout, misrouted, network…), không lưu token trong `localStorage`.
- Shell lấy phiên từ `/auth/me`. Trạng thái API lấy từ `/healthz/ready`; probe lỗi thì hiện **Offline** kèm lý do và `request_id` (trước đây vẫn hiện Online, 18 ms). Bỏ 3 alert mẫu cố định. Logout gọi server.
- Health: bỏ chữ "CONNECTED", "100% Operational", "HEALTHY" và danh sách engine mặc định viết cứng. Chỉ hiện số liệu server trả về.
- SSE không còn `?token=`. Link download report hoạt động nhờ cookie.

## 3. Lệnh kiểm thử

```bash
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements-dev.txt
.venv/Scripts/python -m pytest -q          # tests_pilot: 27 passed, exit 0
.venv/Scripts/python -m pytest tests -q    # legacy: 218 passed / 225 failed, exit 1
```

## 4. Bị chặn hoặc chưa làm

| Hạng mục | Lý do |
|---|---|
| Rotate tunnel token và mật khẩu Cloudflare | Chỉ owner làm được. Hai giá trị này vẫn còn trong lịch sử git công khai. |
| `next build`, typecheck, Vòng B trên trình duyệt | Máy không có Node/npm. Chromium (Playwright) có sẵn. |
| Build image, ghi digest, chạy compose | Máy không có Docker. |
| Named Tunnel và Access | Cần hostname do Empire sở hữu và quyền cấu hình. |
| Mốc 2–7 (inventory/migration, engine SBOM/TLS, lịch, 6 màn hình, contract OpenAPI, 2 vòng nghiệm thu) | Chưa bắt đầu. Bước tiếp theo đề xuất: lát cắt SBOM của Mốc 3. |
| Dashboard tổng hợp theo grant cho developer/viewer | Tạm khóa cho owner (xem mục 2). |
| Viết lại suite cũ | Cần làm sau khi chốt contract của Mốc 3. |

Chưa chấm lại thang 100. Theo prompt, quyết định phát hành phụ thuộc hai luồng engine và hai vòng nghiệm thu, nên chấm sau Mốc 3.
