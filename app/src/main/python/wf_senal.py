"""Lecturas GPS dudosas, común al análisis y al video. No se borran del recorrido (sirven para ver caídas
y cortes): solo no se usan para calcular la velocidad máxima.

Marca dos tipos de lecturas que el GPS del teléfono da mal (y que inflan la velocidad máxima):
  1) Los primeros 5 s después de un corte de señal (más de 5 s sin puntos): al volver a enganchar satélites
     el GPS suele dar velocidades disparatadas (p. ej. 33 kn durante 4 s).
  2) Los puntos cuya precisión empeora de golpe: más de 4 m y más de 1,6 veces la precisión típica (mediana)
     de los 20 s anteriores. Pasa justo antes de perder la señal (teléfono entrando al agua): el GPS sigue
     extrapolando y la velocidad sube sola.
Entrada: lista de (t, lat, lon, v_kn, precisión_m o None), ordenada por t. Salida: conjunto de los t dudosos.
"""

def dudosos(raw, reenganche=True):
    out = set(); n_re = n_prec = 0
    hist = []                     # (t, precisión) de los puntos crudos recientes
    t_corte = None
    prev_t = None
    for x in raw:
        t, ac = x[0], x[4]
        if reenganche and prev_t is not None and t - prev_t > 5: t_corte = t
        prev_t = t
        hist.append((t, ac))
        while hist and hist[0][0] < t - 20: hist.pop(0)
        if t_corte is not None and t - t_corte < 5:
            n_re += 1; out.add(t); continue
        if ac is not None and ac > 4:
            prev = sorted(a for tt, a in hist[:-1] if a is not None)
            if len(prev) >= 5 and ac > 1.6 * prev[len(prev)//2]:
                n_prec += 1; out.add(t); continue
    return out, n_re, n_prec
