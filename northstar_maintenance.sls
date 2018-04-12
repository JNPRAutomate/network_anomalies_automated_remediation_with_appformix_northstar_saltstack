{% set body_json = data['body']|load_json %}
{% set devicename = body_json['status']['entityId'] %}
test_event:
  runner.northstar.put_device_in_maintenance:
    - args:
       - dev: {{ devicename }}
