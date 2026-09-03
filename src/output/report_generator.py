"""
src/output/report_generator.py
Generates a Persian trader-style HTML analysis report.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

__all__ = ["ReportGenerator", "generate_report"]

logger = get_logger(__name__)

# Persian strings as constants (no Persian in code logic)
T_TITLE        = "SmartTraderBot \u2014 \u06af\u0632\u0627\u0631\u0634 \u062a\u062d\u0644\u06cc\u0644"
T_GENERATED    = "\u062a\u0627\u0631\u06cc\u062e \u062a\u0648\u0644\u06cc\u062f:"
T_SUBTITLE     = "\u062a\u062d\u0644\u06cc\u0644 \u0645\u0641\u0627\u0647\u06cc\u0645 \u067e\u0648\u0644 \u0647\u0648\u0634\u0645\u0646\u062f (SMC/ICT)"
T_SCAN_TIME    = "\u0632\u0645\u0627\u0646 \u0627\u0633\u06a9\u0646:"
T_PRICE        = "\u0642\u06cc\u0645\u062a \u0641\u0639\u0644\u06cc:"
T_BIAS         = "\u062c\u0647\u062a \u0628\u0627\u0632\u0627\u0631:"
T_TOTAL_POIS   = "\u062a\u0639\u062f\u0627\u062f \u0646\u0642\u0627\u0637 \u0645\u0647\u0645:"
T_AVG_SCORE    = "\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0627\u0645\u062a\u06cc\u0627\u0632:"
T_TOP_SCORE    = "\u0628\u0627\u0644\u0627\u062a\u0631\u06cc\u0646 \u0627\u0645\u062a\u06cc\u0627\u0632:"
T_ANALYSIS     = "\u062a\u062d\u0644\u06cc\u0644 \u062a\u0631\u06cc\u062f\u0631"
T_TOP_SETUPS   = "\u0628\u0647\u062a\u0631\u06cc\u0646 \u0633\u06cc\u06af\u0646\u0627\u0644\u200c\u0647\u0627"
T_ALL_ZONES    = "\u062a\u0645\u0627\u0645 \u0632\u0648\u0646\u200c\u0647\u0627\u06cc \u0627\u0645\u062a\u06cc\u0627\u0632\u062f\u0647\u06cc \u0634\u062f\u0647"
T_BULL         = "\u0635\u0639\u0648\u062f\u06cc"
T_BEAR         = "\u0646\u0632\u0648\u0644\u06cc"
T_NEUT         = "\u062e\u0646\u062b\u06cc"
T_ZONE         = "\u0632\u0648\u0646:"
T_MID          = "\u0645\u06cc\u0627\u0646\u0647:"
T_SCORE        = "\u0627\u0645\u062a\u06cc\u0627\u0632:"
T_TRADER_NOTE  = "\u062a\u062d\u0644\u06cc\u0644 \u062a\u0631\u06cc\u062f\u0631:"
T_DETECTED_AT  = "\u0632\u0645\u0627\u0646 \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u0632\u0648\u0646:"
T_NO_RESULT    = "\u0647\u06cc\u0686 \u0646\u062a\u06cc\u062c\u0647\u200c\u0627\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
T_NO_ZONES     = "\u0647\u06cc\u0686 \u0632\u0648\u0646 \u0645\u0647\u0645\u06cc \u062f\u0631 \u0627\u06cc\u0646 \u0627\u0633\u06a9\u0646 \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u0646\u0634\u062f."
T_ENTRIES      = "\u0628\u0647\u062a\u0631\u06cc\u0646 \u0646\u0642\u0627\u0637 \u0648\u0631\u0648\u062f"
T_NO_ENTRIES   = "\u0646\u0642\u0637\u0647 \u0648\u0631\u0648\u062f \u0647\u0645\u200c\u062c\u0647\u062a \u0628\u0627 \u0631\u0648\u0646\u062f \u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
T_ENTRY_PRICE  = "\u0646\u0642\u0637\u0647 \u0648\u0631\u0648\u062f:"
T_SL           = "\u062d\u062f \u0636\u0631\u0631:"
T_TP1          = "\u0647\u062f\u0641 \u06f1:"
T_TP2          = "\u0647\u062f\u0641 \u06f2:"
T_STATUS       = "\u0648\u0636\u0639\u06cc\u062a:"
T_FOOTER       = "SmartTraderBot | \u0641\u0627\u0632 \u06f1 | \u0627\u0633\u06a9\u0646\u0631 \u0628\u0627\u0632\u0627\u0631 SMC/ICT"

# Table headers
TH_TIME  = "\u0632\u0645\u0627\u0646"
TH_DIR   = "\u062c\u0647\u062a"
TH_ZONE  = "\u0632\u0648\u0646"
TH_SCORE = "\u0627\u0645\u062a\u06cc\u0627\u0632"
TH_GRADE = "\u0631\u062a\u0628\u0647"
TH_LABEL = "\u062a\u0648\u0636\u06cc\u062d"
TH_TRADE = "\u0645\u0639\u0627\u0645\u0644\u0647"

# Grade labels
GRADE_LABELS = {
    "A+": "\u0633\u06cc\u06af\u0646\u0627\u0644 A+",
    "A":  "\u0633\u06cc\u06af\u0646\u0627\u0644 \u0642\u0648\u06cc",
    "B":  "\u0633\u06cc\u06af\u0646\u0627\u0644 \u062e\u0648\u0628",
    "C":  "\u0633\u06cc\u06af\u0646\u0627\u0644 \u0636\u0639\u06cc\u0641",
    "D":  "\u0633\u06cc\u06af\u0646\u0627\u0644 \u0628\u062f",
}

# Factor names
F_OB    = "\u0627\u0631\u062f\u0631 \u0628\u0644\u0627\u06a9"
F_FVG   = "\u0634\u06a9\u0627\u0641 \u0627\u0631\u0632\u0634"
F_LIQ   = "\u0646\u0642\u062f\u06cc\u0646\u06af\u06cc"
F_BOS   = "\u0634\u06a9\u0633\u062a \u0633\u0627\u062e\u062a\u0627\u0631"
F_PD    = "P/D"
F_HTF   = "\u062a\u0627\u06cc\u0645\u200c\u0641\u0631\u06cc\u0645 \u0628\u0627\u0644\u0627\u062a\u0631"


class ReportGenerator:
    """Generates a Persian trader-style HTML analysis report."""

    def __init__(self, output_dir: str = "output_files") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, scan_result: Any, scoring_outputs: list[Any],
                 cluster_maps: list[Any] = None) -> str:
        try:
            html = self._build_html(scan_result, scoring_outputs, cluster_maps)
            path = self._output_dir / "analysis_report.html"
            path.write_text(html, encoding="utf-8")
            logger.info("Analysis report saved: %s", path)
            return str(path)
        except Exception as exc:
            logger.error("Failed to generate report: %s", exc)
            return ""

    def _build_html(self, scan_result: Any, scoring_outputs: list[Any],
                    cluster_maps: list[Any] = None) -> str:
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        if cluster_maps:
            sections = "\n".join(
                self._build_cluster_section(
                    cluster_map, index,
                    getattr(
                        getattr(scan_result, "timeframe_results", [])[index - 1]
                        if len(getattr(scan_result, "timeframe_results", []) or []) >= index
                        else None,
                        "snapshot",
                        None,
                    ),
                )
                for index, cluster_map in enumerate(cluster_maps, 1)
                if cluster_map is not None
                for _ in [0]
            )
        else:
            sections = "\n".join(self._build_section(o) for o in scoring_outputs)

        return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{T_TITLE}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background: #0d1117;
       color: #e6edf3; line-height: 1.8; direction: rtl; }}
.header {{ background: #161b22; padding: 24px 40px; border-bottom: 2px solid #30363d; }}
.header h1 {{ color: #58a6ff; font-size: 1.8rem; }}
.header p  {{ color: #8b949e; margin-top: 6px; }}
.content {{ max-width: 1000px; margin: 0 auto; padding: 30px 40px; }}
.section {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px;
            padding: 28px; margin-bottom: 28px; }}
.section h2 {{ color: #58a6ff; font-size: 1.3rem; margin-bottom: 16px;
               border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
.section h3 {{ color: #e6edf3; font-size: 1.05rem; margin: 20px 0 10px; }}
.bias-bull {{ color: #28a745; font-weight: bold; }}
.bias-bear {{ color: #dc3545; font-weight: bold; }}
.bias-neut {{ color: #8b949e; font-weight: bold; }}
.grade-aplus {{ background:#28a745;color:#fff;padding:2px 10px;border-radius:12px;font-weight:bold; }}
.grade-a     {{ background:#17a2b8;color:#fff;padding:2px 10px;border-radius:12px;font-weight:bold; }}
.grade-b     {{ background:#ffc107;color:#000;padding:2px 10px;border-radius:12px;font-weight:bold; }}
.grade-c     {{ background:#fd7e14;color:#fff;padding:2px 10px;border-radius:12px;font-weight:bold; }}
.grade-d     {{ background:#dc3545;color:#fff;padding:2px 10px;border-radius:12px;font-weight:bold; }}
.setup-card {{ background:#0d1117;border:1px solid #30363d;border-radius:8px;
               padding:20px;margin-bottom:16px; }}
.setup-card.bull {{ border-right:4px solid #28a745; }}
.setup-card.bear {{ border-right:4px solid #dc3545; }}
.setup-title {{ font-size:1.1rem;font-weight:bold;margin-bottom:12px; }}
.analysis-text {{ color:#c9d1d9;line-height:1.9; }}
.analysis-text p {{ margin-bottom:10px; }}
.timestamp {{ color:#58a6ff;font-weight:bold; }}
.price {{ color:#f0b27a;font-weight:bold;font-family:monospace; }}
.factor-row {{ display:flex;gap:8px;flex-wrap:wrap;margin:10px 0; }}
.factor {{ padding:3px 10px;border-radius:12px;font-size:0.82rem; }}
.factor.yes {{ background:#1a3a1a;color:#28a745;border:1px solid #28a745; }}
.factor.no  {{ background:#2a1a1a;color:#6c757d;border:1px solid #444; }}
.summary-box {{ background:#1c2128;border:1px solid #388bfd;border-radius:8px;
                padding:16px;margin-bottom:20px; }}
.summary-box p {{ color:#c9d1d9;margin-bottom:6px; }}
table {{ width:100%;border-collapse:collapse;margin-top:12px;font-size:0.88rem; }}
th {{ background:#21262d;color:#8b949e;padding:10px 12px;text-align:right; }}
td {{ padding:10px 12px;border-bottom:1px solid #21262d;color:#c9d1d9; }}
tr:hover td {{ background:#1c2128; }}
.footer {{ text-align:center;padding:20px;color:#8b949e;font-size:0.8rem;
           border-top:1px solid #30363d;margin-top:30px; }}
ul {{ margin: 8px 0 8px 0; padding-right: 20px; color: #c9d1d9; }}
li {{ margin-bottom: 6px; }}
</style>
</head>
<body>
<div class="header">
  <h1>📊 {T_TITLE}</h1>
  <p>{T_GENERATED} {now_str} &nbsp;|&nbsp; {T_SUBTITLE}</p>
</div>
<div class="content">
{sections}
</div>
<div class="footer">{T_FOOTER}</div>
</body>
</html>"""

    @staticmethod
    def _time_text(value: Any) -> str:
        return value.strftime("%H:%M") if hasattr(value, "strftime") else "--:--"

    def _build_cluster_section(self, cluster_map: Any, section_number: int,
                               snapshot: Any = None) -> str:
        """Render the top three bias-aligned OB+FVG clusters."""
        clusters = (getattr(cluster_map, "clusters", []) or [])[:3]
        bias = str(getattr(cluster_map, "market_bias", "neutral"))
        direction_fa = T_BULL if bias == "bullish" else T_BEAR
        events = []
        structure = getattr(snapshot, "market_structure", None)
        events = getattr(structure, "events", []) or []
        aligned_events = [
            event for event in events
            if str(getattr(event, "direction", "")) == bias
            and str(getattr(event, "event_type", "")) in ("BOS", "CHoCH")
        ]
        event = aligned_events[-1] if aligned_events else None
        event_type = str(getattr(event, "event_type", "BOS"))
        event_time = self._time_text(getattr(event, "event_time", None))
        signal_parts = []
        for rank, cluster in enumerate(clusters, 1):
            factors = getattr(cluster, "factors", []) or []
            ob = next((f for f in factors if f.factor_type == "order_block"), None)
            fvg = next((f for f in factors if f.factor_type == "fvg"), None)
            has_sweep = bool(getattr(cluster, "has_liquidity_sweep", False))
            has_bos = bool(getattr(cluster, "has_bos", False))
            broken = bool(getattr(ob, "is_broken_retested", False)) if ob else False
            direction = str(getattr(cluster, "direction", bias))
            direction_fa = T_BULL if direction == "bullish" else T_BEAR
            status = "broken & retested" if broken else "fresh"
            ob_time = self._time_text(getattr(cluster, "ob_formation_time", None))
            fvg_time = self._time_text(getattr(cluster, "fvg_formation_time", None))
            entry_time = self._time_text(getattr(cluster, "entry_time_suggestion", None))
            score = float(getattr(cluster, "confluence_score", 0.0))
            grade = str(getattr(cluster, "grade", "D"))
            zbottom = float(getattr(cluster, "zone_bottom", 0.0))
            ztop = float(getattr(cluster, "zone_top", 0.0))
            midpoint = float(getattr(cluster, "zone_midpoint", 0.0))
            entry_ob = getattr(cluster, "entry_point_ob", None)
            entry_fvg = getattr(cluster, "entry_point_fvg", None)
            stop_loss = getattr(cluster, "stop_loss", None)
            risk_pips = abs(float(stop_loss) - float(entry_ob)) / 0.01 if stop_loss is not None and entry_ob is not None else 0.0
            signal_parts.append(f"""
<div class="section setup-card {'bull' if direction == 'bullish' else 'bear'}">
  <h2>سیگنال #{rank} | {direction_fa} | امتیاز: {score:.1f}/100 | رتبه: {grade}</h2>
  <h3>۱. جهت حرکت بازار</h3>
  <p>بازار <strong>{direction_fa}</strong> است. دلیل: {len(aligned_events)} رویداد BOS/CHoCH در جهت {direction_fa} شناسایی شد.<br>آخرین رویداد: {event_type} در ساعت {event_time} تأیید شد.</p>
  <h3>۲. زمان و نقطه ورود</h3>
  <p>اردر بلاک در ساعت <span class="timestamp">{ob_time}</span> تشکیل شد.<br>شکاف ارزش (FVG) در ساعت <span class="timestamp">{fvg_time}</span> تشکیل شد.<br>پیشنهاد ورود: ساعت <span class="timestamp">{entry_time}</span><br>نقطه ورود ۱ (کف OB): <span class="price">{float(entry_ob):.2f}</span><br>نقطه ورود ۲ (کف FVG): <span class="price">{float(entry_fvg):.2f}</span></p>
  <h3>۳. مختصات معامله</h3>
  <p>زون کامل: <span class="price">{zbottom:.2f}</span> — <span class="price">{ztop:.2f}</span><br>میانه زون: <span class="price">{midpoint:.2f}</span><br>حد ضرر: <span class="price">{float(stop_loss):.2f}</span> (بافر ۲ پیپ)<br>ناحیه P/D: {getattr(cluster, 'premium_discount_zone', 'unknown')}</p>
  <div class="factor-row"><span class="factor yes">اردر بلاک: ✅ ({status})</span><span class="factor yes">شکاف ارزش: ✅</span><span class="factor {'yes' if has_sweep else 'no'}">نقدینگی‌برداری: {'✅' if has_sweep else '❌'}</span><span class="factor {'yes' if has_bos else 'no'}">شکست ساختار: {'✅' if has_bos else '❌'}</span></div>
  <h3>استدلال کامل</h3>
  <p class="analysis-text">در ساعت {ob_time} آخرین کندل مخالف پیش از displacement به عنوان اردر بلاک انتخاب شد و این زون بین {zbottom:.2f} و {ztop:.2f} قرار دارد. این اردر بلاک وضعیت {status} دارد. در ساعت {fvg_time} شکاف ارزش منصفانه بین {float(getattr(fvg, 'zone_bottom', 0.0)):.2f} و {float(getattr(fvg, 'zone_top', 0.0)):.2f} تشکیل شد و با OB همپوشانی دارد. پیشنهاد ورود در ساعت {entry_time} است و فاصله ورود تا حد ضرر حدود {risk_pips:.1f} پیپ ریسک دارد.</p>
</div>""")
        return "".join(signal_parts) if signal_parts else f"<div class=\"section\"><p>{T_NO_ZONES}</p></div>"

    def _build_section(self, output: Any) -> str:
        symbol    = str(getattr(output, "symbol", ""))
        timeframe = str(getattr(output, "timeframe", ""))
        summary   = getattr(output, "summary", None)
        results   = getattr(output, "all_results", []) or []
        dash_res  = getattr(output, "dashboard_results", []) or []

        bias       = self._get_bias(results, output)
        bias_fa    = T_BULL if bias == "bullish" else T_BEAR if bias == "bearish" else T_NEUT
        bias_icon  = "🟢" if bias == "bullish" else "🔴" if bias == "bearish" else "⚪"
        bias_class = "bull" if bias == "bullish" else "bear" if bias == "bearish" else "neut"

        avg_score     = float(getattr(summary, "avg_score", 0)) if summary else 0
        top_score     = float(getattr(summary, "top_score", 0)) if summary else 0
        total_pois    = int(getattr(summary, "total_pois_found", 0)) if summary else 0
        scan_time     = getattr(summary, "scanned_at", datetime.utcnow()) if summary else datetime.utcnow()
        scan_str      = scan_time.strftime("%Y-%m-%d %H:%M:%S UTC") if hasattr(scan_time, "strftime") else str(scan_time)
        current_price = float(getattr(summary, "current_price", 0)) if summary else 0

        summary_html = f"""
<div class="summary-box">
  <p>📅 <strong>{T_SCAN_TIME}</strong> <span class="timestamp">{scan_str}</span></p>
  <p>💰 <strong>{T_PRICE}</strong> <span class="price">{current_price:.2f}</span></p>
  <p>📈 <strong>{T_BIAS}</strong> <span class="bias-{bias_class}">{bias_icon} {bias_fa}</span></p>
  <p>🎯 <strong>{T_TOTAL_POIS}</strong> {total_pois} &nbsp;|&nbsp;
     <strong>{T_AVG_SCORE}</strong> {avg_score:.1f}/100 &nbsp;|&nbsp;
     <strong>{T_TOP_SCORE}</strong> {top_score:.1f}/100</p>
</div>"""

        overview   = self._build_overview(bias, bias_fa, current_price, results, scan_str)
        entries_html = self._build_entries(output)
        setup_cards = "".join(self._build_setup_card(r, i) for i, r in enumerate(dash_res[:8], 1))
        table       = self._build_table(results)

        return f"""
<div class="section">
  <h2>📍 {symbol} {timeframe} — {T_ANALYSIS}</h2>
  {summary_html}
  <h3>🧠 {T_ANALYSIS}</h3>
  <div class="analysis-text">{overview}</div>
  <h3>🎯 {T_ENTRIES}</h3>
  {entries_html}
  <h3>🏆 {T_TOP_SETUPS}</h3>
  {setup_cards}
  <h3>📋 {T_ALL_ZONES}</h3>
  {table}
</div>"""

    def _get_bias(self, results: list, output: Any = None) -> str:
        entry_map = getattr(output, "entry_map", None) if output is not None else None
        if entry_map is not None:
            mapped = str(getattr(entry_map, "market_bias", "") or "")
            if mapped in ("bullish", "bearish", "neutral"):
                return mapped
        bull = sum(1 for r in results if getattr(r, "direction", "") == "bullish")
        bear = sum(1 for r in results if getattr(r, "direction", "") == "bearish")
        if bull > bear: return "bullish"
        if bear > bull: return "bearish"
        return "neutral"

    def _build_entries(self, output: Any) -> str:
        entry_map = getattr(output, "entry_map", None)
        entries = getattr(entry_map, "entries", None) or []
        if not entries:
            return f"<p style='color:#8b949e'>{T_NO_ENTRIES}</p>"

        cards = []
        for e in entries:
            direction = str(getattr(e, "direction", ""))
            dir_fa = T_BULL if direction == "bullish" else T_BEAR
            dir_icon = "🟢" if direction == "bullish" else "🔴"
            card_class = "bull" if direction == "bullish" else "bear"
            status = str(getattr(e, "status", ""))
            status_fa = {
                "in_zone": "داخل زون — آماده ورود",
                "awaiting_pullback": "منتظر پولبک به زون",
                "invalidated": "باطل‌شده",
            }.get(status, status)
            grade = str(getattr(e, "grade", "D"))
            grade_class = "grade-" + grade.lower().replace("+", "plus")
            cards.append(f"""
<div class="setup-card {card_class}">
  <div class="setup-title">
    #{int(getattr(e, 'rank', 0))} &nbsp; {dir_icon} {dir_fa} &nbsp;
    <span class="{grade_class}">{grade}</span>
  </div>
  <div class="analysis-text">
    <p>🎯 <strong>{T_ENTRY_PRICE}</strong>
       <span class="price">{float(getattr(e, 'entry_price', 0)):.2f}</span>
       &nbsp;|&nbsp; {T_ZONE}
       <span class="price">{float(getattr(e, 'entry_zone_bottom', 0)):.2f}</span> —
       <span class="price">{float(getattr(e, 'entry_zone_top', 0)):.2f}</span></p>
    <p>🛡️ <strong>{T_SL}</strong>
       <span class="price">{float(getattr(e, 'stop_loss', 0)):.2f}</span>
       &nbsp;|&nbsp; {T_TP1}
       <span class="price">{float(getattr(e, 'take_profit_1', 0)):.2f}</span>
       &nbsp;|&nbsp; {T_TP2}
       <span class="price">{float(getattr(e, 'take_profit_2', 0)):.2f}</span>
       &nbsp;|&nbsp; R:R {float(getattr(e, 'risk_reward_1', 0)):.1f} / {float(getattr(e, 'risk_reward_2', 0)):.1f}</p>
    <p>📌 <strong>{T_STATUS}</strong> {status_fa}
       &nbsp;|&nbsp; {T_SCORE} <strong>{float(getattr(e, 'score', 0)):.0f}/100</strong></p>
    <p>{str(getattr(e, 'reason', ''))}</p>
  </div>
</div>""")
        return "".join(cards)

    def _build_overview(self, bias: str, bias_fa: str, price: float,
                         results: list, scan_str: str) -> str:
        if not results:
            return f"<p>{T_NO_ZONES}</p>"

        tradeable = [r for r in results if getattr(r, "is_tradeable", False)]
        aplus     = [r for r in results if getattr(r, "grade", "") == "A+"]
        bull_res  = [r for r in results if getattr(r, "direction", "") == "bullish"]
        bear_res  = [r for r in results if getattr(r, "direction", "") == "bearish"]

        if bias == "bullish":
            bias_desc = f"بازار <strong>{bias_fa}</strong> است. انتظار می‌رود قیمت در زون‌های تقاضا حمایت شود و به سمت بالا حرکت کند."
        elif bias == "bearish":
            bias_desc = f"بازار <strong>{bias_fa}</strong> است. انتظار می‌رود قیمت در زون‌های عرضه مقاومت کند و به سمت پایین حرکت کند."
        else:
            bias_desc = f"بازار <strong>{bias_fa}</strong> است. هیچ جهت مشخصی شناسایی نشده است."

        aplus_text = (
            f"<strong>{len(aplus)} سیگنال A+</strong> با امتیاز بالای ۸۰ شناسایی شد."
            if aplus else "هیچ سیگنال A+ در این اسکن یافت نشد."
        )

        html = f"""
<p>در تاریخ <span class="timestamp">{scan_str}</span>، اسکنر XAUUSD M1 را با قیمت فعلی
<span class="price">{price:.2f}</span> تحلیل کرد. {bias_desc}</p>

<p>اسکن <strong>{len(results)} نقطه مهم (POI)</strong> شناسایی کرد —
{len(bull_res)} صعودی و {len(bear_res)} نزولی.
از این تعداد، <strong>{len(tradeable)} زون امتیاز بالای ۶۰ دارند</strong> و به عنوان سیگنال معتبر شناخته می‌شوند.
{aplus_text}</p>"""

        if tradeable:
            top = max(tradeable, key=lambda r: getattr(r, "total_score", 0))
            top_dir   = getattr(top, "direction", "")
            top_dir_fa = T_BULL if top_dir == "bullish" else T_BEAR
            top_zt    = float(getattr(top, "zone_top", 0))
            top_zb    = float(getattr(top, "zone_bottom", 0))
            top_score = float(getattr(top, "total_score", 0))
            top_grade = getattr(top, "grade", "")
            top_note  = (
                "این زون زیر قیمت فعلی قرار دارد. منتظر پولبک به این ناحیه تقاضا باشید."
                if top_dir == "bullish"
                else "این زون بالای قیمت فعلی قرار دارد. منتظر رالی به این ناحیه عرضه باشید."
            )
            html += f"""
<p>بهترین سیگنال یک زون <strong>{top_dir_fa}</strong> است بین
<span class="price">{top_zb:.2f}</span> و <span class="price">{top_zt:.2f}</span>
با امتیاز تلاقی <strong>{top_score:.0f}/100 (رتبه {top_grade})</strong>.
{top_note}</p>"""

        return html

    def _build_setup_card(self, result: Any, rank: int) -> str:
        direction = str(getattr(result, "direction", ""))
        dir_fa    = T_BULL if direction == "bullish" else T_BEAR
        zone_top  = float(getattr(result, "zone_top", 0))
        zone_bot  = float(getattr(result, "zone_bottom", 0))
        score     = float(getattr(result, "total_score", 0))
        grade     = str(getattr(result, "grade", "D"))
        pd_zone   = str(getattr(result, "premium_discount_zone", "unknown"))
        scored_at = getattr(result, "scored_at", datetime.utcnow())
        has_ob    = bool(getattr(result, "has_order_block", False))
        has_fvg   = bool(getattr(result, "has_fvg", False))
        has_sweep = bool(getattr(result, "has_liquidity_sweep", False))
        has_bos   = bool(getattr(result, "has_bos", False))
        htf       = bool(getattr(result, "htf_aligned", False))
        ob_sc     = float(getattr(result, "order_block_score", 0))
        fvg_sc    = float(getattr(result, "fvg_score", 0))
        liq_sc    = float(getattr(result, "liquidity_sweep_score", 0))
        bos_sc    = float(getattr(result, "bos_score", 0))
        pd_sc     = float(getattr(result, "premium_discount_score", 0))

        time_str  = scored_at.strftime("%Y-%m-%d %H:%M UTC") if hasattr(scored_at, "strftime") else str(scored_at)
        dir_icon  = "🟢" if direction == "bullish" else "🔴"
        card_class = "bull" if direction == "bullish" else "bear"
        grade_class = "grade-" + grade.lower().replace("+", "plus")
        grade_label = GRADE_LABELS.get(grade, grade)
        midpoint  = (zone_top + zone_bot) / 2.0

        factors_html = f"""
<div class="factor-row">
  <span class="factor {'yes' if has_ob else 'no'}">{F_OB} {'✅' if has_ob else '❌'} {ob_sc:.0f}pt</span>
  <span class="factor {'yes' if has_fvg else 'no'}">{F_FVG} {'✅' if has_fvg else '❌'} {fvg_sc:.0f}pt</span>
  <span class="factor {'yes' if has_sweep else 'no'}">{F_LIQ} {'✅' if has_sweep else '❌'} {liq_sc:.0f}pt</span>
  <span class="factor {'yes' if has_bos else 'no'}">{F_BOS} {'✅' if has_bos else '❌'} {bos_sc:.0f}pt</span>
  <span class="factor {'yes' if pd_sc > 0 else 'no'}">{F_PD} {'✅' if pd_sc > 0 else '❌'} {pd_sc:.0f}pt</span>
  <span class="factor {'yes' if htf else 'no'}">{F_HTF} {'✅' if htf else '❌'}</span>
</div>"""

        explanation = self._explain_setup(
            direction, dir_fa, zone_top, zone_bot, midpoint,
            has_ob, has_fvg, has_sweep, has_bos, pd_zone, pd_sc,
            score, grade, time_str
        )

        return f"""
<div class="setup-card {card_class}">
  <div class="setup-title">
    #{rank} &nbsp; {dir_icon} {dir_fa} &nbsp;
    <span class="{grade_class}">{grade}</span> &nbsp;
    <span style="color:#8b949e;font-weight:normal;font-size:0.9rem">{grade_label}</span>
  </div>
  <div class="analysis-text">
    <p>📅 <span class="timestamp">{time_str}</span></p>
    <p>📊 {T_ZONE} <span class="price">{zone_bot:.2f}</span> — <span class="price">{zone_top:.2f}</span>
       &nbsp;|&nbsp; {T_MID} <span class="price">{midpoint:.2f}</span>
       &nbsp;|&nbsp; {T_SCORE} <strong>{score:.0f}/100</strong>
       &nbsp;|&nbsp; P/D: {pd_zone}</p>
    {factors_html}
    <p style="margin-top:12px;color:#8b949e;font-size:0.9rem"><em>{T_TRADER_NOTE}</em></p>
    {explanation}
  </div>
</div>"""

    def _explain_setup(self, direction: str, dir_fa: str,
                        zt: float, zb: float, mid: float,
                        has_ob: bool, has_fvg: bool, has_sweep: bool, has_bos: bool,
                        pd_zone: str, pd_sc: float,
                        score: float, grade: str, time_str: str) -> str:
        parts = []

        zone_type = "تقاضا" if direction == "bullish" else "عرضه"
        expect    = "فشار خرید و یک حرکت صعودی احتمالی" if direction == "bullish" else "فشار فروش و یک حرکت نزولی احتمالی"

        parts.append(
            f"<p>یک زون <strong>{dir_fa} ({zone_type})</strong> بین "
            f"<span class='price'>{zb:.2f}</span> و <span class='price'>{zt:.2f}</span> "
            f"شناسایی شد (میانه: <span class='price'>{mid:.2f}</span>). "
            f"زمانی که قیمت به این ناحیه برگردد، انتظار {expect} داریم.</p>"
        )

        confluence = []
        if has_ob:
            last_candle = "نزولی" if direction == "bullish" else "صعودی"
            confluence.append(
                f"<strong>اردر بلاک (Order Block)</strong> — آخرین کندل {last_candle} قبل از یک displacement قوی. "
                f"این نشان‌دهنده جریان سفارش نهادی در این ناحیه است."
            )
        if has_fvg:
            confluence.append(
                f"<strong>شکاف ارزش منصفانه (FVG)</strong> — یک عدم تعادل که توسط یک حرکت سریع ایجاد شده. "
                f"قیمت تمایل دارد به این ناحیه برگردد و آن را پر کند."
            )
        if has_sweep:
            confluence.append(
                f"<strong>نقدینگی‌برداری (Liquidity Sweep)</strong> — استاپ‌لاس‌های معامله‌گران قبل از شکل‌گیری این زون "
                f"فعال شدند. این تأییدی است بر حضور پول هوشمند در این ناحیه."
            )
        if has_bos:
            confluence.append(
                f"<strong>شکست ساختار (BOS)</strong> — ساختار بازار از جهت {dir_fa} حمایت می‌کند."
            )
        if pd_sc > 0:
            pd_text = "تخفیف (Discount)" if direction == "bullish" else "پریمیوم (Premium)"
            confluence.append(
                f"<strong>ناحیه {pd_text}</strong> — این زون در بهترین موقعیت قیمتی برای ورود "
                f"بر اساس روش ICT قرار دارد."
            )

        if confluence:
            items = "".join(f"<li>{c}</li>" for c in confluence)
            parts.append(
                f"<p>این زون دارای <strong>{len(confluence)} عامل تلاقی</strong> است:</p>"
                f"<ul>{items}</ul>"
            )

        if score >= 80:
            verdict = "🌟 <strong>سیگنال عالی</strong> — احتمال بالا. تمام عوامل اصلی SMC هم‌راستا هستند."
        elif score >= 65:
            verdict = "✅ <strong>سیگنال قوی</strong> — چندین عامل این زون را تأیید می‌کنند. ارزش پایش دقیق دارد."
        elif score >= 50:
            verdict = "👍 <strong>سیگنال خوب</strong> — تلاقی مناسب. قبل از ورود منتظر تأیید بیشتر باشید."
        else:
            verdict = "⚠️ <strong>سیگنال ضعیف</strong> — تلاقی محدود. احتیاط کنید."

        parts.append(f"<p>{verdict}</p>")
        parts.append(f"<p style='color:#8b949e;font-size:0.85rem'>{T_DETECTED_AT} {time_str}</p>")

        return "\n".join(parts)

    def _build_table(self, results: list) -> str:
        if not results:
            return f"<p style='color:#8b949e'>{T_NO_RESULT}</p>"

        rows = ""
        for r in results:
            direction = str(getattr(r, "direction", ""))
            dir_fa    = T_BULL if direction == "bullish" else T_BEAR
            zt        = float(getattr(r, "zone_top", 0))
            zb        = float(getattr(r, "zone_bottom", 0))
            sc        = float(getattr(r, "total_score", 0))
            gr        = str(getattr(r, "grade", "D"))
            pd        = str(getattr(r, "premium_discount_zone", ""))
            tr        = bool(getattr(r, "is_tradeable", False))
            t         = getattr(r, "scored_at", datetime.utcnow())
            t_str     = t.strftime("%Y-%m-%d %H:%M") if hasattr(t, "strftime") else str(t)
            dir_icon  = "🟢" if direction == "bullish" else "🔴"
            gr_class  = "grade-" + gr.lower().replace("+", "plus")
            gr_label  = GRADE_LABELS.get(gr, gr)
            trade_icon = "✅" if tr else "❌"

            rows += f"""<tr>
<td>{t_str}</td>
<td>{dir_icon} {dir_fa}</td>
<td style="font-family:monospace">{zb:.2f} — {zt:.2f}</td>
<td><strong>{sc:.0f}</strong></td>
<td><span class="{gr_class}">{gr}</span></td>
<td style="color:#8b949e;font-size:0.82rem">{gr_label}</td>
<td style="color:#8b949e;font-size:0.82rem">{pd}</td>
<td>{trade_icon}</td>
</tr>"""

        return f"""<table>
<thead><tr>
<th>{TH_TIME}</th><th>{TH_DIR}</th><th>{TH_ZONE}</th>
<th>{TH_SCORE}</th><th>{TH_GRADE}</th><th>{TH_LABEL}</th>
<th>P/D</th><th>{TH_TRADE}</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>"""


def generate_report(scan_result: Any, scoring_outputs: list[Any],
                    output_dir: str = "output_files",
                    cluster_maps: list[Any] = None) -> str:
    return ReportGenerator(output_dir=output_dir).generate(
        scan_result, scoring_outputs, cluster_maps
    )
