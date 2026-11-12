# Bàn giao Mốc 6 · Hợp đồng API và pilot qua Cloudflare Tunnel

Ngày: 2026-11-11 (UTC). Branch `pilot/m1-m5-defensive-platform`, các thay đổi Mốc 6 chưa commit. Tiếp nối [M5_HANDOVER.md](M5_HANDOVER.md).
Nhãn: **đã đo** = chạy thật · **đọc mã** = chưa chạy · **chưa làm**.

## 1. Kết quả đo

| Lệnh | Kết quả |
|---|---|
| `pytest` (tests_pilot) | 105 passed, exit 0 (M1 28 · M3 42 · M4 16 · M5 9 · M6 10) |
| `pytest tests` (legacy) | 218 passed / 225 failed: số pass không đổi so với các mốc trước |
| `python scripts/contract_audit.py` | 115 lời gọi từ console, **115 khớp**, 0 thiếu route, 0 sai method, 0 không xác định; OpenAPI có 146 operation |
| `python deploy/smoke.py` qua gateway thật | 17/17 PASS, gồm đăng nhập, SSE qua gateway, logout hủy phiên |

## 2. Hợp đồng client ↔ server (đã đo)

- `scripts/contract_audit.py` sinh OpenAPI từ chính app (cùng đường import với production) và quét toàn bộ `frontend/src`:
  - lời gọi `fetchJson`, `api.request`, `fetch` trực tiếp, `EventSource`;
  - URL mở bằng anchor (`${API_BASE}/…`).
  Mỗi lời gọi được đối chiếu với operation server theo method và path. `--write` xuất bảng chi tiết ra [API_CONTRACT.md](API_CONTRACT.md), gồm cả danh sách 37 operation server chưa có caller trong console (API cho CLI, endpoint tương thích cũ, admin chưa có màn hình).
- `tests_pilot/test_m6_contract.py` chạy audit này như một test: thêm một lời gọi lệch contract là suite đỏ.
- Các lệch contract đã sửa:

| Vấn đề | Trước | Sau |
|---|---|---|
| Họ `/intel/*` | 4 lời gọi tới route **không tồn tại** (luôn 404), trang lỗi im lặng | Chuyển sang `/threat-intel/summary`, `/sync`, `/cve/{id}`, `/kev`; client chuyển đúng shape (KEV trả list) |
| Body của `POST /engines/test` | Server trả `{status, probes}`, client đọc `{overall_status, results, duration_ms}` | Thống nhất `{overall_status, results, duration_ms, scope}` |
| Engine health | `GET /engines/health` luôn trả `all_healthy: true` và mọi engine `ONLINE`, kể cả khi không có binary ("lab runner"). `check-updates` luôn `UP_TO_DATE` | **Một contract duy nhất** dựa trên trạng thái đo được: `OPERATIONAL` / `DEGRADED` / `UNAVAILABLE` theo worker heartbeat, snapshot advisory và lần chạy thành công gần nhất. Engine cũ (nuclei, ZAP, trivy, crawler, empire_engine) là `NOT_INTEGRATED`. `test` là self-test trong process với input tổng hợp; `check-updates` báo `latest_version: null` thay vì khẳng định đã cập nhật |
| `verification_status` | Cờ `VERIFIED` không kèm bằng chứng (368 hàng trong đợt kiểm định). UI tự hiện `VERIFIED` khi thiếu giá trị | Thêm `verification_state`, suy ra từ bảng proof: `VERIFIED` khi có proof `VERIFIED`, `UNPROVEN` khi cờ bật mà không có proof. Thêm `verification_proof`. UI hiện số UNPROVEN riêng |
| Asset ngoài scope | `GET /assets/{id}` trả 403 | Trả 404 như mọi object ngoài scope |
| Gọi `runs` theo ngày | Template string lồng nhau | Viết lại một dạng để audit đọc được |

- Contract của các API chính (đã đo trong test):
  - Inventory có phân trang (`items/total/page/size/pages`).
  - Ước lượng trước khi chạy: `/plans/preview`.
  - Launch `202` trả `batch_id`, `accepted_at`, `tracker`, `correlation_id` và số lượt **dự kiến** (`plan.summary.queue`).
  - Chưa có worker → `worker.ready=false` kèm lý do. `/healthz/ready` không phụ thuộc worker.
  - API 404 trả JSON có `request_id`.

## 3. Dữ liệu giả đã gỡ khỏi đường production (đã đo phần backend)

- **Đồng bộ threat intel** từng nạp fixture tổng hợp mà vẫn báo `success`:
  - CISA KEV và NVD: khi feed thật trả rỗng hoặc lỗi.
  - EPSS: khi DB chưa có CVE.
  - OSV và GHSA: **luôn luôn**, vì không có client chạy live.

  Sau khi sửa:
  - Feed thật lỗi → `failed` kèm lý do.
  - OSV/GHSA báo "chưa cấu hình" (engine SBOM dùng snapshot do owner nhập).
  - Fixture chỉ được nạp khi gọi tường minh, và bị chặn ở production (API trả 403, image không chứa `fixtures/threat_intel`).
- **Trang Integrations** (đọc mã) từng giả lập "Engines Verified 100% healthy" bằng `setTimeout`, thẻ OPERATIONAL viết cứng, và nút "gửi webhook thử" không gửi gì. Nay trang chỉ hiện engine/worker và trạng thái feed thật; webhook ghi rõ là chưa có trong pilot.
- **Trang Threat intel** (đọc mã) từng viết cứng 4 dòng "Synchronized". Nay hiện trạng thái thật của từng nguồn.
- **Trang Health** (đọc mã) từng tô xanh mọi engine. Nay tô theo trạng thái, hiện lý do và lần thành công gần nhất.

## 4. Gateway, same origin, cache (đã đo)

Đã đo qua gateway thật bằng smoke test (đã kiểm từ trước, giữ nguyên):
- `/api/v1/*` và `/healthz/*` đi FastAPI. `/health/` là trang tĩnh.
- API 404 là JSON; trang 404 là HTML; không có HTML fallback cho đường API.
- `_worker.js` không được phục vụ.
- Cache:
  - Asset `_next/static` để `immutable`; HTML để `no-cache`.
  - API mặc định `no-store`; report và output trả `private, no-store`.
- SSE stream qua gateway không bị buffer.

Đã thêm ở mốc này:
- **Cloudflare Access ở origin** (`deploy/gateway/access.py`), áp dụng cho mọi request (trang, API, SSE) trừ `/gateway/live`:
  - Kiểm chữ ký RS256 theo JWKS của team (có cache, tự tải lại khi gặp `kid` lạ), `aud`, `iss`, `exp`/`nbf` (leeway 60 giây). Chặn nhầm thuật toán (HS256).
  - Thiếu, hết hạn, sai audience, sai issuer, sai chữ ký đều trả 403 với mã riêng. API trả JSON; trang trả text hướng dẫn đăng nhập lại.
  - `NOOSPIRE_ACCESS_REQUIRED=true` mà thiếu cấu hình → 503 `ACCESS_NOT_CONFIGURED` (fail closed).
  - Gateway xóa mọi header danh tính `X-Noospire-Access-*` do client tự gửi, chỉ chuyển tiếp email/sub đã xác minh.
  - Test dùng khóa RSA sinh lúc chạy và JWKS nạp sẵn, không gọi Cloudflare thật.
- **Console** (đọc mã):
  - Lỗi Access có loại riêng `access_denied`.
  - Polling khi nhận 401/403 sẽ dừng và báo phiên kết thúc. **Lỗi cũ đã sửa:** trước đây trường hợp này lặp gọi liên tục, không có khoảng nghỉ.
  - Host `*.trycloudflare.com` tự dùng polling theo cursor thay cho SSE.

## 5. Đóng gói (đọc mã; máy này không có Docker và Node)

- **Image ghim theo digest** (lấy từ Docker Hub ngày 2026-11-11):

  | Image | Digest |
  |---|---|
  | `python:3.14-slim` | `sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f` |
  | `node:22-alpine` | `sha256:0e1754758c2df4cfa3e68d59e2e1b7374bb7fd9ea6328eaaacf15cc934af8202` |
  | `cloudflare/cloudflared:2026.10.7` | `sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba` |

  - Python đổi từ 3.12 lên 3.14 cho khớp venv đã chạy test với bộ `requirements.txt` đã khóa.
  - Node đổi từ 20 (đã hết hỗ trợ tháng 4/2026) lên 22 LTS.
- **`.dockerignore`** loại `.git`, `.agents`, `.venv`, mọi DB/WAL/SHM, backup, storage, `.env`, khóa, `node_modules`, `.next`, `out`, test, docs, fixture threat intel. Image backend chỉ chép `fixtures/rules` (mẫu an toàn để thử rule).
- **Compose**:
  - `cloudflared` chỉ nằm trong mạng `connector` (internal, chỉ có gateway) và `tunnel-egress`. Trước đây nó nằm chung mạng `internal` với API/DB.
  - Gateway publish chỉ trên `127.0.0.1:8080`.
  - Biến `NOOSPIRE_ACCESS_*` mặc định `REQUIRED=true`.
  - `cloudflared` có `--grace-period`, `--retries`, metrics trên loopback.
- **Lỗi thật đã sửa**: service `scheduler` trong compose chạy `backend/app/scheduler_main.py`. File này vẫn khởi động scheduler **cũ** (DailySchedule → scan engine "all" ngoài luồng phòng thủ), không phải scheduler Mốc 4. Đã chuyển sang monitor scheduler.

## 6. Runbook

[RUNBOOK.md](RUNBOOK.md) gồm: kiến trúc mạng, khởi động sạch, cấu hình Named Tunnel và Access, firewall egress cho QUIC/HTTP2, health, truy log theo correlation ID, đổi token, backup/restore, dừng khẩn cấp, rollback app/schema, thu hồi quyền ở cả Access lẫn app.

## 7. Còn thiếu để triển khai thật

| Hạng mục | Trạng thái | Cần gì |
|---|---|---|
| Build image, chạy compose | chưa làm | Host có Docker. Sau khi build, ghi digest image của app vào bàn giao |
| Build console thật (`next build` → `out/`) | chưa làm | Node 22 (test smoke đang dùng export thay thế tối giản) |
| Named Tunnel và Access | chưa làm | Hostname quản trị của Empire, tài khoản Cloudflare của chủ hệ thống, AUD/team domain, token qua secret store |
| Smoke test qua hostname thật, SSE qua Named Tunnel, connector restart | chưa làm | Như trên, cộng service token của Access |
| Firewall egress trên host | chưa làm | Quyền quản trị host pilot |
| Đổi tunnel token và mật khẩu Cloudflare cũ (đã lộ trong lịch sử git) | **chưa làm, bắt buộc** | Chủ hệ thống |
| Kiểm contract ở mức body/schema (ngoài method/path) | một phần | Mới test body cho các thao tác chính; chưa sinh type TypeScript từ OpenAPI |

Không có link preview nào chưa kiểm được đưa vào bàn giao này.
