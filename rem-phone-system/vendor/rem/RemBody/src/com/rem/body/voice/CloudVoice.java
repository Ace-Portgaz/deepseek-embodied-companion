package com.rem.body.voice;

import android.content.Context;
import android.media.*;
import android.os.Handler;
import android.os.SystemClock;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;
import javax.net.ssl.HttpsURLConnection;
import java.net.URL;
import java.io.*;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import com.rem.body.character.TouchPolicy;

/** Explicit short microphone turns. TLS-verified requests; provider keys never live on the phone. */
public final class CloudVoice {
    public interface Listener {void state(String state);void reply(String heard,String reply);void speech(double rms,boolean playing);void settings(String value);}
    private final Context context;private final Handler main;private final Listener listener;
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private volatile boolean recording,busy;private volatile long generation;
    private volatile AudioRecord recorder;private volatile AudioTrack player;private volatile HttpsURLConnection connection;
    public CloudVoice(Context c,Handler h,Listener l){context=c;main=h;listener=l;}
    public boolean busy(){return busy;}public boolean recording(){return recording;}
    public boolean configured(){return new File(context.getFilesDir(),"cloud-device.json").isFile();}
    private void status(long g,String text){main.post(()->{if(g==generation)listener.state(text);});}
    public void start(java.util.concurrent.Callable<JSONArray> events){
        if(busy)return;busy=true;recording=true;long g=++generation;
        status(g,"正在听 · 再点一下结束，最长 15 秒");
        io.execute(()->{
            try{
                if(g!=generation)return;
                int min=AudioRecord.getMinBufferSize(16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT);
                AudioRecord r=new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(6400,min));recorder=r;
                if(r.getState()!=AudioRecord.STATE_INITIALIZED)throw new IOException("microphone");
                ByteArrayOutputStream pcm=new ByteArrayOutputStream();byte[] block=new byte[1600];r.startRecording();
                while(recording&&g==generation&&pcm.size()<480000){int n=r.read(block,0,Math.min(block.length,480000-pcm.size()));if(n<0)throw new IOException("recording");pcm.write(block,0,n);}
                r.stop();r.release();recorder=null;recording=false;
                if(g!=generation)return;
                if(pcm.size()<3200){status(g,"录音太短，请再试一次");return;}
                java.util.concurrent.FutureTask<JSONArray> observed=new java.util.concurrent.FutureTask<>(events);main.post(observed);
                JSONObject payload=new JSONObject();payload.put("id",UUID.randomUUID().toString());payload.put("audio",Base64.encodeToString(pcm.toByteArray(),Base64.NO_WRAP));payload.put("events",observed.get(3,java.util.concurrent.TimeUnit.SECONDS));
                if(g!=generation)return;
                status(g,"正在听懂并准备回答…");
                JSONObject response=request("turn",payload,g);
                if(g!=generation)return;
                deliver(response,g,null);
            }catch(Exception e){if(g==generation)failure(g,e,false);}
            finally{
                AudioRecord r=recorder;if(r!=null){try{r.stop();}catch(Exception ignored){}r.release();recorder=null;}
                if(g==generation){recording=false;busy=false;main.post(()->{if(g==generation)listener.speech(0,false);});}
            }
        });
    }
    public void touch(String region,JSONArray events){
        if(busy||TouchPolicy.label(region)==null)return;busy=true;long g=++generation;
        status(g,"轻触"+TouchPolicy.label(region)+" · 正在准备回应…");
        io.execute(()->{
            try{
                if(g!=generation)return;
                JSONObject payload=new JSONObject();payload.put("id",UUID.randomUUID().toString());
                payload.put("text",TouchPolicy.prompt(region));payload.put("events",events);
                JSONObject response=request("turn",payload,g);
                if(g==generation)deliver(response,g,"轻触"+TouchPolicy.label(region));
            }catch(Exception e){if(g==generation)failure(g,e,true);}
            finally{if(g==generation){busy=false;main.post(()->{if(g==generation)listener.speech(0,false);});}}
        });
    }
    private void deliver(JSONObject response,long g,String interaction)throws Exception{
        main.post(()->{if(g==generation)listener.reply(interaction==null?response.optString("heard"):interaction,response.optString("reply"));});
        byte[] audio=Base64.decode(response.getString("audio"),Base64.DEFAULT);
        if(response.getInt("sample_rate")!=16000||audio.length>1000000||audio.length%2!=0)throw new IOException("audio");
        play(audio,g);status(g,"点击说话或轻触形象 · DeepSeek / 中文语音");
    }
    private static String safeError(Exception e){String m=e.getMessage();return m!=null&&m.matches("HTTP_[0-9]{3}")?m:e.getClass().getSimpleName();}
    private void failure(long g,Exception e,boolean interaction){
        if("daily_speech_limit".equals(e.getMessage())){status(g,"今日语音额度已用完 · 明日恢复，表情动作仍可使用");return;}
        if("slow_down".equals(e.getMessage())||"busy".equals(e.getMessage())){status(g,"上一轮还在处理，请稍等片刻");return;}
        status(g,(interaction?"互动回复暂时失败（":"连接或语音失败（")+safeError(e)+"）· 可稍后再试");
    }
    public void finish(){recording=false;}
    public void cancel(){generation++;recording=false;busy=false;HttpsURLConnection c=connection;if(c!=null)c.disconnect();AudioTrack p=player;if(p!=null)try{p.pause();p.flush();}catch(Exception ignored){}listener.speech(0,false);}
    public void close(){cancel();io.shutdown();}
    private JSONObject request(String path,JSONObject body,long g)throws Exception{
        JSONObject config;try(InputStream in=context.openFileInput("cloud-device.json")){config=new JSONObject(new String(read(in,4096),"UTF-8"));}
        URL url=new URL(config.getString("url")+"/"+path);
        if(!"https".equals(url.getProtocol())||!CloudEndpoint.HOST.equals(url.getHost()))throw new IOException("host");
        HttpsURLConnection c=(HttpsURLConnection)url.openConnection();connection=c;
        try{
            c.setInstanceFollowRedirects(false);c.setConnectTimeout(10000);c.setReadTimeout(90000);
            c.setRequestProperty("Authorization","Bearer "+config.getString("token"));c.setRequestProperty("X-Rem-Device",config.getString("device"));
            if(body!=null){byte[] bytes=body.toString().getBytes("UTF-8");c.setRequestMethod("POST");c.setDoOutput(true);c.setFixedLengthStreamingMode(bytes.length);c.setRequestProperty("Content-Type","application/json");try(OutputStream out=c.getOutputStream()){out.write(bytes);}}
            if(g!=generation)throw new IOException("cancelled");
            int code=c.getResponseCode();if(code!=200){
                String reason="";try(InputStream error=c.getErrorStream()){if(error!=null)reason=new String(read(error,256),"UTF-8").trim();}catch(IOException ignored){}
                if(code==429&&(reason.equals("daily_speech_limit")||reason.equals("slow_down")||reason.equals("busy")))throw new IOException(reason);
                throw new IOException("HTTP_"+code);
            }
            try(InputStream in=c.getInputStream()){return new JSONObject(new String(read(in,2000000),"UTF-8"));}
        }finally{c.disconnect();if(connection==c)connection=null;}
    }
    private static byte[] read(InputStream in,int limit)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buf=new byte[8192];int n;while((n=in.read(buf))!=-1){if(out.size()+n>limit)throw new IOException("size");out.write(buf,0,n);}return out.toByteArray();}
    private void play(byte[] pcm,long g)throws Exception{
        AudioTrack p=new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(new AudioFormat.Builder().setSampleRate(16000).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build()).setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(6400).build();
        player=p;p.play();int written=0;
        try{
            for(int offset=0;offset<pcm.length&&g==generation;){int n=p.write(pcm,offset,Math.min(1600,pcm.length-offset),AudioTrack.WRITE_BLOCKING);if(n<=0)throw new IOException("playback");
                double sum=0;for(int i=offset;i+1<offset+n;i+=2){short value=(short)((pcm[i]&255)|(pcm[i+1]<<8));sum+=(double)value*value;}
                double level=Math.min(1,Math.sqrt(sum/(n/2))/6500);main.post(()->{if(g==generation)listener.speech(level,true);});offset+=n;written+=n/2;}
            long end=SystemClock.elapsedRealtime()+2000;while(g==generation&&p.getPlaybackHeadPosition()<written&&SystemClock.elapsedRealtime()<end)Thread.sleep(20);
        }finally{p.stop();p.release();player=null;main.post(()->{if(g==generation)listener.speech(0,false);});}
    }
    public void personality(String value){
        if(busy)return;busy=true;long g=++generation;
        io.execute(()->{try{JSONObject body=null;if(value!=null){body=new JSONObject();body.put("style",value);}JSONObject result=request("personality",body,g);
            main.post(()->{if(g==generation){busy=false;listener.settings(value==null?result.optString("style"):null);}});
        }catch(Exception e){status(g,"人格设置暂时无法连接");}finally{if(g==generation)busy=false;}});
    }
}
