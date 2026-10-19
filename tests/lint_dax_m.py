"""Structural review of dax/measures.dax and powerquery/*.m.  ALL DATA IS SYNTHETIC.

IMPORTANT: this is NOT a DAX or Power Query engine. It cannot evaluate anything.
It catches typos a human reviewer would: unbalanced brackets/quotes, unknown
function names, references to tables/columns/measures that do not exist,
duplicate or circular measures, and M type lists that do not match the CSV headers.
Execution in Power BI / DAX Studio is still required.
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"

# Functions this project is allowed to use. Anything else is flagged for a human to look at.
DAX_FUNCTIONS = {
    "SUM", "SUMX", "COUNTROWS", "DISTINCTCOUNT", "DIVIDE", "CALCULATE", "REMOVEFILTERS", "FILTER",
    "RELATED", "VALUES", "SELECTCOLUMNS", "TREATAS", "EDATE", "IF", "MAX", "MAXX", "AVERAGEX",
    "DATEDIFF", "VAR", "RETURN", "IN", "DEFINE", "MEASURE",
}
M_FUNCTIONS_OK = re.compile(r"^(Table|List|Text|Csv|File|Int64|Number|Date|#table|#date)")


def headers():
    out = {}
    for f in CLEAN.glob("*.csv"):
        with open(f, newline="", encoding="utf-8") as fh:
            out[f.stem] = next(csv.reader(fh))
    out["param_AsOfDate"] = ["AsOfDate"]
    out["_Measures"] = ["Placeholder"]
    return out


def _balanced(s, pairs=("()", "[]", "{}")):
    errs = []
    for o, c in pairs:
        depth = 0
        for ch in s:
            depth += (ch == o) - (ch == c)
            if depth < 0:
                break
        if depth != 0:
            errs.append(f"unbalanced {o}{c}")
    return errs


def lint_dax(path=ROOT / "dax" / "measures.dax"):
    problems, notes = [], []
    raw = path.read_text()
    code = re.sub(r"(?m)//.*$", "", raw)                       # strip comments
    if code.count('"') % 2:
        problems.append("odd number of double quotes")
    stripped = re.sub(r'"[^"]*"', '""', code)                  # drop string literals
    problems += [f"file: {e}" for e in _balanced(stripped)]

    chunks = re.split(r"(?m)^MEASURE\s+", stripped)[1:]
    names, bodies = [], {}
    for ch in chunks:
        m = re.match(r"_Measures\[([^\]]+)\]\s*=\s*(.*)", ch, flags=re.S)
        if not m:
            problems.append(f"bad MEASURE header: {ch[:40]!r}")
            continue
        names.append(m.group(1))
        bodies[m.group(1)] = m.group(2)
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        problems.append(f"duplicate measure names: {sorted(dupes)}")

    h = headers()
    graph = {}
    for name, body in bodies.items():
        for e in _balanced(body):
            problems.append(f"[{name}] {e}")
        # Table[Column] references
        for tbl, col in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]", body):
            if tbl not in h:
                problems.append(f"[{name}] unknown table {tbl}")
            elif col not in h[tbl]:
                problems.append(f"[{name}] unknown column {tbl}[{col}]")
        # bare [Measure] references
        refs = re.findall(r"(?<![A-Za-z0-9_\]])\[([^\]]+)\]", body)
        graph[name] = set(refs)
        for r in refs:
            if r not in bodies:
                problems.append(f"[{name}] references undefined measure [{r}]")
        # function names
        for fn in re.findall(r"\b([A-Za-z][A-Za-z0-9\.]*)\s*\(", body):
            if fn.upper() not in DAX_FUNCTIONS:
                problems.append(f"[{name}] function not on the reviewed list: {fn}")
        if "TODAY" in body.upper() or "NOW()" in body.upper():
            problems.append(f"[{name}] uses today/now; as-of date must be the parameter")

    # circular references
    def has_cycle(n, seen=()):
        if n in seen:
            return True
        return any(has_cycle(c, seen + (n,)) for c in graph.get(n, ()) if c in graph)

    for n in graph:
        if has_cycle(n):
            problems.append(f"circular reference involving [{n}]")
    notes.append(f"{len(names)} measures parsed")
    return problems, notes


def lint_m(folder=ROOT / "powerquery"):
    problems, notes = [], []
    h = headers()
    files = sorted(folder.glob("*.m"))
    for f in files:
        code = re.sub(r"(?m)^\s*//.*$", "", f.read_text())
        if code.count('"') % 2:
            problems.append(f"{f.name}: odd number of double quotes")
        s = re.sub(r'"[^"]*"', '""', code)
        problems += [f"{f.name}: {e}" for e in _balanced(s)]
        if f.stem in h and f.stem not in ("param_AsOfDate", "_Measures"):
            if not re.search(r"\blet\b", code) or not re.search(r"\bin\b", code):
                problems.append(f"{f.name}: missing let/in")
            typed = re.findall(r'\{"([A-Za-z0-9_]+)",\s*(?:type [a-z]+|Int64\.Type)\}', code)
            if typed != h[f.stem]:
                problems.append(f"{f.name}: typed columns {typed} != CSV header {h[f.stem]}")
            m = re.search(r'fnLoadCsv\("([^"]+)"\)', code)
            if not m or not (CLEAN / m.group(1)).exists():
                problems.append(f"{f.name}: source CSV missing")
            if '"en-US"' not in code:
                problems.append(f"{f.name}: culture not set on type conversion")
    qa = (folder / "qa_row_counts.m").read_text()
    for t in re.findall(r"Table\.RowCount\(([a-z_]+)\)", qa):
        if t not in h:
            problems.append(f"qa_row_counts.m: unknown query {t}")
    notes.append(f"{len(files)} M files reviewed")
    return problems, notes


if __name__ == "__main__":
    for fn in (lint_dax, lint_m):
        p, n = fn()
        print(fn.__name__, n, "PROBLEMS:" if p else "no problems found", *p, sep="\n  ")
