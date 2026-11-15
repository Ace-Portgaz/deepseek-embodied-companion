package com.rem.body;

/** Sensor ownership for the initial hardware bring-up; all calls on the UI thread. */
public final class BodyState {
    public enum Mode { IDLE, MICROPHONE_TEST, CAMERA_PREVIEW, OBSERVATION }
    private boolean foreground;
    private Mode mode = Mode.IDLE;
    private long generation;

    public void resume() { foreground = true; }
    public void pause() { foreground = false; stop(); }
    public Mode mode() { return mode; }
    public long generation() { return generation; }
    public boolean current(long value) { return foreground && value == generation; }

    public boolean begin(Mode requested, boolean permissionGranted) {
        if (!foreground || !permissionGranted || requested == Mode.IDLE || mode != Mode.IDLE) {
            return false;
        }
        generation++;
        mode = requested;
        return true;
    }

    public void stop() { generation++; mode = Mode.IDLE; }
}

