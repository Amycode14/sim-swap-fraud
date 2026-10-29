"""Optional remote registry/storage publishing. No live service credentials bundled."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
import httpx


def publish_mlflow(report,url,token):
    client=httpx.Client(base_url=url,headers={'Authorization':'Bearer '+token} if token else {},timeout=10)
    response=client.get('/api/2.0/mlflow/experiments/get-by-name',params={'experiment_name':'sim-shield'})
    if response.status_code==404:
        response=client.post('/api/2.0/mlflow/experiments/create',json={'name':'sim-shield'})
    response.raise_for_status()
    data=response.json();experiment_id=data.get('experiment_id',data.get('experiment',{}).get('experiment_id'))
    created=client.post('/api/2.0/mlflow/runs/create',json={'experiment_id':experiment_id,'start_time':int(time.time()*1000),
        'tags':[{'key':'synthetic','value':str(report['synthetic']).lower()},{'key':'dataset_sha256','value':report['dataset_sha256']},
                {'key':'feature_version','value':report['feature_version']},{'key':'deployment_stage','value':'shadow'}]})
    created.raise_for_status();run_id=created.json()['run']['info']['run_id']
    values=[{'key':algorithm+'_'+metric,'value':value,'timestamp':int(time.time()*1000),'step':0}
            for algorithm,metrics in report['models'].items() for metric,value in metrics.items() if isinstance(value,(int,float))]
    result=client.post('/api/2.0/mlflow/runs/log-batch',json={'run_id':run_id,'metrics':values})
    result.raise_for_status()
    client.post('/api/2.0/mlflow/runs/update',json={'run_id':run_id,'status':'FINISHED','end_time':int(time.time()*1000)}).raise_for_status()
    client.close()
    return run_id


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mlflow',action='store_true')
    parser.add_argument('--s3',action='store_true')
    args=parser.parse_args()
    if args.mlflow:
        report=json.loads(Path('reports/evaluation.json').read_text())
        run_id=publish_mlflow(report,os.environ['MLFLOW_URL'],os.getenv('MLFLOW_TOKEN',''))
        print('MLflow run registered:',run_id)
    if args.s3:
        import boto3
        client=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT'))
        bucket=os.environ['S3_BUCKET']
        prefix=os.environ.get('S3_PREFIX','sim-shield')
        # AWS SDK environment/role credential chain; no keys in code or logs.
        for path in list(Path('artifacts').glob('*/*.json'))+list(Path('reports').glob('*.json')):
            payload=path.read_bytes()
            digest=hashlib.sha256(payload).hexdigest()
            client.put_object(Bucket=bucket,Key=f'{prefix}/{digest}/{path.as_posix()}',Body=payload,
                              Metadata={'sha256':digest},ServerSideEncryption='AES256')
        print('Artifacts published. Configure bucket versioning, access controls, and lifecycle separately.')


if __name__=='__main__':main()
