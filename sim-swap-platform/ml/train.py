"""Chronological train/calibration/threshold/holdout pipeline with safe JSON export."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score, confusion_matrix
import xgboost as xgb
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.features import build_features, NAMES, VERSION, dt
from backend.app.decisions import rules, DEFAULT_POLICY


def metrics(y, scores, threshold):
    pred = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0,1]).ravel()
    top = np.argsort(scores)[-max(1, len(y)//20):]
    return {'pr_auc':float(average_precision_score(y,scores)), 'brier':float(brier_score_loss(y,scores)),
            'precision':float(precision_score(y,pred,zero_division=0)), 'recall':float(recall_score(y,pred,zero_division=0)),
            'false_positive_rate':float(fp/max(1,fp+tn)), 'false_positives_per_10000_assessments':float(fp/len(y)*10000),
            'review_fraction':float(pred.mean()), 'recall_at_5_percent_review_capacity':float(y[top].sum()/max(1,y.sum())),
            'confusion_matrix':{'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp)},
            'cost_per_assessment':float((20*fp+1000*fn)/len(y))}


def logit(scores):
    values = np.clip(scores, 1e-6, 1-1e-6)
    return np.log(values/(1-values)).reshape(-1,1)


def train(source, out, reports):
    source = Path(source)
    rows = sorted([json.loads(line) for line in source.read_text().splitlines() if line.strip()], key=lambda r:r['decision_time'])
    # Confirmed mature labels only; unresolved entries are excluded, never converted to negatives.
    rows = [r for r in rows if r.get('label') in (0,1) and r.get('label_time')]
    if len(rows) < 200:
        raise ValueError('At least 200 mature labeled observations required for this pipeline')
    n = len(rows)
    boundaries = [int(n*.6), int(n*.7), int(n*.8)]
    slices = [rows[:boundaries[0]], rows[boundaries[0]:boundaries[1]], rows[boundaries[1]:boundaries[2]], rows[boundaries[2]:]]
    # Purge groups crossing split boundaries. Cohorts must remain sufficiently large after purging.
    seen = set()
    for i, split in enumerate(slices):
        slices[i] = [r for r in split if r['campaign_id'] not in seen]
        seen.update(r['campaign_id'] for r in split)
    # Simulate labels available at the next split boundary, with maturation embargo.
    for i in range(3):
        cutoff = dt(slices[i+1][0]['decision_time'])
        slices[i] = [r for r in slices[i] if dt(r['label_time']) < cutoff]
    xs, ys = [], []
    for split in slices:
        features = [build_features(r['events'], r['decision_time'], r['context'], r['signal']) for r in split]
        for r,f in zip(split,features):
            if 'features' in r and r['features'] != f:
                raise ValueError('Stored features differ from shared point-in-time pipeline')
        xs.append(np.array([[f[name] for name in NAMES] for f in features]))
        ys.append(np.array([r['label'] for r in split]))
        if len(set(ys[-1])) < 2:
            raise ValueError('Both classes required in each split; supply more observations')
    logistic = make_pipeline(StandardScaler(), LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42))
    logistic.fit(xs[0],ys[0])
    boosted = xgb.XGBClassifier(n_estimators=140,max_depth=3,learning_rate=.05,subsample=.8,colsample_bytree=.8,
                               scale_pos_weight=float((ys[0]==0).sum()/max(1,ys[0].sum())),random_state=42,n_jobs=2)
    boosted.fit(xs[0],ys[0])
    anomaly = make_pipeline(StandardScaler(), IsolationForest(n_estimators=100,random_state=42,n_jobs=2))
    anomaly.fit(xs[0][ys[0]==0])
    report = {'synthetic':all(r.get('synthetic',False) for r in rows),'dataset_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'split_sizes':dict(zip(['train','calibration','threshold_validation','holdout'],map(len,slices))),
              'split_method':'chronological; campaign disjoint; labels matured before next boundary',
              'cost_assumptions':{'false_positive':20,'missed_fraud':1000,'currency':'illustrative cost units'},
              'feature_version':VERSION,'models':{}, 'limitation':'Synthetic metrics do not establish real-world effectiveness'}
    output = Path(out)
    output.mkdir(parents=True,exist_ok=True)
    for algorithm, model in [('logistic',logistic),('xgboost',boosted)]:
        raw = [model.predict_proba(x)[:,1] for x in xs[1:]]
        calibration = LogisticRegression(C=1000,random_state=42).fit(logit(raw[0]),ys[1])
        calibrated = [calibration.predict_proba(logit(s))[:,1] for s in raw]
        candidates = np.linspace(.01,.99,99)
        costs = [20*((calibrated[1]>=t)&(ys[2]==0)).sum()+1000*((calibrated[1]<t)&(ys[2]==1)).sum() for t in candidates]
        threshold = float(candidates[int(np.argmin(costs))])
        final_scores = calibrated[2]
        evaluation = metrics(ys[3],final_scores,threshold)
        rng = np.random.default_rng(42)
        boot = []
        for _ in range(200):
            idx = rng.integers(0,len(ys[3]),len(ys[3]))
            if len(set(ys[3][idx])) > 1:
                boot.append(average_precision_score(ys[3][idx],final_scores[idx]))
        evaluation['pr_auc_bootstrap_95_ci'] = np.quantile(boot,[.025,.975]).tolist()
        evaluation['threshold'] = threshold
        evaluation['subgroups'] = {}
        for field in ['operator','scenario']:
            for value in sorted({r[field] for r in slices[3]}):
                mask = np.array([r[field]==value for r in slices[3]])
                evaluation['subgroups'][f'{field}:{value}'] = {'count':int(mask.sum()),'fraud_count':int(ys[3][mask].sum()),
                    'precision':float(precision_score(ys[3][mask],final_scores[mask]>=threshold,zero_division=0)),
                    'recall':float(recall_score(ys[3][mask],final_scores[mask]>=threshold,zero_division=0))}
        seen_subscribers = {r['subscriber'] for r in slices[0]}
        evaluation['subscriber_cohorts'] = {'returning':sum(r['subscriber'] in seen_subscribers for r in slices[3]),
                                            'unseen':sum(r['subscriber'] not in seen_subscribers for r in slices[3])}
        model_id = f'demo-{algorithm}-v1' if report['synthetic'] else f'candidate-{algorithm}-v1'
        folder = output / model_id
        folder.mkdir(exist_ok=True)
        artifact = folder / 'model.json'
        if algorithm == 'logistic':
            scaler, estimator = model.steps[0][1],model.steps[1][1]
            artifact.write_text(json.dumps({'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),
                'coefficients':estimator.coef_[0].tolist(),'intercept':float(estimator.intercept_[0])}))
        else:
            model.save_model(str(artifact))
        manifest = {'algorithm':algorithm,'synthetic':report['synthetic'],'feature_names':NAMES,'feature_version':VERSION,
                    'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'dataset_sha256':report['dataset_sha256'],
                    'stage':'shadow','production_validated':False,'calibration':{'coefficient':float(calibration.coef_[0,0]),
                    'intercept':float(calibration.intercept_[0])},'threshold':threshold,'evaluation':evaluation}
        (folder / 'manifest.json').write_text(json.dumps(manifest,indent=2))
        report['models'][algorithm] = evaluation
        # Export parity: compare native inference artifact with original fitted estimator.
        from backend.app.model_runtime import ModelRuntime
        for index in range(min(20,len(xs[3]))):
            features = dict(zip(NAMES,xs[3][index].tolist()))
            native,_ = ModelRuntime(output).score(model_id,features)
            if abs(native-float(model.predict_proba(xs[3][index:index+1])[0,1])) > 1e-5:
                raise ValueError('Native model export parity failed')
    baseline = np.array([rules(build_features(r['events'],r['decision_time'],r['context'],r['signal']),r['context'],DEFAULT_POLICY)['risk_score']/100 for r in slices[3]])
    report['rules_baseline'] = metrics(ys[3],baseline,.6)
    report['rules_baseline']['brier_note'] = 'Heuristic score; not a calibrated probability'
    report['isolation_forest'] = {'holdout_anomaly_fraction':float((anomaly.predict(xs[3])==-1).mean()),'used_for_decisions':False}
    started = time.perf_counter()
    boosted.predict_proba(xs[3])
    report['batch_inference_ms_per_row'] = (time.perf_counter()-started)/len(xs[3])*1000
    destination = Path(reports)
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'evaluation.json').write_text(json.dumps(report,indent=2))
    (destination/'MODEL_CARD.md').write_text('# Model card\n\n'+
        'Synthetic demonstration models; shadow scoring only. No real operator effectiveness claim.\n\n'+
        'Shared features: '+', '.join(NAMES)+'\n\n'+
        'Chronological train, calibration, threshold validation, and holdout splits; campaign purging and label maturity embargo. '+
        'Synthetic customers are unique across splits; returning-subscriber generalization is not measured.\n\n'+
        'Adjudication and selection bias remain external data-governance requirements. '+
        'Policies use rules; calibrated synthetic outputs are still not real fraud probabilities.\n\n'+
        'See evaluation.json for measured metrics and bootstrap intervals. Artifact export parity was checked on 20 holdout observations per model.\n')
    print(json.dumps({'split_sizes':report['split_sizes'],'models':{k:{m:v[m] for m in ['pr_auc','precision','recall']} for k,v in report['models'].items()}},indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',default='data/synthetic.jsonl')
    parser.add_argument('--artifacts',default='artifacts')
    parser.add_argument('--reports',default='reports')
    args = parser.parse_args()
    train(args.input,args.artifacts,args.reports)
