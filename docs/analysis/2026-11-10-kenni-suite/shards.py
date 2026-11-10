import xml.etree.ElementTree as ET, collections, os, json, sys
S = sys.argv[1]; B = "/home/user/kenni/backend/"
T = collections.Counter(); lost = 0.0
for c in ET.parse(S + "/junit3.xml").getroot().iter("testcase"):
    p = c.get("classname").split(".")
    f = None
    for k in range(len(p), 1, -1):
        cand = "/".join(p[:k]) + ".py"
        if os.path.isfile(B + cand):
            f = cand; break
    t = float(c.get("time") or 0)
    if f is None:
        lost += t; continue
    parts = f.split("/")
    unit = "/".join(parts[:3]) if len(parts) > 3 else f
    T[unit] += t
groups = [[0.0, []] for _ in range(4)]
for unit, t in sorted(T.items(), key=lambda x: -x[1]):
    g = min(groups, key=lambda g: g[0]); g[0] += t; g[1].append(unit)
allu = [u for g in groups for u in g[1]]
overlap = [u for u in allu if any(v != u and u.startswith(v + "/") for v in allu)]
for i, (t, units) in enumerate(groups, 1):
    open(f"{S}/shard{i}.txt", "w").write(" ".join(sorted(units)))
    print("shard", i, "test time", round(t), "s, units", len(units))
print("units", len(T), "overlapping", len(overlap), "unassigned time", round(lost), "missing", sum(not os.path.exists(B + u) for u in allu))
