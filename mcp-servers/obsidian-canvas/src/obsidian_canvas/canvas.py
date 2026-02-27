"""JSON Canvas 1.0 data models and canvas manipulation operations."""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Discriminator, Field, Tag


def generate_id() -> str:
    """Generate a 16-char hex ID matching Obsidian's native format."""
    return uuid.uuid4().hex[:16]


# --- Node Models ---


class BaseNode(BaseModel):
    id: str = Field(default_factory=generate_id)
    x: int
    y: int
    width: int = 400
    height: int = 400
    color: Optional[str] = None


class TextNode(BaseNode):
    type: Literal["text"] = "text"
    text: str


class FileNode(BaseNode):
    type: Literal["file"] = "file"
    file: str
    subpath: Optional[str] = None


class LinkNode(BaseNode):
    type: Literal["link"] = "link"
    url: str


class GroupNode(BaseNode):
    type: Literal["group"] = "group"
    label: Optional[str] = None
    background: Optional[str] = None
    backgroundStyle: Optional[Literal["cover", "ratio", "repeat"]] = None


def _node_discriminator(v: dict | BaseNode) -> str:
    if isinstance(v, dict):
        return v.get("type", "text")
    return getattr(v, "type", "text")


CanvasNode = Annotated[
    Union[
        Annotated[TextNode, Tag("text")],
        Annotated[FileNode, Tag("file")],
        Annotated[LinkNode, Tag("link")],
        Annotated[GroupNode, Tag("group")],
    ],
    Discriminator(_node_discriminator),
]


# --- Edge Model ---

Side = Literal["top", "right", "bottom", "left"]
End = Literal["none", "arrow"]


class Edge(BaseModel):
    id: str = Field(default_factory=generate_id)
    fromNode: str
    toNode: str
    fromSide: Optional[Side] = None
    toSide: Optional[Side] = None
    fromEnd: Optional[End] = None
    toEnd: Optional[End] = None
    color: Optional[str] = None
    label: Optional[str] = None


# --- Canvas Document ---


class CanvasData(BaseModel):
    nodes: list[CanvasNode] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    @classmethod
    def from_json(cls, raw: str) -> CanvasData:
        data = json.loads(raw)
        return cls.model_validate(data)

    def to_json(self) -> str:
        data = self.model_dump(exclude_none=True)
        return json.dumps(data, indent="\t", ensure_ascii=False)


# --- Canvas Operations ---


def add_node_to_canvas(canvas: CanvasData, node: CanvasNode) -> CanvasData:
    if any(n.id == node.id for n in canvas.nodes):
        raise ValueError(f"Node with id '{node.id}' already exists")
    canvas.nodes.append(node)
    return canvas


def update_node_in_canvas(
    canvas: CanvasData, node_id: str, updates: dict
) -> CanvasData:
    for i, node in enumerate(canvas.nodes):
        if node.id == node_id:
            node_dict = node.model_dump()
            node_dict.update(updates)
            canvas.nodes[i] = _parse_node(node_dict)
            return canvas
    raise ValueError(f"Node '{node_id}' not found")


def remove_node_from_canvas(canvas: CanvasData, node_id: str) -> tuple[CanvasData, int]:
    """Remove a node and its connected edges. Returns (canvas, removed_edge_count)."""
    original_count = len(canvas.nodes)
    canvas.nodes = [n for n in canvas.nodes if n.id != node_id]
    if len(canvas.nodes) == original_count:
        raise ValueError(f"Node '{node_id}' not found")
    original_edges = len(canvas.edges)
    canvas.edges = [
        e for e in canvas.edges
        if e.fromNode != node_id and e.toNode != node_id
    ]
    removed_edges = original_edges - len(canvas.edges)
    return canvas, removed_edges


def add_edge_to_canvas(canvas: CanvasData, edge: Edge) -> CanvasData:
    node_ids = {n.id for n in canvas.nodes}
    if edge.fromNode not in node_ids:
        raise ValueError(f"fromNode '{edge.fromNode}' not found in canvas")
    if edge.toNode not in node_ids:
        raise ValueError(f"toNode '{edge.toNode}' not found in canvas")
    if any(e.id == edge.id for e in canvas.edges):
        raise ValueError(f"Edge with id '{edge.id}' already exists")
    canvas.edges.append(edge)
    return canvas


def remove_edge_from_canvas(canvas: CanvasData, edge_id: str) -> CanvasData:
    original_count = len(canvas.edges)
    canvas.edges = [e for e in canvas.edges if e.id != edge_id]
    if len(canvas.edges) == original_count:
        raise ValueError(f"Edge '{edge_id}' not found")
    return canvas


def _parse_node(data: dict) -> CanvasNode:
    node_type = data.get("type")
    match node_type:
        case "text":
            return TextNode.model_validate(data)
        case "file":
            return FileNode.model_validate(data)
        case "link":
            return LinkNode.model_validate(data)
        case "group":
            return GroupNode.model_validate(data)
        case _:
            raise ValueError(f"Unknown node type: '{node_type}'")
