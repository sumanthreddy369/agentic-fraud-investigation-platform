# EDA model selection and verification results

Historical initial-baseline report, superseded for EDA and model comparison by
[FULL_EDA_COMPARISON.md](FULL_EDA_COMPARISON.md) and for infrastructure by
[DEPLOYMENT_PROOF.md](DEPLOYMENT_PROOF.md). The pending labels below describe the earlier stage.

At that earlier stage, initial training-table profiling was complete; comprehensive EDA and multi-model selection are not complete. All reported model metrics use the chronological validation partition, not an independent final test set.

## EDA coverage

| Analysis | Status | Evidence or limitation |
| --- | --- | --- |
| Training schema and duplicate keys | Complete | Required fields checked; transaction and identity keys unique |
| Binary labels and relative time | Complete | Labels validated; finite nonnegative relative time |
| Missing values | Initial profiling complete | Blank or whitespace cells only; sentinel semantics not exhaustively audited |
| Identity matching | Complete | 144233 identity rows; 446307 unmatched transactions retained |
| Temporal split and class balance | Complete | Time ties stay together; no random-only split |
| Test tables | Not profiled | Downloaded but untouched |
| Feature distributions and correlations | Pending | No full univariate or relationship analysis |
| Subgroup errors and fairness | Pending | No subgroup conclusions supported |
| Calibration and drift | Pending | Brier score measured; no fitted calibration or drift evaluation |

## Dataset and split comparison

| Partition | Rows | Fraud prevalence |
| --- | ---: | ---: |
| Training | 472432 | 3.5135% |
| Validation | 118108 | 3.4409% |

Identity match coverage: 24.42%. Relative-time boundary: 12192900. TransactionDT is not a calendar timestamp.

## Model choice

Selected a new scikit-learn RandomForestClassifier as a small reproducible serving baseline. This choice supports nonlinear interactions in 15 numeric features and conversion through skl2onnx. It was not selected through a measured competition between algorithms and must not be described as the best model.

| Setting | Value |
| --- | --- |
| Version | ieee-rf-numeric15-v1 |
| Features | TransactionAmt and C1 through C14 |
| Missing values | Fixed -999 blank sentinel |
| Trees | 40 |
| Maximum depth | 12 |
| Minimum leaf size | 20 |
| Seed and CPU workers | 42 and 2 |
| Threshold | Fixed 0.5; not tuned |
| Export | ONNX with CPUExecutionProvider |

## Baseline comparison

The constant-prior reference below is calculated analytically from training and validation label proportions. It is not another fitted model. XGBoost, logistic regression, and LightGBM have not been benchmarked.

| Metric | Constant training prior reference | Random forest ONNX |
| --- | ---: | ---: |
| ROC AUC | 0.5000 | 0.8469 |
| Average precision | 0.0344 | 0.4273 |
| Brier score lower is better | 0.03323 | 0.02474 |
| Recall at 0.5 | 0% | 24.29% |
| Precision at 0.5 | Undefined no positive predictions | 82.46% |
| False positive rate at 0.5 | 0% | 0.184% |

Average precision is not interchangeable with trapezoidal PR-AUC. The chosen threshold misses approximately three quarters of fraud. Accuracy is not used as the main success criterion because labels are imbalanced.

## Confusion matrix at threshold 0 point 5

| Actual class | Predicted not fraud | Predicted fraud |
| --- | ---: | ---: |
| Not fraud | 113834 | 210 |
| Fraud | 3077 | 987 |

## Tests and deployment evidence

Publication check on October 13: full PostgreSQL-backed suite **133 passed, 1 skipped**.
The database shut down successfully. The wrapper exited with a Windows file-lock
error deleting its temporary command.log afterward; cleanup was not fully successful.
Ruff and formatting checks passed. This supersedes the narrower test count below
without changing its original scope.

| Check | Result | Scope |
| --- | --- | --- |
| Data profiling tests | 8 passed in earlier run | Synthetic invalid-input and split tests |
| Training input API and ONNX suite | 36 passed 1 skipped | Optional provider skipped; suites overlap earlier API tests |
| Source versus ONNX parity | All 118108 validation predictions | Maximum absolute error 1.0224e-7; tolerance atol and rtol 1e-5 |
| FastAPI golden requests | 10 passed | Maximum error 4.2328e-8; in-process |
| Authentication and schema rejection | Passed | Missing token 401; wrong adapter schema safely rejected with 502 |
| Container build and HTTP inference | Build succeeded; 10 predictions passed | Loopback only; temporary container stopped |
| Ruff and formatting | Passed at model milestone | No full security audit rerun claimed |
| Database readiness in container | Not tested | No database deployment proof |
| Kubernetes recovery and scaling | Pending | No cluster proof |
| Terraform reproducibility | Pending | Draft unvalidated |

## Per column blank counts

Aggregate counts only. No raw transactions, model binaries, credentials, or golden feature payloads are published. Numeric sentinel meaning and categorical missing conventions need further analysis.

### train_transaction.csv

| Column | Blank cells | Percent |
| --- | ---: | ---: |
| dist2 | 552913 | 93.63% |
| D7 | 551623 | 93.41% |
| D13 | 528588 | 89.51% |
| D14 | 528353 | 89.47% |
| D12 | 525823 | 89.04% |
| D6 | 517353 | 87.61% |
| D8 | 515614 | 87.31% |
| D9 | 515614 | 87.31% |
| V138 | 508595 | 86.12% |
| V139 | 508595 | 86.12% |
| V140 | 508595 | 86.12% |
| V141 | 508595 | 86.12% |
| V142 | 508595 | 86.12% |
| V146 | 508595 | 86.12% |
| V147 | 508595 | 86.12% |
| V148 | 508595 | 86.12% |
| V149 | 508595 | 86.12% |
| V153 | 508595 | 86.12% |
| V154 | 508595 | 86.12% |
| V155 | 508595 | 86.12% |
| V156 | 508595 | 86.12% |
| V157 | 508595 | 86.12% |
| V158 | 508595 | 86.12% |
| V161 | 508595 | 86.12% |
| V162 | 508595 | 86.12% |
| V163 | 508595 | 86.12% |
| V143 | 508589 | 86.12% |
| V144 | 508589 | 86.12% |
| V145 | 508589 | 86.12% |
| V150 | 508589 | 86.12% |
| V151 | 508589 | 86.12% |
| V152 | 508589 | 86.12% |
| V159 | 508589 | 86.12% |
| V160 | 508589 | 86.12% |
| V164 | 508589 | 86.12% |
| V165 | 508589 | 86.12% |
| V166 | 508589 | 86.12% |
| V322 | 508189 | 86.05% |
| V323 | 508189 | 86.05% |
| V324 | 508189 | 86.05% |
| V325 | 508189 | 86.05% |
| V326 | 508189 | 86.05% |
| V327 | 508189 | 86.05% |
| V328 | 508189 | 86.05% |
| V329 | 508189 | 86.05% |
| V330 | 508189 | 86.05% |
| V331 | 508189 | 86.05% |
| V332 | 508189 | 86.05% |
| V333 | 508189 | 86.05% |
| V334 | 508189 | 86.05% |
| V335 | 508189 | 86.05% |
| V336 | 508189 | 86.05% |
| V337 | 508189 | 86.05% |
| V338 | 508189 | 86.05% |
| V339 | 508189 | 86.05% |
| V217 | 460110 | 77.91% |
| V218 | 460110 | 77.91% |
| V219 | 460110 | 77.91% |
| V223 | 460110 | 77.91% |
| V224 | 460110 | 77.91% |
| V225 | 460110 | 77.91% |
| V226 | 460110 | 77.91% |
| V228 | 460110 | 77.91% |
| V229 | 460110 | 77.91% |
| V230 | 460110 | 77.91% |
| V231 | 460110 | 77.91% |
| V232 | 460110 | 77.91% |
| V233 | 460110 | 77.91% |
| V235 | 460110 | 77.91% |
| V236 | 460110 | 77.91% |
| V237 | 460110 | 77.91% |
| V240 | 460110 | 77.91% |
| V241 | 460110 | 77.91% |
| V242 | 460110 | 77.91% |
| V243 | 460110 | 77.91% |
| V244 | 460110 | 77.91% |
| V246 | 460110 | 77.91% |
| V247 | 460110 | 77.91% |
| V248 | 460110 | 77.91% |
| V249 | 460110 | 77.91% |
| V252 | 460110 | 77.91% |
| V253 | 460110 | 77.91% |
| V254 | 460110 | 77.91% |
| V257 | 460110 | 77.91% |
| V258 | 460110 | 77.91% |
| V260 | 460110 | 77.91% |
| V261 | 460110 | 77.91% |
| V262 | 460110 | 77.91% |
| V263 | 460110 | 77.91% |
| V264 | 460110 | 77.91% |
| V265 | 460110 | 77.91% |
| V266 | 460110 | 77.91% |
| V267 | 460110 | 77.91% |
| V268 | 460110 | 77.91% |
| V269 | 460110 | 77.91% |
| V273 | 460110 | 77.91% |
| V274 | 460110 | 77.91% |
| V275 | 460110 | 77.91% |
| V276 | 460110 | 77.91% |
| V277 | 460110 | 77.91% |
| V278 | 460110 | 77.91% |
| R_emaildomain | 453249 | 76.75% |
| V167 | 450909 | 76.36% |
| V168 | 450909 | 76.36% |
| V172 | 450909 | 76.36% |
| V173 | 450909 | 76.36% |
| V176 | 450909 | 76.36% |
| V177 | 450909 | 76.36% |
| V178 | 450909 | 76.36% |
| V179 | 450909 | 76.36% |
| V181 | 450909 | 76.36% |
| V182 | 450909 | 76.36% |
| V183 | 450909 | 76.36% |
| V186 | 450909 | 76.36% |
| V187 | 450909 | 76.36% |
| V190 | 450909 | 76.36% |
| V191 | 450909 | 76.36% |
| V192 | 450909 | 76.36% |
| V193 | 450909 | 76.36% |
| V196 | 450909 | 76.36% |
| V199 | 450909 | 76.36% |
| V202 | 450909 | 76.36% |
| V203 | 450909 | 76.36% |
| V204 | 450909 | 76.36% |
| V205 | 450909 | 76.36% |
| V206 | 450909 | 76.36% |
| V207 | 450909 | 76.36% |
| V211 | 450909 | 76.36% |
| V212 | 450909 | 76.36% |
| V213 | 450909 | 76.36% |
| V214 | 450909 | 76.36% |
| V215 | 450909 | 76.36% |
| V216 | 450909 | 76.36% |
| V169 | 450721 | 76.32% |
| V170 | 450721 | 76.32% |
| V171 | 450721 | 76.32% |
| V174 | 450721 | 76.32% |
| V175 | 450721 | 76.32% |
| V180 | 450721 | 76.32% |
| V184 | 450721 | 76.32% |
| V185 | 450721 | 76.32% |
| V188 | 450721 | 76.32% |
| V189 | 450721 | 76.32% |
| V194 | 450721 | 76.32% |
| V195 | 450721 | 76.32% |
| V197 | 450721 | 76.32% |
| V198 | 450721 | 76.32% |
| V200 | 450721 | 76.32% |
| V201 | 450721 | 76.32% |
| V208 | 450721 | 76.32% |
| V209 | 450721 | 76.32% |
| V210 | 450721 | 76.32% |
| V220 | 449124 | 76.05% |
| V221 | 449124 | 76.05% |
| V222 | 449124 | 76.05% |
| V227 | 449124 | 76.05% |
| V234 | 449124 | 76.05% |
| V238 | 449124 | 76.05% |
| V239 | 449124 | 76.05% |
| V245 | 449124 | 76.05% |
| V250 | 449124 | 76.05% |
| V251 | 449124 | 76.05% |
| V255 | 449124 | 76.05% |
| V256 | 449124 | 76.05% |
| V259 | 449124 | 76.05% |
| V270 | 449124 | 76.05% |
| V271 | 449124 | 76.05% |
| V272 | 449124 | 76.05% |
| dist1 | 352271 | 59.65% |
| M5 | 350482 | 59.35% |
| M7 | 346265 | 58.64% |
| M8 | 346252 | 58.63% |
| M9 | 346252 | 58.63% |
| D5 | 309841 | 52.47% |
| M4 | 281444 | 47.66% |
| D2 | 280797 | 47.55% |
| D11 | 279287 | 47.29% |
| V1 | 279287 | 47.29% |
| V10 | 279287 | 47.29% |
| V11 | 279287 | 47.29% |
| V2 | 279287 | 47.29% |
| V3 | 279287 | 47.29% |
| V4 | 279287 | 47.29% |
| V5 | 279287 | 47.29% |
| V6 | 279287 | 47.29% |
| V7 | 279287 | 47.29% |
| V8 | 279287 | 47.29% |
| V9 | 279287 | 47.29% |
| M1 | 271100 | 45.91% |
| M2 | 271100 | 45.91% |
| M3 | 271100 | 45.91% |
| D3 | 262878 | 44.51% |
| M6 | 169360 | 28.68% |
| V35 | 168969 | 28.61% |
| V36 | 168969 | 28.61% |
| V37 | 168969 | 28.61% |
| V38 | 168969 | 28.61% |
| V39 | 168969 | 28.61% |
| V40 | 168969 | 28.61% |
| V41 | 168969 | 28.61% |
| V42 | 168969 | 28.61% |
| V43 | 168969 | 28.61% |
| V44 | 168969 | 28.61% |
| V45 | 168969 | 28.61% |
| V46 | 168969 | 28.61% |
| V47 | 168969 | 28.61% |
| V48 | 168969 | 28.61% |
| V49 | 168969 | 28.61% |
| V50 | 168969 | 28.61% |
| V51 | 168969 | 28.61% |
| V52 | 168969 | 28.61% |
| D4 | 168922 | 28.60% |
| P_emaildomain | 94456 | 15.99% |
| V75 | 89164 | 15.10% |
| V76 | 89164 | 15.10% |
| V77 | 89164 | 15.10% |
| V78 | 89164 | 15.10% |
| V79 | 89164 | 15.10% |
| V80 | 89164 | 15.10% |
| V81 | 89164 | 15.10% |
| V82 | 89164 | 15.10% |
| V83 | 89164 | 15.10% |
| V84 | 89164 | 15.10% |
| V85 | 89164 | 15.10% |
| V86 | 89164 | 15.10% |
| V87 | 89164 | 15.10% |
| V88 | 89164 | 15.10% |
| V89 | 89164 | 15.10% |
| V90 | 89164 | 15.10% |
| V91 | 89164 | 15.10% |
| V92 | 89164 | 15.10% |
| V93 | 89164 | 15.10% |
| V94 | 89164 | 15.10% |
| D15 | 89113 | 15.09% |
| V53 | 77096 | 13.06% |
| V54 | 77096 | 13.06% |
| V55 | 77096 | 13.06% |
| V56 | 77096 | 13.06% |
| V57 | 77096 | 13.06% |
| V58 | 77096 | 13.06% |
| V59 | 77096 | 13.06% |
| V60 | 77096 | 13.06% |
| V61 | 77096 | 13.06% |
| V62 | 77096 | 13.06% |
| V63 | 77096 | 13.06% |
| V64 | 77096 | 13.06% |
| V65 | 77096 | 13.06% |
| V66 | 77096 | 13.06% |
| V67 | 77096 | 13.06% |
| V68 | 77096 | 13.06% |
| V69 | 77096 | 13.06% |
| V70 | 77096 | 13.06% |
| V71 | 77096 | 13.06% |
| V72 | 77096 | 13.06% |
| V73 | 77096 | 13.06% |
| V74 | 77096 | 13.06% |
| V12 | 76073 | 12.88% |
| V13 | 76073 | 12.88% |
| V14 | 76073 | 12.88% |
| V15 | 76073 | 12.88% |
| V16 | 76073 | 12.88% |
| V17 | 76073 | 12.88% |
| V18 | 76073 | 12.88% |
| V19 | 76073 | 12.88% |
| V20 | 76073 | 12.88% |
| V21 | 76073 | 12.88% |
| V22 | 76073 | 12.88% |
| V23 | 76073 | 12.88% |
| V24 | 76073 | 12.88% |
| V25 | 76073 | 12.88% |
| V26 | 76073 | 12.88% |
| V27 | 76073 | 12.88% |
| V28 | 76073 | 12.88% |
| V29 | 76073 | 12.88% |
| V30 | 76073 | 12.88% |
| V31 | 76073 | 12.88% |
| V32 | 76073 | 12.88% |
| V33 | 76073 | 12.88% |
| V34 | 76073 | 12.88% |
| D10 | 76022 | 12.87% |
| addr1 | 65706 | 11.13% |
| addr2 | 65706 | 11.13% |
| card2 | 8933 | 1.51% |
| card5 | 4259 | 0.72% |
| card4 | 1577 | 0.27% |
| card6 | 1571 | 0.27% |
| card3 | 1565 | 0.27% |
| D1 | 1269 | 0.21% |
| V281 | 1269 | 0.21% |
| V282 | 1269 | 0.21% |
| V283 | 1269 | 0.21% |
| V288 | 1269 | 0.21% |
| V289 | 1269 | 0.21% |
| V296 | 1269 | 0.21% |
| V300 | 1269 | 0.21% |
| V301 | 1269 | 0.21% |
| V313 | 1269 | 0.21% |
| V314 | 1269 | 0.21% |
| V315 | 1269 | 0.21% |
| V100 | 314 | 0.05% |
| V101 | 314 | 0.05% |
| V102 | 314 | 0.05% |
| V103 | 314 | 0.05% |
| V104 | 314 | 0.05% |
| V105 | 314 | 0.05% |
| V106 | 314 | 0.05% |
| V107 | 314 | 0.05% |
| V108 | 314 | 0.05% |
| V109 | 314 | 0.05% |
| V110 | 314 | 0.05% |
| V111 | 314 | 0.05% |
| V112 | 314 | 0.05% |
| V113 | 314 | 0.05% |
| V114 | 314 | 0.05% |
| V115 | 314 | 0.05% |
| V116 | 314 | 0.05% |
| V117 | 314 | 0.05% |
| V118 | 314 | 0.05% |
| V119 | 314 | 0.05% |
| V120 | 314 | 0.05% |
| V121 | 314 | 0.05% |
| V122 | 314 | 0.05% |
| V123 | 314 | 0.05% |
| V124 | 314 | 0.05% |
| V125 | 314 | 0.05% |
| V126 | 314 | 0.05% |
| V127 | 314 | 0.05% |
| V128 | 314 | 0.05% |
| V129 | 314 | 0.05% |
| V130 | 314 | 0.05% |
| V131 | 314 | 0.05% |
| V132 | 314 | 0.05% |
| V133 | 314 | 0.05% |
| V134 | 314 | 0.05% |
| V135 | 314 | 0.05% |
| V136 | 314 | 0.05% |
| V137 | 314 | 0.05% |
| V95 | 314 | 0.05% |
| V96 | 314 | 0.05% |
| V97 | 314 | 0.05% |
| V98 | 314 | 0.05% |
| V99 | 314 | 0.05% |
| V279 | 12 | 0.00% |
| V280 | 12 | 0.00% |
| V284 | 12 | 0.00% |
| V285 | 12 | 0.00% |
| V286 | 12 | 0.00% |
| V287 | 12 | 0.00% |
| V290 | 12 | 0.00% |
| V291 | 12 | 0.00% |
| V292 | 12 | 0.00% |
| V293 | 12 | 0.00% |
| V294 | 12 | 0.00% |
| V295 | 12 | 0.00% |
| V297 | 12 | 0.00% |
| V298 | 12 | 0.00% |
| V299 | 12 | 0.00% |
| V302 | 12 | 0.00% |
| V303 | 12 | 0.00% |
| V304 | 12 | 0.00% |
| V305 | 12 | 0.00% |
| V306 | 12 | 0.00% |
| V307 | 12 | 0.00% |
| V308 | 12 | 0.00% |
| V309 | 12 | 0.00% |
| V310 | 12 | 0.00% |
| V311 | 12 | 0.00% |
| V312 | 12 | 0.00% |
| V316 | 12 | 0.00% |
| V317 | 12 | 0.00% |
| V318 | 12 | 0.00% |
| V319 | 12 | 0.00% |
| V320 | 12 | 0.00% |
| V321 | 12 | 0.00% |
| C1 | 0 | 0.00% |
| C10 | 0 | 0.00% |
| C11 | 0 | 0.00% |
| C12 | 0 | 0.00% |
| C13 | 0 | 0.00% |
| C14 | 0 | 0.00% |
| C2 | 0 | 0.00% |
| C3 | 0 | 0.00% |
| C4 | 0 | 0.00% |
| C5 | 0 | 0.00% |
| C6 | 0 | 0.00% |
| C7 | 0 | 0.00% |
| C8 | 0 | 0.00% |
| C9 | 0 | 0.00% |
| ProductCD | 0 | 0.00% |
| TransactionAmt | 0 | 0.00% |
| TransactionDT | 0 | 0.00% |
| TransactionID | 0 | 0.00% |
| card1 | 0 | 0.00% |
| isFraud | 0 | 0.00% |

### train_identity.csv

| Column | Blank cells | Percent |
| --- | ---: | ---: |
| id_24 | 139486 | 96.71% |
| id_25 | 139101 | 96.44% |
| id_07 | 139078 | 96.43% |
| id_08 | 139078 | 96.43% |
| id_21 | 139074 | 96.42% |
| id_26 | 139070 | 96.42% |
| id_22 | 139064 | 96.42% |
| id_23 | 139064 | 96.42% |
| id_27 | 139064 | 96.42% |
| id_18 | 99120 | 68.72% |
| id_03 | 77909 | 54.02% |
| id_04 | 77909 | 54.02% |
| id_33 | 70944 | 49.19% |
| id_09 | 69307 | 48.05% |
| id_10 | 69307 | 48.05% |
| id_30 | 66668 | 46.22% |
| id_32 | 66647 | 46.21% |
| id_34 | 66428 | 46.06% |
| id_14 | 64189 | 44.50% |
| DeviceInfo | 25567 | 17.73% |
| id_13 | 16913 | 11.73% |
| id_16 | 14893 | 10.33% |
| id_05 | 7368 | 5.11% |
| id_06 | 7368 | 5.11% |
| id_20 | 4972 | 3.45% |
| id_19 | 4915 | 3.41% |
| id_17 | 4864 | 3.37% |
| id_31 | 3951 | 2.74% |
| DeviceType | 3423 | 2.37% |
| id_02 | 3361 | 2.33% |
| id_11 | 3255 | 2.26% |
| id_28 | 3255 | 2.26% |
| id_29 | 3255 | 2.26% |
| id_15 | 3248 | 2.25% |
| id_35 | 3248 | 2.25% |
| id_36 | 3248 | 2.25% |
| id_37 | 3248 | 2.25% |
| id_38 | 3248 | 2.25% |
| TransactionID | 0 | 0.00% |
| id_01 | 0 | 0.00% |
| id_12 | 0 | 0.00% |

## Reproduction and next improvements

See [baseline instructions](BASELINE_MODEL.md), [data workflow](LOCAL_DATA_WORKFLOW.md), and [deployment proof requirements](DEPLOYMENT_PROOF.md). Saved training, profiling, API verification, and container verification programs are in scripts/. Dependencies are locked in uv.lock.

Next: complete feature-distribution and correlation analysis; establish separate calibration and final holdout partitions; compare candidate models under the same split and compute budget; evaluate precision and recall at investigation capacity; add subgroup and temporal stability checks; prove Kubernetes recovery and scaling; validate Terraform apply and no-change plans. Model probabilities remain uncalibrated and no automated enforcement is approved.
