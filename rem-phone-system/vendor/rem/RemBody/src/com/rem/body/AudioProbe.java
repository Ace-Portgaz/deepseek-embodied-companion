package com.rem.body;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.os.Handler;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Three-second local microphone/speaker check. Audio never leaves RAM. */
public final class AudioProbe {
    public interface Listener { void update(String message, boolean finished); }
    private static final int RATE = 16000;
    private final Handler main;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private volatile boolean cancelled;
    private volatile AudioRecord input;
    private volatile AudioTrack output;

    public AudioProbe(Handler main) { this.main = main; }

    public void start(Listener listener) {
        worker.execute(() -> {
            short[] samples = new short[RATE * 3];
            AudioRecord recorder = null;
            AudioTrack player = null;
            String result = "本机录音回放完成";
            try {
                if (cancelled) return;
                int min = AudioRecord.getMinBufferSize(RATE,
                        AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
                if (min <= 0) throw new IllegalStateException();
                recorder = new AudioRecord(MediaRecorder.AudioSource.MIC, RATE,
                        AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                        Math.max(min, 4096));
                input = recorder;
                if (cancelled) return;
                if (recorder.getState() != AudioRecord.STATE_INITIALIZED) throw new IllegalStateException();
                report(listener, "正在录音 3 秒，仅用于本机回放", false);
                recorder.startRecording();
                int count = 0;
                while (!cancelled && count < samples.length) {
                    int n = recorder.read(samples, count, Math.min(1024, samples.length - count));
                    if (n <= 0) throw new IllegalStateException();
                    count += n;
                }
                recorder.stop();
                if (cancelled || count == 0) return;
                report(listener, "正在回放，麦克风已停止", false);
                player = new AudioTrack.Builder()
                        .setAudioAttributes(new AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_MEDIA)
                                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                        .setAudioFormat(new AudioFormat.Builder().setSampleRate(RATE)
                                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                                .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                        .setBufferSizeInBytes(count * 2).setTransferMode(AudioTrack.MODE_STATIC).build();
                output = player;
                if (cancelled) return;
                if (player.write(samples, 0, count) != count) throw new IllegalStateException();
                player.play();
                long deadline = System.nanoTime() + 5_000_000_000L;
                while (!cancelled && player.getPlaybackHeadPosition() < count) {
                    if (System.nanoTime() > deadline) throw new IllegalStateException();
                    Thread.sleep(30);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (RuntimeException e) {
                result = "音频检查未完成，请检查麦克风权限和音量";
            } finally {
                input = null;
                output = null;
                if (recorder != null) recorder.release();
                if (player != null) player.release();
                Arrays.fill(samples, (short) 0);
                report(listener, result, true);
            }
        });
    }

    private void report(Listener listener, String text, boolean finished) {
        main.post(() -> { if (!cancelled) listener.update(text, finished); });
    }

    public void close() {
        cancelled = true;
        // Interrupt blocking reads promptly; release happens only on the owning worker.
        try { AudioRecord r = input; if (r != null) r.stop(); } catch (RuntimeException ignored) { }
        try { AudioTrack p = output; if (p != null) p.pause(); } catch (RuntimeException ignored) { }
        worker.shutdownNow();
    }
}

