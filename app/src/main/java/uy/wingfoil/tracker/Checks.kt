package uy.wingfoil.tracker

import android.Manifest
import android.app.Activity
import android.app.ActivityManager
import android.app.AlertDialog
import android.app.NotificationManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.hardware.Sensor
import android.hardware.SensorManager
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.os.StatFs
import android.provider.Settings
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** Test de permisos: revisa todo lo que puede cortar una grabación y dice qué falta. */
object Checks {

    private enum class Estado { OK, FALTA, REVISAR }
    private class Item(val estado: Estado, val titulo: String, val detalle: String, val arreglo: (() -> Unit)?)

    fun mostrar(a: Activity) {
        val items = revisar(a)
        val faltan = items.count { it.estado == Estado.FALTA }
        val revisar = items.count { it.estado == Estado.REVISAR }
        val d = a.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()

        val box = LinearLayout(a).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(8), dp(20), dp(8)) }
        box.addView(TextView(a).apply {
            textSize = 16f; setTextColor(if (faltan == 0) Color.rgb(46, 229, 157) else Color.rgb(255, 77, 109))
            text = when {
                faltan == 0 && revisar == 0 -> "Todo OK: la app puede grabar con la pantalla apagada."
                faltan == 0 -> "Lo esencial está OK. Revisá los puntos marcados con ⚠️."
                else -> "Falta${if (faltan > 1) "n" else ""} $faltan ajuste${if (faltan > 1) "s" else ""}. Tocá cada punto ❌ para corregirlo."
            }
            setPadding(0, 0, 0, dp(10))
        })
        for (it in items) {
            val icono = when (it.estado) { Estado.OK -> "✅"; Estado.FALTA -> "❌"; Estado.REVISAR -> "⚠️" }
            box.addView(TextView(a).apply {
                textSize = 15f; setTextColor(Color.WHITE)
                text = "$icono  ${it.titulo}" + if (it.estado != Estado.OK) "\n      ${it.detalle}" + (if (it.arreglo != null) "  → tocar para abrir" else "") else ""
                setPadding(0, dp(7), 0, dp(7))
                if (it.estado != Estado.OK && it.arreglo != null) {
                    isClickable = true
                    setOnClickListener { _ -> try { it.arreglo.invoke() } catch (_: Exception) { abrirAjustesApp(a) } }
                }
            })
        }
        AlertDialog.Builder(a)
            .setTitle("🩺 Test de permisos")
            .setView(ScrollView(a).apply { addView(box) })
            .setPositiveButton("Cerrar", null)
            .setNeutralButton("Volver a probar") { _, _ -> mostrar(a) }
            .show()
    }

    private fun abrirAjustesApp(a: Activity) =
        a.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${a.packageName}")))

    private fun revisar(a: Activity): List<Item> {
        val L = mutableListOf<Item>()
        val pkg = a.packageName
        val ajustesApp = { abrirAjustesApp(a) }

        // 1. Ubicación precisa
        val fine = a.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = a.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        L += Item(if (fine) Estado.OK else Estado.FALTA, "Permiso de ubicación precisa",
            if (coarse) "Está en ubicación aproximada: activá \"Usar ubicación precisa\"." else "Permisos → Ubicación → \"Permitir mientras se usa la app\" + ubicación precisa.",
            ajustesApp)

        // 2. GPS encendido
        val lm = a.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val gps = lm.isProviderEnabled(LocationManager.GPS_PROVIDER)
        L += Item(if (gps) Estado.OK else Estado.FALTA, "Ubicación (GPS) del teléfono encendida",
            "Activá la ubicación del teléfono.", { a.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)) })

        // 3. Notificaciones (la grabación con pantalla apagada necesita su notificación fija)
        val nm = a.getSystemService(NotificationManager::class.java)
        val notif = nm.areNotificationsEnabled() && (Build.VERSION.SDK_INT < 33 ||
                a.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED)
        L += Item(if (notif) Estado.OK else Estado.FALTA, "Notificaciones permitidas",
            "Sin la notificación fija, Android puede cortar la grabación. Activá las notificaciones de la app.",
            { a.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, pkg)) })

        // 4. Optimización de batería
        val pm = a.getSystemService(Context.POWER_SERVICE) as PowerManager
        val ignora = pm.isIgnoringBatteryOptimizations(pkg)
        L += Item(if (ignora) Estado.OK else Estado.FALTA, "Batería: sin optimización para la app",
            "Android puede dormir la app. Aceptá \"Permitir\" en el aviso que se abre.",
            {
                try { a.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$pkg"))) }
                catch (e: Exception) { a.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
            })

        // 5. Restricción de segundo plano
        val am = a.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val restr = am.isBackgroundRestricted
        L += Item(if (!restr) Estado.OK else Estado.FALTA, "Sin restricción de segundo plano",
            "Ajustes de la app → Ahorro de batería → \"Sin restricciones\".", ajustesApp)

        // 6. Ahorro de energía del sistema
        L += Item(if (!pm.isPowerSaveMode) Estado.OK else Estado.REVISAR, "Ahorro de batería del teléfono apagado",
            "Está activado: puede bajar la frecuencia del GPS. Apagalo durante la sesión.",
            { a.startActivity(Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS)) })

        // 7. Acelerómetro (saltos)
        val sm = a.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val acc = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) != null
        L += Item(if (acc) Estado.OK else Estado.REVISAR, "Acelerómetro disponible (detección de saltos)",
            "El teléfono no tiene acelerómetro: se graba el GPS pero no se detectan saltos.", null)

        // 8. Espacio libre
        val libreMb = try {
            val st = StatFs((a.getExternalFilesDir(null) ?: a.filesDir).absolutePath); st.availableBytes / (1024 * 1024)
        } catch (_: Exception) { -1L }
        L += Item(if (libreMb < 0 || libreMb >= 500) Estado.OK else Estado.FALTA,
            "Espacio libre suficiente" + (if (libreMb >= 0) " (${libreMb} MB)" else ""),
            "Quedan menos de 500 MB: una sesión de 2 h ocupa unos 100 MB. Liberá espacio.",
            { a.startActivity(Intent(Settings.ACTION_INTERNAL_STORAGE_SETTINGS)) })

        // 9. Xiaomi / Redmi / POCO: inicio automático (no se puede leer, hay que revisarlo a mano)
        val marca = Build.MANUFACTURER.lowercase()
        if (marca.contains("xiaomi") || marca.contains("redmi") || marca.contains("poco")) {
            L += Item(Estado.REVISAR, "Xiaomi: \"Inicio automático\" activado",
                "Android no deja comprobarlo desde la app. Activá \"Inicio automático\" para Wingfoil & PW Tracker y, en recientes, bloqueá la app con el candado.",
                {
                    try {
                        a.startActivity(Intent().setComponent(ComponentName("com.miui.securitycenter",
                            "com.miui.permcenter.autostart.AutoStartManagementActivity")))
                    } catch (e: Exception) { abrirAjustesApp(a) }
                })
        } else if (marca.contains("samsung")) {
            L += Item(Estado.REVISAR, "Samsung: app fuera de \"Apps en suspensión\"",
                "Batería → Límites de uso en segundo plano: agregá la app a \"Apps que nunca se suspenden\".", ajustesApp)
        } else if (marca.contains("huawei") || marca.contains("honor")) {
            L += Item(Estado.REVISAR, "Huawei/Honor: inicio de aplicaciones manual",
                "Batería → Inicio de aplicaciones → Wingfoil & PW Tracker → gestión manual, todo activado.", ajustesApp)
        }
        return L
    }
}
