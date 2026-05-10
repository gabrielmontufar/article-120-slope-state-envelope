"""
Reproducible demonstration for article 120.

The script creates a synthetic, transparent slope-stability example for a
rainfall-infiltrated slope with cracks and vegetation. It is not a field
calibration. The contribution is the state-conditioned temporal reliability
workflow and the derived decision metrics:

- Hydro-mechanical memory index (HMMI)
- Crack-root compensation factor (CRCF)
- State-conditioned rainfall threshold envelope
"""

from __future__ import annotations

from pathlib import Path
from statistics import NormalDist

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "computational_package"
FIG = OUT / "figures"
DATA = OUT / "data"

SEED = 120
N_MONTE_CARLO = 30_000


SCENARIOS = {
    "Bare slope": {},
    "Cracked slope": {"crack": 1},
    "Vegetated slope": {"veg": 1, "interception": 0.20, "drain_factor": 1.28},
    "Cracked vegetated slope": {
        "crack": 1,
        "veg": 1,
        "interception": 0.20,
        "drain_factor": 1.28,
    },
    "Road surcharge and clogged drain": {
        "crack": 1,
        "infrastructure": 1,
        "surcharge_kpa": 10.0,
        "runoff_concentration": 0.28,
        "drain_factor": 0.72,
    },
    "Road surcharge with maintained drainage": {
        "crack": 1,
        "veg": 1,
        "infrastructure": 1,
        "surcharge_kpa": 10.0,
        "runoff_concentration": -0.12,
        "interception": 0.16,
        "drain_factor": 1.55,
    },
}


def scenario_value(scenario: dict, key: str, default: float = 0.0) -> float:
    return float(scenario[key]) if key in scenario else default


def rainfall_series(t: np.ndarray, scale: float = 1.0, duration_scale: float = 1.0) -> np.ndarray:
    """Piecewise storm intensity in mm/h."""
    rain = np.zeros_like(t, dtype=float)
    rain[(t >= 0) & (t < 6)] = 5.0
    rain[(t >= 6) & (t < 18 * duration_scale)] = 24.0
    rain[(t >= 18 * duration_scale) & (t < 30 * duration_scale)] = 14.0
    rain[(t >= 30 * duration_scale) & (t < 42 * duration_scale)] = 3.0
    return scale * rain


def deterministic_parameters() -> dict[str, np.ndarray]:
    return {
        "beta_deg": np.array([32.0]),
        "z": np.array([2.10]),
        "c": np.array([8.00]),
        "phi_deg": np.array([33.0]),
        "phi_b_deg": np.array([16.0]),
        "s0": np.array([32.0]),
        "ks": np.array([7.50]),
        "gamma_d": np.array([17.0]),
        "gamma_sat": np.array([20.0]),
        "root_c": np.array([5.00]),
        "crack_depth": np.array([0.75]),
    }


def random_parameters(n: int = N_MONTE_CARLO, seed: int = SEED) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    return {
        "beta_deg": np.clip(rng.normal(32.0, 2.0, n), 26.0, 39.0),
        "z": np.clip(rng.normal(2.10, 0.22, n), 1.50, 2.80),
        "c": rng.lognormal(np.log(8.0) - 0.5 * 0.25**2, 0.25, n),
        "phi_deg": np.clip(rng.normal(33.0, 2.0, n), 27.0, 39.0),
        "phi_b_deg": np.clip(rng.normal(16.0, 1.8, n), 10.0, 22.0),
        "s0": rng.lognormal(np.log(32.0) - 0.5 * 0.32**2, 0.32, n),
        "ks": rng.lognormal(np.log(7.5) - 0.5 * 0.42**2, 0.42, n),
        "gamma_d": np.clip(rng.normal(17.0, 0.45, n), 15.5, 18.5),
        "gamma_sat": np.clip(rng.normal(20.0, 0.55, n), 18.5, 22.0),
        "root_c": rng.lognormal(np.log(5.0) - 0.5 * 0.40**2, 0.40, n),
        "crack_depth": np.clip(rng.normal(0.75, 0.15, n), 0.25, 1.15),
    }


def solve_slope(
    params: dict[str, np.ndarray],
    scenario: dict,
    t: np.ndarray,
    scale: float = 1.0,
    duration_scale: float = 1.0,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    beta = np.deg2rad(params["beta_deg"])
    z = params["z"]
    c = params["c"]
    phi = np.deg2rad(params["phi_deg"])
    phi_b = np.deg2rad(params["phi_b_deg"])
    s0 = params["s0"]
    ks = params["ks"]
    gamma_d = params["gamma_d"]
    gamma_sat = params["gamma_sat"]

    n = np.size(np.atleast_1d(beta))
    m = len(t)
    root = params["root_c"] if scenario_value(scenario, "veg") else np.zeros(n)
    crack_depth = params["crack_depth"] if scenario_value(scenario, "crack") else np.zeros(n)
    rain = rainfall_series(t, scale=scale, duration_scale=duration_scale)
    rain_eff = rain * (1.0 - scenario_value(scenario, "interception") + scenario_value(scenario, "runoff_concentration"))
    crack_flow_factor = 1.0 + 0.55 * scenario_value(scenario, "crack")
    drainage_time = 30.0 / max(scenario_value(scenario, "drain_factor", 1.0), 1e-9)

    wetness = np.zeros((n, m), dtype=float)
    dt = float(t[1] - t[0])
    for j in range(1, m):
        recharge = (rain_eff[j] / (ks + 2.0)) * crack_flow_factor
        wetness[:, j] = np.maximum(0.0, wetness[:, j - 1] + dt * (recharge - wetness[:, j - 1] / drainage_time))

    if scenario_value(scenario, "veg"):
        wetness *= np.exp(-0.006 * np.maximum(t - 18.0, 0.0))[None, :]

    saturation = 1.0 - np.exp(-0.09 * wetness)
    suction = s0[:, None] * np.exp(-0.13 * wetness)
    if scenario_value(scenario, "veg"):
        suction += 3.0 * np.exp(-0.5 * ((t - 42.0) / 18.0) ** 2)[None, :]

    gamma = gamma_d[:, None] + (gamma_sat - gamma_d)[:, None] * saturation
    pore_pressure = np.maximum(0.0, 0.30 * (wetness - 9.0))

    if scenario_value(scenario, "crack"):
        crack_head = crack_depth[:, None] * np.clip(wetness / 20.0, 0.0, 1.0)
        pore_pressure += 1.45 * crack_head
        crack_shear = 0.28 * 9.81 * crack_head**2 / np.maximum(1.4, z[:, None] / np.sin(beta[:, None])) * 2.2
    else:
        crack_head = np.zeros_like(wetness)
        crack_shear = 0.0

    chi = np.clip(0.20 + 0.80 * (1.0 - saturation), 0.0, 1.0)
    surcharge = scenario_value(scenario, "surcharge_kpa")
    normal_stress = gamma * z[:, None] * np.cos(beta)[:, None] ** 2 + surcharge * np.cos(beta)[:, None] ** 2
    driving = gamma * z[:, None] * np.sin(beta)[:, None] * np.cos(beta)[:, None] + surcharge * np.sin(beta)[:, None] * np.cos(beta)[:, None] + crack_shear
    resisting = c[:, None] + root[:, None] + (normal_stress - pore_pressure) * np.tan(phi)[:, None] + chi * suction * np.tan(phi_b)[:, None]
    fs = resisting / driving
    states = {
        "rain": rain,
        "rain_eff": rain_eff,
        "wetness": wetness,
        "suction": suction,
        "pore_pressure": pore_pressure,
        "crack_head": crack_head,
        "saturation": saturation,
    }
    return fs, states


def hydro_mechanical_memory_index(t: np.ndarray, fs: np.ndarray, reference_fs: float = 1.15) -> float:
    deficit = np.maximum(0.0, reference_fs - fs)
    return float(np.trapezoid(deficit, t))


def reliability_index(pf: float) -> float:
    pf = min(max(float(pf), 1e-6), 1.0 - 1e-6)
    return -NormalDist().inv_cdf(pf)


def make_outputs() -> None:
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)

    t = np.arange(0.0, 96.0 + 0.25, 0.25)
    det_params = deterministic_parameters()
    mc_params = random_parameters()

    rain_df = pd.DataFrame({"time_h": t, "rainfall_mm_h": rainfall_series(t)})
    rain_df.to_csv(DATA / "rainfall_event.csv", index=False)

    det_rows = []
    ts_rows = []
    for name, scenario in SCENARIOS.items():
        fs, state = solve_slope(det_params, scenario, t)
        fs1 = fs[0]
        min_idx = int(np.argmin(fs1))
        hmmi = hydro_mechanical_memory_index(t, fs1)
        det_rows.append(
            {
                "scenario": name,
                "min_fs": float(fs1[min_idx]),
                "time_of_min_fs_h": float(t[min_idx]),
                "hmmi_fs_hour": hmmi,
                "max_wetness_index": float(np.max(state["wetness"][0])),
                "min_suction_kpa": float(np.min(state["suction"][0])),
                "max_pore_pressure_kpa": float(np.max(state["pore_pressure"][0])),
            }
        )
        for j in range(len(t)):
            ts_rows.append(
                {
                    "scenario": name,
                    "time_h": t[j],
                    "rainfall_mm_h": state["rain"][j],
                    "fs": fs1[j],
                    "wetness_index": state["wetness"][0, j],
                    "suction_kpa": state["suction"][0, j],
                    "pore_pressure_kpa": state["pore_pressure"][0, j],
                    "crack_water_head_m": state["crack_head"][0, j],
                }
            )

    det_summary = pd.DataFrame(det_rows)
    det_summary.to_csv(DATA / "deterministic_scenario_summary.csv", index=False)
    pd.DataFrame(ts_rows).to_csv(DATA / "deterministic_time_series.csv", index=False)

    mc_rows = []
    pf_time_rows = []
    min_fs_by_scenario = {}
    for name, scenario in SCENARIOS.items():
        fs, state = solve_slope(mc_params, scenario, t)
        min_fs = fs.min(axis=1)
        min_fs_by_scenario[name] = min_fs
        pf_t = (fs < 1.0).mean(axis=0)
        peak_pf = float(np.max(pf_t))
        peak_idx = int(np.argmax(pf_t))
        mc_rows.append(
            {
                "scenario": name,
                "peak_pf": peak_pf,
                "time_of_peak_pf_h": float(t[peak_idx]),
                "cumulative_pf": float((min_fs < 1.0).mean()),
                "median_min_fs": float(np.median(min_fs)),
                "p05_min_fs": float(np.quantile(min_fs, 0.05)),
                "p95_min_fs": float(np.quantile(min_fs, 0.95)),
                "reliability_index_at_peak": reliability_index(peak_pf),
            }
        )
        for j in range(len(t)):
            pf_time_rows.append({"scenario": name, "time_h": t[j], "pf_t": pf_t[j]})

    mc_summary = pd.DataFrame(mc_rows)
    mc_summary.to_csv(DATA / "monte_carlo_summary.csv", index=False)
    pd.DataFrame(pf_time_rows).to_csv(DATA / "failure_probability_time_series.csv", index=False)

    bare_pf = float(mc_summary.loc[mc_summary["scenario"] == "Bare slope", "cumulative_pf"].iloc[0])
    cracked_pf = float(mc_summary.loc[mc_summary["scenario"] == "Cracked slope", "cumulative_pf"].iloc[0])
    cracked_veg_pf = float(mc_summary.loc[mc_summary["scenario"] == "Cracked vegetated slope", "cumulative_pf"].iloc[0])
    vegetation_pf = float(mc_summary.loc[mc_summary["scenario"] == "Vegetated slope", "cumulative_pf"].iloc[0])
    infra_bad_pf = float(mc_summary.loc[mc_summary["scenario"] == "Road surcharge and clogged drain", "cumulative_pf"].iloc[0])
    infra_good_pf = float(mc_summary.loc[mc_summary["scenario"] == "Road surcharge with maintained drainage", "cumulative_pf"].iloc[0])
    crc_factor = (cracked_pf - cracked_veg_pf) / max(cracked_pf - bare_pf, 1e-9)
    drainage_resilience = (infra_bad_pf - infra_good_pf) / max(infra_bad_pf, 1e-9)
    innovation = pd.DataFrame(
        [
            {
                "metric": "hydro_mechanical_memory_index",
                "definition": "Integral over time of positive FS deficit below reference FS=1.15",
                "unit": "FS-hour",
                "interpretation": "Duration-weighted instability memory after and during rainfall",
            },
            {
                "metric": "crack_root_compensation_factor",
                "definition": "(Pf_cracked - Pf_cracked_vegetated)/(Pf_cracked - Pf_bare)",
                "unit": "dimensionless",
                "value": crc_factor,
                "interpretation": "Fraction of crack-induced risk neutralized by the selected vegetation state",
            },
            {
                "metric": "state_conditioned_threshold",
                "definition": "Rainfall scale at which the minimum deterministic FS reaches 1.0 for each slope state",
                "unit": "dimensionless rainfall multiplier",
                "interpretation": "Decision envelope linking rainfall duration and slope biological/structural state",
            },
            {
                "metric": "infrastructure_drainage_resilience",
                "definition": "(Pf_road_clogged_drain - Pf_road_maintained_drainage)/Pf_road_clogged_drain",
                "unit": "dimensionless",
                "value": drainage_resilience,
                "interpretation": "Fraction of road-surcharge risk reduced by maintained drainage and vegetation",
            },
        ]
    )
    innovation.to_csv(DATA / "proposed_metrics.csv", index=False)

    # Threshold envelope.
    threshold_rows = []
    durations = np.array([0.50, 0.75, 1.00, 1.25, 1.50, 2.00])
    for name, scenario in SCENARIOS.items():
        for dur in durations:
            lo, hi = 0.10, 3.00
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                fs, _ = solve_slope(det_params, scenario, t, scale=mid, duration_scale=float(dur))
                if float(fs.min()) <= 1.0:
                    hi = mid
                else:
                    lo = mid
            threshold_rows.append(
                {
                    "scenario": name,
                    "duration_multiplier": float(dur),
                    "equivalent_peak_intensity_mm_h": float(24.0 * hi),
                    "rainfall_scale_for_fs_1": float(hi),
                }
            )
    threshold_df = pd.DataFrame(threshold_rows)
    threshold_df.to_csv(DATA / "state_conditioned_threshold_envelope.csv", index=False)

    # Sensitivity on cracked slope by rank correlation with min FS.
    cracked_min = min_fs_by_scenario["Cracked slope"]
    sens_rows = []
    for key, values in mc_params.items():
        rho = pd.Series(values).rank().corr(pd.Series(cracked_min).rank())
        sens_rows.append({"variable": key, "spearman_with_min_fs_cracked": float(rho)})
    sens = pd.DataFrame(sens_rows).sort_values("spearman_with_min_fs_cracked")
    sens.to_csv(DATA / "sensitivity_summary.csv", index=False)

    conv_rows = []
    for sample_size in [1_000, 3_000, 10_000, 30_000]:
        for seed in [120, 121, 122, 123, 124]:
            params_n = random_parameters(sample_size, seed=seed)
            for scenario_name in ["Cracked slope", "Road surcharge and clogged drain", "Road surcharge with maintained drainage"]:
                fs, _ = solve_slope(params_n, SCENARIOS[scenario_name], t)
                min_fs = fs.min(axis=1)
                conv_rows.append(
                    {
                        "scenario": scenario_name,
                        "sample_size": sample_size,
                        "seed": seed,
                        "cumulative_pf": float((min_fs < 1.0).mean()),
                    }
                )
    conv = pd.DataFrame(conv_rows)
    conv.to_csv(DATA / "monte_carlo_convergence.csv", index=False)

    make_figures(t, det_summary, mc_summary, threshold_df, sens, conv)
    write_readme()


def make_figures(
    t: np.ndarray,
    det_summary: pd.DataFrame,
    mc_summary: pd.DataFrame,
    threshold_df: pd.DataFrame,
    sens: pd.DataFrame,
    conv: pd.DataFrame,
) -> None:
    plt.rcParams.update(
        {
            "font.size": 13,
            "axes.titlesize": 15,
            "axes.labelsize": 13,
            "legend.fontsize": 11,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "figure.dpi": 160,
            "savefig.dpi": 600,
            "font.family": "DejaVu Sans",
        }
    )

    colors = {
        "Bare slope": "#2f6b9a",
        "Cracked slope": "#b05b25",
        "Vegetated slope": "#5f9f4a",
        "Cracked vegetated slope": "#6f5aa8",
        "Road surcharge and clogged drain": "#8a2d3d",
        "Road surcharge with maintained drainage": "#2c7f77",
    }

    # Figure 1: conceptual workflow.
    fig, ax = plt.subplots(figsize=(9.4, 5.0))
    ax.axis("off")
    box_h = 0.16
    boxes = [
        (0.04, 0.68, 0.18, "Rainfall\ntime series"),
        (0.30, 0.68, 0.18, "Infiltration\nstate"),
        (0.56, 0.68, 0.18, "Crack-root\nmodifier"),
        (0.81, 0.68, 0.17, "Road load\nand drainage"),
        (0.30, 0.30, 0.18, "FSmin(t)"),
        (0.61, 0.30, 0.32, "Pf(t) and\nthreshold envelope"),
    ]
    for x, y, w, label in boxes:
        ax.add_patch(plt.Rectangle((x, y), w, box_h, facecolor="white", edgecolor="black", linewidth=1.2))
        ax.text(x + w / 2, y + box_h / 2, label, ha="center", va="center", fontsize=12.2, color="black")
    arrows = [
        ((0.235, 0.76), (0.285, 0.76)),
        ((0.495, 0.76), (0.545, 0.76)),
        ((0.755, 0.76), (0.795, 0.76)),
        ((0.895, 0.665), (0.77, 0.475)),
        ((0.39, 0.665), (0.39, 0.475)),
        ((0.50, 0.38), (0.595, 0.38)),
    ]
    for start, end in arrows:
        ax.annotate(
            "",
            xy=end,
            xytext=start,
            arrowprops=dict(arrowstyle="-|>", linewidth=1.35, color="black", mutation_scale=13, shrinkA=0, shrinkB=0),
        )
    ax.text(0.04, 0.12, "New output: state-conditioned temporal reliability for natural and infrastructure-modified slopes.", color="black", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / "Fig1_conceptual_workflow.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Load deterministic and Pf time series.
    det_ts = pd.read_csv(DATA / "deterministic_time_series.csv")
    pf_ts = pd.read_csv(DATA / "failure_probability_time_series.csv")

    fig, axes = plt.subplots(3, 1, figsize=(8.8, 8.8), sharex=True)
    axes[0].plot(t, det_ts[det_ts["scenario"] == "Bare slope"]["rainfall_mm_h"], color="black", lw=2)
    axes[0].set_ylabel("Rainfall\n(mm/h)")
    axes[0].set_title("Rainfall forcing and hydrological response")
    for name in SCENARIOS:
        subset = det_ts[det_ts["scenario"] == name]
        axes[1].plot(subset["time_h"], subset["suction_kpa"], label=name, color=colors[name], lw=2)
    axes[1].set_ylabel("Suction\n(kPa)")
    for name in SCENARIOS:
        subset = det_ts[det_ts["scenario"] == name]
        axes[2].plot(subset["time_h"], subset["pore_pressure_kpa"], label=name, color=colors[name], lw=2)
    axes[2].set_ylabel("Pore pressure\n(kPa)")
    axes[2].set_xlabel("Time (h)")
    axes[2].legend(ncol=2, frameon=True, loc="upper center", bbox_to_anchor=(0.5, -0.34))
    for ax in axes:
        ax.grid(True, alpha=0.25)
    fig.tight_layout(rect=[0, 0.08, 1, 1])
    fig.savefig(FIG / "Fig2_hydrological_response.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(8.8, 7.2), sharex=True)
    for name in SCENARIOS:
        subset = det_ts[det_ts["scenario"] == name]
        axes[0].plot(subset["time_h"], subset["fs"], label=name, color=colors[name], lw=2.2)
    axes[0].axhline(1.0, color="black", lw=1.0, ls="--")
    axes[0].set_ylabel("Deterministic FS")
    axes[0].set_title("Temporal stability and failure probability")
    for name in SCENARIOS:
        subset = pf_ts[pf_ts["scenario"] == name]
        axes[1].plot(subset["time_h"], subset["pf_t"], label=name, color=colors[name], lw=2.2)
    axes[1].set_ylabel("Pf(t)")
    axes[1].set_xlabel("Time (h)")
    axes[1].set_ylim(-0.02, 0.75)
    axes[1].legend(ncol=2, frameon=True, loc="upper center", bbox_to_anchor=(0.5, -0.28))
    for ax in axes:
        ax.grid(True, alpha=0.25)
    fig.tight_layout(rect=[0, 0.08, 1, 1])
    fig.savefig(FIG / "Fig3_temporal_reliability.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    for name in SCENARIOS:
        subset = threshold_df[threshold_df["scenario"] == name]
        ax.plot(
            subset["duration_multiplier"] * 24.0,
            subset["equivalent_peak_intensity_mm_h"],
            marker="o",
            lw=2.3,
            label=name,
            color=colors[name],
        )
    durations_h = np.array(sorted((threshold_df["duration_multiplier"] * 24.0).unique()))
    caine = 14.82 * durations_h ** (-0.39)
    ax.plot(durations_h, caine, color="black", lw=2.0, ls="--", label="Caine empirical lower-bound")
    ax.set_xlabel("Equivalent storm duration (h)")
    ax.set_ylabel("Critical peak intensity (mm/h)")
    ax.set_title("State-conditioned rainfall threshold envelope")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=True)
    fig.tight_layout()
    fig.savefig(FIG / "Fig4_threshold_envelope.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.8, 5.8))
    top = sens.reindex(sens["spearman_with_min_fs_cracked"].abs().sort_values(ascending=False).index).head(8)
    ax.barh(top["variable"], top["spearman_with_min_fs_cracked"], color="#4b7c9f")
    ax.axvline(0, color="black", lw=1)
    ax.set_xlabel("Spearman correlation with minimum FS")
    ax.set_title("Dominant controls for cracked-slope stability")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG / "Fig5_sensitivity_controls.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.4, 5.1))
    x = np.arange(len(mc_summary))
    ax.bar(x - 0.18, mc_summary["cumulative_pf"], width=0.36, color="#b05b25", label="Cumulative Pf")
    ax.bar(x + 0.18, 1.0 - mc_summary["median_min_fs"].clip(upper=1.0), width=0.36, color="#5f9f4a", label="Median FS deficit")
    ax.set_xticks(x)
    display_labels = [
        "Bare\nslope",
        "Cracked\nslope",
        "Vegetated\nslope",
        "Cracked+\nvegetated",
        "Road,\nclogged",
        "Road,\nmaintained",
    ]
    ax.set_xticklabels(display_labels, rotation=0, ha="center")
    ax.set_ylabel("Probability or normalized deficit")
    ax.set_title("Risk contrast by slope state")
    ax.legend(frameon=True)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG / "Fig6_state_risk_contrast.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    for name, color in {
        "Cracked slope": colors["Cracked slope"],
        "Road surcharge and clogged drain": colors["Road surcharge and clogged drain"],
        "Road surcharge with maintained drainage": colors["Road surcharge with maintained drainage"],
    }.items():
        subset = conv[conv["scenario"] == name]
        stats = subset.groupby("sample_size")["cumulative_pf"].agg(["mean", "std"]).reset_index()
        ax.errorbar(
            stats["sample_size"],
            stats["mean"],
            yerr=stats["std"],
            marker="o",
            lw=2.2,
            capsize=4,
            label=name,
            color=color,
        )
    ax.set_xscale("log")
    ax.set_xlabel("Monte Carlo sample size")
    ax.set_ylabel("Cumulative Pf")
    ax.set_title("Monte Carlo convergence check")
    ax.grid(True, alpha=0.25, which="both")
    ax.legend(frameon=True)
    fig.tight_layout()
    fig.savefig(FIG / "Fig7_monte_carlo_convergence.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_readme() -> None:
    (OUT / "requirements.txt").write_text(
        "numpy\npandas\nmatplotlib\npython-docx\npillow\nrequests\n",
        encoding="utf-8",
    )
    (OUT / "README.md").write_text(
        """# Computational package for article 120

This package reproduces the synthetic demonstration used in the manuscript.
It is not a field-calibrated data set. The purpose is to make the proposed
state-conditioned temporal reliability workflow auditable.

Public repository: https://github.com/gabrielmontufar/article-120-slope-state-envelope

## Reproduce

```bash
python code/slope_state_envelope.py
```

The random seed is fixed at `120`, with `30,000` Monte Carlo samples.

## Outputs

- `data/deterministic_scenario_summary.csv`
- `data/deterministic_time_series.csv`
- `data/monte_carlo_summary.csv`
- `data/failure_probability_time_series.csv`
- `data/state_conditioned_threshold_envelope.csv`
- `data/sensitivity_summary.csv`
- `data/monte_carlo_convergence.csv`
- `figures/Fig1_conceptual_workflow.png` to `figures/Fig6_state_risk_contrast.png`
- `figures/Fig7_monte_carlo_convergence.png`

## Scope

The model couples a reduced infiltration state variable, suction loss,
positive pore pressure, crack water loading, root cohesion, deterministic
factor of safety, and Monte Carlo reliability. Parameters are transparent
and intended for reproducible comparison rather than site-specific design.
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    make_outputs()
