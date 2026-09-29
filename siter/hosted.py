"""Container entrypoint for the invite-only public-URL demonstration."""
import os
import signal
import threading
from pathlib import Path
from urllib.parse import urlsplit
from .service import Service
from .server import Server


def public_origin(value):
    parsed=urlsplit(value)
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('','/') or parsed.query or parsed.fragment):
        raise ValueError('SITER_PUBLIC_ORIGIN must be an HTTPS origin without credentials or a path')
    # Validate port syntax as well as hostname.
    parsed.port
    return value.rstrip('/')


def bootstrap(service,username,password):
    with service.connect() as db:
        exists=db.execute('SELECT 1 FROM users LIMIT 1').fetchone()
    if exists:
        return False
    if not username or not password:
        raise ValueError('An empty installation requires SITER_BOOTSTRAP_USER and SITER_BOOTSTRAP_PASSWORD')
    service.add_user(username,password)
    return True


def main():
    origin=public_origin(os.environ.get('SITER_PUBLIC_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL',''))
    state=Path(os.environ.get('SITER_STATE_DIR','/var/data/siter'))
    if not state.is_absolute(): raise ValueError('SITER_STATE_DIR must be an absolute persistent path')
    port=int(os.environ.get('PORT','10000'))
    if not 1024<=port<=65535: raise ValueError('PORT must be between 1024 and 65535')
    username=os.environ.pop('SITER_BOOTSTRAP_USER','')
    password=os.environ.pop('SITER_BOOTSTRAP_PASSWORD','')
    # Prepare only the private state subdirectory, then drop root inside the container.
    if os.geteuid()==0:
        state.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chown(state,10001,10001)
        os.setgroups([]);os.setgid(10001);os.setuid(10001)
    os.umask(0o077)
    service=Service(state)
    try:
        bootstrap(service,username,password)
        del password
        server=Server(('0.0.0.0',port),service,origin)
        # shutdown() must run outside the serve_forever thread.
        signal.signal(signal.SIGTERM,lambda *_:threading.Thread(target=server.shutdown,daemon=True).start())
        print('SITER hosted demo ready. Authenticated access; anonymized data only.',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
    finally: service.close()


if __name__=='__main__': main()
