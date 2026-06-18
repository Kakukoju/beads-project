import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';
import { join } from 'node:path';
var mobileDir = fileURLToPath(new URL('../../dropfreeze/Web/', import.meta.url));
function mobileRoutePlugin() {
    return {
        name: 'mobile-route',
        configureServer: function (server) {
            server.middlewares.use(function (req, res, next) {
                var _a, _b;
                var pathname = (_b = (_a = req.url) === null || _a === void 0 ? void 0 : _a.split('?')[0]) !== null && _b !== void 0 ? _b : '';
                if (pathname === '/mobile') {
                    res.statusCode = 302;
                    res.setHeader('Location', '/mobile/');
                    res.end();
                    return;
                }
                if (pathname === '/mobile/' || pathname === '/mobile/index.html') {
                    res.setHeader('Content-Type', 'text/html; charset=utf-8');
                    res.end(readFileSync(join(mobileDir, 'index.html')));
                    return;
                }
                if (pathname === '/mobile/config.js') {
                    res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
                    res.end('window.API_BASE = window.location.origin;\n');
                    return;
                }
                if (pathname.startsWith('/mobile/')) {
                    var filename = decodeURIComponent(pathname.slice('/mobile/'.length));
                    var target = join(mobileDir, filename);
                    if (existsSync(target)) {
                        res.end(readFileSync(target));
                        return;
                    }
                    res.statusCode = 404;
                    res.setHeader('Content-Type', 'application/json; charset=utf-8');
                    res.end(JSON.stringify({ ok: false, error: 'Mobile asset not found', path: filename }));
                    return;
                }
                next();
            });
        },
    };
}
export default defineConfig({
    base: "/beads-ui/",
    plugins: [mobileRoutePlugin(), react()],
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url))
        }
    },
    server: {
        host: true, // 讓內網電腦可連
        port: 8505, // 指定 port
        // 如果後端 Flask 跑在 5000，而前端用 /api 開頭，就打開這段
        // proxy: {
        //   '/api': 'http://localhost:5000'
        // }
    }
});
