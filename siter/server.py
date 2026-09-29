"""Authenticated single-process demo server. Only anonymized data; no ARCA submission."""
import argparse
import getpass
import hmac
import json
import mimetypes
import os
import threading
import time
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .common import ROOT, load
from .contracts import template_zip, sample_files
from .service import Service, Problem

MAX_BODY=24*1024*1024
ASSETS={'/':'workspace.html','/workspace.html':'workspace.html','/workspace.js':'workspace.js',
        '/workspace.css':'workspace.css','/styles.css':'styles.css','/index.html':'index.html','/app.js':'app.js'}


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,service,origin):
        self.service=service;self.origin=origin;self.secure=origin.startswith('https://')
        self.attempts=defaultdict(deque);self.rate_lock=threading.Lock();self.last_cleanup=0
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(address,Handler)

    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            request.close();return
        try: super().process_request(request,address)
        except Exception:
            self.slots.release();raise

    def process_request_thread(self,request,address):
        try: super().process_request_thread(request,address)
        finally: self.slots.release()

    def service_actions(self):
        if time.time()-self.last_cleanup>60:
            self.service.cleanup();self.last_cleanup=time.time()

    def throttle_login(self,address):
        with self.rate_lock:
            now=time.time()
            for key in list(self.attempts):
                while self.attempts[key] and self.attempts[key][0]<now-300: self.attempts[key].popleft()
                if not self.attempts[key]: del self.attempts[key]
            attempts=self.attempts[address]
            if len(attempts)>=10: raise Problem(429,'Too many login attempts; wait five minutes')
            attempts.append(now)


class Handler(BaseHTTPRequestHandler):
    server_version='SITER'
    sys_version=''
    def setup(self):
        super().setup();self.connection.settimeout(30)

    def log_message(self,*args):
        # Do not write paths, user data, cookies or request bodies to stdout.
        pass

    def send(self,status,body=b'',ctype='application/json; charset=utf-8',extra=None):
        if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status)
        for key,value in {'Content-Type':ctype,'Content-Length':str(len(body)),
             'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
             'X-Frame-Options':'DENY',
             'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",**(extra or {})}.items():
            self.send_header(key,value)
        self.end_headers();self.wfile.write(body)

    def token(self):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return ''
        return cookie['siter_session'].value if 'siter_session' in cookie else ''

    def body(self):
        if self.headers.get('Transfer-Encoding'):
            raise Problem(400,'Chunked requests are not supported')
        try: length=int(self.headers.get('Content-Length','0'))
        except ValueError: raise Problem(400,'Invalid content length')
        if not 0<length<=MAX_BODY: raise Problem(413,'Upload limit: 24 MiB including JSON encoding')
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            raise Problem(415,'Use application/json')
        try: value=json.loads(self.rfile.read(length))
        except (UnicodeError,ValueError): raise Problem(400,'Invalid JSON payload')
        if not isinstance(value,dict): raise Problem(400,'JSON payload must be an object')
        return value

    def cookie(self,token,logout=False):
        return f'siter_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if logout else 43200}'+('; Secure' if self.server.secure else '')

    def handle_request(self,method):
        try:
            # Fixed host and origin defeat DNS rebinding and cross-site writes.
            if self.headers.get('Host')!=urlsplit(self.server.origin).netloc:
                raise Problem(403,'Host not allowed')
            if method!='GET' and self.headers.get('Origin')!=self.server.origin:
                raise Problem(403,'Origin not allowed')
            self.route(method)
        except Problem as exc: self.send(exc.status,{'error':exc.message})
        except (BrokenPipeError,ConnectionResetError,TimeoutError): pass
        except Exception: self.send(500,{'error':'Unexpected server error'})
        finally: self.close_connection=True

    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def do_DELETE(self): self.handle_request('DELETE')

    def route(self,method):
        path=urlsplit(self.path).path;s=self.server.service
        if method=='GET' and path in ASSETS:
            file=ROOT/'web'/ASSETS[path]
            self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream');return
        if method=='POST' and path=='/api/login':
            self.server.throttle_login(self.client_address[0]);body=self.body()
            token,csrf=s.login(body.get('username'),body.get('password'))
            self.send(200,{'csrf':csrf},extra={'Set-Cookie':self.cookie(token)});return
        session=s.session(self.token());uid=session['user_id']
        if method!='GET' and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
            raise Problem(403,'Invalid CSRF token')
        if path=='/api/session' and method=='GET':
            self.send(200,{'username':session['username'],'csrf':session['csrf']});return
        if path=='/api/logout' and method=='POST':
            s.logout(self.token());self.send(200,{'ok':True},extra={'Set-Cookie':self.cookie('',True)});return
        if path=='/api/config' and method=='GET': self.send(200,s.config(session['username']));return
        if path=='/api/sample' and method=='GET': self.send(200,sample_files());return
        if path in ('/api/templates.zip','/api/sample.zip') and method=='GET':
            self.send(200,template_zip(path=='/api/sample.zip'),'application/zip',{'Content-Disposition':'attachment; filename="'+path.rsplit('/',1)[-1]+'"'});return
        if path=='/api/runs':
            if method=='GET': self.send(200,s.list_runs(uid));return
            if method=='POST': self.send(202,s.create(session,self.body()));return
        parts=path.strip('/').split('/')
        if len(parts)>=3 and parts[:2]==['api','runs']:
            rid=parts[2]
            if len(parts)==3:
                if method=='GET': self.send(200,s.public_run(uid,rid));return
                if method=='DELETE': s.delete(uid,rid);self.send(200,{'ok':True});return
            if len(parts)==4 and parts[3]=='execute' and method=='POST': self.send(202,s.start(uid,rid));return
            if len(parts)==4 and parts[3]=='reporting' and method=='GET': self.send(200,s.reporting(uid,rid));return
            if len(parts)==5 and parts[3]=='files' and method=='GET':
                folder,files=s.artifacts(uid,rid)
                if parts[4] not in files: raise Problem(404,'File not found')
                name=files[parts[4]]
                self.send(200,(folder/name).read_bytes(),'application/octet-stream',{'Content-Disposition':f'attachment; filename="{name}"'});return
        raise Problem(404,'Not found')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path,default=ROOT/'runtime')
    sub=p.add_subparsers(dest='command',required=True)
    user=sub.add_parser('add-user');user.add_argument('username')
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8000)
    serve.add_argument('--host',default='127.0.0.1');serve.add_argument('--origin')
    serve.add_argument('--sources',type=Path)
    a=p.parse_args();os.umask(0o077)
    sources=load(a.sources) if a.command=='serve' and a.sources else None
    service=Service(a.state,sources,recover=a.command=='serve')
    if a.command=='add-user':
        password=getpass.getpass('Password (12+ characters): ')
        if password!=getpass.getpass('Confirm password: '): raise SystemExit('Passwords do not match')
        service.add_user(a.username,password);service.close();print('User saved. Previous sessions revoked.');return
    origin=a.origin or f'http://{a.host}:{a.port}'
    parsed=urlsplit(origin)
    if parsed.path or parsed.query or parsed.fragment or parsed.scheme not in ('http','https'):
        raise SystemExit('Origin must be a scheme and host, without a path')
    if a.host not in ('127.0.0.1','localhost') and parsed.scheme!='https':
        raise SystemExit('Non-loopback binding requires an explicit HTTPS origin and TLS reverse proxy')
    server=Server((a.host,a.port),service,origin)
    print(f'SITER console: {origin} — anonymized demo only')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close();service.close()


if __name__=='__main__': main()
