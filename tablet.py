#!/usr/bin/env python3
# IPTV ev sunucusu — Android tablette Termux ile çalışır.
# TV sayfasını sunar ve IPTV sağlayıcısına bu evin internetinden, VLC gibi görünerek bağlanır.
# Kullanım:  python tablet.py            (ilk açılışta sunucu/kullanıcı/şifre sorar)
#            python tablet.py --sifirla  (kayıtlı bilgileri yeniden gir)
import http.server, socketserver, urllib.request, urllib.parse, urllib.error, json, os, sys, socket, re

PORT = 8080
DIR = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.expanduser('~/.iptv.json')
UA = 'VLC/3.0.20 LibVLC/3.0.20'
TV_URL = 'https://raw.githubusercontent.com/dilmen35/IPTV/main/tv.html'


def ayar():
    if '--sifirla' not in sys.argv and os.path.exists(CONF):
        with open(CONF, encoding='utf8') as f:
            return json.load(f)
    print('\nIPTV bilgilerini gir (sadece bu tablette saklanır):')
    c = {'s': input('  Sunucu (ör. tvnefer.xyz:8080): ').strip(),
         'u': input('  Kullanıcı adı: ').strip(),
         'p': input('  Şifre: ').strip()}
    with open(CONF, 'w', encoding='utf8') as f:
        json.dump(c, f)
    os.chmod(CONF, 0o600)
    return c


def tv_sayfasi():
    yerel = os.path.join(DIR, 'tv.html')
    try:  # her açılışta güncel sürümü indir
        with urllib.request.urlopen(TV_URL, timeout=15) as r:
            data = r.read()
        with open(yerel, 'wb') as f:
            f.write(data)
    except Exception as e:
        print('  (TV sayfası güncellenemedi, kayıtlı sürüm kullanılacak:', e, ')')
    with open(yerel, 'rb') as f:
        return f.read().replace(b'<head>', b'<head><script>window.EV_SUNUCU=1</script>', 1)


def yerel_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80)); return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()


CFG = ayar()
PAGE = tv_sayfasi()


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Expose-Headers', '*')

    def basit(self, code, body, ctype='text/plain; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.send_header('Content-Length', '0'); self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        if 'u' in q:
            return self.aktar(q['u'][0])
        if url.path == '/ayar.json':
            return self.basit(200, json.dumps(CFG), 'application/json')
        if url.path in ('/', '/tv', '/tv.html', '/index.html'):
            return self.basit(200, PAGE, 'text/html; charset=utf-8')
        return self.basit(404, 'yok')

    def aktar(self, hedef):
        if not hedef.startswith(('http://', 'https://')):
            return self.basit(400, 'u gerekli')
        h = {'User-Agent': UA, 'Accept': '*/*'}
        if self.headers.get('Range'):
            h['Range'] = self.headers['Range']
        try:
            r = urllib.request.urlopen(urllib.request.Request(hedef, headers=h), timeout=20)
        except urllib.error.HTTPError as e:
            r = e
        except Exception as e:
            return self.basit(502, 'hedefe ulaşılamadı: %s' % e)
        try:
            son = r.geturl() or hedef
            ct = r.headers.get('Content-Type', '')
            yol = urllib.parse.urlparse(son)
            m3u = 'mpegurl' in ct.lower() or yol.path.lower().endswith(('.m3u8', '.m3u'))
            if m3u:
                text = r.read().decode('utf8', 'replace')
                if text.lstrip().startswith('#EXTM3U'):
                    def abs_(x):
                        return '/?u=' + urllib.parse.quote(urllib.parse.urljoin(son, x), safe='')
                    out = []
                    for l in text.splitlines():
                        if not l.strip():
                            out.append(l)
                        elif l.startswith('#'):
                            out.append(re.sub(r'URI="([^"]+)"', lambda m: 'URI="' + abs_(m.group(1)) + '"', l))
                        else:
                            out.append(abs_(l.strip()))
                    return self.basit(r.status, '\n'.join(out), 'application/vnd.apple.mpegurl')
                return self.basit(r.status, text, ct or 'text/plain')
            self.send_response(r.status)
            for n in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges'):
                if r.headers.get(n):
                    self.send_header(n, r.headers[n])
            uzunluk = r.headers.get('Content-Length')
            if not uzunluk:
                self.send_header('Transfer-Encoding', 'chunked')
            self.cors()
            self.end_headers()
            while True:
                buf = r.read(64 * 1024)
                if not buf:
                    break
                if uzunluk:
                    self.wfile.write(buf)
                else:
                    self.wfile.write(b'%x\r\n%s\r\n' % (len(buf), buf))
            if not uzunluk:
                self.wfile.write(b'0\r\n\r\n')
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                r.close()
            except Exception:
                pass


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    ip = yerel_ip()
    print('\n==============================================')
    print('  IPTV ev sunucusu çalışıyor.')
    print('  TV tarayıcısında aç:  http://%s:%d' % (ip, PORT))
    print('  Durdurmak için: Ctrl+C  (ya da Termux\'u kapat)')
    print('==============================================\n')
    S(('0.0.0.0', PORT), H).serve_forever()
