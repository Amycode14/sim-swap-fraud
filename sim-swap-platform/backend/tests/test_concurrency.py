from concurrent.futures import ThreadPoolExecutor
from .conftest import headers,assessment


def test_concurrent_assessments_do_not_starve_request_workers(client):
    def submit(index):
        response=client.post('/api/v1/assessments',json=assessment(action_id=f'concurrent-{index}'),
                             headers={**headers(),'Idempotency-Key':f'concurrent-key-{index}'})
        return response.status_code
    with ThreadPoolExecutor(max_workers=48) as pool:
        statuses=list(pool.map(submit,range(60)))
    assert statuses==[201]*60
    assert client.get('/api/v1/audit',headers=headers()).json()['chain_valid']
