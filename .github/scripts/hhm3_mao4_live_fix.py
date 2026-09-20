from pathlib import Path
root=Path('objects/05_31_Ivolga_13/HHM3_FSE')
def edit(name,changes):
    p=root/name;s=p.read_text(encoding='utf-8')
    for old,new in changes:
        if s.count(old)!=1:raise RuntimeError(f'{name}: expected one match, found {s.count(old)}: {old[:65]!r}')
        s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')
edit('modules/HHM3Outputs.js', [
('''    function startOpen(now){
        state='OPENING';confirmedOffSeq=-1;
        transaction={at:now,level:desiredLevel,sent:false};
    }''','''    function startOpen(now){
        // Only an already qualified OPEN may reuse its fresh, unchanged ON.
        var provedOnSeq=state==='OPEN'&&io.matches(c.enable,true)?io.seq(c.enable):-1;
        state='OPENING';confirmedOffSeq=-1;
        transaction={at:now,level:desiredLevel,sent:false,provedOnSeq:provedOnSeq,reuseOn:false};
    }'''),
('''            if(!transaction.sent){
                transaction.levelSeq=io.seq(c.level);transaction.switchSeq=io.seq(c.enable);
                transaction.sent=true;''','''            if(!transaction.sent){
                // If Switch changed while pump stopped, old ON cannot be reused.
                transaction.reuseOn=transaction.provedOnSeq>=0&&
                    io.seq(c.enable)===transaction.provedOnSeq&&io.matches(c.enable,true);
                transaction.levelSeq=io.seq(c.level);transaction.switchSeq=io.seq(c.enable);
                transaction.sent=true;'''),
('''            // Both attributes must have NEW matching messages AFTER this Level.
            // Never use Switch ON to restore a stale remembered position.
            if(io.seq(c.level)<=transaction.levelSeq||io.seq(c.enable)<=transaction.switchSeq||
                !io.matches(c.level,transaction.level)||!io.matches(c.enable,true))return report(false);''','''            // An observed OFF invalidates former ON immediately.
            if(io.seq(c.enable)>transaction.switchSeq&&io.matches(c.enable,false))
                return fail(now,'OPEN_SWITCH_OFF');
            // New Level is required for EVERY target. A new ON is required from
            // CLOSED; only retargeting an already-qualified OPEN may preserve ON.
            var onNow=io.matches(c.enable,true);
            var freshOn=io.seq(c.enable)>transaction.switchSeq&&onNow;
            var preservedOn=transaction.reuseOn&&io.seq(c.enable)===transaction.switchSeq&&onNow;
            if(io.seq(c.level)<=transaction.levelSeq||!io.matches(c.level,transaction.level)||
                !(freshOn||preservedOn))return report(false);''')])
edit('tests/review-regressions.js',[
('if(p===c.level){o[c.enable]=v>0;if(!drop(c.enable))emit(c.enable,o[c.enable]);}',
 '''if(p===c.level){const oldSwitch=o[c.enable];o[c.enable]=v>0;
    if(oldSwitch!==o[c.enable]&&!drop(c.enable))emit(c.enable,o[c.enable]);}'''),
("test('A05 opening needs new Level AND Switch readback after Level, never cached ON'", "test('A05 first opening needs new Level AND Switch readback after Level, never cached ON'"),
(" test('A05 Level failure before/after application, startup/running, closes only with OFF',()=>{",''' test('A05 live probe: retarget 20/ON to 40/ON without duplicate ON for every mixed channel',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);
   let r=f.run(20,true);assert.equal(r.state,'OPEN');assert.equal(r.ready,true);
   const oldSeq=f.io.seq(c.enable),n=f.writes.length;r=f.run(40,true);
   assert.equal(f.io.seq(c.enable),oldSeq);assert.equal(r.state,'OPEN');assert.equal(r.ready,true);
   assert.equal(r.requested_level,41);assert.equal(f.values[c.pump],true);assert.equal(f.position(),41);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.enable&&w.value===true));
  }
 });
 test('A05 Level failure before/after application, startup/running, closes only with OFF',()=>{''')])
p=root/'tests/level-integer-regressions.js';s=p.read_text(encoding='utf-8')
for old,new in [
('let omitSameOn=true,integerReadback=true,dropEnable=false;', 'let omitSameOn=true,integerReadback=true,dropEnable=false,dropLevel=false;'),
('if(path===c.enable&&dropEnable)return;', 'if((path===c.enable&&dropEnable)||(path===c.level&&dropLevel))return;'),
('return {c,io,writes,values,dropSwitch:v=>dropEnable=v,', '''return {c,io,writes,values,dropSwitch:v=>dropEnable=v,dropLevel:v=>dropLevel=v,
        inject:(path,value)=>record(path,value),''')]:
    if s.count(old)!=1:raise RuntimeError('integer fixture mismatch: '+old)
    s=s.replace(old,new)
a=s.index("test('missing duplicate ON during retarget fails closed without a stale approval',()=>{")
b=s.index("test('closing preserves remembered integer Level; no Level write on close',()=>{",a)
s=s[:a]+'''test('live probe: retarget 20/ON to 40/ON needs new Level, no duplicate ON',()=>{
    const f=fixture();f.run(0,false);assert.equal(f.run(20,true).state,'OPEN');
    const oldSeq=f.io.seq(f.c.enable),r=f.run(40,true);
    assert.equal(f.io.seq(f.c.enable),oldSeq);assert.equal(r.state,'OPEN');assert.equal(r.ready,true);
    assert.equal(r.requested_level,41);assert.equal(f.io.read(f.c.pump),1);
});
test('retarget rejects absent Level acknowledgment and OFF invalidates prior ON',()=>{
    const f=fixture();f.run(0,false);assert.equal(f.run(20,true).state,'OPEN');
    f.dropLevel(true);let r=f.run(40,true);assert.equal(r.state,'OPENING');
    assert.equal(r.ready,false);assert.equal(f.io.read(f.c.pump),0);
    f.inject(f.c.enable,0);f.dropLevel(false);f.inject(f.c.level,41);
    r=f.run(40,true,1000);assert.equal(r.ready,false);assert.equal(r.state,'CLOSED');
    assert.equal(f.io.read(f.c.enable),0);assert.equal(f.io.read(f.c.pump),0);
});
test('first opening from OFF cannot reuse historical ON',()=>{
    const f=fixture();f.run(0,false);f.dropSwitch(true);
    let r=f.run(20,true);assert.equal(r.state,'OPENING');assert.equal(r.ready,false);
    assert.equal(f.io.read(f.c.pump),0);
    r=f.run(20,true,10000);assert.equal(r.ready,false);
    assert.equal(f.writes.filter(w=>w.path===f.c.enable&&w.value===true).length,0);
});
'''+s[b:]
p.write_text(s,encoding='utf-8')
edit('README.md',[
('Физической установки и испытаний на объекте при разработке не было.', 'Установки HHM3 и его эксплуатационной ПНР не было; отдельный MQTT-тест A05 Channel 1 выполнен владельцем 20.09.2026.'),
('| OPENING | Насос OFF; отправка нового целевого Level. Обязательны новые совпадающие сообщения Level и Switch ON после этой записи. Отдельных Switch ON программа не отправляет. |',
 '| OPENING | Насос OFF; новый целочисленный Level. Из CLOSED обязательны новые Level и ON. Только при смене цели из подтверждённого OPEN допускается прежний свежий ON без повторной публикации при неизменном Switch; новый Level обязателен всегда. Отдельных Switch ON программа не пишет. |'),
('Отправляется новый вычисленный Level, а готовность требует двух свежих совпавших сообщений.', 'Отправляется новый вычисленный Level; при первом открытии нужны два новых совпавших сообщения. Только при ретаргетинге из OPEN новый Level подтверждается при сохранении прежнего достоверного ON без промежуточного OFF.'),
('Кэш/retained/прежний readback не подтверждают новую транзакцию.', 'Кэш/retained/прежний Level не подтверждают новую транзакцию; прежний ON используется исключительно при подтверждённом непрерывном OPEN и действующей свежести.'),
('Для всех 560/561/562 используется один HHM3Outputs.', '20.09.2026 23:27 +05 на A05 Channel 1 / 560 владелец проверил без HHM3 и при K1 OFF: Level20 → 20/ON; только Level40 → 40/ON, но в non-retained MQTT за четыре секунды опубликован только Level40, без повторного Switch ON; завершающий только Switch OFF → 40/OFF. Это MQTT-факт одного канала, не испытание герметичности и не ПНР системы.\n\nДля всех 560/561/562 используется один HHM3Outputs.')])
edit('INSTALL.md',[
('Только два новых совпавших non-retained readback — Level и ON — дают готовность;', 'При первом открытии только два новых совпавших non-retained readback — Level и ON — дают готовность; при ретаргетинге из уже подтверждённого OPEN достаточно нового Level и непрерывно достоверного прежнего ON при неизменившемся Switch;'),
('для открытия — новые Level и ON после целевого Level.', 'для первого открытия — новые Level и ON после целевого Level; для смены цели из OPEN — новый Level и всё ещё действительный ON без промежуточного OFF.'),
('- NO_DEMAND: какой конкретный CH-only endpoint', '- Фактический MQTT-тест A05 Channel 1 / 560 20.09.2026 23:27 +05: без HHM3, насос K1 OFF; только Level20 → 20/ON; только Level40 → 40/ON, при этом в течение четырёх секунд пришёл только non-retained Level40 и не пришёл повторный Switch ON; cleanup только Switch OFF → 40/OFF. Это не измерение герметичности и не индивидуальный тест 561/562.\n- NO_DEMAND: какой конкретный CH-only endpoint')])
p=root/'TEST_RESULTS.md';s=p.read_text(encoding='utf-8')
s+='''\n\n## Испытание A05 владельцем и исправление ретаргетинга — 20.09.2026\n\nНа WB `wirenboard-ABF62SL`, A05 Channel 1 / 560, при отсутствии HHM3 и выключенном насосе K1: Level20 → 20/ON; затем только Level40 → 40/ON. В течение четырёх секунд после второй команды non-retained MQTT публиковал только `Channel 1 Dimming Level 40`, повторного Switch ON не было. Cleanup: только Switch OFF → 40/OFF, сохранённый Level не изменился. Это наблюдение одного канала, не физическая приёмка остальных приводов, герметичности или работы HHM3.\n\nВ `HHM3Outputs.js` устранён подтверждённый дефект: первоначальное открытие из CLOSED всё ещё требует новых Level и Switch ON, но ретаргетинг уже подтверждённого OPEN разрешён по **новому Level readback и непрерывно подтверждённому свежему ON**, если последовательность Switch не изменялась. Любой вновь опубликованный OFF немедленно отменяет открытие и ведёт к OFF, в том числе при запаздывании Level. При потере Level readback насос/заявка не разрешаются. Новые mock-группы на все 501/502/504 и отрицательные тесты OFF/Level доступны в tests/review-regressions.js и tests/level-integer-regressions.js.\n\nПроверки после этого коммита: node tests/run.js — ожидается **56 групп**, node tests/manifest.js --check. Исторические 53 PASS относятся к прежней ревизии. ПНР CH-only NO_DEMAND, герметичности/хода 560/561/562, 506, bridge TLS/ACL не проводилась.\n'''
p.write_text(s,encoding='utf-8')
