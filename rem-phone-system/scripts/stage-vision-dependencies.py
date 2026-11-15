"""Create reproducible offline MediaPipe imports, preserving downloaded originals."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/vision-dependencies'
APP = ROOT / 'vendor/rem/RemBody'
REMOVED = {'TasksStatsLoggerFactory.class', 'TasksStatsProtoLogger.class',
           'LoggingClient.class', 'RemoteLoggingClient.class'}


def main():
    manifest = json.loads((SOURCE / 'download-manifest.json').read_text())
    for row in manifest['files']:
        if hashlib.sha256((SOURCE / row['name']).read_bytes()).hexdigest() != row['sha256']:
            raise SystemExit('Download changed: ' + row['name'])
    libs = APP / 'libs'
    libs.mkdir(exist_ok=True)
    removed = []
    with zipfile.ZipFile(SOURCE / 'tasks-core.aar') as aar:
        assert aar.read('classes.jar') == (SOURCE / 'tasks-core-classes.jar').read_bytes()
    with zipfile.ZipFile(SOURCE / 'tasks-core-classes.jar') as original, \
            zipfile.ZipFile(libs / 'tasks-core-offline.jar', 'w', zipfile.ZIP_DEFLATED) as offline:
        for name in original.namelist():
            if name.startswith('com/google/mediapipe/tasks/core/logging/') and name.rsplit('/', 1)[-1] in REMOVED:
                removed.append(name)
            else:
                offline.writestr(name, original.read(name))
    assert len(removed) == len(REMOVED)
    jars = ['tasks-vision-classes', 'guava', 'failureaccess', 'protobuf-javalite',
            'flogger', 'flogger-system-backend', 'androidx-annotation']
    for name in jars:
        shutil.copyfile(SOURCE / (name + '.jar'), libs / (name + '.jar'))
    native = libs / 'arm64-v8a'
    native.mkdir(exist_ok=True)
    with zipfile.ZipFile(SOURCE / 'tasks-core.aar') as aar:
        (native / 'libmediapipe_tasks_jni.so').write_bytes(aar.read('jni/arm64-v8a/libmediapipe_tasks_jni.so'))
    assets = APP / 'assets/vision'
    assets.mkdir(exist_ok=True)
    for name in ('face_landmarker.task', 'gesture_recognizer.task'):
        shutil.copyfile(SOURCE / name, assets / name)
    shutil.copyfile(SOURCE / 'MEDIAPIPE-LICENSE.txt', assets / 'MEDIAPIPE-LICENSE.txt')
    (assets / 'DEPENDENCIES.txt').write_text(
        'MediaPipe Tasks 0.10.35, Apache-2.0. https://github.com/google-ai-edge/mediapipe\n'
        'Face/gesture models: official mediapipe-models bucket, versions pinned to float16/1.\n'
        'Offline modification: telemetry factory replaced with bundled TasksStatsDummyLogger;\n'
        'remote/proto logging classes excluded. Native inference and models unchanged.\n'
        'Guava 27.0.1-android, failureaccess 1.0.1, Flogger 0.6, AndroidX annotations 1.1.0: Apache-2.0.\n'
        'Protobuf Java Lite 4.26.1: BSD-3-Clause (see libs META-INF/LICENSE).\n', encoding='utf-8')
    bp = '''android_app {
    name: "RemBody",
    srcs: ["src/**/*.java"],
    manifest: "AndroidManifest.xml",
    asset_dirs: ["assets"],
    sdk_version: "current",
    min_sdk_version: "29",
    target_sdk_version: "30",
    compile_multilib: "64",
    static_libs: ["rem-vision-java"],
    jni_libs: ["librem_mediapipe_tasks_jni"],
    use_embedded_native_libs: true,
    optimize: { enabled: false },
}

java_import {
    name: "rem-vision-java",
    jars: ["libs/*.jar"],
    sdk_version: "current",
}

cc_prebuilt_library_shared {
    name: "librem_mediapipe_tasks_jni",
    stem: "libmediapipe_tasks_jni",
    arch: { arm64: { srcs: ["libs/arm64-v8a/libmediapipe_tasks_jni.so"] } },
    compile_multilib: "64",
    sdk_version: "24",
    stl: "none",
    strip: { none: true },
    shared_libs: ["libdl", "libjnigraphics", "libEGL", "libGLESv2", "libm", "libz", "liblog", "libandroid", "libc"],
}
'''
    (APP / 'Android.bp').write_text(bp, encoding='utf-8')
    receipt = {'version': '0.10.35', 'removed_telemetry_classes': removed,
               'factory_replacement': 'src/com/google/mediapipe/tasks/core/logging/TasksStatsLoggerFactory.java',
               'files': {str(p.relative_to(APP)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(libs.rglob('*')) if p.is_file()}}
    (ROOT / 'evidence/vision-dependency-stage.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('Staged offline Java imports, original arm64 JNI and two local models.')


if __name__ == '__main__':
    main()
