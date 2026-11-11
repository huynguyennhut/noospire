# Báo cáo nghiệm thu cuối · Noospire pilot cho Empire (Mốc 7)

Ngày: 2026-11-11 (UTC). Branch `pilot/m1-m5-defensive-platform`: commit `f07f1ff` (Mốc 1–5), các thay đổi Mốc 6–7 chưa commit.
Nhãn: **đã đo** = chạy thật · **đọc mã** = chưa chạy · **bị chặn** = thiếu đầu vào (kèm nguyên nhân).

## 1. Hai lần nghiệm thu

| | Vòng A | Vòng B |
|---|---|---|
| ID | `RA-20261111T134358Z-934a64` | `RB-20261111T131609Z-e8a5c4` |
| Môi trường | Suite `tests_pilot`. Mỗi test dùng DB SQLite riêng, xóa sau khi chạy. Engine phòng thủ thật, input kiểm soát | Dựng lại từ artifact bàn giao (`scripts/round_b_stack.py`): process API, worker, scheduler, gateway như compose. Console build thật bằng Node 22.23.4. DB file bền vững. Trình duyệt Chromium trong app Claude, desktop 1024×768 và viewport điện thoại 375×812 |
| Kết quả | **118 passed, exit 0**, JUnit ở `acceptance/RA-20261111T134358Z-934a64.junit.xml` | Đi hết các luồng ở mục 3. Tìm ra **1 lỗi P0** và **5 lỗi P1**, đã sửa và có test hồi quy (mục 4) |
| Chưa có | — | Image Docker (máy không có Docker) và private tunnel (chưa có hostname/credential Cloudflare). Mục 6 |

Lệnh khác và mã thoát (đều đã đo):

| Lệnh | Kết quả | Exit |
|---|---|---|
| `npx tsc --noEmit` (frontend) | sạch | 0 |
| `npm run build` (Next 14.2.35, static export, có lint) | 21 trang | 0 |
| `python scripts/contract_audit.py --write` | 115/115 lời gọi khớp OpenAPI (146 operation) | 0 |
| `python deploy/smoke.py` qua gateway thật (trong suite) | 17/17 PASS | 0 |
| `pytest tests` (legacy) | 218 passed / 225 failed (không đổi từ Mốc 1; suite cũ giả định không cần đăng nhập và dùng chung DB repo) | 1 |

## 2. Vòng A theo ca bắt buộc

| Ca | Bằng chứng (file test) | Trạng thái |
|---|---|---|
| Đăng nhập và grants | `test_m1_identity_scope.py`: owner, developer, viewer, tài khoản bị vô hiệu hóa, scope theo object (404), thu quyền, stream bị cắt sau khi thu quyền | đã đo |
| Lỗi origin | `test_m1_gateway.py`: 502/503/504, timeout, HTML, origin bị kill giữa phiên, DB rỗng vẫn rỗng, không sinh account/job/finding. Kèm test hồi quy cookie (P0) | đã đo |
| Fixture 379 và kho tùy ý | `test_m7_round_a.py`: 379 = 368 + 6 + 5, 728 lượt. Các trường hợp 0, 1 và 500 hàng. Alias lỗi → `INVALID_ALIAS`. Profile không có engine → `NO_APPLICABLE_ENGINE`. Endpoint fixture không ghi DB | đã đo (có sửa planner) |
| Engine thực | Golden output SBOM (`data/golden_sbom_matches.json`), lỗi parse, adapter/binary thiếu → `ENGINE_UNAVAILABLE`, timeout → `TIMEOUT`/124, kết quả 0 finding hợp lệ, lỗi được khử token và bearer, hash evidence. TLS đo dịch vụ HTTPS cục bộ | đã đo |
| Lịch, mất worker, idempotency | Hai scheduler (process thật) tranh một slot; retry request; **kill worker ở preflight và sau khi đã ghi output** → đúng một kết quả logic (4 finding, `occurrence=1`); hủy giữa lúc chạy → bị chặn bằng fencing, không có finding | đã đo |
| Findings và retest | Observation và lịch sử thay đổi; recheck chạy đúng control; chỉ đổi FIXED khi có bằng chứng tương đương; lỗi → `unavailable` | đã đo. **Chưa làm**: `PUBLIC_BY_DESIGN`, phân loại `inconclusive` |
| Event, notification, chart | Replay 260 event qua 3 trang cursor, không trùng không hở; SSE với `Last-Event-ID` hai lần ra cùng tập; ranh giới ngày ICT (16:59:59Z và 17:00:00Z thuộc hai ngày); thông báo riêng theo người; số trên chart khớp bộ lọc | đã đo |
| History và report | Snapshot bất biến; PDF qua parser cấu trúc (xref, offset object); JSON đúng schema; HTML escape `<script>`; tải có phân quyền; ẩn có audit | đã đo |
| Đóng gói và mạng | Build console sạch; start API và readiness; backup → restore-check; **nâng cấp DB đời cũ** (bản sao `noospire.db`, 603 asset giữ nguyên, bảng mới được tạo) | đã đo. Docker: bị chặn |

## 3. Vòng B: các luồng đã chạy trên trình duyệt (đã đo)

1. **Đăng nhập**: sai mật khẩu → báo lỗi và ở lại trang. Đúng mật khẩu → vào dashboard. Đăng xuất → mở deep link finding bị đưa về `/login/`, tải report trả 401.
2. **CTA "Chạy kiểm tra toàn hệ thống"**:
   - Xem trước: 3 asset, 6 cặp asset/engine, có lý do skip (`NO_APPROVED_ENDPOINT` ×2, `NO_ARTIFACT` ×1).
   - Xác nhận → batch `2adcf450…` nhận lúc 20:24:44 ICT, kèm correlation ID.
   - Tracker: 3 execution `succeeded`, diff 9 finding mới, cây module → asset → engine → attempt → evidence.
   - Đóng tab, mở deep link ở tab mới → cùng execution, attempt, driver/version, digest bộ quy tắc, output hash.
   - Engine TLS đo được thật dịch vụ HTTPS cục bộ: chứng chỉ còn 10 ngày → 1 finding HIGH.
3. **Finding → Recheck**: observation thứ hai `unchanged`, execution mới `007385ed`, output hash mới, cùng digest bộ quy tắc. Lịch sử ghi actor và thời điểm.
4. **Notifications** (desktop):
   - Badge số chưa đọc; mở popover; xóa → server còn 11; Escape đóng.
   - Bấm một thông báo → đánh dấu đã đọc (còn 10) và mở đúng modal finding.
   - Mobile: mở được; click bên trong không đóng, click ra ngoài thì đóng (kiểm bằng hit-test DOM). Ảnh chụp trong chế độ giả lập không thấy popover → **chưa xác minh bằng mắt**.
5. **Chart → bộ lọc**: cột CRITICAL trên dashboard mở `/findings/?status_group=open&severity=CRITICAL`, ra 4 dòng, đúng bằng con số trên chart.
6. **Report**:
   - Tạo snapshot từ UI (9 finding, template `noospire-pilot-report/1.0`).
   - PDF, HTML và JSON tải bằng phiên đã đăng nhập; sha256 khớp ở ba nơi (tự tính, header, danh sách). HTML có CSP và không chứa `<script>`.
   - Xem inline bằng cách mở thẳng URL. Iframe trong trang bị chính trình duyệt nhúng chặn (`ERR_BLOCKED_BY_CLIENT`), không phải lỗi app.
   - Tổng số giống nhau ở dashboard, tree, JSON và HTML: 9 finding (4 CRITICAL / 1 HIGH / 4 MEDIUM).
7. **Users và grants**:
   - Owner tạo developer trên UI và cấp READ, SCAN, REPORT trên `pilot-test-api`; audit ghi `GRANT_CREATE`.
   - Developer chỉ thấy 1 asset và 4 finding; finding của asset khác 404; report chung 404; report riêng của asset được cấp 200; quản trị lịch 403.
   - Owner thu quyền trong lúc developer đang mở trang → deep link báo "Không tìm thấy hoặc ngoài phạm vi" kèm request ID, report 404, số asset 0.
8. **Mất origin**:
   - Tắt API khi đang mở Health/Dashboard → băng đỏ "Mất kết nối backend" kèm request ID, tình trạng an ninh `UNKNOWN`, không có màu xanh.
   - Bật lại → tự phục hồi không cần tải trang, phiên vẫn còn.
9. **Lịch và mất worker**:
   - Tạo lịch 15 phút trên UI; countdown giảm mỗi giây mà `/operations/overview` chỉ được gọi 3 lần.
   - Slot 20:45 ICT do process scheduler thật claim và kết thúc `completed`.
   - Tắt worker → job nằm ở hàng đợi, tuổi hàng đợi tăng, worker hiện `stale`. Bật lại → xử lý hết; diff ra 9 `unchanged`, không nhân đôi kết quả.
10. **History**: lọc theo `engine=tls_health` → mở một execution → Back → bộ lọc và số đếm còn nguyên.
11. **Viewport điện thoại**: dashboard, schedules, findings, engine-runs, module hub, reports, users, health đều không cuộn ngang (scrollWidth 371 trên 375).
12. **Build và version**: trang Health hiện build `RB-20261111T131609Z-e8a5c4`, đúng giá trị `/api/v1/version` trả về.

Coverage lấy từ DB của Vòng B (đã đo):

| Hạng mục | Số liệu |
|---|---|
| Asset | 3 (mỗi module một), 2 asset có execution `succeeded` |
| Execution | sbom 4 · tls_health 3, đều `succeeded`; 7 attempt |
| Finding | 9 `NEW` (CRITICAL 4 · HIGH 1 · MEDIUM 4) |
| Observation | new 9 · unchanged 10 |
| Lịch sử thay đổi finding | 9 dòng |
| Thông báo | finding_new 9 · job_succeeded 6 |
| Khác | 2 report snapshot · 1 lịch · 1 slot `completed` · 24 event |
| Audit | 14 loại hành động, gồm `LOGIN_FAILED`, `GRANT_REVOKE`, `FINDING_RECHECK` |

Report mẫu đã khử dữ liệu (chỉ có dữ liệu tổng hợp `pilot-test-*`, không có email): [acceptance/sample_report.html](acceptance/sample_report.html) · [.json](acceptance/sample_report.json) · [.pdf](acceptance/sample_report.pdf).

## 4. Lỗi tìm thấy trong Mốc 7

| Mức | Lỗi | Tìm ở | Trạng thái |
|---|---|---|---|
| **P0** | Client httpx dùng chung trong gateway có cookie jar: phiên đầu tiên đăng nhập qua gateway bị gắn vào mọi request sau đó của bất kỳ ai, nên mọi người dùng thành owner | Vòng B | **đã sửa** (jar không lưu cookie) + test hồi quy với process thật |
| P1 | HTML report bị gateway đổi thành 502 `MISROUTED` | Vòng B | đã sửa (chỉ cho qua đúng route tải report có `X-Template-Version`) + test |
| P1 | Dashboard nạp sẵn số liệu bịa (rủi ro 100, 379 mục tiêu, 58 finding, rủi ro theo module, nhãn "+4% MoM", "Optimal"…) và vẫn hiện khi API lỗi hoặc người dùng không có quyền | Vòng B | đã sửa: gỡ toàn bộ |
| P1 | Trang đăng nhập dùng email thật của chủ hệ thống làm placeholder, ai chưa đăng nhập cũng thấy | Vòng B | đã sửa |
| P1 | Popover thông báo và modal finding không hiện hoặc nằm ngoài màn hình, do `.specular-highlight { position: relative }` đè lên `fixed`/`absolute`/`sticky` | Vòng B | đã sửa (`:where()`) + portal |
| P1 | Lỗi hydration React (#425/#418) làm mất cú bấm đầu tiên ở trang Lịch | Vòng B | đã sửa (nội dung trang render sau khi mount) |
| P1 | Runner bắt đầu chạy mà không kiểm lease, nên execution đã hủy bị kẹt ở `running` | Vòng A | đã sửa + test |
| P2 | `restore-check`/`backup` không đóng kết nối SQLite, báo lỗi trên Windows | Vòng A | đã sửa |
| P2 | Planner 379 nhận alias trỏ tới target không tồn tại, và target không có engine | Vòng A | đã sửa |
| P2 | Lỗi biên dịch `'\n'` trong Settings (từ Mốc 5) | Typecheck | đã sửa |
| P3 | Khi mất backend, các thẻ số cũ hiện `0` thay vì "—"; tuổi hàng đợi trên UI chỉ cập nhật khi có event; header còn chữ "empire.edu.vn SAME-ORIGIN" viết cứng; tab "lệnh cURL tái hiện" trong EvidenceViewer tự dựng lệnh cho finding SBOM; dòng "Dự kiến: 1 lượt" hiện cả khi chưa chọn asset | Vòng B | **chưa sửa** |

## 5. File sửa, migration và rollback, ma trận route

- **File sửa**: `git diff --stat a0bb68d`, gồm 148 file (+12.879 / −7.660), không tính `docs/pilot/acceptance`. Theo nhóm:
  - `backend/app/{api,core,engines,models,reporting,intel}`, `backend/main.py`
  - `deploy/` (gateway, access, smoke, Dockerfile, compose, `.env.example`)
  - `frontend/src` (lib, components, các trang)
  - `scripts/` (`contract_audit`, `round_b_stack`, `round_b_seed`)
  - `tests_pilot/`, `docs/pilot/`, `.dockerignore`
- **Migration**: pilot dùng `create_all`, chỉ **thêm** bảng: execution, operations, lifecycle, notification, report snapshot. Không sửa cột của bảng cũ. Đã đo nâng cấp tại chỗ trên bản sao DB đời cũ.
- **Rollback**: backup trước khi nâng cấp, rồi restore bản backup và quay lại image cũ ([RUNBOOK.md](RUNBOOK.md) mục 6 và 8). Không có migration xuôi/ngược theo phiên bản; việc này cần Alembic nếu chuyển sang PostgreSQL.
- **Ma trận route**: [API_CONTRACT.md](API_CONTRACT.md) (sinh tự động: method, path, nơi gọi, route server, 37 operation chưa có caller).
- **Runbook**: [RUNBOOK.md](RUNBOOK.md).

## 6. Bị chặn và nguyên nhân

| Hạng mục | Nguyên nhân | Cần |
|---|---|---|
| Build và chạy image Docker, ghi digest image app | Máy không có Docker | Host có Docker |
| Named Tunnel, Cloudflare Access thật, SSE qua tunnel, ngắt connector | Chưa có hostname quản trị, tài khoản Cloudflare, AUD/team | Chủ hệ thống cấp, qua secret store |
| Staging theo runbook; thử người dùng có và không có quyền qua Access | Như trên | Như trên |
| Đổi tunnel token và mật khẩu Cloudflare đã lộ trong lịch sử git | Chỉ chủ hệ thống làm được | Chủ hệ thống |
| PostgreSQL (claim nguyên tử dưới tải, Alembic) | Pilot dùng SQLite | Khi lên production |

## 7. Chấm lại theo thang 100

| Hạng mục | Điểm | Căn cứ |
|---|---|---|
| UI | **10/15** | Build, typecheck, lint sạch; chạy thật trên trình duyệt; sửa 5 lỗi P1. Trừ điểm: trang Scans, Active assessments, Remediation vẫn theo luồng cũ; còn lỗi P3; popover mobile chưa xác minh bằng mắt |
| API | **12/15** | 115/115 lời gọi khớp contract; 202 với batch ID và tracker; lỗi JSON có `request_id`; test body cho các thao tác chính. Trừ điểm: chưa sinh type từ OpenAPI; endpoint cũ còn song song |
| Queue và lịch | **12/15** | Claim nguyên tử, fencing, slot unique, chỉ một lượt bù, restart, trần công suất, kill worker ở hai thời điểm. Trừ điểm: chỉ đo trên SQLite; đường dispatcher cũ vẫn còn |
| Engine và evidence | **10/15** | 2 engine thật có golden output, hash, observation, recheck. Trừ điểm: chưa có engine cho web/API/hạ tầng; feed advisory chưa tự cập nhật; chưa có `inconclusive` và `PUBLIC_BY_DESIGN` |
| Quyền và phạm vi | **12/15** | Grants và 404 ngoài scope; thu quyền có hiệu lực ngay; Access JWT kiểm ở origin, fail closed. Trừ điểm: lỗi P0 rò phiên chỉ được Vòng B bắt; Access chưa triển khai thật |
| Report và history | **8/10** | Snapshot bất biến, checksum, 3 định dạng, ẩn có audit. Trừ điểm: chưa đối chiếu mẫu Empire |
| Triển khai và khôi phục | **7/15** | Backup/restore và nâng cấp DB cũ đã đo; restart process đã đo; runbook. Trừ điểm: chưa build image, chưa có tunnel, chưa staging |
| **Tổng** | **71/100** | |

## 8. Quyết định phát hành

**Chưa phát hành ra Internet.** Các P0 còn mở:
1. Tunnel token và mật khẩu Cloudflare đã lộ trong lịch sử git công khai, chưa đổi.
2. Named Tunnel và Access chưa triển khai và chưa nghiệm thu, nên Vòng B qua private tunnel chưa có.
3. Chưa có image Docker build từ artifact bàn giao (chưa có digest).

Lỗi P0 rò phiên qua gateway mà Vòng B tìm ra đã sửa và có test hồi quy. Cũng chính lỗi đó cho thấy cần chạy lại Vòng B đầy đủ (image + tunnel) trước khi go-live.

**Có thể dùng nội bộ ngay** trên host pilot, qua loopback `127.0.0.1:8080` và chỉ cho owner: luồng SBOM và TLS/health, lịch mỗi giờ, findings/recheck, report và history đều đã chạy qua cả hai vòng nghiệm thu.
