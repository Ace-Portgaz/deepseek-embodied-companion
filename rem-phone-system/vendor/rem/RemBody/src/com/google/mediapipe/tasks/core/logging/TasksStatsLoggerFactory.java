package com.google.mediapipe.tasks.core.logging;

import android.content.Context;

/** Offline integration: use the no-op logger already distributed by MediaPipe. */
public final class TasksStatsLoggerFactory {
    private TasksStatsLoggerFactory() {}
    public static TasksStatsLogger create(Context context, String task, String mode) {
        return TasksStatsDummyLogger.create(context, task, mode);
    }
}
