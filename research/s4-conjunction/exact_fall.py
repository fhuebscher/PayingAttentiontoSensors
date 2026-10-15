#!/usr/bin/env python3
"""Exact f_all optimum per budget k over the R(p) sets in relevance.json (post-hoc, not part of AMENDMENT_1 section 4).

An optimal S of size <= k can be replaced by the union of the R sets it covers, so the optimum is the best union of
R sets with |union| <= k. This enumerates the closure of such unions (BFS, no pruning by search order).
    /usr/bin/python3 -B research/s4-conjunction/exact_fall.py tmp/s4-relevance/20260927T102324Z/relevance.json
    /usr/bin/python3 -B research/s4-conjunction/exact_fall.py --self-check
"""
import itertools
import json
import random
import sys
from collections import Counter

K = 8


def exact(sets, K=K):
    mult = Counter(frozenset(s) for s in sets if s)
    small = [s for s in mult if len(s) <= K]
    seen, frontier = {frozenset()}, [frozenset()]
    while frontier:
        nxt = []
        for U in frontier:
            for s in small:
                V = U | s
                if len(V) <= K and V not in seen:
                    seen.add(V); nxt.append(V)
        frontier = nxt
    best = {k: 0 for k in range(1, K + 1)}
    for U in seen:
        if U:
            v = sum(m for s, m in mult.items() if s <= U)
            for k in range(len(U), K + 1):
                best[k] = max(best[k], v)
    return best


def brute(sets, K):
    univ = sorted(set().union(*sets))
    best = {k: 0 for k in range(1, K + 1)}
    for k in range(1, K + 1):
        for S in itertools.combinations(univ, min(k, len(univ))):
            S = set(S)
            best[k] = max(best[k], sum(1 for s in sets if s and set(s) <= S))
    return best


def self_check():
    rng = random.Random(7)
    for _ in range(200):
        sets = [set(rng.sample(range(7), rng.randint(0, 4))) for _ in range(rng.randint(1, 9))]
        assert exact(sets, 5) == brute(sets, 5), sets
    print("self-check: exact == brute force on 200 random instances")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check(); sys.exit(0)
    d = json.load(open(sys.argv[1]))
    for gen, g in d["generations"].items():
        eps = g.get("R", {}).get("episodes")
        if eps:
            print(gen, "episodes", len(eps), "exact f_all per k:", exact([e["R"] for e in eps]))
