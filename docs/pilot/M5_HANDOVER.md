# Bàn giao Mốc 5 · Sáu màn hình quản trị cho ca trực

Ngày: 2026-11-11 (UTC). Working tree trên `a0bb68d`, chưa commit. Tiếp nối [M4_HANDOVER.md](M4_HANDOVER.md).
Nhãn: **đã đo** = chạy thật · **đọc mã** = chưa chạy · **chưa làm**.

## 1. Kết quả đo

| Lệnh | Kết quả |
|---|---|
| `pytest` (tests_pilot) | 95 passed, exit 0 (M1 28 · M3 42 · M4 16 · M5 9) |
| `pytest tests` (legacy) | 218 passed / 225 failed — không đổi so với M1/M3/M4 |
| OpenAPI | 146 operation (thêm 19 cho M5) |

Toàn bộ backend mục 2–8 **đã đo** qua API thật, hàng đợi DB và runner. Giao diện mục 9 chỉ **đọc mã**: máy chưa có Node nên chưa build, chưa typecheck, chưa mở trên trình duyệt.

## 2. Nền chung: observation, lịch sử thay đổi, thông báo theo người

Mỗi execution ghi kết quả, observation, lịch sử thay đổi và thông báo trong **cùng một transaction**, có fencing bảo vệ.

| Bảng | Nội dung |
|---|---|
| `finding_observations` | Mỗi lần đánh giá một finding sinh **một** observation, không bao giờ ghi đè. Kết quả là một trong `new`, `unchanged`, `reopened`, `fixed`, `unavailable` (lượt chạy lỗi: không đổi trạng thái), `changed_scope` (vị trí không còn được đánh giá, hoặc rule không còn trong bộ quy tắc) |
| `finding_changes` | Ai đổi trường nào, khi nào, từ giá trị nào sang giá trị nào, lý do, execution liên quan. Engine ghi với tên `noospire-engine`, triage ghi tên người dùng |
| `notifications` | Hộp thư riêng từng người. Người nhận là owner cộng các user có grant trên asset. Có dedup theo `(user, dedup_key)`. Đọc/xóa là thao tác riêng của mỗi người, không ảnh hưởng hộp thư người khác |

Thông báo được sinh khi:
- Có finding mới hoặc mở lại. Quá 5 finding trong một execution thì gom thành một thông báo tóm tắt, link tới danh sách đã lọc.
- Job thất bại: gửi owner và người bấm chạy.
- Job chạy tay hoàn tất: gửi người bấm chạy.
- Lượt chạy theo lịch kết thúc: gửi owner.
- Nguồn dữ liệu cũ (gửi owner, tối đa một lần mỗi ngày ICT): advisory snapshot quá 7 ngày, hoặc đang có job chờ mà 5 phút không có worker nào báo heartbeat.

## 3. Findings, evidence, remediation (đã đo)

- `GET /findings/{id}/history` trả về:
  - Các mốc thời gian: `first_seen_at`, `last_seen_at`, `last_verified_at` (lần quan sát gần nhất thực sự đánh giá được finding).
  - Nguồn (engine/driver/version), độ tin cậy, owner (`assessment_policy.owner_contact` của asset), người xử lý.
  - Toàn bộ lịch sử thay đổi và toàn bộ observation.
- `POST /findings/{id}/recheck` (nhận `Idempotency-Key`): chạy lại **đúng control đã sinh ra finding**, trên input đang được duyệt, qua chính planner của Mốc 4.
  - Endpoint này không tự đổi trạng thái finding. Chỉ runner đổi sang `FIXED`, và chỉ khi có bằng chứng tương đương.
  - Đã có execution đang chờ hoặc đang chạy cho control đó → trả 200 kèm execution ấy.
  - Finding không đến từ engine phòng thủ → 409.
  - Cần quyền SCAN trên asset.
- **Lỗi thật đã gỡ**: `POST /findings/{id}/retest` cũ gửi GET trực tiếp tới `target_location` rồi tự đặt `FIXED` khi nhận 401/403/404. Đây không phải control đã duyệt và không phải bằng chứng tương đương. Endpoint giờ là alias của recheck, được đánh dấu `deprecated`. `EvidenceViewer` cũng bỏ nhánh "preview" giả báo `VERIFIED_FIXED`.
- **Rescan asset**: `POST /runs` với `selection.kind=assets` tạo một batch mới trong scope của người dùng.
- **Triage** ghi `finding_changes` cho các trường status, assignee, ghi chú và retest_status.
- **Bộ lọc drill-down** trên `GET /findings`: `status_group=open|closed`, `outcome` + `day` (ngày ICT, tính theo observation), `execution_id`. Số lọc ra khớp chính xác với số trên dashboard (có test).
- **Kịch bản đo**:
  1. SBOM có lỗ hổng → 4 `new`.
  2. Upload SBOM đã vá rồi Recheck → 3 `fixed` và 1 `changed_scope` (thành phần không còn trong SBOM nên không coi là đã sửa).
  3. Upload lại SBOM có lỗ hổng → 3 `reopened` và 1 `unchanged`; owner và developer có grant đều nhận thông báo.
  4. SBOM hỏng → 4 `unavailable`, trạng thái finding giữ nguyên.

## 4. Dashboard và Health (đã đo)

`GET /dashboard/summary?days=7`, lọc theo scope của người xem:

| Phần | Nội dung |
|---|---|
| Cửa sổ | 7 ngày ICT |
| Health dịch vụ theo asset | Lấy từ phép đo tls_health gần nhất: up / degraded / down / unknown, kèm `observed_at`, cờ stale (quá 2 giờ) và lý do (chưa duyệt endpoint, chưa đo, lần đo cuối lỗi) |
| Worker | online / tổng / đang tạm dừng do tải |
| Rủi ro | Finding đang mở theo mức độ |
| Theo ngày | Số `new` / `reopened` / `fixed` của từng ngày ICT, đếm theo observation; `new_today` cũng đếm theo observation |
| Trạng thái dữ liệu | `as_of`, `data_state` (`ok` / `partial` / `unknown`) kèm lý do, và `last_real_data_at` |

- Chưa có phép đo thì không bao giờ báo "up".
- Dashboard cũ mặc định hiện `OPTIMAL` (xanh) khi các endpoint metrics (chỉ owner gọi được) lỗi. Nay mặc định là `UNKNOWN`.

## 5. Module hub (đã đo)

`GET /modules/hub` thay cho `/empire-modules` (endpoint cũ chỉ owner gọi được):
- Luôn có đủ 6 module, kể cả module chưa có asset nào trong scope.
- Tổng được đối soát với scope: `assets_in_scope = assets_in_modules + assets_unassigned`.
- Mỗi module có:
  - Health dịch vụ.
  - Coverage 24 giờ: số asset có lượt chạy thành công trên tổng số asset.
  - Finding đang mở theo mức độ.
  - Giờ chạy kế tiếp, tính từ các lịch bao phủ module đó.
  - Link tới đúng asset, finding và lịch sử của module.

## 6. Scan Center và tracker (đã đo)

- `GET /runs?day=` (mặc định là hôm nay theo ICT): mục **Kết quả hôm nay**, liệt kê từng lượt chạy trong ngày kèm diff 6 loại và lý do skip/fail.
- `GET /runs/{id}/tree`: cây module → asset → engine (execution) → attempt → evidence (sha của input và output, digest bộ quy tắc, link output, finding kèm kết quả quan sát).
- `GET /runs/{id}/diff`: số lượng và danh sách finding theo từng loại kết quả.
- Batch ID, giờ nhận, deep link và lựa chọn engine/profile đã có từ Mốc 4.

## 7. History và Reports (đã đo)

**Lịch sử chạy:**
- `GET /history`: lọc theo khoảng ngày ICT, run, asset, engine, module, người chạy, trạng thái; có phân trang.
- **Xóa chọn lọc** (chỉ owner) là *ẩn khỏi giao diện*:
  1. `POST /history/hide/preview` trả số mục sẽ bị ảnh hưởng; job đang chạy không bị ẩn.
  2. `POST /history/hide` yêu cầu `confirm_count` khớp số mục hiện tại (lệch → 409, phải xem trước lại) và một lý do.
  3. Thao tác được ghi audit `HISTORY_HIDE`. Evidence, finding và audit log vẫn giữ nguyên.
  - `POST /history/unhide` khôi phục. `/executions` cũng loại các mục đã ẩn.

**Report snapshot** (`POST /report-snapshots`, phạm vi theo asset, theo run, hoặc toàn hệ thống nếu là owner):
- Snapshot là JSON chuẩn hóa, có sha256 riêng.
- Nội dung gồm: tóm tắt cho quản lý, phạm vi, coverage, thay đổi so với kỳ trước cùng phạm vi, finding kèm evidence đã che dữ liệu riêng tư, remediation kèm owner/người xử lý, phụ lục lỗi và loại trừ, ghi chú về việc che dữ liệu, danh sách execution và correlation ID.
- Ba bản JSON/HTML/PDF đều render từ snapshot, mỗi bản có checksum riêng. HTML và PDF in template version cùng sha256 của snapshot.
- Tải về qua phiên đăng nhập:
  - Header `X-Content-SHA256`, `X-Snapshot-SHA256`, `X-Template-Version`, `private, no-store`.
  - Xem inline có CSP chặn script.
  - Tệp bị sửa → 409.
- **Tái hiện được**: sau khi đổi trạng thái finding, tải lại PDF vẫn ra đúng từng byte (PDF dựng ở chế độ `invariant`).
- **Phân quyền**: cần quyền REPORT trên từng asset. Người không phải owner không thấy report toàn hệ thống.
- Template là `noospire-pilot-report/1.0` (nội bộ), **chưa đối chiếu** với mẫu Empire đã duyệt vì chưa nhận được mẫu. Cần đối chiếu: bố cục, logo/nhãn, cách chấm mức độ, thứ tự các phần, chữ ký phê duyệt.
- PDF dùng font Unicode nếu tìm thấy trên server (DejaVu/Arial). Không có thì phiên âm bỏ dấu và ghi chú rõ trong PDF; HTML và JSON vẫn giữ dấu.

## 8. Notifications và Users (đã đo phía API)

- **Notifications**:
  - `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`, `DELETE /notifications/{id}`.
  - Thông báo của người khác trả 404.
  - Mỗi thông báo mang `link` mở đúng đối tượng: `/findings/?finding=`, `/engine-runs/?execution=` hoặc `?run=`.
- **Users**: API có từ Mốc 1 (danh sách, mời, bật/tắt, grant, audit lọc theo user/action), chỉ owner dùng được. Mốc này bổ sung màn hình.

## 9. Giao diện (đọc mã)

| Màn hình | Thay đổi |
|---|---|
| Shell · thông báo | Hộp thư theo từng người: đọc một, đọc hết, xóa. Server từ chối thì hiện lý do và tải lại. Badge số chưa đọc lấy từ server. Escape và click ra ngoài đều đóng popover; **lỗi cũ đã sửa**: trên mobile, click *bên trong* popover cũng làm popover đóng. Có `role=dialog` và `aria-expanded`. Click thông báo → đánh dấu đã đọc rồi mở đúng đối tượng |
| Dashboard | `DashboardSummaryPanel` ở đầu trang: băng trạng thái (`ok` / `partial` / `unknown` / mất backend, `as_of`, dữ liệu thật gần nhất), thẻ dịch vụ, worker, rủi ro (click mở danh sách đã lọc), cột theo ngày ICT (click hoặc phím mở danh sách finding mới của ngày đó). Tự tải lại khi có event |
| Module hub | Viết lại theo `/modules/hub`: đủ 6 card, có lỗi kèm nút thử lại, có câu đối soát tổng |
| Findings | Đọc tham số drill-down từ URL, deep link `?finding=`, `FindingLifecyclePanel` (các mốc thời gian, nguồn, độ tin cậy, owner, người xử lý, lịch sử thay đổi, mọi observation, nút Recheck và Rescan asset) |
| Engine runs | Cây lượt chạy và diff cho `?run=`; mục **Kết quả hôm nay** |
| Reports | Panel snapshot (tạo, xem inline trong iframe sandbox, tải 3 định dạng) và panel lịch sử (bộ lọc nằm trên URL nên Back giữ lại; ẩn có xem trước, lý do và xác nhận) |
| Users (mới, `/users/`) | Danh sách, bật/tắt (có xác nhận), mời user (chỉ các role không phải owner), grant theo asset, audit lọc theo người/hành động |
| Settings | Nút "xuất system audit" trước đây xuất dữ liệu bịa (mọi engine `OPERATIONAL`, 379 asset, 3 lịch). Nay xuất từ `/operations/overview` |

## 10. Chưa làm

- **Settings / Rules / Integrations**:
  - Rule chưa có bản nháp, thử trên dữ liệu mẫu, version/digest, người duyệt, ngày hiệu lực, rollback.
  - Webhook chưa có receipt và sink nội bộ.
  - Chưa có `PUBLIC_BY_DESIGN` cho `/media`.
  - Chưa phân loại portal login/JSON/bảo trì/timeout.
  - Chưa có telemetry throttling do Empire cấp.
- **Report**: chưa đối chiếu với mẫu Empire đã duyệt (chưa có mẫu). Endpoint `/reports` cũ vẫn còn song song với `/report-snapshots`.
- **Remediation, Scans, Active assessments**: chưa chuyển sang luồng mới. Trang Scan Center cũ vẫn gọi các API của engine cũ.
- **Dữ liệu owner**: chưa có API để sửa owner contact của asset; hiện chỉ đọc `assessment_policy.owner_contact`.
- **Giao diện**: chưa build, chưa typecheck, chưa thử bàn phím và focus trên trình duyệt thật (Vòng B chờ Node 20).
