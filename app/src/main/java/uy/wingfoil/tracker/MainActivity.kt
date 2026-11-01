package uy.wingfoil.tracker

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.provider.Settings
import android.view.Gravity
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {

    private lateinit var tvTime: TextView
    private lateinit var tvState: TextView
    private lateinit var tvStats: TextView
    private lateinit var btnMain: Button
    private lateinit var btnResume: Button
    private lateinit var btnBattery: Button
    private lateinit var list: LinearLayout
    private val ui = Handler(Looper.getMainLooper())
    private var wasRunning = false

    private val tick = object : Runnable {
        override fun run() { refresh(); ui.postDelayed(this, 1000) }
    }

    private val bg = Color.rgb(6, 20, 38)
    private val card = Color.rgb(13, 35, 64)
    private val acc = Color.rgb(0, 200, 255)
    private val red = Color.rgb(255, 77, 109)
    private val mut = Color.rgb(143, 169, 199)

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun text(size: Float, color: Int = Color.WHITE, bold: Boolean = false) = TextView(this).apply {
        textSize = size; setTextColor(color)
        if (bold) typeface = Typeface.DEFAULT_BOLD
    }

    private fun button(label: String, color: Int, txtColor: Int = Color.BLACK) = Button(this).apply {
        text = label; setBackgroundColor(color); setTextColor(txtColor); textSize = 18f
        typeface = Typeface.DEFAULT_BOLD; isAllCaps = false
        layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(10) }
        setPadding(dp(12), dp(16), dp(12), dp(16))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = bg
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(20), dp(16), dp(24))
            setBackgroundColor(bg)
        }
        root.addView(text(20f, Color.WHITE, true).apply { text = "🪁 Wingfoil Tracker" })

        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(card)
            setPadding(dp(14), dp(14), dp(14), dp(14)); gravity = Gravity.CENTER_HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(12) }
        }
        tvTime = text(54f, Color.WHITE, true).apply { text = "00:00:00"; typeface = Typeface.MONOSPACE; gravity = Gravity.CENTER }
        tvState = text(18f, mut, true).apply { text = "Listo para grabar"; gravity = Gravity.CENTER }
        tvStats = text(15f, mut).apply { gravity = Gravity.CENTER; setPadding(0, dp(6), 0, 0) }
        panel.addView(tvTime); panel.addView(tvState); panel.addView(tvStats)
        root.addView(panel)

        btnMain = button("▶  GRABAR", acc)
        btnMain.setOnClickListener {
            if (TrackService.running) Toast.makeText(this, "Mantené apretado para terminar", Toast.LENGTH_SHORT).show()
            else tryStart(resume = false)
        }
        btnMain.setOnLongClickListener {
            if (TrackService.running) confirmStop(); true
        }
        root.addView(btnMain)

        btnResume = button("⟳  Reanudar grabación interrumpida", Color.rgb(255, 190, 11))
        btnResume.setOnClickListener { tryStart(resume = true) }
        root.addView(btnResume)

        btnBattery = button("🔋  Quitar optimización de batería (recomendado)", card, Color.WHITE)
        btnBattery.setOnClickListener { askBattery() }
        root.addView(btnBattery)

        root.addView(button("⚙  Ajustes de la app (batería sin restricciones)", card, Color.WHITE).apply {
            textSize = 15f
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
            }
        })

        root.addView(text(14f, mut, true).apply {
            text = "SESIONES GUARDADAS"; setPadding(0, dp(20), 0, dp(6))
        })
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(list)

        root.addView(text(12f, mut).apply {
            setPadding(0, dp(16), 0, 0)
            text = "Con la grabación iniciada podés apagar la pantalla. El track se guarda punto a punto; " +
                "si se pierde la señal bajo el agua, el GPS se reintenta solo hasta que vuelve.\n" +
                "Compartir guarda el ZIP en Descargas/WingFoil (Location.csv + Metadata.csv formato Sensor Logger + track.gpx)."
        })

        setContentView(ScrollView(this).apply { setBackgroundColor(bg); addView(root) })
    }

    override fun onResume() {
        super.onResume()
        ui.post(tick)
        buildList()
    }

    override fun onPause() {
        super.onPause()
        ui.removeCallbacks(tick)
    }

    /* ---------- Grabar / terminar ---------- */
    private fun tryStart(resume: Boolean) {
        val need = mutableListOf<String>()
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            need += Manifest.permission.ACCESS_FINE_LOCATION
            need += Manifest.permission.ACCESS_COARSE_LOCATION
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            need += Manifest.permission.POST_NOTIFICATIONS
        }
        if (need.isNotEmpty()) {
            requestPermissions(need.toTypedArray(), if (resume) 2 else 1)
            return
        }
        val lm = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        if (!lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
            Toast.makeText(this, "Activá la ubicación (GPS) del teléfono", Toast.LENGTH_LONG).show()
            startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
            return
        }
        val i = Intent(this, TrackService::class.java)
        if (!resume) i.action = TrackService.ACTION_START      // sin acción = retomar la sesión abierta
        startForegroundService(i)
        ui.postDelayed({ buildList() }, 800)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            tryStart(resume = requestCode == 2)
        } else {
            AlertDialog.Builder(this)
                .setTitle("Falta permiso de ubicación precisa")
                .setMessage("Sin ubicación PRECISA no se puede grabar el track. En Ajustes → Permisos → Ubicación elegí \"Permitir mientras se usa la app\" y activá \"Usar ubicación precisa\".")
                .setPositiveButton("Abrir ajustes") { _, _ ->
                    startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
                }
                .setNegativeButton("Cancelar", null).show()
        }
    }

    private fun confirmStop() {
        AlertDialog.Builder(this)
            .setTitle("¿Terminar la grabación?")
            .setPositiveButton("Terminar") { _, _ ->
                startService(Intent(this, TrackService::class.java).setAction(TrackService.ACTION_STOP))
                ui.postDelayed({ buildList() }, 800)
            }
            .setNegativeButton("Seguir grabando", null).show()
    }

    private fun askBattery() {
        try {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    /* ---------- Pantalla ---------- */
    private fun refresh() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        btnBattery.visibility = if (pm.isIgnoringBatteryOptimizations(packageName)) android.view.View.GONE else android.view.View.VISIBLE

        val running = TrackService.running
        val openDir = TrackService.prefs(this).getString("activeDir", null)
        btnResume.visibility = if (!running && openDir != null && File(openDir).exists()) android.view.View.VISIBLE else android.view.View.GONE

        if (running) {
            val s = (System.currentTimeMillis() - TrackService.startWall) / 1000
            tvTime.text = String.format(Locale.US, "%02d:%02d:%02d", s / 3600, (s / 60) % 60, s % 60)
            val now = SystemClock.elapsedRealtime()
            val last = TrackService.lastFixElapsed
            when {
                last == 0L -> { tvState.text = "Buscando GPS…"; tvState.setTextColor(Color.rgb(255, 190, 11)) }
                now - last < 3000 -> { tvState.text = "GPS OK ±${TrackService.lastAcc.toInt()} m"; tvState.setTextColor(Color.rgb(46, 229, 157)) }
                else -> { tvState.text = "Sin señal ${(now - last) / 1000} s"; tvState.setTextColor(red) }
            }
            tvStats.text = String.format(Locale.US,
                "%.1f kn ahora · máx %.1f kn\n%.2f km · %d puntos\ncortes GPS %d · reintentos %d",
                TrackService.lastSpeedKn, TrackService.maxKn, TrackService.distM / 1000,
                TrackService.points, TrackService.gaps, TrackService.restarts)
            btnMain.text = "■  TERMINAR (mantener apretado)"
            btnMain.setBackgroundColor(red); btnMain.setTextColor(Color.WHITE)
        } else {
            tvState.text = "Listo para grabar"; tvState.setTextColor(mut)
            tvStats.text = ""
            btnMain.text = "▶  GRABAR"
            btnMain.setBackgroundColor(acc); btnMain.setTextColor(Color.BLACK)
        }
        if (wasRunning && !running) buildList()
        wasRunning = running
    }

    private fun buildList() {
        list.removeAllViews()
        val active = if (TrackService.running) TrackService.sessionDir?.name else null
        val dirs = TrackService.sessionsRoot(this).listFiles { f -> f.isDirectory }
            ?.sortedByDescending { it.name } ?: emptyList()
        val shown = dirs.filter { it.name != active }
        if (shown.isEmpty()) {
            list.addView(text(14f, mut).apply { text = "Todavía no hay sesiones." }); return
        }
        val fmt = SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault())
        for (d in shown) {
            val sm = Exporter.summary(d)
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; setBackgroundColor(card)
                setPadding(dp(12), dp(10), dp(12), dp(10))
                layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { bottomMargin = dp(8) }
            }
            val dur = if (sm.points > 1) (sm.lastMs - sm.firstMs) / 1000 else 0
            row.addView(text(16f, Color.WHITE, true).apply {
                text = if (sm.points > 0) fmt.format(Date(sm.firstMs)) else d.name
            })
            row.addView(text(13f, mut).apply {
                text = String.format(Locale.US, "%d:%02d:%02d · %d puntos", dur / 3600, (dur / 60) % 60, dur % 60, sm.points)
            })
            val btns = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            val share = Button(this).apply {
                text = "📤 Exportar / compartir"; isAllCaps = false
                layoutParams = LinearLayout.LayoutParams(0, WRAP_CONTENT, 2f)
                setOnClickListener { share(d) }
            }
            val del = Button(this).apply {
                text = "🗑"; layoutParams = LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f)
                setOnClickListener {
                    AlertDialog.Builder(this@MainActivity).setTitle("¿Borrar esta sesión?")
                        .setMessage("Si ya la exportaste, el ZIP en Descargas no se borra.")
                        .setPositiveButton("Borrar") { _, _ ->
                            if (TrackService.prefs(this@MainActivity).getString("activeDir", null) == d.absolutePath)
                                TrackService.prefs(this@MainActivity).edit().remove("activeDir").apply()
                            d.deleteRecursively(); buildList()
                        }
                        .setNegativeButton("Cancelar", null).show()
                }
            }
            btns.addView(share); btns.addView(del)
            row.addView(btns)
            list.addView(row)
        }
    }

    private fun share(dir: File) {
        try {
            val uri = Exporter.zipToDownloads(this, dir)
            if (uri == null) { Toast.makeText(this, "No se pudo crear el ZIP", Toast.LENGTH_LONG).show(); return }
            Toast.makeText(this, "Guardado en Descargas/WingFoil/${dir.name}.zip", Toast.LENGTH_LONG).show()
            val send = Intent(Intent.ACTION_SEND).apply {
                type = "application/zip"
                putExtra(Intent.EXTRA_STREAM, uri)
                putExtra(Intent.EXTRA_SUBJECT, dir.name)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            startActivity(Intent.createChooser(send, "Compartir sesión"))
        } catch (e: Exception) {
            Toast.makeText(this, "Error al exportar: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }
}
