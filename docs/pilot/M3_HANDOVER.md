# Bàn giao Mốc 3 · Engine phòng thủ và xử lý job có bằng chứng

Ngày: 2026-11-11 (UTC). Working tree trên `a0bb68d`, chưa commit. Tiếp nối [M1_HANDOVER.md](M1_HANDOVER.md).
Nhãn: **đã đo** = chạy thật · **đọc mã** = chưa chạy · **chưa làm**.

## 1. Kết quả đo

| Lệnh | Kết quả |
|---|---|
| `pytest` (tests_pilot) | 70 passed, exit 0 (M1: 28, M3: 42) |
| `pytest tests` (legacy) | 218 passed / 225 failed, exit 1 — không đổi so với M1, không có 500 |
| OpenAPI | 121 operation (thêm 11) |

Dữ liệu test là tổng hợp có nhãn: advisory `PILOT-TEST-000x` / `CVE-2099-*`, package `pilot-test-*`, host `*.pilot-test.invalid`, HTTPS service cục bộ với chứng chỉ sinh lúc chạy.

## 2. Lát cắt 1 · SBOM (đã đo)

Luồng: owner nhập advisory snapshot OSV → upload SBOM → `POST /executions` (202) → hàng đợi DB → worker claim nguyên tử → driver phân tích tệp cục bộ → một giao dịch ghi kết quả có điều kiện fencing token → finding + evidence + report.

- **Driver** `noospire-sbom-native 1.0.0`, `execution_mode=native`. Không gọi mạng, không chạy subprocess.
  - Đọc CycloneDX JSON (component lồng nhau) và SPDX JSON.
  - So phiên bản theo đúng ecosystem: PyPI (PEP 440), SemVer (npm, Go, crates…), Maven.
  - Ecosystem không hỗ trợ bị liệt kê là "not evaluated", không đoán.
- **Advisory snapshot** có `digest` theo nội dung (không phụ thuộc thứ tự hay định dạng), số record, `data_modified_max` và tuổi.
  - Record `withdrawn` bị bỏ qua.
  - Severity lấy từ vector CVSS v3 (tự tính base score), sau đó `database_specific`. Nếu advisory không có severity thì đặt MEDIUM kèm nhãn `unrated_default`, không trình bày như điểm đã chấm.
- **Kết quả lưu**: thành phần, phiên bản, advisory, digest DB, bằng chứng khớp (`matched_by`, `range_events`), remediation. Tệp output JSON tất định kèm sha256, tải được qua `/executions/{id}/output`.
- **Trạng thái tách bạch**:

  | Tình huống | status | error_class |
  |---|---|---|
  | Có kết quả, kể cả 0 finding (đã đánh giá ≥1 thành phần) | `succeeded` | — |
  | SBOM không có thành phần | `skipped` | `INPUT_EMPTY` |
  | Không thành phần nào có purl + version hỗ trợ | `skipped` | `INPUT_NOT_EVALUABLE` |
  | JSON hỏng hoặc không phải SBOM | `failed` | `INPUT_PARSE_ERROR` |
  | Hash tệp lưu trữ không khớp | `failed` | `INPUT_INTEGRITY` |
  | Chưa nhập snapshot / snapshot hỏng | `unavailable` | `RULES_UNAVAILABLE` / `RULES_INTEGRITY` |
  | Vượt ngân sách thời gian | `timed_out` | `TIMEOUT` |
  | Hủy | `cancelled` | `CANCELLED` |

- **Vòng đời finding**:
  - Khử trùng theo fingerprint; giữ `first_seen` và `last_seen`, tăng `occurrence_count`.
  - Chỉ đánh dấu `FIXED` khi lượt mới đã đánh giá đúng thành phần đó và advisory vẫn còn trong bộ quy tắc. Thành phần vắng mặt trong SBOM mới thì giữ nguyên trạng thái.
  - Gặp lại thì chuyển `REOPENED`.
- **Report**: tạo theo `scan_id`, tải JSON/HTML/PDF; PDF bắt đầu bằng `%PDF`; header `private, no-store` và `X-Content-SHA256`.

## 3. Lát cắt 2 · TLS/health chỉ đọc (đã đo)

- Owner duyệt đúng một endpoint health cho mỗi asset (`PUT /assets/{id}/health-check`). Endpoint phải là https, không chứa credential, có thể kèm CA nội bộ. Mỗi lần duyệt có `revision` và được ghi audit.
- **Driver** `noospire-tls-health-native 1.0.0`:
  - Kiểm mọi địa chỉ phân giải; luôn chặn metadata; chỉ cho private/loopback khi owner bật.
  - Ghim IP đã kiểm (chống DNS rebinding), SNI = hostname.
  - Một lần GET, không theo redirect, không gửi credential, giới hạn body 64 KB, có timeout.
- **Output**: thời điểm quan sát, loại phép đo, `service_status` (up/degraded/down/unknown), mã HTTP, độ trễ, hạn chứng chỉ, số ngày còn lại, danh sách dữ liệu thiếu kèm nguyên nhân.
- **Phân biệt cấu hình và vận hành**:
  - Chứng chỉ hết hạn, sắp hết hạn (<14 ngày) hoặc xác minh lỗi → finding.
  - Dịch vụ không kết nối được → `service_status=down`, không phải finding.
- **Bị từ chối trước khi có I/O** (`skipped`): chưa duyệt endpoint (`NO_APPROVED_ENDPOINT`), egress bị chặn (`EGRESS_DENIED`), endpoint được duyệt lại sau khi job đã xếp hàng (`SCOPE_CHANGED`).

## 4. Hàng đợi, lease, attempt (đã đo)

- Một nguồn claim: dispatcher claim nguyên tử từ DB.
  - `backend/app/worker.py` cũ claim bằng một worker_id khác rồi để dispatcher lease lại không nguyên tử. Đã sửa.
- Mỗi attempt có `attempt_no`, `fencing_token`, `worker_id`, `phase` (preflight → running → reporting, tất cả trong cùng lease RUNNING), heartbeat, thời lượng theo đồng hồ đơn điệu, exit code và lỗi đã khử bí mật.
- Commit kết quả là một giao dịch `UPDATE scans … WHERE fencing_token = N`. Attempt mất lease thì bị đóng là `fenced` và không ghi gì; lượt retry sau đó thành công với token lớn hơn. Attempt bỏ dở bị đóng là `abandoned` khi có attempt mới.
- Idempotency theo cặp (người dùng, key):
  - Kiểm quyền trước khi tra key. Người khác hoặc không có grant nhận 404, không biết run có tồn tại.
  - Cùng key + cùng payload → 200 với cùng execution; khác payload → 409.
  - Hai submit đồng thời cùng key được chặn bằng ràng buộc unique.
- Readiness của worker là tín hiệu riêng (`/engines/workers`, bảng `worker_heartbeats`, hết hạn sau 30 giây). Khi chưa có worker, API vẫn nhận job ở trạng thái `queued` và nêu lý do.
- **Test restart cấp process**: API, worker, gateway chạy như process thật, DB là file. Các bước:
  1. Launch qua gateway khi chưa có worker.
  2. Restart API → job vẫn `queued`.
  3. Start worker → `succeeded`.
  4. Hard-kill cả 3 process rồi khởi động lại.
  5. Mở lại cùng execution, finding và report → dữ liệu và sha256 trùng khớp.
  6. Replay cùng Idempotency-Key → cùng execution.
  7. Logout → mọi phiên của user bị hủy.

### Lỗi tìm thấy và đã sửa trong mốc này
1. Lease chỉ được gia hạn khi status là `RUNNING`, trong khi dispatcher cũ chuyển sang `INITIALIZING`. Hệ quả: mọi job dài hơn khoảng 15 giây tự hủy. Reaper cũng bỏ sót job ở phase đó.
2. Worker có hai đường claim, một đường không nguyên tử.
3. Gateway gộp nhiều `Set-Cookie` thành một, nên đăng nhập qua gateway mất CSRF cookie.
4. Kho artifact lưu theo hash tái dùng tệp có sẵn mà không kiểm lại; tệp đã hỏng làm hỏng mọi lần upload sau.
5. Report lưu vào `storage/` theo thư mục hiện hành; nay theo `SENTINEL_STORAGE_DIR`.

## 5. API mới

| Method | Path | Quyền |
|---|---|---|
| POST | `/assets/{id}/artifacts?kind=sbom&filename=` (body thô) | SCAN trên asset |
| GET | `/assets/{id}/artifacts` | READ |
| PUT | `/assets/{id}/health-check` | owner |
| POST/GET | `/threat-intel/advisory-snapshots` | POST owner, GET đăng nhập |
| POST | `/executions` (`Idempotency-Key`) → 202 | SCAN |
| GET | `/executions`, `/executions/{id}`, `/executions/{id}/output` | READ, lọc theo grant |
| POST | `/executions/{id}/cancel` | SCAN |
| GET | `/engines/workers` | đăng nhập |
| GET | `/api/v1/version` | công khai |

## 6. UI (đọc mã; chưa build vì máy không có Node)

Trang mới `/engine-runs/`:
- Chọn asset trong phạm vi, upload SBOM hoặc chạy TLS. Mỗi lần bấm sinh một Idempotency-Key; nút bị khóa khi đang gửi.
- Hiện snapshot advisory đang dùng (digest, tuổi). Owner nhập snapshot ngay tại đây.
- Khi được nhận: hiện execution ID, batch ID, giờ nhận theo ICT và cảnh báo nếu chưa có worker.
- Panel chi tiết: polling 3 giây và dừng khi đến trạng thái kết thúc; hiện lý do, driver, rules digest, input sha, bảng attempt, link tải output, danh sách finding của lượt.
- Deep link `?execution=` và `?asset=` giữ khi bấm Back. Đã thêm vào menu (vi/en).

## 7. Chưa làm

- Engine nhóm web/API/mobile/hạ tầng (đọc OpenAPI, IAM, log gateway) và engine tích hợp hiện hữu (trivy/nuclei/zap) chưa gắn vào bảng execution mới. Đường dispatcher cũ vẫn còn hàng đợi bộ nhớ, lease không nguyên tử.
- Feed threat intel tự cập nhật (OSV/GHSA/KEV/EPSS): hiện chỉ nhập snapshot thủ công.
- Kill worker giữa chừng ở cấp process (đã kiểm ở mức unit bằng fencing và reaper); race giữa lịch hourly và chạy thủ công (Mốc 4).
- Report chưa gắn template version, snapshot và checksum trong nội dung (Mốc 5).
- Lớp AI/VACO: chưa làm, theo đúng yêu cầu chỉ làm sau khi luồng cơ sở có bằng chứng.
- Vòng B trên trình duyệt: chặn do thiếu Node.
