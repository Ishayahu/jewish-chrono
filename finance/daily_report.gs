// Install in the private spreadsheet via Extensions > Apps Script.
// Set REPORT_EMAIL in Script Properties; set project timezone Europe/Moscow.
function sendDailyBudgetReport() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const props = PropertiesService.getScriptProperties();
    const email = props.getProperty('REPORT_EMAIL');
    const id = props.getProperty('BUDGET_SPREADSHEET_ID');
    if (!email || !id) throw new Error('Configure REPORT_EMAIL and BUDGET_SPREADSHEET_ID');
    const ss = SpreadsheetApp.openById(id);
    const p = ss.getSheetByName('Показатели').getRange('B2:B5').getValues().flat();
    const expected = Utilities.formatDate(new Date(Date.now()-4*3600000), 'Europe/Moscow', 'yyyy-MM-dd');
    const day = p[0] instanceof Date ? Utilities.formatDate(p[0], 'Europe/Moscow', 'yyyy-MM-dd') : String(p[0]);
    if (props.getProperty('LAST_SENT_DAY') === expected) return;
    const rows = ss.getSheetByName('Операции').getRange('A2:H1000').getDisplayValues().filter(r=>r.some(Boolean));
    const valid = day === expected && p.slice(1).every(v=>typeof v==='number' && Number.isFinite(v));
    const incomplete = rows.some(r=>r[1]==='Приход' && r[4]==='RUB' && (!r[6] || (r[6]==='Дополнительный' && !r[7])));
    const lines = [
      valid && !incomplete ? 'К переводу в копилку: '+p[3].toFixed(2)+' RUB' : 'Сумма к переводу не подтверждена: проверьте дату снимка и полноту операций.',
      'Дата снимка: '+day,
      'Дневная цель: '+p[1],
      'Доступный дополнительный приход: '+p[2],
      '',
      'Операции (дата | тип | категория | сумма | валюта | описание | вид дохода | доступно RUB):',
      ...rows.map(r=>r.join(' | '))
    ];
    MailApp.sendEmail(email, 'Финансовый отчёт — '+expected, lines.join('\n'));
    props.setProperty('LAST_SENT_DAY', expected);
  } finally { lock.releaseLock(); }
}
function installDailyBudgetTrigger() {
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='sendDailyBudgetReport').forEach(t=>ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('sendDailyBudgetReport').timeBased().atHour(2).everyDays(1).inTimezone('Europe/Moscow').create();
}
