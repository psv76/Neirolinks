var System = require("system");
var safeLog = System.safeLog;

var CH = {
    u1: "A01/Urms L1", u2: "A01/Urms L2", u3: "A01/Urms L3",
    i1: "A01/Irms L1", i2: "A01/Irms L2", i3: "A01/Irms L3",
    cross: "wb-gpio/EXT1_IN1", qf1: "wb-gpio/EXT1_IN2", qf2: "wb-gpio/EXT1_IN3", qf3: "wb-gpio/EXT1_IN4",
    upsStatus: "UPS1/battery_status", upsInputV: "UPS1/input_voltage"
};
var CFG = { minPhaseVoltage: 170, crossDelayS: 20, restoreDelayS: 180 };
var STATE = { mainsLost: false, crossTimer: null, restoreTimer: null, lastSms: "" };

function b(v){ return v===true||v===1||v==="1"||v==="true"; }
function n(p){ var v=Number(dev[p]); return isNaN(v)?0:v; }
function smsOnce(key, fn){ if (STATE.lastSms===key) return; STATE.lastSms=key; fn(); }
function hasMains(){ return n(CH.u1)>=CFG.minPhaseVoltage || n(CH.u2)>=CFG.minPhaseVoltage || n(CH.u3)>=CFG.minPhaseVoltage; }
function setCell(c,v){ if(dev["power_monitor/"+c]!==v) dev["power_monitor/"+c]=v; }

function updateStatus(){
 setCell("mains_present", hasMains()); setCell("cross_present", b(dev[CH.cross]));
 setCell("secondary_alerts_blocked", STATE.mainsLost);
 setCell("ups_battery_status", n(CH.upsStatus)); setCell("ups_input_voltage", n(CH.upsInputV));
}
function onLost(){ if(STATE.mainsLost) return; STATE.mainsLost=true; dev["power_monitor/secondary_alerts_blocked"]=true; smsOnce("lost", function(){System.sendAlert("Котельная","Отключено основное питание","Контроль по фазам A01 и кросс-модулю.","Проверьте ввод и реле напряжения.");}); }
function onRestore(){ if(!STATE.mainsLost) return; STATE.mainsLost=false; smsOnce("restore", function(){System.sendRestore("Котельная","Основное питание восстановлено","Снятие блокировки вторичных тревог по задержке.","");}); if(STATE.restoreTimer) clearTimeout(STATE.restoreTimer); STATE.restoreTimer=setTimeout(function(){dev["power_monitor/secondary_alerts_blocked"]=false;}, CFG.restoreDelayS*1000); }

function evaluate(){
 var mains=hasMains(); var cross=b(dev[CH.cross]);
 if(mains && !cross){ if(!STATE.crossTimer){ STATE.crossTimer=setTimeout(function(){STATE.crossTimer=null; if(hasMains()&&!b(dev[CH.cross])) onLost(); updateStatus();}, CFG.crossDelayS*1000);} }
 else { if(STATE.crossTimer){clearTimeout(STATE.crossTimer); STATE.crossTimer=null;} if(!mains||!cross) onLost(); else onRestore(); }
 if(n(CH.upsStatus)>=2){ smsOnce("ups_alarm_"+n(CH.upsStatus), function(){System.sendAlert("Котельная","Аварийный статус UPS1","battery_status="+n(CH.upsStatus),"Проверьте ИБП.");}); }
 updateStatus();
}

defineVirtualDevice("power_monitor",{title:"Монитор питания",cells:{secondary_alerts_blocked:{type:"switch",value:false},mains_present:{type:"switch",readonly:true,value:false},cross_present:{type:"switch",readonly:true,value:false},ups_battery_status:{type:"value",readonly:true,value:0},ups_input_voltage:{type:"value",readonly:true,value:0}}});

defineRule("power_monitor_eval",{whenChanged:[CH.u1,CH.u2,CH.u3,CH.cross,CH.qf1,CH.qf2,CH.qf3,CH.upsStatus,CH.upsInputV],then:function(){evaluate();}});
setTimeout(function(){evaluate(); safeLog("[100_power_monitor] started");},3000);
