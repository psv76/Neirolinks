/* 05 16 Iset: compact per-room WB PersistentStorage binding.
 * One JSON string per room, no automatic setpoint defaults or I/O commands.
 * Writing and reading back verifies in-process acceptance, not power-loss
 * durability: verify that separately on the actual WB before commissioning.
 */
function validId(s){return typeof s==='string'&&/^[a-z][a-z0-9_]{1,63}$/.test(s);}
function integer(n){return typeof n==='number'&&isFinite(n)&&n>=0&&Math.floor(n)===n;}
function finite(n){return typeof n==='number'&&isFinite(n);}
exports.create=function(storage,zoneId){
    if(!storage||!validId(zoneId))
        throw new Error('Iset room settings: storage and zone required');
    var key='iset_hhm_room_v1_'+zoneId;
    function parse(raw){
        if(typeof raw!=='string'||raw.length>400)return null;
        try{
            var o=JSON.parse(raw);
            if(!o||o.version!==1||o.zoneId!==zoneId||
               (o.mode!=='HEAT'&&o.mode!=='OFF')||
               !finite(o.setpointC)||!integer(o.revision))return null;
            return {mode:o.mode,setpointC:o.setpointC,revision:o.revision};
        }catch(e){return null;}
    }
    function encode(s){
        if(!s||(s.mode!=='HEAT'&&s.mode!=='OFF')||
           !finite(s.setpointC)||!integer(s.revision))return null;
        return JSON.stringify({version:1,zoneId:zoneId,mode:s.mode,
            setpointC:s.setpointC,revision:s.revision});
    }
    return {
        key:key,
        read:function(){return parse(storage[key]);},
        commit:function(s){
            var text=encode(s);
            if(text===null)return false;
            // No implicit defaults: first approved commissioning record must
            // be written by an independently authorised commissioning action.
            if(parse(storage[key])===null)return false;
            try{
                storage[key]=text;
                return storage[key]===text;
            }catch(e){return false;}
        },
        // Produces a candidate only: it never writes storage.
        proposeInitial:function(mode,setpointC){
            return encode({mode:mode,setpointC:setpointC,revision:0});
        }
    };
};
