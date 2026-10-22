"""Launch the separate RiverGuard V2 installation without touching V1 data."""
import argparse
import asyncio
from html import escape
import os
from pathlib import Path
import socket
import sys
import webbrowser

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def check_ports(ports):
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'): sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try: sock.bind(('0.0.0.0', port))
            except OSError as exc: raise RuntimeError(f'Port {port} is already in use. Stop the other V2 process or choose alternate V2 ports.') from exc


async def run(args):
    import uvicorn
    import httpx
    from server.app import create_apps
    web, sensor = create_apps(args.db, args.web_port, args.sensor_port)
    servers = [uvicorn.Server(uvicorn.Config(web, host='0.0.0.0', port=args.web_port, log_level='warning')),
               uvicorn.Server(uvicorn.Config(sensor, host='0.0.0.0', port=args.sensor_port, log_level='warning'))]
    tasks = [asyncio.create_task(server.serve()) for server in servers]
    link = args.db.parent/'v2-owner-link.html'
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
            for _ in range(100):
                if any(task.done() for task in tasks): raise RuntimeError('A V2 service stopped during startup. Check the error above.')
                try:
                    responses = await asyncio.gather(*[client.get(f'http://127.0.0.1:{port}/health') for port in (args.web_port, args.sensor_port)])
                    if all(response.status_code == 200 and response.json().get('product') == 'RiverGuard V2' for response in responses): break
                except (httpx.HTTPError, ValueError): pass
                await asyncio.sleep(.2)
            else: raise RuntimeError('V2 services did not become ready. The browser was not opened.')
        token = web.state.access.bootstrap_token()
        url = f'http://localhost:{args.web_port}/#bootstrap={token}'
        if args.no_browser:
            link.write_text('<!doctype html><title>RiverGuard V2 owner</title><a href="'+escape(url, quote=True)+'">Open RiverGuard V2</a><p>Private, single-use link; expires in two minutes.</p>', encoding='utf-8')
            os.chmod(link, 0o600)
            if os.name == 'nt':
                import getpass, subprocess
                account = os.environ.get('USERDOMAIN', '')+'\\'+getpass.getuser()
                secured = subprocess.run(['icacls', str(link), '/inheritance:r', '/grant:r', account+':F'], capture_output=True)
                if secured.returncode:
                    link.unlink(missing_ok=True)
                    raise RuntimeError('Could not protect the owner link. Start without --no-browser instead.')
            print(f'Private owner link: {link}', flush=True)
        else: webbrowser.open(url)
        print(f'RiverGuard V2 ready on http://localhost:{args.web_port}; sensor receiver port {args.sensor_port}.', flush=True)
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in tasks:
            if task.done():
                if task.cancelled(): raise RuntimeError('A V2 service was cancelled unexpectedly.')
                error = task.exception()
                if error: raise RuntimeError('A V2 service failed. Restart after checking the error output.') from error
                raise RuntimeError('A V2 service stopped. Both services have been shut down.')
    finally:
        for server in servers: server.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)
        link.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-port', type=int, default=8510)
    parser.add_argument('--sensor-port', type=int, default=8010)
    parser.add_argument('--db', type=Path, default=ROOT/'data/v2.db')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(); args.db = args.db.resolve()
    if args.web_port == args.sensor_port or not all(1 <= port <= 65535 for port in (args.web_port, args.sensor_port)):
        parser.error('Choose two different valid ports.')
    if args.db == (ROOT.parent/'data/riverguard.db').resolve(): parser.error('Use a separate V2 database; the original application must remain intact.')
    try:
        if not (ROOT/'mobile/web/index.html').is_file():
            raise RuntimeError('Build the V2 interface first: cd v2/frontend, then npm ci and npm run build.')
        check_ports((args.web_port, args.sensor_port))
        asyncio.run(run(args))
    except KeyboardInterrupt: return 0
    except Exception as exc:
        print(f'RiverGuard V2 could not start: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
