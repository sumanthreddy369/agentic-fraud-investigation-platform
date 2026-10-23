"""Render repository-owned portfolio diagrams from measured project results."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "docs" / "images" / "portfolio"
OUT.mkdir(parents=True, exist_ok=True)
BG, PANEL, INK, MUTED, TEAL = "#0b1220", "#152238", "#f1f5f9", "#a9bbd0", "#49ddc5"
FONT_ROOT = Path("C:/Windows/Fonts")


def font(size, bold=False):
    return ImageFont.truetype(str(FONT_ROOT / ("arialbd.ttf" if bold else "arial.ttf")), size)


def page(label, title, subtitle):
    image = Image.new("RGB", (1600, 1000), BG)
    draw = ImageDraw.Draw(image)
    draw.text((64, 40), label.upper(), font=font(20, True), fill=TEAL)
    draw.text((64, 84), title, font=font(49, True), fill=INK)
    draw.text((64, 155), subtitle, font=font(24), fill=MUTED)
    return image, draw


def card(draw, box, tag, title, lines, accent=TEAL):
    x, y, right, bottom = box
    draw.rounded_rectangle(box, radius=18, fill=PANEL, outline="#30415a", width=2)
    draw.text((x + 24, y + 20), tag, font=font(18, True), fill=accent)
    draw.text((x + 24, y + 56), title, font=font(28, True), fill=INK)
    for index, line in enumerate(lines):
        draw.text((x + 24, y + 104 + index * 33), line, font=font(22), fill=MUTED)


def arrow(draw, x1, y, x2):
    draw.line((x1, y, x2, y), fill=TEAL, width=4)
    draw.polygon([(x2, y), (x2 - 12, y - 8), (x2 - 12, y + 8)], fill=TEAL)


def workflow():
    image, draw = page(
        "01 / Built workflow",
        "From model score to human review",
        "Authenticated API • case-scoped inputs • immutable records • bounded automation",
    )
    cards = [
        (
            "01  MODEL",
            "ONNX scoring",
            ["IEEE-CIS fraud model", "Validated model manifest", "Version + artifact hash"],
        ),
        (
            "02  SERVICE",
            "FastAPI + PostgreSQL",
            ["Authenticated case access", "Scores and audit history", "Idempotent requests"],
        ),
        (
            "03  WORKFLOW",
            "LangGraph",
            ["Read-only score metadata", "Bounded tool execution", "Abstaining review packet"],
        ),
        (
            "04  DECISION",
            "Human review",
            ["Approve / reject / revise", "Immutable reviewer record", "No enforcement actions"],
        ),
    ]
    for index, (tag, title, lines) in enumerate(cards):
        x = 64 + index * 375
        card(draw, (x, 250, x + 347, 515), tag, title, lines)
        if index < 3:
            arrow(draw, x + 350, 381, x + 371)
    card(
        draw,
        (64, 565, 790, 780),
        "PLATFORM ENGINEERING",
        "Deployment and operations",
        [
            "Docker • local Kubernetes • Terraform lifecycle proof",
            "Prometheus metrics • Grafana dashboards • CI checks",
        ],
    )
    card(
        draw,
        (814, 565, 1536, 780),
        "CONTROLLED EXECUTION",
        "Designed for reviewability",
        [
            "Owner + domain isolation • write and execution switches",
            "Completed-run replay • append-only PostgreSQL records",
        ],
    )
    image = image.crop((0, 0, 1600, 830))
    image.save(OUT / "01-workflow.png")


def results():
    image, draw = page(
        "02 / Engineering results",
        "Measured, reproducible outcomes",
        "IEEE-CIS modeling • ONNX serving • local platform validation",
    )
    for i, (value, label, detail) in enumerate(
        [
            ("590,540", "Labeled transactions", "Chronological evaluation"),
            ("0.8716", "Audit ROC-AUC", "400-feature gradient boosting"),
            ("0.4401", "Average precision", "118,108 retrospective rows"),
            ("192", "Tests passed", "Full suite with PostgreSQL; 1 skipped"),
        ]
    ):
        x = 64 + 375 * i
        draw.rounded_rectangle((x, 235, x + 347, 410), radius=18, fill=PANEL)
        draw.text((x + 22, 253), value, font=font(48, True), fill=TEAL)
        draw.text((x + 22, 321), label, font=font(24, True), fill=INK)
        draw.text((x + 22, 363), detail, font=font(17), fill=MUTED)
    draw.text((64, 460), "MODEL COMPARISON", font=font(20, True), fill=TEAL)
    rows = [
        ("Model", "Features", "ROC-AUC", "Avg. precision"),
        ("Logistic regression", "15", "0.7093", "0.1627"),
        ("Random forest", "15", "0.8357", "0.4021"),
        ("Histogram gradient boosting", "15", "0.8395", "0.4065"),
        ("Richer gradient boosting", "400", "0.8716", "0.4401"),
    ]
    for i, row in enumerate(rows):
        y = 504 + 49 * i
        draw.line((64, y + 39, 1536, y + 39), fill="#30415a")
        for x, cell in zip((80, 790, 1030, 1280), row, strict=True):
            draw.text((x, y), cell, font=font(23, i in (0, 4)), fill=INK if i else MUTED)
    draw.text(
        (64, 783),
        "ONNX parity: max error 3.37e-7 across 118,108 records",
        font=font(26, True),
        fill=TEAL,
    )
    draw.text(
        (64, 826),
        "Three local Docker replicas: 60/60 replay requests • HTTP p95 117.82 ms • no retries",
        font=font(23),
        fill=INK,
    )
    image = image.crop((0, 0, 1600, 880))
    image.save(OUT / "02-results.png")


def roadmap():
    image, draw = page(
        "03 / Delivery roadmap",
        "Built today. Next engineering milestones.",
        "An AWS-focused portfolio spanning ML platform engineering and agent infrastructure",
    )
    card(
        draw,
        (64, 235, 784, 555),
        "BUILT",
        "Model and service foundation",
        [
            "EDA • model comparison • calibration analysis",
            "ONNX inference • FastAPI • PostgreSQL provenance",
            "Docker • local Kubernetes / Terraform assessment",
            "Prometheus / Grafana • GitHub Actions checks",
            "LangGraph API runs • immutable human reviews",
        ],
    )
    card(
        draw,
        (814, 235, 1536, 555),
        "NEXT 01  /  AWS ASSESSMENT",
        "Deploy, measure, document, tear down",
        [
            "Private EKS • ECR • Terraform-managed resources",
            "Model serving and monitoring on AWS",
            "Recovery, scaling and reproducibility evidence",
            "Cost-aware teardown after the assessment",
        ],
        accent="#f8c66a",
    )
    card(
        draw,
        (64, 590, 784, 845),
        "NEXT 02  /  AGENT CAPABILITIES",
        "Evidence-backed investigation",
        [
            "Amazon Bedrock drafting • MCP tool transport",
            "Governed retrieval and citation evaluation",
            "OIDC identity and independent reviewer assignment",
        ],
        accent="#f8c66a",
    )
    card(
        draw,
        (814, 590, 1536, 845),
        "NEXT 03  /  MODEL OPERATIONS",
        "Lifecycle and scheduled pipelines",
        [
            "MLflow model tracking and version promotion",
            "Airflow pipeline scheduling • drift monitoring",
            "OpenTelemetry tracing and operational alerts",
        ],
        accent="#f8c66a",
    )
    image = image.crop((0, 0, 1600, 895))
    image.save(OUT / "03-roadmap.png")


if __name__ == "__main__":
    workflow()
    results()
    roadmap()
    print(OUT)
