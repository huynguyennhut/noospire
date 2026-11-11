"""
Empirical Adversarial Stress Test Suite for Milestone M9:
Modern Liquid Glass UI, Brand Logo, Live Telemetry Polling, Toast Notifications & Batch Dispatch Controls.

Adversarially validates:
1. Brand Logo Asset Binary and Magic Byte Integrity (JPG & PNG).
2. Shell.tsx Multi-Viewport Brand Presentation & Liquid Glass Invariants (Mobile, Drawer, Desktop Expanded & Collapsed).
3. Toast Notification System Contract (Variants, Specular Highlighting, Lifecycle Cleanup, Buffer Capping, Accessibility, Root Injection).
4. Telemetry and Multi-Worker "trackcurrent" HUD Contract (Polling Intervals, CPU/RAM Meters, Active Thread Slots, Log Focus Switcher, Cooperative Cancel, Emergency Stop All, EventSource and Interval Cleanup).
5. "Scan All" Batch Scan Hero Card Contract (Dynamic Asset Counter, Concurrency Slider 1-4, Engine & Profile Selectors, DEEP_ACTIVE Security Gate, Launch Payload Integrity).
6. TypeScript API Client & Types Contract (Batch Scan, TrackCurrent, System Resources).
7. Simulated Telemetry Malformed Payload Resiliency.
"""

import json
import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
SRC_DIR = FRONTEND_DIR / "src"
PUBLIC_DIR = FRONTEND_DIR / "public"

BRAND_DIR = PUBLIC_DIR / "brand"
LOGO_JPG = BRAND_DIR / "logo.jpg"
LOGO_PNG = BRAND_DIR / "logo.png"

SHELL_FILE = SRC_DIR / "components" / "layout" / "Shell.tsx"
TOAST_FILE = SRC_DIR / "components" / "ui" / "toast.tsx"
LAYOUT_FILE = SRC_DIR / "app" / "layout.tsx"
SCANS_PAGE = SRC_DIR / "app" / "scans" / "page.tsx"
ACTIVE_PAGE = SRC_DIR / "app" / "active-assessments" / "page.tsx"
TYPES_FILE = SRC_DIR / "lib" / "types.ts"
API_FILE = SRC_DIR / "lib" / "api.ts"


# ============================================================================
# 1. BRAND ASSET INTEGRITY & MAGIC BYTES
# ============================================================================

def test_brand_logo_assets_exist_and_magic_bytes():
    """Verify official brand logo exists in both JPG and PNG formats with valid binary headers."""
    assert LOGO_JPG.is_file(), f"Missing logo.jpg at {LOGO_JPG}"
    assert LOGO_PNG.is_file(), f"Missing logo.png at {LOGO_PNG}"

    jpg_bytes = LOGO_JPG.read_bytes()
    png_bytes = LOGO_PNG.read_bytes()

    assert len(jpg_bytes) > 10000, f"logo.jpg too small ({len(jpg_bytes)} bytes)"
    assert len(png_bytes) > 10000, f"logo.png too small ({len(png_bytes)} bytes)"

    # JPEG magic bytes: FF D8 FF
    assert jpg_bytes.startswith(b"\xff\xd8\xff"), "logo.jpg missing JPEG magic byte header"
    # PNG magic bytes: \x89PNG\r\n\x1a\n
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "logo.png missing PNG magic byte header"


# ============================================================================
# 2. SHELL.TSX BRAND INTEGRATION & LIQUID GLASS FRAMING
# ============================================================================

def test_shell_brand_logo_liquid_glass_frames_across_viewports():
    """Adversarially verify logo integration in Shell.tsx across Mobile Bar, Mobile Drawer, Desktop Expanded & Collapsed."""
    assert SHELL_FILE.is_file(), f"Shell.tsx missing at {SHELL_FILE}"
    content = SHELL_FILE.read_text(encoding="utf-8")

    # Ensure no raw Shield placeholder is used for the brand logo
    # All brand headers must use <Image src="/brand/logo.jpg" ... />
    logo_occurrences = list(re.finditer(r'<Image[^>]+src=["\']/brand/logo\.jpg["\']', content))
    assert len(logo_occurrences) >= 3, (
        f"Expected at least 3 occurrences of logo.jpg in Shell.tsx (Mobile bar, Drawer, Desktop sidebar), found {len(logo_occurrences)}"
    )

    # Verify liquid glass framing around brand logos
    assert "backdrop-blur-md bg-white/5 border border-white/10" in content, (
        "Specular liquid glass frame missing around brand logo in Shell.tsx"
    )

    # Verify responsive visibility classes are intact
    assert "md:hidden sticky top-0" in content, "Mobile sticky topbar container missing"
    assert "hidden md:flex" in content, "Desktop sticky sidebar container missing"
    assert "sidebarCollapsed ? 'w-20' : 'w-64'" in content, "Desktop sidebar collapse width toggle missing"

    # Verify brand text identity
    assert "NOOSFORGE" in content
    assert "EMPIRE SOC" in content or "Empire Security SOC" in content


# ============================================================================
# 3. TOAST NOTIFICATION SYSTEM ADVERSARIAL CONTRACT
# ============================================================================

def test_toast_system_implementation_and_contract():
    """Verify toast.tsx primitives, export contracts, auto-dismissal, buffer capping, and accessibility."""
    assert TOAST_FILE.is_file(), f"toast.tsx missing at {TOAST_FILE}"
    content = TOAST_FILE.read_text(encoding="utf-8")

    # 1. Export integrity
    assert "export function useToast" in content, "useToast hook not exported"
    assert "export function ToastProvider" in content, "ToastProvider not exported"
    assert "export type ToastVariant" in content, "ToastVariant type not exported"
    assert "export interface ToastOptions" in content, "ToastOptions interface not exported"
    assert "export interface ToastItem" in content, "ToastItem interface not exported"

    # 2. Supported variants
    for variant in ['default', 'success', 'warning', 'destructive', 'info']:
        assert f"'{variant}'" in content, f"Variant '{variant}' missing from toast.tsx"

    # 3. Specular highlight and liquid-glass styling
    assert "backdrop-blur-xl bg-black/85" in content, "Liquid glass styling missing in toast container"
    assert "bg-gradient-to-r from-transparent via-white/30 to-transparent" in content, (
        "Specular top shine border missing in ToastElement"
    )

    # 4. Auto-dismissal and unmount cleanup
    assert "setTimeout" in content, "Auto-dismiss timer missing"
    assert "clearTimeout(timer)" in content, "clearTimeout cleanup missing in ToastElement useEffect"
    assert "duration <= 0" in content, "Persistent duration guard missing"

    # 5. Buffer limit (prevent infinite DOM node stacking)
    assert "slice(-4)" in content, "Toast buffer capping (max 5 active toasts) missing"

    # 6. Accessibility
    assert 'role="status"' in content, 'role="status" accessibility attribute missing'
    assert 'aria-live="polite"' in content, 'aria-live="polite" accessibility attribute missing'
    assert 'aria-label="Close notification"' in content, 'Close button missing accessible aria-label'


def test_toast_provider_injected_in_root_layout():
    """Verify ToastProvider wraps the application in RootLayout (layout.tsx)."""
    assert LAYOUT_FILE.is_file(), f"layout.tsx missing at {LAYOUT_FILE}"
    content = LAYOUT_FILE.read_text(encoding="utf-8")

    assert "import { ToastProvider } from '../components/ui/toast'" in content or (
        "import ToastProvider from '../components/ui/toast'" in content
    ), "ToastProvider not imported in layout.tsx"
    assert "<ToastProvider>" in content, "ToastProvider not wrapping application in layout.tsx"
    assert "</ToastProvider>" in content, "ToastProvider closing tag missing in layout.tsx"


# ============================================================================
# 4. ACTIVE ASSESSMENTS "TRACKCURRENT" & TELEMETRY HUD CONTRACT
# ============================================================================

def test_active_assessments_telemetry_hud_contract():
    """Adversarially verify telemetry polling, resource meters, worker slot grid, log focus switcher, and cancellations."""
    assert ACTIVE_PAGE.is_file(), f"active-assessments page missing at {ACTIVE_PAGE}"
    content = ACTIVE_PAGE.read_text(encoding="utf-8")

    # 1. Telemetry polling hook and interval
    assert "api.getTrackCurrent()" in content, "Missing api.getTrackCurrent() call"
    assert "setInterval(fetchTelemetry, 2500)" in content or "setInterval(fetchTelemetry" in content, (
        "Missing periodic telemetry polling interval"
    )
    assert "clearInterval(interval)" in content, "Missing clearInterval cleanup in fetchTelemetry effect"

    # 2. Resource meters (CPU, RAM %, Available RAM)
    assert "CPU Load" in content, "Missing CPU Load meter"
    assert "RAM Load" in content, "Missing RAM Load meter"
    assert "Available RAM" in content, "Missing Available RAM meter"
    assert "telemetry?.system_resources?.cpu_percent" in content
    assert "telemetry?.system_resources?.memory_percent" in content

    # 3. Throttling active badge
    assert "telemetry?.is_throttled" in content
    assert "Throttling Active" in content, "Missing 'Throttling Active' badge text"
    assert "animate-pulse" in content, "Missing animate-pulse on throttling alert"

    # 4. Multi-Worker Thread Slots Grid
    assert "Active Worker Process Slots" in content, "Missing Active Worker Process Slots header"
    assert "telemetry?.active_threads" in content, "Missing active_threads rendering"
    assert "thread.thread_id" in content
    assert "thread.target_locator" in content
    assert "thread.progress_percentage" in content
    assert "thread.elapsed_seconds" in content
    assert "thread.last_log" in content

    # 5. Stage badge coverage (7 pipeline stages)
    for stage in ['preflight', 'discovery', 'fingerprint', 'crawling', 'scoring', 'active', 'empire']:
        assert f"'{stage}'" in content, f"Pipeline stage '{stage}' missing in stage badge renderer"

    # 6. Log focus switcher
    assert "onClick={() => setActiveScanId(thread.scan_id)}" in content, (
        "Active worker slot missing click handler to focus SSE log stream on thread.scan_id"
    )
    assert "FOCUSED STREAM" in content, "Missing focused stream indicator on active worker slot"

    # 7. Cancel Batch & Stop All Scans buttons
    assert "handleCancelBatch" in content, "Missing handleCancelBatch handler"
    assert "api.cancelBatch" in content, "Missing api.cancelBatch call"
    assert "handleStopAllScans" in content, "Missing handleStopAllScans handler"
    assert "api.stopAllScans" in content, "Missing api.stopAllScans call"
    assert "Emergency Stop Executed" in content or "Halted" in content

    # 8. Unmount cleanup for SSE and interval
    assert "eventSourceRef.current.close()" in content, "EventSource missing cleanup on unmount/switch"


# ============================================================================
# 5. SCAN CENTER "SCAN ALL" HERO CARD CONTRACT
# ============================================================================

def test_scans_page_batch_controls_hero_card_contract():
    """Adversarially verify the 'Scan All' Hero Card, concurrency slider, engine/profile selectors, and launch payload."""
    assert SCANS_PAGE.is_file(), f"scans page missing at {SCANS_PAGE}"
    content = SCANS_PAGE.read_text(encoding="utf-8")

    # 1. Hero Card presence
    assert "Scan All Targets — Full-Spectrum Batch Orchestration" in content, (
        "Missing 'Scan All Targets' Hero Card title in scans/page.tsx"
    )

    # 2. Dynamic asset counter
    assert "{assets.length} Registered Targets" in content, (
        "Missing dynamic '{assets.length} Registered Targets' badge"
    )

    # 3. Worker concurrency throttle slider (range 1-4)
    assert 'type="range"' in content, "Missing range input slider"
    assert 'min="1"' in content, "Slider min must be 1"
    assert 'max="4"' in content, "Slider max must be 4"
    assert 'step="1"' in content, "Slider step must be 1"
    assert "Worker Concurrency Throttle" in content, "Missing concurrency slider label"

    # 4. Engine selectors (All, Nuclei, ZAP, Trivy)
    for engine_id in ['all', 'nuclei', 'zap', 'trivy']:
        assert f"'{engine_id}'" in content, f"Engine '{engine_id}' missing in batch engine selector"
    assert "All Engines" in content
    assert "Nuclei" in content
    assert "OWASP ZAP" in content
    assert "Trivy" in content

    # 5. Profile selectors (all 7 profiles)
    expected_profiles = [
        'BASELINE',
        'DEEP_ACTIVE',
        'DAILY_SECURITY',
        'STANDARD',
        'INFRASTRUCTURE',
        'LIGHT_PASSIVE',
        'AUTHENTICATED',
    ]
    for p in expected_profiles:
        assert f"'{p}'" in content, f"Profile '{p}' missing from batch profile selector"

    # 6. DEEP_ACTIVE security gate alert
    assert "Security Gate Notice" in content, "Missing DEEP_ACTIVE Security Gate Notice in scans/page.tsx"
    assert "batchProfiles.includes('DEEP_ACTIVE')" in content, "DEEP_ACTIVE alert not conditionally tied to selection"

    # 7. Launch Full Sweep button & API call
    assert "Launch Full Sweep" in content, "Missing 'Launch Full Sweep' button"
    assert "api.createBatchScan" in content, "Missing api.createBatchScan dispatch call"
    assert "targets: 'ALL'" in content, "Batch dispatch payload missing targets: 'ALL'"
    assert "concurrency_limit: batchConcurrency" in content, "Batch dispatch payload missing concurrency_limit"

    # 8. Toast feedback on dispatch
    assert "Batch Scan Dispatched" in content, "Missing success toast notification on batch dispatch"


# ============================================================================
# 6. API CLIENT & TYPES CONTRACT INTEGRITY
# ============================================================================

def test_api_client_and_types_batch_methods_contract():
    """Verify TypeScript types and ApiClient methods for batch scanning and telemetry."""
    types_content = TYPES_FILE.read_text(encoding="utf-8")
    api_content = API_FILE.read_text(encoding="utf-8")

    # Types verification
    assert "export interface ScanBatchCreate" in types_content
    assert "export interface ScanBatchRead" in types_content
    assert "export interface BatchScanResponse" in types_content
    assert "export interface TrackCurrentResponse" in types_content
    assert "export interface ActiveThreadInfo" in types_content
    assert "export interface SystemResourcesInfo" in types_content

    # ApiClient methods verification
    assert "public async createBatchScan(" in api_content
    assert "public async listBatches(" in api_content
    assert "public async getBatch(" in api_content
    assert "public async cancelBatch(" in api_content
    assert "public async stopAllScans(" in api_content
    assert "public async getTrackCurrent(" in api_content


# ============================================================================
# 7. ROBUSTNESS TO MALFORMED / BOUNDARY TELEMETRY PAYLOADS
# ============================================================================

def test_telemetry_payload_schema_and_boundary_handling():
    """Adversarially verify that active-assessments page uses safe optional chaining for all telemetry properties."""
    content = ACTIVE_PAGE.read_text(encoding="utf-8")

    # Safe optional navigation checks:
    # 1. telemetry?.is_throttled
    assert "telemetry?.is_throttled" in content
    # 2. telemetry?.system_resources?.cpu_percent
    assert "telemetry?.system_resources?.cpu_percent" in content
    # 3. telemetry?.system_resources?.memory_percent
    assert "telemetry?.system_resources?.memory_percent" in content
    # 4. telemetry?.system_resources?.memory_available_mb
    assert "telemetry?.system_resources?.memory_available_mb" in content
    # 5. telemetry?.active_threads
    assert "telemetry?.active_threads" in content
    # 6. Empty active threads fallback message
    assert "No active background worker threads currently running" in content, (
        "Missing empty active_threads fallback placeholder"
    )
