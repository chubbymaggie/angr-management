
from collections import defaultdict

import networkx
from grandalf.utils.geometry import getangle
from grandalf.graphs import Graph, Edge, Vertex
from grandalf.layouts import VertexViewer, SugiyamaLayout
from grandalf.routing import EdgeViewer

from atom.api import List, Typed, ForwardTyped, observe
from enaml.widgets.api import Container
from enaml.widgets.frame import Frame
from enaml.core.declarative import d_
from enaml.qt.QtGui import QPainterPath
from enaml.qt.QtCore import QPointF, QRectF
from enaml.qt.qt_container import QtContainer

from .utils import grouper
from .graph import QtGraph, ProxyGraph


class QtFlowGraph(QtGraph):
    declaration = ForwardTyped(lambda: FlowGraph)

    @staticmethod
    def _route_edges(edge, points):
        """
        A simple edge routing algorithm.

        :param edge:
        :param points:
        :return:
        """

        # compute new beginning and ending
        src = edge.v[0].view
        src_width, src_height, (src_x, src_y) = src.w, src.h, src.xy

        dst = edge.v[1].view
        dst_width, dst_height, (dst_x, dst_y) = dst.w, dst.h, dst.xy

        start_point = (src_x, src_y + src_height / 2)
        end_point = (dst_x, dst_y - dst_height / 2)

        points[-1] = start_point
        points[0] = end_point

        edge.view.head_angle = getangle(points[-2], points[-1])

    def _layout_nodes_and_edges(self, start):
        """
        Compute coordinates for all CFG nodes and edges in the view

        :param int start: The starting address
        :return: a mapping between nodes' names and their coordinates (dict), and a list of edge coordinates (list)
        :rtype: tuple
        """

        coordinates = {}
        node_map = {}

        # Create the map
        for child in self.children():
            if not isinstance(child, QtContainer):
                continue
            node_map[child.declaration.addr] = child

        if start not in node_map:
            return { }

        vertices = {}
        edges = [ ]
        # Create all edges
        for s, d in self.declaration.edges:
            src, dst = int(s), int(d)
            if src in vertices:
                src_v = vertices[src]
            else:
                src_v = Vertex(src)
                vertices[src] = src_v

            if dst in vertices:
                dst_v = vertices[dst]
            else:
                dst_v = Vertex(dst)
                vertices[dst] = dst_v

            edge = Edge(src_v, dst_v)
            edge.view = EdgeViewer()
            edges.append(edge)

        # Create all vertices
        for child in self.children():
            addr = child.declaration.addr
            if addr not in vertices:
                vertices[addr] = Vertex(addr)

        g = Graph(vertices.values(), edges)

        # create a view for each node
        for addr, vertex in vertices.iteritems():
            node = node_map[addr]
            width, height = node._layout_manager.best_size()
            vertex.view = VertexViewer(width, height)

        sug = SugiyamaLayout(g.C[0])
        sug.route_edge = self._route_edges
        sug.init_all(roots=[vertices[start]])
        sug.draw()

        # extract coordinates for nodes
        for addr, vertex in vertices.iteritems():
            x, y = vertex.view.xy
            # Convert the center coordinate to left corner coordinate
            coordinates[addr] = (x - vertex.view.w / 2, y - vertex.view.h / 2)

        # extract coordinates for edges
        edge_coordinates = [ ]
        for edge in edges:
            if hasattr(edge.view, '_pts'):
                edge_coordinates.append(edge.view._pts)

        return coordinates, edge_coordinates

    def request_relayout(self):
        # y = 0.0

        # for child in self.children():
        #     if not isinstance(child, QtContainer):
        #         continue
        #     scene_proxy = self._proxies[child]
        #     width, height = child._layout_manager.best_size()
        #     scene_proxy.setPos(0.0, y)
        #     y += height + 25.0

        # Remove all paths
        for p in self._edge_paths:
            self.scene.removeItem(p)
        self._edge_paths = []

        children_names = {child.declaration.name for child in self.children() if isinstance(child, QtContainer)}

        if self.declaration.edges and \
                any(from_ not in children_names or to not in children_names for (from_, to) in self.declaration.edges):
            # hasn't finished being set up yet
            return

        for child in self.children():
            if not isinstance(child, QtContainer):
                continue
            scene_proxy = self._proxy(child)
            width, height = child._layout_manager.best_size()
            scene_proxy.setGeometry(QRectF(0.0, 0.0, width, height))

        node_coords, edge_coords = self._layout_nodes_and_edges(self.declaration.func_addr)

        if not node_coords:
            return

        for child in self.children():
            if not isinstance(child, QtContainer):
                continue
            scene_proxy = self._proxies[child]
            # width, height = child._layout_manager.best_size()
            x, y = node_coords[child.declaration.addr]
            scene_proxy.setPos(x, y)

        for edges in edge_coords:
            for from_, to_ in zip(edges, edges[1:]):
                painter = QPainterPath(QPointF(*from_))
                painter.lineTo(QPointF(*to_))
                p = self.scene.addPath(painter)
                self._edge_paths.append(p)

        rect = self.scene.itemsBoundingRect()
        # Enlarge the rect so there is enough room at right and bottom
        rect.setX(rect.x() - self.LEFT_PADDING)
        rect.setY(rect.y() - self.TOP_PADDING)
        rect.setWidth(rect.width() + 2 * self.LEFT_PADDING)
        rect.setHeight(rect.height() + 2 * self.TOP_PADDING)

        self.scene.setSceneRect(rect)
        self.widget.viewport().update()

        self.show_selected()

class FlowGraph(Frame):

    supergraph = d_(Typed(networkx.DiGraph))

    #: The edges (as names) of the Graph
    edges = d_(List())

    #: The "selected" node that should be visible
    selected = d_(Typed(str))

    func_addr = d_(Typed(int))

    proxy = Typed(ProxyGraph)

    hug_width = 'weak'
    hug_height = 'weak'

    def child_added(self, child):
        super(FlowGraph, self).child_added(child)

    def update(self):
        self.request_relayout()
