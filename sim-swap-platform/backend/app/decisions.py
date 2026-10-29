DEFAULT_POLICY = {'name': 'conservative-demo', 'step_up': 30, 'review': 60, 'hold': 85,
                  'unknown_sensitive_action': 'STEP_UP', 'assessment_ttl': 120, 'version': 'policy-1'}


def rules(features, context, policy):
    reasons = []
    score = 0
    recent = features['sim_age_hours'] < 24 or features['port_recent'] or features['network_recent']
    if recent:
        score += 25
        reasons.append('RECENT_SIM_OR_PORT_CHANGE')
    if features['new_device']:
        score += 15
        reasons.append('UNFAMILIAR_DEVICE')
    if recent and (features['recovery_recent'] or context['action'] == 'recovery'):
        score += 30
        reasons.append('RECOVERY_AFTER_CHANGE')
    if recent and features['new_beneficiary']:
        score += 25
        reasons.append('NEW_BENEFICIARY_AFTER_CHANGE')
    if features['sim_changes_24h'] > 1 or features['requests_24h'] > 2:
        score += 25
        reasons.append('REPEATED_REPLACEMENTS')
    if features['failed_logins_1h'] >= 5:
        score += 15
        reasons.append('AUTH_FAILURE_VELOCITY')
    if features['amount_ratio'] > 5:
        score += 20
        reasons.append('UNUSUAL_AMOUNT')
    if features['transactions_1h'] > 5:
        score += 15
        reasons.append('TRANSACTION_VELOCITY')
    if features['signal_missing']:
        reasons.append('NETWORK_SIGNAL_UNAVAILABLE')
    if features['cold_start']:
        reasons.append('INSUFFICIENT_HISTORY')
    # A trusted-device flag is diagnostic, never proof sufficient to cancel strong fraud signals.
    score = min(100, score)
    action = ('TEMPORARY_HOLD' if score >= policy['hold'] else 'REVIEW' if score >= policy['review']
              else 'STEP_UP' if score >= policy['step_up'] else 'ALLOW')
    if features['signal_missing'] and context['action'] in {'transaction', 'recovery', 'beneficiary_change', 'sim_replacement'} and action == 'ALLOW':
        action = policy['unknown_sensitive_action']
    band = 'high' if score >= policy['review'] else 'medium' if score >= policy['step_up'] else 'low'
    return {'risk_score': score, 'risk_score_meaning': 'Heuristic policy score, not a fraud probability',
            'risk_band': band, 'recommendation': action, 'reason_codes': reasons,
            'step_up_options': ['existing_trusted_device', 'passkey', 'independently_verified_recovery'] if action != 'ALLOW' else []}
