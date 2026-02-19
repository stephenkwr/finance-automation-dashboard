// frontend/src/App.jsx
import { useEffect, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  Brush,
} from "recharts";

// ---------- helpers ----------
function isoDate(d) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d;
}

// ---------- styles ----------
const presetBtnStyle = {
  padding: "6px 10px",
  borderRadius: 8,
  border: "1px solid #333",
  background: "#1a1a1a",
  color: "white",
  cursor: "pointer",
};

function dateStyle(disabled) {
  return {
    padding: 6,
    background: disabled ? "#141414" : "#222",
    border: "1px solid #333",
    color: disabled ? "#777" : "white",
    borderRadius: 6,
  };
}

const buttonStyle = {
  padding: "7px 12px",
  borderRadius: 8,
  border: "1px solid #333",
  background: "#1a1a1a",
  color: "white",
  cursor: "pointer",
};

function CustomTooltip({ active, label, payload }) {
  if (!active || !payload || !payload.length) return null;

  const close = payload[0]?.value;

  return (
    <div
      style={{
        background: "#111",
        border: "1px solid #333",
        borderRadius: 10,
        padding: "10px 12px",
        color: "white",
        minWidth: 170,
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{label}</div>
      <div style={{ opacity: 0.9 }}>
        Close: <b>{Number(close).toFixed(2)}</b>
      </div>
    </div>
  );
}

// ---------- component ----------
export default function App() {
  const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

  // MAX should be limited to what your free plan supports (2 years)
  const MAX_HISTORY_DAYS = 365 * 2;

  // user typing
  const [tickerDraft, setTickerDraft] = useState("GDX");
  // confirmed ticker
  const [activeTicker, setActiveTicker] = useState("GDX");

  // chart series (FULL)
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // brush window (indices into FULL data)
  const [brushStart, setBrushStart] = useState(0);
  const [brushEnd, setBrushEnd] = useState(0);

  // selected day & news
  const [selectedDay, setSelectedDay] = useState(null);
  const [newsLoading, setNewsLoading] = useState(false);
  const [headlines, setHeadlines] = useState([]);
  const [newsError, setNewsError] = useState("");

  // date range inputs
  const [rangeStart, setRangeStart] = useState(isoDate(daysAgo(365)));
  const [rangeEnd, setRangeEnd] = useState(isoDate(new Date()));

  const draftIsDifferent =
    tickerDraft.toUpperCase().trim() !== activeTicker.toUpperCase().trim();

  // Fix the “background not spanning full page” issue coming from Vite template CSS
  useEffect(() => {
    document.documentElement.style.height = "100%";
    document.body.style.height = "100%";
    document.body.style.margin = "0";
    document.body.style.background = "#0f0f0f";

    const root = document.getElementById("root");
    if (root) {
      root.style.maxWidth = "none";
      root.style.margin = "0";
      root.style.padding = "0";
      root.style.width = "100%";
      root.style.minHeight = "100vh";
      root.style.background = "#0f0f0f";
    }
  }, []);

  // visible series based on brush
  const visibleData = useMemo(() => {
    if (!data.length) return [];
    const s = Math.max(0, Math.min(brushStart, data.length - 1));
    const e = Math.max(0, Math.min(brushEnd, data.length - 1));
    const lo = Math.min(s, e);
    const hi = Math.max(s, e);
    return data.slice(lo, hi + 1);
  }, [data, brushStart, brushEnd]);

  // min/max on visible window
  const minMax = useMemo(() => {
    if (!visibleData.length) return null;
    let min = visibleData[0].close;
    let max = visibleData[0].close;
    for (const d of visibleData) {
      if (d.close < min) min = d.close;
      if (d.close > max) max = d.close;
    }
    return { min, max };
  }, [visibleData]);

  // reset brush whenever data changes
  useEffect(() => {
    if (data.length) {
      setBrushStart(0);
      setBrushEnd(data.length - 1);
    } else {
      setBrushStart(0);
      setBrushEnd(0);
    }
  }, [data]);

  function buildPricesUrl(ticker, start, end) {
    const t = (ticker || "").toUpperCase().trim();
    const params = new URLSearchParams();
    params.set("ticker", t);
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return `${API_BASE}/prices/close?${params.toString()}`;
  }

  async function loadCloseSeries(ticker, start, end) {
    const t = (ticker || "").toUpperCase().trim();
    if (!t) return;

    setError("");
    const url = buildPricesUrl(t, start, end);
    const res = await fetch(url);

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`Backend error: ${res.status} ${txt}`);
    }

    const rows = await res.json();
    const normalized = rows.map((r) => ({
      date: r.date,
      close: Number(r.close),
    }));

    setData(normalized);
  }

  async function loadNews(ticker, day) {
    const t = (ticker || "").toUpperCase().trim();
    if (!t || !day) return;

    setNewsLoading(true);
    setNewsError("");
    setHeadlines([]);

    try {
      const res = await fetch(
        `${API_BASE}/news?ticker=${encodeURIComponent(t)}&day=${encodeURIComponent(day)}`
      );
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`News error: ${res.status} ${txt}`);
      }
      const json = await res.json();
      setHeadlines(Array.isArray(json.headlines) ? json.headlines : []);
    } catch (e) {
      setNewsError(e?.message || String(e));
      setHeadlines([]);
    } finally {
      setNewsLoading(false);
    }
  }

  async function confirmIngestRange(ticker, start, end) {
    const t = (ticker || "").toUpperCase().trim();
    if (!t) return;

    const qs = new URLSearchParams();
    qs.set("ticker", t);
    if (start) qs.set("start", start);
    if (end) qs.set("end", end);

    const res = await fetch(`${API_BASE}/symbols/confirm?${qs.toString()}`, {
      method: "POST",
    });

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`Confirm failed: ${res.status} ${txt}`);
    }

    return res.json();
  }

  async function confirmAndLoad(sym) {
    const t = (sym || "").toUpperCase().trim();
    if (!t) return;

    setLoading(true);
    setError("");
    setSelectedDay(null);
    setHeadlines([]);
    setNewsError("");

    try {
      await confirmIngestRange(t, rangeStart, rangeEnd);
      setActiveTicker(t);
      await loadCloseSeries(t, rangeStart, rangeEnd);
    } catch (e) {
      setError(e?.message || String(e));
      setData([]);
    } finally {
      setLoading(false);
    }
  }

  async function applyRange() {
    const t = (activeTicker || "").toUpperCase().trim();
    if (!t) return;

    setLoading(true);
    setError("");
    setSelectedDay(null);
    setHeadlines([]);
    setNewsError("");

    try {
      await confirmIngestRange(t, rangeStart, rangeEnd);
      await loadCloseSeries(t, rangeStart, rangeEnd);
    } catch (e) {
      setError(e?.message || String(e));
      setData([]);
    } finally {
      setLoading(false);
    }
  }

  async function applyPreset(days) {
    const t = (activeTicker || "").toUpperCase().trim();
    if (!t) return;

    const endStr = isoDate(new Date());
    const startStr = isoDate(daysAgo(days));

    setRangeStart(startStr);
    setRangeEnd(endStr);

    setLoading(true);
    setError("");
    setSelectedDay(null);
    setHeadlines([]);
    setNewsError("");

    try {
      await confirmIngestRange(t, startStr, endStr);
      await loadCloseSeries(t, startStr, endStr);
    } catch (e) {
      setError(e?.message || String(e));
      setData([]);
    } finally {
      setLoading(false);
    }
  }

  async function applyMax() {
    // “MAX” = last 2 years (free plan)
    return applyPreset(MAX_HISTORY_DAYS);
  }

  // Initial load
  useEffect(() => {
    confirmAndLoad(activeTicker);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // layout constants
  const chartColWidth = 640;
  const pageTopPadding = 24;
  const headerHeight = 0; // we’re not measuring; we’ll just allow page scroll if needed

  return (
    <div
      style={{
        padding: pageTopPadding,
        fontFamily: "sans-serif",
        color: "white",
        background: "#0f0f0f",
        minHeight: "100vh",
        width: "100vw",
        boxSizing: "border-box",
      }}
    >
      <h1 style={{ marginTop: 0 }}>Market + News Dashboard</h1>

      {/* Top controls */}
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          marginBottom: 12,
          flexWrap: "wrap",
        }}
      >
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          Ticker:
          <input
            value={tickerDraft}
            onChange={(e) => setTickerDraft(e.target.value.toUpperCase())}
            style={{
              padding: 6,
              background: "#222",
              border: "1px solid #333",
              color: "white",
              borderRadius: 6,
              width: 180,
            }}
          />
        </label>

        <button
          onClick={() => confirmAndLoad(tickerDraft)}
          disabled={loading}
          style={{ ...buttonStyle, opacity: loading ? 0.6 : 1 }}
        >
          {loading ? "Working..." : "Confirm / Load"}
        </button>

        <span style={{ opacity: 0.85 }}>
          Active: <b>{activeTicker}</b>
          {draftIsDifferent ? " (draft not confirmed)" : ""}
        </span>

        {minMax && (
          <span style={{ opacity: 0.85 }}>
            Visible: {minMax.min.toFixed(2)} – {minMax.max.toFixed(2)}
          </span>
        )}
      </div>

      {/* Range controls */}
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          marginBottom: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={() => applyPreset(30)} style={presetBtnStyle} disabled={loading}>
            1M
          </button>
          <button onClick={() => applyPreset(90)} style={presetBtnStyle} disabled={loading}>
            3M
          </button>
          <button onClick={() => applyPreset(180)} style={presetBtnStyle} disabled={loading}>
            6M
          </button>
          <button onClick={() => applyPreset(365)} style={presetBtnStyle} disabled={loading}>
            1Y
          </button>
          <button onClick={applyMax} style={presetBtnStyle} disabled={loading}>
            MAX (2Y)
          </button>
        </div>

        <span style={{ opacity: 0.8 }}>
          Range: {rangeStart} → {rangeEnd}
        </span>

        <button
          onClick={applyRange}
          disabled={loading || !activeTicker}
          style={{ ...buttonStyle, opacity: loading || !activeTicker ? 0.6 : 1 }}
        >
          Apply Range
        </button>

        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          Start:
          <input
            type="date"
            value={rangeStart}
            disabled={loading}
            onChange={(e) => setRangeStart(e.target.value)}
            style={dateStyle(loading)}
          />
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          End:
          <input
            type="date"
            value={rangeEnd}
            disabled={loading}
            onChange={(e) => setRangeEnd(e.target.value)}
            style={dateStyle(loading)}
          />
        </label>
      </div>

      {error && <div style={{ color: "crimson", marginBottom: 12 }}>Error: {error}</div>}

      {/* 2-column layout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `${chartColWidth}px 1fr`,
          gap: 24,
          alignItems: "start",
        }}
      >
        {/* LEFT: chart */}
        <div>
          <div
            style={{
              width: "100%",
              height: 420,
              background: "#111",
              borderRadius: 12,
              padding: 12,
              border: "1px solid #2a2a2a",
              boxSizing: "border-box",
            }}
          >
            {visibleData.length === 0 && !loading ? (
              <div style={{ color: "#fff", opacity: 0.8 }}>
                No data. Click “Confirm / Load” for a valid ticker.
              </div>
            ) : (
              <>
                {/* MAIN chart shows ONLY visibleData */}
                <div style={{ height: 330 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={visibleData}
                      onClick={(state) => {
                        if (state && state.activeLabel) {
                          const day = state.activeLabel;
                          setSelectedDay(day);
                          loadNews(activeTicker, day);
                        }
                      }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fontSize: 12 }} minTickGap={40} />
                      <YAxis domain={["auto", "auto"]} />
                      <Tooltip content={<CustomTooltip />} />
                      <Line type="monotone" dataKey="close" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* MINI chart provides Brush over FULL data */}
                <div style={{ height: 70, marginTop: 10 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data}>
                      <XAxis dataKey="date" hide />
                      <YAxis hide domain={["auto", "auto"]} />
                      <Line type="monotone" dataKey="close" dot={false} isAnimationActive={false} />
                      <Brush
                        dataKey="date"
                        height={26}
                        travellerWidth={12}
                        startIndex={brushStart}
                        endIndex={brushEnd}
                        onChange={(r) => {
                          if (!r) return;
                          if (typeof r.startIndex === "number") setBrushStart(r.startIndex);
                          if (typeof r.endIndex === "number") setBrushEnd(r.endIndex);
                        }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
          </div>

          <div style={{ marginTop: 10, opacity: 0.8, fontSize: 12 }}>
            Tip: click any date on the chart to load headlines.
          </div>
        </div>

        {/* RIGHT: news (independent scroll so chart stays visible) */}
        <div
          style={{
            position: "sticky",
            top: 16,
            alignSelf: "start",
            maxHeight: "calc(100vh - 32px)",
            overflow: "hidden",
            borderRadius: 12,
          }}
        >
          <div style={{ paddingRight: 6 }}>
            <h2 style={{ marginTop: 0 }}>
              Headlines{selectedDay ? ` for ${activeTicker} on ${selectedDay}` : ""}
            </h2>

            {!selectedDay && (
              <div style={{ opacity: 0.8 }}>Click a day on the chart to load headlines.</div>
            )}

            {newsLoading && <div>Loading headlines...</div>}
            {newsError && <div style={{ color: "crimson" }}>Error: {newsError}</div>}

            {!newsLoading && selectedDay && !newsError && headlines.length === 0 && (
              <div>No headlines returned.</div>
            )}
          </div>

          <div
            style={{
              marginTop: 12,
              overflowY: "auto",
              maxHeight: "calc(100vh - 120px)", // header + padding allowance
              paddingRight: 10,
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {headlines.map((h, i) => (
                <div
                  key={i}
                  style={{
                    background: "#1a1a1a",
                    padding: 12,
                    borderRadius: 10,
                    border: "1px solid #2a2a2a",
                  }}
                >
                  <a
                    href={h.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      color: "white",
                      textDecoration: "none",
                      fontWeight: 600,
                      lineHeight: 1.3,
                      display: "block",
                    }}
                  >
                    {h.title}
                  </a>
                  <div style={{ fontSize: 12, opacity: 0.8, marginTop: 6 }}>
                    {h.source || "Unknown source"}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ height: 12 }} />
          </div>
        </div>
      </div>
    </div>
  );
}
