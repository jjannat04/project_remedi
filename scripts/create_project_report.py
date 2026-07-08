from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "project_report.pdf"


class NumberedCanvas:
    def __init__(self, canvas, doc):
        self.canvas = canvas
        self.doc = doc

    def draw(self):
        page_num = self.canvas.getPageNumber()
        self.canvas.saveState()
        self.canvas.setStrokeColor(colors.HexColor("#d7dee8"))
        self.canvas.line(0.72 * inch, 0.58 * inch, A4[0] - 0.72 * inch, 0.58 * inch)
        self.canvas.setFont("Helvetica", 8.5)
        self.canvas.setFillColor(colors.HexColor("#4d5b6b"))
        self.canvas.drawString(0.72 * inch, 0.38 * inch, "ReMedi Project Report")
        self.canvas.drawRightString(A4[0] - 0.72 * inch, 0.38 * inch, f"Page {page_num}")
        self.canvas.restoreState()


def on_page(canvas, doc):
    NumberedCanvas(canvas, doc).draw()


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#15324a"),
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["BodyText"],
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#44546a"),
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=colors.HexColor("#15324a"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1f5d75"),
            spaceBefore=5,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontSize=10,
            leading=13.2,
            textColor=colors.HexColor("#222a35"),
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontSize=9,
            leading=11.5,
            textColor=colors.HexColor("#536273"),
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=11.5,
            textColor=colors.HexColor("#536273"),
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "table": ParagraphStyle(
            "TableCell",
            parent=base["BodyText"],
            fontSize=8.6,
            leading=10.5,
            textColor=colors.HexColor("#222a35"),
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.8,
            leading=10.5,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "placeholder": ParagraphStyle(
            "Placeholder",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#31556b"),
        ),
    }


def p(text, style):
    return Paragraph(text, style)


def bullets(items, style):
    return ListFlowable(
        [ListItem(p(item, style), leftIndent=12) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=18,
        bulletFontSize=7,
        spaceAfter=4,
    )


def placeholder_box(title, note, width=6.9 * inch, height=1.25 * inch):
    s = styles()
    box = Table(
        [[p(title, s["placeholder"]), p(note, s["small"])]],
        colWidths=[2.1 * inch, width - 2.1 * inch],
        rowHeights=[height],
    )
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#6fa3b6")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f8fa")),
                ("LINEBEFORE", (1, 0), (1, 0), 0.8, colors.HexColor("#b7d0da")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return box


def table(data, col_widths):
    s = styles()
    rendered = []
    for row_idx, row in enumerate(data):
        style = s["table_head"] if row_idx == 0 else s["table"]
        rendered.append([p(cell, style) for cell in row])
    tbl = Table(rendered, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f5d75")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c9d5de")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    return tbl


def build_story():
    s = styles()
    story = []

    story += [
        p("ReMedi", s["title"]),
        p("Circular Healthcare Redistribution Platform", s["subtitle"]),
        p(
            "Project report prepared for the required PDF submission. The report follows the rulebook sequence: "
            "problem statement, proposed solution, methodology, AI/ML approach, results, limitations, and future work.",
            s["body"],
        ),
        Spacer(1, 8),
        p("Executive Summary", s["h1"]),
        p(
            "ReMedi is a Django-based platform for reducing medicine waste and improving affordable access to "
            "unused, unexpired medicines in Bangladesh. Donors submit medicine details and package images, AI-assisted "
            "services extract visible package information and safety signals, licensed pharmacists make the final "
            "approval decision, and patients reserve verified medicines for QR and OTP-verified pickup.",
            s["body"],
        ),
        p(
            "The project deliberately keeps AI advisory. OCR, visual safety inspection, risk scoring, and decision "
            "support help reviewers work faster, but the system records pharmacist approval or rejection as the source "
            "of truth. This design balances automation with patient safety, traceability, and practical demo reliability.",
            s["body"],
        ),
        p("Problem Statement", s["h1"]),
        p(
            "Unused medicines often remain in households until expiry while many patients struggle to afford basic "
            "treatment. Informal reuse creates serious risks: damaged packaging, unclear expiry dates, missing batch "
            "numbers, possible tampering, and no accountable handoff. A useful solution must therefore address both "
            "waste and access without treating medicine redistribution as a simple peer-to-peer marketplace.",
            s["body"],
        ),
        bullets(
            [
                "Medicine waste increases environmental burden and represents lost healthcare value.",
                "Low-income patients need trusted, affordable access to safe medicines.",
                "Healthcare professionals need a review workflow that is faster than manual sorting alone.",
                "Each donation and pickup needs traceability to reduce misuse and support auditability.",
            ],
            s["body"],
        ),
        p("Proposed Solution", s["h1"]),
        p(
            "ReMedi proposes a circular healthcare redistribution workflow. Donors list suitable medicines, the system "
            "performs AI-assisted package review, pharmacists verify safety and authenticity, and patients reserve "
            "approved medicines at a reduced resale price. The platform adds dashboards and anonymous impact reports "
            "so partners can track waste prevention, affordability, and collection outcomes.",
            s["body"],
        ),
        placeholder_box(
            "Figure 1 Placeholder",
            "Insert final system workflow screenshot or diagram: donor submission -> AI analysis -> pharmacist review -> marketplace reservation -> QR/OTP pickup.",
        ),
        p("Core System Modules", s["h2"]),
        table(
            [
                ["Module", "Purpose", "Implemented Evidence"],
                ["Donation intake", "Collect medicine identity, quantity, expiry, location, storage, and image data.", "Django forms, image upload, image compression, pending status."],
                ["AI review support", "Extract OCR fields, inspect visual safety, compute risk, and produce advisory decisions.", "Gemini OCR/safety, OCR.space fallback, deterministic fallback, cached OCR."],
                ["Pharmacist verification", "Keep final human approval or rejection in the loop.", "Verification queue, review page, rejection reasons, timestamps."],
                ["Marketplace and reservation", "Expose only verified available medicines and reserve them for patients.", "Marketplace listing, detail page, reservation state, reserved-until tracking."],
                ["Pickup trust layer", "Confirm collection using traceable medicine identity and patient OTP.", "QR identifiers, pickup OTP, pharmacist pickup desk, sold/completed state."],
                ["Impact reporting", "Show aggregated, privacy-preserving outcomes.", "Dashboard charts and text reports for overall, weekly, waste, affordability, CSR/ESG."],
            ],
            [1.35 * inch, 2.25 * inch, 3.05 * inch],
        ),
        p("Methodology", s["h1"]),
        p(
            "The project was implemented as a web application with role-specific workflows for donors, healthcare "
            "verifiers, and patients. The methodology focused on safety-first state transitions, traceability, demo "
            "reliability, and measurable impact indicators.",
            s["body"],
        ),
        p("Development Workflow", s["h2"]),
        bullets(
            [
                "Model the core entities: custom users, medicine donations, patient reservations, and ReMedi Corner pickup locations.",
                "Create role-aware pages for marketplace browsing, donation submission, profile tracking, pharmacist queues, pickup verification, dashboards, and reports.",
                "Implement safe medicine states: pending, verified, rejected, reserved, and sold/collected.",
                "Add QR identifiers and pickup OTPs so collection requires both a traceable medicine record and patient-held code.",
                "Seed deterministic demo data for judge presentations while keeping production flows configurable.",
            ],
            s["body"],
        ),
        p("Architecture", s["h2"]),
        table(
            [
                ["Layer", "Technology / Component", "Role in ReMedi"],
                ["Frontend", "Django templates, Tailwind CDN, Bootstrap Icons", "Role-specific screens and responsive presentation UI."],
                ["Backend", "Django 6, Python services", "Business rules, review workflow, reservations, reporting, AI orchestration."],
                ["Data", "SQLite locally, PostgreSQL-ready via DATABASE_URL", "Stores users, medicines, QR/OTP metadata, reports, and demo records."],
                ["Media", "Local filesystem or Cloudinary", "Stores medicine package images with deployment-ready durable storage."],
                ["Static/deploy", "WhiteNoise, Gunicorn, Render build script", "Supports hosted deployment and static asset serving."],
            ],
            [1.25 * inch, 2.15 * inch, 3.25 * inch],
        ),
        p("Verification and Safety Methodology", s["h2"]),
        p(
            "Medicine records do not become patient-facing inventory by default. Donations begin as pending items. "
            "AI analysis can suggest whether the package appears low risk, needs review, or should be rejected, but "
            "licensed pharmacists approve or reject the final item. Approved medicines receive verification metadata "
            "and QR traceability; rejected medicines retain a reason and timestamp.",
            s["body"],
        ),
        placeholder_box(
            "Table 1 Placeholder",
            "Insert a final requirements traceability table mapping rulebook criteria, implemented features, and evidence screenshots.",
        ),
        PageBreak(),
        p("AI/ML Approach", s["h1"]),
        p(
            "The AI/ML layer is built as an assisted review pipeline rather than an autonomous medical decision maker. "
            "It operates on package images and visible text, not on patient diagnosis or clinical suitability. This "
            "scope keeps the model aligned with the platform objective: helping pharmacists review packaging evidence.",
            s["body"],
        ),
        placeholder_box(
            "Figure 2 Placeholder",
            "Insert AI pipeline figure: image upload -> OCR -> visual safety inspection -> risk score -> advisory decision -> pharmacist review.",
        ),
        p("Pipeline Steps", s["h2"]),
        table(
            [
                ["Step", "Inputs", "Outputs", "Safety Design"],
                ["OCR extraction", "Medicine package image", "Name, generic/scientific name, dosage, manufacturer, batch, expiry text, confidence", "Prompt requires visible text only and JSON-only output."],
                ["Fallback OCR", "Same image", "OCR.space result or deterministic demo output", "Prevents demo failure when API keys, quota, or provider access fail."],
                ["Visual safety", "Image plus OCR result", "Flags for damage, tampering, unclear expiry, missing batch, quality, counterfeit warning", "Does not approve medicine; only reports visible package-safety findings."],
                ["Risk scoring", "OCR and safety signals", "0-100 risk score, level, reasons", "Penalizes unclear expiry, low OCR confidence, missing batch, and tamper signals."],
                ["Decision support", "Risk, safety, OCR confidence", "Accept/review/reject recommendation with reasons", "Advisory only; pharmacist remains final authority."],
            ],
            [1.05 * inch, 1.45 * inch, 2.35 * inch, 1.8 * inch],
        ),
        p("Decision Logic", s["h2"]),
        bullets(
            [
                "Reject recommendation: risk score at least 70, tampered seal, or damaged packaging.",
                "Review recommendation: medium risk, unclear expiry, or OCR confidence below 0.8.",
                "Accept recommendation: low risk, no safety issues, and acceptable OCR confidence.",
            ],
            s["body"],
        ),
        PageBreak(),
        p("Results", s["h1"]),
        p(
            "The current implementation delivers an end-to-end prototype with donation intake, AI-assisted analysis, "
            "pharmacist review, verified marketplace listings, patient reservation, QR/OTP pickup, dashboards, reports, "
            "and deployment configuration. The test suite includes coverage for demo seeding, registration, AI safety "
            "fallbacks, OCR behavior, reservation and pickup flows, reporting, image upload, media serving, and Cloudinary storage switching.",
            s["body"],
        ),
        p("Functional Results", s["h2"]),
        table(
            [
                ["Outcome", "Current Result"],
                ["Donation lifecycle", "A donor can submit medicine information and optional image; the record enters pending review."],
                ["AI extraction", "Image analysis returns structured OCR, safety, risk, and explanation data for the donation form."],
                ["Human verification", "A pharmacist can approve or reject pending medicines with recorded state changes."],
                ["Patient access", "Verified medicines appear in the marketplace and can be reserved by patients."],
                ["Secure pickup", "The pickup desk verifies medicine/QR identity and OTP before marking an item collected."],
                ["Impact reporting", "Anonymous overall, weekly, waste, affordability, and CSR/ESG reports are generated from aggregate data."],
                ["Demo readiness", "Seed commands create deterministic users, medicines, ReMedi Corners, and history for judging."],
            ],
            [1.9 * inch, 4.75 * inch],
        ),
        p("Demo Data and Test Indicators", s["h2"]),
        table(
            [
                ["Indicator", "Observed / Seeded Value", "Interpretation"],
                ["Seeded demo medicines", "36", "Enough variety to show pending, verified, rejected, reserved, and sold states."],
                ["Rejected demo medicines", "5", "Unsafe or unsuitable examples remain visible for pharmacist review evidence."],
                ["Completed/redistributed demo medicines", "At least 4", "Supports dashboard and affordability-impact demonstration."],
                ["ReMedi Corner records", "5", "Shows pickup/collection point mapping in the Bangladesh context."],
                ["Resale pricing rule", "30 percent of original price", "Demonstrates affordability benefit for patients."],
            ],
            [1.85 * inch, 1.6 * inch, 3.2 * inch],
        ),
        placeholder_box(
            "Figure 3 Placeholder",
            "Insert screenshots of final dashboard charts: verification outcomes, marketplace distribution, risk levels, categories, and approval timeline.",
        ),
        p("Evaluation Notes", s["h2"]),
        bullets(
            [
                "The prototype favors deterministic fallback behavior for judging reliability when external AI quotas or API keys are unavailable.",
                "Reports are anonymized and avoid exposing donor or patient identities, phone numbers, or emails.",
                "The implemented tests check state transitions and failure modes that matter for medicine safety and platform trust.",
            ],
            s["body"],
        ),
        PageBreak(),
        p("Limitations", s["h1"]),
        bullets(
            [
                "The AI layer cannot guarantee authenticity, clinical suitability, storage history, or chemical integrity of a medicine.",
                "Risk scoring is rule-based and advisory; it needs calibration with pharmacist feedback and real-world donation data.",
                "OCR quality depends on image clarity, lighting, package language, and external provider availability.",
                "The current prototype does not integrate pharmacy inventory systems, payment reconciliation, or regulatory approval workflows.",
                "Uploaded medicine images and records need production-grade operational policies for retention, privacy, and audit review.",
            ],
            s["body"],
        ),
        p("Future Work", s["h1"]),
        bullets(
            [
                "Add richer pharmacist audit logs and reviewer analytics.",
                "Introduce notifications for donation status, reservation expiry, and pickup reminders.",
                "Improve reporting exports with PDF/CSV formats and partner-ready summaries.",
                "Train or tune risk models using pharmacist-labeled review outcomes once sufficient data exists.",
                "Add stronger medicine category analytics, expiry forecasting, and partner dashboard views.",
                "Explore barcode verification, manufacturer databases, and regulatory validation sources for stronger authenticity checks.",
            ],
            s["body"],
        ),
        p("Conclusion", s["h1"]),
        p(
            "ReMedi demonstrates a practical safety-first approach to medicine redistribution. It connects donors, "
            "pharmacists, and patients through a traceable workflow, uses AI to reduce manual review burden, and keeps "
            "human professionals in control of final safety decisions. With further validation and partner integration, "
            "the system can support both waste reduction and affordable healthcare access.",
            s["body"],
        ),
        placeholder_box(
            "Final Screenshots Placeholder",
            "Insert final marketplace, donation, pharmacist queue, pickup desk, and impact dashboard screenshots before submission if required.",
            height=1.0 * inch,
        ),
    ]
    return story


def build_pdf():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=0.72 * inch,
        rightMargin=0.72 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.78 * inch,
        title="ReMedi Project Report",
        author="ReMedi Team",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    template = PageTemplate(id="report", frames=[frame], onPage=on_page)
    doc.addPageTemplates([template])
    doc.build(build_story())
    return OUTPUT


if __name__ == "__main__":
    print(build_pdf())
