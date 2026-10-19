/* #204 Iset: synthetic OpenTherm ramp comparison, offline only.
 * Historical anchor: 19.10.2026 06:32 / 07:56 setpoint rose ~70->75C.
 * No claim about real boiler flame, modulation or heating efficiency.
 */
var assert=require('assert');
var Source=require('../../../Objects/05_16_Iset/HHM/isethhm_source');
var cfg=require('../../../Objects/05_16_Iset/HHM/isethhm_service_config');
function frame(t,request,priority){
    return {nowS:t,sourceRequestedC:request,
        dhwPriorityPause:priority,otConnectionInvalid:false,
        equipmentAllowsHeat:true,offMethodCommissioned:true,
        flame:true};
}
function variant(rate){
    var policy={},k;
    for(k in cfg.source)
        if(cfg.source.hasOwnProperty(k))policy[k]=cfg.source[k];
    policy.dhwUpCPerMin=rate;
    var source=Source.create(policy),t,r,first74_5=null,tail=[];
    // Synthetic steady heating at 70C, preceding DHW priority.
    for(t=0;t<=600;t++){
        r=source.step(frame(t,67,false));
        if(r.desiredWrite)source.acknowledge(t,r.desiredWrite.value);
    }
    assert.strictEqual(r.targetC,70);
    for(t=601;t<=720;t++){
        // Synthetic 75C goal: DHW request 72 + source offset 3.
        r=source.step(frame(t,72,true));
        if(r.desiredWrite)source.acknowledge(t,r.desiredWrite.value);
        if(first74_5===null&&r.targetC>=74.5)first74_5=t-600;
        if(t===630||t===660||t===690)tail.push(r.targetC);
    }
    assert.strictEqual(r.targetC,75);
    return {rate:rate,secondsTo74_5:first74_5,
        valuesAt30_60_90s:tail};
}
var a=variant(10),b=variant(5),c=variant(3);
assert.ok(a.secondsTo74_5>=26&&a.secondsTo74_5<=30);
assert.ok(b.secondsTo74_5>=52&&b.secondsTo74_5<=57);
assert.ok(c.secondsTo74_5>=88&&c.secondsTo74_5<=94);
console.log('Iset source-only offline comparison; no physical replay');
console.log(JSON.stringify([a,b,c],null,2));
console.log('PASS three OT ramp variants, same synthetic heat requests');
