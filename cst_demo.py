#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compressed Symmetry Theory — demo program

This script expresses the core ideas with a concrete finite group:
C4, the 90° rotation group acting on n×n binary grids.

What it shows
- SMI_G(X):  mutual information between X and g·X (with g uniform in G).
- SCI_G:     compression gain from orbit-canonicalization (equivariant code).
- Orbit speedup: expected evaluation reduction when searching over orbit reps.

No third‑party libraries required.
"""

import argparse, math, random, zlib, statistics
from collections import defaultdict, Counter
from typing import Tuple, List

# ------------------------------
# Group action on n×n binary grids
# ------------------------------

def rotate90_indices(n: int) -> List[int]:
    """Return index map for 90° clockwise rotation on an n×n grid stored row-major.
       If x is a flat tuple/list of length n*n, then rot90(x)[i] = x[map[i]]."""
    m = []
    for r in range(n):
        for c in range(n):
            # New position (r,c) takes from old (n-1-c, r)
            src_r, src_c = n - 1 - c, r
            m.append(src_r*n + src_c)
    return m

def apply_map(vec: Tuple[int, ...], index_map: List[int]) -> Tuple[int, ...]:
    return tuple(vec[i] for i in index_map)

def rotate(vec: Tuple[int, ...], n: int, k: int, rot90_map: List[int]) -> Tuple[int, ...]:
    out = vec
    for _ in range(k % 4):
        out = apply_map(out, rot90_map)
    return out

def int_to_bits(n: int, bits: int) -> Tuple[int, ...]:
    return tuple((n >> (bits-1-i)) & 1 for i in range(bits))

def bits_to_int(bits: Tuple[int, ...]) -> int:
    v = 0
    for b in bits:
        v = (v << 1) | (b & 1)
    return v

def canonical_representative(x: Tuple[int, ...], n: int, rot90_map: List[int]) -> Tuple[int, ...]:
    """Lexicographically minimal rotation among {0,90,180,270} applied to x."""
    candidates = [x]
    out = x
    cur = x
    for _ in range(3):
        cur = apply_map(cur, rot90_map)
        candidates.append(cur)
    return min(candidates)

def orbit_size(x: Tuple[int, ...], n: int, rot90_map: List[int]) -> int:
    s = set()
    cur = x
    for k in range(4):
        s.add(bits_to_int(cur))
        cur = apply_map(cur, rot90_map)
    return len(s)

# ------------------------------
# Probability models and sampling
# ------------------------------

def sample_grid(n: int, p: float) -> Tuple[int, ...]:
    """Sample an n×n binary grid with independent Bernoulli(p) pixels."""
    return tuple(1 if random.random() < p else 0 for _ in range(n*n))

# ------------------------------
# Mutual information (SMI) estimation
# ------------------------------

def empirical_mi(pairs: List[Tuple[int, int]]) -> float:
    """Estimate I(X;Y) in bits from empirical pairs of ints using plug-in estimator."""
    N = len(pairs)
    cx = Counter(x for x, _ in pairs)
    cy = Counter(y for _, y in pairs)
    cxy = Counter(pairs)
    mi = 0.0
    for (x,y), nxy in cxy.items():
        px = cx[x] / N
        py = cy[y] / N
        pxy = nxy / N
        mi += pxy * math.log2(pxy/(px*py))
    return mi

def exact_smi_uniform_3x3() -> float:
    """Exactly compute I(X; g·X) for 3×3 grids, X uniform on {0,1}^{9}, g uniform in C4."""
    n = 3
    rot90_map = rotate90_indices(n)
    px = 1.0 / (2**(n*n))
    pg = 1/4
    # joint over states encoded as ints
    from collections import defaultdict
    pxy = defaultdict(float)
    for x_int in range(2**(n*n)):
        x = int_to_bits(x_int, n*n)
        for k in range(4):
            y = rotate(x, n, k, rot90_map)
            y_int = bits_to_int(y)
            pxy[(x_int, y_int)] += px * pg
    # marginals
    py = defaultdict(float)
    for (x,y), p in pxy.items():
        py[y] += p
    # px is uniform
    px_val = px
    mi = 0.0
    for (x,y), p in pxy.items():
        mi += p * math.log2(p/(px_val*py[y]))
    return mi

# ------------------------------
# Compression-based SCI
# ------------------------------

def compress_length_bytes(data: bytes, level: int = 9) -> int:
    return len(zlib.compress(data, level))

def sci_via_compression(samples: List[Tuple[int, ...]], n: int, rot90_map: List[int]) -> float:
    """Return estimated SCI in bits per sample using zlib compression.
       Baseline encodes raw grids; equivariant encodes orbit-canonical reps."""
    # Pack each grid into a fixed number of bytes
    bits = n*n
    bytes_per = (bits + 7) // 8
    raw = bytearray()
    canon = bytearray()
    for x in samples:
        xi = bits_to_int(x)
        ci = bits_to_int(canonical_representative(x, n, rot90_map))
        raw += xi.to_bytes(bytes_per, 'big')
        canon += ci.to_bytes(bytes_per, 'big')
    L_raw = compress_length_bytes(bytes(raw), level=9)
    L_canon = compress_length_bytes(bytes(canon), level=9)
    gain_bits_per_sample = (L_raw - L_canon) * 8.0 / len(samples)
    return gain_bits_per_sample

# ------------------------------
# Search speedup demo
# ------------------------------

def invariant_cost(x: Tuple[int, ...], n: int) -> int:
    """A rotation-invariant 'cost': count of 1s modulo 5 (toy)."""
    return sum(x) % 5

def brute_force_search(samples: List[Tuple[int, ...]], n: int) -> Tuple[int, int]:
    """Return (evals_raw, evals_orbit) needed to find the min cost,
       when we evaluate either every sample or only one rep per orbit."""
    rot90_map = rotate90_indices(n)
    best = None
    # Raw: evaluate all
    evals_raw = 0
    for x in samples:
        c = invariant_cost(x, n)
        evals_raw += 1
        if best is None or c < best:
            best = c
            if best == 0:
                break
    # Orbit: evaluate canonical reps only
    seen = set()
    evals_orbit = 0
    best2 = None
    for x in samples:
        rep = canonical_representative(x, n, rot90_map)
        rep_int = bits_to_int(rep)
        if rep_int in seen:
            continue
        seen.add(rep_int)
        c = invariant_cost(rep, n)
        evals_orbit += 1
        if best2 is None or c < best2:
            best2 = c
            if best2 == 0:
                break
    return evals_raw, evals_orbit

# ------------------------------
# Main CLI
# ------------------------------

def main():
    ap = argparse.ArgumentParser(description="Compressed Symmetry Theory demo (finite rotations on binary grids).")
    ap.add_argument("--n", type=int, default=3, help="grid size n (default: 3)")
    ap.add_argument("--p", type=float, default=0.5, help="Bernoulli(p) for pixels (default: 0.5)")
    ap.add_argument("--samples", type=int, default=50000, help="number of samples for empirical estimates (default: 50k)")
    ap.add_argument("--seed", type=int, default=42, help="PRNG seed")
    args = ap.parse_args()

    random.seed(args.seed)
    n = args.n
    rot90_map = rotate90_indices(n)

    print("\n=== Compressed Symmetry Theory (C4 rotations on n×n binary grids) ===")
    print(f"- grid size: {n}×{n}, Bernoulli(p={args.p}) pixels, samples: {args.samples}")

    # 1) SMI: I(X; g·X)
    pairs = []
    for _ in range(args.samples):
        x = sample_grid(n, args.p)
        g = random.randrange(4)  # uniform in C4
        y = rotate(x, n, g, rot90_map)
        pairs.append((bits_to_int(x), bits_to_int(y)))
    mi_emp = empirical_mi(pairs)
    print(f"- Empirical SMI  I(X; g·X)  ≈ {mi_emp:.5f} bits per sample")

    if n == 3 and abs(args.p - 0.5) < 1e-12:
        mi_exact = exact_smi_uniform_3x3()
        print(f"  (Exact SMI for 3×3, p=0.5) = {mi_exact:.6f} bits per sample")

    # 2) SCI via compression difference
    samples = [sample_grid(n, args.p) for _ in range(args.samples)]
    sci_est = sci_via_compression(samples, n, rot90_map)
    print(f"- Compression SCI gain (zlib) ≈ {sci_est:.5f} bits per sample")

    # 3) Orbit statistics
    # Estimate average orbit size over an IID draw; for finite space we can also do exact for n=3
    # Here we do empirical from the sample.
    sizes = []
    for x in samples[:min(2000, len(samples))]:
        sizes.append(orbit_size(x, n, rot90_map))
    avg_orbit = statistics.mean(sizes)
    print(f"- Empirical average orbit size ≈ {avg_orbit:.4f} (max 4)")

    # 4) Search speedup demo (toy invariant cost)
    evals_raw, evals_orbit = brute_force_search(samples, n)
    if evals_orbit == 0:
        speed = float('inf')
    else:
        speed = evals_raw / evals_orbit
    print(f"- Orbit-restricted search used {evals_orbit} evals vs {evals_raw} raw ⇒ speedup ≈ {speed:.3f}×")

    print("\nInterpretation")
    print("- SMI measures the information shared between X and a random rotated view g·X.")
    print("- SCI (compression gain) measures how many bits you save by encoding only the orbit (canonical rep).")
    print("- The speedup shows that when the cost is rotation-invariant, you only need one evaluation per orbit.\n")

if __name__ == "__main__":
    main()
