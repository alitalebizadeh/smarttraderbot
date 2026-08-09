from __future__ import annotations

import html as html_module
from pathlib import Path
from typing import Any

from src.dashboard.tables import (
    build_no_data_message,
    build_results_table,
    build_summary_card,
    build_top_result_card,
)
from src.utils.logger import get_logger
from src.utils.time_utils import format_datetime, utcnow

__all__ = ["Dashboard"]

_logger = get_logger(__name__)

# ─────────────────────────────────────────────
#  Embedded CSS
# ─────────────────────────────────────────────

_CSS: str = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }
.page-header { background: #161b22; padding: 20px 30px; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; }
.page-header h1 { font-size: 1.5rem; color: #58a6ff; }
.last-updated { color: #8b949e; font-size: 0.85rem; }
.content { padding: 20px 30px; max-width: 1400px; margin: 0 auto; }
.page-footer { background: #161b22; padding: 12px 30px; border-top: 1px solid #30363d; text-align: center; color: #8b949e; font-size: 0.8rem; margin-top: 30px; }
.summary-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.summary-header { font-size: 1rem; font-weight: bold; color: #58a6ff; margin-bottom: 8px; }
.summary-stats { color: #8b949e; font-size: 0.85rem; margin-bottom: 8px; }
.grade-breakdown { display: flex; gap: 12px; flex-wrap: wrap; }
.grade-breakdown span { padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: bold; }
.grade-aplus { background: #28a745; color: #fff; }
.grade-a { background: #17a2b8; color: #fff; }
.grade-b { background: #ffc107; color: #000; }
.grade-c { background: #fd7e14; color: #fff; }
.grade-d { background: #dc3545; color: #fff; }
.table-container { margin-bottom: 30px; }
.table-container h3 { color: #58a6ff; margin-bottom: 12px; font-size: 1.1rem; }
.results-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.results-table th { background: #21262d; color: #8b949e; padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; font-weight: 600; }
.results-table td { padding: 8px 12px; border-bottom: 1px solid #21262d; vertical-align: middle; }
.results-table tr:hover { background: #1c2128; }
.grade-aplus td:first-child { border-left: 3px solid #28a745; }
.grade-a td:first-child { border-left: 3px solid #17a2b8; }
.grade-b td:first-child { border-left: 3px solid #ffc107; }
.grade-c td:first-child { border-left: 3px solid #fd7e14; }
.grade-d td:first-child { border-left: 3px solid #dc3545; }
.score-bar { font-family: monospace; color: #58a6ff; letter-spacing: -1px; }
.factors-cell code { font-size: 0.78rem; color: #8b949e; }
.zone-cell { font-family: monospace; font-size: 0.82rem; }
.no-results { color: #8b949e; font-style: italic; padding: 20px 0; }
.top-result-card { background: #161b22; border: 2px solid #30363d; border-radius: 10px; padding: 20px; margin-bottom: 20px; }
.top-result-header { font-size: 1.1rem; font-weight: bold; color: #58a6ff; margin-bottom: 12px; }
.top-result-body { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.top-result-body div { background: #0d1117; padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }
.no-data-message { background: #1c1c00; border: 1px solid #3d3000; border-radius: 6px; padding: 12px 16px; margin-bottom: 12px; color: #e6c84a; }
.warning-icon { margin-right: 8px; }"""

_DATETIME_FMT: str = "%Y-%m-%d %H:%M:%S"
_DEFAULT_TITLE: str = "SmartTraderBot — Market Scanner"
_DEFAULT_OUTPUT_DIR: str = "output_files"
_DEFAULT_FILENAME: str = "dashboard.html"
_DEFAULT_REFRESH: int = 60


# ─────────────────────────────────────────────
#  Dashboard
# ─────────────────────────────────────────────

class Dashboard:
    """Assembles and writes the complete HTML dashboard for SmartTraderBot.

    Takes a list of ScoringOutput objects (one per scanned symbol/timeframe),
    builds a self-contained HTML page with embedded CSS, and writes it to disk.

    The page auto-refreshes at a configurable interval so it stays current
    during a continuous scan cycle.

    Example:
        dashboard = Dashboard(output_dir="output_files", auto_refresh_seconds=60)
        path = dashboard.render_and_save(outputs=[scoring_output])
        print(f"Saved to: {path}")
    """

    def __init__(
        self,
        output_dir: str = _DEFAULT_OUTPUT_DIR,
        filename: str = _DEFAULT_FILENAME,
        auto_refresh_seconds: int = _DEFAULT_REFRESH,
    ) -> None:
        """Initialize the Dashboard instance.

        Creates the output directory if it does not already exist.

        Args:
            output_dir: Directory path where the HTML file will be written.
                Created automatically if absent. Defaults to "output_files".
            filename: Name of the output HTML file. Defaults to "dashboard.html".
            auto_refresh_seconds: Seconds between automatic browser page
                refreshes via ``<meta http-equiv="refresh">``. Set to 0 to
                disable auto-refresh. Defaults to 60.
        """
        self._output_dir = Path(output_dir)
        self._filename = filename
        self._auto_refresh_seconds = max(0, int(auto_refresh_seconds))

        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            _logger.warning(
                "Could not create output directory '%s': %s", self._output_dir, exc
            )

    # ── Public API ────────────────────────────────────────────────────────

    def render(
        self,
        outputs: list[Any],
        title: str = _DEFAULT_TITLE,
    ) -> str:
        """Build and return the complete HTML dashboard page as a string.

        Iterates over the provided ScoringOutput objects and assembles:
        - One summary card per output
        - One top-result card per output that has a top_result
        - One results table per output

        Args:
            outputs: List of ScoringOutput objects (one per symbol/timeframe).
                May be empty — renders a minimal page with no data messages.
            title: Browser tab title and page heading. Defaults to the
                SmartTraderBot project name.

        Returns:
            Complete, self-contained HTML string ready to write to a file.
            Returns "" on any unrecoverable error. Never raises.
        """
        try:
            now = utcnow()
            now_str = format_datetime(now, _DATETIME_FMT)
            safe_title = html_module.escape(title)

            # ── Meta refresh ───────────────────────────────────────────
            refresh_meta = ""
            if self._auto_refresh_seconds > 0:
                refresh_meta = (
                    f'  <meta http-equiv="refresh" content="{self._auto_refresh_seconds}">\n'
                )

            # ── Content sections ───────────────────────────────────────
            summary_cards_parts: list[str] = []
            top_results_parts:   list[str] = []
            tables_parts:        list[str] = []

            if not outputs:
                tables_parts.append(
                    build_no_data_message("—", "—", "No scan outputs available.")
                )
            else:
                for output in outputs:
                    try:
                        symbol    = str(getattr(output, "symbol", "?"))
                        timeframe = str(getattr(output, "timeframe", "?"))
                        summary   = getattr(output, "summary", None)
                        top       = getattr(output, "top_result", None)
                        dash_res  = getattr(output, "dashboard_results", []) or []

                        # Summary card
                        if summary is not None:
                            summary_cards_parts.append(build_summary_card(summary))
                        else:
                            summary_cards_parts.append(
                                build_no_data_message(
                                    symbol, timeframe, "Summary data unavailable."
                                )
                            )

                        # Top result card (only when a top result exists)
                        if top is not None:
                            top_results_parts.append(build_top_result_card(top))

                        # Results table
                        table_title = f"{symbol} {timeframe} — Setups"
                        tables_parts.append(
                            build_results_table(
                                results=dash_res,
                                title=table_title,
                                show_empty_message=True,
                            )
                        )

                    except Exception as exc:
                        _logger.warning(
                            "Error building dashboard section for output: %s", exc
                        )
                        tables_parts.append(
                            build_no_data_message(
                                "?", "?", f"Render error: {exc}"
                            )
                        )

            summary_cards_html = "\n".join(summary_cards_parts)
            top_results_html   = "\n".join(top_results_parts)
            tables_html        = "\n".join(tables_parts)
            output_count       = len(outputs)

            # ── Assemble full page ─────────────────────────────────────
            page = (
                "<!DOCTYPE html>\n"
                '<html lang="en">\n'
                "<head>\n"
                '  <meta charset="UTF-8">\n'
                '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
                f"{refresh_meta}"
                f"  <title>{safe_title}</title>\n"
                "  <style>\n"
                f"    {_CSS}\n"
                "  </style>\n"
                "</head>\n"
                "<body>\n"
                '  <div class="page-header">\n'
                f'    <h1>📈 {safe_title}</h1>\n'
                f'    <p class="last-updated">Last updated: {html_module.escape(now_str)}</p>\n'
                "  </div>\n"
                '  <div class="content">\n'
                f"{summary_cards_html}\n"
                f"{top_results_html}\n"
                f"{tables_html}\n"
                "  </div>\n"
                '  <div class="page-footer">\n'
                f"    <p>SmartTraderBot | Generated: {html_module.escape(now_str)}"
                f" | Outputs: {output_count}</p>\n"
                "  </div>\n"
                "</body>\n"
                "</html>"
            )

            _logger.info(
                "Dashboard rendered — %d output(s), %d bytes.",
                output_count,
                len(page),
            )
            return page

        except Exception as exc:
            _logger.error("Dashboard.render() failed: %s", exc)
            return ""

    def save(self, html_content: str) -> str:
        """Write the HTML string to the configured output file.

        Args:
            html_content: Complete HTML string produced by render().

        Returns:
            Absolute path to the saved file as a string.
            Returns "" on any error. Never raises.
        """
        try:
            if not html_content:
                _logger.warning("save() received empty HTML content — nothing written.")
                return ""

            file_path = self._output_dir / self._filename
            file_path.write_text(html_content, encoding="utf-8")

            abs_path = str(file_path.resolve())
            _logger.info("Dashboard saved to: %s (%d bytes)", abs_path, len(html_content))
            return abs_path

        except Exception as exc:
            _logger.error("Dashboard.save() failed: %s", exc)
            return ""

    def render_and_save(
        self,
        outputs: list[Any],
        title: str = _DEFAULT_TITLE,
    ) -> str:
        """Render the dashboard and save it to disk in one call.

        Convenience wrapper that calls render() then save() and returns
        the output file path.

        Args:
            outputs: List of ScoringOutput objects to render.
            title: Dashboard page title. Defaults to the project name.

        Returns:
            Absolute path to the saved HTML file, or "" on any error.
            Never raises.
        """
        try:
            html_content = self.render(outputs=outputs, title=title)
            if not html_content:
                _logger.warning("render_and_save(): render() returned empty content.")
                return ""
            return self.save(html_content)
        except Exception as exc:
            _logger.error("Dashboard.render_and_save() failed: %s", exc)
            return ""

    def __repr__(self) -> str:
        """Return a developer-friendly string representation.

        Returns:
            String showing the output path and refresh interval.
        """
        return (
            f"Dashboard("
            f"output={self._output_dir / self._filename}, "
            f"refresh={self._auto_refresh_seconds}s)"
        )