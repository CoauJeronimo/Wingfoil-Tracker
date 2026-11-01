# Wingfoil Tracker — app Android nativa

Graba el track GPS **con la pantalla apagada** y lo exporta en un ZIP con `Location.csv` + `Metadata.csv`
(formato Sensor Logger, sirve directo para `wingfoil_analisis.py`) + `track.gpx`.

## Cómo funciona
- **Servicio en primer plano** con notificación fija "Grabando track": Android no lo mata como a una app en segundo plano.
- **Wake lock parcial**: el procesador sigue despierto con la pantalla apagada.
- **GPS directo** (`GPS_PROVIDER`, intervalo 0): guarda cada fix que da el chip (normalmente 1 Hz), con precisión
  horizontal, vertical, de velocidad y de rumbo.
- **Bajo el agua**: si pasan 15 s sin fix, reinicia el GPS, y lo sigue haciendo hasta que vuelve la señal.
  El tiempo sin señal queda como hueco en el track.
- **Sin pérdidas**: cada punto se escribe en el archivo al instante. Si el sistema llegara a matar el servicio,
  se reinicia solo y sigue en la misma sesión (o aparece el botón "Reanudar").

## Compilar el APK (sin instalar nada)
1. Creá una cuenta en https://github.com (gratis) y un repositorio nuevo (privado si querés).
2. En el repositorio: **Add file → Upload files** y arrastrá **todo el contenido** de esta carpeta
   (incluida la carpeta `.github`). Confirmá con **Commit changes**.
3. Andá a la pestaña **Actions**: se compila solo (unos 4-5 minutos).
4. Cuando termina (tilde verde), el APK queda en **Releases → latest → WingfoilTracker.apk**.

## Instalar en el teléfono
1. Abrí ese enlace desde el teléfono y descargá `WingfoilTracker.apk`.
2. Android pide permitir "instalar apps desconocidas" para el navegador o Archivos: aceptá.
3. Al abrir la app y tocar GRABAR, aceptá **ubicación precisa** y **notificaciones**.
4. Tocá **"Quitar optimización de batería"** y aceptá.

Las versiones nuevas se instalan encima sin perder las sesiones (la firma es siempre la misma).

## Ajustes extra según la marca (importante)
- **Todas**: Ajustes → Apps → Wingfoil Tracker → Batería → **Sin restricciones**.
- **Samsung**: Batería → Límites de uso en segundo plano → que la app NO esté en "Apps en suspensión";
  agregala a "Apps que nunca se suspenden".
- **Xiaomi / Redmi / POCO**: Ajustes de la app → **Inicio automático** activado; Ahorro de batería → **Sin restricciones**.
  En la lista de apps recientes, bloqueá la app con el candado.
- **Huawei / Honor**: Batería → Inicio de aplicaciones → Wingfoil Tracker → gestión **manual**, todo activado.
- **Motorola / Pixel**: con "Sin restricciones" alcanza.
- No uses el modo **ahorro de energía extremo** durante la sesión.

## Uso
1. Abrí la app al aire libre y tocá **GRABAR**. Esperá a que diga **GPS OK** (±3-5 m).
2. Apagá la pantalla y guardá el teléfono. Podés salir de la app: la notificación indica que sigue grabando.
3. Para terminar: abrí la app y **mantené apretado** el botón TERMINAR (tocarlo una vez no hace nada,
   por las manos mojadas).
4. En la sesión: **Exportar / compartir** → guarda el ZIP en `Descargas/WingFoil` y abre el menú para mandarlo
   a Drive, WhatsApp, mail, etc.
