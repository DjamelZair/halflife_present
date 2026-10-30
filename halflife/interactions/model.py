"""Mechanistic static DDI model from ICH M12: reversible inhibition and induction, liver and gut.

AUCR = 1 / (Ag * (1 - Fg) + Fg)  *  1 / (Ah * Ch * fm + (1 - fm))
with A = 1 / (1 + I/Ki) for reversible inhibition and C the fold increase in enzyme activity
by an inducer (C = 1 means no induction).

fm  fraction of the victim cleared through the inhibited enzyme
Fg  fraction escaping gut metabolism (1 means the gut plays no role)
I/Ki  how hard the inhibitor hits the enzyme, liver and gut separately

I took the formula from the pkpd-modeling skill (K-Dense claude-scientific-skills), which cites ICH M12.
This is a screening and teaching model. It leaves out time dependent inhibition, transporters and
metabolites, so it is NOT a clinical prediction.
"""

import numpy as np

# FDA wording for how strong an effect is, based on the AUC ratio
# inhibition: strong >= 5, moderate 2 to 5, weak 1.25 to 2
# induction: strong <= 0.2 (80 percent lower), moderate 0.2 to 0.5, weak 0.5 to 0.8
UP = [(5.0, "strong increase"), (2.0, "moderate increase"), (1.25, "weak increase")]
DOWN = [(0.2, "strong decrease"), (0.5, "moderate decrease"), (0.8, "weak decrease")]


def inhibition_factor(i_over_ki: float) -> float:
    """A in the formula, 1 means no inhibition and it drops towards 0 as inhibition grows."""
    return 1.0 / (1.0 + max(i_over_ki, 0.0))


def auc_ratio(fm: float, i_over_ki_liver: float = 0.0, fg: float = 1.0, i_over_ki_gut: float = 0.0,
              induction_fold: float = 1.0) -> float:
    if not 0 <= fm <= 1 or not 0 < fg <= 1 or induction_fold <= 0:
        raise ValueError("fm must be in [0, 1], Fg in (0, 1] and induction_fold above 0")
    ah = inhibition_factor(i_over_ki_liver)
    ag = inhibition_factor(i_over_ki_gut)
    gut = 1.0 / (ag * (1.0 - fg) + fg)
    liver = 1.0 / (ah * induction_fold * fm + (1.0 - fm))
    return gut * liver


def max_possible_ratio(fm: float, fg: float = 1.0) -> float:
    """Ceiling with full inhibition, 1 / ((1 - fm) * Fg). Shows why fm matters so much."""
    return np.inf if fm >= 1 else 1.0 / ((1.0 - fm) * fg)


def category(ratio: float) -> str:
    for threshold, label in UP:
        if ratio >= threshold:
            return label
    for threshold, label in DOWN:
        if ratio <= threshold:
            return label
    return "no meaningful change"


def concentration_curve(auc_ratio_value: float, hours: float = 24, ka: float = 1.0,
                        ke: float = 0.2, points: int = 300) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Illustrative one compartment oral curve, before and after the interaction.

    I put the whole effect on clearance (ke divided by the ratio), so AUC grows by exactly the ratio.
    The parameters are made up on purpose; the shape is the point, not the numbers.
    """
    t = np.linspace(0, hours, points)

    def bateman(k_el: float) -> np.ndarray:
        if abs(ka - k_el) < 1e-9:
            k_el *= 0.999  # avoid dividing by zero when ka equals ke
        return ka / (ka - k_el) * (np.exp(-k_el * t) - np.exp(-ka * t))

    before = bateman(ke)
    after = bateman(ke / auc_ratio_value)
    scale = before.max()
    return t, before / scale, after / scale
