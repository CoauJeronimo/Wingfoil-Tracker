"""Explicaciones de cada dato del análisis («qué es y para qué sirve»), para el Excel y el PDF.
Se buscan por el comienzo del nombre del dato, así sirven aunque el nombre lleve números (p. ej. «> 10 m»)."""

def resumen(ws=False):
    vn = '4' if ws else '7'
    nav = 'navegando (más de 4 kn)' if ws else 'en planeo (más de 7 kn)'
    return [
        ('Nombre de la sesión', 'El nombre que le pusiste a la sesión en la app. Sirve para encontrarla en el histórico.'),
        ('Lugar', 'Dónde navegaste. Sirve para comparar sesiones del mismo spot.'),
        ('Intensidad del viento', 'Los nudos de viento que anotaste. Sirve para comparar sesiones con viento parecido: con más viento todo es más rápido.'),
        ('Comentario', 'Tu nota sobre la sesión (equipo, olas, cómo te sentiste).'),
        ('Disciplina', 'Wingfoil o windsurf. Cambia cómo se decide si una maniobra salió bien y qué datos se informan.'),
        ('Origen del archivo', 'De dónde salieron los datos: grabados con esta app, con Sensor Logger o importados de un GPX. Los GPX importados pueden tener menos precisión.'),
        ('Dirección del viento', 'Los grados desde DONDE VIENE el viento, como los ingresaste. Todo lo que es virada, trasluchada, ángulos, babor/estribor y VMG depende de este dato: si está mal, esos resultados salen mal.'),
        ('Distancia total', 'Los kilómetros recorridos, sin contar los tramos excluidos ni los cortes de señal. Sirve para ver el volumen de la sesión.'),
        ('Tiempo total', 'Desde que empezaste a moverte (4 kn) hasta que dejaste de hacerlo, sin los tramos excluidos ni los cortes de señal. Incluye las paradas y caídas.'),
        ('Tiempo total de planeo', 'Minutos navegando a más de 7 kn, que es cuando el foil está en vuelo. Sirve para ver cuánto de la sesión fue navegación de verdad y cuánto fue estar parado o arrancando.'),
        ('% del tiempo planeando', 'Qué parte del tiempo total estuviste en planeo. Si sube de una sesión a otra, estás arrancando mejor, cayéndote menos o aprovechando mejor el viento.'),
        ('Velocidad media de navegación en planeo', 'La velocidad promedio solo mientras estuviste en planeo (no cuenta paradas ni arranques). Es la mejor medida de qué tan rápido navegás.'),
        ('Tiempo navegando', 'Minutos a más de 4 kn, es decir moviéndote con la vela (no cuenta paradas, caídas ni arranques).'),
        ('% del tiempo navegando', 'Qué parte del tiempo total estuviste navegando (a más de 4 kn). Si sube de una sesión a otra, pasás menos tiempo parado, levantando la vela o en el agua.'),
        ('Velocidad media navegando', 'La velocidad promedio mientras te movías a más de 4 kn. Es la medida general de qué tan rápido navegás, sin contar paradas.'),
        ('Velocidad máxima en un tramo de 20 m', 'La mayor velocidad media sostenida en 20 m seguidos. Se usa un tramo y no un punto suelto para que un salto del GPS no la infle.'),
        ('Hora de la velocidad máxima', 'Cuándo fue la velocidad máxima. Sirve para ubicarla en el mapa o en un video.'),
        ('Viradas completas', 'Viradas (giro pasando la proa por el viento) en las que seguiste navegando sin caerte.'),
        ('Viradas fallidas', 'Viradas con caída (o con la señal cortada porque el teléfono quedó bajo el agua).'),
        ('% de éxito en viradas', 'Completas sobre el total de viradas. Es el indicador principal de cómo te salen las viradas.'),
        ('Trasluchadas completas', 'Trasluchadas (giro pasando la popa por el viento) en las que seguiste navegando sin caerte.'),
        ('Trasluchadas fallidas', 'Trasluchadas con caída (o con la señal cortada porque el teléfono quedó bajo el agua).'),
        ('% de éxito en trasluchadas', 'Completas sobre el total de trasluchadas. Es el indicador principal de cómo te salen las trasluchadas.'),
        ('Velocidad promedio de entrada', 'Velocidad media en los 40 m antes del giro (solo maniobras completas). Entrar con más velocidad suele dar maniobras más limpias.'),
        ('Velocidad promedio de salida', 'Velocidad media en los 40 m después del giro (solo completas). Cuanto más cerca de la de entrada, mejor.'),
        ('Variación promedio salida vs entrada', 'Cuánta velocidad perdés (−) o ganás (+) en la maniobra. Es la medida de qué tan fluida es: una buena maniobra pierde poco.'),
        ('Velocidad mínima en el giro', 'La velocidad más baja dentro del giro (mediana de las completas). Muestra si la maniobra fue fluida o "se murió" en el medio.' + ('' if ws else ' En wingfoil, por debajo de 7 kn el foil suele bajar al agua.')),
        ('Duración del giro', 'Segundos desde que empezás a cambiar el rumbo hasta que quedás navegando del otro lado (mediana de las completas). Una maniobra más corta suele perder menos velocidad.'),
        ('Radio del giro', 'Qué tan cerrado es el giro, en metros (mediana de las completas). Un radio chico es un giro cerrado; uno grande, un giro abierto y largo. Con GPS de 1 punto por segundo es aproximado.'),
        ('Metros contra el viento', 'Cuántos metros ganás (+) o cedés (−) hacia donde viene el viento durante el giro (mediana de las completas). En las viradas conviene ganar altura; en las trasluchadas es normal ceder algo a sotavento: cuanto menos, mejor.'),
        ('Tiempo para recuperar la velocidad', 'Segundos desde el giro hasta volver al 80% de la velocidad de entrada (mediana de las completas). Mide cuánto te cuesta re-acelerar.'),
        ('Maniobras sin bajar de 7 kn', 'Cuántas maniobras hiciste sin bajar nunca de 7 kn en todo el giro, es decir sin salir del planeo (foiling tack / foiling gybe). Es el objetivo técnico de las maniobras en wingfoil.'),
        ('Completas tocando el agua', 'Maniobras completas en las que bajaste de 4 kn (el foil tocó el agua, o en la virada al cruzar el viento) pero volviste a 7 kn y seguiste volando. Están entre las completas; sirven para ver cuántas te faltan para hacerlas enteras en vuelo.'),
        ('Ángulo de ceñida', 'Qué tan alto navegás contra el viento: grados entre tu rumbo y la dirección de donde viene el viento (mediana del tiempo en ceñida, ' + nav + '). Menos grados = más alto. Se separa por babor y estribor porque casi siempre hay un lado mejor.'),
        ('Ángulo en el largo', 'Qué tan abajo navegás a favor del viento: grados respecto a la dirección de donde viene el viento (180° = popa redonda). Mediana del tiempo a favor del viento.'),
        ('VMG medio contra el viento', 'Velocity made good: la parte de tu velocidad que te acerca a donde viene el viento. Combina ángulo y velocidad: sirve para saber si te conviene orzar más o abrir y ir más rápido.'),
        ('VMG medio a favor del viento', 'La parte de tu velocidad que te lleva hacia donde va el viento. Sirve para ver cuánto avanzás de verdad cuando bajás.'),
        ('Mejor VMG contra el viento', 'El mejor VMG contra el viento sostenido 10 s. Es tu mejor marca de "subir".'),
        ('Mejor VMG a favor del viento', 'El mejor VMG a favor del viento sostenido 10 s. Es tu mejor marca de "bajar".'),
        ('Cortes de señal GPS', 'Veces que el GPS dejó de dar puntos válidos más de unos segundos (por ejemplo, teléfono bajo el agua en una caída). Esos huecos no suman tiempo ni distancia.'),
        ('Tiempo total sin señal', 'Suma de la duración de los cortes de señal.'),
        ('Puntos descartados por precisión', 'Puntos GPS con mala precisión que se descartaron para no ensuciar el recorrido. Si son muchos, el teléfono tenía mala señal (funda, posición, cielo cubierto).'),
        ('Lecturas dudosas no usadas para la velocidad máxima', 'Lecturas del GPS poco confiables: los primeros 5 s después de un corte de señal (al re-enganchar, el GPS suele dar velocidades disparatadas, por ejemplo 33 kn) y los puntos en que la precisión empeora de golpe justo antes de perder la señal. Siguen en el recorrido y en las maniobras, pero no cuentan para la velocidad máxima.'),
        ('Saltos', 'Saltos detectados con el acelerómetro: vuelo de 1 s o más y altura estimada de 0,5 m o más (así el paso de una ola no cuenta).'),
        ('Saltos completos', 'Saltos después de los que seguiste navegando.'),
        ('Saltos fallidos', 'Saltos que terminaron en caída (velocidad bajo 4 kn más de 5 s o corte de señal).'),
        ('% de éxito en saltos', 'Saltos completos sobre el total.'),
        ('Salto más alto', 'Altura máxima estimada del mejor salto, calculada con el tiempo en el aire.'),
        ('Hora del salto más alto', 'Cuándo fue el salto más alto.'),
    ]

def maniobras(ws=False):
    """Explicación de cada columna de la tabla de maniobras."""
    return [
        ('Nombre / Mapa', 'Tipo y número de la maniobra, igual que en el KML; en el PDF, T = trasluchada y V = virada, con el mismo número que en los mapas.'),
        ('Resultado', ('Completa = seguiste navegando. Fallida = caída: en la virada, quedar a menos de 1,5 kn 12 s o más (levantar la vela o waterstart) o no volver a 4 kn en 60 s; '
                       'en la trasluchada, quedar a menos de 2 kn 6 s o más. También es fallida si la señal se corta (teléfono bajo el agua). Umbrales iniciales: se ajustan con tus sesiones.')
                      if ws else 'Completa = sin caída sostenida (2 o más puntos seguidos) bajo 4 kn en los 40 m después del giro. Fallida = con esa caída, o si la señal se corta (teléfono bajo el agua) antes de completar los 40 m. Si la señal se corta pero el giro ya había terminado en vuelo (navegando del otro lado del eje a 7 kn o más, sin bajar de 6 kn en el giro), cuenta como completa: la caída fue después. Si bajó de 4 kn pero volvió a 7 kn y siguió volando, también es completa: en la trasluchada tiene 5 s para recuperar («tocó el agua y siguió») y en la virada 10 s, porque al cruzar la línea del viento con la tabla girando es normal que la velocidad baje mucho («bajó al cruzar el viento y siguió»).'),
        ('Hora / Transcurrido', 'Hora local del giro y tiempo desde el comienzo de la sesión. Sirven para encontrar la maniobra en un video.'),
        ('Vel. entrada', 'Velocidad media en los 40 m antes del giro.'),
        ('Vel. salida', 'Velocidad media en los 40 m después del giro.'),
        ('Variación', 'Diferencia entre salida y entrada, en %. Negativo = perdiste velocidad. Mide qué tan fluida fue la maniobra.'),
        ('Vel. mínima', 'La velocidad más baja dentro del giro.' + ('' if ws else ' Si no baja de 7 kn, la maniobra fue en planeo (foiling).')),
        ('Duración', 'Segundos desde que empezás a cambiar el rumbo (a más de 15° del de entrada) hasta que quedás navegando del otro lado (a menos de 15° del de salida).'),
        ('Radio', 'Radio del giro en metros: distancia recorrida en el giro dividida por el ángulo girado. Chico = giro cerrado. Con 1 punto por segundo es aproximado.'),
        ('Contra el viento', 'Metros ganados (+) o cedidos (−) hacia donde viene el viento entre el inicio y el fin del giro.'),
        ('Recuperación', 'Segundos desde el giro hasta volver al 80% de la velocidad de entrada. Vacío = no la recuperó en 60 s.'),
        ('Ángulo de entrada', 'Grados entre el rumbo de 10 a 3 s antes del giro y el eje que se cruza: la popa redonda en las trasluchadas y el enfachado (proa al viento) en las viradas. 0° = sobre el eje.'),
        ('Ángulo de salida', 'Lo mismo con el rumbo de 3 a 10 s después del giro. Muestra si salís muy cerca del eje (lento) o abriendo (más velocidad).'),
        ('Viento por', 'De qué lado te venía el viento antes del giro (babor = izquierda, estribor = derecha). Sirve para comparar tus dos lados.'),
        *([] if ws else [('En planeo', 'Sí = no bajó de 7 kn en todo el giro (foiling tack / gybe).')]),
        ('Observación', 'Notas, por ejemplo si la señal se cortó tras el giro.'),
    ]

def rumbos(ws=False):
    return [
        ('Rumbo', 'Ceñida = menos de 70° al viento (subiendo); Través = 70 a 110°; Largo = 110 a 150°; Popa = más de 150° (bajando). Se miden solo los tramos rectos (sin los 12 s alrededor de cada maniobra) a más de ' + ('4 kn.' if ws else '7 kn (en planeo).')),
        ('Tiempo', 'Minutos que navegaste en ese rumbo y qué parte del total medido representan. Muestra si la sesión fue más de subir, de través o de bajar.'),
        ('Vel. media / máx.', 'Velocidad media y máxima en ese rumbo. Sirve para ver en qué rumbo sos más rápido.'),
        ('Babor / Estribor', 'Velocidad media en ese rumbo con el viento por babor o por estribor. Si un lado es claramente más lento, es el lado para practicar (o el equipo está más ajustado para el otro).'),
    ]

def buscar(lista, nombre):
    """La explicación cuyo nombre coincide con el comienzo del dato (la más larga); si no, la que aparezca dentro."""
    nl = nombre.lower()
    c = [(len(k), txt) for k, txt in lista if nl.startswith(k.lower())]
    if not c: c = [(len(k), txt) for k, txt in lista if k.lower() in nl]
    return max(c)[1] if c else ''
