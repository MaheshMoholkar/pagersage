"use client";

// The graph canvas for every screen (U02 company graph, U03 incident path, U08 Ask evidence):
// <falkordb-canvas> (@falkordb/canvas, pinned) with our own node drawing. The canvas is
// transparent, so the dot-grid well of its container shows through. Links use the built-in
// renderer (colour and width per link, `isLinkSelected` for the highlighted path) plus
// force-graph's particles, which flow along the highlighted path.
//
//   highlight  amber: what PagerSage found (root-cause path, Ask evidence), glowing, with
//              particles flowing along its edges
//   colorBy    "team": ring and core dot in the owning team's colour
//              "plain": neutral
//   sizeBy     "criticality": bigger = more critical (company view; the default with "team")
//              "role": path and failing nodes a size up (incident view)
//   failing    the sick node: red fill that breathes, its health inside
//   blast      services hurt if `failing` is down: dashed blue rings, a blue ripple
//   rejected   ruled-out suspects: dashed, dimmed, name struck through
//   fit        bump it to animate the view back to fit everything
//   focus      glide to a node ({id, n}: bump n to go back to the same one)
// Fragile services (top betweenness) always get a red ring. The view zooms in once the
// layout settles. Nothing moves under prefers-reduced-motion.

import { animate } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  Data,
  FalkorDBCanvas,
  GraphLink,
  GraphNode,
} from "@falkordb/canvas";

import { teamColor } from "@/lib/format";
import type { GraphView, Highlight } from "@/lib/types";

// Canvas can't read CSS variables: these mirror the tokens in app/globals.css.
const C = {
  bg: "#05060a",
  raised: "#12141c",
  core: "#4a5062",
  pathFill: "#2a2112",
  nodeStroke: "rgba(255, 255, 255, 0.2)",
  edge: "rgba(150, 160, 185, 0.32)",
  amber: "#ffb224",
  amberGlow: "rgba(255, 178, 36, 0.55)",
  particle: "#ffe0a3",
  amberTint: "#2a1f0b",
  onAmberTint: "#ffd889",
  blue: "#6aa8ff",
  danger: "#ff5d6c",
  failing: "#4a1820",
  failingText: "#ffb1b8",
  text: "#eef0f5",
  text2: "#b8bcc8",
  muted: "#868b99",
  dashed: "#4a4f5d",
};

const TOOLTIP_CSS = `
.float-tooltip-kap {
  position: absolute;
  width: max-content;
  max-width: max(50%, 160px);
  padding: 4px 8px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(14, 16, 22, 0.94);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  color: ${C.text};
  font: 500 11px/16px var(--font-geist-mono), ui-monospace, monospace;
  letter-spacing: 0.02em;
  pointer-events: none;
}
`;

export interface GraphCanvasProps {
  graph: GraphView;
  highlight?: Highlight | null;
  colorBy?: "team" | "plain";
  sizeBy?: "criticality" | "role";
  failing?: string | null;
  blast?: boolean;
  rejected?: string[];
  height?: number | "fill";
  fit?: number;
  focus?: { id: string; n: number } | null;
  onNodeClick?: (id: string) => void;
}

type NodeData = {
  pid: string; // our string id
  name: string;
  kind: string;
  team: string | null;
  fragile: boolean;
  health: number | null;
};

const reducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Services that call `failing`, directly or not (DEPENDS_ON walked backwards). */
export function upstreamOf(
  graph: GraphView,
  failing: string | null | undefined,
): Set<string> {
  const callers = new Map<string, string[]>();
  for (const l of graph.links) {
    if (l.type !== "DEPENDS_ON") continue;
    callers.set(l.target, [...(callers.get(l.target) ?? []), l.source]);
  }
  const seen = new Set<string>();
  const queue = failing ? [failing] : [];
  while (queue.length) {
    for (const c of callers.get(queue.shift()!) ?? []) {
      if (!seen.has(c)) {
        seen.add(c);
        queue.push(c);
      }
    }
  }
  return seen;
}

/** "#79b4ff" -> "rgba(121,180,255,a)" */
function alpha(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

export function GraphCanvas({
  graph,
  highlight,
  colorBy = "plain",
  sizeBy = colorBy === "team" ? "criticality" : "role",
  failing,
  blast = false,
  rejected = [],
  height = 460,
  fit = 0,
  focus = null,
  onNodeClick,
}: GraphCanvasProps) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<FalkorDBCanvas>(null);
  const [ready, setReady] = useState(false);
  const [shown, setShown] = useState(false);
  const intro = useRef(true); // the first fit zooms in; later ones glide
  const pendingFit = useRef(true); // new data: fit once its layout settles

  // The web component touches HTMLElement at import: load it in the browser only.
  useEffect(() => {
    import("@falkordb/canvas").then(() => setReady(true));
  }, []);

  // Hover tooltips (a node's name, an edge's relationship) live in the component's shadow
  // DOM, where float-tooltip's own stylesheet in <head> can't reach: style them there.
  useEffect(() => {
    const root = canvas.current?.shadowRoot;
    if (!ready || !root || root.querySelector("style[data-ps-tooltip]")) return;
    const style = document.createElement("style");
    style.dataset.psTooltip = "";
    style.textContent = TOOLTIP_CSS;
    root.append(style);
  }, [ready]);

  const lit = useMemo(() => new Set(highlight?.nodes ?? []), [highlight]);
  const litEdges = useMemo(
    () =>
      new Set(
        (highlight?.edges ?? []).map(([a, rel, b]) => `${a}|${rel}|${b}`),
      ),
    [highlight],
  );
  const hurt = useMemo(
    () => (blast ? upstreamOf(graph, failing) : new Set<string>()),
    [graph, failing, blast],
  );
  const out = useMemo(() => new Set(rejected), [rejected]);

  const data: Data = useMemo(() => {
    const index = new Map(graph.nodes.map((n, i) => [n.id, i + 1]));
    const fragilities = graph.nodes
      .map((n) => n.fragility ?? 0)
      .sort((a, b) => b - a);
    const fragileCut = Math.max(fragilities[2] ?? 0, 1); // top three, and only if > 0
    const maxCrit = Math.max(
      ...graph.nodes.map((n) => n.criticality ?? 0),
      1e-9,
    );
    return {
      nodes: graph.nodes.map((n) => {
        const service = n.kind === "Service";
        const size = service
          ? sizeBy === "criticality"
            ? 8 + 10 * Math.sqrt((n.criticality ?? 0) / maxCrit)
            : lit.has(n.id) || n.id === failing
              ? 13
              : 10
          : 9;
        return {
          id: index.get(n.id)!,
          labels: [n.kind],
          color: colorBy === "team" ? teamColor(n.team) : C.raised,
          visible: true,
          size,
          data: {
            pid: n.id,
            name: n.name,
            kind: n.kind,
            team: n.team ?? null,
            fragile: service && (n.fragility ?? 0) >= fragileCut,
            health: n.health ?? null,
          } satisfies NodeData,
        };
      }),
      links: graph.links
        .filter((l) => index.has(l.source) && index.has(l.target))
        .map((l, i) => {
          const on = litEdges.has(`${l.source}|${l.type}|${l.target}`);
          return {
            id: i + 1,
            relationship: l.type,
            color: on ? C.amber : C.edge,
            width: on ? 1.5 : 1.2,
            arrowSize: on ? 4 : 6, // a selected link is drawn at 2x
            source: index.get(l.source)!,
            target: index.get(l.target)!,
            visible: true,
            data: {
              key: `${l.source}|${l.type}|${l.target}`,
              rejected: out.has(l.source),
            },
          };
        }),
    };
  }, [graph, colorBy, sizeBy, lit, litEdges, failing, out]);

  // Data in: once per graph change. Show it even if the layout never reports settling.
  useEffect(() => {
    if (!ready) return;
    pendingFit.current = true;
    canvas.current?.setData(data);
    const t = setTimeout(() => setShown(true), 1500);
    return () => clearTimeout(t);
  }, [ready, data]);

  // Look: node drawing, link styles, particles. Re-applied when what is highlighted changes.
  useEffect(() => {
    const el = canvas.current;
    if (!ready || !el) return;
    const font = getComputedStyle(document.body).fontFamily;
    const still = reducedMotion();
    const pulsing = !still && (!!failing || blast);
    const flowing = !still && litEdges.size > 0;

    const drawNode = (node: GraphNode, ctx: CanvasRenderingContext2D) => {
      const d = node.data as unknown as NodeData;
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const r = node.size;
      // Labels keep a readable screen size at any zoom: world units = px / zoom.
      const zoom = ctx.getTransform().a / (window.devicePixelRatio || 1);
      const px = (n: number) => n / Math.max(zoom, 0.05);
      const found = lit.has(d.pid);
      const isFailing = d.pid === failing;
      const isOut = out.has(d.pid);
      const now = performance.now();
      ctx.save();
      if (isOut) ctx.globalAlpha = 0.7;

      // blast radius: dashed rings upstream, a ripple from the failing node
      if (blast && hurt.has(d.pid)) {
        ctx.setLineDash([px(4), px(5)]);
        ctx.lineDashOffset = still ? 0 : -((now / 60) % 18) / zoom;
        ctx.strokeStyle = C.blue;
        ctx.lineWidth = px(1.5);
        ctx.beginPath();
        ctx.arc(x, y, r + px(8), 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      if (isFailing) {
        // a red glow that breathes, and with blast on, blue ripples that run outward
        const breathe = still ? 0.5 : 0.5 + 0.5 * Math.sin(now / 520);
        const glow = ctx.createRadialGradient(x, y, r, x, y, r + px(22));
        glow.addColorStop(0, `rgba(255, 93, 108, ${0.28 + 0.22 * breathe})`);
        glow.addColorStop(1, "rgba(255, 93, 108, 0)");
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(x, y, r + px(22), 0, 2 * Math.PI);
        ctx.fill();
        if (blast) {
          for (const offset of [0, 0.5]) {
            const t = still ? 0.3 : (now / 2400 + offset) % 1;
            ctx.globalAlpha = 0.65 * (1 - t);
            ctx.strokeStyle = C.blue;
            ctx.lineWidth = px(2);
            ctx.beginPath();
            ctx.arc(x, y, (r + px(4)) * (1 + 1.6 * t), 0, 2 * Math.PI);
            ctx.stroke();
          }
          ctx.globalAlpha = isOut ? 0.7 : 1;
        }
      }
      if (d.fragile) {
        ctx.shadowColor = alpha(C.danger, 0.7);
        ctx.shadowBlur = 10;
        ctx.strokeStyle = C.danger;
        ctx.lineWidth = px(1.75);
        ctx.beginPath();
        ctx.arc(x, y, r + px(4.5), 0, 2 * Math.PI);
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      // the node: services are circles; changes, deploys, alerts and people are pills
      const box = d.kind !== "Service";
      const unowned = colorBy === "team" && !box && !d.team;
      let w = 0;
      ctx.beginPath();
      if (box) {
        ctx.font = `500 ${px(11)}px ${font}`;
        w = Math.max(
          r * 2.8,
          ctx.measureText(d.name.slice(0, 24)).width + px(18),
        );
        ctx.roundRect(x - w / 2, y - px(13), w, px(26), px(8));
      } else ctx.arc(x, y, r, 0, 2 * Math.PI);

      // fill: flat; the ring and the core dot below carry the colour
      const team = colorBy === "team" && !box && !unowned;
      const fill = isFailing
        ? C.failing
        : found && box
          ? C.amberTint
          : found
            ? C.pathFill
            : isOut || unowned
              ? C.bg
              : team
                ? alpha(node.color, 0.18)
                : C.raised;
      if (found || isFailing) {
        ctx.shadowColor = isFailing ? "rgba(255,93,108,0.6)" : C.amberGlow;
        ctx.shadowBlur = 18;
      }
      if (team) {
        // an opaque base first, so edges under a translucent team fill don't show through
        ctx.fillStyle = C.bg;
        ctx.fill();
      }
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.setLineDash(isOut || unowned ? [px(5), px(4)] : []);
      ctx.strokeStyle =
        found || isFailing
          ? C.amber
          : isOut || unowned
            ? C.dashed
            : team
              ? node.color
              : C.nodeStroke;
      ctx.lineWidth = px(found || isFailing ? 2 : team ? 1.75 : 1.5);
      ctx.stroke();
      ctx.setLineDash([]);

      // a core dot in services: amber on the path, the team colour, or neutral
      if (!box && !isFailing && !isOut && !unowned) {
        ctx.fillStyle = found ? C.amber : team ? node.color : C.core;
        ctx.beginPath();
        ctx.arc(x, y, r * (team ? 0.42 : 0.3), 0, 2 * Math.PI);
        ctx.fill();
      }

      // health inside the failing node ("15%")
      if (isFailing && d.health != null) {
        ctx.fillStyle = C.failingText;
        ctx.font = `600 ${Math.min(px(11), r * 0.7)}px ui-monospace, monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`${Math.round(d.health * 100)}%`, x, y);
      }

      // label under the node (inside for pills)
      ctx.font = `${found || isFailing ? 600 : 500} ${px(box ? 11 : 12)}px ${font}`;
      ctx.textAlign = "center";
      ctx.textBaseline = box ? "middle" : "top";
      ctx.fillStyle =
        found && box
          ? C.onAmberTint
          : found || isFailing
            ? C.text
            : isOut
              ? C.muted
              : C.text2;
      const label = d.name.length > 24 ? `${d.name.slice(0, 23)}…` : d.name;
      const ly = box ? y : y + r + px(d.fragile ? 9 : 6);
      if (!box) {
        // Halo in the canvas colour so edges running under a label don't cut through it.
        ctx.lineJoin = "round";
        ctx.lineWidth = px(3.5);
        ctx.strokeStyle = alpha(C.bg, 0.85);
        ctx.strokeText(label, x, ly);
      }
      ctx.fillText(label, x, ly);
      if (isOut) {
        const tw = ctx.measureText(label).width;
        ctx.strokeStyle = C.muted;
        ctx.lineWidth = px(1);
        ctx.beginPath();
        ctx.moveTo(x - tw / 2, ly);
        ctx.lineTo(x + tw / 2, ly);
        ctx.stroke();
      }
      ctx.restore();
    };

    el.setConfig({
      backgroundColor: "rgba(0,0,0,0)",
      foregroundColor: C.text2,
      isNodeSelected: (n) => lit.has((n.data as unknown as NodeData).pid),
      isLinkSelected: (l: GraphLink) => litEdges.has(String(l.data.key)),
      linkLineDash: (l: GraphLink) => (l.data.rejected ? [3, 3] : []),
      node: {
        nodeCanvasObject: drawNode,
        nodePointerAreaPaint: (node, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x ?? 0, node.y ?? 0, node.size + 2, 0, 2 * Math.PI);
          ctx.fill();
        },
      },
      simulation: { chargeStrength: -240 },
      // No relationship captions on edges at any zoom: the legend explains them.
      largeGraph: {
        enabled: true,
        lowZoomThreshold: 1e6,
        skipLinkLabelsAtLowZoom: true,
        skipLabelsAtLowZoom: false,
        skipArrowsAtLowZoom: false,
      },
      interaction: { zoomToFitPadding: 0.1, zoomToFitMaxZoom: 4 },
      eventHandlers: {
        // Once a new layout settles: fit it. The first time, zoom in from a little further
        // out while the canvas fades in.
        onEngineStop: () => {
          if (!pendingFit.current) return;
          pendingFit.current = false;
          if (intro.current) zoomTo(el, still ? 0 : 0.9, 0.72);
          else zoomTo(el, still ? 0 : 0.6);
          intro.current = false;
          setShown(true);
        },
        onNodeHover: (n: GraphNode | null) => {
          if (wrap.current) wrap.current.style.cursor = n ? "pointer" : "";
        },
        ...(onNodeClick && {
          onNodeClick: (n: GraphNode) =>
            onNodeClick((n.data as unknown as NodeData).pid),
        }),
      },
    });
    // Particles along the highlighted path; keep repainting while anything moves
    // (force-graph pauses redraws when idle).
    const g = el.getGraph();
    // Hover tooltip on a node: its name and owning team (the library's default is the
    // canvas's internal numeric id).
    g?.nodeLabel((n: GraphNode) => {
      const d = n.data as unknown as NodeData;
      return d.team ? `${d.name} · ${d.team}` : d.name;
    });
    // ...and on an edge, the relationship in words ("depends on", not DEPENDS_ON).
    g?.linkLabel((l: GraphLink) =>
      l.relationship.toLowerCase().replaceAll("_", " "),
    );
    g?.linkDirectionalParticles((l: GraphLink) =>
      flowing && litEdges.has(String(l.data?.key)) ? 3 : 0,
    )
      .linkDirectionalParticleWidth(3.2)
      .linkDirectionalParticleSpeed(0.0055)
      .linkDirectionalParticleColor(() => C.particle);
    g?.autoPauseRedraw(!(pulsing || flowing));
    el.refresh();
  }, [ready, lit, litEdges, hurt, failing, blast, out, onNodeClick, colorBy]);

  // The Fit button: glide back to show everything.
  useEffect(() => {
    const el = canvas.current;
    if (ready && el && fit) zoomTo(el, reducedMotion() ? 0 : 0.6);
  }, [ready, fit]);

  // Path chips and evidence rows: glide to that node.
  useEffect(() => {
    if (!ready || !focus) return;
    const g = canvas.current?.getGraph();
    if (!g) return;
    const node = (g.graphData().nodes as GraphNode[]).find(
      (n) => (n.data as unknown as NodeData).pid === focus.id,
    );
    if (node?.x == null || node.y == null) return;
    glide(
      g,
      {
        x: node.x,
        y: node.y,
        k: Math.min(Math.max(g.zoom(), 2.4), g.maxZoom()),
      },
      reducedMotion() ? 0 : 0.7,
    );
  }, [ready, focus]);

  // Size: follow the container. A fixed `height`, or `"fill"` to take the parent's height.
  useEffect(() => {
    const el = canvas.current;
    const box = wrap.current;
    if (!ready || !el || !box) return;
    const resize = () => {
      el.setWidth(box.clientWidth);
      el.setHeight(height === "fill" ? box.clientHeight : height);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(box);
    return () => observer.disconnect();
  }, [ready, height]);

  return (
    <div
      ref={wrap}
      className={`w-full overflow-hidden transition-opacity duration-700 ease-out ${shown ? "opacity-100" : "opacity-0"} ${height === "fill" ? "h-full" : "rounded-card"}`}
      style={height === "fill" ? undefined : { height }}
    >
      <falkordb-canvas ref={canvas} node-mode="replace" />
    </div>
  );
}

type Graph = NonNullable<ReturnType<FalkorDBCanvas["getGraph"]>>;
type View = { x: number; y: number; k: number };

// Wheel and pinch zoom stay within these multiples of the zoom that fits every node.
const ZOOM_OUT = 0.6;
const ZOOM_IN = 3.5;

/** Move the view to `to` in one eased animation (force-graph's own centerAt and zoom
 *  transitions interrupt each other when run together). */
function glide(g: Graph, to: View, seconds: number, from?: View) {
  const c = g.centerAt();
  const start = from ?? { x: c.x, y: c.y, k: g.zoom() };
  if (!seconds) {
    g.centerAt(to.x, to.y, 0);
    g.zoom(to.k, 0);
    return;
  }
  animate(0, 1, {
    duration: seconds,
    ease: [0.22, 1, 0.36, 1],
    onUpdate: (t) => {
      g.centerAt(
        start.x + (to.x - start.x) * t,
        start.y + (to.y - start.y) * t,
        0,
      );
      g.zoom(start.k + (to.k - start.k) * t, 0);
    },
  });
}

/** Animate the view to fit every node, from `from` × the fitted zoom (1 = from where it is). */
function zoomTo(el: FalkorDBCanvas, seconds: number, from = 1) {
  const g = el.getGraph();
  if (!g) return;
  const c0 = g.centerAt();
  const now = { x: c0.x, y: c0.y, k: g.zoom() };
  g.minZoom(0.01).maxZoom(1000); // last fit's limits must not clamp this one
  el.zoomToFit(1);
  const c1 = g.centerAt();
  const fitted = { x: c1.x, y: c1.y, k: g.zoom() };
  g.minZoom(fitted.k * ZOOM_OUT).maxZoom(fitted.k * ZOOM_IN);
  if (!seconds) return;
  glide(
    g,
    fitted,
    seconds,
    from === 1 ? now : { ...fitted, k: fitted.k * from },
  );
}
