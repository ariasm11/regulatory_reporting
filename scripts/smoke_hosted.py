"""Check the CI container's health, HTTPS cookie and authenticated API."""
import http.client
import json
import time

for attempt in range(30):
    try:
        c=http.client.HTTPConnection('127.0.0.1',18000,timeout=2)
        c.request('GET','/healthz');r=c.getresponse();r.read();c.close()
        if r.status==200: break
    except OSError: pass
    time.sleep(1)
else: raise RuntimeError('Container did not become healthy')
c=http.client.HTTPConnection('127.0.0.1',18000,timeout=10)
body=json.dumps({'username':'smoketest','password':'ci-smoke-test-password'})
c.request('POST','/api/login',body,{'Host':'demo.example','Origin':'https://demo.example','Content-Type':'application/json'})
r=c.getresponse();payload=json.loads(r.read());cookie=r.getheader('Set-Cookie','');c.close()
assert r.status==200,(r.status,payload)
assert 'Secure' in cookie and 'HttpOnly' in cookie
c=http.client.HTTPConnection('127.0.0.1',18000,timeout=10)
c.request('GET','/api/config',headers={'Host':'demo.example','Cookie':cookie.split(';')[0]})
r=c.getresponse();data=json.loads(r.read());c.close()
assert r.status==200 and data['contract']['version']=='csv-v1'
print('Hosted container: health, bootstrap, secure session and authenticated config passed.')
