package uy.wingfoil.tracker

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import java.io.BufferedWriter
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Servicio en primer plano que graba el GPS con la pantalla apagada.
 * - Notificación fija (Android no puede matarlo como a una app en segundo plano)
 * - PARTIAL_WAKE_LOCK: el procesador no se duerme aunque la pantalla esté apagada
 * - GPS_PROVIDER directo, intervalo 0 = cada fix que entregue el chip (normalmente 1 Hz)
 * - Perro guardián: sin fix durante STALE_MS (teléfono bajo el agua) => reinicia el GPS, una y otra vez
 * - Cada punto se escribe y se vacía al disco al instante (Location.csv formato Sensor Logger)
 * - START_STICKY + estado en preferencias: si el sistema lo reinicia, retoma la misma sesión
 */
class TrackService : Service() {

    companion object {
        const val ACTION_START = "uy.wingfoil.tracker.START"
        const val ACTION_STOP = "uy.wingfoil.tracker.STOP"
        private const val CHANNEL = "tracking"
        private const val NOTIF_ID = 7
        private const val STALE_MS = 15_000L
        private const val GAP_MS = 5_000L
        private const val KN = 1.943844

        @Volatile var running = false
        @Volatile var points = 0
        @Volatile var gaps = 0
        @Volatile var restarts = 0
        @Volatile var startWall = 0L
        @Volatile var lastFixElapsed = 0L
        @Volatile var lastAcc = 0f
        @Volatile var lastSpeedKn = 0.0
        @Volatile var maxKn = 0.0
        @Volatile var distM = 0.0
        @Volatile var sessionDir: File? = null

        const val LOCATION_HEADER =
            "time,seconds_elapsed,bearingAccuracy,speedAccuracy,verticalAccuracy,horizontalAccuracy,speed,bearing,altitude,longitude,latitude"

        fun sessionsRoot(ctx: Context): File =
            File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "sessions").apply { mkdirs() }

        fun prefs(ctx: Context) = ctx.getSharedPreferences("track", Context.MODE_PRIVATE)
    }

    private lateinit var lm: LocationManager
    private var wakeLock: PowerManager.WakeLock? = null
    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private var writer: BufferedWriter? = null
    private var last: Location? = null
    private var t0 = 0L                 // hora (ms) del primer fix de la sesión
    private var watchStartedElapsed = 0L

    // Acelerómetro (para detectar saltos): TotalAcceleration.csv, formato Sensor Logger (time,seconds_elapsed,z,y,x)
    private var accThread: HandlerThread? = null
    private var accWriter: BufferedWriter? = null
    private var accOffsetNs = 0L          // reloj de pared - reloj del sensor
    private val accListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            val w = accWriter ?: return
            val wallNs = e.timestamp + accOffsetNs
            val sb = StringBuilder(64)
            sb.append(wallNs).append(',')
            sb.append(String.format(Locale.US, "%.3f", (wallNs / 1_000_000L - startWall) / 1000.0)).append(',')
            sb.append(String.format(Locale.US, "%.4f,%.4f,%.4f", e.values[2], e.values[1], e.values[0])).append('\n')
            try { w.write(sb.toString()) } catch (_: Exception) { }
        }
        override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
    }

    private fun startAccel(dir: File) {
        val sm = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val acc = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) ?: return
        val f = File(dir, "TotalAcceleration.csv")
        val nuevo = !f.exists() || f.length() == 0L
        accWriter = BufferedWriter(FileWriter(f, true), 64 * 1024).apply { if (nuevo) write("time,seconds_elapsed,z,y,x\n") }
        accOffsetNs = System.currentTimeMillis() * 1_000_000L - SystemClock.elapsedRealtimeNanos()
        accThread = HandlerThread("acc").apply { start() }
        sm.registerListener(accListener, acc, 10_000, 0, Handler(accThread!!.looper))     // 100 Hz, sin demora
    }

    private fun stopAccel() {
        try { (getSystemService(Context.SENSOR_SERVICE) as SensorManager).unregisterListener(accListener) } catch (_: Exception) { }
        accThread?.quitSafely(); accThread = null
        try { accWriter?.flush(); accWriter?.close() } catch (_: Exception) { }
        accWriter = null
    }

    private val listener = object : LocationListener {
        override fun onLocationChanged(l: Location) = onFix(l)
        override fun onProviderEnabled(provider: String) {}
        override fun onProviderDisabled(provider: String) {}
        @Deprecated("Deprecated in Java")
        override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
    }

    private val watchdog = object : Runnable {
        override fun run() {
            if (!running) return
            val now = SystemClock.elapsedRealtime()
            val ref = if (lastFixElapsed > 0) maxOf(lastFixElapsed, watchStartedElapsed) else watchStartedElapsed
            if (now - ref > STALE_MS) {
                restarts++
                startGps()            // reintenta hasta que vuelva la señal
            }
            if (wakeLock?.isHeld != true) acquireWakeLock()
            try { accWriter?.flush() } catch (_: Exception) { }
            updateNotification()
            handler?.postDelayed(this, 3_000L)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        lm = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, "Grabación de track", NotificationManager.IMPORTANCE_LOW).apply {
                setShowBadge(false)
            }
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { stopRecording(); return START_NOT_STICKY }
            ACTION_START -> if (!running) beginRecording(resumeDir = null)
            else -> {
                // Reinicio por el sistema (intent nulo): retomar la sesión que estaba abierta
                val dir = prefs(this).getString("activeDir", null)
                if (!running && dir != null && File(dir).exists()) beginRecording(File(dir))
                else if (!running) { stopSelf(); return START_NOT_STICKY }
            }
        }
        return START_STICKY
    }

    private fun beginRecording(resumeDir: File?) {
        val fmt = SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.US)
        val p = prefs(this)
        val dir: File
        if (resumeDir == null) {
            startWall = System.currentTimeMillis()
            dir = File(sessionsRoot(this), "WingFoil_" + fmt.format(Date(startWall)))
            dir.mkdirs()
            File(dir, "Location.csv").writeText(LOCATION_HEADER + "\n")
            t0 = 0L; points = 0; gaps = 0; distM = 0.0; maxKn = 0.0
            p.edit().putString("activeDir", dir.absolutePath).putLong("startWall", startWall)
                .putLong("t0", 0L).apply()
        } else {
            dir = resumeDir
            startWall = p.getLong("startWall", System.currentTimeMillis())
            t0 = p.getLong("t0", 0L)
            points = maxOf(0, File(dir, "Location.csv").useLines { it.count() } - 1)
            gaps++  // la interrupción cuenta como corte
        }
        sessionDir = dir
        writeMetadata(dir)
        writer = BufferedWriter(FileWriter(File(dir, "Location.csv"), true))
        last = null; restarts = 0; lastFixElapsed = 0L; lastSpeedKn = 0.0; lastAcc = 0f
        running = true

        val notif = buildNotification("Buscando GPS…")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        } else startForeground(NOTIF_ID, notif)

        acquireWakeLock()
        thread = HandlerThread("gps").apply { start() }
        handler = Handler(thread!!.looper)
        startGps()
        handler?.postDelayed(watchdog, 3_000L)
        try { startAccel(dir) } catch (_: Exception) { }
    }

    @SuppressLint("MissingPermission")
    private fun startGps() {
        val looper = thread?.looper ?: return
        try {
            lm.removeUpdates(listener)
            lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 0L, 0f, listener, looper)
            watchStartedElapsed = SystemClock.elapsedRealtime()
        } catch (e: SecurityException) {
            stopRecording()
        } catch (e: Exception) {
            // GPS apagado u otro problema: el perro guardián vuelve a intentar
            watchStartedElapsed = SystemClock.elapsedRealtime()
        }
    }

    private fun acquireWakeLock() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        if (wakeLock == null) {
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "WingfoilTracker::gps").apply {
                setReferenceCounted(false)
            }
        }
        wakeLock?.acquire(12 * 60 * 60 * 1000L) // hasta 12 h
    }

    private fun onFix(l: Location) {
        val prev = last
        if (prev != null && l.time <= prev.time) return   // fix repetido
        val now = SystemClock.elapsedRealtime()
        if (lastFixElapsed > 0 && now - lastFixElapsed > GAP_MS) gaps++
        lastFixElapsed = now

        if (t0 == 0L) { t0 = l.time; prefs(this).edit().putLong("t0", t0).apply() }

        if (prev != null) {
            val d = prev.distanceTo(l).toDouble()
            val dt = (l.time - prev.time) / 1000.0
            if (dt > 0 && l.accuracy <= 25f && d / dt < 30.0) distM += d
        }
        val kn = if (l.hasSpeed()) l.speed * KN else 0.0
        lastSpeedKn = kn
        if (l.hasSpeed() && l.accuracy <= 25f && l.speed < 30f && kn > maxKn) maxKn = kn
        lastAcc = l.accuracy

        val sb = StringBuilder(160)
        sb.append(l.time * 1_000_000L).append(',')
        sb.append(String.format(Locale.US, "%.3f", (l.time - t0) / 1000.0)).append(',')
        sb.append(if (l.hasBearingAccuracy()) f(l.bearingAccuracyDegrees.toDouble(), 2) else "").append(',')
        sb.append(if (l.hasSpeedAccuracy()) f(l.speedAccuracyMetersPerSecond.toDouble(), 3) else "").append(',')
        sb.append(if (l.hasVerticalAccuracy()) f(l.verticalAccuracyMeters.toDouble(), 2) else "").append(',')
        sb.append(if (l.hasAccuracy()) f(l.accuracy.toDouble(), 2) else "").append(',')
        sb.append(if (l.hasSpeed()) f(l.speed.toDouble(), 4) else "").append(',')
        sb.append(if (l.hasBearing()) f(l.bearing.toDouble(), 2) else "").append(',')
        sb.append(if (l.hasAltitude()) f(l.altitude, 2) else "").append(',')
        sb.append(f(l.longitude, 8)).append(',')
        sb.append(f(l.latitude, 8)).append('\n')
        try {
            writer?.write(sb.toString())
            writer?.flush()
        } catch (_: Exception) { }
        points++
        last = l
    }

    private fun f(x: Double, d: Int) = String.format(Locale.US, "%.${d}f", x)

    private fun writeMetadata(dir: File) {
        val fmt = SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.US)
        val start = if (t0 > 0) t0 else startWall
        val txt = "version,device name,recording epoch time,recording time,recording timezone,platform,appVersion,device id,sensors,sampleRateMs,standardisation\n" +
            listOf("3", "${Build.MANUFACTURER} ${Build.MODEL}".replace(",", " "), start.toString(),
                fmt.format(Date(start)), TimeZone.getDefault().id, "android", "WingfoilTracker-Android-1.5",
                dir.name, "Location|TotalAcceleration", "1000|10", "false").joinToString(",") + "\n"
        try { File(dir, "Metadata.csv").writeText(txt) } catch (_: Exception) { }
    }

    private fun stopRecording() {
        running = false
        stopAccel()
        handler?.removeCallbacksAndMessages(null)
        try { lm.removeUpdates(listener) } catch (_: Exception) { }
        try { writer?.flush(); writer?.close() } catch (_: Exception) { }
        writer = null
        sessionDir?.let { writeMetadata(it) }
        prefs(this).edit().remove("activeDir").apply()
        thread?.quitSafely(); thread = null
        try { if (wakeLock?.isHeld == true) wakeLock?.release() } catch (_: Exception) { }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        // Si el sistema destruye el servicio sin "Terminar", se deja todo guardado y la sesión abierta para retomar
        if (running) {
            running = false
            stopAccel()
            handler?.removeCallbacksAndMessages(null)
            try { lm.removeUpdates(listener) } catch (_: Exception) { }
            try { writer?.flush(); writer?.close() } catch (_: Exception) { }
            thread?.quitSafely()
            try { if (wakeLock?.isHeld == true) wakeLock?.release() } catch (_: Exception) { }
        }
        super.onDestroy()
    }

    /* ---------- Notificación ---------- */
    private fun status(): String {
        val now = SystemClock.elapsedRealtime()
        return when {
            lastFixElapsed == 0L -> "Buscando GPS…"
            now - lastFixElapsed < 3_000 -> "GPS OK ±${lastAcc.toInt()} m"
            else -> "Sin señal ${(now - lastFixElapsed) / 1000} s"
        }
    }

    private fun updateNotification() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIF_ID, buildNotification(status()))
    }

    private fun buildNotification(state: String): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val secs = (System.currentTimeMillis() - startWall) / 1000
        val text = String.format(Locale.US, "%s · %d pts · %.2f km · máx %.1f kn",
            state, points, distM / 1000, maxKn)
        val b = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("Grabando track · " + String.format(Locale.US, "%d:%02d:%02d", secs / 3600, (secs / 60) % 60, secs % 60))
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(open)
            .setCategory(Notification.CATEGORY_SERVICE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE)
        }
        return b.build()
    }
}
