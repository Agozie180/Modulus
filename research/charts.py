"""Render the three Modulus research charts into docs/img/."""
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "axes.spines.top": False, "axes.spines.right": False})
GOLD, INK, GREY, RED = "#F0B90B", "#111111", "#9a9a9a", "#d6453d"

# 1. Discovery curve
c = {int(k): v for k, v in json.load(open("research/data24/discovery_curve.json")).items()}
hb = sorted(c, reverse=True)
fig, ax = plt.subplots(figsize=(11, 5.2), dpi=120)
ax.plot([-h for h in hb], [c[h][2] * 100 for h in hb], color=GOLD, lw=3.2, marker="o", ms=5)
ax.axvspan(-64, -16.5, color="#000", alpha=0.06); ax.axvline(-15.5, color=INK, lw=1, ls="--")
ax.text(-62, 90, "DARK WEEKEND\nonly the token trades", fontsize=11, color=INK, va="top", weight="bold")
ax.text(-15, 56, "Sun 22:00 UTC\nfutures reopen", fontsize=10, color=INK)
ax.set_xlabel("hours before Monday's US open"); ax.set_ylabel("token gets Monday's direction right (%)")
ax.set_ylim(50, 96); ax.set_title("When does the 24/7 token know where Monday opens?  (858 stock-weekends)", loc="left", weight="bold")
fig.tight_layout(); fig.savefig("docs/img/discovery_curve.png"); plt.close(fig)

# 2. Two Nights
fig, ax = plt.subplots(figsize=(11, 5.2), dpi=120)
labels = ["Weekend move\n1-2%", "Weekend move\n>2%", "Weeknight move\n1-2%", "Weeknight move\n>2%"]
vals = [103, 164, -39, -35]; cols = [GOLD, GOLD, GREY, GREY]
b = ax.bar(labels, vals, color=cols, width=0.6)
for r, v in zip(b, vals):
    ax.text(r.get_x() + r.get_width() / 2, v + 6 if v > 0 else v / 2, f"{v:+d} bps", ha="center", va="bottom" if v > 0 else "center", weight="bold", color=INK if v > 0 else "white")
ax.axhline(0, color=INK, lw=1); ax.set_ylim(-60, 190)
ax.set_ylabel("fading the move, P&L to next US open (bps)")
ax.set_title("Two kinds of night: weekend crowds overshoot, weeknight moves are informed", loc="left", weight="bold")
fig.tight_layout(); fig.savefig("docs/img/two_nights.png"); plt.close(fig)

# 3. Liquidity clock
L = json.load(open("research/data24/liquidity_clock.json"))
import numpy as np
M = np.array([[L.get(f"{d}-{h:02d}", 0) for h in range(24)] for d in range(7)])
fig, ax = plt.subplots(figsize=(11, 4.2), dpi=120)
im = ax.imshow(np.log10(M + 1), aspect="auto", cmap="YlOrBr")
ax.set_yticks(range(7), ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]); ax.set_xticks(range(0, 24, 2), [f"{h:02d}" for h in range(0, 24, 2)])
ax.set_xlabel("hour (UTC)"); ax.set_title("The liquidity clock: median $ traded per bStock per hour (log scale)", loc="left", weight="bold")
cb = fig.colorbar(im, ax=ax); cb.set_ticks([2, 3, 4, 5]); cb.set_ticklabels(["$100", "$1k", "$10k", "$100k"])
fig.tight_layout(); fig.savefig("docs/img/liquidity_clock.png"); plt.close(fig)
print("ok")
