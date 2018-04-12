from datetime import timedelta, datetime
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.auth import HTTPBasicAuth
from pprint import pprint
import yaml
import json
import salt.client
import salt.config
import salt.runner

def put_device_in_maintenance(dev):
 opts = salt.config.master_config('/etc/salt/master')
 caller = salt.client.Caller()
 local_minion_id = caller.cmd('grains.get', 'id')
 runner = salt.runner.RunnerClient(opts)
 pillar = runner.cmd('pillar.show_pillar', [local_minion_id])
 url = pillar['northstar']['url']
 maintenance_event_duration = pillar['northstar']['maintenance_event_duration']
 url_base = pillar['northstar']['url_base']
 authuser = pillar['northstar']['authuser']
 authpwd = pillar['northstar']['authpwd']
 requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
 headers = { 'content-type' : 'application/json'}
 data_to_get_token = {"grant_type":"password","username":authuser,"password":authpwd}
 r = requests.post(url, data=json.dumps(data_to_get_token), auth=(authuser, authpwd), headers=headers, verify=False)
 headers = {'Authorization':str('Bearer ' + r.json()['access_token']), 'Accept' : 'application/json', 'Content-Type' : 'application/json'}
 url = url_base + '1/topology/1/nodes'
 r = requests.get(url, headers=headers, verify=False)
 for i in r.json():
   if i['hostName'] == dev:
    node_index = i['nodeIndex']
 maintenance_url = url_base + '1/topology/1/maintenances'
 maintenance_data = {
     "topoObjectType": "maintenance",
     "topologyIndex": 1,
     "user": "admin",
     "name": "event_" + dev,
     "startTime": datetime.now().isoformat(),
     "endTime": (datetime.now() + timedelta(minutes=maintenance_event_duration)).isoformat(),
     "elements": [{"topoObjectType": "node", "index": node_index}]
     }
 m_res = requests.post(maintenance_url, data=json.dumps(maintenance_data), headers=headers, verify=False)
 return "done"
