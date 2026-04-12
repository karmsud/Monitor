from __future__ import annotations
from dataclasses import dataclass
import re
from pathlib import Path
import shutil
from typing import Dict, List, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture" / "frp-architecture.drawio"
SVG_OUTPUT_DIR = ROOT / "docs" / "architecture" / "svg"
ARCHIVE_DIR = ROOT / "docs" / "architecture" / "archived"
ARCHIVE_OUTPUT = ARCHIVE_DIR / "frp-architecture-archive.drawio"
ARCHIVE_SVG_OUTPUT_DIR = ARCHIVE_DIR / "svg"
SHOW_EDGE_LABELS = False


@dataclass
class Box:
    id: str
    text: str
    x: float
    y: float
    width: float
    height: float
    style: str
    parent: str = "1"


@dataclass
class Edge:
    id: str
    source: str
    target: str
    text: str = ""
    style: str = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1.5;endArrow=block;endFill=1;labelBackgroundColor=none;labelBorderColor=none;"
    parent: str = "1"


class PageBuilder:
    def __init__(self, name: str, page_id: str):
        self.name = name
        self.page_id = page_id
        self.boxes: List[Box] = []
        self.edges: List[Edge] = []
        self._init_root()

    def _init_root(self) -> None:
        self.root = Element("mxGraphModel", {
            "dx": "1600",
            "dy": "900",
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": "1920",
            "pageHeight": "1080",
            "math": "0",
            "shadow": "0",
        })
        root_node = SubElement(self.root, "root")
        SubElement(root_node, "mxCell", {"id": "0"})
        SubElement(root_node, "mxCell", {"id": "1", "parent": "0"})
        self.root_node = root_node

    def add_box(self, box: Box) -> None:
        self.boxes.append(box)
        cell = SubElement(self.root_node, "mxCell", {
            "id": box.id,
            "value": box.text,
            "style": box.style,
            "vertex": "1",
            "parent": box.parent,
        })
        SubElement(cell, "mxGeometry", {
            "x": str(box.x),
            "y": str(box.y),
            "width": str(box.width),
            "height": str(box.height),
            "as": "geometry",
        })

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)
        cell = SubElement(self.root_node, "mxCell", {
            "id": edge.id,
            "value": edge.text,
            "style": edge.style,
            "edge": "1",
            "parent": edge.parent,
            "source": edge.source,
            "target": edge.target,
        })
        SubElement(cell, "mxGeometry", {
            "relative": "1",
            "as": "geometry",
        })

    def to_diagram(self) -> Element:
        diagram = Element("diagram", {"id": self.page_id, "name": self.name})
        diagram.text = tostring(self.root, encoding="unicode")
        return diagram

    def get_absolute_box_map(self) -> Dict[str, Box]:
        return {box.id: box for box in self.boxes}


BASE_TEXT = "whiteSpace=wrap;html=1;rounded=1;fontSize=13;fontFamily=Helvetica;align=center;verticalAlign=middle;"
SWIMLANE = "swimlane;fontStyle=1;horizontal=0;startSize=28;rounded=0;html=1;whiteSpace=wrap;"

STYLE_THEMES: Dict[str, Dict[str, str]] = {
    "clean": {
        "title": "shape=mxgraph.basic.rounded_frame;whiteSpace=wrap;html=1;fontSize=24;fontStyle=1;fillColor=#0B3D91;strokeColor=#082B66;fontColor=#FFFFFF;",
        "lane": SWIMLANE + "fillColor=#F7F9FC;strokeColor=#C9D2E3;fontColor=#1C2A39;",
        "primary": BASE_TEXT + "fillColor=#DCEBFF;strokeColor=#4F81BD;fontColor=#10233A;strokeWidth=2;",
        "secondary": BASE_TEXT + "fillColor=#EAF6EE;strokeColor=#5B9B6B;fontColor=#163322;strokeWidth=2;",
        "accent": BASE_TEXT + "fillColor=#FFF1D6;strokeColor=#C6861A;fontColor=#4A3300;strokeWidth=2;",
        "store": BASE_TEXT + "fillColor=#F3EEFF;strokeColor=#7B61C8;fontColor=#241742;strokeWidth=2;",
        "note": BASE_TEXT + "fillColor=#FFF8CC;strokeColor=#B89B00;fontColor=#5E4B00;dashed=1;strokeWidth=1.5;",
        "edge": "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#425466;strokeWidth=1.5;endArrow=block;endFill=1;labelBackgroundColor=none;labelBorderColor=none;",
    },
    "visio": {
        "title": "shape=mxgraph.basic.rounded_frame;whiteSpace=wrap;html=1;fontSize=24;fontStyle=1;fillColor=#1F497D;strokeColor=#17375E;fontColor=#FFFFFF;",
        "lane": SWIMLANE + "fillColor=#FFFFFF;strokeColor=#7F7F7F;fontColor=#1F1F1F;",
        "primary": BASE_TEXT + "fillColor=#D9E2F3;strokeColor=#4F81BD;fontColor=#1F1F1F;strokeWidth=1.5;",
        "secondary": BASE_TEXT + "fillColor=#E2F0D9;strokeColor=#70AD47;fontColor=#1F1F1F;strokeWidth=1.5;",
        "accent": BASE_TEXT + "fillColor=#FCE4D6;strokeColor=#C55A11;fontColor=#1F1F1F;strokeWidth=1.5;",
        "store": BASE_TEXT + "fillColor=#EDEDED;strokeColor=#7F7F7F;fontColor=#1F1F1F;strokeWidth=1.5;",
        "note": BASE_TEXT + "fillColor=#FFF2CC;strokeColor=#BF9000;fontColor=#3F3F3F;dashed=1;strokeWidth=1.2;",
        "edge": "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#5B5B5B;strokeWidth=1.3;endArrow=block;endFill=1;labelBackgroundColor=none;labelBorderColor=none;",
    },
    "modern": {
        "title": "shape=mxgraph.basic.rounded_frame;whiteSpace=wrap;html=1;fontSize=24;fontStyle=1;fillColor=#1A1D29;strokeColor=#10131A;fontColor=#FFFFFF;",
        "lane": SWIMLANE + "fillColor=#F3F5F7;strokeColor=#D7DEE7;fontColor=#111827;",
        "primary": BASE_TEXT + "arcSize=16;fillColor=#BEE3F8;strokeColor=#0EA5E9;fontColor=#082F49;strokeWidth=2;",
        "secondary": BASE_TEXT + "arcSize=16;fillColor=#C6F6D5;strokeColor=#10B981;fontColor=#064E3B;strokeWidth=2;",
        "accent": BASE_TEXT + "arcSize=16;fillColor=#FDE68A;strokeColor=#F59E0B;fontColor=#78350F;strokeWidth=2;",
        "store": BASE_TEXT + "arcSize=16;fillColor=#DDD6FE;strokeColor=#8B5CF6;fontColor=#312E81;strokeWidth=2;",
        "note": BASE_TEXT + "arcSize=16;fillColor=#FCE7F3;strokeColor=#EC4899;fontColor=#831843;dashed=1;strokeWidth=1.5;",
        "edge": "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#475569;strokeWidth=1.6;endArrow=block;endFill=1;labelBackgroundColor=none;labelBorderColor=none;",
    },
}


def simplify_edges(edges: List[Edge]) -> List[Edge]:
    if SHOW_EDGE_LABELS:
        return edges

    for edge in edges:
        edge.text = ""
    return edges


def add_title(page: PageBuilder, title: str, subtitle: str, theme: Dict[str, str]) -> None:
    page.add_box(Box("title", f"{title}<br/><font style='font-size:14px;font-weight:400;'>{subtitle}</font>", 40, 20, 1840, 60, theme["title"]))


def add_lane(page: PageBuilder, box_id: str, title: str, x: float, y: float, w: float, h: float, theme: Dict[str, str]) -> None:
    page.add_box(Box(box_id, title, x, y, w, h, theme["lane"]))


def build_master_page(name: str, page_id: str, theme_name: str, technical: bool) -> PageBuilder:
    theme = STYLE_THEMES[theme_name]
    page = PageBuilder(name, page_id)
    subtitle = "Executive summary of runtime architecture and system boundaries" if not technical else "Technical decomposition of extension, CLI, backend domains, and stores"
    add_title(page, "FRP Agent Master Architecture", subtitle, theme)

    add_lane(page, "lane1", "Operator Interface", 40, 110, 260, 860, theme)
    add_lane(page, "lane2", "VS Code Extension", 310, 110, 340, 860, theme)
    add_lane(page, "lane3", "Python CLI Boundary", 660, 110, 250, 860, theme)
    add_lane(page, "lane4", "Backend Domains", 920, 110, 560, 860, theme)
    add_lane(page, "lane5", "Persistent Stores", 1490, 110, 390, 860, theme)

    page.add_box(Box("user", "Architect / Operator", 70, 180, 200, 70, theme["primary"], "lane1"))
    page.add_box(Box("chat", "GitHub Copilot Chat\nNatural-language prompts", 70, 320, 200, 90, theme["accent"], "lane1"))

    page.add_box(Box("ext", "extension/extension.js\nactivation + backend bootstrap", 370, 160, 220, 80, theme["primary"], "lane2"))
    page.add_box(Box("participant", "chat/participant.js\nslash routing + deterministic orchestration", 350, 300, 260, 100, theme["secondary"], "lane2"))
    page.add_box(Box("tool", "copilot/tool.js\nconfig injection + backendCall() + timeouts", 350, 470, 260, 90, theme["secondary"], "lane2"))
    page.add_box(Box("backendjs", "lib/frp_backend.js\npersistent process + JSON line transport", 350, 630, 260, 90, theme["primary"], "lane2"))
    page.add_box(Box("config", "package.json\nchat commands + extension settings", 370, 790, 220, 80, theme["accent"], "lane2"))

    page.add_box(Box("server", "cli/main.py\nargparse subcommands\nJSON stdout contract", 700, 250, 170, 100, theme["primary"], "lane3"))
    page.add_box(Box("dispatch", "_COMMAND_DISPATCH\nsearch, clone, logs, triage, analysis, staging", 690, 470, 190, 110, theme["secondary"], "lane3"))
    page.add_box(Box("rpc", "--server mode\nready / ping / exit\nstdin request -> stdout response", 695, 660, 180, 100, theme["accent"], "lane3"))

    if technical:
        page.add_box(Box("xml", "XML domain\nparser, writer, CRUD, clone, diff, rollback, templates", 970, 155, 200, 120, theme["primary"], "lane4"))
        page.add_box(Box("cache", "SQLite XML cache\nbackend/db/xml_index.py", 1230, 155, 200, 120, theme["store"], "lane4"))
        page.add_box(Box("db", "Operational DB access\ndeal_repo + template_staging_repo\nMySQL/MSSQL adapters", 970, 360, 200, 120, theme["secondary"], "lane4"))
        page.add_box(Box("logs", "Logs domain\nparser, indexer, analytics", 1230, 360, 200, 120, theme["secondary"], "lane4"))
        page.add_box(Box("triage", "Triage domain\nmsg parser, matcher, analyzer", 970, 555, 200, 120, theme["accent"], "lane4"))
        page.add_box(Box("intel", "Intel + Analysis\ncoverage, orphans, collisions\nhealth, impact, trends, performance", 1230, 555, 200, 120, theme["accent"], "lane4"))
        page.add_box(Box("rules", "Architecture rules\nXML is source of truth\nall writes via XmlWriter\nlog sync is explicit", 1000, 735, 400, 120, theme["note"], "lane4"))
    else:
        page.add_box(Box("domains", "Backend service domains\nXML configuration\nLog ingestion and analytics\nDeal and staging repositories\nTriage and impact analysis", 1000, 250, 400, 220, theme["primary"], "lane4"))
        page.add_box(Box("rules", "Operating rules\nXML is authoritative\nSQLite accelerates lookup\nbackups are mandatory on writes\nlog refresh is user-triggered", 1000, 620, 400, 160, theme["note"], "lane4"))

    page.add_box(Box("settingsxml", "Email + SFTP Settings.xml\nsource of truth", 1560, 170, 250, 90, theme["store"], "lane5"))
    page.add_box(Box("backup", "backup/ snapshots\nrollback points", 1560, 310, 250, 80, theme["store"], "lane5"))
    page.add_box(Box("cachedb", "SQLite XML cache\nemail_jobs + sftp_jobs", 1560, 450, 250, 90, theme["store"], "lane5"))
    page.add_box(Box("logdb", "SQLite log index\nlog_events + indexed_files", 1560, 590, 250, 90, theme["store"], "lane5"))
    page.add_box(Box("opdb", "tblExternalDIDRef\ntblTemplateStaging\nMySQL or MSSQL", 1560, 730, 250, 110, theme["store"], "lane5"))

    edge_style = theme["edge"]
    edges = [
        Edge("e1", "user", "chat", "asks about jobs, logs, staging", edge_style),
        Edge("e2", "chat", "participant", "prompt + slash command", edge_style),
        Edge("e3", "participant", "tool", "normalized backend call", edge_style),
        Edge("e4", "tool", "backendjs", "CLI args + config injection", edge_style),
        Edge("e5", "backendjs", "rpc", "persistent JSON request", edge_style),
        Edge("e6", "rpc", "server", "argparse parse + dispatch", edge_style),
        Edge("e7", "server", "dispatch", "command handler", edge_style),
    ]

    if not technical:
        edges.extend([
            Edge("e8", "dispatch", "settingsxml", "read or mutate config", edge_style),
            Edge("e9", "dispatch", "cachedb", "fast search / rebuild after writes", edge_style),
            Edge("e10", "dispatch", "logdb", "indexed log query", edge_style),
            Edge("e11", "dispatch", "opdb", "deal + staging lookups", edge_style),
            Edge("e12", "dispatch", "backup", "backup / rollback", edge_style),
        ])

    if technical:
        edges.extend([
            Edge("e13", "dispatch", "xml", "XML handlers", edge_style),
            Edge("e14", "dispatch", "cache", "SQLite mirror", edge_style),
            Edge("e15", "dispatch", "db", "repository queries", edge_style),
            Edge("e16", "dispatch", "logs", "sync + analytics", edge_style),
            Edge("e17", "dispatch", "triage", "email verification flow", edge_style),
            Edge("e18", "dispatch", "intel", "health / impact / gaps", edge_style),
            Edge("e19", "xml", "settingsxml", "parse / save", edge_style),
            Edge("e20", "xml", "backup", "XmlWriter backup", edge_style),
            Edge("e21", "cache", "cachedb", "persist mirror", edge_style),
            Edge("e22", "logs", "logdb", "ingest + query", edge_style),
            Edge("e23", "db", "opdb", "ODBC queries", edge_style),
        ])

    for edge in simplify_edges(edges):
        page.add_edge(edge)

    return page


def build_context_page(name: str, page_id: str, technical: bool) -> PageBuilder:
    theme = STYLE_THEMES["clean"]
    page = PageBuilder(name, page_id)
    subtitle = "Who talks to whom and where responsibilities stop" if not technical else "Expanded runtime actors, boundaries, and backend modules"
    add_title(page, "Walkthrough 1: System Context", subtitle, theme)

    add_lane(page, "a", "Client and Control Plane", 50, 120, 520, 820, theme)
    add_lane(page, "b", "Execution Plane", 600, 120, 620, 820, theme)
    add_lane(page, "c", "Data and Evidence Plane", 1250, 120, 620, 820, theme)

    page.add_box(Box("u1", "User", 120, 200, 120, 60, theme["primary"], "a"))
    page.add_box(Box("u2", "VS Code + Copilot Chat", 300, 180, 200, 90, theme["accent"], "a"))
    page.add_box(Box("u3", "FRP Extension\nparticipant, command registration, settings", 150, 360, 300, 110, theme["primary"], "a"))
    page.add_box(Box("u4", "Persistent backend bridge\nspawn exe or venv\nkeep process warm", 150, 560, 300, 100, theme["secondary"], "a"))

    page.add_box(Box("v1", "Python CLI", 700, 180, 160, 80, theme["primary"], "b"))
    page.add_box(Box("v2", "XML commands\nsearch, detail, validate, clone, diff, rollback", 650, 340, 260, 100, theme["secondary"], "b"))
    page.add_box(Box("v3", "Log commands\nsync, search, linkage, trends, performance", 930, 340, 260, 100, theme["secondary"], "b"))
    page.add_box(Box("v4", "Triage and staging commands\ntriage_verify, staging_linkage, deal_pipeline", 650, 540, 260, 110, theme["accent"], "b"))
    page.add_box(Box("v5", "Analysis commands\ncoverage, orphans, collisions, impact, health", 930, 540, 260, 110, theme["accent"], "b"))
    if technical:
        page.add_box(Box("v6", "Stable response envelope\nCliResponse JSON", 820, 740, 200, 80, theme["note"], "b"))

    page.add_box(Box("d1", "Settings.xml\nEmail + SFTP job definitions", 1380, 180, 170, 90, theme["store"], "c"))
    page.add_box(Box("d2", "SQLite XML cache", 1590, 180, 170, 90, theme["store"], "c"))
    page.add_box(Box("d3", "Application log files", 1380, 370, 170, 90, theme["store"], "c"))
    page.add_box(Box("d4", "SQLite log index", 1590, 370, 170, 90, theme["store"], "c"))
    page.add_box(Box("d5", "tblExternalDIDRef", 1380, 580, 170, 90, theme["store"], "c"))
    page.add_box(Box("d6", "tblTemplateStaging", 1590, 580, 170, 90, theme["store"], "c"))
    page.add_box(Box("d7", "backup/ snapshots", 1485, 760, 170, 80, theme["store"], "c"))

    for edge in simplify_edges([
        Edge("ce1", "u1", "u2", "natural language", theme["edge"]),
        Edge("ce2", "u2", "u3", "@frp + slash commands", theme["edge"]),
        Edge("ce3", "u3", "u4", "backendCall", theme["edge"]),
        Edge("ce4", "u4", "v1", "JSON request / response", theme["edge"]),
        Edge("ce5", "v1", "v2", "dispatch", theme["edge"]),
        Edge("ce6", "v1", "v3", "dispatch", theme["edge"]),
        Edge("ce7", "v1", "v4", "dispatch", theme["edge"]),
        Edge("ce8", "v1", "v5", "dispatch", theme["edge"]),
        Edge("ce9", "v2", "d1", "parse / save", theme["edge"]),
        Edge("ce10", "v2", "d2", "rebuild / search", theme["edge"]),
        Edge("ce11", "v2", "d7", "backup / rollback", theme["edge"]),
        Edge("ce12", "v3", "d3", "sync input", theme["edge"]),
        Edge("ce13", "v3", "d4", "query analytics", theme["edge"]),
        Edge("ce14", "v4", "d5", "deal mapping", theme["edge"]),
        Edge("ce15", "v4", "d6", "processing history", theme["edge"]),
        Edge("ce16", "v5", "d5", "coverage + collisions", theme["edge"]),
        Edge("ce17", "v5", "d4", "health + trends", theme["edge"]),
        Edge("ce18", "v5", "d6", "pipeline analysis", theme["edge"]),
    ]):
        page.add_edge(edge)

    return page


def build_request_flow_page(name: str, page_id: str, technical: bool) -> PageBuilder:
    theme = STYLE_THEMES["clean"]
    page = PageBuilder(name, page_id)
    subtitle = "End-to-end request path from chat prompt to backend result" if not technical else "Detailed control flow including persistent backend and deterministic command routing"
    add_title(page, "Walkthrough 2: Request and Control Flow", subtitle, theme)

    steps = [
        ("r1", "User prompt\nexample: /logs search subject:FREMF; days:3", theme["accent"]),
        ("r2", "participant.js\nparse slash command\nchoose deterministic or LLM-backed path", theme["primary"]),
        ("r3", "tool.js\ninject settingsPath, cacheDbPath, db credentials, timeouts", theme["secondary"]),
        ("r4", "frp_backend.js\nwrite JSON request to warm process\nor spawn fallback", theme["primary"]),
        ("r5", "cli/main.py --server\nparse args\nlookup handler in _COMMAND_DISPATCH", theme["secondary"]),
        ("r6", "Domain handler\nsearch XML / query SQLite / query DB / analyze logs", theme["accent"]),
        ("r7", "CliResponse JSON\nsuccess + data + warnings + elapsed_ms", theme["primary"]),
        ("r8", "participant.js formatting\ntables, summaries, inline next actions", theme["secondary"]),
    ]

    y = 180
    for box_id, label, style in steps:
        page.add_box(Box(box_id, label, 140, y, 500, 80 if box_id != "r6" else 100, style))
        y += 110

    stores = [
        ("s1", "Settings.xml", 900, 190),
        ("s2", "SQLite XML cache", 1140, 190),
        ("s3", "SQLite log index", 1380, 190),
        ("s4", "tblExternalDIDRef", 900, 430),
        ("s5", "tblTemplateStaging", 1140, 430),
        ("s6", "backup/ snapshots", 1380, 430),
    ]
    for box_id, label, x, y in stores:
        page.add_box(Box(box_id, label, x, y, 190, 80, theme["store"]))

    note_text = "Deterministic commands stay predictable.\nAutomatic log sync is disabled.\nXML mutations rebuild the SQLite cache after success."
    if technical:
        note_text = "Transport contract:\nrequest = {command,args}\nresponse = CliResponse JSON line\nlate timed-out responses are drained by the extension bridge."
    page.add_box(Box("rn", note_text, 860, 700, 760, 120, theme["note"]))

    edge_style = theme["edge"]
    flow_edges = [
        Edge("re_r1_r2", "r1", "r2", "prompt", edge_style),
        Edge("re_r2_r3", "r2", "r3", "command selection", edge_style),
        Edge("re_r3_r4", "r3", "r4", "normalized call", edge_style),
        Edge("re_r4_r5", "r4", "r5", "JSON transport", edge_style),
        Edge("re_r5_r6", "r5", "r6", "dispatch", edge_style),
        Edge("re_r6_r7", "r6", "r7", "data + warnings", edge_style),
        Edge("re_r7_r8", "r7", "r8", "structured result", edge_style),
        Edge("re1", "r6", "s1", "parse / write", edge_style),
        Edge("re2", "r6", "s2", "search / rebuild", edge_style),
        Edge("re3", "r6", "s3", "log analytics", edge_style),
        Edge("re4", "r6", "s4", "deal lookup", edge_style),
        Edge("re5", "r6", "s5", "staging lookup", edge_style),
        Edge("re6", "r6", "s6", "backup / rollback", edge_style),
    ]

    if technical:
        page.add_box(Box("rt", "Mutation examples\ncreate_job, edit_job, clone_apply, rollback_xml", 900, 560, 330, 90, theme["accent"]))
        page.add_box(Box("rq", "Query examples\nsearch_jobs, deal_lookup, log_linkage, staging_audit", 1280, 560, 330, 90, theme["secondary"]))
        flow_edges.extend([
            Edge("re7", "r6", "rt", "write path", edge_style),
            Edge("re8", "r6", "rq", "read path", edge_style),
        ])

    for edge in simplify_edges(flow_edges):
        page.add_edge(edge)

    return page


def build_data_lineage_page(name: str, page_id: str, technical: bool) -> PageBuilder:
    theme = STYLE_THEMES["clean"]
    page = PageBuilder(name, page_id)
    subtitle = "How configuration, mappings, execution history, and logs relate" if not technical else "Detailed lineage across authoritative sources, mirrors, and evidence stores"
    add_title(page, "Walkthrough 3: Data Lineage and Mutation Safety", subtitle, theme)

    page.add_box(Box("l1", "Settings.xml\njob configuration authority\nMailboxCollection / FolderCollection", 120, 220, 280, 120, theme["primary"]))
    page.add_box(Box("l2", "XmlWriter\nbackup -> write -> verify -> restore on failure", 460, 220, 280, 120, theme["accent"]))
    page.add_box(Box("l3", "backup/ folder\ntimestamped snapshots", 800, 220, 220, 120, theme["store"]))
    page.add_box(Box("l4", "SQLite XML cache\nmirror for fast search and deterministic lookup", 1080, 220, 280, 120, theme["store"]))
    page.add_box(Box("l5", "tblExternalDIDRef\nCompanyID -> DID + ImportDID", 1420, 220, 280, 120, theme["secondary"]))

    page.add_box(Box("l6", "Incoming email / SFTP event", 120, 540, 220, 90, theme["accent"]))
    page.add_box(Box("l7", "Application log files\noperational trace", 400, 540, 220, 90, theme["secondary"]))
    page.add_box(Box("l8", "SQLite log index\nsearchable evidence", 680, 540, 220, 90, theme["store"]))
    page.add_box(Box("l9", "tblTemplateStaging\nexecution history and status", 960, 540, 280, 90, theme["store"]))
    page.add_box(Box("l10", "Cross-link features\ntriage, log_linkage, staging_linkage, deal_pipeline", 1300, 520, 400, 130, theme["primary"]))

    note = "Authoritative order:\n1. Settings.xml\n2. Deal mapping reference\n3. Processing history + logs as evidence\n\nSQLite stores accelerate access but do not replace source systems."
    if technical:
        note = "Post-write safety pattern:\nmutation -> XmlWriter backup + verify -> rebuild SQLite cache\n\nCross-reference pattern:\njob.ServicerID -> tblExternalDIDRef.CompanyID\nscrubber/template -> tblTemplateStaging.TemplateName\nlog evidence -> SQLite log index"
    page.add_box(Box("ln", note, 520, 760, 860, 140, theme["note"]))

    edge_style = theme["edge"]
    relations = [
        ("l1", "l2", "all writes flow through writer"),
        ("l2", "l3", "create safety backup"),
        ("l2", "l4", "trigger rebuild"),
        ("l1", "l5", "ServicerID cross-reference"),
        ("l6", "l7", "monitor event recorded"),
        ("l7", "l8", "sync_logs"),
        ("l6", "l9", "file queued / processed"),
        ("l5", "l10", "deal context"),
        ("l8", "l10", "log evidence"),
        ("l9", "l10", "execution evidence"),
        ("l4", "l10", "fast job lookup"),
        ("l1", "l10", "fallback authoritative read"),
    ]
    lineage_edges = [Edge(f"le{index}", src, dst, txt, edge_style) for index, (src, dst, txt) in enumerate(relations, 1)]
    for edge in simplify_edges(lineage_edges):
        page.add_edge(edge)

    return page


def build_style_compare_page(name: str, page_id: str, theme_name: str) -> PageBuilder:
    theme = STYLE_THEMES[theme_name]
    page = PageBuilder(name, page_id)
    add_title(page, f"Style Comparison: {name}", "Use this page to compare presentation treatment before exporting final assets", theme)

    page.add_box(Box("c1", "User / Architect", 120, 220, 180, 70, theme["accent"]))
    page.add_box(Box("c2", "VS Code Extension", 420, 220, 220, 90, theme["primary"]))
    page.add_box(Box("c3", "Python CLI Boundary", 770, 220, 220, 90, theme["secondary"]))
    page.add_box(Box("c4", "Backend Domains", 1120, 220, 220, 90, theme["primary"]))
    page.add_box(Box("c5", "Persistent Stores", 1470, 220, 220, 90, theme["store"]))

    style_edges = [
        ("c1", "c2", "prompt"),
        ("c2", "c3", "JSON request"),
        ("c3", "c4", "dispatch"),
        ("c4", "c5", "read / write evidence"),
    ]
    for index, (src, dst, txt) in enumerate(style_edges, 1):
        page.add_edge(simplify_edges([Edge(f"sc{index}", src, dst, txt, theme["edge"])])[0])

    comparison_text = {
        "clean": "Clean Enterprise\nBest default for architect reviews\nHigh readability, restrained color, modern but conservative",
        "visio": "Visio Style\nMost familiar for traditional enterprise audiences\nSafe if stakeholders expect classic diagram language",
        "modern": "Modern Architecture Board\nMost visually distinctive\nGood for workshops and whiteboard-style reviews",
    }[theme_name]
    page.add_box(Box("cn", comparison_text, 540, 520, 820, 160, theme["note"]))
    return page


def parse_style(style: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for item in style.split(";"):
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
            parsed[key] = value
        else:
            parsed[item] = "1"
    return parsed


def sanitize_text(text: str) -> str:
    text = text.replace("<br/>", "\n").replace("<br>", "\n")
    text = re.sub(r"</?font[^>]*>", "", text)
    return text


def text_lines(text: str) -> List[str]:
    return [line for line in sanitize_text(text).splitlines() if line.strip()]


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def box_center(box: Box) -> Tuple[float, float]:
    return box.x + box.width / 2, box.y + box.height / 2


def edge_path(source: Box, target: Box) -> Tuple[str, Tuple[float, float]]:
    source_center_x, source_center_y = box_center(source)
    target_center_x, target_center_y = box_center(target)

    if source.x + source.width <= target.x:
        start = (source.x + source.width, source_center_y)
        end = (target.x, target_center_y)
        mid_x = (start[0] + end[0]) / 2
        points = [start, (mid_x, start[1]), (mid_x, end[1]), end]
    elif target.x + target.width <= source.x:
        start = (source.x, source_center_y)
        end = (target.x + target.width, target_center_y)
        mid_x = (start[0] + end[0]) / 2
        points = [start, (mid_x, start[1]), (mid_x, end[1]), end]
    elif source.y + source.height <= target.y:
        start = (source_center_x, source.y + source.height)
        end = (target_center_x, target.y)
        mid_y = (start[1] + end[1]) / 2
        points = [start, (start[0], mid_y), (end[0], mid_y), end]
    else:
        start = (source_center_x, source.y)
        end = (target_center_x, target.y + target.height)
        mid_y = (start[1] + end[1]) / 2
        points = [start, (start[0], mid_y), (end[0], mid_y), end]

    path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    label_point = points[len(points) // 2]
    return path, label_point


def render_box_svg(box: Box, style_map: Dict[str, str]) -> str:
    fill = style_map.get("fillColor", "#FFFFFF")
    stroke = style_map.get("strokeColor", "#1F2937")
    font_color = style_map.get("fontColor", "#111827")
    stroke_width = style_map.get("strokeWidth", "1.5")
    rounded = style_map.get("rounded") == "1"
    is_swimlane = "swimlane" in style_map
    dashed = style_map.get("dashed") == "1"
    dash_attr = ' stroke-dasharray="8 6"' if dashed else ""
    radius = 14 if rounded else 0

    if is_swimlane:
        header_height = 34
        return "".join([
            f'<rect x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" rx="10" ry="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>',
            f'<rect x="{box.x}" y="{box.y}" width="{box.width}" height="{header_height}" rx="10" ry="10" fill="#EEF3FA" stroke="{stroke}" stroke-width="1.5"/>',
            f'<text x="{box.x + 18}" y="{box.y + 23}" fill="{font_color}" font-family="Helvetica, Arial, sans-serif" font-size="15" font-weight="700">{xml_escape(sanitize_text(box.text))}</text>',
        ])

    lines = text_lines(box.text)
    is_title = box.id == "title"
    line_spacing = 18 if is_title else 16
    default_size = int(style_map.get("fontSize", "13"))
    line_sizes = [26] + [14] * (len(lines) - 1) if is_title else [default_size] * len(lines)
    total_height = (len(lines) - 1) * line_spacing
    start_y = box.y + (box.height / 2) - (total_height / 2)
    text_x = box.x + box.width / 2
    font_weight = "700" if style_map.get("fontStyle") == "1" or is_title else "500"

    text_parts = [
        f'<text x="{text_x}" y="{start_y}" fill="{font_color}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-weight="{font_weight}">'
    ]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else line_spacing
        text_parts.append(f'<tspan x="{text_x}" dy="{dy}" font-size="{line_sizes[index]}">{xml_escape(line)}</tspan>')
    text_parts.append("</text>")

    return "".join([
        f'<rect x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" rx="{radius}" ry="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"{dash_attr}/>',
        "".join(text_parts),
    ])


def render_edge_svg(edge: Edge, box_map: Dict[str, Box]) -> str:
    source = box_map[edge.source]
    target = box_map[edge.target]
    style_map = parse_style(edge.style)
    stroke = style_map.get("strokeColor", "#425466")
    stroke_width = style_map.get("strokeWidth", "1.5")
    path, label_point = edge_path(source, target)
    parts = [
        f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}" marker-end="url(#arrow)"/>'
    ]
    if edge.text:
        label_x, label_y = label_point
        parts.append(
            f'<text x="{label_x}" y="{label_y + 3}" text-anchor="middle" fill="#334155" font-family="Helvetica, Arial, sans-serif" font-size="12" font-weight="600">{xml_escape(edge.text)}</text>'
        )
    return "".join(parts)


def render_svg_page(page: PageBuilder, output_path: Path) -> None:
    box_map = page.get_absolute_box_map()
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">',
        '<defs>',
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">',
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#425466"/>',
        '</marker>',
        '<filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">',
        '<feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#0F172A" flood-opacity="0.10"/>',
        '</filter>',
        '</defs>',
        '<rect width="1920" height="1080" fill="#F4F7FB"/>',
        '<g filter="url(#softShadow)">',
    ]

    for box in page.boxes:
        parts.append(render_box_svg(box_map[box.id], parse_style(box.style)))

    parts.append('</g><g>')

    for edge in page.edges:
        parts.append(render_edge_svg(edge, box_map))

    parts.append('</g></svg>')
    output_path.write_text("".join(parts), encoding="utf-8")


def build_mxfile(pages: List[PageBuilder]) -> Element:
    mxfile = Element("mxfile", {
        "host": "app.diagrams.net",
        "modified": "2026-03-24T00:00:00.000Z",
        "agent": "GitHub Copilot GPT-5.4",
        "version": "24.7.17",
        "type": "device",
    })

    for page in pages:
        mxfile.append(page.to_diagram())

    return mxfile


def reset_svg_dir(path: Path) -> None:
    if path.exists():
        for svg_file in path.glob("*.svg"):
            svg_file.unlink()
    path.mkdir(parents=True, exist_ok=True)


def write_package(drawio_path: Path, svg_dir: Path, pages: List[PageBuilder]) -> None:
    drawio_path.parent.mkdir(parents=True, exist_ok=True)
    reset_svg_dir(svg_dir)
    mxfile = build_mxfile(pages)
    drawio_path.write_text(tostring(mxfile, encoding="unicode"), encoding="utf-8")
    for page in pages:
        render_svg_page(page, svg_dir / f"{page.page_id}.svg")


def main() -> None:
    current_pages = [
        build_master_page("Master - Technical", "master-tech", "clean", technical=True),
        build_context_page("Context - Technical", "context-tech", technical=True),
        build_request_flow_page("Request Flow - Technical", "flow-tech", technical=True),
        build_data_lineage_page("Data Lineage - Technical", "lineage-tech", technical=True),
    ]

    archived_pages = [
        build_style_compare_page("Clean Enterprise", "style-clean", "clean"),
        build_style_compare_page("Visio Style", "style-visio", "visio"),
        build_style_compare_page("Modern Board", "style-modern", "modern"),
        build_master_page("Master - Executive", "master-exec", "clean", technical=False),
        build_context_page("Context - Executive", "context-exec", technical=False),
        build_request_flow_page("Request Flow - Executive", "flow-exec", technical=False),
        build_data_lineage_page("Data Lineage - Executive", "lineage-exec", technical=False),
    ]

    write_package(OUTPUT, SVG_OUTPUT_DIR, current_pages)
    write_package(ARCHIVE_OUTPUT, ARCHIVE_SVG_OUTPUT_DIR, archived_pages)

    print(f"Wrote {OUTPUT}")
    print(f"Wrote SVG exports to {SVG_OUTPUT_DIR}")
    print(f"Wrote archive package to {ARCHIVE_OUTPUT}")
    print(f"Wrote archived SVG exports to {ARCHIVE_SVG_OUTPUT_DIR}")


if __name__ == "__main__":
    main()