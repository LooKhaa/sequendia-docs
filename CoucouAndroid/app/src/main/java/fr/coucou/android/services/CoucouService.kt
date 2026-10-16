package fr.coucou.android.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Binder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.SpeechRecognizer
import android.util.Log
import androidx.core.app.NotificationCompat
import fr.coucou.android.Constants
import fr.coucou.android.MainActivity
import fr.coucou.android.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

class CoucouService : Service() {
    private val binder = LocalBinder()
    private lateinit var speechRecognizer: SpeechRecognizer
    private val isListening = AtomicBoolean(false)
    private val handler = Handler(Looper.getMainLooper())
    private var notification: Notification? = null
    private lateinit var prefs: SharedPreferences
    
    inner class LocalBinder : Binder() {
        fun getService(): CoucouService = this@CoucouService
    }

    override fun onBind(intent: Intent?): IBinder {
        return binder
    }

    override fun onCreate() {
        super.onCreate()
        prefs = getSharedPreferences("coucou", Context.MODE_PRIVATE)
        createNotificationChannel()
        startForeground()
        setupSpeechRecognizer()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                Constants.OVERLAY_CHANNEL_ID,
                "Coucou Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Service Coucou en cours d'exécution"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun startForeground() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent, 
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        notification = NotificationCompat.Builder(this, Constants.OVERLAY_CHANNEL_ID)
            .setContentTitle("Coucou")
            .setContentText("Écoute en arrière-plan")
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
        
        startForeground(Constants.OVERLAY_NOTIFICATION_ID, notification)
    }

    private fun setupSpeechRecognizer() {
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : android.speech.RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}
                override fun onError(error: Int) {
                    Log.e("CoucouService", "Speech recognition error: $error")
                    if (isListening.get()) {
                        handler.postDelayed({ startListening() }, 1000)
                    }
                }
                
                override fun onResults(results: Bundle?) {
                    results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let { text ->
                        if (text.lowercase().contains(Constants.WAKE_WORD)) {
                            val intent = Intent(this@CoucouService, MainActivity::class.java).apply {
                                flags = Intent.FLAG_ACTIVITY_NEW_TASK
                                putExtra("wake_word_triggered", true)
                            }
                            startActivity(intent)
                        }
                    }
                    if (isListening.get()) {
                        handler.postDelayed({ startListening() }, 100)
                    }
                }
                
                override fun onPartialResults(partialResults: Bundle?) {}
                override fun onEvent(eventType: Int, params: Bundle?) {}
            })
        }
    }

    fun startListening() {
        if (isListening.compareAndSet(false, true)) {
            try {
                speechRecognizer.startListening(Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL, 
                        android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE, "fr-FR")
                    putExtra(android.speech.RecognizerIntent.EXTRA_CALLING_PACKAGE, packageName)
                    putExtra(android.speech.RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                    putExtra(android.speech.RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                })
            } catch (e: Exception) {
                Log.e("CoucouService", "Failed to start listening", e)
                isListening.set(false)
            }
        }
    }

    fun stopListening() {
        if (isListening.compareAndSet(true, false)) {
            try {
                speechRecognizer.stopListening()
            } catch (e: Exception) {
                Log.e("CoucouService", "Failed to stop listening", e)
            }
        }
    }

    fun isWakeWordEnabled(): Boolean {
        return prefs.getBoolean(Constants.PREF_WAKE_WORD_ENABLED, false)
    }

    override fun onDestroy() {
        super.onDestroy()
        stopListening()
        speechRecognizer.destroy()
    }
}
