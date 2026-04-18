#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
OUTPUT_DIR = Path("generated")
CARD_WIDTH = 495
CARD_HEIGHT = 252

THEME = {
    "background": "#fffefe",
    "border": "none",
    "title": "#41b883",
    "text": "#273849",
    "muted": "#5f7383",
    "grid": "#dce6e0",
    "bar_bg": "#edf3ef",
}

FALLBACK_LANGUAGE_COLORS = [
    "#41b883",
    "#35495e",
    "#f1e05a",
    "#3178c6",
    "#b07219",
    "#dea584",
    "#438eff",
    "#00add8",
]

GITHUB_MARK_PATH = (
    "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59 "
    ".4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94"
    "-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82"
    ".72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 "
    "0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.65 "
    "7.65 0 0 1 8 4.84c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 "
    "1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 "
    "1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"
)


def github_graphql(query: str, variables: dict[str, Any], token: str | None) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "wasabeef-profile-stats-generator",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(GRAPHQL_ENDPOINT, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL request failed: {error.code} {detail}") from error
    except URLError as error:
        raise RuntimeError(f"GitHub GraphQL request failed: {error.reason}") from error

    if "errors" in data:
        messages = ", ".join(item.get("message", "Unknown error") for item in data["errors"])
        raise RuntimeError(f"GitHub GraphQL error: {messages}")

    return data["data"]


def format_number(value: int) -> str:
    return f"{value:,}"


def truncate_text(text: str | None, max_length: int) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def parse_iso_datetime(value: str | None) -> datetime:
    if not value:
        return datetime(1970, 1, 1, tzinfo=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_short_date(value: str | None) -> str:
    parsed = parse_iso_datetime(value)
    return parsed.strftime("%Y-%m-%d")


def month_label(month_key: str) -> str:
    month = datetime.strptime(month_key, "%Y-%m")
    return month.strftime("%b")


def render_github_mark(x: int, y: int, size: float, color: str) -> str:
    scale = size / 16
    return (
        f'<g transform="translate({x},{y}) scale({scale:.4f})">'
        f'<path d="{GITHUB_MARK_PATH}" fill="{color}" />'
        "</g>"
    )


def render_metric_icon(kind: str, x: int, y: int, color: str) -> str:
    if kind == "star":
        return (
            f'<polygon transform="translate({x},{y})" '
            f'points="7,0.5 8.9,5 13.5,5.3 10,8.2 11.2,12.9 7,10.4 2.8,12.9 4,8.2 0.5,5.3 5.1,5" '
            f'fill="{color}" />'
        )
    if kind == "followers":
        return f"""
        <g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="5" cy="4.5" r="2.3" />
          <path d="M1.8 12.4c0-2 1.4-3.5 3.2-3.5s3.2 1.5 3.2 3.5" />
          <circle cx="10.8" cy="5.2" r="1.6" />
          <path d="M9.4 11.9c.5-1.3 1.5-2.2 2.9-2.4" />
        </g>
        """
    if kind == "repo":
        return f"""
        <g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
          <rect x="1.5" y="1.5" width="11" height="11" rx="2" />
          <path d="M4 4.5h6M4 7h6M4 9.5h4" />
        </g>
        """
    if kind == "activity":
        return f"""
        <g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="1.5,10.5 4.5,7.5 6.8,8.8 10,4.8 12.5,6.3" />
          <path d="M1.5 12.5h11" stroke-width="1.2" />
        </g>
        """
    return ""


def render_language_icon(language_name: str, x: int, y: int, fallback_color: str) -> str:
    name = (language_name or "").lower()
    if name == "typescript":
        return f"""
        <g transform="translate({x},{y})">
          <rect width="16" height="16" rx="4" fill="#3178c6" />
          <text x="8" y="8.4" text-anchor="middle" dominant-baseline="middle" fill="#ffffff" style="font:700 6.4px 'Segoe UI', Ubuntu, Sans-Serif;">TS</text>
        </g>
        """
    if name == "java":
        return f"""
        <g transform="translate({x},{y})">
          <rect width="16" height="16" rx="4" fill="#fff4e8" />
          <g fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path d="M6 4c.8-.8 1.2-1.3 1-2M8.5 4.5c.8-.7 1.2-1.3 1.3-2.2" stroke="#f89820" stroke-width="1" />
            <path d="M4.2 7.2h5.4c1 0 1.7.7 1.7 1.7v1H5.7c-1 0-1.6-.6-1.6-1.5 0-.5 0-.7.1-1.2Z" stroke="#5382a1" stroke-width="1" />
            <path d="M5 11.5c1 .6 4 .6 5 0" stroke="#5382a1" stroke-width="1" />
          </g>
        </g>
        """
    if name == "dart":
        return f"""
        <g transform="translate({x},{y})">
          <rect width="16" height="16" rx="4" fill="#e8fbfb" />
          <path d="M3 2.5 8.5 1 13 5.5 8 15 3 10.5Z" fill="#00B4AB" />
          <path d="M8.5 1 13 5.5 8.6 7.2 6 4.7Z" fill="#00838f" />
          <path d="M6 4.7 8.6 7.2 8 15 3 10.5Z" fill="#26c6da" />
        </g>
        """
    if name == "kotlin":
        return f"""
        <g transform="translate({x},{y})">
          <rect width="16" height="16" rx="4" fill="#f5efff" />
          <path d="M2 2h12L8.2 7.8 14 14H9.2L5.8 10.2 2 14Z" fill="#A97BFF" />
          <path d="M2 2h6.2L2 8.1Z" fill="#7f52ff" />
          <path d="M14 2 8.2 7.8 14 14Z" fill="#ff7f52" />
        </g>
        """
    if name == "lua":
        return f"""
        <g transform="translate({x},{y})">
          <rect width="16" height="16" rx="4" fill="#eef1ff" />
          <circle cx="8" cy="8" r="5.8" fill="#000080" />
          <circle cx="6.4" cy="7.4" r="3.4" fill="#ffffff" />
          <circle cx="8" cy="7.4" r="3.4" fill="#000080" />
          <circle cx="11.2" cy="4.8" r="1.1" fill="#ffffff" />
        </g>
        """
    if name == "rust":
        return f"""
        <g transform="translate({x},{y})">
          <rect width="16" height="16" rx="4" fill="#fff5ef" />
          <g fill="none" stroke="#dea584" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="8" cy="8" r="4.1" stroke-width="1.1" />
            <circle cx="8" cy="8" r="5.8" stroke-width="1.1" stroke-dasharray="1 1.9" />
          </g>
          <text x="8" y="8.7" text-anchor="middle" dominant-baseline="middle" fill="#8b5e3c" style="font:700 6px 'Segoe UI', Ubuntu, Sans-Serif;">R</text>
        </g>
        """
    return f"""
    <g transform="translate({x},{y})">
      <rect width="16" height="16" rx="4" fill="{fallback_color}" />
      <text x="8" y="9" text-anchor="middle" dominant-baseline="middle" fill="#ffffff" style="font:700 7px 'Segoe UI', Ubuntu, Sans-Serif;">{escape((language_name or "?")[:2].upper())}</text>
    </g>
    """


def render_scaled_language_icon(language_name: str, x: int, y: int, size: float, fallback_color: str) -> str:
    scale = size / 16
    return f'<g transform="translate({x},{y}) scale({scale:.4f})">{render_language_icon(language_name, 0, 0, fallback_color)}</g>'


def donut_segment_path(cx: float, cy: float, outer_radius: float, inner_radius: float, start_angle: float, sweep_angle: float) -> str:
    if sweep_angle <= 0:
        return ""

    start_rad = math.radians(start_angle - 90)
    end_rad = math.radians(start_angle + sweep_angle - 90)
    x1 = cx + outer_radius * math.cos(start_rad)
    y1 = cy + outer_radius * math.sin(start_rad)
    x2 = cx + outer_radius * math.cos(end_rad)
    y2 = cy + outer_radius * math.sin(end_rad)
    x3 = cx + inner_radius * math.cos(end_rad)
    y3 = cy + inner_radius * math.sin(end_rad)
    x4 = cx + inner_radius * math.cos(start_rad)
    y4 = cy + inner_radius * math.sin(start_rad)
    large_arc_flag = 1 if sweep_angle > 180 else 0

    return (
        f"M{x1:.2f},{y1:.2f} "
        f"A{outer_radius:.2f},{outer_radius:.2f} 0 {large_arc_flag} 1 {x2:.2f},{y2:.2f} "
        f"L{x3:.2f},{y3:.2f} "
        f"A{inner_radius:.2f},{inner_radius:.2f} 0 {large_arc_flag} 0 {x4:.2f},{y4:.2f} Z"
    )


def chunk_points(values: list[int], width: int, height: int, left: int, top: int) -> str:
    if not values:
        return ""

    max_value = max(values) or 1
    step = width / max(1, len(values) - 1)
    points = []
    for index, value in enumerate(values):
        x = left + (step * index)
        y = top + height - ((value / max_value) * height)
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def build_overview_svg(username: str, stats: dict[str, int], monthly_contributions: dict[str, int]) -> str:
    metric_boxes = [
        ("Total GitHub Stars", format_number(stats["total_stars"]), "star"),
        ("Total GitHub Followers", format_number(stats["followers"]), "followers"),
        ("Public Repositories", format_number(stats["public_repos"]), "repo"),
        ("Contributions (365d)", format_number(stats["contributions_365d"]), "activity"),
    ]

    month_keys = sorted(monthly_contributions.keys())[-12:]
    month_values = [monthly_contributions[key] for key in month_keys]
    chart_height = 32
    chart_top = 186
    chart_points = chunk_points(month_values, width=430, height=chart_height, left=36, top=chart_top)
    max_month_value = max(month_values) if month_values else 0
    boxes_svg = []
    for index, (label, value, icon_kind) in enumerate(metric_boxes):
        row = index // 2
        col = index % 2
        x = 24 + (col * 228)
        y = 54 + (row * 54)
        boxes_svg.append(
            f"""
            <g transform="translate({x},{y})">
              <rect width="216" height="48" rx="12" fill="{THEME['bar_bg']}" />
              {render_metric_icon(icon_kind, 14, 17, THEME['title'])}
              <text x="34" y="14" class="label" dominant-baseline="middle">{escape(label)}</text>
              <text x="34" y="33" class="value" dominant-baseline="middle">{escape(value)}</text>
            </g>
            """
        )

    month_labels_svg = []
    for index, key in enumerate(month_keys):
        if len(month_keys) <= 6 or index in {0, 2, 4, 6, 8, 10, len(month_keys) - 1}:
            x = 36 + ((430 / max(1, len(month_keys) - 1)) * index)
            month_labels_svg.append(
                f'<text x="{x:.2f}" y="244" text-anchor="middle" class="axis">{escape(month_label(key))}</text>'
            )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(username)} GitHub Stats</title>
  <desc id="desc">Auto-generated GitHub stats card with stars, followers, public repositories, contributions, and a monthly contribution graph.</desc>
  <style>
    .title {{ fill: {THEME['title']}; font: 600 19px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .label {{ fill: {THEME['muted']}; font: 500 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .value {{ fill: {THEME['text']}; font: 700 18px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .section {{ fill: {THEME['text']}; font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .axis {{ fill: {THEME['muted']}; font: 400 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
  </style>
  <rect x="1" y="1" width="{CARD_WIDTH - 2}" height="{CARD_HEIGHT - 2}" rx="12" fill="{THEME['background']}" stroke="{THEME['border']}" />
  {render_github_mark(24, 14, 17, THEME['title'])}
  <text x="49" y="25" class="title" dominant-baseline="middle">GitHub Stats</text>
  {''.join(boxes_svg)}
  <text x="24" y="176" class="section">Monthly Contributions</text>
  <line x1="36" y1="222" x2="466" y2="222" stroke="{THEME['grid']}" />
  <line x1="36" y1="206" x2="466" y2="206" stroke="{THEME['grid']}" stroke-dasharray="3 3" />
  <polyline fill="none" stroke="{THEME['title']}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="{chart_points}" />
  <circle cx="466" cy="{chart_top + chart_height - ((month_values[-1] / (max_month_value or 1)) * chart_height if month_values else chart_height):.2f}" r="4" fill="{THEME['title']}" />
  <text x="466" y="184" text-anchor="end" class="axis">Peak {format_number(max_month_value)}</text>
  {''.join(month_labels_svg)}
</svg>
"""


def build_language_svg(username: str, language_stats: list[dict[str, Any]], total_bytes: int) -> str:
    top_languages = language_stats[:6]
    grid_svg = []
    donut_svg = []
    footer = ""

    if not top_languages:
        footer = f'<text x="24" y="120" class="empty">No public repository language data was found.</text>'
    else:
        tile_width = 118
        tile_height = 58
        tile_gap_x = 10
        tile_gap_y = 10
        grid_start_x = 24
        grid_start_y = 56

        for index, language in enumerate(top_languages):
            col = index % 2
            row = index // 2
            tile_x = grid_start_x + col * (tile_width + tile_gap_x)
            tile_y = grid_start_y + row * (tile_height + tile_gap_y)
            percentage = (language["size"] / total_bytes * 100) if total_bytes else 0
            label_text = language["name"]
            label_font_size = 14 if len(label_text) <= 8 else 13 if len(label_text) <= 10 else 12
            icon_size = 20
            icon_x = 12
            label_x = 41
            grid_svg.append(
                f"""
                <g transform="translate({tile_x},{tile_y})">
                  <rect width="{tile_width}" height="{tile_height}" rx="12" fill="{THEME['bar_bg']}" />
                  <rect y="{tile_height - 4}" width="{tile_width}" height="4" rx="2" fill="{escape(language['color'])}" />
                  {render_scaled_language_icon(language['name'], icon_x, 12, icon_size, language['color'])}
                  <text x="{label_x}" y="22" class="tile-label" dominant-baseline="middle" style="font-size:{label_font_size}px;">{escape(label_text)}</text>
                  <text x="12" y="43" class="tile-rank" dominant-baseline="middle">#{index + 1}</text>
                  <text x="{tile_width - 12}" y="43" text-anchor="end" class="tile-percent" dominant-baseline="middle">{percentage:.1f}%</text>
                </g>
                """
            )

        cx = 376
        cy = 138
        outer_radius = 80
        inner_radius = 49
        current_angle = 0.0
        for language in top_languages:
            percentage = (language["size"] / total_bytes * 100) if total_bytes else 0
            sweep_angle = percentage / 100 * 360
            donut_svg.append(
                f'<path d="{donut_segment_path(cx, cy, outer_radius, inner_radius, current_angle, sweep_angle)}" fill="{escape(language["color"])}" />'
            )
            current_angle += sweep_angle

        if current_angle < 360:
            donut_svg.append(
                f'<path d="{donut_segment_path(cx, cy, outer_radius, inner_radius, current_angle, 360 - current_angle)}" fill="{THEME["bar_bg"]}" />'
            )

        top_language = top_languages[0]
        top_percentage = (top_language["size"] / total_bytes * 100) if total_bytes else 0
        donut_svg.append(f'<circle cx="{cx}" cy="{cy}" r="{inner_radius - 2}" fill="{THEME["background"]}" />')
        donut_svg.append(
            f'<text x="{cx}" y="{cy - 9}" text-anchor="middle" class="donut-main" dominant-baseline="middle">{top_percentage:.1f}%</text>'
        )
        donut_svg.append(
            f'<text x="{cx}" y="{cy + 13}" text-anchor="middle" class="donut-sub" dominant-baseline="middle">{escape(top_language["name"])}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(username)} Most Used Languages</title>
  <desc id="desc">Auto-generated GitHub language usage card based on public repositories.</desc>
  <style>
    .title {{ fill: {THEME['title']}; font: 600 19px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .tile-label {{ fill: {THEME['text']}; font: 700 13px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .tile-rank {{ fill: {THEME['muted']}; font: 600 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .tile-percent {{ fill: {THEME['muted']}; font: 700 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .donut-main {{ fill: {THEME['text']}; font: 700 22px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .donut-sub {{ fill: {THEME['muted']}; font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .empty {{ fill: {THEME['muted']}; font: 500 12px 'Segoe UI', Ubuntu, Sans-Serif; }}
  </style>
  <rect x="1" y="1" width="{CARD_WIDTH - 2}" height="{CARD_HEIGHT - 2}" rx="12" fill="{THEME['background']}" stroke="{THEME['border']}" />
  {render_github_mark(24, 14, 17, THEME['title'])}
  <text x="49" y="25" class="title" dominant-baseline="middle">Most Used Languages</text>
  {''.join(grid_svg)}
  {''.join(donut_svg)}
  {footer}
</svg>
"""


def build_top_repositories_svg(username: str, repositories: list[dict[str, Any]]) -> str:
    top_repositories = sorted(
        repositories,
        key=lambda repo: (int(repo.get("stargazerCount") or 0), repo.get("pushedAt") or ""),
        reverse=True,
    )[:3]

    rows_svg = []
    if not top_repositories:
        rows_svg.append('<text x="24" y="120" class="empty">No public repositories were found.</text>')
    else:
        for index, repository in enumerate(top_repositories):
            y = 58 + (index * 62)
            fallback_language = ((((repository.get("languages") or {}).get("edges")) or [{}])[0].get("node")) or {}
            language = repository.get("primaryLanguage") or fallback_language or {}
            language_name = language.get("name") or "Unknown"
            language_color = language.get("color") or THEME["title"]
            language_icon = (
                render_scaled_language_icon(language_name, 10, 14, 20, language_color)
                if language_name != "Unknown"
                else f'<circle cx="20" cy="27" r="7" fill="{language_color}" />'
            )
            rows_svg.append(
                f"""
                <g transform="translate(24,{y})">
                  <rect width="447" height="54" rx="12" fill="{THEME['bar_bg']}" />
                  {language_icon}
                  <text x="40" y="18" class="repo" dominant-baseline="middle">{escape(repository['name'])}</text>
                  {render_metric_icon("star", 370, 20, THEME['title'])}
                  <text x="429" y="27" text-anchor="end" class="stars" dominant-baseline="middle">{escape(format_number(int(repository.get('stargazerCount') or 0)))}</text>
                  <text x="40" y="37" class="desc" dominant-baseline="middle">{escape(truncate_text(repository.get('description') or 'Open-source project', 55))}</text>
                </g>
                """
            )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(username)} Top Repositories by Stars</title>
  <desc id="desc">Auto-generated card showing the most starred public repositories.</desc>
  <style>
    .title {{ fill: {THEME['title']}; font: 600 19px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .repo {{ fill: {THEME['text']}; font: 700 14px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .stars {{ fill: {THEME['text']}; font: 700 14px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .desc {{ fill: {THEME['muted']}; font: 500 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .empty {{ fill: {THEME['muted']}; font: 500 12px 'Segoe UI', Ubuntu, Sans-Serif; }}
  </style>
  <rect x="1" y="1" width="{CARD_WIDTH - 2}" height="{CARD_HEIGHT - 2}" rx="12" fill="{THEME['background']}" stroke="{THEME['border']}" />
  {render_github_mark(24, 14, 17, THEME['title'])}
  <text x="49" y="25" class="title" dominant-baseline="middle">Top Repositories by Stars</text>
  {''.join(rows_svg)}
</svg>
"""


def build_recent_releases_svg(username: str, repositories: list[dict[str, Any]]) -> str:
    releases = []
    for repository in repositories:
        fallback_language = ((((repository.get("languages") or {}).get("edges")) or [{}])[0].get("node")) or {}
        language = repository.get("primaryLanguage") or fallback_language or {}
        language_name = language.get("name") or "Unknown"
        language_color = language.get("color") or THEME["title"]
        release_nodes = ((repository.get("releases") or {}).get("nodes")) or []
        for release in release_nodes:
            if release.get("isDraft") or release.get("isPrerelease") or not release.get("publishedAt"):
                continue
            releases.append(
                {
                    "repo_name": repository["name"],
                    "tag_name": release.get("tagName") or "",
                    "name": release.get("name") or release.get("tagName") or "Untitled release",
                    "published_at": release["publishedAt"],
                    "language_name": language_name,
                    "language_color": language_color,
                }
            )

    recent_releases = sorted(releases, key=lambda item: parse_iso_datetime(item["published_at"]), reverse=True)[:3]

    rows_svg = []
    if not recent_releases:
        rows_svg.append('<text x="24" y="120" class="empty">No published releases were found.</text>')
    else:
        for index, release in enumerate(recent_releases):
            y = 58 + (index * 62)
            tag_text = truncate_text(release["tag_name"], 14)
            repo_name = truncate_text(release["repo_name"], 24)
            tag_width = max(42, min(92, len(tag_text) * 7 + 16))
            language_icon = (
                render_scaled_language_icon(release["language_name"], 10, 19, 20, release["language_color"])
                if release["language_name"] != "Unknown"
                else f'<circle cx="20" cy="29" r="7" fill="{release["language_color"]}" />'
            )
            rows_svg.append(
                f"""
                <g transform="translate(24,{y})">
                  <rect width="447" height="58" rx="12" fill="{THEME['bar_bg']}" />
                  {language_icon}
                  <text x="40" y="29" class="repo" dominant-baseline="middle">{escape(repo_name)}</text>
                  <text x="431" y="19" text-anchor="end" class="date" dominant-baseline="middle">{escape(format_short_date(release['published_at']))}</text>
                  <rect x="{431 - tag_width:.2f}" y="31" width="{tag_width}" height="18" rx="9" fill="{THEME['background']}" />
                  <text x="{431 - tag_width / 2:.2f}" y="40" text-anchor="middle" class="tag" dominant-baseline="middle">{escape(tag_text)}</text>
                </g>
                """
            )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(username)} Recent Releases</title>
  <desc id="desc">Auto-generated card showing the most recent published releases across public repositories.</desc>
  <style>
    .title {{ fill: {THEME['title']}; font: 600 19px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .repo {{ fill: {THEME['text']}; font: 700 16px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .date {{ fill: {THEME['muted']}; font: 500 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .tag {{ fill: {THEME['title']}; font: 700 11px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .empty {{ fill: {THEME['muted']}; font: 500 12px 'Segoe UI', Ubuntu, Sans-Serif; }}
  </style>
  <rect x="1" y="1" width="{CARD_WIDTH - 2}" height="{CARD_HEIGHT - 2}" rx="12" fill="{THEME['background']}" stroke="{THEME['border']}" />
  {render_github_mark(24, 14, 17, THEME['title'])}
  <text x="49" y="25" class="title" dominant-baseline="middle">Recent Releases</text>
  {''.join(rows_svg)}
</svg>
"""


def normalize_language_stats(repositories: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    sizes: dict[str, int] = defaultdict(int)
    colors: dict[str, str] = {}

    for repository in repositories:
        languages = repository.get("languages") or {}
        for edge in languages.get("edges") or []:
            node = edge.get("node") or {}
            name = node.get("name")
            if not name:
                continue
            sizes[name] += int(edge.get("size") or 0)
            if node.get("color"):
                colors[name] = node["color"]

    sorted_languages = sorted(sizes.items(), key=lambda item: item[1], reverse=True)
    stats = []
    for index, (name, size) in enumerate(sorted_languages):
        stats.append(
            {
                "name": name,
                "size": size,
                "color": colors.get(name) or FALLBACK_LANGUAGE_COLORS[index % len(FALLBACK_LANGUAGE_COLORS)],
            }
        )
    total_bytes = sum(sizes.values())
    return stats, total_bytes


def aggregate_monthly_contributions(weeks: list[dict[str, Any]]) -> dict[str, int]:
    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=365)
    monthly: dict[str, int] = defaultdict(int)

    for week in weeks:
        for day in week.get("contributionDays") or []:
            date = datetime.strptime(day["date"], "%Y-%m-%d").date()
            if date < start_date:
                continue
            monthly[date.strftime("%Y-%m")] += int(day["contributionCount"])

    cursor = datetime(start_date.year, start_date.month, 1).date()
    end_cursor = datetime(today.year, today.month, 1).date()
    while cursor <= end_cursor:
        monthly.setdefault(cursor.strftime("%Y-%m"), 0)
        if cursor.month == 12:
            cursor = datetime(cursor.year + 1, 1, 1).date()
        else:
            cursor = datetime(cursor.year, cursor.month + 1, 1).date()

    return dict(sorted(monthly.items()))


def fetch_profile_data(username: str, token: str | None) -> dict[str, Any]:
    query = """
    query ProfileStats($login: String!, $cursor: String, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        login
        name
        followers {
          totalCount
        }
        repositories(
          first: 100
          after: $cursor
          privacy: PUBLIC
          isFork: false
          ownerAffiliations: OWNER
          orderBy: { field: UPDATED_AT, direction: DESC }
        ) {
          nodes {
            name
            description
            url
            pushedAt
            stargazerCount
            primaryLanguage {
              name
              color
            }
            releases(first: 5, orderBy: { field: CREATED_AT, direction: DESC }) {
              nodes {
                name
                tagName
                publishedAt
                isDraft
                isPrerelease
                url
              }
            }
            languages(first: 20, orderBy: { field: SIZE, direction: DESC }) {
              totalSize
              edges {
                size
                node {
                  name
                  color
                }
              }
            }
          }
          pageInfo {
            hasNextPage
            endCursor
          }
          totalCount
        }
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """

    repositories: list[dict[str, Any]] = []
    base_user: dict[str, Any] | None = None
    cursor: str | None = None
    from_date = (datetime.now(UTC) - timedelta(days=365)).isoformat()
    to_date = datetime.now(UTC).isoformat()

    while True:
        data = github_graphql(
            query,
            {
                "login": username,
                "cursor": cursor,
                "from": from_date,
                "to": to_date,
            },
            token,
        )
        user = data.get("user")
        if not user:
            raise RuntimeError(f"GitHub user '{username}' was not found.")

        base_user = user
        repository_connection = user["repositories"]
        repositories.extend(repository_connection.get("nodes") or [])
        page_info = repository_connection["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]

    assert base_user is not None
    return {
        "username": base_user["login"],
        "display_name": base_user.get("name") or base_user["login"],
        "followers": int(base_user["followers"]["totalCount"]),
        "public_repos": int(base_user["repositories"]["totalCount"]),
        "contribution_calendar": base_user["contributionsCollection"]["contributionCalendar"],
        "repositories": repositories,
    }


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    username = os.environ.get("PROFILE_USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not username:
        raise SystemExit("PROFILE_USERNAME or GITHUB_REPOSITORY_OWNER is required.")

    token = os.environ.get("GITHUB_TOKEN")
    profile = fetch_profile_data(username, token)

    total_stars = sum(int(repo.get("stargazerCount") or 0) for repo in profile["repositories"])
    language_stats, total_bytes = normalize_language_stats(profile["repositories"])
    monthly_contributions = aggregate_monthly_contributions(profile["contribution_calendar"]["weeks"])

    stats = {
        "total_stars": total_stars,
        "followers": profile["followers"],
        "public_repos": profile["public_repos"],
        "contributions_365d": int(profile["contribution_calendar"]["totalContributions"]),
    }

    overview_svg = build_overview_svg(profile["username"], stats, monthly_contributions)
    language_svg = build_language_svg(profile["username"], language_stats, total_bytes)
    top_repositories_svg = build_top_repositories_svg(profile["username"], profile["repositories"])
    recent_releases_svg = build_recent_releases_svg(profile["username"], profile["repositories"])

    write_file(OUTPUT_DIR / "github-stats.svg", overview_svg)
    write_file(OUTPUT_DIR / "github-most-used-languages.svg", language_svg)
    write_file(OUTPUT_DIR / "github-top-repositories.svg", top_repositories_svg)
    write_file(OUTPUT_DIR / "github-recent-releases.svg", recent_releases_svg)


if __name__ == "__main__":
    main()
