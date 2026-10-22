"""One-process supervisor for the private-network web app and sensor receiver."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import webbrowser
from html import escape

ROOT = Path(__file__).resolve().parent


def check_ports(ports):
    for port in ports:
        try:
            occupied = socket.create_connection(('127.0.0.1',port),timeout=.25)
        except OSError:
            occupied = None
        if occupied is not None:
            occupied.close()
            raise RuntimeError(f'Port {port} is already in use. Stop the older RiverGuard launcher or the application using that port, then start again.')
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            try:
                sock.bind(('0.0.0.0',port))
            except OSError as exc:
                raise RuntimeError(f'Port {port} is already in use. Stop the older RiverGuard launcher or the application using that port, then start again.') from exc


def check_service_exits(servers, tasks):
    """A silent service return is a failure unless shutdown was requested."""
    for server, task in zip(servers, tasks, strict=True):
        if not task.done():
            continue
        requested = bool(server.should_exit or getattr(server, 'force_exit', False))
        if task.cancelled():
            if not requested:
                raise RuntimeError('A RiverGuard service stopped unexpectedly. Restart the launcher after checking its error output.')
            continue
        error = task.exception()
        if error is not None or not requested:
            raise RuntimeError('A RiverGuard service stopped unexpectedly. Restart the launcher after checking its error output.') from error


async def run(args):
    import uvicorn
    import httpx
    import security
    from api import app as receiver
    from ui_api import app as web
    instance = secrets.token_hex(12)
    os.environ['RIVERGUARD_INSTANCE'] = instance
    os.environ['RIVERGUARD_WEB_PORT'] = str(args.web_port)
    servers = [uvicorn.Server(uvicorn.Config(receiver,host='0.0.0.0',port=args.sensor_port,log_level='warning')),
               uvicorn.Server(uvicorn.Config(web,host='0.0.0.0',port=args.web_port,log_level='warning'))]
    tasks = [asyncio.create_task(server.serve()) for server in servers]
    try:
        async with httpx.AsyncClient(trust_env=False,timeout=2) as client:
            for _ in range(100):
                if any(task.done() for task in tasks):
                    raise RuntimeError('A RiverGuard service could not start. Check the error above; the dashboard has not been opened.')
                try:
                    states = [await client.get(f'http://127.0.0.1:{port}/health') for port in (args.sensor_port,args.web_port)]
                    if all(r.status_code==200 and r.json().get('instance')==instance for r in states):
                        break
                except (httpx.HTTPError,ValueError):
                    pass
                await asyncio.sleep(.2)
            else:
                raise RuntimeError('RiverGuard did not become ready. Check the receiver and web application logs.')
        print(f'RiverGuard ready: http://localhost:{args.web_port}',flush=True)
        for url in security.lan_urls(args.web_port):
            print(f'Phone access: {url} (pair with a code from Settings)',flush=True)
        token = security.bootstrap_token()
        owner_url = f'http://localhost:{args.web_port}/#bootstrap={token}'
        if not args.no_browser:
            webbrowser.open(f'http://localhost:{args.web_port}/#bootstrap={token}')
        else:
            import core
            import getpass
            import subprocess
            private_link = core.DB.parent/'owner-link.html'
            private_link.write_text(f'<!doctype html><title>RiverGuard owner session</title><a href="{escape(owner_url,quote=True)}">Open RiverGuard on this laptop</a><p>This single-use link expires after two minutes. Restart the launcher to renew it.</p>',encoding='utf-8')
            os.chmod(private_link,0o600)
            if os.name=='nt':
                account = os.environ.get('USERDOMAIN','')+'\\'+getpass.getuser()
                secured = subprocess.run(['icacls',str(private_link),'/inheritance:r','/grant:r',account+':F'],capture_output=True)
                if secured.returncode:
                    private_link.unlink(missing_ok=True)
                    raise RuntimeError('Could not protect the owner link. Start without --no-browser to open the owner session directly.')
            print(f'Private owner link: {private_link}',flush=True)
        await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        check_service_exits(servers, tasks)
    finally:
        for server in servers:
            server.should_exit = True
        await asyncio.gather(*tasks,return_exceptions=True)
        if args.no_browser:
            import core
            (core.DB.parent/'owner-link.html').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-port',type=int,default=8501)
    parser.add_argument('--sensor-port',type=int,default=8000)
    parser.add_argument('--db',type=Path)
    parser.add_argument('--no-browser',action='store_true')
    args = parser.parse_args()
    if args.web_port==args.sensor_port or not all(1<=p<=65535 for p in [args.web_port,args.sensor_port]):
        parser.error('Choose two different valid ports.')
    if args.db:
        os.environ['RIVERGUARD_DB'] = str(args.db.resolve())
    # Keep BLAS housekeeping bounded on laptops; the Ollama model is unchanged.
    os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
    os.environ.setdefault('OMP_NUM_THREADS','2')
    os.chdir(ROOT)
    try:
        check_ports([args.web_port,args.sensor_port])
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'RiverGuard could not start: {exc}',file=sys.stderr,flush=True)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
