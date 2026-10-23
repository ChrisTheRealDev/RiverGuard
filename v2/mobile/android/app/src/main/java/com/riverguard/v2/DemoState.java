package com.riverguard.v2;
import org.json.JSONObject;
import java.time.Instant;
import static com.riverguard.v2.PhoneValidation.*;
/** Bounded, deterministic scenarios. Only the application runtime writes samples. */
public final class DemoState {
    private DemoState() {}
    public static final String[] SCENARIOS={"Normal river","Cloudier water","Sudden change","Rising water level"};
    public static String scenario(String value){for(String s:SCENARIOS)if(s.equals(value))return value;throw new Problem(422,"Choose an available demonstration scenario.");}
    public static JSONObject initial(){return json("revision",0,"scenario",SCENARIOS[0],"running",true,"step",0,"error",null);}
    private static double randomAt(int index,int channel,long seed){
        int x=(int)(index+channel*131L+seed*8191L);
        for(int i=0;i<2;i++)x=(x^(x>>>16))*0x45d9f3b;
        return Integer.toUnsignedLong(x^(x>>>16))/4294967295.0*2-1;
    }
    private static double variation(int phase,int channel,int span,long seed){
        double position=(double)phase/span,t=position-Math.floor(position),blend=t*t*(3-2*t);int index=(int)Math.floor(position);
        return .8*(randomAt(index,channel,seed)*(1-blend)+randomAt(index+1,channel,seed)*blend)+.2*randomAt(phase,channel+50,seed);
    }
    public static JSONObject sample(String scenario,long step,long now){
        scenario(scenario);int phase=(int)(((step%120)+120)%120);long seed=Math.floorMod(Math.floorDiv(now,240000),1000003);
        JSONObject p=json("timestamp",Instant.ofEpochMilli(now).toString(),"ph",7.2+.12*variation(phase,1,5,seed),"turbidity",14+4*variation(phase,2,5,seed),"temperature",27+.25*variation(phase,3,20,seed),"water_level",30+.3*variation(phase,4,5,seed),"scenario",scenario);
        if(phase>=10){if(scenario.equals("Cloudier water"))put(p,"turbidity",65+120*(1-Math.exp(-(phase-10)/24.0))+6*variation(phase,2,5,seed));if(scenario.equals("Sudden change")){put(p,"ph",5.8+.12*variation(phase,1,5,seed));put(p,"turbidity",80+8*variation(phase,2,5,seed));}if(scenario.equals("Rising water level"))put(p,"water_level",45+100*(1-Math.exp(-(phase-10)/20.0))+.6*variation(phase,4,5,seed));}
        return p;
    }
}
