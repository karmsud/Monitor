"""Use-case flow diagram generator with icon-based visual style.

Generates SVG diagrams showing end-to-end command flows with:
- Dual-path visualization (deterministic slash-command + NLP free-form)
- Boundary containers with corner badges
- Icon nodes (coloured circles with white pictograms)
- Colour-coded edges with numbered step circles
- Legend and annotation callouts

Phase 1: /logs flow.  Phase 2 will add /jobs, /deals, /staging, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "architecture" / "use-cases"

# ── Colour constants ─────────────────────────────────────────────────

# Edge colours
C_DET = "#2563EB"       # Blue-600  – deterministic path
C_NLP = "#059669"       # Emerald-600 – NLP/agentLoop path
C_DATA = "#7C3AED"      # Violet-600 – data-store access
C_SHARED = "#475569"    # Slate-600  – shared / neutral

# Node circle backgrounds
N_UI = "#3B82F6"        # Blue-500  – user-facing
N_PROC = "#10B981"      # Emerald-500 – processing / routing
N_BACK = "#F59E0B"      # Amber-500 – backend / CLI
N_STORE = "#8B5CF6"     # Violet-500 – data stores
N_AI = "#EC4899"        # Pink-500  – AI / LLM

# Container / chrome
CONT_STROKE = "#94A3B8"
CONT_FILL = "#F8FAFC"
BADGE_BG = "#1E293B"
CANVAS_BG = "#FFFFFF"
TITLE_BG = "#0F172A"
SUB_STROKE = "#CBD5E1"
SUB_FILL = "#F0F4F8"

# Text
TEXT_DARK = "#1E293B"
TEXT_MUTED = "#475569"

# ── Icon SVG fragments (24×24 viewBox, white on coloured circle) ────

ICONS: Dict[str, str] = {
    "person": (
        '<circle cx="12" cy="8" r="4" fill="white"/>'
        '<path d="M4 21v-1c0-2.8 3.6-5 8-5s8 2.2 8 5v1z" fill="white"/>'
    ),
    "chat": (
        '<path d="M2 5c0-1 1-2 2-2h16c1 0 2 1 2 2v10c0 1-1 2-2 2H7l-5 4z" fill="white"/>'
    ),
    "gear": (
        '<circle cx="12" cy="12" r="4" fill="none" stroke="white" stroke-width="2.2"/>'
        '<rect x="10.8" y="1.5" width="2.4" height="4" rx=".8" fill="white"/>'
        '<rect x="10.8" y="18.5" width="2.4" height="4" rx=".8" fill="white"/>'
        '<rect x="1.5" y="10.8" width="4" height="2.4" rx=".8" fill="white"/>'
        '<rect x="18.5" y="10.8" width="4" height="2.4" rx=".8" fill="white"/>'
    ),
    "config": (
        '<line x1="4" y1="9" x2="20" y2="9" stroke="white" stroke-width="2" stroke-linecap="round"/>'
        '<line x1="4" y1="15" x2="20" y2="15" stroke="white" stroke-width="2" stroke-linecap="round"/>'
        '<circle cx="9" cy="9" r="2.5" fill="white"/>'
        '<circle cx="15" cy="15" r="2.5" fill="white"/>'
    ),
    "terminal": (
        '<rect x="2" y="4" width="20" height="16" rx="2" fill="none" stroke="white" stroke-width="1.8"/>'
        '<path d="M6 10l3 2-3 2" fill="none" stroke="white" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<line x1="12" y1="14" x2="17" y2="14" stroke="white" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "document": (
        '<rect x="5" y="2" width="14" height="20" rx="1.5" fill="none" stroke="white" stroke-width="1.5"/>'
        '<line x1="8" y1="8" x2="16" y2="8" stroke="white" stroke-width="1.2" stroke-linecap="round"/>'
        '<line x1="8" y1="11.5" x2="16" y2="11.5" stroke="white" stroke-width="1.2" stroke-linecap="round"/>'
        '<line x1="8" y1="15" x2="13" y2="15" stroke="white" stroke-width="1.2" stroke-linecap="round"/>'
    ),
    "database": (
        '<ellipse cx="12" cy="7" rx="7.5" ry="3" fill="none" stroke="white" stroke-width="1.8"/>'
        '<path d="M4.5 7v10c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V7" fill="none" stroke="white" stroke-width="1.8"/>'
        '<path d="M4.5 12.5c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3" fill="none" stroke="white" stroke-width="1.5"/>'
    ),
    "folder": (
        '<path d="M2 7.5c0-.8.7-1.5 1.5-1.5H9l2-2h9.5c.8 0 1.5.7 1.5 1.5v13c0 .8-.7 '
        '1.5-1.5 1.5h-17c-.8 0-1.5-.7-1.5-1.5z" fill="white"/>'
    ),
    "router": (
        '<path d="M12 3l9 9-9 9-9-9z" fill="none" stroke="white" stroke-width="2"/>'
        '<circle cx="12" cy="12" r="2" fill="white"/>'
    ),
}


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class IconNode:
    id: str
    icon: str          # key in ICONS, or "python"/"brain" for text-fallback
    label: str         # may contain \n for multi-line
    cx: float
    cy: float
    color: str         # circle background


@dataclass
class Container:
    x: float
    y: float
    w: float
    h: float
    label_left: str
    badge_right: str
    badge_color: str = N_UI


@dataclass
class SubGroup:
    x: float
    y: float
    w: float
    h: float
    label: str


@dataclass
class FlowEdge:
    points: List[Tuple[float, float]]
    color: str
    dashed: bool = False
    step: int = 0          # 0 = no step marker
    step_pos: Optional[Tuple[float, float]] = None  # override midpoint


@dataclass
class Annotation:
    x: float
    y: float
    w: float
    h: float
    title: str
    lines: List[str]
    bg: str = "#FFFBEB"
    stroke: str = "#F59E0B"


@dataclass
class LoopBand:
    x: float
    y: float
    w: float
    h: float
    label: str          # e.g. "⟳ Loop 1 — Job Match"
    iteration: str      # e.g. "for each job in Settings.xml"
    accent: str
    bg: str = "#EFF6FF"


@dataclass
class ComponentCard:
    """Rich component card for executive diagrams."""
    x: float
    y: float
    w: float
    h: float
    icon: str          # key in ICONS, or text fallback
    title: str
    subtitle: str
    accent: str        # left border + icon bg colour
    bg: str = "#FFFFFF"


# ── Helpers ──────────────────────────────────────────────────────────

def xml_esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def make_path(pts: List[Tuple[float, float]]) -> str:
    return "M " + " L ".join(f"{x:.0f} {y:.0f}" for x, y in pts)


def midpoint(pts: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Return approximate midpoint of a polyline."""
    total = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        total += (dx * dx + dy * dy) ** 0.5
    half = total / 2
    accum = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        seg = (dx * dx + dy * dy) ** 0.5
        if accum + seg >= half:
            frac = (half - accum) / seg if seg else 0
            return pts[i - 1][0] + dx * frac, pts[i - 1][1] + dy * frac
        accum += seg
    return pts[-1]


# ── SVG renderers ────────────────────────────────────────────────────

def render_defs() -> str:
    markers = []
    for name, col in [("det", C_DET), ("nlp", C_NLP), ("data", C_DATA), ("shared", C_SHARED)]:
        markers.append(
            f'<marker id="arr-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{col}"/></marker>'
        )
    shadow = (
        '<filter id="nodeShadow" x="-30%" y="-30%" width="160%" height="160%">'
        '<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#0F172A" flood-opacity="0.12"/>'
        '</filter>'
    )
    return "<defs>\n" + "\n".join(markers) + "\n" + shadow + "\n</defs>"


def marker_for(color: str) -> str:
    m = {C_DET: "det", C_NLP: "nlp", C_DATA: "data", C_SHARED: "shared"}
    return f'url(#arr-{m.get(color, "shared")})'


def render_container(c: Container) -> str:
    parts = [
        f'<rect x="{c.x}" y="{c.y}" width="{c.w}" height="{c.h}" rx="12" '
        f'fill="{CONT_FILL}" stroke="{CONT_STROKE}" stroke-width="1.5" stroke-dasharray="10 5"/>',
    ]
    # Left badge
    bw = len(c.label_left) * 7.2 + 18
    bx = c.x + 14
    by = c.y - 11
    parts.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="22" rx="4" fill="{BADGE_BG}"/>')
    parts.append(
        f'<text x="{bx + bw / 2:.1f}" y="{by + 15}" text-anchor="middle" fill="white" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="11" font-weight="600">'
        f'{xml_esc(c.label_left)}</text>'
    )
    # Right badge
    bw2 = len(c.badge_right) * 7.2 + 18
    bx2 = c.x + c.w - bw2 - 14
    parts.append(f'<rect x="{bx2:.1f}" y="{by}" width="{bw2:.1f}" height="22" rx="4" fill="{c.badge_color}"/>')
    parts.append(
        f'<text x="{bx2 + bw2 / 2:.1f}" y="{by + 15}" text-anchor="middle" fill="white" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="11" font-weight="600">'
        f'{xml_esc(c.badge_right)}</text>'
    )
    return "\n".join(parts)


def render_subgroup(sg: SubGroup) -> str:
    parts = [
        f'<rect x="{sg.x}" y="{sg.y}" width="{sg.w}" height="{sg.h}" rx="8" '
        f'fill="{SUB_FILL}" stroke="{SUB_STROKE}" stroke-width="1" stroke-dasharray="6 3"/>',
        f'<text x="{sg.x + 12}" y="{sg.y + 16}" fill="{TEXT_MUTED}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="10" font-weight="600">{xml_esc(sg.label)}</text>',
    ]
    return "\n".join(parts)


def render_icon_node(n: IconNode) -> str:
    parts = [
        # Soft shadow
        f'<circle cx="{n.cx + 1}" cy="{n.cy + 2}" r="25" fill="black" opacity="0.07"/>',
        # Coloured circle
        f'<circle cx="{n.cx}" cy="{n.cy}" r="24" fill="{n.color}" filter="url(#nodeShadow)"/>',
    ]
    icon_svg = ICONS.get(n.icon)
    if icon_svg:
        parts.append(f'<g transform="translate({n.cx - 12},{n.cy - 12})">{icon_svg}</g>')
    else:
        # Text fallback (python → "Py", brain → "AI")
        txt = {"python": "Py", "brain": "AI"}.get(n.icon, "?")
        parts.append(
            f'<text x="{n.cx}" y="{n.cy + 5}" text-anchor="middle" fill="white" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="14" font-weight="700">{txt}</text>'
        )
    # Label below
    lines = n.label.split("\n")
    ly = n.cy + 38
    for i, line in enumerate(lines):
        fw = "600" if i == 0 else "400"
        parts.append(
            f'<text x="{n.cx}" y="{ly + i * 14}" text-anchor="middle" fill="{TEXT_DARK}" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11" font-weight="{fw}">'
            f'{xml_esc(line)}</text>'
        )
    return "\n".join(parts)


def render_edge(e: FlowEdge) -> str:
    dash = ' stroke-dasharray="6 4"' if e.dashed else ""
    path = make_path(e.points)
    parts = [
        f'<path d="{path}" fill="none" stroke="{e.color}" stroke-width="2" '
        f'marker-end="{marker_for(e.color)}"{dash}/>'
    ]
    if e.step:
        sx, sy = e.step_pos if e.step_pos else midpoint(e.points)
        parts.append(
            f'<circle cx="{sx}" cy="{sy}" r="11" fill="{e.color}"/>'
            f'<text x="{sx}" y="{sy + 4}" text-anchor="middle" fill="white" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11" font-weight="700">{e.step}</text>'
        )
    return "\n".join(parts)


def render_transport_label(y: float, x_start: float, x_end: float, label: str) -> str:
    mx = (x_start + x_end) / 2
    tw = len(label) * 6.5 + 24
    return (
        f'<line x1="{x_start}" y1="{y}" x2="{x_end}" y2="{y}" '
        f'stroke="{CONT_STROKE}" stroke-width="1" stroke-dasharray="4 3"/>\n'
        f'<rect x="{mx - tw / 2}" y="{y - 11}" width="{tw}" height="22" rx="4" fill="white" '
        f'stroke="{CONT_STROKE}" stroke-width="1"/>\n'
        f'<text x="{mx}" y="{y + 4}" text-anchor="middle" fill="{TEXT_MUTED}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="10" font-weight="600">{xml_esc(label)}</text>'
    )


def render_annotation(a: Annotation) -> str:
    parts = [
        f'<rect x="{a.x}" y="{a.y}" width="{a.w}" height="{a.h}" rx="8" '
        f'fill="{a.bg}" stroke="{a.stroke}" stroke-width="1.2"/>',
        f'<text x="{a.x + 14}" y="{a.y + 20}" fill="{TEXT_DARK}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="12" font-weight="700">{xml_esc(a.title)}</text>',
    ]
    for i, line in enumerate(a.lines):
        parts.append(
            f'<text x="{a.x + 14}" y="{a.y + 38 + i * 15}" fill="{TEXT_MUTED}" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10.5">{xml_esc(line)}</text>'
        )
    return "\n".join(parts)


def render_legend(x: float, y: float, w: float, h: float = 280,
                   det_label: str = "Deterministic path (①–⑨)") -> str:
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h:.0f}" rx="8" fill="white" '
        f'stroke="{SUB_STROKE}" stroke-width="1.2"/>',
        f'<text x="{x + 14}" y="{y + 22}" fill="{TEXT_DARK}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="13" font-weight="700">Legend</text>',
        f'<line x1="{x + 14}" y1="{y + 30}" x2="{x + w - 14}" y2="{y + 30}" '
        f'stroke="{SUB_STROKE}" stroke-width="0.5"/>',
    ]
    entries = [
        (C_DET, False, det_label),
        (C_NLP, False, "NLP / LLM tool-call path"),
        (C_DATA, True, "Data store access"),
        (C_SHARED, False, "Shared transport"),
    ]
    for i, (col, dashed, label) in enumerate(entries):
        ey = y + 52 + i * 30
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        parts.append(f'<line x1="{x + 18}" y1="{ey}" x2="{x + 60}" y2="{ey}" stroke="{col}" stroke-width="2.5"{dash}/>')
        parts.append(f'<circle cx="{x + 60}" cy="{ey}" r="4" fill="{col}"/>')  # arrowhead dot
        parts.append(
            f'<text x="{x + 72}" y="{ey + 4}" fill="{TEXT_DARK}" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11">{xml_esc(label)}</text>'
        )
    # Node colours
    node_entries = [
        (N_UI, "User-facing / UI"),
        (N_PROC, "Processing / routing"),
        (N_BACK, "Backend / CLI"),
        (N_STORE, "Data store"),
        (N_AI, "AI / LLM"),
    ]
    ny = y + 52 + len(entries) * 30 + 5
    for i, (col, label) in enumerate(node_entries):
        ey = ny + i * 22
        if ey + 12 > y + h:
            break
        parts.append(f'<circle cx="{x + 28}" cy="{ey}" r="7" fill="{col}"/>')
        parts.append(
            f'<text x="{x + 42}" y="{ey + 4}" fill="{TEXT_DARK}" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10">{xml_esc(label)}</text>'
        )
    return "\n".join(parts)


def render_title(text: str, subtitle: str) -> str:
    return (
        f'<rect x="40" y="15" width="1840" height="55" rx="6" fill="{TITLE_BG}"/>\n'
        f'<text x="960" y="38" text-anchor="middle" fill="white" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="22" font-weight="700">{xml_esc(text)}</text>\n'
        f'<text x="960" y="56" text-anchor="middle" fill="#94A3B8" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="12">{xml_esc(subtitle)}</text>'
    )


def render_loop_band(lb: LoopBand) -> str:
    """Render a loop container with left accent bar and loop badge."""
    parts = [
        # Background
        f'<rect x="{lb.x}" y="{lb.y}" width="{lb.w}" height="{lb.h}" '
        f'rx="8" fill="{lb.bg}" stroke="{lb.accent}" stroke-width="1.2" stroke-opacity="0.5"/>',
        # Left accent bar
        f'<rect x="{lb.x}" y="{lb.y}" width="4" height="{lb.h}" rx="2" fill="{lb.accent}"/>',
    ]
    # Badge
    bw = len(lb.label) * 6.2 + 16
    bx = lb.x + 12
    by = lb.y + 6
    parts.extend([
        f'<rect x="{bx}" y="{by}" width="{bw:.0f}" height="18" rx="3" fill="{lb.accent}" opacity="0.9"/>',
        f'<text x="{bx + bw / 2:.0f}" y="{by + 13}" text-anchor="middle" fill="white" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="9" font-weight="600">'
        f'{xml_esc(lb.label)}</text>',
    ])
    # Iteration label
    parts.append(
        f'<text x="{bx + bw + 8:.0f}" y="{by + 13}" fill="{TEXT_MUTED}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="9" font-style="italic">'
        f'{xml_esc(lb.iteration)}</text>'
    )
    return "\n".join(parts)


def render_component_card(c: ComponentCard) -> str:
    """Render a rich card with icon badge, title, subtitle, and accent bar."""
    parts = [
        # Shadow
        f'<rect x="{c.x + 2}" y="{c.y + 3}" width="{c.w}" height="{c.h}" '
        f'rx="8" fill="black" opacity="0.06"/>',
        # Background
        f'<rect x="{c.x}" y="{c.y}" width="{c.w}" height="{c.h}" '
        f'rx="8" fill="{c.bg}" stroke="#E2E8F0" stroke-width="1"/>',
        # Left accent bar
        f'<rect x="{c.x}" y="{c.y}" width="5" height="{c.h}" '
        f'rx="2" fill="{c.accent}"/>',
    ]
    # Icon badge circle
    icx = c.x + 32
    icy = c.y + c.h / 2
    parts.append(f'<circle cx="{icx:.0f}" cy="{icy:.0f}" r="18" fill="{c.accent}"/>')
    icon_svg = ICONS.get(c.icon)
    if icon_svg:
        parts.append(
            f'<g transform="translate({icx - 9:.0f},{icy - 9:.0f}) scale(0.75)">'
            f'{icon_svg}</g>'
        )
    else:
        txt = {"python": "Py", "brain": "AI", "sql": "SQL"}.get(c.icon, "?")
        parts.append(
            f'<text x="{icx:.0f}" y="{icy + 5:.0f}" text-anchor="middle" fill="white" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="12" font-weight="700">'
            f'{txt}</text>'
        )
    # Title + subtitle
    tx = c.x + 58
    ty_title = c.y + c.h / 2 - 3 if c.subtitle else c.y + c.h / 2 + 4
    parts.append(
        f'<text x="{tx:.0f}" y="{ty_title:.0f}" fill="{TEXT_DARK}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="12" font-weight="600">'
        f'{xml_esc(c.title)}</text>'
    )
    if c.subtitle:
        parts.append(
            f'<text x="{tx:.0f}" y="{c.y + c.h / 2 + 12:.0f}" fill="{TEXT_MUTED}" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10">'
            f'{xml_esc(c.subtitle)}</text>'
        )
    return "\n".join(parts)


def render_feature_pills(x: float, y: float, labels: List[str],
                          color: str, cols: int = 4) -> str:
    """Render a grid of small rounded feature pills."""
    parts: List[str] = []
    ph = 22
    gap_x, gap_y = 6, 5
    col_w = 115
    for i, label in enumerate(labels):
        col = i % cols
        row = i // cols
        pw = max(len(label) * 6.5 + 14, 60)
        px = x + col * col_w
        py = y + row * (ph + gap_y)
        parts.extend([
            f'<rect x="{px:.0f}" y="{py}" width="{pw:.0f}" height="{ph}" '
            f'rx="11" fill="{color}" opacity="0.12"/>',
            f'<text x="{px + pw / 2:.0f}" y="{py + 15}" text-anchor="middle" '
            f'fill="{color}" font-family="Helvetica,Arial,sans-serif" '
            f'font-size="10" font-weight="600">{xml_esc(label)}</text>',
        ])
    return "\n".join(parts)


# ── /logs flow builder ───────────────────────────────────────────────

def build_logs_flow() -> str:
    """Build complete SVG for the /logs use-case flow."""

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="900" viewBox="0 0 1920 900">',
        render_defs(),
        f'<rect width="1920" height="900" fill="{CANVAS_BG}"/>',
    ]

    # Title
    parts.append(render_title(
        "Use Case: /logs — Log Search & Analytics",
        "Deterministic and NLP paths from user prompt to formatted results",
    ))

    # ── Containers ───────────────────────────────────────────────────
    client = Container(40, 85, 1260, 300, "VS Code Process", "Client", N_UI)
    server = Container(40, 430, 1260, 210, "Python Backend", "Server", N_BACK)
    data = Container(40, 685, 1260, 155, "Persistent Stores", "Data", N_STORE)
    parts.append(render_container(client))
    parts.append(render_container(server))
    parts.append(render_container(data))

    # Logs domain sub-group inside server
    parts.append(render_subgroup(SubGroup(530, 468, 730, 155, "Logs Domain")))

    # Transport label
    parts.append(render_transport_label(408, 80, 1260, "JSON Line Transport (stdin / stdout)"))

    # ── Icon Nodes ───────────────────────────────────────────────────
    nodes = [
        # CLIENT tier
        IconNode("user", "person", "Operator", 130, 215, N_UI),
        IconNode("chat", "chat", "Copilot Chat\n@frp", 300, 215, N_UI),
        IconNode("participant", "gear", "participant.js\nparse + route", 490, 215, N_PROC),
        IconNode("det_parser", "document", "deterministic\nparser", 700, 150, N_PROC),
        IconNode("llm", "brain", "agentLoop\nLLM tool-call", 700, 298, N_AI),
        IconNode("tool", "config", "tool.js\ninject config", 920, 215, N_PROC),
        IconNode("backend", "terminal", "frp_backend.js\nprocess bridge", 1140, 215, N_BACK),
        # SERVER tier
        IconNode("cli", "python", "cli/main.py\n--server", 200, 548, N_BACK),
        IconNode("dispatch", "router", "_COMMAND_\nDISPATCH", 420, 548, N_BACK),
        IconNode("log_search", "document", "log_search", 620, 548, N_PROC),
        IconNode("log_fail", "document", "log_did_\nfailures", 790, 548, N_PROC),
        IconNode("log_health", "document", "log_health", 960, 548, N_PROC),
        IconNode("log_more", "document", "log_trends\n+ 5 more", 1130, 548, N_PROC),
        # DATA tier
        IconNode("logfiles", "folder", "Application\nlog files", 400, 765, N_STORE),
        IconNode("sqlitelog", "database", "SQLite\nlog index", 780, 765, N_STORE),
    ]
    for n in nodes:
        parts.append(render_icon_node(n))

    # ── Edges ────────────────────────────────────────────────────────
    R = 24  # node circle radius

    # Helper: horizontal edge between two colinear nodes
    def h_edge(n1: IconNode, n2: IconNode, color: str, step: int = 0, dashed: bool = False) -> FlowEdge:
        return FlowEdge([(n1.cx + R, n1.cy), (n2.cx - R, n2.cy)], color, dashed, step)

    # Blue deterministic path ①-⑨
    edges: List[FlowEdge] = [
        h_edge(nodes[0], nodes[1], C_DET, step=1),                    # ① user→chat
        h_edge(nodes[1], nodes[2], C_DET, step=2),                    # ② chat→participant
        # ③ participant → det_parser (up-right L-bend)
        FlowEdge([
            (514, 215), (597, 215), (597, 150), (676, 150)
        ], C_DET, step=3),
        # ④ det_parser → tool (down-right L-bend)
        FlowEdge([
            (724, 150), (813, 150), (813, 215), (896, 215)
        ], C_DET, step=4),
        h_edge(nodes[5], nodes[6], C_DET, step=5),                    # ⑤ tool→backend
        # ⑥ backend → cli (orthogonal transport crossing)
        FlowEdge([
            (1140, 239), (1140, 408), (200, 408), (200, 524)
        ], C_SHARED, step=6, step_pos=(1140, 323)),
        h_edge(nodes[7], nodes[8], C_SHARED, step=7),                 # ⑦ cli→dispatch
        h_edge(nodes[8], nodes[9], C_SHARED, step=8),                 # ⑧ dispatch→log_search
        # ⑨ log_search → sqlite (vertical drop into data tier)
        FlowEdge([
            (620, 572), (620, 660), (780, 660), (780, 741)
        ], C_DATA, True, step=9),
    ]

    # Green NLP alternative (no step numbers, green edges)
    edges.extend([
        # participant → LLM (down-right L-bend)
        FlowEdge([
            (514, 215), (597, 215), (597, 298), (676, 298)
        ], C_NLP),
        # LLM → tool (up-right L-bend)
        FlowEdge([
            (724, 298), (813, 298), (813, 215), (896, 215)
        ], C_NLP),
    ])

    # Purple data-store edges (dashed) — chain from log_search outward
    edges.extend([
        h_edge(nodes[9], nodes[10], C_DATA, dashed=True),              # log_search→log_fail
        h_edge(nodes[10], nodes[11], C_DATA, dashed=True),            # log_fail→log_health
        h_edge(nodes[11], nodes[12], C_DATA, dashed=True),            # log_health→log_more
        # log files → sqlite (sync relationship)
        FlowEdge([(424, 765), (756, 765)], C_DATA, True),
    ])

    for e in edges:
        parts.append(render_edge(e))

    # ── Right panel: Legend + Annotations ─────────────────────────────
    parts.append(render_legend(1370, 85, 510, 280))

    parts.append(render_annotation(Annotation(
        1370, 380, 510, 210,
        "Deterministic example",
        [
            "/logs search subject:FREMF; days:3",
            "→ parseDeterministicLogsPrompt()",
            '→ backendCall("log_search", {subject, days})',
            "",
            "NLP example",
            '"Any failures in last 3 days for FREMF?"',
            "→ agentLoop → LLM selects log_search",
            "  + log_did_failures → backendCall × 2",
        ],
    )))

    parts.append(render_annotation(Annotation(
        1370, 605, 510, 195,
        "Response path",
        [
            "SQLite query result",
            "  → CliResponse JSON (success + data)",
            "  → frp_backend.js (stdout line)",
            "  → tool.js → participant.js",
            "  → formatted table + inline next actions",
            "",
            "NLP responses are conversational summaries",
            "with suggested follow-up prompts.",
        ],
        bg="#F0F9FF",
        stroke="#3B82F6",
    )))

    # ── Fork / merge labels ──────────────────────────────────────────
    # Small "Deterministic" / "NLP" labels near the fork
    parts.append(
        f'<text x="600" y="133" fill="{C_DET}" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="10" font-weight="600" '
        f'font-style="italic">deterministic</text>'
    )
    parts.append(
        f'<text x="600" y="330" fill="{C_NLP}" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="10" font-weight="600" '
        f'font-style="italic">NLP / agentLoop</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


# ── /triage flow builder ─────────────────────────────────────────────

def build_triage_flow() -> str:
    """Build complete SVG for the /triage use-case flow."""

    parts: List[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1200" viewBox="0 0 1920 1200">',
        render_defs(),
        f'<rect width="1920" height="1200" fill="{CANVAS_BG}"/>',
    ]

    # Title
    parts.append(render_title(
        "Use Case: /triage — Email Triage & Job Matching",
        "Multi-loop pipeline from .msg email to confidence-scored match results",
    ))

    # ── Containers ───────────────────────────────────────────────────
    client = Container(40, 85, 1260, 300, "VS Code Process", "Client", N_UI)
    server = Container(40, 430, 1260, 540, "Python Backend", "Server", N_BACK)
    data = Container(40, 990, 1260, 145, "Persistent Stores", "Data", N_STORE)
    parts.append(render_container(client))
    parts.append(render_container(server))
    parts.append(render_container(data))

    # Triage pipeline subgroup
    parts.append(render_subgroup(SubGroup(80, 468, 1180, 490, "Triage Pipeline")))

    # Transport label
    parts.append(render_transport_label(408, 80, 1260, "JSON Line Transport (stdin / stdout)"))

    # ── Loop Bands ───────────────────────────────────────────────────
    parts.append(render_loop_band(LoopBand(
        90, 570, 1160, 105,
        "⟳ Loop 1 — Job Match", "for each job in Settings.xml",
        C_DET, "#EFF6FF",
    )))
    parts.append(render_loop_band(LoopBand(
        90, 700, 1160, 110,
        "⟳ Loop 2 — DID Match", "for each deal under best-match ServicerID",
        C_DATA, "#F5F3FF",
    )))
    # Nested attachment loop inside Loop 2
    parts.append(render_loop_band(LoopBand(
        560, 715, 310, 82,
        "⟳ Nested — per attachment", "filename keyword scan",
        N_AI, "#FDF2F8",
    )))

    # ── Icon Nodes ───────────────────────────────────────────────────
    nodes = [
        # CLIENT tier (0-6)
        IconNode("user",        "person",   "Operator",                 130, 215, N_UI),
        IconNode("chat",        "chat",     "Copilot Chat\n@frp",      300, 215, N_UI),
        IconNode("participant", "gear",     "participant.js\nparse + route", 490, 215, N_PROC),
        IconNode("det_parser",  "document", "parseTriage\nPrompt()",    700, 150, N_PROC),
        IconNode("llm",         "brain",    "agentLoop\nemail_triage",  700, 298, N_AI),
        IconNode("tool",        "config",   "tool.js\ninject config",   920, 215, N_PROC),
        IconNode("backend",     "terminal", "frp_backend.js\nprocess bridge", 1140, 215, N_BACK),
        # SERVER tier — entry row (7-9)
        IconNode("cli",         "python",   "cli/main.py\n--server",    150, 505, N_BACK),
        IconNode("dispatch",    "router",   "DISPATCH\ntriage_verify",  300, 505, N_BACK),
        IconNode("msgparser",   "document", "MsgParser\n.msg → EmailInfo", 475, 505, N_PROC),
        # SERVER tier — Loop 1: Job Match (10-12)
        IconNode("matcher",     "gear",     "TriageMatcher\n.match()",  220, 618, N_PROC),
        IconNode("check",       "config",   "_check_job()\nsender|mailbox|subj", 470, 618, N_PROC),
        IconNode("rank",        "document", "score & rank\nMatchResult[]", 730, 618, N_PROC),
        # SERVER tier — Loop 2: DID Match (13-16)
        IconNode("get_deals",   "database", "deal_repo\nget_deals(sid)", 220, 750, N_STORE),
        IconNode("subj_kw",     "document", "keyword in\nsubject",      440, 750, N_PROC),
        IconNode("file_kw",     "folder",   "keyword in\nfilenames",    700, 750, N_PROC),
        IconNode("did_out",     "document", "DIDMatch[]\nhit list",     960, 750, N_PROC),
        # SERVER tier — cross-reference row (17-19)
        IconNode("log_xref",    "database", "log cross-\nreference",    220, 860, N_STORE),
        IconNode("tmpl_stg",    "database", "template staging\nlookup", 440, 860, N_STORE),
        IconNode("confidence",  "gear",     "confidence\nassessment",   680, 860, N_PROC),
        # DATA tier (20-24)
        IconNode("settings_xml", "folder",   "Settings.xml\njob definitions", 140, 1060, N_STORE),
        IconNode("msg_files",    "document", ".msg files\nemail source",     350, 1060, N_STORE),
        IconNode("did_ref",      "database", "tblExternalDIDRef\ndeal mappings", 560, 1060, N_STORE),
        IconNode("sqlite_log",   "database", "SQLite\nlog index",            770, 1060, N_STORE),
        IconNode("tmpl_stg_db",  "database", "tblTemplate\nStaging",          980, 1060, N_STORE),
    ]
    for n in nodes:
        parts.append(render_icon_node(n))

    # ── Edges ────────────────────────────────────────────────────────
    R = 24

    def h_edge(n1: IconNode, n2: IconNode, color: str,
               step: int = 0, dashed: bool = False) -> FlowEdge:
        return FlowEdge([(n1.cx + R, n1.cy), (n2.cx - R, n2.cy)],
                        color, dashed, step)

    edges: List[FlowEdge] = [
        # ── Blue deterministic path ①–⑤ ──────────────────────────
        h_edge(nodes[0], nodes[1], C_DET, step=1),          # ① user→chat
        h_edge(nodes[1], nodes[2], C_DET, step=2),          # ② chat→participant
        # ③ participant → det_parser (up-right L-bend)
        FlowEdge([
            (514, 215), (597, 215), (597, 150), (676, 150)
        ], C_DET, step=3),
        # ④ det_parser → tool (down-right L-bend merge)
        FlowEdge([
            (724, 150), (813, 150), (813, 215), (896, 215)
        ], C_DET, step=4),
        h_edge(nodes[5], nodes[6], C_DET, step=5),          # ⑤ tool→backend

        # ── Transport crossing ⑥ ─────────────────────────────────
        FlowEdge([
            (1140, 239), (1140, 408), (150, 408), (150, 481)
        ], C_SHARED, step=6, step_pos=(1140, 323)),

        # ── Server entry ⑦–⑧ ─────────────────────────────────────
        h_edge(nodes[7], nodes[8], C_SHARED, step=7),       # ⑦ cli→dispatch
        h_edge(nodes[8], nodes[9], C_SHARED, step=8),       # ⑧ dispatch→msgParser

        # ── ⑨ msgParser → Loop 1 (L-bend down-left-down) ────────
        FlowEdge([
            (475, 529), (475, 555), (220, 555), (220, 594)
        ], C_SHARED, step=9, step_pos=(350, 555)),

        # ── Loop 1 internals (no step numbers) ──────────────────
        h_edge(nodes[10], nodes[11], C_SHARED),              # matcher→check
        h_edge(nodes[11], nodes[12], C_SHARED),              # check→rank

        # ── ⑩ Loop 1 → Loop 2 (L-bend down-left-down) ──────────
        FlowEdge([
            (730, 642), (730, 680), (220, 680), (220, 726)
        ], C_SHARED, step=10, step_pos=(475, 680)),

        # ── Loop 2 internals ─────────────────────────────────────
        h_edge(nodes[13], nodes[14], C_SHARED),              # get_deals→subj_kw
        h_edge(nodes[14], nodes[15], C_SHARED),              # subj_kw→file_kw
        h_edge(nodes[15], nodes[16], C_SHARED),              # file_kw→did_out

        # ── ⑪ Loop 2 → cross-ref (L-bend down-left) ────────────
        FlowEdge([
            (960, 774), (960, 838), (244, 838)
        ], C_SHARED, step=11, step_pos=(960, 810)),

        # ── Cross-ref internals ──────────────────────────────────
        h_edge(nodes[17], nodes[18], C_SHARED),              # log→tmpl
        h_edge(nodes[18], nodes[19], C_SHARED),              # tmpl→confidence
    ]

    # Green NLP alternative (no step numbers)
    edges.extend([
        FlowEdge([
            (514, 215), (597, 215), (597, 298), (676, 298)
        ], C_NLP),
        FlowEdge([
            (724, 298), (813, 298), (813, 215), (896, 215)
        ], C_NLP),
    ])

    # Data-store read stubs (purple dashed, up from data tier)
    for dn in nodes[20:25]:
        edges.append(
            FlowEdge([(dn.cx, dn.cy - R), (dn.cx, 975)], C_DATA, True))

    for e in edges:
        parts.append(render_edge(e))

    # ── Right panel: Legend + Annotations ─────────────────────────
    parts.append(render_legend(1370, 85, 510, 280,
                               det_label="Deterministic path (①–⑪)"))

    parts.append(render_annotation(Annotation(
        1370, 380, 510, 220,
        "Triage modes",
        [
            '/triage verify "report.msg"',
            "  → parse .msg → match jobs → DID lookup → log xref",
            "",
            "/triage match sender:x@fay.com; subject:Monthly",
            "  → match against all jobs without .msg file",
            "",
            '/triage new "unknown.msg"',
            "  → no match → suggest parser + template + clone",
            "",
            'NLP: \"Is this email already monitored?\"',
            "  → agentLoop → triage_verify tool",
        ],
    )))

    parts.append(render_annotation(Annotation(
        1370, 615, 510, 250,
        "Loop detail",
        [
            "Loop 1 — Job Match",
            "  N = all jobs in Settings.xml",
            "  Per job: check sender, mailbox, subject filters",
            "  Output: MatchResult[] ranked by type + confidence",
            "",
            "Loop 2 — DID Match (best match ServicerID)",
            "  N = deals from tblExternalDIDRef",
            "  Per deal: keyword vs subject, then per-attachment",
            "  Output: DIDMatch[] with keyword + match location",
            "",
            "Cross-Reference (parallel)",
            "  Log events + template staging lookups",
            "  Output: TriageResult with confidence level",
        ],
        bg="#F0F9FF",
        stroke="#3B82F6",
    )))

    parts.append(render_annotation(Annotation(
        1370, 880, 510, 190,
        "Data sources",
        [
            "Settings.xml → Loop 1 (all jobs loaded at init)",
            ".msg file → MsgParser (email extraction)",
            "tblExternalDIDRef → Loop 2 (DID lookup)",
            "SQLite log index → cross-reference",
            "tblTemplateStaging → cross-reference",
            "",
            "Confidence levels:",
            '  \"completed\" — DID + template run evidence',
            '  \"processed\" — DID + log evidence',
            '  \"monitored\" — job match only, no DIDs',
        ],
        bg="#FEF3C7",
        stroke="#D97706",
    )))

    # ── Fork / merge labels ──────────────────────────────────────
    parts.append(
        f'<text x="600" y="133" fill="{C_DET}" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="10" font-weight="600" '
        f'font-style="italic">deterministic</text>'
    )
    parts.append(
        f'<text x="600" y="330" fill="{C_NLP}" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="10" font-weight="600" '
        f'font-style="italic">NLP / agentLoop</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


# ── Executive architecture flow builder ──────────────────────────────

def build_executive_flow() -> str:
    """Build high-level executive architecture diagram."""

    W, H = 1920, 1050
    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">',
        render_defs(),
        f'<rect width="{W}" height="{H}" fill="{CANVAS_BG}"/>',
        render_title(
            "FRP Agent \u2014 Executive Architecture",
            "High-level component view: VS Code extension \u2192 Python backend \u2192 persistent stores",
        ),
    ]

    # ── Boundary containers ──────────────────────────────────────
    client = Container(40, 85, 1260, 310, "User Workstation", "Client", N_UI)
    server = Container(40, 445, 1260, 290, "Python Backend", "Server", N_BACK)
    data_c = Container(40, 785, 1260, 175, "Persistent Stores", "Data", N_STORE)
    for c in [client, server, data_c]:
        parts.append(render_container(c))

    # Transport boundary
    parts.append(render_transport_label(408, 80, 1260,
                                        "JSON Line Protocol (stdin / stdout)"))

    # ── Sub-groups ───────────────────────────────────────────────
    parts.append(render_subgroup(SubGroup(345, 108, 935, 272, "Extension Layer")))
    parts.append(render_subgroup(SubGroup(325, 475, 690, 240, "Domain Engines")))

    # ── Component Cards ──────────────────────────────────────────
    cards = [
        # CLIENT tier ─────────────────────────────────────────────
        # Left column: actor + IDE
        ComponentCard(65, 135, 240, 68,
                      "person", "User", "GSF IR Team member", N_UI),         # 0
        ComponentCard(65, 230, 240, 68,
                      "terminal", "VS Code IDE", "Editor + integrated terminal",
                      N_UI),                                                  # 1
        # Extension Layer — row 1
        ComponentCard(370, 130, 200, 62,
                      "chat", "Copilot Chat", "@frp participant", N_UI),      # 2
        ComponentCard(595, 130, 200, 62,
                      "document", "Slash Commands",
                      "Deterministic routing", N_PROC),                       # 3
        ComponentCard(820, 130, 200, 62,
                      "config", "Tool Bridge",
                      "Config + backend spawn", N_PROC),                      # 4
        ComponentCard(1045, 130, 200, 62,
                      "gear", "Response Renderer",
                      "Markdown + next actions", N_PROC),                     # 5
        # Extension Layer — row 2
        ComponentCard(370, 218, 200, 62,
                      "brain", "Agent Loop",
                      "NLP \u2192 LLM tool-call", N_AI),                          # 6
        ComponentCard(595, 218, 200, 62,
                      "folder", "Local Resources",
                      "Email + SFTP settings", N_STORE),                      # 7

        # SERVER tier ─────────────────────────────────────────────
        ComponentCard(65, 495, 220, 68,
                      "python", "CLI Server",
                      "main.py --server mode", N_BACK),                       # 8
        ComponentCard(65, 590, 220, 68,
                      "router", "Command Router",
                      "DISPATCH \u2192 handler", N_BACK),                         # 9
        # Domain Engines
        ComponentCard(350, 500, 200, 62,
                      "folder", "XML Management",
                      "CRUD, Clone, Diff, Rollback", N_PROC),                 # 10
        ComponentCard(575, 500, 200, 62,
                      "document", "Log Analytics",
                      "Search, Health, Trends", N_PROC),                      # 11
        ComponentCard(350, 590, 200, 62,
                      "chat", "Email Triage",
                      "Match, Verify, Analyze", N_PROC),                      # 12
        ComponentCard(575, 590, 200, 62,
                      "gear", "Intel & Coverage",
                      "Collisions, Orphans, Gaps", N_PROC),                   # 13
        # Backup + Analysis (right)
        ComponentCard(1050, 510, 220, 68,
                      "folder", "Backup Manager",
                      "Versioned XML backups", N_BACK),                       # 14
        ComponentCard(1050, 600, 220, 68,
                      "document", "Analysis Engine",
                      "Consolidation + trends", N_PROC),                      # 15

        # DATA tier ───────────────────────────────────────────────
        ComponentCard(65, 820, 265, 68,
                      "folder", "Settings XML",
                      "Email + SFTP job definitions", N_STORE),               # 16
        ComponentCard(360, 820, 265, 68,
                      "database", "SQLite Cache",
                      "Job index + log index", N_STORE),                      # 17
        ComponentCard(655, 820, 265, 68,
                      "database", "SQL Server",
                      "DID refs + template staging", N_STORE),                # 18
        ComponentCard(950, 820, 265, 68,
                      "folder", "File System",
                      "App logs, .msg files, backups", N_STORE),              # 19
    ]
    for card in cards:
        parts.append(render_component_card(card))

    # Feature pills (slash commands) inside Extension Layer row 2
    parts.append(render_feature_pills(
        820, 225,
        ["/jobs", "/logs", "/triage", "/clone",
         "/deals", "/staging", "/sync", "/rebuild-db"],
        N_PROC, cols=4,
    ))

    # ── Flow Edges ───────────────────────────────────────────────
    edges: List[FlowEdge] = [
        # Blue: user interaction flow
        FlowEdge([(188, 203), (188, 230)], C_DET),                     # Operator → VS Code
        FlowEdge([(305, 264), (340, 264),
                  (340, 161), (370, 161)], C_DET),                     # VS Code → Chat
        FlowEdge([(570, 161), (595, 161)], C_DET),                     # Chat → Slash
        FlowEdge([(795, 161), (820, 161)], C_DET),                     # Slash → Tool Bridge
        FlowEdge([(1020, 161), (1045, 161)], C_DET),                   # Tool Bridge → Renderer

        # Green: NLP alternative path
        FlowEdge([(470, 192), (470, 218)], C_NLP),                     # Chat → Agent Loop
        FlowEdge([(570, 249), (810, 249),
                  (810, 192)], C_NLP),                                 # Agent → Tool Bridge merge

        # Gray: transport crossing
        FlowEdge([(830, 380), (830, 408),
                  (175, 408), (175, 495)], C_SHARED),                  # Ext → CLI Server

        # Gray: server-side flow
        FlowEdge([(175, 563), (175, 590)], C_SHARED),                  # CLI → Router
        FlowEdge([(285, 624), (325, 624)], C_SHARED),                  # Router → Engines
        FlowEdge([(1015, 562), (1050, 544)], C_SHARED),                # Engines → Backup
        FlowEdge([(1015, 624), (1050, 634)], C_SHARED),                # Engines → Analysis

        # Violet dashed: data store access (server bottom → data top)
        FlowEdge([(197, 735), (197, 820)], C_DATA, True),              # Settings XML
        FlowEdge([(492, 735), (492, 820)], C_DATA, True),              # SQLite
        FlowEdge([(787, 735), (787, 820)], C_DATA, True),              # SQL Server
        FlowEdge([(1082, 735), (1082, 820)], C_DATA, True),            # File System
    ]
    for e in edges:
        parts.append(render_edge(e))

    # ── Right Panel ──────────────────────────────────────────────
    lx, ly, lw = 1370, 85, 510

    # Custom legend for executive diagram
    lh = 270
    parts.append(
        f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="8" '
        f'fill="white" stroke="{SUB_STROKE}" stroke-width="1.2"/>'
    )
    parts.append(
        f'<text x="{lx + 14}" y="{ly + 22}" fill="{TEXT_DARK}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="13" font-weight="700">'
        f'Legend</text>'
    )
    parts.append(
        f'<line x1="{lx + 14}" y1="{ly + 30}" x2="{lx + lw - 14}" y2="{ly + 30}" '
        f'stroke="{SUB_STROKE}" stroke-width="0.5"/>'
    )
    leg_edges = [
        (C_DET, False, "User interaction flow"),
        (C_NLP, False, "NLP / AI alternative path"),
        (C_SHARED, False, "Command transport"),
        (C_DATA, True, "Data store access"),
    ]
    for i, (col, dashed, label) in enumerate(leg_edges):
        ey = ly + 52 + i * 28
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        parts.append(
            f'<line x1="{lx + 18}" y1="{ey}" x2="{lx + 60}" y2="{ey}" '
            f'stroke="{col}" stroke-width="2.5"{dash}/>'
        )
        parts.append(f'<circle cx="{lx + 60}" cy="{ey}" r="4" fill="{col}"/>')
        parts.append(
            f'<text x="{lx + 72}" y="{ey + 4}" fill="{TEXT_DARK}" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11">'
            f'{xml_esc(label)}</text>'
        )
    node_entries = [
        (N_UI, "User-facing / UI"),
        (N_PROC, "Processing / routing"),
        (N_BACK, "Backend / CLI engine"),
        (N_STORE, "Data store / config"),
        (N_AI, "AI / LLM"),
    ]
    ny = ly + 52 + len(leg_edges) * 28 + 10
    for i, (col, label) in enumerate(node_entries):
        ey = ny + i * 22
        parts.append(f'<circle cx="{lx + 28}" cy="{ey}" r="7" fill="{col}"/>')
        parts.append(
            f'<text x="{lx + 42}" y="{ey + 4}" fill="{TEXT_DARK}" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10">'
            f'{xml_esc(label)}</text>'
        )

    # Annotation: How It Works
    parts.append(render_annotation(Annotation(
        lx, 370, lw, 220,
        "How It Works",
        [
            "FRP Agent is a VS Code chat extension (@frp)",
            "that monitors email & SFTP transfer jobs.",
            "",
            "Two interaction paths:",
            "  Blue \u2014 typed slash commands (/jobs, /logs\u2026)",
            "  Green \u2014 natural language via LLM",
            "",
            "Both paths converge at the Tool Bridge,",
            "which spawns a Python backend over JSON",
            "line transport (stdin/stdout).",
        ],
    )))

    # Annotation: Key Capabilities
    parts.append(render_annotation(Annotation(
        lx, 605, lw, 265,
        "Key Capabilities",
        [
            "XML Job Configuration",
            "  CRUD, clone, diff, rollback with backups",
            "",
            "Log Search & Analytics",
            "  Health scoring, DID failures, trends",
            "",
            "Email Triage & Job Matching",
            "  .msg parsing, multi-loop confidence scoring",
            "",
            "Intel & Coverage Analysis",
            "  Collision detection, orphan finding, gap reports",
            "",
            "Deal & Template Staging Lookups",
        ],
        bg="#F0F9FF",
        stroke="#3B82F6",
    )))

    # Fork path labels near the Chat → Slash / Agent fork
    parts.append(
        f'<text x="575" y="120" fill="{C_DET}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="9" font-weight="600" '
        f'font-style="italic">deterministic</text>'
    )
    parts.append(
        f'<text x="478" y="210" fill="{C_NLP}" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="9" font-weight="600" '
        f'font-style="italic">NLP</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    svg = build_logs_flow()
    out_path = OUTPUT_DIR / "logs-flow.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {out_path}")

    svg = build_triage_flow()
    out_path = OUTPUT_DIR / "triage-flow.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {out_path}")

    svg = build_executive_flow()
    out_path = OUTPUT_DIR / "executive-architecture.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
