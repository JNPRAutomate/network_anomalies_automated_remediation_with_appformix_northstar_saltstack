
#### Overview:  
Appformix is used for network devices monitoring. Based on Appformix webhook notifications to Salt master, automatically make REST calls to Northstar SDN controller to put the "faulty" device in maintenance mode. The "faulty" device will be considered logically down for a certain amount time, and the SDN controller will reroute the LSPs around this device during the maintenance period. After the maintenance period, LSPs are reverted back to optimal paths. 

#### Building blocks: 

- Juniper devices
- Northstar SDN controller. Version 4 or above is required
- Appformix
- SaltStack based

#### webhooks Overview: 

- A webhook is notification using an HTTP POST. A webhook is sent by a system A to push data (json body as example) to a system B when an event occurred in the system A. Then the system B will decide what to do with these details. Usage is event driven automation.
- Appformix supports webhooks. A notification is generated when the condition of an alarm is observed. You can configure an alarm to post notifications to an external HTTP endpoint. AppFormix will post a JSON payload to the endpoint for each notification.
- SaltStack can listens to webhooks and generate equivalents ZMQ messages to the event bus  
- SaltStack can reacts to webhooks (Event driven automation)  

#### Building blocks role: 

- Appformix:  
    - it collects data from Junos devices.
    - it generates webhooks notifications (HTTP POST with a JSON body) to SaltStack when the condition of an alarm is observed. The JSON body provides the device name and other details. 

- SaltStack: 
    - Only the master is required.   
    - it listens to webhooks 
    - it generates a ZMQ messages to the event bus when a webhook notification is received. The ZMQ message has a tag and data. The data structure is a dictionary, which contains information about the event.
    - the reactor binds sls files to event tags. The reactor has a list of event tags to be matched, and each event tag has a list of reactor SLS files to be run. So these sls files define the SaltStack reactions. 
    - the sls file used in this content does the following: it parses the data from the ZMQ message and extracts the network device name. it then passes the data extracted the ZMQ message to a runner and execute the runner. The runner makes REST calls to Northstar SDN controller to put the "faulty" device in maintenance mode. 

- Northstar: 
    - Handle the REST calls received by SaltStack, i.e put the "faulty" device in maintenance mode. The "faulty" device will be considered logically down for a certain amount time, and Northstar will reroute the LSPs around this device during the maintenance period. After the maintenance period, LSPs are reverted back to optimal paths. 

#### Requirements: 

- Install appformix
- Configure appformix for network devices monitoring
- Install northstar (version 4 or above)
- Add the same network devices to northstar 

#### How to use this content: 

##### Install Appformix  
This is not covered by this documentation

##### Configure Appformix for network devices monitoring  
This is not covered by this documentation

##### Install Northstar (version 4 or above)  
This is not covered by this documentation

##### Add the same network devices to Northstar  
This is not covered by this documentation

##### Install SaltStack
This is not covered by this documentation

##### Configure the Salt master configuration file

ssh to the Salt master and open the salt master configuration file:  
```
more /etc/salt/master
```

make sure the master configuration file has these details:  
```
runner_dirs:
  - /srv/runners
```
```
engines:
  - webhook:
      port: 5001
```
```
ext_pillar:
  - git:
    - master git@gitlab:nora_ops/network_parameters.git
```

So: 
    - the Salt master is listening webhooks on port 5001. It generates equivalents ZMQ messages to the event bus
    - runners are in the directory ```/srv/runners``` on the Salt master
    - pillars (humans defined variables) are in the gitlab repository ```nora_ops/network_parameters``` (root/password, master branch)


##### Update the Salt external pillars

Create a file ```northstar.sls``` at the root of the  external pillars gitlab repository (```nora_ops/network_parameters```) with this content: 
```
northstar: 
    authuser: 'admin'
    authpwd: 'juniper123'
    url: 'https://192.168.128.173:8443/oauth2/token'
    url_base: 'http://192.168.128.173:8091/NorthStar/API/v2/tenant/'
    maintenance_event_duration: 60
```
The runner that SaltStack will execute to make REST calls to northstar will use these variables.  

screenshot

For the ```northstar.sls``` file to be actually used, update the ```top.sls``` file at the root of the gitlab repository ```nora_ops/network_parameters``` with this content: 

```
{% set id = salt['grains.get']('id') %} 
{% set host = salt['grains.get']('host') %} 

base:
  '*':
    - production
    - northstar

{% if host == '' %}
  '{{ id }}':
    - {{ id }}
{% endif %}
```

screenshot

##### Update the Salt reactor
The reactor binds sls files to event tags. The reactor has a list of event tags to be matched, and each event tag has a list of reactor SLS files to be run. So these sls files define the SaltStack reactions.  
Update the reactor.  
This reactor binds ```salt/engines/hook/appformix_to_saltstack``` to ```/srv/reactor/northstar_maintenance.sls``` 

```
# more /etc/salt/master.d/reactor.conf
reactor:
   - 'salt/engines/hook/appformix_to_saltstack':
       - /srv/reactor/northstar_maintenance.sls

```

Restart the Salt master:
```
service salt-master stop
service salt-master start
```

The command ```salt-run reactor.list``` lists currently configured reactors:  
```
salt-run reactor.list
event:
    ----------
    _stamp:
        2018-04-10T13:40:12.062140
suffix:
    salt/reactors/manage/list
|_
  ----------
  salt/engines/hook/appformix_to_saltstack:
      - /srv/reactor/northstar_maintenance.sls
```

##### Create the reactor sls file 

The sls reactor file ```/srv/reactor/northstar_maintenance.sls``` parses the data from the ZMQ message that has the tags ```salt/engines/hook/appformix_to_saltstack``` and extracts the network device name.  
It then passes the data extracted the ZMQ message to the python function ```put_device_in_maintenance``` of the ```northstar``` runner and execute the python function. 

```
# more /srv/reactor/northstar_maintenance.sls
{% set body_json = data['body']|load_json %}
{% set devicename = body_json['status']['entityId'] %}
test_event:
  runner.northstar.put_device_in_maintenance:
    - args:
       - dev: {{ devicename }}
```

##### Create the Salt runner
As you can see in the Salt master configuration file ```/etc/salt/master```, the runners directory is ```/srv/runners/``` 
So the runner ```northstar``` is ```/srv/runners/northstar.py```  

This runner defines a python function ```put_device_in_maintenance```
The python function makes REST calls to Northstar SDN controller to put a device in maintenance mode.  

The device will be considered logically down for a certain amount time, and the SDN controller will reroute the LSPs around this device during the maintenance period. After the maintenance period, LSPs are reverted back to optimal paths. 

```
# more /srv/runners/northstar.py
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
```

You can test manually the runner.  
```
salt-run northstar.put_device_in_maintenance dev=core-rtr-p-02
```

Then log in to the Northstar GUI and verify in the ```topology``` menu if the device ```core-rtr-p-02``` is in maintenance. 

screenshot


##### Run the event driven northstar automation demo: 

- Create Appformix webhook notifications.  

You can do it from Appformix GUI, settings, Notification Settings, Notification Services, add service.    
Then:  
service name: provide the name appformix_to_saltstack  
URL endpoint: provide the Salt master IP and Salt webhook listerner port (```HTTP://192.168.128.174:5001/appformix_to_saltstack``` as example).  
setup  

screenshot

- Create Appformix alarms, and map these alarms to the webhook you just created.

You can do it from the Appformix GUI, Alarms, add rule.  
Then, as example:   
Name: use in_unicast_packets_core-rtr-p-02,  
Module: select Alarms,  
Alarm rule type: select Static,  
scope: select network devices,  
network device/Aggregate: select core-rtr-p-02,  
generate: select generate alert,  
For metric: select interface_in_unicast_packets,  
When: select Average,  
Interval(seconds): use 60,  
Is: select Above,  
Threshold(Packets/s): use 300,  
Severity: select Warning,  
notification: select custom service,  
services: select the service name you created (appformix_to_saltstack),  
save.

- Watch webhook notifications and ZMQ messages  

Run this command on the master to see webhook notifications:
```
# tcpdump port 5001 -XX 
```

Salt provides a runner that displays events in real-time as they are received on the Salt master:  
```
# salt-run state.event pretty=True
```

- Trigger an alarm  to get a webhook notification sent by Appformix to SaltStack 
```
salt "core-rtr-p-02" junos.rpc 'ping' rapid=True
```
- Verify on SaltStack 

Have a look at the tcpdump output 

Have a look at the the ZMQ messages

```
# salt-run state.event pretty=True
salt/engines/hook/appformix_to_saltstack        {
    "_stamp": "2018-04-06T16:43:39.866009",
    "body": "{\"status\": {\"description\": \"NetworkDevice core-rtr-p-02: average ifInUcastPkts above 300 {u'ge-0/0/4_0': {u'sample_value': 15.48, u'status': u'inactive'}, u'demux0': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/5': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/4': {u'sample_value': 15.48, u'status': u'inactive'}, u'ge-0/0/3': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/2': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/1': {u'sample_value': 17.78, u'status': u'active'}, u'ge-0/0/0': {u'sample_value': 0, u'status': u'inactive'}, u'pfe-0/0/0_16383': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/9': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/8': {u'sample_value': 0, u'status': u'inactive'}, u'fxp0_0': {u'sample_value': 98.63, u'status': u'inactive'}, u'tap': {u'sample_value': 0, u'status': u'inactive'}, u'em1_0': {u'sample_value': 844.7, u'status': u'active'}, u'pfh-0/0/0_16384': {u'sample_value': 0, u'status': u'inactive'}, u'pip0': {u'sample_value': 0, u'status': u'inactive'}, u'pimd': {u'sample_value': 0, u'status': u'inactive'}, u'mtun': {u'sample_value': 0, u'status': u'inactive'}, u'gre': {u'sample_value': 0, u'status': u'inactive'}, u'em1': {u'sample_value': 844.7, u'status': u'active'}, u'em2': {u'sample_value': 0, u'status': u'inactive'}, u'lc-0/0/0': {u'sample_value': 0, u'status': u'inactive'}, u'irb': {u'sample_value': 0, u'status': u'inactive'}, u'lo0_16385': {u'sample_value': 47.6, u'status': u'inactive'}, u'dsc': {u'sample_value': 0, u'status': u'inactive'}, u'fxp0': {u'sample_value': 98.63, u'status': u'inactive'}, u'vtep': {u'sample_value': 0, u'status': u'inactive'}, u'cbp0': {u'sample_value': 0, u'status': u'inactive'}, u'jsrv': {u'sample_value': 0, u'status': u'inactive'}, u'rbeb': {u'sample_value': 0, u'status': u'inactive'}, u'lo0_0': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/7': {u'sample_value': 0, u'status': u'inactive'}, u'pp0': {u'sample_value': 0, u'status': u'inactive'}, u'pfh-0/0/0': {u'sample_value': 0, u'status': u'inactive'}, u'pfe-0/0/0': {u'sample_value': 0, u'status': u'inactive'}, u'lsi': {u'sample_value': 0, u'status': u'inactive'}, u'pfh-0/0/0_16383': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/1_0': {u'sample_value': 17.78, u'status': u'active'}, u'lc-0/0/0_32769': {u'sample_value': 0, u'status': u'inactive'}, u'NetworkDeviceId': u'core-rtr-p-02', u'ipip': {u'sample_value': 0, u'status': u'inactive'}, u'lo0_16384': {u'sample_value': 0, u'status': u'inactive'}, u'ge-0/0/6': {u'sample_value': 0, u'status': u'inactive'}, u'lo0': {u'sample_value': 47.6, u'status': u'inactive'}, u'pime': {u'sample_value': 0, u'status': u'inactive'}, u'esi': {u'sample_value': 0, u'status': u'inactive'}, u'em2_32768': {u'sample_value': 0, u'status': u'inactive'}, u'jsrv_1': {u'sample_value': 0, u'status': u'inactive'}}\", \"timestamp\": 1523033019000, \"entityType\": \"network_device\", \"state\": \"active\", \"entityDetails\": {}, \"entityId\": \"core-rtr-p-02\", \"metaData\": {}}, \"kind\": \"Alarm\", \"spec\": {\"aggregationFunction\": \"average\", \"intervalDuration\": 60, \"severity\": \"warning\", \"module\": \"alarms\", \"intervalCount\": 1, \"metricType\": \"ifInUcastPkts\", \"name\": \"ping_in_unicast_packets\", \"eventRuleId\": \"f9e6102e-39b8-11e8-b8ce-0242ac120005\", \"mode\": \"alert\", \"intervalsWithException\": 1, \"threshold\": 300, \"comparisonFunction\": \"above\"}, \"apiVersion\": \"v1\"}",
    "headers": {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Content-Length": "3396",
        "Content-Type": "application/json",
        "Host": "192.168.128.174:5001",
        "User-Agent": "python-requests/2.18.4"
    }
}
salt/run/20180406164340760297/new       {
    "_stamp": "2018-04-06T16:43:40.762533",
    "fun": "runner.northstar.put_device_in_maintenance",
    "fun_args": [
        {
            "dev": "core-rtr-p-02"
        }
    ],
    "jid": "20180406164340760297",
    "user": "Reactor"
}
...
...
...
salt/run/20180406164340760297/ret       {
    "_stamp": "2018-04-06T16:43:43.143082",
    "fun": "runner.northstar.put_device_in_maintenance",
    "fun_args": [
        {
            "dev": "core-rtr-p-02"
        }
    ],
    "jid": "20180406164340760297",
    "return": "done",
    "success": true,
    "user": "Reactor"
}
```
- Verify on Northstar 

Then log in to the Northstar GUI and verify in the topology menu if the device core-rtr-p-02 is in maintenance. 

screenshot

