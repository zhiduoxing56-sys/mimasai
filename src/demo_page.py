"""Loopback page, public asset whitelist and capability-bound final-result API."""
import contextlib,hashlib,hmac,http.cookies,http.server,json,os,secrets,sqlite3,time
from pathlib import Path
from urllib.parse import urlsplit
from .deployment import CODE,PUBLIC_API,root,identity,exact,hexid,call
from .mpc import require,ProtocolError
from .public_projection import status

class Page(http.server.BaseHTTPRequestHandler):
    server_version='PrivacyGNNLocal/1';protocol_version='HTTP/1.1'
    def log_message(self,*args):pass # No cookies, capability URL, or request body logs.
    def reply(self,code,body,content='application/json'):
        if isinstance(body,dict):body=json.dumps(body,ensure_ascii=False).encode()
        elif isinstance(body,str):body=body.encode()
        self.send_response(code);self.send_header('Content-Type',content+'; charset=utf-8');self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        if code>=400:
            self.close_connection=True;self.send_header('Connection','close')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if getattr(self,'cookie_new',False):self.send_header('Set-Cookie',f'pgnn-client={self.client}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
        self.end_headers();self.wfile.write(body)
    def validate_host(self):
        require(self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'),'LOOPBACK_HOST_REQUIRED')
        require(self.client_address[0]=='127.0.0.1','LOOPBACK_PEER_REQUIRED')
    def session(self):
        cookies=http.cookies.SimpleCookie();cookies.load(self.headers.get('Cookie',''));entry=cookies.get('pgnn-client');client=entry.value if entry else None
        try:hexid(client,48)
        except ProtocolError:client=None
        with contextlib.closing(sqlite3.connect(self.server.page_db)) as conn,conn:
            conn.execute('CREATE TABLE IF NOT EXISTS clients(client TEXT PRIMARY KEY,csrf TEXT,expires REAL)')
            row=conn.execute('SELECT csrf,expires FROM clients WHERE client=?',(client,)).fetchone() if client else None
            self.cookie_new=not bool(row)
            if not row:
                client=secrets.token_hex(24);row=(secrets.token_hex(16),0)
                conn.execute('INSERT INTO clients VALUES (?,?,?)',(client,*row))
        self.client=client;self.csrf=row[0];self.authorized=row[1]>time.time()
    def backend(self,action,**args):return call(PUBLIC_API,dict(action=action,**args),timeout=3)
    def do_GET(self):
        try:
            self.validate_host();parsed=urlsplit(self.path);require(not parsed.query,'PAGE_QUERY_REJECTED')
            self.session();path=parsed.path
            if path=='/api/overview':
                try:connected=self.backend('overview')['connected'];reason='LOCAL_AUTHORIZATION_REQUIRED' if not self.authorized else 'REAL_UID_PERMISSIONS_NOT_ACCEPTED'
                except (OSError,ProtocolError):connected=False;reason='PUBLIC_INTERFACE_NOT_CONNECTED'
                return self.reply(200,dict(model=self.server.public_model,connected=bool(connected and self.authorized),connection_reason=reason,csrf=self.csrf))
            assets={'/':('index.html','text/html'),'/style.css':('style.css','text/css'),'/app.js':('app.js','application/javascript')}
            if path not in assets:return self.reply(404,dict(error='PAGE_ROUTE_NOT_FOUND'))
            name,content=assets[path];body=(self.server.assets/name).read_text()
            if name=='index.html':body=body.replace('__PUBLIC_MODEL__',json.dumps(self.server.public_model,ensure_ascii=False).replace('<','\\u003c'))
            self.reply(200,body,content)
        except (ProtocolError,ValueError):self.reply(403,dict(error='PAGE_REQUEST_REJECTED'))
    def do_POST(self):
        try:
            self.validate_host();self.session()
            origin=self.headers.get('Origin');require(origin in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'),'PAGE_ORIGIN_REJECTED')
            require(hmac.compare_digest(self.headers.get('X-PGNN-CSRF',''),self.csrf),'PAGE_CSRF_REJECTED')
            require(self.headers.get('Content-Type')=='application/json','PAGE_CONTENT_TYPE')
            require(not self.headers.get('Transfer-Encoding') and len(self.headers.get_all('Content-Length',[]))==1,'PAGE_BODY_FRAMING')
            size=int(self.headers.get('Content-Length','0'));require(0<size<=4096,'PAGE_BODY_SIZE');data=json.loads(self.rfile.read(size));parsed=urlsplit(self.path)
            require(not parsed.query,'PAGE_QUERY_REJECTED')
            if parsed.path=='/api/login':
                exact(data,('access',));hexid(data['access'],64)
                reply=self.backend('authorize',client=self.client,access=data['access'])
                exact(reply,('authorized',));require(reply['authorized'] is True,'LOCAL_AUTHORIZATION_REJECTED')
                with contextlib.closing(sqlite3.connect(self.server.page_db)) as conn,conn:conn.execute('UPDATE clients SET expires=? WHERE client=?',(time.time()+8*3600,self.client))
                return self.reply(200,reply)
            require(parsed.path in ('/api/submit','/api/status'),'PAGE_ROUTE_NOT_FOUND');require(self.authorized,'LOCAL_AUTHORIZATION_REQUIRED')
            exact(data,('token',));hexid(data['token']);value=self.backend('submit' if parsed.path.endswith('submit') else 'status',client=self.client,token=data['token'])
            # Coordinator returns a fixed public schema; never forward extras.
            exact(value,('request_id','phase','terminal','delivery_state','result','cost','error') if 'retention' not in value else ('request_id','phase','terminal','delivery_state','result','cost','error','retention'))
            self.reply(200,status(value,self.server.public_model))
        except (ProtocolError,ValueError,OSError) as error:
            code=str(error).split(':',1)[0] if isinstance(error,ProtocolError) else 'PUBLIC_INTERFACE_NOT_CONNECTED'
            self.reply(403 if code in ('PAGE_CSRF_REJECTED','PAGE_ORIGIN_REJECTED','LOCAL_AUTHORIZATION_REQUIRED') else 409,dict(error=code))

def server(port=8765,assets=CODE/'ui',page_db=None):
    result=http.server.ThreadingHTTPServer(('127.0.0.1',port),Page)
    result.assets=Path(assets);result.page_db=page_db or root('page')/'state/page.sqlite';result.public_model=json.loads((result.assets/'model-public.json').read_text());return result
def main():
    require(os.geteuid()==identity('page').pw_uid,'PAGE_UID_REQUIRED')
    with server() as http:http.serve_forever()
if __name__=='__main__':main()
