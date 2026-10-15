package fr.coucou.android

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.speech.RecognizerIntent
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.RequiresApi
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.atomic.AtomicInteger

private val bg = Color(0xFF08090D)
private val surface = Color(0xFF151923)
private val accent = Color(0xFF7AA2FF)
private val mint = Color(0xFF4FD6A0)
private val muted = Color(0xFF929BAD)
private val warning = Color(0xFFFFB454)
private val danger = Color(0xFFFF6B7D)

class MainActivity : ComponentActivity(), SensorEventListener {
    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null
    private var shakeCounter = AtomicInteger(0)
    private val handler = Handler(Looper.getMainLooper())
    private var lastShakeTime = 0L
    private var wakeWordTriggered = false
    
    @RequiresApi(Build.VERSION_CODES.M)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Check for wake word trigger
        wakeWordTriggered = intent.getBooleanExtra("wake_word_triggered", false)
        
        // Initialize sensor for shake detection
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        
        setContent { 
            MaterialTheme(colorScheme = darkColorScheme(primary = accent, background = bg, surface = surface)) {
                CoucouApp()
            }
        }
    }
    
    override fun onResume() {
        super.onResume()
        accelerometer?.let { sensor ->
            sensorManager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_NORMAL)
        }
    }
    
    override fun onPause() {
        super.onPause()
        sensorManager.unregisterListener(this)
    }
    
    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type == Sensor.TYPE_ACCELEROMETER) {
            val x = event.values[0]
            val y = event.values[1]
            val z = event.values[2]
            
            val gX = x / SensorManager.GRAVITY_EARTH
            val gY = y / SensorManager.GRAVITY_EARTH
            val gZ = z / SensorManager.GRAVITY_EARTH
            
            val gForce = Math.sqrt(gX * gX + gY * gY + gZ * gZ)
            
            if (gForce > 2.5f) {
                val currentTime = System.currentTimeMillis()
                if (currentTime - lastShakeTime < 500) {
                    return
                }
                lastShakeTime = currentTime
                
                val count = shakeCounter.incrementAndGet()
                if (count >= 3) {
                    shakeCounter.set(0)
                    handler.post {
                        Toast.makeText(this, "Secoue détectée !", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
    }
    
    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) {}
    
    override fun onDestroy() {
        super.onDestroy()
        sensorManager.unregisterListener(this)
    }
}

@Composable
private fun CoucouApp() {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("coucou", 0) }
    var host by remember { mutableStateOf(prefs.getString("host", "http://192.168.1.10:8765") ?: "") }
    var token by remember { mutableStateOf(prefs.getString("token", "") ?: "") }
    var profile by remember { mutableStateOf(prefs.getString("profile", "") ?: "") }
    var setup by remember { mutableStateOf(true) }
    var expanded by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf(JSONObject()) }
    var error by remember { mutableStateOf("") }
    var chat by remember { mutableStateOf("") }
    var messages by remember { mutableStateOf(listOf("Coucou" to "Connecte-toi au pont Hermes de ton PC pour commencer.")) }
    var busy by remember { mutableStateOf(false) }
    var wakeWordEnabled by remember { mutableStateOf(prefs.getBoolean("wake_word_enabled", false)) }
    var overlayEnabled by remember { mutableStateOf(prefs.getBoolean("overlay_enabled", false)) }
    var voiceFeedback by remember { mutableStateOf(prefs.getBoolean("voice_feedback", true)) }
    
    // Nouveaux états pour les fonctionnalités mobiles
    var notes by remember { mutableStateOf(listOf<String>()) }
    var newNote by remember { mutableStateOf("") }
    var reminders by remember { mutableStateOf(listOf<Pair<String, String>>()) }
    var newReminder by remember { mutableStateOf("") }
    var newReminderTime by remember { mutableStateOf("") }
    var batteryLevel by remember { mutableStateOf(0) }
    var batteryStatus by remember { mutableStateOf("") }
    var calculatorInput by remember { mutableStateOf("") }
    var calculatorResult by remember { mutableStateOf("") }
    var clipboardText by remember { mutableStateOf("") }
    var showQuickActions by remember { mutableStateOf(false) }
    
    val scope = rememberCoroutineScope()
    val approvals = remember(status) { status.optJSONArray("approvals") ?: JSONArray() }
    val sessions = remember(status) { status.optJSONArray("sessions") ?: JSONArray() }
    val kanban = remember(status) { status.optJSONObject("kanban") ?: JSONObject() }
    
    // Voice recognition launcher
    val voiceLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val spoken = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            if (spoken.isNotBlank()) {
                chat = spoken
                scope.launch {
                    sendChat(spoken, host, token, profile) { 
                        messages = messages + ("Toi" to spoken) + ("Coucou" to it)
                        chat = ""
                    }
                }
            }
        }
    }
    
    // Permission launcher
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted ->
        if (isGranted) {
            Toast.makeText(ctx, "Permission accordée !", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(ctx, "Permission refusée", Toast.LENGTH_SHORT).show()
        }
    }
    
    // Request overlay permission
    fun requestOverlayPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!Settings.canDrawOverlays(ctx)) {
                val intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + ctx.packageName))
                ctx.startActivity(intent)
            }
        }
    }
    
    // Request microphone permission
    fun requestMicrophonePermission() {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                ctx as Activity,
                arrayOf(Manifest.permission.RECORD_AUDIO),
                1001
            )
        }
    }
    
    // Get battery info
    fun updateBatteryInfo() {
        val batteryManager = ctx.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            batteryLevel = batteryManager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        }
        
        val intent = ctx.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        intent?.let {
            val level = it.getIntExtra(BatteryManager.EXTRA_LEVEL, 0)
            val status = it.getIntExtra(BatteryManager.EXTRA_STATUS, BatteryManager.BATTERY_STATUS_UNKNOWN)
            batteryLevel = level
            batteryStatus = when (status) {
                BatteryManager.BATTERY_STATUS_CHARGING -> "En charge"
                BatteryManager.BATTERY_STATUS_FULL -> "Chargé"
                BatteryManager.BATTERY_STATUS_DISCHARGING -> "Décharge"
                else -> "Inconnu"
            }
        }
    }
    
    // Get clipboard text
    fun getClipboardText(): String {
        val clipboard = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        if (clipboard.hasPrimaryClip() && clipboard.primaryClip?.itemCount ?: 0 > 0) {
            return clipboard.primaryClip?.getItemAt(0)?.text?.toString() ?: ""
        }
        return ""
    }
    
    // Calculate expression
    fun calculateExpression(expr: String): String {
        return try {
            val result = ExpressionEvaluator.evaluate(expr)
            result.toString()
        } catch (e: Exception) {
            "Erreur: ${e.message}"
        }
    }
    
    // Add note
    fun addNote(note: String) {
        if (note.isNotBlank()) {
            val timestamp = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
            notes = notes + listOf("$timestamp - $note")
            newNote = ""
        }
    }
    
    // Add reminder
    fun addReminder(text: String, time: String) {
        if (text.isNotBlank() && time.isNotBlank()) {
            reminders = reminders + listOf(Pair(text, time))
            newReminder = ""
            newReminderTime = ""
        }
    }
    
    // Refresh status from server
    suspend fun refresh() {
        try {
            val obj = api(host, token, "GET", "/api/status", null)
            status = obj
            error = ""
            updateBatteryInfo()
            clipboardText = getClipboardText()
        } catch (e: Exception) { 
            error = e.message ?: "Connexion impossible"
        }
    }
    
    // Auto-refresh
    LaunchedEffect(host, token) {
        while (true) {
            if (!setup) refresh()
            delay(2500)
        }
    }
    
    // Initial data load
    LaunchedEffect(Unit) {
        updateBatteryInfo()
        clipboardText = getClipboardText()
    }
    
    // Main UI
    Box(Modifier.fillMaxSize().background(bg)) {
        Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
            Spacer(Modifier.height(12.dp))
            
            // Island retracts to a small capsule when idle; tapping opens the panel.
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                Row(
                    Modifier
                        .width(if (expanded) 360.dp else 112.dp)
                        .height(34.dp)
                        .background(Color(0xFF020204), RoundedCornerShape(24.dp))
                        .clickable { expanded = !expanded }
                        .padding(horizontal = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center
                ) {
                    Box(Modifier.size(7.dp).background(if (error.isEmpty()) mint else danger, RoundedCornerShape(50)))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (expanded) "COUCOU  •  HERMES" else "coucou",
                        color = Color.White,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    if (!expanded && (approvals.length() > 0)) {
                        Spacer(Modifier.width(7.dp))
                        Text(approvals.length().toString(), color = accent, fontSize = 11.sp)
                    }
                }
            }
            
            Spacer(Modifier.height(20.dp))
            
            if (setup) {
                // Setup screen
                Text("Connexion au PC", color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(
                    "L'application Android se connecte au pont Coucou lancé sur le PC. Les agents et Hermes restent sur ton ordinateur.",
                    color = muted
                )
                Spacer(Modifier.height(20.dp))
                OutlinedTextField(
                    host,
                    { host = it },
                    label = { Text("Adresse du PC, ex. http://192.168.1.20:8765") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    token,
                    { token = it },
                    label = { Text("Jeton d'accès") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(Modifier.height(14.dp))
                Button(
                    onClick = {
                        prefs.edit()
                            .putString("host", host)
                            .putString("token", token)
                            .apply()
                        setup = false
                        scope.launch { refresh() }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Connecter") }
                Text(
                    "Conseil : utilise un réseau Wi-Fi de confiance et ne publie jamais le port sur Internet.",
                    color = muted,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 12.dp)
                )
            } else {
                // Main app screen
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.weight(1f)) {
                        Text("Ton île", color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.Bold)
                        Text(
                            if (error.isEmpty()) "Connecté au pont • actualisation automatique" 
                            else "Hors ligne : $error",
                            color = if (error.isEmpty()) mint else danger,
                            fontSize = 12.sp
                        )
                    }
                    TextButton(onClick = { setup = true }) { Text("Réglages") }
                }
                
                Spacer(Modifier.height(14.dp))
                
                // Quick stats
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    MiniTile("Agents", sessions.length().toString(), Modifier.weight(1f))
                    MiniTile("À valider", approvals.length().toString(), Modifier.weight(1f), 
                        if (approvals.length() > 0) warning else accent)
                    MiniTile("Tâches", kanban.optInt("total", 0).toString(), Modifier.weight(1f))
                    MiniTile("Batterie", "${batteryLevel}%", Modifier.weight(1f), 
                        when {
                            batteryLevel < 20 -> danger
                            batteryLevel < 50 -> warning
                            else -> mint
                        })
                }
                
                Spacer(Modifier.height(18.dp))
                
                // Approvals section
                Text("Demandes à valider", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                if (approvals.length() == 0) {
                    Text("Aucune demande en attente.", color = muted, fontSize = 13.sp)
                } else {
                    LazyColumn(Modifier.heightIn(max = 260.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        items((0 until approvals.length()).map { approvals.optJSONObject(it) ?: JSONObject() }) { ap ->
                            Column(
                                Modifier
                                    .fillMaxWidth()
                                    .background(surface, RoundedCornerShape(16.dp))
                                    .padding(13.dp)
                            ) {
                                Text(
                                    "${ap.optString("agent")} • ${ap.optString("tool")}",
                                    color = Color.White,
                                    fontWeight = FontWeight.SemiBold
                                )
                                Text(ap.optString("summary"), color = muted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 7.dp))
                                Text(
                                    "Risque ${ap.optInt("score")}/100  ${ap.optJSONArray("labels")?.join(", ") ?: ""}",
                                    color = if (ap.optInt("score") >= 70) danger else warning,
                                    fontSize = 12.sp
                                )
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 10.dp)) {
                                    Button(
                                        onClick = { 
                                            scope.launch { 
                                                act(host, token, "/api/approval/${ap.optString("id")}/allow")
                                                refresh() 
                                            }
                                        },
                                        modifier = Modifier.weight(1f)
                                    ) { Text("Autoriser") }
                                    OutlinedButton(
                                        onClick = { 
                                            scope.launch { 
                                                act(host, token, "/api/approval/${ap.optString("id")}/deny")
                                                refresh() 
                                            }
                                        },
                                        modifier = Modifier.weight(1f)
                                    ) { Text("Refuser") }
                                }
                            }
                        }
                    }
                }
                
                Spacer(Modifier.height(18.dp))
                
                // Chat section
                Text("Discuter avec tes agents", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(7.dp))
                OutlinedTextField(
                    profile,
                    { profile = it },
                    label = { Text("Profil Hermes (optionnel)") },
                    placeholder = { Text("ex. dev, recherche…") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(Modifier.height(7.dp))
                LazyColumn(
                    Modifier
                        .weight(1f, fill = false)
                        .heightIn(min = 110.dp, max = 230.dp),
                    verticalArrangement = Arrangement.spacedBy(7.dp)
                ) {
                    items(messages.takeLast(30)) { (who, body) ->
                        Column(
                            Modifier
                                .fillMaxWidth()
                                .background(surface, RoundedCornerShape(13.dp))
                                .padding(11.dp)
                        ) {
                            Text(who, color = accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            Text(body, color = Color.White, fontSize = 14.sp)
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    OutlinedTextField(
                        chat,
                        { chat = it },
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("Message à Hermes…") },
                        maxLines = 3
                    )
                    Button(
                        enabled = !busy && chat.isNotBlank(),
                        onClick = {
                            val prompt = chat
                            busy = true
                            messages = messages + ("Toi" to prompt)
                            scope.launch {
                                sendChat(prompt, host, token, profile) { 
                                    messages = messages + ("Coucou" to it)
                                    chat = ""
                                }
                                busy = false
                            }
                        }
                    ) { Text("Envoyer") }
                    IconButton(onClick = {
                        requestMicrophonePermission()
                        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR")
                            putExtra(RecognizerIntent.EXTRA_PROMPT, "Parle à Coucou")
                        }
                        try {
                            voiceLauncher.launch(intent)
                        } catch (_: Exception) {
                            error = "Reconnaissance vocale indisponible"
                        }
                    }) { 
                        Icon(Icons.Default.Mic, contentDescription = "Microphone", tint = accent)
                    }
                }
                
                Spacer(Modifier.height(18.dp))
                
                // NOUVELLES FONCTIONNALITÉS MOBILE
                
                // 1. Notes rapides
                if (showQuickActions) {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = surface)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text("📝 Notes rapides", color = accent, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(8.dp))
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                OutlinedTextField(
                                    newNote,
                                    { newNote = it },
                                    modifier = Modifier.weight(1f),
                                    placeholder = { Text("Écris une note...") },
                                    maxLines = 2
                                )
                                Button(
                                    enabled = newNote.isNotBlank(),
                                    onClick = { addNote(newNote) }
                                ) { Text("Ajouter") }
                            }
                            Spacer(Modifier.height(8.dp))
                            if (notes.isNotEmpty()) {
                                LazyColumn(Modifier.heightIn(max = 100.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    items(notes.takeLast(5)) { note ->
                                        Text(note, color = Color.White, fontSize = 13.sp)
                                    }
                                }
                            }
                        }
                    }
                    
                    Spacer(Modifier.height(8.dp))
                    
                    // 2. Rappels intelligents
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = surface)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text("⏰ Rappels intelligents", color = accent, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(8.dp))
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                OutlinedTextField(
                                    newReminder,
                                    { newReminder = it },
                                    modifier = Modifier.weight(1f),
                                    placeholder = { Text("Quoi ?") }
                                )
                                OutlinedTextField(
                                    newReminderTime,
                                    { newReminderTime = it },
                                    modifier = Modifier.width(100.dp),
                                    placeholder = { Text("Quand ?") }
                                )
                                Button(
                                    enabled = newReminder.isNotBlank() && newReminderTime.isNotBlank(),
                                    onClick = { addReminder(newReminder, newReminderTime) }
                                ) { Text("Ajouter") }
                            }
                            Spacer(Modifier.height(8.dp))
                            if (reminders.isNotEmpty()) {
                                LazyColumn(Modifier.heightIn(max = 80.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    items(reminders.takeLast(3)) { (text, time) ->
                                        Text("⏰ $text à $time", color = Color.White, fontSize = 13.sp)
                                    }
                                }
                            }
                        }
                    }
                    
                    Spacer(Modifier.height(8.dp))
                    
                    // 3. Synchronisation presse-papiers
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = surface)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text("📋 Presse-papiers", color = accent, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(8.dp))
                            if (clipboardText.isNotBlank() && clipboardText.length > 20) {
                                Text("Dernier texte copié: ${clipboardText.take(50)}...", color = muted, fontSize = 12.sp)
                            } else if (clipboardText.isNotBlank()) {
                                Text("Dernier texte copié: $clipboardText", color = muted, fontSize = 12.sp)
                            } else {
                                Text("Aucun texte dans le presse-papiers", color = muted, fontSize = 12.sp)
                            }
                            Spacer(Modifier.height(8.dp))
                            Button(
                                onClick = { 
                                    val clipboard = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                    clipboard.setPrimaryClip(ClipData.newPlainText("Coucou", "Texte copié depuis Coucou"))
                                    Toast.makeText(ctx, "Texte copié !", Toast.LENGTH_SHORT).show()
                                }
                            ) { Text("Copier un texte") }
                        }
                    }
                    
                    Spacer(Modifier.height(8.dp))
                    
                    // 4. Moniteur de batterie
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = surface)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text("🔋 Batterie", color = accent, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(8.dp))
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(16.dp)
                            ) {
                                Column {
                                    Text("Niveau: ${batteryLevel}%", color = Color.White, fontSize = 14.sp)
                                    Text("État: $batteryStatus", color = muted, fontSize = 12.sp)
                                }
                                Box(
                                    modifier = Modifier
                                        .size(40.dp)
                                        .background(
                                            when {
                                                batteryLevel < 20 -> danger
                                                batteryLevel < 50 -> warning
                                                else -> mint
                                            },
                                            RoundedCornerShape(20.dp)
                                        ),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        "${batteryLevel}%",
                                        color = Color.White,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                            Spacer(Modifier.height(8.dp))
                            if (batteryLevel < 20) {
                                Button(
                                    onClick = { 
                                        val intent = Intent(Intent.ACTION_POWER_USAGE_SUMMARY)
                                        ctx.startActivity(intent)
                                    }
                                ) { Text("Économiser la batterie") }
                            }
                        }
                    }
                    
                    Spacer(Modifier.height(8.dp))
                    
                    // 5. Calculatrice rapide
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = surface)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text("🧮 Calculatrice", color = accent, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(8.dp))
                            OutlinedTextField(
                                calculatorInput,
                                { calculatorInput = it },
                                modifier = Modifier.fillMaxWidth(),
                                placeholder = { Text("Ex: 25 + 15 * 2") }
                            )
                            Spacer(Modifier.height(8.dp))
                            if (calculatorResult.isNotBlank()) {
                                Text("= $calculatorResult", color = mint, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                            }
                            Spacer(Modifier.height(8.dp))
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Button(
                                    onClick = { 
                                        calculatorInput += "7"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("7") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "8"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("8") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "9"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("9") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "/"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("/") }
                            }
                            Spacer(Modifier.height(4.dp))
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Button(
                                    onClick = { 
                                        calculatorInput += "4"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("4") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "5"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("5") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "6"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("6") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "*"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("*") }
                            }
                            Spacer(Modifier.height(4.dp))
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Button(
                                    onClick = { 
                                        calculatorInput = ""
                                        calculatorResult = ""
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("C") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "1"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("1") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "2"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("2") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "3"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("3") }
                            }
                            Spacer(Modifier.height(4.dp))
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Button(
                                    onClick = { 
                                        calculatorInput = calculatorInput.dropLast(1)
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Icon(Icons.Default.Backspace, contentDescription = "Backspace") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "0"
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("0") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "."
                                        calculatorResult = calculateExpression(calculatorInput)
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text(".") }
                                Button(
                                    onClick = { 
                                        calculatorInput += "="
                                        calculatorResult = calculateExpression(calculatorInput.dropLast(1))
                                    },
                                    modifier = Modifier.weight(1f)
                                ) { Text("=") }
                            }
                        }
                    }
                }
                
                // Bouton pour afficher/masquer les actions rapides
                Button(
                    onClick = { showQuickActions = !showQuickActions },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (showQuickActions) "Masquer les outils mobile" else "Afficher les outils mobile")
                }
                
                Spacer(Modifier.height(12.dp))
                
                // Paramètres des fonctionnalités mobiles
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 8.dp),
                    colors = CardDefaults.cardColors(containerColor = surface)
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Text("⚙️  Paramètres mobile", color = accent, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(8.dp))
                        
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Checkbox(
                                checked = wakeWordEnabled,
                                onCheckedChange = { 
                                    wakeWordEnabled = it
                                    prefs.edit().putBoolean("wake_word_enabled", it).apply()
                                }
                            )
                            Spacer(Modifier.width(8.dp))
                            Column {
                                Text("Wake Word (Coucou)", color = Color.White, fontSize = 14.sp)
                                Text("Écoute en arrière-plan pour le mot clé", color = muted, fontSize = 11.sp)
                            }
                        }
                        
                        Spacer(Modifier.height(8.dp))
                        
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Checkbox(
                                checked = overlayEnabled,
                                onCheckedChange = { 
                                    overlayEnabled = it
                                    prefs.edit().putBoolean("overlay_enabled", it).apply()
                                    if (it) {
                                        requestOverlayPermission()
                                    }
                                }
                            )
                            Spacer(Modifier.width(8.dp))
                            Column {
                                Text("Encoche flottante", color = Color.White, fontSize = 14.sp)
                                Text("Afficher une encoche flottante au-dessus des apps", color = muted, fontSize = 11.sp)
                            }
                        }
                        
                        Spacer(Modifier.height(8.dp))
                        
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Checkbox(
                                checked = voiceFeedback,
                                onCheckedChange = { 
                                    voiceFeedback = it
                                    prefs.edit().putBoolean("voice_feedback", it).apply()
                                }
                            )
                            Spacer(Modifier.width(8.dp))
                            Column {
                                Text("Retour vocal", color = Color.White, fontSize = 14.sp)
                                Text("Activer les confirmations vocales", color = muted, fontSize = 11.sp)
                            }
                        }
                    }
                }
                
                Spacer(Modifier.height(12.dp))
                
                // Raccourcis smartphone
                Text("Raccourcis smartphone", color = Color.White, fontWeight = FontWeight.Bold)
                Row(horizontalArrangement = Arrangement.spacedBy(7.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(
                        onClick = { scope.launch { act(host, token, "/api/shortcut/focus"); refresh() } },
                        modifier = Modifier.weight(1f)
                    ) { Text("Focus 25 min") }
                    OutlinedButton(
                        onClick = { scope.launch { act(host, token, "/api/shortcut/bonjour"); refresh() } },
                        modifier = Modifier.weight(1f)
                    ) { Text("Brief vocal") }
                    OutlinedButton(
                        onClick = { scope.launch { act(host, token, "/api/shortcut/calm"); refresh() } },
                        modifier = Modifier.weight(1f)
                    ) { Text("Respirer") }
                }
                
                Spacer(Modifier.height(12.dp))
            }
        }
    }
}

@Composable
private fun MiniTile(label: String, value: String, modifier: Modifier = Modifier, color: Color = accent) {
    Column(modifier.background(surface, RoundedCornerShape(15.dp)).padding(12.dp)) {
        Text(label, color = muted, fontSize = 12.sp)
        Text(value, color = color, fontSize = 23.sp, fontWeight = FontWeight.Bold)
    }
}

// Expression evaluator for calculator
object ExpressionEvaluator {
    fun evaluate(expr: String): Double {
        return try {
            val tokens = tokenize(expr)
            val postfix = infixToPostfix(tokens)
            evaluatePostfix(postfix)
        } catch (e: Exception) {
            throw IllegalArgumentException("Expression invalide")
        }
    }
    
    private fun tokenize(expr: String): List<String> {
        val tokens = mutableListOf<String>()
        var i = 0
        while (i < expr.length) {
            when {
                expr[i].isWhitespace() -> i++
                expr[i].isDigit() || expr[i] == '.' -> {
                    val sb = StringBuilder()
                    while (i < expr.length && (expr[i].isDigit() || expr[i] == '.')) {
                        sb.append(expr[i])
                        i++
                    }
                    tokens.add(sb.toString())
                }
                expr[i] in "+-*\\/()" -> {
                    tokens.add(expr[i].toString())
                    i++
                }
                else -> throw IllegalArgumentException("Caractère invalide: ${expr[i]}")
            }
        }
        return tokens
    }
    
    private fun infixToPostfix(tokens: List<String>): List<String> {
        val output = mutableListOf<String>()
        val stack = mutableListOf<String>()
        
        for (token in tokens) {
            when {
                token.toDoubleOrNull() != null -> output.add(token)
                token == "(" -> stack.add(token)
                token == ")" -> {
                    while (stack.isNotEmpty() && stack.last() != "(") {
                        output.add(stack.removeAt(stack.size - 1))
                    }
                    stack.removeAt(stack.size - 1) // Remove "("
                }
                else -> {
                    while (stack.isNotEmpty() && precedence(stack.last()) >= precedence(token)) {
                        output.add(stack.removeAt(stack.size - 1))
                    }
                    stack.add(token)
                }
            }
        }
        
        while (stack.isNotEmpty()) {
            output.add(stack.removeAt(stack.size - 1))
        }
        
        return output
    }
    
    private fun precedence(op: String): Int {
        return when (op) {
            "+", "-" -> 1
            "*", "/" -> 2
            else -> 0
        }
    }
    
    private fun evaluatePostfix(tokens: List<String>): Double {
        val stack = mutableListOf<Double>()
        
        for (token in tokens) {
            when {
                token.toDoubleOrNull() != null -> stack.add(token.toDouble())
                else -> {
                    val b = stack.removeAt(stack.size - 1)
                    val a = stack.removeAt(stack.size - 1)
                    val result = when (token) {
                        "+" -> a + b
                        "-" -> a - b
                        "*" -> a * b
                        "/" -> a / b
                        else -> throw IllegalArgumentException("Opérateur invalide: $token")
                    }
                    stack.add(result)
                }
            }
        }
        
        return stack[0]
    }
}

private suspend fun sendChat(text: String, host: String, token: String, profile: String, result: (String) -> Unit) {
    try {
        val body = JSONObject().put("text", text).put("profile", profile)
        val out = withContext(Dispatchers.IO) { api(host, token, "POST", "/api/chat", body) }
        result(out.optString("reply", "Message transmis à Hermes."))
    } catch (e: Exception) { 
        result("Erreur : ${e.message ?: "connexion impossible"}") 
    }
}

private suspend fun act(host: String, token: String, path: String) {
    withContext(Dispatchers.IO) { api(host, token, "POST", path, JSONObject()) }
}

private suspend fun api(host: String, token: String, method: String, path: String, body: JSONObject?): JSONObject = withContext(Dispatchers.IO) {
    val conn = URL(host.trimEnd('/') + path).openConnection() as HttpURLConnection
    conn.requestMethod = method
    conn.connectTimeout = Constants.CONNECTION_TIMEOUT
    conn.readTimeout = Constants.READ_TIMEOUT
    conn.setRequestProperty("Authorization", "Bearer $token")
    conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
    if (body != null) {
        conn.doOutput = true
        conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
    }
    try {
        val stream = if (conn.responseCode in 200..299) conn.inputStream else conn.errorStream
        val raw = stream.bufferedReader().use { it.readText() }
        if (conn.responseCode !in 200..299) throw IllegalStateException("HTTP ${conn.responseCode}: $raw")
        JSONObject(raw)
    } finally { 
        conn.disconnect() 
    }
}
