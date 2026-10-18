/* 05 16 Iset: sole physical K1..K11 / living K4 output writer.
 * Pure injectable I/O interface; the live driver is NOT installed.
 * SHADOW never writes physical outputs. PHYSICAL requires separately
 * confirmed exclusive ownership and room commissioning.
 * Actual external HM2 shutdown/ownership audit is a deployment gate.
 */
function name(s){return typeof s==='string'&&s.length>0;}
exports.create=function(c){
    if(!c||!c.map||!c.map.zones||!name(c.map.pump)||
       typeof c.write!=='function'||
       (c.mode!=='SHADOW'&&c.mode!=='PHYSICAL'))
        throw new Error('Iset writer: I/O and explicit mode required');
    var allowed={},i,j,z,p,number=0;
    for(i=0;i<c.map.zones.length;i++){
        z=c.map.zones[i];
        if(!z||!z.outputs||!z.outputs.length)
            throw new Error('Iset writer: invalid room');
        for(j=0;j<z.outputs.length;j++){
            p=z.outputs[j];
            if(!name(p)||allowed[p]||p===c.map.pump)
                throw new Error('Iset writer: duplicate/invalid physical channel');
            allowed[p]='VALVE';number++;
        }
    }
    if(number!==11)throw new Error('Iset writer: expected eleven mapped NO outputs');
    allowed[c.map.pump]='PUMP';
    function eligible(a){
        if(!a||!name(a.path))return false;
        var type=allowed[a.path];
        return type==='VALVE'&&
            ((a.action==='ZONE_OPEN'&&a.value===false)||
             (a.action==='ZONE_CLOSE'&&a.value===true))||
            type==='PUMP'&&
            ((a.action==='PUMP_START'&&a.value===true)||
             (a.action==='PUMP_STOP'&&a.value===false));
    }
    return {
        apply:function(plan){
            if(!plan||plan.state!=='PLANNED_ONLY'||!plan.actions||
               !Array.isArray(plan.actions))
                return {mode:'REJECTED',written:0,reason:'INVALID_PLAN'};
            // Reject the whole batch on unexpected or duplicate channels.
            var seen={},k;
            for(k=0;k<plan.actions.length;k++){
                var a=plan.actions[k];
                if(!eligible(a)||seen[a.path])
                    return {mode:'REJECTED',written:0,
                        reason:'UNKNOWN_OR_DUPLICATE_CHANNEL'};
                seen[a.path]=true;
            }
            if(c.mode!=='PHYSICAL')
                return {mode:'SHADOW',written:0,wouldWrite:plan.actions.length,
                    reason:'PHYSICAL_WRITES_DISABLED'};
            if(c.exclusiveOwnershipConfirmed!==true||
               c.commissioned!==true)
                return {mode:'NOT_COMMISSIONED',written:0,
                    reason:'HM2_OWNERSHIP_OR_COMMISSIONING_NOT_CONFIRMED'};
            var written=0,failures=[],item;
            for(k=0;k<plan.actions.length;k++){
                item=plan.actions[k];
                try{
                    // Boolean WB outputs: NO false=OPEN, true=CLOSE.
                    // A successful write is not physical valve feedback.
                    if(c.write(item.path,item.value)!==true){
                        failures.push(item.path);
                        if(c.log&&typeof c.log.warning==='function')
                            c.log.warning('[отопление][hhm_rooms_writer]['+
                                (item.zoneId||'насос')+']; ОШИБКА=Запись не подтверждена; канал='+item.path);
                    }else{
                        written++;
                        if(c.log&&typeof c.log.info==='function')
                            c.log.info('[отопление][hhm_rooms_writer]['+
                                (item.zoneId||'насос')+']; КОМАНДА='+item.action+
                                '; канал='+item.path+'; значение='+String(item.value));
                    }
                }catch(e){
                    failures.push(item.path);
                    if(c.log&&typeof c.log.warning==='function')
                        c.log.warning('[отопление][hhm_rooms_writer]['+
                            (item.zoneId||'насос')+']; ОШИБКА=Исключение записи; канал='+item.path);
                }
            }
            return {mode:'PHYSICAL',written:written,
                attempted:plan.actions.length,failed:failures};
        },
        ownership:function(){return c.mode==='PHYSICAL'&&
            c.exclusiveOwnershipConfirmed===true&&c.commissioned===true;},
        whitelist:function(){return Object.keys(allowed).sort();}
    };
};
