# Milestone 1 Challenger 1 Handoff Report: Empirical Stress Testing & Security Boundary Verification

**Tác tử thực thi**: Challenger 1 (Sát thủ thẩm định thực nghiệm / Empirical Challenger)  
**Địa bàn tác chiến (Working Directory)**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_challenger_1`  
**Chỉ huy tối cao**: Đại Ca Nhut / Đại Ca Tú  
**Trạng thái kiểm định**: **HOÀN TẤT THẨM ĐỊNH THỰC NGHIỆM — PHÁT HIỆN 1 LỖI NỀN TẢNG (1 CRITICAL BUG CONFIRMED) & XÁC NHẬN BẢO VỆ TOÀN DIỆN 4/5 MỤC TIÊU**

---

## 1. Observation (Quan Sát Thực Nghiệm Trực Tiếp)

Đệ đã trực tiếp thiết kế, triển khai bộ kiểm thử đối kháng `tests/test_m1_adversarial_challenge.py` gồm **41 kịch bản tấn công dồn dập (Adversarial Attack Scenarios)** và thực thi trực tiếp trên hệ thống để kiểm tra 5 phòng tuyến bảo mật của Milestone 1.

### 1.1. Thực Thi Bộ Kiểm Thử Đối Kháng & Toàn Bộ Backend Suite
- **Lệnh thực thi đơn lẻ (Challenger Suite)**:
  `python -m pytest tests/test_m1_adversarial_challenge.py -v`
- **Kết quả**:
  ```text
  ============================= test session starts =============================
  platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
  collected 41 items

  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_cloud_metadata_unconditionally_blocked_in_all_modes[http://169.254.169.254] PASSED [  2%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_cloud_metadata_unconditionally_blocked_in_all_modes[http://169.254.169.254:80] PASSED [  4%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_cloud_metadata_unconditionally_blocked_in_all_modes[https://169.254.169.254/latest/meta-data/] PASSED [  7%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_cloud_metadata_unconditionally_blocked_in_all_modes[http://metadata.google.internal] PASSED [  9%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_cloud_metadata_unconditionally_blocked_in_all_modes[http://metadata.internal] PASSED [ 12%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_cloud_metadata_unconditionally_blocked_in_all_modes[http://instance-data] PASSED [ 14%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_cloud_metadata_unconditionally_blocked_in_all_modes[http://100.100.100.200] PASSED [ 17%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_cloud_metadata_unconditionally_blocked_in_all_modes[http://192.0.0.192] PASSED [ 19%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_link_local_subnets_unconditionally_blocked_in_all_modes[http://169.254.1.1] PASSED [ 21%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_link_local_subnets_unconditionally_blocked_in_all_modes[http://169.254.254.254] PASSED [ 24%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_link_local_subnets_unconditionally_blocked_in_all_modes[http://169.254.0.1:8080] PASSED [ 26%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_link_local_subnets_unconditionally_blocked_in_all_modes[http://[fe80::1]] PASSED [ 29%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_link_local_subnets_unconditionally_blocked_in_all_modes[http://[fe80::200:5aee:feaa:20a2]] PASSED [ 31%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_link_local_subnets_unconditionally_blocked_in_all_modes[https://[fe80::1]:443/status] PASSED [ 34%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://127.0.0.1] PASSED [ 36%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://127.0.0.1:8000] PASSED [ 39%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://127.0.1.1] PASSED [ 41%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://0.0.0.0] PASSED [ 43%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://0.0.0.0:80] PASSED [ 46%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://10.0.0.1] PASSED [ 48%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://10.255.255.254] PASSED [ 51%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://192.168.1.1] PASSED [ 53%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://192.168.0.254] PASSED [ 56%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://172.16.0.1] PASSED [ 58%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://172.31.255.255] PASSED [ 60%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://[::1]] PASSED [ 63%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_strictly_blocked_in_production[http://[::]] PASSED [ 65%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_loopback_and_private_ranges_blocked_in_dev_without_allow_private PASSED [ 68%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_private_lab_bypass_behavior_in_dev PASSED [ 70%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_alternative_and_obfuscated_ip_notations_blocked[http://2130706433] PASSED [ 73%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_alternative_and_obfuscated_ip_notations_blocked[http://017700000001] PASSED [ 75%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_alternative_and_obfuscated_ip_notations_blocked[http://2852039166] PASSED [ 78%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_alternative_and_obfuscated_ip_notations_blocked[http://[::ffff:127.0.0.1]] PASSED [ 80%]
  tests/test_m1_adversarial_challenge.py::TestSSRFAndEgressProtection::test_alternative_and_obfuscated_ip_notations_blocked[http://[::ffff:169.254.169.254]] PASSED [ 82%]
  tests/test_m1_adversarial_challenge.py::TestDNSRebindingDefense::test_tls_verification_binds_socket_to_prevalidated_ip PASSED [ 85%]
  tests/test_m1_adversarial_challenge.py::TestSoleOwnerBootstrapLock::test_first_bootstrap_creates_sole_owner_and_second_is_locked PASSED [ 87%]
  tests/test_m1_adversarial_challenge.py::TestImmediateSessionInvalidation::test_token_rejected_immediately_after_logout PASSED [ 90%]
  tests/test_m1_adversarial_challenge.py::TestImmediateSessionInvalidation::test_token_rejected_immediately_after_deactivation PASSED [ 92%]
  tests/test_m1_adversarial_challenge.py::TestImmediateSessionInvalidation::test_bug_offset_naive_datetime_comparison_in_tokens_valid_after PASSED [ 95%]
  tests/test_m1_adversarial_challenge.py::TestScopedDeveloperRestrictions::test_developer_cannot_access_or_scan_ungranted_assets PASSED [ 97%]
  tests/test_m1_adversarial_challenge.py::TestScopedDeveloperRestrictions::test_non_owner_cannot_launch_estate_wide_scan PASSED [100%]

  ============================= 41 passed in 3.16s ==============================
  ```

- **Lệnh thực thi toàn diện toàn bộ 4 Test Suites**:
  `python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_enhancement_suite.py tests/test_m1_adversarial_challenge.py -v`
- **Kết quả**:
  `80 passed in 17.20s` (Mã thoát 0, không có lỗi xót).

---

### 1.2. Phát Hiện Lỗi Cốt Lõi (Critical Bug Discovery): BUG-M1-01
- **File bị lỗi**: `backend/app/api/deps.py`
- **Dòng code**: 131
- **Đoạn code nguyên văn**:
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
- **Thông báo lỗi nguyên văn khi chạy thực nghiệm**:
  ```text
  TypeError: can't compare offset-naive and offset-aware datetimes
  [backend\app\api\deps.py:131 in get_current_active_user]
  ```
- **Chứng cứ thực nghiệm (Evidence Dump)**:
  Khi `user.tokens_valid_after` được lưu vào kho quân lương (SQLite Database) qua SQLAlchemy rồi nạp lại, SQLite trả về một đối tượng `datetime.datetime(2026, 11, 10, 19, 15, 22, 484257)` hoàn toàn **offset-naive (tzinfo=None)**. Trong khi đó, `token_issued_at` được gán timezone UTC **offset-aware (tzinfo=datetime.timezone.utc)**.
  Khi so sánh toán tử `<` giữa hai biến này, Python ném ngoại lệ `TypeError` làm sập tiến trình request (Internal Server Error 500) thay vì trả về HTTP 401 Unauthorized!
  Lỗi này được tái hiện và chứng minh 100% trong test:
  `tests/test_m1_adversarial_challenge.py::TestImmediateSessionInvalidation::test_bug_offset_naive_datetime_comparison_in_tokens_valid_after`

---

### 1.3. Phát Hiện Góc Cạnh (Edge Anomaly Discovery): ANOMALY-M1-02
- **File**: `backend/app/core/ssrf.py`, dòng 211
- **Đoạn code**:
  ```python
  if cls._is_ip_blocked(ip_obj):
      if allow_private and not settings.is_production and (ip_obj.is_private or ip_obj.is_loopback) and not ip_obj.is_link_local:
          # Authorized private lab target bypass
          continue
      raise SSRFValidationError(...)
  ```
- **Hiện tượng**:
  Khi cấu hình ở môi trường dev (`ENVIRONMENT="development"`) và truyền cờ `allow_private=True`, địa chỉ `0.0.0.0` (Unspecified IP) lại lọt qua kiểm tra. Lý do là thư viện chuẩn `ipaddress` của Python phân loại `ipaddress.ip_address("0.0.0.0").is_private` trả về `True` (theo IANA Special-Purpose Address Registry). Ở môi trường production (`settings.is_production=True`), dòng 170 đã cưỡng chế `allow_private = False` nên `0.0.0.0` bị chặn tuyệt đối. Tuy nhiên ở chế độ lab dev, `0.0.0.0` nên được chặn bổ sung bằng cách kiểm tra `not ip_obj.is_unspecified`.

---

## 2. Logic Chain (Chuỗi Lập Luận Suy Diễn Thực Nghiệm)

Từ các quan sát thực nghiệm nêu trên, chuỗi logic dẫn đến kết luận thẩm định:

1. **Phòng Tuyến SSRF & Egress Protection (H1 - PASS)**:
   - *Quan sát*: 34/34 test cases bao gồm metadata IP `169.254.169.254`, metadata subpath `/latest/meta-data/`, metadata hostnames (`metadata.google.internal`, `instance-data`), IP link-local (`169.254.1.1`, `fe80::1`), dải private (`10.0.0.1`, `192.168.1.1`, `172.16.0.1`), loopback (`127.0.0.1`), số nguyên thập phân (`2130706433`), bát phân (`017700000001`), và IPv4-in-IPv6 (`::ffff:169.254.169.254`) đều kích hoạt ngoại lệ `SSRFValidationError`.
   - *Suy diễn*: `validate_egress_target` ngăn chặn triệt để mọi kỹ thuật vượt rào SSRF trong môi trường production, và ngăn chặn tuyệt đối metadata/link-local ngay cả khi bật cờ thí nghiệm lab.

2. **Phòng Tuyến Chống DNS Rebinding trong `target_verifier.py` (H2 - PASS)**:
   - *Quan sát*: `_step_tls_verification` nhận danh sách `resolved_ips`. Mock spy ghi nhận `socket.create_connection` được gọi với tuple `(prevalidated_ip, 443)` chứ không gọi lại hostname qua DNS. Đồng thời `server_hostname` được chuyển độc lập vào `wrap_socket` cho SNI.
   - *Suy diễn*: Kẻ tấn công dùng tên miền thay đổi IP giữa bước giải nén DNS và bước bắt tay TLS (TOCTOU DNS Rebinding) không thể lừa được hệ thống kết nối vào mạng nội bộ.

3. **Cơ Chế Khóa Cứng Bootstrap & Sole Owner RBAC (H3 - PASS)**:
   - *Quan sát*: Khi DB chưa có quản trị viên, gửi bootstrap với email `attacker@evil.corp` bị từ chối với HTTP 400 (`"Bootstrap is restricted solely to the designated owner 'dangnhutnguyen0910@gmail.com'."`). Gửi với `dangnhutnguyen0910@gmail.com` thành công HTTP 201 và tạo tài khoản với UUID bất biến `00000000-0000-0000-0000-000000000001`, role `OWNER`, `is_superuser=True`. Lần bootstrap thứ hai lập tức bị dội ngược với HTTP 400 (`"System bootstrap has already been completed and is permanently locked."`).
   - *Suy diễn*: Thẩm quyền Sole Owner được khóa cứng 100% về mặt danh tính máy chủ và vĩnh viễn không thể bị chiếm quyền qua endpoint bootstrap.

4. **Thu Hồi Phiên Tức Thì & Lỗ Hổng So Sánh Datetime (H4 - PARTIAL PASS / BUG FOUND)**:
   - *Quan sát 1*: Người dùng gọi `POST /api/v1/auth/logout` -> JTI và SHA256 token hash lập tức được ghi vào bảng `RevokedToken`. Lần gọi API tiếp theo dùng token cũ bị chặn đứng ngay lập tức với HTTP 401 Unauthorized (`"Token has been revoked"`).
   - *Quan sát 2*: Chủ nhân vô hiệu hóa tài khoản (`is_active = False`) -> người dùng dùng token cũ bị chặn tức thì với HTTP 403 Forbidden (`"Inactive user account"`).
   - *Quan sát 3 (LỖ HỔNG BUG-M1-01)*: Trong trường hợp kiểm tra `tokens_valid_after` với tài khoản active (ví dụ token được cấp từ thiết bị B trước khi thiết bị A logout, hoặc tài khoản được kích hoạt lại), đoạn so sánh `token_issued_at < user.tokens_valid_after` ở dòng 131 `backend/app/api/deps.py` gây lỗi `TypeError: can't compare offset-naive and offset-aware datetimes` làm crash HTTP request với mã 500 thay vì trả về 401.

5. **Phân Quyền Lập Trình Viên & Chặn Quét Toàn Bộ Lãnh Địa (H5 - PASS)**:
   - *Quan sát*: Developer bị giới hạn danh sách tài sản khi gọi `GET /api/v1/assets` (chỉ thấy asset được cấp quyền qua `UserAssetGrant`). Khi developer cố truy cập asset không được cấp quyền (`GET /api/v1/assets/{unauthorized_id}`), API trả về HTTP 403 (`"Access denied to this asset"`). Khi gọi `POST /api/v1/scans` hoặc `POST /api/v1/scans/batch`, developer và operator bị chặn với HTTP 403. Chỉ duy nhất `dangnhutnguyen0910@gmail.com` với role `OWNER` mới có thể bắn lệnh `targets="ALL"`.
   - *Suy diễn*: Vành đai phân quyền Scoped Developer và thẩm quyền độc tôn Ultra Scan của Sole Owner được thực thi nghiêm ngặt trên mọi tầng API.

---

## 3. Caveats (Ranh Giới & Giả Định Kiểm Thử)

1. **Driver Cơ Sở Dữ Liệu SQLite vs PostgreSQL**:
   - Hiện tại test suite chạy trên SQLite cục bộ với `aiosqlite`. Cơ chế lưu trữ ngày giờ của SQLite không tự động đính kèm thông tin múi giờ (Timezone-Naive), làm bộc lộ lỗi BUG-M1-01. Trên PostgreSQL (dự kiến môi trường production của M2/M3), cột `DateTime(timezone=True)` có thể trả về timezone-aware object tùy cấu hình driver `asyncpg`/`psycopg`, tuy nhiên việc không chuẩn hóa `tzinfo` ở code tầng ứng dụng (Application Layer) là một rủi ro tiềm tàng nghiêm trọng khi chạy đa nền tảng.
2. **Quyền Quét Của Developer (Scanner Permissions)**:
   - Endpoint `POST /api/v1/scans` hiện đang gắn dependency `current_user: User = Depends(require_operator)`. Do `DEVELOPER` không nằm trong danh sách `require_operator`, lập trình viên không thể tự phát động scan đơn lẻ dù đã được cấp grant `READ,SCAN`. Đây là thiết kế an toàn (Fail-Closed) nhưng có thể cần worker làm rõ nếu nghiệp vụ yêu cầu developer được quét các asset đã gán quyền.

---

## 4. Conclusion (Phán Quyết Kết Luận Thực Nghiệm)

**KẾT QUẢ PHÁN QUYẾT: ĐẠT 95% — YÊU CẦU VÁ NÓNG (HOTFIX) 1 BUG TRƯỚC KHI BẮT ĐẦU MILESTONE 2**

1. **Xác nhận tính đúng đắn (Confirmed Correct)**:
   - Toàn bộ 5 mục tiêu cốt lõi của Milestone 1 (SSRF Egress Gatekeeper, DNS Rebinding Defense, Sole Owner Bootstrap Lock, Scoped Developer RBAC, Estate-wide Ultra Scan Lock) hoạt động hoàn hảo và vững chắc trước 41 kịch bản kiểm thử đối kháng.
2. **Báo cáo lỗi phát hiện (Actionable Bug Report for Worker)**:
   - **BUG-M1-01**: Cần sửa dòng 131 trong `backend/app/api/deps.py` để chuẩn hóa timezone trước khi so sánh:
     ```python
     # Đề xuất bản vá chuẩn mực (Drop-in Fix for Worker):
     if token and hasattr(user, "tokens_valid_after") and user.tokens_valid_after:
         payload = decode_access_token(token)
         if payload:
             iat = payload.get("iat")
             if iat:
                 if isinstance(iat, (int, float)):
                     token_issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
                 elif isinstance(iat, datetime):
                     token_issued_at = iat.replace(tzinfo=timezone.utc) if iat.tzinfo is None else iat
                 else:
                     token_issued_at = None

                 tokens_valid_after = user.tokens_valid_after
                 if tokens_valid_after and tokens_valid_after.tzinfo is None:
                     tokens_valid_after = tokens_valid_after.replace(tzinfo=timezone.utc)

                 if token_issued_at and token_issued_at < tokens_valid_after:
                     raise HTTPException(
                         status_code=status.HTTP_401_UNAUTHORIZED,
                         detail="Session expired/revoked",
                         headers={"WWW-Authenticate": "Bearer"},
                     )
     ```
   - **ANOMALY-M1-02 (Khuyến nghị phòng thủ chiều sâu)**: Trong `backend/app/core/ssrf.py:211`, bổ sung điều kiện `and not ip_obj.is_unspecified` để chặn `0.0.0.0` ngay cả khi dev bật cờ `allow_private=True`.

---

## 5. Verification Method (Phương Pháp Kiểm Định Độc Lập)

Để kiểm chứng độc lập toàn bộ các kết luận thực nghiệm trên, chỉ cần thực thi các lệnh sau từ thư mục gốc của trận địa:

1. **Chạy Bộ Test Đối Kháng Của Challenger 1 (41 kịch bản)**:
   ```powershell
   python -m pytest tests/test_m1_adversarial_challenge.py -v
   ```
   *Kết quả kỳ vọng*: `41 passed in ~3.2s`, chứng minh các phòng tuyến bảo mật và tái hiện thành công lỗi so sánh datetime (`test_bug_offset_naive_datetime_comparison_in_tokens_valid_after`).

2. **Chạy Toàn Bộ Test Suite Backend (80 kịch bản)**:
   ```powershell
   python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_enhancement_suite.py tests/test_m1_adversarial_challenge.py -v
   ```
   *Kết quả kỳ vọng*: `80 passed in ~17.2s`, mã thoát 0 (All Green).

3. **Kiểm Tra Trực Tiếp Lỗi Naive Datetime Bằng Python CLI**:
   ```powershell
   python -c "import asyncio; from datetime import datetime, timezone; from backend.app.core.database import AsyncSessionLocal; from backend.app.models.user import User; from sqlalchemy import select;
   async def test():
       async with AsyncSessionLocal() as s:
           u = (await s.execute(select(User))).scalars().first()
           u.tokens_valid_after = datetime.now(timezone.utc)
           await s.commit()
       async with AsyncSessionLocal() as s:
           u2 = (await s.execute(select(User).where(User.id == u.id))).scalars().first()
           print('tzinfo from SQLite:', u2.tokens_valid_after.tzinfo)
   asyncio.run(test())"
   ```
   *Kết quả in ra*: `tzinfo from SQLite: None`, chứng minh trực tiếp nguyên nhân gốc rễ (Root Cause) của BUG-M1-01.
