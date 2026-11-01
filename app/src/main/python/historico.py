"""Histórico de sesiones: junta los resultados de cada análisis (analisis/resultados.json) y exporta un Excel."""
import json, os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import LineChart, Reference
from openpyxl.utils import get_column_letter

def _leer(sessions_root):
    out = []
    for d in sorted(os.listdir(sessions_root)):
        j = os.path.join(sessions_root, d, 'analisis', 'resultados.json')
        if not os.path.exists(j): continue
        try: R = json.load(open(j, encoding='utf-8'))
        except Exception: continue
        f = R.get('fecha', '')
        try: dd, mm, yy = f.split('-'); orden = f"{yy}{mm}{dd}{R.get('hora_inicio', '')}"
        except ValueError: orden = d
        R['_orden'] = orden; R['_dir'] = d
        out.append(R)
    out.sort(key=lambda r: r['_orden'])
    return out

def _fila(R):
    T = R.get('por_tipo', {}).get('Trasluchada', {}); V = R.get('por_tipo', {}).get('Virada', {})
    S = R.get('saltos', []) if R.get('acc') else None
    sc = sum(1 for e in S if e.get('resultado') == 'Completo') if S is not None else None
    sf = (len(S) - sc) if S is not None else None
    alto = max((e['altura'] for e in S), default=None) if S else None
    return [R.get('fecha', ''), R.get('hora_inicio', ''), R.get('distancia_km'), R.get('tiempo_min'), R.get('planeo_min'),
            R.get('planeo_pct'), R.get('vel_media_planeo'), R.get('vmax20'),
            T.get('completas'), T.get('fallidas'), T.get('v_in'), T.get('v_out'), T.get('variacion'),
            V.get('completas'), V.get('fallidas'), V.get('v_in'), V.get('v_out'), V.get('variacion'),
            sc, sf, alto]

COLS = [('Fecha', 12, None), ('Hora inicio', 11, None), ('Distancia (km)', 11, '0.00'), ('Duración (min)', 11, '0.0'),
        ('Planeo (min)', 11, '0.0'), ('% planeo', 10, '0.0%'), ('Vel. media planeo (kn)', 12, '0.00'), ('Vel. máx. 20 m (kn)', 12, '0.00'),
        ('Trasluchadas completas', 13, '0'), ('Trasluchadas fallidas', 13, '0'), ('Trasl. vel. entrada (kn)', 13, '0.00'),
        ('Trasl. vel. salida (kn)', 13, '0.00'), ('Trasl. variación', 12, '+0.0%;[Red]-0.0%;0.0%'),
        ('Viradas completas', 11, '0'), ('Viradas fallidas', 11, '0'), ('Viradas vel. entrada (kn)', 13, '0.00'),
        ('Viradas vel. salida (kn)', 13, '0.00'), ('Viradas variación', 12, '+0.0%;[Red]-0.0%;0.0%'),
        ('Saltos completos', 11, '0'), ('Saltos fallidos', 11, '0'), ('Salto más alto (m)', 11, '0.00')]

def exportar(sessions_root, out_path):
    S = _leer(sessions_root)
    if not S: return json.dumps({'ok': False, 'error': 'Todavía no hay sesiones analizadas.'})
    F = 'Arial'; HF = PatternFill('solid', fgColor='1F4E78'); HFo = Font(name=F, bold=True, color='FFFFFF', size=10)
    N = Font(name=F, size=10); B = Font(name=F, bold=True, size=10); bd = Border(*(Side(style='thin', color='CCCCCC'),) * 4)
    wb = Workbook(); ws = wb.active; ws.title = 'Histórico'
    ws['A1'] = 'Wingfoil & PW Tracker — Histórico de sesiones'; ws['A1'].font = Font(name=F, bold=True, size=14)
    for ci, (h, w, _) in enumerate(COLS, 1):
        x = ws.cell(3, ci, h); x.font = HFo; x.fill = HF; x.border = bd
        x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[3].height = 44
    r0 = 4
    for i, R in enumerate(S):
        for ci, (val, (_, _, fmt)) in enumerate(zip(_fila(R), COLS), 1):
            x = ws.cell(r0 + i, ci, val); x.font = N; x.border = bd          # vacío = sin dato
            x.alignment = Alignment(horizontal='center')
            if fmt and val is not None: x.number_format = fmt
    rl = r0 + len(S) - 1; rt = rl + 2
    L = lambda c: get_column_letter(c)
    ws.cell(rt, 1, 'TOTAL / PROMEDIO').font = B
    ws.cell(rt, 2, f'{len(S)} sesiones').font = B
    for c in (3, 4, 5, 9, 10, 14, 15, 19, 20):
        x = ws.cell(rt, c, f'=SUM({L(c)}{r0}:{L(c)}{rl})'); x.font = B; x.number_format = COLS[c-1][2] or 'General'
    x = ws.cell(rt, 6, f'=IFERROR(E{rt}/D{rt},"s/d")'); x.font = B; x.number_format = '0.0%'
    for c in (7, 8):
        x = ws.cell(rt, c, f'=IFERROR(AVERAGE({L(c)}{r0}:{L(c)}{rl}),"s/d")'); x.font = B; x.number_format = COLS[c-1][2]
    # velocidades y variación: promedio ponderado por la cantidad de maniobras de cada sesión
    for c, (wc, wf) in ((11, ('I', 'J')), (12, ('I', 'J')), (13, ('I', 'J')), (16, ('N', 'O')), (17, ('N', 'O')), (18, ('N', 'O'))):
        col = L(c); rng = lambda k: f'{k}{r0}:{k}{rl}'
        f_ = (f'=IFERROR(SUMPRODUCT({rng(col)},{rng(wc)}+{rng(wf)})/SUMPRODUCT(--({rng(col)}<>""),{rng(wc)}+{rng(wf)}),"s/d")')
        x = ws.cell(rt, c, f_); x.font = B; x.number_format = COLS[c-1][2]
    x = ws.cell(rt, 21, f'=IFERROR(MAX({L(21)}{r0}:{L(21)}{rl}),"s/d")'); x.font = B; x.number_format = '0.00'
    for c in range(1, 22):
        ws.cell(rt, c).fill = PatternFill('solid', fgColor='DDEBF7'); ws.cell(rt, c).alignment = Alignment(horizontal='center'); ws.cell(rt, c).border = bd
    ws.cell(rt + 1, 1, '% de éxito').font = B
    ws.cell(rt + 1, 9, f'=IFERROR(I{rt}/(I{rt}+J{rt}),"s/d")').number_format = '0.0%'
    ws.cell(rt + 1, 14, f'=IFERROR(N{rt}/(N{rt}+O{rt}),"s/d")').number_format = '0.0%'
    ws.cell(rt + 1, 19, f'=IFERROR(S{rt}/(S{rt}+T{rt}),"s/d")').number_format = '0.0%'
    for c in (9, 14, 19): ws.cell(rt + 1, c).font = B; ws.cell(rt + 1, c).alignment = Alignment(horizontal='center')
    ws.freeze_panes = 'C4'
    # Evolución: % de éxito y % de planeo por sesión
    we = wb.create_sheet('Evolución')
    for ci, h in enumerate(['Sesión', '% planeo', '% éxito trasluchadas', '% éxito viradas', 'Vel. media planeo (kn)'], 1):
        x = we.cell(1, ci, h); x.font = HFo; x.fill = HF; we.column_dimensions[L(ci)].width = 20
    for i in range(len(S)):
        r = i + 2; src = r0 + i
        we.cell(r, 1, f"=Histórico!A{src}")
        we.cell(r, 2, f"=Histórico!F{src}").number_format = '0.0%'
        we.cell(r, 3, f'=IFERROR(Histórico!I{src}/(Histórico!I{src}+Histórico!J{src}),NA())').number_format = '0.0%'
        we.cell(r, 4, f'=IFERROR(Histórico!N{src}/(Histórico!N{src}+Histórico!O{src}),NA())').number_format = '0.0%'
        we.cell(r, 5, f"=Histórico!G{src}").number_format = '0.00'
    last = len(S) + 1
    ch = LineChart(); ch.title = '% de planeo y % de éxito por sesión'; ch.y_axis.title = '%'; ch.y_axis.number_format = '0%'
    ch.add_data(Reference(we, min_col=2, max_col=4, min_row=1, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(we, min_col=1, min_row=2, max_row=last)); ch.height = 9; ch.width = 22
    we.add_chart(ch, 'G2')
    ch2 = LineChart(); ch2.title = 'Velocidad media en planeo (kn)'
    ch2.add_data(Reference(we, min_col=5, min_row=1, max_row=last), titles_from_data=True)
    ch2.set_categories(Reference(we, min_col=1, min_row=2, max_row=last)); ch2.height = 9; ch2.width = 22
    we.add_chart(ch2, 'G22')
    wb.save(out_path)
    return json.dumps({'ok': True, 'n': len(S), 'path': out_path})
