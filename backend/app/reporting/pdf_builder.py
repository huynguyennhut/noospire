"""ReportLab PDF Builder for Noosforge Sentinel.

Generates audit-grade Technical Security Assessment and Executive Summary
reports in vector PDF format using ReportLab 5.1.0.
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Brand Color Palette (Cyber-Slate & SOC Theme)
NAVY_PRIMARY = colors.HexColor("#070B14")
NAVY_SURFACE = colors.HexColor("#0E1526")
BORDER_SUBTLE = colors.HexColor("#1F2E4D")
BORDER_STRONG = colors.HexColor("#2D426B")
TEXT_MUTED = colors.HexColor("#64748B")
TEXT_BODY = colors.HexColor("#1E293B")
TEXT_WHITE = colors.HexColor("#F8FAFC")
ACCENT_CYAN = colors.HexColor("#06B6D4")
ACCENT_BLUE = colors.HexColor("#3B82F6")

# Normalized Severity Colors
COLOR_CRITICAL = colors.HexColor("#EF4444")
COLOR_HIGH = colors.HexColor("#F97316")
COLOR_MEDIUM = colors.HexColor("#F59E0B")
COLOR_LOW = colors.HexColor("#10B981")
COLOR_INFO = colors.HexColor("#06B6D4")


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas that computes and draws the exact total page count,

    running header, and running footer.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, page_count: int) -> None:
        if self._pageNumber == 1:
            # Suppress header and footer on cover page
            return

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(TEXT_MUTED)

        # Running Header
        self.drawString(54, 755, "NOOSFORGE SENTINEL — SECURITY ASSESSMENT REPORT")
        self.drawRightString(558, 755, "CONFIDENTIAL")
        self.setStrokeColor(BORDER_SUBTLE)
        self.setLineWidth(0.75)
        self.line(54, 747, 558, 747)

        # Running Footer
        self.setStrokeColor(BORDER_SUBTLE)
        self.setLineWidth(0.75)
        self.line(54, 45, 558, 45)
        self.setFont("Helvetica", 8)
        self.drawString(54, 32, "CONFIDENTIAL & PROPRIETARY — FOR AUTHORIZED RECIPIENTS ONLY")
        self.drawRightString(558, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


class ReportLabPDFBuilder:
    """Vector PDF generator implementing strict zero-fabrication reporting."""

    def __init__(self, report_data: Dict[str, Any]) -> None:
        self.data = report_data
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self) -> None:
        # Title Styles
        self.styles.add(
            ParagraphStyle(
                name="CoverTitle",
                fontName="Helvetica-Bold",
                fontSize=26,
                leading=32,
                textColor=NAVY_SURFACE,
                spaceAfter=8,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="CoverSubtitle",
                fontName="Helvetica-Bold",
                fontSize=14,
                leading=18,
                textColor=ACCENT_CYAN,
                spaceAfter=20,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="CoverMeta",
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=TEXT_MUTED,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="SectionHeading",
                fontName="Helvetica-Bold",
                fontSize=16,
                leading=20,
                textColor=NAVY_SURFACE,
                spaceBefore=16,
                spaceAfter=8,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="SubSectionHeading",
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=16,
                textColor=BORDER_STRONG,
                spaceBefore=10,
                spaceAfter=4,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="ReportBody",
                fontName="Helvetica",
                fontSize=9,
                leading=13,
                textColor=TEXT_BODY,
                spaceAfter=6,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="EvidenceCode",
                fontName="Courier",
                fontSize=7.5,
                leading=10,
                textColor=colors.HexColor("#0F172A"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="BadgeText",
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=TEXT_WHITE,
                alignment=1,  # Center
            )
        )

    def _get_severity_color(self, severity: str) -> colors.Color:
        sev = severity.upper()
        if sev == "CRITICAL":
            return COLOR_CRITICAL
        elif sev == "HIGH":
            return COLOR_HIGH
        elif sev == "MEDIUM":
            return COLOR_MEDIUM
        elif sev == "LOW":
            return COLOR_LOW
        return COLOR_INFO

    def build_pdf(self, output_path: str) -> str:
        """Builds and writes the PDF file to disk."""
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        story: List[Any] = []

        # 1. Cover Page
        self._add_cover_page(story)
        story.append(PageBreak())

        # 2. Executive Summary & Key Risk Indicators
        self._add_executive_summary(story)

        # 3. Findings Ledger Summary Table
        self._add_findings_summary_table(story)

        # 4. Detailed Findings Dossiers (If Technical Report)
        report_type = self.data.get("report_type", "technical")
        if report_type == "technical":
            story.append(PageBreak())
            self._add_technical_dossiers(story)
        else:
            self._add_strategic_recommendations(story)

        # 5. Coverage Gaps & Exclusions
        self._add_coverage_gaps_section(story)

        # Build Document
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        doc.build(story, canvasmaker=NumberedCanvas)
        return output_path

    def _add_cover_page(self, story: List[Any]) -> None:
        story.append(Spacer(1, 40))

        # Brand Banner
        brand_table = Table(
            [[Paragraph("NOOSFORGE SENTINEL", self.styles["CoverSubtitle"])]],
            colWidths=[504],
        )
        brand_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), NAVY_PRIMARY),
                    ("PADDING", (0, 0), (-1, -1), 12),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(brand_table)
        story.append(Spacer(1, 24))

        # Title
        title_text = self.data.get("title", "Security Assessment Report")
        story.append(Paragraph(title_text, self.styles["CoverTitle"]))

        report_type = self.data.get("report_type", "technical").capitalize()
        story.append(
            Paragraph(
                f"{report_type} Security Assessment & Continuous Intelligence Audit",
                self.styles["CoverSubtitle"],
            )
        )
        story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT_CYAN, spaceAfter=20))

        # Engagement Metadata Table
        meta_data = [
            [
                Paragraph("<b>Target Scope:</b>", self.styles["CoverMeta"]),
                Paragraph(str(self.data.get("target_scope", "All Assets")), self.styles["CoverMeta"]),
            ],
            [
                Paragraph("<b>Generated Timestamp:</b>", self.styles["CoverMeta"]),
                Paragraph(str(self.data.get("generated_at", datetime.now(timezone.utc).isoformat())), self.styles["CoverMeta"]),
            ],
            [
                Paragraph("<b>Classification:</b>", self.styles["CoverMeta"]),
                Paragraph("CONFIDENTIAL // PROPRIETARY AUDIT", self.styles["CoverMeta"]),
            ],
            [
                Paragraph("<b>Assessment Engine:</b>", self.styles["CoverMeta"]),
                Paragraph("Noosforge Sentinel Multi-Engine Orchestrator (Nuclei, ZAP, Trivy)", self.styles["CoverMeta"]),
            ],
            [
                Paragraph("<b>Prepared For:</b>", self.styles["CoverMeta"]),
                Paragraph(str(self.data.get("organization", "Enterprise Cybersecurity Customer")), self.styles["CoverMeta"]),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[150, 354])
        meta_table.setStyle(
            TableStyle(
                [
                    ("PADDING", (0, 0), (-1, -1), 6),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER_SUBTLE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(meta_table)
        story.append(Spacer(1, 30))

        # High Level Severity Distribution Card
        summary = self.data.get("risk_summary", {})
        sev_counts = [
            ("CRITICAL", summary.get("critical_count", 0), COLOR_CRITICAL),
            ("HIGH", summary.get("high_count", 0), COLOR_HIGH),
            ("MEDIUM", summary.get("medium_count", 0), COLOR_MEDIUM),
            ("LOW", summary.get("low_count", 0), COLOR_LOW),
            ("INFO", summary.get("info_count", 0), COLOR_INFO),
        ]

        stat_row = []
        for name, count, col in sev_counts:
            cell_content = [
                Paragraph(f"<font color='white'><b>{name}</b></font>", self.styles["BadgeText"]),
                Spacer(1, 4),
                Paragraph(f"<font color='white'><b><font size='14'>{count}</font></b></font>", self.styles["BadgeText"]),
            ]
            stat_row.append(cell_content)

        stats_table = Table([stat_row], colWidths=[100.8] * 5)
        stat_styles = [("PADDING", (0, 0), (-1, -1), 8), ("ALIGN", (0, 0), (-1, -1), "CENTER")]
        for idx, (_, _, col) in enumerate(sev_counts):
            stat_styles.append(("BACKGROUND", (idx, 0), (idx, 0), col))
        stats_table.setStyle(TableStyle(stat_styles))
        story.append(stats_table)

    def _add_executive_summary(self, story: List[Any]) -> None:
        story.append(Paragraph("1. Executive Security Posture", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_SUBTLE, spaceAfter=12))

        summary = self.data.get("risk_summary", {})
        posture = summary.get("risk_posture", "ELEVATED")
        score = summary.get("overall_risk_score", 0.0)

        posture_text = (
            f"The overall organizational security posture for <b>{self.data.get('target_scope', 'the target environment')}</b> "
            f"has been evaluated at <b>Sentinel Risk Index: {score:.1f}/100</b> ({posture}). "
            f"A total of <b>{summary.get('total_findings', 0)} normalized security findings</b> were verified across "
            f"active automated scan runs and threat intelligence correlations. "
            f"Notably, <b>{summary.get('cisa_kev_count', 0)}</b> vulnerabilities match active entries in the <b>CISA Known Exploited Vulnerabilities (KEV)</b> catalog, "
            f"and <b>{summary.get('high_epss_count', 0)}</b> items exhibit an <b>EPSS exploitation probability > 50%</b>."
        )
        story.append(Paragraph(posture_text, self.styles["ReportBody"]))
        story.append(Spacer(1, 12))

    def _add_findings_summary_table(self, story: List[Any]) -> None:
        story.append(Paragraph("2. Findings Ledger Summary", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_SUBTLE, spaceAfter=8))

        findings = self.data.get("findings", [])
        if not findings:
            story.append(Paragraph("<i>No security vulnerabilities identified in the selected scope.</i>", self.styles["ReportBody"]))
            return

        headers = ["Severity", "Title", "Engine", "CVE / Rule ID", "Status"]
        rows = [[
            Paragraph(f"<b>{h}</b>", self.styles["ReportBody"]) for h in headers
        ]]

        for f in findings:
            sev = f.get("severity", "INFO")
            sev_col = self._get_severity_color(sev)
            badge = Table(
                [[Paragraph(f"<font color='white'><b>{sev}</b></font>", self.styles["BadgeText"])]],
                colWidths=[65],
            )
            badge.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), sev_col),
                ("PADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))

            cve = f.get("cve_id") or f.get("scanner_rule_id", "N/A")
            rows.append([
                badge,
                Paragraph(f"<b>{f.get('title', 'Unknown')}</b>", self.styles["ReportBody"]),
                Paragraph(str(f.get("scanner_engine", "nuclei")), self.styles["ReportBody"]),
                Paragraph(f"<font size='8'>{cve}</font>", self.styles["ReportBody"]),
                Paragraph(str(f.get("status", "OPEN")), self.styles["ReportBody"]),
            ])

        table = Table(rows, colWidths=[75, 190, 75, 104, 60])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("PADDING", (0, 0), (-1, -1), 5),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_SUBTLE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 16))

    def _add_technical_dossiers(self, story: List[Any]) -> None:
        story.append(Paragraph("3. Detailed Vulnerability Dossiers", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_SUBTLE, spaceAfter=12))

        findings = self.data.get("findings", [])
        for idx, f in enumerate(findings, 1):
            dossier_items: List[Any] = []

            sev = f.get("severity", "INFO")
            sev_col = self._get_severity_color(sev)

            # Title Header with Badge
            title_p = Paragraph(f"<b>{idx}. {f.get('title', 'Security Finding')}</b>", self.styles["SubSectionHeading"])
            badge = Table(
                [[Paragraph(f"<font color='white'><b>{sev}</b></font>", self.styles["BadgeText"])]],
                colWidths=[65],
            )
            badge.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), sev_col),
                ("PADDING", (0, 0), (-1, -1), 2),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))

            head_table = Table([[title_p, badge]], colWidths=[430, 74])
            head_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            dossier_items.append(head_table)
            dossier_items.append(Spacer(1, 4))

            # Forensics Meta
            cvss = f.get("cvss_score")
            epss = f.get("epss_score")
            cve = f.get("cve_id") or "N/A"
            loc = f.get("target_location", "Unknown")

            cvss_str = f"{cvss:.1f}" if cvss is not None else "N/A"
            epss_str = f"{epss * 100:.1f}%" if epss is not None else "N/A"
            kev_str = "YES (Active Weaponization)" if f.get("is_kev") else "No"

            meta_details = (
                f"<b>Location:</b> {loc}<br/>"
                f"<b>Identifier:</b> {cve} | <b>CVSS v3.1:</b> {cvss_str} | <b>EPSS Probability:</b> {epss_str} | <b>CISA KEV:</b> {kev_str}<br/>"
                f"<b>Scanner Provenance:</b> {f.get('scanner_engine', 'nuclei')} ({f.get('scanner_rule_id', 'custom')})"
            )
            dossier_items.append(Paragraph(meta_details, self.styles["ReportBody"]))

            # Description
            desc = f.get("description", "No description available.")
            dossier_items.append(Paragraph(f"<b>Description:</b> {desc}", self.styles["ReportBody"]))

            # Evidence / Proof of Concept
            evidence = f.get("evidence", {})
            evidence_str = ""
            if isinstance(evidence, dict):
                req = evidence.get("request")
                resp = evidence.get("response")
                matched = evidence.get("matched_content") or evidence.get("curl_command")
                if req:
                    evidence_str += f"REQUEST:\n{req}\n\n"
                if resp:
                    evidence_str += f"RESPONSE SNIPPET:\n{resp[:400]}...\n\n"
                if matched:
                    evidence_str += f"MATCHED CONTENT:\n{matched}\n"
            if not evidence_str and f.get("raw_payload"):
                evidence_str = str(f.get("raw_payload"))

            if evidence_str:
                dossier_items.append(Spacer(1, 4))
                dossier_items.append(Paragraph("<b>Forensic Evidence:</b>", self.styles["ReportBody"]))
                # Sanitize HTML tags in evidence
                clean_ev = evidence_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                ev_p = Paragraph(f"<font color='#0F172A'><pre>{clean_ev[:800]}</pre></font>", self.styles["EvidenceCode"])
                ev_table = Table([[ev_p]], colWidths=[504])
                ev_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                            ("PADDING", (0, 0), (-1, -1), 6),
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ]
                    )
                )
                dossier_items.append(ev_table)

            # Remediation Guidance
            rem = f.get("remediation")
            if rem:
                dossier_items.append(Spacer(1, 4))
                dossier_items.append(Paragraph(f"<b>Remediation Guidance:</b> {rem}", self.styles["ReportBody"]))

            dossier_items.append(Spacer(1, 8))
            dossier_items.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=8))
            story.append(KeepTogether(dossier_items))

    def _add_strategic_recommendations(self, story: List[Any]) -> None:
        story.append(Paragraph("3. Strategic Risk Mitigation & Priorities", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_SUBTLE, spaceAfter=8))

        recs = [
            ("1. Address Actively Exploited (CISA KEV) Flaws", "Immediately remediate any vulnerabilities present on the CISA KEV list, as threat actors actively utilize weaponized automation against these specific weaknesses."),
            ("2. Prioritize Critical Severity & High EPSS Vectors", "Remediate high-exploitability vulnerabilities (EPSS > 50%) exposed to untrusted networks before low-probability internal issues."),
            ("3. Implement Continuous Security Scanning in CI/CD", "Integrate automated scanner adapters (Nuclei, Trivy, ZAP) directly into development pipelines to detect vulnerabilities prior to production deployment."),
            ("4. Review Asset Criticality & Exposure Tiering", "Ensure external network perimeters and public web applications enforce strict egress and rate limiting policies."),
        ]

        for title, text in recs:
            story.append(Paragraph(f"<b>{title}</b>", self.styles["SubSectionHeading"]))
            story.append(Paragraph(text, self.styles["ReportBody"]))
            story.append(Spacer(1, 4))

    def _add_coverage_gaps_section(self, story: List[Any]) -> None:
        """Adds explicit Coverage Gaps & Exclusions section to disclose unassessed or excluded targets/checks."""
        story.append(Spacer(1, 16))
        report_type = self.data.get("report_type", "technical")
        section_heading = "3. Coverage Gaps & Exclusions" if report_type == "technical" and not self.data.get("findings") else ("4. Coverage Gaps & Exclusions" if report_type == "executive" else "3. Coverage Gaps & Exclusions")
        story.append(Paragraph(section_heading, self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_SUBTLE, spaceAfter=8))

        gaps = self.data.get("coverage_gaps", [])
        metrics = self.data.get("coverage_metrics", {})
        cov_pct = metrics.get("coverage_pct", 100.0)

        intro_text = (
            f"<b>Assessment Integrity Disclosure:</b> Evaluated scope coverage is recorded at <b>{cov_pct}%</b>. "
            "To uphold rigorous audit integrity, all targets, scan engines, or test categories that could not be "
            "executed due to authorization boundaries, rate limiting, network unavailability, or policy exclusions "
            "are explicitly itemized below."
        )
        story.append(Paragraph(intro_text, self.styles["ReportBody"]))
        story.append(Spacer(1, 8))

        if not gaps:
            no_gaps_text = "<b>Zero Unassessed Exclusions:</b> All in-scope execution targets and approved engine modules were successfully evaluated without network timeouts, permission rejections, or unhandled scope exclusions."
            table_data = [[Paragraph(no_gaps_text, self.styles["ReportBody"])]]
            t = Table(table_data, colWidths=[504])
            t.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0FDF4")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#86EFAC")),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ])
            )
            story.append(t)
            story.append(Spacer(1, 12))
        else:
            table_data = [
                [
                    Paragraph("<font color='white'><b>Target Locator</b></font>", self.styles["ReportBody"]),
                    Paragraph("<font color='white'><b>Engine</b></font>", self.styles["ReportBody"]),
                    Paragraph("<font color='white'><b>Status</b></font>", self.styles["ReportBody"]),
                    Paragraph("<font color='white'><b>Exclusion Rationale / Details</b></font>", self.styles["ReportBody"]),
                ]
            ]
            for g in gaps:
                target_str = str(g.get("target_locator") or g.get("target") or "Unknown")
                engine_str = str(g.get("engine") or "All")
                status_str = str(g.get("status") or "EXCLUDED")
                reason_str = str(g.get("reason") or "Scope boundary exclusion")

                table_data.append([
                    Paragraph(f"<code>{target_str[:40]}</code>", self.styles["ReportBody"]),
                    Paragraph(engine_str, self.styles["ReportBody"]),
                    Paragraph(f"<b>{status_str}</b>", self.styles["ReportBody"]),
                    Paragraph(reason_str[:120], self.styles["ReportBody"]),
                ])

            t = Table(table_data, colWidths=[150, 70, 84, 200])
            t.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ])
            )
            story.append(t)
            story.append(Spacer(1, 12))

