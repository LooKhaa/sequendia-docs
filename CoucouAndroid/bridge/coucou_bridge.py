#!/usr/bin/env python3
"""Pont LAN entre l'application Android et coucou-fedora."""
import json, os, secrets, socket, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
SOCK = Path(os.environ.get('COUCOU_SOCK', Path(os.environ.get('XDG_RUNTIME_DIR', f'/tmp/coucou-fedora-{os.getuid()}')) / 'coucou-fedora.sock'))
TOKEN = os.environ.get('COUCOU_ANDROID_TOKEN', '')
HOST = os.environ.get('COUCOU_ANDROID_HOST', '0.0.0.0')
PORT = int(os.environ.get('COUCOU_ANDROID_PORT', '8765'))
def local(msg, timeout=4):
    s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(timeout)
    try:
        s.connect(str(SOCK)); s.sendall((json.dumps(msg, ensure_ascii=False)+'\n').encode())
        line=s.makefile('rb').readline(1<<20)
        if not line: raise RuntimeError('Coucou ne répond pas')
        return json.loads(line.decode())
    finally: s.close()
class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, obj):
        data=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(data)
    def auth(self): return bool(TOKEN) and secrets.compare_digest(self.headers.get('Authorization',''), 'Bearer '+TOKEN)
    def do_GET(self):
        if not self.auth(): return self.send_json(401,{'error':'Authentification requise'})
        if self.path!='/api/status': return self.send_json(404,{'error':'Route inconnue'})
        try: return self.send_json(200,local({'op':'status'}))
        except Exception as e: return self.send_json(503,{'error':str(e)})
    def do_POST(self):
        if not self.auth(): return self.send_json(401,{'error':'Authentification requise'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n>65536: return self.send_json(413,{'error':'Requête trop grande'})
            data=json.loads(self.rfile.read(n) or b'{}')
            if self.path=='/api/chat':
                text=str(data.get('text','')).strip(); profile=str(data.get('profile','default')).strip() or 'default'
                if not text or len(text)>8000: return self.send_json(400,{'error':'Message vide ou trop long'})
                if len(profile)>80 or any(c in profile for c in '\r\n/\\'): return self.send_json(400,{'error':'Profil invalide'})
                local({'op':'ask_profile','profile':profile,'text':text})
                end=time.time()+45; last=''
                while time.time()<end:
                    time.sleep(.7); st=local({'op':'status'}); ai=st.get('ai') or {}; last=str(ai.get('text',''))
                    if ai.get('state') in ('done','error') and last: return self.send_json(200,{'reply':last,'state':ai.get('state')})
                return self.send_json(200,{'reply':last or 'Message transmis à Hermes. La réponse peut encore arriver sur le PC.','state':'pending'})
            if self.path.startswith('/api/approval/'):
                bits=self.path.strip('/').split('/')
                if len(bits)!=4 or bits[0:2]!=['api','approval'] or bits[3] not in ('allow','deny'): return self.send_json(404,{'error':'Route inconnue'})
                return self.send_json(200,local({'op':'resolve','id':unquote(bits[2]),'decision':'allow' if bits[3]=='allow' else 'deny'}))
            shortcuts={'/api/shortcut/focus':{'op':'focus','minutes':25},'/api/shortcut/bonjour':{'op':'bonjour','speak':True},'/api/shortcut/calm':{'op':'calm','kind':'breath'}}
            if self.path in shortcuts: return self.send_json(200,local(shortcuts[self.path]))
            return self.send_json(404,{'error':'Route inconnue'})
        except Exception as e: return self.send_json(502,{'error':str(e)})
    def log_message(self, fmt, *args): print(f'{self.client_address[0]} - {fmt%args}')
if __name__=='__main__':
    if not TOKEN: print('Définis COUCOU_ANDROID_TOKEN avec un jeton long.'); raise SystemExit(2)
    print(f'Pont Coucou Android sur {HOST}:{PORT}; socket locale={SOCK}')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
