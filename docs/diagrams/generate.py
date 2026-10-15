#!/usr/bin/env python3
"""Generate the sbx-vscode-claude diagrams as both .drawio (editable) and .svg.

One description per diagram drives both outputs, so the two files never drift.
Render the PNGs with:  rsvg-convert -o <name>.png <name>.svg
"""
from xml.sax.saxutils import escape

PALETTE = {  # role: (fill, gradient, stroke, text, svg gradient id)
    "client": ("#E3F2FD", "#BBDEFB", "#1565C0", "#0D47A1", "gBlue"),
    "agent": ("#E1F5FE", "#B3E5FC", "#0277BD", "#01579B", "gBlue2"),
    "hl": ("#F3E5F5", "#E1BEE7", "#6A1B9A", "#4A148C", "gPurple"),
    "engine": ("#FFFDE7", "#FFF9C4", "#F9A825", "#F57F17", "gYellow"),
    "neutral": ("#ECEFF1", "#CFD8DC", "#455A64", "#263238", "gGrey"),
}

SVG_DEFS = """  <defs>
    <linearGradient id="gBg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#FFFFFF"/><stop offset="100%" stop-color="#EEF2FA"/></linearGradient>
""" + "".join(
    f'    <linearGradient id="{g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="{f}"/><stop offset="100%" stop-color="{t}"/></linearGradient>\n'
    for f, t, _, _, g in PALETTE.values()
) + """    <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="2" dy="3" stdDeviation="4" flood-color="#000000" flood-opacity="0.25"/></filter>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#37474F"/></marker>
  </defs>
"""


class Diagram:
    def __init__(self, name, width, height, title, subtitle):
        self.name, self.w, self.h = name, width, height
        self.svg = [f'  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#gBg)"/>',
                    f'  <text x="{width/2}" y="38" text-anchor="middle" font-size="25" font-weight="700" fill="#1A237E">{escape(title)}</text>',
                    f'  <text x="{width/2}" y="61" text-anchor="middle" font-size="14" font-style="italic" fill="#546E7A">{escape(subtitle)}</text>']
        self.cells = [
            f'<mxCell id="bg" value="" style="rounded=0;html=1;fillColor=#FAFBFF;strokeColor=none;" vertex="1" parent="1"><mxGeometry width="{width}" height="{height}" as="geometry"/></mxCell>',
            f'<mxCell id="title" value="{escape(title)}" style="text;html=1;align=center;fontSize=24;fontStyle=1;fontColor=#1A237E;" vertex="1" parent="1"><mxGeometry x="0" y="18" width="{width}" height="30" as="geometry"/></mxCell>',
            f'<mxCell id="subtitle" value="{escape(subtitle)}" style="text;html=1;align=center;fontSize=13;fontStyle=2;fontColor=#546E7A;" vertex="1" parent="1"><mxGeometry x="0" y="48" width="{width}" height="20" as="geometry"/></mxCell>']
        self.n = 0

    def _id(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def container(self, x, y, w, h, label, nested=False):
        stroke = "#B0BEC5" if nested else "#90A4AE"
        fill = "#FAFAFA" if nested else "none"
        color = "#78909C" if nested else "#607D8B"
        self.svg.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2" stroke-dasharray="7,5"/>')
        self.svg.append(f'  <text x="{x + w/2}" y="{y + 22}" text-anchor="middle" font-size="13" font-style="italic" font-weight="700" fill="{color}">{escape(label)}</text>')
        self.cells.append(f'<mxCell id="{self._id("c")}" value="{escape(label)}" style="rounded=1;arcSize=4;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};dashed=1;verticalAlign=top;fontSize=13;fontStyle=3;fontColor={color};spacingTop=4;" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

    def box(self, x, y, w, h, role, icon, title, lines=(), badge=None):
        fill, grad, stroke, text, gid = PALETTE[role]
        sw = 3 if role == "hl" else 2
        cx = x + w / 2
        self.svg.append(f'  <g filter="url(#shadow)"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="url(#{gid})" stroke="{stroke}" stroke-width="{sw}"/></g>')
        # icon on its own line, then the bold title, then small detail lines
        block = 26 + 22 + 16 * len(lines)
        top = y + (h - block) / 2
        self.svg.append(f'  <text x="{cx}" y="{top + 22}" text-anchor="middle" font-size="22">{icon}</text>')
        self.svg.append(f'  <text x="{cx}" y="{top + 46}" text-anchor="middle" font-size="16" font-weight="700" fill="{text}">{escape(title)}</text>')
        for i, line in enumerate(lines):
            self.svg.append(f'  <text x="{cx}" y="{top + 64 + 16 * i}" text-anchor="middle" font-size="12" fill="{text}">{escape(line)}</text>')
        value = escape(f"{icon}<br><b>{escape(title)}</b>" + "".join(f"<br><font style='font-size:12px'>{escape(l)}</font>" for l in lines))
        bid = self._id("b")
        self.cells.append(f'<mxCell id="{bid}" value="{value}" style="rounded=1;arcSize=14;whiteSpace=wrap;html=1;fillColor={fill};gradientColor={grad};strokeColor={stroke};strokeWidth={sw};shadow=1;fontSize=15;fontColor={text};" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        if badge:
            bw = 9 + 7.2 * len(badge)
            bx, by = x + w - bw - 14, y - 12
            self.svg.append(f'  <rect x="{bx}" y="{by}" width="{bw}" height="24" rx="12" fill="{stroke}"/>')
            self.svg.append(f'  <text x="{bx + bw/2}" y="{by + 16.5}" text-anchor="middle" font-size="11" font-weight="700" fill="#FFFFFF">{escape(badge)}</text>')
            self.cells.append(f'<mxCell id="{self._id("badge")}" value="{escape(badge)}" style="rounded=1;arcSize=50;html=1;fillColor={stroke};strokeColor=none;fontColor=#FFFFFF;fontSize=11;fontStyle=1;" vertex="1" parent="1"><mxGeometry x="{bx}" y="{by}" width="{bw}" height="24" as="geometry"/></mxCell>')
        return bid

    def edge(self, points, label=None, sub=None, at=None, both=False, lw=None):
        """points: list of (x, y). label sits in a white rect centred on `at`."""
        d = " ".join(("M" if i == 0 else "L") + f"{px},{py}" for i, (px, py) in enumerate(points))
        start = ' marker-start="url(#arrow)"' if both else ""
        self.svg.append(f'  <path d="{d}" fill="none" stroke="#37474F" stroke-width="2.5" marker-end="url(#arrow)"{start}/>')
        (sx, sy), (tx, ty) = points[0], points[-1]
        wps = "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in points[1:-1])
        arrows = "startArrow=block;startFill=1;" if both else ""
        self.cells.append(f'<mxCell id="{self._id("e")}" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#37474F;strokeWidth=2;endArrow=block;endFill=1;{arrows}" edge="1" parent="1"><mxGeometry relative="1" as="geometry"><mxPoint x="{sx}" y="{sy}" as="sourcePoint"/><mxPoint x="{tx}" y="{ty}" as="targetPoint"/>' + (f'<Array as="points">{wps}</Array>' if wps else "") + '</mxGeometry></mxCell>')
        if label:
            ax, ay = at
            w = lw or max(len(label) * 8, len(sub or "") * 6.4) + 12
            h = 36 if sub else 20
            self.svg.append(f'  <rect x="{ax - w/2}" y="{ay - h/2}" width="{w}" height="{h}" rx="4" fill="#FAFBFF"/>')
            if sub:
                self.svg.append(f'  <text x="{ax}" y="{ay - 3}" text-anchor="middle" font-size="12.5" font-weight="700" fill="#263238">{escape(label)}</text>')
                self.svg.append(f'  <text x="{ax}" y="{ay + 12}" text-anchor="middle" font-size="11" fill="#455A64">{escape(sub)}</text>')
            else:
                self.svg.append(f'  <text x="{ax}" y="{ay + 4.5}" text-anchor="middle" font-size="12.5" font-weight="700" fill="#263238">{escape(label)}</text>')
            value = escape(f"<b>{escape(label)}</b>" + (f"<br>{escape(sub)}" if sub else ""))
            self.cells.append(f'<mxCell id="{self._id("l")}" value="{value}" style="text;html=1;align=center;verticalAlign=middle;fontSize=12;fontColor=#263238;labelBackgroundColor=#FAFBFF;fillColor=#FAFBFF;" vertex="1" parent="1"><mxGeometry x="{ax - w/2}" y="{ay - h/2}" width="{w}" height="{h}" as="geometry"/></mxCell>')

    def note(self, x, y, text, size=12):
        self.svg.append(f'  <text x="{x}" y="{y}" text-anchor="middle" font-size="{size}" font-style="italic" fill="#78909C">{escape(text)}</text>')
        self.cells.append(f'<mxCell id="{self._id("n")}" value="{escape(text)}" style="text;html=1;align=center;fontSize={size};fontStyle=2;fontColor=#78909C;" vertex="1" parent="1"><mxGeometry x="{x - 400}" y="{y - 15}" width="800" height="20" as="geometry"/></mxCell>')

    def write(self):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" font-family="DejaVu Sans, Verdana, sans-serif">\n'
               + SVG_DEFS + "\n".join(self.svg) + "\n</svg>\n")
        open(f"{self.name}.svg", "w").write(svg)
        drawio = (f'<mxfile host="app.diagrams.net" agent="sbx-vscode-claude/generate.py" type="device">\n'
                  f'  <diagram name="{self.name}" id="{self.name}">\n'
                  f'    <mxGraphModel dx="1400" dy="800" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{self.w}" pageHeight="{self.h}" math="0" shadow="0">\n'
                  '      <root>\n        <mxCell id="0"/>\n        <mxCell id="1" parent="0"/>\n'
                  + "".join(f"        {c}\n" for c in self.cells)
                  + "      </root>\n    </mxGraphModel>\n  </diagram>\n</mxfile>\n")
        open(f"{self.name}.drawio", "w").write(drawio)


def runtime():
    d = Diagram("runtime-architecture", 1200, 700, "My Secure IDE — runtime architecture",
                "VS Code + Claude Code run inside a Docker Sandbox; only the IDE window reaches the host")
    d.box(30, 140, 200, 110, "client", "🖥️", "Host desktop", ["macOS · Windows · Linux", "shows the VS Code window"])
    d.container(320, 95, 540, 545, "Docker Sandbox (microVM) — kit sbx-vscode-claude")
    d.box(360, 140, 460, 110, "hl", "🧑‍💻", "VS Code (Electron)", ["entrypoint · Wayland client · software rendering", "opens the mounted workspace"], badge="★ entrypoint")
    d.box(360, 300, 460, 100, "agent", "🤖", "Claude Code", ["VS Code extension + claude CLI"])
    d.box(360, 460, 460, 90, "engine", "🗃", "Workspace", ["your project, mounted from the host"])
    d.note(590, 600, "host files outside the workspace stay out of reach")
    d.box(930, 300, 240, 100, "neutral", "🛡️", "sbx network policy", ["allow: *.anthropic.com · claude.ai", "deny: everything else"])
    d.box(930, 470, 240, 80, "agent", "🌐", "Anthropic API")
    d.edge([(232, 195), (358, 195)], "Wayland", "window only", at=(276, 166), both=True, lw=80)
    d.edge([(590, 250), (590, 298)], "hosts the agent", at=(680, 274), lw=120)
    d.edge([(590, 400), (590, 458)], "reads / edits files", at=(690, 429), lw=140)
    d.edge([(822, 350), (928, 350)], "HTTPS", at=(894, 350), lw=54)
    d.edge([(1050, 400), (1050, 468)], "allowed", at=(1100, 434), lw=70)
    d.write()


def build_run():
    d = Diagram("kit-build-and-run", 1200, 460, "My Secure IDE — from kit sources to a running IDE",
                "sbx builds the kit image once, then every sbx run --display starts a fresh, confined IDE")
    d.box(40, 120, 220, 130, "client", "💾", "Kit sources", ["kit.yaml (descriptor, policy)", "kit.dockerfile + bin/ + config/"])
    d.box(340, 120, 220, 130, "engine", "🏗️", "sbx kit builder", ["builds the image and", "embeds the kit descriptor"])
    d.box(640, 120, 220, 130, "agent", "📦", "Kit image", ["VS Code · Claude Code", "network policy · agent context"])
    d.box(940, 120, 220, 130, "hl", "🚀", "sbx run --display", ["fresh sandbox per run", "VS Code window on the host"], badge="★ demo")
    d.box(640, 320, 220, 90, "neutral", "🗄️", "OCI registry", ["share the kit with the team"])
    d.edge([(262, 185), (338, 185)], "build", at=(300, 185), lw=52)
    d.edge([(562, 185), (638, 185)], "image", at=(600, 185), lw=54)
    d.edge([(862, 185), (938, 185)], "run", at=(900, 185), lw=40)
    d.edge([(750, 250), (750, 318)], "sbx kit push", at=(820, 284), lw=100)
    d.edge([(862, 365), (1050, 365), (1050, 252)], "sbx run --display <ref>", at=(955, 365), lw=170)
    d.write()


if __name__ == "__main__":
    runtime()
    build_run()
