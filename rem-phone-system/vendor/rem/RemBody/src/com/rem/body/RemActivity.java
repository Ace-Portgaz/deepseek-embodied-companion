package com.rem.body;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.hardware.camera2.CameraCharacteristics;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.Gravity;
import android.view.TextureView;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import com.rem.body.character.BustRemView;
import com.rem.body.vision.ObservationEngine;
import com.rem.body.vision.ObservationPolicy;
import java.io.FileDescriptor;
import java.io.PrintWriter;
import com.rem.body.voice.CloudVoice;
import org.json.JSONArray;
import org.json.JSONObject;

/** Dedicated system HOME. Camera observation is foreground-only and explicitly pausable. */
public final class RemActivity extends Activity {
    private final Handler main=new Handler(Looper.getMainLooper());
    private final BodyState state=new BodyState();
    private TextView status,caption;
    private Button toggle;
    private FrameLayout stage;
    private BustRemView character;
    private AudioProbe audio;
    private CameraPreview camera;
    private ObservationEngine vision;
    private AlertDialog maintenance;
    private boolean resumed,observationWanted,modelFailed,maintenanceOpen;
    private String lastVision="not_started",lastEvent="none";
    private long captionUntil;
    private int eventCount;
    private CloudVoice voice;private TextView voiceStatus;private Button talk;
    private final java.util.ArrayList<JSONObject> recentEvents=new java.util.ArrayList<>();
    private final java.util.EnumMap<ObservationPolicy.Event,Integer> eventCounts=new java.util.EnumMap<>(ObservationPolicy.Event.class);

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        observationWanted=getPreferences(0).getBoolean("observation_enabled",true);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);root.setPadding(dp(10),dp(20),dp(10),dp(22));
        root.setBackgroundColor(Color.rgb(12,22,34));
        TextView title=new TextView(this);title.setText("レム");title.setTextSize(23);title.setTextColor(Color.WHITE);
        title.setPadding(0,dp(10),0,dp(6));title.setContentDescription("雷姆，长按打开维护入口");
        title.setOnLongClickListener(v->{showMaintenance();return true;});root.addView(title);
        stage=new FrameLayout(this);root.addView(stage,new LinearLayout.LayoutParams(-1,0,1));
        caption=new TextView(this);caption.setTextColor(Color.WHITE);caption.setTextSize(17);caption.setGravity(Gravity.CENTER);caption.setMinHeight(dp(36));
        root.addView(caption,new LinearLayout.LayoutParams(-1,-2));
        status=new TextView(this);status.setTextColor(Color.rgb(181,202,220));status.setTextSize(12);status.setGravity(Gravity.CENTER);status.setMinHeight(dp(32));status.setText("正在准备雷姆…");
        root.addView(status,new LinearLayout.LayoutParams(-1,-2));
        toggle=new Button(this);toggle.setOnClickListener(v->{
            if(state.mode()==BodyState.Mode.MICROPHONE_TEST||state.mode()==BodyState.Mode.CAMERA_PREVIEW){stopHardware();showModel();maybeObserve();}
            else {observationWanted=!observationWanted;getPreferences(0).edit().putBoolean("observation_enabled",observationWanted).apply();
                if(observationWanted)maybeObserve();else{stopHardware();status.setText("观察已暂停 · 摄像头已关闭");caption.setText("ここにいますよ。");}}
            updateButton();
        });root.addView(toggle,new LinearLayout.LayoutParams(-1,-2));
        voiceStatus=new TextView(this);voiceStatus.setTextColor(Color.WHITE);voiceStatus.setTextSize(12);voiceStatus.setGravity(Gravity.CENTER);
        voiceStatus.setText("点击说话 · DeepSeek / 日语语音");root.addView(voiceStatus,new LinearLayout.LayoutParams(-1,-2));
        talk=new Button(this);talk.setText("开始说话");root.addView(talk,new LinearLayout.LayoutParams(-1,-2));
        voice=new CloudVoice(this,main,new CloudVoice.Listener(){
            @Override public void state(String text){voiceStatus.setText(text);talk.setText(voice.recording()?"结束说话":voice.busy()?"取消本轮":"开始说话");}
            @Override public void reply(String heard,String reply){captionUntil=SystemClock.elapsedRealtime()+60000;caption.setText(reply);voiceStatus.setText("你："+heard);talk.setText("停止播放");}
            @Override public void speech(double level,boolean playing){if(character!=null)character.setSpeech(level,playing);if(!playing&&!voice.busy())talk.setText("开始说话");}
            @Override public void settings(String value){if(value==null){voiceStatus.setText("人格设置已保存，下轮对话生效");return;}showPersonality(value);}
        });
        talk.setOnClickListener(v->{
            if(!voice.configured()){voiceStatus.setText("手机还未登记到云端");return;}
            if(voice.recording()){voice.finish();talk.setText("正在处理…");return;}
            if(voice.busy()){voice.cancel();voiceStatus.setText("本轮已停止");talk.setText("开始说话");return;}
            if(!permission(Manifest.permission.RECORD_AUDIO,4))return;
            voice.start(this::recentVisionEvents);
        });
        character=new BustRemView(this);character.setMotionEnabled(false);
        character.setListener(new BustRemView.Listener(){
            @Override public void ready(){status.setText("雷姆已就绪");maybeObserve();}
            @Override public void failed(String message){modelFailed=true;stopHardware();status.setText("形象加载失败 · 长按标题进入维护");android.util.Log.e("RemCharacter",message);}
        });
        showModel();updateButton();setContentView(root);
    }
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private JSONArray recentVisionEvents(){
        JSONArray events=new JSONArray();long now=SystemClock.elapsedRealtime();
        for(JSONObject event:recentEvents)try{long age=now-event.getLong("time");if(age<=15000){JSONObject item=new JSONObject();item.put("event",event.getString("event"));item.put("age_ms",age);events.put(item);}}catch(Exception ignored){}
        return events;
    }
    private void showModel(){
        if(character==null)return;
        if(character.getParent()==stage&&stage.getChildCount()==1)return;
        stage.removeAllViews();stage.addView(character,new FrameLayout.LayoutParams(-1,-1));
        if(resumed)character.resumeCharacter();
    }
    private void immersive(){getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY|View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_STABLE);}
    @Override public void onWindowFocusChanged(boolean focus){super.onWindowFocusChanged(focus);if(focus)immersive();}
    @Override protected void onResume(){super.onResume();resumed=true;state.resume();immersive();if(character!=null)character.resumeCharacter();maybeObserve();}
    @Override protected void onPause(){resumed=false;if(voice!=null){voice.cancel();voiceStatus.setText("点击说话 · DeepSeek / 日语语音");}state.pause();stopHardware();if(maintenance!=null)maintenance.dismiss();if(character!=null)character.pauseCharacter();super.onPause();}
    @Override protected void onDestroy(){if(voice!=null)voice.close();stopHardware();if(character!=null){stage.removeAllViews();character.releaseCharacter();}super.onDestroy();}
    @Override public void onBackPressed(){if(voice!=null)voice.cancel();observationWanted=false;getPreferences(0).edit().putBoolean("observation_enabled",false).apply();stopHardware();showModel();status.setText("观察已暂停 · 摄像头已关闭");updateButton();}

    private void updateButton(){if(toggle!=null)toggle.setText(state.mode()==BodyState.Mode.MICROPHONE_TEST||state.mode()==BodyState.Mode.CAMERA_PREVIEW?"停止检查，返回雷姆":observationWanted?"暂停观察":"开启观察");}
    private void stopHardware(){
        state.stop();
        if(vision!=null){vision.close();lastVision=vision.diagnostics();vision=null;}
        if(audio!=null){audio.close();audio=null;}
        if(camera!=null){camera.close();camera=null;}
        if(character!=null&&character.isCharacterReady())character.setVisualTarget(0,0,false);
        updateButton();
    }
    private void maybeObserve(){
        if(!resumed||!observationWanted||maintenanceOpen||modelFailed||character==null||!character.isCharacterReady()||state.mode()!=BodyState.Mode.IDLE)return;
        if(!permission(Manifest.permission.CAMERA,3))return;
        if(!state.begin(BodyState.Mode.OBSERVATION,true))return;
        final long generation=state.generation();showModel();status.setText("正在开启前置观察…");
        vision=new ObservationEngine(this,main,new ObservationEngine.Listener(){
            @Override public void ready(){if(state.current(generation))status.setText("前置观察中 · 画面仅在本机处理");}
            @Override public void result(ObservationPolicy.Result result){
                if(!state.current(generation))return;
                character.setVisualTarget(result.x,result.y,true);
                if(SystemClock.elapsedRealtime()>captionUntil){caption.setText(result.present?"ちゃんと、見ていますよ。":"ここで待っていますね。");status.setText(result.present?"前置观察中 · 已看到人脸":"前置观察中 · 等待你进入视野");}
                if(!result.events.isEmpty())respond(result.events.get(result.events.size()-1));
            }
            @Override public void events(java.util.List<ObservationPolicy.Event> events){if(state.current(generation)&&!events.isEmpty())respond(events.get(events.size()-1));}
            @Override public void failed(String code){if(!state.current(generation))return;stopHardware();lastVision=code;status.setText("观察暂时不可用："+code+" · 可暂停后重试");}
        });vision.start();updateButton();
    }
    private void respond(ObservationPolicy.Event event){
        try{JSONObject item=new JSONObject();item.put("event",event.name());item.put("time",SystemClock.elapsedRealtime());recentEvents.add(item);while(recentEvents.size()>8)recentEvents.remove(0);}catch(Exception ignored){}
        if(voice!=null&&voice.busy())return;
        lastEvent=event.name();eventCount++;character.respondToObservation(event.name());captionUntil=SystemClock.elapsedRealtime()+2300;
        Integer count=eventCounts.get(event);eventCounts.put(event,count==null?1:count+1);
        String line,label;
        switch(event){
            case ARRIVED:line="あ、来てくれたんですね。";label="进入视野";break;
            case LEFT:line="ここで待っていますね。";label="离开视野";break;
            case NOD:line="うん、うん。";label="点头";break;
            case SHAKE:line="そうじゃないんですね。";label="摇头";break;
            case WAVE:line="はい、見えていますよ！";label="挥手";break;
            case APPROACH:line="近くに来てくれたんですね。";label="靠近";break;
            default:line="ここからでも、見えますよ。";label="退远";
        }
        caption.setText(line);status.setText("前置观察中 · "+label+" · 本地动作回应");
    }
    private boolean permission(String value,int request){
        if(checkSelfPermission(value)==PackageManager.PERMISSION_GRANTED)return true;
        requestPermissions(new String[]{value},request);status.setText(request==3?"请允许摄像头权限以开启观察":"授权后请再次选择硬件检查");return false;
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] grants){super.onRequestPermissionsResult(request,permissions,grants);if(request==3&&grants.length>0&&grants[0]==PackageManager.PERMISSION_GRANTED)maybeObserve();}
    private void showMaintenance(){
        if(voice!=null)voice.cancel();
        maintenanceOpen=true;stopHardware();showModel();status.setText("维护中 · 观察已暂停");
        maintenance=new AlertDialog.Builder(this).setTitle("维护")
            .setItems(new String[]{"Wi-Fi 设置","音量设置","录音并回放 3 秒（不上传）","打开后置摄像头（不上传）","打开前置摄像头（镜像，不上传）","观察状态","关闭硬件检查","性格与说话习惯（云端）"},(d,which)->{
                switch(which){case 0:openSettings(Settings.ACTION_WIFI_SETTINGS);break;case 1:openSettings(Settings.ACTION_SOUND_SETTINGS);break;
                    case 2:probeAudio();break;case 3:previewCamera(CameraCharacteristics.LENS_FACING_BACK);break;case 4:previewCamera(CameraCharacteristics.LENS_FACING_FRONT);break;
                    case 5:status.setText("最近动作："+lastEvent+"；本地回应 "+eventCount+" 次\n"+(voice.configured()?"云端已登记 · 点击说话":"手机尚未登记到云端"));break;
                    case 7:voice.personality(null);break;
                    default:stopHardware();showModel();}
            }).setNegativeButton("返回雷姆",(d,w)->main.postDelayed(this::maybeObserve,400)).create();
        maintenance.setOnDismissListener(d->{maintenanceOpen=false;updateButton();main.postDelayed(this::maybeObserve,400);});maintenance.show();
    }
    private void showPersonality(String value){
        maintenanceOpen=true;stopHardware();
        android.widget.EditText input=new android.widget.EditText(this);input.setText(value);input.setMinLines(4);input.setHint("例如：温柔但有主见，称呼我为……，回复更简短");
        input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(2000)});
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("性格与说话习惯").setMessage("保存到自己的云端，下轮对话生效；留空恢复基础人设，不清除记忆。").setView(input)
            .setPositiveButton("保存",(d,w)->voice.personality(input.getText().toString())).setNegativeButton("取消",null).create();
        dialog.setOnDismissListener(d->{maintenanceOpen=false;main.postDelayed(this::maybeObserve,400);});dialog.show();
    }
    private void openSettings(String action){try{startActivity(new Intent(action));}catch(RuntimeException e){status.setText("系统维护入口不可用");}}
    private void probeAudio(){
        if(!permission(Manifest.permission.RECORD_AUDIO,1)||!state.begin(BodyState.Mode.MICROPHONE_TEST,true))return;
        long generation=state.generation();audio=new AudioProbe(main);updateButton();
        audio.start((message,finished)->{if(!state.current(generation))return;status.setText(message);if(finished){state.stop();audio.close();audio=null;updateButton();}});
    }
    private void previewCamera(int facing){
        if(!permission(Manifest.permission.CAMERA,2)||!state.begin(BodyState.Mode.CAMERA_PREVIEW,true))return;
        long generation=state.generation();String name=facing==CameraCharacteristics.LENS_FACING_FRONT?"前置":"后置";
        character.pauseCharacter();TextureView texture=new TextureView(this);texture.setContentDescription(name+"摄像头实时预览");
        stage.removeAllViews();stage.addView(texture,new FrameLayout.LayoutParams(-1,-1));status.setText(name+"摄像头预览 · 仅本机显示，未上传");updateButton();
        camera=new CameraPreview(this,texture,main,facing,()->{if(!state.current(generation))return;stopHardware();showModel();status.setText(name+"摄像头打开失败");});
    }
    @Override public void dump(String prefix,FileDescriptor fd,PrintWriter out,String[] args){
        super.dump(prefix,fd,out,args);out.println(prefix+"RemVision mode="+state.mode()+" enabled="+observationWanted+" foreground="+resumed+" modelReady="+(character!=null&&character.isCharacterReady())+" modelFailed="+modelFailed);
        out.println(prefix+(vision==null?lastVision:vision.diagnostics()));out.println(prefix+"eventCount="+eventCount+" lastEvent="+lastEvent);
        out.println(prefix+"eventCounts="+eventCounts);
        out.println(prefix+"RemVoice configured="+(voice!=null&&voice.configured())+" busy="+(voice!=null&&voice.busy())+" recording="+(voice!=null&&voice.recording()));
    }
}

