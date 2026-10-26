import tkinter as tk
from tkinter import ttk, messagebox
import math
import heapq
import time


class RoutingVisualizer:
    NODE_RADIUS = 17

    def __init__(self, root):
        self.root = root
        self.root.title("Interactive Network Routing & Cable Layout (Prim’s Algorithm Visualizer)")
        self.root.geometry("1320x790")
        self.root.minsize(980, 620)

        self.mode = tk.StringVar(value="add")
        self.speed = tk.DoubleVar(value=0.7)
        self.status = tk.StringVar(value="Choose a mode, then click the canvas.")
        self.nodes = {}              # node id -> {"x": float, "y": float}
        self.edges = {}              # (u, v) -> Euclidean weight; keys are normalized
        self.next_node_id = 1
        self.selected_node = None
        self.drag_start = None
        self.dragging_node = None
        self.drag_offset = (0, 0)

        self.running = False
        self.after_id = None
        self.steps = []
        self.step_index = 0
        self.mst_edges = set()
        self.candidate_edge = None
        self.rejected_edges = set()
        self.mst_cost = 0.0
        self.visited = set()
        self.algorithm_started = False

        self._build_ui()
        self._refresh_all()

    def _build_ui(self):
        self.root.configure(bg="#edf1f5")
        toolbar = ttk.Frame(self.root, padding=(10, 8))
        toolbar.pack(side=tk.TOP, fill=tk.X)

        mode_frame = ttk.LabelFrame(toolbar, text="Interaction mode", padding=6)
        mode_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        for text, value in [
            ("Add City (Node)", "add"),
            ("Connect Cable (Edge)", "connect"),
            ("Move City", "move"),
            ("Delete", "delete"),
        ]:
            ttk.Radiobutton(
                mode_frame, text=text, value=value, variable=self.mode,
                command=self._mode_changed
            ).pack(side=tk.LEFT, padx=3)

        action_frame = ttk.LabelFrame(toolbar, text="Prim’s algorithm", padding=6)
        action_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        ttk.Button(action_frame, text="Run Prim's MST", command=self.run_prim).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Step Forward", command=self.step_forward).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Auto Play", command=self.auto_play).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Pause", command=self.pause).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Reset All", command=self.reset_all).pack(side=tk.LEFT, padx=2)

        speed_frame = ttk.LabelFrame(toolbar, text="Animation speed", padding=6)
        speed_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        self.speed_scale = ttk.Scale(
            speed_frame, from_=0.1, to=2.0, variable=self.speed,
            orient=tk.HORIZONTAL, length=125
        )
        self.speed_scale.pack(side=tk.LEFT, padx=4)
        self.speed_label = ttk.Label(speed_frame, text="0.7 s")
        self.speed_label.pack(side=tk.LEFT)
        self.speed.trace_add("write", self._speed_changed)

        status_frame = ttk.LabelFrame(toolbar, text="Live status", padding=6)
        status_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(status_frame, textvariable=self.status, wraplength=260).pack(anchor="w")

        body = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        body.pack(fill=tk.BOTH, expand=True)

        canvas_frame = ttk.LabelFrame(body, text="Network canvas — click to add; drag between cities to connect", padding=5)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=1, highlightbackground="#cbd5e1")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._canvas_press)
        self.canvas.bind("<B1-Motion>", self._canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._canvas_release)
        self.canvas.bind("<Motion>", self._canvas_motion)

        side = ttk.Frame(body, width=320)
        side.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        side.pack_propagate(False)

        metrics = ttk.LabelFrame(side, text="Network metrics", padding=10)
        metrics.pack(fill=tk.X, pady=(0, 8))
        self.city_count = tk.StringVar(value="0")
        self.edge_count = tk.StringVar(value="0")
        self.cost_value = tk.StringVar(value="0.00")
        self.visited_value = tk.StringVar(value="0")
        for label, variable in [
            ("Total Cities (|V|)", self.city_count),
            ("Available Connections (|E|)", self.edge_count),
            ("Current MST Cost", self.cost_value),
            ("Cities in MST", self.visited_value),
        ]:
            row = ttk.Frame(metrics)
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text=label).pack(side=tk.LEFT)
            ttk.Label(row, textvariable=variable, font=("TkDefaultFont", 10, "bold")).pack(side=tk.RIGHT)

        legend = ttk.LabelFrame(side, text="Edge legend", padding=8)
        legend.pack(fill=tk.X, pady=(0, 8))
        self._legend_row(legend, "#8b949e", "Initial cable", dashed=False, width=2)
        self._legend_row(legend, "#eab308", "Candidate under evaluation", dashed=True, width=3)
        self._legend_row(legend, "#16a34a", "Accepted MST link", dashed=False, width=5)
        self._legend_row(legend, "#dc2626", "Rejected (would form cycle)", dashed=False, width=3)

        log_frame = ttk.LabelFrame(side, text="Execution log", padding=7)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(log_frame, wrap=tk.WORD, height=18, width=36, state=tk.DISABLED,
                           font=("Consolas", 9), bg="#fbfcfe", relief=tk.FLAT)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        footer = ttk.Label(self.root, text=(
            "Tip: In Connect mode, press on one city and release on another. "
            "Edge weights are straight-line pixel distances. Prim’s algorithm needs a connected graph."
        ), padding=(12, 5), foreground="#475569")
        footer.pack(side=tk.BOTTOM, fill=tk.X)

    def _legend_row(self, parent, color, label, dashed=False, width=2):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        sample = tk.Canvas(row, width=45, height=15, bg="white", highlightthickness=0)
        sample.pack(side=tk.LEFT, padx=(0, 7))
        sample.create_line(3, 8, 42, 8, fill=color, width=width, dash=(5, 3) if dashed else ())
        ttk.Label(row, text=label).pack(side=tk.LEFT)

    @staticmethod
    def edge_key(u, v):
        return (u, v) if u < v else (v, u)

    def _speed_changed(self, *_):
        self.speed_label.configure(text=f"{self.speed.get():.1f} s")

    def _mode_changed(self):
        self.selected_node = None
        self.drag_start = None
        self.dragging_node = None
        names = {
            "add": "Add mode: click an empty area to create a city.",
            "connect": "Connect mode: drag from one city to another.",
            "move": "Move mode: drag a city to reposition it.",
            "delete": "Delete mode: click a city or cable to remove it.",
        }
        self.status.set(names[self.mode.get()])

    def _node_at(self, x, y):
        for node_id, node in reversed(list(self.nodes.items())):
            if math.hypot(node["x"] - x, node["y"] - y) <= self.NODE_RADIUS + 4:
                return node_id
        return None

    def _edge_at(self, x, y, threshold=8):
        for edge in self.edges:
            u, v = edge
            a, b = self.nodes[u], self.nodes[v]
            dx, dy = b["x"] - a["x"], b["y"] - a["y"]
            length_sq = dx * dx + dy * dy
            if length_sq == 0:
                distance = math.hypot(x - a["x"], y - a["y"])
            else:
                t = max(0, min(1, ((x - a["x"]) * dx + (y - a["y"]) * dy) / length_sq))
                px, py = a["x"] + t * dx, a["y"] + t * dy
                distance = math.hypot(x - px, y - py)
            if distance <= threshold:
                return edge
        return None

    def _canvas_press(self, event):
        x, y = event.x, event.y
        mode = self.mode.get()
        node_id = self._node_at(x, y)

        if mode == "add":
            if node_id is None:
                self._add_node(x, y)
            else:
                self.status.set(f"City {node_id} is already here.")
        elif mode == "connect":
            if node_id is not None:
                self.drag_start = node_id
                self.status.set(f"Connecting from City {node_id}… release on another city.")
            else:
                self.drag_start = None
                self.status.set("Start the cable on an existing city.")
        elif mode == "move":
            if node_id is not None:
                self.dragging_node = node_id
                self.drag_offset = (self.nodes[node_id]["x"] - x, self.nodes[node_id]["y"] - y)
                self.selected_node = node_id
                self.status.set(f"Moving City {node_id}.")
            else:
                self.selected_node = None
        elif mode == "delete":
            if node_id is not None:
                self._delete_node(node_id)
            else:
                edge = self._edge_at(x, y)
                if edge:
                    self.edges.pop(edge, None)
                    self._invalidate_algorithm()
                    self._log(f"Deleted cable City {edge[0]} — City {edge[1]}.")
                    self._refresh_all()
                    self.status.set("Cable deleted.")
                else:
                    self.status.set("Click a city or cable to delete it.")
        self._draw_canvas()

    def _canvas_drag(self, event):
        if self.mode.get() == "move" and self.dragging_node in self.nodes:
            node_id = self.dragging_node
            ox, oy = self.drag_offset
            x = max(self.NODE_RADIUS + 2, min(self.canvas.winfo_width() - self.NODE_RADIUS - 2, event.x + ox))
            y = max(self.NODE_RADIUS + 2, min(self.canvas.winfo_height() - self.NODE_RADIUS - 2, event.y + oy))
            self.nodes[node_id]["x"], self.nodes[node_id]["y"] = x, y
            self._recalculate_weights()
            self._invalidate_algorithm()
            self._refresh_all()
        elif self.mode.get() == "connect" and self.drag_start in self.nodes:
            self._draw_canvas(preview=(self.nodes[self.drag_start]["x"], self.nodes[self.drag_start]["y"], event.x, event.y))

    def _canvas_release(self, event):
        if self.mode.get() == "connect" and self.drag_start is not None:
            start = self.drag_start
            end = self._node_at(event.x, event.y)
            if end is not None and end != start:
                key = self.edge_key(start, end)
                weight = self._distance(start, end)
                if key in self.edges:
                    self.status.set(f"Cable between City {start} and City {end} already exists.")
                else:
                    self.edges[key] = weight
                    self._invalidate_algorithm()
                    self._log(f"Added cable {start} — {end}, distance {weight:.2f}.")
                    self.status.set(f"Cable added: {start} — {end} ({weight:.2f}).")
                    self._refresh_all()
            elif end == start:
                self.status.set("Choose a different city as the cable endpoint.")
            else:
                self.status.set("Cable cancelled: release on an existing city.")
        self.drag_start = None
        self.dragging_node = None
        self._draw_canvas()

    def _canvas_motion(self, event):
        if self.mode.get() == "connect" and self.drag_start is not None:
            self._draw_canvas(preview=(self.nodes[self.drag_start]["x"], self.nodes[self.drag_start]["y"], event.x, event.y))

    def _add_node(self, x, y):
        node_id = self.next_node_id
        self.next_node_id += 1
        self.nodes[node_id] = {"x": x, "y": y}
        self._invalidate_algorithm()
        self._log(f"Added City {node_id} at ({int(x)}, {int(y)}).")
        self.status.set(f"City {node_id} added.")
        self._refresh_all()

    def _delete_node(self, node_id):
        self.nodes.pop(node_id, None)
        removed = [edge for edge in self.edges if node_id in edge]
        for edge in removed:
            self.edges.pop(edge, None)
        self._invalidate_algorithm()
        self._log(f"Deleted City {node_id} and {len(removed)} connected cable(s).")
        self.status.set(f"City {node_id} deleted.")
        self._refresh_all()

    def _distance(self, u, v):
        a, b = self.nodes[u], self.nodes[v]
        return math.hypot(a["x"] - b["x"], a["y"] - b["y"])

    def _recalculate_weights(self):
        for edge in list(self.edges):
            self.edges[edge] = self._distance(*edge)

    def _invalidate_algorithm(self):
        self.pause()
        self.steps = []
        self.step_index = 0
        self.mst_edges.clear()
        self.rejected_edges.clear()
        self.candidate_edge = None
        self.mst_cost = 0.0
        self.visited.clear()
        self.algorithm_started = False
        self._update_metrics()

    def _draw_canvas(self, preview=None):
        self.canvas.delete("all")
        # Draw cables first so city circles sit above them.
        for edge, weight in self.edges.items():
            u, v = edge
            a, b = self.nodes[u], self.nodes[v]
            color, width, dash = "#8b949e", 2, ()
            if edge in self.mst_edges:
                color, width = "#16a34a", 5
            elif edge == self.candidate_edge:
                color, width, dash = "#eab308", 3, (7, 4)
            elif edge in self.rejected_edges:
                color, width = "#dc2626", 3
            self.canvas.create_line(a["x"], a["y"], b["x"], b["y"], fill=color, width=width,
                                    dash=dash, capstyle=tk.ROUND)
            mx, my = (a["x"] + b["x"]) / 2, (a["y"] + b["y"]) / 2
            self.canvas.create_rectangle(mx - 24, my - 10, mx + 24, my + 10, fill="white", outline="")
            self.canvas.create_text(mx, my, text=f"{weight:.1f}", fill="#334155",
                                    font=("TkDefaultFont", 8, "bold"))
        if preview:
            x1, y1, x2, y2 = preview
            self.canvas.create_line(x1, y1, x2, y2, fill="#eab308", width=2, dash=(5, 3))
        for node_id, node in self.nodes.items():
            x, y = node["x"], node["y"]
            fill = "#dbeafe"
            outline = "#2563eb"
            if node_id in self.visited:
                fill, outline = "#bbf7d0", "#15803d"
            if node_id == self.selected_node:
                outline = "#7c3aed"
            self.canvas.create_oval(x - self.NODE_RADIUS, y - self.NODE_RADIUS,
                                    x + self.NODE_RADIUS, y + self.NODE_RADIUS,
                                    fill=fill, outline=outline, width=2)
            self.canvas.create_text(x, y, text=str(node_id), fill="#0f172a",
                                    font=("TkDefaultFont", 10, "bold"))

    def _update_metrics(self):
        self.city_count.set(str(len(self.nodes)))
        self.edge_count.set(str(len(self.edges)))
        self.cost_value.set(f"{self.mst_cost:.2f}")
        self.visited_value.set(str(len(self.visited)))

    def _refresh_all(self):
        self._draw_canvas()
        self._update_metrics()

    def _log(self, message):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _is_connected(self):
        if len(self.nodes) <= 1:
            return True
        adjacency = {node_id: [] for node_id in self.nodes}
        for u, v in self.edges:
            adjacency[u].append(v)
            adjacency[v].append(u)
        start = next(iter(self.nodes))
        reached = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor not in reached:
                    reached.add(neighbor)
                    stack.append(neighbor)
        return len(reached) == len(self.nodes)

    def run_prim(self):
        self.pause()
        if not self.nodes:
            messagebox.showinfo("Prim’s MST", "Add at least one city first.")
            return
        if not self._is_connected():
            messagebox.showwarning(
                "Network is disconnected",
                "Prim’s algorithm can only build one spanning tree when every city is connected. "
                "Add cables to connect all cities, then run it again."
            )
            self.status.set("Network is disconnected. Add cables to connect every city.")
            self._log("Cannot build a spanning tree: the network has disconnected cities.")
            return

        self.mst_edges.clear()
        self.rejected_edges.clear()
        self.candidate_edge = None
        self.mst_cost = 0.0
        self.visited.clear()
        self.steps = []
        self.step_index = 0
        self.algorithm_started = True

        start = min(self.nodes)
        self.steps.append(("visit", start, None, None))
        # Heap entries are (weight, source, destination); stale edges are logged as rejected.
        heap = []
        seen = {start}
        for neighbor, weight in self._neighbors(start):
            heapq.heappush(heap, (weight, start, neighbor))

        while heap and len(seen) < len(self.nodes):
            weight, u, v = heapq.heappop(heap)
            edge = self.edge_key(u, v)
            if v in seen:
                self.steps.append(("reject", edge, weight, f"Cable {u}—{v} would form a cycle; skipped."))
                continue
            self.steps.append(("candidate", edge, weight, f"Evaluating cable {u}—{v}, distance {weight:.2f}."))
            self.steps.append(("accept", edge, weight, f"Accepted cable {u}—{v} ({weight:.2f}); added to MST."))
            seen.add(v)
            self.steps.append(("visit", v, None, None))
            for neighbor, neighbor_weight in self._neighbors(v):
                if neighbor not in seen:
                    heapq.heappush(heap, (neighbor_weight, v, neighbor))

        self.steps.append(("done", None, None, "Prim’s algorithm completed."))
        self._log(f"Starting Prim’s algorithm from City {start}.")
        self.status.set("Prim’s MST ready. Use Step Forward or Auto Play.")
        self._refresh_all()

    def _neighbors(self, node_id):
        result = []
        for (u, v), weight in self.edges.items():
            if u == node_id:
                result.append((v, weight))
            elif v == node_id:
                result.append((u, weight))
        return result

    def step_forward(self):
        if not self.algorithm_started or not self.steps:
            self.run_prim()
            if not self.algorithm_started or not self.steps:
                return
        if self.step_index >= len(self.steps):
            self.status.set("Algorithm finished. Reset or change the network to run again.")
            return

        action, item, weight, message = self.steps[self.step_index]
        self.step_index += 1
        if action == "visit":
            self.visited.add(item)
            self._log(f"Visited City {item}.")
            self.status.set(f"Visited City {item}.")
        elif action == "candidate":
            self.candidate_edge = item
            self._log(message)
            self.status.set(message)
        elif action == "accept":
            self.candidate_edge = None
            self.mst_edges.add(item)
            self.mst_cost += weight
            self._log(f"{message} Current MST cost: {self.mst_cost:.2f}.")
            self.status.set(f"MST cost: {self.mst_cost:.2f}")
        elif action == "reject":
            self.candidate_edge = None
            self.rejected_edges.add(item)
            self._log(message)
            self.status.set(message)
        elif action == "done":
            self.candidate_edge = None
            self._log(f"{message} Final MST cost: {self.mst_cost:.2f}.")
            self.status.set(f"Complete — total MST cost {self.mst_cost:.2f}.")
        self._refresh_all()

    def auto_play(self):
        if not self.algorithm_started or not self.steps:
            self.run_prim()
            if not self.algorithm_started or not self.steps:
                return
        if self.step_index >= len(self.steps):
            self.status.set("Algorithm is already complete.")
            return
        if self.running:
            return
        self.running = True
        self.status.set("Auto playing…")
        self._auto_tick()

    def _auto_tick(self):
        if not self.running:
            return
        if self.step_index >= len(self.steps):
            self.running = False
            self.after_id = None
            return
        self.step_forward()
        if self.running and self.step_index < len(self.steps):
            delay = int(self.speed.get() * 1000)
            self.after_id = self.root.after(max(50, delay), self._auto_tick)
        else:
            self.running = False
            self.after_id = None

    def pause(self):
        self.running = False
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None

    def reset_all(self):
        self.pause()
        self.nodes.clear()
        self.edges.clear()
        self.next_node_id = 1
        self.selected_node = None
        self.drag_start = None
        self.dragging_node = None
        self.steps = []
        self.step_index = 0
        self.mst_edges.clear()
        self.rejected_edges.clear()
        self.candidate_edge = None
        self.mst_cost = 0.0
        self.visited.clear()
        self.algorithm_started = False
        self._clear_log()
        self._log("Network cleared. Add cities to begin.")
        self.status.set("Reset complete. Add cities to begin.")
        self._refresh_all()


def main():
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("clam")
    except tk.TclError:
        pass
    RoutingVisualizer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
