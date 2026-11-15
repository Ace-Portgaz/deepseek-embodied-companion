"""Apply reviewed bridge changes once; preserve original import receipt and archive."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'vendor/rem/RemBody'


def replace(path, before, after):
    text = path.read_text(encoding='utf-8')
    if after in text:
        return
    if text.count(before) != 1:
        raise ValueError('Integration anchor differs: ' + str(path))
    path.write_text(text.replace(before, after), encoding='utf-8')


def main():
    view = ROOT / 'src/com/rem/body/character/BustRemView.java'
    replace(view, '    /** Enabled by default; starts only while ready, resumed, attached and visible. */', '''    /** Structured local geometry only; the web renderer never receives camera frames. */
    public void setVisualTarget(double x,double y,boolean active){mainThread();if(!Double.isFinite(x)||!Double.isFinite(y))throw new IllegalArgumentException("Visual target");if(ready)js("RemModel.setVisualTarget("+x+","+y+","+active+")");}
    public void respondToObservation(String event){mainThread();if(!event.matches("ARRIVED|LEFT|NOD|SHAKE|WAVE|APPROACH|RETREAT"))throw new IllegalArgumentException("Observation event");if(ready)js("RemModel.respondToObservation("+JSONObject.quote(event)+")");}
    /** Enabled by default; starts only while ready, resumed, attached and visible. */''')
    replace(view, 'ready=false;removeJavascriptInterface', 'ready=false;removeJavascriptInterface')
    js = ROOT / 'assets/rem-bust-v4/preview/bust-view.js'
    replace(js, "import {createViewer} from './runtime.js';", "import {createViewer} from './runtime.js';\nimport {createVisualFollow} from './visual-follow.js';")
    replace(js, ' const motion=createDeviceMotion();', ' const visual=createVisualFollow();\n const motion=createDeviceMotion();')
    replace(js, 'viewer.setCaptureParameters(applyDeviceMotion(frame,motionPose,inventory.parameters))', 'viewer.setCaptureParameters(visual.apply(applyDeviceMotion(frame,motionPose,inventory.parameters),inventory.parameters))')
    replace(js, 'function loop(now){const dt=', 'function loop(now){if(now-last<1000/30){if(!disposed)raf=requestAnimationFrame(loop);return;}const dt=')
    replace(js, 'elapsed+=dt;motionPose=motion.step(dt);', 'elapsed+=dt;visual.step(dt,now);motionPose=motion.step(dt);')
    replace(js, '  setMotionEnabled(value,source=', '''  setVisualTarget(x,y,active){visual.target(x,y,active);},
  respondToObservation(event){visual.respond(event);const values=event==='LEFT'?{CURIOUS:.25}:event==='SHAKE'?{CURIOUS:.5}:event==='APPROACH'?{SHY:.35,AFFECTION:.35}:{JOY:.55,AFFECTION:.3};reactions.push({values,attack:.2,hold:.8,release:1.2,start:elapsed});manual=null;},
  setMotionEnabled(value,source=''')
    replace(js, 'if(paused){voice=0;', 'if(paused){visual.reset();voice=0;')
    replace(js, 'motion:motion.state(),parameters:', 'motion:motion.state(),visual:visual.state(),parameters:')
    html = ROOT / 'assets/rem-bust-v4/preview/render.html'
    replace(html, "createBustRenderer(document.querySelector('#portrait'))", "createBustRenderer(document.querySelector('#portrait'),{onError:e=>window.RemHost?.failed(String(e?.message||e))})")
    runtime = ROOT / 'assets/rem-bust-v4/preview/runtime.js'
    replace(runtime, 'app.ticker.maxFPS = 60', 'app.ticker.maxFPS = 30')
    print('Integrated local visual target, bounded eye/head control and event reactions.')


if __name__ == '__main__':
    main()
