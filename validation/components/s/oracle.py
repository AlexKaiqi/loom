"""Independent byte/journal reader. Does not import Pi/S or inspect S success claims."""
from pathlib import Path
import hashlib, json

class InvalidEvidence(Exception):
    pass

def sha(data):
    return hashlib.sha256(data).hexdigest()

def strict_json(text):
    def no_duplicate(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise InvalidEvidence("duplicate JSON key: " + key)
            out[key] = value
        return out
    try:
        return json.loads(text, object_pairs_hook=no_duplicate,
                          parse_constant=lambda value: (_ for _ in ()).throw(InvalidEvidence("nonfinite JSON")))
    except (ValueError, UnicodeError) as error:
        raise InvalidEvidence(str(error)) from error

def native_tool_text(messages):
    texts=[]
    for m in messages:
        if not isinstance(m,dict) or m.get("role") not in ("tool","toolResult"):continue
        content=m.get("content",[])
        if isinstance(content,str):texts.append(content)
        elif isinstance(content,list):texts.extend(block["text"] for block in content if isinstance(block,dict) and block.get("type")=="text" and isinstance(block.get("text"),str))
    return "\n".join(texts)

def clipped_context_objects(value):
    """Read the finite default Harness JSON context blocks from actual payload."""
    found=[]
    def visit(x):
        if isinstance(x,dict):
            if x.get("clipped") is True:found.append(x);return
            for v in x.values():visit(v)
        elif isinstance(x,list):
            for v in x:visit(v)
        elif isinstance(x,str):
            try:parsed=strict_json(x)
            except InvalidEvidence:return
            if isinstance(parsed,(dict,list)):visit(parsed)
    visit(value);return found

def pi_jsonl(data):
    if not data or not data.endswith(b"\n"):
        raise InvalidEvidence("missing complete Pi JSONL bytes")
    lines = data.decode("utf-8", errors="strict").splitlines()
    rows = [strict_json(line) for line in lines]
    head = rows.pop(0)
    if not isinstance(head, dict) or head.get("v") != 4 or head.get("kind") != "header":
        raise InvalidEvidence("not original Pi v4 JSONL")
    values, lists, entries, records = {}, {}, [], []
    seen_entries, previous_seq = set(), 0
    for transaction in rows:
        writes = transaction if isinstance(transaction, list) else [transaction]
        if not writes:
            raise InvalidEvidence("empty transaction")
        for row in writes:
            if not isinstance(row, dict) or type(row.get("seq")) is not int or row["seq"] <= previous_seq:
                raise InvalidEvidence("invalid/non-increasing original sequence")
            previous_seq = row["seq"]
            records.append(row)
            kind = row.get("kind")
            if kind == "entry":
                if row.get("id") in seen_entries or not isinstance(row.get("id"), str):
                    raise InvalidEvidence("duplicate/missing original entry")
                if row.get("parentId") is not None and row["parentId"] not in seen_entries:
                    raise InvalidEvidence("unresolved original parent")
                seen_entries.add(row["id"])
                entries.append(row)
            elif kind in ("value", "list"):
                if not isinstance(row.get("namespace"), str) or not isinstance(row.get("key"), str):
                    raise InvalidEvidence("missing original value address")
                table = values if kind == "value" else lists
                bucket = table.setdefault(row["namespace"], {})
                key, op = row["key"], row.get("op")
                if op == "delete":
                    bucket.pop(key, None)
                elif kind == "value" and op == "set" and "value" in row:
                    bucket[key] = row["value"]
                elif kind == "list" and op == "append" and "value" in row:
                    bucket.setdefault(key, []).append(row["value"])
                else:
                    raise InvalidEvidence("unknown Pi value/list mutation")
            elif kind != "usage":
                raise InvalidEvidence("unsupported Pi record kind: " + str(kind))
    counts = {role: 0 for role in ("user", "assistant", "toolResult")}
    messages = []
    for entry in entries:
        if entry.get("type") == "message":
            message = entry.get("message")
            if not isinstance(message, dict):
                raise InvalidEvidence("message missing")
            messages.append(message)
            if message.get("role") in counts:
                counts[message["role"]] += 1
    assistants = [m for m in messages if m.get("role") == "assistant"]
    return {"header": head, "sha256": sha(data), "bytes": len(data),
            "entries": entries, "entry_ids": [e["id"] for e in entries],
            "values": values, "lists": lists, "records": records, "counts": counts,
            "native_tool_text":native_tool_text(messages),
            "assistant_stop_reasons": [m["stopReason"] for m in assistants],
            "assistant_tool_call_counts": [sum(x.get("type") == "toolCall" for x in m.get("content", [])) for m in assistants]}

def read_artifact(root, label, descriptor):
    if not isinstance(descriptor, dict) or descriptor.get("origin") != "trusted_external_collector":
        raise InvalidEvidence("unattested collector source " + label)
    relative = Path(descriptor.get("path", ""))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise InvalidEvidence("artifact path escapes collection")
    path = root / relative
    if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise InvalidEvidence("artifact symlink prohibited")
    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise InvalidEvidence("missing or unbounded artifact")
    data = path.read_bytes()
    if sha(data) != descriptor.get("sha256"):
        raise InvalidEvidence("artifact hash mismatch " + label)
    role = label.split(":")[0]
    if role == "session":
        return pi_jsonl(data)
    if role == "bytes":
        return {"sha256": sha(data), "bytes": len(data), "text": data.decode("utf-8", errors="strict")}
    if role == "journal":
        rows = [strict_json(line) for line in data.decode("utf-8", errors="strict").splitlines()]
        if not all(isinstance(row, dict) and isinstance(row.get("type"), str) for row in rows):
            raise InvalidEvidence("journal must contain typed external observations")
        tool_messages=[]
        for row in rows:
            payload=row.get("payload",{})
            if isinstance(payload,dict):
                messages=payload.get("messages",payload.get("context",{}).get("messages",[]) if isinstance(payload.get("context"),dict) else [])
                tool_messages.extend(m for m in messages if isinstance(m,dict) and m.get("role") in ("tool","toolResult"))
        return {"tool_result_text":json.dumps(tool_messages,ensure_ascii=False,sort_keys=True),
                "native_tool_text":native_tool_text(tool_messages),
                "payload_bytes":[len(json.dumps(row["payload"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()) for row in rows if "payload" in row],
                "clipped_sources":[obj for row in rows if "payload" in row for obj in clipped_context_objects(row["payload"])],
                "count": len(rows), "rows": rows, "types": [row["type"] for row in rows],
                "targets": [row["target"] for row in rows if "target" in row],
                "canonical_text": json.dumps(rows, ensure_ascii=False, sort_keys=True)}
    raise InvalidEvidence("unknown artifact role " + label)

def resolve(sources, ref):
    if ref["source"] not in sources:
        raise InvalidEvidence("missing evidence source " + ref["source"])
    value = sources[ref["source"]]
    for key in ref["path"]:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and type(key) is int and 0 <= key < len(value):
            value = value[key]
        else:
            raise InvalidEvidence("missing observation path: " + repr(ref))
    return value

def equal(left, right):
    return type(left) is type(right) and left == right

def compare(left, op, right):
    if op == "eq":
        return equal(left, right)
    if op in ("contains", "not_contains"):
        if not isinstance(left, (str, list)):
            raise InvalidEvidence("contains needs text/list")
        present = right in left
        return present if op == "contains" else not present
    if op in ("gte","lte") and type(left) in (int, float) and type(right) in (int, float):
        return left >= right if op=="gte" else left <= right
    raise InvalidEvidence("unknown or ill-typed oracle comparison " + op)

def evaluate_case(case, evidence, root):
    required = set(case["evidence_required"])
    for assertion in case["assertions"]:
        if "other" in assertion:
            required.add(assertion["other"]["source"])
    if not case["assertions"] or set(evidence) != required:
        raise InvalidEvidence("missing/extra sources or zero assertions for " + case["id"])
    sources = {label: read_artifact(root, label, evidence[label]) for label in sorted(required)}
    assertions = []
    for ordinal, assertion in enumerate(case["assertions"], 1):
        left = resolve(sources, assertion)
        right = resolve(sources, assertion["other"]) if "other" in assertion else assertion["value"]
        assertions.append({"ordinal": ordinal, "pass": compare(left, assertion["op"], right),
                           "left": left, "right": right, "op": assertion["op"]})
    return {"case_id": case["id"], "status": "PASS" if all(a["pass"] for a in assertions) else "FAIL",
            "assertions": assertions}
