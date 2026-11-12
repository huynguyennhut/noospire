# Bàn giao Mốc 4 · Lịch mỗi giờ, công suất và quan sát sự cố

Ngày: 2026-11-11 (UTC). Working tree trên `a0bb68d`, chưa commit. Tiếp nối [M3_HANDOVER.md](M3_HANDOVER.md).
Nhãn: **đã đo** = chạy thật · **đọc mã** = chưa chạy · **chưa làm**.

## 1. Kết quả đo

| Lệnh | Kết quả |
|---|---|
| `pytest` (tests_pilot) | 86 passed, exit 0, chạy 2 lần liên tiếp đều pass (M1: 28, M3: 42, M4: 16) |
| `pytest tests` (legacy) | 218 passed / 225 failed — không đổi so với M1/M3 |
| OpenAPI | 127 operation (thêm 14 operation M4, bỏ 8 operation `/schedules` cũ khỏi contract) |

Dữ liệu test là tổng hợp có nhãn: asset `svc-*`/`pilot-test-load-*` trên `*.pilot-test.invalid`, advisory `PILOT-TEST-*`. Load test chỉ dùng job SBOM nội bộ, không mở kết nối tới domain nào.

## 2. Một planner cho mọi kiểu kích hoạt (đã đo)

`backend/app/core/planner.py` được dùng cho cả nút **Chạy kiểm tra toàn hệ thống** (`selection.kind=all`), lựa chọn asset hoặc module, và lịch định kỳ. Test `test_same_planner_for_whole_system_selection_and_schedule` xác nhận ba đường cho ra cùng quyết định.

Với mỗi cặp (asset, engine), planner quyết định một trong ba:

| Quyết định | Khi nào | Mã lý do |
|---|---|---|
| `queue` | đủ đầu vào, còn quota, vừa cửa sổ | — |
| `defer` (tạo job, `available_at` muộn hơn) | host hết quota/giờ · host hết ngân sách egress/giờ · vượt cửa sổ thời gian (chuyển sang lane `long`) · profile chậm giãn cách theo host | `HOST_QUOTA` · `EGRESS_BUDGET` · `WINDOW_OVERFLOW` · `HOST_SPACING` |
| `skip` (không tạo job) | chưa có SBOM · chưa duyệt endpoint · chưa có advisory snapshot · đã có job cùng asset+engine đang chờ/chạy | `NO_ARTIFACT` · `NO_APPROVED_ENDPOINT` · `RULES_UNAVAILABLE` · `ALREADY_ACTIVE` |

- `ALREADY_ACTIVE` giải quyết va chạm giữa lịch mỗi giờ và chạy tay: lượt sau không tạo job trùng.
- **Profile**:
  - `light`: kiểm tra nhanh, timeout tls 30 giây / sbom 60 giây.
  - `slow`: tối đa 1 worker, cách nhau 20 giây giữa các request tới cùng host, timeout lớn hơn.
- **Giới hạn**: chủ hệ thống chỉnh số worker tối đa cho từng lịch (`max_workers`), cùng ba giới hạn toàn estate qua `PUT /operations/capacity`: `max_running_executions`, `per_host_hourly_quota`, `per_host_egress_bytes_hourly`.
- **Xem trước** (`POST /plans/preview`, không ghi gì): số asset trong scope, số cặp queue/defer/skip, lý do, thời điểm xong ước tính theo backlog hiện có, có vừa cửa sổ không, và giờ tiếp tục của việc bị dời.
- **Chạy** (`POST /runs`, nhận `Idempotency-Key`): trả 202 kèm `batch_id`, `accepted_at`, `correlation_id` và link `/engine-runs/?run=`.
  - Quyền được kiểm trước khi tra key. Key được tính theo từng người dùng.
  - Cùng key + cùng body → 200, trả về đúng batch cũ. Khác body → 409.

## 3. Lịch, slot và khôi phục (đã đo)

- Bảng `schedule_slots` có ràng buộc unique `(schedule_id, slot_at)`. Ghi slot, lập kế hoạch và tạo execution diễn ra trong **cùng một transaction**:
  - Scheduler thứ hai đụng ràng buộc khi commit và rollback toàn bộ, nên không có claim nửa vời.
  - Process chết giữa chừng thì không có gì được ghi; tick sau làm lại đúng slot đó.
- Slot được căn theo UTC epoch. ICT là UTC+7 và không có giờ mùa hè, nên slot HH:00 UTC cũng là HH:00 ICT. DB lưu UTC; API trả `display_timezone=Asia/Ho_Chi_Minh`.
- **Khi lượt cũ còn chạy** (vẫn còn execution lane `quick` chưa xong):
  - Slot mới được ghi là `coalesced` và đặt `pending_catchup`.
  - Khi lượt cũ xong, đúng **một** lượt bù (`kind=catchup`) được chạy, mang `coalesced_slots=N`.
  - Lượt bù được claim bằng một conditional UPDATE `pending_catchup true→false`, nên hai scheduler cũng chỉ chạy một lượt bù.
- **Sau restart hoặc mất điện**: chỉ chạy slot mới nhất. Các slot đã lỡ được ghi vào `missed_before`, không chạy dồn từng slot một.
- **Theo dõi kết quả**:
  - Mỗi slot kết thúc ở một trong bốn trạng thái: `completed`, `partial`, `failed`, `no_work`.
  - Lịch lưu riêng ba mốc: `last_run_at`, `last_full_success_at` và `latest_result` (kể cả partial).
  - Lý do skip do chưa cấu hình (`NO_ARTIFACT`, `NO_APPROVED_ENDPOINT`) không làm kết quả thành partial. Các lý do còn lại có làm.
- API: `GET/POST /monitor-schedules`, `PATCH /monitor-schedules/{id}` (có `expected_revision`, sai → 409), `GET /monitor-schedules/{id}/slots`. Chỉ owner được dùng.
- Interval phải chia hết 1440 phút. Bật lại một lịch đang tạm dừng không chạy bù các slot lỡ trong lúc dừng.
- `SENTINEL_PROCESS_ROLE=scheduler` giờ chạy scheduler mới, gồm cả reaper và chuyển dead letter. `DailySchedule` cũ không còn khởi chạy job. `/api/v1/schedules` trả **410** kèm `replacement`. Trang `/schedules` và `api.ts` đã chuyển sang API mới.

**Test cấp process** (`test_m4_process.py`, DB file, process thật):
- Hai process scheduler tick mỗi 0,5 giây cùng lúc → đúng **1** slot và 1 batch 40 execution.
- `missed_before=2` vì lịch được lùi về 3 giờ trước.
- Sau khi worker chạy xong, slot chuyển `completed` và lịch có `last_full_success_at`.

## 4. Công suất (đã đo)

- **Trần toàn estate nằm ngay trong câu claim**: điều kiện `(số lease còn sống) < max_running_executions` là một phần của `UPDATE … WHERE` trên SQLite. SQLite tuần tự hóa các thao tác ghi, nên kiểm trần và claim là một bước nguyên tử.
- **Lỗi thật đã sửa**: worker claim job ngay cả khi không còn slot rảnh. Job đó giữ lease mà không có heartbeat, quá 60 giây thì reaper lấy lại trong lúc job vẫn đang chờ. Nay worker chỉ claim khi `_inflight < max_concurrent`.
- **Lý do worker tạm dừng nay hiện ra ngoài**: khi máy chủ vượt ngưỡng CPU/RAM, worker vẫn tự ngừng nhận job như trước. Trước đây việc này chỉ ghi log. Nay lý do nằm ở `worker_heartbeats.throttle_reason`, hiện trên dashboard, và ngưỡng chỉnh được qua `SENTINEL_THROTTLE_CPU_PCT` / `SENTINEL_THROTTLE_MEM_PCT`.
  - Ở Mốc 4, máy dev ở mức RAM 97% làm worker im lặng không nhận job. Đây là cách lỗi này được phát hiện.
- **Số đo mỗi attempt** (bảng `execution_metrics`):

  | Đại lượng | Độ chính xác |
  |---|---|
  | Thời gian engine, thời gian giữ slot (`slot_ms`, từ lúc bắt đầu attempt đến commit), độ trễ hàng đợi, byte input/output, byte egress của TLS | chính xác |
  | CPU, RSS | mẫu của cả process worker, có ghi chú rõ trong API |

  `GET /operations/metrics` trả p50/p95, số retry, số theo trạng thái, và usage theo host trong 1 giờ so với quota và ngân sách egress.
- **Công thức công suất lý thuyết**: `3600 × max_running_executions / số giây giữ slot trung bình`. Ban đầu công thức dùng thời gian engine thuần (9 ms) và cho ra 361.809 job/giờ, cao hơn thực đo 13 lần. Đã sửa sang dùng `slot_ms`.

**Load test có kiểm soát** (đã đo): 40 job SBOM nội bộ, 2 worker process, trần toàn estate = 3.

| Chỉ số | Giá trị |
|---|---|
| Kết quả | 40/40 succeeded, 40 attempt, không execution nào commit hai lần |
| Đỉnh attempt chạy đồng thời (tính từ timestamp attempt) | 3 (bằng trần) |
| Cả 2 worker đều nhận việc | có |
| Khoảng xử lý | 5,25 giây → **27.437 job/giờ thực đo** |
| Công suất lý thuyết theo công thức | 82.051 job/giờ |
| engine p50 / p95 | 0,009 / 0,155 giây |
| slot p50 / p95 | 0,073 / 0,519 giây |
| Độ trễ hàng đợi p50 | 10,5 giây (job chờ trước khi worker được khởi động, đúng như kịch bản test) |
| CPU trung bình / RSS tối đa | 15 ms / 117 MB |

Thực đo thấp hơn lý thuyết khoảng 3 lần. Nguyên nhân: khi claim bị trần từ chối, worker nghỉ 1 giây rồi mới thử lại. Muốn tăng throughput thì giảm khoảng nghỉ này, đổi lại DB bị hỏi nhiều hơn lúc rảnh. Hiện chưa đổi.

## 5. Event, SSE và quan sát (đã đo, trừ phần UI)

- `GET /events?after=&limit=`: polling theo cursor (`id` tăng đơn điệu), có `has_more`, `head`, `poll_after_seconds=10`.
- `GET /events/stream` (SSE). Hợp đồng:
  - `retry: 3000` · `hello` (server_time, cursor) · các event mang `id` là cursor.
  - Tên event: `execution` | `run` | `schedule` | `scan`.
  - `heartbeat` mỗi 15 giây; mỗi heartbeat kiểm lại phiên, phiên hết hạn thì gửi `auth_revoked` và đóng stream.
  - `reset` khi cursor không còn replay được.
  - Stream tự đóng sau `max_seconds` (mặc định 300 giây, dưới timeout idle của Cloudflare). Trình duyệt kết nối lại kèm `Last-Event-ID`.
  - Stream đọc từ DB nên chạy được khi API và worker là các process khác nhau.
- **Phạm vi event**: owner thấy tất cả. Người khác chỉ thấy event của asset mình có quyền READ, không thấy event cấp estate.
- Đã đo: replay đúng các event sau `Last-Event-ID`, có heartbeat, có reset, logout ở tab khác làm stream nhận `auth_revoked`, người xem ngắt kết nối không ảnh hưởng job.
- **Correlation ID** đi xuyên suốt:
  - Chạy tay dùng request ID của API làm correlation ID; lịch tạo một mã `slot-…`.
  - ID này đi vào batch → mọi execution → mọi event (`details.correlation_id`) → `/runs/{id}`.
  - Report chưa in ID này (xem mục 7).
- **`GET /operations/overview`**:
  - Giờ server, `event_cursor`, các lịch (owner).
  - Theo từng engine: lần thành công cuối, kết quả mới nhất, mức stale (ngưỡng = 2 × interval nhỏ nhất), số job chờ/chạy, tuổi job chờ lâu nhất.
  - Job quá hạn: chờ quá 10 phút, hoặc đang chạy nhưng lease đã hết.
  - Trong 24 giờ: số lỗi parse và dead letter.
  - Độ mới evidence, tuổi feed advisory, worker (kèm lý do tạm dừng), cấu hình công suất.
- **Dead letter**: khi job trong hàng đợi hết lượt retry, execution chuyển `failed` với `error_class=DEAD_LETTER` và phát event `EXECUTION_DEAD_LETTER`. Trước đây execution bị kẹt ở `running` mãi mãi.

## 6. UI (đọc mã; chưa build vì máy không có Node)

- `/schedules/` được viết lại thành **Lịch & công suất** (vi/en):
  - **Chạy kiểm tra toàn hệ thống**: chọn engine và profile → xem trước tác động → xác nhận → hiện batch, giờ nhận theo ICT, correlation ID và link theo dõi.
  - **Thẻ lịch**:
    - Giờ chạy kế tiếp theo ICT và countdown cập nhật mỗi giây từ `next_run_at` cộng độ lệch giờ server. Nhịp countdown không gọi API.
    - Lần chạy trước, lần thành công đầy đủ gần nhất, kết quả mới nhất kể cả partial.
    - Số slot lỡ/gộp, lượt bù đang chờ, backlog, giờ dự kiến xong, lý do quá hạn.
    - Bảng slot, nút đổi profile, nút tạm dừng/bật lại, form tạo lịch.
  - **Bảng theo engine**: độ stale và tuổi hàng đợi.
  - **Panel vận hành**: worker (kèm lý do tạm dừng), job quá hạn, lỗi parse, dead letter, tuổi feed.
  - **Form công suất** và **bảng số đo**: p50/p95, CPU/RAM, byte, theo host.
  - **Event gần đây**: mỗi event kèm link tới lượt chạy.
- `frontend/src/lib/events.ts`: mỗi trình duyệt chỉ mở **một** EventSource cho mọi tab của cùng người dùng.
  - Tab giữ Web Lock `noospire-events` mở EventSource và phát lại qua BroadcastChannel; các tab khác chỉ nghe.
  - Lỗi lặp lại thì chuyển sang polling cursor mỗi 10 giây, backoff có jitter.
  - Trang tải lại khi có event thật (gộp trong 1 giây) và dự phòng mỗi 60 giây.
- `/engine-runs/?run=<batch_id>`: hiện lượt chạy (theo trạng thái, lý do skip/dời, lane, từng execution), polling cho tới khi kết thúc.

## 7. Chưa làm hoặc chưa đo

- **PostgreSQL**: chưa đo. Trần công suất ở đó là đếm rồi mới claim, không nguyên tử như SQLite; hai worker có thể vượt trần thêm một job.
- **Tải với tls_health**: chưa có load test vì không gọi mạng thật. Quota, egress và giãn cách theo host mới đo ở bước lập kế hoạch.
- **UI**: chưa build, chưa typecheck, chưa thử trên trình duyệt (Vòng B vẫn chờ Node 20).
- **Report** chưa in correlation ID, template version và checksum trong nội dung (Mốc 5).
- **Trang Settings** vẫn có số `active_schedules: 3` viết cứng (Mốc 5).
- **Đường dispatcher cũ** (hàng đợi trong bộ nhớ, engine "all") vẫn còn, nhưng lịch và `/runs` không còn tạo job loại đó.
- **Throughput**: khoảng nghỉ 1 giây khi claim bị từ chối đang giới hạn throughput (mục 4).
