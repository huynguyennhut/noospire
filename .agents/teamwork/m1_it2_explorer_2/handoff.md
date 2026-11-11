# Milestone 1 Iteration 2 Explorer Report: Datetime Comparison Hazard & Drop-in Remediation

**Explorer**: `m1_it2_explorer_2` (M1 It2 Session Datetime Fix Explorer)  
**Working Directory**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_it2_explorer_2`  
**Parent**: Project Orchestrator (`eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb`)  
**Mission**: Investigate BUG-M1-01 in `backend/app/api/deps.py:131`, examine `tokens_valid_after` across `user.py`, `auth.py`, `security.py`, scan for similar hazards across the entire backend, and formulate a concrete, drop-in fix strategy.

---

## 1. Observation (Trực Tiếp Quan Sát Thực Nghiệm & Đo Kiểm)

### 1.1. Báo Động Đỏ BUG-M1-01: Lỗi So Sánh Datetime Tại `deps.py:131`
- **Tập tin bị lỗi**: `backend/app/api/deps.py`, dòng 119–137
- **Mã nguồn hiện tại**:
  ```python
  # Enforce session expiry via tokens_valid_after timestamp (F03)
  if token and hasattr(user, "tokens_valid_after") and user.tokens_valid_after:
      payload = decode_access_token(token)
      if payload:
          iat = payload.get("iat")
          if iat:
              if isinstance(iat, (int, float)):
                  token_issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
              elif isinstance(iat, datetime):
                  token_issued_at = iat
              else:
                  token_issued_at = None

              if token_issued_at and token_issued_at < user.tokens_valid_after:
                  raise HTTPException(
                      status_code=status.HTTP_401_UNAUTHORIZED,
                      detail="Session expired/revoked",
                      headers={"WWW-Authenticate": "Bearer"},
                  )
  ```
- **Thông báo lỗi nguyên văn khi chạy thực tế**:
  ```text
  TypeError: can't compare offset-naive and offset-aware datetimes
  [backend\app\api\deps.py:131 in get_current_active_user]
  ```
- **Chứng cứ đo kiểm lưu trữ SQLite**:
  Đo kiểm trực tiếp bằng script CLI:
  ```python
  Raw SQLite value: ('2026-11-10 19:44:32.932419',) <class 'str'>
  SQLAlchemy loaded value: 2026-11-10 19:44:32.932419 type: <class 'datetime.datetime'> tzinfo: None
  ```
  SQLite không có kiểu dữ liệu `TIMESTAMP WITH TIME ZONE` nguyên bản; SQLite lưu trữ dưới dạng chuỗi ISO format. Khi SQLAlchemy tải lại đối tượng qua `aiosqlite`, đối tượng Python trả về là **offset-naive (`tzinfo=None`)**. Trong khi đó, `token_issued_at` được gán timezone UTC **offset-aware (`tzinfo=datetime.timezone.utc`)**.
  Toán tử `<` giữa `token_issued_at` và `user.tokens_valid_after` ném ngoại lệ `TypeError` làm sập HTTP request với mã 500 Internal Server Error thay vì trả về HTTP 401 Unauthorized (`"Session expired/revoked"`).

### 1.2. Phát Hiện Lỗ Hổng Tương Tự Số 2: `backend/app/core/scheduler.py:156`
- **Tập tin**: `backend/app/core/scheduler.py`, dòng 140–156 (`SchedulerEngine.tick`)
- **Mã nguồn hiện tại**:
  ```python
  now = datetime.now(timezone.utc)
  ...
  for sched in schedules:
      if sched.next_run_at is None:
          sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
          await session.commit()
          continue

      if sched.next_run_at <= now:
          # Time to trigger
  ```
- **Chứng cứ đo kiểm thực nghiệm**:
  Khi nạp `DailySchedule` từ SQLite:
  ```text
  Loaded next_run_at: 2026-11-10 19:41:08.612268 tzinfo: None
  Comparison error: <class 'TypeError'> can't compare offset-naive and offset-aware datetimes
  ```
  Dòng 156 gặp lỗi chính xác như BUG-M1-01 khi chạy vòng lặp đánh giá lịch trình trên môi trường SQLite.

### 1.3. Điểm Rủi Ro Tiềm Tàng Số 3: `backend/app/intel/nvd.py:252`
- **Tập tin**: `backend/app/intel/nvd.py`, dòng 244–267
- **Mã nguồn**:
  ```python
  @staticmethod
  def chunk_date_range(start_date: datetime, end_date: datetime, max_days: int = 90) -> List[tuple[datetime, datetime]]:
      ...
      while current_start < end_date:
  ```
  Trong `sync_incremental`:
  ```python
  if end_date is None:
      end_date = datetime.now(timezone.utc)
  ```
  Nếu `start_date` là một datetime naive, vòng lặp `while current_start < end_date` sẽ ném ngoại lệ `TypeError`.

### 1.4. Khảo Sát Định Nghĩa Model & Luồng Phát Hành JWT
- **Model `User`** (`backend/app/models/base.py:58` & `backend/app/models/user.py:24`):
  Cột `tokens_valid_after` được khai báo bằng `DateTime(timezone=True)`.
- **Cấp phát JWT** (`backend/app/core/security.py:48-76`):
  `create_access_token` gán `iat: now_utc` (với `now_utc = datetime.now(timezone.utc)`). Thư viện `PyJWT` mã hóa claim `iat` thành số nguyên epoch timestamp (giây). Khi giải mã trong `decode_access_token`, `iat` trả về kiểu `int`.
- **Thiết lập `tokens_valid_after`** (`backend/app/api/auth.py`):
  - `POST /api/v1/auth/logout` (dòng 288): `current_user.tokens_valid_after = datetime.now(timezone.utc)`
  - `PATCH /api/v1/auth/users/{user_id}/status` (dòng 493): `user.tokens_valid_after = datetime.now(timezone.utc)`
- **Bộ kiểm thử đối kháng** (`tests/test_m1_adversarial_challenge.py:421-457`):
  Hàm `test_bug_offset_naive_datetime_comparison_in_tokens_valid_after` được Challenger 1 viết để khẳng định sự tồn tại của lỗi thông qua `with pytest.raises(TypeError)`.

---

## 2. Logic Chain (Chuỗi Lập Luận Suy Diễn Kỹ Thuật)

1. **Từ Quan sát 1.1 & 1.4**:
   - Khi người dùng đăng xuất ở một thiết bị hoặc quản trị viên cập nhật trạng thái tài khoản, `user.tokens_valid_after` được gán giá trị UTC và lưu vào database.
   - Khi token cũ từ một thiết bị khác (chưa nằm trong bảng `RevokedToken`) gửi request tới API, hệ thống chạy qua dependency `get_current_active_user`.
   - SQLite deserialize cột `tokens_valid_after` thành naive datetime (`tzinfo=None`).
   - `deps.py:125` khôi phục `token_issued_at` từ timestamp `iat` với `tz=timezone.utc` (`tzinfo=datetime.timezone.utc`).
   - Toán tử so sánh trực tiếp `<` ở `deps.py:131` ném `TypeError`, dẫn đến sập request (500) thay vì thu hồi phiên (401).

2. **Từ Quan sát 1.2 & 1.3**:
   - Vấn đề không chỉ giới hạn ở `deps.py:131` mà còn ảnh hưởng đến bất kỳ vị trí nào so sánh datetime tải từ SQLite với `datetime.now(timezone.utc)`.
   - Đặc biệt, `backend/app/core/scheduler.py:156` (`sched.next_run_at <= now`) sẽ làm gián đoạn tiến trình SchedulerEngine khi vận hành trên cơ sở dữ liệu SQLite trong môi trường local development hoặc testing.

3. **Từ Đo kiểm giải pháp TypeDecorator (Proof of Concept)**:
   - Thử nghiệm trên SQLite in-memory xác nhận rằng một `TypeDecorator` kế thừa `DateTime(timezone=True)` có thể chặn `process_result_value` và tự động gắn `tzinfo=timezone.utc` cho bất kỳ naive datetime nào đọc từ SQLite.
   - Khi kết hợp với cơ chế chuẩn hóa phòng thủ chiều sâu (Defense-in-depth) tại tầng ứng dụng (`deps.py` và `scheduler.py`), hệ thống được bảo vệ 100% không thể phát sinh lỗi `TypeError` bất kể driver cơ sở dữ liệu là SQLite hay PostgreSQL.

---

## 3. Caveats (Ranh Giới, Giả Định & Lưu Ý Kỹ Thuật)

1. **Sự khác biệt giữa SQLite và PostgreSQL**:
   - Trên PostgreSQL (chuẩn production), kiểu `DateTime(timezone=True)` được ánh xạ thành `TIMESTAMPTZ` và driver `asyncpg` trả về timezone-aware datetime theo mặc định. Lỗi này bộc lộ chủ yếu trên SQLite (môi trường local dev và CI test suite), nhưng việc chuẩn hóa timezone ở tầng ứng dụng và model là bắt buộc để đảm bảo tính nhất quán đa nền tảng (Dual-Database Parity).
2. **Cập nhật Test Case Đối Kháng**:
   - Khi lỗi được khắc phục, hàm `test_bug_offset_naive_datetime_comparison_in_tokens_valid_after` trong `tests/test_m1_adversarial_challenge.py` (vốn đang kỳ vọng `pytest.raises(TypeError)`) sẽ fail nếu không được cập nhật. Test case này cần được chuyển thành assertion kiểm tra kết quả đúng đắn: HTTP 401 Unauthorized với thông báo `"Session expired/revoked"`.

---

## 4. Conclusion & Concrete Drop-in Fix Strategy (Mưu Lược & Bản Vá Chi Tiết Cho Worker)

Áp dụng chiến lược phòng thủ 2 tầng (Two-Tier Defense Strategy):
1. **Tầng 1 (Application Layer - Fail-Safe Normalization)**: Chuẩn hóa timezone ngay trước toán tử so sánh trong `deps.py` và `scheduler.py`.
2. **Tầng 2 (Model Layer - Universal UTCDateTime)**: Bổ sung `UTCDateTime` TypeDecorator trong `backend/app/models/base.py` tương tự như pattern `GUID` đã có.

### Chi Tiết Mã Nguồn Cần Thay Đổi (Drop-in Code Snippets)

#### Vị trí 1: `backend/app/api/deps.py` (Dòng 119–137)
Thay thế đoạn mã so sánh bằng đoạn mã chuẩn hóa an toàn:
```python
    # Enforce session expiry via tokens_valid_after timestamp (F03)
    if token and hasattr(user, "tokens_valid_after") and user.tokens_valid_after:
        payload = decode_access_token(token)
        if payload:
            iat = payload.get("iat")
            if iat:
                if isinstance(iat, (int, float)):
                    token_issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
                elif isinstance(iat, datetime):
                    token_issued_at = iat.replace(tzinfo=timezone.utc) if iat.tzinfo is None else iat.astimezone(timezone.utc)
                else:
                    token_issued_at = None

                tokens_valid_after = user.tokens_valid_after
                if tokens_valid_after is not None:
                    if tokens_valid_after.tzinfo is None:
                        tokens_valid_after = tokens_valid_after.replace(tzinfo=timezone.utc)
                    else:
                        tokens_valid_after = tokens_valid_after.astimezone(timezone.utc)

                if token_issued_at and tokens_valid_after and token_issued_at < tokens_valid_after:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Session expired/revoked",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
```

#### Vị trí 2: `backend/app/models/base.py`
1. Khai báo `UTCDateTime` TypeDecorator (ngay dưới lớp `GUID` ở dòng 29):
```python
class UTCDateTime(TypeDecorator):
    """Platform-independent UTC DateTime type.
    Ensures datetime objects always retain tzinfo=timezone.utc across SQLite and PostgreSQL.
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value
```
2. Cập nhật dòng 58 trong class `User`:
```python
    tokens_valid_after: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
```

#### Vị trí 3: `backend/app/models/user.py`
Cập nhật dòng 23–25:
```python
from backend.app.models.base import Base, GUID, TimestampMixin, User, UTCDateTime

# Dynamically attach tokens_valid_after to User if not already mapped
if not hasattr(User, "tokens_valid_after"):
    User.tokens_valid_after = mapped_column(UTCDateTime, nullable=True)
```

#### Vị trí 4: `backend/app/core/scheduler.py` (Dòng 155–158)
Chuẩn hóa timezone cho `sched.next_run_at`:
```python
                next_run = sched.next_run_at
                if next_run is not None:
                    if next_run.tzinfo is None:
                        next_run = next_run.replace(tzinfo=timezone.utc)
                    else:
                        next_run = next_run.astimezone(timezone.utc)

                    if next_run <= now:
                        # Time to trigger
```

#### Vị trí 5: `backend/app/intel/nvd.py` (Dòng 244–256)
Chuẩn hóa timezone trong `chunk_date_range`:
```python
    @staticmethod
    def chunk_date_range(start_date: datetime, end_date: datetime, max_days: int = 90) -> List[tuple[datetime, datetime]]:
        """Split a wide date range into windows of at most `max_days` to prevent
        NVD 400 Bad Request (>120 days interval rejected).
        """
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        else:
            start_date = start_date.astimezone(timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        else:
            end_date = end_date.astimezone(timezone.utc)

        chunks: List[tuple[datetime, datetime]] = []
        current_start = start_date

        while current_start < end_date:
            current_end = min(current_start + timedelta(days=max_days), end_date)
            chunks.append((current_start, current_end))
            current_start = current_end
        return chunks
```

#### Vị trí 6: `tests/test_m1_adversarial_challenge.py` (Dòng 451–458)
Cập nhật assertion để xác nhận lỗi đã được khắc phục:
```python
        # Calling get_current_active_user now gracefully handles offset-naive DB datetime
        # and rejects the expired token with HTTP 401 instead of crashing with TypeError
        res = await client.get("/api/v1/auth/me", headers=headers)
        assert res.status_code == 401
        assert "Session expired/revoked" in res.json()["detail"]
```

---

## 5. Verification Method (Phương Pháp Kiểm Định Độc Lập)

Sau khi worker áp dụng bản vá, thực thi các lệnh kiểm định sau từ thư mục gốc của repository:

1. **Kiểm tra trực tiếp kiểm thử đối kháng**:
   ```powershell
   python -m pytest tests/test_m1_adversarial_challenge.py -k "test_bug_offset_naive_datetime_comparison_in_tokens_valid_after" -v
   ```
   *Kết quả kỳ vọng*: `1 passed in <1s`, mã trả về HTTP 401 Unauthorized và không có ngoại lệ `TypeError`.

2. **Chạy toàn bộ 41 kịch bản kiểm thử đối kháng**:
   ```powershell
   python -m pytest tests/test_m1_adversarial_challenge.py -v
   ```
   *Kết quả kỳ vọng*: `41 passed in ~3.5s`, mã thoát 0.

3. **Chạy toàn bộ test suites của Milestone 1**:
   ```powershell
   python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_enhancement_suite.py tests/test_m1_adversarial_challenge.py -v
   ```
   *Kết quả kỳ vọng*: `80 passed in ~18s`, mã thoát 0 (All Green).
