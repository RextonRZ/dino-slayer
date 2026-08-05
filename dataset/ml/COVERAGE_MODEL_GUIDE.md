# Coverage model: what to predict, and how it can go wrong

Written against the actual file (`dataset/web/dipi.geojson`, 1,448 settlements).
Every number below was measured, not assumed.

---

## 1. Do not predict DIPI

DIPI is a weighted sum of its own four pillars:

```
dipi = (0.40*p_connectivity + 0.25*p_population
      + 0.15*p_institutions + 0.20*p_equity) * 100
```

Verified across all 1,114 scored settlements: **max error 0.05**, which is just
rounding to 1 dp. A model predicting DIPI from those four columns will score a
near-perfect R² because it is re-deriving arithmetic, not learning anything. A
GeoAI judge will ask "what did the model add?" and there is no answer.

**Predict `dl_mbps` instead**, from features that are not the network.

---

## 2. The split

| Tier | n | has `dl_mbps` | median `n_tests` | use it for |
|---|---|---|---|---|
| `measured` | 850 | 850 | **148** | **TRAIN** |
| `low_evidence` | 264 | 264 | 11 | **VALIDATE** (noisy labels, honest reality check) |
| `insufficient` | 334 | 118 | 0 | 118 = second check · **216 = what we predict** |

Train on `measured` only. Those labels come from a median of 148 speed tests;
`low_evidence` labels come from a median of 11 and carry real noise. Fitting to
noise then reporting the error against that same noise flatters the model.

The payoff is the **216 settlements with no measurement at all**. Right now the
dashboard renders them as "Not scored, measurement needed". A model that says
"our best estimate is 4.2 Mbps, and here is why" turns the biggest hole in the
project into its most interesting slide.

---

## 3. Feature allowlist

Use only these. All are complete except `rwi`.

| Feature | Missing |
|---|---|
| `pop_2km` | 0 |
| `n_schools_3km` | 0 |
| `n_clinics_3km` | 0 |
| `rwi` | 96 |
| `elevation_m` | 0 |
| `seasonal_water_px` | 0 |
| `flood_prone` | 0 |
| `place` (city/town/village/hamlet) | 0 |
| longitude, latitude | 0 |
| `district` (25 categories) | 0 |

### Never use these. Each one leaks the answer.

| Column | Why |
|---|---|
| `p_connectivity` | derived from `dl_mbps`. This IS the target, rescaled |
| `dipi`, `rank` | contain `p_connectivity` |
| `ul_mbps`, `latency_ms` | measured from the same Ookla tile as the target |
| `n_tests`, `n_tiles` | describe how the target was measured |
| `evidence_tier` | a function of `n_tests` |
| `stakes_score`, `gap_rank` | only exist for the rows we predict, never for training rows |

`p_population`, `p_institutions` and `p_equity` are safe in principle, but they
are just rescaled versions of `pop_2km`, `n_schools_3km` and `rwi`. Use the raw
columns; they are easier to explain in SHAP.

---

## 4. Spatial CV is mandatory, and here is the proof

Of the 1,232 settlements with a speed value, **358 (29%) share an exact value
with at least one other settlement**. The largest group is 9 settlements all
reading 7.898 Mbps; another 8 all read 0.359.

They are not coincidences. Those settlements fall inside the same Ookla tile and
inherit the same aggregate. Under a random train/test split, some of those
identical rows land in train and their twins land in test, and the model gets
credit for "predicting" a number it was shown. The score will look excellent and
mean nothing.

Group by **district** so neighbours stay on the same side of the split:

```python
from sklearn.model_selection import GroupKFold, cross_val_predict
cv = GroupKFold(n_splits=5)
pred = cross_val_predict(model, X, y, groups=df["district"], cv=cv)
```

Report both the random-split score and the grouped score. The gap between them
is a genuinely good slide: it shows you knew to check.

---

## 5. Model settings that matter here

**Log-transform the target.** It is heavily right-skewed: min 0.36, median 45.9,
mean 67.2, max 346.2. Train on `np.log1p(dl_mbps)` and invert with `np.expm1`
for reporting. Without this the loss is dominated by a handful of fast towns and
the model gives up on the slow rural tail, which is the only part we care about.

**Do not impute `rwi`.** XGBoost handles `NaN` natively and learns a default
direction. Filling those 96 with 0 is actively wrong: RWI is negative for poorer
areas, so 0 means "average wealth", and you would be inventing data. This is the
same rule the dashboard follows everywhere.

**Beat a baseline or say so.** Compute MAE for:
1. predict the global median (45.9)
2. predict the district median
3. your model

If it cannot beat district-median under grouped CV, that is a finding worth
reporting honestly, not a failure to hide.

**Metrics:** report MAE in Mbps (a planner understands "wrong by 12 Mbps"), plus
R². Skip RMSE-only; the skew makes it hard to read.

### 5a. Per-district residuals — the fairness check

A model can hit a good overall MAE while being systematically wrong about one
part of Sabah. If it always over-predicts speed in the Interior, every Interior
settlement looks better served than it is, and the ranking quietly deprioritises
them. That is the harm this project exists to avoid, so it has to be measured.

After grouped CV, compute the **mean signed residual per district** on the
out-of-fold predictions:

```python
df["resid"] = df["pred"] - df["dl_mbps"]          # signed, not absolute
by_d = df.groupby("district")["resid"].agg(["mean", "median", "count"])
print(by_d.sort_values("mean"))
```

Read it like this:

- **Near zero everywhere** → no geographic bias. Report the table as evidence.
- **One district strongly positive** → the model flatters it; its settlements
  will be ranked as less needy than they are.
- **One district strongly negative** → the reverse; it will be over-prioritised.

Flag any district whose mean residual exceeds **half the overall MAE**. Report
the table either way, including in the model card. A clean table is a finding
worth showing; a skewed one is a finding worth showing *and* a reason to add a
district or division feature and retrain.

This maps to NIST MEASURE 2.11 in `docs/ai_governance.md`, so the numbers need
to exist before that row is true.

---

## 6. Uncertainty beats a point estimate

For the 216 unmeasured settlements, a bare number invites "how do you know?".
Train three quantile models and show a range:

```python
lo  = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.10)
mid = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.50)
hi  = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.90)
```

"Estimated 3 to 11 Mbps" is defensible in a way that "4.2 Mbps" is not.

---

## 7. What to hand back for the dashboard

One CSV, one row per predicted settlement:

```
settlement_id, pred_dl_mbps, pred_lo, pred_hi,
shap_pop_2km, shap_rwi, shap_elevation_m, shap_n_schools_3km, ...,
model_version, cv_mae, cv_r2
```

Include `cv_mae` and `cv_r2` in the file itself. The dashboard rule is that no
model output appears in the UI without its validation numbers next to it, and
having them in the same row makes that automatic.

Predictions will render as a clearly separate block, never merged into DIPI and
never coloured on the DIPI scale. A prediction is not a measurement, and the
footer sentence commits us to that distinction.

---

## 8. Five ways this goes wrong

1. Predicting DIPI from its own components (see §1)
2. Random CV instead of grouped, inflated by the 29% tile sharing (§4)
3. Leaving `p_connectivity` in the feature set
4. Filling missing `rwi` with 0
5. Putting a prediction on the map in DIPI colours, so it reads as measured
