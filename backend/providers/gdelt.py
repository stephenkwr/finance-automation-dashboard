from __future__ import annotations

from datetime import date as dt_date, datetime
from typing import Optional

from google.cloud import bigquery


def _ticker_regex(ticker: str) -> Optional[str]:
    t = (ticker or "").upper().strip()
    if len(t) < 2:
        return None

    # Finance-specific patterns to avoid matching normal English words (e.g., "spy")
    # Matches:
    #   $SPY
    #   NYSEARCA:SPY / NYSEARCA: SPY / NASDAQ:SPY / NYSE:SPY (etc)
    #   SPY ETF / SPY stock / SPY shares
    #   (SPY) or SPY) common in finance headlines
    return (
        rf"(\${t}\b)"
        rf"|((NYSEARCA|NASDAQ|NYSE|AMEX)\s*:\s*{t}\b)"
        rf"|(\b{t}\b\s*(ETF|STOCK|SHARES|FUND|INDEX)\b)"
        rf"|(\(\s*{t}\s*\))"
        rf"|(\b{t}\b\s*\))"
        rf"|(\b{t}\b\s*[:\-]\s*)"
    )


def get_headlines_for_day_bigquery(
    *,
    day: dt_date | str,
    ticker: str,
    company_name: Optional[str] = None,
    limit: int = 50,
    project_id: Optional[str] = None,  # None => ADC default project
) -> list[dict]:
    # normalize day
    if isinstance(day, dt_date):
        day_str = day.isoformat()
    else:
        day_str = str(day).strip().split("T", 1)[0]

    ticker = (ticker or "").upper().strip()
    name_up = (company_name or "").strip().upper() or None
    ticker_pat = _ticker_regex(ticker)

    client = bigquery.Client(project=project_id)

    sql = """
    SELECT
      ANY_VALUE(title) AS title,
      url AS url,
      ANY_VALUE(domain) AS domain,
      MAX(date) AS published_at
    FROM `gdelt-bq.gdeltv2.gal`
    WHERE DATE(date) = @day
      AND (
        (@ticker_pat IS NOT NULL AND REGEXP_CONTAINS(UPPER(title), @ticker_pat))
        OR (@name_up IS NOT NULL AND STRPOS(UPPER(title), @name_up) > 0)
      )
    GROUP BY url
    ORDER BY published_at DESC
    LIMIT @limit
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("day", "DATE", day_str),
            bigquery.ScalarQueryParameter("ticker_pat", "STRING", ticker_pat),
            bigquery.ScalarQueryParameter("name_up", "STRING", name_up),
            bigquery.ScalarQueryParameter("limit", "INT64", int(limit)),
        ]
    )

    rows = client.query_and_wait(sql, job_config=job_config)

    out: list[dict] = []
    for r in rows:
        # r["published_at"] is a datetime (UTC) from BigQuery
        pub = r["published_at"]
        if not isinstance(pub, datetime):
            # be defensive, but usually it is datetime
            try:
                pub = datetime.fromisoformat(str(pub))
            except Exception:
                pub = None

        out.append(
            {
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "domain": r.get("domain") or "",
                "published_at": pub,
            }
        )

    return out
