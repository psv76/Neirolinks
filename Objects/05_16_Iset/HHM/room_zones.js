/* 05 16 Исеть: living actuators confirmed from 2026-10-18 HM2 backup.
 * Eight sensors mapped by 2026-09-07 HA handoff and live 2026-10-18 WB.
 * Master-bedroom uses wardrobe WB-MSW 47 deliberately per HA handoff.
 * Current HA settings and setpoints remain unverified. Not commissioned.
 * Source: HeatingConfig.js SHA256 e359ed02bc87394e57cf59589d18f2fbbc237192d8c2aba84ac286678be5edf1.
 */
exports.objectId='05_16_Iset';
exports.commissioned=false;
// Verified by read-only WB WebUI and local MQTT, 2026-10-18.
// Historical HA sensor/climate entities are in 2026-09-07 handoff.
// HA live files on 2026-10-18 not yet read to exclude later config drift.
exports.roomSensorAudit={
    wbSerial:'AFMEUYOT',
    webuiSHA256:'8c08f64fd2e8186948fada6b3388bb1fc6ae832835e61187b1db9bbe06a8666a',
    observedOn:'2026-10-18',
    haHistoricalMappingDocumented:true,
    haHistoricalDate:'2026-09-07',
    haClimateMappingsVerified:false
};
exports.pump='wb-mr6cu_37/K4';
exports.actuators={type:'NO',openCommand:0,closeCommand:1,
    nominalOpenWaitMs:180000};
exports.zones=[
    {id:'office',title:'Кабинет',
     haSensor:'sensor.temperatura_kabinet',haClimate:'climate.kabinet',
     primarySensor:'wb-msw-v4_22/Temperature',
     primaryEvidence:'WB_WEBUI_AND_LIVE_MQTT',
     backupSensor:null,approvedSetpoint:null,
     oldDemand:'ha_heating_air/office_demand',
     outputs:['wb-mio-gpio_195:2/K1']},
    {id:'summer_kitchen',title:'Летняя кухня',
     haSensor:'sensor.temperatura_letniaia_kukhnia',haClimate:'climate.letniaia_kukhnia',
     primarySensor:'wb-msw-v4_53/Temperature',
     primaryEvidence:'WB_WEBUI_AND_LIVE_MQTT',
     backupSensor:null,approvedSetpoint:null,
     oldDemand:'ha_heating_air/summer_kitchen_demand',
     outputs:['wb-mio-gpio_195:2/K2','wb-mio-gpio_195:2/K3']},
    {id:'corridor',title:'Коридор',
     haSensor:'sensor.temperatura_koridor_2_etazh',haClimate:'climate.koridor',
     primarySensor:'wb-msw-v4_52/Temperature',
     primaryEvidence:'WB_WEBUI_AND_LIVE_MQTT',
     backupSensor:null,approvedSetpoint:null,
     oldDemand:'ha_heating_air/corridor_demand',
     outputs:['wb-mio-gpio_195:2/K4']},
    {id:'master_bathroom',title:'Мастер-санузел',
     haSensor:'sensor.temperatura_sanuzel_master_spalni',haClimate:'climate.master_sanuzel',
     primarySensor:'wb-msw-v4_54/Temperature',
     primaryEvidence:'WB_WEBUI_AND_LIVE_MQTT',
     backupSensor:null,approvedSetpoint:null,
     oldDemand:'ha_heating_air/master_bathroom_demand',
     outputs:['wb-mio-gpio_195:2/K5']},
    {id:'living_kitchen',title:'Гостиная + кухня',
     haSensor:'sensor.temperatura_gostinaia_2',haClimate:'climate.gostinaia_kukhnia',
     primarySensor:'wb-msw-v4_116/Temperature',
     primaryEvidence:'WB_WEBUI_AND_LIVE_MQTT',
     backupSensor:null,approvedSetpoint:null,
     oldDemand:'ha_heating_air/living_kitchen_demand',
     outputs:['wb-mio-gpio_195:2/K6','wb-mio-gpio_195:2/K7',
              'wb-mio-gpio_195:2/K9']},
    {id:'entrance',title:'Прихожая',
     haSensor:'sensor.temperatura_prikhozhaia_2',haClimate:'climate.prikhozhaia',
     primarySensor:'wb-msw-v4_43/Temperature',
     primaryEvidence:'WB_WEBUI_AND_LIVE_MQTT',
     backupSensor:null,approvedSetpoint:null,
     oldDemand:'ha_heating_air/entrance_demand',
     outputs:['wb-mio-gpio_195:2/K8']},
    {id:'guest_bathroom',title:'Гостевой санузел',
     haSensor:'sensor.temperatura_sanuzel_gostevoi',haClimate:'climate.gostevoi_sanuzel',
     primarySensor:'wb-msw-v4_106/Temperature',
     primaryEvidence:'WB_WEBUI_AND_LIVE_MQTT',
     backupSensor:null,approvedSetpoint:null,
     oldDemand:'ha_heating_air/guest_bathroom_demand',
     outputs:['wb-mio-gpio_195:2/K10']},
    {id:'master_bedroom',title:'Мастер-спальня',
     haSensor:'sensor.temperatura_garderob_2',
     haClimate:'climate.master_spalnia',
     primarySensor:'wb-msw-v4_47/Temperature',
     primaryEvidence:'WB_WEBUI_AND_LIVE_MQTT_AND_HA_HANDOFF_20260907',
     primaryLocation:'Гардероб мастер-спальни (намеренный выбор HA 07.09)',
     backupSensor:null,approvedSetpoint:null,
     alternateSensorRejected:'ONOKOM-AIR-HS-3-MB-B_9/Indoor air temperature',
     alternateSensorObservedInvalid:0,
     oldDemand:'ha_heating_air/master_bedroom_demand',
     outputs:['wb-mio-gpio_195:2/K11']}
];
exports.assertCommissionable=function(){
    if(exports.commissioned!==true)
        throw new Error('Iset room thermostats: not commissioned');
    var seen={},ids={},i,j,z,output;
    if(exports.zones.length!==8)
        throw new Error('Iset room thermostats: incomplete living zone map');
    for(i=0;i<exports.zones.length;i++){
        z=exports.zones[i];
        if(ids[z.id]||!z.primarySensor||
           typeof z.approvedSetpoint!=='number'||
           !isFinite(z.approvedSetpoint))
            throw new Error('Iset room thermostats: unverified zone/sensor/setpoint '+z.id);
        ids[z.id]=true;
        for(j=0;j<z.outputs.length;j++){
            output=z.outputs[j];
            if(seen[output])
                throw new Error('Iset room thermostats: duplicate actuator '+output);
            seen[output]=true;
        }
    }
    if(Object.keys(seen).length!==11||exports.actuators.type!=='NO'||
       exports.actuators.openCommand!==0||exports.actuators.closeCommand!==1)
        throw new Error('Iset room thermostats: physical contract mismatch');
    return true;
};
