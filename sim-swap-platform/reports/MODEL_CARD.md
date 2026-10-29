# Model card

Synthetic demonstration models; shadow scoring only. No real operator effectiveness claim.

Shared features: sim_age_hours, sim_changes_24h, requests_24h, port_recent, new_device, recovery_recent, new_beneficiary, failed_logins_1h, transactions_1h, amount_ratio, tenure_days, signal_missing, trusted_device, cold_start, network_recent

Chronological train, calibration, threshold validation, and holdout splits; campaign purging and label maturity embargo. Synthetic customers are unique across splits; returning-subscriber generalization is not measured.

Adjudication and selection bias remain external data-governance requirements. Policies use rules; calibrated synthetic outputs are still not real fraud probabilities.

See evaluation.json for measured metrics and bootstrap intervals. Artifact export parity was checked on 20 holdout observations per model.
