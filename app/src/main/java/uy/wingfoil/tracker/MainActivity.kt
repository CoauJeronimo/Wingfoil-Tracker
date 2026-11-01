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
import android.widget.EditText
import android.widget.CheckBox
import android.text.InputType
import android.content.ActivityNotFoundException
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {

    companion object { private const val REQ_IMPORT = 41 }

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

        root.addView(button("📥  Importar ZIP de Sensor Logger", card, Color.WHITE).apply {
            textSize = 15f
            setOnClickListener {
                val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE); type = "*/*"
                    putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream"))
                }
                try { startActivityForResult(i, REQ_IMPORT) } catch (e: Exception) { toast("No se pudo abrir el selector de archivos") }
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
            val analyze = Button(this).apply {
                text = "📊 Analizar"; isAllCaps = false
                layoutParams = LinearLayout.LayoutParams(0, WRAP_CONTENT, 2f)
                setOnClickListener { analyzeDialog(d) }
            }
            val share = Button(this).apply {
                text = "📤 ZIP"; isAllCaps = false
                layoutParams = LinearLayout.LayoutParams(0, WRAP_CONTENT, 1.4f)
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
            btns.addView(analyze); btns.addView(share); btns.addView(del)
            row.addView(btns)
            list.addView(row)
        }
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

    /* ---------- Importar ZIP de Sensor Logger ---------- */
    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_IMPORT || resultCode != RESULT_OK) return
        val uri = data?.data ?: return
        val wait = AlertDialog.Builder(this).setMessage("Importando…").setCancelable(false).show()
        Thread {
            val dir = try {
                contentResolver.openInputStream(uri)?.use { Analysis.importZip(this, it, uri.lastPathSegment) }
            } catch (e: Exception) { null }
            runOnUiThread {
                wait.dismiss()
                if (dir == null) toast("Ese archivo no es un ZIP con Location.csv")
                else { toast("Sesión importada: ${dir.name}"); buildList() }
            }
        }.start()
    }

    /* ---------- Análisis WingFoil Completo ---------- */
    private fun field(hint: String, value: String, type: Int): EditText = EditText(this).apply {
        this.hint = hint; setText(value); inputType = type; textSize = 17f
        setTextColor(Color.WHITE); setHintTextColor(mut)
    }

    private fun analyzeDialog(dir: File) {
        val p = TrackService.prefs(this)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(8), dp(20), 0) }
        fun label(s: String) = box.addView(text(13f, mut, true).apply { text = s; setPadding(0, dp(10), 0, 0) })
        label("Viento: grados de DONDE VIENE (obligatorio)")
        val fWind = field("ej. 169", p.getString("lastWind", "") ?: "", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL)
        box.addView(fWind)
        label("Fecha de la sesión")
        val fFecha = field("DD-MM-AAAA", Analysis.fechaSesion(dir), InputType.TYPE_CLASS_TEXT)
        box.addView(fFecha)
        label("Secciones del KML")
        val fSec = field("3", p.getString("lastSections", "3") ?: "3", InputType.TYPE_CLASS_NUMBER)
        box.addView(fSec)
        label("Tramos a excluir (opcional, hora local)")
        val fExc = field("14:57:18-15:09:39, …", "", InputType.TYPE_CLASS_TEXT)
        box.addView(fExc)
        val cSat = CheckBox(this).apply {
            text = "Foto satelital de fondo en el mapa (usa internet; queda guardada para la próxima)"
            setTextColor(Color.WHITE); textSize = 14f
            isChecked = p.getBoolean("lastSat", true)
            setPadding(0, dp(12), 0, dp(8))
        }
        box.addView(cSat)

        val dlg = AlertDialog.Builder(this)
            .setTitle("Analizar sesión")
            .setView(ScrollView(this).apply { addView(box) })
            .setPositiveButton("Analizar", null)
            .setNegativeButton("Cancelar", null)
            .show()
        dlg.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val wind = fWind.text.toString().replace(',', '.').toDoubleOrNull()
            val sec = fSec.text.toString().toIntOrNull() ?: 3
            val fecha = fFecha.text.toString().trim()
            when {
                wind == null || wind < 0 || wind > 360 -> fWind.error = "Poné los grados (0 a 360)"
                !Regex("""\d{2}-\d{2}-\d{4}""").matches(fecha) -> fFecha.error = "Formato DD-MM-AAAA"
                sec < 1 || sec > 50 -> fSec.error = "Entre 1 y 50"
                else -> {
                    p.edit().putString("lastWind", fWind.text.toString()).putString("lastSections", sec.toString())
                        .putBoolean("lastSat", cSat.isChecked).apply()
                    dlg.dismiss()
                    runAnalysis(dir, wind, fecha, sec, fExc.text.toString(), cSat.isChecked)
                }
            }
        }
    }

    private fun runAnalysis(dir: File, wind: Double, fecha: String, sec: Int, exc: String, sat: Boolean) {
        val wait = AlertDialog.Builder(this).setTitle("Analizando…")
            .setMessage("Calculando maniobras y armando el PDF y el KML.\nLa primera vez tarda unos segundos más.")
            .setCancelable(false).show()
        Thread {
            val r = try { Analysis.run(this, dir, wind, fecha, sec, exc, sat) }
                    catch (e: Throwable) { Analysis.Result(false, error = e.toString()) }
            var pdfUri: Uri? = null; var kmlUri: Uri? = null
            if (r.ok) try {
                pdfUri = Analysis.saveToDownloads(this, r.pdf!!, "application/pdf")
                kmlUri = Analysis.saveToDownloads(this, r.kml!!, "application/vnd.google-earth.kml+xml")
                Analysis.saveToDownloads(this, r.xlsx!!, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            } catch (_: Exception) { }
            runOnUiThread {
                wait.dismiss()
                if (!r.ok) {
                    AlertDialog.Builder(this).setTitle("No se pudo analizar").setMessage(r.error)
                        .setPositiveButton("OK", null).show()
                    return@runOnUiThread
                }
                AlertDialog.Builder(this)
                    .setTitle("Análisis listo · $fecha")
                    .setMessage(r.resumen + "\n\nGuardado en Descargas/WingFoil/Analisis (PDF, KML y Excel).")
                    .setPositiveButton("Ver PDF") { _, _ ->
                        if (pdfUri != null) try {
                            startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(pdfUri, "application/pdf")
                                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                        } catch (e: ActivityNotFoundException) { toast("No hay un visor de PDF instalado") }
                    }
                    .setNeutralButton("Compartir PDF + KML") { _, _ ->
                        val uris = ArrayList<Uri>().apply { pdfUri?.let { add(it) }; kmlUri?.let { add(it) } }
                        if (uris.isEmpty()) { toast("No se pudieron guardar los archivos"); return@setNeutralButton }
                        val send = Intent(Intent.ACTION_SEND_MULTIPLE).apply {
                            type = "*/*"
                            putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
                            putExtra(Intent.EXTRA_SUBJECT, "Análisis wingfoil $fecha")
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        }
                        startActivity(Intent.createChooser(send, "Compartir análisis"))
                    }
                    .setNegativeButton("Cerrar", null)
                    .show()
            }
        }.start()
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
