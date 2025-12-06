import json
from pprint import pprint

import requests
from decouple import config
from requests.auth import HTTPBasicAuth

cli_url = "http://10.10.20.49:8080/restconf/data/tailf-ncs:devices/device=core-rtr01/live-status/tailf-ned-cisco-ios-xr-stats:exec/any"
user = config("NSO_USER")
passwd = config("NSO_PW")

payload = json.dumps({"input": {"args": "show ip interface brief"}})
headers = {"Accept": "application/yang-data+json", "Content-Type": "application/yang-data+json"}

response = requests.post(cli_url, headers=headers, auth=HTTPBasicAuth(user, passwd), data=payload)
pprint(json.loads(response.text))

# print(response.text)
