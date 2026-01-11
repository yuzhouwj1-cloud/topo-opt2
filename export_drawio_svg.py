"""Export topology to draw.io and SVG formats."""

from __future__ import annotations

import math
import os
from typing import Dict, Tuple
import xml.etree.ElementTree as ET

from topology import Topology


def _circle_layout(nodes: list[int], radius: float = 300.0) -> Dict[int, Tuple[float, float]]:
    count = len(nodes)
    if count == 0:
        return {}
    positions: Dict[int, Tuple[float, float]] = {}
    for idx, node in enumerate(nodes):
        angle = 2 * math.pi * idx / count
        positions[node] = (radius * math.cos(angle), radius * math.sin(angle))
    return positions


def export_drawio_svg(topology: Topology, drawio_path: str, svg_path: str) -> tuple[str, str]:
    nodes = sorted(topology.nodes())
    positions = _circle_layout(nodes)
    os.makedirs(os.path.dirname(drawio_path) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(svg_path) or ".", exist_ok=True)

    _write_drawio(topology, positions, drawio_path)
    _write_svg(topology, positions, svg_path)
    return drawio_path, svg_path


def _write_drawio(
    topology: Topology,
    positions: Dict[int, Tuple[float, float]],
    path: str,
) -> None:
    mxfile = ET.Element("mxfile", host="app.diagrams.net")
    diagram = ET.SubElement(mxfile, "diagram", name="Topology")
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        dx="1000",
        dy="1000",
        grid="1",
        gridSize="10",
        guides="1",
        tooltips="1",
        connect="1",
        arrows="1",
        fold="1",
        page="1",
        pageScale="1",
        pageWidth="850",
        pageHeight="1100",
        math="0",
        shadow="0",
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    node_ids: Dict[int, str] = {}
    for idx, node in enumerate(sorted(positions.keys())):
        node_id = f"n{idx}"
        node_ids[node] = node_id
        x, y = positions[node]
        cell = ET.SubElement(
            root,
            "mxCell",
            id=node_id,
            value=str(node),
            style="ellipse;whiteSpace=wrap;html=1;",
            vertex="1",
            parent="1",
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            x=str(x),
            y=str(y),
            width="40",
            height="40",
            as_="geometry",
        )

    edge_idx = 0
    for node_a, node_b in topology.edges():
        edge = ET.SubElement(
            root,
            "mxCell",
            id=f"e{edge_idx}",
            value="",
            style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;",
            edge="1",
            parent="1",
            source=node_ids[node_a],
            target=node_ids[node_b],
        )
        ET.SubElement(edge, "mxGeometry", relative="1", as_="geometry")
        edge_idx += 1

    tree = ET.ElementTree(mxfile)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _write_svg(
    topology: Topology,
    positions: Dict[int, Tuple[float, float]],
    path: str,
) -> None:
    padding = 50
    xs = [pos[0] for pos in positions.values()] or [0.0]
    ys = [pos[1] for pos in positions.values()] or [0.0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x + 2 * padding
    height = max_y - min_y + 2 * padding

    def transform(point: Tuple[float, float]) -> Tuple[float, float]:
        return (point[0] - min_x + padding, point[1] - min_y + padding)

    lines = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}">'
    )
    for node_a, node_b in topology.edges():
        x1, y1 = transform(positions[node_a])
        x2, y2 = transform(positions[node_b])
        lines.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            'stroke="#999" stroke-width="1"/>'
        )
    for node, pos in positions.items():
        x, y = transform(pos)
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="#ffffff" stroke="#333"/>'
        )
        lines.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="10">{node}</text>'
        )
    lines.append("</svg>")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
