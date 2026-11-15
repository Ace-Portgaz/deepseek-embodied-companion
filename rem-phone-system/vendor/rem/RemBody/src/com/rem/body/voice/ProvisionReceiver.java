package com.rem.body.voice;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Base64;
import org.json.JSONObject;
/** Shell-only provisioning, protected by signature-level DUMP permission in manifest. */
public final class ProvisionReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        try{
            String encoded=intent.getStringExtra("config");
            if(encoded==null||encoded.length()>4096)throw new IllegalArgumentException();
            byte[] bytes=Base64.decode(encoded,Base64.DEFAULT);
            JSONObject config=new JSONObject(new String(bytes,"UTF-8"));
            if(!CloudEndpoint.BASE_URL.equals(config.getString("url"))
                ||!config.getString("device").matches("phone-[a-zA-Z0-9-]{8,64}")
                ||!config.getString("token").matches("[a-zA-Z0-9_-]{40,128}"))throw new IllegalArgumentException();
            try(java.io.FileOutputStream out=context.openFileOutput("cloud-device.json",Context.MODE_PRIVATE)){out.write(bytes);}
            setResultCode(-1);setResultData("enrolled");
        }catch(Exception e){setResultCode(0);setResultData("invalid_configuration");}
    }
}
