"""Kafka -> authenticated ingestion. API deduplication makes replay safe; no offset commit before success."""
import hashlib
import json
import os
import signal
import time
import httpx
from confluent_kafka import Consumer, Producer


def main():
    tenant=os.environ['KAFKA_TENANT']
    config={'bootstrap.servers':os.environ['KAFKA_BOOTSTRAP'], 'group.id':f'sim-shield-{tenant}',
            'enable.auto.commit':False,'auto.offset.reset':'earliest','max.poll.interval.ms':300000}
    if os.getenv('KAFKA_SASL_USERNAME'):
        config.update({'security.protocol':'SASL_SSL','sasl.mechanism':'SCRAM-SHA-512',
                       'sasl.username':os.environ['KAFKA_SASL_USERNAME'],'sasl.password':os.environ['KAFKA_SASL_PASSWORD']})
    consumer=Consumer(config)
    producer=Producer({k:v for k,v in config.items() if k not in ['group.id','enable.auto.commit','auto.offset.reset','max.poll.interval.ms']})
    topic=os.environ['KAFKA_TOPIC']
    dlq=topic+'.dead-letter'
    client=httpx.Client(base_url=os.environ['API_URL'],headers={'Authorization':'Bearer '+os.environ['INTEGRATION_TOKEN']},timeout=10)
    running=True
    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    consumer.subscribe([topic])
    try:
        while running:
            msg=consumer.poll(1)
            if msg is None:continue
            if msg.error():
                time.sleep(1);continue
            while running:
                try:
                    payload=json.loads(msg.value())
                    response=client.post('/api/v1/events',json=payload)
                    if response.status_code==201:
                        consumer.commit(message=msg,asynchronous=False)
                        break
                    if response.status_code in {409,422}:
                        # Do not copy raw phone numbers/secrets to DLQ. Retain source pointer and digest for approved replay.
                        envelope={'topic':msg.topic(),'partition':msg.partition(),'offset':msg.offset(),
                                  'sha256':hashlib.sha256(msg.value()).hexdigest(),'tenant':tenant,
                                  'error':'schema_or_id_conflict','original_payload_retained_in_source':True}
                        delivered=[]
                        producer.produce(dlq,json.dumps(envelope).encode(),callback=lambda err,_:delivered.append(err))
                        producer.flush(10)
                        if not delivered or delivered[0] is not None:raise RuntimeError('DLQ delivery failed')
                        consumer.commit(message=msg,asynchronous=False)
                        break
                    if response.status_code in {401,403}:
                        raise SystemExit('Integration token invalid, expired, or unauthorized; no offset committed')
                    time.sleep(2)
                except json.JSONDecodeError:
                    raise SystemExit('Invalid JSON; offset retained for operator remediation')
                except (httpx.HTTPError,RuntimeError):
                    time.sleep(2)
    finally:
        consumer.close();client.close()


if __name__=='__main__':main()
