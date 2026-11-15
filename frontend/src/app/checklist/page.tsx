'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import {
  ShieldCheck,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  MinusCircle,
  Ban,
  Clock,
  AlertOctagon,
  RefreshCw,
  ExternalLink,
  ChevronRight,
  Info,
  Server,
  Layers,
  Cpu,
  FileCode,
  Lock,
  Boxes,
  Globe,
  Sliders,
  Check,
  X,
  Play,
  RotateCcw,
} from 'lucide-react';
import { useI18n } from '@/lib/i18n';
import { api } from '@/lib/api';
import {
  ChecklistCategory,
  ChecklistResultState,
  AutomationType,
  ChecklistDefinition,
  ChecklistResult,
  ChecklistAssessmentRun,
  SeverityLevel,
  Asset,
} from '@/lib/types';
import { useToast } from '@/components/ui/toast';

// ============================================================================
// Authoritative Empire Pentest Checklist Definitions (All 39 Checks)
// ============================================================================

const EMPIRE_CHECKLIST_CATALOG: ChecklistDefinition[] = [
  // --- Category 1: WEB (10 Checks) ---
  {
    check_id: 'WEB-001',
    category: 'WEB',
    title_vi: 'Cấu hình TLS & Mã hóa vận chuyển',
    title_en: 'TLS Configuration & Transport Encryption',
    description_vi: 'Đánh giá phiên bản TLS (1.2, 1.3), kiểm tra chứng chỉ số X.509, danh sách cipher suite an toàn và kích hoạt HSTS.',
    description_en: 'Evaluates TLS protocol versions (1.2, 1.3), X.509 certificate trust chains, secure cipher suites, and HSTS enforcement.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'ZAP / TLS_HEALTH',
    remediation_guidance_vi: 'Vô hiệu hóa TLS 1.0/1.1 và các cipher yếu; bật HSTS với max-age tối thiểu 31536000 giây.',
    remediation_guidance_en: 'Disable TLS 1.0/1.1 and weak ciphers; enable HSTS with max-age >= 31536000 seconds.',
  },
  {
    check_id: 'WEB-002',
    category: 'WEB',
    title_vi: 'Tiêu đề bảo mật HTTP & CSP',
    title_en: 'HTTP Security Headers & CSP',
    description_vi: 'Kiểm tra sự hiện diện và tính chặt chẽ của Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.',
    description_en: 'Audits Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, and Referrer-Policy headers.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Cấu hình CSP chặt chẽ chặn unsafe-inline/unsafe-eval; thiết lập X-Frame-Options: DENY hoặc SAMEORIGIN.',
    remediation_guidance_en: 'Enforce strict CSP without unsafe-inline/eval; set X-Frame-Options: DENY or SAMEORIGIN.',
  },
  {
    check_id: 'WEB-003',
    category: 'WEB',
    title_vi: 'Cross-Site Scripting (XSS Phản xạ & Lưu trữ)',
    title_en: 'Reflected & Stored Cross-Site Scripting',
    description_vi: 'Thăm dò và phát hiện lỗ hổng XSS trong các tham số URL, form tìm kiếm, cookie và các trường nhập liệu tương tác.',
    description_en: 'Probes for reflected and stored XSS vectors across URL parameters, search forms, and input fields.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'ZAP',
    remediation_guidance_vi: 'Mã hóa ngữ cảnh đầu ra (Context-aware output encoding) và sử dụng framework tự động escape dữ liệu.',
    remediation_guidance_en: 'Apply context-aware output encoding and framework-native sanitization on all untrusted inputs.',
  },
  {
    check_id: 'WEB-004',
    category: 'WEB',
    title_vi: 'Cross-Site Request Forgery (CSRF)',
    title_en: 'Cross-Site Request Forgery & Origin Validation',
    description_vi: 'Xác thực token chống CSRF trên các yêu cầu POST/PUT/DELETE thay đổi trạng thái và kiểm tra thuộc tính SameSite cookie.',
    description_en: 'Validates anti-CSRF token presence on state-changing requests and audits SameSite cookie flags.',
    severity: 'MEDIUM',
    automation_type: 'HYBRID',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Triển khai token CSRF đồng bộ hoặc SameSite=Strict/Lax cho tất cả session cookie.',
    remediation_guidance_en: 'Deploy synchronized anti-CSRF tokens and set SameSite=Strict or Lax for session cookies.',
  },
  {
    check_id: 'WEB-005',
    category: 'WEB',
    title_vi: 'SQL Injection & Rò rỉ ORM',
    title_en: 'SQL Injection & ORM Data Leakage',
    description_vi: 'Kiểm thử các kỹ thuật chèn SQL (In-band, Error-based, Blind, Time-based) trên các endpoint truy vấn cơ sở dữ liệu.',
    description_en: 'Tests in-band, error-based, blind, and time-based SQL injection across database query endpoints.',
    severity: 'CRITICAL',
    automation_type: 'AUTOMATED',
    target_engine: 'ZAP',
    remediation_guidance_vi: 'Sử dụng truy vấn có tham số hóa (Parameterized queries / Prepared statements) và ORM an toàn.',
    remediation_guidance_en: 'Enforce parameterized queries and prepared statements exclusively across all data layers.',
  },
  {
    check_id: 'WEB-006',
    category: 'WEB',
    title_vi: 'Server-Side Request Forgery (SSRF Web)',
    title_en: 'Server-Side Request Forgery via Web Inputs',
    description_vi: 'Phát hiện khả năng thao túng server gửi yêu cầu HTTP trái phép tới mạng nội bộ hoặc cloud metadata (169.254.169.254).',
    description_en: 'Detects unauthorized server-side outbound HTTP requests targeting loopback or internal subnets.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Áp dụng whitelist URL nghiêm ngặt, chặn hoàn toàn RFC1918 và địa chỉ link-local/cloud metadata.',
    remediation_guidance_en: 'Implement strict URL domain whitelisting and block private IP resolution at network level.',
  },
  {
    check_id: 'WEB-007',
    category: 'WEB',
    title_vi: 'Chuyển hướng mở & Lừa đảo URL',
    title_en: 'Open Redirection & Phishing Vectors',
    description_vi: 'Kiểm tra các tham số redirect, next, return_to cho phép chuyển hướng người dùng tới domain độc hại bên ngoài.',
    description_en: 'Audits redirect/return URL parameters for unvalidated external redirects facilitating phishing.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Chỉ cho phép chuyển hướng tới đường dẫn tương đối (relative paths) hoặc domain nằm trong whitelist.',
    remediation_guidance_en: 'Restrict redirects to relative URLs or verified in-scope domain whitelists.',
  },
  {
    check_id: 'WEB-008',
    category: 'WEB',
    title_vi: 'Rò rỉ dấu vết lỗi & Mã nguồn',
    title_en: 'Error Leakage & Diagnostic Stack Traces',
    description_vi: 'Phát hiện thông báo lỗi chi tiết, stack trace, đường dẫn tệp máy chủ và biến môi trường khi gửi payload dị dạng.',
    description_en: 'Detects detailed server stack traces, filesystem paths, and debug variables on malformed requests.',
    severity: 'LOW',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Tắt chế độ debug trong môi trường sản xuất; trả về trang lỗi tiêu chuẩn chung (generic error pages).',
    remediation_guidance_en: 'Disable debug mode in production; return generic user-friendly error handlers.',
  },
  {
    check_id: 'WEB-009',
    category: 'WEB',
    title_vi: 'Sai cấu hình CORS',
    title_en: 'Cross-Origin Resource Sharing (CORS) Misconfiguration',
    description_vi: 'Kiểm tra Access-Control-Allow-Origin: * kết hợp với Access-Control-Allow-Credentials: true hoặc tin cậy Origin tùy ý.',
    description_en: 'Audits wildcard Access-Control-Allow-Origin headers with credentials or reflection of arbitrary origins.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Chỉ định danh sách origin tin cậy rõ ràng; tuyệt đối không phản chiếu tiêu đề Origin tự động.',
    remediation_guidance_en: 'Explicitly declare trusted origins and never dynamically reflect untrusted Origin headers.',
  },
  {
    check_id: 'WEB-010',
    category: 'WEB',
    title_vi: 'Duyệt thư mục & Đường dẫn nhạy cảm',
    title_en: 'Directory Indexing & Sensitive Static Paths',
    description_vi: 'Kiểm tra tính năng directory listing và các đường dẫn tĩnh nhạy cảm (.git, .env, server-status, backup).',
    description_en: 'Checks for web server directory listing and exposed administrative or sensitive static paths.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Tắt Options Indexes trong cấu hình web server (Nginx/Apache) và chặn truy cập tệp ẩn.',
    remediation_guidance_en: 'Disable directory indexing in web server configuration and deny access to dotfiles.',
  },

  // --- Category 2: API (10 Checks) ---
  {
    check_id: 'API-001',
    category: 'API',
    title_vi: 'BOLA / IDOR Hồ sơ Học viên',
    title_en: 'Broken Object Level Authorization (BOLA/IDOR)',
    description_vi: 'Kiểm thử truy cập chéo dữ liệu học viên (học bạ, điểm số, thông tin cá nhân) giữa các tài khoản thử nghiệm độc lập.',
    description_en: 'Tests cross-tenant object access to student records using synthetic accounts without authorization.',
    severity: 'CRITICAL',
    automation_type: 'AUTOMATED',
    target_engine: 'SYNTHETIC_HARNESS',
    remediation_guidance_vi: 'Xác thực quyền sở hữu tài nguyên (Resource-level access control) dựa trên token phiên tại tầng controller.',
    remediation_guidance_en: 'Validate object ownership against the authenticated session context on every endpoint.',
  },
  {
    check_id: 'API-002',
    category: 'API',
    title_vi: 'Xác thực API & Chữ ký JWT',
    title_en: 'Broken Authentication & JWT Validation',
    description_vi: 'Đánh giá thuật toán "none" trong JWT, secret yếu, không kiểm tra hạn dùng (exp) và giả mạo chữ ký token.',
    description_en: 'Evaluates JWT algorithm switching (alg: none), weak HMAC secrets, expiration bypass, and signature tampering.',
    severity: 'CRITICAL',
    automation_type: 'AUTOMATED',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Sử dụng thuật toán khóa bất đối xứng RS256/ES256, kiểm tra exp nghiêm ngặt và xác thực chữ ký.',
    remediation_guidance_en: 'Enforce asymmetric RS256/ES256 verification and strictly validate token expiration.',
  },
  {
    check_id: 'API-003',
    category: 'API',
    title_vi: 'Gán dữ liệu hàng loạt (Mass Assignment)',
    title_en: 'Excessive Data Exposure & Mass Assignment',
    description_vi: 'Kiểm tra khả năng sửa đổi các trường bảo vệ (is_admin, role, balance, verified) khi gửi payload JSON thừa.',
    description_en: 'Audits API endpoints for unauthorized mutation of internal fields (e.g. role, is_admin) via request bodies.',
    severity: 'HIGH',
    automation_type: 'HYBRID',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Sử dụng DTO / Pydantic schema với whitelist trường cho phép cập nhật; cấm gán trực tiếp request body vào model.',
    remediation_guidance_en: 'Use strict schema DTOs with explicit allowed-fields whitelists for request deserialization.',
  },
  {
    check_id: 'API-004',
    category: 'API',
    title_vi: 'Thiếu kiểm soát tần suất API',
    title_en: 'Lack of Resources & Rate Limiting',
    description_vi: 'Đo lường khả năng xử lý yêu cầu dồn dập, thiếu rate limit, kích thước payload không giới hạn gây cạn kiệt tài nguyên.',
    description_en: 'Measures API responsiveness under concurrent bursts and checks for missing rate limit headers.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'ZAP',
    remediation_guidance_vi: 'Cài đặt rate limiting trên API Gateway (token bucket / leaky bucket) và giới hạn kích thước body.',
    remediation_guidance_en: 'Implement token bucket rate limiting on API gateway and enforce request payload limits.',
  },
  {
    check_id: 'API-005',
    category: 'API',
    title_vi: 'BFLA Phân quyền Chức năng Admin',
    title_en: 'Broken Function Level Authorization (BFLA)',
    description_vi: 'Thực thi các lời gọi API quản trị bằng tài khoản học viên có đặc quyền thấp để phát hiện leo thang chức năng.',
    description_en: 'Executes administrative API calls using low-privileged synthetic student tokens to test authorization barriers.',
    severity: 'CRITICAL',
    automation_type: 'AUTOMATED',
    target_engine: 'SYNTHETIC_HARNESS',
    remediation_guidance_vi: 'Kiểm tra vai trò và quyền hạn (RBAC) chặt chẽ tại tất cả các router và endpoint nhạy cảm.',
    remediation_guidance_en: 'Enforce granular role-based access control (RBAC) guards on all sensitive API route handlers.',
  },
  {
    check_id: 'API-006',
    category: 'API',
    title_vi: 'SSRF trong Webhook API',
    title_en: 'Server-Side Request Forgery in API Webhooks',
    description_vi: 'Kiểm tra tính năng cấu hình webhook / callback URL cho phép trỏ tới loopback hoặc hệ thống mạng nội bộ.',
    description_en: 'Tests custom webhook and callback registration endpoints for unvalidated internal destinations.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Phân giải DNS trước khi gửi webhook, chặn IP nội bộ và sử dụng egress proxy chuyên dụng.',
    remediation_guidance_en: 'Resolve DNS pre-dispatch, block loopback/private subnets, and isolate webhook dispatchers.',
  },
  {
    check_id: 'API-007',
    category: 'API',
    title_vi: 'Sai sót cấu hình Cổng kết nối API',
    title_en: 'API Gateway Security Misconfiguration',
    description_vi: 'Kiểm tra các phương thức HTTP không cần thiết (TRACE, OPTIONS, DEBUG), tiêu đề lộ phiên bản và bypass xác thực.',
    description_en: 'Audits unnecessary HTTP verbs, version leakage headers, and authentication bypasses on gateways.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Chỉ cho phép các phương thức HTTP cần thiết (GET/POST/PUT/DELETE) và ẩn banner máy chủ.',
    remediation_guidance_en: 'Restrict allowed HTTP methods and strip informative Server headers at the gateway layer.',
  },
  {
    check_id: 'API-008',
    category: 'API',
    title_vi: 'Chống tấn công tự động trên API',
    title_en: 'Lack of Protection against Automated Threats',
    description_vi: 'Đánh giá khả năng phòng vệ trước các cuộc tấn công tự động, credential stuffing và scrap dữ liệu học viên.',
    description_en: 'Evaluates defenses against automated credential stuffing, brute force, and programmatic scraping.',
    severity: 'HIGH',
    automation_type: 'HYBRID',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Tích hợp CAPTCHA thích ứng, phân tích hành vi bất thường và chặn IP vượt ngưỡng giới hạn.',
    remediation_guidance_en: 'Deploy adaptive CAPTCHA, behavioral bot mitigation, and progressive delay throttling.',
  },
  {
    check_id: 'API-009',
    category: 'API',
    title_vi: 'Phát hiện API ẩn, Điểm cuối Debug & Lộ GraphQL Introspection',
    title_en: 'Shadow API, Debug Endpoints & GraphQL Introspection Exposure',
    description_vi: 'Phát hiện các điểm cuối phiên bản cũ (v1, staging, test-api), giao diện debug (actuator, swagger, openapi) và bật GraphQL introspection trên môi trường công khai.',
    description_en: 'Discovers undocumented deprecated endpoints, debug interfaces, swagger/openapi paths, and enabled GraphQL introspection on public production systems.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Gỡ bỏ các endpoint cũ khỏi API Gateway; tắt Swagger UI, OpenAPI JSON và GraphQL Introspection trên Production.',
    remediation_guidance_en: 'Decommission deprecated routes from API Gateway; disable interactive documentation, debug endpoints, and GraphQL introspection in production.',
  },
  {
    check_id: 'API-010',
    category: 'API',
    title_vi: 'Tích hợp API bên thứ ba & Bảo vệ khóa bí mật',
    title_en: 'Third-Party API Integration & Credential Leakage',
    description_vi: 'Kiểm tra các khóa bí mật của bên thứ ba (AWS, OpenAI, VNPay, SendGrid, Firebase) có bị nhúng vào mã nguồn frontend hoặc phản hồi API hay không.',
    description_en: 'Inspects frontend source code and API responses for leaked third-party service credentials (payment gateways, cloud keys, mailers).',
    severity: 'CRITICAL',
    automation_type: 'AUTOMATED',
    target_engine: 'TRIVY',
    remediation_guidance_vi: 'Không bao giờ để lộ API key bí mật ở client; chuyển toàn bộ logic gọi bên thứ ba về phía backend và sử dụng Secret Manager.',
    remediation_guidance_en: 'Store all third-party secrets in dedicated secrets management vaults; execute external API calls strictly server-side.',
  },

  // --- Category 3: FILE (5 Checks) ---
  {
    check_id: 'FILE-001',
    category: 'FILE',
    title_vi: 'Chính sách /media PUBLIC_BY_DESIGN',
    title_en: 'Approved Media Exposure Policy (PUBLIC_BY_DESIGN)',
    description_vi: 'Đánh giá đường dẫn /media theo chính sách phê duyệt: Tài liệu bài giảng công khai đánh giá ĐẠT mà không báo động giả.',
    description_en: 'Evaluates /media assets against approved policy: Public course materials evaluate to PASS without false alarms.',
    severity: 'INFO',
    automation_type: 'AUTOMATED',
    target_engine: 'FILE_POLICY',
    remediation_guidance_vi: 'Duy trì danh sách ngoại lệ được phê duyệt và giám sát tính toàn vẹn của tài nguyên công khai.',
    remediation_guidance_en: 'Maintain versioned approved baseline exceptions and monitor public media integrity.',
  },
  {
    check_id: 'FILE-002',
    category: 'FILE',
    title_vi: 'Rò rỉ tệp nhạy cảm trong Kho tài liệu',
    title_en: 'Unintended Sensitive File Leakage in Storage',
    description_vi: 'Quét phát hiện các tệp tin nguy hiểm nằm trong thư mục tĩnh (.env, student-records.csv, backup.zip, pass.txt).',
    description_en: 'Probes for unauthorized private files (CSV, .env, database dumps, certificates) stored under public paths.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'FILE_POLICY',
    remediation_guidance_vi: 'Di chuyển toàn bộ tệp nhạy cảm ra ngoài document root; cấu hình quyền truy cập nghiêm ngặt.',
    remediation_guidance_en: 'Relocate all sensitive data outside the web root and enforce private object access policies.',
  },
  {
    check_id: 'FILE-003',
    category: 'FILE',
    title_vi: 'Quyền truy cập Bucket MinIO / S3',
    title_en: 'MinIO / S3 Object Storage Permissions',
    description_vi: 'Kiểm tra quyền truy cập công khai trái phép (Public Read/Write, ListObjects) trên bucket lưu trữ tài liệu học tập.',
    description_en: 'Audits MinIO and S3 bucket ACLs and policies for unintended public Read/Write or List permissions.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Kích hoạt S3 Block Public Access; sử dụng Pre-signed URL có thời hạn ngắn cho việc tải tệp tin cá nhân.',
    remediation_guidance_en: 'Enable Block Public Access and generate short-lived pre-signed URLs for authenticated downloads.',
  },
  {
    check_id: 'FILE-004',
    category: 'FILE',
    title_vi: 'Tải tệp tin tùy ý & Vượt đuôi file',
    title_en: 'Arbitrary File Upload & Extension Bypass',
    description_vi: 'Kiểm tra tính năng tải tài liệu, avatar học viên có bị vượt qua kiểm tra định dạng tệp (webshell, double extension).',
    description_en: 'Tests file upload endpoints for executable extension bypass, double extensions, and polyglot files.',
    severity: 'CRITICAL',
    automation_type: 'HYBRID',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Xác thực Magic Bytes thực tế của tệp, đổi tên ngẫu nhiên (UUID) và lưu trữ trên storage riêng biệt không thực thi.',
    remediation_guidance_en: 'Validate file magic headers, randomize filenames with UUIDs, and store on non-executable object stores.',
  },
  {
    check_id: 'FILE-005',
    category: 'FILE',
    title_vi: 'Duyệt đường dẫn tệp & LFI',
    title_en: 'Path Traversal & Local File Inclusion (LFI)',
    description_vi: 'Thăm dò các tham số tải tệp tin (file, path, doc_id) với chuỗi "../" nhằm đọc tệp hệ thống (/etc/passwd, win.ini).',
    description_en: 'Probes file download and viewer endpoints for directory traversal sequences (../) accessing system files.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'ZAP',
    remediation_guidance_vi: 'Chuẩn hóa đường dẫn (Path Canonicalization), sử dụng ID đại diện thay vì đường dẫn tệp trực tiếp.',
    remediation_guidance_en: 'Canonicalize filesystem paths and map files using opaque database identifiers.',
  },

  // --- Category 4: AUTH (5 Checks) ---
  {
    check_id: 'AUTH-001',
    category: 'AUTH',
    title_vi: 'Chống dò quét mật khẩu & Khóa tài khoản',
    title_en: 'Credential Stuffing & Brute-Force Protection',
    description_vi: 'Kiểm tra cơ chế khóa tài khoản sau số lần đăng nhập sai liên tiếp, CAPTCHA và giới hạn tần suất đăng nhập.',
    description_en: 'Audits account lockout policies, rate limiting, and CAPTCHA enforcement on authentication portals.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Khóa tài khoản tạm thời sau 5 lần thất bại liên tiếp; áp dụng exponential backoff cho các lần thử lại.',
    remediation_guidance_en: 'Temporarily lock accounts after repeated login failures and implement exponential backoff delays.',
  },
  {
    check_id: 'AUTH-002',
    category: 'AUTH',
    title_vi: 'Độ ngẫu nhiên phiên & Hủy token khi Đăng xuất',
    title_en: 'Session Token Entropy & Invalidation on Logout',
    description_vi: 'Đo lường độ dài, tính ngẫu nhiên của session cookie/token và đảm bảo token bị hủy hoàn toàn ở backend khi đăng xuất.',
    description_en: 'Evaluates session token cryptographic entropy and verifies complete server-side invalidation upon logout.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Tạo token phiên bằng CSPRNG tối thiểu 128 bit; thu hồi token vào blacklist Redis khi người dùng đăng xuất.',
    remediation_guidance_en: 'Generate tokens using 128-bit CSPRNG and maintain an active token revocation blacklist in Redis.',
  },
  {
    check_id: 'AUTH-003',
    category: 'AUTH',
    title_vi: 'Chính sách độ phức tạp mật khẩu',
    title_en: 'Password Complexity & Policy Enforcement',
    description_vi: 'Kiểm tra việc thực thi chính sách mật khẩu: độ dài tối thiểu, ký tự đặc biệt, kiểm tra mật khẩu phổ biến bị rò rỉ.',
    description_en: 'Validates password complexity rules, minimum length, and checks against breached password lists.',
    severity: 'MEDIUM',
    automation_type: 'MANUAL',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Yêu cầu mật khẩu tối thiểu 12 ký tự; đối chiếu với cơ sở dữ liệu mật khẩu lộ lọt (HaveIBeenPwned).',
    remediation_guidance_en: 'Require minimum 12 characters and check candidate passwords against known breach datasets.',
  },
  {
    check_id: 'AUTH-004',
    category: 'AUTH',
    title_vi: 'Liệt kê người dùng qua phản hồi đăng nhập',
    title_en: 'User Enumeration in Authentication Flows',
    description_vi: 'Kiểm tra sự khác biệt về thông báo lỗi hoặc thời gian phản hồi khi đăng nhập với tài khoản tồn tại và không tồn tại.',
    description_en: 'Audits timing and response differences between valid and invalid usernames on login/reset forms.',
    severity: 'LOW',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Trả về thông báo lỗi chung chung đồng nhất (e.g. "Thông tin đăng nhập không chính xác") với thời gian đo lường cân bằng.',
    remediation_guidance_en: 'Return uniform error messages and balance timing responses across valid and invalid usernames.',
  },
  {
    check_id: 'AUTH-005',
    category: 'AUTH',
    title_vi: 'Xác thực 2 bước & Leo thang đặc quyền',
    title_en: 'Multi-Factor Authentication & Privilege Escalation',
    description_vi: 'Kiểm tra tính bắt buộc của MFA đối với tài khoản quản trị và khả năng vượt qua bước xác thực thứ 2.',
    description_en: 'Evaluates mandatory MFA enforcement for administrative accounts and tests for step-up auth bypasses.',
    severity: 'HIGH',
    automation_type: 'MANUAL',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Bắt buộc kích hoạt TOTP/FIDO2 cho tất cả tài khoản quản trị viên và giáo viên phụ trách.',
    remediation_guidance_en: 'Mandate hardware FIDO2 or TOTP authenticator enforcement for all privileged administrative accounts.',
  },

  // --- Category 5: INFRA (4 Checks) ---
  {
    check_id: 'INFRA-001',
    category: 'INFRA',
    title_vi: 'Cổng dịch vụ mở trên chu vi mạng',
    title_en: 'Perimeter Port Exposure & Unnecessary Services',
    description_vi: 'Quét cổng chu vi phát hiện các dịch vụ không cần thiết hoặc nguy hiểm (SSH, RDP, MySQL, Redis, Telnet).',
    description_en: 'Scans perimeter IP addresses for unnecessary or exposed administrative ports (SSH, RDP, DB ports).',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Đóng tất cả các cổng không sử dụng; chỉ mở cổng 80/443 ra Internet và quản trị qua VPN nội bộ.',
    remediation_guidance_en: 'Close all non-essential ports; restrict administrative services to dedicated internal management VPNs.',
  },
  {
    check_id: 'INFRA-002',
    category: 'INFRA',
    title_vi: 'Chuyển giao vùng DNS & Chiếm đoạt miền con',
    title_en: 'DNS Zone Transfer & Subdomain Takeover',
    description_vi: 'Kiểm tra AXFR zone transfer trên máy chủ DNS định danh và rà soát CNAME trỏ tới dịch vụ đám mây chưa đăng ký.',
    description_en: 'Audits authoritative nameservers for unrestricted AXFR zone transfers and dangling CNAME records.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Vô hiệu hóa DNS zone transfer công khai; thu hồi ngay các bản ghi CNAME trỏ tới tài nguyên đã xóa.',
    remediation_guidance_en: 'Disable public DNS zone transfers and immediately prune dangling DNS records.',
  },
  {
    check_id: 'INFRA-003',
    category: 'INFRA',
    title_vi: 'Nhận diện OS và Web Server',
    title_en: 'Web Server & Operating System Fingerprinting',
    description_vi: 'Kiểm tra các tiêu đề Server, X-Powered-By, Apache/Nginx version strings tạo điều kiện cho kẻ tấn công chọn vũ khí.',
    description_en: 'Audits banner headers revealing exact web server, OS, and framework versions.',
    severity: 'LOW',
    automation_type: 'AUTOMATED',
    target_engine: 'NUCLEI',
    remediation_guidance_vi: 'Cấu hình server_tokens off (Nginx) hoặc ServerTokens Prod (Apache) để xóa sạch thông tin phiên bản.',
    remediation_guidance_en: 'Disable server tokens and strip revealing runtime software version headers.',
  },
  {
    check_id: 'INFRA-004',
    category: 'INFRA',
    title_vi: 'Vượt tường lửa & Lọc gói tin ra ngoài',
    title_en: 'WAF Evasion & Network Boundary Egress',
    description_vi: 'Đánh giá khả năng nhận diện tấn công của WAF và kiểm soát kết nối ra ngoài (Egress filtering) từ máy chủ.',
    description_en: 'Tests WAF rule evasion resilience and verifies strict outbound network egress filtering.',
    severity: 'MEDIUM',
    automation_type: 'HYBRID',
    target_engine: 'EMPIRE_ENGINE',
    remediation_guidance_vi: 'Cập nhật bộ quy tắc CRS cho WAF; chặn toàn bộ kết nối egress từ ứng dụng trừ các địa chỉ đích được ủy quyền.',
    remediation_guidance_en: 'Keep WAF rulesets updated and lock down outbound network egress to verified destination allowlists.',
  },

  // --- Category 6: DEP (5 Checks) ---
  {
    check_id: 'DEP-001',
    category: 'DEP',
    title_vi: 'Lỗ hổng CVE trong thư viện mã nguồn mở',
    title_en: 'Vulnerable Open-Source Dependencies in Code',
    description_vi: 'Quét phân tích thành phần phần mềm (SCA) phát hiện các thư viện npm, pip, composer chứa CVE đã công bố.',
    description_en: 'Performs Software Composition Analysis (SCA) to identify known CVEs in application dependencies.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'TRIVY',
    remediation_guidance_vi: 'Cập nhật thư viện phụ thuộc lên phiên bản vá lỗi mới nhất và tích hợp kiểm tra tự động vào CI/CD.',
    remediation_guidance_en: 'Upgrade affected packages to patched versions and embed automated vulnerability gates into CI/CD.',
  },
  {
    check_id: 'DEP-002',
    category: 'DEP',
    title_vi: 'Lỗ hổng bảo mật trong Container Base Image',
    title_en: 'Container Base Image Vulnerabilities',
    description_vi: 'Quét hình ảnh container Docker phát hiện lỗ hổng hệ điều hành base image (Alpine, Debian, Ubuntu).',
    description_en: 'Scans production container base images for OS package vulnerabilities and unpatched CVEs.',
    severity: 'HIGH',
    automation_type: 'AUTOMATED',
    target_engine: 'TRIVY',
    remediation_guidance_vi: 'Sử dụng Distroless hoặc Minimal Base Image; cập nhật thường xuyên bản vá bảo mật hệ điều hành.',
    remediation_guidance_en: 'Adopt minimal distroless base images and establish regular automated container rebuild schedules.',
  },
  {
    check_id: 'DEP-003',
    category: 'DEP',
    title_vi: 'Sinh và kiểm toán thành phần phần mềm SBOM',
    title_en: 'Software Bill of Materials (SBOM) Generation & Audit',
    description_vi: 'Tạo và kiểm định tài liệu SBOM định dạng CycloneDX / SPDX phục vụ truy xuất nguồn gốc chuỗi cung ứng.',
    description_en: 'Generates and validates CycloneDX/SPDX SBOM manifests for supply chain transparency.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'TRIVY',
    remediation_guidance_vi: 'Tự động sinh SBOM cho mỗi bản phát hành và đối chiếu liên tục với cơ sở dữ liệu lỗ hổng NVD.',
    remediation_guidance_en: 'Automate SBOM generation on every release build and continuously monitor against vulnerability advisories.',
  },
  {
    check_id: 'DEP-004',
    category: 'DEP',
    title_vi: 'Khóa bí mật và Token cứng trong mã nguồn',
    title_en: 'Hardcoded Secrets & API Keys in Artifacts',
    description_vi: 'Quét tĩnh phát hiện khóa bí mật (API keys, JWT secrets, database credentials, private keys) bị lưu cứng.',
    description_en: 'Scans repositories and container layers for hardcoded credentials, API secrets, and private keys.',
    severity: 'CRITICAL',
    automation_type: 'AUTOMATED',
    target_engine: 'TRIVY',
    remediation_guidance_vi: 'Thu hồi và đổi ngay các khóa bị lộ; chuyển sang quản lý bí mật bằng Vault hoặc biến môi trường.',
    remediation_guidance_en: 'Immediately revoke exposed secrets and migrate credentials to a secure secret management vault.',
  },
  {
    check_id: 'DEP-005',
    category: 'DEP',
    title_vi: 'Môi trường thực thi hết hạn hỗ trợ (EOL)',
    title_en: 'Deprecated & End-of-Life Runtime Stacks',
    description_vi: 'Phát hiện các phiên bản ngôn ngữ/runtime (Python, Node.js, PHP) đã hết vòng đời hỗ trợ không còn nhận bản vá.',
    description_en: 'Identifies unsupported end-of-life language runtimes and frameworks lacking security patches.',
    severity: 'MEDIUM',
    automation_type: 'AUTOMATED',
    target_engine: 'TRIVY',
    remediation_guidance_vi: 'Nâng cấp runtime lên phiên bản LTS hiện hành còn được nhà sản xuất duy trì hỗ trợ bảo mật.',
    remediation_guidance_en: 'Upgrade application runtimes to active Long-Term Support (LTS) releases.',
  },
];

export default function ChecklistPage() {
  const { t, locale } = useI18n();
  const { toast } = useToast();

  const [definitions, setDefinitions] = useState<ChecklistDefinition[]>(EMPIRE_CHECKLIST_CATALOG);
  const [selectedCategory, setSelectedCategory] = useState<'ALL' | ChecklistCategory>('ALL');
  const [selectedState, setSelectedState] = useState<'ALL' | ChecklistResultState>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [resultsMap, setResultsMap] = useState<Record<string, ChecklistResultState>>({});
  const [reviewNotesMap, setReviewNotesMap] = useState<Record<string, string>>({});
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeModalCheck, setActiveModalCheck] = useState<ChecklistDefinition | null>(null);
  const [modalSelectedState, setModalSelectedState] = useState<ChecklistResultState>('NEEDS_REVIEW');
  const [modalNotes, setModalNotes] = useState('');
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string>('all');

  const loadLatestRun = useCallback(async (targetAssetId?: string) => {
    try {
      const filterAsset = targetAssetId && targetAssetId !== 'all' ? targetAssetId : undefined;
      const runs = await api.getChecklistRuns(filterAsset);
      if (Array.isArray(runs) && runs.length > 0) {
        const latestRun = runs[0];
        setActiveRunId(latestRun.id);
        const results = await api.getChecklistRunResults(latestRun.id);
        if (Array.isArray(results) && results.length > 0) {
          const newResultsMap: Record<string, ChecklistResultState> = {};
          const newNotesMap: Record<string, string> = {};
          results.forEach((r) => {
            newResultsMap[r.check_id] = r.state;
            if (r.review_notes || r.notes) {
              newNotesMap[r.check_id] = r.review_notes || r.notes || '';
            }
          });
          setResultsMap(newResultsMap);
          setReviewNotesMap(newNotesMap);
        }
      } else {
        setActiveRunId(null);
        setResultsMap({});
        setReviewNotesMap({});
      }
    } catch {
      // Fallback to empty unrun state if server is offline or no runs exist
    }
  }, []);

  // Load server catalog & assets on mount
  useEffect(() => {
    let mounted = true;
    api.getChecklistDefinitions()
      .then((defs) => {
        if (mounted && Array.isArray(defs) && defs.length > 0) {
          setDefinitions(defs);
        }
      })
      .catch(() => {
        // Fallback to local catalog definitions if server endpoint not yet mounted
      });

    api.listAssets({ size: 50 })
      .then((res) => {
        if (mounted && Array.isArray(res?.items)) {
          setAssets(res.items);
        }
      })
      .catch(() => {});

    return () => {
      mounted = false;
    };
  }, []);

  // Sync latest run results whenever selected asset changes
  useEffect(() => {
    loadLatestRun(selectedAssetId);
  }, [selectedAssetId, loadLatestRun]);

  // Compute Honest Metrics
  const metrics = useMemo(() => {
    const total = definitions.length; // 39
    const automatedCount = definitions.filter((d) => d.automation_type === 'AUTOMATED').length;
    const manualCount = definitions.filter((d) => d.automation_type === 'MANUAL').length;
    const hybridCount = definitions.filter((d) => d.automation_type === 'HYBRID').length;

    // Automated coverage percentage: (automated / total) * 100 with division-by-zero guard
    const automatedCoveragePct = total > 0 ? Math.round((automatedCount / total) * 100) : 0;

    // Manual review completion: manual or hybrid checks that are NOT in 'NOT_RUN' state
    const manualOrHybridChecks = definitions.filter((d) => d.automation_type !== 'AUTOMATED');
    const completedManualChecks = manualOrHybridChecks.filter((d) => {
      const state = resultsMap[d.check_id] || 'NOT_RUN';
      return state !== 'NOT_RUN';
    });
    const manualCompletionPct = manualOrHybridChecks.length > 0
      ? Math.round((completedManualChecks.length / manualOrHybridChecks.length) * 100)
      : 0;

    // State counts
    const stateCounts: Record<ChecklistResultState, number> = {
      PASS: 0,
      FAIL: 0,
      NEEDS_REVIEW: 0,
      NOT_APPLICABLE: 0,
      BLOCKED: 0,
      NOT_RUN: 0,
      ERROR: 0,
    };

    definitions.forEach((d) => {
      const state = resultsMap[d.check_id] || 'NOT_RUN';
      stateCounts[state] = (stateCounts[state] || 0) + 1;
    });

    return {
      total,
      automatedCount,
      manualCount,
      hybridCount,
      automatedCoveragePct,
      manualCompletionPct,
      stateCounts,
    };
  }, [definitions, resultsMap]);

  // Filter definitions based on category, state, and search query
  const filteredDefinitions = useMemo(() => {
    return definitions.filter((def) => {
      if (selectedCategory !== 'ALL' && def.category !== selectedCategory) {
        return false;
      }
      const currentState = resultsMap[def.check_id] || 'NOT_RUN';
      if (selectedState !== 'ALL' && currentState !== selectedState) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesId = def.check_id.toLowerCase().includes(q);
        const matchesTitleVi = def.title_vi.toLowerCase().includes(q);
        const matchesTitleEn = def.title_en.toLowerCase().includes(q);
        const matchesEngine = def.target_engine.toLowerCase().includes(q);
        const matchesSeverity = def.severity.toLowerCase().includes(q);
        return matchesId || matchesTitleVi || matchesTitleEn || matchesEngine || matchesSeverity;
      }
      return true;
    });
  }, [definitions, selectedCategory, selectedState, searchQuery, resultsMap]);

  const handleOpenModal = (check: ChecklistDefinition) => {
    setActiveModalCheck(check);
    const curState = resultsMap[check.check_id] || 'NOT_RUN';
    setModalSelectedState(curState === 'NOT_RUN' ? 'NEEDS_REVIEW' : curState);
    setModalNotes(reviewNotesMap[check.check_id] || '');
  };

  const handleSaveReview = async () => {
    if (!activeModalCheck) return;

    const oldState = resultsMap[activeModalCheck.check_id] || 'NOT_RUN';
    const unverifiedStates: ChecklistResultState[] = ['NOT_RUN', 'BLOCKED', 'ERROR'];

    // Strict Domain Invariant: Transitioning from NOT_RUN, BLOCKED, or ERROR directly to PASS is forbidden
    if (unverifiedStates.includes(oldState) && modalSelectedState === 'PASS') {
      toast({
        title: 'Quy tắc bất biến / Invariant Violation',
        description: t('checklist.invariantNotice', 'Quy tắc bất biến: Không thể chuyển trực tiếp từ Chưa chạy/Bị chặn/Lỗi sang PASS. Cần qua bước NEEDS_REVIEW.'),
        variant: 'destructive',
      });
      return;
    }

    // Affirmative Evidence Guard: Marking PASS requires review notes
    if (modalSelectedState === 'PASS' && !modalNotes.trim()) {
      toast({
        title: 'Quy tắc bất biến / Invariant Violation',
        description: t('checklist.invariantNotice', 'Quy tắc bất biến: Cần ghi chú bằng chứng khi chuyển trạng thái sang PASS.'),
        variant: 'destructive',
      });
      return;
    }

    // Genuine API Persistence
    if (activeRunId) {
      try {
        const updatedResult = await api.reviewChecklistResult(activeRunId, activeModalCheck.check_id, {
          state: modalSelectedState,
          review_notes: modalNotes.trim(),
        });

        const finalState = updatedResult?.state || modalSelectedState;
        const finalNotes = updatedResult?.review_notes || updatedResult?.notes || modalNotes.trim();

        setResultsMap((prev) => ({
          ...prev,
          [activeModalCheck.check_id]: finalState,
        }));

        if (finalNotes) {
          setReviewNotesMap((prev) => ({
            ...prev,
            [activeModalCheck.check_id]: finalNotes,
          }));
        }

        toast({
          title: 'Đã lưu đánh giá / Review Saved',
          description: `${activeModalCheck.check_id} -> ${finalState}`,
        });
        setActiveModalCheck(null);
      } catch (err: any) {
        toast({
          title: 'Lỗi lưu đánh giá / Review Save Failed',
          description: err?.message || 'Không thể lưu đánh giá lên máy chủ. Kiểm tra kết nối API.',
          variant: 'destructive',
        });
      }
    } else {
      // Local fallback when running offline or pre-run
      setResultsMap((prev) => ({
        ...prev,
        [activeModalCheck.check_id]: modalSelectedState,
      }));

      if (modalNotes.trim()) {
        setReviewNotesMap((prev) => ({
          ...prev,
          [activeModalCheck.check_id]: modalNotes.trim(),
        }));
      }

      toast({
        title: 'Đã lưu đánh giá (Cục bộ) / Review Saved (Local)',
        description: `${activeModalCheck.check_id} -> ${modalSelectedState}`,
      });
      setActiveModalCheck(null);
    }
  };

  const handleRunAllEvaluations = async () => {
    const targetAssetId = selectedAssetId !== 'all' ? selectedAssetId : (assets[0]?.id || '');
    if (!targetAssetId) {
      toast({
        title: 'Chưa chọn tài sản / Target Required',
        description: 'Vui lòng chọn hoặc thêm tài sản (Asset) để thực hiện đánh giá.',
        variant: 'destructive',
      });
      return;
    }

    setIsEvaluating(true);
    toast({
      title: t('checklist.runAssessment', 'Khởi chạy đánh giá toàn diện'),
      description: 'Đang gửi lệnh đánh giá 39 tiêu chí tới các Scanner Engine...',
    });

    try {
      const run = await api.createChecklistRun({
        asset_id: targetAssetId,
        mode: 'AUTOMATED',
      });

      setActiveRunId(run.id);

      // Reload live results for the newly created run
      const results = await api.getChecklistRunResults(run.id);
      if (Array.isArray(results) && results.length > 0) {
        const newResultsMap: Record<string, ChecklistResultState> = {};
        const newNotesMap: Record<string, string> = {};
        results.forEach((r) => {
          newResultsMap[r.check_id] = r.state;
          if (r.review_notes || r.notes) {
            newNotesMap[r.check_id] = r.review_notes || r.notes || '';
          }
        });
        setResultsMap(newResultsMap);
        setReviewNotesMap(newNotesMap);
      }

      toast({
        title: 'Hoàn tất đánh giá / Assessment Completed',
        description: `Đã hoàn tất đánh giá cho phiên ${run.id.slice(0, 8)}: ${run.total_checks} tiêu chí.`,
      });
    } catch (err: any) {
      toast({
        title: 'Lỗi khởi chạy đánh giá / Assessment Failed',
        description: err?.message || 'Không thể khởi chạy đánh giá. Kiểm tra phân quyền phạm vi (Scope Gate).',
        variant: 'destructive',
      });
    } finally {
      setIsEvaluating(false);
    }
  };

  const getSeverityBadge = (sev: SeverityLevel) => {
    switch (sev) {
      case 'CRITICAL':
        return 'bg-rose-950/80 text-rose-400 border-rose-800';
      case 'HIGH':
        return 'bg-orange-950/80 text-orange-400 border-orange-800';
      case 'MEDIUM':
        return 'bg-amber-950/80 text-amber-400 border-amber-800';
      case 'LOW':
        return 'bg-emerald-950/80 text-emerald-400 border-emerald-800';
      default:
        return 'bg-cyan-950/80 text-cyan-400 border-cyan-800';
    }
  };

  const getStateBadge = (state: ChecklistResultState) => {
    switch (state) {
      case 'PASS':
        return {
          bg: 'bg-emerald-950/80 text-emerald-400 border-emerald-800',
          icon: CheckCircle2,
          label: t('checklist.statePass', 'PASS'),
        };
      case 'FAIL':
        return {
          bg: 'bg-rose-950/80 text-rose-400 border-rose-800',
          icon: XCircle,
          label: t('checklist.stateFail', 'FAIL'),
        };
      case 'NEEDS_REVIEW':
        return {
          bg: 'bg-amber-950/80 text-amber-400 border-amber-800',
          icon: AlertTriangle,
          label: t('checklist.stateNeedsReview', 'NEEDS_REVIEW'),
        };
      case 'NOT_APPLICABLE':
        return {
          bg: 'bg-zinc-900/80 text-zinc-400 border-zinc-700',
          icon: MinusCircle,
          label: t('checklist.stateNotApplicable', 'N/A'),
        };
      case 'BLOCKED':
        return {
          bg: 'bg-orange-950/80 text-orange-400 border-orange-800',
          icon: Ban,
          label: t('checklist.stateBlocked', 'BLOCKED'),
        };
      case 'NOT_RUN':
        return {
          bg: 'bg-slate-900/80 text-slate-400 border-slate-700',
          icon: Clock,
          label: t('checklist.stateNotRun', 'NOT_RUN'),
        };
      case 'ERROR':
        return {
          bg: 'bg-purple-950/80 text-purple-400 border-purple-800',
          icon: AlertOctagon,
          label: t('checklist.stateError', 'ERROR'),
        };
    }
  };

  const getCategoryIcon = (cat: ChecklistCategory) => {
    switch (cat) {
      case 'WEB':
        return Globe;
      case 'API':
        return Cpu;
      case 'FILE':
        return FileCode;
      case 'AUTH':
        return Lock;
      case 'INFRA':
        return Server;
      case 'DEP':
        return Boxes;
    }
  };

  return (
    <div className="space-y-6">
      {/* =================================================================== */}
      {/* PAGE HEADER & ASSESSMENT CONTROLS                                    */}
      {/* =================================================================== */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-2xl liquid-glass border border-white/10 shadow-xl">
        <div>
          <div className="flex items-center gap-2 text-xs text-nf-400 font-mono mb-1">
            <Link href="/dashboard" className="hover:text-white transition">Platform</Link>
            <span>/</span>
            <span className="text-white font-bold">{t('nav.checklist', 'Empire Checklist')}</span>
          </div>
          <h1 className="text-lg md:text-xl font-black text-white flex items-center gap-2 tracking-wide">
            <ShieldCheck className="w-6 h-6 text-cyan-400" />
            <span>{t('checklist.title', 'EMPIRE PENTEST CHECKLIST CATALOG')}</span>
          </h1>
          <p className="text-xs text-nf-400 mt-1 max-w-2xl">
            {t('checklist.subtitle', '39 tiêu chí kiểm thử bảo mật chuyên sâu trên 6 phân hệ nghiệp vụ với cơ chế đánh giá bất biến 7 trạng thái.')}
          </p>
        </div>

        {/* Top Controls: Target Selector & Launch Assessment */}
        <div className="flex flex-wrap items-center gap-2.5">
          {assets.length > 0 && (
            <select
              value={selectedAssetId}
              onChange={(e) => setSelectedAssetId(e.target.value)}
              className="px-3 py-2 rounded-xl bg-nf-900/90 border border-white/10 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
            >
              <option value="all">Empire Estate (All 7 Assets)</option>
              {assets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.target_locator})
                </option>
              ))}
            </select>
          )}

          <button
            onClick={handleRunAllEvaluations}
            disabled={isEvaluating}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-black text-xs transition-all shadow-lg shadow-cyan-950/40 cursor-pointer disabled:opacity-50"
          >
            {isEvaluating ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Evaluating 39 Checks...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-black" />
                <span>{t('checklist.runAssessment', 'Run Checklist Assessment')}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* SUMMARY KPI CARDS                                                    */}
      {/* =================================================================== */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Checks */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-lg">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-nf-400 uppercase tracking-wider">
              {t('checklist.totalChecks', 'Total Checks')}
            </span>
            <Layers className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-black text-white">{metrics.total}</span>
            <span className="text-[11px] text-nf-500 font-mono">6 Categories</span>
          </div>
          <div className="mt-2 flex items-center gap-2 text-[10px] text-nf-400 font-mono">
            <span className="text-cyan-400 font-bold">{metrics.automatedCount} Auto</span>
            <span>•</span>
            <span className="text-amber-400 font-bold">{metrics.hybridCount} Hybrid</span>
            <span>•</span>
            <span className="text-purple-400 font-bold">{metrics.manualCount} Manual</span>
          </div>
        </div>

        {/* Card 2: Automated Coverage % */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-lg">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-nf-400 uppercase tracking-wider">
              {t('checklist.automatedCoverage', 'Automated Coverage')}
            </span>
            <Cpu className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-black text-emerald-400">{metrics.automatedCoveragePct}%</span>
            <span className="text-[11px] text-nf-500 font-mono">({metrics.automatedCount}/{metrics.total} checks)</span>
          </div>
          {/* Progress Bar */}
          <div className="mt-2 w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full bg-emerald-400 rounded-full transition-all duration-500"
              style={{ width: `${metrics.automatedCoveragePct}%` }}
            />
          </div>
        </div>

        {/* Card 3: Manual Review Completion % */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-lg">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-nf-400 uppercase tracking-wider">
              {t('checklist.manualCompletion', 'Manual Review Completion')}
            </span>
            <Sliders className="w-4 h-4 text-purple-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-black text-purple-400">{metrics.manualCompletionPct}%</span>
            <span className="text-[11px] text-nf-500 font-mono">verified</span>
          </div>
          <div className="mt-2 w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full bg-purple-400 rounded-full transition-all duration-500"
              style={{ width: `${metrics.manualCompletionPct}%` }}
            />
          </div>
        </div>

        {/* Card 4: 7-State Counters Matrix */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-bold text-nf-400 uppercase tracking-wider">
              {t('checklist.filterByState', 'State Counters')}
            </span>
            <span className="text-[9px] font-mono text-cyan-400">7-STATE</span>
          </div>
          <div className="grid grid-cols-4 gap-1 text-center font-mono">
            <div className="p-1 rounded bg-emerald-950/60 border border-emerald-900/60">
              <div className="text-[9px] text-emerald-400 font-bold">PASS</div>
              <div className="text-xs font-black text-white">{metrics.stateCounts.PASS}</div>
            </div>
            <div className="p-1 rounded bg-rose-950/60 border border-rose-900/60">
              <div className="text-[9px] text-rose-400 font-bold">FAIL</div>
              <div className="text-xs font-black text-white">{metrics.stateCounts.FAIL}</div>
            </div>
            <div className="p-1 rounded bg-amber-950/60 border border-amber-900/60">
              <div className="text-[9px] text-amber-400 font-bold">REVIEW</div>
              <div className="text-xs font-black text-white">{metrics.stateCounts.NEEDS_REVIEW}</div>
            </div>
            <div className="p-1 rounded bg-zinc-900/60 border border-zinc-800">
              <div className="text-[9px] text-zinc-400 font-bold">N/A</div>
              <div className="text-xs font-black text-white">{metrics.stateCounts.NOT_APPLICABLE}</div>
            </div>
          </div>
        </div>
      </div>

      {/* =================================================================== */}
      {/* FILTER BAR & SEARCH                                                  */}
      {/* =================================================================== */}
      <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-lg flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 text-xs">
        {/* Category Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setSelectedCategory('ALL')}
            className={`px-3 py-1.5 rounded-xl font-bold transition-all cursor-pointer ${
              selectedCategory === 'ALL'
                ? 'bg-white text-nf-950 font-black shadow-md'
                : 'bg-white/[0.04] text-nf-400 hover:text-white border border-white/5'
            }`}
          >
            {t('checklist.allCategories', 'All Categories (39)')}
          </button>
          {(['WEB', 'API', 'FILE', 'AUTH', 'INFRA', 'DEP'] as ChecklistCategory[]).map((cat) => {
            const Icon = getCategoryIcon(cat);
            const count = definitions.filter((d) => d.category === cat).length;
            const isActive = selectedCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl font-bold transition-all cursor-pointer ${
                  isActive
                    ? 'bg-cyan-500 text-black font-black shadow-md'
                    : 'bg-white/[0.04] text-nf-400 hover:text-white border border-white/5'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{cat}</span>
                <span className="text-[10px] opacity-75">({count})</span>
              </button>
            );
          })}
        </div>

        {/* State Filter & Search Box */}
        <div className="flex items-center gap-2">
          {/* State Filter Dropdown */}
          <select
            value={selectedState}
            onChange={(e) => setSelectedState(e.target.value as any)}
            className="px-3 py-2 rounded-xl bg-nf-900/90 border border-white/10 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
          >
            <option value="ALL">All States (7)</option>
            <option value="PASS">PASS</option>
            <option value="FAIL">FAIL</option>
            <option value="NEEDS_REVIEW">NEEDS_REVIEW</option>
            <option value="NOT_APPLICABLE">NOT_APPLICABLE</option>
            <option value="BLOCKED">BLOCKED</option>
            <option value="NOT_RUN">NOT_RUN</option>
            <option value="ERROR">ERROR</option>
          </select>

          {/* Search Input */}
          <div className="relative flex-1 sm:w-64">
            <Search className="w-3.5 h-3.5 text-nf-500 absolute left-3 top-1/2 transform -translate-y-1/2" />
            <input
              type="text"
              placeholder={t('checklist.searchPlaceholder', 'Search checks, CVEs, engines...')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-xl bg-nf-900/90 border border-white/10 text-xs text-white placeholder-nf-500 focus:outline-none focus:border-cyan-500"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-nf-500 hover:text-white"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* =================================================================== */}
      {/* CHECKLIST DEFINITIONS CATALOG GRID                                   */}
      {/* =================================================================== */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredDefinitions.map((def) => {
          const currentState = resultsMap[def.check_id] || 'NOT_RUN';
          const stateBadge = getStateBadge(currentState);
          const StateIcon = stateBadge.icon;
          const CategoryIcon = getCategoryIcon(def.category);
          const title = locale === 'vi' ? def.title_vi : def.title_en;
          const altTitle = locale === 'vi' ? def.title_en : def.title_vi;
          const description = locale === 'vi' ? def.description_vi : def.description_en;

          return (
            <div
              key={def.check_id}
              onClick={() => handleOpenModal(def)}
              className="p-4 rounded-2xl liquid-glass-card border border-white/10 hover:border-white/20 transition-all flex flex-col justify-between cursor-pointer group shadow-md"
            >
              <div>
                {/* Card Header: Check ID & State Badge */}
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <span className="px-2 py-0.5 rounded-lg bg-white/10 text-white font-mono font-black text-xs border border-white/10">
                      {def.check_id}
                    </span>
                    <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-white/5 text-[10px] text-nf-400 font-mono">
                      <CategoryIcon className="w-3 h-3" />
                      {def.category}
                    </span>
                  </div>

                  <span
                    className={`flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-mono font-bold ${stateBadge.bg}`}
                  >
                    <StateIcon className="w-3 h-3" />
                    <span>{stateBadge.label}</span>
                  </span>
                </div>

                {/* Check Title */}
                <h3 className="font-bold text-white text-xs group-hover:text-cyan-400 transition leading-snug line-clamp-2">
                  {title}
                </h3>
                <p className="text-[10px] text-nf-500 italic mt-0.5 line-clamp-1">{altTitle}</p>

                {/* Description Snippet */}
                <p className="text-[11px] text-nf-400 mt-2 line-clamp-2 leading-relaxed">
                  {description}
                </p>
              </div>

              {/* Card Footer: Metadata Tags & Click affordance */}
              <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-[10px]">
                <div className="flex items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded border font-bold ${getSeverityBadge(def.severity)}`}>
                    {def.severity}
                  </span>
                  <span className="px-1.5 py-0.5 rounded bg-white/5 text-nf-400 font-mono">
                    {def.automation_type}
                  </span>
                </div>

                <div className="flex items-center gap-1 text-nf-500 font-mono">
                  <span>{def.target_engine}</span>
                  <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {filteredDefinitions.length === 0 && (
        <div className="p-12 text-center rounded-2xl liquid-glass-card border border-white/10">
          <AlertOctagon className="w-8 h-8 text-nf-500 mx-auto mb-2" />
          <h4 className="font-bold text-white text-sm">Không tìm thấy tiêu chí phù hợp</h4>
          <p className="text-xs text-nf-400 mt-1">Vui lòng thử lại với từ khóa tìm kiếm hoặc bộ lọc khác.</p>
        </div>
      )}

      {/* =================================================================== */}
      {/* DETAILED CHECK METADATA & MANUAL REVIEW MODAL / DRAWER               */}
      {/* =================================================================== */}
      {activeModalCheck && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
          <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-3xl liquid-glass-modal border border-white/15 p-6 shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-start justify-between pb-4 border-b border-white/10">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 rounded-lg bg-cyan-500 text-black font-mono font-black text-xs">
                    {activeModalCheck.check_id}
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-white/10 text-white font-mono text-xs">
                    {activeModalCheck.category}
                  </span>
                  <span className={`px-2 py-0.5 rounded-md border text-xs font-bold ${getSeverityBadge(activeModalCheck.severity)}`}>
                    {activeModalCheck.severity}
                  </span>
                </div>
                <h2 className="font-black text-white text-base mt-2">
                  {locale === 'vi' ? activeModalCheck.title_vi : activeModalCheck.title_en}
                </h2>
                <p className="text-xs text-nf-400 italic">
                  {locale === 'vi' ? activeModalCheck.title_en : activeModalCheck.title_vi}
                </p>
              </div>

              <button
                onClick={() => setActiveModalCheck(null)}
                className="p-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-white transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="py-4 space-y-4 text-xs">
              {/* Metadata Grid */}
              <div className="grid grid-cols-2 gap-3 p-3.5 rounded-xl bg-white/[0.02] border border-white/10 font-mono text-[11px]">
                <div>
                  <span className="text-nf-500">{t('checklist.automation', 'Automation')}: </span>
                  <span className="text-white font-bold">{activeModalCheck.automation_type}</span>
                </div>
                <div>
                  <span className="text-nf-500">{t('checklist.engine', 'Engine')}: </span>
                  <span className="text-cyan-400 font-bold">{activeModalCheck.target_engine}</span>
                </div>
              </div>

              {/* Description Section */}
              <div className="space-y-1.5">
                <h4 className="font-bold text-white uppercase text-[11px] tracking-wider">
                  {t('checklist.description', 'Description / Chi tiết tiêu chí')}
                </h4>
                <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/10 text-nf-300 leading-relaxed space-y-2">
                  <p>{locale === 'vi' ? activeModalCheck.description_vi : activeModalCheck.description_en}</p>
                  <p className="text-nf-500 italic pt-1 border-t border-white/5">
                    {locale === 'vi' ? activeModalCheck.description_en : activeModalCheck.description_vi}
                  </p>
                </div>
              </div>

              {/* Remediation Guidance */}
              <div className="space-y-1.5">
                <h4 className="font-bold text-emerald-400 uppercase text-[11px] tracking-wider">
                  {t('checklist.remediation', 'Khuyến nghị khắc phục / Remediation Guidance')}
                </h4>
                <div className="p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-900/40 text-emerald-300 leading-relaxed space-y-1.5">
                  <p>{locale === 'vi' ? activeModalCheck.remediation_guidance_vi : activeModalCheck.remediation_guidance_en}</p>
                  <p className="text-emerald-500/70 italic text-[11px]">
                    {locale === 'vi' ? activeModalCheck.remediation_guidance_en : activeModalCheck.remediation_guidance_vi}
                  </p>
                </div>
              </div>

              {/* Manual Review Form */}
              <div className="p-4 rounded-2xl bg-white/[0.04] border border-white/10 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-white text-xs flex items-center gap-1.5">
                    <Sliders className="w-4 h-4 text-cyan-400" />
                    <span>{t('checklist.manualReview', 'Cập nhật đánh giá chuyên gia')}</span>
                  </h4>
                  <span className="text-[10px] text-nf-500 font-mono">Immutable Ledger</span>
                </div>

                {/* State Radios */}
                <div>
                  <label className="block text-[11px] text-nf-400 mb-1.5">Trạng thái kết luận (Result State):</label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
                    {(['PASS', 'FAIL', 'NEEDS_REVIEW', 'NOT_APPLICABLE', 'BLOCKED', 'NOT_RUN', 'ERROR'] as ChecklistResultState[]).map((st) => {
                      const oldState = resultsMap[activeModalCheck.check_id] || 'NOT_RUN';
                      const isForbiddenPass = st === 'PASS' && ['NOT_RUN', 'BLOCKED', 'ERROR'].includes(oldState);
                      return (
                        <button
                          key={st}
                          type="button"
                          disabled={isForbiddenPass}
                          onClick={() => setModalSelectedState(st)}
                          title={isForbiddenPass ? 'Quy tắc bất biến: Không thể chuyển trực tiếp từ Chưa chạy/Bị chặn/Lỗi sang PASS. Cần qua bước NEEDS_REVIEW.' : undefined}
                          className={`px-2 py-1.5 rounded-lg border text-[10px] font-mono font-bold transition-all ${
                            isForbiddenPass
                              ? 'opacity-30 cursor-not-allowed bg-white/[0.01] text-nf-600 border-white/5 line-through'
                              : modalSelectedState === st
                              ? 'bg-cyan-500 text-black border-cyan-400 shadow-md font-black'
                              : 'bg-white/[0.03] text-nf-400 border-white/10 hover:text-white'
                          }`}
                        >
                          {st}
                        </button>
                      );
                    })}
                  </div>
                  {['NOT_RUN', 'BLOCKED', 'ERROR'].includes(resultsMap[activeModalCheck.check_id] || 'NOT_RUN') && (
                    <p className="text-[10px] text-amber-400/90 mt-1.5 italic">
                      * Chú ý: Tiêu chí đang ở trạng thái {resultsMap[activeModalCheck.check_id] || 'NOT_RUN'} không thể chuyển trực tiếp sang PASS (cần qua bước trung gian NEEDS_REVIEW).
                    </p>
                  )}
                </div>

                {/* Review Notes */}
                <div>
                  <label className="block text-[11px] text-nf-400 mb-1.5">
                    {t('checklist.reviewNotes', 'Ghi chú đánh giá / Bằng chứng kiểm thử:')}
                  </label>
                  <textarea
                    rows={3}
                    value={modalNotes}
                    onChange={(e) => setModalNotes(e.target.value)}
                    placeholder="Ghi chú chi tiết kết quả kiểm tra hoặc lý do cập nhật trạng thái..."
                    className="w-full p-2.5 rounded-xl bg-nf-900 border border-white/10 text-xs text-white placeholder-nf-600 focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="pt-4 border-t border-white/10 flex items-center justify-between">
              <span className="text-[10px] text-nf-500 max-w-xs line-clamp-1">
                {t('checklist.invariantNotice', 'Quy tắc bất biến: Cần ghi chú bằng chứng khi chuyển trạng thái sang PASS.')}
              </span>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setActiveModalCheck(null)}
                  className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold text-xs transition"
                >
                  {t('common.close', 'Đóng')}
                </button>
                <button
                  type="button"
                  onClick={handleSaveReview}
                  className="px-5 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-black text-xs transition shadow-lg shadow-cyan-950/50"
                >
                  {t('checklist.saveReview', 'Lưu đánh giá')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
