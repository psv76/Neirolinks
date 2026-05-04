var CH = {
 tBoilerSupply:"wb-m1w2_170/External Sensor 1", tBoilerReturn:"wb-m1w2_170/External Sensor 2",
 tTpDomSupply:"wb-m1w2_141/External Sensor 1", tTpDomReturn:"wb-m1w2_141/External Sensor 2",
 tGpDomSupply:"wb-m1w2_167/External Sensor 1", tGpDomReturn:"wb-m1w2_167/External Sensor 2",
 tGpBesSupply:"wb-m1w2_173/External Sensor 1", tGpBesReturn:"wb-m1w2_173/External Sensor 2",
 tpDomZones:["A08/K1","A08/K2","A08/K3","A08/K4","A08/K5"],
 gpDomZones:["A13/K1","A13/K2","A13/K3","A13/K4","A13/K5","A13/K6","A14/K1","A14/K2","A14/K3","A14/K4"],
 radDomZones:["A09/K1","A09/K2","A09/K3","A09/K4","A09/K5"]
};
var CFG = {sensorMinC:-40,sensorMaxC:120};
function nOrNull(p){var v=Number(dev[p]); return isNaN(v)?null:v;}
function b(v){ return v===true||v===1||v==="1"||v==="true"; }
function cnt(a){var i,c=0;for(i=0;i<a.length;i++) if(b(dev[a[i]])) c++; return c;}
function d(a,bv){ if(a===null||bv===null) return null; return Math.round((a-bv)*10)/10;}
function bad(v){ return v===null||v<CFG.sensorMinC||v>CFG.sensorMaxC;}
function setCell(c,v){ if(dev["heat_diagnostics/"+c]!==v) dev["heat_diagnostics/"+c]=v; }
function evalDiag(){
 var bs=nOrNull(CH.tBoilerSupply), br=nOrNull(CH.tBoilerReturn), ts=nOrNull(CH.tTpDomSupply), tr=nOrNull(CH.tTpDomReturn), gs=nOrNull(CH.tGpDomSupply), gr=nOrNull(CH.tGpDomReturn), bss=nOrNull(CH.tGpBesSupply), bsr=nOrNull(CH.tGpBesReturn);
 var err=[];
 if(bad(bs)) err.push("датчик tBoilerSupply"); if(bad(br)) err.push("датчик tBoilerReturn"); if(bad(ts)) err.push("датчик tTpDomSupply"); if(bad(tr)) err.push("датчик tTpDomReturn"); if(bad(gs)) err.push("датчик tGpDomSupply"); if(bad(gr)) err.push("датчик tGpDomReturn"); if(bad(bss)) err.push("датчик tGpBesSupply"); if(bad(bsr)) err.push("датчик tGpBesReturn");
 setCell("d_boiler", d(bs,br)); setCell("d_tp_dom", d(ts,tr)); setCell("d_gp_dom", d(gs,gr)); setCell("d_gp_besedka", d(bss,bsr));
 setCell("tp_dom_demand_count", cnt(CH.tpDomZones)); setCell("gp_dom_demand_count", cnt(CH.gpDomZones)); setCell("rad_dom_demand_count", cnt(CH.radDomZones));
 setCell("status_text", err.length?"Ошибка: "+err.join(", "):"Диагностика в норме");
}

defineVirtualDevice("heat_diagnostics",{title:"Диагностика отопления",cells:{status_text:{type:"text",value:""},d_boiler:{type:"value",value:0},d_tp_dom:{type:"value",value:0},d_gp_dom:{type:"value",value:0},d_gp_besedka:{type:"value",value:0},tp_dom_demand_count:{type:"value",value:0},gp_dom_demand_count:{type:"value",value:0},rad_dom_demand_count:{type:"value",value:0}}});
defineRule("heat_diagnostics_eval",{whenChanged:[CH.tBoilerSupply,CH.tBoilerReturn,CH.tTpDomSupply,CH.tTpDomReturn,CH.tGpDomSupply,CH.tGpDomReturn,CH.tGpBesSupply,CH.tGpBesReturn].concat(CH.tpDomZones).concat(CH.gpDomZones).concat(CH.radDomZones),then:function(){evalDiag();}});
setTimeout(function(){evalDiag();},3000);
