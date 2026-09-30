"""Renderer-port prototypes; graph structure is always supplied by the model."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Protocol

from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene, QGraphicsTextItem

from .domain import TopologyResult


class TopologyRendererPort(Protocol):
    def render(self, topology: TopologyResult): ...


class QtNativeRenderer:
    def render(self, topology: TopologyResult) -> QGraphicsScene:
        scene = QGraphicsScene()
        positions = {
            node: (index * 140, (index % 2) * 80) for index, node in enumerate(topology.nodes)
        }
        for node, (x, y) in positions.items():
            label = QGraphicsTextItem(node)
            label.setPos(x, y)
            scene.addItem(label)
        for source, target in topology.edges:
            x1, y1 = positions[source]
            x2, y2 = positions[target]
            scene.addItem(QGraphicsLineItem(x1, y1, x2, y2))
        return scene


@dataclass(frozen=True, slots=True)
class WebViewDocument:
    html: str
    view: object


class WebViewPrototypeRenderer:
    def render(self, topology: TopologyResult) -> WebViewDocument:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        nodes = "".join(f"<li>{escape(node)}</li>" for node in topology.nodes)
        edges = "".join(
            f"<li>{escape(source)} → {escape(target)}</li>" for source, target in topology.edges
        )
        html = f"<html><body><ul>{nodes}</ul><ol>{edges}</ol></body></html>"
        view = QWebEngineView()
        view.setHtml(html)
        return WebViewDocument(html, view)
