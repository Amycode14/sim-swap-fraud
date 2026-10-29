"""Offline feature drift report: never changes decisions or promotes models."""
import argparse
import json
from pathlib import Path
import numpy as np


def psi(reference,current,bins=10):
    reference=np.asarray(reference,dtype=float);current=np.asarray(current,dtype=float)
    edges=np.unique(np.quantile(reference,np.linspace(0,1,bins+1)))
    if len(edges)<2:
        return float(abs(np.mean(current != reference[0])))
    edges[0]=-np.inf;edges[-1]=np.inf
    expected=np.histogram(reference,bins=edges)[0]/len(reference)
    actual=np.histogram(current,bins=edges)[0]/max(1,len(current))
    expected=np.clip(expected,1e-6,None);actual=np.clip(actual,1e-6,None)
    return float(np.sum((actual-expected)*np.log(actual/expected)))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reference',required=True)
    parser.add_argument('--current',required=True)
    parser.add_argument('--output',default='reports/drift.json')
    args=parser.parse_args()
    def load(path):return [json.loads(line)['features'] for line in Path(path).read_text().splitlines() if line.strip()]
    reference=load(args.reference);current=load(args.current)
    report={'features':{name:psi([r[name] for r in reference],[r[name] for r in current]) for name in reference[0]},
            'reference_count':len(reference),'current_count':len(current),'automatic_actions':False,
            'interpretation':'PSI heuristic; investigate changes in coverage and cohort before interpreting as model degradation'}
    Path(args.output).write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
