#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据给定拓扑（无向图边列表），生成：
  1) draw.io 图文件 (.drawio)
  2) 对应的 SVG 矢量图 (.svg)

特性：
- 节点按编号排序，自动分成左右两列：
    左列：前半部分节点
    右列：后半部分节点
- 同列内部边：绿色、多层弧线（span 越大弧线越外）
- 跨列边：蓝色直线
- 节点标签： "id (deg)" 写在圆心
"""

import xml.etree.ElementTree as ET
from typing import List, Tuple, Dict, Iterable

def compute_degrees(edges: Iterable[Tuple[int, int]]) -> Dict[int, int]:
    """计算无向图中每个节点的度数。"""
    deg: Dict[int, int] = {}
    for u, v in edges:
        deg[u] = deg.get(u, 0) + 1
        deg[v] = deg.get(v, 0) + 1
    return deg


def make_two_column_layout(nodes: List[int],
                           x_left: float = 300.0,
                           x_right: float = 600.0,
                           center_y: float = 400.0,
                           dy: float = 40.0):
    """
    将节点按编号排序后，一分为二：
    - 左列：前半部分
    - 右列：后半部分
    并返回每个节点的坐标 pos[node] = (x, y)
    同时返回左右分组（方便区分同列/跨列连线）。
    """
    nodes_sorted = sorted(nodes)
    n = len(nodes_sorted)
    mid = n // 2

    group_left = nodes_sorted[:mid]
    group_right = nodes_sorted[mid:]

    def compute_positions(group, x, cy, dy):
        m = len(group)
        if m <= 1:
            total_h = 0.0
        else:
            total_h = (m - 1) * dy
        y0 = cy - total_h / 2.0
        return {node: (x, y0 + i * dy) for i, node in enumerate(group)}

    pos = {}
    pos.update(compute_positions(group_left, x_left, center_y, dy))
    pos.update(compute_positions(group_right, x_right, center_y, dy))

    return pos, set(group_left), set(group_right)


def bend_for_pair(pos: Dict[int, Tuple[float, float]],
                  i: int,
                  j: int,
                  dy: float = 40.0) -> float:
    """
    根据两个节点沿 y 轴的距离（以 dy 为步长）决定弧线“外扩”的距离。
    span 越大 → bend 越大。
    """
    span = abs(pos[i][1] - pos[j][1])
    steps = span / dy
    base = 60.0
    k = 12.0
    bend = base + k * steps
    return max(60.0, min(bend, 220.0))


def generate_drawio(edges: List[Tuple[int, int]],
                    out_path: str):
    """
    生成 draw.io XML 文件，写入 out_path。
    """
    # 1. 收集节点、度数
    nodes = sorted({x for e in edges for x in e})
    deg = compute_degrees(edges)

    # 2. 布局：两列
    pos, group_left, group_right = make_two_column_layout(nodes)

    # 3. 构建 draw.io XML
    mxfile = ET.Element("mxfile")
    diagram = ET.SubElement(mxfile, "diagram", name="Graph")
    model = ET.SubElement(diagram, "mxGraphModel")
    root = ET.SubElement(model, "root")

    # 必须有 id=0 和 id=1 这两个 "根" cell
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    # 4. 节点（ellipse）
    for node in nodes:
        x, y = pos[node]
        label = f"{node} ({deg.get(node, 0)})"
        cell = ET.SubElement(
            root,
            "mxCell",
            id=str(node + 2),          # id 从 2 开始，避免和 0/1 冲突
            value=label,
            style="ellipse;whiteSpace=wrap;html=1;",
            vertex="1",
            parent="1",
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            x=f"{x:.1f}",
            y=f"{y:.1f}",
            width="40",
            height="40",
            **{"as": "geometry"},
        )

    # 5. 边
    edge_id = 10_000
    for s, t in edges:
        same_col_left = (s in group_left and t in group_left)
        same_col_right = (s in group_right and t in group_right)
        same_col = same_col_left or same_col_right

        if same_col:
            base_x = 300.0 if same_col_left else 600.0
            y_s = pos[s][1]
            y_t = pos[t][1]
            mid_y = (y_s + y_t) / 2.0
            bend = bend_for_pair(pos, s, t)
            ctrl_x = base_x - bend if same_col_left else base_x + bend
            style = "endArrow=none;curved=1;roundEdge=1;arcSize=40;strokeColor=#00AA00;"
        else:
            style = "endArrow=none;strokeColor=#0066FF;"

        cell = ET.SubElement(
            root,
            "mxCell",
            id=str(edge_id),
            edge="1",
            parent="1",
            source=str(s + 2),
            target=str(t + 2),
            style=style,
        )
        geo = ET.SubElement(
            cell,
            "mxGeometry",
            relative="1",
            **{"as": "geometry"},
        )

        # 同列边添加控制点，强制走弧线
        if same_col:
            array = ET.SubElement(geo, "Array", **{"as": "points"})
            ET.SubElement(
                array,
                "mxPoint",
                x=f"{ctrl_x:.1f}",
                y=f"{mid_y:.1f}",
            )

        edge_id += 1

    # 6. 写入文件
    tree = ET.ElementTree(mxfile)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def generate_svg(edges: List[Tuple[int, int]],
                 out_path: str):
    """
    使用同样的布局和分层弧线规则，生成 SVG 文件。
    """
    nodes = sorted({x for e in edges for x in e})
    deg = compute_degrees(edges)
    pos, group_left, group_right = make_two_column_layout(nodes)

    svg_width, svg_height = 900, 800
    svg = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=str(svg_width),
        height=str(svg_height),
        viewBox="0 0 900 800",
    )

    # 先画边
    for s, t in edges:
        x_s, y_s = pos[s]
        x_t, y_t = pos[t]

        same_col_left = (s in group_left and t in group_left)
        same_col_right = (s in group_right and t in group_right)
        same_col = same_col_left or same_col_right

        if same_col:
            base_x = 300.0 if same_col_left else 600.0
            mid_y = (y_s + y_t) / 2.0
            bend = bend_for_pair(pos, s, t)
            ctrl_x = base_x - bend if same_col_left else base_x + bend
            color = "#00AA00"
            # 二次贝塞尔曲线
            d = f"M {x_s:.1f} {y_s:.1f} Q {ctrl_x:.1f} {mid_y:.1f} {x_t:.1f} {y_t:.1f}"
        else:
            color = "#0066FF"
            d = f"M {x_s:.1f} {y_s:.1f} L {x_t:.1f} {y_t:.1f}"

        ET.SubElement(
            svg,
            "path",
            d=d,
            fill="none",
            stroke=color,
            **{"stroke-width": "1.5"},
        )

    # 再画节点
    node_radius = 18
    for node in nodes:
        x, y = pos[node]
        # 圆
        ET.SubElement(
            svg,
            "circle",
            cx=f"{x:.1f}",
            cy=f"{y:.1f}",
            r=str(node_radius),
            fill="white",
            stroke="black",
            **{"stroke-width": "1.5"},
        )
        # 上面一行：编号
        text_id = ET.SubElement(
            svg,
            "text",
            x=f"{x:.1f}",
            y=f"{y - 4:.1f}",
            fill="black",
            **{
                "font-size": "10",
                "text-anchor": "middle",
                "dominant-baseline": "middle",
            },
        )
        text_id.text = str(node)
        # 下面一行：deg=?
        text_deg = ET.SubElement(
            svg,
            "text",
            x=f"{x:.1f}",
            y=f"{y + 10:.1f}",
            fill="black",
            **{
                "font-size": "9",
                "text-anchor": "middle",
                "dominant-baseline": "middle",
            },
        )
        text_deg.text = f"deg={deg.get(node, 0)}"

    tree = ET.ElementTree(svg)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def generate_graph_files(edges: List[Tuple[int, int]],
                         prefix: str = "graph"):
    """
    高层封装函数：
      输入：edges（边列表），前缀名 prefix
      输出：<prefix>.drawio 和 <prefix>.svg 文件
    """
    drawio_file = f"{prefix}.drawio"
    svg_file = f"{prefix}.svg"

    print(f"[+] Generating draw.io file: {drawio_file}")
    generate_drawio(edges, drawio_file)
    print(f"[+] Generating SVG file: {svg_file}")
    generate_svg(edges, svg_file)
    print("[✓] Done.")


if __name__ == "__main__":
    # 示例：使用你刚才那组拓扑
    edges_example = [
        (0, 17), (0, 19), (0, 20), (0, 23), (0, 24), (0, 25),
        (0, 28), (0, 29), (0, 31), (1, 13), (1, 16), (1, 18),
        (1, 20), (1, 21), (1, 22), (1, 24), (1, 28), (1, 30),
        (2, 14), (2, 17), (2, 18), (2, 21), (2, 25), (2, 26),
        (2, 27), (2, 29), (2, 30), (3, 12), (3, 19), (3, 20),
        (3, 21), (3, 22), (3, 23), (3, 26), (3, 30), (3, 31),
        (4, 12), (4, 15), (4, 18), (4, 20), (4, 26), (4, 27),
        (4, 28), (4, 30), (4, 31), (5, 14), (5, 16), (5, 19),
        (5, 20), (5, 24), (5, 25), (5, 27), (5, 29), (5, 31),
        (6, 15), (6, 16), (6, 18), (6, 22), (6, 23), (6, 24),
        (6, 26), (6, 28), (6, 31), (7, 17), (7, 18), (7, 20),
        (7, 21), (7, 24), (7, 27), (7, 29), (7, 30), (7, 31),
        (8, 12), (8, 13), (8, 21), (8, 22), (8, 25), (8, 27),
        (8, 28), (8, 29), (8, 30), (9, 10), (9, 14), (9, 16),
        (9, 20), (9, 24), (9, 25), (9, 26), (9, 29), (9, 31),
        (10, 13), (10, 14), (10, 19), (10, 20), (10, 21), (10, 23),
        (10, 26), (10, 28), (11, 12), (11, 17), (11, 19), (11, 25),
        (11, 26), (11, 27), (11, 29), (11, 30), (11, 31), (12, 15),
        (12, 17), (12, 20), (12, 23), (12, 28), (13, 14), (13, 18),
        (13, 21), (13, 23), (13, 24), (13, 25), (14, 17), (14, 22),
        (14, 23), (14, 29), (15, 17), (15, 18), (15, 26), (15, 27),
        (15, 28), (15, 30), (16, 17), (16, 21), (16, 22), (16, 28),
        (16, 31), (17, 23), (18, 22), (18, 26), (19, 21), (19, 22),
        (19, 24), (19, 27), (22, 30), (23, 25), (24, 25), (27, 29),
    ]

    generate_graph_files(edges_example, prefix="graph_two_columns_demo")
