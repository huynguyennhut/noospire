"""
Adversarial Stress Test Suite for Milestone 5:
Responsive Shell & Viewport Behavior + UI Primitives Resilience.
"""

import json
import os
import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
SRC_DIR = FRONTEND_DIR / "src"
COMPONENTS_DIR = SRC_DIR / "components"
UI_DIR = COMPONENTS_DIR / "ui"
SHELL_PATH = COMPONENTS_DIR / "layout" / "Shell.tsx"


def test_shell_file_and_reexport_integrity():
    """Verify Shell component exists and is correctly re-exported."""
    assert SHELL_PATH.is_file(), f"Shell.tsx not found at {SHELL_PATH}"
    compat_shell = COMPONENTS_DIR / "Shell.tsx"
    assert compat_shell.is_file(), f"Legacy Shell.tsx re-export not found at {compat_shell}"
    compat_text = compat_shell.read_text(encoding="utf-8")
    assert "export { default } from './layout/Shell'" in compat_text


def test_ui_primitives_exist_and_complete():
    """Verify all core UI primitives required by Milestone 5 exist in components/ui/."""
    expected_primitives = [
        "button.tsx",
        "modal.tsx",
        "table.tsx",
        "badge.tsx",
        "card.tsx",
        "tooltip.tsx",
        "input.tsx",
        "tabs.tsx",
        "stat-card.tsx",
    ]
    for prim in expected_primitives:
        p = UI_DIR / prim
        assert p.is_file(), f"Required UI primitive {prim} is missing from {UI_DIR}"


def test_button_adversarial_contract():
    """Stress test Button implementation contracts."""
    btn_text = (UI_DIR / "button.tsx").read_text(encoding="utf-8")

    # 1. Variant coverage
    variants = ["primary", "secondary", "destructive", "outline", "ghost", "glass"]
    for v in variants:
        assert f"'{v}'" in btn_text, f"Variant '{v}' missing from Button"

    # 2. Size coverage
    sizes = ["sm", "md", "lg", "icon"]
    for s in sizes:
        assert f"'{s}'" in btn_text, f"Size '{s}' missing from Button"

    # 3. Loading state and spinner
    assert "disabled={disabled || loading}" in btn_text
    assert "Loader2" in btn_text
    assert "animate-spin" in btn_text

    # 4. Ref forwarding
    assert "React.forwardRef<HTMLButtonElement, ButtonProps>" in btn_text

    # 5. Accessibility and interaction disabled classes
    assert "disabled:opacity-50" in btn_text
    assert "disabled:pointer-events-none" in btn_text


def test_modal_adversarial_contract():
    """Stress test Modal accessibility, portal mounting, and scroll lock."""
    modal_text = (UI_DIR / "modal.tsx").read_text(encoding="utf-8")

    # 1. React Portal to document.body
    assert "createPortal(modalNode, document.body)" in modal_text

    # 2. SSR mounted guard to avoid hydration mismatch
    assert "const [mounted, setMounted] = React.useState(false)" in modal_text
    assert "if (!mounted || !isOpen) return null" in modal_text

    # 3. Dialog accessibility
    assert 'role="dialog"' in modal_text
    assert 'aria-modal="true"' in modal_text

    # 4. Escape key listener and unmount cleanup
    assert "e.key === 'Escape'" in modal_text
    assert "window.removeEventListener('keydown', handleKeyDown)" in modal_text

    # 5. Body scroll lock and restoration
    assert "document.body.style.overflow = 'hidden'" in modal_text
    assert "document.body.style.overflow = originalStyle" in modal_text

    # 6. Backdrop dismissal and content event stopPropagation
    assert "closeOnBackdrop" in modal_text
    assert "e.stopPropagation()" in modal_text


def test_table_adversarial_contract():
    """Stress test Table responsive layout, horizontal overflow, and empty state."""
    table_text = (UI_DIR / "table.tsx").read_text(encoding="utf-8")

    # 1. Overflow container
    assert "overflow-x-auto" in table_text

    # 2. Subcomponents
    subcomponents = [
        "Table",
        "TableHeader",
        "TableBody",
        "TableFooter",
        "TableRow",
        "TableHead",
        "TableCell",
        "TableCaption",
        "TableEmpty",
    ]
    for sub in subcomponents:
        assert f"export const {sub}" in table_text or f"export interface {sub}" in table_text

    # 3. Whitespace nowrap on headers
    assert "whitespace-nowrap" in table_text


def test_responsive_shell_mobile_contract():
    """Stress test Mobile (< 768px) Shell specifications."""
    shell_text = SHELL_PATH.read_text(encoding="utf-8")

    # 1. Mobile top bar exclusivity
    assert "md:hidden sticky top-0" in shell_text
    assert "h-14" in shell_text

    # 2. Hamburger button accessibility
    assert "aria-expanded={mobileMenuOpen}" in shell_text
    assert "aria-label=" in shell_text

    # 3. Slide-over drawer dimensions and slide transition
    assert "w-80 max-w-[85vw]" in shell_text
    assert "translate-x-0" in shell_text
    assert "-translate-x-full" in shell_text
    assert "backdrop-blur-md" in shell_text

    # 4. Touch target WCAG minimum 44px height
    assert "min-h-[44px]" in shell_text

    # 5. Navigation link auto-dismisses drawer
    assert "onClick={() => setMobileMenuOpen(false)}" in shell_text

    # 6. Body scroll lock on mobile
    assert "document.body.style.overflow = 'hidden'" in shell_text
    assert "document.body.style.overflow = ''" in shell_text


def test_responsive_shell_tablet_contract():
    """Stress test Tablet (768px - 1024px) collapsible sidebar specifications."""
    shell_text = SHELL_PATH.read_text(encoding="utf-8")

    # 1. Breakpoint visibility and dynamic width transition
    assert "hidden md:flex" in shell_text
    assert "sidebarCollapsed ? 'w-20' : 'w-64'" in shell_text

    # 2. LocalStorage persistence with try-catch safety
    assert "localStorage.getItem('sentinel_sidebar_collapsed')" in shell_text
    assert "localStorage.setItem('sentinel_sidebar_collapsed'" in shell_text
    assert "try {" in shell_text
    assert "catch (_)" in shell_text

    # 3. Tooltip titles on collapsed state
    assert "title={sidebarCollapsed ? translatedName : undefined}" in shell_text


def test_responsive_shell_desktop_contract():
    """Stress test Desktop (> 1024px) Shell specifications."""
    shell_text = SHELL_PATH.read_text(encoding="utf-8")

    # 1. Sticky layout
    assert "sticky top-0 h-screen" in shell_text
    assert "hidden md:flex sticky top-0 z-30" in shell_text

    # 2. Notification popover outside click and ESC dismissal
    assert "notificationsOpen" in shell_text
    assert "notificationsRef" in shell_text
    assert "handleClickOutside" in shell_text
    assert "markAllAlertsRead" in shell_text

    # 3. Bilingual toggle switches
    assert "setLocale('vi')" in shell_text
    assert "setLocale('en')" in shell_text


def test_shell_14_views_routing_taxonomy():
    """Verify all 14 SaaS views are registered in navigation taxonomy."""
    shell_text = SHELL_PATH.read_text(encoding="utf-8")

    expected_routes = [
        "/dashboard",
        "/assets",
        "/scans",
        "/active-assessments",
        "/schedules",
        "/empire-modules",
        "/findings",
        "/threat-intel",
        "/remediation",
        "/detection-rules",
        "/reports",
        "/integrations",
        "/health",
        "/settings",
    ]
    for r in expected_routes:
        assert f"href: '{r}'" in shell_text, f"Route {r} not registered in Shell navigation"
