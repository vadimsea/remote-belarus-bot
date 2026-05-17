# Планировщик Windows (только пока включён ПК). Для работы 24/7 — deploy/setup_linux.sh на VPS.
# Планировщик Windows: реклама в 09:00 + проверка вакансий каждые 5 мин (10:00–20:00)
# Случайное время 5 постов задаётся в БД при первом запуске за день (см. python main.py --show-schedule)
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$Main = Join-Path $ProjectDir "main.py"
$TaskPrefix = "RemoteBelarusVacancy"

# Реклама vadzim.by + канал @vadzimby_live — раз в день в 09:00
$promoTask = "${TaskPrefix}_Promo_0900"
$promoAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$Main`" --promo" -WorkingDirectory $ProjectDir
$promoTrigger = New-ScheduledTaskTrigger -Daily -At "09:00"
$promoSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Unregister-ScheduledTask -TaskName $promoTask -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $promoTask -Action $promoAction -Trigger $promoTrigger -Settings $promoSettings -Description "Реклама vadzim.by и @vadzimby_live в @remote_belarus"
Write-Host "OK: $promoTask в 09:00"

# Удалить старые задачи с фиксированными слотами
$LegacySlots = @(
    "Slot1_1000", "Slot2_1215", "Slot3_1430", "Slot4_1645", "Slot5_1900"
)
foreach ($legacy in $LegacySlots) {
    $legacyName = "${TaskPrefix}_$legacy"
    Unregister-ScheduledTask -TaskName $legacyName -Confirm:$false -ErrorAction SilentlyContinue
}

# Одна задача: каждые 5 минут с 09:55 до 20:05 — публикует, если наступил случайный слот
$checkTask = "${TaskPrefix}_Check_5min"
$checkAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$Main`"" -WorkingDirectory $ProjectDir
$checkTrigger = New-ScheduledTaskTrigger -Daily -At "09:55" `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Hours 10 -Minutes 10)
$checkSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -MultipleInstances IgnoreNew
Unregister-ScheduledTask -TaskName $checkTask -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $checkTask -Action $checkAction -Trigger $checkTrigger -Settings $checkSettings -Description "Публикация удалённых IT/маркетинг вакансий по случайному расписанию дня"
Write-Host "OK: $checkTask каждые 5 мин (09:55–20:05)"

Write-Host ""
Write-Host "Готово. Часовой пояс Windows = Минск (UTC+3)."
Write-Host "Расписание на сегодня: python main.py --show-schedule"
Write-Host "Тест вакансии:         python main.py --dry-run --force-slot 0"
Write-Host "Тест рекламы:          python main.py --promo --dry-run"
