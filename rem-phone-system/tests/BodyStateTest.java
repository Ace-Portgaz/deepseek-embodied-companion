import com.rem.body.BodyState;

public final class BodyStateTest {
    private static void check(boolean ok, String message) { if (!ok) throw new AssertionError(message); }
    public static void main(String[] args) {
        BodyState s = new BodyState();
        check(!s.begin(BodyState.Mode.CAMERA_PREVIEW, true), "background capture rejected");
        s.resume();
        check(!s.begin(BodyState.Mode.MICROPHONE_TEST, false), "permission denial respected");
        check(s.begin(BodyState.Mode.MICROPHONE_TEST, true), "explicit capture accepted");
        long old = s.generation();
        check(!s.begin(BodyState.Mode.CAMERA_PREVIEW, true), "exclusive sensor check");
        s.pause();
        check(s.mode() == BodyState.Mode.IDLE, "background cancels capture");
        check(!s.current(old), "late worker callback rejected");
        s.resume();
        check(s.begin(BodyState.Mode.CAMERA_PREVIEW, true), "foreground retry allowed");
        check(!s.current(old), "previous session cannot alter new session");
        long current = s.generation();
        s.stop();
        check(!s.current(current), "manual stop invalidates queued callbacks");
        System.out.println("PASS: 9 sensor lifecycle assertions");
    }
}

