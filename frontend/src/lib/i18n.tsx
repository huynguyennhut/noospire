'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type Locale = 'vi' | 'en';

export interface I18nContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, fallback?: string) => string;
}

const DICTIONARY: Record<Locale, Record<string, string>> = {
  vi: {
    // Brand & System
    'brand.title': 'NOOSFORGE',
    'brand.subtitle': 'Trung tâm Tình báo An ninh SOC',
    'brand.soc': 'Empire Security SOC',
    'brand.continuousAudit': 'Giám sát an ninh liên tục',
    'brand.targetContext': 'Ngữ cảnh mục tiêu:',
    'brand.version': 'v2.0.0',

    // Navigation
    'nav.overview': 'Tổng quan bảo mật',
    'nav.targets': 'Mục tiêu & Tài sản',
    'nav.modules': 'Phân hệ Empire',
    'nav.scans': 'Trung tâm quét',
    'nav.activeAssessments': 'Đánh giá đang chạy',
    'nav.engineRuns': 'Lượt chạy engine',
    'nav.findings': 'Lỗ hổng & Bằng chứng',
    'nav.intel': 'Tình báo lỗ hổng',
    'nav.remediation': 'Theo dõi khắc phục',
    'nav.reports': 'Báo cáo kiểm toán',
    'nav.schedules': 'Lịch & công suất',
    'nav.users': 'Người dùng & quyền',
    'nav.rules': 'Quy tắc phát hiện',
    'nav.integrations': 'Tích hợp hệ thống',
    'nav.health': 'Trạng thái hệ thống',
    'nav.settings': 'Cài đặt hệ thống',

    // Navigation Groups & Responsive Shell
    'nav.group.core': 'Tổng quan cốt lõi',
    'nav.group.inventory': 'Quản lý & Quét',
    'nav.group.intelligence': 'Tình báo & Phân hệ',
    'nav.group.governance': 'Quản trị & Hệ thống',
    'shell.notifications': 'Thông báo an ninh',
    'shell.markAllRead': 'Đánh dấu tất cả đã đọc',
    'shell.noNotifications': 'Không có cảnh báo mới',
    'shell.alertsCount': '{count} cảnh báo chưa đọc',
    'shell.backendOnline': 'Máy chủ: Hoạt động',
    'shell.backendChecking': 'Đang kiểm tra kết nối...',
    'shell.backendOffline': 'Mất kết nối máy chủ',
    'shell.targetLabel': 'Mục tiêu giám sát:',
    'shell.targetName': 'Empire Education Platform',
    'shell.scopeBadge': 'CÙNG NGUỒN (SAME-ORIGIN)',
    'shell.collapseSidebar': 'Thu gọn thanh điều hướng',
    'shell.expandSidebar': 'Mở rộng thanh điều hướng',
    'shell.menuOpen': 'Mở menu điều hướng',
    'shell.menuClose': 'Đóng menu',

    // Common Actions & Labels
    'common.search': 'Tìm kiếm...',
    'common.filter': 'Lọc',
    'common.refresh': 'Làm mới',
    'common.scanNow': 'Quét ngay',
    'common.verify': 'Xác minh mục tiêu',
    'common.verified': 'ĐÃ XÁC MINH',
    'common.pending': 'CHỜ XỬ LÝ',
    'common.failed': 'THẤT BẠI',
    'common.cancel': 'Hủy bỏ',
    'common.close': 'Đóng',
    'common.save': 'Lưu lại',
    'common.copy': 'Sao chép',
    'common.copied': 'Đã sao chép!',
    'common.retest': 'Kiểm thử lại (Retest)',
    'common.evidence': 'Bằng chứng',
    'common.actions': 'Thao tác',
    'common.status': 'Trạng thái',
    'common.loading': 'Đang tải dữ liệu...',
    'common.noData': 'Không tìm thấy dữ liệu phù hợp.',
    'common.viewDetails': 'Xem chi tiết',
    'common.download': 'Tải xuống',
    'common.submit': 'Gửi duyệt',
    'common.approve': 'Phê duyệt',
    'common.activate': 'Kích hoạt',
    'common.delete': 'Xóa',
    'common.showing': 'Đang hiển thị:',
    'common.all': 'Tất cả',

    // Severities
    'severity.critical': 'Nghiêm trọng',
    'severity.high': 'Cao',
    'severity.medium': 'Trung bình',
    'severity.low': 'Thấp',
    'severity.info': 'Thông tin',

    // Posture
    'posture.critical': 'Nguy cấp',
    'posture.elevated': 'Cảnh báo cao',
    'posture.moderate': 'Trung bình',
    'posture.secure': 'An toàn',

    // Target Management (/assets)
    'targets.title': 'QUẢN LÝ MỤC TIÊU BẢO MẬT EMPIRE',
    'targets.subtitle': 'Đăng ký, nhập hàng loạt, cấu hình và giám sát bề mặt tấn công của các phân hệ Empire.',
    'targets.bulkImport': 'Nhập hàng loạt mục tiêu',
    'targets.registerTarget': 'Đăng ký mục tiêu',
    'targets.searchPlaceholder': 'Tìm kiếm mục tiêu, URL, công nghệ...',
    'targets.allModules': 'Tất cả phân hệ Empire',
    'targets.allEnvironments': 'Tất cả môi trường',
    'targets.colTarget': 'Mục tiêu & Định danh',
    'targets.colModule': 'Phân hệ Empire',
    'targets.colTech': 'Ngăn xếp công nghệ',
    'targets.colEnv': 'Môi trường',
    'targets.colPolicy': 'Chính sách /media',
    'targets.colStatus': 'Trạng thái',
    'targets.colActions': 'Thao tác',
    'targets.verifyButton': 'Xác minh 8 bước',
    'targets.scanButton': 'Quét ngay',
    'targets.findingsButton': 'Lỗ hổng',
    'targets.publicMediaPolicy': 'CÔNG KHAI /MEDIA THEO THIẾT KẾ',
    'targets.standardRestricted': 'Tiêu chuẩn giới hạn',
    'targets.deleteConfirm': 'Bạn có chắc chắn muốn xóa mục tiêu này khỏi danh sách quản lý?',

    // Verification Modal
    'verify.modalTitle': 'Quy trình xác minh mục tiêu 8 bước (Live Probe Pipeline)',
    'verify.modalSubtitle': 'Thực thi quy trình kiểm tra trực tiếp đa tầng: DNS, TLS, HTTP, phát hiện chuyển hướng, nhận diện công nghệ và ủy quyền an ninh.',
    'verify.executing': 'Đang tiến hành kiểm tra trực tiếp...',
    'verify.executeButton': 'Chạy kiểm tra xác minh 8 bước',
    'verify.reverifyButton': 'Kiểm tra lại',
    'verify.step1Title': '1. Xác thực & Chuẩn hóa đầu vào',
    'verify.step1Desc': 'Kiểm tra cấu trúc URI, phân tách host, giao thức, loại bỏ ký tự nguy hiểm.',
    'verify.step2Title': '2. Phân giải tên miền DNS',
    'verify.step2Desc': 'Truy vấn bản ghi A, AAAA, CNAME và kiểm tra máy chủ định danh có thẩm quyền.',
    'verify.step3Title': '3. Xác minh chứng chỉ bảo mật TLS/SSL',
    'verify.step3Desc': 'Đánh giá chuỗi chứng chỉ X.509, hạn dùng, tổ chức cấp phát và bộ mã hóa cipher.',
    'verify.step4Title': '4. Kết nối mạng HTTP/HTTPS',
    'verify.step4Desc': 'Gửi yêu cầu thăm dò chuẩn, đo lường độ trễ mạng và xác thực mã trạng thái HTTP.',
    'verify.step5Title': '5. Phân tích chuỗi chuyển hướng URL',
    'verify.step5Desc': 'Theo dõi các bước nhảy chuyển tiếp (301/302), ngăn chặn vòng lặp vô hạn.',
    'verify.step6Title': '6. Khám phá tài nguyên Web',
    'verify.step6Desc': 'Thu thập cấu hình robots.txt, sitemap và kiểm tra các tiêu đề an ninh cơ bản.',
    'verify.step7Title': '7. Dấu vân tay công nghệ (Fingerprinting)',
    'verify.step7Desc': 'Phân tích máy chủ web, framework ứng dụng, WAF và thành phần nhận diện.',
    'verify.step8Title': '8. Đánh giá kết quả & Kích hoạt chính sách',
    'verify.step8Desc': 'Xác thực toàn bộ tiêu chí, cấp thẻ VERIFIED và kích hoạt quyền quét liên tục.',
    'verify.pass': 'ĐẠT (PASS)',
    'verify.probing': 'ĐANG KIỂM TRA...',
    'verify.queued': 'CHỜ THỰC HIỆN',
    'verify.successBadge': 'XÁC MINH THÀNH CÔNG 100%',
    'verify.successDetail': 'Mục tiêu đã được chứng minh quyền sở hữu và sẵn sàng cho các bài kiểm tra chuyên sâu.',

    // Findings & Evidence (/findings)
    'findings.title': 'TRUNG TÂM LỖ HỔNG & BẰNG CHỨNG PHÁP Y',
    'findings.subtitle': 'Xem xét các quan sát an ninh, bằng chứng kỹ thuật pháp y, chuyển đổi vòng đời và kiểm thử lại lỗ hổng.',
    'findings.searchPlaceholder': 'Tìm CVE, điểm cuối, tiêu đề, mã quy tắc...',
    'findings.allSeverities': 'Tất cả mức độ nghiêm trọng',
    'findings.allLifecycle': 'Tất cả trạng thái vòng đời',
    'findings.colSeverity': 'Mức độ',
    'findings.colTitle': 'Tiêu đề lỗ hổng & Quy tắc',
    'findings.colModule': 'Phân hệ Empire',
    'findings.colLocation': 'Vị trí điểm cuối',
    'findings.colLifecycle': 'Vòng đời',
    'findings.evidenceViewer': 'Trình xem bằng chứng tương tác (Interactive Evidence Viewer)',
    'findings.tabRequest': 'Yêu cầu (Request)',
    'findings.tabResponse': 'Phản hồi (Response)',
    'findings.tabHeaders': 'Tiêu đề (Headers)',
    'findings.tabProof': 'Bằng chứng / Nội dung khớp',
    'findings.tabCurl': 'Lệnh cURL tái hiện',
    'findings.copyCurl': 'Sao chép lệnh cURL',
    'findings.retestTarget': 'Kiểm thử lại mục tiêu trực tiếp',
    'findings.retesting': 'Đang kiểm thử lại...',
    'findings.updateStatus': 'Cập nhật trạng thái',
    'findings.lifecycleState': 'Trạng thái vòng đời',
    'findings.assignee': 'Người phụ trách',
    'findings.description': 'Mô tả chi tiết',
    'findings.remediation': 'Khuyến nghị khắc phục',

    // Active Assessments (/active-assessments)
    'active.title': 'GIÁM SÁT ĐÁNH GIÁ THỜI GIAN THỰC',
    'active.subtitle': 'Đo đạc từ xa trực tiếp, luồng nhật ký SSE thời gian thực, tiến trình phân tầng và nút dừng khẩn cấp.',
    'active.queue': 'Hàng đợi tác vụ đánh giá',
    'active.backToScans': 'Quay lại Trung tâm quét',
    'active.cancelAssessment': 'Dừng đánh giá',
    'active.cancelling': 'Đang gửi tín hiệu dừng...',
    'active.liveStream': 'Luồng SSE trực tiếp',
    'active.fallbackPolling': 'Thăm dò dự phòng (Polling)',
    'active.connecting': 'Đang kết nối SSE...',
    'active.stageProgress': 'Tiến độ giai đoạn:',
    'active.terminalTitle': 'scanner_worker_output.log',
    'active.filterLogs': 'Lọc mức nhật ký:',
    'active.allLevels': 'Tất cả mức độ',
    'active.autoScroll': 'Tự cuộn',

    // Scan Center (/scans)
    'scans.title': 'TRUNG TÂM ĐIỀU PHỐI QUÉT',
    'scans.subtitle': 'Khởi chạy bộ quét ProjectDiscovery Nuclei, OWASP ZAP và động cơ Empire chuyên sâu.',
    'scans.dispatchButton': 'Khởi chạy đánh giá mới',
    'scans.activeScans': 'Tiến trình quét đang hoạt động',
    'scans.scanHistory': 'Lịch sử đánh giá',

    // Empire Modules (/empire-modules)
    'modules.title': 'TRUNG TÂM PHÂN HỆ DOANH NGHIỆP EMPIRE',
    'modules.subtitle': 'Cấu trúc 6 phân hệ nghiệp vụ chính của nền tảng Empire với điểm rủi ro Sentinel tổng hợp.',

    // Threat Intel (/threat-intel)
    'intel.title': 'TRUNG TÂM TÌNH BÁO LỖ HỔNG & CVE',
    'intel.subtitle': 'Danh mục lỗ hổng bị khai thác trong thực tế CISA KEV, hệ số rủi ro EPSS và cảnh báo Zero-Day.',
    'intel.syncButton': 'Đồng bộ CISA KEV & NVD',

    // Remediation (/remediation)
    'remediation.title': 'THEO DÕI & KHẮC PHỤC LỖ HỔNG',
    'remediation.subtitle': 'Kiểm soát tiến độ vá lỗi, gán người xử lý và kiểm định lại tính an toàn.',

    // Reports (/reports)
    'reports.title': 'TRUNG TÂM BÁO CÁO BẢO MẬT',
    'reports.subtitle': 'Xuất báo cáo kỹ thuật và quản trị theo định dạng PDF vector, HTML tương tác và JSON pháp y.',
    'reports.generateButton': 'Tạo báo cáo mới',

    // Schedules (/schedules)
    'schedules.title': 'LỊCH QUÉT ĐỊNH KỲ TỰ ĐỘNG',
    'schedules.subtitle': 'Đường ống đánh giá định kỳ tự động hóa theo múi giờ Châu Á/Hồ Chí Minh (02:00 sáng).',
    'schedules.createButton': 'Tạo lịch quét mới',

    // Detection Rules (/detection-rules)
    'rules.title': 'QUẢN LÝ QUY TẮC PHÁT HIỆN',
    'rules.subtitle': 'Quy tắc phát hiện khai báo YAML với xác thực lược đồ, sandbox thử nghiệm và quy trình phê duyệt.',
    'rules.authorNew': 'Soạn quy tắc mới',

    // Integrations (/integrations)
    'integrations.title': 'TÍCH HỢP HỆ THỐNG & CÔNG CỤ NGOÀI',
    'integrations.subtitle': 'Kết nối Nuclei, ZAP, Jira, SIEM, Webhooks và kênh thông báo bảo mật.',

    // System Health (/health)
    'health.title': 'TRẠNG THÁI SỨC KHỎE HỆ THỐNG',
    'health.subtitle': 'Chẩn đoán dịch vụ, mức sử dụng CPU/RAM, kết nối cơ sở dữ liệu và hàng đợi tác vụ.',

    // Settings (/settings)
    'settings.title': 'CÀI ĐẶT HỆ THỐNG NOOSFORGE',
    'settings.subtitle': 'Cấu hình thông số bảo mật, tài khoản quản trị, khóa API và tham số vận hành.',

    // Overview Dashboard (/dashboard)
    'dashboard.title': 'TÌNH BÁO BẢO MẬT NỀN TẢNG EMPIRE',
    'dashboard.subtitle': 'Giám sát rủi ro liên tục, bề mặt tấn công và tình báo lỗ hổng thời gian thực.',
    'dashboard.riskScore': 'Chỉ số rủi ro Sentinel (SRS)',
    'dashboard.posture': 'Tình trạng an ninh:',
    'dashboard.totalTargets': 'Tổng số mục tiêu',
    'dashboard.assessedToday': 'Đã đánh giá hôm nay',
    'dashboard.openFindings': 'Lỗ hổng đang mở',
    'dashboard.criticalFindings': 'Lỗ hổng nghiêm trọng',
    'dashboard.highFindings': 'Lỗ hổng mức độ cao',
    'dashboard.fixedFindings': 'Lỗ hổng đã khắc phục',
    'dashboard.activeAssessments': 'Đánh giá đang chạy',
  },

  en: {
    // Brand & System
    'brand.title': 'NOOSFORGE',
    'brand.subtitle': 'Empire Security SOC Command Center',
    'brand.soc': 'Empire Security SOC',
    'brand.continuousAudit': 'Continuous Audit Active',
    'brand.targetContext': 'Target Context:',
    'brand.version': 'v2.0.0',

    // Navigation
    'nav.overview': 'Security Overview',
    'nav.targets': 'Targets',
    'nav.modules': 'Empire Modules',
    'nav.scans': 'Scan Center',
    'nav.activeAssessments': 'Active Assessments',
    'nav.engineRuns': 'Engine Runs',
    'nav.findings': 'Findings & Evidence',
    'nav.intel': 'Vulnerability Intelligence',
    'nav.remediation': 'Remediation Tracking',
    'nav.reports': 'Reports',
    'nav.schedules': 'Schedules & capacity',
    'nav.users': 'Users & access',
    'nav.rules': 'Detection Rules',
    'nav.integrations': 'Integrations',
    'nav.health': 'System Health',
    'nav.settings': 'Settings',

    // Navigation Groups & Responsive Shell
    'nav.group.core': 'Core Overview',
    'nav.group.inventory': 'Inventory & Scans',
    'nav.group.intelligence': 'Intelligence & Modules',
    'nav.group.governance': 'Governance & System',
    'shell.notifications': 'Security Alerts',
    'shell.markAllRead': 'Mark all as read',
    'shell.noNotifications': 'No unread alerts',
    'shell.alertsCount': '{count} unread alerts',
    'shell.backendOnline': 'API: Online',
    'shell.backendChecking': 'Checking connection...',
    'shell.backendOffline': 'API: Offline',
    'shell.targetLabel': 'Target Context:',
    'shell.targetName': 'Empire Education Platform',
    'shell.scopeBadge': 'SAME-ORIGIN SCOPE',
    'shell.collapseSidebar': 'Collapse Sidebar',
    'shell.expandSidebar': 'Expand Sidebar',
    'shell.menuOpen': 'Open navigation menu',
    'shell.menuClose': 'Close menu',

    // Common Actions & Labels
    'common.search': 'Search...',
    'common.filter': 'Filter',
    'common.refresh': 'Refresh',
    'common.scanNow': 'Scan Now',
    'common.verify': 'Verify Target',
    'common.verified': 'VERIFIED',
    'common.pending': 'PENDING',
    'common.failed': 'FAILED',
    'common.cancel': 'Cancel',
    'common.close': 'Close',
    'common.save': 'Save',
    'common.copy': 'Copy',
    'common.copied': 'Copied!',
    'common.retest': 'Retest Target Live',
    'common.evidence': 'Evidence',
    'common.actions': 'Actions',
    'common.status': 'Status',
    'common.loading': 'Loading data...',
    'common.noData': 'No matching data found.',
    'common.viewDetails': 'View Details',
    'common.download': 'Download',
    'common.submit': 'Submit',
    'common.approve': 'Approve',
    'common.activate': 'Activate',
    'common.delete': 'Delete',
    'common.showing': 'Showing:',
    'common.all': 'All',

    // Severities
    'severity.critical': 'Critical',
    'severity.high': 'High',
    'severity.medium': 'Medium',
    'severity.low': 'Low',
    'severity.info': 'Info',

    // Posture
    'posture.critical': 'Critical',
    'posture.elevated': 'Elevated',
    'posture.moderate': 'Moderate',
    'posture.secure': 'Secure',

    // Target Management (/assets)
    'targets.title': 'EMPIRE TARGET MANAGEMENT',
    'targets.subtitle': 'Register, import, configure, and monitor Empire application attack surface across functional business modules.',
    'targets.bulkImport': 'Bulk Import Targets',
    'targets.registerTarget': 'Register Target',
    'targets.searchPlaceholder': 'Search targets, URLs, technologies...',
    'targets.allModules': 'All Empire Modules',
    'targets.allEnvironments': 'All Environments',
    'targets.colTarget': 'Target & Identifier',
    'targets.colModule': 'Empire Module',
    'targets.colTech': 'Technology Stack',
    'targets.colEnv': 'Environment',
    'targets.colPolicy': 'Approved /media Policy',
    'targets.colStatus': 'Status',
    'targets.colActions': 'Actions',
    'targets.verifyButton': '8-Step Verify',
    'targets.scanButton': 'Scan Now',
    'targets.findingsButton': 'Findings',
    'targets.publicMediaPolicy': 'PUBLIC_BY_DESIGN',
    'targets.standardRestricted': 'Standard Restricted',
    'targets.deleteConfirm': 'Are you sure you want to remove this target from active management?',

    // Verification Modal
    'verify.modalTitle': '8-Step Live Target Verification Pipeline',
    'verify.modalSubtitle': 'Executes the multi-stage live probe sequence: DNS, TLS, HTTP, redirect loops, content discovery, fingerprinting, and security authorization.',
    'verify.executing': 'Executing multi-stage live probe...',
    'verify.executeButton': 'Execute 8-Step Verification',
    'verify.reverifyButton': 'Re-run Verification',
    'verify.step1Title': '1. Input Validation & URL Normalization',
    'verify.step1Desc': 'Verifies URI schema, host parsing, canonical path normalization, and duplicate safety.',
    'verify.step2Title': '2. DNS Resolution (A/AAAA/CNAME)',
    'verify.step2Desc': 'Resolves authoritative IPv4/IPv6 addresses, canonical aliases, and nameservers.',
    'verify.step3Title': '3. TLS/SSL Certificate Verification',
    'verify.step3Desc': 'Validates X.509 certificate trust chains, SAN hostnames, expiration, and cipher suites.',
    'verify.step4Title': '4. HTTP Connectivity & Status Code',
    'verify.step4Desc': 'Initiates bounded probe request, measures latency (ms), and validates HTTP response status.',
    'verify.step5Title': '5. Redirect Inspection & Loop Detection',
    'verify.step5Desc': 'Traces intermediate HTTP redirect hops (301/302) and verifies canonical endpoint safety.',
    'verify.step6Title': '6. Web Discovery & Content Inspection',
    'verify.step6Desc': 'Discovers robots.txt, sitemaps, and verifies baseline HTTP security response headers.',
    'verify.step7Title': '7. Technology Stack Fingerprint',
    'verify.step7Desc': 'Profiles underlying web server, application framework, CDN/WAF headers, and technologies.',
    'verify.step8Title': '8. Policy Verification & Scope Authorization',
    'verify.step8Desc': 'Verifies all probe stages, sets persistent VERIFIED state, and authorizes continuous scans.',
    'verify.pass': 'PASS',
    'verify.probing': 'PROBING...',
    'verify.queued': 'QUEUED',
    'verify.successBadge': '100% PROBE VERIFIED',
    'verify.successDetail': 'Target is authenticated, reachable, and authorized for comprehensive security scanning.',

    // Findings & Evidence (/findings)
    'findings.title': 'FINDINGS CENTER & EVIDENCE',
    'findings.subtitle': 'Review security observations, forensic technical evidence, lifecycle transitions, and retest remediations.',
    'findings.searchPlaceholder': 'Search CVE, endpoint, title, scanner rule...',
    'findings.allSeverities': 'All Severities',
    'findings.allLifecycle': 'All Lifecycle States',
    'findings.colSeverity': 'Severity',
    'findings.colTitle': 'Finding Title & Rule',
    'findings.colModule': 'Empire Module',
    'findings.colLocation': 'Location',
    'findings.colLifecycle': 'Lifecycle',
    'findings.evidenceViewer': 'Interactive Evidence Viewer',
    'findings.tabRequest': 'Request',
    'findings.tabResponse': 'Response',
    'findings.tabHeaders': 'Headers',
    'findings.tabProof': 'Proof / Matched Content',
    'findings.tabCurl': 'Replay cURL',
    'findings.copyCurl': 'Copy cURL Command',
    'findings.retestTarget': 'Retest Target Live',
    'findings.retesting': 'Retesting...',
    'findings.updateStatus': 'Update Status',
    'findings.lifecycleState': 'Lifecycle State',
    'findings.assignee': 'Assignee',
    'findings.description': 'Description',
    'findings.remediation': 'Recommended Remediation',

    // Active Assessments (/active-assessments)
    'active.title': 'LIVE ASSESSMENT TRACKER',
    'active.subtitle': 'Real-time execution telemetry, live SSE log stream, stage progression, and cooperative cancellation controls.',
    'active.queue': 'Assessment Jobs Queue',
    'active.backToScans': 'Back to Scan Center',
    'active.cancelAssessment': 'Cancel Assessment',
    'active.cancelling': 'Cancelling...',
    'active.liveStream': 'Live SSE Stream',
    'active.fallbackPolling': 'Fallback Polling',
    'active.connecting': 'Connecting SSE...',
    'active.stageProgress': 'Stage Progress:',
    'active.terminalTitle': 'scanner_worker_output.log',
    'active.filterLogs': 'Filter log level:',
    'active.allLevels': 'All Levels',
    'active.autoScroll': 'Auto Scroll',

    // Scan Center (/scans)
    'scans.title': 'SCAN DISPATCH CENTER',
    'scans.subtitle': 'Launch ProjectDiscovery Nuclei, OWASP ZAP, and Empire proprietary security engine assessments.',
    'scans.dispatchButton': 'Dispatch New Assessment',
    'scans.activeScans': 'Active Assessment Jobs',
    'scans.scanHistory': 'Assessment History',

    // Empire Modules (/empire-modules)
    'modules.title': 'EMPIRE BUSINESS MODULE HUB',
    'modules.subtitle': 'Architectural mapping of 6 core Empire operational modules with synthesized Sentinel Risk Scores.',

    // Threat Intel (/threat-intel)
    'intel.title': 'VULNERABILITY & THREAT INTELLIGENCE',
    'intel.subtitle': 'Actively exploited CVE catalogue from CISA KEV, EPSS exploitability ratings, and zero-day alerts.',
    'intel.syncButton': 'Sync CISA KEV & NVD',

    // Remediation (/remediation)
    'remediation.title': 'REMEDIATION TRACKING & VERIFICATION',
    'remediation.subtitle': 'Track vulnerability remediation SLAs, assign engineers, and verify retest verdicts.',

    // Reports (/reports)
    'reports.title': 'SECURITY REPORT GENERATOR',
    'reports.subtitle': 'Generate audit-grade technical and executive reports in vector PDF, interactive HTML, and JSON formats.',
    'reports.generateButton': 'Generate New Report',

    // Schedules (/schedules)
    'schedules.title': 'AUTOMATED ASSESSMENT SCHEDULES',
    'schedules.subtitle': 'Recurring automated assessment pipelines in Asia/Ho_Chi_Minh timezone (02:00 AM ICT).',
    'schedules.createButton': 'Create Schedule',

    // Detection Rules (/detection-rules)
    'rules.title': 'DETECTION RULE MANAGER',
    'rules.subtitle': 'Declarative YAML detection rules with schema validation, sandbox fixtures, and review gating.',
    'rules.authorNew': 'Author New Rule',

    // Integrations (/integrations)
    'integrations.title': 'EXTERNAL INTEGRATIONS & ADAPTERS',
    'integrations.subtitle': 'Connect Nuclei, ZAP, Jira, SIEM, Webhooks, and automated security notification channels.',

    // System Health (/health)
    'health.title': 'SYSTEM HEALTH & DIAGNOSTICS',
    'health.subtitle': 'Service diagnostics, CPU/memory utilization, database connectivity, and task queues.',

    // Settings (/settings)
    'settings.title': 'NOOSFORGE SYSTEM SETTINGS',
    'settings.subtitle': 'Configure platform security parameters, credentials, API keys, and operational limits.',

    // Overview Dashboard (/dashboard)
    'dashboard.title': 'EMPIRE SECURITY INTELLIGENCE',
    'dashboard.subtitle': 'Continuous risk monitoring, attack surface correlation, and real-time threat posture.',
    'dashboard.riskScore': 'Sentinel Risk Score (SRS)',
    'dashboard.posture': 'Security Posture:',
    'dashboard.totalTargets': 'Total Targets',
    'dashboard.assessedToday': 'Assessed Today',
    'dashboard.openFindings': 'Open Findings',
    'dashboard.criticalFindings': 'Critical Findings',
    'dashboard.highFindings': 'High Findings',
    'dashboard.fixedFindings': 'Fixed Findings',
    'dashboard.activeAssessments': 'Active Assessments',
  },
};

const I18nContext = createContext<I18nContextType>({
  locale: 'vi',
  setLocale: () => {},
  t: (key: string, fallback?: string) => fallback || key,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>('vi');

  useEffect(() => {
    try {
      const saved = localStorage.getItem('sentinel_locale') as Locale | null;
      if (saved === 'vi' || saved === 'en') {
        setLocaleState(saved);
      }
    } catch (_) {
      // Local storage unavailable or SSR
    }
  }, []);

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale);
    try {
      localStorage.setItem('sentinel_locale', newLocale);
      document.documentElement.lang = newLocale;
    } catch (_) {}
  };

  const t = (key: string, fallback?: string): string => {
    const dict = DICTIONARY[locale] || DICTIONARY.vi;
    if (dict && dict[key]) {
      return dict[key];
    }
    // Fallback to English dictionary if key missing in current
    if (DICTIONARY.en && DICTIONARY.en[key]) {
      return DICTIONARY.en[key];
    }
    return fallback !== undefined ? fallback : key;
  };

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextType {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return context;
}
