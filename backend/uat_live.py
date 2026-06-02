"""
End-to-end live UAT — exercises every Phase 7/8/11/12 surface as an end user.

Run:
  INSNAV_UAT_BASE=https://...  INSNAV_UAT_EMAIL=...  INSNAV_UAT_PASSWORD=...  python uat_live.py

Stdlib only (urllib) so it runs anywhere. Prints PASS/FAIL per check and a summary.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = os.environ["INSNAV_UAT_BASE"].rstrip("/")
EMAIL = os.environ["INSNAV_UAT_EMAIL"]
PASSWORD = os.environ["INSNAV_UAT_PASSWORD"]

_PASS = 0
_FAIL = 0
_TOKEN: str | None = None


def _req(method: str, path: str, body: dict | None = None, auth: bool = True) -> tuple[int, dict | list | str]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if auth and _TOKEN:
        req.add_header("Authorization", f"Bearer {_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
            try:
                return r.status, json.loads(txt)
            except json.JSONDecodeError:
                return r.status, txt
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try:
            return e.code, json.loads(txt)
        except json.JSONDecodeError:
            return e.code, txt


def check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def main() -> int:
    global _TOKEN
    print(f"UAT against {BASE}\n")

    # /healthz is shadowed by Google's Front End on *.run.app → use the /health alias.
    st, body = _req("GET", "/health", auth=False)
    check("health", st == 200 and isinstance(body, dict) and body.get("status") == "ok", str(body)[:200])
    if isinstance(body, dict):
        print(f"        version={body.get('version')}")

    st, body = _req("POST", "/v1/auth/login", {"email": EMAIL, "password": PASSWORD}, auth=False)
    check("login", st == 200 and isinstance(body, dict) and "access_token" in body, str(body)[:200])
    if not (isinstance(body, dict) and body.get("access_token")):
        print("\nCannot continue without a token.")
        return 1
    _TOKEN = body["access_token"]

    st, projects = _req("GET", "/v1/projects")
    check("list projects", st == 200 and isinstance(projects, list), str(projects)[:200])
    if not isinstance(projects, list) or not projects:
        print("\nNo projects to UAT against.")
        return 1

    # Pick a project whose pivot/fields returns at least one measure (has a cube).
    pid = None
    measure = dim = None
    for p in projects:
        st, fields = _req("GET", f"/v1/pivot/fields?project_id={p['id']}")
        if st == 200 and isinstance(fields, dict) and fields.get("measures"):
            pid = p["id"]
            measure = fields["measures"][0]["name"]
            dims = fields.get("dimensions") or []
            dim = dims[0]["name"] if dims else None
            print(f"\n  using project '{p['name']}' ({pid})  measure={measure}  dim={dim}")
            break
    check("found a project with a cube", pid is not None)
    if pid is None:
        return 1

    # Phase 7 — pivot query
    st, res = _req("POST", "/v1/pivot/query",
                   {"project_id": pid, "measures": [measure], "dimensions": [dim] if dim else []})
    check("pivot query", st == 200 and isinstance(res, dict) and "rows" in res, str(res)[:200])

    # Phase 11 #4 — cost estimate
    st, est = _req("POST", "/v1/pivot/estimate", {"project_id": pid, "measures": [measure]})
    check("cost estimate", st == 200 and isinstance(est, dict) and "estimated_gb" in est, str(est)[:200])
    if isinstance(est, dict):
        print(f"        ~{est.get('estimated_gb')} GB  exceeds={est.get('exceeds_threshold')}")

    # Phase 11 #8 — metric registry
    st, reg = _req("GET", f"/v1/metrics?project_id={pid}")
    check("metric registry", st == 200 and isinstance(reg, dict) and reg.get("metrics"), str(reg)[:200])

    # Phase 11 #1 — lineage
    st, trace = _req("GET", f"/v1/lineage?project_id={pid}&field={measure}")
    check("lineage trace", st == 200 and isinstance(trace, dict) and "source_columns" in trace, str(trace)[:200])

    # Phase 11 #6 — notebook export
    st, nb = _req("POST", "/v1/notebook", {"project_id": pid, "measures": [measure]})
    check("notebook export", st == 200 and isinstance(nb, dict) and nb.get("nbformat") == 4, str(nb)[:120])

    # Phase 8 — dashboards (create → pin → run)
    st, dash = _req("POST", "/v1/dashboards", {"project_id": pid, "name": "UAT dashboard"})
    ok = st in (200, 201) and isinstance(dash, dict) and dash.get("id")
    check("create dashboard", ok, str(dash)[:160])
    if ok:
        did = dash["id"]
        st, _ = _req("POST", f"/v1/dashboards/{did}/tiles",
                     {"title": "UAT tile", "spec": {"measures": [measure], "dimensions": [dim] if dim else []}})
        check("pin tile", st in (200, 201), str(st))
        st, run = _req("POST", f"/v1/dashboards/{did}/run", {})
        check("run dashboard", st == 200 and isinstance(run, dict) and "tiles" in run, str(run)[:120])
        st, shared = _req("POST", f"/v1/dashboards/{did}/share", {})
        check("share dashboard", st == 200 and isinstance(shared, dict) and shared.get("share_token"), str(shared)[:120])
        if isinstance(shared, dict) and shared.get("share_token"):
            st, pub = _req("GET", f"/v1/public/dashboards/{shared['share_token']}", auth=False)
            check("public dashboard (no auth)", st == 200, str(st))

    # Phase 11 #2 — cohorts (need a dim with values; just create + resolve a single-segment expr)
    if dim:
        st, seg = _req("POST", "/v1/cohorts",
                       {"project_id": pid, "name": "UAT_seg", "cube": dim.rsplit(".", 1)[0],
                        "filters": [{"member": dim, "operator": "set", "values": []}]})
        ok = st in (200, 201) and isinstance(seg, dict) and seg.get("id")
        check("create cohort segment", ok, str(seg)[:160])
        if ok:
            st, rr = _req("POST", "/v1/cohorts/resolve",
                          {"project_id": pid, "expression": "UAT_seg", "measures": [measure],
                           "dimensions": [dim]})
            check("resolve cohort", st == 200 and isinstance(rr, dict) and "filter_tree" in rr, str(rr)[:160])
            _req("DELETE", f"/v1/cohorts/{seg['id']}")

    # Phase 11 #3 — snapshots (capture twice → diff)
    st, s1 = _req("POST", "/v1/snapshots", {"project_id": pid, "label": "a", "spec": {"measures": [measure]}})
    st2, s2 = _req("POST", "/v1/snapshots", {"project_id": pid, "label": "b", "spec": {"measures": [measure]}})
    ok = (st in (200, 201) and st2 in (200, 201) and isinstance(s1, dict) and isinstance(s2, dict))
    check("capture snapshots", ok, f"{st}/{st2}")
    if ok:
        st, diff = _req("POST", "/v1/snapshots/diff", {"a": s1["id"], "b": s2["id"]})
        check("diff snapshots", st == 200 and isinstance(diff, dict) and "diff" in diff, str(diff)[:120])

    # Phase 11 #5 — assumptions
    st, rep = _req("POST", "/v1/assumptions/check", {"project_id": pid, "spec": {"measures": [measure]}})
    check("assumption check", st == 200 and isinstance(rep, dict) and "warnings" in rep, str(rep)[:160])

    # Phase 12 — x-ray
    st, sug = _req("POST", "/v1/xray/suggest", {"project_id": pid})
    check("xray suggest", st == 200 and isinstance(sug, list) and len(sug) >= 1, str(sug)[:120])
    st, xd = _req("POST", "/v1/xray/dashboard", {"project_id": pid, "name": "UAT starter"})
    check("xray dashboard", st == 200 and isinstance(xd, dict) and xd.get("tile_count", 0) >= 1, str(xd)[:120])

    # Phase 11 #7 — causal guardrail (should REFUSE without a strategy)
    st, ans = _req("POST", "/v1/chat", {"project_id": pid, "question": "Did the discount cause higher revenue?"})
    check("causal guardrail refuses", st == 200 and isinstance(ans, dict) and ans.get("kind") == "refuse",
          str(ans)[:160])
    # And a causal question WITH a strategy should NOT refuse on guardrail grounds
    st, ans2 = _req("POST", "/v1/chat",
                    {"project_id": pid,
                     "question": "Effect of the discount on revenue via difference-in-differences"})
    check("causal w/ strategy not guardrail-refused",
          st == 200 and isinstance(ans2, dict) and not (
              ans2.get("kind") == "refuse" and "identification strategy" in " ".join(ans2.get("caveats", [])).lower()),
          str(ans2)[:160])

    print(f"\n==== UAT: {_PASS} passed, {_FAIL} failed ====")
    return 0 if _FAIL == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
