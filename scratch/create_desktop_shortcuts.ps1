$desktop = [Environment]::GetFolderPath('Desktop')
if (!(Test-Path $desktop)) {
    $desktop = "$env:USERPROFILE\OneDrive\Desktop"
}
if (!(Test-Path $desktop)) {
    $desktop = "$env:USERPROFILE\Desktop"
}

$WshShell = New-Object -ComObject WScript.Shell

# 1. Game Folder Shortcut
$FolderLnk = $WshShell.CreateShortcut("$desktop\LEGO Batman 3 - Game Folder.lnk")
$FolderLnk.TargetPath = "F:\Games\LEGO-Batman-3-Beyond-Gotham-AnkerGames"
$FolderLnk.Description = "LEGO Batman 3 Game Folder"
$FolderLnk.Save()

# 2. Direct Game Launch Shortcut
$GameLnk = $WshShell.CreateShortcut("$desktop\LEGO Batman 3 Beyond Gotham.lnk")
$GameLnk.TargetPath = "F:\Games\LEGO-Batman-3-Beyond-Gotham-AnkerGames\LEGO Batman 3 Beyond Gotham\LEGOBatman3_DX11.exe"
$GameLnk.WorkingDirectory = "F:\Games\LEGO-Batman-3-Beyond-Gotham-AnkerGames\LEGO Batman 3 Beyond Gotham"
$GameLnk.Description = "Play LEGO Batman 3 Beyond Gotham"
$GameLnk.Save()

Write-Host "Created shortcuts on Desktop: $desktop"
