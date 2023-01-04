import base64
import gzip
import json
import os
import pytz
import re

from datetime import datetime
from elasticsearch import Elasticsearch
from elasticsearch import helpers

def lambda_handler(event, context):
  es_host = os.environ.get("ES_HOST")
  es_port = os.environ.get("ES_PORT")
  # Password for the 'elastic' user generated by Elasticsearch
  es_password = os.environ.get("ES_PASS")

  # Connect to Elasticsearch with HTTPS and bypass the cert validation
  es = Elasticsearch(
    [
      {
        'host':str(es_host),
        'port':int(es_port),
        'scheme': "https"
      }
    ],
    basic_auth=("elastic", str(es_password)),
    verify_certs=False
  )

  # Successful response!
  if not es.ping():
    raise ValueError("Connection failed")
  else:
    es.info()

  # Get event log from CloudWatch
  cw_data = event['awslogs']['data']
  compressed_payload = base64.b64decode(cw_data)
  uncompressed_payload = gzip.decompress(compressed_payload)
  payload = json.loads(uncompressed_payload)
  log_events = payload['logEvents']

  for log in log_events:
    # Parse the log content and get the required content in the message
    ts = datetime.fromtimestamp(int(log['timestamp'])/1000).replace(tzinfo=pytz.utc)
    query_time_start = str([line for line in log['message'].split('\n') if "# Time:" in line]).split('Time: ')[1].replace("']", "")
    client_user = str([line for line in log['message'].split('\n') if "# User@Host:" in line]).split('User@Host: ')[1].split()[0].split('[', 1)[1].split(']')[0]
    client_host = str([line for line in log['message'].split('\n') if "# User@Host:" in line]).split('User@Host: ')[1].split()[2].split('[', 1)[1].split(']')[0]
    query_time_long = str([line for line in log['message'].split('\n') if "# Query_time:" in line]).split('Query_time: ')[1].split()[0]
    query_lock_time = str([line for line in log['message'].split('\n') if "# Query_time:" in line]).split('Query_time: ')[1].split()[2]
    rows_sent = str([line for line in log['message'].split('\n') if "# Query_time:" in line]).split('Query_time: ')[1].split()[4]
    rows_examined = str([line for line in log['message'].split('\n') if "# Query_time:" in line]).split('Query_time: ')[1].split()[6].replace("']", "")
    query = re.sub(r"\/.*?\/", "", str([line for line in log['message'].split('\n') if not(line.startswith('# '))])).replace("']", '').replace('"]', '').replace("['", '').replace('["', '').replace(";', '", "; ").replace(";'", ";").replace(';, "', '; ')

    # Message will be pushed to Elasticsearch with the above parsed information
    message = {
      "@timestamp": ts,
      "account_id": payload['owner'],
      "log_group": payload['logGroup'],
      "log_stream": payload['logStream'],
      "subscription_filters": payload['subscriptionFilters'],
      "@message": log['message'],
      "query_time_start": query_time_start,
      "client_user": client_user,
      "client_host": client_host,
      "query_time_long": query_time_long,
      "query_lock_time": query_lock_time,
      "rows_sent": rows_sent,
      "rows_examined": rows_examined,
      "query": query
    }
    now = datetime.now()
    # Create new index on Elasticsearch and push message
    es.index(index='{}-{}.{}'.format(os.environ.get("LogIndex"),now.year,now.isocalendar()[1]), body=message)

  return {
    'statusCode': 200,
    'body' : 'Hello from Lambda!',
  }