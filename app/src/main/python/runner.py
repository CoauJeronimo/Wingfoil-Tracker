"""Puente entre la app Android y el análisis: corre wingfoil_analisis.py y arma el PDF."""
import sys, io, os, re, json, importlib, contextlib, traceback

def run(session_dir, outdir, wind, fecha, sections, excludes, sat=True, nombre='', lugar='', viento_kn='', comentario=''):
    os.makedirs(outdir, exist_ok=True)
    jpath = os.path.join(outdir, 'resultados.json')
    if os.path.exists(jpath): os.remove(jpath)
    argv = ['wingfoil_analisis.py',
            '--location', os.path.join(session_dir, 'Location.csv'),
            '--metadata', os.path.join(session_dir, 'Metadata.csv'),
            '--wind', str(wind), '--fecha', fecha, '--sections', str(int(sections)),
            '--outdir', outdir, '--json', jpath]
    if nombre: argv += ['--nombre', str(nombre)]
    if lugar: argv += ['--lugar', str(lugar)]
    if comentario: argv += ['--comentario', str(comentario)]
    try:
        if str(viento_kn).strip(): argv += ['--viento-kn', str(float(str(viento_kn).replace(',', '.')))]
    except ValueError:
        return json.dumps({'ok': False, 'error': f"Intensidad del viento inválida: '{viento_kn}'. Poné solo el número de nudos.", 'log': ''}, ensure_ascii=False)
    exc = [e for e in str(excludes or '').replace(',', ' ').split() if e]
    for e in exc:
        if not re.fullmatch(r'\d{1,2}:\d{2}:\d{2}-\d{1,2}:\d{2}:\d{2}', e):
            return json.dumps({'ok': False, 'error': f"Tramo a excluir inválido: '{e}'. Usá el formato HH:MM:SS-HH:MM:SS (por ejemplo 14:57:18-15:09:39).", 'log': ''}, ensure_ascii=False)
    if exc: argv += ['--exclude'] + exc
    out = io.StringIO(); old = sys.argv; sys.argv = argv
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            sys.modules.pop('wingfoil_analisis', None)      # el script corre al importarse
            importlib.import_module('wingfoil_analisis')
        R = json.load(open(jpath, encoding='utf-8'))
        import wf_pdf
        pdf = os.path.join(outdir, f'analisis_wingfoil_{fecha}.pdf')
        wf_pdf.informe(R, pdf, sat=bool(sat))
        T, V = R['por_tipo']['Trasluchada'], R['por_tipo']['Virada']
        def pc(x, s=False): return 's/d' if x is None else (f"{x*100:+.1f}%" if s else f"{x*100:.1f}%")
        resumen = (f"Distancia {R['distancia_km']:.2f} km · Tiempo {R['tiempo_min']:.1f} min\n"
                   f"Planeo {R['planeo_min']:.1f} min ({pc(R['planeo_pct'])}) · Vel. media en planeo {R['vel_media_planeo']:.2f} kn\n"
                   f"Vel. máx. 20 m {R['vmax20']:.2f} kn ({R['vmax20_hora']})\n"
                   f"Trasluchadas {T['completas']} completas / {T['fallidas']} fallidas · variación (completas) {pc(T['variacion'], True)}\n"
                   f"Viradas {V['completas']} completas / {V['fallidas']} fallidas · variación (completas) {pc(V['variacion'], True)}\n"
                   f"Cortes de señal {R['cortes']} ({R['sin_senal_min']:.1f} min) · descartados por precisión {R['descartados_precision']}")
        return json.dumps({'ok': True, 'pdf': pdf, 'kml': os.path.join(outdir, R['kml']),
                           'xlsx': os.path.join(outdir, R['xlsx']), 'resumen': resumen, 'log': out.getvalue()}, ensure_ascii=False)
    except SystemExit as e:
        msg = e.code if isinstance(e.code, str) else out.getvalue().strip().splitlines()[-1:] or ['Error en los parámetros']
        return json.dumps({'ok': False, 'error': msg if isinstance(msg, str) else msg[0], 'log': out.getvalue()}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': f"{type(e).__name__}: {e}", 'log': out.getvalue() + traceback.format_exc()}, ensure_ascii=False)
    finally:
        sys.argv = old
