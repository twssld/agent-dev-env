#!/usr/bin/env python3
"""Generate dark-mode HTML AI usage report from Excel or org-export CSV (optional AI_Ind)."""

from __future__ import annotations

import argparse
import html as html_module
from datetime import datetime
from pathlib import Path

import pandas as pd


def esc(s: object) -> str:
    return html_module.escape(str(s))


def tier(v: float) -> str:
    if v == 0:
        return "安装未使用(0)"
    if v <= 10:
        return "刚上手(0.001~10)"
    if v <= 100:
        return "中度使用(10~100)"
    return "重度使用(100+)"


def fmt_money(v: float) -> str:
    return f"{float(v):,.2f}"


def pct_rate(v: float) -> str:
    return f"{float(v) * 100:.1f}%"


def _strip_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _find_col(df: pd.DataFrame, *names: str) -> str | None:
    cmap = {str(c).strip(): c for c in df.columns}
    for n in names:
        if n in cmap:
            return cmap[n]
    return None


def _read_org_csv(path: Path) -> tuple[str | None, pd.DataFrame]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    period: str | None = None
    skip = 0
    if lines and lines[0].strip().startswith("时间范围"):
        parts = lines[0].split(",", 1)
        if len(parts) == 2:
            period = parts[1].strip()
        skip = 1
    df = pd.read_csv(path, skiprows=skip, encoding="utf-8-sig")
    return period, _strip_cols(df)


def normalize_dataframe(df: pd.DataFrame, *, source: str) -> pd.DataFrame:
    """Return canonical columns: 员工姓名, 二级部门, Total; optional _cc, _cr; pass-through extras."""
    df = _strip_cols(df)
    ren: dict[str, str] = {}
    if "姓名" in df.columns and "员工姓名" not in df.columns:
        ren["姓名"] = "员工姓名"
    if "部门" in df.columns and "二级部门" not in df.columns:
        ren["部门"] = "二级部门"
    df = df.rename(columns=ren)

    cc_c = _find_col(
        df,
        "ClaudeCode ($)",
        "ClaudeCode",
        "CC",
        "Claude code ($)",
    )
    cr_c = _find_col(df, "Cursor ($)", "Cursor")
    tot_c = _find_col(df, "Total", "合计 ($)", "合计")

    cc = pd.to_numeric(df[cc_c], errors="coerce").fillna(0) if cc_c else None
    cr = pd.to_numeric(df[cr_c], errors="coerce").fillna(0) if cr_c else None

    if source == "csv_org":
        if cc is None:
            cc = pd.Series(0.0, index=df.index)
        if cr is None:
            cr = pd.Series(0.0, index=df.index)
        df["Total"] = cc + cr
        df["_cc"] = cc
        df["_cr"] = cr
    else:
        if tot_c is None and cc is not None and cr is not None:
            df["Total"] = cc + cr
        elif tot_c is not None:
            df["Total"] = pd.to_numeric(df[tot_c], errors="coerce").fillna(0)
        else:
            raise SystemExit(
                "Excel sheet needs 'Total' or both CC and Cursor-like columns."
            )
        if cc is not None:
            df["_cc"] = cc
        if cr is not None:
            df["_cr"] = cr

    df["Total"] = pd.to_numeric(df["Total"], errors="coerce").fillna(0)

    for c in ["员工姓名", "一级部门", "二级部门", "岗位名称"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str)
    if "AI_Ind" in df.columns:
        df["AI_Ind"] = pd.to_numeric(df["AI_Ind"], errors="coerce").fillna(0)

    df.attrs["has_cc_cursor"] = "_cc" in df.columns and "_cr" in df.columns
    df.attrs["source"] = source
    return df


def load_df(path: Path, sheet: str) -> pd.DataFrame:
    suf = path.suffix.lower()
    if suf == ".csv":
        period, raw = _read_org_csv(path)
        df = normalize_dataframe(raw, source="csv_org")
        df.attrs["period_note"] = period
        df.attrs["dept_label"] = "部门"
    elif suf in (".xlsx", ".xls"):
        raw = pd.read_excel(path, sheet_name=sheet)
        df = normalize_dataframe(_strip_cols(raw), source="excel")
        df.attrs["period_note"] = None
        df.attrs["dept_label"] = "二级部门"
    else:
        raise SystemExit(f"Unsupported input type: {suf}")
    return df


def build_report(df: pd.DataFrame) -> str:
    period = df.attrs.get("period_note")
    dept_label = df.attrs.get("dept_label", "二级部门")
    has_breakdown = bool(df.attrs.get("has_cc_cursor"))

    has_ai = "AI_Ind" in df.columns
    total_all = len(df)

    if has_ai:
        base = df[df["AI_Ind"] == 1].copy()
        non_req = int((df["AI_Ind"] != 1).sum())
    else:
        base = df.copy()
        non_req = None

    if "二级部门" in base.columns:
        base["二级部门"] = base["二级部门"].replace("", "未分配部门")
    else:
        base = base.copy()
        base["二级部门"] = "未分配部门"

    base["分层"] = base["Total"].apply(tier)
    base["已使用AI"] = base["Total"] > 0

    n = len(base)
    active = int(base["已使用AI"].sum())
    rate = active / n * 100 if n else 0.0
    sum_cost = float(base["Total"].sum())
    avg_cost = float(base["Total"].mean()) if n else 0.0

    tier_order = [
        "安装未使用(0)",
        "刚上手(0.001~10)",
        "中度使用(10~100)",
        "重度使用(100+)",
    ]
    overall_tier = base["分层"].value_counts().reindex(tier_order, fill_value=0)

    count_col = "员工姓名" if "员工姓名" in base.columns else "Total"
    summary = (
        base.groupby("二级部门", dropna=False)
        .agg(
            应用人数=(count_col, "count"),
            使用人数=("已使用AI", "sum"),
            AI总费用=("Total", "sum"),
            人均费用=("Total", "mean"),
        )
        .reset_index()
    )

    piv = pd.crosstab(base["二级部门"], base["分层"]).reindex(columns=tier_order, fill_value=0)
    for t in tier_order:
        summary[t] = summary["二级部门"].map(piv[t]).fillna(0).astype(int)

    summary["使用率"] = summary["使用人数"] / summary["应用人数"]
    summary = summary.sort_values(
        ["使用率", "AI总费用", "应用人数"], ascending=[False, False, False]
    ).reset_index(drop=True)

    overall_tier_html = "".join(
        f"<tr><td>{esc(k)}</td><td>{int(v)}</td><td>{(v / n * 100 if n else 0):.1f}%</td></tr>"
        for k, v in overall_tier.items()
    )

    rows = []
    for _, r in summary.iterrows():
        tot = int(r["应用人数"]) or 1
        p0 = r["安装未使用(0)"] / tot * 100
        p1 = r["刚上手(0.001~10)"] / tot * 100
        p2 = r["中度使用(10~100)"] / tot * 100
        p3 = r["重度使用(100+)"] / tot * 100
        bar = (
            f'<div class="stack"><span class="s0" style="width:{p0:.2f}%"></span>'
            f'<span class="s1" style="width:{p1:.2f}%"></span>'
            f'<span class="s2" style="width:{p2:.2f}%"></span>'
            f'<span class="s3" style="width:{p3:.2f}%"></span></div>'
        )
        rows.append(
            f"<tr><td>{esc(r['二级部门'])}</td><td>{int(r['应用人数'])}</td><td>{int(r['使用人数'])}</td>"
            f"<td>{pct_rate(r['使用率'])}</td><td>{fmt_money(r['AI总费用'])}</td><td>{fmt_money(r['人均费用'])}</td>"
            f"<td>{int(r['安装未使用(0)'])}</td><td>{int(r['刚上手(0.001~10)'])}</td>"
            f"<td>{int(r['中度使用(10~100)'])}</td><td>{int(r['重度使用(100+)'])}</td><td>{bar}</td></tr>"
        )

    p0 = overall_tier["安装未使用(0)"] / n * 100 if n else 0
    p1 = overall_tier["刚上手(0.001~10)"] / n * 100 if n else 0
    p2 = overall_tier["中度使用(10~100)"] / n * 100 if n else 0
    p3 = overall_tier["重度使用(100+)"] / n * 100 if n else 0
    bar_total = (
        f'<div class="stack"><span class="s0" style="width:{p0:.2f}%"></span>'
        f'<span class="s1" style="width:{p1:.2f}%"></span>'
        f'<span class="s2" style="width:{p2:.2f}%"></span>'
        f'<span class="s3" style="width:{p3:.2f}%"></span></div>'
    )
    rows.append(
        f"<tr><td><b>总计</b></td><td><b>{n}</b></td><td><b>{active}</b></td>"
        f"<td><b>{rate:.1f}%</b></td><td><b>{fmt_money(sum_cost)}</b></td><td><b>{fmt_money(avg_cost)}</b></td>"
        f"<td><b>{int(overall_tier['安装未使用(0)'])}</b></td><td><b>{int(overall_tier['刚上手(0.001~10)'])}</b></td>"
        f"<td><b>{int(overall_tier['中度使用(10~100)'])}</b></td><td><b>{int(overall_tier['重度使用(100+)'])}</b></td>"
        f"<td>{bar_total}</td></tr>"
    )

    all_df = df.copy()
    if "一级部门" in all_df.columns:
        all_df["一级部门"] = all_df["一级部门"].replace("", "未分配部门")
    else:
        all_df["一级部门"] = ""
    if "二级部门" in all_df.columns:
        all_df["二级部门"] = all_df["二级部门"].replace("", "未分配部门")
    else:
        all_df["二级部门"] = "未分配部门"
    if "员工姓名" not in all_df.columns:
        all_df["员工姓名"] = ""
    if "岗位名称" not in all_df.columns:
        all_df["岗位名称"] = ""

    all_df["分层"] = all_df["Total"].apply(tier)
    all_df["是否使用AI"] = all_df["Total"].apply(lambda x: "是" if x > 0 else "否")
    all_df = all_df.sort_values(["Total", "二级部门"], ascending=[False, True])
    if has_ai:
        all_df["AI_Ind_说明"] = all_df["AI_Ind"].apply(lambda x: "应使用" if x == 1 else "非必需")

    extra_cols = []
    for c in ("工号", "邮箱", "调用次数"):
        if c in all_df.columns:
            extra_cols.append(c)

    if has_breakdown:
        cost_header = "<th>Claude Code ($)</th><th>Cursor ($)</th><th>合计 ($)</th>"
    else:
        cost_header = "<th>合计费用</th>"
    extra_header = "".join(f"<th>{esc(c)}</th>" for c in extra_cols)

    if has_ai:
        base_header = (
            f"<tr><th>姓名</th>{extra_header}<th>{esc(dept_label)}</th>"
            f"<th>一级部门</th><th>岗位</th><th>AI_Ind</th>{cost_header}"
            f"<th>是否使用AI</th><th>费用分层</th></tr>"
        )
    else:
        base_header = (
            f"<tr><th>姓名</th>{extra_header}<th>{esc(dept_label)}</th>"
            f"<th>一级部门</th><th>岗位</th>{cost_header}"
            f"<th>是否使用AI</th><th>费用分层</th></tr>"
        )

    all_rows = []
    for _, r in all_df.iterrows():
        extra_cells = "".join(f"<td>{esc(r[c])}</td>" for c in extra_cols)
        if has_breakdown:
            cost_cells = (
                f"<td>{fmt_money(r['_cc'])}</td><td>{fmt_money(r['_cr'])}</td>"
                f"<td>{fmt_money(r['Total'])}</td>"
            )
        else:
            cost_cells = f"<td>{fmt_money(r['Total'])}</td>"

        if has_ai:
            row = (
                f"<tr><td>{esc(r['员工姓名'])}</td>{extra_cells}<td>{esc(r['二级部门'])}</td>"
                f"<td>{esc(r['一级部门'])}</td><td>{esc(r['岗位名称'])}</td>"
                f"<td>{r['AI_Ind_说明']}</td>{cost_cells}"
                f"<td>{r['是否使用AI']}</td><td>{esc(r['分层'])}</td></tr>"
            )
        else:
            row = (
                f"<tr><td>{esc(r['员工姓名'])}</td>{extra_cells}<td>{esc(r['二级部门'])}</td>"
                f"<td>{esc(r['一级部门'])}</td><td>{esc(r['岗位名称'])}</td>{cost_cells}"
                f"<td>{r['是否使用AI']}</td><td>{esc(r['分层'])}</td></tr>"
            )
        all_rows.append(row)

    grid_parts = [
        '<div class="card"><div class="k">总人数</div><div class="v">' + str(total_all) + "</div></div>"
    ]
    if has_ai:
        grid_parts.append(
            f'<div class="card"><div class="k">非必要人数（AI_Ind≠1）</div><div class="v">{non_req}</div></div>'
        )
        grid_parts.append(f'<div class="card"><div class="k">应使用AI人数</div><div class="v">{n}</div></div>')
    grid_parts.extend(
        [
            f'<div class="card"><div class="k">已使用人数（Total&gt;0）</div><div class="v">{active}</div></div>',
            f'<div class="card"><div class="k">整体AI使用率</div><div class="v">{rate:.1f}%</div></div>',
            f'<div class="card"><div class="k">AI总费用</div><div class="v">{fmt_money(sum_cost)}</div></div>',
            f'<div class="card"><div class="k">人均AI费用</div><div class="v">{fmt_money(avg_cost)}</div></div>',
        ]
    )

    sub_parts = []
    if period:
        sub_parts.append(f"数据时间范围：<b>{esc(period)}</b>。")
    if has_ai:
        sub_parts.append(
            "统计口径：以 <b>AI_Ind=1</b> 作为应使用AI人员；"
            f"<b>Total</b> 为分层依据；维度为 <b>{esc(dept_label)}</b>。"
        )
    else:
        sub_parts.append(
            "统计口径：全员纳入分析；"
            + (
                "<b>Total</b> = <b>Claude Code</b> + <b>Cursor</b>（组织 CSV）；"
                if df.attrs.get("source") == "csv_org"
                else "<b>Total</b> 为表内合计费用；"
            )
            + f"维度为 <b>{esc(dept_label)}</b>。"
        )
    sub_note = "".join(sub_parts)

    tier_title = "整体费用分层（AI_Ind=1）" if has_ai else "整体费用分层（全员）"
    dept_title = f"按{dept_label}分析（按使用率降序）" + (" — 应使用人群" if has_ai else "")

    dept_th = esc(dept_label)

    css = """\
:root {
  color-scheme: dark;
  --bg: #0d1117;
  --surface: #161b22;
  --surface-hover: #1c2128;
  --border: #30363d;
  --text: #e6edf3;
  --muted: #8b949e;
  --accent: #58a6ff;
  --thead: #21262d;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif;
  margin: 0;
  min-height: 100vh;
  padding: 24px;
  background: var(--bg);
  color: var(--text);
}
h1 { margin: 0 0 8px; font-weight: 700; letter-spacing: -0.02em; }
h3 { color: var(--text); font-weight: 600; margin: 0 0 10px; }
.sub { color: var(--muted); margin-bottom: 18px; line-height: 1.5; }
.sub b { color: #c9d1d9; font-weight: 600; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 12px 0 20px; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  box-shadow: 0 1px 0 rgba(255,255,255,0.04);
}
.card .k { font-size: 12px; color: var(--muted); }
.card .v { margin-top: 6px; font-size: 22px; font-weight: 700; color: var(--accent); }
section { margin-top: 24px; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { border: 1px solid var(--border); padding: 8px; text-align: center; }
.table th { background: var(--thead); color: var(--muted); font-weight: 600; }
.table tbody tr:nth-child(even) { background: rgba(255, 255, 255, 0.02); }
.table tbody tr:hover { background: var(--surface-hover); }
.table td:first-child, .table th:first-child { text-align: left; }
.stack {
  width: 180px;
  height: 12px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--thead);
  margin: auto;
  display: flex;
  flex-direction: row-reverse;
  border: 1px solid var(--border);
}
.stack span { height: 100%; display: block; }
.s0 { background: #6e7681; }
.s1 { background: #79c0ff; }
.s2 { background: #388bfd; }
.s3 { background: #a371f7; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: var(--muted); margin: 8px 0 10px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; vertical-align: middle; }
.l0 { background: #6e7681; }
.l1 { background: #79c0ff; }
.l2 { background: #388bfd; }
.l3 { background: #a371f7; }
.small { font-size: 12px; color: var(--muted); margin-top: 28px; }
"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AI使用率分析报表</title>
<style>
{css}
</style>
</head>
<body>
  <h1>AI使用率分析报表</h1>
  <div class="sub">{sub_note}</div>
  <div class="grid">
{"".join(grid_parts)}
  </div>
  <section>
    <h3>{tier_title}</h3>
    <table class="table">
      <thead><tr><th>分层</th><th>人数</th><th>占比</th></tr></thead>
      <tbody>{overall_tier_html}</tbody>
    </table>
  </section>
  <section>
    <h3>{dept_title}</h3>
    <div class="legend">
      <span><i class="dot l3"></i>重度使用(100+)</span>
      <span><i class="dot l2"></i>中度使用(10~100)</span>
      <span><i class="dot l1"></i>刚上手(0.001~10)</span>
      <span><i class="dot l0"></i>安装未使用(0)</span>
    </div>
    <table class="table">
      <thead>
        <tr>
          <th>{dept_th}</th><th>应用人数</th><th>使用人数</th><th>使用率</th><th>AI总费用</th><th>人均费用</th>
          <th>0</th><th>0.001~10</th><th>10~100</th><th>100+</th><th>分层结构</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </section>
  <section>
    <h3>所有人员数据明细（按合计费用降序）</h3>
    <table class="table">
      <thead>{base_header}</thead>
      <tbody>
{chr(10).join(all_rows)}
      </tbody>
    </table>
  </section>
  <p class="small">生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate AI usage HTML report from Excel or CSV."
    )
    ap.add_argument("--input", "-i", type=Path, required=True, help="Input .xlsx / .csv")
    ap.add_argument("--output", "-o", type=Path, required=True, help="Output .html")
    ap.add_argument("--sheet", "-s", default="汇总数据", help="Excel sheet (default: 汇总数据)")
    ap.add_argument("--names", nargs="*", default=None, help="Filter by employee names")
    args = ap.parse_args()

    df = load_df(args.input, args.sheet)
    if args.names:
        name_col = "员工姓名" if "员工姓名" in df.columns else "姓名"
        df = df[df[name_col].isin(args.names)].reset_index(drop=True)
    html = build_report(df)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
