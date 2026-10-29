"""Export adjudicated feature snapshots for a future dataset; unresolved cases never become negative labels."""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.db import make_engine,session_factory,records,find
parser=argparse.ArgumentParser()
parser.add_argument('--tenant',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
Session=session_factory(make_engine(os.environ['DATABASE_URL']))
rows=[]
with Session() as db:
    for record in records(db,args.tenant,'case'):
        case=record.data
        if case['status'] not in {'resolved_fraud','resolved_legitimate'} or case['label'] not in [0,1]:continue
        assessment=find(db,args.tenant,'assessment',case['assessment_id'])
        if not assessment:continue
        value=assessment.data
        rows.append({'assessment_id':value['assessment_id'],'decision_time':value['assessed_at'],
                     'subscriber':value['subscriber'],'features':value['features'],'context':value['context'],
                     'signal':value['signal'],'feature_version':value['feature_version'],'label':case['label'],
                     'label_time':case['label_provenance']['time'],'label_provenance':case['label_provenance'],
                     'synthetic':value['demo'],
                     'limitation':'Review-selected cohort. Reconstruct historical events using ingestion clock before training.'})
Path(args.output).write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
print(f'Exported {len(rows)} adjudicated snapshots. Protect the output as tenant data.')
