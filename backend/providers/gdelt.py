from __future__ import annotations

import json
import os
from datetime import date as dt_date, datetime
from typing import Optional, Any, Dict, List

from google.cloud import bigquery
from google.oauth2 import service_account


def _ticker_regex(ticker: str) -> Optional[str]:
    t = (ticker or "").upper().strip()
    if len(t) < 2:
        return None

    return (
        rf"(\${t}\b)"
        rf"|((NYSEARCA|NASDAQ|NYSE|AMEX)\s*:\s*{t}\b)"
        rf"|(\b{t}\b\s*(ETF|STOCK|SHARES|FUND|INDEX)\b)"
        rf"|(\(\s*{t}\s*\))"
        rf"|(\b{t}\b\s*\))"
        rf"|(\b{t}\b\s*[:\-]\s*)"
    )


_BQ_CLIENT: Optional[bigquery.Client] = None


def _get_bigquery_client(project_id: Optional[str] = None) -> bigquery.Client:
    """
    Render has no ADC. Use service account JSON from env:
      - GCP_SA_KEY_JSON: raw JSON string of service account key
    Falls back to ADC for local dev if env var isn't set.
    """
    global _BQ_CLIENT
    if _BQ_CLIENT is not None:
        return _BQ_CLIENT

    sa_json = os.getenv("GCP_SA_KEY_JSON", "").strip()

    if sa_json:
        try:
            info = json.loads(sa_json)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "GCP_SA_KEY_JSON is set but is not valid JSON. "
                "On Render, paste the full JSON key exactly (no quotes)."
            ) from e

        creds = service_account.Credentials.from_service_account_info(info)

        # Use explicit project_id if passed; else prefer env; else use the SA's project_id.
        effective_project = (
            project_id
            or os.getenv("GCP_PROJECT_ID")
            or info.get("project_id")
        )

        if not effective_project:
            raise RuntimeError(
                "Could not determine GCP project id. "
                "Set GCP_PROJECT_ID in Render env or ensure the service account JSON contains project_id."
            )

        _BQ_CLIENT = bigquery.Client(project=effective_project, credentials=creds)
        return _BQ_CLIENT

    # Local fallback: ADC
    _BQ_CLIENT = bigquery.Client(project=project_id)
    return _BQ_CLIENT


def get_headlines_for_day_bigquery(
    *,
    day: dt_date | str,
    ticker: str,
    company_name: Optional[str] = None,
    limit: int = 50,
    project_id: Optional[str] = None,  # if None => derived from SA JSON or ADC
) -> List[Dict[str, Any]]:
    # normalize day
    if isinstance(day, dt_date):
        day_str = day.isoformat()
    else:
        day_str = str(day).strip().split("T", 1)[0]

    ticker = (ticker or "").upper().strip()
    name_up = (company_name or "").strip().upper() or None
    ticker_pat = _ticker_regex(ticker)

    client = _get_bigquery_client(project_id=project_id)

    sql = """
    SELECT
      ANY_VALUE(title) AS title,
      url AS url,
      ANY_VALUE(domain) AS domain,
      MAX(date) AS published_at
    FROM gdelt-bq.gdeltv2.gal
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

    rows = client.query(sql, job_config=job_config).result()

    out: List[Dict[str, Any]] = []
    for r in rows:
        pub = r.get("published_at")

        if pub is not None and not isinstance(pub, datetime):
            try:
                pub = datetime.fromisoformat(str(pub))
            except Exception:
                pub = None

        out.append(
            {
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "domain": r.get("domain") or "","published_at": pub,
            }
        )

    return out