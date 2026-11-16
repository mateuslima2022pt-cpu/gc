[CmdletBinding()]
param(
    [string]$ServerRoot = 'C:\GrandChaseS2\02_Codigo_Servidor',
    [string]$SqlInstance = 'localhost',
    [string]$OutputRoot = 'C:\GrandChaseS2\PreparacaoVPS',
    [switch]$HelpersOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-GameStopped {
    $names = @('GameServer.exe', 'ColiseuServer.exe', 'CenterServer.exe',
        'CashServer.exe', 'MsgRouter.exe', 'MsgServer.exe', 'TCPRelay.exe', 'RelayServer.exe')
    $running = @(Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $_.Name -in $names })
    if ($running.Count -gt 0) {
        $list = ($running | ForEach-Object { '{0} (PID {1})' -f $_.Name, $_.ProcessId }) -join ', '
        throw "Encerra primeiro os componentes pelo GCAdmin: $list. O SQL Server deve permanecer ligado."
    }
}

function Get-ChildRelativePath([string]$Root, [string]$FullPath) {
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd([char[]]@('\', '/')) + [IO.Path]::DirectorySeparatorChar
    $full = [IO.Path]::GetFullPath($FullPath)
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Ficheiro fora da pasta esperada.'
    }
    return $full.Substring($prefix.Length)
}

function Copy-PreparedFile([string]$Source, [string]$Destination) {
    if ((Get-Item -LiteralPath $Source).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Link encontrado; copia interrompida para revisao: $Source"
    }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Destination)) | Out-Null
    $extension = [IO.Path]::GetExtension($Source).ToLowerInvariant()
    if ($extension -in @('.ini', '.dsn', '.cfg', '.ps1', '.bat', '.lua')) {
        $encoding = [Text.Encoding]::GetEncoding(28591)
        $text = $encoding.GetString([IO.File]::ReadAllBytes($Source))
        if ($extension -in @('.bat', '.ps1') -and
            $text -match '(?im)^\s*(?:tskill\b|taskkill\b[^\r\n]*/f\b)') {
            $Destination += '.DESATIVADO'
            $script:DisabledFiles.Add($Destination)
        }
        [IO.File]::WriteAllBytes($Destination, $encoding.GetBytes($text))
    } else {
        Copy-Item -LiteralPath $Source -Destination $Destination -ErrorAction Stop
    }
}

function Copy-Component([string]$Source, [string]$Destination) {
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($Source)
    [IO.Directory]::CreateDirectory($Destination) | Out-Null
    while ($pending.Count -gt 0) {
        $folder = $pending.Pop()
        foreach ($item in Get-ChildItem -LiteralPath $folder -Force) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Link encontrado; copia interrompida para revisao: $($item.FullName)"
            }
            $relative = Get-ChildRelativePath $Source $item.FullName
            $target = Join-Path $Destination $relative
            if ($item.PSIsContainer) {
                [IO.Directory]::CreateDirectory($target) | Out-Null
                # Keep empty log directories; historical logs are not needed for the migration.
                if ($item.Name -notin @('logs', 'log', 'dumps', 'dump', '__pycache__')) {
                    $pending.Push($item.FullName)
                }
            } elseif ($item.Name -notmatch '(?i)(\.log$|\.dmp$|\.bak$|\.backup|\.antes-|^diagnostico-)') {
                Copy-PreparedFile $item.FullName $target
            }
        }
    }
}

function New-SqlCommand([string]$Sql, [string]$DiskPath = '') {
    $command = $script:Connection.CreateCommand()
    $command.CommandText = $Sql
    $command.CommandTimeout = 3600
    if ($DiskPath) {
        $parameter = $command.Parameters.Add('@disk', [Data.SqlDbType]::NVarChar, 4000)
        $parameter.Value = $DiskPath
    }
    return $command
}

function Invoke-SqlTable([string]$Sql, [string]$DiskPath = '') {
    $command = New-SqlCommand $Sql $DiskPath
    try {
        $table = New-Object Data.DataTable
        $adapter = New-Object Data.SqlClient.SqlDataAdapter $command
        try { [void]$adapter.Fill($table) } finally { $adapter.Dispose() }
        return ,$table
    } finally { $command.Dispose() }
}

function Invoke-SqlNonQuery([string]$Sql, [string]$DiskPath) {
    $command = New-SqlCommand $Sql $DiskPath
    try { [void]$command.ExecuteNonQuery() } finally { $command.Dispose() }
}

if ($HelpersOnly) { return }

$script:Connection = $null
$script:DisabledFiles = New-Object 'System.Collections.Generic.List[string]'
$transcriptStarted = $false
$stage = $null

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Executa esta ferramenta no Windows que aloja o jogo e o SQL Server.'
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal $identity
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Clica com o botao direito no BAT e escolhe Executar como administrador.'
    }
    Assert-GameStopped
    $ServerRoot = [IO.Path]::GetFullPath($ServerRoot).TrimEnd('\')
    $OutputRoot = [IO.Path]::GetFullPath($OutputRoot).TrimEnd('\')
    if (-not (Test-Path -LiteralPath $ServerRoot -PathType Container)) {
        throw "Pasta de servidor nao encontrada: $ServerRoot"
    }
    if ($OutputRoot.Equals($ServerRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $OutputRoot.StartsWith($ServerRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A pasta de saida deve ficar fora da pasta do servidor.'
    }
    $components = [ordered]@{
        'CenterServer' = 'CenterServer.exe'; 'CashServer' = 'CashServer.exe'
        'GameServer' = 'GameServer.exe'; 'MsgRouter' = 'MsgRouter.exe'
        'MsgServer' = 'MsgServer.exe'; 'TCPRelay' = 'TCPRelay.exe'; 'UDPRelay' = 'RelayServer.exe'
    }
    foreach ($name in $components.Keys) {
        $exe = Join-Path (Join-Path $ServerRoot $name) $components[$name]
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
            throw "Executavel obrigatorio nao encontrado: $exe"
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'Verificar-Pacote.ps1'))) {
        throw 'Extrai os ficheiros da ferramenta juntos; falta Verificar-Pacote.ps1.'
    }

    Write-Host '[1/6] A verificar SQL local e bases...' -ForegroundColor Cyan
    $builder = New-Object Data.SqlClient.SqlConnectionStringBuilder
    # Use canonical SQL keywords through the indexer: PowerShell 5.1 adapts this
    # IDictionary and treats dot assignments like DataSource as dictionary keys.
    $builder['Data Source'] = $SqlInstance
    $builder['Initial Catalog'] = 'master'
    $builder['Integrated Security'] = $true
    $builder['Encrypt'] = $true
    $builder['TrustServerCertificate'] = $true
    $builder['Connect Timeout'] = 15
    $builder['Application Name'] = 'GC-PrepararVPS'
    $script:Connection = New-Object Data.SqlClient.SqlConnection ($builder.get_ConnectionString())
    $script:Connection.Open()
    $server = Invoke-SqlTable @'
SELECT CONVERT(nvarchar(128),SERVERPROPERTY('MachineName')) AS MachineName,
       CONVERT(nvarchar(128),SERVERPROPERTY('Edition')) AS Edition,
       CONVERT(nvarchar(128),SERVERPROPERTY('ProductVersion')) AS ProductVersion,
       CONVERT(nvarchar(4000),SERVERPROPERTY('InstanceDefaultBackupPath')) AS BackupPath;
'@
    if (-not ([string]$server.Rows[0].MachineName).Equals($env:COMPUTERNAME, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A instancia SQL nao esta nesta maquina. Esta ferramenta suporta apenas SQL local.'
    }
    $sqlBackupRoot = [string]$server.Rows[0].BackupPath
    if (-not $sqlBackupRoot -or -not (Test-Path -LiteralPath $sqlBackupRoot -PathType Container)) {
        throw 'Pasta de backup padrao do SQL indisponivel. Confirma-a nas propriedades da instancia.'
    }
    $databases = @('gc', 'Log', 'msg', 'stat')
    $dbInfo = Invoke-SqlTable @'
SELECT d.name,d.state_desc,d.is_read_only,d.compatibility_level,
       CONVERT(decimal(18,2),SUM(CASE WHEN m.type=0 THEN CONVERT(bigint,m.size) ELSE 0 END)*8.0/1024) AS DataMB,
       CONVERT(decimal(18,2),SUM(CONVERT(bigint,m.size))*8.0/1024) AS TotalMB
FROM sys.databases d JOIN sys.master_files m ON m.database_id=d.database_id
WHERE d.name IN ('gc','Log','msg','stat')
GROUP BY d.name,d.state_desc,d.is_read_only,d.compatibility_level;
'@
    foreach ($name in $databases) {
        $rows = @($dbInfo.Rows | Where-Object { $_.name -ieq $name })
        if ($rows.Count -ne 1 -or $rows[0].state_desc -ne 'ONLINE') {
            throw "Base ausente ou fora de ONLINE: $name"
        }
    }
    $sourceBytes = [long]((Get-ChildItem -LiteralPath $ServerRoot -Recurse -File | Measure-Object Length -Sum).Sum)
    $estimatedBytes = [long](($dbInfo.Rows | Measure-Object TotalMB -Sum).Sum * 1MB)
    foreach ($root in @($OutputRoot, $sqlBackupRoot)) {
        $drive = New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($root))
        if ($drive.AvailableFreeSpace -lt ($estimatedBytes * 3 + $sourceBytes * 2 + 2GB)) {
            throw "Espaco insuficiente em $($drive.Name). Reserva tres vezes o tamanho das bases, duas vezes a pasta do servidor e mais 2 GB."
        }
    }

    $stamp = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0,6))
    $stage = Join-Path $OutputRoot ('GC-S2-Migracao-' + $stamp)
    $sqlWork = Join-Path $sqlBackupRoot ('GC-S2-Migracao-' + $stamp)
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    [IO.Directory]::CreateDirectory($sqlWork) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $stage 'Bases')) | Out-Null
    Start-Transcript -Path (Join-Path $stage 'PREPARACAO.log') | Out-Null
    $transcriptStarted = $true

    Write-Host '[2/6] Backups COPY_ONLY com CHECKSUM e verificacao...' -ForegroundColor Cyan
    $backups = @()
    foreach ($name in $databases) {
        Assert-GameStopped
        $sourceBak = Join-Path $sqlWork ($name + '.bak')
        Write-Host "Backup de $name. Aguarda; nao inicies o jogo."
        # Database names are drawn from the fixed four-element list, not input from SQL/text.
        Invoke-SqlNonQuery ('BACKUP DATABASE [' + $name + '] TO DISK=@disk WITH COPY_ONLY, CHECKSUM') $sourceBak
        Invoke-SqlNonQuery 'RESTORE VERIFYONLY FROM DISK=@disk WITH CHECKSUM' $sourceBak
        $files = Invoke-SqlTable 'RESTORE FILELISTONLY FROM DISK=@disk' $sourceBak
        $logicalFiles = @($files.Rows | ForEach-Object {
            [pscustomobject]@{ LogicalName=[string]$_.LogicalName; Type=[string]$_.Type; SizeBytes=[long]$_.Size }
        })
        $targetBak = Join-Path (Join-Path $stage 'Bases') ($name + '.bak')
        Copy-Item -LiteralPath $sourceBak -Destination $targetBak -ErrorAction Stop
        if ((Get-FileHash -LiteralPath $sourceBak -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath $targetBak -Algorithm SHA256).Hash) {
            throw "A copia de $name nao coincide com o backup SQL."
        }
        $backups += [pscustomobject]@{ Database=$name; Verified=$true; Files=$logicalFiles }
        Write-Host "$name : backup verificado e copiado." -ForegroundColor Green
    }

    Write-Host '[3/6] A copiar componentes e configuracoes...' -ForegroundColor Cyan
    $serverStage = Join-Path $stage 'Servidor'
    [IO.Directory]::CreateDirectory($serverStage) | Out-Null
    Copy-Component $ServerRoot $serverStage
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Verificar-Pacote.ps1') -Destination $stage
    $dbSizes = @($dbInfo.Rows | ForEach-Object {
        [pscustomobject]@{ Name=[string]$_.name; DataMB=[double]$_.DataMB;
            Compatibility=[int]$_.compatibility_level; FitsExpressSize=([double]$_.DataMB -lt 10240) }
    })
    $metadata = [ordered]@{
        CreatedUTC=[DateTime]::UtcNow.ToString('o'); SourceServerRoot=$ServerRoot;
        SQLInstance=$SqlInstance; SQLEdition=[string]$server.Rows[0].Edition;
        SQLVersion=[string]$server.Rows[0].ProductVersion; Databases=$dbSizes;
        Backups=$backups;
        DisabledForceStopScripts=@($script:DisabledFiles.ToArray() | ForEach-Object { Get-ChildRelativePath $stage $_ });
        OriginalSQLBackups=$sqlWork; ContainsPrivateAccountData=$true
    }
    $metadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stage 'METADADOS.json') -Encoding UTF8
    @'
PACOTE PRIVADO - GRAND CHASE SEASON 2

Bases: gc, Log, msg, stat. Backups integrais COPY_ONLY verificados com CHECKSUM.
As bases incluem contas, hashes de senhas, personagens, itens, triggers e procedimentos corrigidos.
NAO envies este pacote para repositorios publicos nem para o chat.

Os originais ficaram preservados. As configuracoes foram copiadas com os valores
originais, incluindo eventuais senhas. Trata o pacote inteiro como confidencial.
IPs/instancia SQL ainda sao os da maquina local.
Scripts detectados com tskill/taskkill /F receberam o sufixo .DESATIVADO na copia.
Logs antigos, dumps e copias .backup/.antes foram omitidos.

ANTES DE INICIAR NA VPS:
1. Restaurar as quatro bases, usando os nomes logicos de METADADOS.json e WITH MOVE.
2. Configurar instancia SQL, senhas, IP publico/privado e portas do cliente/servidor.
3. Rever tarefas SQL, jobs e dependencias. Logins SQL da instancia NAO sao incluidos em .bak.
4. Testar os executaveis, drivers ODBC x86/x64 e bibliotecas Visual C++ necessarias.
5. Executar Verificar-Pacote.ps1 antes de modificar os ficheiros extraidos.
6. Testar login, jogo, cash, persistencia e encerramento normal antes do acesso publico.

O cliente/main.exe e o GCAdmin nao estao incluidos: serao preparados separadamente.
VERIFYONLY verifica o backup; um restauro real na VPS continua necessario.
'@ | Set-Content -LiteralPath (Join-Path $stage 'LEIA-ANTES-DE-RESTAURAR.txt') -Encoding UTF8
    Assert-GameStopped
    Stop-Transcript | Out-Null
    $transcriptStarted = $false

    Write-Host '[4/6] A criar manifesto SHA256...' -ForegroundColor Cyan
    $manifest = @(Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object {
        [pscustomobject]@{
            Caminho=(Get-ChildRelativePath $stage $_.FullName).Replace('\','/');
            TamanhoBytes=$_.Length; SHA256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    })
    $manifest | Export-Csv -LiteralPath (Join-Path $stage 'MANIFESTO.csv') -NoTypeInformation -Encoding UTF8

    Write-Host '[5/6] A criar ZIP. Bases grandes podem demorar varios minutos...' -ForegroundColor Cyan
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = $stage + '.zip'
    [IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [IO.Compression.CompressionLevel]::Optimal, $false)

    Write-Host '[6/6] A conferir os ficheiros dentro do ZIP...' -ForegroundColor Cyan
    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        $entryMap = @{}
        foreach ($entry in $archive.Entries) { $entryMap[$entry.FullName.Replace('\','/')] = $entry }
        foreach ($record in $manifest) {
            $entry = $entryMap[$record.Caminho]
            if (-not $entry -or $entry.Length -ne [long]$record.TamanhoBytes) {
                throw "Ficheiro ausente ou tamanho incorreto no ZIP: $($record.Caminho)"
            }
            $stream = $entry.Open()
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','') }
            finally { $stream.Dispose(); $sha.Dispose() }
            if ($hash -ne $record.SHA256) { throw "Hash incorreto no ZIP: $($record.Caminho)" }
        }
    } finally { $archive.Dispose() }
    $zipHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
    ($zipHash + '  ' + [IO.Path]::GetFileName($zip)) | Set-Content -LiteralPath ($zip + '.sha256.txt') -Encoding ASCII
    $needsReview = @($dbSizes | Where-Object { -not $_.FitsExpressSize })
    Write-Host ''
    Write-Host 'PREPARACAO CONCLUIDA. Backups e conteudo do ZIP verificados.' -ForegroundColor Green
    Write-Host "ZIP privado: $zip"
    Write-Host "Pasta preparada: $stage"
    Write-Host "Backups SQL originais preservados em: $sqlWork"
    Write-Host 'Os ficheiros do jogo e as bases locais nao foram alterados.'
    if ($needsReview.Count -gt 0) {
        Write-Warning 'Ha bases com 10 GB ou mais de dados. Rever antes de restaurar em SQL Express.'
    }
    if ([int](([string]$server.Rows[0].ProductVersion).Split('.')[0]) -gt 16) {
        Write-Warning 'SQL de origem mais recente que 2022: estes backups nao podem ser restaurados diretamente no SQL 2022. Rever versao da VPS.'
    }
    Write-Host 'Envia apenas uma imagem desta mensagem final; nao envies os .bak nem o ZIP privado.'
} catch {
    if ($stage -and (Test-Path -LiteralPath $stage)) {
        'PACOTE INCOMPLETO - NAO MIGRAR. Corrigir o erro e executar novamente.' |
            Set-Content -LiteralPath (Join-Path $stage 'FALHOU.txt') -Encoding UTF8
    }
    Write-Host ''
    Write-Host ('FALHA: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Nenhum processo foi terminado e nenhum backup existente foi apagado.'
    exit 1
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    if ($script:Connection) { $script:Connection.Dispose() }
}
