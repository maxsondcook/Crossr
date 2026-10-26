"""
Fit the colt breeding-value model (crossr_core/stud_value.py).

    scripts/pipeline/railway_env.sh crossr_dev .venv/bin/python scripts/train_stud_value.py [--save]

Reads stud_fees, breeding_seasons, race_horses and pedigrees from Postgres. Steps:

  1. Stallion table; impute initial fees for sons with none on file from their
     first-season book (fitted on sons whose fee is known).
  2. Outcome per stallion who started at stud 1999-2011: per-colt stud value of
     his sons (initial fee × 400 / colts), from crops old enough to reach stud.
  3. Two-part model per career stage (chance any son reaches stud; size if so) on
     initial fee + fee change by that stage. Candidates: cohort (first season) and
     pedigree-similar stallions' outcomes. A candidate is kept only if p < 0.01 and it
     improves held-out log-likelihood (train: started ≤ 2005, test: 2006-2011).
  4. Blend weight for a sire's own partial record, fitted on the held-out stallions.
  5. Backtest vs the sire's-sire rule the app used before.

--save writes the artifact to crossr_models (MODEL_NAME) and docs/stud-value-results.md.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy import special, stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crossr_core import stud_value as sv  # noqa: E402

P_KEEP = 0.01
OUTCOME_THROUGH = 2026
TRAIN_LAST_FIRST = 2005
TEST_FIRSTS = range(2006, 2012)
EVAL_STAGES = (2, 5, 8)
PEER_K = 15
ARTIFACT_FILE = ROOT / "Analyzed Sales" / "stud_value_model.json.gz"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ fitting
def fit_logit(X, y):
    b = np.zeros(X.shape[1])
    for _ in range(100):
        p = special.expit(X @ b)
        H = (X * (p * (1 - p))[:, None]).T @ X + 1e-8 * np.eye(len(b))
        step = np.linalg.solve(H, X.T @ (y - p))
        b += step
        if np.max(np.abs(step)) < 1e-10:
            break
    p = special.expit(X @ b)
    H = (X * (p * (1 - p))[:, None]).T @ X
    Hi = np.linalg.inv(H)
    S = X * (y - p)[:, None]
    se = np.sqrt(np.diag(Hi @ (S.T @ S) @ Hi))  # robust (HC0) SEs
    return b, se


def fit_ols(X, y):
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    r = y - X @ b
    XtXi = np.linalg.inv(X.T @ X)
    meat = (X * (r ** 2)[:, None]).T @ X
    n, k = X.shape
    se = np.sqrt(np.diag(XtXi @ meat @ XtXi) * n / (n - k))
    return b, se, float(np.std(r, ddof=k))


def two_part(X, v):
    pos = v > 0
    bz, sez = fit_logit(X, pos.astype(float))
    bp, sep, sig = fit_ols(X[pos], np.log(v[pos]))
    return {"bz": bz, "sez": sez, "bp": bp, "sep": sep, "sig": sig}


def two_part_ll(m, X, v):
    """Held-out log-likelihood per stallion: Bernoulli(any son) + lognormal density of size."""
    pos = v > 0
    p = np.clip(special.expit(X @ m["bz"]), 1e-9, 1 - 1e-9)
    ll = np.where(pos, np.log(p), np.log(1 - p))
    mu = X @ m["bp"]
    ll[pos] += stats.norm.logpdf(np.log(v[pos]), mu[pos], m["sig"]) - np.log(v[pos])
    return float(ll.mean())


def two_part_mean(m, X):
    return special.expit(X @ m["bz"]) * np.exp(X @ m["bp"] + m["sig"] ** 2 / 2)


# ------------------------------------------------------------------ pedigree
def pedigree_slots(keys):
    """name_key -> 5-generation ancestor slots, via the app's own pedigree code."""
    import main
    from crossr_core import horses

    out = {}
    for k in keys:
        try:
            tree = main.pedigree_tree(k)
        except Exception:
            tree = None
        if isinstance(tree, dict) and tree.get("Horse"):
            slots = horses._ancestor_slots(tree, {})
            if slots:
                out[k] = slots
    return out


def slot_similarity(a, b):
    from crossr_core import horses

    both = [p for p in a if p in b]
    if not both:
        return 0.0
    return 100.0 * sum(horses._slot_ids_match(a[p], b[p]) for p in both) / len(both)


def peer_feature(key, slots, pool_keys, pool_y):
    """Similarity-weighted mean log1p(value) of the PEER_K most pedigree-similar pool stallions."""
    me = slots.get(key)
    if not me:
        return None, []
    sims = []
    for pk, py in zip(pool_keys, pool_y):
        if pk == key or pk not in slots:
            continue
        s = slot_similarity(me, slots[pk])
        if s > 0:
            sims.append((s, pk, py))
    sims.sort(reverse=True)
    top = sims[:PEER_K]
    if not top:
        return None, []
    w = np.array([s for s, _, _ in top])
    return float(np.sum(w * np.array([y for *_, y in top])) / w.sum()), top


# ------------------------------------------------------------------ main
def main_() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--report", default=str(ROOT / "docs" / "stud-value-results.md"))
    args = ap.parse_args()

    from crossr_core import sample_db

    log("loading stud_fees, breeding_seasons, race_horses")
    fees = sample_db.stud_fee_history()
    table = sv.build_table(fees, sample_db.load_table("breeding_seasons"), sample_db.load_table("race_horses"))
    sons = sv.sons_index(table)
    log(f"stallions: {len(table):,}; with initial fee {sum(bool(sv.initial_fee(e)) for e in table.values()):,}")

    # 1. imputer
    xs, ys = [], []
    for e in table.values():
        isf, book = sv.initial_fee(e), e["bred"].get(e["first"], 0)
        if isf and book > 0:
            xs.append(math.log(book))
            ys.append(math.log(isf))
    b_imp, a_imp = np.polyfit(xs, ys, 1)
    sd_imp = float(np.std(np.array(ys) - (a_imp + b_imp * np.array(xs))))
    r_imp = float(np.corrcoef(xs, ys)[0, 1])
    impute = sv.Imputer(float(a_imp), float(b_imp), sd_imp)
    log(f"imputer: log ISF = {a_imp:.2f} + {b_imp:.2f} log(first-book mares), r={r_imp:.2f}, n={len(xs):,}")

    # 2. outcomes (first season 1999-2011; breeding data starts 1998, so earlier firsts are censored)
    keys, firsts, outcome = [], [], []
    for k, e in table.items():
        if not (1999 <= e["first"] <= 2011) or not sv.initial_fee(e):
            continue
        rec = sv.own_record(k, table, sons, impute, OUTCOME_THROUGH)
        if rec is None or rec["colts"] < 10:
            continue
        keys.append(k)
        firsts.append(e["first"])
        outcome.append(rec["value_per_colt"])
    firsts, v = np.array(firsts), np.array(outcome)
    tr, te = firsts <= TRAIN_LAST_FIRST, np.isin(firsts, list(TEST_FIRSTS))
    log(f"outcome stallions: {len(v):,} (train {tr.sum()}, test {te.sum()}); any son at stud {np.mean(v > 0):.0%}; "
        f"median ${np.median(v):,.0f}, mean ${v.mean():,.0f}")

    # pedigree candidate (outcome pool = the outcome stallions; feature excludes self)
    log("pedigree slots for outcome stallions")
    slots = pedigree_slots(keys)
    y1 = np.log1p(v)
    ped = np.full(len(v), np.nan)
    for i, k in enumerate(keys):
        # only stallions that started earlier, so the feature is knowable at his own start
        pool = [(kk, yy) for kk, yy, ff in zip(keys, y1, firsts) if ff <= firsts[i] - 2]
        val, _ = peer_feature(k, slots, [p for p, _ in pool], [y for _, y in pool])
        if val is not None:
            ped[i] = val
    has_ped = ~np.isnan(ped)
    log(f"pedigree feature available for {has_ped.sum()} of {len(v)} stallions")

    def design(stage, cols, mask):
        rows = []
        for k, m in zip(keys, mask):
            if not m:
                continue
            f = sv.features(table[k], stage)
            rows.append([1.0, f["log_isf"], f["fee_change"]] + ([f["cohort"]] if "cohort" in cols else []))
        X = np.array(rows)
        if "pedigree" in cols:
            X = np.column_stack([X, ped[mask]])
        return X

    # 3. candidate selection (pooled over EVAL_STAGES)
    def evaluate(cols, base_mask):
        ll, rho, pvals = [], [], []
        for t in EVAL_STAGES:
            m = two_part(design(t, cols, base_mask & tr), v[base_mask & tr])
            Xt = design(t, cols, base_mask & te)
            ll.append(two_part_ll(m, Xt, v[base_mask & te]))
            rho.append(stats.spearmanr(two_part_mean(m, Xt), v[base_mask & te]).statistic)
            full = two_part(design(t, cols, base_mask), v[base_mask])
            pvals.append(full)
        return float(np.mean(ll)), float(np.mean(rho)), pvals

    def last_p(full_fits):
        # p-value of the last column in either part, worst (largest) across stages
        ps = []
        for f in full_fits:
            pz = 2 * stats.norm.sf(abs(f["bz"][-1] / f["sez"][-1]))
            pp = 2 * stats.norm.sf(abs(f["bp"][-1] / f["sep"][-1]))
            ps.append(min(pz, pp))
        return max(ps)

    allm = np.ones(len(v), bool)
    chosen = ["isf", "fee_change"]
    ll0, rho0, _ = evaluate(chosen, allm)
    log(f"base (initial fee + fee change): held-out ll {ll0:.4f}, spearman {rho0:.3f}")
    selection = [{"candidate": "base", "ll": ll0, "spearman": rho0}]
    ll_c, rho_c, fits_c = evaluate(chosen + ["cohort"], allm)
    p_c = last_p(fits_c)
    keep_cohort = bool(p_c < P_KEEP and ll_c > ll0)
    selection.append({"candidate": "+cohort", "ll": ll_c, "spearman": rho_c, "p": p_c, "kept": keep_cohort})
    log(f"+cohort: ll {ll_c:.4f} spearman {rho_c:.3f} p={p_c:.2g} -> {'keep' if keep_cohort else 'drop'}")
    if keep_cohort:
        chosen.append("cohort")
    ref_ll, ref_rho, _ = evaluate(chosen, has_ped)
    ll_p, rho_p, fits_p = evaluate(chosen + ["pedigree"], has_ped)
    p_p = last_p(fits_p)
    keep_ped = bool(p_p < P_KEEP and ll_p > ref_ll)
    selection.append({"candidate": "+pedigree similarity", "ll": ll_p, "spearman": rho_p, "p": p_p,
                      "ref_ll": ref_ll, "ref_spearman": ref_rho, "n": int(has_ped.sum()), "kept": keep_ped})
    log(f"+pedigree (n={has_ped.sum()}): ll {ll_p:.4f} vs {ref_ll:.4f}, spearman {rho_p:.3f} vs {ref_rho:.3f}, "
        f"p={p_p:.2g} -> {'keep' if keep_ped else 'drop'}")
    if keep_ped:
        log("pedigree kept: runtime support not implemented yet; stopping")
        raise SystemExit(2)

    # backtest vs sire's-sire rule (sire's own per-colt value as known at the stallion's first season)
    bt = []
    for t in EVAL_STAGES:
        m = two_part(design(t, chosen, tr), v[tr])
        pred = two_part_mean(m, design(t, chosen, te))
        gs = []
        for k in np.array(keys)[te]:
            s = table[k]["sire"]
            rec = sv.own_record(s, table, sons, impute, table[k]["first"]) if s in table else None
            gs.append(rec["value_per_colt"] if rec else np.nan)
        gs = np.array(gs)
        ok = ~np.isnan(gs)
        bt.append({
            "stage": t, "n": int(te.sum()),
            "spearman": float(stats.spearmanr(pred, v[te]).statistic),
            "p": float(stats.spearmanr(pred, v[te]).pvalue),
            "calibration": float(pred.sum() / v[te].sum()),
            "sire_rule_n": int(ok.sum()),
            "sire_rule_spearman": float(stats.spearmanr(gs[ok], v[te][ok]).statistic) if ok.sum() > 5 else None,
            "sire_rule_p": float(stats.spearmanr(gs[ok], v[te][ok]).pvalue) if ok.sum() > 5 else None,
        })
        log(f"backtest stage {t}: spearman {bt[-1]['spearman']:.3f} (p={bt[-1]['p']:.1g}), pred/actual {bt[-1]['calibration']:.2f}; "
            f"sire's-sire rule spearman {bt[-1]['sire_rule_spearman']} (n={ok.sum()})")

    # 4. own-record blend weight: partial record at first+10 vs final value, held-out stallions
    best = None
    partial, final, model_pred = [], [], []
    m10 = two_part(design(10, chosen, tr), v[tr])
    for i in np.flatnonzero(te):
        k = keys[i]
        rec = sv.own_record(k, table, sons, impute, table[k]["first"] + 10)
        if rec is None or rec["colts"] <= 0:
            continue
        partial.append((rec["value_per_colt"], rec["colts"]))
        final.append(v[i])
        model_pred.append(float(two_part_mean(m10, design(10, chosen, np.arange(len(v)) == i))[0]))
    final, model_pred = np.array(final), np.array(model_pred)
    for k_own in (1, 5, 10, 25, 50, 100, 200, 400, 800, 1600, 3200):
        w = np.array([c / (c + k_own) for _, c in partial])
        blend = w * np.array([pv for pv, _ in partial]) + (1 - w) * model_pred
        err = float(np.mean(np.abs(np.log1p(blend) - np.log1p(final))))
        if best is None or err < best[1]:
            best = (k_own, err)
    own_k = float(best[0])
    log(f"own-record blend: k={own_k:.0f} colts (held-out MAE log1p {best[1]:.3f}, n={len(final)})")

    # 5. final per-stage fits on all outcome stallions
    stages, sig_rows = {}, {}
    names = ["intercept", "log_isf", "fee_change"] + (["cohort"] if "cohort" in chosen else [])
    for t in range(1, sv.MAX_STAGE + 1):
        m = two_part(design(t, chosen, allm), v)
        stages[str(t)] = {
            "any": dict(zip(names, map(float, m["bz"]))),
            "size": dict(zip(names, map(float, m["bp"]))),
            "sigma": m["sig"],
        }
        sig_rows[t] = m
    log(f"stage 5 any-son: {dict(zip(names, np.round(sig_rows[5]['bz'], 3)))}; size: {dict(zip(names, np.round(sig_rows[5]['bp'], 3)))}")

    if not args.save:
        return

    # artifact: every stallion with his own record as of now and nearest comparables
    # latest breeding season on file (fee lists already advertise next year's fees)
    year_now = max(max(e["bred"] or {0: 0}) for e in table.values())
    pool = [(k, own) for k in table for own in [sv.own_record(k, table, sons, impute, year_now)]
            if own and own["colts"] >= 50 and sv.initial_fee(table[k])]
    pool_feats = {
        t: [(pk, pf, pown) for pk, pown in pool for pf in [sv.features(table[pk], t)] if pf]
        for t in range(1, sv.MAX_STAGE + 1)
    }
    stallions = {}
    for k, e in table.items():
        own = sv.own_record(k, table, sons, impute, year_now)
        entry = {"first": e["first"], "fees": {str(y): f for y, f in e["fees"].items()}, "sire": e["sire"],
                 "own": own if own and own["colts"] >= 10 else None}
        f = sv.features(e, max(1, min(year_now - e["first"], sv.MAX_STAGE)))
        if f:
            # nearest comparable stallions: same initial fee and fee path at the same career stage
            stage = max(1, min(year_now - e["first"], sv.MAX_STAGE))
            dists = [
                (math.hypot(pf["log_isf"] - f["log_isf"], pf["fee_change"] - f["fee_change"]), pk, pown)
                for pk, pf, pown in pool_feats[stage]
                if pk != k
            ]
            dists.sort(key=lambda x: x[0])
            entry["comparables"] = [
                {"stallion": pk, "initial_fee": sv.initial_fee(table[pk]),
                 "fee_at_stage": sv.fee_at(table[pk], table[pk]["first"] + stage),
                 "value_per_colt": round(pown["value_per_colt"]), "sons_at_stud": pown["sons_at_stud"]}
                for _, pk, pown in dists[:5]
            ]
        stallions[k] = entry
    artifact = {
        "version": 1, "trained_at": time.strftime("%Y-%m-%d"), "year_now": year_now,
        "multiplier": sv.STUD_DEAL_MULTIPLIER, "features": names, "stages": stages, "own_k": own_k,
        "imputer": {"a": impute.a, "b": impute.b, "sd": impute.sd, "r": r_imp, "n": len(xs)},
        "selection": selection, "backtest": bt, "stallions": stallions,
    }
    from crossr_core import railway_db

    railway_db.save_model(sv.MODEL_NAME, artifact)
    # local copy so scripts/load_railway.py --only models can publish it to production
    import gzip
    import json

    with gzip.open(ARTIFACT_FILE, "wt", encoding="utf-8") as fh:
        json.dump(artifact, fh, separators=(",", ":"))
    log(f"saved {sv.MODEL_NAME} ({len(stallions):,} stallions) to crossr_models and {ARTIFACT_FILE.name}")
    write_report(Path(args.report), artifact, sig_rows, names, len(v))


def write_report(path, art, fits, names, n_out):
    L = ["# Colt breeding value — generated results", "",
         f"Generated by `scripts/train_stud_value.py` on {art['trained_at']}. Method: `docs/stud-value.md`.", "",
         f"Outcome stallions (started at stud 1999–2011): {n_out}. Value per colt = Σ sons' initial fee × "
         f"{art['multiplier']} / colts in crops ≥ {sv.MATURE_CROP_AGE} years old.", "",
         f"Initial fee imputed from first-season book for sons with none on file: log ISF = "
         f"{art['imputer']['a']:.2f} + {art['imputer']['b']:.2f}·log(mares), r = {art['imputer']['r']:.2f} (n = {art['imputer']['n']:,}).", "",
         "## Candidate selection (held-out: started 2006–2011, trained on ≤ 2005)", "",
         "| Candidate | Held-out log-lik | Spearman | p | Kept |", "|---|---|---|---|---|"]
    for s in art["selection"]:
        L.append(f"| {s['candidate']} | {s['ll']:.4f} | {s['spearman']:.3f} | {s.get('p', float('nan')):.2g} | {s.get('kept', '—')} |")
    L += ["", "## Backtest", "", "| Stage | n | Spearman | p | Predicted / actual total | Sire's-sire rule Spearman (n) |",
          "|---|---|---|---|---|---|"]
    for b in art["backtest"]:
        sr = "—" if b["sire_rule_spearman"] is None else f"{b['sire_rule_spearman']:.3f} ({b['sire_rule_n']})"
        L.append(f"| {b['stage']} | {b['n']} | {b['spearman']:.3f} | {b['p']:.1g} | {b['calibration']:.2f} | {sr} |")
    L += ["", f"Own-record blend: weight = colts / (colts + {art['own_k']:.0f}).", "",
          "## Coefficients (stage 5, robust SEs)", "", "| Part | Feature | Coef | SE | p |", "|---|---|---|---|---|"]
    m = fits[5]
    for part, b, se in (("any son at stud (logit)", m["bz"], m["sez"]), ("size if any (log $)", m["bp"], m["sep"])):
        for n, c, s in zip(names, b, se):
            L.append(f"| {part} | {n} | {c:+.3f} | {s:.3f} | {2 * stats.norm.sf(abs(c / s)):.2g} |")
    path.write_text("\n".join(L) + "\n")
    log(f"wrote {path}")


if __name__ == "__main__":
    main_()
