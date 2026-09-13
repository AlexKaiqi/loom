"""G0 source anchors only: this does not judge semantic completeness."""
from pathlib import Path
import hashlib, json, re
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "harness-runtime-revised-v5.md"

def build():
    source = SOURCE.read_text()
    lines = source.splitlines()
    sections = {}
    current = None
    for n, line in enumerate(lines, 1):
        match = re.match(r"^#{2,3} (\d+(?:\.\d+)?)\.? ", line)
        if match:
            current = match.group(1)
            sections[current] = []
        if current:
            sections[current].append((n, line))
    required = {"id", "source_section", "source_quote", "kind", "requirement", "properties", "stage", "acceptance_outline", "unresolved", "status"}
    kinds = {"goal", "principle", "invariant", "contract", "decision", "non_goal", "definition"}
    rows, errors, inputs = [], [], {}
    for filename in ["v5-a.json", "v5-b.json", "user-and-process.json", "research.json"]:
        path = ROOT / "design" / "requirements" / filename
        inputs[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        for item in json.loads(path.read_text()):
            ident = item.get("id", "MISSING")
            if not required <= set(item): errors.append([ident, "missing fields"])
            if item.get("kind") not in kinds: errors.append([ident, "invalid kind"])
            if item.get("stage") not in {"M", "X", "M+X"}: errors.append([ident, "invalid stage"])
            if item.get("status") != "UNVERIFIED": errors.append([ident, "premature runtime status"])
            if any(p not in {f"P{i:02}" for i in range(1,16)} for p in item.get("properties", [])): errors.append([ident, "invalid property"])
            if not item.get("acceptance_outline", "").strip(): errors.append([ident, "empty acceptance outline"])
            row = dict(item)
            row["input_file"] = str(path.relative_to(ROOT))
            if filename.startswith("v5-"):
                target = sections.get(str(item["source_section"]).removeprefix("§"), [])
                quote = item["source_quote"]
                section_text = "\n".join(line for _,line in target)
                if not quote or quote not in section_text:
                    errors.append([ident, "quote not in claimed section"])
                else:
                    offset = section_text.index(quote)
                    row["source_line"] = target[0][0] + section_text[:offset].count("\n")
                row["source_file"] = str(SOURCE.relative_to(ROOT))
            elif "source_file" in item and "source_line" in item:
                research_path = ROOT / item["source_file"]
                research_lines = research_path.read_text().splitlines()
                if item["source_quote"] != research_lines[item["source_line"]-1]: errors.append([ident, "source file line mismatch"])
                inputs[item["source_file"]] = hashlib.sha256(research_path.read_bytes()).hexdigest()
            else:
                row["source_file"] = "user conversation / GOAL.md"
            rows.append(row)
    ids = [x["id"] for x in rows]
    if len(ids) != len(set(ids)): errors.append(["all", "duplicate IDs"])
    inputs[str(SOURCE.relative_to(ROOT))] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    result = {"scope": "G0 structural and exact-source checks; not semantic completeness or system acceptance", "status": "PASS" if not errors else "FAIL", "inputs_sha256": inputs, "requirements_count": len(rows), "errors": errors}
    out = ROOT / "design" / "reviews"
    out.mkdir(exist_ok=True)
    (out / "g0-source-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    (ROOT / "design" / "requirements-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2)+"\n")
    header = ["# G0 原始要求索引", "", "此文件由 verify_source_index.py 生成；精确锚点不等于语义完整性或系统验收。所有系统要求仍为 UNVERIFIED。完整判据草案和未知项见原 JSON 卡片。", "", "| ID | 来源 | 类别 | 范围 | 性质 | 要求 |", "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        source_label = "v5 §"+str(row["source_section"]).removeprefix("§") if row["id"].startswith("V5-") else str(row["source_section"])
        source_label += (" L"+str(row["source_line"])) if "source_line" in row else ""
        values = [row["id"], source_label, row["kind"], row["stage"], ", ".join(row["properties"]), row["requirement"]]
        header.append("| "+" | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in values)+" |")
    (ROOT / "design" / "requirements-matrix.md").write_text("\n".join(header)+"\n")
    print(json.dumps(result, ensure_ascii=False))
    return int(bool(errors))

if __name__ == "__main__":
    raise SystemExit(build())
